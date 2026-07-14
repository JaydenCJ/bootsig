"""Tests for the end-to-end comparison pipeline (`compare_files`).

Small resample counts keep these fast; determinism comes from fixed seeds.
"""

from __future__ import annotations

import pytest

from bootsig.compare import compare_files
from bootsig.errors import DataError, UsageError
from bootsig.report import comparison_to_dict


def test_paired_design_detected_from_ids(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 1, 0, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 1, 0, 1])
    cmp = compare_files(a, b, resamples=200)
    assert cmp.design == "paired"
    assert cmp.pairs == 6
    assert cmp.matched_on == 'id key "id"'


def test_obvious_improvement_is_significant(scores_run):
    a = scores_run("a.jsonl", [0] * 30)
    b = scores_run("b.jsonl", [1] * 30)
    cmp = compare_files(a, b, resamples=2000)
    assert cmp.significant is True
    assert cmp.direction == "improvement"
    assert cmp.diff_mean == pytest.approx(1.0)


def test_tiny_churn_is_not_significant(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
    b = scores_run("b.jsonl", [0, 1, 1, 0, 1, 0, 1, 0, 1, 0])  # one win, one loss
    cmp = compare_files(a, b, resamples=2000)
    assert cmp.significant is False
    assert cmp.diff_mean == pytest.approx(0.0)
    assert cmp.direction == "no change"


def test_mcnemar_only_for_binary_paired_metric_with_correct_counts(scores_run):
    a_bin = scores_run("a.jsonl", [1, 1, 0, 0, 1])
    b_bin = scores_run("b.jsonl", [0, 1, 1, 1, 1])
    cmp = compare_files(a_bin, b_bin, resamples=200)
    assert cmp.mcnemar is not None
    assert cmp.mcnemar.n01 == 1  # A right, B wrong
    assert cmp.mcnemar.n10 == 2  # A wrong, B right

    a_flt = scores_run("a2.jsonl", [0.4, 0.6, 0.8, 0.2])
    b_flt = scores_run("b2.jsonl", [0.5, 0.7, 0.6, 0.3])
    assert compare_files(a_flt, b_flt, resamples=200).mcnemar is None


def test_wins_losses_ties_add_up_and_relative_change(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1])
    b = scores_run("b.jsonl", [0, 1, 1, 1, 1])
    cmp = compare_files(a, b, resamples=200)
    assert (cmp.wins, cmp.losses, cmp.ties) == (2, 1, 2)
    assert cmp.wins + cmp.losses + cmp.ties == cmp.pairs
    assert cmp.relative == pytest.approx(cmp.diff_mean / 0.6)  # baseline mean 0.6


def test_lower_is_better_flips_direction(scores_run):
    a = scores_run("a.jsonl", [100, 110, 105, 95, 100, 108])
    b = scores_run("b.jsonl", [140, 150, 145, 135, 150, 148])  # latency regressed
    default = compare_files(a, b, resamples=500)
    flipped = compare_files(a, b, resamples=500, lower_is_better=True)
    assert default.direction == "improvement"
    assert flipped.direction == "regression"


def test_unpaired_flag_skips_pairing_entirely(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1], id_prefix="left")
    b = scores_run("b.jsonl", [1, 1, 1, 0], id_prefix="right")  # disjoint ids, unequal n
    cmp = compare_files(a, b, unpaired=True, resamples=500)
    assert cmp.design == "unpaired"
    assert cmp.pairs is None and cmp.wins is None and cmp.mcnemar is None
    assert cmp.a.n == 3 and cmp.b.n == 4


def test_metric_key_from_a_is_enforced_on_b(write_run):
    a = write_run("a.jsonl", [{"id": "x", "score": 1}, {"id": "y", "score": 0}])
    b = write_run("b.jsonl", [{"id": "x", "accuracy": 1}, {"id": "y", "accuracy": 0}])
    with pytest.raises(DataError, match=r'b\.jsonl:1: metric "score" is missing'):
        compare_files(a, b, resamples=100)


def test_comparison_is_fully_deterministic(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 1, 0, 1, 0, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 1, 0, 0, 0, 1])
    d1 = comparison_to_dict(compare_files(a, b, resamples=500, seed=9), "0.1.0")
    d2 = comparison_to_dict(compare_files(a, b, resamples=500, seed=9), "0.1.0")
    assert d1 == d2


def test_degenerate_inputs_are_rejected_up_front(scores_run):
    a = scores_run("a.jsonl", [1])
    b = scores_run("b.jsonl", [0])
    with pytest.raises(DataError, match="at least 2"):
        compare_files(a, b, resamples=100)
    with pytest.raises(UsageError, match="alpha"):
        compare_files(a, b, alpha=2.0)  # validated before any file I/O
