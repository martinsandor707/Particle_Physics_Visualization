"""Ensemble 3-D voxels of the co-registered frames: the data behind ``GET /api/voxels``.

The Page-2 ensemble card draws the whole selection's energy as a cloud of
axis-aligned cubes in the Local frame (every shower on its own entry point and
incident direction) or the D-frame (every event on the midpoint of its two
entry points). It is built from the same keyed sub-deposits as the 2-D panels
of those frames, so a cell's footprint is splatted exactly as there - never
dropped at its centre:

* **One scan, two levels.** The keyed CTE (``shower_frames._local_base_sql``,
  ``canonical._canonical_base_sql``) is aggregated to the raw 20 mm 3-D
  accumulation grid and, in the same query, those fine bins to 40 mm voxels.
  The second level keeps each voxel's raw fine-bin *peaks* beside its sums, so
  the reference density is the raw grid's maximum without fetching the fine
  grid. Only the planes the channels read are projected (``VOXEL_PLANES``):
  no segmentation fraction, no count-weighted CAM.
* **Merged about the origin.** The fine bins of each transverse axis are paired
  ``(b - 1, b)`` across the origin (:class:`MergedAxis`), so the origin - each
  shower's entry point, or the midpoint of the two - runs through the centre of
  one voxel column instead of along a voxel edge, where it would split the
  shower core over four columns. When an axis holds an even number of bin pairs
  the outermost voxel on each side is half a voxel wide; it lies at the far
  edge of the accumulation grid, is not drawn, and its energy is counted.
  Depth is never merged: uniform layer-pitch bins along w, or the native
  layers in the D-frame.
* **Density, reference and floor.** ``rho_v = E_v / (N dV_v)`` per voxel, in
  GeV/mm^3/event, with N the frame's co-registered events. ``rho_ref`` is the
  raw 20 mm grid's 3-D peak; each voxel is the mean of its four fine bins
  (empty ones counting zero), so ``rho_v <= rho_ref`` always. A voxel is drawn
  iff ``rho_v >= 10^-3 rho_ref`` (or, for the energy-weighted CAM channels,
  ``|value| >= 10^-3`` of the channel's own raw peak); the rest are counted
  with their energy, never shipped.
* **Cap by energy.** Of the voxels above the floor the brightest ``cap`` by
  energy are shipped - one stated rule for every channel - and the remainder's
  energy is counted beyond the cap. Every joule of the selection lands in
  exactly one of drawn, below floor, beyond cap, partial edge or outside the
  grid, and the five fractions sum to one.
* **Layer-run packing.** The drawn voxels travel as integers only (CLAUDE.md
  section 1.1: never raw hit positions): sorted by depth, then y, then x, with
  a count per layer, one ``(x, y)`` ordinal pair and one colour code per voxel
  - three bytes a voxel, about 60 KB of base64 at the 15 000 cap. The 64
  brightest carry their exact value and energy (``topk``).

The comb is never measured here: a merged grid would hide it. The route quotes
the matching 2-D bundle's raw-grid measurement when that bundle is cached
(:func:`cached_2d_bundle`), and says it was not measured otherwise.

**One heavy scan at a time.** The fine 3-D aggregate of a production D-frame
selection is millions of groups. A cold scan runs through
``physics_cache``'s single flight and its process-wide one-heavy-scan gate
(:func:`_scan_once`), so two identical cold requests share one scan and no
voxel scan ever runs beside another heavy hit scan; the bundle itself lives in
the voxel cache.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import duckdb
import numpy as np

from ..config import Settings
from ..db import ddl
from ..db.registry import ExperimentRecord
from ..encode import quantize
from ..encode import scale as scale_mod
from ..encode.numbers import sig
from ..encode.voxels import b64, pack_layer_runs
from ..grid import frame as frame_mod
from ..grid.frame import CanonicalGrid, KIND_CANONICAL, KIND_LOCAL
from ..text import typographic
from . import cache as cache_mod
from . import canonical, density, hit_sql, physics_cache, shower_frames
from . import planes as planes_mod
from .canonical import FrameStats, _column
from .filters import FilterSpec
from .frame_sql import ANCHOR_BACKPROJECTED, SOURCE_FILE
from .shower_frames import ShowerStats

log = logging.getLogger(__name__)

#: Bumped whenever the cached bundle's meaning changes.
VOXEL_VERSION = 1

#: The frames a 3-D ensemble is accumulated in. The per-shower translated
#: frame integrates each footprint by exact box overlap, which has no 3-D form
#: yet; the route refuses it with that reason.
FRAMES: tuple[str, ...] = (KIND_LOCAL, KIND_CANONICAL)

CHANNELS: tuple[str, ...] = (
    planes_mod.CHANNEL_DENSITY, planes_mod.CHANNEL_GRADCAM_ENERGY, planes_mod.CHANNEL_SHAPCAM_ENERGY,
)

#: The planes the voxel scan sums, of those the experiment measures: energy,
#: the hit count, and the energy-weighted CAM parts the two attention channels
#: read. Segmentation fractions and count-weighted CAM are never projected.
VOXEL_PLANES: tuple[str, ...] = ("e", "n", "eg", "esp", "esn")

#: Fine bins merged per voxel along each transverse axis.
MERGE = 2

#: Voxels shipped at most, and the smallest cap a request may ask for. At three
#: bytes a voxel the default cap is 60 000 base64 characters, about 70 KB with
#: everything around it; the whole-body guard lowers it if that ever overruns.
DEFAULT_CAP = 15_000
MIN_CAP = 1_000

#: Drawn voxels that carry their exact value and energy.
TOPK = 64

RHO_UNIT = "GeV/mm^3/event"

#: The display floor as a fraction of the reference: 10^-3.
FLOOR_RATIO = 10.0 ** -frame_mod.RAMP_DECADES

#: The first colour code a drawn voxel can take: code 1 is "below the floor"
#: in the 2-D panels and is never shipped here.
MIN_DRAWN_CODE = quantize.BELOW_CODE + 1

#: Cache-key kinds, so a voxel bundle never collides with a 2-D one.
CACHE_KIND = {KIND_LOCAL: "local_voxels", KIND_CANONICAL: "canonical_voxels"}

SYMBOLS = {KIND_LOCAL: shower_frames.SYMBOLS[KIND_LOCAL], KIND_CANONICAL: density.SYMBOLS}

TITLE = {KIND_LOCAL: "Local", KIND_CANONICAL: "D-frame"}

#: What the merge centres a voxel column on, in each frame.
ORIGIN = {
    KIND_LOCAL: "each shower's own entry point P0, on its w axis",
    KIND_CANONICAL: "the midpoint of each event's two entry points",
}

#: Keys whose string values are packed bytes or identifiers, never sentences:
#: :func:`typeset` leaves them as they are.
VERBATIM_KEYS = frozenset({"layer_counts", "xy", "code", "table_name", "column"})


def typeset(node: Any, key: str | None = None) -> Any:
    """Every sentence of a payload block with U+2212 for a signed number (``text.typographic``).

    Applied to the whole body, so a sentence written later cannot escape it;
    the packed bytes and identifiers of :data:`VERBATIM_KEYS` are left alone.
    """
    if isinstance(node, str):
        return node if key in VERBATIM_KEYS else typographic(node)
    if isinstance(node, dict):
        return {k: typeset(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [typeset(v, key) for v in node]
    return node


# ------------------------------------------------------------------ merge --


@dataclass(frozen=True)
class MergedAxis:
    """One transverse axis of the 2 x 2 merge, aligned so the origin is a voxel centre.

    The accumulation grid holds ``n_fine = 2 b`` bins of ``pitch`` over
    ``[-half, +half]``; bin ``j`` covers ``[-half + pitch j, +pitch)``, so the
    origin is the edge between bins ``b - 1`` and ``b``. With ``offset =
    (b - 1) mod 2`` the voxel index ``v = (j + offset) // 2`` puts those two
    bins in one voxel, centred at 0. When ``b`` is even the first and last
    voxels hold one bin each: half-width, at the grid's outer edge.
    """

    half: float
    pitch: float
    n_fine: int
    offset: int

    @property
    def n(self) -> int:
        """Voxel indices along the axis, half-width ones included."""
        return (self.n_fine - 1 + self.offset) // 2 + 1

    @property
    def partial(self) -> bool:
        return self.offset == 1

    @property
    def first_full(self) -> int:
        return self.offset

    @property
    def n_full(self) -> int:
        return self.n - 2 * self.offset

    def centre(self, v: Any) -> Any:
        """Centre of voxel ``v`` in mm (a full voxel's; a half-width one is off by pitch/2)."""
        return -self.half + self.pitch * (2 * np.asarray(v) - self.offset + 1)

    def is_partial(self, v: np.ndarray) -> np.ndarray:
        v = np.asarray(v)
        if not self.partial:
            return np.zeros(v.shape, dtype=bool)
        return (v == 0) | (v == self.n - 1)

    def of_fine(self, j: Any) -> Any:
        return (np.asarray(j) + self.offset) // MERGE


def merged_axis(half: float, pitch: float) -> MergedAxis:
    """The merge of a symmetric axis of whole bins (``grid/frame.py`` snaps every half-width up)."""
    n_fine = int(round(2.0 * float(half) / float(pitch)))
    if n_fine < 2 or n_fine % 2:
        raise ValueError(f"a merged axis needs an even number of fine bins, got {n_fine}")
    b = n_fine // 2
    return MergedAxis(float(half), float(pitch), n_fine, (b - 1) % 2)


def depth_pitch(record: ExperimentRecord, kind: str) -> float:
    """Thickness of one depth bin: the layer pitch, in both frames.

    The local frame bins w at the layer pitch; the D-frame keeps native layers,
    each one sampling slab of that pitch thick, whichever layers a selection
    happens to populate.
    """
    if kind == KIND_LOCAL:
        assert record.frame_bounds is not None
        return float(record.frame_bounds.layer_pitch_mm)
    return float(hit_sql.layer_pitch(record))


# ----------------------------------------------------------------- bundle --


@dataclass
class VoxelBundle:
    """The 40 mm voxel sums and raw 20 mm peaks of one selection in one frame.

    Only the voxels the scan populated inside the grid are held, as int16
    indices; the outside-grid group is reduced to its sums.
    """

    kind: str
    grid: CanonicalGrid
    x: MergedAxis
    y: MergedAxis
    dz: float
    vx: np.ndarray
    vy: np.ndarray
    vz: np.ndarray
    sums: dict[str, np.ndarray]
    peaks: dict[str, np.ndarray]
    outside: dict[str, float]
    n_events: int
    subsample_k: int
    k_z: int
    footprint: tuple[float, float]
    sampled: bool
    query_ms: float
    measured: tuple[str, ...]
    model: str = "segmentation"
    anchor: str = ANCHOR_BACKPROJECTED
    coordinate_source: str = SOURCE_FILE
    coordinate_residual_mm: float | None = None
    sample_percent: float = 100.0

    @property
    def exact(self) -> bool:
        return not self.sampled

    @property
    def z_centres(self) -> np.ndarray:
        return np.asarray(self.grid.z_coords, dtype=np.float64)

    @property
    def total_energy(self) -> float:
        """The selection's energy: inside the grid, half-width voxels included, plus outside."""
        return float(self.sums["e"].sum()) + float(self.outside.get("e", 0.0))

    @property
    def n_hits(self) -> int:
        return int(round(float(self.sums["n"].sum()) + float(self.outside.get("n", 0.0))))

    @property
    def nbytes(self) -> int:
        arrays = [self.vx, self.vy, self.vz, *self.sums.values(), *self.peaks.values()]
        return int(sum(a.nbytes for a in arrays)) + 512


def measured_planes(record: ExperimentRecord) -> tuple[str, ...]:
    """The voxel planes the experiment measures: energy and count without networks."""
    measured = planes_mod.measured_planes(record)
    return tuple(p for p in VOXEL_PLANES if p in measured)


def _voxel_params(record: ExperimentRecord, spec: FilterSpec, kind: str,
                  footprint: tuple[float, float]) -> dict[str, Any]:
    if kind == KIND_LOCAL:
        return shower_frames._params(record, spec)
    return canonical._params(record, spec, footprint)


def build_sql(
    record: ExperimentRecord,
    spec: FilterSpec,
    kind: str,
    grid: CanonicalGrid,
    footprint: tuple[float, float],
    k: int,
    k_z: int,
    model: str = "segmentation",
    sampled: bool = False,
    source: str = SOURCE_FILE,
    anchor: str = ANCHOR_BACKPROJECTED,
) -> str:
    """The one voxel query: fine 3-D sums, then their 2 x 2 merge with the fine peaks.

    The keyed CTE marks every sub-deposit outside the grid -1 on all three
    axes; that group passes through both levels as the single ``vx = -1`` row,
    which carries the outside mass.
    """
    planes = measured_planes(record)
    ax, ay = merged_axis(grid.half_x, grid.pitch), merged_axis(grid.half_y, grid.pitch)
    if kind == KIND_LOCAL:
        base = shower_frames._local_base_sql(
            record, spec, grid, footprint, depth_pitch(record, kind), k, k_z, model, sampled,
            source, planes=planes)
        depth, residual = "jz", True
    elif kind == KIND_CANONICAL:
        base = canonical._canonical_base_sql(record, spec, grid, k, sampled, model, anchor,
                                             planes=planes)
        depth, residual = "iz", False
    else:  # pragma: no cover - the route validates first
        raise ValueError(f"no 3-D accumulation for frame {kind!r}")
    fine_sums = ", ".join(f"sum(v_{p}) AS {p}" for p in planes)
    sums = ", ".join(f"sum({p}) AS {p}" for p in planes)
    peaks = ["max(e) AS e_peak"]
    if "eg" in planes:
        peaks.append("max(eg) AS eg_peak")
    if "esp" in planes:
        peaks.append("max(abs(esp + esn)) AS s_peak")
    resid = ", max(resid) AS resid" if residual else ""
    return base + f"""
    , fine AS (
        SELECT jx, jy, {depth} AS jz, {fine_sums}{resid}
        FROM keyed GROUP BY jx, jy, {depth}
    )
    SELECT CASE WHEN jx < 0 THEN -1 ELSE (jx + {ax.offset}) // {MERGE} END AS vx,
           CASE WHEN jy < 0 THEN -1 ELSE (jy + {ay.offset}) // {MERGE} END AS vy,
           jz AS vz,
           {sums}, {", ".join(peaks)}{resid}
    FROM fine GROUP BY ALL"""


def fetch(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    kind: str,
    n_events: int,
    grid: CanonicalGrid,
    footprint: tuple[float, float],
    k: int,
    k_z: int,
    model: str = "segmentation",
    sampled: bool = False,
    sample_percent: float = 100.0,
    source: str = SOURCE_FILE,
    anchor: str = ANCHOR_BACKPROJECTED,
) -> VoxelBundle:
    """Run the voxel query and hold its inside voxels and outside sums."""
    if k < frame_mod.MIN_SUBSAMPLE:
        raise ValueError(f"a rotated footprint is never point-binned: k = {k} < {frame_mod.MIN_SUBSAMPLE}")
    sql = build_sql(record, spec, kind, grid, footprint, k, k_z, model, sampled, source, anchor)
    params = _voxel_params(record, spec, kind, footprint)
    started = time.perf_counter()
    columns = con.execute(sql, params).fetchnumpy()
    query_ms = (time.perf_counter() - started) * 1000.0

    planes = measured_planes(record)
    ax, ay = merged_axis(grid.half_x, grid.pitch), merged_axis(grid.half_y, grid.pitch)

    def index(name: str) -> np.ndarray:
        return np.nan_to_num(_column(columns, name), nan=-1).astype(np.int64)

    vx, vy, vz = index("vx"), index("vy"), index("vz")
    # The outside group is (-1, -1, -1). A key a rounding ulp past the last bin
    # would be folded into it too rather than index past the grid.
    inside = (vx >= 0) & (vx < ax.n) & (vy >= 0) & (vy < ay.n) & (vz >= 0) & (vz < grid.n_z)
    stray = int((~inside & ~((vx == -1) & (vy == -1) & (vz == -1))).sum())
    if stray:  # pragma: no cover - only a key at the floating edge of the grid
        log.debug("%d voxel group(s) keyed past the grid were counted outside", stray)
    sums = {p: np.nan_to_num(_column(columns, p))[inside] for p in planes}
    outside = {p: float(np.nan_to_num(_column(columns, p))[~inside].sum()) for p in planes}
    for p in VOXEL_PLANES:
        sums.setdefault(p, np.zeros(int(inside.sum())))
        outside.setdefault(p, 0.0)
    peaks = {"e": np.nan_to_num(_column(columns, "e_peak"))[inside]}
    peaks["eg"] = (np.nan_to_num(_column(columns, "eg_peak"))[inside] if "eg" in planes
                   else np.zeros(int(inside.sum())))
    peaks["s"] = (np.nan_to_num(_column(columns, "s_peak"))[inside] if "esp" in planes
                  else np.zeros(int(inside.sum())))
    residual = shower_frames._residual(columns) if kind == KIND_LOCAL else None

    bundle = VoxelBundle(
        kind=kind, grid=grid, x=ax, y=ay, dz=depth_pitch(record, kind),
        vx=vx[inside].astype(np.int16), vy=vy[inside].astype(np.int16),
        vz=vz[inside].astype(np.int16),
        sums=sums, peaks=peaks, outside=outside, n_events=int(n_events),
        subsample_k=int(k), k_z=int(k_z), footprint=(float(footprint[0]), float(footprint[1])),
        sampled=sampled, query_ms=query_ms, measured=planes, model=model,
        anchor=anchor, coordinate_source=source, coordinate_residual_mm=residual,
        sample_percent=sample_percent,
    )
    log.debug("%s voxel scan for %s in %.1f ms (%d voxels, k=%d, k_z=%d, sampled=%s)",
              kind, record.table_name, query_ms, bundle.vx.size, k, k_z, sampled)
    return bundle


def scale_sample(bundle: VoxelBundle, percent: float) -> VoxelBundle:
    """Scale a sampled bundle's sums and peaks to full-population estimates.

    Every plane is a sum, so a Bernoulli sample estimates it without bias up to
    the inclusion probability; the peaks are maxima of such sums and scale
    with them. N comes from the exact event table.
    """
    factor = 100.0 / percent if percent > 0 else 1.0
    for values in (*bundle.sums.values(), *bundle.peaks.values()):
        values *= factor
    bundle.outside = {p: v * factor for p, v in bundle.outside.items()}
    bundle.sample_percent = percent
    return bundle


def explain(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    kind: str,
    grid: CanonicalGrid,
    footprint: tuple[float, float],
    k: int,
    k_z: int,
    model: str = "segmentation",
    sampled: bool = False,
    source: str = SOURCE_FILE,
    anchor: str = ANCHOR_BACKPROJECTED,
) -> str:
    """``EXPLAIN`` of the voxel query, for the single-scan test."""
    sql = build_sql(record, spec, kind, grid, footprint, k, k_z, model, sampled, source, anchor)
    rows = con.execute("EXPLAIN " + sql, _voxel_params(record, spec, kind, footprint)).fetchall()
    return "\n".join(str(r[-1]) for r in rows)


# ------------------------------------------------------------------ cache --


def cache_for(settings: Settings) -> cache_mod.BundleCache:
    return cache_mod.get_cache(settings.canonical_cache_entries, name=cache_mod.VOXEL_CACHE)


def cache_key(spec: FilterSpec, sampled: bool, kind: str, grid: CanonicalGrid, k: int, k_z: int,
              footprint: tuple[float, float], model: str, anchor: str, source: str) -> tuple:
    """Identity of a voxel bundle: the 2-D bundle's key under its own kind, versioned.

    ``spec`` must already be clamped. The channel and cap are left out: both
    re-render from the same bundle.
    """
    return (*canonical.cache_key(spec, sampled, grid, k, footprint, model, kind=CACHE_KIND[kind],
                                 k_z=k_z, anchor=anchor, source=source), VOXEL_VERSION)


def plan(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    kind: str,
    footprint: tuple[float, float],
    sampled: bool,
    percent: float,
    model: str = "segmentation",
    anchor: str = ANCHOR_BACKPROJECTED,
) -> tuple[ShowerStats | FrameStats, CanonicalGrid, int, int]:
    """``(stats, grid, k, k_z)`` exactly as the frame's 2-D bundle chooses them.

    Local: ``shower_statistics`` and the dataset's ``plan_shower_window``,
    ``k`` from ``choose_subsample_3d`` at the default ``k_z``. D-frame:
    ``frame_statistics`` and the selection's ``plan_window``, ``k`` from
    ``choose_subsample``, one depth sample (native layers). Both cap ``k`` for
    the drag preview, and never go below ``MIN_SUBSAMPLE``.
    """
    spec = spec.clamped(record)
    if kind == KIND_LOCAL:
        assert record.frame_bounds is not None
        stats: ShowerStats | FrameStats = shower_frames.shower_statistics(
            con, record, spec, KIND_LOCAL, model)
        grid = frame_mod.plan_shower_window(KIND_LOCAL, record.frame_bounds, footprint)
        k_z = frame_mod.LOCAL_K_Z
        rows = int(round(stats.n_hits * (percent / 100.0 if sampled else 1.0)))
        k = frame_mod.choose_subsample_3d(rows, k_z)
    else:
        assert record.lattice is not None
        stats = canonical.frame_statistics(con, record, spec, anchor, max(footprint))
        grid = frame_mod.plan_window(stats.d_entry_max, stats.theta_max, record.lattice)
        k_z = 1
        rows = int(round(stats.n_hits * (percent / 100.0 if sampled else 1.0)))
        k = frame_mod.choose_subsample(rows)
    if sampled:
        k = min(k, frame_mod.PREVIEW_MAX_SUBSAMPLE)
    return stats, grid, k, k_z


def bundle_for(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    settings: Settings,
    kind: str,
    footprint: tuple[float, float],
    sampled: bool,
    percent: float,
    model: str = "segmentation",
    anchor: str = ANCHOR_BACKPROJECTED,
    source: str = SOURCE_FILE,
    any_model: bool = False,
) -> tuple[VoxelBundle, ShowerStats | FrameStats, CanonicalGrid, int, bool]:
    """Statistics, grid, sub-sampling factor and the (cached) voxel bundle.

    Returns ``(bundle, stats, grid, k, was_cached)``. ``any_model`` serves
    density from whichever network's bundle of the selection is cached: it
    reads no CAM plane. A cold bundle is scanned through :func:`_scan_once`.
    Not warmed at boot: the card asks for it.
    """
    clamped = spec.clamped(record)
    stats, grid, k, k_z = plan(con, record, clamped, kind, footprint, sampled, percent, model, anchor)
    if kind == KIND_CANONICAL:
        source = SOURCE_FILE
    else:
        anchor = ANCHOR_BACKPROJECTED
    cache = cache_for(settings)
    key = cache_key(clamped, sampled, kind, grid, k, k_z, footprint, model, anchor, source)
    keys = [key]
    if any_model:
        keys += [cache_key(clamped, sampled, kind, grid, k, k_z, footprint, m, anchor, source)
                 for m in ddl.MODELS if m != model]
    # A cached bundle never queues behind the heavy-scan gate.
    hit = cache.get_any(keys)
    if hit is not None:
        return hit, stats, grid, k, True

    def compute() -> VoxelBundle:
        bundle = fetch(con, record, clamped, kind, stats.n_events, grid, footprint, k, k_z,
                       model=model, sampled=sampled, sample_percent=percent, source=source,
                       anchor=anchor)
        if sampled:
            scale_sample(bundle, percent)
        return bundle

    bundle, was_cached = _scan_once(cache, key, compute)
    return bundle, stats, grid, k, was_cached


def _scan_once(cache: cache_mod.BundleCache, key: tuple,
               compute: Callable[[], VoxelBundle]) -> tuple[VoxelBundle, bool]:
    """``(bundle, was_cached)``: ``physics_cache``'s single flight and heavy-scan gate, the voxel cache's store.

    Identical cold requests share one computation, and one heavy scan runs at
    a time across the process, physics cards included. The bundle is stored in
    the voxel cache: one production voxel bundle in the 64 MiB physics cache
    would evict every physics card's entry.
    """
    return physics_cache.get_or_compute(key, compute, heavy=True, cache=cache)


def cached_2d_bundle(settings: Settings, record: ExperimentRecord, spec: FilterSpec,
                     bundle: VoxelBundle) -> Any | None:
    """The matching 2-D bundle (same selection, sampling, grid, k, k_z, anchor or source), if cached.

    Never computed: the comb is the 2-D panels' measurement on their raw
    grid, quoted here only when they have made it. Any network's bundle
    serves, since the comb is read from the energy plane.
    """
    clamped = spec.clamped(record)
    if bundle.kind == KIND_LOCAL:
        cache = shower_frames.cache_for(settings, KIND_LOCAL)
        keys = [canonical.cache_key(clamped, bundle.sampled, bundle.grid, bundle.subsample_k,
                                    bundle.footprint, m, kind=KIND_LOCAL, k_z=bundle.k_z,
                                    source=bundle.coordinate_source)
                for m in (bundle.model, *ddl.MODELS)]
    else:
        cache = cache_mod.get_cache(settings.canonical_cache_entries, name=cache_mod.CANONICAL_CACHE)
        keys = [canonical.cache_key(clamped, bundle.sampled, bundle.grid, bundle.subsample_k,
                                    bundle.footprint, m, anchor=bundle.anchor)
                for m in (bundle.model, *ddl.MODELS)]
    return cache.get_any(keys)


# --------------------------------------------------------------- classify --


@dataclass
class Classified:
    """Every voxel of a bundle sorted into what happens to it, for one channel.

    Index arrays point into the bundle's voxel arrays. ``order`` lists the
    voxels above the floor, brightest energy first (ties by index), so a cap
    is a prefix of it.
    """

    channel: str
    n_events: int
    rho_ref: float | None
    ref: float | None
    value: np.ndarray
    ratio: np.ndarray
    full: np.ndarray
    populated: np.ndarray
    below: np.ndarray
    order: np.ndarray
    energy: dict[str, float] = field(default_factory=dict)
    cam: dict[str, float] | None = None

    @property
    def n_populated(self) -> int:
        return int(self.populated.sum())

    @property
    def n_below(self) -> int:
        return int(self.below.sum())

    @property
    def n_above(self) -> int:
        return int(self.order.size)


def classify(bundle: VoxelBundle, channel: str) -> Classified:
    """Value, reference, floor and energy ranking of every voxel for ``channel``."""
    if channel not in CHANNELS:  # pragma: no cover - the route validates first
        raise ValueError(f"unknown voxel channel {channel!r}")
    view = planes_mod.view(channel)
    n = max(1, bundle.n_events)
    fine = bundle.grid.pitch ** 2 * bundle.dz
    merged = fine * MERGE * MERGE
    e = bundle.sums["e"]
    full = ~(bundle.x.is_partial(bundle.vx) | bundle.y.is_partial(bundle.vy))
    populated = full & (e > 0)
    rho_ref = float(bundle.peaks["e"].max() / (n * fine)) if bundle.vx.size and bundle.n_events else None
    if rho_ref is not None and not rho_ref > 0:
        rho_ref = None

    numerator = None
    if view.cam is None:
        value = e / (n * merged)
        ref = rho_ref
    else:
        numerator = sum(bundle.sums[p] for p in view.numerator)
        value = numerator / (n * merged)
        peak = bundle.peaks["eg" if view.cam == "gradcam" else "s"]
        ref = float(peak.max() / (n * fine)) if peak.size and bundle.n_events else None
        if ref is not None and not ref > 0:
            ref = None
    if ref:
        ratio = value / ref
    else:
        ratio = np.zeros_like(value)
    magnitude = np.abs(ratio) if view.kind == planes_mod.KIND_SIGNED else ratio
    above = populated & (magnitude >= FLOOR_RATIO)
    below = populated & ~above
    candidates = np.flatnonzero(above)
    order = candidates[np.lexsort((candidates, -e[candidates]))]

    total = bundle.total_energy
    partial = ~full
    energy = {
        "total": total,
        "outside_grid": float(bundle.outside.get("e", 0.0)),
        "partial_edge": float(e[partial].sum()),
        "below_floor": float(e[below].sum()),
        "above_floor": float(e[above].sum()),
        "unpopulated": float(e[full & ~populated].sum()),
    }
    cam = None
    if numerator is not None:
        cam = {
            "total": float(numerator.sum()) + sum(float(bundle.outside.get(p, 0.0))
                                                  for p in view.numerator),
            "outside_grid": sum(float(bundle.outside.get(p, 0.0)) for p in view.numerator),
            "partial_edge": float(numerator[partial].sum()),
            "below_floor": float(numerator[below].sum()),
            "above_floor": float(numerator[above].sum()),
            "unpopulated": float(numerator[full & ~populated].sum()),
            "positive": float(sum(bundle.sums[p][full].sum() for p in view.numerator
                                  if p != "esn")),
            "negative": float(bundle.sums["esn"][full].sum()) if "esn" in view.numerator else 0.0,
        }
    return Classified(channel=channel, n_events=bundle.n_events, rho_ref=rho_ref, ref=ref,
                      value=value, ratio=ratio, full=full, populated=populated, below=below,
                      order=order, energy=energy, cam=cam)


# ------------------------------------------------------------------ render --


def _scale(classified: Classified, channel: str) -> scale_mod.ColorScale:
    """The channel's ramp over the populated full voxels, its floor count set to the one rule."""
    c = classified
    pop = c.populated
    if channel == planes_mod.CHANNEL_DENSITY:
        scale = scale_mod.relative_log_scale(
            c.ratio[pop], c.rho_ref or 0.0, frame_mod.RAMP_DECADES, density.NORM_SELECTION,
            rho_unit=RHO_UNIT, floor=scale_mod.FLOOR_TRANSPARENT)
    elif channel == planes_mod.CHANNEL_GRADCAM_ENERGY:
        scale = scale_mod.extensive_cam_scale(
            c.ratio[pop], np.ones(int(pop.sum()), dtype=bool), c.ref or 0.0, RHO_UNIT, channel,
            decades=frame_mod.RAMP_DECADES)
    else:
        scale = scale_mod.signed_log_scale(
            c.ratio[pop], np.ones(int(pop.sum()), dtype=bool), c.ref or 0.0, RHO_UNIT, channel,
            positive_total=c.cam["positive"] if c.cam else 0.0,
            negative_total=c.cam["negative"] if c.cam else 0.0,
            split_code=quantize.SPLIT_CODE, decades=frame_mod.RAMP_DECADES)
    scale.n_below = c.n_below
    scale.n_empty = 0
    return scale


def _codes(classified: Classified, scale: scale_mod.ColorScale, idx: np.ndarray) -> np.ndarray:
    ratio = classified.ratio[idx]
    if classified.channel == planes_mod.CHANNEL_SHAPCAM_ENERGY:
        codes = quantize.quantize_signed_log(ratio, np.ones(idx.size, dtype=bool),
                                             frame_mod.RAMP_DECADES)
    else:
        codes = quantize.quantize(ratio, scale, below_code=quantize.BELOW_CODE,
                                  populated_mask=np.ones(idx.size, dtype=bool))
    # Every shipped voxel is above the floor by the one stated rule; a ratio a
    # rounding ulp from 10^-3 must not come out as the undrawn code.
    return np.maximum(codes, MIN_DRAWN_CODE).astype(np.uint8)


def render(bundle: VoxelBundle, channel: str, cap: int,
           classified: Classified | None = None) -> dict[str, Any]:
    """The grid, voxels, scale, rho, budget and topk blocks for ``cap`` voxels."""
    c = classified if classified is not None else classify(bundle, channel)
    cap = max(0, int(cap))
    kept = c.order[:cap]
    beyond = c.order[cap:]
    ax, ay = bundle.x, bundle.y
    n_z = bundle.grid.n_z
    e = bundle.sums["e"]
    symbols = SYMBOLS[bundle.kind]

    # Ordinals relative to the first full voxel column of each axis.
    ox = bundle.vx[kept].astype(np.int64) - ax.first_full
    oy = bundle.vy[kept].astype(np.int64) - ay.first_full
    oz = bundle.vz[kept].astype(np.int64)
    packed, order = pack_layer_runs(ox, oy, oz, n_z, ax.n_full, ay.n_full)
    shipped = kept[order]
    scale = _scale(c, channel)
    codes = _codes(c, scale, shipped)
    voxels = {
        "n": int(shipped.size),
        "encoding": "layer-run-u8",
        "layer_counts": packed["layer_counts"],
        "xy": packed["xy"],
        "code": b64(codes),
        "order": (f"by depth {symbols['z']}, then {symbols['y']}, then {symbols['x']}; "
                  "layer_counts holds the number of voxels in each depth layer"),
        "dtype": packed["dtype"],
        "min_code": MIN_DRAWN_CODE,
        "layout": ("x = x_centre0 + voxel_mm[0] · xy[2i], y = y_centre0 + voxel_mm[1] · xy[2i + 1], "
                   "z = z_centres[layer]"),
    }

    # Exact values for the brightest shipped voxels by the channel's magnitude.
    signed = channel == planes_mod.CHANNEL_SHAPCAM_ENERGY
    rank = np.abs(c.value[shipped]) if signed else c.value[shipped]
    top = np.lexsort((np.arange(shipped.size), -rank))[:TOPK]
    z_centres = bundle.z_centres
    topk = [{
        "i": int(i),
        "x": sig(float(ax.centre(bundle.vx[shipped[i]]))),
        "y": sig(float(ay.centre(bundle.vy[shipped[i]]))),
        "z": sig(float(z_centres[bundle.vz[shipped[i]]])),
        "value": sig(float(c.value[shipped[i]])),
        "energy_gev": sig(float(e[shipped[i]])),
    } for i in top]

    total = c.energy["total"]
    gev = {
        "drawn": float(e[kept].sum()),
        "below_floor": c.energy["below_floor"],
        "beyond_cap": float(e[beyond].sum()),
        "outside_grid": c.energy["outside_grid"],
        "partial_edge": c.energy["partial_edge"],
    }

    def fraction(v: float) -> float:
        return round(v / total, 9) if total > 0 else 0.0

    n_partial = int((~c.full & (e > 0)).sum())
    budget = {
        "cap": cap,
        "rank": "energy",
        "n_populated": c.n_populated,
        "n_below_floor": c.n_below,
        "n_above_floor": c.n_above,
        "n_drawn": int(kept.size),
        "n_beyond_cap": int(beyond.size),
        "n_partial_edge": n_partial,
        "energy_total_gev": total,
        "energy_gev": gev,
        "energy_fraction": {key: fraction(v) for key, v in gev.items()},
        "cam": None,
    }
    if c.cam is not None:
        parts = planes_mod.view(channel).numerator
        budget["cam"] = {
            "quantity": channel,
            "unit": "GeV",
            "total": c.cam["total"],
            "drawn": float(sum(bundle.sums[q][kept].sum() for q in parts)),
            "below_floor": c.cam["below_floor"],
            "beyond_cap": float(sum(bundle.sums[q][beyond].sum() for q in parts)),
            "outside_grid": c.cam["outside_grid"],
            "partial_edge": c.cam["partial_edge"],
        }

    p = bundle.grid.pitch
    dz = bundle.dz
    x0 = float(ax.centre(ax.first_full))
    y0 = float(ay.centre(ay.first_full))
    z_uniform = bool(z_centres.size < 2 or np.allclose(np.diff(z_centres), dz, rtol=0, atol=1e-6))
    partial_axes = [symbols[a] for a, axis in (("x", ax), ("y", ay)) if axis.partial]
    if partial_axes:
        partial_note = (
            f"Along {' and '.join(partial_axes)} the accumulation grid holds an even number of "
            f"{p:g} mm bins on each side of the origin, so the outermost voxel on each side is half "
            f"a voxel wide. It lies at the far edge of the grid and is not drawn: {n_partial:,} "
            f"populated half-width voxel(s), {100.0 * fraction(gev['partial_edge']):.4g}% of the "
            "energy, counted.")
    else:
        partial_note = "Every voxel of the grid is full-width; nothing is excluded at its edge."
    grid = {
        "pitch_mm": p,
        "voxel_mm": [MERGE * p, MERGE * p, dz],
        "half_x": bundle.grid.half_x,
        "half_y": bundle.grid.half_y,
        "x_centre0": x0,
        "y_centre0": y0,
        "z_centre0": float(z_centres[0]) if z_centres.size else 0.0,
        "n": [ax.n_full, ay.n_full, n_z],
        "n_fine": [ax.n_fine, ay.n_fine, n_z],
        "z_centres": [round(float(z), 3) for z in z_centres],
        "z_uniform": z_uniform,
        "extent_mm": {
            "x": [x0 - p, x0 + MERGE * p * (ax.n_full - 1) + p],
            "y": [y0 - p, y0 + MERGE * p * (ay.n_full - 1) + p],
            "z": [float(z_centres[0] - dz / 2), float(z_centres[-1] + dz / 2)] if z_centres.size
            else [0.0, 0.0],
        },
        "alignment": (
            f"Fine {p:g} mm bins are merged in pairs about the origin on each transverse axis, "
            f"so the origin ({ORIGIN[bundle.kind]}) runs through the centre of one "
            f"{MERGE * p:g} mm voxel column instead of along a voxel edge; depth is never merged."),
        "partial_edge": {
            "x": ax.partial,
            "y": ay.partial,
            "n_voxels": n_partial,
            "energy_gev": gev["partial_edge"],
            "energy_fraction": fraction(gev["partial_edge"]),
            "note": partial_note,
        },
    }

    fine = (p, p, dz)
    is_density = channel == planes_mod.CHANNEL_DENSITY
    drawn_rho = c.value[kept] if is_density else e[kept] / (
        max(1, bundle.n_events) * MERGE * MERGE * p * p * dz)
    # The floor actually applied: the energy reference for density, the
    # channel's own peak (cam_ref) for an energy-weighted attention channel.
    floor_ref = c.rho_ref if is_density else c.ref
    rho = {
        "rho_ref": c.rho_ref,
        "unit": RHO_UNIT,
        "basis": f"raw {fine[0]:g} × {fine[1]:g} × {fine[2]:g} mm 3-D accumulation peak",
        "floor_ratio": FLOOR_RATIO,
        "norm": density.NORM_SELECTION,
        "floor": floor_ref * FLOOR_RATIO if floor_ref else None,
        "floor_basis": "rho_ref" if is_density else "cam_ref",
        "fine_voxel_mm": list(fine),
        "peak_drawn": float(drawn_rho.max()) if drawn_rho.size else None,
        "provisional": bundle.n_events < frame_mod.PROVISIONAL_N,
        "bound": ("Each voxel is the mean of its four raw bins, empty ones counting zero, so no "
                  "voxel exceeds ρ_ref."),
        "norm_note": ("ρ_ref is this selection's own raw 3-D peak; a dataset-wide reference is "
                      "not offered for the 3-D view in this version."),
    }
    scale_block = {**scale.as_dict(), "floor_rule": (
        "drawn iff ρ_v ≥ 10⁻³ ρ_ref" if is_density else
        "drawn iff |value| ≥ 10⁻³ cam_ref, the channel's own raw peak, among voxels holding "
        "energy")}
    if c.cam is not None:
        rho["cam_ref"] = c.ref
        rho["cam_basis"] = (f"raw {fine[0]:g} × {fine[1]:g} × {fine[2]:g} mm peak of "
                            + ("|Σ E × Shap-CAM|" if signed else "Σ E × Grad-CAM")
                            + " per event and mm³")
        rho["floor_note"] = (
            "The floor of this channel is 10⁻³ of cam_ref, not of the energy ρ_ref: a voxel is "
            "drawn by its own attention-weighted value.")
        # One ρ_ref per payload: the scale's reference is the channel's own
        # peak, carried as scale.ref (rho.cam_ref) and never under the energy name.
        # Present even on an empty selection (null), as the frontend reads it.
        scale_block.pop("rho_ref", None)
        scale_block.pop("rho_unit", None)
        scale_block["ref"] = c.ref
        scale_block["ref_unit"] = RHO_UNIT
        scale_block["ref_name"] = "cam_ref"

    return typeset({
        "grid": grid,
        "voxels": voxels,
        "scale": scale_block,
        "rho": rho,
        "budget": budget,
        "topk": topk,
    })
