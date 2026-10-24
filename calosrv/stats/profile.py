"""Per-bin mean of per-shower profiles: the SD band and the Student-t envelope.

A longitudinal or radial profile is a fraction per bin per shower, ``f_i(j) =
e_i(j) / E_i``. Two marks summarise many of them, and CLAUDE.md section 2 keeps
them apart:

* the **SD band** - the sample SD of the per-shower fractions, ddof = 1, an
  uncapped shaded range: where individual showers lie;
* the **t-envelope** - ``m ± t_{0.975, G-1} SE``, capped: how well the mean
  itself is known.

The showers of one two-shower event are not independent - they share the
event's geometry - so the SE is cluster-robust with the event as the cluster:

    SE² = G / (G - 1) · (Σ_e c_e² - 2 m Σ_e M_e c_e + m² Σ_e M_e²) / N²

with ``c_e`` the summed fraction of event e's ``M_e`` showers and N showers in
G events. When each event holds one shower this is exactly ``s² / N``.

The arrays are the per-bin sums the database rolled up; nothing here sees a
hit. The gates follow the ensemble axis (``query/window_axis.py``): one shower
is labelled as such with no band, two carry "1 d.o.f.", and below N = 20 the
summary is weak and the range provisional.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import gaussian

#: Below this many showers the band is weak and the y-range provisional
#: (``grid.frame.PROVISIONAL_N``; CLAUDE.md section 2).
PROVISIONAL_N = gaussian.MIN_ROBUST_SAMPLES


@dataclass
class ProfileEstimate:
    mean: np.ndarray
    sd: np.ndarray | None
    half95: np.ndarray | None
    t_value: float | None
    n_units: int
    n_clusters: int
    label: str
    dof_note: str | None
    provisional: bool


def profile_estimate(
    c: np.ndarray, q: np.ndarray, n_units: int, *,
    cc: np.ndarray | None = None, mc: np.ndarray | None = None,
    m2: float | None = None, n_clusters: int | None = None,
) -> ProfileEstimate:
    """The mean, band and envelope of per-unit values from their per-bin sums.

    ``c = Σ_i f_i`` and ``q = Σ_i f_i²`` over the ``n_units`` showers, per bin.
    For clustered units pass ``cc = Σ_e c_e²``, ``mc = Σ_e M_e c_e`` per bin
    and ``m2 = Σ_e M_e²``, ``n_clusters = G``; omitted, each unit is its own
    cluster. A bin no shower reached has c = q = 0: its fraction is zero for
    every shower, and it is averaged as such.
    """
    c = np.asarray(c, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    n = int(n_units)
    if n <= 0:
        empty = np.full(c.shape, np.nan)
        return ProfileEstimate(empty, None, None, None, 0, 0, "no showers", None, True)
    mean = c / n
    if cc is None:
        cc, mc, m2, n_clusters = q, c, float(n), n
    g = int(n_clusters if n_clusters is not None else n)
    if n == 1:
        return ProfileEstimate(mean, None, None, None, 1, g,
                               "single shower, not an ensemble", None, True)
    var = np.clip((q - n * mean * mean) / (n - 1), 0.0, None)
    sd = np.sqrt(var)
    half95, t_value = None, None
    if g >= 2:
        cc = np.asarray(cc, dtype=np.float64)
        mc = np.asarray(mc, dtype=np.float64)
        num = np.clip(cc - 2.0 * mean * mc + mean * mean * float(m2), 0.0, None)
        se = np.sqrt(g / (g - 1) * num) / n
        t_value = gaussian.t_quantile_975(g - 1)
        half95 = t_value * se
    provisional = n < PROVISIONAL_N
    label = f"weak (N = {n})" if provisional else ""
    return ProfileEstimate(mean, sd, half95, t_value, n, g, label,
                           "1 d.o.f." if n == 2 else None, provisional)


def scalar_estimate(c: float, q: float, n: int) -> tuple[float | None, float | None, float | None]:
    """``(mean, sd, t half-width)`` of one per-unit quantity from Σ and Σ²."""
    if n <= 0:
        return None, None, None
    est = profile_estimate(np.asarray([c]), np.asarray([q]), n)
    sd = float(est.sd[0]) if est.sd is not None else None
    half = float(est.half95[0]) if est.half95 is not None else None
    mean = float(est.mean[0])
    return (mean if math.isfinite(mean) else None), sd, half
