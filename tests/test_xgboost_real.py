"""Opt-in checks of the XGBoost analysis on the real s1 aggregates and the shipped models.

Skipped unless the four ``ingest/<species>_standalone_..._aggr_s1_v3.parquet``
files are present and ``CALOSRV_XGB_REAL=1``: they read 100,000-event files
and refit full-size models (seconds each), which the committed suite must not.
The Parquet files are read directly, read-only, in file order - the order the
notebook read its CSV - so no database is involved.

* The refit on the reproduced 80 % recreates the shipped electron momentum
  model exactly (max |Δpred| = 0), on the thread count the service uses: the
  claim the stored cross-validation rests on.
* The split check passes for every species and both tasks: seed 42's
  validation / training MSE exceeds the largest of 99 other seeds' by the
  task's margin (``analysis.SPLIT_MARGIN``); row-permuted errors fail it.
* Each angle output predicts its own label better than the other one.
* The whole analysis runs on the electron file; its duration is printed, and
  E3's balanced accuracy keeps the perfectly classified minority class's
  uncertainty (Newcombe MOVER; the bootstrap it replaced gave [0.933, 0.947]).

    CALOSRV_XGB_REAL=1 .venv/bin/python -m pytest -q -s tests/test_xgboost_real.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import duckdb
import numpy as np
import pytest

from calosrv.config import model_threads
from calosrv.modelruns import analysis, discovery
from calosrv.modelruns.pairing import TASK_LABELS

ROOT = Path(__file__).resolve().parent.parent
SPECIES = ("electron", "muon", "pion", "proton")
FILES = {s: ROOT / "ingest" / f"{s}_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet"
         for s in SPECIES}

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_XGB_REAL") != "1" or not all(p.is_file() for p in FILES.values()),
    reason="opt-in: set CALOSRV_XGB_REAL=1 with the four s1 aggregates in ingest/",
)


def _read(species: str):
    con = duckdb.connect()
    try:
        path = str(FILES[species]).replace("'", "''")
        return con.execute(f"SELECT * FROM read_parquet('{path}')").df()
    finally:
        con.close()


def _models(species: str) -> dict[str, discovery.ModelFile]:
    catalogue = discovery.scan(ROOT / "xgboost_models")
    models = {task: catalogue.get(species, 1, task) for task in discovery.TASKS}
    assert all(models.values()), catalogue.as_dict()
    return models


def _dataset(species: str) -> tuple[analysis.Dataset, dict[str, discovery.ModelFile]]:
    df = _read(species)
    assert df["event_id"].is_monotonic_increasing, "the analysis reads event_number order"
    models = _models(species)
    data = analysis.Dataset(
        event_number=df["event_id"].to_numpy(dtype=np.int64),
        e1_bin=df["incoming_momentum_bin"].to_numpy(dtype=np.float64),
        labels={label: df[label].to_numpy(dtype=np.float64)
                for labels in TASK_LABELS.values() for label in labels},
        features={task: df[list(m.feature_names)] for task, m in models.items()},
    )
    return data, models


def test_the_refit_on_the_reproduced_split_is_the_shipped_electron_model():
    import xgboost as xgb

    data, models = _dataset("electron")
    frame = data.features["momentum"]
    train, _ = analysis.split_indices(data.n)
    refit = xgb.XGBRegressor(**analysis.HYPERPARAMETERS, n_jobs=model_threads())
    refit.fit(frame.iloc[train], data.labels["incoming_momentum"][train])
    shipped = analysis.load_model(models["momentum"], model_threads())
    delta = np.abs(refit.predict(frame) - shipped.predict(frame))
    assert float(delta.max()) == 0.0


@pytest.mark.parametrize("species", SPECIES)
def test_the_split_check_passes_for_every_species(species):
    data, models = _dataset(species)
    for task, labels in TASK_LABELS.items():
        regressor = analysis.load_model(models[task], model_threads())
        pred = np.asarray(regressor.predict(data.features[task]), dtype=np.float64)
        truth = np.column_stack([data.labels[label] for label in labels])
        ratios = analysis.split_ratios(pred, truth)
        split = analysis.split_summary(ratios, task)
        print(f"\n{species} {task}: ratio_42 {split['ratio_42']:.4g}, max of 99 others "
              f"{split['max_others']:.4g} (seed {split['seed_of_max']}), headroom "
              f"{split['headroom']:.4g} against the margin {split['margin']:g}")
        assert analysis.reproduced(ratios, task), (species, task, split)
        # Row-permuted errors: a split the model was not trained on fails the check.
        n = truth.shape[0]
        e2 = ((pred.reshape(n, -1) - truth.reshape(n, -1)) ** 2).mean(axis=1)
        rng = np.random.default_rng(1)
        splits = [analysis.split_indices(n, seed) for seed in (42, *analysis.CHECK_SEEDS)]
        passed = 0
        for _ in range(20):
            e = e2[rng.permutation(n)]
            permuted = {seed: e[va].mean() / e[tr].mean()
                        for seed, (tr, va) in zip((42, *analysis.CHECK_SEEDS), splits)}
            passed += analysis.reproduced(permuted, task)
        assert passed == 0, (species, task, passed)
        if task == "angle":
            errors = analysis.output_order(task, pred, truth, labels)
            print(f"{species} output order: {errors}")
            analysis.check_output_order(task, errors)


def test_the_whole_analysis_runs_on_the_electron_file():
    data, models = _dataset("electron")
    started = time.perf_counter()
    result = analysis.run(data, models, nthread=model_threads())
    elapsed = time.perf_counter() - started
    print(f"\nelectron analysis: {elapsed:.1f} s on {model_threads()} threads; steps "
          + ", ".join(f"{k} {v:.1f} s" for k, v in result.timings.items()))
    assert result.n_rows == data.n
    for task in discovery.TASKS:
        t = result.tasks[task]
        assert t.split_reproduced and len(t.folds) == 5
        assert len(t.tree) <= 15 and t.surrogate_r2 is not None
    assert result.binary.n_0 + result.binary.n_1 == 2000
    from calosrv.modelruns import views

    b = result.binary
    tp = int(((b.y_true == 1) & (b.y_pred == 1)).sum())
    fn = int(((b.y_true == 1) & (b.y_pred == 0)).sum())
    tn = int(((b.y_true == 0) & (b.y_pred == 0)).sum())
    fp = int(((b.y_true == 0) & (b.y_pred == 1)).sum())
    balanced = views.balanced_interval(tn, fp, fn, tp)
    print(f"E3: tp {tp} fn {fn} tn {tn} fp {fp}; balanced accuracy {balanced['value']:.4f} "
          f"[{balanced['lo']:.4f}, {balanced['hi']:.4f}]")
    assert balanced["lo"] < 0.9 < balanced["value"]
    # E4: φ's nodes carry the circular mean and R̄ of the booster's predictions.
    angle = result.tasks["angle"]
    assert all(0.0 <= n["circular"]["phi"]["resultant"] <= 1.0 for n in angle.tree)
    print("E4 fidelity per output:", angle.surrogate_outputs)
    importance = result.tasks["momentum"].importance
    top = max(importance, key=lambda f: importance[f][0])
    assert top == "num_hits"
