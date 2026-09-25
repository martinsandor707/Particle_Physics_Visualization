"""Regenerate the laboratory-frame golden snapshot.

Shared code (``NativeBundle.axis``, ``centroids``, ``panels.shower_axes``, the
projection query) is touched by every new frame and schema. This snapshot pins
the lab-frame output on the demonstration dataset - density panels, centroids
and shower axes for ``coord_system=lab, model=segmentation, channel=density`` -
so ``tests/test_golden_lab.py`` can assert that none of it moved. Run it only
when the lab output is *meant* to change::

    .venv/bin/python tests/make_golden.py

The current snapshot was produced in commit 84f65e6 ("Re-baseline the lab
golden on the all-models dummy") by the pre-multi-model code, reading a
29-column file derived verbatim from ``hits_all_models_dummy.csv``; the
multi-model code reproduces it byte for byte from the 99-column file. Ingest
goes through the same ``pipeline.run_ingest`` as the ``ingested`` fixture.
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
SEED_CSV = REPO_ROOT / "hits_all_models_dummy.csv"
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

    os.environ.setdefault("CALOSRV_ALLOW_RAM_STORAGE", "1")

    from calosrv.config import load_settings
    from calosrv.db import registry
    from calosrv.db.bootstrap import bootstrap
    from calosrv.db.connection import get_database, reset_database
    from calosrv.ingest import pipeline

    settings = load_settings()
    database = get_database(settings)
    with database.write_lock() as con:
        bootstrap(con, settings)
        pipeline.run_ingest(con, settings, TABLE, SEED_CSV, build_sample=False)

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
