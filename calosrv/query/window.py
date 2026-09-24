"""Data-fitted display windows for the canonical panels.

The accumulation grid is deliberately generous - it must hold every hit of the
selection - but a display that showed all of it would spend most of its pixels
on empty margin. So each panel is cropped to the bins holding the central
98% of its energy along each transverse axis: the energy-weighted 1st to 99th
percentile, the same rule ``stats/clip.py`` applies to axis ranges and the
Auto-fit RoI control applies on screen.

Two rules from CLAUDE.md section 2 govern the crop. **Disclosure**: the energy
left outside each panel's window is reported as a fraction, never dropped
silently. **Provisional ranges**: below :data:`~calosrv.grid.frame.PROVISIONAL_N`
co-registered events the fitted range rests on weak evidence and is labelled
provisional on the axis itself.

Depth is never cropped: the longitudinal profile, leakage into the back layers
included, is the physics the depth panels exist to show.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..grid import frame as frame_mod
from .canonical import CanonicalBundle

LOW_PERCENTILE = 1.0
HIGH_PERCENTILE = 99.0


@dataclass(frozen=True)
class AxisFit:
    """A crop along one axis, in whole bins."""

    lo_index: int          # first kept bin
    hi_index: int          # one past the last kept bin
    lo: float              # millimetre edge of the first kept bin
    hi: float              # millimetre edge after the last kept bin
    energy_fraction_outside: float
    applied: bool

    @property
    def n_bins(self) -> int:
        return self.hi_index - self.lo_index

    def as_dict(self) -> dict[str, Any]:
        return {
            "range": [self.lo, self.hi],
            "bins": [self.lo_index, self.hi_index],
            "energy_fraction_outside": round(self.energy_fraction_outside, 8),
            "applied": self.applied,
        }


def fit_axis(
    marginal: np.ndarray,
    edges: np.ndarray,
    low: float = LOW_PERCENTILE,
    high: float = HIGH_PERCENTILE,
) -> AxisFit:
    """Bins holding the ``low``..``high`` energy percentiles of a marginal.

    The window is snapped *outward* to whole bins, so the bin containing the
    1st-percentile point and the bin containing the 99th are both kept. With no
    energy at all the full axis is returned and ``applied`` is false.
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
               crop_rows: bool, crop_cols: bool) -> PanelFit:
    row = fit_axis(matrix.sum(axis=1), row_edges) if crop_rows else _full(row_edges)
    col = fit_axis(matrix.sum(axis=0), col_edges) if crop_cols else _full(col_edges)
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
        text = (
            f"Display windows cover the {LOW_PERCENTILE:g}st to {HIGH_PERCENTILE:g}th "
            "energy percentile along x' and y'; up to "
            f"{100.0 * worst:.3f}% of a panel's energy lies outside its window and "
            "is excluded from the view but not from the statistics. Depth is never cropped."
        )
        if self.provisional:
            text += (
                f" With {self.n_events} co-registered event(s) the fitted ranges are "
                "provisional."
            )
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "percentiles": [LOW_PERCENTILE, HIGH_PERCENTILE],
            "provisional": self.provisional,
            "xy": self.xy.as_dict(),
            "yz": self.yz.as_dict(),
            "xz": self.xz.as_dict(),
            "note": self.note,
        }


def fit_window(bundle: CanonicalBundle) -> WindowFit:
    """Fit every panel's display window from the bundle's own energy marginals.

    XY uses its entrance-slab energy; the depth panels use the full-depth
    energy of their own transverse coordinate. Depth columns are never cropped.
    """
    grid = bundle.grid
    return WindowFit(
        xy=_panel_fit("xy", bundle.xy.planes["e"], grid.y_edges, grid.x_edges, True, True),
        yz=_panel_fit("yz", bundle.yz.planes["e"], grid.y_edges, grid.axis("z").edges, True, False),
        xz=_panel_fit("xz", bundle.xz.planes["e"], grid.x_edges, grid.axis("z").edges, True, False),
        n_events=bundle.n_events,
    )
