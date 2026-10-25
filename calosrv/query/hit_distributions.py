"""C4, the hit quantities: per-momentum-bin distributions of u, v, w and hit energy.

The distribution card's other four quantities are properties of hits, so they
need one scan of the selection's hits, grouped by each hit's own shower's 1 GeV
momentum bin. The projection table carries no momentum bin; each hit takes its
shower's from the event table through a join, never from a float momentum
(the plan's "no ``pbin`` column" decision). Everything the series, the window
and the payload share comes from ``query/shower_distributions.py``.

**u, v, w are footprint-splatted hit counts.** Point-binning the cell centres
rotated into the Local frame leaves a comb against the lattice - measured on
the production file even over 20 000 showers (CLAUDE.md section 2, staggered
lattice). So each hit is spread over its cell's measured footprint as
``k x k x k_z`` sub-deposits, offset in the cell's own laboratory axes and
rotated by its shower's ``R(theta, phi)`` exactly as the Local panels do
(``frame_sql.subdeposit_offsets_cte``), each carrying ``1/(k^2 k_z)`` of a
hit. A count is therefore an exact multiple of that fraction, and a series
sums to its hits. u and v use 40 mm bins, where ``k = 2`` is gap-free
(24.3 mm spacing <= 40/sqrt 2); w uses bins of the layer pitch with ``k_z =
2``, so ``w = 0`` is an edge. The comb is measured on every response, on the
pooled raw profile over its full range before any crop, and disclosed with
``k`` and ``k_z``.

**Hit energy** spans some fifteen decades, so it is histogrammed in 0.01-decade
bins of ``log10(E / GeV)`` and the display bins are whole merges of those, so
every displayed count is still exact.

**Display window.** The rule of ``shower_distributions`` on hits: the pooled
1st–99th percentile from 20 hits up, rounded outward to whole bins, called
provisional while fewer than 20 showers set it.

**Cost.** The sub-deposit scan reads every selected hit eight times over -
about 193 M rows on the production file; 16 M sub-deposits of a synthetic
2 M-hit table take 0.2–0.5 s on four threads - so it runs through the physics
cache: one heavy scan at a time, single flight per selection, keyed with the
clamped filter first. Every display choice (quantity among u/v/w, clip
window, coarsening) is NumPy on the cached sums. A drag preview reads the 10%
sample above ``sampling.SAMPLE_THRESHOLD_ROWS`` and scales its counts, marked
inexact.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from ..config import Settings
from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..errors import CapabilityError
from ..grid import frame as frame_mod
from ..text import typographic
from . import canonical, capabilities, frame_sql, hit_sql, physics_cache, sampling
from . import shower_distributions as base
from . import showers as showers_mod
from .filters import FilterSpec
from .shower_distributions import Display, Prepared, Series, SeriesClass, ShowerSample
from .stagger import COMB_THRESHOLD, profile_lag1

#: Transverse bin width of u and v. At the gap-free sub-deposit count for a
#: 48.6 mm footprint (k = 2) a 20 mm bin would need k = 4, four times the scan.
UV_BIN_MM = 40.0

#: Fine energy bins per decade of log10(E / GeV).
ENERGY_FINE_PER_DECADE = 100

#: How many fine bins a display bin may merge: 1-2-5 steps, so every display
#: edge falls on a round fraction of a decade (0.05, 0.1, 0.25 ...) instead of
#: wherever the Rice rule's quotient happens to land.
ENERGY_MERGES: tuple[int, ...] = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)

#: The splat regime, as the payload names it.
SPLAT_REGIME = "subdeposit3d"

#: Bump when the scan's SQL or bundle layout changes, so stale cache entries die.
_UVW_VERSION = 1
_ENERGY_VERSION = 1

_AXIS_GROUP = {3: "u", 5: "v", 6: "w"}   # GROUPING_ID(ju, jv, jw) of each grouping set

_NO_HITS = ("This experiment holds event-level features only (the producer's aggregate): it "
            "has no hits to histogram.")


# ------------------------------------------------------------------ bundle --


@dataclass
class AxisCounts:
    """Dense counts per series row over one axis's populated bins, ``j0`` the first bin index."""

    j0: int
    counts: np.ndarray        # float64 [n_rows, n_bins]


@dataclass
class HitBundle:
    """The cached sums of one hit scan: counts per own momentum bin and axis."""

    bins: np.ndarray                  # int64, the momentum bin of each row
    axes: dict[str, AxisCounts]       # u, v, w (sub-deposits) or energy (hits, fine bins)
    unkeyed: dict[str, float]         # per axis: units it could not bin (no coordinate, E <= 0)
    elapsed_ms: float

    def row_of(self, momentum_bin: int) -> int | None:
        found = np.flatnonzero(self.bins == momentum_bin)
        return int(found[0]) if found.size else None


def _dense(bins: np.ndarray, mb: np.ndarray, j: np.ndarray, n: np.ndarray) -> AxisCounts:
    """A dense ``[row, bin]`` matrix from sparse ``(mb, j, n)`` rows."""
    if j.size == 0:
        return AxisCounts(0, np.zeros((bins.size, 0)))
    j0 = int(j.min())
    counts = np.zeros((bins.size, int(j.max()) - j0 + 1))
    np.add.at(counts, (np.searchsorted(bins, mb), j - j0), n)
    return AxisCounts(j0, counts)


def _rows(data: dict[str, Any], key: str) -> tuple[np.ndarray, np.ndarray]:
    raw = np.ma.asarray(data[key])
    return np.asarray(np.ma.filled(raw, 0), dtype=np.int64), np.ma.getmaskarray(raw)


# -------------------------------------------------------------------- splat --


def footprint_of(con: duckdb.DuckDBPyConnection, record: ExperimentRecord) -> tuple[float, float]:
    """The cell footprint ``(w_x, w_y)`` in mm: measured at ingest, else from the lattice."""
    measured = (record.capabilities or {}).get("footprint_mm")
    if measured:
        return float(measured[0]), float(measured[1])
    if record.lattice is not None:
        return canonical.cell_footprint(con, record)
    raise CapabilityError(
        f"u, v and w are not available for experiment {record.table_name!r}: no cell footprint "
        "or lattice was measured, so its hits cannot be splatted.",
        field="quantity", capability="distribution", kind=record.kind,
        reason="no measured cell footprint", table_name=record.table_name,
    )


def splat_parameters(footprint: tuple[float, float]) -> tuple[int, int]:
    """``(k, k_z)``: the smallest gap-free transverse count for 40 mm bins, never below 2; and 2."""
    k = max(frame_mod.MIN_SUBSAMPLE,
            frame_mod.minimum_gapless_subsample(max(footprint), UV_BIN_MM))
    return k, frame_mod.LOCAL_K_Z


def gap_free(spacing: float, bin_mm: float) -> bool:
    """A rotated sub-deposit lattice of this spacing leaves no empty bin of this width."""
    return spacing <= bin_mm / math.sqrt(2.0) + 1e-9


def uvw_sql(record: ExperimentRecord, spec: FilterSpec, choice: str, *, sampled: bool,
            k: int, k_z: int, footprint: tuple[float, float], pitch: float) -> str:
    """The sub-deposit scan: plain counts per (own momentum bin, u | v | w bin).

    Every shower of the kind gets a frame row, so the row index ``b`` matches
    the projection's origin (A 0, B 1); the shower choice acts on the hits.
    """
    every = showers_mod.of(record, "both")
    selected = showers_mod.of(record, choice)
    event = quote(naming.event_table(record.table_name))
    proj = hit_sql.proj_table(record, sampled=sampled)
    fr = frame_sql.shower_frame_cte(
        event, spec.where_sql(), frame_mod.KIND_LOCAL,
        showers=tuple(s.key for s in every), gate=capabilities.frame_gate(record),
        extra={"mb": tuple(f"CAST({s.momentum_bin} AS INTEGER)" for s in every)},
    )
    sub = frame_sql.subdeposit_offsets_cte(k, k_z, footprint[0], footprint[1], pitch)
    uv, wz = float(UV_BIN_MM), float(pitch)
    return f"""
    WITH {fr}, {sub}, hit AS (
        SELECT f.mb, CAST(p.xl AS DOUBLE) AS xl, CAST(p.yl AS DOUBLE) AS yl,
               CAST(p.zl AS DOUBLE) AS zl,
               f.r11, f.r12, f.r13, f.r21, f.r22, f.r31, f.r32, f.r33
        FROM {proj} p JOIN fr f ON {hit_sql.own_shower_join("p", "f")}
        WHERE {spec.where_sql("p")} AND {hit_sql.origin_filter(selected)}
    ), pts AS (
        SELECT mb,
               CAST(floor((xl + r11 * ox + r12 * oy + r13 * oz) / {uv!r}::DOUBLE) AS INTEGER) AS ju,
               CAST(floor((yl + r21 * ox + r22 * oy) / {uv!r}::DOUBLE) AS INTEGER) AS jv,
               CAST(floor((zl + r31 * ox + r32 * oy + r33 * oz) / {wz!r}::DOUBLE) AS INTEGER) AS jw
        FROM hit, sub
    )
    SELECT GROUPING_ID(ju, jv, jw) AS gid, mb, ju, jv, jw, count(*) AS n
    FROM pts
    GROUP BY GROUPING SETS ((mb, ju), (mb, jv), (mb, jw))"""


def energy_sql(record: ExperimentRecord, spec: FilterSpec, choice: str, *, sampled: bool) -> str:
    """Hit counts per (own momentum bin, 0.01-decade bin of log10 E); E <= 0 keyed NULL."""
    selected = showers_mod.of(record, choice)
    sh = hit_sql.shower_attr_cte(record, spec, selected, attrs=(("mb", "momentum_bin"),))
    proj = hit_sql.proj_table(record, sampled=sampled)
    return f"""
    WITH {sh}
    SELECT s.mb AS mb,
           CASE WHEN p.energy > 0
                THEN CAST(floor(log10(p.energy) * {ENERGY_FINE_PER_DECADE}) AS INTEGER) END AS je,
           count(*) AS n
    FROM {proj} p JOIN sh s ON {hit_sql.own_shower_join("p", "s")}
    WHERE {spec.where_sql("p")} AND {hit_sql.origin_filter(selected)}
    GROUP BY ALL"""


def scan_uvw(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
             choice: str, *, sampled: bool, k: int, k_z: int, footprint: tuple[float, float],
             pitch: float) -> HitBundle:
    started = time.perf_counter()
    sql = uvw_sql(record, spec, choice, sampled=sampled, k=k, k_z=k_z, footprint=footprint,
                  pitch=pitch)
    data = con.execute(sql, spec.params()).fetchnumpy()
    gid = np.asarray(data["gid"], dtype=np.int64)
    mb, mb_null = _rows(data, "mb")
    n = np.asarray(data["n"], dtype=np.float64)
    bins = np.unique(mb[~mb_null])
    axes: dict[str, AxisCounts] = {}
    unkeyed: dict[str, float] = {}
    for code, axis in _AXIS_GROUP.items():
        j, j_null = _rows(data, f"j{axis}")
        mine = (gid == code) & ~mb_null
        axes[axis] = _dense(bins, mb[mine & ~j_null], j[mine & ~j_null], n[mine & ~j_null])
        unkeyed[axis] = float(n[mine & j_null].sum())
    return HitBundle(bins, axes, unkeyed, (time.perf_counter() - started) * 1000.0)


def scan_energy(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                choice: str, *, sampled: bool) -> HitBundle:
    started = time.perf_counter()
    data = con.execute(energy_sql(record, spec, choice, sampled=sampled),
                       spec.params()).fetchnumpy()
    mb, mb_null = _rows(data, "mb")
    je, je_null = _rows(data, "je")
    n = np.asarray(data["n"], dtype=np.float64)
    bins = np.unique(mb[~mb_null])
    ok = ~mb_null & ~je_null
    return HitBundle(bins, {"energy": _dense(bins, mb[ok], je[ok], n[ok])},
                     {"energy": float(n[~mb_null & je_null].sum())},
                     (time.perf_counter() - started) * 1000.0)


def uvw_key(record: ExperimentRecord, spec: FilterSpec, choice: str, sampled: bool, k: int,
            k_z: int, footprint: tuple[float, float], pitch: float) -> tuple:
    return (*spec.clamped(record).cache_key(), sampled, "c4_uvw", _UVW_VERSION, choice, k, k_z,
            UV_BIN_MM, float(pitch), round(footprint[0], 3), round(footprint[1], 3))


def energy_key(record: ExperimentRecord, spec: FilterSpec, choice: str, sampled: bool) -> tuple:
    return (*spec.clamped(record).cache_key(), sampled, "c4_energy", _ENERGY_VERSION, choice)


# ------------------------------------------------------------------ render --


def _coarsened(axis: AxisCounts, factor: int) -> AxisCounts:
    """Whole merges of ``factor`` native bins, aligned on bin index 0 (so on w = 0)."""
    if factor <= 1 or axis.counts.shape[1] == 0:
        return axis
    j = axis.j0 + np.arange(axis.counts.shape[1])
    coarse = np.floor_divide(j, factor)
    starts = np.flatnonzero(np.r_[True, np.diff(coarse) != 0])
    return AxisCounts(int(coarse[0]), np.add.reduceat(axis.counts, starts, axis=1))


def _series_rows(bundle: HitBundle, axis: AxisCounts, classes: list[SeriesClass]) -> np.ndarray:
    """The counts matrix in series order; a series the scan did not reach is zeros."""
    out = np.zeros((len(classes), axis.counts.shape[1]))
    for i, c in enumerate(classes):
        row = bundle.row_of(c.bin)
        if row is not None:
            out[i] = axis.counts[row]
    return out


@dataclass
class Window:
    """Inclusive bin indices of the display window into a counts matrix, and how it was set."""

    i_lo: int
    i_hi: int
    applied: bool


def _window(pooled: np.ndarray, n_units: float, low: float, high: float) -> Window | None:
    """The percentile window of a pooled profile, or its populated range below ROBUST_N units."""
    populated = np.flatnonzero(pooled > 0)
    if populated.size == 0:
        return None
    if n_units < base.ROBUST_N:
        return Window(int(populated[0]), int(populated[-1]), False)
    i_lo, i_hi = base.percentile_bins(pooled, low, high)
    return Window(i_lo, i_hi, True)


def _split(matrix: np.ndarray, i_lo: int, i_hi: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(inside, below, above)`` per row of a counts matrix for the window ``[i_lo, i_hi]``."""
    return (matrix[:, i_lo:i_hi + 1], matrix[:, :i_lo].sum(axis=1),
            matrix[:, i_hi + 1:].sum(axis=1))


def _empty_body(q: base.Quantity, weighting: str, width: float, unit: str,
                classes: list[SeriesClass], splat: dict | None, comb: dict | None,
                exact: bool) -> dict[str, Any]:
    series = [Series(c, np.zeros(0), 0.0, 0.0) for c in classes]
    display = Display(0.0, 0.0, False, True, 0.0, 0.0, 0.0, 0.0,
                      "Nothing in this selection to draw.")
    return {"quantity": q.block(weighting, width, unit), "edges": [],
            "series": base.series_payload(series, exact), "display": display.as_dict(exact),
            "splat": splat, "comb": comb}


def comb_block(native_pooled: np.ndarray, axis: str, width: float, k: int, k_z: int
               ) -> dict[str, Any]:
    """The comb statistic of the pooled raw profile over its full range, before any crop."""
    lag1 = profile_lag1(np.asarray(native_pooled, dtype=np.float64))
    return {
        "lag1": sig(lag1, 3),
        "combed": None if lag1 is None else bool(lag1 < COMB_THRESHOLD),
        "threshold": COMB_THRESHOLD,
        "axis": axis,
        "k": k,
        "k_z": k_z,
        "measured_on": (f"pooled raw footprint-splatted count profile of {axis} (every series, "
                        f"{width:g} mm bins, full range), before any crop"),
    }


def comb_note(comb: dict[str, Any]) -> str:
    lag1 = comb["lag1"]
    splat = f"k = {comb['k']}, k_z = {comb['k_z']}"
    if lag1 is None:
        return (f"Comb not measurable on {comb['axis']}: the pooled raw profile spans too few "
                f"bins to detrend ({splat}).")
    verdict = ("a comb: adjacent bins alternate, which is lattice segmentation, not shower "
               "structure" if comb["combed"] else "no comb")
    return typographic(
        f"Comb measured on the pooled raw {comb['axis']} profile before any crop: lag-1 "
        f"autocorrelation {lag1:+.2f} against the {COMB_THRESHOLD:+.2f} threshold, {verdict} "
        f"({splat}).")


def render_uvw(bundle: HitBundle, classes: list[SeriesClass], axis: str, *, per_hit: int,
               scale: float, k: int, k_z: int, footprint: tuple[float, float], pitch: float,
               low: float, high: float, coarsen: int, exact: bool) -> dict[str, Any]:
    """One of u, v, w: footprint-splatted hit counts per series in the display window."""
    q = base.QUANTITIES[axis]
    native = bundle.axes[axis]
    native_width = UV_BIN_MM if axis in ("u", "v") else float(pitch)
    width = native_width * coarsen
    spacing = max(footprint) / k if axis in ("u", "v") else float(pitch) / k_z
    splat = {"regime": SPLAT_REGIME, "k": k, "k_z": k_z, "bin_mm": sig(width),
             "gap_free": gap_free(spacing, width), "per_hit": per_hit,
             "footprint_mm": [sig(footprint[0]), sig(footprint[1]), sig(pitch)]}
    comb = comb_block(native.counts.sum(axis=0), axis, native_width, k, k_z)
    weighting = "footprint-splatted hit count"

    coarse = _coarsened(native, coarsen)
    hits = _series_rows(bundle, coarse, classes) * (scale / per_hit)
    pooled = hits.sum(axis=0)
    n_showers = sum(c.n_showers for c in classes)
    window = _window(pooled, float(pooled.sum()) / scale, low, high)
    if window is None:
        return _empty_body(q, weighting, width, "mm", classes, splat, comb, exact)
    inside, below, above = _split(hits, window.i_lo, window.i_hi)
    series = [Series(c, inside[i], float(below[i]), float(above[i]))
              for i, c in enumerate(classes)]
    edges = (coarse.j0 + np.arange(window.i_lo, window.i_hi + 2)) * width
    total = float(hits.sum())
    n_outside = float(below.sum() + above.sum())
    note = base.window_note(
        float(edges[0]), float(edges[-1]), "mm", applied=window.applied, low=low, high=high,
        n_outside=n_outside, total=total, what="hits",
        rounding=f"whole {width:g} mm bins", n_showers=n_showers)
    display = Display(float(edges[0]), float(edges[-1]), window.applied,
                      n_showers < base.ROBUST_N, low, high, n_outside, total, note, coarsen)
    return {
        "quantity": q.block(weighting, width, "mm"),
        "edges": [sig(e) for e in edges],
        "series": base.series_payload(series, exact),
        "display": display.as_dict(exact),
        "splat": splat,
        "comb": comb,
    }


def energy_bins(fine_window: int, series_hits: list[float], coarsen: int) -> tuple[int, int]:
    """``(m, N)``: fine bins per display bin and the series hits that set it.

    The Rice rule on the smallest series (``shower_distributions.rice_bins``)
    caps the display bin count; ``m`` is the smallest merge on
    :data:`ENERGY_MERGES` that stays within it, times the guard's coarsening.
    """
    bins, n_ref = base.rice_bins([int(round(h)) for h in series_hits])
    need = max(1, math.ceil(fine_window / bins))
    m = next((step for step in ENERGY_MERGES if step >= need), need)
    return m * max(1, coarsen), n_ref


def render_energy(bundle: HitBundle, classes: list[SeriesClass], *, scale: float, low: float,
                  high: float, coarsen: int, exact: bool) -> tuple[dict[str, Any], str]:
    """Hit energy per series on equal-log display bins, each a whole merge of 0.01-decade bins."""
    q = base.QUANTITIES["energy"]
    fine = bundle.axes["energy"]
    hits = _series_rows(bundle, fine, classes) * scale
    pooled = hits.sum(axis=0)
    n_showers = sum(c.n_showers for c in classes)
    window = _window(pooled, float(pooled.sum()) / scale, low, high)
    if window is None:
        return _empty_body(q, "hit count", 0.0, "decade", classes, None, None, exact), ""
    # The Rice rule counts hits read, not a preview's scaled estimate of them.
    m, n_ref = energy_bins(window.i_hi - window.i_lo + 1, list(hits.sum(axis=1) / scale),
                           coarsen)
    start = math.floor((fine.j0 + window.i_lo) / m) * m
    stop = math.ceil((fine.j0 + window.i_hi + 1) / m) * m
    n_display = (stop - start) // m
    j = fine.j0 + np.arange(hits.shape[1])
    slot = np.floor_divide(j - start, m)
    inside = (slot >= 0) & (slot < n_display)
    counts = np.zeros((hits.shape[0], n_display))
    np.add.at(counts, (slice(None), slot[inside]), hits[:, inside])
    below = hits[:, j < start].sum(axis=1)
    above = hits[:, j >= stop].sum(axis=1)
    series = [Series(c, counts[i], float(below[i]), float(above[i]))
              for i, c in enumerate(classes)]
    log_edges = np.arange(start, stop + 1, m) / ENERGY_FINE_PER_DECADE
    edges = np.power(10.0, log_edges)
    total = float(hits.sum())
    n_outside = float(below.sum() + above.sum())
    decades = m / ENERGY_FINE_PER_DECADE
    note = base.window_note(
        float(edges[0]), float(edges[-1]), "GeV", applied=window.applied, low=low, high=high,
        n_outside=n_outside, total=total, what="hits",
        rounding=f"whole {decades:g}-decade display bins", n_showers=n_showers)
    display = Display(float(edges[0]), float(edges[-1]), window.applied,
                      n_showers < base.ROBUST_N, low, high, n_outside, total, note, coarsen)
    body = {
        "quantity": q.block("hit count", decades, "decade"),
        "edges": [sig(e) for e in edges],
        "edges_log10": [round(float(e), 6) for e in log_edges],
        "series": base.series_payload(series, exact),
        "display": display.as_dict(exact),
        "splat": None,
        "comb": None,
    }
    binning = (f"Hit energies are binned in 0.01-decade bins of log10(E / GeV) and merged "
               f"{m} at a time into {decades:g}-decade display bins (Rice rule on the smallest "
               f"series of at least {base.RICE_FLOOR_N} hits, N = {n_ref:,}), so every count "
               "is exact.")
    return body, binning


# ------------------------------------------------------------------- notes --


def splat_note(k: int, k_z: int, footprint: tuple[float, float], pitch: float) -> str:
    n = k * k * k_z
    return (f"Footprint-splatted hit counts: each hit is spread over its cell's "
            f"{footprint[0]:.2f} × {footprint[1]:.2f} × {pitch:g} mm footprint as {k} × {k} × "
            f"{k_z} sub-deposits, rotated into its own shower's Local frame by R(θ, φ) as the "
            f"Local panels do; each carries 1/{n} of a hit, so a count is a multiple of 1/{n} "
            "and every series sums to its hits.")


def bins_note(k: int, footprint: tuple[float, float], pitch: float) -> str:
    spacing = max(footprint) / k
    return (f"u and v use {UV_BIN_MM:g} mm bins, gap-free at k = {k} (sub-deposit spacing "
            f"{spacing:.1f} mm ≤ {UV_BIN_MM:g}/√2 mm); w uses bins of the {pitch:g} mm layer "
            "pitch, with w = 0 an edge. Each hit is counted in its own shower's momentum bin.")


def unplaced_note(record: ExperimentRecord, sample: ShowerSample) -> str | None:
    lost = ~sample.placed
    if not lost.any():
        return None
    why = ("the event's A–B separation is undefined, so the per-shower frames do not place it"
           if record.kind == ddl.KIND_TWO_SHOWER
           else "its incident direction or entry point is missing")
    hits = float(sample.hits[lost].sum())
    return (f"{base.fmt_count(hits)} hit(s) of {int(lost.sum()):,} shower(s) are not drawn: "
            f"{why}.")


def unkeyed_note(bundle: HitBundle, axis: str, scale: float, sentence: str) -> str | None:
    """``sentence`` with ``{n}`` the units the scan could not bin on ``axis``, or nothing."""
    lost = bundle.unkeyed.get(axis, 0.0) * scale
    if lost <= 0:
        return None
    return sentence.format(n=base.fmt_count(lost))


# ----------------------------------------------------------------- prepare --


def require_hits(record: ExperimentRecord, quantity: str) -> None:
    """Refuse a hit quantity on an experiment without hits, naming the parameter."""
    traits = record.traits
    if traits is not None and traits.has_hits:
        return
    raise CapabilityError(
        f"quantity={quantity!r} is not available for experiment {record.table_name!r}: "
        f"{_NO_HITS} θ, φ and p are.",
        field="quantity", capability="hits", kind=record.kind, reason=_NO_HITS,
        table_name=record.table_name,
    )


def prepare(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            settings: Settings, *, quantity: str, shower: str, low: float, high: float,
            preview: bool) -> Prepared:
    """u, v, w or hit energy of the selection's hits, scanned (or cached) and ready to render."""
    require_hits(record, quantity)
    selected = showers_mod.of(record, shower)
    decision = sampling.decide(record, preview, settings.sample_percent)
    scale = 100.0 / decision.percent if decision.sampled else 1.0
    exact = not decision.sampled
    warnings = [decision.reason] if decision.sampled else []

    if quantity == "energy":
        sample = base.fetch(con, record, spec, selected)
        classes, notices = base.series_classes(sample, field=base._MOMENTUM_FIELD.get(shower, "e1"))
        bundle, cached = physics_cache.get_or_compute(
            energy_key(record, spec, shower, decision.sampled),
            lambda: scan_energy(con, record, spec, shower, sampled=decision.sampled))
        lost = unkeyed_note(bundle, "energy", scale,
                            "{n} hit(s) with E ≤ 0 have no logarithm and are not drawn.")
        fixed = [*base.kind_notes(record), *notices, *base.series_notes(classes, sample)]

        def draw(coarsen: int) -> dict[str, Any]:
            body, binning = render_energy(bundle, classes, scale=scale, low=low, high=high,
                                          coarsen=coarsen, exact=exact)
            notes = [*fixed, binning] + ([lost] if lost else [])
            body["notes"] = [typographic(n) for n in notes if n]
            return body
    else:
        sample = base.fetch(con, record, spec, selected, gate=capabilities.frame_gate(record))
        classes, notices = base.series_classes(sample, mask=sample.placed,
                                                 field=base._MOMENTUM_FIELD.get(shower, "e1"))
        footprint = footprint_of(con, record)
        pitch = hit_sql.layer_pitch(record)
        k, k_z = splat_parameters(footprint)
        bundle, cached = physics_cache.get_or_compute(
            uvw_key(record, spec, shower, decision.sampled, k, k_z, footprint, pitch),
            lambda: scan_uvw(con, record, spec, shower, sampled=decision.sampled, k=k,
                             k_z=k_z, footprint=footprint, pitch=pitch))
        per_hit = k * k * k_z
        fixed = [*base.kind_notes(record), *notices, *base.series_notes(classes, sample),
                 splat_note(k, k_z, footprint, pitch), bins_note(k, footprint, pitch),
                 unplaced_note(record, sample),
                 unkeyed_note(bundle, quantity, scale / per_hit,
                              "{n} hit(s) without Local coordinates are not drawn.")]

        def draw(coarsen: int) -> dict[str, Any]:
            body = render_uvw(bundle, classes, quantity, per_hit=per_hit, scale=scale, k=k,
                              k_z=k_z, footprint=footprint, pitch=pitch, low=low, high=high,
                              coarsen=coarsen, exact=exact)
            notes = [*fixed, comb_note(body["comb"])]
            body["notes"] = [typographic(n) for n in notes if n]
            return body

    return Prepared(draw, exact=exact, cached=cached,
                    query_ms=sample.elapsed_ms + (0.0 if cached else bundle.elapsed_ms),
                    warnings=warnings)
