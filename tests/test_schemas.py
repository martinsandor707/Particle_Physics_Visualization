"""The accepted input schemas: detection, refusal sentences and per-kind facts.

Pure checks - no database. The real electron head Parquet files are read when present
(they are gitignored), so the exact producer headers are pinned too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from calosrv.db import ddl, naming, schemas
from calosrv.errors import IngestError

REPO = Path(__file__).resolve().parent.parent
HIT_HEAD = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3_head.parquet"
AGGR_HEAD = REPO / "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3_head.parquet"


@pytest.mark.parametrize("schema", schemas.SCHEMAS, ids=lambda s: s.name)
def test_each_schema_is_recognised_by_its_exact_header_and_name_set(schema):
    assert schemas.detect_header("f.csv", schema.names) is schema
    assert schemas.detect_names("f.parquet", reversed(schema.names)) is schema


def test_the_three_schemas_have_the_documented_widths_and_kinds():
    widths = {s.name: (s.n_columns, s.kind) for s in schemas.SCHEMAS}
    assert widths == {
        "hits_all_models": (99, ddl.KIND_TWO_SHOWER),
        "standalone_hits": (21, ddl.KIND_SINGLE_HITS),
        "standalone_events": (59, ddl.KIND_SINGLE_EVENTS),
    }


@pytest.mark.parametrize("path, schema", [(HIT_HEAD, schemas.STANDALONE_HITS),
                                          (AGGR_HEAD, schemas.STANDALONE_EVENTS)])
def test_the_producer_headers_are_the_pinned_schemas(path, schema):
    if not path.is_file():
        pytest.skip(f"{path.name} is not present")
    import duckdb

    escaped = str(path).replace("'", "''")
    names = [row[0] for row in duckdb.connect().execute(
        f"DESCRIBE SELECT * FROM read_parquet('{escaped}')").fetchall()]
    assert schemas.detect_names(path.name, names) is schema


@pytest.mark.parametrize("schema", schemas.SCHEMAS, ids=lambda s: s.name)
def test_a_reordered_header_is_refused_naming_its_schema(schema):
    names = list(schema.names)
    names[3], names[4] = names[4], names[3]
    with pytest.raises(IngestError, match="different order") as info:
        schemas.detect_header("order.csv", names)
    assert schema.label in info.value.detail


def test_a_header_one_column_short_names_its_schema_and_the_missing_column():
    names = [n for n in schemas.STANDALONE_HITS.names if n != "daughter_type"]
    with pytest.raises(IngestError) as info:
        schemas.detect_header("short.csv", names)
    detail = info.value.detail
    assert "does not match the standalone_hits v3 input schema (21 columns; missing columns: daughter_type)" in detail
    assert info.value.extra["schema"]["name"] == "standalone_hits"


def test_an_unrecognisable_header_is_reported_against_hits_all_models():
    with pytest.raises(IngestError) as info:
        schemas.detect_header("alpha.csv", ["alpha", "beta"])
    assert "does not match the hits_all_models input schema" in info.value.detail
    assert len(info.value.extra["expected"]) == 99
    assert schemas.accepted_sentence() in info.value.detail


def test_the_v37_sentence_stays_short_and_names_the_retired_schema():
    """Three of the 99 names are present, and they are shared by the 21-column schema too."""
    with pytest.raises(IngestError) as info:
        schemas.detect_header("v37.csv", ["event_number", "x", "energy", "voxel_fA_pred"])
    message = info.value.detail
    assert "(96 in all)" in message and "retired v37" in message
    assert len(message) < 500


def test_a_v2_aggregate_is_named_as_such():
    v2 = ["event_id", "incoming_momentum", "incoming_theta", "incoming_phi", "incoming_momentum_bin",
          "width", "height", "depth", "num_hits", "total_hit_energy", "gnn_logical_node", "energy"]
    with pytest.raises(IngestError) as info:
        schemas.detect_header("aggr_v2.csv", v2)
    assert "standalone_events v3" in info.value.detail
    assert "v2 aggregated file" in info.value.detail


def test_distinctive_columns_never_overlap_and_shared_ones_decide_nothing():
    sigs = [schemas.signature(s) for s in schemas.SCHEMAS]
    for i, a in enumerate(sigs):
        for b in sigs[i + 1:]:
            assert not a & b
    assert schemas.nearest(["event_number", "x", "y", "z", "energy"]) is schemas.DEFAULT


def test_the_accepted_sentence_names_every_schema():
    sentence = schemas.accepted_sentence()
    for schema in schemas.SCHEMAS:
        assert f"{schema.label} ({schema.n_columns} columns)" in sentence


def test_the_upload_advert_lists_every_schema_with_its_columns():
    advert = schemas.advertised()
    assert [a["name"] for a in advert] == [s.name for s in schemas.SCHEMAS]
    assert [len(a["columns"]) for a in advert] == [99, 21, 59]


def test_registry_keys_resolve_and_unknown_ones_do_not():
    assert schemas.get("hits_all_models", 1) is schemas.HITS_ALL_MODELS
    assert schemas.get("standalone_events", 3) is schemas.STANDALONE_EVENTS
    assert schemas.get("standalone_events", 2) is None
    assert schemas.get(None, None) is None


def test_derived_status_per_kind():
    assert schemas.derived_status(ddl.KIND_TWO_SHOWER, None) == "stale"
    assert schemas.derived_status(ddl.KIND_TWO_SHOWER, 2) == "current"
    assert schemas.derived_status(ddl.KIND_SINGLE_HITS, 1) == "current"
    assert schemas.derived_status(None, 1) == "unknown"


def test_required_tables_per_kind():
    assert schemas.required_tables("x", ddl.KIND_SINGLE_EVENTS, 1, False) == {"event_x"}
    assert schemas.required_tables("x", ddl.KIND_TWO_SHOWER, None, True) == {
        "proj_x", "event_x", "proj_x_s10"}
    assert schemas.required_tables("x", ddl.KIND_TWO_SHOWER, 2, False) == {
        "proj_x", "event_x", "layers_x", "profiles_x"}
    assert schemas.required_tables("x", ddl.KIND_SINGLE_HITS, 1, True) == {
        "proj_x", "event_x", "proj_x_s10", "layers_x", "profiles_x"}


def test_new_tables_are_managed_and_dropped_with_their_experiment():
    tables = naming.all_tables("x")
    assert {"layers_x", "profiles_x"} <= set(tables)
    assert naming.experiment_of("profiles_x") == "x" and naming.experiment_of("layers_x") == "x"


def test_group1_has_seventy_columns_per_shower_with_unique_names():
    one, two = ddl.group1_columns(("a",)), ddl.group1_columns(("a", "b"))
    assert len(one) == 70 and len(two) == 140
    assert len({n for n, _ in two}) == 140
    assert ddl.group1_column("sd_r", "b", "loc") == "sd_r_b_loc"
    with pytest.raises(ValueError):
        ddl.group1_column("sd_r", "c", "loc")
    # No Group-1 name collides with an existing event column.
    assert not {n for n, _ in two} & set(ddl.EVENT_COLUMN_NAMES)
