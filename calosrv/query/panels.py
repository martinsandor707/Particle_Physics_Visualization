"""Turn a cached native-resolution bundle into rendered panel payloads.

This is the step that makes the resolution and display-mode controls cheap.
Nothing here touches the database: it resamples the cached native matrices,
picks the requested measurement channel, and encodes the result.

**Channel handling is not symmetric, and must not be.**

*Density* is summed energy - an extensive quantity. Resampling it directly
conserves the total exactly.

*Grad-CAM attention* is a mean - an intensive quantity. Resampling a mean would
average averages, weighting every source cell equally regardless of how much
energy it holds. The numerator and denominator are resampled separately and
divided at the destination resolution instead.

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
from ..encode import scale as scale_mod
from ..grid import splat
from ..grid.resolution import MODE_NATIVE, ResolutionPlan
from .projections import NativeBundle, Panel

CHANNEL_DENSITY = "density"
CHANNEL_GRADCAM = "gradcam"
CHANNELS = (CHANNEL_DENSITY, CHANNEL_GRADCAM)

WEIGHTING_ENERGY = "energy"
WEIGHTING_COUNT = "count"
WEIGHTINGS = (WEIGHTING_ENERGY, WEIGHTING_COUNT)

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


def render_panel(
    bundle: NativeBundle,
    panel_name: str,
    plan: ResolutionPlan,
    channel: str = CHANNEL_DENSITY,
    weighting: str = WEIGHTING_ENERGY,
    global_vmax: float | None = None,
    lock_scale: bool = True,
    scale_mode: str = scale_mod.MODE_DECADES,
) -> tuple[dict[str, Any], np.ndarray]:
    """Resample and encode one panel. Returns ``(payload, resampled_matrix)``."""
    panel: Panel = bundle.panel(panel_name)
    lattice = bundle.lattice
    row_axis_name, col_axis_name = _PANEL_AXES[panel_name]
    row_axis = lattice.axis(row_axis_name)
    col_axis = lattice.axis(col_axis_name)

    native = plan.mode == MODE_NATIVE
    n_rows, n_cols = _plan_shape(plan, panel_name)

    row_op = splat.build_axis_operator(row_axis.edges, n_rows, native)
    col_op = splat.build_axis_operator(col_axis.edges, n_cols, native)
    row_edges = splat.destination_edges(row_axis.edges, n_rows, native)
    col_edges = splat.destination_edges(col_axis.edges, n_cols, native)

    if channel == CHANNEL_GRADCAM:
        if weighting == WEIGHTING_COUNT:
            numerator, denominator = panel.planes["g"], panel.planes["n"]
        else:
            numerator, denominator = panel.planes["eg"], panel.planes["e"]
        resampled = splat.resample_ratio(numerator, denominator, row_op, col_op)
    else:
        resampled = splat.resample(panel.planes["e"], row_op, col_op)

    scale = scale_mod.resolve_scale(
        resampled,
        channel=channel,
        mode=scale_mode,
        global_vmax=global_vmax,
        lock=lock_scale,
    )

    payload = matrix_encode.encode_matrix(
        resampled,
        scale,
        row_edges=row_edges,
        col_edges=col_edges,
        row_axis=row_axis_name,
        col_axis=col_axis_name,
        panel=panel_name,
        native=native,
    )
    return payload, resampled


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

    xy_payload, _ = render_panel(
        bundle, "xy", plan, channel, weighting, global_vmax, lock_scale, scale_mode
    )
    panels["xy"] = xy_payload

    depth_matrices = {}
    for name in ("yz", "xz"):
        payload, resampled = render_panel(
            bundle, name, plan, channel, weighting, global_vmax, lock_scale, scale_mode
        )
        panels[name] = payload
        depth_matrices[name] = resampled

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
