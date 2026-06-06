"""Deterministic ACMG/AMP combining rules (Richards et al., 2015).

This module is intentionally **LLM-free and pure**: given a set of fired criteria,
it returns a classification using the published combining rules. That makes the
core of Reviewer2 reproducible and auditable — an interviewer can read this file
and check it against the ACMG paper line by line.

We implement the germline rules only (v1 scope). Somatic (AMP/ASCO/CAP tiering) is
explicitly out of scope and lives in v2.

Reference: Richards S, et al. "Standards and guidelines for the interpretation of
sequence variants." Genet Med. 2015;17(5):405-424. Table 5 combining criteria.
"""

from __future__ import annotations

from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    CriterionDirection,
    CriterionStrength,
)

ENGINE_VERSION = "acmg-2015-rules/0.1.0"


def _counts(criteria: list[ACMGCriterion]) -> dict[str, int]:
    """Tally fired criteria by direction+strength into the buckets the rules use."""
    buckets = {
        "PVS": 0,  # pathogenic very strong
        "PS": 0,   # pathogenic strong
        "PM": 0,   # pathogenic moderate
        "PP": 0,   # pathogenic supporting
        "BA": 0,   # benign standalone
        "BS": 0,   # benign strong
        "BP": 0,   # benign supporting
    }
    for c in criteria:
        if not c.met:
            continue
        if c.direction is CriterionDirection.PATHOGENIC:
            if c.strength is CriterionStrength.VERY_STRONG:
                buckets["PVS"] += 1
            elif c.strength is CriterionStrength.STRONG:
                buckets["PS"] += 1
            elif c.strength is CriterionStrength.MODERATE:
                buckets["PM"] += 1
            elif c.strength is CriterionStrength.SUPPORTING:
                buckets["PP"] += 1
        else:  # benign
            if c.strength is CriterionStrength.STANDALONE:
                buckets["BA"] += 1
            elif c.strength is CriterionStrength.STRONG:
                buckets["BS"] += 1
            elif c.strength is CriterionStrength.SUPPORTING:
                buckets["BP"] += 1
    return buckets


def _is_pathogenic(b: dict[str, int]) -> bool:
    """ACMG 2015 Table 5 — Pathogenic combining rules."""
    pvs, ps, pm, pp = b["PVS"], b["PS"], b["PM"], b["PP"]
    return (
        (pvs >= 1 and (ps >= 1 or pm >= 2 or (pm == 1 and pp == 1) or pp >= 2))
        or (ps >= 2)
        or (ps == 1 and (pm >= 3 or (pm == 2 and pp >= 2) or (pm == 1 and pp >= 4)))
    )


def _is_likely_pathogenic(b: dict[str, int]) -> bool:
    """ACMG 2015 Table 5 — Likely pathogenic combining rules."""
    pvs, ps, pm, pp = b["PVS"], b["PS"], b["PM"], b["PP"]
    return (
        (pvs == 1 and pm == 1)
        or (ps == 1 and (pm == 1 or pm == 2))
        or (ps == 1 and pp >= 2)
        or (pm >= 3)
        or (pm == 2 and pp >= 2)
        or (pm == 1 and pp >= 4)
    )


def _is_benign(b: dict[str, int]) -> bool:
    """ACMG 2015 — Benign combining rules."""
    return b["BA"] >= 1 or b["BS"] >= 2


def _is_likely_benign(b: dict[str, int]) -> bool:
    """ACMG 2015 — Likely benign combining rules."""
    return (b["BS"] == 1 and b["BP"] == 1) or (b["BP"] >= 2)


def classify(criteria: list[ACMGCriterion]) -> ACMGClassification:
    """Combine fired criteria into a 5-tier ACMG classification.

    Handling of contradictory evidence follows the guideline's intent: if both
    pathogenic and benign rules fire, the result is Uncertain significance (the
    criteria are in conflict and a human must adjudicate).
    """
    b = _counts(criteria)

    path = _is_pathogenic(b)
    likely_path = _is_likely_pathogenic(b)
    benign = _is_benign(b)
    likely_benign = _is_likely_benign(b)

    pathogenic_side = path or likely_path
    benign_side = benign or likely_benign

    # Rule (ii): contradictory criteria -> VUS.
    if pathogenic_side and benign_side:
        return ACMGClassification.VUS

    if path:
        return ACMGClassification.PATHOGENIC
    if likely_path:
        return ACMGClassification.LIKELY_PATHOGENIC
    if benign:
        return ACMGClassification.BENIGN
    if likely_benign:
        return ACMGClassification.LIKELY_BENIGN

    return ACMGClassification.VUS


# Ordinal scale used for measuring disagreement between two classifications.
_ORDINAL: dict[ACMGClassification, int] = {
    ACMGClassification.BENIGN: 0,
    ACMGClassification.LIKELY_BENIGN: 1,
    ACMGClassification.VUS: 2,
    ACMGClassification.LIKELY_PATHOGENIC: 3,
    ACMGClassification.PATHOGENIC: 4,
}


def disagreement_score(
    a: ACMGClassification, b: ACMGClassification
) -> float:
    """Normalised distance (0..1) between two classifications on the 5-tier scale.

    A benign-vs-pathogenic flip is the maximum (1.0); adjacent tiers are small.
    """
    return abs(_ORDINAL[a] - _ORDINAL[b]) / 4.0


def crosses_clinical_actionability(
    a: ACMGClassification, b: ACMGClassification
) -> bool:
    """True if the two calls fall on opposite sides of the VUS line.

    Pathogenic-side (P/LP) vs benign-side (B/LB) disagreements are the ones that
    change clinical action, so the second reviewer escalates these.
    """
    def side(c: ACMGClassification) -> int:
        if _ORDINAL[c] > 2:
            return 1   # pathogenic side
        if _ORDINAL[c] < 2:
            return -1  # benign side
        return 0       # VUS

    sa, sb = side(a), side(b)
    return sa != 0 and sb != 0 and sa != sb


# The three clinical *action bands*. Within a band, the management decision is the
# same, so a tier difference (Pathogenic vs Likely pathogenic, Benign vs Likely
# benign) does not, on its own, warrant interrupting a human reviewer.
_ACTION_BAND: dict[ACMGClassification, int] = {
    ACMGClassification.BENIGN: 0,          # do not act
    ACMGClassification.LIKELY_BENIGN: 0,   # do not act
    ACMGClassification.VUS: 1,             # uncertain — monitor, do not act
    ACMGClassification.LIKELY_PATHOGENIC: 2,  # act
    ACMGClassification.PATHOGENIC: 2,         # act
}


def materially_disagree(
    a: ACMGClassification, b: ACMGClassification
) -> bool:
    """True if two calls fall in different clinical action bands.

    Reviewer2 only escalates a *material* disagreement — one that changes what a
    clinician would do (act / monitor / do-not-act). A within-band difference such
    as Pathogenic vs Likely pathogenic is surfaced in the dossier but is not, by
    itself, a review-blocking conflict. This keeps the second reviewer from crying
    wolf on calls that are clinically equivalent.
    """
    return _ACTION_BAND[a] != _ACTION_BAND[b]
