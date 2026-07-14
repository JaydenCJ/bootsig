"""Shared fixtures: tiny factories for writing JSONL runs and driving the CLI.

All tests run fully offline with fixed seeds; nothing here touches the
network or the wall clock.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bootsig.cli import main


@pytest.fixture
def write_run(tmp_path):
    """Write a JSONL run file from a list of dicts; returns its path as str."""

    def _write(name, rows):
        path = tmp_path / name
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        return str(path)

    return _write


@pytest.fixture
def scores_run(write_run):
    """Write a run of ``{"id": ..., "score": ...}`` rows from a value list."""

    def _write(name, values, id_prefix="ex"):
        rows = [
            {"id": f"{id_prefix}-{i:03d}", "score": v} for i, v in enumerate(values, start=1)
        ]
        return write_run(name, rows)

    return _write


@pytest.fixture
def run_cli(capsys):
    """Invoke the CLI in-process; returns (exit_code, stdout, stderr)."""

    def _run(*argv):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def examples_dir():
    """Path to the committed example runs used by the README and smoke test."""
    return Path(__file__).resolve().parent.parent / "examples"
