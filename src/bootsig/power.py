"""Sensitivity analysis: what difference can this eval even detect?

Most eval suites are far too small to see the differences teams argue
about, and nobody notices because nothing ever reports it. These two
closed-form functions make the limit explicit:

- :func:`mde` — the minimum detectable effect: the smallest true difference
  a two-sided test at level ``alpha`` will flag with probability ``power``,
  given the observed spread and sample size.
- :func:`required_n` — the inverse: how many examples you would need to
  reliably detect a target difference.

Both use the standard normal-approximation power formula
``MDE = (z_{1-alpha/2} + z_{power}) * SE``, where the standard error is
``sd/sqrt(n)`` for paired designs (sd of per-example differences) and
``sd * sqrt(2/n)`` for two independent runs of n examples each. That
approximation is what every sample-size calculator uses; for the n where
the answer matters (dozens to thousands) it is accurate to a percent or so.
"""

from __future__ import annotations

import math

from .errors import UsageError
from .stats import normal_quantile

DESIGNS = ("paired", "unpaired")


def _z_total(alpha: float, power: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise UsageError(f"alpha must be strictly between 0 and 1, got {alpha}")
    if not 0.0 < power < 1.0:
        raise UsageError(f"power must be strictly between 0 and 1, got {power}")
    return normal_quantile(1.0 - alpha / 2.0) + normal_quantile(power)


def _check_design(design: str) -> None:
    if design not in DESIGNS:
        raise UsageError(f'design must be one of {DESIGNS}, got "{design}"')


def mde(
    sd: float,
    n: int,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    design: str = "paired",
) -> float:
    """Minimum detectable difference for a two-sided test.

    ``sd`` is the sd of per-example differences (paired) or the per-run
    example sd (unpaired, assuming two runs of ``n`` each). ``n`` is the
    number of pairs (paired) or examples per run (unpaired).
    """
    _check_design(design)
    if n < 2:
        raise UsageError(f"n must be >= 2, got {n}")
    if sd < 0.0:
        raise UsageError(f"sd must be >= 0, got {sd}")
    se = sd / math.sqrt(n)
    if design == "unpaired":
        se *= math.sqrt(2.0)
    return _z_total(alpha, power) * se


def required_n(
    sd: float,
    target_diff: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    design: str = "paired",
) -> int:
    """Sample size needed to detect ``target_diff`` with the given power.

    Returns pairs for the paired design, examples **per run** for the
    unpaired design. Always at least 2.
    """
    _check_design(design)
    if target_diff <= 0.0:
        raise UsageError(f"target difference must be positive, got {target_diff}")
    if sd < 0.0:
        raise UsageError(f"sd must be >= 0, got {sd}")
    if sd == 0.0:
        # No per-example noise at all: any real difference shows immediately.
        _z_total(alpha, power)  # still validate alpha/power
        return 2
    n = (_z_total(alpha, power) * sd / target_diff) ** 2
    if design == "unpaired":
        n *= 2.0
    return max(2, math.ceil(n))
