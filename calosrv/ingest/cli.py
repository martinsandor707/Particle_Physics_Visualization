"""``python -m calosrv.ingest`` - ingest a CSV or Parquet file without pushing it through HTTP.

The upload endpoint accepts files of any size, but sending 24 GB from a browser
is slow, unresumable and easy to interrupt. For datasets already on the host -
the normal in-house case - this reads the file in place.

    docker compose exec calorimeter-dashboard \\
        python -m calosrv.ingest --input /app/host/hits_all_models.csv \\
                                 --table all_models

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
from ..db import naming
from ..db.bootstrap import bootstrap
from ..db.connection import get_database
from ..errors import ApiError
from ..logging_setup import configure_logging
from . import load, pipeline

log = logging.getLogger("calosrv.ingest.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m calosrv.ingest",
        description="Ingest a calorimeter inference CSV or Parquet file into the DuckDB store.",
    )
    parser.add_argument(
        "--input", "-i", type=Path, default=None,
        help="Path to the CSV or Parquet file to ingest (not needed with --rebuild).",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help=(
            "Re-derive every table of --table from its Parquet archive, reading no "
            "source file, in one transaction: committed only if it verifies. With a "
            "server running, the rebuild is handed to it."
        ),
    )
    parser.add_argument(
        "--compare-features", nargs=2, metavar=("HITS", "EVENTS"), default=None,
        help=(
            "Compare the features rebuilt from a single-shower hit experiment with an "
            "aggregated experiment's, event by event (direct mode). Exit 0 when every "
            "feature agrees to 1e-9."
        ),
    )
    parser.add_argument(
        "--table", "-t", default=None,
        help="Target experiment name (lowercase letters, digits, underscores).",
    )
    parser.add_argument(
        "--mode", "-m", choices=(load.MODE_CREATE_NEW, load.MODE_APPEND),
        default=load.MODE_CREATE_NEW,
        help=(
            "create_new makes a new experiment (an existing one of this name needs "
            "--force-reingest); append adds to an existing one."
        ),
    )
    parser.add_argument(
        "--force-reingest", action="store_true",
        help=(
            "With create_new, replace an existing experiment of this name. It is "
            "deleted before the new file is loaded, and not restored if that fails."
        ),
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


def _post(url: str, fields: dict[str, str] | None = None) -> tuple[dict | None, str | None]:
    """POST a form (or nothing) and parse the JSON body; ``(None, detail)`` on an HTTP error."""
    body = urllib.parse.urlencode(fields or {}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            pass
        return None, detail


def _follow(base_url: str, job: dict, name: str, verb: str = "Ingest") -> int:
    """Poll a job on the server until it finishes; the CLI's exit code."""
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
                "%s of %r completed: %s hits, %s events", verb, name,
                f"{result.get('n_hits', 0):,}", f"{result.get('n_events', 0):,}",
            )
            for warning in job.get("warnings", []):
                log.warning("  %s", warning)
            return 0
        if job["status"] == "failed":
            log.error("%s failed: %s", verb, job.get("error"))
            return 1


def run_rebuild_delegated(base_url: str, name: str) -> int:
    """Hand a rebuild to the running server and follow it to completion."""
    log.info("A server is running at %s; handing the rebuild of %r to it.", base_url, name)
    body, detail = _post(f"{base_url}/api/admin/experiments/{urllib.parse.quote(name)}/rebuild")
    if body is None:
        log.error("Server rejected the rebuild: %s", detail)
        return 2
    return _follow(base_url, body["job"], name, verb="Rebuild")


def run_compare(args: argparse.Namespace) -> int:
    """``--compare-features HITS EVENTS``, in direct mode."""
    from . import feature_parity

    hits, events = (naming.validate_experiment_name(n) for n in args.compare_features)
    settings = load_settings()
    database = get_database(settings)
    with database.read_cursor() as con:
        report = feature_parity.compare(con, hits, events)
    log.info("%s shared events, %s only in %s, %s only in %s", f"{report.n_shared:,}",
             f"{report.n_hits_only:,}", hits, f"{report.n_events_only:,}", events)
    log.info("Base columns equal: %s; deposited energy max relative difference %.3g",
             ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in report.base_equal.items()),
             report.energy_max_rel or 0.0)
    for column, rel in sorted(report.max_rel.items(), key=lambda kv: -kv[1]):
        log.info("  %-28s max rel %.3g (event %d)", column, rel, report.worst_event[column])
    log.info("Feature parity %s (tolerance %.0e)", "PASSED" if report.ok else "FAILED",
             report.tolerance)
    return 0 if report.ok else 1


def run_delegated(args: argparse.Namespace, base_url: str, source: Path) -> int:
    """Hand the ingest to the running server and follow it to completion."""
    name = naming.validate_experiment_name(args.table)
    fields = {
        "path": str(source),
        "table_name": name,
        "mode": args.mode,
        "display_name": args.display_name or name,
        "event_offset": str(args.event_offset),
        "force_reingest": "true" if args.force_reingest else "false",
    }
    log.info(
        "A server is running at %s and holds the database lock; delegating the "
        "ingest to it. The file is still read in place.", base_url,
    )
    body, detail = _post(f"{base_url}/api/ingest-local", fields)
    if body is None:
        log.error("Server rejected the ingest: %s", detail)
        return 2
    return _follow(base_url, body["job"], name)


def _report(name: str, result: pipeline.IngestResult, elapsed: float) -> int:
    schema = result.record.schema
    if schema is not None and not schema.kind.endswith("_hits"):
        content = f"{result.n_events:,} events ({schema.n_columns} event-level columns each)"
    else:
        content = f"{result.n_hits:,} hits, {result.n_events:,} events"
    log.info(
        "Ingest of %r (%s) %s in %.1f s: %s, archive %s rows in %d part(s)",
        name, schema.label if schema else "unknown schema",
        "completed" if result.ok else "FAILED (verification)",
        elapsed, content, f"{result.record.archive_rows:,}", result.record.archive_parts,
    )
    for stage in result.timings:
        log.info("  %-10s %7.1f s  peak RSS %8.0f MB  DuckDB %8s MB  spill %8s MB",
                 stage["stage"], stage["seconds"], stage["peak_rss_mb"],
                 stage["duckdb_memory_mb"], stage["spill_mb"])
    for warning in result.warnings:
        log.warning("  %s", warning)
    return 0 if result.ok else 1


def run(args: argparse.Namespace) -> int:
    if args.compare_features:
        return run_compare(args)
    if not args.table:
        log.error("--table is required.")
        return 2
    name = naming.validate_experiment_name(args.table)
    settings = load_settings()

    if args.rebuild:
        if args.input is not None:
            log.error("--rebuild reads the archive; do not pass --input with it.")
            return 2
        base_url = (args.server_url or settings.server_url).rstrip("/")
        if not args.direct and _server_is_running(base_url):
            return run_rebuild_delegated(base_url, name)
        database = get_database(settings)
        started = time.monotonic()
        with database.write_lock() as con:
            bootstrap(con, settings)
            result = pipeline.rebuild_atomic(con, settings, name, build_sample=not args.no_sample)
        if not result.ok:
            log.error("The rebuild failed verification and was rolled back; %r is unchanged.",
                      name)
        return _report(name, result, time.monotonic() - started)

    if args.input is None:
        log.error("--input is required unless --rebuild is given.")
        return 2
    source: Path = args.input.expanduser().resolve()
    if not source.is_file():
        log.error("Input file does not exist: %s", source)
        return 2

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
        bootstrap(con, settings)
        result = pipeline.run_ingest(
            con, settings, name, source,
            mode=args.mode,
            event_offset=args.event_offset,
            display_name=args.display_name,
            build_sample=not args.no_sample,
            force_reingest=args.force_reingest,
        )

    # The source file is left in place. It belongs to the host, not to the
    # application, and deleting a user's dataset as a side effect of reading it
    # would be indefensible.
    return _report(name, result, time.monotonic() - started)


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
