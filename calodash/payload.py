"""Typed-array encoding of the browser payload.

Every hit reaches the client as three ``uint8`` cell indices plus a ``float32``
energy -- seven bytes -- and hits are ordered by event so each event owns a
contiguous slice. The client filters ~3,800 event scalars and then accumulates
only the slices that pass.

Three encoding rules are load-bearing:

One base64 string per field
    Concatenating fields into a single buffer breaks typed-array alignment:
    ``new Float32Array(buffer, 37877, n)`` throws, because the byte offset must
    be a multiple of the element size. Separate strings sidestep the issue
    entirely.

Explicit endianness
    ``astype('<f4')`` rather than the platform default, so a build on a
    big-endian machine cannot silently produce a corrupt dashboard.

Escaped ``</``
    The JSON is embedded inside a ``<script>`` element, where the character
    sequence ``</`` would otherwise be able to terminate it early.
"""

from __future__ import annotations

import base64
import json

import numpy as np


def _encode(array: np.ndarray, dtype: str) -> dict:
    """Encode one array as a base64 field descriptor."""
    contiguous = np.ascontiguousarray(array.astype(dtype))
    return {
        "dtype": dtype,
        "length": int(contiguous.size),
        "b64": base64.b64encode(contiguous.tobytes()).decode("ascii"),
    }


def encode_hits(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, energy: np.ndarray) -> dict:
    """Pack the per-hit arrays."""
    return {
        "count": int(energy.size),
        "ix": _encode(ix, "<u1"),
        "iy": _encode(iy, "<u1"),
        "iz": _encode(iz, "<u1"),
        "energy": _encode(energy, "<f4"),
    }


def encode_events(events, columns: dict[str, str]) -> dict:
    """Pack the per-event scalar arrays.

    ``columns`` maps payload key to numpy dtype string, so callers decide the
    width of each field rather than this module guessing.
    """
    packed = {"count": int(len(events))}
    for key, dtype in columns.items():
        packed[key] = _encode(events[key].to_numpy(), dtype)
    return packed


def to_json(payload: dict) -> str:
    """Serialise the payload for embedding in a ``<script>`` block."""
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    return text.replace("</", "<\\/")


def payload_bytes(payload: dict) -> int:
    """Approximate encoded size, for the build report."""
    return len(to_json(payload).encode("utf-8"))


def summarise(payload: dict) -> list[str]:
    """Human-readable size breakdown for the build report."""
    hits = payload.get("hits", {})
    events = payload.get("events", {})
    hit_bytes = sum(
        len(v["b64"]) for k, v in hits.items() if isinstance(v, dict) and "b64" in v
    )
    event_bytes = sum(
        len(v["b64"]) for k, v in events.items() if isinstance(v, dict) and "b64" in v
    )
    return [
        f"  hits      {hits.get('count', 0):,} x 7 B  -> {hit_bytes / 1024:,.0f} KiB base64",
        f"  events    {events.get('count', 0):,} scalars -> {event_bytes / 1024:,.0f} KiB base64",
        f"  payload   {payload_bytes(payload) / 1024:,.0f} KiB JSON total",
    ]
