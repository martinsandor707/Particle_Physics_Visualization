"""``GET /api/statistics`` on the booted server: C1 against pandas, C9 against NumPy, over the hits.

The ``single_client`` server holds the two-shower baseline (two events, 1 000
hits) and a synthetic single-shower experiment (287 events, 8 573 hits). Every
reference here is recomputed from the projection table's *rows* with pandas or
NumPy - the describe table from the coordinates and energies, the
energy-weighted quartiles from an exact weighted order statistic, the negative
depth shares from ``z_local < -1e-6`` hit by hit - so the DuckDB aggregates,
the weighted histograms, the Group-1 event columns and the intervals are each
checked against something that shares none of their code. Hand-made event
tables for the cluster logic are in ``test_physics_statistics_c9.py``.
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from test_physics_statistics_c9 import check_splits

from calosrv.db import ddl, registry
from calosrv.query import density, hit_sql, sampling, statistics
from calosrv.stats import metrics
from calosrv.text import MINUS, signed_hyphens

#: Numbers are served to six significant figures: a relative error of at most 5e-6.
REL = 6e-6

SINGLE = SINGLE_HITS_TABLE
KEYS = {
    "lab": ["x", "y", "z", "energy"],
    "trans": ["dx", "dy", "dz", "energy"],
    "local": ["u", "v", "w", "rho", "energy"],
}
CASES = [
    (SINGLE, "local", "both"), (SINGLE, "trans", "a"), (SINGLE, "lab", "both"),
    (BASELINE_TABLE, "local", "both"), (BASELINE_TABLE, "local", "a"),
    (BASELINE_TABLE, "local", "b"), (BASELINE_TABLE, "trans", "b"), (BASELINE_TABLE, "lab", "both"),
]


# ------------------------------------------------------------------- helpers --

@pytest.fixture(scope="module")
def hits(single_client):
    """Each hit experiment's registry record and projection rows."""
    database = single_client.app.state.database
    out = {}
    with database.read_cursor() as con:
        for table in (SINGLE, BASELINE_TABLE):
            record = registry.require_ready(con, table)
            out[table] = (record, con.execute(f'SELECT * FROM "proj_{table}"').df())
    return out


def _get(client, table, **params):
    return client.get("/api/statistics", params={"table_name": table, **params})


def _body(client, table, **params):
    response = _get(client, table, **params)
    assert response.status_code == 200, response.text
    return response.json()


def _scope(df, shower):
    """The rows of the chosen showers: org 0 is A, org 1 and the 'A+B' rows (2) are B."""
    org = df.org.to_numpy()
    return {"a": org == 0, "b": org != 0, "both": np.ones(len(df), bool)}[shower]


def _coordinates(record, df, frame):
    """The frame's coordinates of every hit, from the stored columns and the lattice arrays."""
    if frame == "local":
        u, v, w = (df[c].to_numpy(np.float64) for c in ("xl", "yl", "zl"))
        return {"u": u, "v": v, "w": w, "rho": np.sqrt(u * u + v * v)}
    if frame == "trans":
        return {"dx": df.xt.to_numpy(np.float64), "dy": df.yt.to_numpy(np.float64),
                "dz": df.kt.to_numpy(np.float64) * hit_sql.layer_pitch(record)}
    lattice = record.lattice
    return {axis: np.asarray(getattr(lattice, axis).coords, np.float64)[df[f"i{axis}"].to_numpy()]
            for axis in "xyz"}


def _arrays(hits_, table, frame, shower):
    record, df = hits_[table]
    keep = _scope(df, shower)
    arrays = {k: v[keep] for k, v in _coordinates(record, df, frame).items()}
    arrays["energy"] = df.energy.to_numpy(np.float64)[keep]
    return arrays


def _weighted_quantile(values, weights, q):
    """The exact weighted order statistic: the first value whose cumulative weight reaches q."""
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    i = int(np.searchsorted(cumulative, q * cumulative[-1], side="left"))
    return float(values[order][min(i, values.size - 1)])


def _shower_rows(df):
    """``(event, p, n, nh, e, ne)`` of every shower, from the hit rows alone."""
    neg = df.zl.to_numpy(np.float64) < -1e-6
    energy = df.energy.to_numpy(np.float64)
    shower = np.where(df.org.to_numpy() == 0, 0, 1)
    p = np.where(shower == 0, df.e1.to_numpy(np.float64), df.e2.to_numpy(np.float64)) \
        if "e2" in df.columns else df.e1.to_numpy(np.float64)
    frame = pd.DataFrame({"event": df.event_number.to_numpy(), "shower": shower, "p": p,
                          "neg": neg, "e": energy, "ne": np.where(neg, energy, 0.0)})
    grouped = frame.groupby(["event", "shower"]).agg(
        p=("p", "first"), n=("neg", "size"), nh=("neg", "sum"), e=("e", "sum"), ne=("ne", "sum"))
    # Bracket access: ``Series.ne`` is a method, not the column.
    return [(int(event), float(r["p"]), int(r["n"]), int(r["nh"]), float(r["e"]), float(r["ne"]),
             int(shower_)) for (event, shower_), r in grouped.iterrows()]


def _showers(df, choice):
    keep = {"a": (0,), "b": (1,), "both": (0, 1)}[choice]
    return [row[:6] for row in _shower_rows(df) if row[6] in keep]


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# ---------------------------------------------------------------- C1: describe --

@pytest.mark.parametrize("table, frame, shower", CASES)
def test_describe_rows_match_pandas_over_the_projection_rows(single_client, hits, table, frame, shower):
    body = _body(single_client, table, coord_system=frame, shower=shower)
    describe = body["describe"]
    rows = {r["key"]: r for r in describe["rows"]}
    assert list(rows) == KEYS[frame] and describe["coord_system"] == frame
    _, df = hits[table]
    keep = _scope(df, shower)
    # The event table's own hit and event counts agree with the projection rows scanned.
    assert describe["n_hits"] == int(keep.sum())
    assert body["n_events"] == len(set(df.event_number.to_numpy()[keep]))

    for key, values in _arrays(hits, table, frame, shower).items():
        ref = pd.Series(values).describe()
        row = rows[key]
        assert row["count"] == int(ref["count"]) == describe["n_hits"]
        for ours, theirs in (("mean", "mean"), ("sd", "std"), ("min", "min"), ("q25", "25%"),
                             ("q50", "50%"), ("q75", "75%"), ("max", "max")):
            assert row[ours] == pytest.approx(ref[theirs], rel=REL, abs=1e-12), (key, ours)
        assert row["sd_population"] == pytest.approx(values.std(ddof=0), rel=REL)
        assert row["sd"] > row["sd_population"]          # ddof = 1 is the larger width
        assert row["unit"] == ("GeV" if key == "energy" else "mm")


@pytest.mark.parametrize("table, frame, shower", [
    (SINGLE, "local", "both"), (SINGLE, "lab", "both"), (BASELINE_TABLE, "trans", "b"),
])
def test_energy_weighted_columns_are_exact_to_one_bin(single_client, hits, table, frame, shower):
    body = _body(single_client, table, coord_system=frame, shower=shower)
    rows = {r["key"]: r for r in body["describe"]["rows"]}
    weights = _arrays(hits, table, frame, shower)["energy"]
    for key, values in _arrays(hits, table, frame, shower).items():
        row = rows[key]
        # The weighted mean is exact: sum(E a) / sum(E).
        assert row["ew_mean"] == pytest.approx(np.sum(weights * values) / weights.sum(), rel=REL), key
        for name, q in (("ew_q25", 0.25), ("ew_q50", 0.5), ("ew_q75", 0.75)):
            exact = _weighted_quantile(values, weights, q)
            if key == "energy":
                # 0.01-decade bins of log10 E: within a factor 10^0.01 of the exact order statistic.
                factor = 10 ** statistics.LOG_STEP * (1 + 1e-5)
                assert exact / factor <= row[name] <= exact * factor, (key, name)
            else:
                assert abs(row[name] - exact) <= statistics.FINE_MM + 1e-3, (key, name)
        assert row["ew_q25"] <= row["ew_q50"] <= row["ew_q75"]
    assert "different weighting" in body["describe"]["weighting_note"]


def test_the_weighting_is_a_separate_column_not_a_correction(single_client):
    body = _body(single_client, SINGLE, coord_system="local")
    energy = next(r for r in body["describe"]["rows"] if r["key"] == "energy")
    # Where the energy sits is far from where the hits are: the median hit is a dust hit.
    assert energy["ew_q50"] > 5 * energy["q50"] and energy["ew_mean"] > energy["mean"]


def test_the_lab_frame_adds_the_labelled_shifted_z_row(single_client, hits):
    body = _body(single_client, SINGLE, coord_system="lab")
    describe = body["describe"]
    shifted = describe["shifted_row"]
    assert shifted["label"] == f"z {MINUS} 3649 mm" and shifted["key"] == "z_shifted"
    assert shifted["display_offset_mm"] == ddl.CORE_SHIFT_Z_MM == 3649.0
    ref = pd.Series(_arrays(hits, SINGLE, "lab", "both")["z"] - ddl.CORE_SHIFT_Z_MM).describe()
    for ours, theirs in (("mean", "mean"), ("sd", "std"), ("min", "min"), ("q25", "25%"),
                         ("q50", "50%"), ("q75", "75%"), ("max", "max")):
        assert shifted[ours] == pytest.approx(ref[theirs], rel=REL, abs=1e-9), ours
    # The first sampling layer is 13.3999 mm below the notebook's front face, as measured.
    assert shifted["min"] == pytest.approx(13.3999, abs=1e-4)
    # The shift moves locations only: the stored z row stays raw.
    z = next(r for r in describe["rows"] if r["key"] == "z")
    assert z["min"] == pytest.approx(3662.4, abs=1e-3) and "display_offset_mm" not in z
    assert shifted["sd"] == z["sd"] and shifted["count"] == z["count"]
    # The served z is rounded to six significant figures (0.01 mm), so the two agree to that.
    assert shifted["mean"] == pytest.approx(z["mean"] - 3649.0, abs=6e-3)
    assert shifted["ew_q50"] == pytest.approx(z["ew_q50"] - 3649.0, abs=6e-3)
    assert any("raw z" in note for note in body["notes"])


@pytest.mark.parametrize("frame", ["trans", "local"])
def test_only_the_lab_frame_has_a_shifted_row(single_client, frame):
    assert _body(single_client, SINGLE, coord_system=frame)["describe"]["shifted_row"] is None


def test_the_local_frame_reports_the_two_dimensional_radius(single_client, hits):
    body = _body(single_client, SINGLE, coord_system="local")
    rho = next(r for r in body["describe"]["rows"] if r["key"] == "rho")
    u, v = (_coordinates(*hits[SINGLE], "local")[k] for k in ("u", "v"))
    assert rho["mean"] == pytest.approx(np.hypot(u, v).mean(), rel=REL)
    assert "ρ" in rho["label"] and rho["unit"] == "mm"
    note = next(n for n in body["notes"] if "ρ" in n)
    assert "2-D transverse radius" in note and "3-D distance" in note
    # core.py's 3-D r_local is a different quantity and has no row anywhere.
    assert all(r["key"] != "r_local" for r in body["describe"]["rows"])


def test_the_default_frame_is_local_and_the_default_shower_is_both(single_client):
    body = _body(single_client, SINGLE)
    assert body["describe"]["coord_system"] == "local" and body["meta"]["shower"] == "both"
    assert single_client.get("/api/statistics").status_code == 200


def test_the_shower_scopes_partition_a_two_shower_experiment(single_client, hits):
    counts = {s: _body(single_client, BASELINE_TABLE, shower=s)["describe"]["n_hits"]
              for s in ("a", "b", "both")}
    assert counts["a"] + counts["b"] == counts["both"] == len(hits[BASELINE_TABLE][1])
    assert counts["a"] == int((hits[BASELINE_TABLE][1].org == 0).sum())
    body = _body(single_client, BASELINE_TABLE, shower="b")
    assert any("A+B" in note for note in body["notes"])
    assert not any("A+B" in note for note in _body(single_client, BASELINE_TABLE, shower="a")["notes"])
    # A single shower per event: 'a' and 'both' are the same selection.
    both = _body(single_client, SINGLE, shower="both")["describe"]["rows"]
    assert both == _body(single_client, SINGLE, shower="a")["describe"]["rows"]


def test_the_estimator_text_names_what_a_row_is(single_client):
    describe = _body(single_client, SINGLE)["describe"]
    assert "ddof = 1" in describe["estimator"] and "ddof = 0" in describe["estimator"]
    assert "No standard error of a mean is quoted" in describe["estimator"]


# ------------------------------------------------------------ C1: low-N and empty --

def test_an_empty_selection_is_served_with_empty_rows(single_client):
    body = _body(single_client, SINGLE, e1_min=0.1, e1_max=0.2)
    contract_check.check(body, "statistics")
    assert body["n_events"] == 0 and body["describe"]["n_hits"] == 0
    for row in body["describe"]["rows"]:
        assert row["count"] == 0 and row["mean"] is None and row["ew_q50"] is None
        assert row["note"] == "No hits in this selection."
    assert "No events match the current selection." in body["meta"]["warnings"]
    assert body["negative_w"]["summary"].endswith("no showers in this selection.")
    assert body["negative_w"]["affected"]["n"] == 0


def test_a_separation_window_with_no_event_is_served_empty_on_two_shower_data(single_client):
    body = _body(single_client, BASELINE_TABLE, d_min=0.0, d_max=1.0)
    contract_check.check(body, "statistics")
    assert body["n_events"] == 0 and body["describe"]["n_hits"] == 0
    assert all(r["count"] == 0 for r in body["describe"]["rows"])
    assert all(s["n_events"] == 0 for s in body["negative_w"]["splits"])
    # Letting the undefined-D events in is a valid request on two-shower data.
    assert _get(single_client, BASELINE_TABLE, include_undefined_d="true").status_code == 200


def test_a_single_hit_event_gets_its_value_and_no_spread(single_client, hits):
    database = single_client.app.state.database
    with database.read_cursor() as con:
        (p,) = con.execute(f'SELECT e1 FROM "event_{SINGLE}" WHERE n_hits = 1').fetchone()
    body = _body(single_client, SINGLE, e1_min=p - 1e-6, e1_max=p + 1e-6)
    assert body["n_events"] == 1 and body["describe"]["n_hits"] == 1
    for row in body["describe"]["rows"]:
        assert row["count"] == 1 and row["sd"] is None and "N = 1" in row["note"]
        assert row["min"] == row["max"] == row["mean"]
    one = next(s for s in body["negative_w"]["splits"] if s["n_events"] == 1)
    assert one["hits_fraction_ci95"] is None and "N = 1 event" in one["note"]
    contract_check.check(body, "statistics")


def test_the_low_n_notes_follow_the_describe_floors():
    assert statistics._note(0) == "No hits in this selection."
    assert "N = 1" in statistics._note(1) and "interpolate" not in statistics._note(1)
    assert "1 d.o.f." in statistics._note(2) and "interpolate" in statistics._note(2)
    assert "interpolate" in statistics._note(19)
    assert statistics._note(20) == ""


# ----------------------------------------------------------------- C9: negative depth --

def test_negative_depth_matches_numpy_over_the_hits_of_a_single_shower_experiment(single_client, hits):
    body = _body(single_client, SINGLE)
    block = body["negative_w"]
    record, df = hits[SINGLE]
    contract_check.check(block, "statistics", "negative_w")
    assert block["available"] and block["showers_per_event"] == 1 and block["unit"] == "shower"
    assert block["threshold_mm"] == 1e-6

    check_splits(block["splits"], _showers(df, "both"), 1)
    whole = block["splits"][0]
    neg = df.zl.to_numpy(np.float64) < -1e-6
    energy = df.energy.to_numpy(np.float64)
    assert whole["hits"] == int(neg.sum()) and whole["hits_total"] == len(df)
    assert whole["hits_fraction"] == pytest.approx(neg.mean(), rel=REL)
    assert whole["energy_gev"] == pytest.approx(energy[neg].sum(), rel=REL)
    assert whole["energy_fraction"] == pytest.approx(energy[neg].sum() / energy.sum(), rel=REL)
    assert whole["events_with_any"] == len(set(df.event_number.to_numpy()[neg]))
    assert body["n_events"] == whole["n_events"] == df.event_number.nunique()
    # The synthetic electron-like file has no p < 1 GeV events: an empty split is served, not dropped.
    low = next(s for s in block["splits"] if s["key"] == "low")
    assert low["n_events"] == 0 and low["note"] == "No showers in this split."

    # The affected-shower statistics: the notebook's describe() of the per-event fraction.
    per_event = pd.DataFrame({"event": df.event_number.to_numpy(), "neg": neg}).groupby("event").neg
    fractions = (per_event.sum() / per_event.size())
    fractions = fractions[fractions > 0].to_numpy()
    affected = block["affected"]
    contract_check.check(affected, "statistics", "negative_w_affected")
    assert affected["n"] == fractions.size == whole["events_with_any"]
    assert affected["mean"] == pytest.approx(fractions.mean(), rel=REL)
    assert affected["sd"] == pytest.approx(fractions.std(ddof=1), rel=REL)
    assert affected["min"] == pytest.approx(fractions.min(), rel=REL)
    assert affected["max"] == pytest.approx(fractions.max(), rel=REL)
    for key, q in (("q25", 25), ("q50", 50), ("q75", 75)):
        assert affected[key] == pytest.approx(np.percentile(fractions, q), rel=REL)
    assert affected["n_over_half"] == int((fractions > 0.5).sum())

    # Wilson on events, the shared implementation, and the same interval on showers (one per event).
    ref = metrics.wilson_interval(whole["events_with_any"], whole["n_events"])
    assert whole["events_with_any_ci95"] == [float(f"{ref.lo:.6g}"), float(f"{ref.hi:.6g}")]
    assert whole["showers_with_any_ci95"] == whole["events_with_any_ci95"]


@pytest.mark.parametrize("shower", ["both", "a", "b"])
def test_negative_depth_clusters_the_two_showers_of_an_event(single_client, hits, shower):
    body = _body(single_client, BASELINE_TABLE, shower=shower)
    block = body["negative_w"]
    _, df = hits[BASELINE_TABLE]
    per_event = 2 if shower == "both" else 1
    assert block["showers_per_event"] == per_event
    check_splits(block["splits"], _showers(df, shower), per_event)
    whole = block["splits"][0]
    keep = _scope(df, shower)
    neg = df.zl.to_numpy(np.float64) < -1e-6
    assert whole["hits"] == int((neg & keep).sum()) and whole["hits_total"] == int(keep.sum())
    if shower == "both":
        # Two showers per event: the share of showers has no interval, the share of events has.
        assert whole["showers_with_any_ci95"] is None and whole["events_with_any_ci95"] is not None
        assert "of events (either shower)" in block["summary"]
    else:
        assert whole["showers_with_any_ci95"] == whole["events_with_any_ci95"]
        assert "of showers" in block["summary"]


def test_the_selection_reaches_both_cards(single_client, hits):
    """One filter, one set of events: C1's hits and C9's showers describe the same selection."""
    _, df = hits[SINGLE]
    p = df.groupby("event_number").e1.first()
    lo, hi = 5.0, 12.5
    chosen = p[(p >= lo) & (p <= hi)].index
    body = _body(single_client, SINGLE, e1_min=lo, e1_max=hi)
    assert body["n_events"] == len(chosen)
    assert body["describe"]["n_hits"] == int(df.event_number.isin(chosen).sum())
    assert body["negative_w"]["splits"][0]["n_events"] == len(chosen)
    assert body["negative_w"]["splits"][0]["hits_total"] == body["describe"]["n_hits"]
    check_splits(body["negative_w"]["splits"],
                 [s for s in _showers(df, "both") if lo <= s[1] <= hi], 1)


def test_negative_depth_is_defined_in_the_local_frame_whatever_frame_is_drawn(single_client):
    blocks = [_body(single_client, SINGLE, coord_system=frame)["negative_w"] for frame in KEYS]
    assert blocks[0] == blocks[1] == blocks[2]


# --------------------------------------------------------------------- refusals --

def test_an_aggregated_experiment_has_no_hits_to_describe(single_client):
    response = _get(single_client, SINGLE_EVENTS_TABLE)
    assert response.status_code == 422
    problem = response.json()
    assert problem["type"] == "/problems/unsupported-capability"
    assert problem["capability"] == "statistics" and problem["field"] == "table_name"
    assert problem["kind"] == "single_shower_events" and "no hits" in problem["reason"]


@pytest.mark.parametrize("table, params, field", [
    (SINGLE, {"coord_system": "canonical"}, "coord_system"),
    (SINGLE, {"shower": "b"}, "shower"),
    (SINGLE, {"shower": "c"}, "shower"),
    (BASELINE_TABLE, {"shower": "c"}, "shower"),
    (SINGLE, {"e2_min": 1.0}, "e2_min"),
    (SINGLE, {"d_max": 100.0}, "d_max"),
    (SINGLE, {"include_undefined_d": "true"}, "include_undefined_d"),
])
def test_bad_parameters_are_refused_naming_the_field(single_client, table, params, field):
    response = _get(single_client, table, **params)
    assert response.status_code == 422
    assert response.json()["field"] == field


# ---------------------------------------------------------------------- contract --

@pytest.mark.parametrize("table, frame, shower", CASES)
def test_every_response_satisfies_the_contract(single_client, table, frame, shower):
    contract_check.check(_body(single_client, table, coord_system=frame, shower=shower), "statistics")


def test_the_contract_is_strict_enough_to_catch_a_regression(single_client):
    body = _body(single_client, SINGLE, coord_system="lab")
    mutations = [
        lambda b: b["describe"]["rows"][0].pop("ew_q50"),
        lambda b: b["describe"].pop("n_hits"),
        lambda b: b["describe"]["shifted_row"].pop("label"),
        lambda b: b["negative_w"]["splits"].pop(),
        lambda b: b["negative_w"]["splits"][0].pop("hits_total"),
        lambda b: b["negative_w"]["splits"][1].update(key="other"),
        lambda b: b["negative_w"].update(affected=None),
        lambda b: b["negative_w"].pop("intervals"),
        lambda b: b["negative_w"].update(available=False),
        lambda b: b.pop("n_events"),
    ]
    for mutate in mutations:
        broken = copy.deepcopy(body)
        mutate(broken)
        with pytest.raises(contract_check.ContractError):
            contract_check.check(broken, "statistics")
    unavailable = {"available": False, "reason": "why", "threshold_mm": 1e-6, "unit": "shower",
                   "showers_per_event": 2, "splits": [], "affected": None, "summary": "why"}
    contract_check.check(unavailable, "statistics", "negative_w")
    with pytest.raises(contract_check.ContractError):
        contract_check.check({**unavailable, "available": True}, "statistics", "negative_w")


def test_the_payload_is_small(single_client):
    sizes = [density.wire_size(_body(single_client, t, coord_system=f, shower=s)) for t, f, s in CASES]
    assert max(sizes) < density.RESPONSE_LIMIT / 10, sizes
    assert min(sizes) > 1_000


# ----------------------------------------------------------------- typography --

def test_every_sentence_sets_its_minus_signs_typographically(single_client):
    for frame in KEYS:
        body = _body(single_client, SINGLE, coord_system=frame)
        for text in _strings(body):
            assert signed_hyphens(text) == [], text
        assert body["negative_w"]["summary"].startswith(f"w < {MINUS}10⁻⁶ mm")
    lab = _body(single_client, SINGLE, coord_system="lab")
    assert f"z {MINUS} 3649 mm" in lab["describe"]["shifted_row"]["label"]
    assert any(f"z {MINUS} 3649 mm" in note for note in lab["notes"])


# ------------------------------------------------------------------ cache and preview --

def test_a_repeated_selection_is_served_from_the_physics_cache(single_client):
    first = _body(single_client, SINGLE, coord_system="trans", e1_min=2.61, e1_max=17.37)
    second = _body(single_client, SINGLE, coord_system="trans", e1_min=2.61, e1_max=17.37)
    assert first["meta"]["cached"] is False and second["meta"]["cached"] is True
    assert first["describe"] == second["describe"]
    # Another frame or shower scope is another entry.
    other = _body(single_client, SINGLE, coord_system="lab", e1_min=2.61, e1_max=17.37)
    assert other["meta"]["cached"] is False
    # A bound looser than the data is the same selection as the dataset's own bounds.
    whole = _body(single_client, SINGLE, coord_system="lab")
    loose = _body(single_client, SINGLE, coord_system="lab", e1_min=0.0, e1_max=25.0)
    assert loose["meta"]["cached"] is True and loose["describe"] == whole["describe"]


def test_preview_serves_the_table_from_the_sample_and_keeps_the_counts_exact(
        single_client, monkeypatch):
    exact = _body(single_client, SINGLE, coord_system="local")
    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    preview = _body(single_client, SINGLE, coord_system="local", preview="true")
    assert exact["meta"]["exact"] is True and preview["meta"]["exact"] is False
    assert preview["meta"]["sample_percent"] == 10.0
    assert any("sample" in w for w in preview["meta"]["warnings"])
    assert any(n.startswith("Preview: computed from a 10% unbiased sample") for n in preview["notes"])

    database = single_client.app.state.database
    with database.read_cursor() as con:
        sample = con.execute(f'SELECT xl, yl, zl, energy FROM "proj_{SINGLE}_s10"').df()
    rows = {r["key"]: r for r in preview["describe"]["rows"]}
    assert rows["u"]["count"] == len(sample) < exact["describe"]["n_hits"]
    ref = sample.xl.astype(np.float64).describe()
    assert rows["u"]["mean"] == pytest.approx(ref["mean"], rel=REL, abs=1e-9)
    assert rows["u"]["sd"] == pytest.approx(ref["std"], rel=REL)
    # The event counts and the negative-depth block come from the event table: exact either way.
    assert preview["describe"]["n_hits"] == exact["describe"]["n_hits"]
    assert preview["n_events"] == exact["n_events"]
    assert preview["negative_w"] == exact["negative_w"]
    contract_check.check(preview, "statistics")
    # The sample never contaminates the exact entry.
    assert _body(single_client, SINGLE, coord_system="local")["describe"] == exact["describe"]


def test_the_negative_depth_module_is_what_the_route_serves(single_client):
    """The Local frame reuses ``summarise``; the route must serve exactly its result."""
    from calosrv.query import filters, negative_depth

    body = _body(single_client, SINGLE)
    database = single_client.app.state.database
    with database.read_cursor() as con:
        record = registry.require_ready(con, SINGLE)
        direct = negative_depth.summarise(con, record, filters.build(record), "both")
    assert body["negative_w"] == direct


# ------------------------------------------------------------------------ stale --

def test_a_stale_experiment_still_serves_the_table_and_says_why_the_counts_are_unavailable(single_client):
    """Derived before the Group-1 columns existed: C1 reads the projection table and works as before."""
    database = single_client.app.state.database
    exact = _body(single_client, BASELINE_TABLE, coord_system="local")
    with database.read_cursor() as con:
        (before,) = con.execute('SELECT derived_version FROM "experiment" WHERE table_name = ?',
                                [BASELINE_TABLE]).fetchone()
    with database.write_lock() as con:
        con.execute('UPDATE "experiment" SET derived_version = 1 WHERE table_name = ?', [BASELINE_TABLE])
    try:
        response = _get(single_client, BASELINE_TABLE, coord_system="local")
        assert response.status_code == 200, response.text
        body = response.json()
        contract_check.check(body, "statistics")
        block = body["negative_w"]
        assert block["available"] is False and block["splits"] == [] and block["affected"] is None
        assert "rebuild" in block["reason"].lower() and block["summary"].startswith("Negative-depth counts")
        assert body["describe"] == exact["describe"] and body["n_events"] == exact["n_events"]
        assert not any("w = z_local" in note for note in body["notes"])
    finally:
        with database.write_lock() as con:
            con.execute('UPDATE "experiment" SET derived_version = ? WHERE table_name = ?',
                        [before, BASELINE_TABLE])
    assert _body(single_client, BASELINE_TABLE)["negative_w"]["available"] is True
