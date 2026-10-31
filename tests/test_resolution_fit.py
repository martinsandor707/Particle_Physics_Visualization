"""``stats/resolution_fit.py`` and the anchor rules of ``query/resolution_scaling.py``, on bare arrays.

The closed forms are held to ``numpy.linalg.lstsq`` on the ``√w``-scaled
system, their covariance to ``(XᵀWX)⁻¹`` and to a finite-difference
propagation, ``chi2_sf`` to the textbook table and to the two closed forms
(ν = 1, 2). The fits are then run on simulated windows: recovery of the
generating a and b within 3 standard errors, and the coverage of the reported
95% intervals over 400 seeded replicas. Nothing here is a measurement of the
detector.
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
