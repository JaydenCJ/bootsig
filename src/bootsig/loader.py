"""Load eval runs from JSONL files into per-example metric series.

An eval run is a JSONL file: one JSON object per line, one line per example.
bootsig needs two things from every line — a numeric **metric** (the thing
being compared) and, ideally, a stable **id** (so two runs can be paired
example-by-example). Both are found via dotted key paths, either given
explicitly or auto-detected from a small list of conventional names.

Design decisions worth knowing:

- **Booleans count.** ``"correct": true`` is the most common eval output in
  the wild, so booleans coerce to 1.0/0.0.
- **Wrong types never pass silently.** A string or object where a number
  should be is always an error naming the file and line; ``missing="skip"``
  only forgives *absent or null* metrics, because those mean "no result",
  while a wrong type means "your pipeline is broken".
- **Duplicate ids are an error.** Pairing on ambiguous ids would silently
  compare the wrong examples, which is exactly the failure mode this tool
  exists to prevent.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional

from .errors import DataError, UsageError

#: Metric keys tried, in order, when ``--metric`` is not given.
METRIC_CANDIDATES = ("score", "correct", "passed", "accuracy", "value")

#: Id keys tried, in order, when ``--id`` is not given.
ID_CANDIDATES = ("id", "example_id", "task_id", "case_id", "name")

_MISSING = object()


@dataclass(frozen=True)
class Record:
    """One usable example: its source line, optional id, and metric value."""

    line_no: int
    id: Optional[str]
    value: float


@dataclass
class Run:
    """A parsed eval run: the records plus how they were interpreted."""

    path: str
    records: List[Record]
    metric_key: str
    metric_auto: bool
    id_key: Optional[str]
    id_auto: bool
    skipped: List[int] = field(default_factory=list)

    @property
    def values(self) -> List[float]:
        return [r.value for r in self.records]

    @property
    def n(self) -> int:
        return len(self.records)

    @property
    def has_ids(self) -> bool:
        return self.id_key is not None


def extract(obj: Any, dotted: str) -> Any:
    """Follow a dotted key path into nested dicts; ``_MISSING`` if absent."""
    current = obj
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def coerce_metric(value: Any) -> Optional[float]:
    """Turn a raw JSON value into a float metric.

    Returns ``None`` for null (the "no result" case that ``missing="skip"``
    may forgive) and raises ``ValueError`` for anything that is present but
    not a finite number or boolean.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            raise ValueError("value is NaN or infinite")
        return v
    raise ValueError(f"expected a number or boolean, got {type(value).__name__}")


def _detect_metric_key(first: dict, path: str, line_no: int) -> str:
    hits = [k for k in METRIC_CANDIDATES if k in first]
    if not hits:
        keys = ", ".join(sorted(first.keys())) or "(none)"
        raise DataError(
            "no metric key found (tried: "
            + ", ".join(METRIC_CANDIDATES)
            + f"); pass --metric. Top-level keys on this line: {keys}",
            path=path,
            line=line_no,
        )
    if len(hits) > 1:
        raise DataError(
            "ambiguous metric: this line has "
            + " and ".join(f'"{k}"' for k in hits)
            + "; pass --metric to choose one",
            path=path,
            line=line_no,
        )
    return hits[0]


def load_run(
    path: str,
    *,
    metric: Optional[str] = None,
    id_key: Optional[str] = None,
    missing: str = "error",
) -> Run:
    """Parse one JSONL eval run into a :class:`Run`.

    ``metric`` and ``id_key`` are dotted key paths; when ``None`` they are
    auto-detected from the first data line. ``missing`` controls what an
    absent/null metric does: ``"error"`` (default) fails loudly, ``"skip"``
    drops the line and records its line number in ``Run.skipped``.
    """
    if missing not in ("error", "skip"):
        raise UsageError(f'--missing must be "error" or "skip", got "{missing}"')
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise DataError(exc.strerror or str(exc), path=path)

    records: List[Record] = []
    skipped: List[int] = []
    chosen_metric = metric
    chosen_id = id_key
    metric_auto = metric is None
    id_auto = id_key is None
    first_seen = False
    ids_seen: "dict[str, int]" = {}

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DataError(f"invalid JSON ({exc.msg})", path=path, line=line_no)
        if not isinstance(obj, dict):
            raise DataError(
                f"expected one JSON object per line, got {type(obj).__name__}",
                path=path,
                line=line_no,
            )
        if not first_seen:
            first_seen = True
            if chosen_metric is None:
                chosen_metric = _detect_metric_key(obj, path, line_no)
            if chosen_id is None:
                id_hits = [k for k in ID_CANDIDATES if k in obj]
                chosen_id = id_hits[0] if id_hits else None

        raw_value = extract(obj, chosen_metric)
        if raw_value is _MISSING:
            raw_value = None
        try:
            value = coerce_metric(raw_value)
        except ValueError as exc:
            raise DataError(f'metric "{chosen_metric}": {exc}', path=path, line=line_no)
        if value is None:
            if missing == "skip":
                skipped.append(line_no)
                continue
            raise DataError(
                f'metric "{chosen_metric}" is missing or null '
                "(use --missing skip to drop such lines)",
                path=path,
                line=line_no,
            )

        record_id: Optional[str] = None
        if chosen_id is not None:
            raw_id = extract(obj, chosen_id)
            if raw_id is _MISSING or raw_id is None:
                raise DataError(
                    f'id key "{chosen_id}" is missing on this line '
                    "(every line needs an id once one is in use)",
                    path=path,
                    line=line_no,
                )
            if isinstance(raw_id, (dict, list)):
                raise DataError(
                    f'id key "{chosen_id}" must be a scalar, got {type(raw_id).__name__}',
                    path=path,
                    line=line_no,
                )
            record_id = str(raw_id)
            if record_id in ids_seen:
                raise DataError(
                    f'duplicate id "{record_id}" (first seen on line {ids_seen[record_id]}); '
                    "pairing on ambiguous ids would compare the wrong examples",
                    path=path,
                    line=line_no,
                )
            ids_seen[record_id] = line_no

        records.append(Record(line_no=line_no, id=record_id, value=value))

    if not records:
        detail = ""
        if skipped:
            noun = "line" if len(skipped) == 1 else "lines"
            detail = f" ({len(skipped)} {noun} skipped)"
        raise DataError("no usable records" + detail, path=path)
    assert chosen_metric is not None
    return Run(
        path=path,
        records=records,
        metric_key=chosen_metric,
        metric_auto=metric_auto,
        id_key=chosen_id,
        id_auto=id_auto,
        skipped=skipped,
    )
