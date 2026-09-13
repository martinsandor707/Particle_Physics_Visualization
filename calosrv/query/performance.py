"""Model-performance metrics for the sidebar KPI card.

Every number here is an exact roll-up over the selected events, not an estimate.
That follows from how ``event_<name>`` is built: the stored quantities are
additive sufficient statistics, so accuracy, MAE and RMSE over any subset are
``sum(numerator) / sum(denominator)`` over roughly twenty thousand rows.

The per-slice breakdown is computed alongside the global figure because the
interesting claim about a segmentation model is that it degrades as the two
showers move closer together, and a single global accuracy hides exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import duckdb

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..stats import metrics as metric_mod
from ..stats.slices import Slice, build_slices, case_sql
from .filters import FilterSpec

_AGGREGATES = """
    count(*)                                AS n_events,
    coalesce(sum(n_hits), 0)                AS n_voxels,
    coalesce(sum(e_dep), 0.0)               AS e_dep,
    coalesce(sum(n_correct), 0)             AS n_correct,
    coalesce(sum(n_true_a), 0)              AS n_true_a,
    coalesce(sum(n_pred_a), 0)              AS n_pred_a,
    coalesce(sum(n_tp), 0)                  AS n_tp,
    coalesce(sum(n_shared), 0)              AS n_shared,
    coalesce(sum(sum_abs_err), 0.0)         AS sum_abs_err,
    coalesce(sum(sum_wabs_err), 0.0)        AS sum_wabs_err,
    coalesce(sum(sum_sq_err), 0.0)          AS sum_sq_err,

    -- Energy residuals are per-event quantities, so they are averaged over
    -- events here rather than over voxels.
    avg(e_a_pred - e_a_true)                                        AS bias_a,
    sqrt(avg(pow(e_a_pred - e_a_true, 2)))                          AS rmse_a,
    avg((e_a_pred - e_a_true) / nullif(e_a_true, 0))                AS rel_bias_a,
    stddev_samp((e_a_pred - e_a_true) / nullif(e_a_true, 0))        AS rel_res_a,
    median(abs(e_a_pred - e_a_true) / nullif(e_a_true, 0))          AS rel_med_a,
    corr(e_a_pred, e_a_true)                                        AS corr_a,
    regr_slope(e_a_pred, e_a_true)                                  AS slope_a,

    avg(e_b_pred - e_b_true)                                        AS bias_b,
    sqrt(avg(pow(e_b_pred - e_b_true, 2)))                          AS rmse_b,
    avg((e_b_pred - e_b_true) / nullif(e_b_true, 0))                AS rel_bias_b,
    stddev_samp((e_b_pred - e_b_true) / nullif(e_b_true, 0))        AS rel_res_b,
    median(abs(e_b_pred - e_b_true) / nullif(e_b_true, 0))          AS rel_med_b,
    corr(e_b_pred, e_b_true)                                        AS corr_b,
    regr_slope(e_b_pred, e_b_true)                                  AS slope_b
"""


@dataclass
class PerformanceReport:
    n_events: int
    classification: metric_mod.ClassificationMetrics
    regression: metric_mod.RegressionMetrics
    energy_a: metric_mod.EnergyResidualMetrics
    energy_b: metric_mod.EnergyResidualMetrics
    by_slice: list[dict[str, Any]]
    slices: list[Slice]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "classification": self.classification.as_dict(),
            "regression": self.regression.as_dict(),
            "energy_residuals": {
                "a": self.energy_a.as_dict(),
                "b": self.energy_b.as_dict(),
            },
            "by_slice": self.by_slice,
            "slices": [s.as_dict() for s in self.slices],
            "notes": {
                "mae": (
                    "Unweighted voxel MAE counts every hit equally. Per-hit "
                    "energies span fifteen decades, so this figure is dominated "
                    "by sub-femto-GeV cells where the assignment is physically "
                    "irrelevant."
                ),
                "mae_energy_weighted": (
                    "Energy-weighted MAE is the fraction of deposited energy "
                    "the model mis-assigns between the two showers. This is the "
                    "headline figure."
                ),
                "exactness": (
                    "All metrics are exact roll-ups of per-event sufficient "
                    "statistics over the selected events, not sampled estimates."
                ),
            },
        }


def _row_to_dict(row: tuple, names: Sequence[str]) -> dict[str, Any]:
    return dict(zip(names, row))


_NAMES = (
    "n_events", "n_voxels", "e_dep", "n_correct", "n_true_a", "n_pred_a",
    "n_tp", "n_shared", "sum_abs_err", "sum_wabs_err", "sum_sq_err",
    "bias_a", "rmse_a", "rel_bias_a", "rel_res_a", "rel_med_a", "corr_a", "slope_a",
    "bias_b", "rmse_b", "rel_bias_b", "rel_res_b", "rel_med_b", "corr_b", "slope_b",
)


def _residuals(data: dict[str, Any], suffix: str) -> metric_mod.EnergyResidualMetrics:
    def value(key: str) -> float | None:
        # Relative residuals divide by a per-event true energy that can be
        # femto-GeV small, so these aggregates legitimately come back as
        # infinity or NaN. Neither is a measurement, and neither is JSON.
        return metric_mod.finite(data.get(f"{key}_{suffix}"))

    return metric_mod.EnergyResidualMetrics(
        bias_gev=value("bias"),
        rmse_gev=value("rmse"),
        relative_bias=value("rel_bias"),
        relative_resolution=value("rel_res"),
        median_absolute_relative=value("rel_med"),
        correlation=value("corr"),
        slope=value("slope"),
    )


def compute(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    edges: Sequence[float] | None = None,
) -> PerformanceReport:
    """Compute global and per-slice model metrics for the active selection."""
    table = quote(naming.event_table(record.table_name))
    slices = build_slices(edges) if edges else build_slices()
    where = spec.where_sql()
    params = spec.params()

    row = con.execute(
        f"SELECT {_AGGREGATES} FROM {table} WHERE {where}", params
    ).fetchone()
    data = _row_to_dict(row, _NAMES)

    classification = metric_mod.classification(
        n_voxels=int(data["n_voxels"]),
        n_correct=int(data["n_correct"]),
        n_true_a=int(data["n_true_a"]),
        n_pred_a=int(data["n_pred_a"]),
        n_tp=int(data["n_tp"]),
        n_shared=int(data["n_shared"]),
    )
    regression = metric_mod.regression(
        n_voxels=int(data["n_voxels"]),
        sum_abs_err=float(data["sum_abs_err"]),
        sum_wabs_err=float(data["sum_wabs_err"]),
        sum_sq_err=float(data["sum_sq_err"]),
        e_dep=float(data["e_dep"]),
    )

    slice_rows = con.execute(
        f"""
        SELECT {case_sql(slices)} AS slice_index, {_AGGREGATES}
        FROM {table}
        WHERE {where}
        GROUP BY slice_index
        ORDER BY slice_index
        """,
        params,
    ).fetchall()

    by_slice: list[dict[str, Any]] = []
    lookup = {s.index: s for s in slices}
    for slice_row in slice_rows:
        index = int(slice_row[0])
        sdata = _row_to_dict(slice_row[1:], _NAMES)
        by_slice.append(
            {
                "slice": index,
                "label": lookup[index].label if index in lookup else str(index),
                "n_events": int(sdata["n_events"]),
                "classification": metric_mod.classification(
                    n_voxels=int(sdata["n_voxels"]),
                    n_correct=int(sdata["n_correct"]),
                    n_true_a=int(sdata["n_true_a"]),
                    n_pred_a=int(sdata["n_pred_a"]),
                    n_tp=int(sdata["n_tp"]),
                    n_shared=int(sdata["n_shared"]),
                ).as_dict(),
                "regression": metric_mod.regression(
                    n_voxels=int(sdata["n_voxels"]),
                    sum_abs_err=float(sdata["sum_abs_err"]),
                    sum_wabs_err=float(sdata["sum_wabs_err"]),
                    sum_sq_err=float(sdata["sum_sq_err"]),
                    e_dep=float(sdata["e_dep"]),
                ).as_dict(),
            }
        )

    return PerformanceReport(
        n_events=int(data["n_events"]),
        classification=classification,
        regression=regression,
        energy_a=_residuals(data, "a"),
        energy_b=_residuals(data, "b"),
        by_slice=by_slice,
        slices=list(slices),
    )
