"""Tests for the permutation tests, including exact-enumeration hand cases.

The exact cases are small enough to verify with pencil and paper, which is
the whole point: when bootsig says "exact", the p-value has a closed-form
answer these tests pin down.
"""

from __future__ import annotations

import random

import pytest

from bootsig.errors import UsageError
from bootsig.permutation import (
    EXACT_CAP,
    paired_permutation_test,
    unpaired_permutation_test,
)


# ---------- paired (sign-flip) ----------


def test_paired_exact_hand_case_one_two_three():
    # diffs [1,2,3]: 8 sign assignments, |sum| >= 6 only for +++ and ---,
    # so the exact two-sided p-value is 2/8 = 0.25.
    result = paired_permutation_test([1.0, 2.0, 3.0], resamples=10000)
    assert result.exact is True
    assert result.resamples == 8
    assert result.p_value == pytest.approx(0.25)
    assert result.observed_diff == pytest.approx(2.0)  # the mean difference


def test_paired_exact_counts_mirrored_ties():
    # diffs [1,1]: sums are 2, 0, 0, -2; |sum| >= 2 for two of four -> 0.5.
    result = paired_permutation_test([1.0, 1.0], resamples=10000)
    assert result.exact is True
    assert result.p_value == pytest.approx(0.5)


def test_paired_zero_diffs_are_neutral():
    # All ties: the runs are literally identical -> p = 1.0, exact.
    all_zero = paired_permutation_test([0.0, 0.0, 0.0], resamples=100)
    assert all_zero.p_value == 1.0
    assert all_zero.exact is True
    assert all_zero.observed_diff == 0.0
    # Zeros are dropped from flipping; the p-value must be unchanged.
    with_zeros = paired_permutation_test([1.0, 2.0, 3.0, 0.0, 0.0], resamples=10000)
    without = paired_permutation_test([1.0, 2.0, 3.0], resamples=10000)
    assert with_zeros.p_value == pytest.approx(without.p_value)


def test_exact_enumeration_thresholds():
    diffs = [float(i) for i in range(1, 11)]  # 2^10 = 1024 assignments
    exact = paired_permutation_test(diffs, resamples=1024)
    monte = paired_permutation_test(diffs, resamples=1023)
    assert exact.exact is True and exact.resamples == 1024
    assert monte.exact is False and monte.resamples == 1023
    # 2^25 would fit the requested resamples but exceeds the hard ceiling.
    wide = [float(i % 7 + 1) for i in range(25)]
    capped = paired_permutation_test(wide, resamples=EXACT_CAP + 1, seed=42)
    assert capped.exact is False
    assert capped.resamples == EXACT_CAP + 1


def test_paired_monte_carlo_p_value_is_never_zero():
    # 30 identical positive diffs: overwhelming evidence, but the add-one
    # correction still bounds p at 1/(B+1) instead of an impossible 0.
    result = paired_permutation_test([1.0] * 30, resamples=999, seed=42)
    assert result.exact is False
    assert result.p_value == pytest.approx(1.0 / 1000.0)


def test_paired_monte_carlo_is_seed_deterministic():
    rng = random.Random(11)
    diffs = [rng.gauss(0.02, 0.3) for _ in range(60)]
    a = paired_permutation_test(diffs, resamples=2000, seed=7)
    b = paired_permutation_test(diffs, resamples=2000, seed=7)
    c = paired_permutation_test(diffs, resamples=2000, seed=8)
    assert a.p_value == b.p_value
    assert a.p_value != c.p_value


def test_paired_symmetric_noise_is_not_significant():
    # Antisymmetric diffs: every +d has a matching -d, mean is exactly 0.
    diffs = [0.1, -0.1, 0.25, -0.25, 0.4, -0.4, 0.05, -0.05]
    result = paired_permutation_test(diffs, resamples=10000, seed=42)
    assert result.p_value > 0.5


# ---------- unpaired (shuffle) ----------


def test_unpaired_exact_hand_cases():
    # A=[1,2], B=[3,4]: 6 partitions; |mean diff| >= 2 for exactly two of
    # them ({1,2}|{3,4} and {3,4}|{1,2}), so p = 2/6 = 1/3.
    result = unpaired_permutation_test([1.0, 2.0], [3.0, 4.0], resamples=10000)
    assert result.exact is True
    assert result.resamples == 6
    assert result.p_value == pytest.approx(1.0 / 3.0)
    assert result.observed_diff == pytest.approx(2.0)

    # Identical groups: every partition is at least as extreme -> p = 1.
    same = unpaired_permutation_test([1.0, 2.0], [1.0, 2.0], resamples=10000)
    assert same.exact is True and same.p_value == pytest.approx(1.0)

    # Unequal sizes: pool [1,2,3,10], C(4,3)=4 partitions, only the original
    # reaches |diff| = 8 -> p = 1/4.
    uneven = unpaired_permutation_test([1.0, 2.0, 3.0], [10.0], resamples=10000)
    assert uneven.exact is True and uneven.p_value == pytest.approx(0.25)


def test_unpaired_monte_carlo_properties():
    a = [0.0] * 12
    b = [1.0] * 12  # C(24,12) = 2704156 >> resamples -> Monte Carlo
    r1 = unpaired_permutation_test(a, b, resamples=999, seed=5)
    r2 = unpaired_permutation_test(a, b, resamples=999, seed=5)
    assert r1.exact is False
    assert r1.p_value == pytest.approx(1.0 / 1000.0)  # never zero
    assert r1.p_value == r2.p_value  # seed-deterministic

    rng = random.Random(21)
    near = [rng.gauss(0.3, 0.05) for _ in range(30)]
    far = [rng.gauss(0.9, 0.05) for _ in range(30)]
    assert unpaired_permutation_test(near, far, resamples=4000, seed=42).p_value < 0.001


def test_empty_inputs_are_usage_errors():
    with pytest.raises(UsageError, match="at least one"):
        paired_permutation_test([])
    with pytest.raises(UsageError, match="both runs"):
        unpaired_permutation_test([], [1.0])
