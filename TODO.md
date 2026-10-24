# TODO — deferred views and the files that unlock them

calosrv draws only what the ingested data supports and never trains or fits a model (CLAUDE.md §3, "Never fabricate unverified inference outputs"). Every entry below is deferred because a file does not exist in this repository. Each names the views it unlocks, the exact files and format, and what calosrv will check when they arrive.

The figures quoted were measured on the electron files on 2026-10-24 (data characterisation) and 2026-10-25 (the ingest runs of the three-schema release). Every ingest re-measures the ones that matter and writes them into the experiment's ingest report (`GET /api/experiments` → `ingest_report.verification`).

## Summary

| Deferred view | Page | Blocked by | § |
|---|---|---|---|
| E1 XGBoost 5-fold cross-validation table | /models | model-run artefacts | 1 |
| E2, the XGBoost series (the neural-network E2 is live) | /models | holdout predictions | 1 |
| E3 asymmetric 99 : 1 binary evaluation at 2 GeV, Wilson intervals | /models | binary sample, holdout predictions | 1 |
| E4 depth-3 surrogate tree with fidelity R² | /models | surrogate node table | 1 |
| E5 gain feature importances | /models | importances | 1 |
| B1–B3 and feature distributions by particle species | / and /models | proton, pion, muon v3 files | 2 |
| Seed consistency, s1 against s2 | / and /models | s2 files | 3 |
| Fixed-energy class comparisons (1, 2, 5, 10, 20 GeV) | /models | ddsim proton files | 4 |
| C6 species voxels and C11 on two-shower events | /models | hits_all_models schema v2 | 5 |

Until a bundle is loaded, /models shows: "No model-run artefacts are loaded: the XGBoost views E1, E3, E4 and E5 are deferred (see TODO.md)." The catalogue's capability block carries `model_runs: []` and the `xgboost` gate shut, with that reason.

## 1. XGBoost model-run artefacts (E1, E3, E4, E5; the XGBoost series of E2)

### 1.1 What the notebooks keep today

`reference_ipynb_notebooks/xgboost_model_visualization/XGBoost-Reg-{Electron,Muon,Pion,Proton}.ipynb` run identical code (line numbers cite XGBoost-Reg-Proton.ipynb).

- Input `{species}_standalone_N100000_M0_20GeV_reg_balanced_aggr_s{1,2}_v2.csv` (29 columns, :95-96).
- 19 features, in this order (:136-139): width, height, depth, depth_range, volume, num_hits, total_hit_energy, centroid_x, centroid_y, centroid_z, mean_r, std_r, max_r, weighted_r_mean, avg_theta, avg_phi, angular_spread, numerical_density, energy_density.
- Model: `XGBRegressor(objective='reg:squarederror', random_state=42, n_estimators=100, learning_rate=0.1)`. The xgboost and scikit-learn versions are not recorded.
- E1 (:186-227): `KFold(5, shuffle=True, random_state=42)`, one regressor refit per fold.
  - Only the per-fold MAE, MSE, RMSE and R² are kept; fold indices, out-of-fold predictions, fold models and fold importances are discarded.
  - Angle metrics are uniform averages over [incoming_theta, incoming_phi].
- E2–E5 use `train_test_split(test_size=0.2, random_state=42)` (:652).
  - Angle labels are ['incoming_phi', 'incoming_theta'] (:771), the reverse of E1.
  - The E2 angle bars show φ only (:808).
- E3 (:901-953) pools from the 20 % validation split.
  - Class 0 is p < 2 GeV; class 1 is p > 10 GeV (p > 2 if fewer than 50 rows).
  - 1,980 : 20 rows are drawn with `sample(random_state=42)` and shuffled.
  - y_true = p > 2; y_pred = prediction > 2.
  - Only the metric dictionary is kept; the 2,000 rows are discarded. The comment says 95/5, the code does 99/1.
- E4 (:1144-1175): `DecisionTreeRegressor(max_depth=3, random_state=42)` fitted in-sample on all N rows to the split model's predictions.
  - Fidelity R² and MAE are printed (MAE labelled "GeV" even for angle).
  - The function returns None, so the tree is lost.
- E5 (:1257-1258, :1356-1357): `feature_importances_` of the 80/20 model, i.e. normalised gain averaged over the two angle targets. No per-fold importances exist.

### 1.2 Bundle format `calosrv-model-run`, version 1

One directory per (species, seed, task) named `{species}_s{seed}_{task}`, task ∈ {momentum, angle}. Tables may be Parquet or CSV; JSON is UTF-8.

- **`run.json`**: format "calosrv-model-run"; format_version 1; run_id; library "xgboost"; library_version; sklearn_version; python_version; species; seed; task; labels (ordered); label_units (GeV for incoming_momentum, rad for angles); features (the 19, ordered); hyperparameters (`model.get_params()`); input_file {name, bytes, sha256, n_rows}; event_key "event_id"; splits {cv: KFold 5, shuffle, random_state 42; holdout: train_test_split 0.2, random_state 42}; surrogate {kind, max_depth 3, random_state 42, fit_on "all rows", n_fit, outputs, fidelity_r2, mae_vs_booster}.
- **`cv_folds.parquet`** (E1): fold INT8 (0–4), n_train INT32, n_val INT32, mae, mse, rmse, r2 DOUBLE. For the angle task also mae_theta, mae_phi, mse_theta, mse_phi, r2_theta, r2_phi, because the averaged values mix θ with φ.
- **`holdout_predictions.parquet`** (XGBoost E2, E3, prediction density): event_id INT64, incoming_momentum_bin UTINYINT, and `y_true_<label>`, `y_pred_<label>` DOUBLE for each label. One row per validation event (electron: 19,979 per seed).
- **`binary_eval.json`** (E3): {threshold_gev 2.0, class_0 "p < 2", class_1 "p > 10 (p > 2 if fewer than 50 rows)", n_requested [1980, 20], class_0_count, class_1_count, accuracy, balanced_accuracy, precision_weighted, recall_weighted, f1_weighted, zero_division 0, random_state 42}.
- **`binary_sample.parquet`** (E3): order INT32, event_id INT64, y_true UTINYINT, y_pred_value DOUBLE, y_pred UTINYINT — the exact 2,000 rows. pandas RandomState sampling cannot be reproduced in DuckDB.
- **`surrogate_tree.parquet`** (E4): node_id INT32; children_left and children_right INT32 (−1 at leaves); feature INT32 (index into run.json features, −2 at leaves); threshold DOUBLE (−2 at leaves); n_node_samples INT64; weighted_n_node_samples DOUBLE; impurity DOUBLE; `value_<label>` DOUBLE per output. These are sklearn's `tree_` arrays.
- **`importances.parquet`** (E5): feature VARCHAR, importance_type 'gain', value DOUBLE (`feature_importances_`, sums to 1), fold INT8 (NULL for the 80/20 model). Optionally raw_gain, raw_weight, raw_cover from `get_booster().get_score()`.

Optional, only if the training loop changes: `oof_predictions.parquet` (fold, event_id, y_true_*, y_pred_*) and per-fold importance rows (fold 0–4). Neither exists today: the CV loop would have to store each fold's `val_index`, predictions and `feature_importances_`.

### 1.3 What calosrv will check on arrival

- Format and version; the 19 features in order; labels and their order.
- Units: GeV for momentum, rad for angles.
- The notebooks' printed electron values must be reproduced from the tables (other species are in the notebook outputs):
  - E1 IM s1: MAE 0.6794 ± 0.0026, MSE 1.1997 ± 0.0241, RMSE 1.0953 ± 0.0110, R² 0.9639 ± 0.0005.
  - E1 IA s1: 0.0413 ± 0.0009, 0.0638 ± 0.0030, 0.2525 ± 0.0059, 0.9735 ± 0.0014.
  - E3 S1: accuracy 0.908543, balanced 0.953807, weighted precision 0.990945, recall 0.908543, F1 0.943817, 1,970/20.
  - E3 S2: 0.932500, 0.965909, 0.991290, 0.932500, 0.957345, 1,980/20.
  - E4 IM fidelity R²/MAE: S1 0.9372/1.0111, S2 0.9372/1.0121. IA: S1 0.4440/0.2315, S2 0.4463/0.2308.
- event_id ⊂ the aggregated experiment's event_id when the run was trained on an ingested file; otherwise the run is labelled external.

### 1.4 Ingest path (engineering, deferred with the data)

- Tables model_run, model_prediction, model_importance and model_surrogate_node.
- `POST /api/model-runs` (Admin upload) and `GET /api/model-runs[/{id}]`; the capability block's `model_runs` lists what is loaded.
- E3 rates with Wilson intervals and the confusion matrix, recomputed from binary_sample.

### 1.5 Training-data caveat

The notebooks trained on v2 aggregates. The Feature Explorer shows v3 features computed on raw z (verified: the v3 aggregate matches `calc_all_features_v3` on raw z to 5 × 10⁻¹⁴ over all 99,751 events). The v2 z convention is not recorded. For E4/E5 to explain the features calosrv shows, re-train on the v3 files or state the v2 convention.

### 1.6 Exporter (add to the notebooks after training)

```python
import hashlib, json, platform
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
import xgboost

MARK = {"momentum": "IM", "angle": "IA"}

def export_model_run(out_dir, *, species, seed, task, labels, features, input_path, cv_results,
                     split_model, val_df, binary_metrics, binary_rows, surrogate, fidelity_r2,
                     mae_diff, n_fit):
    """Write one calosrv-model-run v1 bundle (TODO.md §1.2). Needs pyarrow; else write .csv."""
    out = Path(out_dir) / f"{species}_s{seed}_{task}"
    out.mkdir(parents=True, exist_ok=True)
    source = Path(input_path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    run = {
        "format": "calosrv-model-run", "format_version": 1,
        "run_id": f"xgboost_{species}_s{seed}_{task}", "library": "xgboost",
        "library_version": xgboost.__version__, "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(), "species": species, "seed": int(seed),
        "task": task, "labels": list(labels),
        "label_units": {l: "GeV" if l == "incoming_momentum" else "rad" for l in labels},
        "features": list(features), "hyperparameters": split_model.get_params(),
        "input_file": {"name": source.name, "bytes": source.stat().st_size,
                       "sha256": digest.hexdigest(), "n_rows": int(n_fit)},
        "event_key": "event_id",
        "splits": {"cv": {"kind": "KFold", "n_splits": 5, "shuffle": True, "random_state": 42},
                   "holdout": {"kind": "train_test_split", "test_size": 0.2, "random_state": 42}},
        "surrogate": {"kind": "DecisionTreeRegressor", "max_depth": 3, "random_state": 42,
                      "fit_on": "all rows", "n_fit": int(n_fit), "outputs": list(labels),
                      "fidelity_r2": float(fidelity_r2), "mae_vs_booster": float(mae_diff)},
    }
    (out / "run.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")

    mark, n = MARK[task], int(n_fit)
    folds = cv_results.rename(columns={f"MAE_{mark}": "mae", f"MSE_{mark}": "mse",
                                       f"RMSE_{mark}": "rmse", f"R2_score_{mark}": "r2"})
    n_val = [n // 5 + (1 if k < n % 5 else 0) for k in range(len(folds))]
    folds.insert(0, "fold", np.arange(len(folds), dtype=np.int8))
    folds.insert(1, "n_train", np.asarray([n - v for v in n_val], dtype=np.int32))
    folds.insert(2, "n_val", np.asarray(n_val, dtype=np.int32))
    folds.to_parquet(out / "cv_folds.parquet", index=False)

    holdout = pd.DataFrame({"event_id": val_df["event_id"].astype("int64"),
                            "incoming_momentum_bin": val_df["incoming_momentum_bin"].astype("uint8")})
    for label in labels:
        holdout[f"y_true_{label}"] = val_df[label].astype("float64")
        holdout[f"y_pred_{label}"] = val_df[f"pred_{label}"].astype("float64")
    holdout.to_parquet(out / "holdout_predictions.parquet", index=False)

    if task == "momentum":
        (out / "binary_eval.json").write_text(json.dumps(binary_metrics, indent=1, default=float),
                                              encoding="utf-8")
        binary_rows.to_parquet(out / "binary_sample.parquet", index=False)

    tree = surrogate.tree_
    nodes = pd.DataFrame({
        "node_id": np.arange(tree.node_count, dtype=np.int32),
        "children_left": tree.children_left.astype(np.int32),
        "children_right": tree.children_right.astype(np.int32),
        "feature": tree.feature.astype(np.int32), "threshold": tree.threshold,
        "n_node_samples": tree.n_node_samples.astype(np.int64),
        "weighted_n_node_samples": tree.weighted_n_node_samples, "impurity": tree.impurity})
    for j, label in enumerate(labels):
        nodes[f"value_{label}"] = tree.value[:, j, 0]
    nodes.to_parquet(out / "surrogate_tree.parquet", index=False)

    booster = split_model.get_booster()
    raw = {kind: booster.get_score(importance_type=kind) for kind in ("gain", "weight", "cover")}
    table = pd.DataFrame({"feature": list(features), "importance_type": "gain",
                          "value": np.asarray(split_model.feature_importances_, dtype=np.float64),
                          "fold": pd.array([pd.NA] * len(features), dtype="Int8")})
    for kind, scores in raw.items():
        table[f"raw_{kind}"] = [float(scores.get(f, 0.0)) for f in features]
    table.to_parquet(out / "importances.parquet", index=False)
    return out
```

Two notebook changes are needed:

- `surrogate_tree_visualization` must return the fitted tree;
- `evaluate_binary_performance` must return the shuffled 2,000-row sample, giving `binary_rows = DataFrame(order, event_id, y_true = (p > 2), y_pred_value = model.predict(X), y_pred = (pred > 2))`.

## 2. Single-shower files for proton, pion and muon

- Hit-level (21-column v3) and aggregated (59-column v3):
  - `proton_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.csv` and `…_aggr_s1_v3.csv`;
  - the same two names for `pion_…` and `muon_…`.
- The notebooks reference proton and pion hit files on the team's storage (`data/simulations/regression-{proton,pion}/`):
  - proton: s1 54,740,548 hits, s2 54,822,842;
  - pion: s1 49,110,973, s2 48,965,087.
- Nothing references a muon hit file or any non-electron 59-column aggregate.
- About 55 M rows is 4.8 times the electron file, roughly 16 GB as CSV. Please export Parquet; calosrv ingests it directly. (On the development workstation, with a 10 GB DuckDB budget, the 11.4 M-row electron hit file ingests in 20 s with a 4.4 GB peak and the 24 M-row two-shower file in 73 s with a 6.5 GB peak.)
- Unlocks:
  - B1–B3 by species; the notebooks give the sampling fraction as proton 1.9999 % (1/SF 50.0026) and pion 2.4597 % (40.6558);
  - species comparisons of C4, C7, C8 and the Feature Explorer;
  - C6/C11 per species.

## 3. Second-seed (s2) files

`electron_standalone_N100000_M0_20GeV_reg_balanced_s2_v3.csv` and `…_aggr_s2_v3.csv`, and the s2 files of §2. They unlock s1-vs-s2 overlays of B2, C4, C7 and D4, and the two-seed layout of E1–E5. The four electron files become four experiments under the long-name rule: a stem longer than 48 characters keeps its first word and as many trailing words as fit, then a six-character digest (`electron_m0_20gev_reg_balanced_s1_v3_25e581`, `electron_m0_20gev_reg_balanced_aggr_s1_v3_82c5d8`, and their s2 twins).

## 4. Fixed-energy ddsim proton files (8-column)

- Files:
  - `ddsim_vertex0_1GeV_proton_N100000_M1GeV.edm4hep.v2.csv`
  - `ddsim_vertex0_2GeV_proton_N100000_M2GeV.edm4hep.v2.csv`
  - `ddsim_vertex0_5GeV_proton_N100000_M5GeV.edm4hep.csv`
  - `ddsim_vertex0_10GeV_proton_N100000_M10GeV.edm4hep.csv`
  - `ddsim_vertex0_20GeV_proton_N100000_M20GeV.edm4hep.csv`
- Columns: event_id, hit_index, x, y, z, hit_energy, contribution_time, contribution_energy. One row per contribution.
- Rows: 4,251,035 / 11,312,306 / 39,832,991 / 97,198,362 / 212,623,531. Events: 100,000 / 100,000 / 96,844 / 99,709 / 99,989.
- Needed only for discrete fixed-energy classes beyond `incoming_momentum_bin` slicing.
- A fourth input schema would be required:
  - contributions folded to cells (the notebook's drop_duplicates on event_id, x, y, z, hit_energy);
  - the contribution_time ≤ 100,000 cut;
  - the energy taken from the file name;
  - no incident angles.

## 5. Two-shower species columns (hits_all_models schema v2)

- Append per hit: `particle_type` (text), `is_secondary` (0/1), and optionally `parent_type`, `daughter_type` (';'-joined).
- Append per event, repeated per hit: `particle_type_A`, `particle_type_B`.
- calosrv would accept it as hits_all_models version 2 beside version 1.
- Unlocks C6 and C11 on two-shower events (today the species views are shut on two-shower data and say why) and per-particle comparisons.

## 6. Questions for the physics team

1. `High_energy_notebook_proton_pion-v5.ipynb` cites `High_energy_notebook_electron_muon.ipynb`, which is not in the repository.
2. The last column of the 59-column aggregate, `energy`, is 1{incoming_momentum ≥ 2 GeV}.
   - Counts: 0 in 9,795 events, 1 in 89,956 (re-measured at every ingest).
   - The largest p with 0 is 1.99831; the smallest p with 1 is 2.00002.
   - calosrv stores it as the class label `energy_class` and never calls it an energy. Please confirm, and consider renaming it in v4.
3. The v2 29-column aggregates and their gnn_logical_node, gnn_arith_node, gnn_msg_log_sum and gnn_msg_arith_sum columns are not supported; no definition exists in core.py. Supply definitions, or re-export as v3.
4. The v3 aggregates use raw z (first layer 3662.4 mm), while the notebooks' hit-level analyses subtract core.SHIFT_Z = 3649. calosrv keeps raw z everywhere and shows "z − 3649 mm" only as a labelled display row. Confirm raw z for v3, and state the v2 convention.
5. The eps = 1e-6 floors produce densities up to:
   - 2.07e9 absolute (83 events above 1e3);
   - 9.76e10 trans (256 events);
   - 6.59e4 local (69 events).
   Intended, or should a degenerate extent be NaN?
6. avg_phi* are arithmetic means of an azimuth, and angular_spread adds SD(φ). Most of the angular_spread tail above 0.5 rad is the ±π branch cut. calosrv shows them for parity, hatched, beside a circular mean and R̄; consider those in v4.
7. C11 for electrons: 73.83 % of events have no is_secondary = 0 row, rising from 64 % in bin 1 to 80 % in bin 18. The notebooks give 27.39 % for proton and 25.35 % for pion. What does is_secondary = 0 tag for electrons?
8. The aggregate omits the 249 single-hit events (193 in bin 0), so its bins hold 4,807–5,000 events. Intended?
9. Units: energy and momentum GeV, angles rad, positions mm. earliest_contribution_time runs 12.2–52,328.7 — ns?
10. The xgboost and scikit-learn versions of the published runs.

## 7. Engineering deferred with the data

- The model-run import and the E1/E3/E4/E5 panels (§1.4).
- Species and seed layouts (§2, §3), the fixed-energy schema (§4), schema v2 (§5).
