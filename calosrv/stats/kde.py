"""A binned Gaussian kernel density estimate with Silverman's bandwidth.

The bandwidth is chosen from the sample by a stated rule, so this is a density
*estimated from per-event values*: it takes the N ≥ 8 curve floor of CLAUDE.md
section 2 (``gaussian.MIN_CURVE_SAMPLES``), unlike the fixed-bandwidth spatial
display kernel of ``grid/kernel.py``.

Values are linearly binned onto a grid at most h/4 apart and convolved with the
kernel, which is exact to well under a percent of the peak and costs O(M log M)
in the grid size rather than O(N M) in the events. The density is divided by
every finite value of the class, so mass that falls outside the drawn window
stays missing and is never renormalised away.

A feature quantised on the detector lattice (a depth in whole 20.5 mm layers,
say) takes only a few distinct values; a bandwidth below half that quantum
draws one spike per lattice value, which is the lattice and not the
distribution. The curve is then withheld and the note says why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import gaussian

MIN_KDE_SAMPLES = gaussian.MIN_CURVE_SAMPLES
SILVERMAN_FACTOR = 0.9
#: Kernel truncation and grid padding, in bandwidths: φ(4)/φ(0) ≈ 3.4 × 10⁻⁴.
TRUNCATION_H = 4.0
MIN_GRID = 256
MAX_GRID = 8192
CURVE_POINTS = 160


def silverman_bandwidth(values: np.ndarray) -> float | None:
    """h = 0.9 min(σ̂, IQR/1.349) n^(-1/5); ``None`` below N = 8 or for no spread."""
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    n = int(a.size)
    if n < MIN_KDE_SAMPLES:
        return None
    sd = float(a.std(ddof=gaussian.DDOF))
    q25, q75 = np.percentile(a, (25.0, 75.0))
    iqr = float(q75 - q25) / gaussian.IQR_TO_SIGMA
    spread = min(sd, iqr) if iqr > 0 else sd
    if not spread > 0:
        return None
    return SILVERMAN_FACTOR * spread * n ** (-0.2)


@dataclass
class KdeResult:
    x: list[float]
    pdf: list[float] | None
    bandwidth: float | None
    grid_points: int
    delta: float | None
    n: int
    n_total: int
    n_outside_grid: int
    truncation_h: float = TRUNCATION_H
    notes: list[str] = field(default_factory=list)

    @property
    def drawn(self) -> bool:
        return self.pdf is not None

    def scaled(self, bin_width: float) -> list[float] | None:
        """Expected counts per histogram bin: ``n_total · w · pdf``."""
        if self.pdf is None:
            return None
        k = self.n_total * bin_width
        return [k * v for v in self.pdf]


def gaussian_kde_binned(
    values: np.ndarray,
    lo: float,
    hi: float,
    bandwidth: float | None = None,
    points: int = CURVE_POINTS,
    n_total: int | None = None,
    quantum: float | None = None,
) -> KdeResult:
    """The KDE of ``values`` sampled at ``points`` positions over ``[lo, hi]``.

    ``bandwidth`` defaults to Silverman's; ``n_total`` (default: the finite
    values given) is the normaliser; ``quantum`` is the lattice spacing of a
    quantised feature, below half of which no curve is drawn.
    """
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    n = int(a.size)
    total = int(n_total) if n_total is not None else n
    x = np.linspace(lo, hi, int(points)) if hi > lo else np.asarray([lo], dtype=np.float64)
    out = KdeResult(x=[float(v) for v in x], pdf=None, bandwidth=None, grid_points=0,
                    delta=None, n=n, n_total=total, n_outside_grid=0)
    if n < MIN_KDE_SAMPLES:
        out.notes.append(f"N = {n}: no density curve below N = {MIN_KDE_SAMPLES}.")
        return out
    h = silverman_bandwidth(a) if bandwidth is None else float(bandwidth)
    out.bandwidth = h
    if h is None or not h > 0 or not hi > lo:
        out.notes.append("No spread in the sample, so no bandwidth: no density curve.")
        return out
    if quantum is not None and quantum > 0 and h < quantum / 2.0:
        out.notes.append(
            f"Bandwidth {h:.3g} is below half the feature's quantum {quantum:.3g}: a curve "
            "would draw the lattice, not the distribution, so none is drawn.")
        return out

    g0, g1 = lo - TRUNCATION_H * h, hi + TRUNCATION_H * h
    m = int(min(MAX_GRID, max(MIN_GRID, math.ceil((g1 - g0) / (h / 4.0)) + 1)))
    delta = (g1 - g0) / (m - 1)
    out.grid_points, out.delta = m, delta
    if delta > h / 2.0:
        out.notes.append("Bandwidth below the grid resolution: no density curve.")
        return out

    # Linear binning: weight 1 - f to node i, f to node i + 1.
    t = (a - g0) / delta
    inside = (t >= 0.0) & (t <= m - 1)
    out.n_outside_grid = int(n - inside.sum())
    t = t[inside]
    i = np.minimum(np.floor(t).astype(np.int64), m - 2)
    f = t - i
    counts = (np.bincount(i, weights=1.0 - f, minlength=m)
              + np.bincount(i + 1, weights=f, minlength=m))[:m]

    half = int(math.ceil(TRUNCATION_H * h / delta))
    j = np.arange(-half, half + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (j * delta / h) ** 2) / (h * math.sqrt(2.0 * math.pi))
    density = np.convolve(counts, kernel, mode="full")[half: half + m] / max(total, 1)
    grid = g0 + delta * np.arange(m)
    pdf = np.interp(x, grid, density)
    out.pdf = [float(v) for v in pdf]
    if out.n_outside_grid:
        out.notes.append(
            f"{out.n_outside_grid:,} values lie more than {TRUNCATION_H:g} bandwidths outside "
            "the drawn window; each would add under 3.4 × 10⁻⁴ of a peak, and they stay in "
            "the normaliser.")
    return out
