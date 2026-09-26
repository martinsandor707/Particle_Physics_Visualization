"""Refuse to put the database, its spill files or the archive in RAM.

DuckDB spills to ``temp_directory`` when a query outgrows ``memory_limit``.
That only helps if the directory is on disk: on a tmpfs the "spilled" pages are
RAM too, so spilling frees nothing, the spilled bytes are not counted against
``memory_limit``, and a large ingest can take the whole machine down. This is
not hypothetical - an ad-hoc analysis session on this project spilled about
9 GB into a tmpfs ``/tmp``, and the development workstation's swap is zram
(compressed RAM) as well.

So at startup every storage role is resolved to the filesystem it lives on,
through ``/proc/self/mountinfo``, and a RAM-backed one is refused with a message
saying which directory and why. Tests that run on 1000-row fixtures may opt out
explicitly (``CALOSRV_ALLOW_RAM_STORAGE=1``); the opt-out is logged on every
boot and never set by the container.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..errors import StorageConfigError

log = logging.getLogger(__name__)

#: Filesystems whose pages are RAM.
RAM_FILESYSTEMS = frozenset({"tmpfs", "ramfs", "devtmpfs", "hugetlbfs"})

MOUNTINFO = Path("/proc/self/mountinfo")


@dataclass(frozen=True)
class Mount:
    fstype: str
    source: str
    mount_point: str

    @property
    def ram_backed(self) -> bool:
        return self.fstype in RAM_FILESYSTEMS or self.source.startswith("/dev/zram")


def _unescape(field: str) -> str:
    # mountinfo octal-escapes spaces, tabs, newlines and backslashes.
    return (field.replace("\\040", " ").replace("\\011", "\t")
            .replace("\\012", "\n").replace("\\134", "\\"))


def _canonical(path: Path) -> Path:
    """Symlinks resolved through the longest existing ancestor; the tail kept.

    A directory the server is about to create does not exist yet, but it will
    live on whatever filesystem its nearest existing ancestor is mounted from -
    so that ancestor is resolved and the not-yet-created tail re-appended.
    """
    path = path.absolute()
    tail: list[str] = []
    current = path
    while not current.exists() and current != current.parent:
        tail.append(current.name)
        current = current.parent
    resolved = current.resolve()
    for part in reversed(tail):
        resolved = resolved / part
    return resolved


def backing_fs(path: Path, mountinfo_text: str | None = None) -> Mount | None:
    """The mount a path lives on, by longest mount-point prefix; None if unknown."""
    if mountinfo_text is None:
        try:
            mountinfo_text = MOUNTINFO.read_text(encoding="utf-8")
        except OSError:
            return None
    target = str(_canonical(Path(path)))
    best: Mount | None = None
    best_len = -1
    for line in mountinfo_text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or len(right_fields) < 2:
            continue
        mount_point = _unescape(left_fields[4])
        prefix = mount_point.rstrip("/") + "/"
        if target == mount_point or target.startswith(prefix) or mount_point == "/":
            # ``>=``: mountinfo lists a mount before anything mounted over it, so
            # of two entries at one mount point the later one is visible.
            if len(mount_point) >= best_len:
                best_len = len(mount_point)
                best = Mount(right_fields[0], right_fields[1], mount_point)
    return best


def assert_disk_backed(
    roles: dict[str, Path], allow: bool = False, mountinfo_text: str | None = None
) -> dict[str, Mount | None]:
    """Raise :class:`StorageConfigError` if any role lives on a RAM filesystem."""
    found: dict[str, Mount | None] = {}
    offending = []
    for role, path in roles.items():
        mount = backing_fs(path, mountinfo_text)
        found[role] = mount
        if mount is None:
            log.info("Storage %s at %s: filesystem unknown (no mountinfo)", role, path)
            continue
        if mount.ram_backed:
            offending.append(f"{role} at {path} is on {mount.fstype} ({mount.source}, "
                             f"mounted at {mount.mount_point})")
    if offending:
        message = (
            "RAM-backed storage refused: " + "; ".join(offending) + ". DuckDB spill "
            "files, the database and the Parquet archive must live on disk, or a "
            "large query spills into memory it was meant to relieve. Point "
            "CALOSRV_DATA_DIR (or CALOSRV_DB_PATH) at a disk-backed directory."
        )
        if allow:
            log.warning("%s Continuing because CALOSRV_ALLOW_RAM_STORAGE=1.", message)
        else:
            raise StorageConfigError(message)
    return found
