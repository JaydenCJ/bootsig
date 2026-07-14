"""Permutation tests for the difference between two eval runs.

The null hypothesis is "relabeling the two runs changes nothing":

- **Paired** runs use the sign-flip test: under the null, each per-example
  difference is as likely to be +d as -d, so we flip signs and ask how often
  a relabeled |sum of differences| is at least as extreme as the observed
  one. Zero differences are excluded from flipping (a flipped zero is still
  zero) which shrinks the space without changing any p-value.
- **Unpaired** runs use the classic shuffle test: pool all values, deal a
  random group of size n_A, and compare the resulting mean difference.

**Exactness.** When the full permutation space is no larger than
``min(resamples, 100000)``, bootsig enumerates it completely and the
p-value is exact — no Monte Carlo error at all, common for evals with few
disagreements. Otherwise it falls back to Monte Carlo with the add-one
correction ``p = (hits + 1) / (resamples + 1)`` (Phipson & Smyth 2010),
which is never zero and never anti-conservative.

Floating-point ties are counted as "at least as extreme" via a relative
tolerance, so an exactly-mirrored permutation is never dropped by rounding.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from statistics import fmean
from typing import List, Sequence

from .errors import UsageError

#: Hard ceiling on exact enumeration, whatever ``resamples`` asks for.
EXACT_CAP = 100_000


@dataclass(frozen=True)
class PermutationResult:
    """Outcome of a permutation test."""

    p_value: float
    observed_diff: float
    resamples: int
    exact: bool
    method: str


def _tolerance(observed: float) -> float:
    return 1e-9 * max(1.0, abs(observed))


def paired_permutation_test(
    diffs: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 42,
) -> PermutationResult:
    """Two-sided sign-flip test on per-example differences (B - A)."""
    if not diffs:
        raise UsageError("paired permutation test needs at least one difference")
    if resamples < 1:
        raise UsageError(f"resamples must be >= 1, got {resamples}")
    observed_mean = fmean(diffs)
    nonzero = [d for d in diffs if d != 0.0]
    if not nonzero:
        # Every pair tied: the runs are literally identical on this metric.
        return PermutationResult(1.0, 0.0, 1, True, "sign-flip")

    observed = abs(sum(nonzero))
    tol = _tolerance(observed)
    m = len(nonzero)

    if m <= 30 and (1 << m) <= min(resamples, EXACT_CAP):
        total = 1 << m
        hits = 0
        for mask in range(total):
            s = 0.0
            for i, d in enumerate(nonzero):
                s += d if (mask >> i) & 1 else -d
            if abs(s) >= observed - tol:
                hits += 1
        # The identity assignment always counts, so p >= 1/total: exact
        # p-values are never zero either.
        return PermutationResult(hits / total, observed_mean, total, True, "sign-flip")

    rng = random.Random(seed)
    hits = 0
    for _ in range(resamples):
        bits = rng.getrandbits(m)
        s = 0.0
        for i, d in enumerate(nonzero):
            s += d if (bits >> i) & 1 else -d
        if abs(s) >= observed - tol:
            hits += 1
    return PermutationResult((hits + 1) / (resamples + 1), observed_mean, resamples, False, "sign-flip")


def unpaired_permutation_test(
    a_values: Sequence[float],
    b_values: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 42,
) -> PermutationResult:
    """Two-sided shuffle test on the difference of means, mean(B) - mean(A)."""
    na, nb = len(a_values), len(b_values)
    if na < 1 or nb < 1:
        raise UsageError("unpaired permutation test needs values in both runs")
    if resamples < 1:
        raise UsageError(f"resamples must be >= 1, got {resamples}")
    pooled: List[float] = list(a_values) + list(b_values)
    total_sum = sum(pooled)
    observed_diff = fmean(b_values) - fmean(a_values)
    observed = abs(observed_diff)
    tol = _tolerance(observed)

    def diff_from_group_a_sum(sum_a: float) -> float:
        return (total_sum - sum_a) / nb - sum_a / na

    n = na + nb
    space = math.comb(n, na)
    if space <= min(resamples, EXACT_CAP):
        hits = 0
        for combo in itertools.combinations(range(n), na):
            sum_a = 0.0
            for i in combo:
                sum_a += pooled[i]
            if abs(diff_from_group_a_sum(sum_a)) >= observed - tol:
                hits += 1
        return PermutationResult(hits / space, observed_diff, space, True, "shuffle")

    rng = random.Random(seed)
    indices = list(range(n))
    hits = 0
    for _ in range(resamples):
        rng.shuffle(indices)
        sum_a = 0.0
        for i in indices[:na]:
            sum_a += pooled[i]
        if abs(diff_from_group_a_sum(sum_a)) >= observed - tol:
            hits += 1
    return PermutationResult((hits + 1) / (resamples + 1), observed_diff, resamples, False, "shuffle")
