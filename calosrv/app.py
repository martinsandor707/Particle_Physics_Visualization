"""FastAPI application factory.

Owns startup and shutdown: opening the database, reconciling it, seeding the
baseline experiment on a first boot, and mounting the static frontend.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, load_settings
from .db import bootstrap as bootstrap_mod
from .db.connection import get_database, reset_database
from .errors import ApiError
from .ingest import jobs as jobs_mod
from .logging_setup import configure_logging, log_boot_banner
from .api import (
    routes_energy,
    routes_experiments,
    routes_health,
    routes_performance,
    routes_projections,
    routes_upload,
)

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Experiment name used for the automatically seeded demonstration dataset.
BASELINE_TABLE = "experiment_baseline"


def seed_baseline(database, settings: Settings) -> None:
    """Populate the demonstration experiment on a first boot.

    Seeded from the full 1000 rows of ``hits_with_gradcam_dummy.csv`` through
    exactly the same pipeline as a real upload - no synthetic records are
    generated. That file holds two events, both well separated, so the spatial
    panels render correctly while the reconstructed-energy panel reports
    insufficient statistics rather than fitting a meaningless two-point width.
    Section 3 of CLAUDE.md forbids fabricating inference outputs to fill a gap;
    showing the real, small dataset and saying what it cannot support is the
    honest alternative.
    """
    if settings.seed_csv is None or not settings.seed_csv.is_file():
        log.warning(
            "No baseline seed CSV found; the database will start empty. "
            "Upload a dataset or run: python -m calosrv.ingest --input <csv> "
            "--table <name>"
        )
        return

    from .ingest.stream import StagedFile

    staged = StagedFile(
        path=settings.seed_csv,
        original_name=settings.seed_csv.name,
        size_bytes=settings.seed_csv.stat().st_size,
    )
    store = jobs_mod.get_job_store(database)
    log.info("Seeding baseline experiment from %s", settings.seed_csv)
    store.submit(
        table_name=BASELINE_TABLE,
        staged=staged,
        mode="create_new",
        display_name="Baseline (demonstration dataset)",
        # The seed file is either baked into the image or lives in the user's
        # repository. Deleting it after reading would be destructive.
        delete_source=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    database = get_database(settings)
    app.state.database = database

    log_boot_banner(settings)

    with database.write_lock() as con:
        bootstrap_mod.bootstrap(con)
        empty = bootstrap_mod.is_empty(con)

    jobs_mod.get_job_store(database)
    if empty:
        seed_baseline(database, settings)

    try:
        yield
    finally:
        jobs_mod.reset_job_store()
        reset_database()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging()

    app = FastAPI(
        title="Calorimeter Shower Reconstruction Diagnostic Server",
        version=__version__,
        description=(
            "Out-of-core diagnostic interface for calorimeter inference "
            "datasets. All spatial binning and statistical reduction runs "
            "server-side in DuckDB; the browser receives only pre-aggregated "
            "payloads."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Payloads are base64 rasters and JSON arrays, both of which compress well.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_problem(),
            media_type="application/problem+json",
        )

    for module in (
        routes_health,
        routes_experiments,
        routes_upload,
        routes_projections,
        routes_energy,
        routes_performance,
    ):
        app.include_router(module.router)

    if STATIC_DIR.is_dir():
        app.mount(
            "/static", StaticFiles(directory=STATIC_DIR), name="static"
        )

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app
