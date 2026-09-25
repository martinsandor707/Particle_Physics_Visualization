"""Quantise a float matrix to 8-bit colour codes.

Code 0 is reserved for "no deposit". Codes 1 to 255 span the scale's value
range. That reservation matters: an empty detector cell and a cell holding the
faintest measurable deposit are different statements, and mapping both to the
bottom of the colour ramp makes an unlit region look like a faint halo.

**The canonical floor code.** The canonical panels reserve one more code. Code
1 there means "populated, but below the display floor" (10^-3 of the density
reference): such a bin is drawn transparent rather than folded into the opaque
bottom of the ramp, which painted the whole crop as a dark rectangle. The ramp
then starts at code 2 and has 253 levels. The laboratory frame passes no floor
code, keeps 254 levels starting at code 1, and quantises byte-for-byte as
before.

**On precision.** 254 levels across six decades is 0.0236 decades per step, or
about 5.6% in value; the canonical 253 levels across three decades are 0.0119
decades per step, 2.8%. Both are finer than the roughly one hundred
just-noticeable differences a continuous colormap resolves, so nothing visible
is lost. What is lost is tooltip fidelity, which is why ``topk.py`` carries
exact float64 values for the brightest cells - the ones a reader is most likely
to hover over and quote in a paper.
"""

from __future__ import annotations

import numpy as np

from .scale import ColorScale, SCALE_LOG

EMPTY_CODE = 0
MIN_CODE = 1
MAX_CODE = 255
LEVELS = MAX_CODE - MIN_CODE  # 254 usable steps

#: Canonical panels only: populated, but below the display floor.
BELOW_CODE = 1


def ramp_min_code(below_code: int | None = None) -> int:
    """First colour-ramp code: 1, or one above the floor code when there is one."""
    return MIN_CODE if below_code is None else int(below_code) + 1


def _populated(values: np.ndarray, scale: ColorScale) -> np.ndarray:
    if scale.scale == SCALE_LOG:
        return np.isfinite(values) & (values > 0)
    return np.isfinite(values)


def below_floor_mask(values: np.ndarray, scale: ColorScale) -> np.ndarray:
    """Populated bins below the scale's lower bound.

    The same criterion ``scale.relative_log_scale`` counts as ``n_below``: on a
    log scale a positive, finite value whose ``log10`` lies under ``vmin``; on
    a linear scale a finite value under ``vmin``.
    """
    v = np.asarray(values, dtype=np.float64)
    populated = _populated(v, scale)
    if scale.scale == SCALE_LOG:
        transformed = np.full(v.shape, scale.vmin, dtype=np.float64)
        np.log10(v, out=transformed, where=populated)
    else:
        transformed = np.where(populated, v, scale.vmin)
    return populated & (transformed < scale.vmin)


def quantize(
    matrix: np.ndarray,
    scale: ColorScale,
    below_code: int | None = None,
    below_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Map ``matrix`` onto ``uint8`` codes according to ``scale``.

    Values at or below zero (density) or non-finite (a Grad-CAM ratio with no
    denominator) become :data:`EMPTY_CODE`. Everything else is clamped into the
    scale's range and linearly quantised onto ``ramp_min_code(below_code)``
    to :data:`MAX_CODE`.

    With a ``below_code``, populated bins under the scale's floor - and any
    populated bin flagged in ``below_mask`` - receive that code instead of the
    bottom of the ramp. Without one the arithmetic is the legacy
    ``rint(normalised * 254) + 1``, so laboratory payloads are unchanged.
    """
    values = np.asarray(matrix, dtype=np.float64)
    codes = np.zeros(values.shape, dtype=np.uint8)
    min_code = ramp_min_code(below_code)
    levels = MAX_CODE - min_code

    populated = _populated(values, scale)
    if scale.scale == SCALE_LOG:
        transformed = np.full(values.shape, scale.vmin, dtype=np.float64)
        np.log10(values, out=transformed, where=populated)
    else:
        transformed = np.where(populated, values, scale.vmin)

    if populated.any():
        span = scale.vmax - scale.vmin
        if span <= 0:
            codes[populated] = MAX_CODE
        else:
            normalised = (transformed - scale.vmin) / span
            np.clip(normalised, 0.0, 1.0, out=normalised)
            scaled = np.rint(normalised * levels) + min_code
            codes[populated] = scaled[populated].astype(np.uint8)

    if below_code is not None:
        below = populated & (transformed < scale.vmin)
        if below_mask is not None:
            below |= np.asarray(below_mask, dtype=bool) & populated
        codes[below] = below_code
    return codes


def dequantize(codes: np.ndarray, scale: ColorScale, min_code: int = MIN_CODE) -> np.ndarray:
    """Inverse of :func:`quantize`, for tests and for server-side checks.

    ``min_code`` is the first ramp code the payload declares (2 on a canonical
    panel); codes below it - empty, or under the floor - come back as NaN.
    """
    codes = np.asarray(codes, dtype=np.float64)
    out = np.full(codes.shape, np.nan, dtype=np.float64)
    populated = codes >= min_code
    if not populated.any():
        return out
    fraction = (codes[populated] - min_code) / (MAX_CODE - min_code)
    value = scale.vmin + fraction * (scale.vmax - scale.vmin)
    out[populated] = np.power(10.0, value) if scale.scale == SCALE_LOG else value
    return out


def occupancy(codes: np.ndarray, min_code: int = MIN_CODE) -> float:
    """Fraction of cells drawn on the colour ramp (code ``>= min_code``)."""
    total = codes.size
    return float((codes >= min_code).sum() / total) if total else 0.0
