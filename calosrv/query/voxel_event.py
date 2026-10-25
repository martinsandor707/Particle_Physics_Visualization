"""One event as cubes: the notebook's 3-D event displays, C5 and C6 (Page 2).

``GET /api/event?format=voxels`` draws one event - one shower, or both in the
two frames that hold both - as axis-aligned cubes for an orthographic
``echarts-gl`` ``bar3D``: the reference notebook's 3-D event display (C5,
coloured by energy, ``High_energy…`` ``plot_3d_shower_local``) and its species
display (C6, coloured by particle type, primaries edged), plus the network
channels of the two-shower file. The frontend never receives a hit row: a
cube is lattice ordinals or display-grid indices and a quantised colour code,
packed as base64 byte arrays, with exact values only for the 64 brightest.

**Two regimes.**

* *Cells* - the laboratory frame and the per-shower translated frame. One
  cube per detector cell at its measured lattice coordinates (minus P₀ in the
  translated frame, which does not rotate, so the cube stays axis-aligned),
  sized by the measured cell footprint (``canonical.cell_footprint``: the
  pitch between populated neighbours in one row or column) and the layer
  pitch - never by ``Axis.edges``, whose x intervals are Voronoi intervals of
  the twinned coordinates. The rows of one cell are merged: energies summed,
  the per-voxel network values energy-weighted (they repeat on every row of a
  voxel, so the mean is the common value), and a 2-bit code records whose
  rows the cell holds - A, B, an 'A+B' row, or 3 for a split cell.
* *Sub-deposit splat* - the Local frame and the D-frame. There a cell is
  tilted by its shower's R(θ, φ), or turned by the event's R_z(ψ), and a
  ``bar3D`` cube cannot tilt. Each cell's footprint is split into k × k
  (× k_z) equal sub-deposits that move with the frame and are binned onto
  axis-aligned voxels of a 20 mm grid - the Event Inspector's own splat
  (``grid/footprint.py``), which conserves energy. The pitch is coarsened
  only while the grid over the shower's extent would put more than
  :data:`MAX_VOXELS_PER_AXIS` voxels on a transverse axis, past a one-byte
  index; size is the budget guard's to trade (``api/routes_event.py``), not
  the 2-D raster's 96-bins rule, which drew the D-frame 2-4× coarser than
  either needed. Depth is the layer pitch
  along w in Local, and the native layer in the D-frame, whose rotation is
  about the detector axis (k_z = 1). A voxel's network value is the
  energy-weighted mean of what it received; its species the one that brought
  it the most energy, with that share as its purity.

  **k is chosen by convergence, not by the 2-D gap-free rule.** The
  inspector's k = 4, k_z = 2 meets the gap-free rule (sub-deposit spacing at
  most pitch/√2 across the beam), written for panels that sum one axis; in
  3-D nothing is summed. Measured on the demonstration file's showers
  against a k = 32 (k_z = 8) reference at 20 mm, k = 4 left 1.6-7.8% of the
  energy-weighted voxels empty and the voxel energies 0.20-0.32 decades off
  on average (energy-weighted |log10| of the ratio); k = 12 with k_z = 4 (Local)
  leaves 0.03-0.5% empty and 0.02-0.03 decades, and k = 12 in the D-frame
  0.06% and 0.018 decades, in at most 18 ms for a 751-cell shower. One event
  has no row budget to respect, so :data:`EVENT_SPLAT_K` and
  :data:`EVENT_LOCAL_K_Z` are fixed there; the ensemble's bounds
  (``frame.MAX_SUBSAMPLE``) answer a different cost.

**Colour.** Energy is the volumetric density E/V in GeV/mm³ on a log ramp from
a floor to the brightest drawn cube; a cube below the floor is drawn at the
lowest colour, flagged and counted. The floor is the 1st percentile of the
positive densities *of what is drawn* (CLAUDE.md section 2: a display range
follows the evidence on screen). In the cell frames that is the drawn
showers' cells - the inspector's floor, the notebook's A1/C2 ``vmin``. In the
splat frames it is the drawn voxels: a voxel holds only the part of a tilted
footprint that overlaps it, so voxel densities run below cell densities, and
a floor taken from the cells put a sparse shower's every voxel under it, on a
ramp whose top lay above everything drawn. A frame whose drawn cubes all
share one density has no range to span: its ramp is stated as degenerate
(``vmin = vmax``, every cube at the top colour), never padded with a decade
nothing reaches. The notebook's C5 colours raw energy on a linear ramp with
no floor; the payload says this view does not. Grad-CAM and the segmentation
error are linear on
[0, 1]; Shap-CAM is signed, linear on [−1, +1], for the diverging ramp
(CLAUDE.md section 2). Species take stable global codes - e−, e+, γ, n, p,
π+, π−, then "other" - never the notebook's per-event tab20 assignment.

**Cap.** Cubes are ranked by energy; the ``cap`` most energetic are drawn, in
ascending energy (the notebook's draw order, bright cubes last), and the
energy beyond the cap is counted beside the energy outside the window.

**Window.** The notebook's rule (``event_inspector._window_half``) on the
drawn frame's own coordinates: one half-width, 1.15 × half the cloud's
largest extent, never below 150 mm; symmetric about the origin across the
beam in the frames centred on one (Local, D-frame).
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode import quantize as quantize_mod
from ..encode import scale as scale_mod
from ..encode import topk as topk_mod
from ..encode.voxels import pack_ordinals
from ..errors import CapabilityError, NotFoundError, ValidationError
from ..grid import footprint as footprint_mod
from ..grid import frame as frame_mod
from ..grid.frame import KIND_CANONICAL, KIND_LOCAL, KIND_TRANS
from ..text import typographic
from . import capabilities, density, event_inspector, frame_sql, planes, shower_frames
from . import showers as showers_mod
from .event_inspector import _event_row, _grid_edges, _lattice_crop, _mid, _neighbours, _window_half
from .filters import FilterSpec

# ------------------------------------------------------------ vocabulary --

FORMAT_RASTER = "raster"
FORMAT_VOXELS = "voxels"
FORMATS: tuple[str, ...] = (FORMAT_RASTER, FORMAT_VOXELS)

#: The capability each format of ``GET /api/event`` needs.
FORMAT_GATES: dict[str, str] = {FORMAT_RASTER: "event-inspector", FORMAT_VOXELS: "vox-event"}

FRAME_LAB = "lab"
FRAMES: tuple[str, ...] = (FRAME_LAB, KIND_TRANS, KIND_LOCAL, KIND_CANONICAL)
#: The notebook's C5/C6 frame.
DEFAULT_FRAME = KIND_LOCAL
#: The frames that hold both showers of an event in one coordinate system.
BOTH_FRAMES: tuple[str, ...] = (FRAME_LAB, KIND_CANONICAL)
CELL_FRAMES: tuple[str, ...] = (FRAME_LAB, KIND_TRANS)

CHANNEL_ENERGY = "energy"
CHANNEL_GRADCAM = "gradcam"
CHANNEL_SHAPCAM = "shapcam"
CHANNEL_SEGERR = "segerr"
CHANNEL_SPECIES = "species"
CHANNELS: tuple[str, ...] = (
    CHANNEL_ENERGY, CHANNEL_GRADCAM, CHANNEL_SHAPCAM, CHANNEL_SEGERR, CHANNEL_SPECIES,
)
#: Channels read from the networks' columns (two-shower data only).
NETWORK_CHANNELS: tuple[str, ...] = (CHANNEL_GRADCAM, CHANNEL_SHAPCAM, CHANNEL_SEGERR)

REGIME_CELLS = "cells"
REGIME_SPLAT = "subdeposit_splat"

#: The cube cap: default, and the route's bounds.
DEFAULT_CAP = 6_000
MIN_CAP = 100
MAX_CAP = 15_000

#: The coarsest pitch the size guard may take a splat grid to.
BUDGET_MAX_PITCH_MM = 2.0 * frame_mod.CANONICAL_PITCH_MM

#: Most voxels a splat grid puts on one transverse axis: ordinals 0..255, one
#: byte each. The only reason a pitch is coarsened before the size guard runs.
MAX_VOXELS_PER_AXIS = 256

#: Where an energy ramp's floor is measured: the cells (cell frames) or the
#: drawn voxels (splat frames).
FLOOR_BASIS_CELLS = "cells"
FLOOR_BASIS_VOXELS = "voxels"

#: Relative tolerance under which a frame's drawn densities count as one value.
DEGENERATE_RTOL = 1e-9

#: The fraction of the contract the guard aims a lowered cap at.
BUDGET_TARGET = 0.95

#: Cubes carrying their exact value.
TOPK = 64

#: Sub-deposits per cell axis across the beam, and along depth in Local, for
#: one event's splat: chosen by convergence on a finer reference (module
#: docstring), never below ``frame.MIN_SUBSAMPLE``.
EVENT_SPLAT_K = 12
EVENT_LOCAL_K_Z = 4

#: Decimals of a shipped lattice coordinate (0.001 mm).
COORD_DECIMALS = 3

UNIT = "GeV/mm^3"

#: Stable species codes across events: these seven take codes 0–6, and every
#: other particle_type - ions ``PDG_…``, kaons, a missing value - code 7.
SPECIES_ORDER: tuple[str, ...] = ("e-", "e+", "gamma", "neutron", "proton", "pi+", "pi-")
OTHER_CODE = len(SPECIES_ORDER)
SPECIES_NAMES: tuple[str, ...] = SPECIES_ORDER + ("other",)
#: How a missing particle_type is listed among the "other" members.
MISSING_SPECIES = "(missing)"

#: A u8 dictionary code meaning "none" (no parent, no daughter).
NONE_CODE = 255

#: The single-shower hit columns of the species views (``ddl.PROJ_SINGLE_COLUMNS``).
SPECIES_COLUMNS: tuple[str, ...] = ("particle_type", "is_secondary", "parent_type", "daughter_type")

#: The 2-bit shower code (``flags`` bits 0-1).
SHOWER_A, SHOWER_B, SHOWER_AB, SHOWER_MIXED = 0, 1, 2, 3
FLAG_PRIMARY = 1 << 2
FLAG_BELOW_FLOOR = 1 << 3
FLAG_BITS = {"shower": [0, 1], "primary": 2, "below_floor": 3}

_ORDER_NOTE = "ascending energy"

_SYMBOLS = {
    FRAME_LAB: event_inspector.SYMBOLS["lab"],
    KIND_TRANS: event_inspector.SYMBOLS[KIND_TRANS],
    KIND_LOCAL: event_inspector.SYMBOLS[KIND_LOCAL],
    KIND_CANONICAL: dict(density.SYMBOLS),
}


# ------------------------------------------------------------- validation --


def channels_offered(record: ExperimentRecord) -> tuple[str, ...]:
    """The channels this experiment's data can colour cubes by.

    The network channels follow the catalogue's ``vox-attention`` gate, not
    the bare presence of networks, so the route serves exactly what
    ``/api/experiments`` says it does.
    """
    caps = capabilities.of(record)
    offered = [CHANNEL_ENERGY]
    if caps.can("vox-attention"):
        offered += list(NETWORK_CHANNELS)
    if caps.can("vox-species"):
        offered.append(CHANNEL_SPECIES)
    return tuple(offered)


def resolve(record: ExperimentRecord, frame: str, shower: str | None, channel: str, model: str) -> str:
    """Refuse what the request or the data cannot serve; return the shower key.

    A malformed value is the plain validation error naming its parameter. What
    the experiment cannot serve is the capability problem naming the field
    and the capability: the D-frame needs two showers, the per-shower frames
    their measured extents, the network channels the networks' columns, the
    species channel the species columns. ``shower`` defaults to both showers
    in the frames that hold both, and to the one shower otherwise.
    """
    for name, value, allowed in (("frame", frame, FRAMES), ("channel", channel, CHANNELS),
                                 ("model", model, ddl.MODELS)):
        if value not in allowed:
            raise ValidationError(f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name)
    capabilities.require(record, f"frame-{frame}", field="frame")
    offered = channels_offered(record)
    if channel in NETWORK_CHANNELS:
        capabilities.require_choice(record, "channel", channel, offered, "vox-attention")
    elif channel == CHANNEL_SPECIES:
        capabilities.require_choice(record, "channel", channel, offered, "vox-species")
    two = len(showers_mod.of(record)) == 2
    if shower is None:
        return "both" if two and frame in BOTH_FRAMES else "a"
    # Unknown values and shower b of a single-shower experiment, as everywhere.
    showers_mod.of(record, shower)
    if shower == "both" and not two:
        raise CapabilityError(
            f"shower=both is not available for experiment {record.table_name!r}: it holds one "
            "shower per event.",
            field="shower", capability="shower", kind=record.kind,
            reason="one shower per event", table_name=record.table_name,
        )
    if shower == "both" and frame not in BOTH_FRAMES:
        raise ValidationError(
            f"shower=both draws the two showers in one frame, which only the laboratory and the "
            f"D-frame are; frame={frame!r} is each shower's own. Ask for shower a or b.",
            field="shower",
        )
    return shower


# ------------------------------------------------------------ pure helpers --


def species_code(name: str | None) -> int:
    """The stable code of a particle_type; every unlisted name and a missing one are "other"."""
    if name is None:
        return OTHER_CODE
    try:
        return SPECIES_ORDER.index(name)
    except ValueError:
        return OTHER_CODE


def daughter_tokens(text: str | None) -> list[str]:
    """The ``;``-joined daughter list as tokens; empty for NULL or an empty field."""
    if not text:
        return []
    return [token for token in (t.strip() for t in str(text).split(";")) if token]


def daughter_mode(tokens: list[str]) -> str | None:
    """The most frequent daughter, ties broken alphabetically; None when there is none."""
    if not tokens:
        return None
    counts = Counter(tokens)
    top = max(counts.values())
    return min(name for name, count in counts.items() if count == top)


def shower_codes(org_mask: np.ndarray) -> np.ndarray:
    """2-bit code from a bit mask of the row origins present (bit ``org``): one origin, or 3."""
    mask = np.asarray(org_mask, dtype=np.int64)
    single = (mask == 1) | (mask == 2) | (mask == 4)
    code = np.where(mask == 2, SHOWER_B, np.where(mask == 4, SHOWER_AB, SHOWER_A))
    return np.where(single, code, SHOWER_MIXED).astype(np.uint8)


@dataclass
class Cells:
    """The rows of one event merged per detector cell."""

    ix: np.ndarray
    iy: np.ndarray
    iz: np.ndarray
    energy: np.ndarray
    shower: np.ndarray               # u8 2-bit code
    inverse: np.ndarray              # row -> cell
    value: np.ndarray | None = None  # energy-weighted mean of a per-row value
    primary: np.ndarray | None = None
    species: np.ndarray | None = None  # dominant-energy species code
    purity: np.ndarray | None = None   # that species' share of the cell's energy
    lead_row: np.ndarray | None = None  # most energetic row of the dominant species

    @property
    def n(self) -> int:
        return int(self.energy.size)


def merge_cells(ix, iy, iz, org, energy, value=None, primary=None, species=None) -> Cells:
    """Merge rows sharing a cell ``(ix, iy, iz)``.

    Energies are summed. ``value`` is averaged with energy weights over the
    rows where it is finite (a plain mean if they carry no energy; NaN if no
    row has one). ``primary`` is true if any row is primary-tagged. A cell's
    species is the one with most energy in it, ties to the lower code, and its
    purity that species' share. The shower code is the rows' one origin, or 3
    when more than one origin shares the cell (a split cell).
    """
    ix = np.asarray(ix, dtype=np.int64)
    iy = np.asarray(iy, dtype=np.int64)
    iz = np.asarray(iz, dtype=np.int64)
    energy = np.asarray(energy, dtype=np.float64)
    org = np.asarray(org, dtype=np.int64)
    if ix.size == 0:
        empty = np.zeros(0, dtype=np.int64)
        return Cells(empty, empty, empty, np.zeros(0), np.zeros(0, dtype=np.uint8), empty,
                     None if value is None else np.zeros(0),
                     None if primary is None else np.zeros(0, dtype=bool),
                     None if species is None else np.zeros(0, dtype=np.uint8),
                     None if species is None else np.zeros(0), empty)
    keys, inverse = np.unique(np.column_stack([iz, iy, ix]), axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    n = keys.shape[0]
    e = np.bincount(inverse, weights=energy, minlength=n)
    mask = np.zeros(n, dtype=np.int64)
    np.bitwise_or.at(mask, inverse, np.left_shift(1, org))
    cells = Cells(ix=keys[:, 2], iy=keys[:, 1], iz=keys[:, 0], energy=e,
                  shower=shower_codes(mask), inverse=inverse)
    if value is not None:
        v = np.asarray(value, dtype=np.float64)
        finite = np.isfinite(v)
        filled = np.where(finite, v, 0.0)
        ef = np.bincount(inverse, weights=np.where(finite, energy, 0.0), minlength=n)
        ev = np.bincount(inverse, weights=energy * filled, minlength=n)
        nf = np.bincount(inverse, weights=finite.astype(np.float64), minlength=n)
        vs = np.bincount(inverse, weights=filled, minlength=n)
        with np.errstate(invalid="ignore", divide="ignore"):
            cells.value = np.where(ef > 0, ev / np.where(ef > 0, ef, 1.0),
                                   np.where(nf > 0, vs / np.where(nf > 0, nf, 1.0), np.nan))
    if primary is not None:
        flag = np.zeros(n, dtype=bool)
        np.logical_or.at(flag, inverse, np.asarray(primary, dtype=bool))
        cells.primary = flag
    code = np.asarray(species, dtype=np.int64) if species is not None else np.zeros(ix.size, dtype=np.int64)
    by_species = np.bincount(inverse * (OTHER_CODE + 1) + code, weights=energy,
                             minlength=n * (OTHER_CODE + 1)).reshape(n, OTHER_CODE + 1)
    dominant = by_species.argmax(axis=1)
    if species is not None:
        cells.species = dominant.astype(np.uint8)
        cells.purity = np.where(e > 0, by_species.max(axis=1) / np.where(e > 0, e, 1.0), 1.0)
    # The most energetic row of each cell's dominant species: whose parent and daughters it shows.
    of_dominant = code == dominant[inverse]
    order = np.lexsort((-energy, ~of_dominant, inverse))
    starts = np.r_[0, np.flatnonzero(np.diff(inverse[order])) + 1]
    cells.lead_row = order[starts]
    return cells


# ------------------------------------------------------------------- rows --


@dataclass
class Rows:
    """One event's rows of the drawn shower(s)."""

    ix: np.ndarray
    iy: np.ndarray
    iz: np.ndarray
    org: np.ndarray
    energy: np.ndarray
    file_trans: np.ndarray
    file_local: np.ndarray
    value: np.ndarray | None = None
    primary: np.ndarray | None = None
    particle: list[str | None] | None = None
    codes: np.ndarray | None = None       # stable species code per row
    parent: list[str | None] | None = None
    daughters: list[str | None] | None = None

    @property
    def n(self) -> int:
        return int(self.energy.size)


def _floats(column: Any) -> np.ndarray:
    return np.asarray(np.ma.filled(np.ma.asarray(column).astype(np.float64), np.nan), dtype=np.float64)


def _ints(column: Any) -> np.ndarray:
    return np.asarray(np.ma.filled(np.ma.asarray(column), 0), dtype=np.int64)


def _strings(column: Any) -> list[str | None]:
    masked = np.ma.asarray(column)
    mask = np.ma.getmaskarray(masked)
    return [None if m or v is None else str(v) for v, m in zip(masked.data.tolist(), mask.tolist())]


def _channel_sql(channel: str, model: str, coord: str) -> tuple[str, ...]:
    """The allowlisted per-row expressions a network channel reads (``ddl`` builders only)."""
    if channel in (CHANNEL_GRADCAM, CHANNEL_SHAPCAM):
        return (f"CAST(p.{ddl.cam_column(model, coord, channel)} AS DOUBLE)",)
    if channel == CHANNEL_SEGERR:
        return (f"CAST(p.{ddl.seg_column('pred', coord)} AS DOUBLE)",
                f"CAST(p.{ddl.seg_column('true', coord)} AS DOUBLE)")
    return ()


def _voxel_rows(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, event_number: int,
                shower_sql: str, channel: str, model: str, coord: str, species: bool) -> Rows:
    """The event's rows of the drawn shower(s): ordinals, origin, energy, frame columns, channel columns."""
    proj = quote(naming.proj_table(record.table_name))
    base = ("ix", "iy", "iz", "org", "energy", "xt", "yt", "kt", "xl", "yl", "zl")
    select = [f"p.{c}" for c in base]
    network = _channel_sql(channel, model, coord)
    select += [f"{expr} AS v{i}" for i, expr in enumerate(network)]
    if species:
        select += [f"p.{c}" for c in SPECIES_COLUMNS]
    data = con.execute(
        f"""SELECT {', '.join(select)} FROM {proj} p
            WHERE p.event_number = ? AND ({shower_sql})
            ORDER BY p.iz, p.iy, p.ix, p.org""", [int(event_number)],
    ).fetchnumpy()
    n = len(data["ix"])
    xt, yt, kt = _floats(data["xt"]), _floats(data["yt"]), _ints(data["kt"])
    rows = Rows(
        ix=_ints(data["ix"]), iy=_ints(data["iy"]), iz=_ints(data["iz"]), org=_ints(data["org"]),
        energy=_floats(data["energy"]),
        file_trans=np.column_stack([xt, yt, kt.astype(np.float64)]) if n else np.zeros((0, 3)),
        file_local=(np.column_stack([_floats(data[c]) for c in ("xl", "yl", "zl")]) if n
                    else np.zeros((0, 3))),
    )
    if channel in (CHANNEL_GRADCAM, CHANNEL_SHAPCAM):
        rows.value = _floats(data["v0"])
    elif channel == CHANNEL_SEGERR:
        rows.value = np.abs(_floats(data["v0"]) - _floats(data["v1"]))
    if species:
        rows.primary = _ints(data["is_secondary"]) == 0
        # A NULL is_secondary is not a primary tag.
        rows.primary &= ~np.ma.getmaskarray(np.ma.asarray(data["is_secondary"]))
        rows.particle = _strings(data["particle_type"])
        rows.codes = np.asarray([species_code(name) for name in rows.particle], dtype=np.int64)
        rows.parent = _strings(data["parent_type"])
        rows.daughters = _strings(data["daughter_type"])
    return rows


# ------------------------------------------------------------------ cubes --


@dataclass
class Cubes:
    """One frame's cubes, before the cap: integer positions, energy and the channel's inputs."""

    ix: np.ndarray
    iy: np.ndarray
    iz: np.ndarray
    energy: np.ndarray
    shower: np.ndarray
    volume_mm3: float
    geometry: dict[str, Any]
    outside_gev: float
    value: np.ndarray | None = None
    primary: np.ndarray | None = None
    species: np.ndarray | None = None
    purity: np.ndarray | None = None
    parent: np.ndarray | None = None
    n_daughters: np.ndarray | None = None
    daughter_mode: np.ndarray | None = None

    @property
    def n(self) -> int:
        return int(self.energy.size)


@dataclass
class _ShowerInfo:
    key: str
    label: str
    p0: np.ndarray
    theta: float | None
    phi: float | None
    momentum: float | None


@dataclass
class Builder:
    """One event's voxel view: rows read once, rendered at any (cap, pitch) the size guard asks for."""

    record: ExperimentRecord
    frame: str
    shower: str
    channel: str
    model: str
    source: str
    footprint: tuple[float, float]
    pitch_z: float
    event: dict[str, Any]
    in_selection: bool
    prev_event: int | None
    next_event: int | None
    infos: list[_ShowerInfo]
    rows: Rows
    cells: Cells
    centres: np.ndarray            # (n_rows, 3) cell centres in the drawn frame
    rotation: np.ndarray | None    # the frame's R (splat frames)
    half: float
    windows: dict[str, tuple[float, float]]
    floor: float                   # GeV/mm^3: the cell frames' floor (splat frames take the voxels')
    residual: float | None
    k: int = 0
    k_z: int = 0
    first_pitch: float | None = None
    canonical: dict[str, Any] | None = None
    dictionaries: dict[str, list[str]] = field(default_factory=dict)
    build_notes: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    _cache: dict[float | None, Cubes] = field(default_factory=dict)

    # --------------------------------------------------------- properties --

    @property
    def regime(self) -> str:
        return REGIME_CELLS if self.frame in CELL_FRAMES else REGIME_SPLAT

    @property
    def two(self) -> bool:
        return len(showers_mod.of(self.record)) == 2

    @property
    def network(self) -> str | None:
        """The network a channel reads: the requested one's CAMs, the segmentation network's error."""
        if self.channel == CHANNEL_SEGERR:
            return "segmentation"
        return self.model if self.channel in NETWORK_CHANNELS else None

    @property
    def has_species(self) -> bool:
        return self.rows.primary is not None

    @property
    def cell_volume(self) -> float:
        return float(self.footprint[0] * self.footprint[1] * self.pitch_z)

    def n_cubes(self, pitch: float | None) -> int:
        return self.cubes(pitch).n

    def bytes_per_cube(self, pitch: float | None) -> float:
        """Wire bytes one drawn cube costs: the per-cube arrays actually shipped, in base64.

        Five one-byte arrays (three indices, the code, the flags), the indices
        two bytes wide where one passes 255. On the species channel, what
        :meth:`_species_block` ships: the cell frames' parent, daughter count
        and daughter mode, and purity wherever a cube is impure (the splat
        frames' only per-cube species array, and a cell frame's whenever a
        cell mixes species).
        """
        cubes = self.cubes(pitch)
        wide = cubes.n and max(int(cubes.ix.max()), int(cubes.iy.max()), int(cubes.iz.max())) > 0xFF
        raw = 5.0 + (3.0 if wide else 0.0)
        if self.channel == CHANNEL_SPECIES:
            if self.regime == REGIME_CELLS:
                raw += 3.0
            if cubes.purity is not None and bool((cubes.purity < 1.0 - 1e-12).any()):
                raw += 1.0
        return raw * 4.0 / 3.0

    def transverse_edges(self, pitch: float) -> tuple[np.ndarray, np.ndarray]:
        """The splat grid's x and y edges at ``pitch``: the window, tight on the cells plus a footprint."""
        margin = max(self.footprint[0], self.footprint[1], self.pitch_z)
        return tuple(  # type: ignore[return-value]
            _grid_edges(*self.windows[axis], pitch, float(self.centres[:, i].min()),
                        float(self.centres[:, i].max()), margin)
            for i, axis in enumerate("xy"))

    # -------------------------------------------------------------- cubes --

    def cubes(self, pitch: float | None) -> Cubes:
        if pitch not in self._cache:
            self._cache[pitch] = self._cell_cubes() if self.regime == REGIME_CELLS else self._splat_cubes(pitch)
        return self._cache[pitch]

    def _cell_cubes(self) -> Cubes:
        """One cube per cell inside the window, on the lattice (minus P₀ when translated)."""
        lat = self.record.lattice
        cells = self.cells
        shift = self.infos[0].p0 if self.frame == KIND_TRANS else np.zeros(3)
        index = {"x": cells.ix, "y": cells.iy, "z": cells.iz}
        crops: dict[str, tuple[int, int]] = {}
        inside = np.ones(cells.n, dtype=bool)
        for i, axis in enumerate("xyz"):
            coords = lat.axis(axis).coords - shift[i]
            i0, i1 = _lattice_crop(coords, index[axis], *self.windows[axis])
            crops[axis] = (i0, i1)
            inside &= (index[axis] >= i0) & (index[axis] < i1)
        axes = {axis: {"i0": crops[axis][0],
                       "coords": [round(float(v), COORD_DECIMALS)
                                  for v in lat.axis(axis).coords[crops[axis][0]:crops[axis][1]]]}
                for axis in "xyz"}
        geometry = {
            "cube_mm": [float(self.footprint[0]), float(self.footprint[1]), float(self.pitch_z)],
            "axes": axes,
            "coords_rounding_mm": 10.0 ** -COORD_DECIMALS,
            "origin_mm": [float(v) for v in shift],
            "grid": None,
            "splat": None,
            "depth": ({"policy": "native_layers", "note": "the detector's own sampling layers"}
                      if self.frame == FRAME_LAB else
                      {"policy": "native_layers", "note": "the detector's sampling layers, minus the "
                       "shower's first-layer depth P₀z"}),
            "note": (
                "One cube per detector cell, centred on its measured lattice coordinates"
                + (" minus the shower's entry point P₀ (no rotation, so the cube stays axis-aligned)"
                   if self.frame == KIND_TRANS else "")
                + f", sized by the measured cell footprint ({self.footprint[0]:.2f} × "
                f"{self.footprint[1]:.2f} mm, the pitch between populated neighbours in one row or "
                f"column) and the {self.pitch_z:g} mm layer pitch. Centre = axes.<a>.coords[index] − "
                "origin_mm; the lattice's x cells are irregular, so no index is ever turned into a "
                "position by a pitch."
            ),
        }
        sel = np.flatnonzero(inside)
        return Cubes(
            ix=cells.ix[sel] - crops["x"][0], iy=cells.iy[sel] - crops["y"][0],
            iz=cells.iz[sel] - crops["z"][0], energy=cells.energy[sel], shower=cells.shower[sel],
            volume_mm3=self.cell_volume, geometry=geometry,
            outside_gev=float(cells.energy[~inside].sum()),
            value=None if cells.value is None else cells.value[sel],
            primary=None if cells.primary is None else cells.primary[sel],
            species=None if cells.species is None else cells.species[sel],
            purity=None if cells.purity is None else cells.purity[sel],
            **self._cell_species_fields(sel),
        )

    def _cell_species_fields(self, sel: np.ndarray) -> dict[str, np.ndarray | None]:
        """Per-cell parent, daughter count and most frequent daughter, from each cell's lead row."""
        if self.channel != CHANNEL_SPECIES or self.rows.parent is None:
            return {"parent": None, "n_daughters": None, "daughter_mode": None}
        lead = self.cells.lead_row[sel]
        parents = {name: i for i, name in enumerate(self.dictionaries["parents"])}
        daughters = {name: i for i, name in enumerate(self.dictionaries["daughters"])}
        parent = np.full(lead.size, NONE_CODE, dtype=np.int64)
        count = np.zeros(lead.size, dtype=np.int64)
        mode = np.full(lead.size, NONE_CODE, dtype=np.int64)
        for j, row in enumerate(lead):
            name = self.rows.parent[row]
            if name is not None and name in parents:
                parent[j] = parents[name]
            tokens = daughter_tokens(self.rows.daughters[row])
            count[j] = min(len(tokens), 255)
            top = daughter_mode(tokens)
            if top is not None and top in daughters:
                mode[j] = daughters[top]
        return {"parent": parent, "n_daughters": count, "daughter_mode": mode}

    def _splat_cubes(self, pitch: float | None) -> Cubes:
        """The cells' footprints split into sub-deposits, moved with the frame, binned onto voxels."""
        assert pitch is not None
        lat = self.record.lattice
        fp = self.footprint
        rows = self.rows
        margin = max(fp[0], fp[1], self.pitch_z)
        x_edges, y_edges = self.transverse_edges(pitch)
        points, weights = footprint_mod.rotated_subdeposits(
            self.centres, self.rotation, rows.energy, (fp[0], fp[1], self.pitch_z), self.k, self.k_z)
        m = self.k * self.k * self.k_z
        if self.frame == KIND_CANONICAL:
            # Depth is the native layer: bin the ordinal itself, exactly, inside the cropped layers.
            z_lo, z_hi = self.canonical["layers"]
            z_edges = np.arange(z_lo, z_hi + 1, dtype=np.float64) - 0.5
            points = points.copy()
            points[:, 2] = np.repeat(self.rows.iz.astype(np.float64), m)
        else:
            z_edges = _grid_edges(*self.windows["z"], self.pitch_z, float(self.centres[:, 2].min()),
                                  float(self.centres[:, 2].max()), margin)
        edges = (x_edges, y_edges, z_edges)

        def binned(factor: np.ndarray | None) -> np.ndarray:
            w = weights if factor is None else weights * np.repeat(np.asarray(factor, dtype=np.float64), m)
            cube, _ = footprint_mod.bin_uniform(points, w, edges)
            return cube

        energy_cube, outside = footprint_mod.bin_uniform(points, weights, edges)
        jx, jy, jz = np.nonzero(energy_cube > 0)
        energy = energy_cube[jx, jy, jz]

        # Whose rows the energy came from: the one origin, or 3 when more than one.
        origins = np.unique(rows.org)
        mask = np.zeros(energy.size, dtype=np.int64)
        if origins.size == 1:
            mask[:] = 1 << int(origins[0])
        else:
            for o in origins:
                part = binned((rows.org == o).astype(np.float64))[jx, jy, jz]
                mask |= np.where(part > 0, 1 << int(o), 0)
        cubes = Cubes(ix=jx, iy=jy, iz=jz, energy=energy, shower=shower_codes(mask),
                      volume_mm3=float(pitch * pitch * self.pitch_z), geometry={},
                      outside_gev=float(outside))
        if rows.value is not None:
            finite = np.isfinite(rows.value)
            ef = binned(finite.astype(np.float64))[jx, jy, jz]
            ev = binned(np.where(finite, rows.value, 0.0))[jx, jy, jz]
            with np.errstate(invalid="ignore", divide="ignore"):
                cubes.value = np.where(ef > 0, ev / np.where(ef > 0, ef, 1.0), np.nan)
        if rows.primary is not None:
            cubes.primary = binned(rows.primary.astype(np.float64))[jx, jy, jz] > 0
        if self.channel == CHANNEL_SPECIES and rows.codes is not None:
            codes = rows.codes
            present = np.unique(codes)
            parts = np.stack([binned((codes == c).astype(np.float64))[jx, jy, jz] for c in present], axis=1)
            cubes.species = present[parts.argmax(axis=1)].astype(np.uint8)
            cubes.purity = np.where(energy > 0, parts.max(axis=1) / np.where(energy > 0, energy, 1.0), 1.0)

        if self.frame == KIND_CANONICAL:
            z_lo, z_hi = self.canonical["layers"]
            zf = self.canonical["z_front_mm"]
            z_axis = {"i0": int(z_lo), "coords": [round(float(v) - zf, COORD_DECIMALS)
                                                  for v in lat.z.coords[z_lo:z_hi]]}
            grid = {"x0": float(x_edges[0]), "y0": float(y_edges[0]), "z0": None,
                    "pitch_mm": float(pitch), "pitch_z_mm": float(self.pitch_z),
                    "n": [int(x_edges.size - 1), int(y_edges.size - 1), int(z_edges.size - 1)],
                    "z_axis": "native_layers"}
            depth = {"policy": "native_layers",
                     "note": "the detector's own sampling layers, z′ = z − z_front; the index is the "
                             "layer ordinal, placed through axes.z.coords"}
            axes = {"z": z_axis}
            moved = "turned about the detector axis by the event's D-frame rotation R_z(ψ)"
        else:
            grid = {"x0": float(x_edges[0]), "y0": float(y_edges[0]), "z0": float(z_edges[0]),
                    "pitch_mm": float(pitch), "pitch_z_mm": float(self.pitch_z),
                    "n": [int(x_edges.size - 1), int(y_edges.size - 1), int(z_edges.size - 1)],
                    "z_axis": "uniform"}
            depth = {"policy": "uniform_bins",
                     "note": "uniform bins of the layer pitch along w, never smoothed"}
            axes = None
            moved = "tilted by the shower's R(θ, φ)"
        cubes.geometry = {
            "cube_mm": [float(pitch), float(pitch), float(self.pitch_z)],
            "axes": axes,
            "coords_rounding_mm": 10.0 ** -COORD_DECIMALS if axes else None,
            "origin_mm": [0.0, 0.0, 0.0],
            "grid": grid,
            "splat": {"k": int(self.k), "k_z": int(self.k_z),
                      "footprint_mm": [float(fp[0]), float(fp[1]), float(self.pitch_z)]},
            "depth": depth,
            "note": typographic(
                f"In this frame each cell is {moved}, and an echarts-gl bar3D cube cannot tilt. Each "
                f"cell's {fp[0]:.2f} × {fp[1]:.2f} × {self.pitch_z:g} mm footprint is therefore split "
                f"into {self.k} × {self.k}"
                + (f" × {self.k_z}" if self.k_z > 1 else "")
                + f" equal sub-deposits that move with it, binned onto axis-aligned {pitch:g} × "
                f"{pitch:g} × {self.pitch_z:g} mm voxels: energy is conserved, and k is chosen so the "
                "voxels converge on the footprints' area overlap (k = 4, enough for a projected panel, "
                "leaves empty voxels in 3-D). A voxel's centre is grid.x0 + (index + 0.5) × pitch along x and y"
                + (", and axes.z.coords[index] along depth." if self.frame == KIND_CANONICAL
                   else ", and grid.z0 + (index + 0.5) × pitch_z along depth.")
            ),
        }
        return cubes

    # ----------------------------------------------------------- assemble --

    def assemble(self, cap: int, pitch: float | None, requested: int | None = None) -> dict[str, Any]:
        """The response body (without meta and filter) at this cap and pitch.

        ``requested`` is the cap the request asked for, when the size guard has
        lowered it since.
        """
        cubes = self.cubes(pitch)
        cap = max(1, int(cap))
        total = float(self.rows.energy.sum())
        order = np.lexsort((cubes.ix, cubes.iy, cubes.iz, -cubes.energy))
        kept, beyond = order[:cap], order[cap:]
        drawn = kept[::-1]          # ascending energy: the notebook's draw order
        energy = cubes.energy[drawn]
        dens = energy / cubes.volume_mm3
        flags = cubes.shower[drawn].astype(np.int64)
        if cubes.primary is not None:
            flags |= np.where(cubes.primary[drawn], FLAG_PRIMARY, 0)
        scale, codes, below, top_values, notes = self._colour(cubes, drawn, dens, pitch)
        flags |= np.where(below, FLAG_BELOW_FLOOR, 0)

        packed: dict[str, str] = {}
        dtypes: dict[str, str] = {}
        for name, values in (("ix", cubes.ix[drawn]), ("iy", cubes.iy[drawn]), ("iz", cubes.iz[drawn]),
                             ("code", codes), ("flags", flags)):
            packed[name], dtypes[name] = pack_ordinals(values)

        energy_drawn = float(energy.sum())
        energy_beyond = float(cubes.energy[beyond].sum())
        n_total = cubes.n
        cap_block = {
            "limit": int(cap),
            "requested": int(cap if requested is None else requested),
            "n_total": int(n_total),
            "n_drawn": int(drawn.size),
            "n_beyond": int(beyond.size),
            "rank": "energy",
            "energy_total_gev": total,
            "energy_drawn_gev": energy_drawn,
            "energy_beyond_gev": energy_beyond,
            "fraction_beyond": energy_beyond / total if total > 0 else 0.0,
            "energy_outside_window_gev": float(cubes.outside_gev),
            "fraction_outside_window": float(cubes.outside_gev) / total if total > 0 else 0.0,
        }
        what = "cells" if self.regime == REGIME_CELLS else "voxels"
        cap_note = (
            f"All {n_total:,} {what} are drawn." if not beyond.size else
            f"The {drawn.size:,} most energetic of {n_total:,} {what} are drawn (cap {cap:,}, ranked by "
            f"energy); the {beyond.size:,} beyond the cap hold {energy_beyond:.4g} GeV, "
            f"{100.0 * cap_block['fraction_beyond']:.3g}% of the drawn showers' energy, counted and not drawn."
        )
        if cubes.outside_gev > 0:
            cap_note += (f" {cubes.outside_gev:.4g} GeV ({100.0 * cap_block['fraction_outside_window']:.3g}%) "
                         "falls outside the window and is counted, not drawn.")
        voxels: dict[str, Any] = {
            "frame": self.frame,
            "regime": self.regime,
            "symbols": dict(_SYMBOLS[self.frame]),
            "channel": self.channel,
            "model": self.network,
            "geometry": cubes.geometry,
            "cubes": {
                "n": int(drawn.size),
                "order": _ORDER_NOTE,
                "dtype": dtypes,
                **packed,
                "flag_bits": dict(FLAG_BITS),
                "shower_codes": self._shower_labels(),
            },
            "scale": scale,
            "topk": top_values["entries"],
            "topk_quantity": top_values["quantity"],
            "topk_unit": top_values["unit"],
            "cap": cap_block,
            "below_floor": {
                "n": int(below.sum()),
                "drawn_as": ("lowest colour" if self.channel == CHANNEL_ENERGY
                             else "not applicable: this channel's ramp has no floor"),
            },
            "species": self._species_block(cubes, drawn) if self.channel == CHANNEL_SPECIES else None,
            # The geometry sentence is shipped once, at geometry.note.
            "notes": [typographic(n) for n in [*self.build_notes, *notes, cap_note]],
        }
        return {
            "event": self._event_block(),
            "coordinates": self._coordinates_block(),
            "window": self._window_block(),
            "footprint_mm": [float(self.footprint[0]), float(self.footprint[1]), float(self.pitch_z)],
            "voxels": voxels,
            "elapsed_ms": (time.perf_counter() - self.started) * 1000.0,
        }

    # ------------------------------------------------------------- colour --

    def _colour(self, cubes: Cubes, drawn: np.ndarray, dens: np.ndarray, pitch: float | None):
        """The channel's scale, the drawn cubes' codes, the below-floor mask, exact top values, notes."""
        n = drawn.size
        below = np.zeros(n, dtype=bool)
        notes: list[str] = []
        if self.channel in (CHANNEL_ENERGY, CHANNEL_SPECIES):
            ranked, signed = dens, False
            quantity, unit = "energy_density", UNIT
        else:
            ranked, signed = cubes.value[drawn], self.channel == CHANNEL_SHAPCAM
            quantity, unit = self.channel, ("attribution" if signed else
                                            "attention" if self.channel == CHANNEL_GRADCAM else "fraction")
        entries = []
        for item in topk_mod.top_cells(np.asarray(ranked, dtype=np.float64)[None, :], k=TOPK, signed=signed):
            j = int(item["j"])
            entries.append({"i": j, "value": float(item["value"]), "energy_gev": float(cubes.energy[drawn][j])})
        top_values = {"entries": entries, "quantity": quantity, "unit": unit}

        if self.channel == CHANNEL_ENERGY:
            floor, top, degenerate, basis = self._energy_range(dens)
            if degenerate:
                # One value: a zero-width ramp at it, never a decade nothing drawn reaches.
                vmin = vmax = math.log10(top) if top > 0 else 0.0
                below = np.zeros(n, dtype=bool)
            else:
                vmin, vmax = math.log10(floor), math.log10(top)
                below = dens < floor
            colour = scale_mod.ColorScale(
                scale=scale_mod.SCALE_LOG, vmin=vmin, vmax=vmax, unit=UNIT,
                mode=scale_mod.MODE_PERCENTILE, locked=True, global_vmax=top if top > 0 else None,
                n_below=int(below.sum()), n_above=0, n_empty=0, quantity="energy_density",
            )
            # A zero-width ramp puts every populated cube on the top code (quantize's span <= 0).
            codes = quantize_mod.quantize(dens, colour)
            scale = colour.as_dict()
            scale.update({
                "floor_density": floor, "top_density": top, "floor_percentile": event_inspector.FLOOR_PERCENTILE,
                "floor_basis": basis, "degenerate": degenerate,
                "min_code": quantize_mod.MIN_CODE,
                "floor_rule": typographic(self._floor_rule(floor, top, degenerate, int(below.sum()), pitch)),
            })
            notes.append(
                "The notebook's C5 display colours each hit's raw energy on a linear ramp with no "
                "floor; this view colours volumetric density on a logarithmic ramp with the "
                "1st-percentile floor of its A1/C2 figure, because cell energies span many decades.")
            return scale, codes, below, top_values, notes
        if self.channel == CHANNEL_SPECIES:
            codes = cubes.species[drawn].astype(np.int64)
            scale = {
                "scale": "categorical", "quantity": "species", "unit": None,
                "codes": [{"code": i, "name": name} for i, name in enumerate(SPECIES_NAMES)],
                "other_code": OTHER_CODE,
                "floor_rule": "No floor: a categorical channel, every cube drawn in its species' colour.",
            }
            return scale, codes, below, top_values, notes
        values = cubes.value[drawn]
        lo, hi = (-1.0, 1.0) if self.channel == CHANNEL_SHAPCAM else (0.0, 1.0)
        colour = scale_mod.attention_scale(values, self.channel, lo, hi, unit)
        codes = quantize_mod.quantize(values, colour)
        scale = colour.as_dict()
        coord = "lab" if self.frame in (FRAME_LAB, KIND_CANONICAL) else self.frame
        network = ddl.NETWORK_FRAME[coord]
        if self.channel == CHANNEL_SHAPCAM:
            scale["zero_code"] = int(quantize_mod.quantize(np.zeros(1), colour)[0])
        missing = int((~np.isfinite(values)).sum())
        how = ("energy-weighted mean over the voxel's sub-deposits" if self.regime == REGIME_SPLAT
               else "the cell's value (energy-weighted over its rows)")
        if self.channel == CHANNEL_SEGERR:
            scale["floor_rule"] = typographic(
                f"No floor: |f_A,pred − f_A,true| of the {network}-frame segmentation network, {how}, "
                "on a fixed linear ramp [0, 1].")
        else:
            name = "Grad-CAM" if self.channel == CHANNEL_GRADCAM else "Shap-CAM (signed)"
            scale["floor_rule"] = typographic(
                f"No floor: the {self.model} network's raw {name} in the {network} frame, {how}, on a "
                f"fixed linear ramp [{lo:g}, {hi:g}]"
                + (", diverging about zero." if self.channel == CHANNEL_SHAPCAM else "."))
        if missing:
            notes.append(f"{missing:,} drawn cubes carry no {self.channel} value and take code 0 (no colour).")
        return scale, codes, below, top_values, notes

    def _energy_range(self, dens: np.ndarray) -> tuple[float, float, bool, str]:
        """``(floor, top, degenerate, basis)`` of the energy ramp over the drawn densities ``dens``.

        The top is the brightest drawn cube. The floor is the 1st percentile of
        the positive densities of what is drawn: the drawn showers' cells in a
        cell frame (:attr:`floor`, the inspector's rule), the drawn voxels
        themselves in a splat frame. The ramp is degenerate when the top does
        not lie above the floor - every drawn cube holds the same density, or
        none holds any.
        """
        positive = dens[dens > 0]
        top = float(positive.max()) if positive.size else 0.0
        if self.regime == REGIME_CELLS:
            floor, basis = float(self.floor), FLOOR_BASIS_CELLS
        else:
            floor = (float(np.percentile(positive, event_inspector.FLOOR_PERCENTILE))
                     if positive.size else 0.0)
            basis = FLOOR_BASIS_VOXELS
        degenerate = not (top > 0.0 and floor > 0.0 and top > floor * (1.0 + DEGENERATE_RTOL))
        return floor, top, degenerate, basis

    def _floor_rule(self, floor: float, top: float, degenerate: bool, n_below: int,
                    pitch: float | None) -> str:
        what = "cube" if self.regime == REGIME_CELLS else "voxel"
        if degenerate:
            if not top > 0.0:
                return (f"No drawn {what} carries positive energy, so the logarithmic density ramp "
                        "has nothing to span and no cube is coloured.")
            return (f"Every drawn {what} holds the same volumetric energy density ({top:.3g} GeV per "
                    "mm³), so the logarithmic ramp is degenerate: vmin = vmax, every cube is drawn in "
                    "the ramp's top colour, and colour carries no contrast in this view.")
        lead = ("Logarithmic ramp of the volumetric energy density E/V in GeV per mm³, from the "
                f"{event_inspector.FLOOR_PERCENTILE:g}st percentile")
        tail = (f"; {n_below:,} {what}s below the floor are drawn at the lowest colour and flagged.")
        if self.regime == REGIME_CELLS:
            return (f"{lead} of the drawn showers' positive cell densities ({floor:.3g}; the Event "
                    f"Inspector's floor, the notebook's A1/C2 vmin) to the brightest cube ({top:.3g})"
                    + tail)
        return (f"{lead} of the drawn {pitch:g} mm voxels' positive densities ({floor:.3g}) to the "
                f"brightest drawn voxel ({top:.3g}). The floor is the voxels' own, not the cells': a "
                "voxel holds only the part of a moved footprint that overlaps it, so voxel densities "
                "run below cell densities, and a floor from the cells would draw a sparse shower "
                "wholly at the lowest colour" + tail)

    def _shower_labels(self) -> list[str]:
        if not self.two:
            # One shower: every row is shower A's, so only code 0 occurs.
            return ["Shower", "—", "—", "—"]
        mixed = ("split cell: rows of more than one origin" if self.regime == REGIME_CELLS
                 else "energy from rows of more than one origin")
        return ["Shower A", "Shower B", "'A+B' row (counted with B)", mixed]

    # ------------------------------------------------------------ species --

    def _species_block(self, cubes: Cubes, drawn: np.ndarray) -> dict[str, Any]:
        """Legend, dictionaries and per-cube species detail."""
        rows, cells = self.rows, self.cells
        codes = rows.codes
        total = float(rows.energy.sum())
        drawn_codes = cubes.species[drawn].astype(np.int64)
        legend = []
        for code in sorted(set(int(c) for c in cells.species)):
            in_cells = cells.species == code
            entry: dict[str, Any] = {
                "code": code, "name": SPECIES_NAMES[code],
                "cells": int(in_cells.sum()),
                "energy_gev": float(rows.energy[codes == code].sum()),
                "energy_fraction": float(rows.energy[codes == code].sum()) / total if total > 0 else 0.0,
                "primary_cells": int((in_cells & cells.primary).sum()),
                "cubes": int((drawn_codes == code).sum()),
            }
            if code == OTHER_CODE:
                members = Counter(MISSING_SPECIES if rows.particle[i] is None else rows.particle[i]
                                  for i in np.flatnonzero(codes == OTHER_CODE))
                entry["members"] = [{"name": name, "rows": int(count)}
                                    for name, count in sorted(members.items())]
            legend.append(entry)
        # Species that bring energy to a cell but dominate none still belong in the legend.
        for code in sorted(set(int(c) for c in codes) - {e["code"] for e in legend}):
            legend.append({
                "code": code, "name": SPECIES_NAMES[code], "cells": 0,
                "energy_gev": float(rows.energy[codes == code].sum()),
                "energy_fraction": float(rows.energy[codes == code].sum()) / total if total > 0 else 0.0,
                "primary_cells": 0, "cubes": 0,
            })
        legend.sort(key=lambda e: e["code"])
        cell_frame = self.regime == REGIME_CELLS

        def packed(values: np.ndarray | None) -> str | None:
            return None if values is None else pack_ordinals(np.asarray(values)[drawn])[0]

        purity = None
        if cubes.purity is not None and (cubes.purity[drawn] < 1.0 - 1e-12).any():
            purity = pack_ordinals(np.rint(np.clip(cubes.purity[drawn], 0.0, 1.0) * 255.0))[0]
        return {
            "codes_in": "cubes.code",
            "legend": legend,
            "parents": list(self.dictionaries.get("parents", [])) if cell_frame else [],
            "daughters": list(self.dictionaries.get("daughters", [])) if cell_frame else [],
            "parent": packed(cubes.parent) if cell_frame else None,
            "n_daughters": packed(cubes.n_daughters) if cell_frame else None,
            "daughter_mode": packed(cubes.daughter_mode) if cell_frame else None,
            "purity": purity,
            "dtype": {"parent": "u8", "n_daughters": "u8", "daughter_mode": "u8", "purity": "u8 (/255)"},
            "none_code": NONE_CODE,
            "rule": typographic(
                "Stable codes across events: e−, e+, γ, neutron, proton, π+, π− take codes 0–6 and every "
                "other particle_type (ions, kaons, a missing value) code 7, whose members are listed; "
                "the notebook's per-event tab20 assignment is not used. A primary-tagged cell "
                "(is_secondary = 0) sets flag bit 2. "
                + ("Each cell shows its own particle_type, its parent (255: none, as for a primary-tagged "
                   "cell) and the number and most frequent of its ;-joined daughters (255: none)."
                   if cell_frame else
                   "A voxel takes the species that brought it the most energy, with that share as its "
                   "purity (u8 / 255; null when every voxel is pure); the primary bit is set when any "
                   "primary-tagged energy lands in it. Parents and daughters are per cell and are shown "
                   "in the cell frames (laboratory, translated).")),
        }

    # ------------------------------------------------------------- blocks --

    def _event_block(self) -> dict[str, Any]:
        event = self.event
        showers = []
        for info in self.infos:
            in_shower = self._rows_of(info.key)
            direction = (frame_mod.unit_direction(info.theta, info.phi)
                         if info.theta is not None and info.phi is not None else None)
            showers.append({
                "key": info.key, "label": info.label,
                "n_hits": int(in_shower.sum()),
                "energy_gev": float(self.rows.energy[in_shower].sum()),
                "momentum_gev": info.momentum,
                "theta": info.theta, "phi": info.phi,
                "theta_deg": math.degrees(info.theta) if info.theta is not None else None,
                "phi_deg": math.degrees(info.phi) if info.phi is not None else None,
                "p0": [float(v) for v in info.p0],
                "first_layer_z": float(info.p0[2]),
                "direction": None if direction is None else [float(v) for v in direction],
            })
        block: dict[str, Any] = {
            "event_number": int(event["event_number"]),
            "in_selection": self.in_selection,
            "prev": self.prev_event,
            "next": self.next_event,
            "n_hits": int(event["n_hits"] or 0),
            "n_cells": int(self.cells.n),
            "d": event["d"],
            "e1": event["e1"],
            "e2": event["e2"],
            "overlap": event["ovl"],
            "shower": showers[0] if len(showers) == 1 else None,
            "showers": showers,
        }
        if self.has_species:
            primary = np.flatnonzero(self.rows.primary)
            block["n_primary_cells"] = int(self.cells.primary.sum())
            if primary.size:
                lead = primary[int(np.argmax(self.rows.energy[primary]))]
                block["primary_species"] = self.rows.particle[lead]
                block["primary_note"] = (
                    "The particle_type of the most energetic primary-tagged cell (the notebook's title "
                    "takes the first such row in file order).")
            else:
                block["primary_species"] = None
                block["primary_note"] = "primary hit missing: no cell of this event is primary-tagged."
        if self.canonical is not None:
            block["d_frame"] = {key: self.canonical[key] for key in
                                ("anchor", "entry_a", "entry_b", "d_entry_mm", "psi", "z_front_mm",
                                 "ill_conditioned")}
        return block

    def _rows_of(self, key: str) -> np.ndarray:
        if not self.two:
            return np.ones(self.rows.n, dtype=bool)
        return self.rows.org == ddl.ORIGIN_A if key == "a" else self.rows.org != ddl.ORIGIN_A

    def _coordinates_block(self) -> dict[str, Any]:
        tolerance = shower_frames.COORDINATE_TOLERANCE_MM
        residual = self.residual
        within = None if residual is None else bool(residual <= tolerance)
        if self.frame == KIND_LOCAL:
            source = self.source
            note = (("Coordinates: the file's own x/y/z_local; " if source == frame_sql.SOURCE_FILE
                     else "Coordinates: recomputed from the laboratory lattice by the stated SE(3) motion; ")
                    + "the motion (P₀ subtracted, then R(θ, φ) applied) was also applied to every cell here, "
                    f"and the two differ by at most {residual:.3g} mm"
                    + (" (within" if within else " (above") + f" the {tolerance:g} mm tolerance).")
        elif self.frame == KIND_TRANS:
            source = "lattice"
            note = ("Cube positions are the laboratory lattice coordinates minus P₀; the file's x/y_trans "
                    f"and own-shower layers differ from them by at most {residual:.3g} mm"
                    + (" (within" if within else " (above") + f" the {tolerance:g} mm tolerance).")
        elif self.frame == KIND_CANONICAL:
            source = "lattice"
            note = ("Cube positions are the laboratory lattice moved by the event's D-frame motion (the "
                    "midpoint of the two back-projected entry points to the origin, A→B along +x′), "
                    "computed from the lattice as the ensemble D-frame is; the per-shower coordinate "
                    "columns are not read.")
        else:
            source = "lattice"
            note = ("Cube positions are the laboratory lattice coordinates measured at ingest; the "
                    "per-shower coordinate columns are not read in this frame.")
        return {"source": source, "residual_max_mm": residual, "tolerance_mm": tolerance,
                "within_tolerance": within, "note": typographic(note)}

    def _window_block(self) -> dict[str, Any]:
        centred = self.frame in (KIND_LOCAL, KIND_CANONICAL)
        return {
            "half_mm": self.half, "pad": event_inspector.WINDOW_PAD,
            "min_half_mm": event_inspector.WINDOW_MIN_HALF_MM,
            "axes": {axis: [float(v) for v in self.windows[axis]] for axis in "xyz"},
            "rule": typographic(
                f"One half-width for the three axes: {event_inspector.WINDOW_PAD:g} × half the largest "
                f"extent of the drawn cells in this frame, never below "
                f"{event_inspector.WINDOW_MIN_HALF_MM:.0f} mm ({self.half:.0f} mm here)"
                + ("; symmetric about the origin across the beam" if centred else "")
                + "; cells snap it to whole cells, voxels to whole bins."),
        }


# ------------------------------------------------------------------ build --


def build(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    event_number: int,
    frame: str = DEFAULT_FRAME,
    shower: str = "a",
    channel: str = CHANNEL_ENERGY,
    model: str = "segmentation",
    source: str = frame_sql.SOURCE_FILE,
    footprint: tuple[float, float] | None = None,
) -> Builder:
    """Read the event once and prepare its frame; :meth:`Builder.assemble` renders it.

    ``shower`` is the key :func:`resolve` returned. A missing event, an event
    with no row of the shower asked for, and an event the frame cannot place
    (no direction or entry point; no D-frame columns) are 404s.
    """
    assert record.lattice is not None
    started = time.perf_counter()
    lat = record.lattice
    pitch_z = (float(record.frame_bounds.layer_pitch_mm) if record.frame_bounds is not None
               else float(lat.z.mean_pitch))
    fp = footprint or frame_mod.footprint_from_lattice(lat)
    two = len(showers_mod.of(record)) == 2
    drawn = showers_mod.of(record, shower)

    event = _event_row(con, record, event_number)
    in_selection, prev_event, next_event = _neighbours(con, record, spec, event_number)
    coord = "lab" if frame in (FRAME_LAB, KIND_CANONICAL) else frame
    species = bool(record.traits is not None and record.traits.has_species)
    shower_sql = "TRUE" if shower == "both" else drawn[0].origin_sql
    rows = _voxel_rows(con, record, event_number, shower_sql, channel, model, coord, species)

    infos = []
    for s in drawn:
        p0 = np.array([event[ddl.p0_column(s.key, axis)] if event[ddl.p0_column(s.key, axis)] is not None
                       else np.nan for axis in "xyz"], dtype=np.float64)
        infos.append(_ShowerInfo(
            key=s.key, label=event_inspector.SHOWERS[s.key] if two else s.label, p0=p0,
            theta=None if event[s.theta] is None else float(event[s.theta]),
            phi=None if event[s.phi] is None else float(event[s.phi]),
            momentum=None if event[s.momentum] is None else float(event[s.momentum]),
        ))
    if rows.n == 0:
        what = "" if shower == "both" else (f" attributed to shower {infos[0].label}" if two else "")
        raise NotFoundError(f"Event {event_number} has no hit{what}, so there is nothing to draw.")

    cells = merge_cells(rows.ix, rows.iy, rows.iz, rows.org, rows.energy,
                        value=rows.value, primary=rows.primary, species=rows.codes)
    lab = np.column_stack([lat.x.coords[rows.ix], lat.y.coords[rows.iy], lat.z.coords[rows.iz]])

    residual: float | None = None
    rotation = None
    canonical_info = None
    if frame in (KIND_TRANS, KIND_LOCAL):
        info = infos[0]
        if not np.isfinite(info.p0).all() or info.theta is None or info.phi is None:
            raise NotFoundError(
                f"Event {event_number}'s shower {info.label} has no incident direction or entry point "
                "P0, so it has no per-shower frame.")
        translated = frame_mod.per_shower_translated(info.p0).apply(lab)
        local = frame_mod.per_shower_local(info.p0, info.theta, info.phi).apply(lab)
        file_trans = rows.file_trans * np.array([1.0, 1.0, pitch_z])
        if frame == KIND_TRANS:
            residual = float(np.abs(translated - file_trans).max())
            centres = translated
        else:
            residual = float(np.abs(local - rows.file_local).max())
            centres = rows.file_local if source == frame_sql.SOURCE_FILE else local
            rotation = frame_mod.rotation_matrix(info.theta, info.phi)
    elif frame == KIND_CANONICAL:
        names = frame_sql.frame_columns(frame_sql.ANCHOR_BACKPROJECTED)
        table = quote(naming.event_table(record.table_name))
        values = con.execute(f"SELECT {', '.join(names)} FROM {table} WHERE event_number = ?",
                             [int(event_number)]).fetchone()
        columns = dict(zip(names, values))
        if any(v is None for v in values):
            raise NotFoundError(
                f"Event {event_number} has no D-frame: its separation, a shower's centroid or its "
                "incident direction is undefined, so the two entry anchors cannot be placed.")
        zf = float(lat.z.lo)
        xa, ya = frame_mod.entry_anchor(columns["cax"], columns["cay"], columns["caz"],
                                        columns["theta_a"], columns["phi_a"], zf)
        xb, yb = frame_mod.entry_anchor(columns["cbx"], columns["cby"], columns["cbz"],
                                        columns["theta_b"], columns["phi_b"], zf)
        motion = frame_mod.per_event_canonical(np.array([xa, ya]), np.array([xb, yb]), zf)
        centres = motion.apply(lab)
        rotation = motion.r
        d_entry = float(math.hypot(float(xb - xa), float(yb - ya)))
        canonical_info = {
            "anchor": frame_sql.ANCHOR_BACKPROJECTED,
            "entry_a": [float(xa), float(ya)], "entry_b": [float(xb), float(yb)],
            "d_entry_mm": d_entry, "psi": float(math.atan2(float(yb - ya), float(xb - xa))),
            "z_front_mm": zf,
            "ill_conditioned": bool(d_entry < frame_mod.ILL_CONDITIONED_D_MM),
        }
    else:
        centres = lab

    centred = frame in (KIND_LOCAL, KIND_CANONICAL)
    half = _window_half([centres[:, 0], centres[:, 1], centres[:, 2]],
                        centres[:, :2] if centred else np.zeros((0, 2)))
    windows = {
        axis: ((-half, half) if centred and axis != "z" else
               (_mid(centres[:, i]) - half, _mid(centres[:, i]) + half))
        for i, axis in enumerate("xyz")
    }
    # The cell frames' floor: the 1st percentile of the drawn cells' positive densities (one
    # volume, so of energies). The splat frames take theirs from the drawn voxels (_energy_range).
    positive = cells.energy[cells.energy > 0]
    cell_volume = float(fp[0] * fp[1] * pitch_z)
    floor = (float(np.percentile(positive, event_inspector.FLOOR_PERCENTILE)) / cell_volume
             if positive.size else 0.0)

    builder = Builder(
        record=record, frame=frame, shower=shower, channel=channel, model=model, source=source,
        footprint=(float(fp[0]), float(fp[1])), pitch_z=pitch_z, event=event,
        in_selection=in_selection, prev_event=prev_event, next_event=next_event, infos=infos,
        rows=rows, cells=cells, centres=centres, rotation=rotation, half=half, windows=windows,
        floor=floor, residual=residual, canonical=canonical_info, started=started,
    )
    if canonical_info is not None:
        # Depth: the populated native layers inside the window, by ordinal.
        lo, hi = windows["z"]
        # Half-open [i0, i1): one depth bin per native layer, the ordinal binned exactly.
        canonical_info["layers"] = _lattice_crop(lat.z.coords - canonical_info["z_front_mm"], rows.iz, lo, hi)
    if frame not in CELL_FRAMES:
        builder.k = max(frame_mod.MIN_SUBSAMPLE, EVENT_SPLAT_K)
        builder.k_z = max(frame_mod.LOCAL_K_Z, EVENT_LOCAL_K_Z) if frame == KIND_LOCAL else 1
        pitch = event_inspector.START_PITCH_MM
        # Coarsen up front only while an index would not fit one byte: the grid's own bin count
        # over the cells' extent, not the 2-D raster's 96-bin rule. Size is the guard's to trade.
        start = max(edges.size - 1 for edges in builder.transverse_edges(pitch))
        while pitch < event_inspector.MAX_PITCH_MM and \
                max(edges.size - 1 for edges in builder.transverse_edges(pitch)) > MAX_VOXELS_PER_AXIS:
            pitch *= 2.0
        builder.first_pitch = pitch
        if pitch > event_inspector.START_PITCH_MM:
            builder.build_notes.append(
                f"The {event_inspector.START_PITCH_MM:.0f} mm voxels were coarsened to {pitch:.0f} mm: at "
                f"{event_inspector.START_PITCH_MM:.0f} mm the grid over the drawn cells would put {start:,} "
                f"voxels on a transverse axis, more than the {MAX_VOXELS_PER_AXIS} a one-byte index "
                "addresses.")
    if channel == CHANNEL_SPECIES and rows.parent is not None:
        builder.dictionaries = {
            "parents": sorted({name for name in rows.parent if name is not None}),
            "daughters": sorted({t for text in rows.daughters for t in daughter_tokens(text)}),
        }
        for key in ("parents", "daughters"):
            # u8 codes with 255 for none: names past the 255th take "none", and say so.
            names = builder.dictionaries[key]
            if len(names) > NONE_CODE:
                builder.dictionaries[key] = names[:NONE_CODE]
                builder.build_notes.append(
                    f"This event names {len(names):,} distinct {key}; the first {NONE_CODE} "
                    f"alphabetically have codes, the other {len(names) - NONE_CODE:,} are shown as none.")
    return builder


def cam_note(builder: Builder) -> dict[str, Any] | None:
    """``meta.cam`` for a CAM channel: which column, which network, how a cube aggregates it."""
    if builder.channel not in (CHANNEL_GRADCAM, CHANNEL_SHAPCAM):
        return None
    coord = "lab" if builder.frame in (FRAME_LAB, KIND_CANONICAL) else builder.frame
    note = planes.cam_note(builder.model, coord, builder.channel)
    if note is not None:
        note = {**note, "aggregation": (
            "energy-weighted mean of the raw value over the voxel's sub-deposits"
            if builder.regime == REGIME_SPLAT else
            "the cell's raw value (per-voxel, repeated on every row; energy-weighted over a split cell's rows)"),
            "note": typographic(
                f"One event's raw {('Grad-CAM' if builder.channel == CHANNEL_GRADCAM else 'Shap-CAM')} "
                f"map of the {builder.model} network, normalised per "
                f"{'event' if builder.model == 'segmentation' else 'shower'}.")}
    return note
