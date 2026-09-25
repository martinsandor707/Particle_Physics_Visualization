"""Data-fitted, origin-centred display windows for the canonical panels.

The accumulation grid is deliberately generous - it must hold every hit of the
selection - but a display that showed all of it would spend most of its pixels
on empty margin. So each panel is cropped along each transverse axis to a
window **symmetric about the origin**, ``x' in [-dx, +dx]`` and
``y' in [-dy, +dy]``, where the half-width covers the energy-weighted 0.1st to
99.9th percentile of that axis's marginal::

    lo, hi = fit_axis(marginal, p0.1, p99.9)     # bins, snapped outward
    d      = max(|lo|, |hi|, floor)              # centred on the origin
    d      = ceil(d / 20 mm) * 20 mm             # whole accumulation bins
    d      = min(d, accumulation half-width)     # never beyond the grid

The origin is the midpoint of the two entry anchors, so a centred window keeps
it in the middle of the panel; the 1:1 metric aspect comes from the client's
isometric letterbox, not from forcing a square.

**Why 0.1-99.9 and not the CLAUDE.md 1-99 default.** A recorded exception
(``grid/frame.py: WINDOW_LOW_PERCENTILE``): a 1-99 crop cuts the shower halo
15-110x above the 10^-3 display floor, so the colour stops at the window edge
instead of fading out. The 0.1-99.9 window leaves 0.12-0.33% of the X'Y'
energy outside on production v37 (seven selections, N = 3 to 20 143).

**The floor.** Below :data:`~calosrv.grid.frame.PROVISIONAL_N` events the
window rests on weak evidence, so it is never narrower than
:data:`~calosrv.grid.frame.SHOWER_RADIUS_MIN_MM` (200 mm, one shower's own
extent). From there up the evidence sets it, floored only at two cell
footprints (100 mm), the physical resolution.

Two rules from CLAUDE.md section 2 govern the crop. **Disclosure**: the energy
left outside each panel's window is reported as a fraction, never dropped
silently. This module measures it on the raw accumulation grid; the rendered
panel re-measures it after display reconstruction, which can move a little
energy across the window edge. **Provisional ranges**: below ``PROVISIONAL_N``
co-registered events the fitted range is labelled provisional on the axis
itself.

Depth is never cropped: the longitudinal profile, leakage into the back layers
included, is the physics the depth panels exist to show.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..grid import frame as frame_mod
from .canonical import CanonicalBundle

#: Defaults of the percentile primitive :func:`fit_axis` (the CLAUDE.md rule).
LOW_PERCENTILE = 1.0
HIGH_PERCENTILE = 99.0

#: The canonical windows' own percentiles (the recorded exception).
WINDOW_LOW_PERCENTILE = frame_mod.WINDOW_LOW_PERCENTILE
WINDOW_HIGH_PERCENTILE = frame_mod.WINDOW_HIGH_PERCENTILE

#: Half-widths snap outward to whole accumulation bins.
SNAP_MM = frame_mod.CANONICAL_PITCH_MM

RULE_SYMMETRIC = "symmetric"


@dataclass(frozen=True)
class AxisFit:
    """A crop along one axis, in whole bins."""

    lo_index: int          # first kept bin
    hi_index: int          # one past the last kept bin
    lo: float              # millimetre edge of the first kept bin
    hi: float              # millimetre edge after the last kept bin
    energy_fraction_outside: float
    applied: bool
    #: The raw percentile window ``[lo, hi]`` before centring, when one was fitted.
    percentile_range: tuple[float, float] | None = None
    symmetric: bool = False
    floored: bool = False   # the half-width was raised to the floor
    clamped: bool = False   # the half-width was cut to the accumulation grid

    @property
    def n_bins(self) -> int:
        return self.hi_index - self.lo_index

    @property
    def half_width(self) -> float | None:
        """``(hi - lo) / 2`` for a centred window; ``None`` otherwise (depth)."""
        return 0.5 * (self.hi - self.lo) if self.symmetric else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "range": [self.lo, self.hi],
            "bins": [self.lo_index, self.hi_index],
            "energy_fraction_outside": round(self.energy_fraction_outside, 8),
            "applied": self.applied,
            "percentile_range": list(self.percentile_range) if self.percentile_range else None,
            "symmetric": self.symmetric,
            "half_width": self.half_width,
            "floored": self.floored,
            "clamped": self.clamped,
        }


def fit_axis(
    marginal: np.ndarray,
    edges: np.ndarray,
    low: float = LOW_PERCENTILE,
    high: float = HIGH_PERCENTILE,
) -> AxisFit:
    """Bins holding the ``low``..``high`` energy percentiles of a marginal.

    The window is snapped *outward* to whole bins, so the bin containing the
    ``low`` percentile point and the bin containing the ``high`` one are both
    kept. With no energy at all the full axis is returned and ``applied`` is
    false.
    """
    w = np.asarray(marginal, dtype=np.float64)
    n = int(w.size)
    total = float(w.sum())
    if n == 0 or total <= 0:
        return AxisFit(0, n, float(edges[0]), float(edges[-1]), 0.0, False)

    cumulative = np.cumsum(w)
    lo_index = int(np.searchsorted(cumulative, total * low / 100.0, side="right"))
    hi_index = int(np.searchsorted(cumulative, total * high / 100.0, side="left")) + 1
    lo_index = max(0, min(lo_index, n - 1))
    hi_index = max(lo_index + 1, min(hi_index, n))

    outside = float(w[:lo_index].sum() + w[hi_index:].sum())
    return AxisFit(
        lo_index=lo_index,
        hi_index=hi_index,
        lo=float(edges[lo_index]),
        hi=float(edges[hi_index]),
        energy_fraction_outside=outside / total,
        applied=True,
    )


def window_floor_mm(n_events: int, footprint: tuple[float, float] | None) -> float:
    """Smallest half-width a window may take for a selection of ``n_events``.

    Provisional selections get :data:`~calosrv.grid.frame.SHOWER_RADIUS_MIN_MM`;
    robust ones :data:`~calosrv.grid.frame.WINDOW_FLOOR_FOOTPRINTS` cell
    footprints, snapped up to whole bins (2 x 48.6 mm -> 100 mm on v37).
    """
    if n_events < frame_mod.PROVISIONAL_N:
        return float(frame_mod.SHOWER_RADIUS_MIN_MM)
    widths = [float(w) for w in (footprint or ()) if w is not None and math.isfinite(w) and w > 0]
    cell = max(widths) if widths else frame_mod.CANONICAL_PITCH_MM
    span = frame_mod.WINDOW_FLOOR_FOOTPRINTS * cell
    return float(math.ceil(span / SNAP_MM - 1e-9) * SNAP_MM)


def symmetric_axis(
    marginal: np.ndarray,
    edges: np.ndarray,
    pitch: float,
    floor_mm: float,
    low: float = WINDOW_LOW_PERCENTILE,
    high: float = WINDOW_HIGH_PERCENTILE,
    snap_mm: float = SNAP_MM,
) -> AxisFit:
    """An origin-centred window covering the ``low``..``high`` percentiles.

    ``edges`` must be a uniform grid of ``pitch`` symmetric about zero, as the
    canonical accumulation grid is, with ``snap_mm`` a multiple of ``pitch``.
    The half-width is the larger excursion of the percentile fit, raised to
    ``floor_mm`` (``floored``), snapped outward to ``snap_mm``, and cut to the
    grid's own half-width (``clamped``). The outside energy fraction is
    re-measured on the final window. An axis with no energy returns the whole
    grid with ``applied`` false.
    """
    w = np.asarray(marginal, dtype=np.float64)
    e = np.asarray(edges, dtype=np.float64)
    n = int(e.size - 1)
    half = 0.5 * float(e[-1] - e[0])
    raw = fit_axis(w, e, low, high)
    if not raw.applied:
        return AxisFit(0, n, -half, half, 0.0, False, symmetric=True)

    delta = max(abs(raw.lo), abs(raw.hi))
    floored = delta < floor_mm
    if floored:
        delta = float(floor_mm)
    delta = math.ceil(delta / snap_mm - 1e-9) * snap_mm
    clamped = delta > half + 1e-9
    if clamped:
        delta = half

    lo_index = int(round((half - delta) / float(pitch)))
    lo_index = max(0, min(lo_index, n // 2 - 1))
    hi_index = n - lo_index
    # Report the edges from the bin count, not from the linspace grid, so the
    # range is exactly antisymmetric: [-480, 480] rather than a ulp either side.
    kept = half - lo_index * float(pitch)

    total = float(w.sum())
    outside = float(w[:lo_index].sum() + w[hi_index:].sum())
    return AxisFit(
        lo_index=lo_index,
        hi_index=hi_index,
        lo=-kept,
        hi=kept,
        energy_fraction_outside=outside / total if total > 0 else 0.0,
        applied=True,
        percentile_range=(raw.lo, raw.hi),
        symmetric=True,
        floored=floored,
        clamped=clamped,
    )


@dataclass(frozen=True)
class PanelFit:
    """The two-dimensional crop of one panel."""

    name: str
    row: AxisFit
    col: AxisFit
    energy_total: float
    energy_kept: float

    @property
    def energy_fraction_outside(self) -> float:
        if self.energy_total <= 0:
            return 0.0
        return 1.0 - self.energy_kept / self.energy_total

    def crop(self, matrix: np.ndarray) -> np.ndarray:
        return matrix[self.row.lo_index:self.row.hi_index, self.col.lo_index:self.col.hi_index]

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row.as_dict(),
            "col": self.col.as_dict(),
            "energy_fraction_outside": round(self.energy_fraction_outside, 8),
        }


def _full(edges: np.ndarray) -> AxisFit:
    return AxisFit(0, int(edges.size - 1), float(edges[0]), float(edges[-1]), 0.0, False)


def _panel_fit(name: str, matrix: np.ndarray, row_edges: np.ndarray, col_edges: np.ndarray,
               crop_cols: bool, pitch: float, floor_mm: float) -> PanelFit:
    """Rows are always a transverse axis; columns are x' (X'Y') or depth."""
    row = symmetric_axis(matrix.sum(axis=1), row_edges, pitch, floor_mm)
    col = (symmetric_axis(matrix.sum(axis=0), col_edges, pitch, floor_mm)
           if crop_cols else _full(col_edges))
    total = float(matrix.sum())
    kept = float(matrix[row.lo_index:row.hi_index, col.lo_index:col.hi_index].sum())
    return PanelFit(name, row, col, total, kept)


@dataclass(frozen=True)
class WindowFit:
    """Display windows for all three canonical panels."""

    xy: PanelFit
    yz: PanelFit
    xz: PanelFit
    n_events: int
    floor_mm: float = frame_mod.SHOWER_RADIUS_MIN_MM
    #: How the transverse axes are written, for the note.
    axis_words: str = "x′ and y′"

    @property
    def provisional(self) -> bool:
        return self.n_events < frame_mod.PROVISIONAL_N

    def panel(self, name: str) -> PanelFit:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    @property
    def note(self) -> str:
        worst = max(
            (p.energy_fraction_outside for p in (self.xy, self.yz, self.xz)), default=0.0
        )
        floor_kind = (
            "a provisional one-shower floor" if self.provisional else "a two-cell-footprint floor"
        )
        text = (
            f"Display windows are symmetric about the origin along {self.axis_words}, each half-width "
            f"covering the {WINDOW_LOW_PERCENTILE:g}st to {WINDOW_HIGH_PERCENTILE:g}th energy "
            f"percentile, never below {self.floor_mm:.0f} mm ({floor_kind}), and snapped "
            f"outward to whole {SNAP_MM:.0f} mm bins. Up to {100.0 * worst:.3f}% of a panel's "
            "energy lies outside its window on the raw accumulation grid; it is excluded from "
            "the view but not from the statistics. Depth is never cropped."
        )
        if self.provisional:
            text += (
                f" With {self.n_events} co-registered event(s) the fitted ranges are "
                "provisional."
            )
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "percentiles": [WINDOW_LOW_PERCENTILE, WINDOW_HIGH_PERCENTILE],
            "rule": RULE_SYMMETRIC,
            "floor_mm": self.floor_mm,
            "snap_mm": SNAP_MM,
            "provisional": self.provisional,
            "xy": self.xy.as_dict(),
            "yz": self.yz.as_dict(),
            "xz": self.xz.as_dict(),
            "note": self.note,
        }


def fit_window(bundle: CanonicalBundle) -> WindowFit:
    """Fit every panel's display window from the bundle's own energy marginals.

    X'Y' uses its entrance-slab energy along both axes; the depth panels use
    the full-depth energy of their own transverse coordinate. Depth columns
    are never cropped. The floor follows the event count and the measured
    cell footprint (:func:`window_floor_mm`).
    """
    grid = bundle.grid
    floor_mm = window_floor_mm(bundle.n_events, bundle.footprint)
    z_edges = grid.axis("z").edges
    symbols = getattr(bundle, "symbols", None) or {"x": "x′", "y": "y′"}
    return WindowFit(
        axis_words=f"{symbols['x']} and {symbols['y']}",
        xy=_panel_fit("xy", bundle.xy.planes["e"], grid.y_edges, grid.x_edges, True, grid.pitch, floor_mm),
        yz=_panel_fit("yz", bundle.yz.planes["e"], grid.y_edges, z_edges, False, grid.pitch, floor_mm),
        xz=_panel_fit("xz", bundle.xz.planes["e"], grid.x_edges, z_edges, False, grid.pitch, floor_mm),
        n_events=bundle.n_events,
        floor_mm=floor_mm,
    )
