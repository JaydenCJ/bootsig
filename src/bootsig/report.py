"""Turn comparison results into terminal reports and machine-readable JSON.

The human report is designed to be pasted into a PR: every number needed to
reproduce it (seed, resamples, CI method, version) is on the footer line,
and the verdict line states the decision in plain language instead of
leaving the reader to interpret a p-value. The JSON form is the same data
with sorted keys, so diffs of saved reports stay stable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .compare import Comparison
from .stats import describe

SPARK_LEVELS = "▁▂▃▄▅▆▇█"


def fmt_num(x: float, decimals: int = 4) -> str:
    return f"{x:.{decimals}f}"


def fmt_signed(x: float, decimals: int = 4) -> str:
    return f"{x:+.{decimals}f}"


def fmt_p(p: float) -> str:
    """p-values below display precision render as a bound, never as 0.0000."""
    if p < 0.0001:
        return "p < 0.0001"
    return f"p = {p:.4f}"


def sparkline(values: Sequence[float], bins: int = 10) -> str:
    """Fixed-width unicode histogram of a value distribution."""
    lo, hi = min(values), max(values)
    if lo == hi:
        return SPARK_LEVELS[-1]
    counts = [0] * bins
    span = hi - lo
    for v in values:
        idx = min(int((v - lo) / span * bins), bins - 1)
        counts[idx] += 1
    peak = max(counts)
    chars = []
    for c in counts:
        level = 0 if c == 0 else 1 + round((c / peak) * (len(SPARK_LEVELS) - 2))
        chars.append(SPARK_LEVELS[min(level, len(SPARK_LEVELS) - 1)])
    return "".join(chars)


def _ci_str(lo: float, hi: float) -> str:
    return f"[{fmt_num(lo)}, {fmt_num(hi)}]"


def _ci_str_signed(lo: float, hi: float) -> str:
    return f"[{fmt_signed(lo)}, {fmt_signed(hi)}]"


def _plural(n: int, noun: str) -> str:
    """``1 pair`` / ``2 pairs`` — tiny helper so counts never read oddly."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _perm_detail(cmp: Comparison) -> str:
    if cmp.permutation.exact:
        detail = _plural(cmp.permutation.resamples, "permutation")
        return f"{cmp.permutation.method}, exact over {detail}"
    return f"{cmp.permutation.method}, {cmp.permutation.resamples} resamples"


def _verdict_line(cmp: Comparison) -> str:
    n_note = f"n={cmp.pairs}" if cmp.design == "paired" else f"n={cmp.a.n}+{cmp.b.n}"
    if cmp.significant:
        what = "B improves on A" if cmp.direction == "improvement" else "B is worse than A"
        if cmp.direction == "no change":  # significant but zero diff cannot happen, keep safe
            what = "the runs differ"
        return (
            f"verdict: SIGNIFICANT at alpha = {cmp.alpha:g} — {what} by "
            f"{fmt_signed(cmp.diff_mean)} ({fmt_p(cmp.permutation.p_value)})"
        )
    return (
        f"verdict: NOT SIGNIFICANT at alpha = {cmp.alpha:g} ({fmt_p(cmp.permutation.p_value)}) — "
        f"a {fmt_signed(cmp.diff_mean)} difference at {n_note} is within noise"
    )


def render_comparison(cmp: Comparison, version: str) -> str:
    """The human-readable ``bootsig compare`` report."""
    label = "paired" if cmp.design == "paired" else "unpaired"
    width = max(len(cmp.a.path), len(cmp.b.path))
    lines = [f'bootsig compare — {label} analysis of metric "{cmp.metric_key}"', ""]
    for tag, rs in (("A", cmp.a), ("B", cmp.b)):
        lines.append(
            f"  {tag}  {rs.path.ljust(width)}   n={rs.n}   mean {fmt_num(rs.mean)}   "
            f"{100 * (1 - cmp.alpha):g}% CI {_ci_str(rs.ci.lo, rs.ci.hi)}"
        )
    lines.append("")
    if cmp.design == "paired":
        unmatched = (cmp.unmatched_a or 0) + (cmp.unmatched_b or 0)
        lines.append(
            f"  pairing              {cmp.pairs} pairs matched on {cmp.matched_on} "
            f"({unmatched} unmatched)"
        )
        lines.append(
            f"  wins / losses / ties {cmp.wins} / {cmp.losses} / {cmp.ties}   "
            "(B better / A better / tied)"
        )
        lines.append("")
    rel = f"   ({fmt_signed(100 * cmp.relative, 1)}% relative)" if cmp.relative is not None else ""
    lines.append(
        f"  difference (B - A)   {fmt_signed(cmp.diff_mean)}   "
        f"{100 * (1 - cmp.alpha):g}% CI {_ci_str_signed(cmp.diff_ci.lo, cmp.diff_ci.hi)}{rel}"
    )
    lines.append(
        f"  permutation test     {fmt_p(cmp.permutation.p_value)}   ({_perm_detail(cmp)})"
    )
    if cmp.mcnemar is not None:
        lines.append(
            f"  exact McNemar        {fmt_p(cmp.mcnemar.p_value)}   "
            f"({_plural(cmp.mcnemar.n01 + cmp.mcnemar.n10, 'discordant pair')})"
        )
    if cmp.cohens_d is not None:
        lines.append(f"  effect size          Cohen's d = {cmp.cohens_d:.2f} ({cmp.design})")
    lines.append("")
    lines.append(f"  {_verdict_line(cmp)}")
    lines.append("")
    lines.append(
        f"  seed {cmp.seed} · {cmp.ci_method} bootstrap, {cmp.resamples} resamples · bootsig {version}"
    )
    return "\n".join(lines)


def comparison_to_dict(cmp: Comparison, version: str) -> Dict[str, Any]:
    """The ``--json`` form of a comparison; keys sorted at dump time."""
    def run_dict(rs: Any) -> Dict[str, Any]:
        return {
            "path": rs.path,
            "n": rs.n,
            "mean": rs.mean,
            "sd": rs.sd,
            "ci": [rs.ci.lo, rs.ci.hi],
        }

    pairs: Optional[Dict[str, Any]] = None
    if cmp.design == "paired":
        pairs = {
            "n": cmp.pairs,
            "matched_on": cmp.matched_on,
            "unmatched_a": cmp.unmatched_a,
            "unmatched_b": cmp.unmatched_b,
            "wins": cmp.wins,
            "losses": cmp.losses,
            "ties": cmp.ties,
        }
    mcnemar: Optional[Dict[str, Any]] = None
    if cmp.mcnemar is not None:
        mcnemar = {"n01": cmp.mcnemar.n01, "n10": cmp.mcnemar.n10, "p_value": cmp.mcnemar.p_value}
    return {
        "version": version,
        "design": cmp.design,
        "metric": cmp.metric_key,
        "alpha": cmp.alpha,
        "ci_method": cmp.ci_method,
        "resamples": cmp.resamples,
        "seed": cmp.seed,
        "a": run_dict(cmp.a),
        "b": run_dict(cmp.b),
        "difference": {
            "mean": cmp.diff_mean,
            "ci": [cmp.diff_ci.lo, cmp.diff_ci.hi],
            "relative": cmp.relative,
            "direction": cmp.direction,
            "cohens_d": cmp.cohens_d,
            "lower_is_better": cmp.lower_is_better,
        },
        "permutation": {
            "p_value": cmp.permutation.p_value,
            "method": cmp.permutation.method,
            "resamples": cmp.permutation.resamples,
            "exact": cmp.permutation.exact,
        },
        "mcnemar": mcnemar,
        "pairs": pairs,
        "skipped": {"a": cmp.skipped_a, "b": cmp.skipped_b},
        "significant": cmp.significant,
    }


def render_inspect(
    path: str,
    values: Sequence[float],
    metric_key: str,
    metric_auto: bool,
    id_key: Optional[str],
    id_auto: bool,
    skipped: int,
    ci: Any,
    version: str,
) -> str:
    """The human-readable ``bootsig inspect`` report."""
    d = describe(values)
    kind = "binary" if d["binary"] else "continuous"
    detected = "auto-detected" if metric_auto else "given"
    lines = [f"bootsig inspect — {path}", ""]
    lines.append(f"  records   {d['n']} parsed, {skipped} skipped")
    lines.append(f'  metric    "{metric_key}" ({detected}, {kind})')
    if id_key is not None:
        lines.append(f'  id key    "{id_key}" ({"auto-detected" if id_auto else "given"})')
    else:
        lines.append("  id key    none found — compare will pair by line order")
    lines.append("")
    lines.append(
        f"  mean {fmt_num(d['mean'])}   sd {fmt_num(d['sd'])}   "
        f"min {fmt_num(d['min'])}   max {fmt_num(d['max'])}"
    )
    lines.append(
        f"  {100 * (1 - ci.alpha):g}% CI of the mean {_ci_str(ci.lo, ci.hi)}   "
        f"({ci.method} bootstrap, {ci.resamples} resamples)"
    )
    if d["binary"]:
        ones = sum(1 for v in values if v == 1.0)
        lines.append(f"  values    {len(values) - ones} × 0.0, {ones} × 1.0")
    else:
        lines.append(
            f"  p25 {fmt_num(d['p25'])}   median {fmt_num(d['median'])}   p75 {fmt_num(d['p75'])}"
        )
        lines.append(
            f"  histogram {sparkline(values)}   (10 bins, {fmt_num(d['min'])} → {fmt_num(d['max'])})"
        )
    lines.append("")
    lines.append(f"  bootsig {version}")
    return "\n".join(lines)


def inspect_to_dict(
    path: str,
    values: Sequence[float],
    metric_key: str,
    metric_auto: bool,
    id_key: Optional[str],
    id_auto: bool,
    skipped: int,
    ci: Any,
    version: str,
) -> Dict[str, Any]:
    d = describe(values)
    return {
        "version": version,
        "path": path,
        "n": d["n"],
        "skipped": skipped,
        "metric": {"key": metric_key, "auto": metric_auto, "binary": d["binary"]},
        "id_key": {"key": id_key, "auto": id_auto} if id_key is not None else None,
        "mean": d["mean"],
        "sd": d["sd"],
        "min": d["min"],
        "max": d["max"],
        "p25": d["p25"],
        "median": d["median"],
        "p75": d["p75"],
        "distinct": d["distinct"],
        "ci": [ci.lo, ci.hi],
        "ci_method": ci.method,
        "resamples": ci.resamples,
        "alpha": ci.alpha,
    }


def render_mde(info: Dict[str, Any], version: str) -> str:
    """The human-readable ``bootsig mde`` report; ``info`` from cli._mde_info."""
    lines = ["bootsig mde — what can this eval detect?", ""]
    lines.append(f"  design    {info['design_note']}")
    lines.append(f"  spread    {info['spread_note']} = {fmt_num(info['sd'])}")
    lines.append(
        f"  test      two-sided alpha {info['alpha']:g}, power {info['power']:g}"
    )
    lines.append("")
    lines.append(
        f"  minimum detectable difference at n={info['n']}: ±{fmt_num(info['mde'])}"
    )
    lines.append(
        f"  → real differences smaller than ±{fmt_num(info['mde'])} will usually go undetected."
    )
    if info.get("target_diff") is not None:
        unit = "pairs" if info["design"] == "paired" else "examples per run"
        target = info["target_diff"]
        if info["target_from_data"]:
            lines.append("")
            lines.append(
                f"  observed difference is {fmt_signed(target)}; detecting a true difference "
                f"of that size needs n ≈ {info['required_n']} {unit}."
            )
        else:
            lines.append("")
            lines.append(
                f"  to detect ±{fmt_num(abs(target))} you would need n ≈ {info['required_n']} {unit}."
            )
    lines.append("")
    lines.append(f"  bootsig {version}")
    return "\n".join(lines)


def mde_to_dict(info: Dict[str, Any], version: str) -> Dict[str, Any]:
    return {
        "version": version,
        "design": info["design"],
        "n": info["n"],
        "sd": info["sd"],
        "alpha": info["alpha"],
        "power": info["power"],
        "mde": info["mde"],
        "target_diff": info.get("target_diff"),
        "target_from_data": info.get("target_from_data", False),
        "required_n": info.get("required_n"),
        "paths": info["paths"],
        "metric": info["metric"],
    }
