"""An export leaves out what the legend switches off, with its entry (res-emax), executed under Node.

Martin's decision of 2026-11-17: every chart export, on both pages, leaves out a
series switched off on the legend together with its legend entry (replacing the
greyed entry of 2026-11-11), lays the legend rows out without it, and writes no
canvas text naming it. export/figure.js sets the export's legend context
(chart_panel.js ``setExportHidden``) inside its synchronous window and lays the
print legend with ``printLegendOption``; each builder leaves out every mark of a
left-out entry, its companions included (``<entry> · dispersion``,
``<entry> (clipped)``, SD bands, intervals, carets, value labels).

Pinned here:

* ``printLegendOption`` (export/figure.js), pure: object and array legends, a
  legend without ``data`` (given the names it would list, minus the left-out
  ones), a ``show: false`` legend, the reader's memory ``true`` over a builder
  default ``false``, every left-out name marked false and unlisted, no ink laid,
  nothing mutated, and with nothing left out the memory's option itself;
* the recipe of brief section 7 for every Page 1 builder (energy.js,
  response.js's three parts, response_grid.js, distribution.js's C4, D4 and
  residual, profile.js) on the recorded payloads, on the screen and under the
  print tokens: built with no context (A), then for each legend entry N under
  ``setExportHidden([N])`` (B): B's legends list no N and one marks it false; no
  series of B belongs to N (named N, or ``N `` / ``N·`` followed by more, unless
  the longer name is an entry in its own right); no canvas text of B (graphic,
  or a custom series' rendered text) names N; B's grid top is never larger than
  A's; and once the context is cleared the builder returns A again, deep-equal;
* the file name tokens of the resolution card: ``emax-<n>`` right after
  ``energy``, ``deposit-off`` after the view block in both views, ``ratio-none``
  from ``meta.reference``.

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
const clone = (o) => JSON.parse(JSON.stringify(o));

/* ---- a fake DOM and ECharts, for the energy panel's constructor -------------- */
const element = { clientWidth: 760, clientHeight: 380, style: {}, classList: { toggle() {} }, closest: () => null,
  replaceChildren() {} };
const fakeChart = () => ({ getWidth: () => 760, getHeight: () => 380, getDom: () => element,
  getZr: () => ({ on() {}, off() {} }), dispatchAction() {}, on() {}, resize() {}, clear() {}, setOption() {},
  dispose() {} });
const fakeNode = () => ({ style: {}, click() {}, remove() {}, appendChild() {}, getContext: () => null });
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid', hash: '' } };
globalThis.document = { createElement: fakeNode, body: { appendChild() {} }, getElementById: () => element };
globalThis.echarts = { init: () => fakeChart() };

const cp = await imp('panels/chart_panel.js');
const fig = await imp('export/figure.js');
const { THEME } = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const energyMod = await imp('panels/energy.js');
const resp = await imp('panels/response.js');
const grid = await imp('panels/response_grid.js');
const dist = await imp('panels/distribution.js');
const prof = await imp('panels/profile.js');
const out = {};

/* ---- printLegendOption, pure ---------------------------------------------------- */
{
  const series = [{ name: 'A' }, { name: 'B' }, { name: 'B' }, { name: 'C' }, { name: '' }, {}];
  const json = (o) => JSON.stringify(o);
  const objectOpt = { legend: { show: true, data: [{ name: 'A', icon: 'circle' }, 'B', 'C'], selected: { C: false } }, series };
  const arrayOpt = { legend: [{ data: ['A', 'B'] }, { data: [{ name: 'C' }] }, { show: false, data: ['B'] }], series };
  const datalessOpt = { legend: { show: true }, series };
  const before = json([objectOpt, arrayOpt, datalessOpt]);
  const pick = (l) => ({ data: (l.data ?? null)?.map((d) => d?.name ?? d) ?? null, selected: l.selected ?? null,
    show: l.show ?? null, ink: [l.inactiveColor ?? null, l.inactiveBorderColor ?? null, l.lineStyle?.inactiveColor ?? null] });
  const o = fig.printLegendOption(objectOpt, { A: true, C: true }, ['B', 'C']);
  const a = fig.printLegendOption(arrayOpt, { B: true }, ['B']);
  const d = fig.printLegendOption(datalessOpt, {}, ['B']);
  const all = fig.printLegendOption({ legend: { show: true, data: ['A'] }, series }, null, ['A']);
  // The reader switched a builder's default back on: it is not among the left-out names, so it stays on.
  const memoryOn = fig.printLegendOption({ legend: { data: ['A', 'B'], selected: { B: false } }, series }, { B: true }, []);
  const noLegend = { series };
  out.print = {
    object: pick(o.legend), objectKeepsIcon: o.legend.data[0]?.icon ?? null,
    array: a.legend.map(pick), dataless: pick(d.legend), all: pick(all.legend), memoryOn: pick(memoryOn.legend),
    seriesShared: o.series === series,
    same: [fig.printLegendOption(objectOpt, {}, []) === objectOpt, fig.printLegendOption(objectOpt, null, null) === objectOpt,
      fig.printLegendOption(noLegend, { A: false }, ['A']) === noLegend],
    untouched: json([objectOpt, arrayOpt, datalessOpt]) === before,
  };
}

/* ---- the section 7 recipe on every Page 1 builder ---------------------------- */
const api = { coord: (p) => [Number(p[0]), Number(p[1])], value: () => 0, size: () => [1, 1], style: (s) => s ?? {} };
const coordSys = { x: 0, y: 0, width: 400, height: 300 };
const texts = (el, acc) => {
  if (!el || typeof el !== 'object') return acc;
  if (typeof el.style?.text === 'string') acc.push(el.style.text);
  for (const c of el.children ?? []) texts(c, acc);
  return acc;
};
const canvasTexts = (option) => {
  const acc = [];
  for (const g of [].concat(option.graphic ?? [])) texts(g, acc);
  for (const s of [].concat(option.series ?? [])) {
    if (typeof s.renderItem !== 'function') continue;
    for (let i = 0; i < (s.data ?? []).length; i += 1) {
      try { texts(s.renderItem({ dataIndex: i, coordSys }, { ...api, value: (k) => [].concat(s.data[i]?.value ?? s.data[i])[k] }), acc); } catch (e) { /* a mark this fake api cannot draw */ }
    }
  }
  return acc;
};
const entryName = (d) => String(d !== null && typeof d === 'object' ? d.name : d);
const legendsOf = (option) => [].concat(option.legend ?? []).filter((l) => l && typeof l === 'object');
const entriesOf = (option) => [...new Set(legendsOf(option).filter((l) => l.show !== false)
  .flatMap((l) => (l.data ?? []).map(entryName)))];
const topOf = (option) => [].concat(option.grid ?? [])[0]?.top ?? null;
const serialise = (option) => JSON.stringify(option, (k, v) => (typeof v === 'function' ? `fn:${v.toString()}` : v));

/** The entry a series name belongs to: the longest entry it equals, or extends with ' ' or '·'. */
const ownerOf = (name, entries) => {
  let best = null;
  for (const e of entries) {
    const hit = name === e || name.startsWith(`${e} `) || name.startsWith(`${e}·`);
    if (hit && (!best || e.length > best.length)) best = e;
  }
  return best;
};

const ep = new energyMod.EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
const CASES = [
  ['energy/pred', () => ep.buildOption({ payload: load('energy_d_two'), opts: { palette: 'viridis', kind: 'pred', shower: 'both' }, metrics: { width: 760, height: 380 } }).option],
  ['energy/true', () => ep.buildOption({ payload: load('energy_d_two'), opts: { palette: 'viridis', kind: 'true', shower: 'both' }, metrics: { width: 321, height: 300 } }).option],
  ['energy/showerA', () => ep.buildOption({ payload: load('energy_d_two'), opts: { palette: 'viridis', kind: 'pred', shower: 'a' }, metrics: { width: 640, height: 340 } }).option],
];
for (const name of ['response_two', 'response_single_hits', 'response_single_events']) {
  for (const mode of ['b1', 'b2', 'resolution']) {
    CASES.push([`response/${name}/${mode}`, () => resp.responseOption(load(name), { mode }, { width: 640, height: 340 })]);
  }
}
CASES.push(['response/response_two/ratio', () => resp.responseOption(load('response_two'), { mode: 'resolution', quantity: 'response_ratio' }, { width: 321, height: 300 })]);
{
  // B1 below the histogram floor (as tests/test_js_physics_panels.py builds it): a strip row with every companion.
  const strip = clone(load('response_two'));
  for (const s of strip.b1.series) {
    s.draw = 'strip'; s.histogram = null; s.n = 6;
    s.strip = { values: [0.2, 0.5, 0.9, 1.1, 1.7, 9.6], n_shown: 6, truncated: false };
    s.fit = { ...s.fit, n: 6, sigma: 0.9, sigma_error: 0.2915, sigma_ci95: [0.5618, 2.2074], sigma_bias_factor: 0.9515, estimator: 'moments' };
  }
  CASES.push(['response/strip/b1', () => resp.responseOption(strip, { mode: 'b1' }, { width: 640, height: 340 })]);
}
for (const name of ['b3_two_truth', 'b3_single_bins', 'b3_events_bins', 'b3_single_notebook']) {
  CASES.push([`grid/${name}`, () => grid.responseGridOption(load(name), {}, { width: 760, height: null })]);
  CASES.push([`grid/${name}/fixed`, () => grid.responseGridOption(load(name), {}, { width: 600, height: 380 })]);
}
for (const name of ['distribution_two_p', 'distribution_single_u', 'distribution_events_p', 'distribution_single_phi']) {
  CASES.push([`distribution/${name}/linear`, () => dist.distributionOption(load(name), { palette: 'viridis', yScale: 'linear' }, { width: 640, height: 340 })]);
  CASES.push([`distribution/${name}/log`, () => dist.distributionOption(load(name), { palette: 'viridis', yScale: 'log' }, { width: 321, height: 300 })]);
}
for (const name of ['features_single_hist', 'features_single_hist_phi']) {
  CASES.push([`d4/${name}`, () => dist.featureHistOption(load(name), { palette: 'viridis' }, { width: 640, height: 340 })]);
  CASES.push([`d4/${name}/count`, () => dist.featureHistOption(load(name), { palette: 'viridis', quantity: 'count' }, { width: 640, height: 340 })]);
}
for (const name of ['pred_density_two_energy', 'pred_density_two_angle', 'pred_density_xgb_energy', 'pred_density_xgb_phi']) {
  CASES.push([`residual/${name}`, () => dist.residualOption(load(name), {}, { width: 640, height: 340 })]);
}
for (const [name, axis] of [['profiles_two_w', 'depth'], ['profiles_two_w', 'r'], ['profiles_single_w', 'depth'], ['profiles_single_native', 'kt']]) {
  CASES.push([`profile/${name}/${axis}`, () => prof.profileOption(load(name), { axis }, { width: 640, height: 360 })]);
}

const runCase = (build) => {
  const a = build();
  const aText = serialise(a);
  const entries = entriesOf(a);
  const checks = [];
  for (const n of entries) {
    cp.setExportHidden([n]);
    let b;
    try { b = build(); } finally { cp.setExportHidden(null); }
    const listed = legendsOf(b).filter((l) => (l.data ?? []).some((d) => entryName(d) === n)).length;
    const markedOff = legendsOf(b).some((l) => l.selected?.[n] === false);
    const owned = [].concat(b.series ?? []).map((s) => String(s?.name ?? '')).filter((s) => ownerOf(s, entries) === n);
    const named = canvasTexts(b).filter((t) => t.includes(n));
    // A strip entry, `<series> (events)`, carries its row: the series' dispersion, mean and interval marks, named
    // `<series> · …` or `<series> (…)`, go with it (unless the name belongs to an entry still listed).
    const base = n.endsWith(' (events)') ? n.slice(0, -' (events)'.length) : null;
    const rowMarks = base === null ? [] : [].concat(b.series ?? []).map((s) => String(s?.name ?? ''))
      .filter((s) => (s.startsWith(`${base} ·`) || s.startsWith(`${base} (`)) && ownerOf(s, entries) === null);
    const rowMarksA = base === null ? 0 : [].concat(a.series ?? []).map((s) => String(s?.name ?? ''))
      .filter((s) => (s.startsWith(`${base} ·`) || s.startsWith(`${base} (`)) && ownerOf(s, entries) === null).length;
    // The screen with the same entry switched off (legend-sliders): the export's marks and canvas text, with the
    // legend kept and the entry carried by one of its own series, which the legend filter hides.
    const sc = cp.screenBuild({ legendSelected: { [n]: false } }, () => ({ option: build() })).option;
    const namesOf = (o) => [].concat(o.series ?? []).map((x) => String(x?.name ?? ''));
    const without = (o) => ({ ...o, series: [].concat(o.series ?? []).filter((x) => String(x?.name ?? '') !== n) });
    const screen = {
      entries: entriesOf(sc), carried: namesOf(sc).filter((x) => x === n).length, inA: namesOf(a).includes(n),
      sameMarks: JSON.stringify(namesOf(without(sc))) === JSON.stringify(namesOf(without(b))),
      sameTexts: JSON.stringify(canvasTexts(without(sc)).sort()) === JSON.stringify(canvasTexts(without(b)).sort()),
      top: topOf(sc),
    };
    checks.push({ n, listed, markedOff, owned, named, rowMarks, rowMarksA, topA: topOf(a), topB: topOf(b),
      fewer: [].concat(b.series ?? []).length <= [].concat(a.series ?? []).length, screen });
  }
  const again = serialise(build());
  return { entries, checks, back: again === aText, contextCleared: cp.hiddenEntries() === null };
};

out.cases = {};
for (const [id, build] of CASES) out.cases[id] = runCase(build);
const saved = { ...THEME };
Object.assign(THEME, PRINT_TOKENS);
try {
  for (const [id, build] of CASES) out.cases[`${id}@print`] = runCase(build);
} finally {
  Object.assign(THEME, saved);
}

/* ---- the rows of a legend: an export lays them out without the left-out entries --- */
{
  Object.assign(THEME, PRINT_TOKENS);
  try {
    const payload = load('energy_d_two');
    const opts = { palette: 'viridis', kind: 'pred', shower: 'both' };
    const build = () => ep.buildOption({ payload, opts, metrics: { width: 321, height: 300 } }).option;
    const a = build();
    const rowsA = ep.lastLegendRows;
    const names = a.legend[0].data.slice(0, Math.max(1, a.legend[0].data.length - 2));
    cp.setExportHidden(names);
    const b = build();
    const rowsB = ep.lastLegendRows;
    cp.setExportHidden(null);
    out.energyRows = { rowsA, rowsB, topA: a.grid.top, topB: b.grid.top, kept: b.legend[0].data.length,
      offAll: names.every((n) => b.legend[0].selected?.[n] === false) };
  } finally {
    Object.assign(THEME, saved);
  }
}

/* ---- the resolution card's file name tokens ------------------------------------ */
{
  const { figureName } = await imp('export/filename.js');
  const state = { isTouched: () => false, get: () => null, filterAxes: [] };
  const stem = (meta) => figureName('res-scaling', 'svg', { state, spatial: false, meta }).replace(/_\d{8}_\d{6}\.svg$/, '');
  out.names = {
    energy: stem({ view: 'energy', reference: 'e', literature: ['pi', 'e'], estimator: 'median', eMax: 20, deposit: false }),
    energyWide: stem({ view: 'energy', reference: 'deposit', literature: [], estimator: 'median', eMax: 45, deposit: true }),
    energyNone: stem({ view: 'energy', reference: 'none', literature: [], estimator: 'robust', eMax: 20, deposit: false }),
    energyNoEmax: stem({ view: 'energy', reference: 'deposit', literature: [], estimator: 'median' }),
    linearOff: stem({ view: 'linear', estimator: 'sample', deposit: false }),
    linearOn: stem({ view: 'linear', estimator: 'sample', deposit: true }),
    linearToday: stem({ view: 'linear', estimator: 'sample' }),
  };
}

// The output passes 64 KiB: exit only once the pipe has taken all of it.
process.stdout.write(`${JSON.stringify(out)}\n`, () => process.exit(0));
"""


@pytest.fixture(scope="module")
def result() -> dict:
    return _run(_SCRIPT, [JS.as_uri(), str(PAYLOADS)])


# ----------------------------------------------------------- printLegendOption --


def test_an_object_legend_lists_none_of_the_left_out_names_and_marks_them_off(result):
    got = result["print"]
    # The memory laid over first (A on, C on over the builder's C off), then B and C left out: unlisted and false.
    assert got["object"] == {"data": ["A"], "selected": {"C": False, "A": True, "B": False}, "show": True,
                             "ink": [None, None, None]}, got["object"]
    # An entry kept as an object keeps its icon.
    assert got["objectKeepsIcon"] == "circle"
    assert got["seriesShared"], got


def test_each_legend_of_an_array_shown_or_not_lists_none_and_marks_them_off(result):
    got = result["print"]["array"]
    # A legend that dropped an entry and keeps one is shown.
    assert got[0] == {"data": ["A"], "selected": {"B": False}, "show": True, "ink": [None, None, None]}, got
    # A legend that listed none of them still marks them off: ECharts filters a series by name in any legend.
    assert got[1] == {"data": ["C"], "selected": {"B": False}, "show": None, "ink": [None, None, None]}, got
    # A hidden legend lists none and marks them off too, and stays hidden.
    assert got[2] == {"data": [], "selected": {"B": False}, "show": False, "ink": [None, None, None]}, got


def test_a_legend_without_data_is_given_the_names_it_would_list_minus_the_left_out_ones(result):
    # Every named series once, in series order; unnamed series list nothing.
    assert result["print"]["dataless"] == {"data": ["A", "C"], "selected": {"B": False}, "show": True,
                                           "ink": [None, None, None]}


def test_a_legend_left_with_no_entry_is_hidden(result):
    assert result["print"]["all"] == {"data": [], "selected": {"A": False}, "show": False, "ink": [None, None, None]}


def test_the_memory_turns_a_builder_default_back_on(result):
    # The reader switched B back on: legendOffNames does not name it, so the figure draws it.
    assert result["print"]["memoryOn"] == {"data": ["A", "B"], "selected": {"B": True}, "show": None,
                                           "ink": [None, None, None]}


def test_with_nothing_left_out_the_option_is_the_memorys_and_nothing_is_mutated(result):
    got = result["print"]
    assert got["same"] == [True, True, True], got
    assert got["untouched"], "printLegendOption mutated its input"


# ------------------------------------------------------- the section 7 recipe --


def _cases(result):
    return result["cases"]


def test_every_page1_builder_case_ran_on_both_media_with_entries(result):
    cases = _cases(result)
    screen = [k for k in cases if not k.endswith("@print")]
    assert len(screen) == 42, screen
    assert all(f"{k}@print" in cases for k in screen)
    # Every family has a case with legend entries to leave out.
    for family in ("energy/", "response/", "grid/", "distribution/", "d4/", "residual/", "profile/"):
        assert any(k.startswith(family) and cases[k]["entries"] for k in cases), family
    assert sum(len(c["entries"]) for c in cases.values()) > 150
    # Strip rows are exercised: an `(events)` entry whose row draws companions under the series' own name, on the
    # energy panel and on B1 below the histogram floor.
    for key in ("energy/pred", "response/strip/b1"):
        assert any(c["rowMarksA"] > 0 for c in cases[key]["checks"]), key


@pytest.mark.parametrize("medium", ["", "@print"])
def test_an_export_legend_lists_no_left_out_entry_and_marks_it_off(result, medium):
    for key, case in _cases(result).items():
        if not key.endswith(medium) or (not medium and key.endswith("@print")):
            continue
        for c in case["checks"]:
            assert c["listed"] == 0, (key, c["n"])
            assert c["markedOff"], (key, c["n"])


@pytest.mark.parametrize("medium", ["", "@print"])
def test_no_mark_of_a_left_out_entry_is_drawn(result, medium):
    """No series is named the entry or extends its name (a companion: `· dispersion`, `(clipped)`, `· SD band`,
    `· mean 95% interval`, `(events beyond the axis)`, `· 1/c …`), unless the longer name is an entry of its own."""
    for key, case in _cases(result).items():
        if not key.endswith(medium) or (not medium and key.endswith("@print")):
            continue
        for c in case["checks"]:
            assert c["owned"] == [], (key, c["n"], c["owned"])
            assert c["rowMarks"] == [], (key, c["n"], c["rowMarks"])
            assert c["fewer"], (key, c["n"])


@pytest.mark.parametrize("medium", ["", "@print"])
def test_no_canvas_text_names_a_left_out_entry(result, medium):
    for key, case in _cases(result).items():
        if not key.endswith(medium) or (not medium and key.endswith("@print")):
            continue
        for c in case["checks"]:
            assert c["named"] == [], (key, c["n"], c["named"])


@pytest.mark.parametrize("medium", ["", "@print"])
def test_the_grid_never_moves_down_when_an_entry_is_left_out(result, medium):
    for key, case in _cases(result).items():
        if not key.endswith(medium) or (not medium and key.endswith("@print")):
            continue
        for c in case["checks"]:
            if c["topA"] is None:
                continue
            assert c["topB"] <= c["topA"] + 1e-9, (key, c["n"], c["topA"], c["topB"])


@pytest.mark.parametrize("medium", ["", "@print"])
def test_the_screen_draws_what_the_export_draws_and_keeps_the_entry_on_its_legend(result, medium):
    """legend-sliders (2026-11-17): a legend click on screen leaves out the same marks and canvas text as the
    export does, so a companion leaves with its entry; the legend keeps every entry, the switched-off one carried by
    one of its own series (hidden by the legend filter), and the grid never moves down."""
    bad = []
    for case_id, case in _cases(result).items():
        if (medium and not case_id.endswith(medium)) or (not medium and case_id.endswith("@print")):
            continue
        for c in case["checks"]:
            s = c["screen"]
            if s["entries"] != case["entries"]:
                bad.append((case_id, c["n"], "the legend lost an entry"))
            if s["inA"] and s["carried"] < 1:
                bad.append((case_id, c["n"], "no series carries the entry"))
            if not s["sameMarks"]:
                bad.append((case_id, c["n"], "marks differ from the export's"))
            if not s["sameTexts"]:
                bad.append((case_id, c["n"], "canvas text differs from the export's"))
            if s["top"] is not None and c["topA"] is not None and s["top"] > c["topA"] + 1e-9:
                bad.append((case_id, c["n"], "the grid moved down"))
    assert not bad, bad[:10]


def test_with_the_context_cleared_every_builder_returns_its_output_again(result):
    for key, case in _cases(result).items():
        assert case["back"], key
        assert case["contextCleared"], key


def test_the_energy_legend_rows_are_laid_out_without_the_left_out_entries(result):
    got = result["energyRows"]
    # A single-column figure of the two-shower response wraps its 14 entries over several rows; leaving all but
    # two out drops rows and raises the plot.
    assert got["rowsB"] < got["rowsA"], got
    assert got["topB"] < got["topA"], got
    assert got["kept"] == 2 and got["offAll"], got


# --------------------------------------------------------------- file names --


def test_the_e_view_names_its_e_max_right_after_energy(result):
    names = result["names"]
    assert names["energy"] == "res-scaling_full_energy_emax-20_ratio-e_lit-pi-e_deposit-off_est-median"
    assert names["energyWide"] == "res-scaling_full_energy_emax-45_ratio-deposit_est-median"
    # No E max given (today's call): no token.
    assert names["energyNoEmax"] == "res-scaling_full_energy_ratio-deposit_est-median"


def test_no_reference_is_ratio_none(result):
    assert result["names"]["energyNone"] == "res-scaling_full_energy_emax-20_ratio-none_deposit-off_est-robust"


def test_deposit_off_follows_the_view_block_in_both_views(result):
    names = result["names"]
    assert names["linearOff"] == "res-scaling_full_deposit-off_est-sample"
    # The deposit shown, or no word on it: today's name.
    assert names["linearOn"] == names["linearToday"] == "res-scaling_full_est-sample"
