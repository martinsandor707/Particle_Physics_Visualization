"""The shared statistics helpers: each against an independent computation.

Every helper has one owner (``calosrv/stats``), and the physics and model
panels both call it, so these pins are what keeps two panels from quoting
different intervals for one sample.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pandas as pd
import pytest

from calosrv.errors import ValidationError
from calosrv.stats import circular, clip, describe, histogram, jackknife, kde, median, metrics
from calosrv.stats import momentum, profile
from calosrv.stats.gaussian import t_quantile_975


# ------------------------------------------------------------- metrics --

@pytest.mark.parametrize("k, n, lo, hi", [
    (0, 10, 0.0, 0.2775),
    (5, 10, 0.2366, 0.7634),
    (10, 10, 0.7225, 1.0),
    (1, 1, 0.2065, 1.0),
])
def test_wilson_reference_values(k, n, lo, hi):
    interval = metrics.wilson_interval(k, n)
    assert interval.method == metrics.METHOD_WILSON
    assert interval.lo == pytest.approx(lo, abs=5e-5)
    assert interval.hi == pytest.approx(hi, abs=5e-5)
    assert 0.0 <= interval.lo <= k / n <= interval.hi <= 1.0


def test_wilson_and_proportion_edges():
    assert metrics.wilson_interval(0, 0) is None
    est = metrics.proportion_estimate(3, 12)
    assert est.value == 0.25 and est.se is None and est.n == 12
    assert est.interval == metrics.wilson_interval(3, 12)


def test_fisher_z_interval_matches_correlation_and_formula():
    rng = np.random.default_rng(7)
    x = rng.normal(size=40)
    y = 0.6 * x + rng.normal(size=40)
    est = metrics.correlation(x, y)
    r = float(np.corrcoef(x, y)[0, 1])
    z, half = math.atanh(r), 1.959963985 / math.sqrt(40 - 3)
    assert est.value == pytest.approx(r)
    assert est.interval.lo == pytest.approx(math.tanh(z - half), rel=1e-12)
    assert est.interval.hi == pytest.approx(math.tanh(z + half), rel=1e-12)
    assert est.interval.method == metrics.METHOD_FISHER
    assert est.interval.label == "95% Fisher-z interval"
    assert est.se == pytest.approx((1 - r * r) / math.sqrt(37))

    iid = metrics.fisher_z_interval(r, 40)
    assert (iid.lo, iid.hi) == (est.interval.lo, est.interval.hi)
    assert "N = 40 events" in iid.label


def test_fisher_z_interval_jackknife_form_and_gates():
    interval = metrics.fisher_z_interval(0.5, 100, se_z=0.1, dof=7)
    half = t_quantile_975(7) * 0.1
    assert interval.lo == pytest.approx(math.tanh(math.atanh(0.5) - half))
    assert interval.hi == pytest.approx(math.tanh(math.atanh(0.5) + half))
    assert interval.method == metrics.METHOD_JACKKNIFE
    assert "8 groups" in interval.label
    assert metrics.fisher_z_interval(0.5, 3) is None
    assert metrics.fisher_z_interval(1.0, 50) is None
    assert metrics.fisher_z_interval(float("nan"), 50) is None
    assert metrics.fisher_z_interval(0.5, 50, se_z=0.1, dof=0) is None


def test_mae_estimate():
    r = np.array([-1.0, 2.0, -3.0, 4.0, np.nan])
    est = metrics.mae_estimate(r)
    a = np.array([1.0, 2.0, 3.0, 4.0])
    se = a.std(ddof=1) / 2.0
    t = t_quantile_975(3)
    assert est.value == pytest.approx(2.5) and est.n == 4
    assert est.se == pytest.approx(se)
    assert (est.interval.lo, est.interval.hi) == pytest.approx((2.5 - t * se, 2.5 + t * se))
    assert est.interval.method == metrics.METHOD_T and "clipped" not in est.interval.label
    # A t-interval reaching below zero is cut there, and the label says so.
    skewed = metrics.mae_estimate(np.array([0.1, -0.1, 0.2, 5.0]))
    assert skewed.interval.lo == 0.0 and "clipped" in skewed.interval.label
    assert metrics.mae_estimate(np.array([0.3])).interval is None
    assert metrics.mae_estimate(np.array([])).value is None


# -------------------------------------------------------------- median --

@pytest.mark.parametrize("n, j, coverage", [(6, 1, 0.96875), (20, 6, 0.9586)])
def test_order_statistic_interval_reference(n, j, coverage):
    x = np.arange(1.0, n + 1.0)[::-1]           # unsorted on purpose
    interval, achieved = median.median_order_interval(x)
    assert achieved == pytest.approx(coverage, abs=5e-5)
    assert (interval.lo, interval.hi) == (float(j), float(n + 1 - j))
    assert interval.method == metrics.METHOD_ORDER


def test_order_statistic_interval_coverage_is_exact():
    """1 - 2F(j-1) against a direct binomial sum, for every n up to 60."""
    for n in range(6, 61):
        _, achieved = median.median_order_interval(np.arange(float(n)))
        pmf = [math.comb(n, k) / 2.0 ** n for k in range(n + 1)]
        j = max(jj for jj in range(1, n + 1) if sum(pmf[:jj]) <= 0.025)
        assert achieved == pytest.approx(1 - 2 * sum(pmf[:j]), abs=1e-12)
        assert achieved >= 0.95
    assert median.median_order_interval(np.arange(5.0)) is None


@pytest.mark.parametrize("n", [21, 40])
def test_exact_beta_bootstrap_matches_resampling(n):
    """The Beta sampler draws the same median distribution as brute resampling."""
    x = np.sort(np.random.default_rng(3).lognormal(size=n))
    beta = median.bootstrap_median_interval(x, replicates=200_000, seed=1)
    rng = np.random.default_rng(2)
    brute = np.median(x[rng.integers(0, n, size=(200_000, n))], axis=1)
    lo, hi = np.quantile(brute, [0.025, 0.975])
    spread = float(x[-1] - x[0])
    assert beta.lo == pytest.approx(lo, abs=0.01 * spread)
    assert beta.hi == pytest.approx(hi, abs=0.01 * spread)


def test_bootstrap_is_seeded_and_gated():
    x = np.random.default_rng(0).normal(size=25)
    a = median.bootstrap_median_interval(x, seed=[42, 1, 0, 3, 2])
    b = median.bootstrap_median_interval(x, seed=[42, 1, 0, 3, 2])
    assert (a.lo, a.hi) == (b.lo, b.hi)
    # With B = 2000 the ends usually land on the same order statistics whatever
    # the seed; with B = 101 the interpolation between replicates shows it moved.
    c = median.bootstrap_median_interval(x, replicates=101, seed=[42, 1, 0, 3, 2])
    d = median.bootstrap_median_interval(x, replicates=101, seed=[42, 1, 0, 3, 3])
    assert (c.lo, c.hi) != (d.lo, d.hi)
    assert a.method == metrics.METHOD_BOOTSTRAP and "42/1/0/3/2" in a.label
    assert median.bootstrap_median_interval(x[:19]) is None


def test_median_estimate_gates():
    assert median.median_estimate(np.array([1.0, 2.0, 3.0])).interval is None
    small = median.median_estimate(np.arange(10.0))
    assert small.bootstrap is None and small.interval is small.order
    big = median.median_estimate(np.arange(30.0))
    assert big.interval is big.bootstrap and big.order is not None
    assert big.value == 14.5


# ------------------------------------------------------------ describe --

def test_describe_matches_pandas():
    v = np.random.default_rng(5).gamma(2.0, size=57)
    d = describe.describe(np.concatenate([v, [np.nan, np.inf]]))
    ref = pd.Series(v).describe()
    assert d.n == 57 and d.n_nonfinite == 2
    for ours, theirs in ((d.mean, "mean"), (d.sd, "std"), (d.min, "min"), (d.q25, "25%"),
                         (d.q50, "50%"), (d.q75, "75%"), (d.max, "max")):
        assert ours == pytest.approx(ref[theirs], rel=1e-12)
    assert d.sd_population == pytest.approx(v.std(ddof=0))
    assert d.note == ""


def test_describe_low_n_notes():
    assert describe.describe(np.array([2.0])).sd is None
    assert "1 d.o.f." in describe.describe(np.array([1.0, 2.0])).note
    assert "interpolate" in describe.describe(np.arange(5.0)).note
    assert describe.describe(np.array([])).mean is None


def test_weighted_quantiles_against_expanded_sample():
    # Energy 1, 3, 4, 2 in four 1 mm bins starting at 10 mm.
    lo = np.array([12.0, 10.0, 13.0, 11.0])
    w = np.array([4.0, 1.0, 2.0, 3.0])
    q25, q50, q90 = describe.weighted_quantiles(lo, w, 1.0, (0.25, 0.5, 0.9))
    # Cumulative 1, 4, 8, 10: 2.5 of 10 lies half-way through bin 11.
    assert q25 == pytest.approx(11.5)
    assert q50 == pytest.approx(12.25)
    assert q90 == pytest.approx(13.5)
    assert describe.weighted_quantiles(lo, np.zeros(4), 1.0, (0.5,)) == [None]


# ------------------------------------------------------------ circular --

def test_wrap_angle_half_open():
    assert circular.wrap_angle(math.pi) == pytest.approx(math.pi)
    assert circular.wrap_angle(-math.pi) == pytest.approx(math.pi)
    assert circular.wrap_angle(3 * math.pi) == pytest.approx(math.pi)
    assert circular.wrap_angle(-0.5) == pytest.approx(-0.5)
    arr = circular.wrap_angle(np.array([0.0, 2 * math.pi + 0.1, -math.pi]))
    assert arr == pytest.approx([0.0, 0.1, math.pi])


def test_circular_summary():
    phi = np.array([math.pi - 0.1, -math.pi + 0.1])
    s = circular.describe_circular(phi)
    assert abs(s.mean_direction) == pytest.approx(math.pi)
    assert s.resultant == pytest.approx(math.cos(0.1))
    assert s.circular_sd == pytest.approx(math.sqrt(-2 * math.log(math.cos(0.1))))
    uniform = circular.describe_circular(np.linspace(-math.pi, math.pi, 40, endpoint=False))
    assert uniform.resultant == pytest.approx(0.0, abs=1e-12)
    assert "uniform" in uniform.note


def test_rayleigh_has_one_owner():
    from calosrv.grid import frame

    assert frame.rayleigh_p is circular.rayleigh_p
    assert circular.rayleigh_p(10, 0.3) == pytest.approx(math.exp(-0.9))


# ----------------------------------------------------------- jackknife --

def _group_sums(data: np.ndarray, groups: np.ndarray):
    gs = np.unique(groups)
    n_g = np.array([np.sum(groups == g) for g in gs], dtype=float)
    s_g = np.stack([data[groups == g].sum(axis=0) for g in gs])
    q_g = np.stack([data[groups == g].T @ data[groups == g] for g in gs])
    return n_g, s_g, q_g


def test_pearson_from_sums_matches_numpy():
    data = np.random.default_rng(11).normal(size=(300, 4))
    data[:, 1] += 0.8 * data[:, 0]
    r = jackknife.pearson_from_sums(300.0, data.sum(axis=0), data.T @ data)
    assert r == pytest.approx(np.corrcoef(data.T), abs=1e-12)


def test_grouped_jackknife_matches_explicit_leave_one_group_out():
    rng = np.random.default_rng(12)
    data = rng.normal(size=(500, 3))
    data[:, 2] += 0.5 * data[:, 0]
    groups = rng.integers(0, 16, size=500)
    n_g, s_g, q_g = _group_sums(data, groups)
    jk = jackknife.fisher_jackknife(n_g, s_g, q_g, n_events=500)
    z_loo = np.array([np.arctanh(np.corrcoef(data[groups != g].T)[0, 2])
                      for g in np.unique(groups)])
    se = math.sqrt(15 / 16 * np.sum((z_loo - z_loo.mean()) ** 2))
    assert jk.r[0, 2] == pytest.approx(np.corrcoef(data.T)[0, 2], abs=1e-12)
    assert jk.se_z[0, 2] == pytest.approx(se, rel=1e-9)
    interval = jk.interval(0, 2)
    assert interval.method == metrics.METHOD_JACKKNIFE
    assert (interval.lo, interval.hi) == pytest.approx((jk.lo[0, 2], jk.hi[0, 2]))
    assert jk.n_eff[0, 2] == pytest.approx(3 + 1 / se ** 2)


def test_jackknife_gates():
    data = np.random.default_rng(1).normal(size=(6, 2))
    n_g, s_g, q_g = _group_sums(data, np.arange(6) % 3)
    few = jackknife.fisher_jackknife(n_g, s_g, q_g, n_events=6)
    assert np.isfinite(few.r[0, 1]) and np.isnan(few.lo[0, 1])     # 3 groups: r, no interval
    none = jackknife.fisher_jackknife(n_g[:1], s_g[:1], q_g[:1], n_events=2)
    assert np.isnan(none.r[0, 1])
    assert jackknife.n_groups(10) == 10 and jackknife.n_groups(10_000) == 64


def test_mardia_r():
    rng = np.random.default_rng(4)
    phi = rng.uniform(-math.pi, math.pi, size=2000)
    x = np.cos(phi - 0.7) + 0.1 * rng.normal(size=2000)
    data = np.column_stack([x, np.cos(phi), np.sin(phi)])
    r = np.corrcoef(data.T)
    big = jackknife.mardia_r(r[0, 1], r[0, 2], r[1, 2])
    assert 0.95 < big <= 1.0
    noise = rng.normal(size=2000)
    r = np.corrcoef(np.column_stack([noise, np.cos(phi), np.sin(phi)]).T)
    assert jackknife.mardia_r(r[0, 1], r[0, 2], r[1, 2]) < 0.1
    # Two azimuths: cos and sin collinear, R is the |r| on the one that varies.
    assert jackknife.mardia_r(0.1, 0.2, 1.0) == pytest.approx(0.1)
    assert jackknife.mardia_r(float("nan"), -0.3, float("nan")) == pytest.approx(0.3)
    assert jackknife.mardia_r(float("nan"), float("nan"), float("nan")) is None


# ------------------------------------------------------------- profile --

def test_profile_unit_clusters_reduce_to_s_over_root_n():
    f = np.random.default_rng(8).uniform(size=(12, 5))      # 12 showers x 5 bins
    est = profile.profile_estimate(f.sum(axis=0), (f * f).sum(axis=0), 12)
    assert est.mean == pytest.approx(f.mean(axis=0))
    assert est.sd == pytest.approx(f.std(axis=0, ddof=1))
    assert est.half95 == pytest.approx(t_quantile_975(11) * f.std(axis=0, ddof=1) / math.sqrt(12))
    assert est.provisional and est.label == "weak (N = 12)"


def test_profile_cluster_robust_matches_explicit():
    rng = np.random.default_rng(9)
    f = rng.uniform(size=(30, 4))
    event = np.repeat(np.arange(15), 2)                      # two showers per event
    c_e = np.stack([f[event == e].sum(axis=0) for e in range(15)])
    m_e = np.full(15, 2.0)
    m = f.mean(axis=0)
    est = profile.profile_estimate(
        f.sum(axis=0), (f * f).sum(axis=0), 30,
        cc=(c_e ** 2).sum(axis=0), mc=(m_e[:, None] * c_e).sum(axis=0),
        m2=float((m_e ** 2).sum()), n_clusters=15)
    resid = c_e - m_e[:, None] * m
    se = np.sqrt(15 / 14 * (resid ** 2).sum(axis=0)) / 30
    assert est.half95 == pytest.approx(t_quantile_975(14) * se)
    assert not est.provisional


def test_profile_gates():
    one = profile.profile_estimate(np.array([0.2, 0.8]), np.array([0.04, 0.64]), 1)
    assert one.sd is None and one.half95 is None
    assert one.label == "single shower, not an ensemble"
    two = profile.profile_estimate(np.array([0.5]), np.array([0.13]), 2)
    assert two.dof_note == "1 d.o.f." and two.half95 is not None


# ----------------------------------------------------------------- KDE --

def test_kde_integrates_and_matches_direct_sum():
    v = np.random.default_rng(10).normal(5.0, 2.0, size=400)
    h = kde.silverman_bandwidth(v)
    sd = v.std(ddof=1)
    iqr = np.subtract(*np.percentile(v, [75, 25])) / 1.349
    assert h == pytest.approx(0.9 * min(sd, iqr) * 400 ** -0.2)
    res = kde.gaussian_kde_binned(v, -5.0, 15.0, points=401)
    x = np.asarray(res.x)
    direct = np.exp(-0.5 * ((x[:, None] - v[None, :]) / h) ** 2).sum(axis=1) / (
        400 * h * math.sqrt(2 * math.pi))
    assert np.max(np.abs(np.asarray(res.pdf) - direct)) < 0.01 * direct.max()
    assert np.trapezoid(res.pdf, x) == pytest.approx(1.0, abs=2e-3)
    assert res.scaled(0.5) == pytest.approx([400 * 0.5 * p for p in res.pdf])


def test_kde_gates():
    assert not kde.gaussian_kde_binned(np.arange(7.0), 0, 7).drawn
    assert kde.gaussian_kde_binned(np.arange(8.0), 0, 7).drawn
    assert not kde.gaussian_kde_binned(np.ones(20), 0, 2).drawn
    layers = np.repeat(np.arange(3) * 20.5, 50)                # three lattice values
    suppressed = kde.gaussian_kde_binned(layers, 0, 41, quantum=20.5, bandwidth=5.0)
    assert not suppressed.drawn and "quantum" in suppressed.notes[0]


# ----------------------------------------------------- momentum classes --

def test_windows_are_half_open_and_refuse_overlap():
    ws = momentum.windows()
    assert [w.label for w in ws][:2] == ["1 ± 0.5 GeV", "2 ± 0.5 GeV"]
    assert ws[0].contains(0.5) and not ws[0].contains(1.5) and ws[1].contains(1.5)
    with pytest.raises(ValidationError) as err:
        momentum.windows((1.0, 1.6))
    assert err.value.extra["field"] == "p_slices"
    feature = momentum.windows(momentum.FEATURE_CENTRES_GEV)
    assert (feature[-1].lo, feature[-1].hi) == (19.0, 20.0)


def test_case_sql_matches_assign():
    p = np.random.default_rng(13).uniform(0, 20, size=500)
    bins = np.floor(p).astype(int)
    con = duckdb.connect()
    con.register("t", pd.DataFrame({"e1": p, "e1_bin": bins}))
    for classes in (momentum.windows(), momentum.unit_bins(0, 19), momentum.binary_label()):
        sql = momentum.case_sql(classes, "e1", "e1_bin")
        got = np.array([r[0] for r in con.execute(f"SELECT {sql} FROM t").fetchall()])
        assert (got == momentum.assign(p, classes, bins)).all()
    outside = momentum.assign(np.array([3.0]), momentum.windows())
    assert outside[0] == momentum.OUTSIDE


def test_parse_slicing_and_bin_relabel():
    assert momentum.parse_slicing(None).mode == "notebook"
    assert len(momentum.parse_slicing("bins", bin_range=(0, 19)).classes) == 20
    listed = momentum.parse_slicing("3, 7")
    assert [c.centre for c in listed.classes] == [3.0, 7.0]
    for bad in ("x", "-1", "1,1.2"):
        with pytest.raises(ValidationError):
            momentum.parse_slicing(bad)
    classes, notices = momentum.relabel_bins(momentum.unit_bins(0, 2),
                                             {0: (0.1, 0.9), 1: (0.5, 1.9)})
    assert classes[0].label == "0–1 GeV"
    assert classes[1].label.startswith("bin 1 (p 0.5–1.9")
    assert "bin 1" in notices[0]


# ------------------------------------------------- ranges and histograms --

@pytest.mark.parametrize("lo, hi, expected", [
    (0.0, 0.034, (0.0, 0.035, 0.005)),
    (-0.031, 0.022, (-0.035, 0.025, 0.005)),
    (3.0, 7.3, (3.0, 7.5, 0.5)),
    (0.3, 0.7, (0.3, 0.7, 0.05)),
])
def test_nice_range_fine(lo, hi, expected):
    assert clip.nice_range(lo, hi, fine=True) == pytest.approx(expected)


def test_nice_range_default_unchanged():
    assert clip.nice_range(0.0, 0.034) == (0.0, 0.1, 0.1)
    assert clip.nice_range(0.0, 9.197060758) == (0.0, 10.0, 1.0)


def test_count_histogram():
    h = histogram.count_histogram(np.array([-1.0, 0.0, 0.5, 1.0, 2.0, np.nan]),
                                  np.array([0.0, 0.5, 1.0]))
    assert h.counts == [1, 2] and (h.n, h.n_in_range, h.n_below, h.n_above) == (5, 3, 1, 1)
    assert all(isinstance(c, int) for c in h.counts)
