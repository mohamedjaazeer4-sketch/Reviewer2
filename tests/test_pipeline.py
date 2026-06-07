"""Tests for the scorer, conflict detection, pipeline, and the no-claim-without-source rule."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reviewer2 import ReviewRequest, Variant, review_variant
from reviewer2.acmg.rules import classify
from reviewer2.acmg.scorer import score_criteria
from reviewer2.evidence import FixtureEvidenceProvider
from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    ConflictType,
    CriterionDirection,
    CriterionStrength,
    EvidenceItem,
    EvidenceSource,
)


def _evidence(**data) -> EvidenceItem:
    src = data.pop("source", EvidenceSource.GNOMAD)
    return EvidenceItem(
        source=src,
        summary="t",
        source_quote="t",
        data=data,
    )


def test_no_fired_criterion_without_evidence():
    with pytest.raises(ValidationError):
        ACMGCriterion(
            code="PM2",
            direction=CriterionDirection.PATHOGENIC,
            strength=CriterionStrength.SUPPORTING,
            met=True,
            rationale="missing evidence on purpose",
            evidence=[],
        )


def test_ba1_fires_on_common_variant():
    v = Variant(chrom="13", pos=32340301, ref="T", alt="C", gene="BRCA2")
    ev = [_evidence(source=EvidenceSource.GNOMAD, allele_frequency=0.26)]
    crits = {c.code: c for c in score_criteria(v, ev)}
    assert crits["BA1"].met is True


def test_pm2_fires_on_absent_variant():
    v = Variant(chrom="17", pos=43093464, ref="A", alt="T", gene="BRCA1")
    ev = [_evidence(source=EvidenceSource.GNOMAD, allele_frequency=0.0)]
    crits = {c.code: c for c in score_criteria(v, ev)}
    assert crits["PM2"].met is True
    assert crits["BA1"].met is False


def test_pvs1_only_in_lof_gene():
    ev = [_evidence(source=EvidenceSource.VEP, consequence="frameshift_variant")]
    in_gene = Variant(chrom="17", pos=43093464, ref="A", alt="T", gene="BRCA1")
    not_gene = Variant(chrom="1", pos=100, ref="A", alt="T", gene="MADEUP1")
    assert {c.code: c for c in score_criteria(in_gene, ev)}["PVS1"].met is True
    assert {c.code: c for c in score_criteria(not_gene, ev)}["PVS1"].met is False


def test_clean_null_reaches_likely_pathogenic_without_ps1():
    """Regression for the postmortem under-call bug: a clean null variant absent from
    gnomAD must reach at least Likely pathogenic on PVS1(Very Strong)+PM2(Moderate)
    alone — WITHOUT relying on a fabricated same-amino-acid (PS1) flag."""
    v = Variant(chrom="17", pos=7675000, ref="C", alt="T", gene="TP53", hgvs_p="p.Arg213*")
    ev = [
        _evidence(source=EvidenceSource.VEP, consequence="stop_gained"),
        _evidence(source=EvidenceSource.GNOMAD, allele_frequency=0.0),
    ]
    crits = {c.code: c for c in score_criteria(v, ev)}
    assert crits["PVS1"].met is True
    assert crits["PVS1"].strength == CriterionStrength.VERY_STRONG
    independent = classify(list(crits.values()))
    assert independent in (
        ACMGClassification.LIKELY_PATHOGENIC,
        ACMGClassification.PATHOGENIC,
    )


def test_pvs1_downgrades_on_nmd_escape_hint():
    """Transcript/NMD context downgrades PVS1 strength (ClinGen SVI tree)."""
    v = Variant(chrom="17", pos=43093464, ref="A", alt="T", gene="BRCA1")
    ev = [
        _evidence(source=EvidenceSource.VEP, consequence="stop_gained", in_last_exon=True),
    ]
    pvs1 = {c.code: c for c in score_criteria(v, ev)}["PVS1"]
    assert pvs1.met is True
    assert pvs1.strength == CriterionStrength.STRONG


def test_pipeline_flags_stale_clinvar():
    """The headline behaviour: a stale ClinVar record is flagged for re-review."""
    provider = FixtureEvidenceProvider()
    # BRCA1 fixture has ClinVar updated 2026-01-15; with utcnow() retrieval this is
    # < 1yr, so to test staleness we use BRCA2 (2024-03-10) which is > 1yr stale.
    request = ReviewRequest(
        variant=Variant(
            genome="GRCh38", chrom="13", pos=32340301, ref="T", alt="C", gene="BRCA2"
        ),
        proposed_classification=ACMGClassification.VUS,
    )
    dossier = review_variant(request, evidence_provider=provider, llm_provider="none")
    types = {c.type for c in dossier.conflicts}
    assert ConflictType.STALE_EVIDENCE in types


def test_pipeline_disagrees_on_overcalled_common_variant():
    provider = FixtureEvidenceProvider()
    request = ReviewRequest(
        variant=Variant(
            genome="GRCh38", chrom="13", pos=32340301, ref="T", alt="C", gene="BRCA2"
        ),
        proposed_classification=ACMGClassification.LIKELY_PATHOGENIC,
    )
    dossier = review_variant(request, evidence_provider=provider, llm_provider="none")
    assert dossier.independent_classification == ACMGClassification.BENIGN
    assert dossier.has_major_conflict


def test_provenance_hash_is_deterministic():
    provider = FixtureEvidenceProvider()
    request = ReviewRequest(
        variant=Variant(
            genome="GRCh38", chrom="17", pos=43093464, ref="A", alt="T", gene="BRCA1"
        ),
        proposed_classification=ACMGClassification.VUS,
    )
    d1 = review_variant(request, evidence_provider=provider, llm_provider="none")
    d2 = review_variant(request, evidence_provider=provider, llm_provider="none")
    assert d1.provenance_hash == d2.provenance_hash
