"""One event, one shower, three frames: the reference notebook's comparison figure.

``local-coords.ipynb`` (cell 6) draws one event nine times - the original
detector coordinates, the translated-only coordinates and the local
(translated and rotated) ones, each as X-Y, X-Z and Y-Z - with the incident
direction forward and extrapolated backward, the first-layer plane, the
shower's origin and the angle between the cloud's principal axis and the
local depth axis. This module builds that figure for one shower of one event
from the database, as server-rendered rasters rather than a scatter: the
frontend never receives hit rows, and a cell is a footprint, not a point.

**The three frames** are the service's own (``grid/frame.py``): the
laboratory lattice, the per-shower translated frame (``p - P0``) and the
per-shower local frame (``R(theta, phi) (p - P0)``), applied here in NumPy
to the event's cells by the same ``Se3`` the ensemble scans apply in SQL. The
file's own ``*_trans`` / ``*_local`` columns are read beside them and the
largest difference reported, as every per-shower response reports it.

**What a panel holds.** The laboratory panels are the native lattice, one bin
per cell, cropped to the event's window; the translated panels integrate each
cell's footprint by exact box overlap on a 20 mm grid; the local panels split
each cell into ``k x k x k_z`` sub-deposits rotated with the shower (the
gap-free ``k``, ``k_z = 2``), on a 20 mm grid with depth at the layer pitch.
Every panel is the projected energy *surface density* in GeV per mm² - the
cell's energy over its own area on the lattice, a bin's over its area on the
grids - so the nine panels share one colour ramp honestly, as the notebook's
one ``LogNorm`` does: the floor is the 1st percentile of the event's positive
cell densities (the notebook's ``vmin``), the top its brightest bin, both
stated. Unlike the ensemble panels, every panel projects the *whole* depth,
as the notebook's do; no entrance slab is cut.

**The window** is the notebook's: one half-width for all nine panels, ``1.15
x`` half the largest extent of the cloud over the six coordinates, never
below 150 mm, so the tilt reads at its true angle; depth is cropped the same
way, which the ensemble frames never do and the inspector says it does. The
window is what the axes span. The raster under it covers only the populated
part - the cells inside the window, the grid bins the splat can reach, the
layers the detector has - so a stray cell three metres away costs the window
but not the payload: everything between the raster and the window edge is
empty by construction and is drawn as the card.

**Marks** travel as three-dimensional lines and points in each frame's own
coordinates, and the client projects them onto each panel: the incident
direction from the origin (forward, and backward as "extrapolated"), the
first-layer plane - ``z = z0`` in the laboratory, ``delta z = 0`` translated,
and the tilted line ``z' = tan(theta) x'`` on the local X'Z' panel, which is
where the plane ``z = z0`` lands - and the origin itself.

**Payload.** Nine quantised rasters plus the marks. The grids start at 20 mm
and are coarsened by doubling, and disclosed, until the whole response fits
the 100 KB contract; the lattice panels have no coarser form and are served
as measured.

**One shower per event.** A single-shower experiment's event has one shower,
stored under the shower-A names: ``shower=b`` is refused naming the parameter,
the event block's second momentum, separation and overlap class are null, and
the pick rule ranks events by that shower's own polar angle.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode import matrix as matrix_encode
from ..encode import scale as scale_mod
from ..errors import NotFoundError, ValidationError
from ..grid import footprint as footprint_mod
from ..grid import frame as frame_mod
from ..grid.frame import KIND_LOCAL, KIND_TRANS
from ..stats import shape
from ..text import typographic
from . import capabilities, density, frame_sql, shower_frames
from . import showers as showers_mod
from .filters import FilterSpec

#: The notebook's window rule: margin multiplier and smallest half-width.
WINDOW_PAD = 1.15
WINDOW_MIN_HALF_MM = 150.0

#: The notebook's colour floor: this percentile of the event's positive cell densities.
FLOOR_PERCENTILE = 1.0

#: Accumulation pitch the grids start at, and the coarsest the budget may go to.
START_PITCH_MM = frame_mod.CANONICAL_PITCH_MM
MAX_PITCH_MM = 160.0

#: Bins per grid panel axis above which the pitch is doubled before encoding.
MAX_BINS_PER_AXIS = 96

#: The frames of the figure, in the notebook's order.
FRAMES: tuple[str, ...] = ("lab", KIND_TRANS, KIND_LOCAL)

#: Panels in the notebook's order: X-Y, X-Z, Y-Z (depth on the column axis).
PANELS: tuple[str, ...] = ("xy", "xz", "yz")
_PANEL_AXES = {"xy": ("y", "x"), "xz": ("x", "z"), "yz": ("y", "z")}

SYMBOLS = {
    "lab": {"x": "x", "y": "y", "z": "z"},
    KIND_TRANS: shower_frames.SYMBOLS[KIND_TRANS],
    KIND_LOCAL: shower_frames.SYMBOLS[KIND_LOCAL],
}

TITLES = {
    "lab": "Original — detector coordinates (x, y, z)",
    KIND_TRANS: "Translated only — origin shifted to P₀, not rotated (Δx, Δy, Δz)",
    KIND_LOCAL: "Local — translated and rotated by R(θ, φ) (u, v, w)",
}

SHOWERS = {"a": "A", "b": "B"}

UNIT = "GeV/mm^2"


@dataclass
class ShowerRows:
    """One shower's cells of one event, in every frame."""

    lab: np.ndarray        # (n, 3) laboratory positions
    ix: np.ndarray
    iy: np.ndarray
    iz: np.ndarray
    energy: np.ndarray
    file_trans: np.ndarray  # (n, 3): x_trans, y_trans, kt * pitch
    file_local: np.ndarray  # (n, 3)
    kt: np.ndarray

    @property
    def n(self) -> int:
        return int(self.energy.size)


#: The event-table fields the figure reads, and those only a two-shower event has.
_EVENT_FIELDS: tuple[str, ...] = (
    "event_number", "e1", "e2", "d", "ovl", "n_hits", "n_a_rows", "n_b_rows", "n_ab_rows",
    "theta_a", "phi_a", "theta_b", "phi_b", "p0ax", "p0ay", "p0az", "p0bx", "p0by", "p0bz",
)
_TWO_SHOWER_FIELDS: frozenset[str] = frozenset({
    "e2", "d", "ovl", "n_b_rows", "n_ab_rows", "theta_b", "phi_b", "p0bx", "p0by", "p0bz",
})


def _event_row(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, event_number: int) -> dict[str, Any]:
    """The event's fields; a single-shower event has no B, D or E2 column and reads them as null."""
    table = quote(naming.event_table(record.table_name))
    two = len(showers_mod.of(record)) == 2
    present = [name for name in _EVENT_FIELDS if two or name not in _TWO_SHOWER_FIELDS]
    cursor = con.execute(
        f"SELECT {', '.join(present)} FROM {table} WHERE event_number = ?", [int(event_number)],
    )
    names = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    if row is None:
        raise NotFoundError(f"No event {event_number} in experiment {record.table_name!r}.")
    fields = {name: None for name in _EVENT_FIELDS}
    fields.update(zip(names, row))
    return fields


def _rows(con, record, event_number: int, shower: str, pitch: float) -> ShowerRows:
    proj = quote(naming.proj_table(record.table_name))
    origin = "org = 0" if shower == "a" else "org IN (1, 2)"
    columns = con.execute(
        f"""SELECT ix, iy, iz, xt, yt, kt, xl, yl, zl, energy FROM {proj}
            WHERE event_number = ? AND {origin} ORDER BY iz, iy, ix""", [int(event_number)],
    ).fetchnumpy()
    lat = record.lattice
    ix = np.asarray(columns["ix"], dtype=np.int64)
    iy = np.asarray(columns["iy"], dtype=np.int64)
    iz = np.asarray(columns["iz"], dtype=np.int64)
    kt = np.asarray(columns["kt"], dtype=np.int64)
    lab = np.column_stack([lat.x.coords[ix], lat.y.coords[iy], lat.z.coords[iz]]) if ix.size \
        else np.zeros((0, 3))
    f = lambda name: np.asarray(columns[name], dtype=np.float64)  # noqa: E731
    return ShowerRows(
        lab=lab, ix=ix, iy=iy, iz=iz, energy=f("energy"),
        file_trans=np.column_stack([f("xt"), f("yt"), kt * pitch]) if ix.size else np.zeros((0, 3)),
        file_local=np.column_stack([f("xl"), f("yl"), f("zl")]) if ix.size else np.zeros((0, 3)),
        kt=kt,
    )


def _neighbours(con, record, spec: FilterSpec, event_number: int) -> tuple[bool, int | None, int | None]:
    """Whether the event is in the selection, and its neighbours within it."""
    table = quote(naming.event_table(record.table_name))
    params = {**spec.params(), "ev": int(event_number)}
    where = spec.where_sql()
    row = con.execute(
        f"""SELECT count(*) FILTER (WHERE event_number = $ev),
                   max(event_number) FILTER (WHERE event_number < $ev),
                   min(event_number) FILTER (WHERE event_number > $ev)
            FROM {table} WHERE {where}""", params,
    ).fetchone()
    return bool(row[0]), (int(row[1]) if row[1] is not None else None), (int(row[2]) if row[2] is not None else None)


def pick(con, record, spec: FilterSpec, seed: int = 42, pool_size: int = 20) -> dict[str, Any]:
    """The notebook's ``_select_events``: a seeded draw from the densest, most tilted events.

    Events of the selection with more hits than the selection's mean, the
    ``pool_size`` of them with the largest incident polar angle (the larger of
    the two showers' here), and one drawn at random with ``seed``. The events
    are those the per-shower frames can place (``capabilities.frame_gate``):
    a defined separation for two showers; an incident direction and an entry
    point for a single shower, ranked by its own polar angle.
    """
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    params = spec.params()
    showers = showers_mod.of(record)
    two = len(showers) == 2
    gate = capabilities.frame_gate(record)
    angle = f"greatest({', '.join(s.theta for s in showers)})" if two else showers[0].theta
    mean_hits, n = con.execute(
        f"SELECT avg(n_hits), count(*) FROM {table} WHERE {where} AND {gate}", params,
    ).fetchone()
    if not n:
        raise NotFoundError(
            "The selection holds no event with a defined separation to pick from." if two else
            "The selection holds no event with an incident direction and an entry point to pick from."
        )
    rows = con.execute(
        f"""SELECT event_number FROM {table}
            WHERE {where} AND {gate} AND n_hits > $mean
            ORDER BY {angle} DESC, event_number LIMIT {int(pool_size)}""",
        {**params, "mean": float(mean_hits)},
    ).fetchall()
    pool = [int(r[0]) for r in rows]
    if not pool:
        rows = con.execute(
            f"SELECT event_number FROM {table} WHERE {where} AND {gate} "
            f"ORDER BY n_hits DESC, event_number LIMIT {int(pool_size)}", params).fetchall()
        pool = [int(r[0]) for r in rows]
    rng = np.random.default_rng(int(seed))
    chosen = int(rng.choice(np.asarray(pool)))
    if two:
        rule = (
            f"Among the {n:,} selected events with a defined separation, those with more hits "
            f"than the mean ({float(mean_hits):.1f}); of those the {len(pool)} with the largest "
            "incident polar angle (the larger of the two showers'); one drawn at random with "
            f"seed {int(seed)} - the reference notebook's selection rule."
        )
    else:
        rule = (
            f"Among the {n:,} selected events with an incident direction and an entry point, those "
            f"with more hits than the mean ({float(mean_hits):.1f}); of those the {len(pool)} with "
            f"the largest incident polar angle; one drawn at random with seed {int(seed)} - the "
            "reference notebook's selection rule."
        )
    return {
        "event_number": chosen,
        "pool": pool,
        "pool_size": int(pool_size),
        "mean_hits": float(mean_hits),
        "n_events": int(n),
        "seed": int(seed),
        "rule": rule,
    }


# ---------------------------------------------------------------- windows --


def _window_half(coords: list[np.ndarray], local_xy: np.ndarray) -> float:
    """The notebook's one half-width for all nine panels."""
    half = 0.5 * max(float(np.ptp(c)) if c.size else 0.0 for c in coords)
    if local_xy.size:
        half = max(half, float(np.abs(local_xy).max()))
    return max(half * WINDOW_PAD, WINDOW_MIN_HALF_MM)


def _mid(values: np.ndarray) -> float:
    return 0.5 * (float(values.max()) + float(values.min())) if values.size else 0.0


def _lattice_crop(coords: np.ndarray, index: np.ndarray, lo: float, hi: float) -> tuple[int, int]:
    """Index range ``[i0, i1)`` of the populated cells whose centres lie in ``[lo, hi]``.

    Tight on the populated cells inside the window, so the raster never
    carries empty rows of cells; at least one cell, the nearest to the window
    centre, when none is populated inside it.
    """
    inside = (coords[index] >= lo) & (coords[index] <= hi) if index.size else np.zeros(0, dtype=bool)
    if inside.any():
        return int(index[inside].min()), int(index[inside].max()) + 1
    nearest = int(np.clip(np.searchsorted(coords, 0.5 * (lo + hi)), 0, coords.size - 1))
    return nearest, nearest + 1


def _grid_edges(lo: float, hi: float, pitch: float, data_lo: float, data_hi: float, margin: float) -> np.ndarray:
    """Uniform edges of pitch ``pitch``, aligned on multiples of the pitch, over the populated part of a window.

    The window ``[lo, hi]`` bounds the raster; within it the raster covers the
    data's own extent plus ``margin`` (a footprint, so every box or rotated
    sub-deposit of a cell inside the extent lands on the raster).
    """
    a = max(lo, data_lo - margin)
    b = min(hi, data_hi + margin)
    if not b > a:
        a, b = lo, hi
    a = math.floor(a / pitch - 1e-9) * pitch
    b = math.ceil(b / pitch + 1e-9) * pitch
    n = max(1, int(round((b - a) / pitch)))
    return a + pitch * np.arange(n + 1, dtype=np.float64)


# ---------------------------------------------------------- accumulation --


def _lab_panels(rows: ShowerRows, record: ExperimentRecord, windows: dict[str, tuple[float, float]]):
    """Native-lattice crops: energy per cell, projected over the whole depth."""
    lat = record.lattice
    index = {"x": rows.ix, "y": rows.iy, "z": rows.iz}
    crops = {}
    for axis in "xyz":
        a = lat.axis(axis)
        i0, i1 = _lattice_crop(a.coords, index[axis], *windows[axis])
        crops[axis] = (i0, i1, a.edges[i0:i1 + 1])
    inside = np.ones(rows.n, dtype=bool)
    for axis in "xyz":
        i0, i1, _ = crops[axis]
        inside &= (index[axis] >= i0) & (index[axis] < i1)
    panels = {}
    for name in PANELS:
        row_axis, col_axis = _PANEL_AXES[name]
        r0, r1, r_edges = crops[row_axis]
        c0, c1, c_edges = crops[col_axis]
        matrix = np.zeros((r1 - r0, c1 - c0))
        if inside.any():
            np.add.at(matrix, (index[row_axis][inside] - r0, index[col_axis][inside] - c0), rows.energy[inside])
        panels[name] = (matrix, r_edges, c_edges, float(rows.energy[~inside].sum()))
    extents = {axis: [float(crops[axis][2][0]), float(crops[axis][2][-1])] for axis in "xyz"}
    return panels, extents


def _trans_panels(xyz: np.ndarray, energy: np.ndarray, footprint, pitch_z: float,
                  windows: dict[str, tuple[float, float]], pitch: float, n_layers: int):
    """Exact box overlap on a uniform grid; depth is the shower's own layers."""
    wx, wy = footprint
    margin = max(wx, wy)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    x_edges = _grid_edges(*windows["x"], pitch, float(x.min()), float(x.max()), margin)
    y_edges = _grid_edges(*windows["y"], pitch, float(y.min()), float(y.max()), margin)
    # Own-shower layers inside the depth window and the detector, edges half a pitch either side.
    layer = np.rint(z / pitch_z).astype(np.int64)
    k0 = max(0, int(math.floor(windows["z"][0] / pitch_z + 0.5)), int(layer.min()))
    k1 = min(int(n_layers), int(math.ceil(windows["z"][1] / pitch_z + 0.5)), int(layer.max()) + 1)
    k1 = max(k0 + 1, k1)
    z_edges = (np.arange(k0, k1 + 1, dtype=np.float64) - 0.5) * pitch_z
    inside = ((x - wx / 2 >= x_edges[0]) & (x + wx / 2 <= x_edges[-1])
              & (y - wy / 2 >= y_edges[0]) & (y + wy / 2 <= y_edges[-1])
              & (layer >= k0) & (layer < k1))
    ox = footprint_mod.box_overlap_1d(x, energy, wx, x_edges, inside)
    oy = footprint_mod.box_overlap_1d(y, energy, wy, y_edges, inside)
    xy = np.einsum("h,hy,hx->yx", energy, oy, ox)
    xz = np.zeros((x_edges.size - 1, k1 - k0))
    yz = np.zeros((y_edges.size - 1, k1 - k0))
    if inside.any():
        cols = layer[inside] - k0
        np.add.at(xz.T, cols, energy[inside, None] * ox[inside])
        np.add.at(yz.T, cols, energy[inside, None] * oy[inside])
    outside = float(energy[~inside].sum())
    return {
        "xy": (xy, y_edges, x_edges, outside),
        "xz": (xz, x_edges, z_edges, outside),
        "yz": (yz, y_edges, z_edges, outside),
    }, {"x": [float(x_edges[0]), float(x_edges[-1])], "y": [float(y_edges[0]), float(y_edges[-1])],
        "z": [float(z_edges[0]), float(z_edges[-1])]}


def _local_panels(xyz: np.ndarray, energy: np.ndarray, rotation: np.ndarray, footprint, pitch_z: float,
                  windows: dict[str, tuple[float, float]], pitch: float, k: int, k_z: int):
    """Rotated sub-deposits binned on a uniform grid, depth at the layer pitch."""
    margin = max(footprint[0], footprint[1], pitch_z)
    x_edges = _grid_edges(*windows["x"], pitch, float(xyz[:, 0].min()), float(xyz[:, 0].max()), margin)
    y_edges = _grid_edges(*windows["y"], pitch, float(xyz[:, 1].min()), float(xyz[:, 1].max()), margin)
    z_edges = _grid_edges(*windows["z"], pitch_z, float(xyz[:, 2].min()), float(xyz[:, 2].max()), margin)
    points, weights = footprint_mod.rotated_subdeposits(
        xyz, rotation, energy, (footprint[0], footprint[1], pitch_z), k, k_z)
    cube, outside = footprint_mod.bin_uniform(points, weights, (x_edges, y_edges, z_edges))
    return {
        "xy": (cube.sum(axis=2).T, y_edges, x_edges, outside),
        "xz": (cube.sum(axis=1), x_edges, z_edges, outside),
        "yz": (cube.sum(axis=0), y_edges, z_edges, outside),
    }, {"x": [float(x_edges[0]), float(x_edges[-1])], "y": [float(y_edges[0]), float(y_edges[-1])],
        "z": [float(z_edges[0]), float(z_edges[-1])]}


# ---------------------------------------------------------------- marks --


def _marks(kind: str, origin: np.ndarray, direction: np.ndarray, theta: float, z0: float) -> list[dict[str, Any]]:
    """The notebook's overlays, as 3-D lines and points in this frame's coordinates."""
    o = [float(v) for v in origin]
    d = [float(v) for v in direction]
    marks: list[dict[str, Any]] = [
        {"type": "line", "style": "forward", "origin": o, "direction": d, "panels": None,
         "name": "Incident direction (forward)",
         "tooltip": "Incident direction (forward) from the shower origin, along (θ, φ)"},
        {"type": "line", "style": "backward", "origin": o, "direction": [-v for v in d], "panels": None,
         "name": "Extrapolated backward",
         "tooltip": "Incident direction extrapolated backward, upstream of the origin"},
    ]
    if kind == KIND_LOCAL:
        # The plane z = z0 of the first layer maps to z' = tan(theta) x' for every y'.
        marks.append({"type": "line", "style": "plane", "origin": [0.0, 0.0, 0.0],
                      "direction": [1.0, 0.0, math.tan(theta)], "panels": ["xz"],
                      "name": "1st layer plane",
                      "tooltip": "The plane of the shower's first layer, z = z₀, which the rotation "
                                 "tilts to w = tan θ · u; it has no image on the other panels"})
    else:
        marks.append({"type": "plane", "style": "plane", "axis": "z", "at": float(z0), "panels": ["xz", "yz"],
                      "name": "1st layer plane (z = z₀)",
                      "tooltip": "The plane of the shower's first populated layer, z = z₀"})
    marks.append({"type": "point", "style": "origin", "at": o, "panels": None,
                  "name": "Shower origin (1st layer centre of mass)",
                  "tooltip": "Shower origin P₀: the energy-weighted centroid of the first populated layer"})
    return marks


# ------------------------------------------------------------- the figure --


def _encode(matrix: np.ndarray, r_edges: np.ndarray, c_edges: np.ndarray, name: str, native: bool,
            symbols: dict[str, str], floor: float, top: float, outside: float, total: float) -> dict[str, Any]:
    """One panel as an areal density on the shared ramp."""
    row_axis, col_axis = _PANEL_AXES[name]
    area = np.outer(np.diff(r_edges), np.diff(c_edges))
    dens = np.divide(matrix, area, out=np.zeros_like(matrix), where=area > 0)
    positive = dens[dens > 0]
    vmin = math.log10(floor) if floor > 0 else -9.0
    vmax = math.log10(top) if top > 0 else vmin + 1.0
    if not vmax > vmin:
        vmax = vmin + 1.0
    scale = scale_mod.ColorScale(
        scale=scale_mod.SCALE_LOG, vmin=vmin, vmax=vmax, unit=UNIT,
        mode=scale_mod.MODE_PERCENTILE, locked=True, global_vmax=float(top) if top > 0 else None,
        n_below=int((positive < floor).sum()) if positive.size else 0,
        n_above=int((positive > top).sum()) if positive.size else 0,
        n_empty=int(dens.size - positive.size),
    )
    payload = matrix_encode.encode_matrix(
        dens, scale, row_edges=r_edges, col_edges=c_edges, row_axis=row_axis, col_axis=col_axis,
        panel=name, native=native, symbols=symbols,
    )
    payload["total"] = float(matrix.sum())
    payload["total_energy_all_gev"] = float(total)
    payload["energy_outside_window_gev"] = float(outside)
    payload["energy_fraction_outside_window"] = round(outside / total, 8) if total > 0 else 0.0
    payload["kernel"] = "none"
    payload["n_events"] = 1
    payload["rho_unit"] = UNIT
    payload["rho_peak"] = float(dens.max()) if dens.size else 0.0
    payload["bin_area_mm2"] = [float(area.min()), float(area.max())] if area.size else [0.0, 0.0]
    return payload


def inspect(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    event_number: int,
    shower: str = "a",
    source: str = frame_sql.SOURCE_FILE,
    footprint: tuple[float, float] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """The nine-panel figure of one shower of one event, budgeted under the contract.

    ``shower`` must be one of the experiment's: ``b`` is refused (422,
    ``field=shower``) where there is one shower per event.
    """
    assert record.lattice is not None and record.frame_bounds is not None
    if shower not in SHOWERS:
        raise ValidationError(f"shower must be a or b; got {shower!r}.", field="shower")
    selected = showers_mod.of(record, shower)[0]
    two = len(showers_mod.of(record)) == 2
    if source not in frame_sql.SOURCES:
        raise ValidationError(f"coordinates must be one of {', '.join(frame_sql.SOURCES)}; got {source!r}.",
                              field="coordinates")
    started = time.perf_counter()
    limit = density.RESPONSE_LIMIT if limit is None else int(limit)
    lat = record.lattice
    pitch_z = float(record.frame_bounds.layer_pitch_mm)
    fp = footprint or frame_mod.footprint_from_lattice(lat)

    event = _event_row(con, record, event_number)
    in_selection, prev_event, next_event = _neighbours(con, record, spec, event_number)
    rows = _rows(con, record, event_number, shower, pitch_z)
    p0 = np.array([event[ddl.p0_column(shower, axis)] for axis in "xyz"], dtype=np.float64)
    theta, phi = event[selected.theta], event[selected.phi]
    # Two showers are told apart by letter; a single shower is named as such.
    label = SHOWERS[shower] if two else selected.label
    if rows.n == 0 or any(v is None for v in (theta, phi, *p0)):
        raise NotFoundError(
            f"Event {event_number} has no hit attributed to "
            + (f"shower {label}" if two else "its shower")
            + ("" if rows.n else ", so no entry point P0 and no frame") + "."
        )
    theta, phi = float(theta), float(phi)
    direction = frame_mod.unit_direction(theta, phi)
    rotation = frame_mod.rotation_matrix(theta, phi)

    # The two per-shower motions, applied here to the cells, and the file's columns beside them.
    translated = frame_mod.per_shower_translated(p0).apply(rows.lab)
    local = frame_mod.per_shower_local(p0, theta, phi).apply(rows.lab)
    residual = float(max(np.abs(translated - rows.file_trans).max(), np.abs(local - rows.file_local).max()))
    if source == frame_sql.SOURCE_FILE:
        trans_xyz, local_xyz = rows.file_trans, rows.file_local
    else:
        trans_xyz, local_xyz = translated, local

    # The notebook's window, from every coordinate of the cloud.
    half = _window_half([rows.lab[:, 0], rows.lab[:, 1], rows.lab[:, 2],
                         local_xyz[:, 0], local_xyz[:, 1], local_xyz[:, 2]], local_xyz[:, :2])
    windows = {
        "lab": {a: (_mid(rows.lab[:, i]) - half, _mid(rows.lab[:, i]) + half) for i, a in enumerate("xyz")},
        KIND_TRANS: {a: (_mid(trans_xyz[:, i]) - half, _mid(trans_xyz[:, i]) + half) for i, a in enumerate("xyz")},
        KIND_LOCAL: {"x": (-half, half), "y": (-half, half),
                     "z": (_mid(local_xyz[:, 2]) - half, _mid(local_xyz[:, 2]) + half)},
    }
    k = frame_mod.minimum_gapless_subsample(max(fp), START_PITCH_MM)
    k = max(frame_mod.MIN_SUBSAMPLE, min(frame_mod.MAX_SUBSAMPLE, k))
    k_z = frame_mod.LOCAL_K_Z
    tilt = shape.principal_axis(local_xyz, rows.energy)
    total = float(rows.energy.sum())

    lab_panels, lab_extent = _lab_panels(rows, record, windows["lab"])

    def build(pitch: float, notes: list[str]) -> dict[str, Any]:
        trans_panels, trans_extent = _trans_panels(trans_xyz, rows.energy, fp, pitch_z, windows[KIND_TRANS], pitch,
                                                   record.frame_bounds.n_layers_trans)
        local_panels, local_extent = _local_panels(local_xyz, rows.energy, rotation, fp, pitch_z,
                                                   windows[KIND_LOCAL], pitch, k, k_z)
        raw = {"lab": lab_panels, KIND_TRANS: trans_panels, KIND_LOCAL: local_panels}
        extents = {"lab": lab_extent, KIND_TRANS: trans_extent, KIND_LOCAL: local_extent}
        # One ramp for all nine: the notebook's floor on the lattice cells, the top over every bin.
        densities = []
        for name in PANELS:
            matrix, r_edges, c_edges, _ = lab_panels[name]
            area = np.outer(np.diff(r_edges), np.diff(c_edges))
            d = matrix[area > 0] / area[area > 0]
            densities.append(d[d > 0])
        lab_positive = np.concatenate(densities) if densities else np.zeros(0)
        floor = float(np.percentile(lab_positive, FLOOR_PERCENTILE)) if lab_positive.size else 0.0
        top = 0.0
        for kind in FRAMES:
            for name in PANELS:
                matrix, r_edges, c_edges, _ = raw[kind][name]
                area = np.outer(np.diff(r_edges), np.diff(c_edges))
                if matrix.size:
                    top = max(top, float((matrix / np.where(area > 0, area, 1.0)).max()))
        frames: dict[str, Any] = {}
        n_below = 0
        for kind in FRAMES:
            panels = {}
            for name in PANELS:
                matrix, r_edges, c_edges, outside = raw[kind][name]
                panels[name] = _encode(matrix, r_edges, c_edges, name, kind == "lab", SYMBOLS[kind],
                                       floor, top, outside, total)
                n_below += panels[name]["scale"]["clipped_low"]
            origin = p0 if kind == "lab" else np.zeros(3)
            frame_direction = direction if kind != KIND_LOCAL else np.array([0.0, 0.0, 1.0])
            frames[kind] = {
                "kind": kind,
                "title": TITLES[kind],
                "symbols": SYMBOLS[kind],
                # The axes span the window; the rasters cover `raster`, the populated part.
                "window": {axis: [float(v) for v in windows[kind][axis]] for axis in "xyz"},
                "raster": extents[kind],
                "half_mm": half,
                "panels": panels,
                # The first layer is z = z0 in the laboratory and delta z = 0 once P0 is subtracted.
                "marks": _marks(kind, origin, frame_direction, theta, 0.0 if kind == KIND_TRANS else float(p0[2])),
                "depth": (
                    {"policy": "native_layers", "pitch_mm": pitch_z, "note": "the detector's own sampling layers, cropped to the event"}
                    if kind == "lab" else
                    {"policy": "native_layers", "pitch_mm": pitch_z, "note": "the shower's own sampling layers counted from its first, cropped to the event"}
                    if kind == KIND_TRANS else
                    {"policy": "uniform_bins", "pitch_mm": pitch_z, "note": "uniform bins of the layer pitch along w, cropped to the event, never smoothed"}
                ),
                "splat": (
                    {"regime": "native_lattice", "pitch_mm": None}
                    if kind == "lab" else
                    {"regime": "box_overlap", "pitch_mm": pitch, "k": None, "k_z": None}
                    if kind == KIND_TRANS else
                    {"regime": "subdeposit3d", "pitch_mm": pitch, "k": k, "k_z": k_z}
                ),
            }
        return {
            "frames": frames,
            "scale": {
                "unit": UNIT, "floor": floor, "top": top, "vmin": frames["lab"]["panels"]["xy"]["scale"]["vmin"],
                "vmax": frames["lab"]["panels"]["xy"]["scale"]["vmax"],
                "floor_percentile": FLOOR_PERCENTILE, "n_below": n_below,
                # Exponents in the floor and the top take the typographic minus.
                "rule": typographic(
                    f"One logarithmic ramp for all nine panels: projected energy surface density in GeV per mm², "
                    f"from the {FLOOR_PERCENTILE:g}st percentile of this shower's positive lattice-cell densities "
                    f"({floor:.3g}) to its brightest bin ({top:.3g}); {n_below} bins below the floor are drawn at "
                    "the lowest colour."
                ),
            },
            "grid": {"pitch_mm": pitch, "notes": list(notes)},
        }

    notes: list[str] = []
    pitch = START_PITCH_MM
    # Coarsen up front when a wide window would make a grid panel enormous.
    while pitch < MAX_PITCH_MM and 2.0 * half / pitch > MAX_BINS_PER_AXIS:
        pitch *= 2.0
    if pitch > START_PITCH_MM:
        notes.append(f"The {START_PITCH_MM:.0f} mm accumulation grids were coarsened to {pitch:.0f} mm "
                     f"because the window ({half:.0f} mm half-width) would hold more than "
                     f"{MAX_BINS_PER_AXIS} bins per axis.")

    body = None
    for _attempt in range(6):
        body = build(pitch, notes)
        size = density.wire_size(body)
        if size < limit or pitch >= MAX_PITCH_MM:
            break
        notes.append(f"Grids coarsened from {pitch:.0f} mm to {2 * pitch:.0f} mm to keep the response under the "
                     f"{limit:,}-byte contract ({size:,} bytes at {pitch:.0f} mm); the lattice panels have no "
                     "coarser form and are served as measured.")
        pitch *= 2.0
    assert body is not None
    if size >= limit:
        # Out of coarser grids with the panels still over: the step notes above
        # say what was tried, and this one says it did not suffice.
        body["grid"]["notes"].append(
            f"The response is still {size:,} bytes at {pitch:.0f} mm and is served as it is.")

    momentum = event[selected.momentum]
    body.update({
        "event": {
            "event_number": int(event_number),
            "in_selection": in_selection,
            "prev": prev_event,
            "next": next_event,
            "n_hits": int(event["n_hits"] or 0),
            "d": event["d"],
            "e1": event["e1"],
            "e2": event["e2"],
            "overlap": event["ovl"],
            "shower": {
                "key": shower, "label": label, "n_hits": rows.n, "energy_gev": total,
                "momentum_gev": momentum,
                "theta": theta, "phi": phi,
                "theta_deg": math.degrees(theta), "phi_deg": math.degrees(phi),
                "p0": [float(v) for v in p0], "first_layer_z": float(p0[2]),
                "direction": [float(v) for v in direction],
                "principal_axis": tilt,
            },
        },
        "coordinates": {
            "source": source,
            "residual_max_mm": residual,
            "tolerance_mm": shower_frames.COORDINATE_TOLERANCE_MM,
            "within_tolerance": bool(residual <= shower_frames.COORDINATE_TOLERANCE_MM),
            "note": typographic(
                ("Coordinates: the file's own x/y_trans and x/y/z_local; " if source == frame_sql.SOURCE_FILE
                 else "Coordinates: recomputed from the laboratory lattice by the stated SE(3) motions; ")
                + "the motions (P₀ subtracted, then R(θ, φ) applied) were also applied to every cell here, and "
                f"the two differ by at most {residual:.3g} mm"
                + (" (within" if residual <= shower_frames.COORDINATE_TOLERANCE_MM else " (above")
                + f" the {shower_frames.COORDINATE_TOLERANCE_MM:g} mm tolerance)."
            ),
        },
        "window": {
            "half_mm": half, "pad": WINDOW_PAD, "min_half_mm": WINDOW_MIN_HALF_MM,
            "rule": (
                f"One half-width for all nine panels: {WINDOW_PAD:g} × half the largest extent of the cloud "
                f"over x, y, z, u, v and w, never below {WINDOW_MIN_HALF_MM:.0f} mm ({half:.0f} mm here); "
                "lattice panels snap it outward to whole cells, grid panels to whole bins; depth is cropped "
                "to the event, which the ensemble frames never do."
            ),
        },
        "footprint_mm": [float(fp[0]), float(fp[1]), pitch_z],
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
    })
    return body
