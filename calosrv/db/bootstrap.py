"""Idempotent startup reconciliation.

Runs on every boot. Creates the registry if absent, repairs rows left
inconsistent by a crash, and reports whether the database is empty so the
application lifespan knows to seed the baseline experiment.
"""

from __future__ import annotations

import logging

import duckdb

from ..config import Settings
from . import archive, naming, registry
from .ddl import SCHEMA_NAME, SCHEMA_VERSION
from .naming import quote

log = logging.getLogger(__name__)

#: The error recorded on an experiment ingested under the retired 29-column
#: v37 schema. Its tables are never queried again; deleting it and ingesting
#: the data in the hits_all_models format is the way forward.
UNSUPPORTED_V37_ERROR = "unsupported schema (v37, retired): delete and re-ingest"


def physical_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'"
    ).fetchall()
    return {row[0] for row in rows}


def _is_current_schema(record: registry.ExperimentRecord) -> bool:
    return (record.schema_name, record.schema_version) == (SCHEMA_NAME, SCHEMA_VERSION)


def bootstrap(
    con: duckdb.DuckDBPyConnection, settings: Settings | None = None
) -> list[registry.ExperimentRecord]:
    """Prepare the database for serving and return the ready experiments.

    ``ensure_registry`` migrates an older registry by adding columns, so a
    database written before the multi-model schema reads its rows with a NULL
    ``schema_name``: those experiments were ingested under the retired v37
    schema and are marked failed, never queried.
    """
    registry.ensure_registry(con)
    if settings is not None:
        archive.sweep_tmp(settings)

    present = physical_tables(con)
    records = registry.list_experiments(con)

    for record in records:
        name = record.table_name

        if record.status != registry.STATUS_INGESTING and not _is_current_schema(record):
            if record.error != UNSUPPORTED_V37_ERROR:
                log.warning(
                    "Experiment %r was ingested under a retired schema (%s); marking it "
                    "failed. Delete it and ingest the data in the %s format.",
                    name, record.schema_name or "v37", SCHEMA_NAME,
                )
                registry.set_status(con, name, registry.STATUS_FAILED, UNSUPPORTED_V37_ERROR)
            continue

        # A row still marked 'ingesting' means the process died mid-load. The
        # tables it was writing are in an unknown state, so the honest move is
        # to mark it failed and leave the partial data for an operator to
        # inspect, rather than to serve half a dataset as if it were whole.
        if record.status == registry.STATUS_INGESTING:
            log.warning(
                "Experiment %r was mid-ingest at shutdown; marking it failed. "
                "Re-upload or re-run the offline ingest to rebuild it.", name
            )
            registry.set_status(
                con, name, registry.STATUS_FAILED,
                "Ingestion was interrupted before it completed.",
            )
            continue

        if record.status != registry.STATUS_READY:
            continue

        # A registry row whose tables have been dropped out from under it (a
        # hand-edited database, a restored volume) would otherwise fail at query
        # time with a confusing missing-table error.
        required = {naming.proj_table(name), naming.event_table(name)}
        if record.has_sample:
            required.add(naming.proj_table(name, sampled=True))
        missing = required - present
        if missing:
            log.warning(
                "Experiment %r is registered ready but %s missing; marking failed.",
                name, ", ".join(sorted(missing)),
            )
            registry.set_status(
                con, name, registry.STATUS_FAILED,
                f"Backing tables are missing: {', '.join(sorted(missing))}",
            )
            continue

        # The hot path never reads the archive, so a missing one does not stop
        # serving; it does stop append and rebuild, which say so themselves.
        if settings is not None and not archive.part_paths(settings, name):
            log.warning(
                "Experiment %r has no Parquet archive under %s; it can be served but "
                "not appended to or rebuilt.", name, archive.archive_path(settings, name),
            )

    ready = registry.list_experiments(con, ready_only=True)
    log.info(
        "Bootstrap complete: %d experiment(s) ready%s",
        len(ready),
        (": " + ", ".join(r.table_name for r in ready)) if ready else "",
    )
    return ready


def is_empty(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether the database holds no application tables at all.

    Checked against the physical tables rather than the registry: a database
    with orphaned tables but an empty registry should not be silently seeded
    over the top of them.
    """
    managed = [t for t in physical_tables(con) if naming.is_managed_table(t)]
    if managed:
        return False
    count = con.execute('SELECT count(*) FROM "experiment"').fetchone()
    return int(count[0]) == 0


def drop_experiment(
    con: duckdb.DuckDBPyConnection, name: str, settings: Settings | None = None
) -> bool:
    """Remove every table of an experiment, its registry row and its archive.

    The tables include a legacy ``hit_<name>`` from the retired v37 schema.
    Returns whether an archive directory was removed.
    """
    for physical in naming.all_tables(name):
        con.execute(f"DROP TABLE IF EXISTS {quote(physical)};")
    registry.delete(con, name)
    removed = archive.remove(settings, name) if settings is not None else False
    log.info("Dropped experiment %r%s", name, " and its archive" if removed else "")
    return removed


def retire_unsupported(
    con: duckdb.DuckDBPyConnection, name: str, settings: Settings | None = None
) -> bool:
    """Drop ``name`` if it holds a retired schema. For the app-owned baseline only.

    The demonstration experiment is the application's own data, rebuilt from
    the seed file, so a baseline left over from the v37 schema is replaced
    rather than left failed. A user's experiments are never dropped this way.
    """
    record = registry.get_experiment(con, name)
    if record is None or _is_current_schema(record):
        return False
    log.info("Replacing the %r demonstration experiment ingested under a retired schema", name)
    drop_experiment(con, name, settings)
    return True
