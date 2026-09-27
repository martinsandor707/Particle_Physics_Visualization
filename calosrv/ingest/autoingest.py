"""Ingest the datasets dropped into a folder: once each, and never over an existing one.

At every start - and on the Admin Settings panel's Scan now - the server looks
in ``CALOSRV_AUTO_INGEST_DIR`` (compose: the repository's ./ingest, mounted
read-only) and turns each new CSV or Parquet file into an experiment named
after it. It is idempotent by construction. A file is skipped when its
experiment already exists in any form - a registry row in any status, a table,
an archive - or when the same file is already archived under another name.
Nothing is ever forced; replacing an experiment is the upload dialog's Replace,
asked for explicitly.

The scan only decides and queues. The ingests run on the single worker every
upload uses, one at a time, so the server answers at once and memory holds one
ingest at a time. A file that fails its pre-flight check is reported and left
alone, rather than becoming a failed experiment at every boot. An ingest that
crashes leaves a registry row, which the next boot sees as existing, so a bad
file cannot put a restarting container into a loop.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import catalog, naming, registry
from ..errors import IngestError, InsufficientStorageError, ValidationError
from . import formats, stream
from .load import MODE_CREATE_NEW
from .stream import StagedFile

log = logging.getLogger(__name__)

#: The suffixes the scan picks up. ``.txt`` is accepted by the other routes but
#: not collected here: a folder of notes should not become experiments.
SCANNED_SUFFIXES = (".csv", ".parquet")

#: Names of files still being written by the usual tools.
_TEMPORARY_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".download")

#: Scans are serialised: two at once could each queue the same new file.
_SCAN_LOCK = threading.Lock()


@dataclass
class ScanEntry:
    """What the scan did with one file. ``action`` is one of the documented outcomes."""

    file: str
    table_name: str | None
    action: str
    detail: str = ""
    job_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.file, "table_name": self.table_name, "action": self.action,
                "detail": self.detail, "job_id": self.job_id}


@dataclass
class ScanReport:
    """One scan of the drop folder, as the Admin Settings panel shows it."""

    enabled: bool
    dir: str | None
    scanned_at: str | None = None
    entries: list[ScanEntry] = field(default_factory=list)
    #: Why the scan did not run, when it did not.
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "dir": self.dir, "scanned_at": self.scanned_at,
                "reason": self.reason, "entries": [e.as_dict() for e in self.entries]}


def candidates(root: Path, settle_s: float, now: float) -> tuple[list[Path], list[ScanEntry]]:
    """The files to consider, and entries for those that cannot be yet.

    Only the folder's top level. Hidden and temporary names are passed over
    silently; a file modified in the last ``settle_s`` seconds is reported as
    still being written, and a link whose target the container cannot see is
    reported rather than skipped without a word.
    """
    files: list[Path] = []
    waiting: list[ScanEntry] = []
    for path in sorted(root.iterdir()):
        name = path.name
        if name.startswith((".", "~")) or name.lower().endswith(_TEMPORARY_SUFFIXES):
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if path.is_symlink() and not path.exists():
            waiting.append(ScanEntry(name, None, "rejected",
                                     "A link whose target is not visible inside the container. "
                                     "Move or hard-link the file into the folder instead."))
            continue
        try:
            if not path.is_file():
                continue
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < settle_s:
            waiting.append(ScanEntry(
                name, None, "unsettled",
                # A clock ahead of the server's gives a negative age: "just now".
                f"Modified {max(age, 0.0):.0f} s ago. It is picked up once it has been unchanged for "
                f"{settle_s:.0f} s: at the next start, or with Scan now.",
            ))
            continue
        files.append(path)
    return files, waiting


def scan(database, settings: Settings, store) -> ScanReport:
    """Queue an ingest for every new file in the drop folder. Never raises."""
    root = settings.auto_ingest_dir
    if root is None:
        return ScanReport(enabled=False, dir=None, reason="CALOSRV_AUTO_INGEST_DIR is not set.")
    if not root.is_dir():
        log.warning("Automatic ingest is off: the drop folder %s does not exist", root)
        return ScanReport(enabled=False, dir=str(root),
                          reason=f"The drop folder {root} does not exist.")

    with _SCAN_LOCK:
        report = ScanReport(
            enabled=True, dir=str(root),
            scanned_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        )
        try:
            files, waiting = candidates(root, settings.auto_ingest_settle_s, time.time())
        except OSError as exc:
            report.reason = f"The drop folder could not be read: {exc}"
            log.warning("Automatic ingest: %s", report.reason)
            return report
        report.entries.extend(waiting)

        claimed: dict[str, str] = {}
        active = store.active_names()
        for path in files:
            try:
                entry = _consider(database, settings, store, path, claimed, active)
            except Exception as exc:  # noqa: BLE001 - one file must never stop the scan
                log.exception("Automatic ingest could not consider %s", path.name)
                entry = ScanEntry(path.name, None, "rejected", f"Could not be examined: {exc}")
            report.entries.append(entry)
        report.entries.sort(key=lambda e: e.file)

    for entry in report.entries:
        if entry.action != "exists":  # that line is logged where it is decided
            log.info("Automatic ingest: %s -> %s. %s", entry.file, entry.action, entry.detail)
    return report


def _consider(database, settings: Settings, store, path: Path,
              claimed: dict[str, str], active: set[str]) -> ScanEntry:
    """Decide what to do with one file, in order: name, collisions, existence, checks."""
    try:
        name = naming.derive_experiment_name(path.stem)
    except ValidationError as exc:
        return ScanEntry(path.name, None, "invalid_name",
                         f"{exc.detail} Rename the file, or ingest it from the upload dialog.")
    if name in claimed:
        return ScanEntry(path.name, name, "name_collision",
                         f"{claimed[name]} already takes the name {name!r} in this scan.")
    claimed[name] = path.name

    with database.read_cursor() as con:
        present = catalog.presence(con, settings, name)
    if present.exists:
        # The wording the operations directive specifies, for grepping the log.
        log.info("Table '%s' already exists in database catalog. Skipping automatic ingestion.",
                 name)
        detail = f"Experiment {name!r} already exists ({present.describe()})."
        if present.status == registry.STATUS_FAILED:
            detail += " It failed earlier: re-ingest it from the upload dialog with Replace ticked."
        return ScanEntry(path.name, name, "exists", detail)
    if name in active:
        return ScanEntry(path.name, name, "queued",
                         f"An ingest into {name!r} is already queued or running.")

    size = path.stat().st_size
    twin = catalog.archived_as(settings, path.name, size)
    if twin is not None:
        return ScanEntry(path.name, name, "same_source",
                         f"This file ({size:,} bytes) is already archived as experiment {twin!r}.")

    try:
        fmt = formats.detect_format(path)
        with database.read_cursor() as con:
            check = formats.validate(con, path, fmt)
        stream.check_free_space(settings.data_dir, size,
                                formats.headroom_factor(settings, fmt, staged=False))
    except InsufficientStorageError as exc:
        return ScanEntry(path.name, name, "no_space", exc.detail)
    except IngestError as exc:
        return ScanEntry(path.name, name, "rejected", exc.detail)

    job = store.submit(
        table_name=name,
        staged=StagedFile(path=path, original_name=path.name, size_bytes=size),
        mode=MODE_CREATE_NEW,
        display_name=path.stem,
        # The file belongs to whoever dropped it; the ingest reads it in place.
        delete_source=False,
    )
    rows = f", {check.rows:,} rows" if check.rows is not None else ""
    return ScanEntry(path.name, name, "submitted",
                     f"Queued as a {fmt.upper()} ingest ({size:,} bytes{rows}).", job_id=job.job_id)
