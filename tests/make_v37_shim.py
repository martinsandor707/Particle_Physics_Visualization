"""Derive the retired 29-column v37 demonstration CSV from the all-models dummy.

Step 0 of the multi-model change. The v37 CSVs were removed from the working
tree, which took the test seed with them; this rebuilds a 29-column file with
the same 1000 hits so that the *current* code can re-baseline the suite and
regenerate ``tests/golden/lab_demo.json`` before anything is refactored. After
the refactor the new code, reading ``hits_all_models_dummy.csv`` directly, must
reproduce that golden byte for byte.

Every field is copied as its original string - no float is ever re-serialised -
so both code paths parse identical text into identical types. The four v37
model columns are taken from the absolute-frame segmentation network, which is
what the v37 file carried:

    gradcam        := segmentation_absolute_gradcam
    gradcam_energy := segmentation_absolute_gradcam_energy
    voxel_fA_pred  := segmentation_absolute_pred
    voxel_fA_true  := segmentation_absolute_true

This script is a step-0 tool and is deleted in the commit that retires v37.

    .venv/bin/python tests/make_v37_shim.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SOURCE = REPO_ROOT / "hits_all_models_dummy.csv"
TARGET = REPO_ROOT / "hits_with_gradcam_dummy.csv"

V37_FROM_ALL_MODELS = {
    "gradcam": "segmentation_absolute_gradcam",
    "gradcam_energy": "segmentation_absolute_gradcam_energy",
    "voxel_fA_pred": "segmentation_absolute_pred",
    "voxel_fA_true": "segmentation_absolute_true",
}

EXPECTED_ROWS = 1000


def main() -> int:
    from calosrv.db.ddl import HIT_COLUMN_NAMES

    if len(HIT_COLUMN_NAMES) != 29:
        print("ddl.HIT_COLUMN_NAMES is no longer the v37 schema; the shim has served its purpose",
              file=sys.stderr)
        return 1
    if not SOURCE.is_file():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1

    with SOURCE.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    index = {name: i for i, name in enumerate(header)}
    sources = [V37_FROM_ALL_MODELS.get(name, name) for name in HIT_COLUMN_NAMES]
    missing = [name for name in sources if name not in index]
    if missing:
        print(f"{SOURCE.name} lacks {missing}", file=sys.stderr)
        return 1
    picks = [index[name] for name in sources]
    out_rows = [[row[i] for i in picks] for row in rows]

    with TARGET.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HIT_COLUMN_NAMES)
        writer.writerows(out_rows)

    # Re-read and compare field by field: the derivation must be lossless text.
    with TARGET.open(newline="", encoding="utf-8") as handle:
        reread = list(csv.reader(handle))
    assert reread[0] == list(HIT_COLUMN_NAMES), "header mismatch"
    assert len(reread) - 1 == len(out_rows) == EXPECTED_ROWS, (
        f"expected {EXPECTED_ROWS} rows, wrote {len(reread) - 1}"
    )
    assert reread[1:] == out_rows, "a field changed on the round trip"
    print(f"wrote {TARGET.name}: {len(out_rows)} rows x {len(HIT_COLUMN_NAMES)} columns "
          f"from {SOURCE.name} (mapping: {V37_FROM_ALL_MODELS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
