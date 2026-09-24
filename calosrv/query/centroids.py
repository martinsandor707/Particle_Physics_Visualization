"""Energy-weighted shower centroids, and the separation vector between them.

**Why fractional weights rather than the ``particle_origin`` label.**
``particle_origin`` takes three values on this dataset: ``A`` (51%), ``B`` (40%)
and ``A+B`` (8.6%). Selecting ``particle_origin = 'A'`` to locate shower A
therefore discards every hit in the overlap region - which is precisely the
region the study is about - and the discard is *spatially biased*: the shared
hits lie between the two showers, so removing them pushes both centroids outward
and systematically inflates the measured separation.

Weighting by the voxel fraction instead uses all of the deposited energy::

    x_A = sum(x * energy * fA) / sum(energy * fA)
    x_B = sum(x * energy * (1 - fA)) / sum(energy * (1 - fA))

On unambiguous hits this reduces to the categorical answer exactly - rows
labelled ``B`` carry ``voxel_fA_true = 0`` and rows labelled ``A`` carry 1 - so
the two estimators differ only where the label is genuinely ambiguous. The
fractional form is also continuous in the sliders, so the centroid marker glides
rather than jumping when a boundary hit changes category.

**Three centroids are reported, not one**, because their disagreement is itself
a diagnostic:

``truth_voxel``   weighted by ``voxel_fA_true`` - where the energy actually went
``pred_voxel``    weighted by ``voxel_fA_pred`` - where the model thinks it went
``truth_dataset`` the dataset's own ``centroid_A/B_*`` columns, averaged over the
                  selected events (computed in ``summary.py``, from the
                  per-event table)

The offset between the first two is a directly readable spatial bias of the
segmentation model.

**On precision.** The centroids are computed from lattice bin indices mapped back
through the measured coordinate arrays. Because an index is an *ordinal* over
the coordinates that actually occur, that mapping is exact - a bin index
recovers the true cell coordinate, not a bin centre - so there is no
quantisation error here at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .projections import NativeBundle, Panel


@dataclass(frozen=True)
class Centroid:
    x: float | None
    y: float | None
    z: float | None
    energy: float

    def as_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z, "energy": self.energy}


@dataclass(frozen=True)
class CentroidPair:
    label: str
    a: Centroid
    b: Centroid
    separation_mm: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "a": self.a.as_dict(),
            "b": self.b.as_dict(),
            "separation_mm": self.separation_mm,
        }


def _weighted_mean(weights: np.ndarray, coords: np.ndarray, axis: int) -> float | None:
    """Energy-weighted mean position along one matrix axis."""
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 0:
        return None
    # Collapse the other axis, then take the weighted mean over this one.
    marginal = weights.sum(axis=1 - axis)
    denom = float(marginal.sum())
    if denom <= 0:
        return None
    return float(np.dot(marginal, coords) / denom)


def _pair_from_panel(
    panel: Panel,
    bundle: NativeBundle,
    plane: str,
    label: str,
    z_panel: Panel | None = None,
    z_plane: str | None = None,
) -> CentroidPair:
    """Build an A/B centroid pair from one panel's weight planes.

    Coordinates come from ``bundle.axis(name)`` rather than from the lattice
    directly, so the same code measures a canonical-frame bundle, whose axes
    are a uniform grid in x', y', z' rather than detector cells.
    """
    energy = panel.planes["e"]
    w_a = panel.planes[plane]
    # Energy not attributed to A belongs to B. Clipping guards against a
    # float32 fraction marginally above 1 producing a negative B weight.
    w_b = np.clip(energy - w_a, 0.0, None)

    row_coords = bundle.axis(panel.row_axis).coords
    col_coords = bundle.axis(panel.col_axis).coords
    depth_coords = bundle.axis("z").coords

    def build(weights: np.ndarray, is_a: bool) -> Centroid:
        z = None
        if z_panel is not None and z_plane is not None:
            zw_a = z_panel.planes[z_plane]
            zw = zw_a if is_a else np.clip(z_panel.planes["e"] - zw_a, 0.0, None)
            # The YZ panel is (y, z), so depth is the column axis.
            z = _weighted_mean(zw, depth_coords, axis=1)
        return Centroid(
            x=_weighted_mean(weights, col_coords, axis=1),
            y=_weighted_mean(weights, row_coords, axis=0),
            z=z,
            energy=float(weights.sum()),
        )

    a = build(w_a, is_a=True)
    b = build(w_b, is_a=False)

    separation = None
    if None not in (a.x, a.y, b.x, b.y):
        separation = float(np.hypot(a.x - b.x, a.y - b.y))

    return CentroidPair(label=label, a=a, b=b, separation_mm=separation)


def compute(bundle: NativeBundle) -> dict[str, CentroidPair]:
    """Both voxel-weighted centroid pairs, at the shower entrance.

    The XY panel is restricted to the entrance slab, which matches the physical
    definition of D: the transverse separation between the two showers' entry
    centroids. The depth coordinate is taken from the YZ panel, which spans the
    full instrumented depth.
    """
    return {
        "truth_voxel": _pair_from_panel(
            bundle.xy, bundle, "efa_true", "Ground truth (voxel-weighted)",
            z_panel=bundle.yz, z_plane="efa_true",
        ),
        "pred_voxel": _pair_from_panel(
            bundle.xy, bundle, "efa_pred", "Model prediction (voxel-weighted)",
            z_panel=bundle.yz, z_plane="efa_pred",
        ),
    }
