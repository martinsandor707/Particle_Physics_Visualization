"""Footprint splats in NumPy, for the hits of one event.

The ensemble scans splat inside DuckDB (``query/shower_frames.py``,
``query/canonical.py``), where a cross join against the sub-deposit offsets
is the right tool for twenty-four million rows. One event has a few hundred to
a few thousand cells, for which the same two operations are a handful of
array expressions, and the per-event inspector (``query/event_inspector.py``)
needs windows the ensemble grids do not offer - its depth axis is cropped to
the event, for one. So the two splats are written here once more, in NumPy,
with the same definitions as the SQL:

* **Box overlap** (the translated frame, no rotation): a cell is an
  axis-aligned box of the measured footprint, and each grid bin receives the
  exact fraction of its area the bin covers. Energy is conserved; a box that
  reaches past the window is counted outside in full, as the SQL counts it.
* **Rotated sub-deposits** (the local frame): a cell's footprint box -
  including the layer pitch along depth - is sampled by ``k x k x k_z`` equal
  sub-deposits, each offset rotated by the shower's own ``R`` and binned by
  ``floor`` on a uniform grid, exactly as ``_local_sql`` does.

Both bin by ``floor((u - lo) / pitch)`` on uniform grids, never through a
pitch multiplication in the other direction (CLAUDE.md section 2).
"""

from __future__ import annotations

import numpy as np

from .splat import overlap_matrix


def box_overlap_2d(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray,
    width_x: float, width_y: float, x_edges: np.ndarray, y_edges: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Energy of axis-aligned boxes spread over a 2-D grid by exact area overlap.

    Returns ``(matrix (rows y, cols x), weight outside)``. A box not wholly
    inside both axes' ranges is counted outside in full - the ensemble scan's
    rule, so the three panels of an event hold the same hits.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    out = np.zeros((y_edges.size - 1, x_edges.size - 1))
    if x.size == 0:
        return out, 0.0
    hx, hy = 0.5 * float(width_x), 0.5 * float(width_y)
    inside = ((x - hx >= x_edges[0]) & (x + hx <= x_edges[-1])
              & (y - hy >= y_edges[0]) & (y + hy <= y_edges[-1]))
    if inside.any():
        ox = _overlap_fractions(x[inside] - hx, x[inside] + hx, x_edges)
        oy = _overlap_fractions(y[inside] - hy, y[inside] + hy, y_edges)
        out = np.einsum("h,hy,hx->yx", w[inside], oy, ox)
    return out, float(w[~inside].sum())


def box_overlap_1d(
    u: np.ndarray, weights: np.ndarray, width: float, edges: np.ndarray, inside: np.ndarray,
) -> np.ndarray:
    """``(hits, bins)`` overlap fractions of boxes along one axis, zero for hits not ``inside``."""
    u = np.asarray(u, dtype=np.float64)
    half = 0.5 * float(width)
    out = np.zeros((u.size, edges.size - 1))
    if inside.any():
        out[inside] = _overlap_fractions(u[inside] - half, u[inside] + half, edges)
    return out


def _overlap_fractions(lo: np.ndarray, hi: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Fraction of each box ``[lo, hi]`` inside each bin of ``edges``: ``(boxes, bins)``."""
    left = np.maximum(lo[:, None], edges[None, :-1])
    right = np.minimum(hi[:, None], edges[None, 1:])
    return np.clip(right - left, 0.0, None) / (hi - lo)[:, None]


def subdeposit_offsets(footprint: tuple[float, float, float], k: int, k_z: int) -> np.ndarray:
    """The ``k * k * k_z`` sub-deposit offsets over a cell's box, in cell axes, ``(n, 3)``.

    The same lattice ``_local_sql`` samples: ``((i + 0.5) / k - 0.5) * width``
    along each axis, so the mean offset is zero and the sub-deposits tile the
    box evenly.
    """
    wx, wy, wz = (float(v) for v in footprint)
    fx = ((np.arange(k) + 0.5) / k - 0.5) * wx
    fy = ((np.arange(k) + 0.5) / k - 0.5) * wy
    fz = ((np.arange(k_z) + 0.5) / k_z - 0.5) * wz
    gx, gy, gz = np.meshgrid(fx, fy, fz, indexing="ij")
    return np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])


def rotated_subdeposits(
    centres: np.ndarray, rotation: np.ndarray, weights: np.ndarray,
    footprint: tuple[float, float, float], k: int, k_z: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Each cell split into rotated sub-deposits: ``(points (n * m, 3), weights (n * m,))``.

    ``centres`` are the cells' centres in the frame, ``rotation`` the frame's
    ``R`` as ``(3, 3)`` for one shower or ``(n, 3, 3)`` per cell, and each
    sub-deposit carries ``1 / m`` of its cell's weight, so the total is
    conserved for any ``k``.
    """
    centres = np.asarray(centres, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    r = np.asarray(rotation, dtype=np.float64)
    offsets = subdeposit_offsets(footprint, k, k_z)          # (m, 3)
    m = offsets.shape[0]
    if r.ndim == 2:
        rotated = offsets @ r.T                                # (m, 3)
        points = centres[:, None, :] + rotated[None, :, :]
    else:
        rotated = np.einsum("nij,mj->nmi", r, offsets)         # (n, m, 3)
        points = centres[:, None, :] + rotated
    return points.reshape(-1, 3), np.repeat(w / m, m)


def bin_uniform(
    points: np.ndarray, weights: np.ndarray, edges: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, float]:
    """Sum ``weights`` into the uniform bins of ``edges`` by ``floor``; the rest counted outside.

    ``edges[i]`` bounds axis ``i`` of ``points``; the result has one axis per
    entry, in that order. A point on the upper edge is outside, as in SQL.
    """
    pts = np.asarray(points, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    shape = tuple(e.size - 1 for e in edges)
    out = np.zeros(shape)
    if pts.size == 0:
        return out, 0.0
    index = []
    inside = np.ones(pts.shape[0], dtype=bool)
    for axis, e in enumerate(edges):
        pitch = float(e[1] - e[0])
        j = np.floor((pts[:, axis] - e[0]) / pitch).astype(np.int64)
        inside &= (j >= 0) & (j < e.size - 1)
        index.append(j)
    if inside.any():
        np.add.at(out, tuple(j[inside] for j in index), w[inside])
    return out, float(w[~inside].sum())


__all__ = [
    "box_overlap_2d", "box_overlap_1d", "subdeposit_offsets", "rotated_subdeposits", "bin_uniform",
    "overlap_matrix",
]
