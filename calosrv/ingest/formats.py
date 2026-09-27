"""Which format a source file is, and the one place the ingest branches on it.

The pipeline reads a CSV or a Parquet file into the same archive, and past the
archive nothing knows or cares which it was. Everything that does differ - how
the columns are checked, the SELECT that reads them, how the source's rows are
counted, how much disk the ingest needs - is dispatched here, so another format
would be one more branch in this module rather than a hunt through the pipeline.

The format is decided by the file's content, not its name. A staged upload used
to be renamed ``.csv`` whatever it was, a Parquet export may be misnamed, and a
Parquet file still being copied has no footer yet: the magic bytes tell these
apart where a suffix cannot.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from ..config import Settings
from ..errors import IngestError
from . import csv_spec, parquet_spec
from .source_check import SourceCheck

CSV = "csv"
PARQUET = "parquet"
FORMATS = (CSV, PARQUET)

#: The suffixes a source may carry, lower-case, and the format each implies. An
#: empty suffix has always meant CSV; the content decides either way.
SUFFIXES: dict[str, str] = {".csv": CSV, ".txt": CSV, "": CSV, ".parquet": PARQUET}

#: A Parquet file begins and ends with these four bytes.
PARQUET_MAGIC = b"PAR1"
_GZIP_MAGIC = b"\x1f\x8b"
_ZIP_MAGIC = b"PK\x03\x04"


def format_of_name(name: str) -> str | None:
    """The format a file name implies, or None for an unsupported suffix."""
    return SUFFIXES.get(Path(name).suffix.lower())


def detect_format(path: Path) -> str:
    """``csv`` or ``parquet``, from the file's first and last bytes.

    Raises ``IngestError`` for a compressed file, a truncated Parquet file (the
    footer is written last, so a file still being copied has none) and a file
    named ``.parquet`` that is not one.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(4)
            tail = b""
            if size >= 8:
                handle.seek(-4, os.SEEK_END)
                tail = handle.read(4)
    except OSError as exc:
        raise IngestError(f"Could not read {path.name}: {exc}") from exc

    if head == PARQUET_MAGIC:
        if tail != PARQUET_MAGIC:
            raise IngestError(
                f"{path.name} begins like a Parquet file but has no footer: it is "
                "truncated, or still being copied."
            )
        return PARQUET
    if head.startswith(_GZIP_MAGIC):
        raise IngestError(
            f"{path.name} is gzip-compressed. Decompress it first; the ingest reads "
            "plain CSV or Parquet."
        )
    if head == _ZIP_MAGIC:
        raise IngestError(f"{path.name} is a zip archive. Extract the CSV or Parquet file first.")
    if path.suffix.lower() == ".parquet":
        raise IngestError(f"{path.name} is named .parquet but is not a Parquet file.")
    return CSV


def validate(con: duckdb.DuckDBPyConnection, path: Path, fmt: str) -> SourceCheck:
    """Check a source against the input schema; raises ``IngestError`` if it does not fit."""
    if fmt == PARQUET:
        return parquet_spec.validate(con, path)
    csv_spec.validate_header(path)
    return SourceCheck(format=CSV)


def select_sql(path: Path, fmt: str, event_offset: int = 0,
               check: SourceCheck | None = None) -> str:
    """The SELECT that reads every column of the source, typed as the archive stores it."""
    if fmt == PARQUET:
        return parquet_spec.select_sql(path, event_offset, check)
    return csv_spec.select_sql(path, event_offset)


def count_rows(con: duckdb.DuckDBPyConnection, path: Path, fmt: str) -> int:
    """Data rows in the source: a newline count for a CSV, the footer for Parquet."""
    if fmt == PARQUET:
        return parquet_spec.count_rows(con, path)
    return csv_spec.count_data_rows(path)


def headroom_factor(settings: Settings, fmt: str, staged: bool) -> float:
    """Free disk needed, as a multiple of the source's size.

    A CSV compresses about eightfold into the archive, so the derived data are
    a fraction of it. A Parquet source is already compressed: the archive comes
    out near its size and the database near it again. A staged upload adds one
    more copy of the source for as long as the ingest runs.
    """
    if fmt == PARQUET:
        return settings.parquet_headroom_factor + (1.0 if staged else 0.0)
    return settings.disk_headroom_factor if staged else settings.local_headroom_factor
