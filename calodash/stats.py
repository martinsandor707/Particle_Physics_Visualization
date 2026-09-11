"""Distribution estimators, transcribed from ``plan-viz.ipynb``.

The notebook's fourth-panel code is explicitly a demonstration: it fabricates
both the separation ``d`` (``rng.uniform(0, 20)``) and the energies
(``rng.normal``), and its own comments say the real computation must replace
them. Its *numbers* are therefore discarded entirely. Its *estimators* are what
this project standardises on, so the dashboard stays comparable with the study
the notebook describes:

    mu        = np.mean(values)          # moments, not a fitted curve
    sigma     = np.std(values)           # ddof=0
    amplitude = 1 / (sigma * sqrt(2*pi))
    gaussian  = amplitude * exp(-0.5 * ((x - mu) / sigma)**2)
    hist      = np.histogram(values, bins=120, range=(0, EMAX), density=True)

Two deliberate departures, both recorded in the build output:

1. Aggregation is per event, not per hit. The notebook histograms raw hit rows,
   which is only defensible because its energies were synthetic; a
   reconstructed energy is a per-event quantity by definition.
2. mu and sigma are computed on the same in-range subset the histogram uses.
   ``density=True`` normalises over in-range counts only, so moments taken from
   the full sample would produce a curve that visibly fails to match the bars.

The functions here are used for the build-time summary table. Their exact
counterparts live in ``assets/dashboard.js`` so the panel can recompute live as
the filters move; the two implementations must be kept in step.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .constants import ENERGY_BINS


@dataclass
class BandSummary:
    """Fitted description of one selection's reconstructed-energy spectrum."""

    label: str
    count: int
    mu: float
    sigma: float
    resolution: float
    response: float
    truth_mu: float

    def as_dict(self) -> dict:
        return asdict(self)


def gaussian(x: np.ndarray, mu: float, sigma: float, amplitude: float) -> np.ndarray:
    """The notebook's Gaussian, verbatim."""
    return amplitude * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def unit_area_amplitude(sigma: float) -> float:
    """Amplitude that normalises the Gaussian to unit area."""
    return 1.0 / (sigma * np.sqrt(2.0 * np.pi)) if sigma > 0 else 0.0


def density_histogram(
    values: np.ndarray, lo: float, hi: float, bins: int = ENERGY_BINS
) -> tuple[np.ndarray, np.ndarray]:
    """Density-normalised histogram plus bin centres."""
    counts, edges = np.histogram(values, bins=bins, range=(lo, hi), density=True)
    centres = 0.5 * (edges[:-1] + edges[1:])
    return counts, centres


def summarise_band(
    label: str,
    e_reco: np.ndarray,
    p_true: np.ndarray,
    lo: float,
    hi: float,
) -> BandSummary | None:
    """Fit mu / sigma for one energy band, on the in-range subset.

    Returns ``None`` when the selection is too small to describe, mirroring the
    notebook's ``if len(values) < 10: continue``.
    """
    in_range = (e_reco >= lo) & (e_reco <= hi)
    values = e_reco[in_range]
    if values.size < 10:
        return None

    mu = float(np.mean(values))
    sigma = float(np.std(values))
    truth_mu = float(np.mean(p_true[in_range])) if p_true.size else float("nan")

    return BandSummary(
        label=label,
        count=int(values.size),
        mu=mu,
        sigma=sigma,
        resolution=sigma / mu if mu else float("nan"),
        response=mu / truth_mu if truth_mu else float("nan"),
        truth_mu=truth_mu,
    )


def separation_bins(distances: np.ndarray, edges) -> np.ndarray:
    """Assign separation distances to the notebook's ``d`` bins.

    Equivalent to ``pd.cut(..., include_lowest=True)`` over
    ``[0, 50, 100, 150, 200]`` mm. Unused until an overlap dataset is supplied;
    kept alongside the estimators it belongs with so the two paths stay
    consistent.
    """
    index = np.digitize(distances, np.asarray(edges[1:-1], dtype=float), right=False)
    outside = (distances < edges[0]) | (distances > edges[-1])
    return np.where(outside, -1, index)
