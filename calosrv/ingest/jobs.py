"""Background ingest jobs and their status, for polling.

Ingesting the 7.4 GB production file takes minutes. That cannot happen inside an
HTTP request: the client would time out, and - more importantly - DuckDB permits
exactly one writer, so a request thread holding the write lock for minutes would
stall every other write in the process.

So an upload returns immediately with a job identifier, and the work runs on a
single-slot worker thread. One slot, not a pool: two concurrent ingests would
serialise on the write lock anyway, and queueing them explicitly gives an honest
"waiting" status instead of an opaque stall.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..db.connection import Database
from ..db import naming, registry
from ..errors import ApiError
from . import derive_events, derive_proj, lattice_fit, load, verify as verify_mod
from .stream import StagedFile

log = logging.getLogger(__name__)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

#: Ordered pipeline stages, reported so the interface can show real progress
#: rather than a spinner. The weights are rough shares of total wall time on the
#: 7.4 GB file and are used only to turn a stage into a percentage.
STAGES: tuple[tuple[str, str, float], ...] = (
    ("load", "Loading CSV into the hit table", 0.45),
    ("lattice", "Measuring the detector lattice", 0.08),
    ("projection", "Building the projection table", 0.22),
    ("events", "Building per-event statistics", 0.15),
    ("sample", "Building the preview sample", 0.05),
    ("verify", "Verifying the ingested data", 0.05),
)


@dataclass
class IngestJob:
    job_id: str
    table_name: str
    mode: str
    source_name: str
    size_bytes: int
    status: str = JOB_QUEUED
    stage: str = ""
    stage_label: str = "Waiting for the ingest worker"
    progress: float = 0.0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "table_name": self.table_name,
            "mode": self.mode,
            "source_name": self.source_name,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "stage": self.stage,
            "stage_label": self.stage_label,
            "progress": round(self.progress, 4),
            "error": self.error,
            "warnings": list(self.warnings),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
        }


class JobStore:
    """Tracks ingest jobs and runs them one at a time."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._jobs: dict[str, IngestJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="calosrv-ingest"
        )

    def get(self, job_id: str) -> IngestJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[IngestJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.started_at or dt.datetime.min, reverse=True)
        return jobs[:limit]

    def submit(
        self,
        table_name: str,
        staged: StagedFile,
        mode: str,
        display_name: str = "",
        event_offset: int = 0,
        delete_source: bool = True,
    ) -> IngestJob:
        job = IngestJob(
            job_id=uuid.uuid4().hex[:16],
            table_name=table_name,
            mode=mode,
            source_name=staged.original_name,
            size_bytes=staged.size_bytes,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(
            self._run, job, staged, display_name, event_offset, delete_source
        )
        return job

    def _advance(self, job: IngestJob, stage_key: str) -> None:
        completed = 0.0
        for key, label, weight in STAGES:
            if key == stage_key:
                job.stage = key
                job.stage_label = label
                job.progress = completed
                log.info("[%s] %s", job.table_name, label)
                return
            completed += weight
        job.stage = stage_key

    def _run(
        self,
        job: IngestJob,
        staged: StagedFile,
        display_name: str,
        event_offset: int,
        delete_source: bool,
    ) -> None:
        job.status = JOB_RUNNING
        job.started_at = dt.datetime.now(dt.timezone.utc)
        name = job.table_name

        try:
            with self._db.write_lock() as con:
                registry.ensure_registry(con)
                existing = registry.get_experiment(con, name)
                record = existing or registry.ExperimentRecord(table_name=name)
                record.display_name = display_name or record.display_name or name
                record.status = registry.STATUS_INGESTING
                record.error = None
                if staged.original_name not in record.source_files:
                    record.source_files = [*record.source_files, staged.original_name]
                if record.created_at is None:
                    record.created_at = job.started_at.replace(tzinfo=None)
                registry.upsert(con, record)

                self._advance(job, "load")
                n_hits = load.load_csv(
                    con, name, staged.path, mode=job.mode, event_offset=event_offset
                )

                self._advance(job, "lattice")
                hit_physical = naming.hit_table(name)
                lattice = lattice_fit.measure_lattice(con, hit_physical)
                bounds = lattice_fit.measure_bounds(con, hit_physical)

                # Persist the lattice before verification runs: the
                # lattice-bounds check reads it back from the registry, and
                # would otherwise skip itself silently on a first ingest.
                record.lattice = lattice
                registry.upsert(con, record)

                self._advance(job, "projection")
                sanitation = derive_proj.build(con, name, lattice)

                self._advance(job, "events")
                n_events = derive_events.build(con, name)
                c_a, c_b = derive_events.calibration(con, name)
                cell_e_max, cell_e_p999 = derive_proj.measure_color_anchors(
                    con, name, lattice.slab_iz
                )

                self._advance(job, "sample")
                sample_rows = derive_proj.build_sample(
                    con, name, self._db.settings.sample_percent
                )

                self._advance(job, "verify")
                # The staged CSV is still on disk here, so the row-count check
                # can compare against the source before it is deleted.
                verification = verify_mod.verify(con, name, staged.path)

                record.n_hits = n_hits
                record.n_events = n_events
                record.n_events_no_d = bounds["n_events_no_d"]
                record.e1_min = bounds["e1_min"]
                record.e1_max = bounds["e1_max"]
                record.e2_min = bounds["e2_min"]
                record.e2_max = bounds["e2_max"]
                record.d_min = bounds["d_min"]
                record.d_max = bounds["d_max"]
                record.overlaps = bounds["overlaps"]
                record.lattice = lattice
                record.cell_e_max = cell_e_max
                record.cell_e_p999 = cell_e_p999
                record.has_sample = sample_rows > 0
                record.status = (
                    registry.STATUS_READY if verification.ok else registry.STATUS_FAILED
                )
                record.error = (
                    None if verification.ok else "; ".join(verification.warnings)
                )
                registry.upsert(con, record)

            job.warnings = list(verification.warnings)
            job.result = {
                "n_hits": n_hits,
                "n_events": n_events,
                "n_events_no_d": bounds["n_events_no_d"],
                "sanitation": sanitation.as_dict(),
                "calibration": {"c_a": c_a, "c_b": c_b},
                "lattice": {
                    "nx": lattice.x.n, "ny": lattice.y.n, "nz": lattice.z.n,
                    "x_uniform": lattice.x.is_uniform,
                    "y_uniform": lattice.y.is_uniform,
                    "z_uniform": lattice.z.is_uniform,
                },
                "checks": verification.checks,
            }
            job.status = JOB_DONE if verification.ok else JOB_FAILED
            job.error = None if verification.ok else "; ".join(verification.warnings)
            job.progress = 1.0
            job.stage_label = (
                "Ingestion complete" if verification.ok else "Verification failed"
            )
            if verification.ok:
                # The canonical frame's full-range scan is the one query that
                # can take a couple of seconds; pay it now, off the request path.
                from ..query import canonical_cache

                canonical_cache.warm(self._db, self._db.settings, [name])

        except ApiError as exc:
            self._fail(job, name, exc.detail)
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            log.error("Ingest of %r failed: %s\n%s", name, exc, traceback.format_exc())
            self._fail(job, name, str(exc))
        finally:
            job.finished_at = dt.datetime.now(dt.timezone.utc)
            # Reclaim the staging space immediately: on the production file this
            # is 7.4 GB that nothing needs once the derived tables exist.
            if delete_source:
                staged.unlink()

    def _fail(self, job: IngestJob, name: str, message: str) -> None:
        job.status = JOB_FAILED
        job.error = message
        job.stage_label = "Ingestion failed"
        try:
            with self._db.write_lock() as con:
                registry.set_status(con, name, registry.STATUS_FAILED, message)
        except Exception:  # pragma: no cover - the original error is what matters
            log.exception("Could not record ingest failure for %r", name)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


_store: JobStore | None = None
_store_lock = threading.Lock()


def get_job_store(database: Database | None = None) -> JobStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                if database is None:
                    raise RuntimeError(
                        "get_job_store() needs a Database on its first call."
                    )
                _store = JobStore(database)
    return _store


def reset_job_store() -> None:
    global _store
    if _store is not None:
        _store.shutdown()
        _store = None
