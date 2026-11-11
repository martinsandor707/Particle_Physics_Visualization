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
  at zero size;
* the export (``export/figure.js``): the print option carries the memory; a
  legend that hides an entry greys it in the lightest tint of the print muted
  ink that clears 4.5:1 on white (#6f7681), where ECharts would have drawn it
  in the print border, the near-black #111827, darker than the entries on show;
  a panel without a memory, or with one that hides nothing, keeps the legend's
  own inks; the screen theme is back after.

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
const element = { clientWidth: 600, clientHeight: 400, style: {}, classList: { toggle() {} }, closest: () => null };
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
const steps = [];
let live = null;
const step = (what, fn) => {
  const from = live ? live.calls.length : 0;
  fn();
  live = live ?? charts.find((c) => c.renderer === 'canvas') ?? null;
  const calls = live ? live.calls.slice(from) : [];
  steps.push({ what, memory: { ...panel.legendSelected },
    calls: calls.map(([kind, option, flags]) => (kind === 'setOption'
      ? [kind, option.legend?.selected ?? null, Boolean(flags?.notMerge)] : [kind])) });
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

/* ---- the export ------------------------------------------------------------ */
const exportOf = (p) => {
  const n = charts.length;
  fig.exportPanel(p, { panelId: 'tiny', format: 'svg', widthMm: 85, state: null });
  const made = charts.slice(n).filter((c) => c.renderer === 'svg');
  const set = made.flatMap((c) => c.calls.filter(([kind]) => kind === 'setOption'));
  return { charts: made.length, selected: set.map(([, option]) => option.legend?.selected ?? null),
    inks: set.map(([, option]) => [option.legend?.inactiveColor ?? null, option.legend?.inactiveBorderColor ?? null]),
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
    border: THEME.border };
  Object.assign(THEME, saved);
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
    assert steps["first render"]["calls"] == set_only(None)
    assert steps["a click switches A off"] == {"what": "a click switches A off", "memory": {"A": False}, "calls": []}
    assert steps["a repaint (theme, control)"]["calls"] == cleared({"A": False})
    assert steps["a relayout at a new width"]["calls"] == cleared({"A": False})
    assert steps["a new payload"]["calls"] == cleared({"A": False})
    # A card held at zero size paints nothing; shown again it paints with the memory.
    assert steps["held at zero size"]["calls"] == []
    assert steps["shown again"]["calls"] == cleared({"A": False})
    # Switched back on: nothing hidden, no clear; the remembered `true` is laid over the option.
    assert steps["a click switches A on"]["memory"] == {"A": True}
    assert steps["a repaint with nothing hidden"]["calls"] == set_only({"A": True})
    assert steps["a scripted unselect of B"]["memory"] == {"A": True, "B": False}
    assert steps["a repaint with B hidden"]["calls"] == cleared({"A": True, "B": False})
    assert steps["select all"]["memory"] == {"A": True, "B": True}
    assert steps["a repaint after select all"]["calls"] == set_only({"A": True, "B": True})
    assert steps["inverse"]["memory"] == {"A": False, "B": False}
    assert steps["a repaint after inverse"]["calls"] == cleared({"A": False, "B": False})


def test_the_memory_survives_the_panels_clear(result):
    step = _steps(result)["the panel's clear"]
    assert step["calls"] == [["clear"]], step
    assert step["memory"] == {"A": False}, step


# ------------------------------------------------------------------ the export --


def test_the_export_leaves_out_what_the_legend_hides(result):
    got = result["export"]
    ink = result["printInk"]
    # The panel's memory at the end of the paint steps: A and B both switched off by the inverse.
    assert got["hidden"]["charts"] == 1 and got["hidden"]["selected"] == [{"A": False, "B": False}], got
    assert got["hidden"]["screenBack"], got
    # Its legend greys the hidden entries, text and swatch, in the print's inactive ink.
    assert got["hidden"]["inks"] == [[ink["ink"], ink["ink"]]], (got["hidden"], ink)
    # A panel without a memory, and one whose memory is empty, export the option as built; one whose memory hides
    # nothing keeps the legend's own inks.
    assert got["noMemory"]["selected"] == [None] and got["noMemory"]["inks"] == [[None, None]], got
    assert got["nothingHidden"]["selected"] == [None], got
    assert got["allShown"]["selected"] == [{"A": True}], got
    assert got["allShown"]["inks"] == [[ink["border"], None]], (got["allShown"], ink)


def test_a_hidden_entry_is_printed_lighter_than_the_entries_on_show_and_still_legible(result):
    """ECharts draws a hidden entry in `inactiveColor`, which `chartLegend` takes from THEME.border, and the print
    border (#111827) is darker than the print muted ink of the entries on show (#374151): the hidden entry would
    read as the emphasised one. The export's grey is the lightest tint of the muted ink at the 4.5:1 text floor."""
    ink = result["printInk"]
    assert ink["inkOnCard"] >= 4.5, ink
    assert ink["inkOnCard"] < 5, "the faintest legible tint, so it reads as off"
    assert ink["inkOnCard"] < ink["mutedOnCard"], ink
    assert ink["ink"].lower() == "#6f7681", ink
