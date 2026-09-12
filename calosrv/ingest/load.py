"""Load a staged CSV into the archival hit table."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from ..db import naming
from ..db.ddl import HIT_COLUMN_NAMES, create_hit_table, drop_table
from ..db.naming import quote
from ..db.settings import set_ingest_mode
from ..errors import EventRangeCollisionError, IngestError
from . import csv_spec

log = logging.getLogger(__name__)

MODE_CREATE_NEW = "create_new"
MODE_APPEND = "append"
VALID_MODES = (MODE_CREATE_NEW, MODE_APPEND)


def event_range(con: duckdb.DuckDBPyConnection, physical: str) -> tuple[int, int] | None:
    """The ``(min, max)`` event number in a table, or ``None`` if empty."""
    row = con.execute(
        f"SELECT min(event_number), max(event_number) FROM {quote(physical)}"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0]), int(row[1])


def csv_event_range(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[int, int] | None:
    """The ``(min, max)`` event number in a CSV, read without loading it.

    DuckDB projects only the one column it needs out of the CSV, so this is a
    parse of one field per row rather than of twenty-nine.
    """
    expression = csv_spec.read_csv_expression(path)
    row = con.execute(
        f"SELECT min(event_number), max(event_number) FROM {expression}"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0]), int(row[1])


def check_append_collision(
    con: duckdb.DuckDBPyConnection,
    physical: str,
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
    if incoming is None:
        return
    existing = event_range(con, physical)
    if existing is None:
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


def load_csv(
    con: duckdb.DuckDBPyConnection,
    name: str,
    path: Path,
    mode: str = MODE_CREATE_NEW,
    event_offset: int = 0,
) -> int:
    """Load ``path`` into ``hit_<name>``, returning the row count inserted.

    No ``ORDER BY`` is applied. The source file is already sorted by
    ``event_number``, and the ``overlap`` class - which drives the separation
    distance D - is monotone in blocks along it. Loading in file order therefore
    gives DuckDB zone maps that let the D slider prune whole row groups for
    free. Re-sorting on any other key would trade that away.
    """
    if mode not in VALID_MODES:
        raise IngestError(
            f"Unknown upload mode {mode!r}; expected one of {', '.join(VALID_MODES)}."
        )

    physical = naming.hit_table(name)
    csv_spec.validate_header(path)

    exists = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [physical],
    ).fetchone()[0]

    if mode == MODE_CREATE_NEW:
        if exists:
            log.info("CREATE_NEW: dropping existing tables for %r", name)
            for table in naming.all_tables(name):
                con.execute(drop_table(table))
        con.execute(create_hit_table(physical))
    else:
        if not exists:
            raise IngestError(
                f"Cannot append to experiment {name!r}: it does not exist yet. "
                "Use create_new for the first upload."
            )
        incoming = csv_event_range(con, path)
        if event_offset:
            incoming = (incoming[0] + event_offset, incoming[1] + event_offset)
        check_append_collision(con, physical, incoming)

    columns = ", ".join(quote(c) for c in HIT_COLUMN_NAMES)
    expression = csv_spec.read_csv_expression(path)

    # The event_number projection is written out explicitly so the offset can be
    # applied; every other column passes through untouched.
    if event_offset:
        projected = ", ".join(
            f"event_number + {int(event_offset)} AS event_number" if c == "event_number"
            else quote(c)
            for c in HIT_COLUMN_NAMES
        )
    else:
        projected = columns

    set_ingest_mode(con, True)
    try:
        log.info("Loading %s into %s (mode=%s)", path.name, physical, mode)
        con.execute(
            f"INSERT INTO {quote(physical)} ({columns}) "
            f"SELECT {projected} FROM {expression}"
        )
    except duckdb.Error as exc:
        raise IngestError(f"DuckDB rejected {path.name}: {exc}") from exc
    finally:
        set_ingest_mode(con, False)

    total = con.execute(f"SELECT count(*) FROM {quote(physical)}").fetchone()[0]
    log.info("%s now holds %s rows", physical, f"{total:,}")
    return int(total)
