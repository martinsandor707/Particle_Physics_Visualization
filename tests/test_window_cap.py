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
        assert f"plus the display kernel's {reach:.0f} mm reach" in fit.note
    else:
        assert "no kernel reach in Native Grid" in fit.note


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


def test_a_pooled_depth_axis_adds_its_own_mask():
    from calosrv.grid import layer_groups

    bundle = _bundle(_core_and_tail())
    pool = layer_groups.pooled_operator(bundle.grid.axis("z").edges, (5, 5) + (0,) * 11)
    plain = _capped(bundle)
    pooled = _capped(bundle, depth_pool=pool)
    # Flat in depth, so pooling changes nothing here; the call path is exercised.
    assert pooled.xz.row.half_width == plain.xz.row.half_width


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
                            "reach_mm", "limit", "gap_mm", "floor_ratio", "rho_ref", "outside"}
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
