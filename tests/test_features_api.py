"""The feature explorer, ``GET /api/features`` (D2-D5), served by the booted three-kind app.

``single_client`` holds the two-shower baseline, a synthetic single-shower hit
experiment with 1 GeV bins of 1, 2, 7, 8, 14, 15, 19, 20 and 200 events plus
one single-hit event, and the producer-style aggregate of the same events.
So the hit kind and the aggregate must describe the same events identically
(the parity the explorer stands on), and every low-N rung of the histogram
ladder - strip, curve, histogram - is on screen in some class.

Every response is validated against its ``$defs`` entry of
``tests/contracts/features.json``, measured against the 100 KB contract and
scanned for hyphen-signed numbers.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.query import correlations, density
from calosrv.query import features as features_mod
from calosrv.query import features_catalog as catalog
from calosrv.stats import histogram
from calosrv.text import signed_hyphens

ROUTE = "/api/features"
VIEWS = ("catalog", "describe", "corr", "hist", "hist2d")
CIRCULAR = ("avg_phi", "avg_phi_circ")
LINEAR_KEYS = ("mean", "mean_lo", "mean_hi", "sd", "sd_lo", "sd_hi", "sd_population",
               "q25", "q50", "q75")


def _get(client, **params):
    response = client.get(ROUTE, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    contract_check.check(body, "features", f"view_{params.get('view', 'catalog')}")
    # The budget states the size served, its own stamp and any warning included.
    assert body["meta"]["budget"]["bytes"] == density.wire_size(body) == len(response.content)
    return body


def _refused(client, field, **params):
    response = client.get(ROUTE, params=params)
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["field"] == field, problem
    return problem


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _close(a, b, rel=2e-5, abs_tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (str, bool)) or isinstance(b, (str, bool)):
        return a == b
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


def _event_rows(client, table: str, sql_columns: str, where: str = "TRUE") -> dict:
    database = client.app.state.database
    with database.read_cursor() as con:
        return con.execute(
            f"SELECT {sql_columns} FROM {quote(naming.event_table(table))} WHERE {where}"
        ).fetchnumpy()


# ------------------------------------------------------------- catalogue --


def test_catalog_offers_each_kind_its_features(single_client):
    hits = _get(single_client, table_name=SINGLE_HITS_TABLE, view="catalog")
    events = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="catalog")
    hit_ids = [f["id"] for f in hits["features"]]
    event_ids = [f["id"] for f in events["features"]]
    assert len(hit_ids) == 21 and len(event_ids) == 19
    assert set(hit_ids) - set(event_ids) == {"avg_phi_circ", "angular_spread_circ"}
    assert [f["id"] for f in hits["features"] if f["notebook"]] == event_ids
    by_id = {f["id"]: f for f in hits["features"]}
    assert by_id["avg_phi"]["circular"] and by_id["avg_phi_circ"]["circular"]
    assert by_id["avg_phi"]["scales"] == ["circular"]
    assert "partly_circular" in by_id["angular_spread"]["flags"]
    assert by_id["angular_spread"]["hatched"] and by_id["angular_spread_circ"]["hatched"] is None
    # D1: only the absolute-frame depth is quoted below the front face.
    assert by_id["depth"]["display_offset"] == -3649.0
    assert "z − 3649 mm" in by_id["depth"]["label"]
    assert by_id["depth"]["scales"] == ["linear"] and by_id["num_hits"]["scales"] == ["linear"]
    trans = _get(single_client, table_name=SINGLE_HITS_TABLE, view="catalog", coord_system="trans")
    assert {f["id"]: f for f in trans["features"]}["depth"]["display_offset"] is None
    # The aggregate is a censored sample and says so; it is never called balanced.
    notes = " ".join(events["notes"])
    assert "censored sample" in notes and "not balanced" in notes
    assert events["n_excluded_single_hit"] == 0 and hits["n_excluded_single_hit"] == 1
    assert hits["frames"] == ["lab", "trans", "local"] and events["showers"] == ["a"]


# ----------------------------------------------------------------- parity --


@pytest.mark.parametrize("coord_system", ["lab", "trans", "local"])
@pytest.mark.parametrize("classes", ["windows", "bins", "label"])
def test_hits_and_aggregate_describe_the_shared_events_alike(single_client, coord_system, classes):
    """The hit kind rebuilds core.py's features from Group-1 sums; the aggregate stores the
    producer's. Over the events both hold, every number of D2 must agree."""
    hits = _get(single_client, table_name=SINGLE_HITS_TABLE, view="describe",
                coord_system=coord_system, classes=classes)
    events = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="describe",
                  coord_system=coord_system, classes=classes)
    assert [(c["label"], c["n"]) for c in hits["classes"]] == \
        [(c["label"], c["n"]) for c in events["classes"]]
    assert hits["n_events"] == events["n_events"] == 286
    for feature, row in events["table"].items():
        mine = hits["table"][feature]
        for key, values in row.items():
            if key == "circular":
                for stat, cells in values.items():
                    assert all(_close(a, b) for a, b in zip(mine["circular"][stat], cells)), \
                        (feature, stat)
                continue
            assert all(_close(a, b) for a, b in zip(mine[key], values)), (feature, key)


def test_corr_matches_the_aggregate_columns(single_client):
    """D3's r is plain Pearson over the class's events, with the floored events left out
    only of the pairs that involve the volume or a density."""
    body = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="corr", classes="label",
                class_index="1")
    order = body["order"]
    k = len(order)

    def cell(a, b):
        i, j = sorted((order.index(a), order.index(b)))
        return i * k - i * (i - 1) // 2 + (j - i)

    rows = _event_rows(single_client, SINGLE_EVENTS_TABLE,
                       "width, height, depth, n_hits, volume", "energy_class = 1")
    rows = {key: np.asarray(value, dtype=np.float64) for key, value in rows.items()}
    assert body["n"] == rows["n_hits"].size
    expected = np.corrcoef(rows["width"], rows["n_hits"])[0, 1]
    assert math.isclose(body["r"][cell("width", "num_hits")], expected, rel_tol=1e-5)
    floored = (rows["width"] <= 1e-6) | (rows["height"] <= 1e-6) | (rows["depth"] <= 1e-6)
    assert body["n_excluded_eps"] == int(floored.sum()) > 0
    expected = np.corrcoef(rows["volume"][~floored], rows["n_hits"][~floored])[0, 1]
    assert math.isclose(body["r"][cell("volume", "num_hits")], expected, rel_tol=1e-5)
    assert body["n_pairs"][cell("volume", "num_hits")] == body["n"] - body["n_excluded_eps"]
    assert body["n_pairs"][cell("width", "num_hits")] == body["n"]
    raw = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="corr", classes="label",
               class_index="1", exclude_eps="false")
    assert raw["n_excluded_eps"] == 0 and set(raw["n_pairs"]) == {raw["n"]}
    expected = np.corrcoef(rows["volume"], rows["n_hits"])[0, 1]
    assert math.isclose(raw["r"][cell("volume", "num_hits")], expected, rel_tol=1e-5)


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_corr_matrix_is_an_upper_triangle_with_fisher_intervals(single_client, table):
    body = _get(single_client, table_name=table, view="corr", classes="label")
    k = len(body["order"])
    assert len(body["r"]) == len(body["lo"]) == len(body["n_pairs"]) == k * (k + 1) // 2
    assert body["class"] == "pooled" and body["n"] == body["n_events"]
    position = 0
    for i in range(k):
        for j in range(i, k):
            r, lo, hi = body["r"][position], body["lo"][position], body["hi"][position]
            if i == j:
                assert r in (1.0, None) and lo is None and hi is None
            elif r is not None:
                assert lo <= r <= hi and -1.0 <= lo and hi <= 1.0
            position += 1
    assert {"avg_phi", "angular_spread"} <= set(body["hatched"])
    assert body["method"] == "fisher_z"
    # A class of seven events: r from N = 4, so the cells exist with wide intervals.
    small = _get(single_client, table_name=table, view="corr", classes="bins", class_index="11")
    assert small["n"] == 7
    assert any(r is not None for r in small["r"])


def test_corr_puts_no_azimuth_on_the_colour_scale(single_client):
    """avg_phi has no linear r: its cells are off the PuOr scale and carry Mardia's R - gated
    here, the fixture's showers sharing four directions - with the notebook's linear r beside
    it for parity only. One linear cell's interval is pinned to Fisher's formula."""
    body = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="corr", classes="label",
                class_index="1")
    assert body["scale"] == correlations.R_SCALE
    order, k = body["order"], len(body["order"])

    def cell(a, b):
        i, j = sorted((order.index(a), order.index(b)))
        return i * k - i * (i - 1) // 2 + (j - i)

    for other in order:
        position = cell("avg_phi", other)
        assert body["r"][position] is None and body["lo"][position] is None
    entries = {(c["row"], c["col"]): c for c in body["circular_cells"]}
    assert len(entries) == k and all(c["position"] == cell(c["row"], c["col"])
                                     for c in entries.values())
    rows = _event_rows(single_client, SINGLE_EVENTS_TABLE, "avg_phi, width, n_hits",
                       "energy_class = 1")
    rows = {key: np.asarray(value, dtype=np.float64) for key, value in rows.items()}
    width_phi = entries[("width", "avg_phi")]
    assert width_phi["measure"] == "mardia" and width_phi["n"] == rows["width"].size
    assert width_phi["n_azimuths"] == np.unique(rows["avg_phi"]).size == 4
    assert width_phi["value"] is None and width_phi["reason"].startswith("Mardia's R needs 8")
    assert width_phi["null_R2"] == pytest.approx(2 / (width_phi["n"] - 1), rel=1e-5)
    assert width_phi["parity_r"] == pytest.approx(
        np.corrcoef(rows["avg_phi"], rows["width"])[0, 1], rel=1e-5)
    assert entries[("avg_phi", "avg_phi")]["parity_r"] == 1.0
    # Fisher's z for a linear cell: tanh(atanh r ± 1.959964 / √(N − 3)).
    position = cell("width", "num_hits")
    r, n = body["r"][position], body["n_pairs"][position]
    half = 1.959963985 / math.sqrt(n - 3)
    assert body["lo"][position] == pytest.approx(math.tanh(math.atanh(r) - half), rel=2e-5)
    assert body["hi"][position] == pytest.approx(math.tanh(math.atanh(r) + half), rel=2e-5)


# ---------------------------------------------------------------- circular --


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_an_azimuth_never_gets_a_linear_mean(single_client, table):
    body = _get(single_client, table_name=table, view="describe", classes="bins")
    circular_ids = [f["id"] for f in body["features"] if f["circular"]]
    assert set(circular_ids) == ({"avg_phi", "avg_phi_circ"} if table == SINGLE_HITS_TABLE
                                 else {"avg_phi"})
    for fid in circular_ids:
        row = body["table"][fid]
        for key in LINEAR_KEYS:
            assert all(v is None for v in row.get(key, [])), (fid, key)
        stats = row["circular"]
        for n, resultant, direction in zip(row["n"], stats["resultant"], stats["mean_direction"]):
            if n:
                assert 0.0 <= resultant <= 1.0
                assert direction is None or -math.pi < direction <= math.pi
    assert "circular" not in body["table"]["width"]
    assert all(v is not None for n, v in zip(body["table"]["width"]["n"],
                                              body["table"]["width"]["mean"]) if n >= 2)
    for fid in circular_ids:
        hist = _get(single_client, table_name=table, view="hist", feature=fid, classes="label")
        assert hist["axis"]["scale"] == "circular"
        assert hist["axis"]["lo"] == pytest.approx(-math.pi, abs=1e-5)
        assert hist["axis"]["hi"] == pytest.approx(math.pi, abs=1e-5)
        assert all(s["kde"] is None for s in hist["series"])
        _refused(single_client, "scale", table_name=table, view="hist", feature=fid, scale="log")


# --------------------------------------------------------------- D4 gates --


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_histogram_ladder_follows_the_low_n_floors(single_client, table):
    body = _get(single_client, table_name=table, view="hist", feature="total_hit_energy",
                classes="bins")
    axis = body["axis"]
    sizes = sorted(s["n"] for s in body["series"])
    assert {1, 2, 7, 8, 14, 15, 19, 20, 200} <= set(sizes)
    drawn = [s["n"] for s in body["series"] if s["n"] >= histogram.MIN_HISTOGRAM_SAMPLES]
    assert axis["bins"] == histogram.adaptive_bins(min(drawn))
    assert len(axis["edges"]) == axis["bins"] + 1
    width = (axis["hi"] - axis["lo"]) / axis["bins"]
    for s in body["series"]:
        n = s["n"]
        assert s["draw"] == ("histogram" if n >= 15 else "strip" if n else "none")
        assert s["drives_scale"] == (n >= 15)
        assert (s["kde"] is not None) == (n >= 8), (n, s["message"])
        assert (s["strip"] is not None) == (0 < n < 15)
        if s["strip"] is not None:
            assert len(s["strip"]) == n
        assert len(s["counts"]) == (axis["bins"] if n >= 15 else 0)
        assert s["n_in_range"] + s["n_below"] + s["n_above"] == n
        if s["counts"]:
            assert sum(s["counts"]) == s["n_in_range"]
        if s["kde"]:
            assert s["kde"]["scale_to_counts"] == pytest.approx(n * width, rel=1e-5)
            assert len(s["kde"]["pdf"]) == len(body["curve_x"])
        if n:
            assert s["density_scale"] == pytest.approx(1.0 / (n * width), rel=1e-5)
    assert body["y_max"]["provisional"] is False and body["y_max"]["count"] > 0


def test_floored_values_never_set_the_histogram_range(single_client):
    """A quarter of the fixture's heights sit at core.py's 10⁻⁶ mm floor. They used to set
    the 1st percentile and push scale=auto onto a twelve-decade log axis; now the measured
    heights set the range and the floors are a counted underflow."""
    rows = _event_rows(single_client, SINGLE_EVENTS_TABLE, "height", "n_hits >= 2")
    height = np.asarray(rows["height"], dtype=np.float64)
    floored = height <= 1e-6 * (1 + 1e-9)
    assert floored.mean() > 0.01
    kept = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="hist", feature="height",
                classes="label")
    dropped = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="hist", feature="height",
                   classes="label", exclude_eps="true")
    assert kept["exclude_eps"] is False and kept["scale"] == dropped["scale"] == "linear"
    assert (kept["axis"]["lo"], kept["axis"]["hi"]) == (dropped["axis"]["lo"], dropped["axis"]["hi"])
    assert kept["axis"]["lo"] > 100.0
    assert sum(s["n_floored"] for s in kept["series"]) == int(floored.sum())
    assert [s["n_floored"] for s in dropped["series"]] == [0, 0]
    for s in kept["series"]:
        assert s["n_below"] >= s["n_floored"]             # drawn below the axis, counted
    assert kept["axis"]["clipping"]["data_min"] == pytest.approx(1e-6)
    assert any("n_floored" in note for note in kept["notes"])
    two_d = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="hist2d", feature="height",
                 classes="label")
    assert two_d["x"]["scale"] == "linear" and two_d["x"]["lo"] > 100.0
    assert sum(s["n_floored"] for s in two_d["series"]) == int(floored.sum())


def test_describe_labels_low_n_widths(single_client):
    """The two-event class: '1 d.o.f.', the SD's standard error, c4(2) = √(2/π)."""
    body = _get(single_client, table_name=SINGLE_HITS_TABLE, view="describe", classes="bins")
    width = body["table"]["width"]
    two = width["n"].index(2)
    assert "1 d.o.f." in body["notes_by_n"]["2"]
    assert width["sd_se"][two] == pytest.approx(width["sd"][two] / math.sqrt(2), rel=1e-5)
    assert width["c4"][two] == pytest.approx(math.sqrt(2 / math.pi), rel=1e-5)
    assert width["robust"][two] is False
    assert set(body["class_stats"][0]) == {"index", "n"}
    big = width["n"].index(200)
    assert "200" not in body["notes_by_n"] and width["robust"][big] is True


def test_quantised_features_bin_on_their_lattice(single_client):
    depth = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist", feature="depth_range",
                 classes="label")
    quantum = depth["axis"]["quantum"]
    assert quantum["verified"] and quantum["snapped"] and depth["axis"]["quantum_mm"] == 20.5
    edges = np.asarray(depth["axis"]["edges"])
    assert np.allclose(np.diff(edges), quantum["per_bin"] * 20.5)
    phase = np.mod(edges - quantum["anchor"], 20.5)
    assert np.allclose(np.minimum(phase, 20.5 - phase), 10.25, atol=1e-3)
    _refused(single_client, "scale", table_name=SINGLE_HITS_TABLE, view="hist",
             feature="depth_range", scale="log")
    hits = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist", feature="num_hits",
                classes="label")
    edges = np.asarray(hits["axis"]["edges"])
    assert np.allclose(edges - np.floor(edges), 0.5)
    # The aggregate has no lattice: the step is measured from the values themselves.
    events = _get(single_client, table_name=SINGLE_EVENTS_TABLE, view="hist", feature="depth",
                  coord_system="trans", classes="label")
    assert events["axis"]["quantum"]["value"] == 20.5 and events["axis"]["quantum"]["snapped"]
    # The same snapping on the 2-D histogram's feature axis.
    two_d = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist2d",
                 feature="depth_range", classes="label")
    assert two_d["x"]["quantum"]["snapped"] and two_d["y"]["quantum"] is None
    # Depth in the absolute frame is quoted below the front face, on the shifted lattice.
    lab = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist", feature="depth",
               classes="label")
    assert lab["axis"]["offset"] == -3649.0 and lab["axis"]["quantum"]["snapped"]
    raw = _event_rows(single_client, SINGLE_HITS_TABLE, "min(z_max_a_abs) AS z", "n_hits_a >= 2")
    described = _get(single_client, table_name=SINGLE_HITS_TABLE, view="describe", classes="label")
    shown = min(v for v in described["table"]["depth"]["min"] if v is not None)
    assert shown == pytest.approx(float(raw["z"][0]) - 3649.0, abs=1e-3)


def test_eps_exclusion_counts_what_it_leaves_out(single_client):
    keep = _get(single_client, table_name=SINGLE_HITS_TABLE, view="describe", classes="label")
    drop = _get(single_client, table_name=SINGLE_HITS_TABLE, view="describe", classes="label",
                exclude_eps="true")
    for fid in ("height", "volume", "energy_density"):
        n_eps = keep["table"][fid]["n_eps"]
        assert sum(n_eps) > 0
        assert [a - b for a, b in zip(keep["table"][fid]["n"], drop["table"][fid]["n"])] == n_eps
    assert keep["table"]["num_hits"]["n_eps"] == [None, None]
    assert keep["table"]["num_hits"]["n"] == drop["table"]["num_hits"]["n"]
    hist = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist", feature="volume",
                classes="label", exclude_eps="true")
    assert [s["n_excluded_eps"] for s in hist["series"]] == keep["table"]["volume"]["n_eps"]


def test_log_axis_counts_the_values_it_cannot_place(single_client):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist", feature="centroid_x",
                classes="label", scale="log")
    assert body["axis"]["log10"] is True
    rows = _event_rows(single_client, SINGLE_HITS_TABLE, "sum_ex_a_abs / e_dep_a AS cx",
                       "n_hits_a >= 2")
    nonpositive = int((np.asarray(rows["cx"]) <= 0).sum())
    assert sum(s["n_nonpositive"] for s in body["series"]) == nonpositive > 0
    assert sum(s["n"] for s in body["series"]) == 286 - nonpositive


# -------------------------------------------------------------------- D5 --


@pytest.mark.parametrize("classes", ["windows", "bins", "label"])
def test_hist2d_counts_add_up(single_client, classes):
    body = _get(single_client, table_name=SINGLE_HITS_TABLE, view="hist2d", feature="width",
                classes=classes)
    nx, ny = body["x"]["bins"], body["y"]["bins"]
    assert body["y"]["feature"] == "total_hit_energy"
    peak = 0
    for s in body["series"]:
        if s["draw"] == "histogram":
            assert s["n"] >= 15 and len(s["counts"]) == nx * ny
            assert sum(s["counts"]) + s["outside"]["total"] == s["n"]
            assert s["max_count"] == max(s["counts"])
            peak = max(peak, s["max_count"])
        elif s["draw"] == "pairs":
            assert 0 < s["n"] < 15 and len(s["pairs"]) == s["n"]
        else:
            assert s["n"] == 0
    color = body["color"]
    assert color["max_count"] == peak
    assert color["vmax"] == pytest.approx(math.log10(peak) if peak else 0.0, abs=1e-5)


# --------------------------------------------------------------- refusals --


def test_requests_the_data_cannot_serve_are_refused_by_field(single_client):
    hits, events = SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE
    _refused(single_client, "view", table_name=hits, view="table")
    _refused(single_client, "coord_system", table_name=hits, view="describe",
             coord_system="canonical")
    _refused(single_client, "shower", table_name=hits, view="describe", shower="b")
    _refused(single_client, "shower", table_name=events, view="describe", shower="both")
    _refused(single_client, "classes", table_name=hits, view="describe", classes="deciles")
    _refused(single_client, "class_index", table_name=hits, view="corr", classes="bins")
    _refused(single_client, "class_index", table_name=hits, view="corr", classes="bins",
             class_index="99")
    _refused(single_client, "feature", table_name=hits, view="hist")
    _refused(single_client, "feature", table_name=hits, view="hist2d", feature="energy")
    # A feature the aggregate cannot serve is a capability refusal, not a typo.
    problem = _refused(single_client, "feature", table_name=events, view="hist",
                       feature="avg_phi_circ")
    contract_check.check(problem, "capability_problem")
    assert problem["capability"] == "feat-hist" and problem["kind"] == "single_shower_events"
    assert "Σ cos φ" in problem["detail"]
    problem = _refused(single_client, "feature", table_name=events, view="hist2d",
                       feature="angular_spread_circ")
    assert problem["capability"] == "feat-hist2d"
    typo = _refused(single_client, "feature", table_name=events, view="hist", feature="widht")
    assert typo["type"] == "/problems/validation-error"
    _refused(single_client, "scale", table_name=hits, view="hist", feature="width",
             scale="decibel")
    _refused(single_client, "y_scale", table_name=hits, view="hist2d", feature="width",
             y_scale="loglog")
    _refused(single_client, "e2_min", table_name=hits, view="describe", e2_min=1.0)
    _refused(single_client, "d_max", table_name=events, view="describe", d_max=100.0)


def test_a_stale_two_shower_experiment_is_refused_with_the_reason(single_client):
    database = single_client.app.state.database
    with database.read_cursor() as con:
        (version,) = con.execute("SELECT derived_version FROM experiment WHERE table_name = ?",
                                 [BASELINE_TABLE]).fetchone()
    with database.write_lock() as con:
        con.execute("UPDATE experiment SET derived_version = 1 WHERE table_name = ?",
                    [BASELINE_TABLE])
    try:
        for view, gate in (("catalog", "feat-table"), ("describe", "feat-table"),
                           ("corr", "feat-corr"), ("hist", "feat-hist"),
                           ("hist2d", "feat-hist2d")):
            response = single_client.get(ROUTE, params={"table_name": BASELINE_TABLE,
                                                        "view": view, "feature": "width"})
            assert response.status_code == 422, response.text
            problem = response.json()
            assert problem["type"] == "/problems/unsupported-capability"
            assert problem["capability"] == gate and "Rebuild" in problem["reason"]
    finally:
        with database.write_lock() as con:
            con.execute("UPDATE experiment SET derived_version = ? WHERE table_name = ?",
                        [version, BASELINE_TABLE])
    assert single_client.get(ROUTE, params={"table_name": BASELINE_TABLE}).status_code == 200


# ------------------------------------------------- budget and typography --


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE, BASELINE_TABLE])
def test_every_view_fits_the_budget_and_signs_numbers_typographically(single_client, table):
    showers = ("a", "b") if table == BASELINE_TABLE else ("a",)
    for shower in showers:
        for classes in ("windows", "bins", "label"):
            for view in VIEWS:
                params = {"table_name": table, "view": view, "classes": classes,
                          "shower": shower, "coord_system": "lab"}
                if view == "corr" and classes == "bins":
                    params["class_index"] = "pooled"
                features = (["total_hit_energy", "depth", "avg_phi", "volume"]
                            if view in ("hist", "hist2d") else [None])
                for feature in features:
                    if feature:
                        params["feature"] = feature
                    body = _get(single_client, **params)
                    assert density.wire_size(body) < density.RESPONSE_LIMIT
                    assert body["meta"]["budget"]["level"] == 0
                    hyphens = [h for text in _strings(body) for h in signed_hyphens(text)]
                    assert not hyphens, (params, hyphens[:3])


def _synthetic_bundle(n: int = 100_000, seed: int = 7) -> features_mod.FeatureBundle:
    """A production-sized single-shower bundle: 20 bins of 5,000 events, realistic tails."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.0, 20.0, n)
    layers = rng.integers(0, 60, n)
    width = rng.lognormal(5.8, 0.6, n)
    width[rng.random(n) < 0.002] = 1e-6
    height = rng.lognormal(5.8, 0.6, n)
    height[rng.random(n) < 0.003] = 1e-6
    depth_range = np.where(layers > 0, layers * 20.5, 1e-6)
    depth = 3662.39990234375 + rng.integers(0, 60, n) * 20.5
    volume = width * height * depth
    hits = rng.integers(2, 400, n).astype(np.float64)
    energy = 0.031 * p * rng.normal(1.0, 0.1, n)
    phi = rng.uniform(-math.pi, math.pi, n)
    values = {
        "width": width, "height": height, "depth": depth, "depth_range": depth_range,
        "volume": volume, "num_hits": hits, "total_hit_energy": np.abs(energy),
        "centroid_x": rng.uniform(-2500, 2500, n), "centroid_y": rng.uniform(-2500, 2500, n),
        "centroid_z": 3662.4 + rng.lognormal(4.5, 0.5, n), "mean_r": rng.normal(4200, 200, n),
        "std_r": rng.lognormal(4.6, 0.4, n), "max_r": rng.normal(4500, 250, n),
        "weighted_r_mean": rng.normal(4150, 200, n), "avg_theta": rng.uniform(0.06, 0.63, n),
        "avg_phi": phi, "avg_phi_circ": phi + rng.normal(0, 0.01, n),
        "angular_spread": rng.lognormal(-3.0, 1.2, n),
        "angular_spread_circ": rng.lognormal(-3.0, 1.0, n),
        "numerical_density": hits / volume, "energy_density": np.abs(energy) / volume,
    }
    return features_mod.FeatureBundle(
        table_name=SINGLE_HITS_TABLE, kind="single_shower_hits", coord_system="lab", shower="a",
        event_number=np.arange(n, dtype=np.int64), p=p, bin=np.floor(p).astype(np.int64),
        label=None, values=values, n_selected=n, n_excluded_single_hit=0)


def test_the_largest_views_stay_under_the_contract(single_client, monkeypatch):
    """A production-sized selection - 100,000 events in twenty 1 GeV bins - through the real
    route: the twenty-class views are the largest the explorer serves."""
    bundle = _synthetic_bundle()
    monkeypatch.setattr(features_mod, "bundle_for", lambda *args, **kwargs: (bundle, False))
    monkeypatch.setattr(features_mod, "dataset_bin_range", lambda *args, **kwargs: (0, 19))
    requests = [dict(view="describe"), dict(view="corr", class_index="pooled")]
    requests += [dict(view="hist", feature=f) for f in
                 ("total_hit_energy", "width", "depth", "num_hits", "avg_phi", "energy_density")]
    requests += [dict(view="hist2d", feature=f) for f in ("width", "depth_range", "avg_phi")]
    for params in requests:
        body = _get(single_client, table_name=SINGLE_HITS_TABLE, classes="bins", **params)
        assert len(body["classes"]) == 20 and all(c["n"] > 4000 for c in body["classes"])
        assert density.wire_size(body) < density.RESPONSE_LIMIT, params
        if params["view"] == "hist":
            assert all(s["draw"] == "histogram" for s in body["series"])
            assert body["axis"]["bins"] >= 27 or body["axis"]["scale"] == "circular" \
                or body["axis"]["quantum"]
        if params["view"] == "hist2d":
            assert body["x"]["bins"] <= 33 and body["y"]["bins"] == 32
    # Snapped to the lattice, the depth histogram cannot comb; the statistic, measured where
    # the five windows' Rice count gives enough bins, says so.
    depth = _get(single_client, table_name=SINGLE_HITS_TABLE, classes="windows", view="hist",
                 feature="depth")
    assert depth["axis"]["quantum"]["snapped"] and depth["axis"]["bins"] >= 27
    assert depth["comb"]["combed"] is False and depth["comb"]["lag1"] is not None


def test_the_guard_sheds_resolution_and_says_so(single_client, monkeypatch):
    """With the limit lowered under what the twenty-class views need, each view takes its
    stated reductions in order and says which; one that cannot fit says that too."""
    bundle = _synthetic_bundle()
    monkeypatch.setattr(features_mod, "bundle_for", lambda *args, **kwargs: (bundle, False))
    monkeypatch.setattr(features_mod, "dataset_bin_range", lambda *args, **kwargs: (0, 19))
    common = {"table_name": SINGLE_HITS_TABLE, "classes": "bins"}

    monkeypatch.setattr(density, "RESPONSE_LIMIT", 45_000)
    hist = _get(single_client, view="hist", feature="centroid_x", **common)
    assert hist["meta"]["budget"]["level"] >= 1 and density.wire_size(hist) <= 45_000
    assert hist["meta"]["budget"]["limit"] == 45_000
    assert any(note.startswith("Reduced to stay under the 45,000-byte budget")
               for note in hist["notes"])
    assert len(hist["curve_x"]) == 80
    two_d = _get(single_client, view="hist2d", feature="width", **common)
    assert two_d["meta"]["budget"]["level"] >= 1 and two_d["x"]["bins"] < 32
    assert density.wire_size(two_d) <= 45_000

    monkeypatch.setattr(density, "RESPONSE_LIMIT", 52_000)
    described = _get(single_client, view="describe", **common)
    assert described["meta"]["budget"]["level"] == 1 and described["intervals"] is None
    assert "mean_lo" not in described["table"]["width"]

    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1_000)
    over = _get(single_client, view="corr", class_index="pooled", **common)
    assert any("still over" in warning for warning in over["meta"]["warnings"])
    # The stated size includes the warning that says it is over.
    assert over["meta"]["budget"]["bytes"] == density.wire_size(over) > 1_000
