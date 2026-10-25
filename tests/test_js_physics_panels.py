"""The physics panels below the 2 × 2, executed under Node on the recorded payloads.

Every option builder of `calosrv/static/js/panels/` that draws a physics card
(profile, response, response_grid, distribution, correlation, statistics) is a
pure function, so it runs here against each payload `tests/test_payload_fixtures.py`
recorded from the booted fixtures (`tests/fixtures/payloads/*.json`). The script
builds the option, renders every custom series' `renderItem` with an identity
coordinate map, calls every tooltip formatter, and hands back what was drawn.
The tests then hold each chart to CLAUDE.md section 2:

* a capped whisker is an interval of an aggregate, named so in its tooltip; a
  sample SD is an uncapped band or box;
* marks at heights that are not densities live in a tinted, captioned band and
  say so in every tooltip;
* clipped marks get a caret; axis names say "provisional" where the server does;
* circular cells are hatched and off the colour scale;
* density and fraction axes start at zero; no rendered number uses a hyphen;
* nothing the payload withholds is drawn.

The drawer notes (`panel_notes.js`) and the `ChartPanel` delegation (with a fake
DOM and a fake ECharts) are checked here too. Skipped without `node`.
"""

from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
PANELS = JS / "panels"
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

PROFILES = ["profiles_single_w", "profiles_single_native", "profiles_two_w"]
RESPONSES = ["response_single_hits", "response_single_events", "response_two"]
B3 = ["b3_single_notebook", "b3_single_bins", "b3_events_bins", "b3_two_truth"]
DISTRIBUTIONS = ["distribution_single_u", "distribution_single_energy", "distribution_single_phi",
                 "distribution_single_theta_hit", "distribution_events_p", "distribution_two_p"]
CORRELATIONS = ["correlation_single_lab", "correlation_single_local", "correlation_two_lab"]
STATISTICS = ["statistics_single_lab", "statistics_single_local", "statistics_two_local"]

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
#: Not preceded by a word character, so "lag-1" and "1-D" read as words, not numbers.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const palette = await imp('palette.js');
const marks = await imp('panels/marks.js');
const cp = await imp('panels/chart_panel.js');
const prof = await imp('panels/profile.js');
const resp = await imp('panels/response.js');
const grid = await imp('panels/response_grid.js');
const dist = await imp('panels/distribution.js');
const corr = await imp('panels/correlation.js');
const stats = await imp('panels/statistics.js');
const pn = await imp('panel_notes.js');
const textfit = await imp('textfit.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1e-5, -3.14159, 1e-10, 12345, -Math.PI, -Math.PI / 2, Math.PI / 2, Math.PI];

function summarise(el) {
  if (!el) return null;
  if (el.type === 'group') return { type: 'group', children: el.children.map(summarise) };
  const pts = el.shape?.points ?? null;
  return {
    type: el.type,
    points: pts ? pts.length : null,
    pts: pts && pts.length <= 1200 ? pts : null,
    rect: el.type === 'rect' ? el.shape : null,
    text: el.style?.text ?? null,
    fill: el.style?.fill ?? null,
    stroke: el.style?.stroke ?? null,
    dash: el.style?.lineDash ?? null,
    opacity: el.style?.opacity ?? null,
    strokeOpacity: el.style?.strokeOpacity ?? null,
    fillOpacity: el.style?.fillOpacity ?? null,
    line: el.type === 'line' ? el.shape : null,
  };
}

function textsOfAxis(axis) {
  const out = [];
  for (const a of [].concat(axis ?? [])) {
    if (a.name) out.push(a.name);
    const f = a.axisLabel?.formatter;
    if (typeof f === 'function') for (const v of SAMPLES) out.push(String(f(v)));
  }
  return out;
}

/** Render every series item, call every tooltip, collect every string a reader can see. */
function walk(option) {
  const strings = [...textsOfAxis(option.xAxis), ...textsOfAxis(option.yAxis)];
  for (const g of option.graphic ?? []) if (g.style?.text) strings.push(g.style.text);
  for (const l of [].concat(option.legend ?? [])) for (const d of l.data ?? []) strings.push(String(d?.name ?? d));
  for (const vm of [].concat(option.visualMap ?? [])) {
    for (const t of vm.text ?? []) strings.push(String(t));
    if (typeof vm.formatter === 'function') for (const v of [-1, -0.5, 0, 0.5, 1]) strings.push(String(vm.formatter(v)));
  }
  const series = option.series.map((s) => {
    const items = [];
    for (let i = 0; i < s.data.length; i += 1) {
      const datum = s.data[i];
      const value = Array.isArray(datum) ? datum : datum?.value;
      const el = typeof s.renderItem === 'function' ? s.renderItem({ dataIndex: i, coordSys }, api) : null;
      const tip = typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter({ dataIndex: i, value }) : null;
      if (tip) strings.push(tip);
      const summary = summarise(el);
      if (summary?.text) strings.push(summary.text);
      for (const c of summary?.children ?? []) if (c?.text) strings.push(c.text);
      let label = null;
      if (s.type === 'heatmap') {
        const f = datum?.label?.formatter ?? s.label?.formatter;
        label = typeof f === 'function' ? f({ value }) : (f ?? null);
        if (label) strings.push(String(label));
      }
      items.push({
        el: summary, tip, value,
        decal: datum?.itemStyle?.decal ?? null, color: datum?.itemStyle?.color ?? null,
        labelColor: datum?.label?.color ?? null, label,
      });
    }
    return {
      name: s.name, type: s.type, silent: Boolean(s.silent), z: s.z ?? null,
      xAxisIndex: s.xAxisIndex ?? 0, readoutPosition: Boolean(s.tooltip?.position), items,
    };
  });
  const axis = (a) => [].concat(a ?? []).map((x) => ({
    type: x.type, name: x.name ?? '', min: x.min ?? null, max: x.max ?? null,
    labels: x.axisLabel?.show !== false, data: x.data ?? null,
  }));
  const legendRaw = [].concat(option.legend ?? [])[0] ?? null;
  return {
    series, strings,
    graphics: (option.graphic ?? []).map((g) => g.style?.text).filter(Boolean),
    graphicRaw: (option.graphic ?? []).filter((g) => g.style?.text).map((g) => ({
      text: g.style.text, x: g.style.x ?? null, y: g.style.y ?? null, align: g.style.textAlign ?? null, fill: g.style.fill ?? null,
    })),
    legendStyle: legendRaw ? { pageIconColor: legendRaw.pageIconColor ?? null, pageIconInactiveColor: legendRaw.pageIconInactiveColor ?? null,
      pageTextColor: legendRaw.pageTextStyle?.color ?? null, type: legendRaw.type ?? null } : null,
    xAxis: axis(option.xAxis), yAxis: axis(option.yAxis),
    grid: [].concat(option.grid ?? []),
    legend: [].concat(option.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => d?.name ?? d)),
    visualMap: [].concat(option.visualMap ?? []).map((vm) => ({ min: vm.min, max: vm.max, seriesIndex: vm.seriesIndex ?? null, text: vm.text })),
    tooltip: option.tooltip,
  };
}

const out = { profile: {}, response: {}, grid: {}, distribution: {}, correlation: {}, statistics: {}, notes: {} };

/* ---- C7 ------------------------------------------------------------------ */
for (const name of %(profiles)s) {
  const payload = load(name);
  out.profile[name] = {};
  for (const axis of ['depth', 'r']) {
    const key = prof.profileAxisKey(payload, axis);
    out.profile[name][axis] = { key, ax: payload.axes[key], marks: payload.marks, ...walk(prof.profileOption(payload, { axis }, { width: 640, height: 360 })) };
  }
}
// Low-N variants built from a recorded payload: the server's flags, nothing invented.
{
  const base = load('profiles_single_w');
  const single = clone(base);
  single.ensemble = { ...single.ensemble, n_showers: 1, n_events: 1, label: 'single shower, not an ensemble', provisional: true };
  for (const m of single.marks) m.drawn = m.key === 'mean';
  for (const ax of Object.values(single.axes)) { ax.band = null; ax.envelope = null; ax.y.provisional = true; }
  out.profile.single = walk(prof.profileOption(single, { axis: 'depth' }, { width: 640, height: 360 }));
  const weak = clone(base);
  weak.ensemble = { ...weak.ensemble, n_showers: 2, n_events: 2, label: 'weak (N = 2)', dof_note: '1 d.o.f.', provisional: true };
  for (const ax of Object.values(weak.axes)) ax.y.provisional = true;
  out.profile.weak = walk(prof.profileOption(weak, { axis: 'r' }, { width: 640, height: 360 }));
  out.profile.empty = walk(prof.profileOption({ ...clone(base), ensemble: { ...base.ensemble, n_showers: 0 } }, { axis: 'depth' }, { width: 640, height: 360 }));
}

/* ---- B1, B2, σ/μ --------------------------------------------------------- */
for (const name of %(responses)s) {
  const payload = load(name);
  out.response[name] = { payload: { b2y: payload.b2.y, resy: payload.resolution.y, b1axis: { ...payload.b1.axis, hist_centres: null } } };
  for (const mode of ['b1', 'b2', 'resolution']) {
    out.response[name][mode] = walk(resp.responseOption(payload, { mode }, { width: 640, height: 340 }));
  }
  out.response[name].ratio = walk(resp.responseOption(payload, { mode: 'resolution', quantity: 'response_ratio' }, { width: 640, height: 340 }));
  out.response[name].showerA = walk(resp.responseOption(payload, { mode: 'b2', shower: 'a' }, { width: 640, height: 340 }));
}
{
  // B1 below the histogram floor: the server sends events instead of a histogram.
  const strip = clone(load('response_single_hits'));
  const s = strip.b1.series[0];
  s.draw = 'strip'; s.histogram = null; s.n = 6;
  s.strip = { values: [0.2, 0.5, 0.9, 1.1, 1.7, 2.6], n_shown: 6, truncated: false };
  s.message = 'N = 6: below the histogram floor; the events and the summary marks are drawn.';
  // The server's low-N fit of six events: σ with its SE, its χ² interval and c₄.
  s.fit = { ...s.fit, n: 6, sigma: 0.9, sigma_error: 0.2915, sigma_ci95: [0.5618, 2.2074], sigma_bias_factor: 0.9515, estimator: 'moments' };
  out.response.strip = walk(resp.responseOption(strip, { mode: 'b1' }, { width: 640, height: 340 }));
  out.notes.b1Strip = (() => {
    const n = pn.responseNotes({ payload: strip, mode: 'b1' });
    return Object.fromEntries(n.sections.map((sec) => [sec.heading, sec.lines]));
  })();
  // A provisional B2 range, as the server flags it when no bin reaches N = 20.
  const prov = clone(load('response_single_hits'));
  prov.b2.y.provisional = true; prov.resolution.y.provisional = true;
  out.response.provisional = { b2: walk(resp.responseOption(prov, { mode: 'b2' }, { width: 640, height: 340 })),
    resolution: walk(resp.responseOption(prov, { mode: 'resolution' }, { width: 640, height: 340 })) };
}

/* ---- B3 ------------------------------------------------------------------ */
out.grid.tables = {};
for (const name of %(b3)s) {
  const payload = load(name);
  out.grid.tables[name] = { rows: grid.responseGridRows(payload), table: grid.responseGridTable(payload), sparse: grid.responseGridSparse(payload) };
}
{
  // Titles name the showers drawn; a single-column print keeps every title and its count inside the figure.
  const two = load('b3_two_truth');
  out.grid.titlesA = walk(grid.responseGridOption(two, { shower: 'a' }, { width: 760, height: null })).graphics;
  out.grid.titlesBoth = walk(grid.responseGridOption(two, {}, { width: 760, height: null })).graphics;
  out.grid.sparseA = grid.responseGridSparse(two, 'a');
  // Fixed heights at every width: nothing off the canvas, a notice when slices are left out.
  out.grid.sweep = [];
  for (const height of [300, 330, 380]) {
    for (let width = 300; width <= 900; width += 50) {
      for (const n of [1, 2, 4, 6, 10, 16, 19, 20]) {
        const L = grid.responseGridLayout(n, width, height, { legend: ['Shower - deposit'] });
        out.grid.sweep.push({ height, width, n, shown: L.shown, hidden: L.hidden, cells: L.cells.length, layoutHeight: L.height,
          bottom: Math.max(...L.cells.map((c) => c.top + c.height + 3.3 * scale.THEME.fontSmall)),
          minPlot: Math.min(...L.cells.map((c) => c.height)), notice: L.noticeY });
      }
    }
  }
  out.grid.hiddenChart = walk(grid.responseGridOption(load('b3_single_bins'), {}, { width: 450, height: 330 }));
  out.grid.hiddenSparse = grid.responseGridSparse(load('b3_single_bins'), 'both', { hidden: 4, shown: 6 });
}
for (const name of %(b3)s) {
  const payload = load(name);
  const slices = grid.gridSlices(payload).map(({ slice, axis }) => ({ index: slice.index, label: slice.label, axis }));
  const messages = payload.series.map((e) => ({ slice: e.slice, key: e.key, draw: e.draw, n: e.fit.n,
    degenerate: e.fit.degenerate, message: grid.seriesMessage(payload, e), note: grid.estimatorNote(payload, e),
    estimator: e.fit.estimator, estimator_note: e.fit.estimator_note }));
  out.grid[name] = { slices, messages, texts: payload.texts, ...walk(grid.responseGridOption(payload, {}, { width: 760, height: null })) };
  out.grid[name].fixed = walk(grid.responseGridOption(payload, { shower: 'a' }, { width: 600, height: 380 })).grid;
  out.grid[name].layout = grid.responseGridLayout(slices.length, 760, null, {});
  out.grid[name].layoutFixed = grid.responseGridLayout(slices.length, 600, 380, {});
}
{
  // No slice holds a shower: one line says so, no axis is named a density, no empty grid.
  const empty = clone(load('b3_two_truth'));
  empty.slice_axes = []; empty.series = [];
  out.grid.empty = { ...walk(grid.responseGridOption(empty, {}, { width: 760, height: null })),
    layout: grid.responseGridLayout(0, 760, null, {}) };
  // Slices with events but no estimable density anywhere: the shared density name goes too.
  const none = clone(load('b3_single_notebook'));
  none.series = none.series.map((e) => ({ ...e, draw: 'strip', histogram: null, curve: null, drives_scale: false }));
  out.grid.noDensity = walk(grid.responseGridOption(none, {}, { width: 760, height: null }));
}

/* ---- C4 ------------------------------------------------------------------ */
for (const name of %(distributions)s) {
  const payload = load(name);
  out.distribution[name] = {
    linear: walk(dist.distributionOption(payload, { palette: 'viridis', yScale: 'linear' }, { width: 640, height: 340 })),
    log: walk(dist.distributionOption(payload, { palette: 'viridis', yScale: 'log' }, { width: 640, height: 340 })),
    stops: cp.seriesStops('viridis', payload.series.length),
    n: payload.series.length,
  };
}

/* ---- C8 ------------------------------------------------------------------ */
for (const name of %(correlations)s) {
  const payload = load(name);
  out.correlation[name] = { variables: payload.variables, ...walk(corr.correlationOption(payload, { palette: 'viridis' }, { width: 560, height: 460 })) };
}
{
  // A φ cell where the server quotes Mardia's R (from eight distinct azimuths).
  const quoted = clone(load('correlation_single_lab'));
  const k = quoted.variables.length;
  quoted.matrix[k - 1][4].mardia = { R: 0.21, se: 0.04, per_shower_R: 0.18, per_shower_se: 0.05, null_R2: 0.007 };
  quoted.matrix[3][1].ci95 = null;
  out.correlation.quoted = walk(corr.correlationOption(quoted, { palette: 'viridis' }, { width: 560, height: 460 }));
  out.notes.correlationHazards = pn.hazards(quoted, 'correlation');
  // Label contrast against the painted cell, over the whole range of r.
  const pal = scale.rampPalette(corr.R_SCALE, 'viridis');
  out.correlation.labelContrast = [];
  for (let r = -1; r <= 1.0001; r += 0.05) {
    const rgb = corr.cellColour(r, pal);
    out.correlation.labelContrast.push(palette.contrast(rgb, cp.rgbOf(corr.labelColour(rgb))));
  }
  out.correlation.palette = pal;
}

/* ---- C1 + C9 ------------------------------------------------------------- */
for (const name of %(statistics)s) {
  const payload = load(name);
  out.statistics[name] = { model: stats.statisticsRows(payload), lines: pn.negativeDepthLines(payload.negative_w) };
}
out.statistics.local = pn.negativeDepthLines(load('projections_single_local').frame.negative_w);
out.statistics.unavailable = pn.negativeDepthLines({ available: false, reason: 'Derived tables to rebuild.', summary: 'w < −10⁻⁶ mm: —' });

/* ---- series colours against the card, on screen and in print -------------- */
out.contrast = { screen: {}, print: {} };
for (const name of palette.SEQUENTIAL_PALETTES) {
  out.contrast.screen[name] = cp.seriesStops(name, 20).map((c) => palette.contrast(cp.rgbOf(c), palette.SCREEN_CARD));
}
Object.assign(scale.THEME, PRINT_TOKENS);
for (const name of palette.SEQUENTIAL_PALETTES) {
  out.contrast.print[name] = cp.seriesStops(name, 20).map((c) => palette.contrast(cp.rgbOf(c), [255, 255, 255]));
}
out.printCorrelation = walk(corr.correlationOption(load('correlation_single_lab'), { palette: 'viridis' }, { width: 320, height: 300 }));
out.printPalette = scale.rampPalette(corr.R_SCALE, 'viridis');
out.printProfileTooltip = prof.profileOption(load('profiles_single_w'), { axis: 'depth' }, { width: 320, height: 240 }).tooltip;
out.printGridLayout = grid.responseGridLayout(16, 321, null, { legend: ['Shower A - truth', 'Shower B - truth'] });
// Every B3 title and notice of a single-column figure, with its width at the print font.
out.printGridTexts = {};
for (const name of ['b3_single_notebook', 'b3_single_bins', 'b3_two_truth']) {
  const option = grid.responseGridOption(load(name), {}, { width: 321, height: null });
  out.printGridTexts[name] = (option.graphic ?? []).filter((g) => g.style?.text && !g.rotation).map((g) => ({
    text: g.style.text, x: g.style.x, align: g.style.textAlign ?? 'left',
    width: textfit.measureText(g.style.text, g.style.fontSize, g.style.fontFamily),
  }));
}
// A wrapped print legend grows the grid's top inset in every response part.
out.printResponse = {};
for (const mode of ['b1', 'b2', 'resolution']) {
  const option = resp.responseOption(load('response_two'), { mode }, { width: 321, height: 300 });
  const names = (option.legend.data ?? []).map((d) => d?.name ?? d);
  out.printResponse[mode] = { top: option.grid.top, rows: textfit.legendRows(names, 321 - scale.axisPadding().left - scale.axisPadding().right,
    scale.THEME.fontLabel, { fontFamily: scale.THEME.fontFamily }), pad: scale.axisPadding().top, font: scale.THEME.fontLabel };
}
out.printInk = {};
for (const key of ['showerA', 'showerB', 'accent', 'muted', 'text']) {
  const colour = scale.THEME[key];
  out.printInk[key] = [0.18, 0.45, 0.6, 0.7, 0.85].map((w) => {
    const a = cp.legibleOpacity(colour, w);
    return { wanted: w, alpha: a, contrast: palette.contrast(cp.blendOver(colour, a), [255, 255, 255]) };
  });
}
out.printHatch = corr.hatchDecal().color;
scale.restoreScreenTheme();
out.screenInk = {};
for (const key of ['showerA', 'showerB', 'accent', 'muted', 'text']) {
  const colour = scale.THEME[key];
  out.screenInk[key] = [0.18, 0.45, 0.6, 0.7, 0.85].map((w) => {
    const a = cp.legibleOpacity(colour, w);
    return { wanted: w, alpha: a, contrast: palette.contrast(cp.blendOver(colour, a), palette.SCREEN_CARD) };
  });
}
out.screenHatch = corr.hatchDecal().color;
out.theme = { muted: scale.THEME.muted, text: scale.THEME.text, accent: scale.THEME.accent, showerA: scale.THEME.showerA,
  showerB: scale.THEME.showerB, border: scale.THEME.border, card: scale.THEME.card };

out.nice = [0.0042, 0.37, 1.0, 5.06, 7.9, 13, 260].map((v) => {
  const top = cp.niceCeil(v, cp.FINE_STEPS);
  return { v, top, interval: cp.niceInterval(top) };
});

/* ---- marks.js additions ---------------------------------------------------- */
{
  const w = marks.customWhiskers({ name: 'w', points: [[1, 2, 3, {}], [4, 5, 6, { caps: [false, true] }], [7, NaN, 8, {}]], color: '#fff', width: 1, tooltip: (d, i) => `item ${i}` });
  const h = marks.customWhiskers({ name: 'h', points: [[0, 2, 5, {}]], horizontal: true, offsetPx: 10, color: '#fff', width: 1 });
  const hover = marks.binHoverSeries({ name: 'r', edges: [0, 1, 2.5, 4], tooltip: (i) => `bin ${i}`, position: () => [0, 0] });
  out.marks = {
    whiskers: w.data.map((_, i) => w.renderItem({ dataIndex: i }, api).shape.points),
    whiskerTips: w.data.map((_, i) => w.tooltip.formatter({ dataIndex: i })),
    horizontal: h.renderItem({ dataIndex: 0 }, api).shape.points,
    hover: hover.data.map((_, i) => hover.renderItem({ dataIndex: i, coordSys }, api).shape),
    hoverTips: hover.data.map((_, i) => hover.tooltip.formatter({ dataIndex: i })),
    hoverPosition: typeof hover.tooltip.position === 'function',
    hoverFill: hover.renderItem({ dataIndex: 0, coordSys }, api).style.fill,
  };
}

/* ---- ChartPanel delegation, with a fake DOM and a fake ECharts -------------- */
{
  const calls = [];
  const element = {
    clientWidth: 640, clientHeight: 360, style: {},
    classList: { toggle: (cls, on) => calls.push(['toggle', cls, on]) },
    closest: () => null,
  };
  const chart = {
    width: 640, height: 360,
    getWidth() { return this.width; }, getHeight() { return this.height; },
    getDom: () => element, setOption: (option, flags) => calls.push(['setOption', option.grid, flags]),
    resize() { calls.push(['resize']); this.width = element.clientWidth; this.height = element.clientHeight; },
    clear: () => calls.push(['clear']), dispatchAction: () => {},
  };
  globalThis.echarts = { init: () => { calls.push(['init']); return chart; } };
  const panel = new prof.ProfilePanel(element, { axis: 'r' });
  const before = calls.length;
  const payload = load('profiles_single_w');
  panel.render(payload, { palette: 'viridis' });
  const afterRender = calls.slice(before).map((c) => c[0]);
  panel.relayout();
  const afterSameSize = calls.slice(before).map((c) => c[0]);
  element.clientWidth = 500;
  panel.relayout();
  const afterResize = calls.slice(before).map((c) => c[0]);
  const lastSet = calls.filter((c) => c[0] === 'setOption').pop();
  out.panel = {
    afterRender, afterSameSize, afterResize, notMerge: lastSet[2]?.notMerge === true,
    liveGrid: panel.liveGrid, kind: panel.kind, lastOptsKeys: Object.keys(panel.lastOpts),
    exportMetrics: panel.exportMetrics(321), positions: typeof panel.tooltipPosition === 'function' && typeof panel.readoutPosition === 'function',
  };
  element.clientWidth = 0;
  const hidden = calls.length;
  panel.render(payload, {});
  out.panel.hiddenPaints = calls.slice(hidden).filter((c) => c[0] === 'setOption').length;
  panel.clear();
  out.panel.cleared = { payload: panel.lastPayload, grid: panel.liveGrid, clearCalled: calls.some((c) => c[0] === 'clear') };
  panel.setBusy(true);
  out.panel.busy = calls.some((c) => c[0] === 'toggle' && c[1] === 'is-busy' && c[2] === true);
  const kinds = {};
  for (const [name, P] of [['ResponsePanel', resp.ResponsePanel], ['ResponseGridPanel', grid.ResponseGridPanel],
    ['DistributionPanel', dist.DistributionPanel], ['CorrelationPanel', corr.CorrelationPanel]]) {
    kinds[name] = new P(element, {}).kind;
  }
  out.panel.kinds = kinds;
  const modePanel = new resp.ResponsePanel(element, { mode: 'b2' });
  out.panel.modeOption = modePanel.buildOption({ payload: load('response_two'), opts: {}, metrics: { width: 640, height: 340 } }).option.yAxis.name;
  out.panel.modeOverride = modePanel.buildOption({ payload: load('response_two'), opts: { mode: 'resolution' }, metrics: { width: 640, height: 340 } }).option.yAxis.name;
  element.clientWidth = 760;
  const gp = new grid.ResponseGridPanel(element, {});
  gp.render(load('b3_two_truth'), {});
  out.panel.gridHeight = element.style.height;
  out.panel.gridExport = gp.exportMetrics(321);
}

/* ---- drawer notes ---------------------------------------------------------- */
{
  const stub = { isTouched: (a) => a === 'e1', get: (k) => ({ e1_min: 2, e1_max: 5 })[k] ?? null };
  const experiment = { display_name: 'Demo' };
  const pack = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
    sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
  const notes = out.notes;
  notes.profileW = pack(pn.profileNotes({ payload: load('profiles_single_w'), state: stub, experiment, axis: 'depth' }));
  notes.profileNative = pack(pn.profileNotes({ payload: load('profiles_single_native'), state: stub, experiment, axis: 'depth' }));
  notes.profileR = pack(pn.profileNotes({ payload: load('profiles_two_w'), state: stub, experiment, axis: 'r' }));
  for (const mode of ['b1', 'b2', 'resolution']) {
    notes[`response_${mode}`] = pack(pn.responseNotes({ payload: load('response_two'), mode, state: stub, experiment }));
  }
  notes.b3 = pack(pn.responseGridNotes({ payload: load('b3_two_truth'), state: stub, experiment }));
  notes.b3Single = pack(pn.responseGridNotes({ payload: load('b3_single_bins'), state: stub, experiment }));
  notes.energyMomentum = pack(pn.energyNotes({ payload: load('b3_single_notebook'), state: stub, experiment }));
  notes.energyD = pack(pn.energyNotes({ payload: load('energy_d_two'), state: stub, experiment }));
  notes.distribution = pack(pn.distributionNotes({ payload: load('distribution_single_u'), yScale: 'log', state: stub, experiment }));
  notes.distributionPhi = pack(pn.distributionNotes({ payload: load('distribution_single_phi'), state: stub, experiment }));
  notes.correlation = pack(pn.correlationNotes({ payload: load('correlation_two_lab'), state: stub, experiment }));
  notes.correlationD3 = pack(pn.correlationNotes({ payload: load('correlation_two_lab'), title: 'Feature correlation', state: stub, experiment }));
  notes.statistics = pack(pn.statisticsNotes({ payload: load('statistics_single_lab'), state: stub, experiment }));
  // The shell hands each builder its card title; a native-depth response keeps its own.
  notes.cardTitles = {
    radial: pn.profileNotes({ payload: load('profiles_two_w'), axis: 'r', title: 'Radial Profile along ρ' }).title,
    native: pn.profileNotes({ payload: load('profiles_single_native'), axis: 'kt', title: 'Longitudinal Profile along w' }).title,
    distribution: pn.distributionNotes({ payload: load('distribution_single_u'), title: 'Card title' }).title,
    b3: pn.responseGridNotes({ payload: load('b3_two_truth'), title: 'Card B3' }).title,
  };
  const single = clone(load('profiles_single_w'));
  single.ensemble.n_showers = 1; single.ensemble.provisional = true;
  notes.hazards = {
    profileSingle: pn.hazards(single, 'profile-w'),
    profileR: pn.hazards(load('profiles_single_w'), 'profile-r'),
    b1: pn.hazards(load('response_two'), 'response-b1'),
    b2: pn.hazards(load('response_two'), 'response-b2'),
    res: pn.hazards(load('response_single_hits'), 'response-res'),
    b3: pn.hazards(load('b3_single_bins'), 'response-b3'),
    b3Two: pn.hazards(load('b3_two_truth'), 'response-b3'),
    distribution: pn.hazards(load('distribution_single_u'), 'distribution'),
    distributionPhi: pn.hazards(load('distribution_single_phi'), 'distribution'),
    correlation: pn.hazards(load('correlation_single_lab'), 'correlation'),
    statistics: pn.hazards(load('statistics_single_lab'), 'statistics'),
    energyUnchanged: pn.hazards({ calibration: { applied: true }, series: [{ draw: 'strip' }] }, 'energy'),
    generic: pn.hazards({ meta: { exact: false }, frame: { kind: 'canonical', comb: { staggered: true } }, panels: {} }, 'yz'),
  };
  notes.section = pn.SECTION;
  notes.titles = pn.PHYSICS_TITLES;
  notes.notesExported = typeof pn.Notes === 'function' && new pn.Notes('t').section('a', ['x', 'x', '']).done([]).sections[0].lines;
}

/* ---- Phase 6 fixes: the fit table, the panel API, empty and weak cards ---- */
{
  // A fake DOM with text nodes only: the table is built with textContent, never markup.
  const make = (tag) => ({
    tag, children: [], textContent: '', className: '', style: {}, title: '', colSpan: 1,
    append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? { tag: '#text', textContent: n, children: [] } : n); },
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); },
    getContext: () => null,
  });
  const doc = { createElement: make };
  const host = { ...make('div'), ownerDocument: doc };
  const element = { clientWidth: 560, clientHeight: 330, style: {}, classList: { toggle: () => {} }, closest: () => null };
  const chart = { getWidth: () => 560, getHeight: () => 330, setOption: () => {}, resize: () => {}, clear: () => {}, getDom: () => element, dispatchAction: () => {} };
  globalThis.echarts = { init: () => chart };
  const flat = (node) => [node.textContent, ...node.children.flatMap(flat)].filter(Boolean).join(' ');
  const rows = (table) => table.children.find((c) => c.tag === 'tbody').children;
  out.table = {};
  for (const name of ['b3_single_bins', 'b3_two_truth', 'b3_single_notebook']) {
    const panel = new grid.ResponseGridPanel(element, { autoHeight: false });
    panel.render(load(name), {});
    panel.renderTable(host);
    const table = host.children[0];
    out.table[name] = {
      tag: table.tag, className: table.className,
      head: table.children.find((c) => c.tag === 'thead').children[0].children.map((th) => th.textContent),
      rows: rows(table).map((tr) => ({ cells: tr.children.map(flat), swatch: tr.children[0].children[0]?.style?.background ?? null })),
      tableRows: panel.tableRows().length,
      sparse: panel.sparseLines(),
    };
  }
  const empty = new grid.ResponseGridPanel(element, { autoHeight: false });
  empty.renderTable(host);
  out.table.emptyHost = host.children.length;
  out.table.emptySparse = empty.sparseLines();
  // Plot 4 at a height where only some 1 GeV slices fit: the panel says how many more.
  const small = { ...element, clientWidth: 450, clientHeight: 330 };
  const fixed = new grid.ResponseGridPanel(small, { autoHeight: false });
  fixed.render(load('b3_single_bins'), {});
  out.table.fixedSparse = fixed.sparseLines();
  out.table.fixedCounts = fixed.layoutCounts();
  // A resize only the panel's own ResizeObserver sees: `onLayout` is told when the
  // hidden count moves, so plot 4's sparse note is rewritten with it.
  let told = 0;
  const box = { ...element, clientWidth: 450, clientHeight: 330 };
  const watched = new grid.ResponseGridPanel(box, { autoHeight: false, onLayout: () => { told += 1; } });
  watched.render(load('b3_single_bins'), {});
  const afterRender = told;
  watched.paint();
  const afterSame = told;
  box.clientWidth = 1600;
  box.clientHeight = 2400;
  watched.paint();
  out.table.onLayout = { afterRender, afterSame, afterGrow: told, hidden: watched.layoutCounts().hidden,
    sparse: watched.sparseLines() };
  const card = new grid.ResponseGridPanel({ ...element }, { onLayout: () => { told += 1; } });
  const before = told;
  card.render(load('b3_single_bins'), {});
  out.table.onLayout.selfSizing = told - before;

  // σ/μ with no bin of two showers: a notice, no scale, no legend.
  const one = clone(load('response_single_hits'));
  for (const ser of one.resolution.series) for (const b of ser.bins) { b.value = null; b.ci95 = null; b.n = 1; }
  out.response.resEmpty = walk(resp.responseOption(one, { mode: 'resolution' }, { width: 640, height: 340 }));
  out.response.resEmptyNotes = pn.responseNotes({ payload: one, mode: 'resolution' }).sections.map((sec) => sec.lines).flat();
  // Strip-mode B3 rows quote σ with its SE, χ² interval and c₄ (b3_single_bins, 7–8 GeV, N = 2).
  out.grid.stripTips = walk(grid.responseGridOption(load('b3_single_bins'), {}, { width: 760, height: null }))
    .series.filter((x) => /· (SD band|mean)$/.test(x.name)).flatMap((x) => x.items.map((i) => i.tip));
  // The pooled two-shower profile is in a neutral ink, never shower B's blue.
  out.profileInk = {
    two: prof.profileColours(load('profiles_two_w')),
    twoA: prof.profileColours({ ...load('profiles_two_w'), shower: 'a' }),
    single: prof.profileColours(load('profiles_single_w')),
  };
  // The weak-sample label sits in the empty upper triangle, right-aligned.
  const weak = clone(load('correlation_two_lab'));
  weak.weak = true; weak.n_events = 2;
  const wo = corr.correlationOption(weak, { palette: 'viridis' }, { width: 560, height: 460 });
  out.correlation.weakLabel = { graphic: wo.graphic.filter((g) => g.style?.text?.startsWith('weak')).map((g) => ({ ...g.style })), grid: wo.grid };
  // Drawer counts over what each card draws.
  out.notes.resCounts = Object.fromEntries(['a', 'b', 'both'].map((sh) => [sh,
    pn.responseNotes({ payload: load('response_two'), mode: 'resolution', shower: sh }).sections.find((x) => x.heading === 'Disclosures').lines]));
  out.notes.resHazards = Object.fromEntries(['a', 'both'].map((sh) => [sh,
    pn.responseNotes({ payload: load('response_two'), mode: 'resolution', shower: sh }).hazards]));
  out.notes.resSingle = pn.responseNotes({ payload: load('response_single_hits'), mode: 'resolution' }).sections
    .map((x) => [x.heading, x.lines]);
  out.notes.b2Single = pn.responseNotes({ payload: load('response_single_hits'), mode: 'b2' }).sections.map((x) => [x.heading, x.lines]);
  out.notes.b1Two = pn.responseNotes({ payload: load('response_two'), mode: 'b1' }).sections.map((x) => [x.heading, x.lines]);
  out.notes.b3Bins = pn.responseGridNotes({ payload: load('b3_single_bins') }).sections.map((x) => [x.heading, x.lines]);
  out.notes.b3Notebook = pn.responseGridNotes({ payload: load('b3_single_notebook') }).sections.map((x) => [x.heading, x.lines]);
  const noWarnings = clone(load('b3_two_truth'));
  noWarnings.meta = { ...noWarnings.meta, warnings: undefined };
  noWarnings.outside_slices = { a: 2, b: 3 };
  out.notes.b3Fallback = pn.responseGridNotes({ payload: noWarnings }).sections.map((x) => [x.heading, x.lines]);
  out.response.b2Tips = load('response_two').b2.series[0].bins.slice(0, 3).map((b) => resp.b2Tip(b, 'Shower A'));
  out.response.calInterval = resp.calibrationInterval(load('response_two').calibration.a);
}

console.log(JSON.stringify(out));
"""


def _script() -> str:
    return _SCRIPT % {
        "profiles": json.dumps(PROFILES), "responses": json.dumps(RESPONSES), "b3": json.dumps(B3),
        "distributions": json.dumps(DISTRIBUTIONS), "correlations": json.dumps(CORRELATIONS),
        "statistics": json.dumps(STATISTICS),
    }


@pytest.fixture(scope="module")
def out() -> dict:
    """Run the harness once; every test reads its part."""
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _script(), args],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _named(chart: dict, pattern: str) -> list[dict]:
    return [s for s in chart["series"] if re.search(pattern, s["name"] or "")]


def _no_hyphen_numbers(strings) -> None:
    for text in strings:
        # Drop markup and CSS (colours, `font-size`), keep what a reader sees.
        visible = re.sub(r"<[^>]+>", " ", str(text))
        assert not HYPHEN_NUMBER.search(visible), f"hyphen-minus before a digit in: {visible!r}"


def _points(item) -> int | None:
    el = item["el"]
    return el["points"] if el else None


def _children(item) -> list[dict]:
    el = item["el"]
    return el["children"] if el and el["type"] == "group" else []


def _linspace(lo: float, hi: float, count: int) -> list[float]:
    if count == 1:
        return [lo]
    return [lo + i * (hi - lo) / (count - 1) for i in range(count)]


# ------------------------------------------------------------------- C7 --


@pytest.mark.parametrize("name", PROFILES)
@pytest.mark.parametrize("axis", ["depth", "r"])
def test_profile_axes_are_zero_based_in_cm_and_follow_the_server(out, name, axis):
    chart = out["profile"][name][axis]
    ax = chart["ax"]
    y = chart["yAxis"][0]
    assert y["min"] == 0 == ax["y"]["lo"] and y["max"] == ax["y"]["hi"]
    x = chart["xAxis"][0]
    assert (x["min"], x["max"]) == (ax["edges_cm"][0], ax["edges_cm"][-1])
    assert x["name"].endswith("[cm]") and "% per cm" in y["name"]
    assert ("provisional" in y["name"]) == bool(ax["y"]["provisional"])


@pytest.mark.parametrize("name", PROFILES)
@pytest.mark.parametrize("axis", ["depth", "r"])
def test_profile_sd_band_is_uncapped_and_the_intervals_are_capped(out, name, axis):
    chart = out["profile"][name][axis]
    bands = _named(chart, r"^SD band$")
    assert bands and all(s["silent"] for s in bands)
    fills = [s for s in bands if s["items"][0]["el"]["type"] == "polygon"]
    edges = [s for s in bands if s["items"][0]["el"]["type"] == "polyline"]
    assert fills and len(edges) == 2 * len(fills), "each run of the band has its two long edges"
    # The edges carry the extent a reader must see: dashed, so neither reads as a cap or a line.
    assert all(i["el"]["dash"] and i["el"]["opacity"] >= 0.57 for s in edges for i in s["items"])
    for whiskers in (_named(chart, r"^95% t envelope$"), _named(chart, r"^Pooled ratio of sums 95% interval$")):
        assert len(whiskers) == 1
        items = whiskers[0]["items"]
        assert items and all(_points(i) in (2, 4, 6) for i in items)
        # Inside the axis both caps are drawn; a cap is dropped only where a caret marks the cut.
        assert sum(_points(i) == 6 for i in items) >= len(items) - 10
        assert all("95%" in i["tip"] for i in items)
    assert all("not the spread" in i["tip"] for i in _named(chart, r"^95% t envelope$")[0]["items"])


@pytest.mark.parametrize("name", PROFILES)
@pytest.mark.parametrize("axis", ["depth", "r"])
def test_every_listed_overflow_gets_a_caret_with_its_true_values(out, name, axis):
    chart = out["profile"][name][axis]
    ax = chart["ax"]
    carets = _named(chart, r"^SD band \(clipped\)$")
    assert len(carets) == 1
    assert len(carets[0]["items"]) == len(ax["band"]["over"]) + len(ax["band"]["under"])
    assert all(i["el"]["type"] == "polygon" and "true range" in i["tip"] for i in carets[0]["items"])
    env = ax["envelope"]
    expected = len(env["over"]) + len(env["under"])
    found = sum(len(s["items"]) for s in _named(chart, r"^95% t envelope \(clipped\)$"))
    assert found == expected


def test_a_single_shower_draws_its_own_profile_and_nothing_the_server_withheld(out):
    chart = out["profile"]["single"]
    names = {s["name"] for s in chart["series"]}
    assert "Per-shower mean" in names
    assert not any(n.startswith(("SD band", "95% t envelope", "Pooled ratio")) for n in names)
    assert "single shower, not an ensemble" in chart["strings"]
    assert "provisional" in chart["yAxis"][0]["name"]


def test_low_n_labels_are_written_as_the_payload_gives_them(out):
    chart = out["profile"]["weak"]
    assert "weak (N = 2) · 1 d.o.f." in chart["strings"]
    assert "provisional" in chart["yAxis"][0]["name"]


def test_an_empty_selection_draws_no_marks(out):
    chart = out["profile"]["empty"]
    assert chart["series"] == []
    assert "No showers in this selection." in chart["strings"]


@pytest.mark.parametrize("name", PROFILES)
def test_the_w_zero_rule_is_drawn_on_w_only(out, name):
    rule = r"^w = 0 — the shower’s entry point P₀$"
    depth = out["profile"][name]["depth"]
    assert bool(_named(depth, rule)) == (depth["key"] == "w")
    assert not _named(out["profile"][name]["r"], rule)


@pytest.mark.parametrize("name", PROFILES)
def test_the_profile_readout_names_every_mark_of_the_bin(out, name):
    chart = out["profile"][name]["depth"]
    (readout,) = _named(chart, r"^bin readout$")
    assert len(readout["items"]) == len(chart["ax"]["edges_cm"]) - 1
    tip = readout["items"][len(readout["items"]) // 2]["tip"]
    for label in ("Per-shower mean", "SD band (sample dispersion)", "95% t envelope of the mean", "Pooled ratio of sums"):
        assert label in tip


# ------------------------------------------------------- B1, B2, σ/μ --


@pytest.mark.parametrize("name", RESPONSES)
def test_b1_histograms_start_at_zero_with_no_band_over_them(out, name):
    """Every recorded B1 series is a robust histogram: as in the energy panel, no
    reserved band covers it. Its mean of the per-event fractions (long-dashed) and
    its 1/c (dotted) are verticals from the baseline, each with its 95% interval as
    a thin envelope, so the two estimators differ visibly; its SD is the histogram's
    own spread."""
    chart = out["response"][name]["b1"]
    assert chart["yAxis"][0]["min"] == 0 and chart["yAxis"][0]["labels"]
    assert chart["yAxis"][0]["name"] == "Probability density [%⁻¹]"
    assert not _named(chart, r"^reserved summary band$")
    assert not _named(chart, r"· (mean|SD band|mean 95% interval)$"), "no summary mark at a non-density height"
    payload = _load(name)
    rules = _named(chart, r"· 1/c \(Σ E / Σ p\)$")
    assert len(rules) == len(payload["b1"]["series"])
    assert all(any(c["text"] == "1/c (Σ E / Σ p)" for c in _children(i)) for s in rules for i in s["items"])
    for s in rules:
        (line,) = [c for c in _children(s["items"][0]) if c["type"] == "line"]
        assert line["line"]["y1"] == 0, "the rule rises from the baseline: no band below it"
    envelopes = _named(chart, r"· 1/c \(Σ E / Σ p\) · 95% interval$")
    assert len(envelopes) == len(rules)
    for s in envelopes:
        assert len(s["items"]) == 2 and all(i["el"]["type"] == "line" for i in s["items"])
        assert all("thin envelope" in i["tip"] and "95% interval" in i["tip"] for i in s["items"])
    means = _named(chart, r"· mean of f$")
    assert len(means) == len(payload["b1"]["series"]), "the mean is drawn beside 1/c"
    for s in means:
        (line,) = [c for c in _children(s["items"][0]) if c["type"] == "line"]
        assert line["line"]["y1"] == 0
        assert any(c["text"] == "mean f" for c in _children(s["items"][0]))
        assert "mean of the per-event fractions" in html.unescape(s["items"][0]["tip"])
    mean_envelopes = _named(chart, r"· mean of f · 95% interval$")
    assert len(mean_envelopes) == len(means)
    for s in mean_envelopes:
        assert len(s["items"]) == 2 and all("Student-t" in html.unescape(i["tip"]) for i in s["items"])
    for series in payload["b1"]["series"]:
        outline = [x for x in _named(chart, rf"^{re.escape(series['label'])}$") if x["z"] == 3][0]
        tip = html.unescape(outline["items"][0]["tip"])
        assert "mean of the per-event fractions" in tip and "Student-t" in tip and "σ = " in tip and "(SE)" in tip
        # The two estimators are two numbers, drawn at their own positions.
        (mean_rule,) = _named(chart, rf"^{re.escape(series['label'])} · mean of f$")
        (ratio_rule,) = _named(chart, rf"^{re.escape(series['label'])} · 1/c \(Σ E / Σ p\)$")
        assert mean_rule["items"][0]["value"][0] == pytest.approx(series["markers"]["mu"])
        assert ratio_rule["items"][0]["value"][0] == pytest.approx(series["reference"]["value"])


def test_b1_below_the_histogram_floor_draws_events_and_leaves_the_density_axis_unlabelled(out):
    chart = out["response"]["strip"]
    assert not chart["yAxis"][0]["labels"]
    assert chart["yAxis"][0]["name"] == "", "no estimable density: the axis carries no name and the plot says so"
    (band,) = _named(chart, r"^reserved summary band$")
    rect, rule, caption = _children(band["items"][0])
    assert (rect["type"], rule["type"], caption["type"]) == ("rect", "line", "text")
    assert rule["stroke"] == out["theme"]["muted"], "the band's edge is read: muted ink, not the 1.3:1 border"
    in_band = _named(chart, r"· (mean|SD band|mean 95% interval|1/c 95% interval)$")
    assert in_band and all("drawing offset" in i["tip"] for x in in_band for i in x["items"])
    for x in _named(chart, r"· SD band$"):
        assert all(i["el"]["type"] == "group" for i in x["items"]), "the SD band is an uncapped shaded bar"
        bar, top, bottom = _children(x["items"][0])
        assert bar["type"] == "rect" and top["dash"] and bottom["dash"], "dashed long edges, no end strokes"
    for x in _named(chart, r"· mean 95% interval$"):
        assert all(_points(i) == 6 for i in x["items"]), "a mean interval inside the axis is capped at both ends"
    assert any("No density estimate at this sample size" in t for t in chart["strings"])
    assert not any(s["name"] == "Shower" for s in chart["series"]), "no histogram is drawn below N = 15"
    (events,) = _named(chart, r"^Shower \(events\)$")
    assert len(events["items"]) == 5 and all("drawing offset" in i["tip"] for i in events["items"])
    (beyond,) = _named(chart, r"\(events beyond the axis\)$")
    assert "1 event(s) beyond the axis" in beyond["items"][0]["tip"]
    caption = _children(_named(chart, r"^reserved summary band$")[0]["items"][0])[2]["text"]
    assert caption.startswith("events and summary marks")


@pytest.mark.parametrize("name", RESPONSES)
def test_b2_draws_an_uncapped_sd_box_and_a_t_whisker_only_where_an_interval_exists(out, name):
    chart = out["response"][name]["b2"]
    payload = _load(name)
    y = payload["b2"]["y"]
    assert (chart["yAxis"][0]["min"], chart["yAxis"][0]["max"]) == (y["lo"], y["hi"]) and y["lo"] == 0
    for s in payload["b2"]["series"]:
        (boxes,) = _named(chart, rf"^{re.escape(s['label'])} · SD box$")
        assert boxes["silent"] and all(i["el"]["type"] == "rect" for i in boxes["items"])
        (whiskers,) = _named(chart, rf"^{re.escape(s['label'])} · 95% interval$")
        with_ci = [b for b in s["bins"] if b["ci95"] and not (b["ci95"][1] < y["lo"] or b["ci95"][0] > y["hi"])]
        assert len(whiskers["items"]) == len(with_ci)
        assert all(_points(i) in (2, 4, 6) for i in whiskers["items"])
        assert all("Student-t, capped whisker" in i["tip"] for i in whiskers["items"])
        (dots,) = _named(chart, rf"^{re.escape(s['label'])}$")
        inside = [b for b in s["bins"] if b["mean"] is not None and y["lo"] <= b["mean"] <= y["hi"]]
        assert len(dots["items"]) == len(inside)
        single = [b for b in inside if b["n"] < 2]
        assert sum(i["el"]["fill"] != i["el"]["stroke"] and i["el"]["stroke"] is not None for i in dots["items"]) == len(single)
    if y["n_clipped"]:
        assert _named(chart, r"\(clipped\)$")


def test_a_one_dof_interval_crossing_zero_is_cut_at_both_ends_with_carets(out):
    chart = out["response"]["response_single_hits"]["b2"]
    (whiskers,) = _named(chart, r"^Shower · 95% interval$")
    cut = [i for i in whiskers["items"] if _points(i) == 2]
    assert len(cut) == 1, "the N = 2 bin's interval [−9.25, 11.39] leaves the axis at both ends"
    assert "1 d.o.f." in cut[0]["tip"] and "−9.25" in cut[0]["tip"]
    carets = [i for s in _named(chart, r"^Shower \(clipped\)$") for i in s["items"]]
    assert sum("−9.25" in i["tip"] for i in carets) == 2


@pytest.mark.parametrize("name", RESPONSES)
@pytest.mark.parametrize("quantity", ["resolution", "ratio"])
def test_sigma_over_mu_carries_the_chi_squared_whisker_and_skips_empty_bins(out, name, quantity):
    chart = out["response"][name][quantity]
    payload = _load(name)
    kind = "calibrated_energy" if quantity == "resolution" else "response_ratio"
    shown = [s for s in payload["resolution"]["series"] if s["kind"] == kind]
    assert chart["legend"] == [s["label"] for s in shown]
    y = payload["resolution"]["y"]
    assert chart["yAxis"][0]["min"] == 0 and chart["yAxis"][0]["max"] == y["hi"]
    for s in shown:
        (dots,) = _named(chart, rf"^{re.escape(s['label'])}$")
        inside = [b for b in s["bins"] if b["value"] is not None and y["lo"] <= b["value"] <= y["hi"]]
        assert len(dots["items"]) == len(inside), "a bin of one shower has no σ/μ and draws nothing"
        (whiskers,) = _named(chart, rf"^{re.escape(s['label'])} · 95% interval$")
        assert whiskers["items"] and all("χ² interval of σ over μ" in i["tip"] for i in whiskers["items"])
        assert all("delta-method SE" in i["tip"] for i in whiskers["items"])


def test_a_provisional_range_says_so_on_the_axis(out):
    assert "provisional" in out["response"]["provisional"]["b2"]["yAxis"][0]["name"]
    assert "provisional" in out["response"]["provisional"]["resolution"]["yAxis"][0]["name"]
    assert "provisional" not in out["response"]["response_two"]["b2"]["yAxis"][0]["name"]


def test_the_shower_toggle_draws_one_shower(out):
    chart = out["response"]["response_two"]["showerA"]
    assert chart["legend"] == ["Shower A"]
    assert not any(s["name"].startswith("Shower B") for s in chart["series"])


@pytest.mark.parametrize("name", RESPONSES)
def test_no_response_text_uses_a_hyphen_for_a_minus(out, name):
    for mode in ("b1", "b2", "resolution", "ratio"):
        _no_hyphen_numbers(out["response"][name][mode]["strings"])
    _no_hyphen_numbers(out["response"]["strip"]["strings"])


# ------------------------------------------------------------------- B3 --


@pytest.mark.parametrize("name", B3)
def test_b3_draws_one_zero_based_subplot_per_slice_axis(out, name):
    chart = out["grid"][name]
    payload = _load(name)
    assert len(chart["grid"]) == len(payload["slice_axes"]) == len(chart["slices"])
    for k, sl in enumerate(chart["slices"]):
        x = chart["xAxis"][k]
        assert (x["min"], x["max"]) == (sl["axis"]["lo"], sl["axis"]["hi"])
        assert (x["name"] == "provisional") == bool(sl["axis"]["provisional"])
        assert chart["yAxis"][k]["min"] == 0
    titles = [t for t in chart["graphics"] if re.search(r"\bN(_[AB])?( =)? \d", t)]
    assert [t.split(" · ")[0].split(", ")[0].split(" (")[0] for t in titles] == [sl["label"] for sl in chart["slices"]]


@pytest.mark.parametrize("name", B3)
def test_b3_messages_come_from_texts_prefix_and_message(out, name):
    chart = out["grid"][name]
    texts = chart["texts"]
    for m in chart["messages"]:
        if m["draw"] == "histogram" and not m["degenerate"]:
            assert m["message"] is None
            continue
        key = "degenerate" if m["degenerate"] else m["draw"]
        n = f"{m['n']:,}"
        assert m["message"] == texts["prefix"].replace("{n}", n) + texts["message"][key]
        expected = m["estimator_note"] if m["estimator"] == "core_refit" else texts["estimator_note"][m["estimator"]]
        assert m["note"] == expected


@pytest.mark.parametrize("name", B3)
def test_b3_curve_and_histogram_follow_axis_grid(out, name):
    chart = out["grid"][name]
    payload = _load(name)
    for k, sl in enumerate(chart["slices"]):
        entries = [e for e in payload["series"] if e["slice"] == sl["index"]]
        lo, hi = sl["axis"]["lo"], sl["axis"]["hi"]
        cell = [s for s in chart["series"] if s["xAxisIndex"] == k]
        curves = [s for s in cell if s["z"] == 5 and s["items"] and s["items"][0]["el"]["type"] == "polyline"]
        with_curve = [e for e in entries if e["curve"]["y"]]
        assert len(curves) == len(with_curve), "a curve exactly where the server sent one"
        for s, e in zip(curves, with_curve):
            xs = [p[0] for p in s["items"][0]["el"]["pts"]]
            assert xs == pytest.approx(_linspace(lo, hi, len(e["curve"]["y"])))
        hists = [e for e in entries if e["draw"] == "histogram" and e["histogram"]]
        outlines = [s for s in cell if s["z"] == 3]
        assert len(outlines) == len(hists), "a histogram exactly where the server drew one"
        for s, e in zip(outlines, hists):
            xs = sorted({round(p[0], 9) for p in s["items"][0]["el"]["pts"]})
            assert xs == pytest.approx(_linspace(lo, hi, len(e["histogram"]["counts"]) + 1))


@pytest.mark.parametrize("name", B3)
def test_b3_thin_curves_never_set_the_axis_and_are_clipped_with_a_caret(out, name):
    chart = out["grid"][name]
    payload = _load(name)
    for k, sl in enumerate(chart["slices"]):
        entries = [e for e in payload["series"] if e["slice"] == sl["index"]]
        robust = [e for e in entries if e["drives_scale"]]
        y_max = chart["yAxis"][k]["max"]
        if robust:
            peaks = [max(e["histogram"]["counts"]) for e in robust if e["histogram"]]
            peaks += [e["curve_peak"] for e in robust if e["curve_peak"] is not None]
            # The robust peak with 15% headroom, rounded up to a 1-2-2.5-5 tick.
            assert 1.15 * max(peaks) <= y_max * (1 + 1e-9) <= 1.34 * 1.15 * max(peaks)
            mantissa = y_max / 10 ** math.floor(math.log10(y_max))
            assert any(abs(mantissa - m) < 1e-9 for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10))
        thin_over = [e for e in entries if not e["drives_scale"] and (e["curve_peak"] or 0) > y_max]
        carets = [s for s in chart["series"] if s["xAxisIndex"] == k and s["name"].endswith(" fit (clipped)")]
        assert len(carets) == len(thin_over)
        assert all("clipped: peak" in s["items"][0]["tip"] for s in carets)
        provisional = not robust and any(e["curve"]["y"] for e in entries)
        assert (chart["yAxis"][k]["name"] == "provisional") == provisional


@pytest.mark.parametrize("name", B3)
def test_b3_band_exists_only_where_a_low_n_series_needs_it(out, name):
    """As in the energy panel: a band only in a sub-plot holding a series below the
    histogram floor; every mark in it says its height is an offset."""
    chart = out["grid"][name]
    payload = _load(name)
    for k, sl in enumerate(chart["slices"]):
        entries = [e for e in payload["series"] if e["slice"] == sl["index"]]
        needs = any(e["draw"] != "histogram" and (e["strip"]["values"] or e["markers"]) for e in entries)
        bands = [x for x in chart["series"] if x["xAxisIndex"] == k and x["name"] == "reserved summary band"]
        assert len(bands) == int(needs), (sl["label"], "a band only where a low-N series needs it")
    bands = _named(chart, r"^reserved summary band$")
    assert all("not densities" in _children(b["items"][0])[2]["text"] for b in bands)
    assert all(_children(b["items"][0])[1]["stroke"] == out["theme"]["muted"] for b in bands)
    in_band = _named(chart, r"(\(events\)|· mean|· SD band)$")
    assert all("drawing offset" in i["tip"] for x in in_band for i in x["items"])
    low = [e for e in payload["series"] if e["draw"] != "histogram"]
    assert len(_named(chart, r"\(events\)$")) == sum(bool(e["strip"]["values"]) for e in low)
    assert len(_named(chart, r"· mean$")) <= sum(e["markers"] is not None for e in low)


@pytest.mark.parametrize("name", B3)
def test_b3_momentum_is_a_rule_with_its_interval_as_a_thin_envelope(out, name):
    """The slice's mean incident momentum is a reference on the energy axis, not a
    height: a dotted rule, its Student-t interval two hairlines, named in the tip."""
    chart = out["grid"][name]
    payload = _load(name)
    rules = _named(chart, r"mean incident momentum p$")
    assert rules
    for x in rules:
        line = [c for c in _children(x["items"][0]) if c["type"] == "line"][0]
        assert line["dash"] == [2, 3]
        assert line["line"]["x1"] == line["line"]["x2"], "a vertical rule"
    tips = [html.unescape(i["tip"]) for x in rules for i in x["items"]]
    assert all(payload["momentum_marker"]["mean"] in t for t in tips)
    assert any(payload["momentum_marker"]["ci95"]["label"] in t for t in tips)
    assert not any("drawing offset" in t for t in tips)
    for x in _named(chart, r"mean incident momentum p · 95% interval$"):
        assert all(i["el"]["type"] == "line" and not i["el"]["dash"] for i in x["items"])
        assert all("thin envelope" in i["tip"] for i in x["items"])


def test_b3_low_n_momentum_labels_reach_the_tooltip(out):
    chart = out["grid"]["b3_single_bins"]
    tips = [i["tip"] for s in _named(chart, r"mean incident momentum p$") for i in s["items"]]
    assert any("single shower (N = 1)" in t for t in tips)
    assert any("weak (N = 8)" in t and "c₄" in t for t in tips)


@pytest.mark.parametrize("name", B3)
def test_b3_layouts_fit_and_never_overlap(out, name):
    chart = out["grid"][name]
    fixed = out["grid"][name]["layoutFixed"]
    assert fixed["height"] <= 381
    for layout in (chart["layout"], fixed):
        cells = layout["cells"]
        for a in range(len(cells)):
            for b in range(a + 1, len(cells)):
                ca, cb = cells[a], cells[b]
                apart = (ca["left"] + ca["width"] <= cb["left"] or cb["left"] + cb["width"] <= ca["left"]
                         or ca["top"] + ca["height"] <= cb["top"] or cb["top"] + cb["height"] <= ca["top"])
                assert apart


def test_b3_prints_in_two_columns_at_single_column_width(out):
    layout = out["printGridLayout"]
    assert layout["cols"] == 2 and layout["rows"] == 8


@pytest.mark.parametrize("name", B3)
def test_no_b3_text_uses_a_hyphen_for_a_minus(out, name):
    _no_hyphen_numbers(out["grid"][name]["strings"])


# ------------------------------------------------------------------- C4 --


@pytest.mark.parametrize("name", DISTRIBUTIONS)
def test_distribution_colours_are_ordered_legible_stops(out, name):
    d = out["distribution"][name]
    chart = d["linear"]
    payload = _load(name)
    assert chart["legend"] == [s["label"] for s in payload["series"]]
    for k, s in enumerate(payload["series"]):
        outlines = [c for c in chart["series"] if c["name"] == s["label"]]
        assert outlines and all(i["el"]["stroke"] == d["stops"][k] for c in outlines for i in c["items"])
        dashed = all(i["el"]["dash"] == "dashed" for c in outlines for i in c["items"])
        assert dashed == (s["n_showers"] < 15)


@pytest.mark.parametrize("name", DISTRIBUTIONS)
def test_distribution_linear_counts_start_at_zero_and_close_there(out, name):
    chart = out["distribution"][name]["linear"]
    payload = _load(name)
    y = chart["yAxis"][0]
    assert y["min"] == 0 and y["type"] == "value"
    peak = max(max(s["counts"]) for s in payload["series"])
    assert y["max"] >= peak, "the count axis is set explicitly and holds every outline"
    for s in payload["series"]:
        (outline,) = [c for c in chart["series"] if c["name"] == s["label"]]
        pts = outline["items"][0]["el"]["pts"]
        assert pts[0][1] == 0 and pts[-1][1] == 0
        assert pts[0][0] == payload["edges"][s["offset"]]


@pytest.mark.parametrize("name", DISTRIBUTIONS)
def test_distribution_log_axis_states_its_floor_and_splits_at_empty_bins(out, name):
    chart = out["distribution"][name]["log"]
    payload = _load(name)
    y = chart["yAxis"][0]
    assert y["type"] == "log" and "log" in y["name"]
    positive = [v for s in payload["series"] for v in s["counts"] if v > 0]
    assert y["min"] <= min(positive)
    for s in payload["series"]:
        runs, inside = 0, False
        for v in s["counts"]:
            if v > 0 and not inside:
                runs += 1
            inside = v > 0
        outlines = [c for c in chart["series"] if c["name"] == s["label"]]
        assert len(outlines) == runs, "an empty bin splits the outline on a log axis"


def test_hit_energy_runs_on_a_log_axis_and_phi_on_its_full_period(out):
    energy = out["distribution"]["distribution_single_energy"]["linear"]
    assert energy["xAxis"][0]["type"] == "log"
    phi = out["distribution"]["distribution_single_phi"]["linear"]
    assert phi["xAxis"][0]["min"] == pytest.approx(-3.14159, abs=1e-5)
    assert phi["xAxis"][0]["max"] == pytest.approx(3.14159, abs=1e-5)
    assert "−π" in phi["strings"] and "π/2" in phi["strings"]
    payload = _load("distribution_single_phi")
    for s in payload["series"]:
        tips = [i["tip"] for c in phi["series"] if c["name"] == s["label"] for i in c["items"]]
        assert all(("R̄ =" in t) == (s["resultant"] is not None) for t in tips)


def test_counts_beyond_the_display_range_get_a_caret(out):
    chart = out["distribution"]["distribution_single_u"]["linear"]
    (carets,) = _named(chart, r"^beyond the display range$")
    assert len(carets["items"]) == 2
    assert all("counted per series, never dropped" in i["tip"] for i in carets["items"])
    assert not _named(out["distribution"]["distribution_single_phi"]["linear"], r"^beyond the display range$")


@pytest.mark.parametrize("name", DISTRIBUTIONS)
def test_no_distribution_text_uses_a_hyphen_for_a_minus(out, name):
    _no_hyphen_numbers(out["distribution"][name]["linear"]["strings"])
    _no_hyphen_numbers(out["distribution"][name]["log"]["strings"])


# ------------------------------------------------------------------- C8 --


@pytest.mark.parametrize("name", CORRELATIONS)
def test_correlation_draws_the_lower_triangle_with_circular_cells_hatched(out, name):
    chart = out["correlation"][name]
    variables = chart["variables"]
    k = len(variables)
    linear, other = chart["series"]
    # Columns are variables 0..k−2, rows 1..k−1: cell (row i, column j) sits at (j, i − 1).
    assert len(chart["xAxis"][0]["data"]) == k - 1
    assert len(chart["yAxis"][0]["data"]) == k - 1
    cells = [(x, y + 1) for s in (linear, other) for x, y, _ in (i["value"] for i in s["items"])]
    assert len(cells) == k * (k - 1) // 2
    assert all(x < y for x, y in cells), "lower triangle only, diagonal blank"
    circular = {i for i, v in enumerate(variables) if v["circular"]}
    assert circular
    for item in linear["items"]:
        x, y, _ = item["value"]
        assert x not in circular and y + 1 not in circular, "a circular variable is never on the colour scale"
    hatched = [i for i in other["items"] if i["value"][0] in circular or i["value"][1] + 1 in circular]
    assert hatched and all(i["decal"] and i["decal"]["rotation"] for i in hatched)
    assert all("no linear correlation" in i["tip"] for i in hatched)


@pytest.mark.parametrize("name", CORRELATIONS)
def test_correlation_scale_is_symmetric_with_signed_end_labels(out, name):
    chart = out["correlation"][name]
    (vm,) = chart["visualMap"]
    assert (vm["min"], vm["max"], vm["seriesIndex"]) == (-1, 1, 0)
    assert vm["text"] == ["+1.00", "−1.00"]
    assert "0" in chart["strings"], "the zero is marked at the ramp's midpoint"
    linear = chart["series"][0]
    for item in linear["items"]:
        r = item["value"][2]
        assert item["label"] == (f"{abs(r):.2f}" if r >= 0 or abs(r) < 0.005 else f"−{abs(r):.2f}")
        assert "95% interval" in item["tip"] and "N = " in item["tip"]


def test_cell_labels_contrast_with_the_cell_and_print_uses_standard_puor(out):
    assert min(out["correlation"]["labelContrast"]) >= 3.0
    assert out["correlation"]["palette"] == "puor_screen_linear"
    assert out["printPalette"] == "puor"


def test_mardia_r_is_quoted_on_a_hatched_cell_and_a_missing_interval_reads_untestable(out):
    chart = out["correlation"]["quoted"]
    other = chart["series"][1]
    quoted = [i for i in other["items"] if i["label"] == "R 0.21"]
    assert len(quoted) == 1 and "Mardia circular–linear R = 0.21" in quoted[0]["tip"]
    assert "null_R2" in quoted[0]["tip"]
    linear = chart["series"][0]
    assert any("not testable at this sample size" in i["tip"] for i in linear["items"])
    assert "interval untestable" in out["notes"]["correlationHazards"]


@pytest.mark.parametrize("name", CORRELATIONS)
def test_no_correlation_text_uses_a_hyphen_for_a_minus(out, name):
    _no_hyphen_numbers(out["correlation"][name]["strings"])
    _no_hyphen_numbers(out["printCorrelation"]["strings"])


# ------------------------------------------------------------ C1 + C9 --


@pytest.mark.parametrize("name", STATISTICS)
def test_statistics_rows_follow_describe_with_the_shifted_row_after_z(out, name):
    model = out["statistics"][name]["model"]
    payload = _load(name)
    describe = payload["describe"]
    keys = [r["key"] for r in model["rows"]]
    expected = [r["key"] for r in describe["rows"]]
    if describe["shifted_row"]:
        expected.insert(expected.index("z") + 1, describe["shifted_row"]["key"])
        assert any(r["label"] == "z − 3649 mm" and r["offset"] == 3649 for r in model["rows"])
    assert keys == expected
    assert all(len(r["cells"]) == 12 for r in model["rows"])
    assert [g["span"] for g in model["groups"]] == [8, 4]
    _no_hyphen_numbers(c for r in model["rows"] for c in r["cells"])
    if name.endswith("lab"):
        x = next(r for r in model["rows"] if r["key"] == "x")
        assert x["cells"][3].startswith("−"), "a negative minimum is set with U+2212"


@pytest.mark.parametrize("name", STATISTICS)
def test_the_negative_depth_block_quotes_showers_only_one_per_event(out, name):
    model = out["statistics"][name]["model"]
    block = _load(name)["negative_w"]
    neg = model["negative"]
    assert neg["summary"] == block["summary"]
    assert neg["perShower"] == (block["showers_per_event"] == 1)
    assert [r["key"] for r in neg["rows"]] == [s["key"] for s in block["splits"]]
    if not neg["perShower"]:
        assert all(r["showersWith"] == "—" for r in neg["rows"])
    lines = out["statistics"][name]["lines"]
    assert lines[0] == block["summary"]
    _no_hyphen_numbers(lines)


def test_negative_depth_lines_read_the_local_frame_block_and_the_unavailable_reason(out):
    assert out["statistics"]["local"][0].startswith("w < −10⁻⁶ mm:")
    assert out["statistics"]["unavailable"][0] == "Derived tables to rebuild."


# --------------------------------------------------------- shared rules --


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_every_series_colour_clears_three_to_one_against_its_card(out, theme):
    for name, ratios in out["contrast"][theme].items():
        assert min(ratios) >= 3.0, (theme, name, min(ratios))


def test_custom_whiskers_cap_each_item_and_drop_a_cut_cap(out):
    m = out["marks"]
    assert [len(p) for p in m["whiskers"]] == [6, 4], "the non-finite item is not drawn"
    assert m["whiskers"][0][0] == [-3, 2] and m["whiskers"][0][1] == [5, 2]
    assert m["whiskerTips"] == ["item 0", "item 1"]
    assert m["horizontal"][2] == [2, -10] and m["horizontal"][3] == [5, -10], "lifted by offsetPx"


def test_bin_hover_rects_span_the_bin_edges_and_the_plot_height(out):
    m = out["marks"]
    assert [(h["x"], h["width"]) for h in m["hover"]] == [(0, 1), (1, 1.5), (2.5, 1.5)]
    assert all(h["height"] == 100 for h in m["hover"])
    assert m["hoverTips"] == ["bin 0", "bin 1", "bin 2"] and m["hoverPosition"]
    assert m["hoverFill"] == "rgba(0,0,0,0)"


def test_chart_panel_delegates_and_relays_out_only_on_a_size_change(out):
    p = out["panel"]
    assert p["afterRender"] == ["init", "setOption"]
    assert p["afterSameSize"] == ["init", "setOption"], "an unchanged size repaints nothing"
    assert p["afterResize"] == ["init", "setOption", "resize", "setOption"]
    assert p["notMerge"] and p["liveGrid"]["left"] > 0
    assert p["lastOptsKeys"] == ["palette"], "the tooltip placements are injected at paint, never stored"
    assert p["positions"] and p["kind"] == "profile"
    assert p["hiddenPaints"] == 0, "a hidden card is not painted"
    assert p["cleared"] == {"payload": None, "grid": None, "clearCalled": True}
    assert p["busy"]
    assert p["kinds"] == {"ResponsePanel": "response", "ResponseGridPanel": "response-grid",
                          "DistributionPanel": "distribution", "CorrelationPanel": "correlation"}
    assert p["modeOption"].startswith("Sampling fraction") and p["modeOverride"].startswith("Relative resolution")
    assert p["exportMetrics"]["width"] == 321 and p["exportMetrics"]["height"] > 100


def test_the_grid_panel_sizes_itself_from_its_rows(out):
    p = out["panel"]
    assert p["gridHeight"].endswith("px") and int(p["gridHeight"][:-2]) > 380
    assert p["gridExport"]["width"] == 321


def test_print_rebuilds_carry_no_tooltip_placement(out):
    tooltip = out["printProfileTooltip"]
    assert "position" not in tooltip and tooltip["confine"] is False and tooltip["appendTo"] == "#tooltip-layer"


# --------------------------------------------------------------- notes --


NOTE_HEADINGS = ["Selection", "What is drawn", "Disclosures", "Marks and legend"]


def test_the_section_names_are_unchanged(out):
    assert out["notes"]["section"] == {
        "selection": "Selection", "drawn": "What is drawn", "disclosures": "Disclosures",
        "legend": "Marks and legend", "density": "Reading the density axis",
    }
    assert out["notes"]["notesExported"] == ["x"]


@pytest.mark.parametrize("key,title", [
    ("profileW", "Longitudinal Profile along w"),
    ("profileNative", "Longitudinal Profile (native layers)"),
    ("profileR", "Radial Profile"),
    ("response_b1", "Sampling Fraction — Per-Event Distribution"),
    ("response_b2", "Sampling Fraction vs. Incident Momentum"),
    ("response_resolution", "Relative Resolution σ/μ vs. Incident Momentum"),
    ("b3", "Response vs. Incident Momentum p"),
    ("energyMomentum", "Response vs. Incident Momentum p"),
    ("distribution", "Distributions by Momentum Bin"),
    ("correlation", "Hit-level Pearson Correlation"),
    ("correlationD3", "Feature correlation"),
    ("statistics", "Selection Statistics — describe()"),
])
def test_each_physics_card_has_its_title_and_the_four_sections(out, key, title):
    notes = out["notes"][key]
    assert notes["title"] == title
    # The four every drawer shares come first, in order; a card's own sections follow.
    assert list(notes["headings"][:len(NOTE_HEADINGS)]) == list(NOTE_HEADINGS)
    assert notes["sections"]["Selection"][0].startswith("Experiment Demo")
    for lines in notes["sections"].values():
        _no_hyphen_numbers(lines)


def test_the_separation_view_keeps_its_title(out):
    assert out["notes"]["energyD"]["title"] == "Reconstructed Energy vs. Separation D"


def test_response_notes_keep_their_own_part_and_drop_the_others(out):
    b1 = " ".join(out["notes"]["response_b1"]["sections"]["What is drawn"])
    b2 = " ".join(out["notes"]["response_b2"]["sections"]["What is drawn"])
    assert "mean of ratios" in b1 and "mean of ratios" not in b2
    assert "integer momentum bin" in b2 and "integer momentum bin" not in b1
    assert not any(line.startswith(("B1:", "B2:", "Resolution:")) for line in
                   out["notes"]["response_b1"]["sections"]["What is drawn"])


def test_the_profile_drawer_counts_what_the_chart_clipped(out):
    disclosures = " ".join(out["notes"]["profileW"]["sections"]["Disclosures"])
    payload = _load("profiles_single_w")
    clipped = payload["axes"]["w"]["y"]["clipped"]
    assert f"{clipped['band']} SD-band bins above the axis" in disclosures
    assert f"{clipped['band_below_zero']} SD-band bins below zero" in disclosures
    assert "Comb lag-1" in disclosures


def test_the_b3_drawer_states_each_disclosure_once(out):
    """The route's warnings name the values beyond each axis, the provisional axes,
    the empty slices and the showers in no slice; the drawer does not repeat them."""
    disclosures = " ".join(out["notes"]["b3"]["sections"]["Disclosures"])
    assert "5–6 GeV: 4" in disclosures and "22 of 572 values lie beyond their slice's axis" in disclosures
    assert disclosures.count("5–6 GeV: 4") == 1
    single = " ".join(out["notes"]["b3Single"]["sections"]["Disclosures"])
    assert "No showers in this selection fall in: 6–7 GeV" in single and "No showers in: " not in single
    assert single.count("6–7 GeV") == 1
    assert "No series reaches the 15-shower histogram floor" in single and "Provisional energy axes" not in single
    notebook = " ".join(dict(out["notes"]["b3Notebook"])["Disclosures"])
    assert notebook.count("143 showers") == 1, "143 showers in no slice, said once"
    # A payload without the route's warnings states the same facts from its fields, each shower named.
    fallback = " ".join(dict(out["notes"]["b3Fallback"])["Disclosures"])
    assert "2 showers (A) fall in no slice" in fallback and "3 showers (B) fall in no slice" in fallback
    assert "5–6 GeV:" in fallback
    assert out["notes"]["b3"]["headings"][-1] == "Reading the density axis"


def test_circular_and_weighting_sections_appear_where_they_apply(out):
    assert "Circular quantities" in out["notes"]["correlation"]["headings"]
    assert "Weightings" in out["notes"]["correlation"]["headings"]
    assert "Circular quantities" in out["notes"]["distributionPhi"]["headings"]
    assert "Circular quantities" not in out["notes"]["distribution"]["headings"]
    assert "Estimators" in out["notes"]["statistics"]["headings"]
    assert "Hits behind the entry plane" in out["notes"]["statistics"]["headings"]


def test_physics_hazards_are_structural(out):
    h = out["notes"]["hazards"]
    assert h["profileSingle"][:2] == ["single shower", "provisional range"]
    assert h["profileR"] == ["energy beyond the profile range"]
    assert h["b1"] == []
    assert h["b2"] == ["low-statistics bins", "marks clipped at the axis"]
    assert h["res"] == ["low-statistics bins", "marks clipped at the axis"]
    assert h["b3"] == ["low-statistics series", "provisional range"]
    assert h["b3Two"] == ["low-statistics series", "clipped energy range"]
    assert h["distribution"] == ["clipped range"] and h["distributionPhi"] == []
    assert h["correlation"] == ["circular variable"]
    assert h["statistics"] == []
    assert h["energyUnchanged"] == ["low-statistics series"]
    assert h["generic"] == ["sampled preview", "measured comb"]


# -------------------------------------------------------------- source --


NEW_MODULES = ["chart_panel.js", "profile.js", "response.js", "response_grid.js",
               "distribution.js", "correlation.js", "statistics.js"]
CHART_MODULES = ["profile.js", "response.js", "response_grid.js", "distribution.js", "correlation.js"]


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", source)


@pytest.mark.parametrize("module", NEW_MODULES)
def test_new_panel_modules_build_no_html_into_the_page_and_never_confine_a_tooltip(module):
    source = _strip_comments((PANELS / module).read_text(encoding="utf-8"))
    for forbidden in ("innerHTML", "insertAdjacentHTML", "rgba(22,27,34,0.95)"):
        assert forbidden not in source, (module, forbidden)
    assert not re.search(r"confine:\s*true", source)
    assert not re.search(r"getElementById\('", source), "ids come from the caller, never a literal"
    assert "transition" not in source


@pytest.mark.parametrize("module", CHART_MODULES)
def test_every_chart_takes_its_tooltip_from_tooltip_js(module):
    source = _strip_comments((PANELS / module).read_text(encoding="utf-8"))
    assert "tooltipOption(opts.tooltipPosition ?? null)" in source
    assert "from './tooltip.js'" in source
    # ... and wraps the server's prose, which on one line ran off the window.
    assert "wrapTooltip(tooltipOption(opts.tooltipPosition ?? null))" in source


def test_only_a_short_readout_stays_beside_the_pointer():
    """The B1 and B3 bin readouts (a bin's density per series) sit beside the pointer;
    the profile, B2 and resolution bin summaries and the per-bin count list of the
    distribution are explanations, measured at up to 67% of the plot, and leave it."""
    uses = {name: _strip_comments((PANELS / name).read_text(encoding="utf-8")).count("opts.readoutPosition")
            for name in ("profile.js", "response.js", "response_grid.js", "distribution.js", "correlation.js")}
    assert uses == {"profile.js": 0, "response.js": 1, "response_grid.js": 1, "distribution.js": 0,
                    "correlation.js": 0}, uses


def test_every_physics_tooltip_wraps_its_prose(out):
    tips = [out["profile"]["profiles_single_w"]["depth"]["tooltip"],
            out["response"]["response_two"]["b1"]["tooltip"],
            out["response"]["response_two"]["b2"]["tooltip"],
            out["response"]["response_two"]["resolution"]["tooltip"],
            out["grid"]["b3_two_truth"]["tooltip"],
            out["distribution"]["distribution_two_p"]["linear"]["tooltip"],
            out["correlation"]["correlation_two_lab"]["tooltip"]]
    for tip in tips:
        css = tip["extraCssText"]
        assert "white-space: normal" in css and "max-width: min(400px, calc(100vw - 16px))" in css, css
        assert tip["appendTo"] == "#tooltip-layer" and tip["confine"] is False


def test_b3_with_no_shower_in_any_slice_says_so_without_a_density_axis(out):
    empty = out["grid"]["empty"]
    assert empty["graphics"] == ["No showers of this selection fall in any momentum slice."]
    assert empty["layout"]["height"] < 200 and empty["layout"]["cells"] == []
    no_density = out["grid"]["noDensity"]["graphics"]
    assert "no density estimate" in no_density
    assert not any("Probability density" in g for g in no_density)
    assert any("Probability density" in g for g in out["grid"]["b3_two_truth"]["graphics"])


def test_the_chart_panel_base_carries_the_shared_machinery():
    source = _strip_comments((PANELS / "chart_panel.js").read_text(encoding="utf-8"))
    for token in ("new ResizeObserver(", "requestAnimationFrame", "this.liveGrid = option.grid",
                  "this.tooltipPosition = tooltipPosition(this.chart", "hideTooltipOnScroll(this.chart)",
                  "{ notMerge: true }"):
        assert token in source, token


def test_rounded_tops_land_on_a_tick_and_waste_at_most_a_third(out):
    for row in out["nice"]:
        top, step = row["top"], row["interval"]
        assert row["v"] <= top <= 1.34 * row["v"]
        ticks = top / step
        assert abs(ticks - round(ticks)) < 1e-9 and 3 <= round(ticks) <= 5


@pytest.mark.parametrize("name", RESPONSES)
def test_the_b1_density_axis_ends_on_a_tick(out, name):
    y = out["response"][name]["b1"]["yAxis"][0]
    assert y["min"] == 0 and y["max"] > 0


def test_the_distribution_readout_lists_every_non_empty_series_by_colour(out):
    chart = out["distribution"]["distribution_single_phi"]["linear"]
    (readout,) = _named(chart, r"^bin readout$")
    tips = [i["tip"] for i in readout["items"]]
    assert all(t.startswith("<b>φ ") for t in tips)
    assert any("series empty in this bin" in t for t in tips)
    stops = out["distribution"]["distribution_single_phi"]["stops"]
    assert any(stops[0] in t for t in tips)


def test_the_card_title_heads_the_drawer_except_a_native_depth_profile(out):
    assert out["notes"]["cardTitles"] == {
        "radial": "Radial Profile along ρ",
        "native": "Longitudinal Profile (native layers)",
        "distribution": "Card title",
        "b3": "Card B3",
    }


# ------------------------------------------------------ Phase 6 review fixes --


def _visible(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(text)))


@pytest.mark.parametrize("name", B3)
def test_b3_fit_table_reports_mu_and_sigma_with_their_uncertainty(out, name):
    """The drawer's "reported in the table" is true: every slice in order, one row per
    series drawn, σ with its SE and below the core-refit floor its χ² interval and c₄."""
    payload = _load(name)
    rows = out["grid"]["tables"][name]["rows"]
    labels = [r["slice"] for r in rows]
    assert list(dict.fromkeys(labels)) == [s["label"] for s in payload["slices"]], "every slice, in order"
    core = payload["thresholds"]["core"]
    for r in rows:
        if r.get("empty"):
            continue
        assert r["n"] >= 1 and r["estimator"] and r["mu"] is not None
        if r["n"] < core and r["sigma"] is not None:
            assert r["sigma_ci95"] and r["c4"] is not None, (r["slice"], "below the floor σ never goes bare")
        if r["n"] >= core:
            assert r["sigma_ci95"] is None and r["c4"] is None
    table = out["grid"]["tables"][name]["table"]
    assert table["columns"] == ["Momentum slice", "N", "μ ± SE [GeV]", "σ ± SE [GeV]", "σ/μ", "Estimator", "Shape"]
    _no_hyphen_numbers([c["text"] for row in table["rows"] for c in row["cells"]] + [row.get("momentum") or "" for row in table["rows"]])


def test_b3_fit_table_cells_for_a_two_event_slice(out):
    (row,) = [r for r in out["grid"]["tables"]["b3_single_bins"]["table"]["rows"] if r["name"].startswith("7–8 GeV")]
    sigma = row["cells"][2]
    assert sigma["text"] == "8.663" and sigma["uncert"] == "± 6.126"
    assert sigma["sub"] == "χ² 95% 3.865 … 276.446 · c₄ = 0.798"
    (single,) = [r for r in out["grid"]["tables"]["b3_single_bins"]["table"]["rows"] if r["name"].startswith("3–4 GeV")]
    assert single["cells"][2]["text"] == "—" and single["cells"][2]["uncert"] == "no width from one event"
    empty = [r for r in out["grid"]["tables"]["b3_single_bins"]["table"]["rows"] if r.get("empty")]
    assert [r["name"] for r in empty][:2] == ["6–7 GeV", "8–9 GeV"]


@pytest.mark.parametrize("name", ["b3_single_bins", "b3_two_truth", "b3_single_notebook"])
def test_b3_table_is_built_from_text_nodes_into_the_callers_host(out, name):
    table = out["table"][name]
    assert table["tag"] == "table" and table["className"] == "fit-table"
    assert table["head"] == ["Momentum slice", "N", "μ ± SE [GeV]", "σ ± SE [GeV]", "σ/μ", "Estimator", "Shape"]
    assert len(table["rows"]) == table["tableRows"]
    series_rows = [r for r in table["rows"] if r["swatch"]]
    assert series_rows and all(r["swatch"].startswith("#") for r in series_rows)
    _no_hyphen_numbers([c for r in table["rows"] for c in r["cells"]])
    assert out["table"]["emptyHost"] == 0 and out["table"]["emptySparse"] == []


def test_b3_sparse_lines_give_the_key_counts(out):
    notebook = " ".join(out["grid"]["tables"]["b3_single_notebook"]["sparse"])
    assert "Low-statistics series — 2 below N = 15" in notebook and "3 below N = 8" in notebook
    assert "143 showers of this selection fall in no slice" in notebook
    assert "5 energy axes are provisional" in notebook
    two = " ".join(out["grid"]["tables"]["b3_two_truth"]["sparse"])
    assert "22 of 572 values lie beyond their slice's energy axis" in two and "5–6 GeV: 4" in two
    assert "counted over both showers" in " ".join(out["grid"]["sparseA"])
    assert "counted over both showers" not in two
    for name in B3:
        _no_hyphen_numbers(out["grid"]["tables"][name]["sparse"])


def test_a_fixed_host_states_the_slices_it_cannot_draw(out):
    counts = out["table"]["fixedCounts"]
    assert counts["hidden"] > 0 and counts["shown"] + counts["hidden"] == 10
    assert any("slices fit the plot at this height" in line for line in out["table"]["fixedSparse"])
    assert any("in the fit table" in g or "in the table" in g for g in out["grid"]["hiddenChart"]["graphics"])
    assert any("the other 4 are in the table" in line for line in out["grid"]["hiddenSparse"])


def test_a_fixed_host_tells_the_page_when_the_slices_it_hides_change(out):
    told = out["table"]["onLayout"]
    # Hidden at 450 x 330: told once; the same size again: nothing new; grown to fit: told again.
    assert (told["afterRender"], told["afterSame"], told["afterGrow"]) == (1, 1, 2), told
    assert told["hidden"] == 0, told
    assert not any("at this height" in line for line in told["sparse"]), told
    # A self-sizing card hides nothing and has nothing to say.
    assert told["selfSizing"] == 0, told


def test_b3_fixed_heights_never_draw_a_subplot_off_the_canvas(out):
    for row in out["grid"]["sweep"]:
        assert row["shown"] + row["hidden"] == row["n"] and row["cells"] == row["shown"] >= 1
        assert row["bottom"] <= row["layoutHeight"] + 1e-6 <= row["height"] + 1e-6, row
        assert row["minPlot"] >= 70 - 1e-6, row
        assert (row["notice"] is not None) == (row["hidden"] > 0), row
    six = [r for r in out["grid"]["sweep"] if r["n"] == 6 and r["width"] >= 400 and r["height"] >= 300]
    assert six and all(r["hidden"] == 0 for r in six), "plot 4's six notebook windows fit the 2 × 2 cell"


def test_b3_titles_count_the_showers_drawn(out):
    assert "2–3 GeV · N_A = 18" in out["grid"]["titlesA"]
    assert "2–3 GeV · N_A = 18, N_B = 16" in out["grid"]["titlesBoth"]
    assert not any(re.search(r"N = 34\b", t) for t in out["grid"]["titlesA"] + out["grid"]["titlesBoth"])


@pytest.mark.parametrize("name", ["b3_single_notebook", "b3_single_bins", "b3_two_truth"])
def test_single_column_b3_text_stays_inside_the_figure_with_its_full_count(out, name):
    texts = out["printGridTexts"][name]
    for t in texts:
        left = t["x"] - (t["width"] / 2 if t["align"] == "center" else 0)
        assert left >= 0 and left + t["width"] <= 321 + 1e-6, t
    payload = _load(name)
    counts = payload["slice_counts"]
    titles = [t["text"] for t in texts if re.search(r"\bN(_[AB])?( =)? \d", t["text"])]
    axes = {a["slice"] for a in payload["slice_axes"]}
    for s in (s for s in payload["slices"] if s["index"] in axes):
        n = counts[str(s["index"])]
        by = payload["slice_counts_by_shower"]
        whole = [f"{n:,}"] if by.get("b") is None else [f"{by['a'][str(s['index'])]:,}", f"{by['b'][str(s['index'])]:,}"]
        assert any(all(re.search(rf"(?<!\d){w}(?!\d)", t) for w in whole) for t in titles), (s["label"], whole)


def test_b1_strip_rows_quote_sigma_with_its_se_chi_squared_interval_and_c4(out):
    chart = out["response"]["strip"]
    tips = [_visible(i["tip"]) for x in _named(chart, r"· (SD band|mean)$") for i in x["items"]]
    assert tips and all("(SE)" in t and "χ² 95% interval" in t and "c₄(N) = 0.9515" in t for t in tips)
    drawn = " ".join(out["notes"]["b1Strip"]["What is drawn"])
    assert "χ² 95% interval" in drawn and "c₄(N) = 0.9515" in drawn
    assert "bar heights" not in drawn, "no bar is drawn, so the bar-height note is left out"
    legend = " ".join(out["notes"]["b1Strip"]["Marks and legend"])
    assert "carries no name and no scale" in legend and "left unlabelled" not in legend


def test_b3_strip_rows_quote_sigma_with_its_interval_and_c4(out):
    tips = [_visible(t) for t in out["grid"]["stripTips"] if "7–8 GeV" in t]
    assert tips and all("χ² 95% interval 3.865 GeV … 276.446 GeV" in t and "c₄(N) = 0.7979" in t for t in tips)


def test_b1_drawer_quotes_the_numbers_a_histogram_does_not_draw(out):
    sections = dict(out["notes"]["b1Two"])
    drawn = " ".join(sections["What is drawn"])
    assert "Shower A: mean of the per-event fractions 0.718%" in drawn and "(SE)" in drawn
    assert "bar heights are counts" in drawn
    legend = " ".join(sections["Marks and legend"])
    assert "thin envelope" in legend and "no band covers" in legend
    assert "long-dashed one is the mean of the per-event fractions" in legend and "two different numbers" in legend


def test_b2_sd_boxes_take_half_a_bin_each_and_carry_a_dashed_edge(out):
    chart = out["response"]["response_two"]["b2"]
    a = _named(chart, r"^Shower A · SD box$")[0]["items"]
    b = _named(chart, r"^Shower B · SD box$")[0]["items"]
    assert a and b
    assert all(abs(i["value"][0] - math.floor(i["value"][0])) < 1e-9 for i in a), "A takes the left half"
    assert all(abs(i["value"][0] - math.floor(i["value"][0]) - 0.5) < 1e-9 for i in b), "B takes the right half"
    for i in a + b:
        assert i["el"]["dash"] == [2, 2] and i["el"]["strokeOpacity"] >= 0.57 and i["el"]["fillOpacity"] <= 0.18
    single = _named(out["response"]["response_two"]["showerA"], r"^Shower A · SD box$")[0]["items"]
    assert all(abs(i["value"][0] - round(i["value"][0])) < 1e-9 for i in single)


def test_b2_calibration_rule_carries_its_interval_as_a_capped_whisker(out):
    lo, hi = out["response"]["calInterval"]
    assert lo == pytest.approx(100 / 149.904, rel=1e-4) and hi == pytest.approx(100 / 126.764, rel=1e-4)
    chart = out["response"]["response_two"]["b2"]
    for shower in ("A", "B"):
        (whisker,) = _named(chart, rf"^Shower {shower} · 1/c 95% interval$")
        assert len(whisker["items"]) == 1 and _points(whisker["items"][0]) == 6
        tip = _visible(whisker["items"][0]["tip"])
        assert "95% interval" in tip and "capped whisker" in tip
    tip = _visible(_named(chart, r"^Shower A · 1/c \(selection\)$")[0]["items"][0]["tip"])
    assert "95% interval 0.667 … 0.789%" in tip


def test_b2_tooltips_quote_the_sd_standard_error(out):
    assert "SD = 0.471% ± 0.081% (SE)" in _visible(out["response"]["b2Tips"][0])


def test_resolution_with_no_estimable_bin_says_why_without_a_scale(out):
    chart = out["response"]["resEmpty"]
    assert chart["graphics"] == ["No momentum bin holds two showers: σ/μ is not estimable (N = 1 in every bin)."]
    assert chart["series"] == [] and chart["legend"] == []
    assert all(not a["labels"] and a["name"] == "" for a in chart["xAxis"] + chart["yAxis"])
    assert any("No drawn bin holds two showers" in line for line in out["response"]["resEmptyNotes"])


def test_resolution_legend_names_only_series_that_draw(out):
    for name in RESPONSES:
        payload = _load(name)
        drawn = [s["label"] for s in payload["resolution"]["series"] if s["kind"] == "calibrated_energy"
                 and any(b["value"] is not None for b in s["bins"])]
        assert out["response"][name]["resolution"]["legend"] == drawn


def test_a_wrapped_print_legend_grows_the_grid_top(out):
    for mode, row in out["printResponse"].items():
        assert row["top"] == pytest.approx(row["pad"] + max(1, row["rows"]) * 1.6 * row["font"]), mode
    assert out["printResponse"]["resolution"]["rows"] >= 2


def _contrast(rgb, bg):
    def lum(c):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
    hi, lo = sorted((lum(rgb), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hex(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def test_translucent_ink_clears_three_to_one_on_screen_and_in_print(out):
    for theme in ("screenInk", "printInk"):
        for key, rows in out[theme].items():
            for row in rows:
                assert row["contrast"] >= 3 - 1e-9, (theme, key, row)
                assert row["alpha"] >= row["wanted"] - 1e-9
    # Measured independently: shower B's blue at the alpha chosen over the #1c2128 card.
    card = _hex("#1c2128")
    blue = _hex(out["theme"]["showerB"])
    alpha = [r for r in out["screenInk"]["showerB"] if r["wanted"] == 0.45][0]["alpha"]
    blended = tuple(alpha * c + (1 - alpha) * k for c, k in zip(blue, card))
    assert _contrast(blended, card) >= 3


def test_b3_outlines_and_legend_controls_are_legible(out):
    for name in B3:
        chart = out["grid"][name]
        for x in chart["series"]:
            if x["z"] == 3 and x["items"] and x["items"][0]["el"] and x["items"][0]["el"]["type"] == "polyline":
                assert x["items"][0]["el"]["opacity"] >= 0.57, (name, x["name"])
    charts = [out["grid"]["b3_two_truth"], out["response"]["response_two"]["b2"], out["distribution"]["distribution_two_p"]["linear"],
              out["profile"]["profiles_two_w"]["depth"]]
    for chart in charts:
        style = chart["legendStyle"]
        assert style["pageIconColor"] == out["theme"]["text"]
        assert style["pageIconInactiveColor"] == out["theme"]["border"]
        assert style["pageTextColor"] == out["theme"]["muted"]
        assert _contrast(_hex(style["pageIconColor"]), _hex(out["theme"]["card"])) >= 3
        assert _contrast(_hex(style["pageTextColor"]), _hex(out["theme"]["card"])) >= 3


def test_the_pooled_two_shower_profile_is_not_shower_b_blue(out):
    ink = out["profileInk"]
    assert ink["two"]["colour"] == out["theme"]["text"] != out["theme"]["showerB"]
    assert ink["two"]["pooledColour"] == out["theme"]["muted"]
    assert ink["twoA"]["colour"] == out["theme"]["showerA"]
    assert ink["single"]["colour"] == out["theme"]["accent"]
    mean = _named(out["profile"]["profiles_two_w"]["depth"], r"^Per-shower mean$")
    assert mean and all(i["el"]["stroke"] == out["theme"]["text"] for x in mean for i in x["items"])


def test_the_weak_correlation_label_sits_in_the_empty_upper_triangle(out):
    (label,) = out["correlation"]["weakLabel"]["graphic"]
    grid = out["correlation"]["weakLabel"]["grid"]
    assert label["text"] == "weak: 2 events" and label["textAlign"] == "right"
    assert label["x"] == pytest.approx(grid["left"] + grid["width"] - 4)
    assert label["y"] == pytest.approx(grid["top"] + 4)


@pytest.mark.parametrize("name", DISTRIBUTIONS)
def test_the_linear_count_axis_tops_out_on_the_fine_ladder(out, name):
    payload = _load(name)
    peak = max(v for s in payload["series"] for v in (s.get("counts") or s.get("density") or []) if v is not None)
    top = out["distribution"][name]["linear"]["yAxis"][0]["max"]
    assert 1.05 * peak <= top * (1 + 1e-9) <= 1.34 * 1.05 * peak


def _drawn_clipped(series, y, key, sd=False):
    n = 0
    for s in series:
        for b in s["bins"]:
            v = b.get(key)
            if v is None:
                continue
            ci = b.get("ci95") or [None, None]
            cut = v < y["lo"] or v > y["hi"]
            cut = cut or (ci[0] is not None and ci[0] < y["lo"]) or (ci[1] is not None and ci[1] > y["hi"])
            if sd and b.get("sd") is not None:
                cut = cut or v - b["sd"] < y["lo"] or v + b["sd"] > y["hi"]
            n += cut
    return n


def test_the_drawer_counts_only_the_marks_the_card_draws(out):
    payload = _load("response_single_hits")
    shown = [s for s in payload["resolution"]["series"] if s["kind"] == "calibrated_energy"]
    clipped = _drawn_clipped(shown, payload["resolution"]["y"], "value")
    assert clipped == 4, "the reviewer's four carets on the default card"
    sections = dict(out["notes"]["resSingle"])
    assert f"{clipped} drawn bins draw a mark beyond it" in " ".join(sections["Disclosures"])
    assert not any(re.match(r"\d+ bins? with N < 20", line) for line in sections["What is drawn"])
    two = _load("response_two")
    for shower in ("a", "b", "both"):
        series = [s for s in two["resolution"]["series"] if s["kind"] == "calibrated_energy"
                  and (shower == "both" or s["key"] == shower)]
        n = _drawn_clipped(series, two["resolution"]["y"], "value")
        text = " ".join(out["notes"]["resCounts"][shower])
        expected = {0: "No drawn mark leaves it.", 1: "1 drawn bin draws a mark"}.get(n, f"{n} drawn bins draw a mark")
        assert expected in text, (shower, n, text)
    # The Details flag follows the card too: shower A alone draws no clipped mark.
    assert "marks clipped at the axis" not in out["notes"]["resHazards"]["a"]
    assert "marks clipped at the axis" in out["notes"]["resHazards"]["both"]
    b2 = dict(out["notes"]["b2Single"])
    n = _drawn_clipped(payload["b2"]["series"], payload["b2"]["y"], "mean", sd=True)
    assert f"{n} drawn bin" in " ".join(b2["Disclosures"])


def test_the_hatch_has_its_own_token_on_screen_and_in_print(out):
    assert out["screenHatch"] == "#8b949e" and out["printHatch"] == "#6b7280"
    scale_src = (JS / "scale.js").read_text(encoding="utf-8")
    tokens_src = (JS / "export" / "tokens.js").read_text(encoding="utf-8")
    assert re.search(r"hatch: '#8b949e'", scale_src)
    ink = re.search(r"export const PRINT_INK = \{(.*?)\};", tokens_src, re.DOTALL).group(1)
    assert "hatch" not in ink, "the hatch is chrome, not ink"
    assert re.search(r"hatch: '#6b7280'", tokens_src)
