"""``GET /api/response`` on two showers, booted against the synthetic all-models file.

The file holds 286 events at separations whose populations are 1, 2, 7, 8, 14,
15, 19, 20 and 200, with each shower's momentum drawn on 2-18 GeV, so every low-N
rung of the cards is on screen through a D window, and the two showers fill
different momentum bins. Expected values are recomputed from the event table with
NumPy by formulas written out here. Booted against ``synthetic_client`` only:
that fixture owns the database singleton, so this module never mixes with the
single-shower one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pytest import approx

import contract_check
from calosrv.query import density
from calosrv.stats import gaussian, histogram

REL = 1e-5

#: (d_min, d_max) windows around each population of the synthetic file, and its size.
D_WINDOWS = (
    ((0.0, 50.0), 1), ((50.0, 100.0), 2), ((100.0, 150.0), 7), ((150.0, 200.0), 8),
    ((200.0, 250.0), 14), ((250.0, 300.0), 15), ((300.0, 350.0), 19), ((350.0, 400.0), 20),
    ((580.0, 620.0), 200),
)

SHOWERS = (("a", "e_a_true_abs", "e1", "e1_bin"), ("b", "e_b_true_abs", "e2", "e2_bin"))


def _get(client, **params):
    reply = client.get("/api/response", params=params)
    assert reply.status_code == 200, reply.text
    return reply.json()


def _events(client, where="TRUE"):
    with client.app.state.database.read_cursor() as con:
        return con.execute(f'SELECT * FROM "event_experiment_baseline" WHERE {where}').fetchdf()


def _t(n: int) -> float:
    return gaussian.t_quantile_975(n - 1)


def _ratio_se(num: np.ndarray, den: np.ndarray) -> float:
    n = num.size
    r = num.sum() / den.sum()
    return math.sqrt(((num - r * den) ** 2).sum() / (n * (n - 1) * (den.sum() / n) ** 2))


def test_the_synthetic_file_has_every_population(synthetic_client):
    ev = _events(synthetic_client)
    assert len(ev) == 286
    for (lo, hi), n in D_WINDOWS:
        assert int(ev["d"].between(lo, hi).sum()) == n


def test_the_default_response_is_contract_valid_and_small(synthetic_client):
    reply = synthetic_client.get("/api/response")
    assert reply.status_code == 200
    body = reply.json()
    contract_check.check(body, "response")
    assert len(reply.content) < density.RESPONSE_LIMIT
    # Two showers, two series in each card; the resolution has two series per shower.
    assert [s["key"] for s in body["b1"]["series"]] == ["a", "b"]
    assert [s["key"] for s in body["b2"]["series"]] == ["a", "b"]
    assert [(s["key"], s["kind"]) for s in body["resolution"]["series"]] == [
        ("a", "calibrated_energy"), ("a", "response_ratio"),
        ("b", "calibrated_energy"), ("b", "response_ratio")]


@pytest.mark.parametrize("key,dep_col,p_col,bin_col", SHOWERS)
def test_each_shower_is_its_own_series_on_its_own_momentum_and_bins(
        synthetic_client, key, dep_col, p_col, bin_col):
    ev = _events(synthetic_client)
    body = _get(synthetic_client)
    p, dep = ev[p_col].to_numpy(float), ev[dep_col].to_numpy(float)
    f = 100.0 * dep / p
    n = f.size

    cal = body["calibration"][key]
    assert cal["n"] == n and cal["c"] == approx(p.sum() / dep.sum(), rel=REL)
    se = _ratio_se(p, dep)
    assert cal["se"] == approx(se, rel=1e-4)
    assert cal["ci95"] == approx([cal["c"] - _t(n) * se, cal["c"] + _t(n) * se], rel=1e-4)

    b1 = next(s for s in body["b1"]["series"] if s["key"] == key)
    assert b1["n"] == n and b1["fit"]["mu"] == approx(f.mean(), rel=REL)
    assert b1["fit"]["sigma"] == approx(f.std(ddof=1), rel=REL)
    assert b1["reference"]["value"] == approx(100.0 * dep.sum() / p.sum(), rel=REL)
    assert b1["markers"]["mu"] != approx(b1["reference"]["value"], rel=1e-5)

    series = next(s for s in body["b2"]["series"] if s["key"] == key)
    assert [b["bin"] for b in series["bins"]] == sorted(ev[bin_col].unique().tolist())
    for b in series["bins"]:
        sel = ev[ev[bin_col] == b["bin"]]
        sp, sd = sel[p_col].to_numpy(float), sel[dep_col].to_numpy(float)
        sf = 100.0 * sd / sp
        assert b["n"] == sf.size and b["p_mean"] == approx(sp.mean(), rel=REL)
        assert b["mean"] == approx(sf.mean(), rel=REL)
        assert b["weak"] is (sf.size < 20)
        if sf.size >= 2:
            half = _t(sf.size) * sf.std(ddof=1) / math.sqrt(sf.size)
            assert b["ci95"] == approx([sf.mean() - half, sf.mean() + half], rel=1e-4)


def test_the_two_showers_fill_their_bins_differently(synthetic_client):
    """Shower B is binned by e2_bin, never by shower A's: the populations per bin differ."""
    ev = _events(synthetic_client)
    body = _get(synthetic_client)
    sizes = {s["key"]: [b["n"] for b in s["bins"]] for s in body["b2"]["series"]}
    assert sizes["a"] != sizes["b"]
    assert sizes["a"] == ev.groupby("e1_bin").size().tolist()
    assert sizes["b"] == ev.groupby("e2_bin").size().tolist()


@pytest.mark.parametrize("key,dep_col,p_col,bin_col", SHOWERS)
def test_resolution_uses_one_constant_per_shower_over_the_selection(
        synthetic_client, key, dep_col, p_col, bin_col):
    ev = _events(synthetic_client)
    body = _get(synthetic_client)
    c = ev[p_col].sum() / ev[dep_col].sum()
    series = next(s for s in body["resolution"]["series"]
                  if s["key"] == key and s["kind"] == "calibrated_energy")
    for b in series["bins"]:
        sel = ev[ev[bin_col] == b["bin"]]
        values = c * sel[dep_col].to_numpy(float)
        assert b["mu"] == approx(values.mean(), rel=REL)
        if values.size >= 2:
            r = values.std(ddof=1) / values.mean()
            assert b["value"] == approx(100.0 * r, rel=REL)


@pytest.mark.parametrize("params", [
    {"e1_min": 6.0, "e1_max": 12.0},
    {"e2_min": 3.0, "e2_max": 9.0},
    {"d_min": 100.0, "d_max": 400.0},
    {"e1_min": 4.0, "e2_max": 14.0, "d_min": 50.0},
])
def test_every_filter_axis_selects_the_events_numpy_selects(synthetic_client, params):
    clauses = []
    for axis, col in (("e1", "e1"), ("e2", "e2"), ("d", "d")):
        if f"{axis}_min" in params:
            clauses.append(f"{col} >= {params[f'{axis}_min']}")
        if f"{axis}_max" in params:
            clauses.append(f"{col} <= {params[f'{axis}_max']}")
    ev = _events(synthetic_client, " AND ".join(clauses))
    body = _get(synthetic_client, **params)
    assert len(ev) > 0
    for key, dep_col, p_col, _ in SHOWERS:
        series = next(s for s in body["b1"]["series"] if s["key"] == key)
        assert series["n"] == len(ev)
        assert body["calibration"][key]["c"] == approx(
            ev[p_col].sum() / ev[dep_col].sum(), rel=REL)


@pytest.mark.parametrize("window,n", D_WINDOWS)
def test_the_low_n_ladder_of_both_cards_follows_the_population(synthetic_client, window, n):
    body = _get(synthetic_client, d_min=window[0], d_max=window[1])
    contract_check.check(body, "response")
    for series in body["b1"]["series"]:
        assert series["n"] == n
        assert series["draw"] == ("histogram" if n >= histogram.MIN_HISTOGRAM_SAMPLES else "strip")
        assert (series["markers"] is None) is (n < 2)
        assert (series["fit"]["non_gaussian"] is None) is (n < gaussian.MIN_ROBUST_SAMPLES)
    axis = body["b1"]["axis"]
    assert axis["provisional"] is (n < 20)
    assert (axis["bins"] > 0) is (n >= 15)
    if n >= 15:
        assert axis["bins"] == histogram.adaptive_bins(n)
    # B2: bins hold fewer events still; the provisional flag follows whether any bin is robust.
    populations = [b["n"] for s in body["b2"]["series"] for b in s["bins"]]
    assert sum(b["n"] for b in body["b2"]["series"][0]["bins"]) == n
    assert body["b2"]["y"]["provisional"] is (max(populations) < 20)
    assert body["resolution"]["y"]["provisional"] is (max(populations) < 20) or max(populations) < 2


def test_the_largest_synthetic_response_stays_far_under_the_contract(synthetic_client):
    """Two showers, every populated momentum bin of each: the biggest body this fixture makes."""
    reply = synthetic_client.get("/api/response", params={"bins": 120})
    assert reply.status_code == 200
    assert len(reply.content) < 0.6 * density.RESPONSE_LIMIT
    body = reply.json()
    assert not any("significant figures" in w for w in body["meta"]["warnings"])


def test_the_response_calibration_is_the_energy_panels(synthetic_client):
    """The two panels fit one ratio of sums over the showers present (an absent one:
    tests/test_energy_momentum.py, on an in-memory table the fixtures cannot make)."""
    window = {"d_min": 100.0, "d_max": 900.0}
    events = _events(synthetic_client, "d BETWEEN 100 AND 900")
    assert ((events.n_a_rows == 0) | (events.n_b_rows == 0)).sum() == 0
    response = _get(synthetic_client, **window)
    energy = synthetic_client.get("/api/energy-distribution", params=window).json()["calibration"]
    assert response["calibration"]["a"]["c"] == approx(energy["c_a"], rel=1e-5)
    assert response["calibration"]["b"]["c"] == approx(energy["c_b"], rel=1e-5)
    label = response["calibration"]["a"]["label"]
    assert "the calibration the energy panel applies" in label
    assert "A shower with no deposit is left out of both sums" in label
