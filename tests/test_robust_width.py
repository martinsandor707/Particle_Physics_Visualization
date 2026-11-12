"""``stats/robust_width.py``: the robust σ/E, its exact bootstrap, κ and the tail share, on bare arrays.

The exact order-statistic bootstrap is held three ways: each replicate quartile's
distribution over the sample's values to the closed form ``P(X*₍ₖ₎ ≤ x₍ⱼ₎) =
P(Bin(n, j/n) ≥ k)``, the robust width's replicate quantiles and SD to
brute-force resampling with ``np.percentile`` on seeded samples, and the draws
to the reference implementation the card was verified with on
``pion_hits_with_model_outputs`` (``exact()`` of the design's
``scratch/iqr_check.py``, transcribed below), bit for bit. The type-7 ranks are
checked against ``np.percentile`` for every n up to 60, small n and integer
``h`` included. ``median.bootstrap_medians`` is held to the interval it now
feeds, which must not have moved. Nothing here is a measurement of the detector.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pytest import approx

from calosrv.query import performance_bins
from calosrv.stats import gaussian, median, metrics
from calosrv.stats import robust_width as rw


def _heavy(n: int, seed: int = 7, scale: float = 0.1) -> np.ndarray:
    """R near 1 with Student-t₃ tails: a response with the outliers the robust width resists."""
    return 1.0 + scale * np.random.default_rng(seed).standard_t(3, n)


# --------------------------------------------------------------- constants --


def test_the_constants():
    assert rw.IQR_TO_SIGMA == gaussian.IQR_TO_SIGMA == 1.349
    assert rw.MIN_ROBUST_N == gaussian.MIN_ROBUST_SAMPLES == 20
    assert rw.BOOTSTRAP_REPLICATES == median.BOOTSTRAP_REPLICATES == 2000
    assert rw.QUARTILES == (0.25, 0.5, 0.75)
    assert rw.PERCENTILES == (0.025, 0.975)
    # The robust width's seed follows every quantity Model Error vs. Incident Momentum seeds.
    assert rw.SEED_QUANTITY_INDEX == 8 == (len(performance_bins.QUANTITIES)
                                           + len(performance_bins.PHI_QUANTITIES))
    # 2·(1 − Φ(3)), the tail share of a Gaussian.
    assert rw.GAUSSIAN_TAIL_SHARE == approx(0.0026997960632601866, rel=1e-12)
    assert rw.GAUSSIAN_TAIL_SHARE == approx(2 * (1 - 0.5 * (1 + math.erf(3 / math.sqrt(2)))), rel=1e-9)


# ------------------------------------------------------------- type-7 ranks --


@pytest.mark.parametrize("n", range(1, 61))
def test_type7_ranks_reproduce_np_percentile(n):
    """x₍lo₎ + frac·(x₍hi₎ − x₍lo₎) is np.percentile's default (type 7), at every n, on uneven values."""
    x = np.sort(np.random.default_rng(n).lognormal(size=n))
    for p in rw.QUARTILES:
        lo, hi, frac = rw.type7_rank(n, p)
        assert 1 <= lo <= hi <= n and 0.0 <= frac < 1.0
        assert hi == min(lo + 1, n)
        ours = x[lo - 1] + frac * (x[hi - 1] - x[lo - 1])
        assert ours == approx(float(np.percentile(x, 100 * p)), rel=1e-14)


@pytest.mark.parametrize("n, expected", [
    (1, [(1, 1, 0.0)] * 3),                                   # one value: every quartile is it
    (2, [(1, 2, 0.25), (1, 2, 0.5), (1, 2, 0.75)]),
    (3, [(1, 2, 0.5), (2, 3, 0.0), (2, 3, 0.5)]),
    (5, [(2, 3, 0.0), (3, 4, 0.0), (4, 5, 0.0)]),             # integer h: no interpolation
    (20, [(5, 6, 0.75), (10, 11, 0.5), (15, 16, 0.25)]),
    (21, [(6, 7, 0.0), (11, 12, 0.0), (16, 17, 0.0)]),
])
def test_type7_ranks_by_hand(n, expected):
    got = [rw.type7_rank(n, p) for p in rw.QUARTILES]
    assert [(lo, hi) for lo, hi, _ in got] == [(lo, hi) for lo, hi, _ in expected]
    assert [frac for *_, frac in got] == approx([frac for *_, frac in expected], abs=0)


def test_type7_rank_refuses_an_empty_sample():
    with pytest.raises(ValueError):
        rw.type7_rank(0, 0.5)


# ------------------------------------------------------ the exact bootstrap --


def _binomial_sf(n: int, q: float, k: int) -> float:
    """P(Bin(n, q) ≥ k)."""
    return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(k, n + 1))


@pytest.mark.parametrize("n", [21, 25])
def test_each_drawn_order_statistic_has_the_resampling_distribution(n):
    """At an integer h (n = 4m + 1) a replicate quartile is one order statistic of the resample.

    Its exact law over the sample's values: X*₍ₖ₎ ≤ x₍ⱼ₎ when at least k of the n draws
    land on x₍₁₎…x₍ⱼ₎, so P = P(Bin(n, j/n) ≥ k). Held at every j over 200,000 replicates,
    for all three quartiles, which the sequential Betas draw jointly.
    """
    x = np.arange(1.0, n + 1.0)                 # x₍ⱼ₎ = j
    reps = rw.bootstrap_quantiles(x, replicates=200_000, seed=[3, n])
    for row, p in zip(reps, rw.QUARTILES):
        k, _, frac = rw.type7_rank(n, p)
        assert frac == 0.0
        for j in range(1, n + 1):
            expected = _binomial_sf(n, j / n, k)
            assert float(np.mean(row <= j)) == approx(expected, abs=4e-3), (p, j)


def _brute(x: np.ndarray, replicates: int, seed: int) -> np.ndarray:
    """The robust width of ``replicates`` resamples of ``x``, by resampling and np.percentile."""
    rng = np.random.default_rng(seed)
    sample = x[rng.integers(0, x.size, size=(replicates, x.size))]
    q25, q50, q75 = np.percentile(sample, [25, 50, 75], axis=1)
    return (q75 - q25) / rw.IQR_TO_SIGMA / q50


@pytest.mark.parametrize("n", [20, 23, 24, 57, 200])
def test_the_exact_bootstrap_matches_brute_force_resampling(n):
    """Replicate quantiles (2.5, 50, 97.5%) and SD of IQR/(1.349·median) agree with resampling."""
    x = _heavy(n, seed=n)
    replicates = 100_000
    q25, q50, q75 = rw.bootstrap_quantiles(x, replicates=replicates, seed=[1, n])
    exact = (q75 - q25) / rw.IQR_TO_SIGMA / q50
    brute = _brute(x, replicates, seed=n)
    scale = float(np.std(brute))
    for level in (0.025, 0.5, 0.975):
        assert float(np.quantile(exact, level)) == approx(float(np.quantile(brute, level)),
                                                          abs=0.06 * scale), level
    assert float(np.std(exact, ddof=1)) == approx(scale, rel=0.02)
    assert float(np.mean(exact)) == approx(float(np.mean(brute)), abs=0.02 * scale)


def _reference_exact(x, B=2000, seed=(42,)):
    """``exact()`` of the design's scratch/iqr_check.py, verbatim but for names (2026-11-12)."""
    xs = np.sort(x)
    n = xs.size
    rng = np.random.default_rng(np.random.SeedSequence(list(seed)))
    ranks = []
    for p in (0.25, 0.5, 0.75):
        h = (n - 1) * p + 1
        lo = int(math.floor(h))
        ranks.append((lo, h - lo))
    need = sorted({r for lo, _ in ranks for r in (lo, min(lo + 1, n))})
    u = {}
    prev_k, prev_u = 0, np.zeros(B)
    for k in need:
        u[k] = prev_u + (1 - prev_u) * rng.beta(k - prev_k, n - k + 1, size=B)
        prev_k, prev_u = k, u[k]

    def os(k):
        return xs[np.clip(np.ceil(n * u[k]).astype(np.int64), 1, n) - 1]

    q = []
    for lo, frac in ranks:
        a = os(lo)
        b = os(min(lo + 1, n))
        q.append(a + frac * (b - a))
    v = (q[2] - q[0]) / 1.349 / q[1]
    return np.quantile(v, [0.025, 0.975]), v.std(ddof=1)


@pytest.mark.parametrize("n", [20, 21, 23, 24, 25, 57, 1022])
def test_the_robust_interval_is_the_verified_reference_bit_for_bit(n):
    x = _heavy(n, seed=100 + n)
    seed = [42, 0, 1, 10, rw.SEED_QUANTITY_INDEX]
    (lo, hi), se = _reference_exact(x, seed=seed)
    got = rw.robust_width(x, seed=seed)
    assert (got.interval.lo, got.interval.hi, got.se) == (float(lo), float(hi), float(se))


def test_the_bootstrap_is_seeded():
    x = _heavy(40)
    a = rw.bootstrap_quantiles(x, seed=[42, 1, 0, 3, 8])
    b = rw.bootstrap_quantiles(list(x), seed=(42, 1, 0, 3, 8))
    c = rw.bootstrap_quantiles(x, seed=[42, 1, 0, 3, 9])
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert a.shape == (3, rw.BOOTSTRAP_REPLICATES)
    # The quartiles are ordered in every replicate.
    assert (a[0] <= a[1]).all() and (a[1] <= a[2]).all()
    # Non-finite values are dropped first, so they never move the draws.
    noisy = np.concatenate([x, [np.nan, np.inf]])
    assert np.array_equal(rw.bootstrap_quantiles(noisy, seed=[42, 1, 0, 3, 8]), a)
    assert rw.bootstrap_quantiles([], seed=1).shape == (3, 0)


# --------------------------------------------------------------- the width --


def test_the_robust_width_is_the_iqr_over_1_349_median():
    x = _heavy(300)
    q25, q50, q75 = np.percentile(x, [25, 50, 75])
    value = rw.iqr_resolution(x)
    assert value == (q75 - q25) / 1.349 / q50
    # gaussian.fit_gaussian's own robust σ over the median, to the last bit.
    assert value == gaussian.fit_gaussian(x).sigma_robust / q50
    width = rw.robust_width(x, seed=[42, 0, 0, 5, 8])
    assert width.value == value and width.n == 300
    assert width.interval.method == metrics.METHOD_BOOTSTRAP
    assert width.interval.lo < value < width.interval.hi
    assert "B = 2,000" in width.interval.label and "42/0/0/5/8" in width.interval.label
    assert width.kappa == width.se / value and 0 < width.kappa < 1
    assert width.n_replicates == rw.BOOTSTRAP_REPLICATES


def test_the_robust_floor():
    x = _heavy(40)
    for n in (0, 1, 2, 8, 19):
        width = rw.robust_width(x[:n], seed=1)
        assert width.value is None and width.interval is None and width.se is None
        assert width.kappa is None and f"N = {n} < 20" in width.note
        assert rw.tail_share(x[:n]) is None
    width = rw.robust_width(x[:20], seed=1)
    assert width.value is not None and width.interval is not None and width.se > 0


def test_a_non_positive_median_has_no_width():
    x = np.concatenate([-np.ones(15), np.zeros(10), np.ones(5)])
    assert rw.iqr_resolution(x) is None
    width = rw.robust_width(x)
    assert width.value is None and "not positive" in width.note


def test_the_value_alone_skips_the_bootstrap():
    x = _heavy(50)
    alone = rw.robust_width(x, seed=1, bootstrap=False)
    assert alone.value == rw.iqr_resolution(x)
    assert alone.interval is None and alone.se is None and alone.kappa is None


@pytest.mark.parametrize("c", [0.031, 7.3, 1e-3])
def test_the_robust_width_is_invariant_under_a_rescaled_response(c):
    """IQR(cR)/(1.349·median cR) = IQR(R)/(1.349·median R): the calibration cancels, interval included."""
    x = _heavy(500)
    a = rw.robust_width(x, seed=[42, 4, 0, 10, 8])
    b = rw.robust_width(c * x, seed=[42, 4, 0, 10, 8])
    assert b.value == approx(a.value, rel=1e-12)
    assert (b.interval.lo, b.interval.hi) == approx((a.interval.lo, a.interval.hi), rel=1e-12)
    assert b.se == approx(a.se, rel=1e-10) and b.kappa == approx(a.kappa, rel=1e-10)


def test_a_replicate_with_a_non_positive_median_is_left_out_and_counted():
    """A median R near zero: a few replicates' medians fall to or below zero and are dropped, said so."""
    x = np.concatenate([np.full(11, 0.5), np.full(10, -0.5)])
    width = rw.robust_width(x, seed=2)
    assert width.value is not None
    assert 0 < rw.BOOTSTRAP_REPLICATES - width.n_replicates < rw.BOOTSTRAP_REPLICATES
    assert "non-positive median left out" in width.interval.label


def test_relative_se():
    assert rw.relative_se(0.01, 0.2) == approx(0.05)
    for se, value in ((None, 0.2), (0.01, None), (0.0, 0.2), (0.01, 0.0), (-0.01, 0.2)):
        assert rw.relative_se(se, value) is None


# ------------------------------------------------ the median's bootstrap SE --


@pytest.mark.parametrize("n", [1, 2, 7, 19, 20, 21, 64])
def test_the_median_se_is_the_sd_of_the_intervals_own_replicates(n):
    """``bootstrap_medians`` is the array ``bootstrap_median_interval`` takes its percentiles from."""
    x = _heavy(n, seed=n)
    seed = [42, 0, 1, 7, 2]
    reps = median.bootstrap_medians(x, seed=seed)
    assert reps.shape == ((median.BOOTSTRAP_REPLICATES,) if n else (0,))
    se = rw.median_se(x, seed=seed)
    if n < 2:
        assert se is None
    else:
        assert se == float(np.std(reps, ddof=1))
    interval = median.bootstrap_median_interval(x, seed=seed)
    if n < median.MIN_BOOTSTRAP_N:
        assert interval is None
    else:
        lo, hi = np.quantile(reps, [(1 - 0.95) / 2, (1 + 0.95) / 2])
        assert (interval.lo, interval.hi) == (float(lo), float(hi))
        estimate = median.median_estimate(x, seed=seed)
        assert estimate.interval == interval


def test_bootstrap_medians_drops_non_finite_values_and_is_empty_for_none():
    x = _heavy(30)
    noisy = np.concatenate([[np.nan], x, [np.inf, -np.inf]])
    assert np.array_equal(median.bootstrap_medians(noisy, seed=5), median.bootstrap_medians(x, seed=5))
    assert median.bootstrap_medians([], seed=5).size == 0
    assert median.bootstrap_medians([np.nan]).size == 0
    assert rw.median_se([np.nan, 1.0]) is None


# ------------------------------------------------------------- the tail share --


def test_the_tail_share_by_hand():
    """Beyond 3·IQR/1.349 of the median: 2 of 40 here."""
    core = np.linspace(0.9, 1.1, 38)
    x = np.concatenate([core, [5.0, -3.0]])
    q25, q50, q75 = np.percentile(x, [25, 50, 75])
    limit = 3 * (q75 - q25) / 1.349
    assert np.sum(np.abs(x - q50) > limit) == 2
    assert rw.tail_share(x) == 2 / 40


def test_a_gaussian_has_the_gaussian_tail_share():
    x = np.random.default_rng(11).normal(1.0, 0.1, 400_000)
    assert rw.tail_share(x) == approx(rw.GAUSSIAN_TAIL_SHARE, rel=0.08)
    # Student-t₃ tails carry several times as many.
    assert rw.tail_share(_heavy(400_000)) > 5 * rw.GAUSSIAN_TAIL_SHARE
