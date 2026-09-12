"""The experiment catalogue endpoint's data.

Touches no hit data at all: every figure is cached in the registry at ingest, so
this answers in about a millisecond regardless of how many billions of rows the
experiments hold.
"""

from __future__ import annotations

from typing import Any

import duckdb

from ..db import registry
from ..db.registry import ExperimentRecord


def describe(record: ExperimentRecord) -> dict[str, Any]:
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
    }

    if lattice is not None:
        payload["lattice"] = lattice.as_dict()
        payload["native_resolution"] = {
            "xy": list(lattice.shape_xy),
            "yz": list(lattice.shape_yz),
            "xz": list(lattice.shape_xz),
        }

    if record.n_events_no_d:
        payload["notice"] = (
            f"{record.n_events_no_d:,} of {record.n_events:,} events have no "
            "defined A-B separation because shower A deposited no energy. They "
            "are excluded from every D-filtered view."
        )

    return payload


def list_all(
    con: duckdb.DuckDBPyConnection, include_pending: bool = True
) -> list[dict[str, Any]]:
    """Every registered experiment.

    Experiments that are still ingesting or that failed are included by default
    so the interface can show their status rather than appearing to have lost
    them.
    """
    records = registry.list_experiments(con, ready_only=not include_pending)
    return [describe(r) for r in records]
