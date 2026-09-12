"""Build the narrow projection table that every interactive query reads.

Two things happen here: coordinates become ordinal lattice indices, and
unphysical rows are removed.

**Ordinal indexing.** Each coordinate is replaced by its rank among the distinct
values present in that column, resolved by an equi-join against a dictionary
built from the column itself. Float equality is safe because both sides
originate from the same stored values - no arithmetic is performed on them.
This is what makes the native view comb-free: an index exists only if a cell
exists.

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
from ..db.ddl import create_proj_table, drop_table
from ..db.naming import quote
from ..grid.lattice import Lattice

log = logging.getLogger(__name__)


@dataclass
class SanitationReport:
    """What was removed on the way from the hit table to the projection table."""

    total_rows: int = 0
    kept_rows: int = 0
    null_coordinate: int = 0
    null_energy: int = 0
    non_finite_energy: int = 0
    negative_energy: int = 0
    zero_energy: int = 0

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
            "Sanitisation removed %s of %s rows (%.4f%%): "
            "null coordinate %s, null energy %s, non-finite energy %s, "
            "negative energy %s, zero energy %s",
            f"{self.removed:,}", f"{self.total_rows:,}",
            100.0 * self.removed / max(1, self.total_rows),
            f"{self.null_coordinate:,}", f"{self.null_energy:,}",
            f"{self.non_finite_energy:,}", f"{self.negative_energy:,}",
            f"{self.zero_energy:,}",
        )


def keep_predicate(alias: str = "") -> str:
    """The rows worth projecting, optionally qualified by a table alias.

    Zero-energy hits are dropped alongside negative ones: they contribute
    nothing to any sum, but they do occupy a lattice cell, and an occupancy
    statistic that counts them overstates how much of the detector actually saw
    the shower.
    """
    p = f"{alias}." if alias else ""
    return (
        f"{p}x IS NOT NULL AND {p}y IS NOT NULL AND {p}z IS NOT NULL "
        f"AND {p}energy IS NOT NULL AND isfinite({p}energy) AND {p}energy > 0"
    )


def audit(con: duckdb.DuckDBPyConnection, hit_physical: str) -> SanitationReport:
    """Count each rejection rule separately, before anything is removed."""
    row = con.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE x IS NULL OR y IS NULL OR z IS NULL),
               count(*) FILTER (WHERE energy IS NULL),
               count(*) FILTER (WHERE energy IS NOT NULL AND NOT isfinite(energy)),
               count(*) FILTER (WHERE energy IS NOT NULL AND isfinite(energy)
                                  AND energy < 0),
               count(*) FILTER (WHERE energy IS NOT NULL AND isfinite(energy)
                                  AND energy = 0),
               count(*) FILTER (WHERE {keep_predicate()})
        FROM {quote(hit_physical)}
        """
    ).fetchone()
    return SanitationReport(
        total_rows=int(row[0]),
        null_coordinate=int(row[1]),
        null_energy=int(row[2]),
        non_finite_energy=int(row[3]),
        negative_energy=int(row[4]),
        zero_energy=int(row[5]),
        kept_rows=int(row[6]),
    )


def _build_dictionaries(
    con: duckdb.DuckDBPyConnection, hit_physical: str
) -> None:
    """Temporary coordinate dictionaries: distinct value to dense ordinal."""
    for column in ("x", "y", "z"):
        con.execute(f"DROP TABLE IF EXISTS lat_{column};")
        con.execute(
            f"""
            CREATE TEMP TABLE lat_{column} AS
            SELECT v, CAST(row_number() OVER (ORDER BY v) - 1 AS INTEGER) AS i
            FROM (
                SELECT DISTINCT {quote(column)} AS v
                FROM {quote(hit_physical)}
                WHERE {quote(column)} IS NOT NULL
            )
            """
        )


def build(
    con: duckdb.DuckDBPyConnection,
    name: str,
    lattice: Lattice,
) -> SanitationReport:
    """Create ``proj_<name>`` from ``hit_<name>``."""
    hit_physical = naming.hit_table(name)
    proj_physical = naming.proj_table(name)

    report = audit(con, hit_physical)
    report.log()

    con.execute(drop_table(proj_physical))
    con.execute(create_proj_table(proj_physical))
    _build_dictionaries(con, hit_physical)

    log.info("Building %s (ordinal lattice indices)", proj_physical)
    con.execute(
        f"""
        INSERT INTO {quote(proj_physical)}
        SELECT h.event_number,
               CAST(lx.i AS USMALLINT) AS ix,
               CAST(ly.i AS USMALLINT) AS iy,
               CAST(lz.i AS UTINYINT)  AS iz,
               h.energy,
               h.gradcam_energy       AS ge,
               h.voxel_fA_pred        AS fa_pred,
               h.voxel_fA_true        AS fa_true,
               h.incoming_momentum_A  AS e1,
               h.incoming_momentum_B  AS e2,
               h.centroid_AB_distance AS d,
               h.overlap              AS ovl
        FROM {quote(hit_physical)} h
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
