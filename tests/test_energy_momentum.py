"""B3, the energy panel sliced by incident momentum, at the query level.

The fetch is exercised on the two-event demonstration database (its four
showers sit at 2.71, 12.5, 17.9 and 6.39 GeV - in no notebook window, so it
also exercises the outside index), and on an in-memory copy of it in which one
shower left no hits. The panel itself is a pure function of a
:class:`~calosrv.query.energy.MomentumSample`, so the per-slice axes, the
low-N gates and the budget guard are tested on samples built here, where every
population is chosen - production-scale ones included, which is where the
two-shower series limit of ``routes_energy`` is measured.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pytest

from calosrv.api import routes_energy
from calosrv.db import ddl, naming
from calosrv.errors import ValidationError
from calosrv.models.common import ApiMeta, envelope
from calosrv.query import density, energy, filters, showers
from calosrv.stats import gaussian, histogram
from calosrv.stats import momentum as momentum_mod
from calosrv.text import signed_hyphens

D_KEYS = ["slices", "slice_counts", "series", "calibration", "axis", "benchmarks",
          "n_events", "scale", "thresholds"]
MOMENTUM_KEYS = ["slice_by", "slicing", "slice_axes", "slice_counts_by_shower",
                 "outside_slices", "counted", "series_set", "no_deposit",
                 "segmentation_frame", "momentum_marker", "texts"]


def _stored(cursor, record):
    """Each demo shower's stored momentum (as DOUBLE), bin and truth deposit, by event."""
    table = naming.quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"SELECT event_number, CAST(e1 AS DOUBLE), CAST(e2 AS DOUBLE), e1_bin, e2_bin, "
        f"e_a_true_abs, e_b_true_abs FROM {table} ORDER BY event_number"
    ).fetchall()
    return {row[0]: {"a": (row[1], row[3], row[5]), "b": (row[2], row[4], row[6])}
            for row in rows}


# ------------------------------------------------------ the demo database --


def test_the_d_payload_carries_no_momentum_key(cursor, record):
    result = energy.compute(cursor, record, filters.build(record))
    assert list(result.as_dict()) == D_KEYS
    assert result.momentum is None


def test_notebook_windows_leave_every_demo_shower_outside(cursor, record):
    """Showers in no window are counted, drawn nowhere and still calibrate."""
    spec = filters.build(record)
    result = energy.compute_by_momentum(cursor, record, spec)
    payload = result.as_dict()
    assert list(payload) == D_KEYS + MOMENTUM_KEYS

    assert [s["label"] for s in payload["slices"]] == [
        f"{c:g} ± 0.5 GeV" for c in momentum_mod.CALIBRATION_CENTRES_GEV]
    assert payload["outside_slices"] == {"a": 2, "b": 2}
    assert payload["no_deposit"] == {"a": 0, "b": 0}
    assert payload["series"] == [] and payload["slice_axes"] == []
    assert set(payload["slice_counts"].values()) == {0}
    assert payload["counted"] == "showers" and payload["benchmarks"] == []
    # The truth split names its frame although no network made it.
    assert payload["segmentation_frame"] == "absolute"
    assert payload["momentum_marker"] == energy.MOMENTUM_MARKER
    trans = energy.compute_by_momentum(cursor, record, spec, coord_system="trans")
    assert trans.as_dict()["segmentation_frame"] == "trans"

    # The calibration is the D panel's: every shower of the selection, in a
    # slice or not.
    d = energy.compute(cursor, record, spec).calibration
    for key in ("c_a", "c_b"):
        assert payload["calibration"][key] == pytest.approx(d[key], rel=1e-12)
    assert payload["calibration"]["applied"] is True


def test_windows_are_half_open_in_double_precision(cursor, record):
    """A momentum on a window's upper edge belongs to the next window up."""
    stored = _stored(cursor, record)
    p = stored[0]["a"][0]
    # [p - 1, p) and [p, p + 1): exact, because p is a float32 value.
    below, above = p - 0.5, p + 0.5
    assert (above - 0.5, below + 0.5) == (p, p)
    result = energy.compute_by_momentum(
        cursor, record, filters.build(record), f"{below!r},{above!r}")
    payload = result.as_dict()
    lower, upper = payload["slices"]
    assert lower["hi"] == p and upper["lo"] == p
    assert payload["slice_counts_by_shower"]["a"] == {"0": 0, "1": 1}
    # The NumPy twin of the SQL CASE agrees, edge included.
    classes = result.slices
    assert momentum_mod.assign(np.array([p]), classes).tolist() == [1]


def test_each_shower_is_sliced_by_its_own_momentum(cursor, record):
    stored = _stored(cursor, record)
    centres = "2.7,6.4,12.5,17.9"
    result = energy.compute_by_momentum(
        cursor, record, filters.build(record), centres, series="truth")
    payload = result.as_dict()
    classes = result.slices
    expected = {"a": {}, "b": {}}
    for showers_of_event in stored.values():
        for key, (p, _, _) in showers_of_event.items():
            index = int(momentum_mod.assign(np.array([p]), classes)[0])
            expected[key][str(index)] = expected[key].get(str(index), 0) + 1
    for key in ("a", "b"):
        found = {k: v for k, v in payload["slice_counts_by_shower"][key].items() if v}
        assert found == expected[key]
    # One shower per window, so one series per window, of that shower only.
    assert sorted((s.slice_index, s.shower) for s in result.series) == sorted(
        (int(k), key) for key in ("a", "b") for k in expected[key])
    # Its value is that shower's truth deposit on the momentum scale.
    c = payload["calibration"]
    for series in result.series:
        event = next(e for e, sh in stored.items()
                     if str(int(momentum_mod.assign(np.array([sh[series.shower][0]]),
                                                    classes)[0])) == str(series.slice_index))
        deposit = stored[event][series.shower][2]
        assert series.fit.mu == pytest.approx(deposit * c[f"c_{series.shower}"], rel=1e-5)
    # Showers are counted, not events: two events fill four slices.
    assert sum(payload["slice_counts"].values()) == 4
    assert payload["n_events"] == 2


def test_bins_slice_on_the_producers_bin_column(cursor, record):
    stored = _stored(cursor, record)
    result = energy.compute_by_momentum(cursor, record, filters.build(record), "bins")
    payload = result.as_dict()
    bins_held = sorted(b for ev in stored.values() for (_, b, _) in ev.values())
    assert [s["lo"] for s in payload["slices"]] == [float(k) for k in
                                                    range(bins_held[0], bins_held[-1] + 1)]
    assert payload["slicing"] == {
        "mode": "bins", "half_width": None, "role": "bin column",
        "centres": [k + 0.5 for k in range(bins_held[0], bins_held[-1] + 1)]}
    for key in ("a", "b"):
        held = {stored[e][key][1] for e in stored}
        counts = payload["slice_counts_by_shower"][key]
        for cls in result.slices:
            assert counts[str(cls.index)] == (1 if int(cls.lo) in held else 0)
    assert payload["outside_slices"] == {"a": 0, "b": 0}


@pytest.mark.parametrize("choice,keys", [
    (None, ["e_a_true", "e_b_true"]),
    ("truth", ["e_a_true", "e_b_true"]),
    ("model", ["e_a_pred", "e_b_pred"]),
    ("all", ["e_a_pred", "e_b_pred", "e_a_true", "e_b_true"]),
])
def test_series_sets_keep_the_d_panels_order(record, choice, keys):
    chosen, series = energy.momentum_series(record, choice, "trans")
    assert chosen == (choice or "truth")
    assert [m.key for m in series] == keys
    assert all(m.column == f"{m.key}_trn" for m in series)


@pytest.mark.parametrize("raw,field", [
    ("1,1.5", "p_slices"),        # overlapping windows
    ("ten", "p_slices"),
    ("-1", "p_slices"),
    (",".join(str(3 * i + 1) for i in range(25)), "p_slices"),   # too many
    ("1e308", "p_slices"),        # beyond MAX_CENTRE_GEV
])
def test_bad_slicings_are_refused_naming_the_field(cursor, record, raw, field):
    with pytest.raises(ValidationError) as caught:
        energy.compute_by_momentum(cursor, record, filters.build(record), raw)
    assert caught.value.extra["field"] == field


@pytest.mark.parametrize("half", [1e308, momentum_mod.MAX_HALF_WIDTH_GEV * 1.01, math.inf])
def test_no_window_edge_can_overflow_into_the_sql(cursor, record, half):
    """``c + h`` stays a finite literal: an over-wide window is a 422, not a Binder error."""
    with pytest.raises(ValidationError) as caught:
        energy.compute_by_momentum(cursor, record, filters.build(record), "5", half_width=half)
    assert caught.value.extra["field"] == "p_slices"
    widest = momentum_mod.windows([momentum_mod.MAX_CENTRE_GEV], momentum_mod.MAX_HALF_WIDTH_GEV)
    assert math.isfinite(widest[0].hi)


def test_window_labels_set_a_signed_exponent_with_the_minus_sign():
    (tiny,) = momentum_mod.parse_slicing("5", 1e-5).classes
    assert tiny.label == "5 ± 1e−05 GeV" and not signed_hyphens(tiny.label)
    odd, _ = momentum_mod.relabel_bins(momentum_mod.unit_bins(0, 0), {0: (1e-5, 2.0)})
    assert odd[0].label == "bin 0 (p 1e−05–2 GeV)"


def test_an_unknown_series_set_is_refused(cursor, record):
    with pytest.raises(ValidationError) as caught:
        energy.compute_by_momentum(cursor, record, filters.build(record), series="both")
    assert caught.value.extra["field"] == "series"


def test_an_empty_selection_slices_into_nothing(cursor, record):
    spec = filters.build(record, e1_min=100.0, e1_max=200.0)
    for p_slices in (None, "bins"):
        payload = energy.compute_by_momentum(cursor, record, spec, p_slices).as_dict()
        assert payload["n_events"] == 0
        assert payload["series"] == [] and payload["slice_axes"] == []
        assert payload["calibration"]["applied"] is False
    assert payload["slices"] == []        # bins: an empty selection holds none


# ------------------------------------------------------ constructed samples --


def _sample(record, populations, centres=(1.0, 2.0, 5.0, 10.0), n_outside=11,
            seed=7, thin_b=None) -> energy.MomentumSample:
    """Showers drawn inside chosen windows, plus some outside every window.

    One shower (A, a deposit series) unless ``thin_b`` puts a second shower's
    truth series into the first window with that many showers.
    """
    rng = np.random.default_rng(seed)
    slicing = momentum_mod.parse_slicing(",".join(repr(float(c)) for c in centres))
    p = np.concatenate([rng.uniform(c.lo, c.hi, size=n)
                        for c, n in zip(slicing.classes, populations)]
                       + [rng.uniform(30.0, 40.0, size=n_outside)])
    deposit = 0.03 * p * rng.normal(1.0, 0.1, size=p.size)
    a, b = showers.of(record, "both")
    index = momentum_mod.assign(p, slicing.classes).astype(np.int64)
    if thin_b is None:
        series = (energy.MomentumSeries(energy.DEPOSIT_KEY, energy.DEPOSIT_LABEL, "a",
                                        "deposit", "e_dep"),)
        return energy.MomentumSample(
            showers=(a,), series_set=energy.DEPOSIT_SET, series=series, slicing=slicing,
            n_events=p.size, slice_index={"a": index}, momentum={"a": p},
            present={"a": np.ones(p.size, bool)}, deposit={"a": deposit},
            values={"e_dep": deposit})
    # Shower B: ``thin_b`` showers in the first window, one far above the rest.
    p_b = np.full(p.size, 35.0)
    p_b[:thin_b] = slicing.classes[0].lo + 0.1
    dep_b = 0.03 * p_b
    dep_b[0] *= 40.0
    index_b = momentum_mod.assign(p_b, slicing.classes).astype(np.int64)
    series = tuple(energy.MomentumSeries(key, label, shower, "true", f"{key}_abs")
                   for key, label, shower, kind in energy.SERIES if kind == "true")
    return energy.MomentumSample(
        showers=(a, b), series_set=energy.SERIES_TRUTH, series=series, slicing=slicing,
        n_events=p.size, slice_index={"a": index, "b": index_b},
        momentum={"a": p, "b": p_b},
        present={"a": np.ones(p.size, bool), "b": np.ones(p.size, bool)},
        deposit={"a": deposit, "b": dep_b}, values={"e_a_true": deposit, "e_b_true": dep_b})


def test_per_slice_axes_share_the_bin_count(record):
    sample = _sample(record, (200, 30, 5, 0))
    payload = energy.build_by_momentum(sample).as_dict()
    axes = payload["slice_axes"]
    # The empty window has no axis; the others have their own range.
    assert [a["slice"] for a in axes] == [0, 1, 2]
    assert len({(a["lo"], a["hi"]) for a in axes}) == 3
    # The Rice count of the smallest drawn series (30) is shared by all.
    bins = histogram.adaptive_bins(30)
    assert {k: v for k, v in payload["axis"].items() if k != "grid"} == {
        "unit": "GeV (incident-equivalent)", "bins": bins, "per_slice": True,
        "curve_points": histogram.CURVE_POINTS}
    assert "linspace(lo, hi, curve_points)" in payload["axis"]["grid"]
    by_slice = {s["slice"]: s for s in payload["series"]}
    for a in axes:
        # The grids are not shipped: they follow from lo, hi and the axis counts.
        assert "curve_x" not in a and "hist_centres" not in a
        # Floored at zero and rounded outward to clean ticks.
        assert a["lo"] == 0.0 and a["interval"] > 0 and a["lo"] < a["hi"]
        assert a["hi"] / a["interval"] == pytest.approx(round(a["hi"] / a["interval"]))
        assert a["hi"] >= a["clipping"]["hi"]
        series = by_slice[a["slice"]]
        if series["histogram"] is not None:
            assert len(series["histogram"]["counts"]) == bins
        if series["curve"]["y"]:
            # Evaluated on exactly the grid the rule names (to the six significant
            # figures mu_core and sigma_core are shipped at).
            x = np.linspace(a["lo"], a["hi"], histogram.CURVE_POINTS)
            fit = series["fit"]
            # On the histogram's normalisation (decision D-7): the area is the
            # events the Gaussian describes over the events the bars hold.
            area = 1.0
            if series["histogram"] is not None:
                described = (fit["n_core"] / gaussian.CORE_WINDOW_COVERAGE
                             if fit["core_applied"] and fit["n_core"] < fit["n"] else fit["n"])
                area = described / series["histogram"]["n_in_range"]
            amplitude = gaussian.unit_area_amplitude(fit["sigma_core"]) * area
            expected = gaussian.gaussian_curve(x, fit["mu_core"], fit["sigma_core"], amplitude)
            assert series["curve_peak"] == pytest.approx(amplitude, rel=1e-5)
            assert series["curve"]["y"] == pytest.approx(expected, rel=1e-3, abs=1e-9)
    # Only the slices whose series reach the histogram floor set a range.
    assert [a["provisional"] for a in axes] == [False, False, True]
    assert [by_slice[i]["draw"] for i in (0, 1, 2)] == ["histogram", "histogram", "strip"]
    # An explicit bin count is shared the same way.
    explicit = energy.build_by_momentum(sample, bins=20).as_dict()
    assert explicit["axis"]["bins"] == 20
    assert {len(s["histogram"]["counts"]) for s in explicit["series"] if s["histogram"]} == {20}


def test_the_calibration_spans_the_whole_selection(record):
    """Showers outside every window still calibrate; no slice is fitted onto itself."""
    sample = _sample(record, (40, 40, 40, 40), n_outside=25)
    payload = energy.build_by_momentum(sample).as_dict()
    c = sample.momentum["a"].sum() / sample.deposit["a"].sum()
    assert payload["calibration"]["c_a"] == pytest.approx(c, rel=1e-12)
    assert payload["calibration"]["c_b"] is None
    assert payload["outside_slices"] == {"a": 25, "b": None}
    inside = sample.slice_index["a"] != momentum_mod.OUTSIDE
    assert sample.momentum["a"][inside].sum() / sample.deposit["a"][inside].sum() != \
        pytest.approx(c, rel=1e-9)
    assert sum(payload["slice_counts"].values()) + 25 == sample.n_events
    raw = energy.build_by_momentum(sample, calibrated=False).as_dict()
    assert raw["scale"] == "deposited" and raw["axis"]["unit"] == "GeV (deposited)"
    assert raw["calibration"]["applied"] is False
    # Uncalibrated deposits are a few hundredths of a GeV: the tick ladder reaches them.
    assert all(a["interval"] < 0.1 for a in raw["slice_axes"])


def test_each_slice_carries_its_measured_mean_momentum(record):
    sample = _sample(record, (40, 2, 1, 0))
    payload = energy.build_by_momentum(sample).as_dict()
    axes = {a["slice"]: a for a in payload["slice_axes"]}
    for index in (0, 1):
        p = sample.momentum["a"][sample.slice_index["a"] == index]
        marker = axes[index]["momentum"]
        assert marker["b"] is None
        a = marker["a"]
        assert a["n"] == p.size
        assert a["mean"] == pytest.approx(p.mean(), rel=1e-5)
        assert a["sd"] == pytest.approx(p.std(ddof=1), rel=1e-5)
        half = gaussian.t_quantile_975(p.size - 1) * p.std(ddof=1) / math.sqrt(p.size)
        assert a["ci95"] == pytest.approx([p.mean() - half, p.mean() + half], rel=1e-5)
    # Forty showers need no low-N label.
    assert axes[0]["momentum"]["a"]["low_n"] is None
    # Two: one degree of freedom, and the SD quoted with its own uncertainty -
    # its standard error, its asymmetric chi-squared interval and c4(2).
    p = sample.momentum["a"][sample.slice_index["a"] == 1]
    sd = p.std(ddof=1)
    two = axes[1]["momentum"]["a"]["low_n"]
    assert two["label"] == "weak (N = 2)" and two["dof_note"] == "1 d.o.f."
    assert two["sd_se"] == pytest.approx(sd / math.sqrt(2.0), rel=1e-5)
    assert two["sd_ci95"] == pytest.approx(
        [sd * math.sqrt(1 / gaussian.chi2_quantile(1, upper=True)),
         sd * math.sqrt(1 / gaussian.chi2_quantile(1, upper=False))], rel=1e-5)
    assert two["sd_ci95"][1] / sd > 30          # [0.45, 32] x sd at N = 2
    assert two["c4"] == pytest.approx(gaussian.c4(2), rel=1e-5)
    single = axes[2]["momentum"]["a"]
    assert single["n"] == 1 and single["sd"] is None and single["ci95"] is None
    assert single["low_n"] == {"label": "single shower (N = 1)"}
    # Every quantity is named once, the whisker and the band apart.
    names = payload["momentum_marker"]
    assert names["ci95"]["method"] == "t" and "Student-t" in names["ci95"]["label"]
    assert names["sd_ci95"]["method"] == "chi2" and "uncapped" in names["sd"]


#: One slice per rung of the low-N table, single-shower deposits.
RUNGS = (1, 2, 7, 8, 14, 15, 19, 20)


def test_every_low_n_rung_in_momentum_slices(record):
    """N = 1, 2, 7, 8, 14, 15, 19 and 20, each alone in its slice."""
    sample = _sample(record, RUNGS, centres=tuple(range(1, 9)), n_outside=0)
    payload = energy.build_by_momentum(sample).as_dict()
    series = {s["slice"]: s for s in payload["series"]}
    axes = {a["slice"]: a for a in payload["slice_axes"]}
    found = {
        n: (series[i]["draw"], series[i]["fit"]["estimator"], axes[i]["provisional"],
            series[i]["fit"]["shape_testable"], series[i]["drives_scale"])
        for i, n in enumerate(RUNGS)
    }
    assert found == {
        1: ("strip", "mean_only", True, False, False),
        2: ("strip", "moments_1dof", True, False, False),
        7: ("strip", "moments", True, False, False),
        8: ("curve+strip", "moments", True, False, False),
        14: ("curve+strip", "moments", True, False, False),
        15: ("histogram", "core_refit", False, False, True),
        19: ("histogram", "core_refit", False, False, True),
        20: ("histogram", "core_refit", False, True, True),
    }
    # The marker follows the same table: labelled below 20, the SD's own
    # uncertainty quoted below 15, one degree of freedom named at 2.
    for i, n in enumerate(RUNGS):
        low_n = axes[i]["momentum"]["a"]["low_n"]
        if n >= gaussian.MIN_ROBUST_SAMPLES:
            assert low_n is None
            continue
        assert low_n["label"] == ("single shower (N = 1)" if n == 1 else f"weak (N = {n})")
        assert ("dof_note" in low_n) == (n == 2)
        quoted = {"sd_se", "sd_ci95", "c4"} <= set(low_n)
        assert quoted == (2 <= n < gaussian.MIN_CORE_SAMPLES), n
        if quoted:
            assert low_n["sd_ci95"][0] < axes[i]["momentum"]["a"]["sd"] < low_n["sd_ci95"][1]
    # Only the drawn histograms set the shared bin count: the smallest is 15.
    assert payload["axis"]["bins"] == histogram.adaptive_bins(15)
    # The provisional slices are the ones the route names.
    warnings = routes_energy.momentum_warnings(energy.build_by_momentum(sample))
    (provisional,) = [w for w in warnings if "provisional" in w]
    for i, n in enumerate(RUNGS):
        assert (payload["slices"][i]["label"] in provisional) == (n < 15)


def test_a_degenerate_series_never_sets_its_slices_range(record):
    """Twenty identical deposits are drawn as a strip, so they set no range either."""
    sample = _sample(record, (20, 30, 0, 0), n_outside=0)
    first = sample.slice_index["a"] == 0
    # 0.25 sums and divides exactly, so the fit sees a width of exactly zero.
    sample.values["e_dep"][first] = 0.25
    payload = energy.build_by_momentum(sample, calibrated=False).as_dict()
    axis = payload["slice_axes"][0]
    (series,) = [s for s in payload["series"] if s["slice"] == 0]
    assert series["draw"] == "strip" and series["fit"]["degenerate"] is True
    assert axis["provisional"] is True and axis["driven_by"] == ["e_dep"]
    assert payload["slice_axes"][1]["provisional"] is False
    # Identical values whose mean is not exact: whatever the ladder draws, the
    # slice's range follows it.
    sample.values["e_dep"][first] = 0.05
    payload = energy.build_by_momentum(sample).as_dict()
    (series,) = [s for s in payload["series"] if s["slice"] == 0]
    assert payload["slice_axes"][0]["provisional"] == (series["draw"] != "histogram")


def test_the_clip_disclosures_agree_with_the_axis_drawn(record):
    """Sixteen robust showers and four thin ones, one 40 times high, in one slice.

    The range comes from the sixteen - too few for percentiles, so their full
    range from zero - and every sentence and count says so and agrees.
    """
    sample = _sample(record, (16, 40, 0, 0), thin_b=4)
    result = energy.build_by_momentum(sample)
    payload = result.as_dict()
    first, second = payload["slice_axes"][:2]
    clip = first["clipping"]
    assert first["driven_by"] == ["e_a_true"] and first["provisional"] is False
    assert clip["rule"] == "full_range" and clip["n_basis"] == 16
    assert clip["n_total"] == first["n_values"] == 20
    assert clip["n_outside"] == first["n_outside_axis"] == clip["n_below"] + clip["n_above"] >= 1
    assert clip["fraction_outside"] == pytest.approx(clip["n_outside"] / 20)
    assert clip["note"] == (
        "From 0 to the largest of the 16 values that set it, too few for percentiles, "
        f"rounded out to whole ticks; {clip['n_outside']} of 20 values "
        f"{'lies' if clip['n_outside'] == 1 else 'lie'} beyond it.")
    assert "low_percentile" not in clip
    # Forty values: the percentile rule, its headroom and an empty overflow.
    assert second["clipping"]["rule"] == "percentile"
    assert second["clipping"]["note"].startswith(
        "From 0 to the 99th percentile of the 40 values that set it plus 5%, rounded out")
    assert second["clipping"]["n_outside"] == second["n_outside_axis"]
    (sentence,) = [w for w in routes_energy.momentum_warnings(result) if "beyond" in w]
    beyond = sum(a["n_outside_axis"] for a in payload["slice_axes"])
    total = sum(a["n_values"] for a in payload["slice_axes"])
    assert sentence.startswith(
        "Each slice's energy axis runs from 0 to the 99th percentile of the series that set "
        "it plus 5%, or to their largest value where they are too few for percentiles, "
        f"rounded out to whole ticks; {beyond} of {total} values lie beyond their slice's axis")
    assert "1st" not in sentence


def test_a_thin_series_never_sets_its_slices_range(record):
    """A robust series sets the range; the thin one's overflow is counted, not obeyed."""
    sample = _sample(record, (60, 40, 0, 0), thin_b=4)
    payload = energy.build_by_momentum(sample).as_dict()
    first = payload["slice_axes"][0]
    assert first["provisional"] is False
    assert first["driven_by"] == ["e_a_true"]
    assert first["n_values"] == 64
    calibrated = {
        key: sample.values[key] * payload["calibration"][f"c_{key[2]}"]
        for key in ("e_a_true", "e_b_true")
    }
    everything = np.concatenate([calibrated["e_a_true"][sample.slice_index["a"] == 0],
                                 calibrated["e_b_true"][sample.slice_index["b"] == 0]])
    assert everything.size == first["n_values"]
    outside = int(((everything < first["lo"]) | (everything > first["hi"])).sum())
    assert first["n_outside_axis"] == outside >= 1
    thin = [s for s in payload["series"] if s["shower"] == "b"]
    assert [s["draw"] for s in thin] == ["strip"] and thin[0]["drives_scale"] is False
    # The two-shower block names both showers.
    assert first["momentum"]["b"]["n"] == 4
    assert payload["outside_slices"]["b"] == sample.n_events - 4


def test_a_shower_without_hits_is_counted_apart_through_sql(cursor, record):
    """An event whose shower A left no hits, in an in-memory copy of the demo table.

    Fetched through the SQL every request runs: the shower is in no slice and
    not 'outside', it stays out of the calibration, and the sentence says both.
    """
    table = naming.quote(naming.event_table(record.table_name))
    rows = cursor.execute(f"SELECT * FROM {table}").df()
    centres = "2.7,6.4,12.5,17.9"
    spec = filters.build(record)
    con = duckdb.connect(":memory:")
    try:
        con.register("demo", rows)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM demo")
        before = energy.fetch_momentum(con, record, spec, centres)
        (event,) = con.execute(f"SELECT min(event_number) FROM {table}").fetchone()
        emptied = ", ".join(f"{ddl.seg_stat_column(stem, cs)} = 0"
                            for stem in ("e_a_true", "e_a_pred") for cs in ddl.COORD_SYSTEMS)
        con.execute(f"UPDATE {table} SET n_a_rows = 0, {emptied} WHERE event_number = {event}")
        sample = energy.fetch_momentum(con, record, spec, centres)
    finally:
        con.close()
    assert sample.present["a"].tolist().count(False) == 1
    result = energy.build_by_momentum(sample)
    payload = result.as_dict()
    assert payload["no_deposit"] == {"a": 1, "b": 0}
    assert payload["outside_slices"] == {"a": 0, "b": 0}
    old = energy.build_by_momentum(before).as_dict()
    assert sum(payload["slice_counts_by_shower"]["a"].values()) == \
        sum(old["slice_counts_by_shower"]["a"].values()) - 1
    assert len([s for s in payload["series"] if s["shower"] == "a"]) == 1
    # Its momentum is out of the calibration's numerator, as the sentence says.
    kept = sample.present["a"]
    assert payload["calibration"]["c_a"] == pytest.approx(
        sample.momentum["a"][kept].sum() / sample.deposit["a"][kept].sum(), rel=1e-12)
    assert payload["calibration"]["c_a"] < sample.momentum["a"].sum() / sample.deposit["a"].sum()
    notice = energy.no_deposit_notice(1)
    assert "is left out of the calibration" in notice
    assert notice in routes_energy.momentum_warnings(result)
    assert "are left out of the calibration" in energy.no_deposit_notice(3)


def test_the_d_panel_and_the_response_card_share_one_calibration_with_an_absent_shower(
        cursor, record):
    """One shower A emptied in an in-memory copy of the demo table (no hits, so no D).

    Admitted by include_undefined_d, it is left out of the energy panel's
    calibration exactly as /api/response leaves it out, the panel says so,
    and the two constants agree.
    """
    from calosrv.query import response

    table = naming.quote(naming.event_table(record.table_name))
    rows = cursor.execute(f"SELECT * FROM {table}").df()
    con = duckdb.connect(":memory:")
    try:
        con.register("demo", rows)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM demo")
        (event,) = con.execute(f"SELECT min(event_number) FROM {table}").fetchone()
        emptied = ", ".join(f"{ddl.seg_stat_column(stem, cs)} = 0"
                            for stem in ("e_a_true", "e_a_pred") for cs in ddl.COORD_SYSTEMS)
        con.execute(f"UPDATE {table} SET n_a_rows = 0, d = NULL, {emptied} "
                    f"WHERE event_number = {event}")
        spec = filters.build(record, include_undefined_d=True)
        panel = energy.compute(con, record, spec)
        cards = response.fetch(con, record, spec, showers.of(record))
        n_events = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()
    assert panel.n_events == n_events
    by_key = {s.key: response.calibrate(s) for s in cards}
    assert by_key["a"].c.value == pytest.approx(panel.calibration["c_a"], rel=1e-12)
    assert by_key["b"].c.value == pytest.approx(panel.calibration["c_b"], rel=1e-12)
    assert panel.notices == [energy.absent_calibration_notice({"a": 1, "b": 0})]
    assert panel.notices[0].startswith("1 selected event has no shower-A hits:")


def test_a_shower_without_a_deposit_is_counted_apart(record):
    """No hits, no response: in no slice, not 'outside', and out of the calibration."""
    sample = _sample(record, (40, 20, 0, 0), n_outside=5)
    absent = np.flatnonzero(sample.slice_index["a"] == 0)[:3]
    sample.present["a"][absent] = False
    sample.deposit["a"][absent] = 0.0
    sample.values["e_dep"][absent] = 0.0
    payload = energy.build_by_momentum(sample).as_dict()
    assert payload["no_deposit"] == {"a": 3, "b": None}
    assert payload["slice_counts_by_shower"]["a"]["0"] == 37
    assert payload["outside_slices"]["a"] == 5
    assert sum(payload["slice_counts"].values()) + 5 + 3 == sample.n_events
    assert min(s["fit"]["mu"] for s in payload["series"]) > 0
    kept = sample.present["a"]
    c = sample.momentum["a"][kept].sum() / sample.deposit["a"][kept].sum()
    assert payload["calibration"]["c_a"] == pytest.approx(c, rel=1e-12)


def test_bin_ranges_span_every_shower_of_a_bin():
    bins = {"a": np.array([2, 2, 5, -1]), "b": np.array([5, 7, 2, 2])}
    momenta = {"a": np.array([2.1, 2.9, 5.5, 9.0]), "b": np.array([5.2, 7.7, 2.05, np.nan])}
    ranges = energy._bin_ranges(bins, momenta)
    assert ranges == {2: (2.05, 2.9), 5: (5.2, 5.5), 7: (7.7, 7.7)}
    classes, notices = momentum_mod.relabel_bins(momentum_mod.unit_bins(2, 7), ranges)
    assert notices == [] and classes[0].label == "2–3 GeV"
    odd, notices = momentum_mod.relabel_bins(momentum_mod.unit_bins(2, 7), {**ranges, 7: (6.5, 7.7)})
    assert odd[-1].label.startswith("bin 7 (p 6.5") and "bin 7" in notices[0]


def test_momentum_view_numbers_are_compact_and_typeset(record):
    sample = _sample(record, (300, 20, 9, 2))
    payload = energy.build_by_momentum(sample).as_dict()
    for series in payload["series"]:
        fit = series["fit"]
        for name in ("mu", "sigma", "mu_error", "sigma_core"):
            value = fit[name]
            if value is not None:
                assert float(f"{value:.6g}") == value
        assert not signed_hyphens(fit["note"]), fit["note"]
        # The repeated sentences travel once, in texts; a core refit keeps its own.
        assert series["message"] is None
        if fit["estimator"] == "core_refit":
            assert not signed_hyphens(fit["estimator_note"])
        else:
            assert fit["estimator_note"] is None
            assert fit["estimator"] in payload["texts"]["estimator_note"]
        if series["draw"] != "histogram":
            key = "degenerate" if fit["degenerate"] else series["draw"]
            assert payload["texts"]["message"][key]
    core = [s for s in payload["series"] if s["fit"]["estimator"] == "core_refit"]
    assert core and "±2.5σ" in core[0]["fit"]["estimator_note"]
    assert payload["texts"]["prefix"].format(n=7) == "N = 7: "
    assert payload["texts"] is energy.MOMENTUM_TEXTS


# ------------------------------------------------------------ budget guard --


def _production(record, slices, per, series_set, two=True, bins=False, seed=3):
    """A selection at production scale: ``per`` showers per slice and shower.

    Production holds about 1,000 showers per 1 GeV bin and shower; the
    0.8 GeV windows used here hold 800. Shower B's momenta are A's, shuffled,
    so every slice holds ``per`` of each.
    """
    rng = np.random.default_rng(seed)
    if bins:
        slicing = momentum_mod.MomentumSlicing(
            momentum_mod.MODE_BINS, tuple(momentum_mod.unit_bins(0, slices - 1)), None)
    else:
        slicing = momentum_mod.parse_slicing(
            ",".join(repr(0.4 + 0.8 * j) for j in range(slices)), 0.4)
    p = np.concatenate([rng.uniform(c.lo, c.hi, size=per) for c in slicing.classes])

    def index(momenta):
        return momentum_mod.assign(momenta, slicing.classes,
                                   np.floor(momenta).astype(np.int64)).astype(np.int64)

    a, b = showers.of(record, "both")
    if not two:
        dep = 0.03 * p * rng.normal(1.0, 0.1, p.size)
        series = (energy.MomentumSeries(energy.DEPOSIT_KEY, energy.DEPOSIT_LABEL, "a",
                                        "deposit", "e_dep"),)
        return energy.MomentumSample(
            showers=(a,), series_set=energy.DEPOSIT_SET, series=series, slicing=slicing,
            n_events=p.size, slice_index={"a": index(p)}, momentum={"a": p},
            present={"a": np.ones(p.size, bool)}, deposit={"a": dep}, values={"e_dep": dep})
    p_b = rng.permutation(p)
    _, chosen = energy.momentum_series(record, series_set)
    dep = {"a": 0.03 * p * rng.normal(1.0, 0.1, p.size),
           "b": 0.03 * p_b * rng.normal(1.0, 0.1, p.size)}
    values = {m.key: dep[m.shower] * (rng.normal(1.0, 0.05, p.size) if m.kind == "pred" else 1.0)
              for m in chosen}
    return energy.MomentumSample(
        showers=(a, b), series_set=series_set, series=chosen, slicing=slicing,
        n_events=p.size, slice_index={"a": index(p), "b": index(p_b)},
        momentum={"a": p, "b": p_b},
        present={"a": np.ones(p.size, bool), "b": np.ones(p.size, bool)},
        deposit=dep, values=values, segmentation_frame="absolute" if two else None)


def _served(sample) -> tuple[dict, int, bool]:
    """The momentum view of a sample through the route's guard and sentences."""
    network = ({"model": "segmentation", "frame": "absolute"}
               if any(m.kind == "pred" for m in sample.series) else None)

    def respond(points, bins, extra):
        result = energy.build_by_momentum(sample, bins=bins, curve_points=points)
        meta = ApiMeta(table_name="experiment_baseline",
                       warnings=list(extra) + routes_energy.momentum_warnings(result),
                       notes={"network": network})
        return envelope(meta, **result.as_dict(), filter={
            "e1": [0.7, 20.0], "e2": [0.7, 20.0], "d": [0.0, 3200.0],
            "include_undefined_d": False})

    body = routes_energy.within_budget(respond, routes_energy.REMEDY_MOMENTUM)
    over = any("served as it is" in w for w in body["meta"]["warnings"])
    return body, density.wire_size(body), over


def test_the_two_shower_series_limit_fits_every_density_with_headroom(record):
    """MAX_TWO_SHOWER_SERIES, measured at production scale.

    Production's twenty 1 GeV bins with truth or model - 40 series - fit at
    every density, the sparse curve+strip regime (8-14 showers per series)
    included, and keep 5% headroom at the guard's coarsest rendering. The 24
    windows p_slices accepts do not fit even there, which is why they are
    refused. series=all fits at the limit's ten windows, and a single shower's
    24 windows (24 series) fit.
    """
    limit = routes_energy.MAX_TWO_SHOWER_SERIES
    for series_set in ("truth", "model"):
        for per in (8, 14, 1000):
            sample = _production(record, limit // 2, per, series_set, bins=True)
            body, size, over = _served(sample)
            assert len(body["series"]) == limit and size < density.RESPONSE_LIMIT and not over
    coarsest = energy.build_by_momentum(
        _production(record, limit // 2, 14, "truth", bins=True),
        curve_points=routes_energy.CURVE_POINT_STEPS[-1], bins=histogram.MIN_BINS)
    assert density.wire_size(coarsest.as_dict()) < 0.95 * density.RESPONSE_LIMIT
    body, size, over = _served(_production(record, momentum_mod.MAX_CLASSES, 800, "truth"))
    assert over and size >= density.RESPONSE_LIMIT
    # The notice quotes the size of the body that carries it.
    (notice,) = [w for w in body["meta"]["warnings"] if "served as it is" in w]
    assert f"still {size:,} bytes" in notice and "fewer series" in notice
    body, size, over = _served(_production(record, limit // 4, 800, "all"))
    assert len(body["series"]) == limit and size < density.RESPONSE_LIMIT and not over
    body, size, over = _served(_production(record, momentum_mod.MAX_CLASSES, 4000, "deposit",
                                           two=False))
    assert len(body["series"]) == 24 and size < density.RESPONSE_LIMIT and not over


def test_the_series_limit_is_refused_on_p_slices(record):
    limit = routes_energy.MAX_TWO_SHOWER_SERIES
    routes_energy._refuse_too_many_series(_production(record, limit // 2, 20, "truth", bins=True))
    routes_energy._refuse_too_many_series(_production(record, limit // 4, 20, "all"))
    routes_energy._refuse_too_many_series(
        _production(record, momentum_mod.MAX_CLASSES, 20, "deposit", two=False))
    for slices, series_set in ((limit // 2 + 1, "model"), (limit // 4 + 1, "all"),
                               (momentum_mod.MAX_CLASSES, "truth")):
        with pytest.raises(ValidationError) as caught:
            routes_energy._refuse_too_many_series(_production(record, slices, 20, series_set))
        assert caught.value.extra["field"] == "p_slices"
        assert f"at most {limit}" in str(caught.value)


def _respond(sample, request_bins=40):
    calls = []

    def respond(points, bins, extra):
        calls.append((points, bins))
        result = energy.build_by_momentum(
            sample, bins=request_bins if bins is None else bins, curve_points=points)
        return envelope(ApiMeta(table_name="t", warnings=list(extra)), **result.as_dict())

    return respond, calls


def test_guard_serves_a_fitting_body_untouched(record):
    sample = _sample(record, (200, 200, 200, 200))
    respond, calls = _respond(sample)
    body = routes_energy.within_budget(respond)
    assert density.wire_size(body) < density.RESPONSE_LIMIT
    assert calls == [(histogram.CURVE_POINTS, None)]
    assert body["meta"]["warnings"] == []


def test_guard_coarsens_histograms_and_says_still_over(record, monkeypatch):
    sample = _sample(record, (200,) * 20, centres=tuple(range(1, 21)), n_outside=0)
    respond, calls = _respond(sample)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1_000)
    body = routes_energy.within_budget(respond)
    warnings = body["meta"]["warnings"]
    # The curve steps run first and unchanged, then the bins halve to the floor.
    assert [p for p, _ in calls] == [histogram.CURVE_POINTS, 150, 100, 75, 50, 50, 50, 50]
    assert [b for _, b in calls][-3:] == [20, 10, 8]
    assert body["axis"]["bins"] == histogram.MIN_BINS == 8
    assert body["axis"]["curve_points"] == 50
    assert warnings[0].startswith("Density curves sampled at 50 points instead of 200")
    assert "Histograms drawn with 8 bins instead of 40 (40 → 20 → 10 → 8" in warnings[1]
    assert "served as it is" in warnings[-1]
    assert "sampled at 50 points and 8 histogram bins" in warnings[-1]
    assert f"still {density.wire_size(body):,} bytes" in warnings[-1]
    assert "halved at each step, never below 8" in warnings[1]
    # Served through the D panel's remedy by default: it has no series to drop.
    assert "fewer slices bring it under" in warnings[-1] and "series bring" not in warnings[-1]
    assert not any(signed_hyphens(w) for w in warnings)


def test_guard_stops_at_the_first_bin_step_that_fits(record, monkeypatch):
    sample = _sample(record, (200,) * 20, centres=tuple(range(1, 21)), n_outside=0)
    respond, _ = _respond(sample)
    at_40 = density.wire_size(respond(50, 40, ["x" * 300, "y" * 300]))
    at_20 = density.wire_size(respond(50, 20, ["x" * 300, "y" * 300]))
    assert at_20 < at_40
    monkeypatch.setattr(density, "RESPONSE_LIMIT", (at_20 + at_40) // 2)
    body = routes_energy.within_budget(respond)
    assert body["axis"]["bins"] == 20
    assert density.wire_size(body) < density.RESPONSE_LIMIT
    assert not any("served as it is" in w for w in body["meta"]["warnings"])
    assert any("Density curves sampled at 50" in w for w in body["meta"]["warnings"])
