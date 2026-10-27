"""Shared fixtures: an ingested database built from the demonstration file."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import seed  # noqa: E402  (tests/ is on sys.path: pytest's rootdir insertion)

#: The two-event demonstration file every booted server seeds from, as the image does.
SEED_FILE = seed.SEED_FILE
#: The same 1,000 rows as CSV, written from SEED_FILE on first use, for the tests of
#: the CSV reader (header checks, compressed CSV, CSV against Parquet).
SEED_CSV = seed.csv_copy()

#: A small cut of the production file with split cells, 'A+B' hits, an
#: overlap-100 event and an event without shower A - the cases the 2-event
#: demonstration file cannot exercise. Built by tests/make_all_models_fixture.py
#: from ingest/hits_all_models.parquet and not committed; the tests that need it
#: skip without it.
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
    "CALOSRV_MODEL_DIR",
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
        if {"client", "live_server", "synthetic_client", "auto_client", "single_client",
            "physics_live_server", "xgb_client", "xgb_boot"}
        & set(getattr(item, "fixturenames", ()))
    ]
    booted_ids = {id(item) for item in booted}
    items[:] = booted + [item for item in items if id(item) not in booted_ids]


@pytest.fixture(scope="session")
def ingested(tmp_path_factory):
    """Ingest the demonstration CSV once into a throwaway database."""
    if not SEED_FILE.is_file():
        pytest.skip(f"Demonstration file not present at {SEED_FILE}")

    data_dir = tmp_path_factory.mktemp("calosrv-data")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_FILE)

    from calosrv.config import load_settings
    from calosrv.db.connection import get_database, reset_database
    from calosrv.db.bootstrap import bootstrap
    from calosrv.ingest import pipeline

    settings = load_settings()
    database = get_database(settings)

    with database.write_lock() as con:
        bootstrap(con, settings)
        outcome = pipeline.run_ingest(con, settings, TABLE, SEED_FILE)
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

    if not SEED_FILE.is_file():
        pytest.skip("Demonstration file not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()

    data_dir = tmp_path_factory.mktemp("api-data")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_FILE)

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

    if not synthetic_all_models.TEMPLATE_FILE.is_file():
        pytest.skip("Demonstration file not present")

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


#: The experiments the ``single_client`` server holds besides the baseline.
SINGLE_HITS_TABLE = "single_hits"
SINGLE_EVENTS_TABLE = "single_events"
BASELINE_TABLE = "experiment_baseline"


@pytest.fixture(scope="module")
def single_client(tmp_path_factory):
    """A server holding all three kinds: the two-shower baseline, single-shower hits, an aggregate.

    The baseline is seeded as in ``client``; the single-shower experiments
    are ``synthetic_single_shower``'s files, ingested through the app's own
    database under :data:`SINGLE_HITS_TABLE` and :data:`SINGLE_EVENTS_TABLE`.
    """
    import os
    import time

    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest import pipeline
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    import synthetic_single_shower

    if not SEED_FILE.is_file():
        pytest.skip("Demonstration file not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()

    data_dir = tmp_path_factory.mktemp("single-data")
    hits_csv, events_csv = data_dir / "single_hits.csv", data_dir / "single_events.csv"
    synthetic_single_shower.write(hits_csv)
    synthetic_single_shower.write_aggregated(hits_csv, events_csv)
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_FILE)

    app = create_app(load_settings())
    with TestClient(app) as test_client:
        for _ in range(120):
            payload = test_client.get("/api/experiments").json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
            time.sleep(0.25)
        database = app.state.database
        with database.write_lock() as con:
            for name, source in ((SINGLE_HITS_TABLE, hits_csv), (SINGLE_EVENTS_TABLE, events_csv)):
                result = pipeline.run_ingest(con, database.settings, name, source)
                assert result.ok, result.warnings
        yield test_client

    reset_database()
    reset_job_store()
    reset_cache()


# ------------------------------------------------- the XGBoost model analysis --
#
# Small aggregate experiments named as the producer names its files, and tiny
# regressors trained in-test with the notebooks' objective and feature names,
# saved in the models folder's layout. Nothing is a measurement: the fixtures
# test the pairing, the job, the tables and the routes, and the reproduction of
# the notebooks' computations on the same arrays.

#: The synthetic aggregate's momentum bins and their populations: both classes of
#: the 2 GeV threshold, and bins at every low-N rung of the E2 view.
XGB_BINS: tuple[int, ...] = (0, 1, 2, 3, 5, 7, 10, 12, 15, 19)
XGB_COUNTS: tuple[int, ...] = (60, 60, 2, 7, 15, 20, 120, 1, 14, 8)

#: The drop-folder files of ``xgb_client``. Electron seed 1 pairs and is analysed;
#: muon seed 1 pairs with an angle model that needs a feature the table lacks;
#: proton seed 2 has no models; pion seed 1 pairs but holds too few events, so its
#: analysis fails; the plain name pairs with nothing.
XGB_SOURCE = "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv"
XGB_MISSING_FEATURE_SOURCE = "muon_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv"
XGB_NO_MODELS_SOURCE = "proton_standalone_N100000_M0_20GeV_reg_balanced_aggr_s2_v3.csv"
XGB_FAILING_SOURCE = "pion_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv"
XGB_UNNAMED_SOURCE = "aggregate_events.csv"

def _xgb_features() -> tuple[str, ...]:
    """The 52 v3 features in the shipped models' order."""
    from calosrv.db import ddl

    return ("num_hits",
            *(f + s for s in ("", "_trans", "_local") for f in ddl.CORE_FEATURES),
            *(d + s for s in ("", "_trans", "_local") for d in ("numerical_density", "energy_density")))


def xgb_table(source: str) -> str:
    """The experiment name the drop folder gives ``source``."""
    from calosrv.db import naming

    return naming.derive_experiment_name(Path(source).stem)


def train_xgb_models(aggregate: Path, folder: Path, species: str, seed: int = 1,
                     extra_feature: str | None = None) -> dict[str, Path]:
    """Two tiny regressors on the notebook's 80 % split, saved as ``xgboost_<species>/...``.

    The notebook's objective, random_state and labels (momentum; angle as
    ``[incoming_phi, incoming_theta]``), with 20 trees of depth 4 so they fit
    in a moment. ``extra_feature`` trains the angle model on one column more,
    which the event table does not have.
    """
    import pandas as pd
    import xgboost as xgb
    from sklearn.model_selection import train_test_split

    frame = pd.read_csv(aggregate, float_precision="round_trip")
    features = list(_xgb_features())
    train, _ = train_test_split(frame, test_size=0.2, random_state=42)
    out = {}
    target = folder / f"xgboost_{species}"
    target.mkdir(parents=True, exist_ok=True)
    for task, labels in (("momentum", ["incoming_momentum"]),
                         ("angle", ["incoming_phi", "incoming_theta"])):
        names = features + ([extra_feature] if extra_feature and task == "angle" else [])
        x = train[features].copy()
        if extra_feature and task == "angle":
            x[extra_feature] = 0.5
        regressor = xgb.XGBRegressor(objective="reg:squarederror", random_state=42,
                                     n_estimators=20, learning_rate=0.3, max_depth=4, n_jobs=2)
        regressor.fit(x[names], train[labels])
        path = target / f"standalone_{task}_s{seed}_model.json"
        regressor.save_model(str(path))
        out[task] = path
    return out


@pytest.fixture(scope="session")
def xgb_sources(tmp_path_factory):
    """The aggregates and the models folder every XGBoost test reads (built once, read-only)."""
    import shutil

    import synthetic_single_shower

    if not SEED_FILE.is_file():
        pytest.skip("Demonstration file not present")
    root = tmp_path_factory.mktemp("xgb-sources")
    hits = root / "hits.csv"
    synthetic_single_shower.write(hits, counts=XGB_COUNTS, bins=XGB_BINS)
    aggregates = root / "aggregates"
    aggregates.mkdir()
    electron = aggregates / XGB_SOURCE
    synthetic_single_shower.write_aggregated(hits, electron)
    for name in (XGB_MISSING_FEATURE_SOURCE, XGB_NO_MODELS_SOURCE, XGB_UNNAMED_SOURCE):
        shutil.copyfile(electron, aggregates / name)
    lines = electron.read_text(encoding="utf-8").splitlines()
    (aggregates / XGB_FAILING_SOURCE).write_text("\n".join(lines[:7]) + "\n", encoding="utf-8")
    models = root / "models"
    paths = train_xgb_models(electron, models, "electron")
    train_xgb_models(electron, models, "muon", extra_feature="bogus_feature")
    train_xgb_models(electron, models, "pion")
    (models / "xgboost_electron" / "README.txt").write_text("not a model\n", encoding="utf-8")
    (models / "xgboost_electron" / "standalone_energy_s1_model.json").write_text("{}\n")
    return {"root": root, "aggregates": aggregates, "electron": electron, "models": models,
            "electron_models": paths, "features": _xgb_features()}


def wait_for_model_runs(client, names, timeout_s: float = 240.0) -> dict:
    """Poll the Admin Settings list until every named experiment's analysis has settled."""
    import time

    settled = ("done", "failed", "unpaired", "stale")
    deadline = time.monotonic() + timeout_s
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get("/api/admin/model-runs").json()
        states = {r["table_name"]: r["status"] for r in payload["runs"]}
        if all(states.get(n) in settled for n in names):
            return payload
        time.sleep(0.2)
    raise AssertionError(f"model analyses did not settle: {payload.get('runs')}")


@contextlib.contextmanager
def booted_app(env: dict[str, str], wait_ready: int = 1):
    """A server booted with ``env``, every process-wide singleton reset around it."""
    import time

    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.modelruns.jobs import reset_model_runs
    from calosrv.query.cache import reset_cache

    def reset() -> None:
        reset_database()
        reset_job_store()
        reset_model_runs()
        reset_cache()

    reset()
    clean_boot_env()
    os.environ.update({"DUCKDB_MEMORY_GB": "2", "CALOSRV_SEED_CSV": str(SEED_FILE),
                       "CALOSRV_AUTO_INGEST_SETTLE_S": "0", **env})
    try:
        with TestClient(create_app(load_settings())) as test_client:
            for _ in range(480):
                listed = test_client.get("/api/experiments").json()["experiments"]
                busy = [e for e in listed if e["status"] not in ("ready", "failed")]
                if len(listed) >= wait_ready and not busy:
                    break
                time.sleep(0.25)
            yield test_client
    finally:
        reset()
        clean_boot_env()


#: How many experiments ``xgb_client`` holds: the baseline and five aggregates.
XGB_CLIENT_EXPERIMENTS = 6


@pytest.fixture(scope="module")
def xgb_client(tmp_path_factory, xgb_sources):
    """A server holding the two-shower baseline and five aggregates, analysed where they pair.

    The aggregates arrive through the drop folder, so the whole lifecycle runs:
    the ingest worker builds each, the queue hook hands the paired ones to the
    model-run worker, and the fixture waits until every analysis has settled.
    """
    import shutil

    data_dir = tmp_path_factory.mktemp("xgb-data")
    drop = tmp_path_factory.mktemp("xgb-drop")
    for source in xgb_sources["aggregates"].iterdir():
        shutil.copyfile(source, drop / source.name)
    env = {"CALOSRV_DATA_DIR": str(data_dir), "CALOSRV_AUTO_INGEST_DIR": str(drop),
           "CALOSRV_MODEL_DIR": str(xgb_sources["models"])}
    with booted_app(env, wait_ready=XGB_CLIENT_EXPERIMENTS) as test_client:
        wait_for_model_runs(test_client, [xgb_table(XGB_SOURCE), xgb_table(XGB_FAILING_SOURCE)])
        yield test_client


@pytest.fixture
def xgb_boot():
    """:func:`booted_app`, for a test that boots, stops and boots a server again itself."""
    return booted_app


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

    if not SEED_FILE.is_file():
        pytest.skip("Demonstration file not present")

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
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_FILE)

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


#: The two-shower copy the ``physics_live_server`` marks as built by an earlier
#: release, so the cards that need the newer derived tables are shut.
STALE_TWO_TABLE = "stale_two"


@pytest.fixture(scope="module")
def physics_live_server(tmp_path_factory):
    """The real app on a real port, holding every kind the Physics page draws.

    Seeded like ``live_server`` (the two-shower baseline), then given
    ``synthetic_single_shower``'s two files as in ``single_client`` - the
    single-shower hits (:data:`SINGLE_HITS_TABLE`) and the event-level
    aggregate (:data:`SINGLE_EVENTS_TABLE`) - and a second ingest of the
    demonstration CSV whose registry row claims derived tables v1
    (:data:`STALE_TWO_TABLE`), so its profile cards are shut with the server's
    rebuild notice. A separate server from ``live_server``: the existing
    browser modules keep their one-experiment page.
    """
    import threading
    import time

    playwright = pytest.importorskip("playwright.sync_api")
    import httpx
    import uvicorn

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest import pipeline
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    import synthetic_single_shower

    if not SEED_FILE.is_file():
        pytest.skip("Demonstration file not present")

    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()
    data_dir = tmp_path_factory.mktemp("physics-browser-data")
    hits_csv, events_csv = data_dir / "single_hits.csv", data_dir / "single_events.csv"
    synthetic_single_shower.write(hits_csv)
    synthetic_single_shower.write_aggregated(hits_csv, events_csv)
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_FILE)

    app = create_app(load_settings())
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

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

    database = app.state.database
    with database.write_lock() as con:
        for name, source in ((SINGLE_HITS_TABLE, hits_csv), (SINGLE_EVENTS_TABLE, events_csv),
                             (STALE_TWO_TABLE, SEED_FILE)):
            result = pipeline.run_ingest(con, database.settings, name, source)
            assert result.ok, result.warnings
        # Built by "an earlier release": the gates read the registry's version.
        con.execute('UPDATE "experiment" SET derived_version = 1 WHERE table_name = ?', [STALE_TWO_TABLE])

    yield {"base": base, "playwright": playwright}

    server.should_exit = True
    thread.join(timeout=10)
    reset_database()
    reset_job_store()
    reset_cache()
    clean_boot_env()
