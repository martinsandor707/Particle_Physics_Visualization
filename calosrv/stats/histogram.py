"""Density-normalised histograms for the reconstructed-energy panel.

All series in a panel share one binning. That is not a tidiness preference: the
panel overlays predicted against true energies for the same events, and two
histograms on different bin edges cannot be compared bin by bin no matter how
similar they look.

``density=True`` normalisation matches ``calodash/stats.py`` and the reference
notebook, and it is what makes the bars directly comparable with the fitted
Gaussian curve, which is a probability density.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Bin count, transcribed from the reference notebook's ``bins=120``.
DEFAULT_BINS = 120

#: Points used to draw a fitted curve. Enough that the peak is smooth at any
#: reasonable panel width, small enough that four series across five slices stay
#: well inside the payload budget.
CURVE_POINTS = 200


@dataclass
class Histogram:
    """One density-normalised histogram on a shared axis."""

    counts: list[float]
    centres: list[float]
    edges: list[float]
    n: int
    n_in_range: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "centres": self.centres,
            "n": self.n,
            "n_in_range": self.n_in_range,
        }


def axis_edges(lo: float, hi: float, bins: int = DEFAULT_BINS) -> np.ndarray:
    if not hi > lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, bins + 1, dtype=np.float64)


def density_histogram(
    values: np.ndarray, edges: np.ndarray
) -> Histogram:
    """Histogram ``values`` on fixed ``edges``, normalised to unit area."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    lo, hi = float(edges[0]), float(edges[-1])
    in_range = finite[(finite >= lo) & (finite <= hi)]

    if in_range.size == 0:
        counts = np.zeros(edges.size - 1, dtype=np.float64)
    else:
        counts, _ = np.histogram(in_range, bins=edges, density=True)

    centres = 0.5 * (edges[:-1] + edges[1:])
    return Histogram(
        counts=[float(c) for c in counts],
        centres=[float(c) for c in centres],
        edges=[float(e) for e in edges],
        n=int(finite.size),
        n_in_range=int(in_range.size),
    )


def curve_axis(lo: float, hi: float, points: int = CURVE_POINTS) -> np.ndarray:
    """Sample positions for a fitted probability density curve."""
    if not hi > lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, points, dtype=np.float64)
