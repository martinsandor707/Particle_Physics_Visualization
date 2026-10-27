"""``/api/admin/*`` - the defaults and the automatic ingest behind the Admin Settings panel.

The panel reads the effective default view with ``GET /api/admin/config`` and
saves changes with ``POST``; ``POST /api/admin/auto-ingest/scan`` is its Scan
now, and ``POST /api/admin/experiments/{name}/rebuild`` its Rebuild derived
tables. ``GET /api/admin/model-runs`` lists the XGBoost model analysis of every
aggregate experiment - read-only: it reports, and queues nothing -
``POST /api/admin/model-runs/scan`` is its Rescan models, which queues every
missing or stale analysis, and ``POST /api/admin/model-runs/{name}/analyse`` its
Re-analyse. Scripts can use the same calls. No endpoint in this service is
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
from ..modelruns import jobs as modelruns_jobs
from ..modelruns import pairing as pairing_mod
from ..models.common import json_safe
from ..query import experiments
from ..text import typographic
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


def _model_runs_view(found: modelruns_jobs.ModelRunStore, settings) -> dict[str, Any]:
    catalogue = found.catalogue
    return {
        "models": catalogue.as_dict() if catalogue is not None else None,
        "runs": [state.as_dict() for state in found.states()],
        "worker": {"nthread": settings.model_threads, "busy": found.busy(),
                   "steps": modelruns_jobs.N_STEPS},
        "statuses": list(modelruns_jobs.STATUSES),
    }


@router.get("/api/admin/model-runs", summary="The XGBoost model analysis of every aggregate experiment")
def get_model_runs(request: Request, settings: SettingsDep):
    """Each aggregate experiment's pairing with the shipped models, and its analysis. Read-only.

    Rescans the models folder (headers are cached by size and modification
    time), re-pairs every aggregate experiment and compares each stored
    analysis with the models, the libraries and the event table's events: one
    that no longer matches is reported ``stale`` with its reasons. Nothing is
    queued - ``POST /api/admin/model-runs/scan`` does that - and the feature
    values are not re-read (the scan, the ingest hook and the worker compare
    them).
    """
    found = modelruns_jobs.get_model_runs(request.app.state.database)
    found.report()
    return json_safe(_text_tree(_model_runs_view(found, settings)))


@router.post("/api/admin/model-runs/scan", summary="Rescan the models and queue stale analyses")
def scan_model_runs(request: Request, settings: SettingsDep):
    """Rescan models: what a restart's boot check does, without the restart.

    Re-pairs every aggregate experiment and compares each stored analysis
    with everything it was computed from, the feature and label values
    included; a missing or stale one is queued, unless its last attempt
    failed on exactly these inputs (Re-analyse retries that). Idempotent: an
    analysis already queued or running is never queued twice. Answers with
    the list ``GET`` reads.
    """
    found = modelruns_jobs.get_model_runs(request.app.state.database)
    found.scan()
    return json_safe(_text_tree(_model_runs_view(found, settings)))


@router.post(
    "/api/admin/model-runs/{table_name}/analyse", status_code=202,
    summary="Queue the XGBoost analysis of one experiment again",
)
def analyse(table_name: str, request: Request, con: CursorDep, settings: SettingsDep):
    """Re-run the analysis even when the stored one is current (Re-analyse).

    Refused when the experiment is not registered (404), when it does not pair
    with models or is not ready (422, with the pairing's reason) and when an
    analysis of it is already queued or running (409).
    """
    from ..errors import CapabilityError

    name = naming.validate_experiment_name(table_name)
    record = registry.get_experiment(con, name)
    if record is None:
        raise UnknownTableError(f"No experiment named {name!r} is registered.", table_name=name)
    found = modelruns_jobs.get_model_runs(request.app.state.database)
    if name in found.busy():
        raise ConflictError(f"An XGBoost analysis of {name!r} is already queued or running.",
                            table_name=name)
    pairing = pairing_mod.pair(record, found.rescan())
    reason = None
    if not pairing.paired:
        reason = f"No XGBoost models pair with this experiment: {pairing.reason}"
    elif not record.is_ready:
        reason = f"It is not ready (status: {record.status})."
    if reason is None:
        state = found.submit(record, force=True)
        if state.status in (modelruns_jobs.STATUS_QUEUED, modelruns_jobs.STATUS_RUNNING):
            return json_safe(_text_tree({"run": state.as_dict(), "poll": "/api/admin/model-runs"}))
        reason = state.gate_reason() or "It cannot be analysed."
    reason = typographic(reason)
    raise CapabilityError(
        f"xgboost cannot be analysed for experiment {name!r}: {reason}",
        field="table_name", capability="xgboost", kind=record.kind, reason=reason,
        table_name=name)


#: Fields of the model-runs payload that are paths or file names, never typeset.
_VERBATIM = frozenset({"dir", "path", "model_file", "source_file"})


def _text_tree(node: Any) -> Any:
    """Every sentence with U+2212 for a negative number; paths and file names untouched."""
    if isinstance(node, str):
        return typographic(node)
    if isinstance(node, dict):
        return {k: v if k in _VERBATIM else _text_tree(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_text_tree(v) for v in node]
    return node
