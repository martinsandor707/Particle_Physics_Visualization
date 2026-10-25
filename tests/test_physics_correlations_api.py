"""C8 through the booted app: the contract, the jackknife against SQL, the gates, the refusals.

Two booted fixtures, in this order - each resets the process-wide database, so
every ``single_client`` test sits above the first ``synthetic_client`` one:

* ``single_client``: single-shower hits (287 events, so 64 jackknife groups),
  the aggregated experiment (no hits: refused) and the two-event baseline;
* ``synthetic_client``: 286 two-shower events, both showers and their 'A+B'
  hits, with low-N populations in separation slices.

Payload numbers carry six significant figures, so the route is compared with
SQL at 1e-5 relative; the unrounded estimators are compared at 1e-9 through
the query module on the app's own database.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from calosrv.db import naming, registry
from calosrv.query import correlations, density, filters, hit_sql
from calosrv.stats import gaussian, jackknife

URL = "/api/correlations"
PHI = 6
#: The oracle's columns for the matrix rows x, y, z, E, p, θ.
LINEAR = ("x", "y", "z", "e", "mom", "th")
ROUNDED = 1e-5


def _get(client, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    payload = response.json()
    contract_check.check(payload, "correlations")
    assert density.wire_size(payload) == len(response.content) < density.RESPONSE_LIMIT
    return payload


def _refused(client, field: str, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["field"] == field, problem
    return problem


def _hits_sql(record, spec, coord_system: str = "local", shower: str = "both",
              energy_scale: str = "linear") -> tuple[str, dict]:
    """The selected hits with their own shower's p, θ, cos φ, sin φ, written apart from the module."""
    proj = naming.quote(naming.proj_table(record.table_name))
    event = naming.quote(naming.event_table(record.table_name))
    params = dict(spec.params())
    if coord_system == "local":
        x, y, z = "p.xl", "p.yl", "p.zl"
    elif coord_system == "trans":
        x, y, z = "p.xt", "p.yt", f"p.kt * {hit_sql.layer_pitch(record)!r}"
    else:
        x, y, z = ("list_extract($ox, p.ix + 1)", "list_extract($oy, p.iy + 1)",
                   "list_extract($oz, p.iz + 1)")
        lattice = record.lattice
        params.update(ox=[float(v) for v in lattice.x.coords],
                      oy=[float(v) for v in lattice.y.coords],
                      oz=[float(v) for v in lattice.z.coords])
    if record.kind == "two_shower_hits":
        def own(a: str, b: str) -> str:
            return f"CAST(CASE WHEN p.org = 0 THEN ev.{a} ELSE ev.{b} END AS DOUBLE)"

        mom, th, ph = own("e1", "e2"), own("theta_a", "theta_b"), own("phi_a", "phi_b")
        keep = {"a": "p.org = 0", "b": "p.org IN (1, 2)", "both": "TRUE"}[shower]
    else:
        mom, th, ph = ("CAST(ev.e1 AS DOUBLE)", "CAST(ev.theta_a AS DOUBLE)",
                       "CAST(ev.phi_a AS DOUBLE)")
        keep = "TRUE"
    energy = "p.energy" if energy_scale == "linear" else "log10(p.energy)"
    sql = f"""
        SELECT CAST({x} AS DOUBLE) AS x, CAST({y} AS DOUBLE) AS y, CAST({z} AS DOUBLE) AS z,
               {energy} AS e, {mom} AS mom, {th} AS th, cos({ph}) AS c, sin({ph}) AS s,
               p.event_number AS ev_n
        FROM {proj} p JOIN {event} ev ON ev.event_number = p.event_number
        WHERE {keep} AND {spec.where_sql('ev')}
    """
    return sql, params


def _corr(con, sql: str, params: dict, a: str, b: str, where: str = "TRUE") -> float:
    return con.execute(f"SELECT corr({a}, {b}) FROM ({sql}) WHERE {where}", params).fetchone()[0]


def _sql_jackknife(con, sql: str, params: dict, a: str, b: str, n_events: int):
    """``(SE of atanh r, groups)`` by leaving each event group out, one SQL corr() each."""
    groups = jackknife.n_groups(n_events)
    key = "ev_n" if n_events <= jackknife.MAX_GROUPS else f"(ev_n % {groups})"
    ids = [g for (g,) in con.execute(f"SELECT DISTINCT {key} FROM ({sql}) ORDER BY 1", params).fetchall()]
    z = np.array([math.atanh(_corr(con, sql, {**params, "leave": g}, a, b, f"{key} <> $leave"))
                  for g in ids])
    g = z.size
    return math.sqrt((g - 1) / g * np.sum((z - z.mean()) ** 2)), g


def _check_matrix(payload: dict) -> None:
    """Symmetric, unit linear diagonal, every interval around its r, φ hatched."""
    matrix = payload["matrix"]
    for i, row in enumerate(matrix):
        for j, cell in enumerate(row):
            mirror = matrix[j][i]
            for key in ("r", "ci95", "se_z", "n_eff", "event_weighted_r", "mardia"):
                assert cell[key] == mirror[key], (i, j, key)
            if PHI in (i, j):
                assert cell["hatched"] and cell["r"] is None and cell["ci95"] is None
                continue
            if i == j:
                assert cell["r"] == 1.0 and cell["ci95"] is None
            elif cell["ci95"] is not None:
                lo, hi = cell["ci95"]
                assert lo <= cell["r"] <= hi
                assert cell["n_eff"] > 3 and cell["se_iid"] > 0


def _event_table(record) -> str:
    return naming.quote(naming.event_table(record.table_name))


def _record(client, table: str):
    with client.app.state.database.read_cursor() as con:
        return registry.require_ready(con, table)


# ------------------------------------------------------- single_client --


@pytest.mark.parametrize("energy_scale", correlations.ENERGY_SCALES)
@pytest.mark.parametrize("coord_system", ("local", "trans", "lab"))
def test_single_shower_matrix_is_served_under_the_contract(single_client, coord_system,
                                                           energy_scale):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE, coord_system=coord_system,
                   energy_scale=energy_scale)
    assert (payload["n_events"], payload["n_showers"]) == (287, 287)
    assert (payload["groups"], payload["dof"], payload["weak"]) == (64, 63, False)
    assert payload["method"] == "event-grouped jackknife, 64 groups (event_number mod 64)"
    assert payload["interval"] == ("95% event-grouped jackknife on Fisher z, 64 groups "
                                   "(Student-t, 63 dof)")
    assert payload["showers"] == ["Shower"] and payload["shower"] == "both"
    assert payload["filter"]["e2"] == [None, None] and payload["meta"]["exact"] is True
    _check_matrix(payload)
    # Per-shower pairs carry the per-shower (unweighted) value beside the hit-weighted one.
    assert payload["matrix"][4][5]["event_weighted_r"] is not None
    assert payload["matrix"][0][4]["event_weighted_r"] is None


def test_r_and_the_jackknife_match_sql_leave_one_group_out(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE)
    record = _record(single_client, SINGLE_HITS_TABLE)
    spec = filters.build(record)
    sql, params = _hits_sql(record, spec)
    t = gaussian.t_quantile_975(payload["dof"])
    with single_client.app.state.database.read_cursor() as con:
        analysis = correlations.analyse(con, record, spec)
        for i, j in ((0, 2), (3, 4), (2, 5), (0, 1)):
            a, b = LINEAR[i], LINEAR[j]
            r = _corr(con, sql, params, a, b)
            se, groups = _sql_jackknife(con, sql, params, a, b, payload["n_events"])
            assert groups == payload["groups"] == 64
            assert analysis.hit_fit.r[i, j] == pytest.approx(r, abs=1e-9)
            assert analysis.hit_fit.se_z[i, j] == pytest.approx(se, rel=1e-9)
            cell = payload["matrix"][i][j]
            assert cell["r"] == pytest.approx(r, rel=ROUNDED)
            assert cell["se_z"] == pytest.approx(se, rel=ROUNDED)
            z = math.atanh(r)
            assert cell["ci95"] == pytest.approx([math.tanh(z - t * se), math.tanh(z + t * se)],
                                                 rel=ROUNDED)
            assert cell["n_eff"] == pytest.approx(3 + 1 / se ** 2, rel=ROUNDED)
            assert cell["se_iid"] == pytest.approx(1 / math.sqrt(payload["n_hits"] - 3), rel=ROUNDED)


def test_phi_cells_carry_mardia_r_from_the_same_hits(single_client):
    payload = _get(single_client, table_name=SINGLE_HITS_TABLE)
    record = _record(single_client, SINGLE_HITS_TABLE)
    spec = filters.build(record)
    sql, params = _hits_sql(record, spec)
    event = _event_table(record)
    with single_client.app.state.database.read_cursor() as con:
        r_cs = _corr(con, sql, params, "c", "s")
        for i, name in enumerate(LINEAR):
            mardia = payload["matrix"][i][PHI]["mardia"]
            expected = jackknife.mardia_r(_corr(con, sql, params, name, "c"),
                                          _corr(con, sql, params, name, "s"), r_cs)
            assert 0.0 <= mardia["R"] <= 1.0 and mardia["se"] > 0
            assert mardia["R"] == pytest.approx(expected, rel=ROUNDED)
            per_shower = mardia["event_weighted_R"]
            assert (per_shower is not None) == (name in ("mom", "th"))
        # Per shower, each counted once: the event table's own rows.
        row = con.execute(
            f"SELECT corr(e1, theta_a), corr(theta_a, cos(phi_a)), corr(theta_a, sin(phi_a)), "
            f"corr(cos(phi_a), sin(phi_a)) FROM {event} WHERE {spec.where_sql()} AND n_hits > 0",
            spec.params()).fetchone()
    assert payload["matrix"][4][5]["event_weighted_r"] == pytest.approx(row[0], rel=ROUNDED)
    theta_phi = payload["matrix"][5][PHI]["mardia"]
    assert theta_phi["event_weighted_R"] == pytest.approx(
        jackknife.mardia_r(row[1], row[2], row[3]), rel=ROUNDED)
    assert payload["matrix"][PHI][PHI]["mardia"] is None
    assert any("Mardia" in note for note in payload["notes"])


def _first_events_of_bin(client, record, k: int) -> dict:
    """e1 bounds holding exactly the ``k`` lowest-momentum events of the 7-event bin 12."""
    with client.app.state.database.read_cursor() as con:
        moms = [m for (m,) in con.execute(
            f"SELECT e1 FROM {_event_table(record)} WHERE e1_bin = 12 ORDER BY e1").fetchall()]
    assert len(moms) == 7
    return {"e1_min": moms[0] - 1e-6, "e1_max": 0.5 * (moms[k - 1] + moms[k])}


def test_the_low_n_gates_follow_the_event_count(single_client):
    record = _record(single_client, SINGLE_HITS_TABLE)

    def cells(payload):
        return [payload["matrix"][i][j] for i in range(PHI) for j in range(PHI) if i != j]

    two = _get(single_client, table_name=SINGLE_HITS_TABLE, **_first_events_of_bin(single_client, record, 2))
    assert (two["n_events"], two["groups"], two["dof"]) == (2, 2, None)
    assert all(c["r"] is None for c in cells(two))
    assert two["interval"] == "none: a correlation needs at least 3 events; this selection has 2"

    three = _get(single_client, table_name=SINGLE_HITS_TABLE, **_first_events_of_bin(single_client, record, 3))
    assert (three["n_events"], three["groups"], three["dof"], three["weak"]) == (3, 3, None, True)
    assert three["matrix"][0][2]["r"] is not None
    assert all(c["ci95"] is None and c["n_eff"] is None for c in cells(three))
    assert three["interval"] == "none: an interval needs at least 4 event groups; this selection has 3"
    assert three["method"].endswith("too few for an interval, which needs 4")

    four = _get(single_client, table_name=SINGLE_HITS_TABLE, **_first_events_of_bin(single_client, record, 4))
    assert (four["n_events"], four["groups"], four["dof"], four["weak"]) == (4, 4, 3, True)
    assert four["method"] == "event-grouped jackknife, 4 groups (one event each)"
    assert four["interval"] == "95% event-grouped jackknife on Fisher z, 4 groups (Student-t, 3 dof)"
    assert four["matrix"][0][2]["ci95"] is not None
    assert any(note.startswith("Weak (N = 4 events)") and "3.18" in note for note in four["notes"])


def test_an_aggregated_experiment_has_no_hits_and_is_refused(single_client):
    problem = _refused(single_client, "table_name", table_name=SINGLE_EVENTS_TABLE)
    contract_check.check(problem, "capability_problem")
    assert problem["capability"] == "correlation"
    assert problem["kind"] == "single_shower_events"
    assert "no hits" in problem["reason"]


def test_bad_choices_are_refused_naming_the_field(single_client):
    contract_check.check(_refused(single_client, "shower", table_name=SINGLE_HITS_TABLE, shower="b"),
                         "capability_problem")
    _refused(single_client, "coord_system", table_name=SINGLE_HITS_TABLE, coord_system="canonical")
    _refused(single_client, "energy_scale", table_name=SINGLE_HITS_TABLE, energy_scale="ln")
    _refused(single_client, "e2_min", table_name=SINGLE_HITS_TABLE, e2_min=1.0)


def test_the_two_event_baseline_is_served_with_empty_cells(single_client):
    payload = _get(single_client, table_name=BASELINE_TABLE)
    assert (payload["n_events"], payload["groups"], payload["dof"]) == (2, 2, None)
    assert payload["showers"] == ["Shower A", "Shower B"]
    assert all(cell["r"] is None for row in payload["matrix"] for cell in row)


def test_preview_below_the_threshold_is_exact_and_a_repeat_is_cached(single_client):
    params = dict(table_name=SINGLE_HITS_TABLE, coord_system="trans", energy_scale="log10",
                  preview="true")
    first = _get(single_client, **params)
    again = _get(single_client, **params)
    assert first["meta"]["exact"] is True and first["meta"]["sample_percent"] == 100.0
    assert again["meta"]["cached"] is True
    assert again["matrix"] == first["matrix"]


def test_a_response_over_the_contract_is_served_and_says_so(single_client, monkeypatch):
    """49 cells cannot reach 100 KB; were they to, the response would say so, not shrink."""
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    response = single_client.get(URL, params={"table_name": SINGLE_HITS_TABLE})
    assert response.status_code == 200
    warnings = response.json()["meta"]["warnings"]
    assert any(w.endswith("2,000-byte contract and is served as it is.") for w in warnings)


# ---------------------------------------------------- synthetic_client --


@pytest.mark.parametrize("coord_system", ("local", "lab"))
@pytest.mark.parametrize("shower", ("both", "a", "b"))
def test_two_shower_matrices_are_served_under_the_contract(synthetic_client, shower, coord_system):
    payload = _get(synthetic_client, shower=shower, coord_system=coord_system)
    assert payload["n_events"] > jackknife.MAX_GROUPS
    assert (payload["groups"], payload["dof"]) == (64, 63)
    expected = {"both": ["Shower A", "Shower B"], "a": ["Shower A"], "b": ["Shower B"]}[shower]
    assert payload["showers"] == expected
    assert payload["n_showers"] >= payload["n_events"]
    _check_matrix(payload)


def test_two_shower_jackknife_and_hit_weighting_match_sql(synthetic_client):
    payload = _get(synthetic_client)
    record = _record(synthetic_client, BASELINE_TABLE)
    spec = filters.build(record)
    sql, params = _hits_sql(record, spec)
    with synthetic_client.app.state.database.read_cursor() as con:
        analysis = correlations.analyse(con, record, spec)
        for i, j in ((0, 2), (3, 5), (4, 5)):
            a, b = LINEAR[i], LINEAR[j]
            r = _corr(con, sql, params, a, b)
            se, groups = _sql_jackknife(con, sql, params, a, b, payload["n_events"])
            assert groups == payload["groups"] == 64
            assert payload["matrix"][i][j]["r"] == pytest.approx(r, rel=ROUNDED)
            assert payload["matrix"][i][j]["se_z"] == pytest.approx(se, rel=ROUNDED)
        # Per-shower pairs: the event table weighted by hits is the hit-level matrix.
        hit = analysis.hit.pearson()[4:, 4:]
        weighted = analysis.shower_w.pearson()
        assert weighted == pytest.approx(hit, abs=1e-9)
        assert analysis.shower_w_fit.se_z[0, 1] == pytest.approx(analysis.hit_fit.se_z[4, 5], rel=1e-9)
        # ... and each shower once is the plain correlation over the showers.
        event = _event_table(record)
        rows = con.execute(
            f"""SELECT corr(p, th) FROM (
                    SELECT e1 AS p, theta_a AS th FROM {event} WHERE {spec.where_sql()} AND n_a_rows > 0
                    UNION ALL
                    SELECT e2, theta_b FROM {event} WHERE {spec.where_sql()} AND n_b_rows + n_ab_rows > 0)""",
            spec.params()).fetchone()
    assert payload["matrix"][4][5]["event_weighted_r"] == pytest.approx(rows[0], rel=ROUNDED)


def test_a_small_separation_slice_is_weak_with_one_group_per_event(synthetic_client):
    payload = _get(synthetic_client, d_min=100, d_max=150, coord_system="trans")
    assert (payload["n_events"], payload["groups"], payload["dof"]) == (7, 7, 6)
    assert payload["weak"] is True
    assert payload["method"] == "event-grouped jackknife, 7 groups (one event each)"
    assert any(note.startswith("Weak (N = 7 events)") for note in payload["notes"])
    _check_matrix(payload)
