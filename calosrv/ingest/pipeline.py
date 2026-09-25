"""The one ingest pipeline: CSV -> Parquet archive -> derived tables -> checks.

Before this module the same eleven steps were written out three times - in the
background job, in the command-line tool and in the test fixture - and kept in
step by hand. They now all call :func:`run_ingest`; :func:`rebuild` re-derives
every table from an existing archive without reading any CSV.

Every stage records its wall time, the process's peak RSS so far, DuckDB's
buffer-managed memory and its spill-file size, so the report shows which stage
set the peak - the measurement the ingest memory budget is judged on.
"""

from __future__ import annotations

import logging
import resource
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from ..config import Settings
from ..db import archive, registry
from ..db.ddl import SCHEMA_NAME, SCHEMA_VERSION
from ..errors import IngestError
from . import derive_events, derive_proj, lattice_fit, load, stream, verify as verify_mod

log = logging.getLogger(__name__)

#: Ordered pipeline stages, reported so the interface can show real progress
#: rather than a spinner. The weights are rough shares of total wall time on
#: the production file and only turn a stage into a percentage.
STAGES: tuple[tuple[str, str, float], ...] = (
    ("archive", "Writing the Parquet archive", 0.50),
    ("lattice", "Measuring the detector lattice", 0.03),
    ("projection", "Building the projection table", 0.20),
    ("events", "Building per-event statistics", 0.15),
    ("sample", "Building the preview sample", 0.03),
    ("verify", "Verifying the ingested data", 0.09),
)


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

    @property
    def ok(self) -> bool:
        return bool(self.verification and self.verification.ok)

    @property
    def warnings(self) -> list[str]:
        return list(self.verification.warnings) if self.verification else []

    def as_job_result(self) -> dict[str, Any]:
        lattice = self.record.lattice
        return {
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


def _derive(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    record: registry.ExperimentRecord,
    source_csv: Path | None,
    manifest: archive.Manifest,
    build_sample: bool,
    watch: _Stopwatch,
    progress: Callable[[str], None],
    part_rows: int | None = None,
) -> IngestResult:
    """Everything after the archive: lattice, derived tables, verification."""
    name = record.table_name
    relation = archive.relation_sql(archive.part_paths(settings, name))

    progress("lattice")
    lattice = lattice_fit.measure_lattice(con, relation)
    pitch = lattice_fit.layer_pitch(lattice.z.coords)
    # Persist the lattice before the derived tables are verified: the
    # lattice-bounds check reads it, and would otherwise skip itself silently.
    record.lattice = lattice
    registry.upsert(con, record)
    watch.mark("lattice")

    progress("projection")
    sanitation = derive_proj.build(con, name, relation, pitch)
    watch.mark("projection")

    progress("events")
    n_events = derive_events.build(con, name, relation)
    calibration = derive_events.calibration(con, name)
    bounds = lattice_fit.measure_bounds(con, name)
    frame_bounds = lattice_fit.measure_frame_bounds(con, name, pitch)
    cell_e_max, cell_e_p999 = derive_proj.measure_color_anchors(con, name, lattice.slab_iz)
    watch.mark("events")

    sample_rows = 0
    if build_sample:
        progress("sample")
        sample_rows = derive_proj.build_sample(con, name, settings.sample_percent)
        watch.mark("sample")

    progress("verify")
    verification = verify_mod.verify(
        con, name, source_csv, relation, manifest.rows, pitch, part_rows=part_rows,
        lattice_n=(lattice.x.n, lattice.y.n, lattice.z.n),
        depth_mm=float(lattice.z.hi - lattice.z.lo),
    )
    watch.mark("verify")

    counts = con.execute(
        "SELECT coalesce(sum(n_cells), 0), coalesce(sum(n_split_cells), 0), "
        f"coalesce(sum(n_ab_rows), 0) FROM \"event_{name}\""
    ).fetchone()
    record.n_hits = sanitation.kept_rows
    record.n_events = n_events
    record.n_events_no_d = bounds["n_events_no_d"]
    record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
    record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
    record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
    record.overlaps = bounds["overlaps"]
    record.cell_e_max, record.cell_e_p999 = cell_e_max, cell_e_p999
    record.has_sample = sample_rows > 0
    record.schema_name, record.schema_version = SCHEMA_NAME, SCHEMA_VERSION
    record.archive_dir = archive.relative_dir(name)
    record.archive_parts = len(manifest.parts)
    record.archive_rows = manifest.rows
    record.archive_bytes = manifest.bytes
    record.n_cells, record.n_split_cells, record.n_ab_rows = (int(v) for v in counts)
    record.frame_bounds = frame_bounds
    calibration_report = {code: {"c_a": c_a, "c_b": c_b} for code, (c_a, c_b) in calibration.items()}
    record.ingest_report = {
        "sanitation": sanitation.as_dict(),
        "calibration": calibration_report,
        "timings": watch.stages,
        "verification": verification.as_dict(),
        "layer_pitch_mm": pitch,
    }
    record.status = registry.STATUS_READY if verification.ok else registry.STATUS_FAILED
    record.error = None if verification.ok else "; ".join(verification.warnings)
    registry.upsert(con, record)

    return IngestResult(
        record=record, n_hits=record.n_hits, n_events=n_events,
        sanitation=sanitation.as_dict(), calibration=calibration_report,
        verification=verification, timings=watch.stages,
    )


def run_ingest(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    source: Path,
    *,
    source_name: str | None = None,
    mode: str = load.MODE_CREATE_NEW,
    event_offset: int = 0,
    display_name: str = "",
    build_sample: bool = True,
    check_space: bool = True,
    created_at=None,
    progress: Callable[[str], None] | None = None,
) -> IngestResult:
    """Ingest one CSV into experiment ``name``. Caller holds the write lock."""
    progress = progress or (lambda _stage: None)
    watch = _Stopwatch(con)
    source_name = source_name or source.name
    if check_space:
        stream.check_free_space(
            settings.data_dir, source.stat().st_size, settings.local_headroom_factor
        )

    registry.ensure_registry(con)
    existing = registry.get_experiment(con, name)
    record = existing or registry.ExperimentRecord(table_name=name)
    record.display_name = display_name or record.display_name or name
    record.status = registry.STATUS_INGESTING
    record.error = None
    if source_name not in record.source_files:
        record.source_files = [*record.source_files, source_name]
    if record.created_at is None and created_at is not None:
        record.created_at = created_at
    record.schema_name, record.schema_version = SCHEMA_NAME, SCHEMA_VERSION
    registry.upsert(con, record)

    progress("archive")
    loaded = load.load_csv(
        con, settings, name, source, mode=mode, event_offset=event_offset,
        source_name=source_name,
    )
    watch.mark("archive")
    return _derive(con, settings, record, source, loaded.manifest, build_sample, watch, progress,
                   part_rows=loaded.rows)


def rebuild(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    name: str,
    *,
    build_sample: bool = True,
    progress: Callable[[str], None] | None = None,
) -> IngestResult:
    """Re-derive every table of ``name`` from its archive, reading no CSV."""
    progress = progress or (lambda _stage: None)
    manifest = archive.read_manifest(settings, name)
    if manifest is None or not manifest.parts:
        raise IngestError(f"Experiment {name!r} has no archive to rebuild from.")
    record = registry.get_experiment(con, name) or registry.ExperimentRecord(table_name=name)
    record.status = registry.STATUS_INGESTING
    record.error = None
    registry.upsert(con, record)
    watch = _Stopwatch(con)
    return _derive(con, settings, record, None, manifest, build_sample, watch, progress)
