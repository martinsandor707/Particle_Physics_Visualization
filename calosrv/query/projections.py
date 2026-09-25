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
from ..grid.lattice import Axis, Lattice
from . import planes as planes_mod
from .filters import FilterSpec

log = logging.getLogger(__name__)

#: ``GROUPING_ID(ix, iy, iz)`` sets a bit when the column is *absent* from the
#: current grouping set, with ``ix`` most significant.
GID_XY = 0b001  # grouped by (ix, iy); iz absent
GID_XZ = 0b010  # grouped by (ix, iz); iy absent
GID_YZ = 0b100  # grouped by (iy, iz); ix absent

#: Per-cell measurement planes returned by the query (see ``planes.py``).
PLANES = planes_mod.PLANES


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
    #: The network whose CAM planes the bundle holds (density ignores it).
    model: str = "segmentation"

    def panel(self, name: str) -> Panel:
        return {"xy": self.xy, "yz": self.yz, "xz": self.xz}[name]

    def axis(self, name: str) -> Axis:
        """The physical coordinate axis a panel's row or column index refers to.

        For the laboratory frame this is the detector lattice itself. The
        canonical-frame bundle answers the same call with its uniform grid, so
        ``centroids`` and ``panels.shower_axes`` need not know which frame they
        are measuring.
        """
        return self.lattice.axis(name)

    @property
    def nbytes(self) -> int:
        return sum(
            plane.nbytes
            for panel in (self.xy, self.yz, self.xz)
            for plane in panel.planes.values()
        )


def build_sql(
    record: ExperimentRecord, spec: FilterSpec, sampled: bool, model: str = "segmentation"
) -> str:
    """Render the projection query for one experiment, selection and network.

    One scan with ``GROUP BY GROUPING SETS ((ix, iy), (iy, iz), (ix, iz))``;
    every plane is summed over all rows and over the entrance slab
    (``FILTER (WHERE slab)``), which the XY panel reads.
    """
    assert record.lattice is not None
    aggregates = []
    for plane, expr in planes_mod.measures("lab", model):
        agg = "count(*)" if expr is None else f"sum({expr})"
        aggregates.append(f"{agg} AS {plane}_all")
        aggregates.append(f"{agg} FILTER (WHERE slab) AS {plane}_slab")
    return f"""
WITH sel AS (
    SELECT *, (iz <= {record.lattice.slab_iz}) AS slab
    FROM {quote(naming.proj_table(record.table_name, sampled=sampled))}
    WHERE {spec.where_sql()}
)
SELECT
    GROUPING_ID(ix, iy, iz) AS gid,
    ix, iy, iz,
    {(','+chr(10)+'    ').join(aggregates)}
FROM sel
GROUP BY GROUPING SETS ((ix, iy), (iy, iz), (ix, iz))
"""


def _empty(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {name: np.zeros(shape, dtype=np.float64) for name in PLANES}


def fetch_native(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    sampled: bool = False,
    model: str = "segmentation",
) -> NativeBundle:
    """Run the single-scan aggregation and assemble native-resolution matrices."""
    lattice = record.lattice
    assert lattice is not None

    sql = build_sql(record, spec, sampled, model)
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
        for plane in PLANES:
            values = np.asarray(columns[f"{plane}_{suffix}"], dtype=np.float64)[mask]
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
        model=model,
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
