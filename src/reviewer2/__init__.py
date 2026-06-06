"""Reviewer2 — an evidence-grounded second-reviewer AI for germline ACMG/AMP
variant classification.

The public surface is intentionally small:

    from reviewer2 import review_variant, ReviewRequest

`review_variant` runs the 4-node LangGraph second-reviewer pipeline and returns a
fully-typed, auditable :class:`ReviewDossier`.
"""

from reviewer2.models import (
    ACMGClassification,
    ACMGCriterion,
    ConflictFlag,
    EvidenceItem,
    ReviewDossier,
    ReviewRequest,
    Variant,
)
from reviewer2.pipeline import review_variant

__all__ = [
    "review_variant",
    "ReviewRequest",
    "ReviewDossier",
    "Variant",
    "EvidenceItem",
    "ACMGCriterion",
    "ACMGClassification",
    "ConflictFlag",
]

__version__ = "0.1.0"
