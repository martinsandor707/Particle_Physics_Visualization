"""Render a canonical bundle: crop, resample, normalise to a density, encode.

**The quantity.** Each bin carries the ensemble-averaged projected surface
energy density::

    <rho> = sum(E) / (N_frame * dA)      [GeV / mm^2 / event]

Dividing by the number of co-registered events makes selections of different
size comparable; dividing by the bin area makes the value independent of the
display resolution. Area-weighted resampling (``grid/splat.py``) conserves the
energy sum, so the density of a coarser bin is the area-weighted mean of the
finer ones and can never exceed the finest-grid peak.

**The colour.** The ramp is dimensionless: ``<rho> / rho_ref`` on a log scale
spanning ``RAMP_DECADES`` below 1.0, labelled ``Average hit density (a.u.)`` as
the directive asks. The reference ``rho_ref`` is either the selection's own
peak (default, so every selection uses the whole ramp) or the peak of the whole
dataset (so colours stay comparable across D slices - the colour-lock argument
of ``encode/scale.py``); which one, and its value in GeV/mm^2/event, travels in
the payload and is printed on the panel, so a reader can always recover the
physical density. Tooltips show both.

**Payload budget.** A wide, flat canonical window can push a fine raster past
the 100 KB contract. The guard here degrades deterministically and says so:
in continuous mode it lowers R by a quarter per step; in native mode it merges
transverse bins pairwise - never depth layers, which stay native.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..encode import matrix as matrix_encode
from ..encode import scale as scale_mod
from ..encode import topk
from ..grid import frame as frame_mod
from ..grid import splat
from ..grid.resolution import MIN_RESOLUTION, MODE_CONTINUOUS, MODE_NATIVE
from .canonical import CanonicalBundle
from .panels import CHANNEL_DENSITY, CHANNEL_GRADCAM, WEIGHTING_COUNT
from .window import AxisFit, PanelFit, WindowFit

#: How the canonical axes are written; the semantic names stay x, y, z.
SYMBOLS = {"x": "x′", "y": "y′", "z": "z′"}

RHO_UNIT = "GeV/mm^2/event"

NORM_SELECTION = "selection"
NORM_DATASET = "dataset"
NORMS = (NORM_SELECTION, NORM_DATASET)

#: Encoded-size ceiling the guard steers under; the contract is 100 KB and the
#: envelope around the panels needs a few KB of its own.
PAYLOAD_LIMIT = 96_000

_PANEL_AXES = {"xy": ("y", "x"), "yz": ("y", "z"), "xz": ("x", "z")}


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


def selection_peaks(bundle: CanonicalBundle) -> dict[str, float]:
    """Peak ``<rho>`` on the accumulation grid: one for XY, one shared by YZ + XZ."""
    rho = density_planes(bundle)
    xy = float(rho["xy"].max()) if rho["xy"].size else 0.0
    depth = max(
        float(rho["yz"].max()) if rho["yz"].size else 0.0,
        float(rho["xz"].max()) if rho["xz"].size else 0.0,
    )
    return {"xy": xy, "depth": depth}


# ------------------------------------------------------------ resolution --


@dataclass(frozen=True)
class CanonicalPlan:
    """Destination bin counts for the three cropped canonical panels."""

    mode: str
    requested: int
    pitch_mm: float
    display_pitch_mm: float
    xy: tuple[int, int]   # rows (y'), cols (x')
    yz: tuple[int, int]   # rows (y'), cols (z' layers)
    xz: tuple[int, int]   # rows (x'), cols (z' layers)
    merge: int = 1        # native-mode pairwise merge factor applied by the guard
    warnings: tuple[str, ...] = ()

    def shape(self, name: str) -> tuple[int, int]:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def as_dict(self) -> dict[str, Any]:
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
        }


def plan_canonical(
    fit: WindowFit,
    grid: frame_mod.CanonicalGrid,
    mode: str,
    resolution: int,
    merge: int = 1,
) -> CanonicalPlan:
    """Bin counts per panel.

    *Native*: the accumulation pitch, no resampling - each cropped axis keeps
    its own bins (optionally merged pairwise by the budget guard). *Continuous*:
    one display pitch ``span_x(XY) / R`` shared by every transverse axis, so
    display bins stay square across panels; depth is always the native layers.
    """
    n_z = grid.n_z
    if mode == MODE_NATIVE:
        m = max(1, int(merge))

        def merged(n: int) -> int:
            return max(1, -(-n // m))

        display_pitch = grid.pitch * m
        warnings = []
        if m > 1:
            warnings.append(
                f"Transverse bins merged {m}x pairwise to keep the payload under the "
                f"100 KB contract ({display_pitch:.0f} mm display bins); depth layers "
                "are untouched."
            )
        return CanonicalPlan(
            mode=MODE_NATIVE, requested=resolution, pitch_mm=grid.pitch,
            display_pitch_mm=display_pitch,
            xy=(merged(fit.xy.row.n_bins), merged(fit.xy.col.n_bins)),
            yz=(merged(fit.yz.row.n_bins), n_z),
            xz=(merged(fit.xz.row.n_bins), n_z),
            merge=m, warnings=tuple(warnings),
        )

    r = max(MIN_RESOLUTION, int(resolution))
    span_x = fit.xy.col.hi - fit.xy.col.lo
    display_pitch = span_x / r if span_x > 0 else grid.pitch

    def bins(axis: AxisFit) -> int:
        span = axis.hi - axis.lo
        return max(1, int(round(span / display_pitch))) if span > 0 else 1

    warnings = [
        f"Depth is locked to the {n_z} native sampling layers; there is no "
        "measurement between layers to interpolate."
    ]
    if display_pitch < grid.pitch:
        warnings.append(
            f"Requested R = {r} gives {display_pitch:.1f} mm display bins, finer than "
            f"the {grid.pitch:.0f} mm accumulation grid; area-weighted resampling keeps "
            "the image free of gaps, but no finer detail exists."
        )
    return CanonicalPlan(
        mode=MODE_CONTINUOUS, requested=resolution, pitch_mm=grid.pitch,
        display_pitch_mm=display_pitch,
        xy=(bins(fit.xy.row), r),
        yz=(bins(fit.yz.row), n_z),
        xz=(bins(fit.xz.row), n_z),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------- render --


def _destination(
    src_edges: np.ndarray, axis: AxisFit, n_dst: int, passthrough: bool
) -> tuple[np.ndarray | None, np.ndarray]:
    """Overlap operator and destination edges for one cropped axis."""
    cropped = src_edges[axis.lo_index:axis.hi_index + 1]
    n_src = cropped.size - 1
    if passthrough or n_dst == n_src:
        return None, cropped
    dst = splat.uniform_edges(float(cropped[0]), float(cropped[-1]), n_dst)
    return splat.overlap_matrix(cropped, dst), dst


@dataclass
class RenderedPanel:
    payload: dict[str, Any]
    density: np.ndarray
    energy: np.ndarray
    row_edges: np.ndarray
    col_edges: np.ndarray


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
) -> RenderedPanel:
    """One panel: crop to its window, resample, normalise, encode."""
    panel = bundle.panel(name)
    grid = bundle.grid
    row_name, col_name = _PANEL_AXES[name]
    row_src = grid.axis(row_name).edges
    col_src = grid.axis(col_name).edges
    n_rows, n_cols = plan.shape(name)
    depth_cols = col_name == "z"

    row_op, row_edges = _destination(row_src, fit.row, n_rows, False)
    col_op, col_edges = _destination(col_src, fit.col, n_cols, depth_cols)

    energy = splat.resample(fit.crop(panel.planes["e"]), row_op, col_op)
    n_events = max(1, bundle.n_events)
    area = _bin_area(row_edges, col_edges)
    density = energy / (n_events * area)

    if channel == CHANNEL_GRADCAM:
        if weighting == WEIGHTING_COUNT:
            num, den = panel.planes["g"], panel.planes["n"]
        else:
            num, den = panel.planes["eg"], panel.planes["e"]
        attention = splat.resample_ratio(fit.crop(num), fit.crop(den), row_op, col_op)
        scale = scale_mod.resolve_scale(attention, channel=CHANNEL_GRADCAM)
        encoded = attention
        exact = topk.top_cells(attention)
    else:
        ratio = density / rho_ref if rho_ref > 0 else np.zeros_like(density)
        scale = scale_mod.relative_log_scale(ratio, rho_ref, decades, rho_norm, RHO_UNIT)
        encoded = ratio
        # Exact values are shipped in physical units; the client divides by
        # ``scale.rho_ref`` for the a.u. reading.
        exact = topk.top_cells(density)

    payload = matrix_encode.encode_matrix(
        encoded, scale,
        row_edges=row_edges, col_edges=col_edges,
        row_axis=row_name, col_axis=col_name,
        panel=name, native=plan.mode == MODE_NATIVE,
        symbols=SYMBOLS,
    )
    payload["topk"] = exact
    payload["topk_unit"] = RHO_UNIT if channel != CHANNEL_GRADCAM else "attention"
    # ``total`` keeps the lab meaning - energy in GeV - rather than a sum of ratios.
    payload["total"] = float(energy.sum())
    payload["total_energy_all_gev"] = float(panel.planes["e"].sum())
    payload["n_events"] = bundle.n_events
    payload["energy_fraction_outside_window"] = round(fit.energy_fraction_outside, 8)
    payload["bin_area_mm2"] = [float(area.min()), float(area.max())] if area.size else [0.0, 0.0]
    payload["rho_peak"] = float(density.max()) if density.size else 0.0
    payload["rho_unit"] = RHO_UNIT
    return RenderedPanel(payload, density, energy, row_edges, col_edges)


def render_canonical(
    bundle: CanonicalBundle,
    fit: WindowFit,
    mode: str,
    resolution: int,
    channel: str = CHANNEL_DENSITY,
    weighting: str = "energy",
    rho_norm: str = NORM_SELECTION,
    reference: dict[str, float] | None = None,
    limit: int = PAYLOAD_LIMIT,
) -> dict[str, Any]:
    """Render all three panels within the payload budget.

    Returns ``{"panels", "resolution", "rho", "notices"}``. ``reference`` is the
    dataset-wide peak pair ``{xy, depth}`` when ``rho_norm == "dataset"``; the
    selection's own peaks are used otherwise and always reported.
    """
    peaks = selection_peaks(bundle)
    if rho_norm == NORM_DATASET and reference:
        ref = {"xy": float(reference.get("xy") or peaks["xy"]),
               "depth": float(reference.get("depth") or peaks["depth"])}
        ref_k = int(reference.get("k") or 0) or None
    else:
        rho_norm = NORM_SELECTION
        ref = dict(peaks)
        ref_k = bundle.subsample_k

    notices: list[str] = []
    r = int(resolution)
    merge = 1
    for _attempt in range(12):
        plan = plan_canonical(fit, bundle.grid, mode, r, merge)
        panels: dict[str, dict[str, Any]] = {}
        for name in ("xy", "yz", "xz"):
            rho_ref = ref["xy"] if name == "xy" else ref["depth"]
            rendered = render_panel(
                bundle, fit.panel(name), plan, name, channel, weighting, rho_ref, rho_norm
            )
            panels[name] = rendered.payload
        for name in ("yz", "xz"):
            panels[name]["scale"]["shared_with"] = "yz+xz"

        size = len(json.dumps(panels).encode())
        if size <= limit:
            break
        # Degrade deterministically and disclose it.
        if plan.mode == MODE_CONTINUOUS:
            new_r = max(MIN_RESOLUTION, int(r * 0.75))
            if new_r == r:
                break
            notices.append(
                f"Resolution lowered from R = {r} to R = {new_r} to keep the payload "
                f"under the 100 KB contract ({size:,} bytes at R = {r})."
            )
            r = new_r
        else:
            merge *= 2
            notices.append(
                f"Transverse bins merged {merge}x to keep the payload under the 100 KB "
                f"contract ({size:,} bytes before merging)."
            )
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
        },
        "notices": notices,
    }
