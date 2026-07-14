#!/usr/bin/env bash
# Smoke test for bootsig: drive the real CLI end to end on the committed
# example runs — verdicts, gates, JSON output, sensitivity analysis, and
# byte-for-byte reproducibility. Self-contained: pure stdlib, no network,
# idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies: running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bootsig-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. The example generator is deterministic: regenerating must reproduce the
#    committed fixtures byte for byte.
"$PYTHON" "$ROOT/examples/generate_runs.py" "$WORKDIR" >/dev/null
for f in baseline.jsonl candidate.jsonl improved.jsonl; do
  cmp -s "$ROOT/examples/$f" "$WORKDIR/$f" \
    || fail "regenerated $f differs from the committed fixture"
done
echo "[smoke] example fixtures regenerate byte-identically"

# 2. The headline comparison: +2pt on 100 examples is noise, exit 0.
noise_out="$("$PYTHON" -m bootsig compare "$ROOT/examples/baseline.jsonl" "$ROOT/examples/candidate.jsonl")" \
  || fail "compare (noise case) exited non-zero"
echo "$noise_out" | sed 's/^/[compare] /'
echo "$noise_out" | grep -q "verdict: NOT SIGNIFICANT" || fail "noise case should not be significant"
echo "$noise_out" | grep -q "wins / losses / ties 13 / 11 / 76" || fail "wrong win/loss/tie counts"

# 3. The real improvement is flagged significant.
real_out="$("$PYTHON" -m bootsig compare "$ROOT/examples/baseline.jsonl" "$ROOT/examples/improved.jsonl")"
echo "$real_out" | grep -q "verdict: SIGNIFICANT" || fail "real improvement should be significant"
echo "$real_out" | grep -q "B improves on A by +0.1300" || fail "wrong improvement size"

# 4. Reproducibility: the same command twice is byte-identical output.
second_run="$("$PYTHON" -m bootsig compare "$ROOT/examples/baseline.jsonl" "$ROOT/examples/candidate.jsonl")"
[ "$noise_out" = "$second_run" ] || fail "identical inputs produced different reports"
echo "[smoke] reports are byte-identical across runs"

# 5. CI gate: a significant regression (improved -> baseline) must exit 1.
set +e
"$PYTHON" -m bootsig compare "$ROOT/examples/improved.jsonl" "$ROOT/examples/baseline.jsonl" \
  --fail-on regression >/dev/null
gate_rc=$?
set -e
[ "$gate_rc" -eq 1 ] || fail "--fail-on regression should exit 1 on a regression, got $gate_rc"
# ...while the same gate passes when the change is an improvement.
"$PYTHON" -m bootsig compare "$ROOT/examples/baseline.jsonl" "$ROOT/examples/improved.jsonl" \
  --fail-on regression >/dev/null || fail "--fail-on regression tripped on an improvement"
echo "[smoke] --fail-on regression gates correctly in both directions"

# 6. JSON output is valid and carries the decision.
"$PYTHON" -m bootsig compare "$ROOT/examples/baseline.jsonl" "$ROOT/examples/improved.jsonl" --json \
  | "$PYTHON" -c '
import json, sys
payload = json.load(sys.stdin)
assert payload["significant"] is True, "expected significant=true"
assert payload["design"] == "paired", "expected paired design"
assert payload["mcnemar"]["n10"] == 16, "expected 16 discordant wins"
' || fail "JSON payload failed validation"
echo "[smoke] --json payload validates"

# 7. inspect summarizes a run.
inspect_out="$("$PYTHON" -m bootsig inspect "$ROOT/examples/baseline.jsonl")"
echo "$inspect_out" | grep -q '"score" (auto-detected, binary)' || fail "inspect missing metric line"
echo "$inspect_out" | grep -q "29 × 0.0, 71 × 1.0" || fail "inspect miscounted values"

# 8. mde reports what the eval can detect.
mde_out="$("$PYTHON" -m bootsig mde "$ROOT/examples/baseline.jsonl" "$ROOT/examples/candidate.jsonl")"
echo "$mde_out" | sed 's/^/[mde] /'
echo "$mde_out" | grep -q "minimum detectable difference at n=100: ±0.1378" \
  || fail "mde reported an unexpected sensitivity"

# 9. --version agrees with the package version.
version_out="$("$PYTHON" -m bootsig --version)"
pkg_version="$("$PYTHON" -c 'import bootsig; print(bootsig.__version__)')"
[ "$version_out" = "bootsig $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
