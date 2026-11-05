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
        // 'log10' is what the Angle axis control stores (labels.js); the builders must take it as it is.
        const scales = card === 'perf-catalog' ? ['linear', 'log10'] : ['linear'];
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
  'perf-catalog': [cat.BenchCatalogPanel, { angleScale: 'log10' }],
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
                    assert card == "perf-catalog" and scale == "log10", (card, species)
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
        for scale, shape in (("log10", "circle"), ("linear", "rect")):
            chart = run["dark"]["cards"]["perf-catalog"][f"{species}|energy|{scale}"]["wide"]
            angle_axis = 1
            assert chart["xAxis"][angle_axis]["type"] == ("log" if scale == "log10" else "value")
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
    """R2-7, R1-11: one label over a bracket spanning the 30 % and 40-100 % bins, worded for both bins together."""
    for card, species, task, _, case in _cases(run, "dark", "perf-overlap"):
        starved = [s for s in case["wide"]["series"] if s["name"] == "information starvation"]
        if species in ("proton", "all") and task == "energy":
            assert len(starved) == 1 and len(starved[0]["items"]) == 1, species
            item = starved[0]["items"][0]
            assert (item["value"][0], item["value"][2]) == (3, 4)
            texts = [leaf["text"] for leaf in item["leaves"] if leaf["type"] == "text"]
            assert texts == ["info-starved"]
            assert [leaf["type"] for leaf in item["leaves"]].count("line") == 3  # the bracket and its two ends
            tip = item["tip"]
            assert "in the 30 % and 40–100 % bins together the particles have a mean momentum of 3.3 GeV" in tip
            assert "3.3 GeV" in tip and "~8 MeV" in tip
        else:
            assert not starved, (species, task)
        for text in _all_strings(case):
            assert "in this bin" not in text.replace("events in this bin", ""), (species, task, text)


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
    # R1-5: a bound from the rounding, never an exact implication.
    tip = bias["items"][0]["tip"]
    assert "to the report&#39;s rounding, |bias| = MAE" in tip or "to the report's rounding, |bias| = MAE" in tip
    assert "errors of the other sign average under 0.0005 GeV per particle of the window" in tip
    assert "(almost) every error has one sign" in tip
    assert "every error in this window has one sign" not in tip
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
    ac = cards["perf-catalog"]["muon|energy|log10"]["notes"]
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


# ------------------------------------------------- the fix round (review, Stage 5) --

_FIX_SCRIPT = r"""
const [jsRoot] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const { measureText } = await imp('textfit.js');
const sel = await imp('catalog/select.js');
const cards = await imp('models_cards.js');
const cat = await imp('panels/bench_catalog.js');
const ovl = await imp('panels/bench_overlap.js');
const mom = await imp('panels/bench_momentum.js');
const diag = await imp('panels/bench_diagnostics.js');
const notes = await imp('catalog_notes_perf.js');
const out = {};
const arr = (x) => [].concat(x ?? []);
function theme(name) {
  if (name === 'print') { scale.setScreenTheme('dark'); Object.assign(scale.THEME, PRINT_TOKENS); }
  else scale.setScreenTheme(name);
}

/* ---- R2-1 / R3-1: the stored 'log10', end to end through the card's own options ---------------------- */
out.log10 = {};
for (const [label, controls, view] of [
  ['log10', { benchAngleScale: 'log10' }, {}],
  ['log10-all', { benchAngleScale: 'log10' }, { bench_species: 'all' }],
  ['default', {}, {}],
]) {
  const opts = cards.cardOptions('perf-catalog', { controls, view });
  const payload = sel.catalogPayload('perf-catalog', { species: opts.species, task: opts.task });
  out.log10[label] = { angleScale: opts.angleScale, themes: {} };
  for (const name of ['dark', 'light', 'print']) {
    theme(name);
    const height = cat.plotHeight(payload, opts, 1100);
    const { option } = cat.benchCatalogOption(payload, opts, { width: 1100, height });
    const model = cat.benchCatalogModel(payload, opts);
    const angle = model.facets.findIndex((f) => f.key === 'angle');
    const frames = arr(option.series).filter((s) => s.xAxisIndex === angle && ['Absolute', 'Per-shower translated', 'Local'].includes(s.name));
    const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
    const leaves = frames.flatMap((s) => (s.data ?? []).map((d, i) => s.renderItem({ dataIndex: i, coordSys: {} }, api).type));
    const drawn = notes.accuracyNotes({ payload, angleScale: opts.angleScale }).sections.find((x) => x.heading === 'What is drawn').lines;
    out.log10[label].themes[name] = { axis: arr(option.xAxis)[angle].type, otherAxes: arr(option.xAxis).filter((_, i) => i !== angle).map((a) => a.type),
      leaves, drawn };
    scale.restoreScreenTheme();
  }
}
out.logSpellings = ['log', 'log10', 'linear', undefined, 'LOG'].map((v) => cat.angleScaleOf({ angleScale: v }));

/* ---- R2-2: the diagnostics' row labels start inside the figure ------------------------------------- */
out.rowLabels = [];
for (const [name, width] of [['dark', 1100], ['light', 1100], ['dark', 600], ['print', 661], ['print', 321]]) {
  theme(name);
  for (const species of ['proton', 'all']) {
    const payload = sel.catalogPayload('perf-diagnostics', { species });
    const model = diag.benchDiagnosticsModel(payload);
    const layout = diag.benchDiagnosticsLayout(model, payload, width);
    const { option } = diag.benchDiagnosticsOption(payload, {}, { width, height: layout.height });
    const grids = arr(option.grid);
    arr(option.yAxis).forEach((a, i) => {
      const grid = grids[a.gridIndex ?? i];
      const cellX = grid.left - layout.inset;
      for (const label of a.data) {
        const start = grid.left - 8 - measureText(label, a.axisLabel.fontSize, scale.THEME.fontFamily);
        out.rowLabels.push({ name, width, species, label, start, cellX });
      }
    });
  }
  scale.restoreScreenTheme();
}

/* ---- R2-3 / R2-7: every text of every option, inside the figure and clear of every other ------------ */
const LH = 1.25;
const MARGIN = 8;
function box(text, x, y, size, align = 'left', valign = 'top', lineHeight = null) {
  const lines = String(text).split('\n');
  const w = Math.max(...lines.map((l) => measureText(l, size, scale.THEME.fontFamily)));
  const h = lines.length * (lineHeight ?? LH * size);
  const x0 = align === 'right' ? x - w : align === 'center' ? x - w / 2 : x;
  const y0 = valign === 'bottom' ? y - h : valign === 'middle' ? y - h / 2 : y;
  return { text: String(text), lines: lines.length, x0, y0, x1: x0 + w, y1: y0 + h };
}
function axisMap(axis, grid, horizontal) {
  const len = horizontal ? grid.width : grid.height;
  if (axis.type === 'category') {
    const n = (axis.data ?? []).length || 1;
    return (i) => (horizontal ? grid.left : grid.top) + ((axis.inverse || horizontal ? i : n - 1 - i) + 0.5) * len / n;
  }
  const lo = axis.min; const hi = axis.max;
  const t = axis.type === 'log' ? (v) => (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) : (v) => (v - lo) / (hi - lo);
  return horizontal ? (v) => grid.left + t(v) * grid.width : (v) => grid.top + grid.height - t(v) * grid.height;
}
function ticks(axis) {
  if (axis.type === 'log') { const o = []; for (let v = axis.min; v <= axis.max * 1.0000001; v *= 10) o.push(v); return o; }
  if (!(axis.interval > 0)) return [axis.min, axis.max];
  const n = Math.round((axis.max - axis.min) / axis.interval);
  return Array.from({ length: n + 1 }, (_, k) => Number((axis.min + k * axis.interval).toPrecision(12)));
}
function texts(option) {
  const boxes = [];
  for (const g of arr(option.graphic)) {
    const s = g.style ?? {};
    if (s.text) boxes.push({ ...box(s.text, s.x, s.y, s.fontSize, s.textAlign, s.textVerticalAlign, s.lineHeight), kind: 'graphic' });
  }
  const grids = arr(option.grid);
  const xs = arr(option.xAxis);
  const ys = arr(option.yAxis);
  const axisBoxes = (a, horizontal) => {
    const grid = grids[a.gridIndex ?? 0];
    const map = axisMap(a, grid, horizontal);
    const lab = a.axisLabel ?? {};
    if (lab.show !== false) {
      const values = a.type === 'category' ? (a.data ?? []).map((d, i) => [d, i]) : ticks(a).map((v, i) => [v, i]);
      for (const [v, i] of values) {
        const text = typeof lab.formatter === 'function' ? lab.formatter(v, i) : String(v);
        if (!text) continue;
        const p = map(a.type === 'category' ? i : v);
        const pitch = String(text).includes('\n') ? lab.lineHeight : null;
        if (String(text).includes('\n')) out.text.stacked.push(pitch && pitch >= 1.3 * lab.fontSize ? 'stacked' : `${text}: line pitch ${pitch}`);
        boxes.push({ ...(horizontal ? box(text, p, grid.top + grid.height + MARGIN, lab.fontSize, 'center', 'top', pitch)
          : box(text, grid.left - MARGIN, p, lab.fontSize, 'right', 'middle', pitch)), kind: horizontal ? 'x label' : 'y label' });
      }
    }
    if (a.name) {
      const size = a.nameTextStyle.fontSize;
      if (horizontal) boxes.push({ ...box(a.name, grid.left + grid.width / 2, grid.top + grid.height + a.nameGap, size, 'center', 'top'), kind: 'x name' });
      else {
        const w = measureText(a.name, size, scale.THEME.fontFamily);
        const cx = grid.left - a.nameGap;
        const cy = grid.top + grid.height / 2;
        boxes.push({ text: a.name, lines: 1, x0: cx - LH * size, x1: cx, y0: cy - w / 2, y1: cy + w / 2, kind: 'y name' });
      }
    }
    return map;
  };
  const xm = xs.map((a) => axisBoxes(a, true));
  const ym = ys.map((a) => axisBoxes(a, false));
  for (const s of arr(option.series)) {
    if (typeof s.renderItem !== 'function') continue;
    const xi = s.xAxisIndex ?? 0;
    const yi = s.yAxisIndex ?? 0;
    const grid = grids[xs[xi].gridIndex ?? 0];
    const api = {
      coord: (p) => [xm[xi](p[0]), ym[yi](p[1])],
      size: () => [xs[xi].type === 'category' ? grid.width / xs[xi].data.length : 0, ys[yi].type === 'category' ? grid.height / ys[yi].data.length : 0],
    };
    const coordSys = { x: grid.left, y: grid.top, width: grid.width, height: grid.height };
    (s.data ?? []).forEach((d, i) => {
      const walk = (e) => {
        if (!e) return;
        if (e.type === 'group') { e.children.forEach(walk); return; }
        if (e.type === 'text' && e.style?.text) {
          const st = e.style;
          boxes.push({ ...box(st.text, st.x, st.y, st.fontSize, st.textAlign, st.textVerticalAlign), kind: `series ${s.name}` });
        }
        // The N strip's bars: a count must not run onto a neighbouring bar.
        if (e.type === 'rect' && s.name === 'Events per bin (N strip)') {
          const r = e.shape;
          boxes.push({ text: `bar ${i}`, lines: 1, x0: r.x, y0: r.y, x1: r.x + r.width, y1: r.y + r.height, kind: 'bar' });
        }
      };
      walk(s.renderItem({ dataIndex: i, coordSys }, api));
    });
  }
  return boxes;
}
const BUILD = {
  'perf-catalog': [cat.benchCatalogOption, cat.plotHeight],
  'perf-overlap': [ovl.benchOverlapOption, ovl.plotHeight],
  'perf-momentum-bias': [mom.benchMomentumOption, mom.plotHeight],
  'perf-diagnostics': [diag.benchDiagnosticsOption, diag.plotHeight],
};
out.text = { checked: 0, multiline: 0, problems: [], stacked: [] };
for (const [name, width] of [['print', 321], ['print', 661], ['dark', 1100], ['light', 1100], ['dark', 1024], ['dark', 600]]) {
  theme(name);
  for (const [card, [build, height]] of Object.entries(BUILD)) {
    for (const species of ['proton', 'muon', 'electron', 'pion', 'all']) {
      for (const task of ['segmentation', 'angle', 'energy']) {
        for (const angleScale of card === 'perf-catalog' ? ['linear', 'log10'] : ['linear']) {
          const payload = sel.catalogPayload(card, { species, task });
          const opts = { angleScale, species, task, card };
          const h = height(payload, opts, width);
          const boxes = texts(build(payload, opts, { width, height: h }).option);
          out.text.checked += boxes.length;
          out.text.multiline += boxes.filter((b) => b.lines > 1).length;
          const where = `${name} ${width} ${card} ${species} ${task} ${angleScale}`;
          for (const b of boxes) {
            if (b.kind === 'bar') continue;
            if (b.x0 < -0.5 || b.x1 > width + 0.5 || b.y0 < -0.5 || b.y1 > h + 0.5) out.text.problems.push(`${where}: "${b.text}" (${b.kind}) leaves the ${width} × ${h} figure`);
          }
          for (let i = 0; i < boxes.length; i += 1) {
            for (let j = i + 1; j < boxes.length; j += 1) {
              const a = boxes[i];
              const b = boxes[j];
              if (a.kind === 'bar' && b.kind === 'bar') continue;
              if (Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0) > 0.5 && Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0) > 0.5) {
                out.text.problems.push(`${where}: "${a.text}" (${a.kind}) overlaps "${b.text}" (${b.kind})`);
              }
            }
          }
        }
      }
    }
  }
  scale.restoreScreenTheme();
}

/* ---- the bias axis's ticks --------------------------------------------------------------------------- */
out.bias = ['muon', 'electron', 'pion'].map((species) => {
  const m = mom.benchMomentumModel(sel.catalogPayload('perf-momentum-bias', { species }));
  return { species, bound: m.rows[0].bias.bound, interval: m.rows[0].bias.interval, most: mom.maxBiasIntervals() };
});

/* ---- R1-2: the diagnostics tables, every cell ------------------------------------------------------- */
out.blocks = Object.fromEntries(['proton', 'muon', 'all'].map((species) => [species,
  diag.diagnosticsBlocks(sel.catalogPayload('perf-diagnostics', { species })).filter((b) => b.table).map((b) => ({ key: b.key, rows: b.table.rows }))]));
{
  // R3-2: a value the report does not give reads "not reported", through the one formatter.
  const p = JSON.parse(JSON.stringify(sel.catalogPayload('perf-diagnostics', { species: 'proton' })));
  p.throughput.explain.segmentation = { value: null, qualifier: 'none' };
  out.noneCell = diag.diagnosticsBlocks(p).find((b) => b.key === 'throughput').table.rows[0][3];
}

/* ---- R1-5, R1-11, R1-15: the drawers ----------------------------------------------------------------- */
const lines = (n) => n.sections.flatMap((x) => x.lines);
out.notes = {
  momentum: lines(notes.momentumNotes({ payload: sel.catalogPayload('perf-momentum-bias', { species: 'all' }) })),
  accuracy: lines(notes.accuracyNotes({ payload: sel.catalogPayload('perf-catalog', { species: 'muon' }) })),
  overlap: lines(notes.overlapNotes({ payload: sel.catalogPayload('perf-overlap', { species: 'proton', task: 'energy' }) })),
};
out.bound = mom.oneSignBound(sel.catalogPayload('perf-momentum-bias', { species: 'muon' }).windows[0]);
out.starvation = ovl.starvationText(sel.catalogPayload('perf-overlap', { species: 'proton', task: 'energy' }).starvation[0],
  sel.catalogPayload('perf-overlap', { species: 'proton', task: 'energy' }).bins);
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def fixes():
    proc = subprocess.run([NODE, "--input-type=module", "-e", _FIX_SCRIPT, json.dumps([JS.as_uri()])],
                          capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_stored_log10_draws_a_log_angle_axis_with_dots_on_screen_and_in_print(fixes):
    """R2-1 / R3-1: the Angle axis control stores 'log10'; through cardOptions it must reach a log axis."""
    for label in ("log10", "log10-all"):
        case = fixes["log10"][label]
        assert case["angleScale"] == "log10"
        for theme in ("dark", "light", "print"):
            t = case["themes"][theme]
            assert t["axis"] == "log", (label, theme)
            assert t["leaves"] and set(t["leaves"]) == {"circle"}, (label, theme, t["leaves"])
            assert set(t["otherAxes"]) == {"value"}, (label, theme)
            assert any("log₁₀ axis and draws dots" in line for line in t["drawn"]), (label, theme)
    default = fixes["log10"]["default"]
    assert default["angleScale"] == "linear"
    for theme in ("dark", "light", "print"):
        t = default["themes"][theme]
        assert t["axis"] == "value" and set(t["leaves"]) == {"rect"}, theme
    assert fixes["logSpellings"] == ["log", "log", "linear", "linear", "linear"]


def test_the_diagnostics_row_labels_start_inside_the_figure(fixes):
    """R2-2: the gutter is measured from the widest label, so "Per-shower translated" is never cut."""
    labels = fixes["rowLabels"]
    assert {(r["width"]) for r in labels} >= {1100, 321}
    assert any(r["label"] == "Per-shower translated" for r in labels)
    for r in labels:
        assert r["start"] >= 0, r
        assert r["start"] >= r["cellX"] - 0.01, r  # never into the panel on its left


def test_every_text_of_every_option_fits_the_figure_and_overlaps_no_other(fixes):
    """R2-3 / R2-7: every graphic line, tick label, axis name and series text, with the textfit.js estimate,
    at the 321 px single-column export, the 661 px double column and the screen widths: inside the figure,
    and clear of every other text (header lines wrapped, axis names clear of the top tick, the two-line
    window labels stacked); the N strip's counts clear of its neighbouring bars."""
    text = fixes["text"]
    assert text["checked"] > 10000
    assert text["multiline"] > 0  # the momentum window labels: window, then its n
    # Each two-line label sets its own line pitch, so its lines stack apart in the SVG export too.
    assert text["stacked"] and set(text["stacked"]) == {"stacked"}, sorted(set(text["stacked"]))[:5]
    assert text["problems"] == [], "\n".join(text["problems"][:20])


def test_the_bias_axis_keeps_zero_as_a_tick_and_its_labels_apart(fixes):
    for b in fixes["bias"]:
        steps = b["bound"] / b["interval"]
        assert abs(steps - round(steps)) < 1e-9, b  # ±bound and 0 are ticks
        assert 2 * round(steps) <= b["most"], b


def test_the_diagnostics_tables_print_no_decimal_the_report_does_not(fixes):
    """R1-2: Array.map's index never reaches the formatter as a decimal count."""
    report = (ROOT / "models_performance.md").read_text(encoding="utf-8")
    frames = {b["key"]: b["rows"] for b in fixes["blocks"]["all"]}["frames"]
    assert [r[1] for r in frames] == ["≈ 250 × 250 × 53 mm", "≈ 45 × 45 × 55 mm", "≈ 45 × 45 × 55 mm"]
    for species, blocks in fixes["blocks"].items():
        for block in blocks:
            for row in block["rows"]:
                for cell in row:
                    for token in re.findall(r"\d[\d,]*\.\d+", cell):
                        hungarian = token.replace(",", "").replace(".", ",")
                        assert hungarian in report, (species, block["key"], cell, token)
    assert fixes["noneCell"] == "not reported"


def test_the_drawers_bound_f7_name_both_starved_bins_and_read_the_bias_sign(fixes):
    momentum = " ".join(fixes["notes"]["momentum"])
    # R1-5: the bound the rounding leaves, never an exact implication.
    assert "errors average under 0.0005 GeV per particle of the window: (almost) every error has one sign" in momentum
    assert "not an exact implication" in momentum
    assert "every error in such a window has one sign" not in momentum
    assert fixes["bound"] == {"dp": 3, "value": 0.0005, "text": "0.0005"}
    # R1-15: the report's muon reading implies prediction − truth.
    for key in ("momentum", "accuracy"):
        joined = " ".join(fixes["notes"][key])
        assert "states no sign convention" in joined and "implies prediction − truth" in joined, key
    # R1-11: one statement about the two bins together.
    assert fixes["starvation"].startswith(
        "Information starvation (the report): in the 30 % and 40–100 % bins together the particles have a mean momentum of 3.3 GeV")
    overlap = " ".join(fixes["notes"]["overlap"])
    assert "in this bin" not in overlap and "30 % and 40–100 % bins together" in overlap


def test_one_formatter_prints_every_reported_value():
    """R3-2: the Performance cards print through catalog/select.js printed / printedQualified only."""
    for path in MODULES:
        source = path.read_text(encoding="utf-8")
        assert "qualifiedText" not in source, path.name
        assert not re.search(r"function (signed)?[rR]eported\b", source), path.name
        assert not re.search(r"\b(signedReported|reported)\(", source), path.name
        assert "catalog/select.js'" in source, path.name
