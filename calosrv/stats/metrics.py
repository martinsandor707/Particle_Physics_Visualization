"""Model-performance metric formulas.

Kept apart from the SQL that supplies their inputs so the definitions can be
read and checked on their own.

The one that matters most here is the distinction between the plain and the
energy-weighted voxel error. Per-hit energies span fifteen decades and the
overwhelming majority of hits are sub-femto-GeV dust, where the segmentation
model's answer is physically irrelevant. An unweighted mean absolute error is
therefore dominated by cells nobody cares about, and will look excellent while
the model is wrong about the shower core. The energy-weighted form -
``sum(energy * |pred - true|) / sum(energy)`` - answers the question actually
being asked, which is how much *energy* the model mis-assigns. Both are
reported; the energy-weighted one is the headline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any, Sequence

import numpy as np

from . import gaussian


def finite(value: float | None) -> float | None:
    """Return ``value`` only if it is a real, representable number.

    Infinities and NaNs reach here legitimately. A relative residual
    ``(pred - true) / true`` over an event whose true energy is a few
    femto-GeV overflows to infinity, and a correlation over a single event is
    NaN. Neither is a measurement, and neither can be encoded as JSON - the
    model-performance endpoint returned HTTP 500 with "Out of range float
    values are not JSON compliant" for exactly this reason on narrow
    selections. Reporting ``null``, which the interface renders as an em dash,
    is both honest and serialisable.
    """
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return finite(numerator / denominator)


@dataclass
class ClassificationMetrics:
    """Voxel-level assignment quality at a 0.5 decision threshold."""

    n_voxels: int
    accuracy: float | None
    precision_a: float | None
    recall_a: float | None
    f1_a: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegressionMetrics:
    """Error on the continuous voxel fraction itself."""

    mae: float | None
    mae_energy_weighted: float | None
    rmse: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classification(
    n_voxels: int,
    n_correct: int,
    n_true_a: int,
    n_pred_a: int,
    n_tp: int,
) -> ClassificationMetrics:
    """Roll up the stored classification counts.

    Every input is an exact sum over the selected events, so these are exact
    metrics over the selection - not estimates from a sample.
    """
    return ClassificationMetrics(
        n_voxels=n_voxels,
        accuracy=_safe_div(n_correct, n_voxels),
        precision_a=_safe_div(n_tp, n_pred_a),
        recall_a=_safe_div(n_tp, n_true_a),
        f1_a=_safe_div(2.0 * n_tp, n_pred_a + n_true_a),
    )


def regression(
    n_voxels: int,
    sum_abs_err: float,
    sum_wabs_err: float,
    sum_sq_err: float,
    e_dep: float,
) -> RegressionMetrics:
    mse = _safe_div(sum_sq_err, n_voxels)
    return RegressionMetrics(
        mae=_safe_div(sum_abs_err, n_voxels),
        mae_energy_weighted=_safe_div(sum_wabs_err, e_dep),
        rmse=finite(mse ** 0.5) if mse is not None and mse >= 0 else None,
    )


# ------------------------------------------------------------- estimates --
#
# A metric card quotes a statistic of the selection, so it carries the
# uncertainty of that statistic (CLAUDE.md section 2: never a naked point
# estimate) - its standard error and a 95% interval named by method. At small
# N the interval is Student-t, never the normal approximation.

CI_LEVEL = 0.95

METHOD_T = "t"
METHOD_RATIO = "ratio_t"
METHOD_CHI2 = "chi2"
METHOD_FISHER = "fisher_z"

#: Below this many events a card shows its interval rather than its SE.
SHOW_CI_BELOW_N = gaussian.MIN_CORE_SAMPLES


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float
    method: str
    label: str
    level: float = CI_LEVEL

    def as_dict(self) -> dict[str, Any]:
        return {"lo": finite(self.lo), "hi": finite(self.hi), "level": self.level,
                "method": self.method, "label": self.label}


@dataclass(frozen=True)
class Estimate:
    value: float | None
    se: float | None = None
    interval: Interval | None = None
    n: int = 0
    note: str = ""


@dataclass
class Card:
    """One sidebar metric, self-describing so the interface renders it generically."""

    id: str
    label: str
    sub: str
    unit: str          # "fraction" (shown as %), "GeV", "mrad", "" (dimensionless)
    estimate: Estimate
    primary: bool = False
    shower: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        e = self.estimate
        note = " ".join(part for part in (e.note, *self.notes) if part)
        return {
            "id": self.id, "label": self.label, "sub": self.sub, "unit": self.unit,
            "value": finite(e.value), "se": finite(e.se),
            "interval": e.interval.as_dict() if e.interval else None,
            "n": e.n, "show": "ci" if e.n < SHOW_CI_BELOW_N else "se",
            "primary": self.primary, "shower": self.shower, "note": note,
        }


def _clip(interval: Interval | None, bounds: tuple[float, float] | None) -> Interval | None:
    if interval is None or bounds is None:
        return interval
    lo, hi = max(interval.lo, bounds[0]), min(interval.hi, bounds[1])
    if (lo, hi) == (interval.lo, interval.hi):
        return interval
    return Interval(lo, hi, interval.method, interval.label + f", clipped to [{bounds[0]:g}, {bounds[1]:g}]")


def ratio_estimate(
    sn: float, sd: float, snn: float, sdd: float, snd: float, n: int,
    bounds: tuple[float, float] | None = None,
) -> Estimate:
    """``R = sum(num) / sum(den)`` over events, with events as clusters.

    The hits of one event are not independent draws - they share a shower - so
    the sampling unit is the event. The linearised (delta-method) variance of
    a ratio of sums over ``n`` clusters is::

        SE^2 = sum_i (num_i - R den_i)^2 / (n (n - 1) mean(den)^2)

    expanded here in the five sums the event table rolls up in one pass. The
    interval is ``R +- t_{0.975, n-1} SE``, clipped to ``bounds`` when the
    quantity has a physical range (a proportion); the clip is stated.
    """
    n = int(n)
    if n <= 0 or not sd:
        return Estimate(None, n=n, note="No events in this selection.")
    r = sn / sd
    if n < 2:
        return Estimate(r, n=n, note="N = 1: a single event; no uncertainty can be estimated.")
    mean_den = sd / n
    numerator = max(0.0, snn - 2.0 * r * snd + r * r * sdd)
    se = math.sqrt(numerator / (n * (n - 1) * mean_den * mean_den))
    t = gaussian.t_quantile_975(n - 1)
    interval = Interval(r - t * se, r + t * se, METHOD_RATIO,
                        f"95% Student-t interval, {n - 1} dof; events as clusters (linearised ratio)")
    return Estimate(r, se, _clip(interval, bounds), n)


def sqrt_estimate(mse: Estimate) -> Estimate:
    """RMSE from an MSE estimate: interval endpoints square-rooted, SE by the delta method."""
    if mse.value is None or mse.value < 0:
        return Estimate(None, n=mse.n, note=mse.note)
    rmse = math.sqrt(mse.value)
    se = mse.se / (2.0 * rmse) if mse.se is not None and rmse > 0 else None
    interval = None
    if mse.interval is not None:
        interval = Interval(math.sqrt(max(0.0, mse.interval.lo)), math.sqrt(max(0.0, mse.interval.hi)),
                            mse.interval.method, mse.interval.label + "; square root of the MSE interval")
    return Estimate(rmse, se, interval, mse.n, mse.note)


@dataclass(frozen=True)
class ResidualSummary:
    bias: Estimate
    sigma: Estimate
    rmse: Estimate
    fit: gaussian.GaussianFit


def residual_summary(residuals: np.ndarray) -> ResidualSummary:
    """Bias, width and RMSE of per-shower residuals, each with its own interval.

    Built on :func:`gaussian.fit_gaussian`, so the width is the unbiased
    ``ddof = 1`` estimator the energy panel quotes, with its chi-squared
    interval and the c4 bias factor; the bias is the mean with its Student-t
    interval; the RMSE takes a t-interval on the mean squared residual and
    square-roots it. Non-finite residuals are dropped, never zero-filled.
    """
    r = np.asarray(residuals, dtype=np.float64)
    r = r[np.isfinite(r)]
    fit = gaussian.fit_gaussian(r)
    n = int(r.size)
    if n == 0:
        empty = Estimate(None, n=0, note="No showers in this selection.")
        return ResidualSummary(empty, empty, empty, fit)
    if n < 2:
        one = "N = 1: a single shower; no width or uncertainty can be estimated."
        return ResidualSummary(Estimate(float(r[0]), n=1, note=one), Estimate(None, n=1, note=one),
                               Estimate(abs(float(r[0])), n=1, note=one), fit)
    df = n - 1
    bias = Estimate(fit.mu, fit.mu_error,
                    Interval(*fit.mu_ci95, METHOD_T, f"95% Student-t interval of the mean, {df} dof"), n)
    notes = []
    if fit.sigma_bias_factor and n < gaussian.MIN_CORE_SAMPLES:
        notes.append(f"ddof = 1 makes the variance unbiased, not σ: expected s/σ = c4 = "
                     f"{fit.sigma_bias_factor:.3f} at N = {n}.")
    if fit.non_gaussian:
        notes.append(f"Non-Gaussian: robust (IQR) width {fit.sigma_robust:.3g} against the "
                     f"moment width {fit.sigma:.3g}.")
    elif not fit.shape_testable:
        notes.append(f"Gaussian shape untestable below N = {gaussian.MIN_ROBUST_SAMPLES}.")
    sigma = Estimate(fit.sigma, fit.sigma_error,
                     Interval(*fit.sigma_ci95, METHOD_CHI2, f"95% χ² interval of σ, {df} dof"), n,
                     " ".join(notes))
    sq = r * r
    mse = Estimate(float(sq.mean()), float(sq.std(ddof=1) / math.sqrt(n)), None, n)
    t = gaussian.t_quantile_975(df)
    mse = Estimate(mse.value, mse.se,
                   Interval(mse.value - t * mse.se, mse.value + t * mse.se, METHOD_T,
                            f"95% Student-t interval of the mean squared residual, {df} dof"), n)
    return ResidualSummary(bias, sigma, sqrt_estimate(mse), fit)


def correlation(x: np.ndarray, y: np.ndarray) -> Estimate:
    """Pearson r with a Fisher-z 95% interval (n >= 4)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    n = int(x.size)
    if n < 3 or x.std() == 0 or y.std() == 0:
        return Estimate(None, n=n, note="Too few showers, or no spread, for a correlation.")
    r = float(np.corrcoef(x, y)[0, 1])
    if n < 4 or abs(r) >= 1.0:
        return Estimate(r, n=n, note="Fisher-z interval needs N ≥ 4 and |r| < 1.")
    se_z = 1.0 / math.sqrt(n - 3)
    z = math.atanh(r)
    zq = 1.959963985
    interval = Interval(math.tanh(z - zq * se_z), math.tanh(z + zq * se_z), METHOD_FISHER,
                        "95% Fisher-z interval")
    return Estimate(r, (1.0 - r * r) * se_z, interval, n)


def ratio_sums_sql(num: str, den: str, alias: str) -> str:
    """The five per-event sums :func:`ratio_estimate` needs, as SQL aggregates."""
    n = f"CAST({num} AS DOUBLE)"
    d = f"CAST({den} AS DOUBLE)"
    return (f"coalesce(sum({n}), 0) AS {alias}_sn, coalesce(sum({d}), 0) AS {alias}_sd, "
            f"coalesce(sum({n} * {n}), 0) AS {alias}_snn, coalesce(sum({d} * {d}), 0) AS {alias}_sdd, "
            f"coalesce(sum({n} * {d}), 0) AS {alias}_snd")


def ratio_from_row(row: dict[str, Any], alias: str, n: int,
                   bounds: tuple[float, float] | None = None) -> Estimate:
    return ratio_estimate(*(float(row[f"{alias}_{k}"]) for k in ("sn", "sd", "snn", "sdd", "snd")),
                          n, bounds)


__all__: Sequence[str] = (
    "finite", "ClassificationMetrics", "RegressionMetrics", "classification", "regression",
    "Interval", "Estimate", "Card", "ratio_estimate", "sqrt_estimate", "residual_summary",
    "ResidualSummary", "correlation", "ratio_sums_sql", "ratio_from_row",
)
