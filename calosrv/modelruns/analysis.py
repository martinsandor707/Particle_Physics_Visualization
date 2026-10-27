"""The analysis of one paired experiment: the notebooks' computations, reproduced exactly.

Pure computation on arrays: numpy, pandas, XGBoost and scikit-learn, no HTTP
and no database. ``store.read_dataset`` hands it the event table in
``event_number`` order - which is the producer file's order, the order the
notebook read - and ``store.write`` keeps what it returns.

Every step is the notebook's own call, with the notebook's arguments
(``XGBoost-Reg-*.ipynb``, identical across species):

1. **The split.** ``train_test_split(np.arange(n), test_size=0.2,
   random_state=42)`` gives the notebook's validation rows, in the order the
   notebook's ``val_df`` held them. Measured on the four s1 files, refitting
   ``XGBRegressor(objective='reg:squarederror', random_state=42,
   n_estimators=100, learning_rate=0.1)`` on the other 80 % recreates the
   shipped electron momentum model exactly (max |Δpred| = 0).
2. **The split check.** A model fitted on those rows predicts them better than
   the rest, so validation / training MSE at random_state 42 exceeds the same
   ratio at 0 and at 7 (measured 1.11-1.50 momentum, 3.3-33 angle, against
   about 1). When it does not, the stored predictions are not a holdout the
   model never saw, and the run is flagged "split not reproduced".
3. **Holdout predictions** of both shipped models on the validation rows: E2,
   prediction against truth, and E3's pools.
4. **E1**, ``train_and_evaluate``: ``KFold(5, shuffle=True, random_state=42)``
   over all rows, one refit per fold with the hyperparameters above on
   ``np.array`` copies, as the notebook passes them, and its sklearn metrics on
   the raw labels. The angle task is fitted on ``[incoming_theta,
   incoming_phi]``, the order that notebook cell uses (its other cells, and the
   shipped model, use ``[phi, theta]``); its metrics are the uniform average
   over the two, φ unwrapped, kept for parity, beside per-label θ metrics and φ
   metrics on the residual wrapped to (−π, π].
5. **E3** (momentum): the validation rows' pools p < 2 GeV and p > 10 GeV (p >
   2 GeV when fewer than 50), ``pool.sample(min(n, len(pool)), random_state=42)``
   with n = 1,980 and 20, concatenated and shuffled with ``sample(frac=1,
   random_state=42)``, thresholded at 2 GeV, with the notebook's metrics.
6. **E4**: ``DecisionTreeRegressor(max_depth=3, random_state=42)`` fitted
   in-sample to the shipped booster's predictions on all rows; its ``tree_``
   arrays, each node's within-node variance per output, and its fidelity.
7. **E5**: the shipped booster's normalised gain (``feature_importances_``) and
   its raw gain, weight and cover (``get_score``); each fold model's normalised
   gain.

XGBoost runs on ``nthread`` threads (half the cores, ``config.model_threads``),
measured not to change a single prediction against one thread.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from .discovery import TASKS, ModelFile
from .pairing import TASK_LABELS

#: Bumped whenever a change here would change a stored number; every stored
#: analysis of an older version is stale and re-run.
ANALYSIS_VERSION = 1

#: ``train_test_split`` as the notebook calls it, and the seeds of the split check.
TEST_SIZE = 0.2
SPLIT_SEED = 42
CHECK_SEEDS: tuple[int, ...] = (0, 7)

#: The notebook's regressor, for every refit.
HYPERPARAMETERS: dict[str, Any] = {
    "objective": "reg:squarederror", "random_state": 42, "n_estimators": 100,
    "learning_rate": 0.1,
}

#: ``KFold`` as ``train_and_evaluate`` builds it.
KFOLD: dict[str, Any] = {"n_splits": 5, "shuffle": True, "random_state": 42}

#: ``train_and_evaluate``'s label order (``prepare_data``): θ before φ.
CV_LABELS: dict[str, tuple[str, ...]] = {
    "momentum": ("incoming_momentum",),
    "angle": ("incoming_theta", "incoming_phi"),
}

#: Short label keys, as the tables and payloads name them.
LABEL_KEY: dict[str, str] = {
    "incoming_momentum": "momentum", "incoming_phi": "phi", "incoming_theta": "theta",
}

#: ``evaluate_binary_performance``: the threshold, the pools and the sample design.
BINARY: dict[str, Any] = {
    "threshold": 2.0, "class_0_below": 2.0, "class_1_above": 10.0, "min_class_1": 50,
    "total": 2000, "fraction_0": 0.99, "fraction_1": 0.01, "random_state": 42,
}

#: ``surrogate_tree_visualization``.
SURROGATE: dict[str, Any] = {"max_depth": 3, "random_state": 42}

#: The steps of one analysis, for "Analysing: N of M steps".
STEPS: tuple[str, ...] = (
    "read the event table",
    "split check and holdout predictions (momentum)",
    "split check and holdout predictions (angle)",
    *(f"cross-validation fold {k + 1} of 5 (momentum)" for k in range(5)),
    *(f"cross-validation fold {k + 1} of 5 (angle)" for k in range(5)),
    "binary thresholding sample",
    "surrogate tree (momentum)",
    "surrogate tree (angle)",
    "gain importances",
    "write the results",
)
N_STEPS = len(STEPS)


class Cancelled(Exception):
    """The server is shutting down; the analysis stops between steps."""


@dataclass
class Dataset:
    """The event table as the analysis reads it, in ``event_number`` order."""

    event_number: np.ndarray
    e1_bin: np.ndarray
    #: Notebook label (``incoming_momentum`` ...) -> values.
    labels: dict[str, np.ndarray]
    #: Task -> the model's features, columns named and ordered as the model's.
    features: dict[str, pd.DataFrame]
    #: Whether the archive's event ids rise strictly in file order (None: not read).
    archive_increasing: bool | None = None

    @property
    def n(self) -> int:
        return int(self.event_number.size)

    def null_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for frame in self.features.values():
            for name, count in frame.isna().sum().items():
                if count:
                    out[str(name)] = int(count)
        return out


@dataclass
class TaskResult:
    """Everything one task's model contributes."""

    task: str
    labels: tuple[str, ...]
    n_train: int
    n_val: int
    split_ratios: dict[int, float]
    split_reproduced: bool
    #: Validation rows (positions in event order, ascending) and their predictions.
    val_rows: np.ndarray
    val_pred: np.ndarray
    #: E1: one dict per fold: fold, n_train, n_val, values {(metric, label): value}.
    folds: list[dict[str, Any]] = field(default_factory=list)
    #: E5: name -> (gain_norm, raw_gain, raw_weight, raw_cover) of the shipped model.
    importance: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    #: E5: per fold, name -> normalised gain.
    fold_importance: list[dict[str, float]] = field(default_factory=list)
    #: E4: one dict per node.
    tree: list[dict[str, Any]] = field(default_factory=list)
    surrogate_r2: float | None = None
    surrogate_mae: float | None = None
    surrogate_outputs: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class BinaryResult:
    """E3: the sample, in its shuffled order, and the notebook's metrics."""

    rows: np.ndarray            # positions in event order
    p: np.ndarray
    y_true: np.ndarray
    value: np.ndarray
    y_pred: np.ndarray
    pool_0: int
    pool_1: int
    fallback: bool
    n_0: int
    n_1: int
    metrics: dict[str, float]


@dataclass
class AnalysisResult:
    n_rows: int
    tasks: dict[str, TaskResult]
    binary: BinaryResult
    timings: dict[str, float]
    nulls: dict[str, int]
    nthread: int


Progress = Callable[[int, str], None]


def _noop(_step: int, _label: str) -> None:
    return None


def wrap(radians: np.ndarray) -> np.ndarray:
    """An angle difference on (−π, π] (``stats.circular.wrap_angle``)."""
    from ..stats.circular import wrap_angle

    return wrap_angle(np.asarray(radians, dtype=np.float64))


def load_model(model: ModelFile, nthread: int):
    """The shipped regressor, as the notebook's ``XGBRegressor`` holds it."""
    import xgboost as xgb

    regressor = xgb.XGBRegressor()
    regressor.load_model(str(model.path))
    regressor.set_params(n_jobs=nthread)
    return regressor


def split_indices(n: int, random_state: int = SPLIT_SEED) -> tuple[np.ndarray, np.ndarray]:
    """``(train, validation)`` positions, in ``train_test_split``'s own order."""
    from sklearn.model_selection import train_test_split

    train, val = train_test_split(np.arange(n), test_size=TEST_SIZE, random_state=random_state)
    return np.asarray(train), np.asarray(val)


def split_ratios(pred: np.ndarray, truth: np.ndarray) -> dict[int, float]:
    """Validation / training MSE (mean over the outputs) at each split seed."""
    n = truth.shape[0]
    squared = (pred.reshape(n, -1) - truth.reshape(n, -1)) ** 2
    per_row = squared.mean(axis=1)
    out: dict[int, float] = {}
    for seed in (SPLIT_SEED, *CHECK_SEEDS):
        train, val = split_indices(n, seed)
        out[seed] = float(per_row[val].mean() / per_row[train].mean())
    return out


def reproduced(ratios: dict[int, float]) -> bool:
    """The flag: the random_state 42 ratio exceeds both others."""
    mine = ratios[SPLIT_SEED]
    return all(mine > ratios[s] for s in CHECK_SEEDS)


def _truth(data: Dataset, labels: tuple[str, ...]) -> np.ndarray:
    columns = [data.labels[label] for label in labels]
    return columns[0] if len(columns) == 1 else np.column_stack(columns)


def fold_metrics(task: str, truth: np.ndarray, pred: np.ndarray) -> dict[tuple[str, str], float]:
    """One fold's metrics: the notebook's four, then per label for the angle task.

    The notebook's are sklearn's on the raw labels (uniform average over the
    outputs). θ adds its own MAE, RMSE and R²; φ its MAE and RMSE of the
    residual wrapped to (−π, π] - an R² of an azimuth has no meaning.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    parity = "momentum" if task == "momentum" else "parity"
    mse = float(mean_squared_error(truth, pred))
    out = {
        ("mae", parity): float(mean_absolute_error(truth, pred)),
        ("mse", parity): mse,
        ("rmse", parity): float(np.sqrt(mse)),
        ("r2", parity): float(r2_score(truth, pred)),
    }
    if task == "angle":
        order = CV_LABELS["angle"]
        theta_t, theta_p = truth[:, order.index("incoming_theta")], pred[:, order.index("incoming_theta")]
        phi_t, phi_p = truth[:, order.index("incoming_phi")], pred[:, order.index("incoming_phi")]
        theta_mse = float(mean_squared_error(theta_t, theta_p))
        out[("mae", "theta")] = float(mean_absolute_error(theta_t, theta_p))
        out[("rmse", "theta")] = float(np.sqrt(theta_mse))
        out[("r2", "theta")] = float(r2_score(theta_t, theta_p))
        residual = wrap(phi_p - phi_t)
        out[("mae", "phi")] = float(np.mean(np.abs(residual)))
        out[("rmse", "phi")] = float(np.sqrt(np.mean(residual ** 2)))
    return out


def cross_validate(task: str, data: Dataset, nthread: int, step: Callable[[str], None],
                   ) -> tuple[list[dict[str, Any]], list[dict[str, float]]]:
    """E1: ``train_and_evaluate`` - five refits, their metrics and their gain importances."""
    import xgboost as xgb
    from sklearn.model_selection import KFold

    frame = data.features[task]
    names = list(frame.columns)
    x = np.array(frame)
    y = np.array(_truth(data, CV_LABELS[task]))
    folds: list[dict[str, Any]] = []
    importances: list[dict[str, float]] = []
    kfold = KFold(**KFOLD)
    for fold, (train, val) in enumerate(kfold.split(x)):
        step(f"cross-validation fold {fold + 1} of 5 ({task})")
        regressor = xgb.XGBRegressor(**HYPERPARAMETERS, n_jobs=nthread)
        regressor.fit(x[train], y[train])
        pred = regressor.predict(x[val])
        folds.append({"fold": fold, "n_train": int(train.size), "n_val": int(val.size),
                      "values": fold_metrics(task, y[val], pred)})
        gains = np.asarray(regressor.feature_importances_, dtype=np.float64)
        importances.append({name: float(g) for name, g in zip(names, gains)})
    return folds, importances


def shipped_importance(regressor, names: list[str]) -> dict[str, tuple[float, float, float, float]]:
    """E5: normalised gain and the raw gain, weight and cover of every feature (0 if unused)."""
    booster = regressor.get_booster()
    raw = {kind: booster.get_score(importance_type=kind) for kind in ("gain", "weight", "cover")}
    norm = np.asarray(regressor.feature_importances_, dtype=np.float64)
    return {name: (float(norm[i]), float(raw["gain"].get(name, 0.0)),
                   float(raw["weight"].get(name, 0.0)), float(raw["cover"].get(name, 0.0)))
            for i, name in enumerate(names)}


def _depths(left: np.ndarray, right: np.ndarray) -> list[int]:
    depth = [0] * left.size
    stack = [0]
    while stack:
        node = stack.pop()
        for child in (left[node], right[node]):
            if child >= 0:
                depth[child] = depth[node] + 1
                stack.append(int(child))
    return depth


def surrogate(task: str, frame: pd.DataFrame, proxy: np.ndarray,
              labels: tuple[str, ...]) -> tuple[list[dict[str, Any]], float, float,
                                                dict[str, dict[str, float]]]:
    """E4: the depth-3 tree on the booster's predictions, its nodes and its fidelity.

    Each node keeps sklearn's value per output and impurity (for two outputs the
    mean of their variances, as sklearn computes it) and, from the rows the
    decision path sends through it, each output's own within-node variance of
    the booster's predictions - the spread the card draws as ± SD.
    """
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.tree import DecisionTreeRegressor

    tree = DecisionTreeRegressor(**SURROGATE).fit(frame, proxy)
    fitted = tree.predict(frame)
    r2 = float(r2_score(proxy, fitted))
    mae = float(mean_absolute_error(proxy, fitted))
    outputs: dict[str, dict[str, float]] = {}
    proxy2 = proxy.reshape(proxy.shape[0], -1)
    fitted2 = np.asarray(fitted).reshape(proxy.shape[0], -1)
    for k, label in enumerate(labels):
        outputs[LABEL_KEY[label]] = {"r2": float(r2_score(proxy2[:, k], fitted2[:, k])),
                                     "mae": float(mean_absolute_error(proxy2[:, k], fitted2[:, k]))}
    t = tree.tree_
    left, right = np.asarray(t.children_left), np.asarray(t.children_right)
    depth = _depths(left, right)
    path = tree.decision_path(frame).tocsc()
    names = list(frame.columns)
    nodes: list[dict[str, Any]] = []
    for node in range(t.node_count):
        rows = path.indices[path.indptr[node]:path.indptr[node + 1]]
        variance = proxy2[rows].var(axis=0) if rows.size else np.full(len(labels), np.nan)
        leaf = left[node] < 0
        nodes.append({
            "node_id": node, "depth": depth[node],
            "children_left": int(left[node]), "children_right": int(right[node]),
            "feature": None if leaf else names[int(t.feature[node])],
            "threshold": None if leaf else float(t.threshold[node]),
            "n_node_samples": int(t.n_node_samples[node]),
            "impurity": float(t.impurity[node]),
            "values": {LABEL_KEY[label]: float(t.value[node, k, 0]) for k, label in enumerate(labels)},
            "variance": {LABEL_KEY[label]: float(variance[k]) for k, label in enumerate(labels)},
        })
    return nodes, r2, mae, outputs


def binary_sample(data: Dataset, val: np.ndarray, pred_momentum: np.ndarray) -> BinaryResult:
    """E3: ``evaluate_binary_performance`` on the notebook's ``val_df``, row for row.

    ``val`` is the validation positions in ``train_test_split``'s order - the
    order of the notebook's ``val_df`` - so each pool is filtered in that order
    and pandas draws the same rows from it.
    """
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score,
                                 precision_score, recall_score)

    b = BINARY
    p = data.labels["incoming_momentum"]
    val_df = pd.DataFrame({"incoming_momentum": p[val]}, index=val)
    class_0_pool = val_df[val_df["incoming_momentum"] < b["class_0_below"]]
    class_1_pool = val_df[val_df["incoming_momentum"] > b["class_1_above"]]
    fallback = len(class_1_pool) < b["min_class_1"]
    if fallback:
        class_1_pool = val_df[val_df["incoming_momentum"] > b["threshold"]]
    total = b["total"]
    n_0 = int(total * b["fraction_0"])
    n_1 = int(total * b["fraction_1"])
    s_0 = class_0_pool.sample(min(n_0, len(class_0_pool)), random_state=b["random_state"])
    s_1 = class_1_pool.sample(min(n_1, len(class_1_pool)), random_state=b["random_state"])
    special = pd.concat([s_0, s_1]).sample(frac=1, random_state=b["random_state"])
    rows = special.index.to_numpy(dtype=np.int64)
    y_true = (special["incoming_momentum"] > b["threshold"]).astype(int).to_numpy()
    value = pred_momentum[rows]
    y_pred = (value > b["threshold"]).astype(int)
    metrics: dict[str, float] = {}
    if rows.size:
        with warnings.catch_warnings():
            # One class absent from a small sample: sklearn warns and still answers.
            warnings.simplefilter("ignore")
            metrics = {
                "accuracy": float(accuracy_score(y_true, y_pred)),
                "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
                "precision_weighted": float(precision_score(y_true, y_pred, zero_division=0,
                                                            average="weighted")),
                "recall_weighted": float(recall_score(y_true, y_pred, zero_division=0,
                                                      average="weighted")),
                "f1_weighted": float(f1_score(y_true, y_pred, zero_division=0, average="weighted")),
            }
    return BinaryResult(rows=rows, p=special["incoming_momentum"].to_numpy(), y_true=y_true,
                        value=np.asarray(value, dtype=np.float64), y_pred=y_pred,
                        pool_0=len(class_0_pool), pool_1=len(class_1_pool), fallback=bool(fallback),
                        n_0=len(s_0), n_1=len(s_1), metrics=metrics)


def run(data: Dataset, models: dict[str, ModelFile], nthread: int,
        progress: Progress = _noop, should_stop: Callable[[], bool] = lambda: False,
        first_step: int = 1) -> AnalysisResult:
    """Every step of the analysis on ``data`` with the paired ``models``.

    ``progress(step, label)`` is called before each step, numbered from
    ``first_step`` (the caller's read of the table is step 0's predecessor);
    ``should_stop`` is polled between steps and raises :class:`Cancelled`.
    """
    timings: dict[str, float] = {}
    counter = {"step": first_step, "label": "", "t": time.perf_counter()}

    def close() -> None:
        if counter["label"]:
            timings[counter["label"]] = round(time.perf_counter() - counter["t"], 3)
            counter["label"] = ""

    def step(label: str) -> None:
        close()
        if should_stop():
            raise Cancelled("the server is shutting down")
        counter["step"] += 1
        counter["label"], counter["t"] = label, time.perf_counter()
        progress(counter["step"], label)

    n = data.n
    if n < 10:
        raise ValueError(f"the experiment holds {n} events; the 80/20 split and five folds need "
                         "at least 10.")
    train, val = split_indices(n)
    regressors = {task: load_model(models[task], nthread) for task in TASKS}
    tasks: dict[str, TaskResult] = {}
    predictions: dict[str, np.ndarray] = {}
    for task in TASKS:
        step(f"split check and holdout predictions ({task})")
        labels = TASK_LABELS[task]
        frame = data.features[task]
        truth = _truth(data, labels)
        if not np.all(np.isfinite(truth)):
            bad = int((~np.isfinite(np.asarray(truth, dtype=np.float64))).sum())
            raise ValueError(f"{bad} {task} label value(s) are missing or not finite; the notebook's "
                             "metrics are undefined on them, and dropping rows would move its split.")
        pred = np.asarray(regressors[task].predict(frame), dtype=np.float64)
        predictions[task] = pred
        ratios = split_ratios(pred, truth)
        order = np.sort(val)
        tasks[task] = TaskResult(
            task=task, labels=labels, n_train=int(train.size), n_val=int(val.size),
            split_ratios=ratios, split_reproduced=reproduced(ratios),
            val_rows=order, val_pred=pred[order],
        )
    for task in TASKS:
        folds, importances = cross_validate(task, data, nthread, step)
        tasks[task].folds = folds
        tasks[task].fold_importance = importances
    step("binary thresholding sample")
    binary = binary_sample(data, val, predictions["momentum"])
    for task in TASKS:
        step(f"surrogate tree ({task})")
        nodes, r2, mae, outputs = surrogate(task, data.features[task], predictions[task],
                                            TASK_LABELS[task])
        result = tasks[task]
        result.tree, result.surrogate_r2, result.surrogate_mae = nodes, r2, mae
        result.surrogate_outputs = outputs
    step("gain importances")
    for task in TASKS:
        tasks[task].importance = shipped_importance(regressors[task],
                                                    list(data.features[task].columns))
    close()
    return AnalysisResult(n_rows=n, tasks=tasks, binary=binary, timings=timings,
                          nulls=data.null_counts(), nthread=nthread)
