"""Shared request dependencies: the database cursor and the kinematic filter."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import duckdb
from fastapi import Depends, Query, Request

from ..config import Settings
from ..db.connection import Database
from ..db.registry import ExperimentRecord, require_ready
from ..errors import UnknownTableError
from ..query import filters
from ..query.filters import FilterSpec


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.database


def cursor(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """A short-lived read cursor for one request."""
    database: Database = request.app.state.database
    with database.read_cursor() as con:
        yield con


CursorDep = Annotated[duckdb.DuckDBPyConnection, Depends(cursor)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def resolve_table(
    con: CursorDep,
    table_name: str | None = Query(
        None,
        description=(
            "Experiment to query. Defaults to the first ready experiment, so "
            "the interface can load before the user has chosen one."
        ),
    ),
) -> ExperimentRecord:
    """Resolve and validate the requested experiment."""
    if table_name:
        return require_ready(con, table_name)

    from ..db import registry

    ready = registry.list_experiments(con, ready_only=True)
    if not ready:
        raise UnknownTableError(
            "No experiment has finished ingesting yet. Upload a CSV, or run "
            "the offline ingest CLI, to populate the database.",
            available=[],
        )
    return ready[0]


RecordDep = Annotated[ExperimentRecord, Depends(resolve_table)]


def resolve_filter(
    record: RecordDep,
    e1_min: float | None = Query(None, description="Lower bound on incoming_momentum_A (GeV)."),
    e1_max: float | None = Query(None, description="Upper bound on incoming_momentum_A (GeV)."),
    e2_min: float | None = Query(None, description="Lower bound on incoming_momentum_B (GeV)."),
    e2_max: float | None = Query(None, description="Upper bound on incoming_momentum_B (GeV)."),
    d_min: float | None = Query(None, description="Lower bound on centroid_AB_distance (mm)."),
    d_max: float | None = Query(None, description="Upper bound on centroid_AB_distance (mm)."),
    include_undefined_d: bool = Query(
        False,
        description=(
            "Include events whose A-B separation is undefined because shower A "
            "deposited no energy. Excluded by default, and always counted."
        ),
    ),
) -> FilterSpec:
    """Build the chained AND filter shared by every data endpoint."""
    return filters.build(
        record,
        e1_min=e1_min, e1_max=e1_max,
        e2_min=e2_min, e2_max=e2_max,
        d_min=d_min, d_max=d_max,
        include_undefined_d=include_undefined_d,
    )


FilterDep = Annotated[FilterSpec, Depends(resolve_filter)]
