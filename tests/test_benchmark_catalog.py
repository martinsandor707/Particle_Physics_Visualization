"""The benchmark catalogue equals the training report it is made from.

``calosrv/static/js/catalog/benchmarks.js`` is pure data: every figure of the Hungarian training report
``models_performance.md`` (36 models: 4 species x 3 tasks x 3 frames), written out in English with the
report's own numbers. This test parses the report's tables with a small parser of its own (decimal commas;
thousands separated by a space, U+00A0 or U+202F; the minus sign U+2212; ``~``, ``<``, ``\u2248``, ``\u2014``
and ``--`` / en-dash ranges), dumps the module through Node, and asserts

* every number of every results table equals the catalogue's, exactly (the report's decimal text parsed to
  a float equals the module's literal);
* every numeric token of every results table is accounted for: a table counts its tokens and the checks
  consume them, so a number left out, or one added to the report later, fails here;
* every number the report's prose states is present in the catalogue (to the precision the prose prints);
* the report's own integrity facts (F1, F2, F4, F5, F6, F7, F9 of the brief) and two cross-checks: the
  summary table's tree R-squared (4 decimals) rounds to the triad table's (3 decimals), and the
  formula-versus-network table's network MAE equals the summary MAE to its rounding.

Skipped when ``node`` is not on the PATH, like the other module tests.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
MODULE = JS / "catalog" / "benchmarks.js"
REPORT = ROOT / "models_performance.md"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SPECIES = ["proton", "muon", "electron", "pion"]
NEW = ["muon", "electron", "pion"]
TASKS = ["segmentation", "angle", "energy"]
FRAMES = ["absolute", "trans", "local"]
HU_SPECIES = {"m\u00fcon": "muon", "elektron": "electron", "pion": "pion"}
HU_FRAME = {"abszol\u00fat": "absolute", "transzl\u00e1lt": "trans", "lok\u00e1lis": "local"}

# --------------------------------------------------------------------------------------------- Node dump

_DUMP = r"""
const [url] = JSON.parse(process.argv[1]);
const m = await import(url);
const frozen = (v) => v === null || typeof v !== 'object' || (Object.isFrozen(v) && Object.values(v).every(frozen));
const out = { frozen: {}, data: {} };
for (const [k, v] of Object.entries(m)) { out.frozen[k] = frozen(v); out.data[k] = v; }
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def dump() -> dict:
    done = subprocess.run([NODE, "--input-type=module", "-e", _DUMP, json.dumps([MODULE.as_uri()])],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def cat(dump) -> dict:
    return dump["data"]


# --------------------------------------------------------------------------------- report: tokens, tables

_NUM = re.compile(
    r"(?:(?<![\w\-\u2013\u2212])[\u2212-])?(?<!\w)(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:,\d+)?")


@dataclass(frozen=True)
class Tok:
    text: str
    value: float
    decimals: int
    prefix: str  # the qualifier character before the number, or ''


def _to_float(text: str) -> float:
    s = re.sub(r"[ \u00a0\u202f]", "", text).replace("\u2212", "-").replace(",", ".")
    return float(s)


def tokens(cell: str) -> list[Tok]:
    out = []
    for m in _NUM.finditer(cell):
        before = cell[: m.start()].rstrip()
        prefix = before[-1] if before and before[-1] in "\u2248~<" else ""
        text = m.group(0)
        dec = len(text.split(",")[1]) if "," in text else 0
        out.append(Tok(text, _to_float(text), dec, prefix))
    return out


def _sections() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = None
    fenced = False
    for line in REPORT.read_text(encoding="utf8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = re.match(r"^(#{1,3}) (.*)$", line)
        if m:
            cur = m.group(2).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


SECTIONS = _sections()


def _tables(heading: str) -> list[list[list[str]]]:
    tabs: list[list[list[str]]] = []
    cur = None
    for ln in SECTIONS[heading]:
        if ln.startswith("|"):
            if re.fullmatch(r"[:\-\s|]+", ln.strip()):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cur is None:
                cur = []
                tabs.append(cur)
            cur.append(cells)
        else:
            cur = None
    return tabs


def _prose(heading: str) -> str:
    return "\n".join(ln for ln in SECTIONS[heading] if not ln.startswith("|"))


class Ledger:
    """Counts the numeric tokens of one table and the ones the checks consume."""

    def __init__(self, table: list[list[str]]):
        self.table = table
        self.total = sum(len(tokens(c)) for row in table for c in row)
        self.done = 0

    def take(self, cell: str, expected: list) -> list[Tok]:
        toks = tokens(cell)
        got = [t.value for t in toks]
        want = [float(e) for e in expected]
        assert got == want, f"{cell!r}: report {got} != catalogue {want}"
        self.done += len(toks)
        return toks

    def take_text(self, cell: str, text: str) -> None:
        """A cell whose text (formula) the catalogue holds verbatim: every token in it is accounted for."""
        assert cell == text, f"{cell!r} != {text!r}"
        self.done += len(tokens(cell))

    def finish(self) -> None:
        assert self.done == self.total, f"{self.done} of {self.total} numeric tokens accounted for"


def qualified(cell: str) -> dict:
    """The catalogue's qualified scalar for a one-number cell."""
    (t,) = tokens(cell)
    if t.prefix == "<":
        return {"value": None, "qualifier": "lt", "bound": t.value}
    q = {"\u2248": "approx", "~": "about", "": None}[t.prefix]
    return {"value": t.value, "qualifier": q}


def _key(cell: str) -> tuple[str, str]:
    """('segmentation', 'absolute') from 'segmentation_absolute' or 'segmentation absolute'."""
    task, frame = re.split(r"[_ ]", cell.split(" (")[0])
    return task, HU_FRAME.get(frame, frame)


def _by(rows, *fields):
    out = {}
    for r in rows:
        k = tuple(r[f] for f in fields)
        assert k not in out, k
        out[k] = r
    return out


@pytest.fixture(scope="module")
def acc(cat):
    return _by(cat["ACCURACY"], "species", "task", "frame")


@pytest.fixture(scope="module")
def dist(cat):
    return _by(cat["DISTILLATION"], "species", "task", "frame")


def _sec(cat, name: str) -> str:
    return cat["SOURCE"]["sections"][name]


# ---------------------------------------------------------------------------------------- module hygiene


def test_module_is_pure_frozen_data(dump):
    text = MODULE.read_text(encoding="utf8")
    assert not re.search(r"^\s*import\b|\bimport\s*\(|\brequire\s*\(", text, re.M), "benchmarks.js imports nothing"
    assert all(dump["frozen"].values()), {k: v for k, v in dump["frozen"].items() if not v}
    required = {"SOURCE", "SPECIES", "TASKS", "FRAMES", "ARCHITECTURE", "DATASETS", "ACCURACY", "OVERLAP",
                "DISTILLATION", "ANGLE_FORMULA_VS_NET", "MOMENTUM_WINDOWS", "MOMENTUM_SCOPE", "THROUGHPUT",
                "INDECISION", "STARVATION", "CAVEATS", "FEATURES"}
    assert required <= set(dump["data"])


_HUNGARIAN = re.compile("[\u00e1\u00e9\u00ed\u00f3\u00f6\u0151\u00fa\u00fc\u0171\u00c1\u00c9\u00cd\u00d3\u00d6\u0150\u00da\u00dc\u0170]")
_HU_OK = [r"\.aliases\[\d+\]$", r"^DISTILLATION\[\d+\]\.pysr\.source$", r"^SOURCE\.sections\.\w+$",
          r"^CAVEATS\[\d+\]\.reference\.heading$"]


def _strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def test_english_only_outside_verbatim_report_text(cat):
    """Hungarian letters occur only in verbatim report text: the proton's feature aliases, its formula
    sources, the report's section headings and the one heading the report cites in docs/literature.md."""
    bad = [p for p, s in _strings(cat) if _HUNGARIAN.search(s) and not any(re.search(r, p) for r in _HU_OK)]
    assert not bad, bad


def test_sections_are_the_reports_headings(cat):
    sections = cat["SOURCE"]["sections"]
    for name, heading in sections.items():
        assert heading in SECTIONS, (name, heading)
    # every heading that carries a results table is named
    with_tables = {h for h, lines in SECTIONS.items() if any(ln.startswith("|") for ln in lines)}
    unnamed = with_tables - set(sections.values())
    # the very first table (task / model / output) is a glossary without numbers
    assert unnamed <= {h for h in unnamed if sum(len(tokens(c)) for t in _tables(h) for r in t for c in r) == 0}
    assert cat["SOURCE"]["file"] == "models_performance.md" and cat["SOURCE"]["protonDate"] == "2026-09-24"
    assert cat["SOURCE"]["settings"] == {"grid": 32, "epochs": 8, "gpu": "H200", "window": "\u00b13\u03c3"}
    assert cat["SPECIES"] == SPECIES and cat["TASKS"] == TASKS and cat["FRAMES"] == FRAMES


# ---------------------------------------------------------------------------------------- the tables


def test_accuracy_table(cat, acc):
    (table,) = _tables(_sec(cat, "accuracy"))
    led = Ledger(table)
    assert len(table) == 10
    for row in table[1:]:
        task, frame = _key(row[0])
        a = acc["proton", task, frame]
        extra = {"segmentation": [a["coreMae"]],
                 "angle": [a["rmse"], a["bias"]],
                 "energy": [a["rmse"], a["r2"]["value"] if a["r2"] else None]}[task]
        led.take(row[1], [a["params"]])
        led.take(row[2], [a["value"]])
        led.take(row[3], [a["tta"]])
        led.take(row[4], extra)
        assert a["metric"] == ("e-mae" if task == "segmentation" else "mae")
        assert a["unit"] == {"segmentation": "", "angle": "mrad", "energy": "GeV"}[task]
        assert a["treeR2Net"] is None
        assert (a["r2"] is not None) == (task == "energy") and (a["coreMae"] is not None) == (task == "segmentation")
        assert (a["rmse"] is not None) == (task != "segmentation")
        if a["r2"]:
            assert a["r2"]["qualifier"] is None
    led.finish()


def test_summary_table(cat, acc):
    tables = [t for t in _tables(_sec(cat, "newSpecies")) if t[0][1] == "modell"]
    (table,) = tables
    led = Ledger(table)
    assert len(table) == 10
    for row in table[1:]:
        sp = HU_SPECIES[row[0]]
        task = row[1].split(" ")[0]
        for frame, cell in zip(FRAMES, row[2:5]):
            a = acc[sp, task, frame]
            expected = [a["value"], a["treeR2Net"]] if task == "segmentation" else \
                [a["value"], a["r2"]["value"], a["treeR2Net"]]
            led.take(cell, expected)
            assert a["tta"] is None and a["params"] is None and a["rmse"] is None and a["bias"] is None
            if task != "segmentation":
                assert a["r2"]["qualifier"] is None
    led.finish()
    for row in table[1:]:
        task = row[1].split(" ")[0]
        assert {"segmentation": "MAE / tree", "angle": "MAE mrad", "energy": "MAE GeV"}[task] in row[1]
    assert sorted({a["unit"] for a in cat["ACCURACY"]}) == ["", "GeV", "mrad"]


def test_accuracy_covers_every_model_once(cat):
    keys = {(a["species"], a["task"], a["frame"]) for a in cat["ACCURACY"]}
    assert keys == {(s, t, f) for s in SPECIES for t in TASKS for f in FRAMES} and len(cat["ACCURACY"]) == 36
    keys = {(a["species"], a["task"], a["frame"]) for a in cat["DISTILLATION"]}
    assert keys == {(s, t, f) for s in SPECIES for t in TASKS for f in FRAMES} and len(cat["DISTILLATION"]) == 36


def _bin_tokens(cell: str) -> list[float]:
    return [t.value for t in tokens(cell)]


def test_proton_overlap_table_and_f1(cat):
    (table,) = _tables(_sec(cat, "overlapProton"))
    led = Ledger(table)
    bins = cat["OVERLAP"]["bins"]
    assert [b["label"] for b in bins] == table[0][2:7]  # labels as the report prints them
    header = [_bin_tokens(c) for c in table[0][2:7]]
    assert header == [[0.0], [10.0], [20.0], [30.0], [40.0, 100.0]]
    assert [b["key"] for b in bins] == ["0", "10", "20", "30", "40-100"]
    for cell, vals in zip(table[0][2:7], header):
        led.take(cell, vals)
    proton = cat["OVERLAP"]["proton"]
    rows = _by(proton["rows"], "task", "frame")
    assert len(rows) == 9
    unit = {"segmentation": "E-MAE", "angle": "mrad", "energy": "GeV"}
    for row in table[1:]:
        if row[0].startswith("esem\u00e9nyek"):
            ev = proton["events"]
            for cell, v in zip(row[1:], [ev["all"], *ev["bins"]]):
                led.take(cell, [v])
            continue
        task, frame = _key(row[0])
        assert re.search(r"\((.*)\)", row[0]).group(1) == unit[task]
        r = rows[task, frame]
        for cell, v in zip(row[1:], [r["all"], *r["bins"]]):
            led.take(cell, [v])
    led.finish()
    # F1: 1297 + 1384 + 1002 + 204 + 167 = 4054, not 4065
    ev = proton["events"]
    assert ev["all"] == 4065 and sum(ev["bins"]) == 4054 and proton["unbinned"] == ev["all"] - sum(ev["bins"]) == 11
    assert proton["level"] == {"segmentation": "hit", "angle": "hit", "energy": "hit"}


def test_new_species_overlap_table_f2_f3(cat):
    (table,) = _tables(_sec(cat, "overlapNew"))
    led = Ledger(table)
    header = [_bin_tokens(c) for c in table[0][2:7]]
    assert header == [[0.0], [10.0], [20.0], [30.0], [40.0, 100.0]]  # "0%", ..., "40--100%"
    for cell, vals in zip(table[0][2:7], header):
        led.take(cell, vals)
    by = {sp: _by(cat["OVERLAP"][sp]["rows"], "task", "frame") for sp in NEW}
    for sp in NEW:
        assert len(by[sp]) == 9
    for row in table[1:]:
        sp_hu, task, frame = row[0].split(" ")
        r = by[HU_SPECIES[sp_hu]][task, frame]
        for cell, v in zip(row[1:], [r["all"], *r["bins"]]):
            led.take(cell, [v])
    led.finish()
    for sp in NEW:  # F2: the report prints no per-bin event counts for the new species
        o = cat["OVERLAP"][sp]
        assert o["events"] is None and o["unbinned"] is None
        # F3: segmentation hit-level; angle and energy per particle
        assert o["level"] == {"segmentation": "hit", "angle": "particle", "energy": "particle"}
    assert not any("esem\u00e9nyek" in r[0] for r in table)


def test_proton_distillation_table(cat, dist):
    (table,) = _tables(_sec(cat, "distillationProton"))
    led = Ledger(table)
    feats = cat["FEATURES"]
    alias = {a: k for k, f in feats.items() for a in f["aliases"]}
    for row in table[1:]:
        task, frame = _key(row[0])
        d = dist["proton", task, frame]
        led.take(row[1], [d["treeR2Net"]])
        led.take(row[2], [d["treeR2Truth"]])
        names = [f.strip() for f in row[3].split(",")]
        assert [alias.get(n, n) for n in names] == d["features"], row[3]
        assert all(k in feats for k in d["features"])
        p = d["pysr"]
        led.take_text(row[4], p["source"])
        assert p["absent"] == (row[4] in {"\u2014", "(nem ad \u00e9rdemi k\u00e9pletet)"})
        led.take(row[5], [p["r2"]["bound"] if p["r2"]["qualifier"] == "lt" else p["r2"]["value"]])
        assert p["r2"] == qualified(row[5])
        assert p["units"] == "physical"
        assert d["treeMaeNet"] is None and d["netMaeTruth"] is None and d["treeMaeTruth"] is None
    led.finish()
    # F9: the qualified values are kept as qualified
    q = {(t, f): dist["proton", t, f]["pysr"]["r2"] for t in TASKS for f in FRAMES}
    assert q["segmentation", "absolute"] == {"value": 0.0, "qualifier": "approx"}
    assert q["segmentation", "trans"] == {"value": None, "qualifier": "lt", "bound": 0.0}
    assert q["angle", "local"] == {"value": 0.0, "qualifier": "approx"}
    absent = sorted(k for k, v in ((k, dist["proton", *k]["pysr"]["absent"]) for k in q) if v)
    assert absent == [("angle", "local"), ("angle", "trans"), ("segmentation", "local"), ("segmentation", "trans")]


def test_speed_table_and_f10(cat):
    th = cat["THROUGHPUT"]
    (table,) = _tables(_sec(cat, "speed"))
    led = Ledger(table)
    f = th["forward"]
    seg = led.take(table[1][1], [f["segmentation"]["value"], f["segmentation"]["queryHeadSlowdown"]["value"] * 100])
    assert [t.prefix for t in seg] == ["~", "~"]
    assert f["segmentation"]["qualifier"] == "about" and f["segmentation"]["queryHeadSlowdown"]["qualifier"] == "about"
    assert led.take(table[2][1], [f["angle"]["value"]])[0].prefix == "~"
    assert led.take(table[3][1], [f["energy"]["value"]])[0].prefix == "~"
    led.finish()
    assert f["segmentation"]["unit"] == "combined events/s" and f["angle"]["unit"] == "particles/s"
    prose = [t.value for t in tokens(_prose(_sec(cat, "speed")))]
    e = th["explain"]
    d = th["ttaDivisor"]
    assert prose == [d["absolute"], d["local"], e["segmentation"]["value"], *e["angle"]["range"], e["energy"]["value"]]
    assert d["absolute"] == d["trans"] == 8 and d["local"] == 2
    # F10: timing exists for the proton only
    assert th["scope"] == "proton" and th["gpu"] == "H200" and th["notReportedFor"] == NEW
    assert "ttaDivisor" in th


def test_interpretation_numbers(cat):
    prose = _prose(_sec(cat, "interpretation"))
    ind = cat["INDECISION"]
    trip = re.findall(r"(\d,\d+) / (\d,\d+) / (\d,\d+)", prose)
    assert [[_to_float(x) for x in t] for t in trip] == [
        [ind["polarisation"][k][f] for f in FRAMES] for k in ("predicted", "truth")]
    pct = re.findall(r"(\d+) / (\d+) / (\d+) %", prose)
    assert [[_to_float(x) / 100 for x in t] for t in pct] == [
        [ind["ambiguousShare"][k][f] for f in FRAMES] for k in ("predicted", "truth")]
    assert re.search(r"0,3\u20130,7", prose) and ind["ambiguousShare"]["band"] == [0.3, 0.7]
    assert ind["scope"] == "proton"
    st = cat["STARVATION"]
    assert re.search(r"\u00e1tlag 3,3 GeV", prose) and st["meanMomentum"] == {"value": 3.3, "unit": "GeV"}
    assert re.search(r"~8 MeV", prose) and st["deposit"] == {"value": 8, "qualifier": "about", "unit": "MeV"}
    assert re.search(r"30 %-os \u00e9s a 40\u2013100 %-os", prose) and st["bins"] == ["30", "40-100"]
    assert st["species"] == "proton" and st["task"] == "energy"


def test_datasets_table(cat):
    (table,) = [t for t in _tables(_sec(cat, "newSpecies")) if t[0][1] == "kombin\u00e1lt CSV sor"]
    led = Ledger(table)
    ds = cat["DATASETS"]
    for row in table[1:]:
        d = ds[HU_SPECIES[row[0]]]
        toks = led.take(row[1], [d["csvRows"]["value"]])
        assert d["csvRows"]["qualifier"] == ("approx" if "k\u00f6r\u00fcl" in row[1] else None), row
        assert toks[0].value == d["csvRows"]["value"]
        assert row[2].strip("`") == d["outputCsv"]
        led.take(row[3], [d["checkpoints"]])
    led.finish()
    assert ds["proton"]["validationEvents"] == 4065 and ds["proton"]["validationParticles"] == 8130
    prose = _prose(_sec(cat, "newSpecies"))
    assert re.search(r"20 000 kombin\u00e1lt esem\u00e9ny", prose) and re.search(r"4 000 valid\u00e1ci\u00f3s", prose)
    for sp in NEW:
        assert ds[sp]["combinedEvents"] == 20000 and ds[sp]["validationEvents"] == 4000
        assert ds[sp]["validationParticles"] == 2 * ds[sp]["validationEvents"] == 8000  # derived: 2 per event
    assert ds["proton"]["validationParticles"] == 2 * ds["proton"]["validationEvents"]
    assert ds["muon"]["csvRows"]["qualifier"] == "approx"


def _check_formula_numbers(sp: str, d: dict) -> None:
    p = d["pysr"]
    if p["absent"]:
        assert p["ascii"] is None and p["tex"] is None
        return
    src, ascii_, tex = p["source"], p["ascii"], p["tex"]
    nums = r"\d+(?:\.\d+)?(?:e-?\d+)?"
    s_nums = sorted(re.findall(nums, src.replace(",", ".")))
    a_nums = sorted(re.findall(nums, re.sub(r"\^2(?![\d.])", "", ascii_)))
    assert a_nums == s_nums, (src, ascii_)
    t = re.sub(r"\\times\s*10\^\{(-?\d+)\}", r"e\1", tex)
    dec = lambda xs: sorted(x for x in xs if "." in x or "e" in x)  # noqa: E731 - integers are exponents/powers
    assert dec(re.findall(nums, t)) == dec(s_nums), (src, tex)
    assert "*" in ascii_ or re.fullmatch(r"[\w/()]+", ascii_) or "sqrt" in ascii_ or "/" in ascii_
    assert ascii_.isascii() and tex.isascii() and "," not in ascii_.replace(" ", "")
    if sp != "proton":
        # the brief's reproduction rule: drop '*' and spaces, ^2 -> square, decimal points -> commas
        back = re.sub(r"\^2(?![\d.])", "\u00b2", ascii_.replace("*", "").replace(" ", ""))
        back = re.sub(r"(?<=\d)\.(?=\d)", ",", back)
        assert back == src.replace(" ", ""), (back, src)
        assert " " not in ascii_


def test_pysr_formula_table(cat, dist):
    (table,) = [t for t in _tables(_sec(cat, "pysrFormulas")) if t[0][2] == "k\u00e9plet"]
    led = Ledger(table)
    for row in table[1:]:
        sp = HU_SPECIES[row[0]]
        task, frame = _key(row[1])
        d = dist[sp, task, frame]
        p = d["pysr"]
        led.take_text(row[2].strip("`"), p["source"])
        led.take(row[3], [p["r2"]["value"]])
        assert p["r2"] == qualified(row[3]) and p["r2"]["qualifier"] is None
        assert p["units"] == ("standardised" if task == "segmentation" else "physical")
        assert p["absent"] is False
    led.finish()
    assert len(table) == 28
    # one explicit form per formula, comparable with the report's syntax; every formula's numbers match
    for d in cat["DISTILLATION"]:
        _check_formula_numbers(d["species"], d)
    assert sum(1 for d in cat["DISTILLATION"] if not d["pysr"]["absent"]) == 32


def test_angle_formula_vs_network_table(cat, acc):
    (table,) = _tables(_sec(cat, "angleFormulaVsNet"))
    led = Ledger(table)
    summary = _summary_tokens(cat)
    rows = _by(cat["ANGLE_FORMULA_VS_NET"], "species", "frame")
    assert len(rows) == 9
    for row in table[1:]:
        sp, frame = HU_SPECIES[row[0]], HU_FRAME[row[1]]
        r = rows[sp, frame]
        t_formula = led.take(row[2], [r["formulaMae"]])
        t_net = led.take(row[3], [r["netMae"]])
        assert "mrad" in row[2] and "mrad" in row[3] and r["unit"] == "mrad"
        # the network MAE equals the summary MAE to its rounding
        t_sum = summary[sp, "angle", frame][0]
        tol = 0.5 * 10 ** -t_net[0].decimals + 0.5 * 10 ** -t_sum.decimals + 1e-9
        assert abs(r["netMae"] - acc[sp, "angle", frame]["value"]) <= tol, (sp, frame)
        assert t_formula[0].decimals == 2
    led.finish()


def test_momentum_windows_f6_f7(cat):
    (table,) = _tables(_sec(cat, "momentumWindows"))
    led = Ledger(table)
    rows = _by(cat["MOMENTUM_WINDOWS"], "species", "centre")
    assert len(rows) == 9
    header = [tokens(c)[0].value for c in table[0][1:4]]
    assert header == [5, 10, 15]
    for cell in table[0][1:4]:
        led.take(cell, [tokens(cell)[0].value])
    prose = _prose(_sec(cat, "momentumWindows"))
    assert re.search(r"4--6 GeV", prose)  # the 5 GeV window is the only one the report states
    sums = {}
    for row in table[1:]:
        sp = HU_SPECIES[row[0]]
        for centre, cell in zip((5, 10, 15), row[1:4]):
            r = rows[sp, centre]
            toks = led.take(cell, [r["mae"], r["n"], r["bias"]])
            assert "GeV" in cell and re.search(r"n=", cell) and re.search(r"bias", cell)
            assert r["window"] == [centre - 1, centre + 1] and r["windowStated"] == (centre == 5)
            # F7: |bias| equals the MAE exactly <=> one-signed
            assert r["oneSigned"] == (abs(toks[2].value) == toks[0].value and toks[2].decimals == toks[0].decimals)
            sums[sp] = sums.get(sp, 0) + r["n"]
    led.finish()
    one = sorted((sp, c) for (sp, c), r in rows.items() if r["oneSigned"])
    assert one == [("muon", 5), ("muon", 15)]
    # F6: the windows use the whole export; the sums exceed the particles for the electron and the pion
    scope = cat["MOMENTUM_SCOPE"]
    assert scope["scope"] == "all-exported" and scope["notReported"] == ["proton"]
    assert sums == {"muon": 36348, "electron": 77094, "pion": 253659}
    for sp in NEW:
        particles = 2 * cat["DATASETS"][sp]["combinedEvents"]
        assert scope["nConsistent"][sp] == (sums[sp] <= particles), sp
    assert scope["nConsistent"] == {"muon": True, "electron": False, "pion": False}
    assert re.search(r"nem csak a valid\u00e1ci\u00f3s subset", prose)


def _summary_tokens(cat) -> dict:
    (table,) = [t for t in _tables(_sec(cat, "newSpecies")) if t[0][1] == "modell"]
    out = {}
    for row in table[1:]:
        task = row[1].split(" ")[0]
        for frame, cell in zip(FRAMES, row[2:5]):
            out[HU_SPECIES[row[0]], task, frame] = tokens(cell)
    return out


def test_triad_table_and_cross_checks(cat, dist, acc):
    (table,) = _tables(_sec(cat, "distillationNew"))
    led = Ledger(table)
    summary = _summary_tokens(cat)
    feats = cat["FEATURES"]
    assert len(table) == 28
    for row in table[1:]:
        task, frame = _key(row[0])
        sp = HU_SPECIES[row[1]]
        d = dist[sp, task, frame]
        toks = led.take(row[2], [d["treeR2Net"]]) + led.take(row[3], [d["treeMaeNet"]]) \
            + led.take(row[4], [d["netMaeTruth"]]) + led.take(row[5], [d["treeMaeTruth"]])
        assert [f.strip() for f in row[6].split(",")] == d["features"]
        assert all(k in feats for k in d["features"])  # the new species print English keys: no alias needed
        assert d["treeR2Truth"] is None
        s = summary[sp, task, frame]
        a = acc[sp, task, frame]
        # tree R-squared: the summary's 4 decimals round to the triad's 3 (a 4-decimal tie, 0.7665, prints 0.766)
        assert abs(a["treeR2Net"] - d["treeR2Net"]) <= 0.0005 + 1e-9, (sp, task, frame)
        assert toks[0].decimals == 3 and s[-1].decimals == 4
        net, tree_net, net_truth, tree_truth = toks[0:4]
        if task == "segmentation":
            # F5: the triad's network MAE is a voxel-sample figure, not the validation E-MAE
            assert d["maeScope"] == "voxel-sample" and d["maeUnit"] == ""
            assert d["netMaeTruth"] != a["value"], (sp, frame)
        else:
            scale = 1000 if task == "angle" else 1
            assert d["maeScope"] == "validation"
            assert d["maeUnit"] == ("rad" if task == "angle" else "GeV")  # F4: the triad's angle MAEs are radians
            tol = 0.5 * 10 ** -net_truth.decimals * scale + 0.5 * 10 ** -s[0].decimals + 1e-9
            assert abs(d["netMaeTruth"] * scale - a["value"]) <= tol, (sp, task, frame, d["netMaeTruth"], a["value"])
    led.finish()
    # F5, stated plainly: for every segmentation model the two figures differ
    for sp in NEW:
        for f in FRAMES:
            assert dist[sp, "segmentation", f]["netMaeTruth"] != acc[sp, "segmentation", f]["value"]
    # F4 on the rows the brief names: muon absolute 0.00046 rad against the summary's 0.458 mrad
    assert dist["muon", "angle", "absolute"]["netMaeTruth"] == 0.00046 and acc["muon", "angle", "absolute"]["value"] == 0.458
    assert dist["muon", "segmentation", "absolute"]["netMaeTruth"] == 0.1955
    assert acc["muon", "segmentation", "absolute"]["value"] == 0.1086


def test_tree_r2_roundings_hold_for_the_proton(cat, dist):
    # the proton has one tree R-squared source only (3 decimals); no cross-check, but no 4-decimal copy either
    for t in TASKS:
        for f in FRAMES:
            assert dist["proton", t, f]["treeR2Net"] is not None


# ------------------------------------------------------------------------------------------ prose


def _pool(cat) -> list[float]:
    nums: list[float] = []

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, str):
            nums.extend(float(x) for x in re.findall(r"\d+(?:\.\d+)?", v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(cat)
    return nums


_PROSE_SKIP = {"Szerkezet", "Parancsok (a `scripts/` mappából)"}


def test_every_number_in_the_prose_is_in_the_catalogue(cat):
    """Prose is not a table, so it is checked by presence: each number the report states in a sentence
    appears in the catalogue, to the precision the sentence prints (a percentage may be stored as a share)."""
    pool = _pool(cat)
    missing = []
    count = 0
    for heading in SECTIONS:
        if heading in _PROSE_SKIP:
            continue
        for tok in tokens(_prose(heading)):
            count += 1
            tol = 0.5 * 10 ** -tok.decimals + 1e-9
            if not any(abs(x - tok.value) <= tol or abs(x - tok.value / 100) <= tol / 100 for x in pool):
                missing.append((heading, tok.text))
    assert count > 100
    assert not missing, missing


def test_architecture_facts(cat):
    arch = cat["ARCHITECTURE"]
    prose = _prose(_sec(cat, "architecture"))
    widths = [[int(x) for x in m] for m in re.findall(r"(\d+)/(\d+)/(\d+) csatorna", prose)]
    assert widths == [arch["tasks"]["segmentation"]["widths"], arch["tasks"]["angle"]["widths"]]
    millions = [_to_float(x) for x in re.findall(r"(\d,\d\d) M", prose)]
    s, a, e = (arch["tasks"][t] for t in TASKS)
    assert millions == [s["paramsMillions"]["trans"], s["paramsMillions"]["absolute"], a["paramsMillions"],
                        e["paramsMillions"]]
    for m, params in ((s["paramsMillions"], s["params"]),
                      ({"x": a["paramsMillions"]}, {"x": a["params"]}),
                      ({"x": e["paramsMillions"]}, {"x": e["params"]})):
        for k in m:
            assert round(params[k] / 1e6 + 1e-9, 2) == m[k], (k, params[k])
    assert s["queryHead"] == {"absolute": False, "trans": True, "local": True}
    assert e["cnnWidth"] == 56 and e["transformerD"] == 288 and "d = 288" in prose and "CNN 56" in prose
    enc = arch["hitEncoder"]
    assert enc["slots"] == {"absolute": 16, "trans": 4, "local": 4}
    assert re.search(r"abszol\u00fatban 16, transzl\u00e1lt \u00e9s lok\u00e1lis keretben 4", prose)
    assert re.search(r"5,1, illetve 1,4", prose) and enc["meanHitsPerVoxel"] == {"absolute": 5.1, "other": 1.4}
    assert re.search(r"31, illetve 3\b", prose) and enc["p99HitsPerVoxel"] == {"absolute": 31, "other": 3}
    assert arch["symmetry"]["absolute"] == {"group": "D4", "transforms": 8}
    assert arch["symmetry"]["trans"] == {"group": "D4", "transforms": 8}
    assert arch["symmetry"]["local"]["transforms"] == 2
    vox = arch["voxels"]
    top = _prose(next(h for h in SECTIONS if h.startswith("Koordin")))
    assert re.search(r"250 \u00d7 250 \u00d7 53 mm", top) and vox["absolute"] == [250, 250, 53]
    assert re.search(r"45 \u00d7 45 \u00d7 55 mm", top) and vox["trans"] == vox["local"] == [45, 45, 55]
    assert vox["approx"] is True
    # the same architecture is claimed for the new species
    assert "azonosak" in _prose(_sec(cat, "ttaSpeedNew")) and arch["identicalForNewSpecies"] is True
    assert arch["tasks"]["segmentation"]["params"] == {"absolute": 5661932, "trans": 5900429, "local": 5900429}


def test_proton_accuracy_params_match_architecture(cat, acc):
    p = cat["ARCHITECTURE"]["tasks"]
    for f in FRAMES:
        assert acc["proton", "segmentation", f]["params"] == p["segmentation"]["params"][f]
        assert acc["proton", "angle", f]["params"] == p["angle"]["params"]
        assert acc["proton", "energy", f]["params"] == p["energy"]["params"]


# ---------------------------------------------------------------------------------- features, caveats


def test_features_and_caveats(cat, dist):
    feats = cat["FEATURES"]
    used = {k for d in cat["DISTILLATION"] for k in d["features"]}
    assert set(feats) == used
    # definitions only where the report gives them
    assert [k for k, f in feats.items() if f["definition"]] == ["E_sum", "max_hit_frac"]
    assert feats["E_sum"]["definition"] == "total detected energy of the shower"
    assert feats["max_hit_frac"]["definition"] == "relative share of the largest hit"
    assert all(f["inferred"] == bool(f["aliases"]) for f in feats.values())
    # the mappings the brief fixes
    brief = {"r a s\u00falypontt\u00f3l": "r_to_centroid", "voxelsz\u00e1m": "n_voxels", "sz\u00f3r\u00e1s": "spread",
             "szomsz\u00e9d-E": "neighbour_E_frac", "m\u00e9lys\u00e9g": "depth_from_first", "E-h\u00e1nyad": "E_voxel_frac",
             "szomsz\u00e9dok": "n_neighbours", "s\u00falypont \u03b8": "centroid_theta",
             "els\u0151 r\u00e9teg": "z_first", "hitsz\u00e1m": "n_hits", "s\u00falypont r": "centroid_r"}
    got = {a: k for k, f in feats.items() for a in f["aliases"]}
    assert got == brief
    # the proton's formula variables carry an inferred mapping, flagged
    assert all(d["pysr"]["featureMapInferred"] for d in cat["DISTILLATION"]
               if d["species"] == "proton" and not d["pysr"]["absent"])
    ids = [c["id"] for c in cat["CAVEATS"]]
    assert len(ids) == len(set(ids)) and all(c["text"] for c in cat["CAVEATS"])
    for c in cat["CAVEATS"]:
        assert set(c["scope"]) <= {"species", "task", "frame"}
        for k, allowed in (("species", SPECIES), ("task", TASKS), ("frame", FRAMES)):
            assert set(c["scope"].get(k, [])) <= set(allowed)
    # F8: the report's leakage caveats are present
    assert {"local-frame-true-angle", "segmentation-frames-per-particle", "input-separation", "oracle-separation"} <= set(ids)
    by_id = {c["id"]: c for c in cat["CAVEATS"]}
    assert by_id["oracle-separation"]["scope"] == {"task": ["angle", "energy"]}
    assert by_id["local-frame-true-angle"]["scope"] == {"task": ["angle"], "frame": ["local"]}
    assert by_id["segmentation-frames-per-particle"]["scope"]["frame"] == ["trans", "local"]
    # F10
    assert by_id["new-species-throughput"]["scope"]["species"] == NEW


def test_the_catalogue_does_not_derive_an_interval(cat):
    """Point estimates as reported: no key anywhere names an interval, a standard error or a spread."""
    banned = re.compile(r"(interval|stderr|std|sigma|ci95|lower|upper|ci_)", re.I)
    keys = []

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                keys.append(k)
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(cat)
    assert not [k for k in keys if banned.search(k)]


def test_every_number_in_a_caveat_is_in_the_report(cat):
    """The converse of the prose check: the English caveats quote the report's numbers, not their own."""
    report = [t for h in SECTIONS if h not in _PROSE_SKIP for t in tokens("\n".join(SECTIONS[h]))]
    wrong = []
    for c in cat["CAVEATS"]:
        for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w])", c["text"]):
            text = m.group(1)
            value = float(text.replace(",", "")) if re.fullmatch(r"\d{1,3}(?:,\d{3})+", text) else float(text)
            decimals = len(text.split(".")[1]) if "." in text else 0
            if not any(t.value == value and (t.decimals == decimals or decimals == 0) for t in report) \
                    and not any(abs(t.value - value) <= 0.5 * 10 ** -t.decimals + 1e-9 and t.decimals >= decimals
                                for t in report):
                wrong.append((c["id"], text))
    assert not wrong, wrong
