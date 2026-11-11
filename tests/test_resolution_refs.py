"""The literature reference catalogue equals the record it is made from.

``calosrv/static/js/catalog/resolution_refs.js`` holds the two legend curves of the figure recorded in
``resolution_references.md``. This test parses that file's Curves table, dumps the module through Node, and
asserts the catalogue is deep-frozen, equals the table row by row (key, particle, form, a, b, as printed),
reproduces the printed decimals through ``toFixed(dp)``, evaluates sqrt(a^2/E + b^2), gives the exact
equation and label strings, returns null at E = 0, holds no number the record lacks, and that the record
says the Yellow Report bands and the digitized points were left out.

Skipped when ``node`` is not on the PATH, like the other module tests.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "calosrv" / "static" / "js" / "catalog" / "resolution_refs.js"
RECORD = ROOT / "resolution_references.md"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_DUMP = r"""
const [url] = JSON.parse(process.argv[1]);
const m = await import(url);
const frozen = (v) => v === null || typeof v !== 'object' || (Object.isFrozen(v) && Object.values(v).every(frozen));
const out = { frozen: {}, data: {}, calls: {} };
for (const [k, v] of Object.entries(m)) {
  if (typeof v === 'function') continue;
  out.frozen[k] = frozen(v); out.data[k] = v;
}
const pi = m.REFERENCE_BY_KEY.pi, e = m.REFERENCE_BY_KEY.e;
out.calls.values = [pi, e].map((r) => [1, 4, 25, 80].map((E) => m.referenceValue(r, E)));
out.calls.equation = [pi, e].map(m.referenceEquation);
out.calls.label = [pi, e].map(m.referenceLabel);
out.calls.bad = [m.referenceValue(pi, 0), m.referenceValue(pi, -1), m.referenceValue(pi, NaN),
                 m.referenceValue(pi, Infinity), m.referenceValue(null, 4)];
out.calls.of = [m.referenceOf('pi') === pi, m.referenceOf('x'), m.referenceOf('toString')];
out.calls.toFixed = [pi, e].map((r) => [r.a.toFixed(r.dp.a), r.b.toFixed(r.dp.b)]);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def dump() -> dict:
    done = subprocess.run([NODE, "--input-type=module", "-e", _DUMP, json.dumps([MODULE.as_uri()])],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def record() -> str:
    return RECORD.read_text(encoding="utf-8")


def _rows(text: str) -> list[list[str]]:
    section = text.split("## Curves", 1)[1]
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("|")]
    return [r for r in rows[2:]]  # header and rule


def test_catalogue_is_deep_frozen(dump):
    assert all(dump["frozen"].values()), dump["frozen"]
    assert set(dump["data"]) == {"REFERENCE_SOURCE", "RESOLUTION_REFERENCES", "REFERENCE_KEYS",
                                 "REFERENCE_BY_KEY"}


def test_rows_equal_the_record(dump, record):
    rows = _rows(record)
    refs = dump["data"]["RESOLUTION_REFERENCES"]
    assert len(rows) == len(refs) == 2
    for row, ref in zip(rows, refs):
        key, particle, form, a, b, printed = row
        assert (ref["key"], ref["particle"], ref["form"]) == (key, particle, form)
        assert ref["a"] == float(a) and ref["b"] == float(b)
        assert ref["printed"] == printed
        assert ref["interval"] is None
    assert dump["data"]["REFERENCE_KEYS"] == [r["key"] for r in refs] == ["pi", "e"]
    assert dump["data"]["REFERENCE_BY_KEY"] == {r["key"]: r for r in refs}


def test_printed_decimals_reproduce_the_tokens(dump, record):
    tokens = [t for row in _rows(record) for t in row[3:5]]
    assert tokens == ["27.2", "1.0", "14.0", "0.4"]
    assert [t for pair in dump["calls"]["toFixed"] for t in pair] == tokens


def test_reference_value(dump):
    for (a, b), got in zip([(27.2, 1.0), (14.0, 0.4)], dump["calls"]["values"]):
        for energy, value in zip([1, 4, 25, 80], got):
            assert value == pytest.approx(math.sqrt(a * a / energy + b * b), rel=1e-12)
    assert dump["calls"]["bad"] == [None] * 5


def test_equation_label_and_lookup(dump):
    assert dump["calls"]["equation"] == ["σ/E = 27.2%/√E ⊕ 1.0%",
                                         "σ/E = 14.0%/√E ⊕ 0.4%"]
    assert dump["calls"]["label"] == ["π± 27.2/√E ⊕ 1.0", "e± 14.0/√E ⊕ 0.4"]
    assert dump["calls"]["of"] == [True, None, None]
    for s in dump["calls"]["equation"] + dump["calls"]["label"]:
        assert "-" not in s and "−" not in s


def test_source_scope(dump):
    src = dump["data"]["REFERENCE_SOURCE"]
    assert src["interval"] is None and src["supplied"] == "2026-11-10" and src["by"] == "Martin"
    assert src["record"] == RECORD.name


def test_record_says_what_was_left_out(record):
    assert "Yellow Report" in record and "digitized" in record and "Left out on purpose" in record


def test_catalogue_holds_no_number_the_record_lacks(dump, record):
    allowed = {float(t) for row in _rows(record) for t in row[3:5]}
    found: list[float] = []

    def walk(v, key=""):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            if key not in ("dp",):
                found.append(float(v))
        elif isinstance(v, dict):
            for k, c in v.items():
                walk(c, "dp" if k == "dp" else k)
        elif isinstance(v, list):
            for c in v:
                walk(c, key)

    walk(dump["data"]["RESOLUTION_REFERENCES"])
    # the dp counts are integers inside `dp`; the date and prose are strings, never numbers
    assert found and set(found) <= allowed
    walk_src = dump["data"]["REFERENCE_SOURCE"]
    assert all(not isinstance(v, (int, float)) for v in walk_src.values())
