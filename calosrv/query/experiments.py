"""The experiment catalogue endpoint's data.

Touches no hit data at all: every figure is cached in the registry at ingest
(or, for the archive, in its manifest), so this answers in about a millisecond
regardless of how many rows the experiments hold.
"""

from __future__ import annotations

from typing import Any

import duckdb

from ..config import Settings
from ..db import archive, ddl, registry
from ..db.registry import ExperimentRecord
from . import planes as planes_mod

#: The reference frames of the interface, as (coord_system, frame) pairs the
#: API takes; the canonical frame is built from laboratory coordinates.
FRAME_KINDS = ("lab", "trans", "local", "canonical")


def _archive_info(settings: Settings | None, name: str) -> dict[str, Any]:
    manifest = archive.read_manifest(settings, name) if settings is not None else None
    if manifest is None:
        return {"present": False, "parts": 0, "rows": 0, "bytes": 0}
    return {"present": True, "parts": len(manifest.parts), "rows": manifest.rows,
            "bytes": manifest.bytes}


def describe(record: ExperimentRecord, settings: Settings | None = None) -> dict[str, Any]:
    """One experiment, as the frontend needs it."""
    lattice = record.lattice
    payload: dict[str, Any] = {
        "table_name": record.table_name,
        "display_name": record.display_name or record.table_name,
        "status": record.status,
        "error": record.error,
        "source_files": record.source_files,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "n_hits": record.n_hits,
        "n_events": record.n_events,
        "n_events_no_d": record.n_events_no_d,
        "has_sample": record.has_sample,
        "overlap_classes": record.overlaps,
        "bounds": {
            "e1": [record.e1_min, record.e1_max],
            "e2": [record.e2_min, record.e2_max],
            "d": [record.d_min, record.d_max],
        },
        "schema": {
            "name": record.schema_name,
            "version": record.schema_version,
            "n_columns": len(ddl.HIT_COLUMN_NAMES) if record.schema_name == ddl.SCHEMA_NAME else None,
        },
        "archive": _archive_info(settings, record.table_name),
    }

    if lattice is not None:
        payload["lattice"] = lattice.as_dict()
        payload["native_resolution"] = {
            "xy": list(lattice.shape_xy),
            "yz": list(lattice.shape_yz),
            "xz": list(lattice.shape_xz),
        }
        # What the projections route serves for this experiment. The
        # per-shower frames need the extents measured at ingest; an experiment
        # without them offers the laboratory and canonical frames only.
        per_shower = record.frame_bounds is not None
        payload["frames"] = [
            kind for kind in FRAME_KINDS if per_shower or kind not in ("trans", "local")
        ]
        payload["coord_systems"] = [
            c for c in ddl.COORD_SYSTEMS if per_shower or c == "lab"
        ]
        payload["models"] = list(ddl.MODELS)
        payload["channels"] = list(planes_mod.CHANNELS)
        payload["z_front"] = lattice.z.lo

    if record.n_events_no_d:
        payload["notice"] = (
            f"{record.n_events_no_d:,} of {record.n_events:,} events have no "
            "defined A-B separation because shower A deposited no energy. They "
            "are excluded from every D-filtered view."
        )

    return payload


def list_all(
    con: duckdb.DuckDBPyConnection, include_pending: bool = True,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Every registered experiment.

    Experiments that are still ingesting or that failed are included by default
    so the interface can show their status rather than appearing to have lost
    them.
    """
    records = registry.list_experiments(con, ready_only=not include_pending)
    return [describe(r, settings) for r in records]
