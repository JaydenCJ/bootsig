"""Command line interface: ``compare``, ``inspect``, and ``mde``.

Exit codes follow ``diff(1)`` conventions so the tool slots into CI:

- ``0`` — ran fine (and, with ``--fail-on``, the gate did not trip)
- ``1`` — a ``--fail-on`` gate tripped (significant difference/regression)
- ``2`` — usage error or unreadable/invalid data

Expected failures print one readable line to stderr, never a traceback.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from statistics import fmean
from typing import Any, Dict, List, Optional

from . import __version__
from .bootstrap import bootstrap_mean
from .compare import Comparison, compare_files
from .errors import BootsigError, DataError, UsageError
from .loader import load_run
from .pairing import pair_runs
from .power import mde as compute_mde
from .power import required_n
from .report import (
    comparison_to_dict,
    inspect_to_dict,
    mde_to_dict,
    render_comparison,
    render_inspect,
    render_mde,
)
from .stats import sample_sd

EXIT_OK = 0
EXIT_GATE = 1
EXIT_ERROR = 2


def _add_data_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--metric",
        metavar="KEY",
        help="dotted key path to the metric (default: auto-detect score/correct/passed/accuracy/value)",
    )
    parser.add_argument(
        "--missing",
        choices=("error", "skip"),
        default="error",
        help="what to do when the metric is absent or null on a line (default: error)",
    )


def _add_sampling_options(parser: argparse.ArgumentParser, *, permutes: bool = True) -> None:
    if permutes:
        resamples_help = (
            "bootstrap/permutation resamples; the permutation test is exact "
            "when the full space fits (default: 10000)"
        )
    else:
        resamples_help = "bootstrap resamples (default: 10000)"
    parser.add_argument(
        "--resamples",
        type=int,
        default=10000,
        metavar="N",
        help=resamples_help,
    )
    parser.add_argument("--seed", type=int, default=42, metavar="N", help="RNG seed (default: 42)")
    parser.add_argument(
        "--alpha", type=float, default=0.05, metavar="A", help="significance level (default: 0.05)"
    )
    parser.add_argument(
        "--ci-method",
        choices=("bca", "percentile"),
        default="bca",
        help="bootstrap interval method (default: bca)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootsig",
        description=(
            "Tells you whether two eval runs actually differ: bootstrap confidence "
            "intervals and permutation tests over JSONL result files."
        ),
    )
    parser.add_argument("--version", action="version", version=f"bootsig {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_cmp = sub.add_parser(
        "compare",
        help="test whether two runs differ: CIs, permutation p-value, verdict",
    )
    p_cmp.add_argument("run_a", help="baseline run (JSONL)")
    p_cmp.add_argument("run_b", help="candidate run (JSONL)")
    _add_data_options(p_cmp)
    p_cmp.add_argument(
        "--id",
        dest="id_key",
        metavar="KEY",
        help="dotted key path to the example id (default: auto-detect id/example_id/task_id/case_id/name)",
    )
    p_cmp.add_argument(
        "--unpaired",
        action="store_true",
        help="treat the runs as independent samples instead of pairing examples",
    )
    _add_sampling_options(p_cmp)
    p_cmp.add_argument(
        "--lower-is-better",
        action="store_true",
        help="the metric is a cost (latency, loss): lower values are improvements",
    )
    p_cmp.add_argument(
        "--fail-on",
        choices=("none", "regression", "difference"),
        default="none",
        help="exit 1 when B is significantly worse (regression) or significantly different (difference)",
    )
    p_cmp.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    p_ins = sub.add_parser("inspect", help="summarize one run: n, mean, spread, CI of the mean")
    p_ins.add_argument("run", help="run file (JSONL)")
    _add_data_options(p_ins)
    _add_sampling_options(p_ins, permutes=False)
    p_ins.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    p_mde = sub.add_parser(
        "mde",
        help="minimum detectable effect: what difference can this eval even see?",
    )
    p_mde.add_argument("runs", nargs="+", metavar="run", help="one or two run files (JSONL)")
    _add_data_options(p_mde)
    p_mde.add_argument(
        "--id",
        dest="id_key",
        metavar="KEY",
        help="dotted key path to the example id (used to pair two runs)",
    )
    p_mde.add_argument(
        "--unpaired",
        action="store_true",
        help="assume independent runs even when two files are given",
    )
    p_mde.add_argument(
        "--alpha", type=float, default=0.05, metavar="A", help="significance level (default: 0.05)"
    )
    p_mde.add_argument(
        "--power",
        type=float,
        default=0.8,
        metavar="P",
        help="probability of detecting a true difference of the reported size (default: 0.8)",
    )
    p_mde.add_argument(
        "--target-diff",
        type=float,
        metavar="D",
        help="also report the n needed to detect this difference (default with two runs: the observed difference)",
    )
    p_mde.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _gate_exit(cmp: Comparison, fail_on: str) -> int:
    if fail_on == "none" or not cmp.significant:
        return EXIT_OK
    if fail_on == "difference":
        return EXIT_GATE
    return EXIT_GATE if cmp.direction == "regression" else EXIT_OK


def _cmd_compare(args: argparse.Namespace) -> int:
    cmp = compare_files(
        args.run_a,
        args.run_b,
        metric=args.metric,
        id_key=args.id_key,
        unpaired=args.unpaired,
        resamples=args.resamples,
        seed=args.seed,
        alpha=args.alpha,
        ci_method=args.ci_method,
        missing=args.missing,
        lower_is_better=args.lower_is_better,
    )
    exit_code = _gate_exit(cmp, args.fail_on)
    if args.json:
        payload = comparison_to_dict(cmp, __version__)
        payload["gate"] = {"fail_on": args.fail_on, "tripped": exit_code == EXIT_GATE}
        print(json.dumps(payload, sort_keys=True, indent=2))
    else:
        print(render_comparison(cmp, __version__))
        if args.fail_on != "none":
            state = "FAIL" if exit_code == EXIT_GATE else "pass"
            print(f"\n  gate: {state} (--fail-on {args.fail_on})")
    return exit_code


def _cmd_inspect(args: argparse.Namespace) -> int:
    run = load_run(args.run, metric=args.metric, missing=args.missing)
    if run.n < 2:
        raise DataError("need at least 2 records to summarize a run", path=args.run)
    ci = bootstrap_mean(
        run.values, resamples=args.resamples, seed=args.seed, alpha=args.alpha, method=args.ci_method
    )
    fields = (
        args.run,
        run.values,
        run.metric_key,
        run.metric_auto,
        run.id_key,
        run.id_auto,
        len(run.skipped),
        ci,
    )
    if args.json:
        print(json.dumps(inspect_to_dict(*fields, __version__), sort_keys=True, indent=2))
    else:
        print(render_inspect(*fields, __version__))
    return EXIT_OK


def _mde_info(args: argparse.Namespace) -> Dict[str, Any]:
    if len(args.runs) > 2:
        raise UsageError(f"mde takes one or two run files, got {len(args.runs)}")
    observed_diff: Optional[float] = None
    if len(args.runs) == 1:
        run = load_run(args.runs[0], metric=args.metric, missing=args.missing)
        if run.n < 2:
            raise DataError("need at least 2 records for an mde estimate", path=run.path)
        design = "unpaired"
        sd = sample_sd(run.values)
        n = run.n
        metric = run.metric_key
        design_note = (
            f"unpaired (one run of n={n}; assumes a second independent run with similar spread)"
        )
        spread_note = "per-example sd"
    else:
        run_a = load_run(args.runs[0], metric=args.metric, id_key=args.id_key, missing=args.missing)
        run_b = load_run(
            args.runs[1], metric=run_a.metric_key, id_key=args.id_key, missing=args.missing
        )
        metric = run_a.metric_key
        if args.unpaired:
            design = "unpaired"
            sd = math.sqrt((sample_sd(run_a.values) ** 2 + sample_sd(run_b.values) ** 2) / 2.0)
            n = min(run_a.n, run_b.n)
            observed_diff = fmean(run_b.values) - fmean(run_a.values)
            design_note = f"unpaired (two independent runs, n={run_a.n} and n={run_b.n})"
            spread_note = "pooled per-example sd"
        else:
            paired = pair_runs(run_a, run_b)
            if paired.n < 2:
                raise DataError("need at least 2 pairs for an mde estimate", path=run_a.path)
            design = "paired"
            diffs = paired.diffs
            sd = sample_sd(diffs)
            n = paired.n
            observed_diff = fmean(diffs)
            design_note = f'paired ({n} pairs of "{metric}", matched on {paired.matched_on})'
            spread_note = "sd of per-example difference"

    value = compute_mde(sd, n, alpha=args.alpha, power=args.power, design=design)
    info: Dict[str, Any] = {
        "design": design,
        "design_note": design_note,
        "spread_note": spread_note,
        "sd": sd,
        "n": n,
        "alpha": args.alpha,
        "power": args.power,
        "mde": value,
        "paths": list(args.runs),
        "metric": metric,
        "target_from_data": False,
    }
    target = args.target_diff
    if target is None and observed_diff is not None and observed_diff != 0.0:
        target = observed_diff
        info["target_from_data"] = True
    if target is not None:
        info["target_diff"] = target
        info["required_n"] = required_n(
            sd, abs(target), alpha=args.alpha, power=args.power, design=design
        )
    return info


def _cmd_mde(args: argparse.Namespace) -> int:
    info = _mde_info(args)
    if args.json:
        print(json.dumps(mde_to_dict(info, __version__), sort_keys=True, indent=2))
    else:
        print(render_mde(info, __version__))
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_ERROR
    try:
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "mde":
            return _cmd_mde(args)
        raise UsageError(f"unknown command {args.command!r}")
    except BootsigError as exc:
        print(f"bootsig: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"bootsig: error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    sys.exit(main())
