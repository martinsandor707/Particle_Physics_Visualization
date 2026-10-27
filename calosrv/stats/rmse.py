"""The RMSE of a sample of residuals and its 95% interval, by sample size (decision D-4).

Two intervals, gated like the median's (``stats/median.py``):

* **N = 2-19: a χ² interval under normal residuals.** If the residuals are
  drawn from N(0, σ²), ``n · RMSE² / σ²`` is χ² with ``n`` degrees of freedom
  (``n``, not ``n − 1``: the RMSE is taken about zero, not about the sample
  mean), so the 95% interval of the population RMS is
  ``[RMSE · √(n / χ²₀.₉₇₅,ₙ), RMSE · √(n / χ²₀.₀₂₅,ₙ)]``. It is exact under that
  assumption and approximate otherwise; with a bias the residuals are not
  centred on zero and the interval is approximate. The assumption is stated
  with the interval. It replaces the square root of the Student-t interval of
  the mean squared residual, whose lower end collapses to zero at N ≤ 8 and
  whose coverage on squared residuals is poor.
* **From N = 20: the seeded percentile bootstrap of the RMSE**, B = 2,000, each
  group seeded from its own coordinates exactly as the median's bootstrap is
  (``numpy.random.SeedSequence(seed)``), so an interval never depends on which
  other series a request computed.

At N = 1 the RMSE is the one residual's magnitude: an observation, with no
interval. Used by the momentum-bin performance (E2) only; the Physics page's
metric cards keep ``metrics.residual_summary``.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from . import gaussian
from .median import BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, MIN_BOOTSTRAP_N
from .metrics import METHOD_BOOTSTRAP, Estimate, Interval

#: The χ² interval of an RMSE under normal residuals centred on zero.
METHOD_CHI2_RMSE = "chi2_rmse"

#: Fewest residuals for a χ² interval (one degree of freedom is weak but defined).
MIN_CHI2_N = 2

#: Most resampled values held at once while bootstrapping (memory, not accuracy).
_CHUNK_VALUES = 4_000_000

NORMALITY = ("assumes normally distributed residuals centred on zero; approximate "
             "otherwise, and with a bias")


def chi2_interval(rmse: float, n: int) -> Interval | None:
    """``[RMSE·√(n/χ²₀.₉₇₅,ₙ), RMSE·√(n/χ²₀.₀₂₅,ₙ)]``; ``None`` below N = 2."""
    if n < MIN_CHI2_N or not math.isfinite(rmse):
        return None
    lo = rmse * math.sqrt(n / gaussian.chi2_quantile(n, upper=True))
    hi = rmse * math.sqrt(n / gaussian.chi2_quantile(n, upper=False))
    return Interval(lo, hi, METHOD_CHI2_RMSE,
                    f"95% χ² interval of the RMSE, {n} dof; {NORMALITY}")


def bootstrap_interval(
    residuals: np.ndarray,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int | Sequence[int] = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> Interval | None:
    """Percentile bootstrap interval of the RMSE; ``None`` below N = 20.

    Each replicate resamples the ``n`` residuals with replacement and takes the
    root of their mean square. Drawn in chunks so a large bin never holds
    ``B × n`` indices at once; the draws are the same whatever the chunking.
    """
    r = np.asarray(residuals, dtype=np.float64)
    sq = r[np.isfinite(r)] ** 2
    n = int(sq.size)
    if n < MIN_BOOTSTRAP_N:
        return None
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    rows = max(1, _CHUNK_VALUES // n)
    means = np.empty(replicates, dtype=np.float64)
    for start in range(0, replicates, rows):
        stop = min(replicates, start + rows)
        index = rng.integers(0, n, size=(stop - start, n))
        means[start:stop] = sq[index].mean(axis=1)
    q_lo, q_hi = np.quantile(np.sqrt(means), [(1.0 - level) / 2.0, (1.0 + level) / 2.0])
    seed_text = seed if isinstance(seed, int) else "/".join(str(s) for s in seed)
    return Interval(float(q_lo), float(q_hi), METHOD_BOOTSTRAP,
                    f"95% percentile bootstrap of the RMSE, B = {replicates:,}, seed {seed_text}")


def rmse_estimate(residuals: np.ndarray, seed: int | Sequence[int] = BOOTSTRAP_SEED) -> Estimate:
    """The RMSE with its interval: none at N = 1, χ² to N = 19, the bootstrap from N = 20.

    Non-finite residuals are dropped, never zero-filled. ``se`` is the
    large-sample standard error under normality, RMSE / √(2n), for reference.
    """
    r = np.asarray(residuals, dtype=np.float64)
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n == 0:
        return Estimate(None, n=0, note="No showers in this selection.")
    rmse = float(math.sqrt(np.mean(r * r)))
    if n < MIN_CHI2_N:
        return Estimate(rmse, n=1, note="N = 1: a single residual is an observation; no "
                                        "uncertainty can be estimated.")
    se = rmse / math.sqrt(2.0 * n)
    if n < MIN_BOOTSTRAP_N:
        return Estimate(rmse, se, chi2_interval(rmse, n), n,
                        f"χ² interval: the bootstrap needs N ≥ {MIN_BOOTSTRAP_N}.")
    return Estimate(rmse, se, bootstrap_interval(r, seed=seed), n)
