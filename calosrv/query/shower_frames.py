"""The translated and local frames: every shower co-registered on its own entry point.

In both frames each hit is expressed relative to *its own shower*: translated by
that shower's entry point P0 (the energy-weighted x, y centroid of its first
populated layer, at that layer's z), and - in the local frame - rotated by that
shower's own R(theta, phi), so its incident direction lies along +w. The two
showers of every event therefore sit on top of each other at the origin. The
coordinates are the input file's own ``x/y_trans`` and ``x/y/z_local`` columns,
verified at ingest to be exactly that transform.

**Footprints, not points.** A hit is a 48.27 x 48.6 mm cell. Point-binning its
co-registered centre would comb (CLAUDE.md section 2), so its energy is spread
over its physical footprint in both frames - by different means:

* *Translated* - no rotation, so the footprint stays an axis-aligned box and
  its area-weighted overlap with the 20 mm grid is computed **exactly**. The
  overlap of a box of width w with bins of pitch p is, over the bins it
  touches, affine in the fractional position phi of its left edge within its
  first bin (see :func:`box_overlap_operator`). So the SQL aggregates one row
  per hit into the moments sum(v), sum(v*phi_x), sum(v*phi_y), sum(v*phi_x*phi_y)
  keyed by (first bin, side), and NumPy expands them exactly with two
  coefficient matrices per axis. Measured against brute-force overlap on 200 k
  random boxes: maximum relative error 1.4e-15, energy conserved exactly.
* *Local* - each cell's footprint box (x, y and the 20.5 mm layer pitch) is
  sampled by k x k x k_z sub-deposits in laboratory axes and each offset
  rotated by the shower's own R before being added to the local centre; k >= 2
  always, from a row budget, and k_z = 2 by default.

Depth is each shower's own layers counted from its first (translated) or
uniform bins of the layer pitch along w (local); it is never smoothed.

**Where the coordinates come from.** Every scan joins the shower's SE(3)
element from ``query/frame_sql.py`` (the file's own P0 and (theta, phi), as
the event table holds them) and applies it to the hit's laboratory lattice
position inside the scan, so each hit has two sets of frame coordinates: the
file's columns and the motion's own. The ``file`` source (the default) bins
the file's columns, as the frames always did; ``computed`` bins the motion's,
which needs no ``*_trans`` / ``*_local`` columns at all. Either way the
largest difference between the two over the selection is aggregated in the
same scan and reported with every response, beside the ingest-time figure,
so a reader can see that the two are interchangeable - or that they are not.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..config import Settings
from ..db import ddl, naming, registry
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..grid import frame as frame_mod
from ..grid.frame import CanonicalGrid, KIND_LOCAL, KIND_TRANS
from ..grid.lattice import Axis, Lattice
from . import frame_sql
from . import planes as planes_mod
from .canonical import Moments, _column
from . import cache as cache_mod
from . import canonical, density, filters
from .filters import FilterSpec
from .frame_sql import SOURCE_COMPUTED, SOURCE_FILE
from .projections import GID_XY, GID_XZ, GID_YZ, PLANES, Panel

log = logging.getLogger(__name__)

#: How each frame writes its axes; the semantic names stay x, y, z.
SYMBOLS = {
    KIND_TRANS: {"x": "Δx", "y": "Δy", "z": "Δz"},
    KIND_LOCAL: {"x": "u", "y": "v", "z": "w"},
}

DEPTH_POLICY = {
    KIND_TRANS: "each shower's own sampling layers counted from its first, never smoothed",
    KIND_LOCAL: "uniform bins of the layer pitch along w, never smoothed or interpolated",
}

SPLAT_REGIME = {KIND_TRANS: "box_overlap", KIND_LOCAL: "subdeposit3d"}

#: Planes whose outside-grid mass is tracked besides energy.
OUTSIDE_PLANES = ("eg", "esp", "esn")

#: The largest difference between the file's frame coordinates and the
#: motion's own at which the two are called interchangeable: the ingest
#: tolerance of the rotation check (``ingest/verify.py``).
COORDINATE_TOLERANCE_MM = 0.01

#: The ingest-report value each frame's residual is read beside: the
#: translation is rigid to ``p0_spread_mm``, the rotation to
#: ``rotation_residual_mm``.
INGEST_RESIDUAL_KEY = {KIND_TRANS: "p0_spread_mm", KIND_LOCAL: "rotation_residual_mm"}


# ------------------------------------------------------------ statistics --


@dataclass
class ShowerStats:
    """What a per-shower frame knows about a selection before scanning hits."""

    kind: str
    n_selected: int
    n_events: int
    n_hits: int
    n_ab: int
    theta_max: float | None
    d_dataset: Moments
    #: Per shower and axis: moments of the per-event centroid offset from P0,
    #: in this frame (``centroid_*_trans`` / ``centroid_*_local``).
    mean: dict[str, dict[str, Moments]]
    #: Laboratory-azimuth mean resultant length per shower.
    phi_resultant: dict[str, float | None]
    #: Events whose selected network's Grad-CAM / Shap-CAM map is all zero.
    cam_zero: dict[str, int]

    @property
    def n_excluded_no_frame(self) -> int:
        return max(0, self.n_selected - self.n_events)

    @property
    def n_showers(self) -> int:
        return 2 * self.n_events

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "n_selected": self.n_selected,
            "n_excluded_no_frame": self.n_excluded_no_frame,
            "n_showers": self.n_showers,
            "n_hits": self.n_hits,
            "n_ab_hits": self.n_ab,
            "theta_max": self.theta_max,
            "d_dataset": self.d_dataset.as_dict(),
            "phi_resultant": self.phi_resultant,
            "cam_zero_events": self.cam_zero,
        }


def shower_statistics(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    kind: str,
    model: str,
) -> ShowerStats:
    """Per-event statistics for the selection. Reads only the event table.

    As in the canonical frame, only events with a defined separation are
    co-registered: an event without shower A has no D and is excluded from N
    even when ``include_undefined_d`` admits it elsewhere; the count is reported.
    """
    table = quote(naming.event_table(record.table_name))
    suffix = "_t" if kind == KIND_TRANS else "_l"
    where = spec.where_sql()
    centroid = []
    for shower in "ab":
        for axis in "xyz":
            c = f"CAST(c{shower}{axis}{suffix} AS DOUBLE)"
            centroid.append(f"avg({c}), median({c}), stddev_samp({c}), min({c}), max({c}), count({c})")
    gc_bit = 1 << ddl.cam_bit(model, kind, "gradcam")
    sc_bit = 1 << ddl.cam_bit(model, kind, "shapcam")
    row = con.execute(
        f"""
        SELECT
            (SELECT count(*) FROM {table} WHERE {where})    AS n_selected,
            count(*), coalesce(sum(n_hits), 0), coalesce(sum(n_ab_rows), 0),
            max(greatest(theta_a, theta_b)),
            avg(d), median(d), stddev_samp(d), min(d), max(d),
            {", ".join(centroid)},
            avg(cos(CAST(phi_a AS DOUBLE))), avg(sin(CAST(phi_a AS DOUBLE))),
            avg(cos(CAST(phi_b AS DOUBLE))), avg(sin(CAST(phi_b AS DOUBLE))),
            count(*) FILTER (WHERE (cam_zero_mask & {gc_bit}) <> 0),
            count(*) FILTER (WHERE (cam_zero_mask & {sc_bit}) <> 0)
        FROM {table}
        WHERE {where} AND d IS NOT NULL
        """,
        spec.params(),
    ).fetchone()

    def f(i: int) -> float | None:
        v = row[i]
        return float(v) if v is not None and math.isfinite(float(v)) else None

    n_events = int(row[1] or 0)
    mean: dict[str, dict[str, Moments]] = {}
    i = 10
    for shower in "ab":
        mean[shower] = {}
        for axis in "xyz":
            mean[shower][axis] = Moments(f(i), f(i + 1), f(i + 2), f(i + 3), f(i + 4), int(row[i + 5] or 0))
            i += 6
    ensemble = n_events >= 2

    def resultant(c: int, s: int) -> float | None:
        if not ensemble or f(c) is None or f(s) is None:
            return None
        return float(math.hypot(f(c), f(s)))

    return ShowerStats(
        kind=kind,
        n_selected=int(row[0] or 0),
        n_events=n_events,
        n_hits=int(row[2] or 0),
        n_ab=int(row[3] or 0),
        theta_max=f(4),
        d_dataset=Moments(f(5), f(6), f(7), f(8), f(9), n_events),
        mean=mean,
        phi_resultant={"a": resultant(i, i + 1), "b": resultant(i + 2, i + 3)},
        cam_zero={"gradcam": int(row[i + 4] or 0), "shapcam": int(row[i + 5] or 0)},
    )


# ---------------------------------------------------------------- bundle --


@dataclass
class ShowerBundle:
    """Accumulation-grid aggregates of one per-shower frame for one selection.

    Shaped like ``canonical.CanonicalBundle`` - three ``Panel`` objects over a
    uniform grid answered by :meth:`axis` - so the canonical renderer, window
    fit, centroids and comb measurement serve it unchanged.
    """

    xy: Panel
    yz: Panel
    xz: Panel
    grid: CanonicalGrid
    stats: ShowerStats
    lattice: Lattice
    kind: str
    subsample_k: int
    k_z: int
    footprint: tuple[float, float]
    energy_outside: float
    n_outside: int
    exact: bool
    query_ms: float
    n_hits: int
    sample_percent: float = 100.0
    model: str = "segmentation"
    plane_outside: dict[str, float] = field(default_factory=dict)
    #: Which coordinates the panels were binned from (``frame_sql.SOURCES``),
    #: and the largest |file - computed| over the selection's hits, in mm.
    coordinate_source: str = SOURCE_FILE
    coordinate_residual_mm: float | None = None

    @property
    def splat_regime(self) -> str:
        return SPLAT_REGIME[self.kind]

    @property
    def symbols(self) -> dict[str, str]:
        return SYMBOLS[self.kind]

    @property
    def depth_policy(self) -> str:
        return DEPTH_POLICY[self.kind]

    @property
    def depth_clause(self) -> str:
        if self.kind == KIND_TRANS:
            return "depth keeps each shower's own sampling layers"
        return "depth w keeps its layer-pitch bins"

    @property
    def depth_warning(self) -> str:
        """The Continuous Field depth sentence, in this frame's terms."""
        n_z = self.grid.n_z
        if self.kind == KIND_TRANS:
            return (
                f"Depth is locked to each shower's own {n_z} sampling layers, counted from its "
                "first; there is no measurement between layers to interpolate."
            )
        return (
            f"Depth w is binned at the {self.grid.axis('z').edges[1] - self.grid.axis('z').edges[0]:.1f} mm "
            f"layer pitch ({n_z} bins), from {self.k_z} depth sub-deposit(s) per rotated cell; "
            "it is never smoothed or interpolated."
        )

    def panel(self, name: str) -> Panel:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def axis(self, name: str) -> Axis:
        return self.grid.axis(name)

    @property
    def n_events(self) -> int:
        return self.stats.n_events

    @property
    def total_energy(self) -> float:
        return float(self.xz.planes["e"].sum())

    @property
    def energy_fraction_outside(self) -> float:
        total = self.total_energy + self.energy_outside
        return self.energy_outside / total if total > 0 else 0.0

    @property
    def nbytes(self) -> int:
        return sum(
            plane.nbytes for panel in (self.xy, self.yz, self.xz)
            for plane in panel.planes.values()
        )


def _plane_columns(model: str, kind: str) -> tuple[str, ...]:
    return (
        ddl.cam_column(model, kind, "gradcam"), ddl.cam_column(model, kind, "shapcam"),
        ddl.seg_column("true", kind), ddl.seg_column("pred", kind),
    )


def _values(model: str, kind: str) -> list[tuple[str, str]]:
    """``(plane, per-row value)``; a count is the constant 1."""
    return [(plane, "1.0" if expr is None else expr) for plane, expr in planes_mod.measures(kind, model)]


def _params(record: ExperimentRecord, spec: FilterSpec) -> dict[str, Any]:
    """The filter's parameters plus the lattice coordinate arrays the motion reads."""
    assert record.lattice is not None
    return {
        **spec.params(),
        "x_coords": [float(v) for v in record.lattice.x.coords],
        "y_coords": [float(v) for v in record.lattice.y.coords],
        "z_coords": [float(v) for v in record.lattice.z.coords],
    }


def _hit_frame_sql(kind: str, record: ExperimentRecord, spec: FilterSpec, columns: str,
                   proj: str, event: str, layer_pitch: float) -> str:
    """The ``fr`` CTE and a ``hit`` CTE carrying both coordinate sets of every hit.

    ``hit`` holds the file's own frame coordinates (``xf, yf, zf``; the
    translated depth as ``kt * pitch``), the motion's (``xc, yc, zc``), their
    largest difference ``resid`` and the rotation entries ``r11 .. r33``, so
    the two scans below choose a source and aggregate the residual without
    repeating any of it.
    """
    xc, yc, zc = frame_sql.transform_sql("hx", "hy", "hz", "f.")
    if kind == KIND_TRANS:
        file_xyz = ("CAST(p.xt AS DOUBLE)", "CAST(p.yt AS DOUBLE)",
                    f"CAST(p.kt AS DOUBLE) * {float(layer_pitch)!r}::DOUBLE")
    else:
        file_xyz = ("CAST(p.xl AS DOUBLE)", "CAST(p.yl AS DOUBLE)", "CAST(p.zl AS DOUBLE)")
    return f"""{frame_sql.shower_frame_cte(event, spec.where_sql(), kind)}, hit AS (
        SELECT p.event_number, p.kt, p.energy, {columns},
               {file_xyz[0]} AS xf, {file_xyz[1]} AS yf, {file_xyz[2]} AS zf,
               {xc} AS xc, {yc} AS yc, {zc} AS zc,
               f.r11, f.r12, f.r13, f.r21, f.r22, f.r23, f.r31, f.r32, f.r33
        FROM (SELECT p.event_number, p.org, p.kt, p.xt, p.yt, p.xl, p.yl, p.zl, p.energy, {columns},
                     list_extract($x_coords, p.ix + 1) AS hx,
                     list_extract($y_coords, p.iy + 1) AS hy,
                     list_extract($z_coords, p.iz + 1) AS hz
              FROM {proj} p WHERE {spec.where_sql("p")} AND p.d IS NOT NULL) p
        JOIN fr f ON p.event_number = f.event_number
                 AND f.b = CASE WHEN p.org = {ddl.ORIGIN_A} THEN 0 ELSE 1 END
    ), src AS (
        SELECT *, greatest(abs(xc - xf), abs(yc - yf), abs(zc - zf)) AS resid
        FROM hit
    )"""


# ------------------------------------------------ translated: box overlap --


def box_overlap_operator(n_bins: int, width: float, pitch: float, key_lo: int, key_hi: int):
    """Coefficient matrices ``(A, B)`` of the exact box-overlap splat along one axis.

    A box of width ``w`` whose left edge sits at ``u = j0 + phi`` bins into the
    axis (``0 <= phi < 1``) overlaps bins ``j0 .. j0 + m + 1``, ``m = floor(w/p)``,
    ``r = w/p - m``, by these fractions of its area (``q = p / w``)::

        bin j0          q (1 - phi)
        bins +1..+m-1   q
        bin j0+m        q (r + phi)    if phi < 1 - r   (side s = 0)
                        q              otherwise        (side s = 1)
        bin j0+m+1      q (r - 1 + phi) if s = 1, else 0

    Each is ``a + b * phi`` with ``(a, b)`` fixed by the bin offset and the side;
    they sum to 1. So a hit contributes ``A[:, key] * v + B[:, key] * v * phi``,
    where ``key = 2 * j0 + s``. Columns run over keys ``key_lo .. key_hi``;
    bins outside ``0 .. n_bins - 1`` are dropped - that is the energy outside
    the grid, counted by the caller.
    """
    w, p = float(width), float(pitch)
    m = int(math.floor(w / p))
    if m < 1:  # pragma: no cover - the detector's cells are wider than the grid pitch
        raise ValueError("box_overlap_operator needs a box at least one bin wide")
    r = w / p - m
    q = p / w
    n_keys = key_hi - key_lo + 1
    a_mat = np.zeros((n_bins, n_keys))
    b_mat = np.zeros((n_bins, n_keys))
    for col, key in enumerate(range(key_lo, key_hi + 1)):
        j0 = key // 2
        side = key - 2 * j0
        terms = [(0, q, -q)]
        terms += [(b, q, 0.0) for b in range(1, m)]
        terms.append((m, q * r, q) if side == 0 else (m, q, 0.0))
        if side == 1:
            terms.append((m + 1, q * (r - 1.0), q))
        for offset, a, b in terms:
            bin_index = j0 + offset
            if 0 <= bin_index < n_bins:
                a_mat[bin_index, col] += a
                b_mat[bin_index, col] += b
    return a_mat, b_mat


#: Key given to a translated-frame hit outside the grid on every axis. Its
#: groups carry the outside mass; no real key comes near it.
OUTSIDE_KEY = -(1 << 30)


def _trans_sql(record, spec, grid, footprint, model, sampled, layer_pitch,
               source=SOURCE_FILE) -> tuple[str, str]:
    """The XY (entrance slab) and depth moment queries of the translated frame.

    A hit whose footprint is not wholly inside the accumulation grid is counted
    outside - in every panel alike, so the three panels always hold the same
    hits. It is keyed :data:`OUTSIDE_KEY` on every axis, so its group carries
    the outside sums and inside + outside equals the hits' own sums exactly,
    with plain sums and no FILTER on the hot path. The grid is planned from
    the dataset's 1e-4 and 0.9999 energy quantiles plus half a footprint, so
    this is a thin tail.

    ``source`` picks the file's own ``x/y_trans`` and own-shower layer or the
    motion's (``_hit_frame_sql``); the residual between the two rides along
    the depth query as a ``max`` aggregate and never touches the sums.
    """
    assert record.lattice is not None
    proj = quote(naming.proj_table(record.table_name, sampled=sampled))
    event = quote(naming.event_table(record.table_name))
    wx, wy = (float(v) for v in footprint)
    p = float(grid.pitch)
    rx = wx / p - math.floor(wx / p)
    ry = wy / p - math.floor(wy / p)
    values = _values(model, KIND_TRANS)
    per_hit = ",\n               ".join(f"CAST({value} AS DOUBLE) AS v_{plane}" for plane, value in values)
    carried = ", ".join(f"v_{plane}" for plane, _ in values)
    columns = ", ".join(f"p.{c}" for c in _plane_columns(model, KIND_TRANS))
    if source == SOURCE_FILE:
        pos_x, pos_y, pos_k = "xf", "yf", "kt"
    else:
        pos_x, pos_y = "xc", "yc"
        pos_k = f"CAST(round(zc / {float(layer_pitch)!r}::DOUBLE) AS INTEGER)"
    # Every coordinate and constant is DOUBLE: a REAL column combined with a
    # decimal literal is evaluated in single precision, which cost the edge
    # fractions 1e-4 of relative precision against a brute-force overlap.
    base = f"""
    WITH {_hit_frame_sql(KIND_TRANS, record, spec, columns, proj, event, layer_pitch)}, pos AS (
        SELECT {pos_k} AS kt, {pos_x} AS x, {pos_y} AS y, resid,
               {per_hit}
        FROM src
    ), sel AS (
        SELECT kt, {carried}, resid,
               (x - {0.5 * wx!r}::DOUBLE + {grid.half_x!r}::DOUBLE) / {p!r}::DOUBLE AS ux,
               (y - {0.5 * wy!r}::DOUBLE + {grid.half_y!r}::DOUBLE) / {p!r}::DOUBLE AS uy,
               (x - {0.5 * wx!r}::DOUBLE < -{grid.half_x!r}::DOUBLE
                OR x + {0.5 * wx!r}::DOUBLE > {grid.half_x!r}::DOUBLE
                OR y - {0.5 * wy!r}::DOUBLE < -{grid.half_y!r}::DOUBLE
                OR y + {0.5 * wy!r}::DOUBLE > {grid.half_y!r}::DOUBLE
                OR kt >= {grid.n_z}) AS outside
        FROM pos
    ), keyed AS (
        SELECT kt, {carried}, outside, resid,
               ux - floor(ux) AS fx, uy - floor(uy) AS fy,
               CASE WHEN outside THEN {OUTSIDE_KEY} ELSE CAST(2 * floor(ux)
                    + CASE WHEN ux - floor(ux) >= {1.0 - rx!r}::DOUBLE THEN 1 ELSE 0 END AS BIGINT)
               END AS kx,
               CASE WHEN outside THEN {OUTSIDE_KEY} ELSE CAST(2 * floor(uy)
                    + CASE WHEN uy - floor(uy) >= {1.0 - ry!r}::DOUBLE THEN 1 ELSE 0 END AS BIGINT)
               END AS ky,
               CASE WHEN outside THEN {OUTSIDE_KEY} ELSE kt END AS jt
        FROM sel
    )"""
    xy_parts, depth_parts = [], []
    for plane, _ in values:
        v = f"v_{plane}"
        xy_parts += [f"sum({v}) AS {plane}_00", f"sum({v} * fx) AS {plane}_10",
                     f"sum({v} * fy) AS {plane}_01", f"sum({v} * fx * fy) AS {plane}_11"]
        depth_parts += [f"sum({v}) AS {plane}_0", f"sum({v} * fx) AS {plane}_x",
                        f"sum({v} * fy) AS {plane}_y"]
    xy_sql = base + f"""
    SELECT kx, ky, {", ".join(xy_parts)}
    FROM keyed WHERE kt <= {record.lattice.slab_iz} AND NOT outside GROUP BY kx, ky"""
    depth_sql = base + f"""
    SELECT GROUPING_ID(kx, ky, jt) AS gid, kx, ky, jt AS kt, max(resid) AS resid,
           {", ".join(depth_parts)}
    FROM keyed GROUP BY GROUPING SETS ((ky, jt), (kx, jt))"""
    return xy_sql, depth_sql


def _dense(keys_r, keys_c, values, lo_r, n_r, lo_c, n_c) -> np.ndarray:
    out = np.zeros((n_r, n_c))
    np.add.at(out, (keys_r - lo_r, keys_c - lo_c), values)
    return out


def _residual(columns: dict[str, Any]) -> float | None:
    """The largest |file - computed| coordinate difference the scan aggregated."""
    values = np.nan_to_num(_column(columns, "resid"), nan=-1.0)
    return float(values.max()) if values.size and values.max() >= 0 else None


def _fetch_trans(con, record, spec, grid, footprint, model, sampled, layer_pitch, source):
    xy_sql, depth_sql = _trans_sql(record, spec, grid, footprint, model, sampled, layer_pitch, source)
    params = _params(record, spec)
    started = time.perf_counter()
    xy_cols = con.execute(xy_sql, params).fetchnumpy()
    depth_cols = con.execute(depth_sql, params).fetchnumpy()
    query_ms = (time.perf_counter() - started) * 1000.0

    n_x, n_y, n_z = grid.n_x, grid.n_y, grid.n_z
    wx, wy = footprint
    xy_panel = Panel("xy", "y", "x", {name: np.zeros(grid.shape_xy) for name in PLANES})
    yz_panel = Panel("yz", "y", "z", {name: np.zeros(grid.shape_yz) for name in PLANES})
    xz_panel = Panel("xz", "x", "z", {name: np.zeros(grid.shape_xz) for name in PLANES})

    # X'Y': four moments per plane on a (ky, kx) key grid, expanded exactly.
    kx = np.nan_to_num(_column(xy_cols, "kx")).astype(np.int64)
    ky = np.nan_to_num(_column(xy_cols, "ky")).astype(np.int64)
    if kx.size:
        lo_x, hi_x = int(kx.min()), int(kx.max())
        lo_y, hi_y = int(ky.min()), int(ky.max())
        ax, bx = box_overlap_operator(n_x, wx, grid.pitch, lo_x, hi_x)
        ay, by = box_overlap_operator(n_y, wy, grid.pitch, lo_y, hi_y)
        nkx, nky = hi_x - lo_x + 1, hi_y - lo_y + 1
        for plane in PLANES:
            m = {suffix: _dense(ky, kx, np.nan_to_num(_column(xy_cols, f"{plane}_{suffix}")),
                                lo_y, nky, lo_x, nkx)
                 for suffix in ("00", "10", "01", "11")}
            xy_panel.planes[plane] = (
                ay @ m["00"] @ ax.T + ay @ m["10"] @ bx.T
                + by @ m["01"] @ ax.T + by @ m["11"] @ bx.T
            )

    # The depth panels: one transverse key axis and the own-shower layer.
    # Outside hits are keyed OUTSIDE_KEY on every axis: one group per set,
    # dropped here and summed as the outside mass below.
    gid = np.nan_to_num(_column(depth_cols, "gid")).astype(np.int64)
    kt = np.nan_to_num(_column(depth_cols, "kt"), nan=-1).astype(np.int64)
    for panel, key_name, n_bins, width, moment, gid_value in (
        (yz_panel, "ky", n_y, wy, "y", GID_YZ), (xz_panel, "kx", n_x, wx, "x", GID_XZ),
    ):
        rows = gid == gid_value
        keys = np.nan_to_num(_column(depth_cols, key_name)[rows]).astype(np.int64)
        layers = kt[rows]
        keep = (layers >= 0) & (layers < n_z) & (keys != OUTSIDE_KEY)
        if not keep.any():
            continue
        keys, layers = keys[keep], layers[keep]
        lo, hi = int(keys.min()), int(keys.max())
        a_mat, b_mat = box_overlap_operator(n_bins, width, grid.pitch, lo, hi)
        for plane in PLANES:
            m0 = _dense(keys, layers, np.nan_to_num(_column(depth_cols, f"{plane}_0")[rows][keep]),
                        lo, hi - lo + 1, 0, n_z)
            m1 = _dense(keys, layers,
                        np.nan_to_num(_column(depth_cols, f"{plane}_{moment}")[rows][keep]),
                        lo, hi - lo + 1, 0, n_z)
            panel.planes[plane] = a_mat @ m0 + b_mat @ m1

    out_rows = (gid == GID_XZ) & (kt == OUTSIDE_KEY)
    outside = {plane: float(np.nan_to_num(_column(depth_cols, f"{plane}_0")[out_rows]).sum())
               for plane in PLANES}
    n_hits = int(round(float(xz_panel.planes["n"].sum()) + outside["n"]))
    return (xy_panel, yz_panel, xz_panel), outside, n_hits, query_ms, _residual(depth_cols)


# ----------------------------------------------------- local: sub-deposits --


def _local_sql(record, spec, grid, footprint, layer_pitch, k, k_z, model, sampled,
               source=SOURCE_FILE) -> tuple[str, str]:
    """The X'Y' (entrance slab) and depth queries of the local frame.

    Each hit joins its own shower's SE(3) element - a 40 000-row CTE from the
    event table (``query/frame_sql.py``) - and is split into ``k x k x k_z``
    sub-deposits whose offsets over the cell's footprint box are rotated by
    that R. Every plane value is divided by the sub-deposit count once per
    hit, before the split, so the aggregation is nine plain sums. A
    sub-deposit outside the grid is binned at the sentinel key -1 on every
    axis; its group carries the outside mass, so inside + outside equals the
    hits' sums with no FILTER on the hot path. The slab panel runs as its own
    query over slab rows only.

    ``source`` picks the file's own ``x/y/z_local`` or the motion's as the
    sub-deposits' centre; the residual between the two rides along the depth
    query as a ``max`` aggregate.
    """
    assert record.lattice is not None
    proj = quote(naming.proj_table(record.table_name, sampled=sampled))
    event = quote(naming.event_table(record.table_name))
    wx, wy = (float(v) for v in footprint)
    wz = float(layer_pitch)
    p = float(grid.pitch)
    z_edges = grid.axis("z").edges
    z0, z1 = float(z_edges[0]), float(z_edges[-1])
    n = k * k * k_z
    values = _values(model, KIND_LOCAL)
    per_hit = ",\n               ".join(
        f"CAST({value} AS DOUBLE) / {n}.0 AS v_{plane}" for plane, value in values)
    carried = ", ".join(f"v_{plane}" for plane, _ in values)
    sums = ", ".join(f"sum(v_{plane}) AS {plane}" for plane, _ in values)
    columns = ", ".join(f"p.{c}" for c in _plane_columns(model, KIND_LOCAL))
    cx, cy, cz = ("xf", "yf", "zf") if source == SOURCE_FILE else ("xc", "yc", "zc")
    base = f"""
    WITH {_hit_frame_sql(KIND_LOCAL, record, spec, columns, proj, event, layer_pitch)}, sub AS (
        SELECT ((u.range + 0.5) / {k} - 0.5) * {wx!r}::DOUBLE AS ox,
               ((v.range + 0.5) / {k} - 0.5) * {wy!r}::DOUBLE AS oy,
               ((w.range + 0.5) / {k_z} - 0.5) * {wz!r}::DOUBLE AS oz
        FROM range({k}) u, range({k}) v, range({k_z}) w
    ), centre AS (
        SELECT kt, {cx} AS xl, {cy} AS yl, {cz} AS zl, resid,
               r11, r12, r13, r21, r22, r31, r32, r33,
               {per_hit}
        FROM src
    ), pts AS (
        SELECT kt, {carried}, resid,
               xl + r11 * ox + r12 * oy + r13 * oz AS xs,
               yl + r21 * ox + r22 * oy AS ys,
               zl + r31 * ox + r32 * oy + r33 * oz AS zs
        FROM centre, sub
    ), binned AS (
        SELECT kt, {carried}, resid,
               (xs < -{grid.half_x!r}::DOUBLE OR xs >= {grid.half_x!r}::DOUBLE
                OR ys < -{grid.half_y!r}::DOUBLE OR ys >= {grid.half_y!r}::DOUBLE
                OR zs < {z0!r}::DOUBLE OR zs >= {z1!r}::DOUBLE) AS outside,
               CAST(floor((xs + {grid.half_x!r}::DOUBLE) / {p!r}::DOUBLE) AS INTEGER) AS ix_,
               CAST(floor((ys + {grid.half_y!r}::DOUBLE) / {p!r}::DOUBLE) AS INTEGER) AS iy_,
               CAST(floor((zs - {z0!r}::DOUBLE) / {wz!r}::DOUBLE) AS INTEGER) AS iz_
        FROM pts
    ), keyed AS (
        SELECT kt, {carried}, resid,
               CASE WHEN outside THEN -1 ELSE ix_ END AS jx,
               CASE WHEN outside THEN -1 ELSE iy_ END AS jy,
               CASE WHEN outside THEN -1 ELSE iz_ END AS jz
        FROM binned
    )"""
    xy_sql = base + f"""
    SELECT jx, jy, {sums}
    FROM keyed WHERE kt <= {record.lattice.slab_iz}
    GROUP BY jx, jy"""
    depth_sql = base + f"""
    SELECT GROUPING_ID(jx, jy, jz) AS gid, jx, jy, jz, max(resid) AS resid, {sums}
    FROM keyed
    GROUP BY GROUPING SETS ((jy, jz), (jx, jz))"""
    return xy_sql, depth_sql


def _fetch_local(con, record, spec, grid, footprint, layer_pitch, k, k_z, model, sampled, source):
    xy_sql, depth_sql = _local_sql(record, spec, grid, footprint, layer_pitch, k, k_z, model,
                                   sampled, source)
    params = _params(record, spec)
    started = time.perf_counter()
    xy_cols = con.execute(xy_sql, params).fetchnumpy()
    depth_cols = con.execute(depth_sql, params).fetchnumpy()
    query_ms = (time.perf_counter() - started) * 1000.0

    xy = Panel("xy", "y", "x", {name: np.zeros(grid.shape_xy) for name in PLANES})
    yz = Panel("yz", "y", "z", {name: np.zeros(grid.shape_yz) for name in PLANES})
    xz = Panel("xz", "x", "z", {name: np.zeros(grid.shape_xz) for name in PLANES})

    def keys(columns, name):
        return np.nan_to_num(_column(columns, name), nan=-2).astype(np.int64)

    def scatter(panel, columns, mask, rows, cols):
        # The sentinel -1 (outside) and absent keys never index a bin.
        n_rows, n_cols = panel.planes["e"].shape
        keep = mask & (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
        for plane in PLANES:
            panel.planes[plane][rows[keep], cols[keep]] = np.nan_to_num(_column(columns, plane)[keep])

    scatter(xy, xy_cols, np.ones(len(xy_cols["jx"]), dtype=bool), keys(xy_cols, "jy"), keys(xy_cols, "jx"))
    gid = np.nan_to_num(_column(depth_cols, "gid")).astype(np.int64)
    jx, jy, jz = keys(depth_cols, "jx"), keys(depth_cols, "jy"), keys(depth_cols, "jz")
    scatter(yz, depth_cols, gid == GID_YZ, jy, jz)
    scatter(xz, depth_cols, gid == GID_XZ, jx, jz)

    outside_rows = (gid == GID_XZ) & (jx == -1) & (jz == -1)
    outside = {plane: float(np.nan_to_num(_column(depth_cols, plane)[outside_rows]).sum())
               for plane in PLANES}
    n_hits = int(round(float(xz.planes["n"].sum()) + outside["n"]))
    return (xy, yz, xz), outside, n_hits, query_ms, _residual(depth_cols)


# ------------------------------------------------------------- the entry --


def fetch(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    stats: ShowerStats,
    grid: CanonicalGrid,
    kind: str,
    footprint: tuple[float, float],
    k: int,
    k_z: int,
    model: str = "segmentation",
    sampled: bool = False,
    sample_percent: float = 100.0,
    source: str = SOURCE_FILE,
) -> ShowerBundle:
    """Run the accumulation scan of one per-shower frame and assemble its panels.

    ``source`` is where the frame coordinates come from (``frame_sql.SOURCES``).
    """
    assert record.lattice is not None and record.frame_bounds is not None
    if source not in frame_sql.SOURCES:
        raise ValueError(f"unknown coordinate source {source!r}")
    pitch = record.frame_bounds.layer_pitch_mm
    if kind == KIND_TRANS:
        panels, outside, n_hits, query_ms, residual = _fetch_trans(
            con, record, spec, grid, footprint, model, sampled, pitch, source)
    else:
        panels, outside, n_hits, query_ms, residual = _fetch_local(
            con, record, spec, grid, footprint, pitch, k, k_z, model, sampled, source)
    xy, yz, xz = panels
    bundle = ShowerBundle(
        xy=xy, yz=yz, xz=xz, grid=grid, stats=stats, lattice=record.lattice, kind=kind,
        subsample_k=k, k_z=k_z, footprint=footprint,
        energy_outside=float(outside.get("e", 0.0)),
        n_outside=int(round(outside.get("n", 0.0))),
        exact=not sampled, query_ms=query_ms, n_hits=n_hits,
        sample_percent=sample_percent, model=model,
        plane_outside={p: float(outside.get(p, 0.0)) for p in OUTSIDE_PLANES},
        coordinate_source=source, coordinate_residual_mm=residual,
    )
    log.debug("%s-frame scan for %s in %.1f ms (%s hits, k=%d, k_z=%d, sampled=%s, %s coordinates, "
              "residual %s mm)", kind, record.table_name, query_ms, f"{n_hits:,}", k, k_z, sampled,
              source, residual)
    return bundle


def scale_sample(bundle: ShowerBundle, percent: float) -> ShowerBundle:
    """Scale a sampled bundle's extensive planes to full-population estimates."""
    factor = 100.0 / percent if percent > 0 else 1.0
    for panel in (bundle.xy, bundle.yz, bundle.xz):
        for plane in panel.planes.values():
            plane *= factor
    bundle.energy_outside *= factor
    bundle.plane_outside = {key: v * factor for key, v in bundle.plane_outside.items()}
    bundle.n_outside = int(round(bundle.n_outside * factor))
    bundle.n_hits = int(round(bundle.n_hits * factor))
    bundle.sample_percent = percent
    return bundle


def explain(con, record, spec, grid, kind, footprint, k, k_z, model="segmentation",
            source=SOURCE_FILE) -> str:
    """``EXPLAIN`` of the scan(s), for the single-scan test."""
    pitch = record.frame_bounds.layer_pitch_mm
    if kind == KIND_TRANS:
        sqls = _trans_sql(record, spec, grid, footprint, model, False, pitch, source)
    else:
        sqls = _local_sql(record, spec, grid, footprint, pitch, k, k_z, model, False, source)
    out = []
    for sql in sqls:
        rows = con.execute("EXPLAIN " + sql, _params(record, spec)).fetchall()
        out.append("\n".join(str(r[-1]) for r in rows))
    return "\n----\n".join(out)


def trajectories_from_origin(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
    limit: int,
) -> list[dict[str, Any]]:
    """Per-event incident directions drawn from the origin, for the translated frame.

    The translated frame does not rotate, so each shower keeps its laboratory
    direction (theta, phi) and starts at its own entry point - the origin.
    Same shape as ``summary.trajectories`` with the anchor at (0, 0, 0).
    """
    table = quote(naming.event_table(record.table_name))
    rows = con.execute(
        f"""
        SELECT event_number, CAST(theta_a AS DOUBLE), CAST(phi_a AS DOUBLE),
               CAST(theta_b AS DOUBLE), CAST(phi_b AS DOUBLE)
        FROM {table}
        WHERE {spec.where_sql()} AND d IS NOT NULL AND theta_a IS NOT NULL
        ORDER BY event_number LIMIT {int(limit)}
        """,
        spec.params(),
    ).fetchall()
    out = []
    for event, ta, pa, tb, pb in rows:
        entry = {"event": int(event), "a": {"theta": ta, "phi": pa, "x": 0.0, "y": 0.0, "z": 0.0}}
        if tb is not None and pb is not None:
            entry["b"] = {"theta": tb, "phi": pb, "x": 0.0, "y": 0.0, "z": 0.0}
        out.append(entry)
    return out


# ----------------------------------------------------------------- cache --

_CACHE_NAME = {KIND_TRANS: cache_mod.TRANS_CACHE, KIND_LOCAL: cache_mod.LOCAL_CACHE}


def cache_for(settings: Settings, kind: str) -> cache_mod.BundleCache:
    return cache_mod.get_cache(settings.canonical_cache_entries, name=_CACHE_NAME[kind])


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
    k_z: int = frame_mod.LOCAL_K_Z,
    source: str = SOURCE_FILE,
) -> tuple[ShowerBundle, ShowerStats, CanonicalGrid, int, bool]:
    """Statistics, grid, sub-sampling factor and the (cached) bundle of a per-shower frame.

    Returns ``(bundle, stats, grid, k, was_cached)``. The grid is the dataset's
    (``plan_shower_window``), so it never depends on the selection. The
    translated frame integrates each footprint exactly and has no ``k``
    (reported as 1); the local frame chooses ``k >= 2`` from the row budget at
    ``k * k * k_z`` rows per hit, capped for the drag preview. ``source`` is
    the coordinate source (``frame_sql.SOURCES``) and is part of the cache key.
    """
    assert record.lattice is not None and record.frame_bounds is not None
    spec = spec.clamped(record)
    stats = shower_statistics(con, record, spec, kind, model)
    grid = frame_mod.plan_shower_window(kind, record.frame_bounds, footprint)
    rows_scanned = int(round(stats.n_hits * (percent / 100.0 if sampled else 1.0)))
    if kind == KIND_TRANS:
        k, k_z = 1, 1
    else:
        k = frame_mod.choose_subsample_3d(rows_scanned, k_z)
        if sampled:
            k = min(k, frame_mod.PREVIEW_MAX_SUBSAMPLE)

    key = canonical.cache_key(spec, sampled, grid, k, footprint, model, kind=kind, k_z=k_z,
                              source=source)

    def compute() -> ShowerBundle:
        bundle = fetch(con, record, spec, stats, grid, kind, footprint, k, k_z,
                       model=model, sampled=sampled, sample_percent=percent, source=source)
        if sampled:
            scale_sample(bundle, percent)
        return bundle

    cache = cache_for(settings, kind)
    bundle, was_cached = cache.get_or_compute(key, compute)
    return bundle, stats, grid, k, was_cached


def density_bundle_for(con, record, spec, settings, kind, footprint, sampled, percent, model,
                       source=SOURCE_FILE):
    """As :func:`bundle_for`, but reuse any network's cached bundle: density reads no CAM plane."""
    assert record.frame_bounds is not None
    clamped = spec.clamped(record)
    stats = shower_statistics(con, record, clamped, kind, model)
    grid = frame_mod.plan_shower_window(kind, record.frame_bounds, footprint)
    rows_scanned = int(round(stats.n_hits * (percent / 100.0 if sampled else 1.0)))
    if kind == KIND_TRANS:
        k, k_z = 1, 1
    else:
        k_z = frame_mod.LOCAL_K_Z
        k = frame_mod.choose_subsample_3d(rows_scanned, k_z)
        if sampled:
            k = min(k, frame_mod.PREVIEW_MAX_SUBSAMPLE)
    keys = [canonical.cache_key(clamped, sampled, grid, k, footprint, m, kind=kind, k_z=k_z,
                                source=source)
            for m in (model, *ddl.MODELS)]
    hit = cache_for(settings, kind).get_any(keys)
    if hit is not None:
        return hit, stats, grid, k, True
    return bundle_for(con, record, spec, settings, kind, footprint, sampled, percent, model,
                      source=source)


def dataset_reference(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    settings: Settings,
    kind: str,
    footprint: tuple[float, float],
) -> dict[str, float]:
    """Peak density of the whole experiment in this frame, from its cached full-range bundle."""
    full = filters.build(record)
    bundle, _, _, k, _ = density_bundle_for(
        con, record, full, settings, kind, footprint, False, 100.0, "segmentation")
    return {**density.selection_peaks(bundle), "k": k}


def warm(
    database, settings: Settings, table_names: Iterable[str],
    after: threading.Thread | None = None, model: str = "segmentation",
) -> threading.Thread:
    """Compute the full-range translated and local bundles in the background, in turn.

    Best effort, like the canonical warmer. ``after`` is a warm-up thread to
    wait for first, so the co-registered scans run one at a time and never
    compete for DuckDB's memory. ``model`` is the network whose bundles are
    built; density requests reuse any model's, the CAM channels need this one.
    """
    names = list(table_names)

    def run() -> None:
        if after is not None:
            after.join()
        for name in names:
            for kind in (KIND_TRANS, KIND_LOCAL):
                try:
                    with database.read_cursor() as con:
                        record = registry.require_ready(con, name)
                        if record.frame_bounds is None:
                            continue
                        footprint = canonical.cell_footprint(con, record)
                        bundle, stats, grid, k, was_cached = bundle_for(
                            con, record, filters.build(record), settings, kind, footprint,
                            False, 100.0, model,
                        )
                    log.info(
                        "%s-frame cache warmed for %s: %s events, k=%d, grid %dx%dx%d in %.0f ms%s",
                        kind, name, f"{stats.n_events:,}", k, grid.n_x, grid.n_y, grid.n_z,
                        bundle.query_ms, " (already cached)" if was_cached else "",
                    )
                except Exception:  # noqa: BLE001 - background convenience, never fatal
                    log.exception("%s-frame cache warm-up failed for %s", kind, name)

    thread = threading.Thread(target=run, name="shower-frame-warm", daemon=True)
    thread.start()
    return thread
