"""The detector lattice, and the only sanctioned index-to-millimetre mapping.

Measured geometry of the shipped dataset, which is what this module is built
around:

``z``  60 sampling layers, gaps *exactly* 20.5 mm, spanning 3662.4 to 4871.9 mm.
       Perfectly uniform.

``y``  104 cells. Gaps strictly alternate 48.60 / 52.40 mm, an exact 101.0 mm
       period holding two cells. Mean pitch 50.485 mm. The deviation from
       uniform is at most 1.9 mm against a 50 mm pitch, so a uniform
       approximation still round-trips every cell to its own index.

``x``  211 cells, and **not uniform**. Cells sit in tight pairs 4.4 mm apart,
       with the pitch between pair groups alternating 43.87 / 48.27 mm, plus a
       handful of irregular module-boundary gaps. Consecutive-gap histogram over
       the measured values: 4.40 mm (65x), 48.27 mm (50x), 43.87 mm (32x),
       4.41 mm (28x), 43.86 mm (16x), and a scattering of one-offs.

The consequence drives the whole design of this module. ``ix * pitch_x`` is not
a position on this detector - it can be wrong by a factor of ten within a single
pair. So a bin index is an **ordinal**: the rank of a cell among the distinct
coordinates present in the data. Ordinal indexing is what guarantees that the
native-lattice view has no empty bins at all, because every index by
construction corresponds to a cell that exists. Physical placement then goes
through :attr:`Axis.coords` and :attr:`Axis.edges`, never through a pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: A lattice is treated as uniform when every consecutive gap is within this
#: fraction of the mean gap. y (3.8% deviation) passes; x (an 10x spread)
#: does not.
UNIFORM_TOLERANCE = 0.15


@dataclass(frozen=True)
class Axis:
    """One detector axis: the distinct coordinates, in ascending order."""

    name: str
    coords: np.ndarray  # shape (n,), float64, strictly ascending, millimetres

    def __post_init__(self) -> None:
        if self.coords.ndim != 1 or self.coords.size == 0:
            raise ValueError(f"Axis {self.name!r} needs a non-empty 1-D coordinate array.")

    @property
    def n(self) -> int:
        return int(self.coords.size)

    @property
    def lo(self) -> float:
        return float(self.coords[0])

    @property
    def hi(self) -> float:
        return float(self.coords[-1])

    @property
    def mean_pitch(self) -> float:
        """Mean spacing between adjacent cells. Reporting only, never placement."""
        if self.n < 2:
            return 1.0
        return float((self.coords[-1] - self.coords[0]) / (self.n - 1))

    @property
    def is_uniform(self) -> bool:
        """Whether the spacing is regular enough to treat as a constant pitch."""
        if self.n < 3:
            return True
        gaps = np.diff(self.coords)
        mean = gaps.mean()
        if mean <= 0:
            return False
        return bool(np.all(np.abs(gaps - mean) <= UNIFORM_TOLERANCE * mean))

    @property
    def edges(self) -> np.ndarray:
        """Cell boundaries, shape ``(n + 1,)``.

        Interior boundaries are placed midway between adjacent cell centres, so
        the cells tile the axis contiguously with no gaps and no overlaps - the
        property that makes the native view comb-free and makes area-weighted
        resampling in ``splat.py`` energy-conserving. The two outer boundaries
        are reflected outward by half the adjacent gap.
        """
        c = self.coords
        if self.n == 1:
            half = 0.5 * max(abs(c[0]), 1.0)
            return np.array([c[0] - half, c[0] + half], dtype=np.float64)
        mid = 0.5 * (c[:-1] + c[1:])
        first = c[0] - (mid[0] - c[0])
        last = c[-1] + (c[-1] - mid[-1])
        return np.concatenate(([first], mid, [last]))

    @property
    def extent(self) -> tuple[float, float]:
        """Outer physical extent in millimetres, for axis limits."""
        e = self.edges
        return float(e[0]), float(e[-1])

    @property
    def span(self) -> float:
        lo, hi = self.extent
        return hi - lo

    def index_of(self, values: np.ndarray) -> np.ndarray:
        """Map millimetre values to ordinal bin indices via the cell edges.

        ``searchsorted`` on the edges is exact for irregular lattices, where
        rounding a scaled offset is not.
        """
        idx = np.searchsorted(self.edges, values, side="right") - 1
        return np.clip(idx, 0, self.n - 1)

    def as_dict(self) -> dict[str, Any]:
        lo, hi = self.extent
        return {
            "n": self.n,
            "coords": [float(v) for v in self.coords],
            "edges": [float(v) for v in self.edges],
            "extent": [lo, hi],
            "mean_pitch": self.mean_pitch,
            "uniform": self.is_uniform,
            "unit": "mm",
        }


@dataclass(frozen=True)
class Lattice:
    """The full three-axis detector lattice plus the entrance-slab depth."""

    x: Axis
    y: Axis
    z: Axis
    slab_mm: float
    slab_iz: int

    @property
    def shape_xy(self) -> tuple[int, int]:
        """Rows, columns of the XY panel: y is the row axis, x the column axis."""
        return self.y.n, self.x.n

    @property
    def shape_yz(self) -> tuple[int, int]:
        """Rows, columns of the YZ panel: y is the row axis, z (depth) columns."""
        return self.y.n, self.z.n

    @property
    def shape_xz(self) -> tuple[int, int]:
        """Rows, columns of the XZ panel: x is the row axis, z (depth) columns."""
        return self.x.n, self.z.n

    def axis(self, name: str) -> Axis:
        return {"x": self.x, "y": self.y, "z": self.z}[name]

    def as_dict(self) -> dict[str, Any]:
        return {
            "x": self.x.as_dict(),
            "y": self.y.as_dict(),
            "z": self.z.as_dict(),
            "slab_mm": self.slab_mm,
            "slab_iz": self.slab_iz,
            "native_shapes": {
                "xy": list(self.shape_xy),
                "yz": list(self.shape_yz),
                "xz": list(self.shape_xz),
            },
        }


def from_registry_row(
    x_coords: list[float],
    y_coords: list[float],
    z_coords: list[float],
    slab_mm: float,
    slab_iz: int,
) -> Lattice:
    """Rebuild a :class:`Lattice` from its stored coordinate arrays."""
    return Lattice(
        x=Axis("x", np.asarray(x_coords, dtype=np.float64)),
        y=Axis("y", np.asarray(y_coords, dtype=np.float64)),
        z=Axis("z", np.asarray(z_coords, dtype=np.float64)),
        slab_mm=float(slab_mm),
        slab_iz=int(slab_iz),
    )
