"""gnomad-clinvar-mcp — a standalone MCP server exposing Reviewer2's genomics tools.

Why this exists: most bioinformatics code *consumes* APIs. Shipping an MCP server
means any MCP-capable agent (Claude Desktop, VS Code Copilot, a LangGraph agent) can
call your gnomAD/ClinVar lookups and the full ACMG second-review as tools. That is the
"produce, don't just consume" MCP skill the target roles want to see.

Tools exposed:
    get_evidence(variant)        -> structured gnomAD/ClinVar/VEP evidence
    review_variant(variant, ...) -> full Reviewer2 ACMG dossier (JSON)

Run:
    uv run --extra mcp python -m mcp_server.server         # stdio transport
or wire it into an MCP host config (see README).

Note: this module imports the optional `mcp` package lazily so the core stays light.
"""

from __future__ import annotations

import json
from typing import Any

from reviewer2.evidence import get_evidence_provider
from reviewer2.models import ACMGClassification, ReviewRequest, Variant
from reviewer2.pipeline import review_variant


def _build_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP server needs the 'mcp' extra: `uv sync --extra mcp`."
        ) from exc

    mcp = FastMCP("gnomad-clinvar-mcp")

    @mcp.tool()
    def get_evidence(
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        genome: str = "GRCh38",
        gene: str | None = None,
    ) -> str:
        """Fetch gnomAD / ClinVar / VEP / in-silico evidence for a germline variant.

        Returns a JSON list of evidence items, each with the literal source quote so
        the calling agent can ground its own claims.
        """
        provider = get_evidence_provider()
        variant = Variant(genome=genome, chrom=chrom, pos=pos, ref=ref, alt=alt, gene=gene)
        evidence = provider.fetch(variant)
        return json.dumps([json.loads(e.model_dump_json()) for e in evidence], indent=2)

    @mcp.tool()
    def review_variant_tool(
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        genome: str = "GRCh38",
        gene: str | None = None,
        proposed_classification: str | None = None,
    ) -> str:
        """Run the full Reviewer2 ACMG second-review and return an auditable dossier.

        ``proposed_classification`` (optional) is audited against Reviewer2's
        independent call; the dossier lists fired criteria, conflicts, and a
        provenance hash.
        """
        proposed = (
            ACMGClassification(proposed_classification) if proposed_classification else None
        )
        request = ReviewRequest(
            variant=Variant(genome=genome, chrom=chrom, pos=pos, ref=ref, alt=alt, gene=gene),
            proposed_classification=proposed,
        )
        dossier = review_variant(request, llm_provider="none")
        return dossier.model_dump_json(indent=2)

    return mcp


def main() -> None:  # pragma: no cover
    server = _build_server()
    server.run()


if __name__ == "__main__":  # pragma: no cover
    main()
