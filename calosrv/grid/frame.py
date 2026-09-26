"""The canonical centre-of-separation frame: SE(3) co-registration mathematics.

Every event is moved by one rigid-body motion so that its two showers sit at the
same place: the midpoint of the two shower *entry points* goes to the origin,
the A-to-B separation is turned onto the +x' axis, and the calorimeter front
face becomes z' = 0. Because the motion is an element of SE(3) - a rotation and
a translation - distances, transverse widths and longitudinal profiles are
preserved exactly, which is what makes energy from different events addable.

**Where the entry points come from.** The dataset's ``centroid_A/B_*`` columns
are three-dimensional whole-shower centroids sitting a median 253 mm behind the
front face, not entry points, and ``centroid_AB_distance`` is their 3-D
distance. Measured on the production file, back-projecting each centroid to the
front face along its incident direction::

    entry = c - (c_z - z_front) * tan(theta) * (cos(phi), sin(phi))

lands a median 82 mm from the per-event energy-weighted entrance-slab centroid;
the opposite sign lands 181 mm away, which is what fixes the convention. The
transverse separation of the two entry points, ``D_entry``, is therefore *not*
the dataset's ``D`` and both are always reported side by side.

**Sign of the rotation.** With ``psi = atan2(yB - yA, xB - xA)`` the passive
rotation ``R_z(-psi)`` maps the B entry point to ``(+D_entry/2, 0)`` and A to
``(-D_entry/2, 0)``::

    x' =  cos(psi) * (x - x0) + sin(psi) * (y - y0)
    y' = -sin(psi) * (x - x0) + cos(psi) * (y - y0)

Direction vectors transform by the same linear part, and ``z' = z - z_front``.

**Cell footprints.** A hit is a calorimeter cell, not a point. Measured on the
production lattice, cells are 48.27 mm wide in x (the pitch within one y row)
and 48.6 mm in y (the pitch within one x column); rows form blocks of four
offset by 4.4 mm in x between blocks, which is why the sorted x coordinates
show "twins" 4.4 mm apart. :func:`cell_footprint` recovers the physical width
from that structure so a rotated cell can be splatted over its true area
rather than dropped at its centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..stats.gaussian import t_quantile_975 as _t_quantile_975
from .lattice import Axis, Lattice
from .splat import uniform_edges

#: Transverse pitch of the canonical accumulation grid, in millimetres. Close to
#: the 20.5 mm longitudinal sampling pitch and well under half a cell width, so
#: the grid resolves the footprint splat without inventing sub-cell detail.
CANONICAL_PITCH_MM = 20.0

#: Transverse margin added around the anchors when planning the accumulation
#: window: twice the p90 energy-weighted RMS radius of a shower about its own
#: axis (246 mm) on the production dataset.
SHOWER_MARGIN_MM = 500.0

#: Upper bound on the number of sub-deposit rows one canonical scan may create.
#: Measured: 22.5 M hits at k = 1 take 0.54 s; 1.27 M hits at k = 4 take 0.41 s.
SUBSAMPLE_ROW_BUDGET = 30_000_000

#: Largest sub-cell sampling factor. Beyond 6 x 6 the sub-deposit spacing on a
#: 48 mm cell is under 8 mm against a 20 mm grid, which buys nothing visible.
MAX_SUBSAMPLE = 6

#: Smallest factor ever used. Point-binning (k = 1) was measured to leave a
#: real comb even over 20 000 co-registered events - lag-1 autocorrelation of
#: the core row -0.26 on the production dataset, -0.47 on a 221-event slice,
#: against +0.4 to +0.7 at k >= 2 - so the ensemble of rotation angles does
#: *not* smooth cell footprints and a single deposit per cell is never drawn.
MIN_SUBSAMPLE = 2

#: Cap for the sampled drag preview, which is approximate anyway and must stay
#: quick: the 10% sample of the full dataset at k = 2 scans about 9 M rows.
PREVIEW_MAX_SUBSAMPLE = 2

#: Below this entry separation the rotation angle psi is dominated by the
#: ~80 mm anchor residual, so the event's orientation is effectively random.
#: Harmless to the ensemble density (it only averages azimuthally) but counted.
ILL_CONDITIONED_D_MM = 80.0

#: Dynamic range of the relative colour ramp, in decades below the reference
#: peak: 10^-3 .. 1.0 by the directive's explicit bounds.
RAMP_DECADES = 3.0

#: Below this many co-registered events a fitted display range is labelled
#: provisional on the axis itself (CLAUDE.md section 2).
PROVISIONAL_N = 20

#: Standard deviation of the Gaussian display kernel (``grid/kernel.py``): half
#: the accumulation pitch, so one 20 mm bin's energy spreads to 11.5 mm RMS -
#: enough to dissolve the rotated cell blocks a handful of events leaves, still
#: under a quarter of the 48 mm cell.
SMOOTH_SIGMA_MM = CANONICAL_PITCH_MM / 2

#: Below this many co-registered events the Continuous Field uses the Gaussian
#: kernel; from here up the bilinear tent, whose 8.2 mm RMS is enough once the
#: ensemble of rotation angles fills the footprint. The switch narrows the
#: kernel by 29%; re-rendering the production N = 49 and N = 50 bundles
#: (D 753-762 / 753-763 mm) with both kernels at R = 150 shows it raises the
#: displayed X'Y' peak by 6-7% and the depth peaks by 4-5% (1.8% over the full
#: selection, 20% at N = 5, where the Gaussian is used). Both are disclosed in
#: the payload rather than hidden.
GAUSSIAN_KERNEL_BELOW_N = 50

#: Display windows cover the energy-weighted 0.1st to 99.9th percentile of each
#: transverse marginal, symmetric about the origin. A recorded exception to the
#: CLAUDE.md 1st-99th default: on production v37 a 1-99 crop cuts the halo
#: 15-110x above the 10^-3 display floor and leaves 14-99% of the X'Y' boundary
#: bins above it; at 0.1-99.9 that is 2-11% of the boundary bins, and only
#: 0.12-0.33% of the X'Y' energy falls outside (seven production selections,
#: N = 3 to the full 20 143) - counted and reported, as ever.
WINDOW_LOW_PERCENTILE = 0.1
WINDOW_HIGH_PERCENTILE = 99.9

#: Smallest half-width of a provisional (N < PROVISIONAL_N) window: the median
#: single-shower |y'| p98 of the entrance slab, so a handful of events cannot
#: shrink the view below one shower's own extent. It is *not* the narrowest
#: robust window: D-only slices at N >= 20 measure y' +-360 mm or more on
#: production v37, but energy cuts go well below it - E1, E2 < 2 GeV (N = 691)
#: +-160 mm, < 1.5 GeV (N = 643) +-100 mm, < 1 GeV (N = 468) +-80 mm - which is
#: why the floor above PROVISIONAL_N is the physical resolution instead.
SHOWER_RADIUS_MIN_MM = 200.0

#: From PROVISIONAL_N up the robust evidence sets the window, floored only at
#: this many cell footprints (2 x 48.6 mm, snapped to 100 mm): the physical
#: resolution. A fixed 200 mm floor would widen the robust low-energy windows
#: above for no statistical reason: 1.25x at E1, E2 < 2 GeV, 2x at < 1.5 GeV
#: and 2.5x at < 1 GeV, whose +-80 mm is held at this 100 mm floor instead.
WINDOW_FLOOR_FOOTPRINTS = 2

#: A consecutive-gap below this fraction of the 90th-percentile gap is a "twin"
#: (the same column seen in an adjacent row block, offset 4.4 mm).
TWIN_GAP_FRACTION = 0.25

#: An axis whose twin gaps are at least this fraction of all gaps is twinned.
TWIN_AXIS_FRACTION = 0.20


# ------------------------------------------------------------------ vectors --


def unit_direction(theta: Any, phi: Any) -> np.ndarray:
    """Unit vector(s) ``(sin t cos p, sin t sin p, cos t)``; shape ``(..., 3)``."""
    t = np.asarray(theta, dtype=np.float64)
    p = np.asarray(phi, dtype=np.float64)
    st = np.sin(t)
    return np.stack([st * np.cos(p), st * np.sin(p), np.cos(t)], axis=-1)


def entry_anchor(
    cx: Any, cy: Any, cz: Any, theta: Any, phi: Any, z_front: float
) -> tuple[np.ndarray, np.ndarray]:
    """Back-project a 3-D shower centroid to the front face along its direction.

    The direction points *into* the calorimeter (``u_z > 0``), so a centroid at
    depth ``cz - z_front`` entered the face ``(cz - z_front) * tan(theta)``
    upstream along ``(cos phi, sin phi)``.
    """
    cx = np.asarray(cx, dtype=np.float64)
    cy = np.asarray(cy, dtype=np.float64)
    depth = np.asarray(cz, dtype=np.float64) - float(z_front)
    t = np.asarray(theta, dtype=np.float64)
    p = np.asarray(phi, dtype=np.float64)
    drift = depth * np.tan(t)
    return cx - drift * np.cos(p), cy - drift * np.sin(p)


@dataclass(frozen=True)
class FrameParams:
    """The per-event motion: translation ``(x0, y0)``, rotation ``psi``, ``d_entry``."""

    x0: np.ndarray
    y0: np.ndarray
    psi: np.ndarray
    d_entry: np.ndarray

    @property
    def cos(self) -> np.ndarray:
        return np.cos(self.psi)

    @property
    def sin(self) -> np.ndarray:
        return np.sin(self.psi)


def frame_of(ax: Any, ay: Any, bx: Any, by: Any) -> FrameParams:
    """Frame parameters from the two entry points of each event."""
    ax = np.asarray(ax, dtype=np.float64)
    ay = np.asarray(ay, dtype=np.float64)
    bx = np.asarray(bx, dtype=np.float64)
    by = np.asarray(by, dtype=np.float64)
    dx = bx - ax
    dy = by - ay
    return FrameParams(
        x0=0.5 * (ax + bx),
        y0=0.5 * (ay + by),
        psi=np.arctan2(dy, dx),
        d_entry=np.hypot(dx, dy),
    )


def rotate_xy(
    x: Any, y: Any, x0: Any, y0: Any, psi: Any
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the passive rotation ``R_z(-psi)`` after translating by ``(x0, y0)``."""
    xt = np.asarray(x, dtype=np.float64) - np.asarray(x0, dtype=np.float64)
    yt = np.asarray(y, dtype=np.float64) - np.asarray(y0, dtype=np.float64)
    c = np.cos(np.asarray(psi, dtype=np.float64))
    s = np.sin(np.asarray(psi, dtype=np.float64))
    return c * xt + s * yt, -s * xt + c * yt


def rotate_direction(u: Any, psi: Any) -> np.ndarray:
    """Rotate direction vectors ``(..., 3)`` by the linear part only."""
    u = np.asarray(u, dtype=np.float64)
    c = np.cos(np.asarray(psi, dtype=np.float64))
    s = np.sin(np.asarray(psi, dtype=np.float64))
    ux, uy, uz = u[..., 0], u[..., 1], u[..., 2]
    return np.stack([c * ux + s * uy, -s * ux + c * uy, uz], axis=-1)


# ---------------------------------------------------------------- footprint --


def footprint_from_occupancy(
    ix: np.ndarray, iy: np.ndarray, x_coords: np.ndarray, y_coords: np.ndarray
) -> tuple[float | None, float | None]:
    """``(w_x, w_y)`` from the populated ``(ix, iy)`` cells: the pitch between
    *adjacent* cells that share a row (for x) or a column (for y).

    This is the physical measurement: two cells in the same row are neighbours
    in the detector, whatever the sorted union of all x coordinates looks like.
    On a sparsely populated selection most same-row pairs are not adjacent -
    their gap is a multiple of the pitch - so the pitch is read from the lowest
    cluster of gaps (within 25% of the 5th-percentile gap) rather than from the
    median of all of them, which on the two-event demonstration file would
    report three rows (153 mm) as one cell. On the production lattice this gives
    48.27 x 48.6 mm. Either value is ``None`` when no row or column holds two
    cells.
    """
    ix = np.asarray(ix, dtype=np.int64)
    iy = np.asarray(iy, dtype=np.int64)
    xc = np.asarray(x_coords, dtype=np.float64)
    yc = np.asarray(y_coords, dtype=np.float64)

    def adjacent_pitch(group: np.ndarray, member: np.ndarray, coords: np.ndarray) -> float | None:
        if group.size < 2:
            return None
        order = np.lexsort((member, group))
        g = group[order]
        v = coords[member[order]]
        same = g[1:] == g[:-1]
        gaps = (v[1:] - v[:-1])[same]
        gaps = gaps[gaps > 0]
        if gaps.size == 0:
            return None
        low = float(np.percentile(gaps, 5))
        cluster = gaps[(gaps >= 0.9 * low) & (gaps <= 1.25 * low)]
        return float(np.median(cluster if cluster.size else gaps))

    return adjacent_pitch(iy, ix, xc), adjacent_pitch(ix, iy, yc)


def footprint_axis_width(coords: np.ndarray) -> float:
    """Fallback cell width along one axis from the sorted coordinates alone.

    On a plain axis the width is the median consecutive gap. On a *twinned*
    axis - the same column seen in adjacent row blocks a few millimetres apart,
    so the sorted coordinates come in close pairs - the median consecutive gap
    would be the offset, not the cell, and the median gap between every second
    coordinate is used instead. This recovers the in-row pitch on a densely
    populated lattice but over-estimates it when twins are missing (a sparse
    two-event lattice gave 52.7 against a true 48.3), which is why the
    occupancy-based measurement above is preferred whenever hits are at hand.
    """
    c = np.asarray(coords, dtype=np.float64)
    if c.size < 2:
        return 1.0
    gaps = np.diff(c)
    if c.size < 4:
        return float(np.median(gaps))
    threshold = TWIN_GAP_FRACTION * float(np.percentile(gaps, 90))
    twinned = float(np.mean(gaps < threshold)) >= TWIN_AXIS_FRACTION
    if twinned:
        return float(np.median(c[2:] - c[:-2]))
    return float(np.median(gaps))


def footprint_from_lattice(lattice: Lattice) -> tuple[float, float]:
    """Fallback ``(w_x, w_y)`` when no occupancy is available."""
    return footprint_axis_width(lattice.x.coords), footprint_axis_width(lattice.y.coords)


# -------------------------------------------------------------------- grid --


@dataclass(frozen=True)
class CanonicalGrid:
    """The uniform accumulation grid of one canonical-frame query.

    Transverse bins are ``pitch`` wide and centred on the origin - the window
    is ``[-half_x, half_x] x [-half_y, half_y]`` with the half-widths snapped
    to whole bins, so two selections' grids always share bin boundaries. Depth
    keeps the native sampling layers, shifted so the front face is zero.
    """

    pitch: float
    half_x: float
    half_y: float
    z_front: float
    z_coords: np.ndarray  # canonical depth of each native layer, ascending

    @property
    def n_x(self) -> int:
        return int(round(2.0 * self.half_x / self.pitch))

    @property
    def n_y(self) -> int:
        return int(round(2.0 * self.half_y / self.pitch))

    @property
    def n_z(self) -> int:
        return int(self.z_coords.size)

    @property
    def x_edges(self) -> np.ndarray:
        return uniform_edges(-self.half_x, self.half_x, self.n_x)

    @property
    def y_edges(self) -> np.ndarray:
        return uniform_edges(-self.half_y, self.half_y, self.n_y)

    @property
    def x_coords(self) -> np.ndarray:
        e = self.x_edges
        return 0.5 * (e[:-1] + e[1:])

    @property
    def y_coords(self) -> np.ndarray:
        e = self.y_edges
        return 0.5 * (e[:-1] + e[1:])

    def axis(self, name: str) -> Axis:
        """An :class:`Axis` over the canonical bin centres, for shared consumers."""
        if name == "x":
            return Axis("x", self.x_coords)
        if name == "y":
            return Axis("y", self.y_coords)
        if name == "z":
            return Axis("z", np.asarray(self.z_coords, dtype=np.float64))
        raise KeyError(name)

    @property
    def shape_xy(self) -> tuple[int, int]:
        return self.n_y, self.n_x

    @property
    def shape_yz(self) -> tuple[int, int]:
        return self.n_y, self.n_z

    @property
    def shape_xz(self) -> tuple[int, int]:
        return self.n_x, self.n_z

    @property
    def depth_span(self) -> float:
        z = self.axis("z")
        lo, hi = z.extent
        return hi - lo

    def as_dict(self) -> dict[str, Any]:
        return {
            "pitch_mm": self.pitch,
            "x": [-self.half_x, self.half_x],
            "y": [-self.half_y, self.half_y],
            "n_x": self.n_x,
            "n_y": self.n_y,
            "n_z": self.n_z,
            "z_front_mm": self.z_front,
        }


def _snap_up(value: float, pitch: float, minimum_bins: int = 4) -> float:
    bins = max(minimum_bins, int(math.ceil(value / pitch - 1e-9)))
    return bins * pitch


def plan_window(
    d_entry_max: float | None,
    theta_max: float | None,
    lattice: Lattice,
    pitch: float = CANONICAL_PITCH_MM,
    margin: float = SHOWER_MARGIN_MM,
) -> CanonicalGrid:
    """Accumulation window from the selection's own kinematics.

    The anchors sit at ``+-D_entry/2`` on x'. A shower can drift transversely
    by ``depth * tan(theta)`` across the instrumented depth and spreads by
    ``margin`` about its axis, so the half-widths are::

        M      = depth * tan(theta_max) + margin
        half_x = max(D_entry)/2 + M
        half_y = M

    each rounded *up* to a whole number of bins. Measured on the production
    dataset (max D_entry 5176 mm, theta_max 0.628 rad) this gives
    +-3980 x +-1380 mm and leaves 0.008% of the selected energy outside, which
    the query counts and the payload reports.
    """
    z = lattice.z
    depth = float(z.hi - z.lo)
    theta = float(theta_max) if theta_max is not None and math.isfinite(theta_max) else 0.0
    theta = min(max(theta, 0.0), math.radians(89.0))
    d_max = float(d_entry_max) if d_entry_max is not None and math.isfinite(d_entry_max) else 0.0
    m = depth * math.tan(theta) + margin
    return CanonicalGrid(
        pitch=float(pitch),
        half_x=_snap_up(0.5 * d_max + m, pitch),
        half_y=_snap_up(m, pitch),
        z_front=float(z.lo),
        z_coords=np.asarray(z.coords, dtype=np.float64) - float(z.lo),
    )


# --------------------------------------------------------------- subsample --


def choose_subsample(
    rows_scanned: int,
    budget: int = SUBSAMPLE_ROW_BUDGET,
    k_max: int = MAX_SUBSAMPLE,
    k_min: int = MIN_SUBSAMPLE,
) -> int:
    """Largest ``k`` such that ``rows_scanned * k**2`` stays within ``budget``,
    never below ``k_min``.

    The floor costs the full production dataset 1.7 s on a cold query
    (97 M sub-deposit rows at k = 2, all-models file) - paid once per
    selection, then served from the cache, and pre-warmed at start-up for the
    full range every interface opens on.
    """
    if rows_scanned <= 0:
        return k_max
    k = int(math.floor(math.sqrt(budget / rows_scanned)))
    return max(k_min, min(k_max, k))


def minimum_gapless_subsample(footprint: float, pitch: float) -> int:
    """Smallest ``k`` whose sub-deposit spacing ``footprint/k <= pitch/sqrt 2``.

    With that spacing every grid bin under a rotated footprint receives at
    least one sub-deposit, so the splat has no holes at any rotation angle.
    """
    if footprint <= 0 or pitch <= 0:
        return 1
    return max(1, int(math.ceil(math.sqrt(2.0) * footprint / pitch)))


# -------------------------------------------------------------- statistics --


def rayleigh_p(n: int, resultant: float) -> float | None:
    """Rayleigh test p-value that ``n`` directions with mean resultant length
    ``resultant`` are drawn from a uniform circular distribution.

    The large-sample form ``exp(-n R^2)``; adequate for the gating it drives.
    """
    if n is None or n < 2 or resultant is None or not math.isfinite(resultant):
        return None
    return float(math.exp(-n * resultant * resultant))


#: Student-t quantiles come from the energy panel's table (``stats.gaussian``),
#: so the two halves of the interface can never quote different intervals for
#: the same N. Re-exported here for the ensemble-axis envelope.
t_quantile_975 = _t_quantile_975


# ------------------------------------------------------ per-shower frames --

#: The co-registered frame kinds. The canonical frame co-registers each
#: *event* by its two entry points; the translated and local frames each
#: *shower* by its own entry point P0 (and, for local, its own incident
#: direction), superimposing the two showers of an event at the origin.
KIND_CANONICAL = "canonical"
KIND_TRANS = "trans"
KIND_LOCAL = "local"
SHOWER_KINDS = (KIND_TRANS, KIND_LOCAL)

#: Sub-deposits along the depth of a cell in the local frame. The rotation
#: tilts every cell by up to 36 degrees, so its 20.5 mm layer thickness spreads
#: across depth bins; a single depth sample would comb the w axis. Two is the
#: default; one is allowed only where a measured w comb says so.
LOCAL_K_Z = 2

#: The energy-weighted quantile levels the per-shower window is planned from:
#: wide, so the fixed grid holds essentially everything and the display window
#: (0.1-99.9 %, window.py) is fitted inside it per selection.
SHOWER_GRID_LOW = 1e-4
SHOWER_GRID_HIGH = 0.9999


def plan_shower_window(
    kind: str,
    bounds: Any,
    footprint: tuple[float, float],
    pitch: float = CANONICAL_PITCH_MM,
) -> CanonicalGrid:
    """The fixed accumulation grid of a per-shower frame, from the dataset's extents.

    Planned from the dataset-wide energy-weighted quantiles measured at ingest
    (``grid/bounds.py``), not from the selection, so every selection of a
    dataset shares one grid - bin boundaries included - and the energy outside
    it is counted, not dropped. Transverse half-widths are the larger excursion
    of the 1e-4 and 0.9999 quantiles plus half a cell footprint, snapped up to
    whole bins and centred on the origin, which is every shower's own entry
    point. Depth is the own-shower layers (translated) or uniform bins of the
    layer pitch along w (local), neither ever cropped.
    """
    x_name, y_name = ("xt", "yt") if kind == KIND_TRANS else ("xl", "yl")

    def half(axis_name: str, width: float) -> float:
        axis = bounds.axis(axis_name)
        reach = max(abs(axis.quantile(SHOWER_GRID_LOW)), abs(axis.quantile(SHOWER_GRID_HIGH)))
        return _snap_up(reach + 0.5 * float(width), pitch)

    layer = float(bounds.layer_pitch_mm)
    if kind == KIND_TRANS:
        z = np.arange(int(bounds.n_layers_trans), dtype=np.float64) * layer
    elif kind == KIND_LOCAL:
        axis = bounds.axis("zl")
        z0 = math.floor(axis.quantile(SHOWER_GRID_LOW) / layer) * layer
        n = int(math.ceil((axis.quantile(SHOWER_GRID_HIGH) - z0) / layer)) + 1
        z = z0 + (np.arange(n, dtype=np.float64) + 0.5) * layer
    else:  # pragma: no cover - guarded by the caller
        raise ValueError(f"not a per-shower frame: {kind!r}")
    return CanonicalGrid(
        pitch=float(pitch),
        half_x=half(x_name, footprint[0]),
        half_y=half(y_name, footprint[1]),
        z_front=0.0,
        z_coords=z,
    )


def choose_subsample_3d(
    rows_scanned: int,
    k_z: int = LOCAL_K_Z,
    budget: int = SUBSAMPLE_ROW_BUDGET,
    k_max: int = MAX_SUBSAMPLE,
    k_min: int = MIN_SUBSAMPLE,
) -> int:
    """Largest transverse ``k`` with ``rows * k**2 * k_z`` within ``budget``, never below ``k_min``."""
    if rows_scanned <= 0:
        return k_max
    k = int(math.floor(math.sqrt(budget / (rows_scanned * max(1, k_z)))))
    return max(k_min, min(k_max, k))
