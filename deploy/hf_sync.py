"""Keep the repository's ``ingest/`` and ``xgboost_models/`` folders in step with the Hugging Face dataset.

This is the ``hf-sync`` service of ``docker-compose.yml``: a one-shot container that runs before the
dashboard starts, so that ``docker compose up`` is the only command a user needs, today and after
every ``git pull``. The dashboard waits for it (``service_completed_successfully``), which is why the
exit code carries the meaning:

* 0: the folders hold what the dataset lists, or the Hub could not be reached and the files of the
  last sync are complete;
* 1: something that the dashboard needs is missing or unfinished, named in the log.

Rules the code keeps, each one a decision of the design, not an accident:

* Nothing is ever deleted. A local file the dataset does not list is never touched, and neither is
  ``ingest/README.md``.
* A file edited on this computer since the last sync is kept, not overwritten, unless
  ``HF_SYNC_OVERWRITE=1``. Whether it was edited is told from what the previous run recorded in
  ``ingest/.hf-sync/last-sync.json`` (size and modification time), so the answer costs no hashing.
* A file already in step with the dataset costs no network call at all.
* A finished file appears by an atomic rename: ``<root>/.cache`` is a symlink to ``ingest/.hf-sync``,
  so ``huggingface_hub`` keeps its metadata and ``.incomplete`` files on the ingest mount itself,
  where the rename cannot cross a filesystem.
* An update never loses the old copy: ``huggingface_hub`` unlinks the outdated file before it
  downloads, so a hard link to it is held until the new file is verified, and put back on failure.

The hub calls are injectable (``main(api=...)``), so the tests run without a network.
"""

from __future__ import annotations

import argparse
import dataclasses
import errno
import fnmatch
import json
import os
import shutil
import sys
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
BACKUP_FOLDER = "previous"

OFF_WORDS = frozenset({"0", "false", "no", "off"})
ON_WORDS = frozenset({"1", "true", "yes", "on"})

ATTEMPTS = 3
BACKOFF_S = 2.0
LIST_TIMEOUT_S = 30.0

# Replaced in the tests, so a retry does not sleep.
sleep = time.sleep


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
# Privileges and folders
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


def link_cache(root: Path, state: Path) -> None:
    """Make ``<root>/.cache`` a symlink to the state folder, so ``hf`` keeps its files on the mount."""
    link = root / ".cache"
    if link.is_symlink():
        if os.readlink(link) == str(state):
            return
        link.unlink()
    elif link.exists():
        say(f"warning: {link} is a real folder, not a link to {state}; left alone, so the Hugging Face "
            "metadata and partial downloads stay there.")
        return
    link.symlink_to(state, target_is_directory=True)


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


def select_files(files, patterns) -> list[Entry]:
    """Keep what the patterns match, inside the two mounts, never the protected note.

    ``fnmatch.fnmatchcase`` with ``*`` crossing ``/``, the way ``hf download --include`` matches, so
    ``xgboost_models/*.json`` reaches ``xgboost_models/xgboost_pion/standalone_angle_s1_model.json``.
    """
    chosen = []
    for f in files:
        path = f.path
        if path in PROTECTED or not safe_path(path):
            continue
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            continue
        lfs = getattr(f, "lfs", None)
        etag = (getattr(lfs, "sha256", None) if lfs is not None else None) or f.blob_id
        chosen.append(Entry(path=path, size=int(f.size), etag=str(etag)))
    return sorted(chosen, key=lambda e: e.path)


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
# The per-file decision
# --------------------------------------------------------------------------------------------

DOWNLOAD, UPDATE, VERIFY, UNCHANGED, KEPT = "download", "update", "verify", "unchanged", "kept"


def decide(entry: Entry, local: os.stat_result | None, record: dict | None,
           overwrite: bool) -> tuple[str, str]:
    """(action, reason) for one file, in the order of the design's table.

    ``record`` is this file's entry of ``last-sync.json``. A ``kept`` file is one the sync leaves
    alone; with ``overwrite`` the same two cases become an ``update``.
    """
    if local is None:
        return DOWNLOAD, "not on this computer"
    if record is not None:
        unchanged_here = (local.st_size == record.get("bytes") and local.st_mtime_ns == record.get("mtime_ns"))
        if unchanged_here:
            if record.get("etag") == entry.etag:
                return UNCHANGED, "in step with the dataset"
            return UPDATE, "the dataset has a newer version"
        if overwrite:
            return UPDATE, "changed on this computer since the last sync; replaced (HF_SYNC_OVERWRITE=1)"
        return KEPT, "changed on this computer since the last sync; kept"
    if local.st_size == entry.size:
        return VERIFY, "first sync: same size as the dataset, checking its content once"
    if overwrite:
        return UPDATE, "differs from the dataset; replaced (HF_SYNC_OVERWRITE=1)"
    return KEPT, "differs from the dataset; kept"


def lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
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
            "A private or gated dataset needs a token in HF_TOKEN; a repository that does not exist is also "
            "answered with 401.")


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
    """The Hub cannot be reached: 0 if the last sync's files are all here and whole, else 1."""
    record = read_last_sync(state)
    if not record or not record["files"]:
        say(f"error: Hugging Face could not be reached ({describe(exc)}) and nothing was ever synced to "
            f"{cfg.root / 'ingest'}. Connect to the internet and start again, or download the files "
            "by hand (see the README's Quick start).")
        return 1
    problems = []
    for path, rec in sorted(record["files"].items()):
        stat = lstat_or_none(cfg.root / path)
        if stat is None:
            problems.append(f"{path} is missing")
        elif stat.st_size != rec.get("bytes"):
            problems.append(f"{path} has {stat.st_size:,} bytes, the last sync recorded {rec.get('bytes'):,}"
                            if isinstance(rec.get("bytes"), int) else f"{path} has no recorded size")
    when = fmt_utc(record.get("synced_at", ""))
    if problems:
        say(f"error: Hugging Face could not be reached ({describe(exc)}), and the files of the last sync "
            f"({when}) are not complete:")
        for problem in problems:
            say(f"  {problem}")
        return 1
    say(f"warning: Hugging Face could not be reached ({describe(exc)}); starting with the files of the "
        f"last sync, {when}.")
    return 0


# --------------------------------------------------------------------------------------------
# Fetching one file
# --------------------------------------------------------------------------------------------

def keep_old_copy(dest: Path, state: Path, path: str) -> Path | None:
    """A hard link to the file about to be replaced, in the state folder; None if there is no file.

    ``huggingface_hub`` unlinks the outdated file before it downloads. The link keeps the old bytes
    reachable until the new file is whole, at the cost of its disk space for that long.
    """
    if not dest.exists():
        return None
    backup = state / BACKUP_FOLDER / path
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.unlink(missing_ok=True)
        os.link(dest, backup)
    except OSError as exc:
        say(f"warning: cannot keep a spare copy of {path} ({exc}); a download that fails would leave it missing.")
        return None
    return backup


def fetch(client, cfg: Config, state: Path, commit: str, entry: Entry, action: str) -> os.stat_result:
    """Download, update or verify one file; return its stat, or raise.

    A failure puts the old file back. The new file is checked against the dataset's size before it is
    accepted.
    """
    dest = cfg.root / entry.path
    backup = keep_old_copy(dest, state, entry.path) if action in (UPDATE, VERIFY) else None
    force = action == UPDATE  # the local file is known to be wrong: no hashing, no "already up to date"

    def attempt():
        client.download(cfg.repo, entry.path, commit, str(cfg.root), force)
        stat = lstat_or_none(dest)
        if stat is None:
            raise OSError(f"{entry.path} is not on disk after the download")
        if stat.st_size != entry.size:
            raise OSError(f"{entry.path} has {stat.st_size:,} bytes, the dataset lists {entry.size:,}")
        return stat

    try:
        stat = with_retries(attempt, entry.path)
    except BaseException:
        if backup is not None:
            try:
                os.replace(backup, dest)
            except OSError as exc:
                say(f"error: could not put the previous {entry.path} back ({exc}); it is kept at {backup}.")
                backup = None
        raise
    finally:
        if backup is not None:
            backup.unlink(missing_ok=True)
    return stat


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def plan(entries, cfg: Config, record: dict | None):
    """[(entry, action, reason)] in path order."""
    known = (record or {}).get("files", {})
    rows = []
    for entry in entries:
        action, reason = decide(entry, lstat_or_none(cfg.root / entry.path), known.get(entry.path), cfg.overwrite)
        rows.append((entry, action, reason))
    return rows


def print_plan(rows, commit: str, cfg: Config) -> None:
    say(f"plan for {cfg.repo} at {cfg.revision} (commit {commit[:10]}):")
    for entry, action, reason in rows:
        say(f"  {action:<9} {entry.path} ({fmt_bytes(entry.size)}): {reason}")
    todo = [(e, a) for e, a, _ in rows if a in (DOWNLOAD, UPDATE, VERIFY)]
    by_folder = {}
    for entry, _ in todo:
        folder = entry.path.split("/", 1)[0] + "/"
        by_folder[folder] = by_folder.get(folder, 0) + 1
    detail = ", ".join(f"{n} in {folder}" for folder, n in sorted(by_folder.items()))
    say(f"plan: {len(todo)} of {len(rows)} files to fetch ({fmt_bytes(sum(e.size for e, _ in todo))})"
        + (f": {detail}" if detail else "") + ". Dry run: nothing was downloaded.")


def run(cfg: Config, client, dry_run: bool) -> int:
    ingest = cfg.root / "ingest"
    state = ingest / STATE_FOLDER

    # 1. The state folder, and the link that puts hf's metadata and partial files on the ingest mount.
    if not dry_run:
        ingest.mkdir(parents=True, exist_ok=True)
        state.mkdir(parents=True, exist_ok=True)
        link_cache(cfg.root, state)

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
        say("warning: no file of the dataset matches HF_SYNC_INCLUDE; check the patterns and the revision. "
            "The files already here are used as they are.")
        return 0

    record = read_last_sync(state)
    rows = plan(entries, cfg, record)
    if dry_run:
        print_plan(rows, commit, cfg)
        return 0

    # 3. Work through the files, saving the record after each success.
    synced = dict((record or {}).get("files", {}))
    header = {"repo": cfg.repo, "revision": cfg.revision, "commit": commit}
    counts = {DOWNLOAD: 0, UPDATE: 0, VERIFY: 0, UNCHANGED: 0, KEPT: 0}
    fetched_bytes = {DOWNLOAD: 0, UPDATE: 0, VERIFY: 0}
    failed = []

    needed = sum(e.size for e, a, _ in rows if a in (DOWNLOAD, UPDATE))
    try:
        free = shutil.disk_usage(ingest).free
        if needed > free:
            say(f"warning: {fmt_bytes(needed)} to download but only {fmt_bytes(free)} free in {ingest}.")
    except OSError:
        pass

    def save():
        write_last_sync(state, {**header, "synced_at": now_iso(), "files": synced})

    for entry, action, reason in rows:
        if action == UNCHANGED:
            counts[UNCHANGED] += 1
            continue
        if action == KEPT:
            counts[KEPT] += 1
            say(f"warning: {entry.path} {reason}.")
            continue
        verb = {DOWNLOAD: "Downloading", UPDATE: "Updating", VERIFY: "Checking"}[action]
        say(f"{verb} {entry.path} ({fmt_bytes(entry.size)})… [{reason}]")
        before = lstat_or_none(cfg.root / entry.path)
        started = time.monotonic()
        try:
            stat = fetch(client, cfg, state, commit, entry, action)
        except Exception as exc:  # noqa: BLE001
            failed.append(entry.path)
            say(f"error: {entry.path} failed ({describe(exc)}); "
                + ("the previous copy is untouched." if before is not None else "it is not on this computer."))
            continue
        # A "verify" that found the content wrong was downloaded by the hub: the file is a new one.
        outcome = action
        if action == VERIFY and (before is None or (stat.st_ino, stat.st_mtime_ns) != (before.st_ino, before.st_mtime_ns)):
            outcome = UPDATE
        counts[outcome] += 1
        fetched_bytes[outcome] += entry.size
        synced[entry.path] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "etag": entry.etag}
        save()
        elapsed = time.monotonic() - started
        say(f"… {entry.path} " + ("matches the dataset" if outcome == VERIFY else "done")
            + f" in {elapsed:.1f} s.")

    # 4. The summary, and the verdict.
    def tally(key: str, word: str) -> str:
        return f"{counts[key]} {word}" + (f" ({fmt_bytes(fetched_bytes[key])})" if counts[key] else "")

    parts = [tally(DOWNLOAD, "downloaded"), tally(UPDATE, "updated"),
             f"{counts[UNCHANGED]} unchanged", f"{counts[KEPT]} kept"]
    if counts[VERIFY]:
        parts.insert(2, f"{counts[VERIFY]} verified in place")
    say(f"{len(rows)} files examined: " + ", ".join(parts) + ".")
    if failed:
        say(f"error: {len(failed)} file(s) are missing or unfinished: " + ", ".join(failed) + ".")
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

    root_ingest = cfg.root / "ingest"
    if not args.dry_run and os.name == "posix" and root_ingest.is_dir():
        # The one write before the privilege drop: /sync belongs to root in the image, so the link to
        # the state folder must be made while we still are root. It touches neither mount.
        if os.geteuid() == 0:
            link_cache(cfg.root, root_ingest / STATE_FOLDER)
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


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # the slim image's locale may be plain ASCII
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
