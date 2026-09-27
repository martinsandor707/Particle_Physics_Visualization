"""Replacing an experiment happens only when asked for, and never costs a good one for a bad file.

``create_new`` used to drop an existing experiment and its archive before
reading the new file, silently. It is now refused with 409 unless
``force_reingest`` is set, and every check of the new file still runs before
anything is dropped.
"""

from __future__ import annotations

import contextlib
import csv
import json

import pytest

from calosrv.db import archive, naming, registry
from calosrv.errors import ConflictError, ExperimentExistsError, IngestError
from calosrv.ingest import pipeline

from conftest import SEED_CSV


@contextlib.contextmanager
def _existing(ingested, name: str):
    """An experiment of ``name`` ingested from the demonstration file, dropped afterwards."""
    from calosrv.db.bootstrap import drop_experiment

    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        pipeline.run_ingest(con, settings, name, SEED_CSV, source_name="first.csv",
                            build_sample=False)
    try:
        yield
    finally:
        with database.write_lock() as con:
            drop_experiment(con, name, settings)


def _manifest(ingested, name):
    return archive.read_manifest(ingested["settings"], name).as_dict()


def test_create_new_onto_an_existing_experiment_is_refused_and_changes_nothing(ingested):
    database, settings = ingested["database"], ingested["settings"]
    with _existing(ingested, "guarded"):
        before = _manifest(ingested, "guarded")
        with pytest.raises(ExperimentExistsError) as info:
            with database.write_lock() as con:
                pipeline.run_ingest(con, settings, "guarded", SEED_CSV, build_sample=False)
        assert info.value.status_code == 409
        assert info.value.extra == {"table_name": "guarded", "existing_status": "ready"}
        assert "--force-reingest" in info.value.detail
        assert _manifest(ingested, "guarded") == before
        with database.read_cursor() as con:
            assert registry.get_experiment(con, "guarded").is_ready


def test_force_reingest_replaces_the_experiment(ingested):
    database, settings = ingested["database"], ingested["settings"]
    with _existing(ingested, "replaced"):
        with database.write_lock() as con:
            result = pipeline.run_ingest(con, settings, "replaced", SEED_CSV,
                                         source_name="second.csv", build_sample=False,
                                         force_reingest=True)
        assert result.ok
        assert result.record.source_files == ["second.csv"]
        assert [p["source_name"] for p in _manifest(ingested, "replaced")["parts"]] == [
            "second.csv"]


def test_a_forced_reingest_of_a_refused_file_keeps_the_old_experiment(ingested, tmp_path):
    """The file's checks run before the drop, so a bad file costs nothing."""
    bad = tmp_path / "bad.csv"
    with bad.open("w", newline="") as handle:
        csv.writer(handle).writerow(["alpha", "beta"])
    database, settings = ingested["database"], ingested["settings"]
    with _existing(ingested, "survivor"):
        before = _manifest(ingested, "survivor")
        with pytest.raises(IngestError, match="does not match"):
            with database.write_lock() as con:
                pipeline.run_ingest(con, settings, "survivor", bad, force_reingest=True)
        assert _manifest(ingested, "survivor") == before
        with database.read_cursor() as con:
            assert registry.get_experiment(con, "survivor").is_ready


def test_tables_without_a_registry_row_count_as_existing(ingested):
    """A crash can leave tables behind; replacing them silently is still clobbering."""
    database, settings = ingested["database"], ingested["settings"]
    stray = naming.proj_table("orphaned")
    with database.write_lock() as con:
        con.execute(f'CREATE TABLE "{stray}" AS SELECT 1 AS x')
    try:
        with pytest.raises(ExperimentExistsError, match="without a registry row"):
            with database.write_lock() as con:
                pipeline.run_ingest(con, settings, "orphaned", SEED_CSV, build_sample=False)
    finally:
        with database.write_lock() as con:
            con.execute(f'DROP TABLE IF EXISTS "{stray}"')


def test_an_archive_without_a_registry_row_counts_as_existing(ingested):
    database, settings = ingested["database"], ingested["settings"]
    path = archive.archive_path(settings, "archived_only")
    path.mkdir(parents=True)
    try:
        with pytest.raises(ExperimentExistsError, match="an archive without a registry row"):
            with database.write_lock() as con:
                pipeline.run_ingest(con, settings, "archived_only", SEED_CSV,
                                    build_sample=False)
    finally:
        path.rmdir()


# -------------------------------------------------------- route checks --


def test_a_name_with_a_queued_job_is_refused_even_when_forced(ingested, monkeypatch):
    from calosrv.api.routes_upload import _check_target
    from calosrv.ingest import jobs as jobs_mod

    database, settings = ingested["database"], ingested["settings"]
    store = jobs_mod.get_job_store(database)
    monkeypatch.setattr(store, "active_names", lambda: {"busy_name"})
    with pytest.raises(ConflictError, match="already queued or running"):
        _check_target(database, settings, "busy_name", "create_new", True)
    # Nothing is queued under another name, and nothing exists there.
    _check_target(database, settings, "free_name", "create_new", False)


def test_the_route_check_refuses_and_forcing_passes(ingested):
    from calosrv.api.routes_upload import _check_target

    database, settings = ingested["database"], ingested["settings"]
    with _existing(ingested, "route_guarded"):
        with pytest.raises(ExperimentExistsError):
            _check_target(database, settings, "route_guarded", "create_new", False)
        _check_target(database, settings, "route_guarded", "create_new", True)
        _check_target(database, settings, "route_guarded", "append", False)


def test_an_upload_onto_an_existing_name_is_a_409_problem(client):
    response = client.post(
        "/api/upload",
        files={"file": ("again.csv", SEED_CSV.read_bytes(), "text/csv")},
        data={"table_name": "experiment_baseline", "mode": "create_new"},
    )
    assert response.status_code == 409
    problem = response.json()
    assert problem["type"] == "/problems/experiment-exists"
    assert (problem["table_name"], problem["existing_status"]) == ("experiment_baseline", "ready")
    assert "force_reingest" in problem["detail"]


def test_a_forced_upload_replaces_the_experiment(client):
    import time

    response = client.post(
        "/api/upload",
        files={"file": ("again.csv", SEED_CSV.read_bytes(), "text/csv")},
        data={"table_name": "experiment_baseline", "mode": "create_new",
              "force_reingest": "true"},
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["force_reingest"] is True
    for _ in range(120):
        job = client.get(f"/api/upload/{job['job_id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job


# ------------------------------------------------------------------ CLI --


def test_the_cli_forwards_force_reingest_to_a_running_server(monkeypatch, tmp_path):
    """Delegated mode posts the flag with the path; the server applies the rule."""
    import io
    import urllib.error

    from calosrv.ingest import cli

    sent = {}

    def refuse(request, timeout=None):  # the server's 409, without a server
        sent["body"] = request.data.decode()
        raise urllib.error.HTTPError(request.full_url, 409, "Conflict", {},
                                     io.BytesIO(json.dumps({"detail": "exists"}).encode()))

    monkeypatch.setattr(cli.urllib.request, "urlopen", refuse)
    args = cli.build_parser().parse_args(
        ["--input", str(SEED_CSV), "--table", "cli_target", "--force-reingest"])
    assert args.force_reingest is True
    assert cli.run_delegated(args, "http://127.0.0.1:1", SEED_CSV) == 2
    assert "force_reingest=true" in sent["body"]
    unforced = cli.build_parser().parse_args(["--input", str(SEED_CSV), "--table", "cli_target"])
    assert unforced.force_reingest is False
