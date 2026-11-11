"""Load a validated CSV or Parquet source into the experiment's Parquet archive."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from ..config import Settings
from ..db import archive, naming, schemas
from ..db.ddl import drop_table
from ..errors import EventRangeCollisionError, IngestError
from . import formats
from .source_check import SourceCheck

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
    event_offset: int = 0,
) -> None:
    """Reject an append whose event numbers overlap what is already there.

    Ported from ``calodash/ingest.py``, which enforces the same rule in the
    batch pipeline. Two files that each number their events from zero are the
    normal case, not an exotic one, and merging them fuses distinct physics
    events into one: every per-event aggregate downstream - reconstructed
    energy, hit multiplicity, the centroids - would then describe a chimera.

    The caller can override by supplying an explicit ``event_offset``, which
    shifts the incoming numbers clear of the existing range. ``incoming`` is the
    range *after* the requested ``event_offset``, so the suggestion adds the
    extra shift to it: it is the absolute offset to supply next time.
    """
    if incoming is None or existing is None:
        return
    lo_a, hi_a = existing
    lo_b, hi_b = incoming
    if lo_b <= hi_a and lo_a <= hi_b:
        suggested = int(event_offset) + (hi_a - lo_b + 1)
        raise EventRangeCollisionError(
            f"The incoming file covers event numbers {lo_b}-{hi_b}, which "
            f"overlaps the {lo_a}-{hi_a} already in this experiment. Appending "
            "would merge distinct events. Supply an event_offset of at least "
            f"{suggested} to shift the incoming events clear, or upload "
            "into a new table instead.",
            existing_range=[lo_a, hi_a],
            incoming_range=[lo_b, hi_b],
            suggested_offset=suggested,
        )


def check_append_schema(name: str, manifest: archive.Manifest, schema: schemas.InputSchema) -> None:
    """Refuse an append whose file is not the schema the experiment's archive holds."""
    if (manifest.schema_name, manifest.schema_version) == (schema.name, schema.version):
        return
    held = schemas.get(manifest.schema_name, manifest.schema_version)
    held_label = held.label if held else f"{manifest.schema_name} v{manifest.schema_version}"
    raise IngestError(
        f"Cannot append a {schema.label} file to experiment {name!r}: its archive holds "
        f"the {held_label} schema.",
        expected={"name": manifest.schema_name, "version": manifest.schema_version},
        found={"name": schema.name, "version": schema.version},
    )


def _write_part(con, path: Path, part: Path, fmt: str, check: SourceCheck | None,
                event_offset: int, schema: schemas.InputSchema) -> tuple[int, tuple[int, int] | None]:
    """Write the source into ``part``'s temporary file; return its row count and event range.

    The part is left as ``<part>.tmp``: :func:`_publish_part` renames it once the
    caller has made its last check. The event range is read inside the try, so a
    part whose range cannot be read is removed too.
    """
    tmp = part.with_name(part.name + archive.TMP_SUFFIX)
    key = naming.quote(schema.event_key)
    try:
        written = con.execute(
            archive.copy_to_part_sql(formats.select_sql(path, fmt, event_offset, check), tmp)
        ).fetchone()
        rows = int(written[0]) if written and written[0] is not None else int(
            con.execute(f"SELECT count(*) FROM {archive.relation_sql([tmp])}").fetchone()[0]
        )
        bounds = con.execute(
            f"SELECT min({key}), max({key}) FROM {archive.relation_sql([tmp])}"
        ).fetchone()
    except duckdb.Error as exc:
        tmp.unlink(missing_ok=True)
        raise IngestError(f"DuckDB rejected {path.name}: {exc}") from exc
    incoming = (int(bounds[0]), int(bounds[1])) if bounds and bounds[0] is not None else None
    return rows, incoming


def _publish_part(part: Path, source: Path) -> None:
    os.replace(part.with_name(part.name + archive.TMP_SUFFIX), part)


def _part_entry(part: Path, source: Path, rows: int, incoming, source_name: str | None,
                event_offset: int, fmt: str) -> archive.ArchivePart:
    return archive.new_part(
        file=part.name, rows=rows, size=part.stat().st_size,
        source_name=source_name or source.name, source_bytes=source.stat().st_size,
        event_offset=event_offset, event_range=incoming,
        duckdb_version=duckdb.__version__, source_format=fmt,
    )


def stage_replacement(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    path: Path,
    *,
    fmt: str,
    check: SourceCheck,
    job_id: str,
    event_offset: int = 0,
    source_name: str | None = None,
) -> LoadResult:
    """Write ``path`` as a new part beside the committed one, to replace the archive atomically.

    Nothing is dropped and nothing is committed: the committed ``manifest.json``
    still lists the old part, which stays on disk, and readers never see the
    new one. The returned in-memory manifest lists **only** the new part and
    carries ``job_id``; :func:`calosrv.ingest.pipeline.reingest_atomic` derives
    over it inside a transaction and writes it as ``manifest.json.next`` just
    before the commit. The part's index is one past the committed manifest's
    largest (``archive.next_part_path``), so it never overwrites the old file.
    """
    if event_offset < 0:
        raise IngestError(f"event_offset must be zero or positive; got {event_offset}.")
    schema = check.schema
    archive.archive_path(settings, name).mkdir(parents=True, exist_ok=True)
    part = archive.next_part_path(settings, name)
    log.info("Archiving %s into %s (replacement, job %s)", path.name, part, job_id)
    rows, incoming = _write_part(con, path, part, fmt, check, event_offset, schema)
    _publish_part(part, path)
    manifest = archive.Manifest(schema.name, schema.version, job_id=job_id)
    try:
        manifest.parts.append(
            _part_entry(part, path, rows, incoming, source_name, event_offset, fmt))
    except BaseException:
        # The part is published but no manifest will ever list it: do not leave it
        # for the next boot to find.
        part.unlink(missing_ok=True)
        raise
    return LoadResult(rows=rows, part=part, event_range=incoming, manifest=manifest)


def load_source(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    path: Path,
    *,
    fmt: str = formats.CSV,
    check: SourceCheck | None = None,
    mode: str = MODE_CREATE_NEW,
    event_offset: int = 0,
    source_name: str | None = None,
    commit: bool = True,
) -> LoadResult:
    """Commit ``path`` - already validated as ``fmt`` - to the archive as one new part.

    ``create_new`` drops the experiment's derived tables - including a legacy
    ``hit_<name>`` table from the retired v37 schema - and its archive first.
    ``append`` adds a part after checking the event ranges do not collide.

    The source is read exactly once, straight into the part, whatever its
    format; the event range is then read from the part's statistics, not from a
    second pass over the source. ``check`` is the pre-flight result, which says
    which columns need NaN read as undefined.

    ``commit=False`` leaves the part out of the written manifest: the returned
    in-memory manifest lists it, so an append can derive and verify over it and
    commit only on success (``archive.write_manifest``), or discard it.
    Readers take the committed manifest and never glob, so an uncommitted part
    is invisible, and the next append's part replaces it.
    """
    if event_offset < 0:
        raise IngestError(f"event_offset must be zero or positive; got {event_offset}.")
    if mode not in VALID_MODES:
        raise IngestError(
            f"Unknown upload mode {mode!r}; expected one of {', '.join(VALID_MODES)}."
        )
    root = archive.archive_path(settings, name)
    schema = check.schema if check is not None else schemas.DEFAULT

    if mode == MODE_CREATE_NEW:
        for table in naming.all_tables(name):
            con.execute(drop_table(table))
        archive.remove(settings, name)
        manifest = archive.Manifest(schema.name, schema.version)
    else:
        archive.refuse_if_half_finished(settings, name)
        manifest = archive.read_manifest(settings, name)
        if manifest is None or not manifest.parts:
            raise IngestError(
                f"Cannot append to experiment {name!r}: its archive is missing. "
                "Re-ingest it with create_new first."
            )
        check_append_schema(name, manifest, schema)

    root.mkdir(parents=True, exist_ok=True)
    part = archive.next_part_path(settings, name)
    log.info("Archiving %s into %s (mode=%s)", path.name, part, mode)
    rows, incoming = _write_part(con, path, part, fmt, check, event_offset, schema)
    if mode == MODE_APPEND:
        try:
            check_append_collision(manifest.event_range(), incoming, event_offset)
        except EventRangeCollisionError:
            part.with_name(part.name + archive.TMP_SUFFIX).unlink(missing_ok=True)
            raise

    _publish_part(part, path)
    manifest.parts.append(_part_entry(part, path, rows, incoming, source_name, event_offset, fmt))
    if commit:
        archive.write_manifest(settings, name, manifest)
    log.info(
        "Archive %s: part %s holds %s rows (%s bytes); %d part(s), %s rows in total",
        name, part.name, f"{rows:,}", f"{part.stat().st_size:,}",
        len(manifest.parts), f"{manifest.rows:,}",
    )
    return LoadResult(rows=rows, part=part, event_range=incoming, manifest=manifest)
