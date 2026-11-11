"""Which file an experiment's data came from, and whether that file has changed since.

The hf-sync service refreshes ``./ingest`` at every start, so a dataset an
experiment was ingested from can be replaced on disk while the experiment
keeps serving the old data. The drop-folder scan skips an experiment that
exists, by design, so nothing said so. This module is the answer: at ingest
the worker records what the file looked like (``source_info`` on the registry
row), and the Admin Settings panel compares that record with the file as it is
now.

**What is recorded** (:func:`make_info`), exactly: ``origin`` (``drop_folder``,
``local``, ``upload``, ``seed`` or ``cli``), ``name`` (the file name),
``relpath`` (relative to the origin's root, or null), ``path`` (as the server
saw it, for display only), ``bytes``, ``mtime_ns``, ``digest``, ``recorded_at``
and ``job_id`` (the ingest job that produced the current data). The digest is
a BLAKE2b over the size and the first and last mebibyte of the file, so it
costs two reads whatever the file's size; a whole 3 GB file is never hashed.
The fingerprint is taken in the worker immediately before the file is read, so
a file replaced while it waited in the queue is described as the one that was
read, and a load that fails still has it.

**What is concluded** (:func:`inspect`), one of five states:

``unchanged``  size and modification time equal the record;
``changed``    the size differs, or the size is equal, the time differs and the
               sampled content differs;
``touched``    the size is equal, the time differs and the sampled content is
               equal (a copy or a ``touch``: nothing to re-ingest);
``missing``    the origin's folder is not configured, or the file is not in it;
``untracked``  nothing to compare: an upload (the staged copy is deleted), the
               demonstration dataset, a command-line ingest from outside the
               folders the server reads, or a row with no usable record.

``settling`` is separate from the state: a file modified in the last
``auto_ingest_settle_s`` seconds may still be being copied, and is not offered
for a re-ingest yet. A digest is computed only when the size is equal and the
time moved, and never over a whole file.

A row written before source tracking has no record. For it the archive
manifest is the evidence (``basis`` ``legacy``): when exactly one part's file
name derives this experiment's name, the file of that name in the drop folder
is compared with the part's recorded size, and with nothing else. The part
keeps no modification time and no digest, so a file that is newer than the
archive but has the same size is not evidence of a change (a CSV converted to
Parquet after the ingest is exactly that): it is ``unchanged``, and a
Re-ingest of it is offered only with ``force``. That finds a change by size,
never a ``touched``.

:func:`actions` says which of Re-ingest and Retry ingest are offered, with the
reason in a sentence when they are not.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import archive, naming, registry
from ..errors import ValidationError
from . import local

ORIGIN_DROP_FOLDER = "drop_folder"
ORIGIN_LOCAL = "local"
ORIGIN_UPLOAD = "upload"
ORIGIN_SEED = "seed"
ORIGIN_CLI = "cli"
ORIGINS = (ORIGIN_DROP_FOLDER, ORIGIN_LOCAL, ORIGIN_UPLOAD, ORIGIN_SEED, ORIGIN_CLI)

UNCHANGED = "unchanged"
TOUCHED = "touched"
CHANGED = "changed"
MISSING = "missing"
UNTRACKED = "untracked"
STATES = (UNCHANGED, TOUCHED, CHANGED, MISSING, UNTRACKED)

BASIS_RECORDED = "recorded"
BASIS_LEGACY = "legacy"
BASIS_NONE = "none"

#: The first and the last this many bytes of a file are what its digest covers.
SAMPLE_BYTES = 1 << 20

#: The application's own demonstration experiment (``app.BASELINE_TABLE``). It
#: is always described as the seed, whatever its row says: it is rebuilt from
#: the file in the image, never from a folder the operator can change.
BASELINE_TABLE = "experiment_baseline"

#: The action modes of a re-ingest job.
ACTION_REINGEST = "reingest"
ACTION_RETRY = "retry"

REASON_FAILED = "A failed experiment is retried, not re-ingested."
REASON_INGESTING = "It is still being ingested."
REASON_JOB_ACTIVE = "A job for this experiment is queued or running."
REASON_UPLOAD = ("It was uploaded through the browser: there is no file on the server to "
                 "re-ingest from.")
REASON_SEED = "The demonstration dataset ships in the image and is never re-ingested."
REASON_UNCHANGED = "Its source file is unchanged since it was ingested."
REASON_NOT_FAILED = "Only a failed experiment is retried."
#: The detail of a legacy row whose file has the recorded size: all that can be said.
LEGACY_SIZE_ONLY = "Recorded before source tracking: compared by size only."
REASON_NO_RECORD = ("No source file is recorded for this experiment: it was ingested before "
                    "source tracking, and no file in the drop folder carries its name.")
REASON_NO_ARCHIVE = "It has no Parquet archive; replace it from Upload dataset instead."


# ------------------------------------------------------------ the record --


def fingerprint(path: Path) -> dict[str, Any]:
    """``bytes``, ``mtime_ns`` and the sampled ``digest`` of ``path``, from one open handle.

    The digest is BLAKE2b (16 bytes, hex) over the size as eight little-endian
    bytes, then the first ``min(1 MiB, size)`` bytes, then the last
    ``min(1 MiB, size)``. A file of 1 MiB or less is read once and fed once.
    The size and time come from the same handle the bytes are read through, so
    they describe exactly what was hashed.
    """
    with path.open("rb") as handle:
        status = os.fstat(handle.fileno())
        size = status.st_size
        window = min(SAMPLE_BYTES, size)
        hasher = hashlib.blake2b(digest_size=16)
        hasher.update(size.to_bytes(8, "little"))
        hasher.update(handle.read(window))
        if size > SAMPLE_BYTES:
            handle.seek(size - window)
            hasher.update(handle.read(window))
    return {"bytes": size, "mtime_ns": status.st_mtime_ns, "digest": hasher.hexdigest()}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def root_of(settings: Settings, origin: str | None) -> Path | None:
    """The folder an origin's ``relpath`` is relative to, if it has one and it is configured."""
    if origin == ORIGIN_DROP_FOLDER:
        return settings.auto_ingest_dir
    if origin == ORIGIN_LOCAL:
        return settings.local_ingest_dir
    return None


def origin_spec(
    settings: Settings, origin: str, source: Path, name: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """What an ingest says about where its file came from, before the file is read.

    ``relpath`` is relative to the origin's root, null when the file is not
    below it or the origin has none; an upload keeps neither it nor the path,
    because its staged copy is deleted and its name means nothing to the
    server afterwards.
    """
    relpath: str | None = None
    path: str | None = None
    if origin in (ORIGIN_DROP_FOLDER, ORIGIN_LOCAL):
        path = str(source)
        root = root_of(settings, origin)
        if root is not None:
            try:
                relpath = source.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                relpath = None
    elif origin in (ORIGIN_SEED, ORIGIN_CLI):
        path = str(source)
    return {"origin": origin, "name": name or source.name, "relpath": relpath, "path": path,
            "job_id": job_id}


def make_info(spec: dict[str, Any], source: Path, job_id: str | None = None) -> dict[str, Any]:
    """The ``source_info`` to store: ``spec`` from :func:`origin_spec`, plus the file as it is now."""
    return {
        "origin": spec["origin"],
        "name": spec.get("name") or source.name,
        "relpath": spec.get("relpath"),
        "path": spec.get("path"),
        **fingerprint(source),
        "recorded_at": _now_iso(),
        "job_id": job_id or spec.get("job_id"),
    }


# ---------------------------------------------------------------- the state --


@dataclass
class Source:
    """One experiment's source file against its record. ``as_dict`` is the API's ``source``."""

    origin: str | None
    file: str | None
    path: str | None
    state: str
    basis: str
    settling: bool
    recorded: dict[str, Any] | None
    current: dict[str, Any] | None
    detail: str
    #: Not in the payload: the file the actions would read, when it can be read.
    resolved: Path | None = None
    #: The folder it was looked for in.
    root: Path | None = None
    #: The path relative to that folder: what an ingest from it would record.
    relpath: str | None = None
    #: Seconds since the file was modified, when it can be read.
    age_s: float | None = None
    #: Why an untracked source has nothing to compare, as a sentence.
    why: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin, "file": self.file, "path": self.path, "state": self.state,
            "basis": self.basis, "settling": self.settling, "recorded": self.recorded,
            "current": self.current, "detail": self.detail,
        }


def _iso_ns(mtime_ns: int | None) -> str | None:
    if mtime_ns is None:
        return None
    seconds = int(mtime_ns) // 1_000_000_000
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat(timespec="seconds")


def _when(seconds: float) -> str:
    """``2026-11-11 19:40``: a modification time as the sentences write it (UTC follows)."""
    return dt.datetime.fromtimestamp(int(seconds), dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _stat_block(size: int, mtime_ns: int | None) -> dict[str, Any]:
    return {"bytes": int(size), "modified": _iso_ns(mtime_ns)}


def _find(root: Path | None, relpath: str | None) -> tuple[Path | None, Path | None]:
    """``(candidate, found)``: the path under ``root``, and it resolved when it is a file inside it.

    The containment rule is the local ingest's (``local.is_inside``): the path is
    resolved, so ``..`` and symlinks cannot lead out of the root.
    """
    if root is None or not relpath:
        return None, None
    candidate = root / relpath
    try:
        resolved = candidate.resolve()
        if not local.is_inside(root.resolve(), resolved) or not resolved.is_file():
            return candidate, None
    except OSError:
        return candidate, None
    return candidate, resolved


def _folder_name(origin: str | None) -> str:
    return "the local ingest folder" if origin == ORIGIN_LOCAL else "the drop folder"


def _variable(origin: str | None) -> str:
    return "CALOSRV_LOCAL_INGEST_DIR" if origin == ORIGIN_LOCAL else "CALOSRV_AUTO_INGEST_DIR"


def _missing(origin: str | None, file: str | None, relpath: str | None, root: Path | None,
             candidate: Path | None, recorded: dict[str, Any] | None, basis: str) -> Source:
    if root is None:
        detail = (f"Not found: {_folder_name(origin)} is not configured "
                  f"({_variable(origin)}), so {file or 'the source file'} cannot be compared.")
    else:
        detail = f"Not found: {relpath or file} in {root}."
    return Source(
        origin=origin, file=file, path=str(candidate) if candidate is not None else None,
        state=MISSING, basis=basis, settling=False, recorded=recorded, current=None,
        detail=detail, root=root, relpath=relpath,
    )


def _untracked(origin: str | None, file: str | None, why: str, detail: str | None = None,
               basis: str = BASIS_RECORDED, recorded: dict[str, Any] | None = None) -> Source:
    return Source(
        origin=origin, file=file, path=None, state=UNTRACKED, basis=basis, settling=False,
        recorded=recorded, current=None, detail=detail if detail is not None else why, why=why,
    )


def _compare_recorded(info: dict[str, Any], path: Path, settings: Settings, now: float,
                      origin: str | None, file: str | None, root: Path | None,
                      relpath: str | None) -> Source:
    status = path.stat()
    size, mtime_ns = int(status.st_size), int(status.st_mtime_ns)
    recorded_size = int(info.get("bytes") or 0)
    recorded_ns = info.get("mtime_ns")
    recorded_ns = int(recorded_ns) if recorded_ns is not None else None
    before, after = _when((recorded_ns or 0) / 1e9), _when(status.st_mtime)
    if size != recorded_size:
        state = CHANGED
        detail = (f"Size {recorded_size:,} → {size:,} bytes; "
                  f"modified {before} → {after} UTC.")
    elif recorded_ns is not None and mtime_ns == recorded_ns:
        state, detail = UNCHANGED, ""
    else:
        # Equal size, the time moved: the sampled content decides.
        digest = info.get("digest")
        if not digest:
            state = CHANGED
            detail = (f"Same size ({size:,} bytes), modified {before} → {after} UTC; "
                      "no content sample was recorded to compare.")
        elif fingerprint(path)["digest"] != digest:
            state = CHANGED
            detail = (f"Same size ({size:,} bytes) but different content; "
                      f"modified {before} → {after} UTC.")
        else:
            state = TOUCHED
            detail = (f"Modified {before} → {after} UTC; "
                      "the size and sampled content are unchanged.")
    age = now - status.st_mtime
    return Source(
        origin=origin, file=file, path=str(path), state=state, basis=BASIS_RECORDED,
        settling=age < settings.auto_ingest_settle_s,
        recorded=_stat_block(recorded_size, recorded_ns), current=_stat_block(size, mtime_ns),
        detail=detail, resolved=path, root=root, relpath=relpath, age_s=age,
    )


def _seed(record: registry.ExperimentRecord, settings: Settings) -> Source:
    info = record.source_info or {}
    seed = settings.seed_csv
    file = (seed.name if seed is not None else None) or info.get("name") \
        or (record.source_files[0] if record.source_files else None)
    shown = str(seed) if seed is not None else (info.get("path") or file or "the image")
    return _untracked(
        ORIGIN_SEED, file, "The demonstration dataset ships in the image and is never "
        "re-ingested.",
        detail=f"The demonstration dataset ships in the image ({shown}).",
        basis=BASIS_RECORDED if info else BASIS_NONE,
    )


def _recorded(record: registry.ExperimentRecord, settings: Settings, now: float) -> Source:
    info = record.source_info
    origin = info.get("origin")
    file = info.get("name") or (record.source_files[0] if record.source_files else None)

    if origin == ORIGIN_UPLOAD:
        return _untracked(
            ORIGIN_UPLOAD, file, REASON_UPLOAD,
            detail="Uploaded through the browser; the staged copy was deleted after the ingest.",
        )
    if origin == ORIGIN_SEED:
        return _untracked(
            ORIGIN_SEED, file, REASON_SEED,
            detail=f"The demonstration dataset ships in the image ({info.get('path') or file}).",
        )

    recorded = _stat_block(int(info.get("bytes") or 0), info.get("mtime_ns"))
    if origin == ORIGIN_CLI:
        # A command-line ingest is traceable only when its file lies in a folder
        # the server reads; anywhere else the server cannot see it, now or later.
        given = info.get("path")
        found = None
        if given:
            try:
                target = Path(given).resolve()
            except OSError:
                target = None
            for folder, folder_origin in ((settings.auto_ingest_dir, ORIGIN_DROP_FOLDER),
                                          (settings.local_ingest_dir, ORIGIN_LOCAL)):
                if target is not None and folder is not None \
                        and local.is_inside(folder.resolve(), target):
                    found = (folder, target.relative_to(folder.resolve()).as_posix())
                    break
        if found is None:
            why = (f"Ingested from the command line from {given or file}, outside the folders "
                   "the server reads.")
            return _untracked(ORIGIN_CLI, file, why, recorded=recorded)
        root, relpath = found
        candidate, resolved = _find(root, relpath)
        if resolved is None:
            return _missing(ORIGIN_CLI, file, relpath, root, candidate, recorded, BASIS_RECORDED)
        return _compare_recorded(info, resolved, settings, now, ORIGIN_CLI, file, root, relpath)

    if origin in (ORIGIN_DROP_FOLDER, ORIGIN_LOCAL):
        root = root_of(settings, origin)
        relpath = info.get("relpath") or None
        candidate, resolved = _find(root, relpath)
        if resolved is None:
            return _missing(origin, file, relpath, root, candidate, recorded, BASIS_RECORDED)
        return _compare_recorded(info, resolved, settings, now, origin, file, root, relpath)

    return _untracked(origin if origin in ORIGINS else None, file,
                      "No source is recorded for this experiment.", recorded=recorded)


def _legacy(record: registry.ExperimentRecord, settings: Settings, manifest: Any,
            now: float) -> Source:
    """A row with no ``source_info``: judged by the archive manifest and the drop folder."""
    matches = []
    for part in (manifest.parts if manifest is not None else []):
        try:
            derived = naming.derive_experiment_name(Path(part.source_name).stem)
        except ValidationError:
            continue
        if derived == record.table_name:
            matches.append(part)
    if len(matches) != 1:
        file = record.source_files[0] if record.source_files else None
        return _untracked(None, file, REASON_NO_RECORD, basis=BASIS_NONE)

    part = matches[0]
    origin, file, root = ORIGIN_DROP_FOLDER, part.source_name, settings.auto_ingest_dir
    recorded = {"bytes": int(part.source_bytes), "modified": None}
    candidate, resolved = _find(root, file)
    if resolved is None:
        return _missing(origin, file, file, root, candidate, recorded, BASIS_LEGACY)
    status = resolved.stat()
    size = int(status.st_size)
    current = _stat_block(size, int(status.st_mtime_ns))
    if size != part.source_bytes:
        state = CHANGED
        detail = (f"Size {part.source_bytes:,} → {size:,} bytes; modified {_when(status.st_mtime)} "
                  "UTC; recorded before source tracking.")
    else:
        state, detail = UNCHANGED, LEGACY_SIZE_ONLY
    age = now - status.st_mtime
    return Source(
        origin=origin, file=file, path=str(resolved), state=state, basis=BASIS_LEGACY,
        settling=age < settings.auto_ingest_settle_s, recorded=recorded, current=current,
        detail=detail, resolved=resolved, root=root, relpath=file, age_s=age,
    )


def inspect(
    record: registry.ExperimentRecord, settings: Settings, *,
    manifest: archive.Manifest | None = None, now: float | None = None,
) -> Source:
    """Compare one experiment's source file with what was recorded when it was read.

    Reads at most the file's status and, when the size is equal and the time
    moved, two mebibytes of it. ``manifest`` is only consulted for a row
    without a record.
    """
    now = time.time() if now is None else now
    if record.table_name == BASELINE_TABLE:
        return _seed(record, settings)
    if record.source_info:
        return _recorded(record, settings, now)
    return _legacy(record, settings, manifest, now)


# ---------------------------------------------------------------- actions --


def _settling_reason(source: Source, settings: Settings) -> str:
    age = max(source.age_s or 0.0, 0.0)
    return (f"The file was modified {age:.0f} s ago; Re-ingest is offered once it has been "
            f"unchanged for {settings.auto_ingest_settle_s:.0f} s.")


def _not_in(source: Source) -> str:
    name = source.file or "of this experiment"
    if source.root is not None:
        return f"Its source file {name} is not in {source.root}."
    return (f"Its source file {name} cannot be found: "
            f"{_folder_name(source.origin)} is not configured on the server.")


def reingest_reason(
    record: registry.ExperimentRecord, source: Source, settings: Settings, *,
    parts: int, job_active: bool, force: bool = False,
) -> str | None:
    """Why Re-ingest is not offered, the first reason that applies; None when it is.

    ``force`` lifts only the last reason, an unchanged or touched file: every
    other reason is a fact about the experiment that forcing does not alter.
    """
    if record.status == registry.STATUS_FAILED:
        return REASON_FAILED
    if record.status != registry.STATUS_READY:
        return REASON_INGESTING
    if job_active:
        return REASON_JOB_ACTIVE
    if source.state == UNTRACKED:
        if source.origin == ORIGIN_UPLOAD:
            return REASON_UPLOAD
        if source.origin == ORIGIN_SEED:
            return REASON_SEED
        return source.why or REASON_NO_RECORD
    if source.state == MISSING:
        return _not_in(source)
    if source.settling:
        return _settling_reason(source, settings)
    if parts > 1:
        return (f"It was assembled from {parts} files by append; replace it from Upload "
                "dataset instead.")
    if parts < 1:
        return REASON_NO_ARCHIVE
    if source.state != CHANGED and not force:
        return REASON_UNCHANGED
    return None


def retry_reason(
    record: registry.ExperimentRecord, source: Source, settings: Settings, *, job_active: bool,
) -> str | None:
    """Why Retry ingest is not offered; None when it is."""
    if record.status != registry.STATUS_FAILED:
        return REASON_NOT_FAILED
    if source.resolved is None:
        if source.state == MISSING or source.state == UNTRACKED and source.origin in (
                ORIGIN_DROP_FOLDER, ORIGIN_LOCAL, None):
            location = (f"is not in {source.root}" if source.root is not None
                        else "cannot be found on the server")
        else:
            location = "is not on the server"
        name = f"Its source file {source.file}" if source.file else "Its source file"
        return (f"{name} {location}; ingest it again from Upload dataset with Replace ticked.")
    if source.settling:
        return _settling_reason(source, settings)
    if job_active:
        return REASON_JOB_ACTIVE
    return None


def actions(
    record: registry.ExperimentRecord, source: Source, settings: Settings, *,
    parts: int, job_active: bool,
) -> dict[str, dict[str, Any]]:
    """``{reingest: {available, reason}, retry: {available, reason}}``."""
    again = reingest_reason(record, source, settings, parts=parts, job_active=job_active)
    retry = retry_reason(record, source, settings, job_active=job_active)
    return {
        ACTION_REINGEST: {"available": again is None, "reason": again},
        ACTION_RETRY: {"available": retry is None, "reason": retry},
    }
