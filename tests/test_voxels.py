"""``GET /api/voxels``: the ensemble 3-D voxels of the Local frame and the D-frame.

The two-level voxel query against NumPy sub-deposits and an independent fine
aggregate (sums, raw peaks, ρ_ref), energy and E × CAM conservation against
the 2-D bundles of the same selection, the origin-centred 2 × 2 merge on both
parities, the floor, the cap, the layer-run packing, the cache, the preview
sample, the single scan - and, through the booted app, the contract, the
refusals, the quoted comb, the low-N labels and the whole-body guard.

Three booted fixtures, in this order - each resets the process-wide database,
so every test of one sits above the first test of the next: ``client`` (the
two-event demonstration), ``synthetic_client`` (286 two-shower events in
low-N separation slices) and ``single_client`` (single-shower hits in low-N
momentum bins, and an aggregate without hits). The query-level tests read the
session's ingested demonstration database and run after all of them.
"""

from __future__ import annotations

import base64
import copy
import re
import threading
import time

import duckdb
import numpy as np
import pytest

import contract_check
from conftest import SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from calosrv.api import budget as budget_mod
from calosrv.api import frame_canonical, routes_voxels
from calosrv.db import ddl, naming, registry
from calosrv.db.naming import quote
from calosrv.encode import quantize
from calosrv.encode import scale as scale_mod
from calosrv.encode import voxels as encode_voxels
from calosrv.grid import frame as frame_mod
from calosrv.query import cache as cache_mod
from calosrv.query import (canonical, canonical_cache, density, filters, physics_cache, sampling,
                           shower_frames, voxels)
from calosrv.text import signed_hyphens, typographic

URL = "/api/voxels"

#: Payload strings that are data, not sentences.
DATA_KEYS = tuple(voxels.VERBATIM_KEYS)

#: The one place a ``hits`` key may appear: the frozen C9 negative-depth block
#: (``statistics.json`` ``$defs/negative_w``), where it is an integer count of
#: the hits behind the entry plane, never an array.
_NEGATIVE_W_COUNT = re.compile(r"^\.frame\.negative_w\.splits\[\d+\]$")

#: A guard step's sentence: the size that forced it and the cap change.
_STEP = re.compile(r"measured ([\d,]+) bytes against the ([\d,]+)-byte contract, so the voxel cap "
                   r"was lowered from ([\d,]+) to ([\d,]+)")

#: Separation slices of ``synthetic_all_models`` (centre, events), 50 mm wide.
SYNTHETIC_SLICES = ((25.0, 1), (75.0, 2), (125.0, 7), (325.0, 19), (375.0, 20))

#: Momentum bins of ``synthetic_single_shower`` (bin, events).
SINGLE_BINS = ((3, 1), (7, 2), (12, 7), (19, 19), (2, 20))


# --------------------------------------------------------------- helpers --


def _walk(node, path=""):
    """Every ``(path, key, value)`` of a JSON body."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _check_body(body: dict) -> None:
    """The contract, no ``hits`` or ``points`` key anywhere, and U+2212 in every sentence.

    The walk covers the whole body, meta included (the cache counters are
    named ``cache_hits`` and ``cache_misses``). The only ``hits`` key is the
    negative-depth block's integer count, whose shape another contract freezes.
    """
    contract_check.check(body, "voxels")
    for path, key, value in _walk(body):
        if key in ("hits", "points"):
            assert key == "hits" and _NEGATIVE_W_COUNT.match(path), (path, key)
            assert isinstance(value, int) and not isinstance(value, bool), (path, value)
        if isinstance(value, str) and key not in DATA_KEYS:
            assert not signed_hyphens(value), (path, key, signed_hyphens(value))
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    assert not signed_hyphens(item), (path, key, item)


def _get(client, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    _check_body(body)
    assert density.wire_size(body) == len(response.content) < density.RESPONSE_LIMIT
    return body


def _refused(client, field: str, capability: str | None = None, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["field"] == field, problem
    if capability is not None:
        contract_check.check(problem, "capability_problem")
        assert problem["capability"] == capability, problem
        assert not signed_hyphens(problem["reason"])
    return problem


def _decode(body: dict) -> dict[str, np.ndarray]:
    """The shipped voxels as millimetre centres and codes, in payload order."""
    grid, block = body["grid"], body["voxels"]
    ox, oy, oz, codes = encode_voxels.unpack_layer_runs(block, grid["n"][2])
    return {
        "ox": ox, "oy": oy, "oz": oz, "code": codes,
        "x": grid["x_centre0"] + grid["voxel_mm"][0] * ox,
        "y": grid["y_centre0"] + grid["voxel_mm"][1] * oy,
        "z": np.asarray(grid["z_centres"])[oz],
    }


def _table(client) -> str:
    return client.get("/api/experiments").json()["experiments"][0]["table_name"]


def _record(client, table: str):
    with client.app.state.database.read_cursor() as con:
        return registry.require_ready(con, table)


def _response(client, table: str | None = None, **kwargs) -> routes_voxels.VoxelResponse:
    """The route's response object for the full selection, every database read done."""
    record = _record(client, table or _table(client))
    with client.app.state.database.read_cursor() as con:
        return routes_voxels.VoxelResponse(con, record, filters.build(record),
                                           client.app.state.settings, **kwargs)


def _steps(body: dict) -> list[tuple[int, int, int, int]]:
    """``(size, limit, old, new)`` of every guard step the body discloses, in order."""
    out = []
    for text in body["meta"]["notices"]:
        match = _STEP.search(text)
        if match:
            out.append(tuple(int(g.replace(",", "")) for g in match.groups()))
    return out


def _one_step_size(response: routes_voxels.VoxelResponse, size: int, limit: int, cap: int) -> int:
    """The body at ``cap`` as served after one disclosed step from the requested cap."""
    step = response.step_sentence(response.cap, cap, size, limit)
    return density.wire_size(response.build(cap, [step]))


# ------------------------------------------------------------- client --


@pytest.mark.parametrize("frame", voxels.FRAMES)
@pytest.mark.parametrize("channel", voxels.CHANNELS)
def test_every_frame_and_channel_is_served_under_the_contract(client, frame, channel):
    body = _get(client, frame=frame, channel=channel)
    budget = body["budget"]
    decoded = _decode(body)
    assert body["voxels"]["n"] == budget["n_drawn"] == decoded["code"].size > 0
    assert decoded["code"].min() >= voxels.MIN_DRAWN_CODE
    assert budget["n_populated"] == budget["n_below_floor"] + budget["n_above_floor"]
    assert budget["n_above_floor"] == budget["n_drawn"] + budget["n_beyond_cap"]
    assert sum(budget["energy_fraction"].values()) == pytest.approx(1.0, abs=1e-8)
    assert sum(budget["energy_gev"].values()) == pytest.approx(budget["energy_total_gev"], rel=1e-12)
    # Sorted by depth, then y, then x, as the packing promises.
    order = np.lexsort((decoded["ox"], decoded["oy"], decoded["oz"]))
    assert (order == np.arange(order.size)).all()
    # Two events: weak evidence, said on the frame and in the notices.
    assert body["frame"]["provisional"] and body["rho"]["provisional"]
    assert any(text.startswith("N = 2: weak evidence") for text in body["meta"]["notices"])
    assert body["frame"]["splat"]["k"] >= frame_mod.MIN_SUBSAMPLE
    cam = body["meta"]["cam"]
    rho, scale = body["rho"], body["scale"]
    if channel == "density":
        assert cam is None and body["budget"]["cam"] is None
        # The floor applied is 10⁻³ of the energy reference, named as such.
        assert rho["floor_basis"] == "rho_ref" and scale["rho_ref"] == rho["rho_ref"]
        assert rho["floor"] == pytest.approx(rho["rho_ref"] * voxels.FLOOR_RATIO, rel=1e-12)
    else:
        assert cam["network_frame"] == ("local" if frame == "local" else "absolute")
        assert cam["note"] in body["meta"]["notices"]
        assert body["budget"]["cam"]["quantity"] == channel
        # The floor applied is 10⁻³ of the channel's own peak, and that peak is
        # never published under the energy reference's name.
        assert rho["floor_basis"] == "cam_ref" and rho["cam_ref"] != rho["rho_ref"]
        assert rho["floor"] == pytest.approx(rho["cam_ref"] * voxels.FLOOR_RATIO, rel=1e-12)
        assert "rho_ref" not in scale and scale["ref"] == rho["cam_ref"]
        assert scale["ref_name"] == "cam_ref"
        assert any("10⁻³ of cam_ref" in text for text in body["meta"]["notices"])
    if frame == "local":
        assert body["frame"]["symbols"] == {"x": "u", "y": "v", "z": "w"}
        assert body["frame"]["coordinate_check"]["within_tolerance"]
        assert any("no ensemble axis is drawn" in text for text in body["meta"]["notices"])
        assert body["frame"]["negative_w"]["available"] is True
        assert body["frame"]["n_ill_conditioned"] is None
    else:
        assert body["frame"]["coordinates"] is None and body["frame"]["anchor"] == "entry_backprojection"
        assert "negative_w" not in body["frame"]
        assert body["frame"]["ill_conditioned_threshold_mm"] == frame_mod.ILL_CONDITIONED_D_MM


def test_shapcam_energy_is_signed_on_the_split_ramp(client):
    body = _get(client, channel="shapcam_energy", model="energy")
    scale = body["scale"]
    assert scale["scale"] == "signed_log10" and scale["diverging"] is True
    assert scale["split_code"] == quantize.SPLIT_CODE
    assert scale["positive_total"] >= 0 >= scale["negative_total"]
    codes = _decode(body)["code"]
    assert codes.min() >= quantize.SIGNED_MIN_CODE
    # The exact values ride beside the codes, with their signs.
    for entry, code in ((t, codes[t["i"]]) for t in body["topk"]):
        assert (entry["value"] < 0) == (code < quantize.SPLIT_CODE)
    assert body["meta"]["cam"]["column"] == ddl.csv_model_column("energy", "local", "shapcam")
    assert body["meta"]["cam"]["normalisation"] == "shower"


def test_the_origin_is_a_voxel_centre_in_the_payload(client):
    """Every shower passes through the Local origin, so its voxel column is drawn, centred at 0."""
    body = _get(client)
    decoded = _decode(body)
    assert 0.0 in set(decoded["x"].tolist()) and 0.0 in set(decoded["y"].tolist())
    edge = body["grid"]["partial_edge"]
    assert edge["x"] != edge["y"]  # the demonstration grid has one even and one odd half-width


def test_refusals_name_the_field_and_the_reason(client):
    # trans is a plain validation error on frame, not a missing capability:
    # the experiment has the ensemble card, and the advice names what it offers.
    problem = _refused(client, "frame", frame="trans")
    assert problem["type"] == "/problems/validation-error" and "capability" not in problem
    assert problem["detail"].startswith("frame=trans is not offered: ")
    assert "box-overlap" in problem["detail"]
    assert problem["detail"].endswith("Use frame=local or frame=canonical.")
    lab = _refused(client, "frame", frame="lab")
    assert "local, canonical" in lab["detail"]
    _refused(client, "channel", channel="gradcam")
    _refused(client, "model", model="nonsense")
    _refused(client, "anchor", anchor="p0")
    _refused(client, "coordinates", frame="canonical", coordinates="computed")
    # A refusal echoing a signed request value sets it with U+2212.
    signed = _refused(client, "anchor", frame="canonical", anchor="-1")
    assert "'−1'" in signed["detail"] and not signed_hyphens(signed["detail"])
    assert client.get(URL, params={"cap": 999}).status_code == 422
    assert client.get(URL, params={"cap": 15_001}).status_code == 422


def test_the_p0_anchor_and_computed_coordinates_are_served(client):
    p0 = _get(client, frame="canonical", anchor="p0")
    assert p0["frame"]["anchor"] == "p0_backprojection" and p0["meta"]["anchor"] == "p0"
    computed = _get(client, coordinates="computed")
    assert computed["frame"]["coordinates"] == "computed"
    file = _get(client)
    assert computed["budget"]["energy_total_gev"] == pytest.approx(file["budget"]["energy_total_gev"],
                                                                   rel=1e-12)


def test_a_repeat_is_cached_and_invalidation_drops_it(client):
    table = _table(client)
    cache_mod.invalidate_all(table)
    first = _get(client, channel="gradcam_energy")
    again = _get(client, channel="gradcam_energy")
    assert not first["meta"]["cached"] and again["meta"]["cached"]
    assert again["meta"]["query_ms"] == 0.0
    # Density is the same for every network: another model's bundle serves it.
    assert _get(client, channel="density", model="angle")["meta"]["cached"]
    assert cache_mod.invalidate_all(table) >= 1
    assert not _get(client, channel="gradcam_energy")["meta"]["cached"]


@pytest.mark.parametrize("frame,projection", [
    ("local", {"coord_system": "local"}),
    ("canonical", {"frame": "canonical"}),
])
def test_the_comb_is_quoted_from_the_2d_panels_once_they_have_measured_it(client, frame, projection):
    """A one-event selection no warmer computes: absent first, then exactly the 2-D verdict."""
    table = _table(client)
    with client.app.state.database.read_cursor() as con:
        e1 = con.execute(f"SELECT min(e1) FROM {quote(naming.event_table(table))}").fetchone()[0]
    selection = {"e1_min": float(e1) - 0.01, "e1_max": float(e1) + 0.01}
    cache_mod.invalidate_all(table)
    absent = _get(client, frame=frame, **selection)
    assert absent["frame"]["n_events"] == 1
    assert absent["frame"]["comb"] is None
    assert absent["frame"]["comb_source"].startswith("Comb not measured here")
    assert absent["frame"]["comb_source"] in absent["meta"]["notices"]
    assert absent["frame"]["n_label"].startswith("N = 1: one event's own deposit")

    panels = client.get("/api/projections", params={**projection, **selection})
    assert panels.status_code == 200, panels.text
    quoted = _get(client, frame=frame, **selection)
    assert quoted["frame"]["comb"] == panels.json()["frame"]["comb"]
    assert quoted["frame"]["comb_source"].startswith("Comb quoted from the 2-D")
    assert quoted["frame"]["comb"]["note"] in quoted["meta"]["notices"]


def test_the_guard_lowers_the_cap_and_says_so(client, monkeypatch):
    full = _get(client)
    size = density.wire_size(full)
    limit = size - 2_000
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)
    body = _get(client)
    assert density.wire_size(body) < limit
    assert body["budget"]["cap"] < full["budget"]["n_drawn"] == full["budget"]["n_above_floor"]
    assert body["budget"]["cap_requested"] == voxels.DEFAULT_CAP
    assert body["budget"]["n_drawn"] == body["budget"]["cap"]
    assert body["budget"]["n_beyond_cap"] > 0 and body["budget"]["energy_fraction"]["beyond_cap"] > 0
    # One step, disclosed first, quoting the size that forced it and the cap it chose.
    steps = _steps(body)
    assert len(steps) == 1
    measured, contract, old, new = steps[0]
    assert contract == limit and measured >= limit and new == body["budget"]["cap"] < old
    assert _STEP.search(body["meta"]["notices"][0])
    assert any("beyond the" in text and "cap, ranked by energy" in text for text in body["meta"]["notices"])
    assert not any("served as it is" in w for w in body["meta"]["warnings"])
    # Lowering the cap keeps the brightest voxels: the shipped set is a prefix by energy.
    assert body["budget"]["energy_gev"]["drawn"] > 0.5 * full["budget"]["energy_gev"]["drawn"]


@pytest.mark.parametrize("frame,channel", [("local", "density"), ("canonical", "shapcam_energy"),
                                           ("local", "gradcam_energy")])
def test_a_fitting_rendering_is_found_whenever_one_exists(client, monkeypatch, frame, channel):
    """The smallest limit the one-step cap-1 body fits is served under it; one byte less, nothing fits.

    Between that limit and the full body, every limit is served under it in
    one disclosed step, at a cap whose next voxel would not have fitted.
    """
    response = _response(client, frame=frame, channel=channel)
    n_above = response.classified.n_above
    assert n_above > 2
    size = density.wire_size(response.build(response.cap, []))
    # The smallest limit L the cap-1 body fits under, with the sentence of the
    # step that brought it there (whose digits depend on L).
    lowest = _one_step_size(response, size, size, 1) + 1
    for _ in range(5):
        settled = _one_step_size(response, size, lowest, 1) + 1
        if settled == lowest:
            break
        lowest = settled
    assert lowest == _one_step_size(response, size, lowest, 1) + 1

    monkeypatch.setattr(density, "RESPONSE_LIMIT", lowest)
    body = response.serve()
    _check_body(body)
    assert density.wire_size(body) < lowest
    assert body["budget"]["n_drawn"] == body["budget"]["cap"] == 1
    assert [step[3] for step in _steps(body)] == [1]
    assert not any("served as it is" in w for w in body["meta"]["warnings"])

    # One byte less and not even one voxel fits: nothing is withheld, the
    # overrun is stated, and no step is claimed.
    assert _one_step_size(response, size, lowest - 1, 1) >= lowest - 1
    monkeypatch.setattr(density, "RESPONSE_LIMIT", lowest - 1)
    body = response.serve()
    _check_body(body)
    assert body["budget"]["n_drawn"] == n_above and body["budget"]["n_beyond_cap"] == 0
    assert _steps(body) == []
    warning = [w for w in body["meta"]["warnings"] if "served as it is" in w]
    assert len(warning) == 1 and f"still {density.wire_size(body):,} bytes" in warning[0]

    # Every limit in between: under it, in one step, at a locally largest cap.
    for limit in np.unique(np.linspace(lowest, size, 9).astype(int)):
        monkeypatch.setattr(density, "RESPONSE_LIMIT", int(limit))
        body = response.serve()
        served = density.wire_size(body)
        assert served < limit, (limit, served)
        if limit > size:
            assert _steps(body) == []
            continue
        (step,) = _steps(body)
        cap = body["budget"]["cap"]
        assert step == (size, limit, n_above, cap) and body["budget"]["n_drawn"] == cap
        assert served == _one_step_size(response, size, int(limit), cap)
        if cap + 1 < n_above:
            assert _one_step_size(response, size, int(limit), cap + 1) >= limit
        assert not any("served as it is" in w for w in body["meta"]["warnings"])


def test_every_step_of_a_several_step_guard_is_disclosed_in_order(client, monkeypatch):
    """Through ``serve_measured`` with a halving step: each step is said, in order, in the body."""
    response = _response(client)
    n_above = response.classified.n_above
    target = max(1, n_above // 10)
    limit = density.wire_size(response.build(target, [])) + 1_500
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)

    def halve(cap: int, size: int, limit_: int) -> int | None:
        current = min(cap, n_above)
        return current // 2 if current > 1 else None

    response._steps = []
    body = budget_mod.serve_measured(response.build, response.cap, halve, response.describe)
    _check_body(body)
    assert density.wire_size(body) < limit
    steps = _steps(body)
    assert len(steps) >= 2
    old = n_above
    for size, contract, old_cap, new_cap in steps:
        assert contract == limit and size >= limit
        assert old_cap == old and new_cap == old // 2
        old = new_cap
    assert body["budget"]["cap"] == old == body["budget"]["n_drawn"]
    # The step sentences open the notices, in the order they were taken.
    assert [bool(_STEP.search(t)) for t in body["meta"]["notices"][:len(steps)]] == [True] * len(steps)
    assert response._steps == body["meta"]["notices"][:len(steps)]


def _production_sized(bundle: voxels.VoxelBundle, n: int = 40_000) -> voxels.VoxelBundle:
    """A bundle on the production D-frame or Local grid with ``n`` voxels, all above the floor."""
    rng = np.random.default_rng(7)
    half_x, half_y, n_z = (3980.0, 1380.0, 60) if bundle.kind == "canonical" else (1500.0, 1280.0, 85)
    grid = frame_mod.CanonicalGrid(20.0, half_x, half_y, 0.0, np.arange(n_z) * bundle.dz)
    ax, ay = voxels.merged_axis(half_x, 20.0), voxels.merged_axis(half_y, 20.0)
    flat = rng.choice(ax.n * ay.n * n_z, n, replace=False)
    vx, rest = np.divmod(flat, ay.n * n_z)
    vy, vz = np.divmod(rest, n_z)
    e = rng.uniform(0.01, 1.0, n)
    sums = {"e": e, "n": e, "eg": 0.5 * e, "esp": 0.6 * e, "esn": -0.3 * e}
    return voxels.VoxelBundle(
        "canonical" if bundle.kind == "canonical" else "local", grid, ax, ay, bundle.dz,
        vx.astype(np.int16), vy.astype(np.int16), vz.astype(np.int16), sums,
        {"e": e, "eg": 0.5 * e, "s": 0.3 * e}, {p: 0.0 for p in voxels.VOXEL_PLANES},
        bundle.n_events, bundle.subsample_k, bundle.k_z, bundle.footprint, False, 1.0,
        voxels.VOXEL_PLANES)


@pytest.mark.parametrize("frame", voxels.FRAMES)
@pytest.mark.parametrize("channel", voxels.CHANNELS)
def test_the_full_cap_fits_the_contract_on_a_production_sized_cloud(client, monkeypatch, frame, channel):
    """15 000 voxels above the floor on the production grid: about 75 KB, no reduction needed."""
    real = voxels.bundle_for

    def production(*args, **kwargs):
        bundle, stats, grid, k, _ = real(*args, **kwargs)
        big = _production_sized(bundle)
        return big, stats, big.grid, k, False

    monkeypatch.setattr(voxels, "bundle_for", production)
    body = _get(client, frame=frame, channel=channel)
    assert body["voxels"]["n"] == body["budget"]["cap"] == voxels.DEFAULT_CAP
    budget = body["budget"]
    assert budget["n_above_floor"] + budget["n_partial_edge"] == 40_000
    assert budget["n_beyond_cap"] == budget["n_above_floor"] - voxels.DEFAULT_CAP > 0
    assert not any("voxel cap was lowered" in text for text in body["meta"]["notices"])
    assert 60_000 < density.wire_size(body) < 80_000
    assert body["voxels"]["dtype"]["xy"] == "u8"


def test_the_local_cloud_carries_the_negative_depth_summary_of_the_2d_local_frame(client):
    """The cloud draws voxels upstream of P0; the same C9 block as /api/projections says how many."""
    body = _get(client)
    assert min(body["grid"]["z_centres"]) < 0
    panels = client.get("/api/projections", params={"coord_system": "local"})
    assert panels.status_code == 200, panels.text
    assert body["frame"]["negative_w"] == panels.json()["frame"]["negative_w"]
    contract_check.check(body["frame"]["negative_w"], "statistics", at="negative_w")


def _served_bodies(client) -> dict[str, dict]:
    return {
        "density": _get(client),
        "gradcam_energy": _get(client, channel="gradcam_energy", model="angle"),
        "shapcam_energy": _get(client, frame="canonical", channel="shapcam_energy"),
    }


#: (channel, mutation) pairs the contract must refuse: what the frontend reads, per channel.
_MUTATIONS = {
    "shapcam_energy": [
        lambda b: b["scale"].pop("split_code"),
        lambda b: b["scale"].pop("diverging"),
        lambda b: b["scale"].update(split_code=128),
        lambda b: b["scale"].update(scale="log10"),
        lambda b: b["scale"].update(rho_ref=1.0),
        lambda b: b["rho"].pop("cam_ref"),
        lambda b: b["rho"].update(floor_basis="rho_ref"),
        lambda b: b["meta"].update(cam=None),
        lambda b: b["budget"].update(cam=None),
        lambda b: b["frame"].update(n_ill_conditioned=None),
    ],
    "gradcam_energy": [
        lambda b: b["scale"].pop("ref"),
        lambda b: b["scale"].update(scale="signed_log10"),
        lambda b: b["meta"].update(cam=None),
        lambda b: b["budget"].update(cam=None),
        lambda b: b["rho"].pop("cam_ref"),
        lambda b: b["frame"].pop("negative_w"),
    ],
    "density": [
        lambda b: b["scale"].update(scale="signed_log10"),
        lambda b: b["scale"].pop("rho_ref"),
        lambda b: b["scale"].update(split_code=129),
        lambda b: b["budget"].update(cam={"quantity": "gradcam_energy"}),
        lambda b: b["meta"].update(cam={"note": "x"}),
        lambda b: b["rho"].update(cam_ref=1.0),
        lambda b: b["rho"].update(unit="GeV/mm^2/event"),
        lambda b: b["budget"]["energy_fraction"].update(drawn=7.0),
        lambda b: b["budget"]["energy_fraction"].update(below_floor=-0.1),
        lambda b: b["grid"]["partial_edge"].update(energy_fraction=1.5),
        lambda b: b.update(topk=b["topk"] * 20),
        lambda b: b["frame"].update(hits=[]),
        lambda b: b["grid"].update(points=[]),
        lambda b: b["topk"][0].update(points=[]),
        lambda b: b["meta"]["cache"].update(hits=1),
        lambda b: b.update(points=[]),
    ],
}


def test_the_contract_refuses_what_the_frontend_could_not_read(client):
    """Each channel's branch requires its own keys; fractions, topk length and raw keys are bounded."""
    bodies = _served_bodies(client)
    for channel, body in bodies.items():
        assert not contract_check.errors(body, contract_check.load("voxels"))
        assert len(body["topk"]) == voxels.TOPK
        for i, mutate in enumerate(_MUTATIONS[channel]):
            broken = copy.deepcopy(body)
            mutate(broken)
            assert contract_check.errors(broken, contract_check.load("voxels")), (channel, i)
    # A body of one channel is not valid under another's name.
    for channel, body in bodies.items():
        for other in voxels.CHANNELS:
            if other != channel:
                relabelled = copy.deepcopy(body)
                relabelled["meta"]["channel"] = other
                assert contract_check.errors(relabelled, contract_check.load("voxels")), (channel, other)


def test_an_impossible_limit_is_served_with_a_stated_overrun(client, monkeypatch):
    """Below the size of the body without any voxel, dropping voxels cannot help: none are."""
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    contract_check.check(body, "voxels")
    warning = [w for w in body["meta"]["warnings"] if "served as it is" in w]
    assert warning and f"still {len(response.content):,} bytes" in warning[0]
    assert body["budget"]["n_drawn"] == body["budget"]["n_above_floor"]
    assert not any("voxel cap was lowered" in text for text in body["meta"]["notices"])


# ---------------------------------------------------- synthetic_client --


@pytest.mark.parametrize("frame", voxels.FRAMES)
@pytest.mark.parametrize("centre,count", SYNTHETIC_SLICES)
def test_low_n_slices_are_labelled_provisional(synthetic_client, frame, centre, count):
    body = _get(synthetic_client, frame=frame, d_min=centre - 25.0, d_max=centre + 24.99)
    assert body["frame"]["n_events"] == count
    assert body["frame"]["n_showers"] == 2 * count
    provisional = count < frame_mod.PROVISIONAL_N
    assert body["frame"]["provisional"] is provisional and body["rho"]["provisional"] is provisional
    label = body["frame"]["n_label"]
    if count == 1:
        assert label.startswith("N = 1:")
    elif provisional:
        assert label == (f"N = {count}: weak evidence; the cloud and its reference ρ_ref are "
                         "labelled provisional.")
    else:
        assert label is None
    assert (label in body["meta"]["notices"]) if label else True


#: The synthetic events enter 2064 or 2833 mm apart, never closer than 80 mm,
#: so the disclosure is also exercised with the threshold raised between the
#: two (it is read at request time): some slices then hold ill-conditioned
#: events and some do not.
RAISED_ILL_MM = 2500.0


@pytest.mark.parametrize("threshold", [frame_mod.ILL_CONDITIONED_D_MM, RAISED_ILL_MM])
@pytest.mark.parametrize("centre,count", SYNTHETIC_SLICES)
def test_the_d_frame_cloud_states_the_2d_frame_disclosures(synthetic_client, monkeypatch, centre,
                                                           count, threshold):
    """Ill-conditioned rotations and the anchor residual: whenever the 2-D D-frame says so, so does the cloud."""
    monkeypatch.setattr(frame_mod, "ILL_CONDITIONED_D_MM", threshold)
    selection = {"d_min": centre - 25.0, "d_max": centre + 24.99}
    cloud = _get(synthetic_client, frame="canonical", **selection)
    panels = synthetic_client.get("/api/projections", params={"frame": "canonical", **selection})
    assert panels.status_code == 200, panels.text
    panels = panels.json()
    n_ill = panels["frame"]["n_ill_conditioned"]
    assert cloud["frame"]["n_ill_conditioned"] == n_ill
    assert cloud["frame"]["ill_conditioned_threshold_mm"] == panels["frame"]["ill_conditioned_threshold_mm"]
    assert cloud["frame"]["anchor_residual"] == panels["frame"]["anchor_residual"]
    two_d = [notice["text"] for notice in panels["meta"]["notices"]]
    three_d = cloud["meta"]["notices"]
    said = [t for t in three_d if "enter closer than" in t]
    assert any("enter closer than" in t for t in two_d) == bool(n_ill) == bool(said)
    if n_ill:
        # The 2-D sentence without its axis-statistics clause: the cloud draws no axis.
        assert said == [typographic(frame_canonical.ill_conditioned_notice(n_ill, axis_statistics=False))]
        assert said[0].startswith(f"{n_ill:,} event(s) enter closer than {threshold:.0f} mm")
        assert "R̄′" not in said[0]
    assert [t for t in three_d if t.startswith("Anchor:")] == [
        typographic(t) for t in two_d if t.startswith("Anchor:")]
    if count >= 2:
        assert any(t.startswith("Anchor:") for t in three_d)


def test_the_raised_threshold_splits_the_synthetic_slices(synthetic_client, monkeypatch):
    """The parametrised disclosure test above is not vacuous: some slices have ill-conditioned events, some not."""
    monkeypatch.setattr(frame_mod, "ILL_CONDITIONED_D_MM", RAISED_ILL_MM)
    counts = []
    for centre, _ in SYNTHETIC_SLICES:
        body = _get(synthetic_client, frame="canonical", d_min=centre - 25.0, d_max=centre + 24.99)
        counts.append(body["frame"]["n_ill_conditioned"])
    assert any(counts) and not all(counts), counts


def test_an_empty_selection_draws_nothing_and_says_so(synthetic_client):
    body = _get(synthetic_client, d_min=450.0, d_max=500.0)
    assert body["frame"]["n_events"] == 0 and body["voxels"]["n"] == 0
    assert body["rho"]["rho_ref"] is None and body["topk"] == []
    assert body["budget"]["energy_total_gev"] == 0.0
    assert any("No events match" in w for w in body["meta"]["warnings"])
    # Every channel's branch of the contract holds for an empty cloud, references null.
    for frame in voxels.FRAMES:
        for channel in ("gradcam_energy", "shapcam_energy"):
            empty = _get(synthetic_client, frame=frame, channel=channel, d_min=450.0, d_max=500.0)
            assert empty["voxels"]["n"] == 0
            assert empty["rho"]["cam_ref"] is None and empty["scale"]["ref"] is None
            assert empty["rho"]["floor"] is None and empty["budget"]["cam"]["total"] == 0.0


def test_the_half_width_edge_voxels_hold_the_2d_edge_bins(synthetic_client):
    """On the synthetic Local grid y has an even number of bin pairs and x an odd one."""
    record = _record(synthetic_client, _table(synthetic_client))
    settings = synthetic_client.app.state.settings
    with synthetic_client.app.state.database.read_cursor() as con:
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)
        bundle, _, grid, k, _ = voxels.bundle_for(con, record, spec, settings, "local", footprint,
                                                  False, 100.0)
        flat, _, flat_grid, flat_k, _ = shower_frames.bundle_for(
            con, record, spec, settings, "local", footprint, False, 100.0)
    assert flat_grid.as_dict() == grid.as_dict() and flat_k == k
    assert bundle.y.partial and not bundle.x.partial
    edge = flat.yz.planes["e"][[0, -1], :].sum()
    rendered = voxels.render(bundle, "density", voxels.DEFAULT_CAP)
    assert rendered["budget"]["energy_gev"]["partial_edge"] == pytest.approx(edge, rel=1e-9)
    assert rendered["grid"]["partial_edge"]["y"] and not rendered["grid"]["partial_edge"]["x"]


def test_the_synthetic_d_frame_carries_every_channel(synthetic_client):
    for channel in voxels.CHANNELS:
        body = _get(synthetic_client, frame="canonical", channel=channel, model="angle")
        assert body["frame"]["n_events"] == 286 and not body["frame"]["provisional"]
        assert body["voxels"]["n"] > 0


# ------------------------------------------------------- single_client --


def test_single_shower_local_is_served_with_one_shower_per_event(single_client):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE)
    frame = body["frame"]
    assert frame["n_showers"] == frame["n_events"] > 0
    text = " ".join(body["meta"]["notices"])
    assert "A+B" not in text and "separation" not in text and "both showers" not in text
    assert body["meta"]["cam"] is None
    assert frame["coordinate_check"]["within_tolerance"]


@pytest.mark.parametrize("bin_,count", SINGLE_BINS)
def test_single_shower_low_n_bins_are_provisional(single_client, bin_, count):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE, e1_min=float(bin_),
                e1_max=bin_ + 0.9999)
    assert body["frame"]["n_events"] == count
    assert body["frame"]["provisional"] is (count < frame_mod.PROVISIONAL_N)


def test_single_shower_refusals(single_client):
    problem = _refused(single_client, "frame", "frame-canonical", table_name=SINGLE_HITS_TABLE,
                       frame="canonical")
    assert "two showers" in problem["reason"]
    # trans: a validation error whose advice names only the frame this kind offers.
    trans = _refused(single_client, "frame", table_name=SINGLE_HITS_TABLE, frame="trans")
    assert trans["type"] == "/problems/validation-error" and "capability" not in trans
    assert trans["detail"].endswith("Use frame=local.") and "canonical" not in trans["detail"]
    lab = _refused(single_client, "frame", table_name=SINGLE_HITS_TABLE, frame="lab")
    assert "one of local;" in lab["detail"] and "canonical" not in lab["detail"]
    _refused(single_client, "channel", "vox-attention", table_name=SINGLE_HITS_TABLE,
             channel="gradcam_energy")
    _refused(single_client, "channel", "vox-attention", table_name=SINGLE_HITS_TABLE,
             channel="shapcam_energy")
    _refused(single_client, "table_name", "vox-ensemble", table_name=SINGLE_EVENTS_TABLE)
    _refused(single_client, "e2_min", table_name=SINGLE_HITS_TABLE, e2_min=1.0)


# ---------------------------------------------------------- query level --


@pytest.fixture(scope="module")
def built(ingested):
    """The demonstration's voxel and 2-D bundles of both frames, for the full selection."""
    database, settings = ingested["database"], ingested["settings"]
    with database.read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)
        out = {"record": record, "spec": spec, "footprint": footprint, "settings": settings}
        for kind in voxels.FRAMES:
            out[kind] = voxels.bundle_for(con, record, spec, settings, kind, footprint, False, 100.0)
        out["flat", "local"] = shower_frames.bundle_for(con, record, spec, settings, "local",
                                                        footprint, False, 100.0)
        out["flat", "canonical"] = canonical_cache.bundle_for(con, record, spec, settings, footprint,
                                                              False, 100.0)
    return out


def _dense(bundle: voxels.VoxelBundle, values: np.ndarray) -> np.ndarray:
    out = np.zeros((bundle.x.n, bundle.y.n, bundle.grid.n_z))
    out[bundle.vx, bundle.vy, bundle.vz] = values
    return out


def test_the_2d_queries_still_run_the_shared_base_with_every_plane(built):
    """The factoring left the 2-D text as base + aggregates; the voxel base reads no unused column."""
    record, spec, footprint = built["record"], built["spec"].clamped(built["record"]), built["footprint"]
    bundle, _, grid, k, _ = built["local"]
    pitch = record.frame_bounds.layer_pitch_mm
    base = shower_frames._local_base_sql(record, spec, grid, footprint, pitch, k, 2, "energy", False)
    for sql in shower_frames._local_sql(record, spec, grid, footprint, pitch, k, 2, "energy", False):
        assert sql.startswith(base)
    _, _, cgrid, ck, _ = built["canonical"]
    cbase = canonical._canonical_base_sql(record, spec, cgrid, ck, False, "energy")
    for sql in canonical.build_sql(record, spec, cgrid, ck, False, "energy"):
        assert sql.startswith(cbase)
    for kind, g, kk in (("local", grid, k), ("canonical", cgrid, ck)):
        sql = voxels.build_sql(record, spec, kind, g, footprint, kk, 2 if kind == "local" else 1,
                               "energy")
        coord = "local" if kind == "local" else "lab"
        assert ddl.cam_column("energy", coord, "gradcam") in sql
        assert ddl.cam_column("energy", coord, "shapcam") in sql
        for unread in (ddl.seg_column("true", coord), ddl.seg_column("pred", coord), " AS v_g,",
                       " AS v_s,", "v_efa"):
            assert unread not in sql, (kind, unread)


@pytest.mark.parametrize("kind,source", [("local", "file"), ("local", "computed"),
                                         ("canonical", "file")])
def test_the_voxel_query_scans_the_projection_table_once(cursor, built, kind, source):
    bundle, _, grid, k, _ = built[kind]
    record = built["record"]
    plan = voxels.explain(cursor, record, built["spec"].clamped(record), kind, grid,
                          built["footprint"], k, bundle.k_z, source=source)
    assert plan.count(naming.proj_table(record.table_name)) == 1
    assert plan.count(naming.event_table(record.table_name)) >= 1


def test_local_voxels_equal_the_rotated_sub_deposits_in_numpy(cursor, built):
    """Sums, raw fine peaks and ρ_ref against an independent NumPy splat of every hit."""
    record = built["record"]
    bundle, stats, grid, k, _ = built["local"]
    wx, wy = built["footprint"]
    wz = record.frame_bounds.layer_pitch_mm
    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"""SELECT p.xl, p.yl, p.zl, p.energy,
                   CAST(CASE WHEN p.org = 0 THEN e.theta_a ELSE e.theta_b END AS DOUBLE) AS t,
                   CAST(CASE WHEN p.org = 0 THEN e.phi_a ELSE e.phi_b END AS DOUBLE) AS f
            FROM {proj} p JOIN {event} e USING (event_number) WHERE e.d IS NOT NULL"""
    ).fetchnumpy()
    xl, yl, zl = (np.asarray(rows[c], dtype=np.float64) for c in ("xl", "yl", "zl"))
    t, f = np.asarray(rows["t"]), np.asarray(rows["f"])
    e = np.asarray(rows["energy"], dtype=np.float64)
    k_z = bundle.k_z
    offsets = [((a + 0.5) / k - 0.5, (b + 0.5) / k - 0.5, (c + 0.5) / k_z - 0.5)
               for a in range(k) for b in range(k) for c in range(k_z)]
    ct, st, cf, sf = np.cos(t), np.sin(t), np.cos(f), np.sin(f)
    z0 = grid.axis("z").edges[0]
    fine = np.zeros((grid.n_x, grid.n_y, grid.n_z))
    outside = 0.0
    for fx, fy, fz in offsets:
        ox, oy, oz = fx * wx, fy * wy, fz * wz
        xs = xl + ct * cf * ox + ct * sf * oy - st * oz
        ys = yl - sf * ox + cf * oy
        zs = zl + st * cf * ox + st * sf * oy + ct * oz
        jx = np.floor((xs + grid.half_x) / grid.pitch).astype(int)
        jy = np.floor((ys + grid.half_y) / grid.pitch).astype(int)
        jz = np.floor((zs - z0) / wz).astype(int)
        ok = (jx >= 0) & (jx < grid.n_x) & (jy >= 0) & (jy < grid.n_y) & (jz >= 0) & (jz < grid.n_z)
        np.add.at(fine, (jx[ok], jy[ok], jz[ok]), e[ok] / len(offsets))
        outside += float(e[~ok].sum()) / len(offsets)
    scale = e.sum()

    jx, jy, jz = np.nonzero(fine)
    vx, vy = bundle.x.of_fine(jx), bundle.y.of_fine(jy)
    sums = np.zeros((bundle.x.n, bundle.y.n, grid.n_z))
    peaks = np.zeros_like(sums)
    np.add.at(sums, (vx, vy, jz), fine[jx, jy, jz])
    np.maximum.at(peaks, (vx, vy, jz), fine[jx, jy, jz])
    np.testing.assert_allclose(_dense(bundle, bundle.sums["e"]), sums, rtol=0, atol=1e-12 * scale)
    np.testing.assert_allclose(_dense(bundle, bundle.peaks["e"]), peaks, rtol=0, atol=1e-12 * scale)
    assert bundle.outside["e"] == pytest.approx(outside, rel=1e-9, abs=1e-12 * scale)

    classified = voxels.classify(bundle, "density")
    rho_ref = fine.max() / (stats.n_events * grid.pitch ** 2 * wz)
    assert classified.rho_ref == pytest.approx(rho_ref, rel=1e-12)
    assert (classified.value <= classified.rho_ref * (1 + 1e-12)).all()


def test_the_d_frame_rho_ref_is_the_max_of_an_independent_fine_query(cursor, built):
    record = built["record"]
    spec = built["spec"].clamped(record)
    bundle, stats, grid, k, _ = built["canonical"]
    base = canonical._canonical_base_sql(record, spec, grid, k, planes=("e",))
    fine = cursor.execute(
        base + " SELECT jx, jy, iz, sum(v_e) AS e FROM keyed WHERE jx >= 0 GROUP BY ALL",
        canonical._params(record, spec, built["footprint"]),
    ).fetchnumpy()
    dz = record.frame_bounds.layer_pitch_mm
    rho_ref = float(np.max(fine["e"])) / (stats.n_events * grid.pitch ** 2 * dz)
    classified = voxels.classify(bundle, "density")
    assert classified.rho_ref == pytest.approx(rho_ref, rel=1e-12)
    assert (classified.value <= classified.rho_ref * (1 + 1e-12)).all()
    merged = np.zeros((bundle.x.n, bundle.y.n, grid.n_z))
    np.add.at(merged, (bundle.x.of_fine(np.asarray(fine["jx"])), bundle.y.of_fine(np.asarray(fine["jy"])),
                       np.asarray(fine["iz"])), np.asarray(fine["e"]))
    np.testing.assert_allclose(_dense(bundle, bundle.sums["e"]), merged, rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("kind", voxels.FRAMES)
@pytest.mark.parametrize("channel", voxels.CHANNELS)
@pytest.mark.parametrize("cap", [voxels.DEFAULT_CAP, 50])
def test_every_joule_lands_in_exactly_one_category(built, kind, channel, cap):
    """Drawn + below floor + beyond cap + partial edge + outside = the 2-D bundle's total."""
    bundle = built[kind][0]
    flat = built["flat", kind][0]
    rendered = voxels.render(bundle, channel, cap)
    budget = rendered["budget"]
    expected = flat.total_energy + flat.energy_outside
    assert sum(budget["energy_gev"].values()) == pytest.approx(expected, rel=1e-9)
    assert budget["energy_total_gev"] == pytest.approx(expected, rel=1e-9)
    assert budget["energy_gev"]["outside_grid"] == pytest.approx(flat.energy_outside, rel=1e-9,
                                                                 abs=1e-15)
    assert budget["n_drawn"] == min(cap, budget["n_above_floor"])
    if cap == 50:
        assert budget["n_beyond_cap"] > 0 and budget["energy_gev"]["beyond_cap"] > 0
    if channel != "density":
        view_parts = ("eg",) if channel == "gradcam_energy" else ("esp", "esn")
        cam_total = sum(float(flat.xz.planes[p].sum()) + flat.plane_outside[p] for p in view_parts)
        cam = budget["cam"]
        assert cam["total"] == pytest.approx(cam_total, rel=1e-9)
        parts = [cam[key] for key in ("drawn", "below_floor", "beyond_cap", "outside_grid",
                                      "partial_edge")]
        assert sum(parts) == pytest.approx(cam_total, rel=1e-9, abs=1e-15)


@pytest.mark.parametrize("kind", voxels.FRAMES)
@pytest.mark.parametrize("channel", voxels.CHANNELS)
def test_no_voxel_below_the_floor_is_shipped_and_the_cap_keeps_the_brightest(built, kind, channel):
    bundle = built[kind][0]
    classified = voxels.classify(bundle, channel)
    rendered = voxels.render(bundle, channel, 40, classified)
    floor = voxels.FLOOR_RATIO
    drawn = classified.order[:40]
    magnitude = np.abs(classified.ratio) if channel == "shapcam_energy" else classified.ratio
    assert (magnitude[drawn] >= floor).all()
    assert (magnitude[classified.below] < floor).all()
    assert classified.full[drawn].all()
    # The cap is a prefix by energy: nothing beyond it is brighter than anything kept.
    e = bundle.sums["e"]
    if classified.order.size > 40:
        assert e[classified.order[40:]].max() <= e[drawn].min()
    # Codes decode back above the floor.
    codes = np.frombuffer(base64.b64decode(rendered["voxels"]["code"]), dtype="u1")
    assert codes.min() >= voxels.MIN_DRAWN_CODE
    if channel == "shapcam_energy":
        back = quantize.dequantize_signed_log(codes, frame_mod.RAMP_DECADES)
        assert (np.abs(back) >= floor * (1 - 1e-9)).all()
    else:
        scale = scale_mod.ColorScale(**{
            k: rendered["scale"][k] for k in ("scale", "vmin", "vmax", "unit", "mode", "locked")})
        back = quantize.dequantize(codes, scale, min_code=voxels.MIN_DRAWN_CODE)
        assert (back >= floor * (1 - 1e-9)).all()
    # The rendered scale counts the same floor as the classification.
    assert rendered["scale"]["clipped_low"] == classified.n_below


@pytest.mark.parametrize("kind", voxels.FRAMES)
def test_the_layer_runs_round_trip_to_the_kept_voxels(built, kind):
    bundle = built[kind][0]
    classified = voxels.classify(bundle, "density")
    rendered = voxels.render(bundle, "density", 300, classified)
    kept = classified.order[:300]
    ox, oy, oz, codes = encode_voxels.unpack_layer_runs(rendered["voxels"], bundle.grid.n_z)
    expected = sorted(zip(bundle.vz[kept].tolist(), (bundle.vy[kept] - bundle.y.first_full).tolist(),
                          (bundle.vx[kept] - bundle.x.first_full).tolist()))
    assert list(zip(oz.tolist(), oy.tolist(), ox.tolist())) == expected
    grid = rendered["grid"]
    x = grid["x_centre0"] + grid["voxel_mm"][0] * ox
    assert set(np.round(x, 6)) <= set(np.round(bundle.x.centre(np.arange(bundle.x.n)), 6))
    assert (ox >= 0).all() and (ox < grid["n"][0]).all() and (oy < grid["n"][1]).all()
    # topk points at shipped voxels and carries their exact values.
    for entry in rendered["topk"]:
        i = entry["i"]
        assert entry["x"] == pytest.approx(grid["x_centre0"] + grid["voxel_mm"][0] * ox[i])
        assert entry["z"] == pytest.approx(grid["z_centres"][oz[i]])
    values = [entry["value"] for entry in rendered["topk"]]
    assert values == sorted(values, reverse=True)


def test_wide_axes_declare_u16_ordinals():
    vx = np.array([0, 300, 5]); vy = np.array([1, 2, 3]); vz = np.array([0, 0, 1])
    block, order = encode_voxels.pack_layer_runs(vx, vy, vz, 2, 301, 4)
    assert block["dtype"]["xy"] == "u16le"
    block["code"] = base64.b64encode(bytes([2, 3, 4])).decode()
    ox, oy, oz, _ = encode_voxels.unpack_layer_runs(block, 2)
    assert list(zip(ox, oy, oz)) == [(0, 1, 0), (300, 2, 0), (5, 3, 1)]


@pytest.mark.parametrize("b", range(2, 12))
def test_the_merge_centres_a_voxel_on_the_origin_for_both_parities(b):
    pitch = frame_mod.CANONICAL_PITCH_MM
    axis = voxels.merged_axis(b * pitch, pitch)
    assert axis.n_fine == 2 * b and axis.partial == (b % 2 == 0)
    # A point either side of the origin lands in the voxel centred on it.
    for x in (-19.9, -0.1, 0.0, 0.1, 19.9):
        j = int(np.floor((x + axis.half) / pitch))
        assert axis.centre(axis.of_fine(j)) == pytest.approx(0.0)
    # Every fine bin is covered once; full voxels hold two bins, half-width ones one.
    j = np.arange(axis.n_fine)
    v = axis.of_fine(j)
    counts = np.bincount(v, minlength=axis.n)
    assert (counts[axis.is_partial(np.arange(axis.n))] == 1).all()
    assert (counts[~axis.is_partial(np.arange(axis.n))] == 2).all()
    assert axis.n_full == int((~axis.is_partial(np.arange(axis.n))).sum())
    # Each full voxel's centre is the midpoint of its two bins.
    centres = -axis.half + pitch * (j + 0.5)
    for voxel in np.flatnonzero(~axis.is_partial(np.arange(axis.n))):
        assert axis.centre(voxel) == pytest.approx(centres[v == voxel].mean())
    # The SQL arithmetic is the same integer division.
    con = duckdb.connect()
    sql = (f"SELECT range AS j, CASE WHEN range < 0 THEN -1 ELSE (range + {axis.offset}) // "
           f"{voxels.MERGE} END AS v FROM range({axis.n_fine})")
    rows = con.execute(sql).fetchnumpy()
    assert (np.asarray(rows["v"]) == axis.of_fine(np.asarray(rows["j"]))).all()


def test_the_cache_reuses_a_bundle_and_invalidation_drops_it(cursor, built):
    record, spec, settings, footprint = (built[k] for k in ("record", "spec", "settings", "footprint"))
    cache_mod.invalidate_all(record.table_name)
    _, _, _, _, cached = voxels.bundle_for(cursor, record, spec, settings, "local", footprint,
                                           False, 100.0, "angle")
    assert not cached
    _, _, _, _, cached = voxels.bundle_for(cursor, record, spec, settings, "local", footprint,
                                           False, 100.0, "angle")
    assert cached
    # Density takes any network's bundle; an attention channel only its own.
    _, _, _, _, cached = voxels.bundle_for(cursor, record, spec, settings, "local", footprint,
                                           False, 100.0, "energy", any_model=True)
    assert cached
    assert cache_mod.invalidate_all(record.table_name) >= 1
    assert voxels.cache_for(settings).invalidate_table(record.table_name) == 0
    _, _, _, _, cached = voxels.bundle_for(cursor, record, spec, settings, "local", footprint,
                                           False, 100.0, "angle")
    assert not cached


def test_cold_voxel_scans_share_one_flight_and_never_overlap_a_heavy_scan(ingested, built,
                                                                          monkeypatch):
    """Two identical cold requests scan once; no voxel scan runs beside another heavy hit scan."""
    record, spec, settings, footprint = (built[k] for k in ("record", "spec", "settings", "footprint"))
    database = ingested["database"]
    lock = threading.Lock()
    state = {"running": 0, "most": 0, "scans": []}

    def enter(name: str) -> None:
        with lock:
            state["running"] += 1
            state["most"] = max(state["most"], state["running"])
            state["scans"].append(name)

    def leave() -> None:
        with lock:
            state["running"] -= 1

    real_fetch = voxels.fetch

    def slow_fetch(*args, **kwargs):
        enter(args[3])
        try:
            time.sleep(0.15)
            return real_fetch(*args, **kwargs)
        finally:
            leave()

    def physics_scan() -> int:
        enter("physics")
        try:
            time.sleep(0.15)
            return 1
        finally:
            leave()

    monkeypatch.setattr(voxels, "fetch", slow_fetch)
    cache_mod.invalidate_all(record.table_name)
    results: dict[str, tuple] = {}
    errors: list[BaseException] = []

    def request(name: str, kind: str) -> None:
        try:
            with database.read_cursor() as con:
                bundle, _, _, _, cached = voxels.bundle_for(con, record, spec, settings, kind,
                                                            footprint, False, 100.0, "angle")
            results[name] = (bundle, cached)
        except BaseException as error:  # pragma: no cover - reported below
            errors.append(error)

    def physics() -> None:
        physics_cache.get_or_compute((record.table_name, "voxel-gate-probe"), physics_scan)

    threads = [threading.Thread(target=request, args=("local-1", "local")),
               threading.Thread(target=request, args=("local-2", "local")),
               threading.Thread(target=request, args=("canonical", "canonical")),
               threading.Thread(target=physics)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    assert state["most"] == 1, state
    assert sorted(state["scans"]) == ["canonical", "local", "physics"]
    (first, first_cached), (second, second_cached) = results["local-1"], results["local-2"]
    assert first is second and sorted([first_cached, second_cached]) == [False, True]
    # The bundle lives in the voxel cache; the physics cache holds none of it.
    key = voxels.cache_key(spec.clamped(record), False, "local", first.grid, first.subsample_k,
                           first.k_z, first.footprint, "angle", first.anchor,
                           first.coordinate_source)
    assert voxels.cache_for(settings).get_any([key]) is first
    assert physics_cache.get_cache().get_any([key]) is None
    cache_mod.invalidate_all(record.table_name)


def test_the_preview_reads_the_sample_at_k_two_and_scales_it(cursor, built, monkeypatch):
    record, spec, settings, footprint = (built[k] for k in ("record", "spec", "settings", "footprint"))
    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    decision = sampling.decide(record, True, 10.0)
    assert decision.sampled and record.has_sample
    bundle, stats, grid, k, _ = voxels.bundle_for(cursor, record, spec, settings, "local", footprint,
                                                  True, decision.percent)
    assert k == frame_mod.PREVIEW_MAX_SUBSAMPLE and not bundle.exact
    raw = voxels.fetch(cursor, record, spec.clamped(record), "local", stats.n_events, grid,
                       footprint, k, bundle.k_z, sampled=True)
    assert bundle.sums["e"].sum() == pytest.approx(raw.sums["e"].sum() * 100.0 / decision.percent,
                                                   rel=1e-12)
    assert bundle.peaks["e"].max() == pytest.approx(raw.peaks["e"].max() * 100.0 / decision.percent,
                                                    rel=1e-12)


def test_a_rotated_footprint_is_never_point_binned(cursor, built):
    record = built["record"]
    _, stats, grid, _, _ = built["local"]
    with pytest.raises(ValueError, match="never point-binned"):
        voxels.fetch(cursor, record, built["spec"].clamped(record), "local", stats.n_events, grid,
                     built["footprint"], 1, 2)
