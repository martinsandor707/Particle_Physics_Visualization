"""``GET /api/prediction-density`` on the demonstration experiment (two events).

Two events give each shower two (truth, prediction) pairs: every shower is on
the lowest rung of the ladder, so the route must ship the pairs, mark the
residual range provisional, and still quote each shower's mean and width with
the uncertainty a sample of two allows. Populations from a dozen to two
hundred are exercised in ``test_prediction_density_synthetic.py``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import contract_check
from calosrv.db import naming
from calosrv.stats import gaussian


@pytest.fixture(scope="module")
def events(client):
    with client.app.state.database.read_cursor() as con:
        raw = con.execute(
            'SELECT event_number, en_true_a, en_true_b, th_true_a, th_true_b, '
            'en_pred_a_abs, en_pred_b_abs, th_pred_a_abs, th_pred_b_abs '
            f'FROM "{naming.event_table("experiment_baseline")}" ORDER BY event_number'
        ).fetchnumpy()
    return {k: np.asarray(v, dtype=np.float64) for k, v in raw.items()}


def get(client, **params):
    response = client.get("/api/prediction-density", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("model", ["energy", "angle"])
@pytest.mark.parametrize("coord_system", ["lab", "trans", "local"])
def test_the_response_satisfies_its_contract(client, model, coord_system):
    body = get(client, model=model, coord_system=coord_system)
    contract_check.check(body, "prediction_density")
    assert body["meta"]["exact"] is True and body["n_events"] == 2


@pytest.mark.parametrize("model,scale,stem", [("energy", 1.0, "en"), ("angle", 1000.0, "th")])
def test_two_events_ship_their_pairs_in_order(client, events, model, scale, stem):
    body = get(client, model=model)
    for shower in ("a", "b"):
        block = body["density"][shower]
        assert block["encoding"] == "pairs" and block["n"] == 2
        true = events[f"{stem}_true_{shower}"] * scale
        pred = events[f"{stem}_pred_{shower}_abs"] * scale
        order = np.argsort(true)
        assert np.asarray(block["pairs"]) == pytest.approx(
            np.column_stack([true[order], pred[order]]), rel=1e-5)
    assert body["color"]["vmax"] == 0.0


def test_the_demo_energy_axis_is_the_truths_range_from_zero(client, events):
    body = get(client, model="energy")
    truth = np.concatenate([events["en_true_a"], events["en_true_b"]])
    assert body["axes"]["truth"]["lo"] == 0.0
    assert body["axes"]["truth"]["hi"] >= truth.max() and body["axes"]["truth"]["hi"] - truth.max() < 2.0
    assert body["identity"] == {"from": 0.0, "to": body["axes"]["truth"]["hi"],
                                "label": "prediction = truth"}


def test_the_residual_is_provisional_and_each_shower_is_a_strip_with_honest_sigmas(client, events):
    body = get(client, model="energy")
    axis = body["residual"]["axis"]
    assert axis["provisional"] is True and "provisional" in axis["basis"]
    assert axis["clipping"]["applied"] is False
    for shower in ("a", "b"):
        s = body["residual"]["series"][shower]
        assert s["draw"] == "strip" or s["draw"] == "curve+strip"
        assert s["drives_scale"] is False and len(s["strip"]["values"]) == 2
        true = events[f"en_true_{shower}"]
        pred = events[f"en_pred_{shower}_abs"]
        r = (pred - true) / true
        est = s["estimates"]
        t = gaussian.t_quantile_975(1)
        assert est["bias"]["value"] == pytest.approx(r.mean(), rel=1e-5)
        assert est["bias"]["interval"]["hi"] == pytest.approx(
            r.mean() + t * r.std(ddof=1) / math.sqrt(2), rel=1e-5)
        # At N = 2 the width has one degree of freedom, and its interval is wide and asymmetric.
        sigma = est["sigma"]
        assert sigma["value"] == pytest.approx(r.std(ddof=1), rel=1e-5)
        assert sigma["interval"]["lo"] < 0.6 * sigma["value"] and sigma["interval"]["hi"] > 5 * sigma["value"]
        assert "c4" in sigma["note"]


def test_the_notices_say_the_density_is_replaced_by_its_pairs(client):
    warnings = get(client, model="angle")["meta"]["warnings"]
    assert any("Shower A has N = 2" in w and "individual pairs" in w for w in warnings)
    assert any("Shower B has N = 2" in w for w in warnings)
    assert any("residual range is provisional" in w for w in warnings)


def test_the_colour_statement_travels_even_when_no_density_is_drawn(client):
    first = get(client, model="energy")["color"]["ramp"]["first_level"]
    assert first["color"] == "#29788e" and first["contrast"] >= 3.0


@pytest.mark.parametrize("model", ["energy", "angle"])
def test_the_angle_network_has_no_azimuth_to_wrap_and_says_so(client, model):
    notes = get(client, model=model)["notes"]
    if model == "angle":
        assert "azimuth" in notes["angle"] and "nothing to wrap" in notes["angle"]
        assert "calibration" not in notes
    else:
        assert "no sampling-fraction" in notes["calibration"] and "angle" not in notes


def test_segmentation_and_unknown_values_are_refused_naming_the_field(client):
    for params, field in (({"model": "segmentation"}, "model"), ({"model": "x"}, "model"),
                          ({"model": "angle", "coord_system": "polar"}, "coord_system")):
        response = client.get("/api/prediction-density", params=params)
        assert response.status_code == 422 and response.json()["field"] == field
    assert client.get("/api/prediction-density", params={"bins": 5}).status_code == 422
