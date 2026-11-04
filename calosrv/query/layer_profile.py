"""The ``depth_layers`` block of ``/api/projections``, C7's reach and ``/api/event``'s ``layer_planes``.

Everything the interface needs to draw any partition of the depth layers into
layer groups ("Longitudinal Channels", ``grid/layer_groups.py``) without a
further request: which numbering the frame's depth axis takes, its native
edges as stored, the selection's exact energy per layer (and, for an
attention channel, the per-layer Σ E·CAM with Shap-CAM's signed parts apart),
and - where depth counts from each shower's own first layer - how many
showers reach each relative layer.

**Numbering per frame** (the brief's section 1):

* ``lab`` and ``canonical``: *detector* layers, the lattice ordinals 1 .. L.
  The D-frame's depth z′ = z − z_front is one shift for every event, so its
  layers are the detector's own.
* ``trans``: *relative* layers kt + 1, counted from each shower's own first
  populated layer.
* ``local``: *none*. Every shower's layers are tilted by its own (θ, φ), so
  the ensemble has no common layer grid along w; the profile is still given
  per relative layer, from the per-shower layer table.

**Reach.** A shower whose first populated layer is the physical layer ``s``
(0-based, ``round((p0z − z_lo) / p)``) has relative layers 0 .. L_phys − 1 − s
inside the detector, with ``L_phys = round((z_hi − z_lo) / p) + 1``. So the
number of the selection's showers that reach relative layer ``k`` is
``#{s ≤ L_phys − 1 − k}``: one SQL statement over the event table with the
selection's filters, grouped by ``s``.
"""

from __future__ import annotations

import math
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..grid import frame as frame_mod
from ..grid import layer_groups
from ..grid.layer_groups import PooledAxis
from ..text import typographic
from . import planes as planes_mod
from . import showers as showers_mod
from .filters import FilterSpec
from .hit_sql import layer_pitch

NUMBERING_DETECTOR = "detector"
NUMBERING_RELATIVE = "relative"
NUMBERING_NONE = "none"

#: The depth symbol each frame writes.
SYMBOLS = {"lab": "z", "canonical": "z′", "trans": "Δz", "local": "w"}

#: Significant figures of a shipped per-layer sum: ``profile.energy_gev``, the
#: ``profile.attention`` arrays and ``layer_planes.energy_gev`` (brief §9.1,
#: LG-C2). The interface prints a layer's share to 0.1 %, and four figures hold
#: each sum to 0.05 % of itself. The scalar totals (``total_gev``,
#: ``outside_gev``, ``attention.total`` …) keep full precision.
DIGITS = 4

#: Decimals of a shipped depth edge: 0.001 mm.
EDGE_DECIMALS = 3

#: The per-layer arrays of each ``profile.attention`` block, compacted with the energy.
_ATTENTION_ARRAYS = ("values", "positive", "negative")

#: ``depth_layers.trim_note`` when the guard yielded the layer block and the raster kept its plan.
TRIM_NOTE = (
    "The per-layer shares and reach were left out to keep this response under the 100 KB "
    "contract; the raster kept its resolution."
)
#: … and when the raster had to be coarsened as well.
TRIM_NOTE_COARSENED = (
    "The per-layer shares and reach were left out to keep this response under the 100 KB "
    "contract, and the raster was coarsened as well, as the resolution notices say."
)
#: ``layer_planes.trim_note`` of ``/api/event`` when the grids kept their pitch.
TRIM_NOTE_EVENT = (
    "The shower's per-layer energies were left out to keep this response under the 100 KB "
    "contract; the grids kept their pitch."
)
#: … and when the grids had to be coarsened as well.
TRIM_NOTE_EVENT_COARSENED = (
    "The shower's per-layer energies were left out to keep this response under the 100 KB "
    "contract, and the grids were coarsened as well, as the grid notes say."
)


def _sig(values: Any) -> list[float]:
    return [float(f"{float(v):.{DIGITS}g}") for v in np.asarray(values, dtype=np.float64)]


def _edges(values: Any) -> list[float]:
    return [round(float(v), EDGE_DECIMALS) + 0.0 for v in np.asarray(values, dtype=np.float64)]


def physical_layers(record: ExperimentRecord) -> int:
    """``L_phys`` of the experiment's lattice."""
    z = record.lattice.z
    return layer_groups.physical_layers(z.lo, z.hi, layer_pitch(record))


# ----------------------------------------------------------------- reach --


def reach(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    n_layers: int,
    showers: tuple[showers_mod.ShowerColumns, ...] | None = None,
) -> dict[str, Any] | None:
    """How many selected showers reach each of ``n_layers`` relative layers.

    ``counts[k] = #{showers with s ≤ L_phys − 1 − k}``, ``s`` the shower's
    first populated layer from its entry point P0 (``p0az`` / ``p0bz``; A only
    on single-shower kinds). A shower that deposited energy but has no entry
    point is counted in ``n_without_start`` and in no layer. ``None`` for an
    experiment without entry points (the aggregate).
    """
    if record.lattice is None:
        return None
    picked = tuple(showers if showers is not None else showers_mod.of(record))
    if not picked or not all(s.has_centroids for s in picked):
        return None
    pitch = layer_pitch(record)
    z = record.lattice.z
    l_phys = layer_groups.physical_layers(z.lo, z.hi, pitch)
    table = quote(naming.event_table(record.table_name))
    parts = []
    for s in picked:
        column = s.p0("z")
        parts.append(
            f"SELECT CAST(round((CAST({column} AS DOUBLE) - $lg_z_lo) / $lg_pitch) AS BIGINT) AS s "
            f"FROM {table} WHERE {spec.where_sql()} AND {s.present_sql}")
    rows = con.execute(
        f"SELECT s, count(*) FROM ({' UNION ALL '.join(parts)}) GROUP BY s",
        {**spec.params(), "lg_z_lo": float(z.lo), "lg_pitch": float(pitch)},
    ).fetchall()
    by_start: dict[int, int] = {}
    n_without = 0
    for start, count in rows:
        if start is None:
            n_without += int(count)
        else:
            by_start[int(start)] = by_start.get(int(start), 0) + int(count)
    n_showers = sum(by_start.values())
    starts = np.array(sorted(by_start), dtype=np.int64)
    cumulative = np.cumsum([by_start[int(v)] for v in starts]) if starts.size else np.zeros(0)
    counts = []
    for k in range(int(n_layers)):
        limit = l_phys - 1 - k
        idx = int(np.searchsorted(starts, limit, side="right"))
        counts.append(int(cumulative[idx - 1]) if idx > 0 else 0)
    # The plural agrees with the count (LG-G7); one shower of a two-shower kind is named.
    if len(picked) == 2:
        whose = "showers A and B"
    elif len(showers_mod.of(record)) == 2:
        whose = f"showers {picked[0].key.upper()}"
    else:
        whose = "showers"
    note = (
        f"Relative layer k + 1 lies inside the detector for a shower whose first populated layer is "
        f"the physical layer s when s ≤ L_phys − 1 − k, with L_phys = {l_phys} layer slots of "
        f"{pitch:g} mm from z = {z.lo:.1f} to {z.hi:.1f} mm and s = round((P₀z − {z.lo:.1f} mm) / "
        f"{pitch:g} mm); counts[k] is how many of the selection's {n_showers:,} {whose} reach it."
    )
    if n_without:
        note += (f" {n_without:,} selected shower(s) deposited energy but have no entry point P₀ "
                 "and are counted in no layer.")
    return {
        "n_showers": int(n_showers),
        "counts": counts,
        "n_without_start": int(n_without),
        "l_phys": int(l_phys),
        "note": typographic(note),
    }


# --------------------------------------------------------------- profile --


def _attention(channel: str, planes: dict[str, np.ndarray], outside: dict[str, float],
               pool_axis: int) -> dict[str, Any] | None:
    """The channel's per-layer Σ E·CAM, in ``voxel_event.attention_block``'s shape, or None."""
    view = planes_mod.view(channel)
    if not view.is_cam:
        return None
    # The query layer's 3-D module owns the block's shape; imported here, not at the top,
    # because it imports the Event Inspector, which imports this module.
    from .voxel_event import attention_block

    if view.cam == "gradcam":
        parts = {"signed": False, "values": planes["eg"].sum(axis=pool_axis),
                 "outside": float(outside.get("eg", 0.0))}
    else:
        parts = {"signed": True, "positive": planes["esp"].sum(axis=pool_axis),
                 "negative": np.abs(planes["esn"].sum(axis=pool_axis)),
                 "positive_outside": float(outside.get("esp", 0.0)),
                 "negative_outside": abs(float(outside.get("esn", 0.0)))}
    # The block's totals are computed from the full-precision sums; only its
    # per-layer arrays travel compacted.
    block = attention_block(channel, parts)
    for key in _ATTENTION_ARRAYS:
        if key in block:
            block[key] = _sig(block[key])
    return block


def bundle_profile(bundle: Any, panel_name: str, channel: str, numbering: str,
                   outside_gev: float = 0.0, plane_outside: dict[str, float] | None = None
                   ) -> dict[str, Any]:
    """The selection's exact per-layer sums, from a native bundle's depth panel.

    The column sums of the unpooled, uncropped panel: every hit the bundle
    holds, on every native depth bin. ``outside_gev`` is the energy the bundle
    counted off its grid (0 on the lattice).
    """
    planes = bundle.panel(panel_name).planes
    energy = np.asarray(planes["e"], dtype=np.float64).sum(axis=0)
    total = float(energy.sum()) + float(outside_gev)
    return {
        "numbering": numbering,
        "energy_gev": _sig(energy),
        "attention": _attention(channel, planes, plane_outside or {}, 0),
        "outside_gev": float(outside_gev),
        "total_gev": total,
        "exact": bool(bundle.exact),
    }


def _table_exists(con: duckdb.DuckDBPyConnection, physical: str) -> bool:
    row = con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?",
                      [physical]).fetchone()
    return bool(row and row[0])


def layer_table_profile(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                        spec: FilterSpec, n_layers: int) -> dict[str, Any] | None:
    """The selection's energy per relative layer kt, from the ingest-time ``layers_<name>`` table.

    Both showers of a two-shower event (``A+B`` rows with B), as the Local
    panels sum them. ``None`` for an experiment derived before the table
    existed. Layers past ``n_layers`` are counted as outside.
    """
    physical = naming.layers_table(record.table_name)
    if not _table_exists(con, physical):
        return None
    event = quote(naming.event_table(record.table_name))
    rows = con.execute(
        f"""SELECT kt, sum(e_dep) FROM {quote(physical)}
            WHERE event_number IN (SELECT event_number FROM {event} WHERE {spec.where_sql()})
            GROUP BY kt ORDER BY kt""", spec.params(),
    ).fetchall()
    energy = np.zeros(int(n_layers), dtype=np.float64)
    outside = 0.0
    for kt, e in rows:
        if kt is None or e is None:
            continue
        if 0 <= int(kt) < energy.size:
            energy[int(kt)] += float(e)
        else:
            outside += float(e)
    return {
        "numbering": NUMBERING_RELATIVE,
        "energy_gev": _sig(energy),
        "attention": None,
        "outside_gev": float(outside),
        "total_gev": float(energy.sum()) + float(outside),
        "exact": True,
    }


# ------------------------------------------------------------ the block --


def _note(kind: str, record: ExperimentRecord, n_layers: int, is_contiguous: bool | None,
          pitch: float) -> str:
    z = record.lattice.z
    if kind == "lab":
        text = (
            f"Detector layers, numbered by lattice ordinal 1–{n_layers}; a group's seams are the "
            "lattice's own stored cell edges in raw z, which the depth axis labels "
            f"Z = z − {ddl.CORE_SHIFT_Z_MM:g} mm."
        )
    elif kind == "canonical":
        text = (
            f"Detector layers, numbered by lattice ordinal 1–{n_layers}: the D-frame's depth "
            f"z′ = z − {z.lo:.1f} mm is one shift for every event, so its layers are the detector's "
            "own and its seams the lattice's stored cell edges, shifted."
        )
    elif kind == "trans":
        text = (
            f"Relative layers 1–{n_layers}, counted from each shower's own first populated layer "
            f"(relative layer 1 at Δz = 0); seams at (k − ½) × {pitch:g} mm, the last group running "
            "to the end of the axis."
        )
    else:
        return typographic(
            "Local frame: the detector layers tilt by each shower's own (θ, φ), so the superimposed "
            "showers share no common layer grid along w and no layer group is drawn or pooled; the "
            "profile is each relative layer's energy from the per-shower layer table."
        )
    if is_contiguous is False:
        text += (
            " The lattice skips layers the file never populates, so an ordinal is the lattice's own "
            "count, not a physical layer slot."
        )
    return typographic(text)


def depth_layers(
    kind: str,
    record: ExperimentRecord,
    *,
    edges: Any | None,
    profile: dict[str, Any] | None,
    reach_block: dict[str, Any] | None = None,
    pool: PooledAxis | None = None,
    is_contiguous: bool | None = None,
) -> dict[str, Any]:
    """The top-level ``depth_layers`` block of one ``/api/projections`` response.

    ``edges`` are the native depth edges in this response's own depth
    coordinate (raw z, z′ or Δz), ``None`` in the Local frame. ``pool`` is the
    layer-group operator when ``depth_groups`` was sent.
    """
    pitch = layer_pitch(record)
    numbering = {"lab": NUMBERING_DETECTOR, "canonical": NUMBERING_DETECTOR,
                 "trans": NUMBERING_RELATIVE}.get(kind, NUMBERING_NONE)
    n_layers = 0 if edges is None else int(len(edges) - 1)
    return {
        "numbering": numbering,
        "n_layers": n_layers,
        "partition_layers": int(record.lattice.z.n),
        "pitch_mm": float(pitch),
        "edges_mm": None if edges is None else _edges(edges),
        "first_layer": None if edges is None else 1,
        "contiguous": is_contiguous,
        "display_offset_mm": float(ddl.CORE_SHIFT_Z_MM) if kind == "lab" else None,
        "symbol": SYMBOLS[kind],
        "profile": profile,
        "reach": reach_block,
        "groups": None if pool is None else pool.groups_block(first_layer=1, pooled=True),
        "note": _note(kind, record, n_layers, is_contiguous, pitch),
    }


def lattice_contiguous(record: ExperimentRecord) -> bool:
    """Whether the experiment's lattice holds every layer slot: false on the demonstration file."""
    return layer_groups.contiguous(record.lattice.z.coords, layer_pitch(record))


# ------------------------------------------------------------ one event --


def layer_planes(
    kind: str,
    record: ExperimentRecord,
    *,
    iz: np.ndarray,
    kt: np.ndarray,
    energy: np.ndarray,
    p0_z: float,
    theta: float,
    phi: float,
) -> dict[str, Any]:
    """``frames.<kind>.layer_planes`` of one shower of ``/api/event``.

    The detector layer planes in this frame's panel coordinates: their unit
    normal (ê_z in the absolute and per-shower translated frames, ``R(θ, φ) ê_z``
    from ``grid/frame.py``'s ``rotation_matrix`` in Local - the rotation the
    cells were moved by), the seams along it, and the shower's energy per
    layer over every cell, not just the window. A plane ``n̂ · x = s`` has a
    line image only on a panel whose summed axis has a zero normal
    component: both depth panels, except in Local, where the tilt leaves it
    a line on u–w (``w = s / cos θ + u tan θ``) and a band on v–w.
    """
    lattice = record.lattice
    pitch = layer_pitch(record)
    z = lattice.z
    l_phys = layer_groups.physical_layers(z.lo, z.hi, pitch)
    s = layer_groups.start_layer(p0_z, z.lo, pitch)
    start = int(z.index_of(np.array([float(p0_z)]))[0]) + 1
    e = np.asarray(energy, dtype=np.float64)
    if kind == "lab":
        n = int(z.n)
        per_layer = np.bincount(np.asarray(iz, dtype=np.int64), weights=e, minlength=n)[:n]
        return {
            "numbering": NUMBERING_DETECTOR,
            "normal": [0.0, 0.0, 1.0],
            "edges_mm": _edges(z.edges),
            "first_layer": 1,
            "n_layers": n,
            "energy_gev": _sig(per_layer),
            "line_panels": ["xz", "yz"],
            "tilt": None,
            "start_layer": start,
            "reach_layers": None,
            "display_offset_mm": float(ddl.CORE_SHIFT_Z_MM),
        }
    layers = np.asarray(kt, dtype=np.int64)
    bounds = record.frame_bounds
    n = int(bounds.n_layers_trans) if bounds is not None else int(l_phys)
    if layers.size:
        n = max(n, int(layers.max()) + 1)
    per_layer = np.bincount(layers, weights=e, minlength=n)[:n] if layers.size else np.zeros(n)
    if kind == frame_mod.KIND_LOCAL:
        normal = layer_groups.layer_normal(frame_mod.rotation_matrix(theta, phi))
        lines = ["xz", "yz"] if float(theta) == 0.0 else ["xz"]
        tilt = {"theta": float(theta), "theta_deg": math.degrees(float(theta)),
                "pitch_along_w_mm": float(pitch) / math.cos(float(theta))}
    else:
        normal = np.array([0.0, 0.0, 1.0])
        lines = ["xz", "yz"]
        tilt = None
    return {
        "numbering": NUMBERING_RELATIVE,
        "normal": [float(v) + 0.0 for v in normal],
        "edges_mm": _edges(layer_groups.half_pitch_edges(n, pitch)),
        "first_layer": 1,
        "n_layers": n,
        "energy_gev": _sig(per_layer),
        "line_panels": lines,
        "tilt": tilt,
        "start_layer": start,
        "reach_layers": int(max(0, l_phys - s)),
        "display_offset_mm": None,
    }


# ------------------------------------------------------- the 100 KB yield --
#
# The layer blocks are what a guard gives up first (brief §9.1, LG-C2). Each
# guard loop measures the body; over the contract it trims the blocks to the
# shape below and measures the same plan again, and only if it is still over
# does it lower R or coarsen the grids as before, keeping the blocks trimmed.
# A trimmed block keeps every scalar, its edges and its groups, so the seams
# and the pooled axis still draw; only the per-layer arrays and the reach go.


def trim_depth_layers(block: dict[str, Any] | None, *, coarsened: bool = False
                      ) -> tuple[dict[str, Any] | None, bool]:
    """One ``depth_layers`` block in the trimmed shape, and whether that removed anything.

    ``profile`` and ``reach`` become null, ``trimmed`` true and ``trim_note``
    the disclosure: :data:`TRIM_NOTE`, or :data:`TRIM_NOTE_COARSENED` when the
    raster was coarsened as well. A block with neither array (or none at all)
    is returned as it is, with False.
    """
    if not block or (block.get("profile") is None and block.get("reach") is None):
        return block, False
    note = TRIM_NOTE_COARSENED if coarsened else TRIM_NOTE
    return {**block, "profile": None, "reach": None, "trimmed": True,
            "trim_note": typographic(note)}, True


def trim_body(body: dict[str, Any], *, coarsened: bool = False) -> bool:
    """Trim the ``depth_layers`` block of one assembled ``/api/projections`` body in place.

    Returns whether anything was trimmed; the body is untouched otherwise.
    """
    block, trimmed = trim_depth_layers(body.get("depth_layers"), coarsened=coarsened)
    if trimmed:
        body["depth_layers"] = block
    return trimmed


def trim_layer_planes(planes: dict[str, dict[str, Any] | None], *, coarsened: bool = False
                      ) -> tuple[dict[str, dict[str, Any] | None], bool]:
    """``/api/event``'s per-frame ``layer_planes`` in the trimmed shape, and whether that removed anything.

    Each frame's ``energy_gev`` becomes null, ``trimmed`` true and
    ``trim_note`` :data:`TRIM_NOTE_EVENT` (or :data:`TRIM_NOTE_EVENT_COARSENED`
    when the grids were coarsened as well); the normal, edges, tilt, start and
    reach stay.
    """
    note = typographic(TRIM_NOTE_EVENT_COARSENED if coarsened else TRIM_NOTE_EVENT)
    out: dict[str, dict[str, Any] | None] = {}
    trimmed = False
    for kind, block in planes.items():
        if block is None or block.get("energy_gev") is None:
            out[kind] = block
            continue
        out[kind] = {**block, "energy_gev": None, "trimmed": True, "trim_note": note}
        trimmed = True
    return out, trimmed
