"""Detector cell lattice and the display binning grids.

This module owns the single most consequential numerical choice in the build:
the transverse bin width. See ``constants.BIN_XY_MM`` for the measurement that
fixed it at 50.5 mm.

The binning happens here, during the build, and the browser receives only
integer cell indices. That satisfies the requirement to pre-bin rather than ship
raw coordinates, and it means the client never performs geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    BIN_XY_MM,
    N_LAYERS,
    N_XY,
    N_XY_HALF,
    OUTSIDE_WINDOW,
    XY_EXTENT_MM,
    Z_PITCH_MM,
)


@dataclass
class LatticeSurvey:
    """What the detector lattice actually looks like, measured from the data.

    Reported in the build log so the bin-width choice can be re-checked against
    any new input file rather than trusted from a comment.
    """

    n_unique_x: int
    n_unique_y: int
    n_unique_z: int
    z_front_mm: float
    z_pitch_mm: float
    x_period_mm: float
    y_period_mm: float
    regular_z: bool

    def lines(self) -> list[str]:
        return [
            f"  unique cells      x={self.n_unique_x}  y={self.n_unique_y}  z={self.n_unique_z}",
            f"  z front face      {self.z_front_mm:,.1f} mm",
            f"  z pitch           {self.z_pitch_mm:.4f} mm "
            f"({'regular' if self.regular_z else 'IRREGULAR'})",
            f"  transverse period x={self.x_period_mm:.3f} mm  y={self.y_period_mm:.3f} mm",
            f"  display bin       {BIN_XY_MM:.3f} mm transverse, "
            f"{self.z_pitch_mm:.3f} mm longitudinal",
        ]


def survey(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> LatticeSurvey:
    """Measure the cell lattice of an input file."""
    ux, uy, uz = np.unique(x), np.unique(y), np.unique(z)

    z_diffs = np.diff(uz)
    z_pitch = float(np.median(z_diffs)) if z_diffs.size else Z_PITCH_MM
    regular_z = bool(z_diffs.size and np.allclose(z_diffs, z_pitch, atol=1e-6))

    def period(values: np.ndarray) -> float:
        # One lattice period spans two cells on both transverse axes.
        return float(np.median(values[2:] - values[:-2])) if values.size > 2 else float("nan")

    return LatticeSurvey(
        n_unique_x=ux.size,
        n_unique_y=uy.size,
        n_unique_z=uz.size,
        z_front_mm=float(uz.min()) if uz.size else float("nan"),
        z_pitch_mm=z_pitch,
        x_period_mm=period(ux),
        y_period_mm=period(uy),
        regular_z=regular_z,
    )


def quantise_transverse(values: np.ndarray) -> np.ndarray:
    """Map shower-local transverse coordinates in mm onto bin indices.

    Returns ``uint8`` indices in ``[0, N_XY)``, with ``OUTSIDE_WINDOW`` for hits
    beyond the window. The sentinel matters: clamping instead would pile the
    0.7% tail onto the border bins and invent a bright rim that is not there.
    """
    index = np.floor(values / BIN_XY_MM).astype(np.int64) + N_XY_HALF
    inside = (index >= 0) & (index < N_XY)
    return np.where(inside, index, OUTSIDE_WINDOW).astype(np.uint8)


def quantise_depth(depth_mm: np.ndarray, pitch: float = Z_PITCH_MM) -> np.ndarray:
    """Map shower-local depth in mm onto a sampling-layer index.

    Depth is measured from each event's own entry layer, so index 0 is always
    the entry layer and is exactly the set of hits the origin-pinning artifact
    affects.
    """
    index = np.rint(depth_mm / pitch).astype(np.int64)
    return np.clip(index, 0, N_LAYERS - 1).astype(np.uint8)


def transverse_edges() -> np.ndarray:
    """Bin edges in mm, for axis configuration on the client."""
    return np.linspace(-XY_EXTENT_MM, XY_EXTENT_MM, N_XY + 1)


def grid_spec(pitch: float = Z_PITCH_MM) -> dict:
    """Axis geometry handed to the browser.

    ``x0``/``dx`` let plotly place the heatmap in millimetres without shipping
    coordinate arrays, and keep the axes readable in physical units.
    """
    return {
        "nXY": N_XY,
        "nZ": N_LAYERS,
        "binXY": BIN_XY_MM,
        "binZ": pitch,
        # Bin centres of the first bin on each axis.
        "x0": -XY_EXTENT_MM + BIN_XY_MM / 2.0,
        "z0": 0.0,
        "extentXY": XY_EXTENT_MM,
        "depthMax": (N_LAYERS - 1) * pitch,
        "outside": OUTSIDE_WINDOW,
    }
