"""The frozen CSV reader specification.

DuckDB's ``read_csv_auto`` is deliberately *not* used, and the reason is
specific to this dataset rather than general caution.

The type sniffer samples a prefix of the file. In ``hits_all_models.csv`` the
leading gigabytes are entirely ``overlap = 0`` - the well-separated population -
and that region contains **no empty ``centroid_A_*`` fields**. The empty strings
only appear in the 57 events with no shower-A hit at all, every one of them at
``overlap >= 30``, deep in the file. A sniffer would therefore type those
columns from a sample that never exhibits the failure mode, and the first empty
field encountered would either abort the load or silently coerce.

So the column types are pinned, ``nullstr`` is set explicitly, and errors are
fatal rather than ignored.

Every accepted input schema (``db/schemas.py``) is read the same way: the
header decides which one a file is, by exact match, and that schema's pinned
types drive the reader. An empty field is NULL in every schema - an undefined
separation in ``hits_all_models``, no parent or no daughters in the species
columns of ``standalone_hits``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..db import schemas
from ..db.naming import quote
from ..db.schemas import InputSchema
from ..errors import IngestError

#: What an empty field means in this dataset.
#:
#: On the production file 98 rows in 57 events carry an empty string for every
#: ``centroid_A_*`` column (laboratory, ``_trans`` and ``_local``) and for all
#: three ``centroid_AB_distance*`` columns. These are degenerate events with no
#: hit attributed to shower A, so no A centroid exists and the A-B separation
#: is undefined. The emptiness is a property of the *event*, not of individual
#: rows: an affected event has the fields empty on every one of its rows.
NULL_STRING = ""


def columns_clause(schema: InputSchema = schemas.DEFAULT) -> str:
    """The ``columns = {...}`` argument for ``read_csv``."""
    entries = ", ".join(f"'{name}': '{sql_type}'" for name, sql_type in schema.columns)
    return "{" + entries + "}"


def read_csv_expression(path: Path, schema: InputSchema = schemas.DEFAULT) -> str:
    """A ``read_csv`` table function call with every option pinned.

    ``ignore_errors = false`` is the important one. A silently dropped row in a
    physics dataset is a silently wrong result downstream, and there is no
    indication in the output that it happened.
    """
    escaped = str(path).replace("'", "''")
    return (
        f"read_csv('{escaped}', "
        "header = true, "
        "delim = ',', "
        f"nullstr = '{NULL_STRING}', "
        "ignore_errors = false, "
        "parallel = true, "
        f"columns = {columns_clause(schema)})"
    )


def select_sql(path: Path, event_offset: int = 0,
               schema: InputSchema = schemas.DEFAULT) -> str:
    """Every column in file order, typed by the pinned reader.

    The offset shifts the schema's event key. A schema with an archive order
    writes its part sorted by it, so each row group holds whole, contiguous
    events and a CSV- and a Parquet-sourced part agree row for row.
    """
    key = schema.event_key
    sql_type = schema.types[key]
    projected = ", ".join(
        # Cast back to the pinned type: an offset that overflows it is an
        # error here, not an INT64 part beside INT32 ones.
        f"CAST({quote(c)} + {int(event_offset)} AS {sql_type}) AS {quote(c)}"
        if c == key and event_offset
        else quote(c)
        for c in schema.names
    )
    order = (" ORDER BY " + ", ".join(quote(c) for c in schema.archive_order)
             if schema.archive_order else "")
    return f"SELECT {projected} FROM {read_csv_expression(path, schema)}{order}"


def read_header(path: Path) -> tuple[str, ...]:
    """The CSV's first record, stripped."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
    except OSError as exc:
        raise IngestError(f"Could not read {path.name}: {exc}") from exc
    except UnicodeDecodeError as exc:
        # A binary file - compressed, or some other format - read as text. Left
        # unhandled this escaped as a bare 500 instead of saying what is wrong.
        raise IngestError(
            f"{path.name} is not a UTF-8 text CSV (byte {exc.start} cannot be decoded). "
            "Compressed files must be decompressed first."
        ) from exc
    if header is None:
        raise IngestError(f"{path.name} is empty.")
    return tuple(name.strip() for name in header)


def validate_header(path: Path) -> InputSchema:
    """The accepted schema whose columns the CSV header is, in order.

    Failing here costs a few milliseconds and produces a message naming the
    offending column. Failing inside ``read_csv`` on a 24 GB file costs minutes
    and produces a parser error about a row number. Same names in another order
    are refused too: the pinned ``columns`` map is positional, so loading such
    a file would put y values into the x column.
    """
    return schemas.detect_header(path.name, read_header(path))


def count_data_rows(path: Path) -> int:
    """Count data rows (lines minus the header) by streaming the file.

    Used by ``verify`` to confirm that every row of the source reached the
    database. Reads in binary blocks rather than line by line, which matters on
    a multi-gigabyte file.
    """
    newlines = 0
    trailing_newline = True
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            newlines += chunk.count(b"\n")
            trailing_newline = chunk.endswith(b"\n")
    # A file not ending in a newline still has a final record.
    total_lines = newlines + (0 if trailing_newline else 1)
    return max(0, total_lines - 1)
