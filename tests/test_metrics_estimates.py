"""The metric cards' estimators: clustered ratios, residual summaries, correlations."""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.stats import gaussian
from calosrv.stats import metrics as m


def _sums(num: np.ndarray, den: np.ndarray):
    return (num.sum(), den.sum(), (num * num).sum(), (den * den).sum(), (num * den).sum())


def test_the_ratio_se_is_the_per_event_linearisation():
    rng = np.random.default_rng(3)
    den = rng.integers(50, 2000, 40).astype(float)
    num = np.floor(den * rng.uniform(0.6, 0.9, den.size))
    estimate = m.ratio_estimate(*_sums(num, den), den.size)
    r = num.sum() / den.sum()
    z = (num - r * den) / den.mean()
    explicit = math.sqrt(np.sum(z * z) / (den.size * (den.size - 1)))
    assert estimate.value == pytest.approx(r, rel=1e-15)
    assert estimate.se == pytest.approx(explicit, rel=1e-9)
    t = gaussian.t_quantile_975(den.size - 1)
    assert estimate.interval.hi - estimate.value == pytest.approx(t * explicit, rel=1e-9)
    assert estimate.interval.method == m.METHOD_RATIO


def test_the_ratio_interval_covers_at_its_nominal_level():
    """Seeded simulation of clustered hits at N = 30 events: 95% +- 2%."""
    rng = np.random.default_rng(11)
    truth, n_events, trials, covered = 0.7, 30, 2000, 0
    for _ in range(trials):
        den = rng.integers(20, 400, n_events).astype(float)
        # Each event has its own rate: the hits are not independent draws.
        rate = np.clip(rng.normal(truth, 0.08, n_events), 0, 1)
        num = rng.binomial(den.astype(int), rate).astype(float)
        estimate = m.ratio_estimate(*_sums(num, den), n_events)
        # The population ratio for this design is the den-weighted mean rate.
        covered += estimate.interval.lo <= truth <= estimate.interval.hi
    assert 0.93 <= covered / trials <= 0.97


def test_a_proportion_interval_is_clipped_to_the_unit_range_and_says_so():
    num = np.array([10.0, 10.0, 9.0])
    den = np.array([10.0, 10.0, 10.0])
    estimate = m.ratio_estimate(*_sums(num, den), 3, bounds=(0.0, 1.0))
    assert estimate.interval.hi == 1.0
    assert "clipped" in estimate.interval.label


def test_one_event_gives_a_value_and_no_uncertainty():
    estimate = m.ratio_estimate(3.0, 4.0, 9.0, 16.0, 12.0, 1)
    assert estimate.value == 0.75 and estimate.se is None and estimate.interval is None
    assert "N = 1" in estimate.note
    empty = m.ratio_estimate(0.0, 0.0, 0.0, 0.0, 0.0, 0)
    assert empty.value is None


@pytest.mark.parametrize("n", [2, 3, 8, 14, 15, 40])
def test_the_residual_summary_uses_student_t_and_chi_squared(n):
    rng = np.random.default_rng(n)
    r = rng.normal(0.02, 0.2, n)
    summary = m.residual_summary(r)
    assert summary.sigma.value == pytest.approx(float(np.std(r, ddof=1)), rel=1e-12)
    assert summary.bias.value == pytest.approx(float(r.mean()), rel=1e-12)
    half = summary.bias.interval.hi - summary.bias.value
    assert half == pytest.approx(gaussian.t_quantile_975(n - 1) * np.std(r, ddof=1) / math.sqrt(n),
                                 rel=1e-9)
    assert summary.sigma.interval.method == m.METHOD_CHI2
    assert summary.sigma.interval.lo < summary.sigma.value < summary.sigma.interval.hi
    rmse = math.sqrt(float(np.mean(r * r)))
    assert summary.rmse.value == pytest.approx(rmse, rel=1e-12)
    card = m.Card("x", "x", "", "", summary.sigma).as_dict()
    assert card["show"] == ("ci" if n < m.SHOW_CI_BELOW_N else "se")
    if n < gaussian.MIN_CORE_SAMPLES:
        assert "c4" in summary.sigma.note


def test_non_finite_residuals_are_dropped_never_zero_filled():
    summary = m.residual_summary(np.array([0.1, np.nan, 0.3, np.inf, 0.2]))
    assert summary.sigma.n == 3
    assert summary.bias.value == pytest.approx(0.2)


def test_the_correlation_has_a_fisher_z_interval():
    rng = np.random.default_rng(5)
    x = rng.normal(size=200)
    y = 0.6 * x + rng.normal(scale=0.8, size=200)
    estimate = m.correlation(x, y)
    r = float(np.corrcoef(x, y)[0, 1])
    assert estimate.value == pytest.approx(r)
    z = math.atanh(r)
    assert estimate.interval.lo == pytest.approx(math.tanh(z - 1.959963985 / math.sqrt(197)))
    assert estimate.interval.method == m.METHOD_FISHER
    assert m.correlation(x[:3], y[:3]).interval is None
