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
