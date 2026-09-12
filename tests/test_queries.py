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
from calosrv.stats import metrics as metric_mod


def test_ingest_kept_every_row(ingested):
    assert ingested["n_hits"] == 1000
    assert ingested["n_events"] == 2
    assert ingested["verification"].ok


def test_projection_query_uses_a_single_scan(cursor, record):
    """The whole design rests on GROUPING SETS reading the table once.

    This is a planner behaviour rather than a contract. If a DuckDB upgrade
    changed it, the only symptom would be a silently tripled p95 latency, so it
    is asserted here instead.
    """
    spec = filters.build(record)
    plan = projections.explain(cursor, record, spec)
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
        f"SELECT sum(e_a_true), sum(CAST(e1 AS DOUBLE)) FROM {event_table}"
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


def test_small_samples_are_reported_as_insufficient(cursor, record):
    """Two events must not produce a fitted width."""
    spec = filters.build(record)
    result = energy.compute(cursor, record, spec)
    for series in result.series:
        assert series.fit.insufficient
        assert series.fit.sigma is None
        assert series.curve_y == []


def test_performance_metrics_roll_up_exactly(cursor, record):
    """Metrics from stored statistics must equal a direct scan of the hits."""
    spec = filters.build(record)
    report = performance.compute(cursor, record, spec)

    hit_table = quote(naming.hit_table(record.table_name))
    row = cursor.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE (voxel_fA_pred >= 0.5) = (voxel_fA_true >= 0.5)),
               sum(abs(CAST(voxel_fA_pred AS DOUBLE) - CAST(voxel_fA_true AS DOUBLE))),
               sum(energy * abs(CAST(voxel_fA_pred AS DOUBLE)
                                - CAST(voxel_fA_true AS DOUBLE))),
               sum(energy)
        FROM {hit_table}
        WHERE energy IS NOT NULL AND isfinite(energy) AND energy > 0
        """
    ).fetchone()

    n, correct, abs_err, wabs_err, e_dep = (float(v) for v in row)
    assert report.classification.accuracy == pytest.approx(correct / n, rel=1e-12)
    assert report.regression.mae == pytest.approx(abs_err / n, rel=1e-12)
    assert report.regression.mae_energy_weighted == pytest.approx(
        wabs_err / e_dep, rel=1e-12
    )


def test_energy_weighted_mae_differs_from_the_unweighted_one(cursor, record):
    """If they agreed, reporting both would be pointless."""
    spec = filters.build(record)
    report = performance.compute(cursor, record, spec)
    assert report.regression.mae != pytest.approx(
        report.regression.mae_energy_weighted, rel=1e-6
    )


def test_metric_helpers_guard_division_by_zero():
    empty = metric_mod.classification(0, 0, 0, 0, 0, 0)
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
