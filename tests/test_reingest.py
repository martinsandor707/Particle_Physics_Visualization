"""Re-ingesting an experiment from a changed source file, atomically; and retrying a failed one.

``pipeline.reingest_atomic`` replaces a ready experiment's tables, registry row and
archive part in one transaction: every other cursor keeps seeing the old data until
COMMIT, and a failed verification or a raised exception leaves the registry row, the
tables, ``manifest.json``, the archive files and ``config.json`` exactly as they were.
These tests prove that, the crash windows ``archive.reconcile`` settles at boot, the
job and the route around it, and that neither a boot nor Scan now ever re-ingests a
file by itself.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import time
from pathlib import Path

import duckdb
import pytest

import contract_check
from calosrv.db import archive, naming, registry
from calosrv.db.bootstrap import bootstrap, drop_experiment, physical_tables
from calosrv.errors import IngestError, InsufficientStorageError
from calosrv.ingest import autoingest, jobs as jobs_mod, load, pipeline
from calosrv.ingest import source_state as ss

from conftest import SEED_CSV, SEED_FILE, rewrite_parquet, settled

NAME = "swap_run"


def _events(database, name: str) -> list[int]:
    with database.read_cursor() as con:
        return [r[0] for r in con.execute(
            f'SELECT DISTINCT event_number FROM "{naming.event_table(name)}" ORDER BY 1').fetchall()]


class Swap:
    """One experiment ingested from a drop-folder file, and what a re-ingest of it needs."""

    def __init__(self, database, base_settings, folder: Path) -> None:
        self.database = database
        self.drop = folder
        self.settings = dataclasses.replace(base_settings, auto_ingest_dir=folder,
                                            auto_ingest_settle_s=0)
        self.source = folder / f"{NAME}.parquet"
        self.name = NAME

    def spec(self, job_id: str | None = None) -> dict:
        return {**ss.origin_spec(self.settings, ss.ORIGIN_DROP_FOLDER, self.source), "job_id": job_id}

    def change(self, shift: int = 0) -> Path:
        """The source file as a refreshed download: same rows, another codec; optionally new events."""
        tmp = self.drop / "refreshed.parquet"
        rewrite_parquet(SEED_FILE, tmp, event_shift=shift, compression="snappy")
        shutil.move(tmp, self.source)
        return settled(self.source, 600)

    def reingest(self, job_id: str = "job-new", con=None, **kwargs):
        def run(c):
            return pipeline.reingest_atomic(
                c, self.settings, self.name, self.source, source_name=self.source.name,
                provenance=self.spec(), job_id=job_id, build_sample=False, **kwargs)
        if con is not None:
            return run(con)
        with self.database.write_lock() as c:
            return run(c)

    def record(self) -> registry.ExperimentRecord:
        with self.database.read_cursor() as con:
            return registry.get_experiment(con, self.name)

    def archive_dir(self) -> Path:
        return archive.archive_path(self.settings, self.name)

    def snapshot(self) -> dict:
        """Everything a failed re-ingest must leave as it was."""
        with self.database.read_cursor() as con:
            row = con.execute('SELECT * FROM "experiment" WHERE table_name = ?',
                              [self.name]).fetchall()
            present = physical_tables(con)
            counts = {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                      for t in naming.all_tables(self.name) if t in present}
        directory = self.archive_dir()
        config = self.settings.config_path
        return {
            "row": row, "counts": counts,
            "files": {p.name: p.stat().st_size for p in sorted(directory.iterdir())},
            "manifest": (directory / "manifest.json").read_bytes(),
            "config": config.read_bytes() if config.exists() else None,
        }


@pytest.fixture
def swap(ingested, tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    base = ingested["settings"]
    ns = Swap(ingested["database"], base, drop)
    settled(rewrite_parquet(SEED_FILE, ns.source, compression="zstd"))
    base.config_path.write_text('{"default_model": "angle"}\n', encoding="utf-8")
    with ns.database.write_lock() as con:
        result = pipeline.run_ingest(
            con, ns.settings, NAME, ns.source, display_name="My swap run", build_sample=False,
            provenance=ns.spec("first-job"))
    assert result.ok, result.warnings
    yield ns
    with ns.database.write_lock() as con:
        drop_experiment(con, NAME, ns.settings)
    base.config_path.unlink(missing_ok=True)


# ------------------------------------------------------- the swap succeeds --


def test_a_changed_file_replaces_the_data_and_keeps_the_name_and_the_creation_time(swap):
    before = swap.record()
    assert _events(swap.database, NAME) == [0, 1]
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00000.parquet"]
    swap.change(shift=1000)
    result = swap.reingest("job-new")
    assert result.ok, result.warnings
    assert _events(swap.database, NAME) == [1000, 1001]
    after = swap.record()
    assert after.is_ready and after.error is None
    assert after.display_name == "My swap run"
    assert after.created_at == before.created_at and after.updated_at >= before.updated_at
    assert after.source_files == ["swap_run.parquet"]
    assert after.archive_parts == 1 and after.n_hits == before.n_hits


def test_the_new_record_describes_the_file_that_was_read_and_the_job_that_read_it(swap):
    old = swap.record().source_info
    path = swap.change(shift=1000)
    swap.reingest("job-new")
    info = swap.record().source_info
    assert info["job_id"] == "job-new" and old["job_id"] == "first-job"
    assert info["bytes"] == path.stat().st_size != old["bytes"]
    assert info["mtime_ns"] == path.stat().st_mtime_ns
    assert info["digest"] == ss.fingerprint(path)["digest"]
    assert (info["origin"], info["relpath"], info["name"]) == (
        "drop_folder", "swap_run.parquet", "swap_run.parquet")
    state = ss.inspect(swap.record(), swap.settings)
    assert state.state == "unchanged" and state.detail == ""


def test_the_old_part_is_gone_the_new_one_has_a_new_name_and_the_manifest_names_the_job(swap):
    swap.change(shift=1000)
    swap.reingest("job-1")
    directory = swap.archive_dir()
    assert sorted(p.name for p in directory.glob("part-*")) == ["part-00001.parquet"]
    manifest = archive.read_manifest(swap.settings, NAME)
    assert [p.file for p in manifest.parts] == ["part-00001.parquet"] and manifest.job_id == "job-1"
    assert json.loads((directory / "manifest.json").read_text())["job_id"] == "job-1"
    assert not (directory / "manifest.json.next").exists()
    swap.change(shift=2000)
    swap.reingest("job-2")
    assert sorted(p.name for p in directory.glob("part-*")) == ["part-00002.parquet"]
    assert _events(swap.database, NAME) == [2000, 2001]
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00002.parquet"]


def test_the_part_index_is_one_past_the_largest_not_the_count(swap):
    swap.change(shift=1000)
    swap.reingest("job-1")                     # one part, named part-00001
    assert archive.next_part_path(swap.settings, NAME).name == "part-00002.parquet"
    assert archive.part_index("part-00007.parquet") == 7 and archive.part_index("x.parquet") is None
    missing = dataclasses.replace(swap.settings, archive_dir=swap.settings.archive_dir / "nowhere")
    assert archive.next_part_path(missing, "fresh").name == "part-00000.parquet"


def test_a_manifest_written_before_reingest_existed_round_trips_byte_for_byte(swap):
    manifest = archive.read_manifest(swap.settings, NAME)
    assert manifest.job_id is None and "job_id" not in manifest.as_dict()
    before = (swap.archive_dir() / "manifest.json").read_bytes()
    archive.write_manifest(swap.settings, NAME, manifest)
    assert (swap.archive_dir() / "manifest.json").read_bytes() == before


# ------------------------------------------- the old data stays visible --


class Spy:
    """A connection that runs a hook just before COMMIT, to look at the database from outside."""

    def __init__(self, con, before_commit) -> None:
        self._con, self._hook = con, before_commit

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and sql.strip().upper() == "COMMIT":
            self._hook()
        return self._con.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._con, name)


def test_every_other_cursor_sees_the_old_data_until_commit(swap, monkeypatch):
    swap.change(shift=1000)
    seen: dict[str, dict] = {}

    def look(stage: str) -> None:
        directory = swap.archive_dir()
        with swap.database.read_cursor() as other:
            row = registry.get_experiment(other, NAME)
            seen[stage] = {
                "events": [r[0] for r in other.execute(
                    f'SELECT DISTINCT event_number FROM "{naming.event_table(NAME)}" '
                    "ORDER BY 1").fetchall()],
                "status": row.status, "job": row.source_info["job_id"],
                "manifest": json.loads((directory / "manifest.json").read_text()),
                "next": (directory / "manifest.json.next").exists(),
                "parts": sorted(p.name for p in directory.glob("part-*")),
            }

    real_derive = pipeline._derive

    def derive(*args, **kwargs):
        result = real_derive(*args, **kwargs)
        look("derived")
        return result

    monkeypatch.setattr(pipeline, "_derive", derive)
    with swap.database.write_lock() as con:
        result = swap.reingest("job-new", con=Spy(con, lambda: look("before_commit")))
    assert result.ok
    for stage in ("derived", "before_commit"):
        old = seen[stage]
        assert old["events"] == [0, 1] and old["status"] == "ready" and old["job"] == "first-job"
        assert [p["file"] for p in old["manifest"]["parts"]] == ["part-00000.parquet"]
        assert "job_id" not in old["manifest"]
        assert old["parts"] == ["part-00000.parquet", "part-00001.parquet"]
    assert seen["derived"]["next"] is False and seen["before_commit"]["next"] is True
    assert _events(swap.database, NAME) == [1000, 1001]
    assert swap.record().source_info["job_id"] == "job-new"


# ---------------------------------------------------- a failure changes nothing --


def _fail_verification(monkeypatch):
    real = pipeline._derive

    def failing(*args, **kwargs):
        result = real(*args, **kwargs)
        result.verification.fail("injected", "a failure injected by the test")
        return result

    monkeypatch.setattr(pipeline, "_derive", failing)


def _raise_in_derive(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("the disk caught fire")

    monkeypatch.setattr(pipeline, "_derive", boom)


def test_a_failed_verification_rolls_back_to_exactly_what_was_there(swap, monkeypatch):
    before = swap.snapshot()
    assert before["config"] is not None
    swap.change(shift=1000)
    _fail_verification(monkeypatch)
    result = swap.reingest("job-new")
    assert not result.ok
    assert ("The re-ingest failed verification and was rolled back; 'swap_run' is served as "
            "it was.") in result.warnings
    assert "a failure injected by the test" in result.warnings[0]
    assert swap.snapshot() == before
    assert _events(swap.database, NAME) == [0, 1]
    assert swap.record().source_info["job_id"] == "first-job"
    assert not (swap.archive_dir() / "manifest.json.next").exists()


def test_a_raised_exception_rolls_back_to_exactly_what_was_there(swap, monkeypatch):
    before = swap.snapshot()
    swap.change(shift=1000)
    _raise_in_derive(monkeypatch)
    with pytest.raises(IngestError) as info:
        swap.reingest("job-new")
    assert info.value.detail == (
        "The re-ingest of 'swap_run' from swap_run.parquet failed (the disk caught fire) and was "
        "rolled back; the experiment is served as it was.")
    assert swap.snapshot() == before
    assert _events(swap.database, NAME) == [0, 1]


def test_a_failure_after_the_transaction_began_leaves_the_connection_usable(swap, monkeypatch):
    swap.change(shift=1000)
    _raise_in_derive(monkeypatch)
    with pytest.raises(IngestError):
        swap.reingest("job-new")
    monkeypatch.undo()
    assert swap.reingest("job-again").ok            # no transaction was left open
    assert _events(swap.database, NAME) == [1000, 1001]


# ------------------------------------------------------------- refusals --


def test_a_schema_change_is_refused_and_names_both_schemas(swap, tmp_path):
    import synthetic_single_shower

    hits = tmp_path / "single.csv"
    synthetic_single_shower.write(hits)
    other = swap.drop / f"{NAME}.parquet"
    duckdb.connect().execute(
        f"COPY (SELECT * FROM read_csv('{hits}')) TO '{other}' (FORMAT parquet)")
    before = swap.snapshot()
    with pytest.raises(IngestError) as info:
        swap.reingest("job-new")
    assert "standalone_hits" in info.value.detail or "single" in info.value.detail.lower()
    assert "hits_all_models" in info.value.detail or "two-shower" in info.value.detail.lower()
    assert info.value.extra["expected"]["name"] == "hits_all_models"
    assert swap.snapshot() == before


def test_an_experiment_assembled_by_append_is_refused(swap):
    appended = settled(rewrite_parquet(SEED_FILE, swap.drop / "more.parquet", event_shift=500))
    with swap.database.write_lock() as con:
        pipeline.run_ingest(con, swap.settings, NAME, appended, mode="append", build_sample=False)
    assert len(archive.read_manifest(swap.settings, NAME).parts) == 2
    before = swap.snapshot()
    swap.change(shift=1000)
    with pytest.raises(IngestError, match="holds 2 archive part"):
        swap.reingest("job-new")
    assert swap.snapshot() == before


def test_only_a_ready_experiment_is_re_ingested(swap):
    with swap.database.write_lock() as con:
        registry.set_status(con, NAME, registry.STATUS_FAILED, "boom")
    swap.change(shift=1000)
    with pytest.raises(IngestError, match="only a ready experiment"):
        swap.reingest("job-new")
    with pytest.raises(IngestError, match="does not exist"):
        pipeline.reingest_atomic(
            swap.database.raw.cursor(), swap.settings, "no_such_run", swap.source,
            source_name="x", provenance=swap.spec(), job_id="j")


# ---------------------------------------------------- the crash windows --


def test_a_crash_before_the_commit_is_undone_at_boot(swap):
    """The new part and manifest.json.next are on disk; the registry still names the old job."""
    before = swap.snapshot()
    swap.change(shift=1000)
    with swap.database.write_lock() as con:
        check = pipeline.formats.validate(con, swap.source, "parquet")
        loaded = load.stage_replacement(con, swap.settings, NAME, swap.source, fmt="parquet",
                                        check=check, job_id="job-never-committed")
        archive.write_next(swap.settings, NAME, loaded.manifest)
    directory = swap.archive_dir()
    assert (directory / "manifest.json.next").exists() and (directory / "part-00001.parquet").exists()
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    assert swap.snapshot() == before
    assert not (directory / "manifest.json.next").exists()
    assert _events(swap.database, NAME) == [0, 1]


def test_a_crash_between_the_commit_and_the_rename_is_rolled_forward_at_boot(swap, monkeypatch):
    swap.change(shift=1000)

    def killed(settings, name):
        raise KeyboardInterrupt("the process died here")

    monkeypatch.setattr(archive, "commit_next", killed)
    with pytest.raises(KeyboardInterrupt):
        swap.reingest("job-committed")
    monkeypatch.undo()
    directory = swap.archive_dir()
    # The database holds the new data; the archive still lists the old part.
    assert swap.record().source_info["job_id"] == "job-committed"
    assert _events(swap.database, NAME) == [1000, 1001]
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00000.parquet"]
    assert (directory / "manifest.json.next").exists()
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    manifest = archive.read_manifest(swap.settings, NAME)
    assert [p.file for p in manifest.parts] == ["part-00001.parquet"] and manifest.job_id == "job-committed"
    assert sorted(p.name for p in directory.glob("part-*")) == ["part-00001.parquet"]
    assert not (directory / "manifest.json.next").exists()
    assert swap.record().is_ready


def test_a_crash_after_the_rename_leaves_an_old_part_that_boot_removes(swap):
    swap.change(shift=1000)
    swap.reingest("job-1")
    directory = swap.archive_dir()
    stray = directory / "part-00000.parquet"
    shutil.copyfile(directory / "part-00001.parquet", stray)
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    assert not stray.exists() and (directory / "part-00001.parquet").exists()
    assert _events(swap.database, NAME) == [1000, 1001]


def test_boot_never_touches_a_folder_whose_manifest_cannot_be_read(swap):
    directory = swap.archive_dir()
    (directory / "manifest.json").write_text("{ not json", encoding="utf-8")
    stray = directory / "part-00009.parquet"
    stray.write_bytes(b"PAR1")
    actions = archive.reconcile(swap.settings, [swap.record()])
    assert actions == [] and stray.exists()
    assert (directory / "manifest.json").read_text() == "{ not json"
    (directory / "manifest.json").write_bytes(b"")  # restore something the teardown can drop


def test_boot_logs_every_action_at_warning(swap, caplog):
    directory = swap.archive_dir()
    (directory / "part-00004.parquet").write_bytes(b"PAR1")
    (directory / "manifest.json.next").write_text(
        json.dumps({"schema_name": "hits_all_models", "schema_version": 1, "parts": [],
                    "job_id": "nobody"}), encoding="utf-8")
    with caplog.at_level("WARNING", logger="calosrv.db.archive"):
        actions = archive.reconcile(swap.settings, [swap.record()])
    assert len(actions) == 2 and len(caplog.records) == 2
    assert all(r.levelname == "WARNING" for r in caplog.records)
    assert any("uncommitted re-ingest" in m for m in actions)
    assert any("part-00004.parquet" in m for m in actions)


# ------------------------------------------- neither a boot nor a scan re-ingests --


class RecordingStore:
    def __init__(self):
        self.submitted = []

    def active_names(self):
        return set()

    def submit(self, **kwargs):
        self.submitted.append(kwargs)
        return type("Job", (), {"job_id": f"job{len(self.submitted)}"})()


def test_a_boot_and_a_scan_report_a_changed_file_and_never_re_ingest_it(swap):
    swap.change(shift=1000)
    before = swap.snapshot()
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    store = RecordingStore()
    report = autoingest.scan(swap.database, swap.settings, store)
    entry = {e.file: e for e in report.entries}["swap_run.parquet"]
    assert entry.action == "changed" and entry.table_name == NAME
    assert entry.detail.startswith(
        "Experiment 'swap_run' exists, and this file has changed since it was ingested. Size ")
    assert entry.detail.endswith(
        " It is never re-ingested by itself: use Re-ingest under Source files in Admin Settings.")
    assert store.submitted == []
    assert swap.snapshot() == before
    assert _events(swap.database, NAME) == [0, 1]


def test_a_scan_of_an_unchanged_file_says_exists_and_a_failed_one_points_to_retry(swap):
    report = autoingest.scan(swap.database, swap.settings, RecordingStore())
    entry = {e.file: e for e in report.entries}["swap_run.parquet"]
    assert entry.action == "exists" and "already exists (ready)" in entry.detail
    with swap.database.write_lock() as con:
        registry.set_status(con, NAME, registry.STATUS_FAILED, "boom")
    report = autoingest.scan(swap.database, swap.settings, RecordingStore())
    entry = {e.file: e for e in report.entries}["swap_run.parquet"]
    assert entry.action == "exists"
    assert entry.detail.endswith(
        "It failed earlier: use Retry ingest under Source files in Admin Settings.")


def test_a_same_named_file_that_is_not_the_experiments_source_is_just_existing(swap, tmp_path):
    """An experiment uploaded under a name a drop-folder file also derives is not 'changed' by it."""
    other = tmp_path / "other"
    other.mkdir()
    elsewhere = dataclasses.replace(swap.settings, auto_ingest_dir=other)
    shutil.copyfile(SEED_FILE, other / "swap_run.parquet")
    settled(other / "swap_run.parquet")
    report = autoingest.scan(swap.database, elsewhere, RecordingStore())
    entry = {e.file: e for e in report.entries}["swap_run.parquet"]
    assert entry.action == "exists"


def test_the_scan_queues_a_new_file_with_the_drop_folder_as_its_origin(ingested, tmp_path):
    folder = tmp_path / "new"
    folder.mkdir()
    settled(rewrite_parquet(SEED_FILE, folder / "brand_new.parquet"))
    settings = dataclasses.replace(ingested["settings"], auto_ingest_dir=folder,
                                   auto_ingest_settle_s=0)
    store = RecordingStore()
    autoingest.scan(ingested["database"], settings, store)
    assert [s["origin"] for s in store.submitted] == ["drop_folder"]


# ----------------------------------------------- the job: caches and follow-up --


class _Blob:
    nbytes = 8


def _await(job, timeout: float = 120.0) -> None:
    end = time.time() + timeout
    while job.status in (jobs_mod.JOB_QUEUED, jobs_mod.JOB_RUNNING) and time.time() < end:
        time.sleep(0.05)
    assert job.finished_at is not None, "the job did not finish"


@pytest.fixture
def worker(ingested, monkeypatch):
    """A job store of its own on the shared database, with warming and the analysis hook recorded."""
    from calosrv.modelruns import jobs as modelruns_jobs
    from calosrv.query import warming

    calls = {"warm": [], "after_ready": []}
    monkeypatch.setattr(warming, "warm", lambda db, settings, records, **kw: calls["warm"].append(
        [r.table_name for r in records]))
    monkeypatch.setattr(modelruns_jobs, "after_ready", lambda name: calls["after_ready"].append(name))
    # The job store reads ``database.settings``; the shared database may have been opened by an
    # earlier booted module with another data directory, so it is given this test's settings.
    database = type("Db", (), {
        "settings": ingested["settings"],
        "write_lock": staticmethod(ingested["database"].write_lock),
        "read_cursor": staticmethod(ingested["database"].read_cursor),
    })()
    store = jobs_mod.JobStore(database)
    yield store, calls
    store.shutdown()


def _submit(store, swap, action: str):
    from calosrv.ingest.stream import StagedFile

    return store.submit_reingest(
        NAME, StagedFile(path=swap.source, original_name=swap.source.name,
                         size_bytes=swap.source.stat().st_size),
        action, "My swap run", 0, ss.origin_spec(swap.settings, "drop_folder", swap.source))


def test_a_successful_reingest_job_invalidates_every_cache_warms_and_queues_the_analysis(swap, worker):
    from calosrv.query import cache

    store, calls = worker
    swap.change(shift=1000)
    for cache_name in (cache.LAB_CACHE, cache.CANONICAL_CACHE, cache.PHYSICS_CACHE,
                       cache.VOXEL_CACHE):
        cache.get_cache(name=cache_name).get_or_compute((NAME, "key"), _Blob)
    cache.get_cache(name=cache.LAB_CACHE).get_or_compute(("other_experiment", "key"), _Blob)
    job = _submit(store, swap, "reingest")
    assert job.mode == "reingest" and job.force_reingest is False
    _await(job)
    assert job.status == jobs_mod.JOB_DONE, job.error
    assert job.error is None and job.progress == 1.0
    assert job.stage_label == "Re-ingest complete"
    for cache_name in (cache.LAB_CACHE, cache.CANONICAL_CACHE, cache.PHYSICS_CACHE, cache.VOXEL_CACHE):
        _, was_cached = cache.get_cache(name=cache_name).get_or_compute((NAME, "key"), _Blob)
        assert was_cached is False, cache_name
    _, kept = cache.get_cache(name=cache.LAB_CACHE).get_or_compute(("other_experiment", "key"), _Blob)
    assert kept is True
    assert calls == {"warm": [[NAME]], "after_ready": [NAME]}
    assert _events(swap.database, NAME) == [1000, 1001]
    assert swap.source.exists(), "the job never deletes the source file"
    assert store.latest_for(NAME) is job and store.latest_for("nobody") is None


def test_a_failed_reingest_job_is_failed_with_the_rollback_message_and_changes_nothing(
        swap, worker, monkeypatch):
    store, calls = worker
    before = swap.snapshot()
    swap.change(shift=1000)
    _fail_verification(monkeypatch)
    job = _submit(store, swap, "reingest")
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert "was rolled back; 'swap_run' is served as it was." in job.error
    assert job.stage_label == "Re-ingest rolled back"
    assert swap.snapshot() == before
    assert calls == {"warm": [], "after_ready": []}


def test_an_exception_in_a_reingest_job_fails_it_and_leaves_the_experiment_ready(
        swap, worker, monkeypatch):
    store, _ = worker
    before = swap.snapshot()
    swap.change(shift=1000)
    _raise_in_derive(monkeypatch)
    job = _submit(store, swap, "reingest")
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert "failed (the disk caught fire) and was rolled back" in job.error
    assert swap.snapshot() == before and swap.record().is_ready


def test_a_second_job_for_a_name_is_refused_while_one_is_active(swap, worker, monkeypatch):
    from calosrv.errors import ConflictError

    store, _ = worker
    swap.change(shift=1000)
    gate = []
    real = pipeline.reingest_atomic

    def slow(*args, **kwargs):
        while not gate:
            time.sleep(0.02)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "reingest_atomic", slow)
    job = _submit(store, swap, "reingest")
    with pytest.raises(ConflictError):
        _submit(store, swap, "reingest")
    gate.append(1)
    _await(job)
    assert job.status == jobs_mod.JOB_DONE


def test_retry_clears_the_partial_tables_and_the_archive_and_ingests_again(swap, worker):
    store, calls = worker
    swap.change(shift=1000)
    # What a crashed first attempt leaves: a failed row, a stray model table, a stray part.
    stray_table = naming.xgb_tables(NAME)["run"]
    with swap.database.write_lock() as con:
        registry.set_status(con, NAME, registry.STATUS_FAILED, "Ingestion was interrupted before it completed.")
        con.execute(f'CREATE TABLE "{stray_table}" AS SELECT 1 AS leftover')
    stray_part = swap.archive_dir() / "part-00007.parquet"
    stray_part.write_bytes(b"PAR1")
    created = swap.record().created_at
    job = _submit(store, swap, "retry")
    assert job.mode == "retry" and job.force_reingest is True
    _await(job)
    assert job.status == jobs_mod.JOB_DONE, job.error
    record = swap.record()
    assert record.is_ready and record.error is None and record.created_at == created
    assert record.display_name == "My swap run"
    assert record.source_info["job_id"] == job.job_id
    assert record.source_info["bytes"] == swap.source.stat().st_size
    assert _events(swap.database, NAME) == [1000, 1001]
    with swap.database.read_cursor() as con:
        assert stray_table not in physical_tables(con)
    assert not stray_part.exists()
    assert sorted(p.name for p in swap.archive_dir().glob("part-*")) == ["part-00000.parquet"]
    assert calls["after_ready"] == [NAME] and calls["warm"] == [[NAME]]


# ----------------------------------------------------- the route, end to end --


def _wait(client, job_id: str, timeout: float = 120.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/upload/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError("the job did not finish")


def _dropped(source_client, name: str, shift: int = 0) -> str:
    """Put ``name.parquet`` in the drop folder, scan, and wait until it is ready."""
    client, drop = source_client["client"], source_client["drop"]
    settled(rewrite_parquet(SEED_FILE, drop / f"{name}.parquet", event_shift=shift,
                            compression="zstd"))
    scan = client.post("/api/admin/auto-ingest/scan").json()
    entry = next(e for e in scan["entries"] if e["file"] == f"{name}.parquet")
    assert entry["action"] == "submitted", entry
    assert _wait(client, entry["job_id"])["status"] == "done"
    return name


def _change(source_client, name: str, shift: int = 0) -> Path:
    path = source_client["drop"] / f"{name}.parquet"
    rewrite_parquet(SEED_FILE, path.with_suffix(".tmp.parquet"), event_shift=shift,
                    compression="snappy")
    shutil.move(path.with_suffix(".tmp.parquet"), path)
    return settled(path, 600)


def _entry(source_client, name: str) -> dict:
    body = source_client["client"].get("/api/admin/experiments").json()
    return next(e for e in body["experiments"] if e["table_name"] == name)


def _post(source_client, name: str, body=None):
    client = source_client["client"]
    return client.post(f"/api/admin/experiments/{name}/reingest",
                       **({"json": body} if body is not None else {}))


def test_the_route_re_ingests_a_changed_file_and_the_listing_follows(source_client):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_swap")
    with database.read_cursor() as con:
        created = registry.get_experiment(con, name).created_at
    _change(source_client, name, shift=1000)
    assert _entry(source_client, name)["source"]["state"] == "changed"
    reply = _post(source_client, name)
    assert reply.status_code == 202, reply.text
    body = reply.json()
    contract_check.check(body, "admin_experiments", at="reingest_reply")
    assert body["action"] == "reingest" and body["job"]["mode"] == "reingest"
    assert body["poll"] == f"/api/upload/{body['job']['job_id']}"
    job = _wait(client, body["job"]["job_id"])
    assert job["status"] == "done", job
    assert _events(database, name) == [1000, 1001]
    entry = _entry(source_client, name)
    assert entry["source"]["state"] == "unchanged" and entry["status"] == "ready"
    assert entry["job"]["mode"] == "reingest" and entry["job"]["status"] == "done"
    with database.read_cursor() as con:
        record = registry.get_experiment(con, name)
    assert record.created_at == created and record.source_info["job_id"] == job["job_id"]


def test_the_route_says_why_with_the_right_status(source_client, monkeypatch):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_codes")

    assert _post(source_client, "no_such_experiment").status_code == 404

    unchanged = _post(source_client, name)
    assert unchanged.status_code == 422
    problem = unchanged.json()
    assert problem["reason"] == "Its source file is unchanged since it was ingested."
    assert problem["capability"] == "reingest" and problem["table_name"] == name
    assert _post(source_client, "experiment_baseline").json()["reason"] == (
        "The demonstration dataset ships in the image and is never re-ingested.")
    assert _post(source_client, name, {"force": "yes"}).status_code == 422

    store = jobs_mod.get_job_store(database)
    monkeypatch.setattr(store, "active_names", lambda: {name})
    assert _post(source_client, name).status_code == 409
    monkeypatch.undo()
    with database.write_lock() as con:
        registry.set_status(con, name, registry.STATUS_INGESTING)
    busy = _post(source_client, name)
    assert busy.status_code == 409 and "still being ingested" in busy.json()["detail"]
    with database.write_lock() as con:
        registry.set_status(con, name, registry.STATUS_READY)

    _change(source_client, name)
    monkeypatch.setattr("calosrv.ingest.stream.check_free_space",
                        lambda *a, **k: (_ for _ in ()).throw(
                            InsufficientStorageError("Ingesting needs 9.0 GB.", required_bytes=9)))
    full = _post(source_client, name)
    assert full.status_code == 507
    assert full.json()["detail"].startswith("Ingesting needs 9.0 GB. A re-ingest keeps the old and the new copy")
    assert "Upload dataset with Replace ticked" in full.json()["detail"]
    monkeypatch.undo()
    assert _entry(source_client, name)["source"]["state"] == "changed", "nothing was queued"


def test_force_lifts_only_the_unchanged_reason(source_client):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_force")
    reply = _post(source_client, name, {"force": True})
    assert reply.status_code == 202, reply.text
    assert _wait(client, reply.json()["job"]["job_id"])["status"] == "done"
    assert _events(database, name) == [0, 1]


def test_the_route_refuses_a_file_that_is_not_an_accepted_schema_or_not_the_experiments(
        source_client, tmp_path):
    import synthetic_single_shower

    drop = source_client["drop"]
    name = _dropped(source_client, "rt_schema")
    path = drop / f"{name}.parquet"
    path.write_bytes(b"this is not parquet at all")
    settled(path, 600)
    reply = _post(source_client, name)
    assert reply.status_code == 400
    assert reply.json()["type"] == "/problems/ingest-failed"
    hits = tmp_path / "single.csv"
    synthetic_single_shower.write(hits)
    duckdb.connect().execute(f"COPY (SELECT * FROM read_csv('{hits}')) TO '{path}' (FORMAT parquet)")
    settled(path, 600)
    reply = _post(source_client, name)
    assert reply.status_code == 400
    detail = reply.json()["detail"]
    assert "single-shower" in detail.lower() or "standalone" in detail.lower()
    assert "two-shower" in detail.lower() or "hits_all_models" in detail
    assert reply.json()["expected"]["name"] == "hits_all_models"
    assert _entry(source_client, name)["job"]["mode"] == "create_new"


def test_the_route_refuses_an_appended_experiment(source_client):
    client = source_client["client"]
    name = _dropped(source_client, "rt_append")
    more = rewrite_parquet(SEED_FILE, source_client["local"] / "more_events.parquet", event_shift=500)
    reply = client.post("/api/upload", files={"file": ("more.parquet", more.read_bytes(),
                                                       "application/octet-stream")},
                        data={"table_name": name, "mode": "append"})
    assert reply.status_code == 202, reply.text
    assert _wait(client, reply.json()["job"]["job_id"])["status"] == "done"
    _change(source_client, name, shift=1000)
    refused = _post(source_client, name)
    assert refused.status_code == 422
    assert refused.json()["reason"] == (
        "It was assembled from 2 files by append; replace it from Upload dataset instead.")
    assert _entry(source_client, name)["archive_parts"] == 2


def test_a_failed_reingest_through_the_route_leaves_the_experiment_as_it_was(
        source_client, monkeypatch):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_rollback")
    _change(source_client, name, shift=1000)
    with database.read_cursor() as con:
        before = registry.get_experiment(con, name)
    _fail_verification(monkeypatch)
    reply = _post(source_client, name)
    assert reply.status_code == 202
    job = _wait(client, reply.json()["job"]["job_id"])
    assert job["status"] == "failed" and "was rolled back" in job["error"]
    monkeypatch.undo()
    assert _events(database, name) == [0, 1]
    with database.read_cursor() as con:
        after = registry.get_experiment(con, name)
    assert after.is_ready and after.source_info == before.source_info
    assert after.updated_at == before.updated_at
    entry = _entry(source_client, name)
    assert entry["source"]["state"] == "changed", "the file is still newer than the data"
    assert entry["job"]["status"] == "failed"


def test_retry_through_the_route_ingests_a_failed_experiment_again(source_client):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_retry")
    with database.write_lock() as con:
        registry.set_status(con, name, registry.STATUS_FAILED, "Ingestion was interrupted.")
    entry = _entry(source_client, name)
    assert entry["status"] == "failed"
    assert entry["actions"]["retry"] == {"available": True, "reason": None}
    assert entry["actions"]["reingest"]["reason"] == "A failed experiment is retried, not re-ingested."
    reply = _post(source_client, name)
    assert reply.status_code == 202, reply.text
    assert reply.json()["action"] == "retry" and reply.json()["job"]["mode"] == "retry"
    job = _wait(client, reply.json()["job"]["job_id"])
    assert job["status"] == "done", job
    assert _entry(source_client, name)["status"] == "ready"
    assert _events(database, name) == [0, 1]


def test_retry_is_refused_when_the_file_is_gone(source_client):
    database = source_client["database"]
    name = _dropped(source_client, "rt_gone")
    with database.write_lock() as con:
        registry.set_status(con, name, registry.STATUS_FAILED, "boom")
    (source_client["drop"] / f"{name}.parquet").unlink()
    reply = _post(source_client, name)
    assert reply.status_code == 422
    assert reply.json()["reason"] == (
        f"Its source file {name}.parquet is not in {source_client['drop']}; ingest it again from "
        "Upload dataset with Replace ticked.")


def test_scan_now_reports_a_changed_file_and_queues_nothing(source_client):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_scan")
    _change(source_client, name, shift=1000)
    jobs_before = len(client.get("/api/upload").json()["jobs"])
    scan = client.post("/api/admin/auto-ingest/scan").json()
    entry = next(e for e in scan["entries"] if e["file"] == f"{name}.parquet")
    assert entry["action"] == "changed" and entry["job_id"] is None
    assert "use Re-ingest under Source files in Admin Settings." in entry["detail"]
    assert len(client.get("/api/upload").json()["jobs"]) == jobs_before
    assert _events(database, name) == [0, 1]
    assert _entry(source_client, name)["source"]["state"] == "changed"


# ------------------------------------------- a failure after COMMIT (E4) --


def _fail_the_rename(monkeypatch, *, times: int = 99) -> list:
    """Make ``archive.commit_next`` raise ``OSError`` the first ``times`` calls; returns the call log."""
    calls: list[int] = []
    real = archive.commit_next

    def failing(settings, name):
        calls.append(1)
        if len(calls) <= times:
            raise OSError(28, "No space left on device")
        return real(settings, name)

    monkeypatch.setattr(archive, "commit_next", failing)
    return calls


def test_a_rename_that_fails_after_the_commit_is_never_reported_as_a_rollback(swap, monkeypatch):
    swap.change(shift=1000)
    calls = _fail_the_rename(monkeypatch)
    with pytest.raises(pipeline.ReingestCommittedError) as info:
        swap.reingest("job-committed")
    text = info.value.detail
    assert text == (
        "The new data of 'swap_run' are committed, but its archive manifest could not be switched "
        "([Errno 28] No space left on device): the server completes it at its next start. Do not "
        "rebuild or append to it before then.")
    assert "rolled back" not in text and isinstance(info.value, IngestError)
    assert len(calls) == 2, "the rename is tried once more"
    # The database holds the new data and the new record; nothing was undone or cleaned up.
    directory = swap.archive_dir()
    assert _events(swap.database, NAME) == [1000, 1001]
    assert swap.record().source_info["job_id"] == "job-committed" and swap.record().is_ready
    assert (directory / "manifest.json.next").exists() and archive.next_pending(swap.settings, NAME)
    assert sorted(p.name for p in directory.glob("part-*")) == [
        "part-00000.parquet", "part-00001.parquet"]
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00000.parquet"]


def test_a_rename_that_works_the_second_time_is_a_success(swap, monkeypatch):
    swap.change(shift=1000)
    calls = _fail_the_rename(monkeypatch, times=1)
    assert swap.reingest("job-1").ok
    assert len(calls) == 2
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00001.parquet"]
    assert not archive.next_pending(swap.settings, NAME)
    assert sorted(p.name for p in swap.archive_dir().glob("part-*")) == ["part-00001.parquet"]


def test_an_old_part_that_cannot_be_deleted_is_a_warning_and_boot_sweeps_it(
        swap, monkeypatch, caplog):
    swap.change(shift=1000)
    real_unlink = Path.unlink

    def stubborn(self, *args, **kwargs):
        if self.name == "part-00000.parquet":
            raise PermissionError(13, "Permission denied")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", stubborn)
    with caplog.at_level("WARNING"):
        assert swap.reingest("job-1").ok
    monkeypatch.undo()
    assert "could not delete the old part" in caplog.text
    directory = swap.archive_dir()
    assert (directory / "part-00000.parquet").exists()
    assert [p.file for p in archive.read_manifest(swap.settings, NAME).parts] == ["part-00001.parquet"]
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    assert not (directory / "part-00000.parquet").exists()


def test_a_failing_rollback_does_not_skip_the_cleanup_of_the_new_part(swap, monkeypatch):
    class Failing(Spy):
        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.strip().upper() == "ROLLBACK":
                self._con.execute(sql)
                raise duckdb.Error("the rollback itself failed")
            return self._con.execute(sql, *args, **kwargs)

    swap.change(shift=1000)
    _fail_verification(monkeypatch)
    with swap.database.write_lock() as con:
        with pytest.raises(duckdb.Error):
            swap.reingest("job-new", con=Failing(con, lambda: None))
    directory = swap.archive_dir()
    assert sorted(p.name for p in directory.glob("*")) == ["manifest.json", "part-00000.parquet"]
    assert _events(swap.database, NAME) == [0, 1]


def _half_finished(swap, monkeypatch) -> None:
    swap.change(shift=1000)
    _fail_the_rename(monkeypatch)
    with pytest.raises(pipeline.ReingestCommittedError):
        swap.reingest("job-committed")
    monkeypatch.undo()


def test_while_a_re_ingest_is_half_finished_nothing_rebuilds_appends_or_re_ingests_it(
        swap, monkeypatch):
    from calosrv.errors import ConflictError

    _half_finished(swap, monkeypatch)
    message = "A re-ingest of 'swap_run' is half-finished; restart the server to complete it."
    before = swap.snapshot()
    with swap.database.write_lock() as con:
        for attempt in (
            lambda: pipeline.rebuild(con, swap.settings, NAME, build_sample=False),
            lambda: pipeline.rebuild_atomic(con, swap.settings, NAME, build_sample=False),
            lambda: pipeline.run_ingest(con, swap.settings, NAME, swap.source,
                                        mode=load.MODE_APPEND, event_offset=5000,
                                        build_sample=False),
            lambda: load.load_source(con, swap.settings, NAME, swap.source, fmt="parquet",
                                     check=pipeline.formats.validate(con, swap.source, "parquet"),
                                     mode=load.MODE_APPEND),
        ):
            with pytest.raises(ConflictError) as info:
                attempt()
            assert info.value.detail == message
    with pytest.raises(ConflictError):
        swap.reingest("job-again")
    assert swap.snapshot() == before, "a refusal touches nothing"
    assert _events(swap.database, NAME) == [1000, 1001]


def test_boot_rolls_a_half_finished_re_ingest_forward_and_lifts_the_guard(swap, monkeypatch):
    _half_finished(swap, monkeypatch)
    directory = swap.archive_dir()
    with swap.database.write_lock() as con:
        bootstrap(con, swap.settings)
    manifest = archive.read_manifest(swap.settings, NAME)
    assert [p.file for p in manifest.parts] == ["part-00001.parquet"]
    assert manifest.job_id == "job-committed" and not archive.next_pending(swap.settings, NAME)
    assert sorted(p.name for p in directory.glob("part-*")) == ["part-00001.parquet"]
    assert _events(swap.database, NAME) == [1000, 1001]
    with swap.database.write_lock() as con:           # and a rebuild works again, on the new part
        assert pipeline.rebuild_atomic(con, swap.settings, NAME, build_sample=False).ok
    assert _events(swap.database, NAME) == [1000, 1001]


def test_a_job_whose_rename_failed_says_so_invalidates_the_caches_and_queues_nothing(
        swap, worker, monkeypatch):
    from calosrv.query import cache

    store, calls = worker
    swap.change(shift=1000)
    _fail_the_rename(monkeypatch)
    cache.get_cache(name=cache.LAB_CACHE).get_or_compute((NAME, "key"), _Blob)
    job = _submit(store, swap, "reingest")
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert job.error.startswith("The new data of 'swap_run' are committed, but its archive "
                                "manifest could not be switched")
    assert "rolled back" not in job.error and "served as it was" not in job.error
    assert job.stage_label == "Re-ingest committed; manifest pending"
    _, was_cached = cache.get_cache(name=cache.LAB_CACHE).get_or_compute((NAME, "key"), _Blob)
    assert was_cached is False, "the database changed, so the caches go"
    assert calls == {"warm": [], "after_ready": []}, "no analysis may read the stale manifest"
    assert store.active_names() == set()
    assert _events(swap.database, NAME) == [1000, 1001] and swap.record().is_ready


def test_the_route_refuses_a_rebuild_and_a_re_ingest_of_a_half_finished_experiment(
        source_client, monkeypatch):
    client, database = source_client["client"], source_client["database"]
    name = _dropped(source_client, "rt_half")
    _change(source_client, name, shift=1000)
    _fail_the_rename(monkeypatch)
    reply = _post(source_client, name)
    assert reply.status_code == 202
    job = _wait(client, reply.json()["job"]["job_id"])
    monkeypatch.undo()
    assert job["status"] == "failed" and "are committed" in job["error"]
    assert _events(database, name) == [1000, 1001]
    message = "A re-ingest of 'rt_half' is half-finished; restart the server to complete it."
    rebuild = client.post(f"/api/admin/experiments/{name}/rebuild")
    assert rebuild.status_code == 409 and rebuild.json()["detail"] == message
    again = _post(source_client, name, {"force": True})
    assert again.status_code == 409 and again.json()["detail"] == message
    # An append is refused by the upload route itself, before a byte is staged.
    append = client.post("/api/upload", files={"file": ("more.parquet", b"not read")},
                         data={"table_name": name, "mode": "append"})
    assert append.status_code == 409 and append.json()["detail"] == message
    # What the next start does: roll the manifest forward. The guard is gone.
    settings = database.settings
    with database.read_cursor() as con:
        rows = registry.list_experiments(con)
    archive.reconcile(settings, rows)
    assert not archive.next_pending(settings, name)
    assert [p.file for p in archive.read_manifest(settings, name).parts] == ["part-00001.parquet"]
    assert client.post(f"/api/admin/experiments/{name}/rebuild").status_code == 202
    end = time.time() + 120
    while jobs_mod.get_job_store(database).active_names() and time.time() < end:
        time.sleep(0.1)


def test_a_keyboard_interrupt_in_the_worker_leaves_no_active_job(swap, worker, monkeypatch):
    store, _ = worker
    swap.change(shift=1000)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("the worker was interrupted")

    monkeypatch.setattr(pipeline, "reingest_atomic", interrupted)
    job = _submit(store, swap, "reingest")
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert job.error == "The ingest worker was interrupted before the job finished."
    assert store.active_names() == set()
    monkeypatch.undo()
    assert _submit(store, swap, "reingest") is not None, "the name is free again"


@pytest.mark.parametrize("which", ["warm", "after_ready"])
def test_an_optional_step_that_fails_after_the_commit_leaves_the_job_done(
        swap, worker, monkeypatch, which, caplog):
    from calosrv.modelruns import jobs as modelruns_jobs
    from calosrv.query import warming

    store, _ = worker

    def boom(*args, **kwargs):
        raise RuntimeError("an optional step failed")

    if which == "warm":
        monkeypatch.setattr(warming, "warm", boom)
    else:
        monkeypatch.setattr(modelruns_jobs, "after_ready", boom)
    swap.change(shift=1000)
    with caplog.at_level("ERROR"):
        job = _submit(store, swap, "reingest")
        _await(job)
    assert job.status == jobs_mod.JOB_DONE and job.error is None
    assert job.stage_label == "Re-ingest complete"
    assert "an optional step failed" in caplog.text
    assert _events(swap.database, NAME) == [1000, 1001]


# ------------------------------------ the worker re-checks its source (E12) --


def test_the_worker_refuses_a_row_that_another_job_has_rewritten_since_the_request(swap):
    """An upload with Replace ran between the request and the worker: nothing is done."""
    swap.change(shift=1000)
    before = swap.snapshot()
    with pytest.raises(IngestError) as info:
        swap.reingest("job-new", expected_job_id="some-earlier-job")
    assert info.value.detail == ("Experiment 'swap_run' changed since the re-ingest was requested; "
                                 "nothing was done.")
    assert swap.snapshot() == before
    assert not (swap.archive_dir() / "part-00001.parquet").exists()
    assert swap.reingest("job-new", expected_job_id="first-job").ok


def test_a_row_recorded_before_source_tracking_expects_none(swap):
    with swap.database.write_lock() as con:
        row = registry.get_experiment(con, NAME)
        row.source_info = {}
        registry.upsert(con, row)
    swap.change(shift=1000)
    with pytest.raises(IngestError):
        swap.reingest("job-new", expected_job_id="first-job")
    assert swap.reingest("job-new", expected_job_id=None).ok


def test_an_interleaved_replace_makes_the_queued_reingest_do_nothing(swap, worker):
    store, calls = worker
    from calosrv.ingest.stream import StagedFile

    swap.change(shift=1000)
    replacement = settled(rewrite_parquet(SEED_FILE, swap.drop / "uploaded.parquet",
                                          event_shift=5000, compression="zstd"))
    with swap.database.write_lock() as con:
        # Queued while the row still names "first-job"; the worker waits for this lock.
        job = store.submit_reingest(
            NAME, StagedFile(path=swap.source, original_name=swap.source.name,
                             size_bytes=swap.source.stat().st_size),
            "reingest", "My swap run", 0, ss.origin_spec(swap.settings, "drop_folder", swap.source),
            expected_job_id="first-job")
        # An upload with Replace gets in first.
        result = pipeline.run_ingest(
            con, swap.settings, NAME, replacement, source_name="uploaded.parquet",
            force_reingest=True, build_sample=False, display_name="My swap run",
            provenance={**ss.origin_spec(swap.settings, "upload", replacement), "job_id": "replacer"})
        assert result.ok
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert job.error == ("Experiment 'swap_run' changed since the re-ingest was requested; "
                         "nothing was done.")
    assert _events(swap.database, NAME) == [5000, 5001], "the uploaded data stay"
    assert swap.record().source_info["job_id"] == "replacer"
    assert calls == {"warm": [], "after_ready": []}
    assert store.active_names() == set()


def test_a_queued_retry_refuses_a_row_that_is_no_longer_failed(swap, worker):
    store, _ = worker
    from calosrv.ingest.stream import StagedFile

    swap.change(shift=1000)
    with swap.database.write_lock() as con:
        registry.set_status(con, NAME, registry.STATUS_FAILED, "Ingestion was interrupted.")
    with swap.database.write_lock() as con:
        job = store.submit_reingest(
            NAME, StagedFile(path=swap.source, original_name=swap.source.name,
                             size_bytes=swap.source.stat().st_size),
            "retry", "My swap run", 0, ss.origin_spec(swap.settings, "drop_folder", swap.source),
            expected_job_id="first-job")
        registry.set_status(con, NAME, registry.STATUS_READY)    # something else repaired it
    _await(job)
    assert job.status == jobs_mod.JOB_FAILED
    assert "changed since the re-ingest was requested; nothing was done." in job.error
    assert _events(swap.database, NAME) == [0, 1] and swap.record().is_ready


def test_the_route_passes_the_rows_source_job_to_the_worker(source_client, monkeypatch):
    database = source_client["database"]
    name = _dropped(source_client, "rt_expect")
    _change(source_client, name, shift=1000)
    with database.read_cursor() as con:
        wanted = registry.get_experiment(con, name).source_info["job_id"]
    seen = []
    real = jobs_mod.JobStore.submit_reingest

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("expected_job_id", "missing"))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(jobs_mod.JobStore, "submit_reingest", spy)
    reply = _post(source_client, name)
    assert reply.status_code == 202
    assert _wait(source_client["client"], reply.json()["job"]["job_id"])["status"] == "done"
    assert seen == [wanted] and wanted
