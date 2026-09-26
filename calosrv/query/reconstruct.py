"""Display reconstruction of a canonical panel: which kernel, over which bins.

``grid/kernel.py`` holds the maths; this module holds the policy and applies
it to one panel axis at a time.

**Which kernel.** *Native Grid* is the audit view and gets none: the raw 20 mm
accumulation bins, cropped to the window (and box-merged only when the payload
guard must). *Continuous Field* reconstructs the two transverse axes:

* below :data:`~calosrv.grid.frame.GAUSSIAN_KERNEL_BELOW_N` (50) co-registered
  events, a Gaussian of ``sigma = 10 mm`` over each uniform bin - a handful of
  events leaves rotated 48 mm cell blocks that the tent alone would still show;
* from 50 events, the bilinear tent, exact linear interpolation between the bin
  centres, once the ensemble of rotation angles has filled the footprint.

Depth is never reconstructed: there is no measurement between two sampling
layers 20.5 mm apart, so every depth axis passes through untouched.

**Which source bins.** A continuous axis does not start from the cropped
window. Its source is the *full* accumulation axis, sliced losslessly to the
window plus the kernel's reach (one bin for the tent, ``ceil(9 sigma / p) + 1``
for the Gaussian), so energy just outside the window blurs in and energy
blurring out is not lost silently: :func:`inside_weights` gives, per full-grid
bin, the fraction of its energy the rendered window holds, which is how the
panel's in-window total is accounted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..grid import frame as frame_mod
from ..grid import kernel as kernel_mod
from ..grid import splat
from ..grid.kernel import Kernel
from ..grid.resolution import MODE_NATIVE
from .window import AxisFit

#: The axes a display reconstruction acts on, as written on screen.
RECONSTRUCTED_AXES = ("x′", "y′")

DEPTH_POLICY = "native sampling layers, never smoothed or interpolated"


# ---------------------------------------------------------------- policy --


def choose_kernel(mode: str, n_events: int) -> Kernel:
    """The kernel a display mode gets for a selection of ``n_events``."""
    if mode == MODE_NATIVE:
        return kernel_mod.NONE
    if n_events < frame_mod.GAUSSIAN_KERNEL_BELOW_N:
        return kernel_mod.gaussian(frame_mod.SMOOTH_SIGMA_MM)
    return kernel_mod.BILINEAR


def blur_rms(width: float, k: int, bin_spread: float, bin_pitch: float) -> float:
    """Total transverse RMS blur of one cell's energy on the display, about the cell centre.

    Three independent terms add in quadrature:

    * the ``k x k`` footprint splat, whose ``k`` sub-deposits sit ``w / k``
      apart across a cell of width ``w``: variance ``w^2 (1 - 1/k^2) / 12``
      (the continuous ``w^2 / 12`` overstates this term by 15% in RMS at
      k = 2);
    * the point binning of each sub-deposit into its bin of width ``p``
      (``floor`` in the canonical scan): under the ensemble's random rotations
      and offsets the displacement to the bin is uniform, variance ``p^2 / 12``;
    * the spread the kernel gives each bin (``Kernel.bin_spread_rms``), which
      already contains the bin's own ``p / sqrt 12`` box width - a separate
      term from the displacement above.

    A Monte Carlo of 4000 randomly rotated and placed 48.27 mm cells, binned
    to 20 mm exactly as the SQL does and drawn through each kernel onto a
    0.1 mm grid, reproduces the formula to 0.1 mm for the box, tent and
    Gaussian at k = 2, 4 and 6; without the binning term it runs 5-8% low.
    A display bin coarser than ``p`` adds its own quantisation, which the
    caption states separately as the display pitch.
    """
    w = float(width)
    p = float(bin_pitch)
    if k is None:
        # Exact area-weighted box overlap (the translated frame): the footprint
        # is integrated rather than sampled, so its term is the continuous
        # w^2 / 12 - the k -> infinity limit of the sub-deposit term. The
        # binning term stays: overlap weighting still puts each bin's share at
        # the bin centre, and each shower's entry point is continuous, so the
        # displacement to it is uniform over the bin. (Measured with a Monte
        # Carlo of the scan's own operator: 16.15 mm against 16.15 with the term
        # and 15.08 without it, native display.)
        return math.sqrt(w * w / 12.0 + p * p / 12.0 + float(bin_spread) ** 2)
    k = max(1, int(k))
    return math.sqrt(
        w * w * (1.0 - 1.0 / (k * k)) / 12.0 + p * p / 12.0 + float(bin_spread) ** 2
    )


def _gate(kernel: Kernel, n_events: int) -> str:
    gate = frame_mod.GAUSSIAN_KERNEL_BELOW_N
    if kernel.name == kernel_mod.KERNEL_GAUSSIAN:
        return f"used below N = {gate} co-registered events (here N = {n_events:,})"
    return f"used from N = {gate} co-registered events (here N = {n_events:,})"


def kernel_sentence(
    kernel: Kernel, n_events: int, pitch: float,
    axes: tuple[str, str] = RECONSTRUCTED_AXES,
    depth_clause: str = "depth keeps its native sampling layers",
) -> str:
    """One sentence naming the Continuous Field kernel, its spread and its N gate.

    The switch is described qualitatively, because this sentence travels with
    every experiment's payload: on production v37 it raises the displayed X′Y′
    peak by 6-7% (the N = 49 / 50 pair, ``grid/frame.py``), but that figure
    belongs to that dataset, not to the demo or to an upload. ``axes`` and
    ``depth_clause`` word it for the frame the panels are drawn in.
    """
    gauss = kernel_mod.gaussian(frame_mod.SMOOTH_SIGMA_MM)
    tent = kernel_mod.BILINEAR
    narrower = 1.0 - tent.bin_spread_rms(pitch) / gauss.bin_spread_rms(pitch)
    if kernel.name == kernel_mod.KERNEL_GAUSSIAN:
        body = (
            f"a conservative Gaussian kernel (σ = {kernel.sigma_mm:g} mm, "
            f"{kernel.bin_spread_rms(pitch):.1f} mm RMS per {pitch:.0f} mm bin)"
        )
        other = f"from N = {frame_mod.GAUSSIAN_KERNEL_BELOW_N} the bilinear tent takes over"
    else:
        body = (
            "the conservative bilinear (tent) kernel, exact linear interpolation between "
            f"the {pitch:.0f} mm bin centres ({kernel.bin_spread_rms(pitch):.1f} mm RMS per bin)"
        )
        other = (
            f"below N = {frame_mod.GAUSSIAN_KERNEL_BELOW_N} a Gaussian σ = "
            f"{gauss.sigma_mm:g} mm ({gauss.bin_spread_rms(pitch):.1f} mm RMS) is used instead"
        )
    return (
        f"Continuous Field reconstructs {axes[0]} and {axes[1]} only with {body}, {_gate(kernel, n_events)}; "
        f"{other}, the tent being {100.0 * narrower:.0f}% narrower, so the displayed peak is "
        "higher on the tent side of the switch: compare selections on the same side of it. "
        f"Energy is conserved, no displayed bin exceeds the raw {pitch:.0f} mm-grid peak, and "
        f"{depth_clause}."
    )


# --------------------------------------------------------------- axis maps --


@dataclass(frozen=True)
class AxisMap:
    """How one panel axis goes from the full accumulation grid to the display.

    ``src_slice`` selects the accumulation bins that feed the display, ``op``
    maps them onto the destination bins (``None``: passed through unchanged),
    and ``dst_edges`` are the destination bins' millimetre edges.
    """

    op: np.ndarray | None
    dst_edges: np.ndarray
    src_slice: slice

    @property
    def n_dst(self) -> int:
        return int(self.dst_edges.size - 1)


def passthrough(edges: np.ndarray) -> AxisMap:
    """The whole axis, untouched - every depth axis in both modes."""
    return AxisMap(None, np.asarray(edges, dtype=np.float64), slice(0, int(edges.size - 1)))


def native_axis(full_edges: np.ndarray, fit: AxisFit, n_dst: int) -> AxisMap:
    """Index crop to the window, box-merged onto ``n_dst`` bins when the guard asks."""
    cropped = np.asarray(full_edges[fit.lo_index:fit.hi_index + 1], dtype=np.float64)
    src = slice(fit.lo_index, fit.hi_index)
    if n_dst == cropped.size - 1:
        return AxisMap(None, cropped, src)
    dst = splat.uniform_edges(float(cropped[0]), float(cropped[-1]), n_dst)
    return AxisMap(splat.overlap_matrix(cropped, dst), dst, src)


def continuous_axis(
    full_edges: np.ndarray, fit: AxisFit, n_dst: int, kernel: Kernel, pitch: float
) -> AxisMap:
    """Kernel reconstruction of the window from the full axis plus the kernel's reach."""
    full = np.asarray(full_edges, dtype=np.float64)
    n_full = int(full.size - 1)
    reach = kernel.reach_bins(pitch)
    start = max(0, fit.lo_index - reach)
    stop = min(n_full, fit.hi_index + reach)
    src = full[start:stop + 1]
    dst = splat.uniform_edges(float(fit.lo), float(fit.hi), max(1, int(n_dst)))
    return AxisMap(kernel_mod.operator(src, dst, kernel), dst, slice(start, stop))


def apply(matrix: np.ndarray, row_map: AxisMap, col_map: AxisMap) -> np.ndarray:
    """Reconstruct an extensive quantity (energy, hit count)."""
    source = np.asarray(matrix)[row_map.src_slice, col_map.src_slice]
    return splat.resample(source, row_map.op, col_map.op)


def apply_ratio(
    numerator: np.ndarray, denominator: np.ndarray, row_map: AxisMap, col_map: AxisMap,
    fill: float = np.nan,
) -> np.ndarray:
    """Reconstruct an intensive quantity as a normalised convolution.

    The same operator is applied to the numerator and the denominator before
    dividing, so the result stays an energy- (or count-) weighted mean and a
    constant attention field stays exactly constant.
    """
    rows, cols = row_map.src_slice, col_map.src_slice
    return splat.resample_ratio(
        np.asarray(numerator)[rows, cols], np.asarray(denominator)[rows, cols],
        row_map.op, col_map.op, fill=fill,
    )


def inside_weights(axis_map: AxisMap, n_full: int) -> np.ndarray:
    """Per full-grid bin, the fraction of its content the rendered axis holds.

    The column sums of the operator placed at the source slice (an indicator
    of the slice when nothing is resampled). A panel's in-window total is
    ``inside_weights(rows) @ E @ inside_weights(cols)``.
    """
    weights = np.zeros(int(n_full), dtype=np.float64)
    if axis_map.op is None:
        weights[axis_map.src_slice] = 1.0
    else:
        weights[axis_map.src_slice] = axis_map.op.sum(axis=0)
    return weights


# ---------------------------------------------------------------- report --


def reconstruction_report(plan: Any, bundle: Any, panels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The ``frame.reconstruction`` block: what the display did to the raw grid.

    ``plan`` is the ``density.CanonicalPlan`` the panels were rendered with;
    the per-panel outside and below-floor figures are read back from the
    rendered payloads so the block can never disagree with them.
    """
    kernel: Kernel = plan.kernel
    # The bins the kernel acts on: the accumulation grid for a smoothing
    # kernel, the (possibly guard-merged) raw bins for the Native Grid. Their
    # width sets both the kernel's spread and the point-binning term.
    spread_pitch = plan.pitch_mm if kernel.smooths else plan.display_pitch_mm
    spread = kernel.bin_spread_rms(spread_pitch)
    regime = getattr(bundle, "splat_regime", "subdeposit2d")
    k = None if regime == "box_overlap" else int(bundle.subsample_k)
    symbols = getattr(bundle, "symbols", None) or {"x": "x′", "y": "y′"}
    w_x, w_y = bundle.footprint
    n_events = int(bundle.n_events)
    blur_x = blur_rms(w_x, k, spread, spread_pitch)
    blur_y = blur_rms(w_y, k, spread, spread_pitch)

    if kernel.smooths:
        note = kernel_sentence(
            kernel, n_events, plan.pitch_mm, (symbols["x"], symbols["y"]),
            getattr(bundle, "depth_clause", None) or "depth keeps its native sampling layers",
        )
    else:
        note = (
            f"Native Grid: the raw {plan.pitch_mm:.0f} mm accumulation bins with no "
            "reconstruction, the audit view"
        )
        if plan.merge > 1:
            note += (
                f"; merged {plan.merge}× to {plan.display_pitch_mm:.0f} mm by the payload guard"
            )
        note += "."
    if regime == "box_overlap":
        splat_phrase = "the exact area-weighted overlap of each cell's footprint"
    elif regime == "subdeposit3d":
        splat_phrase = (
            f"the {k} × {k} × {int(getattr(bundle, 'k_z', 1))} rotated footprint sub-deposits"
        )
    else:
        splat_phrase = f"the {k} × {k} footprint splat"
    note += (
        f" Total transverse blur including {splat_phrase} and the "
        f"{spread_pitch:.0f} mm binning: {blur_x:.1f} mm RMS in {symbols['x']}, "
        f"{blur_y:.1f} mm in {symbols['y']}."
    )

    return {
        "display": plan.mode,
        "kernel": kernel.name,
        "label": kernel.label(),
        "sigma_mm": kernel.sigma_mm if kernel.name == kernel_mod.KERNEL_GAUSSIAN else None,
        "bin_spread_rms_mm": round(spread, 3),
        "blur_rms_mm": {"x": round(blur_x, 3), "y": round(blur_y, 3)},
        "subsample_k": k,
        "splat_regime": regime,
        "gaussian_below_n": frame_mod.GAUSSIAN_KERNEL_BELOW_N,
        "axes": [symbols["x"], symbols["y"]],
        "depth": getattr(bundle, "depth_policy", DEPTH_POLICY),
        "conservative": True,
        "floor_ratio": float(10.0 ** -frame_mod.RAMP_DECADES),
        "energy_fraction_outside": {
            name: panels[name]["energy_fraction_outside_window"] for name in ("xy", "yz", "xz")
        },
        "below_floor": {
            name: {
                "cells": int(panels[name].get("below_floor_cells", 0)),
                "energy_fraction": panels[name].get("below_floor_energy_fraction", 0.0),
            }
            for name in ("xy", "yz", "xz")
        },
        "note": note,
    }
