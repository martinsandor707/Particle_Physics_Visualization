"""The benchmark catalogue's logic (``static/js/catalog/{formula,gating,select}.js``), run under Node.

Pins:

* ``formula.js``: every PySR formula of ``catalog/benchmarks.js`` parses both in its explicit ``ascii`` form
  and in the report's own implicit syntax (``source``, after ``normaliseReportFormula``), and the two
  evaluate equal at three deterministic points; the grammar's precedence, implicit multiplication, the
  domain (NaN) and the typed ``FormulaSyntaxError``; no ``eval`` and no ``Function``;
* every ``tex`` compiles with ``math.js`` ``texToTree``, and carries the same multiset of numbers as the
  report's ``source``;
* ``gating.js``: the full tier table of brief 3.1 over the 36 models, each rule on synthetic inputs, the
  leak flags, U+2212 in the reasons;
* ``select.js``: every card for every species and ``'all'`` and every task gives a frozen, JSON-serialisable
  payload with ``meta.source == 'catalog'`` and ``filtered is False``; the cards' integrity facts (F1–F10);
  ``curveDomain`` finite, positive and monotone where the formulas are.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "calosrv" / "static" / "js"
CATALOG = JS / "catalog"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MINUS = "\u2212"
HYPHEN_NUMBER = re.compile(r"(?<![\w])-\d")

CARDS = ["distill-pysr", "distill-triangle", "distill-curves", "perf-catalog", "perf-overlap",
         "perf-momentum-bias", "perf-diagnostics"]
SPECIES = ["proton", "muon", "electron", "pion"]
TASKS = ["segmentation", "angle", "energy"]
FRAMES = ["absolute", "trans", "local"]

#: The proton's Hungarian formula variables and the English keys its ascii uses (inferred by B1).
PROTON_VARIABLES = {"voxelszám": "n_voxels", "θ_súlypont": "centroid_theta", "r": "centroid_r"}

#: Brief 3.1's expected tiers, every one of the 36 models.
EXPECTED_TIERS = {
    ("proton", "segmentation", "absolute"): "not-law",
    ("proton", "segmentation", "trans"): "not-law",
    ("proton", "segmentation", "local"): "not-law",
    ("proton", "angle", "absolute"): "unverified",
    ("proton", "angle", "trans"): "not-law",
    ("proton", "angle", "local"): "not-law",
    ("proton", "energy", "absolute"): "law",
    ("proton", "energy", "trans"): "law",
    ("proton", "energy", "local"): "law",
    ("muon", "segmentation", "absolute"): "partial",
    ("muon", "segmentation", "trans"): "partial",
    ("muon", "segmentation", "local"): "partial",
    ("muon", "angle", "absolute"): "law",
    ("muon", "angle", "trans"): "law",
    ("muon", "angle", "local"): "partial",
    ("muon", "energy", "absolute"): "not-law",
    ("muon", "energy", "trans"): "not-law",
    ("muon", "energy", "local"): "not-law",
    ("electron", "segmentation", "absolute"): "not-law",
    ("electron", "segmentation", "trans"): "not-law",
    ("electron", "segmentation", "local"): "partial",
    ("electron", "angle", "absolute"): "law",
    ("electron", "angle", "trans"): "partial",
    ("electron", "angle", "local"): "not-law",
    ("electron", "energy", "absolute"): "law",
    ("electron", "energy", "trans"): "law",
    ("electron", "energy", "local"): "law",
    ("pion", "segmentation", "absolute"): "not-law",
    ("pion", "segmentation", "trans"): "not-law",
    ("pion", "segmentation", "local"): "not-law",
    ("pion", "angle", "absolute"): "law",
    ("pion", "angle", "trans"): "not-law",
    ("pion", "angle", "local"): "not-law",
    ("pion", "energy", "absolute"): "law",
    ("pion", "energy", "trans"): "partial",
    ("pion", "energy", "local"): "partial",
}


def _node(script: str, args=None):
    done = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args or {})],
                          capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _uri(path: Path) -> str:
    return path.as_uri()


IMPORTS = f"""
const F = await import({json.dumps(_uri(CATALOG / 'formula.js'))});
const G = await import({json.dumps(_uri(CATALOG / 'gating.js'))});
const S = await import({json.dumps(_uri(CATALOG / 'select.js'))});
const B = await import({json.dumps(_uri(CATALOG / 'benchmarks.js'))});
const M = await import({json.dumps(_uri(JS / 'math.js'))});
const ARGS = JSON.parse(process.argv[1]);
"""


# ── formula.js ─────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def formulas() -> list:
    """Every formula parsed both ways and evaluated at three points."""
    return _node(IMPORTS + """
const out = [];
for (const d of B.DISTILLATION) {
  const row = { species: d.species, task: d.task, frame: d.frame, absent: d.pysr.absent,
                source: d.pysr.source, ascii: d.pysr.ascii, tex: d.pysr.tex };
  if (!d.pysr.absent) {
    const a = F.parseFormula(d.pysr.ascii);
    const s = F.parseReportFormula(d.pysr.source);
    row.asciiVars = F.variables(a);
    row.sourceVars = F.variables(s);
    row.normalised = F.normaliseReportFormula(d.pysr.source);
    row.points = [];
    for (let k = 0; k < 3; k += 1) {
      const vars = {};
      row.asciiVars.forEach((name, i) => { vars[name] = 0.25 + 0.17 * i + 0.31 * k; });
      const map = ARGS.map;
      const svars = {};
      for (const name of row.sourceVars) svars[name] = vars[map[name] ?? name];
      row.points.push({ ascii: F.evaluate(a, vars), source: F.evaluate(s, svars) });
    }
    try { M.texToTree(d.pysr.tex, { display: true }); row.texOk = true; }
    catch (e) { row.texOk = false; row.texError = String(e && e.message); }
  }
  out.push(row);
}
console.log(JSON.stringify(out));
""", {"map": PROTON_VARIABLES})


def test_every_formula_is_present(formulas):
    assert len(formulas) == 36
    assert sum(1 for f in formulas if not f["absent"]) == 32


def test_every_formula_parses_both_ways_and_agrees(formulas):
    for f in formulas:
        if f["absent"]:
            assert f["ascii"] is None and f["tex"] is None
            continue
        key = (f["species"], f["task"], f["frame"])
        mapped = sorted(PROTON_VARIABLES.get(v, v) for v in f["sourceVars"])
        assert mapped == f["asciiVars"], key
        for p in f["points"]:
            assert p["ascii"] is not None and math.isfinite(p["ascii"]), key
            assert math.isclose(p["ascii"], p["source"], rel_tol=1e-12, abs_tol=1e-15), (key, p)


def test_three_points_are_distinct(formulas):
    """The three points are genuinely different evaluations wherever the formula has a variable."""
    for f in formulas:
        if f["absent"] or not f["asciiVars"]:
            continue
        values = [p["ascii"] for p in f["points"]]
        assert len({round(v, 12) for v in values}) == 3, (f["species"], f["task"], f["frame"], values)


def test_every_tex_compiles(formulas):
    for f in formulas:
        if not f["absent"]:
            assert f["texOk"], (f["species"], f["task"], f["frame"], f.get("texError"))


_TEX_SCI = re.compile(r"(\d+(?:\.\d+)?)\\times\s*10\^\{(-?\d+)\}")
_NUM = re.compile(r"\d+(?:\.\d+)?(?:e[-+]?\d+)?")


def _tex_numbers(tex: str) -> list[float]:
    text = _TEX_SCI.sub(lambda m: f" {m.group(1)}e{m.group(2)} ", tex)
    text = re.sub(r"\\mathrm\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    return sorted(float(t) for t in _NUM.findall(text))


def _source_numbers(normalised: str) -> list[float]:
    text = re.sub(r"(?<![\d.])[^\W\d]\w*", " ", normalised)  # identifiers (any script) out
    return sorted(float(t) for t in _NUM.findall(text))


def test_tex_numbers_equal_source_numbers(formulas):
    for f in formulas:
        if f["absent"]:
            continue
        tex = _tex_numbers(f["tex"])
        src = _source_numbers(f["normalised"])
        assert len(tex) == len(src), (f["species"], f["task"], f["frame"], tex, src)
        for a, b in zip(tex, src):
            assert math.isclose(a, b, rel_tol=1e-12), (f["species"], f["task"], f["frame"], tex, src)


def test_number_extraction_handles_the_scientific_form():
    assert _tex_numbers(r"25.2\,\mathrm{E\_sum}+6.713\times 10^{-7}\,\mathrm{centroid\_r}^{2}+1.947") == \
        sorted([25.2, 6.713e-7, 2.0, 1.947])
    assert _source_numbers("25.2 E_sum+6.713e-7 centroid_r^2+1.947") == sorted([25.2, 6.713e-7, 2.0, 1.947])


def test_grammar():
    cases = [
        ("-2^2", {}, -4.0),
        ("2^3^2", {}, 512.0),
        ("2x y", {"x": 3, "y": 4}, 24.0),
        ("a(b+1)", {"a": 2, "b": 3}, 8.0),
        ("(1+2)(3)", {}, 9.0),
        ("sqrt(4)3", {}, 6.0),
        ("sqrt(4) x", {"x": 5}, 10.0),
        ("8/2x", {"x": 2}, 8.0),
        ("1/2/2", {}, 0.25),
        ("6.713e-7", {}, 6.713e-7),
        ("2e", {"e": 3}, 6.0),
        ("2e+1", {}, 20.0),
        (".5*4", {}, 2.0),
        ("√4", {}, 2.0),
        ("2√x", {"x": 9}, 6.0),
        ("x^(1/2)", {"x": 16}, 4.0),
        ("-x", {"x": 3}, -3.0),
        ("--x", {"x": 3}, 3.0),
        ("2*-x", {"x": 3}, -6.0),
        ("x^-1", {"x": 4}, 0.25),
        ("log(exp(2))", {}, 2.0),
        ("n_hits(0.5+x)", {"n_hits": 2, "x": 0.5}, 2.0),
        ("θ_súlypont", {"θ_súlypont": 0.3}, 0.3),
    ]
    out = _node(IMPORTS + """
console.log(JSON.stringify(ARGS.cases.map(([t, v]) => F.evaluate(F.parseFormula(t), v))));
""", {"cases": [[t, v] for t, v, _ in cases]})
    for (text, _, want), got in zip(cases, out):
        assert got is not None and math.isclose(got, want, rel_tol=1e-12), (text, got, want)


def test_normalise_report_formula():
    out = _node(IMPORTS + """
console.log(JSON.stringify(ARGS.map((t) => F.normaliseReportFormula(t))));
""", ["p ≈ 29,5 · E_sum + 0,0024 · r", "0,6973 exp(-2,4411 n_hits²)", "6,713e-7 x", "1 − 2"])
    assert out == ["29.5 * E_sum + 0.0024 * r", "0.6973 exp(-2.4411 n_hits^2)", "6.713e-7 x", "1 - 2"]


def test_domain_and_unbound_variables():
    out = _node(IMPORTS + """
const ev = (t, v = {}) => F.evaluate(F.parseFormula(t), v);
let unbound = null;
try { ev('x + 1'); } catch (e) { unbound = e.name; }
console.log(JSON.stringify({
  sqrtNeg: Number.isNaN(ev('sqrt(-1)')), logZero: Number.isNaN(ev('log(0)')),
  logNeg: Number.isNaN(ev('log(-2)')), divZero: Number.isNaN(ev('1/0')),
  powNeg: Number.isNaN(ev('(-8)^(1/3)')), expHuge: Number.isNaN(ev('exp(1000)')),
  nanPropagates: Number.isNaN(ev('sqrt(-1) + 2')), unbound,
  vars: F.variables(F.parseFormula('b*a + sqrt(c) + a')),
  compiled: F.compileFormula('2*x')({ x: 4 }), compiledVars: F.compileFormula('y+x').variables,
}));
""")
    assert out == {"sqrtNeg": True, "logZero": True, "logNeg": True, "divZero": True, "powNeg": True,
                   "expHuge": True, "nanPropagates": True, "unbound": "ReferenceError",
                   "vars": ["a", "b", "c"], "compiled": 8, "compiledVars": ["x", "y"]}


def test_syntax_errors_are_typed():
    bad = ["", "   ", "2 +", "(1", "1)", "a $ b", "2 3", "sqrt 4", "sqrt()", "*2", "x^", "1,5", "exp(1", "()"]
    out = _node(IMPORTS + """
const res = ARGS.map((t) => {
  try { F.parseFormula(t); return null; }
  catch (e) { return { name: e.name, typed: e instanceof F.FormulaSyntaxError, isError: e instanceof Error,
                       position: e.position }; }
});
let nonString = null;
try { F.parseFormula(42); } catch (e) { nonString = e.name; }
console.log(JSON.stringify({ res, nonString }));
""", bad)
    for text, r in zip(bad, out["res"]):
        assert r is not None, f"{text!r} should not parse"
        assert r["name"] == "FormulaSyntaxError" and r["typed"] and r["isError"], text
    assert out["nonString"] == "FormulaSyntaxError"


def test_no_eval_no_function_and_imports_are_limited():
    allowed = {
        "formula.js": set(),
        "gating.js": {"../format.js"},
        "select.js": {"./benchmarks.js", "./gating.js", "./formula.js", "../format.js"},
    }
    for name, ok in allowed.items():
        text = (CATALOG / name).read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        assert not re.search(r"\beval\s*\(", code), name
        assert not re.search(r"\bFunction\s*\(", code), name
        assert "innerHTML" not in code and not re.search(r"\bdocument\.", code), name
        imports = set(re.findall(r"""from\s+['"]([^'"]+)['"]""", code))
        imports |= set(re.findall(r"""import\(\s*['"]([^'"]+)['"]""", code))
        assert imports <= ok, (name, imports - ok)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", code), name


# ── gating.js ──────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tiers() -> dict:
    rows = _node(IMPORTS + """
const out = B.DISTILLATION.map((d) => {
  const acc = B.ACCURACY.find((r) => r.species === d.species && r.task === d.task && r.frame === d.frame);
  const t = G.tier({ pysr: d.pysr, netR2: acc.r2, task: d.task, frame: d.frame });
  return { species: d.species, task: d.task, frame: d.frame, tier: t.tier, reasons: t.reasons,
           frozen: Object.isFrozen(t) && Object.isFrozen(t.reasons) };
});
console.log(JSON.stringify(out));
""")
    return {(r["species"], r["task"], r["frame"]): r for r in rows}


def test_tier_table_matches_the_brief(tiers):
    assert set(tiers) == set(EXPECTED_TIERS)
    wrong = {k: (tiers[k]["tier"], v) for k, v in EXPECTED_TIERS.items() if tiers[k]["tier"] != v}
    assert not wrong, wrong


def test_tier_reasons_are_sentences_with_typographic_minus(tiers):
    for key, r in tiers.items():
        assert r["frozen"], key
        assert r["reasons"], key
        for s in r["reasons"]:
            assert s.endswith("."), (key, s)
            assert not HYPHEN_NUMBER.search(s), (key, s)
    assert any(MINUS + "0.024" in s for s in tiers[("pion", "angle", "local")]["reasons"])
    assert any("0.0176" in s for s in tiers[("muon", "energy", "absolute")]["reasons"])
    assert any("truth R" not in s and "no R² of the network" in s
               for s in tiers[("proton", "angle", "absolute")]["reasons"])


def test_tier_rules_on_synthetic_inputs():
    cases = {
        "absent": [{"r2": {"value": 0.9, "qualifier": None}, "units": "physical", "absent": True}, 0.9, "energy", "absolute"],
        "none": [{"r2": {"value": None, "qualifier": "none"}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "lt": [{"r2": {"value": None, "qualifier": "lt", "bound": 0}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "negative": [{"r2": {"value": -0.5, "qualifier": None}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "approx0": [{"r2": {"value": 0, "qualifier": "approx"}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "low": [{"r2": {"value": 0.249, "qualifier": None}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "atPartial": [{"r2": {"value": 0.25, "qualifier": None}, "units": "physical", "absent": False}, 0.9, "energy", "absolute"],
        "weakNet": [{"r2": {"value": 0.95, "qualifier": None}, "units": "physical", "absent": False}, 0.69, "energy", "absolute"],
        "netAtFloor": [{"r2": {"value": 0.75, "qualifier": None}, "units": "physical", "absent": False}, 0.70, "energy", "absolute"],
        "standardised": [{"r2": {"value": 0.9, "qualifier": None}, "units": "standardised", "absent": False}, None, "segmentation", "absolute"],
        "leak": [{"r2": {"value": 0.9, "qualifier": None}, "units": "physical", "absent": False}, 0.99, "angle", "local"],
        "unverified": [{"r2": {"value": 0.9, "qualifier": None}, "units": "physical", "absent": False}, None, "angle", "absolute"],
        "plainNet": [{"r2": {"value": 0.9, "qualifier": None}, "units": "physical", "absent": False}, {"value": 0.8, "qualifier": None}, "energy", "absolute"],
        "middle": [{"r2": {"value": 0.5, "qualifier": None}, "units": "physical", "absent": False}, None, "energy", "absolute"],
        "noPysr": [None, 0.9, "energy", "absolute"],
    }
    out = _node(IMPORTS + """
const res = {};
for (const [k, [pysr, netR2, task, frame]] of Object.entries(ARGS)) res[k] = G.tier({ pysr, netR2, task, frame });
console.log(JSON.stringify({ res, TIERS: G.TIERS, LABELS: G.TIER_LABELS,
  consts: [G.LAW_MIN_PYSR_R2, G.LAW_MIN_NET_R2, G.PARTIAL_MIN_PYSR_R2] }));
""", cases)
    got = {k: v["tier"] for k, v in out["res"].items()}
    assert got == {
        "absent": "not-law", "none": "not-law", "lt": "not-law", "negative": "not-law", "approx0": "not-law",
        "low": "not-law", "atPartial": "partial", "weakNet": "not-law", "netAtFloor": "law",
        "standardised": "partial", "leak": "partial", "unverified": "unverified", "plainNet": "law",
        "middle": "partial", "noPysr": "not-law",
    }
    assert "worse than predicting the mean" in out["res"]["lt"]["reasons"][0]
    assert "< 0" in out["res"]["lt"]["reasons"][0]
    assert MINUS + "0.5" in out["res"]["negative"]["reasons"][0]
    assert "network R² to truth 0.69" in out["res"]["weakNet"]["reasons"][0]
    assert out["TIERS"] == ["law", "unverified", "partial", "not-law"]
    assert out["LABELS"] == {"law": "Physical law", "unverified": "High fidelity, truth R² not reported",
                             "partial": "Partial surrogate", "not-law": "Not a law"}
    assert out["consts"] == [0.75, 0.70, 0.25]


def test_leak_flags():
    out = _node(IMPORTS + """
const res = {};
for (const task of ['segmentation', 'angle', 'energy']) for (const frame of ['absolute', 'trans', 'local'])
  res[task + '/' + frame] = G.leakFlags({ task, frame });
console.log(JSON.stringify({ res, text: G.LEAK_TEXT, caveat: G.caveatFlags({ task: 'energy' }),
  caveatSeg: G.caveatFlags({ task: 'segmentation' }) }));
""")
    assert out["res"] == {
        "segmentation/absolute": [], "segmentation/trans": ["per-particle-frame"],
        "segmentation/local": ["per-particle-frame"], "angle/absolute": [], "angle/trans": [],
        "angle/local": ["local-true-angle"], "energy/absolute": [], "energy/trans": [], "energy/local": [],
    }
    assert set(out["text"]) == {"local-true-angle", "per-particle-frame", "oracle-separation"}
    assert all(t.endswith(".") for t in out["text"].values())
    assert "Per-shower translated" in out["text"]["per-particle-frame"]
    assert out["caveat"] == ["oracle-separation"] and out["caveatSeg"] == []


# ── select.js ──────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def payloads() -> dict:
    rows = _node(IMPORTS + """
const deepFrozen = (v) => v === null || typeof v !== 'object'
  || (Object.isFrozen(v) && Object.values(v).every(deepFrozen));
const out = [];
for (const card of ARGS.cards) for (const species of [...ARGS.species, 'all']) for (const task of ARGS.tasks) {
  const p = S.catalogPayload(card, { species, task });
  const text = JSON.stringify(p);
  out.push({ card, species, task, frozen: deepFrozen(p), roundTrip: JSON.stringify(JSON.parse(text)) === text,
             payload: p });
}
console.log(JSON.stringify(out));
""", {"cards": CARDS, "species": SPECIES, "tasks": TASKS})
    return {(r["card"], r["species"], r["task"]): r for r in rows}


def test_every_payload_is_frozen_json_and_catalog_sourced(payloads):
    assert len(payloads) == len(CARDS) * 5 * 3
    for (card, species, task), r in payloads.items():
        p = r["payload"]
        assert r["frozen"] and r["roundTrip"], (card, species, task)
        assert p["meta"] == {"source": "catalog", "card": card, "species": species, "task": task,
                             "report": "models_performance.md"}
        assert p["filtered"] is False
        assert p["card"] == card and p["task"] == task
        assert p["species"] == (SPECIES if species == "all" else [species])
        assert "no intervals reported" in p["provenance"] and "2026-09-24" in p["provenance"]
        assert p["frameLabels"] == {"absolute": "Absolute", "trans": "Per-shower translated", "local": "Local"}


def _sentences(p) -> list[str]:
    """Every prose string a panel may print (formula sources are verbatim report text and excluded)."""
    out = [p["provenance"]]
    for c in p.get("cells", []):
        for e in c["entries"]:
            out += e["tier"]["reasons"]
    for r in p.get("rows", []):
        out += r.get("missing", []) or []
        if r.get("leakSignalText"):
            out.append(r["leakSignalText"])
    for f in p.get("formulas", []):
        out += f["tier"]["reasons"]
    out += [w["text"] for w in p.get("weakTruth", {}).values()]
    return out


def test_prose_uses_the_typographic_minus(payloads):
    for key, r in payloads.items():
        for s in _sentences(r["payload"]):
            assert not HYPHEN_NUMBER.search(s), (key, s)


def test_defaults_and_bad_arguments():
    out = _node(IMPORTS + """
const p = S.catalogPayload('perf-overlap');
const errs = [['nope', {}], ['perf-overlap', { species: 'kaon' }], ['perf-overlap', { task: 'phi' }]].map(([c, o]) => {
  try { S.catalogPayload(c, o); return null; } catch (e) { return e.name; }
});
console.log(JSON.stringify({ species: p.meta.species, task: p.meta.task, errs,
  nullSpecies: S.catalogPayload('perf-overlap', { species: null, task: null }).meta, cards: S.CATALOG_CARDS }));
""")
    assert out["species"] == "all" and out["task"] == "energy"
    assert out["errs"] == ["RangeError", "RangeError", "RangeError"]
    assert out["nullSpecies"]["species"] == "all" and out["nullSpecies"]["task"] == "energy"
    assert out["cards"] == CARDS


_NUM_TOKEN = re.compile(r"[\u2212-]?\d+(?:\.\d+)?")


def _numbers_as_values(text: str) -> str:
    """The sentence with every decimal number replaced by its value, so 0.590 and 0.59 compare equal."""
    return _NUM_TOKEN.sub(lambda m: repr(float(m.group(0).replace("\u2212", "-"))), text)


def test_pysr_payload(payloads, tiers):
    p = payloads[("distill-pysr", "all", "energy")]["payload"]
    assert [(c["task"], c["frame"]) for c in p["cells"]] == [(t, f) for t in TASKS for f in FRAMES]
    for c in p["cells"]:
        assert [e["species"] for e in c["entries"]] == SPECIES
        for e in c["entries"]:
            key = (e["species"], c["task"], c["frame"])
            assert e["tier"]["tier"] == EXPECTED_TIERS[key], key
            # gating.js's reasons, with each R² re-set to the report's printed decimals (select.js printedReasons)
            assert [_numbers_as_values(r) for r in e["tier"]["reasons"]] == \
                [_numbers_as_values(r) for r in tiers[key]["reasons"]]
            assert set(e["features"]) | set(e["variables"]) <= set(p["features"])
            if c["task"] == "segmentation" and c["frame"] != "absolute":
                assert e["leaks"] == ["per-particle-frame"]
            if c["task"] == "angle" and c["frame"] == "local":
                assert e["leaks"] == ["local-true-angle"]
            if e["formula"]["absent"]:
                assert e["variables"] == [] and e["formula"]["ascii"] is None
    by = {(e["species"], c["task"], c["frame"]): e for c in p["cells"] for e in c["entries"]}
    assert by["muon", "segmentation", "absolute"]["tier"]["reasons"][0].startswith("R²_PySR is 0.590, between")
    assert "R²_PySR is 1.000 (at least 0.75) and the network's R² to truth is 1.0000 (at least 0.7)" \
        in by["muon", "angle", "absolute"]["tier"]["reasons"][0]
    assert "network R² to truth 0.0176, below 0.7 (R²_PySR 0.653)" in by["muon", "energy", "absolute"]["tier"]["reasons"][0]
    assert by["muon", "angle", "trans"]["netR2"] == {"value": 0.984, "qualifier": None, "dp": 4}
    muon_seg = p["cells"][0]["entries"][1]
    assert muon_seg["formula"]["units"] == "standardised"
    assert p["features"]["E_sum"]["definition"] == "total detected energy of the shower"
    one = payloads[("distill-pysr", "electron", "angle")]["payload"]
    assert all([e["species"] for e in c["entries"]] == ["electron"] for c in one["cells"])


def test_triangle_payload(payloads):
    ang = payloads[("distill-triangle", "all", "angle")]["payload"]
    assert ang["unit"] == "mrad"
    rows = {(r["species"], r["frame"]): r for r in ang["rows"]}
    assert len(rows) == 12
    # F4: the triad's radians are shown in mrad.
    assert rows[("muon", "absolute")]["mae"]["netTruth"] == 0.46
    assert rows[("muon", "absolute")]["mae"]["treeTruth"] == 8.7
    assert rows[("muon", "absolute")]["mae"]["formula"] == 0.87
    assert rows[("pion", "trans")]["mae"]["formula"] == 110.5
    assert rows[("proton", "absolute")]["mae"] == {"netTruth": 1.96, "treeTruth": None, "treeNet": None, "formula": None}
    assert rows[("proton", "absolute")]["r2"]["treeTruth"] == {"value": 0.99, "qualifier": None, "dp": 3}
    # printed decimals in the display unit: mrad keeps the triad's digits x 1000 (dp - 3)
    assert rows[("muon", "absolute")]["maeDp"] == {"netTruth": 2, "treeTruth": 1, "treeNet": 1, "formula": 2}
    assert rows[("electron", "trans")]["mae"]["netTruth"] == 21.6 and rows[("electron", "trans")]["maeDp"]["netTruth"] == 1
    assert rows[("pion", "trans")]["maeDp"]["formula"] == 2  # 110.50 as printed
    assert rows[("proton", "trans")]["maeDp"]["netTruth"] == 1  # the accuracy table's 63.6
    assert rows[("muon", "local")]["leaks"] == ["local-true-angle"]
    seg = payloads[("distill-triangle", "all", "segmentation")]["payload"]
    srows = {(r["species"], r["frame"]): r for r in seg["rows"]}
    assert seg["unit"] == ""
    # F5: the voxel-sample MAE is never the validation E-MAE; the proton's E-MAE is not drawn here.
    assert all(r["maeScope"] == "voxel-sample" for r in seg["rows"])
    assert srows[("muon", "absolute")]["mae"]["netTruth"] == 0.1955
    assert srows[("proton", "absolute")]["mae"]["netTruth"] is None
    # Leakage signals: a tree beating the network on truth; the proton's truth-tree far above its net-tree.
    assert srows[("electron", "trans")]["leakSignal"] is True
    assert srows[("proton", "trans")]["leakSignal"] is True
    assert srows[("proton", "absolute")]["leakSignal"] is False
    assert srows[("proton", "trans")]["r2"]["pysrNet"] == {"value": None, "qualifier": "lt", "bound": 0, "dp": 0}
    assert srows[("proton", "trans")]["formulaAbsent"] is True
    en = payloads[("distill-triangle", "electron", "energy")]["payload"]
    assert en["unit"] == "GeV" and len(en["rows"]) == 3
    assert all(r["leakSignal"] is False for r in en["rows"])
    # the leakage signal is a segmentation finding only (brief 12.1): it fires on every new-species
    # segmentation row and the proton's per-particle frames, and on nothing else
    fired = sorted(k for k, r in srows.items() if r["leakSignal"])
    assert fired == sorted([(s, f) for s in ("muon", "electron", "pion") for f in FRAMES] + [("proton", "trans"), ("proton", "local")])
    assert not any(r["treeBeatsNetwork"] for r in seg["rows"])
    assert srows[("muon", "absolute")]["leakSignalText"] == (
        "Tree→Truth MAE 0.1309 is below the network's 0.1955 on the voxel sample: a depth-4 tree beating the network on truth is a leakage signal.")
    for r in ang["rows"] + seg["rows"] + en["rows"]:
        assert r["missing"], (r["species"], r["frame"])


def test_angle_and_energy_rows_say_tree_beats_network_never_leakage(payloads):
    """Muon energy (Absolute, Per-shower translated): a depth-4 tree beats a network that does not predict
    the truth (R² 0.0176). That is a neutral fact with its own flag, never a leakage signal."""
    for task in ("angle", "energy"):
        rows = payloads[("distill-triangle", "all", task)]["payload"]["rows"]
        assert not any(r["leakSignal"] or r["leakSignalText"] for r in rows), task
        for r in rows:
            m = r["mae"]
            beats = m["treeTruth"] is not None and m["netTruth"] is not None and m["treeTruth"] < m["netTruth"]
            assert r["treeBeatsNetwork"] is beats, (task, r["species"], r["frame"])
            assert (r["treeBeatsNetworkText"] is not None) is beats
    en = {(r["species"], r["frame"]): r for r in payloads[("distill-triangle", "all", "energy")]["payload"]["rows"]}
    assert sorted(k for k, r in en.items() if r["treeBeatsNetwork"]) == [("muon", "absolute"), ("muon", "trans")]
    assert en[("muon", "absolute")]["treeBeatsNetworkText"] == (
        "Tree→Truth MAE 4.5868 is below the network's 4.6214 GeV: a depth-4 tree on the summary features predicts "
        "the truth better than the network on this sample.")
    assert "leak" not in en[("muon", "absolute")]["treeBeatsNetworkText"]


def test_curves_payload(payloads):
    p = payloads[("distill-curves", "all", "segmentation")]["payload"]
    assert {(f["species"], f["frame"]) for f in p["formulas"]} == {(s, f) for s in SPECIES for f in FRAMES}
    assert set(p["variables"]) == {"centroid_r", "max_hit_frac", "centroid_theta", "rms_r"}
    for v in p["variables"].values():
        lo, hi = v["domain"]
        assert v["default"] == (lo + hi) / 2
    assert p["variables"]["centroid_r"]["unit"] == "mm"
    assert {u["species"] for u in p["variables"]["rms_r"]["usedBy"]} == {"muon"}
    assert p["ceiling"]["value"] == 20 and p["ceiling"]["unit"] == "GeV" and p["ceiling"]["rule"]
    assert "not a marginal prediction" in p["note"]
    assert p["weakTruth"]["muon"]["text"] == "describe the network: its R² to truth is 0.0176–0.3390"
    assert set(p["weakTruth"]) == {"muon"}
    d = p["domain"]
    assert math.isfinite(d["xMax"]) and 0 < d["xMax"] <= 10
    assert d["xMax"] == max(s["eSum"] for s in d["bySpecies"].values())
    assert all(s["reached"] == "crossed" and s["frame"] == "absolute" for s in d["bySpecies"].values())
    assert p["absentOrExcluded"] == []


def test_curve_domain_is_finite_and_monotone():
    out = _node(IMPORTS + """
const all = S.catalogPayload('distill-curves').formulas;
const only = (sp) => all.filter((f) => f.species === sp);
const rs = [0, 1000, 2000, 3000, 4000, 5000];
const fr = [0.05, 0.2, 0.4, 0.6, 0.8, 1];
const cross = (sp, values) => {
  const d = S.curveDomain(only(sp), values);
  const f = F.compileFormula(only(sp).find((x) => x.frame === 'absolute').ascii);
  return { e: d.xMax, at: f({ ...values, E_sum: d.bySpecies[sp].eSum }) };
};
// Monotone in E_sum: every energy formula rises along the drawn x range at the defaults.
const rising = all.map((f) => {
  const fn = F.compileFormula(f.ascii);
  const vals = { centroid_r: 2500, max_hit_frac: 0.5, centroid_theta: 0.5, rms_r: 150 };
  const ys = Array.from({ length: 21 }, (_, i) => fn({ ...vals, E_sum: (i / 20) * 0.6 }));
  return ys.every((y, i) => i === 0 || y >= ys[i - 1]);
});
console.log(JSON.stringify({
  protonR: rs.map((r) => cross('proton', { centroid_r: r })),
  pionR: rs.map((r) => cross('pion', { centroid_r: r })),
  muonFrac: fr.map((m) => cross('muon', { max_hit_frac: m })),
  electronFrac: fr.map((m) => cross('electron', { max_hit_frac: m })),
  allDefault: S.curveDomain(all, {}),
  never: S.curveDomain(only('muon'), { max_hit_frac: 0 }),
  empty: S.curveDomain([], {}),
  rising,
}));
""")
    for name in ("protonR", "pionR", "muonFrac", "electronFrac"):
        series = out[name]
        es = [s["e"] for s in series]
        assert all(math.isfinite(e) and 0 < e <= 10 for e in es), (name, es)
        # A positive coefficient on the secondary variable: the 20 GeV crossing moves left as it grows.
        assert all(b <= a + 1e-12 for a, b in zip(es, es[1:])), (name, es)
        assert es[0] > es[-1], (name, es)
        for s in series:
            assert math.isclose(s["at"], 20, rel_tol=1e-6), (name, s)
    d = out["allDefault"]
    assert d["xMax"] == max(s["eSum"] for s in d["bySpecies"].values())
    assert set(d["bySpecies"]) == set(SPECIES)
    assert out["never"]["bySpecies"]["muon"]["reached"] == "not-reached"
    assert out["never"]["xMax"] == 10
    assert out["empty"]["xMax"] == 10 and out["empty"]["bySpecies"] == {}
    assert all(out["rising"])


def test_perf_catalog_payload(payloads):
    p = payloads[("perf-catalog", "all", "angle")]["payload"]
    assert [(f["key"], f["unit"]) for f in p["facets"]] == [("segmentation", ""), ("angle", "mrad"),
                                                          ("energy", "GeV"), ("energy-r2", "")]
    assert len(p["rows"]) == 36
    for r in p["rows"]:
        if r["species"] == "proton":
            assert r["n"] == {"events": 4065, "particles": 8130, "nDerived": False}
        else:
            assert r["n"] == {"events": 4000, "particles": 8000, "nDerived": True}
            assert r["tta"] is None  # F10
    assert p["notReported"]["tta"] == ["muon", "electron", "pion"]
    one = payloads[("perf-catalog", "pion", "energy")]["payload"]
    assert len(one["rows"]) == 9 and {r["species"] for r in one["rows"]} == {"pion"}


def test_perf_overlap_payload(payloads):
    p = payloads[("perf-overlap", "all", "energy")]["payload"]
    assert p["unit"] == "GeV" and len(p["bins"]) == 5 and len(p["series"]) == 12
    # F1: 11 unbinned proton events; F2: no N for the new species.
    assert p["events"]["proton"] == {"all": 4065, "bins": [1297, 1384, 1002, 204, 167], "unbinned": 11}
    assert sum(p["events"]["proton"]["bins"]) + p["events"]["proton"]["unbinned"] == p["events"]["proton"]["all"]
    assert all(p["events"][s] is None for s in ("muon", "electron", "pion"))
    # F3: the units of measure per series.
    assert p["levels"] == {"proton": "hit", "muon": "particle", "electron": "particle", "pion": "particle"}
    assert len(p["starvation"]) == 1 and p["starvation"][0]["bins"] == ["30", "40-100"]
    assert payloads[("perf-overlap", "muon", "energy")]["payload"]["starvation"] == []
    assert payloads[("perf-overlap", "proton", "angle")]["payload"]["starvation"] == []
    seg = payloads[("perf-overlap", "all", "segmentation")]["payload"]
    assert set(seg["levels"].values()) == {"hit"} and seg["unit"] == ""
    assert payloads[("perf-overlap", "pion", "angle")]["payload"]["unit"] == "mrad"


def test_perf_momentum_payload(payloads):
    p = payloads[("perf-momentum-bias", "all", "segmentation")]["payload"]
    assert len(p["windows"]) == 9 and p["scope"] == "all-exported" and p["frame"] == "absolute"
    assert p["notReported"] == ["proton"] and p["empty"] is None
    assert p["nConsistent"] == {"muon": True, "electron": False, "pion": False}  # F6
    one_signed = {(w["species"], w["centre"]) for w in p["windows"] if w["oneSigned"]}
    assert one_signed == {("muon", 5), ("muon", 15)}  # F7
    pr = payloads[("perf-momentum-bias", "proton", "energy")]["payload"]
    assert pr["windows"] == [] and pr["notReported"] == ["proton"] and pr["empty"]
    el = payloads[("perf-momentum-bias", "electron", "energy")]["payload"]
    assert el["notReported"] == [] and el["nConsistent"] == {"electron": False} and len(el["windows"]) == 3


def test_perf_diagnostics_payload(payloads):
    p = payloads[("perf-diagnostics", "muon", "energy")]["payload"]
    assert p["indecision"]["scope"] == "proton" and p["throughput"]["scope"] == "proton"
    assert p["protonOnly"] is True and p["protonShown"] is False
    assert p["protonOnlyBlocks"] == ["indecision", "throughput"]
    assert p["architecture"]["scope"] == "all"
    assert p["architecture"]["tasks"]["segmentation"]["params"]["absolute"] == 5661932
    ids = {c["id"] for c in p["caveats"]}
    assert {"momentum-windows", "muon-interpretation", "oracle-separation", "new-species-throughput"} <= ids
    assert "segmentation-indecision" not in ids and "electron-interpretation" not in ids
    seg = payloads[("perf-diagnostics", "proton", "segmentation")]["payload"]
    sids = {c["id"] for c in seg["caveats"]}
    assert "segmentation-indecision" in sids and "oracle-separation" not in sids
    assert seg["protonShown"] is True
    every = payloads[("perf-diagnostics", "all", "angle")]["payload"]
    assert set(every["datasets"]) == set(SPECIES)


# ── printed decimals (the fix round, brief 12.1) ───────────────────────────────────────────────────────────

def test_printed_reproduces_the_reports_tokens_in_js():
    """select.js `printed` formats every (value, dp) the catalogue carries exactly as the B1 test's
    reference formatter does (which tests/test_benchmark_catalog.py pins to the report's tokens), with
    U+2212 for a minus: the JS the cards run prints the report's own rounding."""
    out = _node(IMPORTS + """
const pairs = [];
const walk = (v, path) => {
  if (Array.isArray(v)) { v.forEach((x, i) => walk(x, `${path}[${i}]`)); return; }
  if (!v || typeof v !== 'object') return;
  if (Number.isInteger(v.dp) && 'qualifier' in v) {
    const x = v.qualifier === 'lt' ? v.bound : v.value;
    if (Number.isFinite(x)) pairs.push([path, x, v.dp, S.printed(x, v.dp)]);
  } else if (v.dp && typeof v.dp === 'object') {
    for (const [k, d] of Object.entries(v.dp)) {
      if (Array.isArray(d)) d.forEach((di, i) => pairs.push([`${path}.${k}[${i}]`, v[k][i], di, S.printed(v[k][i], di)]));
      else if (typeof v[k] === 'number') pairs.push([`${path}.${k}`, v[k], d, S.printed(v[k], d)]);
    }
  }
  for (const [k, x] of Object.entries(v)) if (k !== 'dp') walk(x, `${path}.${k}`);
};
for (const [k, v] of Object.entries(B)) walk(v, k);
console.log(JSON.stringify({ pairs,
  cases: [S.printed(1, 4), S.printed(1, 3), S.printed(0.984, 4), S.printed(0.59, 3), S.printed(1.13, 3),
          S.printed(-4.22, 3), S.printed(53, 2), S.printed(16, 1), S.printed(11.9, 1, { sign: true }),
          S.printed(-0.1, 1, { sign: true }), S.printed(null, 2), S.printed(0.5), S.mradDp(5), S.mradDp(4), S.mradDp(null),
          S.printedQualified({ value: 0, qualifier: 'approx', dp: 0 }), S.printedQualified({ value: null, qualifier: 'lt', bound: 0, dp: 0 }),
          S.printedQualified({ value: 1050, qualifier: 'about' }, { thousands: true }), S.printedQualified(null),
          S.printedQualified({ value: 0.59, qualifier: null, dp: 3 }), S.printedQualified({ range: [20, 40], qualifier: 'about' })] }));
""")
    assert len(out["pairs"]) > 400
    for path, value, dp, text in out["pairs"]:
        assert text.replace("−", "-") == f"{value:.{dp}f}", (path, value, dp, text)
        assert "-" not in text, (path, text)  # U+2212, never the hyphen
    assert out["cases"] == ["1.0000", "1.000", "0.9840", "0.590", "1.130", "−4.220", "53.00", "16.0", "+11.9",
                            "−0.1", "—", "0.5", 2, 1, None, "≈ 0", "< 0", "~1,050", "not reported",
                            "0.590", "~20–40"]
