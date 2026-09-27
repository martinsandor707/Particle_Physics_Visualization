"""What already exists under an experiment name, or from a source file.

Asked before anything is written. A ``create_new`` onto an existing name is
refused unless it is forced, and the boot-time scanner skips a file whose
experiment exists: both need the same answer, and "exists" has to mean more
than a registry row. A crash can leave tables without one, and an archive
directory can outlive both; replacing any of them silently is the clobbering
this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from ..config import Settings
from . import archive, bootstrap, naming, registry


@dataclass
class Presence:
    """Everything that carries one experiment's name."""

    name: str
    #: The registry row's status, or None when there is no row.
    status: str | None = None
    tables: list[str] = field(default_factory=list)
    archive: bool = False

    @property
    def exists(self) -> bool:
        return self.status is not None or bool(self.tables) or self.archive

    def describe(self) -> str:
        """A phrase for a message: what exactly is there."""
        if self.status is not None:
            return self.status
        parts = []
        if self.tables:
            parts.append(f"tables {', '.join(self.tables)} without a registry row")
        if self.archive:
            parts.append("an archive without a registry row")
        return " and ".join(parts) or "nothing"


def presence(con: duckdb.DuckDBPyConnection, settings: Settings, name: str) -> Presence:
    """Whether a registry row, any physical table or an archive carries ``name``."""
    name = naming.validate_experiment_name(name)
    registry.ensure_registry(con)
    record = registry.get_experiment(con, name)
    physical = bootstrap.physical_tables(con)
    return Presence(
        name=name,
        status=record.status if record is not None else None,
        tables=[t for t in naming.all_tables(name) if t in physical],
        archive=archive.archive_path(settings, name).exists(),
    )


def archived_as(settings: Settings, source_name: str, source_bytes: int) -> str | None:
    """The experiment whose archive already holds this source file, if any.

    A file is recognised by its name and its size in bytes, which is what every
    manifest records. That is enough to stop a dataset dropped under its
    original name - ``hits_all_models.csv`` - being ingested a second time
    beside the experiment it already is.
    """
    root = settings.archive_dir
    if not root.is_dir():
        return None
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            manifest = archive.read_manifest(settings, directory.name)
        except (OSError, ValueError, TypeError, KeyError):
            continue  # a directory that is not an experiment's archive
        if manifest is None:
            continue
        for part in manifest.parts:
            if part.source_name == source_name and part.source_bytes == source_bytes:
                return directory.name
    return None
