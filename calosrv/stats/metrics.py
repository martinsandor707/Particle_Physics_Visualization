"""Model-performance metric formulas.

Kept apart from the SQL that supplies their inputs so the definitions can be
read and checked on their own.

The one that matters most here is the distinction between the plain and the
energy-weighted voxel error. Per-hit energies span fifteen decades and the
overwhelming majority of hits are sub-femto-GeV dust, where the segmentation
model's answer is physically irrelevant. An unweighted mean absolute error is
therefore dominated by cells nobody cares about, and will look excellent while
the model is wrong about the shower core. The energy-weighted form -
``sum(energy * |pred - true|) / sum(energy)`` - answers the question actually
being asked, which is how much *energy* the model mis-assigns. Both are
reported; the energy-weighted one is the headline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any


def finite(value: float | None) -> float | None:
    """Return ``value`` only if it is a real, representable number.

    Infinities and NaNs reach here legitimately. A relative residual
    ``(pred - true) / true`` over an event whose true energy is a few
    femto-GeV overflows to infinity, and a correlation over a single event is
    NaN. Neither is a measurement, and neither can be encoded as JSON - the
    model-performance endpoint returned HTTP 500 with "Out of range float
    values are not JSON compliant" for exactly this reason on narrow
    selections. Reporting ``null``, which the interface renders as an em dash,
    is both honest and serialisable.
    """
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return finite(numerator / denominator)


@dataclass
class ClassificationMetrics:
    """Voxel-level assignment quality at a 0.5 decision threshold."""

    n_voxels: int
    accuracy: float | None
    precision_a: float | None
    recall_a: float | None
    f1_a: float | None
    shared_voxel_fraction: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegressionMetrics:
    """Error on the continuous voxel fraction itself."""

    mae: float | None
    mae_energy_weighted: float | None
    rmse: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnergyResidualMetrics:
    """Per-event energy reconstruction quality, in calibrated GeV."""

    bias_gev: float | None
    rmse_gev: float | None
    relative_bias: float | None
    relative_resolution: float | None
    median_absolute_relative: float | None
    correlation: float | None
    slope: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classification(
    n_voxels: int,
    n_correct: int,
    n_true_a: int,
    n_pred_a: int,
    n_tp: int,
    n_shared: int,
) -> ClassificationMetrics:
    """Roll up the stored classification counts.

    Every input is an exact sum over the selected events, so these are exact
    metrics over the selection - not estimates from a sample.
    """
    return ClassificationMetrics(
        n_voxels=n_voxels,
        accuracy=_safe_div(n_correct, n_voxels),
        precision_a=_safe_div(n_tp, n_pred_a),
        recall_a=_safe_div(n_tp, n_true_a),
        f1_a=_safe_div(2.0 * n_tp, n_pred_a + n_true_a),
        shared_voxel_fraction=_safe_div(n_shared, n_voxels),
    )


def regression(
    n_voxels: int,
    sum_abs_err: float,
    sum_wabs_err: float,
    sum_sq_err: float,
    e_dep: float,
) -> RegressionMetrics:
    mse = _safe_div(sum_sq_err, n_voxels)
    return RegressionMetrics(
        mae=_safe_div(sum_abs_err, n_voxels),
        mae_energy_weighted=_safe_div(sum_wabs_err, e_dep),
        rmse=finite(mse ** 0.5) if mse is not None and mse >= 0 else None,
    )
