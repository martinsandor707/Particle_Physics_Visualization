"""The immutable Parquet archive of every ingested CSV.

Ingest writes each validated, typed input file once, as a zstd-compressed
Parquet part under ``<data_dir>/archive/<experiment>/``. Everything derived -
the projection, per-event and preview tables - is built from those parts, and
the database itself never holds the 99-column raw rows.

Why a separate archive rather than a raw table inside the database:

* **Other processes can read it.** DuckDB lets a database file be held by one
  read-write process *or* several read-only ones, so while the server runs no
  notebook can open the database at all. Parquet parts are plain immutable
  files: DuckDB, Polars, pandas or pyarrow can read them beside the server.
* **Rebuilding a derived table reads only the columns it needs.** Adding a
  plane to the projection table re-reads a few Parquet columns instead of
  re-parsing 24 GB of CSV text.
* **The raw rows stay out of the buffer pool** the interactive queries share.

Each part is written with a bounded row group (100 000 rows, zstd level 3):
the Parquet writer buffers a row group per thread, so the bound caps the
writer's memory at roughly threads x 40 MB of 99-column rows, and the small
groups keep min/max statistics fine-grained for ``event_number`` pruning.

A part is written to ``*.parquet.tmp`` and renamed only once complete, and a
``manifest.json`` lists the committed parts - readers take the manifest, never
a directory glob, so a stray or half-written file can never enter a scan.

A re-ingest swaps the whole archive of a served experiment, so it cannot
overwrite ``manifest.json`` before the database commits. It writes
``manifest.json.next`` first, commits the transaction, and only then renames
the file over the manifest; :func:`reconcile` finishes or abandons whatever a
crash left between those steps, deciding by the ``job_id`` the registry row
and the ``.next`` file both carry.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..fsutil import TMP_SUFFIX, atomic_write_text
from . import naming

log = logging.getLogger(__name__)

ARCHIVE_SUBDIR = "archive"
PART_PATTERN = "part-{:05d}.parquet"
MANIFEST = "manifest.json"
#: The manifest a re-ingest has written but the database has not yet committed.
NEXT_MANIFEST = "manifest.json.next"
_PART_FILE = re.compile(r"^part-(\d+)\.parquet$")

#: Rows per Parquet row group, and the zstd level. See the module docstring.
ROW_GROUP_SIZE = 100_000
COMPRESSION_LEVEL = 3


@dataclass
class ArchivePart:
    file: str
    rows: int
    bytes: int
    source_name: str
    source_bytes: int
    event_offset: int
    event_min: int | None
    event_max: int | None
    written_at: str
    duckdb_version: str
    #: ``csv`` or ``parquet``. Defaulted, so manifests written before Parquet
    #: sources existed still load: every one of those parts came from a CSV.
    source_format: str = "csv"

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Manifest:
    schema_name: str
    schema_version: int
    parts: list[ArchivePart] = field(default_factory=list)
    #: The ingest job whose data this manifest lists. Set only by a re-ingest,
    #: so that a crash between its commit and its rename can be told apart from
    #: one before it; every other manifest omits the key and reads back as None.
    job_id: str | None = None

    @property
    def rows(self) -> int:
        return sum(p.rows for p in self.parts)

    @property
    def bytes(self) -> int:
        return sum(p.bytes for p in self.parts)

    def event_range(self) -> tuple[int, int] | None:
        lows = [p.event_min for p in self.parts if p.event_min is not None]
        highs = [p.event_max for p in self.parts if p.event_max is not None]
        if not lows or not highs:
            return None
        return min(lows), max(highs)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "parts": [p.as_dict() for p in self.parts],
        }
        # Only when set, so a manifest written before re-ingest existed
        # round-trips byte for byte.
        if self.job_id is not None:
            data["job_id"] = self.job_id
        return data


def relative_dir(name: str) -> str:
    """The archive directory relative to the data directory, as the registry stores it.

    Relative, so the same registry row is right inside the container
    (``/app/data``) and on the host (``./data``).
    """
    return f"{ARCHIVE_SUBDIR}/{naming.validate_experiment_name(name)}"


def archive_path(settings: Settings, name: str) -> Path:
    """The experiment's archive directory, guaranteed to sit inside ``archive_dir``."""
    root = settings.archive_dir.resolve()
    path = (root / naming.validate_experiment_name(name)).resolve()
    if path.parent != root:  # pragma: no cover - the name pattern forbids it
        raise ValueError(f"archive path {path} escapes {root}")
    return path


def _manifest_path(settings: Settings, name: str) -> Path:
    return archive_path(settings, name) / MANIFEST


def _next_path(settings: Settings, name: str) -> Path:
    return archive_path(settings, name) / NEXT_MANIFEST


def _parse_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    job_id = data.get("job_id")
    return Manifest(
        schema_name=data["schema_name"],
        schema_version=int(data["schema_version"]),
        parts=[ArchivePart(**p) for p in data.get("parts", [])],
        job_id=str(job_id) if job_id is not None else None,
    )


def read_manifest(settings: Settings, name: str) -> Manifest | None:
    path = _manifest_path(settings, name)
    if not path.is_file():
        return None
    return _parse_manifest(path)


def write_manifest(settings: Settings, name: str, manifest: Manifest) -> None:
    """Replace the manifest atomically, and durably: it is what readers trust."""
    atomic_write_text(
        _manifest_path(settings, name),
        json.dumps(manifest.as_dict(), indent=1, sort_keys=True),
    )


def write_next(settings: Settings, name: str, manifest: Manifest) -> None:
    """Write the manifest a re-ingest is about to commit, beside the committed one.

    Atomic and durable like :func:`write_manifest`, but under another name, so
    readers still take the old parts until :func:`commit_next`.
    """
    atomic_write_text(
        _next_path(settings, name),
        json.dumps(manifest.as_dict(), indent=1, sort_keys=True),
    )


def commit_next(settings: Settings, name: str) -> None:
    """Make the written ``manifest.json.next`` the manifest: one atomic rename."""
    os.replace(_next_path(settings, name), _manifest_path(settings, name))


def discard_next(settings: Settings, name: str) -> bool:
    """Remove an uncommitted ``manifest.json.next``. Returns whether there was one."""
    path = _next_path(settings, name)
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def part_paths(settings: Settings, name: str, manifest: "Manifest | None" = None) -> list[Path]:
    """The parts of ``manifest`` (default: the committed one) - never from a glob.

    Passing a manifest lets an append derive and verify over its provisional
    part before the part is committed.
    """
    if manifest is None:
        manifest = read_manifest(settings, name)
    if manifest is None:
        return []
    root = archive_path(settings, name)
    return [root / part.file for part in manifest.parts]


def part_index(file: str) -> int | None:
    """The number in a part's file name (``part-00003.parquet`` -> 3), or None."""
    found = _PART_FILE.match(file)
    return int(found.group(1)) if found else None


def next_part_path(settings: Settings, name: str) -> Path:
    """The path of the next part: one past the largest index in the committed manifest.

    Not the part count. A re-ingest leaves a manifest whose one part is
    ``part-00001``, so counting would hand the next one ``part-00001`` again,
    the file the committed manifest still lists.
    """
    manifest = read_manifest(settings, name)
    indices = [i for i in (part_index(p.file) for p in manifest.parts) if i is not None] \
        if manifest else []
    if indices:
        index = max(indices) + 1
    else:
        index = len(manifest.parts) if manifest else 0
    return archive_path(settings, name) / PART_PATTERN.format(index)


def _literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def relation_sql(paths: list[Path]) -> str:
    """A ``read_parquet`` over explicit part paths - the one way the archive is read."""
    if not paths:
        raise ValueError("the archive has no committed parts")
    listed = ", ".join(_literal(p) for p in paths)
    return f"read_parquet([{listed}], hive_partitioning = false, union_by_name = false)"


def relation(settings: Settings, name: str) -> str:
    return relation_sql(part_paths(settings, name))


def copy_to_part_sql(select_sql: str, destination: Path) -> str:
    """``COPY (select) TO destination`` with the archive's pinned writer options."""
    return (
        f"COPY ({select_sql}) TO {_literal(destination)} "
        f"(FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL {COMPRESSION_LEVEL}, "
        f"ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
    )


def new_part(
    *, file: str, rows: int, size: int, source_name: str, source_bytes: int,
    event_offset: int, event_range: tuple[int, int] | None, duckdb_version: str,
    source_format: str = "csv",
) -> ArchivePart:
    return ArchivePart(
        file=file, rows=int(rows), bytes=int(size),
        source_name=source_name, source_bytes=int(source_bytes),
        event_offset=int(event_offset),
        event_min=event_range[0] if event_range else None,
        event_max=event_range[1] if event_range else None,
        written_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        duckdb_version=duckdb_version,
        source_format=source_format,
    )


def remove(settings: Settings, name: str) -> bool:
    """Delete an experiment's archive directory. Returns whether one existed."""
    path = archive_path(settings, name)
    if not path.exists():
        return False
    shutil.rmtree(path)
    log.info("Removed archive %s", path)
    return True


def sweep_tmp(settings: Settings) -> int:
    """Delete half-written parts left by an interrupted ingest."""
    removed = 0
    root = settings.archive_dir
    if not root.is_dir():
        return 0
    for path in root.glob(f"*/*{TMP_SUFFIX}"):
        try:
            path.unlink()
            removed += 1
        except OSError:  # pragma: no cover
            log.warning("Could not remove stale archive file %s", path)
    if removed:
        log.warning("Removed %d incomplete archive file(s) from an interrupted ingest", removed)
    return removed


def reconcile(settings: Settings, records: list) -> list[str]:
    """Finish or abandon what an interrupted re-ingest left in the archives; run at boot.

    A re-ingest writes the new part, then ``manifest.json.next``, then commits
    the database, then renames the manifest into place and deletes the old
    parts. A crash between any two of those steps leaves one of three states,
    told apart by the ``job_id`` that the ``.next`` file and the registry row
    both carry:

    * the ``.next`` names a job the registry does not (the transaction never
      committed): the ``.next`` is removed;
    * it names the registry's job (committed, rename not done): it is renamed
      over the manifest, rolling the archive forward to the data the tables hold;
    * the manifest is already the new one: the old part files are unlisted.

    Afterwards every ``part-*.parquet`` the committed manifest does not list is
    removed, which also clears the new part of an abandoned re-ingest and the
    provisional part of an append that crashed. A folder whose manifest cannot
    be read is never touched. Returns what was done, one line each, all logged
    at WARNING.
    """
    root = settings.archive_dir
    if not root.is_dir():
        return []
    by_name = {record.table_name: record for record in records}
    actions: list[str] = []

    def note(message: str, *args: Any) -> None:
        log.warning(message, *args)
        actions.append(message % args)

    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        name = directory.name
        pending = directory / NEXT_MANIFEST
        if pending.exists():
            record = by_name.get(name)
            try:
                wanted = _parse_manifest(pending).job_id
            except (OSError, ValueError, TypeError, KeyError):
                wanted = None
            current = (record.source_info or {}).get("job_id") if record is not None else None
            if wanted is not None and wanted == current:
                os.replace(pending, directory / MANIFEST)
                note("Archive %s: finished the re-ingest of job %s that the database had "
                     "committed (manifest.json.next became manifest.json)", name, wanted)
            else:
                pending.unlink(missing_ok=True)
                note("Archive %s: removed manifest.json.next of an uncommitted re-ingest", name)
        manifest_file = directory / MANIFEST
        if not manifest_file.is_file():
            continue
        try:
            listed = {part.file for part in _parse_manifest(manifest_file).parts}
        except (OSError, ValueError, TypeError, KeyError):
            log.warning("Archive %s: manifest.json cannot be read; its folder is left as it is", name)
            continue
        for stray in sorted(directory.glob("part-*.parquet")):
            if stray.name not in listed:
                try:
                    stray.unlink()
                except OSError:  # pragma: no cover
                    log.warning("Could not remove stray archive part %s", stray)
                    continue
                note("Archive %s: removed %s, which the manifest does not list", name, stray.name)
    return actions
