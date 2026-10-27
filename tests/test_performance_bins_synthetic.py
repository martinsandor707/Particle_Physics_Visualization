"""``GET /api/model-performance?slice_by=momentum_bin`` against the event table (E2).

Booted on ``synthetic_all_models``: 286 events whose momenta are uniform over
2-18 GeV, so shower A and shower B sit in different bins of the same event and
the populations per bin run from about a dozen to about two dozen - across the
gates at N = 15 and N = 20. Every number is recomputed here from the event
table with NumPy and compared with the payload; narrow selections push bins
down through N = 6 and N = 2.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE
from calosrv.db import ddl, naming
from calosrv.query import density
from calosrv.stats import gaussian, median
from calosrv.text import signed_hyphens


# ---------------------------------------------------- reference formulas --

#: The axis-top mantissas (performance_bins.TOP_MANTISSAS), restated independently.
_TOPS = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)


def nice_top(peak: float) -> float:
    """The smallest m × 10^k, m in _TOPS, at or above ``peak``."""
    k = math.floor(math.log10(peak))
    candidates = [m * 10.0 ** e for e in (k, k + 1) for m in _TOPS]
    return min(c for c in candidates if c >= peak * (1 - 1e-9))


def rmse_interval(r: np.ndarray, seed) -> tuple[float, float]:
    """Decision D-4, restated: the χ² interval (scipy's quantiles) to N = 19, the bootstrap from 20."""
    from scipy.stats import chi2

    r = np.asarray(r, dtype=np.float64)
    n = r.size
    rmse = math.sqrt(np.mean(r ** 2))
    if n < 20:
        return (rmse * math.sqrt(n / chi2.ppf(0.975, n)), rmse * math.sqrt(n / chi2.ppf(0.025, n)))
    rng = np.random.default_rng(np.random.SeedSequence(list(seed)))
    sq = r ** 2
    means = sq[rng.integers(0, n, size=(2000, n))].mean(axis=1)
    lo, hi = np.quantile(np.sqrt(means), [0.025, 0.975])
    return float(lo), float(hi)

FRAME_CODES = {"lab": "abs", "trans": "trn", "local": "loc"}
STEMS = {"energy": "en", "angle": "th"}
FRAMES = {"lab": "absolute", "trans": "trans", "local": "local"}

#: (query parameters, the same selection as bounds on e1, e2).
SELECTIONS = (
    ({}, (0.0, 99.0, 0.0, 99.0)),
    ({"e1_max": 6.0}, (0.0, 6.0, 0.0, 99.0)),
    ({"e1_min": 9.0, "e1_max": 10.0}, (9.0, 10.0, 0.0, 99.0)),
    ({"e1_min": 2.0, "e1_max": 4.0, "e2_min": 2.0, "e2_max": 4.0}, (2.0, 4.0, 2.0, 4.0)),
)


@pytest.fixture(scope="module")
def table(synthetic_client):
    database = synthetic_client.app.state.database
    with database.read_cursor() as con:
        raw = con.execute(f'SELECT * FROM "{naming.event_table(BASELINE_TABLE)}"').fetchnumpy()
    return {k: np.ma.filled(np.ma.asarray(v).astype(np.float64), np.nan) for k, v in raw.items()}


def get(client, model, **params):
    response = client.get("/api/model-performance",
                          params={"model": model, "slice_by": "momentum_bin", **params})
    assert response.status_code == 200, response.text
    return response.json()


def order_interval(sample):
    x = np.sort(sample)
    n = x.size
    cdf = [sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n for k in range(n + 1)]
    j = max(k for k in range(n) if cdf[k] <= 0.025) + 1
    return x[j - 1], x[n - j]


def group(table, model, coord, shower, k, bounds):
    """The oracle: one (frame, shower, bin) group straight from the event table."""
    lo1, hi1, lo2, hi2 = bounds
    in_selection = ((table["e1"] >= lo1) & (table["e1"] <= hi1)
                    & (table["e2"] >= lo2) & (table["e2"] <= hi2) & np.isfinite(table["d"]))
    bins = table["e1_bin" if shower == "a" else "e2_bin"]
    true = table[f"{STEMS[model]}_true_{shower}"]
    pred = table[f"{STEMS[model]}_pred_{shower}_{FRAME_CODES[coord]}"]
    chosen = in_selection & (bins == k)
    both = chosen & np.isfinite(pred) & np.isfinite(true)
    p, t = pred[both], true[both]
    return {"n": int(both.sum()), "n_missing": int((chosen & ~both).sum()),
            "r": (p - t) * (1000.0 if model == "angle" else 1.0),
            "rel": np.abs(p - t) / t, "true": t}


def approx(value, rel=1e-5):
    return pytest.approx(value, rel=rel, abs=1e-9)


def quoted_bytes(notice):
    """The byte count a payload-guard notice states, e.g. 'at 37,345 bytes'."""
    import re

    return int(re.search(r"at ([\d,]+) bytes", notice).group(1).replace(",", ""))


def series_of(block, coord, shower):
    return next(s for s in block["series"] if s["key"] == f"{FRAMES[coord]}:{shower}")


# ------------------------------------------------------------- numbers --


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("params,bounds", SELECTIONS)
def test_every_number_matches_numpy_over_the_event_table(synthetic_client, table, model, params,
                                                         bounds):
    block = get(synthetic_client, model, **params)["by_momentum_bin"]
    assert block["frames"] == ["absolute", "trans", "local"]
    seen_n = set()
    for coord in ddl.COORD_SYSTEMS:
        for shower in ("a", "b"):
            s = series_of(block, coord, shower)
            for i, k in enumerate(block["bins"]["index"]):
                o = group(table, model, coord, shower, k, bounds)
                seen_n.add(o["n"])
                assert (s["n"][i], s["n_missing"][i]) == (o["n"], o["n_missing"])
                assert s["drives_scale"][i] is (o["n"] >= 15)
                if o["n"] == 0:
                    for key in ("rmse", "mae", "median_rel", "bias"):
                        assert s[key][i] is None
                    continue
                r = o["r"]
                assert s["rmse"][i] == approx(math.sqrt(np.mean(r ** 2)))
                assert s["mae"][i] == approx(np.mean(np.abs(r)))
                assert s["bias"][i] == approx(np.mean(r))
                assert s["median_rel"][i] == approx(np.median(o["rel"]))
                if o["n"] < 2:
                    for key in ("rmse_lo", "mae_lo", "bias_lo", "mae_se"):
                        assert s[key][i] is None
                    continue
                n, t = o["n"], gaussian.t_quantile_975(o["n"] - 1)
                ab = np.abs(r)
                # Decision D-4, with the documented seed [42, frame, shower, bin, 0].
                seed = (42, ddl.COORD_SYSTEMS.index(coord), ("a", "b").index(shower), k, 0)
                lo, hi = rmse_interval(r, seed)
                rel = 1e-3 if n < 20 else 1e-5
                assert s["rmse_lo"][i] == approx(lo, rel=rel)
                assert s["rmse_hi"][i] == approx(hi, rel=rel)
                assert s["rmse_method"][i] == ("chi2_rmse" if n < 20 else "bootstrap_percentile")
                half = t * ab.std(ddof=1) / math.sqrt(n)
                assert s["mae_lo"][i] == approx(max(0.0, ab.mean() - half))
                assert s["mae_hi"][i] == approx(ab.mean() + half)
                assert s["mae_se"][i] == approx(ab.std(ddof=1) / math.sqrt(n))
                half = t * r.std(ddof=1) / math.sqrt(n)
                assert s["bias_lo"][i] == approx(r.mean() - half)
                assert s["bias_hi"][i] == approx(r.mean() + half)
                if model == "angle":
                    assert s["median_abs"][i] == approx(np.median(np.abs(r)))
                    assert s["theta_min"][i] == approx(o["true"].min())
                    assert s["n_small_theta"][i] == int((o["true"] < 0.1).sum())
    # The selections between them put bins on both sides of every gate.
    if not params:
        assert min(seen_n) < 15 <= 20 <= max(seen_n)
    elif params == SELECTIONS[1][0]:
        assert 0 in seen_n and any(1 <= n <= 5 for n in seen_n) and max(seen_n) >= 15
    elif params == SELECTIONS[2][0]:
        assert any(1 <= n <= 5 for n in seen_n) and max(seen_n) >= 6
    else:
        assert 0 in seen_n and 0 < max(seen_n) < 15


@pytest.mark.parametrize("model", ("energy", "angle"))
def test_the_median_whisker_follows_its_floors_and_cross_checks(synthetic_client, table, model):
    block = get(synthetic_client, model)["by_momentum_bin"]
    methods = set()
    for coord in ddl.COORD_SYSTEMS:
        frame_index = ddl.COORD_SYSTEMS.index(coord)
        for shower_index, shower in enumerate(("a", "b")):
            s = series_of(block, coord, shower)
            for i, k in enumerate(block["bins"]["index"]):
                o = group(table, model, coord, shower, k, SELECTIONS[0][1])
                n = o["n"]
                method = s["median_rel_method"][i]
                methods.add(method)
                if n < 6:
                    assert method is None and s["median_rel_lo"][i] is None
                    assert s["median_rel_order_lo"][i] is None
                    continue
                lo, hi = order_interval(o["rel"])
                assert s["median_rel_order_lo"][i] == approx(lo)
                assert s["median_rel_order_hi"][i] == approx(hi)
                assert 0.95 <= s["median_rel_order_coverage"][i] < 1.0
                if n < 20:
                    assert method == "order_statistic"
                    assert s["median_rel_lo"][i] == approx(lo) and s["median_rel_hi"][i] == approx(hi)
                else:
                    assert method == "bootstrap_percentile"
                    # The documented seed: SeedSequence([42, frame, shower, bin, quantity]).
                    direct = median.bootstrap_median_interval(
                        o["rel"], seed=[42, frame_index, shower_index, k, 2])
                    assert s["median_rel_lo"][i] == approx(direct.lo)
                    assert s["median_rel_hi"][i] == approx(direct.hi)
    assert {"order_statistic", "bootstrap_percentile"} <= methods


def test_two_identical_requests_agree_exactly(synthetic_client):
    def body():
        out = get(synthetic_client, "angle", coord_system="trans")
        out["meta"].pop("total_ms")
        out["meta"].pop("query_ms")
        return out

    assert body() == body()


def test_a_frame_is_not_perturbed_by_the_frames_requested_beside_it(synthetic_client):
    """The cards' coord_system picks which frame's cards ride along; the block is the same for all."""
    blocks = [get(synthetic_client, "energy", coord_system=c)["by_momentum_bin"]
              for c in ddl.COORD_SYSTEMS]
    assert blocks[0] == blocks[1] == blocks[2]


def test_each_shower_is_binned_by_its_own_momentum(synthetic_client, table):
    block = get(synthetic_client, "energy")["by_momentum_bin"]
    finite_a = np.isfinite(table["en_pred_a_abs"]).sum()
    s_a, s_b = series_of(block, "lab", "a"), series_of(block, "lab", "b")
    assert sum(s_a["n"]) == finite_a and sum(s_b["n"]) == np.isfinite(table["en_pred_b_abs"]).sum()
    by_e1 = [int((table["e1_bin"] == k).sum()) for k in block["bins"]["index"]]
    by_e2 = [int((table["e2_bin"] == k).sum()) for k in block["bins"]["index"]]
    assert s_a["n"] == by_e1 and s_b["n"] == by_e2
    assert by_e1 != by_e2


# ------------------------------------------------------------- the axis --


def test_the_bin_axis_is_the_datasets_and_does_not_move_with_the_selection(synthetic_client, table):
    wide = get(synthetic_client, "energy")["by_momentum_bin"]
    narrow = get(synthetic_client, "energy", e1_min=9.0, e1_max=10.0,
                 e2_min=9.0, e2_max=10.0)["by_momentum_bin"]
    assert wide["bins"] == narrow["bins"]
    present = sorted({int(k) for k in np.concatenate([table["e1_bin"], table["e2_bin"]])})
    assert wide["bins"]["index"] == list(range(present[0], present[-1] + 1))
    assert wide["bins"]["label"][0] == f"{present[0]}–{present[0] + 1} GeV"
    assert wide["bins"]["p_lo"][:2] == [float(present[0]), float(present[0] + 1)]
    assert sum(narrow["series"][0]["n"]) < sum(wide["series"][0]["n"])
    assert "labels" not in wide["notes"]


# ---------------------------------------------------------------- y axes --


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("params,bounds", SELECTIONS[:2] + SELECTIONS[3:])
def test_the_range_comes_from_the_driving_points(synthetic_client, model, params, bounds):
    block = get(synthetic_client, model, **params)["by_momentum_bin"]
    for q, spec in block["y_max"].items():
        signed = block["quantities"][q]["signed"]
        strong, weak = [], []
        for s in block["series"]:
            for i in range(len(s["n"])):
                value, lo, hi = s[q][i], s[f"{q}_lo"][i], s[f"{q}_hi"][i]
                if value is None:
                    continue
                if signed:
                    ends = [abs(v) for v in (lo, hi) if v is not None]
                    top = max(ends) if ends else abs(value)
                else:
                    top = hi if hi is not None else value
                core = abs(value) if signed else value
                (strong if s["drives_scale"][i] else weak).append(
                    (top, core, s["key"], block["bins"]["index"][i]))
        if strong:
            expected = nice_top(max(t for t, *_ in strong))
            assert not spec["provisional"] and spec["value"] == pytest.approx(expected, rel=1e-5)
        else:
            # Provisional: set by the weak points' values alone, whiskers excluded.
            assert spec["provisional"] and "Provisional" in spec["note"]
            peak = max((c for _, c, *_ in weak), default=0.0)
            if peak > 0:
                assert spec["value"] == pytest.approx(nice_top(peak), rel=1e-5)
        if spec["value"] is not None:
            listed = {(o["series"], o["bin"]) for o in spec["overflow"]}
            exceeding = {(k, b) for t, _, k, b in weak if t > spec["value"]}
            assert spec["n_overflow"] == len(exceeding)
            assert listed <= exceeding and (len(listed) == len(exceeding) or len(listed) == 24)
        assert spec["min"] == (-spec["value"] if signed else 0.0)


def test_a_narrow_selection_leaves_the_range_provisional(synthetic_client):
    block = get(synthetic_client, "energy", e1_min=9.0, e1_max=10.0, e2_min=9.0, e2_max=10.0)[
        "by_momentum_bin"]
    assert not any(any(s["drives_scale"]) for s in block["series"])
    assert all(spec["provisional"] for spec in block["y_max"].values())


# --------------------------------------------------- the rest of the body --


def test_the_default_body_is_the_base_set_and_the_block_adds_exactly_one_key(synthetic_client):
    default = synthetic_client.get("/api/model-performance", params={"model": "energy"}).json()
    both = get(synthetic_client, "energy")
    assert set(both) == set(default) | {"by_momentum_bin"}
    for key in ("cards", "by_slice", "slices", "network", "model", "n_events", "notes", "filter"):
        assert both[key] == default[key], key
    extra = {k: v for k, v in both["meta"].items() if k not in default["meta"]}
    assert extra == {"slice_by": "momentum_bin"}
    again = synthetic_client.get("/api/model-performance",
                                 params={"model": "energy", "slice_by": "d"}).json()
    assert set(again) == set(default) and "slice_by" not in again["meta"]


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("coord_system", ddl.COORD_SYSTEMS)
def test_the_response_satisfies_its_contract_and_the_size_budget(synthetic_client, model,
                                                                  coord_system):
    response = synthetic_client.get("/api/model-performance", params={
        "model": model, "coord_system": coord_system, "slice_by": "momentum_bin"})
    assert len(response.content) < density.RESPONSE_LIMIT
    assert len(response.content) < 0.6 * density.RESPONSE_LIMIT
    contract_check.check(response.json(), "performance_momentum")
    assert response.json()["meta"]["warnings"] == []


@pytest.mark.parametrize("model", ("energy", "angle"))
def test_no_sentence_signs_a_number_with_a_hyphen(synthetic_client, model):
    def strings(node, path=""):
        if isinstance(node, str):
            yield path, node
        elif isinstance(node, dict):
            for key, value in node.items():
                yield from strings(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from strings(value, f"{path}[{i}]")

    for params in ({}, {"e1_min": 2.0, "e1_max": 4.0, "e2_min": 2.0, "e2_max": 4.0}):
        body = get(synthetic_client, model, **params)
        for path, text in strings(body):
            if path.endswith((".table_name", ".column")):
                continue
            assert not signed_hyphens(text), (path, signed_hyphens(text))


def test_the_notes_say_what_the_chart_cannot(synthetic_client):
    notes = get(synthetic_client, "angle")["by_momentum_bin"]["notes"]
    assert "e1_bin" in notes["own_bin"] and "e2_bin" in notes["own_bin"]
    assert "never zero-filled" in notes["showers"]
    assert "no sampling-fraction" in notes["calibration"]
    assert "azimuth" in notes["angle"] and "nothing to wrap" in notes["angle"]
    assert "energy" not in get(synthetic_client, "energy")["by_momentum_bin"]["notes"].get("angle", "")


def test_the_quantities_name_their_intervals(synthetic_client):
    quantities = get(synthetic_client, "energy")["by_momentum_bin"]["quantities"]
    assert set(quantities) == {"rmse", "mae", "median_rel", "bias"}
    assert quantities["rmse"]["unit"] == "GeV" and quantities["median_rel"]["unit"] == "fraction"
    assert "χ²" in quantities["rmse"]["interval"] and "bootstrap" in quantities["rmse"]["interval"]
    assert "normally distributed residuals" in quantities["rmse"]["interval"]
    assert "Student-t" in quantities["mae"]["interval"] and "clipped at 0" in quantities["mae"]["interval"]
    assert "bootstrap" in quantities["median_rel"]["interval"]
    assert "order-statistic" in quantities["median_rel"]["interval"]
    assert quantities["bias"]["signed"] and not quantities["rmse"]["signed"]
    angle = get(synthetic_client, "angle")["by_momentum_bin"]["quantities"]
    assert angle["rmse"]["unit"] == "mrad" and angle["median_abs"]["unit"] == "mrad"


# ------------------------------------------------------- payload guard --


def test_the_guard_sheds_the_cross_check_arrays_first_and_says_so(synthetic_client, monkeypatch):
    full = synthetic_client.get("/api/model-performance", params={
        "model": "angle", "slice_by": "momentum_bin"})
    size = len(full.content)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", size - 400)
    shed = synthetic_client.get("/api/model-performance", params={
        "model": "angle", "slice_by": "momentum_bin"})
    body = shed.json()
    assert len(shed.content) < size - 400
    block = body["by_momentum_bin"]
    assert all("median_rel_order_lo" not in s for s in block["series"])
    notice = next(w for w in body["meta"]["warnings"] if "order-statistic cross-check" in w)
    # The size the notice quotes is that of the body as first built; the digits of total_ms
    # make two requests differ by a few bytes.
    assert abs(quoted_bytes(notice) - size) < 64
    assert not any("significant figures" in w for w in body["meta"]["warnings"])
    # What the whiskers say is untouched.
    for a, b in zip(full.json()["by_momentum_bin"]["series"], block["series"]):
        assert a["median_rel_hi"] == b["median_rel_hi"] and a["rmse_hi"] == b["rmse_hi"]
    contract_check.check(body, "performance_momentum")


def test_the_guard_then_rounds_and_finally_serves_as_it_is_with_a_notice(synthetic_client,
                                                                          monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 15_000)
    response = synthetic_client.get("/api/model-performance", params={
        "model": "angle", "slice_by": "momentum_bin"})
    body = response.json()
    warnings = body["meta"]["warnings"]
    assert any("order-statistic cross-check" in w for w in warnings)
    assert any("4 significant figures" in w for w in warnings)
    assert any(w.startswith("Served as it is") and "15,000-byte" in w for w in warnings)
    assert all("median_rel_order_lo" not in s for s in body["by_momentum_bin"]["series"])
    contract_check.check(body, "performance_momentum")


def test_the_guard_leaves_the_separation_view_alone(synthetic_client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1_000)
    body = synthetic_client.get("/api/model-performance", params={"model": "energy"}).json()
    assert body["meta"]["warnings"] == [] and "by_momentum_bin" not in body


# ------------------------------------------------------------- a selection --


def test_an_empty_selection_is_empty_and_says_so(synthetic_client):
    body = get(synthetic_client, "energy", e1_min=19.0, e1_max=19.5)
    block = body["by_momentum_bin"]
    assert block["n_events"] == 0
    assert not any(sum(s["n"]) for s in block["series"])
    assert all(v is None for s in block["series"] for v in s["rmse"])
    assert "No events match the current selection." in body["meta"]["warnings"]
    assert all(spec["value"] is None and spec["provisional"] for spec in block["y_max"].values())
    contract_check.check(json.loads(json.dumps(body)), "performance_momentum")


# ------------------------------------------------ a shower without a prediction --


@pytest.fixture
def a_predictions_removed(synthetic_client, request):
    """Shower A's absolute-frame predictions NULL for the first ``request.param`` events, restored after."""
    database = synthetic_client.app.state.database
    name = naming.event_table(BASELINE_TABLE)
    columns = ("en_pred_a_abs", "th_pred_a_abs")
    total = f'SELECT {", ".join(f"sum({c})" for c in columns)} FROM "{name}"'
    last = request.param
    with database.write_lock() as con:
        before = con.execute(total).fetchone()
        con.execute(f'CREATE TABLE saved_predictions AS SELECT event_number, {", ".join(columns)} '
                    f'FROM "{name}" WHERE event_number <= {last}')
        con.execute(f'UPDATE "{name}" SET {", ".join(c + " = NULL" for c in columns)} '
                    f"WHERE event_number <= {last}")
    yield last
    with database.write_lock() as con:
        con.execute(f'UPDATE "{name}" AS t SET {", ".join(f"{c} = s.{c}" for c in columns)} '
                    "FROM saved_predictions AS s WHERE t.event_number = s.event_number")
        con.execute("DROP TABLE saved_predictions")
        assert con.execute(total).fetchone() == before


@pytest.mark.parametrize("a_predictions_removed", [40, 286], indirect=True)
@pytest.mark.parametrize("model", ("energy", "angle"))
def test_a_shower_without_a_prediction_is_counted_and_never_zero_filled(
        synthetic_client, a_predictions_removed, model):
    database = synthetic_client.app.state.database
    with database.read_cursor() as con:
        raw = con.execute(
            f'SELECT event_number, e1_bin, {STEMS[model]}_true_a AS t, '
            f'{STEMS[model]}_pred_a_abs AS p FROM "{naming.event_table(BASELINE_TABLE)}"'
        ).fetchnumpy()
    event = raw["event_number"]
    bins = np.asarray(raw["e1_bin"], dtype=np.float64)
    removed = event <= a_predictions_removed

    body = get(synthetic_client, model)
    block = body["by_momentum_bin"]
    a_abs, a_trn, b_abs = (series_of(block, "lab", "a"), series_of(block, "trans", "a"),
                           series_of(block, "lab", "b"))
    for i, k in enumerate(block["bins"]["index"]):
        in_bin = bins == k
        assert a_abs["n_missing"][i] == int((in_bin & removed).sum())
        assert a_abs["n"][i] == int((in_bin & ~removed).sum())
        assert a_trn["n_missing"][i] == 0 and b_abs["n_missing"][i] == 0
        assert a_trn["n"][i] == int(in_bin.sum())
    if a_predictions_removed < 286:
        # A mean of the showers that have a prediction, not of those and some zeros.
        i = max(range(len(a_abs["n"])), key=lambda j: a_abs["n"][j])
        k = block["bins"]["index"][i]
        keep = (bins == k) & ~removed
        t = np.ma.filled(np.ma.asarray(raw["t"]).astype(np.float64), np.nan)[keep]
        p = np.ma.filled(np.ma.asarray(raw["p"]).astype(np.float64), np.nan)[keep]
        scale = 1000.0 if model == "angle" else 1.0
        assert a_abs["bias"][i] == approx(np.mean((p - t) * scale))
        assert not any("no absolute-frame" in w for w in body["meta"]["warnings"])
    else:
        assert sum(a_abs["n"]) == 0 and all(v is None for v in a_abs["rmse"])
        assert any("Shower A has no absolute-frame" in w for w in body["meta"]["warnings"])
    contract_check.check(body, "performance_momentum")


# ------------------------------------------------ a bin column that disagrees --


@pytest.fixture
def bins_shifted(synthetic_client):
    """Shower A's producer bin moved up by one for the first 30 events, restored after."""
    database = synthetic_client.app.state.database
    name = naming.event_table(BASELINE_TABLE)
    total = f'SELECT sum(e1_bin), sum(e2_bin) FROM "{name}"'
    with database.write_lock() as con:
        before = con.execute(total).fetchone()
        con.execute(f'UPDATE "{name}" SET e1_bin = e1_bin + 1 WHERE event_number <= 30')
    yield
    with database.write_lock() as con:
        con.execute(f'UPDATE "{name}" SET e1_bin = e1_bin - 1 WHERE event_number <= 30')
        assert con.execute(total).fetchone() == before


def test_a_bin_column_that_disagrees_with_the_momenta_is_labelled_by_number_and_reported(
        synthetic_client, bins_shifted):
    body = get(synthetic_client, "energy")
    block = body["by_momentum_bin"]
    labels = dict(zip(block["bins"]["index"], block["bins"]["label"]))
    # Every bin one of the shifted events landed in now holds momenta from outside [k, k + 1).
    odd = [k for k, label in labels.items() if label.startswith("bin ")]
    assert odd and all("GeV)" in labels[k] and "p " in labels[k] for k in odd)
    for k in odd:
        i = block["bins"]["index"].index(k)
        assert block["bins"]["p_lo"][i] < k or block["bins"]["p_hi"][i] >= k + 1
    assert block["notes"]["labels"] in body["meta"]["warnings"]
    assert "disagrees" in block["notes"]["labels"]
    contract_check.check(body, "performance_momentum")


def test_the_groups_run_on_the_services_own_thread_allocation(synthetic_client, monkeypatch):
    """The pool is bounded by Settings.threads, the figure /api/health reports, never os.cpu_count()."""
    from calosrv.query import performance_bins as pb

    seen = []
    real = pb.map_groups
    monkeypatch.setattr(pb, "map_groups", lambda fn, tasks, workers=1: seen.append(workers) or real(fn, tasks, workers))
    get(synthetic_client, "energy")
    threads = synthetic_client.get("/api/health").json()["threads"]
    assert seen == [threads]
