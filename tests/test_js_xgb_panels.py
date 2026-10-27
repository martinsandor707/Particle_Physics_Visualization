"""The four XGBoost cards of the models page, executed under Node on the recorded payloads.

Every option builder of the XGBoost cards is a pure function - E1's
`xgbCvOption`, E3's `xgbBinaryOption`, E4's `xgbTreeOption`, E5's
`xgbImportanceOption` - and so are the drawer builders of `xgb_notes.js`. The
script runs each against the payloads `tests/test_payload_fixtures.py`
recorded (`tests/fixtures/payloads/xgb_*.json`), renders every custom series'
`renderItem` with an identity coordinate map, calls every tooltip formatter
and hands back what was drawn. The tests hold each card to CLAUDE.md
section 2:

* the five CV folds are dots (individual observations) and the mean carries a
  capped whisker that is the interval the payload names, never the folds' SD;
* rates carry their Wilson (or the payload's other) interval as capped
  whiskers on the full 0-100 % scale; the confusion counts carry none;
* bars start at zero; the fold-mean bracket of E5 is named and lies apart
  from the bar;
* the surrogate's φ is never coloured; θ and momentum leaves are coloured on
  the legible run of the ramp;
* every drawn colour clears 3:1 against the card, on screen and in print;
* no rendered number uses an ASCII hyphen;
* the tree stays legible in a single-column (321 px) export.

Variants the backend may ship (a corrected CV interval, a Newcombe balanced
accuracy interval, per-node circular statistics, clipped importance
intervals, a split that is not reproduced) are built from the recordings by
changing only the fields the server would change. Skipped without `node`.
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
JS = ROOT / "calosrv" / "static" / "js"
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

CV = ["xgb_cv_momentum", "xgb_cv_angle"]
TREES = ["xgb_surrogate_momentum", "xgb_surrogate_angle"]
IMPORTANCE = ["xgb_importance_momentum", "xgb_importance_angle"]

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const palette = await imp('palette.js');
const cp = await imp('panels/chart_panel.js');
const textfit = await imp('textfit.js');
const cv = await imp('panels/xgb_cv.js');
const bin = await imp('panels/xgb_binary.js');
const tree = await imp('panels/xgb_tree.js');
const imps = await imp('panels/xgb_importance.js');
const xn = await imp('xgb_notes.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1e-5, 12345, -1, 0.975, 1];

function summarise(el) {
  if (!el) return null;
  if (el.type === 'group') return { type: 'group', children: el.children.map(summarise) };
  const pts = el.shape?.points ?? null;
  const fill = el.style?.fill;
  return {
    type: el.type,
    points: pts ? pts.length : null,
    pts: pts && pts.length <= 400 ? pts : null,
    rect: el.type === 'rect' ? el.shape : null,
    circle: el.type === 'circle' ? el.shape : null,
    line: el.type === 'line' ? el.shape : null,
    text: el.style?.text ?? null,
    fontSize: el.style?.fontSize ?? null,
    fill: typeof fill === 'string' ? fill : (fill ? 'gradient' : null),
    stroke: el.style?.stroke ?? null,
    dash: el.style?.lineDash ?? null,
    opacity: el.style?.opacity ?? null,
  };
}

function flatten(el, out = []) {
  if (!el) return out;
  if (el.type === 'group') { for (const c of el.children) flatten(c, out); return out; }
  out.push(el);
  return out;
}

function axisTexts(axis) {
  const out = [];
  for (const a of [].concat(axis ?? [])) {
    if (a.name) out.push(a.name);
    for (const d of a.data ?? []) out.push(String(d));
    const f = a.axisLabel?.formatter;
    if (typeof f === 'function') for (const v of SAMPLES) out.push(String(f(v)));
  }
  return out;
}

function walk(option) {
  const strings = [...axisTexts(option.xAxis), ...axisTexts(option.yAxis)];
  const graphics = [];
  for (const g of option.graphic ?? []) {
    graphics.push({ type: g.type, text: g.style?.text ?? null, fill: typeof g.style?.fill === 'string' ? g.style.fill : (g.style?.fill ? 'gradient' : null),
      stops: g.style?.fill?.colorStops?.map((s) => s.color) ?? null, fontSize: g.style?.fontSize ?? null });
    if (g.style?.text) strings.push(g.style.text);
  }
  for (const l of [].concat(option.legend ?? [])) for (const d of l.data ?? []) strings.push(String(d?.name ?? d));
  const series = option.series.map((s) => {
    const items = [];
    for (let i = 0; i < (s.data ?? []).length; i += 1) {
      const datum = s.data[i];
      const value = Array.isArray(datum) ? datum : datum?.value;
      const el = typeof s.renderItem === 'function' ? s.renderItem({ dataIndex: i, coordSys }, api) : null;
      const tip = typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter({ dataIndex: i, value }) : null;
      if (tip) strings.push(tip);
      const leaves = flatten(summarise(el));
      for (const c of leaves) if (c?.text) strings.push(c.text);
      items.push({ el: summarise(el), leaves, tip, value });
    }
    return { name: s.name, type: s.type, silent: Boolean(s.silent), coordinateSystem: s.coordinateSystem ?? null,
      xAxisIndex: s.xAxisIndex ?? 0, colour: s.itemStyle?.color ?? null, items };
  });
  const axis = (a) => [].concat(a ?? []).map((x) => ({ type: x.type, name: x.name ?? '', min: x.min ?? null, max: x.max ?? null,
    data: x.data ?? null, inverse: Boolean(x.inverse) }));
  return {
    series, strings, graphics,
    xAxis: axis(option.xAxis), yAxis: axis(option.yAxis),
    grid: [].concat(option.grid ?? []),
    legend: [].concat(option.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => d?.name ?? d)),
    tooltip: { confine: option.tooltip?.confine ?? null, appendTo: option.tooltip?.appendTo ?? null },
  };
}

const pack = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
  sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);

function render(theme) {
  const res = { cv: {}, binary: {}, tree: {}, importance: {}, colours: {} };
  const W = { width: 560, height: 330 };
  const narrow = (m) => ({ width: 321, height: m });
  for (const name of %(cv)s) {
    const p = load(name);
    res.cv[name] = {
      card: walk(cv.xgbCvOption(p, {}, W)),
      export: walk(cv.xgbCvOption(p, {}, narrow(cv.cvLayout(cv.cvModel(p), 321, null).height))),
      exportLines: cv.cvLayout(cv.cvModel(p), 321, null).lines.map((l) => l.panels.length),
      axes: cv.cvModel(p).rows.flatMap((r) => r.panels.map((q) => ({ id: q.id, ...cv.cvAxis(q) }))),
    };
  }
  {
    const p = load('xgb_binary');
    const h = bin.binaryLayout(bin.binaryModel(p), 321, null).height;
    res.binary = { card: walk(bin.xgbBinaryOption(p, {}, W)), export: walk(bin.xgbBinaryOption(p, {}, narrow(h))),
      stacked: bin.binaryLayout(bin.binaryModel(p), 321, null).stacked, side: bin.binaryLayout(bin.binaryModel(p), 560, 330).stacked };
  }
  for (const name of %(trees)s) {
    const p = load(name);
    const labels = p.labels;
    res.tree[name] = {};
    for (const label of labels) {
      const opts = { label, palette: 'viridis' };
      const m = tree.treeModel(p, opts);
      const out = {};
      for (const width of [1100, 700, 321]) {
        const lay = tree.treeLayout(m, width, width === 321 ? null : 330);
        const chart = walk(tree.xgbTreeOption(p, opts, { width, height: lay.height }));
        out[width] = { kind: lay.kind, height: lay.height, overflow: lay.overflow ?? false, chart,
          boxes: lay.placed.map((b) => ({ x: b.x, w: b.w, lines: (b.lines ?? tree.nodeLines(b.node)),
            widths: (b.lines ?? tree.nodeLines(b.node)).map((t) => textfit.measureText(t, scale.THEME.fontLabel, scale.THEME.fontFamily)),
            padX: lay.padX })) };
      }
      out.coloured = m.coloured;
      out.leafColours = m.nodes.filter((n) => n.leaf).map((n) => n.colour);
      out.allColours = m.nodes.map((n) => n.colour);
      out.font = scale.THEME.fontLabel;
      res.tree[name][label] = out;
    }
  }
  for (const name of %(imp)s) {
    const p = load(name);
    const m = imps.importanceModel(p);
    res.importance[name] = { card: walk(imps.xgbImportanceOption(p, {}, { width: 1100, height: 330 })),
      export: walk(imps.xgbImportanceOption(p, {}, { width: 321, height: imps.importanceLayout(m, 321, null).height })),
      shown: m.shown.map((f) => f.name), hidden: m.hiddenUsed.length, unused: m.unused.length, colours: m.colours };
  }
  res.colours.frames = Object.values(imps.frameColours());
  res.colours.text = [scale.THEME.text, scale.THEME.muted, scale.THEME.accent];
  res.card = scale.THEME.card;
  return res;
}

const out = { screen: render('screen') };
Object.assign(scale.THEME, PRINT_TOKENS);
out.print = render('print');
// The single-column export of each card, as the exporter asks the class for it.
{
  const element = { clientWidth: 900, clientHeight: 330, style: {}, classList: { toggle: () => {} }, closest: () => null };
  const chart = { getWidth: () => element.clientWidth, getHeight: () => element.clientHeight, setOption: () => {}, resize: () => {},
    clear: () => {}, getDom: () => element, dispatchAction: () => {}, on: () => {}, getZr: () => ({ on: () => {} }) };
  globalThis.echarts = { init: () => chart };
  out.exportMetrics = {};
  const classes = { XgbCvPanel: [cv.XgbCvPanel, 'xgb_cv_momentum', {}], XgbBinaryPanel: [bin.XgbBinaryPanel, 'xgb_binary', {}],
    XgbTreePanel: [tree.XgbTreePanel, 'xgb_surrogate_momentum', {}], XgbImportancePanel: [imps.XgbImportancePanel, 'xgb_importance_momentum', {}] };
  for (const [name, [P, fixture, opts]] of Object.entries(classes)) {
    const panel = new P(element, { card: 'x' });
    panel.lastPayload = load(fixture);
    panel.lastOpts = opts;
    out.exportMetrics[name] = panel.exportMetrics(321);
  }
}
scale.restoreScreenTheme();

/* ---- panel classes, with a fake DOM and a fake ECharts ---------------------- */
{
  const element = { clientWidth: 1100, clientHeight: 330, style: {}, classList: { toggle: () => {} }, closest: () => null };
  let last = null;
  const chart = { getWidth: () => element.clientWidth, getHeight: () => element.clientHeight, setOption: (o) => { last = o; }, resize: () => {},
    clear: () => {}, getDom: () => element, dispatchAction: () => {}, on: () => {}, getZr: () => ({ on: () => {} }) };
  globalThis.echarts = { init: () => chart };
  const classes = {
    XgbCvPanel: [cv.XgbCvPanel, 'xgb_cv_angle', { task: 'angle' }],
    XgbBinaryPanel: [bin.XgbBinaryPanel, 'xgb_binary', {}],
    XgbTreePanel: [tree.XgbTreePanel, 'xgb_surrogate_angle', { task: 'angle', label: 'phi' }],
    XgbImportancePanel: [imps.XgbImportancePanel, 'xgb_importance_angle', { task: 'angle' }],
  };
  out.panels = {};
  for (const [name, [P, fixture, opts]] of Object.entries(classes)) {
    const panel = new P(element, { card: 'card' });
    panel.render(load(fixture), { palette: 'viridis', card: 'card', ...opts });
    out.panels[name] = { kind: panel.kind, series: last.series.length, liveGrid: panel.liveGrid,
      lastOpts: Object.keys(panel.lastOpts) };
    panel.clear();
    out.panels[name].cleared = panel.lastPayload === null;
  }
}

/* ---- payload variants the backend may ship -------------------------------- */
{
  const v = {};
  const corrected = clone(load('xgb_cv_momentum'));
  corrected.interval.label = '95%% Nadeau–Bengio corrected Student-t interval of the mean (4 d.o.f.)';
  v.cvCorrected = walk(cv.xgbCvOption(corrected, {}, { width: 560, height: 330 }));
  const newcombe = clone(load('xgb_binary'));
  const ba = newcombe.rates.find((r) => r.id === 'balanced_accuracy');
  ba.interval = { ...ba.interval, method: 'newcombe', label: '95%% Newcombe (MOVER) interval from the two Wilson limits' };
  v.binaryNewcombe = walk(bin.xgbBinaryOption(newcombe, {}, { width: 560, height: 330 }));
  const undef = clone(load('xgb_binary'));
  const prec = undef.rates.find((r) => r.id === 'precision_1');
  prec.value = null; prec.k = 0; prec.n = 0; prec.interval = null;
  v.binaryUndefined = walk(bin.xgbBinaryOption(undef, {}, { width: 560, height: 330 }));
  v.binaryUndefinedNotes = pack(xn.xgbBinaryNotes({ payload: undef }));
  const circ = clone(load('xgb_surrogate_angle'));
  for (const n of circ.nodes) n.circular = { phi: { mean: n.values.phi, resultant: 0.9 } };
  v.treeCircular = walk(tree.xgbTreeOption(circ, { label: 'phi' }, { width: 1100, height: 330 }));
  v.treeCircularNotes = pack(xn.xgbTreeNotes({ payload: circ, label: 'phi' }));
  const told = clone(load('xgb_surrogate_angle'));
  // The backend's own instruction (label_info[], color_by), not the panel's guess.
  told.label_info = told.label_info.map((l) => (l.name === 'theta' ? { ...l, coloured: false } : l));
  told.color_by.theta = false;
  v.treeTold = tree.treeModel(told, { label: 'theta' }).coloured;
  // An older payload without per-node circular statistics: the linear mean, named and flagged.
  const noCirc = clone(load('xgb_surrogate_angle'));
  for (const n of noCirc.nodes) delete n.circular;
  v.treeNoCircular = { boxes: tree.treeModel(noCirc, { label: 'phi' }).nodes.map((n) => tree.nodeLines(n).at(-1)),
    notes: pack(xn.xgbTreeNotes({ payload: noCirc, label: 'phi' })) };
  // The electron angle surrogate's measured fidelities (R5c): phi 0.978, theta 0.004, average 0.491.
  const real = clone(load('xgb_surrogate_angle'));
  real.fidelity.outputs = { phi: { r2: 0.978, mae: 0.0503 }, theta: { r2: 0.004, mae: 0.0118 } };
  real.fidelity.r2 = 0.491;
  v.treeFidelity = {};
  for (const label of ['phi', 'theta']) {
    const m = tree.treeModel(real, { label });
    v.treeFidelity[label] = { texts: tree.fidelityTexts(m), fidelity: m.fidelity,
      header: walk(tree.xgbTreeOption(real, { label }, { width: 1100, height: 330 })).graphics.map((g) => g.text).filter(Boolean),
      notes: pack(xn.xgbTreeNotes({ payload: real, label })) };
  }
  v.r2Texts = [tree.fidelityR2Text(1, 0), tree.fidelityR2Text(1, 0.2), tree.fidelityR2Text(0.999999, 0.1), tree.fidelityR2Text(0.24, 3)];
  // The Rayleigh gate: a node whose predicted azimuths share no direction prints no mean.
  const spread = clone(load('xgb_surrogate_angle'));
  spread.nodes[0].circular.phi = { mean: 2.5, resultant: 0.05 };
  spread.nodes[0].n = 100;
  const sm = tree.treeModel(spread, { label: 'phi' });
  const root = sm.nodes.find((n) => n.depth === 0);
  v.treeRayleigh = { box: tree.nodeLines(root).at(-1), tip: tree.nodeTip(sm, root), circ: tree.circularOf(root, 'phi') };
  const clipped = clone(load('xgb_importance_momentum'));
  clipped.features[4].clipped = true;
  v.importanceClipped = { chart: walk(imps.xgbImportanceOption(clipped, {}, { width: 1100, height: 330 })),
    notes: pack(xn.xgbImportanceNotes({ payload: clipped })) };
  v.cvMeanTip = walk(cv.xgbCvOption(load('xgb_cv_momentum'), {}, { width: 560, height: 330 })).series
    .filter((x) => x.name === 'Mean of the folds').flatMap((x) => x.items.map((i) => i.tip));
  const many = clone(load('xgb_importance_momentum'));
  many.features.forEach((f, i) => { f.shipped = (52 - i) / 1378; });
  const manyModel = imps.importanceModel(many);
  v.importanceMany = { shown: manyModel.shown.length, hidden: manyModel.hiddenUsed.length, unused: manyModel.unused.length,
    chart: walk(imps.xgbImportanceOption(many, {}, { width: 1100, height: 330 })), notes: pack(xn.xgbImportanceNotes({ payload: many })) };
  const broken = {};
  for (const name of ['xgb_cv_momentum', 'xgb_binary', 'xgb_surrogate_momentum', 'xgb_importance_momentum']) {
    const p = clone(load(name));
    p.run.split.reproduced = false;
    p.run.split.warning = 'validation / training MSE at random_state 42 does not exceed the others: split not reproduced';
    p.meta.warnings = [p.run.split.warning];
    broken[name] = p;
  }
  v.splitBroken = {
    cv: pack(xn.xgbCvNotes({ payload: broken.xgb_cv_momentum })),
    binary: pack(xn.xgbBinaryNotes({ payload: broken.xgb_binary })),
    tree: pack(xn.xgbTreeNotes({ payload: broken.xgb_surrogate_momentum })),
    importance: pack(xn.xgbImportanceNotes({ payload: broken.xgb_importance_momentum })),
  };
  v.empty = [cv.xgbCvOption({}, {}, {}), bin.xgbBinaryOption({}, {}, {}), tree.xgbTreeOption({}, {}, {}), imps.xgbImportanceOption({}, {}, {})]
    .map((o) => (o.graphic ?? []).map((g) => g.style?.text).join(' '));
  out.variants = v;
}

/* ---- drawer notes ---------------------------------------------------------- */
{
  const ex = { display_name: 'Demo' };
  out.notes = {
    cv: Object.fromEntries(%(cv)s.map((p) => [p, pack(xn.xgbCvNotes({ payload: load(p), experiment: ex, task: 'x' }))])),
    binary: pack(xn.xgbBinaryNotes({ payload: load('xgb_binary'), experiment: ex })),
    tree: Object.fromEntries(%(trees)s.flatMap((p) => load(p).labels.map((l) => [`${p}:${l}`, pack(xn.xgbTreeNotes({ payload: load(p), label: l }))]))),
    importance: Object.fromEntries(%(imp)s.map((p) => [p, pack(xn.xgbImportanceNotes({ payload: load(p) }))])),
    titled: xn.xgbCvNotes({ payload: load('xgb_cv_momentum'), title: 'Card title' }).title,
    empty: [xn.xgbCvNotes({}), xn.xgbTreeNotes({ payload: null })],
    builders: xn.XGB_NOTE_BUILDERS,
    exported: Object.values(xn.XGB_NOTE_BUILDERS).map((b) => typeof xn[b]),
    section: (await imp('panel_notes.js')).SECTION,
  };
}

/* ---- palette references ------------------------------------------------------ */
out.qualitative = { set2: palette.qualitativeStops('set2', 4), dark2: palette.qualitativeStops('dark2', 4) };

console.log(JSON.stringify(out));
"""


def _script() -> str:
    return _SCRIPT % {"cv": json.dumps(CV), "trees": json.dumps(TREES), "imp": json.dumps(IMPORTANCE)}


@pytest.fixture(scope="module")
def out() -> dict:
    """Run the harness once; every test reads its part."""
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _script(), args],
                          capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _named(chart: dict, pattern: str) -> list[dict]:
    return [s for s in chart["series"] if re.search(pattern, s["name"] or "")]


def _rgb(colour: str) -> tuple[float, float, float]:
    text = colour.strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", text)
    if m:
        v = int(m.group(1), 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+).*\)", text)
    assert m, colour
    return tuple(float(m.group(i)) for i in (1, 2, 3))


def _luminance(rgb) -> float:
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(_rgb(a)), _luminance(_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _is_clear(colour) -> bool:
    if colour in (None, "none", "transparent", "gradient"):
        return True
    return bool(re.fullmatch(r"rgba\([^)]*,\s*0(\.0*)?\s*\)", str(colour).replace(" ", "")))


def _charts(theme: dict):
    for name in CV:
        yield f"cv:{name}", theme["cv"][name]["card"]
        yield f"cv-export:{name}", theme["cv"][name]["export"]
    yield "binary", theme["binary"]["card"]
    yield "binary-export", theme["binary"]["export"]
    for name in TREES:
        for label, entry in theme["tree"][name].items():
            for width in ("1100", "700", "321"):
                yield f"tree:{name}:{label}:{width}", entry[width]["chart"]
    for name in IMPORTANCE:
        yield f"imp:{name}", theme["importance"][name]["card"]
        yield f"imp-export:{name}", theme["importance"][name]["export"]


def _note_lines(notes: dict):
    for lines in notes["sections"].values():
        yield from lines


# ------------------------------------------------------------------- all --


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_every_recorded_payload_renders_with_marks(out, theme):
    for key, chart in _charts(out[theme]):
        drawn = [s for s in chart["series"] if s["items"]]
        assert drawn, key
        assert chart["tooltip"]["confine"] is False and chart["tooltip"]["appendTo"] == "#tooltip-layer", key


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_every_drawn_colour_clears_three_to_one_against_the_card(out, theme):
    card = out[theme]["card"]
    for key, chart in _charts(out[theme]):
        for s in chart["series"]:
            for item in s["items"]:
                for el in item["leaves"]:
                    if el["type"] == "text":
                        continue
                    for colour in (el["fill"], el["stroke"]):
                        if _is_clear(colour) or colour.lower() == card.lower():
                            continue
                        assert _contrast(colour, card) >= 3 - 1e-9, f"{key} / {s['name']}: {colour} on {card}"
        for g in chart["graphics"]:
            for colour in g["stops"] or []:
                assert _contrast(colour, card) >= 3 - 1e-9, f"{key}: ramp stop {colour}"
    for colour in out[theme]["colours"]["frames"] + out[theme]["colours"]["text"]:
        assert _contrast(colour, card) >= 3, colour


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_no_rendered_number_uses_a_hyphen(out, theme):
    strings = [t for _, chart in _charts(out[theme]) for t in chart["strings"]]
    for group in out["notes"].values():
        if isinstance(group, dict) and "sections" in group:
            strings.extend(_note_lines(group))
        elif isinstance(group, dict):
            for notes in group.values():
                if isinstance(notes, dict) and "sections" in notes:
                    strings.extend(_note_lines(notes))
    assert strings
    for text in strings:
        visible = re.sub(r"<[^>]+>", " ", str(text))
        assert not HYPHEN_NUMBER.search(visible), f"hyphen-minus before a digit in: {visible!r}"
    leaf = [t for t in out["screen"]["tree"]["xgb_surrogate_angle"]["phi"]["1100"]["chart"]["strings"] if "0.144" in t]
    assert leaf and all("−0.144" in t for t in leaf)


# -------------------------------------------------------------------- E1 --


@pytest.mark.parametrize("name", CV)
def test_cv_folds_are_dots_and_the_mean_carries_the_payloads_capped_interval(out, name):
    payload = _load(name)
    chart = out["screen"]["cv"][name]["card"]
    label = payload["interval"]["label"]
    dots = _named(chart, r"^Fold value \(one observation each\)$")
    whiskers = [s for s in chart["series"] if s["name"] == label]
    means = _named(chart, r"^Mean of the folds$")
    assert dots and whiskers and means
    assert len(dots) == len(whiskers) == len(means)
    assert set(chart["legend"]) == {"Fold value (one observation each)", "Mean of the folds", label}
    slots = sum(len(w["items"]) for w in whiskers)
    assert sum(len(d["items"]) for d in dots) == 5 * slots
    assert all(i["el"]["type"] == "circle" for d in dots for i in d["items"])
    assert all(i["el"]["type"] == "polygon" for m in means for i in m["items"])
    t95 = {tuple(sorted((round(v, 12) for v in s["t95"]))) for s in payload["summary"].values()}
    if payload["per_label"]:
        for block in payload["per_label"].values():
            t95 |= {tuple(sorted((round(v, 12) for v in s["t95"]))) for s in block["summary"].values()}
    for w in whiskers:
        for item in w["items"]:
            pts = item["el"]["pts"]
            assert item["el"]["points"] == 6, "a mean's interval has both caps"
            ys = sorted({round(p[1], 12) for p in pts})
            assert (ys[0], ys[-1]) in t95, "the whisker is the payload's interval, not the SD"
            assert "uncertainty of the mean" in item["tip"] and label in item["tip"]
            assert "not drawn" in item["tip"] and "SD of the folds" in item["tip"]
    tips = " ".join(i["tip"] for d in dots for i in d["items"])
    assert "one observation" in tips


@pytest.mark.parametrize("name", CV)
def test_every_fold_value_is_reachable_in_a_tooltip_and_listed_in_the_drawer(out, name):
    payload = _load(name)
    chart = out["screen"]["cv"][name]["card"]
    tips = [i["tip"] for d in _named(chart, r"^Fold value") for i in d["items"]]
    drawer = out["notes"]["cv"][name]["sections"]["Fold values"]
    assert len(drawer) >= 5
    for k, fold in enumerate(payload["folds"]):
        assert any(f"Fold {k + 1} of 5" in t for t in tips)
        assert drawer[k].startswith(f"Fold {k + 1} ")
        assert str(fold["n_val"]) in drawer[k]


@pytest.mark.parametrize("name", CV)
def test_error_axes_start_at_zero_and_a_truncated_r2_axis_is_marked(out, name):
    entry = out["screen"]["cv"][name]
    chart = entry["card"]
    for axis in entry["axes"]:
        if not axis["id"].endswith("r2"):
            assert axis["min"] == 0 and not axis["truncated"]
        else:
            assert axis["max"] == 1
    truncated = [a for a in entry["axes"] if a["truncated"]]
    breaks = _named(chart, r"^Axis break")
    assert len(breaks) == len(truncated)
    for b in breaks:
        assert "does not start at 0" in b["items"][0]["tip"]
    for index, axis in enumerate(chart["yAxis"]):
        assert axis["min"] is not None and axis["max"] is not None


def test_the_angle_card_keeps_parity_and_per_label_apart(out):
    chart = out["screen"]["cv"]["xgb_cv_angle"]["card"]
    headings = chart["graphics"][0]["text"], [g["text"] for g in chart["graphics"]]
    assert any(t.startswith("Notebook parity") for t in headings[1])
    assert any(t.startswith("Per label") for t in headings[1])
    categories = [a["data"] for a in chart["xAxis"]]
    assert ["θ", "φ"] in categories and ["parity"] in categories
    assert not any("φ" in c and "parity" in c for c in categories)


def test_cv_flows_into_lines_in_a_single_column_export(out):
    assert out["print"]["cv"]["xgb_cv_momentum"]["exportLines"] == [2, 2]
    assert out["exportMetrics"]["XgbCvPanel"]["height"] > 250


def test_a_corrected_interval_is_drawn_under_the_payloads_own_name(out):
    chart = out["variants"]["cvCorrected"]
    name = "95% Nadeau–Bengio corrected Student-t interval of the mean (4 d.o.f.)"
    assert name in chart["legend"]
    assert all(name in i["tip"] for s in chart["series"] if s["name"] == name for i in s["items"])


# -------------------------------------------------------------------- E3 --


def test_the_balanced_accuracy_carries_the_recorded_mover_interval(out):
    payload = _load("xgb_binary")
    ba = next(r for r in payload["rates"] if r["id"] == "balanced_accuracy")
    assert ba["interval"]["method"] == "mover" and "MOVER" in ba["interval"]["label"]
    chart = out["screen"]["binary"]["card"]
    assert any(name.startswith(ba["interval"]["label"]) for name in chart["legend"])
    narrow = out["print"]["binary"]["export"]["legend"]
    assert any("MOVER" in name for name in narrow), "the narrow legend keeps the method's name"
    rates = " ".join(out["notes"]["binary"]["sections"]["Rates"])
    assert ba["interval"]["label"] in rates and "bootstrap" not in rates


def test_rates_carry_wilson_whiskers_on_the_full_percent_scale(out):
    payload = _load("xgb_binary")
    chart = out["screen"]["binary"]["card"]
    assert chart["xAxis"][0]["min"] == 0 and chart["xAxis"][0]["max"] == 100
    wilson = _named(chart, r"^95% Wilson score interval$")
    assert len(wilson) == 1
    rates = {r["id"]: r for r in payload["rates"]}
    expected = [r for r in payload["rates"] if r["interval"] and r["interval"]["method"] == "wilson"]
    assert len(wilson[0]["items"]) == len(expected)
    spans = sorted((round(min(p[0] for p in i["el"]["pts"]), 6), round(max(p[0] for p in i["el"]["pts"]), 6))
                   for i in wilson[0]["items"])
    assert spans == sorted((round(100 * r["interval"]["lo"], 6), round(100 * r["interval"]["hi"], 6)) for r in expected)
    ba = rates["balanced_accuracy"]
    other = [s for s in chart["series"] if s["name"].startswith(ba["interval"]["label"])]
    assert len(other) == 1 and len(other[0]["items"]) == 1
    assert ba["interval"]["label"] in other[0]["items"][0]["tip"]
    for s in wilson + other:
        for item in s["items"]:
            assert item["el"]["points"] == 6 and "uncertainty of the rate" in item["tip"]
    assert sorted(chart["yAxis"][0]["data"]) == sorted(["Accuracy", "Balanced accuracy", "Recall, class 1", "Recall, class 0",
                                                        "Precision, class 1", "Precision, class 0"])
    minority = [i["tip"] for s in wilson for i in s["items"] if "minority class" in i["tip"]]
    assert minority


def test_the_confusion_matrix_is_counts_without_intervals_and_states_the_minority(out):
    payload = _load("xgb_binary")
    chart = out["screen"]["binary"]["card"]
    (cells,) = _named(chart, r"^Confusion counts$")
    assert cells["coordinateSystem"] == "none" and len(cells["items"]) == 4
    counts = [payload["confusion"][k] for k in ("tn", "fp", "fn", "tp")]
    drawn = [int(next(e["text"] for e in i["leaves"] if e["type"] == "text").replace(",", "")) for i in cells["items"]]
    assert drawn == counts
    for item in cells["items"]:
        assert "no interval" in item["tip"]
    texts = [g["text"] for g in chart["graphics"]]
    assert any("(minority)" in t and "20 rows" in t for t in texts)
    assert any("minority class has 20 rows" in t.lower() or "The minority class" in t for t in texts)
    printed = [g["text"] for g in out["print"]["binary"]["card"]["graphics"]]
    assert any("(minority)" in t for t in printed)


def test_binary_stacks_in_a_single_column_export(out):
    assert out["print"]["binary"]["stacked"] is True and out["screen"]["binary"]["side"] is False
    assert out["exportMetrics"]["XgbBinaryPanel"]["height"] > 330


def test_a_newcombe_interval_and_an_undefined_rate_are_drawn_as_the_payload_says(out):
    chart = out["variants"]["binaryNewcombe"]
    assert any(n.startswith("95% Newcombe (MOVER) interval") for n in chart["legend"])
    undefined = out["variants"]["binaryUndefined"]
    (row,) = _named(undefined, r"^Undefined rate$")
    assert "undefined" in row["items"][0]["tip"]
    points = _named(undefined, r"^Rate \(point estimate\)$")
    assert len(points[0]["items"]) == 5
    assert "undefined rate" in out["variants"]["binaryUndefinedNotes"]["hazards"]


# -------------------------------------------------------------------- E4 --


def test_the_tree_draws_every_node_with_its_numbers(out):
    for name in TREES:
        payload = _load(name)
        for label, entry in out["screen"]["tree"][name].items():
            chart = entry["1100"]["chart"]
            (nodes,) = _named(chart, r"^Surrogate tree nodes$")
            assert len(nodes["items"]) == len(payload["nodes"])
            for item in nodes["items"]:
                assert "within-node SD" in item["tip"] and "no interval" in item["tip"]
            assert not _named(chart, r"interval|whisker")


def test_momentum_leaves_are_coloured_on_the_legible_ramp_and_phi_is_not(out):
    for theme in ("screen", "print"):
        card = out[theme]["card"]
        mom = out[theme]["tree"]["xgb_surrogate_momentum"]["momentum"]
        assert mom["coloured"] is True
        assert all(_contrast(c, card) >= 3 for c in mom["leafColours"])
        theta = out[theme]["tree"]["xgb_surrogate_angle"]["theta"]
        assert theta["coloured"] is True
        phi = out[theme]["tree"]["xgb_surrogate_angle"]["phi"]
        assert phi["coloured"] is False and all(c is None for c in phi["allColours"])
        chart = phi["1100"]["chart"]
        assert not any(g["stops"] for g in chart["graphics"]), "no ramp for an azimuth"
        assert any("not coloured" in (g["text"] or "") for g in chart["graphics"])
        (nodes,) = _named(chart, r"^Surrogate tree nodes$")
        assert all(e["fill"] == card for i in nodes["items"] for e in i["leaves"] if e["type"] == "rect")
        assert all("linear mean" in i["tip"] for i in nodes["items"])
    assert out["variants"]["treeTold"] is False


def test_leaf_text_is_legible_on_its_fill(out):
    for theme in ("screen", "print"):
        chart = out[theme]["tree"]["xgb_surrogate_momentum"]["momentum"]["1100"]["chart"]
        (nodes,) = _named(chart, r"^Surrogate tree nodes$")
        for item in nodes["items"]:
            rect = next(e for e in item["leaves"] if e["type"] == "rect")
            for text in (e for e in item["leaves"] if e["type"] == "text"):
                assert _contrast(text["fill"], rect["fill"]) >= 4.5, (theme, rect["fill"], text["fill"])


def test_the_tree_is_an_outline_that_fits_a_single_column_export(out):
    for name in TREES:
        for label, entry in out["print"]["tree"][name].items():
            narrow = entry["321"]
            assert narrow["kind"] == "outline" and narrow["overflow"] is False
            assert entry["font"] >= 12, "9 pt print type"
            for box in narrow["boxes"]:
                assert box["x"] >= 0 and box["x"] + box["w"] <= 321 + 1e-6
                for width in box["widths"]:
                    assert width + 2 * box["padX"] <= box["w"] + 1e-6 or " " not in "".join(box["lines"])
            texts = [e for s in narrow["chart"]["series"] for i in s["items"] for e in i["leaves"] if e["type"] == "text"]
            assert texts and all(t["fontSize"] >= 12 for t in texts)
    assert out["exportMetrics"]["XgbTreePanel"]["height"] > 300
    wide = out["screen"]["tree"]["xgb_surrogate_momentum"]["momentum"]["1100"]
    assert wide["kind"] == "top-down"


def test_a_circular_statistic_per_node_is_printed_and_explained(out):
    """φ is never averaged arithmetically on the card: each box prints circular.phi (CLAUDE.md section 2)."""
    chart = out["variants"]["treeCircular"]
    (nodes,) = _named(chart, r"^Surrogate tree nodes$")
    assert all(any("R̄" in (e["text"] or "") for e in i["leaves"]) for i in nodes["items"])
    assert all("resultant length" in i["tip"] for i in nodes["items"])
    notes = out["variants"]["treeCircularNotes"]
    assert "Circular quantities" in notes["headings"]
    # The recorded tree's own circular.phi: each box prints its circular mean, never the linear one.
    chart = out["screen"]["tree"]["xgb_surrogate_angle"]["phi"]["1100"]["chart"]
    (nodes,) = _named(chart, r"^Surrogate tree nodes$")
    payload = _load("xgb_surrogate_angle")
    for item, node in zip(nodes["items"], payload["nodes"]):
        texts = " ".join(e["text"] or "" for e in item["leaves"])
        assert "circ." in texts or "no common direction" in texts
        assert "linear mean" in item["tip"] and "notebook parity" in item["tip"]
    recorded = out["notes"]["tree"]["xgb_surrogate_angle:phi"]
    assert "linear mean of an azimuth" not in recorded["hazards"]
    circular = " ".join(recorded["sections"]["Circular quantities"])
    assert payload["notes"]["circular"] in circular and "Rayleigh" in circular
    # Without the statistic (an older payload) the box names the linear mean and the drawer flags it.
    old = out["variants"]["treeNoCircular"]
    assert all(box.startswith("linear ") for box in old["boxes"])
    assert "linear mean of an azimuth" in old["notes"]["hazards"]


def test_a_node_whose_azimuths_share_no_direction_prints_no_mean(out):
    r = out["variants"]["treeRayleigh"]
    assert r["circ"]["directed"] is False and r["circ"]["p"] == pytest.approx(math.exp(-100 * 0.05 ** 2))
    assert r["box"].startswith("no common direction") and "2.5" not in r["box"]
    assert "no mean is printed" in r["tip"]


def test_surrogate_fidelity_is_printed_and_judged_per_output(out):
    """Martin (2026-10-27): the warning per output below R² 0.5; never on, or only, the average."""
    for label, entry in out["variants"]["treeFidelity"].items():
        outputs = {o["label"]: o for o in entry["fidelity"]["outputs"]}
        assert outputs["theta"]["low"] is True and outputs["phi"]["low"] is False
        assert entry["notes"]["hazards"].count("low surrogate fidelity (θ)") == 1
        assert not any("(φ)" in h or "φ, θ" in h for h in entry["notes"]["hazards"])
        subtitle = entry["texts"][0]
        assert "φ R² 0.978" in subtitle and "θ R² 0.004" in subtitle and "0.491" not in subtitle
        assert "low fidelity: θ below R² 0.5" in subtitle
        assert any("φ R² 0.978" in t and "θ R² 0.004" in t for t in entry["header"]), "both outputs on the card"
        disclosures = " ".join(entry["notes"]["sections"]["Disclosures"])
        assert "below 0.5" in disclosures and "never judged" in disclosures and "R² 0.491" in disclosures
        assert "θ: R² 0.004 is below 0.5" in disclosures and "φ: R² 0.978 is below" not in disclosures
    # The recorded near-perfect fixture prints its exact 1 beside an MAE of 0, never "R² 1" from a rounding.
    assert out["variants"]["r2Texts"] == ["1", "> 0.999999", "0.9999990", "0.240"]
    recorded = out["notes"]["tree"]["xgb_surrogate_angle:theta"]
    assert not any(h.startswith("low surrogate fidelity") for h in recorded["hazards"])
    assert "φ R² 1, MAE 0 rad; θ R² 1, MAE 0 rad" in recorded["sections"]["Disclosures"][0]
    momentum = out["notes"]["tree"]["xgb_surrogate_momentum:momentum"]
    assert "low surrogate fidelity" in momentum["hazards"]
    assert momentum["sections"]["Disclosures"][0].startswith("Fidelity to the booster: R² 0.240, MAE 3.57 GeV")


def test_the_cv_mean_names_the_corrected_se(out):
    payload = _load("xgb_cv_momentum")
    assert payload["interval"]["method"] == "corrected_resampled_t"
    tips = out["variants"]["cvMeanTip"]
    assert tips and all("corrected SE of the mean (√0.45 × SD" in t for t in tips)
    folds = out["notes"]["cv"]["xgb_cv_momentum"]["sections"]["Fold values"]
    assert any("corrected SE" in line for line in folds)
    legend = out["screen"]["cv"]["xgb_cv_momentum"]["card"]["legend"]
    assert payload["interval"]["label"] in legend, "the payload's Nadeau–Bengio label names the whisker"


# -------------------------------------------------------------------- E5 --


@pytest.mark.parametrize("name", IMPORTANCE)
def test_importance_bars_start_at_zero_and_are_the_shipped_model(out, name):
    payload = _load(name)
    chart = out["screen"]["importance"][name]["card"]
    shipped = {f["name"]: f["shipped"] for f in payload["features"]}
    rows = chart["yAxis"][0]["data"]
    assert chart["yAxis"][0]["inverse"] and chart["xAxis"][0]["min"] == 0
    frames = [s for s in chart["series"] if s["name"] in ("Absolute frame", "Per-shower translated", "Local frame", "No frame (a count)")]
    assert frames
    for s in frames:
        for item in s["items"]:
            rect = item["el"]["rect"]
            assert rect["x"] == 0, "a bar starts at zero"
            row = rows[int(round(item["value"][1]))]
            assert rect["width"] == pytest.approx(100 * shipped[row])
            assert "the bar, one booster" in item["tip"]


@pytest.mark.parametrize("name", IMPORTANCE)
def test_fold_dots_and_the_named_envelope_sit_apart_from_the_bar(out, name):
    payload = _load(name)
    chart = out["screen"]["importance"][name]["card"]
    envelope = f"Fold mean · {payload['interval']['label']}"
    assert envelope in chart["legend"] and "Fold refit (5, one dot each)" in chart["legend"]
    rows = chart["yAxis"][0]["data"]
    (dots,) = _named(chart, r"^Fold refit")
    assert len(dots["items"]) == 5 * len(rows)
    brackets = [s for s in chart["series"] if s["name"] == envelope]
    assert len(brackets) == 2
    whisker = next(s for s in brackets if s["items"] and s["items"][0]["el"]["type"] == "polyline")
    for item in whisker["items"]:
        assert item["el"]["points"] == 6 and "uncertainty of the mean" in item["tip"]
        ys = {round(p[1], 9) for p in item["el"]["pts"] if True}
        assert max(ys) > min(ys)
    bars = [s for s in chart["series"] if s["name"] in ("Absolute frame", "Per-shower translated", "Local frame", "No frame (a count)")]
    bar_bottoms = {round(i["el"]["rect"]["y"] + i["el"]["rect"]["height"] - i["value"][1], 6) for s in bars for i in s["items"]}
    dot_ys = {round(i["el"]["circle"]["cy"] - i["value"][1], 6) for i in dots["items"]}
    assert max(bar_bottoms) < min(dot_ys), "the dots lie below the bar, never on it"


def test_the_frame_hues_are_the_checked_qualitative_colours(out):
    assert out["screen"]["colours"]["frames"] == out["qualitative"]["set2"]
    assert out["print"]["colours"]["frames"] == out["qualitative"]["dark2"]


def test_rows_beyond_the_top_n_and_unused_features_are_counted_and_listed(out):
    shown = out["screen"]["importance"]["xgb_importance_momentum"]
    texts = [g["text"] for g in shown["card"]["graphics"]]
    assert shown["unused"] == 46 and any("46 never split on" in t for t in texts)
    many = out["variants"]["importanceMany"]
    assert many["shown"] == 15 and many["hidden"] == 37 and many["unused"] == 0
    assert any("37 more with gain" in g["text"] for g in many["chart"]["graphics"])
    disclosures = " ".join(many["notes"]["sections"]["Disclosures"])
    assert "beyond the first 15" in disclosures and "width_trans" in disclosures


def test_the_drawer_lists_every_feature_with_its_numbers(out):
    """Martin (2026-10-27): the top 15 with gain on the plot; every feature, with its numbers, in the drawer."""
    for name in IMPORTANCE:
        payload = _load(name)
        listed = out["notes"]["importance"][name]["sections"]["Features"]
        assert len(listed) == len(payload["features"]) == payload["n_features"]
        for feature in payload["features"]:
            (line,) = [l for l in listed if l.startswith(f"{feature['rank']}. {feature['name']} [")]
            assert "shipped" in line and "folds" in line and "interval" in line and "gain" in line
        never = [l for l in listed if "never split on, not drawn" in l]
        assert len(never) == out["screen"]["importance"][name]["unused"]
    many = out["variants"]["importanceMany"]["notes"]["sections"]["Features"]
    assert sum("beyond the first 15 with gain" in l for l in many) == 37
    clipped = " ".join(out["notes"]["importance"]["xgb_importance_momentum"]["sections"]["Disclosures"])
    assert "3 fold-mean intervals clipped to [0, 1]" in clipped


def test_a_features_summary_leaves_the_chart_like_every_explanation():
    """E5's row tooltip is six lines of explanation: chart-level placement, never the pointer readout."""
    source = (JS / "panels" / "xgb_importance.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code = "\n".join(line.split("//")[0] for line in code.splitlines())
    assert "readoutPosition" not in code
    assert "wrapTooltip(tooltipOption(opts.tooltipPosition ?? null))" in code


def test_a_clipped_importance_interval_is_disclosed(out):
    variant = out["variants"]["importanceClipped"]
    assert "interval clipped" in variant["notes"]["hazards"]
    tips = [i["tip"] for s in variant["chart"]["series"] for i in s["items"] if i["tip"] and "clipped" in i["tip"]]
    assert tips


# ----------------------------------------------------------------- notes --


def test_every_builder_is_exported_under_its_card(out):
    assert out["notes"]["builders"] == {"xgb-cv": "xgbCvNotes", "xgb-binary": "xgbBinaryNotes",
                                        "xgb-surrogate": "xgbTreeNotes", "xgb-importance": "xgbImportanceNotes"}
    assert out["notes"]["exported"] == ["function"] * 4
    assert out["notes"]["titled"] == "Card title"
    assert out["notes"]["empty"] == [None, None]


def _all_notes(out):
    yield from out["notes"]["cv"].values()
    yield out["notes"]["binary"]
    yield from out["notes"]["tree"].values()
    yield from out["notes"]["importance"].values()


def _split_lines(notes):
    return [line for line in notes["sections"]["Disclosures"]
            if line.startswith(("Split check passed", "Split not reproduced"))]


def test_notes_lead_with_the_four_sections_and_the_run(out):
    section = out["notes"]["section"]
    standard = [section["selection"], section["drawn"], section["disclosures"], section["legend"]]
    for notes in _all_notes(out):
        assert notes["headings"][:4] == standard
        selection = notes["sections"]["Selection"]
        assert selection[0] == "Computed once on the whole experiment, as the notebook does; the selection does not apply."
        joined = " ".join(selection)
        assert "Species electron, seed 1" in joined and "sha256" in joined and "standalone_" in joined
        assert len(_split_lines(notes)) == 1


def test_the_split_line_follows_the_payload_and_names_the_largest_other_seed(out):
    # The recorded momentum model reproduces the split; the recorded angle model,
    # which barely overfits its synthetic labels, honestly does not.
    cv = out["notes"]["cv"]
    passed = _split_lines(cv["xgb_cv_momentum"])[0]
    assert passed.startswith("Split check passed")
    assert "at most 5 at the 99 other seeds (random_state 53)" in passed and "1.05 is required" in passed
    failed = _split_lines(cv["xgb_cv_angle"])
    assert failed[0].startswith("Split not reproduced") and failed[0].count("Split not reproduced") == 1
    assert "split not reproduced" in cv["xgb_cv_angle"]["hazards"]
    assert "split not reproduced" not in cv["xgb_cv_momentum"]["hazards"]
    for notes in _all_notes(out):
        assert all(len(line) < 700 for line in _split_lines(notes))   # never the 99 ratios


def test_the_angle_cv_drawer_names_parity_the_wrapped_phi_and_the_label_order(out):
    notes = out["notes"]["cv"]["xgb_cv_angle"]
    text = " ".join(notes["sections"]["Disclosures"])
    assert "wrapped to (−π, π]" in text and "prepare_data" in text and "unwrapped" in text


def test_binary_and_tree_hazards_and_parity_metrics(out):
    binary = out["notes"]["binary"]
    assert "minority class of 20 rows" in binary["hazards"] and "fallback class rule" in binary["hazards"]
    assert "Notebook parity metrics" in binary["headings"]
    assert any("weighted F1" in line for line in binary["sections"]["Notebook parity metrics"])
    assert "low surrogate fidelity" in out["notes"]["tree"]["xgb_surrogate_momentum:momentum"]["hazards"]
    assert "Nodes" in out["notes"]["tree"]["xgb_surrogate_momentum:momentum"]["headings"]


def test_a_split_that_is_not_reproduced_is_a_hazard_on_every_card(out):
    for notes in out["variants"]["splitBroken"].values():
        assert "split not reproduced" in notes["hazards"]
        assert any(line.startswith("Split not reproduced") for line in notes["sections"]["Disclosures"])


def test_empty_payloads_say_so(out):
    assert all(text for text in out["variants"]["empty"])


# ---------------------------------------------------------------- classes --


def test_panel_classes_delegate_and_record_the_plot_area(out):
    panels = out["panels"]
    assert {k: v["kind"] for k, v in panels.items()} == {
        "XgbCvPanel": "xgb-cv", "XgbBinaryPanel": "xgb-binary", "XgbTreePanel": "xgb-tree", "XgbImportancePanel": "xgb-importance"}
    for name, panel in panels.items():
        assert panel["series"] > 0 and panel["cleared"], name
        assert panel["liveGrid"], name
    assert isinstance(panels["XgbBinaryPanel"]["liveGrid"], list) and len(panels["XgbBinaryPanel"]["liveGrid"]) == 2
    assert {"left", "top", "width", "height"} <= set(panels["XgbTreePanel"]["liveGrid"])
    assert "label" in panels["XgbTreePanel"]["lastOpts"]
    for name, metrics in out["exportMetrics"].items():
        assert metrics["width"] == 321 and metrics["height"] > 150, name
