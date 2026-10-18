"""The canonical-frame mathematics, checked without a database."""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.grid import frame
from calosrv.grid.lattice import Axis, Lattice


def _lattice(x, y, z):
    return Lattice(
        x=Axis("x", np.asarray(x, dtype=np.float64)),
        y=Axis("y", np.asarray(y, dtype=np.float64)),
        z=Axis("z", np.asarray(z, dtype=np.float64)),
        slab_mm=120.0,
        slab_iz=5,
    )


def test_anchors_land_on_the_x_axis_at_half_the_entry_separation():
    """B -> (+D/2, 0), A -> (-D/2, 0) for any orientation and offset."""
    rng = np.random.default_rng(1)
    ax, ay = rng.uniform(-2000, 2000, 500), rng.uniform(-2000, 2000, 500)
    bx, by = rng.uniform(-2000, 2000, 500), rng.uniform(-2000, 2000, 500)
    params = frame.frame_of(ax, ay, bx, by)

    xa, ya = frame.rotate_xy(ax, ay, params.x0, params.y0, params.psi)
    xb, yb = frame.rotate_xy(bx, by, params.x0, params.y0, params.psi)

    np.testing.assert_allclose(xa, -params.d_entry / 2, atol=1e-9)
    np.testing.assert_allclose(xb, +params.d_entry / 2, atol=1e-9)
    np.testing.assert_allclose(ya, 0.0, atol=1e-9)
    np.testing.assert_allclose(yb, 0.0, atol=1e-9)


def test_the_motion_is_an_isometry():
    """Pairwise distances of a point cloud survive the transform."""
    rng = np.random.default_rng(2)
    pts = rng.normal(size=(200, 2)) * 300 + np.array([800.0, -400.0])
    params = frame.frame_of(700.0, -450.0, 900.0, -300.0)
    x, y = frame.rotate_xy(pts[:, 0], pts[:, 1], params.x0, params.y0, params.psi)

    before = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
    after = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    np.testing.assert_allclose(after, before, atol=1e-9)


def test_directions_rotate_by_the_linear_part_only():
    u = frame.unit_direction([0.3, 0.5], [1.0, -2.0])
    v = frame.rotate_direction(u, [0.7, 0.7])
    np.testing.assert_allclose(np.linalg.norm(v, axis=-1), 1.0, atol=1e-12)
    np.testing.assert_allclose(v[:, 2], u[:, 2], atol=1e-12)
    # A direction along the separation axis becomes +x' exactly.
    psi = 0.9
    along = np.array([[math.cos(psi), math.sin(psi), 0.0]])
    np.testing.assert_allclose(frame.rotate_direction(along, psi), [[1.0, 0.0, 0.0]], atol=1e-12)


def test_back_projection_recovers_the_entry_point_of_a_straight_shower():
    """A shower drifting along (theta, phi) from its entry point back-projects home."""
    z_front = 3662.4
    theta, phi = 0.4, 1.1
    entry = np.array([120.0, -80.0])
    # A "centroid" 300 mm deep along the incident direction.
    depth = 300.0
    centroid = entry + depth * math.tan(theta) * np.array([math.cos(phi), math.sin(phi)])
    x, y = frame.entry_anchor(centroid[0], centroid[1], z_front + depth, theta, phi, z_front)
    assert x == pytest.approx(entry[0], abs=1e-9)
    assert y == pytest.approx(entry[1], abs=1e-9)


def test_footprint_of_a_twinned_axis_is_the_in_row_pitch():
    """Sorted coordinates in 4.4 mm pairs, 48.27 mm between pair members."""
    firsts = np.arange(0, 50) * 48.27
    coords = np.sort(np.concatenate([firsts, firsts + 4.4]))
    assert frame.footprint_axis_width(coords) == pytest.approx(48.27, abs=1e-9)

    # A plain axis: the consecutive gap.
    plain = np.arange(0, 104) * 50.5
    assert frame.footprint_axis_width(plain) == pytest.approx(50.5, abs=1e-9)


def test_footprint_from_occupancy_recovers_the_block_lattice_pitch():
    """Rows in blocks of four, blocks offset 4.4 mm in x: the production structure.

    The sorted union of x coordinates shows 4.4 mm twins, but cells sharing a
    row are 48.27 mm apart and cells sharing a column 48.6 mm apart.
    """
    pitch_x, pitch_y, offset = 48.27, 48.6, 4.4
    cells = []
    for block in range(6):
        for row in range(4):
            iy = block * 4 + row
            for col in range(20):
                cells.append((col * pitch_x + (block % 2) * offset, iy * pitch_y, iy))
    xs = np.array([c[0] for c in cells])
    x_coords = np.unique(np.round(xs, 6))
    y_coords = np.arange(24) * pitch_y
    ix = np.searchsorted(x_coords, np.round(xs, 6))
    iy = np.array([c[2] for c in cells])

    w_x, w_y = frame.footprint_from_occupancy(ix, iy, x_coords, y_coords)
    assert w_x == pytest.approx(pitch_x, abs=1e-6)
    assert w_y == pytest.approx(pitch_y, abs=1e-6)
    # The lattice-only fallback sees the twins and must also land on the pitch here.
    assert frame.footprint_axis_width(x_coords) == pytest.approx(pitch_x, abs=1e-6)


def test_footprint_from_occupancy_matches_an_independent_grouping(record, cursor):
    """Same quantity computed two ways on the demonstration lattice."""
    from calosrv.db import naming
    from calosrv.db.naming import quote

    proj = quote(naming.proj_table(record.table_name))
    cells = cursor.execute(f"SELECT DISTINCT ix, iy FROM {proj}").fetchall()
    xc, yc = record.lattice.x.coords, record.lattice.y.coords
    ix = np.array([c[0] for c in cells])
    iy = np.array([c[1] for c in cells])

    w_x, w_y = frame.footprint_from_occupancy(ix, iy, xc, yc)

    rows: dict[int, list[float]] = {}
    cols: dict[int, list[float]] = {}
    for i, j in cells:
        rows.setdefault(j, []).append(float(xc[i]))
        cols.setdefault(i, []).append(float(yc[j]))

    def adjacent_pitch(groups: dict[int, list[float]]) -> float:
        gaps = np.concatenate([np.diff(np.sort(v)) for v in groups.values() if len(v) > 1])
        gaps = gaps[gaps > 0]
        low = np.percentile(gaps, 5)
        return float(np.median(gaps[(gaps >= 0.9 * low) & (gaps <= 1.25 * low)]))

    assert w_x == pytest.approx(adjacent_pitch(rows), abs=1e-9)
    assert w_y == pytest.approx(adjacent_pitch(cols), abs=1e-9)
    # The demo file is a cut of the same detector, so it must recover the
    # production cell: 48.27 mm in x, 48.6 mm in y.
    assert w_x == pytest.approx(48.27, abs=0.05)
    assert w_y == pytest.approx(48.6, abs=0.05)


def test_window_is_snapped_to_whole_bins_and_covers_the_anchors():
    lattice = _lattice(np.arange(10) * 48.0, np.arange(8) * 48.6, 3662.4 + np.arange(60) * 20.5)
    grid = frame.plan_window(d_entry_max=4227.6, theta_max=0.628, lattice=lattice)
    assert grid.half_x % grid.pitch == pytest.approx(0.0, abs=1e-9)
    assert grid.half_y % grid.pitch == pytest.approx(0.0, abs=1e-9)
    drift = (lattice.z.hi - lattice.z.lo) * math.tan(0.628)
    assert grid.half_y >= drift + frame.SHOWER_MARGIN_MM
    assert grid.half_x >= 4227.6 / 2 + drift + frame.SHOWER_MARGIN_MM
    # Production-scale numbers: M = 1209.5 * tan(0.628) + 500 = 1379.4 mm.
    assert grid.half_x == pytest.approx(3500.0)
    assert grid.half_y == pytest.approx(1380.0)
    assert grid.n_x == 350 and grid.n_y == 138 and grid.n_z == 60
    # Depth is the native layer set, shifted so the front face is zero.
    assert grid.axis("z").coords[0] == pytest.approx(0.0)
    assert grid.axis("z").coords[-1] == pytest.approx(59 * 20.5)
    # Bin centres reproduce the uniform edges through Axis.edges.
    np.testing.assert_allclose(grid.axis("x").edges, grid.x_edges, atol=1e-9)


def test_window_degrades_gracefully_without_kinematics():
    lattice = _lattice([0.0, 48.0], [0.0, 48.6], [3662.4, 3682.9])
    grid = frame.plan_window(None, None, lattice)
    assert grid.half_x >= frame.SHOWER_MARGIN_MM and grid.half_y >= frame.SHOWER_MARGIN_MM


@pytest.mark.parametrize(
    "rows,expected",
    [(22_532_577, 2), (7_500_000, 2), (3_000_000, 3), (1_273_909, 4), (72_776, 6), (0, 6)],
)
def test_subsample_factor_follows_the_row_budget(rows, expected):
    """Never below 2: point-binning was measured to comb even at 20 k events."""
    assert frame.choose_subsample(rows) == expected
    assert frame.MIN_SUBSAMPLE == 2


def test_gapless_subsample_for_the_measured_footprint():
    """A 48.6 mm cell on a 20 mm grid needs k = 4 for a hole-free splat."""
    assert frame.minimum_gapless_subsample(48.6, 20.0) == 4


def test_rayleigh_and_student_t_helpers():
    assert frame.rayleigh_p(20, 0.30) == pytest.approx(math.exp(-1.8))
    assert frame.rayleigh_p(221, 0.21) < 1e-3
    assert frame.rayleigh_p(1, 0.5) is None
    # Shared with the energy panel's table, so the two never disagree.
    assert frame.t_quantile_975(2) == pytest.approx(4.303, abs=1e-3)
    assert frame.t_quantile_975(30) == pytest.approx(2.042, abs=1e-3)
    assert frame.t_quantile_975(1000) == pytest.approx(1.96, abs=1e-2)


# ------------------------------------------------------------------ SE(3) --
#
# The identities the coordinate-transformation audit checked
# (reference_ipynb_notebooks/01_local_coords_vs_calosrv_se3_audit.md, section 1),
# pinned: the notebook's rotation, the D-frame as its theta = 0 special case,
# and the per-shower frames reproducing the file's own columns.


def _random_angles(seed: int, n: int = 500):
    rng = np.random.default_rng(seed)
    return rng.uniform(0.05, 0.63, n), rng.uniform(-math.pi, math.pi, n)


def test_rotation_matrix_is_the_notebooks_r_y_theta_r_z_phi():
    """R = R_y(theta) R_z(phi): the notebook's matrix, entry for entry."""
    theta, phi = _random_angles(11)
    r = frame.rotation_matrix(theta, phi)
    ct, st, cp, sp = np.cos(theta), np.sin(theta), np.cos(phi), np.sin(phi)
    expected = np.empty((theta.size, 3, 3))
    expected[:, 0] = np.stack([ct * cp, ct * sp, -st], axis=-1)
    expected[:, 1] = np.stack([-sp, cp, np.zeros_like(sp)], axis=-1)
    expected[:, 2] = np.stack([st * cp, st * sp, ct], axis=-1)
    np.testing.assert_allclose(r, expected, atol=0.0)
    # Composed from the two elementary passive rotations.
    r_y = np.array([[[c, 0, -s], [0, 1, 0], [s, 0, c]] for c, s in zip(ct, st)])
    r_z = np.array([[[c, s, 0], [-s, c, 0], [0, 0, 1]] for c, s in zip(cp, sp)])
    np.testing.assert_allclose(r, r_y @ r_z, atol=1e-15)


def test_rotation_matrix_sends_the_incident_direction_to_plus_z_and_is_orthonormal():
    theta, phi = _random_angles(12)
    r = frame.rotation_matrix(theta, phi)
    along = np.einsum("nij,nj->ni", r, frame.unit_direction(theta, phi))
    np.testing.assert_allclose(along, np.tile([0.0, 0.0, 1.0], (theta.size, 1)), atol=1e-15)
    np.testing.assert_allclose(r @ np.swapaxes(r, 1, 2), np.tile(np.eye(3), (theta.size, 1, 1)), atol=1e-15)
    np.testing.assert_allclose(np.linalg.det(r), 1.0, atol=1e-14)


def test_the_d_frame_rotation_is_the_notebooks_at_zero_tilt():
    """rotation_matrix(0, psi) applied to (x, y, z) is rotate_xy with psi, and z untouched."""
    rng = np.random.default_rng(13)
    psi = rng.uniform(-math.pi, math.pi, 300)
    pts = rng.normal(size=(300, 3)) * 500
    motion = frame.Se3.about(frame.rotation_matrix(np.zeros_like(psi), psi), np.zeros((300, 3)))
    moved = motion.apply(pts)
    x, y = frame.rotate_xy(pts[:, 0], pts[:, 1], 0.0, 0.0, psi)
    np.testing.assert_allclose(moved[:, 0], x, atol=1e-12)
    np.testing.assert_allclose(moved[:, 1], y, atol=1e-12)
    np.testing.assert_allclose(moved[:, 2], pts[:, 2], atol=0.0)
    # Directions too: the linear part is what rotate_direction applies.
    u = frame.unit_direction(*_random_angles(14, 300))
    np.testing.assert_allclose(motion.apply_direction(u), frame.rotate_direction(u, psi), atol=1e-15)


def test_every_frame_element_is_an_isometry_with_an_exact_inverse():
    rng = np.random.default_rng(15)
    theta, phi = _random_angles(16, 1)
    p0 = rng.normal(size=3) * 1000
    cloud = rng.normal(size=(400, 3)) * 300 + p0
    before = np.linalg.norm(cloud[:, None] - cloud[None, :], axis=-1)
    for motion in (
        frame.per_shower_translated(p0),
        frame.per_shower_local(p0, theta[0], phi[0]),
        frame.per_event_canonical([10.0, -20.0], [410.0, 280.0], 3662.4),
    ):
        moved = motion.apply(cloud)
        after = np.linalg.norm(moved[:, None] - moved[None, :], axis=-1)
        np.testing.assert_allclose(after, before, atol=1e-9)
        np.testing.assert_allclose(motion.inverse().apply(moved), cloud, atol=1e-9)
        np.testing.assert_allclose(motion.apply(motion.anchor), 0.0, atol=1e-9)


def test_the_per_shower_frames_take_p0_to_the_origin_and_tilt_the_first_layer_plane():
    theta, phi = 0.5, -2.0
    p0 = np.array([120.0, -80.0, 3662.4])
    local = frame.per_shower_local(p0, theta, phi)
    translated = frame.per_shower_translated(p0)
    np.testing.assert_allclose(local.apply(p0), 0.0, atol=1e-12)
    np.testing.assert_allclose(translated.apply(p0), 0.0, atol=1e-12)
    # The incident direction is +z' in the local frame and unchanged in the translated one.
    n = frame.unit_direction(theta, phi)
    np.testing.assert_allclose(local.apply_direction(n), [0.0, 0.0, 1.0], atol=1e-15)
    np.testing.assert_allclose(translated.apply_direction(n), n, atol=0.0)
    # Points of the first-layer plane (delta z = 0) lie on z' = tan(theta) x' for every y'.
    rng = np.random.default_rng(17)
    plane = p0 + np.column_stack([rng.normal(size=50) * 200, rng.normal(size=50) * 200, np.zeros(50)])
    moved = local.apply(plane)
    np.testing.assert_allclose(moved[:, 2], math.tan(theta) * moved[:, 0], atol=1e-9)


def test_per_event_canonical_agrees_with_frame_of_and_rotate_xy():
    rng = np.random.default_rng(18)
    a = rng.uniform(-2000, 2000, (100, 2))
    b = rng.uniform(-2000, 2000, (100, 2))
    z_front = 3662.4
    motion = frame.per_event_canonical(a, b, z_front)
    params = frame.frame_of(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    pts = rng.normal(size=(100, 3)) * 500 + np.array([0.0, 0.0, z_front + 300.0])
    moved = motion.apply(pts)
    x, y = frame.rotate_xy(pts[:, 0], pts[:, 1], params.x0, params.y0, params.psi)
    np.testing.assert_allclose(moved[:, 0], x, atol=1e-9)
    np.testing.assert_allclose(moved[:, 1], y, atol=1e-9)
    np.testing.assert_allclose(moved[:, 2], pts[:, 2] - z_front, atol=1e-9)
    # B lands at (+D_entry/2, 0, 0) and A at (-D_entry/2, 0, 0).
    at_b = motion.apply(np.column_stack([b, np.full(100, z_front)]))
    np.testing.assert_allclose(at_b[:, 0], params.d_entry / 2, atol=1e-9)
    np.testing.assert_allclose(at_b[:, 1:], 0.0, atol=1e-9)


def test_the_per_shower_frames_reproduce_the_files_own_columns(record, cursor):
    """The in-NumPy motions, from the laboratory lattice and the event table's
    P0 and (theta, phi), land on the file's x/y_trans and x/y/z_local within
    the ingest tolerance - the same contract verify.py checks in SQL."""
    from calosrv.db import naming
    from calosrv.db.naming import quote
    from calosrv.ingest.verify import ROTATION_TOLERANCE_MM

    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"""SELECT p.ix, p.iy, p.iz, p.org, p.xt, p.yt, p.kt, p.xl, p.yl, p.zl,
                   CASE WHEN p.org = 0 THEN e.p0ax ELSE e.p0bx END,
                   CASE WHEN p.org = 0 THEN e.p0ay ELSE e.p0by END,
                   CASE WHEN p.org = 0 THEN e.p0az ELSE e.p0bz END,
                   CAST(CASE WHEN p.org = 0 THEN e.theta_a ELSE e.theta_b END AS DOUBLE),
                   CAST(CASE WHEN p.org = 0 THEN e.phi_a ELSE e.phi_b END AS DOUBLE)
            FROM {proj} p JOIN {event} e USING (event_number) WHERE e.d IS NOT NULL"""
    ).fetchnumpy()
    lat = record.lattice
    lab = np.column_stack([
        lat.x.coords[np.asarray(rows["ix"], dtype=int)],
        lat.y.coords[np.asarray(rows["iy"], dtype=int)],
        lat.z.coords[np.asarray(rows["iz"], dtype=int)],
    ])
    p0 = np.column_stack([np.asarray(rows[k], dtype=float) for k in rows.keys() if k.startswith("CASE")][:3])
    theta = np.asarray(list(rows.values())[13], dtype=float)
    phi = np.asarray(list(rows.values())[14], dtype=float)
    pitch = record.frame_bounds.layer_pitch_mm

    local = frame.per_shower_local(p0, theta, phi).apply(lab)
    expected_local = np.column_stack([np.asarray(rows[k], dtype=float) for k in ("xl", "yl", "zl")])
    assert np.abs(local - expected_local).max() <= ROTATION_TOLERANCE_MM

    translated = frame.per_shower_translated(p0).apply(lab)
    expected_trans = np.column_stack([
        np.asarray(rows["xt"], dtype=float), np.asarray(rows["yt"], dtype=float),
        np.asarray(rows["kt"], dtype=float) * pitch,
    ])
    assert np.abs(translated - expected_trans).max() <= ROTATION_TOLERANCE_MM
