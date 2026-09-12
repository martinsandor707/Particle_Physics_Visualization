"""Lattice geometry and area-weighted resampling.

These are the properties the whole spatial display rests on, and they are
checked against a deliberately *irregular* synthetic lattice modelled on the
real one - tight cell pairs 4.4 mm apart with an alternating group pitch -
because a uniform lattice would let a broken implementation pass.
"""

from __future__ import annotations

import numpy as np
import pytest

from calosrv.grid.lattice import Axis, Lattice
from calosrv.grid.resolution import (
    MODE_CONTINUOUS,
    MODE_NATIVE,
    plan_resolution,
)
from calosrv.grid.slab import slab_layer_count
from calosrv.grid.splat import build_axis_operator, overlap_matrix, resample, resample_ratio


def irregular_x(n_pairs: int = 106) -> Axis:
    """An x axis shaped like the real one: paired cells, alternating pitch."""
    coords = []
    position = -2596.0
    for group in range(n_pairs):
        coords += [position, position + 4.4]
        position += 43.87 if group % 2 else 48.27
    return Axis("x", np.array(coords))


def uniform_z(n: int = 60, pitch: float = 20.5) -> Axis:
    return Axis("z", 3662.4 + pitch * np.arange(n))


def test_irregular_axis_is_detected():
    assert irregular_x().is_uniform is False
    assert uniform_z().is_uniform is True


def test_edges_tile_contiguously():
    """Cell boundaries must abut exactly: no gaps, no overlaps.

    This is what makes the native view comb-free and the splat conservative.
    """
    axis = irregular_x()
    edges = axis.edges
    assert edges.size == axis.n + 1
    assert np.all(np.diff(edges) > 0)
    # Every cell centre lies strictly inside its own cell.
    assert np.all(edges[:-1] < axis.coords)
    assert np.all(axis.coords < edges[1:])


def test_index_of_round_trips_every_cell():
    """Each real coordinate must map back to its own ordinal index."""
    axis = irregular_x()
    assert np.array_equal(axis.index_of(axis.coords), np.arange(axis.n))


def test_overlap_operator_columns_sum_to_one():
    axis = irregular_x()
    operator = build_axis_operator(axis.edges, 200, native=False)
    assert np.allclose(operator.sum(axis=0), 1.0)


@pytest.mark.parametrize("r", [30, 60, 104, 150, 200, 250, 512])
def test_resampling_conserves_energy(r):
    """An extensive quantity must survive resampling at any resolution."""
    rng = np.random.default_rng(0)
    axis = irregular_x()
    rows = Axis("y", np.linspace(-2600, 2600, 104))
    matrix = rng.random((rows.n, axis.n)) * 1e-3
    matrix[rng.random(matrix.shape) < 0.7] = 0.0

    col_op = build_axis_operator(axis.edges, r, native=False)
    row_op = build_axis_operator(rows.edges, max(1, round(r * rows.n / axis.n)), native=False)
    out = resample(matrix, row_op, col_op)

    assert out.sum() == pytest.approx(matrix.sum(), rel=1e-12)


@pytest.mark.parametrize("r", [60, 150, 200, 512])
def test_no_structurally_empty_columns(r):
    """Splatting must never picket-fence, even when R exceeds the lattice.

    A uniformly populated source resampled to any R must leave no destination
    column empty; point binning fails this as soon as R exceeds the cell count.
    """
    axis = irregular_x()
    matrix = np.ones((4, axis.n))
    col_op = build_axis_operator(axis.edges, r, native=False)
    out = resample(matrix, None, col_op)
    assert int((out.sum(axis=0) == 0).sum()) == 0


def test_ratio_resampling_preserves_a_constant_field():
    """An intensive quantity must not be distorted by resampling."""
    rng = np.random.default_rng(1)
    axis = irregular_x()
    weights = rng.random((8, axis.n))
    numerator = weights * 0.42
    col_op = build_axis_operator(axis.edges, 173, native=False)
    out = resample_ratio(numerator, weights, None, col_op)
    finite = out[np.isfinite(out)]
    assert np.allclose(finite, 0.42)


def test_ratio_is_energy_weighted_not_a_mean_of_means():
    """Two source cells with very different weights must not count equally.

    One cell holds almost all the energy with attention 1.0; its neighbour holds
    a trace with attention 0.0. Merged, the answer must be ~1.0 (energy
    weighted), not 0.5 (the mean of the two means).
    """
    axis = Axis("x", np.array([0.0, 10.0]))
    energy = np.array([[1.0, 1e-6]])
    attention_numerator = np.array([[1.0, 0.0]])
    col_op = build_axis_operator(axis.edges, 1, native=False)
    out = resample_ratio(attention_numerator, energy, None, col_op)
    assert out[0, 0] == pytest.approx(1.0, abs=1e-5)


def test_native_plan_uses_the_lattice_itself():
    lattice = Lattice(
        x=irregular_x(), y=Axis("y", np.linspace(-2600, 2600, 104)),
        z=uniform_z(), slab_mm=120.0, slab_iz=5,
    )
    plan = plan_resolution(lattice, MODE_NATIVE, 150)
    assert (plan.r_x, plan.r_y, plan.r_z) == (lattice.x.n, 104, 60)
    assert plan.shape_xy == (104, lattice.x.n)


def test_continuous_plan_scales_transverse_and_locks_depth():
    """R drives the transverse axes together; depth stays at the native layers."""
    lattice = Lattice(
        x=irregular_x(), y=Axis("y", np.linspace(-2600, 2600, 104)),
        z=uniform_z(), slab_mm=120.0, slab_iz=5,
    )
    plan = plan_resolution(lattice, MODE_CONTINUOUS, 200)
    assert plan.r_x == 200
    assert plan.r_y == round(200 * 104 / lattice.x.n)
    assert plan.r_z == 60
    assert any("Depth is locked" in w for w in plan.warnings)


def test_entrance_slab_is_six_layers_at_the_real_pitch():
    """120 mm at a 20.5 mm pitch covers layers 0-5; layer 6 is at 123 mm."""
    assert slab_layer_count(uniform_z().coords, 120.0) == 5


def test_slab_never_collapses_to_nothing():
    """A slab narrower than one pitch still keeps the entrance layer."""
    assert slab_layer_count(uniform_z().coords, 1.0) == 0
