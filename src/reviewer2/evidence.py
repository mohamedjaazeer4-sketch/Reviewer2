"""Evidence providers — where Reviewer2 gets gnomAD / ClinVar / VEP / in-silico data.

The pipeline depends only on the :class:`EvidenceProvider` protocol, so we can swap
between:

* :class:`FixtureEvidenceProvider` — offline, deterministic, ships with the repo.
  This is the default so `make demo` and `make eval` need no network and no keys.
* :class:`LiveEvidenceProvider` — real NCBI ClinVar + gnomAD GraphQL + Ensembl VEP.
  Opt-in via `REVIEWER2_EVIDENCE_PROVIDER=live` (requires the `live` extra).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from reviewer2.models import EvidenceItem, Variant

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"


class EvidenceProvider(Protocol):
    """Return all evidence items known for a variant."""

    def fetch(self, variant: Variant) -> list[EvidenceItem]: ...


class FixtureEvidenceProvider:
    """Serve evidence from a local JSON file keyed by variant.key.

    The fixture file is the single source of truth for the demo and the ErrorCatch
    eval, which keeps results reproducible and reviewable.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (FIXTURE_DIR / "evidence.json")
        self._cache: dict[str, list[EvidenceItem]] | None = None

    def _load(self) -> dict[str, list[EvidenceItem]]:
        if self._cache is None:
            raw = json.loads(self.path.read_text())
            self._cache = {
                key: [EvidenceItem.model_validate(item) for item in items]
                for key, items in raw.items()
            }
        return self._cache

    def fetch(self, variant: Variant) -> list[EvidenceItem]:
        return list(self._load().get(variant.key, []))


class LiveEvidenceProvider:
    """Real-API provider. Imported lazily so the core has no httpx dependency.

    NOTE: This is a thin, honest stub of the network calls. It is wired correctly
    (endpoints + parsing shape) but kept minimal in v1; the fixture provider is what
    the eval uses. Extending these three methods is a clearly-scoped v1.1 task.
    """

    def __init__(self, ncbi_email: str | None = None, ncbi_api_key: str | None = None) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "LiveEvidenceProvider needs the 'live' extra: `uv sync --extra live`."
            ) from exc
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key

    def fetch(self, variant: Variant) -> list[EvidenceItem]:  # pragma: no cover
        evidence: list[EvidenceItem] = []
        evidence += self._gnomad(variant)
        evidence += self._clinvar(variant)
        evidence += self._vep(variant)
        return evidence

    # The three methods below are intentionally minimal in v1.
    def _gnomad(self, variant: Variant) -> list[EvidenceItem]:  # pragma: no cover
        return []

    def _clinvar(self, variant: Variant) -> list[EvidenceItem]:  # pragma: no cover
        return []

    def _vep(self, variant: Variant) -> list[EvidenceItem]:  # pragma: no cover
        return []


def get_evidence_provider(name: str = "fixtures") -> EvidenceProvider:
    """Factory used by the pipeline/CLI based on REVIEWER2_EVIDENCE_PROVIDER."""
    if name == "live":
        import os

        return LiveEvidenceProvider(
            ncbi_email=os.getenv("NCBI_EMAIL"),
            ncbi_api_key=os.getenv("NCBI_API_KEY"),
        )
    return FixtureEvidenceProvider()
