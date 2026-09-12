"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import __version__
from ..db import registry
from .deps import CursorDep, SettingsDep

router = APIRouter()


@router.get("/api/health", summary="Liveness probe")
def health(settings: SettingsDep):
    return {
        "status": "ok",
        "version": __version__,
        "duckdb_memory_gb": settings.memory_gb,
        "threads": settings.threads,
    }


@router.get("/api/health/db", summary="Database readiness")
def health_db(con: CursorDep, settings: SettingsDep):
    records = registry.list_experiments(con)
    ready = [r for r in records if r.is_ready]
    return {
        "status": "ok" if ready else "empty",
        "experiments": len(records),
        "ready": len(ready),
        "db_path": str(settings.db_path),
    }
