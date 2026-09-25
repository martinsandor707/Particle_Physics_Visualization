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
folded into the lowest colour code, and the count of them is reported. The
canonical panels' relative ramp (three decades, :func:`relative_log_scale`) is
the one exception: there sub-floor bins get a code of their own and are not
drawn, because folding them into the opaque bottom colour painted the whole
crop as a dark rectangle around the showers.

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

#: A signed quantity on a logarithmic ramp: sign and log10 of the magnitude.
#: The codes split at :data:`calosrv.encode.quantize.SPLIT_CODE` - negative
#: values below it, positive from it - and |v| under the floor is not drawn.
SCALE_SIGNED_LOG = "signed_log10"

MODE_DECADES = "decades"
MODE_PERCENTILE = "percentile"
MODE_FIXED = "fixed"
SCALE_MODES = (MODE_DECADES, MODE_PERCENTILE, MODE_FIXED)

#: Relative mode: values are ratios to a stated reference density and the ramp
#: is dimensionless. Used by the canonical-frame panels; never selectable for
#: the lab frame, whose ramp is anchored in GeV.
MODE_RELATIVE = "relative"

#: Unit string of a relative ramp.
UNIT_RELATIVE = "a.u."

#: How a relative ramp treats bins under its floor: not drawn, rather than
#: folded into the opaque bottom colour. Canonical panels only.
FLOOR_TRANSPARENT = "transparent"

#: A ramp top within this many decades of the reference is the reference: a box
#: merge or an area computed from other edge arrays can put the peak ratio a
#: few ulps above 1.0, which must not read as a selection brighter than itself.
VMAX_SNAP_DECADES = 1e-12

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
    #: Relative-ramp provenance. Left ``None`` for the lab frame so its payload
    #: is unchanged; the canonical panels set all four.
    rho_ref: float | None = None
    rho_unit: str | None = None
    decades: float | None = None
    norm: str | None = None
    #: Sub-floor treatment and the floor as a ratio to ``rho_ref``. Emitted only
    #: when set, so neither the lab payload nor a Grad-CAM scale gains a key.
    floor: str | None = None
    floor_ratio: float | None = None
    #: The display channel the scale belongs to, when it is not density; and
    #: whether it is signed and drawn on a diverging ramp symmetric about zero.
    #: Emitted only when set, so the lab density payload is unchanged.
    quantity: str | None = None
    diverging: bool = False
    #: Energy-weighted CAM channels: the peak the ratio is taken against, its
    #: unit, and (signed channels) the code the positive half starts at and the
    #: positive and negative sums the panel holds.
    ref: float | None = None
    ref_unit: str | None = None
    split_code: int | None = None
    positive_total: float | None = None
    negative_total: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        if self.mode == MODE_RELATIVE:
            # A relative ramp always reaches its own peak, so nothing can sit
            # above it; the field would be a constant zero and is dropped.
            del data["clipped_high"]
            data["rho_ref"] = self.rho_ref
            data["rho_unit"] = self.rho_unit
            data["decades"] = self.decades
            data["norm"] = self.norm
        if self.floor is not None:
            data["floor"] = self.floor
            data["floor_ratio"] = self.floor_ratio
        if self.quantity is not None:
            data["quantity"] = self.quantity
        if self.diverging:
            data["diverging"] = True
        for key in ("ref", "ref_unit", "split_code", "positive_total", "negative_total"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


def _positive(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    return finite[finite > 0]


def relative_log_scale(
    ratio: np.ndarray,
    rho_ref: float,
    decades: float,
    norm: str,
    rho_unit: str = "GeV/mm^2/event",
    floor: str | None = None,
) -> ColorScale:
    """The dimensionless ramp of the canonical panels.

    ``ratio`` is the density divided by a stated reference peak ``rho_ref``.
    The ramp spans ``decades`` below 1.0, and its top is raised to the matrix's
    own peak whenever a selection exceeds the reference (which happens when the
    reference is the whole dataset and a slice of superposed showers is
    brighter), so nothing is ever clipped from above. A top within
    :data:`VMAX_SNAP_DECADES` of the reference is snapped back to it.

    Values below the bottom are counted as ``n_below`` (``clipped_low``), as
    are empty cells. With ``floor=FLOOR_TRANSPARENT`` the payload states that
    those sub-floor bins are not drawn - the encoder gives them their own code
    instead of the bottom of the ramp - and carries the floor as
    ``floor_ratio = 10^-decades`` of ``rho_ref``. Without it they fold into
    the lowest colour, the behaviour this function had before the floor code.
    """
    values = np.asarray(ratio, dtype=np.float64)
    positive = _positive(values)
    n_empty = int(values.size - positive.size)
    vmin = -float(decades)
    if positive.size == 0:
        vmax = 0.0
        n_below = 0
    else:
        log_values = np.log10(positive)
        vmax = max(0.0, float(log_values.max()))
        if vmax < VMAX_SNAP_DECADES:
            vmax = 0.0
        n_below = int((log_values < vmin).sum())
    return ColorScale(
        scale=SCALE_LOG,
        vmin=vmin,
        vmax=vmax,
        unit=UNIT_RELATIVE,
        mode=MODE_RELATIVE,
        locked=norm == "dataset",
        global_vmax=float(rho_ref) if rho_ref else None,
        n_below=n_below,
        n_above=0,
        n_empty=n_empty,
        rho_ref=float(rho_ref) if rho_ref else None,
        rho_unit=rho_unit,
        decades=float(decades),
        norm=norm,
        floor=floor,
        floor_ratio=float(10.0 ** vmin) if floor is not None else None,
    )


def attention_scale(
    matrix: np.ndarray, quantity: str, lo: float, hi: float, unit: str
) -> ColorScale:
    """A fixed linear ramp for a per-bin mean attention or attribution.

    Grad-CAM means lie in [0, 1] and Shap-CAM means in [-1, +1] by
    construction - a weighted mean with non-negative weights stays inside the
    range of what it averages - so nothing should ever fall outside; the
    clipped counts are computed anyway and always reported (CLAUDE.md
    section 2 makes the disclosure mandatory whether or not it is zero).
    """
    values = np.asarray(matrix, dtype=np.float64)
    finite = values[np.isfinite(values)]
    return ColorScale(
        scale=SCALE_LINEAR,
        vmin=float(lo),
        vmax=float(hi),
        unit=unit,
        mode=MODE_FIXED,
        locked=True,
        global_vmax=float(hi),
        n_below=int((finite < lo).sum()),
        n_above=int((finite > hi).sum()),
        n_empty=int(values.size - finite.size),
        quantity=quantity,
        diverging=lo < 0 < hi,
    )


def extensive_cam_scale(
    ratio: np.ndarray,
    populated: np.ndarray,
    ref: float,
    ref_unit: str,
    quantity: str,
    decades: float = 3.0,
    norm: str = "selection",
) -> ColorScale:
    """The ramp of an energy-weighted CAM channel: ``sum(E * CAM)`` over a peak.

    ``ratio`` is the per-bin value divided by the stated peak ``ref``; the ramp
    spans ``decades`` below 1.0 and bins under the floor are not drawn, as on the
    canonical density ramp. ``populated`` marks bins that hold hits: a bin with
    hits whose weighted attention sums to zero is below the floor, never empty.
    """
    values = np.asarray(ratio, dtype=np.float64)
    occupied = np.asarray(populated, dtype=bool) & np.isfinite(values)
    positive = values[occupied & (values > 0)]
    vmin = -float(decades)
    vmax = 0.0
    if positive.size:
        top = float(np.log10(positive.max()))
        vmax = top if top > VMAX_SNAP_DECADES else 0.0
    n_below = int((occupied & ~(values > 10.0 ** vmin)).sum())
    return ColorScale(
        scale=SCALE_LOG, vmin=vmin, vmax=vmax, unit=UNIT_RELATIVE, mode=MODE_RELATIVE,
        locked=norm == "dataset", global_vmax=float(ref) if ref else None,
        n_below=n_below, n_above=0, n_empty=int(values.size - occupied.sum()),
        rho_ref=float(ref) if ref else None, rho_unit=ref_unit,
        decades=float(decades), norm=norm,
        floor=FLOOR_TRANSPARENT, floor_ratio=float(10.0 ** vmin),
        quantity=quantity, ref=float(ref) if ref else None, ref_unit=ref_unit,
    )


def signed_log_scale(
    ratio: np.ndarray,
    populated: np.ndarray,
    ref: float,
    ref_unit: str,
    quantity: str,
    positive_total: float,
    negative_total: float,
    split_code: int,
    decades: float = 3.0,
    norm: str = "selection",
) -> ColorScale:
    """The diverging signed-log ramp of energy-weighted Shap-CAM.

    ``ratio`` is the signed value over the peak |value| ``ref``, so it lies in
    [-1, +1]. Each sign gets ``decades`` of log10 |ratio| below 1.0, the two
    halves meeting at the floor; |ratio| under the floor is not drawn and is
    counted. Nothing is clipped: the peak is the ramp's end by construction.
    """
    values = np.asarray(ratio, dtype=np.float64)
    occupied = np.asarray(populated, dtype=bool) & np.isfinite(values)
    floor = 10.0 ** -float(decades)
    n_below = int((occupied & ~(np.abs(values) >= floor)).sum())
    return ColorScale(
        scale=SCALE_SIGNED_LOG, vmin=-float(decades), vmax=0.0, unit=UNIT_RELATIVE,
        mode=MODE_RELATIVE, locked=norm == "dataset",
        global_vmax=float(ref) if ref else None,
        n_below=n_below, n_above=0, n_empty=int(values.size - occupied.sum()),
        rho_ref=float(ref) if ref else None, rho_unit=ref_unit,
        decades=float(decades), norm=norm,
        floor=FLOOR_TRANSPARENT, floor_ratio=float(floor),
        quantity=quantity, diverging=True, ref=float(ref) if ref else None, ref_unit=ref_unit,
        split_code=int(split_code),
        positive_total=float(positive_total), negative_total=float(negative_total),
    )


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
