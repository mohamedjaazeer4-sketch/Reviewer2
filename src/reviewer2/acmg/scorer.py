"""Map structured evidence to fired ACMG/AMP criteria (germline, v1).

Scope honesty (this matters in interviews): a full ACMG implementation has 28
criteria, many requiring segregation data, functional assays, or expert curation
that no public API provides. v1 implements the subset that can be **defensibly and
deterministically** derived from gnomAD population data, ClinVar assertions, and
in-silico predictors:

    PVS1  (supporting strength here)  null variant in a LoF-intolerant gene
    PS1                               same amino-acid change as known pathogenic
    PM2   (supporting strength)       absent / ultra-rare in gnomAD
    PP3 / BP4                          in-silico predictors agree path / benign
    BA1                               allele frequency > 5% (stand-alone benign)
    BS1                               allele frequency higher than disease expectation

Deliberately NOT implemented in v1 (would require data we don't have): PS3/BS3
(functional), PM3/PP1/BS4 (segregation), PM6/PS2 (de novo), PP4 (phenotype).
We follow ClinGen SVI guidance to *down-weight* PVS1 to Supporting when we cannot
confirm the canonical-transcript/exon context from public data alone — i.e. we err
toward caution rather than over-calling pathogenic.

Each fired criterion is constructed with its supporting EvidenceItem(s); the model
validator in :mod:`reviewer2.models` guarantees we never fire a criterion without one.
"""

from __future__ import annotations

from reviewer2.models import (
    ACMGCriterion,
    CriterionDirection,
    CriterionStrength,
    EvidenceItem,
    EvidenceSource,
    Variant,
)

# Thresholds (documented so they can be challenged / tuned).
BA1_AF = 0.05          # >5% -> stand-alone benign (ACMG BA1)
BS1_AF = 0.01          # >1% -> benign strong (disease-dependent; conservative default)
PM2_AF = 1e-4          # <0.01% (and not absent==0 special-cased) -> rare
INSILICO_PATH = 0.7    # ensemble score above -> predicts damaging (PP3)
INSILICO_BENIGN = 0.3  # ensemble score below -> predicts tolerated (BP4)

# Genes where loss-of-function is an established disease mechanism. v1 keeps a
# small, explicit allow-list rather than pretending to know all LoF genes; this is
# honest and easy for a reviewer to extend. (Subset of ClinGen haploinsufficient.)
LOF_INTOLERANT_GENES = {
    "BRCA1", "BRCA2", "TP53", "PTEN", "MLH1", "MSH2", "MSH6", "PMS2",
    "APC", "RB1", "NF1", "VHL", "STK11", "CDH1", "PALB2",
}

NULL_CONSEQUENCES = {
    "frameshift", "stop_gained", "nonsense", "splice_donor",
    "splice_acceptor", "start_lost",
}


def _af(evidence: list[EvidenceItem]) -> tuple[float | None, EvidenceItem | None]:
    """Pull the gnomAD popmax/global allele frequency from evidence, if present."""
    for ev in evidence:
        if ev.source is EvidenceSource.GNOMAD and "allele_frequency" in ev.data:
            val = ev.data["allele_frequency"]
            if isinstance(val, (int, float)):
                return float(val), ev
    return None, None


def _insilico(evidence: list[EvidenceItem]) -> tuple[float | None, EvidenceItem | None]:
    for ev in evidence:
        if ev.source is EvidenceSource.COMPUTATIONAL and "ensemble_score" in ev.data:
            val = ev.data["ensemble_score"]
            if isinstance(val, (int, float)):
                return float(val), ev
    return None, None


def _clinvar(evidence: list[EvidenceItem]) -> EvidenceItem | None:
    for ev in evidence:
        if ev.source is EvidenceSource.CLINVAR:
            return ev
    return None


def _consequence(evidence: list[EvidenceItem]) -> tuple[str | None, EvidenceItem | None]:
    for ev in evidence:
        if ev.source is EvidenceSource.VEP and "consequence" in ev.data:
            val = ev.data["consequence"]
            if isinstance(val, str):
                return val, ev
    return None, None


def score_criteria(variant: Variant, evidence: list[EvidenceItem]) -> list[ACMGCriterion]:
    """Return every ACMG criterion we evaluated, with met=True/False + rationale.

    We return *non-fired* criteria too (met=False, no evidence required) so the
    dossier shows what was considered, not just what fired — important for trust.
    """
    criteria: list[ACMGCriterion] = []

    af, af_ev = _af(evidence)
    score, score_ev = _insilico(evidence)
    consequence, cons_ev = _consequence(evidence)
    clinvar_ev = _clinvar(evidence)

    # ---- PVS1: null variant in a LoF-intolerant gene (down-weighted to Supporting) ----
    pvs1_met = bool(
        consequence
        and any(nc in consequence for nc in NULL_CONSEQUENCES)
        and variant.gene in LOF_INTOLERANT_GENES
    )
    criteria.append(
        ACMGCriterion(
            code="PVS1",
            direction=CriterionDirection.PATHOGENIC,
            # ClinGen SVI: without confirmed transcript/exon context, cap strength.
            strength=CriterionStrength.SUPPORTING,
            met=pvs1_met,
            rationale=(
                f"{consequence} in LoF-intolerant gene {variant.gene}; strength capped at "
                "Supporting per ClinGen SVI without confirmed transcript context."
                if pvs1_met
                else "Not a qualifying null variant in a known LoF-intolerant gene."
            ),
            evidence=[cons_ev] if (pvs1_met and cons_ev) else [],
        )
    )

    # ---- PS1: same amino-acid change as an established pathogenic variant ----
    ps1_met = bool(
        clinvar_ev
        and clinvar_ev.data.get("same_aa_change_pathogenic") is True
    )
    criteria.append(
        ACMGCriterion(
            code="PS1",
            direction=CriterionDirection.PATHOGENIC,
            strength=CriterionStrength.STRONG,
            met=ps1_met,
            rationale=(
                "Same amino-acid change as a previously established pathogenic variant."
                if ps1_met
                else "No matching established pathogenic amino-acid change found."
            ),
            evidence=[clinvar_ev] if (ps1_met and clinvar_ev) else [],
        )
    )

    # ---- PM2 (Supporting): absent or ultra-rare in gnomAD ----
    pm2_met = af is not None and af < PM2_AF
    criteria.append(
        ACMGCriterion(
            code="PM2",
            direction=CriterionDirection.PATHOGENIC,
            strength=CriterionStrength.SUPPORTING,  # ClinGen SVI down-weights PM2
            met=pm2_met,
            rationale=(
                f"Allele frequency {af:.2e} is below the rare threshold {PM2_AF:.0e}."
                if pm2_met
                else (
                    f"Allele frequency {af:.2e} is not rare enough for PM2."
                    if af is not None
                    else "No gnomAD frequency available; PM2 not assessed."
                )
            ),
            evidence=[af_ev] if (pm2_met and af_ev) else [],
        )
    )

    # ---- PP3 / BP4: in-silico predictors ----
    pp3_met = score is not None and score >= INSILICO_PATH
    criteria.append(
        ACMGCriterion(
            code="PP3",
            direction=CriterionDirection.PATHOGENIC,
            strength=CriterionStrength.SUPPORTING,
            met=pp3_met,
            rationale=(
                f"Ensemble in-silico score {score:.2f} ≥ {INSILICO_PATH} (predicts damaging)."
                if pp3_met
                else "In-silico predictors do not support a damaging effect."
            ),
            evidence=[score_ev] if (pp3_met and score_ev) else [],
        )
    )
    bp4_met = score is not None and score <= INSILICO_BENIGN
    criteria.append(
        ACMGCriterion(
            code="BP4",
            direction=CriterionDirection.BENIGN,
            strength=CriterionStrength.SUPPORTING,
            met=bp4_met,
            rationale=(
                f"Ensemble in-silico score {score:.2f} ≤ {INSILICO_BENIGN} (predicts tolerated)."
                if bp4_met
                else "In-silico predictors do not support a benign effect."
            ),
            evidence=[score_ev] if (bp4_met and score_ev) else [],
        )
    )

    # ---- BA1: allele frequency > 5% (stand-alone benign) ----
    ba1_met = af is not None and af > BA1_AF
    criteria.append(
        ACMGCriterion(
            code="BA1",
            direction=CriterionDirection.BENIGN,
            strength=CriterionStrength.STANDALONE,
            met=ba1_met,
            rationale=(
                f"Allele frequency {af:.2%} exceeds 5% (BA1 stand-alone benign)."
                if ba1_met
                else "Allele frequency does not exceed the 5% BA1 threshold."
            ),
            evidence=[af_ev] if (ba1_met and af_ev) else [],
        )
    )

    # ---- BS1: allele frequency greater than disease prevalence expectation ----
    bs1_met = af is not None and BS1_AF < af <= BA1_AF
    criteria.append(
        ACMGCriterion(
            code="BS1",
            direction=CriterionDirection.BENIGN,
            strength=CriterionStrength.STRONG,
            met=bs1_met,
            rationale=(
                f"Allele frequency {af:.2%} is greater than expected for the disorder."
                if bs1_met
                else "Allele frequency not high enough for BS1."
            ),
            evidence=[af_ev] if (bs1_met and af_ev) else [],
        )
    )

    return criteria
