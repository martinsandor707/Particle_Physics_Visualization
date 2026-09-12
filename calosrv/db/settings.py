"""DuckDB session configuration.

Split from ``connection.py`` so the exact ``SET`` statements the server applies -
the part an operator tunes and a reviewer audits - sit in one short file.
"""

from __future__ import annotations

import logging

import duckdb

from ..config import Settings

log = logging.getLogger(__name__)


def apply_session_settings(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    """Apply the server-wide DuckDB configuration.

    ``max_memory`` and ``memory_limit`` are aliases in current DuckDB; the brief
    names ``max_memory``, so that is what is set, and the effective value is read
    back and logged rather than assumed.
    """
    con.execute(f"SET max_memory = '{settings.memory_gb}GB';")
    con.execute(f"SET threads = {settings.threads};")

    # Spill to the mounted volume, not to the container's writable layer, which
    # is typically far smaller. Without a generous cap, a large ingest aborts
    # partway through with an unhelpful out-of-memory error instead of spilling.
    con.execute(f"SET temp_directory = '{settings.temp_dir.as_posix()}';")
    con.execute("SET max_temp_directory_size = '64GiB';")

    # A progress bar writes control characters to stdout. Harmless in a REPL,
    # corrupting in a container log.
    con.execute("SET enable_progress_bar = false;")

    # Checkpoint more eagerly than the 16 MB default so the write-ahead log does
    # not grow without bound across a multi-gigabyte ingest.
    con.execute("SET checkpoint_threshold = '1GB';")

    effective = dict(
        con.execute(
            "SELECT name, value FROM duckdb_settings() "
            "WHERE name IN ('max_memory', 'threads', 'temp_directory');"
        ).fetchall()
    )
    log.info(
        "DuckDB session configured: max_memory=%s threads=%s temp_directory=%s",
        effective.get("max_memory"),
        effective.get("threads"),
        effective.get("temp_directory"),
    )


def set_ingest_mode(con: duckdb.DuckDBPyConnection, enabled: bool) -> None:
    """Toggle the settings that only make sense while bulk-loading.

    ``preserve_insertion_order = false`` is a large peak-memory saving on a
    multi-gigabyte CSV load. It is safe here because the source file is read in
    order and every query downstream aggregates - nothing depends on the
    physical row order within the table. It is restored afterwards so that any
    later ``SELECT`` a human runs against the database behaves conventionally.
    """
    con.execute(f"SET preserve_insertion_order = {'false' if enabled else 'true'};")
