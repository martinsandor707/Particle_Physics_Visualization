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

**The D-frame's x' cap** (``fit_window(..., cap_x=True)``, the D-frame only).
The percentile rule weighs energy, but the display draws only bins at or above
10^-3 of rho_ref. When most of a selection overlaps near the origin and a few
per cent of well-separated pairs spread thinly along x' - 96.6% / 97.5% of the
electron / muon two-shower events enter closer than 80 mm apart - the 0.1-99.9
half-width reaches +-1,740 mm while, averaged over 20,000 events, nothing beyond
+-186 mm clears the floor: an isometric panel 12:1 wide and 89% empty. So the
x' axis of X'Y' (its columns) and of X'Z' (its rows) is capped at the drawn
field's own extent::

    drawn  = bins at or above the floor on the raw 20 mm grid (channel's mask)
    comps  = runs of drawn x' bins, gaps <= one footprint bridged
    keep   = comps holding >= 0.1% of the drawn energy (the rest are islands)
    limit  = max |outer edge| of keep + kernel reach, snapped, >= floor
    d      = min(percentile half-width, limit)

The cap only tightens. Drawn bins left outside - islands, or bins the
percentile window already cut - are counted, with their share of the panel's
energy and their place, so the panel can mark them at its edge. The y' axes
and depth are unchanged, and the per-shower frames never cap.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..grid import frame as frame_mod
from ..grid.kernel import Kernel
from ..grid.layer_groups import PooledAxis
from ..grid.resolution import MODE_NATIVE
from . import planes as planes_mod
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

#: The name of the D-frame's x' cap in the payload (``AxisFit.cap["rule"]``).
CAP_RULE = "drawn_extent"

#: A component of drawn x' bins holding less than this share of the panel's
#: drawn energy is an island and does not set the cap: the same 0.1% tail the
#: percentile rule already leaves outside.
CAP_ISLAND_SHARE = WINDOW_LOW_PERCENTILE / 100.0


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
    #: The D-frame's drawn-extent cap on an x' axis (:func:`cap_axis`), else None.
    cap: dict[str, Any] | None = None

    @property
    def n_bins(self) -> int:
        return self.hi_index - self.lo_index

    @property
    def half_width(self) -> float | None:
        """``(hi - lo) / 2`` for a centred window; ``None`` otherwise (depth)."""
        return 0.5 * (self.hi - self.lo) if self.symmetric else None

    def as_dict(self, with_cap: bool = False) -> dict[str, Any]:
        """The payload form; ``with_cap`` adds the ``cap`` key (the D-frame's fits)."""
        out = {
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
        if with_cap:
            out["cap"] = self.cap
        return out


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

    def as_dict(self, with_cap: bool = False) -> dict[str, Any]:
        return {
            "row": self.row.as_dict(with_cap),
            "col": self.col.as_dict(with_cap),
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


# ------------------------------------------------------------- x' cap --

_MINUS = "\u2212"
_SUPERSCRIPT = str.maketrans("0123456789-.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻·")


def _floor_label(decades: float = frame_mod.RAMP_DECADES) -> str:
    """``10⁻³`` for three decades (``density.floor_label``, which imports this module)."""
    return "10" + format(-float(decades), "g").translate(_SUPERSCRIPT)


def _mm(value: float, signed: bool = False) -> str:
    """Millimetres with thousands separators; ``signed`` writes U+2212 or ``+``."""
    v = float(value)
    text = f"{abs(v):,.0f}"
    if not signed or text == "0":
        return text if v >= 0 or text == "0" else _MINUS + text
    return (_MINUS if v < 0 else "+") + text


def _percent(fraction: float) -> str:
    pct = 100.0 * float(fraction)
    if 0 < pct < 0.001:
        return "< 0.001%"
    return f"{pct:.3f}%"


def _centres(edges: np.ndarray) -> np.ndarray:
    e = np.asarray(edges, dtype=np.float64)
    return 0.5 * (e[:-1] + e[1:])


def _components(drawn: np.ndarray, gap_bins: int) -> list[tuple[int, int]]:
    """Maximal runs ``[start, stop)`` of drawn bins, bridging undrawn runs of <= ``gap_bins``."""
    idx = np.flatnonzero(np.asarray(drawn, dtype=bool))
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) - 1 > gap_bins)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    stops = np.concatenate((idx[breaks] + 1, [idx[-1] + 1]))
    return [(int(a), int(b)) for a, b in zip(starts, stops)]


def cap_axis(
    fit: AxisFit,
    marginal: np.ndarray,
    edges: np.ndarray,
    pitch: float,
    floor_mm: float,
    *,
    drawn: np.ndarray,
    drawn_energy: np.ndarray,
    drawn_moment: np.ndarray,
    panel_energy: float,
    reach_mm: float,
    gap_mm: float,
    rho_ref: float,
    floor_ratio: float,
    snap_mm: float = SNAP_MM,
) -> AxisFit:
    """Cap a centred x' window at the extent of the drawn field.

    ``fit`` is the percentile window of :func:`symmetric_axis` over the same
    ``edges``. ``drawn`` marks the x' bins holding at least one drawn raw bin,
    ``drawn_energy`` the energy of those drawn bins per x' bin and
    ``drawn_moment`` their energy times the panel's other coordinate (y' or
    z'), for the edge mark's position. Components of drawn bins are bridged
    across undrawn runs no wider than ``gap_mm``; a component under
    :data:`CAP_ISLAND_SHARE` of the drawn energy is an island and does not set
    the cap. The limit - the kept components' outer edge plus ``reach_mm``,
    snapped outward and never below ``floor_mm`` - can only tighten ``fit``.
    Every drawn bin outside the final window is counted in ``cap.outside``.
    """
    e = np.asarray(edges, dtype=np.float64)
    n = int(e.size - 1)
    drawn = np.asarray(drawn, dtype=bool)
    drawn_energy = np.where(drawn, np.asarray(drawn_energy, dtype=np.float64), 0.0)
    drawn_moment = np.where(drawn, np.asarray(drawn_moment, dtype=np.float64), 0.0)
    half_grid = 0.5 * float(e[-1] - e[0])
    percentile_half = fit.half_width if fit.half_width is not None else half_grid
    gap_bins = int(math.floor(float(gap_mm) / float(pitch) + 1e-9))

    comps = _components(drawn, gap_bins)
    total_drawn = float(drawn_energy.sum())
    drawn_half = limit = None
    applied = floored_cap = False
    if comps:
        if total_drawn > 0:
            keep = [(a, b) for a, b in comps
                    if float(drawn_energy[a:b].sum()) / total_drawn >= CAP_ISLAND_SHARE]
        else:
            keep = []
        keep = keep or comps
        drawn_half = max(max(abs(float(e[a])), abs(float(e[b]))) for a, b in keep)
        limit = math.ceil((drawn_half + float(reach_mm)) / snap_mm - 1e-9) * snap_mm
        floored_cap = limit < floor_mm
        limit = float(max(limit, floor_mm))
        applied = bool(fit.applied and limit < percentile_half - 1e-9)

    if applied:
        lo_index = int(round((half_grid - limit) / float(pitch)))
        lo_index = max(0, min(lo_index, n // 2 - 1))
        hi_index = n - lo_index
        kept = half_grid - lo_index * float(pitch)
        w = np.asarray(marginal, dtype=np.float64)
        total = float(w.sum())
        outside = float(w[:lo_index].sum() + w[hi_index:].sum())
        final = AxisFit(
            lo_index=lo_index, hi_index=hi_index, lo=-kept, hi=kept,
            energy_fraction_outside=outside / total if total > 0 else 0.0,
            applied=True, percentile_range=fit.percentile_range, symmetric=True,
            floored=floored_cap, clamped=False,
        )
    else:
        final = fit

    index = np.arange(n)
    sides = []
    for side, beyond in ((-1, index < final.lo_index), (1, index >= final.hi_index)):
        sel = drawn & beyond
        if not sel.any():
            continue
        where = np.flatnonzero(sel)
        energy = float(drawn_energy[sel].sum())
        sides.append({
            "side": side,
            "bins": int(sel.sum()),
            "energy_fraction": round(energy / panel_energy, 8) if panel_energy > 0 else 0.0,
            "range": [float(e[where[0]]), float(e[where[-1] + 1])],
            "at": round(float(drawn_moment[sel].sum()) / energy, 3) if energy > 0 else None,
        })
    outside_bins = sum(side["bins"] for side in sides)
    outside_energy = float(sum(
        drawn_energy[drawn & ((index < final.lo_index) | (index >= final.hi_index))]))

    cap = {
        "rule": CAP_RULE,
        "applied": applied,
        "percentile_half_width": float(percentile_half),
        "drawn_half_width": drawn_half,
        "reach_mm": float(reach_mm),
        "limit": limit,
        "gap_mm": round(float(gap_mm), 3),
        "floor_ratio": float(floor_ratio),
        "rho_ref": float(rho_ref),
        "outside": {
            "bins": int(outside_bins),
            "energy_fraction": (round(outside_energy / panel_energy, 8)
                                if panel_energy > 0 else 0.0),
            "sides": sides,
        },
    }
    return dataclasses.replace(final, cap=cap)


def drawn_masks(
    bundle: CanonicalBundle,
    channel: str = planes_mod.CHANNEL_DENSITY,
    weighting: str = planes_mod.WEIGHTING_ENERGY,
    native: bool = False,
    reference: dict[str, float] | None = None,
    depth_pool: PooledAxis | None = None,
) -> dict[str, Any]:
    """Raw-grid bins of X'Y' and X'Z' the display can draw, and the density reference.

    The semantics of ``density.render_panel``, measured on the raw 20 mm
    accumulation grid (the display kernels are weighted means, so a displayed
    bin clears the floor only where a raw bin within the kernel's reach does):

    * density, and a mean-CAM channel in Continuous Field: ``<rho> >=
      10^-3 rho_ref``, ``rho_ref`` the selection's raw peak of the panel group
      (X'Y' its own, X'Z' shared with Y'Z');
    * a mean-CAM channel in Native Grid: every bin with hits, since attention
      measured on real hits is always drawn there;
    * an energy-weighted CAM channel: the union of the density mask and its
      own ``|sum E*CAM| >= 10^-3`` of its raw peak, so switching channel never
      shrinks the window below the density view's.

    ``reference`` (the dataset peaks under ``rho_norm=dataset``) lowers the
    reference to ``min(selection, dataset)`` per group: a slice brighter than
    the dataset draws further out under that normalisation, and the window
    must hold it. ``depth_pool`` adds the pooled depth grid's mask (its own,
    lower selection peak), mapped back onto the native layers.
    """
    floor_ratio = 10.0 ** -float(frame_mod.RAMP_DECADES)
    view = planes_mod.view(channel, weighting)
    variants = [_variant_masks(bundle, view, native, reference, None, floor_ratio)]
    if depth_pool is not None:
        variants.append(_variant_masks(bundle, view, native, reference, depth_pool, floor_ratio))
    masks = dict(variants[0]["masks"])
    if len(variants) == 2:
        layers = (np.asarray(depth_pool.op) > 0).astype(np.float64)
        pooled = variants[1]["masks"]["xz"].astype(np.float64) @ layers
        masks["xz"] = masks["xz"] | (pooled > 0)
    return {"masks": masks, "rho_ref": variants[0]["rho_ref"], "floor_ratio": floor_ratio}


def _peak(values: np.ndarray, signed: bool = False) -> float:
    if values.size == 0:
        return 0.0
    return float(np.abs(values).max() if signed else values.max())


def _variant_masks(bundle, view, native, reference, pool, floor_ratio) -> dict[str, Any]:
    grid = bundle.grid
    n = max(1, bundle.n_events)
    depth_edges = grid.axis("z").edges if pool is None else pool.dst_edges
    edges = {"xy": (grid.y_edges, grid.x_edges), "yz": (grid.y_edges, depth_edges),
             "xz": (grid.x_edges, depth_edges)}

    def plane(name: str, key: str) -> np.ndarray | None:
        p = bundle.panel(name).planes.get(key)
        if p is None:
            return None
        p = np.asarray(p, dtype=np.float64)
        return p if name == "xy" or pool is None else p @ pool.op.T

    def areal(name: str, values: np.ndarray) -> np.ndarray:
        rows, cols = edges[name]
        return values / (n * np.outer(np.diff(rows), np.diff(cols)))

    energy = {name: plane(name, "e") for name in ("xy", "yz", "xz")}
    rho = {name: areal(name, energy[name]) for name in ("xy", "yz", "xz")}
    ref = {"xy": _peak(rho["xy"]), "depth": max(_peak(rho["yz"]), _peak(rho["xz"]))}
    for key in ref:
        other = (reference or {}).get(key)
        if other is not None and math.isfinite(float(other)) and float(other) > 0:
            ref[key] = min(ref[key], float(other)) if ref[key] > 0 else float(other)

    cam = None
    if view.is_cam and view.kind != planes_mod.KIND_RATIO:
        signed = view.kind == planes_mod.KIND_SIGNED
        parts = {name: [plane(name, p) for p in view.numerator] for name in ("xy", "yz", "xz")}
        if all(part is not None for name in parts for part in parts[name]):
            values = {name: areal(name, sum(parts[name])) for name in parts}
            peaks = {"xy": _peak(values["xy"], signed),
                     "depth": max(_peak(values["yz"], signed), _peak(values["xz"], signed))}
            cam = (values, peaks, signed)

    masks = {}
    for name, group in (("xy", "xy"), ("xz", "depth")):
        peak = ref[group]
        r = rho[name]
        density_drawn = (r > 0) & (r >= floor_ratio * peak) if peak > 0 else np.zeros(r.shape, bool)
        if view.kind == planes_mod.KIND_RATIO:
            den = plane(name, view.denominator)
            if native or peak <= 0:
                mask = (den if den is not None else energy[name]) > 0
            else:
                mask = density_drawn
        elif cam is not None:
            values, peaks, signed = cam
            v = np.abs(values[name]) if signed else values[name]
            own = (energy[name] > 0) & (v >= floor_ratio * peaks[group]) if peaks[group] > 0 \
                else np.zeros(r.shape, bool)
            mask = density_drawn | own
        else:
            mask = density_drawn
        masks[name] = mask
    return {"masks": masks, "rho_ref": ref}


def _cap_panel(panel: PanelFit, matrix: np.ndarray, mask: np.ndarray, x_on_cols: bool,
               other_centres: np.ndarray, x_edges: np.ndarray, pitch: float, floor_mm: float,
               **kwargs: Any) -> PanelFit:
    """Cap a panel's x' axis: X'Y' columns within its y' rows, or X'Z' rows over all depth."""
    m = np.asarray(matrix, dtype=np.float64)
    if x_on_cols:
        rows = slice(panel.row.lo_index, panel.row.hi_index)
        sub, mk = m[rows], np.asarray(mask, dtype=bool)[rows]
        weighted = np.where(mk, sub, 0.0)
        drawn, drawn_energy = mk.any(axis=0), weighted.sum(axis=0)
        moment = (weighted * np.asarray(other_centres)[rows][:, None]).sum(axis=0)
        axis = cap_axis(panel.col, m.sum(axis=0), x_edges, pitch, floor_mm, drawn=drawn,
                        drawn_energy=drawn_energy, drawn_moment=moment,
                        panel_energy=float(m.sum()), **kwargs)
        row, col = panel.row, axis
    else:
        mk = np.asarray(mask, dtype=bool)
        weighted = np.where(mk, m, 0.0)
        drawn, drawn_energy = mk.any(axis=1), weighted.sum(axis=1)
        moment = (weighted * np.asarray(other_centres)[None, :]).sum(axis=1)
        axis = cap_axis(panel.row, m.sum(axis=1), x_edges, pitch, floor_mm, drawn=drawn,
                        drawn_energy=drawn_energy, drawn_moment=moment,
                        panel_energy=float(m.sum()), **kwargs)
        row, col = axis, panel.col
    kept = float(m[row.lo_index:row.hi_index, col.lo_index:col.hi_index].sum())
    return PanelFit(panel.name, row, col, float(m.sum()), kept)


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
    #: The D-frame's x' cap was evaluated (every axis dict then carries ``cap``).
    capped: bool = False
    #: The symbol of the capped axis, for the note.
    x_symbol: str = "x′"

    @property
    def provisional(self) -> bool:
        return self.n_events < frame_mod.PROVISIONAL_N

    def panel(self, name: str) -> PanelFit:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def _capped_axes(self) -> list[tuple[str, AxisFit]]:
        if not self.capped:
            return []
        return [(name, axis) for name, axis in (("X′Y′", self.xy.col), ("X′Z′", self.xz.row))
                if axis.cap is not None]

    @property
    def cap_note(self) -> str:
        """The cap's sentences, empty when it neither tightened a window nor left a drawn bin out."""
        axes = self._capped_axes()
        x = self.x_symbol
        text = ""
        applied = [(name, axis) for name, axis in axes if axis.cap["applied"]]
        if applied:
            reach = applied[0][1].cap["reach_mm"]
            parts = "; ".join(
                f"{name} ±{_mm(axis.half_width)} mm instead of "
                f"±{_mm(axis.cap['percentile_half_width'])} mm"
                for name, axis in applied
            )
            reach_words = (f" plus the display kernel's {_mm(reach)} mm reach" if reach > 0
                           else " (no kernel reach in Native Grid)")
            # Islands left beyond a capped window are drawn bins: the claim that
            # nothing beyond it is drawn holds only apart from them.
            islands = any(axis.cap["outside"]["bins"] for _, axis in applied)
            except_words = ", apart from the isolated bins counted below," if islands else ""
            text += (
                f" The {x} half-width is capped at the extent of the drawn field{reach_words}, "
                f"below the percentile rule's ({parts}): beyond it{except_words} no bin of this "
                f"selection reaches the {_floor_label()} display floor, so nothing would be drawn there."
            )
        beyond = []
        for name, axis in axes:
            outside = axis.cap["outside"]
            if not outside["bins"]:
                continue
            spans = ", ".join(
                f"{_mm(side['range'][0], True)} to {_mm(side['range'][1], True)} mm"
                for side in outside["sides"]
            )
            beyond.append(
                f"{name} {outside['bins']:,} bin(s), {spans}, "
                f"{_percent(outside['energy_fraction'])} of the panel's energy"
            )
        if beyond:
            text += (
                f" Drawn {x} bins beyond the window are counted and marked at its edge, not "
                f"drawn ({'; '.join(beyond)}): islands too small to set the window, or bins the "
                "percentile rule already cut."
            )
        return text

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
            f"outward to whole {SNAP_MM:.0f} mm bins."
            + self.cap_note
            + f" Up to {100.0 * worst:.3f}% of a panel's "
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
            "xy": self.xy.as_dict(self.capped),
            "yz": self.yz.as_dict(self.capped),
            "xz": self.xz.as_dict(self.capped),
            "note": self.note,
        }


def fit_window(
    bundle: CanonicalBundle,
    *,
    cap_x: bool = False,
    kernel: Kernel | None = None,
    channel: str = planes_mod.CHANNEL_DENSITY,
    weighting: str = planes_mod.WEIGHTING_ENERGY,
    display: str | None = None,
    reference: dict[str, float] | None = None,
    depth_pool: PooledAxis | None = None,
) -> WindowFit:
    """Fit every panel's display window from the bundle's own energy marginals.

    X'Y' uses its entrance-slab energy along both axes; the depth panels use
    the full-depth energy of their own transverse coordinate. Depth columns
    are never cropped. The floor follows the event count and the measured
    cell footprint (:func:`window_floor_mm`).

    ``cap_x`` (the D-frame only; the per-shower frames never pass it) caps the
    x' axis of X'Y' and X'Z' at the drawn field's extent plus ``kernel``'s
    reach (:func:`cap_axis`), with the drawn bins those of ``channel`` under
    ``display`` (:func:`drawn_masks`). ``display`` defaults to Native Grid when
    the kernel is ``none``. ``reference`` and ``depth_pool`` are the dataset
    peaks and the pooled depth axis the render will use, when it uses them.
    """
    grid = bundle.grid
    floor_mm = window_floor_mm(bundle.n_events, bundle.footprint)
    z_edges = grid.axis("z").edges
    symbols = getattr(bundle, "symbols", None) or {"x": "x′", "y": "y′"}
    xy = _panel_fit("xy", bundle.xy.planes["e"], grid.y_edges, grid.x_edges, True, grid.pitch, floor_mm)
    yz = _panel_fit("yz", bundle.yz.planes["e"], grid.y_edges, z_edges, False, grid.pitch, floor_mm)
    xz = _panel_fit("xz", bundle.xz.planes["e"], grid.x_edges, z_edges, False, grid.pitch, floor_mm)
    if cap_x:
        if kernel is None:
            raise ValueError("cap_x needs the display kernel, chosen before the fit")
        native = (display == MODE_NATIVE) if display is not None else kernel.name == "none"
        drawn = drawn_masks(bundle, channel, weighting, native, reference, depth_pool)
        widths = [float(w) for w in (bundle.footprint or ())
                  if w is not None and math.isfinite(w) and w > 0]
        cell = max(widths) if widths else grid.pitch
        common = {
            "reach_mm": float(kernel.reach_bins(grid.pitch) * grid.pitch),
            "gap_mm": frame_mod.WINDOW_CAP_GAP_FOOTPRINTS * cell,
            "floor_ratio": drawn["floor_ratio"],
        }
        xy = _cap_panel(xy, bundle.xy.planes["e"], drawn["masks"]["xy"], True,
                        _centres(grid.y_edges), grid.x_edges, grid.pitch, floor_mm,
                        rho_ref=drawn["rho_ref"]["xy"], **common)
        xz = _cap_panel(xz, bundle.xz.planes["e"], drawn["masks"]["xz"], False,
                        _centres(z_edges), grid.x_edges, grid.pitch, floor_mm,
                        rho_ref=drawn["rho_ref"]["depth"], **common)
    return WindowFit(
        axis_words=f"{symbols['x']} and {symbols['y']}",
        xy=xy, yz=yz, xz=xz,
        n_events=bundle.n_events,
        floor_mm=floor_mm,
        capped=cap_x,
        x_symbol=symbols["x"],
    )
