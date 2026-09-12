"""Exact values for the brightest cells.

Quantisation costs about 5.6% of relative precision per colour step. That is
invisible in the image and unacceptable in a tooltip, because the cells a reader
hovers over are the ones they are about to write down. Shipping the exact
float64 value for the brightest handful of cells restores full precision exactly
where it is used, for a few hundred bytes.
"""

from __future__ import annotations

from typing import Any

import numpy as np

DEFAULT_K = 64


def top_cells(matrix: np.ndarray, k: int = DEFAULT_K) -> list[dict[str, Any]]:
    """The ``k`` largest cells, as ``{i, j, value}`` in descending order."""
    values = np.asarray(matrix, dtype=np.float64)
    finite = np.isfinite(values) & (values > 0)
    count = int(finite.sum())
    if count == 0:
        return []

    k = min(k, count)
    flat = np.where(finite, values, -np.inf).ravel()
    # argpartition finds the k largest without sorting the whole matrix, which
    # matters when the native XY panel holds twenty thousand cells.
    picked = np.argpartition(flat, -k)[-k:]
    picked = picked[np.argsort(flat[picked])[::-1]]

    rows, cols = np.unravel_index(picked, values.shape)
    return [
        {"i": int(r), "j": int(c), "value": float(values[r, c])}
        for r, c in zip(rows, cols)
    ]
