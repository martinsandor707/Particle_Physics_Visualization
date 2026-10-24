"""Cut the single-shower real-data test files out of the two electron sources.

Writes, at the repository root (``*.csv`` is git-ignored):

``electron_hits_fixture.csv``
    Every hit row of the picked events, from
    ``electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.csv``.
``electron_events_fixture.csv``
    The same events' rows of the producer's aggregate,
    ``electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv`` - which
    has no row for a single-hit event, so those are picked on purpose.

Picks: every event with ``event_number % 500`` in {3, 250} (about 400 events,
every momentum bin), the five lowest-numbered single-hit events, and the
event with the most hits. Rows are copied as text, never re-formatted, so the
cut carries the producer's exact numbers and the feature-parity test compares
like with like. Read by ``tests/test_single_shower_ingest.py``, which skips
when the files are absent.

Run it alone, as every full-file DuckDB job, under a memory cap:

    systemd-run --user --scope -p MemoryMax=14G -p MemorySwapMax=0 \\
        env DUCKDB_MEMORY_GB=10 .venv/bin/python tests/make_single_shower_fixture.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
HITS_SOURCE = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.csv"
EVENTS_SOURCE = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv"
HITS_FIXTURE = REPO / "electron_hits_fixture.csv"
EVENTS_FIXTURE = REPO / "electron_events_fixture.csv"


def _text(path: Path) -> str:
    escaped = str(path).replace("'", "''")
    return f"read_csv('{escaped}', header = true, all_varchar = true)"


def main() -> int:
    for source in (HITS_SOURCE, EVENTS_SOURCE):
        if not source.is_file():
            print(f"missing {source}", file=sys.stderr)
            return 1
    temp = REPO / "data" / "dev" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('DUCKDB_MEMORY_GB', '4')}GB'")
    con.execute(f"SET temp_directory = '{temp}'")
    started = time.perf_counter()

    con.execute(
        f"""
        CREATE TEMP TABLE counts AS
        SELECT CAST(event_number AS INTEGER) AS e, count(*) AS n
        FROM {_text(HITS_SOURCE)} GROUP BY 1
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE picked AS
        SELECT e FROM counts WHERE e % 500 IN (3, 250)
        UNION SELECT e FROM (SELECT e FROM counts WHERE n = 1 ORDER BY e LIMIT 5)
        UNION SELECT e FROM (SELECT e FROM counts ORDER BY n DESC, e LIMIT 1)
        """
    )
    n_events = con.execute("SELECT count(*) FROM picked").fetchone()[0]

    con.execute(
        f"""
        COPY (
            SELECT h.* FROM {_text(HITS_SOURCE)} h
            JOIN picked p ON CAST(h.event_number AS INTEGER) = p.e
            ORDER BY CAST(h.event_number AS INTEGER), CAST(h.cellID AS BIGINT)
        ) TO '{HITS_FIXTURE}' (FORMAT csv, HEADER true, QUOTE '"')
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT a.* FROM {_text(EVENTS_SOURCE)} a
            JOIN picked p ON CAST(a.event_id AS INTEGER) = p.e
            ORDER BY CAST(a.event_id AS INTEGER)
        ) TO '{EVENTS_FIXTURE}' (FORMAT csv, HEADER true, QUOTE '"')
        """
    )
    n_hits = con.execute(f"SELECT count(*) FROM {_text(HITS_FIXTURE)}").fetchone()[0]
    n_rows = con.execute(f"SELECT count(*) FROM {_text(EVENTS_FIXTURE)}").fetchone()[0]
    print(f"{n_events} events: {n_hits:,} hit rows -> {HITS_FIXTURE.name}, "
          f"{n_rows} aggregate rows -> {EVENTS_FIXTURE.name} "
          f"({time.perf_counter() - started:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
