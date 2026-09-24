"""``POST /api/upload`` - streamed multipart dataset ingestion.

The request body is never buffered in memory. It is written through to the
staging directory in 8 MiB chunks, so a multi-gigabyte upload costs one chunk of
resident memory regardless of size.

The response returns as soon as the file is on disk, carrying a job identifier.
The ingest itself runs on a background worker and is polled through
``GET /api/upload/{job_id}``, because it takes minutes on a large file and holds
DuckDB's single write lock for the duration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, Request, UploadFile

from ..db import naming, registry
from ..db.ddl import HIT_COLUMN_NAMES
from ..errors import IngestError, NotFoundError, ValidationError
from ..ingest import jobs as jobs_mod
from ..ingest import local as local_ingest
from ..ingest import stream
from ..ingest.stream import StagedFile
from ..models.upload import UploadMode
from ..query import cache as cache_mod
from .deps import SettingsDep

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/upload", status_code=202, summary="Upload and ingest a CSV dataset")
async def upload(
    request: Request,
    settings: SettingsDep,
    file: UploadFile = File(..., description="The inference CSV to ingest."),
    table_name: str = Form(..., description="Target experiment name."),
    mode: str = Form(
        UploadMode.CREATE_NEW.value, description="create_new | append"
    ),
    display_name: str = Form("", description="Label for the experiment dropdown."),
    event_offset: int = Form(
        0, description="Shift incoming event numbers to avoid a collision."
    ),
):
    name = naming.validate_experiment_name(table_name)
    if mode not in (m.value for m in UploadMode):
        raise ValidationError(
            f"mode must be create_new or append; got {mode!r}.", field="mode"
        )

    database = request.app.state.database

    # Appending to an experiment that does not exist is a mistake worth catching
    # before spending the upload, not after.
    if mode == UploadMode.APPEND.value:
        with database.read_cursor() as con:
            registry.ensure_registry(con)
            if registry.get_experiment(con, name) is None:
                raise IngestError(
                    f"Cannot append to experiment {name!r}: it does not exist. "
                    "Use create_new for the first upload."
                )

    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        stream.check_free_space(
            settings.staging_dir, int(declared), settings.disk_headroom_factor
        )

    destination = stream.staged_path(settings.staging_dir, file.filename or "upload.csv")
    staged = await stream.stream_to_disk(
        stream.iter_upload(file), destination, file.filename or "upload.csv"
    )

    # Now that the true size is known, re-check headroom before committing the
    # ingest; a chunked upload has no reliable content-length.
    try:
        stream.check_free_space(
            settings.staging_dir, staged.size_bytes, settings.disk_headroom_factor
        )
    except Exception:
        staged.unlink()
        raise

    cache_mod.invalidate_all(name)

    store = jobs_mod.get_job_store(database)
    job = store.submit(
        table_name=name,
        staged=staged,
        mode=mode,
        display_name=display_name,
        event_offset=event_offset,
    )

    return {
        "job": job.as_dict(),
        "poll": f"/api/upload/{job.job_id}",
        "note": (
            "Ingestion runs in the background. Poll the job endpoint for "
            "progress; the experiment appears in /api/experiments once it "
            "reports status 'ready'."
        ),
    }


@router.post(
    "/api/ingest-local", status_code=202,
    summary="Ingest a CSV already present on the server, by path",
)
def ingest_local(
    request: Request,
    settings: SettingsDep,
    path: str = Form(..., description="Path to a CSV inside the allowed root."),
    table_name: str = Form(...),
    mode: str = Form(UploadMode.CREATE_NEW.value),
    display_name: str = Form(""),
    event_offset: int = Form(0),
):
    """Run an ingest inside the server process, without moving the file.

    DuckDB holds its lock on the database file across processes, so a separate
    CLI process cannot open the database while the server is running. Delegating
    to the server is what keeps the single-writer rule intact while still
    letting a multi-gigabyte dataset be read in place rather than uploaded.
    """
    name = naming.validate_experiment_name(table_name)
    if mode not in (m.value for m in UploadMode):
        raise ValidationError(
            f"mode must be create_new or append; got {mode!r}.", field="mode"
        )

    source = local_ingest.resolve_local_path(settings, path)
    database = request.app.state.database

    if mode == UploadMode.APPEND.value:
        with database.read_cursor() as con:
            registry.ensure_registry(con)
            if registry.get_experiment(con, name) is None:
                raise IngestError(
                    f"Cannot append to experiment {name!r}: it does not exist."
                )

    cache_mod.invalidate_all(name)

    staged = StagedFile(
        path=source,
        original_name=source.name,
        size_bytes=source.stat().st_size,
    )
    store = jobs_mod.get_job_store(database)
    job = store.submit(
        table_name=name,
        staged=staged,
        mode=mode,
        display_name=display_name,
        event_offset=event_offset,
        # The file belongs to the host, not the application. Deleting a user's
        # dataset as a side effect of reading it would be indefensible.
        delete_source=False,
    )
    return {"job": job.as_dict(), "poll": f"/api/upload/{job.job_id}"}


@router.get("/api/local-files", summary="CSV files available for server-side ingest")
def local_files(settings: SettingsDep):
    root = settings.local_ingest_dir
    return {
        "root": str(root) if root else None,
        "enabled": root is not None,
        "files": local_ingest.list_local_files(settings),
    }


@router.get("/api/upload/{job_id}", summary="Ingest job status")
def job_status(job_id: str, request: Request):
    store = jobs_mod.get_job_store(request.app.state.database)
    job = store.get(job_id)
    if job is None:
        raise NotFoundError(f"No ingest job with id {job_id!r}.")
    return job.as_dict()


@router.get("/api/upload", summary="Recent ingest jobs")
def recent_jobs(request: Request):
    store = jobs_mod.get_job_store(request.app.state.database)
    return {"jobs": [job.as_dict() for job in store.recent()]}


@router.get("/api/upload-info", summary="Upload limits and guidance")
def upload_info(settings: SettingsDep):
    """What the upload modal needs to warn the user about before they commit."""
    import shutil

    free = shutil.disk_usage(settings.staging_dir).free
    return {
        "modes": [m.value for m in UploadMode],
        "free_bytes": free,
        "headroom_factor": settings.disk_headroom_factor,
        "max_practical_bytes": int(free / settings.disk_headroom_factor),
        "large_upload_warn_bytes": settings.large_upload_warn_bytes,
        "warning": (
            "Large uploads are supported, but a browser upload has no resume: "
            "if the connection drops the transfer restarts from the beginning. "
            "Ingestion also needs roughly three times the CSV size in free disk "
            "space for the staging file and the derived tables. For datasets "
            "already on the server, the offline CLI "
            "(python -m calosrv.ingest --input ... --table ...) avoids the "
            "transfer entirely."
        ),
        "schema": {
            "columns": list(HIT_COLUMN_NAMES),
            "note": (
                "The file must carry exactly these 29 columns in this order. "
                "Empty fields are read as NULL; rows with a missing coordinate "
                "or a non-positive energy are excluded from the projections and "
                "counted in the ingest report."
            ),
        },
    }
