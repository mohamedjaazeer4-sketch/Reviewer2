"""Conflict detection — the core "second reviewer" judgements.

Given Reviewer2's independent classification plus the raw evidence, surface the
specific, human-actionable disagreements. These are the outputs that make the tool
worth a clinician's attention:

* **Classification disagreement** — our call vs the proposed call, with severity
  escalated when it crosses the clinical-actionability line (P/LP vs B/LB).
* **ClinVar submitter conflict** — ClinVar itself reports conflicting interpretations.
* **Stale evidence** — the ClinVar record was updated after the proposed call was made
  (the "reclassified months ago but still reported as VUS" failure mode).
* **Missing evidence** — we could not assess key criteria; flagged so nobody mistakes
  silence for benign.
"""

from __future__ import annotations

from reviewer2.acmg.rules import (
    crosses_clinical_actionability,
    disagreement_score,
    materially_disagree,
)
from reviewer2.models import (
    ACMGClassification,
    ConflictFlag,
    ConflictSeverity,
    ConflictType,
    EvidenceItem,
    EvidenceSource,
    ReviewRequest,
)

# A ClinVar record older than this relative to retrieval is "worth re-checking".
STALENESS_THRESHOLD_DAYS = 365


def detect_conflicts(
    request: ReviewRequest,
    independent: ACMGClassification,
    evidence: list[EvidenceItem],
) -> list[ConflictFlag]:
    flags: list[ConflictFlag] = []

    # 1) Disagreement with the proposed classification.
    #
    # We only raise a *review-blocking* CLASSIFICATION_DISAGREEMENT when the two
    # calls land in different clinical action bands (act / uncertain / do-not-act).
    # A within-band tier difference (e.g. Pathogenic vs Likely pathogenic) is real
    # but clinically equivalent, so we record it as INFO rather than interrupting a
    # human — this is what keeps the second reviewer from crying wolf.
    proposed = request.proposed_classification
    if proposed is not None and proposed != independent:
        if materially_disagree(proposed, independent):
            actionable = crosses_clinical_actionability(proposed, independent)
            score = disagreement_score(proposed, independent)
            flags.append(
                ConflictFlag(
                    type=ConflictType.CLASSIFICATION_DISAGREEMENT,
                    severity=(
                        ConflictSeverity.CRITICAL
                        if actionable
                        else (ConflictSeverity.MAJOR if score >= 0.5 else ConflictSeverity.MINOR)
                    ),
                    message=(
                        f"Proposed call '{proposed.value}' disagrees with the independent "
                        f"call '{independent.value}'"
                        + (
                            " and crosses the clinical-actionability line (pathogenic vs "
                            "benign) — escalate for human review."
                            if actionable
                            else " across clinical action bands — escalate for human review."
                        )
                    ),
                )
            )
        else:
            flags.append(
                ConflictFlag(
                    type=ConflictType.CLASSIFICATION_DISAGREEMENT,
                    severity=ConflictSeverity.INFO,
                    message=(
                        f"Proposed call '{proposed.value}' differs from the independent call "
                        f"'{independent.value}', but both fall in the same clinical action "
                        "band, so management is unchanged. Noted for completeness."
                    ),
                )
            )

    # 2) ClinVar submitter conflict + 3) staleness, read off the ClinVar evidence.
    for ev in evidence:
        if ev.source is not EvidenceSource.CLINVAR:
            continue

        if ev.data.get("review_status_conflicting") is True:
            flags.append(
                ConflictFlag(
                    type=ConflictType.CLINVAR_SUBMITTER_CONFLICT,
                    severity=ConflictSeverity.MAJOR,
                    message=(
                        "ClinVar reports conflicting interpretations among submitters; "
                        "the single proposed call may hide genuine disagreement."
                    ),
                    evidence=[ev],
                )
            )

        stale_days = ev.staleness_days()
        if stale_days is not None and stale_days > STALENESS_THRESHOLD_DAYS:
            flags.append(
                ConflictFlag(
                    type=ConflictType.STALE_EVIDENCE,
                    severity=ConflictSeverity.MAJOR,
                    message=(
                        f"ClinVar record was last updated {stale_days} days before retrieval; "
                        "the underlying classification may have changed since the proposed "
                        "call. Re-pull and re-review."
                    ),
                    evidence=[ev],
                )
            )

    # 4) Missing key evidence — don't let absence look like benign.
    have_freq = any(
        e.source is EvidenceSource.GNOMAD and "allele_frequency" in e.data for e in evidence
    )
    if not have_freq:
        flags.append(
            ConflictFlag(
                type=ConflictType.MISSING_EVIDENCE,
                severity=ConflictSeverity.INFO,
                message=(
                    "No gnomAD allele-frequency evidence was available; frequency-based "
                    "criteria (PM2/BA1/BS1) could not be assessed."
                ),
            )
        )

    return flags
