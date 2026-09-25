"""Turn a cached native-resolution bundle into rendered panel payloads.

This is the step that makes the resolution and display-mode controls cheap.
Nothing here touches the database: it resamples the cached native matrices,
picks the requested measurement channel, and encodes the result.

**Channel handling is not symmetric, and must not be.**

*Density* and the *energy-weighted CAM* channels (sum of E x Grad-CAM, and the
signed sum of E x Shap-CAM) are extensive sums. Resampling them directly
conserves the total exactly - positive and negative Shap-CAM parts each on
their own - and the energy-weighted channels are drawn relative to the peak of
the panel (XY) or of the two depth panels together.

*Grad-CAM attention* and *Shap-CAM attribution* are means - intensive
quantities. Resampling a mean would average averages, weighting every source
cell equally regardless of how much energy it holds. The numerator and
denominator are resampled separately and divided at the destination
resolution instead; a weighted mean of values in [0, 1] (Grad-CAM) or
[-1, +1] (Shap-CAM) stays inside that range, so the fixed linear ramps clip
nothing.

The default Grad-CAM weighting is by **energy**, not by hit count. The literal
``AVG(gradcam_energy)`` of the brief is count-weighted, and on this dataset the
sea of sub-femto-GeV dust hits vastly outnumbers the shower core, so that form
produces a near-uniform attention map that says nothing. The count-weighted form
remains available for comparison.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..encode import matrix as matrix_encode
from ..encode import quantize, topk
from ..encode import scale as scale_mod
from ..grid import splat
from ..grid.resolution import MODE_NATIVE, ResolutionPlan
from . import planes as planes_mod
# The channel vocabulary lives in planes.py; re-exported here for callers.
from .planes import (
    CHANNEL_DENSITY, CHANNEL_GRADCAM, CHANNEL_GRADCAM_ENERGY, CHANNEL_SHAPCAM,
    CHANNEL_SHAPCAM_ENERGY, CHANNELS, KIND_EXTENSIVE, KIND_RATIO, KIND_SIGNED,
    WEIGHTING_COUNT, WEIGHTING_ENERGY, WEIGHTINGS,
)
from .projections import NativeBundle, Panel

#: Decades below the selection peak an energy-weighted CAM ramp spans.
CAM_ENERGY_DECADES = 3.0

#: Destination bin counts per panel, as (rows, cols).
_PANEL_AXES = {
    "xy": ("y", "x"),
    "yz": ("y", "z"),
    "xz": ("x", "z"),
}


def _plan_shape(plan: ResolutionPlan, panel: str) -> tuple[int, int]:
    return {
        "xy": plan.shape_xy,
        "yz": plan.shape_yz,
        "xz": plan.shape_xz,
    }[panel]


def _operators(bundle: NativeBundle, panel_name: str, plan: ResolutionPlan):
    lattice = bundle.lattice
    row_axis_name, col_axis_name = _PANEL_AXES[panel_name]
    native = plan.mode == MODE_NATIVE
    n_rows, n_cols = _plan_shape(plan, panel_name)
    row_edges_src = lattice.axis(row_axis_name).edges
    col_edges_src = lattice.axis(col_axis_name).edges
    return {
        "row_axis": row_axis_name,
        "col_axis": col_axis_name,
        "native": native,
        "row_op": splat.build_axis_operator(row_edges_src, n_rows, native),
        "col_op": splat.build_axis_operator(col_edges_src, n_cols, native),
        "row_edges": splat.destination_edges(row_edges_src, n_rows, native),
        "col_edges": splat.destination_edges(col_edges_src, n_cols, native),
    }


def _sum_planes(panel: Panel, names: tuple[str, ...]) -> np.ndarray:
    total = panel.planes[names[0]].copy()
    for name in names[1:]:
        total = total + panel.planes[name]
    return total


def render_panel(
    bundle: NativeBundle,
    panel_name: str,
    plan: ResolutionPlan,
    channel: str = CHANNEL_DENSITY,
    weighting: str = WEIGHTING_ENERGY,
    global_vmax: float | None = None,
    lock_scale: bool = True,
    scale_mode: str = scale_mod.MODE_DECADES,
    ref: float | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    """Resample and encode one panel. Returns ``(payload, resampled_matrix)``.

    ``ref`` is the peak an energy-weighted CAM channel is shown against; it
    defaults to this panel's own resampled peak (``render_all`` passes the
    shared depth-panel peak).
    """
    panel: Panel = bundle.panel(panel_name)
    ops = _operators(bundle, panel_name, plan)
    view = planes_mod.view(channel, weighting)
    encode_kwargs: dict[str, Any] = {}

    if view.kind == KIND_RATIO:
        numerator = _sum_planes(panel, view.numerator)
        resampled = splat.resample_ratio(
            numerator, panel.planes[view.denominator], ops["row_op"], ops["col_op"]
        )
        if channel == CHANNEL_GRADCAM:
            scale = scale_mod.resolve_scale(resampled, channel=CHANNEL_GRADCAM)
            scale.n_below = int((resampled[np.isfinite(resampled)] < 0).sum())
            scale.n_above = int((resampled[np.isfinite(resampled)] > 1).sum())
            scale.quantity = CHANNEL_GRADCAM
        else:
            scale = scale_mod.attention_scale(resampled, CHANNEL_SHAPCAM, -1.0, 1.0, "attribution")
    elif channel == CHANNEL_DENSITY:
        resampled = splat.resample(panel.planes["e"], ops["row_op"], ops["col_op"])
        scale = scale_mod.resolve_scale(
            resampled,
            channel=channel,
            mode=scale_mode,
            global_vmax=global_vmax,
            lock=lock_scale,
        )
    else:
        # Energy-weighted CAM: an extensive sum, resampled like energy and shown
        # relative to a stated peak. A bin with hits is populated whatever its
        # weighted attention sums to.
        energy = splat.resample(panel.planes["e"], ops["row_op"], ops["col_op"])
        populated = energy > 0
        parts = [splat.resample(panel.planes[name], ops["row_op"], ops["col_op"])
                 for name in view.numerator]
        resampled = parts[0] if len(parts) == 1 else parts[0] + parts[1]
        peak = ref if ref is not None else _peak(resampled, view.kind)
        ratio = resampled / peak if peak and peak > 0 else np.zeros_like(resampled)
        if view.kind == KIND_SIGNED:
            scale = scale_mod.signed_log_scale(
                ratio, populated, peak, "GeV", channel,
                positive_total=float(parts[0].sum()), negative_total=float(parts[1].sum()),
                split_code=quantize.SPLIT_CODE, decades=CAM_ENERGY_DECADES,
            )
        else:
            scale = scale_mod.extensive_cam_scale(
                ratio, populated, peak, "GeV", channel, decades=CAM_ENERGY_DECADES,
            )
            encode_kwargs["below_code"] = quantize.BELOW_CODE
        encode_kwargs["populated"] = populated
        # Exact values in GeV (E x CAM), not the ratio the raster encodes.
        encode_kwargs["top"] = topk.top_cells(
            np.where(populated, resampled, np.nan), signed=view.kind == KIND_SIGNED
        )
        payload = matrix_encode.encode_matrix(
            ratio, scale,
            row_edges=ops["row_edges"], col_edges=ops["col_edges"],
            row_axis=ops["row_axis"], col_axis=ops["col_axis"],
            panel=panel_name, native=ops["native"], **encode_kwargs,
        )
        # `total` keeps a physical meaning: the panel's sum of E x CAM, which
        # every resampling conserves (signed for Shap-CAM).
        payload["total"] = float(resampled.sum())
        payload["topk_unit"] = "GeV"
        return payload, resampled

    payload = matrix_encode.encode_matrix(
        resampled,
        scale,
        row_edges=ops["row_edges"],
        col_edges=ops["col_edges"],
        row_axis=ops["row_axis"],
        col_axis=ops["col_axis"],
        panel=panel_name,
        native=ops["native"],
    )
    return payload, resampled


def _peak(matrix: np.ndarray, kind: str) -> float:
    values = np.asarray(matrix, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if not finite.size:
        return 0.0
    return float(np.abs(finite).max() if kind == KIND_SIGNED else finite.max())


def cam_energy_peaks(bundle: NativeBundle, plan: ResolutionPlan, channel: str) -> dict[str, float]:
    """The peaks the energy-weighted CAM panels are shown against: XY, and YZ + XZ shared."""
    view = planes_mod.view(channel)
    peaks = {}
    for name in ("xy", "yz", "xz"):
        ops = _operators(bundle, name, plan)
        panel = bundle.panel(name)
        value = _sum_planes(panel, view.numerator)
        peaks[name] = _peak(splat.resample(value, ops["row_op"], ops["col_op"]), view.kind)
    return {"xy": peaks["xy"], "depth": max(peaks["yz"], peaks["xz"])}


#: A depth column must hold at least this fraction of the panel's peak column
#: energy before its centroid is plotted. Columns in the far tail hold a handful
#: of stray hits whose centroid is dominated by noise, and joining them to the
#: shower core produces a line that lurches to the detector edge.
AXIS_MIN_COLUMN_FRACTION = 1e-3


def shower_axes(bundle: NativeBundle, panel_name: str) -> dict[str, Any]:
    """Energy-weighted transverse centroid against depth, per shower.

    This is the honest always-available answer to "where did each shower go".
    It is measured from the same binned data the panel displays, so it cannot
    disagree with the picture, and unlike an averaged incident direction it
    stays meaningful at any event count - the azimuths that refuse to average
    (see ``summary.angular_coherence``) have already been folded into the energy
    distribution being summarised here.

    The attribution between showers uses the fractional voxel weights, for the
    same reason ``centroids.py`` does: the categorical ``particle_origin`` label
    discards the overlap region, which is the region under study.

    Computed in NumPy from the cached native-resolution bundle, so it costs no
    database access and is free on a cache hit.
    """
    panel = bundle.panel(panel_name)
    # Coordinates through ``bundle.axis`` so a canonical-frame bundle, whose
    # axes are a uniform grid rather than detector cells, is measured the same way.
    row_axis = bundle.axis(panel.row_axis)

    energy = panel.planes["e"]
    weights = {
        "a": panel.planes["efa_true"],
        "b": np.clip(energy - panel.planes["efa_true"], 0.0, None),
    }

    depth = bundle.axis("z").coords
    out: dict[str, Any] = {"depth": [float(v) for v in depth], "a": [], "b": []}

    for shower, w in weights.items():
        column_total = w.sum(axis=0)
        peak = float(column_total.max()) if column_total.size else 0.0
        floor = peak * AXIS_MIN_COLUMN_FRACTION

        points: list[list[float] | None] = []
        for j in range(w.shape[1]):
            total = float(column_total[j])
            if total <= floor or total <= 0:
                points.append(None)
                continue
            centroid = float(np.dot(w[:, j], row_axis.coords) / total)
            points.append([float(depth[j]), centroid])
        out[shower] = points

    return out


def render_all(
    bundle: NativeBundle,
    plan: ResolutionPlan,
    channel: str = CHANNEL_DENSITY,
    weighting: str = WEIGHTING_ENERGY,
    global_vmax: float | None = None,
    lock_scale: bool = True,
    scale_mode: str = scale_mod.MODE_DECADES,
) -> dict[str, dict[str, Any]]:
    """Render all three panels.

    The depth panels share one colour scale so that the YZ and XZ views can be
    compared directly - a requirement of the brief, and meaningless if each
    normalises to its own maximum. The XY panel keeps its own scale because it
    is restricted to the entrance slab and therefore holds far less energy;
    forcing it onto the depth panels' ramp would render it almost black.
    """
    panels: dict[str, dict[str, Any]] = {}
    view = planes_mod.view(channel, weighting)
    refs = {"xy": None, "yz": None, "xz": None}
    if view.kind in (KIND_EXTENSIVE, KIND_SIGNED) and channel != CHANNEL_DENSITY:
        peaks = cam_energy_peaks(bundle, plan, channel)
        refs = {"xy": peaks["xy"], "yz": peaks["depth"], "xz": peaks["depth"]}

    xy_payload, _ = render_panel(
        bundle, "xy", plan, channel, weighting, global_vmax, lock_scale, scale_mode,
        ref=refs["xy"],
    )
    panels["xy"] = xy_payload

    depth_matrices = {}
    for name in ("yz", "xz"):
        payload, resampled = render_panel(
            bundle, name, plan, channel, weighting, global_vmax, lock_scale, scale_mode,
            ref=refs[name],
        )
        panels[name] = payload
        depth_matrices[name] = resampled
        if refs[name] is not None:
            panels[name]["scale"]["shared_with"] = "yz+xz"

    if channel == CHANNEL_DENSITY:
        shared_max = max(
            (float(np.nanmax(m)) if np.isfinite(m).any() else 0.0)
            for m in depth_matrices.values()
        )
        if shared_max > 0:
            for name, resampled in depth_matrices.items():
                scale = scale_mod.resolve_scale(
                    resampled,
                    channel=channel,
                    mode=scale_mode,
                    global_vmax=shared_max,
                    lock=True,
                )
                lattice = bundle.lattice
                row_name, col_name = _PANEL_AXES[name]
                native = plan.mode == MODE_NATIVE
                n_rows, n_cols = _plan_shape(plan, name)
                panels[name] = matrix_encode.encode_matrix(
                    resampled,
                    scale,
                    row_edges=splat.destination_edges(
                        lattice.axis(row_name).edges, n_rows, native
                    ),
                    col_edges=splat.destination_edges(
                        lattice.axis(col_name).edges, n_cols, native
                    ),
                    row_axis=row_name,
                    col_axis=col_name,
                    panel=name,
                    native=native,
                )
                panels[name]["scale"]["shared_with"] = "yz+xz"

    return panels
