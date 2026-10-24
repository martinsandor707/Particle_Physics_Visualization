"""The median and its 95% interval, from a seeded bootstrap or the order statistics.

Two intervals, gated by sample size:

* **From N = 20** the percentile bootstrap is the whisker. Below that the
  bootstrap distribution of a median sits on a handful of order statistics and
  the percentile interval under-covers - the robust floor of CLAUDE.md
  section 2.
* **From N = 6** the distribution-free order-statistic interval exists: the
  count of values below the true median is Bin(n, 1/2), so ``[x_(j),
  x_(n+1-j)]`` covers it with probability ``1 - 2 F(j - 1)`` whatever the
  distribution. Below N = 6 even ``[x_(1), x_(n)]`` covers less than 95%, so no
  interval is quoted at all. From N = 20 it is reported beside the bootstrap as
  a cross-check.

The bootstrap draws each replicate's median directly from its exact sampling
distribution instead of resampling ``n`` values: the k-th order statistic of
``n`` uniforms is Beta(k, n - k + 1), and resampling with replacement from a
sorted sample picks ``x_(ceil(n U))``. That is the same distribution at O(B)
cost, which matters when one request needs a hundred medians.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from . import gaussian
from .metrics import METHOD_BOOTSTRAP, METHOD_ORDER, Interval

BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 42
MIN_BOOTSTRAP_N = gaussian.MIN_ROBUST_SAMPLES
MIN_ORDER_N = 6


def _sorted_finite(values: np.ndarray) -> np.ndarray:
    a = np.asarray(values, dtype=np.float64)
    return np.sort(a[np.isfinite(a)])


def bootstrap_median_interval(
    values: np.ndarray,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int | Sequence[int] = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> Interval | None:
    """Percentile bootstrap interval of the median; ``None`` below N = 20.

    ``seed`` may be a sequence, so a caller computing many series seeds each
    from its own coordinates and an interval never depends on which other
    series the same request computed.
    """
    x = _sorted_finite(values)
    n = int(x.size)
    if n < MIN_BOOTSTRAP_N:
        return None
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    if n % 2:
        m = (n + 1) // 2
        u = rng.beta(m, n - m + 1, size=replicates)
        medians = x[np.clip(np.ceil(n * u).astype(np.int64), 1, n) - 1]
    else:
        m = n // 2
        u = rng.beta(m, n - m + 1, size=replicates)
        # Given U_(m) = u, the next order statistic is u + (1 - u) Beta(1, n - m).
        u2 = u + (1.0 - u) * rng.beta(1, n - m, size=replicates)
        lo = x[np.clip(np.ceil(n * u).astype(np.int64), 1, n) - 1]
        hi = x[np.clip(np.ceil(n * u2).astype(np.int64), 1, n) - 1]
        medians = 0.5 * (lo + hi)
    q_lo, q_hi = np.quantile(medians, [(1.0 - level) / 2.0, (1.0 + level) / 2.0])
    seed_text = seed if isinstance(seed, int) else "/".join(str(s) for s in seed)
    return Interval(float(q_lo), float(q_hi), METHOD_BOOTSTRAP,
                    f"95% percentile bootstrap of the median, B = {replicates:,}, seed {seed_text}")


def _binomial_half_cdf(n: int) -> np.ndarray:
    """P(Bin(n, 1/2) ≤ k) for k = 0..n, accumulated in log space."""
    k = np.arange(n, dtype=np.float64)
    log_steps = np.log((n - k) / (k + 1.0))
    log_pmf = np.concatenate(([-n * math.log(2.0)], -n * math.log(2.0) + np.cumsum(log_steps)))
    return np.exp(np.logaddexp.accumulate(log_pmf))


def median_order_interval(values: np.ndarray, level: float = 0.95) -> tuple[Interval, float] | None:
    """The distribution-free interval ``[x_(j), x_(n+1-j)]`` and its exact coverage.

    ``j`` is the largest integer with ``F(j - 1) ≤ (1 - level) / 2``, F the
    Bin(n, 1/2) CDF, so the coverage ``1 - 2 F(j - 1)`` is at least ``level``.
    ``None`` below N = 6.
    """
    x = _sorted_finite(values)
    n = int(x.size)
    if n < MIN_ORDER_N:
        return None
    cdf = _binomial_half_cdf(n)
    alpha = (1.0 - level) / 2.0
    # cdf[j - 1] <= alpha for j = 1 .. jmax; cdf[0] = 2^-n <= 0.025 from n = 6.
    j = int(np.searchsorted(cdf, alpha, side="right"))
    j = max(1, min(j, (n + 1) // 2))
    coverage = 1.0 - 2.0 * float(cdf[j - 1])
    interval = Interval(float(x[j - 1]), float(x[n - j]), METHOD_ORDER,
                        f"{100 * coverage:.1f}% order-statistic interval of the median, "
                        f"x₍{j}₎ to x₍{n + 1 - j}₎ of N = {n}")
    return interval, coverage


@dataclass(frozen=True)
class MedianEstimate:
    value: float | None
    n: int
    bootstrap: Interval | None
    order: Interval | None
    order_coverage: float | None
    note: str

    @property
    def interval(self) -> Interval | None:
        """The whisker: the bootstrap from N = 20, the order statistics from N = 6."""
        return self.bootstrap or self.order

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value, "n": self.n,
            "interval": self.interval.as_dict() if self.interval else None,
            "bootstrap": self.bootstrap.as_dict() if self.bootstrap else None,
            "order": self.order.as_dict() if self.order else None,
            "order_coverage": self.order_coverage, "note": self.note,
        }


def median_estimate(values: np.ndarray, seed: int | Sequence[int] = BOOTSTRAP_SEED) -> MedianEstimate:
    x = _sorted_finite(values)
    n = int(x.size)
    if n == 0:
        return MedianEstimate(None, 0, None, None, None, "No values in this selection.")
    value = float(np.median(x))
    if n < MIN_ORDER_N:
        return MedianEstimate(value, n, None, None, None,
                              f"N = {n}: no 95% interval of a median exists below N = "
                              f"{MIN_ORDER_N} without a distributional assumption.")
    order = median_order_interval(x)
    order_interval, coverage = order if order else (None, None)
    boot = bootstrap_median_interval(x, seed=seed)
    note = "" if boot is not None else (
        f"Order-statistic interval: the bootstrap needs N ≥ {MIN_BOOTSTRAP_N}.")
    return MedianEstimate(value, n, boot, order_interval, coverage, note)
