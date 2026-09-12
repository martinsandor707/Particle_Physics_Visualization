"""Idempotent startup reconciliation.

Runs on every boot. Creates the registry if absent, repairs rows left
inconsistent by a crash, and reports whether the database is empty so the
application lifespan knows to seed the baseline experiment.
"""

from __future__ import annotations

import logging

import duckdb

from . import naming, registry
from .naming import quote

log = logging.getLogger(__name__)


def physical_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'"
    ).fetchall()
    return {row[0] for row in rows}


def bootstrap(con: duckdb.DuckDBPyConnection) -> list[registry.ExperimentRecord]:
    """Prepare the database for serving and return the ready experiments."""
    registry.ensure_registry(con)

    present = physical_tables(con)
    records = registry.list_experiments(con)

    for record in records:
        name = record.table_name

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
        required = {naming.hit_table(name), naming.proj_table(name),
                    naming.event_table(name)}
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


def drop_experiment(con: duckdb.DuckDBPyConnection, name: str) -> None:
    """Remove every table belonging to an experiment, and its registry row."""
    for physical in naming.all_tables(name):
        con.execute(f"DROP TABLE IF EXISTS {quote(physical)};")
    registry.delete(con, name)
    log.info("Dropped experiment %r", name)
