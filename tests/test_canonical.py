"""The canonical centre-of-separation frame, against the demonstration database.

The demonstration file holds two events, so these tests exercise the low-N path
the interface opens on: N = 2 labels, provisional ranges, and the sub-cell
splat at its largest factor. Production-scale behaviour (k = 2 on 22.5 M hits,
the payload guard on a wide window) is covered by ``test_canonical_subset.py``
when a subset CSV is available.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.grid import frame
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from calosrv.query import canonical, centroids, density, ensemble, filters, panels, projections, window


@pytest.fixture
def framed(cursor, record):
    """Statistics, grid, footprint and bundle for the full demo selection."""
    spec = filters.build(record)
    stats = canonical.frame_statistics(cursor, record, spec)
    footprint = canonical.cell_footprint(cursor, record)
    grid = frame.plan_window(stats.d_entry_max, stats.theta_max, record.lattice)
    k = frame.choose_subsample(stats.n_hits)
    bundle = canonical.fetch_canonical(cursor, record, spec, stats, grid, k, footprint)
    return {"spec": spec, "stats": stats, "footprint": footprint, "grid": grid, "k": k, "bundle": bundle}


def _framed_energy(cursor, record, spec) -> float:
    """Energy of the selected hits whose event has a defined frame, from the table."""
    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    defined = " AND ".join(f"e.{c} IS NOT NULL" for c in canonical._FRAME_COLUMNS)
    return float(cursor.execute(
        f"SELECT coalesce(sum(p.energy), 0) FROM {proj} p JOIN {event} e USING (event_number) "
        f"WHERE {spec.where_sql('p')} AND {defined}",
        spec.params(),
    ).fetchone()[0])


# ------------------------------------------------------------------- scan --


def test_canonical_query_scans_the_projection_table_once(cursor, record, framed):
    """The join adds a scan of the small event table and two RANGE generators
    for the sub-deposits; the hit-level table itself must appear exactly once."""
    plan = canonical.explain(
        cursor, record, framed["spec"], framed["grid"], framed["k"], framed["footprint"]
    )
    assert plan.count(naming.proj_table(record.table_name)) == 1
    assert plan.count(naming.event_table(record.table_name)) >= 1


@pytest.mark.parametrize("k", [2, 3, 6])
def test_energy_is_conserved_for_any_subsample_factor(cursor, record, framed, k):
    """Splitting a cell into k x k sub-deposits must not create or lose energy."""
    bundle = canonical.fetch_canonical(
        cursor, record, framed["spec"], framed["stats"], framed["grid"], k, framed["footprint"]
    )
    expected = _framed_energy(cursor, record, framed["spec"])
    assert bundle.total_energy + bundle.energy_outside == pytest.approx(expected, rel=1e-9)
    # The two depth panels project the same deposits.
    assert bundle.yz.planes["e"].sum() == pytest.approx(bundle.xz.planes["e"].sum(), rel=1e-12)
    assert bundle.subsample_k == k


def test_the_entrance_slab_holds_less_than_the_full_depth(framed):
    bundle = framed["bundle"]
    assert 0 < bundle.xy.planes["e"].sum() < bundle.xz.planes["e"].sum()


def test_events_without_a_frame_are_counted_not_dropped_silently(cursor, record):
    """Undefined-D events cannot be co-registered even when the filter admits them."""
    spec = filters.build(record, include_undefined_d=True)
    stats = canonical.frame_statistics(cursor, record, spec)
    assert stats.n_selected >= stats.n_events
    assert stats.n_excluded_no_frame == stats.n_selected - stats.n_events


def test_frame_statistics_agree_with_a_numpy_recomputation(cursor, record, framed):
    """D_entry, psi and the rotated directions, recomputed from the event table."""
    stats = framed["stats"]
    z_front = record.lattice.z.lo
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"SELECT cax, cay, caz, cbx, cby, cbz, theta_a, phi_a, theta_b, phi_b FROM {event} "
        f"WHERE {framed['spec'].where_sql()} AND {canonical._FRAME_DEFINED} ORDER BY event_number",
        framed["spec"].params(),
    ).fetchall()
    arr = np.array(rows, dtype=np.float64)
    xa, ya = frame.entry_anchor(arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 6], arr[:, 7], z_front)
    xb, yb = frame.entry_anchor(arr[:, 3], arr[:, 4], arr[:, 5], arr[:, 8], arr[:, 9], z_front)
    params = frame.frame_of(xa, ya, xb, yb)

    assert stats.n_events == len(rows)
    assert stats.d_entry.mean == pytest.approx(float(params.d_entry.mean()), rel=1e-6)
    assert stats.d_entry.hi == pytest.approx(float(params.d_entry.max()), rel=1e-6)

    ua = frame.rotate_direction(frame.unit_direction(arr[:, 6], arr[:, 7]), params.psi)
    slope_x = ua[:, 0] / ua[:, 2]
    assert stats.a.slope_mean[0] == pytest.approx(float(slope_x.mean()), rel=1e-6)
    if len(rows) >= 2:
        assert stats.a.slope_sd[0] == pytest.approx(float(slope_x.std(ddof=1)), rel=1e-6)
    resultant = math.hypot(*(ua[:, :2] / np.linalg.norm(ua[:, :2], axis=1, keepdims=True)).mean(axis=0))
    assert stats.a.resultant_transverse == pytest.approx(resultant, rel=1e-6)


def _single_event_spec(cursor, record):
    """A filter admitting exactly one framed event, through its E1 value."""
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"SELECT event_number, e1 FROM {event} WHERE {canonical._FRAME_DEFINED} "
        "ORDER BY e1"
    ).fetchall()
    if len(rows) < 2:
        pytest.skip("need at least two framed events to isolate one by E1")
    ev, e1 = int(rows[0][0]), float(rows[0][1])
    e1_next = float(rows[1][1])
    if e1_next <= e1:
        pytest.skip("two framed events share E1; cannot isolate one")
    return ev, filters.build(record, e1_max=0.5 * (e1 + e1_next))


def test_per_event_centroid_transforms_exactly_like_the_hits(cursor, record, framed):
    """The co-registration commutes with an energy-weighted mean.

    For one event, the fA-weighted entrance-slab centroid measured in the
    canonical bundle must equal the laboratory centroid pushed through the same
    motion. The sub-deposits of a cell are symmetric about its centre, so their
    mean is the rotated centre exactly; only the 20 mm binning of each
    sub-deposit moves the measured centroid, by well under a bin.
    """
    z_front = record.lattice.z.lo
    event = quote(naming.event_table(record.table_name))
    proj = quote(naming.proj_table(record.table_name))
    ev, spec = _single_event_spec(cursor, record)
    row = cursor.execute(
        f"SELECT cax, cay, caz, cbx, cby, cbz, theta_a, phi_a, theta_b, phi_b "
        f"FROM {event} WHERE event_number = ?", [ev]
    ).fetchone()
    xa, ya = frame.entry_anchor(row[0], row[1], row[2], row[6], row[7], z_front)
    xb, yb = frame.entry_anchor(row[3], row[4], row[5], row[8], row[9], z_front)
    params = frame.frame_of(xa, ya, xb, yb)

    # Laboratory slab centroid of shower A for this event, from the cell coordinates.
    lat = record.lattice
    rows = cursor.execute(
        f"SELECT ix, iy, sum(energy * CAST(fa_true AS DOUBLE)) FROM {proj} "
        f"WHERE event_number = ? AND iz <= {lat.slab_iz} GROUP BY ix, iy", [ev]
    ).fetchall()
    cells = np.array(rows, dtype=np.float64)
    if cells.size == 0 or cells[:, 2].sum() <= 0:
        pytest.skip("the isolated demo event has no shower-A energy in the slab")
    w = cells[:, 2]
    lab_x = float(np.dot(lat.x.coords[cells[:, 0].astype(int)], w) / w.sum())
    lab_y = float(np.dot(lat.y.coords[cells[:, 1].astype(int)], w) / w.sum())
    expected_x, expected_y = frame.rotate_xy(lab_x, lab_y, params.x0, params.y0, params.psi)

    stats = canonical.frame_statistics(cursor, record, spec)
    assert stats.n_events == 1
    grid = frame.plan_window(stats.d_entry_max, stats.theta_max, lat)
    bundle = canonical.fetch_canonical(cursor, record, spec, stats, grid, 6, framed["footprint"])
    pair = centroids.compute(bundle)["truth_voxel"]
    assert pair.a.x == pytest.approx(float(expected_x), abs=0.75 * frame.CANONICAL_PITCH_MM)
    assert pair.a.y == pytest.approx(float(expected_y), abs=0.75 * frame.CANONICAL_PITCH_MM)
    # And the single event's own anchor is where the frame puts it.
    assert stats.d_entry.mean == pytest.approx(float(params.d_entry), rel=1e-9)


def test_single_event_statistics_are_undefined_not_trivial(cursor, record):
    """One direction has no resultant length, dispersion or Rayleigh test.

    Left ungated, avg(u/|u|) over one event is exactly 1.0 and an exported
    figure would state an ensemble coherence of 1.000 for a single shower.
    """
    _, spec = _single_event_spec(cursor, record)
    stats = canonical.frame_statistics(cursor, record, spec)
    assert stats.n_events == 1
    for shower in (stats.a, stats.b):
        assert shower.resultant_transverse is None
        assert shower.rayleigh_p is None
        assert shower.slope_sd == (None, None)
        assert all(v is not None for v in shower.slope_mean)
    assert stats.d_entry.se is None and stats.d_entry.ci95_half is None


def test_out_of_range_selection_stays_empty_after_clamping(record, cursor):
    """Clamping must never resurrect a boundary event from an empty window."""
    beyond = filters.build(record, e1_min=record.e1_max + 5.0, e1_max=record.e1_max + 10.0)
    clamped = beyond.clamped(record)
    assert (clamped.e1_min, clamped.e1_max) == (beyond.e1_min, beyond.e1_max)
    assert canonical.frame_statistics(cursor, record, clamped).n_events == 0
    # A window touching the data from one side is clamped on that side only.
    edge = filters.build(record, e1_min=record.e1_max - 0.5, e1_max=record.e1_max + 10.0)
    inside = edge.clamped(record)
    assert inside.e1_min == pytest.approx(record.e1_max - 0.5)
    assert inside.e1_max == pytest.approx(record.e1_max)


def test_moments_quote_a_student_t_interval(framed):
    stats = framed["stats"]
    if stats.n_events < 2:
        pytest.skip("needs two events")
    m = stats.d_entry
    assert m.ci95_half == pytest.approx(frame.t_quantile_975(m.n - 1) * m.se)
    assert "ci95_half" in m.as_dict()


# ----------------------------------------------------------------- window --


def test_fitted_window_covers_the_central_energy_and_reports_the_rest(framed):
    fit = window.fit_window(framed["bundle"])
    for name in ("xy", "yz", "xz"):
        panel_fit = fit.panel(name)
        assert 0.0 <= panel_fit.energy_fraction_outside <= 0.05
        assert panel_fit.row.hi > panel_fit.row.lo
    # Depth is never cropped.
    assert fit.yz.col.applied is False and fit.xz.col.applied is False
    assert fit.yz.col.n_bins == framed["grid"].n_z
    # Two events: the ranges are labelled provisional.
    assert fit.provisional is (framed["stats"].n_events < frame.PROVISIONAL_N)
    assert "provisional" in fit.note if fit.provisional else True


def test_fit_axis_snaps_outward_to_whole_bins():
    edges = np.linspace(-100.0, 100.0, 11)
    marginal = np.array([0, 0, 1, 5, 20, 40, 20, 5, 1, 0], dtype=float)
    axis = window.fit_axis(marginal, edges)
    # Total 92: the 1st-percentile point (0.92) lies in bin 2 and the 99th
    # (91.08) in bin 8, so both are kept and the window is [-60, 80].
    assert axis.lo == pytest.approx(-60.0) and axis.hi == pytest.approx(80.0)
    assert axis.energy_fraction_outside == pytest.approx(0.0)
    assert axis.applied
    # Tails below the 1st / above the 99th percentile are cut and counted:
    # total 93, so 0.5 in bin 0 lies under the 0.93 mark and 0.5 in bin 9
    # above the 92.07 mark.
    tail = np.array([0.5, 0, 1, 5, 20, 40, 20, 5, 1, 0.5], dtype=float)
    cut = window.fit_axis(tail, edges)
    assert cut.lo_index == 2 and cut.hi_index == 9
    assert cut.energy_fraction_outside == pytest.approx(1.0 / 93.0)
    empty = window.fit_axis(np.zeros(10), edges)
    assert not empty.applied and (empty.lo, empty.hi) == (-100.0, 100.0)


# ---------------------------------------------------------------- density --


@pytest.mark.parametrize("mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 90), (MODE_CONTINUOUS, 250)])
def test_density_conserves_energy_and_stays_within_budget(framed, mode, resolution):
    """sum(<rho> * N * dA) over a panel equals the energy inside its window."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, mode, resolution)
    size = len(json.dumps(out["panels"]).encode())
    assert size < 100_000
    for name in ("xy", "yz", "xz"):
        payload = out["panels"][name]
        cropped = fit.panel(name).crop(bundle.panel(name).planes["e"]).sum()
        assert payload["total"] == pytest.approx(float(cropped), rel=1e-9)
        assert payload["scale"]["unit"] == "a.u."
        assert payload["scale"]["vmin"] == -frame.RAMP_DECADES
        assert payload["scale"]["vmax"] >= 0.0
        assert "clipped_high" not in payload["scale"]
        assert payload["axes"]["col"]["symbol"] in ("x′", "z′")
        assert payload["axes"]["row"]["symbol"] in ("x′", "y′")
        assert payload["n_events"] == bundle.n_events
        assert payload["topk_unit"] == density.RHO_UNIT
        for cell in payload["topk"]:
            assert cell["value"] > 0
    assert out["panels"]["yz"]["scale"]["shared_with"] == "yz+xz"
    assert out["resolution"]["r_z"] == framed["grid"].n_z


def test_relative_ramp_is_normalised_to_the_selection_peak(framed):
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, MODE_NATIVE, 150)
    peaks = density.selection_peaks(bundle)
    assert out["rho"]["norm"] == "selection"
    assert out["rho"]["ref"] == peaks
    xy = out["panels"]["xy"]
    # The brightest exact value, in physical units, is the reference itself
    # when the crop kept the peak bin.
    assert xy["topk"][0]["value"] <= peaks["xy"] * (1 + 1e-9)
    assert xy["scale"]["rho_ref"] == pytest.approx(peaks["xy"])
    assert xy["scale"]["rho_unit"] == density.RHO_UNIT


def test_dataset_reference_can_raise_the_ramp_above_unity(framed):
    """A selection brighter than its reference extends the ramp instead of clipping."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    peaks = density.selection_peaks(bundle)
    weaker = {"xy": peaks["xy"] / 4.0, "depth": peaks["depth"] / 4.0}
    out = density.render_canonical(bundle, fit, MODE_NATIVE, 150, rho_norm="dataset", reference=weaker)
    scale = out["panels"]["xy"]["scale"]
    assert scale["norm"] == "dataset"
    assert scale["vmax"] == pytest.approx(math.log10(4.0), abs=1e-6)
    assert scale["locked"] is True


def test_budget_guard_degrades_deterministically_and_says_so(framed):
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    tight = density.render_canonical(bundle, fit, MODE_CONTINUOUS, 400, limit=20_000)
    assert len(json.dumps(tight["panels"]).encode()) <= 20_000 or tight["notices"]
    assert tight["notices"], "a lowered resolution must be disclosed"
    assert tight["resolution"]["r_x"] < 400
    native = density.render_canonical(bundle, fit, MODE_NATIVE, 150, limit=15_000)
    assert native["resolution"]["merge"] >= 2
    # Depth layers are never merged by the guard.
    assert native["resolution"]["r_z"] == framed["grid"].n_z


def test_gradcam_channel_keeps_the_fixed_attention_scale(framed):
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, MODE_NATIVE, 150, channel=panels.CHANNEL_GRADCAM)
    scale = out["panels"]["xy"]["scale"]
    assert scale["scale"] == "linear" and (scale["vmin"], scale["vmax"]) == (0.0, 1.0)


# --------------------------------------------------------------- overlays --


def test_exactly_two_ensemble_axes_originate_at_the_anchors(framed):
    stats, grid = framed["stats"], framed["grid"]
    axes = ensemble.ensemble_axes(stats, grid)
    half = 0.5 * stats.d_entry.mean
    for shower, sign in (("a", -1.0), ("b", 1.0)):
        block = axes[shower]
        assert block["xz"]["axis"][0] == pytest.approx([0.0, sign * half])
        assert block["yz"]["axis"][0] == pytest.approx([0.0, 0.0])
        assert block["xz"]["axis"][1][0] == pytest.approx(axes["depth_max"])
        assert axes["anchors"][shower]["x"] == pytest.approx(sign * half)
    assert set(axes["anchors"]) == {"a", "b"}
    n = stats.n_events
    if n >= 2:
        for shower in ("a", "b"):
            assert axes[shower]["xz"]["band"] is not None
            assert axes[shower]["xz"]["envelope"] is not None
            assert 0.0 <= axes[shower]["rayleigh_p"] <= 1.0
        if n == 2:
            assert axes["a"]["xz"]["dof_note"] == "1 d.o.f."
            assert axes["a"]["label"].startswith("weak")
            assert axes["anchors"]["a"]["dof_note"] == "1 d.o.f."


def test_single_event_axes_are_labelled_not_ensemble(framed):
    stats = framed["stats"]
    lonely = canonical.FrameStats(**{**stats.__dict__, "n_events": 1})
    axes = ensemble.ensemble_axes(lonely, framed["grid"])
    assert axes["a"]["label"] == "single event, not an ensemble"
    assert axes["a"]["xz"]["band"] is None
    assert axes["a"]["rayleigh_p"] is None
    assert any("not an ensemble" in note for note in axes["notes"])


def test_measured_centroids_are_expressed_in_the_canonical_frame(framed):
    """centroids.compute reads the bundle's own axes, not the detector lattice."""
    bundle = framed["bundle"]
    pairs = centroids.compute(bundle)
    grid = bundle.grid
    for pair in pairs.values():
        for point in (pair.a, pair.b):
            assert -grid.half_x <= point.x <= grid.half_x
            assert -grid.half_y <= point.y <= grid.half_y
            assert 0.0 <= point.z <= grid.axis("z").extent[1]
    axes = panels.shower_axes(bundle, "yz")
    assert len(axes["depth"]) == grid.n_z
    assert axes["depth"][0] == pytest.approx(0.0)


def test_native_bundle_axis_is_the_lattice(cursor, record):
    spec = filters.build(record)
    bundle = projections.fetch_native(cursor, record, spec)
    np.testing.assert_array_equal(bundle.axis("x").coords, record.lattice.x.coords)
    np.testing.assert_array_equal(bundle.axis("z").coords, record.lattice.z.coords)


def test_cache_key_starts_with_the_table_name(framed, record):
    key = canonical.cache_key(framed["spec"], False, framed["grid"], framed["k"], framed["footprint"])
    assert key[0] == record.table_name
    assert "canonical" in key


def test_snapped_full_range_bounds_share_the_warmed_cache_entry(record):
    """The interface snaps slider domains outward (0.70 for a 0.708 GeV bound).

    A looser bound selects the same rows, so it must map onto the same cache
    key as the exact dataset range the start-up warmer used - otherwise the
    two-second production scan would be paid twice.
    """
    exact = filters.build(record)
    snapped = filters.build(
        record,
        e1_min=record.e1_min - 0.03, e1_max=record.e1_max + 0.04,
        e2_min=record.e2_min - 0.01, e2_max=record.e2_max + 0.02,
        d_min=record.d_min - 0.7, d_max=record.d_max + 0.9,
    )
    assert snapped.cache_key() != exact.cache_key()
    assert snapped.clamped(record).cache_key() == exact.clamped(record).cache_key()
    # A genuine narrowing survives clamping.
    narrow = filters.build(record, e1_max=(record.e1_min + record.e1_max) / 2)
    assert narrow.clamped(record).cache_key() != exact.clamped(record).cache_key()
