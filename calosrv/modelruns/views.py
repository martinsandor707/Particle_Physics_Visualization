"""The payloads of ``GET /api/xgboost``: E1, E3, E4 and E5 from the stored analysis.

Each view is computed once on the whole experiment - all rows for E1 and E4,
the validation split's 2,000-row sample for E3, the models themselves for E5 -
exactly as the notebook computes it, so the selection does not apply and every
payload says so (``filtered: false`` and :data:`SELECTION_NOTE`).

The marks follow CLAUDE.md section 2:

* **E1.** Five fold values are five observations, drawn as dots; their mean
  is the aggregate and carries the Student-t 95 % interval of the mean over
  five folds (4 degrees of freedom, t = 2.776), never a naked point. The
  sample SD is reported beside it as the spread of the folds, a different
  quantity.
* **E3.** The confusion matrix is counts. Every rate derived from it carries
  a Wilson score interval, which never leaves [0, 1] and does not collapse
  at 0 or 1, and names it; balanced accuracy, a mean of two rates, has a
  seeded percentile bootstrap over the 2,000 rows instead. The notebook's
  weighted precision, recall and F1 are kept for parity, labelled as such.
* **E4.** A description of a surrogate, not an estimate: each node's n, its
  value and its within-node SD of the booster's predictions (an uncapped
  spread), and the fidelity of the whole tree.
* **E5.** One shipped model's normalised gain is the bar; the five refitted
  folds' values are dots beside it, and their mean's Student-t interval a
  separate named envelope.

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
from ..text import typographic
from . import store
from .analysis import BINARY, CV_LABELS, HYPERPARAMETERS, KFOLD, LABEL_KEY, SURROGATE, TEST_SIZE
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

#: Bootstrap of the balanced accuracy.
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 42

INTERVAL_LABEL = "95 % Student-t interval of the mean over 5 folds (4 d.o.f.)"


def _text(node: Any) -> Any:
    if isinstance(node, str):
        return typographic(node)
    if isinstance(node, dict):
        return {k: _text(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_text(v) for v in node]
    return node


# ------------------------------------------------------------- run block --


def run_block(runs: dict[str, dict[str, Any]], task: str) -> dict[str, Any]:
    """Which model, which split, which analysis: the block every XGBoost payload carries."""
    row = runs[task]
    labels = [LABEL_KEY[label] for label in row["labels"]]
    ratio = row["split_ratio_42"]
    others = [row["split_ratio_0"], row["split_ratio_7"]]
    reproduced = bool(row["split_reproduced"])
    split = {
        "reproduced": reproduced,
        "ratio_42": sig(ratio),
        "ratio_others": sig_list(others),
        "seeds_others": [0, 7],
        "rule": ("validation / training MSE of the shipped model at random_state 42 must exceed "
                 "the same ratio at random_state 0 and 7: a model predicts the rows it was "
                 "trained on better than the rest"),
        "warning": None if reproduced else (
            f"Split not reproduced: validation / training MSE is {ratio:.3g} at random_state 42 "
            f"against {others[0]:.3g} and {others[1]:.3g} at 0 and 7, so the stored validation "
            "rows may include rows the model was trained on."),
    }
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


def mean_interval(values: Sequence[float], bounds: tuple[float, float] | None = None) -> dict[str, Any]:
    """Mean, SD (ddof 1), SE and the Student-t 95 % interval of the mean, clipped to ``bounds``."""
    v = np.asarray([x for x in values if x is not None and math.isfinite(x)], dtype=np.float64)
    n = int(v.size)
    if n == 0:
        return {"mean": None, "sd": None, "se": None, "t95": [None, None], "n": 0, "dof": None,
                "t": None, "clipped": False}
    mean = float(v.mean())
    if n < 2:
        return {"mean": sig(mean), "sd": None, "se": None, "t95": [None, None], "n": n, "dof": 0,
                "t": None, "clipped": False}
    sd = float(v.std(ddof=1))
    se = sd / math.sqrt(n)
    t = gaussian.t_quantile_975(n - 1)
    lo, hi = mean - t * se, mean + t * se
    clipped = False
    if bounds is not None:
        clo, chi = max(lo, bounds[0]), min(hi, bounds[1])
        clipped = (clo, chi) != (lo, hi)
        lo, hi = clo, chi
    return {"mean": sig(mean), "sd": sig(sd), "se": sig(se), "t95": [sig(lo), sig(hi)], "n": n,
            "dof": n - 1, "t": round(t, 3), "clipped": clipped}


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
    summary = {m: mean_interval([f["values"].get((m, parity)) for f in ordered], _BOUNDS[m])
               for m in metric_ids}
    per_label = None
    if task == "angle":
        per_label = {
            "theta": {
                "unit": "mrad", "metrics": _metric_list("mrad", ("mae", "rmse", "r2")),
                "summary": {m: mean_interval([_mrad(m, f["values"].get((m, "theta"))) for f in ordered],
                                             _BOUNDS[m]) for m in ("mae", "rmse", "r2")},
                "residual": "θ_pred − θ_true",
            },
            "phi": {
                "unit": "mrad", "metrics": _metric_list("mrad", ("mae", "rmse")),
                "summary": {m: mean_interval([_mrad(m, f["values"].get((m, "phi"))) for f in ordered],
                                             _BOUNDS[m]) for m in ("mae", "rmse")},
                "residual": "φ_pred − φ_true wrapped to (−π, π]",
            },
        }
    notes = {
        "folds": ("Each fold refits the notebook's regressor (objective reg:squarederror, 100 "
                  "trees, learning rate 0.1, random_state 42) on four fifths of the rows of "
                  "KFold(5, shuffle=True, random_state=42) and scores the fifth. A fold value is "
                  "one observation and is drawn as a dot."),
        "interval": ("The mean of the five folds carries the 95 % Student-t interval of the mean "
                     "(4 d.o.f., t = 2.776): the uncertainty of the aggregate. The SD beside it "
                     "is the spread of the folds, a different quantity, and is not a whisker."),
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
        "interval": {"label": INTERVAL_LABEL, "level": 0.95, "dof": 4,
                     "t": round(gaussian.t_quantile_975(4), 3), "method": metrics.METHOD_T},
        "notes": notes,
    })


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


def balanced_bootstrap(tn: int, fp: int, fn: int, tp: int) -> dict[str, Any]:
    """The 95 % percentile bootstrap of the balanced accuracy over the sample's rows.

    A resample of the rows changes the balanced accuracy only through the four
    confusion counts, which follow the multinomial over the cells; drawing
    those counts directly is the same distribution as resampling the rows.
    A replicate with an empty class has no balanced accuracy and is counted.
    """
    n = tn + fp + fn + tp
    if n == 0:
        return {"lo": None, "hi": None, "n_undefined": 0}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    counts = rng.multinomial(n, np.array([tn, fp, fn, tp], dtype=np.float64) / n,
                             size=BOOTSTRAP_REPLICATES)
    ctn, cfp, cfn, ctp = (counts[:, i].astype(np.float64) for i in range(4))
    neg, pos = ctn + cfp, ctp + cfn
    ok = (neg > 0) & (pos > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        values = 0.5 * (ctp / pos + ctn / neg)
    values = values[ok]
    if values.size == 0:
        return {"lo": None, "hi": None, "n_undefined": int((~ok).sum())}
    lo, hi = np.percentile(values, [2.5, 97.5])
    return {"lo": float(lo), "hi": float(hi), "n_undefined": int((~ok).sum())}


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
    boot = balanced_bootstrap(tn, fp, fn, tp)
    balanced = None
    if n_1 and n_0:
        balanced = 0.5 * (tp / n_1 + tn / n_0)
    rates.append({
        "id": "balanced_accuracy", "label": "Balanced accuracy",
        "definition": "(recall class 1 + recall class 0) / 2", "k": None, "n": n,
        "value": sig(balanced),
        "interval": None if boot["lo"] is None else {
            "lo": sig(boot["lo"]), "hi": sig(boot["hi"]), "level": 0.95,
            "method": metrics.METHOD_BOOTSTRAP,
            "label": (f"95 % percentile bootstrap over the {n:,} rows (B = "
                      f"{BOOTSTRAP_REPLICATES:,}, seed {BOOTSTRAP_SEED})")},
        "n_undefined_replicates": boot["n_undefined"],
        "note": "" if balanced is not None else "Undefined: one class is absent from the sample.",
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
            "intervals": ("Each rate carries a 95 % Wilson score interval of a proportion; the "
                          "balanced accuracy, a mean of two rates, a seeded percentile bootstrap "
                          "over the sample's rows, drawn as the multinomial of the four confusion "
                          "counts - the same distribution as resampling the rows."),
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
    nodes: dict[int, dict[str, Any]] = {}
    for node_id, depth, left, right, feature, threshold, n, impurity, label, value, variance in rows:
        node = nodes.setdefault(int(node_id), {
            "id": int(node_id), "depth": int(depth), "left": int(left), "right": int(right),
            "leaf": int(left) < 0, "feature": feature,
            "frame": ddl.feature_frame(feature) if feature else None,
            # A variance: sklearn's running sums can leave −1e−16 on a pure node.
            "threshold": sig(threshold), "n": int(n), "impurity": sig(max(0.0, impurity)),
            "values": {}, "sd": {},
        })
        node["values"][label] = sig(value)
        node["sd"][label] = sig(math.sqrt(variance)) if variance is not None and variance >= 0 else None
    ordered = [nodes[k] for k in sorted(nodes)]
    for node in ordered:
        if node["leaf"]:
            node["left"] = node["right"] = None
    row = runs[task]
    outputs = ((row.get("details") or {}).get("surrogate_outputs") or {})
    unit = LABEL_UNITS["momentum"] if task == "momentum" else "rad"
    domain = {label: [sig(min(n["values"][label] for n in ordered)),
                      sig(max(n["values"][label] for n in ordered))] for label in labels} if ordered else {}
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
            "outputs": {k: {"r2": sig(v.get("r2")), "mae": sig(v.get("mae"))}
                        for k, v in outputs.items()},
            "against": ("the shipped booster's own predictions on every row, in-sample, as the "
                        "notebook measures it"),
        },
        "tree": {**SURROGATE, "criterion": "squared_error", "n_rows": int(row["n_rows"]),
                 "target": "the shipped booster's predictions"},
        "color_domain": domain,
        "notes": {
            "description": ("A description of the booster, not an estimate: each node shows its "
                            "number of rows, the mean of the booster's predictions over them and "
                            "their SD, the spread within the node (no whisker)."),
            "impurity": ("impurity is sklearn's: the variance of the booster's predictions in the "
                         "node, averaged over the outputs for the angle task; sd is each output's "
                         "own within-node SD."),
            "fidelity": ("Fidelity is R² and MAE of the tree against the booster, on the rows it "
                         "was fitted to; it says how much of the booster the three levels of "
                         "rules describe."),
        },
    })


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
    features = []
    for rank, name in enumerate(order, start=1):
        norm, gain, weight, cover = shipped[name]
        values = [folds.get(name, {}).get(k) for k in range(KFOLD["n_splits"])]
        summary = mean_interval([v for v in values if v is not None], (0.0, 1.0))
        features.append({
            "name": name, "rank": rank, "frame": ddl.feature_frame(name),
            "shipped": sig(norm),
            "raw": {"gain": sig(gain), "weight": sig(weight), "cover": sig(cover)},
            "folds": sig_list(values),
            "fold_mean": summary["mean"], "fold_sd": summary["sd"], "fold_t95": summary["t95"],
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
        "interval": {"label": INTERVAL_LABEL, "level": 0.95, "dof": 4,
                     "t": round(gaussian.t_quantile_975(4), 3), "method": metrics.METHOD_T,
                     "clip": "clipped to [0, 1], the range of a share"},
        "notes": {
            "bar": ("The bar is one model, the shipped one; the dots are the five refitted folds "
                    "and the envelope their mean's Student-t interval, so the bar is never read "
                    "as the folds' mean."),
            "gain": ("A gain importance says how much a feature's splits reduced the training "
                     "loss, not how much the prediction depends on it; correlated features share "
                     "or swap their gain between refits."),
        },
    })
