"""Prediction against truth on bare arrays: the raster, the colour and the residual ladder.

No database and no server. ``density_block`` and ``assemble`` take the finite
(truth, prediction) pairs the one event-table read returns, so a shower of 14
or 15 pairs, a residual with outliers, or a prediction beyond the axis can be
built by hand and checked against NumPy and an independent WCAG formula.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import contract_check
from calosrv.encode.numbers import sig
from calosrv.query import density
from calosrv.query import prediction_density as pd
from calosrv.stats import clip, gaussian, histogram, metrics
from calosrv.text import MINUS, signed_hyphens

rng = np.random.default_rng(5)


def hex_rgb(text: str):
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def wcag(a, b):
    """An independent WCAG contrast: written here from the definition, not imported."""
    def lum(rgb):
        out = []
        for c in rgb:
            v = c / 255.0
            out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------- raster --


def test_counts_are_row_major_with_one_row_per_prediction_bin():
    truth = np.array([3.5, 3.5, 10.5] + [0.5] * 12)
    pred = np.array([5.5, 5.5, 2.5] + [0.5] * 12)
    block = pd.density_block(truth, pred, 0.0, 16.0, bins=16)
    assert block["encoding"] == "counts" and block["shape"] == [16, 16]
    counts = np.asarray(block["counts"]).reshape(16, 16)
    assert counts[5, 3] == 2 and counts[2, 10] == 1 and counts[0, 0] == 12
    assert block["counts"][5 * 16 + 3] == 2 and len(block["counts"]) == 256
    assert block["n"] == 15 == block["n_in_range"] == int(counts.sum()) and block["max_count"] == 12


def test_the_raster_equals_numpy_and_sums_with_the_outside_count_to_n():
    truth = rng.uniform(-1.0, 21.0, 400)
    pred = truth + rng.normal(0.0, 1.5, 400)
    block = pd.density_block(truth, pred, 0.0, 20.0, bins=32)
    edges = np.linspace(0.0, 20.0, 33)
    expected, _, _ = np.histogram2d(pred, truth, bins=[edges, edges])
    assert np.array_equal(np.asarray(block["counts"]).reshape(32, 32), expected.astype(int))
    o = block["outside"]
    assert o["truth_below"] == int((truth < 0).sum()) and o["truth_above"] == int((truth > 20).sum())
    assert o["pred_below"] == int((pred < 0).sum()) and o["pred_above"] == int((pred > 20).sum())
    either = (truth < 0) | (truth > 20) | (pred < 0) | (pred > 20)
    assert o["total"] == int(either.sum()) > 0
    assert sum(block["counts"]) + o["total"] == block["n"] == 400
    assert block["n_in_range"] == sum(block["counts"])


def test_a_value_on_the_upper_edge_belongs_to_the_last_bin_not_to_outside():
    truth = np.full(15, 20.0)
    pred = np.full(15, 20.0)
    block = pd.density_block(truth, pred, 0.0, 20.0, bins=16)
    assert block["counts"][-1] == 15 and block["outside"]["total"] == 0


def test_below_fifteen_pairs_a_shower_gets_its_pairs_not_a_density():
    truth = np.sort(rng.uniform(1.0, 19.0, 15))
    pred = truth * 1.02
    few = pd.density_block(truth[:14], pred[:14], 0.0, 20.0, bins=64)
    assert few["encoding"] == "pairs" and "counts" not in few and few["n"] == 14
    assert few["pairs"] == [[sig(t), sig(p)] for t, p in zip(truth[:14], pred[:14])]
    assert few["n_in_range"] == 14 and few["outside"]["total"] == 0
    full = pd.density_block(truth, pred, 0.0, 20.0, bins=64)
    assert full["encoding"] == "counts" and full["n"] == 15
    assert pd.MIN_DENSITY_SAMPLES == histogram.MIN_HISTOGRAM_SAMPLES == 15


def test_pairs_are_ordered_and_pairs_beyond_the_axis_are_counted_too():
    block = pd.density_block(np.array([5.0, 1.0, 3.0]), np.array([4.0, 30.0, 2.0]), 0.0, 20.0, 64)
    assert block["pairs"] == [[1.0, 30.0], [3.0, 2.0], [5.0, 4.0]]
    assert block["outside"] == {"truth_below": 0, "truth_above": 0, "pred_below": 0,
                                "pred_above": 1, "total": 1}
    assert block["n_in_range"] == 2
    empty = pd.density_block(np.empty(0), np.empty(0), 0.0, 20.0, 64)
    assert empty["pairs"] == [] and empty["n"] == 0 and empty["n_in_range"] == 0


@pytest.mark.parametrize("which", ["counts", "pairs"])
def test_both_blocks_satisfy_their_contract_definitions(which):
    n = 200 if which == "counts" else 9
    truth = rng.uniform(0.0, 20.0, n)
    block = pd.density_block(truth, truth + rng.normal(0, 2, n), 0.0, 20.0, 64)
    contract_check.check(json.loads(json.dumps(block)), "prediction_density", at=f"{which}_block")


def test_the_bin_ladder_steps_down_to_a_floor():
    assert pd.next_bins(128) == 96 and pd.next_bins(64) == 48 and pd.next_bins(48) == 32
    assert pd.next_bins(80) == 64 and pd.next_bins(17) == 16
    assert pd.next_bins(16) is None


# --------------------------------------------------------------- colour --


def test_the_first_colour_level_clears_three_to_one_against_the_card():
    block = pd.color_block(2.0)
    first = block["ramp"]["first_level"]
    assert first["against"] == "#1c2128" and first["count"] == 1
    measured = wcag(hex_rgb(first["color"]), hex_rgb("#1c2128"))
    assert measured >= 3.0 and first["contrast"] == pytest.approx(measured, abs=0.006)
    assert block["ramp"]["stops"][0] == first["color"]
    # The state of the art without the fix: Viridis' own first colour.
    assert wcag(hex_rgb("#440154"), hex_rgb("#1c2128")) < 1.1
    assert first["color"] in block["note"] and "1.06:1" in block["note"]


def test_the_ramp_starts_at_the_first_position_that_clears_it():
    start = pd.ramp_start()
    assert wcag(pd.viridis(start), pd.CARD_RGB) >= 3.0
    assert wcag(pd.viridis(round(start - 0.05, 10)), pd.CARD_RGB) < 3.0
    assert start == pytest.approx(0.4)
    assert pd.hex_of(pd.viridis(start)) == "#29788e"


def test_the_stops_brighten_monotonically_to_viridis_yellow():
    stops = pd.color_block(1.0)["ramp"]["stops"]
    lums = [pd.luminance(hex_rgb(s)) for s in stops]
    assert lums == sorted(lums) and len(set(lums)) == len(lums)
    assert stops[-1] == "#fde725" and pd.viridis(0.0) == (68, 1, 84) and pd.viridis(1.0) == (253, 231, 37)
    assert all(wcag(hex_rgb(s), hex_rgb("#1c2128")) >= 3.0 for s in stops)


def test_the_scale_is_log10_with_transparent_empty_bins():
    block = pd.color_block(math.log10(250))
    assert block["scale"] == "log10" and block["vmin"] == 0 and block["vmax"] == sig(math.log10(250))
    assert block["empty"] == "transparent" and block["unit"] == "showers per bin"


# ------------------------------------------------------------- residual --


def selection(model="energy", a=(300, 0.05), b=(300, 0.05), lo=0.0, hi=20.0, seed=1):
    """A hand-built selection: shower A and B with ``(N, relative spread)`` of their residuals."""
    r = np.random.default_rng(seed)
    truth, pred = {}, {}
    for shower, (n, spread) in zip("ab", (a, b)):
        t = r.uniform(1.0, 19.0, n)
        if model == "energy":
            truth[shower], pred[shower] = t, t * (1.0 + r.normal(0.01, spread, n))
        else:
            t = t / 20.0 * 500.0 + 60.0
            truth[shower], pred[shower] = t, t + r.normal(2.0, spread, n)
    return pd.Selection(model, "lab", lo, hi, max(a[0], b[0]), truth, pred)


def test_energy_residuals_are_relative_and_angle_residuals_are_in_mrad():
    sel = selection("energy", a=(50, 0.1), b=(50, 0.1))
    values, excluded = pd.residuals(sel)
    assert np.allclose(values["a"], (sel.pred["a"] - sel.truth["a"]) / sel.truth["a"])
    assert excluded == {"a": 0, "b": 0}
    ang = selection("angle", a=(50, 3.0), b=(50, 3.0))
    values, _ = pd.residuals(ang)
    assert np.allclose(values["b"], ang.pred["b"] - ang.truth["b"])


def test_a_relative_residual_needs_a_positive_truth_and_the_rest_are_counted():
    sel = pd.Selection("energy", "lab", 0.0, 20.0, 3,
                       {"a": np.array([0.0, 2.0, 4.0]), "b": np.array([1.0])},
                       {"a": np.array([1.0, 3.0, 5.0]), "b": np.array([2.0])})
    values, excluded = pd.residuals(sel)
    assert excluded == {"a": 1, "b": 0} and np.allclose(values["a"], [0.5, 0.25])


def test_a_weak_shower_never_sets_the_residual_axis():
    """Display ranges follow robust evidence: ten wild showers beside three hundred good ones."""
    sel = selection(a=(300, 0.05), b=(10, 0.05))
    sel.pred["b"] = sel.truth["b"] * np.array([5, -3, 6, 4, -2, 7, 5, 6, -3, 8.0])
    block = pd.residual_block(sel)
    axis = block["axis"]
    assert axis["provisional"] is False and "N ≥ 15" in axis["basis"]
    a_values, _ = pd.residuals(sel)
    good = np.percentile(a_values["a"], [1, 99])
    assert axis["lo"] <= good[0] and axis["hi"] >= good[1] and axis["hi"] - axis["lo"] < 1.0
    # The wild shower is clipped and counted, not allowed to stretch the axis.
    assert block["axis"]["outside"]["b"]["n"] == 10 and (
        block["axis"]["outside"]["b"]["above"] + block["axis"]["outside"]["b"]["below"]) > 0
    assert block["series"]["a"]["draw"] == "histogram" and block["series"]["a"]["drives_scale"]
    assert block["series"]["b"]["draw"] == "curve+strip" and not block["series"]["b"]["drives_scale"]
    # The axis is the percentile clip of A, rounded outward, and its disclosure travels along.
    clipped = clip.percentile_clip(a_values["a"], low=1, high=99, pad=0.05)
    assert (axis["lo"], axis["hi"], axis["interval"]) == clip.nice_range(clipped.lo, clipped.hi, fine=True)
    assert axis["clipping"]["n_total"] == 300 and axis["clipping"]["n_outside"] == clipped.n_outside


def test_with_no_shower_at_fifteen_the_axis_covers_everything_and_is_provisional():
    sel = selection(a=(9, 0.4), b=(3, 0.4))
    block = pd.residual_block(sel)
    values, _ = pd.residuals(sel)
    both = np.concatenate([values["a"], values["b"]])
    axis = block["axis"]
    assert axis["provisional"] is True and "provisional" in axis["basis"]
    assert axis["lo"] <= both.min() and axis["hi"] >= both.max()
    assert block["series"]["a"]["draw"] == "curve+strip" and block["series"]["b"]["draw"] == "strip"
    assert not any(s["drives_scale"] for s in block["series"].values())
    assert axis["outside"]["a"]["below"] == axis["outside"]["a"]["above"] == 0


def test_the_bin_count_follows_the_smaller_drawn_shower():
    block = pd.residual_block(selection(a=(2000, 0.05), b=(30, 0.05)))
    assert block["axis"]["bins"] == histogram.adaptive_bins(30)
    assert len(block["axis"]["hist_centres"]) == block["axis"]["bins"]
    assert len(block["axis"]["curve_x"]) == histogram.CURVE_POINTS
    assert pd.residual_block(selection(a=(5, 0.05), b=(4, 0.05)))["axis"]["bins"] == histogram.MIN_BINS


def test_the_mean_and_the_sigma_band_are_two_marks_with_their_own_intervals():
    sel = selection(a=(60, 0.08), b=(60, 0.08))
    block = pd.residual_block(sel)
    values, _ = pd.residuals(sel)
    for shower in "ab":
        r = values[shower]
        s = block["series"][shower]
        n = r.size
        t = gaussian.t_quantile_975(n - 1)
        marks = s["markers"]
        # A capped whisker on the mean: its Student-t interval; the band is the sample's sigma.
        assert marks["ci95_lo"] == pytest.approx(r.mean() - t * r.std(ddof=1) / math.sqrt(n), rel=1e-5)
        assert marks["dispersion_hi"] == pytest.approx(r.mean() + r.std(ddof=1), rel=1e-5)
        est = s["estimates"]
        summary = metrics.residual_summary(r)
        assert est["bias"]["value"] == sig(summary.bias.value)
        assert est["bias"]["interval"]["lo"] == sig(summary.bias.interval.lo)
        assert est["bias"]["interval"]["method"] == "t"
        assert est["sigma"]["value"] == sig(r.std(ddof=1)) and est["sigma"]["interval"]["method"] == "chi2"
        assert est["rmse"]["value"] == sig(math.sqrt(np.mean(r ** 2)))
        assert est["bias"]["n"] == est["sigma"]["n"] == est["rmse"]["n"] == n


def test_low_n_estimates_report_with_their_own_uncertainty():
    sel = selection(a=(3, 0.1), b=(1, 0.1))
    block = pd.residual_block(sel)
    a, b = block["series"]["a"]["estimates"], block["series"]["b"]["estimates"]
    assert a["sigma"]["interval"] is not None and a["sigma"]["n"] == 3
    assert a["sigma"]["interval"]["lo"] < a["sigma"]["value"] < a["sigma"]["interval"]["hi"]
    assert "c4" in a["sigma"]["note"]
    assert b["bias"]["value"] is not None and b["bias"]["interval"] is None
    assert b["sigma"]["value"] is None and "N = 1" in b["sigma"]["note"]
    empty = pd.residual_block(selection(a=(0, 0.1), b=(0, 0.1)))
    assert empty["series"]["a"]["estimates"]["bias"]["value"] is None
    assert empty["axis"]["provisional"] is True


# ------------------------------------------------------------- the whole --


def assembled(**kwargs):
    sel = selection(**kwargs)
    return sel, pd.assemble(sel, pd.residual_block(sel), 64)


def test_the_payload_names_its_network_axes_and_identity_line():
    sel, payload = assembled(model="angle", lo=50.0, hi=650.0, a=(40, 4.0), b=(40, 4.0))
    assert payload["network"] == {"model": "angle", "frame": "absolute"}
    for key in ("truth", "pred"):
        axis = payload["axes"][key]
        assert (axis["lo"], axis["hi"], axis["n"], axis["unit"]) == (50.0, 650.0, 64, "mrad")
        assert axis["zero_based"] is False
    assert payload["identity"]["from"] == 50.0 and payload["identity"]["to"] == 650.0
    assert payload["residual"]["unit"] == "mrad"
    assert payload["thresholds"] == {"moment": 2, "curve": 8, "histogram": 15, "core": 15,
                                     "robust": 20, "density2d": 15}
    sel, payload = assembled(model="energy")
    assert payload["axes"]["truth"]["zero_based"] is True and payload["axes"]["truth"]["unit"] == "GeV"
    assert payload["residual"]["unit"] == "fraction"
    assert set(payload["density"]) == {"a", "b"}


def test_one_colour_scale_serves_both_showers():
    sel, payload = assembled(a=(300, 0.05), b=(300, 0.4))
    peaks = [d["max_count"] for d in payload["density"].values()]
    assert payload["color"]["vmax"] == sig(math.log10(max(peaks)))
    _, few = assembled(a=(4, 0.05), b=(5, 0.05))
    assert few["color"]["vmax"] == 0.0 and all(d["encoding"] == "pairs" for d in few["density"].values())


def test_a_shower_with_every_pair_off_the_axis_does_not_break_the_scale():
    sel = pd.Selection("energy", "lab", 0.0, 20.0, 20,
                       {"a": np.full(20, 5.0), "b": np.full(20, 5.0)},
                       {"a": np.full(20, 50.0), "b": np.full(20, 50.0)})
    payload = pd.assemble(sel, pd.residual_block(sel), 32)
    block = payload["density"]["a"]
    assert block["max_count"] == 0 and block["n_in_range"] == 0 and block["outside"]["total"] == 20
    assert payload["color"]["vmax"] == 0.0
    assert any("outside the shared axis" in n for n in pd.notices(sel, payload))


def test_the_notices_say_what_a_reader_must_know_and_sign_nothing_with_a_hyphen():
    sel, payload = assembled(a=(9, 0.4), b=(0, 0.4))
    text = " ".join(pd.notices(sel, payload))
    assert "Shower A has N = 9" in text and "below the 15" in text
    assert "provisional" in text
    assert "Shower B has no absolute-frame prediction" in text
    empty = pd.Selection("energy", "lab", 0.0, 20.0, 0, {"a": np.empty(0), "b": np.empty(0)},
                         {"a": np.empty(0), "b": np.empty(0)})
    assert pd.notices(empty, pd.assemble(empty, pd.residual_block(empty), 64))[0] == (
        "No events match the current selection.")

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    # A negative bias puts minus signs into the sentences the fit writes.
    negative = pd.Selection("angle", "lab", -100.0, 100.0, 40,
                            {"a": rng.uniform(-50, 50, 40), "b": rng.uniform(-50, 50, 40)},
                            {"a": rng.uniform(-50, 50, 40), "b": rng.uniform(-50, 50, 40)})
    for item in strings(pd.assemble(negative, pd.residual_block(negative), 32)):
        assert not signed_hyphens(item), item


def test_typographic_tree_sets_minus_in_values_but_not_in_keys_or_numbers():
    tree = {"a-1": "N = -3 and x -2.5, 1e-5", "b": ["-4 mrad", {"c": "plain-text"}], "d": -7.5}
    out = pd.typographic_tree(tree)
    assert out["a-1"] == f"N = {MINUS}3 and x {MINUS}2.5, 1e{MINUS}5"
    assert out["b"][0] == f"{MINUS}4 mrad" and out["b"][1]["c"] == "plain-text" and out["d"] == -7.5


def test_the_whole_payload_is_far_under_the_contract_at_every_bin_count():
    sel = selection(a=(20000, 0.08), b=(20000, 0.08))
    residual = pd.residual_block(sel)
    sizes = {b: density.wire_size(pd.assemble(sel, residual, b)) for b in pd.BINS_LADDER}
    assert sizes[64] < 0.5 * density.RESPONSE_LIMIT
    assert sizes[128] > sizes[96] > sizes[64] > sizes[48] > sizes[32] > sizes[24] > sizes[16]
