"""Co-register every selected event into the canonical frame, inside DuckDB.

The rotation is per event, so it cannot be applied to the lab-frame
``NativeBundle`` after the fact: a hit's canonical position depends on which
event it belongs to. Instead each hit row of the projection table joins its
event's frame parameters - a 20 000-row CTE built from the per-event table -
and the rotated position is binned into a uniform canonical grid with the same
``GROUP BY GROUPING SETS`` single-scan pattern as ``projections.py``. Measured
on the 22.5-million-row production table this costs 0.54 s at k = 1 against
0.35 s for the lab-frame scan.

**Sub-cell splatting.** A hit is a 48 x 49 mm cell, not a point; dropping its
rotated centre into a 20 mm bin would draw a dotted comb around every event.
Each cell's energy is therefore split into ``k x k`` equal sub-deposits over its
physical footprint (``CROSS JOIN range(k) x range(k)``), which conserves the
total exactly for any ``k`` and leaves no hole under a rotated footprint once
``k >= 4``. ``k`` is chosen from a row budget so the scan stays interactive -
2 for the whole dataset (about 2 s, cached and pre-warmed), 4 for a
thousand-event slice, 6 for a handful - and never drops to 1: point-binning
was measured to comb even over 20 000 co-registered events.

**Coordinates.** Bin indices become millimetres only through the coordinate
arrays measured at ingest, bound here as list parameters and read with
``list_extract`` - never by multiplying a pitch (CLAUDE.md section 2).

**What is excluded.** An event with no shower-A centroid (``cax IS NULL``,
which coincides with ``d IS NULL``) has no frame and is excluded from ``N``
even when ``include_undefined_d`` would admit it elsewhere; the count is
reported. Energy falling outside the accumulation window is summed and
reported rather than dropped silently.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..grid import frame as frame_mod
from ..grid.frame import CanonicalGrid
from ..grid.lattice import Axis, Lattice
from .filters import FilterSpec
from .projections import GID_XY, GID_XZ, GID_YZ, PLANES, Panel

log = logging.getLogger(__name__)

#: Every per-event column a frame needs. ``d`` is included so the frame-bearing
#: set is a subset of the filtered set even when ``include_undefined_d`` is on.
_FRAME_COLUMNS = (
    "cax", "cay", "caz", "cbx", "cby", "cbz",
    "theta_a", "phi_a", "theta_b", "phi_b", "d",
)
_FRAME_DEFINED = " AND ".join(f"{c} IS NOT NULL" for c in _FRAME_COLUMNS)

#: Back-projected entry points, as SQL over the per-event table.
_ENTRY_SQL = """
    cax - (caz - $zf) * tan(theta_a) * cos(phi_a) AS xa,
    cay - (caz - $zf) * tan(theta_a) * sin(phi_a) AS ya,
    cbx - (cbz - $zf) * tan(theta_b) * cos(phi_b) AS xb,
    cby - (cbz - $zf) * tan(theta_b) * sin(phi_b) AS yb"""


# ------------------------------------------------------------ statistics --


@dataclass
class ShowerDirection:
    """Ensemble direction of one shower in the canonical frame."""

    n: int
    slope_mean: tuple[float | None, float | None]
    slope_sd: tuple[float | None, float | None]
    direction_mean: tuple[float | None, float | None, float | None]
    resultant_transverse: float | None
    rayleigh_p: float | None
    centroid_mean: tuple[float | None, float | None, float | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "slope": list(self.slope_mean),
            "slope_sd": list(self.slope_sd),
            "direction": list(self.direction_mean),
            "resultant_transverse": self.resultant_transverse,
            "rayleigh_p": self.rayleigh_p,
            "centroid_canonical_mean": {
                "x": self.centroid_mean[0],
                "y": self.centroid_mean[1],
                "z": self.centroid_mean[2],
            },
        }


@dataclass
class Moments:
    mean: float | None
    median: float | None
    sd: float | None
    lo: float | None
    hi: float | None
    n: int = 0

    @property
    def se(self) -> float | None:
        if self.sd is None or self.n < 2:
            return None
        return self.sd / math.sqrt(self.n)

    @property
    def ci95_half(self) -> float | None:
        """Half-width of the Student-t 95% interval of the mean.

        This, not the bare standard error, is what the interface quotes beside
        a mean: at N = 2 the two differ by a factor 12.7, and CLAUDE.md
        section 2 is explicit that the normal form understates small-N
        intervals. The SE is still reported for completeness.
        """
        se = self.se
        if se is None:
            return None
        return frame_mod.t_quantile_975(self.n - 1) * se

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean, "median": self.median, "sd": self.sd,
            "se": self.se, "ci95_half": self.ci95_half,
            "min": self.lo, "max": self.hi, "n": self.n,
        }


@dataclass
class FrameStats:
    """Everything the canonical frame knows about a selection before scanning hits."""

    n_selected: int
    n_events: int
    n_hits: int
    n_ill_conditioned: int
    d_entry: Moments
    d_dataset: Moments
    d_entry_max: float | None
    theta_max: float | None
    psi_resultant: float | None
    a: ShowerDirection
    b: ShowerDirection
    z_front: float

    @property
    def n_excluded_no_frame(self) -> int:
        return max(0, self.n_selected - self.n_events)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "n_selected": self.n_selected,
            "n_excluded_no_frame": self.n_excluded_no_frame,
            "n_hits": self.n_hits,
            "n_ill_conditioned": self.n_ill_conditioned,
            "ill_conditioned_threshold_mm": frame_mod.ILL_CONDITIONED_D_MM,
            "d_entry": self.d_entry.as_dict(),
            "d_dataset": self.d_dataset.as_dict(),
            "psi_resultant": self.psi_resultant,
            "z_front_mm": self.z_front,
            "axes": {"a": self.a.as_dict(), "b": self.b.as_dict()},
        }


def _shower_sql(tag: str) -> str:
    """Aggregates for one shower's rotated direction, slopes and centroid."""
    ux, uy, uz = f"u{tag}x_c", f"u{tag}y_c", f"u{tag}z"
    cx, cy, cz = f"c{tag}x_c", f"c{tag}y_c", f"c{tag}z_c"
    norm = f"sqrt({ux} * {ux} + {uy} * {uy})"
    return f"""
        avg({ux} / {uz}), avg({uy} / {uz}),
        stddev_samp({ux} / {uz}), stddev_samp({uy} / {uz}),
        avg({ux}), avg({uy}), avg({uz}),
        avg(CASE WHEN {norm} > 0 THEN {ux} / {norm} END),
        avg(CASE WHEN {norm} > 0 THEN {uy} / {norm} END),
        avg({cx}), avg({cy}), avg({cz})"""


def frame_statistics(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
) -> FrameStats:
    """Per-event frame statistics for the selection. Reads only the event table."""
    assert record.lattice is not None
    z_front = float(record.lattice.z.lo)
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    sql = f"""
    WITH ev AS (
        SELECT event_number, d, n_hits, theta_a, theta_b, phi_a, phi_b,
               cax, cay, caz, cbx, cby, cbz,
               {_ENTRY_SQL}
        FROM {table}
        WHERE {where} AND {_FRAME_DEFINED}
    ), fr AS (
        SELECT *,
               atan2(yb - ya, xb - xa)                 AS psi,
               sqrt((xb - xa) * (xb - xa) + (yb - ya) * (yb - ya)) AS d_entry,
               (xa + xb) / 2                           AS x0,
               (ya + yb) / 2                           AS y0
        FROM ev
    ), rot AS (
        SELECT *, cos(psi) AS c, sin(psi) AS s,
               sin(theta_a) * cos(phi_a) AS uax, sin(theta_a) * sin(phi_a) AS uay, cos(theta_a) AS uaz,
               sin(theta_b) * cos(phi_b) AS ubx, sin(theta_b) * sin(phi_b) AS uby, cos(theta_b) AS ubz
        FROM fr
    ), can AS (
        SELECT d, d_entry, psi, n_hits, theta_a, theta_b, uaz, ubz,
               c * uax + s * uay AS uax_c, -s * uax + c * uay AS uay_c,
               c * ubx + s * uby AS ubx_c, -s * ubx + c * uby AS uby_c,
               c * (cax - x0) + s * (cay - y0) AS cax_c, -s * (cax - x0) + c * (cay - y0) AS cay_c,
               caz - $zf AS caz_c,
               c * (cbx - x0) + s * (cby - y0) AS cbx_c, -s * (cbx - x0) + c * (cby - y0) AS cby_c,
               cbz - $zf AS cbz_c
        FROM rot
    )
    SELECT
        (SELECT count(*) FROM {table} WHERE {where})    AS n_selected,
        count(*)                                        AS n_events,
        coalesce(sum(n_hits), 0)                        AS n_hits,
        avg(d_entry), median(d_entry), stddev_samp(d_entry), min(d_entry), max(d_entry),
        avg(d), median(d), stddev_samp(d), min(d), max(d),
        max(greatest(theta_a, theta_b))                 AS theta_max,
        count(*) FILTER (WHERE d_entry < $ill)          AS n_ill,
        avg(cos(psi)), avg(sin(psi)),
        {_shower_sql("a")},
        {_shower_sql("b")}
    FROM can
    """
    params = {**spec.params(), "zf": z_front, "ill": frame_mod.ILL_CONDITIONED_D_MM}
    row = con.execute(sql, params).fetchone()

    def f(i: int) -> float | None:
        v = row[i]
        return float(v) if v is not None and math.isfinite(float(v)) else None

    n_selected = int(row[0] or 0)
    n_events = int(row[1] or 0)
    n_hits = int(row[2] or 0)
    d_entry = Moments(f(3), f(4), f(5), f(6), f(7), n_events)
    d_dataset = Moments(f(8), f(9), f(10), f(11), f(12), n_events)
    theta_max = f(13)
    n_ill = int(row[14] or 0)
    psi_resultant = None
    if row[15] is not None and row[16] is not None:
        psi_resultant = float(math.hypot(float(row[15]), float(row[16])))

    def shower(offset: int) -> ShowerDirection:
        # A resultant length, a dispersion and a Rayleigh test are statements
        # about an *ensemble*; one direction has none of them (its resultant is
        # trivially 1.0), so they are undefined below two events - in this
        # block as in `ensemble.py`, so no consumer can read a 1.000 from one.
        ensemble = n_events >= 2
        rx, ry = f(offset + 7), f(offset + 8)
        resultant = (
            math.hypot(rx, ry) if ensemble and rx is not None and ry is not None else None
        )
        return ShowerDirection(
            n=n_events,
            slope_mean=(f(offset), f(offset + 1)),
            slope_sd=(f(offset + 2), f(offset + 3)) if ensemble else (None, None),
            direction_mean=(f(offset + 4), f(offset + 5), f(offset + 6)),
            resultant_transverse=resultant,
            rayleigh_p=frame_mod.rayleigh_p(n_events, resultant) if resultant is not None else None,
            centroid_mean=(f(offset + 9), f(offset + 10), f(offset + 11)),
        )

    return FrameStats(
        n_selected=n_selected,
        n_events=n_events,
        n_hits=n_hits,
        n_ill_conditioned=n_ill,
        d_entry=d_entry,
        d_dataset=d_dataset,
        d_entry_max=d_entry.hi,
        theta_max=theta_max,
        psi_resultant=psi_resultant,
        a=shower(17),
        b=shower(17 + 12),
        z_front=z_front,
    )


# ------------------------------------------------------------- footprint --

_footprints: dict[tuple[str, int], tuple[float, float]] = {}
_footprint_lock = threading.Lock()


def cell_footprint(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord
) -> tuple[float, float]:
    """Physical ``(w_x, w_y)`` cell footprint of an experiment, measured once.

    Read from the populated ``(ix, iy)`` cells of the projection table - the
    pitch between adjacent cells sharing a row or a column - and memoised per
    table and row count, so an append re-measures. Falls back to the
    lattice-only estimate when the table holds too few cells to say.
    """
    assert record.lattice is not None
    key = (record.table_name, int(record.n_hits))
    with _footprint_lock:
        cached = _footprints.get(key)
    if cached is not None:
        return cached

    proj = quote(naming.proj_table(record.table_name))
    started = time.perf_counter()
    cells = con.execute(f"SELECT DISTINCT ix, iy FROM {proj}").fetchnumpy()
    ix = np.asarray(np.ma.filled(np.ma.asarray(cells["ix"]), 0), dtype=np.int64)
    iy = np.asarray(np.ma.filled(np.ma.asarray(cells["iy"]), 0), dtype=np.int64)
    w_x, w_y = frame_mod.footprint_from_occupancy(
        ix, iy, record.lattice.x.coords, record.lattice.y.coords
    )
    fallback_x, fallback_y = frame_mod.footprint_from_lattice(record.lattice)
    result = (
        float(w_x) if w_x is not None and w_x > 0 else float(fallback_x),
        float(w_y) if w_y is not None and w_y > 0 else float(fallback_y),
    )
    log.info(
        "Cell footprint for %s: %.2f x %.2f mm from %d cells in %.0f ms",
        record.table_name, result[0], result[1], ix.size,
        (time.perf_counter() - started) * 1000.0,
    )
    with _footprint_lock:
        _footprints[key] = result
    return result


def reset_footprints() -> None:
    with _footprint_lock:
        _footprints.clear()


# ---------------------------------------------------------------- bundle --


@dataclass
class CanonicalBundle:
    """Native-resolution canonical aggregates for one selection.

    The same three ``Panel`` objects as a lab-frame ``NativeBundle`` - so
    ``centroids.compute`` and ``panels.shower_axes`` measure it unchanged - but
    the axes are the uniform canonical grid, answered by :meth:`axis`.
    """

    xy: Panel
    yz: Panel
    xz: Panel
    grid: CanonicalGrid
    stats: FrameStats
    lattice: Lattice
    subsample_k: int
    footprint: tuple[float, float]
    energy_outside: float
    n_outside: int
    exact: bool
    query_ms: float
    n_hits: int
    sample_percent: float = 100.0

    def panel(self, name: str) -> Panel:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def axis(self, name: str) -> Axis:
        return self.grid.axis(name)

    @property
    def n_events(self) -> int:
        return self.stats.n_events

    @property
    def total_energy(self) -> float:
        """Energy inside the accumulation window (the XZ set spans it fully)."""
        return float(self.xz.planes["e"].sum())

    @property
    def energy_fraction_outside(self) -> float:
        total = self.total_energy + self.energy_outside
        return self.energy_outside / total if total > 0 else 0.0

    @property
    def nbytes(self) -> int:
        return sum(
            plane.nbytes
            for panel in (self.xy, self.yz, self.xz)
            for plane in panel.planes.values()
        )


#: Per-cell measures, as (column stem, SQL expression); ``None`` means count(*).
_MEASURES: tuple[tuple[str, str | None], ...] = (
    ("e", "energy"),
    ("eg", "energy * CAST(ge AS DOUBLE)"),
    ("g", "CAST(ge AS DOUBLE)"),
    ("n", None),
    ("efat", "energy * CAST(fa_true AS DOUBLE)"),
    ("efap", "energy * CAST(fa_pred AS DOUBLE)"),
)

_PLANE_SOURCE = {
    "e": "e", "eg": "eg", "g": "g", "n": "n", "efa_true": "efat", "efa_pred": "efap",
}


def _aggregates() -> str:
    parts = []
    for stem, expr in _MEASURES:
        agg = "count(*)" if expr is None else f"sum({expr})"
        parts.append(f"{agg} FILTER (WHERE NOT outside) AS {stem}_all")
        parts.append(f"{agg} FILTER (WHERE slab AND NOT outside) AS {stem}_slab")
    parts.append("sum(energy) FILTER (WHERE outside) AS e_out")
    parts.append("count(*) FILTER (WHERE outside) AS n_out")
    return ",\n        ".join(parts)


def build_sql(
    record: ExperimentRecord,
    spec: FilterSpec,
    grid: CanonicalGrid,
    k: int,
    sampled: bool = False,
) -> str:
    """Render the canonical accumulation query.

    Parameters bound at execution: ``$x_coords``, ``$y_coords`` (the lattice
    coordinate arrays), ``$zf`` (front face), ``$wx``, ``$wy`` (cell footprint),
    and the kinematic filter's ``$e1_min`` ... ``$d_max``.
    """
    assert record.lattice is not None
    k = int(max(1, k))
    event = quote(naming.event_table(record.table_name))
    proj = quote(naming.proj_table(record.table_name, sampled=sampled))
    return f"""
    WITH ev AS (
        SELECT event_number, {_ENTRY_SQL}
        FROM {event}
        WHERE {spec.where_sql()} AND {_FRAME_DEFINED}
    ), fr AS (
        SELECT event_number,
               (xa + xb) / 2 AS x0, (ya + yb) / 2 AS y0,
               cos(atan2(yb - ya, xb - xa)) AS c, sin(atan2(yb - ya, xb - xa)) AS s
        FROM ev
    ), sub AS (
        SELECT (u.range + 0.5) / {k} - 0.5 AS fx, (v.range + 0.5) / {k} - 0.5 AS fy
        FROM range({k}) u, range({k}) v
    ), pts AS (
        SELECT p.iz, p.energy / {k * k} AS energy, p.ge, p.fa_pred, p.fa_true,
               list_extract($x_coords, p.ix + 1) + sub.fx * $wx - f.x0 AS xt,
               list_extract($y_coords, p.iy + 1) + sub.fy * $wy - f.y0 AS yt,
               f.c, f.s
        FROM {proj} p
        JOIN fr f USING (event_number), sub
        WHERE {spec.where_sql("p")}
    ), rot AS (
        SELECT c * xt + s * yt AS xc, -s * xt + c * yt AS yc,
               iz, energy, ge, fa_pred, fa_true
        FROM pts
    ), binned AS (
        SELECT CAST(floor((xc + {grid.half_x!r}) / {grid.pitch!r}) AS INTEGER) AS jx,
               CAST(floor((yc + {grid.half_y!r}) / {grid.pitch!r}) AS INTEGER) AS jy,
               iz, energy, ge, fa_pred, fa_true,
               (iz <= {record.lattice.slab_iz}) AS slab,
               (xc < -{grid.half_x!r} OR xc >= {grid.half_x!r}
                OR yc < -{grid.half_y!r} OR yc >= {grid.half_y!r}) AS outside
        FROM rot
    )
    SELECT GROUPING_ID(jx, jy, iz) AS gid, jx, jy, iz,
        {_aggregates()}
    FROM binned
    GROUP BY GROUPING SETS ((jx, jy), (jy, iz), (jx, iz))
    """


def _params(record: ExperimentRecord, spec: FilterSpec, footprint: tuple[float, float]) -> dict:
    assert record.lattice is not None
    return {
        **spec.params(),
        "zf": float(record.lattice.z.lo),
        "x_coords": [float(v) for v in record.lattice.x.coords],
        "y_coords": [float(v) for v in record.lattice.y.coords],
        "wx": float(footprint[0]),
        "wy": float(footprint[1]),
    }


def _column(columns: dict[str, Any], name: str) -> np.ndarray:
    """A result column as float64 with NULLs as NaN.

    ``fetchnumpy`` returns masked arrays for columns holding NULLs (the
    FILTERed aggregates and the absent grouping keys); integer columns cannot
    be filled with NaN directly, so everything is widened to float first.
    """
    masked = np.ma.asarray(columns[name]).astype(np.float64)
    return np.asarray(np.ma.filled(masked, np.nan), dtype=np.float64)


def _empty(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {name: np.zeros(shape, dtype=np.float64) for name in PLANES}


def fetch_canonical(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    stats: FrameStats,
    grid: CanonicalGrid,
    k: int,
    footprint: tuple[float, float],
    sampled: bool = False,
    sample_percent: float = 100.0,
) -> CanonicalBundle:
    """Run the accumulation scan and assemble the three canonical panels."""
    assert record.lattice is not None
    sql = build_sql(record, spec, grid, k, sampled)
    started = time.perf_counter()
    columns = con.execute(sql, _params(record, spec, footprint)).fetchnumpy()
    query_ms = (time.perf_counter() - started) * 1000.0

    gid = np.nan_to_num(_column(columns, "gid")).astype(np.int64)
    jx = np.nan_to_num(_column(columns, "jx"), nan=-1).astype(np.int64)
    jy = np.nan_to_num(_column(columns, "jy"), nan=-1).astype(np.int64)
    iz = np.nan_to_num(_column(columns, "iz"), nan=-1).astype(np.int64)

    xy = Panel("xy", "y", "x", _empty(grid.shape_xy))
    yz = Panel("yz", "y", "z", _empty(grid.shape_yz))
    xz = Panel("xz", "x", "z", _empty(grid.shape_xz))

    def scatter(
        panel: Panel, mask: np.ndarray, rows: np.ndarray, n_rows: int,
        cols: np.ndarray, n_cols: int, suffix: str,
    ) -> None:
        # Groups whose bin fell outside the window carry only the FILTERed
        # aggregates (NULL -> 0) and indices out of range; they are dropped here,
        # their energy having been counted in e_out.
        keep = mask & (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
        if not keep.any():
            return
        r = rows[keep]
        c = cols[keep]
        for plane, stem in _PLANE_SOURCE.items():
            values = np.nan_to_num(_column(columns, f"{stem}_{suffix}")[keep])
            panel.planes[plane][r, c] = values

    scatter(xy, gid == GID_XY, jy, grid.n_y, jx, grid.n_x, "slab")
    scatter(yz, gid == GID_YZ, jy, grid.n_y, iz, grid.n_z, "all")
    scatter(xz, gid == GID_XZ, jx, grid.n_x, iz, grid.n_z, "all")

    # Each outside sub-deposit appears in exactly one group of each grouping
    # set, so summing e_out over one set counts it once.
    xz_rows = gid == GID_XZ
    energy_outside = float(np.nan_to_num(_column(columns, "e_out")[xz_rows]).sum())
    n_outside = int(np.nan_to_num(_column(columns, "n_out")[xz_rows]).sum())
    n_hits = int(round(xz.planes["n"].sum() / (k * k))) + int(round(n_outside / (k * k)))

    bundle = CanonicalBundle(
        xy=xy, yz=yz, xz=xz,
        grid=grid, stats=stats, lattice=record.lattice,
        subsample_k=k, footprint=footprint,
        energy_outside=energy_outside, n_outside=n_outside,
        exact=not sampled, query_ms=query_ms, n_hits=n_hits,
        sample_percent=sample_percent,
    )
    log.debug(
        "Canonical scan for %s in %.1f ms (%s hits, k=%d, sampled=%s, %.4f%% outside)",
        record.table_name, query_ms, f"{n_hits:,}", k, sampled,
        100.0 * bundle.energy_fraction_outside,
    )
    return bundle


def scale_sample(bundle: CanonicalBundle, percent: float) -> CanonicalBundle:
    """Scale a sampled bundle's extensive planes up to full-population estimates.

    Same reasoning as ``projections.scale_sample``: a Bernoulli sample is an
    unbiased estimator of a sum up to the inclusion probability. The event
    count used to normalise the density comes from the exact event table, so
    the density estimate stays unbiased too. The outside-window energy is an
    extensive sum as well and is scaled with the rest.
    """
    factor = 100.0 / percent if percent > 0 else 1.0
    for panel in (bundle.xy, bundle.yz, bundle.xz):
        for plane in panel.planes.values():
            plane *= factor
    bundle.energy_outside *= factor
    bundle.n_outside = int(round(bundle.n_outside * factor))
    bundle.n_hits = int(round(bundle.n_hits * factor))
    bundle.sample_percent = percent
    return bundle


def explain(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    grid: CanonicalGrid,
    k: int,
    footprint: tuple[float, float],
    sampled: bool = False,
) -> str:
    """``EXPLAIN`` output for the canonical query.

    The projection table must appear exactly once: the plan also scans the
    small per-event table and two ``RANGE`` generators for the sub-deposits,
    which a test documents so a DuckDB upgrade that started scanning the hit
    table twice would be caught.
    """
    sql = build_sql(record, spec, grid, k, sampled)
    rows = con.execute("EXPLAIN " + sql, _params(record, spec, footprint)).fetchall()
    return "\n".join(str(r[-1]) for r in rows)


def cache_key(spec: FilterSpec, sampled: bool, grid: CanonicalGrid, k: int,
              footprint: tuple[float, float]) -> tuple:
    """Identity of a canonical bundle. ``table_name`` stays first for invalidation."""
    return (
        *spec.cache_key(), sampled, "canonical",
        round(grid.pitch, 3), round(grid.half_x, 3), round(grid.half_y, 3),
        int(k), round(footprint[0], 3), round(footprint[1], 3),
    )
