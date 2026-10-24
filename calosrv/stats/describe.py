"""Descriptive statistics of a sample, and quantiles of a weighted histogram.

``describe()`` is the notebook's ``pandas.DataFrame.describe()`` row with the
two widths CLAUDE.md section 2 asks for: the unbiased ``ddof = 1`` SD every
panel quotes, and the ``ddof = 0`` population form so the numbers stay directly
comparable with the reference notebook. Quartiles are ``np.percentile``'s
linear interpolation, which is pandas' default.

``weighted_quantiles()`` reads energy-weighted quantiles off a fine histogram
the database already reduced, so a 24-million-hit selection never leaves
DuckDB as raw values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from . import gaussian

#: Below this many values a quartile interpolates between individual events
#: (CLAUDE.md section 2: the robust floor).
ROBUST_N = gaussian.MIN_ROBUST_SAMPLES


@dataclass(frozen=True)
class Description:
    n: int
    n_nonfinite: int
    mean: float | None
    sd: float | None
    sd_population: float | None
    min: float | None
    q25: float | None
    q50: float | None
    q75: float | None
    max: float | None
    note: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def describe(values: np.ndarray) -> Description:
    """count, mean, SD (ddof 1 and 0), min, quartiles, max of the finite values.

    Non-finite values are counted, never zero-filled. The SD needs N ≥ 2; at
    N = 2 it is one pairwise difference with a single degree of freedom, which
    the note says.
    """
    a = np.asarray(values, dtype=np.float64)
    keep = np.isfinite(a)
    n_nonfinite = int(a.size - keep.sum())
    a = a[keep]
    n = int(a.size)
    if n == 0:
        return Description(0, n_nonfinite, None, None, None, None, None, None, None, None,
                           "No finite values in this selection.")
    q25, q50, q75 = (float(q) for q in np.percentile(a, (25.0, 50.0, 75.0)))
    notes = []
    if n == 1:
        notes.append("N = 1: a single value; no spread can be estimated.")
    elif n == 2:
        notes.append("N = 2: the SD is one pairwise difference, 1 d.o.f.")
    if 1 < n < ROBUST_N:
        notes.append(f"Quartiles interpolate between individual events below N = {ROBUST_N}.")
    return Description(
        n=n, n_nonfinite=n_nonfinite,
        mean=float(a.mean()),
        sd=float(a.std(ddof=gaussian.DDOF)) if n >= 2 else None,
        sd_population=float(a.std(ddof=0)),
        min=float(a.min()), q25=q25, q50=q50, q75=q75, max=float(a.max()),
        note=" ".join(notes),
    )


def weighted_quantiles(
    bin_lo: np.ndarray, weights: np.ndarray, width: float, levels: Sequence[float]
) -> list[float | None]:
    """Quantiles of a weighted histogram, linear within the crossing bin.

    ``bin_lo`` are the bins' lower edges in any order, ``weights`` their summed
    weights (energy, say) and ``width`` the common bin width. A level whose
    cumulative weight falls inside a bin is placed at the matching fraction of
    that bin, so the answer is exact to one bin width - 1 mm on the physics
    panels' quantile grids. Bins with no positive weight are skipped. ``None``
    for every level when the total weight is not positive.
    """
    lo = np.asarray(bin_lo, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    keep = np.isfinite(lo) & np.isfinite(w) & (w > 0)
    lo, w = lo[keep], w[keep]
    total = float(w.sum())
    if lo.size == 0 or not total > 0:
        return [None for _ in levels]
    order = np.argsort(lo, kind="stable")
    lo, w = lo[order], w[order]
    cumulative = np.cumsum(w)
    out: list[float | None] = []
    for level in levels:
        target = min(max(float(level), 0.0), 1.0) * total
        i = int(np.searchsorted(cumulative, target, side="left"))
        i = min(i, lo.size - 1)
        below = float(cumulative[i - 1]) if i > 0 else 0.0
        fraction = (target - below) / float(w[i]) if w[i] > 0 else 0.0
        out.append(float(lo[i] + min(max(fraction, 0.0), 1.0) * width))
    return out
