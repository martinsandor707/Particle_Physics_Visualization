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
from ..query import capabilities, filters
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
    request: Request,
    table_name: str | None = Query(
        None,
        description=(
            "Experiment to query. Defaults to the Admin Settings panel's default "
            "experiment when it is ready, otherwise the first ready experiment, "
            "so the interface can load before the user has chosen one."
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
            "No experiment has finished ingesting yet. Upload a dataset, or run "
            "the offline ingest CLI, to populate the database.",
            available=[],
        )
    defaults = getattr(request.app.state, "defaults", None)
    wanted = defaults.configured("default_dataset") if defaults is not None else None
    chosen = next((record for record in ready if record.table_name == wanted), None)
    if chosen is not None:
        return chosen
    # A request that names no experiment comes from a page loading before the
    # user has chosen one: prefer an experiment with hits, which every page can
    # draw, over an aggregated one that serves only event-level views.
    return next((r for r in ready if r.traits is not None and r.traits.has_hits), ready[0])


RecordDep = Annotated[ExperimentRecord, Depends(resolve_table)]


def capable(*gates: str, field: str = "table_name"):
    """A dependency resolving the experiment and refusing it unless every gate is open.

    ``record: Annotated[ExperimentRecord, capable("profile-w")]`` in a route
    signature gives the record, or a 422 naming the missing capability and why.
    FastAPI caches ``resolve_table`` per request, so it still runs once.
    """

    def dependency(record: RecordDep) -> ExperimentRecord:
        capabilities.require(record, *gates, field=field)
        return record

    return Depends(dependency)


def resolve_filter(
    record: RecordDep,
    e1_min: float | None = Query(
        None, description="Lower bound on incoming_momentum_A, or on the single shower's "
                          "incoming_momentum (GeV)."),
    e1_max: float | None = Query(
        None, description="Upper bound on incoming_momentum_A, or on the single shower's "
                          "incoming_momentum (GeV)."),
    e2_min: float | None = Query(
        None, description="Lower bound on incoming_momentum_B (GeV); two-shower data only."),
    e2_max: float | None = Query(
        None, description="Upper bound on incoming_momentum_B (GeV); two-shower data only."),
    d_min: float | None = Query(
        None, description="Lower bound on centroid_AB_distance (mm); two-shower data only."),
    d_max: float | None = Query(
        None, description="Upper bound on centroid_AB_distance (mm); two-shower data only."),
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
