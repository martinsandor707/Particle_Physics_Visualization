"""Cut the real-data test files out of the production Parquet file.

Two subcommands, both reading ``ingest/hits_all_models.parquet`` (2.87 GB)
directly - no ingested database is opened. The few per-event facts that pick
the events (overlap, row counts by origin, split cells, all-zero CAM maps) are
computed here with the same expressions the ingest uses
(``calosrv.ingest.derive_events``), then those events' rows are copied out:

``fixture``
    ``hits_all_models_fixture.csv``, a handful of events chosen to exercise
    the cases the two-event demonstration file cannot: split cells, 'A+B'
    rows, an overlap-100 event, events without shower A, an all-zero
    Shap-CAM map and one large event. Read by ``tests/test_ingest_all_models.py``
    and ``tests/test_parquet_ingest.py`` (which compares its CSV and Parquet
    ingests, so it stays CSV).

``subset``
    A production subset - every overlap >= 40 event plus about 250 per
    overlap class 0/10/20/30 - for ``CALOSRV_TEST_SUBSET_CSV``.

Run it alone, as every full-file DuckDB job, under a memory cap:

    systemd-run --user --scope -q -p MemoryMax=14G -p MemorySwapMax=0 \\
        env DUCKDB_MEMORY_GB=10 .venv/bin/python tests/make_all_models_fixture.py fixture

REAL and DOUBLE values written by DuckDB round-trip exactly, and NULL is
written as the empty field the loader reads as NULL.
"""

from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from calosrv.db import ddl  # noqa: E402
from calosrv.db.naming import quote  # noqa: E402
from calosrv.ingest import derive_events  # noqa: E402

SOURCE = REPO / "ingest" / "hits_all_models.parquet"

#: The event-table predicate of each fixture pick, and how many to take.
PICKS = (
    ("E1-E3 overlap 30, >= 100 split cells, no 'A+B'",
     "ovl = 30 AND n_split_cells >= 100 AND n_ab_rows = 0", 3),
    ("E4 A, A+B and B, >= 5 rows", "n_a_rows > 0 AND n_ab_rows > 0 AND n_b_rows > 0 AND n_hits >= 5", 1),
    ("E5 overlap 100 (no shower-A centroid)", "ovl = 100", 1),
    ("E6 A+B and B only, > 1 row", "n_a_rows = 0 AND n_ab_rows > 0 AND n_b_rows > 0 AND n_hits > 1", 1),
    ("E7 A and A+B only", "n_a_rows > 0 AND n_ab_rows > 0 AND n_b_rows = 0", 1),
    ("E8 all-zero energy-network translated Shap-CAM",
     f"(cam_zero_mask & {1 << ddl.cam_bit('energy', 'trans', 'shapcam')}) <> 0", 1),
    ("E9 overlap 10 or 20, >= 500 rows", "ovl IN (10, 20) AND n_hits >= 500", 1),
)


def _hits(source: Path) -> str:
    return f"read_parquet('{str(source).replace(chr(39), chr(39) * 2)}')"


def build_events(con, source: Path) -> None:
    """Temp table ``events`` with the columns the picks below test."""
    hits = _hits(source)
    wanted = ("ovl", "n_hits", "n_a_rows", "n_b_rows", "n_ab_rows", "cam_zero_mask")
    expressions = derive_events.event_expressions()
    aggregate = ", ".join(f"{expressions[c]} AS {c}" for c in wanted)
    con.execute(
        f"""
        CREATE TEMP TABLE events AS
        SELECT m.*, coalesce(c.n_split_cells, 0) AS n_split_cells
        FROM (SELECT event_number, {aggregate} FROM {hits} GROUP BY event_number) m
        LEFT JOIN (
            SELECT event_number, count(*) FILTER (WHERE k > 1) AS n_split_cells
            FROM (SELECT event_number, cellID, count(*) AS k FROM {hits}
                  GROUP BY event_number, cellID)
            GROUP BY event_number
        ) c USING (event_number)
        """
    )


def _write(con, source: Path, events: list[int], out: Path) -> int:
    hits = _hits(source)
    columns = ", ".join(quote(c) for c in ddl.HIT_COLUMN_NAMES)
    listed = ", ".join(str(int(e)) for e in sorted(set(events)))
    escaped = str(out).replace("'", "''")
    con.execute(
        f"COPY (SELECT {columns} FROM {hits} WHERE event_number IN ({listed}) "
        f"ORDER BY event_number) TO '{escaped}' (HEADER, DELIMITER ',')"
    )
    return int(con.execute(
        f"SELECT count(*) FROM {hits} WHERE event_number IN ({listed})").fetchone()[0])


def fixture(con, source: Path, out: Path) -> int:
    event = "events"
    chosen: list[int] = []
    print(f"{'pick':<58} events")
    for label, predicate, count in PICKS:
        rows = con.execute(
            f"SELECT event_number FROM {event} WHERE {predicate} ORDER BY event_number LIMIT {count}"
        ).fetchall()
        if len(rows) < count:
            print(f"unmet: {label}", file=sys.stderr)
            return 1
        picked = [int(r[0]) for r in rows]
        chosen += picked
        print(f"{label:<58} {picked}")
    n = _write(con, source, chosen, out)
    print(f"{len(set(chosen))} events, {n:,} rows -> {out}")
    return 0


def subset(con, source: Path, out: Path, per_class: int) -> int:
    event = "events"
    chosen = [int(r[0]) for r in con.execute(
        f"SELECT event_number FROM {event} WHERE ovl >= 40 ORDER BY event_number").fetchall()]
    for ovl in (0, 10, 20, 30):
        n = int(con.execute(f"SELECT count(*) FROM {event} WHERE ovl = {ovl}").fetchone()[0])
        step = max(1, n // per_class)
        chosen += [int(r[0]) for r in con.execute(
            f"""SELECT event_number FROM (
                    SELECT event_number, row_number() OVER (ORDER BY event_number) AS i
                    FROM {event} WHERE ovl = {ovl})
                WHERE i % {step} = 0 ORDER BY event_number LIMIT {per_class}""").fetchall()]
    rows = _write(con, source, chosen, out)
    print(f"{len(set(chosen)):,} events, {rows:,} rows -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("fixture", "subset"))
    parser.add_argument("--source", type=Path, default=SOURCE, help="the production Parquet file")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--per-class", type=int, default=250)
    args = parser.parse_args(argv)
    out = args.out or (REPO / ("hits_all_models_fixture.csv" if args.command == "fixture"
                               else "data/dev/hits_all_models_subset.csv"))
    if not args.source.is_file():
        print(f"missing {args.source}", file=sys.stderr)
        return 1
    started = time.perf_counter()
    temp = REPO / "data" / "dev" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('DUCKDB_MEMORY_GB', '4')}GB'")
    con.execute(f"SET temp_directory = '{temp}'")
    build_events(con, args.source)
    code = (fixture(con, args.source, out) if args.command == "fixture"
            else subset(con, args.source, out, args.per_class))
    print(f"{time.perf_counter() - started:.1f} s, peak RSS "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
    return code


if __name__ == "__main__":
    sys.exit(main())
