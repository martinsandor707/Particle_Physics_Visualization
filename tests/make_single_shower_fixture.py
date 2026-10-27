"""Cut the single-shower real-data test files out of the two electron Parquet sources.

Writes, at the repository root (``*.parquet`` is git-ignored):

``electron_hits_fixture.parquet``
    Every hit row of the picked events, from the ingested archive of the
    producer's hit file, ``data/dev/single/archive/electron_s1_hits/*.parquet``
    (the original ``electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.csv``
    is gone; the archive holds its 21 columns as ingested).
``electron_events_fixture.parquet``
    The same events' rows of the producer's aggregate,
    ``ingest/electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet`` -
    which has no row for a single-hit event, so those are picked on purpose.
``electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3_head.parquet`` and
``electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3_head.parquet``
    The first 20 rows of each source, read by ``tests/test_schemas.py`` to pin
    the producer's exact column names.

Picks: every event with ``event_number % 500`` in {3, 250} (about 400 events,
every momentum bin), the five lowest-numbered single-hit events, and the
event with the most hits. Rows are copied Parquet to Parquet, with the same
column names and types and no re-formatting, so the cut carries the
producer's exact numbers and the feature-parity test compares like with like.
Read by ``tests/test_single_shower_ingest.py``, which skips when the files
are absent.

Run it alone, as every full-file DuckDB job, under a memory cap:

    systemd-run --user --scope -q -p MemoryMax=14G -p MemorySwapMax=0 \\
        env DUCKDB_MEMORY_GB=10 .venv/bin/python tests/make_single_shower_fixture.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
HITS_SOURCE = REPO / "data" / "dev" / "single" / "archive" / "electron_s1_hits" / "*.parquet"
EVENTS_SOURCE = (REPO / "ingest"
                 / "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet")
HITS_FIXTURE = REPO / "electron_hits_fixture.parquet"
EVENTS_FIXTURE = REPO / "electron_events_fixture.parquet"
HITS_HEAD = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3_head.parquet"
EVENTS_HEAD = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3_head.parquet"
HEAD_ROWS = 20


def _pq(path: Path) -> str:
    escaped = str(path).replace("'", "''")
    return f"read_parquet('{escaped}')"


def _copy(con, query: str, target: Path) -> None:
    escaped = str(target).replace("'", "''")
    con.execute(f"COPY ({query}) TO '{escaped}' (FORMAT parquet, COMPRESSION zstd)")


def main() -> int:
    if not list(HITS_SOURCE.parent.glob(HITS_SOURCE.name)):
        print(f"missing {HITS_SOURCE}", file=sys.stderr)
        return 1
    if not EVENTS_SOURCE.is_file():
        print(f"missing {EVENTS_SOURCE}", file=sys.stderr)
        return 1
    temp = REPO / "data" / "dev" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('DUCKDB_MEMORY_GB', '4')}GB'")
    con.execute(f"SET temp_directory = '{temp}'")
    started = time.perf_counter()
    hits, events = _pq(HITS_SOURCE), _pq(EVENTS_SOURCE)

    con.execute(f"CREATE TEMP TABLE counts AS SELECT event_number AS e, count(*) AS n FROM {hits} GROUP BY 1")
    con.execute(
        """
        CREATE TEMP TABLE picked AS
        SELECT e FROM counts WHERE e % 500 IN (3, 250)
        UNION SELECT e FROM (SELECT e FROM counts WHERE n = 1 ORDER BY e LIMIT 5)
        UNION SELECT e FROM (SELECT e FROM counts ORDER BY n DESC, e LIMIT 1)
        """
    )
    n_events = con.execute("SELECT count(*) FROM picked").fetchone()[0]

    _copy(con, f"SELECT h.* FROM {hits} h JOIN picked p ON h.event_number = p.e "
               "ORDER BY h.event_number, h.cellID", HITS_FIXTURE)
    _copy(con, f"SELECT a.* FROM {events} a JOIN picked p ON a.event_id = p.e "
               "ORDER BY a.event_id", EVENTS_FIXTURE)
    _copy(con, f"SELECT * FROM {hits} LIMIT {HEAD_ROWS}", HITS_HEAD)
    _copy(con, f"SELECT * FROM {events} ORDER BY event_id LIMIT {HEAD_ROWS}", EVENTS_HEAD)
    n_hits = con.execute(f"SELECT count(*) FROM {_pq(HITS_FIXTURE)}").fetchone()[0]
    n_rows = con.execute(f"SELECT count(*) FROM {_pq(EVENTS_FIXTURE)}").fetchone()[0]
    print(f"{n_events} events: {n_hits:,} hit rows -> {HITS_FIXTURE.name}, "
          f"{n_rows} aggregate rows -> {EVENTS_FIXTURE.name}, "
          f"{HEAD_ROWS}-row heads -> {HITS_HEAD.name}, {EVENTS_HEAD.name} "
          f"({time.perf_counter() - started:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
