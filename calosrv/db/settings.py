"""DuckDB session configuration.

Split from ``connection.py`` so the exact ``SET`` statements the server applies -
the part an operator tunes and a reviewer audits - sit in one short file.

Every setting here is GLOBAL in DuckDB: one database instance, one buffer
manager, one set of limits for every cursor. Nothing toggles them per query.
"""

from __future__ import annotations

import logging
import shutil

import duckdb

from ..config import Settings

log = logging.getLogger(__name__)

#: Never let spill files use more than this, whatever the disk offers.
MAX_TEMP_DIRECTORY_BYTES = 64 * 1024 ** 3

#: ...nor more than this share of the spill filesystem's free space.
TEMP_SHARE_OF_FREE = 0.5


def _temp_cap_bytes(settings: Settings) -> int:
    try:
        free = shutil.disk_usage(settings.temp_dir).free
    except OSError:
        return MAX_TEMP_DIRECTORY_BYTES
    return int(min(MAX_TEMP_DIRECTORY_BYTES, max(1024 ** 3, TEMP_SHARE_OF_FREE * free)))


def apply_session_settings(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    """Apply the server-wide DuckDB configuration and log what took effect.

    ``memory_limit`` bounds the buffer manager only; query results converted
    to NumPy, the Python heap and the bundle caches sit outside it, which is
    why the container carries about 4 GB of headroom above ``DUCKDB_MEMORY_GB``.
    """
    con.execute(f"SET memory_limit = '{settings.memory_gb}GB';")
    con.execute(f"SET threads = {settings.threads};")

    # Spill to the mounted data volume, never to a tmpfs: the storage guard
    # has already refused a RAM-backed temp_dir by the time this runs. The cap
    # is the smaller of 64 GiB and half the spill filesystem's free space, so a
    # runaway query fails with a clear error instead of filling the disk.
    con.execute(f"SET temp_directory = '{settings.temp_dir.as_posix()}';")
    con.execute(f"SET max_temp_directory_size = '{_temp_cap_bytes(settings)}B';")

    # Every query aggregates or orders explicitly, so row order is never
    # relied on; preserving it forces batch-ordered inserts that buffer far more
    # per thread, and is what a multi-gigabyte CSV-to-Parquet load cannot
    # afford. It also lets the Parquet writer honour its per-row-group size.
    con.execute("SET preserve_insertion_order = false;")

    # Return freed memory to the operating system in the background, so the
    # process RSS falls after an ingest instead of sitting at its peak.
    con.execute("SET allocator_background_threads = true;")

    # A progress bar writes control characters to stdout. Harmless in a REPL,
    # corrupting in a container log.
    con.execute("SET enable_progress_bar = false;")

    # Checkpoint *less* eagerly than the 16 MiB default. Bulk inserts write row
    # groups straight to the database file, so the write-ahead log stays small
    # during an ingest anyway, and a lower threshold would only interrupt it
    # with mid-load checkpoints.
    con.execute("SET checkpoint_threshold = '1GB';")

    effective = dict(
        con.execute(
            "SELECT name, value FROM duckdb_settings() WHERE name IN ("
            "'memory_limit', 'threads', 'temp_directory', 'max_temp_directory_size', "
            "'preserve_insertion_order', 'allocator_background_threads')"
        ).fetchall()
    )
    log.info(
        "DuckDB session configured: memory_limit=%s threads=%s temp_directory=%s "
        "max_temp_directory_size=%s preserve_insertion_order=%s "
        "allocator_background_threads=%s",
        effective.get("memory_limit"), effective.get("threads"),
        effective.get("temp_directory"), effective.get("max_temp_directory_size"),
        effective.get("preserve_insertion_order"),
        effective.get("allocator_background_threads"),
    )
