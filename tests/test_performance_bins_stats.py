"""The momentum-bin statistics on bare arrays: every gate, seed and range of E2.

No database and no server: ``performance_bins.point`` and ``build`` take the
arrays the one event-table read would return, so each rung of the low-N ladder
(N = 0, 1, 2, 5, 6, 7, 14, 15, 19, 20, 200) can be put in a bin by hand and
checked against an oracle written here from NumPy and ``math.comb``.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import contract_check
from calosrv.db import ddl, schemas
from calosrv.db.registry import STATUS_READY, ExperimentRecord
from calosrv.encode.numbers import sig
from calosrv.errors import CapabilityError, ValidationError
from calosrv.query import density, showers
from calosrv.query import performance_bins as pb
from calosrv.stats import clip, gaussian, median, metrics
from calosrv.text import signed_hyphens

LADDER = (0, 1, 2, 5, 6, 7, 14, 15, 19, 20, 200)


def group(model: str, n: int, seed: int, bias: float = 0.04):
    """``(pred, true)`` of one bin: relative errors of a few percent, or milliradians."""
    rng = np.random.default_rng(seed)
    if model == "energy":
        true = rng.uniform(1.0, 20.0, n)
        return true * (1.0 + rng.normal(bias, 0.12, n)), true
    true = rng.uniform(0.05, 0.63, n)
    return true + rng.normal(bias / 20, 0.012, n), true


def order_interval(sample: np.ndarray):
    """The distribution-free median interval, from the exact binomial sum (``math.comb``)."""
    x = np.sort(sample)
    n = x.size
    cdf = [sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n for k in range(n + 1)]
    j = max(k for k in range(n) if cdf[k] <= 0.025) + 1
    return x[j - 1], x[n - j], 1.0 - 2.0 * cdf[j - 1]


# ------------------------------------------------------------ one point --


@pytest.mark.parametrize("model", pb.MODELS)
@pytest.mark.parametrize("n", [1, 2, 3, 7, 15, 20, 57])
def test_a_point_equals_numpy(model, n):
    pred, true = group(model, n, seed=n)
    p = pb.point(model, pred, true, n_missing=3, seed=(42, 0, 0, 5))
    r = (pred - true) * (1000.0 if model == "angle" else 1.0)
    assert (p.n, p.n_missing) == (n, 3)
    assert p.rmse.value == pytest.approx(np.sqrt(np.mean(r ** 2)))
    assert p.mae.value == pytest.approx(np.mean(np.abs(r)))
    assert p.bias.value == pytest.approx(np.mean(r))
    assert p.median_rel.value == pytest.approx(np.median(np.abs(pred - true) / true))
    if n < 2:
        assert p.rmse.interval is None and p.mae.interval is None and p.bias.interval is None
        return
    t = gaussian.t_quantile_975(n - 1)
    sq, ab = r ** 2, np.abs(r)
    half = t * sq.std(ddof=1) / math.sqrt(n)
    assert p.rmse.interval.lo == pytest.approx(math.sqrt(max(0.0, sq.mean() - half)))
    assert p.rmse.interval.hi == pytest.approx(math.sqrt(sq.mean() + half))
    half = t * ab.std(ddof=1) / math.sqrt(n)
    assert p.mae.interval.lo == pytest.approx(max(0.0, ab.mean() - half))
    assert p.mae.interval.hi == pytest.approx(ab.mean() + half)
    assert p.mae.se == pytest.approx(ab.std(ddof=1) / math.sqrt(n))
    half = t * r.std(ddof=1) / math.sqrt(n)
    assert p.bias.interval.lo == pytest.approx(r.mean() - half)
    assert p.bias.interval.hi == pytest.approx(r.mean() + half)


def test_the_mae_whisker_is_clipped_at_zero_and_says_so():
    pred = np.array([1.0, 1.001, 1.0, 40.0])
    true = np.ones(4)
    p = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 0))
    assert p.mae.interval.lo == 0.0
    assert "clipped" in p.mae.interval.label


@pytest.mark.parametrize("n", LADDER)
def test_each_mark_appears_at_its_own_floor(n):
    pred, true = group("energy", n, seed=100 + n)
    p = pb.point("energy", pred, true, 0, seed=(42, 1, 0, 3))
    rel = np.abs(pred - true) / true
    assert p.drives_scale is (n >= 15)
    assert (p.rmse.interval is not None) is (n >= 2)
    est = p.median_rel
    assert (est.value is not None) is (n >= 1)
    if n < 6:
        assert est.interval is None and est.order is None and est.bootstrap is None
        assert ("no 95% interval" in est.note) is (n >= 1)
    elif n < 20:
        assert est.bootstrap is None and est.interval is est.order
        lo, hi, coverage = order_interval(rel)
        assert (est.order.lo, est.order.hi) == (lo, hi)
        assert est.order_coverage == pytest.approx(coverage)
    else:
        assert est.interval is est.bootstrap
        lo, hi, coverage = order_interval(rel)
        assert (est.order.lo, est.order.hi) == (lo, hi)
        assert est.order_coverage == pytest.approx(coverage)
        assert est.bootstrap.method == metrics.METHOD_BOOTSTRAP
        assert est.bootstrap.lo <= est.value <= est.bootstrap.hi


def test_the_thresholds_the_payload_ships_are_the_helpers_own():
    assert pb.THRESHOLDS == {"interval": 2, "order_statistic": 6, "scale": 15, "bootstrap": 20}


def test_every_group_seeds_its_own_bootstrap():
    pred, true = group("energy", 40, seed=7)
    rel = np.abs(pred - true) / true
    a = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 3)).median_rel
    again = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 3)).median_rel
    other_frame = pb.point("energy", pred, true, 0, seed=(42, 1, 0, 3)).median_rel
    other_bin = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 4)).median_rel
    assert (a.bootstrap.lo, a.bootstrap.hi) == (again.bootstrap.lo, again.bootstrap.hi)
    assert a.value == other_frame.value == other_bin.value
    assert (a.bootstrap.lo, a.bootstrap.hi) != (other_frame.bootstrap.lo, other_frame.bootstrap.hi)
    assert (a.bootstrap.lo, a.bootstrap.hi) != (other_bin.bootstrap.lo, other_bin.bootstrap.hi)
    # The documented rule: SeedSequence([42, frame, shower, bin, quantity]) with median_rel = 2.
    assert pb.QUANTITY_INDEX["median_rel"] == 2
    direct = median.bootstrap_median_interval(rel, seed=[42, 0, 0, 3, 2])
    assert (a.bootstrap.lo, a.bootstrap.hi) == (direct.lo, direct.hi)


def test_a_relative_error_needs_a_positive_truth_and_the_rest_are_counted():
    true = np.array([0.0, 2.0, 4.0])
    pred = np.array([1.0, 3.0, 5.0])
    p = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 0))
    assert p.n == 3 and p.n_nonpositive_true == 1
    assert p.median_rel.n == 2 and p.median_rel.value == pytest.approx(0.375)
    assert p.rmse.value == pytest.approx(1.0)


def test_an_angle_point_carries_the_small_theta_disclosure_in_mrad():
    true = np.array([0.03, 0.05, 0.09, 0.2, 0.5])
    pred = true + 0.001
    p = pb.point("angle", pred, true, 0, seed=(42, 0, 0, 1))
    assert p.n_small_theta == 3 and p.theta_min == pytest.approx(0.03)
    assert p.rmse.value == pytest.approx(1.0) and p.bias.value == pytest.approx(1.0)
    assert p.median_abs.value == pytest.approx(1.0)
    assert p.median_rel.value == pytest.approx(np.median(0.001 / true))
    assert pb.point("energy", pred, true, 0, seed=(42, 0, 0, 1)).median_abs is None


def test_an_empty_bin_is_empty_not_zero():
    p = pb.point("angle", np.empty(0), np.empty(0), n_missing=4, seed=(42, 0, 0, 0))
    assert (p.n, p.n_missing) == (0, 4)
    for q in ("rmse", "mae", "bias", "median_rel", "median_abs"):
        assert p.triple(q) == (None, None, None)
    assert p.theta_min is None and p.n_small_theta == 0


# ------------------------------------------------------------- bin axis --


def test_bins_are_labelled_by_the_producers_integer_when_the_momenta_agree():
    axis = pb.axis_from_ranges({2: (2.03, 2.97), 4: (4.01, 4.99)})
    assert axis.numbers == (2, 3, 4)
    assert axis.labels == ("2–3 GeV", "3–4 GeV", "4–5 GeV")
    assert axis.p_lo == (2.0, 3.0, 4.0) and axis.p_hi == (3.0, 4.0, 5.0)
    assert axis.notices == ()


def test_a_bin_that_disagrees_with_its_momenta_is_relabelled_with_the_range_found():
    axis = pb.axis_from_ranges({2: (2.03, 2.97), 3: (1.5, 3.99)})
    assert axis.labels[0] == "2–3 GeV"
    assert axis.labels[1] == "bin 3 (p 1.5–3.99 GeV)"
    assert (axis.p_lo[1], axis.p_hi[1]) == (1.5, 3.99)
    assert "bin 3" in axis.notices[0] and "disagrees" in axis.notices[0]


def test_more_bins_than_the_chart_draws_is_refused_on_slice_by():
    with pytest.raises(ValidationError) as caught:
        pb.axis_from_ranges({0: (0.1, 0.9), 40: (40.1, 40.9)})
    assert caught.value.extra["field"] == "slice_by"
    assert pb.axis_from_ranges({}).numbers == ()


# ---------------------------------------------------------------- build --


def columns(bin_a, true_a, pred_a, bin_b, true_b, pred_b, frames=("lab",)):
    out = {"bin_a": np.asarray(bin_a, float), "true_a": np.asarray(true_a, float),
           "bin_b": np.asarray(bin_b, float), "true_b": np.asarray(true_b, float)}
    for coord in frames:
        out[f"pred_a_{coord}"] = np.asarray(pred_a, float)
        out[f"pred_b_{coord}"] = np.asarray(pred_b, float)
    return out


NAN = float("nan")


def test_each_shower_is_placed_by_its_own_bin_and_a_missing_prediction_is_counted():
    cols = columns(
        bin_a=[0, 0, 0, 1, 1, NAN], true_a=[1, 2, 3, 4, 5, 6], pred_a=[1.1, NAN, 3.3, 4.4, NAN, 6.6],
        bin_b=[1, 1, 0, 0, 0, 1], true_b=[2, 3, 4, 5, 6, 7], pred_b=[2.2, 3.3, 4.4, 5.5, 6.6, 7.7],
    )
    axis = pb.axis_from_ranges({0: (0.1, 0.9), 1: (1.1, 1.9)})
    report = pb.build(cols, axis, "energy", ("lab",))
    a, b = report.series
    assert (a.key, b.key) == ("absolute:a", "absolute:b")
    # A: bin 0 holds events 0, 1, 2 (event 1 has no prediction); bin 1 holds 3, 4 (4 has none).
    assert [p.n for p in a.points] == [2, 1] and [p.n_missing for p in a.points] == [1, 1]
    # B follows e2_bin: bin 0 holds events 2, 3, 4 and bin 1 holds 0, 1, 5.
    assert [p.n for p in b.points] == [3, 3] and [p.n_missing for p in b.points] == [0, 0]
    assert a.points[0].rmse.value == pytest.approx(math.sqrt(np.mean([0.1 ** 2, 0.3 ** 2])))
    assert report.unbinned == {"a": 1, "b": 0} and report.n_events == 6
    # No zero was filled: a mean of the two real residuals, not of three with a zero.
    assert a.points[0].bias.value == pytest.approx(0.2)


def test_a_frame_missing_every_prediction_is_named():
    cols = columns(bin_a=[0, 0], true_a=[1, 2], pred_a=[NAN, NAN], bin_b=[0, 0], true_b=[1, 2],
                   pred_b=[1.0, 2.0])
    report = pb.build(cols, pb.axis_from_ranges({0: (0.1, 0.9)}), "energy", ("lab",))
    assert any("Shower A" in w and "absolute-frame" in w for w in report.warnings())
    assert not any("Shower B" in w for w in report.warnings())


def random_report(model="energy", counts=(0, 1, 2, 7, 14, 15, 20, 60), frames=pb.ddl.COORD_SYSTEMS):
    """A report over len(counts) bins with each bin's population by hand, all three frames."""
    rng = np.random.default_rng(11)
    bins, true, preds = [], [], {c: [] for c in frames}
    for k, n in enumerate(counts):
        t = rng.uniform(1.0, 20.0, n) if model == "energy" else rng.uniform(0.05, 0.63, n)
        bins += [k] * n
        true += list(t)
        for c in frames:
            noise = rng.normal(0.0, 0.1, n)
            preds[c] += list(t * (1 + noise) if model == "energy" else t + noise / 10)
    cols = {"bin_a": np.array(bins, float), "true_a": np.array(true),
            "bin_b": np.array(bins, float)[::-1], "true_b": np.array(true)[::-1]}
    for c in frames:
        cols[f"pred_a_{c}"] = np.array(preds[c])
        cols[f"pred_b_{c}"] = np.array(preds[c])[::-1]
    axis = pb.axis_from_ranges({k: (k + 0.1, k + 0.9) for k in range(len(counts))})
    return pb.build(cols, axis, model, frames)


@pytest.mark.parametrize("model", pb.MODELS)
def test_the_block_satisfies_its_contract_and_its_arrays_align(model):
    report = random_report(model)
    block = report.as_dict()
    contract_check.check(json.loads(json.dumps(block)), "performance_momentum", at="by_momentum_bin")
    n_bins = len(block["bins"]["index"])
    assert n_bins == 8
    for series in block["series"]:
        for key, value in series.items():
            if isinstance(value, list):
                assert len(value) == n_bins, key
    assert [s["key"] for s in block["series"]] == [
        "absolute:a", "absolute:b", "trans:a", "trans:b", "local:a", "local:b"]
    assert block["frames"] == ["absolute", "trans", "local"]
    assert set(block["quantities"]) == ({"rmse", "mae", "median_rel", "bias"}
                                        | ({"median_abs"} if model == "angle" else set()))
    assert set(block["y_max"]) == set(block["quantities"])
    assert ("theta_min" in block["series"][0]) is (model == "angle")


def test_the_block_drops_its_cross_check_arrays_and_digits_on_request():
    report = random_report("energy")
    full = report.as_dict()
    lean = report.as_dict(digits=4, keep_order=False)
    for key in ("median_rel_order_lo", "median_rel_order_hi", "median_rel_order_coverage"):
        assert key in full["series"][0] and key not in lean["series"][0]
    contract_check.check(json.loads(json.dumps(lean)), "performance_momentum", at="by_momentum_bin")
    for value in lean["series"][0]["rmse"]:
        assert value is None or value == sig(value, 4)
    assert density.wire_size(lean) < density.wire_size(full)
    # The whiskers themselves are unchanged apart from the rounding.
    for a, b in zip(full["series"][0]["median_rel_hi"], lean["series"][0]["median_rel_hi"]):
        assert (a is None and b is None) or b == pytest.approx(a, rel=1e-3)


def test_no_sentence_of_the_block_signs_a_number_with_a_hyphen():
    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    for model in pb.MODELS:
        for text in strings(random_report(model).as_dict()):
            assert not signed_hyphens(text), text
    # A relabelled bin states a range; the notice must not hyphenate it either.
    notices = pb.axis_from_ranges({0: (-0.4, 0.9)}).notices
    assert not any(signed_hyphens(n) for n in notices)


def test_the_largest_block_stays_far_under_the_contract():
    """Twenty-four bins, three frames, two showers, angle (the larger series), every bin bootstrapped."""
    counts = (60,) * pb.momentum.MAX_CLASSES
    block = random_report("angle", counts).as_dict()
    size = density.wire_size({"by_momentum_bin": block})
    assert len(block["series"]) == 6 and len(block["bins"]["index"]) == 24
    assert size < 0.6 * density.RESPONSE_LIMIT, size


# --------------------------------------------------------------- y axes --


def series_of(*points, shower="a"):
    return pb.Series("energy", "lab", shower, list(points))


AXIS_2 = pb.axis_from_ranges({0: (0.1, 0.9), 1: (1.1, 1.9), 2: (2.1, 2.9)})


def test_the_range_comes_from_the_driving_points_and_a_weak_point_overflows_it():
    strong_pred, strong_true = group("energy", 40, seed=1)
    weak_true = np.array([3.0, 4.0, 5.0])
    strong = pb.point("energy", strong_pred, strong_true, 0, seed=(42, 0, 0, 0))
    weak = pb.point("energy", weak_true * 6.0, weak_true, 0, seed=(42, 0, 0, 1))
    y = pb.y_axis([series_of(strong, weak)], AXIS_2, "rmse")
    assert not y["provisional"] and y["min"] == 0.0 and not y["signed"]
    assert y["value"] == clip.nice_range(0.0, strong.rmse.interval.hi, fine=True)[1]
    assert y["value"] >= strong.rmse.interval.hi
    assert y["n_overflow"] == 1 and len(y["overflow"]) == 1
    over = y["overflow"][0]
    assert over["series"] == "absolute:a" and over["bin"] == 1 and over["n"] == 3
    # The clipped point's true value and upper end travel with it.
    assert over["value"] == sig(weak.rmse.value) and over["hi"] == sig(weak.rmse.interval.hi)
    assert over["value"] > y["value"]
    assert "under-powered" in y["note"]


def test_a_weak_point_inside_the_range_is_not_listed():
    strong_pred, strong_true = group("energy", 40, seed=1)
    strong = pb.point("energy", strong_pred, strong_true, 0, seed=(42, 0, 0, 0))
    inside = pb.point("energy", np.array([3.0, 4.0, 5.0]) * 1.01, np.array([3.0, 4.0, 5.0]), 0,
                      seed=(42, 0, 0, 1))
    y = pb.y_axis([series_of(strong, inside)], AXIS_2, "rmse")
    assert y["overflow"] == [] and y["n_overflow"] == 0 and "note" not in y


def test_with_no_driving_point_the_range_is_provisional_and_cannot_overflow():
    pred, true = group("energy", 14, seed=3)
    one = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 0))
    two = pb.point("energy", np.array([3.0]), np.array([1.0]), 0, seed=(42, 0, 0, 1))
    y = pb.y_axis([series_of(one, two)], AXIS_2, "rmse")
    assert y["provisional"] is True and y["overflow"] == [] and y["n_overflow"] == 0
    assert "Provisional" in y["note"]
    # Taken from the weak points: the larger reach, the single point's value (no interval).
    reach = max(one.rmse.interval.hi, two.rmse.value)
    assert y["value"] == clip.nice_range(0.0, reach, fine=True)[1]


def test_a_signed_quantity_gets_a_range_symmetric_about_zero():
    pred, true = group("energy", 40, seed=5, bias=-0.3)
    p = pb.point("energy", pred, true, 0, seed=(42, 0, 0, 0))
    y = pb.y_axis([series_of(p)], AXIS_2, "bias")
    reach = max(abs(p.bias.interval.lo), abs(p.bias.interval.hi))
    assert y["signed"] and y["min"] == -y["value"] and y["value"] >= reach
    assert p.bias.value < 0


def test_an_empty_selection_has_no_range_to_offer():
    empty = pb.point("energy", np.empty(0), np.empty(0), 0, seed=(42, 0, 0, 0))
    y = pb.y_axis([series_of(empty)], AXIS_2, "rmse")
    assert y["value"] is None and y["min"] is None and y["provisional"] is True
    assert pb.y_axis([], AXIS_2, "rmse")["value"] is None


def test_the_overflow_list_is_capped_and_its_count_is_not(monkeypatch):
    monkeypatch.setattr(pb, "MAX_OVERFLOW_LISTED", 3)
    strong_pred, strong_true = group("energy", 40, seed=1)
    strong = pb.point("energy", strong_pred, strong_true, 0, seed=(42, 0, 0, 0))
    weak_true = np.array([3.0, 4.0, 5.0])
    weak = [pb.point("energy", weak_true * (6.0 + i), weak_true, 0, seed=(42, 0, 0, i + 1))
            for i in range(8)]
    axis = pb.axis_from_ranges({k: (k + 0.1, k + 0.9) for k in range(len(weak) + 1)})
    y = pb.y_axis([series_of(strong, *weak)], axis, "rmse")
    assert y["n_overflow"] == 8 and len(y["overflow"]) == 3
    # Largest first, so the cap keeps the most extreme.
    tops = [o["hi"] for o in y["overflow"]]
    assert tops == sorted(tops, reverse=True)
    assert y["overflow"][0]["bin"] == 8


# --------------------------------------------------------------- columns --


TWO_SHOWER = ExperimentRecord(
    table_name="t", status=STATUS_READY, schema_name=schemas.HITS_ALL_MODELS.name,
    schema_version=schemas.HITS_ALL_MODELS.version,
    derived_version=schemas.DERIVED_VERSION[ddl.KIND_TWO_SHOWER],
)


def test_every_column_the_reads_name_is_in_the_event_tables_vocabulary():
    names = {name for name, _ in ddl.EVENT_COLUMNS_V2}
    for model in pb.MODELS:
        for coord in ddl.COORD_SYSTEMS:
            for shower in ("a", "b"):
                truth, pred = pb.network_columns(model, coord, shower)
                assert truth in names and pred in names, (model, coord, shower)
    for sh in showers.of(TWO_SHOWER, "both"):
        assert sh.momentum in names and sh.momentum_bin in names
    assert pb.network_columns("energy", "trans", "b") == ("en_true_b", "en_pred_b_trn")
    assert pb.network_columns("angle", "local", "a") == ("th_true_a", "th_pred_a_loc")
    with pytest.raises(KeyError):
        pb.network_columns("segmentation", "lab", "a")
    with pytest.raises(ValueError):
        pb.network_columns("energy", "polar", "a")


def test_the_networks_an_experiment_offers_are_its_frames_not_its_hit_frames():
    assert pb.frames_offered(TWO_SHOWER) == tuple(ddl.COORD_SYSTEMS)
    one = ExperimentRecord(
        table_name="s", status=STATUS_READY, schema_name=schemas.STANDALONE_HITS.name,
        schema_version=schemas.STANDALONE_HITS.version,
        derived_version=schemas.DERIVED_VERSION[ddl.KIND_SINGLE_HITS])
    assert pb.frames_offered(one) == ()
    with pytest.raises(CapabilityError) as caught:
        pb.require_networks(one)
    extra = caught.value.extra
    assert (extra["field"], extra["capability"], extra["kind"]) == (
        "model", "networks", ddl.KIND_SINGLE_HITS)
    assert pb.require_networks(TWO_SHOWER).models == tuple(ddl.MODELS)
