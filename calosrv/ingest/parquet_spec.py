"""The Parquet input specification: what a Parquet dataset must hold, and how it is read.

A Parquet file names and types its own columns, which settles two things a CSV
cannot promise. Column order no longer matters, because every column is read by
name. And each column's type is known before a single row is read, so the check
here is stricter than the CSV header check where it can be: a string in a
numeric column, a floating-point event number or an out-of-range integer is
refused before anything is dropped, not discovered half way through a load.

Every column is cast to its pinned ``ddl.HIT_COLUMNS`` type, so a Parquet-sourced
archive part is interchangeable with a CSV-sourced one - the same types in the
same order, read together and appendable to each other. A DOUBLE source narrowed
to REAL is reported with what it costs: float32 round-off, at most 2⁻²⁴ ≈ 6 × 10⁻⁸
relative, several orders below the detector's resolution.

DuckDB's own Parquet reader does all of this; pyarrow is not needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from ..db.ddl import HIT_COLUMN_NAMES, HIT_COLUMNS, NULLABLE_COLUMNS, SCHEMA_NAME
from ..db.naming import quote
from ..errors import IngestError
from .source_check import SourceCheck

#: DuckDB's names for the integer types a Parquet column can arrive as.
_INTEGER_TYPES = frozenset({
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
})
_FLOAT_TYPES = frozenset({"FLOAT", "REAL", "DOUBLE"})
_TARGET_INTEGERS = frozenset({"INTEGER", "SMALLINT", "BIGINT", "UTINYINT"})

#: pandas writes a non-default index as a column like this. It is not data.
_PANDAS_INDEX = re.compile(r"^__index_level_\d+__$")

_TYPES = dict(HIT_COLUMNS)


def _literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _relation(path: Path) -> str:
    return f"read_parquet({_literal(path)})"


def _kind(sql_type: str) -> str:
    base = sql_type.upper()
    if base in _INTEGER_TYPES:
        return "integer"
    if base in _FLOAT_TYPES:
        return "float"
    if base.startswith("DECIMAL"):
        return "decimal"
    if base == "VARCHAR" or base.startswith("ENUM"):
        return "text"
    return "other"


def describe(con: duckdb.DuckDBPyConnection, path: Path) -> dict[str, str]:
    """Column name -> DuckDB type, as the file declares them, in file order."""
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM {_relation(path)}").fetchall()
    except duckdb.Error as exc:
        raise IngestError(f"{path.name} could not be read as Parquet: {exc}") from exc
    return {row[0]: row[1] for row in rows}


def count_rows(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Rows in the file, from its footer - no scan.

    ``parquet_file_metadata`` has one row per file; ``parquet_metadata`` has one
    per column per row group, and summing it would overcount 99-fold.
    """
    return int(con.execute(
        f"SELECT num_rows FROM parquet_file_metadata({_literal(path)})"
    ).fetchone()[0])


def _check_columns(path: Path, found: dict[str, str]) -> list[str]:
    """Refuse a missing or unexpected column; return the pandas index columns ignored."""
    ignored = [name for name in found if _PANDAS_INDEX.match(name)]
    missing = [c for c in HIT_COLUMN_NAMES if c not in found]
    unexpected = [c for c in found if c not in _TYPES and c not in ignored]
    if not missing and not unexpected:
        return ignored
    parts = []
    if missing:
        parts.append(f"missing columns: {', '.join(missing)}")
    if unexpected:
        parts.append(f"unexpected columns: {', '.join(unexpected)}")
    message = (
        f"{path.name} does not match the {SCHEMA_NAME} input schema "
        f"({len(HIT_COLUMN_NAMES)} columns; {'; '.join(parts)})."
    )
    if "voxel_fA_pred" in found:
        message += (
            " This looks like a retired v37 (hits_with_gradcam) file; re-export it "
            f"in the {SCHEMA_NAME} format."
        )
    raise IngestError(message, expected=list(HIT_COLUMN_NAMES), found=list(found))


def _check_types(path: Path, found: dict[str, str]) -> list[str]:
    """Refuse a column whose type cannot become the pinned one; return those narrowed."""
    wrong: list[str] = []
    narrowed: list[str] = []
    for name, target in HIT_COLUMNS:
        source = found[name]
        kind = _kind(source)
        if target == "VARCHAR":
            ok = kind == "text"
            want = "text"
        elif target in _TARGET_INTEGERS:
            # A floating-point event number or cell ID would be rounded silently.
            ok = kind == "integer"
            want = "an integer type"
        else:
            ok = kind in ("integer", "float", "decimal")
            want = "a number"
            if ok and target == "REAL" and (kind == "decimal" or source.upper() == "DOUBLE"):
                narrowed.append(name)
        if not ok:
            wrong.append(f"{name} is {source}, expected {want}")
    if wrong:
        raise IngestError(
            f"{path.name} has columns of the wrong type: {'; '.join(wrong)}.",
            columns=wrong,
        )
    return narrowed


def _check_integer_ranges(
    con: duckdb.DuckDBPyConnection, path: Path, found: dict[str, str]
) -> None:
    """Every integer must fit its pinned type. A dry-run cast reads only those columns."""
    wider = [
        (name, target) for name, target in HIT_COLUMNS
        if target in _TARGET_INTEGERS and found[name].upper() != target
    ]
    if not wider:
        return
    counts = con.execute(
        "SELECT " + ", ".join(
            f"count(*) FILTER (WHERE {quote(name)} IS NOT NULL "
            f"AND TRY_CAST({quote(name)} AS {target}) IS NULL)"
            for name, target in wider
        ) + f" FROM {_relation(path)}"
    ).fetchone()
    bad = [
        f"{name} ({int(n):,} values do not fit {target})"
        for (name, target), n in zip(wider, counts) if n
    ]
    if bad:
        raise IngestError(
            f"{path.name} holds integers outside the schema's range: {'; '.join(bad)}.",
            columns=bad,
        )


def _count_nan(
    con: duckdb.DuckDBPyConnection, path: Path, found: dict[str, str]
) -> dict[str, int]:
    """NaN in the columns where an undefined value has a meaning of its own."""
    floating = [c for c in NULLABLE_COLUMNS if _kind(found[c]) == "float"]
    if not floating:
        return {}
    counts = con.execute(
        "SELECT " + ", ".join(f"count(*) FILTER (WHERE isnan({quote(c)}))" for c in floating)
        + f" FROM {_relation(path)}"
    ).fetchone()
    return {c: int(n) for c, n in zip(floating, counts) if n}


def validate(con: duckdb.DuckDBPyConnection, path: Path) -> SourceCheck:
    """Check a Parquet file against the input schema before anything is dropped.

    Raises ``IngestError`` naming every offending column. The checks read the
    footer, then only the integer and undefined-separation columns, so they cost
    seconds on the production file rather than a full load.
    """
    found = describe(con, path)
    ignored = _check_columns(path, found)
    narrowed = _check_types(path, found)
    _check_integer_ranges(con, path, found)
    nan_as_null = _count_nan(con, path, found)

    notices: list[str] = []
    if narrowed:
        notices.append(
            f"{len(narrowed)} column(s) stored as DOUBLE were narrowed to the schema's "
            "32-bit REAL, rounding each value by at most 6 × 10⁻⁸ of itself: "
            f"{', '.join(narrowed)}."
        )
    if nan_as_null:
        notices.append(
            f"{sum(nan_as_null.values()):,} NaN value(s) in the undefined-separation "
            "columns were read as undefined (NULL), as an empty field is in a CSV: "
            + ", ".join(f"{c} ({n:,})" for c, n in nan_as_null.items()) + "."
        )
    if ignored:
        notices.append(f"pandas index column(s) ignored: {', '.join(ignored)}.")
    return SourceCheck(
        format="parquet", rows=count_rows(con, path), narrowed=narrowed,
        nan_as_null=nan_as_null, notices=notices,
    )


def select_sql(path: Path, event_offset: int = 0, check: SourceCheck | None = None) -> str:
    """Every column in the schema's order, cast to its pinned type.

    The event offset is applied before the cast, so an offset that overflows the
    pinned INTEGER is an error here rather than an INT64 part beside INT32 ones.
    NaN becomes NULL in the undefined-separation columns the check found it in.
    """
    to_null = set(check.nan_as_null) if check else set()
    projected = []
    for name, sql_type in HIT_COLUMNS:
        column = quote(name)
        if name == "event_number" and event_offset:
            value = f"CAST({column} + {int(event_offset)} AS {sql_type})"
        else:
            value = f"CAST({column} AS {sql_type})"
        if name in to_null:
            value = f"CASE WHEN isnan({column}) THEN NULL ELSE {value} END"
        projected.append(f"{value} AS {column}")
    return f"SELECT {', '.join(projected)} FROM {_relation(path)}"
