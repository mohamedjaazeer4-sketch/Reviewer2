"""Concordance — does Reviewer2's INDEPENDENT call match an external expert standard?

This is the eval the postmortem demanded. ErrorCatch answers "does the second reviewer
*flag* disagreements?" — but its ground truth was derived from the engine itself, so it
could not measure accuracy. Concordance answers the harder, honest question:

    Given only population / computational / assertion evidence, does the deterministic
    engine's independent ACMG call match the EXPERT-PANEL (ClinGen VCEP / 3-star ClinVar)
    classification — a gold standard the engine never sees?

We report two numbers, because both matter clinically:

* **Exact concordance**   — engine call == expert call (all 5 tiers).
* **Action-band concordance** — engine and expert fall in the same clinical action band
  (act / monitor / don't-act). This is the number that reflects whether the *decision*
  would differ, and is the more forgiving, more clinically meaningful measure.

Crucially, the test set INCLUDES cases the v1 engine is expected to miss (pathogenic by
functional assay / segregation, which v1 does not implement). We do NOT hide these — we
report concordance on the full set AND on the "engine_should_match" subset, and we print
a confusion matrix, so the number is honest rather than cherry-picked.

Run:  python -m eval.concordance        (or: make concordance)
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from reviewer2.acmg.rules import action_band
from reviewer2.evidence import EvidenceProvider
from reviewer2.models import (
    ACMGClassification,
    EvidenceItem,
    ReviewRequest,
    Variant,
)
from reviewer2.pipeline import review_variant

HERE = Path(__file__).resolve().parent
TESTSET = HERE / "concordance_testset.json"
RESULTS = HERE / "results" / "concordance.json"
console = Console()

# Wilson 95% interval coefficient (z for 0.975).
_Z = 1.96


class _InlineEvidenceProvider(EvidenceProvider):
    def __init__(self, mapping: dict[str, list[EvidenceItem]]) -> None:
        self._mapping = mapping

    def fetch(self, variant: Variant) -> list[EvidenceItem]:
        return list(self._mapping.get(variant.key, []))


def _wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion (honest small-n reporting)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + _Z**2 / n
    centre = (p + _Z**2 / (2 * n)) / denom
    half = (_Z * ((p * (1 - p) / n + _Z**2 / (4 * n**2)) ** 0.5)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _load_cases() -> list[dict]:
    return json.loads(TESTSET.read_text())["cases"]


def _build(case: dict) -> tuple[ReviewRequest, _InlineEvidenceProvider]:
    variant = Variant.model_validate(case["variant"])
    evidence = [EvidenceItem.model_validate(e) for e in case["evidence"]]
    provider = _InlineEvidenceProvider({variant.key: evidence})
    # No proposed_classification: we want the engine's INDEPENDENT call, unanchored.
    request = ReviewRequest(variant=variant, proposed_by="concordance")
    return request, provider


def run() -> dict:
    cases = _load_cases()

    exact_hits = 0
    band_hits = 0
    subset_total = 0
    subset_hits = 0
    rows: list[dict] = []
    confusion: Counter = Counter()

    for case in cases:
        request, provider = _build(case)
        dossier = review_variant(request, evidence_provider=provider, llm_provider="none")
        engine = dossier.independent_classification
        expert = ACMGClassification(case["expert_truth"])

        exact = engine == expert
        band = action_band(engine) == action_band(expert)
        exact_hits += int(exact)
        band_hits += int(band)

        if case.get("engine_should_match", True):
            subset_total += 1
            subset_hits += int(exact)

        confusion[(expert.value, engine.value)] += 1
        rows.append(
            {
                "id": case["id"],
                "gene": case["gene"],
                "expert_truth": expert.value,
                "engine_call": engine.value,
                "exact_match": exact,
                "band_match": band,
                "expected_to_match": case.get("engine_should_match", True),
                "note": case.get("_why_miss"),
            }
        )

    n = len(cases)
    exact_rate = exact_hits / n if n else 0.0
    band_rate = band_hits / n if n else 0.0
    subset_rate = subset_hits / subset_total if subset_total else 0.0

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "exact_concordance": round(exact_rate, 3),
        "exact_concordance_ci95": [round(x, 3) for x in _wilson(exact_hits, n)],
        "action_band_concordance": round(band_rate, 3),
        "action_band_concordance_ci95": [round(x, 3) for x in _wilson(band_hits, n)],
        "n_in_scope": subset_total,
        "in_scope_exact_concordance": round(subset_rate, 3),
        "in_scope_ci95": [round(x, 3) for x in _wilson(subset_hits, subset_total)],
        "confusion": [
            {"expert": e, "engine": g, "count": c} for (e, g), c in sorted(confusion.items())
        ],
        "rows": rows,
    }
    return result


def _print(result: dict) -> None:
    console.print(
        f"\n[bold]Concordance[/bold] vs expert-panel ClinVar on n={result['n']} variants:\n"
        f"  exact (5-tier):     [bold]{result['exact_concordance']:.0%}[/bold] "
        f"(95% CI {result['exact_concordance_ci95'][0]:.0%}–{result['exact_concordance_ci95'][1]:.0%})\n"
        f"  action-band:        [bold green]{result['action_band_concordance']:.0%}[/bold green] "
        f"(95% CI {result['action_band_concordance_ci95'][0]:.0%}–{result['action_band_concordance_ci95'][1]:.0%})\n"
        f"  in-scope exact:     [bold]{result['in_scope_exact_concordance']:.0%}[/bold] "
        f"on the {result['n_in_scope']} cases the v1 engine is designed to handle "
        f"(the rest need PS3/PP1 etc. — known blind spots).\n"
    )

    table = Table(title="Per-variant concordance")
    table.add_column("id")
    table.add_column("gene")
    table.add_column("expert")
    table.add_column("engine")
    table.add_column("exact")
    table.add_column("band")
    table.add_column("in-scope")
    for r in result["rows"]:
        exact = "[green]✓[/green]" if r["exact_match"] else "[red]✗[/red]"
        band = "[green]✓[/green]" if r["band_match"] else "[red]✗[/red]"
        scope = "yes" if r["expected_to_match"] else "[dim]no (blind spot)[/dim]"
        table.add_row(r["id"], r["gene"], r["expert_truth"], r["engine_call"], exact, band, scope)
    console.print(table)

    console.print(
        "[dim]Action-band concordance is the clinically meaningful number: it asks whether "
        "the management decision (act / monitor / don't-act) would differ.[/dim]"
    )


def main() -> None:
    result = run()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2))
    _print(result)
    console.print(f"[dim]Wrote {RESULTS}[/dim]")


if __name__ == "__main__":
    main()
