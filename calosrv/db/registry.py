"""Read and write the experiment registry.

The registry is the application's catalogue: which experiments exist, whether
they finished ingesting, how many rows and events they hold, their kinematic
bounds, and the detector lattice measured at ingest. Caching all of that here is
what lets ``GET /api/experiments`` answer without touching a single hit row.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import duckdb

from ..errors import UnknownTableError
from ..grid.lattice import Lattice, from_registry_row
from . import naming
from .ddl import CREATE_REGISTRY

log = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_INGESTING = "ingesting"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


@dataclass
class ExperimentRecord:
    """One row of the registry."""

    table_name: str
    display_name: str = ""
    source_files: list[str] = field(default_factory=list)
    status: str = STATUS_PENDING
    error: str | None = None
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None

    n_hits: int = 0
    n_events: int = 0
    n_events_no_d: int = 0

    e1_min: float | None = None
    e1_max: float | None = None
    e2_min: float | None = None
    e2_max: float | None = None
    d_min: float | None = None
    d_max: float | None = None

    lattice: Lattice | None = None

    cell_e_max: float | None = None
    cell_e_p999: float | None = None
    overlaps: list[int] = field(default_factory=list)
    has_sample: bool = False

    @property
    def is_ready(self) -> bool:
        return self.status == STATUS_READY


def ensure_registry(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(CREATE_REGISTRY)


def _row_to_record(row: tuple) -> ExperimentRecord:
    (
        table_name, display_name, source_files, status, error,
        created_at, updated_at,
        n_hits, n_events, n_events_no_d,
        e1_min, e1_max, e2_min, e2_max, d_min, d_max,
        x_lo, x_hi, nx, x_coords,
        y_lo, y_hi, ny, y_coords,
        z_lo, z_hi, nz, z_coords,
        pitch_x, pitch_y, pitch_z,
        x_uniform, y_uniform, z_uniform,
        slab_mm, slab_iz,
        cell_e_max, cell_e_p999, overlap_classes, has_sample,
    ) = row

    lattice = None
    if x_coords and y_coords and z_coords:
        lattice = from_registry_row(
            list(x_coords), list(y_coords), list(z_coords),
            slab_mm=slab_mm, slab_iz=int(slab_iz),
        )

    return ExperimentRecord(
        table_name=table_name,
        display_name=display_name or table_name,
        source_files=list(source_files or []),
        status=status,
        error=error,
        created_at=created_at,
        updated_at=updated_at,
        n_hits=int(n_hits or 0),
        n_events=int(n_events or 0),
        n_events_no_d=int(n_events_no_d or 0),
        e1_min=e1_min, e1_max=e1_max,
        e2_min=e2_min, e2_max=e2_max,
        d_min=d_min, d_max=d_max,
        lattice=lattice,
        cell_e_max=cell_e_max,
        cell_e_p999=cell_e_p999,
        overlaps=[int(o) for o in (overlap_classes or [])],
        has_sample=bool(has_sample),
    )


_SELECT = """
SELECT table_name, display_name, source_files, status, error,
       created_at, updated_at,
       n_hits, n_events, n_events_no_d,
       e1_min, e1_max, e2_min, e2_max, d_min, d_max,
       x_lo, x_hi, nx, x_coords,
       y_lo, y_hi, ny, y_coords,
       z_lo, z_hi, nz, z_coords,
       pitch_x, pitch_y, pitch_z,
       x_uniform, y_uniform, z_uniform,
       slab_mm, slab_iz,
       cell_e_max, cell_e_p999, overlap_classes, has_sample
FROM "experiment"
"""


def list_experiments(
    con: duckdb.DuckDBPyConnection, ready_only: bool = False
) -> list[ExperimentRecord]:
    sql = _SELECT
    if ready_only:
        sql += f" WHERE status = '{STATUS_READY}'"
    sql += " ORDER BY created_at NULLS LAST, table_name"
    return [_row_to_record(row) for row in con.execute(sql).fetchall()]


def get_experiment(
    con: duckdb.DuckDBPyConnection, name: str
) -> ExperimentRecord | None:
    name = naming.validate_experiment_name(name)
    row = con.execute(_SELECT + " WHERE table_name = ?", [name]).fetchone()
    return _row_to_record(row) if row else None


def require_ready(con: duckdb.DuckDBPyConnection, name: str) -> ExperimentRecord:
    """Fetch an experiment, or raise with a message naming what is available.

    This is the function every query endpoint goes through, so a request for a
    table that is still ingesting gets told so rather than failing later with a
    missing-table error from deep inside a query.
    """
    record = get_experiment(con, name)
    if record is None:
        available = [r.table_name for r in list_experiments(con, ready_only=True)]
        raise UnknownTableError(
            f"No experiment named {name!r}.",
            available=available,
        )
    if not record.is_ready:
        raise UnknownTableError(
            f"Experiment {name!r} is not queryable (status: {record.status}).",
            status=record.status,
            error=record.error,
        )
    return record


def upsert(con: duckdb.DuckDBPyConnection, record: ExperimentRecord) -> None:
    """Insert or replace one registry row."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    lat = record.lattice

    def axis_values(name: str) -> list:
        """``(lo, hi, n, coords, mean_pitch, uniform)`` for one axis, or NULLs."""
        if lat is None:
            return [None, None, None, None, None, None]
        axis = lat.axis(name)
        return [
            axis.lo, axis.hi, axis.n,
            [float(v) for v in axis.coords],
            axis.mean_pitch, axis.is_uniform,
        ]

    x_lo, x_hi, nx, x_coords, pitch_x, x_uniform = axis_values("x")
    y_lo, y_hi, ny, y_coords, pitch_y, y_uniform = axis_values("y")
    z_lo, z_hi, nz, z_coords, pitch_z, z_uniform = axis_values("z")

    con.execute(
        """
        INSERT OR REPLACE INTO "experiment" VALUES (
            ?, ?, ?, ?, ?,
            COALESCE(?, ?), ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?
        )
        """,
        [
            record.table_name, record.display_name or record.table_name,
            record.source_files, record.status, record.error,
            record.created_at, now, now,
            record.n_hits, record.n_events, record.n_events_no_d,
            record.e1_min, record.e1_max, record.e2_min, record.e2_max,
            record.d_min, record.d_max,
            x_lo, x_hi, nx, x_coords,
            y_lo, y_hi, ny, y_coords,
            z_lo, z_hi, nz, z_coords,
            pitch_x, pitch_y, pitch_z,
            x_uniform, y_uniform, z_uniform,
            lat.slab_mm if lat else None, lat.slab_iz if lat else None,
            record.cell_e_max, record.cell_e_p999,
            record.overlaps, record.has_sample,
        ],
    )


def set_status(
    con: duckdb.DuckDBPyConnection,
    name: str,
    status: str,
    error: str | None = None,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    con.execute(
        'UPDATE "experiment" SET status = ?, error = ?, updated_at = ? '
        "WHERE table_name = ?",
        [status, error, now, name],
    )


def delete(con: duckdb.DuckDBPyConnection, name: str) -> None:
    con.execute('DELETE FROM "experiment" WHERE table_name = ?', [name])
