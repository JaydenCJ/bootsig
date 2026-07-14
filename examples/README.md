# bootsig examples

Three committed 100-example runs of a fictional QA eval, plus the script
that regenerates them byte-identically:

- **`baseline.jsonl`** — the current prompt, 71/100 correct.
- **`candidate.jsonl`** — a tweaked prompt, 73/100 correct. Looks better;
  `bootsig compare` shows the flips are churn (13 new wins, 11 new losses,
  p ≈ 0.84).
- **`improved.jsonl`** — a genuinely better prompt, 84/100 correct
  (16 new wins, 3 new losses, p ≈ 0.005).
- **`generate_runs.py`** — deterministic generator (seed 7):
  `python examples/generate_runs.py` rewrites the three files in place,
  byte-identical to what is committed.
- **`test_python_api.py`** — a pytest module (collected by `pytest` from
  the repository root) showing the Python API: assert significance in your
  own suite instead of shelling out to the CLI.

Try the two headline comparisons, then the sensitivity check:

```bash
bootsig compare examples/baseline.jsonl examples/candidate.jsonl   # noise
bootsig compare examples/baseline.jsonl examples/improved.jsonl    # real
bootsig mde examples/baseline.jsonl examples/candidate.jsonl       # sensitivity
```

Everything runs fully offline; the files are plain JSONL with `id`,
`category`, and `score` fields.
