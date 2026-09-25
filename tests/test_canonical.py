"""The canonical centre-of-separation frame, against the demonstration database.

The demonstration file holds two events, so these tests exercise the low-N path
the interface opens on: N = 2 labels, provisional ranges, and the sub-cell
splat at its largest factor. Production-scale behaviour (k = 2 on 22.5 M hits,
the payload guard on a wide window) is covered by ``test_canonical_subset.py``
when a subset CSV is available.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import math
import time

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.grid import frame
from calosrv.grid import kernel as kernel_mod
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from calosrv.query import (
    canonical, centroids, density, ensemble, filters, panels, projections, reconstruct, window,
)


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
        # Each transverse axis cuts at most 0.1% + 0.1% of its marginal.
        assert 0.0 <= panel_fit.energy_fraction_outside <= 0.004
        assert panel_fit.row.hi > panel_fit.row.lo
        assert panel_fit.row.symmetric and panel_fit.row.lo == -panel_fit.row.hi
        assert panel_fit.row.percentile_range is not None
    assert fit.xy.col.symmetric and fit.xy.col.lo == -fit.xy.col.hi
    # Depth is never cropped, and is not a centred window.
    assert fit.yz.col.applied is False and fit.xz.col.applied is False
    assert fit.yz.col.n_bins == framed["grid"].n_z
    assert fit.yz.col.half_width is None and not fit.xz.col.symmetric
    # Two events: the ranges are labelled provisional.
    assert fit.provisional is (framed["stats"].n_events < frame.PROVISIONAL_N)
    assert "provisional" in fit.note if fit.provisional else True
    data = fit.as_dict()
    assert data["rule"] == "symmetric" and data["percentiles"] == [0.1, 99.9]
    assert data["snap_mm"] == frame.CANONICAL_PITCH_MM
    assert set(data["xy"]["col"]) >= {"percentile_range", "symmetric", "half_width", "floored", "clamped"}


def test_windows_are_symmetric_whole_bins_above_the_floor(framed):
    fit = window.fit_window(framed["bundle"])
    grid = framed["grid"]
    axes = {"xy.row": fit.xy.row, "xy.col": fit.xy.col, "yz.row": fit.yz.row, "xz.row": fit.xz.row}
    for label, axis in axes.items():
        half = axis.half_width
        assert axis.lo == -half and axis.hi == half, label
        assert half % frame.CANONICAL_PITCH_MM == 0, label
        assert half >= fit.floor_mm or axis.clamped, label
        full = grid.half_y if label in ("xy.row", "yz.row") else grid.half_x
        assert half <= full
        # The index crop and the millimetre range describe the same bins.
        edges = grid.y_edges if label in ("xy.row", "yz.row") else grid.x_edges
        assert edges[axis.lo_index] == pytest.approx(axis.lo, abs=1e-9)
        assert edges[axis.hi_index] == pytest.approx(axis.hi, abs=1e-9)


def test_the_window_floor_is_provisional_below_twenty_events(framed):
    """200 mm while the evidence is weak; two cell footprints once it is not."""
    bundle = framed["bundle"]
    assert bundle.n_events < frame.PROVISIONAL_N
    weak = window.fit_window(bundle)
    assert weak.floor_mm == frame.SHOWER_RADIUS_MIN_MM and weak.provisional
    robust_stats = dataclasses.replace(bundle.stats, n_events=25)
    robust = window.fit_window(dataclasses.replace(bundle, stats=robust_stats))
    assert robust.floor_mm == 100.0 and not robust.provisional
    assert robust.as_dict()["floor_mm"] == 100.0
    assert robust.xy.row.half_width <= weak.xy.row.half_width


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


def _plan_of(out, fit, bundle, mode):
    """Rebuild the plan a render actually used, from what it reported."""
    resolution = out["resolution"]
    return density.plan_canonical(
        fit, bundle.grid, mode, resolution["r_x"], merge=resolution["merge"],
        kernel=reconstruct.choose_kernel(mode, bundle.n_events),
    )


def _codes(payload):
    raw = np.frombuffer(base64.b64decode(payload["data"]), dtype=np.uint8)
    return raw.reshape(payload["shape"])


@pytest.mark.parametrize("mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 90), (MODE_CONTINUOUS, 250)])
def test_density_conserves_energy_and_stays_within_budget(framed, mode, resolution):
    """sum(<rho> * N * dA) over a panel equals the energy the rendered window holds.

    Native Grid holds exactly the raw crop. Continuous Field moves energy across
    the window edge in both directions, so its total is the full accumulation
    plane weighted by each bin's inside fraction, and the outside share is
    measured after reconstruction.
    """
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, mode, resolution)
    size = len(json.dumps(out["panels"]).encode())
    assert size < 100_000
    plan = _plan_of(out, fit, bundle, mode)
    for name in ("xy", "yz", "xz"):
        payload = out["panels"][name]
        plane = bundle.panel(name).planes["e"]
        if mode == MODE_NATIVE:
            expected = float(fit.panel(name).crop(plane).sum())
            assert payload["kernel"] == "none"
        else:
            row_map, col_map = density.axis_maps(bundle, fit.panel(name), plan, name)
            inside_rows = reconstruct.inside_weights(row_map, plane.shape[0])
            inside_cols = reconstruct.inside_weights(col_map, plane.shape[1])
            expected = float(inside_rows @ plane @ inside_cols)
            assert payload["kernel"] == "gaussian", "two events are below the tent's N gate"
        assert payload["total"] == pytest.approx(expected, rel=1e-12)
        total_all = payload["total_energy_all_gev"]
        assert total_all == pytest.approx(float(plane.sum()))
        assert payload["energy_fraction_outside_window"] == pytest.approx(
            1.0 - payload["total"] / total_all, abs=1e-8
        )
        assert payload["energy_outside_window_gev"] == pytest.approx(total_all - payload["total"], abs=1e-12)
        assert payload["energy_fraction_outside_window_raw"] == pytest.approx(
            fit.panel(name).energy_fraction_outside, abs=1e-8
        )
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
    assert "floor" not in scale


def test_native_grid_is_the_raw_crop(framed):
    """The audit view: every displayed bin is the raw accumulation bin, untouched."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    plan = density.plan_canonical(fit, bundle.grid, MODE_NATIVE, 150)
    assert plan.kernel is kernel_mod.NONE
    for name in ("xy", "yz", "xz"):
        rendered = density.render_panel(
            bundle, fit.panel(name), plan, name, panels.CHANNEL_DENSITY, "energy", 1.0, "selection"
        )
        np.testing.assert_array_equal(rendered.energy, fit.panel(name).crop(bundle.panel(name).planes["e"]))


def test_depth_is_never_smoothed(framed):
    """On a transverse map reaching past the kernel's support, every depth
    layer keeps exactly its raw energy: the kernel acts on x′ and y′ only."""
    bundle = framed["bundle"]
    grid = bundle.grid
    gauss = reconstruct.choose_kernel(MODE_CONTINUOUS, bundle.n_events)
    reach = (gauss.reach_bins(grid.pitch) + 1) * grid.pitch
    for name, axis in (("yz", "y"), ("xz", "x")):
        edges = grid.axis(axis).edges
        unbounded = window.AxisFit(0, edges.size - 1, float(edges[0]) - reach, float(edges[-1]) + reach, 0.0, True)
        row_map = reconstruct.continuous_axis(edges, unbounded, 400, gauss, grid.pitch)
        col_map = reconstruct.passthrough(grid.axis("z").edges)
        assert col_map.op is None and col_map.n_dst == grid.n_z
        plane = bundle.panel(name).planes["e"]
        energy = reconstruct.apply(plane, row_map, col_map)
        assert energy.sum(axis=0) == pytest.approx(plane.sum(axis=0), rel=1e-12, abs=1e-15)
    out = density.render_canonical(bundle, window.fit_window(bundle), MODE_CONTINUOUS, 150)
    for name in ("yz", "xz"):
        col = out["panels"][name]["axes"]["col"]
        assert col["n"] == grid.n_z and col["name"] == "z"


@pytest.mark.parametrize("mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 150), (MODE_CONTINUOUS, 400)])
def test_below_floor_bins_have_their_own_code_and_are_counted(framed, mode, resolution):
    bundle = framed["bundle"]
    out = density.render_canonical(bundle, window.fit_window(bundle), mode, resolution)
    for name in ("xy", "yz", "xz"):
        payload = out["panels"][name]
        codes = _codes(payload)
        assert payload["below_code"] == 1 and payload["min_code"] == 2 and payload["empty_code"] == 0
        assert int((codes == 1).sum()) == payload["scale"]["clipped_low"] == payload["below_floor_cells"]
        assert int((codes == 0).sum()) == payload["scale"]["empty_cells"]
        assert payload["scale"]["floor"] == "transparent"
        assert payload["scale"]["floor_ratio"] == pytest.approx(1e-3)
        assert 0.0 <= payload["below_floor_energy_fraction"] < 1.0
        assert codes.max() <= 255 and not np.any(codes[codes > 1] < 2)


@pytest.mark.parametrize("mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 90), (MODE_CONTINUOUS, 400)])
def test_the_raw_peak_bounds_the_reconstructed_field(framed, mode, resolution):
    bundle = framed["bundle"]
    out = density.render_canonical(bundle, window.fit_window(bundle), mode, resolution)
    rho = out["rho"]
    for name in ("xy", "yz", "xz"):
        assert out["panels"][name]["scale"]["vmax"] == 0.0, "the selection's own raw peak is the top"
        assert 0.0 < rho["displayed_over_ref"][name] <= 1.0
        assert 0.0 < rho["kernel_attenuation"][name] <= 1.0
        assert rho["displayed_peak"][name] == out["panels"][name]["rho_peak"]
    if mode == MODE_NATIVE:
        assert rho["kernel_attenuation"]["xy"] == pytest.approx(1.0)
    else:
        assert rho["kernel_attenuation"]["xy"] < 1.0, "a Gaussian lowers a two-event peak"
    assert "raw" in rho["basis"] and "before display reconstruction" in rho["basis"]


def test_gradcam_masks_by_display_mode(framed):
    """Native masks only no-hit bins; continuous masks exactly where the
    reconstructed density falls under the floor."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    native = density.render_canonical(bundle, fit, MODE_NATIVE, 150, channel=panels.CHANNEL_GRADCAM)
    for name in ("xy", "yz", "xz"):
        payload = native["panels"][name]
        assert payload["below_floor_cells"] == 0 and not np.any(_codes(payload) == 1)
        assert payload["attention_mask"]["cells"] == 0
        assert payload["attention_mask"]["max_attention"] is None
        assert payload["attention_mask"]["hit_fraction"] == 0.0

    ref = density.selection_peaks(bundle)
    plan = density.plan_canonical(fit, bundle.grid, MODE_CONTINUOUS, 150)
    for name in ("xy", "yz", "xz"):
        rho_ref = ref["xy"] if name == "xy" else ref["depth"]
        rendered = density.render_panel(
            bundle, fit.panel(name), plan, name, panels.CHANNEL_GRADCAM, "energy", rho_ref, "selection"
        )
        payload = rendered.payload
        codes = _codes(payload)
        row_map, col_map = density.axis_maps(bundle, fit.panel(name), plan, name)
        attention = reconstruct.apply_ratio(
            bundle.panel(name).planes["eg"], bundle.panel(name).planes["e"], row_map, col_map
        )
        expected = np.isfinite(attention) & (rendered.density < 1e-3 * rho_ref)
        np.testing.assert_array_equal(codes == 1, expected)
        assert payload["attention_mask"]["cells"] == int(expected.sum()) == payload["below_floor_cells"]
        assert "kernel tails" in payload["attention_mask"]["rule"]
        assert all(cell["value"] >= 0 for cell in payload["topk"])
        masked = {(i, j) for i, j in zip(*np.nonzero(expected))}
        assert not any((cell["i"], cell["j"]) in masked for cell in payload["topk"])


@pytest.mark.parametrize("mode", [MODE_NATIVE, MODE_CONTINUOUS])
def test_an_unattainable_limit_ends_bounded_and_says_so(framed, mode):
    """The guard stops once no step changes the panels, and says they are over.

    Every notice before the last describes a step that changed what is served:
    the native merge stops when every transverse axis is one bin - merging
    further used to append notices for merges that changed nothing - and its
    warning quotes the width the merged bins actually have.
    """
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, mode, 150, limit=1)
    notices = out["notices"]
    assert notices and "served as they are" in notices[-1]
    assert len(notices) <= density.MAX_ATTEMPTS
    assert out["guard"]["fits"] is False
    if mode == MODE_NATIVE:
        merges = [n for n in notices if n.startswith("Transverse bins merged")]
        merge = out["resolution"]["merge"]
        assert merge == 2 ** len(merges)
        shapes = out["resolution"]["shapes"]
        assert shapes["xy"] == [1, 1] and shapes["yz"][0] == 1 and shapes["xz"][0] == 1
        # The smallest merge that collapses every axis: no no-op merge was taken.
        widest = max(fit.xy.row.n_bins, fit.xy.col.n_bins, fit.yz.row.n_bins, fit.xz.row.n_bins)
        assert merge // 2 < widest <= merge
        assert "single bin" in notices[-1]
        span = fit.xy.col.hi - fit.xy.col.lo
        assert out["resolution"]["display_pitch_mm"] == pytest.approx(span)
        assert f"{merge}x" in out["resolution"]["warnings"][0]
        assert f"{merge * 20:,} mm display bins" not in out["resolution"]["warnings"][0]
    else:
        assert out["resolution"]["r_x"] == 16
        assert "minimum resolution" in notices[-1]
    assert out["resolution"]["r_z"] == framed["grid"].n_z


def test_a_higher_requested_resolution_never_serves_a_coarser_picture(framed):
    """The guard lands on the default R instead of stepping over it.

    From R = 400 the quarter steps run 400, 300, 225, 168, 126 and pass 150 by,
    so a request for more detail could be served coarser than the default
    request (production v37, D 20-40 mm: 126 against 150). With a limit that
    R = 150 just meets, every request at or above it serves at least 150.
    """
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    at_default = density.render_canonical(bundle, fit, MODE_CONTINUOUS, 150, limit=10**9)
    limit = at_default["guard"]["bytes"]
    assert density.render_canonical(bundle, fit, MODE_CONTINUOUS, 150, limit=limit)["guard"]["r"] == 150
    for requested in (160, 200, 300, 400, 512):
        out = density.render_canonical(bundle, fit, MODE_CONTINUOUS, requested, limit=limit)
        assert out["guard"]["fits"] and out["resolution"]["r_x"] >= 150, requested
        assert out["resolution"]["requested"] == requested
    assert density.next_resolution(400, 400) == 300
    assert density.next_resolution(168, 400) == 150
    assert density.next_resolution(150, 400) == 112
    assert density.next_resolution(100, 100) == 75


def test_attempts_whose_rasters_cannot_fit_are_not_rendered(framed, monkeypatch):
    """An attempt is rendered only if it could fit, or if it is the one served."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    calls = []
    original = density.render_panel

    def counting(*args, **kwargs):
        calls.append(args[2].xy)
        return original(*args, **kwargs)

    monkeypatch.setattr(density, "render_panel", counting)
    served = density.render_canonical(bundle, fit, MODE_CONTINUOUS, 150, limit=10**9)
    limit = served["guard"]["bytes"]
    calls.clear()
    out = density.render_canonical(bundle, fit, MODE_CONTINUOUS, 512, limit=limit)
    assert out["resolution"]["r_x"] >= 150
    rendered_shapes = {shape for shape in calls}
    for shape in rendered_shapes:
        plan = density.plan_canonical(fit, bundle.grid, MODE_CONTINUOUS, shape[1])
        assert density.raster_bytes(plan) <= limit or shape[1] == out["resolution"]["r_x"]
    skipped = [n for n in out["notices"] if "rasters alone" in n]
    assert skipped, "a step past an attempt too large to fit must still be disclosed"


def test_an_incremental_continuous_render_is_fast(framed):
    """A display change re-renders the cached bundle; it must stay interactive."""
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        density.render_canonical(bundle, fit, MODE_CONTINUOUS, 150)
        timings.append((time.perf_counter() - started) * 1000.0)
    assert float(np.median(timings)) < 50.0


def test_the_reconstruction_block_names_what_was_done(framed):
    bundle = framed["bundle"]
    fit = window.fit_window(bundle)
    cont = density.render_canonical(bundle, fit, MODE_CONTINUOUS, 150)["reconstruction"]
    assert cont["display"] == "continuous" and cont["kernel"] == "gaussian"
    assert cont["sigma_mm"] == 10.0 and cont["bin_spread_rms_mm"] == pytest.approx(11.547, abs=1e-3)
    assert cont["gaussian_below_n"] == 50 and cont["axes"] == ["x′", "y′"]
    assert cont["depth"].startswith("native sampling layers") and cont["conservative"] is True
    assert cont["subsample_k"] == bundle.subsample_k
    k = bundle.subsample_k
    expected_x = reconstruct.blur_rms(
        bundle.footprint[0], k, kernel_mod.gaussian(10.0).bin_spread_rms(20.0), 20.0
    )
    assert cont["blur_rms_mm"]["x"] == pytest.approx(expected_x, abs=1e-3)
    assert set(cont["below_floor"]) == {"xy", "yz", "xz"}
    assert "N = 2" in cont["note"] and "σ = 10 mm" in cont["note"]
    native = density.render_canonical(bundle, fit, MODE_NATIVE, 150)
    block = native["reconstruction"]
    assert block["kernel"] == "none" and block["sigma_mm"] is None
    assert native["resolution"]["kernel"]["type"] == "none"
    assert block["note"].startswith("Native Grid")


def _canonical_body(cursor, record, ingested, **overrides):
    from calosrv.api import frame_canonical
    from calosrv.models.common import Timer

    params = dict(
        resolution=150, display=MODE_CONTINUOUS, channel=panels.CHANNEL_DENSITY,
        weighting="energy", rho_norm="selection", preview=False, timer=Timer(),
    )
    params.update(overrides)
    return frame_canonical.build_response(
        cursor, record, filters.build(record), ingested["settings"], **params
    )


def test_a_sampled_continuous_preview_is_approximate_and_fits_the_budget(
    cursor, record, ingested, monkeypatch
):
    """A smoke test of the drag preview in Continuous Field.

    It is marked approximate, its sub-cell factor is capped for speed, its
    kernel follows the event count of the event table (the only count the
    bundle carries, sampled or not), and it stays inside the wire budget.
    """
    from calosrv.query import sampling

    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    body = _canonical_body(cursor, record, ingested, preview=True)
    assert body["meta"]["exact"] is False
    assert body["meta"]["warnings"], "the sampling must be disclosed"
    assert body["frame"]["subsample_k"] <= frame.PREVIEW_MAX_SUBSAMPLE
    assert body["frame"]["n_events"] == 2
    assert body["frame"]["reconstruction"]["kernel"] == "gaussian"
    assert body["meta"]["resolution"]["kernel"]["type"] == "gaussian"
    assert density.wire_size(body) < 100_000


def _resolution_notices(body):
    return [n["text"] for n in body["meta"]["notices"] if n["scope"] == "resolution"]


def test_a_response_still_over_after_the_rerender_says_so_and_ends(
    cursor, record, ingested, monkeypatch
):
    """An unattainable whole-response limit: the re-render continues the
    guard's sequence from the state it served, runs out of steps at the
    minimum R, and the response is served with both facts stated - after a
    bounded number of attempts."""
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 5_000)
    body = _canonical_body(cursor, record, ingested)
    texts = _resolution_notices(body)
    budget = [t for t in texts if t.startswith("The whole response measured")]
    assert len(budget) == 1 and "re-rendered from the cached bundle" in budget[0]
    lowered = [t for t in texts if t.startswith("Resolution lowered")]
    assert 0 < len(lowered) <= 2 * density.MAX_ATTEMPTS
    # The resumed pass starts where the first one stopped: no R is stepped from twice.
    starts = [int(t.split("from R = ")[1].split(" ")[0]) for t in lowered]
    assert len(starts) == len(set(starts))
    assert texts[-1].startswith("The response is still") and texts[-1].endswith("served as it is.")
    minimum = body["meta"]["resolution"]["r_x"]
    assert minimum == 16 and f"at the minimum resolution R = {minimum}" in texts[-1]


def test_the_whole_response_check_never_serves_a_higher_request_coarser(
    cursor, record, ingested, monkeypatch
):
    """The whole-response re-render measures each candidate as it is served.

    It used to compare the panel guard's over-counted measure with a limit
    taken from the compact wire size, and so stepped past states that fit: on
    production v37, D 20-40 mm, R = 150 serves 98,377 B, yet every request
    above 150 came back at R = 112. Here the panel guard is lifted, so the
    whole-response check does all the stepping, and the contract is set just
    above what R = 150 needs, with room for the extra notices a stepped-down
    request carries.
    """
    monkeypatch.setattr(density, "PAYLOAD_LIMIT", 10**9)
    at_default = density.wire_size(_canonical_body(cursor, record, ingested))
    monkeypatch.setattr(density, "RESPONSE_LIMIT", at_default + 2_000)
    for requested in (225, 300, 400):
        body = _canonical_body(cursor, record, ingested, resolution=requested)
        assert density.wire_size(body) < density.RESPONSE_LIMIT, requested
        assert body["meta"]["resolution"]["r_x"] >= 150, requested
        texts = _resolution_notices(body)
        lowered = [t for t in texts if t.startswith("Resolution lowered")]
        assert lowered, f"R = {requested} over the contract must be stepped down and say so"
        starts = [int(t.split("from R = ")[1].split(" ")[0]) for t in lowered]
        assert len(starts) == len(set(starts)), "an R was stepped from twice"


def test_a_panel_guard_that_already_failed_is_not_rerun(cursor, record, ingested, monkeypatch):
    """If the panels could not meet their own, looser limit, a tighter one cannot help."""
    monkeypatch.setattr(density, "PAYLOAD_LIMIT", 1)
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 5_000)
    body = _canonical_body(cursor, record, ingested)
    texts = _resolution_notices(body)
    budget = [t for t in texts if t.startswith("The whole response measured")]
    assert len(budget) == 1 and "already failed its own limit" in budget[0]
    assert sum("served as they are" in t for t in texts) == 1
    assert body["meta"]["resolution"]["r_x"] == 16


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
