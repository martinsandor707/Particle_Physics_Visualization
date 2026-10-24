"""What one ingest produced, and the stopwatch every stage reports through.

Kept apart from ``pipeline.py`` so the per-kind recipes (``recipes.py``) and
the pipeline that dispatches to them share these without importing each
other.
"""

from __future__ import annotations

import logging
import resource
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb

from ..db import registry
from . import verify as verify_mod

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Everything one ingest produced, for the job record and the CLI."""

    record: registry.ExperimentRecord
    n_hits: int = 0
    n_events: int = 0
    sanitation: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)
    verification: verify_mod.VerificationResult | None = None
    timings: list[dict[str, Any]] = field(default_factory=list)
    #: What reading the source did that a reader should know: a narrowed
    #: column, NaN read as undefined. Informational, never a failure.
    notices: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.verification and self.verification.ok)

    @property
    def warnings(self) -> list[str]:
        failures = list(self.verification.warnings) if self.verification else []
        return [*failures, *self.notices]

    def as_job_result(self) -> dict[str, Any]:
        lattice = self.record.lattice
        schema = self.record.schema
        return {
            "kind": self.record.kind,
            "schema": {"name": schema.name, "version": schema.version,
                       "n_columns": schema.n_columns} if schema else None,
            "n_hits": self.n_hits,
            "n_events": self.n_events,
            "n_events_no_d": self.record.n_events_no_d,
            "sanitation": self.sanitation,
            "calibration": self.calibration,
            "lattice": {
                "nx": lattice.x.n, "ny": lattice.y.n, "nz": lattice.z.n,
                "x_uniform": lattice.x.is_uniform,
                "y_uniform": lattice.y.is_uniform,
                "z_uniform": lattice.z.is_uniform,
            } if lattice else None,
            "archive": {
                "dir": self.record.archive_dir,
                "parts": self.record.archive_parts,
                "rows": self.record.archive_rows,
                "bytes": self.record.archive_bytes,
            },
            "checks": self.verification.checks if self.verification else {},
            "timings": self.timings,
            "source": self.record.ingest_report.get("source"),
        }


class _Stopwatch:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self._last = time.perf_counter()
        self.stages: list[dict[str, Any]] = []

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        try:
            duck_mem = self._con.execute(
                "SELECT coalesce(sum(memory_usage_bytes), 0) FROM duckdb_memory()"
            ).fetchone()[0]
            spill = self._con.execute(
                "SELECT coalesce(sum(size), 0) FROM duckdb_temporary_files()"
            ).fetchone()[0]
        except duckdb.Error:  # pragma: no cover - diagnostics only
            duck_mem, spill = None, None
        entry = {
            "stage": stage,
            "seconds": round(now - self._last, 3),
            # ru_maxrss is in KiB on Linux: the peak so far, not this stage's.
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "duckdb_memory_mb": round(int(duck_mem) / 1e6, 1) if duck_mem is not None else None,
            "spill_mb": round(int(spill) / 1e6, 1) if spill is not None else None,
        }
        self.stages.append(entry)
        log.info("Ingest stage %s: %.1f s, peak RSS %.0f MB, DuckDB %s MB, spill %s MB",
                 stage, entry["seconds"], entry["peak_rss_mb"],
                 entry["duckdb_memory_mb"], entry["spill_mb"])
        self._last = now
