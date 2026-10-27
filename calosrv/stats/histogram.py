"""Density-normalised histograms for the reconstructed-energy panel.

All series in a panel share one binning. That is not a tidiness preference: the
panel overlays predicted against true energies for the same events, and two
histograms on different bin edges cannot be compared bin by bin no matter how
similar they look.

``density=True`` normalisation matches ``calodash/stats.py`` and the reference
notebook, and it is what makes the bars directly comparable with the fitted
Gaussian curve, which is a probability density.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

#: Bin count, transcribed from the reference notebook's ``bins=120``.
DEFAULT_BINS = 120

#: Fewest events for which a density histogram is drawn at all.
#:
#: This floor belongs to the histogram, not to the fit, and conflating the two
#: is what previously silenced mu and sigma on every small slice. The argument
#: is specific to the estimator: a ``density=True`` histogram normalises by
#: ``N * bin_width``, so once the bins are much finer than the spacing between
#: events each occupied bin holds exactly one event and reports a height of
#: ``1 / (N * bin_width)``. Over a range of ~18 GeV that is about 1.7 GeV^-1 at
#: N = 4 and higher still as N falls. What appears on the panel is then a comb
#: of tall, arbitrarily-scaled spikes at individual event energies - an artefact
#: of the estimator, not a distribution. Below this floor the individual events
#: are plotted instead; rescaling the axis would merely hide the comb.
#:
#: The mean and width of those same events remain perfectly well defined, and
#: ``stats/gaussian.py`` reports them from N = 2 with their uncertainty.
MIN_HISTOGRAM_SAMPLES = 15

#: Points used to draw a fitted curve. Enough that the peak is smooth at any
#: reasonable panel width, small enough that four series across five slices stay
#: well inside the payload budget.
CURVE_POINTS = 200


@dataclass
class Histogram:
    """One density-normalised histogram on a shared axis."""

    counts: list[float]
    centres: list[float]
    edges: list[float]
    n: int
    n_in_range: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "centres": self.centres,
            "n": self.n,
            "n_in_range": self.n_in_range,
        }


#: Fewest bins worth drawing. Below this the histogram stops describing a shape.
MIN_BINS = 8


def adaptive_bins(n: int, cap: int = DEFAULT_BINS) -> int:
    """Bin count for a sample of ``n`` events, by the Rice rule.

    Fixing the bin count at the notebook's 120 is right for the tens of
    thousands of events the full dataset holds and badly wrong for a few dozen.
    A ``density=True`` histogram normalises by ``N * bin_width``, so once the
    bins are much finer than the spacing between events each occupied bin holds
    exactly one event and reports a height of ``1 / (N * bin_width)``. The
    result is a comb of tall spikes whose height is set by the binning rather
    than by the distribution - which is precisely the artefact this panel was
    reported for.

    ``ceil(2 * n**(1/3))`` is the Rice rule, a standard choice that grows slowly
    enough to stay smooth at small n while still resolving structure at large n:
    5 bins at n = 15, 31 at n = 3700, 54 at n = 20000. It is clamped to
    ``MIN_BINS`` below and to the notebook's 120 above, so the busiest panels
    keep the resolution they always had.
    """
    if n <= 0:
        return MIN_BINS
    return int(max(MIN_BINS, min(cap, math.ceil(2.0 * n ** (1.0 / 3.0)))))


def axis_edges(lo: float, hi: float, bins: int = DEFAULT_BINS) -> np.ndarray:
    if not hi > lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, bins + 1, dtype=np.float64)


def density_histogram(
    values: np.ndarray, edges: np.ndarray
) -> Histogram:
    """Histogram ``values`` on fixed ``edges``, normalised to unit area."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    lo, hi = float(edges[0]), float(edges[-1])
    in_range = finite[(finite >= lo) & (finite <= hi)]

    if in_range.size == 0:
        counts = np.zeros(edges.size - 1, dtype=np.float64)
    else:
        counts, _ = np.histogram(in_range, bins=edges, density=True)

    centres = 0.5 * (edges[:-1] + edges[1:])
    return Histogram(
        counts=[float(c) for c in counts],
        centres=[float(c) for c in centres],
        edges=[float(e) for e in edges],
        n=int(finite.size),
        n_in_range=int(in_range.size),
    )


def curve_axis(lo: float, hi: float, points: int = CURVE_POINTS) -> np.ndarray:
    """Sample positions for a fitted probability density curve."""
    if not hi > lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, points, dtype=np.float64)


@dataclass
class CountHistogram:
    """Plain counts on fixed edges, with what fell either side of them."""

    counts: list[int]
    n: int
    n_in_range: int
    n_below: int
    n_above: int

    def as_dict(self) -> dict[str, Any]:
        return {"counts": self.counts, "n": self.n, "n_in_range": self.n_in_range,
                "n_below": self.n_below, "n_above": self.n_above}


def count_histogram(values: np.ndarray, edges: np.ndarray) -> CountHistogram:
    """Integer counts of the finite ``values`` on ``edges``; ``hi`` falls in the last bin.

    Counts, not densities: the caller draws a KDE scaled to expected counts per
    bin over them, and a reader can see that a bar of 3 is three events.
    """
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    lo, hi = float(edges[0]), float(edges[-1])
    below = int((finite < lo).sum())
    above = int((finite > hi).sum())
    inside = finite[(finite >= lo) & (finite <= hi)]
    counts, _ = np.histogram(inside, bins=edges)
    return CountHistogram([int(c) for c in counts], int(finite.size), int(inside.size),
                          below, above)


#: How the prediction residual histograms are binned (decision D-8), for their drawers.
FREEDMAN_DIACONIS_RULE = (
    "Freedman–Diaconis: bin width 2 · IQR · N^(−1/3), the widest among the drawn series so "
    f"they share one binning, clamped to {MIN_BINS}–{DEFAULT_BINS} bins over the axis. An "
    "exception to the Rice rule, for prediction residuals only: their tails are heavy, and "
    "a bin count set by the sample size alone spreads the core over a single bin of a range "
    "the tail sets, while the interquartile range follows the core")


def freedman_diaconis_bins(samples: list[np.ndarray], lo: float, hi: float,
                           cap: int = DEFAULT_BINS) -> tuple[int, float | None]:
    """``(bins, width)``: the Freedman–Diaconis count over [lo, hi], clamped to 8–``cap``.

    Each sample's width is ``2 · IQR · n^(−1/3)``; the widest is used so every
    series shares one binning and the smallest one, whose width is the
    largest, is not split finer than its own rule allows. ``width`` is
    ``None`` when no sample has a positive IQR (fewer than two distinct
    values in the middle half); the count then falls back to the Rice rule of
    the smallest sample, :func:`adaptive_bins`.
    """
    widths = []
    sizes = []
    for values in samples:
        x = np.asarray(values, dtype=np.float64)
        x = x[np.isfinite(x)]
        if x.size < 2:
            continue
        sizes.append(int(x.size))
        q1, q3 = np.percentile(x, [25.0, 75.0])
        if q3 > q1:
            widths.append(2.0 * float(q3 - q1) * x.size ** (-1.0 / 3.0))
    span = hi - lo
    if not widths or not span > 0:
        return adaptive_bins(min(sizes) if sizes else 0, cap), None
    width = max(widths)
    return int(max(MIN_BINS, min(cap, math.ceil(span / width - 1e-9)))), width
