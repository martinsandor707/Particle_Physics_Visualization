"""B3 on ``GET /api/energy-distribution?slice_by=momentum``, served by booted apps.

The momentum-sliced view rides the energy panel's machinery, so the first test
pins the default D-sliced payload byte for byte against the snapshot taken
before the momentum code existed (``tests/golden/energy_default.json``), and
the synthetic-file tests pin four more D payloads that reach every mark of the
ladder - histograms, curves, strips, core refits, robust widths, clipping, the
Rice bin count - and one that reaches the budget guard
(``tests/golden/energy_synthetic_*.json``). Each is compared on the bytes on
the wire with only the timing fields of ``meta`` cut out. Regenerate them only
when the D payload is *meant* to change::

    env CALOSRV_WRITE_GOLDEN=1 .venv/bin/python -m pytest -q \\
        tests/test_energy_momentum_api.py -k "byte_identical"

Every momentum response is validated against ``tests/contracts/energy_momentum``,
measured against the 100 KB contract, scanned for hyphen-signed numbers and
checked for its counting invariants. The tests are grouped by booted fixture -
``client``, then ``synthetic_client``, then ``single_client`` - because each
boot resets the process-wide database the previous one served from.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import naming
from calosrv.query import density
from calosrv.query.energy import CENSORED_AGGREGATE_NOTICE
from calosrv.stats import gaussian, histogram
from calosrv.text import signed_hyphens

GOLDEN = Path(__file__).resolve().parent / "golden" / "energy_default.json"
ROUTE = "/api/energy-distribution"

#: Meta fields that measure the request rather than describe the payload.
TIMING_FIELDS = ("query_ms", "total_ms", "cached")

#: The same fields on the wire: adjacent, in ``ApiMeta`` order, once per body.
WIRE_TIMING = re.compile(rb'"query_ms":[^,]*,"total_ms":[^,]*,"cached":(?:true|false),')

#: The byte counts a budget-guard notice quotes. They measure the body served,
#: timing digits included, so they move with the clock and are cut as well.
WIRE_SIZES = re.compile(rb"[0-9]{1,3}(?:,[0-9]{3})* bytes")

#: The guard's last word when even its coarsest rendering is over the contract.
STILL_OVER = "served as it is"


def _normalised(body: dict) -> str:
    """The payload as the snapshot stores it: timing fields dropped, key order kept."""
    meta = {k: v for k, v in body["meta"].items() if k not in TIMING_FIELDS}
    return json.dumps({**body, "meta": meta}, indent=1, ensure_ascii=False) + "\n"


def _wire(response) -> bytes:
    """The response's bytes as served, the timing fields cut out and nothing re-serialised."""
    body, count = WIRE_TIMING.subn(b"", response.content)
    assert count == 1, count
    return body


def _compact(text: str) -> bytes:
    """A stored snapshot as the route puts it on the wire (``density.wire_size``'s form)."""
    return json.dumps(json.loads(text), ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def _invariants(body: dict) -> None:
    """What every momentum payload must satisfy, whatever its selection."""
    two = body["slice_counts_by_shower"]["b"] is not None
    showers = ("a", "b") if two else ("a",)
    if not two:
        assert body["outside_slices"]["b"] is None and body["no_deposit"]["b"] is None
    # Every shower of the selection is in one slice, outside all, or has no deposit.
    for key in showers:
        counts = body["slice_counts_by_shower"][key]
        assert sum(counts.values()) + body["outside_slices"][key] + body["no_deposit"][key] \
            == body["n_events"]
    for index, total in body["slice_counts"].items():
        assert total == sum(body["slice_counts_by_shower"][k][index] for k in showers)
    # A series per populated (slice, shower), its N that shower's count there.
    for series in body["series"]:
        assert series["fit"]["n"] == body["slice_counts_by_shower"][series["shower"]][
            str(series["slice"])]
    # An axis per populated slice, all sharing the one bin count.
    populated = [int(k) for k, v in body["slice_counts"].items() if v]
    axes = {a["slice"]: a for a in body["slice_axes"]}
    assert sorted(axes) == sorted(populated)
    for a in axes.values():
        assert a["lo"] < a["hi"]
        mine = [s for s in body["series"] if s["slice"] == a["slice"]]
        for s in mine:
            if s["histogram"] is not None:
                assert len(s["histogram"]["counts"]) == body["axis"]["bins"]
            if s["curve"]["y"]:
                assert len(s["curve"]["y"]) == body["axis"]["curve_points"]
        # Only the series drawn as histograms set the range.
        robust = [s["key"] for s in mine if s["draw"] == "histogram"]
        assert all(s["fit"]["n"] >= histogram.MIN_HISTOGRAM_SAMPLES for s in mine
                   if s["key"] in robust)
        assert a["provisional"] == (not robust)
        assert a["driven_by"] == (robust or [s["key"] for s in mine])
        # The clip block counts against the axis as drawn, as n_outside_axis does.
        clip = a["clipping"]
        assert clip["n_total"] == a["n_values"] == sum(s["fit"]["n"] for s in mine)
        assert clip["n_outside"] == a["n_outside_axis"] == clip["n_below"] + clip["n_above"]
        # Percentiles need twenty values (stats/clip.py); fewer give their full range.
        assert clip["rule"] == ("percentile" if clip["n_basis"] >= 20 else "full_range")
        # The marker carries the low-N labels its N calls for.
        for key in showers:
            marker = a["momentum"][key]
            low_n = marker["low_n"]
            n = marker["n"]
            assert (low_n is None) == (n == 0 or n >= gaussian.MIN_ROBUST_SAMPLES)
            if low_n is not None and gaussian.MIN_MOMENT_SAMPLES <= n < gaussian.MIN_CORE_SAMPLES:
                assert {"sd_se", "sd_ci95", "c4"} <= set(low_n)
    for series in body["series"]:
        if series["histogram"] is not None:
            assert len(series["histogram"]["counts"]) == body["axis"]["bins"]
        if series["curve"]["y"]:
            assert len(series["curve"]["y"]) == body["axis"]["curve_points"]


def _momentum(client, **params) -> tuple[dict, int]:
    """One momentum view, checked against the contract, the budget and the rules."""
    response = client.get(ROUTE, params={"slice_by": "momentum", **params})
    assert response.status_code == 200, response.text
    body = response.json()
    contract_check.check(body, "energy_momentum")
    size = len(response.content)
    assert size == density.wire_size(body)
    assert size < density.RESPONSE_LIMIT or any(
        STILL_OVER in w for w in body["meta"]["warnings"]), (params, size)
    for path, text in _strings(body):
        if path.endswith(".table_name"):
            continue
        assert not signed_hyphens(text), (path, signed_hyphens(text))
    _invariants(body)
    return body, size


def _refused(client, params: dict, field: str, capability: str | None = None) -> dict:
    response = client.get(ROUTE, params=params)
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["field"] == field, problem
    if capability is not None:
        contract_check.check(problem, "capability_problem")
        assert problem["capability"] == capability
    return problem


def _event_table(client, table_name: str | None = None) -> str:
    if table_name is None:
        experiments = client.get("/api/experiments").json()["experiments"]
        table_name = next(e["table_name"] for e in experiments if e["status"] == "ready")
    return naming.quote(naming.event_table(table_name))


def _sql(client, sql: str) -> list[tuple]:
    with client.app.state.database.read_cursor() as con:
        return con.execute(sql).fetchall()


def _window_counts(client, table: str, column: str, slices: list[dict]) -> dict[str, int]:
    """Showers per window, counted in SQL on the stored momentum as DOUBLE."""
    p = f"CAST({column} AS DOUBLE)"
    parts = ", ".join(
        f"count(*) FILTER (WHERE {p} >= {s['lo']!r} AND {p} < {s['hi']!r})" for s in slices)
    (row,) = _sql(client, f"SELECT {parts} FROM {table}")
    return {str(s["index"]): int(n) for s, n in zip(slices, row)}


def _bin_counts(client, table: str, column: str, slices: list[dict]) -> dict[str, int]:
    found = dict(_sql(client, f"SELECT {column}, count(*) FROM {table} GROUP BY 1"))
    return {str(s["index"]): int(found.get(int(s["lo"]), 0)) for s in slices}


# ------------------------------------------------------------------ client --


def test_default_d_payload_is_byte_identical(client):
    response = client.get(ROUTE)
    assert response.status_code == 200, response.text
    text = _normalised(response.json())
    if os.environ.get("CALOSRV_WRITE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8")
    assert GOLDEN.is_file(), f"missing {GOLDEN}; see this module's docstring"
    stored = GOLDEN.read_text(encoding="utf-8")
    assert text == stored, "the default D-sliced energy payload moved"
    # And on the wire, where a re-serialisation could not hide a change of
    # float formatting or key order.
    assert _wire(response) == _compact(stored)


def test_the_d_panel_is_explicit_and_carries_no_momentum_key(client):
    default = client.get(ROUTE).json()
    explicit = client.get(ROUTE, params={"slice_by": "d"}).json()
    for body in (default, explicit):
        body["meta"] = {k: v for k, v in body["meta"].items() if k not in TIMING_FIELDS}
    assert explicit == default
    assert not {"slice_by", "slice_axes", "slicing", "counted"} & set(default)


def test_the_baseline_slices_by_momentum_on_request(client):
    body, _ = _momentum(client)
    # Its four showers sit at 2.71, 12.5, 17.9 and 6.39 GeV: in no notebook window.
    assert body["outside_slices"] == {"a": 2, "b": 2}
    assert body["series"] == [] and body["series_set"] == "truth"
    assert body["meta"]["network"] is None
    assert any("in no slice" in w for w in body["meta"]["warnings"])

    windows, _ = _momentum(client, p_slices="2.7,6.4,12.5,17.9", series="all")
    assert {(s["slice"], s["shower"]) for s in windows["series"]} == {
        (0, "a"), (1, "b"), (2, "b"), (3, "a")}
    assert windows["meta"]["network"] == {"model": "segmentation", "frame": "absolute"}
    model, _ = _momentum(client, p_slices="bins", series="model", coord_system="local")
    assert model["meta"]["network"] == {"model": "segmentation", "frame": "local"}
    assert {s["key"] for s in model["series"]} == {"e_a_pred", "e_b_pred"}
    # The truth split names the frame it was taken in, though no network made it.
    truth, _ = _momentum(client, p_slices="bins", coord_system="trans")
    assert truth["meta"]["network"] is None and truth["segmentation_frame"] == "trans"
    assert model["segmentation_frame"] == "local"


def test_an_empty_momentum_selection_qualifies_no_energy(client):
    body, _ = _momentum(client, e1_min=100.0, e1_max=200.0)
    assert body["series"] == [] and body["calibration"]["applied"] is False
    warnings = body["meta"]["warnings"]
    assert not any("not calibrated" in w for w in warnings)
    assert any(w.startswith("No showers in this selection fall in") for w in warnings)


def test_a_tiny_half_width_labels_its_window_with_the_minus_sign(client):
    body, _ = _momentum(client, p_slices="5", p_half_width=0.00001)   # _momentum scans it
    assert [s["label"] for s in body["slices"]] == ["5 ± 1e−05 GeV"]


@pytest.mark.parametrize("params,field", [
    ({"slice_by": "momentum", "p_slices": "1e308", "p_half_width": 1e308}, "p_half_width"),
    ({"slice_by": "momentum", "p_half_width": 11}, "p_half_width"),
    ({"slice_by": "momentum", "p_slices": "1e308"}, "p_slices"),
    ({"slice_by": "momentum", "p_slices": "5,1001"}, "p_slices"),
    ({"p_slices": "bins"}, "p_slices"),
    ({"p_half_width": 1.0}, "p_half_width"),
    ({"series": "all"}, "series"),
    ({"slice_by": "d", "p_slices": "notebook"}, "p_slices"),
    ({"slice_by": "momentum", "d_edges": "50,100"}, "d_edges"),
    ({"slice_by": "energy"}, "slice_by"),
    ({"slice_by": "momentum", "p_slices": "1,1.5"}, "p_slices"),
    ({"slice_by": "momentum", "p_slices": "1,2,x"}, "p_slices"),
    ({"slice_by": "momentum", "p_slices": "bins", "p_half_width": 0.3}, "p_half_width"),
    ({"slice_by": "momentum", "p_half_width": 0}, "p_half_width"),
    ({"slice_by": "momentum", "p_half_width": "nan"}, "p_half_width"),
    ({"slice_by": "momentum", "series": "both"}, "series"),
    ({"slice_by": "momentum", "coord_system": "polar"}, "coord_system"),
])
def test_parameters_of_the_other_slicing_are_refused(client, params, field):
    _refused(client, params, field)


# -------------------------------------------------------- synthetic_client --

#: D payloads of the synthetic low-N file pinned on the wire: the default; an
#: explicit bin count; another frame's network; the eight-slice preset that
#: puts every low-N rung in a slice of its own; and that preset at 20 bins
#: under a 30,000-byte contract, which walks every step of the budget guard -
#: the curves, the bins 20 → 10 → 8 - to "served as it is".
SYNTHETIC_D = {
    "default": ({}, None),
    "bins20": ({"bins": 20}, None),
    "trans": ({"coord_system": "trans"}, None),
    "edges": ({"d_edges": "50,100,150,200,250,300,350"}, None),
    "guard": ({"d_edges": "50,100,150,200,250,300,350", "bins": 20}, 30_000),
}


@pytest.mark.parametrize("case", list(SYNTHETIC_D))
def test_synthetic_d_payload_is_byte_identical(synthetic_client, monkeypatch, case):
    params, limit = SYNTHETIC_D[case]
    if limit is not None:
        monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)
    response = synthetic_client.get(ROUTE, params=params)
    assert response.status_code == 200, response.text
    wire = WIRE_SIZES.sub(b"# bytes", _wire(response)) + b"\n"
    if limit is not None:
        # The size the still-over notice quotes is the size served, and a D
        # panel has no series to drop.
        (still,) = [w for w in response.json()["meta"]["warnings"] if STILL_OVER in w]
        assert f"still {len(response.content):,} bytes" in still
        assert "fewer series" not in still
    golden = GOLDEN.parent / f"energy_synthetic_{case}.json"
    if os.environ.get("CALOSRV_WRITE_GOLDEN") == "1":
        golden.write_bytes(wire)
    assert golden.is_file(), f"missing {golden}; see this module's docstring"
    assert wire == golden.read_bytes(), f"the D-sliced energy payload moved ({case})"


def test_the_synthetic_d_goldens_reach_every_mark():
    """What the snapshots above pin, so a regenerated one cannot quietly pin less."""
    bodies = {case: json.loads((GOLDEN.parent / f"energy_synthetic_{case}.json").read_bytes())
              for case in SYNTHETIC_D}
    edges = bodies["edges"]["series"]
    assert {s["draw"] for s in edges} == {"strip", "curve+strip", "histogram"}
    assert {s["fit"]["estimator"] for s in edges} >= {
        "mean_only", "moments_1dof", "moments", "core_refit"}
    assert any(s["fit"]["shape_testable"] for s in edges)
    assert bodies["bins20"]["axis"]["bins"] == 20
    assert bodies["default"]["axis"]["bins"] != 20
    assert bodies["trans"]["meta"]["network"]["frame"] == "trans"
    guard = bodies["guard"]
    assert guard["axis"]["bins"] == histogram.MIN_BINS
    warnings = guard["meta"]["warnings"]
    assert any(w.startswith("Density curves sampled at") for w in warnings)
    assert any(w.startswith("Histograms drawn with") for w in warnings)
    assert any(STILL_OVER in w for w in warnings)


def test_too_many_two_shower_series_are_refused_naming_p_slices(synthetic_client):
    """Slices times series beyond the measured limit is a 422; at the limit it is served."""
    windows = ",".join(f"{0.4 + 0.8 * k:g}" for k in range(24))
    problem = _refused(synthetic_client, {"slice_by": "momentum", "p_slices": windows,
                                          "p_half_width": 0.4}, "p_slices")
    assert "48 fitted series" in problem["detail"] and "at most 40" in problem["detail"]
    twenty = ",".join(f"{0.4 + 0.8 * k:g}" for k in range(20))
    body, size = _momentum(synthetic_client, p_slices=twenty, p_half_width=0.4)
    assert size < density.RESPONSE_LIMIT and len(body["slices"]) == 20
    eleven = ",".join(f"{1 + 1.5 * k:g}" for k in range(11))
    _refused(synthetic_client, {"slice_by": "momentum", "p_slices": eleven, "series": "all"},
             "p_slices")
    ten = ",".join(f"{1 + 1.5 * k:g}" for k in range(10))
    body, size = _momentum(synthetic_client, p_slices=ten, series="all")
    assert size < density.RESPONSE_LIMIT
    # The 1 GeV bins with all four series stay refused on series, as decided.
    _refused(synthetic_client, {"slice_by": "momentum", "p_slices": "bins", "series": "all"},
             "series")


def test_two_shower_windows_slice_each_shower_by_its_own_momentum(synthetic_client):
    body, _ = _momentum(synthetic_client)
    table = _event_table(synthetic_client)
    assert body["slicing"]["mode"] == "notebook" and body["series_set"] == "truth"
    assert body["meta"]["network"] is None
    for key, column in (("a", "e1"), ("b", "e2")):
        assert body["slice_counts_by_shower"][key] == _window_counts(
            synthetic_client, table, column, body["slices"])
    assert {s["key"] for s in body["series"]} == {"e_a_true", "e_b_true"}
    # Calibrated on the whole selection: the D panel's constants.
    d = synthetic_client.get(ROUTE).json()["calibration"]
    for key in ("c_a", "c_b"):
        assert body["calibration"][key] == pytest.approx(d[key], rel=1e-12)
    # Each slice reports the measured mean momentum of its showers.
    for axis in body["slice_axes"]:
        index = next(s for s in body["slices"] if s["index"] == axis["slice"])
        for key in ("a", "b"):
            marker = axis["momentum"][key]
            assert marker["n"] == body["slice_counts_by_shower"][key][str(axis["slice"])]
            if marker["n"]:
                assert index["lo"] <= marker["mean"] < index["hi"]


def test_two_shower_bins_follow_the_bin_column(synthetic_client):
    body, size = _momentum(synthetic_client, p_slices="bins")
    table = _event_table(synthetic_client)
    (lo, hi), = _sql(synthetic_client,
                     f"SELECT least(min(e1_bin), min(e2_bin)), greatest(max(e1_bin), max(e2_bin)) "
                     f"FROM {table}")
    assert [s["label"] for s in body["slices"]] == [f"{k}–{k + 1} GeV" for k in range(lo, hi + 1)]
    for key, column in (("a", "e1_bin"), ("b", "e2_bin")):
        assert body["slice_counts_by_shower"][key] == _bin_counts(
            synthetic_client, table, column, body["slices"])
    assert body["outside_slices"] == {"a": 0, "b": 0}
    # Sixteen bins of two showers need coarser curves, and the response says so.
    assert size < density.RESPONSE_LIMIT
    assert any(w.startswith("Density curves sampled at") for w in body["meta"]["warnings"])


def test_two_shower_series_sets(synthetic_client):
    body, _ = _momentum(synthetic_client, series="all")
    assert body["meta"]["network"] == {"model": "segmentation", "frame": "absolute"}
    for axis in body["slice_axes"]:
        keys = [s["key"] for s in body["series"] if s["slice"] == axis["slice"]]
        assert keys == ["e_a_pred", "e_b_pred", "e_a_true", "e_b_true"]
    truth, _ = _momentum(synthetic_client, series="truth", coord_system="trans")
    assert truth["meta"]["network"] is None
    assert body["segmentation_frame"] == "absolute" and truth["segmentation_frame"] == "trans"
    # The frame moves the truth split and its calibration, and the payload says so.
    assert truth["calibration"]["c_a"] != body["calibration"]["c_a"]
    assert [s["fit"]["n"] for s in truth["series"]] == [
        s["fit"]["n"] for s in body["series"] if s["kind"] == "true"]


@pytest.mark.parametrize("p_slices", [None, "bins", "3,7,12"])
@pytest.mark.parametrize("series", ["truth", "model", "all"])
@pytest.mark.parametrize("calibrated", [True, False])
def test_every_two_shower_view_fits_or_is_refused(synthetic_client, p_slices, series, calibrated):
    params = {"series": series, "calibrated": calibrated}
    if p_slices:
        params["p_slices"] = p_slices
    if (p_slices, series) == ("bins", "all"):
        # The densest view - every bin, all four series - cannot fit even at the
        # coarsest rendering, so it is refused naming the parameter to change.
        response = synthetic_client.get(ROUTE, params={"slice_by": "momentum", **params})
        assert response.status_code == 422
        assert response.json()["field"] == "series"
        assert "series=truth or series=model" in response.json()["detail"]
        return
    body, size = _momentum(synthetic_client, **params)
    assert size < density.RESPONSE_LIMIT, (params, size)
    if not calibrated:
        assert body["scale"] == "deposited"
        assert any("not calibrated" in w for w in body["meta"]["warnings"])


@pytest.mark.parametrize("path", [
    ("slice_axes", 0, "provisional"),
    ("slice_axes", 0, "momentum", "a", "ci95"),
    ("series", 0, "markers"),
    ("series", 0, "fit", "mu_ci95"),
    ("outside_slices", "b"),
    ("no_deposit",),
    ("meta", "network"),
    ("segmentation_frame",),
    ("momentum_marker", "ci95"),
    ("slice_axes", 0, "momentum", "a", "low_n"),
    ("slice_axes", 0, "clipping", "rule"),
])
def test_the_contract_catches_a_dropped_key(synthetic_client, path):
    body, _ = _momentum(synthetic_client)
    broken = json.loads(json.dumps(body))
    node = broken
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    assert contract_check.errors(broken, contract_check.load("energy_momentum"))


def test_a_narrow_selection_still_counts_every_shower(synthetic_client):
    body, _ = _momentum(synthetic_client, e1_min=9.0, e1_max=10.0, p_slices="bins")
    assert sum(body["slice_counts_by_shower"]["a"].values()) == body["n_events"]
    # Shower B's momenta are not cut, so its bins reach beyond A's one bin.
    assert len([v for v in body["slice_counts_by_shower"]["b"].values() if v]) > 1


# ----------------------------------------------------------- single_client --


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_single_shower_kinds_default_to_momentum_slices(single_client, table):
    response = single_client.get(ROUTE, params={"table_name": table})
    assert response.status_code == 200, response.text
    default = response.json()
    body, size = _momentum(single_client, table_name=table)
    assert default["slice_by"] == "momentum" and default["series"] == body["series"]
    assert body["slicing"]["mode"] == "notebook"
    assert body["series_set"] == "deposit" and body["meta"]["network"] is None
    assert body["segmentation_frame"] is None
    assert {(s["key"], s["kind"], s["shower"]) for s in body["series"]} == {
        ("e_dep", "deposit", "a")}
    assert body["calibration"]["c_b"] is None and body["calibration"]["applied"] is True
    assert body["slice_counts_by_shower"]["a"] == _window_counts(
        single_client, _event_table(single_client, table), "e1", body["slices"])
    censored = CENSORED_AGGREGATE_NOTICE in body["meta"]["warnings"]
    assert censored == (table == SINGLE_EVENTS_TABLE)
    assert size < density.RESPONSE_LIMIT


def test_the_aggregate_lacks_the_single_hit_event(single_client):
    """The hit file's one single-hit shower (4.5 GeV) is in 5 ± 0.5; the aggregate omits it."""
    hits, _ = _momentum(single_client, table_name=SINGLE_HITS_TABLE)
    events, _ = _momentum(single_client, table_name=SINGLE_EVENTS_TABLE)
    five = next(s["index"] for s in hits["slices"] if s["label"] == "5 ± 0.5 GeV")
    assert hits["slice_counts"][str(five)] == events["slice_counts"][str(five)] + 1
    assert hits["n_events"] == events["n_events"] + 1


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_single_shower_bins(single_client, table):
    body, size = _momentum(single_client, table_name=table, p_slices="bins")
    event_table = _event_table(single_client, table)
    (lo, hi), = _sql(single_client, f"SELECT min(e1_bin), max(e1_bin) FROM {event_table}")
    assert [s["label"] for s in body["slices"]] == [f"{k}–{k + 1} GeV" for k in range(lo, hi + 1)]
    assert body["slice_counts_by_shower"]["a"] == _bin_counts(
        single_client, event_table, "e1_bin", body["slices"])
    assert body["outside_slices"] == {"a": 0, "b": None}
    assert size < density.RESPONSE_LIMIT
    # The one 200-shower bin carries a histogram; the 1- and 2-shower bins do not.
    draws = {body["slice_counts"][str(s["slice"])]: s["draw"] for s in body["series"]}
    assert draws[200] == "histogram" and draws[1] == "strip" and draws[2] == "strip"


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_single_shower_refusals(single_client, table):
    base = {"table_name": table}
    _refused(single_client, {**base, "slice_by": "d"}, "slice_by", capability="energy")
    for series in ("model", "all"):
        _refused(single_client, {**base, "series": series}, "series", capability="energy")
    _refused(single_client, {**base, "d_edges": "50,100"}, "d_edges")
    _refused(single_client, {**base, "e2_min": 1.0}, "e2_min")
    _refused(single_client, {**base, "coord_system": "polar"}, "coord_system")
    # 'truth' names the one deposit series there is.
    truth, _ = _momentum(single_client, **base, series="truth")
    assert truth["series_set"] == "deposit"


def test_the_two_shower_baseline_keeps_its_d_default_beside_them(single_client):
    body = single_client.get(ROUTE, params={"table_name": BASELINE_TABLE}).json()
    assert "slice_by" not in body and body["benchmarks"]
    momentum, _ = _momentum(single_client, table_name=BASELINE_TABLE)
    assert momentum["series_set"] == "truth"


@pytest.mark.parametrize("p_slices", [None, "bins", "1,4.5,10.25"])
@pytest.mark.parametrize("calibrated", [True, False])
def test_every_single_shower_view_stays_under_the_contract(single_client, p_slices, calibrated):
    for table in (SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE):
        params = {"table_name": table, "calibrated": calibrated}
        if p_slices:
            params["p_slices"] = p_slices
        body, size = _momentum(single_client, **params)
        assert size < density.RESPONSE_LIMIT, (params, size)
        assert not any(STILL_OVER in w for w in body["meta"]["warnings"])
