"""The Page 1 spatial views on a single-shower experiment, and their refusals.

``single_client`` holds the two-shower baseline, ``single_hits`` (synthetic
single-shower hits, 287 events in 1 GeV bins at the low-N populations) and
``single_events`` (its 59-column aggregate). One shower per event, stored
under the shower-A names, is served by the same lab, per-shower translated
and local code as two showers: one ``energy_voxel`` centroid with no partner
and no separation, ``b`` null wherever a second shower would be, and density
the only channel. What the data cannot serve is refused with a 422
``/problems/unsupported-capability`` naming the request field: the D-frame
(``frame``), an attention channel (``channel``), shower B (``shower``), and
every hit view of the aggregate. The two-shower output these views share is
pinned elsewhere (``test_golden_lab.py``, ``test_frames_shower.py``, ...).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import naming, registry
from calosrv.db.naming import quote
from calosrv.grid import frame as frame_mod
from calosrv.query import (
    canonical, capabilities, density, filters, frame_sql, planes, projections, shower_frames,
)
from calosrv.text import signed_hyphens

HITS = {"table_name": SINGLE_HITS_TABLE}
EVENTS = {"table_name": SINGLE_EVENTS_TABLE}

#: Bins of the synthetic file holding one, two and seven events.
ONE_EVENT = {"e1_min": 3.0, "e1_max": 3.99}
TWO_EVENTS = {"e1_min": 7.0, "e1_max": 7.99}
SEVEN_EVENTS = {"e1_min": 12.0, "e1_max": 12.99}


def _get(client, url: str, **params):
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text[:600]
    assert len(response.content) < density.RESPONSE_LIMIT
    return response.json()


def _refused(client, url: str, field: str, capability: str, kind: str, **params) -> dict:
    response = client.get(url, params=params)
    assert response.status_code == 422, response.text[:600]
    problem = response.json()
    contract_check.check(problem, "capability_problem")
    assert problem["field"] == field and problem["capability"] == capability, problem
    assert problem["kind"] == kind and problem["reason"]
    return problem


def _strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


@pytest.fixture(scope="module")
def db(single_client):
    """The booted app's database, and the single-shower record."""
    database = single_client.app.state.database
    with database.read_cursor() as con:
        record = registry.require_ready(con, SINGLE_HITS_TABLE)
    return {"database": database, "record": record, "settings": single_client.app.state.settings}


def _hits(db) -> dict[str, np.ndarray]:
    """Every hit of the single-shower experiment: lattice ordinals and energy."""
    proj = quote(naming.proj_table(SINGLE_HITS_TABLE))
    with db["database"].read_cursor() as con:
        columns = con.execute(f"SELECT ix, iy, iz, energy FROM {proj}").fetchnumpy()
    return {name: np.asarray(values) for name, values in columns.items()}


def _event_values(db, sql: str, params: dict | None = None):
    """One row of ``sql``, with ``{event}`` standing for the single-shower event table."""
    event = quote(naming.event_table(SINGLE_HITS_TABLE))
    with db["database"].read_cursor() as con:
        return con.execute(sql.format(event=event), params or {}).fetchone()


# -------------------------------------------------------------- catalogue --


def test_the_catalogue_offers_the_three_frames_and_density_only(single_client):
    listed = {e["table_name"]: e for e in single_client.get("/api/experiments").json()["experiments"]}
    hits, aggregate = listed[SINGLE_HITS_TABLE], listed[SINGLE_EVENTS_TABLE]
    assert hits["frames"] == ["lab", "trans", "local"] == hits["coord_systems"]
    assert hits["channels"] == ["density"] and hits["models"] == []
    panels = hits["capabilities"]["panels"]
    for gate in ("xy", "yz", "xz", "frame-lab", "frame-trans", "frame-local",
                 "window-axis", "event-inspector", "compare"):
        assert panels[gate] is True, gate
    assert panels["frame-canonical"] is False
    assert "two showers" in hits["capabilities"]["reasons"]["frame-canonical"]
    assert aggregate["frames"] == [] and aggregate["channels"] == []
    for gate in ("xy", "window-axis", "event-inspector", "compare"):
        assert aggregate["capabilities"]["panels"][gate] is False
        assert "no hits" in aggregate["capabilities"]["reasons"][gate]


# ------------------------------------------------------------- lab frame --


def test_the_lab_payload_has_the_two_shower_keys(single_client):
    """One envelope for both kinds: the frontend reads it with the same code."""
    single = _get(single_client, "/api/projections", **HITS)
    baseline = _get(single_client, "/api/projections", table_name=BASELINE_TABLE)
    assert set(single) == set(baseline) and "frame" not in single
    for block in ("selection", "overlays", "slab", "filter"):
        assert set(single[block]) == set(baseline[block]), block
    assert set(single["meta"]) == set(baseline["meta"])
    assert set(single["panels"]) == {"xy", "yz", "xz"}


def test_the_lab_panels_hold_the_selection_density(single_client, db):
    body = _get(single_client, "/api/projections", **HITS)
    assert body["meta"]["channel"] == "density" and "cam" not in body["meta"]
    hits = _hits(db)
    total = float(hits["energy"].sum())
    for name in ("yz", "xz"):
        assert body["panels"][name]["total"] == pytest.approx(total, rel=1e-9)
    slab = hits["iz"] <= db["record"].lattice.slab_iz
    assert body["panels"]["xy"]["total"] == pytest.approx(float(hits["energy"][slab].sum()), rel=1e-9)


def test_the_bundle_measures_energy_and_count_only(db):
    record = db["record"]
    assert planes.measures_for(record, "lab", "segmentation") == planes.DENSITY_MEASURES
    assert planes.measured_planes(record) == ("e", "n")
    spec = filters.build(record)
    xy_sql, depth_sql = projections.build_sql(record, spec, False)
    for sql in (xy_sql, depth_sql):
        assert "fa_" not in sql and "gc_" not in sql and "sc_" not in sql
    with db["database"].read_cursor() as con:
        bundle = projections.fetch_native(con, record, spec)
        plan = projections.explain(con, record, spec)
    assert bundle.showers == ("a",)
    table = naming.proj_table(record.table_name)
    for part in plan.split("\n----\n"):
        assert part.count(table) == 1
    for panel in (bundle.xy, bundle.yz, bundle.xz):
        assert set(panel.planes) == set(planes.PLANES)
        for name in planes.PLANES:
            if name not in ("e", "n"):
                assert not panel.planes[name].any(), name
    assert bundle.n_hits == record.n_hits


def test_the_lab_centroid_is_the_one_showers_energy_weighted_centroid(single_client, db):
    body = _get(single_client, "/api/projections", **HITS)
    centroids = body["centroids"]
    assert set(centroids) == {"energy_voxel", "truth_dataset"}
    voxel = centroids["energy_voxel"]
    assert voxel["b"] is None and voxel["separation_mm"] is None
    lattice = db["record"].lattice
    hits = _hits(db)
    slab = hits["iz"] <= lattice.slab_iz
    e = hits["energy"]
    x = np.asarray(lattice.x.coords)[hits["ix"].astype(int)]
    y = np.asarray(lattice.y.coords)[hits["iy"].astype(int)]
    z = np.asarray(lattice.z.coords)[hits["iz"].astype(int)]
    assert voxel["a"]["x"] == pytest.approx(float(np.average(x[slab], weights=e[slab])), abs=1e-6)
    assert voxel["a"]["y"] == pytest.approx(float(np.average(y[slab], weights=e[slab])), abs=1e-6)
    # Depth from every layer, as the two-shower pair takes it from the YZ panel.
    assert voxel["a"]["z"] == pytest.approx(float(np.average(z, weights=e)), abs=1e-6)
    assert voxel["a"]["energy"] == pytest.approx(float(e[slab].sum()), rel=1e-9)

    dataset = centroids["truth_dataset"]
    assert dataset == body["selection"]["centroid_dataset"]
    assert dataset["b"] is None and dataset["separation_mm"] is None
    cax, cay, caz = _event_values(db, "SELECT avg(cax), avg(cay), avg(caz) FROM {event}")
    assert (dataset["a"]["x"], dataset["a"]["y"], dataset["a"]["z"]) == pytest.approx((cax, cay, caz))


def test_the_selection_summary_has_no_separation_or_second_shower(single_client, db):
    selection = _get(single_client, "/api/projections", **HITS)["selection"]
    n, hits, e_dep, e1 = _event_values(db, "SELECT count(*), sum(n_hits), sum(e_dep), avg(e1) FROM {event}")
    assert selection["n_events"] == n == 287 and selection["n_hits"] == hits
    assert selection["e_dep_total"] == pytest.approx(e_dep) and selection["e1_mean"] == pytest.approx(e1)
    assert selection["n_events_no_d"] is None and selection["e2_mean"] is None
    assert set(selection["d"].values()) == {None}


def test_the_lab_overlays_carry_one_shower(single_client, db):
    many = _get(single_client, "/api/projections", **HITS)["overlays"]
    # Above the trajectory threshold: the centre of deposited energy per layer, A only.
    assert many["trajectories"] == []
    for name in ("yz", "xz"):
        assert many["axes"][name]["b"] == [] and any(p is not None for p in many["axes"][name]["a"])
    coherence, pointing = many["coherence"], many["pointing"]
    assert coherence["r_b"] is None and coherence["theta_b_mean"] is None
    c, s, n = _event_values(db, "SELECT avg(cos(phi_a)), avg(sin(phi_a)), count(*) FROM {event}")
    assert coherence["n"] == n and coherence["r_a"] == pytest.approx(math.hypot(c, s))
    assert pointing["b"] is None and pointing["a"]["n"] == n
    assert "A:" not in pointing["note"] and "B:" not in pointing["note"]

    few = _get(single_client, "/api/projections", **HITS, **SEVEN_EVENTS)["overlays"]
    assert few["axes"] == {} and len(few["trajectories"]) == 7
    for entry in few["trajectories"]:
        assert set(entry) == {"event", "a"}
        assert set(entry["a"]) == {"theta", "phi", "x", "y", "z"}

    one = _get(single_client, "/api/projections", **HITS, **ONE_EVENT)["overlays"]
    assert len(one["trajectories"]) == 1 and one["pointing"]["a"]["sd_deg"] is None
    assert "for its one event" in one["pointing"]["note"]


@pytest.mark.parametrize("display", ["native", "continuous"])
def test_the_lab_frame_serves_every_low_n_rung(single_client, display):
    for bounds in ({}, ONE_EVENT, TWO_EVENTS, SEVEN_EVENTS):
        body = _get(single_client, "/api/projections", **HITS, display=display, resolution=400, **bounds)
        assert body["centroids"]["energy_voxel"]["b"] is None


# ---------------------------------------------------- per-shower frames --


@pytest.mark.parametrize("kind", ["trans", "local"])
def test_the_per_shower_frames_superimpose_one_shower_per_event(single_client, db, kind):
    body = _get(single_client, "/api/projections", **HITS, coord_system=kind)
    frame = body["frame"]
    assert frame["kind"] == kind
    assert frame["n_events"] == frame["n_showers"] == frame["n_selected"] == 287
    assert frame["n_excluded_no_frame"] == 0 and frame["n_ab_hits"] == 0
    assert frame["d_dataset"] == {"mean": None, "ci95_half": None, "sd": None, "n": 0}
    assert frame["phi_resultant"]["b"] is None and frame["phi_resultant"]["a"] is not None
    assert "no separation D" in frame["anchor_note"]
    # Every selected hit is in a panel or counted outside the accumulation grid.
    total = float(_hits(db)["energy"].sum())
    for name in ("xy", "yz", "xz"):
        panel = body["panels"][name]
        assert panel["total_energy_all_gev"] >= panel["total"] - 1e-12
    xz = body["panels"]["xz"]
    assert xz["total_energy_all_gev"] + frame["window"]["energy_outside_gev"] == pytest.approx(total, rel=1e-9)

    centroids = body["centroids"]
    assert set(centroids) == {"energy_voxel", "frame_mean"}
    assert centroids["energy_voxel"]["b"] is None and centroids["energy_voxel"]["offset_mm"] is None
    mean = centroids["frame_mean"]
    assert mean["b"] is None and mean["sd"]["b"] is None and mean["ci95_half"]["b"] is None
    suffix = "_t" if kind == "trans" else "_l"
    n, cx, sx = _event_values(db, f"SELECT count(*), avg(cax{suffix}), stddev_samp(cax{suffix}) FROM {{event}}")
    assert mean["n"] == n and mean["a"]["x"] == pytest.approx(cx) and mean["sd"]["a"]["x"] == pytest.approx(sx)
    t = frame_mod.t_quantile_975(n - 1)
    assert mean["ci95_half"]["a"]["x"] == pytest.approx(t * sx / math.sqrt(n))

    texts = [notice["text"] for notice in body["meta"]["notices"]]
    assert any("one per event" in text for text in texts)
    assert not any("A+B" in text or "A-B" in text or "both showers" in text for text in texts)
    assert not any(notice["scope"] == "separation" for notice in body["meta"]["notices"])


@pytest.mark.parametrize("kind", ["trans", "local"])
@pytest.mark.parametrize("bounds", [ONE_EVENT, TWO_EVENTS, SEVEN_EVENTS], ids=["n1", "n2", "n7"])
def test_the_per_shower_frames_follow_the_low_n_table(single_client, kind, bounds):
    body = _get(single_client, "/api/projections", **HITS, coord_system=kind, display="continuous", **bounds)
    mean, n = body["centroids"]["frame_mean"], body["frame"]["n_events"]
    assert body["frame"]["fit"]["provisional"] is True
    if n == 1:
        assert "not an ensemble mean" in mean["label"] and mean["sd"]["a"]["x"] is None
        assert "own centroid;" in mean["dof_note"]
    else:
        assert mean["ci95_half"]["a"]["x"] is not None and "weak evidence" in mean["dof_note"]
    if kind == "trans":
        paths = body["overlays"]["trajectories"]
        assert len(paths) == n and all(set(p) == {"event", "a"} for p in paths)
        assert all(p["a"]["x"] == p["a"]["y"] == p["a"]["z"] == 0.0 for p in paths)
        assert body["frame"]["coherence"]["r_b"] is None
    else:
        assert body["overlays"] == {} and "coherence" not in body["frame"]


@pytest.mark.parametrize("kind", ["trans", "local"])
def test_the_per_shower_frames_scan_the_projection_table_once(db, kind):
    record = db["record"]
    spec = filters.build(record)
    with db["database"].read_cursor() as con:
        footprint = canonical.cell_footprint(con, record)
        bundle, stats, grid, k, _ = shower_frames.bundle_for(
            con, record, spec, db["settings"], kind, footprint, False, 100.0)
        plan = shower_frames.explain(con, record, spec, grid, kind, footprint, k, bundle.k_z)
    assert stats.showers == ("a",) and stats.n_showers == stats.n_events == 287
    assert bundle.showers == ("a",)
    table = naming.proj_table(record.table_name)
    for part in plan.split("\n----\n"):
        assert part.count(table) == 1
    for name in planes.PLANES:
        if name not in ("e", "n"):
            assert not bundle.xz.planes[name].any(), name
    assert bundle.n_hits == record.n_hits


@pytest.mark.parametrize("kind", ["trans", "local"])
def test_the_frame_sql_keeps_the_two_shower_text_and_gates_one_shower_on_its_frame(db, kind):
    """Two showers: the default ``fr`` CTE, verbatim. One: its own row, gated, no separation."""
    with db["database"].read_cursor() as con:
        two = registry.require_ready(con, BASELINE_TABLE)
    for record in (two, db["record"]):
        spec = filters.build(record)
        event = quote(naming.event_table(record.table_name))
        proj = quote(naming.proj_table(record.table_name))
        columns = ", ".join(f"p.{c}" for c in shower_frames._plane_columns(record, "energy", kind))
        sql = shower_frames._hit_frame_sql(kind, record, spec, columns, proj, event, 20.5)
        if record is two:
            assert columns.count("p.") == 4
            assert sql.startswith(frame_sql.shower_frame_cte(event, spec.where_sql(), kind))
            assert "AND p.d IS NOT NULL" in sql
        else:
            assert columns == ""
            gate = capabilities.frame_gate(record)
            assert sql.startswith(frame_sql.shower_frame_cte(
                event, spec.where_sql(), kind, showers=("a",), gate=gate))
            assert "UNION ALL" not in sql and "p.d " not in sql and gate in sql


@pytest.mark.parametrize("kind", ["trans", "local"])
def test_computed_coordinates_and_the_dataset_reference_serve_one_shower(single_client, kind):
    computed = _get(single_client, "/api/projections", **HITS, coord_system=kind, coordinates="computed")
    block = computed["frame"]["coordinates"]
    assert block["source"] == "computed" and block["within_tolerance"] is True
    dataset = _get(single_client, "/api/projections", **HITS, coord_system=kind, rho_norm="dataset")
    assert dataset["frame"]["rho"]["norm"] == "dataset"


@pytest.mark.parametrize("kind", ["lab", "trans", "local"])
def test_an_empty_selection_is_served_as_empty(single_client, kind):
    body = _get(single_client, "/api/projections", **HITS, coord_system=kind, e1_min=0.0, e1_max=0.5)
    assert body["selection"]["n_events"] == 0
    assert body["centroids"]["energy_voxel"]["a"]["x"] is None


def test_an_empty_selection_has_no_event_to_pick(single_client):
    response = single_client.get("/api/event/pick", params={**HITS, "e1_min": 0.0, "e1_max": 0.5})
    assert response.status_code == 404
    assert "incident direction and an entry point" in response.json()["detail"]


def test_the_compare_view_serves_all_three_frames(single_client):
    """The compare-frames view is the three frames' projections of one selection."""
    totals = {}
    for kind in ("lab", "trans", "local"):
        body = _get(single_client, "/api/projections", **HITS, **SEVEN_EVENTS, coord_system=kind)
        assert body["meta"]["coord_system"] == kind
        totals[kind] = body["selection"]["n_events"]
    assert set(totals.values()) == {7}


# ------------------------------------------------------------ window axis --


def test_the_window_axis_has_one_shower_block(single_client, db):
    body = _get(single_client, "/api/window-axis", **HITS, panel="xz", t_min=-1e5, t_max=1e5)
    assert body["b"] is None and len(body["notes"]) == 1
    (n,) = _event_values(db, "SELECT count(*) FROM {event} WHERE theta_a IS NOT NULL "
                             "AND phi_a IS NOT NULL AND cax IS NOT NULL")
    block = body["a"]
    assert block["n"] == block["n_selection"] == n
    assert len(block["band"]) == len(block["envelope"]) == body["stations"]
    assert body["notes"][0].startswith("Shower: N = ")
    assert body["meta"]["notices"][0]["text"] == body["notes"][0]

    narrow = _get(single_client, "/api/window-axis", **HITS, **ONE_EVENT, panel="yz", t_min=-1e5, t_max=1e5)
    assert narrow["a"]["n"] == 1 and narrow["a"]["label"] == "single event, not an ensemble"
    assert narrow["a"]["band"] is None and narrow["b"] is None
    empty = _get(single_client, "/api/window-axis", **HITS, panel="yz", t_min=1e6, t_max=1e6 + 1)
    assert empty["a"]["n"] == 0 and "no selected event enters" in empty["notes"][0]


# ---------------------------------------------------------- event inspector --


def test_the_pick_rule_ranks_the_one_showers_polar_angle(single_client, db):
    picked = _get(single_client, "/api/event/pick", **HITS, seed=42)
    assert picked["n_events"] == 287 and picked["event_number"] in picked["pool"]
    assert "incident polar angle" in picked["rule"] and "two showers" not in picked["rule"]
    assert "separation" not in picked["rule"]
    event = quote(naming.event_table(SINGLE_HITS_TABLE))
    with db["database"].read_cursor() as con:
        mean_hits = con.execute(f"SELECT avg(n_hits) FROM {event}").fetchone()[0]
        expected = [r[0] for r in con.execute(
            f"SELECT event_number FROM {event} WHERE n_hits > ? "
            "ORDER BY theta_a DESC, event_number LIMIT 20", [mean_hits]).fetchall()]
    assert picked["pool"] == expected
    assert picked["mean_hits"] == pytest.approx(mean_hits)


def test_the_event_inspector_draws_the_one_shower(single_client, db):
    picked = _get(single_client, "/api/event/pick", **HITS, seed=7)
    number = picked["event_number"]
    body = _get(single_client, "/api/event", **HITS, event_number=number)
    assert set(body["frames"]) == {"lab", "trans", "local"}
    event = body["event"]
    assert event["d"] is None and event["e2"] is None and event["overlap"] is None
    assert event["shower"]["key"] == "a" and event["shower"]["label"] == "Shower"
    proj = quote(naming.proj_table(SINGLE_HITS_TABLE))
    n, energy, e1 = _event_values(db, f"SELECT count(*), sum(energy), any_value(e1) FROM {proj} "
                                      "WHERE event_number = $ev", {"ev": number})
    assert event["n_hits"] == event["shower"]["n_hits"] == n
    assert event["shower"]["energy_gev"] == pytest.approx(energy, rel=1e-9)
    assert event["shower"]["momentum_gev"] == pytest.approx(e1) == event["e1"]
    assert body["coordinates"]["within_tolerance"] is True
    computed = _get(single_client, "/api/event", **HITS, event_number=number, coordinates="computed")
    assert computed["coordinates"]["source"] == "computed"


def test_a_single_hit_event_is_drawn(single_client, db):
    (number,) = _event_values(db, "SELECT min(event_number) FROM {event} WHERE n_hits = 1")
    body = _get(single_client, "/api/event", **HITS, event_number=number)
    assert body["event"]["shower"]["n_hits"] == 1


# ------------------------------------------------------------- refusals --


def test_the_d_frame_is_refused_naming_frame(single_client):
    for display in ("native", "continuous"):
        problem = _refused(single_client, "/api/projections", "frame", "frame-canonical",
                           "single_shower_hits", **HITS, frame="canonical", display=display)
        assert "two showers" in problem["reason"]


@pytest.mark.parametrize("channel", ["gradcam", "gradcam_energy", "shapcam", "shapcam_energy"])
@pytest.mark.parametrize("coord_system", ["lab", "trans", "local"])
def test_an_attention_channel_is_refused_naming_channel(single_client, channel, coord_system):
    problem = _refused(single_client, "/api/projections", "channel", "channel", "single_shower_hits",
                       **HITS, channel=channel, coord_system=coord_system)
    assert "density" in problem["reason"]


def test_shower_b_is_refused_naming_shower(single_client):
    picked = _get(single_client, "/api/event/pick", **HITS)
    _refused(single_client, "/api/event", "shower", "shower", "single_shower_hits",
             **HITS, event_number=picked["event_number"], shower="b")
    # An unknown shower is still the plain validation error it always was.
    bad = single_client.get("/api/event", params={**HITS, "event_number": picked["event_number"],
                                                  "shower": "c"})
    assert bad.status_code == 422 and bad.json()["field"] == "shower"


@pytest.mark.parametrize("url,params,capability", [
    ("/api/projections", {}, "xy"),
    ("/api/projections", {"coord_system": "trans"}, "xy"),
    ("/api/projections", {"coord_system": "local"}, "xy"),
    ("/api/projections", {"frame": "canonical"}, "xy"),
    ("/api/window-axis", {"panel": "xz", "t_min": -100.0, "t_max": 100.0}, "window-axis"),
    ("/api/event", {"event_number": 1}, "event-inspector"),
    ("/api/event/pick", {}, "event-inspector"),
], ids=["lab", "trans", "local", "canonical", "window-axis", "event", "pick"])
def test_every_hit_view_of_the_aggregate_is_refused(single_client, url, params, capability):
    problem = _refused(single_client, url, "table_name", capability, "single_shower_events",
                       **EVENTS, **params)
    assert "no hits" in problem["reason"]


def test_two_shower_cuts_are_refused_before_any_view(single_client):
    response = single_client.get("/api/projections", params={**HITS, "d_min": 10.0})
    assert response.status_code == 422 and response.json()["field"] == "d_min"


# ------------------------------------------------------------ typography --


def test_no_single_shower_sentence_signs_a_number_with_a_hyphen(single_client):
    picked = _get(single_client, "/api/event/pick", **HITS, seed=7)
    bodies = [
        _get(single_client, "/api/event", **HITS, event_number=picked["event_number"]),
        _get(single_client, "/api/window-axis", **HITS, panel="xz", t_min=-500.0, t_max=500.0),
        picked,
    ]
    for kind in ("lab", "trans", "local"):
        for bounds in ({}, ONE_EVENT):
            bodies.append(_get(single_client, "/api/projections", **HITS, coord_system=kind,
                               display="continuous", **bounds))
    for body in bodies:
        for path, text in _strings(body):
            if path.endswith(("data", ".table_name", "source_files")):
                continue
            assert not signed_hyphens(text), (path, signed_hyphens(text))


# ------------------------------------------------------- C9 in the Local frame --

@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, BASELINE_TABLE])
def test_the_local_frame_carries_the_negative_depth_block(single_client, table):
    """The Local frame embeds /api/statistics' C9 block for the same selection, and only it."""
    local = _get(single_client, "/api/projections", table_name=table, coord_system="local")
    block = local["frame"]["negative_w"]
    contract_check.check(block, "statistics", at="negative_w")
    stats = _get(single_client, "/api/statistics", table_name=table)
    assert block == stats["negative_w"]
    assert block["available"] is True and "−" in block["summary"]
    trans = _get(single_client, "/api/projections", table_name=table, coord_system="trans")
    assert "negative_w" not in trans["frame"]
    lab = _get(single_client, "/api/projections", table_name=table)
    assert "frame" not in lab
