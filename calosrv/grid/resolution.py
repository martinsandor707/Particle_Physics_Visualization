"""Resolution planning for the two display modes.

**Mode A - Native Detector Lattice (hardware truth).** One bin per real
calorimeter cell: 211 x 104 for XY, 104 x 60 for YZ, 211 x 60 for XZ on the
shipped dataset. Because a bin index is an ordinal over the coordinates that
actually occur in the data, every bin corresponds to a cell that exists, and the
empty-bin comb is impossible by construction rather than merely unlikely.

**Mode B - Continuous Field (anti-aliased voxel splatting).** A uniform grid
whose fineness follows ``resolution``. The transverse axes scale together so the
relative sampling of the native lattice is preserved - ``R_y = round(R * ny/nx)``
- and the depth axis is *locked* to the 60 native sampling layers, because depth
is not a continuum here: there is no information between two scintillator layers
20.5 mm apart, and interpolating across that gap would invent structure.

Energy is not point-binned into this grid. It is distributed across destination
bins in proportion to geometric overlap (see ``splat.py``), which is what lets R
exceed the native count without picket-fencing: a source cell straddling three
destination bins contributes to all three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ValidationError
from .lattice import Lattice

MODE_NATIVE = "native"
MODE_CONTINUOUS = "continuous"
DISPLAY_MODES = (MODE_NATIVE, MODE_CONTINUOUS)

DEFAULT_RESOLUTION = 150
MIN_RESOLUTION = 16

#: Upper bound on R. Past this the payload budget is the binding constraint, not
#: physics: a 512-wide uint8 panel is already 260 KB before encoding.
MAX_RESOLUTION = 512


@dataclass(frozen=True)
class ResolutionPlan:
    """Destination bin counts for all three panels."""

    mode: str
    requested: int
    r_x: int
    r_y: int
    r_z: int
    warnings: tuple[str, ...] = ()

    @property
    def shape_xy(self) -> tuple[int, int]:
        return self.r_y, self.r_x

    @property
    def shape_yz(self) -> tuple[int, int]:
        return self.r_y, self.r_z

    @property
    def shape_xz(self) -> tuple[int, int]:
        return self.r_x, self.r_z

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "requested": self.requested,
            "r_x": self.r_x,
            "r_y": self.r_y,
            "r_z": self.r_z,
            "shapes": {
                "xy": list(self.shape_xy),
                "yz": list(self.shape_yz),
                "xz": list(self.shape_xz),
            },
            "warnings": list(self.warnings),
        }


def plan_resolution(
    lattice: Lattice,
    mode: str = MODE_NATIVE,
    resolution: int = DEFAULT_RESOLUTION,
) -> ResolutionPlan:
    """Resolve a display mode and requested R into concrete bin counts."""
    if mode not in DISPLAY_MODES:
        raise ValidationError(
            f"Unknown display mode {mode!r}; expected one of "
            f"{', '.join(DISPLAY_MODES)}.",
            field="display",
        )

    if mode == MODE_NATIVE:
        return ResolutionPlan(
            mode=MODE_NATIVE,
            requested=resolution,
            r_x=lattice.x.n,
            r_y=lattice.y.n,
            r_z=lattice.z.n,
        )

    if not MIN_RESOLUTION <= resolution <= MAX_RESOLUTION:
        raise ValidationError(
            f"resolution must be between {MIN_RESOLUTION} and {MAX_RESOLUTION}; "
            f"got {resolution}.",
            field="resolution",
        )

    warnings: list[str] = []
    r_x = int(resolution)
    r_y = max(1, round(resolution * lattice.y.n / lattice.x.n))
    r_z = lattice.z.n

    if r_x > lattice.x.n:
        warnings.append(
            f"Requested R={r_x} exceeds the {lattice.x.n} native transverse x "
            "cells. Area-weighted splatting keeps the image free of gaps, but "
            "no detail beyond the native lattice is recoverable."
        )
    warnings.append(
        f"Depth is locked to the {lattice.z.n} native sampling layers "
        f"({lattice.z.mean_pitch:.1f} mm pitch); there is no measurement "
        "between layers to interpolate."
    )

    return ResolutionPlan(
        mode=MODE_CONTINUOUS,
        requested=int(resolution),
        r_x=r_x,
        r_y=r_y,
        r_z=r_z,
        warnings=tuple(warnings),
    )
