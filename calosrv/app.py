"""FastAPI application factory.

Owns startup and shutdown: opening the database, reconciling it, seeding the
baseline experiment on a first boot, and mounting the static frontend.
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
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

#: Matches the asset URLs in index.html, so they can be given a version stamp.
_ASSET_URL = re.compile(r'(src|href)="(/static/[^"?]+)"')


def asset_fingerprint(directory: Path = STATIC_DIR) -> str:
    """A short hash over the static tree's paths, sizes and modification times.

    This is the fix for a genuinely nasty class of failure. The page and its
    scripts are separate downloads with independent cache lifetimes, so a
    browser can hold a *stale* script against *fresh* markup. When that happened
    here the cached script still expected the readout elements that the numeric
    inputs replaced, and threw

        TypeError: Cannot set properties of null (setting 'textContent')

    during module initialisation - before ECharts was configured or any data
    fetched, so the whole interface was dead with no visible cause. The stale
    stylesheet likewise lacked the rules for the new inputs and buttons, which
    is why they rendered as browser-default white boxes.

    Stamping every asset URL with a hash of the tree means the markup can only
    ever reference the scripts and styles it was built against: change any file
    and every URL changes with it, so there is no combination of caches that can
    produce a mismatched pair.
    """
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(str(stat.st_size).encode())
        digest.update(str(int(stat.st_mtime)).encode())
    return digest.hexdigest()[:12]


#: Relative ES module specifiers, e.g. ``from './state.js'`` or
#: ``import('./panels/energy.js')``. Anchored on the quote so a matching string
#: in a comment or a template literal is not rewritten.
_JS_IMPORT = re.compile(
    r"""(\bfrom\s*|\bimport\s*\(?\s*)(['"])(\.{1,2}/[^'"?]+?\.js)(['"])"""
)


class VersionedStaticFiles(StaticFiles):
    """Static files, with the module graph stamped and cached deliberately.

    Two things happen here, and the second is the one that actually closes the
    hole.

    **Caching.** A request carrying the ``v`` stamp is safe to keep forever: if
    the file changes the stamp changes, so the URL changes too. An unstamped
    request must revalidate, so a stale copy is never served silently.

    **Rewriting.** Only the entry points can be stamped by the markup; a module
    reached through ``import './state.js'`` is requested by the browser at a
    bare URL of its own. Stamping the entry point alone therefore leaves the
    rest of the graph on whatever each browser already had - which produced

        TypeError: state.isTouched is not a function

    when a page holding a fresh ``main.js`` imported a ``state.js`` cached
    before that method existed. Revalidation headers do not rescue it either,
    because an entry cached *before* those headers existed is still governed by
    the heuristic freshness it was stored under.

    So every relative specifier inside a served script is rewritten to carry the
    same stamp. The whole graph then hangs off one version: either every module
    is the new one, or the URL differs and the browser must fetch it.
    """

    def __init__(self, *args, fingerprint: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fingerprint = fingerprint

    async def get_response(self, path: str, scope):
        stamped = "v=" in scope.get("query_string", b"").decode()

        # Vendored libraries are skipped: they are large, they carry no relative
        # imports of ours, and rewriting a minified bundle risks more than it
        # gains.
        if self.fingerprint and path.endswith(".js") and "vendor" not in path:
            full = Path(self.directory) / path
            if full.is_file():
                source = full.read_text(encoding="utf-8")
                rewritten = _JS_IMPORT.sub(
                    rf"\1\2\3?v={self.fingerprint}\4", source
                )
                return Response(
                    rewritten,
                    media_type="text/javascript; charset=utf-8",
                    headers={
                        "Cache-Control": (
                            "public, max-age=31536000, immutable" if stamped
                            else "no-cache"
                        ),
                    },
                )

        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if stamped else "no-cache"
        )
        return response

#: Experiment name used for the automatically seeded demonstration dataset.
BASELINE_TABLE = "experiment_baseline"


def seed_baseline(database, settings: Settings) -> None:
    """Populate the demonstration experiment on a first boot.

    Seeded from the full 1000 rows of ``hits_all_models_dummy.csv`` through
    exactly the same pipeline as a real upload - no synthetic records are
    generated. That file holds two events, both well separated, so the spatial
    panels render correctly while the reconstructed-energy panel reports its
    two-event mean and width - flagged as one degree of freedom, and quoted with
    the standard errors that make the weakness of the estimate legible - while
    drawing the events themselves rather than a fitted curve.

    Section 3 of CLAUDE.md forbids fabricating inference outputs to fill a gap;
    showing the real, small dataset and saying exactly what it can and cannot
    support is the honest alternative.
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
        ready = bootstrap_mod.bootstrap(con, settings)
        # A demonstration experiment left over from the retired v37 schema is
        # the application's own data: replace it rather than leave it failed.
        reseed = bootstrap_mod.retire_unsupported(con, BASELINE_TABLE, settings)
        empty = bootstrap_mod.is_empty(con) or reseed

    jobs_mod.get_job_store(database)
    if empty:
        seed_baseline(database, settings)
    else:
        # Warm the co-registered frames' full-range bundles for every ready
        # experiment - canonical first, then translated and local, one scan at
        # a time: cold, each costs seconds on the production table.
        # Background and best-effort.
        from .query import canonical_cache, shower_frames

        names = [r.table_name for r in ready if r.is_ready]
        shower_frames.warm(
            database, settings, names, after=canonical_cache.warm(database, settings, names)
        )

    try:
        yield
    finally:
        jobs_mod.reset_job_store()
        reset_database()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging()

    # Starlette spools every upload larger than 1 MB into a temporary file in
    # TMPDIR before the route copies it to staging. On a host where /tmp is a
    # tmpfs that is RAM, so a 24 GB upload would fill memory; spool to the
    # data volume's staging directory instead (compose also sets TMPDIR).
    tempfile.tempdir = str(settings.staging_dir)
    log.info("Upload spooling directory: %s", tempfile.tempdir)

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
        fingerprint = asset_fingerprint()
        app.mount(
            "/static",
            VersionedStaticFiles(directory=STATIC_DIR, fingerprint=fingerprint),
            name="static",
        )
        log.info("Static asset version: %s", fingerprint)

        @app.get("/", include_in_schema=False)
        async def index() -> HTMLResponse:
            # Stamp every asset URL, and never let the page itself be cached:
            # a stale page would reference a stale stamp and defeat the whole
            # mechanism.
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            html = _ASSET_URL.sub(rf'\1="\2?v={fingerprint}"', html)
            return HTMLResponse(
                html, headers={"Cache-Control": "no-cache, must-revalidate"}
            )

    return app
