"""Tests for report formatting: number rendering, sparklines, JSON shape."""

from __future__ import annotations

import json

from bootsig.compare import compare_files
from bootsig.report import (
    comparison_to_dict,
    fmt_p,
    fmt_signed,
    render_comparison,
    sparkline,
)


def test_number_formatting_conventions():
    assert fmt_p(0.00003) == "p < 0.0001"  # never prints an impossible 0.0000
    assert fmt_p(0.0234) == "p = 0.0234"
    assert fmt_p(1.0) == "p = 1.0000"
    assert fmt_signed(0.02) == "+0.0200"  # differences always carry a sign
    assert fmt_signed(-0.02) == "-0.0200"
    assert fmt_signed(0.0) == "+0.0000"


def test_sparkline_deterministic_fixed_width_and_degenerate():
    values = [0.0, 0.1, 0.1, 0.2, 0.5, 0.5, 0.5, 0.9, 1.0, 1.0]
    line = sparkline(values, bins=10)
    assert len(line) == 10
    assert line == sparkline(values, bins=10)
    assert sparkline([0.7, 0.7, 0.7]) == "█"


def test_render_includes_pairing_note_and_reproducibility_footer(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 0, 0, 1])
    text = render_comparison(compare_files(a, b, resamples=300, seed=5), "0.1.0")
    assert 'pairs matched on id key "id"' in text
    assert "seed 5 · bca bootstrap, 300 resamples · bootsig 0.1.0" in text


def test_render_marks_exact_permutation_tests(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0, 1, 1])
    b = scores_run("b.jsonl", [1, 1, 1, 0, 0, 1])
    # Only 2 nonzero diffs -> the sign-flip space (4) is enumerated exactly.
    text = render_comparison(compare_files(a, b, resamples=300, seed=5), "0.1.0")
    assert "exact over 4 permutations" in text


def test_singular_counts_render_without_stray_plurals(scores_run):
    # One discordant pair and a two-permutation space: both counts must
    # pluralize correctly ("1 discordant pair", never "1 discordant pairs").
    a = scores_run("a.jsonl", [1, 1, 0])
    b = scores_run("b.jsonl", [1, 0, 0])
    text = render_comparison(compare_files(a, b, resamples=300), "0.1.0")
    assert "(1 discordant pair)" in text
    assert "exact over 2 permutations" in text

    # Identical runs collapse the sign-flip space to the single identity
    # assignment — the report must say "1 permutation".
    same = render_comparison(compare_files(a, a, resamples=300), "0.1.0")
    assert "exact over 1 permutation" in same
    assert "(0 discordant pairs)" in same


def test_json_dict_dumps_cleanly_with_stable_content(scores_run):
    a = scores_run("a.jsonl", [1, 0, 1, 0])
    b = scores_run("b.jsonl", [0, 1, 1, 0])
    payload = comparison_to_dict(compare_files(a, b, resamples=200), "0.1.0")
    dumped = json.dumps(payload, sort_keys=True)
    assert json.loads(dumped) == payload
    assert payload["mcnemar"]["n01"] == 1
    assert payload["pairs"]["ties"] == 2


def test_verdict_wording_matches_significance(scores_run):
    a = scores_run("a.jsonl", [0] * 20)
    b = scores_run("b.jsonl", [1] * 20)
    sig = render_comparison(compare_files(a, b, resamples=1000), "0.1.0")
    assert "verdict: SIGNIFICANT" in sig
    assert "B improves on A" in sig

    a2 = scores_run("a2.jsonl", [1, 0, 1, 0])
    b2 = scores_run("b2.jsonl", [0, 1, 1, 0])
    not_sig = render_comparison(compare_files(a2, b2, resamples=200), "0.1.0")
    assert "verdict: NOT SIGNIFICANT" in not_sig
    assert "within noise" in not_sig
