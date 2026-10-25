"""``GET /api/profiles`` (C7) on two-shower data with many events: the event as the cluster.

The ``synthetic_client`` server holds 286 two-shower events in D slices of 1,
2, 7, 8, 14, 15, 19, 20 and 200 events. With both showers selected, the two
showers of one event share its geometry, so the envelope of the per-shower
mean and the pooled line's interval treat the event as the sampling unit;
the route is held to an explicit per-event brute force
(``test_physics_profiles_render.reference``) on the full selection and on
the one- and two-event slices, where the cluster count gates the marks.
"""

from __future__ import annotations

from typing import Any

import pytest

import contract_check
from test_physics_profiles_render import assert_axis_matches, assert_typography, reference
from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.query import density

BOTH = [(0, "a"), (1, "b")]


@pytest.fixture(scope="module")
def table(synthetic_client) -> str:
    ready = [e["table_name"] for e in synthetic_client.get("/api/experiments").json()["experiments"]
             if e["status"] == "ready"]
    assert ready, "the synthetic experiment did not ingest"
    return ready[0]


def _get(client, **params) -> dict[str, Any]:
    response = client.get("/api/profiles", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _check(client, table: str, payload: dict[str, Any], units, where: str, params: dict,
           notebook: bool = False) -> None:
    with client.app.state.database.read_cursor() as con:
        for key, block in payload["axes"].items():
            assert_axis_matches(key, block, reference(con, table, units, where, params, key, notebook))


def _events(client, table: str, where: str, params: dict) -> int:
    with client.app.state.database.read_cursor() as con:
        return con.execute(f"SELECT count(*) FROM {quote(naming.event_table(table))} WHERE {where}",
                           params).fetchone()[0]


@pytest.mark.parametrize("depth", ["w", "native"])
def test_both_showers_cluster_on_the_event(synthetic_client, table, depth):
    payload = _get(synthetic_client, table_name=table, depth=depth)
    g = _events(synthetic_client, table, "d IS NOT NULL", {})
    ensemble = payload["ensemble"]
    assert (ensemble["n_events"], ensemble["n_showers"], ensemble["clustered"]) == (g, 2 * g, True)
    for block in payload["axes"].values():
        assert block["envelope"]["cluster"] == "event" and block["envelope"]["dof"] == g - 1
    _check(synthetic_client, table, payload, BOTH, "d IS NOT NULL", {})


def test_the_notebook_convention_on_two_showers(synthetic_client, table):
    payload = _get(synthetic_client, table_name=table, notebook="true")
    _check(synthetic_client, table, payload, BOTH, "d IS NOT NULL", {}, notebook=True)


@pytest.mark.parametrize("shower, units", [("a", [(0, "a")]), ("b", [(1, "b")])])
def test_one_shower_of_each_event_is_its_own_cluster(synthetic_client, table, shower, units):
    payload = _get(synthetic_client, table_name=table, shower=shower)
    g = _events(synthetic_client, table, "d IS NOT NULL", {})
    assert (payload["ensemble"]["n_showers"], payload["ensemble"]["clustered"]) == (g, False)
    _check(synthetic_client, table, payload, units, "d IS NOT NULL", {})


def test_one_event_gives_a_band_but_no_interval(synthetic_client, table):
    where, params = "d IS NOT NULL AND d BETWEEN $lo AND $hi", {"lo": 0.0, "hi": 50.0}
    assert _events(synthetic_client, table, where, params) == 1
    payload = _get(synthetic_client, table_name=table, d_min=0.0, d_max=50.0)
    ensemble = payload["ensemble"]
    assert (ensemble["n_showers"], ensemble["n_events"], ensemble["dof_note"]) == (2, 1, "1 d.o.f.")
    drawn = {m["key"]: m["drawn"] for m in payload["marks"]}
    assert drawn == {"mean": True, "band": True, "envelope": False, "pooled": True}
    for block in payload["axes"].values():
        assert block["band"] is not None and block["envelope"] is None
        assert all(v is None for v in block["pooled"]["ci95_lo"])
    assert any("G = 1 event" in note for note in payload["notes"])
    assert not any("Capped envelope" in note for note in payload["notes"])
    _check(synthetic_client, table, payload, BOTH, where, params)


def test_two_events_give_an_envelope_on_one_degree_of_freedom(synthetic_client, table):
    where, params = "d IS NOT NULL AND d BETWEEN $lo AND $hi", {"lo": 50.0, "hi": 100.0}
    assert _events(synthetic_client, table, where, params) == 2
    payload = _get(synthetic_client, table_name=table, d_min=50.0, d_max=100.0)
    assert (payload["ensemble"]["n_showers"], payload["ensemble"]["n_events"]) == (4, 2)
    assert payload["ensemble"]["label"] == "weak (N = 4)"
    assert any("(1 degree of freedom)" in note for note in payload["notes"])
    assert not any("1 degrees" in note for note in payload["notes"])
    for block in payload["axes"].values():
        assert block["envelope"]["dof"] == 1 and block["envelope"]["t"] == pytest.approx(12.706, abs=1e-3)
    _check(synthetic_client, table, payload, BOTH, where, params)


@pytest.mark.parametrize("params", [
    {"depth": "w"}, {"depth": "native"}, {"depth": "w", "notebook": "true"},
    {"depth": "w", "d_min": 0.0, "d_max": 50.0},
])
def test_contract_and_budget_at_full_size(synthetic_client, table, params):
    response = synthetic_client.get("/api/profiles", params={"table_name": table, **params})
    assert response.status_code == 200, response.text
    payload = response.json()
    contract_check.check(payload, "profiles")
    assert len(response.content) < density.RESPONSE_LIMIT
    assert density.wire_size(payload) == len(response.content)
    assert_typography(payload)
