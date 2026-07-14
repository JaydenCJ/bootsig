"""End-to-end CLI tests: output text, JSON payloads, and exit codes.

The CLI is invoked in-process (``bootsig.cli.main``) so failures show real
tracebacks and no subprocess overhead creeps in; one test drives the real
``python -m bootsig`` entry point as a subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bootsig import __version__
from bootsig.cli import EXIT_ERROR, EXIT_GATE, EXIT_OK


def _significant_pair(scores_run):
    a = scores_run("a.jsonl", [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0])
    b = scores_run("b.jsonl", [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1])
    return a, b


def _noise_pair(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 0, 1, 0])
    b = scores_run("b.jsonl", [1, 0, 1, 1, 0, 0, 1, 0])
    return a, b


def test_version_via_flag_and_python_dash_m():
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "bootsig", "--version"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(root / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"bootsig {__version__}"


def test_no_command_prints_help_and_exits_2(run_cli):
    code, out, _ = run_cli()
    assert code == EXIT_ERROR
    assert "compare" in out and "inspect" in out and "mde" in out


def test_compare_report_contains_the_essentials(run_cli, scores_run):
    a, b = _noise_pair(scores_run)
    code, out, err = run_cli("compare", a, b, "--resamples", "500")
    assert code == EXIT_OK
    assert err == ""
    assert 'paired analysis of metric "score"' in out
    assert "permutation test" in out
    assert "verdict: NOT SIGNIFICANT" in out
    assert f"bootsig {__version__}" in out


def test_compare_json_payload_shape(run_cli, scores_run):
    a, b = _noise_pair(scores_run)
    code, out, _ = run_cli("compare", a, b, "--resamples", "500", "--json")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["design"] == "paired"
    assert payload["significant"] is False
    assert payload["seed"] == 42
    assert payload["a"]["n"] == 8
    assert isinstance(payload["difference"]["ci"], list)
    assert payload["gate"] == {"fail_on": "none", "tripped": False}


def test_significant_difference_gates_only_when_asked(run_cli, scores_run):
    a, b = _significant_pair(scores_run)
    code, out, _ = run_cli("compare", a, b, "--resamples", "2000")
    assert code == EXIT_OK  # informational by default
    assert "verdict: SIGNIFICANT" in out
    code, out, _ = run_cli("compare", a, b, "--resamples", "2000", "--fail-on", "difference")
    assert code == EXIT_GATE
    assert "gate: FAIL (--fail-on difference)" in out

    a2, b2 = _noise_pair(scores_run)
    code, _, _ = run_cli("compare", a2, b2, "--resamples", "500", "--fail-on", "difference")
    assert code == EXIT_OK  # noise never trips the gate


def test_fail_on_regression_distinguishes_gains_from_losses(run_cli, scores_run):
    a, b = _significant_pair(scores_run)
    code, out, _ = run_cli("compare", a, b, "--resamples", "2000", "--fail-on", "regression")
    assert code == EXIT_OK  # a significant *improvement* passes the gate
    assert "gate: pass (--fail-on regression)" in out

    code, out, _ = run_cli("compare", b, a, "--resamples", "2000", "--fail-on", "regression")
    assert code == EXIT_GATE  # swapped: the candidate is now the bad run
    assert "B is worse than A" in out


def test_fail_on_regression_respects_lower_is_better(run_cli, scores_run):
    a, b = _significant_pair(scores_run)  # metric went up...
    code, _, _ = run_cli(
        "compare", a, b, "--resamples", "2000", "--fail-on", "regression", "--lower-is-better"
    )
    assert code == EXIT_GATE  # ...but up is bad for a latency-style metric


def test_data_errors_are_single_stderr_lines_with_location(run_cli, tmp_path):
    code, out, err = run_cli("compare", str(tmp_path / "no.jsonl"), str(tmp_path / "pe.jsonl"))
    assert code == EXIT_ERROR
    assert out == ""
    assert err.startswith("bootsig: error: ")
    assert "Traceback" not in err

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a", "score": 1}\nnot json\n', encoding="utf-8")
    good = tmp_path / "good.jsonl"
    good.write_text('{"id": "a", "score": 1}\n', encoding="utf-8")
    code, _, err = run_cli("compare", str(bad), str(good))
    assert code == EXIT_ERROR
    assert "bad.jsonl:2" in err


def test_invalid_alpha_is_a_usage_error(run_cli, scores_run):
    a, b = _noise_pair(scores_run)
    code, _, err = run_cli("compare", a, b, "--alpha", "1.5")
    assert code == EXIT_ERROR
    assert "alpha" in err


def test_compare_unpaired_via_flag(run_cli, scores_run):
    a = scores_run("a.jsonl", [1, 0, 1], id_prefix="m")
    b = scores_run("b.jsonl", [1, 1, 0, 1], id_prefix="n")
    code, out, _ = run_cli("compare", a, b, "--unpaired", "--resamples", "500")
    assert code == EXIT_OK
    assert "unpaired analysis" in out
    assert "pairing" not in out


def test_inspect_binary_and_continuous_reports(run_cli, scores_run):
    binary = scores_run("bin.jsonl", [1, 0, 1, 1, 0, 1, 0, 1])
    code, out, _ = run_cli("inspect", binary, "--resamples", "500")
    assert code == EXIT_OK
    assert '"score" (auto-detected, binary)' in out
    assert "CI of the mean" in out
    assert "3 × 0.0, 5 × 1.0" in out

    cont = scores_run("cont.jsonl", [0.1, 0.4, 0.35, 0.8, 0.55, 0.62, 0.9, 0.15])
    code, out, _ = run_cli("inspect", cont, "--resamples", "500")
    assert code == EXIT_OK
    assert "histogram" in out and "median" in out


def test_inspect_json_payload(run_cli, scores_run):
    path = scores_run("run.jsonl", [1, 0, 1, 0])
    code, out, _ = run_cli("inspect", path, "--resamples", "500", "--json")
    payload = json.loads(out)
    assert code == EXIT_OK
    assert payload["n"] == 4
    assert payload["metric"] == {"key": "score", "auto": True, "binary": True}


def test_mde_human_reports_across_designs(run_cli, scores_run):
    single = scores_run("run.jsonl", [1, 0, 1, 1, 0, 1, 0, 1, 1, 1])
    code, out, _ = run_cli("mde", single)
    assert code == EXIT_OK
    assert "unpaired (one run of n=10" in out
    assert "minimum detectable difference" in out

    code, out, _ = run_cli("mde", single, "--target-diff", "0.05")
    assert code == EXIT_OK
    assert "to detect ±0.0500" in out

    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 1, 0, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 0, 0, 1, 1, 1])
    code, out, _ = run_cli("mde", a, b)
    assert code == EXIT_OK
    assert "paired (8 pairs" in out
    assert "needs n ≈" in out


def test_mde_json_payload_and_arity_check(run_cli, scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 1, 0, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 0, 0, 1, 1, 1])
    code, out, _ = run_cli("mde", a, b, "--json")
    payload = json.loads(out)
    assert code == EXIT_OK
    assert payload["design"] == "paired"
    assert payload["n"] == 8
    assert payload["mde"] > 0
    assert payload["required_n"] is not None

    code, _, err = run_cli("mde", a, a, b)
    assert code == EXIT_ERROR
    assert "one or two run files" in err
