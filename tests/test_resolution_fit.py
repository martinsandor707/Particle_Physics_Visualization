"""``stats/resolution_fit.py`` and the anchor rules of ``query/resolution_scaling.py``, on bare arrays.

The closed forms are held to ``numpy.linalg.lstsq`` on the ``√w``-scaled
system, their covariance to ``(XᵀWX)⁻¹`` and to a finite-difference
propagation, ``chi2_sf`` to the textbook table and to the two closed forms
(ν = 1, 2). The fits are then run on simulated windows: recovery of the
generating a and b within 3 standard errors, and the coverage of the reported
95% intervals over 400 seeded replicas. The quadrature band, drawn in the
card's E view, is held to √ of a z-band built independently from ``lstsq``, to
its cut at zero and its value at x = 0, to Student's t once S scales it, and to
its coverage of the generating σ/E over 400 replicas. The misfit gate
(``Fit.misfit``: ν ≥ 1 and S > 5) is held just above and just below 5, at ν = 0,
and on a pinned fit through a constant term. Nothing here is a measurement of
the detector.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pytest import approx

from calosrv.query import performance_bins, resolution_scaling as rs
from calosrv.stats import gaussian
from calosrv.stats import resolution_fit as rf


def _system(seed: int = 0, n: int = 9):
    rng = np.random.default_rng(seed)
    x = np.sort(rng.uniform(0.2, 0.5, n))
    y = 0.15 * x + 0.02 + rng.normal(0, 0.004, n)
    w = 1.0 / rng.uniform(0.002, 0.008, n) ** 2
    return x, y, w


# ---------------------------------------------------------- closed forms --


def test_affine_closed_form_matches_lstsq_on_the_scaled_system():
    x, y, w = _system()
    theta, cov = rf.wls_affine(x, y, w)
    design = np.stack([x, np.ones_like(x)], axis=1)
    root = np.sqrt(w)
    expected, *_ = np.linalg.lstsq(design * root[:, None], y * root, rcond=None)
    assert theta == approx(expected, rel=1e-10)
    assert cov == approx(np.linalg.inv(design.T @ (w[:, None] * design)), rel=1e-9)


def test_pinned_closed_form_matches_lstsq_on_the_scaled_system():
    x, y, w = _system(1)
    theta, cov = rf.wls_pinned(x, y, w)
    root = np.sqrt(w)
    expected, *_ = np.linalg.lstsq((x * root)[:, None], y * root, rcond=None)
    assert theta == approx(expected, rel=1e-10)
    assert cov[0, 0] == approx(1.0 / (w * x * x).sum(), rel=1e-12)


@pytest.mark.parametrize("solve", [rf.wls_affine, rf.wls_pinned])
def test_covariance_is_the_propagated_measurement_variance(solve):
    """Σ = J diag(1/w) Jᵀ with J = ∂θ/∂y by central differences: the WLS covariance is exact."""
    x, y, w = _system(2)
    theta, cov = solve(x, y, w)
    h = 1e-6
    jac = np.empty((theta.size, y.size))
    for i in range(y.size):
        up, down = y.copy(), y.copy()
        up[i] += h
        down[i] -= h
        jac[:, i] = (solve(x, up, w)[0] - solve(x, down, w)[0]) / (2 * h)
    assert jac @ np.diag(1.0 / w) @ jac.T == approx(cov, rel=1e-6)


def test_affine_refuses_points_that_share_one_x():
    assert rf.wls_affine(np.array([0.3, 0.3]), np.array([0.1, 0.2]), np.ones(2)) is None
    assert rf.fit_affine([0.3, 0.3], [0.1, 0.12], [50, 60]) is None


# ------------------------------------------------------------------ chi2 --


@pytest.mark.parametrize("x, nu", [(3.841, 1), (5.991, 2), (7.815, 3), (11.070, 5),
                                   (18.307, 10), (31.410, 20)])
def test_chi2_sf_matches_the_table(x, nu):
    assert rf.chi2_sf(x, nu) == approx(0.05, abs=2e-4)


def test_chi2_sf_matches_the_closed_forms_on_both_branches():
    for x in (0.01, 0.5, 1.0, 2.0, 3.0, 8.0, 30.0, 80.0):
        assert rf.chi2_sf(x, 1) == approx(math.erfc(math.sqrt(x / 2)), rel=1e-9, abs=1e-15)
        assert rf.chi2_sf(x, 2) == approx(math.exp(-x / 2), rel=1e-9, abs=1e-15)
    assert rf.chi2_sf(0.0, 3) == 1.0
    assert rf.chi2_sf(1.0, 0) is None


# ------------------------------------------------------------ iteration --


def test_iterated_weights_reach_their_fixed_point():
    """At convergence a refit with se at the fitted value returns the same line."""
    x = 1 / np.sqrt(np.array([5.5, 7.5, 10.5, 14.5, 19.5]))
    r = np.array([0.112, 0.093, 0.083, 0.072, 0.062])
    n = np.array([150, 90, 400, 60, 220])
    fit = rf.fit_affine(x, r, n)
    assert fit.converged and 1 <= fit.iterations < rf.MAX_ITERATIONS
    w = 1.0 / rf.resolution_se(fit.predict(x), n) ** 2
    again, cov = rf.wls_affine(x, r, w)
    assert again == approx(np.array(fit.theta), rel=1e-9)
    assert fit.cov_stat == approx(cov, rel=1e-6)
    assert fit.chi2 == approx(float((w * (r - fit.predict(x)) ** 2).sum()), rel=1e-6)
    assert fit.ndf == 3 and fit.p_value == approx(rf.chi2_sf(fit.chi2, 3))


def test_two_points_have_no_degrees_of_freedom():
    fit = rf.fit_affine([0.25, 0.4], [0.07, 0.09], [100, 100])
    assert fit.ndf == 0 and fit.p_value is None and fit.scale_factor == 1.0
    assert fit.chi2 == approx(0.0, abs=1e-20)
    pinned = rf.fit_pinned([0.3], [0.06], [50])
    assert pinned.ndf == 0 and pinned.theta[0] == approx(0.2)


def test_scale_factor_inflates_errors_and_band_and_keeps_the_stat_ones():
    x = 1 / np.sqrt(np.array([5.5, 8.5, 12.5, 19.5]))
    r = np.array([0.12, 0.07, 0.09, 0.05])            # far from a line at N = 400
    fit = rf.fit_affine(x, r, [400, 400, 400, 400])
    assert fit.chi2 / fit.ndf > 1
    assert fit.scale_factor == approx(math.sqrt(fit.chi2 / fit.ndf))
    assert fit.se[0] == approx(fit.se_stat[0] * fit.scale_factor)
    # S is estimated from ν = 2 residual degrees of freedom: the band takes t₀.₉₇₅,₂ = 4.303, not 1.96.
    assert fit.ndf == 2 and fit.band_quantile == gaussian.t_quantile_975(2) == 4.303
    y, lo, hi = rf.band(fit, [0.0, 0.3])
    half = 4.303 * math.sqrt(fit.cov[1, 1])
    assert hi[0] - y[0] == approx(half) and y[0] - lo[0] == approx(half)


def test_an_unscaled_band_keeps_the_normal_quantile():
    """While χ²/ν ≤ 1 the windows' own standard errors stand, and the band is ±z₀.₉₇₅."""
    x = 1 / np.sqrt(np.array([5.5, 8.5, 12.5, 19.5]))
    fit = rf.fit_affine(x, 0.2 * x + 0.01, [400, 400, 400, 400])
    assert fit.scale_factor == 1.0 and fit.band_quantile == rf.Z95
    y, lo, hi = rf.band(fit, [0.0])
    assert hi[0] - y[0] == approx(rf.Z95 * math.sqrt(fit.cov[1, 1]))


def _fit_at(scale: float, ndf: int = 3, form: str = rf.FORM_PINNED) -> rf.Fit:
    """A fit with a chosen S and ν (χ² = ν·S²), for the misfit gate alone."""
    theta = (0.2,) if form == rf.FORM_PINNED else (0.2, 0.02)
    chi2 = ndf * scale ** 2
    return rf.Fit(form, ndf + len(theta), theta, np.eye(len(theta)) * 1e-6, chi2=chi2, ndf=ndf,
                  p_value=rf.chi2_sf(chi2, ndf), scale_factor=scale, iterations=1, converged=True)


@pytest.mark.parametrize("scale, misfit", [
    (5.0 * (1 + 1e-9), True), (5.0001, True), (12.0, True),
    (5.0, False), (4.9999, False), (5.0 * (1 - 1e-9), False), (1.0, False),
])
@pytest.mark.parametrize("form", [rf.FORM_AFFINE, rf.FORM_PINNED, rf.FORM_QUADRATURE])
def test_the_misfit_gate_is_s_above_five(scale, misfit, form):
    """S = √(χ²/ν), the RMS of the residuals in the windows' own errors: a misfit just above 5, never at or below."""
    assert rf.MISFIT_SCALE == 5.0
    fit = _fit_at(scale, form=form)
    assert fit.scale_factor == scale and fit.misfit is misfit


def test_no_degree_of_freedom_is_never_a_misfit():
    """ν = 0 passes through its points and has no test: never a misfit, whatever S is set to."""
    assert _fit_at(50.0, ndf=0).misfit is False
    assert _fit_at(5.0001, ndf=1).misfit is True
    # Real fits with ν = 0, through points far from any common form, at N = 5,000.
    line = rf.fit_affine([0.25, 0.4], [0.07, 0.30], [5000, 5000])
    assert line.ndf == 0 and line.scale_factor == 1.0 and line.misfit is False
    pinned = rf.fit_pinned([0.3], [0.6], [5000])
    assert pinned.ndf == 0 and pinned.misfit is False


def test_a_pinned_fit_through_a_constant_term_is_a_misfit_and_its_block_says_so():
    """σ/E = √(a²/E + b²) with b = 30% at N = 2,000 a window: a₀/√E cannot hold it, the quadrature form can."""
    rng = np.random.default_rng(1111)
    x, r, n = _windows(rng, lambda p: np.sqrt(0.2 ** 2 / p + 0.3 ** 2), 2000)
    pinned, quad = rf.fit_pinned(x, r, n), rf.fit_quadrature(x, r, n)
    assert pinned.ndf >= 1 and pinned.scale_factor > rf.MISFIT_SCALE and pinned.misfit
    assert quad.scale_factor < 3 and not quad.misfit
    # The χ² test rejects the pinned form at any threshold a reader would use, as it rejects small misfits too.
    assert pinned.p_value < 1e-6
    block = rs.fit_block(pinned, provisional=False)
    assert block["misfit"] is True and block["provisional"] is False
    assert f"S = {pinned.scale_factor:.3g} > 5" in block["note"] and "does not describe these windows" in block["note"]
    assert "drawn faded and never sets a range" in block["note"]
    calm = rs.fit_block(quad, provisional=False)
    assert calm["misfit"] is False and "does not describe" not in calm["note"]


def test_an_oscillating_refit_is_damped_to_its_fixed_point():
    """Five windows at σ/E near 100% whose quadrature refits swing between A ≈ 3 and 23: settled by half steps."""
    x = 1 / np.sqrt(np.array([5.5, 7.5, 10.5, 14.5, 19.5]))
    r = np.array([2.1, 1.166, 0.55, 0.557, 0.819])
    n = np.array([30, 31, 29, 30, 29])
    fit = rf.fit_quadrature(x, r, n)
    assert fit.converged and fit.iterations < rf.MAX_ITERATIONS
    # The fixed point: one more refit at the fitted value returns the same parameters.
    yhat = fit.predict(x)
    w = 1.0 / (2.0 * yhat * rf.resolution_se(yhat, n)) ** 2
    again, _ = rf.wls_affine(x * x, r * r, w)
    assert again == approx(np.array(fit.theta), rel=1e-8)


# -------------------------------------------------------------- recovery --


def _windows(rng, sigma_of_p, n_per_window, energies=range(5, 20)):
    """Per window [k, k + 1): x = ⟨1/√p⟩, r = s(R)/R̄ and N, with R ~ N(1, σ(p)²)."""
    xs, rs_, ns = [], [], []
    for k in energies:
        p = rng.uniform(k, k + 1, n_per_window)
        ratio = 1.0 + sigma_of_p(p) * rng.standard_normal(n_per_window)
        fit = gaussian.fit_gaussian(ratio)
        xs.append(float(np.mean(1 / np.sqrt(p))))
        rs_.append(fit.resolution)
        ns.append(n_per_window)
    return np.array(xs), np.array(rs_), np.array(ns)


A_TRUE, B_TRUE = 0.20, 0.02


def test_affine_and_pinned_recover_the_generating_terms():
    rng = np.random.default_rng(20261031)
    x, r, n = _windows(rng, lambda p: A_TRUE / np.sqrt(p) + B_TRUE, 2000)
    fit = rf.fit_affine(x, r, n)
    assert abs(fit.theta[0] - A_TRUE) < 3 * fit.se[0]
    assert abs(fit.theta[1] - B_TRUE) < 3 * fit.se[1]
    pinned_x, pinned_r, pinned_n = _windows(rng, lambda p: A_TRUE / np.sqrt(p), 2000)
    pinned = rf.fit_pinned(pinned_x, pinned_r, pinned_n)
    assert abs(pinned.theta[0] - A_TRUE) < 3 * pinned.se[0]


def test_quadrature_recovers_quadrature_data():
    rng = np.random.default_rng(7)
    x, r, n = _windows(rng, lambda p: np.sqrt(A_TRUE ** 2 / p + 0.05 ** 2), 2000)
    terms = rf.quadrature_terms(rf.fit_quadrature(x, r, n))
    assert terms.a_defined and terms.b_defined
    assert abs(terms.a - A_TRUE) < 3 * terms.se_a
    assert abs(terms.b - 0.05) < 3 * terms.se_b


def test_quadrature_reports_b_undefined_when_b_squared_is_negative():
    x = np.array([0.25, 0.3, 0.35, 0.4, 0.45])
    r = np.sqrt(0.05 * x * x - 0.0005)              # B = −0.0005 exactly
    fit = rf.fit_quadrature(x, r, [500] * 5)
    assert fit.theta[1] == approx(-0.0005, rel=1e-6)
    terms = rf.quadrature_terms(fit)
    assert terms.b is None and not terms.b_defined and terms.se_b is None
    assert terms.b2 == approx(-0.0005, rel=1e-6) and terms.se_b2 > 0
    block = rs.fit_block(fit, provisional=False)
    assert block["params"]["b"] is None and block["params"]["b_defined"] is False
    assert block["params"]["b2"] == approx(-5.0, rel=1e-6)     # %²
    assert block["curve"] is None and "B ≤ 0" in block["note"]
    # The E view rebuilds the band from the params: ρ(A, B) and the quantile travel with it.
    assert block["params"]["rho_a2b2"] == approx(fit.rho) and -1.0 <= fit.rho <= 1.0
    assert block["band_quantile"] == fit.band_quantile


def test_reported_intervals_cover_the_truth_over_400_replicas():
    """95% intervals (scaled SEs, as served) of a, b and a₀ cover the generating values."""
    rng = np.random.default_rng(42)
    hits = {"a": 0, "b": 0, "a0": 0}
    replicas = 400
    for _ in range(replicas):
        x, r, n = _windows(rng, lambda p: A_TRUE / np.sqrt(p) + B_TRUE, 200)
        fit = rf.fit_affine(x, r, n)
        hits["a"] += abs(fit.theta[0] - A_TRUE) <= rf.Z95 * fit.se[0]
        hits["b"] += abs(fit.theta[1] - B_TRUE) <= rf.Z95 * fit.se[1]
        x, r, n = _windows(rng, lambda p: A_TRUE / np.sqrt(p), 200)
        pinned = rf.fit_pinned(x, r, n)
        hits["a0"] += abs(pinned.theta[0] - A_TRUE) <= rf.Z95 * pinned.se[0]
    for name, count in hits.items():
        assert 0.92 <= count / replicas <= 0.98, (name, count / replicas)


# ------------------------------------------------------ quadrature band --


def _quadrature_fit(theta, cov_stat, ndf=3, scale=1.0) -> rf.Fit:
    """A quadrature fit with chosen parameters, for the band's arithmetic alone."""
    return rf.Fit(rf.FORM_QUADRATURE, ndf + 2, tuple(theta), np.asarray(cov_stat, dtype=float),
                  chi2=float(ndf) * scale ** 2, ndf=ndf, p_value=None, scale_factor=scale,
                  iterations=1, converged=True)


def _final_weights(fit: rf.Fit, x, r, n) -> np.ndarray:
    """The quadrature fit's weights at its fixed point: 1/se_z² at the fitted ŷ."""
    x, r, n = (np.asarray(v, dtype=float) for v in (x, r, n))
    zhat = fit.theta[0] * x * x + fit.theta[1]
    se_meas = 2.0 * r * rf.resolution_se(r, n)
    yhat = np.sqrt(np.where(zhat > 0, zhat, 1.0))
    return 1.0 / np.where(zhat > 0, 2.0 * yhat * rf.resolution_se(yhat, n), se_meas) ** 2


@pytest.mark.parametrize("seed, spread", [(11, 0.0), (12, 0.25)])
def test_the_quadrature_band_is_the_root_of_the_z_band_from_lstsq(seed, spread):
    """√ of ẑ ± q·√(gᵀVg), V the lstsq covariance on the √w-scaled (u, 1) system times S²."""
    rng = np.random.default_rng(seed)
    x = 1 / np.sqrt(np.array([4.5, 6.5, 9.5, 13.5, 18.5]))
    r = np.sqrt(0.04 * x * x + 0.0025) * (1 + spread * rng.standard_normal(x.size))
    n = np.array([300, 250, 400, 150, 220])
    fit = rf.fit_quadrature(x, r, n)
    assert fit.converged
    w = _final_weights(fit, x, r, n)
    design = np.stack([x * x, np.ones_like(x)], axis=1)
    root = np.sqrt(w)
    scaled = design * root[:, None]
    theta, *_ = np.linalg.lstsq(scaled, r * r * root, rcond=None)
    assert theta == approx(np.array(fit.theta), rel=1e-6)
    chi2 = float((w * (r * r - design @ theta) ** 2).sum())
    ndf = x.size - 2
    s = math.sqrt(chi2 / ndf) if chi2 / ndf > 1 else 1.0
    assert s == approx(fit.scale_factor, rel=1e-6)
    cov = np.linalg.inv(scaled.T @ scaled) * s * s
    q = gaussian.t_quantile_975(ndf) if s > 1 else rf.Z95
    xs = np.linspace(0.0, 0.5, 11)
    g = np.stack([xs * xs, np.ones_like(xs)], axis=1)
    zhat = g @ theta
    half = q * np.sqrt(np.einsum("ij,jk,ik->i", g, cov, g))
    y, lo, hi = rf.band(fit, xs)
    assert y == approx(np.sqrt(zhat), rel=1e-6)
    assert y == approx(fit.predict(xs), rel=1e-12)
    assert lo == approx(np.sqrt(np.maximum(zhat - half, 0.0)), rel=1e-5, abs=1e-12)
    assert hi == approx(np.sqrt(zhat + half), rel=1e-5)
    assert (lo <= y).all() and (y <= hi).all()


def test_the_quadrature_band_is_cut_at_zero_below():
    """Where ẑ − half < 0 the lower edge is 0, never the root of a negative number; elsewhere it is not."""
    fit = _quadrature_fit((0.04, 0.0004), [[1e-4, 0.0], [0.0, 1e-6]])
    xs = np.array([0.0, 0.05, 0.5])
    y, lo, hi = rf.band(fit, xs)
    zhat = 0.04 * xs * xs + 0.0004
    half = rf.Z95 * np.sqrt(1e-4 * xs ** 4 + 1e-6)
    assert (zhat - half)[:2].max() < 0 < (zhat - half)[2]
    assert lo[:2].tolist() == [0.0, 0.0]
    assert lo[2] == approx(math.sqrt(zhat[2] - half[2]))
    assert np.isfinite(lo).all() and (hi > y).all()
    # A model that is not positive draws zero, not NaN.
    flat = _quadrature_fit((-0.04, 0.001), [[1e-6, 0.0], [0.0, 1e-8]])
    y, lo, hi = rf.band(flat, [0.5])
    assert y[0] == 0.0 and lo[0] == 0.0 and np.isfinite(hi[0])


def test_the_quadrature_band_at_infinite_energy_is_the_interval_of_root_b():
    fit = _quadrature_fit((0.05, 0.0025), [[4e-5, -3e-7], [-3e-7, 1e-8]])
    y, lo, hi = rf.band(fit, [0.0])
    half = rf.Z95 * 1e-4
    assert y[0] == approx(0.05)
    assert lo[0] == approx(math.sqrt(0.0025 - half)) and hi[0] == approx(math.sqrt(0.0025 + half))


def test_the_quadrature_band_takes_student_t_once_s_scales_it():
    """Four windows far from the form at N = 400: S > 1, ν = 2, and the band takes t₀.₉₇₅,₂."""
    x = 1 / np.sqrt(np.array([5.5, 8.5, 12.5, 19.5]))
    r = np.array([0.14, 0.07, 0.10, 0.05])
    fit = rf.fit_quadrature(x, r, [400] * 4)
    assert fit.scale_factor > 1.0 and fit.ndf == 2
    assert fit.band_quantile == gaussian.t_quantile_975(2) == 4.303
    big_a, big_b = fit.theta
    _, _, hi = rf.band(fit, [0.0, 0.3])
    u = 0.09
    gvg = u * u * fit.cov[0, 0] + 2 * u * fit.cov[0, 1] + fit.cov[1, 1]
    # hi² − ẑ is the z-band's half-width (ẑ itself may be negative at x = 0: B < 0 here).
    assert hi[1] ** 2 - (big_a * u + big_b) == approx(4.303 * math.sqrt(gvg), rel=1e-9)
    assert hi[0] ** 2 - big_b == approx(4.303 * math.sqrt(fit.cov[1, 1]), rel=1e-9)
    # The scaled covariance, not the WLS one.
    assert fit.cov[1, 1] == approx(fit.cov_stat[1, 1] * fit.scale_factor ** 2)
    # Unscaled, the normal quantile.
    calm = rf.fit_quadrature(x, np.sqrt(0.04 * x * x + 0.0025), [400] * 4)
    assert calm.scale_factor == 1.0 and calm.band_quantile == rf.Z95


B_QUAD = 0.05
COVERAGE_ENERGIES = (5.0, 10.0, 18.0)


def test_the_quadrature_band_covers_the_truth_over_400_replicas():
    """At 5, 10 and 18 GeV the served band covers the generating √(a²/E + b²) about 95% of the time."""
    rng = np.random.default_rng(1110)
    xs = 1 / np.sqrt(np.array(COVERAGE_ENERGIES))
    truth = np.sqrt(A_TRUE ** 2 * xs * xs + B_QUAD ** 2)
    hits = np.zeros(len(COVERAGE_ENERGIES), dtype=int)
    replicas = 400
    for _ in range(replicas):
        x, r, n = _windows(rng, lambda p: np.sqrt(A_TRUE ** 2 / p + B_QUAD ** 2), 200)
        fit = rf.fit_quadrature(x, r, n)
        _, lo, hi = rf.band(fit, xs)
        hits += (lo <= truth) & (truth <= hi)
    for energy, count in zip(COVERAGE_ENERGIES, hits):
        assert 0.92 <= count / replicas <= 0.98, (energy, count / replicas)


# --------------------------------------------------------------- anchors --


def _axis(lo: int, hi: int) -> performance_bins.BinAxis:
    return performance_bins.axis_from_ranges({k: (k + 0.01, k + 0.99) for k in range(lo, hi + 1)})


def test_nominal_anchors_on_both_producer_axes():
    assert rs.nominal_anchors(_axis(0, 19)) == (5, 10, 19)
    assert rs.nominal_anchors(_axis(2, 17)) == (5, 9, 17)
    assert rs.nominal_anchors(_axis(0, 4)) == ()
    assert rs.nominal_anchors(_axis(3, 5)) == (5,)
    assert rs.nominal_anchors(_axis(5, 6)) == (5, 6)


def _series_windows(counts: dict[int, int], seed: int = 3):
    """Windows of an axis 0–19 holding ``counts[k]`` events in bin k."""
    rng = np.random.default_rng(seed)
    bins, p = [], []
    for k, count in counts.items():
        bins += [k] * count
        p += list(rng.uniform(k, k + 1, count))
    bins, p = np.array(bins, dtype=float), np.array(p)
    ratio = 1.0 + (0.2 / np.sqrt(p)) * rng.standard_normal(p.size)
    return rs.windows_of(ratio, p, bins, _axis(0, 19))


def test_a_thin_anchor_takes_the_nearest_eligible_window_and_says_so():
    windows = _series_windows({3: 40, 5: 10, 6: 30, 10: 50, 19: 25})
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    assert mode.points == [6, 10, 19] and not mode.fallback and not mode.provisional
    (sub,) = mode.substitutions
    assert sub["nominal"] == 5 and sub["used"] == 6 and "N = 10" in sub["reason"]
    # Bin 3 has N = 40 but lies below 4 GeV: never a candidate.
    every = rs.mode_fits("all", (5, 10, 19), windows)
    assert every.points == [6, 10, 19]
    assert all(mode.fits[form] is not None for form in ("affine", "pinned", "quadrature"))


def test_a_thin_anchor_never_takes_a_window_below_the_anchor_floor():
    """The 4–5 GeV window may be fitted in the all-windows mode, but it never stands in for an anchor."""
    windows = _series_windows({4: 60, 5: 10, 7: 30, 10: 50, 19: 25})
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    assert mode.points == [7, 10, 19]
    (sub,) = mode.substitutions
    assert sub["used"] == 7 and "from 5 GeV" in sub["reason"]
    assert rs.mode_fits("all", (5, 10, 19), windows).points == [4, 7, 10, 19]


def test_an_anchor_with_nothing_left_is_dropped():
    windows = _series_windows({5: 10, 10: 50, 19: 25})
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    assert mode.points == [10, 19] and not mode.fallback
    assert mode.substitutions == [{"nominal": 5, "used": None, "reason": mode.substitutions[0]["reason"]}]
    assert "dropped" in mode.substitutions[0]["reason"]


def test_too_few_eligible_windows_fall_back_to_whiskered_ones_provisionally():
    windows = _series_windows({5: 10, 10: 30, 19: 9})
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    assert mode.points == [5, 10, 19] and mode.fallback and mode.provisional
    block = rs.fit_block(mode.fits["affine"], mode.provisional)
    assert block["provisional"] is True and "Provisional" in block["note"]
    every = rs.mode_fits("all", (5, 10, 19), windows)
    assert every.points == [5, 10, 19] and every.fallback
    # Nothing reaches N = 8 beside the one eligible window: no fallback, one point.
    lone = rs.mode_fits("anchors", (5, 10, 19), _series_windows({5: 3, 10: 30, 19: 2}))
    assert lone.points == [10] and not lone.fallback
    assert lone.fits["affine"] is None and lone.fits["pinned"] is not None


def test_window_gates():
    windows = {w.bin: w for w in _series_windows({1: 30, 4: 25, 6: 1, 7: 2, 8: 8, 9: 19, 10: 20})}
    assert windows[1].off_axis and not windows[1].eligible and windows[1].whisker
    assert windows[4].eligible and not windows[4].off_axis
    assert windows[6].as_dict()["value"] is None and not windows[6].whisker
    assert windows[7].as_dict()["value"] is not None and not windows[7].whisker
    assert windows[7].as_dict()["c4"] is not None and windows[7].as_dict()["dof_note"] == "1 d.o.f."
    assert windows[8].whisker and windows[8].as_dict()["weak"] and not windows[8].eligible
    assert not windows[9].eligible and windows[10].eligible
    assert windows[10].as_dict()["c4"] is None
