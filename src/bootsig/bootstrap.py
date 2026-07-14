"""Bootstrap confidence intervals for run means and mean differences.

Two interval methods are offered:

- ``percentile`` — plain quantiles of the bootstrap distribution. Simple,
  transparent, and what most people mean by "bootstrap CI".
- ``bca`` (default) — bias-corrected and accelerated (Efron 1987). It
  corrects both the median bias of the bootstrap distribution and its
  skewness (estimated by a jackknife), which matters for the small, lumpy
  samples eval suites actually have.

Resampling respects the study design: **paired** analysis resamples pairs
(one index vector drives A, B, and the difference, preserving per-example
correlation), while **unpaired** analysis resamples each run independently.
All randomness comes from one seeded ``random.Random``, so identical inputs
and flags always reproduce identical intervals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import fmean
from typing import List, Sequence, Tuple

from .errors import UsageError
from .stats import normal_cdf, normal_quantile, quantile

CI_METHODS = ("bca", "percentile")


@dataclass(frozen=True)
class BootstrapCI:
    """A point estimate with its bootstrap confidence interval."""

    estimate: float
    lo: float
    hi: float
    method: str
    resamples: int
    alpha: float


def _validate(resamples: int, alpha: float, method: str) -> None:
    if resamples < 1:
        raise UsageError(f"resamples must be >= 1, got {resamples}")
    if not 0.0 < alpha < 1.0:
        raise UsageError(f"alpha must be strictly between 0 and 1, got {alpha}")
    if method not in CI_METHODS:
        raise UsageError(f'ci method must be one of {CI_METHODS}, got "{method}"')


def jackknife_means(values: Sequence[float]) -> List[float]:
    """Leave-one-out means in O(n) via the running total."""
    n = len(values)
    total = sum(values)
    return [(total - v) / (n - 1) for v in values]


def percentile_interval(boot_sorted: Sequence[float], alpha: float) -> Tuple[float, float]:
    """Plain percentile interval from a sorted bootstrap distribution."""
    return quantile(boot_sorted, alpha / 2.0), quantile(boot_sorted, 1.0 - alpha / 2.0)


def bca_interval(
    boot_sorted: Sequence[float],
    estimate: float,
    jack_stats: Sequence[float],
    alpha: float,
) -> Tuple[float, float]:
    """Bias-corrected and accelerated interval (Efron 1987).

    ``boot_sorted`` is the sorted bootstrap distribution of the statistic,
    ``estimate`` the statistic on the original data, and ``jack_stats`` the
    leave-one-out values used to estimate acceleration. Degenerate cases
    (constant bootstrap distribution, zero jackknife spread, or a bias
    correction pushed off the ends) fall back to well-defined behavior
    instead of NaNs.
    """
    n_boot = len(boot_sorted)
    if boot_sorted[0] == boot_sorted[-1]:
        return boot_sorted[0], boot_sorted[0]

    # Midrank convention: ties with the estimate count half. Binary metrics
    # put a large atom exactly at the estimate, and counting it all as
    # "below" (or none of it) would bias z0 on the most common eval data.
    below = sum(1 for t in boot_sorted if t < estimate)
    ties = sum(1 for t in boot_sorted if t == estimate)
    proportion = (below + 0.5 * ties) / n_boot
    # Clamp so z0 stays finite even when the estimate sits outside the
    # bootstrap distribution entirely (tiny n, extreme skew).
    proportion = min(max(proportion, 1.0 / (n_boot + 1)), n_boot / (n_boot + 1))
    z0 = normal_quantile(proportion)

    jack_mean = fmean(jack_stats)
    cubed = sum((jack_mean - j) ** 3 for j in jack_stats)
    squared = sum((jack_mean - j) ** 2 for j in jack_stats)
    acceleration = cubed / (6.0 * squared ** 1.5) if squared > 0.0 else 0.0

    def adjusted(q: float) -> float:
        z = normal_quantile(q)
        denom = 1.0 - acceleration * (z0 + z)
        if denom <= 0.0:
            # Acceleration blew up the correction; degrade to percentile.
            return q
        return min(max(normal_cdf(z0 + (z0 + z) / denom), 0.0), 1.0)

    lo_q = adjusted(alpha / 2.0)
    hi_q = adjusted(1.0 - alpha / 2.0)
    if lo_q > hi_q:
        lo_q, hi_q = hi_q, lo_q
    return quantile(boot_sorted, lo_q), quantile(boot_sorted, hi_q)


def _interval(
    boot: List[float],
    estimate: float,
    jack_stats: Sequence[float],
    alpha: float,
    method: str,
    resamples: int,
) -> BootstrapCI:
    boot_sorted = sorted(boot)
    if method == "bca":
        lo, hi = bca_interval(boot_sorted, estimate, jack_stats, alpha)
    else:
        lo, hi = percentile_interval(boot_sorted, alpha)
    return BootstrapCI(estimate=estimate, lo=lo, hi=hi, method=method, resamples=resamples, alpha=alpha)


def bootstrap_mean(
    values: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 42,
    alpha: float = 0.05,
    method: str = "bca",
) -> BootstrapCI:
    """CI for the mean of one run (used by ``bootsig inspect``)."""
    _validate(resamples, alpha, method)
    n = len(values)
    if n < 2:
        raise UsageError(f"bootstrap needs at least 2 values, got {n}")
    estimate = fmean(values)
    if min(values) == max(values):
        return BootstrapCI(estimate, estimate, estimate, method, resamples, alpha)
    rng = random.Random(seed)
    indices = range(n)
    boot = []
    for _ in range(resamples):
        total = 0.0
        for i in rng.choices(indices, k=n):
            total += values[i]
        boot.append(total / n)
    return _interval(boot, estimate, jackknife_means(values), alpha, method, resamples)


def paired_bootstrap(
    a_values: Sequence[float],
    b_values: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 42,
    alpha: float = 0.05,
    method: str = "bca",
) -> Tuple[BootstrapCI, BootstrapCI, BootstrapCI]:
    """CIs for mean(A), mean(B), and mean(B-A), resampling *pairs*.

    One index vector per resample drives all three statistics, so the
    difference interval honestly reflects the per-example correlation that
    makes paired evals sensitive. Returns ``(ci_a, ci_b, ci_diff)``.
    """
    _validate(resamples, alpha, method)
    n = len(a_values)
    if n != len(b_values):
        raise UsageError("paired bootstrap requires equal-length value vectors")
    if n < 2:
        raise UsageError(f"bootstrap needs at least 2 pairs, got {n}")
    diffs = [b - a for a, b in zip(a_values, b_values)]
    mean_a = fmean(a_values)
    mean_d = fmean(diffs)

    rng = random.Random(seed)
    indices = range(n)
    boot_a: List[float] = []
    boot_d: List[float] = []
    for _ in range(resamples):
        sum_a = 0.0
        sum_d = 0.0
        for i in rng.choices(indices, k=n):
            sum_a += a_values[i]
            sum_d += diffs[i]
        boot_a.append(sum_a / n)
        boot_d.append(sum_d / n)
    boot_b = [a + d for a, d in zip(boot_a, boot_d)]

    def one(boot: List[float], estimate: float, source: Sequence[float]) -> BootstrapCI:
        if min(source) == max(source):
            return BootstrapCI(estimate, estimate, estimate, method, resamples, alpha)
        return _interval(boot, estimate, jackknife_means(source), alpha, method, resamples)

    ci_a = one(boot_a, mean_a, a_values)
    ci_b = one(boot_b, mean_a + mean_d, b_values)
    ci_d = one(boot_d, mean_d, diffs)
    return ci_a, ci_b, ci_d


def unpaired_bootstrap(
    a_values: Sequence[float],
    b_values: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 42,
    alpha: float = 0.05,
    method: str = "bca",
) -> Tuple[BootstrapCI, BootstrapCI, BootstrapCI]:
    """CIs for mean(A), mean(B), and their difference, resampling each run
    independently (no correspondence between examples is assumed)."""
    _validate(resamples, alpha, method)
    na, nb = len(a_values), len(b_values)
    if na < 2 or nb < 2:
        raise UsageError("bootstrap needs at least 2 values in each run")
    mean_a = fmean(a_values)
    mean_b = fmean(b_values)

    rng = random.Random(seed)
    idx_a = range(na)
    idx_b = range(nb)
    boot_a: List[float] = []
    boot_b: List[float] = []
    for _ in range(resamples):
        sum_a = 0.0
        for i in rng.choices(idx_a, k=na):
            sum_a += a_values[i]
        sum_b = 0.0
        for j in rng.choices(idx_b, k=nb):
            sum_b += b_values[j]
        boot_a.append(sum_a / na)
        boot_b.append(sum_b / nb)
    boot_d = [b - a for a, b in zip(boot_a, boot_b)]

    # Jackknife for the difference: leave out one observation from either
    # run; the other run's mean is unchanged.
    jack_d = [(mean_b - jm) for jm in jackknife_means(a_values)] + [
        (jm - mean_a) for jm in jackknife_means(b_values)
    ]

    def one(boot: List[float], estimate: float, source: Sequence[float], jack: Sequence[float]) -> BootstrapCI:
        if min(source) == max(source):
            return BootstrapCI(estimate, estimate, estimate, method, resamples, alpha)
        return _interval(boot, estimate, jack, alpha, method, resamples)

    ci_a = one(boot_a, mean_a, a_values, jackknife_means(a_values))
    ci_b = one(boot_b, mean_b, b_values, jackknife_means(b_values))
    if min(a_values) == max(a_values) and min(b_values) == max(b_values):
        d = mean_b - mean_a
        ci_d = BootstrapCI(d, d, d, method, resamples, alpha)
    else:
        ci_d = _interval(boot_d, mean_b - mean_a, jack_d, alpha, method, resamples)
    return ci_a, ci_b, ci_d
