"""``GET /api/resolution-scaling``: σ/E against 1/√E on every kind, against NumPy over the event table.

Booted against ``synthetic_client`` (two showers, 286 events in bins 2–17),
``single_client`` (single-shower hits: 287 events in bins of 1, 2, 7, 8, 14,
15, 19, 20 and 200 events, plus one single-hit event; and the 59-column
aggregate of the same events, unpaired) and ``xgb_client`` (an electron
aggregate analysed with in-test XGBoost models). The fixtures test shapes,
gates and arithmetic, never physics: every expected σ/E below is recomputed
from the event table with NumPy, by the formula written out here.
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest import approx

import contract_check
from conftest import SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE, XGB_SOURCE, xgb_table
from calosrv.db import ddl, registry
from calosrv.modelruns import store
from calosrv.query import density, response, showers
from calosrv.query import resolution_scaling as rs
from calosrv.text import signed_hyphens

ROUTE = "/api/resolution-scaling"
REL = 1e-5      # six significant figures


def _get(client, **params):
    reply = client.get(ROUTE, params=params)
    assert reply.status_code == 200, reply.text
    body = reply.json()
    contract_check.check(body, "resolution_scaling")
    return body


def _events(client, table, where="TRUE"):
    with client.app.state.database.read_cursor() as con:
        return con.execute(f'SELECT * FROM "event_{table}" WHERE {where}').fetchdf()


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _common(body):
    """What holds on every kind: the axes, the gates, the typography and the size."""
    axis = body["axis"]
    assert axis["y"]["zero_based"] and axis["y"]["lo"] == 0.0
    assert axis["x"] == {**axis["x"], "min": 0.0, "max": rs.X_MAX, "inverse": True}
    assert [t["e_gev"] for t in axis["top"]["ticks"]] == [*rs.ENERGY_TICKS_GEV, None]
    for tick in axis["top"]["ticks"][:-1]:
        assert tick["x"] == approx(1 / np.sqrt(tick["e_gev"]), rel=REL)
    assert body["gates"] == {"report_n": 2, "whisker_n": 8, "fit_n": 20, "e_min_gev": 4.0,
                             "anchor_low_gev": 5.0, "n_anchors": 3}
    bad = [s for s in _strings(body) if signed_hyphens(s)]
    assert not bad, bad[:3]
    off = {o["series"]: o for o in body["off_axis"]}
    for s in body["series"]:
        assert s["label"] == f"{s['shower_label']} · {s['estimator_label']}"
        gone = [w for w in s["windows"] if w["off_axis"]]
        for w in s["windows"]:
            assert w["off_axis"] == (w["p_lo"] < rs.E_MIN_GEV)
            assert w["eligible"] == (w["n"] >= 20 and not w["off_axis"])
            assert w["whisker"] == (w["n"] >= 8)
            assert (w["value"] is None) == (w["n"] < 2)
        if gone:
            assert off[s["key"]]["bins"] == [w["bin"] for w in gone]
            assert off[s["key"]]["n"] == sum(w["n"] for w in gone)
        for mode in s["fits"].values():
            for form in ("affine", "pinned"):
                fit = mode[form]
                if fit is not None:
                    assert len(fit["curve"]) == rs.BAND_POINTS
                    assert fit["curve"][0][0] == 0.0 and fit["curve"][-1][0] == rs.X_MAX
                    assert fit["provisional"] == mode["provisional"]
            if mode["quadrature"] is not None:
                assert mode["quadrature"]["curve"] is None


def _check_detector_window(series, dep, p, bins):
    """Each window's σ/E is 100 s(R)/R̄ of R = E_dep / p (c cancels), x the mean of 1/√p."""
    for w in series["windows"]:
        mask = bins == w["bin"]
        ratio, pk = dep[mask] / p[mask], p[mask]
        assert w["n"] == int(mask.sum())
        assert w["x"] == approx(float(np.mean(1 / np.sqrt(pk))), rel=REL)
        if w["n"] >= 2:
            assert w["value"] == approx(100 * ratio.std(ddof=1) / ratio.mean(), rel=REL)


# ------------------------------------------------------------ two showers --


def test_two_showers_draw_the_detector_and_the_energy_network(synthetic_client):
    body = _get(synthetic_client)
    _common(body)
    assert body["kind"] == ddl.KIND_TWO_SHOWER
    assert body["model"] == {"available": True, "source": "network", "frame": "absolute",
                             "label": "Energy network · absolute frame", "reason": None,
                             "split": None}
    assert [s["key"] for s in body["series"]] == ["detector:a", "network:a", "detector:b",
                                                  "network:b"]
    assert {s["colour_slot"] for s in body["series"]} == {"detector", "absolute"}
    assert [s["shower_label"] for s in body["series"]] == ["Shower A", "Shower A", "Shower B",
                                                           "Shower B"]
    # Bins 2–17: the anchors of the contract's second example.
    assert body["anchors"]["nominal_bins"] == [5, 9, 17]
    assert body["anchors"]["labels"] == ["5–6 GeV", "9–10 GeV", "17–18 GeV"]
    assert body["meta"]["coord_system"] == "lab" and body["meta"]["coord_system_applies"]
    # Bins 2 and 3 lie below 4 GeV: off the axis on every series.
    assert {o["series"] for o in body["off_axis"]} == {s["key"] for s in body["series"]}
    assert all(o["bins"] == [2, 3] for o in body["off_axis"])

    # The default selection leaves out the events with no A–B separation.
    events = _events(synthetic_client, body["meta"]["table_name"], "d IS NOT NULL")
    a = events[events["n_a_rows"] > 0]
    dep_col = ddl.seg_stat_column("e_a_true", "lab")
    series = {s["key"]: s for s in body["series"]}
    _check_detector_window(series["detector:a"], a[dep_col].to_numpy(float),
                           a["e1"].to_numpy(float), a["e1_bin"].to_numpy(float))
    # The network: R = en_pred / en_true, windows by the shower's own bin.
    pred, true = a["en_pred_a_abs"].to_numpy(float), a["en_true_a"].to_numpy(float)
    for w in series["network:a"]["windows"]:
        mask = a["e1_bin"].to_numpy(float) == w["bin"]
        ratio = pred[mask] / true[mask]
        assert w["value"] == approx(100 * ratio.std(ddof=1) / ratio.mean(), rel=REL)
        assert w["bias"] == approx(100 * (ratio.mean() - 1), rel=REL, abs=1e-9)
    assert len(str(body).encode()) < density.RESPONSE_LIMIT


def test_coord_system_moves_only_the_network_series(synthetic_client):
    lab = _get(synthetic_client, coord_system="lab")
    local = _get(synthetic_client, coord_system="local")
    trans = _get(synthetic_client, coord_system="trans")
    assert local["model"]["frame"] == "local" and trans["model"]["frame"] == "trans"
    assert local["model"]["label"] == "Energy network · local frame"
    assert trans["model"]["label"] == "Energy network · per-shower translated frame"
    for body, slot in ((local, "local"), (trans, "trans")):
        net = [s for s in body["series"] if s["source"] == "network"]
        assert {s["colour_slot"] for s in net} == {slot}
        assert all(s["estimator_label"] == body["model"]["label"] for s in net)
    detector = [[s for s in b["series"] if s["source"] == "detector"] for b in (lab, local)]
    assert detector[0] == detector[1]
    assert lab["series"][1]["windows"] != local["series"][1]["windows"]
    assert local["meta"]["coord_system"] == "local"


@pytest.mark.parametrize("bad", ["canonical", "bogus"])
def test_an_invalid_coord_system_is_refused(synthetic_client, bad):
    reply = synthetic_client.get(ROUTE, params={"coord_system": bad})
    assert reply.status_code == 422
    assert "coord_system" in reply.text


# The booted clients share one DuckDB singleton, and each resets it when it boots: every
# test of one client runs before the next client's first test.



def test_the_budget_ladder_says_what_it_shortened(synthetic_client, monkeypatch):
    full = _get(synthetic_client)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1_000)
    body = _get(synthetic_client)
    warnings = " ".join(body["meta"]["warnings"])
    assert "significant figures" in warnings and "11 points" in warnings
    assert "served as it is" in warnings
    fit = body["series"][0]["fits"]["all"]["affine"]
    assert len(fit["curve"]) == 11
    assert body["series"][0]["windows"][0]["n"] == full["series"][0]["windows"][0]["n"]


# ------------------------------------------------------------- one shower --


def test_single_shower_hits_draw_the_detector_only_and_name_the_species(single_client):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE)
    _common(body)
    assert body["model"]["available"] is False and body["model"]["source"] is None
    assert "single-shower hit" in body["model"]["reason"]
    assert not body["meta"]["coord_system_applies"]
    assert "does not apply" in body["meta"]["coord_system_note"]
    (series,) = body["series"]
    assert series["key"] == "detector:a" and series["colour_slot"] == "detector"

    events = _events(single_client, SINGLE_HITS_TABLE, "n_hits > 0")
    # The share is of every selected event: one without a primary particle counts against the name.
    top = events["primary_type"].dropna().value_counts()
    share = top.iloc[0] / len(events)
    expected = (rs.SPECIES_CODES.get(top.index[0]) if share >= rs.DOMINANT_SHARE else None) or "Shower"
    assert series["shower_label"] == expected
    (named,) = [n for n in body["notes"] if "named" in n]
    assert f"of the {len(events):,} selected events" in named and f"{100 * share:.1f}%" in named
    untyped = int(events["primary_type"].isna().sum())
    assert (f"{untyped:,} of them have no primary particle" in named) == (untyped > 0)

    _check_detector_window(series, events["e_dep"].to_numpy(float), events["e1"].to_numpy(float),
                           events["e1_bin"].to_numpy(float))
    # 0–19 GeV: the contract's first example. Bins 5 (N = 15) and 19 (N = 19) are thin and
    # only bin 10 (N = 200) is eligible, so the anchor fit falls back to N ≥ 8, provisionally.
    assert body["anchors"]["nominal_bins"] == [5, 10, 19]
    anchors = series["fits"]["anchors"]
    assert anchors["points"] == [5, 10, 19] and anchors["fallback"] and anchors["provisional"]
    assert anchors["affine"]["provisional"] and "Provisional" in anchors["affine"]["note"]
    # Bin 10 sets the range, so it is not provisional.
    assert body["axis"]["y"]["provisional"] is False
    assert {o["series"]: o["bins"] for o in body["off_axis"]} == {"detector:a": [1, 2, 3]}


def test_a_selection_without_an_eligible_window_has_a_provisional_range(single_client):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE, e1_min=5.0, e1_max=9.99)
    _common(body)
    assert body["axis"]["y"]["provisional"] is True
    (series,) = body["series"]
    assert not any(w["eligible"] for w in series["windows"])
    assert all(m["affine"] is None for m in series["fits"].values())
    assert any("provisional" in n for n in body["notes"])
    # The anchors are the whole table's, whatever the selection.
    assert body["anchors"]["nominal_bins"] == [5, 10, 19]


def test_an_unpaired_aggregate_says_why_it_has_no_model(single_client):
    body = _get(single_client, table_name=SINGLE_EVENTS_TABLE)
    _common(body)
    assert body["kind"] == ddl.KIND_SINGLE_EVENTS
    model = body["model"]
    assert model["available"] is False and model["source"] is None
    assert "pair" in model["reason"]
    (series,) = body["series"]
    assert series["shower_label"] == "Shower"
    events = _events(single_client, SINGLE_EVENTS_TABLE, "n_hits > 0")
    _check_detector_window(series, events["e_dep"].to_numpy(float), events["e1"].to_numpy(float),
                           events["e1_bin"].to_numpy(float))


def test_xgboost_series_on_a_paired_aggregate(xgb_client):
    table = xgb_table(XGB_SOURCE)
    body = _get(xgb_client, table_name=table)
    _common(body)
    model = body["model"]
    assert model["available"] and model["source"] == "xgb" and model["frame"] is None
    assert model["label"] == rs.XGB_LABEL
    split = model["split"]
    assert split["n_selected"] == body["n_events"]
    assert split["n_validation"] + split["n_training_excluded"] == split["n_selected"]
    assert [s["key"] for s in body["series"]] == ["detector:a", "xgb:a"]
    detector, xgb = body["series"]
    assert xgb["colour_slot"] == "xgb" and detector["colour_slot"] == "detector"
    # The paired models are the electron's: the species word fixes the charge.
    assert detector["shower_label"] == xgb["shower_label"] == "Electron e⁻"
    assert xgb["n"] + xgb["n_missing"] + xgb["n_dropped"] == split["n_validation"]
    # The validation split is a fifth of a small table: few windows reach N = 20.
    assert xgb["n"] < detector["n"]
    assert any(n.startswith("The model series is the shipped XGBoost") for n in body["notes"])
    # R = pred_momentum / true_momentum over the validation rows, by the stored bin.
    with xgb_client.app.state.database.read_cursor() as con:
        record = registry.get_experiment(con, table)
        rows = store.read_holdout(con, record, "momentum", "TRUE", {})
    ok = np.isfinite(rows["pred_momentum"]) & (rows["true_momentum"] > 0)
    ratio = rows["pred_momentum"][ok] / rows["true_momentum"][ok]
    for w in xgb["windows"]:
        r = ratio[rows["bin"][ok] == w["bin"]]
        assert w["n"] == r.size
        if w["n"] >= 2:
            assert w["value"] == approx(100 * r.std(ddof=1) / r.mean(), rel=REL)


# ---------------------------------------------------------- the estimator --


def test_the_calibration_cancels_in_sigma_over_mu():
    """Scaling every deposit leaves σ/E unchanged: c rescales with it and cancels."""
    rng = np.random.default_rng(5)
    p = rng.uniform(4, 20, 3000)
    bins = np.floor(p)
    dep = 0.031 * p * (1 + (0.2 / np.sqrt(p)) * rng.standard_normal(p.size))
    columns = showers._SINGLE
    axis = rs.performance_bins.axis_from_ranges({k: (k + 0.01, k + 0.99) for k in range(4, 20)})
    values = []
    for scale in (1.0, 7.3):
        sample = response.Sample(columns, dep * scale, p, bins.astype(np.int64), p.size, 0, 0)
        c = response.calibrate(sample).c.value
        windows = rs.windows_of(c * sample.dep / sample.p, sample.p, sample.bin, axis)
        values.append([w.as_dict() for w in windows])
    for a, b in zip(*values):
        assert a["value"] == approx(b["value"], rel=1e-12)
        assert a["mean_r"] == approx(b["mean_r"], rel=1e-12)
        assert a["ci95"] == approx(b["ci95"], rel=1e-12)
