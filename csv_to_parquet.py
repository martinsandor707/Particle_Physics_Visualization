#!/usr/bin/env python3
"""Convert a CSV file to Parquet: zstd level 3, row groups of 100 000 rows.

    python csv_to_parquet.py --input ingest/hits_all_models.csv
    python csv_to_parquet.py --input data.csv --output out/data.parquet

A CSV whose header is exactly the 99-column ``hits_all_models`` schema is read
with the ingest pipeline's pinned column types (``calosrv/ingest/csv_spec.py``),
never by DuckDB's type sniffer, which samples only the start of the file. The
Parquet file then carries the server archive's types: ``energy`` DOUBLE, every
coordinate, kinematic and model column REAL, as ``calosrv/db/ddl.py`` defends.
Any other CSV is typed by the sniffer, and a later value that does not fit a
sniffed type aborts the conversion rather than being coerced.

The CSV's row order is kept, so each row group holds a contiguous run of events
and its ``event_number`` min/max statistics stay useful for pruning. DuckDB
streams the file under ``--memory-limit``, spilling to ``<output>.spill`` beside
the output. The file is written as ``<output>.tmp`` and renamed only when
complete, so an interrupted run never leaves a truncated ``.parquet`` - which
the ``ingest/`` drop folder would otherwise find.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import duckdb

from calosrv.db.ddl import HIT_COLUMN_NAMES, SCHEMA_NAME
from calosrv.ingest.csv_spec import read_csv_expression

ROW_GROUP_SIZE = 100_000
COMPRESSION_LEVEL = 3  # zstd

#: DuckDB's own default is 80% of RAM. The conversion streams, so it needs far
#: less; a tighter limit only makes it slower.
DEFAULT_MEMORY_LIMIT = "8GB"


def quoted(value: object) -> str:
    """A SQL string literal. DuckDB cannot bind a file path in COPY or SET."""
    return "'" + str(value).replace("'", "''") + "'"


def has_hits_header(path: Path) -> bool:
    """Whether the header is exactly the pinned ``hits_all_models`` column list."""
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        header = next(csv.reader(handle), [])
    return tuple(name.strip() for name in header) == HIT_COLUMN_NAMES


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", "-i", type=Path, required=True, help="CSV file to convert.")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Parquet file to write (default: the input with a .parquet suffix).",
    )
    parser.add_argument(
        "--memory-limit", default=DEFAULT_MEMORY_LIMIT,
        help=f"DuckDB memory limit (default: {DEFAULT_MEMORY_LIMIT}).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    args = parser.parse_args(argv)

    args.output = args.output or args.input.with_suffix(".parquet")
    if not args.input.is_file():
        parser.error(f"{args.input} is not a file")
    if args.output.resolve() == args.input.resolve():
        parser.error("the output path is the input file")
    if args.output.exists() and not args.force:
        parser.error(f"{args.output} already exists; pass --force to overwrite it")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source, target = args.input, args.output

    if has_hits_header(source):
        relation = read_csv_expression(source)
        typing = f"the pinned {SCHEMA_NAME} column types"
    else:
        relation = f"read_csv({quoted(source)})"
        typing = f"column types sniffed by DuckDB (not a {SCHEMA_NAME} header)"
    # Flushed, so a redirected log shows it before a long conversion, not after.
    print(f"Reading {source} with {typing}.", flush=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".tmp")
    con = duckdb.connect()
    con.execute(f"SET memory_limit = {quoted(args.memory_limit)}")
    con.execute(f"SET temp_directory = {quoted(target.with_name(target.name + '.spill'))}")
    if sys.stdout.isatty():
        # Worth having on a 24 GB file; control characters in a redirected log are not.
        con.execute("SET enable_progress_bar = true")

    start = time.perf_counter()
    try:
        (rows,) = con.execute(
            f"COPY (SELECT * FROM {relation}) TO {quoted(partial)} (FORMAT parquet, "
            f"COMPRESSION zstd, COMPRESSION_LEVEL {COMPRESSION_LEVEL}, "
            f"ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
        ).fetchone()
        (groups,) = con.execute(
            f"SELECT num_row_groups FROM parquet_file_metadata({quoted(partial)})"
        ).fetchone()
        partial.replace(target)
    except duckdb.Error as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()  # DuckDB removes the spill directory it created
        partial.unlink(missing_ok=True)

    size = target.stat().st_size
    print(
        f"Wrote {rows:,} rows in {groups:,} row group(s) to {target} "
        f"({size / 1e6:,.1f} MB, {size / source.stat().st_size:.1%} of the CSV) "
        f"in {time.perf_counter() - start:,.1f} s."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
