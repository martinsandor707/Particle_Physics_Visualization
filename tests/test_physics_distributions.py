"""C4, the per-momentum-bin distributions, against independent computations.

The footprint splat of u, v and w against a NumPy re-implementation of the
rotated sub-deposits; the exactness of every count (eighths of a hit that sum
to each series' hits); hit energy's display bins as whole merges of the
0.01-decade fine histogram; θ, φ and p against ``np.histogram`` in both
weightings, with the hit weighting equal to a histogram over the hits
themselves; φ over its full period with a resultant and never a mean; the comb
measured before any crop; the display window and the guard's coarsening
conserving every count; the physics cache and the sampled preview.

Runs on the two-event demonstration file (four showers in four momentum bins).
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.encode.numbers import sig
from calosrv.query import (
    density, filters, hit_distributions, physics_cache, sampling, shower_distributions,
)
from calosrv.query.hit_distributions import AxisCounts, HitBundle
from calosrv.query.shower_distributions import SeriesClass, ShowerSample
from calosrv.query.stagger import profile_lag1
from calosrv.stats import circular, histogram
from calosrv.text import signed_hyphens

CHOICES = ("a", "b", "both")
ORIGINS = {"a": (0,), "b": (1, 2), "both": (0, 1, 2)}


@pytest.fixture(scope="module")
def c4(ingested):
    """The demonstration experiment, its full selection and the helpers every test reads."""
    from calosrv.db import registry

    with ingested["database"].read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
    return {"record": record, "spec": filters.build(record), "settings": ingested["settings"]}


def _hit(cursor, c4, quantity, shower="both", low=1.0, high=99.0, preview=False, coarsen=1):
    prepared = hit_distributions.prepare(
        cursor, c4["record"], c4["spec"], c4["settings"], quantity=quantity, shower=shower,
        low=low, high=high, preview=preview)
    return prepared, prepared.render(coarsen)


def _shower(cursor, c4, quantity, weighting="shower", shower="both", low=1.0, high=99.0,
            coarsen=1):
    prepared = shower_distributions.prepare(
        cursor, c4["record"], c4["spec"], quantity=quantity, weighting=weighting, shower=shower,
        low=low, high=high)
    return prepared.render(coarsen)


def _dense(series: dict, n_bins: int) -> np.ndarray:
    out = np.zeros(n_bins)
    counts = np.asarray(series["counts"], dtype=np.float64)
    out[series["offset"]:series["offset"] + counts.size] = counts
    return out


def _hit_rows(cursor, record, columns: str, choice: str = "both") -> dict:
    """Every hit of the chosen showers with its own shower's event-table values."""
    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    origins = ", ".join(str(o) for o in ORIGINS[choice])
    return cursor.execute(
        f"""SELECT {columns},
                   CAST(CASE WHEN p.org = 0 THEN e.e1_bin ELSE e.e2_bin END AS INTEGER) AS mb
            FROM {proj} p JOIN {event} e USING (event_number)
            WHERE e.d IS NOT NULL AND p.org IN ({origins})"""
    ).fetchnumpy()


def _shower_rows(cursor, record, choice: str = "both") -> dict:
    """One row per shower: own bin, p, θ, φ and hits, straight from the event table."""
    event = quote(naming.event_table(record.table_name))
    parts = []
    if choice in ("a", "both"):
        parts.append(f"SELECT CAST(e1_bin AS INTEGER) AS mb, CAST(e1 AS DOUBLE) AS p, "
                     f"CAST(theta_a AS DOUBLE) AS t, CAST(phi_a AS DOUBLE) AS f, "
                     f"CAST(n_a_rows AS DOUBLE) AS w FROM {event} WHERE d IS NOT NULL "
                     "AND n_a_rows > 0")
    if choice in ("b", "both"):
        parts.append(f"SELECT CAST(e2_bin AS INTEGER) AS mb, CAST(e2 AS DOUBLE) AS p, "
                     f"CAST(theta_b AS DOUBLE) AS t, CAST(phi_b AS DOUBLE) AS f, "
                     f"CAST(n_b_rows + n_ab_rows AS DOUBLE) AS w FROM {event} "
                     "WHERE d IS NOT NULL AND n_b_rows + n_ab_rows > 0")
    return cursor.execute(" UNION ALL ".join(parts)).fetchnumpy()


# ------------------------------------------------------------- u, v, w --


def _numpy_splat(cursor, record, choice, k, k_z, footprint, pitch) -> dict[str, dict]:
    """``{axis: {(bin, j): sub-deposits}}`` of the rotated sub-deposits, in NumPy."""
    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    origins = ", ".join(str(o) for o in ORIGINS[choice])
    rows = cursor.execute(
        f"""SELECT p.xl, p.yl, p.zl,
                   CAST(CASE WHEN p.org = 0 THEN e.e1_bin ELSE e.e2_bin END AS INTEGER) AS mb,
                   CAST(CASE WHEN p.org = 0 THEN e.theta_a ELSE e.theta_b END AS DOUBLE) AS t,
                   CAST(CASE WHEN p.org = 0 THEN e.phi_a ELSE e.phi_b END AS DOUBLE) AS f
            FROM {proj} p JOIN {event} e USING (event_number)
            WHERE e.d IS NOT NULL AND p.org IN ({origins})"""
    ).fetchnumpy()
    xl, yl, zl = (np.asarray(rows[c], dtype=np.float64) for c in ("xl", "yl", "zl"))
    t, f = np.asarray(rows["t"]), np.asarray(rows["f"])
    mb = np.asarray(rows["mb"], dtype=np.int64)
    ct, st, cf, sf = np.cos(t), np.sin(t), np.cos(f), np.sin(f)
    wx, wy = footprint
    out: dict[str, dict] = {"u": {}, "v": {}, "w": {}}
    for a in range(k):
        for b in range(k):
            for c in range(k_z):
                ox = ((a + 0.5) / k - 0.5) * wx
                oy = ((b + 0.5) / k - 0.5) * wy
                oz = ((c + 0.5) / k_z - 0.5) * pitch
                coords = {
                    "u": (xl + ct * cf * ox + ct * sf * oy - st * oz) / 40.0,
                    "v": (yl - sf * ox + cf * oy) / 40.0,
                    "w": (zl + st * cf * ox + st * sf * oy + ct * oz) / pitch,
                }
                for axis, value in coords.items():
                    for key in zip(mb.tolist(), np.floor(value).astype(np.int64).tolist()):
                        out[axis][key] = out[axis].get(key, 0) + 1
    return out


def _bundle_cells(bundle: HitBundle, axis: str) -> dict:
    counts = bundle.axes[axis]
    cells = {}
    for row, mb in enumerate(bundle.bins.tolist()):
        for i in np.flatnonzero(counts.counts[row]):
            cells[(mb, counts.j0 + int(i))] = int(counts.counts[row, i])
    return cells


@pytest.mark.parametrize("choice", CHOICES)
def test_uvw_counts_equal_the_rotated_sub_deposits_in_numpy(cursor, c4, choice):
    record, spec = c4["record"], c4["spec"]
    footprint = hit_distributions.footprint_of(cursor, record)
    pitch = record.frame_bounds.layer_pitch_mm
    k, k_z = hit_distributions.splat_parameters(footprint)
    assert (k, k_z) == (2, 2)
    bundle = hit_distributions.scan_uvw(cursor, record, spec, choice, sampled=False, k=k,
                                        k_z=k_z, footprint=footprint, pitch=pitch)
    expected = _numpy_splat(cursor, record, choice, k, k_z, footprint, pitch)
    for axis in ("u", "v", "w"):
        assert _bundle_cells(bundle, axis) == expected[axis], axis
        assert bundle.unkeyed[axis] == 0


@pytest.mark.parametrize("quantity", ["u", "v", "w"])
@pytest.mark.parametrize("choice", CHOICES)
def test_uvw_counts_are_eighths_that_sum_to_each_series_hits(cursor, c4, quantity, choice):
    prepared, body = _hit(cursor, c4, quantity, shower=choice)
    assert prepared.exact
    rows = _hit_rows(cursor, c4["record"], "p.event_number", choice)
    mb = np.asarray(rows["mb"], dtype=np.int64)
    expected = {int(b): int((mb == b).sum()) for b in np.unique(mb)}
    assert [s["bin"] for s in body["series"]] == sorted(expected)
    for s in body["series"]:
        for value in [*s["counts"], s["below"], s["above"]]:
            assert float(value) * 8 == pytest.approx(round(float(value) * 8), abs=1e-9)
        assert sum(s["counts"]) + s["below"] + s["above"] == pytest.approx(expected[s["bin"]],
                                                                         abs=1e-9)
        assert s["n"] == expected[s["bin"]]
        assert s["resultant"] is None and s["rayleigh_p"] is None
    assert body["display"]["n_outside"] == pytest.approx(
        sum(s["below"] + s["above"] for s in body["series"]))
    assert body["quantity"]["weighting"] == "footprint-splatted hit count"
    assert body["quantity"]["bin_width"] == (40.0 if quantity in "uv" else 20.5)


def test_the_window_is_the_pooled_percentile_rounded_outward_to_whole_bins(cursor, c4):
    _, body = _hit(cursor, c4, "u")
    edges = np.asarray(body["edges"])
    assert np.allclose(np.diff(edges), 40.0) and np.allclose(edges / 40.0, np.round(edges / 40.0))
    total = sum(s["n"] for s in body["series"])
    below = sum(s["below"] for s in body["series"])
    above = sum(s["above"] for s in body["series"])
    assert below < 0.01 * total and above <= 0.01 * total
    first = sum(_dense(s, edges.size - 1)[0] for s in body["series"])
    last = sum(_dense(s, edges.size - 1)[-1] for s in body["series"])
    # One bin narrower on either side would leave more than the percentile outside.
    assert below + first >= 0.01 * total and above + last > 0.01 * total
    assert body["display"]["percentiles"] == [1.0, 99.0]
    # Four showers: the window is real but set by weak evidence.
    assert body["display"]["provisional"] is True


def test_the_comb_is_measured_on_the_pooled_raw_profile_before_any_crop(cursor, c4):
    record, spec = c4["record"], c4["spec"]
    footprint = hit_distributions.footprint_of(cursor, record)
    k, k_z = hit_distributions.splat_parameters(footprint)
    bundle = hit_distributions.scan_uvw(cursor, record, spec, "both", sampled=False, k=k,
                                        k_z=k_z, footprint=footprint,
                                        pitch=record.frame_bounds.layer_pitch_mm)
    for axis in ("u", "v", "w"):
        _, wide = _hit(cursor, c4, axis)
        _, narrow = _hit(cursor, c4, axis, low=20.0, high=80.0)
        lag1 = profile_lag1(bundle.axes[axis].counts.sum(axis=0))
        assert wide["comb"]["lag1"] == sig(lag1, 3)
        assert narrow["comb"] == wide["comb"]
        assert wide["comb"]["combed"] is bool(lag1 is not None and lag1 < -0.10)
        assert (wide["comb"]["k"], wide["comb"]["k_z"], wide["comb"]["axis"]) == (2, 2, axis)
        assert "before any crop" in wide["comb"]["measured_on"]
        assert len(narrow["edges"]) < len(wide["edges"])


def test_the_splat_block_states_the_sub_deposits_and_that_they_leave_no_gap(cursor, c4):
    for axis, width in (("u", 40.0), ("v", 40.0), ("w", 20.5)):
        _, body = _hit(cursor, c4, axis)
        splat = body["splat"]
        assert splat["regime"] == "subdeposit3d"
        assert (splat["k"], splat["k_z"], splat["per_hit"]) == (2, 2, 8)
        assert splat["bin_mm"] == width and splat["gap_free"] is True
        assert any("Footprint-splatted hit counts" in n for n in body["notes"])
    assert hit_distributions.gap_free(48.6 / 2, 40.0)
    assert not hit_distributions.gap_free(48.6, 40.0)


# ------------------------------------------------------------- energy --


@pytest.mark.parametrize("choice", CHOICES)
def test_energy_display_counts_are_whole_merges_of_the_fine_histogram(cursor, c4, choice):
    _, body = _hit(cursor, c4, "energy", shower=choice)
    rows = _hit_rows(cursor, c4["record"], "p.energy", choice)
    energy = np.asarray(rows["energy"], dtype=np.float64)
    mb = np.asarray(rows["mb"], dtype=np.int64)
    fine = np.floor(np.log10(energy) * 100).astype(np.int64)
    log_edges = np.asarray(body["edges_log10"])
    stops = np.round(log_edges * 100).astype(np.int64)
    m = int(stops[1] - stops[0])
    assert np.all(np.diff(stops) == m) and stops[0] % m == 0
    assert m in hit_distributions.ENERGY_MERGES
    assert body["quantity"]["bin_width"] == pytest.approx(m / 100)
    np.testing.assert_allclose(body["edges"], [sig(10 ** e) for e in log_edges])
    for s in body["series"]:
        mine = fine[mb == s["bin"]]
        expected = np.array([((mine >= lo) & (mine < hi)).sum()
                             for lo, hi in zip(stops[:-1], stops[1:])])
        np.testing.assert_array_equal(_dense(s, stops.size - 1), expected)
        assert s["below"] == int((mine < stops[0]).sum())
        assert s["above"] == int((mine >= stops[-1]).sum())
        assert s["n"] == mine.size
    assert body["quantity"]["scale"] == "log10" and body["comb"] is None


def test_energy_merges_follow_the_rice_rule_on_a_decade_ladder():
    m, n_ref = hit_distributions.energy_bins(700, [5000.0, 30.0, 10.0], coarsen=1)
    # Rice on the smallest series of at least 15 hits (30 -> 7, clamped to 8 bins).
    assert n_ref == 30 and m == 100
    m, _ = hit_distributions.energy_bins(700, [10 ** 7], coarsen=1)
    assert m == 10      # 120 bins over 7 decades: 0.1-decade bins
    m, _ = hit_distributions.energy_bins(700, [10 ** 7], coarsen=2)
    assert m == 20


# ---------------------------------------------------------- θ, φ and p --


@pytest.mark.parametrize("weighting", ["shower", "hit"])
@pytest.mark.parametrize("quantity", ["theta", "phi", "p"])
@pytest.mark.parametrize("choice", CHOICES)
def test_shower_quantities_match_numpy_histograms(cursor, c4, quantity, weighting, choice):
    body = _shower(cursor, c4, quantity, weighting=weighting, shower=choice)
    rows = _shower_rows(cursor, c4["record"], choice)
    values = np.asarray(rows[{"theta": "t", "phi": "f", "p": "p"}[quantity]], dtype=np.float64)
    if quantity == "phi":
        values = circular.wrap_angle(values)
    weights = (np.asarray(rows["w"], dtype=np.float64) if weighting == "hit"
               else np.ones(values.size))
    mb = np.asarray(rows["mb"], dtype=np.int64)
    edges = np.asarray(body["edges"], dtype=np.float64)
    if quantity == "phi":
        edges[0], edges[-1] = -math.pi, math.pi
    assert [s["bin"] for s in body["series"]] == sorted(set(mb.tolist()))
    for s in body["series"]:
        mine = mb == s["bin"]
        v, w = values[mine], weights[mine]
        inside = (v >= edges[0]) & (v <= edges[-1])
        expected, _ = np.histogram(v[inside], bins=edges, weights=w[inside])
        np.testing.assert_array_equal(_dense(s, edges.size - 1), expected)
        assert s["below"] == w[v < edges[0]].sum() and s["above"] == w[v > edges[-1]].sum()
        assert s["n"] == int(w.sum())
        assert s["n_showers"] == int(mine.sum())
    assert body["quantity"]["source"] == "showers"
    assert body["splat"] is None and body["comb"] is None


@pytest.mark.parametrize("quantity", ["theta", "phi", "p"])
def test_the_hit_weighting_equals_a_histogram_over_the_hits_themselves(cursor, c4, quantity):
    """The notebook's hit sample, taken whole: every hit carries its own shower's value."""
    body = _shower(cursor, c4, quantity, weighting="hit")
    column = {"theta": "theta", "phi": "phi", "p": None}[quantity]
    if column is None:
        expr = "CAST(CASE WHEN p.org = 0 THEN e.e1 ELSE e.e2 END AS DOUBLE) AS x"
    else:
        expr = (f"CAST(CASE WHEN p.org = 0 THEN e.{column}_a ELSE e.{column}_b END AS DOUBLE) "
                "AS x")
    rows = _hit_rows(cursor, c4["record"], expr)
    x = np.asarray(rows["x"], dtype=np.float64)
    if quantity == "phi":
        x = circular.wrap_angle(x)
    mb = np.asarray(rows["mb"], dtype=np.int64)
    edges = np.asarray(body["edges"], dtype=np.float64)
    if quantity == "phi":
        edges[0], edges[-1] = -math.pi, math.pi
    for s in body["series"]:
        mine = x[mb == s["bin"]]
        expected, _ = np.histogram(mine[(mine >= edges[0]) & (mine <= edges[-1])], bins=edges)
        np.testing.assert_array_equal(_dense(s, edges.size - 1), expected)
        assert s["n"] == mine.size


def _keys(value, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _keys(item, found)
    return found


@pytest.mark.parametrize("weighting", ["shower", "hit"])
def test_phi_is_drawn_over_its_full_period_with_a_resultant_and_never_a_mean(cursor, c4,
                                                                             weighting):
    body = _shower(cursor, c4, "phi", weighting=weighting)
    assert body["edges"][0] == sig(-math.pi) and body["edges"][-1] == sig(math.pi)
    display = body["display"]
    assert display["percentiles"] is None and display["n_outside"] == 0
    assert display["provisional"] is False
    rows = _shower_rows(cursor, c4["record"])
    mb = np.asarray(rows["mb"], dtype=np.int64)
    phi = np.asarray(rows["f"], dtype=np.float64)
    for s in body["series"]:
        # One shower per series here: R̄ = 1 by construction, so it is withheld.
        assert s["n_showers"] == 1
        assert s["resultant"] is None and s["rayleigh_p"] is None
        assert s["below"] == 0 and s["above"] == 0
    assert not {k for k in _keys(body, set()) if "mean" in k}
    assert any("never averaged" in n for n in body["notes"])


def test_each_phi_series_carries_its_resultant_and_rayleigh_p_from_two_showers():
    rng = np.random.default_rng(11)
    sizes = {3: 1, 7: 2, 9: 60}
    mb = np.repeat(list(sizes), list(sizes.values()))
    phi = np.where(mb == 9, rng.vonmises(1.0, 2.0, mb.size), rng.uniform(-3, 3, mb.size))
    sample = ShowerSample(mb=mb, p=mb + 0.5, theta=np.full(mb.size, 0.3), phi=phi,
                          hits=rng.integers(1, 50, mb.size).astype(float),
                          placed=np.ones(mb.size, dtype=bool), n_no_bin=0)
    classes, _ = shower_distributions.series_classes(sample)
    for weighting in ("shower", "hit"):
        body = shower_distributions.render(sample, classes, "phi", weighting, 1.0, 99.0)
        by_bin = {s["bin"]: s for s in body["series"]}
        assert by_bin[3]["resultant"] is None and by_bin[3]["rayleigh_p"] is None
        for k in (7, 9):
            c, s, n = circular.resultant_sums(phi[mb == k])
            r = circular.mean_resultant_length(c, s, n)
            assert by_bin[k]["resultant"] == sig(r)
            assert by_bin[k]["rayleigh_p"] == sig(circular.rayleigh_p(n, r), 3)
        assert by_bin[9]["resultant"] > 0.5        # a concentrated series
        assert body["display"]["provisional"] is False


def test_theta_window_is_a_fine_nice_range_with_rice_bins(cursor, c4):
    body = _shower(cursor, c4, "theta")
    edges = np.asarray(body["edges"])
    rows = _shower_rows(cursor, c4["record"])
    theta = np.asarray(rows["t"], dtype=np.float64)
    # Four showers: below the robust floor the full range is shown, rounded outward.
    assert edges[0] <= theta.min() and edges[-1] >= theta.max()
    assert body["display"]["percentiles"] is None and body["display"]["provisional"] is True
    assert edges.size - 1 == histogram.MIN_BINS
    assert "provisional" in body["display"]["note"]


def test_momentum_bins_are_tenths_of_a_gev_aligned_on_whole_gev(cursor, c4):
    body = _shower(cursor, c4, "p")
    edges = np.asarray(body["edges"])
    assert edges[0] == math.floor(edges[0]) and edges[-1] == math.floor(edges[-1])
    np.testing.assert_allclose(np.diff(edges), 0.1, atol=1e-9)
    for s in body["series"]:
        # Each shower sits in the tenth of a GeV that holds its momentum, inside its own bin.
        assert s["bin"] <= edges[s["offset"]] + 1e-9 < s["bin"] + 1


# ------------------------------------------------------------ the whole --


@pytest.mark.parametrize("quantity", ["u", "v", "w", "energy"])
def test_the_shower_choice_splits_the_hits(cursor, c4, quantity):
    totals = {}
    for choice in CHOICES:
        _, body = _hit(cursor, c4, quantity, shower=choice)
        totals[choice] = sum(s["n"] for s in body["series"])
    assert totals["a"] + totals["b"] == totals["both"] == c4["record"].n_hits


@pytest.mark.parametrize("quantity", ["u", "v", "w", "energy", "theta", "phi", "p"])
@pytest.mark.parametrize("coarsen", [2, 4])
def test_coarsening_merges_whole_bins_and_conserves_every_count(cursor, c4, quantity, coarsen):
    if quantity in shower_distributions.SHOWER_QUANTITIES:
        fine = _shower(cursor, c4, quantity, weighting="hit")
        coarse = _shower(cursor, c4, quantity, weighting="hit", coarsen=coarsen)
    else:
        fine = _hit(cursor, c4, quantity)[1]
        coarse = _hit(cursor, c4, quantity, coarsen=coarsen)[1]
    assert coarse["display"]["coarsened"] == coarsen
    assert len(coarse["edges"]) <= len(fine["edges"])
    for a, b in zip(fine["series"], coarse["series"]):
        assert a["bin"] == b["bin"]
        assert sum(a["counts"]) + a["below"] + a["above"] == pytest.approx(
            sum(b["counts"]) + b["below"] + b["above"])


def test_hit_scans_are_cached_under_the_clamped_selection(cursor, c4):
    record = c4["record"]
    loose = filters.build(record, e1_min=0.0, e1_max=1000.0)
    first = hit_distributions.prepare(cursor, record, c4["spec"], c4["settings"], quantity="w",
                                      shower="both", low=1.0, high=99.0, preview=False)
    again = hit_distributions.prepare(cursor, record, loose, c4["settings"], quantity="u",
                                      shower="both", low=1.0, high=99.0, preview=False)
    assert again.cached
    assert first.render(1)["series"] != []
    footprint = hit_distributions.footprint_of(cursor, record)
    key = hit_distributions.uvw_key(record, loose, "both", False, 2, 2, footprint, 20.5)
    assert key[0] == record.table_name
    assert physics_cache.get_cache().get_any([key]) is not None


def test_the_preview_reads_the_sample_and_scales_its_counts(cursor, c4, monkeypatch):
    record = c4["record"]
    assert record.has_sample
    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    prepared, body = _hit(cursor, c4, "energy", preview=True)
    assert not prepared.exact and prepared.warnings
    sample = quote(naming.proj_table(record.table_name, sampled=True))
    n_sampled = cursor.execute(f"SELECT count(*) FROM {sample}").fetchone()[0]
    scale = 100.0 / c4["settings"].sample_percent
    total = sum(s["n"] for s in body["series"])
    assert total == round(n_sampled * scale)
    _, uvw = _hit(cursor, c4, "w", preview=True)
    assert sum(sum(s["counts"]) + s["below"] + s["above"] for s in uvw["series"]) == \
        pytest.approx(n_sampled * scale, rel=1e-5)


@pytest.mark.parametrize("quantity", ["u", "v", "w", "energy", "theta", "phi", "p"])
def test_an_empty_selection_draws_nothing_and_says_so(cursor, c4, quantity):
    import contract_check

    empty = filters.build(c4["record"], e1_min=1000.0, e1_max=2000.0)
    if quantity in shower_distributions.SHOWER_QUANTITIES:
        prepared = shower_distributions.prepare(cursor, c4["record"], empty, quantity=quantity,
                                                weighting="shower", shower="both", low=1.0,
                                                high=99.0)
    else:
        prepared = hit_distributions.prepare(cursor, c4["record"], empty, c4["settings"],
                                             quantity=quantity, shower="both", low=1.0,
                                             high=99.0, preview=False)
    body = prepared.render(1)
    assert body["series"] == [] and body["edges"] == []
    assert body["display"]["note"] == "Nothing in this selection to draw."
    contract_check.check({**body, "meta": {}, "kind": c4["record"].kind, "shower": "both",
                          "filter": empty.as_dict()}, "distributions")


def test_every_sentence_sets_its_negative_numbers_with_a_true_minus(cursor, c4):
    bodies = [_hit(cursor, c4, q)[1] for q in ("u", "v", "w", "energy")]
    bodies += [_shower(cursor, c4, q) for q in ("theta", "phi", "p")]
    for body in bodies:
        texts = [*body["notes"], body["display"]["note"], body["quantity"]["label"],
                 *(s["label"] for s in body["series"])]
        for text in texts:
            assert not signed_hyphens(text), text
    assert "−" in bodies[0]["display"]["note"]   # the u window starts below zero


def test_the_event_table_module_never_reads_the_projection_table():
    source = inspect.getsource(shower_distributions)
    assert "proj_table" not in source and "proj_" not in source


# ------------------------------------------------------------- budget --


def _classes(n: int) -> list[SeriesClass]:
    return [SeriesClass(k, f"{k}–{k + 1} GeV", 5000) for k in range(n)]


def test_the_worst_case_hit_payloads_fit_the_budget():
    """Twenty series, every bin populated with seven-figure eighths, over wide windows."""
    rng = np.random.default_rng(3)
    bins = np.arange(20)
    wide = {axis: AxisCounts(-75, rng.integers(10 ** 6, 10 ** 7, (20, 151)).astype(float) + 1)
            for axis in ("u", "v", "w")}
    bundle = HitBundle(bins, wide, {}, 0.0)
    for axis in ("u", "v", "w"):
        body = hit_distributions.render_uvw(
            bundle, _classes(20), axis, per_hit=8, scale=1.0, k=2, k_z=2,
            footprint=(48.27, 48.6), pitch=20.5, low=0.0, high=100.0, coarsen=1, exact=True)
        assert len(body["series"]) == 20 and len(body["edges"]) == 152
        assert density.wire_size(body) < 50_000
    fine = AxisCounts(-1500, rng.integers(10 ** 5, 10 ** 6, (20, 1450)).astype(float))
    energy = HitBundle(bins, {"energy": fine}, {}, 0.0)
    body, _ = hit_distributions.render_energy(energy, _classes(20), scale=1.0, low=0.0,
                                              high=100.0, coarsen=1, exact=True)
    assert len(body["edges"]) - 1 <= histogram.DEFAULT_BINS
    assert density.wire_size(body) < 50_000


def test_the_worst_case_shower_payloads_fit_the_budget(monkeypatch):
    """Twenty series at the Rice cap of 120 bins, hit-weighted counts of six figures."""
    monkeypatch.setattr(histogram, "adaptive_bins", lambda n, cap=120: 120)
    rng = np.random.default_rng(5)
    n = 20 * 400
    mb = np.repeat(np.arange(20), 400)
    p = mb + rng.uniform(0.0, 1.0, n)
    sample = ShowerSample(
        mb=mb, p=p, theta=rng.uniform(0.05, 0.63, n),
        phi=rng.uniform(-math.pi, math.pi, n), hits=rng.integers(100, 9000, n).astype(float),
        placed=np.ones(n, dtype=bool), n_no_bin=0)
    classes = [SeriesClass(k, f"{k}–{k + 1} GeV", 400) for k in range(20)]
    for quantity in ("theta", "phi", "p"):
        body = shower_distributions.render(sample, classes, quantity, "hit", 1.0, 99.0)
        assert len(body["series"]) == 20
        assert density.wire_size(body) < 50_000, quantity
