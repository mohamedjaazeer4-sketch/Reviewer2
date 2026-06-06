"""Test that ErrorCatch runs and meets a sane bar (and reports a low false-positive rate)."""

from __future__ import annotations

from eval.errorcatch import run


def test_errorcatch_runs_and_reports():
    result = run()
    assert result["n_injected"] >= 8
    assert result["n_controls"] >= 4
    # The starter set is constructed so Reviewer2 catches the large majority.
    assert result["catch_rate"] >= 0.75
    # And does not cry wolf on correct calls: within-band differences (e.g.
    # Pathogenic vs Likely pathogenic) must NOT be raised as blocking conflicts.
    assert result["false_positive_rate"] == 0.0
