"""The hf-sync downloader (deploy/hf_sync.py), exercised with a fake Hub: no network, no real ``hf`` call.

The fake downloader behaves as ``huggingface_hub`` does where it matters here: an outdated file is
unlinked before the new bytes are written, and a file whose content already matches is adopted
without being rewritten. Every root is a temporary folder under pytest's basetemp. ``setuid`` is
never called: the privilege drop is tested as the pure decision it is.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from huggingface_hub.errors import (
    GatedRepoError,
    HfHubHTTPError,
    OfflineModeIsEnabled,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "deploy" / "hf_sync.py"

_spec = importlib.util.spec_from_file_location("hf_sync_under_test", SCRIPT)
hf = importlib.util.module_from_spec(_spec)
sys.modules["hf_sync_under_test"] = hf  # dataclasses resolve their module through sys.modules
_spec.loader.exec_module(hf)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
COMMIT2 = "fedcba9876543210fedcba9876543210fedcba98"


def http_error(cls, status: int):
    request = httpx2.Request("GET", "https://huggingface.co/api/datasets/x/y")
    return cls(f"{status} error", response=httpx2.Response(status, request=request))


class FakeHub:
    """Serves ``content`` ({path: bytes}) as the dataset's one commit."""

    def __init__(self, root: Path, content: dict[str, bytes], commit: str = COMMIT):
        self.root = root
        self.content = dict(content)
        self.commit = commit
        self.resolve_error = None
        self.list_error = None
        self.download_errors: dict[str, list[BaseException]] = {}  # raised in turn, before and after the unlink
        self.fail_after_unlink: set[str] = set()
        self.calls: list[dict] = []
        self.resolves = 0

    # --- the dataset
    def file(self, path: str):
        data = self.content[path]
        digest = hashlib.sha256(data).hexdigest()
        if path.endswith(".parquet"):
            return SimpleNamespace(path=path, size=len(data), blob_id="git-" + digest[:8],
                                   lfs=SimpleNamespace(sha256=digest))
        return SimpleNamespace(path=path, size=len(data), blob_id=hashlib.sha1(data).hexdigest(), lfs=None)

    # --- the three hub calls
    def resolve(self, repo, revision):
        self.resolves += 1
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.commit

    def list_files(self, repo, commit):
        if self.list_error is not None:
            raise self.list_error
        return [self.file(p) for p in sorted(self.content)]

    def download(self, repo, path, commit, local_dir, force):
        self.calls.append({"path": path, "commit": commit, "force": force, "local_dir": local_dir, "repo": repo})
        dest = Path(local_dir) / path
        data = self.content[path]
        if not force and dest.exists() and dest.read_bytes() == data:
            return str(dest)  # adopted: hashed and found to match
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)  # as hf_hub_download does, before the download
        queue = self.download_errors.get(path)
        if queue:
            raise queue.pop(0)
        if path in self.fail_after_unlink:
            raise http_error(HfHubHTTPError, 503)
        dest.write_bytes(data)
        return str(dest)

    def downloads(self) -> list[str]:
        return [c["path"] for c in self.calls]


@pytest.fixture
def root(tmp_path):
    (tmp_path / "ingest").mkdir()
    (tmp_path / "xgboost_models").mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    pauses = []
    monkeypatch.setattr(hf, "sleep", pauses.append)
    return pauses


CONTENT = {
    "ingest/a.parquet": b"A" * 300,
    "ingest/b.parquet": b"B" * 500,
    "xgboost_models/xgboost_pion/standalone_energy_s1_model.json": b'{"m": 1}',
}


def env_for(root: Path, **extra) -> dict:
    return {"HF_SYNC_ROOT": str(root), **extra}


def run_main(root, hub, capsys, *argv, **env):
    code = hf.main(list(argv), env_for(root, **env), hub)
    return code, capsys.readouterr().out


def record_of(root: Path) -> dict:
    return json.loads((root / "ingest" / ".hf-sync" / "last-sync.json").read_text())


def first_sync(root, capsys, content=None):
    hub = FakeHub(root, content or CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0, out
    return hub


# --------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["0", "false", "FALSE", "No", " off "])
def test_skip_prints_one_line_and_never_touches_the_hub(root, capsys, word):
    class Boom:
        def __getattr__(self, name):
            raise AssertionError("the hub must not be used when HF_SYNC is off")

    code, out = run_main(root, Boom(), capsys, HF_SYNC=word)
    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("hf-sync: ") and "skipped" in lines[0]
    assert not (root / "ingest" / ".hf-sync").exists() and not (root / ".cache").exists()


def test_default_patterns_equal_the_readmes_two():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.lstrip().startswith(".venv/bin/hf download"))
    readme = tuple(re.findall(r'--include "([^"]+)"', line))
    assert len(readme) == 2
    assert hf.parse_patterns(None) == readme
    assert hf.parse_patterns("") == readme
    assert tuple(hf.DEFAULT_INCLUDE.split(",")) == readme
    assert hf.read_config({}).patterns == readme


def test_the_documented_defaults():
    cfg = hf.read_config({})
    assert cfg.enabled and not cfg.overwrite
    assert cfg.repo == "martinsandor707/particles_combined_all_models"
    assert cfg.revision == "main" and cfg.root == Path("/sync")


def test_patterns_are_matched_like_hf_and_stay_inside_the_two_mounts():
    files = [SimpleNamespace(path=p, size=1, blob_id="x", lfs=None) for p in [
        "ingest/a.parquet", "ingest/README.md", "ingest/sub/c.parquet",
        "xgboost_models/xgboost_pion/m.json", "xgboost_models/notes.txt",
        "other/z.parquet", "ingest/../escape.parquet", "/abs.parquet", "ingest//odd.parquet", ".gitattributes"]]
    chosen = [e.path for e in hf.select_files(files, ("ingest/*.parquet", "xgboost_models/*.json"))]
    assert chosen == ["ingest/a.parquet", "ingest/sub/c.parquet", "xgboost_models/xgboost_pion/m.json"]
    # Even a pattern that matches everything cannot reach the README or anything outside the mounts.
    chosen = [e.path for e in hf.select_files(files, ("*",))]
    assert "ingest/README.md" not in chosen and "other/z.parquet" not in chosen
    assert "ingest/../escape.parquet" not in chosen and ".gitattributes" not in chosen


def test_the_etag_is_the_lfs_sha256_else_the_blob_id(root):
    hub = FakeHub(root, CONTENT)
    by_path = {e.path: e for e in hf.select_files(hub.list_files("r", COMMIT), hf.parse_patterns(None))}
    assert by_path["ingest/a.parquet"].etag == hashlib.sha256(CONTENT["ingest/a.parquet"]).hexdigest()
    small = "xgboost_models/xgboost_pion/standalone_energy_s1_model.json"
    assert by_path[small].etag == hashlib.sha1(CONTENT[small]).hexdigest()


# --------------------------------------------------------------------------------------------
# The privilege decision (never call setuid)
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("euid, uid, gid, expected", [
    (0, 1000, 1000, (1000, 1000)),   # root, a user's folder: become the user
    (0, 501, 20, (501, 20)),
    (0, 0, 0, None),                 # root's own folder: stay root
    (1000, 1000, 1000, None),        # already a user: nothing to do
    (1000, 0, 0, None),
])
def test_privilege_drop_decision(euid, uid, gid, expected):
    assert hf.plan_privilege_drop(euid, uid, gid) == expected


def test_main_drops_to_the_owner_of_ingest_in_the_right_order(root, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(hf.os, "geteuid", lambda: 0)
    monkeypatch.setattr(hf.os, "setgroups", lambda g: calls.append(("setgroups", tuple(g))))
    monkeypatch.setattr(hf.os, "setgid", lambda g: calls.append(("setgid", g)))
    monkeypatch.setattr(hf.os, "setuid", lambda u: calls.append(("setuid", u)))
    st = (root / "ingest").stat()
    # Pretend the folder belongs to someone else.
    monkeypatch.setattr(hf, "plan_privilege_drop", lambda euid, u, g: (4242, 4343))
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert calls == [("setgroups", ()), ("setgid", 4343), ("setuid", 4242)]
    assert "uid 4242, gid 4343" in out
    assert st.st_uid  # (the real owner was not root, so the unpatched decision would also have dropped)


def test_a_non_root_process_never_drops(root, capsys, monkeypatch):
    monkeypatch.setattr(hf.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(hf, "drop_privileges", lambda *a: pytest.fail("must not drop"))
    first_sync(root, capsys)


# --------------------------------------------------------------------------------------------
# First sync, the record, the link
# --------------------------------------------------------------------------------------------

def test_first_sync_downloads_everything_and_records_it(root, capsys):
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert sorted(hub.downloads()) == sorted(CONTENT)
    assert all(c["commit"] == COMMIT and not c["force"] and c["local_dir"] == str(root) for c in hub.calls)
    assert all(c["repo"] == "martinsandor707/particles_combined_all_models" for c in hub.calls)
    for path, data in CONTENT.items():
        assert (root / path).read_bytes() == data
    rec = record_of(root)
    assert rec["repo"] == "martinsandor707/particles_combined_all_models"
    assert rec["revision"] == "main" and rec["commit"] == COMMIT and rec["synced_at"]
    assert set(rec["files"]) == set(CONTENT)
    for path, data in CONTENT.items():
        st = (root / path).stat()
        assert rec["files"][path] == {"bytes": len(data), "mtime_ns": st.st_mtime_ns,
                                      "etag": hub.file(path).lfs.sha256 if path.endswith(".parquet")
                                      else hub.file(path).blob_id}
    assert "Downloading ingest/a.parquet (300 B)" in out
    assert "done in" in out
    assert "3 files examined: 3 downloaded (808 B), 0 updated, 0 unchanged, 0 kept." in out
    assert all(l.startswith("hf-sync: ") for l in out.strip().splitlines())


def test_unchanged_files_cost_no_download_call(root, capsys):
    first_sync(root, capsys)
    again = FakeHub(root, CONTENT)
    code, out = run_main(root, again, capsys)
    assert code == 0 and again.calls == []
    assert "3 unchanged" in out and "0 downloaded" in out


def test_upstream_update_replaces_only_the_changed_file(root, capsys):
    first_sync(root, capsys)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert hub.downloads() == ["ingest/a.parquet"]
    assert hub.calls[0]["force"] is True and hub.calls[0]["commit"] == COMMIT2
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320
    rec = record_of(root)
    assert rec["commit"] == COMMIT2 and rec["files"]["ingest/a.parquet"]["bytes"] == 320
    assert "1 updated (320 B)" in out and "2 unchanged" in out
    assert not (root / "ingest/.hf-sync/previous/ingest/a.parquet").exists()


def test_a_local_edit_is_kept(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"edited by hand")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == []
    assert (root / "ingest/b.parquet").read_bytes() == b"edited by hand"
    assert "changed on this computer since the last sync; kept" in out and "1 kept" in out
    assert record_of(root)["files"]["ingest/b.parquet"]["bytes"] == 500  # the record still describes the sync


def test_a_touched_file_counts_as_changed_and_is_kept(root, capsys):
    first_sync(root, capsys)
    path = root / "ingest/b.parquet"
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == [] and "kept" in out


def test_overwrite_opt_in_replaces_a_local_edit(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"edited by hand")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys, HF_SYNC_OVERWRITE="1")
    assert code == 0
    assert hub.downloads() == ["ingest/b.parquet"] and hub.calls[0]["force"] is True
    assert (root / "ingest/b.parquet").read_bytes() == CONTENT["ingest/b.parquet"]
    assert "1 updated" in out and "0 kept" in out


def test_first_sync_size_mismatch_is_kept_unless_overwrite(root, capsys):
    (root / "ingest/a.parquet").write_bytes(b"short")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert "ingest/a.parquet" not in hub.downloads()
    assert (root / "ingest/a.parquet").read_bytes() == b"short"
    assert "differs from the dataset; kept" in out
    assert "ingest/a.parquet" not in record_of(root)["files"]
    assert sorted(hub.downloads()) == sorted(p for p in CONTENT if p != "ingest/a.parquet")

    hub2 = FakeHub(root, CONTENT)
    code, out = run_main(root, hub2, capsys, HF_SYNC_OVERWRITE="1")
    assert code == 0 and "ingest/a.parquet" in hub2.downloads()
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"]


def test_first_sync_same_size_is_verified_and_adopted(root, capsys):
    (root / "ingest/a.parquet").write_bytes(CONTENT["ingest/a.parquet"])
    inode = (root / "ingest/a.parquet").stat().st_ino
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    call = next(c for c in hub.calls if c["path"] == "ingest/a.parquet")
    assert call["force"] is False  # hf hashes it once itself
    assert (root / "ingest/a.parquet").stat().st_ino == inode
    assert "ingest/a.parquet" in record_of(root)["files"]
    assert "1 verified in place" in out
    # Adopted, so the next run is the fast path.
    again = FakeHub(root, CONTENT)
    run_main(root, again, capsys)
    assert again.calls == []


def test_first_sync_same_size_wrong_content_is_downloaded(root, capsys):
    (root / "ingest/a.parquet").write_bytes(b"X" * 300)
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"]
    assert "1 updated" in out


def test_a_recorded_file_that_went_missing_is_downloaded_again(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/a.parquet").unlink()
    hub = FakeHub(root, CONTENT)
    code, _ = run_main(root, hub, capsys)
    assert code == 0 and hub.downloads() == ["ingest/a.parquet"]


def test_the_readme_and_unlisted_files_are_never_touched(root, capsys):
    (root / "ingest/README.md").write_text("mine")
    (root / "ingest/mine.parquet").write_bytes(b"not in the dataset")
    content = dict(CONTENT, **{"ingest/README.md": b"theirs"})
    hub = FakeHub(root, content)
    code, out = run_main(root, hub, capsys, HF_SYNC_INCLUDE="ingest/*,xgboost_models/*")
    assert code == 0
    assert "ingest/README.md" not in hub.downloads()
    assert (root / "ingest/README.md").read_text() == "mine"
    assert (root / "ingest/mine.parquet").read_bytes() == b"not in the dataset"
    assert "ingest/README.md" not in record_of(root)["files"]
    # A file that left the dataset stays on disk and in the record.
    smaller = {k: v for k, v in CONTENT.items() if k != "ingest/b.parquet"}
    run_main(root, FakeHub(root, smaller, commit=COMMIT2), capsys)
    assert (root / "ingest/b.parquet").read_bytes() == CONTENT["ingest/b.parquet"]
    assert "ingest/b.parquet" in record_of(root)["files"]


def test_the_cache_link_points_at_the_state_folder(root, capsys):
    first_sync(root, capsys)
    link = root / ".cache"
    assert link.is_symlink()
    assert os.path.realpath(link) == os.path.realpath(root / "ingest" / ".hf-sync")


def test_a_stale_link_is_replaced_and_a_real_folder_is_left_alone(root, capsys):
    (root / ".cache").symlink_to(root / "xgboost_models", target_is_directory=True)
    first_sync(root, capsys)
    assert os.path.realpath(root / ".cache") == os.path.realpath(root / "ingest" / ".hf-sync")

    other = root.parent / (root.name + "-real")
    (other / "ingest").mkdir(parents=True)
    (other / ".cache").mkdir()
    (other / ".cache" / "keep").write_text("x")
    hub = FakeHub(other, {"ingest/a.parquet": b"A" * 10})
    code, out = run_main(other, hub, capsys)
    assert code == 0
    assert not (other / ".cache").is_symlink() and (other / ".cache" / "keep").read_text() == "x"
    assert "real folder" in out


# --------------------------------------------------------------------------------------------
# The record is written atomically, after every file
# --------------------------------------------------------------------------------------------

def test_the_record_is_saved_after_each_success_and_leaves_no_temporary_file(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.download_errors["ingest/b.parquet"] = [http_error(HfHubHTTPError, 404)]
    code, out = run_main(root, hub, capsys)
    assert code == 1
    rec = record_of(root)
    assert "ingest/a.parquet" in rec["files"] and "ingest/b.parquet" not in rec["files"]
    assert sorted(p.name for p in (root / "ingest/.hf-sync").iterdir() if p.is_file()) == ["last-sync.json"]


def test_a_failed_write_leaves_the_previous_record_whole(root, capsys, monkeypatch):
    first_sync(root, capsys)
    before = (root / "ingest/.hf-sync/last-sync.json").read_text()
    monkeypatch.setattr(hf.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk went away")))
    with pytest.raises(OSError):
        hf.write_last_sync(root / "ingest/.hf-sync", {"files": {}})
    assert (root / "ingest/.hf-sync/last-sync.json").read_text() == before


def test_a_corrupt_record_is_a_first_sync(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/.hf-sync/last-sync.json").write_text("{not json")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and "could not be read" in out
    # Same size and content: verified, none downloaded for real.
    assert all(not c["force"] for c in hub.calls)
    assert set(record_of(root)["files"]) == set(CONTENT)


# --------------------------------------------------------------------------------------------
# Failures
# --------------------------------------------------------------------------------------------

def test_a_failed_update_keeps_the_old_bytes_and_returns_1(root, capsys):
    first_sync(root, capsys)
    old = (root / "ingest/a.parquet").read_bytes()
    old_record = record_of(root)["files"]["ingest/a.parquet"]
    hub = FakeHub(root, dict(CONTENT, **{"ingest/a.parquet": b"N" * 310}), commit=COMMIT2)
    hub.fail_after_unlink.add("ingest/a.parquet")  # the hub has already unlinked the old file when it fails
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert (root / "ingest/a.parquet").read_bytes() == old
    # The restored file is the old inode, so the record still describes it exactly: the next run retries.
    assert record_of(root)["files"]["ingest/a.parquet"] == old_record
    st = (root / "ingest/a.parquet").stat()
    assert (st.st_size, st.st_mtime_ns) == (old_record["bytes"], old_record["mtime_ns"])
    assert "ingest/a.parquet" in out.splitlines()[-1] and "previous copy is untouched" in out
    assert not (root / "ingest/.hf-sync/previous/ingest/a.parquet").exists()
    assert len(hub.calls) == hf.ATTEMPTS  # a 503 is transient: tried three times


def test_a_failed_first_download_returns_1_and_names_the_file(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.fail_after_unlink.add("ingest/b.parquet")
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert not (root / "ingest/b.parquet").exists()
    assert "ingest/b.parquet" in out.splitlines()[-1]
    assert (root / "ingest/a.parquet").exists()  # the others were still fetched


def test_transient_errors_are_retried_with_backoff(root, capsys, no_sleep):
    hub = FakeHub(root, {"ingest/a.parquet": b"A" * 10})
    hub.download_errors["ingest/a.parquet"] = [httpx2.ConnectError("reset"), httpx2.ReadTimeout("slow")]
    code, out = run_main(root, hub, capsys)
    assert code == 0 and len(hub.calls) == 3
    assert no_sleep == [2.0, 4.0]
    assert "retrying" in out


def test_denied_and_disk_errors_are_not_retried(root, capsys):
    hub = FakeHub(root, {"ingest/a.parquet": b"A" * 10})
    hub.download_errors["ingest/a.parquet"] = [OSError(errno.ENOSPC, "No space left on device")]
    code, out = run_main(root, hub, capsys)
    assert code == 1 and len(hub.calls) == 1 and "No space left" in out


def test_a_download_of_the_wrong_size_is_a_failure(root, capsys):
    class Short(FakeHub):
        def download(self, repo, path, commit, local_dir, force):
            super().download(repo, path, commit, local_dir, force)
            (Path(local_dir) / path).write_bytes(b"cut")  # a truncated file
            return ""

    hub = Short(root, {"ingest/a.parquet": b"A" * 10})
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "ingest/a.parquet" in out.splitlines()[-1]


@pytest.mark.parametrize("cls, status", [(RepositoryNotFoundError, 404), (RevisionNotFoundError, 404),
                                         (GatedRepoError, 403), (RepositoryNotFoundError, 401)])
def test_not_found_or_denied_returns_1_with_the_reason(root, capsys, cls, status):
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = http_error(cls, status)
    code, out = run_main(root, hub, capsys, HF_SYNC_REVISION="no-such-branch")
    assert code == 1
    assert f"HTTP {status}" in out and "no-such-branch" in out
    assert hub.calls == []


def test_a_denied_hub_is_not_excused_by_a_previous_sync(root, capsys):
    first_sync(root, capsys)
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = http_error(RepositoryNotFoundError, 404)
    code, _ = run_main(root, hub, capsys)
    assert code == 1


UNREACHABLE = [
    httpx2.ConnectError("no route"),
    httpx2.ConnectTimeout("timed out"),
    OfflineModeIsEnabled("HF_HUB_OFFLINE=1"),
    http_error(HfHubHTTPError, 503),
    http_error(HfHubHTTPError, 500),
]


@pytest.mark.parametrize("error", UNREACHABLE, ids=lambda e: type(e).__name__)
def test_offline_with_a_complete_last_sync_starts_with_it(root, capsys, error):
    first_sync(root, capsys)
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = error
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert "could not be reached" in out and "starting with the files of the last sync" in out
    assert re.search(r"last sync, \d{4}-\d\d-\d\d \d\d:\d\d UTC", out)
    assert hub.calls == []


def test_offline_while_listing_is_the_same(root, capsys):
    first_sync(root, capsys)
    hub = FakeHub(root, CONTENT)
    hub.list_error = httpx2.ConnectError("dropped")
    code, _ = run_main(root, hub, capsys)
    assert code == 0


def test_offline_mode_is_not_retried(root, capsys, no_sleep):
    first_sync(root, capsys)
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = OfflineModeIsEnabled("HF_HUB_OFFLINE=1")
    run_main(root, hub, capsys)
    assert hub.resolves == 1 and no_sleep == []


def test_offline_with_a_file_missing_or_cut_returns_1_and_names_it(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/a.parquet").unlink()
    (root / "ingest/b.parquet").write_bytes(b"cut")
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("no route")
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert "ingest/a.parquet is missing" in out and "ingest/b.parquet has 3 bytes" in out


def test_never_synced_and_offline_returns_1(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("no route")
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "nothing was ever synced" in out


def test_never_synced_is_not_rescued_by_files_that_happen_to_be_there(root, capsys):
    for path, data in CONTENT.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("no route")
    code, _ = run_main(root, hub, capsys)
    assert code == 1


def test_classify_covers_the_hubs_classes():
    c = hf.classify
    assert c(httpx2.ConnectError("x")) == hf.UNREACHABLE
    assert c(httpx2.ReadTimeout("x")) == hf.UNREACHABLE
    assert c(OfflineModeIsEnabled("x")) == hf.UNREACHABLE
    assert c(ConnectionResetError()) == hf.UNREACHABLE
    assert c(http_error(HfHubHTTPError, 502)) == hf.UNREACHABLE
    assert c(http_error(HfHubHTTPError, 429)) == hf.UNREACHABLE
    for status in (401, 403, 404):
        assert c(http_error(HfHubHTTPError, status)) == hf.DENIED
    assert c(http_error(RevisionNotFoundError, 404)) == hf.DENIED
    assert c(OSError(errno.ENOSPC, "full")) == hf.LOCAL
    assert c(ValueError("x")) == hf.OTHER
    assert c(http_error(HfHubHTTPError, 400)) == hf.OTHER


# --------------------------------------------------------------------------------------------
# --dry-run
# --------------------------------------------------------------------------------------------

def test_dry_run_prints_the_plan_and_changes_nothing(root, capsys):
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys, "--dry-run")
    assert code == 0 and hub.calls == []
    assert "plan: 3 of 3 files to fetch" in out and "2 in ingest/" in out and "1 in xgboost_models/" in out
    assert "download  ingest/a.parquet" in out and "nothing was downloaded" in out
    assert not (root / "ingest/.hf-sync").exists() and not (root / ".cache").exists()
    assert list((root / "ingest").iterdir()) == []


def test_dry_run_shows_what_each_file_would_do(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"edited")
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 301})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys, "--dry-run")
    assert code == 0 and hub.calls == []
    assert "update    ingest/a.parquet" in out
    assert "kept      ingest/b.parquet" in out
    assert "unchanged xgboost_models" in out
