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

**Mardia's circular-linear R** regresses a variable on (cos φ, sin φ): an
intercept and two slopes. Three directions fit any variable exactly (R = 1
whatever the data), and with a handful the fit follows the points rather than
a dependence, so R is quoted only from :data:`MIN_MARDIA_AZIMUTHS` *distinct*
directions - not events, which can share one - and its jackknife SE only from
:data:`MIN_MARDIA_GROUPS` groups. Under no association R² averages
:func:`mardia_null_r2` = 2 / (N − 1), given beside R.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import gaussian
from .metrics import Interval, fisher_z_interval

#: Most event groups a hit scan rolls its sums up into.
MAX_GROUPS = 64
#: Fewest events for which a correlation is quoted.
MIN_R_EVENTS = 3
#: Fewest groups for which a jackknife interval is quoted.
MIN_JACKKNIFE_GROUPS = 4

#: Fewest distinct directions for which Mardia's R is quoted: the curve floor of
#: CLAUDE.md's low-N table. R claims a shape of dependence on the direction,
#: which fewer directions cannot constrain; at three it is identically 1.
MIN_MARDIA_AZIMUTHS = gaussian.MIN_CURVE_SAMPLES
#: Fewest groups for a jackknife SE of Mardia's R, one more than the linear
#: cells need: R is bounded at 1 and untransformed, and a four-event selection
#: was measured serving an SE of exactly 0 because each of its leave-one-out
#: samples, three directions, reproduced R = 1.
MIN_MARDIA_GROUPS = 5


def n_groups(n_events: int) -> int:
    """G = min(64, N events): with ≤ 64 events, a delete-one-event jackknife."""
    return max(0, min(MAX_GROUPS, int(n_events)))


def group_ids(event_number: np.ndarray) -> np.ndarray:
    """Each row's jackknife group when every row is one event, as ``hit_sql.group_key``.

    Up to :data:`MAX_GROUPS` events each is its own group; above, the event
    number modulo G, non-negative.
    """
    events = np.asarray(event_number, dtype=np.int64)
    if events.size <= MAX_GROUPS:
        return np.arange(events.size, dtype=np.int64)
    return np.mod(events, n_groups(events.size))


@dataclass(frozen=True)
class Grouping:
    """Rows sorted into jackknife groups once, so many moment sums can share the sort."""

    order: np.ndarray       # row order that makes each group contiguous
    starts: np.ndarray      # first sorted row of each group
    ends: np.ndarray        # one past its last

    @classmethod
    def of(cls, group: np.ndarray) -> "Grouping":
        group = np.asarray(group)
        order = np.argsort(group, kind="stable")
        ordered = group[order]
        if ordered.size == 0:
            starts = np.zeros(0, dtype=np.int64)
        else:
            starts = np.flatnonzero(np.concatenate([[True], ordered[1:] != ordered[:-1]]))
        ends = np.concatenate([starts[1:], [ordered.size]]).astype(np.int64)
        return cls(order, starts, ends)

    def sums(self, data: np.ndarray, keep: np.ndarray | None = None,
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(n_g, s_g, q_g)`` of the rows of ``data`` (N × k) that ``keep`` holds.

        A row left out weighs nothing, whatever its value; a group left with
        no rows is dropped, so it cannot enter a jackknife as a sample that
        leaves nothing out.
        """
        data = np.asarray(data, dtype=np.float64)
        if data.ndim == 1:
            data = data[:, None]
        k = data.shape[1]
        if self.starts.size == 0:
            return np.zeros(0), np.zeros((0, k)), np.zeros((0, k, k))
        rows = data[self.order]
        if keep is None:
            weight = np.ones(self.order.size)
        else:
            weight = np.asarray(keep, dtype=bool)[self.order].astype(np.float64)
            rows = np.where(weight[:, None] > 0.0, rows, 0.0)
        n_g = np.add.reduceat(weight, self.starts)
        s_g = np.add.reduceat(rows, self.starts, axis=0)
        q_g = np.stack([rows[a:b].T @ rows[a:b] for a, b in zip(self.starts, self.ends)])
        present = n_g > 0
        return n_g[present], s_g[present], q_g[present]


def sums_by_group(data: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(n_g, s_g, q_g)``: count, Σ v_i and Σ v_i v_j of the rows of ``data`` per group.

    The NumPy counterpart of a grouped moment scan, for samples already in
    memory; ``data`` is N × k, ``group`` the N group ids.
    """
    return Grouping.of(group).sums(data)


def pearson_stack(n: np.ndarray, s: np.ndarray, q: np.ndarray) -> np.ndarray:
    """:func:`pearson_from_sums` over a leading axis: ``n`` (G,), ``s`` (G, k), ``q`` (G, k, k)."""
    n = np.asarray(n, dtype=np.float64)
    s = np.asarray(s, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = q - s[..., :, None] * s[..., None, :] / n[..., None, None]
        var = np.clip(np.diagonal(cov, axis1=-2, axis2=-1), 0.0, None)
        r = cov / np.sqrt(var[..., :, None] * var[..., None, :])
    r[~np.isfinite(r)] = np.nan
    r[~(n > 1)] = np.nan
    return np.clip(r, -1.0, 1.0)


def pearson_from_sums(n: float, s: np.ndarray, q: np.ndarray) -> np.ndarray:
    """The Pearson matrix from ``n``, ``s[i] = Σ v_i`` and ``q[i, j] = Σ v_i v_j``.

    Entries with no spread in either variable are NaN.
    """
    s = np.asarray(s, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    return pearson_stack(np.asarray([n], dtype=np.float64), s[None], q[None])[0]


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


#: Within this of |r(cos, sin)| = 1 the two are collinear: the angle takes two values at most.
COLLINEAR_TOL = 1e-9


def mardia_r_stack(r_xc: np.ndarray, r_xs: np.ndarray, r_cs: np.ndarray) -> np.ndarray:
    """:func:`mardia_r` elementwise over arrays, NaN where it is ``None``: the one formula."""
    r_xc, r_xs, r_cs = (np.asarray(v, dtype=np.float64) for v in (r_xc, r_xs, r_cs))
    regular = np.isfinite(r_cs) & (1.0 - np.abs(r_cs) > COLLINEAR_TOL)
    with np.errstate(invalid="ignore", divide="ignore"):
        num = r_xc * r_xc + r_xs * r_xs - 2.0 * r_xc * r_xs * r_cs
        full = np.sqrt(np.clip(num / (1.0 - r_cs * r_cs), 0.0, 1.0))
    full = np.where(np.isfinite(r_xc) & np.isfinite(r_xs), full, np.nan)
    fallback = np.where(np.isfinite(r_xc), np.minimum(1.0, np.abs(r_xc)),
                        np.where(np.isfinite(r_xs), np.minimum(1.0, np.abs(r_xs)), np.nan))
    return np.where(regular, full, fallback)


def mardia_r(r_xc: float, r_xs: float, r_cs: float) -> float | None:
    """Mardia's circular-linear correlation of x with an angle, from its cos and sin.

    ``R = sqrt((r_xc² + r_xs² - 2 r_xc r_xs r_cs) / (1 - r_cs²))`` in [0, 1]: how
    well x is predicted by the direction, with no sign because a circle has no
    order. Where cos and sin are collinear (two azimuths) the form is 0/0 and
    would return rounding noise; there, and where one of them has no spread (two
    azimuths mirrored about an axis), the multiple correlation on (cos, sin) is
    the |r| on the one that varies. ``None`` when neither varies (one azimuth)
    or x does not.
    """
    value = float(mardia_r_stack(*(np.nan if v is None else v for v in (r_xc, r_xs, r_cs))))
    return value if math.isfinite(value) else None


def jackknife_se(values_loo: np.ndarray, min_groups: int = MIN_JACKKNIFE_GROUPS) -> float | None:
    """The plain grouped-jackknife SE of a scalar statistic (no transform)."""
    v = np.asarray(values_loo, dtype=np.float64)
    v = v[np.isfinite(v)]
    g = v.size
    if g < max(2, int(min_groups)):
        return None
    return float(math.sqrt((g - 1) / g * np.sum((v - v.mean()) ** 2)))


def mardia_gate(n_azimuths: int, where: str = "this selection") -> str | None:
    """Why Mardia's R is not quoted over ``n_azimuths`` distinct directions; ``None`` when it is."""
    floor = MIN_MARDIA_AZIMUTHS
    if n_azimuths >= floor:
        return None
    return (f"Mardia's R needs {floor} distinct azimuths; {where} has {n_azimuths:,}. "
            "Three directions fit any variable exactly (R = 1), and a few cannot constrain "
            "a dependence on the direction.")


def mardia_null_r2(n: int) -> float | None:
    """E[R²] = 2 / (N − 1): Mardia's R² under no association, over N independent units.

    R² is the multiple correlation on (cos φ, sin φ), two regressors, so with N
    independent Gaussian observations and no dependence it is Beta(1, (N − 3)/2)
    distributed with mean 2 / (N − 1). An R² near it is no evidence of
    association. ``None`` below N = 4, where the distribution is degenerate.
    """
    if n is None or n < 4:
        return None
    return 2.0 / (n - 1)


def mardia_jackknife(n_g: np.ndarray, s_g: np.ndarray, q_g: np.ndarray,
                     x: int, c: int, s: int) -> tuple[float | None, float | None]:
    """``(R, SE)``: Mardia's R of variable ``x`` with the angle whose cos, sin are ``c``, ``s``.

    Ungated on the directions - the caller applies :func:`mardia_gate`. The SE is
    the grouped jackknife's from :data:`MIN_MARDIA_GROUPS` groups, never clamped:
    a spread of rounding size is served as measured, not rounded to a zero.
    """
    n_g = np.asarray(n_g, dtype=np.float64)
    s_g = np.asarray(s_g, dtype=np.float64)
    q_g = np.asarray(q_g, dtype=np.float64)
    if n_g.size == 0:
        return None, None
    r = pearson_from_sums(n_g.sum(), s_g.sum(axis=0), q_g.sum(axis=0))
    value = mardia_r(float(r[x, c]), float(r[x, s]), float(r[c, s]))
    if value is None:
        return None, None
    se = None
    if n_g.size >= MIN_MARDIA_GROUPS:
        # Every leave-one-group-out sample at once: the sums less each group.
        r_loo = pearson_stack(n_g.sum() - n_g, s_g.sum(axis=0) - s_g, q_g.sum(axis=0) - q_g)
        loo = mardia_r_stack(r_loo[:, x, c], r_loo[:, x, s], r_loo[:, c, s])
        se = jackknife_se(loo, min_groups=MIN_MARDIA_GROUPS)
    return value, se
