"""Ingest a file that is already on the server, by path.

Why this exists. DuckDB's lock is held on the *database file*, across
processes - not merely within one. So a second process cannot open the database
while the server has it, and an "offline" CLI run against a live server fails
outright with a lock error. The single-writer constraint is real, and the only
way to honour it is to have the process that already owns the database do the
work.

So a path-based ingest is a request to the server, which runs it on the same
background worker every upload uses. The multi-gigabyte file still never
traverses HTTP; only its path does.

Security. An endpoint that opens an arbitrary server-side path is a file
disclosure primitive if left unconstrained. Every requested path is resolved -
following symlinks and collapsing ``..`` - and then checked to be inside the one
configured root. Nothing outside that directory can be reached, whatever the
caller sends.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from ..errors import IngestError, NotFoundError, ValidationError

log = logging.getLogger(__name__)

#: Directories never worth listing as candidate datasets.
_SKIP_DIRECTORIES = frozenset(
    {
        "node_modules", "__pycache__", "site-packages", "dist-info",
        "venv", "env", "build", "dist", "data", "tmp", "staging",
    }
)


def resolve_local_path(settings: Settings, raw: str) -> Path:
    """Resolve ``raw`` inside the allowed ingest directory, or raise."""
    root = settings.local_ingest_dir
    if root is None:
        raise ValidationError(
            "Server-side ingestion by path is not enabled: no local ingest "
            "directory is configured (CALOSRV_LOCAL_INGEST_DIR).",
            field="path",
        )

    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = root / candidate

    # resolve() collapses '..' and follows symlinks, so the containment check
    # below cannot be defeated by either.
    resolved = candidate.resolve()
    root_resolved = root.resolve()

    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValidationError(
            f"Path must be inside {root_resolved}; {resolved} is not.",
            field="path",
            allowed_root=str(root_resolved),
        )

    if not resolved.exists():
        raise NotFoundError(f"No such file on the server: {resolved}")
    if not resolved.is_file():
        raise ValidationError(f"{resolved} is not a regular file.", field="path")
    if resolved.suffix.lower() not in (".csv", ".txt"):
        raise IngestError(
            f"Unsupported file type {resolved.suffix or '(none)'!r}; "
            "expected a .csv file."
        )
    return resolved


def list_local_files(settings: Settings, limit: int = 200) -> list[dict]:
    """CSV files available for server-side ingestion, newest first."""
    root = settings.local_ingest_dir
    if root is None:
        return []

    entries = []
    try:
        for path in sorted(root.rglob("*.csv")):
            relative = path.relative_to(root)
            # The ingest root is often a whole repository checkout, which
            # contains thousands of irrelevant CSVs inside virtual environments
            # and test fixtures. Listing those buries the datasets a physicist
            # is actually looking for.
            if any(
                part.startswith(".") or part in _SKIP_DIRECTORIES
                for part in relative.parts[:-1]
            ):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append(
                {
                    "path": str(path),
                    "relative": str(path.relative_to(root)),
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )
            if len(entries) >= limit:
                break
    except OSError as exc:  # pragma: no cover - unreadable mount
        log.warning("Could not list %s: %s", root, exc)

    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries
