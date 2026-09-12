"""Separation-distance slices for the reconstructed-energy panel.

The default edges are the notebook's, converted from centimetres: 50, 100, 150
and 200 mm. Measured against the data those cover the genuine overlap regime -
per-event D has a p25 of 93 mm and a median of 175 mm - so the four slices hold
roughly 53% of events between them.

A **fifth overflow slice** is appended for everything at or beyond the last edge.
The per-event D distribution is strongly bimodal: a tight cluster below ~200 mm,
then a sparse middle, then a broad well-separated population out to 5308 mm (p75
is 1995 mm). Without the overflow slice, about 47% of events would silently
vanish from the panel. Keeping it means the well-separated population is visible
as what it is - the reference against which the overlapping cases are read.

Note on ``calodash/constants.py``: its ``D_BINS_MM = (0, 50, 100, 150, 200)``
came from reading the notebook's centimetre values as millimetres. The numbers
happen to be right for the overlap regime, but the derivation was not, and its
upper edge of 200 mm silently discards the well-separated majority. That module
is not imported here for exactly this reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from ..errors import ValidationError

#: Slice boundaries in millimetres, from the reference notebook.
DEFAULT_EDGES: tuple[float, ...] = (50.0, 100.0, 150.0, 200.0)

MAX_SLICES = 8


@dataclass(frozen=True)
class Slice:
    index: int
    label: str
    lo: float
    hi: float | None  # None for the unbounded overflow slice

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "lo": self.lo,
            "hi": self.hi,
        }


def _format_mm(value: float) -> str:
    return f"{value:g}"


def build_slices(edges: Sequence[float] = DEFAULT_EDGES) -> list[Slice]:
    """Turn a list of upper edges into labelled, contiguous slices."""
    cleaned = sorted({float(e) for e in edges if np.isfinite(e) and e > 0})
    if not cleaned:
        raise ValidationError(
            "At least one positive separation-distance edge is required.",
            field="d_edges",
        )
    if len(cleaned) >= MAX_SLICES:
        raise ValidationError(
            f"At most {MAX_SLICES - 1} separation edges are supported; "
            f"got {len(cleaned)}.",
            field="d_edges",
        )

    slices: list[Slice] = []
    lo = 0.0
    for index, hi in enumerate(cleaned):
        slices.append(
            Slice(
                index=index,
                label=f"D < {_format_mm(hi)} mm" if index == 0
                else f"{_format_mm(lo)} ≤ D < {_format_mm(hi)} mm",
                lo=lo,
                hi=hi,
            )
        )
        lo = hi

    slices.append(
        Slice(
            index=len(cleaned),
            label=f"D ≥ {_format_mm(lo)} mm (well separated)",
            lo=lo,
            hi=None,
        )
    )
    return slices


def case_sql(slices: Sequence[Slice], column: str = "d") -> str:
    """A ``CASE`` expression assigning each row to its slice index."""
    branches = [
        f"WHEN {column} < {s.hi} THEN {s.index}"
        for s in slices
        if s.hi is not None
    ]
    overflow = slices[-1].index
    return "CASE " + " ".join(branches) + f" ELSE {overflow} END"


def parse_edges(raw: str | None) -> tuple[float, ...]:
    """Parse a ``d_edges=50,100,150,200`` query parameter."""
    if not raw:
        return DEFAULT_EDGES
    try:
        values = tuple(float(part) for part in raw.split(",") if part.strip())
    except ValueError as exc:
        raise ValidationError(
            f"d_edges must be a comma-separated list of numbers; got {raw!r}.",
            field="d_edges",
        ) from exc
    if not values:
        return DEFAULT_EDGES
    return values
