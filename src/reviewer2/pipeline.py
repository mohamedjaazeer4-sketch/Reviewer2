"""The Reviewer2 second-reviewer pipeline, as a 4-node LangGraph graph.

    normalise ──▶ fetch_evidence ──▶ score_acmg ──▶ detect_conflicts ──▶ END

Why LangGraph for four nodes? Because it makes the *workflow* explicit, typed, and
checkpoint-able — and it's the production-standard agent framework that the target
roles want to see. Each node is a pure function of the shared, typed state, which
keeps the whole thing reproducible and unit-testable.

Scope discipline (per the working-backwards brief): this is the entire v1 graph.
RAG, an NLI critic node, and a human-approval interrupt are deliberately deferred.
"""

from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import END, StateGraph

from reviewer2.acmg import ENGINE_VERSION, classify, disagreement_score, score_criteria
from reviewer2.conflicts import detect_conflicts
from reviewer2.evidence import EvidenceProvider, get_evidence_provider
from reviewer2.llm import get_llm_client
from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    ConflictFlag,
    EvidenceItem,
    ReviewDossier,
    ReviewRequest,
)
from reviewer2.normalise import normalise_variant
from reviewer2.summary import (
    LLM_SYSTEM_PROMPT,
    provenance_hash,
    render_template_summary,
)


class ReviewState(TypedDict, total=False):
    """Shared state threaded through the graph nodes."""

    request: ReviewRequest
    evidence: list[EvidenceItem]
    criteria: list[ACMGCriterion]
    independent: ACMGClassification
    conflicts: list[ConflictFlag]
    dossier: ReviewDossier


def _node_normalise(state: ReviewState) -> ReviewState:
    request = state["request"]
    request.variant = normalise_variant(request.variant)
    return {"request": request}


def _make_fetch_node(provider: EvidenceProvider):
    def _node_fetch_evidence(state: ReviewState) -> ReviewState:
        evidence = provider.fetch(state["request"].variant)
        return {"evidence": evidence}

    return _node_fetch_evidence


def _node_score_acmg(state: ReviewState) -> ReviewState:
    criteria = score_criteria(state["request"].variant, state["evidence"])
    independent = classify(criteria)
    return {"criteria": criteria, "independent": independent}


def _make_conflicts_node(llm_provider: str | None):
    def _node_detect_conflicts(state: ReviewState) -> ReviewState:
        request = state["request"]
        criteria = state["criteria"]
        independent = state["independent"]
        evidence = state["evidence"]

        conflicts = detect_conflicts(request, independent, evidence)

        # Deterministic summary is the source of truth; LLM only polishes it.
        base_summary = render_template_summary(request, independent, criteria, conflicts)
        client = get_llm_client(llm_provider)
        if client.model_id == "template":
            summary, summary_source = base_summary, "template"
        else:
            try:
                summary = client.complete(LLM_SYSTEM_PROMPT, base_summary)
                summary_source = client.model_id
            except Exception:
                summary, summary_source = base_summary, "template"

        proposed = request.proposed_classification
        score = disagreement_score(proposed, independent) if proposed else 0.0

        dossier = ReviewDossier(
            request=request,
            independent_classification=independent,
            criteria=criteria,
            conflicts=conflicts,
            disagreement_score=score,
            summary=summary,
            summary_source=summary_source,
            engine_version=ENGINE_VERSION,
            provenance_hash=provenance_hash(
                request.variant, evidence, criteria, ENGINE_VERSION
            ),
        )
        return {"conflicts": conflicts, "dossier": dossier}

    return _node_detect_conflicts


def build_graph(
    evidence_provider: EvidenceProvider | None = None,
    llm_provider: str | None = None,
):
    """Compile the 4-node second-reviewer graph.

    Providers are injected so tests and the eval can run fully offline/deterministic.
    """
    provider = evidence_provider or get_evidence_provider(
        os.getenv("REVIEWER2_EVIDENCE_PROVIDER", "fixtures")
    )

    graph = StateGraph(ReviewState)
    graph.add_node("normalise", _node_normalise)
    graph.add_node("fetch_evidence", _make_fetch_node(provider))
    graph.add_node("score_acmg", _node_score_acmg)
    graph.add_node("detect_conflicts", _make_conflicts_node(llm_provider))

    graph.set_entry_point("normalise")
    graph.add_edge("normalise", "fetch_evidence")
    graph.add_edge("fetch_evidence", "score_acmg")
    graph.add_edge("score_acmg", "detect_conflicts")
    graph.add_edge("detect_conflicts", END)

    return graph.compile()


def review_variant(
    request: ReviewRequest,
    evidence_provider: EvidenceProvider | None = None,
    llm_provider: str | None = None,
) -> ReviewDossier:
    """Run the full second-reviewer pipeline and return an auditable dossier."""
    app = build_graph(evidence_provider=evidence_provider, llm_provider=llm_provider)
    final_state = app.invoke({"request": request})
    return final_state["dossier"]
