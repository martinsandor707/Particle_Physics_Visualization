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
from calosrv.errors import ValidationError
from calosrv.query import features as features_mod
from calosrv.query import features_catalog as catalog
from calosrv.query import showers, stagger

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
    with pytest.raises(ValidationError) as caught:
        catalog.get(ddl.KIND_SINGLE_EVENTS, "angular_spread_circ")
    assert caught.value.extra["field"] == "feature"


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
