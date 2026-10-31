"""``GET /api/selection-cells``: the selection's detector cells as cubes (Page 2, Absolute frame).

The cubes are checked against the projection table they were summed from,
aggregated here independently in NumPy: every hit of both showers in its
cell, the energy divided by the selection's N (the event table's count), the
network channels as energy-weighted means over the hits that carry a value,
the window as the event route's rule on the selection's cells, the cap and
the floor on what is drawn, the depth profile per layer. The body must be
the one-event cubes' body with a ``selection`` block in place of ``event``
(the browser decodes both alike); every served body is validated against
``tests/contracts/selection_cells.json``, measured against the 100 KB
contract, searched for raw hit keys and for hyphen-signed numbers.

The tests are grouped by booted fixture - ``single_client`` (the two-event
demonstration file, the synthetic single-shower hits and their aggregate),
then ``synthetic_client`` (286 clones of the demonstration's events in nine D
slices, for the filters and N) - because each boot resets the process-wide
database the previous one served from.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import ddl, naming, registry
from calosrv.db.naming import quote
from calosrv.query import canonical, density, event_inspector, filters, voxel_event, voxel_selection
from calosrv.text import signed_hyphens

ROUTE = "/api/selection-cells"
BASE = {"table_name": BASELINE_TABLE}
HITS = {"table_name": SINGLE_HITS_TABLE}
EVENTS = {"table_name": SINGLE_EVENTS_TABLE}


# ---------------------------------------------------------------- helpers --


def _decode(text: str, dtype: str) -> np.ndarray:
    raw = base64.b64decode(text)
    return np.frombuffer(raw, dtype=np.uint8 if dtype == "u8" else "<u2").astype(np.int64)


def _cubes(body: dict) -> dict[str, np.ndarray]:
    cubes = body["voxels"]["cubes"]
    return {name: _decode(cubes[name], cubes["dtype"][name]) for name in ("ix", "iy", "iz", "code", "flags")}


def _strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def _keys(node, path="$"):
    """Every key of every object in ``node``, at any depth, with its path."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key
            yield from _keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _keys(value, f"{path}[{index}]")


def _check_body(body: dict) -> None:
    """What every selection body must satisfy."""
    contract_check.check(body, "selection_cells")
    raw = [path for path, key in _keys(body) if key in ("hits", "points")]
    assert not raw, raw
    for path, sentence in _strings(body):
        if path.endswith((".ix", ".iy", ".iz", ".code", ".flags", ".table_name")):
            continue
        assert not signed_hyphens(sentence), (path, signed_hyphens(sentence))
    vox = body["voxels"]
    assert all(item["i"] < vox["cubes"]["n"] for item in vox["topk"])
    # The geometry sentence is shipped once, at geometry.note.
    note = vox["geometry"]["note"]
    assert sum(1 for _, text in _strings(body) if text == note) == 1
    scale = vox["scale"]
    if vox["channel"] == "energy" and vox["cubes"]["n"]:
        brightest = max(item["value"] for item in vox["topk"])
        assert scale["top_density"] == pytest.approx(brightest, rel=1e-12)
        assert scale["vmax"] == pytest.approx(np.log10(brightest), abs=1e-12)
        assert scale["degenerate"] == (scale["vmin"] == scale["vmax"])


def _served(client, **params) -> dict:
    response = client.get(ROUTE, params=params)
    assert response.status_code == 200, response.text[:800]
    assert len(response.content) < density.RESPONSE_LIMIT
    body = response.json()
    _check_body(body)
    return body


def _refused(client, field: str, capability: str | None = None, status: int = 422, **params) -> dict:
    response = client.get(ROUTE, params=params)
    assert response.status_code == status, response.text[:600]
    problem = response.json()
    assert problem.get("field") == field, problem
    if capability is not None:
        contract_check.check(problem, "capability_problem")
        assert problem["capability"] == capability, problem
    for _, sentence in _strings(problem):
        assert not signed_hyphens(sentence), sentence
    return problem


def _con(client):
    return client.app.state.database.read_cursor()


def _record(con, table: str):
    return registry.require_ready(con, table)


def _reference(con, table: str, params: dict | None = None, channel: str | None = None,
               model: str = "segmentation") -> dict[str, Any]:
    """The selection's cells summed here from the projection rows, independently of the module.

    ``cells`` are the distinct (ix, iy, iz) in lexicographic order; per cell the
    energy, the origin bits and, for a network channel, the sums over the hits
    with a finite value: their energy, Σ E·v, and the signed parts of Σ E·v.
    """
    record = _record(con, table)
    spec = filters.build(record, **(params or {}))
    proj = quote(naming.proj_table(table))
    value = f"CAST({ddl.cam_column(model, 'lab', channel)} AS DOUBLE)" if channel else "NULL::DOUBLE"
    data = con.execute(f"SELECT ix, iy, iz, org, energy, {value} AS v FROM {proj} WHERE {spec.where_sql()}",
                       spec.params()).fetchnumpy()
    n_events = con.execute(f"SELECT count(*) FROM {quote(naming.event_table(table))} "
                           f"WHERE {spec.where_sql()}", spec.params()).fetchone()[0]
    keys = np.column_stack([np.asarray(data[c], dtype=np.int64) for c in ("ix", "iy", "iz")])
    energy = np.asarray(data["energy"], dtype=np.float64)
    cells, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    n = cells.shape[0]
    mask = np.zeros(n, dtype=np.int64)
    np.bitwise_or.at(mask, inverse, np.left_shift(1, np.asarray(data["org"], dtype=np.int64)))
    out = {"record": record, "spec": spec, "n_events": int(n_events), "n_hits": int(energy.size),
           "cells": cells, "energy": np.bincount(inverse, weights=energy, minlength=n), "mask": mask,
           "rows": {"iz": keys[:, 2], "energy": energy, "inverse": inverse}}
    if channel:
        v = np.asarray(np.ma.filled(np.ma.asarray(data["v"]).astype(np.float64), np.nan))
        finite = np.isfinite(v)
        filled = np.where(finite, v, 0.0)
        out["weight"] = np.bincount(inverse, weights=np.where(finite, energy, 0.0), minlength=n)
        out["ev"] = np.bincount(inverse, weights=energy * filled, minlength=n)
        out["positive"] = np.bincount(inverse, weights=energy * np.maximum(filled, 0.0), minlength=n)
        out["negative"] = np.bincount(inverse, weights=energy * np.minimum(filled, 0.0), minlength=n)
        out["n_valued"] = int(finite.sum())
        out["rows"]["value"] = v
    return out


def _lookup(reference: dict) -> dict[tuple[int, int, int], int]:
    return {tuple(int(v) for v in cell): i for i, cell in enumerate(reference["cells"])}


def _drawn_cells(body: dict) -> np.ndarray:
    """The lattice ordinals (ix, iy, iz) of the shipped cubes, in payload order."""
    cubes = _cubes(body)
    axes = body["voxels"]["geometry"]["axes"]
    return np.column_stack([cubes[f"i{a}"] + axes[a]["i0"] for a in "xyz"])


def _centres(record, cells: np.ndarray) -> np.ndarray:
    lat = record.lattice
    return np.column_stack([lat.x.coords[cells[:, 0]], lat.y.coords[cells[:, 1]], lat.z.coords[cells[:, 2]]])


def _inside(centres: np.ndarray, window: dict) -> np.ndarray:
    keep = np.ones(centres.shape[0], dtype=bool)
    for i, axis in enumerate("xyz"):
        keep &= (centres[:, i] >= window[axis][0]) & (centres[:, i] <= window[axis][1])
    return keep


def _builder(con, table: str, params: dict | None = None, channel: str = "energy",
             model: str = "segmentation", window: str = "per_axis"):
    """The module's own scan and builder for a selection, outside the route and its cache."""
    record = _record(con, table)
    spec = filters.build(record, **(params or {})).clamped(record)
    network = model if channel in voxel_selection.NETWORK_CHANNELS else None
    sums = voxel_selection.scan(con, record, spec, channel, network)
    return voxel_selection.build(record, sums, channel, model, window, canonical.cell_footprint(con, record))


# ------------------------------------------------------------ pure helpers --


def test_the_scan_names_only_allowlisted_columns_and_filters_valued_hits():
    from calosrv.db import schemas
    from calosrv.db.registry import STATUS_READY, ExperimentRecord

    schema = schemas.of_kind(ddl.KIND_TWO_SHOWER)
    record = ExperimentRecord(table_name="t_two", status=STATUS_READY, schema_name=schema.name,
                              schema_version=schema.version,
                              derived_version=schemas.DERIVED_VERSION[ddl.KIND_TWO_SHOWER])
    spec = filters.FilterSpec(table_name="t_two", e1_min=0.0, e1_max=1.0, e2_min=0.0, e2_max=1.0,
                              d_min=0.0, d_max=1.0)
    energy = voxel_selection.scan_sql(record, spec, "energy", None)
    assert "GROUP BY p.ix, p.iy, p.iz" in energy and "bit_or(1 << p.org)" in energy
    assert "FILTER" not in energy and "sc_" not in energy and "gc_" not in energy
    shap = voxel_selection.scan_sql(record, spec, "shapcam", "energy")
    column = ddl.cam_column("energy", "lab", "shapcam")
    assert column == "sc_en_abs" and f"isfinite(CAST(p.{column} AS DOUBLE))" in shap
    assert shap.count("FILTER (WHERE isfinite(") == 4
    # The key holds the selection, the channel and the network - never the window or the cap.
    key = voxel_selection.cache_key(spec, "shapcam", "energy")
    assert key[0] == "t_two" and key[-3:-1] == ("shapcam", "energy")


# ------------------------------------------------------ single_client: shape --


def test_the_body_is_the_event_body_with_a_selection_block(single_client):
    """Every block but ``event`` is the one-event lab body's, key for key, so one decoder reads both."""
    for channel in ("energy", "gradcam", "shapcam"):
        body = _served(single_client, **BASE, channel=channel)
        event = single_client.get("/api/event", params={**BASE, "format": "voxels", "event_number": 0,
                                                        "frame": "lab", "shower": "both",
                                                        "channel": channel}).json()
        assert set(body) == (set(event) - {"event"}) | {"selection"}
        vox, ev = body["voxels"], event["voxels"]
        assert list(vox) == list(ev)
        for block in ("cubes", "geometry", "scale", "cap", "below_floor", "depth_profile"):
            assert list(vox[block]) == list(ev[block]), block
        assert list(body["window"]) == list(event["window"])
        assert list(body["coordinates"]) == list(event["coordinates"])
        assert (vox["frame"], vox["regime"], vox["species"]) == ("lab", "cells", None)
        assert vox["cubes"]["flag_bits"] == ev["cubes"]["flag_bits"]
        assert vox["symbols"] == ev["symbols"] and body["footprint_mm"] == event["footprint_mm"]
        assert body["coordinates"]["source"] == "lattice"
        meta = body["meta"]
        assert (meta["frame"], meta["shower"], meta["channel"], meta["format"]) == ("lab", "both", channel, "voxels")
        assert meta["model"] == (None if channel == "energy" else "segmentation") == vox["model"]
        assert meta["exact"] is True and meta["warnings"] == []
        selection = body["selection"]
        assert list(selection) == ["n_events", "n_hits", "n_cells", "quantity", "aggregation"]
        scopes = {n["scope"] for n in meta["notices"]}
        assert scopes == ({"selection"} if channel == "energy" else {"selection", "channel"})
        texts = [n["text"] for n in meta["notices"]]
        for sentence in (selection["quantity"], selection["aggregation"], body["window"]["rule"],
                         vox["scale"]["floor_rule"], *vox["notes"]):
            assert sentence in texts


def test_the_energy_cells_are_the_selections_sums_divided_by_n(single_client):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE)
        record = ref["record"]
        builder = _builder(con, BASELINE_TABLE)
    body = _served(single_client, **BASE)
    selection, vox = body["selection"], body["voxels"]
    n = ref["n_events"]
    assert n == 2 and selection["n_events"] == n
    assert selection["n_hits"] == ref["n_hits"] and selection["n_cells"] == len(ref["cells"])
    assert f"N = {n:,}" in selection["quantity"] and "GeV per mm³ per event" in selection["quantity"]
    # The cubes are the selection's cells inside the window, once each.
    index = _lookup(ref)
    drawn = _drawn_cells(body)
    centres = _centres(record, ref["cells"])
    inside = _inside(centres, body["window"]["axes"])
    assert {tuple(c) for c in drawn.tolist()} == {tuple(c) for c in ref["cells"][inside].tolist()}
    assert drawn.shape[0] == vox["cubes"]["n"] == int(inside.sum())
    assert vox["cap"]["cells_outside_window"] == int((~inside).sum())
    # Every energy is a mean per selected event: the selection's sums divided by N.
    mean = ref["energy"] / n
    cap = vox["cap"]
    assert cap["energy_total_gev"] == pytest.approx(float(ref["energy"].sum()) / n, rel=1e-12)
    assert cap["energy_outside_window_gev"] == pytest.approx(float(mean[~inside].sum()), rel=1e-9, abs=1e-15)
    assert cap["energy_drawn_gev"] == pytest.approx(float(mean[inside].sum()), rel=1e-9)
    volume = float(np.prod(vox["geometry"]["cube_mm"]))
    for item in vox["topk"]:
        cell = index[tuple(int(v) for v in drawn[item["i"]])]
        assert item["energy_gev"] == pytest.approx(mean[cell], rel=1e-12)
        assert item["value"] == pytest.approx(mean[cell] / volume, rel=1e-12)
    assert vox["topk_unit"] == vox["scale"]["unit"] == "GeV/mm^3/event"
    # The module's own builder holds the same per-cube energies for every drawn cube.
    built = builder.cubes(None)
    i0 = [vox["geometry"]["axes"][a]["i0"] for a in "xyz"]
    for x, y, z, e in zip(built.ix.tolist(), built.iy.tolist(), built.iz.tolist(), built.energy.tolist()):
        assert e == pytest.approx(mean[index[(x + i0[0], y + i0[1], z + i0[2])]], rel=1e-12)


def test_every_hit_of_both_showers_is_summed_and_coded(single_client):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE)
        proj = quote(naming.proj_table(BASELINE_TABLE))
        origins = dict(con.execute(f"SELECT org, count(*) FROM {proj} GROUP BY org").fetchall())
        n_hits = con.execute(f"SELECT coalesce(sum(n_hits), 0) FROM "
                             f"{quote(naming.event_table(BASELINE_TABLE))}").fetchone()[0]
    body = _served(single_client, **BASE)
    assert set(origins) >= {ddl.ORIGIN_A, ddl.ORIGIN_B}
    # Every row of every origin, A, B and 'A+B', and the event table's own count.
    assert body["selection"]["n_hits"] == sum(origins.values()) == ref["n_hits"] == n_hits
    assert body["meta"]["shower"] == "both"
    # A cube's 2-bit code is the origins its cell holds over the selection.
    index = _lookup(ref)
    codes = voxel_event.shower_codes(ref["mask"])
    drawn = _drawn_cells(body)
    flags = _cubes(body)["flags"]
    expected = np.array([codes[index[tuple(c)]] for c in drawn.tolist()])
    np.testing.assert_array_equal(flags & 3, expected)
    assert {int(c) for c in flags & 3} >= {voxel_event.SHOWER_A, voxel_event.SHOWER_B}
    labels = body["voxels"]["cubes"]["shower_codes"]
    assert labels[voxel_event.SHOWER_MIXED].endswith("across the selection")


@pytest.mark.parametrize("channel", ["gradcam", "shapcam"])
@pytest.mark.parametrize("model", ["segmentation", "energy"])
def test_network_cubes_are_the_energy_weighted_mean_over_the_cells_hits(single_client, channel, model):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE, channel=channel, model=model)
        builder = _builder(con, BASELINE_TABLE, channel=channel, model=model)
    body = _served(single_client, **BASE, channel=channel, model=model)
    vox = body["voxels"]
    value = np.where(ref["weight"] > 0, ref["ev"] / np.where(ref["weight"] > 0, ref["weight"], 1.0), np.nan)
    index = _lookup(ref)
    drawn = _drawn_cells(body)
    # The exact top values are the energy-weighted means of their cells' hits.
    assert len(vox["topk"]) == min(64, vox["cubes"]["n"])
    for item in vox["topk"]:
        cell = index[tuple(int(v) for v in drawn[item["i"]])]
        assert item["value"] == pytest.approx(value[cell], rel=1e-9, abs=1e-15)
        assert item["energy_gev"] == pytest.approx(ref["energy"][cell] / ref["n_events"], rel=1e-12)
    # ...and so is every cube the builder colours.
    built = builder.cubes(None)
    i0 = [vox["geometry"]["axes"][a]["i0"] for a in "xyz"]
    cells = [index[(x + i0[0], y + i0[1], z + i0[2])]
             for x, y, z in zip(built.ix.tolist(), built.iy.tolist(), built.iz.tolist())]
    np.testing.assert_allclose(built.value, value[cells], rtol=1e-9, atol=1e-15)
    # The one-event ramps, fixed and linear.
    scale = vox["scale"]
    assert (scale["scale"], scale["vmin"], scale["vmax"]) == (
        "linear", -1 if channel == "shapcam" else 0, 1)
    assert vox["topk_quantity"] == scale["quantity"] == channel
    assert "energy-weighted mean over the selection's hits in the cell" in scale["floor_rule"]
    cam = body["meta"]["cam"]
    assert cam["model"] == model and cam["column"] == ddl.csv_model_column(model, "absolute", channel)
    assert "selection's hits" in cam["aggregation"]
    assert {"scope": "channel", "text": cam["note"]} in body["meta"]["notices"]
    assert ref["n_valued"] == ref["n_hits"], "the demonstration file's every hit carries a value"


# ---------------------------------------------- single_client: depth, window --


def _check_depth_profile(body: dict) -> dict:
    vox = body["voxels"]
    dp = vox["depth_profile"]
    axis = vox["geometry"]["axes"]["z"]
    assert dp["n"] == len(dp["energy_gev"]) == len(dp["centres_mm"]) == len(axis["coords"])
    assert dp["index"] == "cubes.iz" and dp["pitch_mm"] == body["footprint_mm"][2]
    assert (dp["numbering"], dp["first_layer"]) == ("detector_layers", axis["i0"] + 1)
    cap = vox["cap"]
    assert dp["energy_total_gev"] == cap["energy_total_gev"]
    assert dp["energy_outside_gev"] == cap["energy_outside_window_gev"]
    assert sum(dp["energy_gev"]) + dp["energy_outside_gev"] == pytest.approx(dp["energy_total_gev"], rel=1e-9)
    assert all(v >= 0.0 for v in dp["energy_gev"])
    assert "per selected event" in dp["note"]
    return dp


@pytest.mark.parametrize("channel", ["energy", "gradcam", "shapcam"])
def test_the_depth_profile_is_the_cells_per_layer_per_event(single_client, channel):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE, channel=None if channel == "energy" else channel, model="energy")
    body = _served(single_client, **BASE, channel=channel, model="energy")
    dp = _check_depth_profile(body)
    n = ref["n_events"]
    axis = body["voxels"]["geometry"]["axes"]["z"]
    inside = _inside(_centres(ref["record"], ref["cells"]), body["window"]["axes"])
    layer = ref["cells"][:, 2] - axis["i0"]
    expected = np.bincount(layer[inside], weights=ref["energy"][inside] / n, minlength=dp["n"])
    np.testing.assert_allclose(dp["energy_gev"], expected, rtol=1e-9, atol=1e-15)
    att = dp["attention"]
    if channel == "energy":
        assert att is None
        return
    assert att["channel"] == channel and att["unit"] == "GeV/event"
    assert att["quantity"] == {"gradcam": "Σ E·Grad-CAM", "shapcam": "Σ E·Shap-CAM"}[channel]
    if channel == "shapcam":
        assert att["signed"] is True
        pos = np.bincount(layer[inside], weights=ref["positive"][inside] / n, minlength=dp["n"])
        neg = np.bincount(layer[inside], weights=-ref["negative"][inside] / n, minlength=dp["n"])
        np.testing.assert_allclose(att["positive"], pos, rtol=1e-9, atol=1e-15)
        np.testing.assert_allclose(att["negative"], neg, rtol=1e-9, atol=1e-15)
        assert att["positive_total"] == pytest.approx(float(ref["positive"].sum()) / n, rel=1e-9)
        assert att["negative_total"] == pytest.approx(-float(ref["negative"].sum()) / n, rel=1e-9)
        assert np.sum(att["positive"]) + att["positive_outside"] == pytest.approx(att["positive_total"], rel=1e-9)
        assert np.sum(att["negative"]) + att["negative_outside"] == pytest.approx(att["negative_total"], rel=1e-9)
        assert att["total"] == pytest.approx(att["positive_total"] - att["negative_total"], rel=1e-9, abs=1e-15)
        # Sums over hits, never a cell's mean times its energy: a cell whose hits disagree in sign
        # adds to both halves (none in the demonstration file, so the two agree here).
        rows = ref["rows"]
        hit_pos = float((rows["energy"] * np.maximum(np.nan_to_num(rows["value"]), 0.0)).sum()) / n
        assert att["positive_total"] == pytest.approx(hit_pos, rel=1e-9)
    else:
        assert att["signed"] is False
        values = np.bincount(layer[inside], weights=ref["ev"][inside] / n, minlength=dp["n"])
        np.testing.assert_allclose(att["values"], values, rtol=1e-9, atol=1e-15)
        assert att["total"] == pytest.approx(float(ref["ev"].sum()) / n, rel=1e-9)
        assert np.sum(att["values"]) + att["outside"] == pytest.approx(att["total"], rel=1e-9)


@pytest.mark.parametrize("window", ["per_axis", "shared"])
def test_the_window_is_the_event_rule_on_the_selections_cells(single_client, window):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE)
        record = ref["record"]
        fp = canonical.cell_footprint(con, record)
    body = _served(single_client, **BASE, window=window)
    pitch_z = record.frame_bounds.layer_pitch_mm
    centres = _centres(record, ref["cells"])
    weights = ref["energy"]
    if window == "per_axis":
        halves, windows = event_inspector.frame_window(centres, weights, "lab", fp, pitch_z)
    else:
        half, centre = event_inspector._window({a: centres[:, i] for i, a in enumerate("xyz")}, weights,
                                               pad=max(fp[0], fp[1], pitch_z))
        halves = {a: half for a in "xyz"}
        windows = {a: (centre[a] - half, centre[a] + half) for a in "xyz"}
    block = body["window"]
    assert block["mode"] == window
    assert block["half_mm_axes"] == pytest.approx(halves)
    for axis in "xyz":
        assert block["axes"][axis] == pytest.approx(list(windows[axis]))
        assert block["half_mm_axes"][axis] >= event_inspector.WINDOW_MIN_HALF_MM
    assert block["half_mm"] == pytest.approx(max(halves.values()))
    assert "the selection's cells (both showers, summed over its 2 events)" in block["rule"]
    assert ("Per-axis" if window == "per_axis" else "One half-width") in block["rule"]
    assert "paired projections" not in block["rule"]
    inside = _inside(centres, windows)
    assert body["voxels"]["cap"]["cells_outside_window"] == int((~inside).sum())
    assert body["voxels"]["cubes"]["n"] == int(inside.sum())


def test_the_cap_draws_the_most_energetic_and_counts_the_rest(single_client):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE)
    whole = _served(single_client, **BASE, cap=15000)
    capped = _served(single_client, **BASE, cap=100)
    cap = capped["voxels"]["cap"]
    total = whole["voxels"]["cap"]["n_total"]
    assert (cap["limit"], cap["requested"], cap["n_drawn"], cap["n_total"]) == (100, 100, 100, total)
    assert cap["n_beyond"] == total - 100 and capped["voxels"]["cubes"]["n"] == 100
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
        == pytest.approx(cap["energy_total_gev"], rel=1e-9)
    # The drawn are the most energetic of the cells inside the window, in ascending energy.
    index = _lookup(ref)
    mean = ref["energy"] / ref["n_events"]
    drawn = np.array([mean[index[tuple(c)]] for c in _drawn_cells(capped).tolist()])
    everything = np.array([mean[index[tuple(c)]] for c in _drawn_cells(whole).tolist()])
    assert (np.diff(drawn) >= 0).all()
    np.testing.assert_allclose(np.sort(drawn), np.sort(everything)[-100:], rtol=0)
    assert cap["energy_beyond_gev"] == pytest.approx(float(np.sort(everything)[:-100].sum()), rel=1e-9)
    note = capped["voxels"]["notes"][-1]
    assert "The 100 most energetic of" in note and "GeV per selected event" in note
    assert "of the selection's mean energy per event" in note
    # The profile counts every in-window cell before the cap, so the cap does not move it.
    assert capped["voxels"]["depth_profile"] == whole["voxels"]["depth_profile"]


@pytest.mark.parametrize("cap", [100, 15000])
def test_the_floor_is_the_first_percentile_of_the_drawn_cubes(single_client, cap):
    with _con(single_client) as con:
        ref = _reference(con, BASELINE_TABLE)
    body = _served(single_client, **BASE, cap=cap)
    vox = body["voxels"]
    scale = vox["scale"]
    volume = float(np.prod(vox["geometry"]["cube_mm"]))
    index = _lookup(ref)
    dens = np.array([ref["energy"][index[tuple(c)]] for c in _drawn_cells(body).tolist()]) / ref["n_events"] / volume
    assert scale["floor_density"] == pytest.approx(np.percentile(dens[dens > 0], 1.0), rel=1e-12)
    assert scale["top_density"] == pytest.approx(dens.max(), rel=1e-12)
    assert (scale["floor_basis"], scale["unit"], scale["degenerate"]) == ("drawn_cells", "GeV/mm^3/event", False)
    assert scale["vmin"] == pytest.approx(np.log10(scale["floor_density"]))
    cubes = _cubes(body)
    below = (cubes["flags"] & voxel_event.FLAG_BELOW_FLOOR) > 0
    assert vox["below_floor"]["n"] == int(below.sum()) == scale["clipped_low"]
    assert int(below.sum()) == int((dens < scale["floor_density"]).sum())
    assert below.any() and (cubes["code"][below] == 1).all() and (cubes["code"] >= 1).all()
    assert "1st percentile of the drawn cubes' positive densities" in scale["floor_rule"]
    if cap == 100:
        # Far above every cell's floor: the drawn cubes are the brightest hundred.
        everything = ref["energy"] / ref["n_events"] / volume
        assert scale["floor_density"] > np.percentile(everything, 50.0)


def test_the_single_shower_selection_draws_its_one_shower(single_client):
    with _con(single_client) as con:
        ref = _reference(con, SINGLE_HITS_TABLE)
    body = _served(single_client, **HITS)
    selection, vox = body["selection"], body["voxels"]
    assert (selection["n_events"], selection["n_hits"], selection["n_cells"]) == (
        ref["n_events"], ref["n_hits"], len(ref["cells"]))
    assert body["meta"]["shower"] == "a" and vox["model"] is None
    assert vox["cubes"]["shower_codes"] == ["Shower", "—", "—", "—"]
    assert set((_cubes(body)["flags"] & 3).tolist()) == {voxel_event.SHOWER_A}
    assert "both showers" not in selection["quantity"] and "the shower in the cell" in selection["quantity"]
    assert vox["cap"]["energy_total_gev"] == pytest.approx(float(ref["energy"].sum()) / ref["n_events"], rel=1e-12)
    _check_depth_profile(body)


# ---------------------------------------------------- single_client: refusals --


def test_per_event_channels_are_refused_naming_channel(single_client):
    for channel in ("segerr", "species"):
        problem = _refused(single_client, "channel", **BASE, channel=channel)
        assert "per-event quantity" in problem["detail"] and "energy, gradcam or shapcam" in problem["detail"]
        _refused(single_client, "channel", **HITS, channel=channel)


def test_unknown_values_are_refused_naming_their_parameter(single_client):
    _refused(single_client, "channel", **BASE, channel="density")
    _refused(single_client, "model", **BASE, model="vertex")
    _refused(single_client, "window", **BASE, window="wide")
    for cap in (99, 15001, 0):
        problem = _refused(single_client, "cap", **BASE, cap=cap)
        assert "100 to 15,000" in problem["detail"]
    _refused(single_client, "cap", **BASE, cap="many")
    # No frame and no shower parameter exist to choose from: they are ignored, as any unknown name.
    body = _served(single_client, **BASE, frame="local", shower="a")
    assert (body["voxels"]["frame"], body["meta"]["shower"]) == ("lab", "both")


def test_an_aggregated_experiment_is_refused_before_the_filter(single_client):
    _refused(single_client, "table_name", "vox-event", **EVENTS)
    # Refused as a kind that cannot serve the view, even with a filter it could never have made.
    _refused(single_client, "table_name", "vox-event", **EVENTS, d_min=10.0)


def test_network_channels_need_the_networks_columns(single_client):
    for channel in ("gradcam", "shapcam"):
        problem = _refused(single_client, "channel", "vox-attention", **HITS, channel=channel)
        assert "no reconstruction-network outputs" in problem["reason"]
    # The energy channel of the same experiment is served.
    _served(single_client, **HITS, channel="energy")


# ------------------------------------------------ single_client: cache, budget --


def test_a_window_or_cap_change_makes_no_new_scan(single_client):
    """The scan is cached per selection, channel and network; the window and the cap re-render it."""
    cache = voxel_selection.cache_for()
    # include_undefined_d is part of the selection's key: a fresh entry for the same rows.
    fresh = {**BASE, "include_undefined_d": "true"}
    first = _served(single_client, **fresh, channel="gradcam", model="angle")
    assert first["meta"]["cached"] is False
    misses = cache.info()["misses"]
    for params in ({"window": "shared"}, {"cap": 100}, {"window": "per_axis", "cap": 2000}):
        again = _served(single_client, **fresh, channel="gradcam", model="angle", **params)
        assert again["meta"]["cached"] is True
        assert again["selection"] == first["selection"]
    # The energy channel reads the sums a network channel's scan of the same selection holds.
    energy = _served(single_client, **fresh, channel="energy")
    assert energy["meta"]["cached"] is True
    assert cache.info()["misses"] == misses
    # Another network is another scan.
    assert _served(single_client, **fresh, channel="gradcam", model="energy")["meta"]["cached"] is False
    assert cache.info()["misses"] == misses + 1
    # The same rows as the plain selection (no event of the file lacks its separation).
    plain = _served(single_client, **BASE, channel="energy")
    assert plain["voxels"]["cubes"] == energy["voxels"]["cubes"]


def test_the_query_scans_the_projection_table_once(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        spec = filters.build(record)
        for channel, model in (("energy", None), ("shapcam", "energy")):
            plan = voxel_selection.explain(con, record, spec, channel, model)
            assert plan.count(naming.proj_table(BASELINE_TABLE)) == 1, plan
            assert len(re.findall(r"SEQ_SCAN|TABLE_SCAN", plan)) == 1, plan


def test_the_guard_lowers_the_cap_and_says_so(single_client, monkeypatch):
    whole = single_client.get(ROUTE, params=BASE)
    limit = len(whole.content) - 2_000
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)
    response = single_client.get(ROUTE, params=BASE)
    assert response.status_code == 200
    body = response.json()
    contract_check.check(body, "selection_cells")
    assert len(response.content) < limit and density.wire_size(body) < limit
    cap = body["voxels"]["cap"]
    assert cap["limit"] < cap["n_total"] and cap["requested"] == voxel_selection.DEFAULT_CAP
    assert cap["n_drawn"] == cap["limit"] == body["voxels"]["cubes"]["n"] and cap["n_beyond"] > 0
    steps = [n["text"] for n in body["meta"]["notices"] if n["scope"] == "budget"]
    assert steps and all("the cap was lowered" in s for s in steps)
    assert f"to {cap['limit']:,} cubes" in steps[-1]
    assert body["meta"]["warnings"] == []


def test_an_overrun_after_every_step_is_served_and_said(single_client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    response = single_client.get(ROUTE, params=BASE)
    body = response.json()
    assert response.status_code == 200 and len(response.content) >= 2_000
    warning = body["meta"]["warnings"][-1]
    assert "still" in warning and "a smaller cap or a narrower selection" in warning
    assert not signed_hyphens(warning)


# ----------------------------------------------------------- synthetic_client --
#
# 286 events cloned from the demonstration file's two, in nine D slices of
# 1, 2, 7, 8, 14, 15, 19, 20 and 200 events centred 50 mm apart (±20 mm): every
# event's hits sit in its template's cells, its energies scaled with its momenta.


#: D windows holding one slice each, and one holding none.
_SLICES = {1: (0.0, 50.0), 2: (50.0, 100.0), 7: (100.0, 150.0), 200: (500.0, 700.0)}
_EMPTY = {"d_min": 46.0, "d_max": 54.0}


@pytest.mark.parametrize("count", sorted(_SLICES))
def test_filters_narrow_the_selection_and_n_follows(synthetic_client, count):
    lo, hi = _SLICES[count]
    params = {"d_min": lo, "d_max": hi}
    with _con(synthetic_client) as con:
        table = _record(con, BASELINE_TABLE).table_name
        ref = _reference(con, table, params)
    body = _served(synthetic_client, **params)
    selection = body["selection"]
    assert selection["n_events"] == ref["n_events"] == count
    assert selection["n_hits"] == ref["n_hits"] and selection["n_cells"] == len(ref["cells"])
    assert body["filter"]["d"] == [lo, hi]
    cap = body["voxels"]["cap"]
    assert cap["energy_total_gev"] == pytest.approx(float(ref["energy"].sum()) / count, rel=1e-12)
    index = _lookup(ref)
    drawn = _drawn_cells(body)
    for item in body["voxels"]["topk"]:
        cell = index[tuple(int(v) for v in drawn[item["i"]])]
        assert item["energy_gev"] == pytest.approx(ref["energy"][cell] / count, rel=1e-12)
    _check_depth_profile(body)
    if count == 1:
        assert "With N = 1 the mean is that one event's own deposit." in selection["aggregation"]


def test_a_one_event_selection_draws_that_events_cells(synthetic_client):
    """N = 1: the selection's cells are the event's own, through the same window, cap and profile."""
    params = {"d_min": _SLICES[1][0], "d_max": _SLICES[1][1]}
    with _con(synthetic_client) as con:
        record = _record(con, BASELINE_TABLE)
        spec = filters.build(record, **params)
        (event_number,), = con.execute(
            f"SELECT event_number FROM {quote(naming.event_table(BASELINE_TABLE))} WHERE {spec.where_sql()}",
            spec.params()).fetchall()
    body = _served(synthetic_client, **params)
    event = synthetic_client.get("/api/event", params={"format": "voxels", "event_number": event_number,
                                                       "frame": "lab", "shower": "both"}).json()
    assert body["window"]["axes"] == event["window"]["axes"]
    assert body["window"]["half_mm_axes"] == event["window"]["half_mm_axes"]
    vox, ev = body["voxels"], event["voxels"]
    assert vox["geometry"] == ev["geometry"]
    for name in ("ix", "iy", "iz"):
        assert vox["cubes"][name] == ev["cubes"][name]
    assert np.array_equal(_cubes(body)["flags"] & 3, _cubes(event)["flags"] & 3)
    for key in ("n_total", "n_drawn", "n_beyond", "cells_outside_window"):
        assert vox["cap"][key] == ev["cap"][key]
    for key in ("energy_total_gev", "energy_drawn_gev", "energy_outside_window_gev"):
        assert vox["cap"][key] == pytest.approx(ev["cap"][key], rel=1e-12, abs=1e-15)
    np.testing.assert_allclose(vox["depth_profile"]["energy_gev"], ev["depth_profile"]["energy_gev"], rtol=1e-9)
    assert body["selection"]["n_cells"] == event["event"]["n_cells"]


def test_an_empty_selection_is_a_404_that_says_so(synthetic_client):
    with _con(synthetic_client) as con:
        record = _record(con, BASELINE_TABLE)
        spec = filters.build(record, **_EMPTY)
        n = con.execute(f"SELECT count(*) FROM {quote(naming.event_table(BASELINE_TABLE))} "
                        f"WHERE {spec.where_sql()}", spec.params()).fetchone()[0]
    assert n == 0
    response = synthetic_client.get(ROUTE, params=_EMPTY)
    assert response.status_code == 404
    assert "The selection holds no event" in response.json()["detail"]


def test_the_synthetic_selection_fits_the_contract_on_every_channel(synthetic_client):
    for channel in ("energy", "gradcam", "shapcam"):
        body = _served(synthetic_client, channel=channel)
        assert body["selection"]["n_events"] == 286
