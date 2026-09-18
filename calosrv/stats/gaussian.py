"""Gaussian description of a reconstructed-energy spectrum.

**Reported numbers and drawn marks are gated separately.** A table cell makes no
claim about the *shape* of a distribution - it states two moments and their
uncertainty - so it can be filled from far fewer events than a smooth density
curve, which reads as a measured distribution whether or not the sample supports
one. Conflating the two is what produced the panel this module was rewritten
for: a slice of fourteen events reported nothing at all, not because its mean
and width were unknowable but because its *histogram* would have been an
artefact. See the threshold table below; each floor is justified on its own
terms and none of them is a proxy for another.

**The estimator is moment-based, and that is a deliberate commitment rather than
a shortcut.** Switching to a least-squares fit against a histogram would make
every quoted width depend on the bin count and - because the spectrum has a
genuine low-side containment-leakage tail - return a number describing neither
the core nor the tail.

*The width is the unbiased sample standard deviation,* ``ddof = 1``. The
population form understates sigma by ``sqrt(1 - 1/N)``: 18% at N = 3, 6% at
N = 8, 0.3% at N = 200. The divergence is confined to exactly the regime this
module now reports on, so continuity with the large-N figures already published
is preserved while the small slices stop being quietly optimistic.
``sigma_population`` (``ddof = 0``) is computed alongside and shipped, so the
bit-identical comparison with ``calodash/stats.py`` and the reference notebook
remains available; ``calodash/stats.py`` quotes the same ``ddof = 1`` width.

*The iterated core fit.* Re-taking the moments inside ``mu +/- 2.5 sigma`` is the
standard calorimetric response measurement. It is still pure moments - no
solver, no initial guess - and it separates the Gaussian core resolution from
the non-Gaussian tail, which the shipped histogram still shows. It needs a
populated tail to cut, so it is gated at :data:`MIN_CORE_SAMPLES` and its
de-biasing correction is applied only when it actually truncated something.

*A robustness flag.* The interquartile width divided by 1.349 estimates sigma for
a true Gaussian. When it disagrees with the moment sigma by more than
:data:`NON_GAUSSIAN_TOLERANCE`, the distribution is not Gaussian and the panel
says so rather than drawing a curve that misrepresents it. Below
:data:`MIN_ROBUST_SAMPLES` the verdict is ``None`` rather than ``False``:
``np.percentile`` on a handful of points interpolates between individual events,
so the flag would fire or stay silent at random, and a reassuring "Gaussian" is
worse than an admission that nothing was tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

#: Degrees-of-freedom correction for every width this module quotes.
DDOF = 1

#: Fewest events for which mu, sigma and sigma/mu are *reported as numbers*.
#:
#: At N = 2 the sample standard deviation is a single pairwise difference with
#: one degree of freedom. That is a weak estimate, not an undefined one, and the
#: panel says which it is rather than printing an em-dash: a reader can discount
#: a number that arrives labelled "1 d.o.f.", but cannot do anything at all with
#: a dash. Below this the width genuinely does not exist.
MIN_MOMENT_SAMPLES = 2

#: Fewest events for which a continuous parametric density *curve* is drawn.
#:
#: A smooth curve is read as a measured distribution, so it must not be drawn
#: from a sample whose shape is unconstrained. Three points fix a mean and a
#: width but say nothing about whether the underlying density is Gaussian, and
#: the curve would be an assumption imported from the high-N slices wearing the
#: appearance of a measurement. Eight is the point at which the width is
#: determined to better than a factor of two either way.
MIN_CURVE_SAMPLES = 8

#: Fewest events for the iterated core refit. See :func:`core_refit`.
MIN_CORE_SAMPLES = 15

#: Fewest events for the robust width and the Gaussian-shape verdict.
MIN_ROBUST_SAMPLES = 20

#: Half-width of the core refit window, in units of the current sigma.
CORE_SIGMA = 2.5

#: Iteration cap for the core refit. The loop exits early on convergence.
CORE_ITERATIONS = 16

#: Truncation de-biasing constant for the iterated core fit.
#:
#: Discarding everything beyond +/- 2.5 sigma removes real variance, so the
#: refitted width *underestimates* the width of a true Gaussian - and because
#: the window is recomputed from the shrinking sigma, the iteration converges to
#: a fixed point rather than to the right answer. Left uncorrected it reports a
#: width about 6.3% low, which on an energy-resolution figure is a material
#: misstatement.
#:
#: The variance of a Gaussian truncated symmetrically at +/- a sigma is
#: ``sigma^2 * f(a)`` with ``f(a) = 1 - 2a*phi(a) / (2*Phi(a) - 1)``. At the
#: iteration's fixed point the window sits at +/- 2.5 of the *measured* width,
#: so ``k = sigma_measured / sigma_true`` solves ``k = sqrt(f(2.5k))``, giving
#: k = 0.9365574. A 40 x 200000-sample Monte Carlo of the same iteration
#: converges to 0.936856 +/- 0.0018, confirming the constant; dividing by it
#: recovers a true sigma of 2.0 as 2.0006.
#:
#: It corrects for truncation, so it is applied **only when the refit actually
#: truncated something**. Applying it to an untruncated sample inflates the
#: quoted width by 6.77% to correct for a cut that never happened.
CORE_TRUNCATION_FACTOR = 0.9365574133

#: Relative disagreement between the moment sigma and the robust sigma above
#: which the sample is flagged as non-Gaussian.
NON_GAUSSIAN_TOLERANCE = 0.15

#: sigma = IQR / 1.349 for a Gaussian.
IQR_TO_SIGMA = 1.349

#: Two-sided 95% Student-t quantiles, ``t_{0.975, nu}``, for nu = 1..30.
#:
#: scipy is not a dependency, and the normal approximation cannot stand in: at
#: nu = 2 the true quantile is 4.303 against 1.96, so a naive interval would
#: understate the uncertainty on the mean by a factor of 2.2 in exactly the
#: regime where it is being quoted for the first time.
_T_975: dict[int, float] = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}

#: ``chi2_{0.975, nu}`` for nu = 1..30 - the *upper* tail point.
_CHI2_975: dict[int, float] = {
    1: 5.024, 2: 7.378, 3: 9.348, 4: 11.143, 5: 12.833,
    6: 14.449, 7: 16.013, 8: 17.535, 9: 19.023, 10: 20.483,
    11: 21.920, 12: 23.337, 13: 24.736, 14: 26.119, 15: 27.488,
    16: 28.845, 17: 30.191, 18: 31.526, 19: 32.852, 20: 34.170,
    21: 35.479, 22: 36.781, 23: 38.076, 24: 39.364, 25: 40.646,
    26: 41.923, 27: 43.195, 28: 44.461, 29: 45.722, 30: 46.979,
}

#: ``chi2_{0.025, nu}`` for nu = 1..30 - the *lower* tail point.
_CHI2_025: dict[int, float] = {
    1: 0.000982, 2: 0.0506, 3: 0.216, 4: 0.484, 5: 0.831,
    6: 1.237, 7: 1.690, 8: 2.180, 9: 2.700, 10: 3.247,
    11: 3.816, 12: 4.404, 13: 5.009, 14: 5.629, 15: 6.262,
    16: 6.908, 17: 7.564, 18: 8.231, 19: 8.907, 20: 9.591,
    21: 10.283, 22: 10.982, 23: 11.689, 24: 12.401, 25: 13.120,
    26: 13.844, 27: 14.573, 28: 15.308, 29: 16.047, 30: 16.791,
}

#: Standard normal 97.5% point, for the nu > 30 asymptotes.
_Z_975 = 1.959963985


def t_quantile_975(df: int) -> float:
    """``t_{0.975, df}``, tabulated to df = 30 and asymptotic beyond."""
    if df < 1:
        return float("nan")
    if df in _T_975:
        return _T_975[df]
    # Cornish-Fisher expansion; within 0.1% of the true quantile for df > 30.
    z = _Z_975
    return z + (z ** 3 + z) / (4.0 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (
        96.0 * df * df
    )


def chi2_quantile(df: int, upper: bool) -> float:
    """``chi2_{0.975, df}`` when ``upper``, else ``chi2_{0.025, df}``."""
    if df < 1:
        return float("nan")
    table = _CHI2_975 if upper else _CHI2_025
    if df in table:
        return table[df]
    # Wilson-Hilferty: chi2_p(df) ~ df * (1 - 2/(9df) + z_p*sqrt(2/(9df)))^3.
    z = _Z_975 if upper else -_Z_975
    a = 2.0 / (9.0 * df)
    return df * (1.0 - a + z * math.sqrt(a)) ** 3


def c4(n: int) -> float:
    """``E[s] / sigma`` for a Gaussian sample of size ``n``.

    ``ddof = 1`` makes the *variance* unbiased, not the standard deviation:
    taking a square root is a concave operation, so ``s`` still underestimates
    sigma by 11.4% at N = 3 and 6.0% at N = 5. The factor is reported so the
    residual bias is visible rather than folded silently into the quoted width.
    """
    if n < 2:
        return float("nan")
    return math.sqrt(2.0 / (n - 1)) * math.exp(
        math.lgamma(n / 2.0) - math.lgamma((n - 1) / 2.0)
    )


@dataclass
class CoreRefit:
    """Outcome of the iterated ``mu +/- CORE_SIGMA * sigma`` refit."""

    mu: float
    sigma: float
    n: int
    iterations: int
    #: Whether any event was actually excluded by the window.
    truncated: bool
    #: Whether the refit ran at all and its result should be quoted.
    applied: bool


def core_refit(values: np.ndarray, mu: float, sigma: float) -> CoreRefit:
    """Re-take the moments inside ``mu +/- CORE_SIGMA * sigma``, iterated.

    Returns ``applied = False`` - and the untouched input moments - whenever the
    sample is too small, has no width, or the window never validated a core. The
    de-biasing factor is applied only when the final window genuinely cut
    events; see :data:`CORE_TRUNCATION_FACTOR`.
    """
    n = int(values.size)
    if n < MIN_CORE_SAMPLES or not sigma > 0:
        return CoreRefit(mu=mu, sigma=sigma, n=n, iterations=0,
                         truncated=False, applied=False)

    window = sigma
    core_mu = mu
    core_n = n
    iterations = 0
    for _ in range(CORE_ITERATIONS):
        lo = core_mu - CORE_SIGMA * window
        hi = core_mu + CORE_SIGMA * window
        core = values[(values >= lo) & (values <= hi)]
        if core.size < MIN_CORE_SAMPLES:
            break
        new_sigma = float(core.std(ddof=DDOF))
        if not new_sigma > 0:
            break
        converged = abs(new_sigma - window) <= 1e-7 * max(window, 1e-12)
        core_mu = float(core.mean())
        window = new_sigma
        core_n = int(core.size)
        iterations += 1
        if converged:
            break

    if iterations == 0:
        return CoreRefit(mu=mu, sigma=sigma, n=n, iterations=0,
                         truncated=False, applied=False)

    truncated = core_n < n
    core_sigma = window / CORE_TRUNCATION_FACTOR if truncated else window
    return CoreRefit(mu=core_mu, sigma=core_sigma, n=core_n,
                     iterations=iterations, truncated=truncated, applied=True)


@dataclass
class GaussianFit:
    """Moment description of one sample, with the uncertainty on each moment."""

    n: int
    mu: float | None = None
    #: Unbiased sample standard deviation, ``ddof = 1``. The quoted width.
    sigma: float | None = None
    #: Population form, ``ddof = 0``, for comparison with the notebook only.
    sigma_population: float | None = None
    #: Core refit inside mu +/- CORE_SIGMA * sigma, or a copy of the plain
    #: moments when the refit did not run. ``estimator`` says which.
    mu_core: float | None = None
    sigma_core: float | None = None
    n_core: int = 0
    #: Robust width from the interquartile range; None below MIN_ROBUST_SAMPLES.
    sigma_robust: float | None = None
    #: sigma / mu, and the same ratio taken on the quoted core pair.
    resolution: float | None = None
    resolution_core: float | None = None
    #: Standard errors, and the interval marks they are NOT interchangeable with.
    mu_error: float | None = None
    sigma_error: float | None = None
    resolution_error: float | None = None
    mu_ci95: tuple[float, float] | None = None
    sigma_ci95: tuple[float, float] | None = None
    sigma_bias_factor: float | None = None
    sigma_unbiased: float | None = None
    #: Which rung of the ladder produced mu_core / sigma_core.
    estimator: str = "none"
    estimator_note: str = ""
    core_applied: bool = False
    #: All values identical: a delta, not a density.
    degenerate: bool = False
    #: Whether the sample was large enough to test the Gaussian assumption.
    shape_testable: bool = False
    non_gaussian: bool | None = None
    #: Which subset the moments were taken on, and how many survive the axis.
    moments_subset: str = "all finite values in slice"
    n_in_range: int | None = None
    #: True only when no width exists at all (n < MIN_MOMENT_SAMPLES).
    insufficient: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("mu_ci95", "sigma_ci95"):
            if data[key] is not None:
                data[key] = list(data[key])
        return data


def gaussian_curve(
    x: np.ndarray, mu: float, sigma: float, amplitude: float | None = None
) -> np.ndarray:
    """The notebook's Gaussian, evaluated on ``x``.

    ``amplitude`` defaults to the unit-area normalisation, so the curve is a
    probability density directly comparable with a ``density=True`` histogram.
    """
    if sigma is None or not sigma > 0:
        return np.zeros_like(x)
    amp = unit_area_amplitude(sigma) if amplitude is None else amplitude
    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def unit_area_amplitude(sigma: float) -> float:
    """Amplitude normalising the Gaussian to unit area."""
    return 1.0 / (sigma * math.sqrt(2.0 * math.pi)) if sigma > 0 else 0.0


def fit_gaussian(values: np.ndarray, label: str = "") -> GaussianFit:
    """Describe ``values`` by its moments, with a core refit and a sanity flag.

    Never refuses above :data:`MIN_MOMENT_SAMPLES`. What changes with the sample
    size is which estimator produced the numbers and how wide their uncertainty
    is, and both are reported rather than being grounds for silence.
    """
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    n = int(finite.size)

    if n == 0:
        return GaussianFit(
            n=0, estimator="none", insufficient=True,
            note="No events in this selection.",
        )

    mu = float(finite.mean())
    sigma_population = float(finite.std(ddof=0))

    if n < MIN_MOMENT_SAMPLES:
        return GaussianFit(
            n=n, mu=mu, sigma_population=sigma_population,
            mu_core=mu, n_core=n,
            estimator="mean_only", insufficient=True,
            estimator_note=(
                "A single event fixes a position and nothing else; no width "
                "exists to report."
            ),
            note=f"{label}: 1 event" if label else "1 event",
        )

    sigma = float(finite.std(ddof=DDOF))
    degenerate = sigma == 0.0
    df = n - 1

    # Uncertainty on each moment. These are two different quantities: mu_error
    # is the precision of the mean, sigma is the spread of the events, and they
    # differ by a factor of sqrt(N). The panel draws them as different marks.
    mu_error = sigma / math.sqrt(n)
    sigma_error = sigma / math.sqrt(2.0 * df)
    t = t_quantile_975(df)
    mu_ci95 = (mu - t * mu_error, mu + t * mu_error)
    sigma_ci95 = (
        sigma * math.sqrt(df / chi2_quantile(df, upper=True)),
        sigma * math.sqrt(df / chi2_quantile(df, upper=False)),
    )
    bias = c4(n)
    resolution = (sigma / mu) if mu else None
    resolution_error = None
    if resolution is not None:
        resolution_error = abs(resolution) * math.sqrt(
            1.0 / (2.0 * df) + resolution * resolution / n
        )

    # The Gaussian assumption is only testable with enough events to place
    # quartiles between rather than on individual observations.
    shape_testable = n >= MIN_ROBUST_SAMPLES
    sigma_robust: float | None = None
    non_gaussian: bool | None = None
    note = ""
    if shape_testable:
        q25, q75 = (float(v) for v in np.percentile(finite, [25.0, 75.0]))
        sigma_robust = (q75 - q25) / IQR_TO_SIGMA
        non_gaussian = False
        if sigma > 0 and sigma_robust > 0:
            disagreement = abs(sigma_robust - sigma) / sigma
            if disagreement > NON_GAUSSIAN_TOLERANCE:
                non_gaussian = True
                note = (
                    f"Moment width {sigma:.3g} and robust width "
                    f"{sigma_robust:.3g} differ by {100 * disagreement:.0f}%; "
                    "this spectrum has a non-Gaussian tail and the fitted "
                    "curve describes the core only."
                )

    refit = core_refit(finite, mu, sigma)

    if degenerate:
        estimator = "degenerate"
        estimator_note = (
            f"All {n:,} events share one energy to floating-point precision. "
            "The width is a measured zero, not an unknown, and no density "
            "curve is drawn: a delta is not a density."
        )
    elif refit.applied:
        estimator = "core_refit"
        estimator_note = (
            f"Iterated +/-{CORE_SIGMA:g} sigma core refit over {refit.n:,} of "
            f"{n:,} events in {refit.iterations} iteration"
            f"{'s' if refit.iterations != 1 else ''}"
            + (
                "; de-biased for truncation."
                if refit.truncated
                else "; the window cut nothing, so no truncation correction "
                     "was applied."
            )
        )
    elif n < MIN_CURVE_SAMPLES:
        estimator = "moments_1dof" if n == MIN_MOMENT_SAMPLES else "moments"
        pct = 100.0 * sigma_error / sigma if sigma > 0 else float("nan")
        estimator_note = (
            f"N = {n}: mu and sigma are plain sample moments (ddof = {DDOF}). "
            f"sigma is itself uncertain by {pct:.0f}%, its 95% interval is "
            f"[{sigma_ci95[0]:.3g}, {sigma_ci95[1]:.3g}], and no core refit was "
            "attempted. Too few events for a density curve; the individual "
            "events are drawn instead."
        )
    else:
        estimator = "moments"
        pct = 100.0 * sigma_error / sigma if sigma > 0 else float("nan")
        estimator_note = (
            f"N = {n}: mu and sigma are plain sample moments (ddof = {DDOF}); "
            f"sigma is uncertain by {pct:.0f}%. Below the {MIN_CORE_SAMPLES}-"
            "event core-refit floor, so the curve is drawn de-weighted and "
            "does not set the axis scale."
        )

    return GaussianFit(
        n=n,
        mu=mu,
        sigma=sigma,
        sigma_population=sigma_population,
        mu_core=refit.mu,
        sigma_core=refit.sigma,
        n_core=refit.n if refit.applied else n,
        sigma_robust=sigma_robust,
        resolution=resolution,
        resolution_core=(refit.sigma / refit.mu) if refit.mu else None,
        mu_error=mu_error,
        sigma_error=sigma_error,
        resolution_error=resolution_error,
        mu_ci95=mu_ci95,
        sigma_ci95=sigma_ci95,
        sigma_bias_factor=bias,
        sigma_unbiased=(sigma / bias) if bias else None,
        estimator=estimator,
        estimator_note=estimator_note,
        core_applied=refit.applied,
        degenerate=degenerate,
        shape_testable=shape_testable,
        non_gaussian=non_gaussian,
        insufficient=False,
        note=note or (f"{label}: {n:,} events" if label else ""),
    )
