# Methodology

Exactly what bootsig computes, so you can check the math instead of
trusting the tool. Everything below is implemented in pure standard-library
Python; module names refer to `src/bootsig/`.

## Paired vs unpaired

Two runs over the **same examples** should be compared pairwise: each
example's difficulty affects both runs, and differencing per example
cancels that shared noise. bootsig pairs on ids when both files have them
(`id`, `example_id`, `task_id`, `case_id`, `name`, or `--id KEY`), falls
back to line order only when neither file has ids, both are the same
length, and nothing was skipped, and refuses to guess in every other case
(`pairing.py`). `--unpaired` treats the runs as independent samples — use
it when the runs cover different examples.

## Permutation test (`permutation.py`)

The reported p-value is two-sided, for the null hypothesis "labels A/B are
exchangeable".

- **Paired (sign-flip).** Under the null each per-example difference
  `d_i = b_i - a_i` is symmetric around zero, so each `d_i` keeps or flips
  its sign with probability ½. The statistic is `|Σ d_i|` over nonzero
  differences (flipping a zero changes nothing, so ties are excluded from
  the space without changing any p-value).
- **Unpaired (shuffle).** All values are pooled and dealt into groups of
  the original sizes; the statistic is `|mean(B*) − mean(A*)|`.

**Exact when small.** If the full permutation space (2^m sign patterns, or
C(n_A+n_B, n_A) partitions) is no larger than `min(--resamples, 100000)`,
bootsig enumerates it completely and the p-value is exact — common for
evals where only a handful of examples changed. Otherwise it samples
`--resamples` permutations and applies the add-one correction
`p = (hits + 1) / (resamples + 1)` (Phipson & Smyth, 2010), which is never
zero and never anti-conservative. The report says which mode ran.
Permutations at least as extreme as the observed statistic are counted
with a relative tolerance of 1e-9, so exact mirror-image permutations are
not lost to floating-point rounding.

## Bootstrap confidence intervals (`bootstrap.py`)

Intervals for mean(A), mean(B), and the mean difference come from
resampling with replacement, honoring the design: paired analysis
resamples **pairs** (one index vector drives all three statistics), and
unpaired analysis resamples each run independently.

- **`percentile`** — plain type-7 quantiles of the bootstrap distribution
  (the same interpolation rule as NumPy's default).
- **`bca`** (default) — bias-corrected and accelerated (Efron, 1987). The
  bias term `z₀` uses the midrank convention (bootstrap replicates tied
  with the point estimate count half), which matters for binary metrics
  where a large atom sits exactly at the sample mean; the acceleration
  term comes from a leave-one-out jackknife. Degenerate cases (constant
  data, corrections pushed off the ends) fall back to percentile behavior
  instead of producing NaNs.

## Exact McNemar (`compare.py`)

When both runs are binary (every value 0/1) and the analysis is paired,
bootsig also reports the exact McNemar test: of the discordant pairs
(`n01` = A right/B wrong, `n10` = A wrong/B right), is the split
compatible with a fair coin? The p-value is the exact two-sided binomial
test at p = ½ using the minimum-likelihood definition, computed in
log-space (`stats.py`) — the same convention as SciPy's `binomtest`, so
numbers are directly comparable.

## Minimum detectable effect (`power.py`)

`bootsig mde` answers "what difference could this eval even see?" with the
standard normal-approximation power formula:

```
MDE = (z_{1-α/2} + z_{power}) · SE
SE  = sd(d) / √n            (paired: sd of per-example differences)
SE  = sd · √(2/n)           (unpaired: two runs of n, common sd)
```

and inverts it for `required n` given a target difference. With α = 0.05
and power = 0.8 the constant is z₀.₉₇₅ + z₀.₈ ≈ 2.8016. These are
approximations — good to a few percent for n in the dozens and beyond —
meant to set expectations, not to replace the tests above.

## Determinism

Every number bootsig prints is a pure function of the input files and the
flags. The bootstrap consumes `random.Random(seed)` and the permutation
test `random.Random(seed + 1)` (so the two procedures never share a
stream), with `--seed 42` by default. The report footer records seed,
resample count, CI method, and version — paste it into a PR and anyone can
reproduce the report byte for byte.

## References

- B. Efron (1987), *Better bootstrap confidence intervals*, JASA 82(397).
- B. Phipson & G. K. Smyth (2010), *Permutation p-values should never be
  zero*, Stat. Appl. Genet. Mol. Biol. 9(1).
- A. C. Davison & D. V. Hinkley (1997), *Bootstrap Methods and their
  Application*, Cambridge University Press.
- Q. McNemar (1947), *Note on the sampling error of the difference between
  correlated proportions or percentages*, Psychometrika 12(2).
