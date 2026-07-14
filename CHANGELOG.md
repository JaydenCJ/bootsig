# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-12

### Added

- `bootsig compare`: paired and unpaired comparison of two JSONL eval runs —
  bootstrap confidence intervals for each run's mean and for the difference,
  a two-sided permutation test (sign-flip for paired, shuffle for unpaired),
  win/loss/tie counts, Cohen's d, relative change, and a plain-language
  verdict at the chosen alpha.
- Exact permutation p-values whenever the full permutation space fits in
  `min(--resamples, 100000)`; Monte Carlo with the add-one correction
  (Phipson & Smyth 2010) otherwise, so p-values are never zero.
- BCa (bias-corrected and accelerated, Efron 1987) bootstrap intervals by
  default with a midrank tie convention for discrete metrics, and
  `--ci-method percentile` for plain type-7 quantile intervals.
- Exact McNemar test on discordant pairs, reported automatically for binary
  paired metrics, with the two-sided binomial p-value computed in log-space.
- Pairing that refuses to guess: id-based matching (auto-detected or
  `--id`), line-order fallback only when provably safe, and loud
  `PairingError`s with fix hints everywhere else.
- JSONL loader with dotted key paths, metric auto-detection
  (score/correct/passed/accuracy/value), boolean coercion, `--missing
  error|skip` policies, and per-line error messages naming file and line.
- `bootsig inspect`: one-run summary — n, mean, sd, bootstrap CI of the
  mean, binary detection, quartiles, and a unicode histogram.
- `bootsig mde`: minimum detectable effect and required-n estimates for
  paired and unpaired designs, so under-powered evals announce themselves.
- CI gating: `--fail-on regression|difference` (exit 1), `--lower-is-better`
  for cost metrics, and `--json` machine output with sorted keys.
- Full determinism under `--seed`: byte-identical reports for identical
  inputs, with the reproducibility parameters printed in the footer.
- Three committed 100-example demo runs with a byte-reproducible generator,
  a Python-API example test module, `docs/methodology.md` describing every
  formula with references, 90 deterministic offline tests, and
  `scripts/smoke.sh`, which exercises the CLI end to end and prints
  `SMOKE OK`.

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/bootsig/releases/tag/v0.1.0
