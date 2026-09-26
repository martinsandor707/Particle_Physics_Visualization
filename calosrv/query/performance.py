"""Model-performance metrics for the sidebar cards, per network.

Nine networks answer three questions in three input frames: segmentation (which
shower each hit's energy belongs to), energy (each shower's incident momentum)
and angle (each shower's polar angle theta). ``model`` picks the question and
``coord_system`` the frame the network was trained on; the canonical view uses
the absolute-frame networks.

Every card is a statistic of the selected events, so it carries the
uncertainty of that statistic (``stats/metrics.py``):

* **Segmentation** metrics are ratios of sums over hits - accuracy, the
  energy-weighted and plain MAE, the MSE, F1 - rolled up exactly from the
  event table's additive sufficient statistics. The hits of one event share a
  shower and are not independent draws, so the standard error treats events
  as clusters (linearised ratio, Student-t interval) from five sums per
  metric, still one pass over twenty thousand rows.
* **Energy and angle** metrics are per-shower residuals - (pred - true) / true
  for energy, (pred - true) in mrad for theta - summarised by
  ``gaussian.fit_gaussian`` (ddof = 1 width with its chi-squared interval,
  Student-t bias) and a Fisher-z correlation. Shower A and shower B are
  reported separately, each with its own N: an event without shower-A hits
  has no A prediction, and it is dropped from A, never zero-filled.

The per-slice breakdown repeats the primary cards per separation slice,
because the claim of interest is how a network degrades as the two showers
close in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..stats import metrics as metric_mod
from ..stats.metrics import Card
from ..stats.slices import Slice, build_slices, case_sql
from .filters import FilterSpec

MRAD_PER_RAD = 1000.0

#: (card id, numerator, denominator) of each segmentation ratio, per frame code.
def _ratios(f: str) -> tuple[tuple[str, str, str], ...]:
    return (
        ("accuracy", f"n_correct_{f}", "n_hits"),
        ("wmae", f"sum_wabs_err_{f}", "e_dep"),
        ("mae", f"sum_abs_err_{f}", "n_hits"),
        ("mse", f"sum_sq_err_{f}", "n_hits"),
        ("f1", f"2 * n_tp_{f}", f"n_pred_a_{f} + n_true_a_{f}"),
        ("split", "n_split_cells", "n_cells"),
    )


def _seg_aggregates(f: str) -> str:
    parts = [
        "count(*) AS n_events",
        "coalesce(sum(n_hits), 0) AS n_voxels",
        "coalesce(sum(e_dep), 0.0) AS e_dep",
        f"coalesce(sum(n_correct_{f}), 0) AS n_correct",
        f"coalesce(sum(n_true_a_{f}), 0) AS n_true_a",
        f"coalesce(sum(n_pred_a_{f}), 0) AS n_pred_a",
        f"coalesce(sum(n_tp_{f}), 0) AS n_tp",
        f"coalesce(sum(sum_abs_err_{f}), 0.0) AS sum_abs_err",
        f"coalesce(sum(sum_wabs_err_{f}), 0.0) AS sum_wabs_err",
        f"coalesce(sum(sum_sq_err_{f}), 0.0) AS sum_sq_err",
    ]
    parts += [metric_mod.ratio_sums_sql(num, den, alias) for alias, num, den in _ratios(f)]
    return ",\n        ".join(parts)


@dataclass
class PerformanceReport:
    n_events: int
    model: str
    coord_system: str
    cards: list[Card]
    by_slice: list[dict[str, Any]]
    slices: list[Slice]
    classification: metric_mod.ClassificationMetrics | None = None
    regression: metric_mod.RegressionMetrics | None = None
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def network(self) -> dict[str, str]:
        return {"model": self.model, "frame": ddl.NETWORK_FRAME[self.coord_system]}

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "n_events": self.n_events,
            "network": self.network,
            "cards": [c.as_dict() for c in self.cards],
            "by_slice": self.by_slice,
            "slices": [s.as_dict() for s in self.slices],
            "notes": self.notes,
        }
        if self.classification is not None:
            out["classification"] = self.classification.as_dict()
        if self.regression is not None:
            out["regression"] = self.regression.as_dict()
        return out


# ---------------------------------------------------------- segmentation --


def _seg_cards(row: dict[str, Any], primary_only: bool = False) -> list[Card]:
    n = int(row["n_events"])
    unit_interval = (0.0, 1.0)
    acc = metric_mod.ratio_from_row(row, "accuracy", n, unit_interval)
    wmae = metric_mod.ratio_from_row(row, "wmae", n, unit_interval)
    cards = [
        Card("accuracy", "Voxel accuracy", "assignment at fA ≥ 0.5 on both sides", "fraction",
             acc, primary=True),
        Card("wmae", "Energy-weighted MAE", "fraction of energy mis-assigned", "fraction",
             wmae, primary=True),
    ]
    if primary_only:
        return cards
    mse = metric_mod.ratio_from_row(row, "mse", n, (0.0, float("inf")))
    cards += [
        Card("mae", "Voxel MAE", "unweighted; dominated by the lowest-energy hits", "",
             metric_mod.ratio_from_row(row, "mae", n, unit_interval)),
        Card("rmse", "Voxel RMSE", "on the fraction itself", "", metric_mod.sqrt_estimate(mse)),
        Card("f1_a", "F1 (shower A)", "2·TP / (predicted A + true A)", "",
             metric_mod.ratio_from_row(row, "f1", n, unit_interval)),
        Card("split_cells", "Split cells", "cells holding energy of both showers (two rows each)",
             "fraction", metric_mod.ratio_from_row(row, "split", n, unit_interval),
             notes=["A property of the data, not of the network: every such cell is two rows, "
                    "so the unweighted per-hit counts see it twice."]),
    ]
    return cards


def _segmentation(con, record, spec, f, slices):
    table = quote(naming.event_table(record.table_name))
    where, params = spec.where_sql(), spec.params()
    cursor = con.execute(f"SELECT {_seg_aggregates(f)} FROM {table} WHERE {where}", params)
    names = [d[0] for d in cursor.description]
    row = dict(zip(names, cursor.fetchone()))

    def rollups(data):
        classification = metric_mod.classification(
            n_voxels=int(data["n_voxels"]), n_correct=int(data["n_correct"]),
            n_true_a=int(data["n_true_a"]), n_pred_a=int(data["n_pred_a"]), n_tp=int(data["n_tp"]),
        )
        regression = metric_mod.regression(
            n_voxels=int(data["n_voxels"]), sum_abs_err=float(data["sum_abs_err"]),
            sum_wabs_err=float(data["sum_wabs_err"]), sum_sq_err=float(data["sum_sq_err"]),
            e_dep=float(data["e_dep"]),
        )
        return classification, regression

    cursor = con.execute(
        f"""SELECT {case_sql(slices)} AS slice_index, {_seg_aggregates(f)}
            FROM {table} WHERE {where} GROUP BY slice_index ORDER BY slice_index""",
        params,
    )
    names = [d[0] for d in cursor.description]
    lookup = {s.index: s for s in slices}
    by_slice = []
    for values in cursor.fetchall():
        data = dict(zip(names, values))
        index = int(data["slice_index"])
        if index not in lookup:
            continue  # no defined separation: counted in the totals, in no D slice
        classification, regression = rollups(data)
        by_slice.append({
            "slice": index,
            "label": lookup[index].label if index in lookup else str(index),
            "n_events": int(data["n_events"]),
            "classification": classification.as_dict(),
            "regression": regression.as_dict(),
            "cards": [c.as_dict() for c in _seg_cards(data, primary_only=True)],
        })
    classification, regression = rollups(row)
    return int(row["n_events"]), _seg_cards(row), by_slice, classification, regression


# ------------------------------------------------------ energy and angle --


def _residual_cards(kind: str, arrays: dict[str, np.ndarray], mask: np.ndarray | None,
                    primary_only: bool = False) -> list[Card]:
    cards: list[Card] = []
    for shower in ("a", "b"):
        pred = np.asarray(arrays[f"pred_{shower}"], dtype=np.float64)
        true = np.asarray(arrays[f"true_{shower}"], dtype=np.float64)
        if mask is not None:
            pred, true = pred[mask], true[mask]
        keep = np.isfinite(pred) & np.isfinite(true)
        pred, true = pred[keep], true[keep]
        tag = shower.upper()
        if kind == "energy":
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = (pred - true) / true
            summary = metric_mod.residual_summary(rel)
            cards.append(Card(f"sigma_rel_{shower}", f"Energy resolution {tag}",
                              "σ of (pred − true) / true, ddof = 1", "fraction",
                              summary.sigma, primary=True, shower=shower))
            if primary_only:
                continue
            cards.append(Card(f"bias_rel_{shower}", f"Relative bias {tag}",
                              "mean of (pred − true) / true", "fraction", summary.bias, shower=shower))
            absolute = metric_mod.residual_summary(pred - true)
            cards.append(Card(f"rmse_{shower}", f"RMSE {tag}", "√mean (pred − true)²", "GeV",
                              absolute.rmse, shower=shower))
            cards.append(Card(f"corr_{shower}", f"Correlation {tag}", "Pearson r, pred vs. true", "",
                              metric_mod.correlation(pred, true), shower=shower))
        else:
            summary = metric_mod.residual_summary((pred - true) * MRAD_PER_RAD)
            cards.append(Card(f"sigma_theta_{shower}", f"θ resolution {tag}",
                              "σ of θ_pred − θ_true, ddof = 1", "mrad",
                              summary.sigma, primary=True, shower=shower))
            if primary_only:
                continue
            cards.append(Card(f"bias_theta_{shower}", f"θ bias {tag}", "mean of θ_pred − θ_true",
                              "mrad", summary.bias, shower=shower))
            cards.append(Card(f"rmse_theta_{shower}", f"θ RMSE {tag}", "√mean (θ_pred − θ_true)²",
                              "mrad", summary.rmse, shower=shower))
    return cards


def _residuals(con, record, spec, model, f, slices):
    table = quote(naming.event_table(record.table_name))
    stem = "en" if model == "energy" else "th"
    arrays = con.execute(
        f"""SELECT {case_sql(slices)} AS slice_index,
                   CAST({stem}_pred_a_{f} AS DOUBLE) AS pred_a, CAST({stem}_true_a AS DOUBLE) AS true_a,
                   CAST({stem}_pred_b_{f} AS DOUBLE) AS pred_b, CAST({stem}_true_b AS DOUBLE) AS true_b
            FROM {table} WHERE {spec.where_sql()}""",
        spec.params(),
    ).fetchnumpy()
    arrays = {k: np.ma.filled(np.ma.asarray(v).astype(np.float64), np.nan) for k, v in arrays.items()}
    n_events = int(arrays["slice_index"].size)
    cards = _residual_cards(model, arrays, None)
    lookup = {s.index: s for s in slices}
    by_slice = []
    index = arrays["slice_index"]
    for s in slices:
        mask = index == s.index
        if not mask.any():
            continue
        by_slice.append({
            "slice": s.index, "label": lookup[s.index].label, "n_events": int(mask.sum()),
            "cards": [c.as_dict() for c in _residual_cards(model, arrays, mask, primary_only=True)],
        })
    return n_events, cards, by_slice


def compute(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    model: str = "segmentation",
    coord_system: str = "lab",
    edges: Sequence[float] | None = None,
) -> PerformanceReport:
    """The cards and the per-slice breakdown for one network over the selection."""
    f = ddl.frame_code(coord_system)
    slices = build_slices(edges) if edges else build_slices()
    notes: dict[str, str] = {
        "uncertainty": (
            "Each card quotes its standard error and a 95% interval of the statistic over "
            "the selected events; below N = "
            f"{metric_mod.SHOW_CI_BELOW_N} the interval is shown beside the SE, with the "
            "card's small-sample caveats."
        ),
    }
    if model == "segmentation":
        n_events, cards, by_slice, classification, regression = _segmentation(
            con, record, spec, f, slices)
        notes.update({
            "mae": (
                "Unweighted voxel MAE counts every hit equally. Per-hit energies span "
                "fifteen decades, so it is dominated by the lowest-energy hits, where the "
                "assignment is physically irrelevant."
            ),
            "mae_energy_weighted": (
                "Energy-weighted MAE is the fraction of deposited energy the network "
                "mis-assigns between the two showers: the headline figure."
            ),
            "clusters": (
                "The hits of one event share a shower, so the uncertainty treats events as "
                "clusters (linearised ratio of sums, Student-t)."
            ),
        })
        return PerformanceReport(n_events, model, coord_system, cards, by_slice, list(slices),
                                 classification, regression, notes)
    n_events, cards, by_slice = _residuals(con, record, spec, model, f, slices)
    notes["showers"] = (
        "Showers A and B are reported separately, each with its own N; an event without "
        "shower-A hits has no A prediction and is dropped from A, never zero-filled."
    )
    return PerformanceReport(n_events, model, coord_system, cards, by_slice, list(slices), notes=notes)
