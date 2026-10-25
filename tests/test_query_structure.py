"""Structural rules of the query layer, checked over every module and every kind.

Two rules the plan freezes, enforced here rather than left to review:

* **Column names come from the vocabulary.** Every per-shower column the query
  layer reads is named by ``query/showers.py`` or a ``db/ddl.py`` builder. Each
  name is bound against empty tables built from its kind's own DDL, so a name
  that does not exist in that kind's table fails here, not at a user's request.
* **Per-event quantities come from the event table.** The event-table modules
  never read the projection table: an average over hit rows weights an event
  by its hit count (``query/__init__.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

from calosrv.db import ddl, group1, schemas
from calosrv.db.registry import STATUS_READY, ExperimentRecord
from calosrv.query import showers

QUERY = Path(__file__).resolve().parent.parent / "calosrv" / "query"

#: The modules that aggregate per-event quantities: never a projection read.
EVENT_TABLE_MODULES = (
    "summary", "energy", "performance", "performance_bins", "prediction_density", "response",
    "negative_depth", "shower_distributions", "primaries", "features_catalog", "features",
    "profiles",
)
#: The modules that scan hits.
HIT_MODULES = ("projections", "hit_distributions", "statistics", "correlations")

#: Each kind's tables, as its DDL builds them.
KIND_TABLES = {
    ddl.KIND_TWO_SHOWER: {"event": ddl.EVENT_COLUMNS_V2,
                          "proj": tuple((n, t) for n, t, _ in ddl.PROJ_COLUMNS)},
    ddl.KIND_SINGLE_HITS: {"event": ddl.EVENT_SINGLE_COLUMNS,
                           "proj": tuple((n, t) for n, t, _ in ddl.PROJ_SINGLE_COLUMNS)},
    ddl.KIND_SINGLE_EVENTS: {"event": ddl.EVENT_FEATURE_COLUMNS},
}


def _record(kind: str) -> ExperimentRecord:
    schema = schemas.of_kind(kind)
    return ExperimentRecord(table_name=f"t_{schema.name}", status=STATUS_READY,
                            schema_name=schema.name, schema_version=schema.version,
                            derived_version=schemas.DERIVED_VERSION[kind])


def _con(kind: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for alias, columns in KIND_TABLES[kind].items():
        body = ", ".join(f"{name} {sql_type.split()[0]}" for name, sql_type in columns)
        con.execute(f"CREATE TABLE {alias} ({body})")
    return con


def _binds(con: duckdb.DuckDBPyConnection, table: str, expression: str) -> None:
    con.execute(f"SELECT {expression} FROM {table} p LIMIT 0")


@pytest.mark.parametrize("kind", list(KIND_TABLES))
def test_every_shower_column_exists_in_its_kinds_tables(kind):
    con = _con(kind)
    record = _record(kind)
    for shower in showers.of(record):
        for field in ("momentum", "momentum_bin", "theta", "phi", "deposit", "hits",
                      "present_sql", "shower_energy", "w_neg_hits", "w_neg_energy",
                      "primary_rows"):
            expression = getattr(shower, field)
            if expression is not None:
                _binds(con, "event", expression)
        if shower.has_centroids:
            for axis in "xyz":
                _binds(con, "event", shower.p0(axis))
                for frame in ddl.CENTROID_SUFFIX:
                    _binds(con, "event", shower.centroid(axis, frame))
        if shower.shower_energy is not None:
            for stem, _ in ddl.GROUP1_SHOWER_STEMS:
                _binds(con, "event", shower.group1(stem))
            for stem, _ in ddl.GROUP1_FRAME_STEMS:
                for frame in ddl.GROUP1_FRAMES:
                    _binds(con, "event", shower.group1(stem, frame))
        if shower.origin_sql is not None and "proj" in KIND_TABLES[kind]:
            _binds(con, "proj", shower.origin_sql)


@pytest.mark.parametrize("kind", [ddl.KIND_TWO_SHOWER, ddl.KIND_SINGLE_HITS])
def test_every_rebuilt_feature_binds_for_hit_kinds(kind):
    con = _con(kind)
    for shower in showers.of(_record(kind)):
        for frame in ddl.GROUP1_FRAMES:
            for feature in group1.FEATURES:
                _binds(con, "event", group1.feature_sql(feature, frame, shower.key))
            _binds(con, "event", group1.circular_mean_sql(frame, shower.key))
            _binds(con, "event", group1.resultant_sql(frame, shower.key))


def test_every_network_and_segmentation_column_exists_for_two_showers():
    con = _con(ddl.KIND_TWO_SHOWER)
    for coord in ddl.COORD_SYSTEMS:
        for stem, _ in ddl.SEG_STAT_COLUMNS:
            _binds(con, "event", ddl.seg_stat_column(stem, coord))
        for net in ("en", "th"):
            for shower in "ab":
                for column in ddl.prediction_columns(net, shower, coord):
                    _binds(con, "event", column)


def test_vocabulary_builders_refuse_unknown_names():
    for call in (lambda: ddl.centroid_column("c", "x"), lambda: ddl.p0_column("a", "w"),
                 lambda: ddl.seg_stat_column("e_c_true", "lab"),
                 lambda: ddl.prediction_columns("xx", "a", "lab")):
        with pytest.raises(ValueError):
            call()
    with pytest.raises(ValueError):
        showers.of(_record(ddl.KIND_SINGLE_EVENTS))[0].centroid("x")


_PROJECTION_READ = re.compile(r"proj_table\(|[\"']proj_")


@pytest.mark.parametrize("module", EVENT_TABLE_MODULES)
def test_event_table_modules_never_read_the_projection_table(module):
    source = (QUERY / f"{module}.py").read_text(encoding="utf-8")
    assert not _PROJECTION_READ.search(source), module


def test_the_package_docstring_names_every_module_by_its_rule():
    import calosrv.query as query

    for module in (*EVENT_TABLE_MODULES, *HIT_MODULES):
        assert (QUERY / f"{module}.py").is_file(), module
        assert f"``{module}.py``" in query.__doc__, module
