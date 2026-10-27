"""The payloads of ``GET /api/xgboost``: E1, E3, E4 and E5 from the stored analysis.

Each view is computed once on the whole experiment - all rows for E1 and E4,
the validation split's 2,000-row sample for E3, the models themselves for E5 -
exactly as the notebook computes it, so the selection does not apply and every
payload says so (``filtered: false`` and :data:`SELECTION_NOTE`).

The marks follow CLAUDE.md section 2:

* **E1.** Five fold values are five observations, drawn as dots; their mean
  is the aggregate and carries a 95 % interval of the mean, never a naked
  point. The folds are not independent - any two share three quarters of
  their training rows - so the interval is Nadeau and Bengio's corrected
  resampled t: SE² = (1/k + n_test/n_train) s², with t at k − 1 = 4 degrees
  of freedom (:func:`mean_interval`). The plain sample SD across the folds is
  reported beside it as their spread, a different quantity.
* **E3.** The confusion matrix is counts. Every rate derived from it carries
  a Wilson score interval, which never leaves [0, 1] and does not collapse
  at 0 or 1, and names it. Balanced accuracy, the mean of the two class
  recalls with the class sizes fixed by the sample design, carries Newcombe's
  MOVER interval built from the two recalls' Wilson limits
  (:func:`balanced_interval`): a class classified perfectly keeps its own
  uncertainty, which a bootstrap of the rows loses. The notebook's weighted
  precision, recall and F1 are kept for parity, labelled as such.
* **E4.** A description of a surrogate, not an estimate: each node's n, its
  value and its within-node SD of the booster's predictions (an uncapped
  spread), and the fidelity of the whole tree and of each output. A node's φ
  value is sklearn's linear mean, kept for notebook parity; beside it the
  circular mean and mean resultant length R̄ of the booster's φ predictions
  on the node's rows, and φ is never coloured (no cyclic ramp is sanctioned).
* **E5.** One shipped model's normalised gain is the bar; the five refitted
  folds' values are dots beside it, and their mean's corrected resampled t
  interval a separate named envelope.

Numbers are rounded to six significant figures (``encode.numbers``) and every
sentence goes through :func:`~calosrv.text.typographic`.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..stats import gaussian, metrics
from ..errors import CapabilityError
from ..text import typographic
from . import store
from .analysis import (BINARY, CV_LABELS, HYPERPARAMETERS, KFOLD, LABEL_KEY, SPLIT_MARGIN,
                       SURROGATE, TEST_SIZE)
from .pairing import TASK_LABELS

VIEWS: tuple[str, ...] = ("cv", "binary", "surrogate", "importance")
TASKS: tuple[str, ...] = ("momentum", "angle")

SELECTION_NOTE = ("Computed once on the whole experiment, as the notebook does; the selection "
                  "does not apply.")

#: The label every XGBoost series and payload carries.
SERIES_LABEL = "XGBoost (20 % validation split)"

#: Units of the labels as the data hold them, and of the residual displays.
LABEL_UNITS: dict[str, str] = {"momentum": "GeV", "phi": "rad", "theta": "rad"}
MRAD_PER_RAD = 1000.0

#: The interval of a mean over the folds, and its method's name in the payload.
INTERVAL_LABEL = "95 % Nadeau–Bengio corrected resampled t interval of the mean (4 d.o.f.)"
METHOD_CORRECTED_T = "corrected_resampled_t"

#: Balanced accuracy's interval.
METHOD_MOVER = "mover"
MOVER_LABEL = "95 % Newcombe MOVER interval from per-class Wilson limits"


def _text(node: Any) -> Any:
    if isinstance(node, str):
        return typographic(node)
    if isinstance(node, dict):
        return {k: _text(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_text(v) for v in node]
    return node


# ------------------------------------------------------------- run block --


def require_runs(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, task: str,
                 field: str) -> dict[str, dict[str, Any]]:
    """The stored analysis of ``record``, or a refusal (422) when it is missing or lacks ``task``.

    The capability gate is open only while the analysis is done and current,
    but the tables can still vanish under it (a delete, a failed write): every
    route that reads them refuses the same way rather than failing.
    """
    runs = store.read_runs(con, record.table_name)
    if runs is None or task not in runs:
        reason = ("The stored XGBoost analysis is missing; Admin Settings › Model runs "
                  "re-analyses it.")
        raise CapabilityError(
            f"xgboost is not available for experiment {record.table_name!r}: {reason}",
            field=field, capability="xgboost", kind=record.kind, reason=reason,
            table_name=record.table_name)
    return runs


def split_block(row: dict[str, Any], task: str) -> dict[str, Any]:
    """The split check of one stored task: the 42 ratio, the 99 others, their maximum, the margin."""
    stored = (row.get("details") or {}).get("split") or {}
    ratio = row["split_ratio_42"]
    seeds = [int(x) for x in stored.get("seeds_others") or []]
    others = list(stored.get("ratio_others") or [])
    biggest = stored.get("max_others")
    margin = stored.get("margin", SPLIT_MARGIN[task])
    reproduced = bool(row["split_reproduced"])
    n = len(seeds)
    return {
        "reproduced": reproduced,
        "ratio_42": sig(ratio),
        "ratio_others": sig_list(others),
        "seeds_others": seeds,
        "n_others": n,
        "max_others": sig(biggest),
        "seed_of_max": stored.get("seed_of_max"),
        "median_others": sig(stored.get("median_others")),
        "margin": margin,
        "headroom": sig(stored.get("headroom")),
        "rule": (f"validation / training MSE of the shipped model at random_state 42 must exceed "
                 f"{margin:g} times the largest of the same ratio at {n} other random_state values "
                 f"(0 to 99 without 42): a model predicts the rows it was trained on better than "
                 "the rest. The per-row errors come from one prediction of every row; each seed "
                 "only re-indexes them."),
        "warning": None if reproduced else (
            f"Split not reproduced: validation / training MSE is {ratio:.3g} at random_state 42 "
            f"against at most {biggest:.3g} at the {n} other seeds (random_state "
            f"{stored.get('seed_of_max')}), short of the required {margin:g} times, so the stored "
            "validation rows may include rows the model was trained on."
            if biggest is not None else
            "Split not reproduced: the stored analysis carries no seed comparison."),
    }


def run_block(runs: dict[str, dict[str, Any]], task: str) -> dict[str, Any]:
    """Which model, which split, which analysis: the block every XGBoost payload carries."""
    row = runs[task]
    labels = [LABEL_KEY[label] for label in row["labels"]]
    split = split_block(row, task)
    versions = row.get("versions") or {}
    return _text({
        "species": row["species"],
        "seed": int(row["seed"]),
        "task": task,
        "labels": labels,
        "label_units": {label: LABEL_UNITS[label] for label in labels},
        "model_file": row["model_file"],
        "sha256": str(row["sha256"])[:12],
        "analysis_version": int(row["analysis_version"]),
        "split": split,
        "xgboost_version": versions.get("xgboost"),
        "n_rows": int(row["n_rows"]),
        "n_train": int(row["n_train"]),
        "n_holdout": int(row["n_val"]),
        "test_size": TEST_SIZE,
        "archive_increasing": row.get("archive_increasing"),
    })


def dataset_wide(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """The selection fields of a dataset-wide view: what was asked, and that it does not apply."""
    return {"filtered": False, "selection_note": SELECTION_NOTE, "filter": spec_dict}


# ------------------------------------------------------------- summaries --


def holdout_ratio(folds: Sequence[dict[str, Any]]) -> float:
    """n_test / n_train of the cross-validation: the mean held-out rows over the mean fitted rows."""
    n_val = [float(f["n_val"]) for f in folds]
    n_train = [float(f["n_train"]) for f in folds]
    return float(np.mean(n_val) / np.mean(n_train)) if folds and np.mean(n_train) > 0 else 0.0


def mean_interval(values: Sequence[float], bounds: tuple[float, float] | None = None,
                  test_train: float | None = None) -> dict[str, Any]:
    """Mean, SD (ddof 1), SE and the 95 % interval of the mean, clipped to ``bounds``.

    ``test_train`` (n_test / n_train) makes it Nadeau and Bengio's corrected
    resampled t (2003): the k values come from refits whose training sets
    overlap, so their variance understates the variance of their mean, and
    SE² = (1/k + n_test/n_train) s² replaces s² / k, with t at k − 1 degrees
    of freedom. Without it, the plain Student-t interval. ``sd`` is the plain
    sample SD either way: the spread of the values, which the dots show.
    """
    v = np.asarray([x for x in values if x is not None and math.isfinite(x)], dtype=np.float64)
    n = int(v.size)
    factor = None if test_train is None else (1.0 / n if n else 0.0) + test_train
    if n == 0:
        return {"mean": None, "sd": None, "se": None, "t95": [None, None], "n": 0, "dof": None,
                "t": None, "clipped": False, "variance_factor": None}
    mean = float(v.mean())
    if n < 2:
        return {"mean": sig(mean), "sd": None, "se": None, "t95": [None, None], "n": n, "dof": 0,
                "t": None, "clipped": False, "variance_factor": None}
    sd = float(v.std(ddof=1))
    se = sd * math.sqrt(factor) if factor is not None else sd / math.sqrt(n)
    t = gaussian.t_quantile_975(n - 1)
    lo, hi = mean - t * se, mean + t * se
    clipped = False
    if bounds is not None:
        clo, chi = max(lo, bounds[0]), min(hi, bounds[1])
        clipped = (clo, chi) != (lo, hi)
        lo, hi = clo, chi
    return {"mean": sig(mean), "sd": sig(sd), "se": sig(se), "t95": [sig(lo), sig(hi)], "n": n,
            "dof": n - 1, "t": round(t, 3), "clipped": clipped,
            "variance_factor": sig(factor if factor is not None else 1.0 / n)}


# -------------------------------------------------------------------- E1 --

_METRICS: tuple[tuple[str, str, str], ...] = (
    ("mae", "MAE", "mean |pred − true|"),
    ("mse", "MSE", "mean (pred − true)²"),
    ("rmse", "RMSE", "√MSE"),
    ("r2", "R²", "1 − Σ(pred − true)² / Σ(true − mean true)²"),
)
_BOUNDS: dict[str, tuple[float, float]] = {
    "mae": (0.0, math.inf), "mse": (0.0, math.inf), "rmse": (0.0, math.inf), "r2": (-math.inf, 1.0),
}


def _metric_list(unit: str, keep: Sequence[str] = ("mae", "mse", "rmse", "r2")) -> list[dict[str, Any]]:
    units = {"mae": unit, "mse": f"{unit}²" if unit else "", "rmse": unit, "r2": ""}
    return [{"id": m, "label": label, "unit": units[m], "definition": definition}
            for m, label, definition in _METRICS if m in keep]


def cv_view(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
            runs: dict[str, dict[str, Any]], task: str) -> dict[str, Any]:
    """E1: the five folds of ``train_and_evaluate`` and the mean of each metric."""
    rows = store.read_folds(con, record.table_name, task)
    folds: dict[int, dict[str, Any]] = {}
    for fold, n_train, n_val, metric, label, value in rows:
        entry = folds.setdefault(int(fold), {"fold": int(fold), "n_train": int(n_train),
                                             "n_val": int(n_val), "values": {}})
        entry["values"][(metric, label)] = value
    parity = "momentum" if task == "momentum" else "parity"
    unit = "GeV" if task == "momentum" else "rad"
    metric_ids = [m for m, *_ in _METRICS]
    ordered = [folds[k] for k in sorted(folds)]
    out_folds: list[dict[str, Any]] = []
    for f in ordered:
        entry = {"fold": f["fold"], "n_train": f["n_train"], "n_val": f["n_val"],
                 "metrics": {m: sig(f["values"].get((m, parity))) for m in metric_ids},
                 "per_label": None}
        if task == "angle":
            entry["per_label"] = {
                "theta": {m: sig(_mrad(m, f["values"].get((m, "theta")))) for m in ("mae", "rmse", "r2")},
                "phi": {m: sig(_mrad(m, f["values"].get((m, "phi")))) for m in ("mae", "rmse")},
            }
        out_folds.append(entry)
    ratio = holdout_ratio(ordered)
    summary = {m: mean_interval([f["values"].get((m, parity)) for f in ordered], _BOUNDS[m], ratio)
               for m in metric_ids}
    per_label = None
    if task == "angle":
        per_label = {
            "theta": {
                "unit": "mrad", "metrics": _metric_list("mrad", ("mae", "rmse", "r2")),
                "summary": {m: mean_interval([_mrad(m, f["values"].get((m, "theta"))) for f in ordered],
                                             _BOUNDS[m], ratio) for m in ("mae", "rmse", "r2")},
                "residual": "θ_pred − θ_true",
            },
            "phi": {
                "unit": "mrad", "metrics": _metric_list("mrad", ("mae", "rmse")),
                "summary": {m: mean_interval([_mrad(m, f["values"].get((m, "phi"))) for f in ordered],
                                             _BOUNDS[m], ratio) for m in ("mae", "rmse")},
                "residual": "φ_pred − φ_true wrapped to (−π, π]",
            },
        }
    notes = {
        "folds": ("Each fold refits the notebook's regressor (objective reg:squarederror, 100 "
                  "trees, learning rate 0.1, random_state 42) on four fifths of the rows of "
                  "KFold(5, shuffle=True, random_state=42) and scores the fifth. A fold value is "
                  "one observation and is drawn as a dot."),
        "interval": ("The mean of the five folds carries the 95 % Nadeau–Bengio corrected "
                     "resampled t interval of the mean (4 d.o.f., t = 2.776): any two folds share "
                     "three quarters of their training rows, so their values are not independent "
                     "and s²/k would understate the variance of their mean; the correction uses "
                     f"(1/k + n_test/n_train) s² = {1 / KFOLD['n_splits'] + ratio:.3g} s² instead "
                     "of s²/5. It is the uncertainty of the aggregate. The SD beside it is the "
                     "plain spread of the folds, a different quantity, and is not a whisker."),
        "refit": ("The refits are what the notebook computed: refitting on the reproduced 80 % "
                  "split recreates the shipped model exactly, and XGBoost's result does not "
                  "depend on the thread count."),
    }
    if task == "angle":
        notes["parity"] = ("notebook parity: the mean over φ and θ, φ unwrapped. sklearn's "
                           "uniform average of the two outputs' metrics on the raw labels, in rad, "
                           "as the notebook prints them; an R² or a squared error of an azimuth "
                           "that is not wrapped counts a residual of 2π − ε as a large error.")
        notes["per_label"] = ("Per label, in mrad: θ's MAE, RMSE and R²; φ's MAE and RMSE of the "
                              "residual wrapped to (−π, π], and no R², which is undefined for an "
                              "azimuth.")
        notes["order"] = ("This notebook cell fits the angle task on [incoming_theta, "
                          "incoming_phi], the order its prepare_data builds; the shipped model "
                          "predicts [incoming_phi, incoming_theta].")
    return _text({
        "view": "cv",
        "task": task,
        "labels": [LABEL_KEY[label] for label in CV_LABELS[task]],
        "n_rows": int(runs[task]["n_rows"]),
        "kfold": dict(KFOLD),
        "hyperparameters": dict(HYPERPARAMETERS),
        "metrics": _metric_list(unit),
        "parity_label": "momentum" if task == "momentum" else (
            "notebook parity: the mean over φ and θ, φ unwrapped"),
        "folds": out_folds,
        "summary": summary,
        "per_label": per_label,
        "interval": _interval_block(ratio),
        "notes": notes,
    })


def _interval_block(ratio: float) -> dict[str, Any]:
    """The fold-mean interval's description: Nadeau-Bengio's corrected resampled t."""
    k = KFOLD["n_splits"]
    return {"label": INTERVAL_LABEL, "level": 0.95, "dof": k - 1,
            "t": round(gaussian.t_quantile_975(k - 1), 3), "method": METHOD_CORRECTED_T,
            "test_train": sig(ratio), "variance_factor": sig(1.0 / k + ratio),
            "reference": ("Nadeau and Bengio (2003), Inference for the generalization error, "
                          "Machine Learning 52, 239–281")}


def _mrad(metric: str, value: float | None) -> float | None:
    """A per-label angle metric in mrad (R² is dimensionless)."""
    if value is None or metric == "r2":
        return value
    return float(value) * MRAD_PER_RAD


# -------------------------------------------------------------------- E3 --


def _rate(identifier: str, label: str, k: int, n: int, definition: str) -> dict[str, Any]:
    estimate = metrics.proportion_estimate(k, n)
    interval = estimate.interval
    return {
        "id": identifier, "label": label, "definition": definition, "k": int(k), "n": int(n),
        "value": sig(estimate.value),
        "interval": None if interval is None else {
            "lo": sig(interval.lo), "hi": sig(interval.hi), "level": interval.level,
            "method": interval.method, "label": interval.label},
        "note": "" if n else "Undefined: no rows in its denominator.",
    }


def balanced_interval(tn: int, fp: int, fn: int, tp: int) -> dict[str, Any]:
    """Balanced accuracy and Newcombe's MOVER 95 % interval from the class recalls' Wilson limits.

    BA = (p1 + p0) / 2 with p1 = TP / (TP + FN) and p0 = TN / (TN + FP), the
    class sizes fixed by the sample design (1,980 and 20). The method of
    variance estimates recovery (Zou and Donner 2008; Newcombe 1998) combines
    each recall's own Wilson limits (l, u):

        L = BA − ½ √((p1 − l1)² + (p0 − l0)²)
        U = BA + ½ √((u1 − p1)² + (u0 − p0)²)

    clipped to [0, 1]. A class classified perfectly (p1 = 1) still contributes
    its Wilson half-width 1 − l1, which a bootstrap of the rows or a Wald
    interval loses: both collapse that class's uncertainty to zero.
    """
    n_1, n_0 = tp + fn, tn + fp
    w1, w0 = metrics.wilson_interval(tp, n_1), metrics.wilson_interval(tn, n_0)
    if w1 is None or w0 is None:
        return {"value": None, "lo": None, "hi": None}
    p1, p0 = tp / n_1, tn / n_0
    value = 0.5 * (p1 + p0)
    lo = value - 0.5 * math.hypot(p1 - w1.lo, p0 - w0.lo)
    hi = value + 0.5 * math.hypot(w1.hi - p1, w0.hi - p0)
    return {"value": value, "lo": max(0.0, lo), "hi": min(1.0, hi)}


def binary_view(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """E3: ``evaluate_binary_performance``'s sample, its confusion matrix and its rates."""
    rows = store.read_binary(con, record.table_name)
    details = (runs["momentum"].get("details") or {}).get("binary") or {}
    y_true = np.asarray(rows["y_true"], dtype=np.int64)
    y_pred = np.asarray(rows["y_pred"], dtype=np.int64)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    n = tp + tn + fp + fn
    n_1, n_0 = tp + fn, tn + fp
    threshold = BINARY["threshold"]
    rates = [
        _rate("accuracy", "Accuracy", tp + tn, n, "(TP + TN) / N"),
        _rate("recall_1", f"Recall, class 1 (p > {threshold:g} GeV)", tp, n_1, "TP / (TP + FN)"),
        _rate("recall_0", f"Recall, class 0 (p < {threshold:g} GeV)", tn, n_0, "TN / (TN + FP)"),
        _rate("precision_1", "Precision, class 1", tp, tp + fp, "TP / (TP + FP)"),
        _rate("precision_0", "Precision, class 0", tn, tn + fn, "TN / (TN + FN)"),
    ]
    balanced = balanced_interval(tn, fp, fn, tp)
    rates.append({
        "id": "balanced_accuracy", "label": "Balanced accuracy",
        "definition": "(recall class 1 + recall class 0) / 2", "k": None, "n": n,
        "value": sig(balanced["value"]),
        "interval": None if balanced["lo"] is None else {
            "lo": sig(balanced["lo"]), "hi": sig(balanced["hi"]), "level": 0.95,
            "method": METHOD_MOVER, "label": MOVER_LABEL},
        "note": "" if balanced["value"] is not None else "Undefined: one class is absent from the sample.",
    })
    minority = min(n_0, n_1)
    parity = details.get("metrics") or {}
    pool_rule = (f"p > {threshold:g} GeV (fewer than {BINARY['min_class_1']} validation rows lie "
                 f"above {BINARY['class_1_above']:g} GeV)" if details.get("fallback")
                 else f"p > {BINARY['class_1_above']:g} GeV")
    return _text({
        "view": "binary",
        "task": "momentum",
        "threshold_gev": threshold,
        "design": {
            "n_target": BINARY["total"],
            "n_0_target": int(BINARY["total"] * BINARY["fraction_0"]),
            "n_1_target": int(BINARY["total"] * BINARY["fraction_1"]),
            "ratio": "99 : 1",
            "class_0_rule": f"p < {BINARY['class_0_below']:g} GeV",
            "class_1_rule": pool_rule,
            "fallback": bool(details.get("fallback", False)),
            "pool_0": details.get("pool_0"),
            "pool_1": details.get("pool_1"),
            "drawn_from": "the 20 % validation split",
            "sampler": ("pandas pool.sample(min(n, len(pool)), random_state=42) per class, then "
                        "concat and sample(frac=1, random_state=42), as the notebook"),
            "prediction": f"the shipped regressor's momentum, thresholded at {threshold:g} GeV",
        },
        "counts": {"class_0": n_0, "class_1": n_1, "n": n},
        "confusion": {
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "matrix": [[tn, fp], [fn, tp]],
            "layout": "rows: true class 0, 1; columns: predicted class 0, 1",
        },
        "rates": rates,
        "parity": {
            "label": ("The notebook's metrics, for parity: accuracy, balanced accuracy, and "
                      "precision, recall and F1 weighted by class support (zero_division = 0). "
                      "Point values from sklearn, without intervals."),
            "accuracy": sig(parity.get("accuracy")),
            "balanced_accuracy": sig(parity.get("balanced_accuracy")),
            "precision_weighted": sig(parity.get("precision_weighted")),
            "recall_weighted": sig(parity.get("recall_weighted")),
            "f1_weighted": sig(parity.get("f1_weighted")),
            "class_0_count": details.get("n_0", n_0),
            "class_1_count": details.get("n_1", n_1),
        },
        "minority": {
            "n": minority,
            "class": 0 if n_0 <= n_1 else 1,
            "note": (
                f"Class {0 if n_0 <= n_1 else 1} is absent from the sample (its validation pool "
                "is empty): its recall, the other class's precision and the balanced accuracy are "
                "undefined." if minority == 0 else
                f"The minority class has {minority:,} row{'s' if minority != 1 else ''}: every "
                "rate whose denominator is that class rests on that many events, and its "
                "Wilson interval is correspondingly wide."),
        },
        "notes": {
            "intervals": ("Each rate carries a 95 % Wilson score interval of a proportion. The "
                          "balanced accuracy, the mean of the two class recalls with the class "
                          "sizes fixed by the sample design, carries Newcombe's MOVER interval "
                          "built from the two recalls' Wilson limits, so a class classified "
                          "perfectly keeps the uncertainty of its few rows; a bootstrap of the "
                          "rows would collapse it to zero."),
            "counts": "The confusion matrix is counts, which carry no interval.",
            "weighted": ("Support-weighted precision, recall and F1 are dominated by the majority "
                         "class at 99 : 1; they are the notebook's numbers, kept for parity, and "
                         "the per-class rates are what the card draws."),
        },
    })


# -------------------------------------------------------------------- E4 --


def surrogate_view(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                   runs: dict[str, dict[str, Any]], task: str) -> dict[str, Any]:
    """E4: the depth-3 surrogate tree, node by node, and its fidelity to the booster."""
    rows = store.read_tree(con, record.table_name, task)
    labels = [LABEL_KEY[label] for label in TASK_LABELS[task]]
    row = runs[task]
    stored_circular = (row.get("details") or {}).get("surrogate_circular") or {}
    nodes: dict[int, dict[str, Any]] = {}
    for node_id, depth, left, right, feature, threshold, n, impurity, label, value, variance in rows:
        node = nodes.setdefault(int(node_id), {
            "id": int(node_id), "depth": int(depth), "left": int(left), "right": int(right),
            "leaf": int(left) < 0, "feature": feature,
            "frame": ddl.feature_frame(feature) if feature else None,
            # A variance: sklearn's running sums can leave −1e−16 on a pure node.
            "threshold": sig(threshold), "n": int(n), "impurity": sig(max(0.0, impurity)),
            "values": {}, "sd": {},
            "circular": {k: {"mean": sig(v.get("mean")), "resultant": sig(v.get("resultant"))}
                         for k, v in (stored_circular.get(str(int(node_id))) or {}).items()},
        })
        node["values"][label] = sig(value)
        node["sd"][label] = sig(math.sqrt(variance)) if variance is not None and variance >= 0 else None
    ordered = [nodes[k] for k in sorted(nodes)]
    for node in ordered:
        if node["leaf"]:
            node["left"] = node["right"] = None
    outputs = ((row.get("details") or {}).get("surrogate_outputs") or {})
    unit = LABEL_UNITS["momentum"] if task == "momentum" else "rad"
    coloured = [label for label in labels if label not in CIRCULAR_LABELS]
    domain = {label: [sig(min(n["values"][label] for n in ordered)),
                      sig(max(n["values"][label] for n in ordered))] for label in coloured} if ordered else {}
    label_info = [{"name": label, "coloured": label in coloured,
                   "reason": (COLOUR_REASON_CIRCULAR if label in CIRCULAR_LABELS else
                              "its node value, on the sequential ramp (Viridis by default)")}
                  for label in labels]
    fidelity_outputs = {k: {"r2": sig(v.get("r2")), "mae": sig(v.get("mae"))}
                        for k, v in outputs.items()}
    return _text({
        "view": "surrogate",
        "task": task,
        "labels": labels,
        "units": {label: LABEL_UNITS[label] for label in labels},
        "nodes": ordered,
        "n_nodes": len(ordered),
        "rule": "left: feature ≤ threshold; right: feature > threshold",
        "fidelity": {
            "r2": sig(row["surrogate_r2"]), "mae": sig(row["surrogate_mae"]), "unit": unit,
            "outputs": fidelity_outputs,
            "against": ("the shipped booster's own predictions on every row, in-sample, as the "
                        "notebook measures it"),
            "statement": _fidelity_statement(row, fidelity_outputs, labels),
        },
        "tree": {**SURROGATE, "criterion": "squared_error", "n_rows": int(row["n_rows"]),
                 "target": "the shipped booster's predictions"},
        "color_domain": domain,
        "color_by": {info["name"]: info["coloured"] for info in label_info},
        "label_info": label_info,
        "notes": {
            "description": ("A description of the booster, not an estimate: each node shows its "
                            "number of rows, the mean of the booster's predictions over them and "
                            "their SD, the spread within the node (no whisker)."),
            "impurity": ("impurity is sklearn's: the variance of the booster's predictions in the "
                         "node, averaged over the outputs for the angle task; sd is each output's "
                         "own within-node SD."),
            "fidelity": ("Fidelity is R² and MAE of the tree against the booster, on the rows it "
                         "was fitted to; it says how much of the booster the three levels of "
                         "rules describe. Each output's own fidelity is stated: their average "
                         "can hide an output the tree does not describe at all."),
            **({"circular": CIRCULAR_NOTE} if any(label in CIRCULAR_LABELS for label in labels)
               else {}),
        },
    })


#: Outputs that are azimuths: never coloured on a sequential ramp, never averaged as a line.
CIRCULAR_LABELS: frozenset[str] = frozenset({"phi"})

COLOUR_REASON_CIRCULAR = (
    "not coloured: φ is an azimuth, and a sequential ramp would put −2.7 and +2.7 rad, 0.8 rad "
    "apart on the circle, at its two ends; CLAUDE.md sanctions no cyclic ramp")

CIRCULAR_NOTE = (
    "A node's φ value is sklearn's linear mean of the booster's φ predictions on its rows, kept "
    "for notebook parity; it is not a direction. Beside it, circular.phi gives their circular "
    "mean and mean resultant length R̄ in [0, 1]: a low R̄ means the predictions point every "
    "way, the node has no direction, and neither the linear nor the circular mean describes it. "
    "The ± SD of φ is the linear spread, likewise kept for parity.")


def _fidelity_statement(row: dict[str, Any], outputs: dict[str, dict[str, Any]],
                        labels: Sequence[str]) -> str:
    """The fidelity in one sentence, per output whenever there is more than one."""
    if len(labels) == 1 or not outputs:
        return f"R² {row['surrogate_r2']:.3g} against the booster's predictions"
    per = "; ".join(f"{label} R² {outputs[label]['r2']:.3g}" for label in labels
                    if label in outputs and outputs[label].get("r2") is not None)
    return (f"{per} (sklearn's average over the outputs {row['surrogate_r2']:.3g}, which no "
            "single output has)")


# -------------------------------------------------------------------- E5 --


def importance_view(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                    runs: dict[str, dict[str, Any]], task: str) -> dict[str, Any]:
    """E5: the shipped model's gain importances, sorted, with the five folds' beside them."""
    rows = store.read_importance(con, record.table_name, task)
    shipped: dict[str, tuple] = {}
    folds: dict[str, dict[int, float]] = {}
    for source, fold, feature, norm, gain, weight, cover in rows:
        if source == "shipped":
            shipped[feature] = (norm, gain, weight, cover)
        else:
            folds.setdefault(feature, {})[int(fold)] = norm
    order = sorted(shipped, key=lambda f: (-shipped[f][0], f))
    ratio = holdout_ratio(_fold_sizes(con, record, task))
    features = []
    for rank, name in enumerate(order, start=1):
        norm, gain, weight, cover = shipped[name]
        values = [folds.get(name, {}).get(k) for k in range(KFOLD["n_splits"])]
        summary = mean_interval([v for v in values if v is not None], (0.0, 1.0), ratio)
        features.append({
            "name": name, "rank": rank, "frame": ddl.feature_frame(name),
            "shipped": sig(norm),
            "raw": {"gain": sig(gain), "weight": sig(weight), "cover": sig(cover)},
            "folds": sig_list(values),
            "fold_mean": summary["mean"], "fold_sd": summary["sd"], "fold_t95": summary["t95"],
            "clipped": bool(summary["clipped"]),
        })
    frames = {f["frame"] for f in features}
    return _text({
        "view": "importance",
        "task": task,
        "features": features,
        "n_features": len(features),
        "n_used": sum(1 for f in features if (f["shipped"] or 0) > 0),
        "measure": {
            "shipped": ("the shipped booster's feature_importances_: each feature's average "
                        "split gain, divided by the sum over the features"),
            "raw": ("get_score: gain the average gain of the feature's splits, weight the number "
                    "of splits, cover the average number of rows they cover"),
            "folds": "the same normalised gain of each of the five cross-validation refits",
        },
        "frames": {
            "absolute": "detector coordinates", "trans": "per-shower translated",
            "local": "local (shower-fixed)", "none": "no frame (a count)",
        },
        "frames_present": sorted(frames),
        "interval": {**_interval_block(ratio),
                     "clip": ("clipped to [0, 1], the range of a share; a feature's clipped says "
                              "whether its interval was")},
        "n_clipped": sum(1 for f in features if f["clipped"]),
        "notes": {
            "bar": ("The bar is one model, the shipped one; the dots are the five refitted folds "
                    "and the envelope their mean's corrected resampled t interval (the refits "
                    "share three quarters of their rows), so the bar is never read as the "
                    "folds' mean."),
            "gain": ("A gain importance says how much a feature's splits reduced the training "
                     "loss, not how much the prediction depends on it; correlated features share "
                     "or swap their gain between refits."),
        },
    })


def _fold_sizes(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                task: str) -> list[dict[str, Any]]:
    """Each fold's n_train and n_val, as E1 stored them (E5's interval needs the ratio)."""
    seen: dict[int, dict[str, Any]] = {}
    for fold, n_train, n_val, *_ in store.read_folds(con, record.table_name, task):
        seen.setdefault(int(fold), {"n_train": n_train, "n_val": n_val})
    return [seen[k] for k in sorted(seen)]
