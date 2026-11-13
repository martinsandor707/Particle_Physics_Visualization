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
says so. The reversal is judged on the parameters that moved in both steps: a
term the noise form's constraint holds at 0 in both refits takes a step of
exactly 0, which can never reverse, and must not keep the damping off. The
other forms take an exactly zero step only at convergence, where the iteration
has already stopped, so their fits did not move by a bit.

**A relative weight law, κ** (the ``kappa`` argument of every fit; Martin's
decisions, 2026-11-12). The card's two non-sample estimators, the median
relative error ``median |R − 1|`` and the robust ``IQR(R)/(1.349·median R)``,
have no closed-form standard error that holds on these windows: R-stats
measured the bootstrap SE over the Gaussian large-N law at a median 1.37× for
the robust width and 1.06× for the median rel. on
``pion_hits_with_model_outputs`` (1.23× and 0.97× over every stored
experiment; windows of N ≥ 20, 2026-11-12; ``stats/robust_width.py``). A fit
given ``kappa``, one relative SE per point, takes ``se = κ·r`` for its first
fit and ``se = κ·ŷ`` at the fitted value for every refit; the quadrature fit
takes ``se_z = 2κ·ŷ²``. Everything else is the same code: the closed forms, the
iteration and its damping, χ², S, the band, the misfit gate. ``kappa=None``
runs the delta-method law exactly as before, so the sample estimator's fits did
not move by a bit.

**What κ must not be.** ``kappa`` takes any array, and the card passes
``κₖ = c/√Nₖ`` with ``c`` its series' pooled scale, the median of ``√N·κ``
over the series' fittable windows (``query/resolution_scaling.py``). It must not
be each window's own measured ``SEₖ/valueₖ``: the refit weight would be
``1/(SEₖ·ŷₖ/valueₖ)²``, which still holds the window's measured value, now in
the numerator, so a window that fluctuated high is up-weighted. That is a bias
opposite to Neyman's and larger, not a protection against it: R-stats' Monte
Carlo of the served code paths (2026-11-12; 16 windows, true σ/E = 30%/√E,
Gaussian R) put the origin-pinned term +0.70 (median rel.) and +0.77 (robust)
of its SD high at 40 events a window, +0.35 and +0.33 at 200, +0.15 and +0.17
at 1,000, against 0.00 within Monte Carlo error under the pooled scale. A common
``c`` cancels in the fitted parameters (scaling every weight by one constant
leaves the WLS solution unchanged) and sets only χ², S and the parameters'
errors.

**Goodness of fit and the PDG scale factor.** ``χ² = Σ w (y − ŷ)²`` at the
final weights, ``ν = n − p`` and ``p = Q(ν/2, χ²/2)``, the upper tail of
χ²_ν through a hand-written regularised incomplete gamma (:func:`chi2_sf`;
scipy is not a dependency). When ``ν ≥ 1`` and ``χ²/ν > 1`` the reported
standard errors and the band are multiplied by ``S = √(χ²/ν)``, as the
Particle Data Group does for inconsistent measurements; the unscaled ones
travel beside them. ``ν = 0`` (two points, two parameters) is a line through
both points, with no test of fit and ``p = None``.

**A form that does not describe its windows** (:attr:`Fit.misfit`,
:data:`MISFIT_SCALE`). ``S = √(χ²/ν)`` is the RMS of the residuals in units of
the windows' own standard errors. Where ``ν ≥ 1`` and ``S > 5`` they average
more than five of those errors: the form does not describe the windows,
whatever its parameters' errors say, and the card draws the fit faded and
never lets it set a range. The p-value cannot make that call. A window holds
hundreds to thousands of events, so its standard error is small and the χ²
test rejects a form for a misfit no reader could see: measured on the five
stored experiments (2026-11-11), 71 of the 84 fits with ``ν ≥ 1`` have
``p < 0.05``, every fit of the all-windows mode among them. What separates a
form that does not describe its windows is how large its misfit is. The
calibrated deposit's origin-pinned fits have S = 5.5–28.6
(χ²/ν 31–818): a deposit's σ/E is mostly a constant term, which ``a₀·x``
cannot hold. The quadrature and affine fits through the same windows have
S = 1.1–4.7. At ``S > 5`` the gate flags 21 of the 28 pinned fits with
``ν ≥ 1`` and 4 of the 56 quadrature and affine ones; at ``S > 3`` it would
flag 23 of those 56, which is why the threshold is 5. ``ν = 0`` has no test,
and is never a misfit.

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

**The noise form** (:data:`FORM_NOISE`; Martin's decisions, 2026-11-13). The
card's E view draws ``r = a/√E ⊕ b ⊕ c/E``, the textbook form with the noise
term c/E, fitted as ``z = r² = A·u + B + C·u²`` with ``u = x² = 1/E`` and
``A = a²``, ``B = b²``, ``C = c²``. It is linear in ``(A, B, C)``, so the
weights, their iteration, χ², S and the misfit gate are the quadrature fit's:
``se_z = 2ŷ·se(ŷ)``, measured at the first fit and at ``ŷ = √ẑ`` after.

*Why the constraint.* Fitted without it, a square comes out negative and its
term is not real on most series. Measured by the lead on 2026-11-13 on the
eight stored experiments, Absolute frame, through every window of N ≥ 20 from
1 GeV with the served weights (``data/dev/design/res-noise/scratch/
noise_feasibility.out`` and ``noise_nnls.out``): all three terms are real on
only 0–1 of the 8 network series per estimator and on 3–6 of the 12 deposit
series; the networks want ``a² < 0``. So the fit holds ``A, B, C ≥ 0``, and a
term the constraint holds at 0 is named. Constrained, it often lands on that
boundary: the networks usually hold b = 0 or a = 0, the deposits sometimes
c = 0.

*The face enumeration* (:func:`wls_noise`). At fixed weights the problem is
convex, a weighted non-negative least squares in three unknowns. Its optimum
frees some set F of the terms and holds the rest at 0, and on F it is the
unconstrained weighted fit of that face. So every one of the seven non-empty
faces of {A, B, C} is solved by its own normal equations (a face whose
equilibrated normal matrix has a condition number above :data:`COND_LIMIT` is
skipped), a face solution is feasible when every term it frees is positive, and
the feasible solution of the smallest weighted SSR is the constrained optimum:
exact, with no iteration. One tolerance only separates faces whose SSRs differ
by rounding (:data:`NOISE_TIE_RTOL` of ``Σwz²``): such a tie goes to the face
with fewer free terms, since the term the other adds is not estimated by the
windows. It arises where a form with fewer terms passes through the windows
exactly: the XGBoost test fixture's deposit has one robust value in every
window, and without it the (B, C) face beat B alone by rounding and served
c = 3·10⁻⁶ %·GeV with an SE of 2·10¹⁰ %·GeV. A single-term face is always
feasible, since every ``z > 0``, so a solution always exists. The held terms are
exact zeros, and the covariance is that face's inverse normal matrix at its free
indices and zero elsewhere. Each refit of :func:`_iterate` re-enumerates, so a
term may be held at one weighting and freed at the next; the last refit's face
is the fit's.

*ν over the free terms.* ``ν = n − |F|``: a held term is not estimated, so it
spends no degree of freedom. Three windows fitted by three free terms pass
through their points (ν = 0, no χ² test), as two windows do for a two-term form.

*The conditional band.* ``ẑ ± q·√(gᵀΣg)`` with ``g = (u, 1, u²)``, taken
through ``√`` as the quadrature band is. ``Σ`` is zero on the held rows and
columns, so the band is conditional on the held terms being 0: it carries the
free terms' uncertainty, not the chance that a held term is in fact positive.
The card says so wherever a term is held.

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

#: A fit with ν ≥ 1 whose scale factor S = √(χ²/ν) exceeds this does not describe its windows:
#: its residuals average more than this many of the windows' own standard errors (RMS), so it is
#: drawn faded and never sets a range. The size of the misfit, not the χ² p-value, which rejects
#: almost every fit at the stored experiments' hundreds to thousands of events per window (the
#: module docstring has the measurement behind the 5).
MISFIT_SCALE = 5.0

FORM_AFFINE, FORM_PINNED, FORM_QUADRATURE = "affine", "pinned", "quadrature"
#: σ/E = a/√E ⊕ b ⊕ c/E, fitted as r² = A·u + B + C·u² with A, B, C ≥ 0 (the module docstring).
FORM_NOISE = "noise"

#: Fewest points each form needs (ν = 0 is allowed and said): as many windows as terms.
MIN_POINTS: dict[str, int] = {FORM_AFFINE: 2, FORM_PINNED: 1, FORM_QUADRATURE: 2, FORM_NOISE: 3}

#: The noise form's terms, in the order of ``Fit.theta``: A = a², B = b², C = c².
NOISE_TERMS: tuple[str, ...] = ("a", "b", "c")

#: The seven non-empty faces of {A, B, C} :func:`wls_noise` solves, in this order.
NOISE_FACES: tuple[tuple[int, ...], ...] = ((0, 1, 2), (0, 1), (0, 2), (1, 2), (0,), (1,), (2,))

#: A face whose normal matrix, equilibrated to a unit diagonal, has a condition number above this
#: is singular and skipped. The affine solver's ``Δ > 10⁻¹⁴·S·Sxx`` asks the like of two columns:
#: ``1 − ρ² > 10⁻¹⁴`` of the equilibrated matrix, a condition number below about 4·10¹⁴.
COND_LIMIT = 1e14

#: Two feasible faces whose weighted SSRs differ by less than this share of ``Σwz²`` (the SSR at
#: θ = 0) tie, and the face with fewer free terms takes the tie: the term the other adds moves the
#: SSR by rounding alone, so the windows do not estimate it.
NOISE_TIE_RTOL = 1e-12


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


def _noise_basis(u: np.ndarray) -> np.ndarray:
    """The design of ``z = A·u + B + C·u²``: the columns ``(u, 1, u²)``."""
    return np.stack([u, np.ones_like(u), u * u], axis=1)


def _solve_face(design: np.ndarray, z: np.ndarray, w: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray] | None:
    """One face's weighted normal equations: ``(θ_F, (XᵀWX)⁻¹)``, or ``None`` when singular.

    Singular means a normal matrix whose equilibrated form (unit diagonal) has
    a condition number above :data:`COND_LIMIT`, or a column with no weight.
    """
    normal = design.T @ (design * w[:, None])
    diag = np.diag(normal)
    if not (np.isfinite(normal).all() and (diag > 0.0).all()):
        return None
    scale = 1.0 / np.sqrt(diag)
    if np.linalg.cond(normal * np.outer(scale, scale)) > COND_LIMIT:
        return None
    cov = np.linalg.inv(normal)
    return cov @ (design.T @ (w * z)), cov


def wls_noise(u: np.ndarray, z: np.ndarray, w: np.ndarray
              ) -> tuple[np.ndarray, np.ndarray] | None:
    """``(A, B, C)`` of ``z = A·u + B + C·u²`` with every term ≥ 0, and their 3 × 3 covariance.

    Exact weighted non-negative least squares at fixed weights, by the face
    enumeration of the module docstring: each face of :data:`NOISE_FACES` is
    solved, a face whose free terms are all positive is feasible, and the
    feasible face of the smallest weighted SSR wins. Faces within
    :data:`NOISE_TIE_RTOL` of ``Σwz²`` of that SSR tie, and the tie goes to the
    fewest free terms, then the smaller SSR, then the order above. The held
    terms are exact zeros, and the covariance holds the winning face's inverse
    normal matrix at its free indices and zeros on the held rows and columns.
    ``None`` only when no face is feasible, which ``z > 0`` with a positive
    weight rules out.
    """
    basis = _noise_basis(u)
    feasible: list[tuple[float, tuple[int, ...], np.ndarray, np.ndarray]] = []
    for face in NOISE_FACES:
        design = basis[:, face]
        solved = _solve_face(design, z, w)
        if solved is None:
            continue
        theta_face, cov_face = solved
        if not bool((theta_face > 0.0).all()):
            continue
        feasible.append((float((w * (z - design @ theta_face) ** 2).sum()), face, theta_face,
                         cov_face))
    if not feasible:
        return None
    least = min(item[0] for item in feasible)
    tie = least + NOISE_TIE_RTOL * float((w * z * z).sum())
    # min() keeps the first of equal keys, so exact ties fall to the order of NOISE_FACES.
    _, face, theta_face, cov_face = min((item for item in feasible if item[0] <= tie),
                                        key=lambda item: (len(item[1]), item[0]))
    theta = np.zeros(3)
    cov = np.zeros((3, 3))
    index = list(face)
    theta[index] = theta_face
    cov[np.ix_(index, index)] = cov_face
    return theta, cov


# ---------------------------------------------------------------- fits --


@dataclass(frozen=True)
class Fit:
    """One fitted form. Parameters are fractions: affine ``(a, b)``, pinned ``(a₀,)``,
    quadrature ``(A, B)`` of ``r² = A·x² + B``, noise ``(A, B, C)`` of
    ``r² = A·x² + B + C·x⁴``, each ≥ 0 and exactly 0 where the constraint holds it."""

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

    @property
    def misfit(self) -> bool:
        """The form does not describe its windows: ``ν ≥ 1`` and ``S > MISFIT_SCALE``.

        S is the RMS of the residuals in units of the windows' own standard
        errors. ``ν = 0`` passes through its points and has no test, so it is
        never a misfit.
        """
        return self.ndf >= 1 and self.scale_factor > MISFIT_SCALE

    @property
    def held(self) -> tuple[str, ...]:
        """The noise form's terms the constraint holds at 0, in the order a, b, c; ``()`` otherwise."""
        if self.form != FORM_NOISE:
            return ()
        return tuple(name for name, value in zip(NOISE_TERMS, self.theta) if value == 0.0)

    @property
    def n_free(self) -> int:
        """The parameters the fit estimated: every one, but the noise form's held terms."""
        return len(self.theta) - len(self.held)

    def predict(self, x) -> np.ndarray:
        """The fitted resolution ``r(x)`` (for quadrature and noise, √ of a non-negative ``r²``)."""
        x = np.asarray(x, dtype=np.float64)
        if self.form == FORM_AFFINE:
            return self.theta[0] * x + self.theta[1]
        if self.form == FORM_PINNED:
            return self.theta[0] * x
        if self.form == FORM_NOISE:
            u = x * x
            return np.sqrt(np.maximum(self.theta[0] * u + self.theta[1] + self.theta[2] * u * u,
                                      0.0))
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
    refit; once a refit reverses the previous step of every parameter that
    moved in both, the parameters move :data:`DAMPING` of the way to each refit
    from then on. A parameter whose step is exactly 0 in either (a noise term
    held at 0) has no direction to reverse and is left out of that judgement;
    when no parameter moved in both, nothing has reversed.
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
        if step_before is not None:
            moved = (step != 0.0) & (step_before != 0.0)
            if bool(moved.any()) and bool((step[moved] * step_before[moved] < 0.0).all()):
                rate = DAMPING
        theta = theta + rate * step
        step_before = step
    # Unsettled: the last refit, whose parameters, covariance and weights belong together.
    return new, cov, w, MAX_ITERATIONS, False


def _finish(form: str, theta: np.ndarray, cov: np.ndarray, residual: np.ndarray,
            w: np.ndarray, iterations: int, converged: bool, free: int | None = None) -> Fit:
    """The fit at its final weights: χ², ``ν = n − p`` and S.

    ``p`` is ``free``, the parameters estimated, where given (the noise form's
    free terms: a held term spends no degree of freedom), else every parameter.
    """
    n, p = residual.size, (theta.size if free is None else free)
    chi2 = float((w * residual ** 2).sum())
    ndf = n - p
    scale = math.sqrt(chi2 / ndf) if ndf >= 1 and chi2 / ndf > 1.0 else 1.0
    return Fit(form, int(n), tuple(float(t) for t in theta), cov, chi2, int(ndf),
               chi2_sf(chi2, ndf) if ndf >= 1 else None, float(scale), iterations, converged)


def _arrays(x, r, n, kappa=None
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """The points as float arrays, their measured se, and κ (``None`` for the delta-method law).

    With ``kappa`` the first fit's se is ``κ·|r|`` (the card passes ``κ = c/√N``,
    the module docstring).
    """
    x = np.asarray(x, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    if not (x.shape == r.shape == n.shape) or x.ndim != 1:
        raise ValueError("x, r and n must be one-dimensional and of one length")
    if kappa is None:
        se = np.asarray(resolution_se(r, n), dtype=np.float64).reshape(x.shape)
    else:
        kappa = np.asarray(kappa, dtype=np.float64)
        if kappa.shape != x.shape:
            raise ValueError("kappa must be aligned with x")
        if not (np.isfinite(kappa).all() and (kappa > 0).all()):
            raise ValueError("every κ must be finite and positive")
        se = kappa * np.abs(r)
    if (n < 2).any() or not (se > 0).all():
        raise ValueError("every point needs N ≥ 2 and a positive standard error")
    return x, r, n, se, kappa


def _se_law(n: np.ndarray, kappa: np.ndarray | None) -> Callable[[np.ndarray], np.ndarray]:
    """se at a model value ŷ: the delta-method ``resolution_se(ŷ, n)``, or ``κ·ŷ``."""
    if kappa is None:
        return lambda yhat: resolution_se(yhat, n)
    return lambda yhat: kappa * yhat


def fit_affine(x, r, n, kappa=None) -> Fit | None:
    """``r = a·x + b``; ``None`` below two points or with fewer than two distinct x.

    ``kappa``: each point's relative SE, for the κ law (the module docstring:
    a pooled ``c/√N``, never a window's own measured SE/value); ``None``, the
    delta-method law.
    """
    if len(x) < MIN_POINTS[FORM_AFFINE]:
        return None
    x, r, n, se0, kappa = _arrays(x, r, n, kappa)
    out = _iterate(lambda t: t[0] * x + t[1], lambda w: wls_affine(x, r, w),
                   _se_law(n, kappa), se0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_AFFINE, theta, cov, r - (theta[0] * x + theta[1]), w, iterations, converged)


def fit_pinned(x, r, n, kappa=None) -> Fit | None:
    """``r = a₀·x``; ``None`` without a point. ``kappa`` as :func:`fit_affine`'s."""
    if len(x) < MIN_POINTS[FORM_PINNED]:
        return None
    x, r, n, se0, kappa = _arrays(x, r, n, kappa)
    out = _iterate(lambda t: t[0] * x, lambda w: wls_pinned(x, r, w), _se_law(n, kappa), se0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_PINNED, theta, cov, r - theta[0] * x, w, iterations, converged)


def fit_quadrature(x, r, n, kappa=None) -> Fit | None:
    """``r² = A·x² + B`` by WLS in ``z = r²`` against ``u = x²``, with ``se_z = 2ŷ·se(ŷ)``.

    The first fit takes ``se_z = 2r·se(r)`` at the measured r; later ones take
    it at the model's ``ŷ = √(A·x² + B)``, and a point where ``A·x² + B ≤ 0``
    keeps its measured se_z. Under the κ law (``kappa`` as :func:`fit_affine`'s)
    se(ŷ) = κ·ŷ, so ``se_z = 2κ·ŷ²``.
    """
    if len(x) < MIN_POINTS[FORM_QUADRATURE]:
        return None
    x, r, n, se0, kappa = _arrays(x, r, n, kappa)
    u, z = x * x, r * r
    se_z0 = 2.0 * np.abs(r) * se0
    law = _se_law(n, kappa)

    def se_z(zhat: np.ndarray) -> np.ndarray:
        yhat = np.sqrt(zhat)
        return 2.0 * yhat * law(yhat)

    out = _iterate(lambda t: t[0] * u + t[1], lambda w: wls_affine(u, z, w), se_z, se_z0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_QUADRATURE, theta, cov, z - (theta[0] * u + theta[1]), w, iterations,
                   converged)


def fit_noise(x, r, n, kappa=None) -> Fit | None:
    """``r² = A·x² + B + C·x⁴`` with ``A, B, C ≥ 0``: σ/E = a/√E ⊕ b ⊕ c/E; ``None`` below three points.

    As :func:`fit_quadrature`, in ``z = r²`` against ``u = x²``: the first fit
    takes ``se_z = 2r·se(r)`` at the measured r, later ones ``se_z = 2ŷ·se(ŷ)`` at
    ``ŷ = √ẑ`` (``2κ·ŷ²`` under the κ law; ``kappa`` as :func:`fit_affine`'s),
    each solved by :func:`wls_noise`. The final θ is the last refit's, so a held
    term is exactly 0, and ``ν = n −`` the free terms (the module docstring).
    """
    if len(x) < MIN_POINTS[FORM_NOISE]:
        return None
    x, r, n, se0, kappa = _arrays(x, r, n, kappa)
    u, z = x * x, r * r
    se_z0 = 2.0 * np.abs(r) * se0
    law = _se_law(n, kappa)

    def se_z(zhat: np.ndarray) -> np.ndarray:
        yhat = np.sqrt(zhat)
        return 2.0 * yhat * law(yhat)

    def model(t: np.ndarray) -> np.ndarray:
        return t[0] * u + t[1] + t[2] * u * u

    out = _iterate(model, lambda w: wls_noise(u, z, w), se_z, se_z0)
    if out is None:
        return None
    theta, cov, w, iterations, converged = out
    return _finish(FORM_NOISE, theta, cov, z - model(theta), w, iterations, converged,
                   free=int(np.count_nonzero(theta)))


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


@dataclass(frozen=True)
class NoiseTerms:
    """The noise fit's terms: ``a = √A``, ``b = √B``, ``c = √C`` with delta-method SEs.

    A held term is 0 with no SE (``None``): it was not estimated. ``rho`` holds
    the correlations ``a2b2``, ``a2c2`` and ``b2c2`` of the squares, from the
    unscaled covariance (S cancels in them), each ``None`` when either term is
    held. SEs are the scaled ones (``Fit.se``).
    """

    a: float
    b: float
    c: float
    se_a: float | None
    se_b: float | None
    se_c: float | None
    a2: float
    b2: float
    c2: float
    se_a2: float | None
    se_b2: float | None
    se_c2: float | None
    held: tuple[str, ...]
    rho: dict[str, float | None]


def noise_terms(fit: Fit) -> NoiseTerms:
    """The noise fit's a, b and c: ``se(√A) = se(A)/(2√A)``, likewise for B and C; ``None`` when held."""
    if fit.form != FORM_NOISE:
        raise ValueError(f"noise_terms needs a {FORM_NOISE!r} fit, got {fit.form!r}")
    held = fit.held
    free = [name not in held for name in NOISE_TERMS]
    squares = [float(v) for v in fit.theta]
    roots = [math.sqrt(v) if ok else 0.0 for v, ok in zip(squares, free)]
    se_sq = [se if ok else None for se, ok in zip(fit.se, free)]
    se_root = [None if s is None else s / (2.0 * root) for s, root in zip(se_sq, roots)]
    var = np.diag(fit.cov_stat)

    def rho(i: int, j: int) -> float | None:
        if not (free[i] and free[j] and var[i] > 0 and var[j] > 0):
            return None
        return float(fit.cov_stat[i, j] / math.sqrt(var[i] * var[j]))

    return NoiseTerms(
        a=roots[0], b=roots[1], c=roots[2], se_a=se_root[0], se_b=se_root[1], se_c=se_root[2],
        a2=squares[0], b2=squares[1], c2=squares[2],
        se_a2=se_sq[0], se_b2=se_sq[1], se_c2=se_sq[2], held=held,
        rho={"a2b2": rho(0, 1), "a2c2": rho(0, 2), "b2c2": rho(1, 2)},
    )


def band(fit: Fit, xs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(ŷ, lo, hi)`` on ``xs``: the fitted resolution and its 95% confidence band.

    The scaled covariance, at :attr:`Fit.band_quantile`: Student's t of the
    fit's ν once S scales it, the normal quantile otherwise. Affine and pinned
    are bands of a line in ``x``. Quadrature is the band of the line in
    ``z = r²`` against ``u = x²``, taken through ``√`` (the module docstring):
    ``(√max(ẑ, 0), √max(ẑ − h, 0), √max(ẑ + h, 0))``, the lower edge cut at 0
    where ``ẑ − h < 0``. Noise is the same in ``z = A·u + B + C·u²`` with
    ``g = (u, 1, u²)``; its covariance is zero on the held rows, so its band is
    conditional on the held terms.
    """
    xs = np.asarray(xs, dtype=np.float64)
    q = fit.band_quantile
    if fit.form in (FORM_QUADRATURE, FORM_NOISE):
        u = xs * xs
        if fit.form == FORM_NOISE:
            g = _noise_basis(u)
            zhat = fit.theta[0] * u + fit.theta[1] + fit.theta[2] * u * u
        else:
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
