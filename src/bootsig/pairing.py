"""Align two eval runs example-by-example for paired analysis.

Paired tests are dramatically more sensitive than unpaired ones — the same
hard example drags both runs down, and pairing cancels that shared noise —
so bootsig tries hard to pair and refuses to guess when it cannot do so
safely:

- If **both** runs carry ids, pairs are matched on id values (in the order
  they appear in run A). Unmatched examples are counted and reported, never
  silently mixed in.
- If **neither** run has ids, equal-length runs are paired by line order.
  This is only sound when nothing was skipped, so ``--missing skip`` plus
  line-order pairing is an error rather than a silent misalignment.
- If exactly **one** run has ids, that is a data problem the user must
  resolve; guessing here is how wrong conclusions get shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .errors import PairingError
from .loader import Run


@dataclass
class PairedRuns:
    """Two runs reduced to matched value vectors plus bookkeeping."""

    ids: Optional[List[str]]
    a_values: List[float]
    b_values: List[float]
    matched_on: str
    unmatched_a: int
    unmatched_b: int

    @property
    def n(self) -> int:
        return len(self.a_values)

    @property
    def diffs(self) -> List[float]:
        """Per-example differences, run B minus run A."""
        return [b - a for a, b in zip(self.a_values, self.b_values)]


def pair_runs(run_a: Run, run_b: Run) -> PairedRuns:
    """Pair two loaded runs, or raise :class:`PairingError` with a fix hint."""
    if run_a.has_ids and run_b.has_ids:
        return _pair_on_ids(run_a, run_b)
    if run_a.has_ids != run_b.has_ids:
        with_ids = run_a if run_a.has_ids else run_b
        without = run_b if run_a.has_ids else run_a
        raise PairingError(
            f'{with_ids.path} has an id key ("{with_ids.id_key}") but {without.path} '
            "does not; add ids to both runs, pass --id, or use --unpaired"
        )
    return _pair_on_line_order(run_a, run_b)


def _pair_on_ids(run_a: Run, run_b: Run) -> PairedRuns:
    b_by_id = {r.id: r.value for r in run_b.records}
    ids: List[str] = []
    a_values: List[float] = []
    b_values: List[float] = []
    for record in run_a.records:
        assert record.id is not None
        if record.id in b_by_id:
            ids.append(record.id)
            a_values.append(record.value)
            b_values.append(b_by_id[record.id])
    if not ids:
        raise PairingError(
            f'no common ids between {run_a.path} (id key "{run_a.id_key}") and '
            f'{run_b.path} (id key "{run_b.id_key}"); pass --id to pick the right '
            "key, or use --unpaired"
        )
    if run_a.id_key == run_b.id_key:
        matched_on = f'id key "{run_a.id_key}"'
    else:
        matched_on = f'id keys "{run_a.id_key}"/"{run_b.id_key}"'
    return PairedRuns(
        ids=ids,
        a_values=a_values,
        b_values=b_values,
        matched_on=matched_on,
        unmatched_a=run_a.n - len(ids),
        unmatched_b=run_b.n - len(ids),
    )


def _pair_on_line_order(run_a: Run, run_b: Run) -> PairedRuns:
    if run_a.skipped or run_b.skipped:
        raise PairingError(
            "cannot pair by line order when lines were skipped (--missing skip); "
            "the remaining lines may no longer align — add an id key or use --unpaired"
        )
    if run_a.n != run_b.n:
        raise PairingError(
            f"runs have different lengths ({run_a.n} vs {run_b.n}) and no id key; "
            "add ids so examples can be matched, or use --unpaired"
        )
    return PairedRuns(
        ids=None,
        a_values=run_a.values,
        b_values=run_b.values,
        matched_on="line order",
        unmatched_a=0,
        unmatched_b=0,
    )
