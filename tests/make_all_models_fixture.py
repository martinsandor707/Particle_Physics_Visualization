"""Cut the real-data test files out of an ingested production archive.

Two subcommands, both reading an experiment that has already been ingested
(its event table picks the events; its Parquet archive supplies their rows),
so neither re-reads the 24 GB CSV:

``fixture``
    ``hits_all_models_fixture.csv``, a handful of events chosen to exercise
    the cases the two-event demonstration file cannot: split cells, 'A+B'
    rows, an overlap-100 event, events without shower A, an all-zero
    Shap-CAM map and one large event. Read by ``tests/test_ingest_all_models.py``.

``subset``
    A production subset - every overlap >= 40 event plus about 250 per
    overlap class 0/10/20/30 - for ``CALOSRV_TEST_SUBSET_CSV``.

Run it alone, as every full-dataset DuckDB job (nothing else holding the
database), with an explicit memory limit:

    CALOSRV_DATA_DIR=$PWD/data/dev/full .venv/bin/python tests/make_all_models_fixture.py fixture
    CALOSRV_DATA_DIR=$PWD/data/dev/full .venv/bin/python tests/make_all_models_fixture.py subset \\
        --out data/dev/hits_all_models_subset.csv

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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("DUCKDB_MEMORY_GB", "4")

from calosrv.config import load_settings  # noqa: E402
from calosrv.db import archive, ddl, naming, registry  # noqa: E402
from calosrv.db.connection import get_database  # noqa: E402
from calosrv.db.naming import quote  # noqa: E402

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


def _write(con, settings, table: str, events: list[int], out: Path) -> int:
    hits = archive.relation(settings, table)
    columns = ", ".join(quote(c) for c in ddl.HIT_COLUMN_NAMES)
    listed = ", ".join(str(int(e)) for e in sorted(set(events)))
    escaped = str(out).replace("'", "''")
    con.execute(
        f"COPY (SELECT {columns} FROM {hits} WHERE event_number IN ({listed}) "
        f"ORDER BY event_number) TO '{escaped}' (HEADER, DELIMITER ',')"
    )
    return int(con.execute(
        f"SELECT count(*) FROM {hits} WHERE event_number IN ({listed})").fetchone()[0])


def fixture(con, settings, table: str, out: Path) -> int:
    event = quote(naming.event_table(table))
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
    n = _write(con, settings, table, chosen, out)
    print(f"{len(set(chosen))} events, {n:,} rows -> {out}")
    return 0


def subset(con, settings, table: str, out: Path, per_class: int) -> int:
    event = quote(naming.event_table(table))
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
    rows = _write(con, settings, table, chosen, out)
    print(f"{len(set(chosen)):,} events, {rows:,} rows -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("fixture", "subset"))
    parser.add_argument("--table", default="all_models", help="the ingested production experiment")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--per-class", type=int, default=250)
    args = parser.parse_args(argv)
    out = args.out or (REPO / ("hits_all_models_fixture.csv" if args.command == "fixture"
                               else "data/dev/hits_all_models_subset.csv"))
    started = time.perf_counter()
    settings = load_settings()
    database = get_database(settings)
    with database.read_cursor() as con:
        registry.require_ready(con, args.table)
        code = (fixture(con, settings, args.table, out) if args.command == "fixture"
                else subset(con, settings, args.table, out, args.per_class))
    print(f"{time.perf_counter() - started:.1f} s, peak RSS "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
    return code


if __name__ == "__main__":
    sys.exit(main())
