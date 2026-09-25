"""Read and write the experiment registry.

The registry is the application's catalogue: which experiments exist, whether
they finished ingesting, how many rows and events they hold, their kinematic
bounds, the detector lattice measured at ingest, and - for the per-shower
frames - the energy-weighted extents grid planning starts from. Caching all of
that here is what lets ``GET /api/experiments`` answer without touching a
single hit row.

Rows are read and written by *column name*, generated from
:data:`calosrv.db.ddl.REGISTRY_SCHEMA`, never by position: a positional tuple
unpack is exactly the thing that breaks silently the day a column is added.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import duckdb

from ..errors import UnknownTableError
from ..grid.bounds import FrameBounds
from ..grid.lattice import Lattice, from_registry_row
from . import naming
from .ddl import CREATE_REGISTRY, REGISTRY_COLUMNS, REGISTRY_SCHEMA

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

    schema_name: str | None = None
    schema_version: int | None = None
    archive_dir: str | None = None
    archive_parts: int = 0
    archive_rows: int = 0
    archive_bytes: int = 0
    n_cells: int = 0
    n_split_cells: int = 0
    n_ab_rows: int = 0
    frame_bounds: FrameBounds | None = None
    ingest_report: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status == STATUS_READY


def ensure_registry(con: duckdb.DuckDBPyConnection) -> None:
    """Create the registry, and add any column an older database lacks.

    Columns are only ever appended to :data:`REGISTRY_SCHEMA`, so an existing
    database - one written before the per-shower frames existed - migrates by
    ``ALTER TABLE ... ADD COLUMN`` alone. The names come from that constant,
    never from input. Existing rows read the new columns as NULL, which the
    bootstrap then recognises as a retired schema.
    """
    con.execute(CREATE_REGISTRY)
    present = {
        row[0]
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'experiment'"
        ).fetchall()
    }
    for name, sql_type in REGISTRY_SCHEMA:
        if name in present:
            continue
        column_type = sql_type.replace("PRIMARY KEY", "").strip()
        log.info("Registry migration: adding column %s %s", name, column_type)
        con.execute(f'ALTER TABLE "experiment" ADD COLUMN "{name}" {column_type}')


def _row_to_record(row: tuple) -> ExperimentRecord:
    data = dict(zip(REGISTRY_COLUMNS, row))

    lattice = None
    if data["x_coords"] and data["y_coords"] and data["z_coords"]:
        lattice = from_registry_row(
            list(data["x_coords"]), list(data["y_coords"]), list(data["z_coords"]),
            slab_mm=data["slab_mm"], slab_iz=int(data["slab_iz"]),
        )

    report: dict[str, Any] = {}
    if data.get("ingest_report"):
        try:
            report = json.loads(data["ingest_report"])
        except (TypeError, ValueError):
            log.warning("Unreadable ingest_report for %r", data["table_name"])

    return ExperimentRecord(
        table_name=data["table_name"],
        display_name=data["display_name"] or data["table_name"],
        source_files=list(data["source_files"] or []),
        status=data["status"],
        error=data["error"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        n_hits=int(data["n_hits"] or 0),
        n_events=int(data["n_events"] or 0),
        n_events_no_d=int(data["n_events_no_d"] or 0),
        e1_min=data["e1_min"], e1_max=data["e1_max"],
        e2_min=data["e2_min"], e2_max=data["e2_max"],
        d_min=data["d_min"], d_max=data["d_max"],
        lattice=lattice,
        cell_e_max=data["cell_e_max"],
        cell_e_p999=data["cell_e_p999"],
        overlaps=[int(o) for o in (data["overlap_classes"] or [])],
        has_sample=bool(data["has_sample"]),
        schema_name=data["schema_name"],
        schema_version=int(data["schema_version"]) if data["schema_version"] is not None else None,
        archive_dir=data["archive_dir"],
        archive_parts=int(data["archive_parts"] or 0),
        archive_rows=int(data["archive_rows"] or 0),
        archive_bytes=int(data["archive_bytes"] or 0),
        n_cells=int(data["n_cells"] or 0),
        n_split_cells=int(data["n_split_cells"] or 0),
        n_ab_rows=int(data["n_ab_rows"] or 0),
        frame_bounds=FrameBounds.from_json(data["frame_bounds"]),
        ingest_report=report,
    )


_SELECT = "SELECT " + ", ".join(f'"{c}"' for c in REGISTRY_COLUMNS) + ' FROM "experiment"'


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


def _axis_values(lattice: Lattice | None, name: str) -> dict[str, Any]:
    """The registry columns of one lattice axis, or NULLs."""
    if lattice is None:
        return {f"{name}_lo": None, f"{name}_hi": None, f"n{name}": None,
                f"{name}_coords": None, f"pitch_{name}": None, f"{name}_uniform": None}
    axis = lattice.axis(name)
    return {
        f"{name}_lo": axis.lo, f"{name}_hi": axis.hi, f"n{name}": axis.n,
        f"{name}_coords": [float(v) for v in axis.coords],
        f"pitch_{name}": axis.mean_pitch, f"{name}_uniform": axis.is_uniform,
    }


def upsert(con: duckdb.DuckDBPyConnection, record: ExperimentRecord) -> None:
    """Insert or replace one registry row, by column name."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    lat = record.lattice
    values: dict[str, Any] = {
        "table_name": record.table_name,
        "display_name": record.display_name or record.table_name,
        "source_files": record.source_files,
        "status": record.status,
        "error": record.error,
        "created_at": record.created_at or now,
        "updated_at": now,
        "n_hits": record.n_hits,
        "n_events": record.n_events,
        "n_events_no_d": record.n_events_no_d,
        "e1_min": record.e1_min, "e1_max": record.e1_max,
        "e2_min": record.e2_min, "e2_max": record.e2_max,
        "d_min": record.d_min, "d_max": record.d_max,
        **_axis_values(lat, "x"),
        **_axis_values(lat, "y"),
        **_axis_values(lat, "z"),
        "slab_mm": lat.slab_mm if lat else None,
        "slab_iz": lat.slab_iz if lat else None,
        "cell_e_max": record.cell_e_max,
        "cell_e_p999": record.cell_e_p999,
        "overlap_classes": record.overlaps,
        "has_sample": record.has_sample,
        "schema_name": record.schema_name,
        "schema_version": record.schema_version,
        "archive_dir": record.archive_dir,
        "archive_parts": record.archive_parts,
        "archive_rows": record.archive_rows,
        "archive_bytes": record.archive_bytes,
        "n_cells": record.n_cells,
        "n_split_cells": record.n_split_cells,
        "n_ab_rows": record.n_ab_rows,
        "frame_bounds": record.frame_bounds.to_json() if record.frame_bounds else None,
        "ingest_report": json.dumps(record.ingest_report, sort_keys=True, default=str)
        if record.ingest_report else None,
    }
    missing = [c for c in REGISTRY_COLUMNS if c not in values]
    assert not missing, f"registry upsert does not set {missing}"
    columns = ", ".join(f'"{c}"' for c in REGISTRY_COLUMNS)
    placeholders = ", ".join("?" for _ in REGISTRY_COLUMNS)
    con.execute(
        f'INSERT OR REPLACE INTO "experiment" ({columns}) VALUES ({placeholders})',
        [values[c] for c in REGISTRY_COLUMNS],
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
