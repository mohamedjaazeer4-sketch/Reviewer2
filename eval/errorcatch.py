"""ErrorCatch — the honest evaluation harness for Reviewer2.

This is the headline artifact. Every other genomics-AI repo shows the happy path;
ErrorCatch injects *known* classification errors and measures how many Reviewer2
catches — and, just as importantly, how many correct calls it wrongly flags.

Definitions (stated plainly so an interviewer can interrogate them):

* A case is "caught" if Reviewer2 raises a CLASSIFICATION_DISAGREEMENT (or, for the
  submitter-conflict case, the corresponding conflict flag) on a case where
  ``is_injected_error == true``.
* **Catch rate** = caught / number of injected errors, reported overall and per
  error_type.
* **False-positive rate** = (controls flagged with a classification disagreement) /
  (number of controls). Controls have ``is_injected_error == false``.

The harness reads inline evidence from the test set, so it is fully self-contained,
offline, and deterministic. Results are written to eval/results/errorcatch.json.

Run:  python -m eval.errorcatch          (or: make eval)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from reviewer2.evidence import EvidenceProvider
from reviewer2.models import (
    ACMGClassification,
    ConflictSeverity,
    ConflictType,
    EvidenceItem,
    ReviewRequest,
    Variant,
)
from reviewer2.pipeline import review_variant

HERE = Path(__file__).resolve().parent
TESTSET = HERE / "errorcatch_testset.json"
RESULTS = HERE / "results" / "errorcatch.json"
console = Console()

# A conflict "blocks" sign-off if it is anything more than an informational note.
# Within-band classification differences (e.g. Pathogenic vs Likely pathogenic) are
# emitted at INFO severity precisely so they do NOT count here — that is what keeps
# the false-positive rate honest.
_BLOCKING = {ConflictSeverity.MINOR, ConflictSeverity.MAJOR, ConflictSeverity.CRITICAL}



class _InlineEvidenceProvider(EvidenceProvider):
    """Serve the evidence embedded in each ErrorCatch case, keyed by variant.key."""

    def __init__(self, mapping: dict[str, list[EvidenceItem]]) -> None:
        self._mapping = mapping

    def fetch(self, variant: Variant) -> list[EvidenceItem]:
        return list(self._mapping.get(variant.key, []))


def _load_cases() -> list[dict]:
    return json.loads(TESTSET.read_text())["cases"]


def _build(case: dict) -> tuple[ReviewRequest, _InlineEvidenceProvider]:
    variant = Variant.model_validate(case["variant"])
    evidence = [EvidenceItem.model_validate(e) for e in case["evidence"]]
    provider = _InlineEvidenceProvider({variant.key: evidence})
    request = ReviewRequest(
        variant=variant,
        proposed_classification=ACMGClassification(case["proposed_classification"]),
        proposed_by="errorcatch",
    )
    return request, provider


def _was_caught(case: dict, dossier) -> bool:
    """Did Reviewer2 flag this case in a way that would stop a human approving it?"""
    blocking_types = {c.type for c in dossier.conflicts if c.severity in _BLOCKING}
    if ConflictType.CLASSIFICATION_DISAGREEMENT in blocking_types:
        return True
    # Submitter-conflict cases may agree on the point call but must still be flagged.
    if case["error_type"] == "clinvar_submitter_conflict":
        return ConflictType.CLINVAR_SUBMITTER_CONFLICT in blocking_types
    if case["error_type"] == "stale_clinvar":
        return (
            ConflictType.STALE_EVIDENCE in blocking_types
            or ConflictType.CLASSIFICATION_DISAGREEMENT in blocking_types
        )
    return False


def _is_false_positive(dossier) -> bool:
    """A control is a false positive only if a *blocking* disagreement is raised.

    Informational, within-band notes (Pathogenic vs Likely pathogenic) are not
    counted — they do not interrupt sign-off.
    """
    return any(
        c.type == ConflictType.CLASSIFICATION_DISAGREEMENT and c.severity in _BLOCKING
        for c in dossier.conflicts
    )



def run() -> dict:
    cases = _load_cases()
    injected = [c for c in cases if c["is_injected_error"]]
    controls = [c for c in cases if not c["is_injected_error"]]

    per_type_total: dict[str, int] = defaultdict(int)
    per_type_caught: dict[str, int] = defaultdict(int)
    rows: list[dict] = []

    caught_total = 0
    for case in injected:
        request, provider = _build(case)
        dossier = review_variant(request, evidence_provider=provider, llm_provider="none")
        caught = _was_caught(case, dossier)
        caught_total += int(caught)
        per_type_total[case["error_type"]] += 1
        per_type_caught[case["error_type"]] += int(caught)
        rows.append(
            {
                "id": case["id"],
                "error_type": case["error_type"],
                "expected_truth": case["expected_truth"],
                "proposed": case["proposed_classification"],
                "reviewer2_call": dossier.independent_classification.value,
                "caught": caught,
            }
        )

    false_positives = 0
    for case in controls:
        request, provider = _build(case)
        dossier = review_variant(request, evidence_provider=provider, llm_provider="none")
        flagged = _is_false_positive(dossier)
        false_positives += int(flagged)
        rows.append(
            {
                "id": case["id"],
                "error_type": case["error_type"],
                "expected_truth": case["expected_truth"],
                "proposed": case["proposed_classification"],
                "reviewer2_call": dossier.independent_classification.value,
                "caught": None,
                "false_positive": flagged,
            }
        )

    catch_rate = caught_total / len(injected) if injected else 0.0
    fp_rate = false_positives / len(controls) if controls else 0.0

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_injected": len(injected),
        "n_controls": len(controls),
        "caught": caught_total,
        "catch_rate": round(catch_rate, 3),
        "false_positives": false_positives,
        "false_positive_rate": round(fp_rate, 3),
        "per_type": {
            t: {"caught": per_type_caught[t], "total": per_type_total[t]}
            for t in sorted(per_type_total)
        },
        "rows": rows,
    }
    return result


def _print(result: dict) -> None:
    console.print(
        f"\n[bold]ErrorCatch[/bold] — {result['caught']}/{result['n_injected']} injected "
        f"errors caught  ([bold green]catch rate {result['catch_rate']:.0%}[/bold green]);  "
        f"false-positive rate [bold]{result['false_positive_rate']:.0%}[/bold] "
        f"on {result['n_controls']} controls.\n"
    )

    table = Table(title="Catch rate by error type")
    table.add_column("Error type", style="bold")
    table.add_column("Caught / total")
    table.add_column("Rate")
    for t, d in result["per_type"].items():
        rate = d["caught"] / d["total"] if d["total"] else 0.0
        table.add_row(t, f"{d['caught']}/{d['total']}", f"{rate:.0%}")
    console.print(table)

    detail = Table(title="Per-case detail")
    detail.add_column("id")
    detail.add_column("type")
    detail.add_column("proposed")
    detail.add_column("reviewer2")
    detail.add_column("result")
    for r in result["rows"]:
        if r.get("caught") is None:
            outcome = "[red]FALSE POS[/red]" if r.get("false_positive") else "[green]ok[/green]"
        else:
            outcome = "[green]CAUGHT[/green]" if r["caught"] else "[red]MISSED[/red]"
        detail.add_row(r["id"], r["error_type"], r["proposed"], r["reviewer2_call"], outcome)
    console.print(detail)


def main() -> None:
    result = run()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2))
    _print(result)
    console.print(f"[dim]Wrote {RESULTS}[/dim]")


if __name__ == "__main__":
    main()
