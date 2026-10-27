"""Decision D-4: the RMSE interval of the momentum-bin performance (``stats/rmse.py``).

A χ² interval under normal residuals centred on zero from N = 2 to 19, the
seeded percentile bootstrap of the RMSE from N = 20, and nothing at N = 1. The
Physics page's metric cards keep ``metrics.residual_summary`` (the square root
of the Student-t interval of the mean squared residual); that is checked here
too, so the decision cannot leak into Page 1.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import chi2

from calosrv.stats import metrics
from calosrv.stats import rmse


def test_no_residual_and_one_residual_have_no_interval():
    assert rmse.rmse_estimate(np.array([])).value is None
    one = rmse.rmse_estimate(np.array([-0.7]))
    assert one.value == pytest.approx(0.7) and one.interval is None and one.n == 1
    assert "observation" in one.note


@pytest.mark.parametrize("n", [2, 3, 8, 19])
def test_below_twenty_the_interval_is_chi_squared_on_n_degrees_of_freedom(n):
    r = np.random.default_rng(n).normal(0.0, 2.0, n)
    est = rmse.rmse_estimate(r)
    value = math.sqrt(np.mean(r ** 2))
    assert est.value == pytest.approx(value)
    # The tabulated quantiles carry three decimals: within 1e-3 of scipy's.
    assert est.interval.lo == pytest.approx(value * math.sqrt(n / chi2.ppf(0.975, n)), rel=1e-3)
    assert est.interval.hi == pytest.approx(value * math.sqrt(n / chi2.ppf(0.025, n)), rel=1e-3)
    assert est.interval.lo < value < est.interval.hi
    assert est.interval.method == rmse.METHOD_CHI2_RMSE
    assert "normally distributed residuals" in est.interval.label and f"{n} dof" in est.interval.label


def test_from_twenty_the_interval_is_the_seeded_bootstrap_and_does_not_depend_on_chunking(monkeypatch):
    r = np.random.default_rng(3).standard_t(4, 57)
    seed = [42, 1, 0, 7, 0]
    est = rmse.rmse_estimate(r, seed=seed)
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    means = (r ** 2)[rng.integers(0, r.size, size=(2000, r.size))].mean(axis=1)
    lo, hi = np.quantile(np.sqrt(means), [0.025, 0.975])
    assert (est.interval.lo, est.interval.hi) == pytest.approx((lo, hi))
    assert est.interval.method == metrics.METHOD_BOOTSTRAP and "42/1/0/7/0" in est.interval.label
    monkeypatch.setattr(rmse, "_CHUNK_VALUES", 100)
    again = rmse.rmse_estimate(r, seed=seed)
    assert (again.interval.lo, again.interval.hi) == (est.interval.lo, est.interval.hi)
    other = rmse.rmse_estimate(r, seed=[42, 1, 0, 8, 0])
    assert (other.interval.lo, other.interval.hi) != (est.interval.lo, est.interval.hi)


def test_the_lower_end_no_longer_collapses_to_zero_at_small_n():
    """The review's evidence: √(t interval of the MSE) gave 0 at N ≤ 8; χ² never does."""
    r = np.array([0.01, -0.02, 3.0])
    old = metrics.residual_summary(r).rmse.interval
    new = rmse.rmse_estimate(r).interval
    assert old.lo == 0.0 and new.lo > 0.0


def test_page_one_keeps_its_estimator():
    r = np.random.default_rng(11).normal(0, 1, 30)
    card = metrics.residual_summary(r).rmse.interval
    assert card.method == metrics.METHOD_T and "square root of the MSE interval" in card.label


# ------------------------------------------- the groups on a thread pool --


def _production_sized(model: str) -> tuple[dict, object]:
    """A synthetic two-shower selection the size of production: 20,325 events, 19 bins, 3 frames."""
    from calosrv.query import performance_bins as pb

    rng = np.random.default_rng(2026)
    n = 20_325
    cols = {}
    for s in ("a", "b"):
        p = rng.uniform(1, 20, n)
        cols[f"bin_{s}"] = np.floor(p).clip(1, 19)
        true = p if model == "energy" else rng.uniform(0.05, 0.4, n)
        cols[f"true_{s}"] = true
        for c in ("lab", "trans", "local"):
            pred = true * (1 + rng.normal(0, 0.05, n)) + rng.standard_t(3, n) * 0.02
            pred[rng.random(n) < 0.01] = np.nan       # a few missing predictions
            cols[f"pred_{s}_{c}"] = pred
    return cols, pb.axis_from_ranges({k: (float(k), k + 0.999) for k in range(1, 20)})


@pytest.mark.parametrize("model", ["energy", "angle"])
def test_the_threaded_groups_equal_the_serial_path_exactly(model):
    """Each group keeps its own seed: the pool changes the time, never a number."""
    from calosrv.query import performance_bins as pb

    cols, axis = _production_sized(model)
    frames = ("lab", "trans", "local")
    serial = pb.build(cols, axis, model, frames, workers=1).as_dict()
    threaded = pb.build(cols, axis, model, frames, workers=8).as_dict()
    assert threaded == serial
    # The bootstrap regime is exercised: every group is well above N = 20.
    assert all(m == "bootstrap_percentile" for s in serial["series"] for m in s["rmse_method"])


def test_map_groups_keeps_task_order_and_never_exceeds_its_bound(monkeypatch):
    from calosrv.query import performance_bins as pb

    made = []
    real = pb.ThreadPoolExecutor

    def spy(max_workers, **kw):
        made.append(max_workers)
        return real(max_workers=max_workers, **kw)

    monkeypatch.setattr(pb, "ThreadPoolExecutor", spy)
    tasks = [(i,) for i in range(50)]
    assert pb.map_groups(lambda i: i * i, tasks, workers=6) == [i * i for i in range(50)]
    assert pb.map_groups(lambda i: i, [(1,), (2,)], workers=6) == [1, 2]
    assert pb.map_groups(lambda i: i, tasks, workers=1) == list(range(50))
    # One pool per call, bounded by the workers and by the tasks; none for one worker.
    assert made == [6, 2]
