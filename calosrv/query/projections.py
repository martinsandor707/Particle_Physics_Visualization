"""The three spatial projections, aggregated in a single pass.

All three panels come out of **one scan** of the projection table, using
``GROUP BY GROUPING SETS``. DuckDB's hash aggregate keeps one hash table per
grouping set and distributes each input tuple into all of them as it streams,
so the 22.5-million-row table is read once rather than three times.

A shared CTE would not achieve this. DuckDB inlines non-recursive CTEs by
default, so a CTE referenced three times is planned as three independent scans.
Forcing ``MATERIALIZED`` would avoid that, but it writes the entire filtered
subset - up to ten million rows - into a buffer that spills to disk under a
modest memory ceiling. The grouping-sets form streams and never materialises the
selection at all.

The entrance-slab variant of the XY panel is computed in the same pass with
``FILTER (WHERE iz <= slab)`` rather than in a second query. The slab boundary
is a literal integer comparison against a stored layer index, which DuckDB's
zone maps can exploit, because the calorimeter front face is a fixed piece of
hardware at z = 3662.4 mm rather than a per-event minimum.

Everything is aggregated at the **native lattice resolution**. Resampling to the
requested display resolution happens afterwards in NumPy, from a cached bundle
(see ``cache.py`` and ``grid/splat.py``), which is what makes changing the
resolution or the display mode cost milliseconds instead of another scan.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..grid.lattice import Lattice
from .filters import FilterSpec

log = logging.getLogger(__name__)

#: ``GROUPING_ID(ix, iy, iz)`` sets a bit when the column is *absent* from the
#: current grouping set, with ``ix`` most significant.
GID_XY = 0b001  # grouped by (ix, iy); iz absent
GID_XZ = 0b010  # grouped by (ix, iz); iy absent
GID_YZ = 0b100  # grouped by (iy, iz); ix absent

#: Per-cell measurement planes returned by the query.
PLANES = ("e", "eg", "g", "n", "efa_true", "efa_pred")


@dataclass
class Panel:
    """One projection panel's native-resolution measurement planes."""

    name: str
    row_axis: str
    col_axis: str
    planes: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return next(iter(self.planes.values())).shape


@dataclass
class NativeBundle:
    """Native-resolution aggregates for all three panels of one selection.

    This is what the LRU caches. Roughly 41 000 cells across the three panels
    times six float64 planes is about 2 MB, so a 128-entry cache costs a few
    hundred megabytes and covers a long interactive session.
    """

    xy: Panel
    yz: Panel
    xz: Panel
    lattice: Lattice
    exact: bool
    query_ms: float
    n_hits: int

    def panel(self, name: str) -> Panel:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    @property
    def nbytes(self) -> int:
        return sum(
            plane.nbytes
            for panel in (self.xy, self.yz, self.xz)
            for plane in panel.planes.values()
        )


_QUERY = """
WITH sel AS (
    SELECT ix, iy, iz, energy, ge, fa_pred, fa_true,
           (iz <= {slab_iz}) AS slab
    FROM {table}
    WHERE {where}
)
SELECT
    GROUPING_ID(ix, iy, iz)                                   AS gid,
    ix, iy, iz,
    sum(energy)                                               AS e_all,
    sum(energy) FILTER (WHERE slab)                           AS e_slab,
    sum(energy * CAST(ge AS DOUBLE))                          AS eg_all,
    sum(energy * CAST(ge AS DOUBLE)) FILTER (WHERE slab)      AS eg_slab,
    sum(CAST(ge AS DOUBLE))                                   AS g_all,
    sum(CAST(ge AS DOUBLE)) FILTER (WHERE slab)               AS g_slab,
    count(*)                                                  AS n_all,
    count(*) FILTER (WHERE slab)                              AS n_slab,
    sum(energy * CAST(fa_true AS DOUBLE))                     AS efat_all,
    sum(energy * CAST(fa_true AS DOUBLE)) FILTER (WHERE slab) AS efat_slab,
    sum(energy * CAST(fa_pred AS DOUBLE))                     AS efap_all,
    sum(energy * CAST(fa_pred AS DOUBLE)) FILTER (WHERE slab) AS efap_slab
FROM sel
GROUP BY GROUPING SETS ((ix, iy), (iy, iz), (ix, iz))
"""


def build_sql(record: ExperimentRecord, spec: FilterSpec, sampled: bool) -> str:
    """Render the projection query for one experiment and selection."""
    assert record.lattice is not None
    return _QUERY.format(
        table=quote(naming.proj_table(record.table_name, sampled=sampled)),
        where=spec.where_sql(),
        slab_iz=record.lattice.slab_iz,
    )


def _empty(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {name: np.zeros(shape, dtype=np.float64) for name in PLANES}


def fetch_native(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    sampled: bool = False,
) -> NativeBundle:
    """Run the single-scan aggregation and assemble native-resolution matrices."""
    lattice = record.lattice
    assert lattice is not None

    sql = build_sql(record, spec, sampled)
    started = time.perf_counter()
    columns = con.execute(sql, spec.params()).fetchnumpy()
    query_ms = (time.perf_counter() - started) * 1000.0

    gid = np.asarray(columns["gid"], dtype=np.int64)

    xy = Panel("xy", "y", "x", _empty(lattice.shape_xy))
    yz = Panel("yz", "y", "z", _empty(lattice.shape_yz))
    xz = Panel("xz", "x", "z", _empty(lattice.shape_xz))

    def scatter(
        panel: Panel,
        mask: np.ndarray,
        rows: np.ndarray,
        cols: np.ndarray,
        suffix: str,
    ) -> None:
        """Place one grouping set's rows into a dense matrix.

        The query returns only non-empty combinations, so this is a scatter into
        a zero matrix rather than a reshape. Duplicate (row, col) pairs cannot
        occur within a grouping set, so direct assignment is correct and there
        is no need for ``np.add.at``.
        """
        if not mask.any():
            return
        r = rows[mask].astype(np.intp)
        c = cols[mask].astype(np.intp)
        source = {
            "e": f"e_{suffix}",
            "eg": f"eg_{suffix}",
            "g": f"g_{suffix}",
            "n": f"n_{suffix}",
            "efa_true": f"efat_{suffix}",
            "efa_pred": f"efap_{suffix}",
        }
        for plane, column in source.items():
            values = np.asarray(columns[column], dtype=np.float64)[mask]
            # FILTER aggregates yield NULL, not zero, for groups where no row
            # satisfied the filter; numpy renders those as NaN.
            np.nan_to_num(values, copy=False)
            panel.planes[plane][r, c] = values

    ix = np.asarray(columns["ix"], dtype=np.float64)
    iy = np.asarray(columns["iy"], dtype=np.float64)
    iz = np.asarray(columns["iz"], dtype=np.float64)
    ix = np.nan_to_num(ix).astype(np.int64)
    iy = np.nan_to_num(iy).astype(np.int64)
    iz = np.nan_to_num(iz).astype(np.int64)

    # The XY panel shows shower entry, so it uses the slab-restricted
    # aggregates; the depth panels use the full selection.
    scatter(xy, gid == GID_XY, iy, ix, "slab")
    scatter(yz, gid == GID_YZ, iy, iz, "all")
    scatter(xz, gid == GID_XZ, ix, iz, "all")

    n_hits = int(xz.planes["n"].sum())

    log.debug(
        "Projection scan for %s in %.1f ms (%s hits, sampled=%s)",
        record.table_name, query_ms, f"{n_hits:,}", sampled,
    )

    return NativeBundle(
        xy=xy, yz=yz, xz=xz,
        lattice=lattice,
        exact=not sampled,
        query_ms=query_ms,
        n_hits=n_hits,
    )


def explain(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    sampled: bool = False,
) -> str:
    """``EXPLAIN`` output for the projection query.

    Exposed so a test can assert that the plan contains exactly one sequential
    scan of the projection table. The single-scan property is a planner
    behaviour rather than a contract, and if a DuckDB upgrade changed it the
    symptom would otherwise be a silently tripled p95 latency.
    """
    sql = build_sql(record, spec, sampled)
    rows = con.execute("EXPLAIN " + sql, spec.params()).fetchall()
    return "\n".join(str(r[-1]) for r in rows)


def scale_sample(bundle: NativeBundle, percent: float) -> NativeBundle:
    """Scale a sampled bundle's extensive planes up to full-population estimates.

    Every plane except the ratios is a sum, and a Bernoulli sample is an
    unbiased estimator of a sum up to the known inclusion probability, so
    dividing by that probability recovers the expected full-population value.
    The result is explicitly marked inexact so the interface can say so.
    """
    factor = 100.0 / percent if percent > 0 else 1.0
    for panel in (bundle.xy, bundle.yz, bundle.xz):
        for plane in panel.planes.values():
            plane *= factor
    bundle.n_hits = int(bundle.n_hits * factor)
    return bundle
