"""A stored XGBoost analysis is re-run when what it was computed from changes, and only then.

The stamp (``modelruns/store.py``) is the analysis version, each model file's
sha256, the library versions and the event table's ``event_number``
fingerprint. These tests change a model file's bytes - the same model written
with different whitespace, so the numbers must come back identical - and check
that the analysis is queued again: by the Admin Settings list's rescan while
the server runs, and by the boot check after a restart. A restart with nothing
changed recomputes nothing, and neither does a rebuild of the experiment's
derived tables, whose queue hook finds the stored analysis current.

The test boots its servers itself (``xgb_boot``), one after another on one
data directory, so it owns its fixture rather than sharing ``xgb_client``.
"""

from __future__ import annotations

import json
import shutil
import time

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.modelruns import store
from calosrv.modelruns.analysis import ANALYSIS_VERSION
from conftest import XGB_SOURCE, wait_for_model_runs, xgb_table

ELECTRON = xgb_table(XGB_SOURCE)


def _row(client) -> dict:
    payload = client.get("/api/admin/model-runs").json()
    return {r["table_name"]: r for r in payload["runs"]}[ELECTRON]


def _shas(row) -> dict[str, str]:
    return {r["task"]: r["sha256"] for r in row["runs"]}


def _rewrite(path) -> None:
    """The same model, different bytes: the JSON re-serialised with indentation."""
    document = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")


def _stored_created_at(client):
    with client.app.state.database.read_cursor() as con:
        return con.execute(
            f"SELECT task, created_at FROM {quote(naming.xgb_table('run', ELECTRON))} ORDER BY task"
        ).fetchall()


def _importance(client) -> list:
    return client.get("/api/xgboost", params={"table_name": ELECTRON, "view": "importance",
                                              "task": "momentum"}).json()["features"]


def test_a_changed_model_file_requeues_the_analysis(xgb_boot, xgb_sources, tmp_path):
    data_dir, drop, models = tmp_path / "data", tmp_path / "drop", tmp_path / "models"
    drop.mkdir()
    shutil.copyfile(xgb_sources["electron"], drop / XGB_SOURCE)
    shutil.copytree(xgb_sources["models"] / "xgboost_electron", models / "xgboost_electron")
    env = {"CALOSRV_DATA_DIR": str(data_dir), "CALOSRV_AUTO_INGEST_DIR": str(drop),
           "CALOSRV_MODEL_DIR": str(models)}
    momentum = models / "xgboost_electron" / "standalone_momentum_s1_model.json"
    angle = models / "xgboost_electron" / "standalone_angle_s1_model.json"

    # 1. The first boot ingests the file and analyses it once.
    with xgb_boot(env, wait_ready=2) as client:
        wait_for_model_runs(client, [ELECTRON])
        first = _row(client)
        assert first["status"] == "done", first
        reference = _importance(client)

        # 2. A model file's bytes change while the server runs: the list's rescan finds the
        #    stored analysis stale, shuts the gate and queues it at once.
        _rewrite(momentum)
        rescanned = _row(client)
        assert rescanned["status"] in ("queued", "running"), rescanned
        assert any("momentum model file changed" in r for r in rescanned["stale_reasons"])
        settled = wait_for_model_runs(client, [ELECTRON])
        after = {r["table_name"]: r for r in settled["runs"]}[ELECTRON]
        assert after["status"] == "done" and after["stale_reasons"] == []
        assert _shas(after)["momentum"] != _shas(first)["momentum"]
        assert _shas(after)["angle"] == _shas(first)["angle"]
        assert _importance(client) == reference, "the same model must give the same numbers"

    # 3. The other model changes while the server is down: the boot check queues it.
    _rewrite(angle)
    with xgb_boot(env, wait_ready=2) as client:
        booted = _row(client)
        assert booted["status"] in ("queued", "running", "done"), booted
        assert booted["queued_at"] is not None, "a stale analysis is queued at boot"
        settled = wait_for_model_runs(client, [ELECTRON])
        after_boot = {r["table_name"]: r for r in settled["runs"]}[ELECTRON]
        assert after_boot["status"] == "done"
        assert _shas(after_boot)["angle"] != _shas(after)["angle"]
        assert _importance(client) == reference

    # 4. Nothing changed: the boot finds the analysis current and queues nothing; a rebuild
    #    of the derived tables re-runs the queue hook, which recomputes nothing either.
    with xgb_boot(env, wait_ready=2) as client:
        current = _row(client)
        assert current["status"] == "done" and current["queued_at"] is None, current
        stored = _stored_created_at(client)
        reply = client.post(f"/api/admin/experiments/{ELECTRON}/rebuild")
        assert reply.status_code == 202, reply.text
        poll = reply.json()["poll"]
        for _ in range(240):
            if client.get(poll).json()["status"] in ("done", "failed"):
                break
            time.sleep(0.25)
        assert client.get(poll).json()["status"] == "done"
        for _ in range(240):
            row = _row(client)
            if row["queued_at"] is not None and row["status"] == "done":
                break
            time.sleep(0.1)
        assert row["status"] == "done" and row["queued_at"] is not None, row
        assert _stored_created_at(client) == stored, "a current analysis is not recomputed"


def _stamp(**changes) -> store.Stamp:
    base = dict(analysis_version=ANALYSIS_VERSION, sha256=(("momentum", "a" * 64), ("angle", "b" * 64)),
                versions=(("numpy", "2.4.6"), ("xgboost", "3.2.0")), n_rows=300, fingerprint="f" * 64)
    base.update(changes)
    return store.Stamp(**base)


def test_every_input_of_the_stamp_makes_it_stale():
    current = _stamp()
    assert store.stale_reasons(current, current) == []
    assert store.stale_reasons(current, None) == ["no stored analysis"]
    cases = {
        "analysis version": _stamp(analysis_version=ANALYSIS_VERSION - 1),
        "angle model file changed": _stamp(sha256=(("momentum", "a" * 64), ("angle", "c" * 64))),
        "xgboost 3.1.0 against 3.2.0": _stamp(versions=(("numpy", "2.4.6"), ("xgboost", "3.1.0"))),
        "event table changed": _stamp(fingerprint="0" * 64),
    }
    for expected, stored in cases.items():
        reasons = store.stale_reasons(current, stored)
        assert len(reasons) == 1 and expected in reasons[0], (expected, reasons)


def test_library_versions_are_read_without_importing():
    versions = store.library_versions()
    assert set(versions) == {"xgboost", "scikit-learn", "numpy", "pandas"}
    assert versions["xgboost"] == "3.2.0"
