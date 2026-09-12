"""Structured logging and the boot banner.

The banner is not decoration: section 1 of the brief requires the resolved
memory ceiling and thread allocation to reach standard output at boot, because
that is the only place an operator can confirm that ``DUCKDB_MEMORY_GB`` was
read as an integer rather than silently falling back to the default.
"""

from __future__ import annotations

import logging
import sys

from .config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)-28s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own colourised handlers; route them through ours so a
    # container log is one consistent stream.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # DuckDB is chatty about buffer-manager internals at DEBUG.
    logging.getLogger("duckdb").setLevel("WARNING")


def log_boot_banner(settings: Settings) -> None:
    """Emit the hardware allocation summary required at server boot."""
    log = logging.getLogger("calosrv.boot")
    log.info("=" * 72)
    log.info("Calorimeter Shower Reconstruction Diagnostic Server")
    log.info("-" * 72)
    log.info("DuckDB memory ceiling : %d GB  (DUCKDB_MEMORY_GB)", settings.memory_gb)
    log.info("DuckDB worker threads : %d  (of %d host CPU cores)",
             settings.threads, settings.cpu_cores)
    log.info("Database file         : %s", settings.db_path)
    log.info("Upload staging        : %s", settings.staging_dir)
    log.info("DuckDB temp spill     : %s", settings.temp_dir)
    log.info("Baseline seed CSV     : %s", settings.seed_csv or "<none found>")
    log.info("Listening on          : http://%s:%d", settings.host, settings.port)
    log.info(
        "Container memory should be >= %d GB; DuckDB's limit excludes the "
        "Python heap, Arrow buffers and the %d-entry matrix cache.",
        settings.memory_gb + 4,
        settings.cache_entries,
    )
    log.info("=" * 72)
