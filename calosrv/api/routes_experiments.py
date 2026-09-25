"""``GET /api/experiments`` - the experiment catalogue."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import bootstrap as bootstrap_mod
from ..db import registry
from ..query import cache as cache_mod
from ..models.common import json_safe
from ..query import experiments
from .deps import CursorDep, SettingsDep, get_db
from fastapi import Depends, Request

router = APIRouter()


@router.get("/api/experiments", summary="Registered experiments and their bounds")
def list_experiments(
    con: CursorDep,
    settings: SettingsDep,
    include_pending: bool = Query(
        True,
        description=(
            "Include experiments that are still ingesting or that failed, so "
            "the interface can report their status rather than appearing to "
            "have lost them."
        ),
    ),
):
    records = experiments.list_all(con, include_pending=include_pending, settings=settings)
    cache = cache_mod.get_cache(settings.cache_entries)
    canonical_cache = cache_mod.get_cache(
        settings.canonical_cache_entries, name=cache_mod.CANONICAL_CACHE
    )
    # This route does not go through `envelope`, so it applies the non-finite
    # float guard itself; a dataset with a degenerate bound would otherwise 500.
    return json_safe({
        "experiments": records,
        "compute": {
            "duckdb_memory_gb": settings.memory_gb,
            "threads": settings.threads,
            "cpu_cores": settings.cpu_cores,
            "debounce_ms": settings.debounce_ms,
            "sample_percent": settings.sample_percent,
            "large_upload_warn_bytes": settings.large_upload_warn_bytes,
            "cache": cache.info(),
            "canonical_cache": canonical_cache.info(),
            "trans_cache": cache_mod.get_cache(
                settings.canonical_cache_entries, name=cache_mod.TRANS_CACHE).info(),
            "local_cache": cache_mod.get_cache(
                settings.canonical_cache_entries, name=cache_mod.LOCAL_CACHE).info(),
        },
    })


@router.delete(
    "/api/experiments/{table_name}", summary="Drop an experiment and its tables"
)
def delete_experiment(table_name: str, request: Request, settings: SettingsDep):
    """Remove every table belonging to one experiment, and its Parquet archive.

    Destructive and irreversible, so it is a separate explicit verb rather than
    a side effect of re-uploading. This is also how an experiment ingested under
    the retired v37 schema is cleared away.
    """
    database = request.app.state.database
    with database.write_lock() as con:
        record = registry.get_experiment(con, table_name)
        archive_removed = bootstrap_mod.drop_experiment(con, table_name, settings)
    cache_mod.invalidate_all(table_name)
    return {
        "deleted": table_name,
        "existed": record is not None,
        "archive_removed": archive_removed,
    }
