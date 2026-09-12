"""The process-wide DuckDB connection and its cursor policy.

DuckDB is a single-writer embedded engine. One connection owns the database
file; concurrent work is done with *cursors* taken from it, which share the
buffer pool and the configuration but carry independent transaction state.

Two access patterns exist and they are deliberately different:

``read_cursor()``
    Short-lived, taken per request. Cheap, and freely concurrent with other
    readers.

``write_lock()``
    Serialised behind a mutex. Ingest holds this for minutes at a time, so it
    must never be acquired from inside an HTTP handler - ``ingest/jobs.py`` runs
    it on a dedicated worker thread instead.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from ..config import Settings
from .settings import apply_session_settings

log = logging.getLogger(__name__)


class Database:
    """Owns the DuckDB connection for the lifetime of the process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._write_mutex = threading.Lock()

        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Opening DuckDB database at %s", settings.db_path)
        self._con = duckdb.connect(str(settings.db_path))
        apply_session_settings(self._con, settings)

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def raw(self) -> duckdb.DuckDBPyConnection:
        """The underlying connection. Prefer the cursor helpers below."""
        return self._con

    @contextmanager
    def read_cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """A short-lived read cursor.

        ``cursor()`` on DuckDB returns a connection sharing the same database
        instance and buffer pool, so this is cheap - no file is reopened and no
        configuration is re-applied.
        """
        cursor = self._con.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    @contextmanager
    def write_lock(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Exclusive write cursor, serialised across the process.

        DuckDB permits exactly one writer. Without this mutex two concurrent
        ingests - or an ingest racing a registry update - would surface as an
        opaque transaction conflict at an arbitrary point mid-load.
        """
        with self._write_mutex:
            cursor = self._con.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def close(self) -> None:
        log.info("Closing DuckDB database")
        self._con.close()


_database: Database | None = None
_init_lock = threading.Lock()


def get_database(settings: Settings | None = None) -> Database:
    """Return the process-wide :class:`Database`, creating it on first call."""
    global _database
    if _database is None:
        with _init_lock:
            if _database is None:
                if settings is None:
                    raise RuntimeError(
                        "get_database() needs Settings on its first call; the "
                        "application lifespan is responsible for that call."
                    )
                _database = Database(settings)
    return _database


def reset_database() -> None:
    """Drop the process-wide connection. For tests and for shutdown."""
    global _database
    if _database is not None:
        _database.close()
        _database = None
