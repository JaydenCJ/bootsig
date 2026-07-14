"""Tests for run pairing: matching rules and refusal to guess.

Silent misalignment is the deadliest failure a paired test can have, so
every ambiguous situation must raise ``PairingError`` with a fix hint.
"""

from __future__ import annotations

import pytest

from bootsig.errors import PairingError
from bootsig.loader import load_run
from bootsig.pairing import pair_runs


def test_pairs_match_on_ids_in_run_a_order_with_b_minus_a_diffs(write_run):
    a = write_run("a.jsonl", [{"id": "x", "score": 0.2}, {"id": "y", "score": 0.8}])
    b = write_run("b.jsonl", [{"id": "y", "score": 0.6}, {"id": "x", "score": 0.5}])
    paired = pair_runs(load_run(a), load_run(b))
    assert paired.ids == ["x", "y"]
    assert paired.a_values == [0.2, 0.8]
    assert paired.b_values == [0.5, 0.6]
    assert paired.diffs == pytest.approx([0.3, -0.2])
    assert paired.matched_on == 'id key "id"'


def test_unmatched_examples_are_counted_not_mixed_in(write_run):
    a = write_run("a.jsonl", [{"id": "x", "score": 1}, {"id": "only-a", "score": 0}])
    b = write_run(
        "b.jsonl",
        [{"id": "x", "score": 1}, {"id": "only-b1", "score": 0}, {"id": "only-b2", "score": 1}],
    )
    paired = pair_runs(load_run(a), load_run(b))
    assert paired.n == 1
    assert paired.unmatched_a == 1
    assert paired.unmatched_b == 2


def test_disjoint_ids_raise_with_hint(write_run):
    a = write_run("a.jsonl", [{"id": "p", "score": 1}])
    b = write_run("b.jsonl", [{"id": "q", "score": 1}])
    with pytest.raises(PairingError, match="no common ids.*--unpaired"):
        pair_runs(load_run(a), load_run(b))


def test_line_order_fallback_when_neither_run_has_ids(write_run):
    a = write_run("a.jsonl", [{"score": 1}, {"score": 0}])
    b = write_run("b.jsonl", [{"score": 0}, {"score": 0}])
    paired = pair_runs(load_run(a), load_run(b))
    assert paired.matched_on == "line order"
    assert paired.ids is None
    assert paired.n == 2


def test_refuses_to_guess_on_asymmetric_runs(write_run):
    short = write_run("short.jsonl", [{"score": 1}])
    long = write_run("long.jsonl", [{"score": 1}, {"score": 0}])
    with pytest.raises(PairingError, match="different lengths.*--unpaired"):
        pair_runs(load_run(long), load_run(short))

    with_ids = write_run("ids.jsonl", [{"id": "x", "score": 1}, {"id": "y", "score": 1}])
    with pytest.raises(PairingError, match="has an id key.*does not"):
        pair_runs(load_run(with_ids), load_run(long))


def test_line_order_after_skips_refuses_to_misalign(write_run):
    # If --missing skip dropped line 2 of run A only, "line 3 of A" would
    # silently pair with "line 2 of B". bootsig must refuse instead.
    a = write_run("a.jsonl", [{"score": 1}, {"score": None}, {"score": 0}])
    b = write_run("b.jsonl", [{"score": 1}, {"score": 1}, {"score": 0}])
    with pytest.raises(PairingError, match="skipped.*--unpaired"):
        pair_runs(load_run(a, missing="skip"), load_run(b, missing="skip"))


def test_different_id_keys_still_match_on_values(write_run):
    a = write_run("a.jsonl", [{"id": "x", "score": 1}])
    b = write_run("b.jsonl", [{"example_id": "x", "score": 0}, {"example_id": "y", "score": 1}])
    paired = pair_runs(load_run(a), load_run(b))
    assert paired.n == 1
    assert 'id"/"example_id' in paired.matched_on
