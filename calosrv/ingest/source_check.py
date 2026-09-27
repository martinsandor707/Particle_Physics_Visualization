"""What the pre-flight check learned about a source file, whatever its format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceCheck:
    """The outcome of validating one source before anything is dropped or written.

    Carried from the check to the load, which needs to know which columns to
    convert, and into the ingest report, where a reader can see what the
    conversion did.
    """

    #: ``csv`` or ``parquet`` - decided from the file's content, not its name.
    format: str
    #: Data rows the source holds, when that is known without a full scan.
    rows: int | None = None
    #: Columns stored wider than the pinned schema (DOUBLE into REAL).
    narrowed: list[str] = field(default_factory=list)
    #: NaN values read as undefined (NULL), per column.
    nan_as_null: dict[str, int] = field(default_factory=dict)
    #: Sentences for the ingest report and the upload dialog.
    notices: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "rows": self.rows,
            "narrowed": list(self.narrowed),
            "nan_as_null": dict(self.nan_as_null),
            "notices": list(self.notices),
        }
