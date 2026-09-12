"""Shared fixtures: an ingested database built from the demonstration CSV."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SEED_CSV = REPO_ROOT / "hits_with_gradcam_dummy.csv"

TABLE = "test_experiment"


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
    from calosrv.db import registry
    from calosrv.db.bootstrap import bootstrap
    from calosrv.ingest import derive_events, derive_proj, lattice_fit, load, verify

    settings = load_settings()
    database = get_database(settings)

    with database.write_lock() as con:
        bootstrap(con)
        record = registry.ExperimentRecord(table_name=TABLE)
        record.status = registry.STATUS_INGESTING
        registry.upsert(con, record)

        n_hits = load.load_csv(con, TABLE, SEED_CSV)
        from calosrv.db import naming

        lattice = lattice_fit.measure_lattice(con, naming.hit_table(TABLE))
        bounds = lattice_fit.measure_bounds(con, naming.hit_table(TABLE))
        record.lattice = lattice
        registry.upsert(con, record)

        derive_proj.build(con, TABLE, lattice)
        n_events = derive_events.build(con, TABLE)
        cell_max, cell_p999 = derive_proj.measure_color_anchors(
            con, TABLE, lattice.slab_iz
        )
        derive_proj.build_sample(con, TABLE, 10.0)
        result = verify.verify(con, TABLE, SEED_CSV)

        record.n_hits = n_hits
        record.n_events = n_events
        record.n_events_no_d = bounds["n_events_no_d"]
        record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
        record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
        record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
        record.overlaps = bounds["overlaps"]
        record.cell_e_max = cell_max
        record.cell_e_p999 = cell_p999
        record.has_sample = True
        record.status = registry.STATUS_READY
        registry.upsert(con, record)

    yield {
        "database": database,
        "settings": settings,
        "table": TABLE,
        "verification": result,
        "n_hits": n_hits,
        "n_events": n_events,
    }

    reset_database()


@pytest.fixture
def record(ingested):
    from calosrv.db import registry

    with ingested["database"].read_cursor() as con:
        return registry.require_ready(con, ingested["table"])


@pytest.fixture
def cursor(ingested):
    with ingested["database"].read_cursor() as con:
        yield con
