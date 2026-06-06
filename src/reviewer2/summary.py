"""Deterministic summary rendering + provenance hashing.

``render_template_summary`` produces a faithful, deterministic paragraph from the
structured dossier. This is the text the TemplateClient returns verbatim, and the
text we *ask an LLM to lightly polish* (never to add facts). Keeping a deterministic
summary as the source of truth means the dossier is reproducible regardless of model.

``provenance_hash`` makes runs auditable: identical inputs + evidence + fired criteria
=> identical hash. This is the "re-run and get the same answer" property that signals
reproducibility rigor (and maps to the gwas_nf/Nextflow discipline).
"""

from __future__ import annotations

import hashlib
import json

from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    ConflictFlag,
    ConflictSeverity,
    EvidenceItem,
    ReviewRequest,
    Variant,
)

LLM_SYSTEM_PROMPT = (
    "You are a clinical genomics second reviewer. Rewrite the provided summary so it "
    "reads clearly for a variant scientist. Do NOT add, remove, or change any facts, "
    "numbers, gene names, or classifications. Only improve clarity and flow."
)


def render_template_summary(
    request: ReviewRequest,
    independent: ACMGClassification,
    criteria: list[ACMGCriterion],
    conflicts: list[ConflictFlag],
) -> str:
    fired = [c for c in criteria if c.met]
    fired_codes = ", ".join(c.code for c in fired) or "no criteria"

    lines: list[str] = []
    lines.append(
        f"Reviewer2 independently classifies {request.variant} as "
        f"'{independent.value}' based on {fired_codes}."
    )

    if request.proposed_classification:
        if request.proposed_classification == independent:
            lines.append(
                f"This agrees with the proposed call "
                f"('{request.proposed_classification.value}')."
            )
        else:
            lines.append(
                f"This DISAGREES with the proposed call "
                f"('{request.proposed_classification.value}')."
            )

    if conflicts:
        order = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.MAJOR: 1,
            ConflictSeverity.MINOR: 2,
            ConflictSeverity.INFO: 3,
        }
        ordered = sorted(conflicts, key=lambda c: order.get(c.severity, 99))
        lines.append("Flags for human review:")
        for c in ordered:
            lines.append(f"  - [{c.severity.value.upper()}] {c.message}")
    else:
        lines.append("No conflicts detected.")

    return "\n".join(lines)


def _evidence_fingerprint(evidence: list[EvidenceItem]) -> list[dict]:
    """Stable, order-independent representation of evidence for hashing."""
    items = [
        {
            "source": e.source.value,
            "source_id": e.source_id,
            "quote": e.source_quote,
            "data": {k: e.data[k] for k in sorted(e.data)},
        }
        for e in evidence
    ]
    return sorted(items, key=lambda d: json.dumps(d, sort_keys=True))


def provenance_hash(
    variant: Variant,
    evidence: list[EvidenceItem],
    criteria: list[ACMGCriterion],
    engine_version: str,
) -> str:
    payload = {
        "engine": engine_version,
        "variant": variant.key,
        "evidence": _evidence_fingerprint(evidence),
        "fired": sorted(c.code for c in criteria if c.met),
    }
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
