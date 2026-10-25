"""The two-shower Page 1 responses are pinned while the shared views change.

Teaching the lab, per-shower translated and local views, the window axis and
the Event Inspector one shower per event rewrote code every two-shower
response runs through. ``tests/golden/two_shower_api.json`` holds the served
JSON of those views on the demonstration dataset (``tests/make_golden_two_shower.py``,
generated from 747baba and reproduced by this tree, apart from the deliberate
changes it lists), so any other change to a two-shower response fails here
with the path that moved. Timing, cache counters and measured byte counts are
masked; floats are compared exactly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "two_shower_api.json"


def _generator():
    """Load the generator by file path: ``tests/`` is not a package."""
    path = Path(__file__).resolve().with_name("make_golden_two_shower.py")
    spec = importlib.util.spec_from_file_location("calosrv_make_golden_two_shower", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _walk(expected, actual, path=""):
    """Yield the paths where two JSON trees differ, comparing floats exactly."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            yield f"{path}: {expected!r} != {actual!r}"
            return
        if set(expected) != set(actual):
            yield f"{path}: keys -{sorted(set(expected) - set(actual))} +{sorted(set(actual) - set(expected))}"
        for key in expected.keys() & actual.keys():
            yield from _walk(expected[key], actual[key], f"{path}/{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            yield f"{path}: length {len(expected)} != {len(actual) if isinstance(actual, list) else actual!r}"
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            yield from _walk(e, a, f"{path}[{i}]")
    elif type(expected) is not type(actual) or expected != actual:
        yield f"{path}:\n    golden  {expected!r}\n    served  {actual!r}"


@pytest.fixture(scope="module")
def served(client):
    if not GOLDEN.is_file():
        pytest.skip("two-shower golden not generated; run tests/make_golden_two_shower.py")
    return _generator().snapshot(client)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_the_snapshot_covers_every_request(served, golden):
    assert sorted(served) == sorted(golden)
    assert all(entry["status"] == 200 for entry in served.values())


def test_two_shower_responses_match_the_golden_snapshot(served, golden):
    differences = []
    for key in sorted(golden.keys() & served.keys()):
        differences.extend(f"{key}{line}" for line in _walk(golden[key], served[key]))
    assert not differences, (
        f"{len(differences)} two-shower value(s) moved; if the change is deliberate, regenerate "
        "with tests/make_golden_two_shower.py and name it in its DELIBERATE list:\n"
        + "\n".join(differences[:30])
    )


def test_the_masking_hides_only_jitter():
    """Timing and cache counters are masked, and only the digits of a measured byte count."""
    mask = _generator().mask
    body = mask({"meta": {"query_ms": 3.2, "total_ms": 4.0, "cached": True, "pitch_mm": 20.0,
                          "notes": {"cache": {"hits": 3}}},
                 "notes": ["The response measured 101,234 bytes against the 100,000-byte contract."]})
    assert body["meta"] == {"query_ms": "<masked>", "total_ms": "<masked>", "cached": "<masked>",
                            "pitch_mm": 20.0, "notes": {"cache": "<masked>"}}
    assert body["notes"] == ["The response measured # bytes against the #-byte contract."]
