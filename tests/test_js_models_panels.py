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

import html
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
RES = ["res_scaling_two", "res_scaling_xgb", "res_scaling_single_hits", "res_scaling_single_events"]

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
const rs = await imp('panels/resolution_scaling.js');
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
      name: s.name, id: s.id ?? null, type: s.type, silent: Boolean(s.silent), xAxisIndex: s.xAxisIndex ?? 0, yAxisIndex: s.yAxisIndex ?? 0,
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

const out = { perf: {}, pred: {}, residual: {}, hist: {}, hist2d: {}, corr: {}, rates: {}, table: {}, notes: {}, contrast: {}, res: {} };
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
  // P-22: the server's rounded tops land on a round step; an older top off the grid still gets one.
  out.perf.ticks = [[0, 0.12], [0, 1.5], [-1.2, 1.2], [0, 6], [0, 0.3], [0, 8], [0, 0.22], [0, 0.11]]
    .map(([a, b]) => perf.dividingInterval(a, b));
}
{
  // P-14, P-15: the legend wraps into rows over the plot, and shower B's swatch is its wash and outline.
  const two = load('perf_two_energy');
  const opt = perf.perfBinsOption(two, { quantity: 'rmse' }, W);
  const narrow = perf.perfBinsOption(two, { quantity: 'rmse' }, { width: 360, height: 340 });
  out.perf.legendOption = { type: opt.legend.type, left: opt.legend.left, right: opt.legend.right,
    wideTop: opt.grid.top, narrowTop: narrow.grid.top, gridLeft: opt.grid.left, gridRight: opt.grid.right,
    icons: opt.legend.data.map((d) => d.icon ?? null) };
  out.perf.swatches = opt.series.filter((x) => x.type === 'custom' && / · shower [AB]$/.test(x.name ?? ''))
    .map((x) => ({ name: x.name, itemStyle: x.itemStyle }));
  // P-4 and D-9 on the XGBoost recording: medians of 2-5 events have no interval and are weak.
  const xgbE = load('perf_xgb_energy');
  const m = perf.perfModel(xgbE, { quantity: 'median_rel' });
  out.perf.medianPoints = m.series.flatMap((x) => x.points.map((pt) => ({ n: pt.n, weak: pt.weak, single: pt.single,
    lo: pt.lo, hi: pt.hi, tip: perf.perfTip(m, x, pt) })));
  out.perf.medianChart = walk(perf.perfBinsOption(xgbE, { quantity: 'median_rel' }, W));
  out.perf.xgbEnergy = walk(perf.perfBinsOption(xgbE, { quantity: 'rmse' }, W));
  out.perf.xgbEnergyModel = (({ momentum, noun, intervalFloor }) => ({ momentum, noun, intervalFloor }))(perf.perfModel(xgbE, { quantity: 'rmse' }));
  out.notes.xgbEnergy = mn.perfBinsNotes({ payload: xgbE, quantity: 'rmse' });
  out.perf.casing = scale.THEME.canvas;
  out.perf.ink = scale.THEME.text;
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
  // P-19: the XGBoost azimuth spans its period in mrad, ticked at multiples of π/2 written in π.
  const phi = load('pred_density_xgb_phi');
  const opt = h2.hist2dOption(phi, { palette: 'viridis' }, { width: 760, height: null });
  out.pred.phiAxes = [opt.xAxis[0], opt.yAxis[0]].map((a) => ({ min: a.min, max: a.max, interval: a.interval,
    labels: [-3141.59, -1570.795, 0, 1570.795, 3141.59].map((v) => a.axisLabel.formatter(v)) }));
  out.pred.phiChart = walk(opt);
  out.pred.momentum = walk(h2.hist2dOption(load('pred_density_xgb_energy'), { palette: 'viridis' }, { width: 760, height: null }));
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
  // P-23: a log10 axis prints its end labels only at decades; P-21: the energy axis falls back to E.
  const opt = h2.hist2dOption(payload, { palette: 'viridis' }, { width: 760, height: null });
  out.hist2d.ends = { y: { min: opt.yAxis[0].min, max: opt.yAxis[0].max, showMin: opt.yAxis[0].axisLabel.showMinLabel,
    showMax: opt.yAxis[0].axisLabel.showMaxLabel }, xHasEnds: 'showMinLabel' in opt.xAxis[0].axisLabel };
  const tiny = h2.hist2dOption(payload, { palette: 'viridis' }, { width: 230, height: null });
  out.hist2d.tinyNames = tiny.yAxis.map((a) => a.name).filter(Boolean);
  out.hist2d.chartTiny = walk(tiny);
}

/* ---- D3 ------------------------------------------------------------------ */
for (const name of %(corrs)s) {
  const payload = load(name);
  // D-10: the feature card fades a cell whose interval contains 0; without the option (C8) nothing is faded.
  const faded = corr.correlationOption(payload, { palette: 'viridis', fadeNull: true }, { width: 620, height: 560 });
  const plain = corr.correlationOption(payload, { palette: 'viridis' }, { width: 620, height: 560 });
  const lin = (o) => o.series[0].data.map((d) => ({ opacity: d.itemStyle?.opacity ?? null, value: d.value }));
  out.corr[`${name}:fade`] = { faded: lin(faded), plain: lin(plain),
    tips: faded.series[0].data.map((_, i) => faded.series[0].tooltip.formatter({ dataIndex: i })),
    matrix: corr.featureCorrMatrix(payload).matrix.map((row) => row.map((c) => (c ? { ci95: c.ci95 ?? null, hatched: Boolean(c.hatched), r: c.r } : null))),
    notes: mn.featureCorrNotes({ payload }) };
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

/* ---- res-scaling ------------------------------------------------------------- */
{
  const packR = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
    sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
  const stubR = { isTouched: () => false, get: () => null };
  const RW = { width: 760, height: 420 };
  const axesOf = (o) => ({
    x: [].concat(o.xAxis).map((a) => ({ position: a.position ?? null, min: a.min ?? null, max: a.max ?? null, inverse: Boolean(a.inverse),
      interval: a.interval ?? null, name: a.name ?? '', tickValues: a.axisTick?.customValues ?? null,
      labelValues: a.axisLabel?.customValues ?? null, labelShow: a.axisLabel?.show !== false,
      labels: (a.axisLabel?.customValues ?? []).map((v) => String(a.axisLabel.formatter(v))), split: a.splitLine?.show ?? null })),
    y: [].concat(o.yAxis).map((a) => ({ min: a.min ?? null, max: a.max ?? null, interval: a.interval ?? null, name: a.name ?? '',
      labelShow: a.axisLabel?.show !== false })),
    seriesAxes: o.series.map((x) => x.xAxisIndex ?? 0),
    graphics: (o.graphic ?? []).map((g) => g.style?.text).filter(Boolean),
  });
  const modelOf = (payload, windows, shower) => {
    const m = rs.resolutionModel(payload, { windows, shower });
    return { clipped: m.clipped, series: m.series.map((s) => ({ key: s.key, colour: s.colour, isB: s.isB,
      points: s.points.map((p) => ({ bin: p.w.bin, n: p.n, whisker: p.whisker, weak: p.weak, subFloor: p.subFloor, over: p.over,
        tip: rs.pointTip(m, s, p) })),
      fits: Object.fromEntries(rs.DRAWN_FORMS.map((f) => [f, s.fits[f] ? { runs: s.fits[f].runs.length,
        line: rs.lineTip(m, s, s.fits[f], payload), band: rs.bandTip(s, s.fits[f]), cut: s.fits[f].cut,
        cutTip: s.fits[f].cut ? rs.fitCutTip(m, s, s.fits[f]) : null } : null])),
      unreported: s.unreported.map((w) => w.bin) })), y: m.y };
  };
  for (const name of %(res)s) {
    const payload = load(name);
    const entry = { charts: {}, axes: {}, tables: {}, models: {}, notes: {}, ink: scale.THEME.text,
      hues: perf.sourceColours(['absolute', 'trans', 'local', 'xgb']) };
    for (const windows of ['anchors', 'all']) {
      for (const shower of ['both', 'a', 'b']) {
        const key = `${windows}:${shower}`;
        const opt = rs.resolutionScalingOption(payload, { windows, shower, palette: 'viridis', card: 'res-scaling' }, RW);
        entry.charts[key] = walk(opt);
        entry.axes[key] = axesOf(opt);
        entry.tables[key] = rs.fitTableRows(payload, { windows, shower });
        entry.models[key] = modelOf(payload, windows, shower);
      }
      entry.notes[windows] = packR(mn.resolutionScalingNotes({ payload, state: stubR, experiment: { display_name: 'Demo' }, windows }));
    }
    entry.notes.shownA = packR(mn.resolutionScalingNotes({ payload, windows: 'all', shower: 'a' }));
    out.res[name] = entry;
  }
  // A provisional range: the axis says so.
  const prov = clone(load('res_scaling_two'));
  prov.axis.y.provisional = true;
  out.res.provisional = axesOf(rs.resolutionScalingOption(prov, { windows: 'anchors' }, RW));
  out.res.provisionalNotes = packR(mn.resolutionScalingNotes({ payload: prov, windows: 'anchors' }));
  // A lower range: markers and whiskers clipped with carets carrying their true values.
  const low = clone(load('res_scaling_single_hits'));
  low.axis.y.hi = 60; low.axis.y.interval = 10;
  out.res.clipped = { chart: walk(rs.resolutionScalingOption(low, { windows: 'all' }, RW)), model: modelOf(low, 'all', 'both'),
    notes: packR(mn.resolutionScalingNotes({ payload: low, windows: 'all' })) };
  // No drawable window: every window off the axis.
  const none = clone(load('res_scaling_two'));
  for (const s of none.series) for (const w of s.windows) { w.off_axis = true; w.p_lo = Math.min(w.p_lo, 3); }
  const emptyOpt = rs.resolutionScalingOption(none, { windows: 'all' }, RW);
  out.res.empty = { chart: walk(emptyOpt), axes: axesOf(emptyOpt) };
  out.res.nothing = walk(rs.resolutionScalingOption(null, {}, RW));
  // A window of N = 5 in the all mode: a dashed ring without a whisker, its tip naming the floor.
  const thin = clone(load('res_scaling_single_events'));
  const w = thin.series[0].windows.find((x) => !x.off_axis);
  w.n = 5; w.whisker = false; w.weak = true; w.eligible = false;
  out.res.thin = { bin: w.bin, chart: walk(rs.resolutionScalingOption(thin, { windows: 'all' }, RW)), model: modelOf(thin, 'all', 'both') };
  out.res.clip = rs.clipPolyline([[0, -10], [0.25, 5], [0.5, 20]], 0, 15);
  // A fit whose iterated weights did not settle: said in its tooltip, the table, the drawer and the hazards.
  const unsettled = clone(load('res_scaling_two'));
  const uf = unsettled.series.find((x) => x.key === 'network:a').fits.anchors.affine;
  uf.converged = false; uf.iterations = 200;
  const um = rs.resolutionModel(unsettled, { windows: 'anchors' });
  const us = um.series.find((x) => x.key === 'network:a');
  out.res.unsettled = {
    lineTip: rs.lineTip(um, us, us.fits.affine, unsettled),
    status: rs.fitTableRows(unsettled, { windows: 'anchors' }).rows.find((r) => r.key === 'network:a').fits[0].cells[5],
    notes: packR(mn.resolutionScalingNotes({ payload: unsettled, windows: 'anchors' })),
  };
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

{
  // The resolution panel: the fit table goes once after the card's plot frame, text nodes only.
  const make = (tag) => ({
    tag, children: [], textContent: '', className: '', attrs: {},
    append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? { tag: '#text', textContent: n, children: [] } : n); },
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); },
    setAttribute(k, v) { this.attrs[k] = v; },
  });
  const doc = { createElement: make };
  const inserted = [];
  const frame = { ownerDocument: doc, after: (node) => inserted.push(node) };
  const card = { querySelector: (sel) => (sel === '.plot-frame' ? frame : null) };
  const element = { clientWidth: 760, clientHeight: 420, style: {}, classList: { toggle: () => {} },
    closest: (sel) => (sel === '.card' ? card : null) };
  const panel = new rs.ResolutionScalingPanel(element, { card: 'res-scaling' });
  panel.render(load('res_scaling_two'), { windows: 'anchors', shower: 'both' });
  panel.render(load('res_scaling_two'), { windows: 'all', shower: 'a' });
  const flat = (node) => [node.textContent, ...node.children.flatMap(flat)].filter(Boolean).join(' ');
  const host = inserted[0];
  const table = host.children[0];
  const option = panel.buildOption({ payload: load('res_scaling_two'), opts: { windows: 'all' }, metrics: { width: 760, height: 420 } }).option;
  const cellOf = (c) => ({ tag: c.tag, text: flat(c), cls: c.className, scope: c.attrs.scope ?? null, rowspan: c.attrs.rowspan ?? null });
  out.res.panel = { inserted: inserted.length, hostClass: host.className, tag: table.tag, kinds: table.children.map((c) => c.tag),
    head: table.children[1].children[0].children.map(flat), headCls: table.children[1].children[0].children.map((c) => c.className),
    bodies: table.children.filter((c) => c.tag === 'tbody').map((b) => b.children.map((tr) => tr.children.map(cellOf))),
    kind: panel.kind, series: option.series.length, export: panel.exportMetrics(321) };
  panel.clear();
  out.res.panel.cleared = host.children.length;
  out.res.panel.payloadCleared = panel.lastPayload === null;
}

/* ---- res-scaling: the E view (sigma/E against E in GeV, with the ratio panel) -------- */
{
  const RE = { width: 760, height: 600 };
  const fnText = (k, v) => (typeof v === 'function' ? `fn:${v.toString()}` : v);
  const canonical = (o) => JSON.stringify(o, fnText);
  const refs = rs.RATIO_REFERENCES;
  const packRef = (r) => ({ key: r.key, shower: r.shower, form: r.form, series: r.series, label: r.label, reason: r.reason,
    span: r.span, interval: r.interval, hasBand: Boolean(r.band), bandClipped: r.bandClipped, literature: r.literature?.key ?? null,
    outlined: r.outlined ?? null, bandCut: r.bandCut ?? null, provisional: r.provisional });
  const packModel = (m, full) => ({
    x: m.x, y: m.y, curveMinGev: m.curveMinGev, yMinGev: m.yMinGev, nPoints: m.nPoints, nLines: m.nLines,
    reference: { key: m.reference.key, label: m.reference.label, interval: m.reference.interval, flag: m.reference.flag,
      byShower: Object.fromEntries(Object.entries(m.reference.byShower).map(([k, r]) => [k, packRef(r)])) },
    ratio: m.ratio, clipped: m.clipped, offScale: m.offScale, spans: m.spans, noteText: m.noteText,
    bandsOutlined: { main: m.bandsOutlined.main, ratio: m.bandsOutlined.ratio }, twoOnShow: m.twoOnShow, endLabels: m.endLabels,
    literature: m.literature.map((l) => ({ key: l.key, label: l.label, legend: l.legend, inForce: l.inForce, cut: l.cut,
      curve: full ? l.curve : null, runs: full ? l.runs : null })),
    series: m.series.map((s) => ({
      key: s.key, shower: s.raw.shower ?? null, source: s.raw.source, isB: s.isB, colour: s.colour, span: s.span, offsetPx: s.offsetPx,
      lineOpacity: s.lineOpacity(false), reference: s.reference ? packRef(s.reference) : null,
      unreported: s.unreported.map((w) => w.bin),
      points: s.points.map((p) => ({ bin: p.w.bin, label: p.w.label, x: p.x, E: p.E, value: p.value, lo: p.lo, hi: p.hi, n: p.n,
        pLo: p.w.p_lo, whisker: p.whisker, weak: p.weak, subFloor: p.subFloor, below4: p.below4, fitted: p.fitted, robust: p.robust,
        over: p.over, roles: p.roles, clip: p.clip,
        ratio: { drawn: p.ratio.drawn, reason: p.ratio.reason, ref: p.ratio.ref, value: p.ratio.value, lo: p.ratio.lo, hi: p.ratio.hi,
          over: p.ratio.over ?? null, clip: p.ratio.clip ?? null, robust: p.ratio.robust } })),
      fits: Object.fromEntries(rs.ENERGY_FORMS.map((form) => {
        const f = s.fits[form];
        if (!f.drawable) return [form, { drawable: false, reason: f.reason, span: f.span }];
        return [form, { drawable: true, reason: f.reason, span: f.span, domain: f.domain, provisional: f.provisional,
          converged: f.converged, isReference: f.isReference, cut: f.cut, floorCut: f.floorCut, outlined: f.outlined,
          curve: full ? f.curve : null, solid: full ? f.solid : null, dashed: full ? f.dashed : null, band: full ? f.band : null,
          ratio: f.ratio ? { solid: full ? f.ratio.solid : null, dashed: full ? f.ratio.dashed : null, cut: f.ratio.cut, outlined: f.ratio.outlined,
            rows: full ? f.ratio.rows : null, band: full ? f.ratio.band : null } : null }];
      })),
    })),
  });
  const optionOf = (payload, opts, metrics = RE) => {
    const built = rs.energyViewOption(payload, opts, metrics);
    const o = built.option;
    const ax = (a) => ({ type: a.type ?? 'value', gridIndex: a.gridIndex ?? 0, min: a.min ?? null, max: a.max ?? null,
      interval: a.interval ?? null, name: a.name ?? '', labelShow: a.axisLabel?.show !== false, tickShow: a.axisTick?.show !== false,
      tickValues: a.axisTick?.customValues ?? null, labelValues: a.axisLabel?.customValues ?? null,
      labels: (a.axisLabel?.customValues ?? []).map((v) => String(a.axisLabel.formatter(v))),
      pointer: a.axisPointer ? { show: a.axisPointer.show, type: a.axisPointer.type, snap: a.axisPointer.snap,
        triggerTooltip: a.axisPointer.triggerTooltip, label: a.axisPointer.label?.show ?? null,
        labelText: typeof a.axisPointer.label?.formatter === 'function' ? [a.axisPointer.label.formatter({ value: 12.5 }), a.axisPointer.label.formatter(-3.5)] : null } : null });
    return {
      chart: walk(o), plotGrid: built.plotGrid ?? null, grid: [].concat(o.grid ?? []), axisPointer: o.axisPointer ?? null,
      tooltipTrigger: o.tooltip?.trigger ?? null,
      xAxes: [].concat(o.xAxis).map(ax), yAxes: [].concat(o.yAxis).map(ax),
      graphicTexts: (o.graphic ?? []).map((g) => ({ text: g.style?.text ?? null, x: g.style?.x ?? null, y: g.style?.y ?? null, align: g.style?.textAlign ?? null })),
    };
  };
  out.resE = { fixtures: {}, linear: {}, evaluators: {}, catalogue: {}, tables: {} };
  out.resE.exports = { views: rs.RES_VIEWS, refs, steps: rs.RATIO_STEPS, grid: rs.E_GRID_STEP_GEV, linearPx: rs.LINEAR_VIEW_PX,
    energyPx: rs.ENERGY_VIEW_PX, forms: rs.ENERGY_FORMS,
    resolutionView: ['energy', 'linear', undefined, 'bogus', null].map((v) => rs.resolutionView(v)) };
  const cat = await imp('catalog/resolution_refs.js');
  out.resE.catalogue = cat.RESOLUTION_REFERENCES.map((e) => ({ key: e.key, a: e.a, b: e.b, label: cat.referenceLabel(e), equation: cat.referenceEquation(e) }));

  for (const name of %(res)s) {
    const payload = load(name);
    const entry = { models: {}, charts: {}, tables: {} };
    for (const windows of ['anchors', 'all']) {
      for (const reference of refs) {
        const opts = { view: 'energy', windows, shower: 'both', reference, palette: 'viridis', card: 'res-scaling' };
        const key = `${windows}:${reference}`;
        entry.models[key] = packModel(rs.energyModel(payload, opts), reference !== 'e');
        entry.charts[key] = optionOf(payload, opts);
        // The dispatcher hands the E view to energyViewOption.
        entry.charts[key].dispatched = canonical(rs.resolutionScalingOption(payload, opts, RE)) === canonical(rs.energyViewOption(payload, opts, RE).option);
      }
      entry.tables[windows] = rs.fitTableRows(payload, { view: 'energy', windows, shower: 'both' });
      for (const shower of ['a', 'b']) {
        const opts = { view: 'energy', windows, shower, reference: 'deposit' };
        entry.models[`${windows}:deposit:${shower}`] = packModel(rs.energyModel(payload, opts), false);
        entry.charts[`${windows}:deposit:${shower}`] = optionOf(payload, opts);
      }
      // The 1/√E view is untouched: no view, view 'linear' and any other view give one option and one table.
      for (const shower of ['both', 'a', 'b']) {
        const base = { windows, shower, palette: 'viridis', card: 'res-scaling' };
        const variants = [base, { ...base, view: 'linear' }, { ...base, view: 'bogus' }, { ...base, reference: 'pi' }];
        const opts = variants.map((o) => canonical(rs.resolutionScalingOption(payload, o, { width: 760, height: 420 })));
        const walks = variants.map((o) => JSON.stringify(walk(rs.resolutionScalingOption(payload, o, { width: 760, height: 420 }))));
        const tables = variants.map((o) => JSON.stringify(rs.fitTableRows(payload, o)));
        out.resE.linear[`${name}:${windows}:${shower}`] = {
          option: opts.every((t) => t === opts[0]), walk: walks.every((t) => t === walks[0]), table: tables.every((t) => t === tables[0]),
          modelOf: JSON.stringify(rs.resolutionModel(payload, base)?.y) === JSON.stringify(rs.resolutionModel(payload, variants[1])?.y),
        };
      }
      // The evaluators, from the fit blocks alone: pinned and affine at E = 1/x² of the server's own curve rows;
      // quadrature at fixed energies (the Python side holds it to rfit.band on a Fit rebuilt from the block).
      for (const s of payload.series) {
        for (const form of ['affine', 'pinned', 'quadrature']) {
          const fit = s.fits[windows][form];
          if (!fit) continue;
          const key = `${name}:${windows}:${s.key}:${form}`;
          if (form === 'quadrature') {
            const energies = [0.5, 1, 2, 3.5, 4, 5, 7.5, 10, 16, 20, 40, 80];
            out.resE.evaluators[key] = { energies, js: rs.fitCurveE(fit, energies), drawable: rs.quadratureDrawable(fit) };
          } else {
            const rows = (fit.curve ?? []).filter((c) => c[0] > 0);
            out.resE.evaluators[key] = { server: rows, js: rs.fitCurveE(fit, rows.map((c) => 1 / (c[0] * c[0]))) };
          }
        }
      }
    }
    out.resE.fixtures[name] = entry;
  }

  // Variants of the two-shower payload, changed only where the server would change them.
  const two = load('res_scaling_two');
  const undefinedB = clone(two);
  undefinedB.series.find((x) => x.key === 'network:b').fits.all.quadrature.params.b_defined = false;
  const undefinedA = clone(two);
  undefinedA.series.find((x) => x.key === 'detector:b').fits.all.quadrature.params.a_defined = false;
  const undef = (p) => {
    const m = rs.energyModel(p, { windows: 'all', reference: 'deposit' });
    return { model: packModel(m, false), chart: optionOf(p, { windows: 'all', reference: 'deposit' }),
      table: rs.fitTableRows(p, { view: 'energy', windows: 'all' }) };
  };
  out.resE.undefinedB = undef(undefinedB);
  out.resE.undefinedA = undef(undefinedA);
  // A lower E-view top: windows above it are off scale, each with a caret and the canvas note.
  const off = clone(two);
  off.axis.energy.y.hi = 90; off.axis.energy.y.interval = 10;
  out.resE.offScale = { model: packModel(rs.energyModel(off, { windows: 'all', reference: 'deposit' }), false),
    chart: optionOf(off, { windows: 'all', reference: 'deposit' }),
    narrow: optionOf(off, { windows: 'all', reference: 'deposit' }, { width: 420, height: 600 }) };
  const prov = clone(two);
  prov.axis.energy.y.provisional = true;
  out.resE.provisional = optionOf(prov, { windows: 'anchors' });
  // Empty states: no response, no E axis, no window on the axis.
  const noAxis = clone(two);
  delete noAxis.axis.energy;
  const none = clone(two);
  for (const s of none.series) for (const w of s.windows) { w.value = null; w.n = 1; }
  for (const s of none.series) for (const mode of ['anchors', 'all']) { s.fits[mode] = { points: [], substitutions: [], fallback: false, provisional: false, span_gev: null, affine: null, pinned: null, quadrature: null }; }
  out.resE.empty = {
    nothing: optionOf(null, { view: 'energy' }), noAxis: optionOf(noAxis, { view: 'energy' }), none: optionOf(none, { view: 'energy', windows: 'all' }),
    noAxisModel: rs.energyModel(noAxis, {}), linearNone: walk(rs.resolutionScalingOption(none, { windows: 'all' }, RE)).graphics,
  };
  // Pure helpers.
  out.resE.helpers = {
    grid: rs.energyGrid(4, 6, [5.1, 7, 3]),
    gridEnds: (() => { const g = rs.energyGrid(4, 80, [7, 16]); return [g[0], g[g.length - 1], g.length, g.includes(7), g.includes(16)]; })(),
    ranges: [
      rs.ratioRange([{ value: 1.3, lo: 0.9, hi: 1.6, robust: true }, { value: 9, marker: true }]),
      rs.ratioRange([{ value: 0.5, marker: true }, { value: 1.2, marker: true }]),
      rs.ratioRange([]),
      rs.ratioRange([{ value: 40, robust: true }]),
      rs.ratioRange([{ value: 1.05, robust: true }]),
      rs.ratioRange([{ value: 0.3, robust: true }]),
    ],
    ticks: [[1.5, 120], [2, 120], [4, 120], [10, 120], [1.1, 120], [10, 45]].map(([k, h]) => rs.ratioTicks(k, h)),
    drawable: [
      rs.quadratureDrawable({ params: { a_defined: true, b_defined: true, rho_a2b2: -0.9, a2: 1, b2: 1 } }),
      rs.quadratureDrawable({ params: { a_defined: true, b_defined: true, rho_a2b2: null, a2: 1, b2: 1 } }),
      rs.quadratureDrawable({ params: { a_defined: false, b_defined: true, rho_a2b2: -0.9, a2: -1, b2: 1 } }),
      rs.quadratureDrawable(null),
    ],
  };
  // B's lines at 70%% strength never fall below 3:1, on the dark card and on the light one.
  const inkOf = () => {
    const card = cp.rgbOf(scale.THEME.card);
    const m = rs.energyModel(two, { windows: 'all', reference: 'deposit' });
    return m.series.map((s) => ({ key: s.key, isB: s.isB, opacity: s.lineOpacity(false), provisional: s.lineOpacity(true),
      contrast: palette.contrast(cp.blendOver(s.colour, s.lineOpacity(false)), card),
      contrastProvisional: palette.contrast(cp.blendOver(s.colour, s.lineOpacity(true)), card),
      wanted: cp.legibleOpacity(s.colour, 0.7) }));
  };
  out.resE.ink = { dark: inkOf() };
  scale.setScreenTheme('light');
  out.resE.ink.light = inkOf();
  out.resE.lightChart = optionOf(two, { windows: 'all', reference: 'pi' });
  scale.setScreenTheme('dark');

  // The class: the plot is ENERGY_VIEW_PX tall in the E view, the CSS height in the 1/√E view; the E export is two panels tall.
  const el = { clientWidth: 760, clientHeight: 420, style: {}, classList: { toggle: () => {} }, closest: () => null };
  let resized = 0;
  let lastOption = null;
  const fake = { getWidth: () => el.clientWidth, getHeight: () => el.clientHeight, setOption: (o) => { lastOption = o; },
    resize: () => { resized += 1; }, clear: () => {}, getDom: () => el, dispatchAction: () => {} };
  const savedEcharts = globalThis.echarts;
  globalThis.echarts = { init: () => fake };
  const panel = new rs.ResolutionScalingPanel(el, { card: 'res-scaling' });
  const cls = {};
  panel.render(two, { windows: 'all', shower: 'both' });
  cls.linearFirst = { height: el.style.height ?? null, resized };
  const linearExport = panel.exportMetrics(321);
  panel.render(two, { view: 'energy', windows: 'all', shower: 'both', reference: 'deposit' });
  cls.energy = { height: el.style.height, resized, grids: [].concat(lastOption.grid).length, liveGrid: Array.isArray(panel.liveGrid) ? panel.liveGrid.length : 1,
    export: panel.exportMetrics(321), exportWide: panel.exportMetrics(661),
    built: Object.keys(panel.buildOption({ payload: two, opts: { view: 'energy' }, metrics: RE })) };
  panel.relayout();
  cls.relayoutResized = resized;
  panel.render(two, { view: 'linear', windows: 'all', shower: 'both' });
  cls.linear = { height: el.style.height, resized, grids: [].concat(lastOption.grid).length, export: panel.exportMetrics(321), exportBefore: linearExport,
    built: Object.keys(panel.buildOption({ payload: two, opts: { view: 'linear' }, metrics: { width: 760, height: 420 } })) };
  out.resE.cls = cls;
  globalThis.echarts = savedEcharts;
}

/* ---- res-scaling: the E view's drawer (models_notes.js) --------------------------- */
{
  const packN = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
    sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
  const stubState = { isTouched: () => false, get: () => null };
  // What the drawer must agree with: the panel's own model, read through nothing but its fields.
  const facts = (m) => ({
    nPoints: m.nPoints, nLines: m.nLines, clipped: m.clipped, ratioClipped: m.ratio.clipped, belowNotDrawn: m.ratio.belowNotDrawn,
    offScale: m.offScale.map((g) => ({ label: g.label, entries: g.entries.map((e) => ({ short: e.short, n: e.n })) })),
    k: m.ratio.k, ratioProvisional: m.ratio.provisional, yProvisional: m.y.provisional, nClippedServer: m.y.n_clipped,
    flag: m.reference.flag, label: m.reference.label, literature: m.reference.literature?.key ?? null,
    spansShared: m.spans.shared, span: m.spans.span, spanList: m.spans.bySeries.map((b) => ({ form: b.form, span: b.span })),
    notDrawn: m.series.flatMap((s) => rs.ENERGY_FORMS.filter((f) => !s.fits[f].drawable)
      .map((f) => ({ label: s.label, form: f, reason: s.fits[f].reason }))),
    drawn: m.series.flatMap((s) => rs.ENERGY_FORMS.filter((f) => s.fits[f].drawable).map((f) => ({
      label: s.label, form: f, provisional: s.fits[f].provisional, converged: s.fits[f].converged,
      cut: Boolean(s.fits[f].cut), floorCut: Boolean(s.fits[f].floorCut) }))),
    anyUnconverged: m.series.some((s) => [s.mf?.affine, s.mf?.pinned, s.mf?.quadrature].some((f) => f && f.converged === false)),
    points: { weak: m.series.flatMap((s) => s.points).filter((p) => p.weak).length, weakAlone: m.series.flatMap((s) => s.points).filter((p) => p.weak && !p.subFloor && !p.fitted).length,
      subFloor: m.series.flatMap((s) => s.points).filter((p) => p.subFloor).length, below4: m.series.flatMap((s) => s.points).filter((p) => p.below4).length,
      ratioWhiskers: m.series.flatMap((s) => s.points).filter((p) => p.ratio.drawn && Number.isFinite(p.ratio.lo)).length },
    noReference: m.ratio.noReference, anyB: m.series.some((s) => s.isB),
    deposit: Object.values(m.reference.byShower).map((r) => ({ shower: r.shower, reason: r.reason, why: r.why, provisional: r.provisional })),
    notes: m.notes, rule: m.rule, noteText: m.noteText, nShowers: m.nShowers, mode: m.mode,
    bandsOutlined: { main: m.bandsOutlined.main, ratio: m.bandsOutlined.ratio }, capped: m.ratio.capped,
  });
  const run = (payload, opts) => {
    const model = rs.energyModel(payload, opts);
    const notes = mn.resolutionScalingNotes({ payload, state: stubState, experiment: { display_name: 'Demo' }, ...opts, view: 'energy' });
    return { notes: packN(notes), hazards: mn.modelsHazards(payload, 'res-scaling', { ...opts, view: 'energy' }), facts: model ? facts(model) : null };
  };
  out.resNotes = { fixtures: {}, linear: {}, variants: {}, titles: {} };
  for (const name of %(res)s) {
    const payload = load(name);
    const entry = {};
    for (const windows of ['anchors', 'all']) {
      for (const reference of rs.RATIO_REFERENCES) {
        for (const shower of ['both', 'a', 'b']) entry[`${windows}:${reference}:${shower}`] = run(payload, { windows, shower, reference });
      }
      // The 1/√E drawer and hazards are one output whatever the view or the reference.
      for (const shower of ['both', 'a', 'b']) {
        const base = { payload, state: stubState, experiment: { display_name: 'Demo' }, windows, shower };
        const variants = [base, { ...base, view: 'linear' }, { ...base, view: 'bogus', reference: 'pi' }, { ...base, reference: 'e' }];
        const texts = variants.map((o) => JSON.stringify(mn.resolutionScalingNotes(o)));
        const hz = [{ windows, shower }, { windows, shower, view: 'linear' }, { windows, shower, view: 'bogus', reference: 'pi' }]
          .map((o) => JSON.stringify(mn.modelsHazards(payload, 'res-scaling', o)));
        out.resNotes.linear[`${name}:${windows}:${shower}`] = {
          notes: texts.every((t) => t === texts[0]), hazards: hz.every((t) => t === hz[0]),
          title: JSON.parse(texts[0]).title, text: JSON.parse(texts[0]).sections.map((x) => x.lines.join(' ')).join(' '),
        };
      }
    }
    out.resNotes.fixtures[name] = entry;
  }
  // Variants of the two-shower payload, changed only where the server would change them.
  const two = load('res_scaling_two');
  const off = clone(two);
  off.axis.energy.y.hi = 90; off.axis.energy.y.interval = 10;
  out.resNotes.variants.offScale = run(off, { windows: 'all', reference: 'deposit' });
  const lowTop = clone(two);
  lowTop.axis.energy.y.hi = 30; lowTop.axis.energy.y.interval = 10;
  out.resNotes.variants.literatureClipped = run(lowTop, { windows: 'all', reference: 'pi' });
  const prov = clone(two);
  prov.axis.energy.y.provisional = true;
  out.resNotes.variants.yProvisional = run(prov, { windows: 'anchors', reference: 'deposit' });
  const thin = clone(two);
  for (const s of thin.series) for (const w of s.windows) w.n = Math.min(w.n ?? 0, 10);
  for (const s of thin.series) for (const mode of ['anchors', 'all']) {
    s.fits[mode].provisional = true;
    for (const f of [s.fits[mode].affine, s.fits[mode].pinned, s.fits[mode].quadrature]) if (f) f.provisional = true;
  }
  out.resNotes.variants.ratioProvisional = run(thin, { windows: 'all', reference: 'deposit' });
  const unsettled = clone(two);
  const uf = unsettled.series.find((x) => x.key === 'network:b').fits.anchors.pinned;
  uf.converged = false; uf.iterations = 200;
  out.resNotes.variants.unsettled = run(unsettled, { windows: 'anchors', reference: 'deposit' });
  const undefinedB = clone(two);
  undefinedB.series.find((x) => x.key === 'network:b').fits.all.quadrature.params.b_defined = false;
  out.resNotes.variants.undefinedB = run(undefinedB, { windows: 'all', reference: 'deposit' });
  const noAxis = clone(two);
  delete noAxis.axis.energy;
  out.resNotes.variants.noAxis = run(noAxis, { windows: 'all', reference: 'deposit' });
  out.resNotes.variants.nothing = [mn.resolutionScalingNotes({ payload: null, view: 'energy' }), mn.modelsHazards(null, 'res-scaling', { view: 'energy' })];
  const none = clone(two);
  for (const s of none.series) for (const w of s.windows) { w.value = null; w.n = 1; }
  for (const s of none.series) for (const mode of ['anchors', 'all']) { s.fits[mode] = { points: [], substitutions: [], fallback: false, provisional: false, span_gev: null, affine: null, pinned: null, quadrature: null }; }
  out.resNotes.variants.empty = run(none, { windows: 'all', reference: 'deposit' });
  const sampled = clone(two);
  sampled.meta = { ...(sampled.meta ?? {}), exact: false };
  out.resNotes.variants.sampled = run(sampled, { windows: 'all', reference: 'deposit' });
  // Titles: the shell's wins; the E view has its own default.
  const titled = (view, title) => mn.resolutionScalingNotes({ payload: two, view, title }).title;
  out.resNotes.titles = { linear: titled('linear'), energy: titled('energy'), given: titled('energy', 'Card title'),
    constants: [mn.RES_SCALING_TITLE, mn.RES_SCALING_ENERGY_TITLE] };
}

/* ---- res-scaling: the E view's review fix round (fixes.md part A, P1-P15 and N1-N4) ---- */
{
  const RE = { width: 760, height: 600 };
  const stubState = { isTouched: () => false, get: () => null };
  const notesOf = (payload, opts) => {
    const n = mn.resolutionScalingNotes({ payload, state: stubState, experiment: { display_name: 'Demo' }, ...opts, view: 'energy' });
    return n ? { title: n.title, hazards: n.hazards, sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null;
  };
  const graphicsOf = (o) => (o.graphic ?? []).map((g) => ({ text: g.style?.text ?? null, x: g.style?.x ?? null, y: g.style?.y ?? null,
    align: g.style?.textAlign ?? null, font: g.style?.fontSize ?? null, lineHeight: g.style?.lineHeight ?? null }));
  // The drawn style of every band edge (a series '<id>|edges|<solid|dashed>|<i>'), with its tooltip.
  const edgesOf = (o) => o.series.filter((s) => (s.id ?? '').includes('|edges|')).map((s) => {
    const el = s.renderItem({ dataIndex: 0, coordSys }, api);
    return { id: s.id, name: s.name, xAxisIndex: s.xAxisIndex ?? 0, stroke: el.style.stroke, width: el.style.lineWidth,
      opacity: el.style.opacity, dash: el.style.lineDash ?? null, points: el.shape.points, tip: s.tooltip.formatter({ dataIndex: 0 }) };
  });
  const labelsOf = (o) => o.series.filter((s) => (s.id ?? '').endsWith('|endlabels')).map((s) => {
    const el = s.renderItem({ dataIndex: 0, coordSys }, api);
    return { id: s.id, name: s.name, clip: s.clip, silent: s.silent, xAxisIndex: s.xAxisIndex ?? 0,
      texts: el.children.map((c) => ({ text: c.style.text, fill: c.style.fill, x: c.style.x, y: c.style.y, align: c.style.textAlign })) };
  });
  const two = load('res_scaling_two');
  const fix = {};

  // P1: a ν = 1 quadrature fit whose errors S = 1.5 scales, so its band takes Student's t₀.₉₇₅,₁ = 12.71, on a top
  // of 300%% where its edges cross the plot (at S = 3.6 both edges lie beyond it, and nothing of the band is drawn).
  const t12 = clone(two);
  t12.axis.energy.y.hi = 300; t12.axis.energy.y.interval = 50;
  {
    const q = t12.series.find((x) => x.key === 'network:a').fits.anchors.quadrature;
    q.scale_factor = 1.5; q.band_quantile = 12.7062;
    for (const key of ['se_a2', 'se_b2', 'se_a', 'se_b']) q.params[key] *= 1.5;
  }
  const t12opts = { view: 'energy', windows: 'anchors', shower: 'both', reference: 'deposit' };
  {
    const m = rs.energyModel(t12, t12opts);
    const s = m.series.find((x) => x.key === 'network:a');
    const f = s.fits.quadrature;
    const built = rs.energyViewOption(t12, t12opts, RE).option;
    fix.outlined = {
      main: m.bandsOutlined.main, ratio: m.bandsOutlined.ratio,
      entries: m.bandsOutlined.entries.map((b) => ({ panel: b.panel, key: b.key, form: b.form, reference: b.reference })),
      outlined: f.outlined, ratioOutlined: f.ratio?.outlined ?? null, span: f.span, curve: f.curve, ratioRows: f.ratio?.rows ?? null,
      k: m.ratio.k, yhi: m.y.hi, colour: s.colour, edgeOpacity: cp.legibleOpacity(s.colour, 0.5), lineAxis: scale.THEME.lineAxis,
      edges: edgesOf(built), chart: walk(built), notes: notesOf(t12, t12opts),
      hazards: mn.modelsHazards(t12, 'res-scaling', t12opts), hazardsBase: mn.modelsHazards(two, 'res-scaling', t12opts),
      // Every fixture fit judged by the rule itself, re-derived here from its rows: [key, form, panel, outlined,
      // some in-span row whose part inside the axis covers half of it or more, on the panel's own scale].
      fixtures: %(res)s.flatMap((name) => ['anchors', 'all'].flatMap((windows) => ['deposit', 'pi', 'e'].flatMap((reference) => {
        const mm = rs.energyModel(load(name), { windows, reference });
        const inSpan = (rows, span) => rows.filter((r) => r[0] >= span[0] - 1e-9 && r[0] <= span[1] + 1e-9);
        const halfLin = (r) => Math.min(r[3], mm.y.hi) - Math.max(r[2], 0) >= 0.5 * mm.y.hi;
        const lk = Math.log(mm.ratio.k);
        const halfLog = (r) => Math.min(Math.log(r[3]), lk) - Math.max(r[2] > 0 ? Math.log(r[2]) : -Infinity, -lk) >= 0.5 * 2 * lk;
        const out = [];
        for (const x of mm.series) {
          for (const form of rs.ENERGY_FORMS) {
            const ff = x.fits[form];
            if (!ff.drawable) continue;
            out.push([name, windows, reference, x.key, form, 'main', ff.outlined, inSpan(ff.curve, ff.span).some(halfLin)]);
            if (ff.ratio) out.push([name, windows, reference, x.key, form, 'ratio', ff.ratio.outlined,
              inSpan(ff.ratio.rows, ff.span).some(halfLog)]);
          }
        }
        for (const r of Object.values(mm.reference.byShower)) {
          if (!r.band) continue;
          const rows = [...r.band.below, ...r.band.inside, ...r.band.above];
          out.push([name, windows, reference, r.series, r.form, 'reference', r.outlined,
            inSpan(rows, r.span).some(halfLog)]);
        }
        return out;
      }))),
    };
  }

  // P1 on the deposit reference's own band about 1: shower B's quadrature reference, ν = 1 and S = 3. (A pinned
  // reference's band about 1 is 1 ± q·SE(a₀)/a₀ at every E, so once wider than the axis no edge of it is on the plot.)
  const refWide = clone(two);
  {
    const q = refWide.series.find((x) => x.key === 'detector:b').fits.anchors.quadrature;
    q.scale_factor = 3; q.band_quantile = 12.7062;
    for (const key of ['se_a2', 'se_b2', 'se_a', 'se_b']) q.params[key] *= 3;
  }
  {
    const mm = rs.energyModel(refWide, t12opts);
    const ref = mm.reference.byShower.b;
    const built = rs.energyViewOption(refWide, t12opts, RE).option;
    fix.refOutlined = { outlined: ref.outlined, cut: ref.bandCut, form: ref.form, series: ref.series, muted: scale.THEME.muted,
      edgeOpacity: cp.legibleOpacity(scale.THEME.muted, 0.5), entries: mm.bandsOutlined.entries.map((b) => ({ panel: b.panel, key: b.key, reference: b.reference })),
      ratio: mm.bandsOutlined.ratio, edges: edgesOf(built).filter((e) => e.id.startsWith('detector:b|ratio|reference|edges|')),
      washes: built.series.filter((x) => (x.id ?? '').startsWith('detector:b|ratio|reference|band|')).length,
      notes: notesOf(refWide, t12opts) };
  }
  fix.tickLabels = [0.5, 1 / 3, 1 / 1.5, 0.8, 1, 1.25, 2, 50, 1 / 50, 1 / 1.1].map((v) => rs.ratioTickLabel(v));

  // P2: end labels in a column beside the plot; shower B's strength as drawn.
  fix.labels = {};
  for (const [key, payload, opts] of [
    ['two:anchors:deposit:both', two, { windows: 'anchors', reference: 'deposit', shower: 'both' }],
    ['two:all:pi:both', two, { windows: 'all', reference: 'pi', shower: 'both' }],
    ['two:all:deposit:a', two, { windows: 'all', reference: 'deposit', shower: 'a' }],
    ['two:all:e:b', two, { windows: 'all', reference: 'e', shower: 'b' }],
    ['low:all:deposit:both', (() => { const low = clone(two); low.axis.energy.y.hi = 30; low.axis.energy.y.interval = 10; return low; })(),
      { windows: 'all', reference: 'deposit', shower: 'both' }],
    ['xgb:all:deposit:both', load('res_scaling_xgb'), { windows: 'all', reference: 'deposit', shower: 'both' }],
    ['xgb:all:e:both', load('res_scaling_xgb'), { windows: 'all', reference: 'e', shower: 'both' }],
  ]) {
    const o = { view: 'energy', ...opts };
    const mm = rs.energyModel(payload, o);
    const built = rs.energyViewOption(payload, o, RE).option;
    fix.labels[key] = {
      twoOnShow: mm.twoOnShow, endLabels: mm.endLabels, k: mm.ratio.k, yhi: mm.y.hi, xmax: mm.x.max,
      fits: mm.series.flatMap((s) => rs.ENERGY_FORMS.filter((form) => s.fits[form].drawable).map((form) => ({
        key: s.key, shower: s.raw.shower ?? null, colour: s.colour, form, end: s.fits[form].curve.at(-1),
        ratioEnd: s.fits[form].ratio ? s.fits[form].ratio.rows.at(-1) : null }))),
      literature: mm.literature.map((l) => ({ key: l.key, label: l.label, legend: l.legend })),
      series: labelsOf(built), grid: built.grid, pad: scale.axisPadding(), muted: scale.THEME.muted, fontTip: scale.THEME.fontTip,
      bTips: walk(built).series.filter((s) => /^(detector|network):b\|(quadrature|pinned)\|(solid|dashed)\|/.test(s.id ?? '')).map((s) => s.items[0].tip),
      bOpacity: Object.fromEntries(mm.series.filter((s) => s.isB).map((s) => [s.key, s.lineOpacity(false)])),
      notes: notesOf(payload, o),
    };
  }
  scale.setScreenTheme('light');
  fix.lightB = {
    notes: notesOf(two, { windows: 'all', reference: 'deposit', shower: 'both' }),
    strengths: rs.energyModel(two, { windows: 'all', reference: 'deposit' }).series.filter((s) => s.isB).map((s) => ({ short: s.short, op: s.lineOpacity(false) })),
  };
  scale.setScreenTheme('dark');
  fix.spread = [
    rs.spreadLabels([100, 101, 102, 300], 12, 0, 400),
    rs.spreadLabels([5, 6], 12, 0, 400),
    rs.spreadLabels([395, 396, 398], 12, 0, 400),
    rs.spreadLabels([50, 10, 30], 12, 0, 400),
    rs.spreadLabels([], 12, 0, 400),
  ];

  // P3: the canvas note at five widths, on screen and in print; an off-scale list whose first token is wider than its room.
  const off = clone(two);
  off.axis.energy.y.hi = 90; off.axis.energy.y.interval = 10;
  const offOpts = { view: 'energy', windows: 'all', reference: 'deposit', shower: 'both' };
  const noteCase = (width, height) => {
    const built = rs.energyViewOption(off, offOpts, { width, height }).option;
    const mm = rs.energyModel(off, offOpts);
    return { width, height, graphics: graphicsOf(built), grid: built.grid, extrapolation: mm.noteText.extrapolation, offScale: mm.noteText.offScale,
      fontTip: scale.THEME.fontTip, padLeft: scale.axisPadding().left };
  };
  fix.note = { screen: [321, 360, 440, 760, 1100].map((w) => noteCase(w, 600)) };
  fix.gap = { screen: scale.THEME.fontLabel };
  Object.assign(scale.THEME, PRINT_TOKENS);
  fix.note.print = [321, 360, 440, 760, 1100].map((w) => noteCase(w, rs.energyExportMetrics(off, offOpts, w, 0.62).height));
  fix.note.export = { off: rs.energyExportMetrics(off, offOpts, 321, 0.62).height, two: rs.energyExportMetrics(two, offOpts, 321, 0.62).height,
    offTop: [].concat(rs.energyViewOption(off, offOpts, { width: 321, height: 600 }).option.grid)[0].top,
    twoTop: [].concat(rs.energyViewOption(two, offOpts, { width: 321, height: 600 }).option.grid)[0].top };
  fix.gap.print = scale.THEME.fontLabel;
  fix.gap.printGrid = rs.energyViewOption(two, offOpts, { width: 321, height: 600 }).option.grid;
  scale.restoreScreenTheme();

  // P6, P7: the class keeps 420 px for the E view's empty state, and clear() drops the 600 px.
  {
    const el = { clientWidth: 760, clientHeight: 420, style: {}, classList: { toggle: () => {} }, closest: () => null };
    const fake = { getWidth: () => el.clientWidth, getHeight: () => el.clientHeight, setOption: () => {},
      resize: () => {}, clear: () => {}, getDom: () => el, dispatchAction: () => {} };
    const saved = globalThis.echarts;
    globalThis.echarts = { init: () => fake };
    const none = clone(two);
    for (const s of none.series) for (const w of s.windows) { w.value = null; w.n = 1; }
    for (const s of none.series) for (const mode of ['anchors', 'all']) { s.fits[mode] = { points: [], substitutions: [], fallback: false, provisional: false, span_gev: null, affine: null, pinned: null, quadrature: null }; }
    const panel = new rs.ResolutionScalingPanel(el, { card: 'res-scaling' });
    const eo = { view: 'energy', windows: 'all', shower: 'both', reference: 'deposit' };
    panel.render(none, eo);
    fix.cls = { empty: el.style.height ?? null, emptyDraws: rs.energyDrawsPanels(none, eo), drawsTwo: rs.energyDrawsPanels(two, eo) };
    panel.render(two, eo);
    fix.cls.drawn = el.style.height;
    panel.clear();
    fix.cls.cleared = el.style.height;
    panel.render(two, eo);
    fix.cls.again = el.style.height;
    panel.render(none, eo);
    fix.cls.emptyAfter = el.style.height;
    globalThis.echarts = saved;
  }

  // P8: under a literature reference every ratio mark says the curve carries no interval; a clone that clips a
  // ratio fit (t12) and a literature curve (a low top).
  const t12low = clone(t12);
  t12low.axis.energy.y.hi = 30; t12low.axis.energy.y.interval = 10;
  fix.literatureTips = {
    pi: walk(rs.energyViewOption(t12low, { ...t12opts, reference: 'pi' }, RE).option),
    deposit: walk(rs.energyViewOption(t12low, t12opts, RE).option),
  };

  // P9: a robust ratio mark beyond the last step (×50): capped, said on the axis and in the drawer.
  const big = clone(two);
  {
    const w = big.series.find((x) => x.key === 'network:a').windows.find((x) => x.n >= 20 && x.p_lo >= 4 && Number.isFinite(x.value));
    w.value *= 100; w.ci95 = w.ci95.map((v) => v * 100);
  }
  const bigOpts = { view: 'energy', windows: 'all', reference: 'deposit', shower: 'both' };
  {
    const mb = rs.energyModel(big, bigOpts);
    const built = rs.energyViewOption(big, bigOpts, RE).option;
    fix.capped = { k: mb.ratio.k, capped: mb.ratio.capped, provisional: mb.ratio.provisional, axisName: built.yAxis[1].name,
      notes: notesOf(big, bigOpts), clipped: mb.ratio.clipped,
      ranges: [rs.ratioRange([{ value: 80, robust: true }]), rs.ratioRange([{ value: 1.2, lo: 0.01, hi: 1.5, robust: true }, { value: 2, robust: true }]),
        rs.ratioRange([{ value: 60, marker: true }]), rs.ratioRange([{ value: 30, robust: true }])],
      uncapped: rs.energyModel(two, bigOpts).ratio.capped };
  }

  // P13: a deposit reference band clamped at the ratio axis but not wider than it: one muted caret each.
  {
    const o = { view: 'energy', windows: 'anchors', reference: 'deposit', shower: 'both' };
    const mm = rs.energyModel(two, o);
    const built = rs.energyViewOption(two, o, RE).option;
    const carets = built.series.filter((s) => (s.id ?? '').endsWith('|ratio|reference|caret')).map((s) => ({
      id: s.id, name: s.name, xAxisIndex: s.xAxisIndex ?? 0, fill: s.renderItem({ dataIndex: 0, coordSys }, api).style.fill,
      at: s.data[0], tip: s.tooltip.formatter({ dataIndex: 0 }) }));
    fix.refCaret = { carets, muted: scale.THEME.muted, k: mm.ratio.k, bands: mm.ratio.clipped.bands, ratio: mm.clipped.ratio, clipped: mm.ratio.clipped,
      refs: Object.values(mm.reference.byShower).map((r) => ({ shower: r.shower, series: r.series, outlined: r.outlined ?? null, clipped: r.bandClipped, cut: r.bandCut })),
      notes: notesOf(two, o), hazards: mn.modelsHazards(two, 'res-scaling', o) };
  }

  // N4: a provisional y range set by weaker windows, and one with no window reporting σ/E.
  {
    const prov = clone(two);
    prov.axis.energy.y.provisional = true;
    fix.provisional = { weaker: notesOf(prov, { windows: 'all', reference: 'deposit' }),
      axisName: rs.energyViewOption(prov, { windows: 'all', reference: 'deposit' }, RE).option.yAxis[0].name };
    const bare = clone(prov);
    for (const s of bare.series) for (const w of s.windows) { w.value = null; w.n = 1; }
    fix.provisional.nothing = notesOf(bare, { windows: 'all', reference: 'deposit' });
  }
  // The outline threshold itself: half the axis, on the drawn scale, at one E of the span.
  fix.share = {
    value: rs.OUTLINE_SHARE,
    half: rs.bandSpansShare([[5, 10, 60], [10, 20, 30]], [5, 20], 0, 100),
    under: rs.bandSpansShare([[5, 10, 55], [10, 20, 30]], [5, 20], 0, 100),
    beyondSpan: rs.bandSpansShare([[30, 0, 100]], [5, 20], 0, 100),
    clampedTop: rs.bandSpansShare([[5, 40, 400]], [5, 20], 0, 100),
    clampedShort: rs.bandSpansShare([[5, 60, 400]], [5, 20], 0, 100),
    logHalf: rs.bandSpansShare([[5, 0.45, 2.2]], [5, 20], 0.25, 4, true),
    logUnder: rs.bandSpansShare([[5, 0.6, 1.6]], [5, 20], 0.25, 4, true),
  };
  out.resFix = fix;
}

/* ---- colours a reader must see, against the card on screen and in print ----- */
function measureInk(theme) {
  const card = cp.rgbOf(scale.THEME.card);
  const c = (colour) => palette.contrast(cp.rgbOf(colour), card);
  const res = {};
  res.perf = Object.values(perf.sourceColours(['absolute', 'trans', 'local', 'xgb'])).map(c);
  // The hues themselves, in the order absolute, trans, local, XGBoost; and the checked palette's stops.
  res.perfHues = perf.sourceColours(['xgb', 'local', 'absolute', 'trans']);
  res.qualitative = palette.qualitativeStops(theme === 'screen' ? 'set2' : 'dark2', 4);
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
out.printRes = { chart: walk(rs.resolutionScalingOption(load('res_scaling_two'), { windows: 'all' }, { width: 321, height: 300 })),
  ink: scale.THEME.text, card: scale.THEME.card, hues: perf.sourceColours(['absolute', 'trans', 'local', 'xgb']) };
{
  const opts = { view: 'energy', windows: 'all', reference: 'pi' };
  const height = rs.energyExportMetrics(load('res_scaling_two'), opts, 321, 0.62).height;
  const built = rs.energyViewOption(load('res_scaling_two'), opts, { width: 321, height });
  out.printResE = { chart: walk(built.option), grid: built.option.grid, height, muted: scale.THEME.muted, legendType: built.option.legend.type,
    ink: scale.THEME.text, hues: perf.sourceColours(['absolute', 'trans', 'local', 'xgb']), fontTip: scale.THEME.fontTip,
    noteFont: (built.option.graphic ?? []).map((g) => g.style?.fontSize) };
}
scale.restoreScreenTheme();

console.log(JSON.stringify(out));
"""


def _script() -> str:
    return _SCRIPT % {
        "perf": json.dumps(PERF), "pred": json.dumps(PRED), "hists": json.dumps(HISTS), "corrs": json.dumps(CORRS),
        "describe": json.dumps(DESCRIBE), "palettes": json.dumps(PALETTES), "res": json.dumps(RES),
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
    yield out["pred"]["phiChart"]
    yield out["pred"]["momentum"]
    yield out["perf"]["medianChart"]
    yield out["perf"]["xgbEnergy"]
    yield out["hist2d"]["chartTiny"]
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
                # P-3: a dark casing under the light ink, so the whisker reads over any bar fill.
                el = item["el"]
                assert el["type"] == "group" and len(el["children"]) == 2
                casing, ink = el["children"]
                assert casing["points"] == ink["points"] and ink["points"] in (2, 4, 6)
                assert casing["stroke"] == out["perf"]["casing"] and ink["stroke"] == out["perf"]["ink"]
                assert "95% interval" in item["tip"] and "not the spread of the showers" in item["tip"]


def test_a_bin_of_one_shower_is_a_dot_with_no_whisker(out):
    """D-9: one shower is an observation, not an aggregate: a dot labelled so, never a bar."""
    chart = out["perf"]["weak"]
    (bar,) = [s for s in chart["series"] if s["name"] == "Absolute-frame network · shower A"]
    first = bar["items"][0]
    assert first["el"]["type"] == "circle" and first["el"]["rect"] is None
    assert "one shower" in first["tip"] and "dot" in first["tip"] and "not an aggregate" in first["tip"]
    assert all(i["el"]["type"] == "rect" for i in bar["items"][1:])
    (whisker,) = _named(chart, r"^Absolute-frame network · shower A · 95% interval$")
    assert len(whisker["items"]) == len(bar["items"]) - 1


def test_a_point_without_an_interval_is_weak_whatever_its_n(out):
    """P-4: medians of 2-5 events have no interval, so they are faded, and say which floor they miss."""
    points = out["perf"]["medianPoints"]
    for p in points:
        assert p["weak"] is (p["lo"] is None or p["hi"] is None), p
        assert p["single"] is (p["n"] == 1)
    small = [p for p in points if 2 <= p["n"] < 6]
    assert small, "the recording has medians of 2-5 events"
    for p in small:
        assert p["weak"] and "interval floor, N = 6" in p["tip"] and "faded" in p["tip"]
    bars = [s for s in out["perf"]["medianChart"]["series"] if s["name"].startswith("XGBoost") and "·" not in s["name"]]
    drawn = [i for s in bars for i in s["items"] if i["el"]["type"] == "rect"]
    assert drawn and all(i["el"]["dash"] for i in drawn if "faded" in i["tip"])


def test_the_xgboost_momentum_regressor_is_labelled_momentum(out):
    """P-5: the aggregate's regressor predicts momentum, which is not an energy for μ, π and p."""
    model = out["perf"]["xgbEnergyModel"]
    assert model["momentum"] is True and model["noun"] == "event"
    y = out["perf"]["xgbEnergy"]["yAxis"][0]["name"]
    assert "momentum" in y and "energy" not in y.lower()
    notes = out["notes"]["xgbEnergy"]
    selection = " ".join(line for sec in notes["sections"] if sec["heading"] == "Selection"
                         for line in sec["lines"] if line)
    assert "XGBoost momentum regressor" in selection and "energy network" not in selection
    tips = [i["tip"] for s in out["perf"]["xgbEnergy"]["series"] for i in s["items"] if i["tip"]]
    assert any("χ² interval of the RMSE" in t and "normally distributed residuals" in t for t in tips)
    pred = out["pred"]["momentum"]
    assert any("Predicted momentum" in a["name"] for a in pred["yAxis"])


def test_the_legend_wraps_and_shower_bs_swatch_is_its_wash(out):
    """P-14, P-15: the legend wraps into rows over the plot width; B's swatch matches its bars."""
    lo = out["perf"]["legendOption"]
    assert lo["type"] == "plain" and lo["left"] == lo["gridLeft"] and lo["right"] == lo["gridRight"]
    assert lo["narrowTop"] > lo["wideTop"], "a narrow card takes more legend rows, not a pager"
    assert set(lo["icons"]) == {"rect"}
    for s in out["perf"]["swatches"]:
        style = s["itemStyle"]
        if s["name"].endswith("shower B"):
            assert style["color"].startswith("rgba(") and style["color"].endswith(",0.22)")
            assert style["borderColor"] and style["borderWidth"] == 1
        else:
            assert style["color"].startswith("#") and "borderColor" not in style


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
    # P-22: round steps only; 0.22 and 0.11 (older tops off the grid) never get a quarter of the span.
    assert out["perf"]["ticks"] == pytest.approx([0.02, 0.25, 0.4, 1, 0.05, 1, 0.05, 0.02])


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


@pytest.mark.parametrize("theme", ["screen", "print"])
def test_the_networks_take_the_checked_qualitative_hues_in_the_importance_cards_order(out, theme):
    """E2: palette.js qualitativeStops('set2'|'dark2', 4) in the order absolute, trans, local, XGBoost.

    The order is E5's (absolute, trans, local, none), so a frame reads the same on both cards.
    ColorBrewer's own fourth colours fail the colour-vision check (palette.js); the checked stops do not.
    """
    ink = out["contrast"][theme]
    hues = ink["perfHues"]
    assert [hues[k] for k in ("absolute", "trans", "local", "xgb")] == ink["qualitative"]
    assert "#e78ac3" not in hues.values() and "#e7298a" not in hues.values()


def test_no_rendered_number_uses_an_ascii_hyphen(out):
    for chart in _all_charts(out):
        _no_hyphen_numbers(chart["strings"])


# ------------------------------------------------------------- sources --

NEW_MODULES = ["perf_bins.js", "hist2d.js", "rates.js", "feature_table.js", "resolution_scaling.js"]
CHART_MODULES = ["perf_bins.js", "hist2d.js", "rates.js", "resolution_scaling.js"]


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


# ------------------------------------------------- fix round B additions --


def test_the_azimuth_prediction_axes_span_its_period_in_mrad_with_pi_ticks(out):
    """P-19: φ's axes are [−π, π] in mrad whatever the data, ticked at π/2 and written in π."""
    for axis in out["pred"]["phiAxes"]:
        assert axis["min"] == pytest.approx(-3141.59) and axis["max"] == pytest.approx(3141.59)
        assert axis["interval"] == pytest.approx(1000 * 3.141592653589793 / 2)
        assert axis["labels"] == ["−π", "−π/2", "0", "π/2", "π"]


def test_log_axis_end_labels_only_at_decades_and_the_energy_axis_is_never_y(out):
    """P-23: no 0.316228 end label; P-21: the deposited-energy axis falls back to E, not y."""
    ends = out["hist2d"]["ends"]
    y = ends["y"]
    assert y["min"] == -3.5 and y["max"] == 0.0
    assert y["showMin"] is False and y["showMax"] is True
    assert ends["xHasEnds"] is False, "a linear axis keeps ECharts' default end labels"
    names = out["hist2d"]["tinyNames"]
    assert names and all(not re.match(r"y\b", n) for n in names), names
    assert any(n.startswith("E [GeV]") or "energy" in n for n in names), names


@pytest.mark.parametrize("name", CORRS)
def test_the_feature_card_fades_correlations_indistinguishable_from_none(out, name):
    """D-10: a cell whose 95% interval contains 0 (or has none) is faded; C8's default is untouched."""
    fade = out["corr"][f"{name}:fade"]
    linear = {}
    for i, row in enumerate(fade["matrix"]):
        for j, cell in enumerate(row):
            if cell and not cell["hatched"] and cell["r"] is not None:
                linear[(j, i - 1)] = cell
    assert len(fade["faded"]) == len(linear)
    n_faded = 0
    for item, tip in zip(fade["faded"], fade["tips"]):
        cell = linear[tuple(item["value"][:2])]
        ci = cell["ci95"]
        expected = ci is None or (ci[0] <= 0 <= ci[1])
        assert (item["opacity"] is not None) is expected, (item, ci)
        assert ("faded:" in tip) is expected
        n_faded += expected
    assert all(item["opacity"] is None for item in fade["plain"]), "C8 (no option) is never faded"
    disclosures = next(s["lines"] for s in fade["notes"]["sections"] if s["heading"] == "Disclosures")
    if n_faded:
        assert any(f"{n_faded} cell" in line and "faded" in line for line in disclosures), disclosures


def test_the_residual_drawer_states_the_freedman_diaconis_exception(out):
    """D-8: residual bins follow the IQR of the drawn showers, an exception to Rice stated in the drawer."""
    for name in PRED:
        drawn = out["notes"]["residual"][name]["sections"]["What is drawn"]
        line = next(line for line in drawn if line.startswith("Bins:"))
        assert "Freedman" in line and "Rice" in line and "prediction residuals only" in line


# ------------------------------------------------------------- res-scaling --
#
# The resolution card on the four recorded payloads: σ/E against a reversed
# 1/√E axis that ends at the origin, an exact Energy axis on top carrying no
# data, χ² whiskers only from N = 8, one line and one band per drawn fit and
# none for the quadrature form, and the fit table beneath.

RES_KEYS = [f"{w}:{s}" for w in ("anchors", "all") for s in ("both", "a", "b")]


def _res_shown(payload: dict, shower: str) -> list[dict]:
    n_showers = len({s["shower"] for s in payload["series"]})
    return [s for s in payload["series"] if shower == "both" or n_showers < 2 or s["shower"] == shower]


def _res_drawn_bins(series: dict, windows: str) -> list[int]:
    """The windows a mode draws: the fit's points, or every on-axis window with a value."""
    on_axis = [w for w in series["windows"]
               if w["value"] is not None and not w["off_axis"] and w["p_lo"] >= 4 and w["n"] >= 2]
    if windows == "anchors":
        points = set(series["fits"]["anchors"]["points"])
        return [w["bin"] for w in on_axis if w["bin"] in points]
    return [w["bin"] for w in on_axis]


def _ids(chart: dict, suffix: str, key: str | None = None) -> list[dict]:
    return [s for s in chart["series"] if (s["id"] or "").endswith(suffix) and (key is None or s["id"].startswith(f"{key}|"))]


@pytest.mark.parametrize("name", RES)
def test_res_axes_end_at_the_origin_with_an_exact_energy_axis_on_top(out, name):
    payload = _load(name)
    top = payload["axis"]["top"]
    for key in RES_KEYS:
        axes = out["res"][name]["axes"][key]
        bottom, upper = axes["x"]
        assert bottom["position"] == "bottom" and bottom["inverse"] is True
        assert (bottom["min"], bottom["max"], bottom["interval"]) == (0, 0.5, 0.1)
        assert bottom["name"] == payload["axis"]["x"]["name"]
        assert upper["position"] == "top" and upper["inverse"] is True
        assert (upper["min"], upper["max"]) == (0, 0.5)
        assert upper["tickValues"] == [t["x"] for t in top["ticks"]] == upper["labelValues"]
        assert upper["labels"] == [t["label"] for t in top["ticks"]]
        assert upper["labels"][upper["labelValues"].index(0.0)] == "∞"
        assert upper["name"] == top["name"] and upper["split"] is False
        assert all(i == 0 for i in axes["seriesAxes"]), "no series is plotted against the energy axis"
        (y,) = axes["y"]
        assert y["min"] == 0 and y["max"] == payload["axis"]["y"]["hi"] and y["interval"] == payload["axis"]["y"]["interval"]
        assert ("provisional" in y["name"]) == payload["axis"]["y"]["provisional"]
    assert "provisional" in out["res"]["provisional"]["y"][0]["name"]
    assert "provisional range" in out["res"]["provisionalNotes"]["hazards"]


@pytest.mark.parametrize("name", RES)
def test_res_modes_draw_exactly_their_windows_with_whiskers_from_n_eight(out, name):
    payload = _load(name)
    for key in RES_KEYS:
        windows, shower = key.split(":")
        chart = out["res"][name]["charts"][key]
        model = out["res"][name]["models"][key]
        shown = _res_shown(payload, shower)
        assert [s["key"] for s in model["series"]] == [s["key"] for s in shown]
        for s, m in zip(shown, model["series"]):
            expected = _res_drawn_bins(s, windows)
            assert [p["bin"] for p in m["points"]] == expected, (key, s["key"])
            if windows == "anchors":
                assert sorted(expected) == sorted(s["fits"]["anchors"]["points"])
            by_bin = {w["bin"]: w for w in s["windows"]}
            for p in m["points"]:
                assert p["whisker"] == by_bin[p["bin"]]["whisker"]
            markers = _ids(chart, "|markers", s["key"])
            drawn = [p for p in m["points"] if not p["over"]]
            assert sum(len(x["items"]) for x in markers) == len(drawn)
            whiskers = _ids(chart, "|whiskers", s["key"])
            assert sum(len(x["items"]) for x in whiskers) == sum(1 for p in m["points"] if p["whisker"])
            for x in whiskers:
                for item in x["items"]:
                    assert item["el"]["type"] == "group" and len(item["el"]["children"]) == 2, "the whisker lies on a casing"
                    assert "not the spread of its events" in item["tip"]


def test_res_a_window_below_eight_is_a_faded_ring_without_a_whisker(out):
    thin = out["res"]["thin"]
    (series,) = thin["model"]["series"]
    point = next(p for p in series["points"] if p["bin"] == thin["bin"])
    assert point["subFloor"] and not point["whisker"]
    assert "N = 8 floor" in point["tip"] and "No whisker" in point["tip"]
    whiskers = _ids(thin["chart"], "|whiskers")
    assert sum(len(x["items"]) for x in whiskers) == sum(1 for p in series["points"] if p["whisker"])
    markers = _ids(thin["chart"], "|markers")[0]
    ring = next(i["el"] for i in markers["items"] if "N = 5 " in (i["tip"] or "") or "N = 5 events" in (i["tip"] or ""))
    circle = ring["children"][0] if ring["type"] == "group" else ring
    assert circle["dash"] and circle["opacity"] < 1


@pytest.mark.parametrize("name", RES)
def test_res_a_line_and_a_band_per_drawn_fit_and_none_for_the_quadrature(out, name):
    payload = _load(name)
    for key in RES_KEYS:
        windows, shower = key.split(":")
        chart = out["res"][name]["charts"][key]
        assert not [s for s in chart["series"] if "quadrature" in (s["id"] or "")]
        for s in _res_shown(payload, shower):
            mf = s["fits"][windows]
            for form in ("affine", "pinned"):
                lines = [x for x in chart["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|line|")]
                bands = _ids(chart, f"|{form}|band", s["key"])
                if mf[form] is None:
                    assert not lines and not bands
                    continue
                assert len(lines) >= 1 and len(bands) == 1, (key, s["key"], form)
                tip = bands[0]["items"][0]["tip"]
                assert "95% confidence band" in tip and "not the spread of the events" in tip
                assert not bands[0]["silent"]
                assert "σ/E" in lines[0]["items"][0]["tip"]
                # Clipped to the plot: nothing is drawn below zero or above the range.
                y_hi = payload["axis"]["y"]["hi"]
                for line in lines:
                    for pt in line["items"][0]["el"]["pts"]:
                        assert -1e-9 <= pt[1] <= y_hi + 1e-9


def test_res_a_negative_intercept_runs_down_to_the_axis_and_stops(out):
    (run,) = out["res"]["clip"]
    assert run[0] == pytest.approx([0.1666666, 0], abs=1e-6)
    assert run[-1] == pytest.approx([0.4166666, 15], abs=1e-6)
    xgb = out["res"]["res_scaling_xgb"]["models"]["anchors:both"]
    tip = next(s for s in xgb["series"] if s["key"] == "xgb:a")["fits"]["affine"]["line"]
    assert "b &lt; 0" in tip or "b < 0" in tip
    assert "ν = 0" in tip


def test_res_the_shower_filter_keeps_one_showers_series(out):
    payload = _load("res_scaling_two")
    for windows in ("anchors", "all"):
        for shower in ("a", "b"):
            chart = out["res"]["res_scaling_two"]["charts"][f"{windows}:{shower}"]
            keys = {s["id"].split("|")[0] for s in chart["series"]}
            assert keys == {s["key"] for s in payload["series"] if s["shower"] == shower}
            assert set(chart["legend"]) == {s["label"] for s in payload["series"] if s["shower"] == shower}
    for name in ("res_scaling_single_hits", "res_scaling_single_events"):
        assert out["res"][name]["charts"]["anchors:b"]["legend"] == out["res"][name]["charts"]["anchors:both"]["legend"]


@pytest.mark.parametrize("name", RES)
def test_res_colour_is_the_estimator_and_every_mark_carries_its_series_name(out, name):
    payload = _load(name)
    entry = out["res"][name]
    for key in RES_KEYS:
        chart = entry["charts"][key]
        shown = _res_shown(payload, key.split(":")[1])
        assert chart["legend"] == [s["label"] for s in shown]
        labels = {s["key"]: s["label"] for s in shown}
        for series in chart["series"]:
            assert series["name"] == labels[series["id"].split("|")[0]]
        for s, m in zip(shown, entry["models"][key]["series"]):
            expected = entry["ink"] if s["colour_slot"] == "detector" else entry["hues"][s["colour_slot"]]
            assert m["colour"] == expected
            for item in (x for markers in _ids(chart, "|markers", s["key"]) for x in markers["items"]):
                el = item["el"]
                if el["type"] == "group":
                    # Shower A's sub-floor ring: the ring in the series' colour, its centre dot filled with it.
                    assert el["children"][0]["stroke"] == expected and el["children"][1]["fill"] == expected
                    continue
                if el["dash"]:
                    assert el["stroke"] == expected and m["isB"], "only shower B's sub-floor ring is a bare ring"
                    continue
                assert (el["stroke"] if m["isB"] else el["fill"]) == expected


def test_res_marks_beyond_the_range_are_clipped_with_carets_carrying_true_values(out):
    clipped = out["res"]["clipped"]
    model = clipped["model"]
    assert model["clipped"]["markers"] > 0 or model["clipped"]["whiskers"] > 0
    carets = _ids(clipped["chart"], "|carets")
    tips = [i["tip"] for c in carets for i in c["items"]]
    # A window's caret says it is clipped; a fit's says where its line or band leaves the plot.
    assert tips and all("clipped at the" in t or "leaves the top of the" in t for t in tips)
    over = [p for s in model["series"] for p in s["points"] if p["over"]]
    cut = [f for s in model["series"] for f in s["fits"].values() if f and f["cut"]]
    assert sum("clipped at the" in t for t in tips) >= len(over)
    assert sum("leaves the top of the" in t for t in tips) == len(cut) == model["clipped"]["fits"] > 0
    assert "marks clipped at the axis" in clipped["notes"]["hazards"]
    disclosures = " ".join(clipped["notes"]["sections"]["Disclosures"])
    assert f"{len(cut)} fit" in disclosures and "leave the top of the plot" in disclosures


@pytest.mark.parametrize("name", RES)
def test_res_every_fit_leaving_the_plot_is_clipped_with_a_caret_and_counted(out, name):
    """CLAUDE.md: an estimate beyond the range is clipped and said so. A fit's line or band above y.hi gets a caret
    at the exit with its true values, and the model counts it; a fit inside the range gets none."""
    payload = _load(name)
    for key in RES_KEYS:
        mode, shower = key.split(":")
        model = out["res"][name]["models"][key]
        hi = model["y"]["hi"]
        expected = 0
        for s, m in zip(_res_shown(payload, shower), model["series"]):
            for form in ("affine", "pinned"):
                fit = s["fits"][mode][form]
                got = m["fits"][form]
                if not fit or not fit.get("curve"):
                    continue
                above = max(c[3] for c in fit["curve"]) > hi
                expected += above
                assert bool(got["cut"]) == above, (name, key, s["key"], form)
                if above:
                    peak = max(fit["curve"], key=lambda c: c[3])
                    assert got["cut"]["peak"] == peak
                    assert "leaves the top of the" in got["cutTip"] and "True values" in got["cutTip"]
                    assert "the caret there gives its true values" in got["line"]
        assert model["clipped"]["fits"] == expected, (name, key)


def test_res_with_no_drawable_window_the_panel_says_so(out):
    empty = out["res"]["empty"]
    assert not empty["chart"]["series"]
    assert empty["axes"]["graphics"] and "No momentum window" in empty["axes"]["graphics"][0]
    assert not empty["axes"]["y"][0]["labelShow"]
    assert out["res"]["nothing"]["graphics"]


def _fit_rows(table):
    """{series key: {form: cells}}, the cells from the Fit column on (Fit, a, b, χ²/ν, S, Status)."""
    return {r["key"]: {f["form"]: f["cells"] for f in r["fits"]} for r in table["rows"]}


def test_res_fit_table_rows(out):
    """One row group per series, one row per fit: a, b, χ²/ν (p), S and the status of each, the windows spanning the group."""
    two = out["res"]["res_scaling_two"]["tables"]
    for key in RES_KEYS:
        table = two[key]
        assert table["columns"] == ["Series", "Fit", "a ± SE [%·√GeV]", "b ± SE [%]", "χ²/ν (p)", "S", "Windows fitted", "Status"]
        shower = key.split(":")[1]
        assert [r["key"] for r in table["rows"]] == [s["key"] for s in _res_shown(_load("res_scaling_two"), shower)]
        for r in table["rows"]:
            assert [f["form"] for f in r["fits"]] == ["affine", "pinned", "quadrature"]
            assert all(len(f["cells"]) == 6 for f in r["fits"]) and r["windows"]
    payload = _load("res_scaling_two")
    fits = {s["key"]: s["fits"]["anchors"] for s in payload["series"]}
    rows = _fit_rows(two["anchors:both"])
    windows = {r["key"]: r["windows"] for r in two["anchors:both"]["rows"]}
    for key, by_form in rows.items():
        for form, cells in by_form.items():
            fit = fits[key][form]
            # The S column: S where it scaled the errors, 1 where they stand, — without a χ² test.
            if fit["ndf"] == 0:
                assert cells[4] == "—" and "ν = 0" in cells[3]
            elif fit["scale_factor"] > 1:
                assert cells[4] != "1" and cells[4] != "—"
            else:
                assert cells[4] == "1"
        assert by_form["pinned"][2] == "0 (through the origin)"
        assert by_form["affine"][1].startswith(("−", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
    # An undefined quadrature term is printed as its square with its SE, the defined one as a ± SE.
    for key, by_form in rows.items():
        q = fits[key]["quadrature"]["params"]
        assert ("a undefined" in by_form["quadrature"][1]) == (q["a_defined"] is False), key
        assert ("b undefined" in by_form["quadrature"][2]) == (q["b_defined"] is False), key
    assert any(fits[key]["quadrature"]["params"]["a_defined"] is False for key in rows)
    assert "(for 5–6 GeV)" in windows["detector:a"]
    xgb = out["res"]["res_scaling_xgb"]["tables"]["anchors:both"]
    xrows, xwin = _fit_rows(xgb), {r["key"]: r["windows"] for r in xgb["rows"]}
    assert "b undefined" in xrows["xgb:a"]["quadrature"][2] and "ν = 0" in xrows["xgb:a"]["affine"][3]
    assert all("provisional" in xrows["xgb:a"][form][5] for form in ("affine", "pinned", "quadrature"))
    assert "dropped" in xwin["xgb:a"]
    single = _fit_rows(out["res"]["res_scaling_single_hits"]["tables"]["anchors:both"])["detector:a"]
    assert all("provisional" in cells[5] for cells in single.values())
    assert "S = √(χ²/ν)" in xgb["caption"] and "Student's t" in xgb["caption"]


def test_res_a_fit_that_did_not_settle_says_so_everywhere(out):
    """converged = false reaches the line's tooltip, the table's status, the drawer and the hazards."""
    got = out["res"]["unsettled"]
    assert "Not converged" in got["lineTip"] and "last refit" in got["lineTip"]
    assert got["status"].startswith("not converged in 200 refits") or "not converged in 200 refits" in got["status"]
    assert any("did not settle within 200 refits" in line for line in got["notes"]["sections"]["Disclosures"])
    assert "fit not converged" in got["notes"]["hazards"]
    assert "fit not converged" not in out["res"]["res_scaling_two"]["notes"]["anchors"]["hazards"]


def test_res_the_panel_inserts_its_table_once_after_the_plot_frame(out):
    panel = out["res"]["panel"]
    assert panel["inserted"] == 1 and panel["hostClass"] == "res-fit-table"
    two = _load("res_scaling_two")
    shown = [s["label"] for s in two["series"] if s["shower"] == "a"]
    # One tbody per series: its name heads the group and, with its windows, spans the three fit rows.
    assert panel["tag"] == "table" and panel["kinds"] == ["caption", "thead"] + ["tbody"] * len(shown)
    assert panel["head"][0] == "Series" and len(panel["head"]) == 8
    assert panel["headCls"] == ["text", "text", "num", "num", "num", "num", "text", "text"]
    for label, body in zip(shown, panel["bodies"]):
        assert len(body) == 3 and [len(tr) for tr in body] == [8, 6, 6]
        series, fit = body[0][0], body[0][1]
        assert (series["tag"], series["scope"], series["rowspan"], series["text"]) == ("th", "rowgroup", "3", label)
        assert (fit["tag"], fit["scope"]) == ("th", "row") and fit["text"].startswith("Affine")
        assert body[0][6]["rowspan"] == "3" and body[0][6]["cls"] == "text"
        assert [tr[0]["text"].split()[0] for tr in body[1:]] == ["Origin-pinned", "Quadrature"]
        assert [c["cls"] for c in body[1]] == ["text", "num", "num", "num", "num", "text"]
    assert panel["kind"] == "res-scaling" and panel["series"] > 0
    assert panel["export"]["width"] == 321 and panel["export"]["height"] > 0
    assert panel["cleared"] == 0 and panel["payloadCleared"]


@pytest.mark.parametrize("name", RES)
def test_res_notes_have_the_four_sections_and_name_what_is_drawn(out, name):
    section = out["notes"]["section"]
    for mode in ("anchors", "all", "shownA"):
        n = out["res"][name]["notes"][mode]
        _check_notes(n, section)
        assert n["headings"] == [section["selection"], section["drawn"], section["disclosures"], section["legend"]]
        legend = " ".join(n["sections"][section["legend"]])
        assert "95% χ² interval" in legend and "not the spread of the events" in legend and "confidence band" in legend
        drawn = " ".join(n["sections"][section["drawn"]])
        assert "exact unit conversion" in drawn and "a/√E + b" in drawn and "a₀/√E" in drawn
        disclosures = " ".join(n["sections"][section["disclosures"]])
        assert "quadrature b and the affine b are different" in disclosures
        assert "incident momentum p" in disclosures
        assert "off the axis" in disclosures
    payload = _load(name)
    hazards = out["res"][name]["notes"]["anchors"]["hazards"]
    provisional = any(s["fits"]["anchors"]["provisional"] for s in payload["series"])
    assert ("provisional fit" in hazards) == provisional
    if name == "res_scaling_two":
        disclosures = " ".join(out["res"][name]["notes"]["anchors"]["sections"][section["disclosures"]])
        assert "nearest window from 5 GeV in log E" in disclosures and "S = " in disclosures
        assert "weak windows drawn" in out["res"][name]["notes"]["all"]["hazards"]
    if name == "res_scaling_xgb":
        disclosures = " ".join(out["res"][name]["notes"]["anchors"]["sections"][section["disclosures"]])
        assert "validation split" in disclosures and "negative" in disclosures
        selection = " ".join(out["res"][name]["notes"]["anchors"]["sections"][section["selection"]])
        assert "62 of the 307" in selection


def test_res_print_tokens_build(out):
    printed = out["printRes"]
    chart = printed["chart"]
    assert chart["series"] and chart["legend"]
    for s in chart["series"]:
        if s["id"].startswith("detector:a|markers"):
            assert all(i["el"]["fill"] == printed["ink"] for i in s["items"])
        if s["id"].startswith("network:a|markers"):
            assert all(i["el"]["fill"] == printed["hues"]["absolute"] for i in s["items"])
    _no_hyphen_numbers(chart["strings"])


def test_res_no_rendered_number_uses_an_ascii_hyphen(out):
    for name in RES:
        entry = out["res"][name]
        for key in RES_KEYS:
            _no_hyphen_numbers(entry["charts"][key]["strings"])
            _no_hyphen_numbers(entry["axes"][key]["x"][1]["labels"])
            table = entry["tables"][key]
            _no_hyphen_numbers([table["caption"], *table["columns"], *(r["windows"] for r in table["rows"]),
                                *(c for r in table["rows"] for f in r["fits"] for c in f["cells"])])
        for n in entry["notes"].values():
            _no_hyphen_numbers(line for lines in n["sections"].values() for line in lines)
    _no_hyphen_numbers(out["res"]["clipped"]["chart"]["strings"])


# ------------------------------------------------------- res-scaling: E view --
#
# The card's second view (brief section 4): σ/E against E in GeV on 0 to
# axis.energy.x.max, the origin-pinned a₀/√E ⊕ 0 and, where both terms are
# defined, the quadrature a/√E ⊕ b, solid over the windows each was fitted to
# and dashed beyond, never below 4 GeV; a ratio panel underneath on a log axis
# symmetric about 1. The 1/√E view above is held byte for byte by
# test_js_dark_golden.py; here it is held to one output whatever `view` is
# when it is not 'energy'.

RES_E_REFS = ["deposit", "pi", "e"]
RES_E_KEYS = [f"{w}:{r}" for w in ("anchors", "all") for r in RES_E_REFS]


def _e_axis(name: str) -> dict:
    return _load(name)["axis"]["energy"]


def _e_drawn_fits(model: dict):
    for s in model["series"]:
        for form, f in s["fits"].items():
            if f["drawable"]:
                yield s, form, f


def test_res_e_exports_and_the_view_switch(out):
    e = out["resE"]["exports"]
    assert e["views"] == ["linear", "energy"]
    assert e["refs"] == ["deposit", "pi", "e"] and e["refs"][1:] == [c["key"] for c in out["resE"]["catalogue"]]
    assert e["steps"] == [1.1, 1.25, 1.5, 2, 3, 4, 5, 8, 10, 20, 50], "P9: the ladder ends at 50"
    assert (e["grid"], e["linearPx"], e["energyPx"]) == (0.25, 420, 600)
    assert e["forms"] == ["quadrature", "pinned"]
    assert e["resolutionView"] == ["energy", "linear", "linear", "linear", "linear"]


def test_res_e_the_linear_view_is_untouched_by_view_and_reference(out):
    """No view, view 'linear', any other view and a reference give the 1/√E view's one option and one table."""
    linear = out["resE"]["linear"]
    assert len(linear) == len(RES) * 2 * 3
    for key, same in linear.items():
        assert same == {"option": True, "walk": True, "table": True, "modelOf": True}, key


@pytest.mark.parametrize("name", RES)
def test_res_e_the_dispatcher_draws_the_e_view(out, name):
    for key in RES_E_KEYS:
        assert out["resE"]["fixtures"][name]["charts"][key]["dispatched"], key


#: The wire's six significant figures: the largest relative rounding of any number in a payload.
WIRE_EPS = 5e-6


def _wire_bounds(fit: dict, x: float) -> tuple[float, float]:
    """How far the wire's rounding of a fit block's params can move y and an edge y ± h at x, propagated.

    An affine edge with ρ(a, b) near −1 is a difference of nearly equal terms under the root, so rounding ρ by
    half a unit in its sixth figure moves h by far more than 10⁻⁴ of h (xgb:a: ρ = −0.999695, h moves ±2.3×10⁻⁴).
    """
    p, q = fit["params"], fit["band_quantile"]
    if fit["form"] == "pinned":
        return 2 * WIRE_EPS * abs(p["a0"] * x), 3 * WIRE_EPS * q * p["se_a0"] * x
    t1, t3 = (x * p["se_a"]) ** 2, p["se_b"] ** 2
    t2 = 2 * p["rho_ab"] * x * p["se_a"] * p["se_b"]
    root = max(t1 + t2 + t3, 1e-300) ** 0.5
    dy = WIRE_EPS * (abs(p["a"] * x) + abs(p["b"]))
    dh = q * WIRE_EPS * (2 * t1 + 3 * abs(t2) + 2 * t3) / (2 * root) + WIRE_EPS * q * root
    return dy, dh


@pytest.mark.parametrize("name", RES)
def test_res_e_pinned_and_affine_evaluators_reproduce_the_servers_curve(out, name):
    """fitCurveE at E = 1/x² equals the payload's own [x, y, lo, hi] rows for x > 0, from the params alone:
    to 10⁻⁴, or to the wire's rounding of the params and the rows where that is larger (`_wire_bounds`)."""
    blocks = {(m, s["key"], f): s["fits"][m][f] for s in _load(name)["series"] for m in ("anchors", "all") for f in ("affine", "pinned")}
    checked = 0
    for key, got in out["resE"]["evaluators"].items():
        if not key.startswith(f"{name}:") or key.endswith(":quadrature"):
            continue
        _, mode, source, shower, form = key.split(":")  # name:mode:series key (source:shower):form
        fit = blocks[(mode, f"{source}:{shower}", form)]
        assert len(got["js"]) == len(got["server"]) > 0, key
        for (x, y, lo, hi), (e, jy, jlo, jhi) in zip(got["server"], got["js"]):
            assert e == pytest.approx(1 / (x * x), rel=1e-12)
            dy, dh = _wire_bounds(fit, x)
            for js, server, bound in ((jy, y, dy), (jlo, lo, dy + dh), (jhi, hi, dy + dh)):
                tol = max(1e-4 * abs(server), 2 * (bound + WIRE_EPS * abs(server))) + 1e-9
                assert abs(js - server) <= tol, (key, x, js, server, tol)
            checked += 1
    assert checked > 0


def _quadrature_fit(block: dict):
    """The server's Fit, rebuilt from a wire block: θ = (A, B) as fractions, cov_stat from the unscaled SEs and ρ."""
    import numpy as np
    from calosrv.stats import resolution_fit as rfit

    p = block["params"]
    sa, sb, rho = p["se_a2_stat"] / 1e4, p["se_b2_stat"] / 1e4, p["rho_a2b2"]
    cov = np.array([[sa * sa, rho * sa * sb], [rho * sa * sb, sb * sb]])
    return rfit.Fit("quadrature", block["n_points"], (p["a2"] / 1e4, p["b2"] / 1e4), cov, block["chi2"], block["ndf"],
                    block["p_value"], block["scale_factor"], block["iterations"], block["converged"])


@pytest.mark.parametrize("name", RES)
def test_res_e_the_quadrature_evaluator_equals_rfit_band(out, name):
    """√ of the z = A/E + B band, from a2, b2, their SEs, ρ(A, B) and band_quantile, is the server's band() exactly."""
    import numpy as np
    from calosrv.stats import resolution_fit as rfit

    payload = _load(name)
    checked = 0
    for s in payload["series"]:
        for mode in ("anchors", "all"):
            block = s["fits"][mode]["quadrature"]
            if not block or block["params"].get("rho_a2b2") is None:
                continue
            got = out["resE"]["evaluators"][f"{name}:{mode}:{s['key']}:quadrature"]
            energies = np.array(got["energies"])
            y, lo, hi = (100 * v for v in rfit.band(_quadrature_fit(block), 1 / np.sqrt(energies)))
            assert [r[0] for r in got["js"]] == got["energies"]
            for (e, jy, jlo, jhi), want in zip(got["js"], zip(y, lo, hi)):
                scale = max(abs(v) for v in want) or 1e-9
                assert [jy, jlo, jhi] == pytest.approx(list(want), rel=1e-4, abs=1e-4 * scale), (s["key"], mode, e)
            assert got["drawable"] == (block["params"]["a_defined"] and block["params"]["b_defined"])
            checked += 1
    assert checked > 0


@pytest.mark.parametrize("name", RES)
def test_res_e_windows_sit_at_e_equals_one_over_x_squared(out, name):
    payload = _load(name)
    ax = _e_axis(name)
    for key in RES_E_KEYS:
        windows = key.split(":")[0]
        model = out["resE"]["fixtures"][name]["models"][key]
        for s, m in zip(payload["series"], model["series"]):
            for p in m["points"]:
                assert p["E"] == pytest.approx(1 / (p["x"] * p["x"]), rel=1e-12)
                assert 0 <= p["E"] <= ax["x"]["max"]
            eligible = [w for w in s["windows"] if w["value"] is not None and w["x"] and w["n"] >= 2
                        and 1 / w["x"] ** 2 <= ax["x"]["max"]]
            if windows == "anchors":
                eligible = [w for w in eligible if w["bin"] in s["fits"]["anchors"]["points"]]
            # The all mode draws every window with a value, those below 4 GeV included, as points only.
            assert [p["bin"] for p in m["points"]] == [w["bin"] for w in eligible], (key, s["key"])
            for p in m["points"]:
                assert p["below4"] == (p["pLo"] < ax["curve_min_gev"])
                if p["below4"]:
                    assert p["roles"][0] == "below 4 GeV: no fit uses it; drawn as a point only" and not p["fitted"]
    # Every fixture has windows below 4 GeV; the all mode draws them on this axis.
    assert any(p["below4"] for s in out["resE"]["fixtures"][name]["models"]["all:deposit"]["series"] for p in s["points"])


@pytest.mark.parametrize("name", RES)
def test_res_e_solid_over_the_fitted_span_dashed_beyond_never_below_four_gev(out, name):
    ax = _e_axis(name)
    x_max, floor, top = ax["x"]["max"], ax["curve_min_gev"], ax["y"]["hi"]
    payload = {s["key"]: s for s in _load(name)["series"]}
    seen = 0
    for key in ("anchors:deposit", "all:deposit", "anchors:pi", "all:pi"):
        windows = key.split(":")[0]
        for s, form, f in _e_drawn_fits(out["resE"]["fixtures"][name]["models"][key]):
            span = payload[s["key"]]["fits"][windows]["span_gev"]
            assert f["span"] == span and f["domain"] == [floor, x_max]
            es = [c[0] for c in f["curve"]]
            assert min(es) == floor and max(es) == x_max, "no curve point below 4 GeV; the curve runs to the axis end"
            for run in f["solid"]:
                assert all(span[0] - 1e-9 <= pt[0] <= span[1] + 1e-9 for pt in run)
            for run in f["solid"] + f["dashed"]:
                assert all(pt[0] >= floor - 1e-9 and -1e-9 <= pt[1] <= top + 1e-9 for pt in run)
            by_e = {c[0]: c[1] for c in f["curve"]}
            ends = [pt for run in f["dashed"] for pt in (run[0], run[-1])]
            starts = [run[0] for run in f["solid"]] + [run[-1] for run in f["solid"]]
            for edge in span:
                if span[0] > floor or edge == span[1]:
                    if 0 <= by_e[edge] <= top:
                        # The solid and the dashed part share the edge row exactly.
                        assert [edge, by_e[edge]] in ends and [edge, by_e[edge]] in starts, (s["key"], form, edge)
            if 0 <= by_e[x_max] <= top:
                assert [x_max, by_e[x_max]] in ends, "the dashed part runs to x.max"
            seen += 1
    assert seen > 0


def test_res_e_an_undefined_quadrature_term_is_not_drawn_and_says_why(out):
    for case, key, word in (("undefinedB", "network:b", "B ≤ 0"), ("undefinedA", "detector:b", "A ≤ 0")):
        got = out["resE"][case]
        s = next(x for x in got["model"]["series"] if x["key"] == key)
        quad = s["fits"]["quadrature"]
        assert quad["drawable"] is False and quad["reason"].startswith(word)
        assert s["fits"]["pinned"]["drawable"] is True
        ids = [x["id"] for x in got["chart"]["chart"]["series"]]
        assert not [i for i in ids if i.startswith(f"{key}|quadrature|")]
        assert [i for i in ids if i.startswith(f"{key}|pinned|solid|")]
        row = next(r for r in got["table"]["rows"] if r["key"] == key)
        assert row["fits"][2]["cells"][0] == f"Quadrature a/√E ⊕ b — not drawn: {quad['reason']}"
    # A deposit whose ⊕ fit is not drawable hands the ratio its pinned fit, named so.
    ref = out["resE"]["undefinedA"]["model"]["reference"]["byShower"]["b"]
    assert ref["form"] == "pinned" and ref["series"] == "detector:b" and "a₀/√E" in ref["label"]


@pytest.mark.parametrize("name", RES)
def test_res_e_axes_and_two_grids_on_one_energy_axis(out, name):
    ax = _e_axis(name)
    for key in RES_E_KEYS:
        chart = out["resE"]["fixtures"][name]["charts"][key]
        top, bottom = chart["xAxes"]
        assert (top["gridIndex"], bottom["gridIndex"]) == (0, 1)
        assert (top["min"], top["max"], top["interval"]) == (bottom["min"], bottom["max"], bottom["interval"]) \
            == (0, ax["x"]["max"], ax["x"]["interval"])
        assert not top["labelShow"] and top["name"] == "" and bottom["labelShow"] and bottom["name"] == ax["x"]["name"]
        main, ratio = chart["yAxes"]
        assert (main["gridIndex"], main["min"], main["max"]) == (0, 0, ax["y"]["hi"])
        assert main["interval"] == ax["y"]["interval"], "the screen height never crowds the server's ticks"
        assert ("provisional" in main["name"]) == ax["y"]["provisional"]
        assert ratio["gridIndex"] == 1 and ratio["type"] == "log"
        assert ratio["min"] * ratio["max"] == pytest.approx(1), "1 is the ratio axis's geometric centre"
        assert ratio["tickValues"] == ratio["labelValues"] and 1 in ratio["tickValues"]
        assert all(any(abs(t * u - 1) < 1e-9 for u in ratio["tickValues"]) for t in ratio["tickValues"]), "symmetric ticks"
        assert ratio["tickValues"][0] == pytest.approx(ratio["min"]) and ratio["tickValues"][-1] == pytest.approx(ratio["max"])
        # P4: a tick below 1 reads 1/x, with x = sigFigs(1/v, 3); from 1 up it stays decimal.
        for v, label in zip(ratio["labelValues"], ratio["labels"]):
            if v < 1 - 1e-9:
                assert label.startswith("1/") and float(label[2:]) == pytest.approx(1 / v, rel=5e-3), (v, label)
            else:
                assert "/" not in label and float(label) == pytest.approx(v, rel=5e-3), (v, label)
        # Two grids with one left and right, 1.4 label heights apart (P5); the tips stay off their union.
        g0, g1 = chart["grid"]
        assert (g0["left"], g0["right"]) == (g1["left"], g1["right"])
        assert g1["top"] - (g0["top"] + g0["height"]) == 14, "round(1.4 × fontLabel), fontLabel 10 on screen"
        assert chart["plotGrid"] == chart["grid"]
        # A linked crosshair, never an axis tooltip, labelled with E on the bottom axis only.
        assert chart["axisPointer"] == {"link": [{"xAxisIndex": "all"}]}
        for a in (top, bottom):
            assert a["pointer"]["show"] and a["pointer"]["type"] == "line"
            assert a["pointer"]["triggerTooltip"] is False and a["pointer"]["snap"] is False
        assert top["pointer"]["label"] is False and bottom["pointer"]["label"] is True
        assert bottom["pointer"]["labelText"] == ["E = 12.5 GeV", "E = −3.5 GeV"]
        assert chart["tooltipTrigger"] == "item"
        # Every series of the ratio panel is on the second grid.
        for s in chart["chart"]["series"]:
            on_ratio = "|ratio|" in (s["id"] or "") or (s["id"] or "").startswith("ratio|")
            assert (s["xAxisIndex"], s["yAxisIndex"]) == ((1, 1) if on_ratio else (0, 0)), s["id"]
    assert "provisional" in out["resE"]["provisional"]["yAxes"][0]["name"]


@pytest.mark.parametrize("name", RES)
def test_res_e_the_ratio_axis_covers_the_robust_marks(out, name):
    steps = out["resE"]["exports"]["steps"]
    for key in RES_E_KEYS:
        model = out["resE"]["fixtures"][name]["models"][key]
        k = model["ratio"]["k"]
        assert k in steps
        robust = [v for s in model["series"] for p in s["points"] if p["ratio"]["drawn"] and p["ratio"]["robust"]
                  for v in (p["ratio"]["value"], p["ratio"]["lo"], p["ratio"]["hi"]) if v]
        if robust and max(max(v, 1 / v) for v in robust) <= steps[-1]:
            need = max(max(v, 1 / v) for v in robust)
            assert k >= need * (1 - 1e-9)
        clipped = model["ratio"]["clipped"]
        over = sum(1 for s in model["series"] for p in s["points"] if p["ratio"]["drawn"] and p["ratio"]["over"])
        assert clipped["markers"] == over
        assert model["clipped"]["ratio"] == clipped["markers"] + clipped["whiskers"] + clipped["fits"] + clipped["bands"]
        carets = [i for s in out["resE"]["fixtures"][name]["charts"][key]["chart"]["series"] if (s["id"] or "").endswith("|ratio|carets")
                  for i in s["items"]]
        assert len(carets) >= over
        assert all("clipped at the ratio axis" in c["tip"] or "leaves the ratio axis" in c["tip"] for c in carets)
    helpers = out["resE"]["helpers"]
    assert helpers["ranges"] == [{"k": 2, "provisional": False, "capped": 0}, {"k": 2, "provisional": True, "capped": 0},
                                 {"k": 2, "provisional": True, "capped": 0}, {"k": 50, "provisional": False, "capped": 0},
                                 {"k": 1.1, "provisional": False, "capped": 0}, {"k": 4, "provisional": False, "capped": 0}]
    for ticks in helpers["ticks"]:
        assert all(any(abs(t * u - 1) < 1e-9 for u in ticks) for t in ticks) and 1 in ticks
    assert helpers["grid"] == [4, 4.25, 4.5, 4.75, 5, 5.1, 5.25, 5.5, 5.75, 6]
    assert helpers["gridEnds"] == [4, 80, 305, True, True]
    assert helpers["drawable"] == [True, False, False, False]


@pytest.mark.parametrize("name", RES)
def test_res_e_the_deposit_reference_is_each_showers_own(out, name):
    payload = _load(name)
    for windows in ("anchors", "all"):
        model = out["resE"]["fixtures"][name]["models"][f"{windows}:deposit"]
        chart = out["resE"]["fixtures"][name]["charts"][f"{windows}:deposit"]
        assert model["reference"]["key"] == "deposit" and model["reference"]["interval"] == "band" and model["reference"]["flag"] is None
        for shower, ref in model["reference"]["byShower"].items():
            det = next(s for s in payload["series"] if s["source"] == "detector" and s["shower"] == shower)
            q, pinned = det["fits"][windows]["quadrature"], det["fits"][windows]["pinned"]
            drawable = bool(q and q["params"]["a_defined"] and q["params"]["b_defined"] and q["params"].get("rho_a2b2") is not None)
            assert ref["series"] == det["key"] and ref["form"] == ("quadrature" if drawable else "pinned") and ref["hasBand"]
            fit = q if drawable else pinned
            p = fit["params"]
            value = (lambda e: (p["a2"] / e + p["b2"]) ** 0.5) if drawable else (lambda e: p["a0"] / e ** 0.5)
            below = 0
            for s in (x for x in model["series"] if x["shower"] == shower):
                for pt in s["points"]:
                    r = pt["ratio"]
                    if pt["E"] < model["curveMinGev"]:
                        assert not r["drawn"], "no ratio below 4 GeV under the deposit reference"
                        below += 1
                        continue
                    assert r["drawn"] and r["ref"] == pytest.approx(value(pt["E"]), rel=1e-9)
                    assert r["value"] == pytest.approx(pt["value"] / r["ref"], rel=1e-12)
                    if pt["whisker"]:
                        assert [r["lo"], r["hi"]] == pytest.approx([pt["lo"] / r["ref"], pt["hi"] / r["ref"]], rel=1e-12)
                    else:
                        assert r["lo"] is None and r["hi"] is None
                # The fit that is the reference is not divided by itself.
                for form, f in s["fits"].items():
                    if f["drawable"]:
                        assert f["isReference"] == (s["key"] == det["key"] and form == ref["form"])
                        assert (f["ratio"] is None) == f["isReference"]
            assert below == sum(1 for s in model["series"] if s["shower"] == shower for pt in s["points"] if pt["E"] < model["curveMinGev"])
        assert model["ratio"]["belowNotDrawn"] == sum(1 for s in model["series"] for pt in s["points"] if pt["E"] < model["curveMinGev"])
        bands = [s for s in chart["chart"]["series"] if "|ratio|reference|band|" in (s["id"] or "")
                 or "|ratio|reference|edges|" in (s["id"] or "")]
        assert bands and all(s["name"] in {x["label"] for x in payload["series"] if x["source"] == "detector"} for s in bands)
        assert all(not s["silent"] and "own 95% confidence band" in s["items"][0]["tip"] for s in bands)
        for shower, ref in model["reference"]["byShower"].items():
            washed = [s for s in bands if s["id"].startswith(f"{ref['series']}|ratio|reference|band|")]
            outlined = [s for s in bands if s["id"].startswith(f"{ref['series']}|ratio|reference|edges|")]
            assert bool(outlined) == bool(ref["outlined"]) and bool(washed) == (not ref["outlined"])
            # P13: a band not outlined but clamped at the axis takes one muted caret.
            caret = [s for s in chart["chart"]["series"] if s["id"] == f"{ref['series']}|ratio|reference|caret"]
            assert len(caret) == (1 if ref["bandCut"] else 0) and ref["bandClipped"] == bool(ref["bandCut"])
            assert not (ref["outlined"] and ref["bandCut"])
        assert model["ratio"]["clipped"]["bands"] == sum(1 for r in model["reference"]["byShower"].values() if r["bandCut"])
        ids = {s["id"] for s in chart["chart"]["series"]}
        for shower, ref in model["reference"]["byShower"].items():
            assert not [i for i in ids if i.startswith(f"{ref['series']}|ratio|{ref['form']}|")]
    # One shower of two-shower data: its own reference only.
    one = out["resE"]["fixtures"]["res_scaling_two"]["models"]["all:deposit:b"]
    assert list(one["reference"]["byShower"]) == ["b"] and one["reference"]["byShower"]["b"]["series"] == "detector:b"


@pytest.mark.parametrize("name", RES)
def test_res_e_a_literature_reference_is_the_catalogues_curve(out, name):
    cat = {c["key"]: c for c in out["resE"]["catalogue"]}
    for windows in ("anchors", "all"):
        for ref in ("pi", "e"):
            model = out["resE"]["fixtures"][name]["models"][f"{windows}:{ref}"]
            chart = out["resE"]["fixtures"][name]["charts"][f"{windows}:{ref}"]
            c = cat[ref]
            value = lambda e: (c["a"] ** 2 / e + c["b"] ** 2) ** 0.5  # noqa: E731
            assert model["reference"]["key"] == ref and model["reference"]["label"] == c["label"]
            assert model["reference"]["interval"] is None and model["reference"]["flag"] == "no interval reported"
            assert all(r["form"] == "literature" and r["literature"] == ref and not r["hasBand"] for r in model["reference"]["byShower"].values())
            for s in model["series"]:
                for pt in s["points"]:
                    assert pt["ratio"]["drawn"], "a literature curve is defined over the whole axis"
                    assert pt["ratio"]["ref"] == pytest.approx(value(pt["E"]), rel=1e-12)
                for f in s["fits"].values():
                    if f["drawable"]:
                        assert f["isReference"] is False and f["ratio"] is not None
            assert model["ratio"]["belowNotDrawn"] == 0
            # Both catalogue curves on the main panel, dotted and muted, named in the legend; the one in force flagged.
            assert [l["key"] for l in model["literature"]] == ["pi", "e"]
            assert [l["inForce"] for l in model["literature"]] == [ref == "pi", ref == "e"]
            lits = [s for s in chart["chart"]["series"] if (s["id"] or "").startswith("literature|")
                    and not s["id"].endswith(("|caret", "|endlabels"))]
            assert len(lits) == 2
            for s, lit in zip(lits, model["literature"]):
                assert s["name"] == lit["legend"] and lit["legend"] in chart["chart"]["legend"]
                group = s["items"][0]["el"]
                lines = [ch for ch in group["children"] if ch["type"] == "polyline"]
                assert lines and all(ch["dash"] == [1.5, 3] for ch in lines)
                # P2: the particle is its label, in the end column (an end-label series), never inside the plot.
                assert lit["label"] == {"pi": "π±", "e": "e±"}[lit["key"]]
                assert not [ch for ch in group["children"] if ch["type"] == "text"]
                tip = s["items"][0]["tip"]
                assert cat[lit["key"]]["equation"] in tip and "no interval reported" in tip and "not this detector" in tip
                if ref != "e":
                    assert all(v == pytest.approx((cat[lit["key"]]["a"] ** 2 / e + cat[lit["key"]]["b"] ** 2) ** 0.5, rel=1e-12)
                               for e, v in lit["curve"])
                    end = lit["curve"][-1][1]
                    labelled = [x for x in model["endLabels"]["main"] if x["key"] == f"literature|{lit['key']}"]
                    assert len(labelled) == (1 if 0 <= end <= model["y"]["hi"] else 0)
                    assert all(x["text"] == lit["label"] and x["literature"] for x in labelled)
                    assert lit["curve"][0][0] == 0.25 and lit["curve"][-1][0] == _e_axis(name)["x"]["max"]
            assert not [s for s in chart["chart"]["series"] if "|ratio|reference|band|" in (s["id"] or "")], "no band for a literature reference"
            assert ("÷" in chart["yAxes"][1]["name"] or "ratio to" in chart["yAxes"][1]["name"])
        assert not out["resE"]["fixtures"][name]["models"][f"{windows}:deposit"]["literature"]


def test_res_e_off_scale_windows_get_carets_and_the_canvas_note(out):
    got = out["resE"]["offScale"]
    model, chart = got["model"], got["chart"]
    top = 90
    over = [(s, p) for s in model["series"] for p in s["points"] if p["value"] > top]
    assert over and model["clipped"]["markers"] == len(over)
    assert sum(len(g["entries"]) for g in model["offScale"]) == len(over)
    assert [g["E"] for g in model["offScale"]] == sorted(g["E"] for g in model["offScale"])
    first = model["offScale"][0]
    assert model["noteText"]["offScale"].startswith(f"↑ off scale: {first['label']} — ")
    assert all(short in {"A deposit", "B deposit", "A network", "B network"} for g in model["offScale"] for short in (e["short"] for e in g["entries"]))
    carets = [i for s in chart["chart"]["series"] if (s["id"] or "").endswith("|carets") and "|ratio|" not in s["id"] for i in s["items"]]
    assert sum("clipped at the axis (0 to 90%)" in c["tip"] for c in carets) >= len(over)
    texts = [g["text"] for g in chart["graphicTexts"]]
    assert any(t.startswith("↑ off scale: ") for t in texts) and any(t.startswith("dashed: ") for t in texts)
    left = next(g for g in chart["graphicTexts"] if g["text"].startswith("↑"))
    right = next(g for g in chart["graphicTexts"] if g["text"].startswith("dashed"))
    assert left["align"] is None and right["align"] == "right" and left["y"] == right["y"]
    # Between the legend and the main panel, at most two lines, the rest counted.
    assert left["y"] < chart["grid"][0]["top"] and len(left["text"].split("\n")) <= 2
    narrow = next(g["text"] for g in got["narrow"]["graphicTexts"] if g["text"].startswith("↑"))
    assert len(narrow.split("\n")) <= 2 and re.search(r"\+\d+ more in Details$", narrow)
    # No window is ever split across a line: every line break falls after a ',' or ';'.
    for text in (left["text"], narrow):
        for line in text.split("\n")[:-1]:
            assert line.endswith((",", ";")), line


@pytest.mark.parametrize("name", RES)
def test_res_e_fit_marks_carry_their_form_and_extrapolation_in_their_tips(out, name):
    for key in ("anchors:deposit", "all:pi"):
        chart = out["resE"]["fixtures"][name]["charts"][key]
        model = out["resE"]["fixtures"][name]["models"][key]
        for s, form, f in _e_drawn_fits(model):
            solid = [x for x in chart["chart"]["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|solid|")]
            dashed = [x for x in chart["chart"]["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|dashed|")]
            assert len(solid) == len(f["solid"]) and len(dashed) == len(f["dashed"])
            for x in solid + dashed:
                el = x["items"][0]["el"]
                assert el["dash"] == ([6, 4] if x in dashed else None)
                tip = x["items"][0]["tip"]
                assert ("σ/E = (" in tip and ("%/√E ⊕ (" in tip if form == "quadrature" else "⊕ 0 (b ≡ 0, through the origin)" in tip))
                assert ("Extrapolated: beyond the windows this fit used" in tip) == (x in dashed)
                assert "assumes the form holds" in tip if x in dashed else True
            bands = [x for x in chart["chart"]["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|band|")]
            edges = [x for x in chart["chart"]["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|edges|")]
            # P1: a band wider than the axis over its span is its two edges, never a wash; any other band is a wash.
            assert (not bands and edges) if f["outlined"] else (bands and not edges)
            assert all(not b["silent"] for b in bands + edges)
            alphas = {b["id"].split("|")[-1]: b["items"][0]["el"]["opacity"] for b in bands}
            if "inside" in alphas:
                for part in ("below", "above"):
                    if part in alphas:
                        assert alphas[part] == pytest.approx(alphas["inside"] / 3), "the band beyond its windows at a third"
            # Shower B: hollow markers, its lines at 70% strength and never below 3:1; no shower dash on this view.
            for x in solid:
                assert x["items"][0]["el"]["opacity"] == pytest.approx(s["lineOpacity"]) or f["provisional"]
        for s in model["series"]:
            if s["isB"]:
                assert s["lineOpacity"] < 1
    if name == "res_scaling_two":
        ink = out["resE"]["ink"]
        for theme in ("dark", "light"):
            for s in ink[theme]:
                assert s["contrast"] >= 3 and s["contrastProvisional"] >= 3, (theme, s)
                if s["isB"]:
                    assert s["opacity"] == s["wanted"]


@pytest.mark.parametrize("name", RES)
def test_res_e_fits_leaving_the_top_get_one_caret_with_true_values(out, name):
    for key in RES_E_KEYS:
        model = out["resE"]["fixtures"][name]["models"][key]
        chart = out["resE"]["fixtures"][name]["charts"][key]
        cut = [(s, f) for s, _, f in _e_drawn_fits(model) if f["cut"]]
        assert model["clipped"]["fits"] == len(cut)
        tips = [i["tip"] for x in chart["chart"]["series"] if (x["id"] or "").endswith("|carets") and "|ratio|" not in x["id"] for i in x["items"]]
        assert sum("leaves the top of the" in t and "True values" in t for t in tips) == len(cut)


@pytest.mark.parametrize("name", RES)
def test_res_e_fit_table_names_what_this_view_draws(out, name):
    payload = _load(name)
    linear = out["res"][name]["tables"]
    for windows in ("anchors", "all"):
        table = out["resE"]["fixtures"][name]["tables"][windows]
        base = linear[f"{windows}:both"]
        assert table["view"] == "energy" and table["columns"] == base["columns"]
        assert [r["key"] for r in table["rows"]] == [r["key"] for r in base["rows"]]
        assert "this view draws the origin-pinned a₀/√E ⊕ 0" in table["caption"].replace("This", "this")
        assert "affine a/√E + b is drawn in the 1/√E view" in table["caption"]
        for row, lrow, s in zip(table["rows"], base["rows"], _res_shown(payload, "both")):
            assert [f["form"] for f in row["fits"]] == ["affine", "pinned", "quadrature"]
            for f, lf in zip(row["fits"], lrow["fits"]):
                assert f["cells"][1:] == lf["cells"][1:], "only the Fit column names the view"
            names = [f["cells"][0] for f in row["fits"]]
            assert names[0] == "Affine a/√E + b — drawn in the 1/√E view"
            assert names[1] == "Origin-pinned a₀/√E ⊕ 0 — drawn"
            q = s["fits"][windows]["quadrature"]["params"]
            if q["a_defined"] and q["b_defined"]:
                assert names[2] == "Quadrature a/√E ⊕ b — drawn"
            else:
                assert names[2].startswith("Quadrature a/√E ⊕ b — not drawn: ")
                assert ("A ≤ 0" in names[2]) == (not q["a_defined"]) and ("B ≤ 0" in names[2]) == (not q["b_defined"])


def test_res_e_empty_states_say_so(out):
    empty = out["resE"]["empty"]
    for key in ("nothing", "noAxis", "none"):
        chart = empty[key]
        assert not chart["chart"]["series"] and chart["graphicTexts"], key
    assert "no energy-resolution series" in empty["nothing"]["graphicTexts"][0]["text"]
    assert "No momentum window holds two events" in empty["none"]["graphicTexts"][0]["text"]
    assert empty["noAxisModel"] is None


def test_res_e_print_tokens_build(out):
    printed = out["printResE"]
    chart = printed["chart"]
    assert chart["series"] and chart["legend"] and len(printed["grid"]) == 2 and printed["legendType"] == "plain"
    for s in chart["series"]:
        if s["id"] == "detector:a|markers":
            assert all(i["el"]["fill"] == printed["ink"] for i in s["items"])
        if s["id"] == "network:a|markers":
            assert all(i["el"]["fill"] == printed["hues"]["absolute"] for i in s["items"])
        if (s["id"] or "").startswith("literature|") and "|caret" not in s["id"]:
            assert all(ch["stroke"] == printed["muted"] for ch in s["items"][0]["el"]["children"] if ch["type"] == "polyline")
    assert printed["noteFont"] and all(f == printed["fontTip"] for f in printed["noteFont"])
    g0, g1 = printed["grid"]
    assert g1["top"] + g1["height"] < printed["height"]
    _no_hyphen_numbers(chart["strings"])


def test_res_e_the_panel_sets_its_height_and_exports_two_panels(out):
    cls = out["resE"]["cls"]
    assert cls["linearFirst"] == {"height": None, "resized": 0}, "the 1/√E view leaves the CSS height alone"
    assert cls["energy"]["height"] == "600px" and cls["energy"]["resized"] == 1, "resized in the same call"
    assert cls["energy"]["grids"] == 2 and cls["energy"]["liveGrid"] == 2 and cls["energy"]["built"] == ["option", "plotGrid"]
    assert cls["relayoutResized"] == 1, "a relayout at an unchanged view does not resize again"
    assert cls["linear"]["height"] == "" and cls["linear"]["resized"] == 2 and cls["linear"]["grids"] == 1
    assert cls["linear"]["built"] == ["option"]
    assert cls["linear"]["export"] == cls["linear"]["exportBefore"]
    assert cls["energy"]["export"]["width"] == 321 and cls["energy"]["export"]["height"] > cls["linear"]["export"]["height"]
    assert cls["energy"]["exportWide"]["height"] > cls["energy"]["export"]["height"]


def test_res_e_no_rendered_number_uses_an_ascii_hyphen(out):
    for name in RES:
        entry = out["resE"]["fixtures"][name]
        for chart in entry["charts"].values():
            _no_hyphen_numbers(chart["chart"]["strings"])
            _no_hyphen_numbers(t for a in chart["yAxes"] + chart["xAxes"] for t in a["labels"])
            _no_hyphen_numbers(g["text"] for g in chart["graphicTexts"])
        for table in entry["tables"].values():
            _no_hyphen_numbers([table["caption"], *(c for r in table["rows"] for f in r["fits"] for c in f["cells"])])
        for model in entry["models"].values():
            _no_hyphen_numbers([model["noteText"]["offScale"], model["noteText"]["extrapolation"], model["reference"]["label"]])
            _no_hyphen_numbers(role for s in model["series"] for p in s["points"] for role in p["roles"])
    for key in ("undefinedA", "undefinedB", "offScale"):
        _no_hyphen_numbers(out["resE"][key]["chart"]["chart"]["strings"])
    _no_hyphen_numbers(out["resE"]["lightChart"]["chart"]["strings"])


# ------------------------------------------------- res-scaling: E view drawer --
#
# The drawer of the E view (models_notes.js `resolutionScalingNotes` with
# view 'energy', `modelsHazards`). Every sentence is built from the panel's
# `energyModel`, so each test reads the model's own counts from the harness and
# holds the drawer to them; the 1/√E drawer and its hazards are held to one
# output whatever `view` or `reference` is passed (the dark golden holds that
# output to the recorded one).

RES_NOTE_KEYS = [f"{w}:{r}:{s}" for w in ("anchors", "all") for r in RES_E_REFS for s in ("both", "a", "b")]
MAE_SENTENCE = ("MAE/E is not σ/E: for unbiased Gaussian errors MAE/E = √(2/π)·σ/E ≈ 0.798·σ/E, and MAE also carries the bias "
                "that σ(R)/μ(R) divides out; this card plots σ(R)/μ(R) and never converts one into the other.")
LIT_EQUATIONS = {"pi": "σ/E = 27.2%/√E ⊕ 1.0%", "e": "σ/E = 14.0%/√E ⊕ 0.4%"}


def _n(count: int, word: str, many: str | None = None) -> str:
    return f"{count:,} {word if count == 1 else (many or word + 's')}"


def _span(span) -> str:
    return f"{span[0]:g}–{span[1]:g} GeV" if span else "no window"


def _e_notes(out: dict):
    """Every (name, key, record) of the E-view drawer on the four fixtures."""
    for name in RES:
        for key in RES_NOTE_KEYS:
            yield name, key, out["resNotes"]["fixtures"][name][key]


def _lines(n: dict, out: dict, which: str) -> list[str]:
    return n["sections"].get(out["notes"]["section"][which], [])


def _text(n: dict) -> str:
    return " ".join(line for lines in n["sections"].values() for line in lines)


def _starts(lines: list[str], prefix: str) -> list[str]:
    return [line for line in lines if line.startswith(prefix)]


def _range_basis(note: str) -> str:
    """The server's E-view range sentence without its trailing clipped count, as the drawer restates it (N1)."""
    return re.sub(r"\s*\S+ marks? beyond it (?:is|are) clipped, not rescaled\.\s*$", "", note)


def _in_force(facts: dict, key: str) -> str:
    """How the drawer names the mode and shower choice its counts belong to: "in the 3-anchor mode, both showers"."""
    mode = "the 3-anchor mode" if facts["mode"] == "anchors" else "the all-windows mode"
    if facts["nShowers"] < 2:
        return f"in {mode}"
    shower = key.split(":")[2]
    return f"in {mode}, {'both showers' if shower == 'both' else f'shower {shower.upper()} only'}"


def test_res_notes_e_view_has_the_four_sections_in_order(out):
    section = out["notes"]["section"]
    standard = [section["selection"], section["drawn"], section["disclosures"], section["legend"]]
    for name, key, rec in _e_notes(out):
        n = rec["notes"]
        _check_notes(n, section)
        assert n["headings"] == standard, (name, key)
        assert n["title"] == "Energy Resolution vs. E"
        selection = _lines(n, out, "selection")
        assert any(line.startswith("View: σ/E against the energy E in GeV, 0 to 80 GeV") for line in selection)
        facts = rec["facts"]
        ratio_to = _starts(selection, "Ratio to: ")
        assert len(ratio_to) == 1 and facts["label"] in ratio_to[0], (name, key)
        assert ("the literature curve" in ratio_to[0]) == (facts["literature"] is not None)
        drawn = _lines(n, out, "drawn")
        # The conversion and the server's own notes are said as the server wrote them, the range basis without the
        # server's clipped count (N1): the drawer states the model's own counts instead.
        assert drawn[0].startswith("E = 1/x²") and facts["rule"].rstrip(".") in drawn[0]
        for i, note in enumerate(facts["notes"]):
            assert (_range_basis(note) if i == 0 else note) in drawn, (name, key, note)
        assert not [line for line in drawn if "clipped, not rescaled" in line]
        assert "the server's count" not in _text(n)
        # P15: the drawer names the section that derives the view; P11: no dodge.
        assert drawn[1] == ('Methodology §2.4.11, "Resolution scaling against E", derives this view, from E = 1/x² to the '
                            "ratio panel's axis; §3.6 audits its marks.")
        assert ("Windows of different series at one energy are drawn at that energy, not set apart: a window sits on its own "
                "curve, which no offset could follow.") in drawn


def test_res_notes_e_view_counts_equal_the_models(out):
    for name, key, rec in _e_notes(out):
        n, f = rec["notes"], rec["facts"]
        drawn, dis = _lines(n, out, "drawn"), _lines(n, out, "disclosures")
        where = (name, key)
        assert f"{_n(f['nPoints'], 'window')} and {_n(f['nLines'], 'fit curve')} are drawn in this view." in drawn, where
        # Clipped at the top of the main panel: markers, whiskers, fits and literature curves, with the server's count.
        c = f["clipped"]
        parts = [_n(c[k], word) for k, word in (("markers", "marker"), ("whiskers", "whisker"), ("fits", "fit"), ("literature", "literature curve")) if c[k]]
        top = _starts(dis, "Clipped at the top of the main panel")
        if parts:
            # N1: the model's own counts, for the mode and shower in force, named; never the server's count.
            assert len(top) == 1 and top[0].endswith(f": {', '.join(parts)}."), where
            assert f" {_in_force(f, key)}, each with a caret" in top[0], where
        else:
            assert not top, where
        # Windows above the top, listed by window with their N.
        total = sum(len(g["entries"]) for g in f["offScale"])
        above = [line for line in dis if "above the top of the axis" in line]
        if total:
            assert len(above) == 1 and above[0].startswith(f"{_n(total, 'window')} ") and above[0].count("(N = ") == total, where
            for g in f["offScale"]:
                assert g["label"] in above[0]
                for e in g["entries"]:
                    assert e["short"] in above[0]
        else:
            assert not above, where
        # Fits that leave the top, bands cut at zero, fits not drawn.
        assert sum(d["cut"] for d in f["drawn"]) == c["fits"]
        leave = [line for line in dis if "the top of the main panel, line or band" in line]
        assert len(leave) == (1 if c["fits"] else 0), where
        if c["fits"]:
            assert leave[0].startswith(f"{_n(c['fits'], 'fit')} {'leaves' if c['fits'] == 1 else 'leave'} ")
        floor = sum(d["floorCut"] for d in f["drawn"])
        cut0 = [line for line in dis if " cut at 0: " in line]
        assert len(cut0) == (1 if floor else 0), where
        if floor:
            assert cut0[0].startswith(_n(floor, "fit") + " ")
            # N3: the quadrature band is cut where (σ/E)², not σ/E, would be negative.
            quad = any(d["floorCut"] and d["form"] == "quadrature" for d in f["drawn"])
            assert ("where the band of (σ/E)² falls below zero, its lower edge is cut at 0" in cut0[0]) == quad, where
            assert "cut at σ/E = 0 where it would be negative" not in cut0[0]
        for d in f["notDrawn"]:
            matching = [line for line in dis if line.startswith(f"{d['label']}: the ") and "is not drawn, " in line and d["reason"] in line]
            assert len(matching) == 1, (where, d)
            assert "stays in the fit table" in matching[0]
        # Spans: said once in What is drawn when shared, per span under Disclosures when they differ.
        differ = [line for line in dis if line.startswith("The fits were not all fitted over the same windows")]
        if f["drawn"] and f["spansShared"]:
            assert not differ and any(f"here {_span(f['span'])}" in line for line in drawn), where
        elif f["drawn"]:
            assert len(differ) == 1
            for d in f["spanList"]:
                assert _span(d["span"]) in differ[0]
        else:
            assert any(line.startswith("No fit is drawn for this selection") for line in dis)
        # Windows.
        p = f["points"]
        below = [line for line in dis if re.search(r" below 4 GeV (is|are) drawn as ", line)]
        assert len(below) == (1 if p["below4"] else 0), where
        if p["below4"]:
            assert below[0].startswith(f"{_n(p['below4'], 'window')} below 4 GeV ")
        alone = [line for line in dis if line.endswith("χ² whisker, not fitted.")]
        assert len(alone) == (1 if p["weakAlone"] else 0)
        if p["weakAlone"]:
            assert alone[0].startswith(_n(p["weakAlone"], "window") + " of N < 20")
        ring = [line for line in dis if "faded dashed ring with no whisker" in line]
        assert len(ring) == (1 if p["subFloor"] else 0)
        if p["subFloor"]:
            assert ring[0].startswith(_n(p["subFloor"], "window") + " of N < 8")
        # The ratio panel.
        rc = f["ratioClipped"]
        ratio_parts = [_n(rc[k], word) for k, word in (("markers", "marker"), ("whiskers", "whisker"), ("fits", "fit"),
                                                       ("bands", "reference band")) if rc[k]]
        clipped_ratio = _starts(dis, "Clipped at the ratio axis")
        if ratio_parts:
            assert len(clipped_ratio) == 1 and clipped_ratio[0].endswith(f": {', '.join(ratio_parts)}."), where
            assert f" {_in_force(f, key)}, each with a caret" in clipped_ratio[0], where
        else:
            assert not clipped_ratio
        assert c["ratio"] == rc["markers"] + rc["whiskers"] + rc["fits"] + rc["bands"]
        bands = [line for line in dis if "clamped at the ratio axis, a muted wash with one muted caret" in line]
        assert len(bands) == (1 if rc["bands"] else 0)
        if rc["bands"]:
            assert bands[0].startswith(_n(rc["bands"], "reference band") + " ")
        # P1: the bands drawn as their edges are counted per panel and listed.
        outlined = f["bandsOutlined"]["main"] + f["bandsOutlined"]["ratio"]
        listed = [line for line in dis if "never as a wash: " in line]
        assert len(listed) == (1 if outlined else 0), where
        if outlined:
            assert listed[0].startswith(f"{_n(outlined, 'band')} {'spans' if outlined == 1 else 'span'} half ")
        # P9: a cap is said, with its count.
        assert any(line.startswith("The ratio axis is capped at ×50") for line in dis) == bool(f["capped"]), where
        gone = [line for line in dis if "not drawn on the ratio panel" in line]
        assert len(gone) == (1 if f["belowNotDrawn"] else 0), where
        if f["belowNotDrawn"]:
            assert gone[0].startswith(f"{_n(f['belowNotDrawn'], 'window')} below 4 GeV ")
        k = f"1/{f['k']:.3g} to {f['k']:.3g}"
        prefix = f"The ratio range, {k}, "
        range_line = _starts(dis, prefix)
        assert len(range_line) == 1 and ("is provisional" in range_line[0]) == f["ratioProvisional"], where
        assert (f["yProvisional"]) == any(line.startswith("The y range is provisional") for line in dis)
        for r in f["noReference"]:
            assert any("has no ratio marks" in line for line in dis), where
        # Shower B's 70% strength.
        assert any(line.startswith("Shower B's lines are drawn at 70% strength") for line in dis) == f["anyB"], where


def test_res_notes_e_view_names_the_reference_and_says_its_whiskers_are_conditional(out):
    for name, key, rec in _e_notes(out):
        n, f = rec["notes"], rec["facts"]
        dis = _lines(n, out, "disclosures")
        whisker = [line for line in dis if line.startswith("A ratio whisker is the window's 95% χ² interval divided by ")]
        if f["points"]["ratioWhiskers"]:
            assert len(whisker) == 1, (name, key)
            assert f"it is conditional on the reference, {f['label']}, " in whisker[0]
            assert ("the literature curve" in whisker[0]) == (f["literature"] is not None)
            assert "does not include the reference's own uncertainty" in whisker[0]
        else:
            assert not whisker, (name, key)
        drawn = " ".join(_lines(n, out, "drawn"))
        if f["literature"] is None:
            # One line per shower, which fit divides its windows or why none does, and the reference's own band.
            for d in f["deposit"]:
                line = [x for x in _lines(n, out, "drawn") if x.endswith("evaluated from 4 to 80 GeV only.") or "no ratio marks" in x]
                assert line, (name, key)
                if d["reason"]:
                    assert any(d["reason"] in x for x in _lines(n, out, "drawn"))
                else:
                    assert any(d["why"] in x for x in _lines(n, out, "drawn")), (name, key, d)
            assert "own 95% band relative to itself" in drawn
        else:
            assert LIT_EQUATIONS[f["literature"]] in drawn and "no interval reported" in drawn


def test_res_notes_e_view_literature_sentences_only_under_a_literature_reference(out):
    for name, key, rec in _e_notes(out):
        n, f = rec["notes"], rec["facts"]
        text = _text(n)
        dis = " ".join(_lines(n, out, "disclosures"))
        literature = f["literature"] is not None
        assert key.split(":")[1] == (f["literature"] or "deposit")
        for needle in ("ECCE G4 simulation", "none derived", "resolution_references.md", "supplied by Martin on 2026-11-10",
                       "not this dataset's detector", "transcribed as the legend prints them"):
            assert (needle in dis) == literature, (name, key, needle)
        if literature:
            assert LIT_EQUATIONS["pi"] in dis and LIT_EQUATIONS["e"] in dis, "both legend curves are named"
            assert "Each is a documented point estimate with no interval reported and none derived" in dis
            assert "Dotted muted lines labelled" in " ".join(_lines(n, out, "legend"))
            assert f"{_n(f['clipped']['literature'], 'curve')} " in dis or f["clipped"]["literature"] == 0
        else:
            assert "ECCE" not in text and "none derived" not in text
            assert "none is drawn while the ratio reference is the deposit fit" in " ".join(_lines(n, out, "legend"))
        # The MAE/E sentence, exactly, in every E-view drawer.
        assert MAE_SENTENCE in _lines(n, out, "disclosures")


def test_res_notes_e_view_hazards(out):
    for name, key, rec in _e_notes(out):
        f = rec["facts"]
        c = f["clipped"]
        expected = []
        if any(d["provisional"] for d in f["drawn"]):
            expected.append("provisional fit")
        if f["points"]["weak"]:
            expected.append("weak windows drawn")
        if f["yProvisional"]:
            expected.append("provisional range")
        if f["ratioProvisional"]:
            expected.append("provisional ratio range")
        if c["markers"] or c["whiskers"] or c["fits"] or c["literature"] or c["ratio"]:
            expected.append("marks clipped at the axis")
        if f["anyUnconverged"]:
            expected.append("fit not converged")
        if f["literature"]:
            expected.append("no interval reported")
        assert rec["hazards"] == expected, (name, key)
        assert rec["notes"]["hazards"] == expected
        assert ("no interval reported" in rec["hazards"]) == (key.split(":")[1] != "deposit")
    # The two-shower payload draws weak windows and clips fits and ratio marks: the chip would show.
    two = out["resNotes"]["fixtures"]["res_scaling_two"]["all:pi:both"]["hazards"]
    assert two == ["weak windows drawn", "marks clipped at the axis", "no interval reported"]


def test_res_notes_e_view_variants(out):
    v = out["resNotes"]["variants"]
    # A lower top: windows above it are listed by window, with a caret, and the clip hazard stands.
    off = v["offScale"]
    assert sum(len(g["entries"]) for g in off["facts"]["offScale"]) > 0
    assert "marks clipped at the axis" in off["hazards"]
    above = [line for line in _lines(off["notes"], out, "disclosures") if "above the top of the axis (90%)" in line]
    assert len(above) == 1
    # A literature curve crossing the top is counted and said.
    lit = v["literatureClipped"]
    assert lit["facts"]["clipped"]["literature"] > 0 and "marks clipped at the axis" in lit["hazards"]
    crosses = [line for line in _lines(lit["notes"], out, "disclosures") if " the top, clipped there with a caret" in line]
    assert len(crosses) == 1 and f"{_n(lit['facts']['clipped']['literature'], 'curve')} " in crosses[0]
    # A provisional y range, a provisional ratio range.
    assert "provisional range" in v["yProvisional"]["hazards"]
    assert any(line.startswith("The y range is provisional") for line in _lines(v["yProvisional"]["notes"], out, "disclosures"))
    rp = v["ratioProvisional"]
    assert rp["facts"]["ratioProvisional"] and "provisional ratio range" in rp["hazards"]
    assert any("is provisional: no window of N ≥ 20" in line for line in _lines(rp["notes"], out, "disclosures"))
    assert "provisional fit" in rp["hazards"]
    # A fit whose weights did not settle.
    un = v["unsettled"]
    assert "fit not converged" in un["hazards"] and "fit not converged" not in out["resNotes"]["fixtures"]["res_scaling_two"]["anchors:deposit:both"]["hazards"]
    assert any("did not settle within 200 refits" in line for line in _lines(un["notes"], out, "disclosures"))
    # A quadrature fit not drawn names its reason and its numbers.
    ub = v["undefinedB"]
    assert {"label": "Shower B · Energy network · absolute frame", "form": "quadrature",
            "reason": "B ≤ 0: σ/E falls faster than 1/√E, so there is no real constant term"} in ub["facts"]["notDrawn"]
    line = [x for x in _lines(ub["notes"], out, "disclosures") if x.startswith("Shower B · Energy network · absolute frame: the quadrature fit a/√E ⊕ b is not drawn")]
    assert len(line) == 1 and "B ≤ 0" in line[0] and "(A = " in line[0] and "%²·GeV, B = " in line[0]
    # No E-view axis, no response, nothing drawable.
    na = v["noAxis"]
    assert na["facts"] is None and na["hazards"] == []
    assert na["notes"]["headings"] == [out["notes"]["section"]["disclosures"]]
    assert "no energy-resolution series with an E-view axis" in _text(na["notes"])
    assert v["nothing"] == [None, []]
    empty = v["empty"]
    _check_notes(empty["notes"], out["notes"]["section"])
    assert empty["facts"]["nPoints"] == 0 and empty["facts"]["nLines"] == 0
    assert any(line.startswith("No fit is drawn for this selection") for line in _lines(empty["notes"], out, "disclosures"))
    assert "provisional fit" not in empty["hazards"] and "weak windows drawn" not in empty["hazards"]
    # A sampled response keeps its flag first and says so.
    assert v["sampled"]["hazards"][0] == "sampled"
    assert "Sampled preview: the exact numbers follow." in _lines(v["sampled"]["notes"], out, "disclosures")


def test_res_notes_e_view_titles(out):
    t = out["resNotes"]["titles"]
    assert t["constants"] == ["Energy Resolution vs. 1/√E", "Energy Resolution vs. E"]
    assert t["linear"] == t["constants"][0] and t["energy"] == t["constants"][1] and t["given"] == "Card title"


def test_res_notes_the_linear_drawer_and_hazards_ignore_view_and_reference(out):
    """No view, view 'linear', any other view and a reference give the 1/√E drawer's one output, with none of the E view's text."""
    for key, rec in out["resNotes"]["linear"].items():
        assert rec["notes"] and rec["hazards"], key
        assert rec["title"] == "Energy Resolution vs. 1/√E"
        assert MAE_SENTENCE not in rec["text"] and "Ratio to:" not in rec["text"] and "ECCE" not in rec["text"]
        assert "tabled and not drawn" not in rec["text"]
        assert "not drawn." in rec["text"] and "The quadrature form √(a²/E + b²) is fitted as (σ/E)² = A/E + B and tabled under the plot, not drawn." in rec["text"]


def test_res_notes_e_view_uses_the_unicode_minus(out):
    two = out["resNotes"]["fixtures"]["res_scaling_two"]["all:deposit:both"]["notes"]
    xgb = out["resNotes"]["fixtures"]["res_scaling_xgb"]["anchors:deposit:both"]["notes"]
    for n in (two, xgb):
        text = _text(n)
        assert "−" in text, "a negative A or B is set with U+2212"
        _no_hyphen_numbers(line for lines in n["sections"].values() for line in lines)
    assert re.search(r"B = −\d", _text(xgb)) and re.search(r"A = −\d", _text(two))
    for name, key, rec in _e_notes(out):
        _no_hyphen_numbers(line for lines in rec["notes"]["sections"].values() for line in lines)


# ------------------------------------------- res-scaling: the E view's review fix round --
#
# fixes.md part A: one test per item (P1-P15, N1-N4; P15 and N1 sit in the drawer tests above), on the fixtures and
# on clones changed only where the server would change them (`out["resFix"]`): a ν = 1 quadrature fit with
# t = 12.71, an off-scale list wider than its room at 321 px, a provisional reference, a robust ratio beyond 50.

LIT_NO_INTERVAL = "The literature curve has no interval reported; none is derived."
NO_RANGE = "the figure does not state the energy range the curve was fitted over; it is drawn over the whole axis"


def _width(text: str, font: float) -> float:
    """Node's text width without a DOM (`textfit.js` measureText): 0.55 em per UTF-16 code unit."""
    return len(text.encode("utf-16-le")) // 2 * font * 0.55


def _dis(n: dict, out: dict) -> list[str]:
    return n["sections"].get(out["notes"]["section"]["disclosures"], [])


def _plain(tip: str) -> str:
    """A tooltip's text as read: tags dropped, entities decoded, spaces collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", tip)).split())


def test_res_fix_p1_the_outline_threshold_is_half_the_axis_within_the_span(out):
    """A band is drawn as its edges once it spans half its axis or more at one E of its fitted span."""
    s = out["resFix"]["share"]
    assert s["value"] == 0.5
    assert s["half"] is True and s["under"] is False, "50 of 100 at 5 GeV is half; 45 is not"
    assert s["beyondSpan"] is False, "only the fitted span counts"
    assert s["clampedTop"] is True and s["clampedShort"] is False, "only the part inside the axis counts: 40-100 is 60%, 60-100 is 40%"
    assert s["logHalf"] is True and s["logUnder"] is False, "on the ratio panel the share is taken on the log scale"


def test_res_fix_p1_a_band_wider_than_the_axis_is_drawn_as_its_edges(out):
    o = out["resFix"]["outlined"]
    span, yhi, k = o["span"], o["yhi"], o["k"]
    assert any(r[2] <= 0 and r[3] >= yhi for r in o["curve"] if span[0] <= r[0] <= span[1]), "the clone runs floor to top in span"
    assert o["outlined"] is True and o["ratioOutlined"] is True
    for panel in ("main", "ratio"):
        assert {"panel": panel, "key": "network:a", "form": "quadrature", "reference": False} in o["entries"]
        assert o[panel] == sum(1 for e in o["entries"] if e["panel"] == panel)
    ids = [s["id"] for s in o["chart"]["series"]]
    assert not [i for i in ids if i.startswith(("network:a|quadrature|band|", "network:a|ratio|quadrature|band|"))], "no wash"
    edges = [e for e in o["edges"] if e["id"].startswith(("network:a|quadrature|edges|", "network:a|ratio|quadrature|edges|"))]
    assert {e["id"].split("|")[-2] for e in edges} == {"solid", "dashed"}
    assert {"|ratio|" in e["id"] for e in edges} == {True, False}, "edges on both panels"
    for e in edges:
        part, ratio = e["id"].split("|")[-2], "|ratio|" in e["id"]
        assert e["stroke"] == o["colour"] and e["width"] == pytest.approx(0.8 * o["lineAxis"])
        assert e["opacity"] == pytest.approx(o["edgeOpacity"]) and e["xAxisIndex"] == (1 if ratio else 0)
        assert e["dash"] == ([6, 4] if part == "dashed" else None), "solid in span, dashed beyond, as the curve"
        for x, y in e["points"]:  # identity coordinates: clipped to the plot, the solid part inside the span
            assert (1 / k - 1e-9 <= y <= k + 1e-9) if ratio else (0 < y <= yhi + 1e-9)
            if part == "solid":
                assert span[0] - 1e-9 <= x <= span[1] + 1e-9
        assert ("Its 95% band spans half its axis or more over its fitted windows (S = 1.5, ν = 1, q = 12.71), "
                "so it is drawn as its edges, not as a wash.") in e["tip"]
    curves = [s["items"][0]["tip"] for s in o["chart"]["series"]
              if s["id"].startswith(("network:a|quadrature|solid|", "network:a|ratio|quadrature|solid|"))]
    assert len(curves) >= 2 and all("so it is drawn as its edges, not as a wash" in t for t in curves)
    listed = [line for line in _dis(o["notes"], out) if "never as a wash: " in line]
    assert len(listed) == 1 and "main panel: A network a/√E ⊕ b (S = 1.5, ν = 1, q = 12.71)" in listed[0]
    assert "ratio panel: A network a/√E ⊕ b (S = 1.5, ν = 1, q = 12.71)" in listed[0]
    assert set(o["hazards"]) <= set(o["hazardsBase"]) | {"marks clipped at the axis"}, "no hazard of its own"
    # Every fixture, mode and reference: outlined exactly where the band spans half its axis or more in its span.
    assert o["fixtures"]
    for name, windows, ref, key, form, panel, outlined, full in o["fixtures"]:
        assert outlined == full, (name, windows, ref, key, form, panel)
    assert any(row[6] for row in o["fixtures"]), "the fixtures hold an outlined band (res_scaling_two, anchors, π±)"
    # The deposit reference's own band about 1 follows the same rule: muted edges, no wash, no caret, listed.
    r = out["resFix"]["refOutlined"]
    assert r["outlined"] is True and r["cut"] is None and r["washes"] == 0
    assert {"panel": "ratio", "key": "detector:b", "reference": True} in r["entries"] and r["form"] == "quadrature"
    assert r["edges"] and all(e["stroke"] == r["muted"] and e["opacity"] == pytest.approx(r["edgeOpacity"]) for e in r["edges"])
    assert all("Its own 95% band spans half its axis or more over its fitted windows (S = 3, ν = 1, q = 12.71)" in e["tip"] for e in r["edges"])
    assert any("the reference band about 1 of B deposit a/√E ⊕ b (S = 3, ν = 1, q = 12.71)" in line for line in _dis(r["notes"], out))


def test_res_fix_p2_end_labels_name_the_shower_in_a_column_beside_the_plot(out):
    seen = {"ab": 0, "lit": 0}
    for key, rec in out["resFix"]["labels"].items():
        k, yhi, font = rec["k"], rec["yhi"], rec["fontTip"]
        want_main, want_ratio = [], []
        for f in rec["fits"] if rec["twoOnShow"] else []:
            assert f["end"][0] == pytest.approx(rec["xmax"])
            tag = (f["key"], f["form"], f["shower"].upper(), f["colour"])
            if 0 <= f["end"][1] <= yhi:
                want_main.append(tag)
            if f["ratioEnd"] and 1 / k * (1 - 1e-9) <= f["ratioEnd"][1] <= k * (1 + 1e-9):
                want_ratio.append(tag)
        got = lambda panel: [(x["key"], x["form"], x["text"], x["colour"]) for x in rec["endLabels"][panel] if not x["literature"]]  # noqa: E731
        assert got("main") == want_main and got("ratio") == want_ratio, key
        seen["ab"] += len(want_main)
        # The literature curves' particles, muted, on the main panel only.
        lits = [x for x in rec["endLabels"]["main"] if x["literature"]]
        assert [x["text"] for x in lits] == [l["label"] for l in rec["literature"]] and all(x["colour"] == rec["muted"] for x in lits)
        assert not [x for x in rec["endLabels"]["ratio"] if x["literature"]]
        seen["lit"] += len(lits)
        # The column: both grids' right widened by the widest label and its gap; untouched without a label.
        g0, g1 = rec["grid"]
        labels = rec["endLabels"]["main"] + rec["endLabels"]["ratio"]
        column = -(-(0.5 * font + max(_width(x["text"], font) for x in labels)) // 1) if labels else 0
        assert g0["right"] == g1["right"] == pytest.approx(rec["pad"]["right"] + column), key
        # One series per legend entry and panel, drawn outside the plot, the text left-aligned past x.max.
        texts = [t for s in rec["series"] for t in s["texts"]]
        assert sorted(t["text"] for t in texts) == sorted(x["text"] for x in labels)
        for s in rec["series"]:
            assert s["clip"] is False and s["silent"] is True and s["xAxisIndex"] == (1 if s["id"].endswith("|ratio|endlabels") else 0)
            assert all(t["align"] == "left" and t["x"] == pytest.approx(rec["xmax"] + 0.5 * font) for t in s["texts"])
        # Shower B's strength, worded as drawn; the end labels named only where both showers are drawn.
        assert rec["bTips"] or not rec["bOpacity"], key
        for tip in map(_plain, rec["bTips"]):
            assert "Shower B's lines are drawn at 70% strength, raised where the card needs it to keep 3:1 (this one at " in tip
            assert ("so the end labels name the shower" in tip) == rec["twoOnShow"]
            strength = int(re.search(r"\(this one at (\d+)%\)", tip).group(1))
            assert strength >= 70 or "Provisional" in tip
    assert seen["ab"] and seen["lit"]
    assert not out["resFix"]["labels"]["two:all:deposit:a"]["endLabels"]["main"], "one shower, no literature: no label"
    assert not out["resFix"]["labels"]["two:all:deposit:a"]["twoOnShow"] and not out["resFix"]["labels"]["xgb:all:deposit:both"]["twoOnShow"]
    # A curve that leaves the plot before x.max has its caret and no label (a top of 30%: the deposit curves leave it).
    low = out["resFix"]["labels"]["low:all:deposit:both"]
    gone = [f for f in low["fits"] if f["end"][1] > low["yhi"]]
    assert gone and low["endLabels"]["main"]
    assert not {(f["key"], f["form"]) for f in gone} & {(x["key"], x["form"]) for x in low["endLabels"]["main"]}
    # The drawer, on the dark card (nothing raised) and on the light one (E2's network hue raised to 3:1).
    dark = [x for x in _dis(out["resFix"]["labels"]["two:anchors:deposit:both"]["notes"], out) if x.startswith("Shower B's lines")]
    assert dark == ["Shower B's lines are drawn at 70% strength, raised where the card needs it to keep 3:1 (no hue needs it on this "
                    "card), so the end labels \"A\" and \"B\" name the shower; on this view the dash means extrapolation, so shower B gives "
                    "up the long dash the 1/√E view gives it."]
    light = out["resFix"]["lightB"]
    raised = [s for s in light["strengths"] if s["op"] > 0.7 + 1e-6]
    assert raised, "the network hue needs more than 70% on the light card"
    line = next(x for x in _dis(light["notes"], out) if x.startswith("Shower B's lines"))
    named = ", ".join(f"{s['short']} at {round(100 * s['op'])}%" for s in raised)
    assert f"({named} on this card)" in line
    # The spread keeps order and the pitch, with the least displacement, inside the panel.
    assert out["resFix"]["spread"] == [[89, 101, 113, 300], [0, 12], [376, 388, 400], [50, 10, 30], []]


@pytest.mark.parametrize("medium", ["screen", "print"])
def test_res_fix_p3_the_note_band_never_overprints_and_never_cuts(out, medium):
    cases = out["resFix"]["note"][medium]
    assert [c["width"] for c in cases] == [321, 360, 440, 760, 1100]
    layouts = []
    for c in cases:
        left = next(g for g in c["graphics"] if g["text"].startswith("↑ off scale: "))
        right = next(g for g in c["graphics"] if g["text"].startswith("dashed: "))
        font, lh = c["fontTip"], left["lineHeight"]
        ls, rs_ = left["text"].split("\n"), right["text"].split("\n")
        # Never cut: the rule's lines are its whole sentence, the span "(4–20 GeV)" or "(Details)" included and on one line.
        assert " ".join(rs_) == c["extrapolation"], c["width"]
        span = re.search(r"\([^)]*\)", c["extrapolation"]).group(0)
        assert any(span in line for line in rs_), (c["width"], rs_)
        assert len(ls) <= 2 and left["x"] == c["padLeft"] and right["align"] == "right"
        if right["y"] == left["y"]:
            layouts.append("side")
            assert left["x"] + max(_width(t, font) for t in ls) <= right["x"] - max(_width(t, font) for t in rs_), c["width"]
        else:
            layouts.append("stacked")
            assert right["y"] == pytest.approx(left["y"] + len(ls) * lh), "the rule right-aligned beneath the list"
            assert left["x"] + max(_width(t, font) for t in ls) <= c["width"], "the list stays on the canvas"
        # The reserved height holds the layout: the main panel starts below the note's last line.
        assert max(left["y"] + len(ls) * lh, right["y"] + len(rs_) * lh) <= c["grid"][0]["top"] + 1e-9, c["width"]
    # 321 px (the 85 mm export under print) stacks: the first token alone is wider than the room beside the rule.
    assert layouts[0] == "stacked" and layouts[-1] == "side", layouts
    first = cases[0]["offScale"].split("; ")[0].split(", ")[0]
    assert _width(first, cases[0]["fontTip"]) > 0.5 * (cases[0]["width"] - cases[0]["padLeft"])
    if medium == "print":
        ex = out["resFix"]["note"]["export"]
        assert ex["off"] - ex["two"] == round(ex["offTop"] - ex["twoTop"]) > 0, "the export reserves the stacked note"


def test_res_fix_p4_ratio_ticks_below_one_read_one_over_x(out):
    assert out["resFix"]["tickLabels"] == ["1/2", "1/3", "1/1.5", "1/1.25", "1", "1.25", "2", "50", "1/50", "1/1.1"]


def test_res_fix_p5_the_grid_gap_is_one_point_four_label_heights_in_either_medium(out):
    gap = out["resFix"]["gap"]
    g0, g1 = gap["printGrid"]
    assert g1["top"] - (g0["top"] + g0["height"]) == round(1.4 * gap["print"]) and round(1.4 * gap["print"]) > 14
    assert round(1.4 * gap["screen"]) == 14


def test_res_fix_p6_p7_the_empty_state_and_a_cleared_card_keep_the_css_height(out):
    c = out["resFix"]["cls"]
    assert c["emptyDraws"] is False and c["drawsTwo"] is True
    assert c["empty"] in (None, ""), "the E view's one-sentence empty state stays 420 px"
    assert c["drawn"] == "600px" and c["cleared"] == "" and c["again"] == "600px" and c["emptyAfter"] == ""


def test_res_fix_p8_every_ratio_against_a_literature_curve_says_no_interval(out):
    pi, deposit = out["resFix"]["literatureTips"]["pi"], out["resFix"]["literatureTips"]["deposit"]

    def tips(chart, pattern):
        return [i["tip"] for s in chart["series"] if re.search(pattern, s["id"] or "") for i in s["items"] if i["tip"]]

    fits = tips(pi, r"\|ratio\|(quadrature|pinned)\|(solid|dashed|band|edges)\|")
    carets = [t for t in tips(pi, r"\|ratio\|carets$") if "leaves the ratio axis" in t]
    unity, lit = tips(pi, r"^ratio\|unity$"), tips(pi, r"^literature\|\w+\|caret$")
    assert fits and carets and unity and lit, "the clone draws every kind of mark the rule names"
    for t in fits + carets + unity + lit:
        assert _plain(t).endswith(LIT_NO_INTERVAL), _plain(t)[-160:]
    assert all("the reference is held exact." in t for t in fits)
    assert all("its own uncertainty is not included" not in t for t in fits)
    # Under the deposit reference no tooltip says it; its band is drawn beside the ratio, not folded in.
    assert not [t for s in deposit["series"] for i in s["items"] if (t := i["tip"]) and LIT_NO_INTERVAL in t]
    dep = tips(deposit, r"\|ratio\|(quadrature|pinned)\|(solid|dashed|band|edges)\|")
    assert dep and all("the reference is held exact (its own band about 1 is drawn beside it, not folded in)." in t for t in dep)


def test_res_fix_p9_a_robust_ratio_beyond_fifty_is_capped_and_said(out):
    c = out["resFix"]["capped"]
    assert (c["k"], c["capped"], c["provisional"], c["uncapped"]) == (50, 1, False, 0)
    assert c["axisName"].endswith("— capped at ×50")
    assert c["clipped"]["markers"] >= 1
    assert ("The ratio axis is capped at ×50, the last step of its ladder: 1 robust ratio mark reaches beyond it (whiskers "
            "included), clipped there with carets whose tooltips give the true values.") in _dis(c["notes"], out)
    assert c["ranges"] == [{"k": 50, "provisional": False, "capped": 1}, {"k": 50, "provisional": False, "capped": 1},
                           {"k": 50, "provisional": True, "capped": 0}, {"k": 50, "provisional": False, "capped": 0}]


def test_res_fix_p10_a_ratio_mark_against_a_provisional_reference_is_not_robust(out):
    seen = 0
    for name in RES:
        for windows in ("anchors", "all"):
            model = out["resE"]["fixtures"][name]["models"][f"{windows}:deposit"]
            for shower, ref in model["reference"]["byShower"].items():
                if not ref["provisional"]:
                    continue
                seen += 1
                for s in (x for x in model["series"] if (x["shower"] or "a") == shower):
                    assert not [p for p in s["points"] if p["ratio"]["robust"]], (name, windows, s["key"])
            if all(r["provisional"] for r in model["reference"]["byShower"].values()):
                assert model["ratio"]["provisional"] is True, (name, windows)
                chart = out["resE"]["fixtures"][name]["charts"][f"{windows}:deposit"]
                assert chart["yAxes"][1]["name"].endswith("— provisional")
            # The same windows against a literature curve, which is not provisional, are robust again.
            lit = out["resE"]["fixtures"][name]["models"][f"{windows}:pi"]
            assert any(p["ratio"]["robust"] for s in lit["series"] for p in s["points"]) == any(
                p["robust"] for s in lit["series"] for p in s["points"])
    assert seen, "the single-shower fixtures' deposit reference is provisional"


@pytest.mark.parametrize("name", RES)
def test_res_fix_p11_no_series_dodge_on_the_e_view(out, name):
    for key in RES_E_KEYS:
        model = out["resE"]["fixtures"][name]["models"][key]
        chart = out["resE"]["fixtures"][name]["charts"][key]
        assert all(s["offsetPx"] == 0 for s in model["series"])
        for s in model["series"]:
            markers = next((x for x in chart["chart"]["series"] if x["id"] == f"{s['key']}|markers"), None)
            shown = [p for p in s["points"] if not p["over"]]
            if not markers:
                continue
            for item, p in zip(markers["items"], shown):
                el = item["el"] if item["el"]["type"] == "circle" else item["el"]["children"][0]
                assert el["circle"]["cx"] == pytest.approx(p["E"]), "a window sits at its exact E"


@pytest.mark.parametrize("name", RES)
def test_res_fix_p12_a_curve_is_solid_over_the_span_of_its_windows(out, name):
    chart = out["resE"]["fixtures"][name]["charts"]["all:deposit"]
    model = out["resE"]["fixtures"][name]["models"]["all:deposit"]
    for s, form, f in _e_drawn_fits(model):
        for x in chart["chart"]["series"]:
            if (x["id"] or "").startswith(f"{s['key']}|{form}|solid|"):
                tip = x["items"][0]["tip"]
                assert f"Solid over the span of the windows it was fitted to ({_span(f['span'])}); dashed beyond" in tip


def test_res_fix_p13_a_reference_band_reaching_the_ratio_axis_is_outlined(out):
    """A deposit reference's band about 1 contains 1, the centre of the log-symmetric ratio axis, so once it
    reaches either end it covers half the axis or more, and OUTLINE_SHARE = 0.5 draws it as its edges: a
    clamped reference wash, and so its muted caret (kept for a share above one half), cannot occur."""
    r = out["resFix"]["refCaret"]
    reaching = [x for x in r["refs"] if x["clipped"] or x["outlined"]]
    assert reaching, "the anchors-mode fixture's reference bands reach the ratio axis"
    assert all(x["outlined"] is True and not x["cut"] for x in reaching)
    assert r["carets"] == [] and r["bands"] == 0
    assert r["ratio"] == r["clipped"]["markers"] + r["clipped"]["whiskers"] + r["clipped"]["fits"] + r["clipped"]["bands"]


def test_res_fix_p14_a_provisional_sigma_axis_names_the_two_gev_floor(out):
    assert out["resFix"]["provisional"]["axisName"] == "σ/E [%] — provisional, no window from 2 GeV reaches N = 20"
    assert out["resE"]["provisional"]["yAxes"][0]["name"] == "σ/E [%] — provisional, no window from 2 GeV reaches N = 20"


def test_res_fix_n2_the_literature_provenance_says_its_range_is_unknown(out):
    chart = out["resE"]["fixtures"]["res_scaling_two"]["charts"]["all:pi"]
    lits = [s for s in chart["chart"]["series"] if re.fullmatch(r"literature\|\w+", s["id"] or "")]
    assert len(lits) == 2 and all(NO_RANGE in s["items"][0]["tip"] for s in lits)
    for name, key, rec in _e_notes(out):
        dis = _dis(rec["notes"], out)
        said = [line for line in dis if line.startswith("The figure does not state the energy range the curve was fitted over")]
        assert len(said) == (0 if key.split(":")[1] == "deposit" else 1), (name, key)


def test_res_fix_n3_the_quadrature_band_is_cut_where_its_square_falls_below_zero(out):
    lines = [line for _, _, rec in _e_notes(out) for line in _dis(rec["notes"], out) if " cut at 0: " in line]
    assert any("where the band of (σ/E)² falls below zero, its lower edge is cut at 0" in line for line in lines)
    assert not [line for line in lines if "cut at σ/E = 0 where it would be negative" in line]


def test_res_fix_n4_a_provisional_range_names_what_sets_it(out):
    p = out["resFix"]["provisional"]
    weaker = [x for x in _dis(p["weaker"], out) if x.startswith("The y range is provisional")]
    # What sets it, counted over every series of the response (the range is the response's, not the mode's).
    windows = [w for s in _load("res_scaling_two")["series"] for w in s["windows"] if w["value"] is not None and w["n"] >= 2]
    weak = sum(1 for w in windows if w["p_lo"] >= 2 and w["n"] < 20)
    below = sum(1 for w in windows if w["p_lo"] < 2)
    by = [f"the {_n(weak, 'window')} of N < 20 from 2 GeV"] * bool(weak) + [f"the markers of the {_n(below, 'window')} below 2 GeV"] * bool(below)
    assert weak and weaker == [f"The y range is provisional: no window from 2 GeV reaches N = 20, so it is set by weaker windows "
                               f"of the response, {' and '.join(by)}."]
    nothing = [x for x in _dis(p["nothing"], out) if x.startswith("The y range is provisional")]
    assert nothing == ["The y range is provisional: no window from 2 GeV reaches N = 20, and no window of the response reports σ/E, "
                       "so nothing on the plot sets it."]
    assert not [x for _, _, rec in _e_notes(out) for x in _dis(rec["notes"], out) if x.endswith("so it is set by weaker windows.")]


def test_res_fix_no_rendered_number_uses_an_ascii_hyphen(out):
    fix = out["resFix"]
    _no_hyphen_numbers(fix["outlined"]["chart"]["strings"])
    _no_hyphen_numbers(e["tip"] for e in fix["outlined"]["edges"] + fix["refOutlined"]["edges"])
    _no_hyphen_numbers(c["tip"] for c in fix["refCaret"]["carets"])
    _no_hyphen_numbers(fix["literatureTips"]["pi"]["strings"] + fix["literatureTips"]["deposit"]["strings"])
    _no_hyphen_numbers([fix["capped"]["axisName"], fix["provisional"]["axisName"], *fix["tickLabels"]])
    for medium in ("screen", "print"):
        _no_hyphen_numbers(g["text"] for c in fix["note"][medium] for g in c["graphics"])
    notes = [fix["outlined"]["notes"], fix["refOutlined"]["notes"], fix["capped"]["notes"], fix["refCaret"]["notes"],
             fix["provisional"]["weaker"], fix["provisional"]["nothing"], fix["lightB"]["notes"],
             *(rec["notes"] for rec in fix["labels"].values())]
    _no_hyphen_numbers(line for n in notes for lines in n["sections"].values() for line in lines)
