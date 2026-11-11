"""The hf-sync downloader (deploy/hf_sync.py), exercised with a fake Hub: no network, no real ``hf`` call.

``FakeHub.download`` follows ``huggingface_hub`` 2.3.0's ``hf_hub_download(local_dir=...)``
(``file_download.py`` ``_hf_hub_download_to_local_dir`` and ``_download_to_tmp_and_move``):

* it writes ``<local_dir>/<path>`` and its metadata under ``<local_dir>/.cache/huggingface/download``;
* a file already there is returned at once when the metadata names the commit, when it names the same
  etag, or (LFS only, no metadata) when its SHA-256 equals the etag; otherwise the outdated file is
  unlinked first and the bytes are fetched into a uniquely named ``.incomplete`` file that is removed
  on any failure (never reopened, so there is nothing to resume) and moved into place at the end;
* the metadata is written after the move.

The sync hands it only the stage folder, so the fake asserts that its ``local_dir`` is never the final
place. A ``Killed`` exception models SIGKILL: no clean-up runs. Every root is a temporary folder under
pytest's basetemp. ``setuid`` is never called: the privilege drop is tested as the pure decision it is.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import re
import signal
import sys
import uuid
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


class Killed(BaseException):
    """SIGKILL: nothing after the raise runs, so no ``finally`` may clean up after it."""


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def etag_of(path: str, data: bytes) -> str:
    """The Hub's etag: the SHA-256 for an LFS file (Parquet here), Git's blob id for the others."""
    return hashlib.sha256(data).hexdigest() if path.endswith(".parquet") else git_blob_sha1(data)


class FakeHub:
    """Serves ``content`` ({path: bytes}) as the dataset's one commit."""

    def __init__(self, root: Path, content: dict[str, bytes], commit: str = COMMIT):
        self.root = root
        self.content = dict(content)
        self.commit = commit
        self.resolve_error = None
        self.list_error = None
        self.download_errors: dict[str, list[BaseException]] = {}  # raised in turn, after the unlink
        self.fail_after_unlink: set[str] = set()
        self.kill: dict[str, str] = {}   # path -> "midway" | "after_move" | "after_metadata"
        self.midway = None               # called with the path while the .incomplete file exists
        self.calls: list[dict] = []
        self.network: list[str] = []     # the downloads that really fetched bytes
        self.real_seen: list[tuple[str, bytes | None]] = []  # the final place's bytes at each call
        self.resolves = 0

    @property
    def stage(self) -> Path:
        return self.root / "ingest" / ".hf-sync" / "stage"

    # --- the dataset
    def file(self, path: str):
        data = self.content[path]
        etag = etag_of(path, data)
        if path.endswith(".parquet"):
            return SimpleNamespace(path=path, size=len(data), blob_id="git-" + etag[:8],
                                   lfs=SimpleNamespace(sha256=etag))
        return SimpleNamespace(path=path, size=len(data), blob_id=etag, lfs=None)

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
        local_dir = Path(local_dir)
        assert local_dir == self.stage, f"hf must download only into the stage, not {local_dir}"
        assert force is False
        self.calls.append({"path": path, "commit": commit, "force": force, "local_dir": str(local_dir),
                           "repo": repo})
        real = self.root / path
        self.real_seen.append((path, real.read_bytes() if real.is_file() else None))
        data = self.content[path]
        etag = etag_of(path, data)
        final = local_dir / path
        meta = local_dir / ".cache" / "huggingface" / "download" / (path + ".metadata")

        def read_meta():
            if not (meta.exists() and final.is_file()):
                return None
            commit_hash, meta_etag, _ = meta.read_text().splitlines()
            return commit_hash, meta_etag

        def write_meta():
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(f"{commit}\n{etag}\n0.0\n")

        if final.is_file():
            known = read_meta()
            if known is not None and known[0] == commit:
                return str(final)  # local file + metadata + same commit: nothing is asked of the Hub
            if known is not None and known[1] == etag:
                write_meta()
                return str(final)
            if known is None and len(etag) == 64 and hashlib.sha256(final.read_bytes()).hexdigest() == etag:
                write_meta()
                return str(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        final.unlink(missing_ok=True)  # "delete outdated file first"
        partial = meta.parent / f"{hashlib.sha1(path.encode()).hexdigest()[:8]}.{etag}.{uuid.uuid4().hex[:8]}.incomplete"
        partial.parent.mkdir(parents=True, exist_ok=True)
        killed = False
        try:
            partial.write_bytes(data[: len(data) // 2])
            if self.midway is not None:
                self.midway(path)
            if self.kill.get(path) == "midway":
                raise Killed(path)
            queue = self.download_errors.get(path)
            if queue:
                raise queue.pop(0)
            if path in self.fail_after_unlink:
                raise http_error(HfHubHTTPError, 503)
            partial.write_bytes(data)
            os.replace(partial, final)
            if self.kill.get(path) == "after_move":
                raise Killed(path)
            write_meta()
            if self.kill.get(path) == "after_metadata":
                raise Killed(path)
        except Killed:
            killed = True
            raise
        finally:
            if not killed:
                partial.unlink(missing_ok=True)
        self.network.append(path)
        return str(final)

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
# Small helpers
# --------------------------------------------------------------------------------------------

MODEL = "xgboost_models/xgboost_pion/standalone_energy_s1_model.json"
STATE = Path("ingest") / ".hf-sync"


def state_dir(root: Path) -> Path:
    return root / STATE


def stage_files(root: Path) -> list[str]:
    """Every file left in the stage apart from hf's own ``.cache``."""
    stage = state_dir(root) / "stage"
    if not stage.exists():
        return []
    return sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*")
                  if p.is_file() and ".cache" not in p.relative_to(stage).parts)


def snapshot(root: Path) -> dict[str, bytes]:
    """The real files of the two mounts (the hidden state folder left out)."""
    found = {}
    for top in ("ingest", "xgboost_models"):
        for p in (root / top).rglob("*"):
            if p.is_file() and ".hf-sync" not in p.parts:
                found[p.relative_to(root).as_posix()] = p.read_bytes()
    return found


def touch_later(path: Path, seconds: int = 5) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 1_000_000_000))


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
    assert not state_dir(root).exists() and not (root / ".cache").exists()


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
    assert by_path[MODEL].etag == git_blob_sha1(CONTENT[MODEL])


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


def test_the_privilege_drop_happens_before_any_write_or_network_call(root, capsys, monkeypatch):
    order = []
    monkeypatch.setattr(hf.os, "geteuid", lambda: 0)
    monkeypatch.setattr(hf, "plan_privilege_drop", lambda euid, u, g: (4242, 4343))
    monkeypatch.setattr(hf, "drop_privileges", lambda uid, gid: order.append("drop"))
    hub = FakeHub(root, CONTENT)
    real_resolve = hub.resolve
    hub.resolve = lambda *a: (order.append("network"), real_resolve(*a))[1]
    run_main(root, hub, capsys)
    assert order[:2] == ["drop", "network"] and not (root / ".cache").exists()


# --------------------------------------------------------------------------------------------
# First sync, the record, the layout of the state folder
# --------------------------------------------------------------------------------------------

def test_first_sync_downloads_everything_and_records_it(root, capsys):
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert sorted(hub.downloads()) == sorted(CONTENT) and sorted(hub.network) == sorted(CONTENT)
    stage = str(root / "ingest" / ".hf-sync" / "stage")
    assert all(c["commit"] == COMMIT and not c["force"] and c["local_dir"] == stage for c in hub.calls)
    assert all(c["repo"] == "martinsandor707/particles_combined_all_models" for c in hub.calls)
    for path, data in CONTENT.items():
        assert (root / path).read_bytes() == data
    rec = record_of(root)
    assert rec["repo"] == "martinsandor707/particles_combined_all_models"
    assert rec["revision"] == "main" and rec["commit"] == COMMIT and rec["synced_at"]
    assert set(rec["files"]) == set(CONTENT) and sorted(rec["expected"]) == sorted(CONTENT)
    assert rec["complete"] is True and rec["kept"] == []
    for path, data in CONTENT.items():
        st = (root / path).stat()
        assert rec["files"][path] == {"bytes": len(data), "mtime_ns": st.st_mtime_ns, "etag": etag_of(path, data)}
    assert "Downloading ingest/a.parquet (300 B)" in out
    assert "done in" in out
    assert "3 files examined: 3 downloaded (808 B), 0 updated, 0 adopted, 0 unchanged, 0 kept." in out
    assert all(l.startswith("hf-sync: ") for l in out.strip().splitlines())


def test_the_state_folder_holds_exactly_the_stage_and_the_record(root, capsys):
    first_sync(root, capsys)
    assert sorted(p.name for p in state_dir(root).iterdir()) == ["last-sync.json", "stage"]
    assert not (root / ".cache").exists() and not (root / ".cache").is_symlink()
    assert stage_files(root) == []  # every finished file was moved out of the stage


def test_unchanged_files_cost_no_download_call_and_no_hashing(root, capsys, monkeypatch):
    first_sync(root, capsys)
    monkeypatch.setattr(hf, "file_digest", lambda *a: pytest.fail("a recorded, untouched file is not hashed"))
    again = FakeHub(root, CONTENT)
    code, out = run_main(root, again, capsys)
    assert code == 0 and again.calls == []
    assert "3 unchanged" in out and "0 downloaded" in out and "Checking" not in out


def test_upstream_update_replaces_only_the_changed_file(root, capsys):
    first_sync(root, capsys)
    old = (root / "ingest/a.parquet").read_bytes()
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert hub.downloads() == ["ingest/a.parquet"]
    assert hub.calls[0]["force"] is False and hub.calls[0]["commit"] == COMMIT2
    assert hub.real_seen == [("ingest/a.parquet", old)]  # the old file was whole while the download ran
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320
    rec = record_of(root)
    assert rec["commit"] == COMMIT2 and rec["files"]["ingest/a.parquet"]["bytes"] == 320 and rec["complete"] is True
    assert "1 updated (320 B)" in out and "2 unchanged" in out
    assert sorted(p.name for p in state_dir(root).iterdir()) == ["last-sync.json", "stage"]


def test_an_update_never_unlinks_or_truncates_the_real_file_while_downloading(root, capsys):
    first_sync(root, capsys)
    seen = []

    def watch(path):
        real = root / path
        seen.append((real.stat().st_size, real.read_bytes()))

    hub = FakeHub(root, dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320}), commit=COMMIT2)
    hub.midway = watch
    run_main(root, hub, capsys)
    assert seen == [(300, b"A" * 300)]


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


# --------------------------------------------------------------------------------------------
# The decision is by content (E6, E7): hash, adopt, update, keep, overwrite
# --------------------------------------------------------------------------------------------

def test_file_digest_is_sha256_for_lfs_and_the_git_blob_id_for_the_rest(tmp_path, monkeypatch):
    data = bytes(range(256)) * 3
    path = tmp_path / "f"
    path.write_bytes(data)
    monkeypatch.setattr(hf, "HASH_CHUNK", 7)  # several chunks, none aligned
    assert hf.file_digest(path, hf.SHA256, len(data)) == hashlib.sha256(data).hexdigest()
    assert hf.file_digest(path, hf.GIT_SHA1, len(data)) == git_blob_sha1(data)
    # The blob id of the empty file is a known constant of Git.
    empty = tmp_path / "e"
    empty.write_bytes(b"")
    assert hf.file_digest(empty, hf.GIT_SHA1, 0) == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_etag_kind():
    assert hf.etag_kind("a" * 64) == hf.SHA256 and hf.etag_kind("0" * 40) == hf.GIT_SHA1
    assert hf.etag_kind("g" * 40) is None and hf.etag_kind("a" * 41) is None and hf.etag_kind("A" * 64) is None


def test_decide_table(tmp_path):
    data = b"x" * 10
    path = tmp_path / "f"
    path.write_bytes(data)
    st = path.lstat()
    entry = hf.Entry("ingest/f.parquet", 10, hashlib.sha256(data).hexdigest())
    other = hashlib.sha256(b"older").hexdigest()

    def digest(kind):
        return hf.file_digest(path, kind, st.st_size)

    own = {"bytes": 10, "mtime_ns": st.st_mtime_ns, "etag": entry.etag}

    def never(kind):
        pytest.fail("no hashing expected")

    d = hf.decide
    assert d(entry, None, None, False, never) == (hf.DOWNLOAD, "not on this computer")
    assert d(entry, st, own, False, never)[0] == hf.UNCHANGED
    assert d(entry, st, dict(own, etag=other), False, never)[0] == hf.UPDATE
    # Stat moved, content equals the dataset: adopted, whether or not a record exists.
    moved = dict(own, mtime_ns=st.st_mtime_ns - 1)
    assert d(entry, st, moved, False, digest)[0] == hf.ADOPT
    assert d(entry, st, None, False, digest)[0] == hf.ADOPT
    # Different size from the dataset and from any record: kept without reading a byte.
    bigger = hf.Entry("ingest/f.parquet", 11, "b" * 64)
    assert d(bigger, st, None, False, never) == (hf.KEPT, "differs from the dataset; kept")
    assert d(bigger, st, None, True, never)[0] == hf.UPDATE
    # Same size, other bytes: kept; with overwrite, an update.
    wrong = hf.Entry("ingest/f.parquet", 10, hashlib.sha256(b"y" * 10).hexdigest())
    assert d(wrong, st, None, False, digest) == (hf.KEPT, "differs from the dataset; kept")
    edited = dict(own, etag=other, mtime_ns=st.st_mtime_ns - 1)  # neither the dataset's bytes nor the recorded ones
    assert d(wrong, st, edited, False, digest)[1] == "changed on this computer since the last sync; kept"
    assert d(wrong, st, edited, True, digest)[0] == hf.UPDATE
    # An untouched copy of the recorded older version: update, no matter what moved its mtime.
    older_rec = {"bytes": 10, "mtime_ns": st.st_mtime_ns - 1, "etag": hashlib.sha256(data).hexdigest()}
    assert d(wrong, st, older_rec, False, digest)[0] == hf.UPDATE
    # A malformed record entry counts as no record.
    for bad in ("oops", 7, [1], {"bytes": "x"}, {"bytes": 10, "mtime_ns": 1}):
        assert d(entry, st, bad, False, digest)[0] == hf.ADOPT
        assert d(wrong, st, bad, False, digest) == (hf.KEPT, "differs from the dataset; kept")
    # An etag of an unknown form cannot be checked: kept.
    odd = hf.Entry("ingest/f.parquet", 10, "not-an-etag")
    assert d(odd, st, None, False, never)[0] == hf.KEPT


def test_a_local_edit_of_another_size_is_kept_without_hashing(root, capsys, monkeypatch):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"edited by hand")
    monkeypatch.setattr(hf, "file_digest", lambda *a: pytest.fail("nothing to compare a different size with"))
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == []
    assert (root / "ingest/b.parquet").read_bytes() == b"edited by hand"
    assert "changed on this computer since the last sync; kept" in out and "1 kept" in out
    assert record_of(root)["files"]["ingest/b.parquet"]["bytes"] == 500  # the record still describes the sync


def test_a_same_size_local_edit_is_kept_after_hashing(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"E" * 500)
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == []
    assert (root / "ingest/b.parquet").read_bytes() == b"E" * 500
    assert "Checking ingest/b.parquet (500 B) against the dataset" in out
    assert "changed on this computer since the last sync; kept" in out


def test_a_touched_file_is_adopted_not_kept_forever(root, capsys):
    """E7: git checkout, touch or cp move the mtime; the content is still the dataset's."""
    first_sync(root, capsys)
    touch_later(root / MODEL)
    touch_later(root / "ingest/b.parquet")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == []
    assert "2 adopted" in out and "0 kept" in out and "Checking" in out
    for path in (MODEL, "ingest/b.parquet"):
        assert record_of(root)["files"][path]["mtime_ns"] == (root / path).stat().st_mtime_ns
    # Adopted for good: the next start is the fast path.
    again = FakeHub(root, CONTENT)
    code, out = run_main(root, again, capsys)
    assert again.calls == [] and "3 unchanged" in out and "Checking" not in out


def test_a_touched_file_still_follows_a_later_update(root, capsys):
    first_sync(root, capsys)
    touch_later(root / MODEL)
    newer = dict(CONTENT, **{MODEL: b'{"m": 2}'})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.downloads() == [MODEL]
    assert (root / MODEL).read_bytes() == b'{"m": 2}'
    assert "untouched copy of the last sync's older version" in out and "1 updated" in out


def test_a_touched_and_edited_file_is_kept_even_when_the_dataset_moved_on(root, capsys):
    first_sync(root, capsys)
    (root / MODEL).write_bytes(b'{"m": 9}')
    newer = dict(CONTENT, **{MODEL: b'{"m": 2}'})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == [] and (root / MODEL).read_bytes() == b'{"m": 9}'
    assert "changed on this computer since the last sync; kept" in out


def test_overwrite_opt_in_replaces_a_local_edit(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/b.parquet").write_bytes(b"edited by hand")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys, HF_SYNC_OVERWRITE="1")
    assert code == 0
    assert hub.downloads() == ["ingest/b.parquet"] and hub.calls[0]["force"] is False
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


@pytest.mark.parametrize("path, size", [("ingest/a.parquet", 300), (MODEL, 8)])
def test_first_sync_same_size_other_bytes_is_kept_not_overwritten(root, capsys, path, size):
    """E6, for an LFS file (SHA-256) and for a Git-tracked one (blob SHA-1)."""
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_bytes(b"X" * size)
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert path not in hub.downloads()
    assert (root / path).read_bytes() == b"X" * size
    assert "differs from the dataset; kept" in out and "1 kept" in out
    assert f"Checking {path}" in out
    rec = record_of(root)
    assert path not in rec["files"] and path in rec["kept"] and rec["complete"] is True

    hub2 = FakeHub(root, CONTENT)
    code, out = run_main(root, hub2, capsys, HF_SYNC_OVERWRITE="1")
    assert code == 0 and hub2.downloads() == [path]
    assert (root / path).read_bytes() == CONTENT[path]


@pytest.mark.parametrize("path", ["ingest/a.parquet", MODEL])
def test_first_sync_same_size_same_bytes_is_adopted_in_place(root, capsys, path):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_bytes(CONTENT[path])
    inode = (root / path).stat().st_ino
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert path not in hub.downloads()
    assert (root / path).stat().st_ino == inode
    assert path in record_of(root)["files"]
    assert "1 adopted" in out and f"Checking {path}" in out
    # Adopted, so the next run is the fast path.
    again = FakeHub(root, CONTENT)
    run_main(root, again, capsys)
    assert again.calls == []


def test_a_recorded_file_that_went_missing_is_downloaded_again(root, capsys):
    first_sync(root, capsys)
    (root / "ingest/a.parquet").unlink()
    hub = FakeHub(root, CONTENT)
    code, _ = run_main(root, hub, capsys)
    assert code == 0 and hub.downloads() == ["ingest/a.parquet"]


def test_a_symlink_in_the_way_is_kept_and_a_dangling_link_is_not_missing(root, capsys):
    target = root / "elsewhere.parquet"
    target.write_bytes(CONTENT["ingest/a.parquet"])
    (root / "ingest/a.parquet").symlink_to(target)
    (root / "ingest/b.parquet").symlink_to(root / "nowhere.parquet")  # dangling
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0
    assert "ingest/a.parquet" not in hub.downloads() and "ingest/b.parquet" not in hub.downloads()
    assert (root / "ingest/a.parquet").is_symlink() and (root / "ingest/b.parquet").is_symlink()
    assert "is a link or a folder, not a file; kept" in out and "2 kept" in out
    # With the opt-in the link itself is replaced by a real file; its target is not written through.
    hub2 = FakeHub(root, CONTENT)
    run_main(root, hub2, capsys, HF_SYNC_OVERWRITE="1")
    assert not (root / "ingest/a.parquet").is_symlink()
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"]
    assert target.read_bytes() == CONTENT["ingest/a.parquet"]
    assert not (root / "nowhere.parquet").exists()


# --------------------------------------------------------------------------------------------
# The staging design: the final place is only ever written by an atomic swap
# --------------------------------------------------------------------------------------------

def test_ingest_files_are_swapped_by_one_rename_from_the_stage_and_models_by_a_sibling_temp(root, capsys,
                                                                                         monkeypatch):
    swaps = []
    real_replace = os.replace
    monkeypatch.setattr(hf.os, "replace", lambda src, dst: (swaps.append((Path(src), Path(dst))),
                                                            real_replace(src, dst))[1])
    first_sync(root, capsys)
    by_dest = {dst: src for src, dst in swaps if dst.name != "last-sync.json"}
    stage = state_dir(root) / "stage"
    assert by_dest[root / "ingest/a.parquet"] == stage / "ingest/a.parquet"
    assert by_dest[root / MODEL] == (root / MODEL).with_name(Path(MODEL).name + ".hf-sync-tmp")
    assert by_dest[root / MODEL].parent == (root / MODEL).parent  # on the model mount, never across mounts
    assert not list((root / "xgboost_models").rglob("*.hf-sync-tmp"))


def test_a_model_copy_that_fails_leaves_the_old_model_whole_and_no_temporary_file(root, capsys, monkeypatch):
    first_sync(root, capsys)
    newer = dict(CONTENT, **{MODEL: b'{"m": 22}'})
    real_copy = hf.shutil.copyfile

    def cut_copy(src, dst):
        real_copy(src, dst)
        with open(dst, "r+b") as handle:
            handle.truncate(3)
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(hf.shutil, "copyfile", cut_copy)
    code, out = run_main(root, FakeHub(root, newer, commit=COMMIT2), capsys)
    assert code == 1 and (root / MODEL).read_bytes() == CONTENT[MODEL]
    assert not list((root / "xgboost_models").rglob("*.hf-sync-tmp"))
    assert MODEL in out.splitlines()[-1] and "previous copy of each is untouched" in out


def test_a_model_write_that_is_refused_names_the_cause(root, capsys, monkeypatch):
    def refuse(src, dst):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(hf.shutil, "copyfile", refuse)
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert "cannot write into" in out and f"belongs to uid {(root / 'xgboost_models').stat().st_uid}" in out
    assert f"runs as uid {os.geteuid()}" in out
    assert len([c for c in hub.calls if c["path"] == MODEL]) == 1  # EACCES is not retried
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"]  # the datasets still synced


def test_stale_partial_downloads_are_cleared_at_the_start(root, capsys):
    partial = state_dir(root) / "stage/.cache/huggingface/download/ingest/a.parquet.abc.deadbeef.incomplete"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"x" * 2000)
    code, out = run_main(root, FakeHub(root, CONTENT), capsys)
    assert code == 0 and not partial.exists() and "removed 2.0 kB of partial downloads" in out


# --------------------------------------------------------------------------------------------
# Interruptions (E3): every real file stays whole, and the next run finishes the job
# --------------------------------------------------------------------------------------------

def test_killed_midway_leaves_the_real_files_whole_and_the_next_run_downloads_again(root, capsys):
    first_sync(root, capsys)
    before = snapshot(root)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    hub = FakeHub(root, newer, commit=COMMIT2)
    hub.kill["ingest/a.parquet"] = "midway"
    with pytest.raises(Killed):
        run_main(root, hub, capsys)
    assert snapshot(root) == before
    assert record_of(root)["complete"] is False
    # The orphaned partial file of the killed process is cleared by the next run, which finishes the update.
    hub2 = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub2, capsys)
    assert code == 0 and hub2.network == ["ingest/a.parquet"] and "partial downloads" in out
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320 and record_of(root)["complete"] is True


def test_killed_after_hf_finished_but_before_the_swap_swaps_the_staged_file_without_a_download(root, capsys):
    first_sync(root, capsys)
    before = snapshot(root)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    hub = FakeHub(root, newer, commit=COMMIT2)
    hub.kill["ingest/a.parquet"] = "after_metadata"
    with pytest.raises(Killed):
        run_main(root, hub, capsys)
    assert snapshot(root) == before and stage_files(root) == ["ingest/a.parquet"]
    hub2 = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub2, capsys)
    assert code == 0 and hub2.network == []  # hf found the staged file whole and asked the Hub for nothing
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320 and stage_files(root) == []
    assert record_of(root)["complete"] is True


def test_killed_between_the_move_and_the_metadata_does_not_trust_the_staged_file_blindly(root, capsys):
    """A staged file without hf's metadata is hashed (LFS) or fetched again (Git blob); never swapped unchecked."""
    first_sync(root, capsys)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320, MODEL: b'{"m": 5}'})
    hub = FakeHub(root, newer, commit=COMMIT2)
    hub.kill["ingest/a.parquet"] = "after_move"
    with pytest.raises(Killed):
        run_main(root, hub, capsys)
    hub2 = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub2, capsys)
    assert code == 0
    assert hub2.network == [MODEL]  # the parquet's SHA-256 matched; the model was the only real fetch
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320 and (root / MODEL).read_bytes() == b'{"m": 5}'


def test_killed_after_the_swap_but_before_the_record_adopts_the_file_next_time(root, capsys, monkeypatch):
    first_sync(root, capsys)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    real_swap = hf.swap_into_place

    def swap_then_die(cfg, stage, entry):
        real_swap(cfg, stage, entry)
        raise Killed(entry.path)

    monkeypatch.setattr(hf, "swap_into_place", swap_then_die)
    hub = FakeHub(root, newer, commit=COMMIT2)
    with pytest.raises(Killed):
        run_main(root, hub, capsys)
    assert (root / "ingest/a.parquet").read_bytes() == b"Z" * 320  # the new file is whole and in place
    assert record_of(root)["files"]["ingest/a.parquet"]["bytes"] == 300  # ... but the record is behind
    monkeypatch.undo()
    hub2 = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub2, capsys)
    assert code == 0 and hub2.calls == []  # hashed, equal to the dataset: adopted, not downloaded again
    assert "1 adopted" in out and record_of(root)["files"]["ingest/a.parquet"]["bytes"] == 320


def test_killed_after_the_swap_during_a_first_sync_adopts_the_file_next_time(root, capsys, monkeypatch):
    real_swap = hf.swap_into_place
    done = []

    def swap_then_die(cfg, stage, entry):
        stat = real_swap(cfg, stage, entry)
        done.append(entry.path)
        if len(done) == 2:
            raise Killed(entry.path)
        return stat

    monkeypatch.setattr(hf, "swap_into_place", swap_then_die)
    with pytest.raises(Killed):
        run_main(root, FakeHub(root, CONTENT), capsys)
    monkeypatch.undo()
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.downloads() == [MODEL] and "1 adopted" in out
    assert record_of(root)["complete"] is True


def test_sigterm_is_turned_into_an_interrupt_and_every_real_file_stays_whole(root, capsys):
    first_sync(root, capsys)
    before = snapshot(root)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320})
    previous = signal.getsignal(signal.SIGTERM)
    hub = FakeHub(root, newer, commit=COMMIT2)
    hub.midway = lambda path: os.kill(os.getpid(), signal.SIGTERM)
    code, out = run_main(root, hub, capsys)
    assert code == 143 and "interrupted" in out and "docker compose up again" in out
    assert snapshot(root) == before and stage_files(root) == []  # hf's own clean-up ran in the unwinding
    assert signal.getsignal(signal.SIGTERM) == previous  # the handler is put back
    assert record_of(root)["complete"] is False
    code, out = run_main(root, FakeHub(root, newer, commit=COMMIT2), capsys)
    assert code == 0 and (root / "ingest/a.parquet").read_bytes() == b"Z" * 320


def test_ctrl_c_returns_130_and_leaves_the_real_files_whole(root, capsys):
    first_sync(root, capsys)
    before = snapshot(root)
    hub = FakeHub(root, dict(CONTENT, **{"ingest/a.parquet": b"Z" * 320}), commit=COMMIT2)

    def interrupt(path):
        raise KeyboardInterrupt

    hub.midway = interrupt
    code, out = run_main(root, hub, capsys)
    assert code == 130 and snapshot(root) == before


def test_the_sigterm_handler_raises_keyboard_interrupt():
    previous = hf.install_sigterm_handler()
    try:
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not previous
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_a_download_that_raises_midway_leaves_every_real_file_whole(root, capsys):
    first_sync(root, capsys)
    before = snapshot(root)
    hub = FakeHub(root, {k: (v + b"!" if k != MODEL else v) for k, v in CONTENT.items()}, commit=COMMIT2)
    hub.download_errors["ingest/b.parquet"] = [RuntimeError("boom")] * 3
    code, out = run_main(root, hub, capsys)
    assert code == 1 and (root / "ingest/b.parquet").read_bytes() == before["ingest/b.parquet"]
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"] + b"!"  # the others went on


# --------------------------------------------------------------------------------------------
# The record: expected paths, the complete flag, atomic writes
# --------------------------------------------------------------------------------------------

def test_the_record_is_written_before_any_download_with_the_expected_paths(root, capsys):
    hub = FakeHub(root, CONTENT)
    seen = []
    hub.midway = lambda path: seen.append(record_of(root))
    run_main(root, hub, capsys)
    assert seen and all(r["complete"] is False and sorted(r["expected"]) == sorted(CONTENT) for r in seen)
    assert seen[0]["files"] == {}  # nothing downloaded yet, but the intent is on disk
    assert record_of(root)["complete"] is True


def test_the_record_is_saved_after_each_success_and_leaves_no_temporary_file(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.download_errors["ingest/b.parquet"] = [http_error(HfHubHTTPError, 404)]
    code, out = run_main(root, hub, capsys)
    assert code == 1
    rec = record_of(root)
    assert "ingest/a.parquet" in rec["files"] and "ingest/b.parquet" not in rec["files"]
    assert rec["complete"] is False and sorted(rec["expected"]) == sorted(CONTENT)
    assert sorted(p.name for p in state_dir(root).iterdir() if p.is_file()) == ["last-sync.json"]


def test_complete_is_set_again_by_a_run_that_finishes_the_job(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.fail_after_unlink.add("ingest/b.parquet")
    assert run_main(root, hub, capsys)[0] == 1 and record_of(root)["complete"] is False
    code, _ = run_main(root, FakeHub(root, CONTENT), capsys)
    assert code == 0 and record_of(root)["complete"] is True


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
    # Same size and content: adopted, none downloaded.
    assert hub.calls == [] and "3 adopted" in out
    assert set(record_of(root)["files"]) == set(CONTENT)


def test_a_malformed_record_entry_counts_as_no_record(root, capsys):
    first_sync(root, capsys)
    rec = record_of(root)
    rec["files"]["ingest/a.parquet"] = "oops"
    rec["files"][MODEL] = {"bytes": "8"}
    (root / "ingest/.hf-sync/last-sync.json").write_text(json.dumps(rec))
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 0 and hub.calls == [] and "2 adopted" in out and "1 unchanged" in out
    assert all(hf.valid_entry(v) for v in record_of(root)["files"].values())


# --------------------------------------------------------------------------------------------
# Failures
# --------------------------------------------------------------------------------------------

def test_a_failed_update_keeps_the_old_bytes_and_returns_1_with_the_way_out(root, capsys):
    first_sync(root, capsys)
    old = (root / "ingest/a.parquet").read_bytes()
    old_record = record_of(root)["files"]["ingest/a.parquet"]
    hub = FakeHub(root, dict(CONTENT, **{"ingest/a.parquet": b"N" * 310}), commit=COMMIT2)
    hub.fail_after_unlink.add("ingest/a.parquet")
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert (root / "ingest/a.parquet").read_bytes() == old
    # The real file was never touched, so the record still describes it exactly: the next run retries.
    assert record_of(root)["files"]["ingest/a.parquet"] == old_record
    st = (root / "ingest/a.parquet").stat()
    assert (st.st_size, st.st_mtime_ns) == (old_record["bytes"], old_record["mtime_ns"])
    last = out.splitlines()[-1]
    assert "ingest/a.parquet" in last and "previous copy of each is untouched" in last
    assert "docker compose up again" in last and "HF_SYNC=0" in last
    assert "previous copy is untouched" in out
    assert not (state_dir(root) / "previous").exists()
    assert len(hub.calls) == hf.ATTEMPTS  # a 503 is transient: tried three times
    assert record_of(root)["complete"] is False


def test_a_failed_first_download_returns_1_and_names_the_file(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.fail_after_unlink.add("ingest/b.parquet")
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert not (root / "ingest/b.parquet").exists() and stage_files(root) == []
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


def test_a_download_of_the_wrong_size_is_a_failure_and_never_reaches_the_real_place(root, capsys):
    class Short(FakeHub):
        def download(self, repo, path, commit, local_dir, force):
            super().download(repo, path, commit, local_dir, force)
            (Path(local_dir) / path).write_bytes(b"cut")  # a truncated file
            return ""

    hub = Short(root, {"ingest/a.parquet": b"A" * 10})
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "ingest/a.parquet" in out.splitlines()[-1]
    assert not (root / "ingest/a.parquet").exists() and stage_files(root) == []


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


def test_the_private_dataset_hint_names_hf_token(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = http_error(GatedRepoError, 403)
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "HF_TOKEN" in out


# --------------------------------------------------------------------------------------------
# No file matches the patterns (E10)
# --------------------------------------------------------------------------------------------

def test_patterns_that_match_nothing_anywhere_are_an_error(root, capsys):
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys, HF_SYNC_INCLUDE="ingest/*.parqet")
    assert code == 1 and hub.calls == []
    assert "no file of the dataset matches HF_SYNC_INCLUDE and no local file does either" in out


def test_patterns_that_match_only_local_files_warn_and_exit_0(root, capsys):
    (root / "ingest/mine.parquet").write_bytes(b"mine")
    (root / "ingest/.hf-sync").mkdir()
    (root / "ingest/.hf-sync/stage-leftover.parquet").write_bytes(b"hidden state is not a dataset file")
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys, HF_SYNC_INCLUDE="ingest/mine*")
    assert code == 0 and hub.calls == []
    assert "no file of the dataset matches HF_SYNC_INCLUDE" in out and "1 matching file(s) already here" in out


def test_the_readme_alone_does_not_count_as_a_local_match(root, capsys):
    (root / "ingest/README.md").write_text("note")
    code, out = run_main(root, FakeHub(root, CONTENT), capsys, HF_SYNC_INCLUDE="ingest/*.md")
    assert code == 1


# --------------------------------------------------------------------------------------------
# The mounts (E9)
# --------------------------------------------------------------------------------------------

def test_an_unwritable_models_mount_is_named_and_the_datasets_are_still_synced(root, capsys, monkeypatch):
    real = hf.mount_problem
    monkeypatch.setattr(hf, "mount_problem", lambda folder: (
        f"{folder} is not writable: it belongs to uid 0 and this process runs as uid 1000. Give it to the user"
        if folder.name == "xgboost_models" else real(folder)))
    hub = FakeHub(root, CONTENT)
    code, out = run_main(root, hub, capsys)
    assert code == 1
    assert "xgboost_models is not writable: it belongs to uid 0 and this process runs as uid 1000" in out
    assert "datasets are still synced" in out
    assert (root / "ingest/a.parquet").read_bytes() == CONTENT["ingest/a.parquet"]
    assert (root / "ingest/b.parquet").read_bytes() == CONTENT["ingest/b.parquet"]
    assert hub.downloads() == ["ingest/a.parquet", "ingest/b.parquet"]  # no model was downloaded for nothing
    assert MODEL in out.splitlines()[-1] and not (root / MODEL).exists()
    assert record_of(root)["complete"] is False


def test_an_unwritable_models_mount_is_harmless_when_nothing_needs_writing(root, capsys, monkeypatch):
    first_sync(root, capsys)
    real = hf.mount_problem
    monkeypatch.setattr(hf, "mount_problem",
                        lambda folder: "nope" if folder.name == "xgboost_models" else real(folder))
    code, out = run_main(root, FakeHub(root, CONTENT), capsys)
    assert code == 0 and "3 unchanged" in out


def test_an_unwritable_ingest_mount_stops_before_any_network_call(root, capsys, monkeypatch):
    class Boom:
        def __getattr__(self, name):
            raise AssertionError("no hub call before the mount is known to be writable")

    monkeypatch.setattr(hf, "mount_problem",
                        lambda folder: f"{folder} is not writable" if folder.name == "ingest" else None)
    code, out = run_main(root, Boom(), capsys)
    assert code == 1 and "HF_SYNC=0" in out and "Nothing can be downloaded" in out
    assert not (root / "ingest/.hf-sync").exists()


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignores file modes")
def test_mount_problem_names_the_owner_and_the_running_uid(tmp_path):
    folder = tmp_path / "xgboost_models"
    folder.mkdir()
    assert hf.mount_problem(folder) is None
    folder.chmod(0o555)
    try:
        text = hf.mount_problem(folder)
    finally:
        folder.chmod(0o755)
    assert text and f"belongs to uid {folder.stat().st_uid}" in text and f"runs as uid {os.geteuid()}" in text
    assert "chown" in text


# --------------------------------------------------------------------------------------------
# Offline
# --------------------------------------------------------------------------------------------

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


def test_an_interrupted_first_sync_followed_by_an_offline_start_returns_1(root, capsys):
    """E2: the record lists only the files that arrived; the dataset's other files are missing."""
    hub = FakeHub(root, CONTENT)
    hub.fail_after_unlink.add("ingest/b.parquet")
    assert run_main(root, hub, capsys)[0] == 1
    offline = FakeHub(root, CONTENT)
    offline.resolve_error = httpx2.ConnectError("down")
    code, out = run_main(root, offline, capsys)
    assert code == 1
    assert "the last sync did not finish" in out and "ingest/b.parquet is missing" in out


def test_a_killed_first_sync_followed_by_an_offline_start_returns_1(root, capsys):
    hub = FakeHub(root, CONTENT)
    hub.kill["ingest/b.parquet"] = "midway"
    with pytest.raises(Killed):
        run_main(root, hub, capsys)
    offline = FakeHub(root, CONTENT)
    offline.resolve_error = httpx2.ConnectError("down")
    code, out = run_main(root, offline, capsys)
    assert code == 1 and "did not finish" in out and "ingest/b.parquet is missing" in out


def test_an_interrupted_run_is_refused_offline_even_when_every_file_is_there(root, capsys):
    first_sync(root, capsys)
    rec = record_of(root)
    rec["complete"] = False
    (root / "ingest/.hf-sync/last-sync.json").write_text(json.dumps(rec))
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("down")
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "did not finish" in out


@pytest.mark.parametrize("damage", ["no_expected", "no_complete", "expected_not_a_list"])
def test_offline_needs_both_the_complete_flag_and_the_expected_list(root, capsys, damage):
    first_sync(root, capsys)
    rec = record_of(root)
    if damage == "no_expected":
        del rec["expected"]
    elif damage == "no_complete":
        del rec["complete"]
    else:
        rec["expected"] = "ingest/a.parquet"
    (root / "ingest/.hf-sync/last-sync.json").write_text(json.dumps(rec))
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("down")
    assert run_main(root, hub, capsys)[0] == 1


def test_offline_ignores_a_malformed_entry_gracefully(root, capsys):
    first_sync(root, capsys)
    rec = record_of(root)
    rec["files"]["ingest/a.parquet"] = "oops"
    (root / "ingest/.hf-sync/last-sync.json").write_text(json.dumps(rec))
    hub = FakeHub(root, CONTENT)
    hub.resolve_error = httpx2.ConnectError("down")
    code, out = run_main(root, hub, capsys)
    assert code == 1 and "ingest/a.parquet was never recorded as complete" in out


def test_a_file_kept_on_purpose_does_not_block_an_offline_start(root, capsys):
    (root / "ingest/a.parquet").write_bytes(b"short")  # mine, of another size: kept
    run_main(root, FakeHub(root, CONTENT), capsys)
    assert record_of(root)["complete"] is True and record_of(root)["kept"] == ["ingest/a.parquet"]
    offline = FakeHub(root, CONTENT)
    offline.resolve_error = httpx2.ConnectError("down")
    code, out = run_main(root, offline, capsys)
    assert code == 0 and "starting with the files of the last sync" in out


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
    touch_later(root / MODEL)
    newer = dict(CONTENT, **{"ingest/a.parquet": b"Z" * 301})
    hub = FakeHub(root, newer, commit=COMMIT2)
    code, out = run_main(root, hub, capsys, "--dry-run")
    assert code == 0 and hub.calls == []
    assert "update    ingest/a.parquet" in out
    assert "kept      ingest/b.parquet" in out
    assert "adopt     xgboost_models" in out and "1 already here and to be adopted" in out
    assert "plan: 1 of 3 files to fetch" in out
