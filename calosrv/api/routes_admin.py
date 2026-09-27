"""``/api/admin/config`` - the defaults behind the Admin Settings panel.

The panel reads the effective default view with ``GET`` and saves changes with
``POST``. Scripts can use the same two calls. No endpoint in this service is
authenticated, and this one follows the same trust model as upload and delete:
anyone who can reach the port can change what a new session opens on.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from ..admin.store import DefaultsStore
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
