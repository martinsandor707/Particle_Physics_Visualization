"""Background ingest jobs and their status, for polling.

Ingesting the 24 GB production file takes minutes. That cannot happen inside an
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
from ..db import registry
from ..errors import ApiError
from . import pipeline
from .pipeline import STAGES
from .stream import StagedFile

log = logging.getLogger(__name__)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

__all__ = ["STAGES", "IngestJob", "JobStore", "get_job_store", "reset_job_store"]


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
                result = pipeline.run_ingest(
                    con, self._db.settings, name, staged.path,
                    source_name=staged.original_name,
                    mode=job.mode,
                    event_offset=event_offset,
                    display_name=display_name,
                    # An upload was already checked against the 3x headroom
                    # before it was staged; ingest-local checks in its route.
                    check_space=False,
                    created_at=job.started_at.replace(tzinfo=None),
                    progress=lambda stage: self._advance(job, stage),
                )

            # The tables were rebuilt under the write lock: anything cached (or
            # being computed) against the old ones must go before the warmers
            # run. The upload routes also invalidate at submit time.
            from ..query import cache as cache_mod

            cache_mod.invalidate_all(name)
            job.warnings = result.warnings
            job.result = result.as_job_result()
            job.status = JOB_DONE if result.ok else JOB_FAILED
            job.error = None if result.ok else "; ".join(result.warnings)
            job.progress = 1.0
            job.stage_label = "Ingestion complete" if result.ok else "Verification failed"
            if result.ok:
                # The co-registered frames' full-range scans are the queries
                # that take seconds; pay them now, off the request path.
                from ..query import canonical_cache, shower_frames

                shower_frames.warm(
                    self._db, self._db.settings, [name],
                    after=canonical_cache.warm(self._db, self._db.settings, [name]),
                )

        except ApiError as exc:
            self._fail(job, name, exc.detail)
            self._invalidate(name)
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            log.error("Ingest of %r failed: %s\n%s", name, exc, traceback.format_exc())
            self._fail(job, name, str(exc))
            self._invalidate(name)
        finally:
            job.finished_at = dt.datetime.now(dt.timezone.utc)
            # Reclaim the staging space immediately: on the production file this
            # is 24 GB that nothing needs once the archive and derived tables exist.
            if delete_source:
                staged.unlink()

    @staticmethod
    def _invalidate(name: str) -> None:
        """Drop cached bundles of ``name``: a failed ingest may have rebuilt its tables."""
        from ..query import cache as cache_mod

        cache_mod.invalidate_all(name)

    def _fail(self, job: IngestJob, name: str, message: str) -> None:
        job.status = JOB_FAILED
        job.error = message
        job.stage_label = "Ingestion failed"
        try:
            with self._db.write_lock() as con:
                # Only an experiment the job had started to rewrite is failed.
                # A refused file (header, event-range collision) or a discarded
                # append leaves the experiment as it was, and it stays served.
                current = registry.get_experiment(con, name)
                if current is None or current.status == registry.STATUS_INGESTING:
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
