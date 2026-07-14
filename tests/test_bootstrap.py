"""Tests for bootstrap confidence intervals.

The bootstrap is Monte Carlo, but a fixed seed makes it a pure function —
so these tests assert exact reproducibility, structural properties (width
vs n, width vs confidence), and correct handling of degenerate inputs.
"""

from __future__ import annotations

import random

import pytest

from bootsig.bootstrap import (
    bca_interval,
    bootstrap_mean,
    jackknife_means,
    paired_bootstrap,
    percentile_interval,
    unpaired_bootstrap,
)
from bootsig.errors import UsageError


def _noisy_values(n, seed=1):
    rng = random.Random(seed)
    return [rng.gauss(0.6, 0.15) for _ in range(n)]


def test_seed_fixes_the_interval_exactly():
    values = _noisy_values(40)
    a = bootstrap_mean(values, resamples=500, seed=42)
    b = bootstrap_mean(values, resamples=500, seed=42)
    c = bootstrap_mean(values, resamples=500, seed=43)
    assert (a.lo, a.hi) == (b.lo, b.hi)
    assert (a.lo, a.hi) != (c.lo, c.hi)


def test_interval_brackets_the_sample_mean():
    values = _noisy_values(60)
    ci = bootstrap_mean(values, resamples=1000, seed=42)
    assert ci.lo < ci.estimate < ci.hi


def test_constant_data_collapses_to_a_point_interval():
    ci = bootstrap_mean([0.5] * 20, resamples=200, seed=42)
    assert ci.lo == ci.hi == ci.estimate == 0.5


def test_bca_close_to_percentile_on_symmetric_data():
    values = _noisy_values(80)
    bca = bootstrap_mean(values, resamples=2000, seed=42, method="bca")
    pct = bootstrap_mean(values, resamples=2000, seed=42, method="percentile")
    assert bca.lo == pytest.approx(pct.lo, abs=0.02)
    assert bca.hi == pytest.approx(pct.hi, abs=0.02)


def test_bca_differs_from_percentile_on_skewed_data():
    rng = random.Random(3)
    values = [rng.expovariate(1.0) for _ in range(50)]  # strongly right-skewed
    bca = bootstrap_mean(values, resamples=2000, seed=42, method="bca")
    pct = bootstrap_mean(values, resamples=2000, seed=42, method="percentile")
    assert (bca.lo, bca.hi) != (pct.lo, pct.hi)


def test_interval_width_scales_with_n_and_confidence():
    small = bootstrap_mean(_noisy_values(20, seed=5), resamples=1000, seed=42)
    large = bootstrap_mean(_noisy_values(320, seed=5), resamples=1000, seed=42)
    assert (large.hi - large.lo) < (small.hi - small.lo)

    values = _noisy_values(50)
    ci95 = bootstrap_mean(values, resamples=1000, seed=42, alpha=0.05)
    ci99 = bootstrap_mean(values, resamples=1000, seed=42, alpha=0.01)
    assert (ci99.hi - ci99.lo) > (ci95.hi - ci95.lo)


def test_paired_bootstrap_respects_the_pairing_structure():
    # b = a + 0.1 exactly: every resampled difference is exactly 0.1, so the
    # difference interval must be the point [0.1, 0.1] regardless of noise
    # in a — and B's estimate must equal A's plus the difference.
    a = _noisy_values(30)
    b = [v + 0.1 for v in a]
    ci_a, ci_b, ci_d = paired_bootstrap(a, b, resamples=500, seed=42)
    assert ci_d.lo == pytest.approx(0.1)
    assert ci_d.hi == pytest.approx(0.1)
    assert ci_b.estimate == pytest.approx(ci_a.estimate + ci_d.estimate)


def test_unpaired_bootstrap_deterministic_and_brackets_diff():
    rng = random.Random(9)
    a = [rng.gauss(0.5, 0.1) for _ in range(40)]
    b = [rng.gauss(0.7, 0.1) for _ in range(35)]
    ci1 = unpaired_bootstrap(a, b, resamples=800, seed=42)[2]
    ci2 = unpaired_bootstrap(a, b, resamples=800, seed=42)[2]
    assert (ci1.lo, ci1.hi) == (ci2.lo, ci2.hi)
    assert ci1.lo < ci1.estimate < ci1.hi
    assert ci1.estimate == pytest.approx(sum(b) / 35 - sum(a) / 40)


def test_interval_helpers_match_hand_computation():
    values = [1.0, 4.0, 7.0, 8.0]
    direct = []
    for i in range(len(values)):
        rest = values[:i] + values[i + 1 :]
        direct.append(sum(rest) / len(rest))
    assert jackknife_means(values) == pytest.approx(direct)

    boot = sorted(float(i) for i in range(1, 101))
    lo, hi = percentile_interval(boot, 0.05)
    assert lo == pytest.approx(3.475)  # (n-1)*0.025 interpolated (type 7)
    assert hi == pytest.approx(97.525)


def test_degenerate_and_invalid_inputs():
    # Estimate entirely outside the bootstrap distribution: clamps, no crash.
    boot = sorted([1.0, 1.1, 1.2, 1.3, 1.4])
    lo, hi = bca_interval(boot, 0.5, [0.4, 0.5, 0.6], alpha=0.05)
    assert boot[0] <= lo <= hi <= boot[-1]

    with pytest.raises(UsageError, match="at least 2"):
        bootstrap_mean([1.0], resamples=100, seed=42)
    with pytest.raises(UsageError, match="alpha"):
        bootstrap_mean([1.0, 2.0], resamples=100, seed=42, alpha=1.5)
    with pytest.raises(UsageError, match="ci method"):
        bootstrap_mean([1.0, 2.0], resamples=100, seed=42, method="magic")
