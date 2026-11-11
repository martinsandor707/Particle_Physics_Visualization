"""Keep the repository's ``ingest/`` and ``xgboost_models/`` folders in step with the Hugging Face dataset.

This is the ``hf-sync`` service of ``docker-compose.yml``: a one-shot container that runs before the
dashboard starts, so that ``docker compose up`` is the only command a user needs, today and after
every ``git pull``. The dashboard waits for it (``service_completed_successfully``), which is why the
exit code carries the meaning:

* 0: the folders hold what the dataset lists, or the Hub could not be reached and the last sync had
  finished and its files are all here;
* 1: something that the dashboard needs is missing or unfinished, named in the log;
* 130 / 143: interrupted by Ctrl-C / by ``docker compose stop`` (SIGTERM). Every file in place is whole.

Rules the code keeps, each one a decision of the design, not an accident:

* Nothing is ever deleted. A local file the dataset does not list is never touched, and neither is
  ``ingest/README.md``.
* ``huggingface_hub`` never writes, unlinks or truncates a file at its final place. It downloads only
  into ``ingest/.hf-sync/stage/`` (its own ``.cache`` lives there too), and the sync swaps a whole,
  size-checked file into place: ``os.replace`` for ``ingest/``, which is one atomic rename on one
  mount, and for ``xgboost_models/`` a copy to ``<name>.hf-sync-tmp`` beside the destination, fsynced
  and then renamed, because that folder is another mount. The old file therefore stays whole until
  the swap, whatever kills the process, and no spare copy is needed.
* A file's fate is decided by its content, not by ``huggingface_hub``'s metadata and not by
  timestamps alone. The sync records what it wrote (size, modification time, the dataset's etag).
  A file whose size and time still match the record is the sync's own and costs no hashing and no
  network call. Any other file is hashed (SHA-256 for a Git LFS etag, Git's blob SHA-1 for the
  others) and compared with the dataset's etag: equal means *adopted* (recorded, nothing downloaded);
  equal to the recorded etag means an untouched older copy, so *updated*; anything else was changed
  on this computer or is a different file, so it is *kept* unless ``HF_SYNC_OVERWRITE=1``.
* The record, ``ingest/.hf-sync/last-sync.json``, is written right after the listing, before any
  download, and after every file. It lists the ``expected`` paths and a ``complete`` flag that is
  true only when a run ended with every one of them present, recorded and of its listed size (a file
  kept on purpose counts as present). A start without the Hub requires both, so an interrupted first
  sync never passes for a finished one.

The ``.hf-sync/`` folder holds exactly two things: ``stage/`` and ``last-sync.json``.

The hub calls are injectable (``main(api=...)``), so the tests run without a network.
"""

from __future__ import annotations

import argparse
import dataclasses
import errno
import fnmatch
import hashlib
import json
import os
import shutil
import signal
import stat as stat_module
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:  # The image installs it; the import stays soft so the pure functions load without it.
    import httpx2
    from huggingface_hub.errors import HfHubHTTPError, OfflineModeIsEnabled
except ImportError:  # pragma: no cover - exercised only where huggingface_hub is absent
    httpx2 = None
    HfHubHTTPError = OfflineModeIsEnabled = None

PREFIX = "hf-sync: "

DEFAULT_REPO = "martinsandor707/particles_combined_all_models"
DEFAULT_REVISION = "main"
DEFAULT_INCLUDE = "ingest/*.parquet,xgboost_models/*.json"
DEFAULT_ROOT = "/sync"

# The only top-level folders the sync may write to: the two mounts.
ALLOWED_PREFIXES = ("ingest/", "xgboost_models/")
# Never touched, whatever the patterns match: the note that ships with the repository.
PROTECTED = frozenset({"ingest/README.md"})

STATE_FOLDER = ".hf-sync"
STATE_FILE = "last-sync.json"
STAGE_FOLDER = "stage"
MODEL_TMP_SUFFIX = ".hf-sync-tmp"

OFF_WORDS = frozenset({"0", "false", "no", "off"})
ON_WORDS = frozenset({"1", "true", "yes", "on"})

ATTEMPTS = 3
BACKOFF_S = 2.0
LIST_TIMEOUT_S = 30.0
HASH_CHUNK = 8 * 1024 * 1024

# Replaced in the tests, so a retry does not sleep.
sleep = time.sleep


class Terminated(KeyboardInterrupt):
    """SIGTERM, raised as an interrupt so the ``finally`` blocks run.

    Python as PID 1 ignores SIGTERM unless a handler is installed, and Docker then kills the
    container after ten seconds. Raising here lets a swap in progress finish or unwind.
    """


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------

def say(message: str) -> None:
    """One log line, prefixed so ``docker compose logs`` shows whose it is."""
    print(PREFIX + message, flush=True)


def fmt_bytes(n: int) -> str:
    """Decimal units, as the Hub and ``hf`` print them."""
    value = float(n)
    for unit in ("B", "kB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{n} B"  # pragma: no cover - the loop returns


def fmt_utc(iso: str) -> str:
    """``2026-11-11T19:40:03+00:00`` as ``2026-11-11 19:40 UTC``; anything else is shown as it is."""
    try:
        return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(iso)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Config:
    enabled: bool
    repo: str
    revision: str
    patterns: tuple[str, ...]
    overwrite: bool
    root: Path


def parse_patterns(text: str | None) -> tuple[str, ...]:
    """Comma-separated patterns; an empty setting means the defaults."""
    parts = tuple(p.strip() for p in (text or "").split(",") if p.strip())
    return parts or tuple(DEFAULT_INCLUDE.split(","))


def read_config(env) -> Config:
    def value(key: str, default: str) -> str:
        return (env.get(key) or "").strip() or default

    return Config(
        enabled=value("HF_SYNC", "1").lower() not in OFF_WORDS,
        repo=value("HF_SYNC_REPO", DEFAULT_REPO),
        revision=value("HF_SYNC_REVISION", DEFAULT_REVISION),
        patterns=parse_patterns(env.get("HF_SYNC_INCLUDE")),
        overwrite=value("HF_SYNC_OVERWRITE", "0").lower() in ON_WORDS,
        root=Path(value("HF_SYNC_ROOT", DEFAULT_ROOT)),
    )


# --------------------------------------------------------------------------------------------
# Privileges, mounts and signals
# --------------------------------------------------------------------------------------------

def plan_privilege_drop(euid: int, owner_uid: int, owner_gid: int) -> tuple[int, int] | None:
    """The (uid, gid) to become, or None to stay as we are.

    The container starts as root so that it can write into a bind mount whatever its owner is. Files
    written as root would belong to root on the user's computer, and could not be deleted without
    sudo; so when the ingest folder belongs to someone else, the process becomes that someone.
    """
    if euid != 0 or owner_uid == 0:
        return None
    return owner_uid, owner_gid


def drop_privileges(uid: int, gid: int) -> None:
    """Become ``uid:gid`` for good. Order matters: the group IDs go while we can still change them."""
    try:
        os.setgroups([])
    except OSError:
        pass  # Best effort: the groups of root are harmless once the uid is not root's.
    os.setgid(gid)
    os.setuid(uid)
    # The image sets HF_HOME; a user without a home directory must not make the hub look for one.
    os.environ.setdefault("HF_HOME", "/tmp/hf-home")


def current_uid() -> int | str:
    return os.geteuid() if hasattr(os, "geteuid") else "?"


def mount_problem(folder: Path) -> str | None:
    """Why this process cannot write into ``folder``, or None when it can.

    Checked after the privilege drop: the drop follows ``ingest/``'s owner, so a ``xgboost_models/``
    that belongs to someone else (a checkout made with sudo) is only found out here.
    """
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # reported just below, with the owner
    if os.access(folder, os.W_OK | os.X_OK):
        return None
    try:
        owner = f"uid {folder.stat().st_uid}"
    except OSError:
        owner = "an unknown owner"
    return (f"{folder} is not writable: it belongs to {owner} and this process runs as uid {current_uid()}. "
            f"Give it to the user who runs Docker (for example sudo chown -R $USER {folder.name}) and start again")


def install_sigterm_handler():
    """Turn SIGTERM into an interrupt; returns the previous handler, or None where none could be set."""
    def handler(signum, frame):
        raise Terminated()

    try:
        if threading.current_thread() is not threading.main_thread():
            return None
        return signal.signal(signal.SIGTERM, handler)
    except (ValueError, OSError):
        return None


# --------------------------------------------------------------------------------------------
# The listing and the last sync
# --------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Entry:
    """One file of the dataset at the resolved commit."""

    path: str
    size: int
    etag: str


def safe_path(path: str) -> bool:
    """A path inside one of the two mounts, with no way out of them."""
    parts = path.split("/")
    return (path.startswith(ALLOWED_PREFIXES) and ".." not in parts and "" not in parts
            and not path.startswith("/"))


def matches(path: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def select_files(files, patterns) -> list[Entry]:
    """Keep what the patterns match, inside the two mounts, never the protected note.

    ``fnmatch.fnmatchcase`` with ``*`` crossing ``/``, the way ``hf download --include`` matches, so
    ``xgboost_models/*.json`` reaches ``xgboost_models/xgboost_pion/standalone_angle_s1_model.json``.
    """
    chosen = []
    for f in files:
        path = f.path
        if path in PROTECTED or not safe_path(path) or not matches(path, patterns):
            continue
        lfs = getattr(f, "lfs", None)
        etag = (getattr(lfs, "sha256", None) if lfs is not None else None) or f.blob_id
        chosen.append(Entry(path=path, size=int(f.size), etag=str(etag)))
    return sorted(chosen, key=lambda e: e.path)


def local_matches(cfg: Config) -> list[str]:
    """Paths under the two mounts that the patterns match, ignoring hidden folders (``.hf-sync/``)."""
    found = []
    for top in ("ingest", "xgboost_models"):
        base = cfg.root / top
        for folder, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in names:
                path = (Path(folder) / name).relative_to(cfg.root).as_posix()
                if path not in PROTECTED and safe_path(path) and matches(path, cfg.patterns):
                    found.append(path)
    return sorted(found)


def read_last_sync(state: Path) -> dict | None:
    """The record, or None when there is none or it cannot be read."""
    path = state / STATE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        say(f"warning: {path} could not be read ({exc}); treating this as a first sync.")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        say(f"warning: {path} is not a sync record; treating this as a first sync.")
        return None
    return data


def valid_entry(rec) -> dict | None:
    """One file's record, or None when it is not a record (a hand-edited or damaged entry)."""
    if (isinstance(rec, dict) and isinstance(rec.get("bytes"), int) and isinstance(rec.get("mtime_ns"), int)
            and isinstance(rec.get("etag"), str)):
        return rec
    return None


def write_last_sync(state: Path, record: dict) -> None:
    """Atomically: a temporary file in the same folder, flushed, then renamed over the record."""
    target = state / STATE_FILE
    tmp = state / (STATE_FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=1, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


# --------------------------------------------------------------------------------------------
# The per-file decision, by content
# --------------------------------------------------------------------------------------------

DOWNLOAD, UPDATE, ADOPT, UNCHANGED, KEPT = "download", "update", "adopt", "unchanged", "kept"

SHA256, GIT_SHA1 = "sha256", "git-sha1"


def etag_kind(etag: str) -> str | None:
    """How to hash a file to compare it with ``etag``: 64 hex digits are an LFS SHA-256, 40 a Git blob id."""
    if len(etag) == 64 and all(c in "0123456789abcdef" for c in etag):
        return SHA256
    if len(etag) == 40 and all(c in "0123456789abcdef" for c in etag):
        return GIT_SHA1
    return None


def file_digest(path: Path, kind: str, size: int) -> str:
    """The hex digest ``etag_kind`` names, read in 8 MiB chunks. Git's blob id hashes a header first."""
    digest = hashlib.sha256() if kind == SHA256 else hashlib.sha1()
    if kind == GIT_SHA1:
        digest.update(b"blob %d\0" % size)
    with open(path, "rb") as handle:
        while chunk := handle.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def decide(entry: Entry, local: os.stat_result | None, record, overwrite: bool, digest) -> tuple[str, str]:
    """(action, reason) for one file.

    ``record`` is this file's entry of ``last-sync.json``; ``digest(kind)`` hashes the local file (it
    is called only when a comparison is possible, and the caller may cache and announce it).

    1. missing: download;
    2. the record exists and the file's size and mtime equal it: the sync's own copy, so unchanged
       when the dataset's etag is the recorded one, else an update;
    3. otherwise hash it: equal to the dataset's etag is adopted; equal to the recorded etag is an
       untouched older copy, so an update; anything else is kept (or replaced with the opt-in).
    """
    if local is None:
        return DOWNLOAD, "not on this computer"
    if not stat_module.S_ISREG(local.st_mode):
        if overwrite:
            return UPDATE, "is a link or a folder, not a file; replaced (HF_SYNC_OVERWRITE=1)"
        return KEPT, "is a link or a folder, not a file; kept"
    rec = valid_entry(record)
    if rec is not None and local.st_size == rec["bytes"] and local.st_mtime_ns == rec["mtime_ns"]:
        if rec["etag"] == entry.etag:
            return UNCHANGED, "in step with the dataset"
        return UPDATE, "the dataset has a newer version"

    upstream = etag_kind(entry.etag)
    if upstream is not None and local.st_size == entry.size and digest(upstream) == entry.etag:
        return ADOPT, "already the dataset's content; recorded without a download"
    if rec is not None and rec["etag"] != entry.etag and local.st_size == rec["bytes"]:
        older = etag_kind(rec["etag"])
        if older is not None and digest(older) == rec["etag"]:
            return UPDATE, "an untouched copy of the last sync's older version; the dataset has a newer one"

    if rec is not None:
        if overwrite:
            return UPDATE, "changed on this computer since the last sync; replaced (HF_SYNC_OVERWRITE=1)"
        return KEPT, "changed on this computer since the last sync; kept"
    if overwrite:
        return UPDATE, "differs from the dataset; replaced (HF_SYNC_OVERWRITE=1)"
    return KEPT, "differs from the dataset; kept"


def lstat_or_none(path: Path) -> os.stat_result | None:
    """``lstat``: a dangling link is not "missing", and a link is not followed."""
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------------

UNREACHABLE, DENIED, LOCAL, OTHER = "unreachable", "denied", "local", "other"

# Errors that retrying cannot mend: the disk or its permissions.
_LOCAL_ERRNOS = frozenset({errno.ENOSPC, errno.EACCES, errno.EPERM, errno.EROFS, errno.EDQUOT})


def status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def classify(exc: BaseException) -> str:
    """UNREACHABLE (connection, timeout, offline mode, HTTP 5xx or 429), DENIED (401, 403, 404, no
    such repository or revision), LOCAL (the disk) or OTHER.

    The transport classes mirror what ``huggingface_hub/_snapshot_download.py`` treats as offline.
    """
    status = status_of(exc)
    if HfHubHTTPError is not None and isinstance(exc, HfHubHTTPError) or status is not None:
        if status in (401, 403, 404):
            return DENIED
        if status is not None and (status >= 500 or status in (408, 429)):
            return UNREACHABLE
        return OTHER
    transport = (httpx2.TransportError,) if httpx2 is not None else ()
    offline = (OfflineModeIsEnabled,) if OfflineModeIsEnabled is not None else ()
    if isinstance(exc, transport + offline + (ConnectionError, TimeoutError)):
        return UNREACHABLE
    if isinstance(exc, OSError) and exc.errno in _LOCAL_ERRNOS:
        return LOCAL
    return OTHER


def describe(exc: BaseException) -> str:
    """One line for the log: the class and the first line of the message."""
    text = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def denied_reason(exc: BaseException, cfg: Config) -> str:
    status = status_of(exc)
    where = f"dataset {cfg.repo} at revision {cfg.revision}"
    if status == 404:
        return (f"{where} was not found (HTTP 404). Check HF_SYNC_REPO and HF_SYNC_REVISION; a private "
                "repository also answers 404 without a token.")
    return (f"Hugging Face refused access to {where} (HTTP {status}). "
            "A private or gated dataset needs a token in HF_TOKEN (compose passes it on); a repository that "
            "does not exist is also answered with 401.")


# --------------------------------------------------------------------------------------------
# The Hub, injectable
# --------------------------------------------------------------------------------------------

class HubClient:
    """The three Hub calls the sync makes. Tests pass an object with the same three methods."""

    def __init__(self):
        from huggingface_hub import HfApi, hf_hub_download

        self._api = HfApi()
        self._download = hf_hub_download

    def resolve(self, repo: str, revision: str) -> str:
        """The commit that ``revision`` names right now."""
        return self._api.dataset_info(repo, revision=revision, timeout=LIST_TIMEOUT_S).sha

    def list_files(self, repo: str, commit: str):
        return [f for f in self._api.list_repo_tree(repo, recursive=True, revision=commit, repo_type="dataset")
                if hasattr(f, "size")]

    def download(self, repo: str, path: str, commit: str, local_dir: str, force: bool) -> str:
        return self._download(repo_id=repo, filename=path, repo_type="dataset", revision=commit,
                              local_dir=local_dir, force_download=force)


def with_retries(call, label: str):
    """Run ``call()``; up to ATTEMPTS tries with growing pauses, but only for errors that can pass."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - classified right below
            kind = classify(exc)
            offline_mode = OfflineModeIsEnabled is not None and isinstance(exc, OfflineModeIsEnabled)
            if kind in (DENIED, LOCAL) or offline_mode or attempt == ATTEMPTS:
                raise
            pause = BACKOFF_S * 2 ** (attempt - 1)
            say(f"warning: {label}: {describe(exc)}; retrying in {pause:g} s (attempt {attempt + 1} of {ATTEMPTS}).")
            sleep(pause)
    raise AssertionError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------------------------
# Offline fallback
# --------------------------------------------------------------------------------------------

def offline_outcome(cfg: Config, state: Path, exc: BaseException) -> int:
    """The Hub cannot be reached: 0 only if the last sync finished and its files are all here and whole.

    "Finished" is the record's ``complete`` flag; "all here" is every ``expected`` path, at its
    recorded size (a file kept on purpose only has to exist). A record without both, such as one left
    by an interrupted first sync, is refused: the dashboard would start without its datasets.
    """
    record = read_last_sync(state)
    if not record or not record["files"] and not record.get("expected"):
        say(f"error: Hugging Face could not be reached ({describe(exc)}) and nothing was ever synced to "
            f"{cfg.root / 'ingest'}. Connect to the internet and start again, or download the files "
            "by hand (see the README's Quick start).")
        return 1
    expected = record.get("expected")
    expected = sorted(p for p in expected if isinstance(p, str)) if isinstance(expected, list) else []
    kept = set(record["kept"]) if isinstance(record.get("kept"), list) else set()
    finished = record.get("complete") is True and bool(expected)

    problems = []
    for path in expected:
        stat = lstat_or_none(cfg.root / path)
        rec = valid_entry(record["files"].get(path))
        if stat is None:
            problems.append(f"{path} is missing")
        elif path in kept:
            continue
        elif rec is None:
            problems.append(f"{path} was never recorded as complete")
        elif stat.st_size != rec["bytes"]:
            problems.append(f"{path} has {stat.st_size:,} bytes, the last sync recorded {rec['bytes']:,}")
    when = fmt_utc(record.get("synced_at", ""))
    if not finished or problems:
        reason = ("the last sync did not finish" if not finished else "the files of the last sync are not complete")
        say(f"error: Hugging Face could not be reached ({describe(exc)}), and {reason} ({when})"
            + (":" if problems else "; start again with a connection to finish it."))
        for problem in problems:
            say(f"  {problem}")
        return 1
    say(f"warning: Hugging Face could not be reached ({describe(exc)}); starting with the files of the "
        f"last sync, {when}.")
    return 0


# --------------------------------------------------------------------------------------------
# Fetching one file: download into the stage, then swap into place
# --------------------------------------------------------------------------------------------

def clear_partials(stage: Path) -> None:
    """Delete ``.incomplete`` files left by a killed download.

    ``huggingface_hub`` 2.3.0 names each partial file uniquely and never reopens one, so a leftover
    cannot resume; it only holds disk space.
    """
    freed = 0
    for partial in (stage / ".cache" / "huggingface" / "download").rglob("*.incomplete"):
        try:
            size = partial.stat().st_size
            partial.unlink()
            freed += size
        except OSError:
            pass
    if freed:
        say(f"removed {fmt_bytes(freed)} of partial downloads left by an interrupted run.")


def forget_stage_metadata(stage: Path, path: str) -> None:
    """Drop ``hf``'s metadata for a file that has left the stage, so it can never vouch for a later one."""
    try:
        (stage / ".cache" / "huggingface" / "download" / (path + ".metadata")).unlink(missing_ok=True)
    except OSError:
        pass


def swap_into_place(cfg: Config, stage: Path, entry: Entry) -> os.stat_result:
    """Move the whole staged file to its final place and return its stat.

    ``ingest/``: one ``os.replace`` on the same mount. ``xgboost_models/``: a copy to a sibling
    ``.hf-sync-tmp`` name on its own mount, fsynced, then ``os.replace``; the staged copy goes last.
    The old file is whole until the rename, and the rename is atomic.
    """
    staged = stage / entry.path
    dest = cfg.root / entry.path
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if entry.path.startswith("ingest/"):
            os.replace(staged, dest)
        else:
            tmp = dest.with_name(dest.name + MODEL_TMP_SUFFIX)
            try:
                shutil.copyfile(staged, tmp)
                with open(tmp, "rb+") as handle:
                    os.fsync(handle.fileno())
                os.replace(tmp, dest)
            finally:
                tmp.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)
    except PermissionError as exc:
        owner = None
        try:
            owner = dest.parent.stat().st_uid
        except OSError:
            pass
        raise PermissionError(
            errno.EACCES, f"cannot write into {dest.parent}: it belongs to uid {owner} and the sync runs as uid "
            f"{current_uid()}") from exc
    forget_stage_metadata(stage, entry.path)
    stat = lstat_or_none(dest)
    if stat is None:  # pragma: no cover - the rename just succeeded
        raise OSError(f"{entry.path} is not on disk after the swap")
    return stat


def fetch(client, cfg: Config, stage: Path, commit: str, entry: Entry) -> os.stat_result:
    """Download one file into the stage, check it, swap it into place; return its stat, or raise.

    ``force_download`` is always off: the stage never holds an outdated file (a finished one is moved
    away), so ``hf`` downloads, and a staged file that is already whole and matches the listing, left
    by a run killed before its swap, is simply swapped.
    """
    staged = stage / entry.path

    def attempt():
        client.download(cfg.repo, entry.path, commit, str(stage), False)
        stat = lstat_or_none(staged)
        if stat is None:
            raise OSError(f"{entry.path} is not on disk after the download")
        if stat.st_size != entry.size:
            size = stat.st_size
            staged.unlink(missing_ok=True)  # never let a short file be reused or swapped
            forget_stage_metadata(stage, entry.path)
            raise OSError(f"{entry.path} has {size:,} bytes, the dataset lists {entry.size:,}")

    with_retries(attempt, entry.path)
    return swap_into_place(cfg, stage, entry)


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def plan(entries, cfg: Config, record: dict | None):
    """[(entry, action, reason)] in path order. Hashing announces itself, one line per file."""
    known = (record or {}).get("files", {})
    rows = []
    for entry in entries:
        dest = cfg.root / entry.path
        local = lstat_or_none(dest)
        cache: dict[str, str] = {}

        def digest(kind: str, dest=dest, entry=entry, local=local) -> str:
            if not cache:
                say(f"Checking {entry.path} ({fmt_bytes(local.st_size)}) against the dataset…")
            if kind not in cache:
                cache[kind] = file_digest(dest, kind, local.st_size)
            return cache[kind]

        action, reason = decide(entry, local, known.get(entry.path), cfg.overwrite, digest)
        rows.append((entry, action, reason))
    return rows


def print_plan(rows, commit: str, cfg: Config) -> None:
    say(f"plan for {cfg.repo} at {cfg.revision} (commit {commit[:10]}):")
    for entry, action, reason in rows:
        say(f"  {action:<9} {entry.path} ({fmt_bytes(entry.size)}): {reason}")
    todo = [e for e, a, _ in rows if a in (DOWNLOAD, UPDATE)]
    by_folder = {}
    for entry in todo:
        folder = entry.path.split("/", 1)[0] + "/"
        by_folder[folder] = by_folder.get(folder, 0) + 1
    detail = ", ".join(f"{n} in {folder}" for folder, n in sorted(by_folder.items()))
    adopted = sum(1 for _, a, _ in rows if a == ADOPT)
    say(f"plan: {len(todo)} of {len(rows)} files to fetch ({fmt_bytes(sum(e.size for e in todo))})"
        + (f": {detail}" if detail else "") + (f"; {adopted} already here and to be adopted" if adopted else "")
        + ". Dry run: nothing was downloaded.")


def run(cfg: Config, client, dry_run: bool) -> int:
    ingest = cfg.root / "ingest"
    state = ingest / STATE_FOLDER
    stage = state / STAGE_FOLDER

    # 1. The state folder, once the ingest mount is known to be writable.
    unwritable: dict[str, str] = {}
    if not dry_run:
        problem = mount_problem(ingest)
        if problem:
            say(f"error: {problem}. Nothing can be downloaded; start with HF_SYNC=0 to use the files as they are.")
            return 1
        state.mkdir(parents=True, exist_ok=True)
        stage.mkdir(parents=True, exist_ok=True)
        clear_partials(stage)
        problem = mount_problem(cfg.root / "xgboost_models")
        if problem:
            unwritable["xgboost_models/"] = problem
            say(f"warning: {problem}. The datasets are still synced; the models are not.")

    # 2. What the dataset holds at one commit.
    try:
        commit = with_retries(lambda: client.resolve(cfg.repo, cfg.revision), "resolving the revision")
        files = with_retries(lambda: client.list_files(cfg.repo, commit), "listing the dataset")
    except Exception as exc:  # noqa: BLE001
        kind = classify(exc)
        if kind == DENIED:
            say("error: " + denied_reason(exc, cfg))
            return 1
        if kind == UNREACHABLE:
            return offline_outcome(cfg, state, exc)
        say(f"error: could not read the dataset listing ({describe(exc)}).")
        return 1

    entries = select_files(files, cfg.patterns)
    say(f"{cfg.repo} at {cfg.revision}: commit {commit[:10]}, {len(entries)} files match "
        f"{', '.join(cfg.patterns)} ({fmt_bytes(sum(e.size for e in entries))}).")
    if not entries:
        here = local_matches(cfg)
        if not here:
            say("error: no file of the dataset matches HF_SYNC_INCLUDE and no local file does either; check the "
                "patterns and the revision, or start with HF_SYNC=0.")
            return 1
        say("warning: no file of the dataset matches HF_SYNC_INCLUDE; check the patterns and the revision. "
            f"The {len(here)} matching file(s) already here are used as they are.")
        return 0

    record = read_last_sync(state)
    rows = plan(entries, cfg, record)
    if dry_run:
        print_plan(rows, commit, cfg)
        return 0

    # 3. Record the intent before any download, then work through the files, saving after each.
    synced = {p: r for p, r in (record or {}).get("files", {}).items() if valid_entry(r) is not None}
    header = {"repo": cfg.repo, "revision": cfg.revision, "commit": commit}
    expected = [e.path for e in entries]
    kept = sorted(e.path for e, a, _ in rows if a == KEPT)
    counts = {DOWNLOAD: 0, UPDATE: 0, ADOPT: 0, UNCHANGED: 0, KEPT: 0}
    fetched_bytes = {DOWNLOAD: 0, UPDATE: 0}
    failed = []

    def save(complete: bool = False):
        write_last_sync(state, {**header, "synced_at": now_iso(), "expected": expected, "complete": complete,
                                "kept": kept, "files": synced})

    save()

    needed = sum(e.size for e, a, _ in rows if a in (DOWNLOAD, UPDATE))
    try:
        free = shutil.disk_usage(ingest).free
        if needed > free:
            say(f"warning: {fmt_bytes(needed)} to download but only {fmt_bytes(free)} free in {ingest}.")
    except OSError:
        pass

    for entry, action, reason in rows:
        if action == UNCHANGED:
            counts[UNCHANGED] += 1
            continue
        if action == KEPT:
            counts[KEPT] += 1
            say(f"warning: {entry.path} {reason}.")
            continue
        dest = cfg.root / entry.path
        before = lstat_or_none(dest)
        if action == ADOPT:
            stat = lstat_or_none(dest)
            counts[ADOPT] += 1
            synced[entry.path] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "etag": entry.etag}
            save()
            say(f"{entry.path} is already the dataset's content; adopted.")
            continue
        folder = entry.path.split("/", 1)[0] + "/"
        if folder in unwritable:
            failed.append(entry.path)
            say(f"error: {entry.path} was not fetched: {folder} is not writable by this process. "
                + ("The previous copy is untouched." if before is not None else "It is not on this computer."))
            continue
        verb = {DOWNLOAD: "Downloading", UPDATE: "Updating"}[action]
        say(f"{verb} {entry.path} ({fmt_bytes(entry.size)})… [{reason}]")
        started = time.monotonic()
        try:
            stat = fetch(client, cfg, stage, commit, entry)
        except Exception as exc:  # noqa: BLE001
            failed.append(entry.path)
            say(f"error: {entry.path} failed ({describe(exc)}); "
                + ("the previous copy is untouched." if before is not None else "it is not on this computer."))
            continue
        counts[action] += 1
        fetched_bytes[action] += entry.size
        synced[entry.path] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "etag": entry.etag}
        save()
        say(f"… {entry.path} done in {time.monotonic() - started:.1f} s.")

    # 4. Is every expected file here, whole, and either recorded or kept on purpose?
    def satisfied(entry: Entry) -> bool:
        stat = lstat_or_none(cfg.root / entry.path)
        if stat is None or entry.path in failed:
            return False
        if entry.path in kept:
            return True
        rec = valid_entry(synced.get(entry.path))
        return rec is not None and rec["bytes"] == entry.size == stat.st_size

    complete = all(satisfied(e) for e in entries)
    save(complete)

    def tally(key: str, word: str) -> str:
        return f"{counts[key]} {word}" + (f" ({fmt_bytes(fetched_bytes[key])})" if counts[key] else "")

    parts = [tally(DOWNLOAD, "downloaded"), tally(UPDATE, "updated"), f"{counts[ADOPT]} adopted",
             f"{counts[UNCHANGED]} unchanged", f"{counts[KEPT]} kept"]
    say(f"{len(rows)} files examined: " + ", ".join(parts) + ".")
    if failed:
        say(f"error: {len(failed)} file(s) are missing or unfinished: " + ", ".join(failed)
            + ". The previous copy of each is untouched. Run docker compose up again to continue (finished files "
              "are not downloaded again), or start with HF_SYNC=0 to use the files as they are.")
        return 1
    return 0


def main(argv=None, env=None, api=None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync ingest/ and xgboost_models/ with the Hugging Face dataset (settings are HF_SYNC_* variables).")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be downloaded, changing nothing on disk")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    cfg = read_config(env)

    if not cfg.enabled:
        say(f"skipped: HF_SYNC={env.get('HF_SYNC')}; the files in ingest/ and xgboost_models/ are used as they are.")
        return 0

    previous = install_sigterm_handler()
    try:
        root_ingest = cfg.root / "ingest"
        if not args.dry_run and os.name == "posix" and root_ingest.is_dir():
            stat = root_ingest.stat()
            target = plan_privilege_drop(os.geteuid(), stat.st_uid, stat.st_gid)
            if target is not None:
                drop_privileges(*target)
                say(f"running as uid {target[0]}, gid {target[1]}, the owner of {root_ingest}, so the files "
                    "belong to you.")

        try:
            client = api if api is not None else HubClient()
        except ImportError as exc:
            say(f"error: huggingface_hub is not installed ({exc}).")
            return 1
        return run(cfg, client, args.dry_run)
    except KeyboardInterrupt as exc:
        code = 143 if isinstance(exc, Terminated) else 130
        say("interrupted. Every file already in place is whole and the download that was running was not "
            "swapped in. Run docker compose up again to continue.")
        return code
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # the slim image's locale may be plain ASCII
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
