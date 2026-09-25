"""Build the projection table that every interactive query reads.

Three things happen here: laboratory coordinates become ordinal lattice
indices, the per-shower frames' coordinates are carried alongside them, and
unphysical rows are removed.

**Ordinal indexing.** Each laboratory coordinate is replaced by its rank among
the distinct values present in that column, resolved by an equi-join against a
dictionary built from the column itself. Float equality is safe because both
sides originate from the same stored values - no arithmetic is performed on
them. This is what makes the native laboratory view comb-free: an index exists
only if a cell exists.

**Per-shower frames.** ``x_trans``/``y_trans`` and the three local coordinates
are continuous - every shower is shifted by its own energy-weighted entry
point, and the local frame is rotated as well - so they are stored as REAL
millimetres, never as lattice ordinals. ``z_trans`` is always a whole number of
sampling layers counted from the shower's own first layer, so it is stored as
that layer index, ``kt``.

**Sanitisation.** CLAUDE.md section 3 requires unphysical values to be detected
and removed rather than propagated. A negative or non-finite deposited energy is
not a measurement, and a single one would poison a summed-energy cell and the
logarithmic colour scale derived from it. Every rejection is counted by rule and
reported, so a dataset that loses a suspicious number of rows is visible rather
than silently smaller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

import duckdb

from ..db import naming
from ..db.ddl import (
    COORD_SYSTEMS, NETWORK_FRAME, PROJ_COLUMN_NAMES, create_proj_table, csv_model_column,
    drop_table, raw_cam_columns, seg_column,
)
from ..db.naming import quote

log = logging.getLogger(__name__)

#: The per-shower frame coordinates a projected row must carry.
FRAME_COORDINATES = ("x_trans", "y_trans", "z_trans", "x_local", "y_local", "z_local")


@dataclass
class SanitationReport:
    """What was removed on the way from the archive to the projection table."""

    total_rows: int = 0
    kept_rows: int = 0
    null_coordinate: int = 0
    null_frame_coordinate: int = 0
    null_energy: int = 0
    non_finite_energy: int = 0
    negative_energy: int = 0
    zero_energy: int = 0
    bad_origin: int = 0

    @property
    def removed(self) -> int:
        return self.total_rows - self.kept_rows

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["removed"] = self.removed
        return data

    def log(self) -> None:
        if self.removed == 0:
            log.info("Sanitisation: all %s rows retained", f"{self.total_rows:,}")
            return
        log.warning(
            "Sanitisation removed %s of %s rows (%.4f%%): null coordinate %s, "
            "null or non-finite frame coordinate %s, null energy %s, non-finite "
            "energy %s, negative energy %s, zero energy %s, unknown origin %s",
            f"{self.removed:,}", f"{self.total_rows:,}",
            100.0 * self.removed / max(1, self.total_rows),
            f"{self.null_coordinate:,}", f"{self.null_frame_coordinate:,}",
            f"{self.null_energy:,}", f"{self.non_finite_energy:,}",
            f"{self.negative_energy:,}", f"{self.zero_energy:,}", f"{self.bad_origin:,}",
        )


def _frame_ok(p: str) -> str:
    return " AND ".join(
        f"{p}{c} IS NOT NULL AND isfinite({p}{c})" for c in FRAME_COORDINATES
    )


def keep_predicate(alias: str = "") -> str:
    """The rows worth projecting, optionally qualified by a table alias.

    Zero-energy hits are dropped alongside negative ones: they contribute
    nothing to any sum, but they do occupy a lattice cell, and an occupancy
    statistic that counts them overstates how much of the detector actually saw
    the shower. A row without finite per-shower coordinates, or with an origin
    other than A, B or 'A+B', cannot be placed in every frame and is dropped
    from all of them, so the frames always describe the same hits.
    """
    p = f"{alias}." if alias else ""
    return (
        f"{p}x IS NOT NULL AND {p}y IS NOT NULL AND {p}z IS NOT NULL "
        f"AND {p}energy IS NOT NULL AND isfinite({p}energy) AND {p}energy > 0 "
        f"AND {_frame_ok(p)} "
        f"AND {p}particle_origin IN ('A', 'B', 'A+B')"
    )


def audit(con: duckdb.DuckDBPyConnection, source: str) -> SanitationReport:
    """Count each rejection rule separately, before anything is removed."""
    frame_bad = " OR ".join(f"{c} IS NULL OR NOT isfinite({c})" for c in FRAME_COORDINATES)
    row = con.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE x IS NULL OR y IS NULL OR z IS NULL),
               count(*) FILTER (WHERE {frame_bad}),
               count(*) FILTER (WHERE energy IS NULL),
               count(*) FILTER (WHERE energy IS NOT NULL AND NOT isfinite(energy)),
               count(*) FILTER (WHERE energy IS NOT NULL AND isfinite(energy)
                                  AND energy < 0),
               count(*) FILTER (WHERE energy IS NOT NULL AND isfinite(energy)
                                  AND energy = 0),
               count(*) FILTER (WHERE particle_origin IS NULL
                                  OR particle_origin NOT IN ('A', 'B', 'A+B')),
               count(*) FILTER (WHERE {keep_predicate()})
        FROM {source}
        """
    ).fetchone()
    return SanitationReport(
        total_rows=int(row[0]),
        null_coordinate=int(row[1]),
        null_frame_coordinate=int(row[2]),
        null_energy=int(row[3]),
        non_finite_energy=int(row[4]),
        negative_energy=int(row[5]),
        zero_energy=int(row[6]),
        bad_origin=int(row[7]),
        kept_rows=int(row[8]),
    )


def _build_dictionaries(con: duckdb.DuckDBPyConnection, source: str) -> None:
    """Temporary coordinate dictionaries: distinct value to dense ordinal."""
    for column in ("x", "y", "z"):
        con.execute(f"DROP TABLE IF EXISTS lat_{column};")
        con.execute(
            f"""
            CREATE TEMP TABLE lat_{column} AS
            SELECT v, CAST(row_number() OVER (ORDER BY v) - 1 AS INTEGER) AS i
            FROM (
                SELECT DISTINCT {quote(column)} AS v
                FROM {source}
                WHERE {quote(column)} IS NOT NULL
            )
            """
        )


def projection_select(layer_pitch_mm: float) -> list[str]:
    """``expression AS column`` for every projection column, in table order."""
    expressions: dict[str, str] = {
        "event_number": "h.event_number",
        "ix": "CAST(lx.i AS USMALLINT)",
        "iy": "CAST(ly.i AS USMALLINT)",
        "iz": "CAST(lz.i AS UTINYINT)",
        "org": ("CAST(CASE h.particle_origin WHEN 'A' THEN 0 WHEN 'B' THEN 1 "
                "ELSE 2 END AS UTINYINT)"),
        "xt": "h.x_trans",
        "yt": "h.y_trans",
        "kt": f"CAST(round(h.z_trans / {float(layer_pitch_mm)!r}) AS UTINYINT)",
        "xl": "h.x_local",
        "yl": "h.y_local",
        "zl": "h.z_local",
        "energy": "h.energy",
        "e1": "h.incoming_momentum_A",
        "e2": "h.incoming_momentum_B",
        "d": "h.centroid_AB_distance",
        "ovl": "h.overlap",
    }
    for column, csv_name, *_ in raw_cam_columns():
        expressions[column] = f"h.{quote(csv_name)}"
    for kind in ("pred", "true"):
        for coord in COORD_SYSTEMS:
            csv_name = csv_model_column("segmentation", NETWORK_FRAME[coord], kind)
            expressions[seg_column(kind, coord)] = f"h.{quote(csv_name)}"
    missing = [c for c in PROJ_COLUMN_NAMES if c not in expressions]
    assert not missing, f"no source for projection columns {missing}"
    return [f"{expressions[c]} AS {c}" for c in PROJ_COLUMN_NAMES]


def build(
    con: duckdb.DuckDBPyConnection,
    name: str,
    source: str,
    layer_pitch_mm: float,
) -> SanitationReport:
    """Create ``proj_<name>`` from the archive relation ``source``."""
    proj_physical = naming.proj_table(name)

    report = audit(con, source)
    report.log()

    con.execute(drop_table(proj_physical))
    con.execute(create_proj_table(proj_physical))
    _build_dictionaries(con, source)

    log.info("Building %s (lattice ordinals + per-shower frames)", proj_physical)
    columns = ", ".join(PROJ_COLUMN_NAMES)
    select = ",\n               ".join(projection_select(layer_pitch_mm))
    con.execute(
        f"""
        INSERT INTO {quote(proj_physical)} ({columns})
        SELECT {select}
        FROM {source} h
        JOIN lat_x lx ON h.x = lx.v
        JOIN lat_y ly ON h.y = ly.v
        JOIN lat_z lz ON h.z = lz.v
        WHERE {keep_predicate("h")}
        """
    )

    for column in ("x", "y", "z"):
        con.execute(f"DROP TABLE IF EXISTS lat_{column};")

    inserted = int(
        con.execute(f"SELECT count(*) FROM {quote(proj_physical)}").fetchone()[0]
    )
    log.info("%s holds %s rows", proj_physical, f"{inserted:,}")

    if inserted != report.kept_rows:
        # The joins are inner, so a coordinate absent from its own dictionary
        # would silently drop a row. That cannot happen by construction, which
        # is exactly why a mismatch here must be loud.
        log.error(
            "Projection row count %s does not match the %s rows that passed "
            "sanitisation; a lattice join dropped rows unexpectedly.",
            f"{inserted:,}", f"{report.kept_rows:,}",
        )
    report.kept_rows = inserted
    return report


def measure_color_anchors(
    con: duckdb.DuckDBPyConnection, name: str, slab_iz: int
) -> tuple[float, float]:
    """Global colour-scale anchors: the brightest cell over the whole dataset.

    Computed once at ingest so the interactive colour ramp can be *locked* to
    the full dataset rather than rescaled to whatever the sliders currently
    select. Without a lock, a selection carrying a tenth of the energy renders
    identically to the full dataset, and a reader will reasonably conclude that
    nothing changed.

    The maximum is taken across all three panel binnings, since they are
    displayed together and a shared anchor keeps them comparable. The 99.9th
    percentile is stored alongside it as a less outlier-sensitive alternative.
    """
    proj = quote(naming.proj_table(name))
    row = con.execute(
        f"""
        WITH cells AS (
            SELECT sum(energy) AS s FROM {proj}
            WHERE iz <= {int(slab_iz)} GROUP BY ix, iy
            UNION ALL
            SELECT sum(energy) AS s FROM {proj} GROUP BY iy, iz
            UNION ALL
            SELECT sum(energy) AS s FROM {proj} GROUP BY ix, iz
        )
        SELECT max(s), quantile_cont(s, 0.999) FROM cells WHERE s > 0
        """
    ).fetchone()
    cell_max = float(row[0]) if row and row[0] is not None else 0.0
    cell_p999 = float(row[1]) if row and row[1] is not None else cell_max
    log.info(
        "Colour anchors: brightest cell %.6e GeV, p99.9 %.6e GeV",
        cell_max, cell_p999,
    )
    return cell_max, cell_p999


def build_sample(
    con: duckdb.DuckDBPyConnection, name: str, percent: float = 10.0
) -> int:
    """Build the Bernoulli-sampled companion used for drag preview.

    Every aggregate the projection endpoint computes is a sum, and a Bernoulli
    sample is an unbiased estimator of a sum up to a known scale factor, so the
    preview is a genuine statistical estimate rather than a crop. The relative
    error on a cell holding ``k`` hits is about ``1/sqrt(0.1 * k)``, which is a
    fraction of a percent in the bright cells that carry the structure and
    invisible against 8-bit quantisation elsewhere.

    A fixed seed makes the preview reproducible, so the image does not flicker
    between two runs of the same query.
    """
    source = naming.proj_table(name)
    target = naming.proj_table(name, sampled=True)
    con.execute(drop_table(target))
    con.execute(
        f"CREATE TABLE {quote(target)} AS SELECT * FROM {quote(source)} "
        f"USING SAMPLE {percent} PERCENT (bernoulli, 42)"
    )
    rows = int(con.execute(f"SELECT count(*) FROM {quote(target)}").fetchone()[0])
    log.info("%s holds %s rows (%.0f%% sample)", target, f"{rows:,}", percent)
    return rows
