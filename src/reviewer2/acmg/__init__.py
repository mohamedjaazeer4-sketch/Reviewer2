"""Deterministic ACMG/AMP engine (germline, v1).

Two pure modules:

* :mod:`reviewer2.acmg.rules` — the 2015 combining rules (criteria -> classification).
* :mod:`reviewer2.acmg.scorer` — maps structured evidence -> fired criteria.

Neither uses an LLM. This is the auditable core of Reviewer2.
"""

from reviewer2.acmg.rules import (
    ENGINE_VERSION,
    action_band,
    classify,
    crosses_clinical_actionability,
    disagreement_score,
    materially_disagree,
)
from reviewer2.acmg.scorer import score_criteria

__all__ = [
    "classify",
    "score_criteria",
    "disagreement_score",
    "crosses_clinical_actionability",
    "materially_disagree",
    "action_band",
    "ENGINE_VERSION",
]
