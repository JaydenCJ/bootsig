"""Small, exact statistical primitives — the pieces everything else trusts.

Everything here is deterministic, closed-form, and standard-library only:
means, sample standard deviation, type-7 quantiles (the same interpolation
NumPy and R use by default), the standard normal distribution, an exact
two-sided binomial test at p = 1/2 (the engine behind McNemar), and effect
sizes. Keeping these in one dependency-free module makes the statistical
claims of the whole tool auditable in a single screen of code.
"""

from __future__ import annotations

import math
from statistics import NormalDist, fmean
from typing import Dict, List, Sequence

_NORMAL = NormalDist()


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; raises ``StatisticsError`` on empty input."""
    return fmean(values)


def sample_sd(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1 denominator); 0.0 when n < 2."""
    n = len(values)
    if n < 2:
        return 0.0
    m = fmean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Type-7 (linear interpolation) quantile of an already-sorted sequence.

    Matches NumPy's default ``quantile`` and R's ``quantile(type = 7)``, so
    bootstrap percentile intervals here agree with what users would compute
    themselves in either ecosystem.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"quantile q must be in [0, 1], got {q}")
    n = len(sorted_values)
    if n == 0:
        raise ValueError("quantile of empty sequence")
    if n == 1:
        return sorted_values[0]
    h = (n - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, n - 1)
    frac = h - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def normal_cdf(x: float) -> float:
    """Standard normal CDF Φ(x)."""
    return _NORMAL.cdf(x)


def normal_quantile(p: float) -> float:
    """Standard normal quantile Φ⁻¹(p); p must be strictly inside (0, 1)."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"normal quantile requires 0 < p < 1, got {p}")
    return _NORMAL.inv_cdf(p)


def binom_test_two_sided_half(k: int, n: int) -> float:
    """Exact two-sided binomial test of k successes in n trials at p = 1/2.

    Uses the minimum-likelihood definition (sum the probability of every
    outcome no more likely than the observed one), which is what SciPy's
    ``binomtest`` reports by default — so results here are directly
    comparable. Log-space arithmetic keeps it stable for any n.
    """
    if not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return 1.0
    log_half_n = n * math.log(0.5)

    def log_p(i: int) -> float:
        return math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + log_half_n

    observed = log_p(k)
    tolerance = 1e-9
    total = 0.0
    for i in range(n + 1):
        if log_p(i) <= observed + tolerance:
            total += math.exp(log_p(i))
    return min(1.0, total)


def cohens_d_paired(diffs: Sequence[float]) -> "float | None":
    """Cohen's d for paired data: mean(d) / sd(d). ``None`` when sd is 0."""
    sd = sample_sd(diffs)
    if sd == 0.0:
        return None
    return fmean(diffs) / sd


def cohens_d_unpaired(a: Sequence[float], b: Sequence[float]) -> "float | None":
    """Cohen's d for two independent samples, using the pooled sd."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    var_a = sample_sd(a) ** 2
    var_b = sample_sd(b) ** 2
    pooled = math.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))
    if pooled == 0.0:
        return None
    return (fmean(b) - fmean(a)) / pooled


def describe(values: Sequence[float]) -> Dict[str, object]:
    """Summary statistics used by ``bootsig inspect`` and ``bootsig mde``."""
    ordered: List[float] = sorted(values)
    unique = set(ordered)
    return {
        "n": len(ordered),
        "mean": fmean(ordered),
        "sd": sample_sd(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "p25": quantile(ordered, 0.25),
        "median": quantile(ordered, 0.5),
        "p75": quantile(ordered, 0.75),
        "distinct": len(unique),
        "binary": unique <= {0.0, 1.0},
    }


def is_binary(values: Sequence[float]) -> bool:
    """True when every value is exactly 0.0 or 1.0 (pass/fail metrics)."""
    return set(values) <= {0.0, 1.0}
