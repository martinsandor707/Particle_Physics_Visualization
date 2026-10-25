"""B3, the energy panel sliced by incident momentum, at the query level.

The fetch is exercised on the two-event demonstration database (its four
showers sit at 2.71, 12.5, 17.9 and 6.39 GeV - in no notebook window, so it
also exercises the outside index). The panel itself is a pure function of a
:class:`~calosrv.query.energy.MomentumSample`, so the per-slice axes, the
low-N gates and the budget guard are tested on samples built here, where every
population is chosen.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.api import routes_energy
from calosrv.db import naming
from calosrv.errors import ValidationError
from calosrv.models.common import ApiMeta, envelope
from calosrv.query import density, energy, filters, showers
from calosrv.stats import gaussian, histogram
from calosrv.stats import momentum as momentum_mod
from calosrv.text import signed_hyphens

D_KEYS = ["slices", "slice_counts", "series", "calibration", "axis", "benchmarks",
          "n_events", "scale", "thresholds"]
MOMENTUM_KEYS = ["slice_by", "slicing", "slice_axes", "slice_counts_by_shower",
                 "outside_slices", "counted", "series_set", "no_deposit"]


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
])
def test_bad_slicings_are_refused_naming_the_field(cursor, record, raw, field):
    with pytest.raises(ValidationError) as caught:
        energy.compute_by_momentum(cursor, record, filters.build(record), raw)
    assert caught.value.extra["field"] == field


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
    assert payload["axis"] == {"unit": "GeV (incident-equivalent)", "bins": bins,
                               "per_slice": True, "curve_points": histogram.CURVE_POINTS}
    by_slice = {s["slice"]: s for s in payload["series"]}
    for a in axes:
        assert len(a["hist_centres"]) == bins
        assert len(a["curve_x"]) == histogram.CURVE_POINTS
        width = (a["hi"] - a["lo"]) / bins
        assert a["hist_centres"][0] == pytest.approx(a["lo"] + width / 2, rel=1e-5)
        assert a["hist_centres"][-1] == pytest.approx(a["hi"] - width / 2, rel=1e-5)
        # Floored at zero and rounded outward to clean ticks.
        assert a["lo"] == 0.0 and a["interval"] > 0
        assert a["hi"] / a["interval"] == pytest.approx(round(a["hi"] / a["interval"]))
        assert a["hi"] >= a["clipping"]["hi"]
        series = by_slice[a["slice"]]
        if series["histogram"] is not None:
            assert len(series["histogram"]["counts"]) == bins
        if series["curve"]["y"]:
            assert len(series["curve"]["y"]) == len(a["curve_x"])
    # Only the slices whose series reach the histogram floor set a range.
    assert [a["provisional"] for a in axes] == [False, False, True]
    assert [by_slice[i]["draw"] for i in (0, 1, 2)] == ["histogram", "histogram", "strip"]
    # An explicit bin count is shared the same way.
    explicit = energy.build_by_momentum(sample, bins=20).as_dict()
    assert {len(a["hist_centres"]) for a in explicit["slice_axes"]} == {20}


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
    axes = {a["slice"]: a for a in energy.build_by_momentum(sample).as_dict()["slice_axes"]}
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
    single = axes[2]["momentum"]["a"]
    assert single["n"] == 1 and single["sd"] is None and single["ci95"] is None


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


def test_a_shower_without_a_deposit_is_counted_apart(record):
    """No hits, no response: in no slice and not 'outside', but still in the calibration."""
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
    c = sample.momentum["a"].sum() / sample.deposit["a"].sum()
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
        for text in (series["message"], fit["estimator_note"], fit["note"]):
            assert not signed_hyphens(text), text
    core = [s for s in payload["series"] if s["fit"]["estimator"] == "core_refit"]
    assert core and "+/−" in core[0]["fit"]["estimator_note"]


# ------------------------------------------------------------ budget guard --


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
