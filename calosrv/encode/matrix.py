"""Assemble one projection panel into its wire payload.

The envelope carries everything the client needs to render the panel and to read
physical values back out of it: the raster, the scale constants, the millimetre
extents, the bin edges, and the exact values for the brightest cells.

The **edges** are the reason panels stay geometrically honest. The native
transverse lattice is irregular, so a bin index cannot be turned into a position
by multiplying a pitch. Shipping the edges lets the client place every column at
its true millimetre coordinate and keep a 1:1 metric aspect ratio regardless of
the matrix shape - which is what CLAUDE.md section 2 requires and what a
shape-derived aspect would violate.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np

from . import quantize, topk
from .scale import ColorScale


def _encode_edges(edges: np.ndarray, native: bool) -> dict[str, Any]:
    """Axis geometry: full edges when irregular, endpoints when uniform.

    A uniform axis is fully described by its two endpoints and a count, so
    sending 513 floats would be waste. An irregular one genuinely needs every
    edge, and 212 float32 values is about 1.1 KB - worth it, because without
    them the panel cannot be drawn in real space.
    """
    lo, hi = float(edges[0]), float(edges[-1])
    n = int(edges.size - 1)

    if n > 1:
        widths = np.diff(edges)
        uniform = bool(
            np.all(np.abs(widths - widths.mean()) <= 1e-6 * abs(widths.mean()))
        )
    else:
        uniform = True

    payload: dict[str, Any] = {
        "lo": lo,
        "hi": hi,
        "n": n,
        "uniform": uniform,
        "unit": "mm",
    }
    if not uniform:
        payload["edges"] = [float(v) for v in edges]
    return payload


def encode_matrix(
    matrix: np.ndarray,
    scale: ColorScale,
    row_edges: np.ndarray,
    col_edges: np.ndarray,
    row_axis: str,
    col_axis: str,
    panel: str,
    native: bool,
    k: int = topk.DEFAULT_K,
    symbols: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Encode one panel: raster, scale, geometry, and exact peak values.

    ``symbols`` optionally names how each axis is written on screen (``x'``
    for a canonical axis whose semantic identity is still ``x``). The axis
    ``name`` stays the semantic key every consumer indexes by; the display
    symbol is added only when given, so the lab-frame payload is unchanged.
    """
    codes = quantize.quantize(matrix, scale)
    raster = base64.b64encode(codes.tobytes(order="C")).decode("ascii")

    values = np.asarray(matrix, dtype=np.float64)
    finite = values[np.isfinite(values)]
    total = float(finite[finite > 0].sum()) if finite.size else 0.0

    row: dict[str, Any] = {"name": row_axis, **_encode_edges(row_edges, native)}
    col: dict[str, Any] = {"name": col_axis, **_encode_edges(col_edges, native)}
    if symbols:
        row["symbol"] = symbols.get(row_axis, row_axis)
        col["symbol"] = symbols.get(col_axis, col_axis)

    return {
        "panel": panel,
        "encoding": "u8-b64",
        "shape": [int(codes.shape[0]), int(codes.shape[1])],
        "data": raster,
        "empty_code": quantize.EMPTY_CODE,
        "min_code": quantize.MIN_CODE,
        "max_code": quantize.MAX_CODE,
        "scale": scale.as_dict(),
        "axes": {"row": row, "col": col},
        "occupancy": round(quantize.occupancy(codes), 6),
        "total": total,
        "topk": topk.top_cells(matrix, k),
    }
