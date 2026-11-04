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
from calosrv.query import density
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
        np.testing.assert_allclose(block["edges_mm"], z.edges, atol=1e-6)
        assert block["n_layers"] == z.n and block["contiguous"] is False
    elif frame == "canonical":
        np.testing.assert_allclose(block["edges_mm"], z.edges - z.lo, atol=1e-6)
        assert block["n_layers"] == z.n
    elif frame == "trans":
        n = body["frame"]["depth"]["n"]
        assert block["n_layers"] == n and block["contiguous"] is True
        np.testing.assert_allclose(block["edges_mm"], lg.half_pitch_edges(n, 20.5), atol=1e-6)
    else:
        assert block["n_layers"] == 0 and block["edges_mm"] is None
    assert (block["reach"] is not None) == (frame in ("trans", "local"))
    profile = block["profile"]
    assert profile["numbering"] == ("detector" if numbering == "detector" else "relative")
    assert sum(profile["energy_gev"]) + profile["outside_gev"] == pytest.approx(
        profile["total_gev"], rel=1e-9)
    assert profile["attention"] is None
    assert len(json.dumps(block)) < 4000


def test_the_lab_profile_is_the_native_yz_column_sums(single_client, records):
    record = records[BASELINE_TABLE]
    body = _get(single_client, BASE)
    profile = body["depth_layers"]["profile"]
    proj = quote(naming.proj_table(record.table_name))
    rows = dict(_sql(single_client, f"SELECT iz, sum(energy) FROM {proj} GROUP BY iz"))
    expected = [float(rows.get(k, 0.0)) for k in range(record.lattice.z.n)]
    np.testing.assert_allclose(profile["energy_gev"], expected, rtol=1e-9, atol=1e-15)
    assert profile["outside_gev"] == 0.0 and profile["exact"] is True
    assert profile["total_gev"] == pytest.approx(sum(expected), rel=1e-9)


def test_a_preview_profile_is_marked_inexact(single_client):
    body = _get(single_client, {**BASE, "preview": "true"})
    assert body["depth_layers"]["profile"]["exact"] is body["meta"]["exact"]


def test_the_shapcam_profile_keeps_its_signed_parts_apart(single_client):
    for frame in ("lab", "canonical", "trans"):
        body = _get(single_client, {**BASE, **FRAMES[frame], "channel": "shapcam_energy"})
        attention = body["depth_layers"]["profile"]["attention"]
        assert attention["signed"] is True and attention["quantity"] == "Σ E·Shap-CAM"
        assert min(attention["positive"]) >= 0 and min(attention["negative"]) >= 0
        assert attention["total"] == pytest.approx(
            attention["positive_total"] - attention["negative_total"], rel=1e-9, abs=1e-15)
        assert sum(attention["positive"]) + attention["positive_outside"] == pytest.approx(
            attention["positive_total"], rel=1e-9)
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
        np.testing.assert_allclose(_col_edges(panel), expected, atol=1e-6)
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
    np.testing.assert_allclose(lab["edges_mm"], z.edges, atol=1e-6)
    assert lab["n_layers"] == z.n and lab["display_offset_mm"] == ddl.CORE_SHIFT_Z_MM
    assert sum(lab["energy_gev"]) == pytest.approx(shower["energy_gev"], rel=1e-9)
    assert lab["start_layer"] == int(z.index_of(np.array([shower["first_layer_z"]]))[0]) + 1
    for planes in (trans, local):
        assert planes["numbering"] == "relative"
        assert sum(planes["energy_gev"]) == pytest.approx(shower["energy_gev"], rel=1e-9)
        np.testing.assert_allclose(planes["edges_mm"], lg.half_pitch_edges(planes["n_layers"], 20.5))
        assert planes["reach_layers"] == lg.physical_layers(z.lo, z.hi, 20.5) - lg.start_layer(
            shower["first_layer_z"], z.lo, 20.5)
        assert planes["display_offset_mm"] is None
    assert trans["normal"] == [0.0, 0.0, 1.0] and trans["line_panels"] == ["xz", "yz"]
    normal = frame_mod.rotation_matrix(theta, phi) @ np.array([0.0, 0.0, 1.0])
    np.testing.assert_allclose(local["normal"], normal, atol=1e-12)
    assert local["line_panels"] == (["xz"] if theta != 0.0 else ["xz", "yz"])
    assert local["tilt"]["theta"] == pytest.approx(theta)
    assert local["tilt"]["pitch_along_w_mm"] == pytest.approx(20.5 / math.cos(theta))
