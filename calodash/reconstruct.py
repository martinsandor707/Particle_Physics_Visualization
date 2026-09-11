"""Conventional calorimetric energy reconstruction.

This is the "conventional method" half of the comparison the fourth panel is
built around. It needs no trained model: a sampling calorimeter reconstructs
energy by summing the visible deposits and dividing by the sampling fraction.

    E_reco = sum(E_hit) / f,    f = sum(E_dep) / sum(p_true)

``f`` is fitted from the data itself, not assumed. On the shipped dataset it
comes out at 0.008790, i.e. roughly 1 part in 114 of the incident energy is
visible.

One property of this estimator is worth stating plainly, because it bounds what
the panel can demonstrate: with a single global ``f`` calibrated on the same
sample, ``mean(E_reco) == mean(p)`` holds *by construction*. The absolute scale
therefore cannot falsify anything. The per-event residual ``(E_reco - p) / p``
is the quantity that actually measures resolution, which is why the dashboard
offers both views.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Calibration:
    """Sampling-fraction calibration, fitted from the input data."""

    sampling_fraction: float
    n_events: int
    method: str = "global energy-weighted ratio sum(E_dep)/sum(p_true)"

    @property
    def inverse(self) -> float:
        return 1.0 / self.sampling_fraction if self.sampling_fraction else float("nan")

    def lines(self) -> list[str]:
        return [
            f"  sampling fraction f = {self.sampling_fraction:.6f}  (1/f = {self.inverse:.1f})",
            f"  fitted on {self.n_events:,} events via {self.method}",
        ]


def per_event_energy(hits: pd.DataFrame) -> pd.Series:
    """Total visible deposit per event, in GeV."""
    return hits.groupby("event_number")["energy"].sum()


def fit_calibration(deposited: pd.Series, truth: pd.Series) -> Calibration:
    """Fit the sampling fraction as the ratio of summed energies.

    Summing before dividing, rather than averaging per-event ratios, keeps the
    many low-multiplicity events from dominating: 17.2% of events have a single
    hit, and their individual ratios are almost pure containment noise.
    """
    aligned_truth = truth.reindex(deposited.index)
    total_truth = float(aligned_truth.sum())
    if total_truth <= 0:
        raise ValueError("Total incident momentum is zero; cannot fit a sampling fraction.")

    fraction = float(deposited.sum()) / total_truth
    if not np.isfinite(fraction) or fraction <= 0:
        raise ValueError(f"Fitted sampling fraction is not usable: {fraction!r}")

    return Calibration(sampling_fraction=fraction, n_events=len(deposited))


def reconstruct(events: pd.DataFrame, calibration: Calibration) -> pd.DataFrame:
    """Add reconstructed energy and fractional residual to the event frame."""
    frame = events.copy()
    frame["e_reco"] = frame["e_dep"].to_numpy() / calibration.sampling_fraction

    truth = frame["p_true"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        residual = np.where(truth > 0, (frame["e_reco"].to_numpy() - truth) / truth, np.nan)
    frame["residual"] = residual
    return frame


def energy_axis_max(e_reco: np.ndarray, p_true: np.ndarray) -> float:
    """Upper limit of the reconstructed-energy axis.

    ``plan-viz.ipynb`` uses ``max(25, percentile(energy, 99.5))`` for a 20 GeV
    dataset. Generalised here so the same rule adapts to the 1 GeV sample:
    cover the truth range with headroom, but never clip the visible tail.
    """
    if e_reco.size == 0:
        return 1.0
    truth_headroom = 1.2 * float(np.max(p_true)) if p_true.size else 0.0
    tail = float(np.percentile(e_reco, 99.5))
    return float(max(truth_headroom, tail))
