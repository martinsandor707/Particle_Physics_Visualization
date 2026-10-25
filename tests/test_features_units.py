"""The feature explorer's pure parts: column vocabulary, lattice quanta, scales, the comb test.

No server and no ingested data: the SQL the catalogue writes is bound against
empty tables built from ``ddl``'s own column lists, so a feature that names a
column no kind's event table has fails here rather than in a request.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pytest

from calosrv.db import ddl
from calosrv.errors import CapabilityError, ValidationError
from calosrv.query import correlations
from calosrv.query import features as features_mod
from calosrv.query import features_catalog as catalog
from calosrv.query import showers, stagger
from calosrv.stats import circular

KIND_TABLES = {
    ddl.KIND_TWO_SHOWER: (ddl.EVENT_COLUMNS_V2, ("a", "b")),
    ddl.KIND_SINGLE_HITS: (ddl.EVENT_SINGLE_COLUMNS, ("a",)),
    ddl.KIND_SINGLE_EVENTS: (ddl.EVENT_FEATURE_COLUMNS, ("a",)),
}


class _Record:
    """Just enough of an experiment record for ``showers.of``."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.table_name = "t"


@pytest.mark.parametrize("kind", list(KIND_TABLES))
def test_every_feature_binds_against_its_kinds_event_table(kind):
    columns, shower_keys = KIND_TABLES[kind]
    con = duckdb.connect(":memory:")
    con.execute(ddl.create_event_table("t", columns))
    for key in shower_keys:
        (shower,) = showers.of(_Record(kind), key)
        for coord in catalog.COORD_SYSTEMS:
            select = ", ".join(f"{sql} AS v_{fid}"
                               for fid, sql in catalog.select_list(kind, coord, shower))
            hits = catalog.hits_sql(kind, shower)
            con.execute(f"SELECT {shower.momentum}, {shower.momentum_bin}, {hits}, {select} "
                        f"FROM t WHERE {hits} >= 2").fetchall()
    label = catalog.label_sql(kind)
    if label:
        con.execute(f"SELECT {label} FROM t").fetchall()


def test_the_catalogue_follows_the_notebook_order():
    notebook = [f.id for f in catalog.FEATURES if f.notebook]
    assert notebook == [
        "width", "height", "depth", "depth_range", "volume", "num_hits", "total_hit_energy",
        "centroid_x", "centroid_y", "centroid_z", "mean_r", "std_r", "max_r", "weighted_r_mean",
        "avg_theta", "avg_phi", "angular_spread", "numerical_density", "energy_density"]
    assert [f.id for f in catalog.offered(ddl.KIND_SINGLE_EVENTS)] == notebook
    assert catalog.EPS_PAIR_FEATURES == ("volume", "numerical_density", "energy_density")
    # A hit-kind feature asked of the aggregate: the data cannot serve it, a capability refusal.
    with pytest.raises(CapabilityError) as caught:
        catalog.get(ddl.KIND_SINGLE_EVENTS, "angular_spread_circ", capability="feat-hist2d")
    assert caught.value.extra["field"] == "feature"
    assert caught.value.extra["capability"] == "feat-hist2d"
    assert caught.value.extra["kind"] == ddl.KIND_SINGLE_EVENTS
    # An unknown id is a plain validation error.
    with pytest.raises(ValidationError) as caught:
        catalog.get(ddl.KIND_SINGLE_EVENTS, "widht")
    assert not isinstance(caught.value, CapabilityError)


def test_circular_variants_sql_on_known_sums():
    """avg_phi_circ is atan2(Σ sin, Σ cos); angular_spread_circ is SD(θ) + √(−2 ln R̄)."""
    con = duckdb.connect(":memory:")
    con.execute(ddl.create_event_table("t", ddl.EVENT_SINGLE_COLUMNS))
    angles = np.array([3.0, -3.0, 2.9])           # straddling the ±π cut
    c, s = float(np.cos(angles).sum()), float(np.sin(angles).sum())
    con.execute("INSERT INTO t (event_number, n_hits_a, sum_cos_phi_a_abs, sum_sin_phi_a_abs, "
                "sd_theta_a_abs, sum_r_a_abs) VALUES (1, 3, ?, ?, 0.01, 10.0)", [c, s])
    (shower,) = showers.of(_Record(ddl.KIND_SINGLE_HITS), "a")
    mean_sql, spread_sql = (
        catalog.column_sql(ddl.KIND_SINGLE_HITS, catalog.BY_ID[fid], "lab", shower)
        for fid in ("avg_phi_circ", "angular_spread_circ"))
    mean, spread = con.execute(f"SELECT {mean_sql}, {spread_sql} FROM t").fetchone()
    assert mean == pytest.approx(math.atan2(s, c))
    assert abs(mean) > 3.0                          # near ±π, not the arithmetic 0.97
    r = math.hypot(c, s) / 3
    assert spread == pytest.approx(0.01 + math.sqrt(-2 * math.log(r)))


def test_measured_step_is_the_common_divisor_of_the_values():
    assert features_mod._measured_step(np.array([102.5, 553.5, 861.0])) == pytest.approx(20.5)
    lattice = (np.float32(3662.4) + np.arange(60, dtype=np.float32) * np.float32(20.5))
    sample = lattice.astype(np.float64)[[2, 9, 31]]
    assert features_mod._measured_step(sample) == pytest.approx(20.5)
    assert features_mod._measured_step(np.array([4.0])) is None
    assert features_mod._measured_step(np.array([1.0, 1.37, 2.71])) is None


def test_snapped_edges_hold_whole_quanta_off_the_lattice():
    edges, per_bin = features_mod._snapped_edges(100.0, 1100.0, 30, 20.5, 102.5)
    assert per_bin == 2
    assert np.allclose(np.diff(edges), 41.0)
    assert edges[0] <= 100.0 and edges[-1] >= 1100.0
    lattice = 102.5 + 20.5 * np.arange(-5, 60)
    counts, _ = np.histogram(lattice[(lattice > edges[0]) & (lattice < edges[-1])], edges)
    assert set(counts.tolist()) == {per_bin}          # every bin holds the same number of values


def test_auto_scale_and_its_refusals():
    def scale(fid, coord, requested, values):
        return features_mod.resolve_scale(catalog.BY_ID[fid], coord, requested, values, "scale")[0]

    wide = np.geomspace(1e-3, 1.0, 500)
    assert scale("total_hit_energy", "lab", "auto", wide) == "log"
    assert scale("std_r", "lab", "auto", np.linspace(30, 200, 500)) == "linear"
    # Quantised: linear on auto however many decades, refused on log.
    assert scale("num_hits", "lab", "auto", np.geomspace(2, 1000, 500)) == "linear"
    with pytest.raises(ValidationError):
        scale("depth_range", "trans", "log", wide)
    # Local depth is not on the layer lattice: log is allowed there.
    assert scale("depth_range", "local", "log", wide) == "log"
    assert scale("avg_phi", "lab", "auto", wide) == "circular"
    assert scale("centroid_x", "lab", "auto", wide) == "linear"


def test_counting_noise_lag1_reference():
    """Independent counts give a detrended lag-1 of −10/72; a clean alternation is far below."""
    rng = np.random.default_rng(3)
    lags = [stagger.profile_lag1(rng.poisson(400.0, 400).astype(float)) for _ in range(300)]
    assert np.mean(lags) == pytest.approx(features_mod.NOISE_LAG1, abs=0.02)
    combed = np.tile([400.0, 200.0], 30) + rng.normal(0, 5, 60)
    verdict = features_mod._comb(combed)
    assert verdict["combed"] is True and verdict["lag1"] < verdict["threshold"]
    flat = features_mod._comb(rng.poisson(400.0, 60).astype(float))
    assert flat["combed"] is False
    assert features_mod._comb(np.ones(10))["lag1"] is None


def test_a_comb_is_blamed_on_the_lattice_only_where_there_is_one():
    def cause(fid, coord="lab"):
        return features_mod.comb_cause(catalog.BY_ID[fid], coord)

    assert cause("width") == cause("height") == "lattice"          # irregular lattice
    assert cause("depth_range", "trans") == "lattice"              # whole layers
    assert cause("depth_range", "local") is None                   # off the layer lattice
    assert cause("num_hits") == "integer"
    for fid in ("total_hit_energy", "centroid_x", "std_r"):
        assert cause(fid) is None
    combed = np.tile([400.0, 200.0], 30) + np.random.default_rng(5).normal(0, 5, 60)
    lattice = features_mod._comb(combed, "lattice")
    assert "segmentation" in lattice["note"] and lattice["cause"] == "lattice"
    neutral = features_mod._comb(combed, None)
    assert neutral["combed"] is True and neutral["cause"] is None
    assert "segmentation, not" not in neutral["note"] and "noise alone" in neutral["note"]


def _bundle(n: int = 600, seed: int = 11) -> features_mod.FeatureBundle:
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.0, 20.0, n)
    width = rng.lognormal(5.8, 0.6, n)
    width[:7] = 1e-6
    values = {f.id: rng.lognormal(1.0, 0.5, n) for f in catalog.FEATURES}
    values.update(width=width, volume=width * values["height"] * values["depth"],
                  avg_phi=rng.uniform(-math.pi, math.pi, n),
                  avg_phi_circ=rng.uniform(-math.pi, math.pi, n))
    values["numerical_density"] = values["num_hits"] / values["volume"]
    return features_mod.FeatureBundle(
        table_name="t", kind=ddl.KIND_SINGLE_HITS, coord_system="lab", shower="a",
        event_number=np.arange(n), p=p, bin=np.floor(p).astype(np.int64), label=None,
        values=values, n_selected=n, n_excluded_single_hit=0)


def _label_classes(bundle):
    classes = features_mod.momentum.binary_label()
    return features_mod.ClassSet("label", classes, features_mod.momentum.assign(bundle.p, classes),
                                 "incident momentum p")


def test_corr_matrix_path_agrees_with_the_pairwise_path():
    bundle = _bundle()
    cs = _label_classes(bundle)
    fast = features_mod.corr_view(bundle, cs, features_mod.POOLED, exclude_eps=True)
    # One missing value in a feature sends the view down the per-pair path.
    bundle.values["std_r"][-1] = np.nan
    slow = features_mod.corr_view(bundle, cs, features_mod.POOLED, exclude_eps=True)
    order, k = fast["order"], len(fast["order"])
    position = 0
    for i in range(k):
        for j in range(i, k):
            if "std_r" not in (order[i], order[j]):
                assert fast["r"][position] == pytest.approx(slow["r"][position], abs=2e-6)
                assert fast["n_pairs"][position] == slow["n_pairs"][position]
            else:
                assert slow["n_pairs"][position] == fast["n_pairs"][position] - 1
            eps = {order[i], order[j]} & set(catalog.EPS_PAIR_FEATURES)
            assert fast["n_pairs"][position] == fast["n"] - (7 if eps else 0)
            position += 1
    assert fast["n_excluded_eps"] == 7
    # The azimuth cells read shared grouped sums on the fast path (all events, or all but
    # the floored ones) and their own per pair on the slow one: the same numbers.
    slow_cells = {(c["row"], c["col"]): c for c in slow["circular_cells"]}
    compared = 0
    for cell in fast["circular_cells"]:
        if "std_r" in (cell["row"], cell["col"]):
            continue
        other = slow_cells[(cell["row"], cell["col"])]
        for key in ("n", "n_azimuths", "value", "se", "se_z", "ci95", "parity_r", "null_R2"):
            assert other[key] == pytest.approx(cell[key], rel=1e-5), (cell["row"], cell["col"], key)
        compared += cell["value"] is not None and cell["se"] is not None
    assert compared >= 15
    floored_pair = next(c for c in fast["circular_cells"] if c["row"] == "volume")
    assert floored_pair["n"] == fast["n"] - 7


def test_corr_of_an_empty_class_is_served_empty():
    bundle = _bundle()
    cs = _label_classes(bundle)
    cs.index[:] = cs.index.dtype.type(features_mod.momentum.OUTSIDE)
    body = features_mod.corr_view(bundle, cs, 0, exclude_eps=True)
    assert body["n"] == 0 and all(r is None for r in body["r"])
    assert all(c["value"] is None and c["reason"] for c in body["circular_cells"])


def test_describe_never_averages_an_azimuth():
    bundle = _bundle()
    cs = _label_classes(bundle)
    table = features_mod.describe_view(bundle, cs, exclude_eps=False)["table"]
    for fid in ("avg_phi", "avg_phi_circ"):
        assert all(v is None for key in ("mean", "sd", "q50") for v in table[fid][key])
        assert all(0 <= r <= 1 for r in table[fid]["circular"]["resultant"])
    assert all(v is not None for v in table["width"]["mean"])
    assert table["width"]["n_eps"] == [int((bundle.floored("width") & cs.mask(c.index)).sum())
                                       for c in cs.classes]


@pytest.mark.parametrize("per_class, provisional_scale", [(10, True), (5, False)])
def test_weak_classes_set_only_a_provisional_y_range(per_class, provisional_scale):
    """No class reaches N = 15: curves (N ≥ 8) set a provisional range; strips alone set none."""
    bundle = _bundle(n=5 * per_class)
    bundle.p = np.repeat([1.0, 2.0, 5.0, 10.0, 19.5], per_class)
    bundle.bin = np.floor(bundle.p).astype(np.int64)
    classes = features_mod.momentum.windows(features_mod.momentum.FEATURE_CENTRES_GEV)
    cs = features_mod.ClassSet("windows", classes, features_mod.momentum.assign(bundle.p, classes),
                               "incident momentum p")
    body = features_mod.hist_view(bundle, cs, catalog.BY_ID["total_hit_energy"], "linear",
                                  False, None)
    assert body["axis"]["provisional"] and body["y_max"]["provisional"]
    assert all(s["draw"] == "strip" and len(s["strip"]) == per_class for s in body["series"])
    if provisional_scale:
        assert all(s["kde"] is not None for s in body["series"])
        assert body["y_max"]["count"] > 0 and body["y_max"]["density"] > 0
    else:
        assert all(s["kde"] is None for s in body["series"])
        assert body["y_max"]["count"] is None and body["y_max"]["density"] is None


# ---------------------------------------------------- formulas, by hand --

#: Literature quantiles (not the module's tables): t(0.975, ν) and χ²(0.975 / 0.025, ν).
T_975 = {1: 12.7062047, 2: 4.30265273, 7: 2.36462425}
CHI2_HI = {1: 5.02388619, 2: 7.37775891, 7: 16.0127643}
CHI2_LO = {1: 0.000982069, 2: 0.0506356, 7: 1.68986918}
C4 = {2: 0.7978845608, 3: 0.8862269255, 6: 0.9515332, 8: 0.9650304}


def _window_bundle(sizes, seed=29):
    """Classes of the given sizes in the first windows (1, 2, 5 GeV), values drawn at random."""
    p = np.concatenate([np.full(n, centre) for n, centre in zip(sizes, (1.0, 2.0, 5.0, 10.0))])
    bundle = _bundle(n=int(p.size), seed=seed)
    bundle.values["width"] = np.random.default_rng(seed).lognormal(5.8, 0.6, p.size)
    bundle.p = p
    bundle.bin = np.floor(p).astype(np.int64)
    classes = features_mod.momentum.windows(features_mod.momentum.FEATURE_CENTRES_GEV)
    cs = features_mod.ClassSet("windows", classes, features_mod.momentum.assign(p, classes),
                               "incident momentum p")
    return bundle, cs


def test_describe_intervals_c4_and_low_n_notes_follow_their_formulas():
    """mean ± t(N − 1)·s/√N, s·√((N − 1)/χ²), s/√(2(N − 1)), c4(N) at N = 2, 3, 8, and the
    '1 d.o.f.' label at N = 2; with floored widths left out, the width's c4 is c4(6)."""
    bundle, cs = _window_bundle((2, 3, 8))
    bundle.values["width"][-2:] = 1e-6                     # two floored in the class of 8
    body = features_mod.describe_view(bundle, cs, exclude_eps=True)
    table = body["table"]
    hits = table["num_hits"]
    for i, n in enumerate((2, 3, 8)):
        v = bundle.values["num_hits"][cs.mask(i)]
        mean, sd = v.mean(), v.std(ddof=1)
        half = T_975[n - 1] * sd / math.sqrt(n)
        assert hits["n"][i] == n
        assert hits["mean_lo"][i] == pytest.approx(mean - half, rel=1e-3)
        assert hits["mean_hi"][i] == pytest.approx(mean + half, rel=1e-3)
        assert hits["sd_lo"][i] == pytest.approx(sd * math.sqrt((n - 1) / CHI2_HI[n - 1]), rel=1e-3)
        assert hits["sd_hi"][i] == pytest.approx(sd * math.sqrt((n - 1) / CHI2_LO[n - 1]), rel=1e-3)
        assert hits["sd_se"][i] == pytest.approx(sd / math.sqrt(2 * (n - 1)), rel=1e-5)
        assert hits["c4"][i] == pytest.approx(C4[n], rel=1e-6)
        assert hits["robust"][i] is False
    notes = body["notes_by_n"]
    assert "1 d.o.f." in notes["2"] and "1 d.o.f." not in notes["3"]
    assert notes["8"].startswith("Quartiles interpolate")
    # The width of the third class lost two floored events: its labels follow N = 6.
    assert table["width"]["n"][2] == 6 and table["width"]["n_eps"][2] == 2
    assert table["width"]["c4"][2] == pytest.approx(C4[6], rel=1e-6)
    assert hits["c4"][2] == pytest.approx(C4[8], rel=1e-6)
    assert body["class_stats"][2] == {"index": 2, "n": 8}
    # An azimuth: no c4, no SD's SE, and its circular note passed through.
    phi = table["avg_phi"]
    assert phi["c4"] == [None] * len(cs.classes) and phi["sd_se"] == [None] * len(cs.classes)
    assert phi["circular"]["note"][3] == "No finite angles in this selection."
    assert "note" not in phi


def _regression_r(x, phi):
    design = np.column_stack([np.ones_like(phi), np.cos(phi), np.sin(phi)])
    beta, *_ = np.linalg.lstsq(design, x, rcond=None)
    residual = x - design @ beta
    centred = x - x.mean()
    return math.sqrt(max(0.0, 1.0 - residual @ residual / (centred @ centred)))


def test_corr_serves_circular_measures_for_azimuths():
    """Mardia's R by least squares, its delete-one-event jackknife SE, r_c of the two
    azimuths with its jackknife interval on Fisher z, and the notebook's linear r as parity
    only - which alone moves when the ±π cut does."""
    bundle, cs = _window_bundle((40,), seed=31)
    rng = np.random.default_rng(31)
    phi = rng.uniform(-math.pi, math.pi, 40)
    bundle.values["avg_phi"] = phi
    bundle.values["avg_phi_circ"] = circular.wrap_angle(phi + rng.normal(0, 0.3, 40))
    bundle.values["total_hit_energy"] = 2.0 + np.cos(phi - 1.0) + 0.4 * rng.normal(size=40)
    body = features_mod.corr_view(bundle, cs, 0, exclude_eps=False)
    assert body["scale"] == correlations.R_SCALE
    cells = {(c["row"], c["col"]): c for c in body["circular_cells"]}
    for c in cells.values():
        assert body["r"][c["position"]] is None and body["lo"][c["position"]] is None
    energy = cells[("total_hit_energy", "avg_phi")]
    x = bundle.values["total_hit_energy"]
    assert energy["measure"] == "mardia" and energy["n_azimuths"] == 40
    assert energy["value"] == pytest.approx(_regression_r(x, phi), rel=1e-5)
    loo = np.array([_regression_r(np.delete(x, k), np.delete(phi, k)) for k in range(40)])
    assert energy["se"] == pytest.approx(math.sqrt(39 / 40 * np.sum((loo - loo.mean()) ** 2)),
                                         rel=1e-5)
    assert energy["null_R2"] == pytest.approx(2 / 39, rel=1e-5)
    assert energy["parity_r"] == pytest.approx(np.corrcoef(x, phi)[0, 1], rel=1e-5)
    both = cells[("avg_phi", "avg_phi_circ")]
    assert both["measure"] == "circular_circular" and both["parity_r"] is None
    r_c = circular.circular_correlation(phi, bundle.values["avg_phi_circ"])
    assert both["value"] == pytest.approx(r_c, rel=1e-5)
    lo, hi = both["ci95"]
    assert lo < both["value"] < hi and both["se_z"] > 0
    assert cells[("avg_phi", "avg_phi")]["value"] == 1.0
    # Moving the cut by π: the parity r changes, the circular measures do not.
    bundle.values["avg_phi"] = circular.wrap_angle(phi + math.pi) - math.pi
    moved = {(c["row"], c["col"]): c for c in features_mod.corr_view(
        bundle, cs, 0, exclude_eps=False)["circular_cells"]}
    assert moved[("total_hit_energy", "avg_phi")]["value"] == pytest.approx(energy["value"],
                                                                            rel=1e-5)
    assert moved[("avg_phi", "avg_phi_circ")]["value"] == pytest.approx(both["value"], rel=1e-5)
    assert moved[("total_hit_energy", "avg_phi")]["parity_r"] != pytest.approx(
        energy["parity_r"], abs=0.05)


def test_corr_gates_mardia_on_distinct_azimuths():
    bundle, cs = _window_bundle((30,), seed=37)
    bundle.values["avg_phi"] = np.resize([0.1, 1.4, 2.9, -2.2, -0.8, 2.0, -1.5], 30)
    body = features_mod.corr_view(bundle, cs, 0, exclude_eps=False)
    cell = next(c for c in body["circular_cells"]
                if (c["row"], c["col"]) == ("width", "avg_phi"))
    assert (cell["n"], cell["n_azimuths"], cell["value"], cell["se"]) == (30, 7, None, None)
    assert cell["reason"] == ("Mardia's R needs 8 distinct azimuths; this class has 7. Three "
                              "directions fit any variable exactly (R = 1), and a few cannot "
                              "constrain a dependence on the direction.")


def test_floored_volumes_do_not_set_the_log_axis():
    """1.2% floored widths make 1.2% of the volumes ~10⁻⁵ mm³: the range and the automatic
    log scale follow the measured volumes; the floored ones are counted below the axis."""
    bundle = _bundle()
    cs = _label_classes(bundle)
    body = features_mod.hist_view(bundle, cs, catalog.BY_ID["volume"], "auto", False, None)
    measured = bundle.values["volume"][~bundle.volume_floored()]
    assert body["axis"]["scale"] == "log"
    assert body["axis"]["lo"] > math.log10(np.percentile(measured, 1)) - 1.0
    assert sum(s["n_floored"] for s in body["series"]) == 7
    assert all(s["n_below"] >= s["n_floored"] for s in body["series"])
    assert any("n_floored" in note for note in body["view_notes"])
