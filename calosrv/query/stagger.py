"""Detect a staggered transverse lattice in the native XY projection.

This exists because of a claim that turned out to be only half true.

One bin per real calorimeter cell does guarantee that no *one-dimensional* bin
is structurally empty: an ordinal index exists only where a cell exists. But the
XY panel is a two-dimensional product of two such axes, and on this detector the
set of populated ``(x, y)`` pairs is **not** the full product. The transverse
cells are staggered: alternate x columns intersect different subsets of the y
cells, so roughly half of every column is empty by geometry rather than by
physics.

Measured on the production dataset, adjacent native x columns alternate between
46.2% and 42.3% occupancy, and the lag-1 autocorrelation of the detrended column
profile is -0.25. The result is a fine vertical comb that a physicist could
reasonably read as detector structure, and which ``calodash/constants.py``
already documented for the batch pipeline - its solution was a 50.5 mm transverse
bin, chosen to stay commensurate with the lattice rather than beat against it.

Area-weighted splatting has the same effect and is measurable: the same
selection rendered at R = 150 has a lag-1 of +0.05 and 90% occupancy; at R = 104
it is +0.85 and 94%. So the honest presentation is to show the comb when the
user has asked for hardware truth, say plainly what it is, and name the control
that removes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Lag-1 autocorrelation below which a profile is called combed. A clean
#: alternation approaches -1; smoothly varying structure sits near 0 or above.
COMB_THRESHOLD = -0.10

#: Ignore the outermost fraction of each axis, where the detector's octagonal
#: outline dominates the occupancy and would swamp the measurement.
EDGE_MARGIN = 0.15

#: Smoothing window used to remove the real large-scale shower profile before
#: measuring cell-to-cell alternation.
DETREND_WINDOW = 9


@dataclass
class StaggerReport:
    staggered: bool
    lag1: float | None
    occupancy: float
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "staggered": self.staggered,
            "lag1": self.lag1,
            "occupancy": self.occupancy,
            "note": self.note,
        }


def _lag1(profile: np.ndarray) -> float | None:
    """Lag-1 autocorrelation of a profile, after removing its smooth trend."""
    if profile.size < DETREND_WINDOW * 3:
        return None
    window = np.ones(DETREND_WINDOW) / DETREND_WINDOW
    detrended = profile - np.convolve(profile, window, mode="same")
    # Drop the convolution's edge effects.
    half = DETREND_WINDOW // 2
    detrended = detrended[half:-half]
    if detrended.size < 4 or not np.any(detrended):
        return None
    a, b = detrended[:-1], detrended[1:]
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def intensity_lag1(matrix: np.ndarray) -> dict[str, float | None]:
    """Lag-1 autocorrelation of the detrended *energy* profiles of a raster.

    :func:`detect` looks at occupancy - whether a bin holds anything - which is
    the right instrument for the native lattice, where the comb is structurally
    empty bins. A sub-cell footprint splat fills every bin under a footprint by
    construction, so its residual comb, if any, is an *intensity* alternation
    that occupancy cannot see. Measured on the production dataset: point-binned
    cell centres (k = 1) gave a core-row energy lag-1 of -0.26 while the
    occupancy statistic barely moved; at k >= 2 both are positive.

    Returns the lag-1 of the column-summed energy profile and of the single
    brightest row ("core"), each ``None`` when too short to detrend.
    """
    values = np.asarray(matrix, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 16 or values.size == 0:
        return {"columns": None, "core_row": None}
    lo = int(values.shape[1] * EDGE_MARGIN)
    hi = int(values.shape[1] * (1.0 - EDGE_MARGIN))
    interior = values[:, lo:hi]
    columns = interior.sum(axis=0)
    core = interior[int(np.argmax(interior.sum(axis=1)))] if interior.shape[0] else columns
    return {"columns": _lag1(columns), "core_row": _lag1(core)}


def detect(matrix: np.ndarray) -> StaggerReport:
    """Measure whether ``matrix`` shows a column-to-column comb."""
    values = np.asarray(matrix, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 16:
        return StaggerReport(False, None, 0.0, "")

    populated = values > 0
    occupancy = float(populated.mean())

    lo = int(values.shape[1] * EDGE_MARGIN)
    hi = int(values.shape[1] * (1.0 - EDGE_MARGIN))
    interior = populated[:, lo:hi].mean(axis=0)

    lag1 = _lag1(interior)
    staggered = lag1 is not None and lag1 < COMB_THRESHOLD

    note = ""
    if staggered:
        note = (
            "The transverse cells are staggered: adjacent columns of the native "
            "lattice intersect different subsets of the y cells, so about half "
            f"of each column is empty by geometry (overall occupancy "
            f"{100 * occupancy:.0f}%). The resulting fine vertical comb is "
            "detector segmentation, not shower structure. Switch to Continuous "
            "Field to merge the staggered pairs into uniform bins."
        )
    return StaggerReport(staggered, lag1, occupancy, note)
