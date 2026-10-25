"""The feature explorer on two-shower data: each shower read from its own Group-1 sums.

Booted on ``synthetic_all_models``' 286 events, whose two incident momenta are
drawn independently in [2, 18] GeV, so the 1 GeV bins of either shower hold
about eighteen events each - enough for histograms - and shower A's classes
differ from shower B's. The checks: each shower is classed by its own
momentum, its features come from its own sums, and every view stays inside
its contract and the 100 KB budget.
"""

from __future__ import annotations

import pytest

import contract_check

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.query import density
from calosrv.text import signed_hyphens

ROUTE = "/api/features"


def _get(client, **params):
    response = client.get(ROUTE, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    contract_check.check(body, "features", f"view_{params.get('view', 'catalog')}")
    return body


def _table(client) -> str:
    listed = client.get("/api/experiments").json()["experiments"]
    ready = [e for e in listed if e["status"] == "ready"]
    assert ready, listed
    return ready[0]["table_name"]


def _rows(client, sql: str) -> list[tuple]:
    with client.app.state.database.read_cursor() as con:
        return con.execute(sql).fetchall()


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


@pytest.mark.parametrize("shower, momentum_bin, hits", [("a", "e1_bin", "n_hits_a"),
                                                        ("b", "e2_bin", "n_hits_b")])
def test_each_shower_is_classed_by_its_own_momentum(synthetic_client, shower, momentum_bin, hits):
    table = _table(synthetic_client)
    body = _get(synthetic_client, table_name=table, view="describe", classes="bins", shower=shower)
    event = quote(naming.event_table(table))
    expected = dict(_rows(synthetic_client,
                          f"SELECT CAST({momentum_bin} AS INTEGER), count(*) FROM {event} "
                          f"WHERE {hits} >= 2 GROUP BY 1"))
    served = {int(c["lo"]): c["n"] for c in body["classes"] if c["n"]}
    assert served == expected
    # The shower's own hit count, never the event's.
    largest = dict(_rows(synthetic_client,
                         f"SELECT CAST({momentum_bin} AS INTEGER), max({hits}) FROM {event} "
                         f"WHERE {hits} >= 2 GROUP BY 1"))
    for c, top in zip(body["classes"], body["table"]["num_hits"]["max"]):
        if c["n"]:
            assert top == largest[int(c["lo"])]


def test_the_two_showers_are_different_samples(synthetic_client):
    table = _table(synthetic_client)
    a = _get(synthetic_client, table_name=table, view="catalog", classes="bins", shower="a")
    b = _get(synthetic_client, table_name=table, view="catalog", classes="bins", shower="b")
    assert [c["n"] for c in a["classes"]] != [c["n"] for c in b["classes"]]
    assert sum(c["n"] for c in a["classes"]) == a["n_events"]
    assert a["kind"] == "two_shower_hits" and b["shower"] == "b"
    notes = " ".join(a["notes"])
    assert "own incident momentum" in notes and "'A+B' rows count with shower B" in notes


@pytest.mark.parametrize("shower", ["a", "b"])
@pytest.mark.parametrize("coord_system", ["lab", "trans", "local"])
def test_histograms_are_drawn_where_the_bins_hold_enough_events(synthetic_client, shower,
                                                                 coord_system):
    table = _table(synthetic_client)
    body = _get(synthetic_client, table_name=table, view="hist", feature="total_hit_energy",
                classes="bins", shower=shower, coord_system=coord_system)
    drawn = [s for s in body["series"] if s["draw"] == "histogram"]
    assert drawn and all(s["n"] >= 15 and s["kde"] is not None for s in drawn)
    assert not body["axis"]["provisional"]
    two_d = _get(synthetic_client, table_name=table, view="hist2d", feature="depth_range",
                 classes="bins", shower=shower, coord_system=coord_system)
    assert any(s["draw"] == "histogram" for s in two_d["series"])
    assert two_d["x"]["quantum"] is None or two_d["x"]["quantum"]["snapped"]


def test_every_view_fits_the_budget(synthetic_client):
    table = _table(synthetic_client)
    for shower in ("a", "b"):
        for classes in ("windows", "bins", "label"):
            for params in ({"view": "catalog"}, {"view": "describe"},
                           {"view": "corr", "class_index": "pooled"},
                           {"view": "hist", "feature": "width"},
                           {"view": "hist", "feature": "avg_phi_circ"},
                           {"view": "hist2d", "feature": "num_hits"}):
                body = _get(synthetic_client, table_name=table, shower=shower, classes=classes,
                            **params)
                assert density.wire_size(body) < density.RESPONSE_LIMIT
                assert not [h for text in _strings(body) for h in signed_hyphens(text)]
