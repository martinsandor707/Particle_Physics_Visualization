"""The Parquet input specification: what a Parquet dataset must hold, and how it is read.

A Parquet file names and types its own columns, which settles two things a CSV
cannot promise. Column order no longer matters, because every column is read by
name. And each column's type is known before a single row is read, so the check
here is stricter than the CSV header check where it can be: a string in a
numeric column, a floating-point event number or an out-of-range integer is
refused before anything is dropped, not discovered half way through a load.

The file's set of column names decides which accepted input schema it is
(``db/schemas.py``), and every column is cast to that schema's pinned type, so a
Parquet-sourced archive part is interchangeable with a CSV-sourced one - the
same types in the same order (and, where the schema sorts its parts, the same
row order), read together and appendable to each other. A DOUBLE source
narrowed to REAL is reported with what it costs: float32 round-off, at most
2⁻²⁴ ≈ 6 × 10⁻⁸ relative, several orders below the detector's resolution.

Two Parquet spellings are normalised to what the CSV reader produces: an empty
string in a text column the schema allows to be empty is NULL, as an empty CSV
field is, and a BOOLEAN where the schema stores 0/1 becomes 0/1.

DuckDB's own Parquet reader does all of this; pyarrow is not needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from ..db import schemas
from ..db.naming import quote
from ..db.schemas import InputSchema
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
    if base == "BOOLEAN":
        return "boolean"
    if base == '"NULL"' or base == "NULL":
        # An all-null Arrow column: no value to type, which only a column the
        # schema allows to be empty may be.
        return "null"
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


def _detect(path: Path, found: dict[str, str]) -> tuple[InputSchema, list[str]]:
    """The schema whose names the file holds; the pandas index columns ignored."""
    ignored = [name for name in found if _PANDAS_INDEX.match(name)]
    names = [name for name in found if name not in ignored]
    return schemas.detect_names(path.name, names), ignored


def _check_types(path: Path, found: dict[str, str], schema: InputSchema) -> list[str]:
    """Refuse a column whose type cannot become the pinned one; return those narrowed."""
    wrong: list[str] = []
    narrowed: list[str] = []
    for name, target in schema.columns:
        source = found[name]
        kind = _kind(source)
        if target == "VARCHAR":
            ok = kind == "text" or (kind == "null" and name in schema.empty_is_null)
            want = "text"
        elif target in _TARGET_INTEGERS:
            # A floating-point event number or cell ID would be rounded silently.
            ok = kind == "integer" or (kind == "boolean" and name in schema.boolean_ok)
            want = "an integer type" + (" or a boolean" if name in schema.boolean_ok else "")
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
    con: duckdb.DuckDBPyConnection, path: Path, found: dict[str, str], schema: InputSchema
) -> None:
    """Every integer must fit its pinned type. A dry-run cast reads only those columns."""
    wider = [
        (name, target) for name, target in schema.columns
        if target in _TARGET_INTEGERS and found[name].upper() != target
        and _kind(found[name]) == "integer"
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
    con: duckdb.DuckDBPyConnection, path: Path, found: dict[str, str], schema: InputSchema
) -> dict[str, int]:
    """NaN in the columns where an undefined value has a meaning of its own."""
    floating = [c for c in schema.nan_as_null if _kind(found[c]) == "float"]
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
    schema, ignored = _detect(path, found)
    narrowed = _check_types(path, found, schema)
    _check_integer_ranges(con, path, found, schema)
    nan_as_null = _count_nan(con, path, found, schema)
    booleans = [c for c in schema.boolean_ok if _kind(found[c]) == "boolean"]

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
    if booleans:
        notices.append(f"BOOLEAN column(s) stored as 0/1: {', '.join(booleans)}.")
    if ignored:
        notices.append(f"pandas index column(s) ignored: {', '.join(ignored)}.")
    return SourceCheck(
        format="parquet", rows=count_rows(con, path), narrowed=narrowed,
        nan_as_null=nan_as_null, notices=notices, schema=schema,
    )


def select_sql(path: Path, event_offset: int = 0, check: SourceCheck | None = None) -> str:
    """Every column in the schema's order, cast to its pinned type.

    The event offset is applied to the schema's event key before the cast, so
    an offset that overflows the pinned type is an error here rather than an
    INT64 part beside INT32 ones. NaN becomes NULL in the undefined-separation
    columns the check found it in, an empty string NULL in the text columns
    the schema allows to be empty, and the rows are written in the schema's
    archive order when it has one.
    """
    schema = check.schema if check else schemas.DEFAULT
    to_null = set(check.nan_as_null) if check else set()
    projected = []
    for name, sql_type in schema.columns:
        column = quote(name)
        if name == schema.event_key and event_offset:
            value = f"CAST({column} + {int(event_offset)} AS {sql_type})"
        elif name in schema.empty_is_null:
            value = f"NULLIF(CAST({column} AS VARCHAR), '')"
        else:
            value = f"CAST({column} AS {sql_type})"
        if name in to_null:
            value = f"CASE WHEN isnan({column}) THEN NULL ELSE {value} END"
        projected.append(f"{value} AS {column}")
    order = (" ORDER BY " + ", ".join(quote(c) for c in schema.archive_order)
             if schema.archive_order else "")
    return f"SELECT {', '.join(projected)} FROM {_relation(path)}{order}"
