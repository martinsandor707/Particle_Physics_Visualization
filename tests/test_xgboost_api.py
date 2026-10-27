"""The XGBoost backend end to end: pairing, the job, the tables, the routes and their refusals.

``xgb_client`` (conftest) boots a server with the two-shower baseline and five
aggregates dropped into its drop folder, and models trained in-test in a
models folder of their own. The ingest worker builds each experiment, its queue
hook hands the paired ones to the model-run worker, and the fixture waits for
every analysis to settle - so these tests see the lifecycle a deployment does:

* electron seed 1 pairs and is analysed;
* muon seed 1 pairs with an angle model needing a feature the table lacks;
* proton seed 2 has no models; ``aggregate_events.csv`` names no species;
* pion seed 1 pairs, but six events are too few, so its analysis fails.

Every route is checked against its contract and the 100 KB budget, and the
stored tables against the numbers the routes serve.
"""

from __future__ import annotations

import numpy as np
import pytest

import contract_check
from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.modelruns import analysis
from calosrv.modelruns import jobs as modelruns_jobs
from conftest import (BASELINE_TABLE, XGB_FAILING_SOURCE, XGB_MISSING_FEATURE_SOURCE,
                      XGB_NO_MODELS_SOURCE, XGB_SOURCE, XGB_UNNAMED_SOURCE, xgb_table)

ELECTRON = xgb_table(XGB_SOURCE)
MUON = xgb_table(XGB_MISSING_FEATURE_SOURCE)
PROTON = xgb_table(XGB_NO_MODELS_SOURCE)
PION = xgb_table(XGB_FAILING_SOURCE)
UNNAMED = xgb_table(XGB_UNNAMED_SOURCE)

VIEWS = [("cv", "momentum"), ("cv", "angle"), ("binary", "momentum"), ("surrogate", "momentum"),
         ("surrogate", "angle"), ("importance", "momentum"), ("importance", "angle")]


def _signed_hyphens(node, key: str = "") -> list[str]:
    """Every sentence in a payload that signs a number with a hyphen-minus (U+2212 rule)."""
    from calosrv.text import signed_hyphens

    if isinstance(node, str):
        return [] if key in ("model_file", "sha256", "table_name") else signed_hyphens(node)
    if isinstance(node, dict):
        return [h for k, v in node.items() for h in _signed_hyphens(v, k)]
    if isinstance(node, list):
        return [h for v in node for h in _signed_hyphens(v, key)]
    return []


def _experiments(client) -> dict[str, dict]:
    return {e["table_name"]: e for e in client.get("/api/experiments").json()["experiments"]}


def _ok(response, contract: str) -> dict:
    assert response.status_code == 200, response.text
    assert len(response.content) < 100_000, len(response.content)
    body = response.json()
    contract_check.check(body, contract)
    return body


def _refused(response, capability: str, field: str) -> dict:
    assert response.status_code == 422, response.text
    problem = response.json()
    contract_check.check(problem, "capability_problem")
    assert problem["capability"] == capability and problem["field"] == field, problem
    return problem


# ---------------------------------------------------------------- pairing --


def test_the_catalogue_opens_the_gates_of_the_analysed_experiment_only(xgb_client):
    reply = xgb_client.get("/api/experiments")
    contract_check.check(reply.json(), "experiments")
    assert len(reply.content) < 100_000
    listed = {e["table_name"]: e for e in reply.json()["experiments"]}
    caps = listed[ELECTRON]["capabilities"]
    for gate in ("xgboost", "perf-bins", "pred-truth", "pred-residuals"):
        assert caps["panels"][gate] is True, (gate, caps["reasons"].get(gate))
    runs = caps["model_runs"]
    assert [r["task"] for r in runs] == ["momentum", "angle"]
    assert all(r["status"] == "done" and r["species"] == "electron" and r["seed"] == 1 for r in runs)
    assert runs[1]["labels"] == ["phi", "theta"] and runs[0]["labels"] == ["momentum"]
    assert runs[0]["n_holdout"] > 0 and runs[0]["split_reproduced"] is True
    assert caps["networks"] == []


def test_each_refused_pairing_says_why(xgb_client):
    listed = _experiments(xgb_client)
    reasons = {name: listed[name]["capabilities"]["reasons"]["xgboost"]
               for name in (MUON, PROTON, UNNAMED, BASELINE_TABLE)}
    assert "bogus_feature" in reasons[MUON]
    assert "standalone_momentum_s2_model.json" in reasons[PROTON]
    assert "does not name a species and seed" in reasons[UNNAMED]
    assert "single_shower_events" in reasons[BASELINE_TABLE]
    for name in (MUON, PROTON, UNNAMED):
        caps = listed[name]["capabilities"]
        assert not caps["panels"]["xgboost"]
        assert caps["model_runs"] == [], name
        # Unpaired, the performance cards have nothing to draw: the networks are named.
        assert not caps["panels"]["perf-bins"] and "network" in caps["reasons"]["perf-bins"]
    assert listed[BASELINE_TABLE]["capabilities"]["panels"]["perf-bins"] is True


def test_a_failed_analysis_shuts_the_cards_with_its_error(xgb_client):
    caps = _experiments(xgb_client)[PION]["capabilities"]
    assert not caps["panels"]["xgboost"]
    assert "failed" in caps["reasons"]["xgboost"] and "at least 10" in caps["reasons"]["xgboost"]
    # Paired: the performance cards say exactly what the xgboost gate says.
    for card in ("perf-bins", "pred-truth", "pred-residuals"):
        assert caps["reasons"][card] == caps["reasons"]["xgboost"]
    assert [r["status"] for r in caps["model_runs"]] == ["failed", "failed"]
    assert all(r["n_holdout"] is None for r in caps["model_runs"])


def test_the_admin_list_reports_every_pairing_and_the_models_folder(xgb_client):
    payload = _ok(xgb_client.get("/api/admin/model-runs"), "model_runs_admin")
    runs = {r["table_name"]: r for r in payload["runs"]}
    assert set(runs) == {ELECTRON, MUON, PROTON, PION, UNNAMED}
    assert runs[ELECTRON]["status"] == "done" and runs[ELECTRON]["reason"] is None
    assert runs[ELECTRON]["step"] == runs[ELECTRON]["steps"] == analysis.N_STEPS
    assert [r["task"] for r in runs[ELECTRON]["runs"]] == ["momentum", "angle"]
    assert runs[PION]["status"] == "failed" and "at least 10" in runs[PION]["error"]
    for name in (MUON, PROTON, UNNAMED):
        assert runs[name]["status"] == "unpaired" and runs[name]["reason"]
    rejected = {r["path"]: r["reason"] for r in payload["models"]["rejected"]}
    assert "names the task 'energy'" in rejected["xgboost_electron/standalone_energy_s1_model.json"]
    assert {f["species"] for f in payload["models"]["files"]} == {"electron", "muon", "pion"}
    assert payload["worker"]["busy"] == [] and payload["worker"]["nthread"] >= 1


# ------------------------------------------------------------------ tables --


def _query(xgb_client, sql: str, params=None):
    with xgb_client.app.state.database.read_cursor() as con:
        return con.execute(sql, params or []).fetchall()


def test_the_six_tables_hold_the_analysis(xgb_client):
    tables = naming.xgb_tables(ELECTRON)
    count = {role: _query(xgb_client, f"SELECT count(*) FROM {quote(t)}")[0][0]
             for role, t in tables.items()}
    n_events = _query(xgb_client, f"SELECT count(*) FROM {quote(naming.event_table(ELECTRON))}")[0][0]
    n_val = -(-n_events * 2 // 10)  # ceil(0.2 n), train_test_split's rounding
    assert count["run"] == 2
    assert count["pred"] == n_val * 3            # momentum, then φ and θ
    assert count["fold"] == 5 * 4 + 5 * (4 + 3 + 2)
    assert count["imp"] == 2 * 52 * (1 + 5)
    assert 0 < count["bin"] <= 2000
    assert count["tree"] > 0
    # Each managed table is dropped with its experiment.
    assert set(tables.values()) <= set(naming.all_tables(ELECTRON))
    assert all(naming.experiment_of(t) == ELECTRON for t in tables.values())
    # The validation rows are the split's, and every one carries its own bin.
    pred = _query(xgb_client, f"SELECT DISTINCT event_number FROM {quote(tables['pred'])}")
    assert len(pred) == n_val
    stamp = _query(xgb_client, f"SELECT analysis_version, n_rows, archive_increasing, nthread "
                               f"FROM {quote(tables['run'])}")
    assert all(row[0] == analysis.ANALYSIS_VERSION and row[1] == n_events and row[2] is True
               for row in stamp)


def test_no_analysis_is_stored_for_an_unpaired_or_failed_experiment(xgb_client):
    for name in (MUON, PROTON, UNNAMED, PION):
        found = _query(xgb_client, "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?",
                       [naming.xgb_table("run", name)])
        assert found[0][0] == 0, name


# ------------------------------------------------------------------ routes --


@pytest.mark.parametrize("view,task", VIEWS)
def test_every_view_satisfies_its_contract_and_says_it_is_dataset_wide(xgb_client, view, task):
    params = {"table_name": ELECTRON, "view": view}
    if view != "binary":
        params["task"] = task
    body = _ok(xgb_client.get("/api/xgboost", params=params), f"xgboost_{view}")
    assert body["filtered"] is False and "selection does not apply" in body["selection_note"]
    assert body["run"]["task"] == task and body["run"]["species"] == "electron"
    assert len(body["run"]["sha256"]) == 12
    # A selection is accepted and changes nothing: the notebook computes on everything.
    narrowed = xgb_client.get("/api/xgboost", params={**params, "e1_min": 5.0}).json()
    for key in ("folds", "summary", "nodes", "features", "confusion", "rates"):
        if key in body:
            assert narrowed[key] == body[key], key
    assert _signed_hyphens(body) == []


def test_cv_summary_is_the_mean_of_the_stored_folds_with_its_t_interval(xgb_client):
    body = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "cv",
                                                  "task": "momentum"}).json()
    rows = _query(xgb_client, f"SELECT value FROM {quote(naming.xgb_table('fold', ELECTRON))} "
                              "WHERE task = 'momentum' AND metric = 'rmse' ORDER BY fold")
    values = np.array([r[0] for r in rows])
    s = body["summary"]["rmse"]
    se = values.std(ddof=1) / np.sqrt(5)
    assert s["mean"] == pytest.approx(values.mean(), rel=1e-5)
    assert s["se"] == pytest.approx(se, rel=1e-5) and s["dof"] == 4 and s["t"] == 2.776
    assert s["t95"] == pytest.approx([values.mean() - 2.7764451 * se, values.mean() + 2.7764451 * se],
                                     rel=1e-4)
    assert [f["metrics"]["rmse"] for f in body["folds"]] == pytest.approx(values.tolist(), rel=1e-5)
    assert body["per_label"] is None and body["interval"]["dof"] == 4


def test_cv_angle_carries_parity_and_per_label_blocks(xgb_client):
    body = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "cv",
                                                  "task": "angle"}).json()
    assert body["parity_label"] == "notebook parity: the mean over φ and θ, φ unwrapped"
    assert body["labels"] == ["theta", "phi"]
    assert set(body["per_label"]) == {"theta", "phi"}
    assert "r2" not in body["per_label"]["phi"]["summary"]
    assert body["per_label"]["theta"]["unit"] == "mrad"


def test_binary_counts_and_rates_agree(xgb_client):
    body = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "binary"}).json()
    c = body["confusion"]
    n = c["tn"] + c["fp"] + c["fn"] + c["tp"]
    assert n == body["counts"]["n"] == body["counts"]["class_0"] + body["counts"]["class_1"]
    rates = {r["id"]: r for r in body["rates"]}
    assert rates["accuracy"]["value"] == pytest.approx((c["tn"] + c["tp"]) / n, rel=1e-5)
    assert rates["accuracy"]["interval"]["method"] == "wilson"
    assert rates["balanced_accuracy"]["interval"]["method"] == "bootstrap_percentile"
    for r in body["rates"]:
        if r["interval"]:
            assert 0.0 <= r["interval"]["lo"] <= r["value"] <= r["interval"]["hi"] <= 1.0, r
    assert body["parity"]["accuracy"] == pytest.approx(rates["accuracy"]["value"], rel=1e-5)
    stored = _query(xgb_client, f"SELECT count(*) FROM {quote(naming.xgb_table('bin', ELECTRON))}")
    assert stored[0][0] == n


def test_surrogate_nodes_form_a_depth_three_tree(xgb_client):
    for task, labels in (("momentum", ["momentum"]), ("angle", ["phi", "theta"])):
        body = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "surrogate",
                                                      "task": task}).json()
        nodes = {n["id"]: n for n in body["nodes"]}
        assert len(nodes) <= 15 and nodes[0]["depth"] == 0 and body["labels"] == labels
        for node in nodes.values():
            assert set(node["values"]) == set(labels) == set(node["sd"])
            if node["leaf"]:
                assert node["feature"] is None and node["left"] is None
            else:
                left, right = nodes[node["left"]], nodes[node["right"]]
                assert left["n"] + right["n"] == node["n"]
                assert node["frame"] in ("absolute", "trans", "local", "none")
        if task == "momentum":
            for node in nodes.values():
                assert node["sd"]["momentum"] == pytest.approx(np.sqrt(node["impurity"]), rel=1e-4,
                                                               abs=1e-9)


def test_importance_is_sorted_and_names_each_frame(xgb_client):
    body = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "importance",
                                                  "task": "momentum"}).json()
    shipped = [f["shipped"] for f in body["features"]]
    assert shipped == sorted(shipped, reverse=True) and sum(shipped) == pytest.approx(1.0, rel=1e-4)
    assert body["n_features"] == 52 and [f["rank"] for f in body["features"]] == list(range(1, 53))
    frames = {f["name"]: f["frame"] for f in body["features"]}
    assert frames["num_hits"] == "none" and frames["width_trans"] == "trans"
    assert frames["avg_phi_local"] == "local" and frames["energy_density"] == "absolute"
    for f in body["features"]:
        assert len(f["folds"]) == 5
        if f["fold_t95"][0] is not None:
            assert 0.0 <= f["fold_t95"][0] <= f["fold_mean"] <= f["fold_t95"][1] <= 1.0


# -------------------------------------------------------- the E2 xgb series --


@pytest.mark.parametrize("model", ["energy", "angle"])
def test_model_performance_serves_the_xgboost_series(xgb_client, model):
    body = _ok(xgb_client.get("/api/model-performance", params={
        "table_name": ELECTRON, "slice_by": "momentum_bin", "model": model}),
        "performance_momentum")
    block = body["by_momentum_bin"]
    assert block["source"] == "xgb" and block["frames"] == ["xgb"] and body["cards"] == []
    (series,) = block["series"]
    assert series["code"] == "xgb" and series["label"] == "XGBoost (20 % validation split)"
    assert series["key"] == "xgb:a" and series["network"] == {"model": model, "frame": "xgb"}
    split = block["split"]
    assert split["n_validation"] == sum(series["n"]) + sum(series["n_missing"]) + block["excluded"]["unbinned"]["a"]
    assert split["n_selected"] == body["n_events"] == split["n_validation"] + split["n_training_excluded"]
    if model == "angle":
        assert block["quantity_groups"]["phi"] == ["phi_rmse", "phi_mae", "phi_median_abs"]
        assert {"phi_rmse", "phi_mae", "phi_median_abs"} <= set(block["quantities"]) <= set(block["y_max"])
        assert "phi_bias" not in series and "phi_median_rel" not in series
        assert len(series["phi_rmse"]) == len(block["bins"]["index"])
    else:
        assert "quantity_groups" not in block and not any(k.startswith("phi_") for k in series)
    assert body["meta"]["source"] == "xgb" and body["run"]["task"] == (
        "momentum" if model == "energy" else "angle")


def test_the_selection_applies_to_the_validation_rows(xgb_client):
    full = xgb_client.get("/api/model-performance", params={
        "table_name": ELECTRON, "slice_by": "momentum_bin", "model": "energy"}).json()
    cut = xgb_client.get("/api/model-performance", params={
        "table_name": ELECTRON, "slice_by": "momentum_bin", "model": "energy", "e1_min": 9.5}).json()
    a, b = full["by_momentum_bin"], cut["by_momentum_bin"]
    assert b["split"]["n_validation"] < a["split"]["n_validation"]
    assert b["split"]["n_selected"] < a["split"]["n_selected"]
    # The axis comes from the whole table: it does not move with the selection.
    assert a["bins"] == b["bins"]
    expected = _query(xgb_client, (
        f"SELECT count(*) FROM {quote(naming.xgb_table('pred', ELECTRON))} x "
        f"JOIN {quote(naming.event_table(ELECTRON))} e USING (event_number) "
        "WHERE x.task = 'momentum' AND e.e1 >= 9.5"))[0][0]
    assert b["split"]["n_validation"] == expected


@pytest.mark.parametrize("model,label", [("energy", None), ("angle", None), ("angle", "theta"),
                                         ("angle", "phi")])
def test_prediction_density_serves_the_xgboost_series(xgb_client, model, label):
    params = {"table_name": ELECTRON, "model": model}
    if label:
        params["label"] = label
    body = _ok(xgb_client.get("/api/prediction-density", params=params), "prediction_density")
    assert body["source"] == "xgb" and body["network"]["frame"] == "xgb"
    assert list(body["density"]) == ["a"]
    chosen = label or ("momentum" if model == "energy" else "theta")
    assert body["network"]["label"] == chosen and body["meta"]["source"] == "xgb"
    assert body["n_events"] == body["split"]["n_validation"] <= body["n_selected"]
    if chosen == "phi":
        assert body["axes"]["truth"]["circular"] is True
        assert "wrapped" in body["residual"]["quantity"] and "azimuth" in body["notes"]["angle"]
        residuals = body["residual"]["series"]["a"]
        assert residuals["estimates"]["rmse"]["value"] is not None


# ---------------------------------------------------------------- refusals --


def test_an_unpaired_experiment_is_refused_by_every_xgboost_route(xgb_client):
    problem = _refused(xgb_client.get("/api/xgboost", params={"table_name": MUON, "view": "cv"}),
                       "xgboost", "view")
    assert "bogus_feature" in problem["reason"]
    for params in ({"slice_by": "momentum_bin", "model": "energy"}, {}):
        problem = _refused(xgb_client.get("/api/model-performance",
                                          params={"table_name": UNNAMED, **params}),
                           "networks", "model")
        assert "network" in problem["reason"] and UNNAMED in problem["detail"]
    _refused(xgb_client.get("/api/prediction-density", params={"table_name": PROTON}),
             "networks", "model")


def test_a_two_shower_experiment_has_no_xgboost_views(xgb_client):
    problem = _refused(xgb_client.get("/api/xgboost", params={"table_name": BASELINE_TABLE,
                                                              "view": "importance"}),
                       "xgboost", "view")
    assert "single_shower_events" in problem["reason"]
    reply = xgb_client.get("/api/prediction-density", params={
        "table_name": BASELINE_TABLE, "model": "angle", "label": "phi"})
    assert reply.status_code == 422 and reply.json()["field"] == "label"
    assert "θ only" in reply.json()["detail"]


def test_a_failed_analysis_refuses_with_its_error(xgb_client):
    for path, params, capability, field in (
            ("/api/xgboost", {"view": "binary"}, "xgboost", "view"),
            ("/api/model-performance", {"slice_by": "momentum_bin", "model": "energy"}, "xgboost", "model"),
            ("/api/prediction-density", {"model": "energy"}, "xgboost", "model")):
        problem = _refused(xgb_client.get(path, params={"table_name": PION, **params}), capability, field)
        assert "failed" in problem["reason"] and "at least 10" in problem["reason"]


def test_a_pending_analysis_refuses_with_its_progress(xgb_client):
    from calosrv.db import registry

    with xgb_client.app.state.database.read_cursor() as con:
        record = registry.get_experiment(con, ELECTRON)
    state = modelruns_jobs.lookup(record)
    saved = (state.status, state.step, state.step_label)
    try:
        state.status, state.step, state.step_label = "running", 7, "cross-validation fold 4 of 5 (momentum)"
        problem = _refused(xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "cv"}),
                           "xgboost", "view")
        assert problem["reason"].startswith(f"Analysing: 7 of {analysis.N_STEPS} steps")
        caps = _experiments(xgb_client)[ELECTRON]["capabilities"]
        assert caps["reasons"]["perf-bins"] == caps["reasons"]["xgboost"] == problem["reason"]
        assert [r["status"] for r in caps["model_runs"]] == ["running", "running"]
        _refused(xgb_client.get("/api/model-performance", params={
            "table_name": ELECTRON, "slice_by": "momentum_bin", "model": "angle"}), "xgboost", "model")
        state.status = "queued"
        problem = _refused(xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "cv"}),
                           "xgboost", "view")
        assert "queued" in problem["reason"]
    finally:
        state.status, state.step, state.step_label = saved


@pytest.mark.parametrize("params,field", [
    ({"view": "nope"}, "view"),
    ({"view": "cv", "task": "energy"}, "task"),
    ({"view": "binary", "task": "angle"}, "task"),
])
def test_bad_parameters_name_their_field(xgb_client, params, field):
    reply = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, **params})
    assert reply.status_code == 422 and reply.json()["field"] == field, reply.text


def test_the_aggregate_refuses_what_only_two_showers_serve(xgb_client):
    for params, field in (({"slice_by": "d", "model": "energy"}, "slice_by"),
                          ({"slice_by": "momentum_bin", "model": "segmentation"}, "model")):
        reply = xgb_client.get("/api/model-performance", params={"table_name": ELECTRON, **params})
        assert reply.status_code == 422 and reply.json()["field"] == field, reply.text
    reply = xgb_client.get("/api/prediction-density", params={"table_name": ELECTRON, "model": "energy",
                                                              "label": "phi"})
    assert reply.status_code == 422 and reply.json()["field"] == "label"


# ------------------------------------------------------------- re-analyse --


def test_reanalyse_refuses_what_cannot_be_analysed(xgb_client):
    reply = xgb_client.post(f"/api/admin/model-runs/{MUON}/analyse")
    assert reply.status_code == 422 and "bogus_feature" in reply.json()["reason"]
    reply = xgb_client.post(f"/api/admin/model-runs/{BASELINE_TABLE}/analyse")
    assert reply.status_code == 422 and reply.json()["capability"] == "xgboost"
    assert xgb_client.post("/api/admin/model-runs/no_such_experiment/analyse").status_code == 404


def test_reanalyse_recomputes_the_same_numbers(xgb_client, tmp_path):
    before = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "importance",
                                                    "task": "angle"}).json()
    reply = xgb_client.post(f"/api/admin/model-runs/{ELECTRON}/analyse")
    assert reply.status_code == 202, reply.text
    contract_check.check(reply.json(), "model_runs_admin", at="analysed")
    assert reply.json()["run"]["status"] in ("queued", "running", "done")
    from conftest import wait_for_model_runs

    payload = wait_for_model_runs(xgb_client, [ELECTRON])
    assert {r["table_name"]: r["status"] for r in payload["runs"]}[ELECTRON] == "done"
    after = xgb_client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "importance",
                                                   "task": "angle"}).json()
    assert after["features"] == before["features"] and after["run"] == before["run"]
