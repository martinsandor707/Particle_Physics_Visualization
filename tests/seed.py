"""The two-event demonstration file every booted test seeds from, and its rows as text.

``hits_all_models_dummy.parquet`` at the repository root is the image's seed
(Dockerfile) and the suite's: the same 1,000 rows as ``ingest/``'s copy, kept in
git so a fresh clone builds and tests before the data are downloaded. It replaced
the CSV of the same name; its coordinate, momentum and network columns are float32.

:func:`rows` reads it as the CSV module once read the CSV - a header and lists
of strings - for the fixture generators that copy template rows verbatim. A
float is written with ``repr`` of its exact double value, so a float32 column
round-trips to the same float32 and a DOUBLE column to the same double; the
CSV :func:`csv_copy` writes therefore ingests to exactly what the Parquet does.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
SEED_FILE = REPO / "hits_all_models_dummy.parquet"

#: The same rows as CSV, for the tests of the CSV reader: written on first use
#: under the git-ignored data folder, never committed.
CSV_COPY = REPO / "data" / "dev" / "test-seed" / "hits_all_models_dummy.csv"


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def rows(path: Path = SEED_FILE) -> tuple[list[str], list[list[str]]]:
    """``(header, rows)`` of a Parquet file, every value as text, in file order."""
    con = duckdb.connect()
    try:
        cursor = con.execute(f"SELECT * FROM read_parquet('{Path(path).as_posix()}')")
        header = [d[0] for d in cursor.description]
        body = [[_text(v) for v in record] for record in cursor.fetchall()]
    finally:
        con.close()
    return header, body


def csv_copy(path: Path = SEED_FILE, out: Path = CSV_COPY) -> Path:
    """The Parquet file written as CSV with :func:`rows`' text, rewritten when the Parquet is newer.

    Written to a private name and renamed into place, so two test processes
    starting at once never read a half-written file.
    """
    if out.is_file() and out.stat().st_mtime >= Path(path).stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    header, body = rows(path)
    part = out.with_name(f"{out.name}.{os.getpid()}.part")
    with part.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(body)
    part.replace(out)
    return out
