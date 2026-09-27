"""The ingest job store's bookkeeping, without running an ingest."""

from __future__ import annotations

import datetime as dt

from calosrv.ingest.jobs import JOB_QUEUED, JOB_RUNNING, IngestJob, JobStore


def _job(job_id: str, submitted: dt.datetime, status: str, started: dt.datetime | None) -> IngestJob:
    return IngestJob(job_id=job_id, table_name=f"t_{job_id}", mode="create_new",
                     source_name=f"{job_id}.csv", size_bytes=1, status=status,
                     submitted_at=submitted, started_at=started)


def test_recent_orders_a_running_and_a_queued_job_by_submission():
    """One running job beside a queued one used to raise: naive min vs aware start."""
    store = JobStore(database=None)
    try:
        t0 = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        running = _job("run", t0, JOB_RUNNING, t0)
        queued = _job("wait", t0 + dt.timedelta(seconds=5), JOB_QUEUED, None)
        store._jobs = {running.job_id: running, queued.job_id: queued}
        assert [job.job_id for job in store.recent()] == ["wait", "run"]
    finally:
        store.shutdown()


def test_every_job_reports_when_it_was_submitted():
    job = IngestJob(job_id="x", table_name="t", mode="create_new", source_name="x.csv",
                    size_bytes=1)
    stamped = dt.datetime.fromisoformat(job.as_dict()["submitted_at"])
    assert stamped.tzinfo is not None
