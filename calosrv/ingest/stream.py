"""Stream an uploaded file to disk without buffering it in memory.

A multi-gigabyte upload must never be materialised as a ``bytes`` object. The
FastAPI route hands this module an async stream and it writes through to the
staging directory in fixed-size chunks, so peak memory is one chunk regardless
of whether the file is 300 KB or 8 GB.

Free space is checked *before* the write begins. Peak disk usage during an
ingest is the staging CSV plus the hit table plus the projection table plus the
write-ahead log, so the default headroom factor is three times the incoming
size. Discovering the shortfall after spending twenty minutes on the transfer
would be a poor trade.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from ..errors import IngestError, InsufficientStorageError

log = logging.getLogger(__name__)

#: 8 MiB. Large enough that syscall overhead is negligible on a multi-gigabyte
#: transfer, small enough that a few concurrent uploads cannot exhaust memory.
CHUNK_BYTES = 8 * 1024 * 1024


@dataclass
class StagedFile:
    path: Path
    original_name: str
    size_bytes: int

    def unlink(self) -> None:
        """Delete the staged file. Safe to call more than once."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - best-effort cleanup
            log.warning("Could not remove staged file %s: %s", self.path, exc)


def check_free_space(
    directory: Path, needed_bytes: int, factor: float = 3.0
) -> None:
    """Raise unless the filesystem can hold ``needed_bytes * factor``."""
    required = int(needed_bytes * factor)
    free = shutil.disk_usage(directory).free
    if free < required:
        raise InsufficientStorageError(
            f"Ingesting this file needs about {required / 1e9:.1f} GB of free "
            f"space (the CSV itself plus the derived tables and write-ahead "
            f"log), but only {free / 1e9:.1f} GB is available on the data "
            "volume.",
            required_bytes=required,
            free_bytes=free,
        )


def staged_path(staging_dir: Path, original_name: str) -> Path:
    """A collision-free path in the staging directory.

    The client-supplied filename is never used as a path component - only its
    suffix, and only after validation - so a name like ``../../etc/passwd``
    cannot escape the staging directory.
    """
    suffix = Path(original_name).suffix.lower()
    if suffix not in (".csv", ".txt", ""):
        raise IngestError(
            f"Unsupported file type {suffix or '(none)'!r}; expected a .csv file."
        )
    return staging_dir / f"upload_{uuid.uuid4().hex}.csv"


async def stream_to_disk(
    chunks: AsyncIterator[bytes],
    destination: Path,
    original_name: str,
    max_bytes: int | None = None,
) -> StagedFile:
    """Write an async byte stream to ``destination`` in chunks."""
    written = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as handle:
            async for chunk in chunks:
                if not chunk:
                    continue
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise IngestError(
                        f"Upload exceeds the {max_bytes / 1e9:.1f} GB limit."
                    )
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if written == 0:
        destination.unlink(missing_ok=True)
        raise IngestError("The uploaded file is empty.")

    log.info(
        "Staged %s as %s (%.2f GB)", original_name, destination.name, written / 1e9
    )
    return StagedFile(path=destination, original_name=original_name, size_bytes=written)


async def iter_upload(upload, chunk_bytes: int = CHUNK_BYTES) -> AsyncIterator[bytes]:
    """Adapt a Starlette ``UploadFile`` into a plain chunk iterator."""
    while chunk := await upload.read(chunk_bytes):
        yield chunk
