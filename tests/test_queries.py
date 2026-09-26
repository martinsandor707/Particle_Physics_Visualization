"""Query-layer behaviour against a real ingested database."""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.errors import ValidationError
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE, plan_resolution
from calosrv.query import (
    centroids,
    energy,
    filters,
    panels,
    performance,
    projections,
    summary,
)
from calosrv.stats import histogram
from calosrv.stats import metrics as metric_mod


def test_ingest_kept_every_row(ingested):
    assert ingested["n_hits"] == 1000
    assert ingested["n_events"] == 2
    assert ingested["verification"].ok


def test_each_projection_query_uses_a_single_scan(cursor, record):
    """The depth panels rest on GROUPING SETS reading the table once; the
    entrance-slab XY query is the second and last scan.

    This is a planner behaviour rather than a contract. If a DuckDB upgrade
    changed it, the only symptom would be a silently doubled p95 latency, so it
    is asserted here instead.
    """
    spec = filters.build(record)
    plans = projections.explain(cursor, record, spec).split("\n----\n")
    assert len(plans) == 2
    for plan in plans:
        scans = re.findall(r"SEQ_SCAN|TABLE_SCAN", plan)
        assert len(scans) == 1, f"expected one scan, found {len(scans)}:\n{plan}"


def test_depth_panels_agree_on_total_energy(cursor, record):
    """YZ and XZ project the same selection, so their totals must match."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    assert bundle.yz.planes["e"].sum() == pytest.approx(
        bundle.xz.planes["e"].sum(), rel=1e-12
    )


def test_xy_panel_is_restricted_to_the_entrance_slab(cursor, record):
    """The XY panel must hold strictly less energy than the full depth."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    assert bundle.xy.planes["e"].sum() < bundle.yz.planes["e"].sum()


def test_panel_shapes_match_the_measured_lattice(cursor, record):
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    lattice = record.lattice
    assert bundle.xy.planes["e"].shape == (lattice.y.n, lattice.x.n)
    assert bundle.yz.planes["e"].shape == (lattice.y.n, lattice.z.n)
    assert bundle.xz.planes["e"].shape == (lattice.x.n, lattice.z.n)


def test_filter_narrows_the_selection(cursor, record):
    """A tighter E1 band must not return more energy than the full range."""
    wide = filters.build(record)
    narrow = filters.build(
        record,
        e1_min=record.e1_min,
        e1_max=(record.e1_min + record.e1_max) / 2,
    )
    total_wide = projections.fetch_native(cursor, record, wide).xz.planes["e"].sum()
    total_narrow = projections.fetch_native(cursor, record, narrow).xz.planes["e"].sum()
    assert total_narrow <= total_wide


def test_inverted_range_is_rejected(record):
    with pytest.raises(ValidationError):
        filters.build(record, e1_min=99.0, e1_max=1.0)


def test_null_separation_is_excluded_explicitly(record):
    """The NULL-D exclusion must be written out, not left implicit in BETWEEN."""
    spec = filters.build(record)
    assert "d IS NOT NULL" in spec.where_sql()

    permissive = filters.build(record, include_undefined_d=True)
    assert "d IS NULL" in permissive.where_sql()


def test_centroids_use_fractional_weights_not_the_category(cursor, record):
    """Both voxel-weighted centroid pairs must be produced and be distinct."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    pairs = centroids.compute(bundle)

    assert set(pairs) == {"truth_voxel", "pred_voxel"}
    for pair in pairs.values():
        assert pair.a.x is not None and pair.b.x is not None
        assert pair.separation_mm is not None and pair.separation_mm > 0

    # Ground truth and prediction disagree somewhere, which is the diagnostic.
    truth = pairs["truth_voxel"]
    pred = pairs["pred_voxel"]
    assert truth.separation_mm != pytest.approx(pred.separation_mm, rel=1e-9)


def test_centroid_energy_splits_between_the_two_showers(cursor, record):
    """A and B attributions must sum to the panel's total deposited energy."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    pair = centroids.compute(bundle)["truth_voxel"]
    total = bundle.xy.planes["e"].sum()
    assert pair.a.energy + pair.b.energy == pytest.approx(total, rel=1e-9)


def test_mean_d_comes_from_events_not_hits(cursor, record):
    """Mean D must be the per-event mean, never hit-multiplicity weighted."""
    spec = filters.build(record)
    selection = summary.summarise(cursor, record, spec)

    event_table = quote(naming.event_table(record.table_name))
    expected = cursor.execute(f"SELECT avg(d) FROM {event_table}").fetchone()[0]
    assert selection.d_mean == pytest.approx(float(expected), rel=1e-9)

    # And it must differ from the hit-weighted average, or the test proves
    # nothing about which one is being used.
    proj_table = quote(naming.proj_table(record.table_name))
    hit_weighted = cursor.execute(f"SELECT avg(d) FROM {proj_table}").fetchone()[0]
    assert selection.d_mean != pytest.approx(float(hit_weighted), rel=1e-6)


def test_energy_calibration_puts_truth_on_the_momentum_scale(cursor, record):
    """Calibrated truth energies must average to the true incident momentum.

    That is the definition of the calibration constant, so it is a check that
    it was applied in the right direction and to the right series.
    """
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec, calibrated=True)

    assert result.calibration["applied"]
    c_a = result.calibration["c_a"]
    assert c_a > 1.0, "sampling fraction must scale deposits up, not down"

    event_table = quote(naming.event_table(record.table_name))
    row = cursor.execute(
        f"SELECT sum(e_a_true_abs), sum(CAST(e1 AS DOUBLE)) FROM {event_table}"
    ).fetchone()
    assert float(row[0]) * c_a == pytest.approx(float(row[1]), rel=1e-9)


def test_uncalibrated_energies_are_far_below_the_momentum_scale(cursor, record):
    """The reason calibration exists: deposits are orders of magnitude smaller."""
    spec = filters.build(record)
    raw = energy.compute(cursor, record, spec, calibrated=False)
    assert raw.scale == "deposited"
    assert raw.axis["hi"] < 1.0
    assert raw.benchmarks == []


def test_energy_slices_include_an_overflow_bin(cursor, record):
    """No event may fall outside the slice scheme."""
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec)
    assert result.slices[-1].hi is None
    assert sum(result.slice_counts.values()) == result.n_events


def test_two_event_slices_report_moments_but_draw_no_curve(cursor, record):
    """Two events fix a mean and a one-d.o.f. width, and no shape at all.

    The demonstration dataset holds exactly two events, so this is the panel a
    first-boot user sees. It must show real numbers rather than em-dashes, and
    must not draw a smooth density curve through them.
    """
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec)
    for series in result.series:
        assert series.fit.insufficient is False
        assert series.fit.mu is not None
        assert series.fit.sigma is not None
        assert series.fit.estimator == "moments_1dof"
        # No curve, and nothing that could set the density axis.
        assert series.curve_y == []
        assert series.draw == "strip"
        assert series.drives_scale is False
        # The two interval marks are distinct quantities.
        markers = series.markers()
        ci = markers["ci95_hi"] - markers["ci95_lo"]
        spread = markers["dispersion_hi"] - markers["dispersion_lo"]
        assert ci > 0 and spread > 0 and ci != spread


@pytest.mark.parametrize("coord_system,frame", [
    ("lab", "absolute"), ("trans", "trans"), ("local", "local"),
])
def test_performance_metrics_roll_up_exactly(cursor, record, ingested, coord_system, frame):
    """Every frame's segmentation cards equal a direct scan of the archived hits."""
    from calosrv.db import archive

    spec = filters.build(record)
    report = performance.compute(cursor, record, spec, coord_system=coord_system)

    hits = archive.relation(ingested["settings"], record.table_name)
    pred, true = f"segmentation_{frame}_pred", f"segmentation_{frame}_true"
    row = cursor.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE ({pred} >= 0.5) = ({true} >= 0.5)),
               sum(abs(CAST({pred} AS DOUBLE) - CAST({true} AS DOUBLE))),
               sum(energy * abs(CAST({pred} AS DOUBLE) - CAST({true} AS DOUBLE))),
               sum(energy)
        FROM {hits}
        WHERE energy IS NOT NULL AND isfinite(energy) AND energy > 0
        """
    ).fetchone()

    n, correct, abs_err, wabs_err, e_dep = (float(v) for v in row)
    assert report.classification.accuracy == pytest.approx(correct / n, rel=1e-12)
    assert report.regression.mae == pytest.approx(abs_err / n, rel=1e-12)
    assert report.regression.mae_energy_weighted == pytest.approx(
        wabs_err / e_dep, rel=1e-12
    )
    cards = {c.id: c.estimate for c in report.cards}
    assert cards["accuracy"].value == pytest.approx(correct / n, rel=1e-12)
    assert cards["wmae"].value == pytest.approx(wabs_err / e_dep, rel=1e-12)
    assert report.network == {"model": "segmentation", "frame": frame}


@pytest.mark.parametrize("model", ["energy", "angle"])
@pytest.mark.parametrize("coord_system,frame", [
    ("lab", "absolute"), ("trans", "trans"), ("local", "local"),
])
def test_residual_cards_equal_the_archived_per_shower_values(cursor, record, ingested, model,
                                                            coord_system, frame):
    from calosrv.db import archive

    spec = filters.build(record)
    report = performance.compute(cursor, record, spec, model=model, coord_system=coord_system)
    hits = archive.relation(ingested["settings"], record.table_name)
    cards = {c.id: c.estimate for c in report.cards}
    for shower, is_a in (("a", True), ("b", False)):
        # One prediction per (event, shower); 'A+B' hits carry shower B's values.
        pred, true = (np.asarray(v, dtype=np.float64) for v in zip(*cursor.execute(
            f"""SELECT CAST(max({model}_{frame}_pred) AS DOUBLE), CAST(max({model}_{frame}_true) AS DOUBLE)
                FROM {hits} WHERE centroid_AB_distance IS NOT NULL
                  AND (particle_origin = 'A') = {is_a}
                GROUP BY event_number"""
        ).fetchall()))
        if model == "energy":
            residual, card = (pred - true) / true, f"sigma_rel_{shower}"
        else:
            residual, card = (pred - true) * 1000.0, f"sigma_theta_{shower}"
        got = cards[card]
        assert got.n == pred.size
        assert got.value == pytest.approx(float(np.std(residual, ddof=1)), rel=1e-6)


def test_energy_weighted_mae_differs_from_the_unweighted_one(cursor, record):
    """If they agreed, reporting both would be pointless."""
    spec = filters.build(record)
    report = performance.compute(cursor, record, spec)
    assert report.regression.mae != pytest.approx(
        report.regression.mae_energy_weighted, rel=1e-6
    )


def test_metric_helpers_guard_division_by_zero():
    empty = metric_mod.classification(0, 0, 0, 0, 0)
    assert empty.accuracy is None and empty.f1_a is None


# --------------------------------------------------------------- rendering --


@pytest.mark.parametrize(
    "mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 150), (MODE_CONTINUOUS, 200)]
)
def test_rendered_payload_stays_under_the_budget(cursor, record, mode, resolution):
    """Every projections payload must fit the 100 KB budget."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    plan = plan_resolution(record.lattice, mode, resolution)
    rendered = panels.render_all(bundle, plan, global_vmax=record.cell_e_max)

    size = len(json.dumps(rendered).encode())
    assert size < 100_000, f"payload {size} bytes exceeds the 100 KB budget"


def test_rendered_payload_contains_no_raw_hits(cursor, record):
    """The frontend must never receive a raw hit array."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    plan = plan_resolution(record.lattice, MODE_NATIVE, 150)
    rendered = panels.render_all(bundle, plan, global_vmax=record.cell_e_max)

    for panel in rendered.values():
        # The only per-cell arrays permitted are the quantised raster and the
        # bounded top-k list of exact peak values.
        assert isinstance(panel["data"], str)
        assert len(panel["topk"]) <= 64
        assert "hits" not in panel and "rows" not in panel


def test_gradcam_channel_uses_a_fixed_zero_to_one_scale(cursor, record):
    """Attention maps must stay comparable between selections."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    plan = plan_resolution(record.lattice, MODE_NATIVE, 150)
    rendered = panels.render_all(
        bundle, plan, channel=panels.CHANNEL_GRADCAM, global_vmax=record.cell_e_max
    )
    scale = rendered["xy"]["scale"]
    assert scale["scale"] == "linear"
    assert (scale["vmin"], scale["vmax"]) == (0.0, 1.0)


def test_native_render_matches_the_native_matrix_exactly(cursor, record):
    """Native mode must pass the matrix through, not resample it onto itself."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    plan = plan_resolution(record.lattice, MODE_NATIVE, 150)
    _, resampled = panels.render_panel(bundle, "yz", plan)
    assert np.array_equal(resampled, bundle.yz.planes["e"])


def test_depth_panels_share_one_colour_scale(cursor, record):
    """YZ and XZ are meant to be read against each other."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    plan = plan_resolution(record.lattice, MODE_NATIVE, 150)
    rendered = panels.render_all(bundle, plan, global_vmax=record.cell_e_max)
    assert rendered["yz"]["scale"]["vmax"] == pytest.approx(
        rendered["xz"]["scale"]["vmax"]
    )


# ------------------------------------------------------- staggered lattice --


def test_stagger_detection_flags_an_alternating_comb():
    """A synthetic staggered lattice must be recognised.

    One bin per cell keeps every 1-D bin populated, but the XY panel is a
    product of two axes and the populated (x, y) pairs are not the full product
    on a staggered detector. Half of every other column is empty by geometry.
    """
    from calosrv.query import stagger

    rng = np.random.default_rng(4)
    matrix = rng.random((104, 212)) * 1e-3
    # Alternate columns only populate alternate rows.
    matrix[1::2, 1::2] = 0.0

    report = stagger.detect(matrix)
    assert report.staggered is True
    assert report.lag1 < stagger.COMB_THRESHOLD
    assert "staggered" in report.note


def test_stagger_detection_is_quiet_on_a_smooth_field():
    """A smoothly varying shower must not be flagged."""
    from calosrv.query import stagger

    y, x = np.mgrid[0:104, 0:212]
    smooth = np.exp(-(((x - 106) / 40.0) ** 2 + ((y - 52) / 20.0) ** 2))
    report = stagger.detect(smooth)
    assert report.staggered is False
    assert report.note == ""


def test_splatting_removes_the_comb(cursor, record):
    """Continuous Field must actually fix what Native mode exposes.

    This is the claim the interface makes to the user when it tells them how to
    get rid of the comb, so it is worth asserting rather than assuming.
    """
    from calosrv.query import stagger

    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)

    synthetic = bundle.xy.planes["e"].copy()
    if not stagger.detect(synthetic).staggered:
        pytest.skip("demonstration lattice is not staggered")

    plan = plan_resolution(record.lattice, MODE_CONTINUOUS, record.lattice.x.n // 2)
    _, resampled = panels.render_panel(bundle, "xy", plan)
    assert stagger.detect(resampled).staggered is False


# ------------------------------------------- low statistics and overlays --


def test_low_statistics_suppresses_the_histogram_not_the_estimate(cursor, record):
    """Below the threshold a density histogram is an artefact, not a result.

    density=True divides by N * bin_width, so at small N a single event produces
    a spike whose height is set by the binning. The panel must receive the
    events themselves instead, and be told why - but mu and sigma are not
    artefacts and must still be reported.
    """
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec)
    assert result.n_events < result.thresholds["histogram"]

    for series in result.series:
        payload = series.as_dict()
        assert payload["draw"] != "histogram"
        assert payload["drives_scale"] is False
        assert payload["histogram"] is None
        assert len(payload["strip"]["values"]) == result.n_events
        # The strip must be sorted, so it reads left to right.
        assert payload["strip"]["values"] == sorted(payload["strip"]["values"])
        # The estimate itself survives, and the message explains the marks
        # rather than announcing a refusal.
        assert payload["fit"]["mu"] is not None
        assert payload["markers"] is not None
        assert "Insufficient sample size" not in payload["message"]


def test_a_thin_slice_never_sets_the_density_axis(cursor, record):
    """Only statistically robust series may drive the canvas scale.

    A curve peak is 1/(sigma*sqrt(2pi)); with sigma poorly determined, letting a
    thin slice set yMax would flatten every well-measured slice beside it.
    """
    edges = histogram.axis_edges(0.0, 20.0, 40)
    curve_x = histogram.curve_axis(0.0, 20.0)
    rng = np.random.default_rng(31)

    thin = energy._build_series(
        "e_a_pred", "Shower A - model", "a", "pred", 0, "0-50 mm",
        rng.normal(10.0, 1.0, size=9), edges, curve_x,
    )
    assert thin.draw == "curve+strip"
    assert thin.drives_scale is False
    assert thin.curve_y and thin.curve_peak > 0
    assert thin.strip  # the events are shown alongside the de-weighted curve

    thick = energy._build_series(
        "e_a_pred", "Shower A - model", "a", "pred", 0, "0-50 mm",
        rng.normal(10.0, 1.0, size=200), edges, curve_x,
    )
    assert thick.draw == "histogram"
    assert thick.drives_scale is True
    assert thick.strip == []


def test_curve_floor_withholds_the_curve_but_not_the_numbers(cursor, record):
    """3 <= N < 8: events and summary markers, no continuous density."""
    edges = histogram.axis_edges(0.0, 20.0, 40)
    curve_x = histogram.curve_axis(0.0, 20.0)
    sample = np.array([9.0, 10.0, 11.0, 12.0])

    series = energy._build_series(
        "e_a_pred", "Shower A - model", "a", "pred", 0, "0-50 mm",
        sample, edges, curve_x,
    )
    assert series.draw == "strip"
    assert series.curve_y == []
    assert series.curve_peak is None
    assert series.fit.mu == pytest.approx(10.5)
    assert series.fit.sigma == pytest.approx(float(sample.std(ddof=1)))
    assert series.markers() is not None


def test_energy_axis_lands_on_clean_ticks(cursor, record):
    """A raw percentile bound must never terminate the axis."""
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec)
    axis = result.axis

    interval = axis["interval"]
    assert interval > 0
    for edge in (axis["lo"], axis["hi"]):
        assert abs(edge / interval - round(edge / interval)) < 1e-9
    # And the clean range must still contain everything the clip kept.
    assert axis["lo"] <= axis["clipping"]["lo"]
    assert axis["hi"] >= axis["clipping"]["hi"]


def test_trajectories_skip_events_without_a_centroid(cursor, record):
    """Events where shower A deposited nothing have no entry point to project."""
    spec = filters.build(record)
    paths = summary.trajectories(cursor, record, spec)

    for path in paths:
        assert path["a"]["x"] is not None
        assert path["a"]["theta"] is not None
        assert path["a"]["phi"] is not None

    event_table = quote(naming.event_table(record.table_name))
    eligible = cursor.execute(
        f"SELECT count(*) FROM {event_table} "
        "WHERE cax IS NOT NULL AND theta_a IS NOT NULL AND phi_a IS NOT NULL"
    ).fetchone()[0]
    assert len(paths) == min(int(eligible), summary.MAX_TRAJECTORY_EVENTS)


def test_trajectories_are_capped(cursor, record):
    spec = filters.build(record)
    assert len(summary.trajectories(cursor, record, spec, limit=1)) <= 1


def test_angular_coherence_reports_a_resultant_length(cursor, record):
    """The measurement that justifies never drawing an averaged direction."""
    spec = filters.build(record)
    coherence = summary.angular_coherence(cursor, record, spec)
    assert coherence["n"] > 0
    for key in ("r_a", "r_b"):
        assert 0.0 <= coherence[key] <= 1.0


def test_shower_axes_cover_every_depth_layer(cursor, record):
    """The measured axis is the overlay that stays valid at any event count."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)

    for name in ("yz", "xz"):
        axes = panels.shower_axes(bundle, name)
        assert len(axes["depth"]) == record.lattice.z.n
        assert len(axes["a"]) == record.lattice.z.n
        assert len(axes["b"]) == record.lattice.z.n

        row_axis = record.lattice.axis(bundle.panel(name).row_axis)
        for point in axes["a"]:
            if point is None:
                continue
            depth, centroid = point
            # A centroid is a weighted mean of coordinates, so it can never fall
            # outside the range of those coordinates.
            assert row_axis.lo <= centroid <= row_axis.hi
            assert record.lattice.z.lo <= depth <= record.lattice.z.hi


def test_shower_axes_split_energy_between_the_showers(cursor, record):
    """A and B axes must be computed from complementary weights."""
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    axes = panels.shower_axes(bundle, "yz")
    a_pts = [p for p in axes["a"] if p]
    b_pts = [p for p in axes["b"] if p]
    assert a_pts and b_pts
    # The two showers are at different places, so the axes must not coincide.
    assert any(abs(a[1] - b[1]) > 1e-9 for a, b in zip(a_pts, b_pts))


def test_a_scan_that_straddles_an_invalidation_is_not_cached():
    """An in-flight scan read the old tables; its bundle is returned but never cached."""
    from types import SimpleNamespace

    from calosrv.query.cache import BundleCache

    cache = BundleCache(4, name="straddle")
    key = ("some_table", 1)

    def compute():
        cache.invalidate_table("some_table")  # an ingest finished meanwhile
        return SimpleNamespace(nbytes=1)

    bundle, cached = cache.get_or_compute(key, compute)
    assert bundle is not None and cached is False
    assert cache.get_any([key]) is None
    fresh, cached = cache.get_or_compute(key, lambda: SimpleNamespace(nbytes=1))
    assert cache.get_any([key]) is fresh


def test_an_undefined_separation_joins_no_d_slice():
    """With include_undefined_d, a NULL D must not fall into the well-separated slice."""
    import duckdb

    from calosrv.stats.slices import UNDEFINED_SLICE, build_slices, case_sql

    slices = build_slices()
    rows = duckdb.connect().execute(
        f"SELECT d, {case_sql(slices)} AS s FROM (VALUES (NULL), (10.0), (5000.0)) t(d) ORDER BY d NULLS FIRST"
    ).fetchall()
    assert rows[0][1] == UNDEFINED_SLICE
    assert rows[1][1] == slices[0].index and rows[2][1] == slices[-1].index
