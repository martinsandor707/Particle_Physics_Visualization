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

from ..db import naming
from ..db.naming import quote
from ..errors import IngestError
from ..grid.bounds import FRAME_AXES, QUANTILE_LEVELS, AxisBounds, FrameBounds, quantile_key
from ..grid.lattice import Axis, Lattice
from ..grid.slab import DEFAULT_SLAB_MM, slab_layer_count

log = logging.getLogger(__name__)

#: Refuse to build a lattice axis with more distinct values than this. A
#: continuous-valued coordinate column would otherwise produce millions of
#: "cells" and a projection table that cannot be indexed with a small integer.
MAX_AXIS_CELLS = 4096


def _distinct_axis(
    con: duckdb.DuckDBPyConnection, source: str, column: str
) -> Axis:
    rows = con.execute(
        f"SELECT DISTINCT {quote(column)} AS v FROM {source} "
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
    source: str,
    slab_mm: float = DEFAULT_SLAB_MM,
) -> Lattice:
    """Measure the laboratory x, y and z lattices and the entrance-slab depth.

    ``source`` is a relation - the archive's ``read_parquet(...)`` - rather than
    a table name. Only the laboratory coordinates form a lattice; the per-shower
    frames are continuous and are described by :func:`measure_frame_bounds`.
    """
    x = _distinct_axis(con, source, "x")
    y = _distinct_axis(con, source, "y")
    z = _distinct_axis(con, source, "z")

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


def layer_pitch(z_coords: np.ndarray) -> float:
    """The sampling-layer pitch: the smallest gap between populated layers.

    Not the mean spacing: a selection or a small file that misses a layer
    (the 2-event demonstration file populates 56 of 60) has a mean spacing
    above the true pitch, while its smallest gap is still one layer.
    """
    coords = np.unique(np.asarray(z_coords, dtype=np.float64))
    if coords.size < 2:
        raise IngestError("Cannot measure a layer pitch from fewer than two layers.")
    return float(round(float(np.min(np.diff(coords))), 4))


def measure_bounds(con: duckdb.DuckDBPyConnection, name: str) -> dict:
    """Kinematic bounds and the overlap classes present, from the event table.

    The E1/E2/D bounds are taken over *events*, not hit rows. A hit-weighted
    minimum would be identical, but a hit-weighted mean would not, and reading
    the per-event table keeps the rule "per-event quantities are aggregated per
    event" visible rather than implicit.
    """
    event = quote(naming.event_table(name))
    row = con.execute(
        f"""
        SELECT min(e1), max(e1), min(e2), max(e2),
               min(d),  max(d),
               count(*),
               count(*) FILTER (WHERE d IS NULL)
        FROM {event}
        """
    ).fetchone()

    overlaps = [
        int(r[0])
        for r in con.execute(
            f"SELECT DISTINCT ovl FROM {event} WHERE ovl IS NOT NULL ORDER BY ovl"
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


def measure_frame_bounds(
    con: duckdb.DuckDBPyConnection, name: str, layer_pitch_mm: float
) -> FrameBounds:
    """Extent and energy-weighted quantiles of every per-shower coordinate.

    Measured from 1 mm histograms of each coordinate on the projection table
    (one grouped scan per axis) and cumulated in NumPy, so the quantiles are
    exact to the millimetre without sorting 24 million values. Grid planning
    for the translated and local frames starts from these.
    """
    proj = quote(naming.proj_table(name))
    axes: dict[str, AxisBounds] = {}
    for column in FRAME_AXES:
        rows = con.execute(
            f"SELECT floor({column}) AS b, sum(energy) AS e FROM {proj} "
            "GROUP BY b ORDER BY b"
        ).fetchnumpy()
        bins = np.asarray(rows["b"], dtype=np.float64)
        weights = np.asarray(rows["e"], dtype=np.float64)
        lo, hi = con.execute(f"SELECT min({column}), max({column}) FROM {proj}").fetchone()
        quantiles: dict[str, float] = {}
        if weights.size and weights.sum() > 0:
            cumulative = np.cumsum(weights) / weights.sum()
            for level in QUANTILE_LEVELS:
                index = int(np.searchsorted(cumulative, level, side="left"))
                index = min(index, bins.size - 1)
                # The upper edge of the millimetre bin that crosses the level.
                quantiles[quantile_key(level)] = float(bins[index] + 1.0)
        axes[column] = AxisBounds(
            column, float(lo if lo is not None else 0.0), float(hi if hi is not None else 0.0),
            quantiles,
        )
        log.info(
            "Frame bounds %s: %.0f..%.0f mm, energy-weighted 0.1-99.9%% %.0f..%.0f mm",
            column, axes[column].lo, axes[column].hi,
            quantiles.get(quantile_key(1e-3), float("nan")),
            quantiles.get(quantile_key(0.999), float("nan")),
        )
    n_layers = int(con.execute(f"SELECT coalesce(max(kt), 0) + 1 FROM {proj}").fetchone()[0])
    return FrameBounds(axes=axes, n_layers_trans=n_layers, layer_pitch_mm=float(layer_pitch_mm))
