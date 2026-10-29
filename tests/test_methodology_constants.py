"""Every number the Methodology article quotes equals the code it describes.

The article (``calosrv/static/js/methodology/``) never types one of the
dashboard's gates, widths, windows or codes: it reads them from
``methodology/constants.js``, whose every entry names its source. This test
resolves each source against the live code - a Python expression in its
module, a JavaScript expression over a module's exports under Node, or a
snippet of prose the code states the fact in - and fails when the article's
number and the code's disagree, so a changed rule cannot leave the article
behind.

Skipped when ``node`` is not on the PATH, like the other module tests.
"""

from __future__ import annotations

import importlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_DUMP = r"""
const [url] = JSON.parse(process.argv[1]);
const { CONSTANTS, C } = await import(url);
console.log(JSON.stringify({ constants: CONSTANTS, values: C }));
"""

_EVAL_JS = r"""
const [base, items] = JSON.parse(process.argv[1]);
const out = {};
for (const [name, path, expr] of items) {
  const module = await import(new URL(path, base).href);
  const keys = Object.keys(module);
  out[name] = Function(...keys, `return (${expr});`)(...keys.map((k) => module[k]));
}
console.log(JSON.stringify(out));
"""


def _node(script: str, args) -> dict:
    done = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args)],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def ledger() -> dict:
    return _node(_DUMP, [(JS / "methodology" / "constants.js").as_uri()])


def _same(expected, actual) -> bool:
    if isinstance(expected, list) or isinstance(actual, (list, tuple)):
        return (isinstance(actual, (list, tuple)) and len(expected) == len(actual)
                and all(_same(e, a) for e, a in zip(expected, actual)))
    if isinstance(expected, str) or isinstance(actual, str):
        return expected == actual
    return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-12)


def _spelt(value) -> str:
    """A number as prose writes it: 212, not 212.0."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _split(source: str) -> tuple[str, str, str]:
    kind, _, rest = source.partition(":")
    where, _, expr = rest.partition(":")
    return kind, where, expr


def test_every_entry_names_a_source_and_a_meaning(ledger):
    for name, entry in ledger["constants"].items():
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", name), name
        kind, where, expr = _split(entry["source"])
        assert kind in ("py", "js", "text") and where and expr, (name, entry["source"])
        assert entry["meaning"].strip(), name
        assert ledger["values"][name] == entry["value"], name


def test_the_python_sources_agree(ledger):
    checked = 0
    for name, entry in ledger["constants"].items():
        kind, module, expr = _split(entry["source"])
        if kind != "py":
            continue
        actual = eval(expr, vars(importlib.import_module(module)))  # noqa: S307 - the article's own sources
        assert _same(entry["value"], actual), f"{name}: the article says {entry['value']!r}, {module} has {actual!r}"
        checked += 1
    assert checked > 50


def test_the_javascript_sources_agree(ledger):
    items = [(name, where, expr) for name, entry in ledger["constants"].items()
             for kind, where, expr in [_split(entry["source"])] if kind == "js"]
    assert items
    actual = _node(_EVAL_JS, [JS.as_uri() + "/", items])
    for name, *_ in items:
        expected = ledger["constants"][name]["value"]
        assert _same(expected, actual[name]), f"{name}: the article says {expected!r}, the module has {actual[name]!r}"


def test_the_prose_sources_state_the_value(ledger):
    for name, entry in ledger["constants"].items():
        kind, path, snippet = _split(entry["source"])
        if kind != "text":
            continue
        text = (ROOT / path).read_text(encoding="utf-8")
        assert snippet in text, f"{name}: {path} no longer says {snippet!r}"
        values = entry["value"] if isinstance(entry["value"], list) else [entry["value"]]
        for value in values:
            assert _spelt(value) in snippet, f"{name}: {snippet!r} does not state {value!r}"
