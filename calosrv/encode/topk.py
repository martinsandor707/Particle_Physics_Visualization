"""Exact values for the brightest cells.

Quantisation costs about 5.6% of relative precision per colour step. That is
invisible in the image and unacceptable in a tooltip, because the cells a reader
hovers over are the ones they are about to write down. Shipping the exact
value for the brightest handful of cells restores full precision exactly where
it is used, for a few hundred bytes.

On the ``/api/projections`` panels the value travels at :data:`SIGNIFICANT`
significant figures, rounded toward zero. That is the precision of the float32
source columns (2^-24 relative, about 7.2 digits), so nothing the data hold is
lost, and it is twice what the tooltips print. Rounding toward zero, never to nearest, keeps every shipped
magnitude at or below the cell's own, so the brightest value can never exceed
the panel's peak. At 17 digits the 64 values of three panels cost 1.6-1.8 KB a
response (review R-4, decision on R6).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_K = 64

#: Significant figures of a shipped value: the float32 source's precision.
SIGNIFICANT = 7


def toward_zero(value: float, digits: int = SIGNIFICANT) -> float:
    """``value`` at ``digits`` significant figures, truncated toward zero.

    The magnitude never exceeds ``abs(value)``: where a product rounds up to the
    next integer, the last digit is stepped back. Zero and non-finite values
    pass through.
    """
    v = float(value)
    if v == 0.0 or not math.isfinite(v):
        return v
    exponent = math.floor(math.log10(abs(v)))
    shift = digits - 1 - exponent
    if shift >= 0:
        scale = 10.0 ** shift
        kept = math.trunc(v * scale)
        out = kept / scale
        if abs(out) > abs(v):
            out = (kept - math.copysign(1, v)) / scale
    else:
        scale = 10.0 ** (-shift)
        kept = math.trunc(v / scale)
        out = kept * scale
        if abs(out) > abs(v):
            out = (kept - math.copysign(1, v)) * scale
    return float(out)


def top_cells(
    matrix: np.ndarray, k: int = DEFAULT_K, signed: bool = False,
    significant: int | None = None,
) -> list[dict[str, Any]]:
    """The ``k`` largest cells, as ``{i, j, value}`` in descending order.

    ``signed`` ranks by magnitude and keeps the sign, for a diverging channel
    whose most negative bins matter as much as its most positive ones.
    ``significant`` ships each value at that many significant figures, rounded
    toward zero (:func:`toward_zero`); ``None`` ships it whole. The
    ``/api/projections`` panels pass :data:`SIGNIFICANT`; ``/api/event`` keeps
    whole values, because its 3-D ramp quotes the brightest cube's value as
    its top and is pinned to it.
    """
    values = np.asarray(matrix, dtype=np.float64)
    if signed:
        finite = np.isfinite(values) & (values != 0)
        rank = np.abs(values)
    else:
        finite = np.isfinite(values) & (values > 0)
        rank = values
    count = int(finite.sum())
    if count == 0:
        return []

    k = min(k, count)
    flat = np.where(finite, rank, -np.inf).ravel()
    # argpartition finds the k largest without sorting the whole matrix, which
    # matters when the native XY panel holds twenty thousand cells.
    picked = np.argpartition(flat, -k)[-k:]
    picked = picked[np.argsort(flat[picked])[::-1]]

    rows, cols = np.unravel_index(picked, values.shape)
    return [
        {"i": int(r), "j": int(c),
         "value": float(values[r, c]) if significant is None
         else toward_zero(values[r, c], significant)}
        for r, c in zip(rows, cols)
    ]
