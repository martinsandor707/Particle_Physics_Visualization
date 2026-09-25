"""Load a validated CSV into the experiment's Parquet archive."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from ..config import Settings
from ..db import archive, naming
from ..db.ddl import HIT_COLUMN_NAMES, SCHEMA_NAME, SCHEMA_VERSION, drop_table
from ..db.naming import quote
from ..errors import EventRangeCollisionError, IngestError
from . import csv_spec

log = logging.getLogger(__name__)

MODE_CREATE_NEW = "create_new"
MODE_APPEND = "append"
VALID_MODES = (MODE_CREATE_NEW, MODE_APPEND)


@dataclass
class LoadResult:
    """What one load committed to the archive."""

    rows: int
    part: Path
    event_range: tuple[int, int] | None
    manifest: archive.Manifest


def check_append_collision(
    existing: tuple[int, int] | None,
    incoming: tuple[int, int] | None,
) -> None:
    """Reject an append whose event numbers overlap what is already there.

    Ported from ``calodash/ingest.py``, which enforces the same rule in the
    batch pipeline. Two files that each number their events from zero are the
    normal case, not an exotic one, and merging them fuses distinct physics
    events into one: every per-event aggregate downstream - reconstructed
    energy, hit multiplicity, the centroids - would then describe a chimera.

    The caller can override by supplying an explicit ``event_offset``, which
    shifts the incoming numbers clear of the existing range.
    """
    if incoming is None or existing is None:
        return
    lo_a, hi_a = existing
    lo_b, hi_b = incoming
    if lo_b <= hi_a and lo_a <= hi_b:
        raise EventRangeCollisionError(
            f"The incoming file covers event numbers {lo_b}-{hi_b}, which "
            f"overlaps the {lo_a}-{hi_a} already in this experiment. Appending "
            "would merge distinct events. Supply an event_offset of at least "
            f"{hi_a - lo_b + 1} to shift the incoming events clear, or upload "
            "into a new table instead.",
            existing_range=[lo_a, hi_a],
            incoming_range=[lo_b, hi_b],
            suggested_offset=hi_a - lo_b + 1,
        )


def _select_sql(path: Path, event_offset: int) -> str:
    """Every column in file order, typed by the pinned reader."""
    if event_offset:
        projected = ", ".join(
            f"event_number + {int(event_offset)} AS event_number" if c == "event_number"
            else quote(c)
            for c in HIT_COLUMN_NAMES
        )
    else:
        projected = ", ".join(quote(c) for c in HIT_COLUMN_NAMES)
    return f"SELECT {projected} FROM {csv_spec.read_csv_expression(path)}"


def load_csv(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    path: Path,
    mode: str = MODE_CREATE_NEW,
    event_offset: int = 0,
    source_name: str | None = None,
) -> LoadResult:
    """Validate ``path`` and commit it to the archive as one new Parquet part.

    ``create_new`` drops the experiment's derived tables - including a legacy
    ``hit_<name>`` table from the retired v37 schema - and its archive first.
    ``append`` adds a part after checking the event ranges do not collide.

    The CSV is parsed exactly once, straight into the part; the event range is
    then read from the part's statistics, not from a second pass over the CSV.
    """
    if mode not in VALID_MODES:
        raise IngestError(
            f"Unknown upload mode {mode!r}; expected one of {', '.join(VALID_MODES)}."
        )
    csv_spec.validate_header(path)
    root = archive.archive_path(settings, name)

    if mode == MODE_CREATE_NEW:
        for table in naming.all_tables(name):
            con.execute(drop_table(table))
        archive.remove(settings, name)
        manifest = archive.Manifest(SCHEMA_NAME, SCHEMA_VERSION)
    else:
        manifest = archive.read_manifest(settings, name)
        if manifest is None or not manifest.parts:
            raise IngestError(
                f"Cannot append to experiment {name!r}: its archive is missing. "
                "Re-ingest it with create_new first."
            )
        if (manifest.schema_name, manifest.schema_version) != (SCHEMA_NAME, SCHEMA_VERSION):
            raise IngestError(
                f"Cannot append to experiment {name!r}: its archive holds the "
                f"{manifest.schema_name} v{manifest.schema_version} schema."
            )

    root.mkdir(parents=True, exist_ok=True)
    part = archive.next_part_path(settings, name)
    tmp = part.with_name(part.name + archive.TMP_SUFFIX)
    log.info("Archiving %s into %s (mode=%s)", path.name, part, mode)
    try:
        written = con.execute(
            archive.copy_to_part_sql(_select_sql(path, event_offset), tmp)
        ).fetchone()
    except duckdb.Error as exc:
        tmp.unlink(missing_ok=True)
        raise IngestError(f"DuckDB rejected {path.name}: {exc}") from exc
    rows = int(written[0]) if written and written[0] is not None else int(
        con.execute(f"SELECT count(*) FROM {archive.relation_sql([tmp])}").fetchone()[0]
    )

    bounds = con.execute(
        f"SELECT min(event_number), max(event_number) FROM {archive.relation_sql([tmp])}"
    ).fetchone()
    incoming = (int(bounds[0]), int(bounds[1])) if bounds and bounds[0] is not None else None
    if mode == MODE_APPEND:
        try:
            check_append_collision(manifest.event_range(), incoming)
        except EventRangeCollisionError:
            tmp.unlink(missing_ok=True)
            raise

    os.replace(tmp, part)
    manifest.parts.append(archive.new_part(
        file=part.name, rows=rows, size=part.stat().st_size,
        source_name=source_name or path.name, source_bytes=path.stat().st_size,
        event_offset=event_offset, event_range=incoming,
        duckdb_version=duckdb.__version__,
    ))
    archive.write_manifest(settings, name, manifest)
    log.info(
        "Archive %s: part %s holds %s rows (%s bytes); %d part(s), %s rows in total",
        name, part.name, f"{rows:,}", f"{part.stat().st_size:,}",
        len(manifest.parts), f"{manifest.rows:,}",
    )
    return LoadResult(rows=rows, part=part, event_range=incoming, manifest=manifest)
