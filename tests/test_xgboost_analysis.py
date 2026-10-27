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


def test_the_split_check_is_the_probe_s(notebook):
    df, result = notebook["df"], notebook["result"]
    for task, labels in TASK_LABELS.items():
        pred = notebook["shipped"][task].predict(df[notebook["features"]])
        y = df[list(labels)].to_numpy()
        e2 = ((pred.reshape(len(df), -1) - y) ** 2).mean(axis=1)
        ratios = {}
        for seed in (42, 0, 7):
            tr, va = train_test_split(np.arange(len(df)), test_size=0.2, random_state=seed)
            ratios[seed] = e2[va].mean() / e2[tr].mean()
        assert result.tasks[task].split_ratios == pytest.approx(ratios, rel=1e-12)
        assert result.tasks[task].split_reproduced == (ratios[42] > max(ratios[0], ratios[7]))
    # The fixture's models were trained on the reproduced 80 %, so the check passes.
    assert result.tasks["momentum"].split_reproduced


def test_the_flag_needs_the_42_ratio_above_both_others():
    assert analysis.reproduced({42: 1.3, 0: 1.0, 7: 1.1})
    assert not analysis.reproduced({42: 1.05, 0: 1.0, 7: 1.1})


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


def test_the_balanced_accuracy_bootstrap_is_seeded_and_brackets_the_value():
    first = views.balanced_bootstrap(tn=900, fp=80, fn=6, tp=14)
    assert first == views.balanced_bootstrap(tn=900, fp=80, fn=6, tp=14)
    value = 0.5 * (14 / 20 + 900 / 980)
    assert first["lo"] < value < first["hi"] and first["n_undefined"] == 0
    assert views.balanced_bootstrap(0, 0, 0, 20)["lo"] is None


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
    if task == "momentum":
        # One output: the per-label variance is sklearn's impurity itself.
        assert [n["variance"]["momentum"] for n in nodes] == pytest.approx(
            np.maximum(t.impurity, 0).tolist(), rel=1e-9, abs=1e-12)
    fitted = tree.predict(X)
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
