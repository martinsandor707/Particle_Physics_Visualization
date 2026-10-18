"""Shape statistics of one shower's energy cloud.

The principal axis of the energy-weighted covariance is the reference
notebook's check that the local frame did what it claims: after the rotation
the shower's own axis should lie close to ``+z'``, and the angle between the
two is printed on the panel. It is a statement about one cloud, so it needs
a cloud: below three cells, or with no energy, there is no axis to speak of
and ``None`` is returned rather than an angle of zero.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

#: Fewest weighted points for which a principal axis is quoted.
MIN_POINTS = 3


def principal_axis(points: np.ndarray, weights: np.ndarray) -> dict[str, Any] | None:
    """The energy-weighted principal axis of a 3-D cloud and its tilt from ``+z``.

    Returns ``{"tilt_deg", "axis", "eigenvalues", "n"}``: the angle in degrees
    between the largest eigenvector of the weighted covariance and ``+z``
    (``arccos |v_z|``, so the sign of the eigenvector does not matter), the
    unit eigenvector with its z component made non-negative, the three
    eigenvalues ascending, and the number of points. ``None`` when the cloud
    cannot define an axis.
    """
    pts = np.asarray(points, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    keep = np.isfinite(w) & (w > 0) & np.isfinite(pts).all(axis=1)
    pts, w = pts[keep], w[keep]
    if pts.shape[0] < MIN_POINTS or w.sum() <= 0:
        return None
    centre = np.average(pts, axis=0, weights=w)
    d = pts - centre
    cov = (d * w[:, None]).T @ d / w.sum()
    if not np.isfinite(cov).all():
        return None
    values, vectors = np.linalg.eigh(cov)
    if not (values[-1] > 0):
        return None
    axis = vectors[:, -1]
    if axis[2] < 0:
        axis = -axis
    tilt = math.degrees(math.acos(min(1.0, max(0.0, abs(float(axis[2]))))))
    return {
        "tilt_deg": tilt,
        "axis": [float(v) for v in axis],
        "eigenvalues": [float(v) for v in values],
        "n": int(pts.shape[0]),
    }
