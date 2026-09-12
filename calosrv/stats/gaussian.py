"""Gaussian description of a reconstructed-energy spectrum.

**The estimator is moment-based, and that is a deliberate commitment rather than
a shortcut.** ``calodash/stats.py`` already standardises this project on the
notebook's estimators - ``mu = mean``, ``sigma = std`` with ``ddof = 0``,
``amplitude = 1 / (sigma * sqrt(2*pi))`` - so that every sigma quoted anywhere in
the repository is comparable with the study the notebook describes. Switching to
a least-squares fit against a histogram would silently change every one of those
numbers, make them depend on the bin count, and - because the spectrum has a
genuine low-side containment-leakage tail - return a width that describes
neither the core nor the tail.

This module must stay numerically identical to ``calodash/stats.py`` for the
quantities they share. The functions below are re-implemented rather than
imported so the two architectures stay decoupled, and any change here needs the
same change there.

Two additions the batch module does not have:

*The iterated core fit.* Re-taking the moments inside ``mu +/- 2.5 sigma`` is the
standard calorimetric response measurement. It is still pure moments - no
solver, no initial guess - and it separates the Gaussian core resolution from
the non-Gaussian tail, which the shipped histogram still shows.

*A robustness flag.* The interquartile width divided by 1.349 estimates sigma for
a true Gaussian. When it disagrees with the moment sigma by more than
:data:`NON_GAUSSIAN_TOLERANCE`, the distribution is not Gaussian and the panel
says so rather than drawing a curve that misrepresents it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

#: Minimum sample size worth describing. Below this, ``calodash/stats.py``
#: returns nothing rather than a sigma from a handful of events, mirroring the
#: notebook's ``if len(values) < 10: continue``. The same guard applies here:
#: the demonstration dataset has two events, and a two-point "Gaussian" would be
#: arithmetically valid and scientifically meaningless.
MIN_SAMPLES = 10

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
CORE_TRUNCATION_FACTOR = 0.9365574133

#: Relative disagreement between the moment sigma and the robust sigma above
#: which the sample is flagged as non-Gaussian.
NON_GAUSSIAN_TOLERANCE = 0.15

#: sigma = IQR / 1.349 for a Gaussian.
IQR_TO_SIGMA = 1.349


@dataclass
class GaussianFit:
    """Moment description of one sample."""

    n: int
    mu: float | None = None
    sigma: float | None = None
    #: Core refit inside mu +/- CORE_SIGMA * sigma.
    mu_core: float | None = None
    sigma_core: float | None = None
    n_core: int = 0
    #: Robust width from the interquartile range.
    sigma_robust: float | None = None
    #: sigma / mu, the fractional energy resolution.
    resolution: float | None = None
    non_gaussian: bool = False
    insufficient: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    """Describe ``values`` by its moments, with a core refit and a sanity flag."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    n = int(finite.size)

    if n < MIN_SAMPLES:
        return GaussianFit(
            n=n,
            insufficient=True,
            note=(
                f"Only {n} event{'s' if n != 1 else ''} in this selection; at "
                f"least {MIN_SAMPLES} are needed before a width is meaningful."
            ),
        )

    mu = float(finite.mean())
    sigma = float(finite.std(ddof=0))

    q25, q75 = (float(v) for v in np.percentile(finite, [25.0, 75.0]))
    sigma_robust = (q75 - q25) / IQR_TO_SIGMA

    mu_core, sigma_core, n_core = mu, sigma, n
    if sigma > 0:
        window = sigma
        for _ in range(CORE_ITERATIONS):
            lo = mu_core - CORE_SIGMA * window
            hi = mu_core + CORE_SIGMA * window
            core = finite[(finite >= lo) & (finite <= hi)]
            if core.size < MIN_SAMPLES:
                break
            new_mu = float(core.mean())
            new_sigma = float(core.std(ddof=0))
            if new_sigma <= 0:
                break
            converged = abs(new_sigma - window) <= 1e-7 * max(window, 1e-12)
            mu_core, window, n_core = new_mu, new_sigma, int(core.size)
            if converged:
                break
        # De-bias: the refit measures the width of the *truncated* sample, not
        # of the Gaussian it was cut from. See CORE_TRUNCATION_FACTOR.
        sigma_core = window / CORE_TRUNCATION_FACTOR

    non_gaussian = False
    note = ""
    if sigma > 0 and sigma_robust > 0:
        disagreement = abs(sigma_robust - sigma) / sigma
        if disagreement > NON_GAUSSIAN_TOLERANCE:
            non_gaussian = True
            note = (
                f"Moment width {sigma:.3g} and robust width {sigma_robust:.3g} "
                f"differ by {100 * disagreement:.0f}%; this spectrum has a "
                "non-Gaussian tail and the fitted curve describes the core only."
            )

    return GaussianFit(
        n=n,
        mu=mu,
        sigma=sigma,
        mu_core=mu_core,
        sigma_core=sigma_core,
        n_core=n_core,
        sigma_robust=sigma_robust,
        resolution=(sigma / mu) if mu else None,
        non_gaussian=non_gaussian,
        note=note or (f"{label}: {n:,} events" if label else ""),
    )
