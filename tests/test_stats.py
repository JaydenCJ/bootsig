"""Unit tests for the statistical primitives in ``bootsig.stats``.

These are the numbers everything else trusts, so they are checked against
hand-computed and independently published values, not against the code.
"""

from __future__ import annotations

import math

import pytest

from bootsig.stats import (
    binom_test_two_sided_half,
    cohens_d_paired,
    cohens_d_unpaired,
    describe,
    is_binary,
    normal_cdf,
    normal_quantile,
    quantile,
    sample_sd,
)


def test_sample_sd_matches_hand_computed_value_and_degenerates_to_zero():
    # values 2,4,4,4,5,5,7,9: mean 5, sum of squared deviations 32, n-1 = 7.
    assert sample_sd([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(math.sqrt(32 / 7))
    assert sample_sd([3.0]) == 0.0
    assert sample_sd([2.0, 2.0, 2.0]) == 0.0


def test_quantile_type7_interpolation_matches_numpy_convention():
    # numpy.quantile([1,2,3,4], .25) == 1.75 and .5 == 2.5 under type 7.
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert quantile([1.0, 5.0, 9.0], 0.0) == 1.0
    assert quantile([1.0, 5.0, 9.0], 1.0) == 9.0


def test_quantile_rejects_bad_inputs():
    with pytest.raises(ValueError):
        quantile([1.0, 2.0], 1.5)
    with pytest.raises(ValueError):
        quantile([], 0.5)


def test_normal_quantile_and_cdf_round_trip_including_the_familiar_196():
    for p in (0.025, 0.2, 0.5, 0.8, 0.975):
        assert normal_cdf(normal_quantile(p)) == pytest.approx(p, abs=1e-12)
    assert normal_quantile(0.975) == pytest.approx(1.959964, abs=1e-5)
    with pytest.raises(ValueError):
        normal_quantile(0.0)


def test_binom_test_exact_small_cases():
    # Exact two-sided (minlike) value: 112/1024 = 0.109375, matching
    # scipy.stats.binomtest(2, 10, 0.5).pvalue.
    assert binom_test_two_sided_half(2, 10) == pytest.approx(0.109375, abs=1e-12)
    # Symmetry, the balanced case, the most extreme case, and n = 0.
    assert binom_test_two_sided_half(3, 19) == pytest.approx(binom_test_two_sided_half(16, 19))
    assert binom_test_two_sided_half(5, 10) == pytest.approx(1.0)
    assert binom_test_two_sided_half(0, 8) == pytest.approx(2 * 0.5 ** 8, abs=1e-12)
    assert binom_test_two_sided_half(0, 0) == 1.0


def test_binom_test_large_n_stays_finite_and_small():
    p = binom_test_two_sided_half(400, 1000)
    assert 0.0 < p < 1e-9


def test_describe_distinguishes_binary_from_continuous():
    binary = describe([0.0, 1.0, 1.0, 0.0])
    assert binary["binary"] is True
    assert binary["mean"] == pytest.approx(0.5)

    continuous = describe([0.1, 0.2, 0.3, 0.4, 0.5])
    assert continuous["binary"] is False
    assert continuous["p25"] == pytest.approx(0.2)
    assert continuous["median"] == pytest.approx(0.3)
    assert continuous["p75"] == pytest.approx(0.4)

    assert is_binary([0.0, 1.0, 1.0])
    assert not is_binary([0.0, 0.5, 1.0])


def test_cohens_d_paired_hand_value_and_zero_sd_guard():
    assert cohens_d_paired([1.0, 2.0, 3.0]) == pytest.approx(2.0)  # mean 2, sd 1
    assert cohens_d_paired([0.5, 0.5, 0.5]) is None


def test_cohens_d_unpaired_uses_pooled_sd():
    a = [0.0, 2.0]  # mean 1, var 2
    b = [3.0, 5.0]  # mean 4, var 2
    assert cohens_d_unpaired(a, b) == pytest.approx(3.0 / math.sqrt(2.0))
