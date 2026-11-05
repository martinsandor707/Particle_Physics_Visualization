"""The three Distillations cards of the benchmark catalogue, run under Node (brief section 6, P1).

`panels/pysr_matrix.js` (a DOM card), `panels/distill_triangle.js` and `panels/distill_curves.js` (ECharts
cards), their notes (`catalog_notes_distill.js`) and `css/catalog.css`. The script builds every card from
`catalog/select.js` `catalogPayload` for every species and Compare all and every task, in the dark and the
light screen theme and under the print tokens, renders every custom series' `renderItem` with a linear
coordinate map, calls every tooltip formatter and hands back what was drawn. The tests hold the cards to
CLAUDE.md section 2 and Martin's recorded exception of 2026-11-05:

* zero baselines: R² on a fixed 0–1 axis, MAE and p̂ and E_sum from zero; no dual axes;
* an R² below zero (or reported only as "< 0") is clamped at 0 with a visible "R² < 0" mark, and the
  exact or qualified value is in the tooltip and the drawer;
* angle MAEs in mrad (F4), segmentation MAEs labelled voxel-sample (F5);
* the tier as text and border style; leak badges; the leakage-signal wording of brief section 11;
* every tooltip names "N not reported" (or the accuracy table's N) and "point estimate as reported; no
  interval"; every drawer carries the hazard "no interval reported";
* U+2212 in every rendered string; ink at 3:1 and text at 4.5:1 on both screen cards and on paper;
* no colour literal and no innerHTML in the new modules; the DOM card builds MathML with createElementNS;
* the curves' sliders repaint with no request and the export draws the sliders' values;
* catalog.css implements every class of brief section 6 with tokens only and nothing animated.
"""

from __future__ import annotations

import json
import re

import pytest

from test_js_physics_shell import _FAKE_DOM, JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

CSS = JS.parent / "css" / "catalog.css"
MODULES = {
    "pysr": JS / "panels" / "pysr_matrix.js",
    "triangle": JS / "panels" / "distill_triangle.js",
    "curves": JS / "panels" / "distill_curves.js",
    "notes": JS / "catalog_notes_distill.js",
}
SPECIES = ["proton", "muon", "electron", "pion", "all"]
TASKS = ["segmentation", "angle", "energy"]

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w.])-(?=[\d.∞])")
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")

_SCRIPT = _FAKE_DOM + r"""
const [jsRoot] = JSON.parse(process.argv[1]);
// No canvas under Node: textfit.js falls back to its estimate, as in the other builder tests.
FakeElement.prototype.getContext = () => null;
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { THEME } = scale;
const { PRINT_TOKENS } = await imp('export/tokens.js');
const palette = await imp('palette.js');
const cp = await imp('panels/chart_panel.js');
const sel = await imp('catalog/select.js');
const tri = await imp('panels/distill_triangle.js');
const cur = await imp('panels/distill_curves.js');
const pys = await imp('panels/pysr_matrix.js');
const notes = await imp('catalog_notes_distill.js');

const SPECIES = ['proton', 'muon', 'electron', 'pion', 'all'];
const TASKS = ['segmentation', 'angle', 'energy'];
const api = { coord: (p) => [Number(p[0]) * 100, Number(p[1]) * 30] };

function flatten(el, out = []) {
  if (!el) return out;
  if (el.type === 'group') { for (const c of el.children ?? []) flatten(c, out); return out; }
  out.push(el);
  return out;
}

const rgb = (c) => cp.rgbOf(c);
function inkContrast(colour, opacity = 1) {
  const c = rgb(colour);
  if (!c) return null;
  return palette.contrast(cp.blendOver(colour, opacity ?? 1), rgb(THEME.card));
}

function walk(option) {
  const strings = [];
  const inks = [];      // [contrast, what] of every drawn stroke/fill a reader must see
  const texts = [];     // [contrast, text] of every drawn text
  const axes = { x: [].concat(option.xAxis ?? []), y: [].concat(option.yAxis ?? []) };
  for (const a of [...axes.x, ...axes.y]) {
    if (a.name) strings.push(a.name);
    const f = a.axisLabel?.formatter;
    if (typeof f === 'function' && a.type === 'value') for (const v of [-1, -0.5, 0, 0.5, 1, 12.5]) strings.push(String(f(v)));
    if (typeof f === 'function' && a.type === 'category') for (const d of a.data ?? []) strings.push(String(f(d)));
  }
  for (const g of option.graphic ?? []) {
    for (const leaf of flatten(g)) {
      if (leaf.style?.text) {
        strings.push(leaf.style.text);
        texts.push([inkContrast(leaf.style.fill, leaf.style.opacity ?? 1), leaf.style.text]);
      }
    }
  }
  for (const l of [].concat(option.legend ?? [])) for (const d of l.data ?? []) strings.push(String(d?.name ?? d));
  const series = [];
  for (const s of option.series ?? []) {
    const items = [];
    for (let i = 0; i < (s.data ?? []).length; i += 1) {
      const el = typeof s.renderItem === 'function' ? s.renderItem({ dataIndex: i, coordSys: { x: 0, y: 0, width: 100, height: 100 } }, api) : null;
      const leaves = flatten(el);
      for (const leaf of leaves) {
        const st = leaf.style ?? {};
        if (st.text) {
          strings.push(st.text);
          texts.push([inkContrast(st.fill, st.opacity ?? 1), st.text]);
          continue;
        }
        const op = st.opacity ?? 1;
        // A stroke in the card's own colour is a casing that separates a mark from its neighbours; the
        // mark is its fill.
        if (st.stroke && st.stroke !== 'none' && st.stroke !== THEME.card) inks.push([inkContrast(st.stroke, st.strokeOpacity ?? op), `${s.name} stroke`, st.lineDash ?? null]);
        else if (st.fill && st.fill !== 'none' && st.fill !== THEME.card) inks.push([inkContrast(st.fill, st.fillOpacity ?? op), `${s.name} fill`, null]);
      }
      const tip = typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter({ dataIndex: i }) : null;
      if (tip) strings.push(tip);
      items.push({ leaves: leaves.map((l) => ({ type: l.type, text: l.style?.text ?? null, dash: l.style?.lineDash ?? null,
        opacity: l.style?.opacity ?? null, stroke: l.style?.stroke ?? null, fill: typeof l.style?.fill === 'string' ? l.style.fill : null,
        shape: l.type === 'rect' || l.type === 'line' || l.type === 'circle' ? l.shape : null })), tip, datum: s.data[i] });
    }
    series.push({ name: s.name, type: s.type, xAxisIndex: s.xAxisIndex ?? 0, yAxisIndex: s.yAxisIndex ?? 0, items });
  }
  return {
    strings, inks, texts, series,
    xAxis: axes.x.map((a) => ({ type: a.type, name: a.name ?? '', min: a.min ?? null, max: a.max ?? null, gridIndex: a.gridIndex ?? 0, inverse: Boolean(a.inverse) })),
    yAxis: axes.y.map((a) => ({ type: a.type, name: a.name ?? '', min: a.min ?? null, max: a.max ?? null, gridIndex: a.gridIndex ?? 0, inverse: Boolean(a.inverse), data: a.data ?? null })),
    grids: [].concat(option.grid ?? []).length,
    tooltip: { appendTo: option.tooltip?.appendTo ?? null, confine: option.tooltip?.confine ?? null },
  };
}

const pack = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
  sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);

function build(theme) {
  const out = { triangle: {}, curves: {}, pysr: {}, notes: {}, theme: {} };
  out.theme = { card: THEME.card, text: inkContrast(THEME.text), muted: inkContrast(THEME.muted), warn: inkContrast(THEME.warn),
    frames: Object.fromEntries(Object.entries(tri.frameColours()).map(([k, c]) => [k, inkContrast(c)])) };
  for (const species of SPECIES) {
    for (const task of TASKS) {
      const key = `${species}:${task}`;
      const tp = sel.catalogPayload('distill-triangle', { species, task });
      const tm = tri.triangleModel(tp, { task });
      out.triangle[key] = {
        wide: walk(tri.distillTriangleOption(tp, { species, task }, { width: 1100, height: 400 }).option),
        narrow: walk(tri.distillTriangleOption(tp, { species, task }, { width: 321, height: 700 }).option),
        height: { wide: tri.plotHeight(tp, {}, 1100), narrow: tri.plotHeight(tp, {}, 321) },
        layout: { wide: tri.triangleLayout(tm, 1100).stacked, narrow: tri.triangleLayout(tm, 321).stacked },
        model: { unit: tm.unit, rows: tm.rows.map((r) => ({ key: r.key, label: r.label, badges: r.badges, leaks: r.leaks, leakSignal: r.leakSignal,
          leakSignalText: r.leakSignalText, mae: r.mae, clamped: Object.fromEntries(Object.entries(r.r2).map(([k, m]) => [k, m ? { drawn: m.drawn, clamped: m.clamped, text: m.text, exact: m.exact } : null])) })) },
      };
      out.notes[`triangle:${key}`] = pack(notes.triangleNotes({ payload: tp, task, species }));
      const pp = sel.catalogPayload('distill-pysr', { species, task });
      out.notes[`pysr:${key}`] = pack(notes.pysrNotes({ payload: pp, task, species, panelState: { highlight: 'centroid_theta' } }));
    }
    const cpay = sel.catalogPayload('distill-curves', { species });
    const variants = { defaults: null, extreme: { centroid_r: 5000, max_hit_frac: 1, centroid_theta: 1, rms_r: 300 }, low: { centroid_r: 0, max_hit_frac: 0, centroid_theta: 0, rms_r: 0 } };
    out.curves[species] = {};
    for (const [name, values] of Object.entries(variants)) {
      const m = cur.curvesModel(cpay, { values });
      out.curves[species][name] = {
        wide: walk(cur.distillCurvesOption(cpay, { species, values }, { width: 1100, height: 400 }).option),
        narrow: walk(cur.distillCurvesOption(cpay, { species, values }, { width: 321, height: 900 }).option),
        model: { xTop: m.xTop, yTop: m.yTop, values: m.values, clipped: m.clipped.map((c) => c.key), carets: m.carets,
          curves: m.curves.map((c) => ({ key: c.key, tier: c.tier, dash: c.stroke.dash, width: c.stroke.width, opacity: c.opacity,
            colour: c.colour, segments: c.segments.map((s) => s.map((p) => p)), runs: c.runs })) },
        height: { wide: cur.plotHeight(cpay, { values }, 1100), narrow: cur.plotHeight(cpay, { values }, 321) },
        notes: pack(notes.curvesNotes({ payload: cpay, panelState: { values } })),
      };
    }
    const pp = sel.catalogPayload('distill-pysr', { species });
    const pm = pys.pysrModel(pp, { highlight: 'centroid_theta' });
    out.pysr[species] = { entries: pm.entries.map((e) => ({ id: e.id, tier: e.tier, tierLabel: e.tierLabel, badges: e.badges.map((b) => b.kind),
      absent: e.absent, r2Text: e.r2Text, netR2Text: e.netR2Text, features: e.features, extra: e.extraVariables, inferred: e.featureMapInferred })),
      matches: pm.matches, highlight: pm.highlight, status: pys.highlightStatus(pm), counts: pm.counts };
  }
  return out;
}

const result = {};
for (const theme of ['dark', 'light']) {
  scale.setScreenTheme(theme);
  result[theme] = build(theme);
}
scale.setScreenTheme('dark');
const saved = { ...THEME };
Object.assign(THEME, PRINT_TOKENS);
result.print = build('print');
scale.restoreScreenTheme();
Object.assign(THEME, saved);

/* ---- the DOM card on the fake DOM ------------------------------------------ */
{
  const made = [];
  document.createElementNS = (ns, tag) => { made.push([ns, tag]); return new FakeElement(tag); };
  Object.defineProperty(FakeElement.prototype, 'innerHTML', { set() { throw new Error('innerHTML written'); }, get() { return ''; } });
  const events = [];
  FakeElement.prototype.dispatchEvent = function (e) { events.push({ type: e.type, detail: e.detail, bubbles: e.bubbles }); return true; };
  const host = document.createElement('div');
  host.className = 'card-table';
  const panel = new pys.PysrMatrixPanel(host, { card: 'distill-pysr' });
  const payload = sel.catalogPayload('distill-pysr', { species: 'all' });
  panel.render(payload, { species: 'all' });
  const entries = host.findAll((el) => el.className === 'pysr-entry');
  const chips = host.findAll((el) => el.className.split(' ').includes('feature-chip'));
  const maths = host.findAll((el) => el.tagName === 'MATH');
  const codes = host.findAll((el) => el.tagName === 'CODE');
  const copies = host.findAll((el) => el.className.includes('pysr-copy'));
  const absent = host.findAll((el) => el.className === 'pysr-absent').map((el) => el.textContent);
  const tierChips = host.findAll((el) => el.className === 'tier-chip').map((el) => ({ tier: el.dataset.tier, text: el.textContent }));
  const badges = host.findAll((el) => el.className === 'badge-chip').map((el) => ({ kind: el.dataset.kind, text: el.textContent, title: el.title }));
  const r2Titles = [...new Set(host.findAll((el) => el.className === 'pysr-r2').map((el) => el.title))];
  const r2Lines = Object.fromEntries(entries.map((e) => [e.dataset.entry, e.find((el) => el.className === 'pysr-r2')?.textContent ?? null]));
  const fits = Object.fromEntries(entries.map((e) => [e.dataset.entry, e.find((el) => el.className === 'pysr-formula')?.dataset.fit ?? null]));
  const hintsShown = host.findAll((el) => el.className === 'pysr-scroll-hint' && !el.hidden).length;
  const hints = host.findAll((el) => el.className === 'pysr-scroll-hint').length;
  // The chips of an entry whose formula names were mapped by inference say so in their titles.
  const inferredTitles = entries.filter((e) => e.find((el) => el.className === 'badge-chip' && el.dataset.kind === 'inferred'))
    .flatMap((e) => e.findAll((el) => el.className.includes('feature-chip')).map((el) => el.title));
  const plainTitles = entries.filter((e) => !e.find((el) => el.className === 'badge-chip' && el.dataset.kind === 'inferred'))
    .flatMap((e) => e.findAll((el) => el.className.includes('feature-chip')).map((el) => el.title));
  // A click on a chip highlights every use of its feature; a second click clears it.
  const theta = chips.find((c) => c.dataset.feature === 'centroid_theta');
  theta.click();
  const after = {
    highlight: panel.highlight,
    state: panel.notesState(),
    pressed: chips.filter((c) => c.attrs['aria-pressed'] === 'true').map((c) => c.dataset.feature),
    highlighted: chips.filter((c) => c.className.includes('is-highlighted')).length,
    matched: entries.filter((e) => e.className.includes('is-match')).map((e) => e.dataset.entry),
    status: host.find((el) => el.className === 'pysr-status').textContent,
    events: events.slice(),
  };
  // A repaint keeps the highlight while the feature is still drawn.
  panel.render(sel.catalogPayload('distill-pysr', { species: 'electron' }), {});
  const repaint = { highlight: panel.highlight, matched: host.findAll((el) => el.className.includes('is-match')).length };
  panel.render(payload, {});
  host.findAll((el) => el.className.includes('feature-chip')).find((c) => c.dataset.feature === 'centroid_theta').click();
  const cleared = { highlight: panel.highlight, matched: host.findAll((el) => el.className.includes('is-match')).length, events: events.length };
  // Copy: success and failure, said in the button's title.
  let copied = null;
  // Node defines navigator as a getter: redefine it for the test.
  const setNavigator = (value) => Object.defineProperty(globalThis, 'navigator', { value, configurable: true, writable: true });
  setNavigator({ clipboard: { writeText: (t) => { copied = t; return Promise.resolve(); } } });
  const firstCopy = host.findAll((el) => el.className.includes('pysr-copy'))[0];
  firstCopy.click();
  await settle();
  const copyOk = { copied, title: firstCopy.title, state: firstCopy.dataset.state, text: firstCopy.textContent };
  setNavigator({ clipboard: { writeText: () => Promise.reject(new Error('denied by the browser')) } });
  const second = host.findAll((el) => el.className.includes('pysr-copy'))[1];
  second.click();
  await settle();
  const copyFail = { title: second.title, state: second.dataset.state };
  setNavigator({});
  const third = host.findAll((el) => el.className.includes('pysr-copy'))[2];
  third.click();
  const copyNone = { title: third.title, state: third.dataset.state };
  // The LaTeX source sits behind its toggle, hidden until asked for (the Methodology's convention).
  const texToggles = host.findAll((el) => el.className.split(' ').includes('pysr-tex-toggle'));
  const texPanels = host.findAll((el) => el.className === 'pysr-tex-panel');
  const texToggle = {
    toggles: texToggles.length, panels: texPanels.length,
    codesInPanels: texPanels.filter((p) => p.find((el) => el.tagName === 'CODE')).length,
    copiesInPanels: texPanels.filter((p) => p.find((el) => el.className.includes('pysr-copy'))).length,
    hidden: texPanels.every((p) => p.hidden), collapsed: texToggles.every((t) => t.attrs['aria-expanded'] === 'false'),
    uniqueIds: new Set(texPanels.map((p) => p.id)).size,
    idsPlain: texPanels.every((p) => /^pysr-tex-[A-Za-z0-9_-]+$/.test(p.id)),
    controls: texToggles.every((t, i) => t.attrs['aria-controls'] === texPanels[i].id),
  };
  texToggles[0].click();
  texToggle.open = { hidden: texPanels[0].hidden, expanded: texToggles[0].attrs['aria-expanded'], title: texToggles[0].title };
  texToggles[0].click();
  texToggle.closed = { hidden: texPanels[0].hidden, expanded: texToggles[0].attrs['aria-expanded'], title: texToggles[0].title };
  // A TeX the compiler refuses falls back to the explicit text.
  const broken = JSON.parse(JSON.stringify(payload));
  broken.cells[6].entries[0].formula.tex = '\\notacommand{x}';
  const host2 = document.createElement('div');
  const p2 = new pys.PysrMatrixPanel(host2, { card: 'distill-pysr' });
  p2.render(broken, {});
  const fallback = host2.findAll((el) => el.className === 'pysr-fallback').map((el) => ({ text: el.textContent, title: el.parent.title, mode: el.parent.dataset.fallback }));
  p2.clear();
  // A formula wider than its box at the floor: the relayout measures it, marks the box, shows its hint and
  // tells the drawer (notesState().scrolling) with one models:panelstate.
  const before = events.length;
  const boxOf = (id) => host.findAll((el) => el.className === 'pysr-entry' && el.dataset.entry === id)[0].find((el) => el.className === 'pysr-formula');
  const wide = boxOf('muon:segmentation:absolute');
  const size = (el, sw, cw) => {
    Object.defineProperty(el, 'scrollWidth', { value: sw, configurable: true });
    Object.defineProperty(el, 'clientWidth', { value: cw, configurable: true });
  };
  size(wide, 900, 300);
  const narrow = boxOf('electron:segmentation:absolute');
  size(narrow, 200, 300);
  panel.relayout();
  const entryOf = (id) => host.findAll((el) => el.className === 'pysr-entry' && el.dataset.entry === id)[0];
  const scroll = {
    state: panel.notesState(),
    marked: wide.dataset.scrolls, unmarked: narrow.dataset.scrolls,
    hintShown: !entryOf('muon:segmentation:absolute').find((el) => el.className === 'pysr-scroll-hint').hidden,
    otherHintShown: !entryOf('electron:segmentation:absolute').find((el) => el.className === 'pysr-scroll-hint').hidden,
    events: events.length - before,
  };
  panel.relayout();
  scroll.eventsAgain = events.length - before;
  const scrollNotes = pack(notes.pysrNotes({ payload, panelState: panel.notesState() }));
  result.dom = {
    r2Lines, fits, hints, hintsShown, scroll, scrollNotes,
    entries: entries.length, tiers: entries.map((e) => e.dataset.tier), chips: chips.length, maths: maths.length,
    codes: codes.length, copies: copies.length, absent, tierChips, badges, r2Titles, inferredTitles, plainTitles,
    madeNs: [...new Set(made.map((m) => m[0]))], madeTags: [...new Set(made.map((m) => m[1]))],
    after, repaint, cleared, copyOk, copyFail, copyNone, texToggle, fallback, clearedChildren: host2.childNodes.length,
    kind: panel.kind, hasRelayout: typeof panel.relayout === 'function', hasBusy: typeof panel.setBusy === 'function',
  };
}

/* ---- the chart cards' classes, with a fake ECharts -------------------------- */
{
  FakeElement.prototype.after = function (node) {
    const parent = this.parent;
    node.parent = parent;
    const i = parent.childNodes.indexOf(this);
    parent.childNodes.splice(i + 1, 0, node);
  };
  FakeElement.prototype.remove = function () {
    if (this.parent) this.parent.childNodes = this.parent.childNodes.filter((c) => c !== this);
    this.parent = null;
  };
  let fetches = 0;
  globalThis.fetch = () => { fetches += 1; return Promise.reject(new Error('no request expected')); };
  const options = [];
  const mkChart = (element) => ({ getWidth: () => 1100, getHeight: () => 330, setOption: (o) => options.push(o), resize: () => {},
    clear: () => {}, getDom: () => element, dispatchAction: () => {}, on: () => {}, getZr: () => ({ on: () => {} }) });
  globalThis.echarts = { init: (el) => mkChart(el) };
  globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
  const mount = () => {
    const card = document.createElement('div'); card.className = 'card';
    const frame = document.createElement('div'); frame.className = 'plot-frame';
    const plot = document.createElement('div'); plot.className = 'plot';
    Object.defineProperty(plot, 'clientWidth', { get: () => 1100 });
    frame.append(plot); card.append(frame);
    return { card, frame, plot };
  };
  // Curves.
  const { card, frame, plot } = mount();
  const events = [];
  plot.dispatchEvent = (e) => { events.push(e.detail); return true; };
  const panel = new cur.DistillCurvesPanel(plot, { card: 'distill-curves' });
  panel.render(sel.catalogPayload('distill-curves', { species: 'all' }), { species: 'all', task: 'energy', palette: 'viridis' });
  const first = options.length;
  const controls = card.children[1];
  const inputs = controls.findAll((el) => el.tagName === 'INPUT');
  const rms = inputs.find((i) => i.attrs['aria-label']?.startsWith('rms_r'));
  rms.value = '300';
  rms.dispatch('input');
  const afterSlide = options.length;
  const valuesAfterSlide = panel.notesState();
  const lastOption = options[options.length - 1];
  const exported = panel.buildOption({ payload: panel.lastPayload, opts: panel.lastOpts, metrics: { width: 321, height: 900 } }).option;
  const exportedFromScreenOpts = panel.buildOption({ payload: panel.lastPayload, opts: { species: 'all' }, metrics: { width: 661, height: 500 } }).option;
  const keyText = (o) => (o.graphic ?? []).map((g) => g.style?.text).filter(Boolean).join(' | ');
  // A repaint (theme, palette) keeps the values.
  panel.render(sel.catalogPayload('distill-curves', { species: 'muon' }), { species: 'muon' });
  const keptAfterRepaint = { ...panel.values };
  const valuesText = controls.find((el) => el.className === 'curve-values')?.textContent ?? null;
  const reset = card.children[1].find((el) => el.className.includes('curve-reset'));
  reset.click();
  const afterReset = { ...panel.values };
  const metrics = panel.exportMetrics(321);
  const height = plot.style.height;
  const frameNext = frame.parent.children[1]?.className ?? null;
  panel.clear();
  result.curvesPanel = {
    first, afterSlide, fetches, events, frameNext,
    inputs: inputs.map((i) => ({ label: i.attrs['aria-label'], min: i.min, max: i.max, step: i.step, value: i.value })),
    valuesAfterSlide, keptAfterRepaint, afterReset, valuesText,
    liveKey: keyText(lastOption), exportKey: keyText(exported), exportKeyScreenOpts: keyText(exportedFromScreenOpts),
    metrics, height, controlsAfterClear: card.children.length,
  };
  // Triangle.
  const t = mount();
  const tp = new tri.DistillTrianglePanel(t.plot, { card: 'distill-triangle' });
  tp.render(sel.catalogPayload('distill-triangle', { species: 'all', task: 'angle' }), { species: 'all', task: 'angle' });
  const all = t.plot.style.height;
  tp.render(sel.catalogPayload('distill-triangle', { species: 'muon', task: 'angle' }), { species: 'muon', task: 'angle' });
  const one = t.plot.style.height;
  result.trianglePanel = { all, one, export: tp.exportMetrics(321), liveGrid: Array.isArray(tp.liveGrid) ? tp.liveGrid.length : null, fetches };
}
process.stdout.write(JSON.stringify(result));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    return _run(_SCRIPT, [JS.as_uri()])


def _all_strings(card: dict):
    yield from card["strings"]


def _tips(card: dict):
    for s in card["series"]:
        for item in s["items"]:
            if item["tip"]:
                yield s["name"], item["tip"]


# -------------------------------------------------------------- triangle --


def test_the_triangle_axes_start_at_zero_and_r2_is_fixed_to_0_1(out):
    for theme in ("dark", "light", "print"):
        for key, card in out[theme]["triangle"].items():
            for layout in ("wide", "narrow"):
                x = card[layout]["xAxis"]
                assert len(x) == 2, key
                assert (x[0]["min"], x[0]["max"]) == (0, 1), (theme, key)
                assert x[1]["min"] == 0 and x[1]["max"] > 0, (theme, key)
                assert all(a["type"] == "category" for a in card[layout]["yAxis"]), key
                assert card[layout]["grids"] == 2


def test_no_mark_is_drawn_left_of_zero(out):
    for key, card in out["dark"]["triangle"].items():
        for s in card["wide"]["series"]:
            for item in s["items"]:
                for leaf in item["leaves"]:
                    if leaf["type"] == "rect" and leaf["shape"]:
                        assert leaf["shape"]["x"] >= 0 and leaf["shape"]["width"] >= 0, (key, s["name"])


def test_a_negative_r2_is_clamped_at_zero_with_a_visible_mark_and_its_value_in_tip_and_drawer(out):
    card = out["dark"]["triangle"]["all:angle"]
    rows = {r["key"]: r for r in card["model"]["rows"]}
    pion = rows["pion:local"]["clamped"]["pysrNet"]
    assert pion["clamped"] and pion["drawn"] == 0
    assert pion["text"] == "−0.024"
    assert "R² < 0" in card["wide"]["strings"]
    tips = [t for name, t in _tips(card["wide"]) if name.startswith("PySR") and "Pion · Local" in t]
    assert tips and "−0.024" in tips[0] and "drawn at 0" in tips[0]
    drawer = out["dark"]["notes"]["triangle:all:angle"]["sections"]["Disclosures"]
    assert any("Pion · Local" in line and "−0.024" in line and "R² < 0" in line for line in drawer)
    # Reported only as "< 0": no number is invented.
    seg = out["dark"]["triangle"]["proton:segmentation"]
    trans = {r["key"]: r for r in seg["model"]["rows"]}["proton:trans"]["clamped"]["pysrNet"]
    assert trans["clamped"] and trans["exact"] == "reported only as < 0, with no number"
    assert any(t.startswith("R² < 0") for t in seg["wide"]["strings"])
    lines = out["dark"]["notes"]["triangle:proton:segmentation"]["sections"]["Disclosures"]
    assert any("reported only as < 0" in line for line in lines)
    # "≈ 0" keeps its qualifier.
    assert "≈ 0" in seg["wide"]["strings"]


def test_angle_maes_are_in_mrad_and_segmentation_maes_are_voxel_sample(out):
    angle = out["dark"]["triangle"]["muon:angle"]
    assert angle["model"]["unit"] == "mrad"
    assert "mrad" in angle["wide"]["xAxis"][1]["name"]
    rows = {r["key"]: r["mae"] for r in angle["model"]["rows"]}
    assert rows["muon:absolute"]["netTruth"] == 0.46          # 0.00046 rad (F4)
    assert rows["muon:absolute"]["formula"] == 0.87
    seg = out["dark"]["triangle"]["muon:segmentation"]
    assert seg["wide"]["xAxis"][1]["name"].startswith("Voxel-sample MAE")
    for _, tip in _tips(seg["wide"]):
        if "MAE" in tip.split("</b>")[0]:
            assert "voxel-sample" in tip, tip
    drawer = out["dark"]["notes"]["triangle:muon:segmentation"]["sections"]["What is drawn"]
    assert any("voxel-sample" in line and "E-MAE" in line for line in drawer)
    assert any("× 1000" in line or "multiplied by 1000" in line for line in out["dark"]["notes"]["triangle:muon:angle"]["sections"]["What is drawn"])


def test_every_triangle_tooltip_names_its_n_and_the_absent_interval(out):
    for key, card in out["dark"]["triangle"].items():
        tips = list(_tips(card["wide"]))
        assert tips, key
        for name, tip in tips:
            assert "point estimate as reported; no interval" in tip, (key, name)
            assert "N not reported" in tip or "N = 4,065 validation events" in tip, (key, name)


def test_the_proton_network_mae_carries_the_accuracy_tables_n(out):
    card = out["dark"]["triangle"]["proton:energy"]
    tips = [t for name, t in _tips(card["wide"]) if name == "Network → Truth MAE"]
    assert tips and all("N = 4,065 validation events (8,130 particles)" in t for t in tips)
    assert "tree MAEs not reported" in card["wide"]["strings"]
    seg = out["dark"]["triangle"]["proton:segmentation"]
    assert "no voxel-sample MAE in the report" in seg["wide"]["strings"]


def test_leak_badges_and_the_leakage_signal_wording(out):
    card = out["dark"]["triangle"]["all:segmentation"]
    rows = {r["key"]: r for r in card["model"]["rows"]}
    assert rows["muon:trans"]["badges"] == ["leak", "signal"]
    assert rows["muon:absolute"]["badges"] == ["signal"]
    assert rows["proton:absolute"]["badges"] == []
    assert "matches the report's own leakage caveat" in rows["electron:trans"]["leakSignalText"]
    assert "warning, not a finding" in rows["electron:absolute"]["leakSignalText"]
    assert "⚑ label leakage · leakage signal" in card["wide"]["strings"]
    assert any(s.startswith("⚑ leak") for s in card["narrow"]["strings"])
    every = json.dumps(out["dark"]["notes"], ensure_ascii=False)
    assert "better model" not in every.replace("Never read it as a better model", "")
    angle = {r["key"]: r for r in out["dark"]["triangle"]["all:angle"]["model"]["rows"]}
    assert angle["muon:local"]["leaks"] == ["local-true-angle"] and "leak" in angle["muon:local"]["badges"]


def test_compare_all_needs_more_height_and_a_narrow_card_stacks(out):
    for task in TASKS:
        card = out["dark"]["triangle"][f"all:{task}"]
        single = out["dark"]["triangle"][f"muon:{task}"]
        assert card["height"]["wide"] > single["height"]["wide"]
        assert card["layout"] == {"wide": False, "narrow": True}
        assert card["height"]["narrow"] > card["height"]["wide"]
    assert int(out["trianglePanel"]["all"].rstrip("px")) > int(out["trianglePanel"]["one"].rstrip("px"))
    assert out["trianglePanel"]["export"]["height"] > 0 and out["trianglePanel"]["liveGrid"] == 2
    assert out["trianglePanel"]["fetches"] == 0


def test_species_are_rows_never_a_second_hue(out):
    card = out["dark"]["triangle"]["all:energy"]
    frames = out["dark"]["theme"]
    labels = [r["label"] for r in card["model"]["rows"]]
    assert labels[0] == "Proton · Absolute" and labels[4] == "Muon · Per-shower translated"
    assert not any(label.endswith(" Translated") or label == "Translated" for label in labels)
    assert set(frames["frames"]) == {"absolute", "trans", "local"}


# ----------------------------------------------------------------- curves --


def test_the_curve_axes_start_at_zero_and_y_is_the_20_gev_ceiling(out):
    for theme in ("dark", "light", "print"):
        for species, variants in out[theme]["curves"].items():
            for name, v in variants.items():
                for layout in ("wide", "narrow"):
                    for a in v[layout]["xAxis"]:
                        assert a["min"] == 0 and a["max"] == pytest.approx(v["model"]["xTop"]), (species, name)
                    for a in v[layout]["yAxis"]:
                        assert (a["min"], a["max"]) == (0, 20), (species, name)
                assert len(v["wide"]["xAxis"]) == 3


def test_every_drawn_point_is_inside_the_axes(out):
    for species, variants in out["dark"]["curves"].items():
        for name, v in variants.items():
            m = v["model"]
            for c in m["curves"]:
                for seg in c["segments"]:
                    for x, y in seg:
                        assert -1e-9 <= x <= m["xTop"] + 1e-9, (species, name, c["key"])
                        assert -1e-9 <= y <= 20 + 1e-9, (species, name, c["key"])


def test_the_absolute_formula_that_sets_x_ends_in_the_corner(out):
    m = out["dark"]["curves"]["pion"]["defaults"]["model"]
    pion = next(c for c in m["curves"] if c["key"] == "pion:absolute")
    assert pion["runs"] == []
    end = pion["segments"][-1][-1]
    assert end[0] == pytest.approx(m["xTop"]) and end[1] == pytest.approx(20, abs=1e-6)
    assert m["xTop"] == pytest.approx(0.5498958, abs=1e-6)


def test_clipped_curves_get_carets_and_a_count(out):
    v = out["dark"]["curves"]["all"]["defaults"]
    assert v["model"]["clipped"] and v["model"]["carets"] >= len(v["model"]["clipped"])
    carets = [s for s in v["wide"]["series"] if s["name"].endswith("(clipped)")]
    assert sum(len(s["items"]) for s in carets) == v["model"]["carets"]
    for s in carets:
        for item in s["items"]:
            assert "Clipped at the axis" in item["tip"] and "point estimate as reported; no interval" in item["tip"]
    # Muon Local runs below zero at the defaults: a downward caret, its true minimum in the tip.
    muon = next(c for c in v["model"]["curves"] if c["key"] == "muon:local")
    assert muon["runs"][0]["dir"] == "below" and muon["runs"][0]["extreme"] < 0
    lines = v["notes"]["sections"]["Disclosures"]
    assert any(f"{len(v['model']['clipped'])} of 12 curves leave" in line for line in lines)
    assert any("−12.01" in line for line in lines)


def test_below_law_curves_are_dashed_and_faded_at_three_to_one(out):
    for theme in ("dark", "light", "print"):
        m = out[theme]["curves"]["all"]["defaults"]["model"]
        for c in m["curves"]:
            if c["tier"] == "law":
                assert c["dash"] is None and c["width"] == 2
            else:
                assert c["dash"], c["key"]
                assert c["opacity"] < 1, c["key"]
        inks = out[theme]["curves"]["all"]["defaults"]["wide"]["inks"]
        assert inks and min(i[0] for i in inks) >= 3 - 1e-9, (theme, min(inks))
    labels = out["dark"]["curves"]["all"]["defaults"]["wide"]["strings"]
    assert "Muon (not a law)" in labels and "Pion (partial)" in labels and "Proton" in labels


def test_the_muon_curves_say_they_describe_the_network(out):
    v = out["dark"]["curves"]["muon"]["defaults"]
    tips = [t for name, t in _tips(v["wide"]) if name.startswith("Muon ·") and not name.endswith("(clipped)")]
    assert tips and all("describe the network: its R² to truth is 0.0176–0.3390" in t for t in tips)
    assert any("describe the network" in line for line in v["notes"]["sections"]["Disclosures"])
    for t in tips:
        assert "conditional at these values, not a marginal prediction" in t or "Depends on E_sum alone" in t
        assert "N not reported · point estimate as reported; no interval" in t


def test_the_values_in_force_are_on_the_canvas_and_in_the_drawer(out):
    v = out["dark"]["curves"]["all"]["extreme"]
    assert any("centroid_r = 5,000 mm" in s and "rms_r = 300 mm" in s for s in v["wide"]["strings"])
    values = v["notes"]["sections"]["Values in force"]
    assert any(line.startswith("rms_r = 300 mm") for line in values)
    assert v["model"]["values"] == {"centroid_r": 5000, "max_hit_frac": 1, "centroid_theta": 1, "rms_r": 300}


def test_the_sliders_repaint_with_no_request_and_the_export_draws_their_values(out):
    p = out["curvesPanel"]
    assert p["frameNext"] == "curve-controls"
    assert p["afterSlide"] == p["first"] + 1, "a slider repaints once"
    assert p["fetches"] == 0
    assert p["events"] and p["events"][0] == {"card": "distill-curves"}
    assert p["valuesAfterSlide"]["values"]["rms_r"] == 300
    assert "rms_r = 300 mm" in p["liveKey"]
    assert "rms_r = 300 mm" in p["exportKey"]
    assert "rms_r = 300 mm" in p["exportKeyScreenOpts"], "an export without values in opts takes the instance's"
    assert p["keptAfterRepaint"]["rms_r"] == 300
    assert p["afterReset"]["rms_r"] == 150
    assert p["valuesText"].startswith("Values in force: ")
    assert "not a marginal prediction" in p["valuesText"]
    assert {i["label"].split(" ")[0] for i in p["inputs"]} == {"centroid_r", "max_hit_frac", "centroid_theta", "rms_r"}
    rms = next(i for i in p["inputs"] if i["label"].startswith("rms_r"))
    assert (rms["min"], rms["max"]) == ("0", "300")
    assert p["metrics"]["width"] == 321 and p["metrics"]["height"] > 0
    assert p["height"].endswith("px")
    assert p["controlsAfterClear"] == 1, "clear() removes the slider row"


# ------------------------------------------------------------------ PySR --


def test_the_pysr_matrix_tiers_are_the_gating_tiers(out):
    entries = {e["id"]: e for e in out["dark"]["pysr"]["all"]["entries"]}
    assert len(entries) == 36
    assert entries["proton:angle:absolute"]["tier"] == "unverified"
    assert entries["muon:energy:absolute"]["tier"] == "not-law"
    assert entries["electron:energy:absolute"]["tier"] == "law"
    assert entries["pion:energy:trans"]["tier"] == "partial"
    assert entries["proton:segmentation:trans"]["absent"] and entries["proton:segmentation:trans"]["r2Text"] == "< 0"
    assert "inferred" in entries["proton:energy:absolute"]["badges"]
    assert "standardised" in entries["muon:segmentation:absolute"]["badges"]
    assert "leak" in entries["muon:angle:local"]["badges"]
    assert "negative" in entries["pion:angle:local"]["badges"]
    assert entries["electron:angle:trans"]["extra"] == ["centroid_z", "centroid_r"] or set(entries["electron:angle:trans"]["extra"]) >= {"centroid_z"}


def test_the_pysr_dom_card_builds_mathml_and_never_innerhtml(out):
    d = out["dom"]
    assert d["entries"] == 36 and d["kind"] == "table"
    assert d["maths"] >= 30 and d["madeNs"] == ["http://www.w3.org/1998/Math/MathML"]
    assert "math" in d["madeTags"]
    assert d["codes"] == d["copies"] == d["maths"]
    # The proton's segmentation and angle formulas in the per-shower translated and Local frames.
    assert len(d["absent"]) == 4 and all("no meaningful formula" in a for a in d["absent"])
    assert {c["tier"] for c in d["tierChips"]} == {"law", "unverified", "partial", "not-law"}
    assert all(c["text"] for c in d["tierChips"])
    assert d["r2Titles"] == ["N not reported; point estimate as reported; no interval."]
    leak = [b for b in d["badges"] if b["kind"] == "leak"]
    assert leak and all(b["text"] == "label leakage" and "leakage" in b["title"] for b in leak)
    assert d["inferredTitles"] and all("featureMapInferred" in t for t in d["inferredTitles"])
    assert not any("featureMapInferred" in t for t in d["plainTitles"])
    assert any("Total detected energy of the shower (the report's definition)" in t for t in d["plainTitles"] + d["inferredTitles"])
    assert any("surrogate.json, which is not shipped" in t for t in d["plainTitles"])
    assert d["fallback"] and d["fallback"][0]["mode"] == "text" and "refused" in d["fallback"][0]["title"]
    assert d["clearedChildren"] == 0
    assert d["hasRelayout"] and d["hasBusy"]


def test_a_feature_chip_cross_highlights_and_tells_the_drawer(out):
    a = out["dom"]["after"]
    assert a["highlight"] == "centroid_theta" and a["state"] == {"highlight": "centroid_theta", "scrolling": []}
    assert set(a["pressed"]) == {"centroid_theta"} and a["highlighted"] >= 2
    assert "dark" in out and len(a["matched"]) == len(out["dark"]["pysr"]["all"]["matches"])
    assert all(m.split(":")[0] in {"proton", "muon", "electron", "pion"} for m in a["matched"])
    assert a["status"].startswith("Highlighted: centroid_theta, used by ")
    assert a["events"] == [{"type": "models:panelstate", "detail": {"card": "distill-pysr"}, "bubbles": True}]
    assert out["dom"]["repaint"]["highlight"] == "centroid_theta" and out["dom"]["repaint"]["matched"] > 0
    assert out["dom"]["cleared"]["highlight"] is None and out["dom"]["cleared"]["matched"] == 0
    drawer = out["dark"]["notes"]["pysr:all:energy"]["sections"]["What is drawn"]
    assert any(line.startswith("Highlighted: centroid_theta") for line in drawer)


def test_the_copy_button_says_what_happened(out):
    d = out["dom"]
    assert d["copyOk"]["copied"] and "\\" in d["copyOk"]["copied"]
    assert d["copyOk"]["state"] == "copied" and d["copyOk"]["text"] == "Copied"
    assert d["copyFail"]["state"] == "failed" and "denied by the browser" in d["copyFail"]["title"]
    assert d["copyNone"]["state"] == "failed" and "clipboard is not available" in d["copyNone"]["title"]


def test_the_latex_source_sits_behind_its_toggle(out):
    """As on the Methodology page: the card reads as formulas; the source (ASCII hyphens, which LaTeX needs)
    shows on request, with its Copy button inside the panel the toggle controls."""
    t = out["dom"]["texToggle"]
    assert t["toggles"] == t["panels"] == t["codesInPanels"] == t["copiesInPanels"] == out["dom"]["codes"] > 0
    assert t["hidden"] and t["collapsed"] and t["controls"] and t["idsPlain"] and t["uniqueIds"] == t["panels"]
    assert t["open"] == {"hidden": False, "expanded": "true", "title": "Hide the LaTeX source"}
    assert t["closed"] == {"hidden": True, "expanded": "false", "title": "Show the LaTeX source"}


# ----------------------------------------------------------------- notes --


def test_every_drawer_carries_the_hazard_and_the_four_sections(out):
    every = list(out["dark"]["notes"].values()) + [v["notes"] for s in out["dark"]["curves"].values() for v in s.values()]
    assert len(every) == 2 * len(SPECIES) * len(TASKS) + 3 * len(SPECIES)
    for n in every:
        assert "no interval reported" in n["hazards"], n["title"]
        assert n["headings"][:4] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"], n["title"]
        sel = " ".join(n["sections"]["Selection"])
        assert "models_performance.md" in sel and "do not apply" in sel
        assert any("Recorded exception" in line for line in n["sections"]["Disclosures"])
    assert "label leakage" in out["dark"]["notes"]["pysr:all:energy"]["hazards"]
    assert "label leakage" in out["dark"]["notes"]["triangle:all:segmentation"]["hazards"]
    # a leakage signal is a segmentation finding only (brief 12.1); muon energy's tree beats a network that
    # does not predict the truth, which is a neutral fact with no hazard
    assert "leakage signal" in out["dark"]["notes"]["triangle:muon:segmentation"]["hazards"]
    assert "leakage signal" not in out["dark"]["notes"]["triangle:muon:energy"]["hazards"]
    assert out["dark"]["notes"]["triangle:muon:energy"]["hazards"] == ["no interval reported"]
    assert out["dark"]["notes"]["triangle:electron:energy"]["hazards"] == ["no interval reported"]


def test_the_drawers_carry_the_reports_facts_where_they_apply(out):
    n = out["dark"]["notes"]
    angle = " ".join(n["triangle:all:angle"]["sections"]["Disclosures"])
    assert "particle_origin" in angle and "rotated by the true incidence angle" in angle      # F8
    seg = " ".join(n["triangle:all:segmentation"]["sections"]["Disclosures"])
    assert "defined per particle" in seg and "no tree MAEs for the proton" in seg
    pysr = " ".join(n["pysr:all:energy"]["sections"]["Disclosures"])
    assert "standardised voxel features" in pysr and "inference" in pysr and "F9" in pysr


# ------------------------------------------------- text, colour, contrast --


def _rendered(out):
    for theme in ("dark", "light", "print"):
        t = out[theme]
        for card in t["triangle"].values():
            for layout in ("wide", "narrow"):
                yield from card[layout]["strings"]
        for variants in t["curves"].values():
            for v in variants.values():
                for layout in ("wide", "narrow"):
                    yield from v[layout]["strings"]
                yield from json.dumps(v["notes"], ensure_ascii=False).split('"')
        for n in t["notes"].values():
            yield from json.dumps(n, ensure_ascii=False).split('"')
        for p in t["pysr"].values():
            yield p["status"]
            for e in p["entries"]:
                yield e["r2Text"]
                yield e["netR2Text"]


def test_every_rendered_negative_uses_the_minus_sign(out):
    bad = [s for s in _rendered(out) if HYPHEN_NUMBER.search(re.sub(r"<[^>]+>", "", s))]
    assert not bad, bad[:5]


def test_ink_clears_three_and_text_four_and_a_half_on_every_card(out):
    for theme in ("dark", "light", "print"):
        th = out[theme]["theme"]
        assert min(th["frames"].values()) >= 3, (theme, th["frames"])
        assert th["text"] >= 4.5 and th["muted"] >= 4.5 and th["warn"] >= 4.5, (theme, th)
        for key, card in out[theme]["triangle"].items():
            inks = [i[0] for i in card["wide"]["inks"] if i[0] is not None]
            assert inks and min(inks) >= 3 - 1e-9, (theme, key, min(inks))
            texts = [t for t in card["wide"]["texts"] if t[0] is not None]
            assert all(c >= 4.5 for c, _ in texts), (theme, key, [t for t in texts if t[0] < 4.5][:3])
        for species, variants in out[theme]["curves"].items():
            texts = [t for t in variants["defaults"]["wide"]["texts"] if t[0] is not None]
            assert all(c >= 4.5 for c, _ in texts), (theme, species, [t for t in texts if t[0] < 4.5][:3])


def test_tooltips_go_to_the_layer_unconfined(out):
    for card in out["dark"]["triangle"].values():
        assert card["wide"]["tooltip"] == {"appendTo": "#tooltip-layer", "confine": False}
    assert out["dark"]["curves"]["all"]["defaults"]["wide"]["tooltip"] == {"appendTo": "#tooltip-layer", "confine": False}


def _code(path):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def test_no_colour_literal_innerhtml_eval_or_clock_in_the_new_modules():
    for name, path in MODULES.items():
        code = _code(path)
        assert not COLOUR_LITERAL.search(code), (name, COLOUR_LITERAL.findall(code))
        assert "innerHTML" not in code, name
        assert not re.search(r"\beval\s*\(|\bnew Function\b|\bFunction\s*\(", code), name
        assert "Date" not in code and "Math.random" not in code, name


def test_the_builders_are_exported_for_the_golden():
    exports = {
        "triangle": ["triangleModel", "triangleLayout", "distillTriangleOption", "plotHeight", "DistillTrianglePanel"],
        "curves": ["curvesModel", "curvesLayout", "distillCurvesOption", "plotHeight", "sampleCurve", "DistillCurvesPanel"],
        "pysr": ["pysrModel", "highlightStatus", "PysrMatrixPanel"],
        "notes": ["pysrNotes", "triangleNotes", "curvesNotes"],
    }
    for name, names in exports.items():
        code = MODULES[name].read_text(encoding="utf-8")
        for export in names:
            assert re.search(rf"export (?:function|class|const) {export}\b", code), (name, export)


# -------------------------------------------------------------------- CSS --

#: Every class brief section 6 names (P2 uses them without seeing catalog.css).
BRIEF_CLASSES = [
    "pysr-grid", "pysr-head", "pysr-cell", "pysr-entry", "pysr-species", "pysr-formula", "pysr-source",
    "pysr-copy", "pysr-r2", "tier-chip", "feature-chip", "badge-chip", "catalog-table", "curve-controls",
    "curve-control", "curve-values", "diag-block", "diag-heading", "diag-scope", "caveat-list",
]
BADGE_KINDS = ["leak", "standardised", "negative", "inferred", "not-reported", "one-signed", "starvation", "hit",
               "particle", "proton-only", "training"]


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.DOTALL)


def test_catalog_css_implements_every_class_of_the_brief():
    css = _css()
    for cls in BRIEF_CLASSES:
        assert re.search(rf"\.{cls}\b[^{{]*\{{", css), cls
    for tier, style in (("law", "solid"), ("unverified", "solid"), ("partial", "dashed"), ("not-law", "dotted")):
        rule = re.search(rf'\.pysr-entry\[data-tier="{tier}"\]\s*\{{([^}}]*)\}}', css)
        assert rule and style in rule.group(1), tier
        assert re.search(rf'\.tier-chip\[data-tier="{tier}"\]\s*\{{[^}}]*{style}', css), tier
    assert "var(--muted)" in re.search(r'\.pysr-entry\[data-tier="not-law"\]\s*\{([^}]*)\}', css).group(1)
    for kind in BADGE_KINDS:
        assert f'.badge-chip[data-kind="{kind}"]' in css, kind
    assert re.search(r"\.feature-chip\.is-highlighted\s*\{", css)
    assert re.search(r"\.pysr-formula\s*\{[^}]*overflow-x:\s*auto", css)
    assert re.search(r"\.catalog-table\s*\{[^}]*overflow-x:\s*auto", css)
    assert re.search(r"\.pysr-source\s*\{[^}]*var\(--mono\)", css)


def test_catalog_css_is_tokens_only_and_never_animated():
    css = _css()
    assert not COLOUR_LITERAL.findall(css), COLOUR_LITERAL.findall(css)
    assert not re.search(r"\btransition\s*:|\banimation\s*:|@keyframes", css)
    tokens = (JS.parent / "css" / "tokens.css").read_text(encoding="utf-8")
    for var in set(re.findall(r"var\((--[\w-]+)", css)) - {"--frame-hue"}:
        assert f"{var}:" in tokens, var


# ------------------------------------------------- the fix round (brief 12.1) --


def test_report_numbers_print_with_the_reports_decimals(out):
    """1.000, 1.0000, 0.9840, 0.590 and 53.00 print as the report prints them, on the card and in the drawer."""
    pysr = {e["id"]: e for e in out["dark"]["pysr"]["all"]["entries"]}
    assert pysr["muon:angle:absolute"]["r2Text"] == "1.000" and pysr["muon:angle:absolute"]["netR2Text"] == "1.0000"
    assert pysr["muon:angle:trans"]["netR2Text"] == "0.9840"
    assert pysr["muon:segmentation:absolute"]["r2Text"] == "0.590"
    assert pysr["proton:segmentation:absolute"]["r2Text"] == "\u2248 0"
    assert pysr["pion:angle:local"]["r2Text"] == "\u22120.024"
    d = out["dom"]
    assert d["r2Lines"]["muon:angle:absolute"] == "R\u00b2_PySR 1.000 \u00b7 network R\u00b2 to truth 1.0000"
    assert d["r2Lines"]["muon:segmentation:absolute"].startswith("R\u00b2_PySR 0.590 ")
    tri = out["dark"]["triangle"]["all:angle"]["wide"]["strings"]
    assert any("Pion \u00b7 Per-shower translated \u2014 PySR formula \u2192 Truth MAE: 110.50 mrad" in t for t in tri)
    assert any("Network \u2192 Truth MAE: 53.0 mrad" in t for t in tri)   # 0.0530 rad: the triad's digits x 1000
    assert any("R\u00b2 = 1.000" in t for t in tri)
    rows = " ".join(out["dark"]["notes"]["triangle:all:angle"]["sections"]["Rows"])
    assert "Muon \u00b7 Absolute: Tree \u2192 Network R\u00b2 0.995; PySR formula \u2192 Network R\u00b2 1.000" in rows
    assert "PySR formula \u2192 Truth MAE 113.50 mrad" in rows
    tips = " ".join(out["dark"]["curves"]["all"]["defaults"]["wide"]["strings"])
    assert "R\u00b2_PySR to the network 0.770; the network's R\u00b2 to truth 0.8265" in tips
    pysr_notes = " ".join(out["dark"]["notes"]["pysr:all:energy"]["sections"]["Tiers"])
    assert "R\u00b2_PySR is 1.000 (at least 0.75) and the network's R\u00b2 to truth is 1.0000" in pysr_notes


def test_tree_beats_network_is_a_neutral_badge_never_a_leak(out):
    rows = {r["key"]: r for r in out["dark"]["triangle"]["all:energy"]["model"]["rows"]}
    assert rows["muon:absolute"]["badges"] == ["beats"] and rows["muon:trans"]["badges"] == ["beats"]
    assert not rows["muon:absolute"]["leakSignal"] and rows["muon:absolute"]["leakSignalText"] is None
    seg = {r["key"]: r for r in out["dark"]["triangle"]["all:segmentation"]["model"]["rows"]}
    assert "signal" in seg["muon:absolute"]["badges"] and "beats" not in seg["muon:absolute"]["badges"]
    for theme in ("dark", "light", "print"):
        texts = out[theme]["triangle"]["all:energy"]["wide"]["texts"]
        neutral = [t for t in texts if "tree beats the network on truth" in t[1]]
        assert neutral and all("\u2691" not in t[1] for t in neutral)
        assert all(t[0] >= 4.5 - 1e-9 for t in neutral), (theme, neutral)
        warn = [t for t in out[theme]["triangle"]["all:segmentation"]["wide"]["texts"] if "leakage signal" in t[1]]
        assert warn and all(t[1].startswith("\u2691") for t in warn)
    n = out["dark"]["notes"]["triangle:muon:energy"]
    disc = " ".join(n["sections"]["Disclosures"])
    assert "a depth-4 tree on the summary features predicts the truth better than the network on this sample" in disc
    assert "A neutral fact, not label leakage" in disc and "leakage signal" not in n["hazards"]
    legend = " ".join(n["sections"]["Marks and legend"])
    assert "tree beats the network on truth" in legend and "no hazard" in legend


def test_long_formulas_step_down_to_a_floor_then_scroll_in_their_cell(out):
    d = out["dom"]
    assert d["fits"]["muon:segmentation:absolute"] == "floor"
    assert d["fits"]["muon:angle:trans"] == "compact"
    assert d["fits"]["electron:energy:absolute"] == "normal"
    assert d["hints"] >= 30 and d["hintsShown"] == 0      # nothing measured overflowing on the fake DOM
    sc = d["scroll"]
    assert sc["state"] == {"highlight": None, "scrolling": ["muon:segmentation:absolute"]}
    assert sc["marked"] == "true" and sc["unmarked"] == "false"
    assert sc["hintShown"] and not sc["otherHintShown"]
    assert sc["events"] == 1 and sc["eventsAgain"] == 1    # one event per change, none when nothing changed
    disc = " ".join(d["scrollNotes"]["sections"]["Disclosures"])
    assert "14 px up to 40 characters" in disc and "11 px beyond, the floor" in disc and "never the page" in disc
    assert "Scrolling sideways at the card's current width: Muon Segmentation Absolute." in disc


def test_the_css_styles_the_fit_steps_the_scrollbar_and_the_new_badges():
    css = CSS.read_text(encoding="utf8")
    assert '.pysr-formula[data-fit="compact"] { font-size: 12px; }' in css
    assert '.pysr-formula[data-fit="floor"] { font-size: 11px; }' in css
    block = css[css.index(".pysr-formula {"):]
    block = block[:block.index("}")]
    assert "overflow-x: auto" in block and "scrollbar-width: thin" in block and "scrollbar-gutter: stable" in block
    assert ".pysr-scroll-hint[hidden] { display: none; }" in css
    assert '.badge-chip[data-kind="tree-beats"]' in css and '.badge-chip[data-kind="signal"]::before' in css
    assert not re.search(r"\b(transition|animation)\s*:", css)
