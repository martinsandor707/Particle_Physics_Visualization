"""The laboratory-frame output is pinned while shared code is refactored.

The canonical-frame feature makes ``centroids`` and ``panels.shower_axes`` read
axis coordinates through ``bundle.axis(name)`` instead of the lattice directly.
That must be a pure refactor for the lab frame: every rendered panel, centroid
and axis point on the demonstration dataset has to come out identical to the
snapshot captured before the change (``tests/make_golden.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "lab_demo.json"


def _walk(expected, actual, path=""):
    """Yield the paths where two JSON trees differ, comparing floats exactly."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            yield f"{path}: keys {sorted(expected) if isinstance(expected, dict) else expected} != {sorted(actual) if isinstance(actual, dict) else actual}"
            return
        for key in expected:
            yield from _walk(expected[key], actual[key], f"{path}/{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            yield f"{path}: length {len(expected)} != {len(actual) if isinstance(actual, list) else actual}"
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            yield from _walk(e, a, f"{path}[{i}]")
    elif expected != actual:
        yield f"{path}: {expected!r} != {actual!r}"


def _lab_snapshot():
    """Load the generator by file path: ``tests/`` is not a package."""
    import importlib.util

    path = Path(__file__).resolve().with_name("make_golden.py")
    spec = importlib.util.spec_from_file_location("calosrv_make_golden", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.lab_snapshot


def test_lab_frame_output_matches_the_golden_snapshot(cursor, record):
    if not GOLDEN.is_file():
        pytest.skip("golden snapshot not generated; run tests/make_golden.py")
    lab_snapshot = _lab_snapshot()

    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = lab_snapshot(cursor, record)

    differences = list(_walk(expected, actual))
    assert not differences, "lab-frame output moved:\n" + "\n".join(differences[:20])
