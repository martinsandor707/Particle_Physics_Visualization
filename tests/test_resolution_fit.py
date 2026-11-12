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
and on a pinned fit through a constant term.

The κ law (the ``kappa`` argument, Martin's decisions of 2026-11-12): without
it every fit runs the delta-method law exactly as before; with it each form
reaches the fixed point of ``se = κ·ŷ`` (``se_z = 2κ·ŷ²`` for the quadrature),
held to ``numpy.linalg.lstsq`` on the ``√w``-scaled system at the final weights,
with the χ² those weights give. The window gates of the three estimators are
held on bare windows.

The pooled weight scale (the fix brief's F1, 2026-11-12): the card passes
``κ = c/√N`` with ``c`` the series' median of ``√N·κ`` over its fittable windows,
never a window's own κ. It is held to its definition, to cancelling in the
parameters (3c leaves θ and divides χ² by 9), and, by a seeded Monte Carlo
through ``windows_of`` and ``mode_fits``, to removing the upward bias a
per-window κ adds. Why a window is not fitted (F3: never blamed on N when N is
not the cause) and the robust estimator's refusal to fit one window (F4) are
held on bare windows. Nothing here is a measurement of the detector.
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


def _series_windows(counts: dict[int, int], seed: int = 3, estimator: str = "sample"):
    """Windows of an axis 0–19 holding ``counts[k]`` events in bin k (the sample estimator unless named)."""
    rng = np.random.default_rng(seed)
    bins, p = [], []
    for k, count in counts.items():
        bins += [k] * count
        p += list(rng.uniform(k, k + 1, count))
    bins, p = np.array(bins, dtype=float), np.array(p)
    ratio = 1.0 + (0.2 / np.sqrt(p)) * rng.standard_normal(p.size)
    return rs.windows_of(ratio, p, bins, _axis(0, 19), estimator=estimator)


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
    assert mode.substitutions == [{"nominal": 5, "used": None, "cause": "n",
                                   "reason": mode.substitutions[0]["reason"]}]
    assert mode.substitutions[0]["reason"] == (
        "The nominal anchor 5–6 GeV holds N = 10 for this series, below 20, and no other window "
        "from 5 GeV with N ≥ 20 is left: it is dropped.")


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


@pytest.mark.parametrize("estimator", ["median", "robust"])
def test_the_anchor_rules_hold_under_the_other_estimators(estimator):
    """A thin anchor is replaced the same way; under the robust width no N ≥ 8 fallback exists,
    and no line is fitted through one window (F4)."""
    windows = _series_windows({3: 40, 5: 10, 6: 30, 10: 50, 19: 25}, estimator=estimator)
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    assert mode.points == [6, 10, 19] and not mode.fallback
    (sub,) = mode.substitutions
    assert sub["cause"] == "n" and "fittable window from 5 GeV" in sub["reason"]
    thin = _series_windows({5: 10, 10: 30, 19: 9}, estimator=estimator)
    fallback = rs.mode_fits("anchors", (5, 10, 19), thin)
    if estimator == "robust":
        assert fallback.points == [] and fallback.declined == [10]
        assert not fallback.fallback and not fallback.provisional
        assert all(fit is None for fit in fallback.fits.values())
        every = rs.mode_fits("all", (5, 10, 19), thin)
        assert every.points == [] and every.declined == [10]
        assert all(fit is None for fit in every.fits.values())
    else:
        assert fallback.points == [5, 10, 19] and fallback.fallback and fallback.provisional
        assert fallback.declined == []


def test_window_gates_under_the_median_estimator():
    """The median rel. from N = 2, its order-statistic interval from N = 6, the whisker from N = 8."""
    windows = {w.bin: w for w in _series_windows({6: 1, 7: 2, 8: 6, 9: 8, 10: 19, 11: 20},
                                                 estimator="median")}
    assert windows[6].r is None and windows[6].as_dict()["value"] is None
    assert windows[7].r is not None and windows[7].ci is None and windows[7].as_dict()["c4"] is None
    assert windows[7].as_dict()["dof_note"] is None and windows[7].se > 0
    assert windows[8].ci is not None and not windows[8].whisker
    assert windows[8].method == "order_statistic"
    assert windows[9].whisker and windows[9].method == "order_statistic"
    assert windows[10].whisker and not windows[10].eligible
    assert windows[11].eligible and windows[11].method == "bootstrap_percentile"
    for w in windows.values():
        d = w.as_dict()
        assert d["se_delta"] is None and set(d["alt"]) == {"robust", "sample"}
        if w.r is not None:
            assert d["se_rel"] == approx(w.se / w.r) and d["se"] == approx(100 * w.se)


def test_window_gates_under_the_robust_estimator():
    """Nothing below the robust floor: no value, no whisker, no fit, and the window says why."""
    windows = {w.bin: w for w in _series_windows({7: 2, 8: 8, 9: 19, 10: 20},
                                                 estimator="robust")}
    for k in (7, 8, 9):
        d = windows[k].as_dict()
        assert d["value"] is None and d["ci95"] is None and not d["whisker"] and not d["eligible"]
        assert "below the robust floor" in d["dof_note"] and d["weak"]
        assert d["alt"]["sample"] is not None and d["alt"]["median"] is not None
    d = windows[10].as_dict()
    assert d["value"] is not None and d["whisker"] and d["eligible"] and not d["weak"]
    assert d["method"] == "bootstrap_percentile" and d["se_rel"] == approx(d["se"] / d["value"])
    assert set(d["alt"]) == {"median", "sample"} and d["dof_note"] is None
    # The tail share waits for N = 300 (F5).
    assert d["tail_share"] is None and d["se_delta"] is None


# ------------------------------------------------------------- the κ law --


def _kappa_windows(seed: int, spread: float = 0.0):
    rng = np.random.default_rng(seed)
    x = 1 / np.sqrt(np.array([4.5, 6.5, 9.5, 13.5, 18.5]))
    r = np.sqrt(0.04 * x * x + 0.0025) * (1 + spread * rng.standard_normal(x.size))
    n = np.array([300, 250, 400, 150, 220])
    kappa = rng.uniform(0.03, 0.09, x.size)
    return x, r, n, kappa


def test_no_kappa_is_the_delta_method_law_exactly():
    """kappa=None runs the delta-method law: the same Fit, field for field, as the call without it."""
    rng = np.random.default_rng(20261112)
    x, r, n = _windows(rng, lambda p: A_TRUE / np.sqrt(p) + B_TRUE, 300)
    for fit in (rf.fit_affine, rf.fit_pinned, rf.fit_quadrature):
        a, b = fit(x, r, n), fit(x, r, n, kappa=None)
        assert a.theta == b.theta and np.array_equal(a.cov_stat, b.cov_stat)
        assert (a.chi2, a.ndf, a.p_value, a.scale_factor, a.iterations, a.converged) == (
            b.chi2, b.ndf, b.p_value, b.scale_factor, b.iterations, b.converged)
    # At its fixed point the delta law's weights are 1/resolution_se(ŷ, n)², not κ's.
    fit = rf.fit_affine(x, r, n)
    w = 1.0 / rf.resolution_se(fit.predict(x), n) ** 2
    again, _ = rf.wls_affine(x, r, w)
    assert again == approx(np.array(fit.theta), rel=1e-9)


@pytest.mark.parametrize("seed, spread", [(31, 0.0), (32, 0.2), (33, 0.4)])
@pytest.mark.parametrize("form", [rf.FORM_AFFINE, rf.FORM_PINNED])
def test_a_kappa_fit_is_lstsq_at_its_final_weights(seed, spread, form):
    """At convergence w = 1/(κ·ŷ)²: lstsq on the √w-scaled system returns θ, (XᵀWX)⁻¹ its covariance."""
    x, r, n, kappa = _kappa_windows(seed, spread)
    fit = (rf.fit_affine if form == rf.FORM_AFFINE else rf.fit_pinned)(x, r, n, kappa)
    assert fit.converged and fit.iterations < rf.MAX_ITERATIONS
    yhat = fit.predict(x)
    assert (yhat > 0).all()
    w = 1.0 / (kappa * yhat) ** 2
    design = np.stack([x, np.ones_like(x)], axis=1) if form == rf.FORM_AFFINE else x[:, None]
    root = np.sqrt(w)
    theta, *_ = np.linalg.lstsq(design * root[:, None], r * root, rcond=None)
    assert theta == approx(np.array(fit.theta), rel=1e-8)
    assert fit.cov_stat == approx(np.linalg.inv(design.T @ (w[:, None] * design)), rel=1e-6)
    assert fit.chi2 == approx(float((w * (r - design @ theta) ** 2).sum()), rel=1e-6)
    # Not the delta law's answer: the weights differ.
    delta = (rf.fit_affine if form == rf.FORM_AFFINE else rf.fit_pinned)(x, r, n)
    assert not np.allclose(delta.theta, fit.theta, rtol=1e-6)


@pytest.mark.parametrize("seed, spread", [(41, 0.0), (42, 0.25)])
def test_a_kappa_quadrature_fit_is_lstsq_in_z_at_its_final_weights(seed, spread):
    """se_z = 2κ·ŷ² at the fixed point; lstsq on the √w-scaled (u, 1) system in z = r² returns (A, B)."""
    x, r, n, kappa = _kappa_windows(seed, spread)
    fit = rf.fit_quadrature(x, r, n, kappa)
    assert fit.converged
    zhat = fit.theta[0] * x * x + fit.theta[1]
    assert (zhat > 0).all()
    w = 1.0 / (2.0 * kappa * zhat) ** 2
    design = np.stack([x * x, np.ones_like(x)], axis=1)
    root = np.sqrt(w)
    theta, *_ = np.linalg.lstsq(design * root[:, None], r * r * root, rcond=None)
    assert theta == approx(np.array(fit.theta), rel=1e-7)
    assert fit.cov_stat == approx(np.linalg.inv(design.T @ (w[:, None] * design)), rel=1e-6)
    assert fit.chi2 == approx(float((w * (r * r - design @ theta) ** 2).sum()), rel=1e-6)


def test_kappa_fits_recover_the_generating_terms_and_converge():
    """Windows with a known relative SE κ: the κ-weighted fits recover a and b within 3 SE."""
    rng = np.random.default_rng(1112)
    x = 1 / np.sqrt(np.arange(5.5, 20.0))
    truth = A_TRUE * x + B_TRUE
    kappa = np.full(x.size, 0.04)
    hits = 0
    for _ in range(200):
        r = truth * (1 + kappa * rng.standard_normal(x.size))
        fit = rf.fit_affine(x, r, np.full(x.size, 500), kappa)
        assert fit.converged
        hits += abs(fit.theta[0] - A_TRUE) <= rf.Z95 * fit.se[0]
    assert 0.9 <= hits / 200 <= 0.99
    pinned = rf.fit_pinned(x, A_TRUE * x, np.full(x.size, 500), kappa)
    assert pinned.theta[0] == approx(A_TRUE, rel=1e-12) and pinned.chi2 == approx(0.0, abs=1e-20)


@pytest.mark.parametrize("kappa", [[0.05, 0.0, 0.05], [0.05, -0.1, 0.05], [0.05, np.nan, 0.05],
                                   [0.05, np.inf, 0.05], [0.05, 0.05]])
def test_kappa_must_be_positive_finite_and_aligned(kappa):
    with pytest.raises(ValueError):
        rf.fit_affine([0.25, 0.3, 0.4], [0.1, 0.09, 0.08], [50, 50, 50], kappa)


# ------------------------------------------------- the pooled weight scale --
# F1 of the fix brief (2026-11-12): under median and robust the fits weight window k by
# se = c·ŷₖ/√Nₖ, c the series' pooled scale, the median of √N·κ over its fittable windows.


@pytest.mark.parametrize("estimator", ["median", "robust"])
def test_the_pooled_scale_is_the_median_of_root_n_kappa_over_the_fittable_windows(estimator):
    """Off-axis, thin and κ-less windows stay out of c; each window keeps its measured κ as se_rel."""
    windows = _series_windows({3: 40, 5: 10, 6: 30, 10: 50, 14: 60, 19: 25}, estimator=estimator)
    scale = rs.pooled_scale(windows)
    fittable = [w for w in windows if w.eligible]
    assert [w.bin for w in fittable] == [6, 10, 14, 19]
    assert scale.basis == "fit" and scale.n_windows == 4
    assert scale.c == float(np.median([math.sqrt(w.n) * w.kappa for w in fittable]))
    assert "median of √N·κ over this series' windows of N ≥ 20 from 4 GeV" in scale.rule
    assert scale.as_dict() == {"c": scale.c, "n_windows": 4, "rule": scale.rule}
    for w in windows:
        if w.r is not None and w.kappa is not None:
            assert w.as_dict()["se_rel"] == w.kappa == approx(w.se / w.r)
    assert rs.pooled_scale(_series_windows({10: 50, 14: 60})) is None   # sample: the delta method


def test_the_pooled_scale_falls_back_with_the_median_and_is_absent_without_a_weight():
    """No window of N ≥ 20: c over the N ≥ 8 windows the provisional fits draw on; none at all: no c."""
    windows = _series_windows({5: 10, 10: 12, 19: 9}, estimator="median")
    scale = rs.pooled_scale(windows)
    assert scale.basis == "fallback" and scale.n_windows == 3
    assert scale.c == float(np.median([math.sqrt(w.n) * w.kappa for w in windows]))
    assert "No window of N ≥ 20 from 4 GeV carries a fit weight" in scale.rule
    mode = rs.mode_fits("all", (5, 10, 19), windows)
    assert mode.provisional and mode.points == [5, 10, 19]
    bare = rs.pooled_scale(_series_windows({5: 3, 10: 5}, estimator="median"))
    assert bare.c is None and bare.n_windows == 0 and bare.basis == "none"
    assert bare.rule.startswith("No window from 4 GeV carries a fit weight")


@pytest.mark.parametrize("estimator", ["median", "robust"])
def test_the_fits_weight_by_c_over_root_n_never_by_a_windows_own_kappa(estimator):
    """Both modes' fits are resolution_fit's κ law given c/√N, the same c for every window."""
    windows = _series_windows({4: 60, 6: 30, 8: 45, 10: 50, 14: 60, 19: 25}, estimator=estimator)
    c = rs.pooled_scale(windows).c
    mode = rs.mode_fits("all", (5, 10, 19), windows)
    points = [w for w in windows if w.bin in mode.points]
    x, r, n = [w.x for w in points], [w.r for w in points], [w.n for w in points]
    for form, fit in (("affine", rf.fit_affine), ("pinned", rf.fit_pinned),
                      ("quadrature", rf.fit_quadrature)):
        expected = fit(x, r, n, [c / math.sqrt(k) for k in n])
        assert mode.fits[form].theta == expected.theta and mode.fits[form].chi2 == expected.chi2
        own = fit(x, r, n, [w.kappa for w in points])
        assert own.theta != expected.theta


@pytest.mark.parametrize("form", [rf.FORM_AFFINE, rf.FORM_PINNED, rf.FORM_QUADRATURE])
def test_the_pooled_scale_cancels_in_the_parameters(form):
    """Scaling c by 3 scales every weight by 1/9: θ is unchanged, χ² falls by 9, the WLS errors grow 3×."""
    windows = _series_windows({4: 60, 6: 30, 8: 45, 10: 50, 14: 60, 19: 25}, estimator="median")
    c = rs.pooled_scale(windows).c
    one, three = rs._fits(windows, c)[form], rs._fits(windows, 3 * c)[form]
    assert three.theta == approx(one.theta, rel=1e-9, abs=1e-15)
    assert three.chi2 == approx(one.chi2 / 9, rel=1e-9)
    assert np.asarray(three.se_stat) == approx(3 * np.asarray(one.se_stat), rel=1e-9)
    assert three.iterations == one.iterations and three.converged and one.converged


def _expected_median_of_half_normals(n: int) -> float:
    """E[median of n |Z|], Z standard normal: the order statistics' means by quadrature (n even)."""
    x = np.linspace(0.0, 12.0, 20001)
    cdf = np.vectorize(math.erf)(x / math.sqrt(2.0))
    pdf = 2.0 * np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    def mean_order(k: int) -> float:
        log_c = math.lgamma(n + 1) - math.lgamma(k) - math.lgamma(n - k + 1)
        with np.errstate(divide="ignore"):
            density = np.exp(log_c + (k - 1) * np.log(cdf) + (n - k) * np.log1p(-cdf)) * pdf
        density[0] = 0.0
        return float(np.trapezoid(x * density, x))

    return 0.5 * (mean_order(n // 2) + mean_order(n // 2 + 1))


#: The Monte Carlo below: 16 windows of 40 events at 4–20 GeV, true σ/E = 30%/√E.
MC_REPLICAS = 200
MC_EVENTS = 40
MC_STOCHASTIC = 0.30


def test_the_pooled_scale_removes_the_bias_a_per_window_kappa_adds():
    """F1, the reason pinned: a window's own κ puts its value back into its weight and biases the fit up.

    R-stats' Monte Carlo of the served code paths (2026-11-12) put the origin-pinned term of the
    per-window κ fit +0.70 of its SD high at 40 events a window under the median rel., and the
    pooled scale at 0.00. Here, through ``windows_of`` and ``mode_fits`` (the median estimator,
    16 windows of N = 40 from 4 to 20 GeV, R ~ N(1, σₖ²) with σₖ = 30%·⟨1/√p⟩ₖ, so window k's
    expected median rel. is 30%·m₄₀·xₖ exactly, m₄₀ = E[median of 40 |Z|] = 0.67977): over 200
    seeded replicas the served pinned a₀ is unbiased for 30%·m₄₀ (measured −0.05 of its SD, Monte
    Carlo SE 0.07), and the same replicas refitted with each window's own κ come out +0.77 of their
    SD high (2026-11-12). About 1.8 s.
    """
    axis = performance_bins.axis_from_ranges({k: (k + 0.01, k + 0.99) for k in range(4, 20)})
    nominal = rs.nominal_anchors(axis)
    truth = MC_STOCHASTIC * _expected_median_of_half_normals(MC_EVENTS)
    assert truth == approx(MC_STOCHASTIC * 0.67977312, rel=1e-7)
    rng = np.random.default_rng(20261112)
    pooled, own = [], []
    for replica in range(MC_REPLICAS):
        bins, p, ratio = [], [], []
        for k in range(4, 20):
            pk = rng.uniform(k, k + 1, MC_EVENTS)
            sigma = MC_STOCHASTIC * float(np.mean(1.0 / np.sqrt(pk)))
            bins += [k] * MC_EVENTS
            p += list(pk)
            ratio += list(1.0 + sigma * rng.standard_normal(MC_EVENTS))
        windows = rs.windows_of(np.array(ratio), np.array(p), np.array(bins, dtype=float), axis,
                                estimator="median", seed=(42, 0, 0, replica))
        assert len(windows) == 16 and all(w.eligible for w in windows)
        mode = rs.mode_fits("all", nominal, windows, axis)
        pooled.append(mode.fits[rf.FORM_PINNED].theta[0])
        x, r, n = [w.x for w in windows], [w.r for w in windows], [w.n for w in windows]
        own.append(rf.fit_pinned(x, r, n, [w.kappa for w in windows]).theta[0])
    pooled, own = np.array(pooled), np.array(own)
    pooled_bias = (pooled.mean() - truth) / pooled.std(ddof=1)
    own_bias = (own.mean() - truth) / own.std(ddof=1)
    assert abs(pooled_bias) <= 0.25, pooled_bias
    assert own_bias >= 0.5, own_bias
    assert (own > pooled).mean() > 0.9           # replica by replica, the own-κ fit sits higher


# -------------------------------------------- why a window is not fitted --
# F3 of the fix brief: a window of N ≥ 20 without a fit weight is never blamed on N.


def _windows_with(estimator: str, special: dict[int, tuple[np.ndarray, np.ndarray]],
                  counts: dict[int, int], seed: int = 3):
    """Windows on the 0–19 axis: ``counts[k]`` Gaussian events in bin k, and in each ``special``
    bin the given ``(R, relative error)`` instead."""
    rng = np.random.default_rng(seed)
    bins, p, ratio, relative = [], [], [], []
    for k, count in counts.items():
        pk = rng.uniform(k, k + 1, count)
        rk = 1.0 + (0.2 / np.sqrt(pk)) * rng.standard_normal(count)
        bins += [k] * count
        p += list(pk)
        ratio += list(rk)
        relative += list(np.abs(rk - 1.0))
    for k, (rk, rel) in special.items():
        bins += [k] * rk.size
        p += list(rng.uniform(k, k + 1, rk.size))
        ratio += list(rk)
        relative += list(rel)
    return rs.windows_of(np.array(ratio), np.array(p), np.array(bins, dtype=float), _axis(0, 19),
                         estimator=estimator, relative=np.array(relative))


def test_an_anchor_without_a_robust_value_is_never_called_thin():
    """R-stats' example: the 10–11 GeV anchor holds N = 60 but its median R < 0."""
    rk = -0.2 + 0.1 * np.random.default_rng(5).standard_normal(60)
    windows = _windows_with("robust", {10: (rk, np.abs(rk - 1))}, {6: 40, 9: 50, 19: 30})
    window = next(w for w in windows if w.bin == 10)
    assert window.n == 60 and window.r is None and window.unfit_cause(20) == "no_value"
    assert "not positive" in window.as_dict()["dof_note"]
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    by_nominal = {s["nominal"]: s for s in mode.substitutions}
    assert by_nominal[10]["cause"] == "no_value" and by_nominal[10]["used"] == 9
    assert by_nominal[10]["reason"] == (
        "The nominal anchor 10–11 GeV holds N = 60 for this series but has no robust σ/E (its "
        "median response is not positive); the nearest fittable window from 5 GeV in log E with "
        "N ≥ 20 is 9–10 GeV (N = 50).")
    assert "below 20" not in by_nominal[10]["reason"]
    assert by_nominal[5]["cause"] == "n" and ", below 20; " in by_nominal[5]["reason"]


def test_a_tied_anchor_is_named_tied_and_dropped_when_nothing_fittable_is_left():
    """R-ui's example: a tied median window of N ≥ 20 has no fit weight, said so, and is dropped."""
    tied = 0.2 + 1e-13 * np.random.default_rng(3).standard_normal(22)
    windows = _windows_with("median", {10: (1.0 + tied, tied)}, {5: 5, 19: 4})
    window = next(w for w in windows if w.bin == 10)
    assert window.n == 22 and window.tied and window.unfit_cause(20) == "tied"
    mode = rs.mode_fits("anchors", (5, 10, 19), windows)
    by_nominal = {s["nominal"]: s for s in mode.substitutions}
    assert by_nominal[10]["cause"] == "tied" and by_nominal[10]["used"] is None
    assert by_nominal[10]["reason"] == (
        "The nominal anchor 10–11 GeV holds N = 22 for this series but its bootstrap SE is below "
        "10⁻⁶ of its value (tied replicates), so it carries no fit weight, and no other fittable "
        "window from 5 GeV with N ≥ 20 is left: it is dropped.")


def test_a_withheld_robust_interval_is_the_anchors_cause():
    """F7: 7 of 21 events at R < 0 drop 6% of the replicates; the window keeps its value, not its weight."""
    rk = np.concatenate([np.full(7, -0.5), np.linspace(0.6, 1.4, 14)])
    windows = _windows_with("robust", {10: (rk, np.abs(rk - 1))}, {6: 40, 9: 50, 19: 30})
    window = next(w for w in windows if w.bin == 10)
    d = window.as_dict()
    assert window.withheld and d["value"] is not None
    assert d["ci95"] is None and d["se"] is None and d["se_rel"] is None and not d["whisker"]
    assert not d["eligible"] and d["dof_note"].startswith("Robust interval withheld:")
    (sub,) = [s for s in rs.mode_fits("anchors", (5, 10, 19), windows).substitutions
              if s["nominal"] == 10]
    assert sub["cause"] == "withheld" and "its robust interval is withheld" in sub["reason"]
