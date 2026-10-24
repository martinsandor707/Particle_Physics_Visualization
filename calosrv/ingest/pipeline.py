"""The one ingest pipeline: CSV or Parquet -> Parquet archive -> derived tables -> checks.

Before this module the same eleven steps were written out three times - in the
background job, in the command-line tool and in the test fixture - and kept in
step by hand. They now all call :func:`run_ingest`; :func:`rebuild` re-derives
every table from an existing archive without reading any source file, and
:func:`rebuild_atomic` does so inside one transaction, so readers keep the old
tables until the new ones have verified.

Which tables are derived, and how they are checked, depends on the input
schema's kind; ``recipes.py`` holds one recipe per kind.

Every stage records its wall time, the process's peak RSS so far, DuckDB's
buffer-managed memory and its spill-file size, so the report shows which stage
set the peak - the measurement the ingest memory budget is judged on.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

import duckdb

from ..config import Settings
from ..db import archive, catalog, registry, schemas
from ..db.ddl import KIND_TWO_SHOWER
from ..errors import ExperimentExistsError, IngestError
from . import formats, load, recipes, stream
from .recipes import DeriveContext
from .result import IngestResult, _Stopwatch
from .source_check import SourceCheck

log = logging.getLogger(__name__)

#: The two-shower stage table, kept under its old name for the job store's
#: callers; ``recipes.stages(kind)`` gives every kind's.
STAGES: tuple[tuple[str, str, float], ...] = recipes.STAGES_BY_KIND[KIND_TWO_SHOWER]

__all__ = ["STAGES", "IngestResult", "run_ingest", "rebuild", "rebuild_atomic"]


def _no_progress(_stage: str, _kind: str) -> None:
    return None


def _derive(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    record: registry.ExperimentRecord,
    source: Path | None,
    manifest: archive.Manifest,
    build_sample: bool,
    watch: _Stopwatch,
    progress: Callable[[str, str], None],
    part_rows: int | None = None,
    check: SourceCheck | None = None,
) -> IngestResult:
    """Everything after the archive, by the recipe of the archive's schema."""
    schema = schemas.get(manifest.schema_name, manifest.schema_version)
    if schema is None:
        raise IngestError(
            f"Experiment {record.table_name!r} holds an archive of the "
            f"{manifest.schema_name} v{manifest.schema_version} schema, which this release "
            "does not derive. Delete it and re-ingest the source file."
        )
    return recipes.derive(DeriveContext(
        con=con, settings=settings, record=record, schema=schema, source=source,
        manifest=manifest, build_sample=build_sample, watch=watch, progress=progress,
        part_rows=part_rows, check=check,
    ))


def run_ingest(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    source: Path,
    *,
    source_name: str | None = None,
    mode: str = load.MODE_CREATE_NEW,
    event_offset: int = 0,
    display_name: str = "",
    build_sample: bool = True,
    check_space: bool = True,
    created_at=None,
    progress: Callable[[str, str], None] | None = None,
    force_reingest: bool = False,
) -> IngestResult:
    """Ingest one CSV or Parquet file into experiment ``name``. Caller holds the write lock.

    Nothing in the registry changes until the file is known to be acceptable:
    its format is read from its content and its columns checked first, and an
    append also passes its event-range check before the record is touched, so a
    refused file leaves a ready experiment ready. An append is **provisional**
    until it verifies: its part is committed to the manifest only on success; on
    failure the part is discarded and the experiment rebuilt from its previous
    parts.

    ``create_new`` onto a name that already holds anything - a registry row in
    any status, a table, an archive - raises ``ExperimentExistsError`` unless
    ``force_reingest``. Replacing drops the old experiment before the new file
    is read, so the file's checks all run first: a refused file never costs the
    experiment it would have replaced.
    """
    progress = progress or _no_progress
    watch = _Stopwatch(con)
    source_name = source_name or source.name
    fmt = formats.detect_format(source)
    check = formats.validate(con, source, fmt)
    schema = check.schema
    if check_space:
        stream.check_free_space(
            settings.data_dir, source.stat().st_size,
            formats.headroom_factor(settings, fmt, staged=False),
        )

    appending = mode == load.MODE_APPEND
    if not appending and not force_reingest:
        present = catalog.presence(con, settings, name)
        if present.exists:
            raise ExperimentExistsError(
                f"Experiment {name!r} already exists ({present.describe()}). Pass "
                "force_reingest=true (--force-reingest on the command line) to replace "
                "it; it is deleted before the new file is loaded.",
                table_name=name, existing_status=present.status,
            )

    registry.ensure_registry(con)
    existing = registry.get_experiment(con, name)
    snapshot = copy.deepcopy(existing)

    def mark_ingesting() -> registry.ExperimentRecord:
        record = existing or registry.ExperimentRecord(table_name=name)
        record.display_name = display_name or record.display_name or name
        record.status = registry.STATUS_INGESTING
        record.error = None
        if not appending:
            # create_new replaces every row, so earlier files no longer describe
            # anything the experiment holds.
            record.source_files = [source_name]
        elif source_name not in record.source_files:
            record.source_files = [*record.source_files, source_name]
        if record.created_at is None and created_at is not None:
            record.created_at = created_at
        record.schema_name, record.schema_version = schema.name, schema.version
        registry.upsert(con, record)
        return record

    progress("archive", schema.kind)
    if not appending:
        record = mark_ingesting()
        loaded = load.load_source(
            con, settings, name, source, fmt=fmt, check=check, mode=mode,
            event_offset=event_offset, source_name=source_name,
        )
        watch.mark("archive")
        return _derive(con, settings, record, source, loaded.manifest, build_sample, watch,
                       progress, part_rows=loaded.rows, check=check)

    loaded = load.load_source(
        con, settings, name, source, fmt=fmt, check=check, mode=mode,
        event_offset=event_offset, source_name=source_name, commit=False,
    )
    record = mark_ingesting()
    watch.mark("archive")
    try:
        result = _derive(con, settings, record, source, loaded.manifest, build_sample, watch,
                         progress, part_rows=loaded.rows, check=check)
    except Exception as exc:
        _discard_append(con, settings, name, loaded, snapshot, build_sample)
        raise IngestError(
            f"Appending {source_name} to {name!r} failed ({exc}). The new part was discarded "
            "and the experiment rebuilt from its previous parts."
        ) from exc
    if result.ok:
        archive.write_manifest(settings, name, loaded.manifest)
        return result
    _discard_append(con, settings, name, loaded, snapshot, build_sample)
    result.verification.warnings.append(
        f"The append of {source_name} failed verification; its part was discarded and "
        f"{name!r} rebuilt from its previous parts."
    )
    return result


def _discard_append(con, settings, name, loaded, snapshot, build_sample) -> None:
    """Remove an uncommitted append part and restore the experiment it was appended to."""
    loaded.part.unlink(missing_ok=True)
    if snapshot is not None:
        registry.upsert(con, snapshot)
    log.warning("Append to %r discarded; rebuilding from the committed parts", name)
    rebuild(con, settings, name, build_sample=build_sample)


def rebuild(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    *,
    build_sample: bool = True,
    progress: Callable[[str, str], None] | None = None,
) -> IngestResult:
    """Re-derive every table of ``name`` from its archive, reading no source file."""
    progress = progress or _no_progress
    manifest = archive.read_manifest(settings, name)
    if manifest is None or not manifest.parts:
        raise IngestError(f"Experiment {name!r} has no archive to rebuild from.")
    record = registry.get_experiment(con, name) or registry.ExperimentRecord(table_name=name)
    record.status = registry.STATUS_INGESTING
    record.error = None
    registry.upsert(con, record)
    watch = _Stopwatch(con)
    return _derive(con, settings, record, None, manifest, build_sample, watch, progress)


def rebuild_atomic(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    *,
    build_sample: bool = True,
    progress: Callable[[str, str], None] | None = None,
) -> IngestResult:
    """:func:`rebuild` inside one transaction, committed only if it verifies.

    Readers keep the old tables and the old registry row (DuckDB's snapshot
    isolation) for the whole rebuild, so the experiment stays served. A
    rebuild that fails verification, or raises, rolls back to exactly what
    was there; the disk holds the old and the new tables side by side until
    then.
    """
    con.execute("BEGIN TRANSACTION")
    try:
        result = rebuild(con, settings, name, build_sample=build_sample, progress=progress)
    except BaseException:
        con.execute("ROLLBACK")
        raise
    if result.ok:
        con.execute("COMMIT")
        log.info("Rebuild of %r committed", name)
    else:
        con.execute("ROLLBACK")
        log.warning("Rebuild of %r failed verification and was rolled back: %s",
                    name, "; ".join(result.warnings))
    return result
