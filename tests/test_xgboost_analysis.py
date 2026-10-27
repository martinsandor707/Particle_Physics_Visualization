"""The model analysis reproduces the XGBoost notebooks' own computations, on the same arrays.

``calosrv/modelruns/analysis.py`` restates five notebook cells - the split,
``train_and_evaluate`` (E1), ``evaluate_binary_performance`` (E3),
``surrogate_tree_visualization`` (E4) and ``feature_importances_`` (E5) - in
index form, so it can run on the event table instead of a DataFrame read from
CSV. Each test here runs the notebook's code as the notebook wrote it, on the
DataFrame the notebook would have read (the fixture's aggregate, in file
order), and asserts the analysis got the same numbers: the folds' metrics, the
2,000-row sample row for row, the surrogate's ``tree_`` arrays, the importances.
No database: :class:`analysis.Dataset` is built from the same file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score,
                             mean_absolute_error, mean_squared_error, precision_score,
                             r2_score, recall_score)
from sklearn.model_selection import KFold, train_test_split
from sklearn.tree import DecisionTreeRegressor

from calosrv.modelruns import analysis, discovery, views
from calosrv.modelruns.pairing import TASK_LABELS


@pytest.fixture(scope="module")
def notebook(xgb_sources):
    """The notebook's DataFrame, the shipped (fixture) models, and the analysis of both."""
    df = pd.read_csv(xgb_sources["electron"], float_precision="round_trip")
    catalogue = discovery.scan(xgb_sources["models"])
    models = {task: catalogue.get("electron", 1, task) for task in discovery.TASKS}
    assert all(models.values()), catalogue.as_dict()
    features = {task: df[list(models[task].feature_names)] for task in discovery.TASKS}
    data = analysis.Dataset(
        event_number=df["event_id"].to_numpy(dtype=np.int64),
        e1_bin=df["incoming_momentum_bin"].to_numpy(dtype=np.float64),
        labels={label: df[label].to_numpy(dtype=np.float64)
                for labels in TASK_LABELS.values() for label in labels},
        features=features,
    )
    steps: list[tuple[int, str]] = []
    result = analysis.run(data, models, nthread=2, progress=lambda k, label: steps.append((k, label)))
    shipped = {}
    for task, model in models.items():
        regressor = xgb.XGBRegressor(n_jobs=THREADS)
        regressor.load_model(str(model.path))
        shipped[task] = regressor
    return {"df": df, "models": models, "shipped": shipped, "data": data, "result": result,
            "steps": steps, "features": list(models["momentum"].feature_names)}


def test_every_step_is_reported_in_order(notebook):
    numbers = [k for k, _ in notebook["steps"]]
    assert numbers == list(range(2, analysis.N_STEPS))
    assert [label for _, label in notebook["steps"]] == list(analysis.STEPS[1:-1])


# ------------------------------------------------------------------ split --


def test_holdout_predictions_are_the_notebooks_val_df_predictions(notebook):
    """``train_test_split(df, test_size=0.2, random_state=42)``: the same rows, the same values."""
    df, result = notebook["df"], notebook["result"]
    _, val_df = train_test_split(df, test_size=0.2, random_state=42)
    for task in discovery.TASKS:
        t = result.tasks[task]
        assert np.array_equal(t.val_rows, np.sort(val_df.index.to_numpy()))
        expected = notebook["shipped"][task].predict(df.loc[t.val_rows, notebook["features"]])
        assert np.array_equal(t.val_pred, np.asarray(expected, dtype=np.float64))
        assert t.n_val == len(val_df) and t.n_train == len(df) - len(val_df)


def _per_row_errors(notebook, task: str) -> np.ndarray:
    df = notebook["df"]
    pred = notebook["shipped"][task].predict(df[notebook["features"]])
    y = df[list(TASK_LABELS[task])].to_numpy()
    return ((pred.reshape(len(df), -1) - y) ** 2).mean(axis=1)


def test_the_split_check_compares_seed_42_with_99_others(notebook):
    df, result = notebook["df"], notebook["result"]
    assert analysis.CHECK_SEEDS == tuple(s for s in range(100) if s != 42)
    for task in TASK_LABELS:
        e2 = _per_row_errors(notebook, task)
        ratios = {}
        for seed in (42, *range(100)):
            tr, va = train_test_split(np.arange(len(df)), test_size=0.2, random_state=seed)
            ratios[seed] = e2[va].mean() / e2[tr].mean()
        t = result.tasks[task]
        assert t.split_ratios == pytest.approx(ratios, rel=1e-12)
        others = [ratios[s] for s in range(100) if s != 42]
        assert t.split_reproduced == (ratios[42] > analysis.SPLIT_MARGIN[task] * max(others))
        assert t.split["max_others"] == pytest.approx(max(others), rel=1e-12)
        assert t.split["seed_of_max"] == analysis.CHECK_SEEDS[int(np.argmax(others))]
        assert t.split["margin"] == analysis.SPLIT_MARGIN[task] and len(t.split["ratio_others"]) == 99
    # The fixture's models were trained on the reproduced 80 %. The momentum model fits its
    # training rows far better (ratio 6.7), so the check passes. The angle model predicts the
    # synthetic angles almost exactly on every row (ratio 1.03): nothing tells its training
    # rows apart, the check cannot confirm the split and says so - where the former rule
    # (above seeds 0 and 7 only, 0.80 and 0.91) passed it by chance.
    assert result.tasks["momentum"].split_reproduced
    assert not result.tasks["angle"].split_reproduced
    assert result.tasks["angle"].split["ratio_42"] < 1.1


def test_the_flag_needs_the_42_ratio_above_every_other_by_the_margin():
    others = {s: 1.0 for s in analysis.CHECK_SEEDS}
    for task, margin in analysis.SPLIT_MARGIN.items():
        assert analysis.reproduced({**others, 42: 1.01 * margin}, task)
        assert not analysis.reproduced({**others, 42: 0.99 * margin}, task)
        # One seed of the 99 as high as 42: not reproduced, whatever the other 98 say.
        assert not analysis.reproduced({**others, 13: 1.5 * margin, 42: 1.01 * margin}, task)
    assert not analysis.reproduced({42: float("nan"), **others}, "momentum")


#: Row permutations of the per-row errors on which the check must fail, and the most of them
#: it may pass (measured on the fixture: see test_row_permuted_errors_fail_the_split_check).
PERMUTATIONS = 200


@pytest.mark.parametrize("task", discovery.TASKS)
def test_row_permuted_errors_fail_the_split_check(notebook, task):
    """The errors in a shuffled order are a split the model was not trained on: the check fails.

    The fixture's 300 rows and its 20-tree models reproduce the real data's result (row-
    permuted, 5,000 permutations per species and task on the four s1 aggregates: 1 pass in
    20,000 for momentum, 5 in 20,000 for angle): every one of 200 permutations fails here.
    """
    e2 = _per_row_errors(notebook, task)
    n = e2.size
    rng = np.random.default_rng(2026)
    splits = [analysis.split_indices(n, seed) for seed in (42, *analysis.CHECK_SEEDS)]
    passed = 0
    for _ in range(PERMUTATIONS):
        e = e2[rng.permutation(n)]
        ratios = {seed: e[va].mean() / e[tr].mean()
                  for seed, (tr, va) in zip((42, *analysis.CHECK_SEEDS), splits)}
        passed += analysis.reproduced(ratios, task)
    assert passed == 0, f"{passed} of {PERMUTATIONS} permutations passed"
    if task == "momentum":
        # The true order passes, by more than the margin (the fixture's angle model does not
        # tell its training rows apart; test_the_split_check_compares_seed_42_with_99_others).
        true = {seed: e2[va].mean() / e2[tr].mean()
                for seed, (tr, va) in zip((42, *analysis.CHECK_SEEDS), splits)}
        assert analysis.reproduced(true, task)


def test_the_angle_outputs_are_checked_against_their_own_labels(notebook):
    df = notebook["df"]
    labels = TASK_LABELS["angle"]
    pred = np.asarray(notebook["shipped"]["angle"].predict(df[notebook["features"]]), dtype=np.float64)
    truth = df[list(labels)].to_numpy()
    errors = analysis.output_order("angle", pred, truth, labels)
    assert set(errors) == {"phi", "theta"} and errors["phi"]["phi"] < errors["phi"]["theta"]
    assert errors["theta"]["theta"] < errors["theta"]["phi"]
    analysis.check_output_order("angle", errors)
    stored = notebook["result"].tasks["angle"].output_order
    for output, row in errors.items():
        assert stored[output] == pytest.approx(row, rel=1e-12)
    # φ's error is wrapped: a prediction 2π away from its truth is no error at all.
    shifted = pred.copy()
    shifted[:, 0] += 2 * np.pi
    assert analysis.output_order("angle", shifted, truth, labels)["phi"]["phi"] == pytest.approx(
        errors["phi"]["phi"], rel=1e-9)
    # The outputs swapped: the run would store φ as θ; it fails, naming both errors.
    with pytest.raises(ValueError, match=r"not in the order \[phi, theta\]"):
        analysis.check_output_order("angle", analysis.output_order("angle", pred[:, ::-1], truth, labels))


def test_a_model_with_swapped_outputs_fails_the_run(notebook, monkeypatch):
    """End to end: the analysis refuses before it stores anything under the wrong labels."""
    real = analysis.load_model

    class Swapped:
        def __init__(self, regressor):
            self.regressor = regressor

        def predict(self, x):
            return np.asarray(self.regressor.predict(x))[:, ::-1]

    def load(model, nthread):
        regressor = real(model, nthread)
        return Swapped(regressor) if model.task == "angle" else regressor

    monkeypatch.setattr(analysis, "load_model", load)
    with pytest.raises(ValueError, match="outputs are not in the order"):
        analysis.run(notebook["data"], notebook["models"], nthread=1)


def test_the_value_hash_follows_the_values(notebook):
    data = notebook["data"]
    first = data.value_hash()
    assert first == data.value_hash() and len(first) == 64
    features = {task: frame.copy() for task, frame in data.features.items()}
    features["momentum"].iloc[3, 5] += 1e-9
    changed = analysis.Dataset(event_number=data.event_number, e1_bin=data.e1_bin,
                               labels=data.labels, features=features)
    assert changed.value_hash() != first
    labels = dict(data.labels)
    labels["incoming_phi"], labels["incoming_theta"] = labels["incoming_theta"], labels["incoming_phi"]
    swapped = analysis.Dataset(event_number=data.event_number, e1_bin=data.e1_bin, labels=labels,
                               features=data.features)
    assert swapped.value_hash() != first


# --------------------------------------------------------------------- E1 --


#: Threads for the reference refits. XGBoost's result does not depend on the count
#: (measured: identical predictions on 1 to 24 threads); all cores on 300 rows is
#: pure scheduling overhead.
THREADS = 2


def _train_and_evaluate(X, y, n_splits=5, mark=""):
    """The notebook's cell 5, verbatim but for ``core.``, the progress bar and the threads."""
    X_arr = np.array(X)
    y_arr = np.array(y)
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    xgb_regressor = xgb.XGBRegressor(objective="reg:squarederror", random_state=42,
                                     n_estimators=100, learning_rate=0.1, n_jobs=THREADS)
    results = {f"MAE_{mark}": [], f"MSE_{mark}": [], f"RMSE_{mark}": [], f"R2_score_{mark}": []}
    for train_index, val_index in kf.split(X_arr):
        X_train, X_val = X_arr[train_index], X_arr[val_index]
        y_train, y_val = y_arr[train_index], y_arr[val_index]
        xgb_regressor.fit(X_train, y_train)
        y_pred = xgb_regressor.predict(X_val)
        mse = mean_squared_error(y_val, y_pred)
        results[f"MAE_{mark}"].append(mean_absolute_error(y_val, y_pred))
        results[f"MSE_{mark}"].append(mse)
        results[f"RMSE_{mark}"].append(np.sqrt(mse))
        results[f"R2_score_{mark}"].append(r2_score(y_val, y_pred))
    return pd.DataFrame(results)


@pytest.mark.parametrize("task", discovery.TASKS)
def test_cross_validation_folds_equal_train_and_evaluate(notebook, task):
    df, result = notebook["df"], notebook["result"]
    X = df[notebook["features"]]
    # prepare_data: momentum is incoming_momentum, angle [incoming_theta, incoming_phi].
    y = df["incoming_momentum"] if task == "momentum" else df[["incoming_theta", "incoming_phi"]]
    expected = _train_and_evaluate(X, y, mark="X")
    label = "momentum" if task == "momentum" else "parity"
    folds = result.tasks[task].folds
    assert [f["fold"] for f in folds] == [0, 1, 2, 3, 4]
    for metric, column in (("mae", "MAE_X"), ("mse", "MSE_X"), ("rmse", "RMSE_X"), ("r2", "R2_score_X")):
        got = [f["values"][(metric, label)] for f in folds]
        assert got == pytest.approx(expected[column].tolist(), rel=1e-12, abs=1e-15), metric
    assert sum(f["n_val"] for f in folds) == len(df)


def test_angle_per_label_metrics_wrap_phi_and_keep_theta_raw(notebook):
    df, result = notebook["df"], notebook["result"]
    x = np.array(df[notebook["features"]])
    y = np.array(df[["incoming_theta", "incoming_phi"]])
    train, val = next(KFold(5, shuffle=True, random_state=42).split(x))
    model = xgb.XGBRegressor(objective="reg:squarederror", random_state=42, n_estimators=100,
                             learning_rate=0.1, n_jobs=THREADS).fit(x[train], y[train])
    pred = model.predict(x[val])
    values = result.tasks["angle"].folds[0]["values"]
    assert values[("mae", "theta")] == pytest.approx(mean_absolute_error(y[val, 0], pred[:, 0]), rel=1e-12)
    assert values[("r2", "theta")] == pytest.approx(r2_score(y[val, 0], pred[:, 0]), rel=1e-12)
    wrapped = np.angle(np.exp(1j * (pred[:, 1] - y[val, 1])))
    assert values[("mae", "phi")] == pytest.approx(np.abs(wrapped).mean(), rel=1e-9)
    assert values[("rmse", "phi")] == pytest.approx(np.sqrt((wrapped ** 2).mean()), rel=1e-9)
    assert ("r2", "phi") not in values


def test_a_wrapped_residual_takes_the_short_way_round():
    out = analysis.wrap(np.array([2 * np.pi - 0.1, -2 * np.pi + 0.1, np.pi, -np.pi, 0.0]))
    assert out == pytest.approx([-0.1, 0.1, np.pi, np.pi, 0.0])


# --------------------------------------------------------------------- E3 --


def _evaluate_binary_performance(model, df, features):
    """The notebook's cell 18, verbatim but for ``core.``."""
    class_0_pool = df[df["incoming_momentum"] < 2]
    class_1_pool = df[df["incoming_momentum"] > 10]
    if len(class_1_pool) < 50:
        class_1_pool = df[df["incoming_momentum"] > 2]
    total_samples = 2000
    n_0 = int(total_samples * 0.99)
    n_1 = int(total_samples * 0.01)
    s_0 = class_0_pool.sample(min(n_0, len(class_0_pool)), random_state=42)
    s_1 = class_1_pool.sample(min(n_1, len(class_1_pool)), random_state=42)
    val_special = pd.concat([s_0, s_1]).sample(frac=1, random_state=42)
    y_true_binary = (val_special["incoming_momentum"] > 2).astype(int)
    y_pred_continuous = model.predict(val_special[features])
    y_pred_binary = (y_pred_continuous > 2).astype(int)
    metrics = {
        "accuracy": accuracy_score(y_true_binary, y_pred_binary),
        "balanced_accuracy": balanced_accuracy_score(y_true_binary, y_pred_binary),
        "precision_weighted": precision_score(y_true_binary, y_pred_binary, zero_division=0,
                                              average="weighted"),
        "recall_weighted": recall_score(y_true_binary, y_pred_binary, zero_division=0,
                                        average="weighted"),
        "f1_weighted": f1_score(y_true_binary, y_pred_binary, zero_division=0, average="weighted"),
    }
    return val_special, y_true_binary.to_numpy(), y_pred_continuous, metrics, len(s_0), len(s_1)


def test_the_binary_sample_is_the_notebooks_row_for_row(notebook):
    df, result = notebook["df"], notebook["result"]
    _, val_df = train_test_split(df, test_size=0.2, random_state=42)
    special, y_true, continuous, metrics, n_0, n_1 = _evaluate_binary_performance(
        notebook["shipped"]["momentum"], val_df, notebook["features"])
    b = result.binary
    assert np.array_equal(b.rows, special.index.to_numpy())
    assert np.array_equal(b.y_true, y_true)
    assert np.array_equal(b.value, np.asarray(continuous, dtype=np.float64))
    assert np.array_equal(b.y_pred, (continuous > 2).astype(int))
    assert (b.n_0, b.n_1) == (n_0, n_1) and b.n_0 > 0 and b.n_1 > 0
    assert b.metrics == pytest.approx(metrics, rel=1e-12)


def _wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """The Wilson score interval, written out here rather than taken from metrics."""
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _mover(tn: int, fp: int, fn: int, tp: int) -> tuple[float, float, float]:
    p1, p0 = tp / (tp + fn), tn / (tn + fp)
    (l1, u1), (l0, u0) = _wilson(tp, tp + fn), _wilson(tn, tn + fp)
    ba = (p1 + p0) / 2
    return (ba, max(0.0, ba - 0.5 * np.hypot(p1 - l1, p0 - l0)),
            min(1.0, ba + 0.5 * np.hypot(u1 - p1, u0 - p0)))


def test_the_balanced_accuracy_interval_keeps_a_perfect_class_uncertain():
    """fn = 0: the real electron sample's shape (tp 20, fn 0, tn 1743, fp 237).

    The class-1 recall is 20 / 20 with the Wilson interval [0.839, 1]; a bootstrap of the
    rows drew that class perfect every time and left only class 0's ±0.007. MOVER keeps it.
    """
    got = views.balanced_interval(tn=1743, fp=237, fn=0, tp=20)
    value, lo, hi = _mover(1743, 237, 0, 20)
    assert got["value"] == pytest.approx(0.5 * (1.0 + 1743 / 1980), rel=1e-12)
    assert (got["value"], got["lo"], got["hi"]) == pytest.approx((value, lo, hi), rel=1e-9)
    assert got["lo"] == pytest.approx(0.8592, abs=1e-4) and got["hi"] == pytest.approx(0.9469, abs=1e-4)
    assert got["value"] - got["lo"] > 0.07   # the minority class's own uncertainty


def test_the_balanced_accuracy_interval_in_the_interior():
    got = views.balanced_interval(tn=900, fp=80, fn=6, tp=14)
    value, lo, hi = _mover(900, 80, 6, 14)
    assert (got["value"], got["lo"], got["hi"]) == pytest.approx((value, lo, hi), rel=1e-9)
    assert 0.0 < got["lo"] < got["value"] < got["hi"] < 1.0
    # Asymmetric, as the Wilson limits it is built from.
    assert got["hi"] - got["value"] != pytest.approx(got["value"] - got["lo"], rel=1e-3)
    assert views.balanced_interval(0, 0, 0, 20) == {"value": None, "lo": None, "hi": None}
    perfect = views.balanced_interval(tn=1980, fp=0, fn=0, tp=20)
    assert perfect["value"] == 1.0 and perfect["hi"] == 1.0 and perfect["lo"] < 0.92


# --------------------------------------------------------------------- E4 --


@pytest.mark.parametrize("task", discovery.TASKS)
def test_the_surrogate_tree_is_sklearns(notebook, task):
    """``surrogate_tree_visualization``: the same tree_ arrays, the same fidelity."""
    df, result = notebook["df"], notebook["result"]
    X = df[notebook["features"]]
    y_proxy = notebook["shipped"][task].predict(X)
    tree = DecisionTreeRegressor(max_depth=3, random_state=42).fit(X, y_proxy)
    t = tree.tree_
    nodes = result.tasks[task].tree
    assert len(nodes) == t.node_count <= 15
    assert [n["children_left"] for n in nodes] == t.children_left.tolist()
    assert [n["children_right"] for n in nodes] == t.children_right.tolist()
    assert [n["n_node_samples"] for n in nodes] == t.n_node_samples.tolist()
    assert [n["impurity"] for n in nodes] == pytest.approx(t.impurity.tolist(), abs=1e-12)
    for node, feature, threshold in zip(nodes, t.feature, t.threshold):
        if feature >= 0:
            assert node["feature"] == notebook["features"][feature]
            assert node["threshold"] == threshold
        else:
            assert node["feature"] is None and node["threshold"] is None
    labels = [analysis.LABEL_KEY[label] for label in TASK_LABELS[task]]
    for k, label in enumerate(labels):
        assert [n["values"][label] for n in nodes] == pytest.approx(t.value[:, k, 0].tolist(), rel=1e-12)
    # Each output's within-node variance is the unbiased sample form, ddof = 1 (CLAUDE.md
    # section 2); impurity above stays sklearn's own ddof = 0 variance.
    path = tree.decision_path(X).tocsc()
    proxy2 = np.asarray(y_proxy, dtype=np.float64).reshape(len(X), -1)
    for node in nodes:
        rows = path.indices[path.indptr[node["node_id"]]:path.indptr[node["node_id"] + 1]]
        for k, label in enumerate(labels):
            if rows.size >= 2:
                assert node["variance"][label] == pytest.approx(
                    np.var(proxy2[rows, k], ddof=1), rel=1e-9, abs=1e-12)
            else:
                assert np.isnan(node["variance"][label])
    if task == "momentum":
        # One output: the variance is sklearn's impurity scaled by n / (n − 1).
        for node, impurity, n in zip(nodes, t.impurity, t.n_node_samples):
            if n >= 2:
                assert node["variance"]["momentum"] == pytest.approx(
                    max(impurity, 0.0) * n / (n - 1), rel=1e-9, abs=1e-12)
        assert all(n["circular"] == {} for n in nodes)
    else:
        # φ: beside sklearn's linear mean, the circular mean and R̄ of the rows reaching the node.
        k = labels.index("phi")
        for node in nodes:
            rows = path.indices[path.indptr[node["node_id"]]:path.indptr[node["node_id"] + 1]]
            phi = np.asarray(y_proxy, dtype=np.float64)[rows, k]
            c, s_ = np.cos(phi).sum(), np.sin(phi).sum()
            circ = node["circular"]["phi"]
            assert circ["resultant"] == pytest.approx(np.hypot(c, s_) / rows.size, rel=1e-9)
            assert circ["mean"] == pytest.approx(np.arctan2(s_, c), rel=1e-9, abs=1e-12)
            assert 0.0 <= circ["resultant"] <= 1.0
    fitted = tree.predict(X)
    if task == "angle":
        # φ's fidelity on the circle (D-5): 1 − Σ(1 − cos Δ) / Σ(1 − cos(φ − φ̄)) and mean |Δ|.
        k = labels.index("phi")
        target, mine = np.asarray(y_proxy)[:, k], np.asarray(fitted)[:, k]
        delta = np.angle(np.exp(1j * (mine - target)))
        mean = np.arctan2(np.sin(target).sum(), np.cos(target).sum())
        expected = 1 - np.sum(1 - np.cos(delta)) / np.sum(1 - np.cos(target - mean))
        phi = result.tasks[task].surrogate_outputs["phi"]
        assert phi["r2_circular"] == pytest.approx(expected, rel=1e-9, abs=1e-12)
        assert phi["mae_wrapped"] == pytest.approx(np.mean(np.abs(delta)), rel=1e-9, abs=1e-12)
        assert phi["r2"] == pytest.approx(r2_score(target, mine), rel=1e-12)
        assert "r2_circular" not in result.tasks[task].surrogate_outputs["theta"]
    assert result.tasks[task].surrogate_r2 == pytest.approx(r2_score(y_proxy, fitted), rel=1e-12)
    assert result.tasks[task].surrogate_mae == pytest.approx(mean_absolute_error(y_proxy, fitted),
                                                             rel=1e-12)


# --------------------------------------------------------------------- E5 --


@pytest.mark.parametrize("task", discovery.TASKS)
def test_shipped_importance_equals_feature_importances(notebook, task):
    regressor = notebook["shipped"][task]
    importance = notebook["result"].tasks[task].importance
    norm = [importance[f][0] for f in notebook["features"]]
    assert norm == pytest.approx(regressor.feature_importances_.tolist(), rel=1e-7)
    assert sum(norm) == pytest.approx(1.0, rel=1e-6)
    gain = regressor.get_booster().get_score(importance_type="gain")
    total = sum(gain.values())
    assert [gain.get(f, 0.0) / total for f in notebook["features"]] == pytest.approx(norm, rel=1e-6)
    weight = regressor.get_booster().get_score(importance_type="weight")
    assert {f: v[2] for f, v in importance.items() if v[2]} == weight
    # D-1: total gain is the average gain times the number of splits, as E5's tooltip quotes it.
    total_gain = regressor.get_booster().get_score(importance_type="total_gain")
    for f, v in importance.items():
        assert v[1] * v[2] == pytest.approx(total_gain.get(f, 0.0), rel=1e-5, abs=1e-9)


def test_fold_importances_are_the_refits(notebook):
    folds = notebook["result"].tasks["momentum"].fold_importance
    assert len(folds) == 5
    for gains in folds:
        assert sum(gains.values()) == pytest.approx(1.0, rel=1e-6)
        assert list(gains) == notebook["features"]


# ----------------------------------------------------------------- guards --


def test_too_few_events_and_missing_labels_fail_with_a_reason(notebook):
    data = notebook["data"]
    tiny = analysis.Dataset(event_number=data.event_number[:6], e1_bin=data.e1_bin[:6],
                            labels={k: v[:6] for k, v in data.labels.items()},
                            features={k: v.iloc[:6] for k, v in data.features.items()})
    with pytest.raises(ValueError, match="at least 10"):
        analysis.run(tiny, notebook["models"], nthread=1)
    labels = dict(data.labels)
    labels["incoming_theta"] = labels["incoming_theta"].copy()
    labels["incoming_theta"][3] = np.nan
    broken = analysis.Dataset(event_number=data.event_number, e1_bin=data.e1_bin, labels=labels,
                              features=data.features)
    with pytest.raises(ValueError, match="not finite"):
        analysis.run(broken, notebook["models"], nthread=1)


def test_a_stop_request_cancels_between_steps(notebook):
    with pytest.raises(analysis.Cancelled):
        analysis.run(notebook["data"], notebook["models"], nthread=1, should_stop=lambda: True)


# ------------------------------------------------------ circular fidelity --


def test_circular_fidelity_takes_the_short_way_round_the_seam():
    """A surrogate disagreeing across ±π by a few mrad is nearly perfect on the circle."""
    rng = np.random.default_rng(3)
    # Azimuths around the seam: about half the surrogate's values land on the other side of ±π.
    target = analysis.wrap(np.pi + rng.normal(0.0, 0.3, 500))
    fitted = analysis.wrap(target + rng.normal(0.0, 0.01, 500))
    fid = analysis.circular_fidelity(target, fitted)
    assert fid["r2_circular"] > 0.99 and fid["mae_wrapped"] < 0.02
    # A linear MAE counts the seam crossings as about 2π.
    assert np.mean(np.abs(fitted - target)) > 5 * fid["mae_wrapped"]
    # The one mean direction for every row scores 0; a single direction is undefined.
    from calosrv.stats.circular import circular_mean, resultant_sums

    uniform = rng.uniform(-np.pi, np.pi, 500)
    c, s, _ = resultant_sums(uniform)
    assert analysis.circular_fidelity(uniform, np.full(500, circular_mean(c, s)))["r2_circular"] == \
        pytest.approx(0.0, abs=1e-12)
    assert analysis.circular_fidelity(np.full(4, 1.0), np.full(4, 1.0))["r2_circular"] is None
    assert analysis.circular_fidelity(np.array([]), np.array([])) == {"r2_circular": None,
                                                                       "mae_wrapped": None}


def test_the_colour_domain_comes_from_nodes_of_twenty_rows():
    """D-6: a small leaf beyond the robust nodes' range is counted, not allowed to set it."""
    nodes = [{"n": n, "values": {"momentum": v}} for n, v in
             ((300, 6.5), (150, 2.0), (150, 11.0), (5, 18.0), (2, 0.5), (40, 9.0))]
    basis = views.colour_domain(nodes, "momentum")
    assert basis["domain"] == [2.0, 11.0] and basis["n_nodes"] == 4 and not basis["provisional"]
    assert (basis["n_above"], basis["n_below"]) == (1, 1)
    tiny = views.colour_domain([{"n": 12, "values": {"momentum": v}} for v in (1.0, 3.0)], "momentum")
    assert tiny["domain"] == [1.0, 3.0] and tiny["provisional"]
