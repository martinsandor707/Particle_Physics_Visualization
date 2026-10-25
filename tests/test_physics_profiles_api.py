"""``GET /api/profiles`` (C7) on the three kinds of experiment, booted once.

The ``single_client`` server holds a synthetic single-shower hit experiment
(287 events in 1 GeV bins with populations 1, 2, 7, 8, 14, 15, 19, 20 and 200,
plus one single-hit event), its 59-column aggregate, and the two-event
two-shower baseline. Every number the route draws is held to a brute force
built from the same profile and layer tables (``test_physics_profiles_render.
reference``): the per-shower mean, the ddof = 1 SD band, the Student-t
envelope and the pooled ratio with its event-clustered interval, in both
normalisation conventions and on both depth axes.
"""

from __future__ import annotations

from typing import Any

import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from test_physics_profiles_render import approx, assert_axis_matches, assert_typography, reference
from calosrv.db import ddl, naming
from calosrv.db.naming import quote
from calosrv.query import density, profiles, showers

#: The single-shower fixture's 1 GeV bins, by their population.
BIN_OF_N = {1: 3, 2: 7, 7: 12, 20: 2, 200: 10}


def _get(client, **params) -> dict[str, Any]:
    response = client.get("/api/profiles", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _momentum_bin(k: int) -> dict[str, float]:
    return {"e1_min": float(k), "e1_max": k + 0.99999}


def _query(client, sql: str, params: dict | None = None) -> list[tuple]:
    with client.app.state.database.read_cursor() as con:
        return con.execute(sql, params or {}).fetchall()


def _reference(client, name: str, showers_: list[tuple[int, str]], where: str, params: dict,
               axis: str, notebook: bool = False) -> dict[str, Any]:
    with client.app.state.database.read_cursor() as con:
        return reference(con, name, showers_, where, params, axis, notebook)


# ------------------------------------------------------------ vocabulary --

def test_every_column_read_exists_in_the_ddl_and_the_tables(single_client):
    assert set(profiles.PROFILE_READS) <= {name for name, _ in ddl.PROFILES_COLUMNS}
    assert set(profiles.LAYER_READS) <= {name for name, _ in ddl.LAYERS_COLUMNS}
    for name in (SINGLE_HITS_TABLE, BASELINE_TABLE):
        def columns(table: str) -> set[str]:
            return {r[0] for r in _query(single_client, "SELECT column_name FROM "
                                         "information_schema.columns WHERE table_name = ?", [table])}
        assert set(profiles.PROFILE_READS) <= columns(naming.profiles_table(name))
        assert set(profiles.LAYER_READS) <= columns(naming.layers_table(name))
        with single_client.app.state.database.read_cursor() as con:
            from calosrv.db import registry
            record = registry.require_ready(con, name)
        event = columns(naming.event_table(name))
        for s in showers.of(record, "both"):
            assert {s.shower_energy, s.w_neg_energy, s.group1("n_cells")} <= event


# ------------------------------------------------- numbers against NumPy --

@pytest.mark.parametrize("depth", ["w", "native"])
def test_single_shower_profiles_match_numpy(single_client, depth):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, depth=depth)
    n = _query(single_client, f"SELECT count(*) FROM {quote(naming.event_table(SINGLE_HITS_TABLE))}")[0][0]
    assert payload["ensemble"]["n_showers"] == payload["ensemble"]["n_events"] == n
    assert payload["ensemble"]["clustered"] is False and not payload["ensemble"]["provisional"]
    first = "w" if depth == "w" else "kt"
    assert list(payload["axes"]) == [first, "r"]
    for key, block in payload["axes"].items():
        ref = _reference(single_client, SINGLE_HITS_TABLE, [(0, "a")], "TRUE", {}, key)
        assert_axis_matches(key, block, ref)
        assert block["envelope"]["dof"] == n - 1 and block["envelope"]["cluster"] == "shower"


def test_notebook_convention_matches_numpy(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, notebook="true")
    assert payload["notebook_scale"] is True and payload["convention"]["notebook"] is True
    e_dep, e_neg = _query(single_client, "SELECT sum(e_dep_a), sum(w_neg_energy_a) FROM "
                          f"{quote(naming.event_table(SINGLE_HITS_TABLE))}")[0]
    assert payload["convention"]["dropped_energy_fraction"] == pytest.approx(e_neg / e_dep, rel=1e-5)
    for key, block in payload["axes"].items():
        ref = _reference(single_client, SINGLE_HITS_TABLE, [(0, "a")], "TRUE", {}, key, notebook=True)
        assert_axis_matches(key, block, ref)
        assert block["outside"]["below_fraction"] >= 0.0
    plain = _get(single_client, table_name=SINGLE_HITS_TABLE)
    assert plain["notebook_scale"] is False
    # Dropping the hits behind the entry plane removes energy below w = 0.
    assert (payload["axes"]["w"]["w_zero_rule"]["energy_fraction_below"]
            < plain["axes"]["w"]["w_zero_rule"]["energy_fraction_below"])
    assert any("Notebook convention" in note for note in payload["notes"])


def test_the_radial_axis_is_the_same_with_either_depth(single_client):
    w = _get(single_client, table_name=SINGLE_HITS_TABLE, depth="w")["axes"]["r"]
    native = _get(single_client, table_name=SINGLE_HITS_TABLE, depth="native")["axes"]["r"]
    # Two statements sum the same rows in different orders: equal to rounding.
    assert w["mean"] == approx(native["mean"])
    for mark, fields in (("band", ("lo", "hi")), ("envelope", ("lo", "hi")),
                         ("pooled", ("value", "ci95_lo", "ci95_hi"))):
        for field in fields:
            assert w[mark][field] == approx(native[mark][field]), (mark, field)
    assert w["n_present"] == native["n_present"]
    assert w["outside"] == pytest.approx(native["outside"], rel=1e-5)


def test_curves_and_outside_fractions_close_to_one(single_client):
    for depth in ("w", "native"):
        payload = _get(single_client, table_name=SINGLE_HITS_TABLE, depth=depth)
        for block in payload["axes"].values():
            width_cm = block["pitch_mm"] / 10.0
            out = block["outside"]
            pooled = sum(v * width_cm for v in block["pooled"]["value"]) / 100.0
            mean = sum(v * width_cm for v in block["mean"]) / 100.0
            assert pooled + out["below_fraction"] + out["above_fraction"] == pytest.approx(1.0, abs=1e-5)
            assert mean + out["mean_below_fraction"] + out["mean_above_fraction"] == pytest.approx(
                1.0, abs=1e-5)


# ------------------------------------------------------------- low-N gates --

def _expected_n(client, k: int) -> int:
    lo, hi = _momentum_bin(k).values()
    return _query(client, f"SELECT count(*) FROM {quote(naming.event_table(SINGLE_HITS_TABLE))} "
                  "WHERE e1 BETWEEN $lo AND $hi", {"lo": lo, "hi": hi})[0][0]


def test_one_shower_is_its_own_profile_not_an_ensemble(single_client):
    k = BIN_OF_N[1]
    assert _expected_n(single_client, k) == 1
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, **_momentum_bin(k))
    ensemble = payload["ensemble"]
    assert (ensemble["n_showers"], ensemble["label"], ensemble["dof_note"], ensemble["provisional"]) == (
        1, "single shower, not an ensemble", None, True)
    drawn = {m["key"]: m["drawn"] for m in payload["marks"]}
    assert drawn == {"mean": True, "band": False, "envelope": False, "pooled": False}
    lo, hi = _momentum_bin(k).values()
    for key, block in payload["axes"].items():
        assert block["band"] is None and block["envelope"] is None
        assert all(v is None for v in block["pooled"]["ci95_hi"])
        assert block["y"]["provisional"] is True
        ref = _reference(single_client, SINGLE_HITS_TABLE, [(0, "a")], "e1 BETWEEN $lo AND $hi",
                         {"lo": lo, "hi": hi}, key)
        assert_axis_matches(key, block, ref)
        # The pooled line of one shower is that shower's own profile.
        assert block["pooled"]["value"] == pytest.approx(block["mean"], rel=1e-5, abs=1e-9)
    assert any("single shower, not an ensemble" in note for note in payload["notes"])


def test_the_single_hit_event_is_a_single_cell_shower(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, e1_min=4.0, e1_max=4.99999)
    assert payload["ensemble"]["n_showers"] == 1 and payload["ensemble"]["n_single_cell"] == 1
    w = payload["axes"]["w"]
    # One cell at its own entry point: the splat puts half of it behind w = 0.
    assert w["w_zero_rule"]["energy_fraction_below"] == pytest.approx(0.5, abs=1e-6)
    assert any("deposits in one cell" in note for note in payload["notes"])


@pytest.mark.parametrize("n, label, dof, provisional", [
    (2, "weak (N = 2)", "1 d.o.f.", True),
    (7, "weak (N = 7)", None, True),
    (20, "", None, False),
])
def test_low_n_labels_and_marks(single_client, n, label, dof, provisional):
    k = BIN_OF_N[n]
    assert _expected_n(single_client, k) == n
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, **_momentum_bin(k))
    ensemble = payload["ensemble"]
    assert (ensemble["n_showers"], ensemble["label"], ensemble["dof_note"], ensemble["provisional"]) == (
        n, label, dof, provisional)
    assert all(m["drawn"] for m in payload["marks"])
    lo, hi = _momentum_bin(k).values()
    for key, block in payload["axes"].items():
        assert block["y"]["provisional"] is provisional
        assert block["envelope"]["dof"] == n - 1
        ref = _reference(single_client, SINGLE_HITS_TABLE, [(0, "a")], "e1 BETWEEN $lo AND $hi",
                         {"lo": lo, "hi": hi}, key)
        assert_axis_matches(key, block, ref)
    if dof:
        assert any("1 degree of freedom" in note for note in payload["notes"])
    if provisional:
        assert any("y range provisional" in note for note in payload["notes"])


# ---------------------------------------------------- two-shower baseline --

@pytest.mark.parametrize("shower, units, clustered", [
    ("a", [(0, "a")], False),
    ("b", [(1, "b")], False),
    ("both", [(0, "a"), (1, "b")], True),
])
def test_two_shower_baseline_by_shower(single_client, shower, units, clustered):
    payload = _get(single_client, table_name=BASELINE_TABLE, shower=shower)
    n_events = _query(single_client, f"SELECT count(*) FROM {quote(naming.event_table(BASELINE_TABLE))} "
                      "WHERE d IS NOT NULL")[0][0]
    ensemble = payload["ensemble"]
    assert ensemble["n_events"] == n_events and ensemble["clustered"] is clustered
    assert ensemble["n_showers"] == n_events * len(units)
    assert payload["shower"] == shower and payload["kind"] == ddl.KIND_TWO_SHOWER
    for key, block in payload["axes"].items():
        ref = _reference(single_client, BASELINE_TABLE, units, "d IS NOT NULL", {}, key)
        assert_axis_matches(key, block, ref)
        assert block["envelope"]["cluster"] == ("event" if clustered else "shower")
    assert any("'A+B' cells are counted with shower B" in note for note in payload["notes"])


# ---------------------------------------------------------------- refusals --

def test_the_aggregate_is_refused_with_the_capability_problem(single_client):
    response = single_client.get("/api/profiles", params={"table_name": SINGLE_EVENTS_TABLE})
    assert response.status_code == 422
    problem = response.json()
    contract_check.check(problem, "capability_problem")
    assert problem["capability"] in ("profile-w", "profile-r")
    assert problem["kind"] == ddl.KIND_SINGLE_EVENTS and "no hits" in problem["reason"]


def test_a_stale_two_shower_experiment_is_refused_with_the_rebuild(single_client, monkeypatch):
    """Derived before the profile tables existed: refused naming the rebuild, never an empty chart."""
    import dataclasses

    from calosrv.api import deps

    real = deps.require_ready
    monkeypatch.setattr(deps, "require_ready",
                        lambda con, name: dataclasses.replace(real(con, name), derived_version=1))
    response = single_client.get("/api/profiles", params={"table_name": BASELINE_TABLE})
    assert response.status_code == 422
    problem = response.json()
    contract_check.check(problem, "capability_problem")
    assert problem["capability"] == "profile-w" and problem["kind"] == ddl.KIND_TWO_SHOWER
    assert "Rebuild derived tables" in problem["reason"]


@pytest.mark.parametrize("params, field", [
    ({"shower": "b"}, "shower"),
    ({"shower": "c"}, "shower"),
    ({"depth": "z"}, "depth"),
    ({"depth": "native", "notebook": "true"}, "notebook"),
    ({"e2_min": 1.0}, "e2_min"),
])
def test_bad_requests_name_the_field(single_client, params, field):
    response = single_client.get("/api/profiles", params={"table_name": SINGLE_HITS_TABLE, **params})
    assert response.status_code == 422, response.text
    assert response.json()["field"] == field


# ------------------------------------------- contract, budget, typography --

_CASES = [
    (SINGLE_HITS_TABLE, {"depth": "w"}),
    (SINGLE_HITS_TABLE, {"depth": "native"}),
    (SINGLE_HITS_TABLE, {"depth": "w", "notebook": "true"}),
    (SINGLE_HITS_TABLE, {"depth": "w", "shower": "a", **_momentum_bin(BIN_OF_N[1])}),
    (SINGLE_HITS_TABLE, {"depth": "w", "e1_min": 30.0, "e1_max": 31.0}),       # no shower at all
    (BASELINE_TABLE, {"depth": "w", "shower": "both"}),
    (BASELINE_TABLE, {"depth": "native", "shower": "b"}),
    (BASELINE_TABLE, {"depth": "w", "shower": "both", "notebook": "true"}),
]


@pytest.mark.parametrize("name, params", _CASES)
def test_contract_budget_and_typography(single_client, name, params):
    response = single_client.get("/api/profiles", params={"table_name": name, **params})
    assert response.status_code == 200, response.text
    payload = response.json()
    contract_check.check(payload, "profiles")
    assert len(response.content) < density.RESPONSE_LIMIT
    assert density.wire_size(payload) == len(response.content)
    assert_typography(payload)
    assert [m["key"] for m in payload["marks"]] == ["mean", "band", "envelope", "pooled"]
    assert payload["depth"] == params["depth"]


def test_an_empty_selection_says_so(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, e1_min=30.0, e1_max=31.0)
    assert payload["ensemble"]["n_showers"] == 0 and payload["ensemble"]["label"] == "no showers"
    assert payload["meta"]["warnings"]
    assert all(v is None for block in payload["axes"].values() for v in block["mean"])


def test_a_repeated_request_is_served_from_the_cache(single_client):
    params = {"table_name": SINGLE_HITS_TABLE, "depth": "w", **_momentum_bin(BIN_OF_N[200])}
    first = _get(single_client, **params)
    second = _get(single_client, **params)
    assert second["meta"]["cached"] is True
    assert first["axes"] == second["axes"]


# ---------------------------------------------------------- disclosures --

def test_w_zero_rule_comb_and_splat_are_reported(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE)
    with single_client.app.state.database.read_cursor() as con:
        from calosrv.db import registry
        spec = registry.require_ready(con, SINGLE_HITS_TABLE).capabilities["profiles"]
    e_dep, e_neg = _query(single_client, "SELECT sum(e_dep_a), sum(w_neg_energy_a) FROM "
                          f"{quote(naming.event_table(SINGLE_HITS_TABLE))}")[0]
    w = payload["axes"]["w"]
    rule = w["w_zero_rule"]
    assert 0.0 in w["edges_cm"] and rule["at_cm"] == 0.0 and rule["bin_edge"] is True
    assert 0.0 <= rule["energy_fraction_below"] <= 1.0
    assert rule["hit_level_c9"] == pytest.approx(e_neg / e_dep, rel=1e-5)
    assert payload["axes"]["r"]["w_zero_rule"] is None
    for key in ("w", "r"):
        comb = payload["axes"][key]["comb"]
        assert (comb["k"], comb["k_z"]) == (spec["k"], spec["k_z"])
        assert comb["threshold"] == -0.1 and comb["regime"] == "local_subdeposit_splat"
        # The full selection's pooled profile is the one ingest measured.
        assert comb["lag1"] == pytest.approx(spec["comb"][key], abs=1e-3)
        assert payload["axes"][key]["splat"]["k"] == spec["k"]
    assert payload["axes"]["r"]["outside"]["above_fraction"] > 0
    assert payload["axes"]["r"]["edges_cm"][-1] == 50.0
    native = _get(single_client, table_name=SINGLE_HITS_TABLE, depth="native")["axes"]["kt"]
    assert native["splat"] is None and native["comb"]["regime"] == "native_layers"
    # One bin per layer cannot alias: the lag-1 is recorded, never called a comb.
    assert native["comb"]["combed"] is None and native["comb"]["k"] is None
    assert native["w_zero_rule"] is None
