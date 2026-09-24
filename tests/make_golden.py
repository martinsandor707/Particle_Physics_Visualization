"""Regenerate the laboratory-frame golden snapshot.

The canonical-frame work touches shared code (``NativeBundle.axis``,
``centroids``, ``panels.shower_axes``). This snapshot pins the lab-frame output
on the demonstration dataset so ``tests/test_golden_lab.py`` can assert that
none of it moved. Run **before** such a refactor to capture the reference::

    .venv/bin/python tests/make_golden.py

Ingest mirrors the ``ingested`` fixture in ``conftest.py`` exactly.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

GOLDEN = Path(__file__).resolve().parent / "golden" / "lab_demo.json"
SEED_CSV = REPO_ROOT / "hits_with_gradcam_dummy.csv"
TABLE = "golden_experiment"


def lab_snapshot(con, record) -> dict:
    """Everything the lab path renders for the full selection of ``record``."""
    from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE, plan_resolution
    from calosrv.query import centroids, filters, panels, projections

    spec = filters.build(record)
    bundle = projections.fetch_native(con, record, spec)
    out = {
        "native": panels.render_all(
            bundle, plan_resolution(record.lattice, MODE_NATIVE, 150),
            global_vmax=record.cell_e_max,
        ),
        "continuous_150": panels.render_all(
            bundle, plan_resolution(record.lattice, MODE_CONTINUOUS, 150),
            global_vmax=record.cell_e_max,
        ),
        "centroids": {k: v.as_dict() for k, v in centroids.compute(bundle).items()},
        "shower_axes": {name: panels.shower_axes(bundle, name) for name in ("yz", "xz")},
    }
    return json.loads(json.dumps(out))  # normalise tuples / numpy scalars


def main() -> int:
    if not SEED_CSV.is_file():
        print(f"missing {SEED_CSV}", file=sys.stderr)
        return 1
    data_dir = Path(tempfile.mkdtemp(prefix="calosrv-golden-"))
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)

    from calosrv.config import load_settings
    from calosrv.db import naming, registry
    from calosrv.db.bootstrap import bootstrap
    from calosrv.db.connection import get_database, reset_database
    from calosrv.ingest import derive_events, derive_proj, lattice_fit, load

    settings = load_settings()
    database = get_database(settings)
    with database.write_lock() as con:
        bootstrap(con)
        record = registry.ExperimentRecord(table_name=TABLE)
        record.status = registry.STATUS_INGESTING
        registry.upsert(con, record)
        n_hits = load.load_csv(con, TABLE, SEED_CSV)
        lattice = lattice_fit.measure_lattice(con, naming.hit_table(TABLE))
        bounds = lattice_fit.measure_bounds(con, naming.hit_table(TABLE))
        record.lattice = lattice
        registry.upsert(con, record)
        derive_proj.build(con, TABLE, lattice)
        n_events = derive_events.build(con, TABLE)
        cell_max, cell_p999 = derive_proj.measure_color_anchors(con, TABLE, lattice.slab_iz)
        record.n_hits, record.n_events = n_hits, n_events
        record.n_events_no_d = bounds["n_events_no_d"]
        record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
        record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
        record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
        record.overlaps = bounds["overlaps"]
        record.cell_e_max, record.cell_e_p999 = cell_max, cell_p999
        record.status = registry.STATUS_READY
        registry.upsert(con, record)

    with database.read_cursor() as con:
        record = registry.require_ready(con, TABLE)
        snapshot = lab_snapshot(con, record)
    reset_database()

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(snapshot, sort_keys=True, indent=1), encoding="utf-8")
    print(f"wrote {GOLDEN} ({GOLDEN.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
