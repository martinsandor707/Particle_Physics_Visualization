"""C9 (hits at negative depth) from a hand-made event table, against an independent computation.

``negative_depth.summarise`` reads only the Group-1 columns of the event table,
so a few lines of SQL give it a table whose answer can be worked out by hand:
two showers per event in different momentum splits, an event whose second
shower deposited nothing, boundary momenta (exactly 1 and 10 GeV), an event
every one of whose hits is negative, one the filter must drop (an undefined D)
and one outside the momentum range. The expected numbers are recomputed here
from the per-shower rows with explicit loops and the textbook formulas, not
with the helpers under test, so the SQL, the clustering and the intervals each
have an independent check. The booted-server checks live in
``test_physics_statistics_api.py``.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pytest

from calosrv.db import ddl, schemas
from calosrv.db.registry import ExperimentRecord
from calosrv.errors import CapabilityError
from calosrv.query import density, filters, negative_depth
from calosrv.stats import metrics
from calosrv.stats.gaussian import t_quantile_975
from calosrv.text import MINUS, signed_hyphens

import contract_check

# e1, e2, d, nA, nB, nAB, eA, eB, nhA, nhB, neA, neB
EVENTS = [
    (0.5, 12.0, 100.0, 40, 30, 5, 0.10, 2.00, 4, 0, 0.010, 0.000),    # A low, B high
    (3.0, 4.0, 150.0, 20, 25, 0, 1.50, 1.80, 2, 5, 0.100, 0.200),     # both mid
    (1.0, 10.0, 90.0, 10, 10, 0, 0.50, 0.60, 0, 1, 0.000, 0.010),     # exactly 1 and 10: both mid
    (15.0, 0.9, 300.0, 80, 12, 3, 4.00, 0.05, 8, 2, 0.300, 0.004),    # A high, B low
    (11.0, 11.5, 50.0, 60, 0, 0, 3.00, 0.00, 0, 0, 0.000, 0.000),     # shower B deposited nothing
    (7.0, 8.0, None, 30, 30, 0, 1.00, 1.10, 3, 3, 0.100, 0.100),      # D undefined: dropped
    (25.0, 5.0, 100.0, 30, 30, 0, 1.00, 1.10, 3, 3, 0.100, 0.100),    # p outside the range: dropped
    (2.0, 2.5, 200.0, 5, 5, 0, 0.20, 0.30, 5, 0, 0.200, 0.000),       # every hit of A is negative
]
IN_SELECTION = (0, 1, 2, 3, 4, 7)


@pytest.fixture(scope="module")
def two_shower():
    con = duckdb.connect()
    con.execute(
        'CREATE TABLE "event_unit" (event_number INTEGER, e1 DOUBLE, e2 DOUBLE, d DOUBLE, '
        "n_a_rows BIGINT, n_b_rows BIGINT, n_ab_rows BIGINT, e_dep_a DOUBLE, e_dep_b DOUBLE, "
        "w_neg_hits_a BIGINT, w_neg_hits_b BIGINT, w_neg_energy_a DOUBLE, w_neg_energy_b DOUBLE, "
        "n_hits_a BIGINT, n_hits_b BIGINT)"
    )
    for i, row in enumerate(EVENTS):
        # Group-1 counts a shower's rows: 'A+B' rows belong to B.
        n_a, n_b, n_ab = row[3:6]
        con.execute('INSERT INTO "event_unit" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [i, *row, n_a, n_b + n_ab])
    record = ExperimentRecord(
        table_name="unit", status="ready", schema_name=schemas.HITS_ALL_MODELS.name,
        schema_version=schemas.HITS_ALL_MODELS.version, derived_version=2)
    spec = filters.build(record, e1_min=0.0, e1_max=20.0, e2_min=0.0, e2_max=20.0,
                         d_min=0.0, d_max=1000.0)
    return con, record, spec


# ------------------------------------------------- the independent computation --

def _showers(scope: str):
    """``(event, p, n, nh, e, ne)`` per shower of the selected events, from the table above."""
    out = []
    for i in IN_SELECTION:
        e1, e2, _d, na, nb, nab, ea, eb, nha, nhb, nea, neb = EVENTS[i]
        if "a" in scope and na > 0:
            out.append((i, e1, na, nha, ea, nea))
        if "b" in scope and nb + nab > 0:
            out.append((i, e2, nb + nab, nhb, eb, neb))
    return out


def _in_split(key: str, p: float) -> bool:
    return {"all": True, "low": p < 1.0, "mid": 1.0 <= p <= 10.0, "high": p > 10.0}[key]


def _ratio(num, den):
    """``(R, (lo, hi))``: ratio of sums over clusters, linearised SE, Student-t, clipped to [0, 1]."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    n = num.size
    r = num.sum() / den.sum()
    if n < 2:
        return r, None
    se = math.sqrt(np.sum((num - r * den) ** 2) / (n * (n - 1) * den.mean() ** 2))
    t = t_quantile_975(n - 1)
    return r, (max(0.0, r - t * se), min(1.0, r + t * se))


def _wilson(k: int, n: int):
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def expected_split(showers, key: str):
    """``(members, clusters, array)`` of one split from per-shower ``(event, p, n, nh, e, ne)`` rows.

    A shower belongs to the split of its own momentum; an event's cluster in a
    split sums the showers of the event that fall in it. Shared with the
    booted-server tests, which build the rows from the hits instead.
    """
    members = [s for s in showers if _in_split(key, s[1])]
    clusters: dict[int, list[float]] = {}
    for event, _p, n, nh, e, ne in members:
        c = clusters.setdefault(event, [0.0, 0.0, 0.0, 0.0])
        c[0] += n; c[1] += nh; c[2] += e; c[3] += ne
    cl = np.array(list(clusters.values())).reshape(-1, 4)
    return members, clusters, cl


def check_splits(splits, showers, per_event: int) -> None:
    """Every split of a ``negative_w`` block against the independent computation."""
    assert [s["key"] for s in splits] == ["all", "low", "mid", "high"]
    for split in splits:
        members, clusters, cl = expected_split(showers, split["key"])
        assert split["n_events"] == len(clusters)
        assert split["n_showers"] == len(members)
        if not members:
            assert split["hits_fraction"] is None and split["note"] == "No showers in this split."
            continue
        assert split["events_with_any"] == int((cl[:, 1] > 0).sum())
        assert split["showers_with_any"] == sum(1 for m in members if m[3] > 0)
        assert split["hits"] == int(cl[:, 1].sum()) and split["hits_total"] == int(cl[:, 0].sum())
        assert split["energy_gev"] == pytest.approx(cl[:, 3].sum(), **APPROX)
        assert split["energy_total_gev"] == pytest.approx(cl[:, 2].sum(), **APPROX)

        # Events are the clusters: a two-shower event is one cluster, not two draws.
        r, hit_ci = _ratio(cl[:, 1], cl[:, 0])
        assert split["hits_fraction"] == pytest.approx(r, **APPROX)
        check_interval(split["hits_fraction_ci95"], hit_ci)
        r, energy_ci = _ratio(cl[:, 3], cl[:, 2])
        assert split["energy_fraction"] == pytest.approx(r, **APPROX)
        check_interval(split["energy_fraction_ci95"], energy_ci)

        # The primary proportion is on events; the shower-level one only with one shower per event.
        assert split["events_with_any_ci95"] == [
            pytest.approx(v, **APPROX) for v in _wilson(split["events_with_any"], split["n_events"])]
        if per_event == 1:
            assert split["showers_with_any_ci95"] == split["events_with_any_ci95"]
        else:
            assert split["showers_with_any_ci95"] is None


APPROX = dict(rel=6e-6, abs=1e-9)  # numbers are served to six significant figures


def check_interval(got, expected):
    if expected is None:
        assert got is None
    else:
        assert got == [pytest.approx(expected[0], **APPROX), pytest.approx(expected[1], **APPROX)]


@pytest.mark.parametrize("scope, choice", [("ab", "both"), ("a", "a"), ("b", "b")])
def test_every_split_matches_an_independent_computation(two_shower, scope, choice):
    con, record, spec = two_shower
    block = negative_depth.summarise(con, record, spec, choice)
    contract_check.check(block, "statistics", "negative_w")
    assert block["available"] is True and block["showers_per_event"] == len(scope)
    check_splits(block["splits"], _showers(scope), len(scope))


def test_the_selection_is_the_filters_not_the_table(two_shower):
    con, record, spec = two_shower
    whole = negative_depth.summarise(con, record, spec)["splits"][0]
    assert whole["n_events"] == len(IN_SELECTION)
    # Event 5 (D undefined) and event 6 (p = 25 GeV) are in the table and not in the selection.
    assert whole["n_showers"] == 2 * len(IN_SELECTION) - 1  # event 4's shower B deposited nothing
    wider = filters.build(record, e1_min=0.0, e1_max=30.0, e2_min=0.0, e2_max=20.0,
                          d_min=0.0, d_max=1000.0)
    assert negative_depth.summarise(con, record, wider)["splits"][0]["n_events"] == len(IN_SELECTION) + 1
    undefined = filters.build(record, e1_min=0.0, e1_max=20.0, e2_min=0.0, e2_max=20.0,
                              d_min=0.0, d_max=1000.0, include_undefined_d=True)
    assert negative_depth.summarise(con, record, undefined)["splits"][0]["n_events"] == len(IN_SELECTION) + 1


def test_the_momentum_cuts_are_strict_and_the_splits_partition_the_selection(two_shower):
    con, record, spec = two_shower
    block = negative_depth.summarise(con, record, spec)
    by_key = {s["key"]: s for s in block["splits"]}
    # Event 2 has p = 1 and p = 10 exactly: neither low nor high, as in the notebook.
    assert by_key["low"]["n_showers"] == 2     # event 0's A (0.5), event 3's B (0.9)
    assert by_key["high"]["n_showers"] == 3    # event 0's B (12), event 3's A (15), event 4's A (11)
    assert by_key["mid"]["n_showers"] == by_key["all"]["n_showers"] - 5
    for field in ("n_showers", "hits", "hits_total"):
        assert sum(by_key[k][field] for k in ("low", "mid", "high")) == by_key["all"][field]
    assert by_key["all"]["label"] == "All selected"
    assert by_key["low"]["label"] == "p < 1 GeV" and by_key["high"]["label"] == "p > 10 GeV"


def test_the_affected_statistics_describe_the_showers_with_any_negative_hit(two_shower):
    con, record, spec = two_shower
    affected = negative_depth.summarise(con, record, spec)["affected"]
    contract_check.check(affected, "statistics", "negative_w_affected")
    fractions = np.array([nh / n for _e, _p, n, nh, _en, _ne in _showers("ab") if nh > 0])
    assert affected["n"] == fractions.size
    assert affected["mean"] == pytest.approx(fractions.mean(), **APPROX)
    assert affected["sd"] == pytest.approx(fractions.std(ddof=1), **APPROX)
    assert affected["min"] == pytest.approx(fractions.min(), **APPROX)
    assert affected["max"] == pytest.approx(1.0, **APPROX)
    for key, q in (("q25", 25), ("q50", 50), ("q75", 75)):
        assert affected[key] == pytest.approx(np.percentile(fractions, q), **APPROX)
    assert affected["n_over_half"] == int((fractions > 0.5).sum())
    assert affected["n_over_half"] >= 1   # event 7's shower A, every hit negative


def test_a_single_shower_experiment_has_one_shower_per_event():
    con = duckdb.connect()
    con.execute('CREATE TABLE "event_one" (event_number INTEGER, e1 DOUBLE, n_hits BIGINT, '
                "e_dep_a DOUBLE, w_neg_hits_a BIGINT, w_neg_energy_a DOUBLE, n_hits_a BIGINT)")
    rows = [(0, 0.4, 20, 1.0, 2, 0.05), (1, 5.0, 30, 2.0, 0, 0.0), (2, 12.0, 40, 3.0, 8, 0.2),
            (3, 12.5, 10, 0.5, 1, 0.01)]
    for row in rows:
        con.execute('INSERT INTO "event_one" VALUES (?, ?, ?, ?, ?, ?, ?)', [*row, row[2]])
    record = ExperimentRecord(
        table_name="one", status="ready", schema_name=schemas.STANDALONE_HITS.name,
        schema_version=schemas.STANDALONE_HITS.version, derived_version=1)
    spec = filters.build(record, e1_min=0.0, e1_max=20.0)
    block = negative_depth.summarise(con, record, spec)
    contract_check.check(block, "statistics", "negative_w")
    assert block["showers_per_event"] == 1
    high = next(s for s in block["splits"] if s["key"] == "high")
    # Two events, 8 + 1 of 50 hits at negative depth: the cluster ratio, and Wilson on both units.
    r, ci = _ratio([8, 1], [40, 10])
    assert high["hits_fraction"] == pytest.approx(r, **APPROX)
    check_interval(high["hits_fraction_ci95"], ci)
    assert high["events_with_any"] == high["showers_with_any"] == 2
    assert high["showers_with_any_ci95"] == high["events_with_any_ci95"]
    low = next(s for s in block["splits"] if s["key"] == "low")
    assert low["n_events"] == 1 and low["hits_fraction"] == pytest.approx(0.1)
    assert low["hits_fraction_ci95"] is None and "N = 1 event" in low["note"]
    with pytest.raises(CapabilityError) as refused:
        negative_depth.summarise(con, record, spec, "b")
    assert refused.value.extra["field"] == "shower"


def test_an_unknown_shower_is_refused_naming_the_parameter(two_shower):
    con, record, spec = two_shower
    with pytest.raises(CapabilityError) as refused:
        negative_depth.summarise(con, record, spec, "c")
    assert refused.value.extra["field"] == "shower"


def test_a_stale_experiment_is_unavailable_with_the_reason_and_not_an_error():
    stale = ExperimentRecord(
        table_name="old", status="ready", schema_name=schemas.HITS_ALL_MODELS.name,
        schema_version=schemas.HITS_ALL_MODELS.version, derived_version=1)
    spec = filters.build(stale, e1_min=0.0, e1_max=20.0, e2_min=0.0, e2_max=20.0,
                         d_min=0.0, d_max=1000.0)
    # No event table exists: the answer must come from the capability, not from a query.
    block = negative_depth.summarise(duckdb.connect(), stale, spec)
    contract_check.check(block, "statistics", "negative_w")
    assert block["available"] is False and block["splits"] == [] and block["affected"] is None
    assert "rebuild" in block["reason"].lower()
    assert block["summary"].startswith("Negative-depth counts are unavailable")
    assert block["showers_per_event"] == 2


def test_an_aggregated_experiment_has_no_hits_to_count():
    events = ExperimentRecord(
        table_name="agg", status="ready", schema_name=schemas.STANDALONE_EVENTS.name,
        schema_version=schemas.STANDALONE_EVENTS.version, derived_version=1)
    spec = filters.build(events, e1_min=0.0, e1_max=20.0)
    block = negative_depth.summarise(duckdb.connect(), events, spec)
    assert block["available"] is False and "no hits" in block["reason"]


def test_an_empty_selection_is_served_not_refused(two_shower):
    con, record, _ = two_shower
    nothing = filters.build(record, e1_min=40.0, e1_max=50.0, e2_min=0.0, e2_max=20.0,
                            d_min=0.0, d_max=1000.0)
    block = negative_depth.summarise(con, record, nothing)
    contract_check.check(block, "statistics", "negative_w")
    assert block["available"] is True
    assert all(s["n_events"] == 0 and s["hits_fraction"] is None for s in block["splits"])
    assert block["affected"]["n"] == 0 and block["affected"]["mean"] is None
    assert block["summary"].endswith("no showers in this selection.")


def test_the_summary_is_one_typographic_line_with_its_intervals(two_shower):
    con, record, spec = two_shower
    block = negative_depth.summarise(con, record, spec)
    summary = block["summary"]
    assert summary.startswith(f"w < {MINUS}10⁻⁶ mm: ")
    assert signed_hyphens(summary) == [] and "\n" not in summary
    whole = block["splits"][0]
    assert f"{100 * whole['hits_fraction']:.2f}%" in summary
    assert f"{100 * whole['energy_fraction']:.2f}%" in summary
    assert "of events (either shower)" in summary and "[" in summary
    one = negative_depth.summarise(con, record, spec, "a")["summary"]
    assert "of showers" in one


def test_the_threshold_is_the_ingest_cut():
    assert negative_depth.THRESHOLD_MM == -ddl.NEG_DEPTH_MM == 1e-6
    assert negative_depth.threshold_label() == "10⁻⁶"
    sentences = negative_depth.rationale()
    assert f"z_local < {MINUS}10⁻⁶ mm" in sentences[0]
    assert all(signed_hyphens(text) == [] for text in sentences)


def test_the_block_is_small_enough_to_ride_in_a_frame_response(two_shower):
    con, record, spec = two_shower
    assert density.wire_size(negative_depth.summarise(con, record, spec)) < 3_000


def test_the_module_reads_the_event_table_only():
    """The structural rule of ``query/__init__``: a per-event quantity never comes from hit rows."""
    import inspect

    source = inspect.getsource(negative_depth)
    assert "proj_table" not in source and "hit_sql" not in source
    assert "event_table" in source


def test_wilson_is_the_shared_implementation(two_shower):
    """The share of events with any such hit is ``metrics.wilson_interval``, not a copy of it."""
    con, record, spec = two_shower
    whole = negative_depth.summarise(con, record, spec)["splits"][0]
    ref = metrics.wilson_interval(whole["events_with_any"], whole["n_events"])
    assert whole["events_with_any_ci95"] == [float(f"{ref.lo:.6g}"), float(f"{ref.hi:.6g}")]
