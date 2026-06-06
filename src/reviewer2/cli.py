"""Reviewer2 command-line interface.

    reviewer2 review --gene BRCA1 --hgvs-p p.Glu23fs --proposed "Uncertain significance"
    reviewer2 demo            # run the bundled fixture cases
    reviewer2 demo --json     # machine-readable dossiers

The CLI renders an auditable dossier with Rich so the terminal output itself is a
compelling README screenshot.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from reviewer2.evidence import FixtureEvidenceProvider
from reviewer2.models import (
    ACMGClassification,
    ConflictSeverity,
    ReviewDossier,
    ReviewRequest,
    Variant,
)
from reviewer2.pipeline import review_variant

app = typer.Typer(add_completion=False, help="Reviewer2 — evidence-grounded ACMG second reviewer.")
console = Console()

_SEVERITY_STYLE = {
    ConflictSeverity.INFO: "dim",
    ConflictSeverity.MINOR: "yellow",
    ConflictSeverity.MAJOR: "bold orange1",
    ConflictSeverity.CRITICAL: "bold red",
}

_CLASS_STYLE = {
    ACMGClassification.PATHOGENIC: "bold red",
    ACMGClassification.LIKELY_PATHOGENIC: "red",
    ACMGClassification.VUS: "yellow",
    ACMGClassification.LIKELY_BENIGN: "green",
    ACMGClassification.BENIGN: "bold green",
}


def _render(dossier: ReviewDossier) -> None:
    req = dossier.request
    indep = dossier.independent_classification
    style = _CLASS_STYLE.get(indep, "white")

    header = f"[bold]{req.variant}[/bold]\n"
    header += f"Independent call: [{style}]{indep.value}[/{style}]"
    if req.proposed_classification:
        agree = req.proposed_classification == indep
        tag = "[green]AGREES[/green]" if agree else "[bold red]DISAGREES[/bold red]"
        header += (
            f"   vs proposed: {req.proposed_classification.value}  {tag}"
            f"   (disagreement {dossier.disagreement_score:.2f})"
        )
    console.print(Panel(header, title="Reviewer2 dossier", border_style=style))

    # Fired criteria with their grounding quote.
    fired = dossier.fired_criteria
    if fired:
        table = Table(title="Fired ACMG criteria (with source grounding)", show_lines=False)
        table.add_column("Code", style="bold")
        table.add_column("Dir")
        table.add_column("Strength")
        table.add_column("Rationale")
        table.add_column("Source quote", style="dim")
        for c in fired:
            quote = c.evidence[0].source_quote if c.evidence else ""
            table.add_row(
                c.code,
                c.direction.value[:4],
                c.strength.value,
                c.rationale,
                quote,
            )
        console.print(table)
    else:
        console.print("[dim]No ACMG criteria fired.[/dim]")

    # Conflicts.
    if dossier.conflicts:
        console.print("[bold]Flags for human review:[/bold]")
        for cf in dossier.conflicts:
            s = _SEVERITY_STYLE.get(cf.severity, "white")
            console.print(f"  [{s}]\\[{cf.severity.value.upper()}][/{s}] {cf.message}")
    else:
        console.print("[green]No conflicts detected.[/green]")

    console.print(
        f"[dim]engine={dossier.engine_version}  "
        f"provenance={dossier.provenance_hash}  "
        f"summary_by={dossier.summary_source}[/dim]\n"
    )


@app.command()
def review(
    gene: str = typer.Option(None, help="HGNC gene symbol, e.g. BRCA1."),
    chrom: str = typer.Option("17", help="Chromosome."),
    pos: int = typer.Option(..., help="1-based position."),
    ref: str = typer.Option(..., help="Reference allele."),
    alt: str = typer.Option(..., help="Alternate allele."),
    hgvs_p: str = typer.Option(None, "--hgvs-p", help="Protein HGVS."),
    proposed: str = typer.Option(None, help="Proposed ACMG classification to audit."),
    llm: str = typer.Option(None, help="LLM provider override (ollama/anthropic/openai/gemini/none)."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON dossier."),
) -> None:
    """Review a single variant."""
    proposed_cls = ACMGClassification(proposed) if proposed else None
    request = ReviewRequest(
        variant=Variant(chrom=chrom, pos=pos, ref=ref, alt=alt, gene=gene, hgvs_p=hgvs_p),
        proposed_classification=proposed_cls,
    )
    dossier = review_variant(request, llm_provider=llm)
    if as_json:
        console.print_json(dossier.model_dump_json(indent=2))
    else:
        _render(dossier)


@app.command()
def demo(
    llm: str = typer.Option("none", help="LLM provider (default 'none' = offline template)."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON dossiers."),
) -> None:
    """Run Reviewer2 over the bundled fixture cases (fully offline)."""
    provider = FixtureEvidenceProvider()
    cases = _demo_cases()
    results = []
    for request in cases:
        dossier = review_variant(request, evidence_provider=provider, llm_provider=llm)
        results.append(dossier)
        if not as_json:
            _render(dossier)
    if as_json:
        console.print_json(json.dumps([json.loads(d.model_dump_json()) for d in results]))


def _demo_cases() -> list[ReviewRequest]:
    """The fixture variants, paired with the proposed calls we want to audit.

    These align with eval/fixtures/evidence.json. The headline case is a variant
    whose ClinVar record is stale relative to the proposed VUS call.
    """
    return [
        ReviewRequest(
            variant=Variant(
                genome="GRCh38", chrom="17", pos=43093464, ref="A", alt="T",
                gene="BRCA1", hgvs_p="p.Glu23fs", rsid="rs80357914",
            ),
            proposed_classification=ACMGClassification.VUS,
            proposed_by="legacy_pipeline_v3",
            condition="Hereditary breast and ovarian cancer",
        ),
        ReviewRequest(
            variant=Variant(
                genome="GRCh38", chrom="1", pos=55039974, ref="G", alt="A",
                gene="PCSK9", hgvs_p="p.Arg46Leu", rsid="rs11591147",
            ),
            proposed_classification=ACMGClassification.LIKELY_PATHOGENIC,
            proposed_by="curator_a",
            condition="Hypercholesterolemia",
        ),
        ReviewRequest(
            variant=Variant(
                genome="GRCh38", chrom="13", pos=32340301, ref="T", alt="C",
                gene="BRCA2", hgvs_p="p.Val2466Ala", rsid="rs169547",
            ),
            proposed_classification=ACMGClassification.VUS,
            proposed_by="curator_b",
            condition="Hereditary breast and ovarian cancer",
        ),
    ]


if __name__ == "__main__":  # pragma: no cover
    app()
