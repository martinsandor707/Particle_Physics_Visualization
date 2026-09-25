"""Render a canonical bundle: crop, reconstruct, normalise, encode.

**The quantity.** Each bin carries the ensemble-averaged projected surface
energy density::

    <rho> = sum(E) / (N_frame * dA)      [GeV / mm^2 / event]

Dividing by the number of co-registered events makes selections of different
size comparable; dividing by the bin area makes the value independent of the
display resolution.

**Two display modes.** *Native Grid* is the audit view: the raw 20 mm
accumulation bins inside the display window, box-merged only when the payload
guard must. *Continuous Field* reconstructs the transverse axes with a
conservative kernel - Gaussian ``sigma = 10`` mm below 50 events, the bilinear
tent above (``grid/kernel.py`` for the maths, ``query/reconstruct.py`` for the
choice). Depth is never smoothed in either mode.

**Why the raw peak bounds the picture.** Both kernels, like the box merge, are
non-negative partitions of unity on the uniform accumulation grid, so every
displayed bin is a weighted *mean* of raw bin densities and can never exceed
the raw 20 mm-grid peak. That peak is therefore the density reference
``rho_ref``: a proven upper bound, independent of R, the kernel and the window,
which keeps the dataset normalisation comparable across selections. How far a
kernel lowers the displayed peak below it is reported per panel as
``rho.kernel_attenuation``.

**The colour.** The ramp is dimensionless: ``<rho> / rho_ref`` on a log scale
spanning ``RAMP_DECADES`` below 1.0, labelled ``Average hit density (a.u.)`` as
the directive asks. ``rho_ref`` is either the selection's own raw peak
(default, so every selection uses the whole ramp) or the raw peak of the whole
dataset (so colours stay comparable across D slices - the colour-lock argument
of ``encode/scale.py``); which one, and its value in GeV/mm^2/event, travels in
the payload and is printed on the panel. Bins below the 10^-3 floor are *not
drawn*: they get their own colour code (``encode/quantize.py``), are counted,
and the energy they hold is reported. Grad-CAM panels keep their fixed 0-1
scale; in Continuous Field their attention is masked where the reconstructed
energy density is below the same floor, because the kernel tails carry
attention into bins no measured energy reached.

**Energy bookkeeping.** A kernel moves energy across the window edge in both
directions, so a panel's ``total`` is the in-window energy *after*
reconstruction and ``energy_fraction_outside_window = 1 - total / total_all``
is measured after it too; the window fit's raw-grid figure travels beside it
as ``energy_fraction_outside_window_raw``.

**Payload budget.** A wide, flat canonical window can push a fine raster past
the 100 KB contract. The guard here degrades deterministically and says so:
in continuous mode it lowers R by a quarter per step (landing on the default
R rather than stepping over it, :func:`next_resolution`); in native mode it
merges transverse bins pairwise - never depth layers, which stay native - and
stops once every transverse axis is a single bin. An attempt whose rasters
alone exceed the limit is stepped past without being rendered
(:func:`raster_bytes`). It bounds the panels; ``api/frame_canonical.py`` then
measures the whole response as it goes on the wire (:func:`wire_size`) and,
when the envelope around the panels pushes it over, continues the guard's own
sequence from the state it served (``guard["next"]``), measuring each
candidate as it is served.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..encode import matrix as matrix_encode
from ..encode import quantize
from ..encode import scale as scale_mod
from ..encode import topk
from ..grid import frame as frame_mod
from ..grid import kernel as kernel_mod
from ..grid.kernel import Kernel
from ..grid.resolution import DEFAULT_RESOLUTION, MIN_RESOLUTION, MODE_CONTINUOUS, MODE_NATIVE
from . import reconstruct
from . import planes as planes_mod
from .canonical import CanonicalBundle
from .panels import CHANNEL_DENSITY, CHANNEL_GRADCAM, WEIGHTING_COUNT
from .planes import KIND_RATIO, KIND_SIGNED
from .window import AxisFit, PanelFit, WindowFit

#: How the canonical axes are written; the semantic names stay x, y, z.
SYMBOLS = {"x": "x′", "y": "y′", "z": "z′"}

RHO_UNIT = "GeV/mm^2/event"

NORM_SELECTION = "selection"
NORM_DATASET = "dataset"
NORMS = (NORM_SELECTION, NORM_DATASET)

#: Encoded-size ceiling the panel guard steers under; the contract is 100 KB and
#: the envelope around the panels needs a few KB of its own. Resolved at call
#: time, so a test can lower or lift it.
PAYLOAD_LIMIT = 96_000

#: The contract itself, for the whole response as it goes on the wire.
RESPONSE_LIMIT = 100_000

#: Render attempts of the panel guard before it gives up and says so.
MAX_ATTEMPTS = 12

_PANEL_AXES = {"xy": ("y", "x"), "yz": ("y", "z"), "xz": ("x", "z")}
_PANELS = ("xy", "yz", "xz")


_SUPERSCRIPT = str.maketrans("0123456789-.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻·")


def floor_label(decades: float = frame_mod.RAMP_DECADES) -> str:
    """The display floor as the interface writes it: ``10⁻³`` for three decades."""
    return "10" + format(-float(decades), "g").translate(_SUPERSCRIPT)


def wire_size(obj: Any) -> int:
    """Bytes of ``obj`` exactly as the route puts it on the wire.

    FastAPI renders a plain-dict response with ``JSONResponse``: compact
    separators, UTF-8 without ASCII escapes, no NaN. ``GZipMiddleware`` then
    compresses it, but the 100 KB contract is on the JSON itself.
    """
    return len(json.dumps(
        obj, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"),
    ).encode("utf-8"))


# --------------------------------------------------------------- density --


def _bin_area(row_edges: np.ndarray, col_edges: np.ndarray) -> np.ndarray:
    """Area of every bin in mm^2, as an ``(rows, cols)`` matrix."""
    return np.outer(np.diff(row_edges), np.diff(col_edges))


def density_planes(bundle: CanonicalBundle) -> dict[str, np.ndarray]:
    """``<rho>`` on the accumulation grid for each panel, before any crop."""
    n = max(1, bundle.n_events)
    grid = bundle.grid
    z_edges = grid.axis("z").edges
    return {
        "xy": bundle.xy.planes["e"] / (n * _bin_area(grid.y_edges, grid.x_edges)),
        "yz": bundle.yz.planes["e"] / (n * _bin_area(grid.y_edges, z_edges)),
        "xz": bundle.xz.planes["e"] / (n * _bin_area(grid.x_edges, z_edges)),
    }


def raw_panel_peaks(bundle: CanonicalBundle) -> dict[str, float]:
    """Peak ``<rho>`` of each panel's own raw accumulation grid."""
    rho = density_planes(bundle)
    return {name: float(rho[name].max()) if rho[name].size else 0.0 for name in _PANELS}


def cam_energy_peaks(bundle: CanonicalBundle, channel: str) -> dict[str, float]:
    """Raw-grid peak of an energy-weighted CAM density: XY, and YZ + XZ shared.

    ``sum(E * CAM) / (N * dA)`` per bin, before any crop or reconstruction, so
    - exactly as for density - the peak bounds every displayed bin (the
    kernels are weighted means). Signed channels take the peak magnitude.
    """
    view = planes_mod.view(channel)
    n = max(1, bundle.n_events)
    grid = bundle.grid
    z_edges = grid.axis("z").edges
    areas = {
        "xy": _bin_area(grid.y_edges, grid.x_edges),
        "yz": _bin_area(grid.y_edges, z_edges),
        "xz": _bin_area(grid.x_edges, z_edges),
    }
    peaks = {}
    for name in _PANELS:
        plane = bundle.panel(name).planes
        value = sum(plane[p] for p in view.numerator) / (n * areas[name])
        peaks[name] = float(np.abs(value).max() if view.kind == KIND_SIGNED else value.max()) \
            if value.size else 0.0
    return {"xy": peaks["xy"], "depth": max(peaks["yz"], peaks["xz"])}


def selection_peaks(bundle: CanonicalBundle) -> dict[str, float]:
    """Peak ``<rho>`` on the accumulation grid: one for XY, one shared by YZ + XZ."""
    peaks = raw_panel_peaks(bundle)
    return {"xy": peaks["xy"], "depth": max(peaks["yz"], peaks["xz"])}


# ------------------------------------------------------------ resolution --


@dataclass(frozen=True)
class CanonicalPlan:
    """Destination bin counts and the kernel for the three cropped canonical panels."""

    mode: str
    requested: int
    pitch_mm: float
    display_pitch_mm: float
    xy: tuple[int, int]   # rows (y'), cols (x')
    yz: tuple[int, int]   # rows (y'), cols (z' layers)
    xz: tuple[int, int]   # rows (x'), cols (z' layers)
    merge: int = 1        # native-mode pairwise merge factor applied by the guard
    warnings: tuple[str, ...] = ()
    kernel: Kernel = kernel_mod.NONE

    def shape(self, name: str) -> tuple[int, int]:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def as_dict(self) -> dict[str, Any]:
        spread_pitch = self.pitch_mm if self.kernel.smooths else self.display_pitch_mm
        return {
            "mode": self.mode,
            "requested": self.requested,
            "r_x": self.xy[1],
            "r_y": self.xy[0],
            "r_z": self.yz[1],
            "pitch_mm": self.pitch_mm,
            "display_pitch_mm": self.display_pitch_mm,
            "merge": self.merge,
            "shapes": {"xy": list(self.xy), "yz": list(self.yz), "xz": list(self.xz)},
            "warnings": list(self.warnings),
            "kernel": self.kernel.as_dict(spread_pitch),
        }


def plan_canonical(
    fit: WindowFit,
    grid: frame_mod.CanonicalGrid,
    mode: str,
    resolution: int,
    merge: int = 1,
    kernel: Kernel | None = None,
    cell_mm: float | None = None,
    requested: int | None = None,
    depth_warning: str | None = None,
    axes: tuple[str, str] = reconstruct.RECONSTRUCTED_AXES,
    depth_clause: str | None = None,
) -> CanonicalPlan:
    """Bin counts and kernel per panel.

    *Native*: the accumulation pitch, no reconstruction - each cropped axis
    keeps its own bins (optionally merged pairwise by the budget guard) and the
    kernel is always ``none``. *Continuous*: one display pitch
    ``span_x(XY) / R`` shared by every transverse axis, so display bins stay
    square across panels; depth is always the native layers. The kernel
    defaults to :func:`reconstruct.choose_kernel` for the fit's event count.
    ``cell_mm`` (the measured footprint) only words a warning; ``requested``
    is the R the caller asked for, when the guard renders a lower one;
    ``depth_warning`` replaces the native-layer sentence for a frame whose
    depth axis is not the detector's layers (the local frame's w bins).
    """
    n_z = grid.n_z
    requested = int(resolution if requested is None else requested)
    if mode == MODE_NATIVE:
        m = max(1, int(merge))

        def merged(n: int) -> int:
            return max(1, -(-n // m))

        # The merged bins span each cropped axis evenly, so their width is
        # span / bins - under ``m`` accumulation bins when ``m`` does not
        # divide the axis - and differs between the four transverse axes.
        def width(axis: AxisFit) -> float:
            span = axis.hi - axis.lo
            return span / merged(axis.n_bins) if span > 0 else grid.pitch

        widths = [width(axis) for axis in (fit.xy.col, fit.xy.row, fit.yz.row, fit.xz.row)]
        # Along x′ on X′Y′, as the continuous display pitch is.
        display_pitch = widths[0] if m > 1 else grid.pitch
        warnings = []
        if m > 1:
            lo, hi = min(widths), max(widths)
            bins = f"{lo:.0f} mm" if hi - lo < 0.5 else f"{lo:.0f}-{hi:.0f} mm"
            warnings.append(
                f"Transverse bins merged {m}x pairwise to keep the payload under the "
                f"100 KB contract ({bins} display bins); depth layers are untouched."
            )
        return CanonicalPlan(
            mode=MODE_NATIVE, requested=requested, pitch_mm=grid.pitch,
            display_pitch_mm=display_pitch,
            xy=(merged(fit.xy.row.n_bins), merged(fit.xy.col.n_bins)),
            yz=(merged(fit.yz.row.n_bins), n_z),
            xz=(merged(fit.xz.row.n_bins), n_z),
            merge=m, warnings=tuple(warnings), kernel=kernel_mod.NONE,
        )

    if kernel is None:
        kernel = reconstruct.choose_kernel(mode, fit.n_events)
    r = max(MIN_RESOLUTION, int(resolution))
    span_x = fit.xy.col.hi - fit.xy.col.lo
    display_pitch = span_x / r if span_x > 0 else grid.pitch

    def bins(axis: AxisFit) -> int:
        span = axis.hi - axis.lo
        return max(1, int(round(span / display_pitch))) if span > 0 else 1

    warnings = [
        depth_warning or (
            f"Depth is locked to the {n_z} native sampling layers; there is no "
            "measurement between layers to interpolate."
        ),
        reconstruct.kernel_sentence(
            kernel, fit.n_events, grid.pitch, axes,
            depth_clause or "depth keeps its native sampling layers",
        ),
    ]
    if display_pitch < grid.pitch:
        cell = f"the {cell_mm:.1f} mm cell" if cell_mm else "the cell footprint"
        warnings.append(
            # ``r`` is the R rendered, which the payload guard may have lowered
            # below the one requested; the guard's own notice says so.
            f"R = {r} gives {display_pitch:.1f} mm display bins, finer than "
            f"the {grid.pitch:.0f} mm accumulation grid; the kernel fills them without "
            f"gaps, but no detail exists below the {grid.pitch:.0f} mm grid or {cell}."
        )
    return CanonicalPlan(
        mode=MODE_CONTINUOUS, requested=requested, pitch_mm=grid.pitch,
        display_pitch_mm=display_pitch,
        xy=(bins(fit.xy.row), r),
        yz=(bins(fit.yz.row), n_z),
        xz=(bins(fit.xz.row), n_z),
        warnings=tuple(warnings), kernel=kernel,
    )


# ---------------------------------------------------------------- render --


@dataclass
class RenderedPanel:
    payload: dict[str, Any]
    density: np.ndarray
    energy: np.ndarray
    row_edges: np.ndarray
    col_edges: np.ndarray


def axis_maps(
    bundle: CanonicalBundle, fit: PanelFit, plan: CanonicalPlan, name: str
) -> tuple[reconstruct.AxisMap, reconstruct.AxisMap]:
    """Row and column maps of one panel under ``plan``; depth always passes through."""
    grid = bundle.grid
    row_name, col_name = _PANEL_AXES[name]
    row_src = grid.axis(row_name).edges
    col_src = grid.axis(col_name).edges
    n_rows, n_cols = plan.shape(name)

    def transverse(src: np.ndarray, axis: AxisFit, n_dst: int) -> reconstruct.AxisMap:
        if plan.mode == MODE_NATIVE:
            return reconstruct.native_axis(src, axis, n_dst)
        return reconstruct.continuous_axis(src, axis, n_dst, plan.kernel, grid.pitch)

    row_map = transverse(row_src, fit.row, n_rows)
    col_map = reconstruct.passthrough(col_src) if col_name == "z" else transverse(col_src, fit.col, n_cols)
    return row_map, col_map


def _attention_mask(
    mask: np.ndarray, attention: np.ndarray, hits: np.ndarray, native: bool, decades: float
) -> dict[str, Any]:
    """What the Grad-CAM floor hid, in the channel's own terms.

    ``hit_fraction`` is the share of the panel's in-window hit count
    (reconstructed with the same operator) that lies in masked bins, and
    ``max_attention`` the largest attention among them. Many hits carry almost
    no energy: on production v37 the X'Y' mask at N = 5 (D 257-258 mm) holds
    20% of the hits but 0.8% of the energy, and the raw 20 mm grid puts 25% of
    the hits below the same floor.
    """
    if native:
        return {
            "rule": (
                "Native Grid: only bins with no hits are transparent (attention undefined); "
                "attention measured on real hits is always drawn."
            ),
            "cells": 0,
            "hit_fraction": 0.0,
            "max_attention": None,
        }
    total_hits = float(hits.sum())
    hidden = attention[mask]
    return {
        "rule": (
            "Continuous Field: attention is not drawn where the reconstructed energy density "
            f"is below {floor_label(decades)} of ρ_ref, because the kernel tails carry attention "
            "into bins no measured energy reached."
        ),
        "cells": int(mask.sum()),
        "hit_fraction": round(float(hits[mask].sum()) / total_hits, 8) if total_hits > 0 else 0.0,
        "max_attention": float(np.nanmax(hidden)) if hidden.size and np.isfinite(hidden).any() else None,
    }


def render_panel(
    bundle: CanonicalBundle,
    fit: PanelFit,
    plan: CanonicalPlan,
    name: str,
    channel: str,
    weighting: str,
    rho_ref: float,
    rho_norm: str,
    decades: float = frame_mod.RAMP_DECADES,
    symbols: dict[str, str] | None = None,
) -> RenderedPanel:
    """One panel: crop to its window, reconstruct, normalise, encode.

    For an energy-weighted CAM channel ``rho_ref`` is that channel's own
    raw-grid peak (:func:`cam_energy_peaks`), not the density's.
    """
    panel = bundle.panel(name)
    row_name, col_name = _PANEL_AXES[name]
    row_map, col_map = axis_maps(bundle, fit, plan, name)
    native = plan.mode == MODE_NATIVE

    energy = reconstruct.apply(panel.planes["e"], row_map, col_map)
    n_events = max(1, bundle.n_events)
    area = _bin_area(row_map.dst_edges, col_map.dst_edges)
    density = energy / (n_events * area)
    floor_ratio = 10.0 ** -float(decades)

    attention_mask = None
    view = planes_mod.view(channel, weighting)
    populated = None
    below_code = quantize.BELOW_CODE
    cam_parts = None
    if view.kind == KIND_RATIO:
        num = panel.planes[view.numerator[0]]
        for name_ in view.numerator[1:]:
            num = num + panel.planes[name_]
        den = panel.planes[view.denominator]
        attention = reconstruct.apply_ratio(num, den, row_map, col_map)
        if channel == CHANNEL_GRADCAM:
            scale = scale_mod.resolve_scale(attention, channel=CHANNEL_GRADCAM)
            scale.quantity = CHANNEL_GRADCAM
            finite = attention[np.isfinite(attention)]
            scale.n_below = int((finite < 0).sum())
            scale.n_above = int((finite > 1).sum())
        else:
            scale = scale_mod.attention_scale(attention, channel, -1.0, 1.0, "attribution")
        encoded = attention
        if native or rho_ref <= 0:
            below = np.zeros(attention.shape, dtype=bool)
        else:
            below = np.isfinite(attention) & (density < floor_ratio * rho_ref)
        hits = reconstruct.apply(panel.planes["n"], row_map, col_map)
        attention_mask = _attention_mask(below, attention, hits, native, decades)
        exact = topk.top_cells(np.where(below, np.nan, attention), signed=scale.diverging)
        mask_arg = below
    elif view.is_cam:
        # Energy-weighted CAM: sum(E * CAM) per bin as an areal density, like
        # <rho>, shown relative to its own raw-grid peak (``rho_ref`` here).
        cam_parts = [reconstruct.apply(panel.planes[p], row_map, col_map) for p in view.numerator]
        cam_sum = cam_parts[0] if len(cam_parts) == 1 else cam_parts[0] + cam_parts[1]
        value = cam_sum / (n_events * area)
        ratio = value / rho_ref if rho_ref > 0 else np.zeros_like(value)
        populated = energy > 0
        if view.kind == KIND_SIGNED:
            scale = scale_mod.signed_log_scale(
                ratio, populated, rho_ref, RHO_UNIT, channel,
                positive_total=float(cam_parts[0].sum()),
                negative_total=float(cam_parts[1].sum()),
                split_code=quantize.SPLIT_CODE, decades=decades,
            )
            undrawn = populated & ~(np.abs(ratio) >= floor_ratio)
        else:
            scale = scale_mod.extensive_cam_scale(
                ratio, populated, rho_ref, RHO_UNIT, channel, decades=decades,
            )
            undrawn = populated & ~(ratio >= floor_ratio)
        encoded = ratio
        below = undrawn
        exact = topk.top_cells(np.where(undrawn | ~populated, np.nan, value),
                               signed=view.kind == KIND_SIGNED)
        mask_arg = None
    else:
        ratio = density / rho_ref if rho_ref > 0 else np.zeros_like(density)
        scale = scale_mod.relative_log_scale(
            ratio, rho_ref, decades, rho_norm, RHO_UNIT, floor=scale_mod.FLOOR_TRANSPARENT
        )
        encoded = ratio
        below = quantize.below_floor_mask(ratio, scale)
        # Exact values are shipped in physical units; the client divides by
        # ``scale.rho_ref`` for the a.u. reading. Undrawn bins are not offered.
        exact = topk.top_cells(np.where(below, np.nan, density))
        mask_arg = None

    payload = matrix_encode.encode_matrix(
        encoded, scale,
        row_edges=row_map.dst_edges, col_edges=col_map.dst_edges,
        row_axis=row_name, col_axis=col_name,
        panel=name, native=native,
        symbols=symbols or SYMBOLS,
        below_code=below_code, below_mask=mask_arg,
        top=exact, populated=populated,
    )
    # ``total`` keeps the lab meaning - energy in GeV - rather than a sum of
    # ratios, and is the energy the rendered window holds after reconstruction.
    total = float(energy.sum())
    total_all = float(panel.planes["e"].sum())
    outside = min(1.0, max(0.0, 1.0 - total / total_all)) if total_all > 0 else 0.0
    below_energy = float(energy[below].sum()) if below.any() else 0.0

    payload["topk_unit"] = (
        "attention" if channel == CHANNEL_GRADCAM
        else "attribution" if view.kind == KIND_RATIO
        else RHO_UNIT
    )
    if cam_parts is not None:
        # The panel's in-window sum of E x CAM after reconstruction - the
        # quantity every conservative operator preserves (signed for Shap-CAM).
        payload["cam_total"] = float(sum(part.sum() for part in cam_parts))
        # ...and on the whole raw accumulation grid, before the crop: this is
        # the figure that must equal the SQL sum over the selected hits.
        payload["cam_total_all"] = float(sum(panel.planes[p].sum() for p in view.numerator))
        plane_out = getattr(bundle, "plane_outside", {}) or {}
        payload["cam_total_outside_grid"] = float(sum(plane_out.get(p, 0.0) for p in view.numerator))
    payload["kernel"] = plan.kernel.name
    payload["total"] = total
    payload["total_energy_all_gev"] = total_all
    payload["energy_outside_window_gev"] = max(0.0, total_all - total)
    payload["energy_fraction_outside_window"] = round(outside, 8)
    payload["energy_fraction_outside_window_raw"] = round(fit.energy_fraction_outside, 8)
    payload["below_floor_energy_fraction"] = round(below_energy / total, 8) if total > 0 else 0.0
    if attention_mask is not None:
        payload["attention_mask"] = attention_mask
    payload["n_events"] = bundle.n_events
    payload["bin_area_mm2"] = [float(area.min()), float(area.max())] if area.size else [0.0, 0.0]
    payload["rho_peak"] = float(density.max()) if density.size else 0.0
    payload["rho_unit"] = RHO_UNIT
    return RenderedPanel(payload, density, energy, row_map.dst_edges, col_map.dst_edges)


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 6) if den > 0 else None


# ----------------------------------------------------------------- guard --


def raster_bytes(plan: CanonicalPlan) -> int:
    """A lower bound on the panels' encoded size: their base64 rasters alone.

    Known from the bin counts before anything is rendered. Every other field
    only adds bytes, so an attempt whose rasters already exceed the limit
    cannot fit, and the guard steps past it without building its operators:
    at R = 400 on the production N = 3 slice (D 246.39-246.54 mm) the first
    four attempts measured 140-550 KB, and rendering each cost 20-30 ms.
    """
    return sum(4 * -(-(rows * cols) // 3) for rows, cols in (plan.xy, plan.yz, plan.xz))


def next_resolution(r: int, requested: int) -> int:
    """The guard's next R below ``r``: a quarter lower, never stepping over the default.

    A geometric sequence from a high request - 400, 300, 225, 168, 126 -
    passes R = 150 by, so asking for more detail could serve less than the
    default request does: on production v37, D 20-40 mm, R = 300 and 400 both
    served 126 where R = 150 serves 150. A step that would cross the default
    lands on it instead, so from there on every request at or above the
    default walks the default's own sequence and never ends coarser.
    """
    new_r = max(MIN_RESOLUTION, int(r * 0.75))
    anchor = min(int(requested), DEFAULT_RESOLUTION)
    return anchor if new_r < anchor < r else new_r


def _collapsed(plan: CanonicalPlan) -> bool:
    """Whether every transverse axis is already a single bin, so merging changes nothing."""
    return plan.xy == (1, 1) and plan.yz[0] == 1 and plan.xz[0] == 1


def render_canonical(
    bundle: CanonicalBundle,
    fit: WindowFit,
    mode: str,
    resolution: int,
    channel: str = CHANNEL_DENSITY,
    weighting: str = "energy",
    rho_norm: str = NORM_SELECTION,
    reference: dict[str, float] | None = None,
    limit: int | None = None,
    kernel: Kernel | None = None,
    start: tuple[int, int] | None = None,
    symbols: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render all three panels within the payload budget.

    Returns ``{"panels", "resolution", "rho", "notices", "reconstruction",
    "guard"}``. ``reference`` is the dataset-wide peak pair ``{xy, depth}``
    when ``rho_norm == "dataset"``; the selection's own peaks are used
    otherwise and always reported. ``limit`` defaults to
    :data:`PAYLOAD_LIMIT` at call time; ``kernel`` to
    :func:`reconstruct.choose_kernel` for the bundle's exact N.

    ``start`` is an ``(r, merge)`` guard state to render from instead of the
    requested R; the whole-response check in ``api/frame_canonical.py`` uses it
    to continue this guard's own sequence rather than restart it. ``guard``
    reports the state served (``r``, ``merge``, the panels' ``bytes``),
    whether it ``fits`` the limit, and ``next``, the state the guard would
    step to from there (``None`` once no step changes anything); it is
    bookkeeping for the caller and is not part of the response.
    """
    if limit is None:
        limit = PAYLOAD_LIMIT
    if kernel is None:
        kernel = reconstruct.choose_kernel(mode, bundle.n_events)
    raw_peaks = raw_panel_peaks(bundle)
    peaks = selection_peaks(bundle)
    if rho_norm == NORM_DATASET and reference:
        ref = {"xy": float(reference.get("xy") or peaks["xy"]),
               "depth": float(reference.get("depth") or peaks["depth"])}
        ref_k = int(reference.get("k") or 0) or None
    else:
        rho_norm = NORM_SELECTION
        ref = dict(peaks)
        ref_k = bundle.subsample_k
    ref_of = {"xy": ref["xy"], "yz": ref["depth"], "xz": ref["depth"]}
    view = planes_mod.view(channel, weighting)
    cam_ref = None
    if view.is_cam and view.kind != KIND_RATIO:
        # Energy-weighted CAM: relative to the selection's own raw-grid peak of
        # the same quantity. A dataset reference exists for density only.
        cam_ref = cam_energy_peaks(bundle, channel)
        ref_of = {"xy": cam_ref["xy"], "yz": cam_ref["depth"], "xz": cam_ref["depth"]}
    cell = max(bundle.footprint) if bundle.footprint else None

    notices: list[str] = []
    requested = int(resolution)
    r, merge = (int(start[0]), max(1, int(start[1]))) if start else (requested, 1)
    fits = False
    for attempt in range(MAX_ATTEMPTS):
        plan = plan_canonical(fit, bundle.grid, mode, r, merge, kernel, cell, requested=requested,
                              depth_warning=getattr(bundle, "depth_warning", None),
                              axes=((symbols or SYMBOLS)["x"], (symbols or SYMBOLS)["y"]),
                              depth_clause=getattr(bundle, "depth_clause", None))
        continuous = plan.mode == MODE_CONTINUOUS
        # The step this attempt would take if it is over, or None when no step
        # changes anything any more: R at its minimum, or every transverse axis
        # merged down to one bin.
        if continuous:
            new_r = next_resolution(r, requested)
            step = (new_r, merge) if new_r != r else None
        else:
            step = None if _collapsed(plan) else (r, merge * 2)
        last = attempt == MAX_ATTEMPTS - 1 or step is None

        # An attempt whose rasters alone are over is stepped past without
        # rendering - but only when another attempt follows, so something is
        # always rendered and served.
        lower = raster_bytes(plan)
        if not last and lower > limit:
            measured = f"its rasters alone {lower:,} bytes"
        else:
            panels: dict[str, dict[str, Any]] = {}
            for name in _PANELS:
                rendered = render_panel(
                    bundle, fit.panel(name), plan, name, channel, weighting, ref_of[name], rho_norm,
                    symbols=symbols,
                )
                panels[name] = rendered.payload
            for name in ("yz", "xz"):
                panels[name]["scale"]["shared_with"] = "yz+xz"

            # Deliberately the default (ASCII-escaped, spaced) encoding: it
            # over-counts the wire form, so the guard errs towards fitting.
            size = len(json.dumps(panels).encode())
            if size <= limit:
                fits = True
                break
            # Degrade only when another attempt follows, so every notice
            # describes a step the returned panels actually took.
            if attempt == MAX_ATTEMPTS - 1:
                notices.append(
                    f"The panels are still {size:,} bytes after {MAX_ATTEMPTS} attempts against a "
                    f"{limit:,}-byte limit and are served as they are."
                )
                break
            if step is None:
                where = (
                    f"at the minimum resolution R = {r}" if continuous
                    else "with every transverse axis merged into a single bin"
                )
                notices.append(
                    f"The panels are still {size:,} bytes {where} against a {limit:,}-byte "
                    "limit and are served as they are."
                )
                break
            measured = f"{size:,} bytes"

        if continuous:
            notices.append(
                f"Resolution lowered from R = {r} to R = {step[0]} to keep the payload "
                f"under the 100 KB contract ({measured} at R = {r})."
            )
        else:
            notices.append(
                f"Transverse bins merged {step[1]}x to keep the payload under the 100 KB "
                f"contract ({measured} before merging)."
            )
        r, merge = step

    displayed = {name: float(panels[name]["rho_peak"]) for name in _PANELS}
    scope = "this selection" if rho_norm == NORM_SELECTION else "the whole dataset"
    return {
        "panels": panels,
        "resolution": plan.as_dict(),
        "rho": {
            "norm": rho_norm,
            "ref": ref,
            "ref_k": ref_k,
            "selection_k": bundle.subsample_k,
            "selection_peak": peaks,
            "unit": RHO_UNIT,
            "decades": frame_mod.RAMP_DECADES,
            "basis": (
                f"peak of the raw {bundle.grid.pitch:.0f} mm accumulation grid of {scope}, "
                "before display reconstruction"
            ),
            "displayed_peak": displayed,
            "displayed_over_ref": {name: _ratio(displayed[name], ref_of[name]) for name in _PANELS},
            "kernel_attenuation": {name: _ratio(displayed[name], raw_peaks[name]) for name in _PANELS},
        },
        "cam_ref": None if cam_ref is None else {
            "channel": channel, "ref": cam_ref, "unit": RHO_UNIT,
            "basis": (
                f"peak of sum(E x CAM) / (N x dA) on the raw {bundle.grid.pitch:.0f} mm "
                "accumulation grid of this selection"
                + (", in magnitude" if view.kind == KIND_SIGNED else "")
            ),
        },
        "notices": notices,
        "reconstruction": reconstruct.reconstruction_report(plan, bundle, panels),
        "guard": {"r": r, "merge": merge, "bytes": size, "limit": limit, "fits": fits, "next": step},
    }
