"""Colour-scale policy.

Per-cell summed energies span roughly fifteen decades, so a linear ramp is
useless: essentially every cell renders as the bottom colour except the few
brightest. The density panels therefore use ``log10``.

**The decade floor.** ``calodash/constants.py`` sets ``COLOR_FLOOR_GEV = 1e-6``
with the reasoning recorded in its docstring: without a floor, most of the
colour ramp is spent on cells around a tenth of a milli-electronvolt that carry
no physics. The same reasoning generalises here as a *relative* floor of six
decades below the brightest cell, which adapts to datasets at other energy
scales instead of hard-coding one detector's numbers. Cells below the floor are
folded into the lowest colour code, and the count of them is reported.

**Locking the ramp is a scientific-integrity feature, not a convenience.** If
``vmax`` is recomputed from each selection, then a selection carrying one tenth
of the energy renders identically to the full dataset, and a reader will
reasonably conclude the physics is unchanged. So the default anchors ``vmax`` to
the experiment's global maximum and the interface shows a badge when autoscaling
is switched on instead.

**Grad-CAM attention is a different quantity and gets a different policy.** It
is already bounded in [0, 1], so it uses a linear scale with *fixed* endpoints -
fixed, so that attention maps remain comparable across slider positions, which
is the entire reason for looking at them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

SCALE_LOG = "log10"
SCALE_LINEAR = "linear"

MODE_DECADES = "decades"
MODE_PERCENTILE = "percentile"
MODE_FIXED = "fixed"
SCALE_MODES = (MODE_DECADES, MODE_PERCENTILE, MODE_FIXED)

#: Dynamic range of the logarithmic ramp, in decades below the brightest cell.
DEFAULT_DECADES = 6.0

#: Percentile bounds used by ``MODE_PERCENTILE``.
LOW_PERCENTILE = 1.0
HIGH_PERCENTILE = 99.0


@dataclass
class ColorScale:
    """How cell values map onto the 1..255 colour codes."""

    scale: str
    vmin: float
    vmax: float
    unit: str
    mode: str
    locked: bool
    global_vmax: float | None = None
    n_below: int = 0
    n_above: int = 0
    n_empty: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "scale": self.scale,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "unit": self.unit,
            "mode": self.mode,
            "locked": self.locked,
            "global_vmax": self.global_vmax,
            "clipped_low": self.n_below,
            "clipped_high": self.n_above,
            "empty_cells": self.n_empty,
        }


def _positive(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    return finite[finite > 0]


def resolve_scale(
    matrix: np.ndarray,
    channel: str = "density",
    mode: str = MODE_DECADES,
    global_vmax: float | None = None,
    lock: bool = True,
    decades: float = DEFAULT_DECADES,
) -> ColorScale:
    """Choose the value range this matrix will be quantised against."""
    values = np.asarray(matrix, dtype=np.float64)

    if channel == "gradcam":
        # Bounded quantity; fixed endpoints keep attention maps comparable.
        empty = int((~np.isfinite(values)).sum())
        return ColorScale(
            scale=SCALE_LINEAR,
            vmin=0.0,
            vmax=1.0,
            unit="attention",
            mode=MODE_FIXED,
            locked=True,
            global_vmax=1.0,
            n_empty=empty,
        )

    positive = _positive(values)
    n_empty = int(values.size - positive.size)

    if positive.size == 0:
        return ColorScale(
            scale=SCALE_LOG, vmin=-9.0, vmax=0.0, unit="GeV",
            mode=mode, locked=lock, global_vmax=global_vmax,
            n_empty=n_empty,
        )

    log_values = np.log10(positive)

    if mode == MODE_PERCENTILE:
        lo = float(np.percentile(log_values, LOW_PERCENTILE))
        hi = float(np.percentile(log_values, HIGH_PERCENTILE))
    else:
        hi = float(log_values.max())
        lo = max(float(log_values.min()), hi - decades)

    if lock and global_vmax is not None and global_vmax > 0:
        hi = float(np.log10(global_vmax))
        lo = max(float(log_values.min()), hi - decades)

    if not hi > lo:
        hi = lo + 1.0

    return ColorScale(
        scale=SCALE_LOG,
        vmin=lo,
        vmax=hi,
        unit="GeV",
        mode=mode,
        locked=bool(lock and global_vmax),
        global_vmax=float(global_vmax) if global_vmax else None,
        n_below=int((log_values < lo).sum()),
        n_above=int((log_values > hi).sum()),
        n_empty=n_empty,
    )
