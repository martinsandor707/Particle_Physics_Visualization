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


#: Below this mean square of sin(α − ᾱ) - a spread under a microradian - the
#: angles have no spread about their mean direction: the quadratic form of the
#: sums cancels to about 1e-16 per angle, and no correlation is quoted.
_NO_SPREAD = 1e-12


def circular_correlation_from_sums(n: float, s: np.ndarray, q: np.ndarray) -> float | None:
    """Jammalamadaka-SenGupta r_c from the moment sums of (cos α, sin α, cos β, sin β).

    ``s[i] = Σ u_i`` and ``q[i, j] = Σ u_i u_j`` over the four unit-vector
    components. sin(α − ᾱ) = e_α · (cos α, sin α) with e_α = (−sin ᾱ, cos ᾱ),
    so every sum :func:`circular_correlation` needs is a quadratic form of the
    raw second moments - which lets a grouped jackknife leave groups out of the
    sums. ``None`` below two pairs, without a mean direction, or without spread.
    """
    if not n >= 2:
        return None
    s = np.asarray(s, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    mean_a = circular_mean(float(s[0]), float(s[1]))
    mean_b = circular_mean(float(s[2]), float(s[3]))
    if mean_a is None or mean_b is None:
        return None
    ea = np.array([-math.sin(mean_a), math.cos(mean_a)])
    eb = np.array([-math.sin(mean_b), math.cos(mean_b)])
    saa = float(ea @ q[0:2, 0:2] @ ea)
    sbb = float(eb @ q[2:4, 2:4] @ eb)
    if not (saa > _NO_SPREAD * n and sbb > _NO_SPREAD * n):
        return None
    r = float(ea @ q[0:2, 2:4] @ eb) / math.sqrt(saa * sbb)
    return max(-1.0, min(1.0, r)) if math.isfinite(r) else None


def circular_correlation(alpha: np.ndarray, beta: np.ndarray) -> float | None:
    """The circular-circular correlation r_c of paired angles (Jammalamadaka & SenGupta 2001).

    ``r_c = Σ sin(α − ᾱ) sin(β − β̄) / √(Σ sin²(α − ᾱ) · Σ sin²(β − β̄))``, with
    ᾱ and β̄ the circular means: in [−1, 1], unchanged by rotating either angle
    - so by where the ±π cut falls - and sign-flipped by reflecting one. A
    Pearson r of two azimuths has neither property. Pairs with a non-finite
    angle are left out.
    """
    a = np.asarray(alpha, dtype=np.float64)
    b = np.asarray(beta, dtype=np.float64)
    keep = np.isfinite(a) & np.isfinite(b)
    u = np.column_stack([np.cos(a[keep]), np.sin(a[keep]), np.cos(b[keep]), np.sin(b[keep])])
    return circular_correlation_from_sums(float(u.shape[0]), u.sum(axis=0), u.T @ u)
