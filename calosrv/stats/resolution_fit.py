"""Weighted least-squares fits of the energy resolution against 1/√E.

The Models page's ``res-scaling`` card plots, per momentum window, the
resolution ``r = σ/μ`` of the per-event response ratio against
``x = ⟨1/√p⟩`` and fits three forms to the windows (``query/
resolution_scaling.py`` chooses which windows):

* **affine**, ``r = a·x + b``: the stochastic term and a constant term added
  linearly, the form a linear-sum calorimeter is usually quoted in;
* **origin-pinned**, ``r = a₀·x``: a purely stochastic resolution, the line
  through the origin (E → ∞) of the reversed axis;
* **quadrature**, ``r² = A·x² + B``: the textbook ``a/√E ⊕ b``, fitted as a
  straight line in ``z = r²`` against ``u = x²``. On the 1/√E axis it is
  tabled, never drawn; the card's E view (σ/E against E in GeV) draws it where
  both terms are defined, ``A > 0`` and ``B > 0``.

**Closed forms, not a solver.** Each is a one- or two-parameter linear WLS
problem with weights ``w = 1/se²``. With ``S = Σw``, ``Sx = Σwx``,
``Sxx = Σwx²``, ``Sy = Σwy``, ``Sxy = Σwxy`` and ``Δ = S·Sxx − Sx²``:
``a = (S·Sxy − Sx·Sy)/Δ``, ``b = (Sxx·Sy − Sx·Sxy)/Δ``, ``Var a = S/Δ``,
``Var b = Sxx/Δ``, ``Cov(a, b) = −Sx/Δ``; pinned, ``a₀ = Sxy/Sxx`` and
``Var a₀ = 1/Sxx``. The tests hold them to ``numpy.linalg.lstsq`` on the
``√w``-scaled system.

**Weights from the model, iterated.** A window's standard error is the delta
method's ``se(r, N) = |r|·√(1/(2(N−1)) + r²/N)`` (``gaussian.fit_gaussian``'s
``resolution_error``). Taken at each window's *measured* r it is smaller for a
window that fluctuated low, which then pulls the line towards itself (the
Neyman-χ² bias). So the first fit uses the measured se, and every later one
recomputes se at the fitted model value ``ŷ(x_i)``, until the parameters move
by less than :data:`TOLERANCE` (at most :data:`MAX_ITERATIONS` refits). A
window where the model is not positive keeps its measured se: the delta-method
se of a non-positive resolution is not a weight. Once a refit reverses every
parameter's previous step the iteration is oscillating, and from then on it
takes half steps towards each refit (:data:`DAMPING`): the fixed point is the
same, and an oscillation settles instead of running to the limit. Measured on
2,000 seeded replicas of five windows at the fixtures' σ/E of about 87%, plain
refits left 142 of about 6,000 fits unconverged after 50; damped, one after 200.
A fit that still has not settled is reported as not converged, and the card
says so.

**Goodness of fit and the PDG scale factor.** ``χ² = Σ w (y − ŷ)²`` at the
final weights, ``ν = n − p`` and ``p = Q(ν/2, χ²/2)``, the upper tail of
χ²_ν through a hand-written regularised incomplete gamma (:func:`chi2_sf`;
scipy is not a dependency). When ``ν ≥ 1`` and ``χ²/ν > 1`` the reported
standard errors and the band are multiplied by ``S = √(χ²/ν)``, as the
Particle Data Group does for inconsistent measurements; the unscaled ones
travel beside them. ``ν = 0`` (two points, two parameters) is a line through
both points, with no test of fit and ``p = None``.

**The band** is the 95% confidence band of the fitted line,
``ŷ ± q·√(gᵀΣg)`` with ``g = (x, 1)`` (affine) or ``(x)`` (pinned) and ``Σ``
the scaled covariance: the uncertainty of the aggregate, never the spread of
the events. ``q`` is ``z₀.₉₇₅`` while the windows' own standard errors stand,
and Student's ``t₀.₉₇₅,ν`` once ``S`` scales them: the variance scale is then
estimated from the fit's own ν residual degrees of freedom, and the normal
quantile would understate the interval (12.71 against 1.96 at ν = 1, the
affine fit through three anchors). The quantile travels with the fit
(:attr:`Fit.band_quantile`).

**The quadrature band** is built in ``z``, where the fit is linear: with
``u = x²``, ``ẑ = A·u + B`` and ``g = (u, 1)`` the 95% band of ``z`` is
``ẑ ± q·√(gᵀΣg)``, and it is returned as ``(√max(ẑ, 0), √max(ẑ − h, 0),
√max(ẑ + h, 0))``. The interval of ``z`` is pointwise and ``√`` is monotone on
``z ≥ 0``, so this is the exact 95% band of ``√(A/E + B)``, with no delta
method; where ``ẑ − h < 0`` the lower edge is cut at zero, because a
resolution cannot be negative. At ``x = 0`` (E → ∞) it is ``√B``'s interval.

Pure NumPy. Every input and output here is a fraction (``r`` = 0.12, not
12 %); the query module converts to percent for the wire.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .gaussian import _Z_975, t_quantile_975

#: Most model-weight refits before a fit is reported as not converged.
MAX_ITERATIONS = 200

#: The step taken towards each refit once the iteration oscillates (a half step).
DAMPING = 0.5

#: A refit has converged when no parameter moves by more than this (relative to max(1, |θ|)).
TOLERANCE = 1e-10

#: Two-sided 95% normal quantile of the band while the windows' standard errors stand.
Z95 = _Z_975

FORM_AFFINE, FORM_PINNED, FORM_QUADRATURE = "affine", "pinned", "quadrature"

#: Fewest points each form needs (ν = 0 is allowed and said).
MIN_POINTS: dict[str, int] = {FORM_AFFINE: 2, FORM_PINNED: 1, FORM_QUADRATURE: 2}


# ------------------------------------------------------------ helpers --


def resolution_se(r, n):
    """Delta-method standard error of ``r = s/μ`` from ``n`` events: ``|r|·√(1/(2(n−1)) + r²/n)``.

    Works on scalars and arrays alike; ``n`` must be at least 2.
    """
    r = np.asarray(r, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    out = np.abs(r) * np.sqrt(1.0 / (2.0 * (n - 1.0)) + r * r / n)
    return float(out) if out.ndim == 0 else out


def _gamma_series(s: float, x: float) -> float:
    """The regularised lower incomplete gamma P(s, x) by its series (x < s + 1)."""
    term = total = 1.0 / s
    a = s
    for _ in range(10_000):
        a += 1.0
        term *= x / a
        total += term
        if abs(term) < abs(total) * 1e-16:
            break
    return total * math.exp(-x + s * math.log(x) - math.lgamma(s))


def _gamma_fraction(s: float, x: float) -> float:
    """The regularised upper incomplete gamma Q(s, x) by Lentz's continued fraction (x ≥ s + 1)."""
    tiny = 1e-300
    b = x + 1.0 - s
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h * math.exp(-x + s * math.log(x) - math.lgamma(s))


def chi2_sf(x: float, nu: int) -> float | None:
    """``P(χ²_ν > x)``: the regularised upper incomplete gamma ``Q(ν/2, x/2)``.

    ``None`` for ``ν < 1`` (no test exists); 1 for ``x ≤ 0``.
    """
    if nu is None or nu < 1 or x is None or not math.isfinite(x):
        return None
    if x <= 0.0:
        return 1.0
    s, half = 0.5 * nu, 0.5 * x
    if half < s + 1.0:
        return max(0.0, min(1.0, 1.0 - _gamma_series(s, half)))
    return max(0.0, min(1.0, _gamma_fraction(s, half)))


# --------------------------------------------------------- closed forms --


def wls_affine(x: np.ndarray, y: np.ndarray, w: np.ndarray
               ) -> tuple[np.ndarray, np.ndarray] | None:
    """``(a, b)`` of ``y = a·x + b`` and their covariance; ``None`` when the x are not distinct."""
    s, sx, sxx = w.sum(), (w * x).sum(), (w * x * x).sum()
    sy, sxy = (w * y).sum(), (w * x * y).sum()
    delta = s * sxx - sx * sx
    if not delta > 1e-14 * s * sxx:
        return None
    a = (s * sxy - sx * sy) / delta
    b = (sxx * sy - sx * sxy) / delta
    cov = np.array([[s / delta, -sx / delta], [-sx / delta, sxx / delta]])
    return np.array([a, b]), cov


def wls_pinned(x: np.ndarray, y: np.ndarray, w: np.ndarray
               ) -> tuple[np.ndarray, np.ndarray] | None:
    """``a₀`` of ``y = a₀·x`` and its variance; ``None`` when every x is zero."""
    sxx = (w * x * x).sum()
    if not sxx > 0.0:
        return None
    return np.array([(w * x * y).sum() / sxx]), np.array([[1.0 / sxx]])


# ---------------------------------------------------------------- fits --


@dataclass(frozen=True)
class Fit:
    """One fitted form. Parameters are fractions: affine ``(a, b)``, pinned ``(a₀,)``,
    quadrature ``(A, B)`` of ``r² = A·x² + B``."""

    form: str
    n_points: int
    theta: tuple[float, ...]
    cov_stat: np.ndarray           # the WLS covariance, before the scale factor
    chi2: float
    ndf: int
    p_value: float | None
    scale_factor: float
    iterations: int
    converged: bool

    @property
    def cov(self) -> np.ndarray:
        """The reported covariance: the WLS one times S²."""
        return self.cov_stat * self.scale_factor ** 2

    @property
    def se(self) -> tuple[float, ...]:
        return tuple(float(math.sqrt(max(v, 0.0))) for v in np.diag(self.cov))

    @property
    def se_stat(self) -> tuple[float, ...]:
        return tuple(float(math.sqrt(max(v, 0.0))) for v in np.diag(self.cov_stat))

    @property
    def rho(self) -> float | None:
        """Correlation of the two parameters (the scale factor cancels)."""
        if len(self.theta) != 2:
            return None
        va, vb = self.cov_stat[0, 0], self.cov_stat[1, 1]
        if not (va > 0 and vb > 0):
            return None
        return float(self.cov_stat[0, 1] / math.sqrt(va * vb))

    @property
    def band_quantile(self) -> float:
        """The band's multiplier: ``t₀.₉₇₅,ν`` once S scales the covariance, else ``z₀.₉₇₅``."""
        return t_quantile_975(self.ndf) if self.scale_factor > 1.0 else Z95

    def predict(self, x) -> np.ndarray:
        """The fitted resolution ``r(x)`` (for quadrature, √ of a non-negative ``r²``)."""
        x = np.asarray(x, dtype=np.float64)
        if self.form == FORM_AFFINE:
            return self.theta[0] * x + self.theta[1]
        if self.form == FORM_PINNED:
            return self.theta[0] * x
        return np.sqrt(np.maximum(self.theta[0] * x * x + self.theta[1], 0.0))


def _iterate(model: Callable[[np.ndarray], np.ndarray],
             solve: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray] | None],
             se_at: Callable[[np.ndarray], np.ndarray], se_measured: np.ndarray,
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, bool] | None:
    """Fit at the measured se, then refit with se at the model value until it settles.

    ``model(theta)`` gives the model value per point, ``solve(w)`` the WLS
    solution at weights ``w``, ``se_at(model value)`` the model-based se.
    Returns ``(theta, cov, w, iterations, converged)``; ``iterations`` counts
    the refits after the first. Convergence is judged on the full step to the
    refit; once a refit reverses every parameter's previous step, the
    parameters move :data:`DAMPING` of the way to each refit from then on.
    """
    w = 1.0 / se_measured ** 2
    solved = solve(w)
    if solved is None:
        return None
    theta, cov = solved
    step_before: np.ndarray | None = None
    rate = 1.0
    for iteration in range(1, MAX_ITERATIONS + 1):
        yhat = model(theta)
        positive = yhat > 0.0
        se = np.where(positive, se_at(np.where(positive, yhat, 1.0)), se_measured)
        w = 1.0 / se ** 2
        solved = solve(w)
        if solved is None:
            return None
        new, cov = solved
        step = new - theta
        if bool((np.abs(step) <= TOLERANCE * np.maximum(1.0, np.abs(theta))).all()):
            return new, cov, w, iteration, True
        if step_before is not None and bool((step * step_before < 0.0).all()):
            rate = DAMPING
        theta = theta + rate * step
        step_before = step
    # Unsettled: the last refit, whose parameters, covariance and weights belong together.
    return new, cov, w, MAX_ITERATIONS, False


def _finish(form: str, theta: np.ndarray, cov: np.ndarray, residual: np.ndarray,
            w: np.ndarray, iterations: int, converged: bool) -> Fit:
    n, p = residual.size, theta.size
    chi2 = float((w * residual ** 2).sum())
    ndf = n - p
    scale = math.sqrt(chi2 / ndf) if ndf >= 1 and chi2 / ndf > 1.0 else 1.0
    return Fit(form, int(n), tuple(float(t) for t in theta), cov, chi2, int(ndf),
               chi2_sf(chi2, ndf) if ndf >= 1 else None, float(scale), iterations, converged)


def _arrays(x, r, n) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    if not (x.shape == r.shape == n.shape) or x.ndim != 1:
        raise ValueError("x, r and n must be one-dimensional and of one length")
    se = np.asarray(resolution_se(r, n), dtype=np.float64).reshape(x.shape)
    if (n < 2).any() or not (se > 0).all():
        raise ValueError("every point needs N ≥ 2 and a positive standard error")
    return x, r, n, se


def fit_affine(x, r, n) -> Fit | None:
    """``r = a·x + b``; ``None`` below two points or with fewer than two distinct x."""
    if len(x) < MIN_POINTS[FORM_AFFINE]:
        return None
    x, r, n, se0 = _arrays(x, r, n)
    out = _iterate(lambda t: t[0] * x + t[1], lambda w: wls_affine(x, r, w),
                   lambda yhat: resolution_se(yhat, n), se0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_AFFINE, theta, cov, r - (theta[0] * x + theta[1]), w, iterations, converged)


def fit_pinned(x, r, n) -> Fit | None:
    """``r = a₀·x``; ``None`` without a point."""
    if len(x) < MIN_POINTS[FORM_PINNED]:
        return None
    x, r, n, se0 = _arrays(x, r, n)
    out = _iterate(lambda t: t[0] * x, lambda w: wls_pinned(x, r, w),
                   lambda yhat: resolution_se(yhat, n), se0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_PINNED, theta, cov, r - theta[0] * x, w, iterations, converged)


def fit_quadrature(x, r, n) -> Fit | None:
    """``r² = A·x² + B`` by WLS in ``z = r²`` against ``u = x²``, with ``se_z = 2ŷ·se(ŷ)``.

    The first fit takes ``se_z = 2r·se(r)`` at the measured r; later ones take
    it at the model's ``ŷ = √(A·x² + B)``, and a point where ``A·x² + B ≤ 0``
    keeps its measured se_z.
    """
    if len(x) < MIN_POINTS[FORM_QUADRATURE]:
        return None
    x, r, n, se0 = _arrays(x, r, n)
    u, z = x * x, r * r
    se_z0 = 2.0 * np.abs(r) * se0

    def se_z(zhat: np.ndarray) -> np.ndarray:
        yhat = np.sqrt(zhat)
        return 2.0 * yhat * resolution_se(yhat, n)

    out = _iterate(lambda t: t[0] * u + t[1], lambda w: wls_affine(u, z, w), se_z, se_z0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_QUADRATURE, theta, cov, z - (theta[0] * u + theta[1]), w, iterations,
                   converged)


@dataclass(frozen=True)
class QuadratureTerms:
    """``a = √A`` and ``b = √B`` with delta-method SEs; each undefined when its square is not positive."""

    a: float | None
    se_a: float | None
    se_a_stat: float | None
    b: float | None
    se_b: float | None
    se_b_stat: float | None
    a2: float
    se_a2: float
    se_a2_stat: float
    b2: float
    se_b2: float
    se_b2_stat: float
    a_defined: bool
    b_defined: bool


def quadrature_terms(fit: Fit) -> QuadratureTerms:
    """The quadrature fit's terms as a and b: ``se(√A) = se(A)/(2√A)``, likewise for B."""
    big_a, big_b = fit.theta
    (se_A, se_B), (se_A0, se_B0) = fit.se, fit.se_stat
    a = math.sqrt(big_a) if big_a > 0 else None
    b = math.sqrt(big_b) if big_b > 0 else None
    return QuadratureTerms(
        a=a, se_a=se_A / (2 * a) if a else None, se_a_stat=se_A0 / (2 * a) if a else None,
        b=b, se_b=se_B / (2 * b) if b else None, se_b_stat=se_B0 / (2 * b) if b else None,
        a2=big_a, se_a2=se_A, se_a2_stat=se_A0, b2=big_b, se_b2=se_B, se_b2_stat=se_B0,
        a_defined=a is not None, b_defined=b is not None,
    )


def band(fit: Fit, xs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(ŷ, lo, hi)`` on ``xs``: the fitted resolution and its 95% confidence band.

    The scaled covariance, at :attr:`Fit.band_quantile`: Student's t of the
    fit's ν once S scales it, the normal quantile otherwise. Affine and pinned
    are bands of a line in ``x``. Quadrature is the band of the line in
    ``z = r²`` against ``u = x²``, taken through ``√`` (the module docstring):
    ``(√max(ẑ, 0), √max(ẑ − h, 0), √max(ẑ + h, 0))``, the lower edge cut at 0
    where ``ẑ − h < 0``.
    """
    xs = np.asarray(xs, dtype=np.float64)
    q = fit.band_quantile
    if fit.form == FORM_QUADRATURE:
        u = xs * xs
        g = np.stack([u, np.ones_like(u)], axis=1)
        zhat = fit.theta[0] * u + fit.theta[1]
        half = q * np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", g, fit.cov, g), 0.0))
        return (np.sqrt(np.maximum(zhat, 0.0)), np.sqrt(np.maximum(zhat - half, 0.0)),
                np.sqrt(np.maximum(zhat + half, 0.0)))
    if fit.form == FORM_AFFINE:
        g = np.stack([xs, np.ones_like(xs)], axis=1)
    elif fit.form == FORM_PINNED:
        g = xs[:, None]
    else:
        raise ValueError(f"unknown fit form {fit.form!r}")
    yhat = fit.predict(xs)
    half = q * np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", g, fit.cov, g), 0.0))
    return yhat, yhat - half, yhat + half
