"""Percentile clipping for readable axis and colour ranges.

Both the demonstration CSV and the production files contain genuine outliers.
Per-hit energies span roughly fifteen decades, and per-event reconstructed
energies have a long containment-leakage tail. Fitting an axis or a colour ramp
to the full data range spends almost all of it on a handful of extreme values
and collapses the structure everyone actually wants to see into one or two
pixels.

So display ranges are taken from the 1st to 99th percentile by default rather
than from the minimum and maximum.

The firm condition is **disclosure**. This is a decision about the displayed
range, not a data cut: nothing is removed from any aggregation, and every result
carries the count of values falling outside the visible range so it can be shown
as a footnote. Silently dropping a tail would conflict with the perceptual
integrity rules in CLAUDE.md section 2; showing a readable range and saying what
lies beyond it does not.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

#: Default percentile bounds. Section 2 of CLAUDE.md forbids a truncated
#: continuous scale without an explicit indicator, which the reported counts and
#: the panel footnote provide.
DEFAULT_LOW_PERCENTILE = 1.0
DEFAULT_HIGH_PERCENTILE = 99.0


@dataclass
class ClipResult:
    """A display range, and what it leaves out."""

    lo: float
    hi: float
    low_percentile: float
    high_percentile: float
    n_total: int
    n_below: int
    n_above: int
    data_min: float | None = None
    data_max: float | None = None
    applied: bool = True

    @property
    def n_outside(self) -> int:
        return self.n_below + self.n_above

    @property
    def fraction_outside(self) -> float:
        return self.n_outside / self.n_total if self.n_total else 0.0

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["n_outside"] = self.n_outside
        data["fraction_outside"] = round(self.fraction_outside, 6)
        data["note"] = self.note
        return data

    @property
    def note(self) -> str:
        if not self.applied or self.n_outside == 0:
            return "Full data range shown."
        return (
            f"Display range covers the {self.low_percentile:g}th to "
            f"{self.high_percentile:g}th percentile; {self.n_outside:,} of "
            f"{self.n_total:,} values ({100 * self.fraction_outside:.2f}%) lie "
            "outside it and are excluded from the view but not from the "
            "statistics."
        )


#: Candidate tick intervals, in ascending order of the range they suit.
#: Chosen so an axis carries roughly five to twelve labelled ticks.
_NICE_INTERVALS = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)

#: Target number of ticks used to pick between the candidates above.
_TARGET_TICKS = 6


def nice_range(lo: float, hi: float) -> tuple[float, float, float]:
    """Round a display range outward to clean tick boundaries.

    Returns ``(lo, hi, interval)``.

    A percentile-derived bound is an arbitrary float - 9.197060758 GeV, say -
    and letting it terminate an axis puts that number on a tick label, where it
    reads as false precision about a limit that was a display choice. Rounding
    the range outward to a multiple of a human interval fixes the labels at
    source, and doing it here rather than in the chart means the histogram bins
    and the fitted curve are sampled over the same range that is drawn, so bars
    line up with ticks instead of drifting against them.

    Rounding is always *outward*, so nothing that was inside the clipped range
    falls outside the displayed one.
    """
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return 0.0, 1.0, 0.2

    span = hi - lo
    interval = _NICE_INTERVALS[-1]
    for candidate in _NICE_INTERVALS:
        if span / candidate <= _TARGET_TICKS * 2:
            interval = candidate
            break

    nice_lo = float(np.floor(lo / interval) * interval)
    nice_hi = float(np.ceil(hi / interval) * interval)
    if nice_hi <= nice_lo:
        nice_hi = nice_lo + interval

    # Float multiplication leaves dust like 9.600000000000001; the interval is
    # never finer than 0.1, so six decimals is far more than enough.
    return round(nice_lo, 6), round(nice_hi, 6), interval


def percentile_clip(
    values: np.ndarray,
    low: float = DEFAULT_LOW_PERCENTILE,
    high: float = DEFAULT_HIGH_PERCENTILE,
    floor_at_zero: bool = False,
    pad: float = 0.0,
) -> ClipResult:
    """Compute a display range from percentiles, reporting what falls outside.

    ``floor_at_zero`` pins the lower bound to zero for quantities that are
    physically non-negative - a probability density axis, or an energy - which
    CLAUDE.md section 2 requires for bar charts and density functions.
    """
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    n_total = int(finite.size)

    if n_total == 0:
        return ClipResult(
            lo=0.0, hi=1.0,
            low_percentile=low, high_percentile=high,
            n_total=0, n_below=0, n_above=0, applied=False,
        )

    data_min = float(finite.min())
    data_max = float(finite.max())

    if n_total < 20:
        # Percentiles of a handful of points are noise. Show everything and say
        # that nothing was clipped.
        lo, hi = data_min, data_max
        if floor_at_zero:
            lo = min(0.0, lo)
        if hi <= lo:
            hi = lo + max(abs(lo), 1.0)
        return ClipResult(
            lo=lo, hi=hi,
            low_percentile=low, high_percentile=high,
            n_total=n_total, n_below=0, n_above=0,
            data_min=data_min, data_max=data_max, applied=False,
        )

    lo = float(np.percentile(finite, low))
    hi = float(np.percentile(finite, high))

    if floor_at_zero:
        lo = 0.0
    if hi <= lo:
        hi = lo + max(abs(lo), 1.0)

    if pad > 0:
        width = hi - lo
        hi += pad * width
        if not floor_at_zero:
            lo -= pad * width

    return ClipResult(
        lo=lo, hi=hi,
        low_percentile=low, high_percentile=high,
        n_total=n_total,
        n_below=int((finite < lo).sum()),
        n_above=int((finite > hi).sum()),
        data_min=data_min, data_max=data_max,
        applied=True,
    )
