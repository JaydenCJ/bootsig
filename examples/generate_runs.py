"""Regenerate the example eval runs committed in this directory.

Three 100-example runs of a fictional QA eval, built with a fixed seed so
regeneration is byte-identical to the committed files:

- ``baseline.jsonl``  — the current prompt: 71/100 correct.
- ``candidate.jsonl`` — a tweaked prompt: 73/100 correct, but the flips are
  mostly churn (13 new wins, 11 new losses). Looks better; is noise.
- ``improved.jsonl``  — a genuinely better prompt: 84/100 correct
  (16 new wins, 3 new losses). A real, detectable improvement.

Usage::

    python examples/generate_runs.py [output_dir]   # default: examples/
"""

from __future__ import annotations

import json
import os
import random
import sys

CATEGORIES = ("arithmetic", "code", "extraction", "reasoning")
N = 100


def _write(path: str, scores: "list[int]") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for i, score in enumerate(scores, start=1):
            record = {
                "id": f"ex-{i:03d}",
                "category": CATEGORIES[(i - 1) % len(CATEGORIES)],
                "score": score,
            }
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"wrote {path} ({sum(scores)}/{len(scores)} correct)")


def _flip(rng: random.Random, base: "list[int]", to_one: int, to_zero: int) -> "list[int]":
    """Copy ``base``, flipping ``to_one`` zeros up and ``to_zero`` ones down."""
    out = list(base)
    zeros = [i for i, s in enumerate(out) if s == 0]
    ones = [i for i, s in enumerate(out) if s == 1]
    for i in rng.sample(zeros, to_one):
        out[i] = 1
    for i in rng.sample(ones, to_zero):
        out[i] = 0
    return out


def main(out_dir: str) -> None:
    rng = random.Random(7)
    baseline = [0] * N
    for i in rng.sample(range(N), 71):
        baseline[i] = 1

    candidate = _flip(rng, baseline, to_one=13, to_zero=11)  # 73 correct, churn
    improved = _flip(rng, baseline, to_one=16, to_zero=3)  # 84 correct, real gain

    os.makedirs(out_dir, exist_ok=True)
    _write(os.path.join(out_dir, "baseline.jsonl"), baseline)
    _write(os.path.join(out_dir, "candidate.jsonl"), candidate)
    _write(os.path.join(out_dir, "improved.jsonl"), improved)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
