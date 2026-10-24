"""Correlations from moment sums, with an event-grouped jackknife on Fisher's z.

A hit-level correlation over 11 million hits is not 11 million independent
pairs. The incident momentum and angle take one value per event, repeated on
every hit, and the hits of one shower share its development, so Fisher's
``1 / sqrt(N - 3)`` with N = hits would quote ±0.0003 on everything. The
sampling unit is the event.

The database therefore returns the moment sums - count, Σ v_i and Σ v_i v_j -
per *group of events* (``event_number % G``, G ≤ 64; one group per event when
there are no more than 64), and the jackknife leaves one group out at a time:

    SE_J² = (G - 1) / G · Σ_g (z_(g) - z̄)²,  z = atanh r

with a Student-t quantile on G - 1 degrees of freedom. ``n_eff = 3 + 1 / SE_J²``
is the number of independent pairs the interval is worth, reported beside the
naive count so the reader sees how much the hits were not independent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .metrics import Interval, fisher_z_interval

#: Most event groups a hit scan rolls its sums up into.
MAX_GROUPS = 64
#: Fewest events for which a correlation is quoted.
MIN_R_EVENTS = 3
#: Fewest groups for which a jackknife interval is quoted.
MIN_JACKKNIFE_GROUPS = 4


def n_groups(n_events: int) -> int:
    """G = min(64, N events): with ≤ 64 events, a delete-one-event jackknife."""
    return max(0, min(MAX_GROUPS, int(n_events)))


def pearson_from_sums(n: float, s: np.ndarray, q: np.ndarray) -> np.ndarray:
    """The Pearson matrix from ``n``, ``s[i] = Σ v_i`` and ``q[i, j] = Σ v_i v_j``.

    Entries with no spread in either variable are NaN.
    """
    s = np.asarray(s, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    if not n > 1:
        return np.full(q.shape, np.nan)
    cov = q - np.outer(s, s) / n
    var = np.clip(np.diag(cov), 0.0, None)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = cov / np.sqrt(np.outer(var, var))
    r[~np.isfinite(r)] = np.nan
    return np.clip(r, -1.0, 1.0)


def grouped_jackknife(
    n_g: np.ndarray, s_g: np.ndarray, q_g: np.ndarray,
    statistic: Callable[[float, np.ndarray, np.ndarray], np.ndarray],
) -> np.ndarray:
    """``statistic`` evaluated with each group left out, stacked along axis 0."""
    n_g = np.asarray(n_g, dtype=np.float64)
    s_g = np.asarray(s_g, dtype=np.float64)
    q_g = np.asarray(q_g, dtype=np.float64)
    n, s, q = n_g.sum(), s_g.sum(axis=0), q_g.sum(axis=0)
    return np.stack([statistic(n - n_g[g], s - s_g[g], q - q_g[g]) for g in range(n_g.size)])


@dataclass
class FisherJackknife:
    """Every pair's r, its jackknife SE on z, and the interval ends, as k × k arrays."""

    r: np.ndarray
    se_z: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    n_eff: np.ndarray
    groups: int
    n_events: int

    def interval(self, i: int, j: int) -> Interval | None:
        if not np.isfinite(self.lo[i, j]):
            return None
        return fisher_z_interval(float(self.r[i, j]), self.n_events,
                                 se_z=float(self.se_z[i, j]), dof=self.groups - 1)


def jackknife_se_z(r_loo: np.ndarray) -> np.ndarray:
    """SE_J of atanh r from the leave-one-group-out estimates (axis 0)."""
    g = r_loo.shape[0]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.arctanh(np.clip(r_loo, -1.0, 1.0))
    # |r| = 1 (the diagonal, or a pair with no spread left) has no finite z:
    # its SE is NaN, and no interval is quoted for it.
    ok = np.isfinite(z).all(axis=0)
    out = np.full(z.shape[1:], np.nan)
    zs = z[:, ok]
    out[ok] = np.sqrt((g - 1) / g * np.sum((zs - zs.mean(axis=0)) ** 2, axis=0))
    return out


def fisher_jackknife(n_g: np.ndarray, s_g: np.ndarray, q_g: np.ndarray,
                     n_events: int) -> FisherJackknife:
    """r for every pair, with the event-grouped jackknife interval where it exists.

    r needs N ≥ 3 events; the interval needs G ≥ 4 groups and |r| < 1.
    """
    n_g = np.asarray(n_g, dtype=np.float64)
    s_g = np.asarray(s_g, dtype=np.float64)
    q_g = np.asarray(q_g, dtype=np.float64)
    k = s_g.shape[1]
    nan = np.full((k, k), np.nan)
    groups = int(n_g.size)
    if n_events < MIN_R_EVENTS:
        return FisherJackknife(nan.copy(), nan.copy(), nan.copy(), nan.copy(), nan.copy(),
                               groups, int(n_events))
    r = pearson_from_sums(n_g.sum(), s_g.sum(axis=0), q_g.sum(axis=0))
    se = lo = hi = n_eff = nan.copy()
    if groups >= MIN_JACKKNIFE_GROUPS:
        se = jackknife_se_z(grouped_jackknife(n_g, s_g, q_g, pearson_from_sums))
        lo, hi, n_eff = nan.copy(), nan.copy(), nan.copy()
        for i in range(k):
            for j in range(k):
                interval = fisher_z_interval(float(r[i, j]), int(n_events),
                                             se_z=float(se[i, j]), dof=groups - 1)
                if interval is not None:
                    lo[i, j], hi[i, j] = interval.lo, interval.hi
                    n_eff[i, j] = 3.0 + 1.0 / (se[i, j] ** 2)
    return FisherJackknife(r, se, lo, hi, n_eff, groups, int(n_events))


def mardia_r(r_xc: float, r_xs: float, r_cs: float) -> float | None:
    """Mardia's circular-linear correlation of x with an angle, from its cos and sin.

    ``R = sqrt((r_xc² + r_xs² - 2 r_xc r_xs r_cs) / (1 - r_cs²))`` in [0, 1]: how
    well x is predicted by the direction, with no sign because a circle has no
    order. ``None`` when cos and sin are perfectly correlated (one direction).
    """
    values = (r_xc, r_xs, r_cs)
    if any(v is None or not math.isfinite(v) for v in values):
        return None
    den = 1.0 - r_cs * r_cs
    if not den > 0:
        return None
    num = r_xc * r_xc + r_xs * r_xs - 2.0 * r_xc * r_xs * r_cs
    return math.sqrt(min(1.0, max(0.0, num / den)))


def mardia_from_sums(x: int, c: int, s: int) -> Callable[[float, np.ndarray, np.ndarray], np.ndarray]:
    """A jackknife statistic: Mardia R of variable ``x`` with the angle whose cos, sin are ``c``, ``s``."""

    def statistic(n: float, sums: np.ndarray, q: np.ndarray) -> np.ndarray:
        r = pearson_from_sums(n, sums, q)
        value = mardia_r(float(r[x, c]), float(r[x, s]), float(r[c, s]))
        return np.asarray(np.nan if value is None else value)

    return statistic


def jackknife_se(values_loo: np.ndarray) -> float | None:
    """The plain grouped-jackknife SE of a scalar statistic (no transform)."""
    v = np.asarray(values_loo, dtype=np.float64)
    v = v[np.isfinite(v)]
    g = v.size
    if g < MIN_JACKKNIFE_GROUPS:
        return None
    return float(math.sqrt((g - 1) / g * np.sum((v - v.mean()) ** 2)))
