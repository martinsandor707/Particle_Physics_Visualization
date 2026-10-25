"""``GET /api/prediction-density`` against the event table.

Booted on ``synthetic_all_models``: 286 events with true momenta uniform over
2-18 GeV and the networks' columns copied from two template events, so the
predictions are scattered (many beyond the truth range - good for the outside
counts) rather than physical. Every raster, range and estimate is recomputed
from the event table with NumPy and compared with the payload.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE
from calosrv.db import ddl, naming
from calosrv.query import density
from calosrv.stats import clip, metrics
from calosrv.text import signed_hyphens

FRAME_CODES = {"lab": "abs", "trans": "trn", "local": "loc"}
FRAMES = {"lab": "absolute", "trans": "trans", "local": "local"}
STEMS = {"energy": "en", "angle": "th"}

#: (query parameters, the selection as bounds on e1 and e2).
SELECTIONS = (
    ({}, (0.0, 99.0, 0.0, 99.0)),
    ({"e1_max": 9.0}, (0.0, 9.0, 0.0, 99.0)),
    ({"e1_min": 2.0, "e1_max": 4.0, "e2_min": 2.0, "e2_max": 4.0}, (2.0, 4.0, 2.0, 4.0)),
)


@pytest.fixture(scope="module")
def table(synthetic_client):
    with synthetic_client.app.state.database.read_cursor() as con:
        raw = con.execute(f'SELECT * FROM "{naming.event_table(BASELINE_TABLE)}"').fetchnumpy()
    return {k: np.ma.filled(np.ma.asarray(v).astype(np.float64), np.nan) for k, v in raw.items()}


def get(client, **params):
    response = client.get("/api/prediction-density", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def scale(model):
    return 1000.0 if model == "angle" else 1.0


def expected_range(table, model):
    truth = np.concatenate([table[f"{STEMS[model]}_true_a"], table[f"{STEMS[model]}_true_b"]])
    lo, hi, _ = clip.nice_range(truth.min() * scale(model), truth.max() * scale(model), fine=True)
    return (0.0 if model == "energy" else lo), hi


def pairs_of(table, model, coord, shower, bounds):
    lo1, hi1, lo2, hi2 = bounds
    chosen = ((table["e1"] >= lo1) & (table["e1"] <= hi1) & (table["e2"] >= lo2)
              & (table["e2"] <= hi2) & np.isfinite(table["d"]))
    true = table[f"{STEMS[model]}_true_{shower}"][chosen] * scale(model)
    pred = table[f"{STEMS[model]}_pred_{shower}_{FRAME_CODES[coord]}"][chosen] * scale(model)
    keep = np.isfinite(true) & np.isfinite(pred)
    return true[keep], pred[keep], int(chosen.sum())


# -------------------------------------------------------------------- axes --


@pytest.mark.parametrize("model", ("energy", "angle"))
def test_the_axes_are_the_whole_tables_range_and_ignore_the_selection(synthetic_client, table, model):
    lo, hi = expected_range(table, model)
    wide = get(synthetic_client, model=model)
    narrow = get(synthetic_client, model=model, e1_min=9.0, e1_max=10.0)
    assert wide["axes"] == narrow["axes"]
    for key in ("truth", "pred"):
        axis = wide["axes"][key]
        assert (axis["lo"], axis["hi"]) == (lo, hi) and axis["n"] == 64
        assert axis["unit"] == ("GeV" if model == "energy" else "mrad")
        assert axis["zero_based"] is (lo == 0.0)
    assert wide["axes"]["truth"]["label"] != wide["axes"]["pred"]["label"]
    # The identity line is the diagonal of that square.
    assert wide["identity"]["from"] == lo and wide["identity"]["to"] == hi
    assert narrow["n_events"] < wide["n_events"]


def test_the_energy_axis_starts_at_zero_and_the_angle_axis_says_it_does_not(synthetic_client):
    energy = get(synthetic_client, model="energy")["axes"]["truth"]
    angle = get(synthetic_client, model="angle")["axes"]["truth"]
    assert energy["lo"] == 0.0 and energy["zero_based"] is True
    assert angle["lo"] > 0 and angle["zero_based"] is False


# ------------------------------------------------------------------ raster --


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("coord_system", ddl.COORD_SYSTEMS)
@pytest.mark.parametrize("params,bounds", SELECTIONS)
def test_each_showers_pairs_equal_numpy(synthetic_client, table, model, coord_system, params, bounds):
    body = get(synthetic_client, model=model, coord_system=coord_system, bins=48, **params)
    lo, hi = expected_range(table, model)
    edges = np.linspace(lo, hi, 49)
    assert body["network"] == {"model": model, "frame": FRAMES[coord_system]}
    for shower in ("a", "b"):
        true, pred, selected = pairs_of(table, model, coord_system, shower, bounds)
        block = body["density"][shower]
        assert block["n"] == true.size
        outside = ((true < lo) | (true > hi) | (pred < lo) | (pred > hi))
        assert block["outside"] == {
            "truth_below": int((true < lo).sum()), "truth_above": int((true > hi).sum()),
            "pred_below": int((pred < lo).sum()), "pred_above": int((pred > hi).sum()),
            "total": int(outside.sum())}
        assert block["n_in_range"] == true.size - int(outside.sum())
        if true.size < 15:
            assert block["encoding"] == "pairs" and "counts" not in block
            order = np.lexsort((pred, true))
            got = np.asarray(block["pairs"]).reshape(-1, 2)
            assert got == pytest.approx(np.column_stack([true[order], pred[order]]), rel=1e-5)
        else:
            assert block["encoding"] == "counts" and block["shape"] == [48, 48]
            expected, _, _ = np.histogram2d(pred, true, bins=[edges, edges])
            counts = np.asarray(block["counts"]).reshape(48, 48)
            assert np.array_equal(counts, expected.astype(int))
            assert int(counts.sum()) + block["outside"]["total"] == block["n"]
            assert block["max_count"] == int(counts.max())


def test_predictions_beyond_the_truth_range_are_counted_not_dropped(synthetic_client, table):
    body = get(synthetic_client, model="energy")
    block = body["density"]["a"]
    # The template's 19.2 GeV prediction sits above the 18 GeV truth axis for half the events.
    assert block["outside"]["pred_above"] > 100 and block["n_in_range"] < block["n"]
    assert any("outside the shared axis" in w and "not drawn" in w for w in body["meta"]["warnings"])


def test_a_low_n_selection_ships_pairs_and_says_so(synthetic_client):
    body = get(synthetic_client, model="angle", e1_min=2.0, e1_max=4.0, e2_min=2.0, e2_max=4.0)
    for shower in ("a", "b"):
        block = body["density"][shower]
        assert block["encoding"] == "pairs" and 0 < block["n"] < 15
        assert len(block["pairs"]) == block["n"]
    assert any("below the 15 a density needs" in w for w in body["meta"]["warnings"])
    assert body["color"]["vmax"] == 0.0
    contract_check.check(body, "prediction_density")


def test_a_selection_of_fifteen_gets_a_density_and_fourteen_does_not(synthetic_client, table):
    # Walk the e1 ceiling up until shower A first reaches fifteen selected showers.
    e1 = np.sort(table["e1"])
    ceiling = float(e1[14])
    at_15 = get(synthetic_client, model="energy", e1_max=ceiling)
    at_14 = get(synthetic_client, model="energy", e1_max=float(e1[13]))
    assert at_15["density"]["a"]["n"] == 15 and at_15["density"]["a"]["encoding"] == "counts"
    assert at_14["density"]["a"]["n"] == 14 and at_14["density"]["a"]["encoding"] == "pairs"


# --------------------------------------------------------------- residuals --


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("params,bounds", SELECTIONS)
def test_residual_estimates_equal_the_cards_summary(synthetic_client, table, model, params, bounds):
    body = get(synthetic_client, model=model, **params)
    residual = body["residual"]
    assert residual["unit"] == ("fraction" if model == "energy" else "mrad")
    for shower in ("a", "b"):
        true, pred, _ = pairs_of(table, model, "lab", shower, bounds)
        r = (pred - true) / true if model == "energy" else pred - true
        summary = metrics.residual_summary(r)
        est = residual["series"][shower]["estimates"]
        assert est["bias"]["n"] == r.size
        if r.size >= 2:
            assert est["bias"]["value"] == pytest.approx(summary.bias.value, rel=1e-5)
            assert est["bias"]["interval"]["lo"] == pytest.approx(summary.bias.interval.lo, rel=1e-5)
            assert est["bias"]["interval"]["hi"] == pytest.approx(summary.bias.interval.hi, rel=1e-5)
            assert est["sigma"]["value"] == pytest.approx(r.std(ddof=1), rel=1e-5)
            assert est["sigma"]["interval"]["method"] == "chi2"
            assert est["rmse"]["value"] == pytest.approx(math.sqrt(np.mean(r ** 2)), rel=1e-5)
        fit = residual["series"][shower]["fit"]
        assert fit["n"] == r.size and fit["sigma"] == pytest.approx(
            r.std(ddof=1) if r.size > 1 else fit["sigma"])


def test_the_residual_axis_is_the_percentile_clip_of_the_drawn_showers(synthetic_client, table):
    body = get(synthetic_client, model="energy")
    values = []
    for shower in ("a", "b"):
        true, pred, _ = pairs_of(table, "energy", "lab", shower, SELECTIONS[0][1])
        values.append((pred - true) / true)
    axis = body["residual"]["axis"]
    clipped = clip.percentile_clip(np.concatenate(values), low=1, high=99, pad=0.05)
    expected = clip.nice_range(clipped.lo, clipped.hi, fine=True)
    assert (axis["lo"], axis["hi"], axis["interval"]) == pytest.approx(expected, rel=1e-6)
    assert axis["provisional"] is False
    assert axis["clipping"]["n_outside"] == clipped.n_outside
    assert axis["bins"] == 14
    for shower in ("a", "b"):
        o = axis["outside"][shower]
        r = values[0 if shower == "a" else 1]
        assert (o["n"], o["below"], o["above"]) == (r.size, int((r < axis["lo"]).sum()),
                                                    int((r > axis["hi"]).sum()))


def test_the_series_climb_the_energy_panels_ladder(synthetic_client):
    full = get(synthetic_client, model="energy")["residual"]["series"]
    assert {s["draw"] for s in full.values()} == {"histogram"}
    few = get(synthetic_client, model="energy", e1_min=2.0, e1_max=4.0, e2_min=2.0,
              e2_max=4.0)["residual"]
    assert few["axis"]["provisional"] is True and "provisional" in few["axis"]["basis"]
    assert {s["draw"] for s in few["series"].values()} <= {"curve+strip", "strip"}
    for s in few["series"].values():
        assert s["drives_scale"] is False and len(s["strip"]["values"]) == s["fit"]["n"]


# ------------------------------------------------------------------ colour --


def test_the_colour_scale_states_a_first_level_that_clears_the_card(synthetic_client):
    body = get(synthetic_client, model="energy")
    color = body["color"]
    peaks = [d["max_count"] for d in body["density"].values()]
    assert color["scale"] == "log10" and color["vmin"] == 0
    assert color["vmax"] == pytest.approx(math.log10(max(peaks)), rel=1e-5)
    first = color["ramp"]["first_level"]
    assert first["color"] == "#29788e" and first["contrast"] >= 3.0 and first["against"] == "#1c2128"
    assert "#29788e" in color["note"] and "#1c2128" in color["note"]
    assert color["empty"] == "transparent" and color["unit"] == "showers per bin"


# ------------------------------------------------------------------ errors --


@pytest.mark.parametrize("params,field", [
    ({"model": "segmentation"}, "model"),
    ({"model": "gpt"}, "model"),
    ({"model": "energy", "coord_system": "polar"}, "coord_system"),
])
def test_unserved_values_are_refused_naming_the_parameter(synthetic_client, params, field):
    response = synthetic_client.get("/api/prediction-density", params=params)
    assert response.status_code == 422
    assert response.json()["field"] == field


def test_segmentation_is_told_where_its_reconstruction_lives(synthetic_client):
    detail = synthetic_client.get("/api/prediction-density", params={"model": "segmentation"}).json()[
        "detail"]
    assert "per-hit" in detail and "energy panel" in detail and "model=energy" in detail


@pytest.mark.parametrize("bins", [0, 15, 129, 1000])
def test_bins_outside_the_range_are_refused(synthetic_client, bins):
    assert synthetic_client.get("/api/prediction-density",
                                params={"model": "energy", "bins": bins}).status_code == 422


def test_the_defaults_are_energy_lab_and_sixty_four_bins(synthetic_client):
    body = synthetic_client.get("/api/prediction-density").json()
    assert body["network"] == {"model": "energy", "frame": "absolute"}
    assert body["axes"]["truth"]["n"] == 64 and body["density"]["a"]["shape"] == [64, 64]
    assert body["meta"]["model"] == "energy" and body["meta"]["coord_system"] == "lab"


# --------------------------------------------------------- contract, size --


@pytest.mark.parametrize("model", ("energy", "angle"))
@pytest.mark.parametrize("coord_system", ddl.COORD_SYSTEMS)
@pytest.mark.parametrize("bins", [16, 64, 128])
@pytest.mark.parametrize("params", [p for p, _ in SELECTIONS])
def test_every_view_satisfies_the_contract_and_stays_under_the_limit(synthetic_client, model,
                                                                     coord_system, bins, params):
    response = synthetic_client.get("/api/prediction-density", params={
        "model": model, "coord_system": coord_system, "bins": bins, **params})
    assert response.status_code == 200
    assert len(response.content) < density.RESPONSE_LIMIT, (model, coord_system, bins, params)
    body = response.json()
    contract_check.check(body, "prediction_density")
    assert body["filter"]["e1"][1] == params.get("e1_max", body["filter"]["e1"][1])
    assert not any("The density is drawn on" in w for w in body["meta"]["warnings"])


def test_the_filter_is_echoed_and_n_events_is_the_selection(synthetic_client, table):
    body = get(synthetic_client, model="energy", e1_min=5.0, e1_max=9.0)
    expected = int(((table["e1"] >= 5.0) & (table["e1"] <= 9.0)).sum())
    assert body["n_events"] == expected
    assert body["filter"]["e1"] == [5.0, 9.0] and body["filter"]["include_undefined_d"] is False


def test_no_sentence_signs_a_number_with_a_hyphen(synthetic_client):
    def strings(node, path=""):
        if isinstance(node, str):
            yield path, node
        elif isinstance(node, dict):
            for key, value in node.items():
                yield from strings(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from strings(value, f"{path}[{i}]")

    for model in ("energy", "angle"):
        for params in ({}, {"e1_min": 2.0, "e1_max": 4.0, "e2_min": 2.0, "e2_max": 4.0}):
            for path, text in strings(get(synthetic_client, model=model, **params)):
                if path.endswith(".table_name"):
                    continue
                assert not signed_hyphens(text), (path, signed_hyphens(text))


# ------------------------------------------------------------ payload guard --


def test_the_guard_lowers_the_bin_count_keeps_the_range_and_says_so(synthetic_client, monkeypatch):
    base = synthetic_client.get("/api/prediction-density", params={"model": "energy", "bins": 64})
    size = len(base.content)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", size - 200)
    stepped = synthetic_client.get("/api/prediction-density", params={"model": "energy", "bins": 64})
    body = stepped.json()
    assert len(stepped.content) < size - 200
    assert body["axes"]["truth"]["n"] == 48 and body["density"]["a"]["shape"] == [48, 48]
    notice = next(w for w in body["meta"]["warnings"] if w.startswith("The density is drawn on"))
    assert "48 bins per axis instead of 64" in notice
    # The size quoted is that of the body as first built; total_ms digits move it by a few bytes.
    quoted = int(re.search(r"\(([\d,]+) bytes at 64\)", notice).group(1).replace(",", ""))
    assert abs(quoted - size) < 64
    # The same dataset-wide range, and every pair still accounted for.
    assert body["axes"]["truth"]["lo"] == base.json()["axes"]["truth"]["lo"]
    assert body["axes"]["truth"]["hi"] == base.json()["axes"]["truth"]["hi"]
    for shower in ("a", "b"):
        block, ref = body["density"][shower], base.json()["density"][shower]
        assert sum(block["counts"]) + block["outside"]["total"] == block["n"] == ref["n"]
        assert block["outside"] == ref["outside"]
    contract_check.check(body, "prediction_density")


def test_the_guard_steps_down_as_far_as_it_must_and_then_serves_as_it_is(synthetic_client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 12_000)
    response = synthetic_client.get("/api/prediction-density", params={"model": "energy", "bins": 128})
    body = response.json()
    assert body["axes"]["truth"]["n"] == 16
    warnings = body["meta"]["warnings"]
    assert any("16 bins per axis instead of 128" in w for w in warnings)
    assert any(w.startswith("Served as it is") and "12,000-byte" in w and "16 bins" in w
               for w in warnings)
    assert len(response.content) >= 12_000
    contract_check.check(body, "prediction_density")


def test_a_default_sized_response_is_never_touched_by_the_guard(synthetic_client):
    body = get(synthetic_client, model="energy", bins=128)
    assert body["axes"]["truth"]["n"] == 128
    assert not any("The density is drawn on" in w for w in body["meta"]["warnings"])


# --------------------------------------------- a shower without a prediction --


@pytest.fixture
def a_predictions_removed(synthetic_client):
    """Shower A's absolute-frame energy predictions NULL for the first 100 events, restored after."""
    database = synthetic_client.app.state.database
    name = naming.event_table(BASELINE_TABLE)
    total = f'SELECT sum(en_pred_a_abs) FROM "{name}"'
    with database.write_lock() as con:
        before = con.execute(total).fetchone()
        con.execute(f'CREATE TABLE saved_density_predictions AS SELECT event_number, en_pred_a_abs '
                    f'FROM "{name}" WHERE event_number <= 100')
        con.execute(f'UPDATE "{name}" SET en_pred_a_abs = NULL WHERE event_number <= 100')
    yield 100
    with database.write_lock() as con:
        con.execute(f'UPDATE "{name}" AS t SET en_pred_a_abs = s.en_pred_a_abs '
                    "FROM saved_density_predictions AS s WHERE t.event_number = s.event_number")
        con.execute("DROP TABLE saved_density_predictions")
        assert con.execute(total).fetchone() == before


def test_a_shower_without_a_prediction_is_not_a_pair_and_not_a_zero(synthetic_client,
                                                                     a_predictions_removed):
    body = get(synthetic_client, model="energy")
    assert body["n_events"] == 286
    a, b = body["density"]["a"], body["density"]["b"]
    assert a["n"] == 186 and b["n"] == 286
    assert a["outside"]["pred_below"] == 0  # nothing was filled with zero
    # The dropped showers are counted, by cause, and the meta warnings say so.
    assert a["n_missing"] == {"total": 100, "prediction": 100, "truth": 0}
    assert b["n_missing"]["total"] == 0
    assert any(w.startswith("Shower A: 100 selected events were left out")
               for w in body["meta"]["warnings"])
    assert body["residual"]["series"]["a"]["fit"]["n"] == 186
    # The other frame of the same shower is untouched.
    assert get(synthetic_client, model="energy", coord_system="trans")["density"]["a"]["n"] == 286
