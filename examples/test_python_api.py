"""Runnable example: the Python API on the committed example runs.

This file is collected by ``pytest`` from the repository root, so the
example is guaranteed to keep working. Copy this shape into your own
suite to gate merges on eval significance without shelling out.
"""

from __future__ import annotations

from pathlib import Path

import bootsig

EXAMPLES = Path(__file__).resolve().parent


def test_prompt_tweak_that_looks_better_is_actually_noise():
    cmp = bootsig.compare_files(
        str(EXAMPLES / "baseline.jsonl"),
        str(EXAMPLES / "candidate.jsonl"),
    )
    # 73% beat 71% — and it means nothing.
    assert cmp.a.mean == 0.71
    assert cmp.b.mean == 0.73
    assert cmp.significant is False
    assert cmp.permutation.p_value > 0.5


def test_real_improvement_is_flagged_significant():
    cmp = bootsig.compare_files(
        str(EXAMPLES / "baseline.jsonl"),
        str(EXAMPLES / "improved.jsonl"),
    )
    assert cmp.significant is True
    assert cmp.direction == "improvement"
    assert cmp.diff_ci.lo > 0  # even the CI's low end is a gain


def test_this_eval_cannot_see_small_differences():
    from statistics import stdev

    paired = bootsig.pair_runs(
        bootsig.load_run(str(EXAMPLES / "baseline.jsonl")),
        bootsig.load_run(str(EXAMPLES / "candidate.jsonl")),
    )
    detectable = bootsig.mde(stdev(paired.diffs), paired.n)
    # A 100-example eval with this much churn cannot detect ~2pt differences.
    assert detectable > 0.10
