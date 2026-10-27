"""The models page's 2-D panels, executed under Node on the recorded payloads.

Every option builder of the Page 2 2-D cards is a pure function - E2's
`perfBinsOption`, pred-truth and D5's `hist2dOption`, the residual and D4 modes
of `distribution.js`, D3 through `correlationOption`, C11's `ratesOption` - and
D2's `featureRows` is the pure part of a table. The script runs each against the
payloads `tests/test_payload_fixtures.py` recorded (`tests/fixtures/payloads/`),
renders every custom series' `renderItem` with an identity coordinate map,
calls every tooltip formatter and hands back what was drawn. The tests then
hold each card to CLAUDE.md section 2:

* a capped whisker is the interval of the plotted statistic, named so in its
  tooltip; a sample SD is an uncapped bar; the spread is never a whisker;
* bars and density axes start at zero, a fraction runs 0-100 %;
* marks at heights that are not densities sit in a tinted, captioned band and
  every tooltip there says so;
* a mark beyond its range is clipped with a caret carrying its true value;
* azimuth cells are hatched and never on the colour scale; parity r has no
  interval;
* nothing the payload withholds is drawn (no histogram below N = 15, no curve
  below N = 8, no raster below 15 pairs, no whisker without an interval);
* every colour a reader must see clears 3:1 against the card, on screen and in
  print, and no rendered number uses an ASCII hyphen.

Low-N and clipped variants are built from recorded payloads by changing only
the fields the server would change. The drawer notes (`models_notes.js`) and
the panel classes' delegation are checked too. Skipped without `node`.
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
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

PERF = ["perf_two_energy", "perf_two_angle"]
PRED = ["pred_density_two_energy", "pred_density_two_angle"]
HISTS = ["features_single_hist", "features_single_hist_phi"]
CORRS = ["features_single_corr", "features_two_corr"]
DESCRIBE = ["features_single_describe", "features_events_describe"]
PALETTES = ["viridis", "cividis", "plasma", "turbo"]

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
const perf = await imp('panels/perf_bins.js');
const h2 = await imp('panels/hist2d.js');
const dist = await imp('panels/distribution.js');
const corr = await imp('panels/correlation.js');
const rates = await imp('panels/rates.js');
const ft = await imp('panels/feature_table.js');
const mn = await imp('models_notes.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1e-5, -3.14159, 12345, -Math.PI, -Math.PI / 2, Math.PI / 2, Math.PI, -3.5, -1];

function summarise(el) {
  if (!el) return null;
  if (el.type === 'group') return { type: 'group', children: el.children.map(summarise) };
  const pts = el.shape?.points ?? null;
  return {
    type: el.type,
    points: pts ? pts.length : null,
    pts: pts && pts.length <= 400 ? pts : null,
    rect: el.type === 'rect' ? el.shape : null,
    circle: el.type === 'circle' ? el.shape : null,
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
    for (let i = 0; i < (s.data ?? []).length; i += 1) {
      const datum = s.data[i];
      const value = Array.isArray(datum) ? datum : datum?.value;
      const el = typeof s.renderItem === 'function' ? s.renderItem({ dataIndex: i, coordSys }, api) : null;
      const tip = typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter({ dataIndex: i, value }) : null;
      if (tip) strings.push(tip);
      const summary = summarise(el);
      for (const c of summary?.children ?? []) if (c?.text) strings.push(c.text);
      let label = null;
      if (s.type === 'heatmap') {
        const f = datum?.label?.formatter ?? s.label?.formatter;
        label = typeof f === 'function' ? f({ value }) : (f ?? null);
        if (label) strings.push(String(label));
      }
      items.push({ el: summary, tip, value, decal: datum?.itemStyle?.decal ?? null, label });
    }
    return {
      name: s.name, type: s.type, silent: Boolean(s.silent), xAxisIndex: s.xAxisIndex ?? 0,
      colour: s.itemStyle?.color ?? null, labelShow: s.label?.show ?? null, items,
    };
  });
  const axis = (a) => [].concat(a ?? []).map((x) => ({
    type: x.type, name: x.name ?? '', min: x.min ?? null, max: x.max ?? null, labels: x.axisLabel?.show !== false,
  }));
  return {
    series, strings,
    graphics: (option.graphic ?? []).map((g) => g.style?.text).filter(Boolean),
    xAxis: axis(option.xAxis), yAxis: axis(option.yAxis),
    grid: [].concat(option.grid ?? []),
    legend: [].concat(option.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => d?.name ?? d)),
    visualMap: [].concat(option.visualMap ?? []).map((vm) => ({ min: vm.min, max: vm.max, text: vm.text, seriesIndex: vm.seriesIndex ?? null, inRange: vm.inRange?.color ?? null })),
  };
}

const out = { perf: {}, pred: {}, residual: {}, hist: {}, hist2d: {}, corr: {}, rates: {}, table: {}, notes: {}, contrast: {} };
const W = { width: 760, height: 340 };

/* ---- E2 ------------------------------------------------------------------ */
for (const name of %(perf)s) {
  const payload = load(name);
  out.perf[name] = { quantities: perf.perfQuantities(payload), payload: payload.by_momentum_bin, charts: {} };
  for (const q of perf.perfQuantities(payload)) {
    out.perf[name].charts[q.key] = walk(perf.perfBinsOption(payload, { quantity: q.key }, W));
  }
  out.perf[name].showerA = walk(perf.perfBinsOption(payload, { quantity: 'rmse', shower: 'a' }, W));
}
{
  // Low N: one shower in the first bin of absolute:a, which the server ships without an interval.
  const weak = clone(load('perf_two_energy'));
  const s = weak.by_momentum_bin.series[0];
  s.n[0] = 1; s.rmse_lo[0] = null; s.rmse_hi[0] = null; s.drives_scale[0] = false;
  out.perf.weak = walk(perf.perfBinsOption(weak, { quantity: 'rmse' }, W));
  // A provisional range the weak points overflow, with the server's overflow list.
  const clipped = clone(load('perf_two_energy'));
  const y = clipped.by_momentum_bin.y_max.rmse;
  y.value = 10; y.provisional = true; y.n_overflow = 3; y.note = 'Provisional: no point reaches N = 15.';
  y.overflow = [{ series: 'absolute:a', bin: 3, n: 20, value: 13.54, lo: 11.5, hi: 15.3 }];
  out.perf.clipped = walk(perf.perfBinsOption(clipped, { quantity: 'rmse' }, W));
  out.perf.clippedModel = (({ clipped: c, y: yy }) => ({ clipped: c, y: { ...yy } }))(perf.perfModel(clipped, { quantity: 'rmse' }));
  out.notes.perfClipped = mn.perfBinsNotes({ payload: clipped, quantity: 'rmse' });
  // An XGBoost hold-out series, as the backend adds it: a code of its own, no relative error for phi.
  const xgb = clone(load('perf_two_angle'));
  const src = clone(xgb.by_momentum_bin.series[0]);
  delete src.median_rel; delete src.median_rel_lo; delete src.median_rel_hi; delete src.median_rel_method;
  xgb.by_momentum_bin.series.push({ ...src, key: 'xgb:a', code: 'xgb', label: 'XGBoost (20 %% validation split)', network: null });
  out.perf.xgb = { rmse: walk(perf.perfBinsOption(xgb, { quantity: 'rmse' }, W)), rel: walk(perf.perfBinsOption(xgb, { quantity: 'median_rel' }, W)),
    notes: mn.perfBinsNotes({ payload: xgb, quantity: 'median_rel' }) };
  out.perf.geometry = perf.groupedBarGeometry(16, 6, 1);
  out.perf.intervals = [[0, 16], [0, 140], [0, 0.35], [-16, 16], [0, 7]].map(([a, b]) => perf.dividingInterval(a, b));
}

/* ---- pred-truth ---------------------------------------------------------- */
for (const name of %(pred)s) {
  const payload = load(name);
  out.pred[name] = { payload: { axes: payload.axes, color: payload.color, identity: payload.identity,
    nonzero: Object.fromEntries(Object.entries(payload.density).map(([k, d]) => [k, d.counts.filter((c) => c > 0).length])) }, charts: {} };
  for (const p of %(palettes)s) {
    out.pred[name].charts[p] = walk(h2.hist2dOption(payload, { palette: p }, { width: 760, height: null }));
    out.pred[name].charts[p].firstLevel = h2.countColour(1, h2.countRamp(p, payload.color.ramp.by_palette[p]), payload.color.vmin, payload.color.vmax);
  }
  out.pred[name].layout = h2.hist2dLayout(2, 760, { square: true });
}
{
  // Below 15 pairs the server ships the pairs: points, never a raster; one lies beyond the axes.
  const few = clone(load('pred_density_two_energy'));
  few.density.a = { encoding: 'pairs', pairs: [[3, 3.4], [5, 4.1], [9, 30.0], [12, 11.6]], n: 4, n_in_range: 3,
    outside: { truth_below: 0, truth_above: 0, pred_below: 0, pred_above: 1, total: 1 }, n_missing: { total: 0, prediction: 0, truth: 0 } };
  out.pred.pairs = walk(h2.hist2dOption(few, { palette: 'viridis' }, { width: 760, height: null }));
  out.notes.predPairs = mn.predTruthNotes({ payload: few });
}

/* ---- residual histogram ---------------------------------------------------- */
for (const name of %(pred)s) {
  const payload = load(name);
  out.residual[name] = { chart: walk(dist.residualOption(payload, {}, W)), axis: { ...payload.residual.axis, curve_x: null },
    series: Object.fromEntries(Object.entries(payload.residual.series).map(([k, s]) => [k, { draw: s.draw, drives: s.drives_scale,
      bins: s.histogram?.counts?.length ?? 0, curvePeak: s.curve_peak, markers: s.markers }])) };
}
{
  // Shower A below the histogram floor: its events and summary marks in the reserved band.
  const strip = clone(load('pred_density_two_energy'));
  const a = strip.residual.series.a;
  a.draw = 'strip'; a.histogram = null; a.curve = null; a.drives_scale = false;
  a.strip = { values: [-0.4, -0.1, 0.05, 0.3, 0.9, 7.5], n_shown: 6, truncated: false };
  a.fit = { ...a.fit, n: 6, sigma: 0.9, sigma_error: 0.2915, sigma_ci95: [0.5618, 2.2074], sigma_bias_factor: 0.9515, estimator: 'moments' };
  a.markers = { mu: 0.2, ci95_lo: -0.3, ci95_hi: 0.7, dispersion_lo: -0.7, dispersion_hi: 1.1 };
  a.message = 'N = 6: below the 8-event floor for a density curve; the events and summary marks are drawn.';
  out.residual.strip = walk(dist.residualOption(strip, {}, W));
  // Both showers between the curve and the histogram floors: thin curves set a provisional range.
  const thin = clone(load('pred_density_two_angle'));
  for (const s of Object.values(thin.residual.series)) {
    s.draw = 'curve+strip'; s.histogram = null; s.drives_scale = false; s.strip = { values: [-12, -3, 0.1, 0.2], n_shown: 4, truncated: false };
  }
  out.residual.thin = walk(dist.residualOption(thin, {}, W));
  // Shower B's thin curve over shower A's robust histogram: clipped at the range, with a caret.
  const over = clone(load('pred_density_two_angle'));
  const b = over.residual.series.b;
  b.draw = 'curve+strip'; b.histogram = null; b.drives_scale = false; b.strip = { values: [0.1, 0.2], n_shown: 2, truncated: false };
  out.residual.over = walk(dist.residualOption(over, {}, W));
  // Nothing estimable: no density axis may be named.
  const none = clone(load('pred_density_two_energy'));
  for (const s of Object.values(none.residual.series)) {
    s.draw = 'strip'; s.histogram = null; s.curve = null; s.drives_scale = false; s.strip = { values: [0.1, 0.5], n_shown: 2, truncated: false };
  }
  out.residual.none = walk(dist.residualOption(none, {}, W));
}
{
  // The XGBoost azimuth residual: circular statistics, no line marks.
  const phi = load('pred_density_xgb_phi');
  out.residual.phi = walk(dist.residualOption(phi, {}, W));
  // Below the histogram floor: the residuals as ticks, still no summary marks.
  const few = clone(phi);
  const a = few.residual.series.a;
  a.draw = 'strip'; a.histogram = null; a.curve = { y: null }; a.curve_peak = null; a.drives_scale = false;
  a.core_fit = null; a.strip = { values: [-30, -2, 0.5, 4, 2900], n_shown: 5, truncated: false };
  a.fit = { ...a.fit, n: 5, mu_core: null, sigma_core: null };
  out.residual.phiStrip = walk(dist.residualOption(few, {}, W));
  // A payload that still carried line markers: an azimuth draws none of them anyway.
  const stray = clone(few);
  stray.residual.series.a.markers = { mu: 0.1, ci95_lo: -0.2, ci95_hi: 0.4, dispersion_lo: -1, dispersion_hi: 1.2 };
  out.residual.phiStray = walk(dist.residualOption(stray, {}, W));
}

/* ---- D4 ------------------------------------------------------------------ */
for (const name of %(hists)s) {
  const payload = load(name);
  out.hist[name] = {
    density: walk(dist.featureHistOption(payload, { palette: 'viridis' }, W)),
    count: walk(dist.featureHistOption(payload, { palette: 'viridis', quantity: 'count' }, W)),
    series: payload.series.map((s) => ({ label: s.label, draw: s.draw, n: s.n, kde: Boolean(s.kde), strip: (s.strip ?? []).length,
      counts: s.counts, scale: s.density_scale })),
    axis: { lo: payload.axis.lo, hi: payload.axis.hi, scale: payload.axis.scale }, y_max: payload.y_max,
    stops: cp.seriesStops('viridis', payload.series.length),
  };
}
{
  // A weak class's KDE above the robust range: clipped at the axis with its true peak.
  const tall = clone(load('features_single_hist'));
  tall.series[1].kde.pdf = tall.series[1].kde.pdf.map((v) => v * 20);
  out.hist.tall = walk(dist.featureHistOption(tall, { palette: 'viridis' }, W));
}

/* ---- D5 ------------------------------------------------------------------ */
{
  const payload = load('features_single_hist2d');
  out.hist2d = { chart: walk(h2.hist2dOption(payload, { palette: 'viridis' }, { width: 760, height: null })), payload: {
    series: payload.series.map((s) => ({ draw: s.draw, n: s.n, pairs: s.pairs ?? null, nonzero: (s.counts ?? []).filter((c) => c > 0).length })),
    x: { lo: payload.x.lo, hi: payload.x.hi }, y: { lo: payload.y.lo, hi: payload.y.hi }, color: payload.color } };
  out.hist2d.many = h2.hist2dLayout(19, 1100, { square: false });
}

/* ---- D3 ------------------------------------------------------------------ */
for (const name of %(corrs)s) {
  const payload = load(name);
  const k = payload.order.length;
  out.corr[name] = { chart: walk(corr.correlationOption(payload, { palette: 'viridis' }, { width: 620, height: 560 })),
    order: payload.order, circular: payload.circular_cells, hatched: Object.keys(payload.hatched),
    positions: payload.order.map((_, i) => payload.order.map((__, j) => corr.upperIndex(i, j, k))) };
}

/* ---- C11 ----------------------------------------------------------------- */
{
  const payload = load('primaries_single');
  out.rates = { chart: walk(rates.ratesOption(payload, {}, { width: 640, height: 320 })), payload };
}

/* ---- D2 ------------------------------------------------------------------ */
{
  const make = (tag) => ({
    tag, children: [], textContent: '', className: '', style: {}, title: '',
    append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? { tag: '#text', textContent: n, children: [] } : n); },
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); },
  });
  const doc = { createElement: make };
  const host = { ...make('div'), ownerDocument: doc, classList: { toggle: () => {} } };
  for (const name of %(describe)s) {
    out.table[name] = {};
    for (const stat of ['median', 'mean', 'range']) out.table[name][stat] = ft.featureRows(load(name), stat);
  }
  const panel = new ft.FeatureTablePanel(host);
  panel.render(load('features_single_describe'), { stat: 'mean' });
  const flat = (node) => [node.textContent, ...node.children.flatMap(flat)].filter(Boolean).join(' ');
  const table = host.children[0];
  out.table.dom = { tag: table.tag, kind: panel.kind, head: table.children[0].children[0].children.map(flat),
    rows: table.children[1].children.length, firstRow: table.children[1].children[0].children.map(flat),
    titles: table.children[1].children[0].children.slice(1).map((td) => td.title) };
  panel.clear();
  out.table.cleared = host.children.length;
}

/* ---- drawer notes ---------------------------------------------------------- */
{
  const pack = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
    sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
  const stub = { isTouched: () => false, get: () => null };
  const ex = { display_name: 'Demo' };
  const n = out.notes;
  n.perf = Object.fromEntries(%(perf)s.map((p) => [p, pack(mn.perfBinsNotes({ payload: load(p), state: stub, experiment: ex, quantity: 'median_rel' }))]));
  n.pred = Object.fromEntries(%(pred)s.map((p) => [p, pack(mn.predTruthNotes({ payload: load(p), palette: 'plasma' }))]));
  n.residual = Object.fromEntries(%(pred)s.map((p) => [p, pack(mn.residualNotes({ payload: load(p) }))]));
  n.residualPhi = pack(mn.residualNotes({ payload: load('pred_density_xgb_phi') }));
  n.table = Object.fromEntries(%(describe)s.map((p) => [p, pack(mn.featureTableNotes({ payload: load(p), stat: 'mean' }))]));
  n.corr = Object.fromEntries(%(corrs)s.map((p) => [p, pack(mn.featureCorrNotes({ payload: load(p) }))]));
  n.hist = Object.fromEntries(%(hists)s.map((p) => [p, pack(mn.featureHistNotes({ payload: load(p) }))]));
  n.hist2d = pack(mn.featureHist2dNotes({ payload: load('features_single_hist2d') }));
  n.primaries = pack(mn.primariesNotes({ payload: load('primaries_single') }));
  n.perfClipped = pack(n.perfClipped);
  n.predPairs = pack(n.predPairs);
  n.titled = mn.primariesNotes({ payload: load('primaries_single'), title: 'Card title' }).title;
  n.empty = [mn.perfBinsNotes({}), mn.residualNotes({ payload: null })];
  n.section = (await imp('panel_notes.js')).SECTION;
  n.builders = mn.MODELS_NOTE_BUILDERS;
  n.exported = Object.values(mn.MODELS_NOTE_BUILDERS).map((b) => typeof mn[b]);
}

/* ---- panel classes, with a fake DOM and a fake ECharts ---------------------- */
{
  const element = { clientWidth: 760, clientHeight: 340, style: {}, classList: { toggle: () => {} }, closest: () => null };
  const chart = { getWidth: () => element.clientWidth, getHeight: () => element.clientHeight, setOption: () => {}, resize: () => {},
    clear: () => {}, getDom: () => element, dispatchAction: () => {} };
  globalThis.echarts = { init: () => chart };
  const classes = {
    PerfBinsPanel: [perf.PerfBinsPanel, 'perf_two_energy'], Hist2dPanel: [h2.Hist2dPanel, 'pred_density_two_energy'],
    RatesPanel: [rates.RatesPanel, 'primaries_single'], DistributionPanel: [dist.DistributionPanel, 'features_single_hist'],
    CorrelationPanel: [corr.CorrelationPanel, 'features_two_corr'],
  };
  out.panels = {};
  for (const [name, [P, fixture]] of Object.entries(classes)) {
    const panel = new P(element, {});
    panel.render(load(fixture), { palette: 'viridis' });
    const option = panel.buildOption({ payload: load(fixture), opts: { palette: 'viridis' }, metrics: { width: 760, height: 340 } }).option;
    out.panels[name] = { kind: panel.kind, series: option.series.length, lastOpts: Object.keys(panel.lastOpts),
      export: panel.exportMetrics(321), height: element.style.height ?? null };
    panel.clear();
    out.panels[name].cleared = panel.lastPayload === null;
  }
  const residualPanel = new dist.DistributionPanel(element, {});
  out.panels.residualDispatch = residualPanel.buildOption({ payload: load('pred_density_two_energy'), opts: {}, metrics: W }).option.xAxis.name;
  out.panels.c4Dispatch = residualPanel.buildOption({ payload: load('distribution_single_u'), opts: { palette: 'viridis' }, metrics: W }).option.xAxis.name;
}

/* ---- colours a reader must see, against the card on screen and in print ----- */
function measureInk(theme) {
  const card = cp.rgbOf(scale.THEME.card);
  const c = (colour) => palette.contrast(cp.rgbOf(colour), card);
  const res = {};
  res.perf = Object.values(perf.sourceColours(['absolute', 'trans', 'local', 'xgb'])).map(c);
  res.rates = [c(scale.THEME.accent), c(scale.THEME.muted)];
  res.pairs = [c(scale.THEME.accent), c(scale.THEME.showerA), c(scale.THEME.showerB)];
  res.counts = {};
  for (const p of palette.SEQUENTIAL_PALETTES) {
    const ramp = h2.countRamp(p, theme === 'screen' ? load('pred_density_two_energy').color.ramp.by_palette[p] ?? null : null);
    const d5 = h2.countRamp(p, null);
    res.counts[p] = [0, 0.25, 0.5, 0.75, 1].flatMap((f) => [ramp, d5].map((r) => palette.contrast(h2.countColour(10 ** f, r, 0, 1), card)));
  }
  res.classes = {};
  for (const p of palette.SEQUENTIAL_PALETTES) res.classes[p] = cp.seriesStops(p, 19).map(c);
  return res;
}
out.contrast.screen = measureInk('screen');
Object.assign(scale.THEME, PRINT_TOKENS);
out.contrast.print = measureInk('print');
out.printPerf = walk(perf.perfBinsOption(load('perf_two_energy'), { quantity: 'bias' }, { width: 321, height: 300 }));
scale.restoreScreenTheme();

console.log(JSON.stringify(out));
"""


def _script() -> str:
    return _SCRIPT % {
        "perf": json.dumps(PERF), "pred": json.dumps(PRED), "hists": json.dumps(HISTS), "corrs": json.dumps(CORRS),
        "describe": json.dumps(DESCRIBE), "palettes": json.dumps(PALETTES),
    }


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


def _no_hyphen_numbers(strings) -> None:
    for text in strings:
        visible = re.sub(r"<[^>]+>", " ", str(text))
        assert not HYPHEN_NUMBER.search(visible), f"hyphen-minus before a digit in: {visible!r}"


def _hex_rgb(colour: str) -> list[int]:
    colour = colour.lstrip("#")
    return [int(colour[i:i + 2], 16) for i in (0, 2, 4)]


def _all_charts(out: dict):
    for name in PERF:
        yield from out["perf"][name]["charts"].values()
    yield out["perf"]["weak"]
    yield out["perf"]["clipped"]
    for name in PRED:
        yield from out["pred"][name]["charts"].values()
        yield out["residual"][name]["chart"]
    yield out["pred"]["pairs"]
    for key in ("strip", "thin", "over", "none", "phi", "phiStrip", "phiStray"):
        yield out["residual"][key]
    for name in HISTS:
        yield out["hist"][name]["density"]
        yield out["hist"][name]["count"]
    yield out["hist"]["tall"]
    yield out["hist2d"]["chart"]
    for name in CORRS:
        yield out["corr"][name]["chart"]
    yield out["rates"]["chart"]
    yield out["printPerf"]


# ------------------------------------------------------------------- E2 --


@pytest.mark.parametrize("name", PERF)
def test_every_bar_starts_at_zero_inside_its_momentum_bin(out, name):
    payload = out["perf"][name]["payload"]
    for key, chart in out["perf"][name]["charts"].items():
        bars = [s for s in chart["series"] if s["items"] and s["items"][0]["el"] and s["items"][0]["el"]["type"] == "rect"
                and s["name"] != "bin readout"]
        assert bars, key
        for s in bars:
            for item in s["items"]:
                r = item["el"]["rect"]
                assert min(abs(r["y"]), abs(r["y"] + r["height"])) < 1e-9, f"{key}: a bar not anchored at zero"
                centre = r["x"] + r["width"] / 2
                assert any(lo <= centre <= hi for lo, hi in zip(payload["bins"]["p_lo"], payload["bins"]["p_hi"]))
        y = chart["yAxis"][0]
        ymax = payload["y_max"][key]
        factor = 100 if payload["quantities"][key]["unit"] == "fraction" else 1
        assert y["max"] == pytest.approx(ymax["value"] * factor) and y["min"] == pytest.approx(ymax["min"] * factor)
        assert ("provisional" in y["name"]) == bool(ymax["provisional"])
        if not payload["quantities"][key]["signed"]:
            assert y["min"] == 0


@pytest.mark.parametrize("name", PERF)
def test_whiskers_are_the_interval_of_the_plotted_statistic_and_only_where_one_exists(out, name):
    payload = out["perf"][name]["payload"]
    for key, chart in out["perf"][name]["charts"].items():
        whiskers = _named(chart, r" · 95% interval$")
        expected = sum(
            1 for s in payload["series"] for v, lo, hi in zip(s[key], s[f"{key}_lo"], s[f"{key}_hi"])
            if v is not None and lo is not None and hi is not None)
        assert sum(len(w["items"]) for w in whiskers) == expected, key
        for w in whiskers:
            for item in w["items"]:
                assert item["el"]["points"] in (2, 4, 6)
                assert "95% interval" in item["tip"] and "not the spread of the showers" in item["tip"]


def test_a_bar_of_one_shower_is_faded_and_has_no_whisker(out):
    chart = out["perf"]["weak"]
    (bar,) = [s for s in chart["series"] if s["name"] == "Absolute-frame network · shower A"]
    first = bar["items"][0]
    assert first["el"]["dash"] and first["el"]["fillOpacity"] < 0.5
    assert "single shower" in first["tip"] and "faded" in first["tip"]
    (whisker,) = _named(chart, r"^Absolute-frame network · shower A · 95% interval$")
    assert len(whisker["items"]) == len(bar["items"]) - 1


def test_bars_and_whiskers_beyond_the_range_are_clipped_with_carets_and_counted(out):
    chart = out["perf"]["clipped"]
    model = out["perf"]["clippedModel"]
    assert "provisional" in chart["yAxis"][0]["name"] and chart["yAxis"][0]["max"] == 10
    bars = [s for s in chart["series"] if s["items"] and s["items"][0]["el"]["type"] == "rect" and s["name"] != "bin readout"]
    assert all(i["el"]["rect"]["y"] + i["el"]["rect"]["height"] <= 10 + 1e-9 for s in bars for i in s["items"])
    carets = _named(chart, r" \(clipped\)$")
    assert carets and all(i["el"]["type"] == "polygon" and "clipped at the provisional axis" in i["tip"] for s in carets for i in s["items"])
    assert model["clipped"]["bars"] > 0
    disclosures = out["notes"]["perfClipped"]["sections"]["Disclosures"]
    assert any("1 under-powered point" not in line and "beyond the axis, clipped with a caret" in line for line in disclosures)
    assert "provisional range" in out["notes"]["perfClipped"]["hazards"]
    assert "marks clipped at the axis" in out["notes"]["perfClipped"]["hazards"]


def test_the_xgboost_series_draws_from_the_payload_without_a_special_case(out):
    rmse = out["perf"]["xgb"]["rmse"]
    rel = out["perf"]["xgb"]["rel"]
    assert "XGBoost (20 % validation split) · shower A" in rmse["legend"]
    assert "XGBoost (20 % validation split) · shower A" not in rel["legend"]
    notes = {s["heading"]: s["lines"] for s in out["perf"]["xgb"]["notes"]["sections"]}
    assert any("Not reported for this statistic" in line and "XGBoost" in line for line in notes["Disclosures"])


def test_the_bar_geometry_and_the_tick_intervals(out):
    g = out["perf"]["geometry"]
    assert g["groups"] == 16 and len(g["offsets"]) == 6
    assert g["offsets"][0] == pytest.approx(-g["offsets"][-1])
    assert 6 * g["width"] < 1
    assert out["perf"]["intervals"] == [2, 20, 0.05, 4, 1]


# ------------------------------------------------------------ pred-truth --


@pytest.mark.parametrize("name", PRED)
def test_pred_truth_draws_square_equal_axes_with_the_identity(out, name):
    chart = out["pred"][name]["charts"]["viridis"]
    axes = out["pred"][name]["payload"]["axes"]
    assert len(chart["grid"]) == 2
    for g in chart["grid"]:
        assert g["width"] == pytest.approx(g["height"]), "1:1"
    for x, y in zip(chart["xAxis"], chart["yAxis"]):
        assert (x["min"], x["max"]) == (axes["truth"]["lo"], axes["truth"]["hi"]) == (y["min"], y["max"])
    identity = _named(chart, r"^identity: prediction = truth$")
    assert len(identity) == 2
    assert all("ŷ = y" in s["items"][0]["tip"] for s in identity)


@pytest.mark.parametrize("name", PRED)
def test_only_counted_bins_are_drawn_on_the_users_ramp(out, name):
    data = out["pred"][name]
    for palette in PALETTES:
        chart = data["charts"][palette]
        for key in ("a", "b"):
            (rects,) = _named(chart, rf"^Shower {key.upper()} · counts$")
            assert len(rects["items"]) == data["payload"]["nonzero"][key], "empty bins are transparent"
        measured = data["payload"]["color"]["ramp"]["by_palette"][palette]
        assert chart["firstLevel"] == pytest.approx(_hex_rgb(measured["first_level"]["color"]), abs=2)
        assert chart["visualMap"][0]["min"] == data["payload"]["color"]["vmin"]


def test_below_fifteen_pairs_the_pairs_are_drawn_and_those_beyond_the_axes_counted(out):
    chart = out["pred"]["pairs"]
    assert not _named(chart, r"^Shower A · counts$")
    (pairs,) = _named(chart, r"^Shower A · pairs$")
    assert len(pairs["items"]) == 3
    assert all("not a density" in i["tip"] for i in pairs["items"])
    assert any("pairs (N < 15)" in g and "1 outside" in g for g in chart["graphics"])
    assert "pairs below N = 15" in out["notes"]["predPairs"]["hazards"]


# --------------------------------------------------------------- residual --


@pytest.mark.parametrize("name", PRED)
def test_robust_residual_histograms_start_at_zero_with_their_means_and_no_band(out, name):
    chart = out["residual"][name]["chart"]
    assert chart["yAxis"][0]["min"] == 0 and chart["yAxis"][0]["labels"]
    assert chart["yAxis"][0]["name"].startswith("Probability density")
    assert not _named(chart, r"^reserved summary band$")
    outlines = [s for s in chart["series"] if not s["silent"] and s["name"].endswith("residual")
                and s["items"][0]["el"]["type"] == "polyline" and s["items"][0]["el"]["points"] < 100]
    assert len(outlines) == 2
    for s in outlines:
        pts = s["items"][0]["el"]["pts"]
        assert pts[0][1] == 0 and pts[-1][1] == 0
    assert len(_named(chart, r" · mean$")) == 2 and len(_named(chart, r" · mean · 95% interval$")) == 2
    assert _named(chart, r"^zero residual \(prediction = truth\)$")


def test_a_residual_below_the_histogram_floor_takes_the_band_with_two_marks(out):
    chart = out["residual"]["strip"]
    (band,) = _named(chart, r"^reserved summary band$")
    caption = [c["text"] for c in band["items"][0]["el"]["children"] if c["text"]]
    assert caption and "offsets, not densities" in caption[0]
    (events,) = _named(chart, r"^Shower A residual \(events\)$")
    assert len(events["items"]) == 5, "the event beyond the axis is a caret, not a tick"
    (sd,) = _named(chart, r"^Shower A residual · SD band$")
    assert sd["items"][0]["el"]["type"] == "group"
    assert "not the precision of the mean" in sd["items"][0]["tip"]
    (whisker,) = _named(chart, r"^Shower A residual · mean 95% interval$")
    assert whisker["items"][0]["el"]["points"] == 6
    assert "χ² 95% interval" in whisker["items"][0]["tip"] and "c₄(N)" in whisker["items"][0]["tip"]
    band_tips = [i["tip"] for s in _named(chart, r"^Shower A residual( \(events\)| · SD band| · mean 95% interval| · mean)$") for i in s["items"]]
    assert band_tips and all("drawing offset" in t for t in band_tips)


def test_thin_residual_curves_set_a_provisional_range(out):
    chart = out["residual"]["thin"]
    assert "provisional" in chart["yAxis"][0]["name"]
    assert not [s for s in chart["series"] if s["items"] and s["items"][0]["el"] and s["items"][0]["el"]["type"] == "polygon"
                and s["silent"] and s["name"].endswith("residual")], "no histogram below N = 15"


def test_a_thin_curve_above_the_robust_range_is_clipped_with_its_true_peak(out):
    chart = out["residual"]["over"]
    carets = _named(chart, r"^Shower B residual · fitted Gaussian \(clipped\)$")
    assert len(carets) == 1 and "lies above the axis" in carets[0]["items"][0]["tip"]


@pytest.mark.parametrize("key", ["phi", "phiStrip", "phiStray"])
def test_the_azimuth_residual_draws_no_mean_whisker_or_sd_bar(out, key):
    """CLAUDE.md section 2: never average a circular quantity - no line statistic is drawn."""
    chart = out["residual"][key]
    assert not _named(chart, r" · mean( 95% interval)?$") and not _named(chart, r" · mean · 95% interval$")
    assert not _named(chart, r" · SD band$")
    tips = " ".join(i["tip"] or "" for s in chart["series"] for i in s["items"])
    assert "circular mean direction" in tips and "R̄" in tips
    assert "mean residual (bias)" not in tips and "σ = " not in tips
    assert _named(chart, r"^zero residual \(prediction = truth\)$")


def test_the_azimuth_residual_names_its_curve_a_fit_of_the_core(out):
    chart = out["residual"]["phi"]
    tips = " ".join(i["tip"] or "" for s in chart["series"] for i in s["items"])
    assert "Gaussian fit of the core" in tips
    events = _named(out["residual"]["phiStrip"], r"\(events\)$")
    assert events and not _named(out["residual"]["phiStrip"], r"^reserved summary band$") is None


def test_the_azimuth_residual_drawer_names_the_circular_statistics(out):
    notes = out["notes"]["residualPhi"]
    legend = " ".join(notes["sections"]["Marks and legend"])
    assert "no mean rule, whisker or ± 1 SD bar" in legend and "circular SD" in legend
    (estimator,) = [lines for heading, lines in notes["sections"].items() if heading not in
                    ("Selection", "What is drawn", "Disclosures", "Marks and legend")]
    text = " ".join(estimator)
    assert "circular mean direction" in text and "R̄" in text and "no bias, σ or σ/μ" in text
    assert "bias −" not in text and "bias 0" not in text
    drawn = " ".join(notes["sections"]["What is drawn"])
    assert "no arithmetic mean, whisker or σ band" in drawn and "Gaussian fit of its core" in drawn
    _no_hyphen_numbers(notes["sections"][h] for h in notes["sections"])


def test_the_linear_residual_drawer_agrees_with_the_servers_note(out):
    """The drawer's legend and the server's own residual note describe the same marks."""
    notes = out["notes"]["residual"]["pred_density_two_energy"]
    drawn = " ".join(notes["sections"]["What is drawn"])
    legend = " ".join(notes["sections"]["Marks and legend"])
    for words in ("long-dashed", "two thin hairlines", "uncapped ± 1 SD bar", "the spread of the events"):
        assert words in drawn and words in legend, words


def test_with_no_estimable_density_the_axis_is_unlabelled_and_the_panel_says_so(out):
    chart = out["residual"]["none"]
    assert chart["yAxis"][0]["name"] == "" and not chart["yAxis"][0]["labels"]
    assert any("No density estimate" in g for g in chart["graphics"])


# -------------------------------------------------------------------- D4 --


@pytest.mark.parametrize("name", HISTS)
def test_feature_histograms_follow_the_payloads_ladder(out, name):
    data = out["hist"][name]
    chart = data["density"]
    for s in data["series"]:
        mine = [x for x in chart["series"] if x["name"] == s["label"]]
        polygons = [x for x in mine if x["silent"] and x["items"][0]["el"]["type"] == "polygon"]
        assert bool(polygons) == (s["draw"] == "histogram"), s["label"]
        curves = [x for x in mine if not x["silent"] and x["items"][0]["el"].get("points") == 160]
        assert bool(curves) == s["kde"], s["label"]
        events = _named(chart, rf"^{re.escape(s['label'])} \(events\)$")
        assert bool(events) == (s["draw"] == "strip")
        if polygons:
            heights = [p[1] for p in polygons[0]["items"][0]["el"]["pts"][1:-1:2]]
            assert heights == pytest.approx([c * s["scale"] for c in s["counts"]], rel=1e-9)
    assert chart["yAxis"][0]["min"] == 0
    if any(s["draw"] == "strip" for s in data["series"]):
        assert _named(chart, r"^reserved summary band$")
        tips = [i["tip"] for x in _named(chart, r" \(events\)$") for i in x["items"]]
        assert tips and all("drawing offset" in t for t in tips)
    assert data["count"]["yAxis"][0]["name"] == "Events per bin"


def test_an_azimuth_gets_its_full_period_and_no_linear_kernel(out):
    chart = out["hist"]["features_single_hist_phi"]["density"]
    x = chart["xAxis"][0]
    assert x["min"] == pytest.approx(-3.14159) and x["max"] == pytest.approx(3.14159)
    assert not [s for s in chart["series"] if s["items"] and s["items"][0]["el"] and s["items"][0]["el"].get("points") == 160]


def test_a_weak_kde_above_the_robust_range_is_clipped(out):
    carets = _named(out["hist"]["tall"], r"· Gaussian KDE \(clipped\)$")
    assert len(carets) == 1 and "lies above the axis" in carets[0]["items"][0]["tip"]


# -------------------------------------------------------------------- D5 --


def test_d5_multiples_share_edges_and_scale_and_draw_pairs_below_fifteen(out):
    data = out["hist2d"]
    chart = data["chart"]
    assert len(chart["grid"]) == 2
    for x, y in zip(chart["xAxis"], chart["yAxis"]):
        assert (x["min"], x["max"]) == (data["payload"]["x"]["lo"], data["payload"]["x"]["hi"])
        assert (y["min"], y["max"]) == (data["payload"]["y"]["lo"], data["payload"]["y"]["hi"])
    pairs_series, hist_series = data["payload"]["series"]
    (pairs,) = _named(chart, r"· pairs$")
    inside = [p for p in pairs_series["pairs"] if data["payload"]["y"]["lo"] <= p[1] <= data["payload"]["y"]["hi"]]
    assert len(pairs["items"]) == len(inside) == 7
    (rects,) = _named(chart, r"· counts$")
    assert len(rects["items"]) == hist_series["nonzero"]
    assert chart["visualMap"][0]["min"] == data["payload"]["color"]["vmin"]
    assert chart["visualMap"][0]["max"] == pytest.approx(data["payload"]["color"]["vmax"])
    assert "log₁₀ axis" in chart["yAxis"][0]["name"]
    assert data["many"]["rows"] * data["many"]["cols"] >= 19 and data["many"]["height"] > 600


# -------------------------------------------------------------------- D3 --


@pytest.mark.parametrize("name", CORRS)
def test_azimuth_cells_are_hatched_and_never_on_the_colour_scale(out, name):
    data = out["corr"][name]
    chart = data["chart"]
    linear, other = chart["series"]
    assert linear["name"] == "Pearson r"
    order = data["order"]
    k = len(order)
    circular_positions = {c["position"] for c in data["circular"]}
    # Map each drawn linear cell back to its upper-triangle position.
    for item in linear["items"]:
        j, row = int(item["value"][0]), int(item["value"][1]) + 1
        assert data["positions"][row][j] not in circular_positions
        assert not {order[row], order[j]} & {"avg_phi", "avg_phi_circ"}
    lower_circular = [c for c in data["circular"] if c["row"] != c["col"]]
    assert len(other["items"]) >= len(lower_circular)
    assert all(i["decal"] for i in other["items"])
    tips = [i["tip"] for i in other["items"]]
    assert all("off the colour scale" in t for t in tips)
    for t in tips:
        if "parity" in t:
            tail = t.split("the notebook")[1]
            assert "95% interval" not in tail.split("<br/>")[0], "parity r has no interval"
    spread = [i for i in linear["items"] if "angular_spread" in (order[int(i["value"][0])], order[int(i["value"][1]) + 1])]
    assert spread and all(i["decal"] and "hatched:" in i["tip"] for i in spread)
    assert chart["visualMap"][0]["min"] == -1 and chart["visualMap"][0]["max"] == 1
    assert len(chart["xAxis"][0]["name"]) == 0 and k == 21


# ------------------------------------------------------------------- C11 --


def test_rates_are_points_with_capped_wilson_whiskers_on_the_full_scale(out):
    chart = out["rates"]["chart"]
    payload = out["rates"]["payload"]
    y = chart["yAxis"][0]
    assert (y["min"], y["max"]) == (0, 100)
    (whiskers,) = _named(chart, r"^Wilson 95% interval$")
    assert len(whiskers["items"]) == len(payload["by_bin"]["bin"])
    for item, lo, hi in zip(whiskers["items"], payload["by_bin"]["lo"], payload["by_bin"]["hi"]):
        assert item["el"]["points"] == 6
        pts = item["el"]["pts"]
        assert pts[2][1] == pytest.approx(100 * lo) and pts[3][1] == pytest.approx(100 * hi)
        assert "Wilson" in item["tip"]
    (rule,) = _named(chart, r"^Whole selection$")
    tip = rule["items"][0]["tip"]
    assert "75.3%" in tip and "[70.0%, 79.9%]" in tip
    assert "not drawn" in tip


# -------------------------------------------------------------------- D2 --


@pytest.mark.parametrize("name", DESCRIBE)
def test_the_feature_table_prints_circular_rows_as_directions(out, name):
    payload = _load(name)
    for stat, model in out["table"][name].items():
        assert len(model["columns"]) == len(payload["classes"])
        assert len(model["rows"]) == len(payload["features"])
        for row in model["rows"]:
            if row["circular"] and stat != "range":
                assert all("±" not in c["text"] for c in row["cells"])
                assert any("R̄" in c["text"] for c in row["cells"])
            for c, col in zip(row["cells"], model["columns"]):
                if 0 < c["n"] < 20:
                    assert c["flag"]
        _no_hyphen_numbers(c["text"] for r in model["rows"] for c in r["cells"])
        _no_hyphen_numbers(c["title"] for r in model["rows"] for c in r["cells"])


def test_low_n_cells_say_so(out):
    model = out["table"]["features_events_describe"]["mean"]
    counts = [c["n"] for c in model["columns"]]
    width = next(r for r in model["rows"] if r["key"] == "width")
    for c, n in zip(width["cells"], counts):
        if n == 2:
            assert "1 d.o.f." in c["text"]
        if n == 1:
            assert "±" not in c["text"]
        if 2 < n < 15:
            assert "χ² 95% interval" in c["title"] and "c₄(N)" in c["title"]


def test_the_table_dom_is_text_only(out):
    dom = out["table"]["dom"]
    assert dom["tag"] == "table" and dom["kind"] == "table"
    assert dom["head"][0].startswith("Feature · mean ± SD")
    assert dom["rows"] == len(_load("features_single_describe")["features"])
    assert all("N = " in t for t in dom["titles"])
    assert out["table"]["cleared"] == 0


# ----------------------------------------------------------------- notes --


def _check_notes(n: dict, section: dict) -> None:
    standard = [section["selection"], section["drawn"], section["disclosures"], section["legend"]]
    present = [h for h in n["headings"] if h in standard]
    assert present == [h for h in standard if h in present], "the four sections keep their order"
    assert n["headings"][: len(present)] == present, "a card's own headings follow the four"
    assert section["drawn"] in n["headings"] and section["legend"] in n["headings"]
    _no_hyphen_numbers(line for lines in n["sections"].values() for line in lines)


def test_every_notes_builder_returns_the_four_sections(out):
    notes = out["notes"]
    section = notes["section"]
    for group in ("perf", "pred", "residual", "table", "corr", "hist"):
        for n in notes[group].values():
            _check_notes(n, section)
    for key in ("hist2d", "primaries", "perfClipped", "predPairs"):
        _check_notes(notes[key], section)
    assert notes["titled"] == "Card title"
    assert notes["empty"] == [None, None]
    assert notes["exported"] == ["function"] * 8
    assert set(notes["builders"]) == {"perf-bins", "pred-truth", "pred-residuals", "feat-table", "feat-corr",
                                      "feat-hist", "feat-hist2d", "prim-rate"}


def test_the_drawers_name_what_the_cards_disclose(out):
    notes = out["notes"]
    pred = notes["pred"]["pred_density_two_energy"]
    disclosures = " ".join(pred["sections"]["Disclosures"])
    assert "143 of 286 pairs lie outside" in disclosures
    assert "outside the shared axes (" not in disclosures, "the server's warning states the outside count; ours is not repeated"
    assert "plasma" in " ".join(pred["sections"]["What is drawn"]) and "#bf3984" in " ".join(pred["sections"]["What is drawn"])
    residual = " ".join(notes["residual"]["pred_density_two_energy"]["sections"]["Disclosures"])
    assert "below and 5 above the axis" in residual
    hist = notes["hist"]["features_single_hist"]
    assert "low-statistics classes" in hist["hazards"]
    assert any("Comb lag-1" in line and "lattice" in line for line in hist["sections"]["Disclosures"])
    table = notes["table"]["features_single_describe"]
    assert {"small classes", "floored values", "circular feature"} <= set(table["hazards"])
    assert any("floored at 10⁻⁶ mm" in line for line in table["sections"]["Disclosures"])
    corr = notes["corr"]["features_two_corr"]
    assert "circular variable" in corr["hazards"]
    assert any("parity_r" in line for line in corr["sections"]["Circular quantities"])
    prim = notes["primaries"]
    assert "small bins" in prim["hazards"]
    assert any("216" in line and "≥ 10" in line for line in prim["sections"]["Exact counts"])
    perf = notes["perf"]["perf_two_angle"]
    assert any("θ < 0.1 rad" in line for line in perf["sections"]["Disclosures"])
    assert any(line.startswith("Median relative error:") for line in perf["sections"]["Estimators"])


# ------------------------------------------------------- panels and ink --


def test_panel_classes_delegate_to_their_builders(out):
    panels = out["panels"]
    assert panels["PerfBinsPanel"]["kind"] == "perf-bins"
    assert panels["Hist2dPanel"]["kind"] == "hist2d" and panels["Hist2dPanel"]["height"].endswith("px")
    assert panels["RatesPanel"]["kind"] == "rates"
    assert panels["DistributionPanel"]["kind"] == "distribution"
    assert panels["CorrelationPanel"]["kind"] == "correlation"
    for p in ("PerfBinsPanel", "Hist2dPanel", "RatesPanel", "DistributionPanel", "CorrelationPanel"):
        assert panels[p]["series"] > 0 and panels[p]["cleared"]
        assert panels[p]["export"]["width"] == 321 and panels[p]["export"]["height"] > 0
    assert panels["residualDispatch"].startswith("Relative energy residual")
    assert "per bin" not in panels["c4Dispatch"]


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_every_colour_a_reader_must_see_clears_three_to_one(out, theme):
    ink = out["contrast"][theme]
    assert min(ink["perf"]) >= 3, ink["perf"]
    assert min(ink["rates"]) >= 3 and min(ink["pairs"]) >= 3
    for palette, values in ink["counts"].items():
        assert min(values) >= 2.95, (palette, values)
    for palette, values in ink["classes"].items():
        assert min(values) >= 3, palette


def test_no_rendered_number_uses_an_ascii_hyphen(out):
    for chart in _all_charts(out):
        _no_hyphen_numbers(chart["strings"])


# ------------------------------------------------------------- sources --

NEW_MODULES = ["perf_bins.js", "hist2d.js", "rates.js", "feature_table.js"]
CHART_MODULES = ["perf_bins.js", "hist2d.js", "rates.js"]


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


@pytest.mark.parametrize("module", NEW_MODULES)
def test_new_modules_build_no_html_into_the_page_and_never_confine_a_tooltip(module):
    source = _strip_comments((JS / "panels" / module).read_text(encoding="utf-8"))
    for forbidden in ("innerHTML", "insertAdjacentHTML", "rgba(22,27,34,0.95)"):
        assert forbidden not in source, (module, forbidden)
    assert not re.search(r"confine:\s*true", source)
    assert not re.search(r"getElementById\('", source), "ids come from the caller, never a literal"
    assert "transition" not in source


@pytest.mark.parametrize("module", CHART_MODULES)
def test_every_new_chart_takes_its_wrapped_tooltip_from_tooltip_js(module):
    source = _strip_comments((JS / "panels" / module).read_text(encoding="utf-8"))
    assert "wrapTooltip(tooltipOption(opts.tooltipPosition ?? null))" in source
    assert "from './tooltip.js'" in source


def test_the_notes_module_reads_no_page():
    source = _strip_comments((JS / "models_notes.js").read_text(encoding="utf-8"))
    for forbidden in ("document.", "window.", "innerHTML"):
        assert forbidden not in source
