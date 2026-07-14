"""Tests for JSONL loading: key detection, coercion, and loud failures.

Loader errors are where users meet bootsig on a bad day, so every error
path asserts on the message content (file, line, and the suggested fix),
not just the exception type.
"""

from __future__ import annotations

import pytest

from bootsig.errors import DataError, UsageError
from bootsig.loader import load_run


def test_loads_values_and_ids_and_ignores_blank_lines(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text(
        '{"id": "a", "score": 0.5}\n\n   \n{"id": "b", "score": 1.0}\n', encoding="utf-8"
    )
    run = load_run(str(path))
    assert run.values == [0.5, 1.0]
    assert [r.id for r in run.records] == ["a", "b"]
    assert run.metric_key == "score" and run.metric_auto
    assert run.id_key == "id" and run.id_auto


def test_numbers_and_booleans_all_coerce_to_float(write_run):
    rows = [
        {"id": "a", "correct": True},
        {"id": "b", "correct": False},
        {"id": "c", "correct": 1},
        {"id": "d", "correct": 0.25},
    ]
    run = load_run(write_run("run.jsonl", rows))
    assert run.values == [1.0, 0.0, 1.0, 0.25]
    assert run.metric_key == "correct"


def test_dotted_metric_path_reaches_nested_values(write_run):
    rows = [{"id": "a", "metrics": {"exact_match": 0.4}}, {"id": "b", "metrics": {"exact_match": 0.9}}]
    run = load_run(write_run("run.jsonl", rows), metric="metrics.exact_match")
    assert run.values == [0.4, 0.9]
    assert run.metric_auto is False


def test_metric_detection_failures_explain_the_fix(write_run):
    ambiguous = write_run("amb.jsonl", [{"id": "a", "score": 1, "correct": True}])
    with pytest.raises(DataError, match="ambiguous metric.*--metric"):
        load_run(ambiguous)
    none_found = write_run("none.jsonl", [{"id": "a", "grade": 0.5}])
    with pytest.raises(DataError, match="no metric key found.*grade"):
        load_run(none_found)


def test_malformed_lines_report_the_line_number(tmp_path):
    bad_json = tmp_path / "bad.jsonl"
    bad_json.write_text('{"id": "a", "score": 1}\n{oops}\n', encoding="utf-8")
    with pytest.raises(DataError, match=r"bad\.jsonl:2: invalid JSON"):
        load_run(str(bad_json))
    non_object = tmp_path / "arr.jsonl"
    non_object.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(DataError, match="expected one JSON object per line, got list"):
        load_run(str(non_object))


def test_missing_metric_error_and_skip_policies(write_run):
    rows = [{"id": "a", "score": 1}, {"id": "b", "score": None}, {"id": "c", "score": 0}]
    path = write_run("run.jsonl", rows)
    with pytest.raises(DataError, match=r":2: .*missing or null.*--missing skip"):
        load_run(path)
    run = load_run(path, missing="skip")
    assert run.values == [1.0, 0.0]
    assert run.skipped == [2]


def test_wrong_type_and_nonfinite_metrics_error_even_with_skip(write_run):
    # A string where a number should be means the pipeline is broken;
    # silently skipping it would hide real corruption.
    wrong_type = write_run("t.jsonl", [{"id": "a", "score": "high"}])
    with pytest.raises(DataError, match="expected a number or boolean, got str"):
        load_run(wrong_type, missing="skip")
    nonfinite = write_run("n.jsonl", [{"id": "a", "score": float("nan")}])
    with pytest.raises(DataError, match="NaN or infinite"):
        load_run(nonfinite, missing="skip")


def test_duplicate_ids_error_names_both_lines(write_run):
    path = write_run("run.jsonl", [{"id": "a", "score": 1}, {"id": "a", "score": 0}])
    with pytest.raises(DataError, match=r'duplicate id "a" \(first seen on line 1\)'):
        load_run(path)


def test_id_key_rules_consistent_or_absent(write_run):
    # Once an id key is in use, a line without it is an error...
    partial = write_run("p.jsonl", [{"id": "a", "score": 1}, {"score": 0}])
    with pytest.raises(DataError, match=r':2: id key "id" is missing'):
        load_run(partial)
    # ...but a run with no id candidates at all loads fine, without ids.
    no_ids = write_run("q.jsonl", [{"score": 1}, {"score": 0}])
    run = load_run(no_ids)
    assert run.id_key is None and not run.has_ids


def test_unusable_files_and_policies_raise_clean_errors(tmp_path, write_run):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(DataError, match="no usable records"):
        load_run(str(empty))
    with pytest.raises(DataError):
        load_run(str(tmp_path / "nope.jsonl"))  # missing file, not raw OSError
    ok = write_run("ok.jsonl", [{"id": "a", "score": 1}])
    with pytest.raises(UsageError, match="--missing"):
        load_run(ok, missing="ignore")
