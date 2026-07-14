"""The README quickstart, executed verbatim against the committed examples.

If these fail, the README is lying — keep code and docs in sync.
"""

from __future__ import annotations

from bootsig.cli import main


def test_readme_quickstart_noise_verdict(capsys, examples_dir):
    code = main(
        ["compare", str(examples_dir / "baseline.jsonl"), str(examples_dir / "candidate.jsonl")]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "mean 0.7100" in out
    assert "mean 0.7300" in out
    assert "wins / losses / ties 13 / 11 / 76" in out
    assert "p = 0.8375" in out
    assert "verdict: NOT SIGNIFICANT at alpha = 0.05" in out


def test_readme_quickstart_real_improvement_verdict(capsys, examples_dir):
    code = main(
        ["compare", str(examples_dir / "baseline.jsonl"), str(examples_dir / "improved.jsonl")]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "mean 0.8400" in out
    assert "verdict: SIGNIFICANT at alpha = 0.05" in out
    assert "+0.1300" in out


def test_readme_mde_numbers(capsys, examples_dir):
    code = main(
        ["mde", str(examples_dir / "baseline.jsonl"), str(examples_dir / "candidate.jsonl")]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "minimum detectable difference at n=100: ±0.1378" in out
