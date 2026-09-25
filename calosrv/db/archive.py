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
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from . import naming

log = logging.getLogger(__name__)

ARCHIVE_SUBDIR = "archive"
PART_PATTERN = "part-{:05d}.parquet"
TMP_SUFFIX = ".tmp"
MANIFEST = "manifest.json"

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

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Manifest:
    schema_name: str
    schema_version: int
    parts: list[ArchivePart] = field(default_factory=list)

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
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "parts": [p.as_dict() for p in self.parts],
        }


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


def read_manifest(settings: Settings, name: str) -> Manifest | None:
    path = _manifest_path(settings, name)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(
        schema_name=data["schema_name"],
        schema_version=int(data["schema_version"]),
        parts=[ArchivePart(**p) for p in data.get("parts", [])],
    )


def write_manifest(settings: Settings, name: str, manifest: Manifest) -> None:
    """Replace the manifest atomically."""
    path = _manifest_path(settings, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    tmp.write_text(json.dumps(manifest.as_dict(), indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def part_paths(settings: Settings, name: str) -> list[Path]:
    """The committed parts, from the manifest - never from a glob."""
    manifest = read_manifest(settings, name)
    if manifest is None:
        return []
    root = archive_path(settings, name)
    return [root / part.file for part in manifest.parts]


def next_part_path(settings: Settings, name: str) -> Path:
    manifest = read_manifest(settings, name)
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
) -> ArchivePart:
    return ArchivePart(
        file=file, rows=int(rows), bytes=int(size),
        source_name=source_name, source_bytes=int(source_bytes),
        event_offset=int(event_offset),
        event_min=event_range[0] if event_range else None,
        event_max=event_range[1] if event_range else None,
        written_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        duckdb_version=duckdb_version,
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
