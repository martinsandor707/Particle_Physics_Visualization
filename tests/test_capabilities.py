"""The capability contract: one owner of what each experiment kind can serve.

``query/capabilities.py`` decides every gate, ``query/filters.py`` builds the
selection of the axes a kind has, and ``query/showers.py`` names its per-shower
columns. These tests pin the three together, the catalogue's capability block
against its checked-in contract, and the two-shower selection byte for byte
against the release before the single-shower kinds existed.
"""

from __future__ import annotations

import json
import re

import duckdb
import pandas as pd
import pytest

import contract_check
from calosrv.db import ddl, schemas
from calosrv.db.registry import STATUS_READY, ExperimentRecord
from calosrv.errors import CapabilityError, ValidationError
from calosrv.query import capabilities, experiments, filters, showers


def _record(schema, **extra) -> ExperimentRecord:
    base = dict(table_name=f"t_{schema.name}", status=STATUS_READY,
                schema_name=schema.name, schema_version=schema.version,
                derived_version=schemas.DERIVED_VERSION[schema.kind],
                n_events=100, e1_min=0.5, e1_max=19.9)
    if schema.kind == ddl.KIND_TWO_SHOWER:
        base.update(e2_min=0.6, e2_max=19.8, d_min=10.0, d_max=5000.0)
    base.update(extra)
    return ExperimentRecord(**base)


SINGLE_HITS = _record(schemas.STANDALONE_HITS)
SINGLE_EVENTS = _record(schemas.STANDALONE_EVENTS)
TWO = _record(schemas.HITS_ALL_MODELS)


# --------------------------------------------------------- capabilities --

def test_every_gate_is_decided_with_a_reason():
    for record in (SINGLE_HITS, SINGLE_EVENTS, TWO):
        caps = capabilities.of(record)
        assert set(caps.gates) == set(capabilities.ALL_GATES)
        for gate, open_ in caps.gates.items():
            assert open_ or caps.reasons.get(gate), (record.kind, gate)


def test_no_card_is_advertised_before_its_route_exists():
    for record in (SINGLE_HITS, SINGLE_EVENTS, TWO):
        caps = capabilities.of(record)
        assert {g for g, open_ in caps.gates.items() if open_} <= capabilities.IMPLEMENTED


def test_single_shower_kinds_never_offer_two_shower_views():
    for record in (SINGLE_HITS, SINGLE_EVENTS):
        caps = capabilities.of(record)
        assert not caps.can("frame-canonical")
        assert caps.models == () and not caps.can("energy")
        assert caps.filters == ("e1",) and caps.showers == ("a",)
    assert "two showers" in capabilities.of(SINGLE_HITS).reasons["frame-canonical"]
    assert "no hits" in capabilities.of(SINGLE_EVENTS).reasons["xy"]


def test_xgboost_is_always_shut_and_says_where_to_look():
    for record in (SINGLE_HITS, SINGLE_EVENTS, TWO):
        assert "TODO.md" in capabilities.of(record).reasons["xgboost"]


def test_capability_block_matches_contract():
    for record in (SINGLE_HITS, SINGLE_EVENTS, TWO):
        block = capabilities.of(record).as_dict()
        contract_check.check(json.loads(json.dumps(block)), "experiments", at="capabilities")


def test_described_lists_are_always_present():
    for record in (SINGLE_HITS, SINGLE_EVENTS):
        payload = experiments.describe(record)
        for key in ("frames", "coord_systems", "models", "channels"):
            assert payload[key] == [], key
        assert payload["kind"] == record.kind
        assert payload["schema"]["n_columns"] == record.schema.n_columns


def test_require_raises_the_problem_contract():
    with pytest.raises(CapabilityError) as err:
        capabilities.require(SINGLE_HITS, "frame-canonical", field="coord_system")
    problem = err.value.to_problem()
    contract_check.check(problem, "capability_problem")
    assert problem["field"] == "coord_system" and problem["capability"] == "frame-canonical"
    assert problem["kind"] == ddl.KIND_SINGLE_HITS and problem["status"] == 422
    with pytest.raises(ValueError):
        capabilities.require(TWO, "no-such-card")


def test_stale_two_shower_experiment_names_the_rebuild():
    stale = _record(schemas.HITS_ALL_MODELS, derived_version=1)
    caps = capabilities.of(stale)
    assert caps.derived["status"] == "stale" and "Rebuild" in caps.derived["notice"]


# -------------------------------------------------------------- catalogue --

def test_catalogue_matches_contract_and_deduplicates_lattices(client):
    response = client.get("/api/experiments")
    payload = response.json()
    contract_check.check(payload, "experiments")
    assert len(response.content) < 100_000
    for experiment in payload["experiments"]:
        lattice = experiment.get("lattice")
        if lattice is None:
            continue
        assert lattice["id"] in payload["lattices"]
        assert "coords" not in lattice["x"]
        assert "coords" in payload["lattices"][lattice["id"]]["x"]


def test_contract_validator_reports_violations():
    errors = contract_check.errors({"a": 1, "hits": []},
                                   {"type": "object", "required": ["a", "b"],
                                    "properties": {"a": {"type": "string"}},
                                    "propertyNames": {"not": {"enum": ["hits"]}}})
    assert any("missing required key 'b'" in e for e in errors)
    assert any("expected string" in e for e in errors)
    assert any("forbidden" in e for e in errors)
    for name in contract_check.names():
        assert contract_check.load(name)["$defs"]["filter"]


# ---------------------------------------------------------------- filters --

def _placeholders(sql: str) -> set[str]:
    return set(re.findall(r"\$(\w+)", sql))


@pytest.mark.parametrize("record", [TWO, SINGLE_HITS, SINGLE_EVENTS], ids=lambda r: r.kind)
def test_where_sql_and_params_are_in_lockstep(record):
    for undefined in ((False, True) if record.kind == ddl.KIND_TWO_SHOWER else (False,)):
        spec = filters.build(record, include_undefined_d=undefined)
        assert _placeholders(spec.where_sql("p")) == set(spec.params())
        # Rows: inside, outside on E1, and (two-shower) undefined D.
        columns = {"e1": [1.0, 25.0]}
        expected = 1
        if "e2" in spec.axes:
            columns = {"e1": [1.0, 25.0, 1.0], "e2": [1.0, 1.0, 1.0], "d": [20.0, 20.0, None]}
            expected = 2 if undefined else 1
        con = duckdb.connect()
        con.register("t", pd.DataFrame(columns))
        # The SQL names only columns this kind's table has, and DuckDB accepts
        # exactly these parameters.
        n = con.execute(f"SELECT count(*) FROM t p WHERE {spec.where_sql('p')}",
                        spec.params()).fetchone()[0]
        assert n == expected


def test_two_shower_selection_is_byte_identical_to_the_previous_release():
    spec = filters.build(TWO, e1_min=1.0, e1_max=5.0, d_min=20.0, d_max=40.0)
    assert spec.where_sql() == (
        "e1 BETWEEN $e1_min AND $e1_max AND e2 BETWEEN $e2_min AND $e2_max "
        "AND d IS NOT NULL AND d BETWEEN $d_min AND $d_max")
    assert spec.where_sql("p") == (
        "p.e1 BETWEEN $e1_min AND $e1_max AND p.e2 BETWEEN $e2_min AND $e2_max "
        "AND p.d IS NOT NULL AND p.d BETWEEN $d_min AND $d_max")
    undefined = filters.build(TWO, include_undefined_d=True)
    assert undefined.where_sql() == (
        "e1 BETWEEN $e1_min AND $e1_max AND e2 BETWEEN $e2_min AND $e2_max "
        "AND (d IS NULL OR d BETWEEN $d_min AND $d_max)")
    assert list(spec.params().items()) == [
        ("e1_min", 1.0), ("e1_max", 5.0), ("e2_min", 0.6), ("e2_max", 19.8),
        ("d_min", 20.0), ("d_max", 40.0)]
    assert spec.cache_key() == (TWO.table_name, 1.0, 5.0, 0.6, 19.8, 20.0, 40.0, False)
    assert spec.as_dict() == {"e1": [1.0, 5.0], "e2": [0.6, 19.8], "d": [20.0, 40.0],
                              "include_undefined_d": False}
    assert spec.clamped(TWO) == spec


@pytest.mark.parametrize("record", [SINGLE_HITS, SINGLE_EVENTS], ids=lambda r: r.kind)
def test_one_axis_kinds_refuse_two_shower_cuts(record):
    for name in ("e2_min", "e2_max", "d_min", "d_max"):
        with pytest.raises(ValidationError) as err:
            filters.build(record, **{name: 1.0})
        assert err.value.extra["field"] == name
    with pytest.raises(ValidationError) as err:
        filters.build(record, include_undefined_d=True)
    assert err.value.extra["field"] == "include_undefined_d"
    spec = filters.build(record, e1_min=2.0)
    assert spec.as_dict() == {"e1": [2.0, 19.9], "e2": [None, None], "d": [None, None],
                              "include_undefined_d": False}
    assert spec.cache_key() == (record.table_name, 2.0, 19.9, None, None, None, None, False)
    assert spec.clamped(record).e2_min is None


def test_one_axis_kind_refused_through_the_api_filter_names_the_field():
    from calosrv.api import deps

    with pytest.raises(ValidationError) as err:
        deps.resolve_filter(SINGLE_HITS, None, None, None, None, 5.0, None, False)
    assert err.value.extra["field"] == "d_min"


# ---------------------------------------------------------------- showers --

def test_shower_vocabulary_names_real_columns():
    event_columns = {
        ddl.KIND_TWO_SHOWER: {n for n, _ in ddl.EVENT_COLUMNS_V2},
        ddl.KIND_SINGLE_HITS: {n for n, _ in ddl.EVENT_SINGLE_COLUMNS},
        ddl.KIND_SINGLE_EVENTS: {n for n, _ in ddl.EVENT_FEATURE_COLUMNS},
    }
    for record in (TWO, SINGLE_HITS, SINGLE_EVENTS):
        names = event_columns[record.kind]
        for shower in showers.of(record):
            for attr in ("momentum", "momentum_bin", "theta", "phi", "shower_energy",
                         "w_neg_hits", "w_neg_energy"):
                column = getattr(shower, attr)
                assert column is None or column in names, (record.kind, attr, column)
            for expr in (shower.deposit, shower.hits, shower.present_sql):
                idents = set(re.findall(r"[a-z_][a-z0-9_]*", expr))
                assert idents <= names, (record.kind, expr, idents - names)
            if shower.shower_energy is not None:
                assert shower.group1("sd_r", "loc") in names


def test_shower_choices_per_kind():
    assert [s.key for s in showers.of(TWO)] == ["a", "b"]
    assert [s.key for s in showers.of(TWO, "b")] == ["b"]
    assert [s.label for s in showers.of(SINGLE_HITS)] == ["Shower"]
    assert showers.of(SINGLE_HITS, "a") == showers.of(SINGLE_HITS, "both")
    for bad, record in (("b", SINGLE_HITS), ("b", SINGLE_EVENTS), ("c", TWO)):
        with pytest.raises(CapabilityError) as err:
            showers.of(record, bad)
        assert err.value.extra["field"] == "shower"
        contract_check.check(err.value.to_problem(), "capability_problem")
    assert showers.of(SINGLE_EVENTS)[0].origin_sql is None
