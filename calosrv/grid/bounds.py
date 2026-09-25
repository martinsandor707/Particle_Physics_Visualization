"""Dataset-wide extents of the per-shower frames, measured once at ingest.

The translated and local coordinates are continuous - every shower is shifted
by its own energy-weighted entry point, and the local frame is also rotated -
so there is no lattice to freeze into the registry the way the laboratory frame
has one. What *is* frozen is where the energy lies: energy-weighted quantiles
of each coordinate over the whole dataset. The co-registered accumulation grids
are planned from them, so a grid is a property of the dataset rather than of a
selection, and two selections always share bin boundaries (and cache nicely).

Extremes reach about +-4.9 m against energy-weighted 0.1-99.9 % ranges of about
+-1.1 m on the production file, which is why the grid is planned from
quantiles, never from min/max; the energy that falls outside is counted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: Energy-weighted quantile levels measured for every per-shower coordinate.
QUANTILE_LEVELS: tuple[float, ...] = (1e-4, 1e-3, 1e-2, 0.5, 0.99, 0.999, 0.9999)

#: Frame coordinates in the projection table.
FRAME_AXES: tuple[str, ...] = ("xt", "yt", "xl", "yl", "zl")


def _key(level: float) -> str:
    return repr(float(level))


@dataclass(frozen=True)
class AxisBounds:
    """Extent and energy-weighted quantiles of one per-shower coordinate, in mm."""

    name: str
    lo: float
    hi: float
    quantiles: dict[str, float] = field(default_factory=dict)

    def quantile(self, level: float) -> float:
        return float(self.quantiles[_key(level)])

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lo": self.lo, "hi": self.hi, "quantiles": dict(self.quantiles)}


@dataclass(frozen=True)
class FrameBounds:
    """Everything grid planning needs to know about the per-shower frames."""

    axes: dict[str, AxisBounds]
    n_layers_trans: int
    layer_pitch_mm: float

    def axis(self, name: str) -> AxisBounds:
        return self.axes[name]

    def as_dict(self) -> dict[str, Any]:
        return {
            "axes": {name: axis.as_dict() for name, axis in self.axes.items()},
            "n_layers_trans": self.n_layers_trans,
            "layer_pitch_mm": self.layer_pitch_mm,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str | None) -> "FrameBounds | None":
        if not text:
            return None
        data = json.loads(text)
        axes = {
            name: AxisBounds(
                name=axis["name"], lo=float(axis["lo"]), hi=float(axis["hi"]),
                quantiles={k: float(v) for k, v in axis["quantiles"].items()},
            )
            for name, axis in data["axes"].items()
        }
        return cls(
            axes=axes,
            n_layers_trans=int(data["n_layers_trans"]),
            layer_pitch_mm=float(data["layer_pitch_mm"]),
        )


def quantile_key(level: float) -> str:
    """The dictionary key a quantile level is stored under."""
    return _key(level)
