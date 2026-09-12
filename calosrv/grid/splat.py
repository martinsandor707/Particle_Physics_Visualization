"""Area-weighted resampling from the native lattice to a uniform display grid.

The problem this solves. The native lattice is irregular in x and merely
quasi-regular in y, and the display wants a uniform raster at an arbitrary
resolution R. Re-binning by assigning each source cell to whichever destination
bin contains its centre - point binning - produces exactly the artefacts the
resolution control is supposed to avoid: when R is finer than the source,
destination bins between two source centres receive nothing and the image
picket-fences; when R is coarser, one destination bin may capture two source
cells while its neighbour captures none, which is the periodic comb.

The fix is to treat both grids as what they physically are: tilings of an
interval by cells with finite width. A source cell spanning ``[a, b)`` that
overlaps a destination bin spanning ``[c, d)`` contributes the fraction
``overlap / (b - a)`` of its content. Every destination bin that any part of the
source touches receives a share, so there are no gaps at any R, and the total is
conserved exactly.

Two properties make this cheap enough to run per request:

*Separability.* A 2-D resampling of an ``(m, n)`` matrix is
``W_rows @ M @ W_cols.T``, two small matrix products rather than an
``O(m*n*R^2)`` scatter.

*Locality.* Each row of the overlap matrix touches only the handful of source
cells the destination bin spans, so the operator is sparse and the products cost
microseconds on the ~22 000-cell matrices involved.

Extensive quantities (summed energy, hit counts) are resampled directly and
conserve their total. Intensive quantities (mean Grad-CAM attention) must never
be resampled directly - averaging an average weights cells equally regardless of
how much energy each holds. Resample the numerator and the denominator
separately and divide afterwards; :func:`resample_ratio` does exactly that.
"""

from __future__ import annotations

import numpy as np


def overlap_matrix(src_edges: np.ndarray, dst_edges: np.ndarray) -> np.ndarray:
    """Fractional overlap operator mapping source cells to destination bins.

    Returns shape ``(len(dst_edges) - 1, len(src_edges) - 1)``. Entry ``[r, c]``
    is the fraction of source cell ``c`` that falls inside destination bin ``r``,
    so each column sums to at most 1 - exactly 1 for a source cell wholly inside
    the destination range, less for one hanging over the edge.

    Built with ``np.maximum``/``np.minimum`` on the outer product of the edges.
    That is ``O(R * n)`` in memory, which for the largest case here
    (512 destination bins against 211 source cells) is 108 000 float64 entries -
    under a megabyte, and small enough that a dense operator beats the
    bookkeeping of a sparse one.
    """
    src_lo = src_edges[:-1][None, :]
    src_hi = src_edges[1:][None, :]
    dst_lo = dst_edges[:-1][:, None]
    dst_hi = dst_edges[1:][:, None]

    overlap = np.minimum(src_hi, dst_hi) - np.maximum(src_lo, dst_lo)
    np.clip(overlap, 0.0, None, out=overlap)

    width = (src_hi - src_lo).astype(np.float64)
    # A degenerate zero-width source cell cannot contribute; guard the divide
    # rather than emit a NaN that would silently poison the whole panel.
    np.divide(overlap, width, out=overlap, where=width > 0)
    return overlap


def uniform_edges(lo: float, hi: float, n: int) -> np.ndarray:
    """``n + 1`` evenly spaced edges spanning ``[lo, hi]``."""
    return np.linspace(lo, hi, n + 1, dtype=np.float64)


def resample(
    matrix: np.ndarray,
    row_op: np.ndarray | None,
    col_op: np.ndarray | None,
) -> np.ndarray:
    """Apply row and column overlap operators to an extensive-quantity matrix.

    ``None`` for either operator means that axis is passed through unchanged,
    which is the common case for depth: the z axis is locked to the native
    layers in both display modes, so no depth operator is ever built.
    """
    out = np.asarray(matrix, dtype=np.float64)
    if row_op is not None:
        out = row_op @ out
    if col_op is not None:
        out = out @ col_op.T
    return out


def resample_ratio(
    numerator: np.ndarray,
    denominator: np.ndarray,
    row_op: np.ndarray | None,
    col_op: np.ndarray | None,
    fill: float = np.nan,
) -> np.ndarray:
    """Resample an intensive quantity expressed as a ratio.

    Both numerator and denominator are resampled as extensive quantities and
    divided at the destination resolution, which keeps the result an
    energy-weighted (or count-weighted) mean rather than a mean of means.

    Destination bins whose denominator is zero receive ``fill`` - by default
    NaN, which the encoder maps to the dedicated "empty" colour code rather than
    to the bottom of the ramp.
    """
    num = resample(numerator, row_op, col_op)
    den = resample(denominator, row_op, col_op)
    out = np.full(num.shape, fill, dtype=np.float64)
    np.divide(num, den, out=out, where=den > 0)
    return out


def build_axis_operator(
    src_edges: np.ndarray,
    n_dst: int,
    native: bool,
) -> np.ndarray | None:
    """Overlap operator for one axis, or ``None`` when no resampling is needed.

    ``native=True`` (or a destination count equal to the source count under a
    native plan) returns ``None`` so the matrix is passed through untouched -
    resampling a grid onto itself is an identity that costs a matrix product and
    introduces float round-off for nothing.
    """
    n_src = src_edges.size - 1
    if native or n_dst == n_src:
        return None
    dst_edges = uniform_edges(float(src_edges[0]), float(src_edges[-1]), n_dst)
    return overlap_matrix(src_edges, dst_edges)


def destination_edges(
    src_edges: np.ndarray, n_dst: int, native: bool
) -> np.ndarray:
    """The physical edges of the destination bins, for axis extents.

    In native mode these are the true (irregular) cell boundaries; in continuous
    mode they are evenly spaced across the same total extent. Either way the
    client positions the panel from these millimetre values, never from the
    matrix shape, which is what preserves the 1:1 metric aspect ratio.
    """
    if native:
        return src_edges
    return uniform_edges(float(src_edges[0]), float(src_edges[-1]), n_dst)
