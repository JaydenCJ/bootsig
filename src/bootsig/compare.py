"""The full comparison pipeline: load, pair, resample, test, decide.

:func:`compare_files` is the library equivalent of ``bootsig compare`` —
everything the CLI prints comes from the :class:`Comparison` it returns, so
scripts and CI hooks can consume the same numbers programmatically.

Reproducibility contract: the same two files with the same flags always
produce the same ``Comparison``, byte for byte. The bootstrap consumes
``Random(seed)`` and the permutation test ``Random(seed + 1)``, so the two
procedures never share (and therefore never perturb) each other's stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import List, Optional

from .bootstrap import CI_METHODS, BootstrapCI, paired_bootstrap, unpaired_bootstrap
from .errors import DataError, UsageError
from .loader import Run, load_run
from .pairing import PairedRuns, pair_runs
from .permutation import PermutationResult, paired_permutation_test, unpaired_permutation_test
from .stats import cohens_d_paired, cohens_d_unpaired, binom_test_two_sided_half, is_binary, sample_sd


@dataclass(frozen=True)
class RunStats:
    """One run's contribution to a comparison."""

    path: str
    n: int
    mean: float
    sd: float
    ci: BootstrapCI


@dataclass(frozen=True)
class McNemarResult:
    """Exact McNemar test on discordant pairs (binary paired metrics only)."""

    n01: int  # A correct, B wrong (B lost this example)
    n10: int  # A wrong, B correct (B won this example)
    p_value: float


@dataclass(frozen=True)
class Comparison:
    """Everything ``bootsig compare`` knows about two runs."""

    design: str  # "paired" | "unpaired"
    metric_key: str
    metric_auto: bool
    a: RunStats
    b: RunStats
    diff_mean: float
    diff_ci: BootstrapCI
    relative: Optional[float]
    permutation: PermutationResult
    alpha: float
    significant: bool
    direction: str  # "improvement" | "regression" | "no change"
    lower_is_better: bool
    cohens_d: Optional[float]
    seed: int
    resamples: int
    ci_method: str
    skipped_a: int
    skipped_b: int
    # Paired-only fields (None for unpaired analyses).
    pairs: Optional[int] = None
    matched_on: Optional[str] = None
    unmatched_a: Optional[int] = None
    unmatched_b: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ties: Optional[int] = None
    mcnemar: Optional[McNemarResult] = None


def _direction(diff: float, lower_is_better: bool) -> str:
    if diff == 0.0:
        return "no change"
    improved = diff > 0.0
    if lower_is_better:
        improved = not improved
    return "improvement" if improved else "regression"


def _mcnemar(a_values: List[float], b_values: List[float]) -> McNemarResult:
    n01 = sum(1 for a, b in zip(a_values, b_values) if a == 1.0 and b == 0.0)
    n10 = sum(1 for a, b in zip(a_values, b_values) if a == 0.0 and b == 1.0)
    discordant = n01 + n10
    p = 1.0 if discordant == 0 else binom_test_two_sided_half(n10, discordant)
    return McNemarResult(n01=n01, n10=n10, p_value=p)


def compare_files(
    path_a: str,
    path_b: str,
    *,
    metric: Optional[str] = None,
    id_key: Optional[str] = None,
    unpaired: bool = False,
    resamples: int = 10000,
    seed: int = 42,
    alpha: float = 0.05,
    ci_method: str = "bca",
    missing: str = "error",
    lower_is_better: bool = False,
) -> Comparison:
    """Compare two JSONL eval runs; see the module docstring for guarantees."""
    if not 0.0 < alpha < 1.0:
        raise UsageError(f"alpha must be strictly between 0 and 1, got {alpha}")
    if ci_method not in CI_METHODS:
        raise UsageError(f'ci method must be one of {CI_METHODS}, got "{ci_method}"')
    if resamples < 1:
        raise UsageError(f"resamples must be >= 1, got {resamples}")

    run_a = load_run(path_a, metric=metric, id_key=id_key, missing=missing)
    # Run B must be read with the *same* metric key as run A, whether that
    # key was given or auto-detected — comparing different metrics would be
    # nonsense, and this way a mismatch fails loudly with B's path and line.
    run_b = load_run(path_b, metric=run_a.metric_key, id_key=id_key, missing=missing)

    if unpaired:
        return _compare_unpaired(run_a, run_b, resamples, seed, alpha, ci_method, lower_is_better)
    return _compare_paired(run_a, run_b, resamples, seed, alpha, ci_method, lower_is_better)


def _run_stats(run_path: str, values: List[float], ci: BootstrapCI) -> RunStats:
    return RunStats(path=run_path, n=len(values), mean=fmean(values), sd=sample_sd(values), ci=ci)


def _relative(diff: float, mean_a: float) -> Optional[float]:
    return diff / abs(mean_a) if mean_a != 0.0 else None


def _compare_paired(
    run_a: Run,
    run_b: Run,
    resamples: int,
    seed: int,
    alpha: float,
    ci_method: str,
    lower_is_better: bool,
) -> Comparison:
    paired: PairedRuns = pair_runs(run_a, run_b)
    if paired.n < 2:
        matched = "only 1 pair" if paired.n == 1 else f"only {paired.n} pairs"
        raise DataError(
            f"{matched} matched — need at least 2 for a paired test",
            path=run_a.path,
        )
    diffs = paired.diffs
    ci_a, ci_b, ci_d = paired_bootstrap(
        paired.a_values, paired.b_values, resamples=resamples, seed=seed, alpha=alpha, method=ci_method
    )
    perm = paired_permutation_test(diffs, resamples=resamples, seed=seed + 1)
    diff_mean = fmean(diffs)
    mcnemar = None
    if is_binary(paired.a_values) and is_binary(paired.b_values):
        mcnemar = _mcnemar(paired.a_values, paired.b_values)
    significant = perm.p_value < alpha
    return Comparison(
        design="paired",
        metric_key=run_a.metric_key,
        metric_auto=run_a.metric_auto,
        a=_run_stats(run_a.path, paired.a_values, ci_a),
        b=_run_stats(run_b.path, paired.b_values, ci_b),
        diff_mean=diff_mean,
        diff_ci=ci_d,
        relative=_relative(diff_mean, fmean(paired.a_values)),
        permutation=perm,
        alpha=alpha,
        significant=significant,
        direction=_direction(diff_mean, lower_is_better),
        lower_is_better=lower_is_better,
        cohens_d=cohens_d_paired(diffs),
        seed=seed,
        resamples=resamples,
        ci_method=ci_method,
        skipped_a=len(run_a.skipped),
        skipped_b=len(run_b.skipped),
        pairs=paired.n,
        matched_on=paired.matched_on,
        unmatched_a=paired.unmatched_a,
        unmatched_b=paired.unmatched_b,
        wins=sum(1 for d in diffs if d > 0.0),
        losses=sum(1 for d in diffs if d < 0.0),
        ties=sum(1 for d in diffs if d == 0.0),
        mcnemar=mcnemar,
    )


def _compare_unpaired(
    run_a: Run,
    run_b: Run,
    resamples: int,
    seed: int,
    alpha: float,
    ci_method: str,
    lower_is_better: bool,
) -> Comparison:
    a_values, b_values = run_a.values, run_b.values
    if len(a_values) < 2 or len(b_values) < 2:
        raise DataError("unpaired comparison needs at least 2 records in each run", path=run_a.path)
    ci_a, ci_b, ci_d = unpaired_bootstrap(
        a_values, b_values, resamples=resamples, seed=seed, alpha=alpha, method=ci_method
    )
    perm = unpaired_permutation_test(a_values, b_values, resamples=resamples, seed=seed + 1)
    diff_mean = fmean(b_values) - fmean(a_values)
    significant = perm.p_value < alpha
    return Comparison(
        design="unpaired",
        metric_key=run_a.metric_key,
        metric_auto=run_a.metric_auto,
        a=_run_stats(run_a.path, a_values, ci_a),
        b=_run_stats(run_b.path, b_values, ci_b),
        diff_mean=diff_mean,
        diff_ci=ci_d,
        relative=_relative(diff_mean, fmean(a_values)),
        permutation=perm,
        alpha=alpha,
        significant=significant,
        direction=_direction(diff_mean, lower_is_better),
        lower_is_better=lower_is_better,
        cohens_d=cohens_d_unpaired(a_values, b_values),
        seed=seed,
        resamples=resamples,
        ci_method=ci_method,
        skipped_a=len(run_a.skipped),
        skipped_b=len(run_b.skipped),
    )
