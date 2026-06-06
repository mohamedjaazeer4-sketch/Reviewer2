"""Tests for the deterministic ACMG combining rules.

These pin the published ACMG 2015 Table 5 combinations so the engine can't silently
drift. If you change a threshold or rule, a test must change with it — that's the point.
"""

from __future__ import annotations

from reviewer2.acmg.rules import (
    classify,
    crosses_clinical_actionability,
    disagreement_score,
)
from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    CriterionDirection,
    CriterionStrength,
    EvidenceItem,
    EvidenceSource,
)


def _ev() -> EvidenceItem:
    return EvidenceItem(
        source=EvidenceSource.INTERNAL,
        summary="test",
        source_quote="test evidence",
    )


def _crit(code, direction, strength, met=True) -> ACMGCriterion:
    return ACMGCriterion(
        code=code,
        direction=direction,
        strength=strength,
        met=met,
        rationale="test",
        evidence=[_ev()] if met else [],
    )


P = CriterionDirection.PATHOGENIC
B = CriterionDirection.BENIGN
VS = CriterionStrength.VERY_STRONG
ST = CriterionStrength.STRONG
MO = CriterionStrength.MODERATE
SU = CriterionStrength.SUPPORTING
SA = CriterionStrength.STANDALONE


def test_pvs1_plus_strong_is_pathogenic():
    crits = [_crit("PVS1", P, VS), _crit("PS1", P, ST)]
    assert classify(crits) == ACMGClassification.PATHOGENIC


def test_two_strong_is_pathogenic():
    crits = [_crit("PS1", P, ST), _crit("PS2", P, ST)]
    assert classify(crits) == ACMGClassification.PATHOGENIC


def test_pvs1_plus_moderate_is_likely_pathogenic():
    crits = [_crit("PVS1", P, VS), _crit("PM2", P, MO)]
    assert classify(crits) == ACMGClassification.LIKELY_PATHOGENIC


def test_three_moderate_is_likely_pathogenic():
    crits = [_crit("PM1", P, MO), _crit("PM2", P, MO), _crit("PM5", P, MO)]
    assert classify(crits) == ACMGClassification.LIKELY_PATHOGENIC


def test_ba1_is_benign():
    crits = [_crit("BA1", B, SA)]
    assert classify(crits) == ACMGClassification.BENIGN


def test_two_benign_strong_is_benign():
    crits = [_crit("BS1", B, ST), _crit("BS2", B, ST)]
    assert classify(crits) == ACMGClassification.BENIGN


def test_benign_strong_plus_supporting_is_likely_benign():
    crits = [_crit("BS1", B, ST), _crit("BP4", B, SU)]
    assert classify(crits) == ACMGClassification.LIKELY_BENIGN


def test_no_criteria_is_vus():
    assert classify([]) == ACMGClassification.VUS


def test_contradictory_evidence_is_vus():
    # Pathogenic-side and benign-side both fire -> uncertain.
    crits = [_crit("PVS1", P, VS), _crit("PM2", P, MO), _crit("BA1", B, SA)]
    assert classify(crits) == ACMGClassification.VUS


def test_disagreement_score_endpoints():
    assert disagreement_score(
        ACMGClassification.BENIGN, ACMGClassification.PATHOGENIC
    ) == 1.0
    assert disagreement_score(
        ACMGClassification.VUS, ACMGClassification.VUS
    ) == 0.0


def test_crosses_actionability():
    assert crosses_clinical_actionability(
        ACMGClassification.PATHOGENIC, ACMGClassification.BENIGN
    )
    assert not crosses_clinical_actionability(
        ACMGClassification.PATHOGENIC, ACMGClassification.LIKELY_PATHOGENIC
    )
    # VUS is neutral, never crosses.
    assert not crosses_clinical_actionability(
        ACMGClassification.VUS, ACMGClassification.PATHOGENIC
    )
