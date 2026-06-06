"""Typed domain model for Reviewer2.

Every object that flows through the pipeline is a Pydantic model. This is a
deliberate senior-engineering signal *and* a correctness tool: the ACMG engine
cannot silently produce an untyped dict, and every classification is forced to
carry the evidence that justifies it.

Design rule (from the working-backwards brief): **no claim without a source.**
Each fired :class:`ACMGCriterion` must reference at least one :class:`EvidenceItem`,
and each :class:`EvidenceItem` carries the exact source quote so a human can verify
it. That is what "transparent evidence grounding" means in v1 (no NLI black box).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)



# --------------------------------------------------------------------------- #
# Core variant identity
# --------------------------------------------------------------------------- #
class Genome(str, Enum):
    GRCH37 = "GRCh37"
    GRCH38 = "GRCh38"


class Zygosity(str, Enum):
    HET = "heterozygous"
    HOM = "homozygous"
    HEMI = "hemizygous"
    UNKNOWN = "unknown"


class Variant(BaseModel):
    """A germline small variant in normalised form.

    We key on the VCF-style 5-tuple (genome, chrom, pos, ref, alt) because it is
    unambiguous; HGVS and rsID are carried along for human readability and joins.
    """

    genome: Genome = Genome.GRCH38
    chrom: str = Field(..., description="Chromosome, no 'chr' prefix, e.g. '17'.")
    pos: int = Field(..., gt=0, description="1-based position.")
    ref: str = Field(..., pattern=r"^[ACGT]+$")
    alt: str = Field(..., pattern=r"^[ACGT]+$")

    gene: str | None = Field(None, description="HGNC symbol, e.g. 'BRCA1'.")
    hgvs_c: str | None = Field(None, description="Coding HGVS, e.g. 'c.68_69del'.")
    hgvs_p: str | None = Field(None, description="Protein HGVS, e.g. 'p.Glu23fs'.")
    rsid: str | None = Field(None, description="dbSNP id, e.g. 'rs80357914'.")
    zygosity: Zygosity = Zygosity.UNKNOWN

    @property
    def key(self) -> str:
        """Stable, hashable identity used for caching and provenance."""
        return f"{self.genome.value}-{self.chrom}-{self.pos}-{self.ref}-{self.alt}"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        label = self.gene or self.chrom
        detail = self.hgvs_p or self.hgvs_c or f"{self.pos}{self.ref}>{self.alt}"
        return f"{label} {detail}"


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
class EvidenceSource(str, Enum):
    CLINVAR = "ClinVar"
    GNOMAD = "gnomAD"
    VEP = "VEP"
    COMPUTATIONAL = "computational"  # AlphaMissense/REVEL-style in-silico
    LITERATURE = "literature"        # v1.1+
    INTERNAL = "internal"


class EvidenceItem(BaseModel):
    """A single piece of evidence, with the exact text needed to verify it.

    ``source_quote`` is the load-bearing field: it is the literal sentence/value
    pulled from the source so a reviewer can confirm the claim without trusting
    the model. ``retrieved_at`` + ``source_last_updated`` power staleness checks.
    """

    source: EvidenceSource
    summary: str = Field(..., description="One-line human summary of this evidence.")
    source_quote: str = Field(
        ..., description="Literal value/sentence from the source backing the claim."
    )
    source_id: str | None = Field(
        None, description="Stable id within the source, e.g. ClinVar VCV/RCV accession."
    )
    url: str | None = None

    # Structured payload (provider-specific but typed where it matters).
    data: dict[str, str | float | int | bool | None] = Field(default_factory=dict)

    retrieved_at: datetime = Field(default_factory=_utcnow)
    source_last_updated: date | None = Field(
        None, description="When the source last changed this record (for staleness)."
    )

    def staleness_days(self) -> int | None:
        if self.source_last_updated is None:
            return None
        return (self.retrieved_at.date() - self.source_last_updated).days


# --------------------------------------------------------------------------- #
# ACMG/AMP criteria
# --------------------------------------------------------------------------- #
class CriterionDirection(str, Enum):
    PATHOGENIC = "pathogenic"
    BENIGN = "benign"


class CriterionStrength(str, Enum):
    # Pathogenic strengths
    STANDALONE = "standalone"        # BA1 (benign) — handled by direction
    VERY_STRONG = "very_strong"      # PVS1
    STRONG = "strong"                # PS1..PS4 / BS1..BS4
    MODERATE = "moderate"            # PM1..PM6
    SUPPORTING = "supporting"        # PP1..PP5 / BP1..BP7


class ACMGCriterion(BaseModel):
    """One ACMG/AMP criterion evaluation (e.g. PVS1, PM2, BA1, BS1).

    A criterion only counts as *fired* (``met=True``) if it carries supporting
    evidence. The validator enforces the project's core rule.
    """

    code: str = Field(..., description="ACMG code, e.g. 'PVS1', 'PM2', 'BA1'.")
    direction: CriterionDirection
    strength: CriterionStrength
    met: bool = Field(..., description="Whether this criterion fired for this variant.")
    rationale: str = Field(..., description="Why it did/did not fire, in plain English.")
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_fired_criterion_without_evidence(self) -> ACMGCriterion:
        if self.met and not self.evidence:
            raise ValueError(
                f"Criterion {self.code} is marked met=True but carries no evidence. "
                "Reviewer2 forbids claims without a source."
            )
        return self


class ACMGClassification(str, Enum):
    PATHOGENIC = "Pathogenic"
    LIKELY_PATHOGENIC = "Likely pathogenic"
    VUS = "Uncertain significance"
    LIKELY_BENIGN = "Likely benign"
    BENIGN = "Benign"


# --------------------------------------------------------------------------- #
# Conflicts (the "second reviewer disagrees" output)
# --------------------------------------------------------------------------- #
class ConflictSeverity(str, Enum):
    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"          # e.g. P/LP vs B/LB disagreement
    CRITICAL = "critical"    # clinically actionable direction flip


class ConflictType(str, Enum):
    CLASSIFICATION_DISAGREEMENT = "classification_disagreement"
    CLINVAR_SUBMITTER_CONFLICT = "clinvar_submitter_conflict"
    STALE_EVIDENCE = "stale_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    CRITERION_MISAPPLIED = "criterion_misapplied"


class ConflictFlag(BaseModel):
    """A specific, human-actionable disagreement raised by the second reviewer."""

    type: ConflictType
    severity: ConflictSeverity
    message: str = Field(..., description="What the reviewer should look at, specifically.")
    evidence: list[EvidenceItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Request / response
# --------------------------------------------------------------------------- #
class ReviewRequest(BaseModel):
    """Input to the second reviewer.

    ``proposed_classification`` is what a human curator or an upstream tool claims;
    Reviewer2 independently re-derives its own call and compares. It may be omitted
    to run Reviewer2 as a first-pass classifier.
    """

    variant: Variant
    proposed_classification: ACMGClassification | None = None
    proposed_by: str | None = Field(None, description="Curator / tool that made the call.")
    condition: str | None = Field(None, description="Clinical context, e.g. 'HBOC'.")


class ReviewDossier(BaseModel):
    """The auditable output. Everything needed to trust (or challenge) the call."""

    request: ReviewRequest

    independent_classification: ACMGClassification
    criteria: list[ACMGCriterion]
    conflicts: list[ConflictFlag] = Field(default_factory=list)

    disagreement_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="0 = full agreement with proposed call; 1 = maximal disagreement.",
    )
    summary: str = Field(..., description="Plain-English summary (template or LLM-written).")
    summary_source: str = Field(
        "template", description="'template' or the LLM model id that wrote the summary."
    )

    # Provenance / reproducibility
    engine_version: str = Field(..., description="Reviewer2 ACMG engine version.")
    provenance_hash: str = Field(
        ..., description="Deterministic hash of (variant, evidence, fired criteria)."
    )
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def fired_criteria(self) -> list[ACMGCriterion]:
        return [c for c in self.criteria if c.met]

    @property
    def has_major_conflict(self) -> bool:
        return any(
            c.severity in (ConflictSeverity.MAJOR, ConflictSeverity.CRITICAL)
            for c in self.conflicts
        )
