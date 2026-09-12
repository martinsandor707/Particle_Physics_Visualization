"""Compact encoding of projection matrices for the wire.

A dense float64 matrix serialised as JSON is both enormous and useless to a
colour mapper. This package turns one into an 8-bit raster plus the handful of
constants needed to read physical values back out of it.
"""

from __future__ import annotations

from .scale import ColorScale, resolve_scale
from .matrix import encode_matrix

__all__ = ["ColorScale", "resolve_scale", "encode_matrix"]
