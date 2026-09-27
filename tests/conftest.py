"""Shared fixtures: an ingested database built from the demonstration CSV."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SEED_CSV = REPO_ROOT / "hits_all_models_dummy.csv"

#: A small cut of the production file with split cells, 'A+B' hits, an
#: overlap-100 event and an event without shower A - the cases the 2-event
#: demonstration file cannot exercise. Built by tests/make_all_models_fixture.py
#: and, like every CSV, not committed; the tests that need it skip without it.
FIXTURE_CSV = REPO_ROOT / "hits_all_models_fixture.csv"

# The demonstration and fixture databases are a few megabytes, so the default
# pytest temporary directory (often a tmpfs) is acceptable for them. The server
# refuses RAM-backed storage otherwise; this is the documented test opt-out.
os.environ.setdefault("CALOSRV_ALLOW_RAM_STORAGE", "1")

TABLE = "test_experiment"

#: Variables a booted server reads that the fixtures below set or must not
#: inherit. The fixtures write os.environ directly, so without this a drop
#: folder or a default set for one booted module would reach the next.
_BOOT_ENV = (
    "CALOSRV_AUTO_INGEST_DIR", "CALOSRV_AUTO_INGEST_SETTLE_S", "CALOSRV_CONFIG_PATH",
    "CALOSRV_DEFAULT_DATASET", "CALOSRV_DEFAULT_COORD_SYSTEM", "CALOSRV_DEFAULT_MODEL",
    "CALOSRV_DEFAULT_CHANNEL", "CALOSRV_DEFAULT_DISPLAY_MODE", "CALOSRV_DEFAULT_RHO_NORM",
)


def clean_boot_env() -> None:
    """Forget every boot-time variable a previous booted fixture may have set."""
    for name in _BOOT_ENV:
        os.environ.pop(name, None)


def pytest_collection_modifyitems(session, config, items):
    """Run every booted-server test before the ingested-database tests.

    The `client` fixture boots the app against an empty database and, because
    the DuckDB connection is a process-wide singleton, calls `reset_database()`
    on setup and teardown. The session-scoped `ingested` fixture holds that
    same singleton, so a `client` module running *after* the first `ingested`
    test would close the connection under every later query test. The suite
    used to rely on alphabetical module order to avoid this; ordering by
    fixture makes it explicit and lets query-level test modules be named freely.
    """
    booted = [
        item for item in items
        if {"client", "live_server", "synthetic_client", "auto_client"}
        & set(getattr(item, "fixturenames", ()))
    ]
    booted_ids = {id(item) for item in booted}
    items[:] = booted + [item for item in items if id(item) not in booted_ids]


@pytest.fixture(scope="session")
def ingested(tmp_path_factory):
    """Ingest the demonstration CSV once into a throwaway database."""
    if not SEED_CSV.is_file():
        pytest.skip(f"Demonstration CSV not present at {SEED_CSV}")

    data_dir = tmp_path_factory.mktemp("calosrv-data")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)

    from calosrv.config import load_settings
    from calosrv.db.connection import get_database, reset_database
    from calosrv.db.bootstrap import bootstrap
    from calosrv.ingest import pipeline

    settings = load_settings()
    database = get_database(settings)

    with database.write_lock() as con:
        bootstrap(con, settings)
        outcome = pipeline.run_ingest(con, settings, TABLE, SEED_CSV)
    result = outcome.verification
    n_hits, n_events = outcome.n_hits, outcome.n_events

    yield {
        "database": database,
        "settings": settings,
        "table": TABLE,
        "verification": result,
        "n_hits": n_hits,
        "n_events": n_events,
    }

    reset_database()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A server booted against an empty database, so seeding is exercised.

    Shared rather than owned by `test_api.py`, because the export-asset tests
    need the same running app to check that the new modules are served and
    their imports rewritten. Two independently booted copies would each call
    `reset_database()` on the singleton the other was still using.
    """
    import os
    import time

    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    if not SEED_CSV.is_file():
        pytest.skip("Demonstration CSV not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()

    data_dir = tmp_path_factory.mktemp("api-data")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)

    with TestClient(create_app(load_settings())) as test_client:
        # Seeding runs on a background worker; wait for it to report ready.
        for _ in range(120):
            payload = test_client.get("/api/experiments").json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
            time.sleep(0.25)
        yield test_client

    reset_database()
    reset_job_store()
    reset_cache()


@pytest.fixture(scope="module")
def synthetic_client(tmp_path_factory):
    """A server seeded from the synthetic low-N file of ``synthetic_all_models``."""
    import os
    import time

    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    import synthetic_all_models

    if not synthetic_all_models.TEMPLATE_CSV.is_file():
        pytest.skip("Demonstration CSV not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()

    data_dir = tmp_path_factory.mktemp("synthetic-data")
    csv_path = data_dir / "hits_all_models_synthetic.csv"
    synthetic_all_models.write(csv_path)
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(csv_path)

    with TestClient(create_app(load_settings())) as test_client:
        for _ in range(240):
            payload = test_client.get("/api/experiments").json()
            if any(e["status"] in ("ready", "failed") for e in payload["experiments"]):
                break
            time.sleep(0.25)
        yield test_client

    reset_database()
    reset_job_store()
    reset_cache()


@pytest.fixture
def record(ingested):
    from calosrv.db import registry

    with ingested["database"].read_cursor() as con:
        return registry.require_ready(con, ingested["table"])


@pytest.fixture
def cursor(ingested):
    with ingested["database"].read_cursor() as con:
        yield con


# ------------------------------------------------------ browser test server --
#
# Shared by the opt-in Chromium tests (``test_browser_*.py``), which gate
# themselves on CALOSRV_BROWSER_TESTS=1.


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """The real app on a real port, seeded from the demonstration CSV."""
    import threading
    import time

    playwright = pytest.importorskip("playwright.sync_api")
    import uvicorn

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    if not SEED_CSV.is_file():
        pytest.skip("Demonstration CSV not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()
    os.environ["CALOSRV_DATA_DIR"] = str(tmp_path_factory.mktemp("browser-data"))
    # An empty drop folder, so the Admin Settings panel's Scan now can be driven.
    drop = tmp_path_factory.mktemp("browser-drop")
    os.environ["CALOSRV_AUTO_INGEST_DIR"] = str(drop)
    os.environ["CALOSRV_AUTO_INGEST_SETTLE_S"] = "0"
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(load_settings()), host="127.0.0.1", port=port, log_level="warning",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import httpx

    base = f"http://127.0.0.1:{port}"
    for _ in range(240):
        try:
            payload = httpx.get(f"{base}/api/experiments", timeout=2).json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
        except Exception:
            pass
        time.sleep(0.25)
    else:
        server.should_exit = True
        pytest.fail("the server never reported a ready experiment")

    yield {"base": base, "playwright": playwright, "drop": drop}

    server.should_exit = True
    thread.join(timeout=10)
    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()
