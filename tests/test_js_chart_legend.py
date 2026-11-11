"""The legend memory of ``ChartPanel`` (``panels/chart_panel.js``), executed under Node.

Every paint is ``setOption(option, {notMerge: true})``, which builds a new
ECharts model and forgot the legend: a series the reader had switched off came
back on a theme switch or a card control (Martin's report on the energy-resolution
card, 2026-11-11). The panel now records the reader's legend choices and lays
them over every option; while they hide anything it clears the chart before the
option, because ECharts 5.5.1 throws when a custom series view the legend
emptied next draws fewer items (the module header of chart_panel.js has the stack).

Pinned here:

* ``withLegendMemory`` on an object legend and on an array legend; a builder's
  own ``selected`` kept where the memory is silent and overridden where it
  speaks; an empty memory returning the option itself, deep-equal; names the
  legend does not list kept in the memory but never applied (ECharts would hide
  a series of that name with no entry to bring it back), while a legend that
  lists no ``data`` takes them all and a hidden legend none; the real
  res-scaling options of both views, whose legend entries are the series labels;
* ``legendChange``: a named event records its entry alone, select-all and
  inverse every entry, a batch each of its events;
* the paint decision, on a fake chart: the listeners are on every legend event,
  once; ``clear()`` precedes ``setOption`` exactly when the memory holds a
  false; the memory survives repaints, a relayout, ``clear()`` and a card held
  at zero size; every legend event tells ``onLegendChange``, with the panel;
* the ink of a hidden entry (Martin's approval, 2026-11-11): ECharts drew it in
  ``THEME.border``, 1.33:1 on the dark card and 1.45:1 on the light one. It is
  now ``legendInactiveInk()``, the faintest tint of the muted ink that clears
  4.5:1 (#808993 on #1c2128, #6e7780 on #ffffff), for the text, the swatch and
  a line series' swatch line; laid at paint time only while the legend hides
  an entry, and merged into the legend on show by the click that hides one;
* the drawer: ``legendHiddenNames`` names only what the legend on show lists,
  ``legendHiddenLine`` says so, and panel_notes.js ``withHiddenLegend`` puts the
  line first in Marks and legend (making the section, before Reading the
  density axis, where a drawer has none), with no hazard;
* the export (``export/figure.js``): the print option carries the memory; a
  legend that hides an entry greys it in the lightest tint of the print muted
  ink that clears 4.5:1 on white (#6f7681), where ECharts would have drawn it
  in the print border, the near-black #111827, darker than the entries on show;
  a panel without a memory, or with one that hides nothing, keeps the legend's
  own inks; the screen theme is back after;
* Page 1's energy panel (``panels/energy.js``), on the recorded two-shower
  response: the same listeners, memory, clear and ink through the shared
  helpers, on its two legends (the series and the references) each taking the
  names it lists; across shower A alone (fewer series) and back; its drawer
  line; its export.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import JS, NODE, PAYLOADS, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The entry Martin switched off on the two-shower card.
DEPOSIT_A = "Shower A · Calibrated deposit c·E_dep — linear-sum benchmark"

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir, depositA] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const json = (o) => JSON.stringify(o);

/* ---- a fake DOM and a fake ECharts: every chart records its calls ------------ */
const element = { clientWidth: 600, clientHeight: 400, style: {}, classList: { toggle() {} }, closest: () => null,
  replaceChildren() {} };
const charts = [];
function makeChart(renderer) {
  const chart = {
    renderer, calls: [], handlers: {},
    getWidth: () => element.clientWidth, getHeight: () => element.clientHeight,
    getDom: () => element, getZr: () => ({ on() {}, off() {} }), dispatchAction() {},
    on(type, fn) { (this.handlers[type] ??= []).push(fn); },
    resize() { this.calls.push(['resize']); },
    clear() { this.calls.push(['clear']); },
    setOption(option, flags) { this.calls.push(['setOption', option, flags ?? null]); },
    renderToSVGString: () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    getDataURL: () => 'data:image/png;base64,',
    dispose() {},
  };
  charts.push(chart);
  return chart;
}
// No 2-D context: textfit.js then estimates text widths, as in the other Node tests.
const fakeNode = () => ({ style: {}, click() {}, remove() {}, appendChild() {}, getContext: () => null });
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid', hash: '' } };
globalThis.document = { createElement: fakeNode, body: { appendChild() {} }, getElementById: () => element };
globalThis.echarts = { init: (dom, theme, opts) => makeChart(opts?.renderer ?? 'canvas') };
// The download: no object URL to keep, and no two-second wait for its release.
URL.createObjectURL = () => 'blob:test';
URL.revokeObjectURL = () => {};
const realTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn) => realTimeout(fn, 0);

const cp = await imp('panels/chart_panel.js');
const rs = await imp('panels/resolution_scaling.js');
const fig = await imp('export/figure.js');
const { THEME } = await imp('scale.js');
const out = {};

/* ---- withLegendMemory ------------------------------------------------------ */
const series = [{ type: 'line', name: 'A', data: [[0, 1]] }, { type: 'line', name: 'B', data: [[0, 2]] }];
const objectLegend = { legend: { show: true, data: [{ name: 'A', icon: 'circle' }, 'B'] }, series };
const memoryAB = Object.freeze({ A: false });
const o1 = cp.withLegendMemory(objectLegend, memoryAB);
out.object = {
  selected: o1.legend.selected, untouched: json(objectLegend.legend), keepsRest: o1.series === series,
  legendRest: json({ ...o1.legend, selected: undefined }) === json(objectLegend.legend), fresh: o1 !== objectLegend,
};

const arrayLegend = { legend: [{ data: ['A'] }, { data: [{ name: 'B' }], selected: { B: true } }, { data: ['C'] }], series };
const o2 = cp.withLegendMemory(arrayLegend, { A: false, B: false });
out.array = {
  selected: o2.legend.map((l) => l.selected ?? null), third: o2.legend[2] === arrayLegend.legend[2],
  untouched: json(arrayLegend.legend), isArray: Array.isArray(o2.legend),
  none: cp.withLegendMemory(arrayLegend, { Z: false }) === arrayLegend,
};

const defaults = { legend: { data: ['A', 'B', 'C', 'D'], selected: { A: false, B: false, D: true } }, series };
out.defaults = cp.withLegendMemory(defaults, { B: true, C: false }).legend.selected;

out.empty = {
  same: [{}, null, undefined, { A: 'no' }].map((m) => cp.withLegendMemory(objectLegend, m) === objectLegend),
  noLegend: cp.withLegendMemory({ series }, { A: false }).legend ?? null,
  noLegendSame: (() => { const o = { series }; return cp.withLegendMemory(o, { A: false }) === o; })(),
};

const memoryAbsent = { A: false, Z: false };
const before = json(memoryAbsent);
out.absent = {
  listed: cp.withLegendMemory({ legend: { data: ['A', 'B'] }, series }, memoryAbsent).legend.selected,
  unlisted: cp.withLegendMemory({ legend: { data: ['B'] }, series }, memoryAbsent).legend.selected ?? null,
  derived: cp.withLegendMemory({ legend: { show: true }, series }, memoryAbsent).legend.selected,
  hidden: cp.withLegendMemory({ legend: { show: false, data: ['A'] }, series }, memoryAbsent).legend.selected ?? null,
  memoryKept: json(memoryAbsent) === before,
};

// The card Martin reported: both views of the two-shower response.
const payload = load('res_scaling_two');
const metrics = { width: 760, height: 600 };
out.res = {};
for (const view of ['linear', 'energy']) {
  const opts = { view, windows: 'all', shower: 'both', reference: 'deposit', palette: 'viridis', card: 'res-scaling' };
  const built = view === 'energy' ? rs.energyViewOption(payload, opts, metrics).option
    : rs.resolutionScalingOption(payload, opts, metrics);
  const hid = cp.withLegendMemory(built, { [depositA]: false, 'An entry of another card': false });
  out.res[view] = {
    names: (built.legend.data ?? []).map((d) => d?.name ?? d),
    seriesOfName: built.series.filter((s) => s.name === depositA).length,
    same: cp.withLegendMemory(built, {}) === built,
    sameJson: json(cp.withLegendMemory(built, {})) === json(built),
    builderSelected: built.legend.selected ?? null,
    selected: hid.legend.selected,
    seriesShared: hid.series === built.series,
    restSame: json({ ...hid, legend: null }) === json({ ...built, legend: null }),
    legendRestSame: json({ ...hid.legend, selected: null }) === json({ ...built.legend, selected: null }),
  };
}

/* ---- legendChange and legendHides ---------------------------------------- */
out.change = {
  named: cp.legendChange({ type: 'legendselectchanged', name: 'A', selected: { A: false, B: true, C: false } }),
  all: cp.legendChange({ type: 'legendselectall', selected: { A: true, B: true } }),
  inverse: cp.legendChange({ type: 'legendinverseselect', selected: { A: false, B: true } }),
  batch: cp.legendChange({ type: 'legendunselected', batch: [{ name: 'A', selected: { A: false, B: true } },
    { name: 'B', selected: { A: false, B: false } }] }),
  numeric: cp.legendChange({ name: 3, selected: { 3: false } }),
  malformed: [null, {}, { name: 'A' }, { name: 'A', selected: { A: 'no' } }].map((e) => cp.legendChange(e)),
};
out.hides = [{}, { A: true }, { A: true, B: false }, null].map((m) => cp.legendHides(m));
out.events = cp.LEGEND_EVENTS;

/* ---- the paint decision, on a fake chart --------------------------------- */
class TinyPanel extends cp.ChartPanel {
  buildOption() {
    return { option: { ...cp.baseOption(), legend: cp.chartLegend([{ name: 'A' }, { name: 'B' }]), series } };
  }
}
const panel = new TinyPanel(element);
// Who the panel tells of a legend event (the page's drawer), and with what.
const told = [];
panel.onLegendChange = (p) => told.push(p === panel);
const steps = [];
let live = null;
// A legend's inks for a hidden entry: text, swatch border and a line series' swatch line, and the keys it carries.
const inkOf = (legend) => (legend && !Array.isArray(legend) ? { inactive: legend.inactiveColor ?? null,
  border: legend.inactiveBorderColor ?? null, line: legend.lineStyle?.inactiveColor ?? null,
  keys: Object.keys(legend).sort() } : null);
const step = (what, fn) => {
  const from = live ? live.calls.length : 0;
  const toldFrom = told.length;
  fn();
  live = live ?? charts.find((c) => c.renderer === 'canvas') ?? null;
  const calls = live ? live.calls.slice(from) : [];
  steps.push({ what, memory: { ...panel.legendSelected },
    calls: calls.map(([kind, option, flags]) => (kind === 'setOption'
      ? [kind, option.legend?.selected ?? null, Boolean(flags?.notMerge)] : [kind])),
    inks: calls.filter(([kind]) => kind === 'setOption').map(([, option]) => inkOf(option.legend)),
    told: told.slice(toldFrom), liveLegend: inkOf(panel.liveLegend) });
};
const fire = (type, event) => (live.handlers[type] ?? []).forEach((fn) => fn({ type, ...event }));
step('first render', () => panel.render({ n: 1 }, {}));
step('a click switches A off', () => fire('legendselectchanged', { name: 'A', selected: { A: false, B: true } }));
step('a repaint (theme, control)', () => panel.render({ n: 1 }, {}));
step('a relayout at a new width', () => { element.clientWidth = 640; panel.relayout(); });
step("the panel's clear", () => panel.clear());
step('a new payload', () => panel.render({ n: 2 }, {}));
step('held at zero size', () => { element.clientWidth = 0; panel.render({ n: 3 }, {}); });
step('shown again', () => { element.clientWidth = 640; panel.relayout(); });
step('a click switches A on', () => fire('legendselectchanged', { name: 'A', selected: { A: true, B: true } }));
step('a repaint with nothing hidden', () => panel.render({ n: 3 }, {}));
step('a scripted unselect of B', () => fire('legendunselected', { name: 'B', selected: { A: true, B: false } }));
step('a repaint with B hidden', () => panel.render({ n: 3 }, {}));
step('select all', () => fire('legendselectall', { selected: { A: true, B: true } }));
step('a repaint after select all', () => panel.render({ n: 3 }, {}));
step('inverse', () => fire('legendinverseselect', { selected: { A: false, B: false } }));
step('a repaint after inverse', () => panel.render({ n: 3 }, {}));
out.steps = steps;
out.handlers = Object.fromEntries(Object.entries(live.handlers).map(([k, v]) => [k, v.length]));
out.canvasCharts = charts.filter((c) => c.renderer === 'canvas').length;

/* ---- the legible ink of a hidden entry, on each card --------------------- */
const scale = await imp('scale.js');
const { contrast } = await imp('palette.js');
const measureInk = () => {
  const card = cp.rgbOf(THEME.card);
  const muted = cp.rgbOf(THEME.muted);
  const ink = cp.legendInactiveInk();
  const rgb = cp.rgbOf(ink);
  return { ink, card: THEME.card, muted: THEME.muted, border: THEME.border,
    inkOnCard: contrast(rgb, card), mutedOnCard: contrast(muted, card), borderOnCard: contrast(cp.rgbOf(THEME.border), card),
    // A tint of the muted ink towards the card: every channel between the two.
    tint: rgb.every((v, i) => (v - card[i]) * (muted[i] - v) >= 0) };
};
out.inks = { dark: measureInk(), textContrast: cp.TEXT_CONTRAST };
scale.setScreenTheme('light');
out.inks.light = measureInk();
// A repaint on the light card while A and B are hidden (the memory the paint steps left): the light card's ink.
{
  const from = live.calls.length;
  panel.render({ n: 4 }, {});
  out.lightPaint = live.calls.slice(from).filter(([kind]) => kind === 'setOption').map(([, option]) => inkOf(option.legend));
}
scale.setScreenTheme('dark');

// withInactiveInk, pure: only a legend that hides an entry is inked, and the option is otherwise itself.
{
  const legendAB = cp.chartLegend([{ name: 'A' }, { name: 'B' }]);
  const shown = { legend: { ...legendAB, selected: { A: true } }, series };
  const hiding = { legend: { ...legendAB, selected: { A: false, B: true }, lineStyle: { width: 3 } }, series };
  const arrayed = { legend: [{ data: ['A'], selected: { A: false } }, { data: ['B'] }, { data: ['C'], show: false, selected: { C: false } }], series };
  const plain = { legend: legendAB, series };
  const inked = cp.withInactiveInk(hiding);
  const inkedArray = cp.withInactiveInk(arrayed);
  out.inkRules = {
    same: [cp.withInactiveInk(plain) === plain, cp.withInactiveInk(shown) === shown],
    noLegend: (() => { const o = { series }; return cp.withInactiveInk(o) === o; })(),
    inked: inkOf(inked.legend), lineKept: inked.legend.lineStyle?.width ?? null, selectedKept: inked.legend.selected,
    seriesShared: inked.series === series, untouched: JSON.stringify(hiding.legend),
    array: inkedArray.legend.map(inkOf), arraySame: [1, 2].map((i) => inkedArray.legend[i] === arrayed.legend[i]),
    given: inkOf(cp.withInactiveInk(hiding, '#123456').legend),
  };
}

/* ---- what the drawer names: legendHiddenNames, legendHiddenLine, withHiddenLegend ---- */
{
  const pn = await imp('panel_notes.js');
  out.hiddenNames = {
    listed: cp.legendHiddenNames({ legendSelected: { B: false, Z: false, A: false, C: true },
      liveLegend: { data: ['A', { name: 'B' }, 'C'] } }),
    array: cp.legendHiddenNames({ legendSelected: { R: false, A: false },
      liveLegend: [{ data: ['A'] }, { data: ['R', 'A'] }, { data: ['Q'], show: false }] }),
    derived: cp.legendHiddenNames({ legendSelected: { A: false }, liveLegend: { selected: { A: false, B: true } } }),
    none: [cp.legendHiddenNames(null), cp.legendHiddenNames({}), cp.legendHiddenNames({ legendSelected: { A: false } }),
      cp.legendHiddenNames({ legendSelected: { A: false }, liveLegend: { data: ['A'], show: false } })],
    panel: cp.legendHiddenNames(panel),
  };
  out.hiddenLine = { none: [cp.legendHiddenLine([]), cp.legendHiddenLine(null), cp.legendHiddenLine([''])],
    one: cp.legendHiddenLine(['A']), two: cp.legendHiddenLine(['A', 'B · fit']) };
  const legendNotes = { title: 't', hazards: [], sections: [{ heading: pn.SECTION.selection, lines: ['s'] },
    { heading: pn.SECTION.legend, lines: ['m'] }] };
  const densityNotes = { title: 'e', hazards: ['h'], sections: [{ heading: pn.SECTION.selection, lines: ['s'] },
    { heading: pn.SECTION.disclosures, lines: ['d'] }, { heading: pn.SECTION.density, lines: ['r'] }] };
  const plainNotes = { title: 'p', hazards: [], sections: [{ heading: pn.SECTION.drawn, lines: ['w'] }] };
  const hiding = { legendSelected: { A: false }, liveLegend: { data: ['A', 'B'] } };
  const before = JSON.stringify([legendNotes, densityNotes, plainNotes]);
  const shape = (n) => ({ title: n.title, hazards: n.hazards, sections: n.sections.map((s) => [s.heading, s.lines]) });
  out.withHidden = {
    legend: shape(pn.withHiddenLegend(legendNotes, hiding)),
    density: shape(pn.withHiddenLegend(densityNotes, hiding)),
    plain: shape(pn.withHiddenLegend(plainNotes, hiding)),
    same: [pn.withHiddenLegend(legendNotes, { legendSelected: { A: true }, liveLegend: { data: ['A'] } }) === legendNotes,
      pn.withHiddenLegend(legendNotes, { legendSelected: { Z: false }, liveLegend: { data: ['A'] } }) === legendNotes,
      pn.withHiddenLegend(legendNotes, null) === legendNotes, pn.withHiddenLegend(null, hiding) === null],
    unchanged: JSON.stringify([legendNotes, densityNotes, plainNotes]) === before,
    line: cp.legendHiddenLine(['A']),
  };
}

/* ---- the export ------------------------------------------------------------ */
const exportOf = (p) => {
  const n = charts.length;
  fig.exportPanel(p, { panelId: 'tiny', format: 'svg', widthMm: 85, state: null });
  const made = charts.slice(n).filter((c) => c.renderer === 'svg');
  const set = made.flatMap((c) => c.calls.filter(([kind]) => kind === 'setOption'));
  return { charts: made.length, selected: set.map(([, option]) => option.legend?.selected ?? null),
    inks: set.map(([, option]) => [option.legend?.inactiveColor ?? null, option.legend?.inactiveBorderColor ?? null]),
    lines: set.map(([, option]) => option.legend?.lineStyle?.inactiveColor ?? null),
    screenBack: THEME.medium !== 'print' };
};
out.export = { hidden: exportOf(panel) };
const plain = {
  kind: 'chart', lastPayload: { n: 1 }, lastOpts: {},
  exportMetrics: (width) => ({ width, height: 200 }),
  buildOption: () => ({ option: { legend: { data: ['A', 'B'] }, series } }),
};
out.export.noMemory = exportOf(plain);
const exportWith = (memory) => {
  const p = new TinyPanel(element);
  p.legendSelected = memory;
  p.lastPayload = { n: 1 };
  p.lastOpts = {};
  return exportOf(p);
};
out.export.nothingHidden = exportWith({});
out.export.allShown = exportWith({ A: true });
// The print inks, measured under the print tokens: the grey the export gives a hidden entry, against the ink of
// the entries on show and the border ECharts would otherwise use.
{
  const { PRINT_TOKENS } = await imp('export/tokens.js');
  const { contrast } = await imp('palette.js');
  const saved = { ...THEME };
  Object.assign(THEME, PRINT_TOKENS);
  const white = cp.rgbOf(THEME.card);
  const ink = fig.printInactiveInk();
  out.printInk = { ink, inkOnCard: contrast(cp.rgbOf(ink), white), mutedOnCard: contrast(cp.rgbOf(THEME.muted), white),
    border: THEME.border, screenRule: cp.legendInactiveInk() };
  Object.assign(THEME, saved);
}

/* ---- Page 1's energy panel: the same memory, events, clear, ink, drawer and export ---- */
{
  const energyMod = await imp('panels/energy.js');
  const pn = await imp('panel_notes.js');
  const payload = load('energy_d_two');
  element.clientWidth = 760;
  element.clientHeight = 380;
  const first = charts.length;
  const ep = new energyMod.EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
  const chart = charts[first];
  const eTold = [];
  ep.onLegendChange = (p) => eTold.push(p === ep);
  const opts = (shower) => ({ palette: 'viridis', kind: 'pred', shower });
  const legendsOf = (option) => (option.legend ?? []).map((l) => ({ data: (l.data ?? []).map((d) => d?.name ?? d),
    selected: l.selected ?? null, ...inkOf(l) }));
  const sets = (from) => chart.calls.slice(from).map(([kind, option, flags]) => (kind === 'setOption'
    ? { kind, notMerge: Boolean(flags?.notMerge), legends: Array.isArray(option.legend) ? legendsOf(option)
      : option.legend ?? null, series: (option.series ?? []).length } : { kind }));
  const fireOn = (type, event) => (chart.handlers[type] ?? []).forEach((fn) => fn({ type, ...event }));
  const record = {};
  let from = chart.calls.length;
  ep.render(payload, opts('both'));
  record.fresh = sets(from);
  const [main, bench] = ep.liveLegend;
  const entry = main.data[0];
  const reference = bench.data[0];
  record.entry = entry;
  record.reference = reference;
  record.handlers = Object.fromEntries(Object.entries(chart.handlers).map(([k, v]) => [k, v.length]));
  from = chart.calls.length;
  fireOn('legendselectchanged', { name: entry, selected: { [entry]: false } });
  record.click = sets(from);
  record.memory = { ...ep.legendSelected };
  from = chart.calls.length;
  ep.render(payload, opts('both'));
  record.repaint = sets(from);
  // Fewer series: shower A alone (main.js's A / B / Both buttons repaint the payload in hand).
  from = chart.calls.length;
  ep.render(payload, opts('a'));
  record.showerA = sets(from);
  from = chart.calls.length;
  ep.render(payload, opts('both'));
  record.both = sets(from);
  // An entry of the references' own legend (the second): its legend alone takes the ink.
  from = chart.calls.length;
  fireOn('legendselectchanged', { name: reference, selected: { [entry]: false, [reference]: false } });
  record.referenceClick = sets(from);
  record.hiddenNames = cp.legendHiddenNames(ep);
  const notes = pn.withHiddenLegend(pn.energyNotes({ payload, notices: ep.lastNotices }), ep);
  record.notes = notes.sections.map((s) => [s.heading, s.lines]);
  record.builderNotes = pn.energyNotes({ payload, notices: ep.lastNotices }).sections.map((s) => s.heading);
  // The export: the figure leaves both out, its legends grey them in the print's ink.
  const n = charts.length;
  fig.exportPanel(ep, { panelId: 'energy', format: 'svg', widthMm: 85, state: null });
  const printed = charts.slice(n).filter((c) => c.renderer === 'svg')
    .flatMap((c) => c.calls.filter(([kind]) => kind === 'setOption')).map(([, option]) => legendsOf(option));
  record.export = { printed, screenBack: THEME.medium !== 'print' };
  record.told = [...eTold];
  // Both back on: nothing is named, the inks stay until the next paint and that paint lays none.
  fireOn('legendselectall', { selected: Object.fromEntries([...main.data, ...bench.data].map((name) => [name, true])) });
  const fresh = pn.energyNotes({ payload, notices: ep.lastNotices });
  record.allBack = { names: cp.legendHiddenNames(ep), same: pn.withHiddenLegend(fresh, ep) === fresh };
  from = chart.calls.length;
  ep.render(payload, opts('both'));
  record.afterAll = sets(from);
  ep.clear();
  record.cleared = { memory: { ...ep.legendSelected }, live: ep.liveLegend, names: cp.legendHiddenNames(ep) };
  out.energy = record;
}

console.log(JSON.stringify(out));
process.exit(0);
"""


@pytest.fixture(scope="module")
def result() -> dict:
    return _run(_SCRIPT, [JS.as_uri(), str(PAYLOADS), DEPOSIT_A])


# ------------------------------------------------------------ withLegendMemory --


def test_an_object_legend_takes_the_memory_and_nothing_else_moves(result):
    got = result["object"]
    assert got["selected"] == {"A": False}
    assert got["fresh"] and got["keepsRest"] and got["legendRest"], got
    # The builder's option is not mutated.
    assert '"selected"' not in got["untouched"], got


def test_each_legend_of_an_array_takes_the_names_it_lists(result):
    got = result["array"]
    assert got["isArray"]
    assert got["selected"] == [{"A": False}, {"B": False}, None], got
    # A legend the memory says nothing about is the same object, and an array none of whose legends moves is the
    # option itself.
    assert got["third"] and got["none"], got
    assert '"selected":{"B":true}' in got["untouched"], "the builder's array was mutated"


def test_the_builders_selected_survives_where_the_memory_is_silent(result):
    # A, D kept from the builder; B overridden (the reader switched it back on); C added (switched off).
    assert result["defaults"] == {"A": False, "B": True, "C": False, "D": True}


def test_an_empty_memory_returns_the_option_itself(result):
    got = result["empty"]
    # {}, null, undefined and a memory without a boolean: the same object, so the builders' outputs and the dark
    # golden cannot move.
    assert got["same"] == [True, True, True, True], got
    # An option without a legend never gains one.
    assert got["noLegend"] is None and got["noLegendSame"], got


def test_a_name_the_legend_does_not_list_stays_in_the_memory_and_hides_nothing(result):
    got = result["absent"]
    assert got["listed"] == {"A": False}, got
    assert got["unlisted"] is None, got
    # A legend without `data` lists every named series, so it takes the whole memory; a hidden legend takes none.
    assert got["derived"] == {"A": False, "Z": False}, got
    assert got["hidden"] is None, got
    assert got["memoryKept"], got


@pytest.mark.parametrize("view", ["linear", "energy"])
def test_the_resolution_cards_legend_takes_the_memory_in_both_views(result, view):
    got = result["res"][view]
    assert DEPOSIT_A in got["names"], got["names"]
    # Every mark of the series carries its label, so its entry hides them all.
    assert got["seriesOfName"] >= 2, got
    assert got["builderSelected"] is None, "the builder sets no selected state of its own"
    assert got["same"] and got["sameJson"], got
    assert got["selected"] == {DEPOSIT_A: False}, got
    assert got["seriesShared"] and got["restSame"] and got["legendRestSame"], got


# ---------------------------------------------------------------- legendChange --


def test_a_legend_event_records_what_it_changed(result):
    got = result["change"]
    # A click names its entry: the rest of its `selected` map is the builder's state, not the reader's choice.
    assert got["named"] == {"A": False}
    assert got["all"] == {"A": True, "B": True}
    assert got["inverse"] == {"A": False, "B": True}
    assert got["batch"] == {"A": False, "B": False}
    assert got["numeric"] == {"3": False}
    assert got["malformed"] == [{}, {}, {}, {}]
    assert result["hides"] == [False, False, True, False]
    assert result["events"] == ["legendselectchanged", "legendselected", "legendunselected", "legendselectall",
                                "legendinverseselect"]


# ------------------------------------------------------------ the paint decision --


def _steps(result):
    return {s["what"]: s for s in result["steps"]}


def test_the_panel_listens_to_every_legend_event_once(result):
    assert result["canvasCharts"] == 1
    assert result["handlers"] == {event: 1 for event in result["events"]}, result["handlers"]


def test_the_chart_is_cleared_before_the_option_only_while_the_legend_hides_a_series(result):
    steps = _steps(result)
    set_only = lambda selected: [["setOption", selected, True]]  # noqa: E731
    cleared = lambda selected: [["clear"], ["setOption", selected, True]]  # noqa: E731
    # The ink merged into the legend on show: no notMerge, no `selected`, no clear (see the ink tests below).
    merged = [["setOption", None, False]]
    assert steps["first render"]["calls"] == set_only(None)
    assert steps["a click switches A off"]["memory"] == {"A": False}
    assert steps["a click switches A off"]["calls"] == merged
    assert steps["a repaint (theme, control)"]["calls"] == cleared({"A": False})
    assert steps["a relayout at a new width"]["calls"] == cleared({"A": False})
    assert steps["a new payload"]["calls"] == cleared({"A": False})
    # A card held at zero size paints nothing; shown again it paints with the memory.
    assert steps["held at zero size"]["calls"] == []
    assert steps["shown again"]["calls"] == cleared({"A": False})
    # Switched back on: nothing hidden, no clear; the remembered `true` is laid over the option.
    assert steps["a click switches A on"]["memory"] == {"A": True}
    # Nothing is drawn as off any more: no merge (the legend keeps the ink until the next paint, which lays none).
    assert steps["a click switches A on"]["calls"] == []
    assert steps["a repaint with nothing hidden"]["calls"] == set_only({"A": True})
    assert steps["a scripted unselect of B"]["memory"] == {"A": True, "B": False}
    assert steps["a scripted unselect of B"]["calls"] == merged
    assert steps["a repaint with B hidden"]["calls"] == cleared({"A": True, "B": False})
    assert steps["select all"]["memory"] == {"A": True, "B": True}
    assert steps["select all"]["calls"] == []
    assert steps["a repaint after select all"]["calls"] == set_only({"A": True, "B": True})
    assert steps["inverse"]["memory"] == {"A": False, "B": False}
    assert steps["inverse"]["calls"] == merged
    assert steps["a repaint after inverse"]["calls"] == cleared({"A": False, "B": False})


def test_the_memory_survives_the_panels_clear(result):
    step = _steps(result)["the panel's clear"]
    assert step["calls"] == [["clear"]], step
    assert step["memory"] == {"A": False}, step
    # The legend on show goes with the picture; the memory does not.
    assert step["liveLegend"] is None, step


def test_every_legend_event_tells_the_page_once_with_the_panel(result):
    """A legend click redraws nothing of the page, but the drawer names what is hidden: `onLegendChange` is told."""
    for step in result["steps"]:
        expected = [True] if step["what"].startswith(("a click", "a scripted", "select all", "inverse")) else []
        assert step["told"] == expected, step


# --------------------------------------------------- the ink of a hidden entry --

#: The inactive inks: the faintest tint of each card's muted ink at 4.5:1 (chart_panel.js `legendInactiveInk`).
DARK_INACTIVE, LIGHT_INACTIVE, PRINT_INACTIVE = "#808993", "#6e7780", "#6f7681"


@pytest.mark.parametrize(("theme", "ink", "card"), [("dark", DARK_INACTIVE, "#1c2128"),
                                                     ("light", LIGHT_INACTIVE, "#ffffff")])
def test_a_hidden_entry_is_drawn_legible_on_each_screen_card(result, theme, ink, card):
    """ECharts drew a hidden entry, text and swatch, in `THEME.border`: 1.33:1 on the dark card, 1.45:1 on the light
    one, so the reader could not find it again. Its ink is now the faintest tint of the muted ink of the entries on
    show that clears the 4.5:1 text floor (CLAUDE.md section 2): dimmer than the muted ink, by as much as the card
    allows."""
    got = result["inks"][theme]
    assert result["inks"]["textContrast"] == 4.5
    assert got["card"] == card and got["ink"] == ink, got
    assert got["inkOnCard"] >= 4.5, got
    assert got["inkOnCard"] < got["mutedOnCard"], "dimmer than the entries on show"
    assert got["inkOnCard"] < 4.6, "the faintest legible tint"
    assert got["tint"], "a tint of the muted ink towards the card"
    assert got["borderOnCard"] < 1.5, "the ink it replaces"


def test_the_ink_is_laid_only_while_the_legend_hides_an_entry(result):
    steps = _steps(result)
    builders = {"inactive": "#30363d", "border": None, "line": None}
    hidden = {"inactive": DARK_INACTIVE, "border": DARK_INACTIVE, "line": DARK_INACTIVE}
    pick = lambda ink: {k: ink[k] for k in ("inactive", "border", "line")}  # noqa: E731
    # Nothing hidden: the builder's own ink (THEME.border), nothing added.
    for what in ("first render", "a repaint with nothing hidden", "a repaint after select all"):
        assert [pick(i) for i in steps[what]["inks"]] == [builders], (what, steps[what]["inks"])
    # Hidden: the text, the swatch and a line series' swatch line, on every paint.
    for what in ("a repaint (theme, control)", "a relayout at a new width", "a new payload", "shown again",
                 "a repaint with B hidden", "a repaint after inverse"):
        assert [pick(i) for i in steps[what]["inks"]] == [hidden], (what, steps[what]["inks"])
    # A click that hides an entry merges the inks alone into the legend on show: it keeps its state and its page.
    for what in ("a click switches A off", "a scripted unselect of B", "inverse"):
        ink = steps[what]["inks"]
        assert ink == [{**hidden, "keys": ["inactiveBorderColor", "inactiveColor", "lineStyle"]}], (what, ink)
        assert steps[what]["liveLegend"]["inactive"] == DARK_INACTIVE, steps[what]
    # On the light card, the light card's ink.
    assert [pick(i) for i in result["lightPaint"]] == [{k: LIGHT_INACTIVE for k in ("inactive", "border", "line")}]


def test_with_inactive_ink_is_pure_and_inks_only_a_legend_that_hides(result):
    got = result["inkRules"]
    # A legend that hides nothing, and an option without a legend: the option itself.
    assert got["same"] == [True, True] and got["noLegend"], got
    assert {k: got["inked"][k] for k in ("inactive", "border", "line")} == {
        "inactive": DARK_INACTIVE, "border": DARK_INACTIVE, "line": DARK_INACTIVE}
    # The legend's own line style and selected state are kept; the series are shared; the input is not mutated.
    assert got["lineKept"] == 3 and got["selectedKept"] == {"A": False, "B": True} and got["seriesShared"], got
    assert '"inactiveBorderColor"' not in got["untouched"] and '"inactiveColor":"#30363d"' in got["untouched"]
    # An array legend: the one that hides is inked, the others are the same objects (a hidden legend included).
    assert [a["inactive"] for a in got["array"]] == [DARK_INACTIVE, None, None], got["array"]
    assert got["arraySame"] == [True, True], got
    # An ink handed in (the export's print ink) is the one laid.
    assert {k: got["given"][k] for k in ("inactive", "border", "line")} == {
        "inactive": "#123456", "border": "#123456", "line": "#123456"}


# ------------------------------------------------------------ the drawer line --


def test_the_drawer_names_only_what_the_legend_on_show_lists(result):
    got = result["hiddenNames"]
    # In the legend's order; a remembered name the legend does not list (Z) and a name shown (C) are not named.
    assert got["listed"] == ["A", "B"], got
    # Across an array legend, once each; a hidden legend names nothing.
    assert got["array"] == ["A", "R"], got
    # A legend without `data`: the names its painted `selected` hides.
    assert got["derived"] == ["A"], got
    assert got["none"] == [[], [], [], []], got
    # The paint steps' panel: A and B switched off by the inverse.
    assert got["panel"] == ["A", "B"], got


def test_the_drawer_line_says_the_reader_hid_them_and_how_to_bring_them_back(result):
    got = result["hiddenLine"]
    assert got["none"] == [None, None, None]
    assert got["one"] == ("Hidden on the legend by the reader: A. Click its entry to show it again; "
                          "an export leaves it out.")
    assert got["two"] == ("Hidden on the legend by the reader: A; B · fit. Click an entry to show it again; "
                          "an export leaves them out.")


def test_with_hidden_legend_puts_the_line_first_in_marks_and_legend_and_adds_no_hazard(result):
    got = result["withHidden"]
    line = got["line"]
    assert got["legend"]["sections"] == [["Selection", ["s"]], ["Marks and legend", [line, "m"]]], got["legend"]
    # A drawer without the section gains it in its standard place: before Reading the density axis.
    assert got["density"]["sections"] == [["Selection", ["s"]], ["Disclosures", ["d"]], ["Marks and legend", [line]],
                                          ["Reading the density axis", ["r"]]], got["density"]
    assert got["plain"]["sections"] == [["What is drawn", ["w"]], ["Marks and legend", [line]]], got["plain"]
    # The reader's own choice: never a hazard.
    assert got["legend"]["hazards"] == [] and got["density"]["hazards"] == ["h"]
    # Nothing hidden (or hidden but not listed), no panel, no notes: the notes themselves; the input never changes.
    assert got["same"] == [True, True, True, True] and got["unchanged"], got


# ------------------------------------------------------------------ the export --


def test_the_export_leaves_out_what_the_legend_hides(result):
    got = result["export"]
    ink = result["printInk"]
    # The panel's memory at the end of the paint steps: A and B both switched off by the inverse.
    assert got["hidden"]["charts"] == 1 and got["hidden"]["selected"] == [{"A": False, "B": False}], got
    assert got["hidden"]["screenBack"], got
    # Its legend greys the hidden entries, text, swatch and swatch line, in the print's inactive ink.
    assert got["hidden"]["inks"] == [[ink["ink"], ink["ink"]]], (got["hidden"], ink)
    assert got["hidden"]["lines"] == [ink["ink"]], got["hidden"]
    # A panel without a memory, and one whose memory is empty, export the option as built; one whose memory hides
    # nothing keeps the legend's own inks.
    assert got["noMemory"]["selected"] == [None] and got["noMemory"]["inks"] == [[None, None]], got
    assert got["nothingHidden"]["selected"] == [None], got
    assert got["allShown"]["selected"] == [{"A": True}], got
    assert got["allShown"]["inks"] == [[ink["border"], None]], (got["allShown"], ink)
    assert got["allShown"]["lines"] == [None], got["allShown"]


def test_a_hidden_entry_is_printed_lighter_than_the_entries_on_show_and_still_legible(result):
    """ECharts draws a hidden entry in `inactiveColor`, which `chartLegend` takes from THEME.border, and the print
    border (#111827) is darker than the print muted ink of the entries on show (#374151): the hidden entry would
    read as the emphasised one. The export's grey is the lightest tint of the muted ink at the 4.5:1 text floor."""
    ink = result["printInk"]
    assert ink["inkOnCard"] >= 4.5, ink
    assert ink["inkOnCard"] < 5, "the faintest legible tint, so it reads as off"
    assert ink["inkOnCard"] < ink["mutedOnCard"], ink
    assert ink["ink"].lower() == PRINT_INACTIVE, ink
    # The screen's rule, taken under the print tokens: one derivation for the three cards.
    assert ink["screenRule"] == ink["ink"], ink


# ------------------------------------------------------- Page 1's energy panel --


def _sets(record, key):
    """The energy chart's calls of one step: 'clear', or (notMerge, series count, [legend: entries, selected, inks])."""
    out = []
    for s in record[key]:
        if s["kind"] != "setOption":
            out.append(s["kind"])
            continue
        out.append((s["notMerge"], s["series"], [(len(lg["data"]), lg["selected"], lg["inactive"], lg["border"], lg["line"])
                                                  for lg in s["legends"]]))
    return out


def test_the_energy_panel_listens_to_every_legend_event_once(result):
    got = result["energy"]
    assert got["handlers"] == {event: 1 for event in result["events"]}, got["handlers"]
    # The page is told of each event, with the panel.
    assert got["told"] == [True, True], got["told"]
    # The first entry of the recorded two-shower response: a thin slice's fit, of shower A.
    assert got["entry"].startswith("E_A · ") and got["entry"].endswith("fit (N=8)"), got["entry"]
    assert got["reference"].startswith("[Ref] "), got["reference"]


def test_the_energy_panel_keeps_the_legend_clears_while_hiding_and_inks_the_hidden_entry(result):
    """Page 1's energy card was not a ChartPanel and forgot the legend on every repaint (bug 2). It now keeps the
    memory, clears the chart while anything is hidden (bug 3's guard) and draws a hidden entry in the legible ink;
    its two legends (the series, the references) each take only the names they list."""
    got = result["energy"]
    entry = got["entry"]
    assert got["memory"] == {entry: False}, got["memory"]
    border = "#30363d"
    # The first paint: nothing hidden, no clear, the builder's inks on both legends.
    assert _sets(got, "fresh") == [(True, 29, [(14, None, border, None, None), (2, None, border, None, None)])]
    # The click merges the ink into the series legend alone (index 0), not a repaint.
    assert _sets(got, "click") == [(False, 0, [(0, None, DARK_INACTIVE, DARK_INACTIVE, DARK_INACTIVE),
                                              (0, None, None, None, None)])]
    hidden = (DARK_INACTIVE, DARK_INACTIVE, DARK_INACTIVE)
    # Every repaint after it clears first and lays the memory and the ink over the series legend.
    assert _sets(got, "repaint") == ["clear", (True, 29, [(14, {entry: False}, *hidden), (2, None, border, None, None)])]
    # Shower A alone draws fewer series and fewer entries; the entry is still listed, and still off.
    assert _sets(got, "showerA") == ["clear", (True, 15, [(7, {entry: False}, *hidden), (1, None, border, None, None)])]
    assert _sets(got, "both") == ["clear", (True, 29, [(14, {entry: False}, *hidden), (2, None, border, None, None)])]
    # A reference switched off: its own legend (index 1) takes the ink; the series legend has it already.
    assert _sets(got, "referenceClick") == [(False, 0, [(0, None, None, None, None), (0, None, *hidden)])]
    # Everything back on: the next paint lays no ink and no clear.
    after = _sets(got, "afterAll")
    assert len(after) == 1 and after[0][0] is True and after[0][1] == 29, after
    assert [lg[2:] for lg in after[0][2]] == [(border, None, None), (border, None, None)], after
    assert all(set(lg[1].values()) == {True} for lg in after[0][2]), after
    # The panel's clear keeps the memory and forgets the legend on show.
    assert got["cleared"]["live"] is None and got["cleared"]["names"] == [], got["cleared"]
    assert got["cleared"]["memory"][entry] is True, got["cleared"]


def test_the_energy_drawer_names_the_hidden_series_in_a_marks_and_legend_section(result):
    got = result["energy"]
    names = [got["entry"], got["reference"]]
    assert got["hiddenNames"] == names, got["hiddenNames"]
    # energyNotes has no Marks and legend section; the line makes one, before Reading the density axis.
    assert got["builderNotes"] == ["What is drawn", "Disclosures", "Reading the density axis"], got["builderNotes"]
    headings = [heading for heading, _ in got["notes"]]
    assert headings == ["What is drawn", "Disclosures", "Marks and legend", "Reading the density axis"], headings
    assert dict(got["notes"])["Marks and legend"] == [
        f"Hidden on the legend by the reader: {names[0]}; {names[1]}. Click an entry to show it again; "
        "an export leaves them out."]
    # All back on: nothing named, the notes are the builder's.
    assert got["allBack"] == {"names": [], "same": True}, got["allBack"]


def test_the_energy_export_leaves_out_what_the_legend_hides(result):
    """figure.js's energy branch reads `legendSelected` too: each printed legend marks its own hidden entry off, in
    the print's inactive ink (text, swatch, swatch line), and the screen theme is back after."""
    got = result["energy"]["export"]
    entry, reference = result["energy"]["entry"], result["energy"]["reference"]
    assert got["screenBack"], got
    assert len(got["printed"]) == 1, got
    series, references = got["printed"][0]
    assert series["selected"] == {entry: False} and references["selected"] == {reference: False}, got
    for legend in (series, references):
        assert (legend["inactive"], legend["border"], legend["line"]) == (PRINT_INACTIVE,) * 3, legend
