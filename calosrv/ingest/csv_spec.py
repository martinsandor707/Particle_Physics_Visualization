"""The frozen CSV reader specification.

DuckDB's ``read_csv_auto`` is deliberately *not* used, and the reason is
specific to this dataset rather than general caution.

The type sniffer samples a prefix of the file. In ``hits_with_gradcam_v37.csv``
the first two gigabytes are entirely ``overlap = 0`` - the well-separated
population - and that region contains **no empty ``centroid_A_*`` fields**. The
empty strings only begin once ``overlap >= 30``, hundreds of millions of rows
later. A sniffer would therefore type those four columns from a sample that
never exhibits the failure mode, and the first empty field encountered would
either abort the load or silently coerce.

So the column types are pinned, ``nullstr`` is set explicitly, and errors are
fatal rather than ignored.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..db.ddl import HIT_COLUMNS, HIT_COLUMN_NAMES
from ..errors import IngestError

#: What an empty field means in this dataset.
#:
#: Roughly 0.11% of rows carry an empty string for ``centroid_A_x``,
#: ``centroid_A_y``, ``centroid_A_z`` and ``centroid_AB_distance``. These are
#: degenerate events in which shower A deposited no energy at all, so no A
#: centroid exists and the A-B separation is undefined. The emptiness is a
#: property of the *event*, not of individual rows: an affected event has the
#: field empty on every one of its rows.
NULL_STRING = ""


def columns_clause() -> str:
    """The ``columns = {...}`` argument for ``read_csv``."""
    entries = ", ".join(f"'{name}': '{sql_type}'" for name, sql_type in HIT_COLUMNS)
    return "{" + entries + "}"


def read_csv_expression(path: Path) -> str:
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
        f"columns = {columns_clause()})"
    )


def validate_header(path: Path) -> None:
    """Check the CSV header against the expected 29 columns before loading.

    Failing here costs a few milliseconds and produces a message naming the
    offending column. Failing inside ``read_csv`` on a 7.4 GB file costs minutes
    and produces a parser error about a row number.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
    except OSError as exc:
        raise IngestError(f"Could not read {path.name}: {exc}") from exc

    if header is None:
        raise IngestError(f"{path.name} is empty.")

    found = tuple(name.strip() for name in header)
    if found == HIT_COLUMN_NAMES:
        return

    missing = [c for c in HIT_COLUMN_NAMES if c not in found]
    unexpected = [c for c in found if c not in HIT_COLUMN_NAMES]

    if missing or unexpected:
        parts = []
        if missing:
            parts.append(f"missing columns: {', '.join(missing)}")
        if unexpected:
            parts.append(f"unexpected columns: {', '.join(unexpected)}")
        raise IngestError(
            f"{path.name} does not match the expected 29-column inference "
            f"schema ({'; '.join(parts)}).",
            expected=list(HIT_COLUMN_NAMES),
            found=list(found),
        )

    # Same names, different order. The pinned `columns` map is positional, so
    # loading this file would put y values into the x column.
    raise IngestError(
        f"{path.name} has the expected 29 columns but in a different order. "
        "The reader is positional, so the file must be reordered before it can "
        "be ingested.",
        expected=list(HIT_COLUMN_NAMES),
        found=list(found),
    )


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
