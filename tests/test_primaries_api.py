"""``GET /api/primaries`` (C11): events without a primary-tagged hit, with Wilson intervals.

Booted against ``single_client``. Its single-shower hits hold 287 events whose
momentum bins hold 1, 1, 2, 8, 14, 15, 19, 20 and 200 events, a quarter of them
(event numbers divisible by four) carrying exactly one row with ``is_secondary =
0``; the aggregate and the two-shower baseline hold no species and must be refused.
Every expectation is recomputed from the event table with NumPy, and the Wilson
interval from a formula written out here, not by ``metrics.wilson_interval``. The
unit tests build a miniature event table in memory for the cases the fixture cannot
make: a bin with no event without a primary, one where every event lacks it, a
tagged-row count past the top bucket, and a count that is NULL.
"""

from __future__ import annotations

import math

import duckdb
import pandas as pd
import pytest
from pytest import approx

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from calosrv.db import ddl, schemas
from calosrv.db.registry import STATUS_READY, ExperimentRecord
from calosrv.query import density, filters, primaries, showers
from calosrv.stats import metrics
from calosrv.text import signed_hyphens

Z = 1.959963985


def _wilson(k: int, n: int) -> tuple[float, float]:
    """The 95% Wilson score interval, from the formula."""
    p = k / n
    d = 1.0 + Z * Z / n
    centre = (p + Z * Z / (2.0 * n)) / d
    half = Z * math.sqrt(p * (1.0 - p) / n + Z * Z / (4.0 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def _get(client, table=SINGLE_HITS_TABLE, **params):
    reply = client.get("/api/primaries", params={"table_name": table, **params})
    assert reply.status_code == 200, reply.text
    return reply.json()


def _events(client, where="TRUE"):
    with client.app.state.database.read_cursor() as con:
        return con.execute(
            f'SELECT * FROM "event_{SINGLE_HITS_TABLE}" WHERE {where}').fetchdf()


def _strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


# ------------------------------------------------------------ the numbers --

def test_response_is_contract_valid_and_small(single_client):
    reply = single_client.get("/api/primaries", params={"table_name": SINGLE_HITS_TABLE})
    assert reply.status_code == 200
    assert len(reply.content) < density.RESPONSE_LIMIT
    body = reply.json()
    contract_check.check(body, "primaries")
    columns = body["by_bin"]
    assert len({len(v) for v in columns.values()}) == 1       # one entry per bin in every column
    assert body["meta"]["table_name"] == SINGLE_HITS_TABLE and body["meta"]["exact"] is True


def test_rates_match_numpy_over_the_event_table(single_client):
    ev = _events(single_client)
    none = ev["n_primary_rows"] == 0
    body = _get(single_client)
    by_bin = body["by_bin"]

    populated = sorted(ev["e1_bin"].unique().tolist())
    assert by_bin["bin"] == populated
    assert by_bin["n"] == [int((ev["e1_bin"] == k).sum()) for k in populated]
    assert by_bin["k"] == [int((none & (ev["e1_bin"] == k)).sum()) for k in populated]
    assert by_bin["label"] == [f"{k}–{k + 1} GeV" for k in populated]
    assert by_bin["fraction"] == approx([k / n for k, n in zip(by_bin["k"], by_bin["n"])],
                                        rel=1e-5)
    for k, n, lo, hi in zip(by_bin["k"], by_bin["n"], by_bin["lo"], by_bin["hi"]):
        assert (lo, hi) == approx(_wilson(k, n), rel=1e-5)

    overall = body["overall"]
    assert overall["n_events"] == len(ev) == sum(by_bin["n"])
    assert overall["n_no_primary"] == int(none.sum()) == sum(by_bin["k"])
    assert overall["fraction"] == approx(none.mean(), rel=1e-5)
    assert (overall["interval"]["lo"], overall["interval"]["hi"]) == approx(
        _wilson(int(none.sum()), len(ev)), rel=1e-5)
    assert overall["interval"]["method"] == "wilson" and overall["interval"]["level"] == 0.95


def test_wilson_is_the_one_in_metrics(single_client):
    body = _get(single_client)
    for k, n, lo, hi in zip(body["by_bin"]["k"], body["by_bin"]["n"],
                            body["by_bin"]["lo"], body["by_bin"]["hi"]):
        reference = metrics.wilson_interval(k, n)
        assert (lo, hi) == approx((reference.lo, reference.hi), rel=1e-5)
    overall = metrics.wilson_interval(body["overall"]["n_no_primary"], body["overall"]["n_events"])
    assert body["overall"]["interval"]["label"] == overall.label
    assert body["overall"]["interval"]["lo"] == approx(overall.lo, rel=1e-5)


def test_the_event_not_the_hit_is_the_unit(single_client):
    """One tagged row or ten, an event is 'with a primary': the fractions count events."""
    ev = _events(single_client)
    assert ev["n_primary_rows"].max() >= 1
    body = _get(single_client)
    assert body["overall"]["n_events"] == len(ev)
    assert body["overall"]["n_events"] != int(ev["n_hits"].sum())


def test_the_count_distribution_is_exact_and_ends_in_an_open_bucket(single_client):
    ev = _events(single_client)
    body = _get(single_client)["primary_count"]
    assert body["value"] == list(range(11)) and body["top_bucket"] == "≥ 10"
    expected = [int((ev["n_primary_rows"] == c).sum()) for c in range(10)]
    expected.append(int((ev["n_primary_rows"] >= 10).sum()))
    assert body["events"] == expected and sum(body["events"]) == len(ev)


def test_a_selection_narrows_the_events_not_the_definition(single_client):
    ev = _events(single_client, "e1 >= 5 AND e1 <= 12")
    body = _get(single_client, e1_min=5.0, e1_max=12.0)
    assert body["overall"]["n_events"] == len(ev)
    assert body["overall"]["n_no_primary"] == int((ev["n_primary_rows"] == 0).sum())
    assert body["by_bin"]["bin"] == sorted(ev["e1_bin"].unique().tolist())
    assert body["filter"]["e1"] == [5.0, 12.0] and body["filter"]["e2"] == [None, None]
    contract_check.check(body, "primaries")


def test_an_empty_selection_is_served_with_no_bars_and_no_interval(single_client):
    body = _get(single_client, e1_min=0.0, e1_max=0.5)
    contract_check.check(body, "primaries")
    assert body["overall"] == {"n_events": 0, "n_no_primary": 0, "fraction": None, "interval": None}
    assert body["by_bin"]["bin"] == [] and body["primary_count"]["events"] == [0] * 11
    assert "No events match the current selection." in body["meta"]["warnings"]


def test_the_notes_define_the_card_name_the_interval_and_the_reference(single_client):
    body = _get(single_client)
    notes = " ".join(body["notes"])
    assert body["definition"] in body["notes"][0]
    assert "is_secondary = 0" in body["definition"]
    assert "Wilson" in notes and "Wald" in notes
    assert "73.83%" in notes and "electron file" in notes and "not this selection" in notes
    assert "25–27%" in notes
    for text in _strings(body):
        assert not signed_hyphens(text), text


# ------------------------------------------------------------ the refusals --

@pytest.mark.parametrize("table,kind", [(SINGLE_EVENTS_TABLE, "single_shower_events"),
                                         (BASELINE_TABLE, "two_shower_hits")])
def test_kinds_without_species_are_refused_with_the_reason(single_client, table, kind):
    reply = single_client.get("/api/primaries", params={"table_name": table})
    assert reply.status_code == 422
    problem = reply.json()
    assert problem["type"] == "/problems/unsupported-capability"
    assert problem["capability"] == "prim-rate" and problem["kind"] == kind
    assert problem["field"] == "table_name" and problem["table_name"] == table
    assert "is_secondary" in problem["reason"]
    contract_check.check(problem, "capability_problem")


def test_the_capability_is_checked_before_the_selection(single_client):
    """An e2 bound is refused on the aggregate, but the kind's refusal comes first."""
    reply = single_client.get("/api/primaries", params={"table_name": SINGLE_EVENTS_TABLE,
                                                        "e2_min": 1.0})
    assert reply.status_code == 422 and reply.json()["capability"] == "prim-rate"
    # On the hit kind the same bound is what is refused, naming the field.
    reply = single_client.get("/api/primaries", params={"table_name": SINGLE_HITS_TABLE,
                                                        "e2_min": 1.0})
    assert reply.status_code == 422 and reply.json()["field"] == "e2_min"


def test_the_columns_the_query_reads_exist(single_client):
    names = {name for name, _ in ddl.EVENT_SINGLE_COLUMNS}
    shower = showers.of(
        ExperimentRecord(table_name="x", status=STATUS_READY,
                         schema_name=schemas.STANDALONE_HITS.name,
                         schema_version=schemas.STANDALONE_HITS.version), "a")[0]
    assert {primaries.PRIMARY_ROWS, shower.momentum, shower.momentum_bin} <= names
    with single_client.app.state.database.read_cursor() as con:
        live = {row[0] for row in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [f"event_{SINGLE_HITS_TABLE}"]).fetchall()}
    assert {primaries.PRIMARY_ROWS, shower.momentum, shower.momentum_bin} <= live


# ------------------------------------------------------- unit: extremes --

def _single_record(table: str, n_events: int) -> ExperimentRecord:
    schema = schemas.STANDALONE_HITS
    return ExperimentRecord(
        table_name=table, status=STATUS_READY, schema_name=schema.name,
        schema_version=schema.version, derived_version=schemas.DERIVED_VERSION[schema.kind],
        n_events=n_events, e1_min=0.0, e1_max=100.0)


def _mini(rows: list[tuple[float, int, int | None]]):
    """An in-memory single-shower event table: (momentum, bin, tagged rows) per event."""
    frame = pd.DataFrame(rows, columns=["e1", "e1_bin", "n_primary_rows"]).astype(
        {"n_primary_rows": "Int64"})
    con = duckdb.connect()
    con.execute('CREATE TABLE "event_mini" AS SELECT * FROM frame')
    record = _single_record("mini", len(rows))
    return con, record, filters.build(record)


def test_a_bin_with_every_event_lacking_a_primary_and_one_with_none_lacking_it():
    rows = ([(2.5, 2, 0)] * 6                       # all six lack one
            + [(3.5, 3, 1)] * 5                     # none lacks one
            + [(4.5, 4, 0)] * 3 + [(4.6, 4, 2)] * 3)
    con, record, spec = _mini(rows)
    body = primaries.compute(con, record, spec).as_dict()
    by_bin = body["by_bin"]
    assert by_bin["bin"] == [2, 3, 4] and by_bin["n"] == [6, 5, 6] and by_bin["k"] == [6, 0, 3]
    assert by_bin["fraction"] == [1.0, 0.0, 0.5]
    # The Wilson interval does not collapse at k = n or k = 0, and stays inside [0, 1].
    assert by_bin["hi"][0] == 1.0 and by_bin["lo"][0] == approx(_wilson(6, 6)[0], rel=1e-5)
    assert by_bin["lo"][0] < 1.0
    assert by_bin["lo"][1] == 0.0 and by_bin["hi"][1] == approx(_wilson(0, 5)[1], rel=1e-5)
    assert by_bin["hi"][1] > 0.0
    assert all(0.0 <= lo <= hi <= 1.0 for lo, hi in zip(by_bin["lo"], by_bin["hi"]))


def test_tagged_row_counts_past_the_top_bucket_are_gathered_in_it():
    counts = [0, 0, 1, 2, 9, 10, 10, 11, 25]
    con, record, spec = _mini([(1.5, 1, c) for c in counts])
    body = primaries.compute(con, record, spec).as_dict()["primary_count"]
    assert body["value"] == list(range(11))
    assert body["events"] == [2, 1, 1, 0, 0, 0, 0, 0, 0, 1, 4]       # 10, 10, 11 and 25 are open
    assert sum(body["events"]) == len(counts) and body["top_bucket"] == "≥ 10"


def test_an_event_with_no_recorded_count_is_in_no_bar_and_is_disclosed():
    con, record, spec = _mini([(1.5, 1, 0), (1.6, 1, 1), (1.7, 1, None), (2.5, 2, None)])
    result = primaries.compute(con, record, spec)
    body = result.as_dict()
    assert result.n_unknown == 2 and body["overall"]["n_events"] == 2
    assert body["by_bin"]["bin"] == [1] and body["by_bin"]["n"] == [2]
    assert any("2 selected events have no recorded count" in n for n in body["notes"])
    assert sum(body["primary_count"]["events"]) == 2


def test_a_bin_that_disagrees_with_its_momenta_is_labelled_by_number():
    con, record, spec = _mini([(3.2, 3, 0), (4.2, 3, 1), (5.5, 5, 0)])
    body = primaries.compute(con, record, spec).as_dict()
    assert body["by_bin"]["label"][0].startswith("bin 3 (p 3.2")
    assert body["by_bin"]["label"][1] == "5–6 GeV"
    assert any("disagrees with the momenta in bin 3" in n for n in body["notes"])


def test_more_bins_than_can_be_labelled_is_refused_as_a_table_problem():
    from calosrv.errors import ValidationError

    con, record, spec = _mini([(k + 0.5, k, 0) for k in range(30)])
    with pytest.raises(ValidationError) as error:
        primaries.compute(con, record, spec)
    assert error.value.extra["field"] == "table_name"
