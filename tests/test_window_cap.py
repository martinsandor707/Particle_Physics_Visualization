"""The D-frame's x′ window cap at the drawn field (``query/window.py: cap_axis``).

On the electron and muon two-shower datasets ~97% of the events enter closer
than 80 mm apart: the 0.1-99.9 percentile window is set by a few per cent of
well-separated pairs spread thinly along x′, which averaged over the selection
sit below the 10⁻³ display floor and are never drawn. The cap holds the x′
window to what is drawn (plus the display kernel's reach) and counts every
drawn bin it leaves out. These tests build the accumulation planes by hand, so
every number is known; the API checks at the end use the synthetic fixtures.
"""

from __future__ import annotations

import base64
import itertools
import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from calosrv.api import frame_canonical
from calosrv.grid import frame as frame_mod
from calosrv.grid import kernel as kernel_mod
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from calosrv.query import planes as planes_mod
from calosrv.query import window
from calosrv.text import signed_hyphens

PITCH = 20.0
HALF_X = 2000.0
HALF_Y = 400.0
N_Z = 10
FOOTPRINT = (48.27, 48.6)
FLOOR = 10.0 ** -frame_mod.RAMP_DECADES


# ------------------------------------------------------------- builders --


@dataclass
class FakeBundle:
    """The attributes ``fit_window`` reads from a ``CanonicalBundle``."""

    grid: frame_mod.CanonicalGrid
    planes: dict[str, dict[str, np.ndarray]]
    n: int
    footprint: tuple[float, float] = FOOTPRINT
    extra: dict[str, Any] = field(default_factory=dict)
    #: Read by the renderer (``density.render_canonical``) for its notes.
    subsample_k: int = 3

    @property
    def n_events(self) -> int:
        return self.n

    def panel(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(planes=self.planes[name])

    @property
    def xy(self):
        return self.panel("xy")

    @property
    def yz(self):
        return self.panel("yz")

    @property
    def xz(self):
        return self.panel("xz")


def _grid() -> frame_mod.CanonicalGrid:
    return frame_mod.CanonicalGrid(
        pitch=PITCH, half_x=HALF_X, half_y=HALF_Y, z_front=0.0,
        z_coords=np.arange(N_Z, dtype=np.float64) * 20.5 + 10.25,
    )


def _gauss(edges: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    """Bin integrals of a unit Gaussian over ``edges``."""
    cdf = np.array([0.5 * (1.0 + math.erf((e - mu) / (sigma * math.sqrt(2.0)))) for e in edges])
    return np.diff(cdf)


def _uniform(edges: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Bin integrals of a unit box on [lo, hi]."""
    left, right = edges[:-1], edges[1:]
    overlap = np.clip(np.minimum(right, hi) - np.maximum(left, lo), 0.0, None)
    return overlap / (hi - lo)


def _bundle(x_profile: np.ndarray, n: int = 100, y_sigma: float = 40.0,
            planes: dict[str, np.ndarray] | None = None, y_profile: np.ndarray | None = None
            ) -> FakeBundle:
    """Separable planes: ``x_profile`` along x′ (energy per x′ bin), a Gaussian in y′
    and a flat depth profile, the same x′ profile in X′Y′ and X′Z′."""
    grid = _grid()
    gy = _gauss(grid.y_edges, 0.0, y_sigma) if y_profile is None else y_profile
    gz = np.full(N_Z, 1.0 / N_Z)
    xy = np.outer(gy, x_profile)
    xz = np.outer(x_profile, gz)
    yz = np.outer(gy, gz) * float(x_profile.sum())
    out = {"xy": {"e": xy}, "yz": {"e": yz}, "xz": {"e": xz}}
    for key, profile in (planes or {}).items():
        out["xy"][key] = np.outer(gy, profile)
        out["xz"][key] = np.outer(profile, gz)
        out["yz"][key] = np.outer(gy, gz) * float(profile.sum())
    return FakeBundle(grid, out, n)


def _core_and_tail(core_sigma: float = 40.0, tail_share: float = 0.01,
                   tail_half: float = 1900.0) -> np.ndarray:
    """A dominant overlap core at the origin and a thin flat tail to ±tail_half."""
    edges = _grid().x_edges
    return 1000.0 * ((1.0 - tail_share) * _gauss(edges, 0.0, core_sigma)
                     + tail_share * _uniform(edges, -tail_half, tail_half))


def _drawn_x(bundle: FakeBundle, fit: window.WindowFit, channel: str = planes_mod.CHANNEL_DENSITY,
             native: bool = False) -> dict[str, np.ndarray]:
    """The x′ bins holding a drawn raw bin (X′Y′ within its y′ rows; X′Z′ over depth)."""
    masks = window.drawn_masks(bundle, channel, native=native)["masks"]
    rows = slice(fit.xy.row.lo_index, fit.xy.row.hi_index)
    return {"xy": masks["xy"][rows].any(axis=0), "xz": masks["xz"].any(axis=1)}


def _snap(mm: float) -> float:
    return math.ceil(mm / PITCH - 1e-9) * PITCH


def _capped(bundle: FakeBundle, kernel=kernel_mod.NONE, **kw) -> window.WindowFit:
    return window.fit_window(bundle, cap_x=True, kernel=kernel, **kw)


# ---------------------------------------------------------------- (a) ---


def test_an_overlap_core_with_a_faint_far_tail_is_capped_and_nothing_drawn_is_cut():
    bundle = _bundle(_core_and_tail())
    plain = window.fit_window(bundle)
    fit = _capped(bundle)
    # The 1% tail pushes the percentile window far out ...
    assert plain.xy.col.half_width >= 1400.0 and plain.xz.row.half_width >= 1400.0
    for axis, before in ((fit.xy.col, plain.xy.col), (fit.xz.row, plain.xz.row)):
        cap = axis.cap
        assert cap["rule"] == "drawn_extent" and cap["applied"] is True
        assert cap["percentile_half_width"] == before.half_width
        # ... but nothing out there is drawn, so the window ends at the drawn field.
        assert cap["drawn_half_width"] < 300.0
        assert cap["reach_mm"] == 0.0
        assert cap["limit"] == max(_snap(cap["drawn_half_width"]), fit.floor_mm)
        assert axis.half_width == cap["limit"] < before.half_width
        assert axis.lo == -axis.half_width and axis.symmetric and axis.applied
        assert cap["gap_mm"] == pytest.approx(48.6)
        assert cap["floor_ratio"] == pytest.approx(FLOOR)
        assert cap["outside"] == {"bins": 0, "energy_fraction": 0.0, "sides": []}
    # Every drawn x′ bin lies inside the final window.
    drawn = _drawn_x(bundle, fit)
    for name, axis in (("xy", fit.xy.col), ("xz", fit.xz.row)):
        idx = np.flatnonzero(drawn[name])
        assert idx.min() >= axis.lo_index and idx.max() < axis.hi_index
    # The y′ axes and depth are untouched, and the outside shares describe the final window.
    assert fit.xy.row == plain.xy.row and fit.yz == plain.yz and fit.xz.col == plain.xz.col
    marginal = bundle.planes["xy"]["e"].sum(axis=0)
    inside = marginal[fit.xy.col.lo_index:fit.xy.col.hi_index].sum()
    assert fit.xy.col.energy_fraction_outside == pytest.approx(1.0 - inside / marginal.sum())
    assert fit.xy.energy_fraction_outside > plain.xy.energy_fraction_outside
    # The rho_ref is the selection's own raw peak of each panel group.
    rho_xy = bundle.planes["xy"]["e"] / (bundle.n * PITCH * PITCH)
    assert fit.xy.col.cap["rho_ref"] == pytest.approx(rho_xy.max())
    # The note says so; the payload carries the block on the x′ axes only.
    assert "half-width is capped at the extent of the drawn field" in fit.note
    assert "below the percentile rule's (X′Y′ ±" in fit.note
    # With no drawn bin left outside, the claim is unqualified.
    assert "beyond it no bin of this selection reaches the 10⁻³ display floor" in fit.note
    assert "apart from the isolated bins" not in fit.note
    data = fit.as_dict()
    assert data["xy"]["col"]["cap"]["applied"] and data["xz"]["row"]["cap"]["applied"]
    assert data["xy"]["row"]["cap"] is None and data["yz"]["row"]["cap"] is None
    assert data["yz"]["col"]["cap"] is None and data["xz"]["col"]["cap"] is None


# ---------------------------------------------------------------- (b) ---


def test_two_separated_showers_with_nothing_at_the_origin_keep_their_window():
    edges = _grid().x_edges
    profile = 500.0 * (_gauss(edges, -1000.0, 40.0) + _gauss(edges, 1000.0, 40.0))
    bundle = _bundle(profile)
    plain = window.fit_window(bundle)
    fit = _capped(bundle)
    for axis, before in ((fit.xy.col, plain.xy.col), (fit.xz.row, plain.xz.row)):
        cap = axis.cap
        # The cap is the components' outer edge, not zero: nothing at the origin is fine.
        assert cap["drawn_half_width"] > 1000.0
        assert cap["applied"] is False
        assert (axis.lo, axis.hi, axis.lo_index, axis.hi_index) == (
            before.lo, before.hi, before.lo_index, before.hi_index)
        assert axis.energy_fraction_outside == before.energy_fraction_outside
    assert "capped at the extent" not in fit.note


def test_a_narrow_slice_of_separated_pairs_is_capped_at_their_outer_edge():
    """Two components at ±D/2 and a faint undrawn halo beyond: the cap is their
    outer edge, never the empty origin."""
    edges = _grid().x_edges
    profile = 495.0 * (_gauss(edges, -600.0, 40.0) + _gauss(edges, 600.0, 40.0)) \
        + 10.0 * _uniform(edges, -1900.0, 1900.0)
    fit = _capped(_bundle(profile))
    cap = fit.xy.col.cap
    assert cap["applied"] is True
    assert 600.0 < cap["drawn_half_width"] < 900.0
    assert fit.xy.col.half_width == cap["limit"] >= 600.0


# ---------------------------------------------------------------- (c) ---


def test_a_far_island_under_a_tenth_of_a_percent_is_excluded_and_disclosed():
    grid = _grid()
    x_edges, y_edges = grid.x_edges, grid.y_edges
    bundle = _bundle(_core_and_tail())
    # One raw bin at x′ [1280, 1300], y′ [20, 40]: well above the floor, but
    # 0.05% of the panel's drawn energy.
    ix = int(np.searchsorted(x_edges, 1280.0))
    iy = int(np.searchsorted(y_edges, 20.0))
    assert x_edges[ix] == 1280.0 and y_edges[iy] == 20.0
    island = 0.5
    bundle.planes["xy"]["e"][iy, ix] += island
    bundle.planes["xz"]["e"][ix, 4] += island
    fit = _capped(bundle)
    drawn = _drawn_x(bundle, fit)
    assert drawn["xy"][ix] and drawn["xz"][ix], "the island must itself be drawn"

    cap = fit.xy.col.cap
    assert cap["applied"] is True and cap["drawn_half_width"] < 300.0
    outside = cap["outside"]
    assert outside["bins"] == 1
    # The drawn bin's energy: the island and the faint tail under it.
    plane = bundle.planes["xy"]["e"]
    assert outside["energy_fraction"] == pytest.approx(plane[iy, ix] / plane.sum(), abs=1e-8)
    (side,) = outside["sides"]
    assert side["side"] == 1 and side["bins"] == 1
    assert side["range"] == [1280.0, 1300.0]
    assert side["at"] == pytest.approx(30.0)            # the island's y′ bin centre
    assert outside["energy_fraction"] < window.CAP_ISLAND_SHARE
    # In X′Z′ the edge mark sits at the island's depth.
    (xz_side,) = fit.xz.row.cap["outside"]["sides"]
    assert xz_side["range"] == [1280.0, 1300.0]
    assert xz_side["at"] == pytest.approx(grid.axis("z").edges[4:6].mean(), abs=1e-6)
    assert "Drawn x′ bins beyond the window are counted" in fit.note
    assert "X′Y′ 1 bin(s), +1,280 to +1,300 mm, 0.051% of the panel's energy" in fit.note
    # The island is drawn, so "nothing beyond the window is drawn" must concede it.
    assert ("beyond it, apart from the isolated bins counted below, no bin of this selection "
            "reaches the 10⁻³ display floor") in fit.note
    assert signed_hyphens(fit.cap_note) == [], "negative numbers are written with U+2212"


def test_the_island_rule_measures_components_bridged_across_a_footprint():
    """An undrawn run no wider than one footprint (two 20 mm bins under 48.6 mm)
    joins two drawn runs; a wider one splits them."""
    drawn = np.zeros(20, dtype=bool)
    drawn[[2, 3, 6, 7, 11, 12]] = True
    assert window._components(drawn, 2) == [(2, 8), (11, 13)]
    assert window._components(drawn, 3) == [(2, 13)]
    assert window._components(np.zeros(5, dtype=bool), 2) == []


# ---------------------------------------------------------------- (d) ---


@pytest.mark.parametrize("n_events,floor", [(5, 200.0), (50, 100.0)])
def test_the_cap_never_goes_below_the_window_floor(n_events, floor):
    profile = _core_and_tail(core_sigma=5.0)
    bundle = _bundle(profile, n=n_events, y_sigma=5.0)
    fit = _capped(bundle)
    assert fit.floor_mm == floor
    for axis in (fit.xy.col, fit.xz.row):
        assert axis.cap["applied"] is True
        assert axis.cap["drawn_half_width"] < floor
        assert axis.cap["limit"] == floor == axis.half_width
        assert axis.floored is True
    assert ("provisional" in fit.note) is (n_events < frame_mod.PROVISIONAL_N)


# ---------------------------------------------------------------- (e) ---


@pytest.mark.parametrize("kernel,display,reach", [
    (kernel_mod.NONE, MODE_NATIVE, 0.0),
    (kernel_mod.BILINEAR, MODE_CONTINUOUS, PITCH),
    (kernel_mod.gaussian(frame_mod.SMOOTH_SIGMA_MM), MODE_CONTINUOUS,
     kernel_mod.gaussian(frame_mod.SMOOTH_SIGMA_MM).reach_bins(PITCH) * PITCH),
])
def test_the_limit_adds_the_display_kernels_reach(kernel, display, reach):
    bundle = _bundle(_core_and_tail(core_sigma=100.0))
    fit = _capped(bundle, kernel=kernel, display=display)
    cap = fit.xy.col.cap
    assert cap["reach_mm"] == reach
    assert cap["limit"] == _snap(cap["drawn_half_width"] + reach)
    assert cap["applied"] and fit.xy.col.half_width == cap["limit"]
    if reach:
        assert f"plus the {reach:.0f} mm reach of the Continuous Field kernel" in fit.note
    else:
        assert "(no kernel reach)" in fit.note


def test_the_gaussian_reach_is_six_bins_and_the_tent_one():
    assert kernel_mod.gaussian(frame_mod.SMOOTH_SIGMA_MM).reach_bins(PITCH) == 6
    assert kernel_mod.BILINEAR.reach_bins(PITCH) == 1
    assert kernel_mod.NONE.reach_bins(PITCH) == 0


def test_capping_needs_the_kernel():
    with pytest.raises(ValueError):
        window.fit_window(_bundle(_core_and_tail()), cap_x=True)


# ---------------------------------------------------------------- (f) ---


def test_an_energy_weighted_cam_channel_draws_the_union_of_both_masks():
    """Σ E·CAM high in the faint tail: the CAM view draws further out than the
    density, and its window holds it; never narrower than the density's."""
    edges = _grid().x_edges
    energy = _core_and_tail()
    core = 1000.0 * 0.97 * _gauss(edges, 0.0, 40.0)
    cam = np.where(core > 0.5 * energy, 1e-4, 1.0)      # attention on the tail only
    bundle = _bundle(energy, planes={"eg": energy * cam})
    density = _capped(bundle)
    weighted = _capped(bundle, channel=planes_mod.CHANNEL_GRADCAM_ENERGY)
    assert weighted.xy.col.half_width > density.xy.col.half_width
    # The cap never tightens below the percentile rule, so the CAM's outermost
    # drawn bins, beyond the percentile window, are counted rather than framed.
    drawn = _drawn_x(bundle, weighted, planes_mod.CHANNEL_GRADCAM_ENERGY)["xy"]
    col = weighted.xy.col
    beyond = drawn.copy()
    beyond[col.lo_index:col.hi_index] = False
    assert col.cap["outside"]["bins"] == int(beyond.sum())
    assert col.half_width == col.cap["percentile_half_width"]

    # Attention on the core only: the CAM mask is narrower, the union keeps the density's.
    core_only = _bundle(energy, planes={"eg": energy * np.where(core > 0.5 * energy, 1.0, 0.0)})
    assert (_capped(core_only, channel=planes_mod.CHANNEL_GRADCAM_ENERGY).xy.col.half_width
            == _capped(core_only).xy.col.half_width)


def test_a_mean_cam_channel_in_native_grid_draws_every_bin_with_hits():
    """Native Grid draws attention measured on any real hit, so the faint tail is
    drawn and the cap does not tighten; Continuous Field masks it by density."""
    energy = _core_and_tail()
    bundle = _bundle(energy, planes={"eg": 0.5 * energy, "n": (energy > 0).astype(float)})
    native = _capped(bundle, channel=planes_mod.CHANNEL_GRADCAM, display=MODE_NATIVE)
    assert native.xy.col.cap["applied"] is False
    continuous = _capped(bundle, kernel=kernel_mod.BILINEAR,
                         channel=planes_mod.CHANNEL_GRADCAM, display=MODE_CONTINUOUS)
    assert continuous.xy.col.cap["applied"] is True


def test_a_slice_brighter_than_the_dataset_reference_widens_to_what_it_draws():
    """Under rho_norm=dataset a reference below the selection's peak lowers the
    floor; the window must still hold every drawn bin."""
    bundle = _bundle(_core_and_tail())
    own = _capped(bundle)
    peak = own.xy.col.cap["rho_ref"]
    dim = _capped(bundle, reference={"xy": peak / 50.0, "depth": peak / 50.0})
    assert dim.xy.col.cap["rho_ref"] == pytest.approx(peak / 50.0)
    assert dim.xy.col.half_width > own.xy.col.half_width
    bright = _capped(bundle, reference={"xy": peak * 3.0, "depth": peak * 3.0})
    assert bright.as_dict() == own.as_dict()


def test_a_pooled_depth_axis_counts_what_its_pooled_raster_draws():
    """With layer groups on, X′Z′ draws the pooled raster, whose own peak is lower.

    The core deposits in one layer; a far island spreads evenly over five. Below
    10⁻³ of the core in every native layer, it clears the floor once five layers
    are averaged: the pooled view draws it, so its bins are counted outside the
    window there and nowhere else.
    """
    from calosrv.grid import layer_groups

    grid = _grid()
    xe = grid.x_edges
    core = 1000.0 * _gauss(xe, 0.0, 40.0)
    gy = _gauss(grid.y_edges, 0.0, 40.0)
    xz = np.zeros((xe.size - 1, N_Z))
    xz[:, 0] = core
    ix = int(np.searchsorted(xe, 1500.0))
    xz[ix, :5] = 3e-4 * core.max()
    yz = np.outer(gy, xz.sum(axis=0))
    xy = np.outer(gy, xz[:, :3].sum(axis=1))
    bundle = FakeBundle(grid, {"xy": {"e": xy}, "yz": {"e": yz}, "xz": {"e": xz}}, 100)
    pool = layer_groups.pooled_operator(grid.axis("z").edges, (5, 5) + (0,) * 11)

    def island_counted(cap) -> bool:
        return any(side["side"] == 1 and side["range"][1] >= 1520.0 for side in cap["outside"]["sides"])

    plain = _capped(bundle).xz.row.cap
    pooled = _capped(bundle, depth_pool=pool).xz.row.cap
    # (Both also count the core's own drawn tail at 140-160 mm, which the
    # 0.1-99.9 rule has always cut: the cap is not applied here.)
    assert not island_counted(plain), "below the floor in every native layer"
    assert island_counted(pooled), "drawn once five layers are averaged"
    (far,) = [side for side in pooled["outside"]["sides"] if side["side"] == 1]
    assert far["range"] == [140.0, 1520.0] and far["bins"] == plain["outside"]["sides"][-1]["bins"] + 1


# ------------------------------------------- judged by the real renderer ---

#: Every display channel and weighting the D-frame serves.
CHANNELS = (
    ("density", "energy"), ("gradcam", "energy"), ("gradcam", "count"),
    ("gradcam_energy", "energy"), ("shapcam", "energy"), ("shapcam", "count"),
    ("shapcam_energy", "energy"),
)


def _full_fit(bundle: FakeBundle) -> window.WindowFit:
    """The whole accumulation grid as the window, so a render shows every drawn bin."""
    grid = bundle.grid
    z = grid.axis("z").edges

    def panel(name: str, row_edges, col_edges) -> window.PanelFit:
        energy = float(np.asarray(bundle.planes[name]["e"]).sum())
        return window.PanelFit(name, window._full(row_edges), window._full(col_edges), energy, energy)

    return window.WindowFit(xy=panel("xy", grid.y_edges, grid.x_edges),
                            yz=panel("yz", grid.y_edges, z), xz=panel("xz", grid.x_edges, z),
                            n_events=bundle.n_events, floor_mm=100.0)


def _random_bundle(rng: np.random.Generator) -> FakeBundle:
    """Clusters at random places and strengths with sparse holes and stray hits, and CAM
    planes (energy- and count-weighted, signed) consistent with the energy."""
    grid = _grid()
    xc = 0.5 * (grid.x_edges[:-1] + grid.x_edges[1:])
    yc = 0.5 * (grid.y_edges[:-1] + grid.y_edges[1:])
    zc = np.arange(N_Z)
    shape = (xc.size, yc.size, N_Z)
    E, G, SP, SN, N = (np.zeros(shape) for _ in range(5))
    for i in range(int(rng.integers(1, 6))):
        mx, my = rng.normal(0.0, rng.choice([30.0, 300.0, 1000.0])), rng.normal(0.0, 40.0)
        sx, sy = rng.uniform(15.0, 80.0, size=2)
        amp = 1.0 if i == 0 else 10.0 ** rng.uniform(-3.5, 0.0)
        e = (amp * np.exp(-0.5 * ((xc[:, None] - mx) / sx) ** 2 - 0.5 * ((yc[None, :] - my) / sy) ** 2)[:, :, None]
             * np.exp(-zc / rng.uniform(2.0, 8.0))[None, None, :])
        e = e * (rng.random(shape) < rng.uniform(0.3, 1.0))
        cam = rng.uniform(-1.0, 1.0, shape)
        E += e
        G += e * np.abs(cam)
        SP += e * np.clip(cam, 0.0, None)
        SN += e * np.clip(cam, None, 0.0)
        N += e > 0
    for _ in range(int(rng.integers(0, 20))):
        ix, iy, iz = int(rng.integers(xc.size)), int(rng.integers(yc.size)), int(rng.integers(N_Z))
        v, c = 10.0 ** rng.uniform(-6.0, -1.0), rng.uniform(-1.0, 1.0)
        E[ix, iy, iz] += v
        G[ix, iy, iz] += v * abs(c)
        SP[ix, iy, iz] += v * max(c, 0.0)
        SN[ix, iy, iz] += v * min(c, 0.0)
        N[ix, iy, iz] += 1
    safe = np.maximum(E, 1e-300)
    volumes = {"e": E, "eg": G, "esp": SP, "esn": SN, "n": N,
               "g": np.where(N > 0, G / safe, 0.0) * N, "s": (SP + SN) / safe * N}
    planes: dict[str, dict[str, np.ndarray]] = {"xy": {}, "yz": {}, "xz": {}}
    for key, volume in volumes.items():
        planes["xy"][key] = volume[:, :, :3].sum(axis=2).T
        planes["yz"][key] = volume.sum(axis=0)
        planes["xz"][key] = volume.sum(axis=1)
    return FakeBundle(grid, planes, int(rng.choice([3, 10, 30, 100, 5000])))


@pytest.mark.parametrize("seed", range(12))
def test_every_drawn_bin_beyond_a_capped_window_is_counted_as_the_renderer_draws_it(seed):
    """Judged by ``density.render_canonical`` itself, never by ``drawn_masks``.

    The whole grid is rendered for every channel and both display modes. Every
    x′ display bin it draws beyond the capped window (X′Y′ within the window's
    own y′ rows) must lie on a side ``cap.outside`` counts, within the kernel's
    reach of the counted range; in Native Grid, where a display bin is a raw
    bin, the counts must agree exactly, so nothing undrawn is counted either.
    """
    from calosrv.query import density, reconstruct

    rng = np.random.default_rng(seed)
    bundle = _random_bundle(rng)
    full = _full_fit(bundle)
    for (channel, weighting), mode in itertools.product(CHANNELS, (MODE_CONTINUOUS, MODE_NATIVE)):
        capped = window.fit_window(
            bundle, cap_x=True, kernel=reconstruct.choose_kernel(MODE_CONTINUOUS, bundle.n_events),
            channel=channel, weighting=weighting, display=mode)
        rendered = density.render_canonical(
            bundle, full, mode, 150, channel, weighting, limit=10 ** 9,
            kernel=reconstruct.choose_kernel(mode, bundle.n_events))
        for name, key, axis in (("xy", "col", capped.xy.col), ("xz", "row", capped.xz.row)):
            panel = rendered["panels"][name]
            drawn = (np.frombuffer(base64.b64decode(panel["data"]), dtype=np.uint8)
                     .reshape(panel["shape"]) >= panel["min_code"])
            ax = panel["axes"][key]
            edges = np.linspace(ax["lo"], ax["hi"], ax["n"] + 1)
            centres = 0.5 * (edges[:-1] + edges[1:])
            if name == "xy":
                other = panel["axes"]["row"]
                rows = np.linspace(other["lo"], other["hi"], other["n"] + 1)
                row_c = 0.5 * (rows[:-1] + rows[1:])
                inside_rows = (row_c > capped.xy.row.lo) & (row_c < capped.xy.row.hi)
                profile = drawn[inside_rows].any(axis=0)
            else:
                profile = drawn.any(axis=1)
            cap = axis.cap
            pitch = float(edges[1] - edges[0])
            tol = cap["reach_mm"] + pitch
            counted = {side["side"]: side for side in cap["outside"]["sides"]}
            case = (seed, channel, weighting, mode, name)
            for side, beyond in ((-1, centres < axis.lo), (1, centres > axis.hi)):
                shown = centres[profile & beyond]
                if mode == MODE_NATIVE:
                    # A display bin is a raw bin: the counts agree exactly.
                    assert len(shown) == (counted[side]["bins"] if side in counted else 0), (case, side)
                    continue
                # Continuous Field: a bin straddling the edge, or holding the
                # kernel's smear of a drawn bin inside the window, is within the
                # reach of the edge; any drawn bin further out is a counted island.
                edge = axis.hi if side == 1 else axis.lo
                for c in shown[np.abs(shown - edge) > tol]:
                    entry = counted.get(side)
                    assert entry is not None, (case, "uncounted drawn bin at", float(c))
                    assert entry["range"][0] - tol <= c <= entry["range"][1] + tol, (case, float(c), entry)


# ---------------------------------------------------------------- (g) ---


def test_the_per_shower_frames_never_cap():
    bundle = _bundle(_core_and_tail())
    fit = window.fit_window(bundle)
    assert not fit.capped
    data = fit.as_dict()
    for panel in ("xy", "yz", "xz"):
        for axis in ("row", "col"):
            assert "cap" not in data[panel][axis]
    assert fit.xy.col.half_width >= 1400.0
    assert "capped" not in fit.note


@pytest.mark.parametrize("frame", ["trans", "local"])
def test_per_shower_responses_carry_no_cap(single_client, frame):
    client = single_client
    response = client.get("/api/projections", params={"coord_system": frame})
    assert response.status_code == 200, response.text
    body = response.json()
    fit = body["frame"]["fit"]
    for panel in ("xy", "yz", "xz"):
        for axis in ("row", "col"):
            assert "cap" not in fit[panel][axis]
    assert "ill_conditioned_share" not in body["frame"]


# ------------------------------------------------------------------ API ---


def test_the_canonical_response_carries_the_cap_and_the_ill_conditioned_share(synthetic_client):
    body = synthetic_client.get("/api/projections", params={"frame": "canonical"}).json()
    frame = body["frame"]
    fit = frame["fit"]
    for panel, axis in (("xy", "col"), ("xz", "row")):
        cap = fit[panel][axis]["cap"]
        assert cap["rule"] == "drawn_extent"
        assert set(cap) == {"rule", "applied", "percentile_half_width", "drawn_half_width",
                            "reach_mm", "limit", "gap_mm", "floor_ratio", "rho_ref", "mask", "outside"}
        assert set(cap["outside"]) == {"bins", "energy_fraction", "sides"}
        assert fit[panel][axis]["half_width"] <= cap["percentile_half_width"]
    for panel, axis in (("xy", "row"), ("yz", "row"), ("yz", "col"), ("xz", "col")):
        assert fit[panel][axis]["cap"] is None
    n = frame["n_events"]
    assert frame["ill_conditioned_share"] == pytest.approx(frame["n_ill_conditioned"] / n)
    assert frame["ill_conditioned_majority"] is (
        frame["n_ill_conditioned"] / n > frame_mod.ILL_CONDITIONED_MAJORITY)


@pytest.mark.parametrize("threshold,majority", [(frame_mod.ILL_CONDITIONED_D_MM, False),
                                                (5000.0, True)])
def test_a_mostly_ill_conditioned_selection_is_told_so(synthetic_client, monkeypatch,
                                                       threshold, majority):
    monkeypatch.setattr(frame_mod, "ILL_CONDITIONED_D_MM", threshold)
    body = synthetic_client.get("/api/projections", params={"frame": "canonical"}).json()
    frame = body["frame"]
    assert frame["ill_conditioned_majority"] is majority
    texts = [n["text"] for n in body["meta"]["notices"]]
    said = [t for t in texts if "enter closer than" in t]
    n, n_ill = frame["n_events"], frame["n_ill_conditioned"]
    if majority:
        assert n_ill == n and frame["ill_conditioned_share"] == 1.0
        (text,) = said
        assert text.startswith(f"{n_ill:,} of {n:,} events (100.0%) enter closer than 5000 mm")
        assert "Most of this selection is ill-conditioned" in text
        assert "raising the lower bound of D" in text
    else:
        assert not any("Most of this selection" in t for t in texts)


def test_the_notice_states_the_share_and_formats_counts():
    text = frame_canonical.ill_conditioned_notice(19_326, 19_998)
    assert text.startswith("19,326 of 19,998 events (96.6%) enter closer than 80 mm apart, so")
    assert "Most of this selection is ill-conditioned" in text
    minority = frame_canonical.ill_conditioned_notice(3, 1_000, axis_statistics=False)
    assert minority.startswith("3 of 1,000 events (0.3%) enter")
    assert minority.endswith("averaged over azimuth.")
    assert frame_canonical.ill_conditioned_notice(0, 10) is None
    assert frame_canonical.ill_conditioned_fields(0, 0) == {
        "ill_conditioned_share": None, "ill_conditioned_majority": False}
    assert frame_canonical.ill_conditioned_fields(6, 10) == {
        "ill_conditioned_share": 0.6, "ill_conditioned_majority": True}
    assert frame_canonical.ill_conditioned_fields(5, 10)["ill_conditioned_majority"] is False
