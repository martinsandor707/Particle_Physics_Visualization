"""Circular statistics for azimuths.

An azimuth wraps, so its arithmetic mean is meaningless: two showers at +179°
and -179° average to 0°, the opposite of where both point (CLAUDE.md section 2,
"Never average a circular quantity"). Every summary of an angle on the circle
therefore goes through the resultant vector of its unit directions - the mean
resultant length R̄ in [0, 1] says how concentrated the directions are, and the
mean direction is only quoted beside it.

The SQL that rolls resultants up over millions of hits keeps its own sums
(``query/summary.py``, ``query/shower_frames.py``); these are the formulas the
Python side applies to them, one owner each.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

TWO_PI = 2.0 * math.pi

#: Above this Rayleigh p the directions are consistent with a uniform circle,
#: and a mean direction carries no information however precisely it is quoted.
UNIFORM_P = 0.05


def wrap_angle(x):
    """Map an angle, or an array of them, onto (-π, π].

    ``x - 2π ceil((x - π) / 2π)``: π stays π and -π becomes π, so the interval
    is half-open the conventional way round. ``np.angle`` can return -π, which
    is why it is not used.
    """
    if isinstance(x, np.ndarray):
        return x - TWO_PI * np.ceil((x - math.pi) / TWO_PI)
    return float(x) - TWO_PI * math.ceil((float(x) - math.pi) / TWO_PI)


def resultant_sums(phi: np.ndarray) -> tuple[float, float, int]:
    """``(Σ cos φ, Σ sin φ, n)`` over the finite angles."""
    a = np.asarray(phi, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.cos(a).sum()), float(np.sin(a).sum()), int(a.size)


def mean_resultant_length(c: float, s: float, n: int) -> float | None:
    """R̄ = √(C² + S²) / n, clamped to 1 against rounding; ``None`` at n = 0."""
    if not n:
        return None
    return min(1.0, math.hypot(c, s) / n)


def circular_mean(c: float, s: float) -> float | None:
    """The mean direction atan2(S, C) on (-π, π]; ``None`` when the resultant vanishes."""
    if c == 0.0 and s == 0.0:
        return None
    return wrap_angle(math.atan2(s, c))


def circular_sd(resultant: float | None) -> float | None:
    """The circular standard deviation √(-2 ln R̄), in radians; ``None`` at R̄ = 0."""
    if resultant is None or not resultant > 0.0:
        return None
    return math.sqrt(max(0.0, -2.0 * math.log(min(1.0, resultant))))


def rayleigh_p(n: int, resultant: float) -> float | None:
    """Rayleigh test p-value that ``n`` directions with mean resultant length
    ``resultant`` are drawn from a uniform circular distribution.

    The large-sample form ``exp(-n R^2)``; adequate for the gating it drives.
    """
    if n is None or n < 2 or resultant is None or not math.isfinite(resultant):
        return None
    return float(math.exp(-n * resultant * resultant))


@dataclass(frozen=True)
class CircularSummary:
    n: int
    mean_direction: float | None
    resultant: float | None
    circular_sd: float | None
    rayleigh_p: float | None
    note: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def describe_circular(phi: np.ndarray) -> CircularSummary:
    """The circular counterpart of ``describe()``: never a linear mean or SD."""
    c, s, n = resultant_sums(phi)
    resultant = mean_resultant_length(c, s, n)
    p = rayleigh_p(n, resultant) if resultant is not None else None
    if n == 0:
        note = "No finite angles in this selection."
    elif n == 1:
        note = "N = 1: one direction; no concentration can be estimated."
    elif p is not None and p > UNIFORM_P:
        note = (f"Directions are consistent with a uniform circle (R̄ = {resultant:.3f}, "
                f"Rayleigh p = {p:.2g}): the mean direction carries no information.")
    else:
        note = ""
    return CircularSummary(n, circular_mean(c, s) if n else None, resultant,
                           circular_sd(resultant), p, note)
