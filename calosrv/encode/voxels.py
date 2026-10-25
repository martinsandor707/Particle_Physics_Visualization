"""Byte packing of 3-D voxel and cube payloads: one owner for both voxel routes.

A 3-D view ships ordinals and quantised codes, never positions or raw values
(CLAUDE.md section 1.1: the browser never receives hit arrays). Ordinals are
relative to a grid the payload describes in millimetres, so a packed array
means nothing without its grid block.

* :func:`pack_ordinals` - one unsigned array, u8 when every value fits, else
  little-endian u16 (the single-event cubes of ``query/voxel_event.py``);
* :func:`pack_layer_runs` / :func:`unpack_layer_runs` - the ensemble's
  layer-run form, a voxel count per depth layer and one (x, y) pair per
  voxel (``query/voxels.py``).
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np


def b64(array: np.ndarray) -> str:
    """The array's bytes, as stored, in base64."""
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def pack_ordinals(values: np.ndarray) -> tuple[str, str]:
    """``(base64, dtype)``: unsigned bytes when every value fits, little-endian u16 otherwise."""
    array = np.asarray(values, dtype=np.int64)
    if array.size and (array.min() < 0 or array.max() > 0xFFFF):
        raise ValueError("a packed index must lie in 0..65535")
    if not array.size or array.max() <= 0xFF:
        return b64(array.astype(np.uint8)), "u8"
    return b64(array.astype("<u2")), "u16le"


def pack_layer_runs(vx: np.ndarray, vy: np.ndarray, vz: np.ndarray, n_z: int,
                    n_x: int, n_y: int) -> tuple[dict[str, Any], np.ndarray]:
    """Layer-run packing of voxel ordinals; returns the block and the payload order.

    Voxels are sorted by depth, then y, then x. ``layer_counts`` holds the
    number of voxels in each of the ``n_z`` layers (u16 little-endian),
    ``xy`` one ``(x, y)`` ordinal pair per voxel - u8, or u16 little-endian
    when an axis spans more than 256 voxels. Ordinals are relative to the
    first full voxel column, so they never encode a position by themselves:
    the grid block turns them into millimetres.
    """
    vx = np.asarray(vx, dtype=np.int64)
    vy = np.asarray(vy, dtype=np.int64)
    vz = np.asarray(vz, dtype=np.int64)
    order = np.lexsort((vx, vy, vz))
    counts = np.bincount(vz, minlength=n_z).astype("<u2") if vz.size else np.zeros(n_z, "<u2")
    wide = max(n_x, n_y) > 256
    dtype = "<u2" if wide else "u1"
    xy = np.empty(2 * order.size, dtype=dtype)
    xy[0::2] = vx[order]
    xy[1::2] = vy[order]
    block = {
        "layer_counts": b64(counts),
        "xy": b64(xy),
        "dtype": {"layer_counts": "u16le", "xy": "u16le" if wide else "u8", "code": "u8"},
    }
    return block, order


def unpack_layer_runs(block: dict[str, Any], n_z: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Inverse of the packing, for tests and server-side checks: ``(x, y, z, code)`` ordinals."""
    counts = np.frombuffer(base64.b64decode(block["layer_counts"]), dtype="<u2")
    assert counts.size == n_z
    dtype = "<u2" if block["dtype"]["xy"] == "u16le" else "u1"
    xy = np.frombuffer(base64.b64decode(block["xy"]), dtype=dtype).astype(np.int64)
    codes = np.frombuffer(base64.b64decode(block["code"]), dtype="u1")
    z = np.repeat(np.arange(n_z), counts.astype(np.int64))
    return xy[0::2], xy[1::2], z, codes
