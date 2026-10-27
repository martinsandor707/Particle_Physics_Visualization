"""The Event Inspector: one shower of one event in the three frames.

The per-event figure of ``local-coords.ipynb`` (cell 6), server-rendered:
energy conservation in every frame, the SE(3) residual against the file's
columns, the one shared colour ramp, the notebook's window and selection
rules, the marks, the budget, and the route's contract.
"""

from __future__ import annotations

import json
import math
import re

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.grid import footprint as footprint_mod
from calosrv.grid import frame as frame_mod
from calosrv.query import canonical, density, event_inspector, filters, frame_sql
from calosrv.stats import shape


@pytest.fixture(scope="module")
def inspected(ingested):
    from calosrv.db import registry

    database = ingested["database"]
    with database.read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)
        events = [r[0] for r in con.execute(
            f"SELECT event_number FROM {quote(naming.event_table(record.table_name))} "
            "WHERE d IS NOT NULL ORDER BY event_number").fetchall()]
        bodies = {}
        for event in events:
            for shower in ("a", "b"):
                bodies[event, shower] = event_inspector.inspect(con, record, spec, event, shower,
                                                                frame_sql.SOURCE_FILE, footprint)
    return {"record": record, "spec": spec, "footprint": footprint, "events": events, "bodies": bodies}


def _shower_energy(cursor, record, event, shower):
    proj = quote(naming.proj_table(record.table_name))
    origin = "org = 0" if shower == "a" else "org IN (1, 2)"
    return cursor.execute(
        f"SELECT coalesce(sum(energy), 0), count(*) FROM {proj} WHERE event_number = ? AND {origin}",
        [event]).fetchone()


# ------------------------------------------------------------- the figure --


def test_every_frame_holds_the_showers_whole_energy(cursor, inspected):
    """Nine panels, three frames: each projects the same cells and conserves their energy."""
    for (event, shower), body in inspected["bodies"].items():
        energy, n = _shower_energy(cursor, inspected["record"], event, shower)
        assert body["event"]["shower"]["n_hits"] == n
        assert body["event"]["shower"]["energy_gev"] == pytest.approx(energy, rel=1e-12)
        for kind in event_inspector.FRAMES:
            frame = body["frames"][kind]
            assert set(frame["panels"]) == set(event_inspector.PANELS)
            for name, panel in frame["panels"].items():
                assert panel["total"] + panel["energy_outside_window_gev"] == pytest.approx(energy, rel=1e-9)
                assert panel["total_energy_all_gev"] == pytest.approx(energy, rel=1e-12)
                assert panel["kernel"] == "none" and panel["n_events"] == 1
                assert panel["rho_unit"] == event_inspector.UNIT
                assert panel["axes"]["col"]["name"] == event_inspector._PANEL_AXES[name][1]
                assert panel["axes"]["row"]["name"] == event_inspector._PANEL_AXES[name][0]
            # The lab panels are the native lattice: irregular x edges travel.
            if kind == "lab":
                assert frame["panels"]["xy"]["axes"]["col"]["uniform"] is False or \
                    frame["panels"]["xy"]["axes"]["col"]["n"] == 1


def test_the_motions_reproduce_the_files_columns_within_tolerance(inspected):
    for body in inspected["bodies"].values():
        block = body["coordinates"]
        assert block["source"] == "file" and block["within_tolerance"] is True
        assert 0.0 <= block["residual_max_mm"] <= block["tolerance_mm"] == 0.01


def test_the_computed_source_bins_the_motions_coordinates(cursor, inspected):
    event, shower = inspected["events"][0], "a"
    file_body = inspected["bodies"][event, shower]
    computed = event_inspector.inspect(cursor, inspected["record"], inspected["spec"], event, shower,
                                       frame_sql.SOURCE_COMPUTED, inspected["footprint"])
    assert computed["coordinates"]["source"] == "computed"
    assert computed["coordinates"]["residual_max_mm"] == pytest.approx(
        file_body["coordinates"]["residual_max_mm"], abs=1e-9)
    assert computed["event"]["shower"]["energy_gev"] == pytest.approx(file_body["event"]["shower"]["energy_gev"])
    for kind in ("trans", "local"):
        a = computed["frames"][kind]["panels"]["xy"]
        b = file_body["frames"][kind]["panels"]["xy"]
        assert a["total"] + a["energy_outside_window_gev"] == pytest.approx(
            b["total"] + b["energy_outside_window_gev"], rel=1e-9)


def test_one_ramp_for_all_nine_panels(inspected):
    for body in inspected["bodies"].values():
        scale = body["scale"]
        assert scale["unit"] == event_inspector.UNIT
        assert scale["top"] >= scale["floor"] > 0
        for kind in event_inspector.FRAMES:
            for panel in body["frames"][kind]["panels"].values():
                s = panel["scale"]
                assert (s["vmin"], s["vmax"]) == (scale["vmin"], scale["vmax"])
                assert s["unit"] == event_inspector.UNIT and s["scale"] == "log10" and s["locked"] is True
                assert s["clipped_high"] == 0, "the top is the brightest bin, so nothing is above it"
        assert scale["n_below"] == sum(
            body["frames"][k]["panels"][n]["scale"]["clipped_low"]
            for k in event_inspector.FRAMES for n in event_inspector.PANELS)
        assert "1st percentile" in scale["rule"]


def _percentile_cells(values, weights):
    """The cells at the energy-weighted 0.1st and 99.9th percentiles, re-derived for the test."""
    order = np.argsort(values, kind="stable")
    v, c = values[order], np.cumsum(np.clip(weights[order], 0, None))
    total = c[-1]
    i0 = min(int(np.searchsorted(c, 0.001 * total, side="right")), v.size - 1)
    i1 = min(max(int(np.searchsorted(c, 0.999 * total, side="left")), i0), v.size - 1)
    return float(v[i0]), float(v[i1])


def test_the_window_is_the_energy_weighted_percentile_rule_and_the_rasters_lie_inside_it(cursor, inspected):
    """Decision D-3: the widest energy-weighted 0.1-99.9% range over the six coordinates, floor 150 mm."""
    record = inspected["record"]
    assert event_inspector.WINDOW_PERCENTILES == (0.1, 99.9)
    for (event, shower), body in inspected["bodies"].items():
        proj = quote(naming.proj_table(record.table_name))
        origin = "org = 0" if shower == "a" else "org IN (1, 2)"
        rows = cursor.execute(
            f"SELECT ix, iy, iz, xt, yt, kt, xl, yl, zl, energy FROM {proj} WHERE event_number = ? AND {origin}",
            [event]).fetchnumpy()
        lat = record.lattice
        x, y, z = (lat.axis(a).coords[np.asarray(rows[i], int)] for a, i in (("x", "ix"), ("y", "iy"), ("z", "iz")))
        xt, yt = (np.asarray(rows[c], float) for c in ("xt", "yt"))
        zt = np.asarray(rows["kt"], float) * body["footprint_mm"][2]
        xl, yl, zl = (np.asarray(rows[c], float) for c in ("xl", "yl", "zl"))
        energy = np.asarray(rows["energy"], float)
        snap = event_inspector.WINDOW_SNAP_MM
        half = 0.0
        for v in (x, y, z, xt, yt, zt, zl):
            lo, hi = _percentile_cells(v, energy)
            centre = round(0.5 * (lo + hi) / snap) * snap
            half = max(half, hi - centre, centre - lo)
        for v in (xl, yl):
            half = max(half, *map(abs, _percentile_cells(v, energy)))
        # Plus one cell footprint (the cells at either end drawn whole), floor 150 mm, snapped to 20 mm.
        half = max(math.ceil((half + max(body["footprint_mm"])) / snap - 1e-9) * snap,
                   event_inspector.WINDOW_MIN_HALF_MM)
        assert body["window"]["percentiles"] == [0.1, 99.9]
        assert "0.1st–99.9th percentile" in body["window"]["rule"]
        assert "nine" not in body["window"]["rule"] and "nine" not in body["scale"]["rule"]
        # The cells beyond each frame's window are counted (D-3), and the rule names them.
        for kind in event_inspector.FRAMES:
            out = body["frames"][kind]["outside_window"]
            cells = np.unique(np.column_stack([rows["ix"], rows["iy"], rows["iz"]]), axis=0).shape[0]
            assert out["n_cells_total"] == cells and 0 <= out["n_cells"] <= cells
            # Each axis leaves at most 0.1% of the energy past either end of its percentile range.
            assert 0.0 <= out["fraction"] <= 0.006 + 1e-12
            if out["n_cells"]:
                assert f"{out['n_cells']:,} of {cells:,} cells" in body["window"]["rule"]
        assert body["window"]["half_mm"] == pytest.approx(half)
        for kind in event_inspector.FRAMES:
            frame = body["frames"][kind]
            assert frame["half_mm"] == pytest.approx(half)
            # The window edges are 20 mm bin edges, so the grid rasters end on them (the 150 mm floor aside).
            for axis in ("xyz" if half > event_inspector.WINDOW_MIN_HALF_MM else ""):
                for edge in frame["window"][axis]:
                    assert edge / snap == pytest.approx(round(edge / snap), abs=1e-9), (kind, axis, edge)
            for axis in "xyz":
                lo, hi = frame["window"][axis]
                assert hi - lo == pytest.approx(2 * half)
            # The local transverse window is the notebook's lim0: symmetric about the origin.
            if kind == "local":
                assert frame["window"]["x"] == pytest.approx([-half, half])
                assert frame["window"]["y"] == pytest.approx([-half, half])
            # Every raster lies within its window: the grid rasters exactly, the
            # lattice crops to within half a cell - half the widest lattice gap,
            # since x has module-boundary gaps and a cell's edge sits midway.
            for axis in "xyz":
                lo, hi = frame["window"][axis]
                r_lo, r_hi = frame["raster"][axis]
                tolerance = 1e-6 if kind != "lab" else 0.5 * float(np.diff(lat.axis(axis).coords).max()) + 1e-6
                assert r_lo >= lo - tolerance and r_hi <= hi + tolerance, (kind, axis)


def test_the_marks_are_the_notebooks_overlays(inspected):
    for (event, shower), body in inspected["bodies"].items():
        info = body["event"]["shower"]
        n = frame_mod.unit_direction(info["theta"], info["phi"])
        np.testing.assert_allclose(info["direction"], n, atol=1e-12)
        for kind in event_inspector.FRAMES:
            marks = {m["name"]: m for m in body["frames"][kind]["marks"]}
            assert "Incident direction (forward)" in marks and "Extrapolated backward" in marks
            assert "Shower origin (1st layer centre of mass)" in marks
            forward = marks["Incident direction (forward)"]
            origin = marks["Shower origin (1st layer centre of mass)"]["at"]
            if kind == "lab":
                np.testing.assert_allclose(origin, info["p0"])
                np.testing.assert_allclose(forward["direction"], n, atol=1e-12)
                plane = marks["1st layer plane (z = z₀)"]
                assert plane["axis"] == "z" and plane["at"] == pytest.approx(info["first_layer_z"])
            elif kind == "trans":
                np.testing.assert_allclose(origin, [0.0, 0.0, 0.0])
                np.testing.assert_allclose(forward["direction"], n, atol=1e-12)
                assert marks["1st layer plane (z = z₀)"]["at"] == pytest.approx(0.0)
            else:
                np.testing.assert_allclose(origin, [0.0, 0.0, 0.0])
                np.testing.assert_allclose(forward["direction"], [0.0, 0.0, 1.0], atol=1e-12)
                plane = marks["1st layer plane"]
                assert plane["panels"] == ["xz"]
                assert plane["direction"][2] == pytest.approx(math.tan(info["theta"]))


def test_the_principal_axis_is_the_notebooks_statistic(cursor, inspected):
    record = inspected["record"]
    for (event, shower), body in inspected["bodies"].items():
        proj = quote(naming.proj_table(record.table_name))
        origin = "org = 0" if shower == "a" else "org IN (1, 2)"
        rows = cursor.execute(f"SELECT xl, yl, zl, energy FROM {proj} WHERE event_number = ? AND {origin}",
                              [event]).fetchnumpy()
        pts = np.column_stack([np.asarray(rows[c], float) for c in ("xl", "yl", "zl")])
        w = np.asarray(rows["energy"], float)
        tilt = body["event"]["shower"]["principal_axis"]
        if pts.shape[0] < shape.MIN_POINTS:
            assert tilt is None
            continue
        d = pts - np.average(pts, axis=0, weights=w)
        cov = (d * w[:, None]).T @ d / w.sum()
        _, vecs = np.linalg.eigh(cov)
        expected = math.degrees(math.acos(min(1.0, abs(float(vecs[2, -1])))))
        assert tilt["tilt_deg"] == pytest.approx(expected, abs=1e-9)
        assert tilt["n"] == pts.shape[0] and tilt["axis"][2] >= 0


def test_a_single_cell_has_no_principal_axis():
    assert shape.principal_axis(np.zeros((2, 3)), np.ones(2)) is None
    assert shape.principal_axis(np.random.default_rng(1).normal(size=(5, 3)), np.zeros(5)) is None
    axis = shape.principal_axis(np.column_stack([np.zeros(4), np.zeros(4), np.arange(4.0)]), np.ones(4))
    assert axis["tilt_deg"] == pytest.approx(0.0) and axis["axis"][2] == pytest.approx(1.0)


# -------------------------------------------------------- the footprints --


def test_box_overlap_2d_is_the_exact_area_overlap():
    rng = np.random.default_rng(3)
    edges = np.linspace(-200.0, 200.0, 21)
    x, y = rng.uniform(-260, 260, 300), rng.uniform(-260, 260, 300)
    w = rng.uniform(0.1, 1.0, 300)
    matrix, outside = footprint_mod.box_overlap_2d(x, y, w, 48.27, 48.6, edges, edges)
    assert matrix.sum() + outside == pytest.approx(w.sum(), rel=1e-12)
    assert (matrix >= 0).all()
    inside = ((x - 24.135 >= -200) & (x + 24.135 <= 200) & (y - 24.3 >= -200) & (y + 24.3 <= 200))
    assert matrix.sum() == pytest.approx(w[inside].sum(), rel=1e-12)
    # A box wholly inside one bin lands there entirely.
    one, _ = footprint_mod.box_overlap_2d([10.0], [10.0], [1.0], 10.0, 10.0, edges, edges)
    assert one[10, 10] == pytest.approx(1.0) and one.sum() == pytest.approx(1.0)


def test_rotated_subdeposits_conserve_weight_and_centre_on_the_cell():
    rng = np.random.default_rng(4)
    centres = rng.normal(size=(50, 3)) * 100
    r = frame_mod.rotation_matrix(0.4, -1.3)
    pts, w = footprint_mod.rotated_subdeposits(centres, r, np.ones(50), (48.27, 48.6, 20.5), 4, 2)
    assert pts.shape == (50 * 32, 3) and w.sum() == pytest.approx(50.0)
    means = pts.reshape(50, 32, 3).mean(axis=1)
    np.testing.assert_allclose(means, centres, atol=1e-9)
    # Per-cell rotations broadcast too.
    pts_n, _ = footprint_mod.rotated_subdeposits(centres, np.tile(r, (50, 1, 1)), np.ones(50),
                                                 (48.27, 48.6, 20.5), 4, 2)
    np.testing.assert_allclose(pts_n, pts, atol=1e-12)
    edges = tuple(np.arange(-400.0, 401.0, 20.0) for _ in range(3))
    cube, outside = footprint_mod.bin_uniform(pts, w, edges)
    assert cube.sum() + outside == pytest.approx(50.0, rel=1e-12)


# ------------------------------------------------------- selection, pick --


def test_neighbours_and_membership_follow_the_selection(cursor, inspected):
    record, events = inspected["record"], inspected["events"]
    first = inspected["bodies"][events[0], "a"]["event"]
    assert first["in_selection"] is True and first["prev"] is None
    assert first["next"] == (events[1] if len(events) > 1 else None)
    if len(events) > 1:
        last = inspected["bodies"][events[-1], "a"]["event"]
        assert last["prev"] == events[-2] and last["next"] is None
        # Narrow the selection to the first event: the last one is drawn but outside.
        e1 = cursor.execute(f"SELECT e1 FROM {quote(naming.event_table(record.table_name))} "
                            "WHERE event_number = ?", [events[0]]).fetchone()[0]
        narrow = filters.build(record, e1_min=float(e1) - 1e-3, e1_max=float(e1) + 1e-3)
        body = event_inspector.inspect(cursor, record, narrow, events[-1], "a", "file", inspected["footprint"])
        assert body["event"]["in_selection"] is False


def test_pick_is_the_notebooks_seeded_rule(cursor, inspected):
    record, spec = inspected["record"], inspected["spec"]
    first = event_inspector.pick(cursor, record, spec, seed=42)
    again = event_inspector.pick(cursor, record, spec, seed=42)
    assert first["event_number"] == again["event_number"] and first["pool"] == again["pool"]
    assert first["event_number"] in first["pool"]
    assert "more hits than the mean" in first["rule"] and "seed 42" in first["rule"]
    assert first["n_events"] == len(inspected["events"])
    event = quote(naming.event_table(record.table_name))
    mean_hits = cursor.execute(f"SELECT avg(n_hits) FROM {event} WHERE d IS NOT NULL").fetchone()[0]
    dense = [r[0] for r in cursor.execute(
        f"SELECT event_number FROM {event} WHERE d IS NOT NULL AND n_hits > ? "
        "ORDER BY greatest(theta_a, theta_b) DESC, event_number LIMIT 20", [mean_hits]).fetchall()]
    assert first["pool"] == dense
    # The default is the tilted rule, named as such.
    assert first["rule_id"] == event_inspector.RULE_TILTED and first["seed_used"] is True


def test_the_densest_rule_is_the_notebooks_idxmax_in_cells(cursor, inspected):
    """``groupby('event_number').size().idxmax()``, counted in cells, ties to the lowest number."""
    record, spec = inspected["record"], inspected["spec"]
    picked = event_inspector.pick(cursor, record, spec, seed=3, rule=event_inspector.RULE_DENSEST)
    event = quote(naming.event_table(record.table_name))
    ranked = cursor.execute(
        f"SELECT event_number, n_cells FROM {event} WHERE d IS NOT NULL "
        "ORDER BY n_cells DESC, event_number LIMIT 20").fetchall()
    assert picked["pool"] == [r[0] for r in ranked] and picked["event_number"] == ranked[0][0]
    assert picked["n_cells"] == ranked[0][1]
    # Deterministic: every seed gives the same event, and the body says the seed is unused.
    again = event_inspector.pick(cursor, record, spec, seed=99, rule=event_inspector.RULE_DENSEST)
    assert again["event_number"] == picked["event_number"]
    assert picked["rule_id"] == "densest" and picked["seed_used"] is False and picked["seed"] == 3
    assert "not used" in picked["rule"] and "drawn at random" not in picked["rule"]
    from calosrv.errors import ValidationError

    with pytest.raises(ValidationError) as err:
        event_inspector.pick(cursor, record, spec, rule="brightest")
    assert err.value.extra["field"] == "rule"


def test_a_missing_event_or_shower_is_a_404(cursor, inspected):
    from calosrv.errors import NotFoundError

    with pytest.raises(NotFoundError):
        event_inspector.inspect(cursor, inspected["record"], inspected["spec"], 10**6, "a", "file",
                                inspected["footprint"])


def test_the_figure_fits_the_contract_and_coarsens_when_asked(cursor, inspected):
    event = inspected["events"][0]
    body = inspected["bodies"][event, "a"]
    assert density.wire_size(body) < density.RESPONSE_LIMIT
    tight = event_inspector.inspect(cursor, inspected["record"], inspected["spec"], event, "a", "file",
                                    inspected["footprint"], limit=5_000)
    assert tight["grid"]["pitch_mm"] > body["grid"]["pitch_mm"]
    assert any("coarsened" in n for n in tight["grid"]["notes"])
    for kind in ("trans", "local"):
        assert tight["frames"][kind]["splat"]["pitch_mm"] == tight["grid"]["pitch_mm"]
        panel = tight["frames"][kind]["panels"]["xy"]
        assert panel["total"] + panel["energy_outside_window_gev"] == pytest.approx(
            body["event"]["shower"]["energy_gev"], rel=1e-9)


def test_a_figure_still_over_the_limit_at_the_coarsest_grid_says_so(cursor, inspected):
    """The guard stops at MAX_PITCH_MM; its last note must not claim the coarsening sufficed."""
    event = inspected["events"][0]
    body = inspected["bodies"][event, "a"]
    assert not any("served as it is" in n for n in body["grid"]["notes"])
    tight = event_inspector.inspect(cursor, inspected["record"], inspected["spec"], event, "a", "file",
                                    inspected["footprint"], limit=1_000)
    assert tight["grid"]["pitch_mm"] == event_inspector.MAX_PITCH_MM
    *steps, last = tight["grid"]["notes"]
    assert any("coarsened" in n for n in steps)
    match = re.fullmatch(r"The response is still ([\d,]+) bytes at (\d+) mm and is served as it is\.", last)
    assert match, last
    assert int(match.group(1).replace(",", "")) >= 1_000
    assert float(match.group(2)) == event_inspector.MAX_PITCH_MM


# ----------------------------------------------------------------- route --


def test_the_event_route_serves_the_figure_under_budget(client):
    picked = client.get("/api/event/pick", params={"seed": 7}).json()
    assert picked["event_number"] in picked["pool"] and picked["seed"] == 7
    # A pick that names no rule is the body it was before the rules: no rule_id.
    assert "rule_id" not in picked and "seed_used" not in picked
    densest = client.get("/api/event/pick", params={"rule": "densest"}).json()
    assert densest["rule_id"] == "densest" and densest["event_number"] == densest["pool"][0]
    bad = client.get("/api/event/pick", params={"rule": "brightest"})
    assert bad.status_code == 422 and bad.json()["field"] == "rule"
    response = client.get("/api/event", params={"event_number": picked["event_number"], "shower": "b"})
    assert response.status_code == 200
    assert len(response.content) < density.RESPONSE_LIMIT
    body = response.json()
    assert set(body["frames"]) == set(event_inspector.FRAMES)
    assert body["meta"]["event"] == picked["event_number"] and body["meta"]["shower"] == "b"
    assert body["meta"]["coordinates"] == "file"
    texts = [n["text"] for n in body["meta"]["notices"]]
    assert body["coordinates"]["note"] in texts and body["window"]["rule"] in texts
    assert body["scale"]["rule"] in texts
    assert "filter" in body and body["event"]["shower"]["label"] == "B"
    # Not a raw hit array: nine rasters and marks only.
    text = json.dumps(body)
    assert '"hits"' not in text and '"points"' not in text

    assert client.get("/api/event", params={"event_number": 10**6}).status_code == 404
    bad = client.get("/api/event", params={"event_number": picked["event_number"], "shower": "c"})
    assert bad.status_code == 422 and bad.json()["field"] == "shower"
    bad = client.get("/api/event", params={"event_number": picked["event_number"], "coordinates": "guess"})
    assert bad.status_code == 422 and bad.json()["field"] == "coordinates"
    assert client.get("/api/event").status_code == 422


def test_an_event_outside_the_selection_is_drawn_and_said_so(client):
    experiments = client.get("/api/experiments").json()["experiments"]
    bounds = next(e for e in experiments if e["status"] == "ready")["bounds"]
    # A window that admits nothing: the event is outside it, and still drawn.
    response = client.get("/api/event", params={"event_number": 0, "e1_min": bounds["e1"][1] + 5.0,
                                                "e1_max": bounds["e1"][1] + 6.0})
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["in_selection"] is False
    assert any("outside the current selection" in w for w in body["meta"]["warnings"])


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def test_no_event_sentence_signs_a_number_with_a_hyphen(client):
    """Every rendered negative number - the ramp's floor, a residual's exponent - is set with U+2212."""
    from calosrv.text import signed_hyphens

    picked = client.get("/api/event/pick", params={"seed": 7}).json()
    for shower in ("a", "b"):
        body = client.get("/api/event", params={"event_number": picked["event_number"], "shower": shower}).json()
        assert body["scale"]["floor"] < 1e-3, "the demonstration file's floor writes an exponent"
        for path, text in _strings(body):
            if path.endswith(("data", ".table_name")):
                continue
            assert not signed_hyphens(text), (path, signed_hyphens(text))
