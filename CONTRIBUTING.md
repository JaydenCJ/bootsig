# Contributing to bootsig

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome — a statistical correction with a citation is the
ideal first contribution.

## Development setup

```bash
git clone https://github.com/JaydenCJ/bootsig
cd bootsig
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # unit tests + example tests (tests/ and examples/)
bash scripts/smoke.sh  # end-to-end CLI smoke: verdicts, gates, JSON, mde
```

Both must pass before a pull request is reviewed; `scripts/smoke.sh` drives
the real CLI end to end and must print `SMOKE OK`. Everything runs fully
offline with fixed seeds — no API keys, no network, no flakiness.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Statistical claims need receipts.** Any change to a p-value, interval,
  or power computation must cite the method (paper or textbook), update
  `docs/methodology.md`, and add a hand-verifiable exact test case.
- **Determinism is a contract.** The same files and flags must produce
  byte-identical reports; anything that consumes randomness must derive it
  from the user's `--seed`.
- **Every public API needs an English docstring and a test.** The README
  quickstart numbers are asserted verbatim by
  `tests/test_readme_example.py`, so keep code and docs in sync.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line parallel; update all three when you
  change one (English is the authoritative version).

## Reporting bugs

Please include `bootsig --version` output, the exact command line
(including `--seed` if you changed it), and a minimal pair of JSONL files
that reproduces the problem — a dozen lines is usually enough, and the
report footer already contains the reproducibility parameters.

## Security

Please do not open public issues for security problems; use GitHub's
private vulnerability reporting on this repository instead.
