"""Quantise a float matrix to 8-bit colour codes.

Code 0 is reserved for "no deposit". Codes 1 to 255 span the scale's value
range. That reservation matters: an empty detector cell and a cell holding the
faintest measurable deposit are different statements, and mapping both to the
bottom of the colour ramp makes an unlit region look like a faint halo.

**On precision.** 254 levels across six decades is 0.0236 decades per step, or
about 5.6% in value. That is finer than the roughly one hundred just-noticeable
differences a continuous colormap resolves, so nothing visible is lost. What is
lost is tooltip fidelity, which is why ``topk.py`` carries exact float64 values
for the brightest cells - the ones a reader is most likely to hover over and
quote in a paper.
"""

from __future__ import annotations

import numpy as np

from .scale import ColorScale, SCALE_LOG

EMPTY_CODE = 0
MIN_CODE = 1
MAX_CODE = 255
LEVELS = MAX_CODE - MIN_CODE  # 254 usable steps


def quantize(matrix: np.ndarray, scale: ColorScale) -> np.ndarray:
    """Map ``matrix`` onto ``uint8`` codes according to ``scale``.

    Values at or below zero (density) or non-finite (a Grad-CAM ratio with no
    denominator) become :data:`EMPTY_CODE`. Everything else is clamped into the
    scale's range and linearly quantised.
    """
    values = np.asarray(matrix, dtype=np.float64)
    codes = np.zeros(values.shape, dtype=np.uint8)

    if scale.scale == SCALE_LOG:
        populated = np.isfinite(values) & (values > 0)
        transformed = np.full(values.shape, scale.vmin, dtype=np.float64)
        np.log10(values, out=transformed, where=populated)
    else:
        populated = np.isfinite(values)
        transformed = np.where(populated, values, scale.vmin)

    if not populated.any():
        return codes

    span = scale.vmax - scale.vmin
    if span <= 0:
        codes[populated] = MAX_CODE
        return codes

    normalised = (transformed - scale.vmin) / span
    np.clip(normalised, 0.0, 1.0, out=normalised)

    scaled = np.rint(normalised * LEVELS) + MIN_CODE
    codes[populated] = scaled[populated].astype(np.uint8)
    return codes


def dequantize(codes: np.ndarray, scale: ColorScale) -> np.ndarray:
    """Inverse of :func:`quantize`, for tests and for server-side checks."""
    codes = np.asarray(codes, dtype=np.float64)
    out = np.full(codes.shape, np.nan, dtype=np.float64)
    populated = codes >= MIN_CODE
    if not populated.any():
        return out
    fraction = (codes[populated] - MIN_CODE) / LEVELS
    value = scale.vmin + fraction * (scale.vmax - scale.vmin)
    out[populated] = np.power(10.0, value) if scale.scale == SCALE_LOG else value
    return out


def occupancy(codes: np.ndarray) -> float:
    """Fraction of cells holding a deposit."""
    total = codes.size
    return float((codes >= MIN_CODE).sum() / total) if total else 0.0
