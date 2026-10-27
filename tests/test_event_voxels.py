"""``GET /api/event?format=voxels``: one event as cubes, C5 and C6 (Page 2).

The cubes are checked against the database they were built from: every cell
drawn once at its lattice ordinal (the laboratory frame) or its lattice
coordinate minus P₀ (translated), the splat frames conserving the energy
they were given, the shower code against the ingest's split-cell census, the
cap and the window counting what they leave out, the exact top values, the
species legend and the primary flag. The refusals name their field and
capability; every served body is validated against
``tests/contracts/event_voxels.json``, measured against the 100 KB contract,
searched for raw hit keys and for hyphen-signed numbers.

Every booted test uses ``single_client``, which holds the two-shower
demonstration file (the baseline), the synthetic single-shower hits with
species, and their 59-column aggregate; the pure helpers are tested on
arrays built here. The pick rules' tests on the demonstration file live
with the Event Inspector's (``test_event_inspector.py``).
"""

from __future__ import annotations

import base64
import dataclasses
import json

import duckdb
import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import ddl, naming, registry
from calosrv.db.naming import quote
from calosrv.encode import voxels as encode_voxels
from calosrv.grid import frame as frame_mod
from calosrv.errors import CapabilityError
from calosrv.query import canonical, capabilities, density, filters, voxel_event
from calosrv.text import signed_hyphens, typographic

ROUTE = "/api/event"
BASE = {"table_name": BASELINE_TABLE}
HITS = {"table_name": SINGLE_HITS_TABLE}
EVENTS = {"table_name": SINGLE_EVENTS_TABLE}
VOX = {"format": "voxels"}


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


#: The scale quantity each channel is drawn on.
_QUANTITY = {"energy": "energy_density", "gradcam": "gradcam", "shapcam": "shapcam", "segerr": "segerr",
             "species": "species"}


def _check_body(body: dict) -> None:
    """What every voxel body must satisfy, served or built."""
    contract_check.check(body, "event_voxels")
    # No raw hit array under any name, at any depth (the contract repeats the guard per object).
    raw = [path for path, key in _keys(body) if key in ("hits", "points")]
    assert not raw, raw
    for path, sentence in _strings(body):
        if path.endswith((".ix", ".iy", ".iz", ".code", ".flags", ".table_name", ".parent",
                          ".n_daughters", ".daughter_mode", ".purity")):
            continue
        assert not signed_hyphens(sentence), (path, signed_hyphens(sentence))
    vox = body["voxels"]
    scale = vox["scale"]
    assert scale["quantity"] == _QUANTITY[vox["channel"]]
    assert all(item["i"] < vox["cubes"]["n"] for item in vox["topk"])
    # The geometry sentence is shipped once, at geometry.note.
    note = vox["geometry"]["note"]
    assert sum(1 for _, text in _strings(body) if text == note) == 1
    if vox["channel"] == "energy" and vox["cubes"]["n"]:
        # The ramp's top is the brightest drawn cube, never above every drawn value; a
        # single-valued frame is a zero-width ramp, stated, never a padded decade.
        brightest = max(item["value"] for item in vox["topk"])
        assert scale["top_density"] == pytest.approx(brightest, rel=1e-12)
        assert scale["vmax"] == pytest.approx(np.log10(brightest), abs=1e-12)
        assert scale["vmin"] <= scale["vmax"]
        assert scale["degenerate"] == (scale["vmin"] == scale["vmax"])
        assert scale["floor_basis"] == ("cells" if vox["regime"] == "cells" else "voxels")


def _served(client, **params) -> dict:
    """A voxel body, checked against everything every response must satisfy."""
    response = client.get(ROUTE, params={**VOX, **params})
    assert response.status_code == 200, response.text[:800]
    assert len(response.content) < density.RESPONSE_LIMIT
    body = response.json()
    _check_body(body)
    return body


def _refused(client, field: str, capability: str | None = None, **params) -> dict:
    response = client.get(ROUTE, params={**VOX, **params})
    assert response.status_code == 422, response.text[:600]
    problem = response.json()
    assert problem["field"] == field, problem
    if capability is not None:
        contract_check.check(problem, "capability_problem")
        assert problem["capability"] == capability, problem
    return problem


def _con(single_client):
    return single_client.app.state.database.read_cursor()


def _record(con, table: str):
    return registry.require_ready(con, table)


def _rows(con, table: str, event: int, where: str = "TRUE", extra: str = "") -> dict[str, np.ndarray]:
    proj = quote(naming.proj_table(table))
    data = con.execute(
        f"SELECT ix, iy, iz, org, energy{extra} FROM {proj} p WHERE event_number = ? AND {where}",
        [event]).fetchnumpy()
    return {k: np.asarray(np.ma.filled(np.ma.asarray(v), 0) if v.dtype != object else v)
            for k, v in data.items()}


def _events(con, table: str) -> list[int]:
    event = quote(naming.event_table(table))
    return [int(r[0]) for r in con.execute(f"SELECT event_number FROM {event} ORDER BY event_number").fetchall()]


# -------------------------------------------------------------- placement --
#
# Where a cube is drawn is decoded only from what the payload states (the
# frontend's placement rules) and compared with what the database says the
# shower is. Energies come from the builder, keyed by the shipped ordinals,
# because the wire carries colour codes and the exact values of only the
# brightest 64.
#
# Demonstration event 1 is the head of a longer event: the dummy CSV is the
# file's first 1,000 rows, of which event 0 holds 921 and event 1 only 79, so
# event 1's per-event centroid columns describe hits the file does not hold
# (its rows' centroid sits 300 mm from caz). Comparisons with the event table
# run on the events whose rows reproduce its laboratory centroid (_complete).


def _build(con, table: str, event: int, frame: str, shower: str, channel: str = "energy",
           cap: int = voxel_event.MAX_CAP):
    """A builder and the voxel block it renders at its own first pitch: every cube drawn."""
    record = _record(con, table)
    builder = voxel_event.build(con, record, filters.build(record), event, frame, shower, channel,
                                footprint=canonical.cell_footprint(con, record))
    return builder, builder.assemble(cap, builder.first_pitch)


def _placed(builder, body: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(centre (n, 3) mm, energy (n,) GeV, shower code (n,))`` of each shipped cube, in payload order.

    Centres follow the payload's stated rules: ``axes.<a>.coords[index] −
    origin_mm`` for cells; ``grid.x0 + (index + 0.5) × pitch`` across the beam
    for voxels, and along depth ``grid.z0 + (index + 0.5) × pitch_z`` or
    ``axes.z.coords[index]`` as ``grid.z_axis`` says.
    """
    vox = body["voxels"]
    geometry = vox["geometry"]
    cubes = _cubes(body)
    index = np.column_stack([cubes["ix"], cubes["iy"], cubes["iz"]])
    if vox["regime"] == "cells":
        centre = np.column_stack([
            np.asarray(geometry["axes"][axis]["coords"])[index[:, i]] - geometry["origin_mm"][i]
            for i, axis in enumerate("xyz")])
    else:
        grid = geometry["grid"]
        depth = (np.asarray(geometry["axes"]["z"]["coords"])[index[:, 2]]
                 if grid["z_axis"] == "native_layers"
                 else grid["z0"] + (index[:, 2] + 0.5) * grid["pitch_z_mm"])
        centre = np.column_stack([grid["x0"] + (index[:, 0] + 0.5) * grid["pitch_mm"],
                                  grid["y0"] + (index[:, 1] + 0.5) * grid["pitch_mm"], depth])
    built = builder.cubes(geometry["grid"]["pitch_mm"] if geometry["grid"] else None)
    energy_of = dict(zip(zip(built.ix.tolist(), built.iy.tolist(), built.iz.tolist()), built.energy.tolist()))
    energy = np.array([energy_of[tuple(key)] for key in index.tolist()])
    return centre, energy, cubes["flags"] & 3


def _table_centroid(con, table: str, event: int, shower: str, frame: str = "abs") -> np.ndarray:
    """The event table's energy-weighted 3-D centroid of one shower (raw z in the laboratory)."""
    names = [ddl.centroid_column(shower, axis, frame) for axis in "xyz"]
    row = con.execute(f"SELECT {', '.join(names)} FROM {quote(naming.event_table(table))} "
                      "WHERE event_number = ?", [event]).fetchone()
    return np.asarray(row, dtype=np.float64)


def _shower_where(shower: str) -> str:
    return {"a": "org = 0", "b": "org IN (1, 2)", "both": "TRUE"}[shower]


def _complete(con, table: str, event: int, showers: tuple[str, ...]) -> bool:
    """Whether the event's rows reproduce the event table's laboratory centroids (0.5 mm)."""
    lat = _record(con, table).lattice
    for shower in showers:
        rows = _rows(con, table, event, _shower_where(shower))
        lab = np.column_stack([lat.x.coords[rows["ix"]], lat.y.coords[rows["iy"]], lat.z.coords[rows["iz"]]])
        own = np.average(lab, axis=0, weights=rows["energy"].astype(np.float64))
        if not np.allclose(own, _table_centroid(con, table, event, shower), atol=0.5):
            return False
    return True


def _rotation(theta: float, phi: float) -> np.ndarray:
    """R(θ, φ) of the reference notebook, written out: the incident direction onto +w."""
    st, ct, sp, cp = np.sin(theta), np.cos(theta), np.sin(phi), np.cos(phi)
    return np.array([[ct * cp, ct * sp, -st], [-sp, cp, 0.0], [st * cp, st * sp, ct]])


def _reference_splat(centres, energy, rotation, footprint, k, k_z, edges, layer=None) -> np.ndarray:
    """The stated splat, written independently: each cell's box cut into k × k × k_z equal parts.

    The parts sit on a regular grid over the footprint, are turned by the
    frame's rotation about the cell centre, and are summed into the payload's
    grid by floor. ``layer`` replaces depth by the native layer ordinal (the
    D-frame).
    """
    axes = [((np.arange(n) + 0.5) / n - 0.5) * w for n, w in zip((k, k, k_z), footprint)]
    offsets = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3) @ np.asarray(rotation).T
    m = offsets.shape[0]
    out = np.zeros(tuple(e.size - 1 for e in edges))
    for start in range(0, centres.shape[0], 256):
        points = (centres[start:start + 256, None, :] + offsets[None]).reshape(-1, 3)
        weights = np.repeat(energy[start:start + 256] / m, m)
        if layer is not None:
            points[:, 2] = np.repeat(layer[start:start + 256].astype(np.float64), m)
        index, inside = [], np.ones(points.shape[0], dtype=bool)
        for axis, e in enumerate(edges):
            j = np.floor((points[:, axis] - e[0]) / (e[1] - e[0])).astype(np.int64)
            inside &= (j >= 0) & (j < e.size - 1)
            index.append(j)
        np.add.at(out, tuple(j[inside] for j in index), weights[inside])
    return out


# ------------------------------------------------------------ pure helpers --


def test_merge_cells_sums_energy_and_codes_split_cells():
    # Cells: (0,0,0) A only; (1,0,0) split A + B; (2,0,0) one 'A+B' row; (3,0,0) B + 'A+B'.
    ix = [0, 1, 1, 2, 3, 3]
    org = [0, 0, 1, 2, 1, 2]
    energy = [1.0, 2.0, 6.0, 0.5, 1.0, 3.0]
    value = [0.2, 0.4, 0.4, 0.9, 0.1, np.nan]
    cells = voxel_event.merge_cells(ix, [0] * 6, [0] * 6, org, energy, value=value)
    assert cells.n == 4
    np.testing.assert_allclose(cells.energy, [1.0, 8.0, 0.5, 4.0])
    assert cells.shower.tolist() == [voxel_event.SHOWER_A, voxel_event.SHOWER_MIXED,
                                     voxel_event.SHOWER_AB, voxel_event.SHOWER_MIXED]
    # A per-voxel value repeated on every row is its own energy-weighted mean; NaN rows are skipped.
    np.testing.assert_allclose(cells.value, [0.2, 0.4, 0.9, 0.1])
    assert cells.inverse.tolist() == [0, 1, 1, 2, 3, 3]


def test_merge_cells_takes_the_dominant_species_and_any_primary_tag():
    ix = [0, 0, 0, 1]
    species = [2, 0, 0, 5]          # gamma 3 GeV against e- 1 + 1.5 GeV in cell 0
    energy = [3.0, 1.0, 1.5, 2.0]
    primary = [False, True, False, False]
    cells = voxel_event.merge_cells(ix, [0] * 4, [0] * 4, [0] * 4, energy, primary=primary, species=species)
    assert cells.species.tolist() == [2, 5]
    np.testing.assert_allclose(cells.purity, [3.0 / 5.5, 1.0])
    assert cells.primary.tolist() == [True, False]
    # The lead row is the most energetic row of the dominant species.
    assert cells.lead_row.tolist() == [0, 3]
    assert voxel_event.merge_cells([], [], [], [], []).n == 0


def test_species_codes_are_stable_and_everything_else_is_other():
    assert [voxel_event.species_code(n) for n in voxel_event.SPECIES_ORDER] == list(range(7))
    for name in ("PDG_1000080160", "kaon+", "mu-", None, ""):
        assert voxel_event.species_code(name) == voxel_event.OTHER_CODE == 7
    assert voxel_event.SPECIES_NAMES[7] == "other"


def test_daughters_are_counted_and_their_mode_breaks_ties_alphabetically():
    assert voxel_event.daughter_tokens(None) == [] and voxel_event.daughter_tokens("") == []
    assert voxel_event.daughter_tokens("gamma;e-") == ["gamma", "e-"]
    assert voxel_event.daughter_tokens("e-;;gamma;") == ["e-", "gamma"]
    assert voxel_event.daughter_mode(["gamma", "e-"]) == "e-"
    assert voxel_event.daughter_mode(["gamma", "gamma", "e-"]) == "gamma"
    assert voxel_event.daughter_mode([]) is None


def test_packing_declares_its_width():
    text, dtype = encode_voxels.pack_ordinals(np.array([0, 7, 255]))
    assert dtype == "u8" and _decode(text, dtype).tolist() == [0, 7, 255]
    text, dtype = encode_voxels.pack_ordinals(np.array([0, 256, 1000]))
    assert dtype == "u16le" and _decode(text, dtype).tolist() == [0, 256, 1000]
    with pytest.raises(ValueError):
        encode_voxels.pack_ordinals(np.array([-1]))


def test_the_columns_read_exist_in_each_kinds_projection_table():
    """Every column name the voxel rows read is in its kind's DDL (the vocabulary rule)."""
    for kind, columns in ((ddl.KIND_TWO_SHOWER, ddl.PROJ_COLUMNS),
                          (ddl.KIND_SINGLE_HITS, ddl.PROJ_SINGLE_COLUMNS)):
        con = duckdb.connect()
        con.execute("CREATE TABLE p (" + ", ".join(f"{n} {t}" for n, t, _ in columns) + ")")
        con.execute("SELECT ix, iy, iz, org, energy, xt, yt, kt, xl, yl, zl FROM p LIMIT 0")
        if kind == ddl.KIND_SINGLE_HITS:
            con.execute(f"SELECT {', '.join(voxel_event.SPECIES_COLUMNS)} FROM p LIMIT 0")
        else:
            for channel in voxel_event.NETWORK_CHANNELS:
                for model in ddl.MODELS:
                    for coord in ddl.COORD_SYSTEMS:
                        for expr in voxel_event._channel_sql(channel, model, coord):
                            con.execute(f"SELECT {expr} FROM p LIMIT 0")


# ------------------------------------------------------- two showers: cells --


def test_format_raster_is_the_default_and_unchanged(single_client):
    params = {**BASE, "event_number": 0, "shower": "a"}
    default = single_client.get(ROUTE, params=params).json()
    raster = single_client.get(ROUTE, params={**params, "format": "raster"}).json()
    for body in (default, raster):
        for key in ("query_ms", "total_ms"):
            body["meta"].pop(key)
    assert default == raster
    assert "voxels" not in default and set(default["frames"]) == {"lab", "trans", "local"}
    # No shower: the raster still draws shower A.
    bare = single_client.get(ROUTE, params={**BASE, "event_number": 0}).json()
    assert bare["meta"]["shower"] == "a" and bare["event"]["shower"]["key"] == "a"


def test_lab_cubes_are_the_events_cells_once_each(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        for event in _events(con, BASELINE_TABLE):
            body = _served(single_client, **BASE, event_number=event, frame="lab")
            vox = body["voxels"]
            assert vox["regime"] == "cells" and vox["frame"] == "lab"
            assert body["meta"]["shower"] == "both" and body["event"]["shower"] is None
            assert [s["key"] for s in body["event"]["showers"]] == ["a", "b"]
            rows = _rows(con, BASELINE_TABLE, event)
            cells = {(int(x), int(y), int(z)) for x, y, z in zip(rows["ix"], rows["iy"], rows["iz"])}
            cubes = _cubes(body)
            axes = vox["geometry"]["axes"]
            drawn = {(int(x) + axes["x"]["i0"], int(y) + axes["y"]["i0"], int(z) + axes["z"]["i0"])
                     for x, y, z in zip(cubes["ix"], cubes["iy"], cubes["iz"])}
            # The window (decision D-3: energy-weighted 0.1-99.9%) holds the cells whose centres lie in it;
            # the rest are counted, not drawn.
            lat = record.lattice
            win = body["window"]["axes"]
            inside = {c for c in cells if all(
                win[a][0] <= lat.axis(a).coords[c[k]] <= win[a][1] for k, a in enumerate("xyz"))}
            assert drawn == inside and len(drawn) == vox["cubes"]["n"]
            assert len(cells) == body["event"]["n_cells"]
            assert vox["cap"]["cells_outside_window"] == len(cells) - len(inside)
            # The shower code is the ingest's census: split cells are the event's n_split_cells.
            (n_split, e_dep) = con.execute(
                f"SELECT n_split_cells, e_dep FROM {quote(naming.event_table(BASELINE_TABLE))} "
                "WHERE event_number = ?", [event]).fetchone()
            assert int(((cubes["flags"] & 3) == voxel_event.SHOWER_MIXED).sum()) == n_split
            cap = vox["cap"]
            assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
                == pytest.approx(e_dep, rel=1e-9)
            assert cap["energy_total_gev"] == pytest.approx(float(rows["energy"].sum()), rel=1e-12)
            # Lattice coordinates and the measured footprint, never Axis.edges.
            lat = record.lattice
            for axis in "xyz":
                coords = np.asarray(axes[axis]["coords"])
                i0 = axes[axis]["i0"]
                np.testing.assert_allclose(coords, lat.axis(axis).coords[i0:i0 + coords.size], atol=5e-4)
            fp = canonical.cell_footprint(con, record)
            assert vox["geometry"]["cube_mm"] == pytest.approx([fp[0], fp[1], record.frame_bounds.layer_pitch_mm])


def test_cubes_are_drawn_in_ascending_energy_and_topk_is_exact(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        body = _served(single_client, **BASE, event_number=0, frame="lab", shower="b")
        rows = _rows(con, BASELINE_TABLE, 0, "org IN (1, 2)")
    vox = body["voxels"]
    cubes = _cubes(body)
    axes = vox["geometry"]["axes"]
    energy = {}
    for x, y, z, e in zip(rows["ix"], rows["iy"], rows["iz"], rows["energy"]):
        energy[(int(x), int(y), int(z))] = energy.get((int(x), int(y), int(z)), 0.0) + float(e)
    drawn = np.array([energy[(int(x) + axes["x"]["i0"], int(y) + axes["y"]["i0"], int(z) + axes["z"]["i0"])]
                      for x, y, z in zip(cubes["ix"], cubes["iy"], cubes["iz"])])
    assert (np.diff(drawn) >= 0).all(), "ascending energy, the notebook's draw order"
    volume = float(np.prod(vox["geometry"]["cube_mm"]))
    assert len(vox["topk"]) == min(64, drawn.size)
    for item in vox["topk"]:
        assert item["energy_gev"] == drawn[item["i"]]
        assert item["value"] == pytest.approx(drawn[item["i"]] / volume, rel=1e-12)
    assert vox["topk_quantity"] == "energy_density" and vox["topk_unit"] == "GeV/mm^3"
    assert set(int(c) for c in cubes["flags"] & 3) <= {voxel_event.SHOWER_B, voxel_event.SHOWER_AB}
    assert body["event"]["shower"]["key"] == "b" and body["event"]["shower"]["label"] == "B"


def test_the_energy_ramp_floors_at_the_first_percentile_of_cells(single_client):
    with _con(single_client) as con:
        rows = _rows(con, BASELINE_TABLE, 0)
    body = _served(single_client, **BASE, event_number=0, frame="lab")
    vox = body["voxels"]
    scale = vox["scale"]
    volume = float(np.prod(vox["geometry"]["cube_mm"]))
    energy = {}
    for x, y, z, e in zip(rows["ix"], rows["iy"], rows["iz"], rows["energy"]):
        energy[(int(x), int(y), int(z))] = energy.get((int(x), int(y), int(z)), 0.0) + float(e)
    cells = np.array(sorted(energy.values()))
    assert scale["floor_density"] == pytest.approx(np.percentile(cells, 1.0) / volume, rel=1e-12)
    assert scale["top_density"] == pytest.approx(cells.max() / volume, rel=1e-12)
    assert scale["scale"] == "log10" and scale["unit"] == "GeV/mm^3"
    assert scale["vmin"] == pytest.approx(np.log10(scale["floor_density"]))
    flags, code = _cubes(body)["flags"], _cubes(body)["code"]
    below = (flags & voxel_event.FLAG_BELOW_FLOOR) > 0
    assert vox["below_floor"]["n"] == int(below.sum()) == scale["clipped_low"]
    assert vox["below_floor"]["drawn_as"] == "lowest colour"
    assert (code[below] == 1).all() and (code >= 1).all()
    assert int((cells / volume < scale["floor_density"]).sum()) == int(below.sum())
    assert any("linear ramp with no floor" in n for n in vox["notes"])
    assert scale["floor_basis"] == "cells" and scale["degenerate"] is False


@pytest.mark.parametrize("frame, shower, cap", [("local", "a", 6000), ("local", "b", 6000),
                                                ("canonical", "both", 6000), ("local", "b", 500)])
def test_the_splat_ramp_floors_at_the_first_percentile_of_its_drawn_voxels(single_client, frame, shower, cap):
    """A splat's ramp runs from the 1st percentile of the drawn voxels' densities to the brightest."""
    with _con(single_client) as con:
        builder, body = _build(con, BASELINE_TABLE, 0, frame, shower, cap=cap)
    vox = body["voxels"]
    scale = vox["scale"]
    cubes = builder.cubes(vox["geometry"]["grid"]["pitch_mm"])
    drawn = np.sort(cubes.energy)[::-1][:cap] / cubes.volume_mm3
    floor = float(np.percentile(drawn, 1.0))
    assert scale["floor_basis"] == "voxels" and scale["degenerate"] is False
    assert scale["floor_density"] == pytest.approx(floor, rel=1e-12)
    assert scale["top_density"] == pytest.approx(drawn.max(), rel=1e-12)
    assert (scale["vmin"], scale["vmax"]) == pytest.approx((np.log10(floor), np.log10(drawn.max())), abs=1e-12)
    flags, code = _cubes(body)["flags"], _cubes(body)["code"]
    below = (flags & voxel_event.FLAG_BELOW_FLOOR) > 0
    assert int(below.sum()) == int((drawn < floor).sum()) == vox["below_floor"]["n"] == scale["clipped_low"]
    assert (code[below] == 1).all() and len(set(code.tolist())) > 100
    # The percentile's share, never the bulk the cells' floor put there.
    assert below.mean() <= 0.011
    assert "drawn 20 mm voxels' positive densities" in scale["floor_rule"]


def test_no_single_shower_splat_is_drawn_wholly_at_the_lowest_colour(single_client):
    """Over every Local shower of the single-shower file, the voxels span the ramp.

    With the floor taken from cell densities, 15 of these 60 showers drew
    every voxel at code 1 and 30 had more than half below the floor.
    """
    with _con(single_client) as con:
        events = _events(con, SINGLE_HITS_TABLE)
        for event in events:
            _, body = _build(con, SINGLE_HITS_TABLE, event, "local", "a", cap=6000)
            vox = body["voxels"]
            code = _cubes(body)["code"]
            n = vox["cubes"]["n"]
            if vox["scale"]["degenerate"]:
                # Only a frame whose voxels all hold one density: drawn at the top, said so.
                assert set(code.tolist()) == {255}, event
                continue
            assert len(set(code.tolist())) > 1, event
            assert vox["below_floor"]["n"] <= max(1, int(np.ceil(0.01 * n))), (event, vox["below_floor"], n)
    assert len(events) >= 50


def test_translated_cubes_sit_at_the_lattice_minus_p0(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        for shower in ("a", "b"):
            body = _served(single_client, **BASE, event_number=0, frame="trans", shower=shower)
            vox = body["voxels"]
            p0 = np.asarray(body["event"]["shower"]["p0"])
            assert vox["geometry"]["origin_mm"] == pytest.approx(p0.tolist())
            cubes = _cubes(body)
            axes = vox["geometry"]["axes"]
            for axis, index in (("x", cubes["ix"]), ("y", cubes["iy"]), ("z", cubes["iz"])):
                i0 = axes[axis]["i0"]
                coords = np.asarray(axes[axis]["coords"])
                decoded = coords[index] - p0["xyz".index(axis)]
                exact = record.lattice.axis(axis).coords[index + i0] - p0["xyz".index(axis)]
                np.testing.assert_allclose(decoded, exact, atol=5e-4 + 1e-9)
            assert body["coordinates"]["source"] == "lattice"
            assert body["coordinates"]["within_tolerance"] is True
            assert vox["symbols"] == {"x": "Δx", "y": "Δy", "z": "Δz"}


# -------------------------------------------------------------- placement --


def _cut_shift(con, table: str, event: int, body: dict) -> float:
    """How far the window can move an energy-weighted centroid, in mm.

    The event window (decision D-3, energy-weighted 0.1-99.9%) leaves a
    fraction f of the drawn energy out. Dropping mass f from a distribution
    moves its mean by at most f / (1 - f) times the largest distance from the
    mean, which the event's full lattice extent bounds. Zero when nothing was
    left out.
    """
    cap = body["voxels"]["cap"]
    f = cap["energy_outside_window_gev"] / cap["energy_total_gev"] if cap["energy_total_gev"] else 0.0
    if f <= 0:
        return 0.0
    lat = _record(con, table).lattice
    rows = _rows(con, table, event)
    lab = np.column_stack([lat.x.coords[rows["ix"]], lat.y.coords[rows["iy"]], lat.z.coords[rows["iz"]]])
    return f / (1.0 - f) * float(np.linalg.norm(np.ptp(lab, axis=0)))


def test_lab_cube_centres_are_their_cells_lattice_coordinates(single_client):
    """Each decoded cube centre is the measured lattice position of exactly one of the event's cells."""
    with _con(single_client) as con:
        cases = [(BASELINE_TABLE, e, "both") for e in _events(con, BASELINE_TABLE)]
        cases += [(SINGLE_HITS_TABLE, e, "a") for e in _events(con, SINGLE_HITS_TABLE)[:6]]
        for table, event, shower in cases:
            lat = _record(con, table).lattice
            builder, body = _build(con, table, event, "lab", shower)
            contract_check.check(body["voxels"], "event_voxels", at="voxels_cells")
            rows = _rows(con, table, event)
            cells: dict[tuple[int, int, int], float] = {}
            for x, y, z, e in zip(rows["ix"], rows["iy"], rows["iz"], rows["energy"]):
                key = (int(x), int(y), int(z))
                cells[key] = cells.get(key, 0.0) + float(e)
            keys = np.array(list(cells))
            lattice = np.column_stack([lat.x.coords[keys[:, 0]], lat.y.coords[keys[:, 1]], lat.z.coords[keys[:, 2]]])
            energy = np.array(list(cells.values()))
            centre, shipped, _ = _placed(builder, body)
            distance = np.abs(centre[:, None, :] - lattice[None, :, :]).max(axis=2)
            match = distance.argmin(axis=1)
            # Within the 0.001 mm the coordinates are rounded to, and one cube per cell.
            assert distance[np.arange(match.size), match].max() <= 5e-4 + 1e-9, (table, event)
            outside = body["voxels"]["cap"]["cells_outside_window"]
            assert len(set(match.tolist())) == match.size == len(cells) - outside, (table, event)
            np.testing.assert_allclose(shipped, energy[match], rtol=1e-12)
            # Payload order is ascending energy of the cell each cube is drawn on.
            assert (np.diff(energy[match]) >= 0).all(), (table, event)
            for item in body["voxels"]["topk"]:
                assert item["energy_gev"] == pytest.approx(energy[match[item["i"]]], rel=1e-12)


def test_translated_cube_centroid_is_the_event_tables(single_client):
    """The energy-weighted cube centroid is the event table's translated centroid, within half a cube."""
    checked = 0
    with _con(single_client) as con:
        cases = [(BASELINE_TABLE, e, s) for e in _events(con, BASELINE_TABLE) for s in ("a", "b")]
        cases += [(SINGLE_HITS_TABLE, e, "a") for e in _events(con, SINGLE_HITS_TABLE)[:12]]
        for table, event, shower in cases:
            if not _complete(con, table, event, (shower,)):
                continue
            builder, body = _build(con, table, event, "trans", shower)
            centre, energy, _ = _placed(builder, body)
            got = np.average(centre, axis=0, weights=energy)
            expected = _table_centroid(con, table, event, shower, "trn")
            # Half a cube, plus what the window's 0.2% cut can move the centroid by.
            half = 0.5 * np.asarray(body["voxels"]["geometry"]["cube_mm"]) + _cut_shift(con, table, event, body)
            assert (np.abs(got - expected) <= half).all(), (table, event, shower, got - expected)
            checked += 1
    assert checked >= 10


def test_local_voxel_centroid_is_the_event_tables(single_client):
    """The energy-weighted voxel centroid is the event table's local centroid, within half a voxel pitch."""
    checked = 0
    with _con(single_client) as con:
        cases = [(BASELINE_TABLE, e, s) for e in _events(con, BASELINE_TABLE) for s in ("a", "b")]
        cases += [(SINGLE_HITS_TABLE, e, "a") for e in _events(con, SINGLE_HITS_TABLE)[:12]]
        for table, event, shower in cases:
            if not _complete(con, table, event, (shower,)):
                continue
            builder, body = _build(con, table, event, "local", shower)
            centre, energy, _ = _placed(builder, body)
            got = np.average(centre, axis=0, weights=energy)
            expected = _table_centroid(con, table, event, shower, "loc")
            grid = body["voxels"]["geometry"]["grid"]
            half = 0.5 * np.array([grid["pitch_mm"], grid["pitch_mm"], grid["pitch_z_mm"]]) \
                + _cut_shift(con, table, event, body)
            assert (np.abs(got - expected) <= half).all(), (table, event, shower, got - expected)
            checked += 1
    assert checked >= 10


def test_the_d_frame_puts_shower_a_at_negative_x_and_b_at_positive(single_client):
    """A→B runs along +x′: A's voxels lie at negative x′, B's at positive, D_entry apart at the face."""
    anchored = 0
    with _con(single_client) as con:
        for event in _events(con, BASELINE_TABLE):
            builder, body = _build(con, BASELINE_TABLE, event, "canonical", "both")
            d_frame = body["event"]["d_frame"]
            assert d_frame["d_entry_mm"] >= frame_mod.ILL_CONDITIONED_D_MM
            centre, energy, code = _placed(builder, body)
            sides = {"a": code == voxel_event.SHOWER_A,
                     "b": (code == voxel_event.SHOWER_B) | (code == voxel_event.SHOWER_AB)}
            mean_x = {key: np.average(centre[sel, 0], weights=energy[sel]) for key, sel in sides.items()}
            assert mean_x["a"] < 0.0 < mean_x["b"], (event, mean_x)
            if not _complete(con, BASELINE_TABLE, event, ("a", "b")):
                continue
            # What the window's 0.2% cut can move a centroid by, and so its back-projection.
            cut = _cut_shift(con, BASELINE_TABLE, event, body)
            # A complete event: every voxel on its own side, and each shower's centroid,
            # back-projected along its own direction to the face z′ = 0, on its anchor.
            assert (centre[sides["a"], 0] < 0.0).all() and (centre[sides["b"], 0] > 0.0).all(), event
            pitch = body["voxels"]["geometry"]["grid"]["pitch_mm"]
            psi = d_frame["psi"]
            back = {}
            slack = {}
            for shower in body["event"]["showers"]:
                sel = sides[shower["key"]]
                c = np.average(centre[sel], axis=0, weights=energy[sel])
                u = np.asarray(shower["direction"])
                along = np.cos(psi) * u[0] + np.sin(psi) * u[1]
                across = -np.sin(psi) * u[0] + np.cos(psi) * u[1]
                back[shower["key"]] = (c[0] - c[2] * along / u[2], c[1] - c[2] * across / u[2])
                slack[shower["key"]] = cut * (1.0 + max(abs(along), abs(across)) / abs(u[2]))
            assert back["b"][0] - back["a"][0] == pytest.approx(
                d_frame["d_entry_mm"], abs=pitch + slack["a"] + slack["b"]), (event, back)
            # Each on its own anchor (x′ = ∓D_entry/2, y′ = 0) within half a voxel: 0.07-0.19 mm measured
            # on the whole event, plus what the window's cut can move it.
            for key, sign in (("a", -1.0), ("b", 1.0)):
                assert back[key][0] == pytest.approx(sign * 0.5 * d_frame["d_entry_mm"],
                                                     abs=0.5 * pitch + slack[key]), (event, back)
                assert abs(back[key][1]) <= 0.5 * pitch + slack[key], (event, back)
            anchored += 1
    assert anchored >= 1


def test_splat_voxels_are_the_stated_splat_of_the_cells(single_client):
    """Every splat frame's voxels are what the payload states: the cells' footprints, moved, binned.

    An independent re-implementation - the payload's k, k_z and footprint, the
    frame's own rotation (R(θ, φ) from the shower's direction in Local, R_z(ψ)
    from the entry anchors in the D-frame), the payload's grid - must reproduce
    the shipped voxel energies. A footprint left unrotated, a grid origin off
    by a pitch or a mirrored D-frame moves 8-38% of the energy to other voxels.
    """
    worst = 0.0
    with _con(single_client) as con:
        cases = [(BASELINE_TABLE, e, f, s) for e in _events(con, BASELINE_TABLE)
                 for f, s in (("local", "a"), ("local", "b"), ("canonical", "both"))]
        cases += [(SINGLE_HITS_TABLE, e, "local", "a") for e in _events(con, SINGLE_HITS_TABLE)[:6]]
        for table, event, frame, shower in cases:
            lat = _record(con, table).lattice
            builder, body = _build(con, table, event, frame, shower)
            geometry = body["voxels"]["geometry"]
            grid, splat = geometry["grid"], geometry["splat"]
            pitch = grid["pitch_mm"]
            x_edges = grid["x0"] + pitch * np.arange(grid["n"][0] + 1)
            y_edges = grid["y0"] + pitch * np.arange(grid["n"][1] + 1)
            rows = _rows(con, table, event, _shower_where(shower), extra=", xl, yl, zl")
            energy = rows["energy"].astype(np.float64)
            if frame == "local":
                info = body["event"]["shower"]
                centres = np.column_stack([rows[c].astype(np.float64) for c in ("xl", "yl", "zl")])
                z_edges = grid["z0"] + grid["pitch_z_mm"] * np.arange(grid["n"][2] + 1)
                reference = _reference_splat(centres, energy, _rotation(info["theta"], info["phi"]),
                                             splat["footprint_mm"], splat["k"], splat["k_z"],
                                             (x_edges, y_edges, z_edges))
            else:
                d_frame = body["event"]["d_frame"]
                mid = 0.5 * (np.asarray(d_frame["entry_a"]) + np.asarray(d_frame["entry_b"]))
                turn = _rotation(0.0, d_frame["psi"])
                lab = np.column_stack([lat.x.coords[rows["ix"]], lat.y.coords[rows["iy"]], lat.z.coords[rows["iz"]]])
                centres = (lab - np.array([mid[0], mid[1], d_frame["z_front_mm"]])) @ turn.T
                layer = rows["iz"].astype(np.int64) - geometry["axes"]["z"]["i0"]
                z_edges = np.arange(grid["n"][2] + 1, dtype=np.float64) - 0.5
                reference = _reference_splat(centres, energy, turn, splat["footprint_mm"], splat["k"],
                                             splat["k_z"], (x_edges, y_edges, z_edges), layer=layer)
            cubes = _cubes(body)
            _, shipped_energy, _ = _placed(builder, body)
            shipped = np.zeros_like(reference)
            np.add.at(shipped, (cubes["ix"], cubes["iy"], cubes["iz"]), shipped_energy)
            moved = float(np.abs(shipped - reference).sum() / reference.sum())
            worst = max(worst, moved)
            assert moved < 1e-3, (table, event, frame, shower, moved)
    assert worst < 1e-3


# ------------------------------------------------------ two showers: splats --


@pytest.mark.parametrize("shower", ["a", "b"])
def test_the_local_splat_conserves_the_showers_energy(single_client, shower):
    origin = "org = 0" if shower == "a" else "org IN (1, 2)"
    with _con(single_client) as con:
        rows = _rows(con, BASELINE_TABLE, 0, origin)
    body = _served(single_client, **BASE, event_number=0, shower=shower)
    vox = body["voxels"]
    assert vox["frame"] == "local" and vox["regime"] == "subdeposit_splat"
    geometry = vox["geometry"]
    assert geometry["splat"]["k"] == voxel_event.EVENT_SPLAT_K >= frame_mod.MIN_SUBSAMPLE
    assert geometry["splat"]["k_z"] == voxel_event.EVENT_LOCAL_K_Z
    assert "cannot tilt" in geometry["note"]
    cap = vox["cap"]
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
        == pytest.approx(float(rows["energy"].sum()), rel=1e-9)
    cubes = _cubes(body)
    n = geometry["grid"]["n"]
    assert (cubes["ix"] < n[0]).all() and (cubes["iy"] < n[1]).all() and (cubes["iz"] < n[2]).all()
    # 20 mm: both showers' grids fit a one-byte index there, so nothing coarsens them up front.
    assert geometry["grid"]["pitch_mm"] == 20.0 and geometry["cube_mm"][:2] == [20.0, 20.0]
    assert max(n[:2]) <= voxel_event.MAX_VOXELS_PER_AXIS and vox["cubes"]["dtype"]["ix"] == "u8"
    assert not any("were coarsened" in note for note in vox["notes"])
    assert vox["symbols"] == {"x": "u", "y": "v", "z": "w"}
    computed = _served(single_client, **BASE, event_number=0, shower=shower, coordinates="computed")
    assert computed["coordinates"]["source"] == "computed"
    assert computed["voxels"]["cap"]["energy_total_gev"] == pytest.approx(cap["energy_total_gev"], rel=1e-12)


def test_the_d_frame_draws_both_showers_on_native_layers(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        rows = _rows(con, BASELINE_TABLE, 0)
    # Every voxel drawn, so every populated layer appears (at 20 mm the default cap leaves the faintest out).
    body = _served(single_client, **BASE, event_number=0, frame="canonical", cap=15000)
    vox = body["voxels"]
    assert body["meta"]["shower"] == "both" and vox["symbols"] == {"x": "x′", "y": "y′", "z": "z′"}
    cap = vox["cap"]
    assert cap["n_beyond"] == 0
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
        == pytest.approx(float(rows["energy"].sum()), rel=1e-9)
    geometry = vox["geometry"]
    assert geometry["splat"]["k_z"] == 1 and geometry["grid"]["z_axis"] == "native_layers"
    z = geometry["axes"]["z"]
    zf = record.lattice.z.lo
    np.testing.assert_allclose(z["coords"], record.lattice.z.coords[z["i0"]:z["i0"] + len(z["coords"])] - zf,
                               atol=5e-4)
    assert geometry["grid"]["n"][2] == len(z["coords"])
    # Every populated layer is a depth index: iz - i0.
    layers = set(int(v) - z["i0"] for v in rows["iz"])
    assert set(_cubes(body)["iz"].tolist()) == layers
    d_frame = body["event"]["d_frame"]
    assert d_frame["anchor"] == "backprojected" and d_frame["d_entry_mm"] > 0
    # One shower in the event's D-frame: its own rows, the same frame.
    only_a = _served(single_client, **BASE, event_number=0, frame="canonical", shower="a")
    cap_a = only_a["voxels"]["cap"]
    assert cap_a["energy_total_gev"] == pytest.approx(float(rows["energy"][rows["org"] == 0].sum()), rel=1e-12)
    assert only_a["event"]["d_frame"] == d_frame and only_a["event"]["shower"]["key"] == "a"
    assert set(int(c) for c in _cubes(only_a)["flags"] & 3) == {voxel_event.SHOWER_A}
    # A well-separated event carries no ill-conditioning sentence.
    assert not any("effectively random" in n["text"] for n in body["meta"]["notices"])


def test_the_splat_pitch_coarsens_only_past_a_one_byte_index(single_client, monkeypatch):
    """20 mm wherever the grid fits 256 voxels per axis; coarser only as far as a byte needs, and said."""
    with _con(single_client) as con:
        for event in _events(con, BASELINE_TABLE):
            for frame, shower in (("local", "a"), ("local", "b"), ("canonical", "both")):
                builder, body = _build(con, BASELINE_TABLE, event, frame, shower)
                grid = body["voxels"]["geometry"]["grid"]
                # The D-frame's 212-voxel-wide grid included: the 96-bin rule drew it at 80 mm.
                assert builder.first_pitch == grid["pitch_mm"] == 20.0, (event, frame, shower)
                assert max(grid["n"][:2]) <= voxel_event.MAX_VOXELS_PER_AXIS
                assert not any("coarsened" in note for note in body["voxels"]["notes"])
        # With room for only 60 voxels per axis, event 0's D-frame doubles until it fits, no further.
        monkeypatch.setattr(voxel_event, "MAX_VOXELS_PER_AXIS", 60)
        builder, body = _build(con, BASELINE_TABLE, 0, "canonical", "both")
    pitch = builder.first_pitch
    wide = max(e.size - 1 for e in builder.transverse_edges(20.0))
    assert wide > 60 and pitch > 20.0
    assert max(e.size - 1 for e in builder.transverse_edges(pitch)) <= 60
    assert max(e.size - 1 for e in builder.transverse_edges(pitch / 2.0)) > 60
    grid = body["voxels"]["geometry"]["grid"]
    assert grid["pitch_mm"] == pitch and max(grid["n"][:2]) <= 60
    note = next(n for n in body["voxels"]["notes"] if "coarsened" in n)
    assert f"coarsened to {pitch:.0f} mm" in note and f"{wide:,} voxels" in note and "60" in note


def test_an_ill_conditioned_d_frame_event_says_its_orientation_is_random(single_client):
    """Entry anchors 10 mm apart fix no rotation: the body says so, in the D-frame's own sentence."""
    from calosrv.api import frame_canonical, routes_event
    from calosrv.models.common import Timer

    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        # Shower B's centroid and direction set 10 mm from shower A's: anchors 10 mm apart.
        moved = ", ".join(
            f"CASE WHEN event_number = 0 THEN {a} ELSE {b} END AS {b}"
            for a, b in (("cax + 10", "cbx"), ("cay", "cby"), ("caz", "cbz"), ("theta_a", "theta_b"),
                         ("phi_a", "phi_b")))
        probe = _probe(con, record, "ill", event_sql=f"SELECT * REPLACE ({moved}) FROM {{event}}")
        body = routes_event._voxels(con, probe, filters.build(probe), Timer(), 0, None, "file",
                                    "canonical", "energy", "segmentation", None)
    body = json.loads(json.dumps(body))
    _check_body(body)
    d_frame = body["event"]["d_frame"]
    assert d_frame["d_entry_mm"] == pytest.approx(10.0, abs=1e-6) and d_frame["ill_conditioned"] is True
    expected = typographic(frame_canonical.ill_conditioned_event_notice(d_frame["d_entry_mm"]))
    assert "10 mm apart" in expected and "effectively random" in expected
    events = [n["text"] for n in body["meta"]["notices"] if n["scope"] == "event"]
    assert expected in events and expected in body["voxels"]["notes"]


@pytest.mark.parametrize("channel", ["gradcam", "shapcam", "segerr"])
@pytest.mark.parametrize("frame", ["lab", "local"])
def test_network_channels_on_their_ramps(single_client, channel, frame):
    shower = "a" if frame == "local" else None
    params = {**BASE, "event_number": 0, "frame": frame, "channel": channel, "model": "energy"}
    if shower:
        params["shower"] = shower
    body = _served(single_client, **params)
    vox = body["voxels"]
    scale = vox["scale"]
    assert scale["scale"] == "linear" and scale["quantity"] == channel
    lo, hi = (-1.0, 1.0) if channel == "shapcam" else (0.0, 1.0)
    assert (scale["vmin"], scale["vmax"]) == (lo, hi)
    assert scale["clipped_low"] == scale["clipped_high"] == 0
    if channel == "shapcam":
        assert scale["diverging"] is True and scale["zero_code"] == 128
    # Segmentation error is always the frame's segmentation network, whatever model was asked for.
    assert vox["model"] == body["meta"]["model"] == ("segmentation" if channel == "segerr" else "energy")
    assert vox["below_floor"]["n"] == 0
    values = [t["value"] for t in vox["topk"]]
    assert all(lo <= v <= hi for v in values)
    if channel == "shapcam":
        assert values == sorted(values, key=abs, reverse=True)
    if channel in ("gradcam", "shapcam"):
        assert body["meta"]["cam"]["model"] == "energy"
        assert body["meta"]["cam"]["network_frame"] == ("absolute" if frame == "lab" else "local")
    else:
        assert body["meta"]["cam"] is None


def test_an_event_outside_the_selection_is_drawn_and_said_so(single_client):
    experiments = single_client.get("/api/experiments").json()["experiments"]
    bounds = next(e for e in experiments if e["table_name"] == BASELINE_TABLE)["bounds"]
    body = _served(single_client, **BASE, event_number=0, frame="lab",
                   e1_min=bounds["e1"][1] + 5.0, e1_max=bounds["e1"][1] + 6.0)
    assert body["event"]["in_selection"] is False
    assert any("outside the current selection" in w for w in body["meta"]["warnings"])


def test_lab_cam_values_are_the_cells_own(single_client):
    """A cell's Grad-CAM is the per-voxel column value: the exact top values are the database's."""
    column = ddl.cam_column("energy", "lab", "gradcam")
    with _con(single_client) as con:
        rows = _rows(con, BASELINE_TABLE, 0, extra=f", CAST({column} AS DOUBLE) AS g")
    body = _served(single_client, **BASE, event_number=0, frame="lab", channel="gradcam", model="energy")
    values = {(int(x), int(y), int(z)): float(g)
              for x, y, z, g in zip(rows["ix"], rows["iy"], rows["iz"], rows["g"])}
    vox = body["voxels"]
    cubes = _cubes(body)
    axes = vox["geometry"]["axes"]
    for item in vox["topk"]:
        i = item["i"]
        key = (int(cubes["ix"][i]) + axes["x"]["i0"], int(cubes["iy"][i]) + axes["y"]["i0"],
               int(cubes["iz"][i]) + axes["z"]["i0"])
        assert item["value"] == pytest.approx(values[key], abs=1e-7)


# ------------------------------------------------------------ cap, budget --


def test_the_cap_draws_the_most_energetic_and_counts_the_rest(single_client):
    full = _served(single_client, **BASE, event_number=0, frame="lab", cap=15000)
    capped = _served(single_client, **BASE, event_number=0, frame="lab", cap=100)
    cap, whole = capped["voxels"]["cap"], full["voxels"]["cap"]
    assert whole["n_beyond"] == 0 and whole["n_drawn"] == whole["n_total"] > 100
    assert cap["n_drawn"] == capped["voxels"]["cubes"]["n"] == 100 and cap["limit"] == cap["requested"] == 100
    assert cap["n_beyond"] == whole["n_total"] - 100
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] == pytest.approx(whole["energy_drawn_gev"], rel=1e-9)
    assert cap["fraction_beyond"] == pytest.approx(cap["energy_beyond_gev"] / cap["energy_total_gev"])
    # The drawn hundred are the brightest (exactly so in the builder test below), and it is said.
    assert any("beyond the cap" in n for n in capped["voxels"]["notes"])


def test_cap_is_checked_for_the_cubes_and_ignored_by_the_raster(single_client):
    """cap is an integer; the raster never reads its value, so no range refuses a raster request."""
    params = {**BASE, "event_number": 0, "shower": "a"}
    plain = single_client.get(ROUTE, params=params).json()
    for key in ("query_ms", "total_ms"):
        plain["meta"].pop(key)
    for cap in ("50", "15001", "6000"):
        raster = single_client.get(ROUTE, params={**params, "cap": cap})
        assert raster.status_code == 200, (cap, raster.text[:300])
        body = raster.json()
        for key in ("query_ms", "total_ms"):
            body["meta"].pop(key)
        assert body == plain, cap
    for cap in ("50", "99", "15001"):
        problem = _refused(single_client, "cap", **BASE, event_number=0, frame="lab", cap=cap)
        assert "cap must be an integer from 100 to 15,000" in problem["detail"]
    # Not an integer at all: the declared type refuses it, on either format.
    for fmt in ("raster", "voxels"):
        for cap in ("abc", "1e3"):
            reply = single_client.get(ROUTE, params={**params, "format": fmt, "cap": cap})
            assert reply.status_code == 422 and reply.json()["field"] == "cap", (fmt, cap)
    for cap in ("100", "15000"):
        assert _served(single_client, **BASE, event_number=0, frame="lab", cap=cap)["voxels"]["cap"]["requested"] \
            == int(cap)


def test_a_cap_below_the_routes_floor_is_the_builders_to_take(single_client):
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        builder = voxel_event.build(con, record, filters.build(record), 0, "lab", "both",
                                    footprint=canonical.cell_footprint(con, record))
        whole = builder.assemble(15000, None)["voxels"]["cap"]
        body = builder.assemble(50, None)["voxels"]
    assert body["cap"]["n_drawn"] == body["cubes"]["n"] == 50
    energies = np.sort(builder.cubes(None).energy)[::-1]
    assert body["cap"]["energy_drawn_gev"] == pytest.approx(energies[:50].sum(), rel=1e-12)
    assert body["cap"]["energy_beyond_gev"] == pytest.approx(whole["energy_drawn_gev"] - energies[:50].sum(),
                                                             rel=1e-9)


@pytest.mark.parametrize("table, frame, channel", [
    (BASELINE_TABLE, "lab", "energy"), (BASELINE_TABLE, "local", "shapcam"),
    (SINGLE_HITS_TABLE, "lab", "species"), (SINGLE_HITS_TABLE, "trans", "species"),
    (SINGLE_HITS_TABLE, "local", "species"),
])
def test_bytes_per_cube_is_what_a_cube_costs_on_the_wire(single_client, table, frame, channel):
    """The guard's per-cube cost is the per-cube arrays actually shipped for this regime and channel."""
    with _con(single_client) as con:
        record = _record(con, table)
        event = 0 if table == BASELINE_TABLE else int(con.execute(
            f"SELECT event_number FROM {quote(naming.event_table(table))} "
            "ORDER BY n_cells DESC, event_number LIMIT 1").fetchone()[0])
        shower = "a" if frame != "lab" or table == SINGLE_HITS_TABLE else "both"
        builder = voxel_event.build(con, record, filters.build(record), event, frame, shower, channel,
                                    footprint=canonical.cell_footprint(con, record))
    pitch = builder.first_pitch
    n = builder.n_cubes(pitch)
    estimate = builder.bytes_per_cube(pitch)
    # Exactly the per-cube arrays in the body: cells ship parent, daughter count and mode on the
    # species channel, splats only purity, and purity only where a cube is impure.
    vox = builder.assemble(n, pitch)["voxels"]
    arrays = [vox["cubes"][name] for name in ("ix", "iy", "iz", "code", "flags")]
    if vox["species"] is not None:
        arrays += [vox["species"][name] for name in ("parent", "n_daughters", "daughter_mode", "purity")
                   if vox["species"][name] is not None]
    assert sum(len(text) for text in arrays) / n == pytest.approx(estimate, abs=4.0 * len(arrays) / n)
    if n > 400:
        # And at the margin: both caps above the 64 exact values and below n, so only the cubes
        # change - provided both ship the same arrays (purity can vanish with the impure cubes).
        high, low = (builder.assemble(cap, pitch) for cap in (n - 1, n - 301))
        same = all((body["voxels"]["species"] or {}).get("purity") is None
                   for body in (high, low)) or all(body["voxels"]["species"]["purity"] for body in (high, low))
        if same:
            measured = (density.wire_size(high) - density.wire_size(low)) / 300.0
            assert measured == pytest.approx(estimate, rel=0.03), (n, measured)


def test_the_guard_lowers_the_cap_and_says_so(single_client, monkeypatch):
    params = {**VOX, **BASE, "event_number": 0, "frame": "lab"}
    whole = single_client.get(ROUTE, params=params)
    limit = len(whole.content) - 2_000
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)
    response = single_client.get(ROUTE, params=params)
    assert response.status_code == 200
    body = response.json()
    contract_check.check(body, "event_voxels")
    assert len(response.content) < limit and density.wire_size(body) < limit
    cap = body["voxels"]["cap"]
    assert cap["limit"] < cap["requested"] == voxel_event.DEFAULT_CAP and cap["n_beyond"] > 0
    assert cap["n_drawn"] == cap["limit"] == body["voxels"]["cubes"]["n"]
    steps = [n["text"] for n in body["meta"]["notices"] if n["scope"] == "budget"]
    assert steps and all("the cap was lowered" in s for s in steps)
    assert f"to {cap['limit']:,} cubes" in steps[-1]
    assert body["meta"]["warnings"] == []


def test_the_guard_coarsens_a_splat_before_it_caps(single_client, monkeypatch):
    params = {**VOX, **BASE, "event_number": 0, "shower": "a"}
    first = single_client.get(ROUTE, params=params)
    assert first.json()["voxels"]["geometry"]["grid"]["pitch_mm"] == 20.0
    monkeypatch.setattr(density, "RESPONSE_LIMIT", len(first.content) - 500)
    body = single_client.get(ROUTE, params=params).json()
    steps = [n["text"] for n in body["meta"]["notices"] if n["scope"] == "budget"]
    assert steps and "coarsened from 20 mm to 40 mm" in steps[0]
    geometry = body["voxels"]["geometry"]
    assert geometry["grid"]["pitch_mm"] == 40.0 and geometry["cube_mm"][:2] == [40.0, 40.0]
    cap = body["voxels"]["cap"]
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
        == pytest.approx(cap["energy_total_gev"], rel=1e-9)


def test_an_overrun_after_every_step_is_served_and_said(single_client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    response = single_client.get(ROUTE, params={**VOX, **BASE, "event_number": 0, "frame": "lab"})
    body = response.json()
    assert response.status_code == 200 and len(response.content) >= 2_000
    assert "still" in body["meta"]["warnings"][-1] and "a smaller cap" in body["meta"]["warnings"][-1]


# ------------------------------------------------------------------ probes --
#
# Copies of an experiment as two temporary views on one read cursor - the event
# and projection tables, one of them altered - under a name no other test uses,
# for the cases the fixture files do not hold.


def _probe(con, record, suffix: str, event_sql: str | None = None, proj_sql: str | None = None):
    probe = dataclasses.replace(record, table_name=f"{record.table_name}_{suffix}")
    event = quote(naming.event_table(record.table_name))
    proj = quote(naming.proj_table(record.table_name))
    con.execute(f"CREATE OR REPLACE TEMP VIEW {quote(naming.event_table(probe.table_name))} AS "
                + (event_sql or f"SELECT * FROM {event}").format(event=event, proj=proj))
    con.execute(f"CREATE OR REPLACE TEMP VIEW {quote(naming.proj_table(probe.table_name))} AS "
                + (proj_sql or f"SELECT * FROM {proj}").format(event=event, proj=proj))
    return probe


def test_a_split_cell_is_one_cube_coded_three(single_client):
    """A B row added to one of shower A's cells: one cube, the energies summed, shower code 3."""
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        (ix, iy, iz, e) = con.execute(
            f"SELECT ix, iy, iz, energy FROM {quote(naming.proj_table(BASELINE_TABLE))} "
            "WHERE event_number = 0 AND org = 0 ORDER BY energy DESC LIMIT 1").fetchone()
        probe = _probe(con, record, "split", proj_sql=(
            "SELECT * FROM {proj} UNION ALL SELECT * REPLACE (1::UTINYINT AS org, energy * 0.5 AS energy) "
            f"FROM {{proj}} WHERE event_number = 0 AND org = 0 AND ix = {ix} AND iy = {iy} AND iz = {iz}"))
        spec = filters.build(probe)
        fp = canonical.cell_footprint(con, record)
        builder = voxel_event.build(con, probe, spec, 0, "lab", "both", footprint=fp)
        split = builder.assemble(15000, None)
        plain = voxel_event.build(con, record, filters.build(record), 0, "lab", "both",
                                  footprint=fp).assemble(15000, None)
        only_b = voxel_event.build(con, probe, spec, 0, "lab", "b", footprint=fp).assemble(15000, None)
    flags = _decode(split["voxels"]["cubes"]["flags"], "u8")
    assert int(((flags & 3) == voxel_event.SHOWER_MIXED).sum()) == 1
    assert split["voxels"]["cubes"]["n"] == plain["voxels"]["cubes"]["n"]
    assert split["voxels"]["cap"]["energy_total_gev"] == pytest.approx(
        plain["voxels"]["cap"]["energy_total_gev"] + 0.5 * e, rel=1e-12)
    # The split cell is one cube holding both rows' energy.
    cubes = builder.cubes(None)
    (index,) = np.flatnonzero(cubes.shower == voxel_event.SHOWER_MIXED)
    assert cubes.energy[index] == pytest.approx(1.5 * e, rel=1e-12)
    axes = split["voxels"]["geometry"]["axes"]
    assert (cubes.ix[index] + axes["x"]["i0"], cubes.iy[index] + axes["y"]["i0"],
            cubes.iz[index] + axes["z"]["i0"]) == (ix, iy, iz)
    assert split["event"]["showers"][0]["energy_gev"] == pytest.approx(
        plain["event"]["showers"][0]["energy_gev"])
    # Shower B alone holds the added row as a B cell of its own.
    assert int(((_decode(only_b["voxels"]["cubes"]["flags"], "u8") & 3) == voxel_event.SHOWER_MIXED).sum()) == 0


def test_frames_that_cannot_place_the_event_are_404s(single_client):
    from calosrv.errors import NotFoundError

    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
        probe = _probe(con, record, "unplaced", event_sql=(
            "SELECT * REPLACE (CASE WHEN event_number = 0 THEN NULL ELSE cax END AS cax, "
            "CASE WHEN event_number = 0 THEN NULL ELSE theta_a END AS theta_a) FROM {event}"))
        spec = filters.build(probe)
        fp = canonical.cell_footprint(con, record)
        with pytest.raises(NotFoundError, match="no D-frame"):
            voxel_event.build(con, probe, spec, 0, "canonical", "both", footprint=fp)
        with pytest.raises(NotFoundError, match="no incident direction"):
            voxel_event.build(con, probe, spec, 0, "local", "a", footprint=fp)
        # The laboratory frame needs neither; shower B's own frames are untouched.
        assert voxel_event.build(con, probe, spec, 0, "lab", "both", footprint=fp).assemble(100, None)
        assert voxel_event.build(con, probe, spec, 0, "local", "b", footprint=fp).assemble(100, 20.0)
        nothing = _probe(con, record, "no_a", proj_sql="SELECT * FROM {proj} WHERE org <> 0")
        with pytest.raises(NotFoundError, match="no hit attributed to shower A"):
            voxel_event.build(con, nothing, filters.build(nothing), 0, "lab", "a", footprint=fp)


def test_other_species_are_one_code_with_their_members_listed(single_client):
    with _con(single_client) as con:
        record = _record(con, SINGLE_HITS_TABLE)
        event = _events(con, SINGLE_HITS_TABLE)[0]
        probe = _probe(con, record, "ions", proj_sql=(
            "SELECT * REPLACE (CASE WHEN ix % 3 = 0 THEN 'PDG_1000080160' WHEN ix % 3 = 1 THEN NULL "
            "ELSE particle_type END AS particle_type) FROM {proj}"))
        rows = con.execute(
            f"SELECT ix % 3 AS k, count(*) FROM {quote(naming.proj_table(SINGLE_HITS_TABLE))} "
            "WHERE event_number = ? GROUP BY k", [event]).fetchall()
        builder = voxel_event.build(con, probe, filters.build(probe), event, "lab", "a", "species",
                                    footprint=canonical.cell_footprint(con, record))
        body = builder.assemble(15000, None)
    counts = dict(rows)
    other = next(e for e in body["voxels"]["species"]["legend"] if e["code"] == voxel_event.OTHER_CODE)
    members = {m["name"]: m["rows"] for m in other["members"]}
    assert members == {name: counts[k] for name, k in
                       (("PDG_1000080160", 0), (voxel_event.MISSING_SPECIES, 1)) if counts.get(k)}
    codes = _decode(body["voxels"]["cubes"]["code"], "u8")
    assert int((codes == voxel_event.OTHER_CODE).sum()) == other["cells"] == other["cubes"]


@pytest.mark.parametrize("frame", ["lab", "trans", "local"])
def test_a_single_hit_event_is_one_cube_or_its_splat(single_client, frame):
    with _con(single_client) as con:
        (event,) = con.execute(
            f"SELECT min(event_number) FROM {quote(naming.event_table(SINGLE_HITS_TABLE))} "
            "WHERE n_hits = 1").fetchone()
    body = _served(single_client, **HITS, event_number=event, frame=frame)
    vox = body["voxels"]
    scale = vox["scale"]
    codes = _cubes(body)["code"]
    assert body["event"]["n_cells"] == 1
    if frame != "local":
        # One cell is one density: a zero-width ramp at it, stated as degenerate, the cube at its top.
        assert vox["cubes"]["n"] == 1 and scale["degenerate"] is True
        assert scale["vmin"] == scale["vmax"] == pytest.approx(np.log10(scale["top_density"]), abs=1e-12)
        assert codes.tolist() == [255] and vox["below_floor"]["n"] == 0
        assert "degenerate" in scale["floor_rule"]
    else:
        # The splat's voxels hold different parts of one footprint: a ramp from their own floor,
        # so they span the colours instead of all sitting at the lowest under a cell floor.
        n = vox["cubes"]["n"]
        assert n == vox["cap"]["n_total"] > 1
        assert scale["degenerate"] is False and scale["vmax"] > scale["vmin"]
        assert len(set(codes.tolist())) > 1
        assert vox["below_floor"]["n"] <= max(1, int(np.ceil(0.01 * n)))
    assert body["window"]["half_mm"] == 150.0


# ---------------------------------------------------------------- refusals --


def test_two_shower_refusals_name_the_field(single_client):
    problem = _refused(single_client, "channel", "vox-species", **BASE, event_number=0, channel="species")
    assert "TODO.md" in problem["reason"]
    _refused(single_client, "shower", **BASE, event_number=0, frame="local", shower="both")
    _refused(single_client, "shower", **BASE, event_number=0, frame="trans", shower="both")
    _refused(single_client, "shower", **BASE, event_number=0, shower="c")
    _refused(single_client, "frame", **BASE, event_number=0, frame="detector")
    _refused(single_client, "channel", **BASE, event_number=0, channel="density")
    _refused(single_client, "model", **BASE, event_number=0, channel="gradcam", model="gnn")
    _refused(single_client, "coordinates", **BASE, event_number=0, coordinates="guess")
    bad = single_client.get(ROUTE, params={**BASE, "event_number": 0, "format": "mesh"})
    assert bad.status_code == 422 and bad.json()["field"] == "format"
    assert single_client.get(ROUTE, params={**VOX, **BASE, "event_number": 10**6}).status_code == 404


def test_network_channels_follow_the_vox_attention_gate(single_client):
    """The route serves the network channels exactly where the catalogue's vox-attention gate is open."""
    with _con(single_client) as con:
        record = _record(con, BASELINE_TABLE)
    assert capabilities.of(record).can("vox-attention")
    assert set(voxel_event.NETWORK_CHANNELS) <= set(voxel_event.channels_offered(record))
    # Networks and a lattice but no measured frame extents: the event cubes need only the
    # lattice, so vox-attention stays open and the lab cubes carry every network channel,
    # while the ensemble (which needs the extents) is shut.
    unbounded = dataclasses.replace(record, frame_bounds=None)
    caps = capabilities.of(unbounded)
    assert caps.can("vox-event") and not caps.can("vox-ensemble") and caps.can("vox-attention")
    assert set(voxel_event.NETWORK_CHANNELS) <= set(voxel_event.channels_offered(unbounded))
    for channel in voxel_event.NETWORK_CHANNELS:
        voxel_event.resolve(unbounded, "lab", None, channel, "segmentation")
    # No networks at all: the gate is shut and the route refuses every network channel.
    with _con(single_client) as con:
        networkless = _record(con, SINGLE_HITS_TABLE)
    assert not capabilities.of(networkless).can("vox-attention")
    assert voxel_event.channels_offered(networkless) == ("energy", "species")
    for channel in voxel_event.NETWORK_CHANNELS:
        with pytest.raises(CapabilityError) as refused:
            voxel_event.resolve(networkless, "lab", None, channel, "segmentation")
        assert refused.value.extra["field"] == "channel"
        assert refused.value.extra["capability"] == "vox-attention"


def test_the_contract_refuses_what_the_frontend_cannot_place_or_colour(single_client):
    """Each regression the reviewer's mutations slipped past the old contract is now a violation."""
    lab = _served(single_client, **BASE, event_number=0, frame="lab")
    shap = _served(single_client, **BASE, event_number=0, frame="lab", channel="shapcam")
    grad = _served(single_client, **BASE, event_number=0, frame="lab", channel="gradcam")
    local = _served(single_client, **BASE, event_number=0, shower="a")
    dframe = _served(single_client, **BASE, event_number=0, frame="canonical")
    species = _served(single_client, **HITS, event_number=_first_species_event(single_client), frame="lab",
                      channel="species")

    def refused(body, mutate):
        copy = json.loads(json.dumps(body))
        mutate(copy)
        with pytest.raises(contract_check.ContractError):
            contract_check.check(copy, "event_voxels")

    def pop(*path):
        def go(body):
            node = body
            for key in path[:-1]:
                node = node[key]
            node.pop(path[-1])
        return go

    def put(value, *path):
        def go(body):
            node = body
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
        return go

    cases = [
        # Ramp bounds.
        (shap, pop("voxels", "scale", "vmin")), (shap, pop("voxels", "scale", "vmax")),
        (shap, pop("voxels", "scale", "zero_code")), (shap, put(False, "voxels", "scale", "diverging")),
        (grad, put(True, "voxels", "scale", "diverging")), (grad, pop("voxels", "scale", "vmax")),
        (lab, pop("voxels", "scale", "vmin")), (lab, pop("voxels", "scale", "vmax")),
        (lab, pop("voxels", "scale", "floor_density")), (lab, pop("voxels", "scale", "degenerate")),
        (lab, pop("voxels", "scale", "floor_basis")), (species, pop("voxels", "scale", "codes")),
        # Placement fields of each regime.
        (local, put(None, "voxels", "geometry", "grid")), (local, put(None, "voxels", "geometry", "splat")),
        (local, put(dframe["voxels"]["geometry"], "voxels", "geometry")),
        (dframe, put(None, "voxels", "geometry", "axes")), (dframe, put(None, "voxels", "geometry", "grid")),
        (lab, put(None, "voxels", "geometry", "axes")), (lab, put(local["voxels"]["geometry"]["grid"],
                                                                 "voxels", "geometry", "grid")),
        (lab, pop("voxels", "geometry", "axes", "y")),
        (lab, put("subdeposit_splat", "voxels", "regime")),
        # Meta.
        (lab, put({}, "meta")), (lab, pop("meta", "notices")), (lab, pop("meta", "warnings")),
        (lab, put([{"scope": "elsewhere", "text": "x"}], "meta", "notices")),
        (lab, put([{"scope": "event"}], "meta", "notices")), (lab, pop("meta", "cam")),
        (shap, put({"model": "energy"}, "meta", "cam")), (lab, pop("meta", "model")),
        # Indices and widths.
        (lab, put(10 ** 6, "voxels", "topk", 0, "i")), (lab, put("u16le", "voxels", "cubes", "dtype", "code")),
        (lab, put("u16le", "voxels", "cubes", "dtype", "flags")), (lab, put("u32", "voxels", "cubes", "dtype", "ix")),
        # Raw hits under any name, at any depth.
        (lab, put([], "hits")), (lab, put([], "voxels", "points")), (lab, put([], "voxels", "geometry", "hits")),
        (lab, put([], "voxels", "scale", "points")), (lab, put([], "event", "hits")),
        (lab, put([], "event", "showers", 0, "points")), (lab, put([], "meta", "hits")),
        (dframe, put([], "event", "d_frame", "hits")), (species, put([], "voxels", "species", "points")),
        (species, put([], "voxels", "species", "legend", 0, "hits")),
        (lab, put([], "voxels", "cap", "hits")), (lab, put([], "window", "points")),
    ]
    for body, mutate in cases:
        refused(body, mutate)
    # And the unmutated bodies all pass.
    for body in (lab, shap, grad, local, dframe, species):
        contract_check.check(body, "event_voxels")


def _first_species_event(single_client) -> int:
    with _con(single_client) as con:
        return [e for e in _events(con, SINGLE_HITS_TABLE) if e % 4 == 0][0]


def test_single_shower_refusals_name_the_field_and_capability(single_client):
    with _con(single_client) as con:
        event = _events(con, SINGLE_HITS_TABLE)[0]
    problem = _refused(single_client, "frame", "frame-canonical", **HITS, event_number=event,
                       frame="canonical")
    assert "two showers" in problem["reason"]
    for channel in ("gradcam", "shapcam", "segerr"):
        problem = _refused(single_client, "channel", "vox-attention", **HITS, event_number=event,
                           channel=channel)
        assert "network" in problem["reason"]
    for shower in ("b", "both"):
        _refused(single_client, "shower", "shower", **HITS, event_number=event, frame="lab", shower=shower)
    # The aggregate has no hits: both formats are refused before anything else.
    for fmt in ("voxels", "raster"):
        response = single_client.get(ROUTE, params={**EVENTS, "event_number": event, "format": fmt})
        assert response.status_code == 422
        problem = response.json()
        contract_check.check(problem, "capability_problem")
        assert problem["field"] == "table_name" and "no hits" in problem["reason"]
        assert problem["capability"] == ("vox-event" if fmt == "voxels" else "event-inspector")


# ------------------------------------------------------------ one shower --


def _species_rows(con, event: int) -> dict:
    proj = quote(naming.proj_table(SINGLE_HITS_TABLE))
    data = con.execute(
        f"SELECT ix, iy, iz, energy, particle_type, is_secondary, parent_type, daughter_type "
        f"FROM {proj} WHERE event_number = ?", [event]).fetchnumpy()
    return {k: (list(np.ma.asarray(v).filled(None)) if v.dtype == object else np.asarray(v))
            for k, v in data.items()}


def test_the_single_shower_default_is_local_energy_of_its_one_shower(single_client):
    with _con(single_client) as con:
        event = _events(con, SINGLE_HITS_TABLE)[3]
        rows = _rows(con, SINGLE_HITS_TABLE, event)
    body = _served(single_client, **HITS, event_number=event)
    vox = body["voxels"]
    assert body["meta"]["shower"] == "a" and vox["frame"] == "local" and vox["channel"] == "energy"
    assert body["event"]["shower"]["label"] == "Shower" and body["event"]["d"] is None
    assert vox["cubes"]["shower_codes"][0] == "Shower"
    cap = vox["cap"]
    assert cap["energy_drawn_gev"] + cap["energy_beyond_gev"] + cap["energy_outside_window_gev"] \
        == pytest.approx(float(rows["energy"].sum()), rel=1e-9)
    assert body["event"]["n_primary_cells"] >= 0 and "primary_species" in body["event"]


def test_the_species_legend_and_primary_flag_in_the_lab(single_client):
    with _con(single_client) as con:
        events = _events(con, SINGLE_HITS_TABLE)
        # Two events with a primary-tagged row (every fourth event carries one).
        tagged = [e for e in events if e % 4 == 0][:2]
        checked = 0
        for event in tagged:
            rows = _species_rows(con, event)
            body = _served(single_client, **HITS, event_number=event, frame="lab", channel="species")
            vox = body["voxels"]
            species = vox["species"]
            names = {e["name"] for e in species["legend"]}
            members = {m["name"] for e in species["legend"] for m in e.get("members", [])}
            present = {n if n is not None else voxel_event.MISSING_SPECIES for n in rows["particle_type"]}
            for name in present:
                assert name in names or name in members, name
            cubes = _cubes(body)
            primary = (cubes["flags"] & voxel_event.FLAG_PRIMARY) > 0
            assert int(primary.sum()) == int((np.asarray(rows["is_secondary"]) == 0).sum())
            assert body["event"]["n_primary_cells"] == int(primary.sum())
            assert sum(e["cells"] for e in species["legend"]) == body["event"]["n_cells"]
            assert sum(e["cubes"] for e in species["legend"]) == vox["cubes"]["n"]
            assert sum(e["energy_fraction"] for e in species["legend"]) == pytest.approx(1.0)
            # Stable codes: each cube's code is its cell's particle_type's global code.
            axes = vox["geometry"]["axes"]
            by_cell = {(int(x), int(y), int(z)): voxel_event.species_code(n)
                       for x, y, z, n in zip(rows["ix"], rows["iy"], rows["iz"], rows["particle_type"])}
            for x, y, z, code in zip(cubes["ix"], cubes["iy"], cubes["iz"], cubes["code"]):
                key = (int(x) + axes["x"]["i0"], int(y) + axes["y"]["i0"], int(z) + axes["z"]["i0"])
                assert code == by_cell[key]
            assert vox["scale"]["scale"] == "categorical" and vox["scale"]["codes"][0]["name"] == "e-"
            # Per-cell parent and daughters, by dictionary code.
            parents = _decode(species["parent"], "u8")
            counts = _decode(species["n_daughters"], "u8")
            assert parents.size == counts.size == vox["cubes"]["n"]
            assert all(p == 255 or p < len(species["parents"]) for p in parents)
            assert species["purity"] is None
            assert body["event"]["primary_species"] == "e-"
            checked += 1
    assert checked == 2


def test_species_in_a_splat_frame_take_the_dominant_energy(single_client):
    with _con(single_client) as con:
        event = [e for e in _events(con, SINGLE_HITS_TABLE) if e % 4 == 0][0]
        rows = _species_rows(con, event)
    body = _served(single_client, **HITS, event_number=event, channel="species")
    species = body["voxels"]["species"]
    assert species["parent"] is None and species["n_daughters"] is None and species["parents"] == []
    assert "most energy" in species["rule"]
    flags = _cubes(body)["flags"]
    # The primary-tagged cell's energy lands in at least one voxel.
    assert ((flags & voxel_event.FLAG_PRIMARY) > 0).any() == bool((np.asarray(rows["is_secondary"]) == 0).any())
    if species["purity"] is not None:
        purity = _decode(species["purity"], "u8")
        assert purity.size == body["voxels"]["cubes"]["n"] and (purity <= 255).all()


def test_an_event_without_a_primary_tag_says_primary_hit_missing(single_client):
    with _con(single_client) as con:
        event = [e for e in _events(con, SINGLE_HITS_TABLE) if e % 4 == 1][0]
    body = _served(single_client, **HITS, event_number=event, frame="trans", channel="species")
    assert body["event"]["primary_species"] is None
    assert body["event"]["primary_note"].startswith("primary hit missing")


def test_species_codes_agree_across_events(single_client):
    with _con(single_client) as con:
        events = _events(con, SINGLE_HITS_TABLE)[:2]
    legends = [
        {e["name"]: e["code"] for e in
         _served(single_client, **HITS, event_number=event, frame="lab", channel="species")["voxels"]["species"]["legend"]}
        for event in events
    ]
    for name in set(legends[0]) & set(legends[1]):
        assert legends[0][name] == legends[1][name]
    for legend in legends:
        for name, code in legend.items():
            assert voxel_event.SPECIES_NAMES[code] == name


# ------------------------------------------------------------- pick rules --


def test_densest_pick_is_the_argmax_of_cells(single_client):
    for params in (HITS, BASE):
        response = single_client.get("/api/event/pick", params={**params, "rule": "densest"})
        assert response.status_code == 200
        body = response.json()
        contract_check.check(body, "event_voxels", at="pick")
        table = params["table_name"]
        with _con(single_client) as con:
            gate = "d IS NOT NULL" if table == BASELINE_TABLE else \
                "theta_a IS NOT NULL AND phi_a IS NOT NULL AND p0ax IS NOT NULL"
            expected = [int(r[0]) for r in con.execute(
                f"SELECT event_number FROM {quote(naming.event_table(table))} WHERE {gate} "
                "ORDER BY n_cells DESC, event_number ASC LIMIT 20").fetchall()]
            (cells,) = con.execute(
                f"SELECT max(n_cells) FROM {quote(naming.event_table(table))} WHERE {gate}").fetchone()
        assert body["pool"] == expected and body["event_number"] == expected[0]
        assert body["rule_id"] == "densest" and body["seed_used"] is False and body["n_cells"] == cells
        assert "not used" in body["rule"] and "most detector cells" in body["rule"]
        if table == SINGLE_HITS_TABLE:
            assert "separation" not in body["rule"]


def test_tilted_pick_by_name_carries_its_rule_id(single_client):
    named = single_client.get("/api/event/pick", params={**HITS, "rule": "tilted", "seed": 7}).json()
    bare = single_client.get("/api/event/pick", params={**HITS, "seed": 7}).json()
    contract_check.check(named, "event_voxels", at="pick")
    assert named["rule_id"] == "tilted" and named["seed_used"] is True
    assert "rule_id" not in bare and "seed_used" not in bare
    assert named["pool"] == bare["pool"] and named["event_number"] == bare["event_number"]
    bad = single_client.get("/api/event/pick", params={**HITS, "rule": "brightest"})
    assert bad.status_code == 422 and bad.json()["field"] == "rule"
