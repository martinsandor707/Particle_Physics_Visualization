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
from typing import Any

from ..db.connection import Database
from ..db import registry
from ..errors import ApiError, ConflictError
from . import pipeline, source_state
from .pipeline import STAGES
from .recipes import stages as stages_of
from .stream import StagedFile

log = logging.getLogger(__name__)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

__all__ = ["STAGES", "IngestJob", "JobStore", "get_job_store", "reset_job_store"]

#: A job that re-derives an experiment from its archive.
MODE_REBUILD = "rebuild"
#: A job that replaces a ready experiment's data from its changed source file,
#: atomically, and one that ingests a failed experiment's file again.
MODE_REINGEST = source_state.ACTION_REINGEST
MODE_RETRY = source_state.ACTION_RETRY


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
    #: When the job was queued. Always set and timezone-aware, so jobs can be
    #: ordered before any of them has started.
    submitted_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    #: Replace an existing experiment of this name (``create_new`` only).
    force_reingest: bool = False
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    #: The experiment kind and input schema, once the source is recognised.
    kind: str | None = None
    schema: str | None = None
    #: Where the source file came from (``source_state.ORIGINS``): what the
    #: registry row's source record says. Not in the payload.
    origin: str | None = None

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
            "submitted_at": self.submitted_at.isoformat(),
            "force_reingest": self.force_reingest,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
            "kind": self.kind,
            "schema": self.schema,
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
        """The latest jobs, newest submission first.

        Ordered by submission rather than start: a queued job has not started,
        and mixing its missing start time with the aware ones of started jobs
        is what used to raise here whenever one job ran while another waited.
        """
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.submitted_at, reverse=True)
        return jobs[:limit]

    def latest_for(self, table_name: str) -> IngestJob | None:
        """The newest job, by submission, that names ``table_name``; None when there is none."""
        with self._lock:
            found = [j for j in self._jobs.values() if j.table_name == table_name]
        return max(found, key=lambda j: j.submitted_at, default=None)

    def active_names(self) -> set[str]:
        """Experiments with a job queued or running.

        A second job for one of these would replace or interleave with the
        first, and nothing else would stop it: the registry knows of a queued
        job only once the worker reaches it.
        """
        with self._lock:
            return {
                job.table_name for job in self._jobs.values()
                if job.status in (JOB_QUEUED, JOB_RUNNING)
            }

    def submit(
        self,
        table_name: str,
        staged: StagedFile,
        mode: str,
        display_name: str = "",
        event_offset: int = 0,
        delete_source: bool = True,
        force_reingest: bool = False,
        kind: str | None = None,
        schema: str | None = None,
        origin: str | None = None,
    ) -> IngestJob:
        job = IngestJob(
            job_id=uuid.uuid4().hex[:16],
            table_name=table_name,
            mode=mode,
            source_name=staged.original_name,
            size_bytes=staged.size_bytes,
            force_reingest=force_reingest,
            kind=kind,
            schema=schema,
            origin=origin,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(
            self._run, job, staged, display_name, event_offset, delete_source
        )
        return job

    def submit_reingest(
        self,
        table_name: str,
        staged: StagedFile,
        action: str,
        display_name: str,
        event_offset: int,
        provenance: dict[str, Any],
        kind: str | None = None,
        schema: str | None = None,
        expected_job_id: Any = pipeline.UNCHECKED,
    ) -> IngestJob:
        """Re-ingest ``table_name`` from its source file on the ingest worker.

        ``action`` is ``reingest`` (a ready experiment: replaced atomically, the
        old data served until the new verify) or ``retry`` (a failed one: ingested
        again as ``create_new`` with replacement). ``staged.path`` is the source
        file in place, which the job never deletes. Raises ``ConflictError`` when
        a job for the name is queued or running: the check and the registration
        are one step, so two requests cannot both pass it.

        ``expected_job_id`` is the ``job_id`` of the row's source record when the
        request was judged (None for a row recorded before source tracking). The
        worker reads the row again and refuses when it names another job, which
        means an upload or another job rewrote the experiment since.
        """
        if action not in (MODE_REINGEST, MODE_RETRY):
            raise ValueError(f"unknown re-ingest action {action!r}")
        job = IngestJob(
            job_id=uuid.uuid4().hex[:16],
            table_name=table_name,
            mode=action,
            source_name=staged.original_name,
            size_bytes=staged.size_bytes,
            force_reingest=action == MODE_RETRY,
            kind=kind,
            schema=schema,
            origin=provenance.get("origin"),
        )
        with self._lock:
            if any(j.table_name == table_name and j.status in (JOB_QUEUED, JOB_RUNNING)
                   for j in self._jobs.values()):
                raise ConflictError(
                    f"A job for {table_name!r} is already queued or running.",
                    table_name=table_name)
            self._jobs[job.job_id] = job
        self._executor.submit(self._run_reingest, job, staged, display_name, event_offset,
                              provenance, expected_job_id)
        return job

    def submit_rebuild(self, table_name: str, size_bytes: int = 0) -> IngestJob:
        """Re-derive ``table_name`` from its archive, atomically, on the ingest worker."""
        job = IngestJob(
            job_id=uuid.uuid4().hex[:16],
            table_name=table_name,
            mode=MODE_REBUILD,
            source_name="(archive)",
            size_bytes=int(size_bytes),
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(self._run_rebuild, job)
        return job

    def _advance(self, job: IngestJob, stage_key: str, kind: str | None = None) -> None:
        if kind:
            job.kind = kind
        completed = 0.0
        for key, label, weight in stages_of(job.kind, rebuild=job.mode == MODE_REBUILD):
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
                    progress=lambda stage, kind: self._advance(job, stage, kind),
                    force_reingest=job.force_reingest,
                    provenance=self._provenance(job, staged),
                )

            self._complete(job, name, result)

        except ApiError as exc:
            self._fail(job, name, exc.detail)
            self._invalidate(name)
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            log.error("Ingest of %r failed: %s\n%s", name, exc, traceback.format_exc())
            self._fail(job, name, str(exc))
            self._invalidate(name)
        finally:
            self._finish(job)
            # Reclaim the staging space immediately: on the production file this
            # is 24 GB that nothing needs once the archive and derived tables exist.
            if delete_source:
                staged.unlink()

    def _complete(self, job: IngestJob, name: str, result) -> None:
        """What follows an ingest that returned: caches, the job's record, warming, the analysis."""
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
            job.kind = result.record.kind
            self._after_commit(name, result.record)

    def _after_commit(self, name: str, record) -> None:
        """The optional steps after a data change that is already committed.

        The data are served whether or not these succeed, so a failure is logged
        and the job stays what it is: ``done``, not ``failed``.
        """
        try:
            # The co-registered frames' full-range scans are the queries
            # that take seconds; pay them now, off the request path.
            from ..query import warming

            warming.warm(self._db, self._db.settings, [record])
        except Exception:  # noqa: BLE001 - warming is an optimisation
            log.exception("Warming %r after its ingest failed; the data are served", name)
        try:
            self._queue_model_analysis(name)
        except Exception:  # noqa: BLE001 - the analysis can be queued again by a rescan
            log.exception("Queueing the model analysis of %r failed; Rescan models queues it", name)

    @staticmethod
    def _finish(job: IngestJob) -> None:
        """Close a job whatever escaped the worker, so ``active_names`` never keeps a dead one.

        ``except Exception`` does not catch ``KeyboardInterrupt`` or ``SystemExit``;
        a job they leave ``running`` would block every later job for its name.
        """
        job.finished_at = dt.datetime.now(dt.timezone.utc)
        if job.status in (JOB_QUEUED, JOB_RUNNING):
            job.status = JOB_FAILED
            job.error = job.error or "The ingest worker was interrupted before the job finished."
            job.stage_label = "Interrupted"

    def _provenance(self, job: IngestJob, staged: StagedFile) -> dict[str, Any] | None:
        """The origin spec the pipeline records, or None for a caller that named no origin."""
        if job.origin is None:
            return None
        return source_state.origin_spec(
            self._db.settings, job.origin, staged.path, staged.original_name, job.job_id)

    def _run_reingest(
        self,
        job: IngestJob,
        staged: StagedFile,
        display_name: str,
        event_offset: int,
        provenance: dict[str, Any],
        expected_job_id: Any = pipeline.UNCHECKED,
    ) -> None:
        """A re-ingest or a retry, on the ingest worker. The source file is never deleted.

        The worker reads the experiment's row again before it touches anything
        (``expected_job_id``): a re-ingest that finds another job's data, or a
        retry whose row is no longer ``failed``, refuses with nothing done.
        """
        job.status = JOB_RUNNING
        job.started_at = dt.datetime.now(dt.timezone.utc)
        name = job.table_name
        reingest = job.mode == MODE_REINGEST
        try:
            with self._db.write_lock() as con:
                if reingest:
                    result = pipeline.reingest_atomic(
                        con, self._db.settings, name, staged.path,
                        source_name=staged.original_name, provenance=provenance,
                        job_id=job.job_id, expected_job_id=expected_job_id,
                        progress=lambda stage, kind: self._advance(job, stage, kind),
                    )
                else:
                    pipeline.ensure_unchanged_since(
                        registry.get_experiment(con, name), name, expected_job_id,
                        status=registry.STATUS_FAILED)
                    result = pipeline.run_ingest(
                        con, self._db.settings, name, staged.path,
                        source_name=staged.original_name,
                        mode="create_new",
                        event_offset=event_offset,
                        display_name=display_name,
                        check_space=False,
                        created_at=job.started_at.replace(tzinfo=None),
                        progress=lambda stage, kind: self._advance(job, stage, kind),
                        force_reingest=True,
                        provenance={**provenance, "job_id": job.job_id},
                    )
            self._complete(job, name, result)
            if reingest:
                job.stage_label = "Re-ingest complete" if result.ok else "Re-ingest rolled back"
        except pipeline.ReingestCommittedError as exc:
            # The database changed: the job failed, but the caches are stale all the same.
            job.status, job.error = JOB_FAILED, exc.detail
            job.stage_label = "Re-ingest committed; manifest pending"
            self._invalidate(name)
        except ApiError as exc:
            self._fail_reingest(job, name, exc.detail, reingest)
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            log.error("%s of %r failed: %s\n%s", job.mode, name, exc, traceback.format_exc())
            self._fail_reingest(job, name, str(exc), reingest)
        finally:
            self._finish(job)

    def _fail_reingest(self, job: IngestJob, name: str, message: str, reingest: bool) -> None:
        """A failed re-ingest left the experiment as it was; a failed retry fails it again."""
        if reingest:
            # Rolled back: the registry row is untouched and is not written here.
            job.status, job.error = JOB_FAILED, message
            job.stage_label = "Re-ingest rolled back"
        else:
            self._fail(job, name, message)
        self._invalidate(name)

    def _run_rebuild(self, job: IngestJob) -> None:
        job.status = JOB_RUNNING
        job.started_at = dt.datetime.now(dt.timezone.utc)
        name = job.table_name
        try:
            with self._db.write_lock() as con:
                result = pipeline.rebuild_atomic(
                    con, self._db.settings, name,
                    progress=lambda stage, kind: self._advance(job, stage, kind),
                )
            from ..query import cache as cache_mod

            cache_mod.invalidate_all(name)
            job.warnings = result.warnings
            job.result = result.as_job_result()
            job.status = JOB_DONE if result.ok else JOB_FAILED
            job.error = None if result.ok else (
                "The rebuild failed verification and was rolled back; the experiment is "
                "served as it was. " + "; ".join(result.warnings))
            job.progress = 1.0
            job.stage_label = "Rebuild complete" if result.ok else "Rebuild rolled back"
            if result.ok:
                self._after_commit(name, result.record)
        except ApiError as exc:
            job.status, job.error, job.stage_label = JOB_FAILED, exc.detail, "Rebuild failed"
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            log.error("Rebuild of %r failed: %s\n%s", name, exc, traceback.format_exc())
            job.status, job.error, job.stage_label = JOB_FAILED, str(exc), "Rebuild failed"
        finally:
            self._finish(job)

    @staticmethod
    def _queue_model_analysis(name: str) -> None:
        """An aggregate experiment that pairs with shipped XGBoost models is analysed on the
        model-run worker (``calosrv/modelruns``), never on this one: a no-op for any other."""
        from ..modelruns import jobs as modelruns_jobs

        modelruns_jobs.after_ready(name)

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
