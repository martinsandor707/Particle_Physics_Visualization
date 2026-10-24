"""The experiment catalogue endpoint's data.

Touches no hit data at all: every figure is cached in the registry at ingest
(or, for the archive, in its manifest), so this answers in about a millisecond
regardless of how many rows the experiments hold.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

import duckdb

from ..config import Settings
from ..db import archive, registry
from ..db.registry import ExperimentRecord
from . import capabilities as capabilities_mod

#: The reference frames of the interface, as (coord_system, frame) pairs the
#: API takes; the canonical frame is built from laboratory coordinates.
FRAME_KINDS = capabilities_mod.FRAME_KINDS


def _archive_info(settings: Settings | None, name: str) -> dict[str, Any]:
    manifest = archive.read_manifest(settings, name) if settings is not None else None
    if manifest is None:
        return {"present": False, "parts": 0, "rows": 0, "bytes": 0}
    return {"present": True, "parts": len(manifest.parts), "rows": manifest.rows,
            "bytes": manifest.bytes}


def describe(record: ExperimentRecord, settings: Settings | None = None) -> dict[str, Any]:
    """One experiment, as the frontend needs it.

    ``frames``, ``coord_systems``, ``models`` and ``channels`` are always
    present, empty when the experiment serves none, so the interface never
    falls back to a two-shower default for a dataset that cannot serve it; the
    ``capabilities`` block carries every per-card gate and its reason.
    """
    lattice = record.lattice
    caps = capabilities_mod.of(record)
    schema = record.schema
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
            "n_columns": schema.n_columns if schema is not None else None,
        },
        "archive": _archive_info(settings, record.table_name),
        "kind": caps.kind,
        # What the routes serve for this experiment. The per-shower frames
        # need the extents measured at ingest, the D-frame two showers, the
        # attention channels and the model cards the networks' outputs.
        "frames": list(caps.frames),
        "coord_systems": list(caps.coord_systems),
        "models": list(caps.models),
        "channels": list(caps.channels),
        "capabilities": caps.as_dict(),
    }

    if lattice is not None:
        payload["lattice"] = lattice.as_dict()
        payload["native_resolution"] = {
            "xy": list(lattice.shape_xy),
            "yz": list(lattice.shape_yz),
            "xz": list(lattice.shape_xz),
        }
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


def lattice_id(lattice: dict[str, Any]) -> str:
    """A content id of a lattice description: equal coordinates, equal id."""
    digest = hashlib.blake2b(digest_size=6)
    for axis in ("x", "y", "z"):
        coords = lattice[axis]["coords"]
        digest.update(struct.pack(f"<{len(coords)}d", *coords))
    digest.update(struct.pack("<dq", float(lattice["slab_mm"]), int(lattice["slab_iz"])))
    return digest.hexdigest()


def deduplicate_lattices(
    experiments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Move each experiment's lattice arrays into one shared map keyed by content.

    Every hit experiment on this detector carries the same 212 x 104 x 60
    lattice - 755 coordinates and edges, about 14 KB of JSON. Shipping it once
    keeps the catalogue under the 100 KB response contract however many
    experiments are registered. Each experiment keeps the axis summaries and
    names its lattice by ``lattice.id``.
    """
    shared: dict[str, dict[str, Any]] = {}
    out = []
    for experiment in experiments:
        lattice = experiment.get("lattice")
        if lattice is None:
            out.append(experiment)
            continue
        key = lattice_id(lattice)
        shared.setdefault(key, lattice)
        summary = {
            axis: {k: v for k, v in lattice[axis].items() if k not in ("coords", "edges")}
            for axis in ("x", "y", "z")
        }
        summary.update(id=key, slab_mm=lattice["slab_mm"], slab_iz=lattice["slab_iz"],
                       native_shapes=lattice["native_shapes"])
        out.append({**experiment, "lattice": summary})
    return out, shared
