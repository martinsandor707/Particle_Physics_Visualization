"""The screen draws what its export would: a legend click takes every mark of an entry along (legend-sliders).

Martin's request of 2026-11-17 (the res-emax report's first open item): on screen a legend click hid a
series but not its companions (intervals, carets, bands, the resolution card's note band and end labels),
which an export already left out. chart_panel.js now keeps one legend context, `hiddenEntries()`, that every
builder reads; a paint sets it for the names the reader switched off (`screenBuild`, `withScreenHidden`), an
export for the names it leaves out (`setExportHidden`), and a legend event repaints the panel at the next
frame. Only an export changes the legend itself: on screen the entry stays, greyed, and a builder that left
out every series of it is given one back as its legend carrier, because ECharts draws an entry only for a
name some series carries.

Pinned here, executed under Node:

* the context: `withScreenHidden` sets the names and restores whatever was in force (an export's context
  included, and on a throw); on screen `chartLegend`, `legendShown`, `legendTop` and `legendAlias` are the
  identity;
* `listedNames` and `screenHiddenNames`: a remembered name the legend on show does not list is not hidden;
* `screenBuild`: one build with nothing switched off; with a listed name off, a second build under the
  context, a legend carrier for a name no series carries any more (its clashing `id` dropped), and the first
  build kept as `plain`;
* the repaint: a legend event repaints once per animation frame however many events land, clears first,
  keeps a scroll legend's page, and does nothing for a panel without a picture;
* the energy card's notices never depend on the legend;
* review R2-7 on the catalogue card: a left-out frame takes its rows, its label and its height with it, in
  an export and on screen alike (the card resizes after the click), while its axis never moves; in Compare
  all a species group keeps its label on its middle kept row.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import JS, NODE, PAYLOADS, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));

/* ---- a fake DOM, a fake ECharts that records its calls, and a frame queue ---------------------- */
const makeElement = (width, height) => ({
  clientWidth: width,
  // A set style height is the element's height, as a browser lays it out.
  get clientHeight() { const h = Number.parseFloat(this.style.height); return Number.isFinite(h) ? h : height; },
  style: {}, classList: { toggle() {} }, closest: () => null, replaceChildren() {},
});
const charts = [];
let scrollIndex = 0;
globalThis.echarts = {
  init: (dom) => {
    const chart = {
      dom, calls: [], handlers: {},
      getWidth: () => dom.clientWidth, getHeight: () => dom.clientHeight,
      getDom: () => dom, getZr: () => ({ on() {}, off() {} }), dispatchAction() {},
      on(type, fn) { (this.handlers[type] ??= []).push(fn); },
      resize() { this.calls.push(['resize', dom.clientHeight]); },
      clear() { this.calls.push(['clear']); },
      setOption(option, flags) { this.calls.push(['setOption', option, flags ?? null]); },
      // ECharts keeps a scroll legend's page in the legend model (`legendScroll`).
      getModel: () => ({ getComponent: (type, i) => (type === 'legend' && i === 0
        ? { get: (key) => (key === 'scrollDataIndex' ? scrollIndex : undefined) } : null) }),
      dispose() {},
    };
    charts.push(chart);
    return chart;
  },
};
const fakeNode = () => ({ style: {}, click() {}, remove() {}, appendChild() {}, getContext: () => null });
const element = makeElement(760, 380);
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid', hash: '' } };
globalThis.document = { createElement: fakeNode, body: { appendChild() {} }, getElementById: () => element };
const frames = [];
globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
const flush = () => { while (frames.length) frames.shift()(); };
const fire = (chart, type, event) => (chart.handlers[type] ?? []).forEach((fn) => fn({ type, ...event }));

const cp = await imp('panels/chart_panel.js');
const out = {};

/* ---- the context ------------------------------------------------------------------------------ */
{
  const c = { initial: cp.hiddenEntries() };
  let inside = null;
  const r = cp.withScreenHidden(['A', null, 'B'], () => {
    inside = { names: [...cp.hiddenEntries()], exportContext: cp.isExportContext() };
    return 42;
  });
  c.screen = { r, inside, after: cp.hiddenEntries() };
  c.empty = cp.withScreenHidden([], () => cp.hiddenEntries());
  cp.setExportHidden(['X']);
  const nested = cp.withScreenHidden(['A'], () => ({ names: [...cp.hiddenEntries()], exportContext: cp.isExportContext() }));
  c.nested = { nested, after: [...cp.hiddenEntries()], afterExport: cp.isExportContext() };
  cp.setExportHidden(null);
  try { cp.withScreenHidden(['A'], () => { throw new Error('a builder failed'); }); } catch (e) { /* restored */ }
  c.afterThrow = { names: cp.hiddenEntries(), exportContext: cp.isExportContext() };
  // On screen the legend helpers keep every entry: the legend greys a hidden one, it never drops it.
  const entries = ['A', { name: 'B', icon: 'circle' }, 'C'];
  const long = [1, 2, 3, 4, 5, 6].map((i) => `Shower ${i} · Calibrated deposit c·E_dep — linear-sum benchmark`);
  const snap = () => JSON.stringify({ legend: cp.chartLegend(entries), wrapped: cp.wrappedLegend(long, { left: 10, right: 10 }),
    top: cp.legendTop(long, 300, { wrap: true }), screenTop: cp.legendTop(long, 300) });
  const before = snap();
  c.identity = cp.withScreenHidden(['A', 'B', ...long], () => ({ same: snap() === before, shownSame: cp.legendShown(entries) === entries }));
  c.alias = cp.withScreenHidden(['wide name'], () => { cp.legendAlias(['wide name', 'short'], 'short'); return [...cp.hiddenEntries()]; });
  out.context = c;
}

/* ---- listedNames, screenHiddenNames ------------------------------------------------------------ */
{
  const option = {
    legend: [{ data: ['A', { name: 'B' }] }, { show: false, data: ['C'] }, {}],
    series: [{ name: 'A' }, { name: 'D' }, { name: '' }, {}],
  };
  out.listed = [...cp.listedNames(option)].sort();
  out.screenHidden = cp.screenHiddenNames({ legendSelected: { A: false, C: false, D: false, Z: false, B: true } }, option);
  out.screenHiddenNone = cp.screenHiddenNames({ legendSelected: {} }, option);
}

/* ---- screenBuild ------------------------------------------------------------------------------- */
{
  const seen = [];
  const build = () => {
    const h = cp.hiddenEntries();
    seen.push({ names: h ? [...h] : null, exportContext: cp.isExportContext() });
    const series = [];
    if (!h?.has('A')) series.push({ name: 'A', id: 'shared', type: 'line', data: [1] }, { name: 'A · 95% interval', type: 'custom', data: [1] });
    series.push({ name: 'B', id: 'shared', type: 'line', data: [2] });
    return { option: { legend: { data: ['A', 'B'] }, series }, made: h ? 'context' : 'plain' };
  };
  const run = (memory) => {
    seen.length = 0;
    const r = cp.screenBuild({ legendSelected: memory }, build);
    return { builds: seen.map((s) => ({ ...s })), series: r.option.series.map((s) => [s.name, s.id ?? null]),
      made: r.made, plain: r.plain?.made ?? null, hidden: r.hidden ?? null, context: cp.hiddenEntries() };
  };
  out.build = { none: run({}), on: run({ A: true }), unlisted: run({ Z: false }), off: run({ A: false }) };
}

/* ---- the repaint a legend event asks for ------------------------------------------------------- */
{
  class Tiny extends cp.ChartPanel {
    buildOption() {
      const h = cp.hiddenEntries();
      this.builds.push(h ? [...h] : null);
      const series = [{ name: 'A', type: 'line', data: [1] }];
      if (!h?.has('A')) series.push({ name: 'A (clipped)', type: 'custom', data: [] });
      series.push({ name: 'B', type: 'line', data: [2] });
      return { option: { ...cp.baseOption(), legend: cp.chartLegend(['A', 'B']), series } };
    }
  }
  const el = makeElement(600, 400);
  const panel = new Tiny(el);
  panel.builds = [];
  const told = [];
  panel.onLegendChange = () => told.push(panel.legendRepainting);
  panel.render({ n: 1 }, {});
  const chart = charts[charts.length - 1];
  const names = (option) => (option.series ?? []).map((s) => s.name);
  const slice = (from) => chart.calls.slice(from).map(([kind, option, flags]) => (kind === 'setOption'
    ? { kind, notMerge: Boolean(flags?.notMerge), series: option.series ? names(option) : null,
      page: option.legend?.scrollDataIndex ?? null, selected: option.legend?.selected ?? null } : { kind }));
  const r = { first: slice(0), buildsFirst: [...panel.builds] };
  scrollIndex = 3;
  let from = chart.calls.length;
  panel.builds.length = 0;
  fire(chart, 'legendselectchanged', { name: 'A', selected: { A: false, B: true } });
  fire(chart, 'legendselectchanged', { name: 'B', selected: { A: false, B: false } });
  fire(chart, 'legendselectchanged', { name: 'B', selected: { A: false, B: true } });
  r.beforeFrame = { calls: slice(from), frames: frames.length, told: [...told] };
  from = chart.calls.length;
  flush();
  r.frame = { calls: slice(from), builds: [...panel.builds], repainting: panel.legendRepainting, screenHidden: panel.screenHidden };
  // Back on: the repaint draws the companion again, from one build.
  panel.builds.length = 0;
  scrollIndex = 0;
  from = chart.calls.length;
  fire(chart, 'legendselectchanged', { name: 'A', selected: { A: true, B: true } });
  flush();
  r.back = { calls: slice(from), builds: [...panel.builds] };
  // A panel with nothing to draw is not repainted.
  const bare = new Tiny(makeElement(600, 400));
  bare.builds = [];
  bare.ensureChart();
  fire(charts[charts.length - 1], 'legendselectchanged', { name: 'A', selected: { A: false } });
  flush();
  r.bare = { builds: bare.builds.length, calls: charts[charts.length - 1].calls.length };
  out.repaint = r;
}

/* ---- the energy card: the notices never depend on the legend ----------------------------------- */
{
  const energyMod = await imp('panels/energy.js');
  const ep = new energyMod.EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
  const chart = charts[charts.length - 1];
  const payload = load('energy_d_two');
  const opts = { palette: 'viridis', kind: 'pred', shower: 'both' };
  const strip = (notices) => JSON.stringify(notices, (k, v) => (typeof v === 'function' ? 'fn' : v));
  const built = ep.buildOption({ payload, opts, metrics: { width: 760, height: 380 } });
  ep.render(payload, opts);
  const before = strip(ep.lastNotices);
  const entries = ep.liveLegend[0].data.map((d) => d?.name ?? d);
  const events = entries.find((n) => n.endsWith(' (events)'));
  fire(chart, 'legendselectchanged', { name: events, selected: { [events]: false } });
  flush();
  ep.render(payload, opts);
  out.energy = { events, same: strip(ep.lastNotices) === before, plainNotices: Object.keys(built.notices ?? {}).sort(),
    // The click's repaint drew no row for the strip: its events' series is the carrier alone.
    eventsSeries: chart.calls.filter(([k]) => k === 'setOption').at(-1)[1].series.filter((s) => s.name === events).length };
}

/* ---- review R2-7: the catalogue lays its rows out without a left-out frame --------------------- */
{
  const sel = await imp('catalog/select.js');
  const cat = await imp('panels/bench_catalog.js');
  const labelsOf = (option) => option.yAxis.map((a) => a.data.map((d, i) => (a.axisLabel?.formatter ? a.axisLabel.formatter(d, i) : d)));
  const one = sel.catalogPayload('perf-catalog', { species: 'proton', task: 'segmentation' });
  const all = sel.catalogPayload('perf-catalog', { species: 'all', task: 'segmentation' });
  const frame = (p, f) => cat.labelOf(p, 'frame', f);
  const snapshot = (p, width) => {
    const model = cat.benchCatalogModel(p, {});
    const option = cat.benchCatalogOption(p, {}, { width, height: cat.plotHeight(p, {}, width) }).option;
    return { keys: model.keys, height: cat.plotHeight(p, {}, width), labels: labelsOf(option)[0],
      axes: model.facets.map((f) => f.axis), yData: option.yAxis.map((a) => a.data) };
  };
  const r = { frames: ['absolute', 'trans', 'local'].map((f) => frame(one, f)) };
  r.one = snapshot(one, 760);
  cp.setExportHidden([frame(one, 'local')]);
  r.oneExport = snapshot(one, 760);
  cp.setExportHidden(null);
  r.oneScreen = cp.withScreenHidden([frame(one, 'local')], () => snapshot(one, 760));
  r.all = snapshot(all, 760);
  r.species = all.species.map((s) => cat.labelOf(all, 'species', s));
  cp.setExportHidden([frame(all, 'trans')]);
  r.allExport = snapshot(all, 760);
  cp.setExportHidden([frame(all, 'trans'), frame(all, 'absolute'), frame(all, 'local')]);
  r.noneLeft = snapshot(all, 760);
  cp.setExportHidden(null);
  r.restored = JSON.stringify(snapshot(one, 760)) === JSON.stringify(r.one);

  // On screen: a click that switches a frame off resizes the card to the rows it draws, and back.
  const el = makeElement(760, 400);
  const panel = new cat.BenchCatalogPanel(el);
  panel.render(one, {});
  const chart = charts[charts.length - 1];
  const h0 = el.clientHeight;
  fire(chart, 'legendselectchanged', { name: frame(one, 'local'), selected: { [frame(one, 'local')]: false } });
  flush();
  const h1 = el.clientHeight;
  const last = chart.calls.filter(([k]) => k === 'setOption').at(-1)[1];
  fire(chart, 'legendselectchanged', { name: frame(one, 'local'), selected: { [frame(one, 'local')]: true } });
  flush();
  r.panel = { h0, h1, h2: el.clientHeight, resized: chart.calls.filter(([k]) => k === 'resize').map(([, h]) => h),
    wanted: cp.withScreenHidden([frame(one, 'local')], () => cat.plotHeight(one, {}, 760)),
    rows: last.yAxis[0].data, legend: last.legend.data.map((d) => d?.name ?? d),
    carrier: last.series.filter((s) => s.name === frame(one, 'local')).length };
  out.catalog = r;
}

/* ---- review R-M3: a name chosen by width keeps the reader's choice across a relayout ---------- */
{
  const imps = await imp('panels/xgb_importance.js');
  const payload = load('xgb_importance_momentum');
  const el = makeElement(1100, 400);
  const panel = new imps.XgbImportancePanel(el);
  panel.render(payload, {});
  const chart = charts[charts.length - 1];
  const legendOf = () => (panel.liveLegend?.data ?? []).map((d) => d?.name ?? d);
  const wide = legendOf();
  const model = imps.importanceModel(payload);
  const envelopeWide = imps.envelopeLegend(model, 1100);
  const envelopeNarrow = imps.envelopeLegend(model, 400);
  fire(chart, 'legendselectchanged', { name: envelopeWide, selected: { [envelopeWide]: false } });
  flush();
  const before = { hidden: panel.screenHidden, drawer: cp.legendHiddenNames(panel) };
  // The Details drawer opens and the card narrows: the envelope takes its short name.
  el.clientWidth = 400;
  panel.relayout();
  out.alias = { wide, envelopeWide, envelopeNarrow, before, memory: { ...panel.legendSelected },
    after: { hidden: panel.screenHidden, drawer: cp.legendHiddenNames(panel), legend: legendOf(),
      selected: panel.liveLegend?.selected ?? null } };
  // Switched back on at the narrow width: on under both names.
  fire(chart, 'legendselectchanged', { name: envelopeNarrow, selected: { [envelopeNarrow]: true } });
  flush();
  el.clientWidth = 1100;
  panel.relayout();
  out.alias.back = { memory: { ...panel.legendSelected }, hidden: panel.screenHidden, drawer: cp.legendHiddenNames(panel) };
}

/* ---- review R-N2: an entry a builder starts off leaves its companions out on screen too -------- */
{
  class Default extends cp.ChartPanel {
    buildOption() {
      const h = cp.hiddenEntries();
      const series = [{ name: 'A', type: 'line', data: [1] }];
      if (!h?.has('A')) series.push({ name: 'A (clipped)', type: 'custom', data: [] });
      series.push({ name: 'B', type: 'line', data: [2] });
      return { option: { ...cp.baseOption(), legend: cp.chartLegend(['A', 'B'], { selected: { A: false } }), series } };
    }
  }
  const panel = new Default(makeElement(600, 400));
  panel.render({ n: 1 }, {});
  const chart = charts[charts.length - 1];
  const lastSeries = () => chart.calls.filter(([k]) => k === 'setOption').at(-1)[1].series.map((x) => x.name);
  const first = { hidden: panel.screenHidden, series: lastSeries(), exportOff: cp.legendOffNames(panel) };
  fire(chart, 'legendselectchanged', { name: 'A', selected: { A: true, B: true } });
  flush();
  out.defaults = { first, on: { hidden: panel.screenHidden, series: lastSeries() } };
}

console.log(JSON.stringify(out));
process.exit(0);
"""


@pytest.fixture(scope="module")
def result() -> dict:
    return _run(_SCRIPT, [JS.as_uri(), str(PAYLOADS)])


# ------------------------------------------------------------------------------ the context --


def test_with_screen_hidden_sets_the_names_and_restores_the_context_in_force(result):
    c = result["context"]
    assert c["initial"] is None
    assert c["screen"] == {"r": 42, "inside": {"names": ["A", "B"], "exportContext": False}, "after": None}
    assert c["empty"] is None
    # Inside an export's context: the screen's names, then the export's back.
    assert c["nested"] == {"nested": {"names": ["A"], "exportContext": False}, "after": ["X"], "afterExport": True}
    assert c["afterThrow"] == {"names": None, "exportContext": False}


def test_on_screen_the_legend_helpers_keep_every_entry(result):
    assert result["context"]["identity"] == {"same": True, "shownSame": True}
    # legendAlias adds a name only in an export: a paint lays out at the width the reader clicked at.
    assert result["context"]["alias"] == ["wide name"]


def test_only_a_name_the_legend_on_show_lists_is_hidden(result):
    # A legend without data lists every named series; a hidden legend lists none.
    assert result["listed"] == ["A", "B", "D"]
    assert result["screenHidden"] == ["A", "D"]
    assert result["screenHiddenNone"] == []


# ------------------------------------------------------------------------------- screenBuild --


def test_with_nothing_switched_off_a_paint_builds_once_with_no_context(result):
    for case in ("none", "on"):
        got = result["build"][case]
        assert got["builds"] == [{"names": None, "exportContext": False}], case
        assert got["made"] == "plain" and got["plain"] is None and got["hidden"] is None, case


def test_a_remembered_name_the_legend_does_not_list_hides_nothing(result):
    got = result["build"]["unlisted"]
    assert got["builds"] == [{"names": None, "exportContext": False}]
    assert got["made"] == "plain" and got["hidden"] is None
    assert [n for n, _ in got["series"]] == ["A", "A · 95% interval", "B"]


def test_a_switched_off_entry_is_built_without_its_marks_and_carried_on_the_legend(result):
    got = result["build"]["off"]
    # The plain build first (what the legend lists), then the screen's context, never an export's.
    assert got["builds"] == [{"names": None, "exportContext": False}, {"names": ["A"], "exportContext": False}]
    assert got["made"] == "context" and got["plain"] == "plain" and got["hidden"] == ["A"]
    # The companion is gone; A's first series comes back as the legend carrier, its clashing id dropped.
    assert got["series"] == [["B", "shared"], ["A", None]]
    assert got["context"] is None


# ------------------------------------------------------------------------------- the repaint --


def test_a_legend_event_repaints_once_per_frame_clearing_first_and_keeping_the_page(result):
    r = result["repaint"]
    assert r["first"] == [{"kind": "setOption", "notMerge": True, "series": ["A", "A (clipped)", "B"],
                           "page": None, "selected": None}]
    # Three events in one frame: the inks merge at once, one repaint is asked for, and the page is told each time.
    assert r["beforeFrame"]["frames"] == 1, r["beforeFrame"]
    assert all(c["kind"] == "setOption" and not c["notMerge"] and c["series"] is None for c in r["beforeFrame"]["calls"])
    assert r["beforeFrame"]["told"] == [False, False, False]
    # The frame: two builds (plain, then under the context), a clear, then the option at the legend's page.
    assert r["frame"]["builds"] == [None, ["A"]]
    assert r["frame"]["calls"] == [{"kind": "clear"},
                                   {"kind": "setOption", "notMerge": True, "series": ["A", "B"], "page": 3,
                                    "selected": {"A": False, "B": True}}]
    assert r["frame"]["repainting"] is False and r["frame"]["screenHidden"] == ["A"]


def test_switched_back_on_the_companion_returns_with_its_entry(result):
    r = result["repaint"]["back"]
    assert r["builds"] == [None]
    assert r["calls"][-1]["series"] == ["A", "A (clipped)", "B"]
    assert r["calls"][-1]["page"] is None
    assert {"kind": "clear"} in r["calls"]


def test_a_panel_with_nothing_to_draw_is_not_repainted(result):
    assert result["repaint"]["bare"] == {"builds": 0, "calls": 0}


def test_the_energy_cards_notices_never_depend_on_the_legend(result):
    got = result["energy"]
    assert got["events"].endswith(" (events)")
    assert got["same"] is True
    assert got["eventsSeries"] == 1, "the strip's events are drawn by nothing but their legend carrier"


# ------------------------------------------------------------------------ review R2-7, catalogue --


def test_a_left_out_frame_takes_its_rows_label_and_height_in_an_export(result):
    r = result["catalog"]
    absolute, trans, local = r["frames"]
    assert r["one"]["keys"] == ["proton:absolute", "proton:trans", "proton:local"]
    assert r["oneExport"]["keys"] == ["proton:absolute", "proton:trans"]
    assert all(data == ["proton:absolute", "proton:trans"] for data in r["oneExport"]["yData"])
    # No empty, unlabelled slot: every row left is labelled with its frame.
    assert r["oneExport"]["labels"] == [absolute, trans]
    assert r["oneExport"]["height"] < r["one"]["height"]
    # The axes never move with the legend.
    assert r["oneExport"]["axes"] == r["one"]["axes"]
    assert r["restored"] is True


def test_the_screen_lays_the_catalogue_out_as_the_export_does(result):
    r = result["catalog"]
    assert r["oneScreen"] == r["oneExport"]


def test_in_compare_all_a_species_keeps_its_label_on_its_middle_kept_row(result):
    r = result["catalog"]
    n = len(r["species"])
    assert n > 1
    # Three frames: the label on the second, as before.
    labels = r["all"]["labels"]
    assert [l for l in labels if l] == r["species"]
    assert all(labels[4 * i + 1] == r["species"][i] for i in range(n)), labels
    # Per-shower translated left out: two rows a group, the label on the first, one spacer between groups.
    keys = r["allExport"]["keys"]
    assert len(keys) == 2 * n + (n - 1)
    assert not any(k.endswith(":trans") for k in keys)
    labels = r["allExport"]["labels"]
    assert all(labels[3 * i] == r["species"][i] for i in range(n)), labels
    assert r["allExport"]["axes"] == r["all"]["axes"]
    # Every frame left out: no row and no spacer.
    assert r["noneLeft"]["keys"] == []


def test_a_click_resizes_the_catalogue_card_to_the_rows_it_draws(result):
    p = result["catalog"]["panel"]
    assert p["h1"] < p["h0"], p
    assert p["h1"] == p["wanted"], p
    assert p["h2"] == p["h0"], p
    assert p["rows"] == ["proton:absolute", "proton:trans"]
    # The legend keeps the frame, carried by one hidden series.
    assert result["catalog"]["frames"][2] in p["legend"]
    assert p["carrier"] == 1


# ------------------------------------------------------------- review fixes R-M3 and R-N2 --


def test_a_click_under_a_width_chosen_name_survives_the_relayout_that_renames_it(result):
    """Review R-M3: the importance envelope is named in full on a wide card and in short on a narrow one. Switched
    off at 1100 px, it stays off when the card narrows to 400 px (the Details drawer opening at a 1024 px window),
    and the drawer keeps naming it; switched back on under its short name, it is on under both."""
    a = result["alias"]
    assert a["envelopeWide"] != a["envelopeNarrow"], a
    assert a["envelopeWide"] in a["wide"]
    assert a["before"] == {"hidden": [a["envelopeWide"]], "drawer": [a["envelopeWide"]]}
    assert a["memory"][a["envelopeWide"]] is False and a["memory"][a["envelopeNarrow"]] is False
    assert a["envelopeNarrow"] in a["after"]["legend"]
    assert a["after"]["hidden"] == [a["envelopeNarrow"]] and a["after"]["drawer"] == [a["envelopeNarrow"]]
    assert a["after"]["selected"].get(a["envelopeNarrow"]) is False
    assert a["back"]["memory"][a["envelopeWide"]] is True and a["back"]["memory"][a["envelopeNarrow"]] is True
    assert a["back"]["hidden"] == [] and a["back"]["drawer"] == []


def test_an_entry_a_builder_starts_off_takes_its_companions_along_on_screen(result):
    """Review R-N2: an export leaves out an entry a builder starts off (`selected: false`); the screen now does too,
    keeping the entry and its carrier, until the reader switches it on."""
    d = result["defaults"]
    assert d["first"]["hidden"] == ["A"] and d["first"]["exportOff"] == ["A"]
    # The builder keeps A's own series (the legend filter hides it), so no carrier is needed; its companion goes.
    assert d["first"]["series"] == ["A", "B"]
    assert d["on"]["hidden"] == [] and d["on"]["series"] == ["A", "A (clipped)", "B"]
