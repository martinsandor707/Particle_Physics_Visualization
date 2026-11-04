"""Layer groups through the API: ``depth_layers``, ``depth_groups`` pooling, C7 reach, ``layer_planes``.

Served by ``single_client``: the two-shower demonstration file (whose lattice
populates 56 of its 60 layer slots) and the synthetic single-shower hits.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from calosrv.db import ddl, naming, registry
from calosrv.db.naming import quote
from calosrv.grid import frame as frame_mod
from calosrv.grid import layer_groups as lg
from calosrv.query import canonical, density, event_inspector, filters, frame_sql, layer_profile, sampling
from calosrv.text import signed_hyphens
from conftest import BASELINE_TABLE, SINGLE_HITS_TABLE

BASE = {"table_name": BASELINE_TABLE}
HITS = {"table_name": SINGLE_HITS_TABLE}
FRAMES = {
    "lab": {},
    "canonical": {"frame": "canonical"},
    "trans": {"coord_system": "trans"},
    "local": {"coord_system": "local"},
}


@pytest.fixture(scope="module")
def records(single_client):
    with single_client.app.state.database.read_cursor() as con:
        return {name: registry.require_ready(con, name) for name in (BASELINE_TABLE, SINGLE_HITS_TABLE)}


#: The compaction of brief §9.1 (LG-C2): a shipped per-layer sum is within half a unit of its
#: fourth significant figure of the exact one, and a shipped edge within 0.0005 mm.
REL = 0.5 * 10.0 ** (1 - layer_profile.DIGITS)
EDGE_ATOL = 0.5 * 10.0 ** (-layer_profile.EDGE_DECIMALS) + 1e-9


def _get(client, params: dict, path: str = "/api/projections") -> dict:
    reply = client.get(path, params=params)
    assert reply.status_code == 200, reply.text
    return reply.json()


def _uniform(record) -> str:
    return lg.format_counts(lg.uniform_counts(record.lattice.z.n))


def _col_edges(panel: dict) -> np.ndarray:
    col = panel["axes"]["col"]
    if "edges" in col:
        return np.asarray(col["edges"], dtype=np.float64)
    return np.linspace(col["lo"], col["hi"], col["n"] + 1)


def _sql(client, sql: str, params=None):
    with client.app.state.database.read_cursor() as con:
        return con.execute(sql, params or []).fetchall()


# --------------------------------------------------------- refusals --


@pytest.mark.parametrize("value", ["5.5.5", "a.b.c", "5.5.5.5.5.5.5.5.4.4.4.4.0", "60"])
def test_a_malformed_partition_is_a_422_naming_depth_groups(single_client, value):
    reply = single_client.get("/api/projections", params={**BASE, "depth_groups": value})
    assert reply.status_code == 422
    assert reply.json()["field"] == "depth_groups"


def test_a_partition_of_the_wrong_layer_count_is_refused(single_client, records):
    wrong = lg.format_counts(lg.uniform_counts(records[BASELINE_TABLE].lattice.z.n + 4))
    reply = single_client.get("/api/projections", params={**BASE, "depth_groups": wrong})
    assert reply.status_code == 422
    problem = reply.json()
    assert problem["field"] == "depth_groups" and "sum to" in problem["detail"]


def test_the_local_frame_refuses_pooling(single_client, records):
    reply = single_client.get("/api/projections", params={
        **BASE, "coord_system": "local", "depth_groups": _uniform(records[BASELINE_TABLE])})
    assert reply.status_code == 422
    problem = reply.json()
    assert problem["field"] == "depth_groups" and "no common layer grid" in problem["detail"]


# --------------------------------------------------------- depth_layers --


@pytest.mark.parametrize("frame, numbering, symbol", [
    ("lab", "detector", "z"), ("canonical", "detector", "z′"),
    ("trans", "relative", "Δz"), ("local", "none", "w"),
])
def test_every_frame_carries_depth_layers_with_its_numbering(single_client, records, frame,
                                                              numbering, symbol):
    record = records[BASELINE_TABLE]
    body = _get(single_client, {**BASE, **FRAMES[frame]})
    block = body["depth_layers"]
    assert block["numbering"] == numbering and block["symbol"] == symbol
    assert block["partition_layers"] == record.lattice.z.n
    assert block["groups"] is None
    assert block["pitch_mm"] == pytest.approx(20.5)
    assert block["display_offset_mm"] == (ddl.CORE_SHIFT_Z_MM if frame == "lab" else None)
    assert isinstance(block["note"], str) and signed_hyphens(block["note"]) == []
    z = record.lattice.z
    if frame == "lab":
        np.testing.assert_allclose(block["edges_mm"], z.edges, rtol=0, atol=EDGE_ATOL)
        assert block["n_layers"] == z.n and block["contiguous"] is False
    elif frame == "canonical":
        np.testing.assert_allclose(block["edges_mm"], z.edges - z.lo, rtol=0, atol=EDGE_ATOL)
        assert block["n_layers"] == z.n
    elif frame == "trans":
        n = body["frame"]["depth"]["n"]
        assert block["n_layers"] == n and block["contiguous"] is True
        np.testing.assert_allclose(block["edges_mm"], lg.half_pitch_edges(n, 20.5), rtol=0,
                                   atol=EDGE_ATOL)
    else:
        assert block["n_layers"] == 0 and block["edges_mm"] is None
    assert (block["reach"] is not None) == (frame in ("trans", "local"))
    profile = block["profile"]
    assert profile["numbering"] == ("detector" if numbering == "detector" else "relative")
    assert sum(profile["energy_gev"]) + profile["outside_gev"] == pytest.approx(
        profile["total_gev"], rel=REL)
    assert profile["attention"] is None
    assert len(json.dumps(block)) < 4000


def test_the_lab_profile_is_the_native_yz_column_sums(single_client, records):
    record = records[BASELINE_TABLE]
    body = _get(single_client, BASE)
    profile = body["depth_layers"]["profile"]
    proj = quote(naming.proj_table(record.table_name))
    rows = dict(_sql(single_client, f"SELECT iz, sum(energy) FROM {proj} GROUP BY iz"))
    expected = [float(rows.get(k, 0.0)) for k in range(record.lattice.z.n)]
    np.testing.assert_allclose(profile["energy_gev"], expected, rtol=REL, atol=1e-15)
    assert profile["outside_gev"] == 0.0 and profile["exact"] is True
    assert profile["total_gev"] == pytest.approx(sum(expected), rel=1e-9)


@pytest.mark.parametrize("frame, pooled", [
    ("lab", False), ("lab", True), ("canonical", False), ("canonical", True),
    ("trans", False), ("trans", True), ("local", False),
])
def test_a_preview_profile_is_marked_inexact(single_client, records, monkeypatch, frame, pooled):
    """LG-C4: the demonstration file is far below the sampling threshold, so lower it and
    make the preview really sample; a profile summed from the sample must say so."""
    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    params = {**BASE, **FRAMES[frame], "preview": "true"}
    if pooled:
        params["depth_groups"] = _uniform(records[BASELINE_TABLE])
    body = _get(single_client, params)
    profile = body["depth_layers"]["profile"]
    if frame == "local":
        # The stated choice: Local's profile is summed from the ingest-time per-shower
        # layer table over every selected event, never from the sampled hits, so it is
        # exact even while the preview's rasters are not.
        assert profile["exact"] is True
        return
    assert body["meta"]["exact"] is False
    assert profile["exact"] is False
    assert (body["depth_layers"]["groups"] is not None) is pooled


def test_the_shapcam_profile_keeps_its_signed_parts_apart(single_client):
    for frame in ("lab", "canonical", "trans"):
        body = _get(single_client, {**BASE, **FRAMES[frame], "channel": "shapcam_energy"})
        attention = body["depth_layers"]["profile"]["attention"]
        assert attention["signed"] is True and attention["quantity"] == "Σ E·Shap-CAM"
        assert min(attention["positive"]) >= 0 and min(attention["negative"]) >= 0
        assert attention["total"] == pytest.approx(
            attention["positive_total"] - attention["negative_total"], rel=1e-9, abs=1e-15)
        assert sum(attention["positive"]) + attention["positive_outside"] == pytest.approx(
            attention["positive_total"], rel=REL)
    grad = _get(single_client, {**BASE, "channel": "gradcam"})["depth_layers"]["profile"]["attention"]
    assert grad["signed"] is False and grad["quantity"] == "Σ E·Grad-CAM"


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE])
def test_reach_equals_a_direct_count_over_the_hits_table(single_client, records, table):
    record = records[table]
    params = {"table_name": table, "coord_system": "trans"}
    block = _get(single_client, params)["depth_layers"]
    reach = block["reach"]
    z = record.lattice.z
    l_phys = lg.physical_layers(z.lo, z.hi, 20.5)
    proj = quote(naming.proj_table(table))
    two = record.kind == ddl.KIND_TWO_SHOWER
    shower = (f"CASE WHEN org = {ddl.ORIGIN_A} THEN 0 ELSE 1 END" if two else "0")
    firsts = _sql(single_client, f"SELECT event_number, {shower}, min(iz) FROM {proj} GROUP BY ALL")
    starts = [lg.start_layer(float(z.coords[int(iz)]), z.lo, 20.5) for _, _, iz in firsts]
    assert reach["n_showers"] == len(starts) and reach["n_without_start"] == 0
    assert reach["l_phys"] == l_phys
    expected = [sum(1 for s in starts if s <= l_phys - 1 - k) for k in range(block["n_layers"])]
    assert reach["counts"] == expected
    assert reach["counts"][0] == reach["n_showers"]
    assert all(a >= b for a, b in zip(reach["counts"], reach["counts"][1:]))


# --------------------------------------------------------- pooling --


@pytest.mark.parametrize("frame", ["lab", "canonical", "trans"])
@pytest.mark.parametrize("display", ["native", "continuous"])
def test_a_pooled_response_has_13_depth_bins_at_the_stored_edges(single_client, records, frame, display):
    record = records[BASELINE_TABLE]
    counts = lg.uniform_counts(record.lattice.z.n)
    params = {**BASE, **FRAMES[frame], "display": display}
    native = _get(single_client, params)
    pooled = _get(single_client, {**params, "depth_groups": lg.format_counts(counts)})
    edges = np.asarray(native["depth_layers"]["edges_mm"])
    n_bins = edges.size - 1
    bins, beyond = lg.group_bins(counts, n_bins)
    expected = edges[[bins[0].start, *(b.stop for b in bins)]]
    groups = pooled["depth_layers"]["groups"]
    assert groups["counts"] == list(counts) and groups["pooled"] is True
    assert groups["beyond_axis"] == list(beyond) == []
    assert groups["bins"][-1]["last"] == n_bins
    for name in ("yz", "xz"):
        panel = pooled["panels"][name]
        assert panel["shape"][1] == 13 == panel["axes"]["col"]["n"]
        np.testing.assert_allclose(_col_edges(panel), expected, rtol=0, atol=EDGE_ATOL)
        # Rows are untouched.
        assert panel["shape"][0] == native["panels"][name]["shape"][0]
    assert pooled["panels"]["xy"] == native["panels"]["xy"]
    # Everything about the layers but the groups is the same.
    assert {k: v for k, v in pooled["depth_layers"].items() if k != "groups"} == \
        {k: v for k, v in native["depth_layers"].items() if k != "groups"}
    assert any("layer groups" in n["text"] for n in pooled["meta"]["notices"])
    assert density.wire_size(pooled) < density.RESPONSE_LIMIT


def test_pooled_lab_panels_conserve_the_energy_and_stay_under_the_peak(single_client, records):
    record = records[BASELINE_TABLE]
    params = {**BASE, "depth_groups": _uniform(record)}
    native, pooled = _get(single_client, BASE), _get(single_client, params)
    for name in ("yz", "xz"):
        assert pooled["panels"][name]["total"] == pytest.approx(native["panels"][name]["total"], rel=1e-9)
        top_native = max(c["value"] for c in native["panels"][name]["topk"])
        top_pooled = max(c["value"] for c in pooled["panels"][name]["topk"])
        assert top_pooled <= top_native * (1 + 1e-6)
    # The scale is the pooled rasters' own: a smaller peak than the per-layer one.
    assert pooled["panels"]["yz"]["scale"]["vmax"] <= native["panels"]["yz"]["scale"]["vmax"] + 1e-12
    signed_native = _get(single_client, {**BASE, "channel": "shapcam_energy"})
    signed_pooled = _get(single_client, {**params, "channel": "shapcam_energy"})
    for name in ("yz", "xz"):
        a, b = signed_native["panels"][name]["scale"], signed_pooled["panels"][name]["scale"]
        assert b["positive_total"] == pytest.approx(a["positive_total"], rel=1e-9)
        assert b["negative_total"] == pytest.approx(a["negative_total"], rel=1e-9)


@pytest.mark.parametrize("frame", ["canonical", "trans"])
def test_pooled_co_registered_panels_conserve_the_in_window_energy(single_client, records, frame):
    params = {**BASE, **FRAMES[frame]}
    native = _get(single_client, params)
    pooled = _get(single_client, {**params, "depth_groups": _uniform(records[BASELINE_TABLE])})
    for name in ("yz", "xz"):
        assert pooled["panels"][name]["total"] == pytest.approx(native["panels"][name]["total"], rel=1e-9)
        assert pooled["panels"][name]["rho_peak"] <= native["panels"][name]["rho_peak"] * (1 + 1e-9)


@pytest.mark.parametrize("frame", ["lab", "canonical", "trans"])
def test_the_comb_is_identical_with_and_without_pooling(single_client, records, frame):
    params = {**BASE, **FRAMES[frame]}
    native = _get(single_client, params)
    pooled = _get(single_client, {**params, "depth_groups": _uniform(records[BASELINE_TABLE])})
    if frame == "lab":
        assert pooled["meta"]["stagger"] == native["meta"]["stagger"]
    else:
        assert pooled["frame"]["comb"] == native["frame"]["comb"]


def test_a_single_shower_experiment_pools_too(single_client, records):
    record = records[SINGLE_HITS_TABLE]
    body = _get(single_client, {**HITS, "depth_groups": _uniform(record)})
    assert body["panels"]["yz"]["shape"][1] == 13
    trans = _get(single_client, {**HITS, "coord_system": "trans", "depth_groups": _uniform(record)})
    assert trans["panels"]["xz"]["shape"][1] == 13 and trans["depth_layers"]["reach"]["n_showers"] > 0


# --------------------------------------------------------- C7 --


def test_profiles_carry_the_reach_on_native_depth_and_none_along_w(single_client):
    native = _get(single_client, {**HITS, "depth": "native"}, "/api/profiles")
    block = native["depth_layers"]
    assert block["numbering"] == "relative" and block["reach"]["n_showers"] > 0
    trans = _get(single_client, {**HITS, "coord_system": "trans"})["depth_layers"]["reach"]
    assert block["reach"]["counts"][:len(trans["counts"])] == trans["counts"][:len(block["reach"]["counts"])]
    w = _get(single_client, {**HITS, "depth": "w"}, "/api/profiles")["depth_layers"]
    assert w["numbering"] == "none" and w["reach"] is None and "tilted" in w["note"]


def test_profile_reach_follows_the_shower_choice(single_client):
    both = _get(single_client, {**BASE, "depth": "native"}, "/api/profiles")["depth_layers"]["reach"]
    a = _get(single_client, {**BASE, "depth": "native", "shower": "a"}, "/api/profiles")
    b = _get(single_client, {**BASE, "depth": "native", "shower": "b"}, "/api/profiles")
    ra, rb = a["depth_layers"]["reach"], b["depth_layers"]["reach"]
    assert ra["n_showers"] + rb["n_showers"] == both["n_showers"]
    assert [x + y for x, y in zip(ra["counts"], rb["counts"])] == both["counts"]


# --------------------------------------------------------- /api/event --


def test_event_frames_carry_layer_planes(single_client, records):
    record = records[BASELINE_TABLE]
    body = _get(single_client, {**BASE, "event_number": 0, "shower": "a"}, "/api/event")
    shower = body["event"]["shower"]
    theta, phi = shower["theta"], shower["phi"]
    lab, trans, local = (body["frames"][k]["layer_planes"] for k in ("lab", "trans", "local"))
    z = record.lattice.z
    assert lab["numbering"] == "detector" and lab["normal"] == [0.0, 0.0, 1.0]
    np.testing.assert_allclose(lab["edges_mm"], z.edges, rtol=0, atol=EDGE_ATOL)
    assert lab["n_layers"] == z.n and lab["display_offset_mm"] == ddl.CORE_SHIFT_Z_MM
    assert sum(lab["energy_gev"]) == pytest.approx(shower["energy_gev"], rel=REL)
    assert lab["start_layer"] == int(z.index_of(np.array([shower["first_layer_z"]]))[0]) + 1
    for planes in (trans, local):
        assert planes["numbering"] == "relative"
        assert sum(planes["energy_gev"]) == pytest.approx(shower["energy_gev"], rel=REL)
        np.testing.assert_allclose(planes["edges_mm"], lg.half_pitch_edges(planes["n_layers"], 20.5),
                                   rtol=0, atol=EDGE_ATOL)
        assert planes["reach_layers"] == lg.physical_layers(z.lo, z.hi, 20.5) - lg.start_layer(
            shower["first_layer_z"], z.lo, 20.5)
        assert planes["display_offset_mm"] is None
    assert trans["normal"] == [0.0, 0.0, 1.0] and trans["line_panels"] == ["xz", "yz"]
    normal = frame_mod.rotation_matrix(theta, phi) @ np.array([0.0, 0.0, 1.0])
    np.testing.assert_allclose(local["normal"], normal, atol=1e-12)
    assert local["line_panels"] == (["xz"] if theta != 0.0 else ["xz", "yz"])
    assert local["tilt"]["theta"] == pytest.approx(theta)
    assert local["tilt"]["pitch_along_w_mm"] == pytest.approx(20.5 / math.cos(theta))


def test_the_reach_note_agrees_with_its_count(single_client):
    """LG-G7: one shower kind writes 'showers', one shower of a pair is named."""
    single = _get(single_client, {**HITS, "coord_system": "trans"})["depth_layers"]["reach"]
    assert single["note"].endswith(f"of the selection's {single['n_showers']:,} showers reach it.")
    both = _get(single_client, {**BASE, "coord_system": "trans"})["depth_layers"]["reach"]
    assert both["note"].endswith(f"of the selection's {both['n_showers']:,} showers A and B reach it.")
    for shower in ("a", "b"):
        one = _get(single_client, {**BASE, "depth": "native", "shower": shower},
                   "/api/profiles")["depth_layers"]["reach"]
        assert one["note"].endswith(
            f"of the selection's {one['n_showers']:,} showers {shower.upper()} reach it.")
    c7 = _get(single_client, {**HITS, "depth": "native"}, "/api/profiles")["depth_layers"]["reach"]
    assert " shower reach " not in c7["note"] and c7["note"].endswith("showers reach it.")


# ---------------------------------------------- compaction and the 100 KB yield (LG-C2) --


def _figures(value: float) -> int:
    """Significant figures of a shipped float, as JSON writes it."""
    digits = repr(abs(float(value))).split("e")[0].replace(".", "").lstrip("0").rstrip("0")
    return len(digits) or 1


def _per_layer_arrays(profile: dict) -> list[list[float]]:
    arrays = [profile["energy_gev"]]
    attention = profile["attention"]
    if attention is not None:
        arrays += [attention[k] for k in ("values", "positive", "negative") if k in attention]
    return arrays


@pytest.mark.parametrize("frame", list(FRAMES))
def test_the_layer_blocks_travel_compacted(single_client, frame):
    for channel in ("density", "gradcam", "shapcam_energy"):
        block = _get(single_client, {**BASE, **FRAMES[frame], "channel": channel})["depth_layers"]
        for values in _per_layer_arrays(block["profile"]):
            assert values and all(_figures(v) <= layer_profile.DIGITS for v in values)
        if block["edges_mm"] is not None:
            assert all(round(v, layer_profile.EDGE_DECIMALS) == v for v in block["edges_mm"])
        assert "trimmed" not in block and "trim_note" not in block
    planes = _get(single_client, {**BASE, "event_number": 0, "shower": "a"}, "/api/event")["frames"]
    for kind in ("lab", "trans", "local"):
        block = planes[kind]["layer_planes"]
        assert all(_figures(v) <= layer_profile.DIGITS for v in block["energy_gev"])
        assert all(round(v, layer_profile.EDGE_DECIMALS) == v for v in block["edges_mm"])
        assert "trimmed" not in block


def _shapes(body: dict) -> dict:
    return {name: body["panels"][name]["shape"] for name in ("xy", "yz", "xz")}


def _steps(body: dict) -> list[str]:
    return [n["text"] for n in body["meta"]["notices"]
            if n["scope"] == "resolution" and ("lowered" in n["text"] or "merged" in n["text"])]


def _trimmed_size(body: dict) -> int:
    block, did = layer_profile.trim_depth_layers(body["depth_layers"])
    assert did
    return density.wire_size({**body, "depth_layers": block})


@pytest.mark.parametrize("frame", list(FRAMES))
def test_over_the_contract_the_layer_block_yields_before_the_raster(single_client, monkeypatch, frame):
    params = {**BASE, **FRAMES[frame], "display": "continuous", "resolution": 100,
              "channel": "shapcam_energy"}
    full = _get(single_client, params)
    assert "trimmed" not in full["depth_layers"]
    size, trimmed_size = density.wire_size(full), _trimmed_size(full)
    assert trimmed_size < size - 300
    # Between the two: over with the block, under without its arrays.
    monkeypatch.setattr(density, "RESPONSE_LIMIT", (size + trimmed_size) // 2)
    body = _get(single_client, params)
    block = body["depth_layers"]
    assert block["trimmed"] is True and block["profile"] is None and block["reach"] is None
    assert block["trim_note"] == layer_profile.TRIM_NOTE
    assert {k: v for k, v in block.items() if k not in ("profile", "reach", "trimmed", "trim_note")} \
        == {k: v for k, v in full["depth_layers"].items() if k not in ("profile", "reach")}
    assert _shapes(body) == _shapes(full) and body["meta"]["resolution"] == full["meta"]["resolution"]
    # No step of its own: only the panel guard's, which the full body took as well.
    assert _steps(body) == _steps(full)
    assert not any("served as it is" in n["text"] or "whole response measured" in n["text"]
                   for n in body["meta"]["notices"])
    assert density.wire_size(body) < density.RESPONSE_LIMIT


@pytest.mark.parametrize("frame", ["lab", "canonical", "trans"])
def test_still_over_after_the_trim_the_raster_coarsens_and_the_block_stays_trimmed(
        single_client, monkeypatch, frame):
    params = {**BASE, **FRAMES[frame], "display": "continuous", "resolution": 300}
    full = _get(single_client, params)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", _trimmed_size(full) - 200)
    body = _get(single_client, params)
    block = body["depth_layers"]
    assert block["trimmed"] is True and block["profile"] is None
    assert block["trim_note"] == layer_profile.TRIM_NOTE_COARSENED
    assert any("Resolution lowered" in text for text in _steps(body))
    assert density.wire_size(body) < density.RESPONSE_LIMIT


def test_a_native_lab_response_yields_its_block_before_it_is_served_over(single_client, monkeypatch):
    params = {**BASE, "display": "native", "channel": "gradcam"}
    full = _get(single_client, params)
    size, trimmed_size = density.wire_size(full), _trimmed_size(full)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", (size + trimmed_size) // 2)
    fits = _get(single_client, params)
    assert fits["depth_layers"]["trimmed"] is True
    assert not any("served as it is" in n["text"] for n in fits["meta"]["notices"])
    assert _shapes(fits) == _shapes(full)
    # Below even the trimmed body: the native lattice has no coarser form, so it is served
    # as measured, trimmed, and its note says the raster kept its resolution.
    monkeypatch.setattr(density, "RESPONSE_LIMIT", trimmed_size - 200)
    over = _get(single_client, params)
    assert over["depth_layers"]["trim_note"] == layer_profile.TRIM_NOTE
    assert any("served as it is" in n["text"] for n in over["meta"]["notices"])
    assert _shapes(over) == _shapes(full)


def test_an_event_over_the_contract_yields_its_layer_planes_before_the_grids(single_client, records):
    record = records[BASELINE_TABLE]
    with single_client.app.state.database.read_cursor() as con:
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)

        def run(limit=None):
            return event_inspector.inspect(con, record, spec, 0, "a", frame_sql.SOURCE_FILE,
                                           footprint, limit=limit)

        full = run()
        # The guard measures the figure before the event's own metadata joins it.
        measured = {k: full[k] for k in ("frames", "scale", "grid")}
        planes, _ = layer_profile.trim_layer_planes(
            {k: f["layer_planes"] for k, f in full["frames"].items()})
        trimmed = {**measured, "frames": {k: {**f, "layer_planes": planes[k]}
                                          for k, f in full["frames"].items()}}
        size, trimmed_size = density.wire_size(measured), density.wire_size(trimmed)
        assert trimmed_size < size - 300
        mid = run((size + trimmed_size) // 2)
        assert mid["grid"]["pitch_mm"] == full["grid"]["pitch_mm"] and mid["grid"]["notes"] == []
        for kind, frame in mid["frames"].items():
            block = frame["layer_planes"]
            assert block["energy_gev"] is None and block["trimmed"] is True
            assert block["trim_note"] == layer_profile.TRIM_NOTE_EVENT
            assert block["edges_mm"] == full["frames"][kind]["layer_planes"]["edges_mm"]
            assert frame["panels"] == full["frames"][kind]["panels"]
        tight = run(trimmed_size - 200)
        assert tight["grid"]["pitch_mm"] > full["grid"]["pitch_mm"]
        assert all(f["layer_planes"]["trim_note"] == layer_profile.TRIM_NOTE_EVENT_COARSENED
                   for f in tight["frames"].values())


def _guard_cases() -> list[tuple[str, str, str, int]]:
    cases = []
    for frame in FRAMES:
        for channel in ("density", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy"):
            cases += [(BASELINE_TABLE, frame, channel, r) for r in (300, 350, 400)]
    for frame in ("lab", "trans", "local"):
        cases += [(SINGLE_HITS_TABLE, frame, "density", r) for r in (300, 350, 400)]
    return cases


def test_the_layer_blocks_never_lower_the_served_resolution(single_client, monkeypatch):
    """LG-C2's regression: the continuous R 300/350/400 views of every channel are served at
    the resolution they would have without the layer block (``depth_layers`` patched away).
    Before the yield, Absolute gradcam_energy and shapcam_energy at R = 350 stepped to 262."""
    def served(case):
        table, frame, channel, r = case
        body = _get(single_client, {"table_name": table, **FRAMES[frame], "channel": channel,
                                    "display": "continuous", "resolution": r})
        assert density.wire_size(body) < density.RESPONSE_LIMIT
        return _shapes(body), len(_steps(body))

    cases = _guard_cases()
    with_block = {case: served(case) for case in cases}
    monkeypatch.setattr(layer_profile, "depth_layers", lambda *a, **k: None)
    without = {case: served(case) for case in cases}
    moved = [case for case in cases if with_block[case] != without[case]]
    assert moved == [], moved
    # The fixture holds views the guard has to step at all, so the comparison has teeth.
    assert any(steps for _, steps in without.values())


def test_the_layer_planes_never_coarsen_the_event_grids(single_client, monkeypatch):
    events = [row[0] for row in _sql(
        single_client, f"SELECT event_number FROM {quote(naming.event_table(BASELINE_TABLE))} "
        "WHERE d IS NOT NULL ORDER BY event_number")]
    cases = [(e, s, w) for e in events for s in ("a", "b") for w in ("shared", "per_axis")]

    def pitch(case):
        event, shower, window = case
        return _get(single_client, {**BASE, "event_number": event, "shower": shower,
                                    "window": window}, "/api/event")["grid"]["pitch_mm"]

    with_planes = {case: pitch(case) for case in cases}
    monkeypatch.setattr(layer_profile, "layer_planes", lambda *a, **k: None)
    without = {case: pitch(case) for case in cases}
    assert with_planes == without
