"""The four Performance cards of the benchmark catalogue, executed under Node.

`perf-catalog` (`panels/bench_catalog.js`), `perf-overlap` (`panels/bench_overlap.js`),
`perf-momentum-bias` (`panels/bench_momentum.js`) and `perf-diagnostics` (`panels/bench_diagnostics.js`)
are pure option builders over the static payloads of `catalog/select.js`, and so are their drawer builders
in `catalog_notes_perf.js`. The script builds every card for every species and Compare all, every task and
both angle scales, on the dark and light screen cards and in print, renders every custom series' items with
an identity coordinate map, calls every tooltip formatter and hands back what was drawn. The tests hold the
cards to CLAUDE.md section 2 and to the recorded exception for documented point estimates:

* every bar starts at zero, a bias sits on a zero-centred axis with a zero rule, and Log10 draws dots;
* an R² below zero is clamped at zero with an "R² < 0" mark and its printed value in the tooltip;
* every mark's tooltip names its N (or "N not reported") and says it is a point estimate with no interval;
* the N strip, the 11 unbinned proton events (F1), the unit badges (F3), the one-signed windows (F7), the
  training-included windows (F6) and the proton-only scope (F10) are drawn and disclosed;
* every series colour clears 3:1 and every text 4.5:1 on both screen cards and in print, and a species is
  never a hue of its own;
* no rendered number uses an ASCII hyphen, no new module holds a colour literal or touches innerHTML, and
  the frame is never written "Translated" alone.

Skipped without `node`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MODULES = [
    JS / "panels" / "bench_catalog.js",
    JS / "panels" / "bench_overlap.js",
    JS / "panels" / "bench_momentum.js",
    JS / "panels" / "bench_diagnostics.js",
    JS / "catalog_notes_perf.js",
]

CARDS = ["perf-catalog", "perf-overlap", "perf-momentum-bias", "perf-diagnostics"]
SPECIES = ["proton", "muon", "electron", "pion", "all"]
TASKS = ["segmentation", "angle", "energy"]
THEMES = ["dark", "light", "print"]

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")
#: "Translated" alone names the D-frame; the report's frame is Per-shower translated.
BARE_TRANSLATED = re.compile(r"(?<!per-shower )\btranslated\b", re.IGNORECASE)

POINT_ESTIMATE = "point estimate as reported; no interval"

_SCRIPT = r"""
const [jsRoot] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const palette = await imp('palette.js');
const cp = await imp('panels/chart_panel.js');
const sel = await imp('catalog/select.js');
const cat = await imp('panels/bench_catalog.js');
const ovl = await imp('panels/bench_overlap.js');
const mom = await imp('panels/bench_momentum.js');
const diag = await imp('panels/bench_diagnostics.js');
const notes = await imp('catalog_notes_perf.js');

const CARDS = %(cards)s;
const SPECIES = %(species)s;
const TASKS = %(tasks)s;
const BUILDERS = {
  'perf-catalog': [cat.benchCatalogOption, cat.plotHeight, cat.drawnColours, notes.accuracyNotes],
  'perf-overlap': [ovl.benchOverlapOption, ovl.plotHeight, ovl.drawnColours, notes.overlapNotes],
  'perf-momentum-bias': [mom.benchMomentumOption, mom.plotHeight, mom.drawnColours, notes.momentumNotes],
  'perf-diagnostics': [diag.benchDiagnosticsOption, diag.plotHeight, diag.drawnColours, notes.diagnosticsNotes],
};
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1, 6, 1500, 0.1, 100];
const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };

function flatten(el, out = []) {
  if (!el) return out;
  if (el.type === 'group') { for (const c of el.children) flatten(c, out); return out; }
  out.push({ type: el.type, text: el.style?.text ?? null, fill: typeof el.style?.fill === 'string' ? el.style.fill : null,
    stroke: el.style?.stroke ?? null, opacity: el.style?.opacity ?? null, strokeOpacity: el.style?.strokeOpacity ?? null,
    dash: el.style?.lineDash ?? null, shape: el.shape ?? null });
  return out;
}

function axisInfo(axis) {
  return [].concat(axis ?? []).map((a) => {
    const f = a.axisLabel?.formatter;
    const labels = [];
    if (typeof f === 'function') {
      if (a.type === 'category') (a.data ?? []).forEach((d, i) => labels.push(String(f(d, i))));
      else for (const v of SAMPLES) labels.push(String(f(v)));
    }
    return { type: a.type, min: a.min ?? null, max: a.max ?? null, data: a.data ?? null, name: a.name ?? '', labels,
      show: a.axisLabel?.show !== false };
  });
}

function walk(result) {
  const option = result.option;
  const strings = [];
  const graphics = (option.graphic ?? []).map((g) => ({ text: g.style?.text ?? null, fill: g.style?.fill ?? null }));
  for (const g of graphics) if (g.text) strings.push(g.text);
  const legend = [].concat(option.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => d?.name ?? d));
  strings.push(...legend);
  const xAxis = axisInfo(option.xAxis);
  const yAxis = axisInfo(option.yAxis);
  for (const a of [...xAxis, ...yAxis]) { strings.push(...a.labels); if (a.name) strings.push(a.name); }
  const series = (option.series ?? []).map((s) => {
    const items = [];
    for (let i = 0; i < (s.data ?? []).length; i += 1) {
      const el = typeof s.renderItem === 'function' ? s.renderItem({ dataIndex: i, coordSys }, api) : null;
      const tip = typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter({ dataIndex: i, value: s.data[i] }) : null;
      if (tip) strings.push(tip);
      const leaves = flatten(el);
      for (const l of leaves) if (l.text) strings.push(l.text);
      items.push({ value: s.data[i], tip, leaves });
    }
    return { name: s.name, xAxisIndex: s.xAxisIndex ?? 0, colour: s.itemStyle?.color ?? null, items };
  });
  return { series, strings, graphics, legend, xAxis, yAxis, grids: [].concat(option.grid ?? []).length,
    plotGrid: result.plotGrid ? result.plotGrid.length : null };
}

const pack = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
  sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);

function renderAll() {
  const res = {};
  for (const card of CARDS) {
    const [build, height, colours, note] = BUILDERS[card];
    res[card] = {};
    for (const species of SPECIES) {
      for (const task of TASKS) {
        const payload = sel.catalogPayload(card, { species, task });
        const scales = card === 'perf-catalog' ? ['linear', 'log'] : ['linear'];
        for (const angleScale of scales) {
          const opts = { angleScale, species, task, palette: 'viridis', card };
          const key = `${species}|${task}|${angleScale}`;
          const out = { heights: {} };
          for (const width of [1100, 600, 321]) out.heights[width] = height(payload, opts, width);
          out.wide = walk(build(payload, opts, { width: 1100, height: out.heights[1100] }));
          out.narrow = walk(build(payload, opts, { width: 321, height: out.heights[321] }));
          out.colours = colours(payload, opts);
          out.notes = pack(note({ payload, species, task, angleScale, palette: 'viridis', card, title: null }));
          res[card][key] = out;
        }
      }
    }
  }
  return res;
}

function themeTokens() {
  return { card: scale.THEME.card, text: scale.THEME.text, muted: scale.THEME.muted, frames: cat.frameHues() };
}

const out = {};
scale.setScreenTheme('dark');
out.dark = { cards: renderAll(), tokens: themeTokens() };
scale.setScreenTheme('light');
out.light = { cards: renderAll(), tokens: themeTokens() };
scale.setScreenTheme('dark');
Object.assign(scale.THEME, PRINT_TOKENS);
out.print = { cards: renderAll(), tokens: themeTokens() };
scale.restoreScreenTheme();

/* ---- payload variants: a clamped R² ---------------------------------------------------------------- */
{
  const p = JSON.parse(JSON.stringify(sel.catalogPayload('perf-catalog', { species: 'all' })));
  const muon = p.rows.find((r) => r.species === 'muon' && r.task === 'energy' && r.frame === 'absolute');
  muon.r2 = { value: null, qualifier: 'lt', bound: 0 };
  const pion = p.rows.find((r) => r.species === 'pion' && r.task === 'energy' && r.frame === 'local');
  pion.r2 = { value: -0.024, qualifier: null };
  out.clamped = { chart: walk(cat.benchCatalogOption(p, {}, { width: 1100, height: 400 })), model: cat.benchCatalogModel(p, {}),
    notes: pack(notes.accuracyNotes({ payload: p })) };
}

/* ---- a fake DOM for the panel classes --------------------------------------------------------------- */
class FakeText { constructor(t) { this.nodeName = '#text'; this.data = String(t); this.parent = null; } get textContent() { return this.data; } }
class FakeElement {
  constructor(tag, doc) {
    this.tagName = String(tag).toUpperCase(); this.childNodes = []; this.attrs = {}; this.dataset = {}; this.style = {};
    this.className = ''; this.title = ''; this.parent = null; this.ownerDocument = doc;
  }
  getContext() { return null; }
  set innerHTML(_v) { throw new Error('innerHTML written'); }
  get innerHTML() { throw new Error('innerHTML read'); }
  get children() { return this.childNodes.filter((n) => n instanceof FakeElement); }
  get clientWidth() { return this.tagName === 'DIV' && this.className === 'plot' ? 1100 : 0; }
  get clientHeight() { return Number.parseFloat(this.style.height) || 330; }
  append(...nodes) {
    for (const n of nodes) {
      const node = typeof n === 'string' ? new FakeText(n) : n;
      if (node.parent) node.parent.childNodes = node.parent.childNodes.filter((c) => c !== node);
      node.parent = this; this.childNodes.push(node);
    }
  }
  after(node) {
    const p = this.parent; const i = p.childNodes.indexOf(this);
    if (node.parent) node.parent.childNodes = node.parent.childNodes.filter((c) => c !== node);
    node.parent = p; p.childNodes.splice(i + 1, 0, node);
  }
  remove() { if (this.parent) this.parent.childNodes = this.parent.childNodes.filter((c) => c !== this); this.parent = null; }
  replaceChildren(...nodes) { for (const c of this.childNodes) c.parent = null; this.childNodes = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(''); }
  set textContent(v) { this.replaceChildren(); if (v !== '' && v !== null && v !== undefined) this.append(new FakeText(v)); }
  hasClass(c) { return this.className.split(/\s+/).includes(c); }
  closest(sel) { for (let el = this; el; el = el.parent) if (el instanceof FakeElement && el.hasClass(sel.slice(1))) return el; return null; }
  querySelector(sel) { for (const c of this.children) { if (c.hasClass(sel.slice(1))) return c; const d = c.querySelector(sel); if (d) return d; } return null; }
  walk(fn) { fn(this); for (const c of this.children) c.walk(fn); }
  findAll(fn) { const o = []; this.walk((e) => { if (fn(e)) o.push(e); }); return o; }
}
const doc = { createElement: (t) => new FakeElement(t, doc), createTextNode: (t) => new FakeText(t) };
globalThis.document = doc;
let lastOption = null;
const fakeChart = (el) => ({ getWidth: () => el.clientWidth, getHeight: () => el.clientHeight, setOption: (o) => { lastOption = o; },
  resize: () => {}, clear: () => {}, getDom: () => el, dispatchAction: () => {}, on: () => {}, getZr: () => ({ on: () => {} }) });
globalThis.echarts = { init: (el) => fakeChart(el) };

function mount() {
  const card = doc.createElement('section'); card.className = 'card';
  const frame = doc.createElement('div'); frame.className = 'plot-frame';
  const plot = doc.createElement('div'); plot.className = 'plot';
  frame.append(plot); card.append(frame);
  return { card, frame, plot };
}
const describe = (el) => ({ tag: el.tagName, cls: el.className, kind: el.dataset.kind ?? null, text: el.textContent });

out.panels = {};
const classes = {
  'perf-catalog': [cat.BenchCatalogPanel, { angleScale: 'log' }],
  'perf-overlap': [ovl.BenchOverlapPanel, {}],
  'perf-momentum-bias': [mom.BenchMomentumPanel, {}],
  'perf-diagnostics': [diag.BenchDiagnosticsPanel, {}],
};
for (const [card, [P, extra]] of Object.entries(classes)) {
  out.panels[card] = {};
  for (const species of ['proton', 'muon', 'all']) {
    const { card: host, frame, plot } = mount();
    const panel = new P(plot, { card });
    const payload = sel.catalogPayload(card, { species, task: 'energy' });
    const opts = { palette: 'viridis', card, species, task: 'energy', ...extra };
    panel.render(payload, opts);
    const after = host.childNodes.slice(host.childNodes.indexOf(frame) + 1);
    const res = {
      height: Number.parseFloat(plot.style.height), wanted: BUILDERS[card][1](payload, opts, 1100),
      series: lastOption?.series?.length ?? 0, kind: panel.kind,
      extra: after.map((n) => ({ ...describe(n), nodes: n.findAll(() => true).map(describe) })),
      hostOrder: host.childNodes.map((n) => n.className),
    };
    // The export: print tokens, the panel's own lastOpts (angle scale included), its own height.
    const saved = { ...scale.THEME };
    Object.assign(scale.THEME, PRINT_TOKENS);
    const metrics = panel.exportMetrics(321);
    const printed = panel.buildOption({ payload: panel.lastPayload, opts: panel.lastOpts, metrics });
    res.export = { metrics, wanted: BUILDERS[card][1](payload, opts, 321),
      xTypes: [].concat(printed.option.xAxis ?? []).map((a) => a.type) };
    scale.restoreScreenTheme();
    Object.assign(scale.THEME, saved);
    panel.clear();
    res.cleared = { payload: panel.lastPayload === null, after: host.childNodes.length - host.childNodes.indexOf(frame) - 1 };
    out.panels[card][species] = res;
  }
}

process.stdout.write(JSON.stringify(out));
"""


def _contrast(a, b):
    def lum(rgb):
        def ch(c):
            c = c / 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, bl = (ch(v) for v in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _rgb(colour: str):
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", colour.strip())
    if m:
        v = int(m.group(1), 16)
        return [(v >> 16) & 255, (v >> 8) & 255, v & 255]
    m = re.fullmatch(r"#([0-9a-fA-F]{3})", colour.strip())
    if m:
        return [int(c * 2, 16) for c in m.group(1)]
    m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", colour)
    if m:
        return [float(m.group(i)) for i in (1, 2, 3)]
    raise ValueError(colour)


def _blend(colour, alpha, card):
    c, bg = _rgb(colour), _rgb(card)
    return [alpha * v + (1 - alpha) * w for v, w in zip(c, bg)]


@pytest.fixture(scope="module")
def run():
    script = _SCRIPT % {"cards": json.dumps(CARDS), "species": json.dumps(SPECIES), "tasks": json.dumps(TASKS)}
    proc = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps([JS.as_uri()])],
                          capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _cases(run, theme="dark", card=None):
    for c, cases in run[theme]["cards"].items():
        if card and c != card:
            continue
        for key, case in cases.items():
            species, task, scale = key.split("|")
            yield c, species, task, scale, case


# ------------------------------------------------------------ every build --


def test_every_card_builds_for_every_species_task_and_theme(run):
    for theme in THEMES:
        for card in CARDS:
            keys = run[theme]["cards"][card]
            assert len(keys) == len(SPECIES) * len(TASKS) * (2 if card == "perf-catalog" else 1), (theme, card)
            for key, case in keys.items():
                assert case["wide"]["series"] or "proton" in key, (theme, card, key)
                assert all(h >= 180 for h in case["heights"].values()), (card, key, case["heights"])


def test_compare_all_takes_more_height_than_one_species(run):
    for card in ("perf-catalog", "perf-overlap", "perf-momentum-bias"):
        cases = run["dark"]["cards"][card]
        for width in ("1100", "600"):
            one = cases["muon|energy|linear"]["heights"][width]
            many = cases["all|energy|linear"]["heights"][width]
            assert many > one, (card, width, one, many)


# ------------------------------------------------------------- zero axes --


def test_every_bar_axis_starts_at_zero_and_the_bias_axis_is_centred(run):
    for theme in THEMES:
        for card, species, task, scale, case in _cases(run, theme):
            chart = case["wide"]
            value_axes = [a for a in chart["xAxis"] + chart["yAxis"] if a["type"] in ("value", "log")]
            for a in value_axes:
                if a["type"] == "log":
                    assert card == "perf-catalog" and scale == "log", (card, species)
                    continue
                if card == "perf-momentum-bias" and a["min"] is not None and a["min"] < 0:
                    assert a["min"] == -a["max"], (species, a)
                    continue
                if a["min"] is None:  # an empty state's unlabelled axes
                    assert not a["show"]
                    continue
                assert a["min"] == 0, (theme, card, species, task, a)


def test_the_bias_has_an_explicit_zero_rule(run):
    for species in ("muon", "electron", "pion", "all"):
        chart = run["dark"]["cards"]["perf-momentum-bias"][f"{species}|energy|linear"]["wide"]
        rules = [s for s in chart["series"] if s["name"] == "zero"]
        bias_axes = [a for a in chart["yAxis"] if a["min"] is not None and a["min"] < 0]
        assert len(rules) == len(bias_axes) >= 1, species
        for rule in rules:
            line = rule["items"][0]["leaves"][0]
            assert line["type"] == "line" and line["shape"]["y1"] == line["shape"]["y2"] == 0


def test_log_draws_dots_and_linear_draws_bars(run):
    for species in SPECIES:
        for scale, shape in (("log", "circle"), ("linear", "rect")):
            chart = run["dark"]["cards"]["perf-catalog"][f"{species}|energy|{scale}"]["wide"]
            angle_axis = 1
            assert chart["xAxis"][angle_axis]["type"] == ("log" if scale == "log" else "value")
            frames = [s for s in chart["series"] if s["name"] in ("Absolute", "Per-shower translated", "Local")]
            angle = [s for s in frames if s["xAxisIndex"] == angle_axis]
            assert angle
            for s in angle:
                assert {leaf["type"] for item in s["items"] for leaf in item["leaves"]} == {shape}, (species, scale)
            # Every other facet keeps its bars.
            others = [s for s in frames if s["xAxisIndex"] != angle_axis]
            assert {leaf["type"] for s in others for item in s["items"] for leaf in item["leaves"]} == {"rect"}


def test_the_catalog_draws_the_reported_values_in_display_units(run):
    chart = run["dark"]["cards"]["perf-catalog"]["muon|energy|linear"]["wide"]
    absolute = [s for s in chart["series"] if s["name"] == "Absolute"]
    values = [s["items"][0]["value"][0] for s in absolute]
    # Segmentation E-MAE, angle MAE [mrad], energy MAE [GeV], energy R².
    assert values == [0.1086, 0.458, 4.621, 0.0176]
    titles = [g["text"] for g in chart["graphics"]]
    assert any("Angle MAE [mrad]" in t for t in titles) and any("Energy MAE [GeV]" in t for t in titles)
    assert any("mrad" in s for s in chart["strings"] if "Angle MAE" in s)


def test_the_proton_carries_its_tta_tick_and_rmse_marker_and_the_others_say_not_reported(run):
    proton = run["dark"]["cards"]["perf-catalog"]["proton|energy|linear"]["wide"]
    names = {s["name"] for s in proton["series"]}
    assert {"TTA value (tick)", "RMSE (hollow marker)"} <= names
    tta = [s for s in proton["series"] if s["name"] == "TTA value (tick)"]
    assert sum(len(s["items"]) for s in tta) == 9
    rmse = [s for s in proton["series"] if s["name"] == "RMSE (hollow marker)"]
    assert sum(len(s["items"]) for s in rmse) == 6  # angle and energy only
    assert all(leaf["type"] == "circle" and leaf["fill"] == run["dark"]["tokens"]["card"]
               for s in rmse for i in s["items"] for leaf in i["leaves"])
    muon = run["dark"]["cards"]["perf-catalog"]["muon|energy|linear"]["wide"]
    assert not {"TTA value (tick)", "RMSE (hollow marker)"} & {s["name"] for s in muon["series"]}
    assert any("TTA not reported: Muon" in g["text"] for g in muon["graphics"] if g["text"])
    assert all("TTA not reported for the muon" in i["tip"] for s in muon["series"] if s["name"] == "Absolute" for i in s["items"]
               if "R² to truth" not in i["tip"].split("<br/>")[0])


def test_r2_below_zero_is_clamped_with_a_mark_and_its_printed_value(run):
    v = run["clamped"]
    assert v["model"]["clamped"] == 2
    r2_axis = 3
    frames = [s for s in v["chart"]["series"] if s["name"] in ("Absolute", "Local") and s["xAxisIndex"] == r2_axis]
    tips = [i["tip"] for s in frames for i in s["items"] if "R² &lt; 0" in i["tip"] or "R² < 0" in i["tip"]]
    assert len(tips) == 2
    assert any("&lt; 0" in t.split("<br/>")[1] for t in tips)
    assert any("−0.024" in t for t in tips)
    marks = [leaf["text"] for s in v["chart"]["series"] if s["name"] == "catalogue marks" and s["xAxisIndex"] == r2_axis
             for i in s["items"] for leaf in i["leaves"]]
    assert marks.count("R² < 0") == 2
    clamped_values = [i["value"][0] for s in frames for i in s["items"] if "drawn clamped" in i["tip"]]
    assert clamped_values == [0, 0]
    assert "R² < 0 clamped" in v["notes"]["hazards"]


def test_leak_flags_are_marked_where_the_report_raises_them(run):
    chart = run["dark"]["cards"]["perf-catalog"]["electron|energy|linear"]["wide"]
    marks = [(s["xAxisIndex"], i["tip"].split("<br/>")[0]) for s in chart["series"] if s["name"] == "catalogue marks"
             for i in s["items"]]
    # Segmentation: Per-shower translated and Local; angle: Local.
    assert sorted(m[0] for m in marks) == [0, 0, 1]
    assert all("Absolute" not in m[1] for m in marks)


# ------------------------------------------------------------ the overlap --


def test_overlap_has_five_ordered_bins_and_all_is_a_rule_never_a_bin(run):
    for card, species, task, _, case in _cases(run, "dark", "perf-overlap"):
        chart = case["wide"]
        bins = [a for a in chart["xAxis"] if a["type"] == "category"]
        for a in bins:
            assert a["data"] == ["0 %", "10 %", "20 %", "30 %", "40–100 %"]
        frames = [s for s in chart["series"] if s["name"] in ("Absolute", "Per-shower translated", "Local")]
        rules = [s for s in frames if len(s["items"]) == 1 and s["items"][0]["leaves"][0]["type"] == "line"]
        dots = [s for s in frames if s not in rules]
        n_facets = 4 if species == "all" else 1
        assert len(rules) == len(dots) == 3 * n_facets
        for r in rules:
            leaf = r["items"][0]["leaves"][0]
            assert leaf["dash"] and leaf["shape"]["x1"] == 0 and leaf["shape"]["x2"] == 100
            assert "not the headline metric" in r["items"][0]["tip"]
        for d in dots:
            assert all(i["leaves"][-1]["type"] == "circle" for i in d["items"])


def test_the_n_strip_shows_the_proton_counts_and_says_not_reported_for_the_others(run):
    proton = run["dark"]["cards"]["perf-overlap"]["proton|angle|linear"]["wide"]
    strip = [s for s in proton["series"] if s["name"] == "Events per bin (N strip)"]
    assert len(strip) == 1
    assert [i["value"][1] for i in strip[0]["items"]] == [1297, 1384, 1002, 204, 167]
    assert [leaf["text"] for i in strip[0]["items"] for leaf in i["leaves"] if leaf["text"]] == ["1,297", "1,384", "1,002", "204", "167"]
    assert any(g["text"] == "11 of 4,065 events in no bin" for g in proton["graphics"])
    for species in ("muon", "electron", "pion"):
        chart = run["dark"]["cards"]["perf-overlap"][f"{species}|angle|linear"]["wide"]
        assert not [s for s in chart["series"] if s["name"] == "Events per bin (N strip)"]
        assert any(g["text"] and g["text"].startswith("N not reported") for g in chart["graphics"])
        joined = " ".join(chart["strings"])
        for n in ("1,297", "1,384", "4,065"):
            assert n not in joined, (species, n)
    every = run["dark"]["cards"]["perf-overlap"]["all|segmentation|linear"]["wide"]
    assert len([g for g in every["graphics"] if g["text"] and g["text"].startswith("N not reported")]) == 3
    assert len([s for s in every["series"] if s["name"] == "Events per bin (N strip)"]) == 1


def test_every_overlap_facet_carries_its_unit_badge(run):
    for task in TASKS:
        chart = run["dark"]["cards"]["perf-overlap"][f"all|{task}|linear"]["wide"]
        titles = [g["text"] for g in chart["graphics"] if g["text"] and g["text"].split(" · ")[0] in ("Proton", "Muon", "Electron", "Pion")]
        assert len(titles) == 4
        for t in titles:
            want = "per hit" if (task == "segmentation" or t.startswith("Proton")) else "per particle"
            assert f" · {want}" in t, (task, t)


def test_information_starvation_marks_the_proton_energy_bins_only(run):
    for card, species, task, _, case in _cases(run, "dark", "perf-overlap"):
        starved = [s for s in case["wide"]["series"] if s["name"] == "information starvation"]
        if species in ("proton", "all") and task == "energy":
            assert len(starved) == 1 and [i["value"][0] for i in starved[0]["items"]] == [3, 4]
            assert "3.3 GeV" in starved[0]["items"][0]["tip"] and "~8 MeV" in starved[0]["items"][0]["tip"]
        else:
            assert not starved, (species, task)


# ------------------------------------------------------------ the windows --


def test_the_proton_has_an_empty_momentum_state_with_its_reason(run):
    for task in TASKS:
        chart = run["dark"]["cards"]["perf-momentum-bias"][f"proton|{task}|linear"]["wide"]
        assert chart["series"] == []
        assert any("no momentum windows for the proton" in (g["text"] or "") for g in chart["graphics"])
    every = run["dark"]["cards"]["perf-momentum-bias"]["all|energy|linear"]["wide"]
    assert any(g["text"] == "Proton: no momentum windows in the report." for g in every["graphics"])


def test_one_signed_windows_are_diamonds_labelled_one_sign(run):
    chart = run["dark"]["cards"]["perf-momentum-bias"]["muon|energy|linear"]["wide"]
    bias = [s for s in chart["series"] if s["name"] == "Mean signed error as reported"][0]
    shapes = [i["leaves"][0]["type"] for i in bias["items"]]
    assert shapes == ["polygon", "circle", "polygon"]
    labels = [leaf["text"] for i in bias["items"] for leaf in i["leaves"] if leaf["text"]]
    assert labels == ["one sign", "one sign"]
    assert "every error in this window has one sign" in bias["items"][0]["tip"]
    labels_x = chart["xAxis"][0]["labels"]
    assert labels_x == ["4–6 GeV\nn = 11,758", "9–11 GeV\nn = 12,132", "14–16 GeV\nn = 12,458"]
    for species in ("electron", "pion"):
        other = run["dark"]["cards"]["perf-momentum-bias"][f"{species}|energy|linear"]["wide"]
        b = [s for s in other["series"] if s["name"] == "Mean signed error as reported"][0]
        assert all(i["leaves"][0]["type"] == "circle" for i in b["items"])
        assert any("n exceeds the particles" in (g["text"] or "") for g in other["graphics"])


# ------------------------------------------------------------ diagnostics --


def test_the_proton_only_heading_is_kept_for_every_species(run):
    for card, species, task, _, case in _cases(run, "dark", "perf-diagnostics"):
        heads = [g["text"] for g in case["wide"]["graphics"] if g["text"]]
        assert any("measured on the proton models only" in h for h in heads), species
        for s in case["wide"]["series"]:
            for i in s["items"]:
                assert "Measured on the proton models only" in i["tip"]
                assert i["tip"].startswith("<b>Proton segmentation")


def test_the_indecision_dumbbells_are_on_their_whole_ranges(run):
    chart = run["dark"]["cards"]["perf-diagnostics"]["muon|segmentation|linear"]["wide"]
    axes = [a for a in chart["xAxis"] if a["type"] == "value"]
    assert [(a["min"], a["max"]) for a in axes] == [(0, 1), (0, 100)]
    pred = [s for s in chart["series"] if s["name"].startswith("Network prediction")]
    truth = [s for s in chart["series"] if s["name"].startswith("Truth")]
    assert [i["value"][0] for i in pred[0]["items"]] == [0.69, 0.74, 0.74]
    assert [round(i["value"][0], 9) for i in truth[1]["items"]] == [11, 4, 4]
    assert all(i["leaves"][-1]["fill"] == run["dark"]["tokens"]["card"] for i in truth[0]["items"])


# --------------------------------------------------------------- tooltips --

ALLOWED_WITHOUT_N = {"zero", "information starvation", "Events per bin (N strip)"}


def test_every_mark_tooltip_names_its_n_and_the_point_estimate(run):
    for theme in ("dark",):
        for card, species, task, scale, case in _cases(run, theme):
            for s in case["wide"]["series"]:
                if s["name"] in ALLOWED_WITHOUT_N:
                    continue
                for i in s["items"]:
                    tip = i["tip"]
                    assert tip, (card, s["name"])
                    assert POINT_ESTIMATE in tip, (card, species, s["name"])
                    assert re.search(r"\b[Nn] = [\d,]+|N not reported", tip), (card, species, s["name"], tip)


def test_new_species_never_borrow_the_proton_n_in_the_overlap(run):
    for species in ("muon", "electron", "pion"):
        for task in TASKS:
            chart = run["dark"]["cards"]["perf-overlap"][f"{species}|{task}|linear"]["wide"]
            for s in chart["series"]:
                for i in s["items"]:
                    if i["tip"]:
                        assert "N not reported" in i["tip"] and "N = " not in i["tip"]


# -------------------------------------------------------------- the notes --


def test_every_drawer_carries_the_no_interval_hazard_and_the_selection_line(run):
    for card, species, task, scale, case in _cases(run):
        n = case["notes"]
        assert n["hazards"][0] == "no interval reported", (card, species)
        assert n["headings"][0] == "Selection"
        sel = " ".join(n["sections"]["Selection"])
        assert "models_performance.md" in sel and "do not apply" in sel
        assert any("Recorded exception" in line for line in n["sections"].get("Disclosures", [])) or "proton" in species


def test_the_drawers_carry_the_reports_facts(run):
    cards = run["dark"]["cards"]
    ov = cards["perf-overlap"]["all|angle|linear"]["notes"]
    disc = " ".join(ov["sections"]["Disclosures"])
    assert "4,054 of the 4,065 events" in disc and "11 fall in no bin (F1)" in disc
    assert "N not reported: Muon, Electron, Pion" in disc and "(F2)" in disc and "(F3)" in disc
    assert ov["hazards"] == ["no interval reported", "N not reported", "label leakage", "per-hit and per-particle mixed"]
    assert cards["perf-overlap"]["proton|segmentation|linear"]["notes"]["hazards"] == ["no interval reported", "label leakage"]
    mo = cards["perf-momentum-bias"]["all|energy|linear"]["notes"]
    disc = " ".join(mo["sections"]["Disclosures"])
    assert "Training split included (F6)" in disc and "Electron and Pion" in disc
    assert "(F7)" in disc and "Muon 4–6 GeV (+5.525 GeV)" in disc and "Muon 14–16 GeV (−4.220 GeV)" in disc
    assert "≤" in disc and "<=" not in disc
    assert mo["hazards"] == ["no interval reported", "training split included", "n exceeds the particles"]
    assert cards["perf-momentum-bias"]["muon|energy|linear"]["notes"]["hazards"] == ["no interval reported", "training split included"]
    ac = cards["perf-catalog"]["muon|energy|log"]["notes"]
    assert "(F10)" in " ".join(ac["sections"]["Disclosures"])
    assert any("Cleveland dot plot" in line for line in ac["sections"]["What is drawn"])
    assert "label leakage" in ac["hazards"]
    di = cards["perf-diagnostics"]["electron|energy|linear"]["notes"]
    assert "(F10)" in " ".join(di["sections"]["Disclosures"])
    assert "measured on the proton only" in di["hazards"]
    assert "measured on the proton only" not in cards["perf-diagnostics"]["proton|energy|linear"]["notes"]["hazards"]


# ------------------------------------------------------------- typography --


def _all_strings(case):
    out = list(case["wide"]["strings"]) + list(case["narrow"]["strings"])
    for lines in (case["notes"] or {}).get("sections", {}).values():
        out.extend(lines)
    return out


def test_no_rendered_number_uses_an_ascii_hyphen(run):
    for theme in THEMES:
        for card, species, task, scale, case in _cases(run, theme):
            for text in _all_strings(case):
                plain = re.sub(r"<[^>]+>", "", text)
                assert not HYPHEN_NUMBER.search(plain), (card, species, plain)
    # The bias axis's own negative ticks.
    chart = run["dark"]["cards"]["perf-momentum-bias"]["muon|energy|linear"]["wide"]
    assert "−2.5" in chart["yAxis"][1]["labels"]


def test_the_frame_is_never_translated_alone(run):
    for card, species, task, scale, case in _cases(run):
        for text in _all_strings(case):
            plain = re.sub(r"<[^>]+>", "", text).replace('"translated"', "")
            assert not BARE_TRANSLATED.search(plain), (card, species, plain)
    for card in CARDS:
        for species in ("proton", "muon", "all"):
            for node in run["panels"][card][species]["extra"]:
                for el in node["nodes"]:
                    text = el["text"].replace('"translated"', "")
                    assert not BARE_TRANSLATED.search(text), (card, text[:200])


# ---------------------------------------------------------------- colours --


def test_every_series_colour_and_text_clears_its_floor_on_every_card(run):
    for theme in THEMES:
        card_colour = run[theme]["tokens"]["card"]
        for card, species, task, scale, case in _cases(run, theme):
            for c in case["colours"]:
                rgb = _blend(c["colour"], c["opacity"], card_colour)
                floor = 3 if c["role"] == "mark" else 4.5
                assert _contrast(rgb, _rgb(card_colour)) >= floor, (theme, card, c)
            for g in case["wide"]["graphics"]:
                if g["text"] and g["fill"]:
                    assert _contrast(_rgb(g["fill"]), _rgb(card_colour)) >= 4.5, (theme, card, g)
            for s in case["wide"]["series"]:
                for i in s["items"]:
                    for leaf in i["leaves"]:
                        if leaf["type"] == "text":
                            assert _contrast(_rgb(leaf["fill"]), _rgb(card_colour)) >= 4.5, (theme, card, leaf)


def test_a_species_is_never_a_hue(run):
    for theme in THEMES:
        tokens = run[theme]["tokens"]
        allowed = set(tokens["frames"].values()) | {tokens["text"], tokens["muted"]}
        for card, species, task, scale, case in _cases(run, theme):
            colours = {s["colour"] for s in case["wide"]["series"] if s["colour"]}
            assert colours <= allowed, (theme, card, species, colours - allowed)
        # Compare all uses no more hues than one species.
        for card in ("perf-catalog", "perf-overlap", "perf-momentum-bias"):
            one = {s["colour"] for s in run[theme]["cards"][card]["muon|energy|linear"]["wide"]["series"] if s["colour"]}
            every = {s["colour"] for s in run[theme]["cards"][card]["all|energy|linear"]["wide"]["series"] if s["colour"]}
            assert every <= one | {tokens["text"]}, (theme, card)


def test_the_new_modules_hold_no_colour_literal_and_never_touch_inner_html():
    for path in MODULES:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source), path.name
        assert not re.search(r"\b(rgba?|hsla?)\(", source), path.name
        assert "innerHTML" not in source, path.name
        assert "Math.random" not in source and "Date" not in source, path.name


# ------------------------------------------------------- the panel classes --


def test_each_panel_sets_its_own_height_and_exports_what_the_screen_shows(run):
    for card in CARDS:
        for species in ("proton", "muon", "all"):
            p = run["panels"][card][species]
            assert p["height"] == p["wanted"], (card, species)
            assert p["export"]["metrics"]["height"] == p["export"]["wanted"], (card, species)
            assert p["cleared"]["payload"] and p["cleared"]["after"] == 0, (card, species)
    # The angle scale in force reaches the export through the panel's own opts.
    assert "log" in run["panels"]["perf-catalog"]["all"]["export"]["xTypes"]


def test_the_catalog_table_follows_the_plot_frame(run):
    p = run["panels"]["perf-catalog"]["all"]
    assert p["hostOrder"] == ["plot-frame", "catalog-table"]
    table = p["extra"][0]
    tags = [n["tag"] for n in table["nodes"]]
    assert "TABLE" in tags and "CAPTION" in tags
    rows = [n for n in table["nodes"] if n["tag"] == "TR"]
    assert len(rows) == 1 + 36
    assert "−0.1 mrad" in table["text"] and "+11.9 mrad" in table["text"]
    assert "4,000 events / 8,000 particles (derived)" in table["text"]


def test_the_diagnostics_blocks_use_the_catalogue_classes(run):
    for species in ("proton", "muon", "all"):
        p = run["panels"]["perf-diagnostics"][species]
        nodes = p["extra"][0]["nodes"]
        classes = [n["cls"] for n in nodes]
        assert classes.count("diag-block") == 5, species
        assert classes.count("diag-heading") == 5 and "diag-scope" in classes and "catalog-table" in classes
        assert "caveat-list" in classes
        scopes = [n["text"] for n in nodes if n["cls"] == "diag-scope"]
        assert scopes[0].startswith("Measured on the proton models only"), species
        if species == "muon":
            assert "not for Muon" in scopes[0]
        chips = [n for n in nodes if n["cls"] == "badge-chip"]
        assert all(c["kind"] == "proton-only" and c["text"] == "Measured on the proton models only" for c in chips)
        assert bool(chips) == (species != "muon"), species
        text = p["extra"][0]["text"]
        assert "~1,050 combined events/s" in text and "÷2 (Local)" in text and "~20–40 events/s" in text


# ------------------------------------------------- the fix round (brief 12.1) --

_PRINTED_SCRIPT = r"""
const [jsRoot] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const sel = await imp('catalog/select.js');
const cat = await imp('panels/bench_catalog.js');
const ovl = await imp('panels/bench_overlap.js');
const diag = await imp('panels/bench_diagnostics.js');
const notes = await imp('catalog_notes_perf.js');
const all = sel.catalogPayload('perf-catalog', { species: 'all' });
const model = cat.benchCatalogModel(all, {});
const tips = {};
for (const facet of model.facets) for (const r of facet.rows) tips[`${facet.key}:${r.species}:${r.frame}`] = cat.catalogTip(all, facet, r);
const ov = sel.catalogPayload('perf-overlap', { species: 'proton', task: 'angle' });
const om = ovl.benchOverlapModel(ov);
const f0 = om.facets[0];
const local = f0.series.find((x) => x.frame === 'local');
const oe = sel.catalogPayload('perf-overlap', { species: 'electron', task: 'energy' });
const oem = ovl.benchOverlapModel(oe);
const etrans = oem.facets[0].series.find((x) => x.frame === 'trans');
const titles = {};
for (const [sp, task] of [['proton', 'angle'], ['proton', 'segmentation'], ['muon', 'energy'], ['muon', 'segmentation']]) {
  const p = sel.catalogPayload('perf-overlap', { species: sp, task });
  const o = ovl.benchOverlapOption(p, {}, { width: 1100, height: 400 }).option;
  titles[`${sp}:${task}`] = (o.graphic ?? []).map((g) => g.style?.text).filter((t) => t && t.startsWith(p.speciesLabels[sp]));
}
const dg = sel.catalogPayload('perf-diagnostics', { species: 'proton' });
const dm = diag.benchDiagnosticsModel(dg);
console.log(JSON.stringify({
  tips,
  table: cat.secondaryTableRows(all).rows,
  overlap: { local: ovl.overlapTip(om, ov, f0, local, 0), all: local.all, dp: local.dp, electron: ovl.overlapTip(oem, oe, oem.facets[0], etrans, 2) },
  titles,
  diag: dm.panels.map((p) => p.rows.map((r) => [diag.valueText(p, r.predicted), diag.valueText(p, r.truth)])),
  momentum: notes.momentumNotes({ payload: sel.catalogPayload('perf-momentum-bias', { species: 'muon' }) }).sections
    .find((x) => x.heading === 'What is drawn').lines,
}));
"""


@pytest.fixture(scope="module")
def printed():
    proc = subprocess.run([NODE, "--input-type=module", "-e", _PRINTED_SCRIPT, json.dumps([JS.as_uri()])],
                          capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_report_numbers_print_with_the_reports_decimals(printed):
    """The report's 1,0000, 0,9840, 1,130 GeV, \u22124,220, 0,2120, 16,0 and 0,590 print with their zeros."""
    t = printed["tips"]
    assert "Muon \u00b7 Absolute \u00b7 Angle MAE: 0.458 mrad" in t["angle:muon:absolute"]
    assert "R\u00b2 to truth 1.0000" in t["angle:muon:absolute"] and "tree R\u00b2 to the network 0.9953" in t["angle:muon:absolute"]
    assert "R\u00b2 to truth 0.9840" in t["angle:muon:trans"]
    assert "Energy MAE: 1.130 GeV" in t["energy:proton:trans"]
    assert "with test-time augmentation (TTA): 0.2120" in t["segmentation:proton:trans"]
    assert "Energy R\u00b2 to truth: 0.3390" in t["energy-r2:muon:local"]
    assert "bias \u22120.1 mrad" in t["angle:proton:absolute"] and "bias +11.9 mrad" in t["angle:proton:trans"]
    assert "RMSE 6.8 mrad" in t["angle:proton:absolute"]
    rows = {(r[0], r[1], r[2]): r for r in printed["table"]}
    assert rows["Muon", "Angle", "Absolute"][7] == "1.0000"
    assert rows["Muon", "Energy", "Local"][9] == "0.2183"
    assert rows["Electron", "Segmentation", "Per-shower translated"][3] == "E-MAE 0.0855"
    assert rows["Proton", "Energy", "Per-shower translated"][3] == "MAE 1.130 GeV"
    o = printed["overlap"]
    assert o["all"] == 16 and o["dp"]["all"] == 1
    assert "All (the table&#39;s own total) 16.0 mrad" in o["local"]
    assert "overlap bin 20 %: MAE 0.590 GeV" in o["electron"]
    assert printed["diag"] == [[["0.69", "0.86"], ["0.74", "0.95"], ["0.74", "0.94"]],
                               [["31 %", "11 %"], ["19 %", "4 %"], ["18 %", "4 %"]]]
    mo = " ".join(printed["momentum"])
    assert "MAE 4.220 GeV, bias \u22124.220 GeV" in mo and "MAE 5.525 GeV, bias +5.525 GeV" in mo


def test_the_overlap_facet_title_names_the_level_once(printed):
    t = printed["titles"]
    assert t["proton:angle"] == ["Proton \u00b7 per hit (as the report titles its overlap table)"]
    assert t["proton:segmentation"] == ["Proton \u00b7 per hit (energy-weighted)"]
    assert t["muon:energy"] == ["Muon \u00b7 per particle (one value per shower)"]
    for titles in t.values():
        for title in titles:
            assert "hit-level" not in title and title.count("per hit") + title.count("per particle") == 1
