"""The display-reconstruction kernels and the symmetric window rule, without a database.

Every property the canonical Continuous Field relies on is pinned here: the
operators are non-negative and conservative, a flat field stays flat, nothing
drawn can exceed the raw peak, slicing the source to the kernel's reach is
exact, and the float64 guard holds when float32 edges come in.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.grid import frame, kernel as kernel_mod, splat
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from calosrv.query import reconstruct, window

PITCH = frame.CANONICAL_PITCH_MM
KERNELS = [kernel_mod.NONE, kernel_mod.BOX, kernel_mod.BILINEAR, kernel_mod.gaussian(10.0)]
SMOOTHING = [kernel_mod.BILINEAR, kernel_mod.gaussian(10.0)]


def _grid(half: float, pitch: float = PITCH) -> np.ndarray:
    return splat.uniform_edges(-half, half, int(round(2 * half / pitch)))


def _unbounded(src: np.ndarray, kern, n_dst: int = 311) -> np.ndarray:
    """Destination edges reaching past the kernel's whole support."""
    reach = (kern.reach_bins(PITCH) + 1) * PITCH
    return splat.uniform_edges(float(src[0]) - reach, float(src[-1]) + reach, n_dst)


# ------------------------------------------------------------ primitives --


def test_erfcc_is_accurate_and_monotone():
    """Numerical Recipes erfcc: fractional error below 1.2e-7 on [-9, 9]."""
    x = np.linspace(-9.0, 9.0, 20001)
    reference = np.array([math.erfc(v) for v in x])
    approx = kernel_mod.erfcc(x)
    assert np.max(np.abs(approx - reference) / reference) < 1.2e-7
    assert np.all(np.diff(approx) <= 0.0)
    assert kernel_mod.erfcc(0.0) == pytest.approx(1.0, abs=1.2e-7)


def test_psi_tilde_is_the_non_linear_part_of_the_normal_antiderivative():
    """psi(u) = u Phi(u) + phi(u) = max(u, 0) + psi~(u), and psi~ vanishes past 9."""
    u = np.linspace(-6.0, 6.0, 241)
    phi = np.exp(-0.5 * u * u) / math.sqrt(2 * math.pi)
    cdf = 0.5 * np.array([math.erfc(-v / math.sqrt(2)) for v in u])
    psi = u * cdf + phi
    assert np.allclose(np.maximum(u, 0.0) + kernel_mod.psi_tilde(u), psi, atol=1e-7)
    assert kernel_mod.psi_tilde(9.0) == 0.0 and kernel_mod.psi_tilde(-12.0) == 0.0
    assert kernel_mod.psi_tilde(0.0) == pytest.approx(1 / math.sqrt(2 * math.pi))


def test_tent_cdf_is_the_integral_of_the_unit_tent():
    u = np.array([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 3.0])
    assert kernel_mod.tent_cdf(u) == pytest.approx([0.0, 0.0, 0.125, 0.5, 0.875, 1.0, 1.0])


# --------------------------------------------------------------- operators --


@pytest.mark.parametrize("kern", KERNELS, ids=lambda k: k.name)
def test_columns_telescope_to_one_and_entries_are_non_negative(kern):
    src = _grid(400.0)
    weights = kernel_mod.operator(src, _unbounded(src, kern), kern)
    assert weights.dtype == np.float64
    assert weights.min() >= 0.0
    assert np.max(np.abs(weights.sum(axis=0) - 1.0)) < 1e-12


@pytest.mark.parametrize("kern", KERNELS, ids=lambda k: k.name)
def test_energy_is_conserved_on_an_unbounded_destination(kern):
    rng = np.random.default_rng(11)
    rows, cols = _grid(300.0), _grid(500.0)
    energy = rng.gamma(0.4, 1.0, size=(rows.size - 1, cols.size - 1))
    out = splat.resample(
        energy,
        kernel_mod.operator(rows, _unbounded(rows, kern, 173), kern),
        kernel_mod.operator(cols, _unbounded(cols, kern, 257), kern),
    )
    assert out.sum() == pytest.approx(energy.sum(), rel=1e-12)
    assert out.min() >= 0.0


def test_a_vanishing_sigma_reduces_the_gaussian_to_the_box():
    src = _grid(300.0)
    dst = splat.uniform_edges(-333.0, 333.0, 97)
    box = splat.overlap_matrix(src, dst)
    assert np.max(np.abs(kernel_mod.operator(src, dst, kernel_mod.gaussian(1e-9)) - box)) < 1e-10
    np.testing.assert_array_equal(kernel_mod.operator(src, dst, kernel_mod.BOX), box)
    np.testing.assert_array_equal(kernel_mod.operator(src, dst, kernel_mod.NONE), box)


def test_the_tent_is_linear_interpolation_through_the_bin_centres():
    """Integrated over sub-bins aligned to the knots, the tent is exactly the
    trapezoid of ``np.interp`` through the bin-centre densities."""
    rng = np.random.default_rng(5)
    src = _grid(200.0)
    energy = rng.uniform(0.1, 3.0, size=src.size - 1)
    centres = 0.5 * (src[:-1] + src[1:])
    density = energy / PITCH
    dst = np.linspace(centres[0], centres[-1], 4 * (centres.size - 1) + 1)
    mean_density = (kernel_mod.operator(src, dst, kernel_mod.BILINEAR) @ energy) / np.diff(dst)
    interp = np.interp(dst, centres, density)
    assert mean_density == pytest.approx(0.5 * (interp[:-1] + interp[1:]), rel=1e-12)


def test_the_displayed_field_never_exceeds_the_raw_peak():
    """Non-negative partitions of unity: every displayed bin is a weighted mean
    of raw densities, so the raw 20 mm-grid peak bounds the picture."""
    rng = np.random.default_rng(2026)
    rows, cols = _grid(400.0), _grid(600.0)
    raw_area = PITCH * PITCH
    for r in (7, 33, 150, 512):
        lo_x, hi_x = -310.0, 290.0
        pitch = (hi_x - lo_x) / r
        n_y = max(1, int(round(500.0 / pitch)))
        dst_x = splat.uniform_edges(lo_x, hi_x, r)
        dst_y = splat.uniform_edges(-260.0, 240.0, n_y)
        area = np.outer(np.diff(dst_y), np.diff(dst_x))
        ops = [
            (kernel_mod.operator(rows, dst_y, k), kernel_mod.operator(cols, dst_x, k))
            for k in (kernel_mod.BOX, kernel_mod.BILINEAR, kernel_mod.gaussian(10.0))
        ]
        for _ in range(100):
            energy = rng.gamma(0.3, 1.0, size=(rows.size - 1, cols.size - 1))
            raw_peak = energy.max() / raw_area
            for row_op, col_op in ops:
                shown = splat.resample(energy, row_op, col_op) / area
                assert shown.max() <= raw_peak * (1 + 1e-12)


@pytest.mark.parametrize(
    "kern,expected", [(kernel_mod.BOX, 5.7735), (kernel_mod.BILINEAR, 8.165), (kernel_mod.gaussian(10.0), 11.547)],
    ids=lambda v: getattr(v, "name", str(v)),
)
def test_the_spread_per_bin_matches_the_second_moment(kern, expected):
    assert kern.bin_spread_rms(PITCH) == pytest.approx(expected, abs=1e-3)
    src = np.array([-10.0, 10.0])
    dst = splat.uniform_edges(-150.0, 150.0, 6000)
    weights = kernel_mod.operator(src, dst, kern)[:, 0]
    centres = 0.5 * (dst[:-1] + dst[1:])
    second = float(weights @ centres ** 2) + (dst[1] - dst[0]) ** 2 / 12.0
    assert math.sqrt(second) == pytest.approx(expected, abs=2e-3)


@pytest.mark.parametrize("pitch", [3.0, 7.3, 20.0, 26.0])
@pytest.mark.parametrize("kern", SMOOTHING, ids=lambda k: k.name)
def test_a_flat_field_stays_flat(kern, pitch):
    src = _grid(1000.0)
    n = int(600.0 // pitch)
    dst = splat.uniform_edges(-300.0, -300.0 + n * pitch, n)
    energy = np.full((src.size - 1, src.size - 1), 2.5 * PITCH * PITCH)
    op = kernel_mod.operator(src, dst, kern)
    density = splat.resample(energy, op, op) / np.outer(np.diff(dst), np.diff(dst))
    assert density == pytest.approx(np.full(density.shape, 2.5), rel=1e-12)


def test_the_tent_refuses_an_irregular_source():
    """Bilinear interpolation needs a pitch; the lab lattice has none."""
    irregular = np.array([0.0, 4.4, 48.27, 52.67, 96.54])
    with pytest.raises(ValueError, match="uniform"):
        kernel_mod.operator(irregular, np.linspace(0, 96, 11), kernel_mod.BILINEAR)
    # The Gaussian is defined on any tiling, like the box.
    assert kernel_mod.operator(irregular, np.linspace(0, 96, 11), kernel_mod.gaussian(10.0)).min() >= 0


@pytest.mark.parametrize("kern", SMOOTHING, ids=lambda k: k.name)
def test_a_normalised_convolution_keeps_attention_bounded(kern):
    rng = np.random.default_rng(3)
    rows, cols = _grid(200.0), _grid(300.0)
    den = rng.gamma(0.5, 1.0, size=(rows.size - 1, cols.size - 1))
    num = rng.uniform(0.0, 1.0, size=den.shape) * den
    row_op = kernel_mod.operator(rows, splat.uniform_edges(-180, 180, 47), kern)
    col_op = kernel_mod.operator(cols, splat.uniform_edges(-260, 260, 71), kern)
    ratio = splat.resample_ratio(num, den, row_op, col_op)
    finite = ratio[np.isfinite(ratio)]
    assert finite.size and finite.min() >= 0.0 and finite.max() <= 1.0 + 1e-12
    constant = splat.resample_ratio(0.37 * den, den, row_op, col_op)
    assert constant[np.isfinite(constant)] == pytest.approx(0.37, rel=1e-12)


@pytest.mark.parametrize("kern", SMOOTHING, ids=lambda k: k.name)
def test_slicing_the_source_to_the_reach_is_exact(kern):
    full = _grid(1010.0)
    lo, hi = 40, 61
    dst = splat.uniform_edges(float(full[lo]), float(full[hi]), 57)
    reach = kern.reach_bins(PITCH)
    whole = kernel_mod.operator(full, dst, kern)
    sliced = kernel_mod.operator(full[lo - reach:hi + reach + 1], dst, kern)
    np.testing.assert_array_equal(whole[:, lo - reach:hi + reach], sliced)
    assert not whole[:, :lo - reach].any() and not whole[:, hi + reach:].any()


@pytest.mark.parametrize("kern", KERNELS, ids=lambda k: k.name)
def test_float32_edges_take_the_float64_path(kern):
    """Guard 3: psi~ cancels in the tails, so nothing may run in float32."""
    src = np.linspace(-500.0, 500.0, 51, dtype=np.float32)
    dst = np.linspace(-333.3, 333.3, 77, dtype=np.float32)
    from32 = kernel_mod.operator(src, dst, kern)
    from64 = kernel_mod.operator(src.astype(np.float64), dst.astype(np.float64), kern)
    assert from32.dtype == np.float64
    np.testing.assert_array_equal(from32, from64)
    assert kernel_mod.erfcc(np.float32(0.3)).dtype == np.float64
    assert kernel_mod.psi_tilde(np.float32(0.3)).dtype == np.float64


def test_kernel_descriptors():
    g = kernel_mod.gaussian(10.0)
    assert g.as_dict(PITCH) == {
        "type": "gaussian", "sigma_mm": 10.0, "bin_spread_rms_mm": 11.547,
        "separable": True, "conservative": True, "non_negative": True,
    }
    assert kernel_mod.NONE.as_dict(40.0)["bin_spread_rms_mm"] == pytest.approx(40 / math.sqrt(12), abs=1e-3)
    assert [k.reach_bins(PITCH) for k in KERNELS] == [0, 0, 1, 6]
    assert g.label() == "Gaussian σ = 10 mm" and kernel_mod.BILINEAR.label() == "bilinear (tent)"
    assert g.smooths and kernel_mod.BILINEAR.smooths and not kernel_mod.NONE.smooths
    with pytest.raises(ValueError):
        kernel_mod.gaussian(0.0)
    with pytest.raises(ValueError):
        kernel_mod.Kernel("bicubic")
    with pytest.raises(ValueError):
        kernel_mod.Kernel("bilinear", 5.0)


# ------------------------------------------------------------------ policy --


def test_the_kernel_follows_the_display_mode_and_the_event_count():
    assert reconstruct.choose_kernel(MODE_NATIVE, 5) is kernel_mod.NONE
    assert reconstruct.choose_kernel(MODE_NATIVE, 20_000) is kernel_mod.NONE
    below = reconstruct.choose_kernel(MODE_CONTINUOUS, frame.GAUSSIAN_KERNEL_BELOW_N - 1)
    assert below.name == "gaussian" and below.sigma_mm == frame.SMOOTH_SIGMA_MM == 10.0
    assert reconstruct.choose_kernel(MODE_CONTINUOUS, frame.GAUSSIAN_KERNEL_BELOW_N) is kernel_mod.BILINEAR


def test_blur_adds_the_discrete_footprint_the_binning_and_the_kernel():
    """k sub-deposits w/k apart: variance w^2 (1 - 1/k^2) / 12, not w^2 / 12;
    plus p^2 / 12 for the point binning of each sub-deposit; plus the kernel's
    own spread per bin."""
    spread = kernel_mod.BILINEAR.bin_spread_rms(PITCH)
    expected = math.sqrt(48.6 ** 2 * (1 - 1 / 4) / 12 + PITCH ** 2 / 12 + spread ** 2)
    assert reconstruct.blur_rms(48.6, 2, spread, PITCH) == pytest.approx(expected)
    # One deposit at the cell centre: only the binning and the kernel remain.
    assert reconstruct.blur_rms(48.6, 1, spread, PITCH) == pytest.approx(
        math.sqrt(PITCH ** 2 / 12 + spread ** 2)
    )


@pytest.mark.parametrize("kern", [kernel_mod.BOX, kernel_mod.BILINEAR, kernel_mod.gaussian(10.0)])
@pytest.mark.parametrize("k", [2, 4])
def test_blur_matches_a_monte_carlo_of_rotated_cells(kern, k):
    """The payload's blur is what one cell's energy actually spreads to.

    Cells of the measured 48.27 mm footprint are split into k x k sub-deposits
    exactly as the canonical scan does, rotated and placed at random, and
    point-binned to the 20 mm grid with ``floor``. A symmetric kernel draws a
    bin's energy with mean at its centre and variance ``bin_spread_rms^2``,
    so the displayed second moment about the cell centre is the mean squared
    distance of the bin centres plus that variance. Without the binning term
    the formula runs 5-8% low of this.
    """
    rng = np.random.default_rng(7)
    width, cells = 48.27, 20_000
    offsets = ((np.arange(k) + 0.5) / k - 0.5) * width
    gx, gy = (grid.ravel() for grid in np.meshgrid(offsets, offsets))
    centre = rng.uniform(-PITCH, PITCH, cells)[:, None]
    angle = rng.uniform(0.0, 2.0 * math.pi, cells)[:, None]
    position = centre + np.cos(angle) * gx - np.sin(angle) * gy
    bin_centre = (np.floor(position / PITCH) + 0.5) * PITCH
    spread = kern.bin_spread_rms(PITCH)
    measured = math.sqrt(float(np.mean((bin_centre - centre) ** 2)) + spread ** 2)
    assert reconstruct.blur_rms(width, k, spread, PITCH) == pytest.approx(measured, rel=0.01)


@pytest.mark.parametrize("kern", [kernel_mod.BOX, kernel_mod.BILINEAR, kernel_mod.gaussian(10.0)])
def test_the_box_overlap_blur_matches_a_monte_carlo_of_the_scan_operator(kern):
    """The translated frame's exact box overlap still pays the p^2/12 binning term.

    Boxes of the 48.27 mm footprint are placed at random continuous positions
    and spread over the 20 mm grid by the scan's own ``box_overlap_operator``;
    the displayed second moment about the box centre is the overlap-weighted
    mean squared distance of the bin centres plus the kernel's spread.
    """
    from calosrv.query.shower_frames import box_overlap_operator

    rng = np.random.default_rng(11)
    width, n_bins, half = 48.27, 40, 400.0
    centres = rng.uniform(-100.0, 100.0, 20_000)
    u = (centres - 0.5 * width + half) / PITCH
    j0 = np.floor(u)
    phi = u - j0
    r = width / PITCH - math.floor(width / PITCH)
    keys = (2 * j0 + (phi >= 1.0 - r)).astype(np.int64)
    a_mat, b_mat = box_overlap_operator(n_bins, width, PITCH, int(keys.min()), int(keys.max()))
    weights = a_mat[:, keys - keys.min()] + b_mat[:, keys - keys.min()] * phi  # (bins, boxes)
    bin_centres = -half + (np.arange(n_bins) + 0.5) * PITCH
    second = float(np.mean((weights * (bin_centres[:, None] - centres[None, :]) ** 2).sum(0)))
    spread = kern.bin_spread_rms(PITCH)
    measured = math.sqrt(second + spread ** 2)
    assert reconstruct.blur_rms(width, None, spread, PITCH) == pytest.approx(measured, rel=0.01)


# ---------------------------------------------------------------- windows --


EDGES = splat.uniform_edges(-200.0, 200.0, 20)


def _marginal(bins: dict[int, float], n: int = 20) -> np.ndarray:
    w = np.zeros(n)
    for index, value in bins.items():
        w[index] = value
    return w


def test_symmetric_window_is_centred_on_the_origin():
    # Energy in [-40, 80]: the larger excursion (80 mm) sets both sides.
    axis = window.symmetric_axis(_marginal({8: 1, 9: 3, 10: 5, 11: 3, 12: 2, 13: 1}), EDGES, 20.0, 50.0)
    assert (axis.lo, axis.hi) == (-80.0, 80.0)
    assert (axis.lo_index, axis.hi_index) == (6, 14)
    assert axis.percentile_range == (-40.0, 80.0)
    assert axis.symmetric and axis.applied and not axis.floored and not axis.clamped
    assert axis.half_width == 80.0
    assert axis.energy_fraction_outside == 0.0
    data = axis.as_dict()
    assert data["half_width"] == 80.0 and data["percentile_range"] == [-40.0, 80.0]


def test_symmetric_window_is_floored_and_snapped():
    marginal = _marginal({9: 1, 10: 1})
    floored = window.symmetric_axis(marginal, EDGES, 20.0, 150.0)
    assert (floored.lo, floored.hi) == (-160.0, 160.0) and floored.floored
    fine = splat.uniform_edges(-200.0, 200.0, 40)  # 10 mm bins, 20 mm snap
    w = np.zeros(40)
    w[17:25] = 1.0  # [-30, 50]
    snapped = window.symmetric_axis(w, fine, 10.0, 20.0)
    assert (snapped.lo, snapped.hi) == (-60.0, 60.0)
    assert (snapped.lo_index, snapped.hi_index) == (14, 26)
    assert not snapped.floored


def test_symmetric_window_is_clamped_to_the_accumulation_grid():
    axis = window.symmetric_axis(_marginal({10: 1}), EDGES, 20.0, 300.0)
    assert (axis.lo, axis.hi) == (-200.0, 200.0)
    assert (axis.lo_index, axis.hi_index) == (0, 20)
    assert axis.clamped and axis.floored


def test_symmetric_window_cuts_a_sub_permille_tail_and_counts_it():
    # 0.05% of the energy in the first bin lies below the 0.1st percentile.
    axis = window.symmetric_axis(_marginal({0: 0.5, 9: 499.75, 10: 499.75}), EDGES, 20.0, 40.0)
    assert (axis.lo, axis.hi) == (-40.0, 40.0)
    assert axis.energy_fraction_outside == pytest.approx(0.5 / 1000.0)


def test_an_empty_axis_keeps_the_whole_grid():
    axis = window.symmetric_axis(np.zeros(20), EDGES, 20.0, 100.0)
    assert not axis.applied and (axis.lo, axis.hi) == (-200.0, 200.0)
    assert axis.half_width == 200.0


def test_the_window_floor_follows_the_evidence():
    footprint = (48.27, 48.6)
    assert window.window_floor_mm(5, footprint) == frame.SHOWER_RADIUS_MIN_MM == 200.0
    assert window.window_floor_mm(frame.PROVISIONAL_N - 1, footprint) == 200.0
    assert window.window_floor_mm(frame.PROVISIONAL_N, footprint) == 100.0
    assert window.window_floor_mm(400, (30.0, 30.0)) == 60.0
    assert window.window_floor_mm(400, None) == 2 * PITCH
