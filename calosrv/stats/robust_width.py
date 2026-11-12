"""Robust widths of the per-event response ratio, and exact bootstraps of their uncertainty.

The Models page's energy-resolution card (``query/resolution_scaling.py``)
plots one error scale per momentum window of ``R = E_est / p``, by one of three
estimators (Martin's decisions, 2026-11-12): the median relative error
``median |R − 1|`` (the default, the Median rel. of Model Error vs. Incident
Momentum), the robust ``σ/E = IQR(R) / (1.349 · median R)`` of this module, and
the sample ``s(R) / R̄``. This module holds the robust width, its interval, the
bootstrap standard errors both non-sample estimators weight their fits by, and
the tail share every window quotes.

**Why a robust width.** Measured on ``pion_hits_with_model_outputs``
(2026-11-12; shower A, absolute-frame energy network, 10–11 GeV, N = 1,022):
``s(R)/R̄`` = 17.15%, ``IQR(R)/(1.349·median R)`` = 12.03%, and
``median |R − 1|`` = 8.52%. 17.15 = 8.52 × 1.4826 × 0.953 × 1.426: ×1.4826 is a
definition (``median |R − 1| = Φ⁻¹(¾)·σ/E = 0.6745·σ/E`` for unbiased Gaussian
errors), ×0.953 is bias and centring, and ×1.43 is the tails: 4.3% of the
window's events lie beyond 3 robust σ, against 0.27% for a Gaussian
(:data:`GAUSSIAN_TAIL_SHARE`), with an excess kurtosis of 3.9. The
σ-consistent widths of that window agree within ±0.4 points (IQR 12.03, MAD
12.04, σ_eff 12.77, the ±2.5σ core 12.68, 1.4826·median rel. 12.63). The
interquartile range is the one served, for three reasons: it is the codebase's
existing robust width (``gaussian.IQR_TO_SIGMA``), it is invariant under
``R → cR`` (so the deposit's calibration cancels in it, as in ``s/R̄``), and it
admits an exact O(B) bootstrap.

**Type-7 quartiles**, NumPy's default ``np.percentile``: with ``h = (n − 1)p +
1`` the quantile is ``x₍⌊h⌋₎ + (h − ⌊h⌋)(x₍⌊h⌋+1₎ − x₍⌊h⌋₎)``, 1-based
(:func:`type7_rank`). The point value is ``np.percentile`` itself, so it agrees
with ``gaussian.fit_gaussian``'s ``sigma_robust`` to the last bit.

**The exact bootstrap** (:func:`bootstrap_quantiles`). Resampling ``n`` values
with replacement from the sorted sample and taking the k-th smallest picks
``x₍⌈n·U₍ₖ₎⌉₎``, ``U₍ₖ₎`` the k-th order statistic of ``n`` uniforms. A type-7
quartile needs only two of them, so each replicate draws the (at most six)
order statistics behind the three quartiles directly, in increasing rank, by
sequential conditional Betas: ``U₍ₖ₎ = U₍ⱼ₎ + (1 − U₍ⱼ₎)·Beta(k − j, n − k + 1)``
given the previous ``U₍ⱼ₎`` (``U₍₀₎ = 0``). That is the resampling distribution
itself at O(B) cost, the trick ``stats/median.py`` uses for one median. Measured
on the pion file's network windows (2026-11-12): within 0.1 point of brute-force
resampling at about 0.5 ms a window, against 15–64 ms. The median absolute
deviation would not qualify: its order statistics are those of ``|x − median|``,
which move with each resample's median (45 ms a window, brute force).

**Fit weights κ** (:func:`median_se`, :func:`relative_se`). The Gaussian
asymptotic standard-error law understates the measured bootstrap SE of these
widths: by a median 1.17×, 0.94–1.71× over the 5th–95th percentile of windows
and up to 2.4× at the edge windows of a bounded-range regressor (pion file,
2026-11-12). So the card's median and robust fits weight each window by its own
measured relative SE, ``κ = SE_boot / value``, applied at the fitted value and
iterated (``stats/resolution_fit.py``), which keeps the protection against the
Neyman bias the delta-method law gave the sample estimator.

**The tail share** (:func:`tail_share`): the share of a window's events beyond
3 robust σ of its median, ``mean(|R − R̃| > 3·IQR(R)/1.349)``, from the robust
floor (N = 20): a Gaussian gives :data:`GAUSSIAN_TAIL_SHARE` = 0.27%.

Pure NumPy. Inputs and outputs are fractions; the query module writes percent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from . import gaussian
from . import median as median_mod
from .metrics import METHOD_BOOTSTRAP, Interval

#: σ = IQR / 1.349 for a Gaussian (2·Φ⁻¹(¾) = 1.3490), the codebase's robust width.
IQR_TO_SIGMA = gaussian.IQR_TO_SIGMA

#: The three type-7 quantiles the robust width reads.
QUARTILES: tuple[float, float, float] = (0.25, 0.5, 0.75)

#: The robust width, its whisker, fits and range start here (CLAUDE.md, the robust floor:
#: below it np.percentile interpolates between single events).
MIN_ROBUST_N = gaussian.MIN_ROBUST_SAMPLES

#: Replicates per bootstrap, as the median's.
BOOTSTRAP_REPLICATES = median_mod.BOOTSTRAP_REPLICATES

#: The last element of the robust width's bootstrap seed ``[42, frame, shower, bin, 8]``:
#: after ``performance_bins.QUANTITIES`` (0–4) and its azimuth quantities (5–7), so no
#: quantity of either card shares a random stream with another.
SEED_QUANTITY_INDEX = 8

#: A window's events beyond this many robust σ of its median are its tail.
TAIL_SIGMAS = 3.0

#: The tail share of a Gaussian: 2·(1 − Φ(3)) = 0.26998%.
GAUSSIAN_TAIL_SHARE = math.erfc(TAIL_SIGMAS / math.sqrt(2.0))

#: The 95% percentile interval's ends, written as decimals: ``(1 − 0.95)/2`` evaluates to
#: 0.025000000000000022, and the reference implementation the card was verified with takes
#: ``np.quantile(replicates, [0.025, 0.975])``.
PERCENTILES: tuple[float, float] = (0.025, 0.975)


def _sorted_finite(values) -> np.ndarray:
    a = np.asarray(values, dtype=np.float64)
    return np.sort(a[np.isfinite(a)])


def type7_rank(n: int, p: float) -> tuple[int, int, float]:
    """``(lo, hi, frac)``: the 1-based ranks a type-7 quantile interpolates between, and its weight.

    ``h = (n − 1)p + 1``; ``lo = ⌊h⌋``, ``hi = min(lo + 1, n)`` and
    ``frac = h − lo``, so the quantile is ``x₍lo₎ + frac·(x₍hi₎ − x₍lo₎)``. At an
    integer ``h`` the weight is 0 and ``hi`` still names the next rank (the
    bootstrap draws it; its weight is zero). ``(n − 1)p`` is exact for the
    quartiles, binary fractions, so an integer ``h`` is recognised exactly.
    """
    if n < 1:
        raise ValueError("a quantile needs at least one value")
    h = (n - 1) * p + 1.0
    lo = int(math.floor(h))
    return lo, min(lo + 1, n), h - lo


def bootstrap_quantiles(values, probs: Sequence[float] = QUARTILES,
                        replicates: int = BOOTSTRAP_REPLICATES,
                        seed: int | Sequence[int] = median_mod.BOOTSTRAP_SEED) -> np.ndarray:
    """Exact bootstrap replicates of type-7 quantiles: an array of shape ``(len(probs), replicates)``.

    Row i holds the ``probs[i]`` quantile of ``replicates`` resamples of the
    finite ``values``, each drawn from the resample's exact order statistics
    (the module docstring): the ranks behind every quantile, in increasing
    order, by sequential conditional Betas from one seeded generator. Empty
    columns for an empty sample.
    """
    x = _sorted_finite(values)
    n = int(x.size)
    if n == 0:
        return np.empty((len(probs), 0), dtype=np.float64)
    plan = [type7_rank(n, p) for p in probs]
    ranks = sorted({k for lo, hi, _ in plan for k in (lo, hi)})
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    uniform: dict[int, np.ndarray] = {}
    prev_k, prev_u = 0, np.zeros(replicates)
    for k in ranks:
        # U_(k) given U_(prev): prev + (1 − prev)·Beta(k − prev_k, n − k + 1).
        uniform[k] = prev_u + (1.0 - prev_u) * rng.beta(k - prev_k, n - k + 1, size=replicates)
        prev_k, prev_u = k, uniform[k]

    def order_statistic(k: int) -> np.ndarray:
        return x[np.clip(np.ceil(n * uniform[k]).astype(np.int64), 1, n) - 1]

    rows = []
    for lo, hi, frac in plan:
        a = order_statistic(lo)
        b = order_statistic(hi)
        rows.append(a + frac * (b - a))
    return np.array(rows)


def iqr_resolution(values) -> float | None:
    """``IQR(R) / (1.349 · median R)`` of the finite ``values``, type-7; ``None`` unless median R > 0.

    Not gated here: :func:`robust_width` applies the robust floor.
    """
    x = _sorted_finite(values)
    if x.size == 0:
        return None
    q25, q50, q75 = (float(v) for v in np.percentile(x, [25.0, 50.0, 75.0]))
    if not q50 > 0.0:
        return None
    return (q75 - q25) / IQR_TO_SIGMA / q50


def _seed_text(seed: int | Sequence[int]) -> str:
    return str(seed) if isinstance(seed, int) else "/".join(str(s) for s in seed)


def _replicate_summary(replicates: np.ndarray) -> tuple[tuple[float, float] | None, float | None, int]:
    """``(95% percentile interval, SD with ddof = 1, finite count)`` of bootstrap replicates."""
    finite = replicates[np.isfinite(replicates)]
    if finite.size < 2:
        return None, None, int(finite.size)
    lo, hi = np.quantile(finite, list(PERCENTILES))
    return (float(lo), float(hi)), float(finite.std(ddof=1)), int(finite.size)


#: The smallest relative SE that is a sampling error. Below one part per million of its own
#: value, a bootstrap SD is the floating-point spread of tied replicates: every resample's
#: median (or quartiles) is the same order statistic, so the replicates differ by rounding
#: alone. Such a "SE" would weight its window 10¹² times or more against the others. On the
#: synthetic two-shower fixture (2026-11-12), 32 median windows of tied deposits gave
#: κ ≈ 10⁻⁸, and the pinned fits through them reached S = 8.2 × 10⁶. A window below the floor
#: therefore has no κ: it is drawn with its (zero-width) interval and not fitted, which is the
#: rule a window without a positive SE has always followed. Continuous data stay far above it:
#: the stored experiments' windows have κ of 2–40%.
KAPPA_FLOOR = 1e-6


def relative_se(se: float | None, value: float | None) -> float | None:
    """κ = SE / value: a window's relative standard error.

    ``None`` unless both are positive and κ reaches :data:`KAPPA_FLOOR`: below
    it the SE is the rounding of tied replicates, not a sampling error.
    """
    if se is None or value is None or not (se > 0.0 and value > 0.0):
        return None
    kappa = se / value
    return kappa if kappa >= KAPPA_FLOOR else None


@dataclass(frozen=True)
class RobustWidth:
    """One window's robust width ``IQR(R)/(1.349·median R)``, as a fraction, with its uncertainty."""

    value: float | None
    n: int
    interval: Interval | None
    se: float | None
    #: Bootstrap replicates with a positive median, which the interval and SE are taken over.
    n_replicates: int
    note: str

    @property
    def kappa(self) -> float | None:
        """κ = SE / value, the fit weight's relative SE."""
        return relative_se(self.se, self.value)


def robust_width(values, seed: int | Sequence[int] = median_mod.BOOTSTRAP_SEED,
                 replicates: int = BOOTSTRAP_REPLICATES, bootstrap: bool = True) -> RobustWidth:
    """The robust width of ``values`` from N = 20, with its exact-bootstrap 95% interval and SE.

    Below :data:`MIN_ROBUST_N` the value is ``None`` and the note says why; it
    is ``None`` too where median R ≤ 0, since a width relative to a
    non-positive response is no resolution. ``bootstrap=False`` skips the
    interval and SE (a cross-reference quotes the value alone). A replicate
    whose median is not positive is left out of both, and counted.
    """
    x = _sorted_finite(values)
    n = int(x.size)
    if n < MIN_ROBUST_N:
        return RobustWidth(None, n, None, None, 0,
                           f"N = {n} < {MIN_ROBUST_N}: below the robust floor, no robust σ/E.")
    value = iqr_resolution(x)
    if value is None:
        return RobustWidth(None, n, None, None, 0,
                           "The median response is not positive, so no robust σ/E is defined.")
    if not bootstrap:
        return RobustWidth(value, n, None, None, 0, "")
    q25, q50, q75 = bootstrap_quantiles(x, QUARTILES, replicates, seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        widths = np.where(q50 > 0.0, (q75 - q25) / IQR_TO_SIGMA / q50, np.nan)
    bounds, se, used = _replicate_summary(widths)
    dropped = replicates - used
    label = (f"95% percentile bootstrap of IQR(R)/(1.349·median R), B = {replicates:,}, each "
             "replicate's quartiles drawn exactly from its resample's order statistics, seed "
             f"{_seed_text(seed)}")
    if dropped:
        label += (f"; {dropped:,} replicate{'s' if dropped != 1 else ''} with a non-positive "
                  "median left out")
    interval = None if bounds is None else Interval(bounds[0], bounds[1], METHOD_BOOTSTRAP, label)
    return RobustWidth(value, n, interval, se, used, "")


def median_se(relative, seed: int | Sequence[int] = median_mod.BOOTSTRAP_SEED,
              replicates: int = BOOTSTRAP_REPLICATES) -> float | None:
    """The bootstrap SE of ``median(relative)``: the SD (ddof = 1) of ``median.bootstrap_medians``.

    The same seed as ``median.median_estimate`` gives the same replicates, so
    the SE belongs to the interval quoted beside it. From N = 2, a reported
    number; ``None`` below.
    """
    medians = median_mod.bootstrap_medians(relative, replicates=replicates, seed=seed)
    finite = medians[np.isfinite(medians)]
    if _sorted_finite(relative).size < gaussian.MIN_MOMENT_SAMPLES or finite.size < 2:
        return None
    return float(finite.std(ddof=1))


def tail_share(values) -> float | None:
    """The share of events beyond 3 robust σ of the median, ``|R − R̃| > 3·IQR(R)/1.349``; from N = 20.

    A fraction (a Gaussian gives :data:`GAUSSIAN_TAIL_SHARE`); ``None`` below the robust floor.
    """
    x = _sorted_finite(values)
    if x.size < MIN_ROBUST_N:
        return None
    q25, q50, q75 = (float(v) for v in np.percentile(x, [25.0, 50.0, 75.0]))
    sigma = (q75 - q25) / IQR_TO_SIGMA
    return float(np.mean(np.abs(x - q50) > TAIL_SIGMAS * sigma))
