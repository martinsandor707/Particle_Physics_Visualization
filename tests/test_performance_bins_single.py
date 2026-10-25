"""The two network routes on experiments that carry no networks.

Booted with all three kinds (``single_client``): the two-shower baseline and the
single-shower hit and aggregate experiments. A single-shower file has no
reconstruction-network outputs, so ``/api/model-performance`` (whatever is asked
of it) and ``/api/prediction-density`` refuse it with a capability problem
naming the request field, instead of failing inside a query - and the same
routes still serve the baseline on the same server.
"""

from __future__ import annotations

import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

NETWORKLESS = (SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE)
KINDS = {SINGLE_HITS_TABLE: "single_shower_hits", SINGLE_EVENTS_TABLE: "single_shower_events"}


def assert_capability_problem(response, field="model", capability=None, kind=None):
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    contract_check.check(problem, "capability_problem")
    assert problem["type"] == "/problems/unsupported-capability"
    assert problem["field"] == field
    if capability is not None:
        assert problem["capability"] == capability
    if kind is not None:
        assert problem["kind"] == kind
    assert "network" in problem["reason"].lower()
    return problem


# ------------------------------------------------------ model-performance --


@pytest.mark.parametrize("table", NETWORKLESS)
@pytest.mark.parametrize("model", ["segmentation", "energy", "angle"])
@pytest.mark.parametrize("slice_by", ["d", "momentum_bin"])
def test_model_performance_refuses_an_experiment_without_networks(single_client, table, model,
                                                                   slice_by):
    response = single_client.get("/api/model-performance", params={
        "table_name": table, "model": model, "slice_by": slice_by})
    problem = assert_capability_problem(response, capability="networks", kind=KINDS[table])
    assert table in problem["detail"]


@pytest.mark.parametrize("table", NETWORKLESS)
def test_the_default_request_is_refused_the_same_way(single_client, table):
    response = single_client.get("/api/model-performance", params={"table_name": table})
    assert_capability_problem(response, capability="networks", kind=KINDS[table])


def test_the_baseline_is_still_served_beside_them(single_client):
    for slice_by in ("d", "momentum_bin"):
        model = "segmentation" if slice_by == "d" else "energy"
        response = single_client.get("/api/model-performance", params={
            "table_name": BASELINE_TABLE, "model": model, "slice_by": slice_by})
        assert response.status_code == 200, response.text
    block = single_client.get("/api/model-performance", params={
        "table_name": BASELINE_TABLE, "model": "energy", "slice_by": "momentum_bin",
    }).json()["by_momentum_bin"]
    assert block["frames"] == ["absolute", "trans", "local"]


def test_a_bad_value_is_still_a_validation_error_on_a_networkless_experiment(single_client):
    response = single_client.get("/api/model-performance", params={
        "table_name": SINGLE_HITS_TABLE, "slice_by": "foo"})
    assert response.status_code == 422 and response.json()["field"] == "slice_by"


# ------------------------------------------------------ prediction-density --


@pytest.mark.parametrize("table", NETWORKLESS)
@pytest.mark.parametrize("model", ["energy", "angle", "segmentation"])
def test_prediction_density_refuses_an_experiment_without_networks(single_client, table, model):
    response = single_client.get("/api/prediction-density", params={
        "table_name": table, "model": model})
    problem = assert_capability_problem(response, kind=KINDS[table])
    # The gates of the two cards, not the route's own wording.
    assert problem["capability"] in ("pred-truth", "pred-residuals")


def test_prediction_density_still_serves_the_baseline(single_client):
    response = single_client.get("/api/prediction-density", params={
        "table_name": BASELINE_TABLE, "model": "energy"})
    assert response.status_code == 200, response.text
    contract_check.check(response.json(), "prediction_density")


def test_the_catalogue_agrees_with_the_refusals(single_client):
    listed = {e["table_name"]: e for e in single_client.get("/api/experiments").json()["experiments"]}
    for table in NETWORKLESS:
        panels = listed[table]["capabilities"]["panels"]
        reasons = listed[table]["capabilities"]["reasons"]
        for card in ("perf-bins", "pred-truth", "pred-residuals"):
            assert panels[card] is False and "network" in reasons[card].lower()
    panels = listed[BASELINE_TABLE]["capabilities"]["panels"]
    assert panels["perf-bins"] and panels["pred-truth"] and panels["pred-residuals"]
