"""The one ingest pipeline: CSV or Parquet -> Parquet archive -> derived tables -> checks.

Before this module the same eleven steps were written out three times - in the
background job, in the command-line tool and in the test fixture - and kept in
step by hand. They now all call :func:`run_ingest`; :func:`rebuild` re-derives
every table from an existing archive without reading any source file, and
:func:`rebuild_atomic` does so inside one transaction, so readers keep the old
tables until the new ones have verified. :func:`reingest_atomic` is the same
transaction around a *replacement* of the archive: the source file of a ready
experiment changed on disk, and the experiment stays served from its previous
data until the new tables and the new archive part have verified.

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
from ..db import archive, catalog, naming, registry, schemas
from ..db.ddl import KIND_TWO_SHOWER, drop_table
from ..errors import ExperimentExistsError, IngestError
from . import formats, load, recipes, source_state, stream
from .recipes import DeriveContext
from .result import IngestResult, _Stopwatch
from .source_check import SourceCheck

log = logging.getLogger(__name__)

#: The two-shower stage table, kept under its old name for the job store's
#: callers; ``recipes.stages(kind)`` gives every kind's.
STAGES: tuple[tuple[str, str, float], ...] = recipes.STAGES_BY_KIND[KIND_TWO_SHOWER]

__all__ = ["STAGES", "IngestResult", "run_ingest", "rebuild", "rebuild_atomic",
           "reingest_atomic"]


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
    provenance: dict | None = None,
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

    ``provenance`` (``source_state.origin_spec``) says where the file came from.
    The file's fingerprint is taken here, immediately before it is read, and
    stored on the registry row by ``mark_ingesting``, so a load that fails still
    has it. A replacing ingest always rewrites the row's source record; an
    append leaves it describing the file the experiment was created from.
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
    info = (source_state.make_info(provenance, source)
            if provenance is not None and not appending else None)

    def mark_ingesting() -> registry.ExperimentRecord:
        record = existing or registry.ExperimentRecord(table_name=name)
        record.display_name = display_name or record.display_name or name
        record.status = registry.STATUS_INGESTING
        record.error = None
        if not appending:
            # create_new replaces every row, so earlier files no longer describe
            # anything the experiment holds.
            record.source_files = [source_name]
            record.source_info = info or {}
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


def _cleanup_replacement(settings: Settings, name: str, loaded: load.LoadResult) -> None:
    """Remove what a re-ingest wrote beside the committed archive: the new part and the next manifest."""
    loaded.part.unlink(missing_ok=True)
    loaded.part.with_name(loaded.part.name + archive.TMP_SUFFIX).unlink(missing_ok=True)
    archive.discard_next(settings, name)


def reingest_atomic(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    source: Path,
    *,
    source_name: str,
    provenance: dict,
    job_id: str,
    progress: Callable[[str, str], None] | None = None,
    build_sample: bool = True,
) -> IngestResult:
    """Replace a ready experiment's data from its changed source file, in one transaction.

    The caller holds the write lock. The experiment is served from its previous
    tables, registry row and archive until the new ones have verified: DuckDB's
    snapshot isolation keeps them visible to every other cursor until COMMIT,
    and the committed ``manifest.json`` keeps listing the old part until the
    rename after it. Steps:

    1. detect the format and validate; the file's schema must equal the
       experiment's, and the experiment must be ready with exactly one part;
    2. write the file as a new part beside the committed one
       (``load.stage_replacement``) - not committed;
    3. ``BEGIN``, drop every table of the experiment;
    4. upsert a copy of its row as ``ingesting`` with the new source record,
       keeping the display name and ``created_at``;
    5. derive and verify over the new manifest;
    6. verified: write ``manifest.json.next``, ``COMMIT``, rename it over the
       manifest, delete the old part. Not verified: ``ROLLBACK``, remove the
       new part, and say so in the warnings. An exception: the same, raised as
       an ``IngestError`` that says the experiment is served as it was.

    A crash between the steps is settled at the next boot
    (``archive.reconcile``).
    """
    progress = progress or _no_progress
    watch = _Stopwatch(con)
    fmt = formats.detect_format(source)
    check = formats.validate(con, source, fmt)
    schema = check.schema

    existing = registry.get_experiment(con, name)
    if existing is None:
        raise IngestError(f"Experiment {name!r} does not exist, so there is nothing to re-ingest.")
    if existing.status != registry.STATUS_READY:
        raise IngestError(
            f"Experiment {name!r} is {existing.status}; only a ready experiment is re-ingested.")
    committed = archive.read_manifest(settings, name)
    if committed is None or len(committed.parts) != 1:
        found = len(committed.parts) if committed is not None else 0
        raise IngestError(
            f"Experiment {name!r} holds {found} archive part(s); a re-ingest replaces exactly "
            "one. Replace it from Upload dataset instead.")
    if (committed.schema_name, committed.schema_version) != (schema.name, schema.version):
        held = schemas.get(committed.schema_name, committed.schema_version)
        held_label = held.label if held else f"{committed.schema_name} v{committed.schema_version}"
        raise IngestError(
            f"{source_name} is a {schema.label} file, but experiment {name!r} holds the "
            f"{held_label} schema; a re-ingest keeps the schema. Replace it from Upload dataset "
            "instead.",
            expected={"name": committed.schema_name, "version": committed.schema_version},
            found={"name": schema.name, "version": schema.version},
        )

    # Taken immediately before the file is read, so it describes what was read.
    info = source_state.make_info(provenance, source, job_id)
    event_offset = int(committed.parts[0].event_offset or 0)
    old_files = [str(path) for path in archive.part_paths(settings, name, committed)]

    progress("archive", schema.kind)
    loaded = load.stage_replacement(
        con, settings, name, source, fmt=fmt, check=check, job_id=job_id,
        event_offset=event_offset, source_name=source_name,
    )
    watch.mark("archive")

    def failure(exc: BaseException) -> IngestError:
        return IngestError(
            f"The re-ingest of {name!r} from {source_name} failed ({exc}) and was rolled back; "
            "the experiment is served as it was.")

    con.execute("BEGIN TRANSACTION")
    committed_db = False
    try:
        for table in naming.all_tables(name):
            con.execute(drop_table(table))
        record = copy.deepcopy(existing)
        record.status = registry.STATUS_INGESTING
        record.error = None
        record.source_files = [source_name]
        record.source_info = info
        record.schema_name, record.schema_version = schema.name, schema.version
        registry.upsert(con, record)
        result = _derive(con, settings, record, source, loaded.manifest, build_sample, watch,
                         progress, part_rows=loaded.rows, check=check)
        if result.ok:
            archive.write_next(settings, name, loaded.manifest)
            con.execute("COMMIT")
            committed_db = True
    except BaseException as exc:
        if not committed_db:
            try:
                con.execute("ROLLBACK")
            except duckdb.Error:  # pragma: no cover - the transaction is already gone
                log.warning("Rollback of the re-ingest of %r failed", name)
            _cleanup_replacement(settings, name, loaded)
        if isinstance(exc, Exception):
            log.error("Re-ingest of %r failed and was rolled back: %s", name, exc)
            raise failure(exc) from exc
        raise

    if not result.ok:
        con.execute("ROLLBACK")
        _cleanup_replacement(settings, name, loaded)
        message = (f"The re-ingest failed verification and was rolled back; {name!r} is served "
                   "as it was.")
        log.warning("%s %s", message, "; ".join(result.warnings))
        result.verification.warnings.append(message)
        return result

    archive.commit_next(settings, name)
    for old in old_files:
        if Path(old) != loaded.part:
            Path(old).unlink(missing_ok=True)
    log.info("Re-ingest of %r committed: %s replaced by %s", name,
             ", ".join(Path(o).name for o in old_files), loaded.part.name)
    return result
