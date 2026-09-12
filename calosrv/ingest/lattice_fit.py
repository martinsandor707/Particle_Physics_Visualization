"""Measure the detector lattice and dataset bounds from loaded hit data.

Everything here is *measured*, never assumed. The lattice is a property of the
hardware that produced the file, and a second dataset from a different detector
configuration must produce a different lattice without a code change.

The measurement is frozen into the registry and reused for the lifetime of the
table. Re-measuring per request would be both wasteful and wrong: a filter that
happens to exclude the outermost hit would shift every bin edge by a fraction of
a cell, and the heatmaps would shimmer as the sliders moved.
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np

from ..db.naming import quote
from ..errors import IngestError
from ..grid.lattice import Axis, Lattice
from ..grid.slab import DEFAULT_SLAB_MM, slab_layer_count

log = logging.getLogger(__name__)

#: Refuse to build a lattice axis with more distinct values than this. A
#: continuous-valued coordinate column would otherwise produce millions of
#: "cells" and a projection table that cannot be indexed with a small integer.
MAX_AXIS_CELLS = 4096


def _distinct_axis(
    con: duckdb.DuckDBPyConnection, physical: str, column: str
) -> Axis:
    rows = con.execute(
        f"SELECT DISTINCT {quote(column)} AS v FROM {quote(physical)} "
        f"WHERE {quote(column)} IS NOT NULL ORDER BY v"
    ).fetchall()
    if not rows:
        raise IngestError(f"Column {column!r} holds no usable values.")
    if len(rows) > MAX_AXIS_CELLS:
        raise IngestError(
            f"Column {column!r} has {len(rows):,} distinct values, above the "
            f"{MAX_AXIS_CELLS:,} supported. This does not look like a sampled "
            "detector lattice.",
            column=column,
            distinct=len(rows),
        )
    return Axis(column, np.array([float(r[0]) for r in rows], dtype=np.float64))


def measure_lattice(
    con: duckdb.DuckDBPyConnection,
    physical: str,
    slab_mm: float = DEFAULT_SLAB_MM,
) -> Lattice:
    """Measure the x, y and z lattices and the entrance-slab depth."""
    x = _distinct_axis(con, physical, "x")
    y = _distinct_axis(con, physical, "y")
    z = _distinct_axis(con, physical, "z")

    slab_iz = slab_layer_count(z.coords, slab_mm)

    log.info(
        "Lattice measured: x=%d cells (pitch %.2f mm, %s) "
        "y=%d cells (pitch %.2f mm, %s) z=%d layers (pitch %.2f mm, %s)",
        x.n, x.mean_pitch, "uniform" if x.is_uniform else "IRREGULAR",
        y.n, y.mean_pitch, "uniform" if y.is_uniform else "IRREGULAR",
        z.n, z.mean_pitch, "uniform" if z.is_uniform else "IRREGULAR",
    )
    if not x.is_uniform or not y.is_uniform:
        log.info(
            "Transverse lattice is irregular; bin indices are ordinals over the "
            "measured cell coordinates and physical placement uses the stored "
            "coordinate arrays."
        )
    log.info(
        "Entrance slab: %.0f mm from the front face at z=%.1f mm -> layers 0-%d",
        slab_mm, z.lo, slab_iz,
    )
    return Lattice(x=x, y=y, z=z, slab_mm=slab_mm, slab_iz=slab_iz)


def measure_bounds(con: duckdb.DuckDBPyConnection, physical: str) -> dict:
    """Kinematic bounds and the overlap classes present.

    The E1/E2/D bounds are taken over *events*, not hit rows. A hit-weighted
    minimum would be identical, but a hit-weighted mean would not, and taking
    all of them from the same event-level subquery keeps the rule "per-event
    quantities are aggregated per event" visible rather than implicit.
    """
    row = con.execute(
        f"""
        WITH ev AS (
            SELECT event_number,
                   max(incoming_momentum_A)  AS e1,
                   max(incoming_momentum_B)  AS e2,
                   max(centroid_AB_distance) AS d
            FROM {quote(physical)}
            GROUP BY event_number
        )
        SELECT min(e1), max(e1), min(e2), max(e2),
               min(d),  max(d),
               count(*),
               count(*) FILTER (WHERE d IS NULL)
        FROM ev
        """
    ).fetchone()

    overlaps = [
        int(r[0])
        for r in con.execute(
            f"SELECT DISTINCT overlap FROM {quote(physical)} "
            "WHERE overlap IS NOT NULL ORDER BY overlap"
        ).fetchall()
    ]

    bounds = {
        "e1_min": row[0], "e1_max": row[1],
        "e2_min": row[2], "e2_max": row[3],
        "d_min": row[4], "d_max": row[5],
        "n_events": int(row[6] or 0),
        "n_events_no_d": int(row[7] or 0),
        "overlaps": overlaps,
    }

    if bounds["n_events_no_d"]:
        log.warning(
            "%d of %d events have an undefined A-B separation (shower A "
            "deposited no energy). They are excluded from D-filtered views and "
            "reported as n_events_no_d.",
            bounds["n_events_no_d"], bounds["n_events"],
        )
    log.info(
        "Bounds: E1 %.3f-%.3f GeV, E2 %.3f-%.3f GeV, D %.1f-%.1f mm, "
        "%d events, overlap classes %s",
        bounds["e1_min"] or 0, bounds["e1_max"] or 0,
        bounds["e2_min"] or 0, bounds["e2_max"] or 0,
        bounds["d_min"] or 0, bounds["d_max"] or 0,
        bounds["n_events"], overlaps,
    )
    return bounds
