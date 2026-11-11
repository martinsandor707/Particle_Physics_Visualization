"""Source tracking: what an experiment's source file looked like, and whether it still does.

The state machine (``calosrv/ingest/source_state.py``) is exercised on files in a
temporary drop folder against hand-made registry rows, so each state, the legacy
rule, settling and every reason an action is unavailable can be provoked without an
ingest. The provenance each origin records is then checked end to end: through the
pipeline, the upload and ingest-local routes, the seed, the drop-folder scan and
the command line.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import time
from pathlib import Path

import pytest

import contract_check
from calosrv.config import load_settings
from calosrv.db import archive, registry
from calosrv.ingest import source_state as ss

from conftest import SEED_CSV, SEED_FILE, rewrite_parquet, settled

NOW = 1_800_000_000.0  # a fixed "now", so ages are exact


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Settings with a drop folder and a distinct local folder, a 30 s settle window."""
    drop, local = tmp_path / "drop", tmp_path / "local"
    drop.mkdir()
    local.mkdir()
    monkeypatch.setenv("CALOSRV_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CALOSRV_AUTO_INGEST_DIR", str(drop))
    monkeypatch.setenv("CALOSRV_LOCAL_INGEST_DIR", str(local))
    monkeypatch.setenv("CALOSRV_AUTO_INGEST_SETTLE_S", "30")
    settings = load_settings()
    return settings, drop, local


def _file(folder: Path, name: str, content: bytes = b"0123456789" * 100, age: float = 3600.0) -> Path:
    path = folder / name
    path.write_bytes(content)
    return settled(path, age)


def _record(name: str, info: dict | None, *, status: str = registry.STATUS_READY,
            files: list[str] | None = None) -> registry.ExperimentRecord:
    return registry.ExperimentRecord(
        table_name=name, display_name=name, status=status, source_files=files or [],
        source_info=info or {})


def _info(settings, origin: str, path: Path, job_id: str = "job1") -> dict:
    return ss.make_info(ss.origin_spec(settings, origin, path), path, job_id)


# ----------------------------------------------------------- fingerprint --


def test_a_small_file_is_fingerprinted_over_its_size_and_all_of_its_bytes(tmp_path):
    path = tmp_path / "small.bin"
    path.write_bytes(b"abc" * 1000)
    expected = hashlib.blake2b(digest_size=16)
    expected.update((3000).to_bytes(8, "little"))
    expected.update(b"abc" * 1000)
    found = ss.fingerprint(path)
    assert found["bytes"] == 3000
    assert found["mtime_ns"] == path.stat().st_mtime_ns
    assert found["digest"] == expected.hexdigest() and len(found["digest"]) == 32


def test_a_large_file_is_fingerprinted_from_its_first_and_last_mebibyte_only(tmp_path):
    """Two reads, whatever the size: a change in the middle is below what the digest sees."""
    mib = 1 << 20
    body = bytearray(os.urandom(4 * mib))
    path = tmp_path / "large.bin"
    path.write_bytes(bytes(body))
    before = ss.fingerprint(path)
    expected = hashlib.blake2b(digest_size=16)
    expected.update(len(body).to_bytes(8, "little"))
    expected.update(bytes(body[:mib]))
    expected.update(bytes(body[-mib:]))
    assert before["digest"] == expected.hexdigest()
    body[2 * mib] ^= 0xFF
    path.write_bytes(bytes(body))
    assert ss.fingerprint(path)["digest"] == before["digest"]
    body[0] ^= 0xFF
    path.write_bytes(bytes(body))
    assert ss.fingerprint(path)["digest"] != before["digest"]
    body[0] ^= 0xFF
    body[-1] ^= 0xFF
    path.write_bytes(bytes(body))
    assert ss.fingerprint(path)["digest"] != before["digest"]


def test_the_digest_never_reads_more_than_two_mebibytes(tmp_path, monkeypatch):
    path = tmp_path / "big.bin"
    with path.open("wb") as handle:
        handle.truncate(64 * (1 << 20))  # a sparse 64 MiB file
    read = []
    real_open = Path.open

    class Counting:
        def __init__(self, handle):
            self._handle = handle

        def read(self, n=-1):
            data = self._handle.read(n)
            read.append(len(data))
            return data

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()

    monkeypatch.setattr(Path, "open", lambda self, *a, **k: Counting(real_open(self, *a, **k)))
    ss.fingerprint(path)
    assert sum(read) == 2 * (1 << 20)


# ------------------------------------------------------------ the record --


def test_the_record_holds_exactly_the_documented_keys(folders):
    settings, drop, _ = folders
    path = _file(drop, "run7.parquet")
    info = _info(settings, ss.ORIGIN_DROP_FOLDER, path, "abc123")
    assert set(info) == {"origin", "name", "relpath", "path", "bytes", "mtime_ns", "digest",
                         "recorded_at", "job_id"}
    assert info["origin"] == "drop_folder" and info["name"] == "run7.parquet"
    assert info["relpath"] == "run7.parquet" and info["path"] == str(path)
    assert info["bytes"] == path.stat().st_size and info["job_id"] == "abc123"
    assert info["recorded_at"].endswith("+00:00") and len(info["recorded_at"]) == 25


@pytest.mark.parametrize("origin, root_key, relpath, path_set", [
    (ss.ORIGIN_DROP_FOLDER, "drop", "nested/x.csv", True),
    (ss.ORIGIN_LOCAL, "local", "nested/x.csv", True),
    (ss.ORIGIN_UPLOAD, None, None, False),
    (ss.ORIGIN_SEED, None, None, True),
    (ss.ORIGIN_CLI, None, None, True),
])
def test_each_origin_says_where_the_file_came_from(folders, origin, root_key, relpath, path_set):
    settings, drop, local = folders
    root = {"drop": drop, "local": local, None: drop.parent}[root_key]
    (root / "nested").mkdir(exist_ok=True)
    source = _file(root / "nested", "x.csv")
    spec = ss.origin_spec(settings, origin, source, "x.csv", "j")
    assert spec["origin"] == origin and spec["name"] == "x.csv"
    assert spec["relpath"] == relpath
    assert (spec["path"] == str(source)) is path_set
    if origin == ss.ORIGIN_UPLOAD:
        assert spec["path"] is None and spec["relpath"] is None


def test_a_file_outside_its_origins_root_has_no_relpath(folders):
    settings, _, local = folders
    elsewhere = _file(local, "x.csv")
    assert ss.origin_spec(settings, ss.ORIGIN_DROP_FOLDER, elsewhere)["relpath"] is None


# ---------------------------------------------------------------- states --


def _state(settings, record, **kwargs):
    return ss.inspect(record, settings, now=kwargs.pop("now", time.time()), **kwargs)


def test_an_untouched_file_is_unchanged(folders):
    settings, drop, _ = folders
    path = _file(drop, "same.parquet")
    source = _state(settings, _record("same", _info(settings, "drop_folder", path)))
    assert (source.state, source.basis, source.detail) == ("unchanged", "recorded", "")
    assert source.origin == "drop_folder" and source.file == "same.parquet"
    assert source.path == str(path.resolve()) and source.settling is False
    assert source.recorded["bytes"] == source.current["bytes"] == path.stat().st_size
    assert source.recorded["modified"] == source.current["modified"]
    assert source.recorded["modified"].endswith("+00:00")


def test_a_different_size_is_changed_and_the_detail_says_both_sizes_and_times(folders):
    settings, drop, _ = folders
    path = _file(drop, "grow.parquet", b"x" * 2_873_386, age=5 * 86400)
    info = _info(settings, "drop_folder", path)
    path.write_bytes(b"y" * 2_911_002)
    settled(path, 3600)
    source = _state(settings, _record("grow", info))
    assert source.state == "changed"
    before = time.strftime("%Y-%m-%d %H:%M", time.gmtime(info["mtime_ns"] // 10**9))
    after = time.strftime("%Y-%m-%d %H:%M", time.gmtime(path.stat().st_mtime))
    assert source.detail == (f"Size 2,873,386 → 2,911,002 bytes; modified {before} → {after} UTC.")


def test_the_same_size_with_other_content_is_changed(folders):
    settings, drop, _ = folders
    path = _file(drop, "swap.parquet", b"a" * 5000 + b"b" * 5000)
    info = _info(settings, "drop_folder", path)
    path.write_bytes(b"c" * 5000 + b"b" * 5000)
    settled(path, 1800)
    source = _state(settings, _record("swap", info))
    assert source.state == "changed"
    assert source.detail.startswith("Same size (10,000 bytes) but different content; modified ")
    assert source.detail.endswith(" UTC.")


def test_a_moved_time_with_the_same_sampled_content_is_touched(folders):
    settings, drop, _ = folders
    path = _file(drop, "touch.parquet")
    info = _info(settings, "drop_folder", path)
    settled(path, 1800)
    source = _state(settings, _record("touch", info))
    assert source.state == "touched"
    assert source.detail.endswith("UTC; the size and sampled content are unchanged.")
    assert source.detail.startswith("Modified ")


def test_a_digest_is_computed_only_when_the_size_is_equal_and_the_time_moved(folders, monkeypatch):
    settings, drop, _ = folders
    path = _file(drop, "lazy.parquet")
    info = _info(settings, "drop_folder", path)
    calls = []
    real = ss.fingerprint
    monkeypatch.setattr(ss, "fingerprint", lambda p: calls.append(p) or real(p))
    _state(settings, _record("lazy", info))                  # untouched
    path.write_bytes(b"much longer than before" * 100)       # size differs
    _state(settings, _record("lazy", info))
    assert calls == []
    path.write_bytes(b"0123456789" * 100)                    # the size again, the time moved
    settled(path, 100)
    _state(settings, _record("lazy", info))
    assert len(calls) == 1


def test_a_deleted_file_is_missing_and_the_detail_names_it(folders):
    settings, drop, _ = folders
    path = _file(drop, "gone.parquet")
    info = _info(settings, "drop_folder", path)
    path.unlink()
    source = _state(settings, _record("gone", info))
    assert source.state == "missing" and source.current is None
    assert source.recorded["bytes"] == info["bytes"]
    assert source.detail == f"Not found: gone.parquet in {drop}."


def test_an_unset_root_is_missing_not_untracked(folders):
    settings, drop, _ = folders
    info = _info(settings, "drop_folder", _file(drop, "r.parquet"))
    source = _state(dataclasses.replace(settings, auto_ingest_dir=None), _record("r", info))
    assert source.state == "missing"
    assert "CALOSRV_AUTO_INGEST_DIR" in source.detail


def test_a_relpath_that_leaves_the_root_or_follows_a_link_out_is_not_found(folders):
    settings, drop, _ = folders
    outside = _file(drop.parent, "outside.parquet")
    info = _info(settings, "drop_folder", _file(drop, "in.parquet"))
    assert _state(settings, _record("x", {**info, "relpath": "../outside.parquet"})).state == "missing"
    (drop / "link.parquet").symlink_to(outside)
    assert _state(settings, _record("x", {**info, "relpath": "link.parquet"})).state == "missing"


def test_a_local_origin_is_looked_for_in_the_local_folder(folders):
    settings, drop, local = folders
    path = _file(local, "viaapi.parquet")
    info = _info(settings, "local", path)
    assert _state(settings, _record("viaapi", info)).state == "unchanged"
    path.write_bytes(b"different")
    assert _state(settings, _record("viaapi", info)).state == "changed"
    assert _state(dataclasses.replace(settings, local_ingest_dir=None),
                  _record("viaapi", info)).state == "missing"


def test_an_upload_and_the_seed_are_untracked_with_their_own_sentences(folders):
    settings, _, _ = folders
    upload = _record("up", {"origin": "upload", "name": "mine.csv", "relpath": None, "path": None,
                            "bytes": 5, "mtime_ns": 1, "digest": "d", "job_id": "j"})
    source = _state(settings, upload)
    assert (source.state, source.origin, source.file) == ("untracked", "upload", "mine.csv")
    assert source.detail == ("Uploaded through the browser; the staged copy was deleted after "
                             "the ingest.")
    assert source.path is None
    seeded = _record("seeded", {"origin": "seed", "name": SEED_FILE.name, "path": str(SEED_FILE),
                                "relpath": None, "bytes": 1, "mtime_ns": 1, "digest": "d"})
    source = _state(settings, seeded)
    assert source.state == "untracked" and source.origin == "seed"
    assert source.detail == f"The demonstration dataset ships in the image ({SEED_FILE})."


def test_the_baseline_is_always_the_seed_whatever_its_row_says(folders):
    settings, drop, _ = folders
    settings = dataclasses.replace(settings, seed_csv=SEED_FILE)
    info = _info(settings, "drop_folder", _file(drop, "experiment_baseline.parquet"))
    for row in (info, {}):
        source = _state(settings, _record(ss.BASELINE_TABLE, row))
        assert (source.state, source.origin, source.path) == ("untracked", "seed", None)
        assert source.file == SEED_FILE.name
        assert source.detail == f"The demonstration dataset ships in the image ({SEED_FILE})."
    assert _state(settings, _record(ss.BASELINE_TABLE, info)).basis == "recorded"
    assert _state(settings, _record(ss.BASELINE_TABLE, {})).basis == "none"


def test_a_command_line_ingest_is_tracked_only_inside_the_folders_the_server_reads(folders, tmp_path):
    settings, drop, local = folders
    outside = _file(tmp_path, "cli_out.parquet")
    info = _info(settings, "cli", outside)
    source = _state(settings, _record("cliout", info))
    assert source.state == "untracked" and source.origin == "cli"
    assert source.why == (f"Ingested from the command line from {outside}, outside the "
                          "folders the server reads.")
    inside = _file(drop, "cli_in.parquet")
    info = _info(settings, "cli", inside)
    assert _state(settings, _record("cliin", info)).state == "unchanged"
    inside.write_bytes(b"changed")
    assert _state(settings, _record("cliin", info)).state == "changed"
    held = _file(local, "cli_local.parquet")
    assert _state(settings, _record("clilocal", _info(settings, "cli", held))).state == "unchanged"


# --------------------------------------------------------------- settling --


def test_a_file_modified_inside_the_settle_window_is_settling_whatever_its_state(folders):
    settings, drop, _ = folders
    path = _file(drop, "fresh.parquet", age=3600)
    info = _info(settings, "drop_folder", path)
    path.write_bytes(b"new content, new size")
    settled(path, 5)
    source = _state(settings, _record("fresh", info))
    assert source.state == "changed" and source.settling is True
    settled(path, 31)
    assert _state(settings, _record("fresh", info)).settling is False
    assert _state(dataclasses.replace(settings, auto_ingest_settle_s=0),
                  _record("fresh", info)).settling is False


# ------------------------------------------------------------ legacy rows --


def _manifest(*parts) -> archive.Manifest:
    return archive.Manifest("hits_all_models", 1, list(parts))


def _part(source_name: str, source_bytes: int, written_at: str = "2026-10-28T16:47:08+00:00",
          index: int = 0) -> archive.ArchivePart:
    return archive.ArchivePart(
        file=f"part-{index:05d}.parquet", rows=10, bytes=5, source_name=source_name,
        source_bytes=source_bytes, event_offset=0, event_min=0, event_max=1,
        written_at=written_at, duckdb_version="x")


def test_a_legacy_row_is_judged_by_its_archive_part_and_the_drop_folder(folders):
    settings, drop, _ = folders
    path = _file(drop, "legacy_run.parquet", b"z" * 4000, age=40 * 86400)
    # Archived long after the file was written: unchanged.
    archived = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 30 * 86400))
    manifest = _manifest(_part("legacy_run.parquet", 4000, written_at=archived))
    source = _state(settings, _record("legacy_run", None), manifest=manifest)
    assert (source.state, source.basis, source.origin) == ("unchanged", "legacy", "drop_folder")
    assert source.recorded == {"bytes": 4000, "modified": None}
    assert source.current["bytes"] == 4000
    assert source.detail == "Recorded before source tracking: compared by size only."
    assert source.path == str(path.resolve())


def test_a_legacy_row_is_changed_only_when_the_size_differs(folders):
    settings, drop, _ = folders
    path = _file(drop, "legacy_run.parquet", b"z" * 5000, age=3600)
    manifest = _manifest(_part("legacy_run.parquet", 4000))
    by_size = _state(settings, _record("legacy_run", None), manifest=manifest)
    assert by_size.state == "changed" and by_size.basis == "legacy"
    assert by_size.detail.startswith("Size 4,000 → 5,000 bytes; modified ")
    assert by_size.detail.endswith("UTC; recorded before source tracking.")
    assert path.exists()


def test_a_legacy_row_with_the_recorded_size_is_unchanged_however_new_the_file_is(folders):
    """Martin's ``hits_all_models``: archived 2026-09-29 from a CSV, the same rows written as
    Parquet of the very size the manifest recorded on 2026-10-28. A later mtime at an equal
    size is no evidence of a change: the part keeps no mtime and no digest to compare."""
    settings, drop, _ = folders
    path = _file(drop, "hits_all_models.parquet", b"p" * 6000, age=3600)
    stamp = time.mktime(time.strptime("2026-10-28 15:47", "%Y-%m-%d %H:%M"))
    os.utime(path, (stamp, stamp))
    manifest = _manifest(_part("hits_all_models.parquet", 6000,
                               written_at="2026-09-29T17:15:42+00:00"))
    source = _state(settings, _record("hits_all_models", None), manifest=manifest, now=stamp + 86400)
    assert (source.state, source.basis) == ("unchanged", "legacy")
    assert source.detail == "Recorded before source tracking: compared by size only."
    assert source.as_dict()["state"] == "unchanged"
    record = _record("hits_all_models", None)
    # Re-ingest is offered only with force, and the reason is the unchanged one.
    refused = ss.reingest_reason(record, source, settings, parts=1, job_active=False, force=False)
    assert refused == "Its source file is unchanged since it was ingested."
    assert ss.reingest_reason(record, source, settings, parts=1, job_active=False,
                              force=True) is None


def test_a_legacy_row_whose_file_is_gone_is_missing_and_one_with_no_match_is_untracked(folders):
    settings, _, _ = folders
    manifest = _manifest(_part("legacy_run.parquet", 4000))
    gone = _state(settings, _record("legacy_run", None), manifest=manifest)
    assert (gone.state, gone.basis) == ("missing", "legacy")
    assert gone.detail == f"Not found: legacy_run.parquet in {settings.auto_ingest_dir}."
    other = _state(settings, _record("another_name", None, files=["legacy_run.parquet"]),
                   manifest=manifest)
    assert (other.state, other.basis, other.origin) == ("untracked", "none", None)
    two = _manifest(_part("legacy_run.parquet", 1), _part("Legacy Run.csv", 1, index=1))
    ambiguous = _state(settings, _record("legacy_run", None), manifest=two)
    assert (ambiguous.state, ambiguous.basis) == ("untracked", "none")
    assert _state(settings, _record("legacy_run", None), manifest=None).basis == "none"


def test_a_row_with_a_record_has_the_recorded_basis(folders):
    settings, drop, _ = folders
    info = _info(settings, "drop_folder", _file(drop, "r.parquet"))
    assert _state(settings, _record("r", info)).basis == "recorded"


# ---------------------------------------------------------------- actions --


def _actions(settings, record, source, parts=1, active=False):
    return ss.actions(record, source, settings, parts=parts, job_active=active)


def _changed(folders, name="c"):
    settings, drop, _ = folders
    path = _file(drop, f"{name}.parquet")
    info = _info(settings, "drop_folder", path)
    path.write_bytes(b"new bytes of another length")
    settled(path, 600)
    return settings, _record(name, info), _state(settings, _record(name, info))


def test_reingest_is_offered_only_for_a_ready_changed_settled_single_part_idle_experiment(folders):
    settings, record, source = _changed(folders)
    offered = _actions(settings, record, source)
    assert offered["reingest"] == {"available": True, "reason": None}
    assert offered["retry"] == {"available": False, "reason": "Only a failed experiment is retried."}


@pytest.mark.parametrize("change, reason", [
    (lambda r: setattr(r, "status", "failed"), "A failed experiment is retried, not re-ingested."),
    (lambda r: setattr(r, "status", "ingesting"), "It is still being ingested."),
    (lambda r: setattr(r, "status", "pending"), "It is still being ingested."),
])
def test_reingest_says_why_by_status(folders, change, reason):
    settings, record, source = _changed(folders)
    change(record)
    assert _actions(settings, record, source)["reingest"] == {"available": False, "reason": reason}


def test_reingest_says_why_for_a_job_an_upload_the_seed_and_a_cli_file_outside(folders, tmp_path):
    settings, record, source = _changed(folders)
    assert _actions(settings, record, source, active=True)["reingest"]["reason"] == (
        "A job for this experiment is queued or running.")
    upload = _record("up", {"origin": "upload", "name": "m.csv", "bytes": 1, "mtime_ns": 1})
    assert _actions(settings, upload, _state(settings, upload))["reingest"]["reason"] == (
        "It was uploaded through the browser: there is no file on the server to re-ingest from.")
    seeded = _record("sd", {"origin": "seed", "name": "s.parquet", "bytes": 1, "mtime_ns": 1})
    assert _actions(settings, seeded, _state(settings, seeded))["reingest"]["reason"] == (
        "The demonstration dataset ships in the image and is never re-ingested.")
    out = _file(tmp_path, "o.parquet")
    cli = _record("cl", _info(settings, "cli", out))
    state = _state(settings, cli)
    assert _actions(settings, cli, state)["reingest"]["reason"] == state.why
    assert "outside the folders the server reads" in state.why


def test_reingest_says_why_for_a_missing_file_a_settling_one_append_and_an_unchanged_one(folders):
    settings, drop, _ = folders
    path = _file(drop, "m.parquet")
    info = _info(settings, "drop_folder", path)
    path.unlink()
    record = _record("m", info)
    assert _actions(settings, record, _state(settings, record))["reingest"]["reason"] == (
        f"Its source file m.parquet is not in {drop}.")

    settings, record, source = _changed(folders, "s")
    path = drop / "s.parquet"
    settled(path, 12)
    source = _state(settings, record, now=time.time())
    reason = _actions(settings, record, source)["reingest"]["reason"]
    assert reason.startswith("The file was modified 12 s ago; Re-ingest is offered once it has "
                             "been unchanged for 30 s.") or reason.startswith(
        "The file was modified 13 s ago;")
    settled(path, 600)
    source = _state(settings, record)
    assert _actions(settings, record, source, parts=3)["reingest"]["reason"] == (
        "It was assembled from 3 files by append; replace it from Upload dataset instead.")

    same = _record("u", _info(settings, "drop_folder", _file(drop, "u.parquet")))
    assert _actions(settings, same, _state(settings, same))["reingest"]["reason"] == (
        "Its source file is unchanged since it was ingested.")
    touched = _record("t", _info(settings, "drop_folder", _file(drop, "t.parquet")))
    settled(drop / "t.parquet", 1800)
    assert _actions(settings, touched, _state(settings, touched))["reingest"]["reason"] == (
        "Its source file is unchanged since it was ingested.")


def test_force_lifts_only_the_unchanged_reason(folders):
    settings, drop, _ = folders
    record = _record("f", _info(settings, "drop_folder", _file(drop, "f.parquet")))
    source = _state(settings, record)
    assert ss.reingest_reason(record, source, settings, parts=1, job_active=False) is not None
    assert ss.reingest_reason(record, source, settings, parts=1, job_active=False, force=True) is None
    # Every other reason stands.
    assert ss.reingest_reason(record, source, settings, parts=2, job_active=False, force=True) \
        == "It was assembled from 2 files by append; replace it from Upload dataset instead."
    assert ss.reingest_reason(record, source, settings, parts=1, job_active=True, force=True) \
        == "A job for this experiment is queued or running."
    record.status = "failed"
    assert ss.reingest_reason(record, source, settings, parts=1, job_active=False, force=True) \
        == "A failed experiment is retried, not re-ingested."


def test_retry_is_offered_for_a_failed_experiment_whose_file_resolves_and_has_settled(folders):
    settings, drop, _ = folders
    path = _file(drop, "r.parquet")
    record = _record("r", _info(settings, "drop_folder", path), status="failed")
    source = _state(settings, record)
    assert _actions(settings, record, source)["retry"] == {"available": True, "reason": None}
    # Whatever state the file is in: a retry reads the file as it is now.
    path.write_bytes(b"other")
    settled(path, 600)
    assert _actions(settings, record, _state(settings, record))["retry"]["available"] is True
    assert _actions(settings, record, _state(settings, record))["reingest"]["reason"] == (
        "A failed experiment is retried, not re-ingested.")


def test_retry_says_why_not(folders, tmp_path):
    settings, drop, _ = folders
    path = _file(drop, "r.parquet")
    info = _info(settings, "drop_folder", path)
    ready = _record("r", info)
    assert _actions(settings, ready, _state(settings, ready))["retry"]["reason"] == (
        "Only a failed experiment is retried.")
    path.unlink()
    failed = _record("r", info, status="failed")
    assert _actions(settings, failed, _state(settings, failed))["retry"]["reason"] == (
        f"Its source file r.parquet is not in {drop}; ingest it again from Upload dataset with "
        "Replace ticked.")
    upload = _record("u", {"origin": "upload", "name": "mine.csv", "bytes": 1, "mtime_ns": 1},
                     status="failed")
    reason = _actions(settings, upload, _state(settings, upload))["retry"]["reason"]
    assert reason == ("Its source file mine.csv is not on the server; ingest it again from "
                      "Upload dataset with Replace ticked.")
    path = _file(drop, "s.parquet", age=3)
    settling = _record("s", _info(settings, "drop_folder", path), status="failed")
    assert "was modified" in _actions(settings, settling, _state(settings, settling))["retry"]["reason"]
    settled(path, 600)
    assert _actions(settings, settling, _state(settings, settling), active=True)["retry"]["reason"] \
        == "A job for this experiment is queued or running."


def test_every_state_and_origin_the_contract_lists_is_the_one_the_module_names():
    contract = contract_check.load("admin_experiments")["$defs"]
    assert contract["state"]["enum"] == list(ss.STATES)
    assert contract["origin"]["enum"] == list(ss.ORIGINS)


# ------------------------------------ every origin records source_info --


def _wait(client, job_id: str, timeout: float = 120.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/upload/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError("the job did not finish")


def _row(source_client, name: str) -> registry.ExperimentRecord:
    with source_client["database"].read_cursor() as con:
        return registry.get_experiment(con, name)


def test_the_seed_records_its_source(source_client):
    info = _row(source_client, "experiment_baseline").source_info
    assert info["origin"] == "seed" and info["name"] == SEED_FILE.name
    assert info["relpath"] is None and info["path"].endswith(SEED_FILE.name)
    assert info["bytes"] == SEED_FILE.stat().st_size and len(info["digest"]) == 32


def test_the_drop_folder_scan_records_its_source(source_client):
    row = _row(source_client, "dropped_run")
    info = row.source_info
    assert row.is_ready
    assert info["origin"] == "drop_folder" and info["name"] == "dropped_run.parquet"
    assert info["relpath"] == "dropped_run.parquet"
    path = source_client["drop"] / "dropped_run.parquet"
    assert info["path"] == str(path) and info["bytes"] == path.stat().st_size
    assert info["mtime_ns"] == path.stat().st_mtime_ns
    assert ss.fingerprint(path)["digest"] == info["digest"]
    assert info["job_id"] and info["recorded_at"]


def test_the_ingest_local_route_records_its_source(source_client):
    client, local = source_client["client"], source_client["local"]
    reply = client.post("/api/ingest-local", data={
        "path": "local_run.parquet", "table_name": "local_run", "mode": "create_new"})
    assert reply.status_code == 202, reply.text
    job = _wait(client, reply.json()["job"]["job_id"])
    assert job["status"] == "done", job
    info = _row(source_client, "local_run").source_info
    assert info["origin"] == "local" and info["relpath"] == "local_run.parquet"
    assert info["path"] == str((local / "local_run.parquet").resolve())
    assert info["job_id"] == job["job_id"]


def test_the_upload_route_records_its_source_without_a_path(source_client):
    client = source_client["client"]
    reply = client.post(
        "/api/upload", files={"file": ("browser_copy.csv", SEED_CSV.read_bytes(), "text/csv")},
        data={"table_name": "uploaded_run", "mode": "create_new"})
    assert reply.status_code == 202, reply.text
    job = _wait(client, reply.json()["job"]["job_id"])
    assert job["status"] == "done", job
    info = _row(source_client, "uploaded_run").source_info
    assert info["origin"] == "upload" and info["name"] == "browser_copy.csv"
    assert info["relpath"] is None and info["path"] is None
    assert info["job_id"] == job["job_id"]
    view = {e["table_name"]: e for e in client.get("/api/admin/experiments").json()["experiments"]}
    assert view["uploaded_run"]["source"]["state"] == "untracked"
    assert view["uploaded_run"]["source"]["origin"] == "upload"


def test_the_command_line_direct_mode_records_its_source(ingested, tmp_path, monkeypatch):
    from calosrv.db.bootstrap import drop_experiment
    from calosrv.ingest import cli

    source = settled(rewrite_parquet(SEED_FILE, tmp_path / "from_cli.parquet"))
    monkeypatch.setattr(cli, "load_settings", lambda: ingested["settings"])
    monkeypatch.setattr(cli, "get_database", lambda settings: ingested["database"])
    args = cli.build_parser().parse_args(
        ["--input", str(source), "--table", "cli_run", "--direct", "--no-sample"])
    try:
        assert cli.run(args) == 0
        with ingested["database"].read_cursor() as con:
            info = registry.get_experiment(con, "cli_run").source_info
        assert info["origin"] == "cli" and info["name"] == "from_cli.parquet"
        assert info["path"] == str(source.resolve()) and info["relpath"] is None
    finally:
        with ingested["database"].write_lock() as con:
            drop_experiment(con, "cli_run", ingested["settings"])


def test_a_replacing_ingest_rewrites_the_record_and_an_append_leaves_it(ingested, tmp_path):
    from calosrv.db.bootstrap import drop_experiment
    from calosrv.ingest import pipeline

    database, settings = ingested["database"], ingested["settings"]
    first = settled(rewrite_parquet(SEED_FILE, tmp_path / "first.parquet"))
    second = settled(rewrite_parquet(SEED_FILE, tmp_path / "second.parquet", event_shift=100))
    spec = lambda p: ss.origin_spec(settings, "cli", p)  # noqa: E731
    try:
        with database.write_lock() as con:
            pipeline.run_ingest(con, settings, "rec_run", first, build_sample=False,
                                provenance=spec(first))
            created = registry.get_experiment(con, "rec_run").source_info
            pipeline.run_ingest(con, settings, "rec_run", second, mode="append",
                                build_sample=False, provenance=spec(second))
            appended = registry.get_experiment(con, "rec_run").source_info
            pipeline.run_ingest(con, settings, "rec_run", second, build_sample=False,
                                force_reingest=True, provenance=spec(second))
            replaced = registry.get_experiment(con, "rec_run").source_info
        assert created["name"] == "first.parquet" and appended == created
        assert replaced["name"] == "second.parquet" and replaced["bytes"] == second.stat().st_size
    finally:
        with database.write_lock() as con:
            drop_experiment(con, "rec_run", settings)


def test_a_failed_load_still_has_the_fingerprint(ingested, tmp_path):
    """The record is taken before the file is read and stored when the row is marked ingesting."""
    from calosrv.db.bootstrap import drop_experiment
    from calosrv.ingest import load, pipeline

    database, settings = ingested["database"], ingested["settings"]
    source = settled(rewrite_parquet(SEED_FILE, tmp_path / "doomed.parquet"))

    def explode(*args, **kwargs):
        raise RuntimeError("disk on fire")

    real = load.load_source
    load.load_source = explode
    try:
        with database.write_lock() as con:
            with pytest.raises(RuntimeError):
                pipeline.run_ingest(con, settings, "doomed_run", source, build_sample=False,
                                    provenance=ss.origin_spec(settings, "cli", source))
            info = registry.get_experiment(con, "doomed_run").source_info
        assert info["bytes"] == source.stat().st_size and info["digest"]
    finally:
        load.load_source = real
        with database.write_lock() as con:
            drop_experiment(con, "doomed_run", settings)


# ------------------------------------------------ the GET and its contract --


def test_get_admin_experiments_satisfies_its_contract_and_lists_every_experiment(source_client):
    client = source_client["client"]
    body = client.get("/api/admin/experiments").json()
    contract_check.check(body, "admin_experiments")
    assert body["roots"] == {"drop_folder": str(source_client["drop"]),
                             "local": str(source_client["local"]), "settle_s": 0}
    assert body["states"] == list(ss.STATES) and body["origins"] == list(ss.ORIGINS)
    listed = [e["table_name"] for e in body["experiments"]]
    with source_client["database"].read_cursor() as con:
        assert listed == [r.table_name for r in registry.list_experiments(con)]
    view = {e["table_name"]: e for e in body["experiments"]}
    dropped = view["dropped_run"]
    assert dropped["source"]["state"] == "unchanged" and dropped["source"]["basis"] == "recorded"
    assert dropped["source"]["origin"] == "drop_folder" and dropped["source_changed"] is False
    assert dropped["archive_parts"] == 1 and dropped["kind"] == "two_shower_hits"
    assert dropped["actions"]["reingest"]["reason"] == (
        "Its source file is unchanged since it was ingested.")
    assert view["experiment_baseline"]["source"]["origin"] == "seed"
    assert view["experiment_baseline"]["source"]["path"] is None
    assert dropped["job"]["mode"] == "create_new" and dropped["job"]["status"] == "done"
    assert set(dropped["job"]) == {"job_id", "mode", "status", "progress", "stage_label",
                                   "error", "finished_at"}


def test_the_get_marks_a_changed_file_and_reads_nothing_else(source_client):
    client, drop = source_client["client"], source_client["drop"]
    path = drop / "dropped_run.parquet"
    original = path.read_bytes()
    rewrite_parquet(SEED_FILE, drop / "tmp_copy.parquet", compression="zstd")
    path.write_bytes((drop / "tmp_copy.parquet").read_bytes())
    (drop / "tmp_copy.parquet").unlink()
    settled(path, 3600)
    try:
        view = {e["table_name"]: e for e in client.get("/api/admin/experiments").json()["experiments"]}
        entry = view["dropped_run"]
        assert entry["source_changed"] is True and entry["source"]["state"] == "changed"
        assert entry["source"]["detail"].startswith("Size ")
        assert entry["actions"]["reingest"] == {"available": True, "reason": None}
        assert view["local_run"]["source"]["state"] == "unchanged"
    finally:
        path.write_bytes(original)
        os.utime(path, ns=(_row(source_client, "dropped_run").source_info["mtime_ns"],) * 2)
    again = {e["table_name"]: e for e in client.get("/api/admin/experiments").json()["experiments"]}
    assert again["dropped_run"]["source"]["state"] == "unchanged"


def test_sentences_carry_the_true_minus_and_paths_stay_verbatim(source_client):
    from calosrv.text import signed_hyphens

    body = client_body = source_client["client"].get("/api/admin/experiments").json()
    for entry in client_body["experiments"]:
        for sentence in (entry["source"]["detail"], entry["actions"]["reingest"]["reason"],
                         entry["actions"]["retry"]["reason"], entry["error"] or ""):
            assert signed_hyphens(sentence) == []
    assert body["roots"]["drop_folder"] == str(source_client["drop"])
