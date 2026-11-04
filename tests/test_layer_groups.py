"""Layer groups ('Longitudinal Channels'): the partition, the seams and the pooled depth operator.

Units only (``calosrv/grid/layer_groups.py`` and the event's ``layer_planes``
builder); the routes are tested in ``test_api_layer_groups.py``.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from calosrv.errors import ValidationError
from calosrv.grid import frame as frame_mod
from calosrv.grid import layer_groups as lg
from calosrv.grid.lattice import Axis
from calosrv.query import layer_profile

PITCH = 20.5
#: The production lattice: 60 layers from 3662.4 mm at exactly 20.5 mm.
PRODUCTION_Z = Axis("z", 3662.4 + PITCH * np.arange(60, dtype=np.float64))
#: A lattice that skips layers the file never populates, as the demonstration file's does (56 of 60).
GAPPED_Z = Axis("z", 3662.4 + PITCH * np.delete(np.arange(60), [7, 19, 33, 52]).astype(np.float64))


# ------------------------------------------------------------- partitions --


@pytest.mark.parametrize("text, words", [
    ("", "positive integers"),
    ("5.5.5.5.5.5.5.5.4.4.4.4.x", "positive integers"),
    ("5,5,5,5,5,5,5,5,4,4,4,4,4", "positive integers"),
    ("5.5.5.5.5.5.5.5.4.4.4.4.-4", "positive integers"),
    ("5..5", "positive integers"),
    ("5.5.5.5.5.5.5.5.4.4.4.8", "exactly 13"),
    ("5.5.5.5.5.5.5.5.4.4.4.4.4.0", "exactly 13"),
    ("0.5.5.5.5.5.5.5.4.4.4.8.4", "at least one layer"),
    ("5.5.5.5.5.5.5.5.4.4.4.4.5", "sum to this experiment's 60 layers"),
])
def test_malformed_partitions_are_refused_naming_the_field(text, words):
    with pytest.raises(ValidationError) as caught:
        lg.parse_counts(text, 60)
    assert caught.value.extra["field"] == "depth_groups"
    assert words in caught.value.detail


def test_a_valid_partition_parses_and_round_trips():
    text = "2.2.3.3.3.4.4.5.5.6.7.8.8"
    counts = lg.parse_counts(text, 60)
    assert counts == (2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8)
    assert lg.format_counts(counts) == text
    assert lg.boundaries(counts)[-1] == 60
    assert lg.boundaries((5,) * 8 + (4,) * 5) == (5, 10, 15, 20, 25, 30, 35, 40, 44, 48, 52, 56, 60)


@pytest.mark.parametrize("n, expected", [
    (60, (5,) * 8 + (4,) * 5),
    (56, (5,) * 4 + (4,) * 9),
    (13, (1,) * 13),
    (65, (5,) * 13),
    (27, (3,) + (2,) * 12),
])
def test_the_uniform_rule_puts_the_larger_groups_first(n, expected):
    counts = lg.uniform_counts(n)
    assert counts == expected and sum(counts) == n and len(counts) == lg.GROUP_COUNT


def test_the_uniform_rule_refuses_fewer_layers_than_groups():
    with pytest.raises(ValidationError) as caught:
        lg.uniform_counts(12)
    assert caught.value.extra["field"] == "depth_groups"


# ------------------------------------------------------------------ seams --


def test_seams_are_the_stored_edges_and_on_production_3652_15_plus_20_5_b():
    counts = lg.uniform_counts(60)
    pool = lg.pooled_operator(PRODUCTION_Z.edges, counts, pitch_mm=PITCH)
    picks = [0, *lg.boundaries(counts)]
    np.testing.assert_array_equal(pool.dst_edges, PRODUCTION_Z.edges[picks])
    np.testing.assert_allclose(pool.dst_edges, 3652.15 + PITCH * np.asarray(picks), rtol=0, atol=1e-9)
    # Z = z - 3649 at the seams: 3.15 + 20.5 b.
    np.testing.assert_allclose(pool.dst_edges - 3649.0, 3.15 + PITCH * np.asarray(picks), atol=1e-9)


def test_seams_on_a_gapped_lattice_follow_the_stored_edges_not_a_pitch():
    counts = lg.uniform_counts(GAPPED_Z.n)
    pool = lg.pooled_operator(GAPPED_Z.edges, counts, pitch_mm=PITCH)
    picks = [0, *lg.boundaries(counts)]
    np.testing.assert_array_equal(pool.dst_edges, GAPPED_Z.edges[picks])
    # An index-times-pitch seam would sit elsewhere wherever a layer is missing.
    assert not np.allclose(pool.dst_edges, GAPPED_Z.edges[0] + PITCH * np.asarray(picks))
    assert not lg.contiguous(GAPPED_Z.coords, PITCH) and lg.contiguous(PRODUCTION_Z.coords, PITCH)


def test_groups_on_a_longer_axis_run_the_last_group_to_its_end():
    counts = lg.uniform_counts(56)
    bins, beyond = lg.group_bins(counts, 60)
    assert beyond == () and len(bins) == 13
    assert bins[-1].start == 52 and bins[-1].stop == 60 and bins[-1].partial
    assert all(not b.partial for b in bins[:-1])
    assert bins[-1].as_dict() == {"group": 13, "first": 53, "last": 60}


def test_groups_beyond_a_shorter_axis_are_dropped_and_reported():
    counts = lg.uniform_counts(60)
    bins, beyond = lg.group_bins(counts, 43)
    assert [b.group for b in bins] == list(range(1, 10))
    assert beyond == (10, 11, 12, 13)
    assert bins[-1].start == 40 and bins[-1].stop == 43 and bins[-1].partial
    pool = lg.pooled_operator(lg.half_pitch_edges(43, PITCH), counts)
    assert pool.n_dst == 9 and pool.beyond == (10, 11, 12, 13)
    assert pool.groups_block()["beyond_axis"] == [10, 11, 12, 13]


# --------------------------------------------------------------- operator --


@pytest.fixture(params=["production", "gapped"])
def depth_axis(request):
    return PRODUCTION_Z if request.param == "production" else GAPPED_Z


def _random_counts(n: int, rng: np.random.Generator) -> tuple[int, ...]:
    cuts = np.sort(rng.choice(np.arange(1, n), size=lg.GROUP_COUNT - 1, replace=False))
    return tuple(int(v) for v in np.diff(np.concatenate(([0], cuts, [n]))))


def test_the_absolute_operator_is_non_negative_and_a_weighted_mean(depth_axis):
    rng = np.random.default_rng(7)
    for _ in range(20):
        counts = _random_counts(depth_axis.n, rng)
        pool = lg.pooled_operator(depth_axis.edges, counts, pitch_mm=PITCH)
        assert (pool.op >= 0).all()
        energy = rng.gamma(0.5, 2.0, size=(9, depth_axis.n))
        pooled = energy @ pool.op.T
        # Every group bin is at most its own layers' peak, so at most the raw per-layer peak.
        for row, b in enumerate(pool.bins):
            assert (pooled[:, row] <= energy[:, b.start:b.stop].max(axis=1) * (1 + 1e-12)).all()
        assert pooled.max() <= energy.max() * (1 + 1e-12)
        # A uniform field of one layer value stays at most that value.
        assert (np.ones(depth_axis.n) @ pool.op.T <= 1 + 1e-12).all()


def test_the_absolute_operator_conserves_the_energy(depth_axis):
    rng = np.random.default_rng(11)
    for _ in range(20):
        counts = _random_counts(depth_axis.n, rng)
        pool = lg.pooled_operator(depth_axis.edges, counts, pitch_mm=PITCH)
        energy = rng.gamma(0.5, 2.0, size=(5, depth_axis.n))
        pooled = energy @ pool.op.T
        conserved = (pooled * pool.energy_weights()[None, :]).sum()
        assert conserved == pytest.approx(energy.sum(), rel=1e-12)


def test_the_co_registered_operator_gives_the_mean_density_and_conserves_it(depth_axis):
    rng = np.random.default_rng(3)
    edges = depth_axis.edges - depth_axis.lo  # z' = z - z_front: the D-frame's own edges
    widths = np.diff(edges)
    for _ in range(20):
        counts = _random_counts(depth_axis.n, rng)
        pool = lg.pooled_operator(edges, counts)
        assert pool.weighting == lg.WEIGHT_OVERLAP and set(np.unique(pool.op)) <= {0.0, 1.0}
        energy = rng.gamma(0.5, 2.0, size=(4, depth_axis.n))
        rho = energy / widths[None, :]
        pooled = (energy @ pool.op.T) / pool.widths[None, :]
        for row, b in enumerate(pool.bins):
            layer = rho[:, b.start:b.stop]
            w = widths[b.start:b.stop]
            np.testing.assert_allclose(pooled[:, row], (layer * w).sum(axis=1) / w.sum(), rtol=1e-12)
            assert (pooled[:, row] <= layer.max(axis=1) * (1 + 1e-12)).all()
        np.testing.assert_allclose((pooled * pool.widths).sum(axis=1), (rho * widths).sum(axis=1),
                                   rtol=1e-12)


def test_signed_parts_pool_apart_and_each_is_conserved():
    rng = np.random.default_rng(5)
    pool = lg.pooled_operator(PRODUCTION_Z.edges, lg.uniform_counts(60), pitch_mm=PITCH)
    positive = rng.gamma(0.5, 1.0, size=(6, 60))
    negative = -rng.gamma(0.5, 1.0, size=(6, 60))
    pos, neg = positive @ pool.op.T, negative @ pool.op.T
    assert (pos >= 0).all() and (neg <= 0).all()
    w = pool.energy_weights()
    assert (pos * w).sum() == pytest.approx(positive.sum(), rel=1e-12)
    assert (neg * w).sum() == pytest.approx(negative.sum(), rel=1e-12)


# ------------------------------------------------------------------ layers --


def test_physical_layers_and_start_layer():
    assert lg.physical_layers(PRODUCTION_Z.lo, PRODUCTION_Z.hi, PITCH) == 60
    assert lg.physical_layers(GAPPED_Z.lo, GAPPED_Z.hi, PITCH) == 60
    assert lg.start_layer(3662.4, 3662.4, PITCH) == 0
    assert lg.start_layer(3662.4 + 7 * PITCH, 3662.4, PITCH) == 7
    np.testing.assert_allclose(lg.half_pitch_edges(3, PITCH), [-10.25, 10.25, 30.75, 51.25])


def _record(z: Axis = PRODUCTION_Z) -> SimpleNamespace:
    lattice = SimpleNamespace(z=z)
    return SimpleNamespace(lattice=lattice, frame_bounds=SimpleNamespace(
        layer_pitch_mm=PITCH, n_layers_trans=60), ingest_report={}, table_name="units")


@pytest.mark.parametrize("seed", range(8))
def test_the_local_normal_is_r_times_e_z_and_the_plane_trace_is_exact(seed):
    rng = np.random.default_rng(seed)
    theta, phi = float(rng.uniform(0.02, 0.6)), float(rng.uniform(-math.pi, math.pi))
    rotation = frame_mod.rotation_matrix(theta, phi)
    normal = lg.layer_normal(rotation)
    np.testing.assert_allclose(normal, [-math.sin(theta), 0.0, math.cos(theta)], atol=1e-12)
    # Points of the plane dz = s in the translated frame, moved as the hits are moved.
    s = float(rng.uniform(-30.0, 600.0))
    points = np.column_stack([rng.uniform(-300, 300, 50), rng.uniform(-300, 300, 50), np.full(50, s)])
    moved = frame_mod.per_shower_local(np.zeros(3), theta, phi).apply(points)
    np.testing.assert_allclose(moved @ normal, s, atol=1e-9)
    # Its trace on u-w: w = s / cos(theta) + u tan(theta), for every v.
    u, w = moved[:, 0], moved[:, 2]
    np.testing.assert_allclose(w, s / math.cos(theta) + u * math.tan(theta), atol=1e-9)

    kt = np.array([0, 0, 1, 2, 5])
    planes = layer_profile.layer_planes(
        "local", _record(), iz=kt + 3, kt=kt, energy=np.ones(5), p0_z=3662.4 + 3 * PITCH,
        theta=theta, phi=phi)
    np.testing.assert_allclose(planes["normal"], normal, atol=1e-12)
    assert planes["line_panels"] == ["xz"]
    assert planes["numbering"] == "relative"
    assert planes["tilt"]["pitch_along_w_mm"] == pytest.approx(PITCH / math.cos(theta))
    assert planes["start_layer"] == 4 and planes["reach_layers"] == 57
    assert planes["energy_gev"][:6] == [2.0, 1.0, 1.0, 0.0, 0.0, 1.0]
    np.testing.assert_allclose(planes["edges_mm"], lg.half_pitch_edges(60, PITCH))


def test_lab_and_translated_planes_are_flat_and_untilted():
    kt = np.array([0, 1, 1])
    for kind in ("lab", "trans"):
        planes = layer_profile.layer_planes(
            kind, _record(), iz=kt + 10, kt=kt, energy=np.array([1.0, 2.0, 3.0]),
            p0_z=3662.4 + 10 * PITCH, theta=0.3, phi=1.0)
        assert planes["normal"] == [0.0, 0.0, 1.0]
        assert planes["line_panels"] == ["xz", "yz"] and planes["tilt"] is None
        assert planes["start_layer"] == 11
    lab = layer_profile.layer_planes("lab", _record(), iz=kt + 10, kt=kt, energy=np.ones(3),
                                     p0_z=3662.4 + 10 * PITCH, theta=0.3, phi=1.0)
    np.testing.assert_allclose(lab["edges_mm"], PRODUCTION_Z.edges, atol=1e-6)
    assert lab["numbering"] == "detector" and lab["display_offset_mm"] == 3649.0
    assert lab["reach_layers"] is None and lab["energy_gev"][10:12] == [1.0, 2.0]


def test_a_shower_at_normal_incidence_has_lines_on_both_local_panels():
    planes = layer_profile.layer_planes("local", _record(), iz=np.array([0]), kt=np.array([0]),
                                        energy=np.ones(1), p0_z=3662.4, theta=0.0, phi=0.4)
    assert planes["line_panels"] == ["xz", "yz"]
    np.testing.assert_allclose(planes["normal"], [0.0, 0.0, 1.0], atol=1e-15)
