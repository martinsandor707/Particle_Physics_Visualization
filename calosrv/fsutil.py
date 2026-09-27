"""Crash-safe file replacement.

A settings file or an archive manifest that is half written when the container
is killed is worse than a stale one: the stale one still parses. So the new
content is written to a sibling temporary file, flushed to the disk, and then
renamed over the old one - a rename within one directory is atomic on POSIX, so
a reader sees either the old file or the new one, never a torn mix.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Suffix of the temporary sibling. ``archive.sweep_tmp`` removes leftovers.
TMP_SUFFIX = ".tmp"


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Replace ``path`` with ``text`` so that no reader ever sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    with tmp.open("w", encoding=encoding) as handle:
        handle.write(text)
        handle.flush()
        # Without this the rename can reach the disk before the data does, and
        # a power cut leaves an empty file under the final name.
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
    except OSError:  # pragma: no cover - platforms that cannot open a directory
        return
    try:
        os.fsync(directory)  # make the rename itself durable
    except OSError:  # pragma: no cover - some filesystems refuse directory fsync
        pass
    finally:
        os.close(directory)
