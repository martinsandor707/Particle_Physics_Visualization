"""``GET /api/response``: B1, B2 and the resolution, against NumPy over the event table.

Booted against ``single_client``, which holds the two-shower baseline (two
events), single-shower hits (287 events in 1 GeV bins of 1, 2, 7, 8, 14, 15, 19,
20 and 200 events, plus one single-hit event) and the 59-column aggregate (the
same events without the single-hit one). Every expectation below is recomputed
from the event table with NumPy, by formulas written out here rather than by the
helpers under test; the fixtures test shapes, gates and arithmetic, never physics.

The unit tests at the end build a miniature two-shower event table in memory, so
counts the booted fixtures cannot produce (dropped values, an absent shower, a
weak series beside a robust one, bins that disagree with their momenta) are
exercised through the same code.
"""

from __future__ import annotations

import math
import re

import duckdb
import numpy as np
import pandas as pd
import pytest
from pytest import approx

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from calosrv.db import ddl, registry, schemas
from calosrv.db.registry import STATUS_READY, ExperimentRecord
from calosrv.errors import ValidationError
from calosrv.query import density, filters, response, showers
from calosrv.stats import gaussian, histogram
from calosrv.text import signed_hyphens

REL = 1e-5      # six significant figures


def _get(client, table, **params):
    reply = client.get("/api/response", params={"table_name": table, **params})
    assert reply.status_code == 200, reply.text
    return reply.json()


def _events(client, table, where="TRUE"):
    with client.app.state.database.read_cursor() as con:
        return con.execute(f'SELECT * FROM "event_{table}" WHERE {where}').fetchdf()


def _t(n: int) -> float:
    return gaussian.t_quantile_975(n - 1)


def _ratio_se(num: np.ndarray, den: np.ndarray) -> float:
    """SE of sum(num) / sum(den), events as clusters, from the residuals: no expanded sums."""
    n = num.size
    r = num.sum() / den.sum()
    return math.sqrt(((num - r * den) ** 2).sum() / (n * (n - 1) * (den.sum() / n) ** 2))


def _strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def _bin_of(series, k):
    return next(b for b in series["bins"] if b["bin"] == k)


# ------------------------------------------------------------- contract --

@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE, BASELINE_TABLE])
def test_every_kind_serves_a_contract_valid_response_under_the_limit(single_client, table):
    reply = single_client.get("/api/response", params={"table_name": table})
    assert reply.status_code == 200, reply.text
    assert len(reply.content) < density.RESPONSE_LIMIT
    body = reply.json()
    contract_check.check(body, "response")
    assert body["unit"] == "%"
    assert body["meta"]["table_name"] == table
    assert body["kind"] == {
        SINGLE_HITS_TABLE: "single_shower_hits", SINGLE_EVENTS_TABLE: "single_shower_events",
        BASELINE_TABLE: "two_shower_hits"}[table]


def test_the_contract_catches_a_dropped_key(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE)
    del body["b2"]["whisker"]
    with pytest.raises(contract_check.ContractError, match="whisker"):
        contract_check.check(body, "response")
    body = _get(single_client, SINGLE_HITS_TABLE)
    del body["resolution"]["value_unit"]
    with pytest.raises(contract_check.ContractError, match="value_unit"):
        contract_check.check(body, "response")


# ---------------------------------------------------------- calibration --

@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_calibration_is_the_ratio_of_sums_over_the_whole_selection(single_client, table):
    ev = _events(single_client, table)
    p, dep = ev["e1"].to_numpy(float), ev["e_dep"].to_numpy(float)
    n = p.size
    c = p.sum() / dep.sum()
    se = _ratio_se(p, dep)
    cal = _get(single_client, table)["calibration"]["a"]
    assert cal["n"] == n
    assert cal["c"] == approx(c, rel=REL)
    assert cal["sampling_fraction_pct"] == approx(100.0 * dep.sum() / p.sum(), rel=REL)
    assert cal["se"] == approx(se, rel=1e-4)
    assert cal["ci95"] == approx([c - _t(n) * se, c + _t(n) * se], rel=1e-4)
    assert cal["method"] == "ratio_t"
    # Sum before divide is not the mean of the per-event ratios: that would be a per-event
    # normalisation, which forces every event onto its own truth.
    assert cal["c"] != approx(1.0 / np.mean(dep / p), rel=1e-4)


def test_calibration_is_fitted_per_shower_not_per_bin(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    body = _get(single_client, SINGLE_HITS_TABLE)
    c = body["calibration"]["a"]["c"]
    calibrated = next(s for s in body["resolution"]["series"] if s["kind"] == "calibrated_energy")
    for b in calibrated["bins"]:
        sel = ev[ev["e1_bin"] == b["bin"]]
        dep, p = sel["e_dep"].to_numpy(float), sel["e1"].to_numpy(float)
        assert b["mu"] == approx(c * dep.mean(), rel=REL)
        if b["n"] >= 20:
            # A constant fitted to the bin itself would make mu exactly the bin's mean momentum.
            assert abs(b["mu"] - p.mean()) > 1e-4 * p.mean()


# ------------------------------------------------------------------- B1 --

def test_b1_markers_are_the_mean_of_ratios_and_the_rule_is_the_ratio_of_sums(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    p, dep = ev["e1"].to_numpy(float), ev["e_dep"].to_numpy(float)
    f = 100.0 * dep / p
    n = f.size
    b1 = _get(single_client, SINGLE_HITS_TABLE)["b1"]
    s = b1["series"][0]

    assert s["markers"]["mu"] == approx(f.mean(), rel=REL)
    half = _t(n) * f.std(ddof=1) / math.sqrt(n)
    assert s["markers"]["ci95_lo"] == approx(f.mean() - half, rel=REL)
    assert s["markers"]["ci95_hi"] == approx(f.mean() + half, rel=REL)
    # The band is the sample SD, uncapped and sqrt(N) wider than the whisker.
    assert s["markers"]["dispersion_lo"] == approx(f.mean() - f.std(ddof=1), rel=REL)
    assert s["markers"]["dispersion_hi"] == approx(f.mean() + f.std(ddof=1), rel=REL)
    assert (s["markers"]["dispersion_hi"] - s["markers"]["mu"]) / half == approx(
        math.sqrt(n) / _t(n), rel=1e-4)

    assert b1["whisker"]["method"] == "t" and b1["whisker"]["level"] == 0.95
    assert "mean of the per-event sampling fractions" in b1["whisker"]["label"]
    assert "sample standard deviation" in b1["dispersion"] and "√N wider" in b1["dispersion"]

    ref = s["reference"]
    assert ref["value"] == approx(100.0 * dep.sum() / p.sum(), rel=REL)
    se = 100.0 * _ratio_se(dep, p)
    assert ref["ci95_lo"] == approx(ref["value"] - _t(n) * se, rel=1e-4)
    assert ref["ci95_hi"] == approx(ref["value"] + _t(n) * se, rel=1e-4)
    assert "Sum before divide" in ref["label"]
    # Two different numbers, and the response says so.
    assert ref["value"] != approx(s["markers"]["mu"], rel=1e-5)


def test_b1_two_estimators_differ_visibly_on_the_two_shower_baseline(single_client):
    ev = _events(single_client, BASELINE_TABLE)
    body = _get(single_client, BASELINE_TABLE)
    by_key = {s["key"]: s for s in body["b1"]["series"]}
    for key, dep_col, p_col in (("a", "e_a_true_abs", "e1"), ("b", "e_b_true_abs", "e2")):
        dep, p = ev[dep_col].to_numpy(float), ev[p_col].to_numpy(float)
        s = by_key[key]
        assert s["markers"]["mu"] == approx((100 * dep / p).mean(), rel=REL)
        assert s["reference"]["value"] == approx(100 * dep.sum() / p.sum(), rel=REL)
        assert abs(s["markers"]["mu"] - s["reference"]["value"]) > 0.1
    assert any("two different numbers" in n for n in body["notes"])
    assert any(n.startswith("B1, Shower A: mean of ratios") for n in body["notes"])


def test_b1_histogram_is_a_density_over_all_events_on_rice_bins(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    f = 100.0 * ev["e_dep"].to_numpy(float) / ev["e1"].to_numpy(float)
    body = _get(single_client, SINGLE_HITS_TABLE)
    axis, s = body["b1"]["axis"], body["b1"]["series"][0]

    assert s["draw"] == "histogram" and s["strip"] is None
    assert axis["bins"] == histogram.adaptive_bins(f.size)
    assert axis["lo"] == 0.0 and axis["hi"] > 0.0 and not axis["provisional"]
    assert len(axis["hist_centres"]) == axis["bins"] == len(s["histogram"]["density"])
    width = (axis["hi"] - axis["lo"]) / axis["bins"]
    expected, _ = np.histogram(f, bins=np.linspace(axis["lo"], axis["hi"], axis["bins"] + 1))
    assert np.array(s["histogram"]["density"]) == approx(expected / (f.size * width), rel=1e-4)
    # The area is the fraction of events inside the axis.
    inside = ((f >= axis["lo"]) & (f <= axis["hi"])).sum()
    assert sum(s["histogram"]["density"]) * width == approx(inside / f.size, rel=1e-4)
    assert s["histogram"]["n_in_range"] == inside
    assert s["fit"]["estimator"] == "moments" and "all events" in s["fit"]["moments_subset"]
    assert s["fit"]["sigma"] == approx(f.std(ddof=1), rel=REL)
    assert s["fit"]["sigma_population"] == approx(f.std(ddof=0), rel=REL)


@pytest.mark.parametrize("window,n,drawn", [
    ((3.0, 3.99), 1, "strip"),
    ((7.0, 7.99), 2, "strip"),
    ((12.0, 12.99), 7, "strip"),
    ((15.0, 15.99), 14, "strip"),
    ((5.0, 5.99), 15, "histogram"),
])
def test_b1_ladder_draws_events_below_15_and_a_histogram_from_15(single_client, window, n, drawn):
    body = _get(single_client, SINGLE_HITS_TABLE, e1_min=window[0], e1_max=window[1])
    s = body["b1"]["series"][0]
    assert s["n"] == n and s["draw"] == drawn
    if drawn == "strip":
        assert s["histogram"] is None and s["strip"]["n_shown"] == n
        assert s["strip"]["values"] == sorted(s["strip"]["values"])
        assert body["b1"]["axis"]["bins"] == 0 and body["b1"]["axis"]["hist_centres"] == []
        assert ("comb" in s["message"]) is (n > 1)
    else:
        assert s["strip"] is None and body["b1"]["axis"]["bins"] >= histogram.MIN_BINS
    if n == 1:
        assert s["markers"] is None and "single shower" in s["message"]
        assert s["fit"]["sigma"] is None and s["fit"]["estimator"] == "mean_only"
    else:
        assert s["markers"] is not None and s["fit"]["sigma"] is not None
    if n == 2:
        assert "1 d.o.f." in s["message"] and s["fit"]["estimator"] == "moments_1dof"
        # At N = 2 the mean's whisker is the t interval on one degree of freedom.
        half = s["markers"]["ci95_hi"] - s["markers"]["mu"]
        assert half / s["fit"]["mu_error"] == approx(12.706, rel=1e-3)


def test_b1_low_n_axis_is_provisional_and_a_robust_series_is_not(single_client):
    weak = _get(single_client, SINGLE_HITS_TABLE, e1_min=7.0, e1_max=7.99)["b1"]["axis"]
    assert weak["provisional"] is True and "Provisional" in weak["clipping"]["note"]
    robust = _get(single_client, SINGLE_HITS_TABLE)["b1"]["axis"]
    assert robust["provisional"] is False


def test_b1_clip_percentile_is_disclosed_and_counted_against_the_served_axis(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    f = 100.0 * ev["e_dep"].to_numpy(float) / ev["e1"].to_numpy(float)
    body = _get(single_client, SINGLE_HITS_TABLE, clip_high=51.0)
    axis = body["b1"]["axis"]
    clip = axis["clipping"]
    assert clip["high_percentile"] == 51.0 and clip["n_total"] == f.size
    assert clip["n_above"] == int((f > axis["hi"]).sum()) > 0
    assert clip["n_below"] == 0
    assert clip["n_outside"] == clip["n_above"]
    assert clip["fraction_outside"] == approx(clip["n_outside"] / f.size, rel=1e-4)
    assert "lie outside it and are excluded from the view but not from the statistics" in clip["note"]
    assert clip["note"] in body["meta"]["warnings"]
    # The statistics are untouched by the display clip.
    assert body["b1"]["series"][0]["fit"]["mu"] == approx(f.mean(), rel=REL)
    assert body["b1"]["series"][0]["histogram"]["n_above"] == clip["n_above"]


def test_b1_bins_parameter_sets_the_histogram(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE, bins=40)
    assert body["b1"]["axis"]["bins"] == 40
    assert len(body["b1"]["series"][0]["histogram"]["density"]) == 40


# ------------------------------------------------------------------- B2 --

def test_b2_per_bin_numbers_match_numpy(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    series = _get(single_client, SINGLE_HITS_TABLE)["b2"]["series"][0]
    served = [b["bin"] for b in series["bins"]]
    assert served == sorted(ev["e1_bin"].unique().tolist())
    for b in series["bins"]:
        sel = ev[ev["e1_bin"] == b["bin"]]
        p, dep = sel["e1"].to_numpy(float), sel["e_dep"].to_numpy(float)
        f = 100.0 * dep / p
        n = f.size
        assert b["n"] == n and b["label"] == f"{b['bin']}–{b['bin'] + 1} GeV"
        assert (b["lo"], b["hi"]) == (b["bin"], b["bin"] + 1)
        assert b["p_mean"] == approx(p.mean(), rel=REL)
        assert b["mean"] == approx(f.mean(), rel=REL)
        assert b["scaling_factor"] == approx(1.0 / (f.mean() / 100.0), rel=REL)
        assert b["weak"] is (n < 20)
        assert b["ratio_of_sums"]["value"] == approx(100.0 * dep.sum() / p.sum(), rel=REL)
        if n >= 2:
            assert b["p_sd"] == approx(p.std(ddof=1), rel=REL)
            assert b["sd"] == approx(f.std(ddof=1), rel=REL)
            assert b["se"] == approx(f.std(ddof=1) / math.sqrt(n), rel=REL)
            # The SD is quoted with its own SE, asymmetric chi-squared interval and bias factor.
            sd, df = f.std(ddof=1), n - 1
            assert b["sd_se"] == approx(sd / math.sqrt(2.0 * df), rel=REL)
            assert b["sd_ci95"] == approx(
                [sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=True)),
                 sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=False))], rel=1e-4)
            assert (b["c4"] == approx(gaussian.c4(n), rel=1e-5)) if n < 15 else b["c4"] is None
            se = 100.0 * _ratio_se(dep, p)
            assert b["ratio_of_sums"]["ci95"] == approx(
                [max(0.0, b["ratio_of_sums"]["value"] - _t(n) * se),
                 b["ratio_of_sums"]["value"] + _t(n) * se],
                rel=1e-4)
        else:
            assert b["sd"] is None and b["ci95"] is None and b["ratio_of_sums"]["ci95"] is None
            assert b["sd_se"] is None and b["sd_ci95"] is None and b["c4"] is None
            assert "single shower" in b["dof_note"]
        assert (b["dof_note"] == "1 d.o.f.") is (n == 2)


def test_b2_whisker_is_the_95_percent_t_interval_at_every_n(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE)
    assert body["b2"]["whisker"]["method"] == "t" and body["b2"]["whisker"]["level"] == 0.95
    seen = set()
    for b in body["b2"]["series"][0]["bins"]:
        if b["n"] < 2:
            continue
        half = (b["ci95"][1] - b["ci95"][0]) / 2.0
        # Never the SE at large N and the interval at small N: always t * s / sqrt(N).
        assert half == approx(_t(b["n"]) * b["sd"] / math.sqrt(b["n"]), rel=1e-4)
        assert half > 1.9 * b["se"]
        assert (b["ci95"][0] + b["ci95"][1]) / 2.0 == approx(b["mean"], rel=1e-4)
        seen.add(b["n"])
    assert {2, 200} <= seen          # one degree of freedom, and a large sample, on one axis
    assert "√N wider" in body["b2"]["dispersion"]


def test_b2_y_axis_is_zero_based_with_a_robust_top_and_counts_what_it_clips(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE)
    y = body["b2"]["y"]
    bins = body["b2"]["series"][0]["bins"]
    assert y["zero_based"] is True and y["lo"] == 0.0 and y["provisional"] is False
    robust_top = max(max(b["mean"] + b["sd"], b["ci95"][1]) for b in bins if b["n"] >= 20)
    assert y["hi"] >= robust_top and y["hi"] < robust_top * 1.5
    clipped = 0
    for b in bins:
        marks = [b["mean"]] + ([b["mean"] - b["sd"], b["mean"] + b["sd"], *b["ci95"]]
                               if b["sd"] is not None else [])
        clipped += any(m > y["hi"] or m < 0.0 for m in marks)
    assert y["n_clipped"] == clipped > 0
    # A weak bin whose whisker leaves the range does not rescale it.
    assert max(b["ci95"][1] for b in bins if b["ci95"]) > y["hi"]


def test_b2_with_no_robust_bin_is_provisional(single_client):
    body = _get(single_client, BASELINE_TABLE)
    assert body["b2"]["y"]["provisional"] is True
    assert body["resolution"]["y"]["provisional"] is True


# ----------------------------------------------------------- resolution --

def test_resolution_numbers_match_numpy_for_both_series(single_client):
    ev = _events(single_client, SINGLE_HITS_TABLE)
    body = _get(single_client, SINGLE_HITS_TABLE)
    c = body["calibration"]["a"]["c"]
    res = body["resolution"]
    kinds = {s["kind"]: s for s in res["series"]}
    assert set(kinds) == {"calibrated_energy", "response_ratio"}
    assert kinds["calibrated_energy"]["unit"] == "GeV" and kinds["response_ratio"]["unit"] == "%"
    assert res["value_unit"] == "%"
    assert res["whisker"]["method"] == "chi2_over_mu" and res["whisker"]["level"] == 0.95

    for kind, series in kinds.items():
        for b in series["bins"]:
            sel = ev[ev["e1_bin"] == b["bin"]]
            p, dep = sel["e1"].to_numpy(float), sel["e_dep"].to_numpy(float)
            values = c * dep if kind == "calibrated_energy" else 100.0 * dep / p
            n = values.size
            assert b["n"] == n and b["p_mean"] == approx(p.mean(), rel=REL)
            assert b["mu"] == approx(values.mean(), rel=REL)
            assert b["weak"] is (n < 20)
            if n < 2:
                assert all(b[k] is None for k in ("sigma", "sigma_se", "sigma_ci95", "value",
                                                 "ci95", "se_delta", "c4", "momentum_spread"))
                continue
            sigma, mu, df = values.std(ddof=1), values.mean(), n - 1
            r = sigma / mu
            se = r * math.sqrt(1.0 / (2.0 * df) + r * r / n)
            assert b["sigma"] == approx(sigma, rel=REL)
            assert b["sigma_se"] == approx(sigma / math.sqrt(2.0 * df), rel=REL)
            assert b["value"] == approx(100.0 * r, rel=REL)
            assert b["se_delta"] == approx(100.0 * se, rel=1e-4)
            # The chi-squared interval of sigma alone, in the series' own unit ...
            chi2 = [sigma * math.sqrt(df / gaussian.chi2_quantile(df, upper=True)),
                    sigma * math.sqrt(df / gaussian.chi2_quantile(df, upper=False))]
            assert b["sigma_ci95"] == approx(chi2, rel=1e-4)
            # ... and the whisker is that interval over mu: never negative, skewed up.
            assert b["ci95"] == approx([100.0 * chi2[0] / mu, 100.0 * chi2[1] / mu], rel=1e-4)
            assert 0.0 < b["ci95"][0] < b["value"] < b["ci95"][1]
            assert b["ci95"][1] - b["value"] > b["value"] - b["ci95"][0]
            assert b["momentum_spread"] == approx(100.0 * p.std(ddof=1) / p.mean(), rel=REL)
            assert (b["c4"] == approx(gaussian.c4(n), rel=1e-5)) if n < 15 else b["c4"] is None
            assert (b["non_gaussian"] is None) if n < 20 else isinstance(b["non_gaussian"], bool)


def test_response_ratio_resolution_does_not_depend_on_the_calibration(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE)
    b2 = {b["bin"]: b for b in body["b2"]["series"][0]["bins"]}
    ratio = next(s for s in body["resolution"]["series"] if s["kind"] == "response_ratio")
    for b in ratio["bins"]:
        # Same quantity as B2: the per-event sampling fraction, whatever c is.
        assert b["mu"] == approx(b2[b["bin"]]["mean"], rel=1e-5)
        if b["sigma"] is not None:
            assert b["value"] == approx(100.0 * b2[b["bin"]]["sd"] / b2[b["bin"]]["mean"], rel=1e-5)


def test_resolution_interval_at_two_events_is_one_degree_of_freedom(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE)
    for series in body["resolution"]["series"]:
        b = _bin_of(series, 7)                       # two events
        # One degree of freedom: sigma's 95% chi-squared range spans 0.446 to 31.9 times
        # the estimate, so the whisker runs from 0.446 to 31.9 times sigma/mu.
        assert b["ci95"][0] / b["value"] == approx(math.sqrt(1 / gaussian.chi2_quantile(1, upper=True)), rel=1e-3)
        assert b["ci95"][1] / b["value"] == approx(math.sqrt(1 / gaussian.chi2_quantile(1, upper=False)), rel=1e-3)
        assert b["c4"] == approx(0.797885, rel=1e-4) and b["weak"] is True


def test_resolution_y_axis_is_zero_based_and_robust(single_client):
    res = _get(single_client, SINGLE_HITS_TABLE)["resolution"]
    y = res["y"]
    bins = [b for s in res["series"] for b in s["bins"]]
    assert y["zero_based"] is True and y["lo"] == 0.0 and y["provisional"] is False
    assert y["hi"] >= max(max(b["value"], b["ci95"][1]) for b in bins if b["n"] >= 20)
    assert y["n_clipped"] == sum(
        1 for b in bins if b["value"] is not None and (b["ci95"][1] > y["hi"] or b["ci95"][0] < 0.0))


# ------------------------------------------------------ parts and showers --

def test_parts_select_the_cards_and_the_others_are_null(single_client):
    only = _get(single_client, SINGLE_HITS_TABLE, parts="b2")
    assert only["b1"] is None and only["resolution"] is None and only["b2"] is not None
    assert only["meta"]["parts"] == ["b2"]
    contract_check.check(only, "response")
    two = _get(single_client, SINGLE_HITS_TABLE, parts="resolution, b1")
    assert two["b2"] is None and two["b1"] is not None and two["resolution"] is not None
    assert two["meta"]["parts"] == ["b1", "resolution"]
    assert _get(single_client, SINGLE_HITS_TABLE, parts="")["b2"] is not None
    # The calibration travels with every request: it is what the resolution is built on.
    assert only["calibration"]["a"]["c"] is not None


def test_an_unknown_part_is_refused_naming_the_parameter(single_client):
    reply = single_client.get("/api/response", params={"table_name": SINGLE_HITS_TABLE,
                                                       "parts": "b1,b4"})
    assert reply.status_code == 422 and reply.json()["field"] == "parts"


def test_a_single_shower_experiment_has_one_series_and_refuses_shower_b(single_client):
    for table in (SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE):
        for choice in ("both", "a"):
            body = _get(single_client, table, shower=choice)
            assert [s["key"] for s in body["b1"]["series"]] == ["a"]
            assert [s["key"] for s in body["b2"]["series"]] == ["a"]
        reply = single_client.get("/api/response", params={"table_name": table, "shower": "b"})
        assert reply.status_code == 422
        assert reply.json()["field"] == "shower" and reply.json()["capability"] == "shower"
    reply = single_client.get("/api/response", params={"table_name": BASELINE_TABLE, "shower": "c"})
    assert reply.status_code == 422 and reply.json()["field"] == "shower"


def test_the_two_shower_baseline_returns_both_showers_as_separate_series(single_client):
    ev = _events(single_client, BASELINE_TABLE)
    body = _get(single_client, BASELINE_TABLE)
    assert [s["key"] for s in body["b1"]["series"]] == ["a", "b"]
    assert [s["label"] for s in body["b1"]["series"]] == ["Shower A", "Shower B"]
    assert set(body["calibration"]) == {"a", "b"}
    for key, dep_col, p_col in (("a", "e_a_true_abs", "e1"), ("b", "e_b_true_abs", "e2")):
        assert body["calibration"][key]["c"] == approx(
            ev[p_col].sum() / ev[dep_col].sum(), rel=REL)
    only_b = _get(single_client, BASELINE_TABLE, shower="b")
    assert [s["key"] for s in only_b["b1"]["series"]] == ["b"]
    assert set(only_b["calibration"]) == {"b"}


@pytest.mark.parametrize("params", [{"bins": 4}, {"bins": 501}, {"clip_low": 60.0},
                                    {"clip_high": 10.0}])
def test_out_of_range_parameters_are_refused(single_client, params):
    reply = single_client.get("/api/response", params={"table_name": SINGLE_HITS_TABLE, **params})
    assert reply.status_code == 422


def test_a_selection_the_kind_cannot_make_is_refused_naming_the_field(single_client):
    reply = single_client.get("/api/response", params={"table_name": SINGLE_HITS_TABLE,
                                                       "e2_min": 1.0})
    assert reply.status_code == 422 and reply.json()["field"] == "e2_min"


def test_an_empty_selection_is_served_and_says_so(single_client):
    body = _get(single_client, SINGLE_HITS_TABLE, e1_min=0.0, e1_max=0.5)
    contract_check.check(body, "response")
    assert body["b1"]["series"][0]["draw"] == "none" and body["b1"]["series"][0]["n"] == 0
    assert body["b2"]["series"][0]["bins"] == [] and body["resolution"]["series"] == []
    assert "No events match the current selection." in body["meta"]["warnings"]
    assert body["calibration"]["a"]["c"] is None


# ----------------------------------------------------- kind disclosures --

def test_the_aggregate_says_it_is_censored_and_not_balanced(single_client):
    body = _get(single_client, SINGLE_EVENTS_TABLE)
    note = next(n for n in body["notes"] if "single hit" in n)
    assert note.startswith(schemas.CENSORED_AGGREGATE_NOTICE)
    # The figures are this experiment's, measured, never the electron file's.
    ev = _events(single_client, SINGLE_EVENTS_TABLE)
    counts = ev["e1_bin"].value_counts()
    assert f"{counts.min():,} to {counts.max():,} events" in note and "not balanced" in note
    assert "biased high" in note and "249" not in note
    # The hit-level kinds keep every event and carry no such note.
    for table in (SINGLE_HITS_TABLE, BASELINE_TABLE):
        assert not any("not balanced" in n for n in _get(single_client, table)["notes"])


def test_the_aggregate_drops_the_single_hit_event_the_hit_file_keeps(single_client):
    hits = _get(single_client, SINGLE_HITS_TABLE)["b1"]["series"][0]["n"]
    events = _get(single_client, SINGLE_EVENTS_TABLE)["b1"]["series"][0]["n"]
    assert hits == events + 1


# --------------------------------------------------------- typography --

def test_negative_numbers_in_text_use_the_true_minus(single_client):
    for table in (SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE, BASELINE_TABLE):
        body = _get(single_client, table)
        for text in _strings(body):
            assert not signed_hyphens(text), text
    # And the numbers themselves are negative where the interval says so (N = 2).
    baseline = _get(single_client, BASELINE_TABLE)
    assert baseline["b1"]["series"][0]["markers"]["ci95_lo"] < 0


# --------------------------------------------------------------- budget --

def _served(client, **params):
    reply = client.get("/api/response", params={"table_name": SINGLE_HITS_TABLE, **params})
    assert reply.status_code == 200, reply.text
    return reply


def test_the_guard_coarsens_the_histogram_and_the_digits_and_says_so(single_client, monkeypatch):
    base = _served(single_client)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1)
    floor = _served(single_client)            # every step taken, and still over
    limit = (len(base.content) + len(floor.content)) // 2
    assert len(floor.content) < len(base.content)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)

    reply = _served(single_client)
    body = reply.json()
    assert len(reply.content) < limit
    assert body["b1"]["axis"]["bins"] < base.json()["b1"]["axis"]["bins"]
    assert len(body["b1"]["series"][0]["histogram"]["density"]) == body["b1"]["axis"]["bins"]
    note = next(w for w in body["meta"]["warnings"] if "significant figures" in w)
    assert "no statistic changed" in note
    stated = int(re.search(r"\(([\d,]+) bytes at full fidelity\)", note).group(1).replace(",", ""))
    assert abs(stated - len(base.content)) < 100      # timing digits move a response by a byte or two
    assert not any("served as it is" in w for w in body["meta"]["warnings"])
    contract_check.check(body, "response")
    # The statistics are the same ones, to the digits the guard kept.
    assert body["b1"]["series"][0]["fit"]["mu"] == approx(
        base.json()["b1"]["series"][0]["fit"]["mu"], rel=1e-3)
    assert body["calibration"]["a"]["c"] == approx(base.json()["calibration"]["a"]["c"], rel=1e-3)


def test_the_guard_says_so_when_it_cannot_reach_the_limit(single_client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    body = _served(single_client).json()
    assert any("still" in w and "served as it is" in w for w in body["meta"]["warnings"])


def test_the_guard_leaves_a_response_under_the_limit_alone(single_client):
    body = _served(single_client).json()
    assert not any("significant figures" in w for w in body["meta"]["warnings"])


# ----------------------------------------------------- unit: the fetch --

def _two_shower_record(table: str, n_events: int) -> ExperimentRecord:
    schema = schemas.HITS_ALL_MODELS
    return ExperimentRecord(
        table_name=table, status=STATUS_READY, schema_name=schema.name,
        schema_version=schema.version, derived_version=schemas.DERIVED_VERSION[schema.kind],
        n_events=n_events, e1_min=0.0, e1_max=100.0, e2_min=0.0, e2_max=100.0,
        d_min=0.0, d_max=1e6)


def _mini(rows: list[dict]) -> tuple[duckdb.DuckDBPyConnection, ExperimentRecord]:
    """An in-memory two-shower event table with just the columns the response reads."""
    frame = pd.DataFrame(rows)
    con = duckdb.connect()
    con.execute('CREATE TABLE "event_mini" AS SELECT * FROM frame')
    return con, _two_shower_record("mini", len(rows))


def _row(e1, dep_a, e2=None, dep_b=None, n_b=3, n_a=3, d=300.0, k1=None, k2=None):
    e2 = e1 if e2 is None else e2
    return {
        "e1": float(e1), "e2": float(e2), "d": float(d),
        "e1_bin": int(e1) if k1 is None else k1, "e2_bin": int(e2) if k2 is None else k2,
        "e_a_true_abs": dep_a, "e_b_true_abs": dep_a if dep_b is None else dep_b,
        "n_a_rows": n_a, "n_b_rows": n_b, "n_ab_rows": 0,
    }


def test_fetch_counts_dropped_and_absent_values_apart():
    rows = [_row(2.5, 0.075), _row(3.5, 0.105), _row(4.5, 0.135)]
    rows += [
        _row(5.5, float("nan")),                      # a deposit that is not finite
        _row(6.5, float("inf")),
        _row(7.5, -0.01),                             # an unphysical negative deposit
        _row(0.0, 0.05),                              # a momentum that is not positive
        _row(8.5, 0.2, n_b=0),                        # shower B absent: not a dropped value
    ]
    con, record = _mini(rows)
    con.execute('UPDATE "event_mini" SET e_a_true_abs = NULL WHERE e1 = 3.5')   # a NULL deposit
    spec = filters.build(record)
    a, b = response.fetch(con, record, spec, showers.of(record, "both"))

    assert (a.n_selected, a.n, a.n_absent, a.n_dropped) == (8, 3, 0, 5)
    order = np.argsort(a.p)
    assert a.p[order].tolist() == [2.5, 4.5, 8.5] and a.dep[order].tolist() == [0.075, 0.135, 0.2]
    assert a.fraction[order] == approx([3.0, 3.0, 100 * 0.2 / 8.5])
    # Shower B shares the deposit column values in this table, so it drops the same bad rows,
    # and has one event with no hit rows at all.
    assert (b.n_selected, b.n_absent) == (8, 1)
    assert b.n_dropped == 4 and b.n == 3


def test_dropped_and_absent_events_are_disclosed_in_the_payload():
    rows = [_row(2.5, 0.075), _row(3.5, 0.105), _row(4.5, 0.135),
            _row(5.5, float("nan")), _row(8.5, 0.2, n_b=0)]
    con, record = _mini(rows)
    result = response.compute(con, record, filters.build(record), showers.of(record, "both"))
    warnings = result.warnings()
    assert any(w.startswith("Shower A: 1 event was dropped") and "never zero-filled" in w
               for w in warnings)
    assert any(w.startswith("Shower B: 1 selected event holds no hit rows") for w in warnings)
    series = {s["key"]: s for s in result.as_dict()["b1"]["series"]}
    assert (series["a"]["n"], series["a"]["n_dropped"], series["a"]["n_absent"]) == (4, 1, 0)
    assert (series["b"]["n"], series["b"]["n_dropped"], series["b"]["n_absent"]) == (3, 1, 1)


def test_a_weak_series_never_sets_the_b1_range_but_is_counted_when_it_overflows():
    # Shower A is in all 60 events at ~3%; shower B in the first 10 only, one of them at 30%.
    rows = []
    for i in range(60):
        p = 2.0 + 0.25 * i
        dep_a = 0.03 * p * (1.0 + 0.05 * math.sin(i))
        row = _row(p, dep_a, n_b=3 if i < 10 else 0)
        if i == 9:
            row["e_b_true_abs"] = 0.3 * row["e2"]
        rows.append(row)
    con, record = _mini(rows)
    result = response.compute(con, record, filters.build(record), showers.of(record, "both"),
                              response.Request(parts=("b1",)))
    body = result.as_dict()
    a, b = body["b1"]["series"]
    assert (a["n"], b["n"], b["n_absent"]) == (60, 10, 50)
    axis = body["b1"]["axis"]
    # The range comes from the robust series alone, so the outlier cannot stretch it ...
    assert axis["provisional"] is False and 3.0 < axis["hi"] < 4.0
    # ... it is counted as outside, still in the weak series' strip with its true value ...
    assert axis["clipping"]["n_above"] == 1 and axis["clipping"]["n_total"] == 70
    assert b["draw"] == "strip" and max(b["strip"]["values"]) == approx(30.0, rel=1e-4)
    # ... and the weak series' own moments are taken over all ten events, outlier included.
    assert b["fit"]["mu"] > 5.0 > a["fit"]["mu"]
    # The summary marks the axis cuts are counted and named too, not only the events: shower B's
    # mean (above 5%) and its band leave an axis that tops out below 4%.
    assert axis["n_clipped_marks"] >= 2
    clipped = {c["key"]: c["marks"] for c in axis["clipped_marks"]}
    assert "b" not in clipped.get("a", []) and "mean" in clipped["b"]
    assert any("summary mark" in n and "clipped, not rescaled" in n for n in body["notes"])


def test_events_with_an_undefined_separation_are_counted_when_the_selection_leaves_them_out():
    con, record = _mini([_row(2.5 + i, 0.03 * (2.5 + i)) for i in range(4)])
    record.n_events_no_d = 7
    record.n_events = 400
    left_out = response.compute(con, record, filters.build(record), showers.of(record, "both"))
    note = next(n for n in left_out.as_dict()["notes"] if "no A–B separation" in n)
    assert note.startswith("7 of the experiment's 400 events have no shower A hits")
    assert "unless include_undefined_d is set" in note
    # Admitted by the request, they are not left out and nothing is said.
    admitted = response.compute(con, record, filters.build(record, include_undefined_d=True),
                                showers.of(record, "both"))
    assert not any("no A–B separation" in n for n in admitted.as_dict()["notes"])


def test_a_shower_absent_from_every_event_has_no_series_constant_or_resolution():
    rows = [_row(2.5 + i, 0.03 * (2.5 + i), n_b=0) for i in range(4)]
    con, record = _mini(rows)
    body = response.compute(con, record, filters.build(record), showers.of(record, "both")).as_dict()
    contract_check.check({**body, "meta": {}, "filter": filters.build(record).as_dict()}, "response")
    series = {s["key"]: s for s in body["b1"]["series"]}
    assert (series["b"]["n"], series["b"]["n_absent"], series["b"]["draw"]) == (0, 4, "none")
    assert body["calibration"]["b"]["c"] is None and body["calibration"]["b"]["n"] == 0
    assert body["calibration"]["a"]["c"] == approx(1.0 / 0.03, rel=1e-5)
    assert [s["bins"] for s in body["b2"]["series"] if s["key"] == "b"] == [[]]
    assert {s["key"] for s in body["resolution"]["series"]} == {"a"}


def test_a_series_of_identical_fractions_is_a_measured_zero_width_not_a_density():
    # dep = p / 32 makes the fraction exactly 3.125% in binary floating point, not nearly.
    rows = [_row(2.0 + 0.5 * i, (2.0 + 0.5 * i) / 32.0) for i in range(24)]
    con, record = _mini(rows)
    body = response.compute(con, record, filters.build(record), showers.of(record, "a"),
                            response.Request(parts=("b1",))).as_dict()
    s = body["b1"]["series"][0]
    assert s["n"] == 24 and s["draw"] == "strip" and s["histogram"] is None
    assert s["fit"]["estimator"] == "degenerate" and s["fit"]["sigma"] == approx(0.0, abs=1e-9)
    assert "delta is not a density" in s["message"]
    assert body["b1"]["axis"]["bins"] == 0 and body["b1"]["axis"]["hist_centres"] == []
    assert s["markers"]["mu"] == approx(3.125, rel=1e-6)


def test_the_b2_and_resolution_y_axes_are_empty_but_valid_without_any_bin():
    rows = [_row(2.5, 0.075, n_a=0, n_b=0)]
    con, record = _mini(rows)
    body = response.compute(con, record, filters.build(record), showers.of(record, "both")).as_dict()
    for card in ("b2", "resolution"):
        y = body[card]["y"]
        assert y["zero_based"] is True and y["lo"] == 0.0 and y["hi"] > 0.0
        assert y["provisional"] is True and y["n_clipped"] == 0


def test_bins_that_disagree_with_their_momenta_are_labelled_by_number():
    rows = [_row(3.2, 0.1), _row(3.4, 0.1), _row(4.1, 0.1), _row(4.2, 0.1)]
    rows[2]["e1_bin"] = 3                       # the producer's bin says 3, the momentum says 4
    con, record = _mini(rows)
    result = response.compute(con, record, filters.build(record), showers.of(record, "a"),
                              response.Request(parts=("b2",)))
    body = result.as_dict()
    labels = [b["label"] for b in body["b2"]["series"][0]["bins"]]
    assert labels[0].startswith("bin 3 (p 3.2") and labels[1] == "4–5 GeV"
    assert any("disagrees with the momenta in bin 3" in n for n in body["notes"])


def test_more_bins_than_the_table_can_label_is_refused_as_a_table_problem():
    rows = [_row(k + 0.5, 0.05) for k in range(30)]
    con, record = _mini(rows)
    with pytest.raises(ValidationError) as error:
        response.compute(con, record, filters.build(record), showers.of(record, "a"))
    assert error.value.extra["field"] == "table_name"


def test_parse_parts_is_canonical_and_deduplicated():
    assert response.parse_parts(None) == response.PARTS
    assert response.parse_parts("resolution,b1,b1") == ("b1", "resolution")
    assert response.parse_parts(" B2 ") == ("b2",)
    assert set(response.GATES.values()) == {"response-b1", "response-b2", "response-res"}


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE, BASELINE_TABLE])
def test_event_columns_the_query_reads_exist_in_the_ingested_tables(single_client, table):
    with single_client.app.state.database.read_cursor() as con:
        live = {row[0] for row in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [f"event_{table}"]).fetchall()}
        record = registry.require_ready(con, table)
    for s in showers.of(record, "both"):
        for name in (s.momentum, s.momentum_bin, s.deposit):
            assert name in live, (table, name)
    assert {"e1", "e1_bin"} <= live


def test_event_columns_the_query_reads_exist_for_every_kind():
    """The names come from showers.py; each must be a column of its kind's event table."""
    expected = {
        ddl.KIND_TWO_SHOWER: {name for name, _ in ddl.EVENT_COLUMNS_V2},
        ddl.KIND_SINGLE_HITS: {name for name, _ in ddl.EVENT_SINGLE_COLUMNS},
        ddl.KIND_SINGLE_EVENTS: {name for name, _ in ddl.EVENT_FEATURE_COLUMNS},
    }
    for kind, columns in expected.items():
        schema = schemas.of_kind(kind)
        record = ExperimentRecord(table_name="x", status=STATUS_READY, schema_name=schema.name,
                                  schema_version=schema.version)
        for s in showers.of(record, "both"):
            for name in (s.momentum, s.momentum_bin, s.deposit):
                assert name in columns, (kind, name)


def test_a_provisional_b1_range_that_takes_percentiles_says_so_and_counts_what_lies_outside():
    # Two showers of 19 events each: no series reaches N = 20, but 38 values pool, so the
    # percentile cut applies and the one 30% event lies beyond the range.
    rows = []
    for i in range(19):
        p = 2.0 + 0.25 * i
        rows.append(_row(p, 0.03 * p * (1.0 + 0.02 * math.sin(i)),
                         dep_b=(0.3 * p if i == 9 else 0.03 * p * (1.0 + 0.02 * math.cos(i)))))
    con, record = _mini(rows)
    result = response.compute(con, record, filters.build(record), showers.of(record, "both"),
                              response.Request(parts=("b1",)))
    clipping = result.as_dict()["b1"]["axis"]["clipping"]
    assert result.b1_range.provisional and clipping["n_total"] == 38 and clipping["n_outside"] == 1
    assert "Provisional range" in clipping["note"] and "percentile" in clipping["note"]
    assert "spans the data" not in clipping["note"]
    assert "1 of 38 values" in clipping["note"]
    assert any("1 of 38 values" in w for w in result.warnings())


def test_the_b1_note_names_only_the_upper_percentile_because_the_axis_starts_at_zero():
    rows = [_row(2.0 + 0.25 * i, 0.03 * (2.0 + 0.25 * i) * (1.0 + 0.05 * math.sin(i)))
            for i in range(60)]
    con, record = _mini(rows)
    result = response.compute(con, record, filters.build(record), showers.of(record, "both"),
                              response.Request(parts=("b1",), clip_low=40.0, clip_high=60.0))
    note = result.as_dict()["b1"]["axis"]["clipping"]["note"]
    assert "zero-based" in note and "60th percentile" in note and "40" not in note


def test_ratio_intervals_of_non_negative_sums_are_clipped_at_zero():
    # Two events at very different fractions: the delta-method interval of the ratio of sums
    # would run far below zero, quoting a negative calibration constant.
    dep, p = np.array([0.02, 0.9]), np.array([10.0, 10.0])
    for num, den in ((p, dep), (dep, p)):
        estimate = response._ratio(num, den)
        assert estimate.interval.lo == 0.0 and estimate.interval.hi > estimate.value
    cal = response._calibration_block(response.Calibration(2, response._ratio(p, dep),
                                                           response._ratio(dep, p)))
    assert cal["ci95"][0] == 0.0 and "clipped at zero" in cal["label"]


def test_resolution_bins_carry_the_one_degree_of_freedom_label_at_n_two():
    rows = [_row(2.4, 0.07), _row(2.6, 0.081), _row(3.5, 0.1), _row(3.6, 0.11), _row(3.7, 0.105)]
    con, record = _mini(rows)
    body = response.compute(con, record, filters.build(record), showers.of(record, "both"),
                            response.Request(parts=("resolution",))).as_dict()
    bins = {(s["key"], b["bin"]): b for s in body["resolution"]["series"] for b in s["bins"]}
    assert bins[("a", 2)]["n"] == 2 and bins[("a", 2)]["dof_note"] == "1 d.o.f."
    assert bins[("a", 3)]["n"] == 3 and bins[("a", 3)]["dof_note"] is None
