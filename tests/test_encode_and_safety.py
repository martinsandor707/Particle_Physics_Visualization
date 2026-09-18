"""Payload encoding, colour scaling, statistics, and the SQL-injection wall."""

from __future__ import annotations

import base64
import math

import numpy as np
import pytest

from calodash import stats as calodash_stats
from calosrv.db import naming
from calosrv.encode import quantize, scale as scale_mod, topk
from calosrv.encode.matrix import encode_matrix
from calosrv.errors import ValidationError
from calosrv.grid.lattice import Axis
from calosrv.stats import clip, gaussian, histogram, slices

# ------------------------------------------------------------------ naming --


@pytest.mark.parametrize(
    "bad",
    [
        "", "  ", "Run3", "1run", "run-3", "run 3", "run;DROP TABLE x",
        'run"x', "run'x", "experiment", "a" * 49, "../etc",
    ],
)
def test_invalid_experiment_names_are_rejected(bad):
    """The single wall between a user string and SQL identifier text."""
    with pytest.raises(ValidationError):
        naming.validate_experiment_name(bad)


@pytest.mark.parametrize("good", ["run3", "v37", "a", "experiment_baseline", "a_1_b"])
def test_valid_names_survive_a_round_trip(good):
    assert naming.validate_experiment_name(good) == good
    assert naming.experiment_of(naming.hit_table(good)) == good
    assert naming.experiment_of(naming.proj_table(good, sampled=True)) == good


def test_every_derived_table_is_recognised_as_managed():
    for table in naming.all_tables("run3"):
        assert naming.is_managed_table(table)


# --------------------------------------------------------------- quantising --


def test_empty_cells_are_distinct_from_the_faintest_deposit():
    """Code 0 must mean 'no deposit', never 'bottom of the ramp'.

    Painting an unlit cell with the ramp's lowest colour makes an empty detector
    region look like a faint halo.
    """
    matrix = np.array([[0.0, 1e-12, 1e-3]])
    colour = scale_mod.resolve_scale(matrix, lock=False)
    codes = quantize.quantize(matrix, colour)
    assert codes[0, 0] == quantize.EMPTY_CODE
    assert codes[0, 1] >= quantize.MIN_CODE
    assert codes[0, 2] == quantize.MAX_CODE


def test_quantisation_round_trips_within_one_step():
    rng = np.random.default_rng(7)
    matrix = 10 ** (rng.uniform(-8, -2, size=(40, 40)))
    colour = scale_mod.resolve_scale(matrix, lock=False)
    codes = quantize.quantize(matrix, colour)
    recovered = quantize.dequantize(codes, colour)

    step = (colour.vmax - colour.vmin) / quantize.LEVELS
    error = np.abs(np.log10(recovered) - np.log10(matrix))
    assert np.nanmax(error) <= step


def test_log_scale_floors_at_six_decades():
    """Without a floor, the ramp is spent on cells carrying no physics."""
    matrix = np.array([[1e-20, 1e-2]])
    colour = scale_mod.resolve_scale(matrix, lock=False)
    assert colour.vmax - colour.vmin == pytest.approx(scale_mod.DEFAULT_DECADES)
    assert colour.n_below == 1


def test_locked_scale_ignores_the_selection_maximum():
    """A locked ramp keeps two selections visually comparable."""
    full = np.array([[1e-2]])
    subset = np.array([[1e-4]])
    locked = scale_mod.resolve_scale(subset, global_vmax=float(full.max()), lock=True)
    unlocked = scale_mod.resolve_scale(subset, lock=False)
    assert locked.vmax > unlocked.vmax
    assert locked.locked is True


def test_gradcam_scale_is_always_zero_to_one():
    colour = scale_mod.resolve_scale(np.array([[0.1, 0.2]]), channel="gradcam")
    assert (colour.vmin, colour.vmax) == (0.0, 1.0)
    assert colour.scale == "linear"


def test_topk_returns_the_largest_cells_in_order():
    matrix = np.arange(100, dtype=float).reshape(10, 10)
    cells = topk.top_cells(matrix, k=5)
    assert [c["value"] for c in cells] == [99.0, 98.0, 97.0, 96.0, 95.0]


def test_topk_ignores_empty_cells():
    assert topk.top_cells(np.zeros((5, 5)), k=4) == []


# ---------------------------------------------------------------- encoding --


def test_encoded_matrix_decodes_to_the_original_shape():
    matrix = np.abs(np.random.default_rng(3).normal(size=(20, 30))) * 1e-4
    colour = scale_mod.resolve_scale(matrix, lock=False)
    axis_rows = Axis("y", np.linspace(-100, 100, 20))
    axis_cols = Axis("x", np.linspace(-200, 200, 30))

    payload = encode_matrix(
        matrix, colour, axis_rows.edges, axis_cols.edges, "y", "x", "xy", native=True
    )

    raw = base64.b64decode(payload["data"])
    assert len(raw) == 20 * 30
    assert payload["shape"] == [20, 30]


def test_irregular_axis_ships_its_edges_and_uniform_one_does_not():
    """Edges are only worth their bytes when the axis is genuinely irregular."""
    matrix = np.ones((4, 6))
    colour = scale_mod.resolve_scale(matrix, lock=False)
    uniform = Axis("y", np.linspace(0, 100, 4))
    irregular = Axis("x", np.array([0.0, 1.0, 40.0, 41.0, 80.0, 81.0]))

    payload = encode_matrix(
        matrix, colour, uniform.edges, irregular.edges, "y", "x", "xy", native=True
    )
    assert "edges" not in payload["axes"]["row"]
    assert payload["axes"]["row"]["uniform"] is True
    assert "edges" in payload["axes"]["col"]
    assert payload["axes"]["col"]["uniform"] is False


# -------------------------------------------------------------- statistics --


def test_three_events_still_report_a_sample_width():
    """A width from three events is weak, not undefined.

    The old behaviour refused outright, which left the panel printing em-dashes
    for a slice whose mean and spread were perfectly computable. What the small
    sample forbids is a *curve*, not a *number*.
    """
    sample = np.array([1.0, 2.0, 3.0])
    fit = gaussian.fit_gaussian(sample)
    assert fit.insufficient is False
    assert fit.mu == pytest.approx(2.0)
    assert fit.sigma == pytest.approx(float(sample.std(ddof=1)))
    assert fit.resolution == pytest.approx(fit.sigma / fit.mu)
    assert fit.estimator == "moments"
    assert fit.core_applied is False
    # ...and the note must say what was used, not what was withheld.
    assert "sample moments" in fit.estimator_note


def test_two_events_report_one_degree_of_freedom():
    """N = 2 is the shipped demo dataset; it must not print em-dashes."""
    fit = gaussian.fit_gaussian(np.array([4.0, 6.0]))
    assert fit.estimator == "moments_1dof"
    assert fit.mu == pytest.approx(5.0)
    assert fit.sigma == pytest.approx(math.sqrt(2.0))
    assert fit.insufficient is False


def test_one_event_has_a_position_but_no_width():
    fit = gaussian.fit_gaussian(np.array([7.0]))
    assert fit.estimator == "mean_only"
    assert fit.mu == pytest.approx(7.0)
    assert fit.sigma is None
    assert fit.insufficient is True


def test_thresholds_are_separately_gated():
    """One threshold used to answer three different questions.

    Reporting a number, drawing a curve, drawing a histogram and refitting a
    core are four decisions with four different justifications, and collapsing
    them into a single floor is what silenced mu and sigma on every thin slice.
    """
    assert gaussian.MIN_MOMENT_SAMPLES == 2
    assert gaussian.MIN_CURVE_SAMPLES == 8
    assert histogram.MIN_HISTOGRAM_SAMPLES == 15
    assert gaussian.MIN_CORE_SAMPLES == 15
    assert gaussian.MIN_ROBUST_SAMPLES == 20
    assert (
        gaussian.MIN_MOMENT_SAMPLES
        < gaussian.MIN_CURVE_SAMPLES
        <= gaussian.MIN_CORE_SAMPLES
        <= gaussian.MIN_ROBUST_SAMPLES
    )

    # Fourteen events: moments only. Fifteen: the core refit takes over.
    rng = np.random.default_rng(3)
    assert gaussian.fit_gaussian(rng.normal(10, 1, 14)).estimator == "moments"
    fit = gaussian.fit_gaussian(rng.normal(10, 1, 15))
    assert fit.core_applied is True
    assert fit.sigma is not None


def test_gaussian_moments_match_numpy():
    rng = np.random.default_rng(11)
    sample = rng.normal(10.0, 2.0, size=5000)
    fit = gaussian.fit_gaussian(sample)
    assert fit.mu == pytest.approx(float(sample.mean()))
    # The quoted width is the unbiased sample estimator...
    assert fit.sigma == pytest.approx(float(sample.std(ddof=1)))
    # ...and the population form is kept so the notebook stays comparable.
    assert fit.sigma_population == pytest.approx(float(sample.std(ddof=0)))
    assert fit.sigma_core == pytest.approx(2.0, rel=0.02)
    assert fit.non_gaussian is False


def test_ddof_matches_calodash_on_both_widths():
    """The two architectures must not quote different sigma for one sample.

    calosrv and calodash/stats.py both moved to ddof = 1 together; the ddof = 0
    form survives here only so the reference notebook stays comparable.
    """
    rng = np.random.default_rng(17)
    sample = rng.normal(5.0, 1.5, size=400)
    fit = gaussian.fit_gaussian(sample)
    band = calodash_stats.summarise_band(
        "band", sample, sample, float(sample.min()), float(sample.max())
    )
    assert fit.sigma == pytest.approx(band.sigma)
    assert fit.sigma_population == pytest.approx(float(sample.std(ddof=0)))


def test_core_debias_is_not_applied_when_nothing_was_truncated():
    """The de-bias corrects for a cut; an uncut sample must not receive it.

    Applying it unconditionally inflated the quoted width by 6.77% whenever the
    +/-2.5 sigma window happened to exclude nothing - reachable at N = 15-25,
    and far more reachable now that thin slices are reported at all.
    """
    # A tight, symmetric sample: no event lies beyond +/-2.5 sigma.
    sample = np.linspace(-1.0, 1.0, 21)
    fit = gaussian.fit_gaussian(sample)
    assert fit.core_applied is True
    assert fit.n_core == fit.n
    assert fit.sigma_core == pytest.approx(fit.sigma)
    assert fit.sigma_core < fit.sigma / gaussian.CORE_TRUNCATION_FACTOR


def test_shape_verdict_is_withheld_below_the_robust_floor():
    """An untestable assumption must read as untested, not as confirmed."""
    rng = np.random.default_rng(19)
    thin = gaussian.fit_gaussian(rng.normal(10, 1, 12))
    assert thin.shape_testable is False
    assert thin.non_gaussian is None
    assert thin.sigma_robust is None

    thick = gaussian.fit_gaussian(rng.normal(10, 1, 400))
    assert thick.shape_testable is True
    assert thick.non_gaussian is False


def test_moment_uncertainties_match_their_closed_forms():
    rng = np.random.default_rng(23)
    sample = rng.normal(10.0, 2.0, size=9)
    fit = gaussian.fit_gaussian(sample)
    n = fit.n
    assert fit.mu_error == pytest.approx(fit.sigma / math.sqrt(n))
    assert fit.sigma_error == pytest.approx(fit.sigma / math.sqrt(2 * (n - 1)))
    # c4 makes the residual bias of s visible rather than folding it in.
    assert fit.sigma_bias_factor == pytest.approx(gaussian.c4(n))
    assert fit.sigma_unbiased == pytest.approx(fit.sigma / gaussian.c4(n))


def test_mean_interval_uses_student_t_not_a_normal_approximation():
    """At N = 3 a normal interval understates the uncertainty by 2.2x."""
    fit = gaussian.fit_gaussian(np.array([9.0, 10.0, 11.0]))
    half_width = fit.mu_ci95[1] - fit.mu
    assert half_width == pytest.approx(4.303 * fit.mu_error, rel=1e-3)
    assert half_width > 1.96 * fit.mu_error


def test_sigma_interval_is_asymmetric_and_wide_at_small_n():
    """A symmetric +/-SE on sigma is badly misleading at N = 3."""
    fit = gaussian.fit_gaussian(np.array([9.0, 10.0, 11.0]))
    lo, hi = fit.sigma_ci95
    assert lo / fit.sigma == pytest.approx(0.521, abs=0.005)
    assert hi / fit.sigma == pytest.approx(6.287, abs=0.01)
    # Asymmetric: the upper reach is far longer than the lower.
    assert (hi - fit.sigma) > 5 * (fit.sigma - lo)


def test_quantile_tables_match_reference_values():
    assert gaussian.t_quantile_975(2) == pytest.approx(4.303)
    assert gaussian.t_quantile_975(10) == pytest.approx(2.228)
    assert gaussian.chi2_quantile(2, upper=True) == pytest.approx(7.378)
    assert gaussian.chi2_quantile(2, upper=False) == pytest.approx(0.0506)
    # Beyond the table, the asymptotes must still land close.
    assert gaussian.t_quantile_975(40) == pytest.approx(2.021, abs=0.005)
    assert gaussian.chi2_quantile(50, upper=True) == pytest.approx(71.42, rel=0.01)


def test_identical_values_report_a_measured_zero_not_an_unknown():
    """sigma = 0 and sigma = None are different statements."""
    fit = gaussian.fit_gaussian(np.array([2.0, 2.0, 2.0, 2.0]))
    assert fit.degenerate is True
    assert fit.sigma == 0.0
    assert fit.sigma is not None
    assert fit.estimator == "degenerate"


def test_core_refit_is_unbiased_on_a_true_gaussian():
    """Truncating at ±2.5σ removes real variance; the fit must correct for it.

    Without the de-biasing constant the iterated refit converges about 6.3% low,
    which on a quoted energy resolution is a material misstatement.
    """
    rng = np.random.default_rng(2024)
    widths = []
    for _ in range(12):
        sample = rng.normal(0.0, 3.0, size=40000)
        widths.append(gaussian.fit_gaussian(sample).sigma_core)
    assert float(np.mean(widths)) == pytest.approx(3.0, rel=0.01)


def test_heavy_tail_is_flagged_as_non_gaussian():
    """A contaminated sample must be flagged, not silently curve-fitted."""
    rng = np.random.default_rng(5)
    core = rng.normal(10.0, 1.0, size=2000)
    tail = rng.normal(10.0, 12.0, size=400)
    fit = gaussian.fit_gaussian(np.concatenate([core, tail]))
    assert fit.non_gaussian is True
    # The core refit must recover the core width despite the contamination.
    assert fit.sigma_core < fit.sigma


def test_unit_area_gaussian_integrates_to_one():
    x = np.linspace(-40, 40, 20001)
    y = gaussian.gaussian_curve(x, 0.0, 3.0)
    assert np.trapezoid(y, x) == pytest.approx(1.0, rel=1e-6)


def test_percentile_clip_reports_what_it_hides():
    values = np.concatenate([np.full(1000, 1.0), np.array([1e6])])
    result = clip.percentile_clip(values, floor_at_zero=True)
    assert result.hi < 1e6
    assert result.n_above >= 1
    assert "outside" in result.note


def test_percentile_clip_leaves_small_samples_alone():
    """Percentiles of a handful of points are noise, not a range."""
    result = clip.percentile_clip(np.array([1.0, 2.0, 3.0]))
    assert result.applied is False
    assert result.n_outside == 0


def test_slices_always_end_in_an_unbounded_overflow():
    built = slices.build_slices([50, 100, 150, 200])
    assert len(built) == 5
    assert built[-1].hi is None
    assert "well separated" in built[-1].label


def test_slice_case_expression_covers_every_distance():
    built = slices.build_slices([50, 100])
    sql = slices.case_sql(built)
    assert "ELSE 2" in sql


def test_slice_edges_are_parsed_and_validated():
    assert slices.parse_edges("50,100") == (50.0, 100.0)
    assert slices.parse_edges(None) == slices.DEFAULT_EDGES
    with pytest.raises(ValidationError):
        slices.parse_edges("not,a,number")


# ------------------------------------------------------------- nice ranges --


@pytest.mark.parametrize(
    "lo,hi",
    [(0.0, 9.197060758), (0.0, 18.86), (0.0, 34.07297653), (0.0, 2.3), (0.0, 121.4)],
)
def test_nice_range_rounds_outward_to_clean_ticks(lo, hi):
    """A percentile bound must never terminate an axis as a raw float.

    9.197060758 on a tick label reads as precision about a limit that was only a
    display choice.
    """
    nlo, nhi, interval = clip.nice_range(lo, hi)
    assert nlo <= lo and nhi >= hi, "rounding must be outward, never inward"
    assert interval > 0
    # Every boundary must sit exactly on a tick.
    assert abs(nlo / interval - round(nlo / interval)) < 1e-9
    assert abs(nhi / interval - round(nhi / interval)) < 1e-9


def test_nice_range_produces_a_readable_number_of_ticks():
    for lo, hi in [(0.0, 9.2), (0.0, 25.0), (0.0, 34.1), (0.0, 120.0)]:
        nlo, nhi, interval = clip.nice_range(lo, hi)
        ticks = (nhi - nlo) / interval
        assert 2 <= ticks <= 24, f"{ticks} ticks for range {lo}-{hi}"


def test_nice_range_survives_degenerate_input():
    assert clip.nice_range(5.0, 5.0)[1] > clip.nice_range(5.0, 5.0)[0]
    assert clip.nice_range(float("nan"), 1.0) == (0.0, 1.0, 0.2)


# -------------------------------------------------------- adaptive binning --


@pytest.mark.parametrize(
    "n,expected",
    [(0, 8), (15, 8), (100, 10), (3700, 31), (3730, 32), (20000, 55), (10**9, 120)],
)
def test_adaptive_bins_follow_the_rice_rule(n, expected):
    """Bin count must track the sample size, clamped at both ends.

    A fixed 120 bins is right for tens of thousands of events and wrong for a
    few dozen: once the bins are finer than the spacing between events, each
    occupied bin holds exactly one and reports a height set by the bin width.
    """
    from calosrv.stats import histogram

    assert histogram.adaptive_bins(n) == expected


def test_adaptive_bins_keep_spike_heights_bounded():
    """The property the bin count exists to guarantee.

    With density normalisation a lone event in a bin peaks at
    1 / (N * bin_width). Adapting the bin count keeps that within a factor of a
    few of the true density instead of letting it run away as N shrinks.
    """
    from calosrv.stats import histogram

    span = 18.0
    for n in (15, 50, 500, 5000):
        bins = histogram.adaptive_bins(n)
        lone_spike = 1.0 / (n * (span / bins))
        assert lone_spike < 0.6, f"n={n} bins={bins} spike={lone_spike:.3f}"


# ------------------------------------------------- JSON float compliance --


def test_finite_rejects_infinity_and_nan():
    """These reach the metrics legitimately and cannot be encoded as JSON.

    A relative residual over an event whose true energy is femto-GeV small
    overflows to infinity; a correlation over a single event is NaN. Both used
    to abort the whole model-performance response with HTTP 500.
    """
    from calosrv.stats import metrics as metric_mod

    assert metric_mod.finite(float("inf")) is None
    assert metric_mod.finite(float("-inf")) is None
    assert metric_mod.finite(float("nan")) is None
    assert metric_mod.finite(None) is None
    assert metric_mod.finite(0.0) == 0.0
    assert metric_mod.finite(-2.5) == -2.5


def test_safe_div_survives_an_overflowing_ratio():
    from calosrv.stats import metrics as metric_mod

    # 1e308 / 1e-308 overflows the double range.
    assert metric_mod._safe_div(1e308, 1e-308) is None
    assert metric_mod._safe_div(1.0, 4.0) == 0.25


def test_json_safe_scrubs_nested_non_finite_values():
    """The net beneath the individual guards.

    A future aggregate added to a query must not be able to reintroduce a 500,
    so the envelope sanitises whatever it is handed.
    """
    import json

    from calosrv.models.common import json_safe

    payload = {
        "a": float("inf"),
        "b": [1.0, float("nan"), {"c": float("-inf")}],
        "d": {"e": (float("nan"), 2.0)},
        "keep": [1, "two", True, None, 3.5],
    }
    clean = json_safe(payload)

    assert clean["a"] is None
    assert clean["b"] == [1.0, None, {"c": None}]
    assert clean["d"]["e"] == [None, 2.0]
    assert clean["keep"] == [1, "two", True, None, 3.5]
    json.dumps(clean)  # must not raise


def test_envelope_output_is_json_encodable():
    import json

    from calosrv.models.common import ApiMeta, envelope

    body = envelope(
        ApiMeta(table_name="t"),
        metric=float("inf"),
        nested={"values": [float("nan"), 1.0]},
    )
    json.dumps(body)
    assert body["metric"] is None
    assert body["nested"]["values"] == [None, 1.0]
