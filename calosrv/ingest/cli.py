"""``python -m calosrv.ingest`` - ingest a CSV without pushing it through HTTP.

The upload endpoint accepts files of any size, but sending 7.4 GB from a browser
is slow, unresumable and easy to interrupt. For datasets already on the host -
the normal in-house case - this reads the file in place.

    docker compose exec calorimeter-dashboard \\
        python -m calosrv.ingest --input /app/host/hits_with_gradcam_v37.csv \\
                                 --table v37

**How it reaches the database.** DuckDB holds its lock on the database file
*across processes*, not merely within one, so a second process cannot open the
database while the server has it - the attempt fails immediately with a lock
error rather than waiting. This command therefore works in two modes and picks
between them automatically:

*Delegated* (a server is running) - it posts the path to ``/api/ingest-local``
and follows the job to completion. The server process, which already owns the
database, does the work on the same background worker an upload would use. Only
the path crosses HTTP; the file itself is still read in place.

*Direct* (no server) - it opens the database itself and runs the pipeline
in-process.

``--direct`` forces the second mode, which fails loudly if the database is
locked rather than silently delegating.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb

from ..config import load_settings
from ..db import naming, registry
from ..db.bootstrap import bootstrap
from ..db.connection import get_database
from ..errors import ApiError
from ..logging_setup import configure_logging
from . import derive_events, derive_proj, lattice_fit, load, verify as verify_mod

log = logging.getLogger("calosrv.ingest.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m calosrv.ingest",
        description="Ingest a calorimeter inference CSV into the DuckDB store.",
    )
    parser.add_argument(
        "--input", "-i", required=True, type=Path,
        help="Path to the CSV file to ingest.",
    )
    parser.add_argument(
        "--table", "-t", required=True,
        help="Target experiment name (lowercase letters, digits, underscores).",
    )
    parser.add_argument(
        "--mode", "-m", choices=(load.MODE_CREATE_NEW, load.MODE_APPEND),
        default=load.MODE_CREATE_NEW,
        help="create_new drops any existing table of this name; append adds to it.",
    )
    parser.add_argument(
        "--display-name", default="",
        help="Human-readable label shown in the experiment dropdown.",
    )
    parser.add_argument(
        "--event-offset", type=int, default=0,
        help="Shift incoming event numbers, to append files that both start at 0.",
    )
    parser.add_argument(
        "--no-sample", action="store_true",
        help="Skip the 10%% preview sample table (saves time and disk).",
    )
    parser.add_argument(
        "--direct", action="store_true",
        help=(
            "Always open the database directly. Fails if a server is running, "
            "because DuckDB's file lock is held across processes."
        ),
    )
    parser.add_argument(
        "--server-url", default="",
        help="Base URL of a running server (default: CALOSRV_SERVER_URL).",
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser


def _server_is_running(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def run_delegated(args: argparse.Namespace, base_url: str, source: Path) -> int:
    """Hand the ingest to the running server and follow it to completion."""
    name = naming.validate_experiment_name(args.table)
    fields = {
        "path": str(source),
        "table_name": name,
        "mode": args.mode,
        "display_name": args.display_name or name,
        "event_offset": str(args.event_offset),
    }
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(
        f"{base_url}/api/ingest-local",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    log.info(
        "A server is running at %s and holds the database lock; delegating the "
        "ingest to it. The file is still read in place.", base_url,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            job = json.load(response)["job"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            pass
        log.error("Server rejected the ingest: %s", detail)
        return 2

    job_id = job["job_id"]
    last_stage = ""
    while True:
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(
                f"{base_url}/api/upload/{job_id}", timeout=30
            ) as response:
                job = json.load(response)
        except (urllib.error.URLError, OSError) as exc:
            log.error("Lost contact with the server: %s", exc)
            return 2

        if job["stage_label"] != last_stage:
            last_stage = job["stage_label"]
            log.info("[%s] %s (%.0f%%)", name, last_stage, 100 * job["progress"])

        if job["status"] == "done":
            result = job.get("result", {})
            log.info(
                "Ingest of %r completed: %s hits, %s events",
                name,
                f"{result.get('n_hits', 0):,}",
                f"{result.get('n_events', 0):,}",
            )
            for warning in job.get("warnings", []):
                log.warning("  %s", warning)
            return 0
        if job["status"] == "failed":
            log.error("Ingest failed: %s", job.get("error"))
            return 1


def run(args: argparse.Namespace) -> int:
    source: Path = args.input.expanduser().resolve()
    if not source.is_file():
        log.error("Input file does not exist: %s", source)
        return 2

    name = naming.validate_experiment_name(args.table)
    settings = load_settings()

    log.info(
        "Ingesting %s (%.2f GB) into experiment %r [mode=%s]",
        source.name, source.stat().st_size / 1e9, name, args.mode,
    )

    # DuckDB's lock spans processes, so if the server is up it owns the database
    # and this process cannot open it at all. Delegate rather than fail.
    base_url = (args.server_url or settings.server_url).rstrip("/")
    if not args.direct and _server_is_running(base_url):
        return run_delegated(args, base_url, source)

    database = get_database(settings)
    started = time.monotonic()

    with database.write_lock() as con:
        bootstrap(con)
        existing = registry.get_experiment(con, name)
        record = existing or registry.ExperimentRecord(table_name=name)
        record.display_name = args.display_name or record.display_name or name
        record.status = registry.STATUS_INGESTING
        record.error = None
        if source.name not in record.source_files:
            record.source_files = [*record.source_files, source.name]
        registry.upsert(con, record)

        n_hits = load.load_csv(
            con, name, source, mode=args.mode, event_offset=args.event_offset
        )

        hit_physical = naming.hit_table(name)
        lattice = lattice_fit.measure_lattice(con, hit_physical)
        bounds = lattice_fit.measure_bounds(con, hit_physical)

        # Persist the lattice before the derived tables are verified: the
        # lattice-bounds check reads it back from the registry, and would
        # otherwise skip itself silently on a first ingest.
        record.lattice = lattice
        registry.upsert(con, record)

        derive_proj.build(con, name, lattice)
        n_events = derive_events.build(con, name)
        derive_events.calibration(con, name)
        cell_e_max, cell_e_p999 = derive_proj.measure_color_anchors(
            con, name, lattice.slab_iz
        )

        sample_rows = 0
        if not args.no_sample:
            sample_rows = derive_proj.build_sample(
                con, name, settings.sample_percent
            )

        verification = verify_mod.verify(con, name, source)

        record.n_hits = n_hits
        record.n_events = n_events
        record.n_events_no_d = bounds["n_events_no_d"]
        record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
        record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
        record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
        record.overlaps = bounds["overlaps"]
        record.lattice = lattice
        record.cell_e_max = cell_e_max
        record.cell_e_p999 = cell_e_p999
        record.has_sample = sample_rows > 0
        record.status = (
            registry.STATUS_READY if verification.ok else registry.STATUS_FAILED
        )
        record.error = None if verification.ok else "; ".join(verification.warnings)
        registry.upsert(con, record)

    elapsed = time.monotonic() - started
    log.info(
        "Ingest of %r %s in %.1f s: %s hits, %s events",
        name, "completed" if verification.ok else "FAILED (verification)",
        elapsed, f"{n_hits:,}", f"{n_events:,}",
    )
    for warning in verification.warnings:
        log.warning("  %s", warning)

    # The source file is left in place. It belongs to the host, not to the
    # application, and deleting a user's dataset as a side effect of reading it
    # would be indefensible.
    return 0 if verification.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging("WARNING" if args.quiet else "INFO")
    try:
        return run(args)
    except ApiError as exc:
        log.error("%s: %s", exc.title, exc.detail)
        return 2
    except duckdb.IOException as exc:
        # The most likely cause by far, and the raw DuckDB message does not say
        # what to do about it.
        log.error(
            "Could not open the database: %s\n"
            "A running server holds DuckDB's file lock, and that lock is held "
            "across processes. Either drop --direct so this command delegates "
            "to the running server, or stop the server first "
            "(docker compose stop) and run it again.",
            exc,
        )
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        log.error("Interrupted.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
