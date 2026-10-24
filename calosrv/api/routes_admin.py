"""``/api/admin/*`` - the defaults and the automatic ingest behind the Admin Settings panel.

The panel reads the effective default view with ``GET /api/admin/config`` and
saves changes with ``POST``; ``POST /api/admin/auto-ingest/scan`` is its Scan
now, and ``POST /api/admin/experiments/{name}/rebuild`` its Rebuild derived
tables. Scripts can use the same calls. No endpoint in this service is
authenticated, and this one follows the same trust model as upload and delete:
anyone who can reach the port can change what a new session opens on.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from ..admin.store import DefaultsStore
from ..db import archive, naming, registry
from ..errors import ConflictError, IngestError, UnknownTableError
from ..ingest import autoingest
from ..ingest import jobs as jobs_mod
from ..models.common import json_safe
from ..query import experiments
from .deps import CursorDep, SettingsDep

router = APIRouter()


def _store(request: Request) -> DefaultsStore:
    return request.app.state.defaults


def _auto_ingest(request: Request) -> dict[str, Any] | None:
    report = getattr(request.app.state, "auto_ingest", None)
    return report.as_dict() if report is not None else None


@router.get("/api/admin/config", summary="The default view, and where each value comes from")
def get_config(request: Request, con: CursorDep, settings: SettingsDep):
    records = experiments.list_all(con, include_pending=True, settings=settings)
    return json_safe(_store(request).admin_view(records, _auto_ingest(request)))


@router.post("/api/admin/config", summary="Save the default view")
def post_config(
    request: Request,
    con: CursorDep,
    settings: SettingsDep,
    patch: dict[str, Any] = Body(
        ...,
        description=(
            "Any subset of default_dataset, default_coord_system, default_model, "
            "default_channel, default_display_mode and default_rho_norm. A null "
            "clears that field's saved value, so the environment or built-in "
            "default shows through."
        ),
        examples=[{"default_coord_system": "trans", "default_channel": "gradcam"}],
    ),
):
    records = experiments.list_all(con, include_pending=True, settings=settings)
    store = _store(request)
    store.update(patch, records)
    return json_safe(store.admin_view(records, _auto_ingest(request)))


@router.post("/api/admin/auto-ingest/scan", summary="Scan the drop folder now")
def scan_now(request: Request, settings: SettingsDep):
    """What a restart would do, without the restart: queue every new file.

    Idempotent like the boot-time scan - a file whose experiment exists, or
    whose content is already archived, is skipped - and serialised, so two
    clicks cannot queue one file twice.
    """
    database = request.app.state.database
    report = autoingest.scan(database, settings, jobs_mod.get_job_store(database))
    request.app.state.auto_ingest = report
    # A file still being copied is scanned again once it has settled.
    watch = getattr(request.app.state, "settle_watch", None)
    if watch is not None:
        watch.after(report)
    if not report.enabled:
        raise ConflictError(f"Automatic ingest is off: {report.reason}", reason=report.reason)
    return json_safe(report.as_dict())


@router.post(
    "/api/admin/experiments/{table_name}/rebuild", status_code=202,
    summary="Rebuild an experiment's derived tables from its archive",
)
def rebuild(table_name: str, request: Request, con: CursorDep, settings: SettingsDep):
    """Re-derive every table of an experiment from its Parquet archive, atomically.

    How an experiment derived by an earlier release gains the tables the new
    panels read. The rebuild runs in one transaction on the ingest worker:
    the experiment stays served from its old tables until the new ones have
    verified, and a rebuild that fails verification is rolled back.
    """
    name = naming.validate_experiment_name(table_name)
    record = registry.get_experiment(con, name)
    if record is None:
        raise UnknownTableError(f"No experiment named {name!r} is registered.", table_name=name)
    database = request.app.state.database
    store = jobs_mod.get_job_store(database)
    if name in store.active_names():
        raise ConflictError(f"A job for {name!r} is already queued or running.", table_name=name)
    manifest = archive.read_manifest(settings, name)
    if manifest is None or not manifest.parts:
        raise IngestError(f"Experiment {name!r} has no archive to rebuild from.", table_name=name)
    job = store.submit_rebuild(name, size_bytes=manifest.bytes)
    return {"job": job.as_dict(), "poll": f"/api/upload/{job.job_id}"}
