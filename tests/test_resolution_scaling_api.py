"""``GET /api/resolution-scaling``: σ/E against 1/√E on every kind, against NumPy over the event table.

Booted against ``synthetic_client`` (two showers, 286 events in bins 2–17),
``single_client`` (single-shower hits: 287 events in bins of 1, 2, 7, 8, 14,
15, 19, 20 and 200 events, plus one single-hit event; and the 59-column
aggregate of the same events, unpaired) and ``xgb_client`` (an electron
aggregate analysed with in-test XGBoost models). The fixtures test shapes,
gates and arithmetic, never physics: every expected σ/E below is recomputed
from the event table with NumPy, by the formula written out here.

The E view's fields (``axis.energy``, each mode's ``span_gev``, the quadrature
fit's ``rho_a2b2`` and ``band_quantile``) are checked on every kind, the 2 GeV
floor of its σ/E range on synthetic windows, and the 1/√E view's x axes against
the recorded payload fixtures, which they must not move.

**The windows alone set both views' σ/E range** (Martin's decision of
2026-11-11): every served ``axis.y`` and ``axis.energy.y`` is held to the range
the served windows alone give, rebuilt here from the payload, and a fit line
above every window is shown not to raise either top. Every fit block carries
``misfit``, ν ≥ 1 and S above ``gates.misfit_scale``.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest
from pytest import approx

import contract_check
import test_payload_fixtures as recorded_payloads
from conftest import SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE, XGB_SOURCE, xgb_table
from calosrv.db import ddl, registry
from calosrv.modelruns import store
from calosrv.query import density, performance_bins, response, showers
from calosrv.query import resolution_scaling as rs
from calosrv.stats import clip as clip_mod
from calosrv.stats import resolution_fit as rfit
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
                             "anchor_low_gev": 5.0, "n_anchors": 3,
                             "misfit_scale": rfit.MISFIT_SCALE}
    bad = [s for s in _strings(body) if signed_hyphens(s)]
    assert not bad, bad[:3]
    _check_windows_alone(body)
    _check_misfit(body)
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
            _check_span(mode, s["windows"])
            for form in ("affine", "pinned", "quadrature"):
                if mode[form] is not None:
                    assert mode[form]["band_quantile"] > 0
    _check_energy_axis(body)


def _check_span(mode, windows):
    """span_gev is [p_lo of the first fitted window, p_hi of the last], or null without points."""
    if not mode["points"]:
        assert mode["span_gev"] is None
        return
    fitted = [w for w in windows if w["bin"] in set(mode["points"])]
    assert len(fitted) == len(mode["points"])
    assert mode["span_gev"] == [min(w["p_lo"] for w in fitted), max(w["p_hi"] for w in fitted)]


def _check_energy_axis(body):
    """axis.energy: E from 0 to 80 GeV (or the top edge rounded up), its own zero-based range."""
    energy = body["axis"]["energy"]
    x, y = energy["x"], energy["y"]
    assert x["min"] == 0.0 and x["interval"] == rs.E_VIEW_INTERVAL_GEV == 10.0
    assert x["unit"] == "GeV" and x["name"] == "Energy E [GeV]"
    top = energy["data_max_gev"]
    expected = rs.E_VIEW_MAX_GEV if top is None else max(80.0, 10.0 * np.ceil(top / 10.0))
    assert x["max"] == expected
    assert y["zero_based"] and y["lo"] == 0.0 and y["hi"] > 0 and y["unit"] == "%"
    assert energy["y_min_gev"] == rs.E_VIEW_Y_MIN_GEV == 2.0
    assert energy["curve_min_gev"] == rs.E_MIN_GEV == 4.0
    assert len(energy["notes"]) == 3 and energy["rule"].startswith("E = 1/x²")
    basis = energy["notes"][0]
    assert ("provisional" in basis) == y["provisional"]
    assert ("follows the windows alone" in basis) == (not y["provisional"])
    # No fit sets it, and one that leaves the top is clipped; the drawer states its own counts, so none is here.
    assert "No fitted curve, band or extrapolation sets it" in basis and "clipped there with a caret" in basis
    assert not re.search(r"\d+ (?:marks?|windows?) beyond it", basis)
    assert "fits over the windows" not in basis
    assert f"to {x['max']:g} GeV" in energy["notes"][1]


def _served_window_extents(body, energy: bool):
    """What the served windows draw on a σ/E axis, rebuilt from the payload: (extents, tops below 2 GeV).

    1/√E view: the windows on the axis; robust where eligible. E view: every window, those below
    2 GeV apart; robust from N ≥ 20 with a positive SE. No fit enters either.
    """
    extents, below = [], []
    for s in body["series"]:
        for w in s["windows"]:
            if w["value"] is None or w["n"] < rs.REPORT_MIN_N or (not energy and w["off_axis"]):
                continue
            lo = hi = w["value"]
            if w["whisker"]:
                lo, hi = min(w["value"], w["ci95"][0]), max(w["value"], w["ci95"][1])
            if energy and w["p_lo"] < rs.E_VIEW_Y_MIN_GEV:
                below.append(hi)
                continue
            robust = (w["n"] >= rs.FIT_MIN_N and (w["se_delta"] or 0) > 0) if energy else w["eligible"]
            extents.append(response.Extent(lo, hi, w["value"], robust))
    return extents, below


def _check_windows_alone(body):
    """Both served σ/E ranges are the ranges the served windows alone give (Martin, 2026-11-11)."""
    keys = ("lo", "hi", "interval", "provisional", "n_clipped")
    extents, _ = _served_window_extents(body, energy=False)
    linear = response._y_axis(extents)
    assert {k: body["axis"]["y"][k] for k in keys} == {k: linear[k] for k in keys}
    extents, below = _served_window_extents(body, energy=True)
    if not any(e.robust for e in extents):
        # Nothing robust from 2 GeV: the provisional range follows every marker, those below 2 GeV included.
        for s in body["series"]:
            for w in s["windows"]:
                if (w["value"] is not None and w["n"] >= rs.REPORT_MIN_N
                        and w["p_lo"] < rs.E_VIEW_Y_MIN_GEV):
                    extents.append(response.Extent(w["value"], w["value"], w["value"], False))
    e_view = response._y_axis(extents)
    e_view["n_clipped"] += sum(1 for top in below if top > e_view["hi"])
    assert {k: body["axis"]["energy"]["y"][k] for k in keys} == {k: e_view[k] for k in keys}
    # The sentences: the windows alone, no fit, and the clipped fits said.
    (basis,) = [n for n in body["notes"] if n.startswith("The y range ")]
    assert "No fit sets it" in basis and "clipped there with a caret" in basis
    assert ("(whiskers included) alone" in basis) == (not body["axis"]["y"]["provisional"])
    assert "the fits through them" not in basis


def _check_misfit(body):
    """Every fit block says whether its form describes its windows: ν ≥ 1 and S above the gate."""
    gate = body["gates"]["misfit_scale"]
    for s in body["series"]:
        for mode in s["fits"].values():
            for form in ("affine", "pinned", "quadrature"):
                fit = mode[form]
                if fit is None:
                    continue
                assert fit["misfit"] is (fit["ndf"] >= 1 and fit["scale_factor"] > gate), (s["key"], form)
                assert ("does not describe these windows" in fit["note"]) == fit["misfit"]
    rule = [n for n in body["notes"] if n.startswith("A fit whose residuals average more than")]
    assert len(rule) == 1 and f"S = √(χ²/ν) > {gate:g}" in rule[0] and "p-value" in rule[0]


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


def test_the_e_view_fields_of_the_two_shower_payload(synthetic_client):
    """data_max_gev is the bin axis's top edge; rho_a2b2 and band_quantile are a refit's."""
    body = _get(synthetic_client)
    with synthetic_client.app.state.database.read_cursor() as con:
        record = registry.get_experiment(con, body["meta"]["table_name"])
        axis = performance_bins.dataset_axis(con, record)
    energy = body["axis"]["energy"]
    assert energy["data_max_gev"] == axis.p_hi[-1] == 18.0
    assert energy["x"]["max"] == 80.0
    refits = 0
    for s in body["series"]:
        by_bin = {w["bin"]: w for w in s["windows"]}
        for mode in s["fits"].values():
            quad = mode["quadrature"]
            if quad is None:
                continue
            chosen = [by_bin[k] for k in mode["points"]]
            fit = rfit.fit_quadrature([w["x"] for w in chosen], [w["value"] / 100 for w in chosen],
                                      [w["n"] for w in chosen])
            # The payload's x and σ/E are written at six significant figures.
            assert quad["params"]["rho_a2b2"] == approx(fit.rho, rel=1e-3)
            assert quad["band_quantile"] == approx(fit.band_quantile, rel=1e-5)
            assert mode["span_gev"] == [chosen[0]["p_lo"], chosen[-1]["p_hi"]]
            refits += 1
    assert refits == 8                   # four series, two modes


def test_the_two_shower_payload_stays_under_the_contract(synthetic_client):
    """Measured on 2026-11-10: 56,388 bytes, the E view's fields 1,620 of them."""
    reply = synthetic_client.get(ROUTE)
    assert reply.status_code == 200
    assert len(reply.content) < density.RESPONSE_LIMIT == 100_000
    assert "over the" not in " ".join(reply.json()["meta"]["warnings"])


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


# --------------------------------------------- the 1/√E view stays put --

#: The fields of the 1/√E view the E view must not move: the panel and the dark golden read them.
#: ``axis.y`` and ``notes`` left this guard on 2026-11-11, when they changed on purpose (the
#: windows alone set the range; a misfit is said): ``_common`` now holds ``axis.y`` to the range the
#: served windows alone give, and the notes to their range and misfit sentences, on every response,
#: which also holds after the fixtures are re-recorded.
LINEAR_FIELDS = (("axis", "x"), ("axis", "top"))


def _linear_fields_match_the_recording(client, name):
    _, path, params, _ = recorded_payloads.PAYLOADS[name]
    reply = client.get(path, params=params)
    assert reply.status_code == 200, reply.text
    stored = recorded_payloads.OUT / f"{name}.json"
    recorded = recorded_payloads._comparable(
        path, json.loads(stored.read_text(encoding="utf-8")), name)
    served = recorded_payloads._comparable(path, recorded_payloads._masked(reply.json()), name)
    for keys in LINEAR_FIELDS:
        old, new = recorded, served
        for key in keys:
            old, new = old[key], new[key]
        assert new == old, (name, keys)


def test_the_linear_fields_match_the_two_shower_recording(synthetic_client):
    _linear_fields_match_the_recording(synthetic_client, "res_scaling_two")


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


@pytest.mark.parametrize("name", ["res_scaling_single_hits", "res_scaling_single_events"])
def test_the_linear_fields_match_the_single_shower_recordings(single_client, name):
    _linear_fields_match_the_recording(single_client, name)


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


def test_the_linear_fields_match_the_xgboost_recording(xgb_client):
    _linear_fields_match_the_recording(xgb_client, "res_scaling_xgb")


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


# ----------------------------------------------- the E view's 2 GeV floor --


def _series(windows: dict[int, tuple[int, float]], seed: int = 9) -> rs.Series:
    """A detector series on the axis 0–19 GeV: ``windows[k] = (N, σ/E)`` in bin k, R ~ N(1, σ²).

    Each bin draws from its own seeded stream, so adding a window leaves the others unchanged.
    """
    bins, p, ratio = [], [], []
    for k, (count, sigma) in windows.items():
        rng = np.random.default_rng([seed, k])
        bins += [k] * count
        p += list(rng.uniform(k, k + 1, count))
        ratio += list(1.0 + sigma * rng.standard_normal(count))
    axis = performance_bins.axis_from_ranges({k: (k + 0.01, k + 0.99) for k in range(0, 20)})
    return rs.build_series(rs.SOURCE_DETECTOR, "a", "Shower", rs.DETECTOR_LABEL, rs.SOURCE_DETECTOR,
                           np.array(ratio), np.array(p), np.array(bins, dtype=float), axis,
                           rs.nominal_anchors(axis))


ROBUST = {k: (200, 0.2 / np.sqrt(k + 0.5)) for k in range(4, 20)}


def test_a_window_below_2_gev_never_sets_the_e_range_and_is_counted_when_clipped():
    base = rs.energy_y_axis([_series(ROBUST)])
    assert not base["provisional"] and base["hi"] < 50.0
    # A big, robust 1–2 GeV window at about 300%: the range does not move; it is clipped and counted.
    big = rs.energy_y_axis([_series({1: (400, 3.0), **ROBUST})])
    assert (big["hi"], big["interval"], big["provisional"]) == (
        base["hi"], base["interval"], base["provisional"])
    assert big["n_clipped"] == base["n_clipped"] + 1
    extents, below = rs.energy_extents([_series({1: (400, 3.0), **ROBUST})])
    assert len(below) == 1 and below[0] > 200.0
    assert all(e.hi < 200.0 for e in extents)
    # One below the top is not counted.
    low = rs.energy_y_axis([_series({1: (400, 0.01), **ROBUST})])
    assert low == base


def test_a_robust_window_from_2_gev_sets_the_e_range_though_off_the_linear_axis():
    """The 2–3 GeV window is off the 1/√E axis but on the E axis, so it sets the E range there."""
    series = _series({2: (400, 0.8), **ROBUST})
    window = next(w for w in series.windows if w.bin == 2)
    assert window.off_axis and window.p_lo == rs.E_VIEW_Y_MIN_GEV
    y = rs.energy_y_axis([series])
    assert y["hi"] >= 100 * window.ci[1] and not y["provisional"]
    assert y["n_clipped"] == 0


def test_a_weak_window_below_2_gev_never_sets_a_range_that_has_a_robust_extent():
    below = {0: (12, 0.8), 1: (12, 0.8)}
    base = rs.energy_y_axis([_series(ROBUST)])
    joined = rs.energy_y_axis([_series({**below, **ROBUST})])
    assert (joined["hi"], joined["provisional"]) == (base["hi"], False)
    assert joined["n_clipped"] == base["n_clipped"] + 2


def test_a_selection_with_no_robust_extent_from_2_gev_follows_every_marker_provisionally():
    """S1: weak windows from 2 GeV, and weak ones below it, whose markers the range covers."""
    weak = {k: (12, 0.1) for k in (5, 10, 15)}
    alone = rs.energy_y_axis([_series(weak)])
    assert alone["provisional"]
    below = {0: (12, 0.8), 1: (12, 0.8)}
    series = _series({**below, **weak})
    joined = rs.energy_y_axis([series])
    assert joined["provisional"] and joined["hi"] > alone["hi"]
    markers = [100 * w.r for w in series.windows if w.r is not None and w.n >= rs.REPORT_MIN_N]
    assert joined["hi"] >= max(markers)
    # Whisker tops beyond the resulting top are counted; nothing else is.
    _, tops = rs.energy_extents([series])
    assert joined["n_clipped"] == sum(1 for t in tops if t > joined["hi"]) + sum(
        1 for w in series.windows
        if w.r is not None and w.n >= rs.REPORT_MIN_N and w.p_lo >= rs.E_VIEW_Y_MIN_GEV
        and 100 * (max(w.ci[1], w.r) if w.whisker else w.r) > joined["hi"])


def test_a_selection_wholly_below_2_gev_covers_its_markers_and_clips_nothing_robust():
    below = {0: (30, 0.5), 1: (12, 0.4)}
    series = _series(below)
    y = rs.energy_y_axis([series])
    markers = [100 * w.r for w in series.windows if w.r is not None and w.n >= rs.REPORT_MIN_N]
    assert markers and y["provisional"] and y["hi"] >= max(markers)
    extents, _ = rs.energy_extents([series])
    assert not any(e.robust for e in extents)


def test_no_fit_enters_either_views_extents():
    """One extent per window that reports σ/E, in either view: a fit summarises its windows, not more evidence."""
    series = _series({**ROBUST, 2: (400, 0.8), 3: (12, 0.5)})
    assert all(f is not None for mode in series.modes.values() for f in mode.fits.values())
    reported = [w for w in series.windows if w.r is not None and w.n >= rs.REPORT_MIN_N]
    extents, below = rs.energy_extents([series])
    assert below == [] and len(extents) == len(reported)
    assert [e.core_hi for e in extents] == [100 * w.r for w in reported]
    linear = rs.linear_extents([series])
    on_axis = [w for w in reported if not w.off_axis]
    assert len(linear) == len(on_axis) < len(reported)
    assert [e.robust for e in linear] == [w.eligible for w in on_axis]


#: σ/E flat at 30%, mostly a constant term, in windows of 2,000 events from 4 to 20 GeV.
FLAT = {k: (2000, 0.30) for k in range(4, 20)}


def test_a_fit_line_above_every_window_no_longer_raises_either_views_top():
    """The origin-pinned line through a flat σ/E rises above every window towards 4 GeV: it is clipped, not followed.

    The line a₀·x is forced through the origin, so through windows at a flat 30% it runs to about 45% at
    x = 0.5 (4 GeV): above every window and its whisker. The windows alone set both tops, and the old rule,
    which took that line, would have set a higher one.
    """
    series = _series(FLAT)
    windows = [w for w in series.windows if w.r is not None]
    reach = 100 * max(max(w.r, w.ci[1]) for w in windows)
    linear, energy = rs.linear_y_axis([series]), rs.energy_y_axis([series])
    for y in (linear, energy):
        assert not y["provisional"] and y["n_clipped"] == 0
        assert y["hi"] >= reach
        assert (y["lo"], y["hi"], y["interval"]) == clip_mod.nice_range(0.0, reach * (1 + response.HEADROOM),
                                                                          fine=True)
    for mode in series.modes.values():
        pinned = mode.fits[rfit.FORM_PINNED]
        line_top = 100 * float(pinned.predict(rs.X_MAX))      # 4 GeV, the 1/√E axis's left end
        span = rs.fitted_span(mode.points, series.windows)
        span_top = 100 * float(pinned.predict(1 / np.sqrt(span[0])))   # the E view, at its fitted span's foot
        assert line_top > reach and line_top > linear["hi"], "the line leaves the 1/√E view's top: clipped"
        assert span_top > energy["hi"], "and the E view's, over its own fitted windows"
        old = clip_mod.nice_range(0.0, line_top * (1 + response.HEADROOM), fine=True)[1]
        assert old > linear["hi"], "the old rule, which took the line, set a higher top"
        # A form that does not describe these windows: S far above 5; the quadrature form describes them.
        assert pinned.misfit and pinned.scale_factor > rfit.MISFIT_SCALE
        assert not mode.fits[rfit.FORM_QUADRATURE].misfit
        assert rs.fit_block(pinned, mode.provisional)["misfit"] is True


def test_fitted_span_is_null_without_points():
    series = _series(ROBUST)
    assert rs.fitted_span([], series.windows) is None
    assert rs.fitted_span([5, 10, 19], series.windows) == [5.0, 20.0]
