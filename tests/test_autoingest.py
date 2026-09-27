"""The drop folder: each new file becomes an experiment once; nothing existing is touched.

The scan's decisions are checked against the ingested database with a job
store that only records what it is given, so every outcome can be provoked
without running an ingest. A booted server then shows the whole loop: a boot
queues the file, the worker ingests it, and the next scan skips it.
"""

from __future__ import annotations

import csv
import dataclasses
import logging
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from calosrv.db import naming
from calosrv.errors import ValidationError
from calosrv.ingest import autoingest

from conftest import SEED_CSV, TABLE, clean_boot_env

OLD = time.time() - 3600  # long settled


class RecordingStore:
    """A job store that queues nothing: it records what the scan submits."""

    def __init__(self, active=()):
        self.submitted: list[dict] = []
        self.active = set(active)

    def active_names(self) -> set[str]:
        return set(self.active)

    def submit(self, **kwargs):
        self.submitted.append(kwargs)
        return SimpleNamespace(job_id=f"job{len(self.submitted)}")


@pytest.fixture
def drop(tmp_path):
    folder = tmp_path / "ingest"
    folder.mkdir()
    return folder


def _put(folder: Path, name: str, source: Path = SEED_CSV, mtime: float = OLD) -> Path:
    path = folder / name
    shutil.copyfile(source, path)
    os.utime(path, (mtime, mtime))
    return path


def _v37(folder: Path, name: str = "old_v37.csv") -> Path:
    path = folder / name
    with path.open("w", newline="") as handle:
        csv.writer(handle).writerow(["event_number", "x", "energy", "voxel_fA_pred"])
    os.utime(path, (OLD, OLD))
    return path


def _scan(ingested, drop, store=None, settle_s: int = 30):
    settings = dataclasses.replace(ingested["settings"], auto_ingest_dir=drop,
                                   auto_ingest_settle_s=settle_s)
    store = store or RecordingStore()
    report = autoingest.scan(ingested["database"], settings, store)
    return report, store, {e.file: e for e in report.entries}


# ---------------------------------------------------------------- names --


@pytest.mark.parametrize("stem, name", [
    ("production_20k", "production_20k"),
    ("Production-20k (v2)", "production_20k_v2"),
    ("hits all models", "hits_all_models"),
    ("2026_run", "exp_2026_run"),
    ("__edge__", "edge"),
    ("a" * 60, "a" * 48),
])
def test_a_file_name_becomes_an_experiment_name(stem, name):
    assert naming.derive_experiment_name(stem) == name


@pytest.mark.parametrize("stem", ["experiment", "run_s10", "---", ""])
def test_a_name_the_rules_refuse_is_not_bent_into_another(stem):
    with pytest.raises(ValidationError):
        naming.derive_experiment_name(stem)


# ------------------------------------------------------------- outcomes --


def test_a_new_file_is_queued_as_a_new_experiment(ingested, drop):
    _put(drop, "run7.csv")
    report, store, entries = _scan(ingested, drop)
    assert report.enabled and report.scanned_at
    assert entries["run7.csv"].action == "submitted"
    assert entries["run7.csv"].job_id == "job1"
    (submitted,) = store.submitted
    assert (submitted["table_name"], submitted["mode"], submitted["display_name"]) == (
        "run7", "create_new", "run7")
    assert submitted["delete_source"] is False, "the file belongs to whoever dropped it"
    assert submitted["staged"].path == drop / "run7.csv"


def test_an_existing_experiment_is_skipped_and_logged_as_specified(ingested, drop, caplog):
    _put(drop, f"{TABLE}.csv")
    with caplog.at_level(logging.INFO, logger="calosrv.ingest.autoingest"):
        _, store, entries = _scan(ingested, drop)
    assert entries[f"{TABLE}.csv"].action == "exists"
    assert store.submitted == []
    assert (f"Table '{TABLE}' already exists in database catalog. "
            "Skipping automatic ingestion.") in caplog.messages


def test_tables_without_a_registry_row_also_count_as_existing(ingested, drop):
    stray = naming.event_table("stray_tables")
    with ingested["database"].write_lock() as con:
        con.execute(f'CREATE TABLE "{stray}" AS SELECT 1 AS x')
    try:
        _put(drop, "stray_tables.csv")
        _, store, entries = _scan(ingested, drop)
        assert entries["stray_tables.csv"].action == "exists"
        assert "without a registry row" in entries["stray_tables.csv"].detail
        assert store.submitted == []
    finally:
        with ingested["database"].write_lock() as con:
            con.execute(f'DROP TABLE IF EXISTS "{stray}"')


def test_a_name_with_a_job_under_way_is_not_queued_twice(ingested, drop):
    _put(drop, "busy.csv")
    _, store, entries = _scan(ingested, drop, RecordingStore(active={"busy"}))
    assert entries["busy.csv"].action == "queued"
    assert store.submitted == []


def test_a_file_already_archived_under_another_name_is_not_ingested_again(ingested, drop):
    """The demonstration file is the ingested experiment's source: same name, same bytes."""
    _put(drop, SEED_CSV.name)
    _, store, entries = _scan(ingested, drop)
    entry = entries[SEED_CSV.name]
    assert entry.action == "same_source"
    assert f"'{TABLE}'" in entry.detail
    assert store.submitted == []


def test_a_file_still_being_written_waits_for_the_next_scan(ingested, drop):
    _put(drop, "arriving.csv", mtime=time.time())
    _, store, entries = _scan(ingested, drop, settle_s=30)
    assert entries["arriving.csv"].action == "unsettled"
    assert store.submitted == []


def test_hidden_temporary_and_other_files_are_passed_over(ingested, drop):
    for name in (".hidden.csv", "~lock.csv", "copying.csv.part", "notes.txt", "readme.md"):
        _put(drop, name)
    (drop / "nested").mkdir()
    _put(drop / "nested", "deeper.csv")
    report, store, _ = _scan(ingested, drop)
    assert report.entries == [] and store.submitted == []


def test_a_file_that_fails_its_checks_is_reported_not_queued(ingested, drop, part):
    _v37(drop)
    truncated = drop / "half.parquet"
    truncated.write_bytes(part.read_bytes()[: part.stat().st_size // 2])
    os.utime(truncated, (OLD, OLD))
    _, store, entries = _scan(ingested, drop)
    assert entries["old_v37.csv"].action == "rejected"
    assert "retired v37" in entries["old_v37.csv"].detail
    assert entries["half.parquet"].action == "rejected"
    assert "no footer" in entries["half.parquet"].detail
    assert store.submitted == []


def test_two_files_with_one_name_queue_only_the_first(ingested, drop, part):
    _put(drop, "twin.csv")
    _put(drop, "twin.parquet", source=part)
    _, store, entries = _scan(ingested, drop)
    assert entries["twin.csv"].action == "submitted"
    assert entries["twin.parquet"].action == "name_collision"
    assert len(store.submitted) == 1


def test_a_reserved_name_is_reported(ingested, drop):
    _put(drop, "experiment.csv")
    _, store, entries = _scan(ingested, drop)
    assert entries["experiment.csv"].action == "invalid_name"
    assert store.submitted == []


def test_the_scan_is_off_without_a_folder_and_says_why(ingested, tmp_path):
    settings = dataclasses.replace(ingested["settings"], auto_ingest_dir=None)
    report = autoingest.scan(ingested["database"], settings, RecordingStore())
    assert (report.enabled, report.reason) == (False, "CALOSRV_AUTO_INGEST_DIR is not set.")
    settings = dataclasses.replace(settings, auto_ingest_dir=tmp_path / "absent")
    report = autoingest.scan(ingested["database"], settings, RecordingStore())
    assert report.enabled is False and "does not exist" in report.reason


@pytest.fixture(scope="module")
def part(ingested) -> Path:
    from calosrv.db import archive

    return archive.part_paths(ingested["settings"], ingested["table"])[0]


# -------------------------------------------------- a booted server loop --


@pytest.fixture(scope="module")
def auto_client(tmp_path_factory):
    """A server whose drop folder holds one new dataset and one retired-schema file."""
    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()
    folder = tmp_path_factory.mktemp("drop")
    _put(folder, "dropped_run.csv")
    _v37(folder)
    os.environ["CALOSRV_DATA_DIR"] = str(tmp_path_factory.mktemp("auto-data"))
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)
    os.environ["CALOSRV_AUTO_INGEST_DIR"] = str(folder)

    with TestClient(create_app(load_settings())) as client:
        for _ in range(240):
            names = {e["table_name"]: e["status"]
                     for e in client.get("/api/experiments").json()["experiments"]}
            if names.get("dropped_run") in ("ready", "failed"):
                break
            time.sleep(0.25)
        yield client

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()


def test_a_boot_ingests_the_new_file_and_reports_the_rest(auto_client):
    names = {e["table_name"]: e for e in auto_client.get("/api/experiments").json()["experiments"]}
    assert names["dropped_run"]["status"] == "ready"
    assert names["dropped_run"]["display_name"] == "dropped_run"
    report = auto_client.get("/api/admin/config").json()["auto_ingest"]
    assert report["enabled"] is True
    actions = {e["file"]: e["action"] for e in report["entries"]}
    assert actions == {"dropped_run.csv": "submitted", "old_v37.csv": "rejected"}


def test_scanning_again_changes_nothing(auto_client):
    before = auto_client.get("/api/upload").json()["jobs"]
    response = auto_client.post("/api/admin/auto-ingest/scan")
    assert response.status_code == 200, response.text
    actions = {e["file"]: e["action"] for e in response.json()["entries"]}
    assert actions == {"dropped_run.csv": "exists", "old_v37.csv": "rejected"}
    assert auto_client.get("/api/upload").json()["jobs"] == before, "no job may be queued"


def test_scan_now_is_refused_when_the_scanner_is_off(client):
    response = client.post("/api/admin/auto-ingest/scan")
    assert response.status_code == 409
    assert "CALOSRV_AUTO_INGEST_DIR" in response.json()["detail"]
