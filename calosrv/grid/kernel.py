"""Conservative reconstruction kernels for display resampling of a uniform grid.

Maths only; which kernel a request gets is decided in ``query/reconstruct.py``.

**The problem.** The canonical accumulation grid holds energy in 20 mm bins.
Drawn as they are, a handful of co-registered events reads as a mosaic of
rotated cell blocks; drawn through a point interpolation, energy is invented or
lost between samples. What the display needs is an operator that turns a
raster of *binned energy* into a finer raster of binned energy without
creating, destroying or inventing any.

**The construction.** Each source bin ``c`` is taken as a slab of energy
spread over its extent and then blurred by a kernel. Its mass below a
position ``d`` is a cumulative distribution ``G_c(d)``, and the share it gives
destination bin ``[d_r, d_r+1)`` is::

    W[r, c] = G_c(d_r+1) - G_c(d_r)

Every such operator has the three properties the display relies on:

* **Non-negative**: ``G_c`` is monotone, so no entry is negative (round-off
  near ``-1e-16`` is clipped to zero).
* **Conservative**: a column telescopes to the kernel mass inside the
  destination range - exactly 1 when the destination covers the kernel's
  support, less when part of it falls outside, which the caller counts.
* **A partition of unity** on a uniform source: a flat field stays flat, so the
  reconstructed density of a destination bin is a weighted *mean* of source
  densities and can never exceed the raw peak. That makes the raw 20 mm-grid
  peak a proven upper bound on everything drawn from it.

The kernels:

``none`` / ``box``
    The area-weighted overlap operator of ``grid/splat.py``, unchanged.

``bilinear`` (tent)
    Exact linear interpolation through the bin centres, integrated over each
    destination bin: the kernel of bin ``c`` is a tent of half-width ``p``
    centred on it, with cumulative ``H(u) = (1+u)^2 / 2`` on ``[-1, 0]`` and
    ``1 - (1-u)^2 / 2`` on ``(0, 1]``. Defined only on a uniform source, so it
    can never be applied to the irregular laboratory lattice.

``gaussian``
    Each bin taken as uniform, then convolved with ``N(0, sigma^2)``. With
    ``psi(u) = u Phi(u) + phi(u)`` the smeared cumulative of a bin
    ``[a, b)`` of width ``w`` is ``(sigma / w) [psi(u_a) - psi(u_b)]``, and
    splitting ``psi(u) = max(u, 0) + psi~(u)`` separates the box part::

        W = overlap_matrix + diff_r[(sigma / w) (psi~(u_a) - psi~(u_b))]
        psi~(z) = phi(|z|) - |z| erfc(|z| / sqrt 2) / 2

    ``psi~`` is set to exactly zero for ``|z| >= 9``, so as ``sigma -> 0`` the
    operator reduces to the box operator exactly, and a source bin more than
    ``9 sigma`` from the destination contributes exactly nothing - which is
    what lets the caller slice the source to the window plus a finite reach.

Rejected, and why: bicubic interpolation has negative lobes, so it produces
negative densities and overshoots the peak; point interpolation samples the
field instead of integrating it, so it does not conserve energy.

**Spread per bin**, the RMS width a single 20 mm bin's energy acquires: box
``p / sqrt 12`` = 5.77 mm, tent ``p / sqrt 6`` = 8.165 mm, Gaussian
``sqrt(p^2 / 12 + sigma^2)`` = 11.547 mm at ``sigma = 10`` mm.

**Precision.** numpy has no ``erf`` and scipy is not a dependency, so ``erfc``
is the Numerical Recipes Chebyshev fit ``erfcc`` (fractional error below
1.2e-7 everywhere). The Abramowitz & Stegun 7.1.26 form is *not* used: its
relative error in the tails is 0.3-1.8%. Every input is cast to ``float64``
and all arithmetic stays there, because ``psi~`` is a difference of two
nearly equal terms in the tails and cancels badly in ``float32``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .splat import overlap_matrix

#: ``psi~`` is set to exactly zero beyond this many standard deviations. The
#: true value there is below 1.3e-20 of a bin, far under float64 resolution of
#: the unit column sum.
TAIL_Z = 9.0

KERNEL_NONE = "none"
KERNEL_BOX = "box"
KERNEL_BILINEAR = "bilinear"
KERNEL_GAUSSIAN = "gaussian"
KERNELS = (KERNEL_NONE, KERNEL_BOX, KERNEL_BILINEAR, KERNEL_GAUSSIAN)

#: A source counts as uniform for the tent when every bin width is within this
#: relative tolerance of the mean width.
UNIFORM_TOLERANCE = 1e-9

#: Numerical Recipes ``erfcc`` coefficients, innermost term last.
_ERFCC = (
    -1.26551223, 1.00002368, 0.37409196, 0.09678418, -0.18628806,
    0.27886807, -1.13520398, 1.48851587, -0.82215223, 0.17087277,
)

_INV_SQRT2 = 1.0 / math.sqrt(2.0)
_INV_SQRT2PI = 1.0 / math.sqrt(2.0 * math.pi)


# ------------------------------------------------------------ primitives --


def erfcc(x: Any) -> np.ndarray:
    """Complementary error function, fractional error below 1.2e-7.

    Numerical Recipes' Chebyshev fit on ``|x|``, with ``erfc(-x) = 2 - erfc(x)``
    for negative arguments. Monotone decreasing, as the operator requires.
    """
    x = np.asarray(x, dtype=np.float64)
    z = np.abs(x)
    t = 1.0 / (1.0 + 0.5 * z)
    poly = np.full(z.shape, _ERFCC[-1], dtype=np.float64)
    for coefficient in reversed(_ERFCC[:-1]):
        poly = coefficient + t * poly
    ans = t * np.exp(-z * z + poly)
    return np.where(x >= 0.0, ans, 2.0 - ans)


def psi_tilde(z: Any) -> np.ndarray:
    """``phi(|z|) - |z| Q(|z|)``: the non-linear part of ``psi(u) = u Phi(u) + phi(u)``.

    ``psi`` is the antiderivative of the normal CDF. For ``u >= 0``,
    ``u Phi(u) = u - u Q(u)``; for ``u < 0``, ``u Phi(u) = -|u| Q(|u|)`` by
    symmetry. Either way ``psi(u) = max(u, 0) + psi~(u)`` with ``psi~`` even,
    positive and decaying like ``phi(z) / z^2``. Exactly zero for
    ``|z| >= TAIL_Z``.
    """
    z = np.abs(np.asarray(z, dtype=np.float64))
    out = _INV_SQRT2PI * np.exp(-0.5 * z * z) - z * 0.5 * erfcc(z * _INV_SQRT2)
    return np.where(z >= TAIL_Z, 0.0, out)


def tent_cdf(u: Any) -> np.ndarray:
    """Cumulative distribution of the unit tent on ``[-1, 1]``."""
    u = np.asarray(u, dtype=np.float64)
    out = np.where(u <= 0.0, 0.5 * (1.0 + u) ** 2, 1.0 - 0.5 * (1.0 - u) ** 2)
    out = np.where(u <= -1.0, 0.0, out)
    return np.where(u >= 1.0, 1.0, out)


# ---------------------------------------------------------------- kernels --


@dataclass(frozen=True)
class Kernel:
    """A separable, conservative, non-negative reconstruction kernel."""

    name: str
    sigma_mm: float | None = None

    def __post_init__(self) -> None:
        if self.name not in KERNELS:
            raise ValueError(f"Unknown kernel {self.name!r}; expected one of {', '.join(KERNELS)}.")
        if self.name == KERNEL_GAUSSIAN:
            if self.sigma_mm is None or not math.isfinite(self.sigma_mm) or self.sigma_mm <= 0:
                raise ValueError(f"A Gaussian kernel needs a positive sigma; got {self.sigma_mm!r}.")
        elif self.sigma_mm is not None:
            raise ValueError(f"Only the Gaussian kernel takes a sigma; {self.name} got {self.sigma_mm!r}.")

    @property
    def smooths(self) -> bool:
        """Whether the kernel spreads energy beyond its own bin."""
        return self.name in (KERNEL_BILINEAR, KERNEL_GAUSSIAN)

    def bin_spread_rms(self, pitch: float) -> float:
        """RMS width, in mm, that one source bin of width ``pitch`` acquires."""
        p = float(pitch)
        if self.name == KERNEL_BILINEAR:
            return p / math.sqrt(6.0)
        if self.name == KERNEL_GAUSSIAN:
            return math.sqrt(p * p / 12.0 + float(self.sigma_mm) ** 2)
        return p / math.sqrt(12.0)

    def reach_bins(self, pitch: float) -> int:
        """Source bins beyond a destination edge that can still reach it.

        The tent reaches one bin; the Gaussian ``9 sigma``, rounded up, plus one
        for the bin's own width. Slicing the source to the window plus this
        reach is exact, because ``psi~`` is exactly zero past ``TAIL_Z``.
        """
        if self.name == KERNEL_BILINEAR:
            return 1
        if self.name == KERNEL_GAUSSIAN:
            p = float(pitch)
            if p <= 0:
                raise ValueError(f"pitch must be positive; got {pitch!r}.")
            return int(math.ceil(TAIL_Z * float(self.sigma_mm) / p - 1e-9)) + 1
        return 0

    def label(self) -> str:
        if self.name == KERNEL_GAUSSIAN:
            return f"Gaussian σ = {self.sigma_mm:g} mm"
        if self.name == KERNEL_BILINEAR:
            return "bilinear (tent)"
        if self.name == KERNEL_BOX:
            return "box (area-weighted overlap)"
        return "none (raw bins)"

    def as_dict(self, pitch: float) -> dict[str, Any]:
        return {
            "type": self.name,
            "sigma_mm": self.sigma_mm,
            "bin_spread_rms_mm": round(self.bin_spread_rms(pitch), 3),
            "separable": True,
            "conservative": True,
            "non_negative": True,
        }


NONE = Kernel(KERNEL_NONE)
BOX = Kernel(KERNEL_BOX)
BILINEAR = Kernel(KERNEL_BILINEAR)


def gaussian(sigma_mm: float) -> Kernel:
    """A uniform-bin-convolved-with-Gaussian kernel of standard deviation ``sigma_mm``."""
    return Kernel(KERNEL_GAUSSIAN, float(sigma_mm))


# --------------------------------------------------------------- operator --


def _gaussian_operator(src: np.ndarray, dst: np.ndarray, sigma: float) -> np.ndarray:
    width = np.diff(src)
    ratio = np.zeros(width.shape, dtype=np.float64)
    np.divide(sigma, width, out=ratio, where=width > 0)
    # Adjacent source bins share an edge, so psi~ is evaluated once per
    # (destination edge, source edge) pair - and only inside the 9-sigma band,
    # where it is non-zero; outside it is exactly zero by definition. On a
    # production X'Z' window that is about an eighth of the pairs.
    u = (dst[:, None] - src[None, :]) / sigma
    psi = np.zeros(u.shape, dtype=np.float64)
    near = np.abs(u) < TAIL_Z
    psi[near] = psi_tilde(u[near])
    tail = ratio[None, :] * (psi[:, :-1] - psi[:, 1:])
    return overlap_matrix(src, dst) + np.diff(tail, axis=0)


def _tent_operator(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    widths = np.diff(src)
    pitch = float(widths.mean()) if widths.size else 0.0
    if pitch <= 0 or np.any(np.abs(widths - pitch) > UNIFORM_TOLERANCE * pitch):
        raise ValueError(
            "The bilinear (tent) kernel needs a uniform source grid; this one has bin "
            f"widths from {float(widths.min()):.6g} to {float(widths.max()):.6g} mm."
        )
    centres = 0.5 * (src[:-1] + src[1:])
    cumulative = tent_cdf((dst[:, None] - centres[None, :]) / pitch)
    return np.diff(cumulative, axis=0)


def operator(src_edges: Any, dst_edges: Any, kernel: Kernel) -> np.ndarray:
    """The ``(n_dst, n_src)`` operator mapping source bins onto destination bins.

    ``W[r, c] = G_c(d_r+1) - G_c(d_r)``: the share of source bin ``c``'s
    kernel mass that lands in destination bin ``r``. Apply it with
    ``splat.resample`` / ``splat.resample_ratio``, which accept any operator.
    Both edge arrays are cast to ``float64`` first; the result is ``float64``.
    """
    src = np.asarray(src_edges, dtype=np.float64)
    dst = np.asarray(dst_edges, dtype=np.float64)
    if kernel.name == KERNEL_GAUSSIAN:
        weights = _gaussian_operator(src, dst, float(kernel.sigma_mm))
    elif kernel.name == KERNEL_BILINEAR:
        weights = _tent_operator(src, dst)
    else:
        weights = overlap_matrix(src, dst)
    np.clip(weights, 0.0, None, out=weights)
    return weights
