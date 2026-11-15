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
from decimal import ROUND_HALF_UP, Decimal
import math
import statistics
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
        cutTip: s.fits[f].cut ? rs.fitCutTip(m, s, s.fits[f]) : null,
        outlined: s.fits[f].outlined, span: s.fits[f].span, xSpan: s.fits[f].xSpan } : null])),
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
    status: rs.fitTableRows(unsettled, { windows: 'anchors' }).rows.find((r) => r.key === 'network:a').fits[0].cells[6],
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
  // The fields the single-curve round retired (Martin's directive of 2026-11-15: no band on the E view): any of them
  // still on a model object is listed, so a test can pin that none is.
  const RETIRED_REF = ['band', 'outlined', 'edges', 'edgesOffAxis', 'bandCut', 'bandClipped', 'envelope', 'singular'];
  const RETIRED_FIT = ['band', 'outlined', 'edges', 'floorCut', 'envelope', 'singular'];
  const RETIRED_ENTRY = ['bandAt', 'lowAt', 'bandAbove'];
  const retiredOn = (o, keys) => (o ? keys.filter((k) => k in o) : []);
  const packRef = (r) => ({ key: r.key, shower: r.shower, form: r.form, series: r.series, label: r.label, reason: r.reason,
    span: r.span, interval: r.interval, retired: retiredOn(r, RETIRED_REF), literature: r.literature?.key ?? null,
    provisional: r.provisional, misfit: r.misfit ?? null, why: r.why ?? null,
    floorGev: r.floorGev ?? null, floorBy: r.floorBy ?? null, noiseReason: r.noiseReason ?? null, held: r.held ?? null });
  const packModel = (m, full) => ({
    x: m.x, y: m.y, curveMinGev: m.curveMinGev, noiseMinGev: m.noiseMinGev, yMinGev: m.yMinGev, nPoints: m.nPoints, nLines: m.nLines,
    nShowers: m.nShowers,
    reference: { key: m.reference.key, label: m.reference.label, interval: m.reference.interval, flag: m.reference.flag,
      byShower: Object.fromEntries(Object.entries(m.reference.byShower).map(([k, r]) => [k, packRef(r)])) },
    ratio: m.ratio, clipped: m.clipped, offScale: m.offScale, spans: m.spans, noteText: m.noteText,
    retired: { bandsOutlined: 'bandsOutlined' in m, ratioBands: 'bands' in m.ratio.clipped }, twoOnShow: m.twoOnShow, endLabels: m.endLabels,
    // The literature curve in force is always packed whole: under 'e' it is the only record of the e± curve.
    literature: m.literature.map((l) => ({ key: l.key, label: l.label, legend: l.legend, colour: l.colour, cut: l.cut,
      curve: l.curve, runs: l.runs })),
    series: m.series.map((s) => ({
      key: s.key, shower: s.raw.shower ?? null, source: s.raw.source, isB: s.isB, colour: s.colour, span: s.span, offsetPx: s.offsetPx,
      lineOpacity: s.lineOpacity(false), lineOpacityFaded: s.lineOpacity(true), reference: s.reference ? packRef(s.reference) : null,
      unreported: s.unreported.map((w) => w.bin), noise: s.noise, drawnForm: s.drawnForm,
      drawnIsFit: s.drawn === null ? null : s.drawn === s.fits[s.drawnForm],
      points: s.points.map((p) => ({ bin: p.w.bin, label: p.w.label, x: p.x, E: p.E, value: p.value, lo: p.lo, hi: p.hi, n: p.n,
        pLo: p.w.p_lo, whisker: p.whisker, weak: p.weak, subFloor: p.subFloor, below4: p.below4, fitted: p.fitted, robust: p.robust,
        belowNoise: p.belowNoise, noiseFitted: p.noiseFitted, lowAnchor: p.lowAnchor, anchor: p.anchor,
        over: p.over, roles: p.roles, clip: p.clip,
        ratio: { drawn: p.ratio.drawn, reason: p.ratio.reason, ref: p.ratio.ref, value: p.ratio.value, lo: p.ratio.lo, hi: p.ratio.hi,
          over: p.ratio.over ?? null, clip: p.ratio.clip ?? null, robust: p.ratio.robust } })),
      fits: Object.fromEntries(rs.ENERGY_FORMS.map((form) => {
        const f = s.fits[form];
        if (!f.drawable) return [form, { drawable: false, reason: f.reason, span: f.span }];
        return [form, { drawable: true, reason: f.reason, span: f.span, domain: f.domain, provisional: f.provisional,
          misfit: f.misfit, faded: f.faded, entry: f.entry ?? null, held: f.held ?? null, points: f.points ?? null,
          lowAnchor: f.lowAnchor ?? null, full: full ? (f.full ?? null) : null, fallback: f.fallback ?? null, noiseReason: f.noiseReason ?? null,
          converged: f.converged, isReference: f.isReference, cut: f.cut,
          retired: [...retiredOn(f, RETIRED_FIT), ...retiredOn(f.entry, RETIRED_ENTRY).map((k) => `entry.${k}`),
            ...retiredOn(f.ratio, RETIRED_FIT).map((k) => `ratio.${k}`)],
          rowWidths: [...new Set([...(f.curve ?? []), ...(f.full ?? []), ...(f.ratio?.rows ?? [])].map((r) => r.length))],
          curve: full ? f.curve : null, solid: full ? f.solid : null, dashed: full ? f.dashed : null,
          ratio: f.ratio ? { solid: full ? f.ratio.solid : null, dashed: full ? f.ratio.dashed : null, cut: f.ratio.cut,
            entry: f.ratio.entry ?? null, rows: full ? f.ratio.rows : null } : null }];
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
      legendItems: [].concat(o.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => ({ name: d?.name ?? d, icon: d?.icon ?? null,
        colour: d?.itemStyle?.color ?? null }))),
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
      // a/√E ⊕ b ⊕ c/E at fixed energies (the Python side holds it to rfit.band on a Fit rebuilt from the block,
      // its free face included). The quadrature form is tabled only and has no evaluator (brief-fix nit 2).
      for (const s of payload.series) {
        for (const form of ['affine', 'pinned', 'noise']) {
          const fit = s.fits[windows][form];
          if (!fit) continue;
          const key = `${name}:${windows}:${s.key}:${form}`;
          if (form === 'noise') {
            const energies = [0.05, 0.2, 0.5, 1, 2, 3.5, 4, 5, 7.5, 10, 16, 20, 40, 80];
            out.resE.evaluators[key] = { energies, js: rs.fitCurveE(fit, energies), drawable: rs.noiseDrawable?.(fit) ?? null };
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
  // a/√E ⊕ b ⊕ c/E (Martin's decisions of 2026-11-13): cases built on the two-shower payload, changed only where the
  // server would change them.
  {
    const packNotes = (n) => (n ? { title: n.title, hazards: n.hazards, sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
    const NO_NOISE = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.';
    const noiseCase = (payload, windows) => {
      const opts = { view: 'energy', windows, shower: 'both', reference: 'deposit' };
      const m = rs.energyModel(payload, opts);
      const w = walk(rs.energyViewOption(payload, opts, RE).option);
      const tipsOf = (re) => Object.fromEntries(w.series.filter((x) => re.test(x.id ?? '')).map((x) => [x.id, x.items.map((i) => i.tip)]));
      return {
        model: packModel(m, true), strings: w.strings,
        ids: w.series.map((x) => x.id),
        carets: w.series.filter((x) => (x.id ?? '').endsWith('|carets')).map((x) => ({ id: x.id, items: x.items.map((i) => ({ value: i.value, tip: i.tip })) })),
        noiseTips: tipsOf(/\|noise\|(solid|dashed|band|edges)\|/),
        fallbackTips: tipsOf(/^detector:a\|pinned\|(solid|dashed)\|/),
        ratioNoiseTips: tipsOf(/\|ratio\|noise\|(solid|dashed|band|edges)\|/),
        ratioMarkerTips: tipsOf(/\|ratio\|markers$/),
        table: rs.fitTableRows(payload, opts), linearTable: rs.fitTableRows(payload, { windows, shower: 'both' }),
        notes: packNotes(mn.resolutionScalingNotes({ payload, state: { isTouched: () => false, get: () => null }, experiment: { display_name: 'Demo' }, ...opts })),
      };
    };
    // Shower A's deposit with no noise fit in either mode: its ratio falls back to a₀/√E from 4 GeV, saying why.
    const fallback = clone(two);
    for (const mode of ['anchors', 'all']) {
      const mf = fallback.series.find((x) => x.key === 'detector:a').fits[mode];
      mf.noise = null; mf.noise_reason = NO_NOISE;
    }
    // A top below b: the deposit A's curve (b = 53.6%%) and the flat network A (b = 79.7%%) lie above it everywhere.
    const above = clone(two);
    above.axis.energy.y.hi = 30; above.axis.energy.y.interval = 10;
    // The flat network A (a and c held) with SE(b²) raised a thousandfold: before the single-curve round its band's
    // upper edge lay above the top at every E. With no band on the view (Martin's directive of 2026-11-15) an SE moves
    // no drawn mark: only its tooltip's numbers.
    const bandAbove = clone(two);
    bandAbove.series.find((x) => x.key === 'network:a').fits.anchors.noise.params.se_b2 = 1e5;
    // A fit that holds no term: shower B's deposit, its c freed (the server would refit; only the fields change here).
    const free = clone(two);
    {
      const pf = free.series.find((x) => x.key === 'detector:b').fits.anchors.noise.params;
      Object.assign(pf, { c2: 400, se_c2: 300, c: 20, se_c: 7.5, held: [] });
      pf.rho = { a2b2: -0.5, a2c2: -0.3, b2c2: -0.2 };
    }
    // The single-curve round (Martin's directive of 2026-11-15) retired FX1's all-free face and the noise block's
    // band_quantile. A recording from before it (`params.free` on every block that holds a term, `band_quantile` on
    // every noise block, `weight_scale.c_low` / `n_low`) must draw exactly what the new wire draws: no client code
    // reads them. `singular` is the old wire, `singularCurves` its line, which must equal the new wire's.
    const singular = clone(two);
    const singularCurves = {};
    for (const sx of singular.series) {
      if (sx.weight_scale) Object.assign(sx.weight_scale, { c_low: 3.94, n_low: 2 });
      for (const mode of ['anchors', 'all']) {
        const nf = sx.fits[mode].noise;
        if (!nf) continue;
        nf.band_quantile = 12.7062;
        if ((nf.params.held ?? []).length) {
          nf.params.free = { a2: 1234, b2: -56, c2: 789, se_a2: 300, se_b2: 40, se_c2: 500, rho: { a2b2: -0.9, a2c2: -0.8, b2c2: 0.7 } };
        }
        const energies = [0.05, 0.5, 1, 2, 4, 10, 20, 80];
        singularCurves[`${mode}:${sx.key}`] = { energies, js: rs.fitCurveE(nf, energies),
          base: rs.fitCurveE(two.series.find((x) => x.key === sx.key).fits[mode].noise, energies) };
      }
    }
    // Review nit 1: a robust all-windows mode that declines its one fittable window from 4 GeV while the noise fit
    // uses it (NF-panel's synthetic copy of robust_two: every other window from 4 GeV thinned to N = 10).
    const declinedCase = (() => {
      const r = load('res_scaling_robust_two');
      for (const sx of r.series) {
        const mf = sx.fits.all;
        if (!mf.noise) continue;
        const hi = mf.noise.points.map((b) => sx.windows.find((w) => w.bin === b)).filter((w) => w && w.p_lo >= 4);
        if (!hi.length) continue;
        const keep = hi[0];
        for (const w of sx.windows) if (w.p_lo >= 4 && w.bin !== keep.bin) w.n = 10;
        mf.points = [];
        const mm = rs.energyModel(r, { view: 'energy', windows: 'all', shower: 'both' });
        const pt = mm.series.find((x) => x.key === sx.key).points.find((q) => q.w.bin === keep.bin);
        return { key: sx.key, label: keep.label, n: keep.n, roles: pt.roles,
          declinedText: rs.declinedText(keep), tip: rs.energyPointTip(mm, mm.series.find((x) => x.key === sx.key), pt) };
      }
      return null;
    })();
    // Review nit 8: a robust payload with no window of 2 ≤ N < 20 left without a value (each thinned to N = 1), so
    // robustFloorLine's first count is 0 and its clause is not printed.
    const noThin = load('res_scaling_robust_two');
    for (const sx of noThin.series) for (const w of sx.windows) if (w.n >= 2 && w.n < 20 && !Number.isFinite(w.value)) w.n = 1;
    const robustNotes = (payload) => ['linear', 'energy'].flatMap((view) => ['anchors', 'all'].map((windows) => packNotes(
      mn.resolutionScalingNotes({ payload, view, windows, shower: 'both', literature: [] }))));
    // brief-fix FX3: the removed fields put back with sentinels (every fit block's and the noise block's `note`, the
    // quadrature rho_a2b2 / se_a2_stat / se_b2_stat): no client output may change, so no client code reads them.
    const everything = (payload) => JSON.stringify(['anchors', 'all'].flatMap((windows) => [
      walk(rs.resolutionScalingOption(payload, { windows, shower: 'both' }, { width: 760, height: 420 })),
      walk(rs.energyViewOption(payload, { view: 'energy', windows, shower: 'both', literature: ['pi', 'e'] }, RE).option),
      rs.fitTableRows(payload, { windows, shower: 'both' }), rs.fitTableRows(payload, { view: 'energy', windows, shower: 'both' }),
      ...['linear', 'energy'].map((view) => packNotes(mn.resolutionScalingNotes({ payload, view, windows, shower: 'both', literature: ['pi', 'e'] }))),
    ]));
    const removedFields = {};
    for (const nm of ['res_scaling_two', 'res_scaling_median_two', 'res_scaling_robust_xgb']) {
      const back = load(nm);
      for (const sx of back.series) {
        for (const mode of ['anchors', 'all']) {
          for (const form of ['affine', 'pinned', 'quadrature', 'noise']) {
            const f = sx.fits[mode][form];
            if (!f) continue;
            f.note = `SENTINEL_FX3_NOTE ${form}`;
            if (form === 'quadrature') Object.assign(f.params, { rho_a2b2: 0.3141592, se_a2_stat: 2718.28, se_b2_stat: 1414.21 });
          }
        }
      }
      const a = everything(load(nm));
      const b = everything(back);
      removedFields[nm] = { same: a === b, sentinel: b.includes('SENTINEL_FX3'), length: a.length };
    }
    // The single-curve round's retired wire fields put back as a recording from before it carried them: the all-free
    // face (`params.free`) on every noise block that holds a term, the noise block's `band_quantile`, and
    // `weight_scale.c_low` / `n_low`. No client output may change on any of the twelve recordings.
    const oldWire = {};
    for (const nm of fs.readdirSync(fixtureDir).filter((f) => /^res_scaling_.*\.json$/.test(f)).map((f) => f.slice(0, -5)).sort()) {
      const back = load(nm);
      let touched = 0;
      for (const sx of back.series) {
        if (sx.weight_scale) { Object.assign(sx.weight_scale, { c_low: 9.876, n_low: 3 }); touched += 1; }
        for (const mode of ['anchors', 'all']) {
          const nf = sx.fits[mode].noise;
          if (!nf) continue;
          nf.band_quantile = 12.7062;
          touched += 1;
          if ((nf.params.held ?? []).length) {
            nf.params.free = { a2: 1234, b2: -56, c2: 789, se_a2: 300, se_b2: 40, se_c2: 500, rho: { a2b2: -0.9, a2c2: -0.8, b2c2: 0.7 } };
          }
        }
      }
      const a = everything(load(nm));
      const b = everything(back);
      oldWire[nm] = { same: a === b, touched, cLow: a.includes('c_low') || b.includes('c_low') };
    }
    out.resE.fixRound = { declined: declinedCase, noThin: robustNotes(noThin), thin: robustNotes(load('res_scaling_robust_two')),
      removedFields, oldWire };

    // The noise line on every recording (the single-curve round): fitCurveE at fixed energies, for the Python side to
    // hold to the server's Fit.predict; and the module-private evalFitAt, reached through a copy of the module whose
    // relative imports point at the same files (so it shares their instances) and which exports it, on every block.
    const src = fs.readFileSync(new URL(`${jsRoot}/panels/resolution_scaling.js`), 'utf8')
      .replaceAll("from '../", `from '${jsRoot}/`).replaceAll("from './", `from '${jsRoot}/panels/`);
    const priv = await import(`data:text/javascript;base64,${Buffer.from(`${src}\nexport { evalFitAt as __evalFitAt };\n`).toString('base64')}`);
    const LINE_E = [0, 0.05, 0.2, 0.5, 1, 2, 3.5, 4, 5, 7.5, 10, 16, 20, 40, 80];
    const noiseLines = {};
    for (const nm of fs.readdirSync(fixtureDir).filter((f) => /^res_scaling_.*\.json$/.test(f)).map((f) => f.slice(0, -5)).sort()) {
      for (const sx of load(nm).series) {
        for (const mode of ['anchors', 'all']) {
          const nf = sx.fits[mode].noise;
          if (!nf) continue;
          // The same block as an old recording carried it (band_quantile, the all-free face), and with SEs a
          // thousandfold: no band, conditional or enveloped, comes out of either evaluator.
          const loud = clone(nf);
          loud.band_quantile = 12.7062;
          loud.params.free = { a2: 1, b2: 2, c2: 3, se_a2: 4, se_b2: 5, se_c2: 6, rho: { a2b2: 0, a2c2: 0, b2c2: 0 } };
          for (const k of ['se_a2', 'se_b2', 'se_c2', 'se_a', 'se_b', 'se_c']) if (loud.params[k] !== null) loud.params[k] *= 1000;
          const evals = LINE_E.map((e) => priv.__evalFitAt(nf, e));
          noiseLines[`${nm}:${mode}:${sx.key}`] = {
            energies: LINE_E, js: rs.fitCurveE(nf, LINE_E), loud: rs.fitCurveE(loud, LINE_E),
            evalKeys: [...new Set(evals.filter(Boolean).flatMap((v) => Object.keys(v)))].sort(),
            evalLoudKeys: [...new Set(LINE_E.map((e) => priv.__evalFitAt(loud, e)).filter(Boolean).flatMap((v) => Object.keys(v)))].sort(),
            evalY: evals.map((v) => v?.y ?? null),
          };
        }
      }
    }
    // The pinned and affine forms keep their band (the 1/√E view's `withSpanEdges` reads it): the evaluator's keys there.
    const two0 = load('res_scaling_two').series[0].fits.all;
    out.resE.noiseLines = { lines: noiseLines, pinnedKeys: Object.keys(priv.__evalFitAt(two0.pinned, 10) ?? {}).sort(),
      affineKeys: Object.keys(priv.__evalFitAt(two0.affine, 10) ?? {}).sort() };
    out.resE.noise = {
      singular: { anchors: noiseCase(singular, 'anchors'), all: noiseCase(singular, 'all'), curves: singularCurves },
      // The FX1 band texts and the conditional-band text left the module with the band (single-curve round).
      retiredExports: ['noiseBandText', 'noiseConditionalText', 'energyBandTip'].filter((k) => k in rs),
      noBandText: rs.ENERGY_NO_BAND_TEXT ?? null,
      axisLine: { share: rs.NOISE_AXIS_SHARE ?? null, text: rs.NOISE_AXIS_LINE_TEXT ?? null },
      fallback: { anchors: noiseCase(fallback, 'anchors'), all: noiseCase(fallback, 'all') },
      above: noiseCase(above, 'anchors'), bandAbove: noiseCase(bandAbove, 'anchors'), free: noiseCase(free, 'anchors'),
      noReason: NO_NOISE,
      xgbAll: noiseCase(load('res_scaling_xgb'), 'all'),
      held: [[], ['b'], ['a', 'c'], ['a', 'b', 'c']].map((h) => [rs.noiseHeldPhrase?.(h) ?? null]),
      correlation: [
        {}, { a2b2: null, a2c2: null, b2c2: null }, { a2b2: -0.9, a2c2: -0.8, b2c2: 0.1 }, { a2b2: -0.95, a2c2: -0.71, b2c2: -0.3 },
        { a2b2: -0.837128, a2c2: null, b2c2: null }, { a2b2: null, a2c2: null, b2c2: -0.292308 }, { a2b2: 0.85, a2c2: -0.2, b2c2: null },
        { a2b2: -0.69999, a2c2: null, b2c2: null }, { a2b2: -0.7, a2c2: null, b2c2: null },
      ].map((rho) => rs.noiseCorrelationText?.(rho) ?? null),
      words: { strong: rs.NOISE_STRONG_RHO ?? null, caveat: rs.NOISE_NAMING_CAVEAT ?? null, floor: rs.noiseFloorText?.(1) ?? null,
        constraint: rs.noiseConstraintText?.('σ/E') ?? null,
        below: [rs.noiseBelowText?.(1) ?? null, rs.noiseBelowText?.(2) ?? null],
        entry: [rs.noiseEntryText?.(1.25, 'c') ?? null, rs.noiseEntryText?.(0.0035, 'a') ?? null],
        lowAnchor: [rs.noiseLowAnchorText?.('3–4 GeV', 1, 3) ?? null, rs.noiseLowAnchorText?.('1–2 GeV', 1, 2) ?? null], name: rs.NOISE_FORM_NAME ?? null },
    };
  }
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
    // The quadrature form has no evaluator and no drawable test any more (brief-fix nit 2): a quadrature block gives
    // fitCurveE nothing, defined or not.
    quadratureCurve: [
      rs.fitCurveE({ form: 'quadrature', params: { a_defined: true, b_defined: true, a2: 1, b2: 1, se_a2: 0.1, se_b2: 0.1 } }, [1, 4, 16]),
      rs.fitCurveE({ form: 'quadrature', params: { a_defined: false, b_defined: true, a2: -1, b2: 1 } }, [1, 4, 16]),
    ],
    exportsQuadratureDrawable: 'quadratureDrawable' in rs,
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
  // The literature curves' identity colours (palette.js), and the palette each card picks them by.
  const litOf = (reference) => {
    const m = rs.energyModel(two, { windows: 'all', reference });
    return { palette: scale.THEME.qualitativePalette, card: scale.THEME.card, literature: m.literature.map((l) => ({ key: l.key, colour: l.colour })),
      endLabels: m.endLabels.main.filter((l) => l.literature) };
  };
  out.resE.litColours = { table: palette.LITERATURE_COLOURS, hues: palette.LITERATURE_HUES, dark: { pi: litOf('pi'), e: litOf('e') },
    refusals: [['pi', 'viridis'], ['mu', 'set2'], ['e', undefined]].map(([key, pal]) => {
      try { return palette.literatureColour(key, pal); } catch (err) { return `threw: ${err.message}`; }
    }) };
  scale.setScreenTheme('light');
  out.resE.ink.light = inkOf();
  out.resE.lightChart = optionOf(two, { windows: 'all', reference: 'pi' });
  out.resE.lightChartE = optionOf(two, { windows: 'all', reference: 'e' });
  out.resE.litColours.light = { pi: litOf('pi'), e: litOf('e') };
  scale.setScreenTheme('dark');

  // Martin's requests of 2026-11-11: one pair of toggles, both on by default; they also pick the ratio's reference.
  const litCase = (payload, literature, windows = 'all') => {
    const opts = { view: 'energy', windows, shower: 'both', literature };
    const m = rs.energyModel(payload, opts);
    return {
      reference: m.reference.key, choice: m.reference.choice, label: m.reference.label,
      literature: m.literature.map((l) => ({ key: l.key, isReference: l.isReference, colour: l.colour, cut: l.cut,
        ratio: l.ratio ? { rows: l.ratio.rows, runs: l.ratio.runs, cut: l.ratio.cut } : null })),
      points: m.series.flatMap((s) => s.points.map((p) => ({ E: p.E, value: p.value, n: p.n, pLo: p.w.p_lo }))),
      k: m.ratio.k, ratioClipped: m.ratio.clipped, clippedRatio: m.clipped.ratio,
      endMain: m.endLabels.main.filter((l) => l.literature), endRatio: m.endLabels.ratio.filter((l) => l.literature),
      chart: optionOf(payload, opts),
      unityTip: (() => { const u = rs.energyViewOption(payload, opts, RE).option.series.find((x) => x.id === 'ratio|unity'); return u?.tooltip?.formatter?.() ?? null; })(),
      notes: (() => {
        const n = mn.resolutionScalingNotes({ payload, ...opts });
        return { title: n.title, hazards: n.hazards, sections: Object.fromEntries(n.sections.map((sec) => [sec.heading, sec.lines])) };
      })(),
      hazards: mn.modelsHazards(payload, 'res-scaling', opts),
    };
  };
  // A clone whose windows sit at 0.7 × π±: π± is then the farther curve (|ln 0.7| = 0.36 against |ln 1.37| = 0.31),
  // the reference; k is 1.5, and e±/π± (about 0.51) lies below 1/k.
  const scaled = (factor, key) => {
    const c = clone(two);
    const lit = cat.referenceOf(key);
    for (const s of c.series) {
      for (const w of s.windows) {
        if (!(w.p_lo >= 2) || !(w.x > 0)) continue;
        const v = factor * cat.referenceValue(lit, 1 / (w.x * w.x));
        Object.assign(w, { n: 200, value: v, ci95: [0.99 * v, 1.01 * v], whisker: true, weak: false });
      }
    }
    return c;
  };
  const W = (E, value, n = 100, pLo = E - 0.5) => ({ E, value, n, pLo });
  out.resE.litToggles = {
    drawn: [[['pi', 'e'], null], [['e', 'pi', 'mu'], null], [[], 'pi'], [undefined, 'e'], [undefined, 'deposit'], [undefined, null], ['e', null]]
      .map(([lit, ref]) => rs.literatureDrawn(lit, ref)),
    choices: {
      none: rs.ratioReferenceChoice([], [W(10, 20)]),
      one: rs.ratioReferenceChoice(['e'], [W(10, 20)]),
      onPi: rs.ratioReferenceChoice(['pi', 'e'], [5, 10, 15].map((E) => W(E, cat.referenceValue(cat.referenceOf('pi'), E)))),
      onE: rs.ratioReferenceChoice(['pi', 'e'], [5, 10, 15].map((E) => W(E, cat.referenceValue(cat.referenceOf('e'), E)))),
      // The geometric mean of the two curves: equally far from both, so π± (the catalogue's first).
      tie: rs.ratioReferenceChoice(['pi', 'e'], [10].map((E) => W(E, Math.sqrt(cat.referenceValue(cat.referenceOf('pi'), E) * cat.referenceValue(cat.referenceOf('e'), E))))),
      empty: rs.ratioReferenceChoice(['pi', 'e'], []),
      // No robust window (N < 20): every window on show decides, and says so.
      markers: rs.ratioReferenceChoice(['pi', 'e'], [W(10, 2.0, 5), W(12, 2.2, 5)]),
      // A robust window outweighs any number of weak ones.
      robustWins: rs.ratioReferenceChoice(['pi', 'e'], [W(10, cat.referenceValue(cat.referenceOf('e'), 10), 100), W(10, 50, 5), W(12, 60, 5)]),
    },
    both: litCase(two, ['pi', 'e']),
    bothAnchors: litCase(two, ['pi', 'e'], 'anchors'),
    pi: litCase(two, ['pi']),
    e: litCase(two, ['e']),
    none: litCase(two, []),
    atSevenTenthsPi: litCase(scaled(0.7, 'pi'), ['pi', 'e']),
  };

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
    notDrawn: m.series.flatMap((s) => [...rs.ENERGY_FORMS, 'quadrature'].filter((f) => !s.fits[f].drawable)
      .map((f) => ({ label: s.label, form: f, reason: s.fits[f].reason }))),
    drawn: m.series.flatMap((s) => rs.ENERGY_FORMS.filter((f) => s.fits[f].drawable).map((f) => ({
      label: s.label, form: f, provisional: s.fits[f].provisional, converged: s.fits[f].converged,
      cut: Boolean(s.fits[f].cut), cutPeak: s.fits[f].cut?.peak ?? null, misfit: Boolean(s.fits[f].misfit),
      fallback: Boolean(s.fits[f].fallback), noiseReason: s.fits[f].noiseReason ?? null,
      entry: s.fits[f].entry ? { lineAt: s.fits[f].entry.lineAt, above: s.fits[f].entry.above, atAxis: s.fits[f].entry.atAxis,
        term: s.fits[f].entry.term } : null, held: s.fits[f].held ?? null }))),
    // The series with no curve at all (neither fit drawable), and why.
    noCurve: m.series.filter((s) => !s.drawn).map((s) => ({ label: s.label, noise: s.fits.noise.reason, pinned: s.fits.pinned.reason })),
    ratioBelow: m.ratio.below, noiseMinGev: m.noiseMinGev,
    anyUnconverged: m.series.some((s) => [s.mf?.affine, s.mf?.pinned, s.mf?.quadrature].some((f) => f && f.converged === false)),
    points: { weak: m.series.flatMap((s) => s.points).filter((p) => p.weak).length, weakAlone: m.series.flatMap((s) => s.points).filter((p) => p.weak && !p.subFloor && !p.fitted && !p.noiseFitted).length,
      weakNoiseOnly: m.series.flatMap((s) => s.points).filter((p) => p.weak && !p.subFloor && !p.fitted && p.noiseFitted).length,
      subFloor: m.series.flatMap((s) => s.points).filter((p) => p.subFloor).length, below4: m.series.flatMap((s) => s.points).filter((p) => p.below4).length,
      ratioWhiskers: m.series.flatMap((s) => s.points).filter((p) => p.ratio.drawn && Number.isFinite(p.ratio.lo)).length },
    noReference: m.ratio.noReference, anyB: m.series.some((s) => s.isB),
    deposit: Object.values(m.reference.byShower).map((r) => ({ shower: r.shower, reason: r.reason, why: r.why, provisional: r.provisional })),
    notes: m.notes, rule: m.rule, noteText: m.noteText, nShowers: m.nShowers, mode: m.mode,
    retired: { bandsOutlined: 'bandsOutlined' in m, ratioBands: 'bands' in m.ratio.clipped }, capped: m.ratio.capped,
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
    // The noise fit too, as the server marks every fit of a mode that fell back (the drawn curve since the
    // single-curve round).
    for (const f of [s.fits[mode].affine, s.fits[mode].pinned, s.fits[mode].quadrature, s.fits[mode].noise]) if (f) f.provisional = true;
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
      texts: el.children.filter((c) => c.type === 'text').map((c) => ({ text: c.style.text, fill: c.style.fill, x: c.style.x, y: c.style.y, align: c.style.textAlign })),
      keys: el.children.filter((c) => c.type === 'line').map((c) => ({ stroke: c.style.stroke, width: c.style.lineWidth, dash: c.style.lineDash ?? null,
        opacity: c.style.opacity, x1: c.shape.x1, x2: c.shape.x2, y: c.shape.y1 })), ink: scale.THEME.text };
  });
  const two = load('res_scaling_two');
  const fix = {};

  // P1: an a/√E ⊕ b ⊕ c/E fit (the E view's drawn ⊕ form since Martin's decisions of 2026-11-13; the network A's,
  // a and c held, ν = 3) whose errors S = 1.5 scales, its band at a quantile of 12.71, on a top of 300%%, where its
  // upper edge crosses the plot and its lower edge is cut at 0.
  const t12 = clone(two);
  t12.axis.energy.y.hi = 300; t12.axis.energy.y.interval = 50;
  {
    const q = t12.series.find((x) => x.key === 'network:a').fits.anchors.noise;
    q.scale_factor = 1.5; q.band_quantile = 12.7062;
    for (const key of ['se_a2', 'se_b2', 'se_c2', 'se_a', 'se_b', 'se_c']) if (q.params[key] !== null) q.params[key] *= 1.5;
  }
  const t12opts = { view: 'energy', windows: 'anchors', shower: 'both', reference: 'deposit' };
  {
    const m = rs.energyModel(t12, t12opts);
    const s = m.series.find((x) => x.key === 'network:a');
    const f = s.fits.noise ?? {};
    const built = rs.energyViewOption(t12, t12opts, RE).option;
    // The same top without the scaled errors: S and the quantile move no drawn mark now (no band on this view).
    const top300 = clone(two);
    top300.axis.energy.y.hi = 300; top300.axis.energy.y.interval = 50;
    const fb = rs.energyModel(top300, t12opts).series.find((x) => x.key === 'network:a').fits.noise ?? {};
    fix.outlined = {
      retired: { bandsOutlined: 'bandsOutlined' in m, fit: ['band', 'outlined', 'edges', 'floorCut'].filter((k) => k in f) },
      drawnForm: s.drawnForm, span: f.span, curve: f.curve, ratioRows: f.ratio?.rows ?? null, baseCurve: fb.curve ?? null,
      baseRatioRows: fb.ratio?.rows ?? null,
      k: m.ratio.k, yhi: m.y.hi, colour: s.colour, lineAxis: scale.THEME.lineAxis,
      edges: edgesOf(built), ids: built.series.map((x) => x.id ?? ''), chart: walk(built), notes: notesOf(t12, t12opts),
      hazards: mn.modelsHazards(t12, 'res-scaling', t12opts), hazardsBase: mn.modelsHazards(two, 'res-scaling', t12opts),
    };
  }

  // P1 on the deposit reference's own band about 1: shower B's a/√E ⊕ b ⊕ c/E reference (c held, ν = 2), S = 3. (A
  // pinned reference's band about 1 is 1 ± q·SE(a₀)/a₀ at every E, so once wider than the axis no edge of it is on the plot.)
  const refWide = clone(two);
  {
    const q = refWide.series.find((x) => x.key === 'detector:b').fits.anchors.noise;
    q.scale_factor = 3; q.band_quantile = 12.7062;
    for (const key of ['se_a2', 'se_b2', 'se_c2', 'se_a', 'se_b', 'se_c']) if (q.params[key] !== null) q.params[key] *= 3;
  }
  {
    const mm = rs.energyModel(refWide, t12opts);
    const ref = mm.reference.byShower.b;
    const built = rs.energyViewOption(refWide, t12opts, RE).option;
    const base = rs.energyModel(two, t12opts);
    fix.refOutlined = { retired: ['band', 'outlined', 'edges', 'edgesOffAxis', 'bandCut', 'bandClipped'].filter((k) => k in ref),
      interval: ref.interval, form: ref.form, series: ref.series,
      ids: built.series.map((x) => x.id ?? '').filter((id) => id.includes('|reference|') || id.includes('|band|') || id.includes('|edges|')),
      // The ratio marks against the reference move with nothing but its line, so S = 3 leaves them where they were.
      ratios: mm.series.flatMap((x) => x.points.map((p) => [p.ratio.value, p.ratio.lo, p.ratio.hi])),
      baseRatios: base.series.flatMap((x) => x.points.map((p) => [p.ratio.value, p.ratio.lo, p.ratio.hi])),
      clipped: mm.clipped, baseClipped: base.clipped,
      unityTip: (() => { const u = built.series.find((x) => x.id === 'ratio|unity'); return u?.tooltip?.formatter?.() ?? null; })(),
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
      bTips: walk(built).series.filter((s) => /^(detector|network):b\|(noise|pinned)\|(solid|dashed)\|/.test(s.id ?? '')).map((s) => s.items[0].tip),
      bOpacity: Object.fromEntries(mm.series.filter((s) => s.isB).map((s) => [s.key, s.lineOpacity(false)])),
      bOnMain: mm.series.some((s) => s.isB && s.drawn && s.drawn.solid.length + s.drawn.dashed.length > 0),
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
    fix.refCaret = { carets, muted: scale.THEME.muted, k: mm.ratio.k, ratio: mm.clipped.ratio, clipped: mm.ratio.clipped,
      refIds: built.series.map((x) => x.id ?? '').filter((id) => id.includes('|reference|')),
      refs: Object.values(mm.reference.byShower).map((r) => ({ shower: r.shower, series: r.series, interval: r.interval,
        retired: ['band', 'outlined', 'edges', 'bandCut', 'bandClipped'].filter((key) => key in r) })),
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

/* ---- res-scaling: the windows alone set the range; a misfit is faded (Martin, 2026-11-11) ---- */
{
  const stubState = { isTouched: () => false, get: () => null };
  const packN = (n) => (n ? { title: n.title, hazards: n.hazards, sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
  const RW = { width: 760, height: 420 };
  const RE = { width: 760, height: 600 };
  const two = load('res_scaling_two');
  // A fit whose form does not describe its windows, as the server writes one: ν ≥ 1 and S > 5, its χ² and p with it.
  const misfitted = (payload, picks, S = 8) => {
    const p = clone(payload);
    for (const [key, mode, form] of picks) {
      const f = p.series.find((x) => x.key === key).fits[mode][form];
      f.misfit = true; f.scale_factor = S; f.chi2 = S * S * f.ndf; f.p_value = 1e-12;
    }
    return p;
  };
  // The deposit A's pinned fit (drawn in both views), the network B's quadrature fit (tabled in both views) and its
  // a/√E ⊕ b ⊕ c/E fit (drawn in the E view, Martin's decisions of 2026-11-13).
  const picks = [['detector:a', 'all', 'pinned'], ['network:b', 'all', 'quadrature'], ['network:b', 'all', 'noise']];
  const mis = misfitted(two, picks);
  const lin = { windows: 'all', shower: 'both' };
  const eo = { view: 'energy', windows: 'all', shower: 'both', reference: 'deposit' };
  // One curve per series (Martin's directive of 2026-11-15): the deposit A's a₀/√E is tabled beside its noise curve,
  // so a drawn a₀/√E misfit needs the fallback: the network A without its noise fit (the server's reason served),
  // its a₀/√E drawn from 4 GeV and divided by the deposit A's noise reference on the ratio panel.
  const fb = clone(two);
  { const mf = fb.series.find((x) => x.key === 'network:a').fits.all; mf.noise = null;
    mf.noise_reason = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.'; }
  const fbMis = misfitted(fb, [['network:a', 'all', 'pinned']]);
  const seriesOf = (built, prefix) => walk(built).series.filter((s) => (s.id ?? '').startsWith(prefix))
    .map((s) => ({ id: s.id, opacity: s.items[0]?.el?.opacity ?? null, tip: s.items[0]?.tip ?? null }));
  const m = {};
  for (const [name, payload] of [['base', two], ['mis', mis], ['fb', fb], ['fbMis', fbMis]]) {
    const lm = rs.resolutionModel(payload, lin);
    const ls = lm.series.find((x) => x.key === 'detector:a');
    const linear = rs.resolutionScalingOption(payload, { ...lin, palette: 'viridis', card: 'res-scaling' }, RW);
    const em = rs.energyModel(payload, eo);
    const energy = rs.energyViewOption(payload, eo, RE).option;
    const eFits = (key, form) => {
      const f = em.series.find((x) => x.key === key).fits[form] ?? {};
      return { drawable: f.drawable, provisional: f.provisional, misfit: f.misfit, faded: f.faded, cut: Boolean(f.cut) };
    };
    m[name] = {
      linearFit: { misfit: ls.fits.pinned.misfit, faded: ls.fits.pinned.faded, provisional: ls.fits.pinned.provisional,
        line: rs.lineTip(lm, ls, ls.fits.pinned, payload), colour: ls.colour, wanted: cp.legibleOpacity(ls.colour, 0.55) },
      linearLines: seriesOf(linear, 'detector:a|pinned|line|'), linearBand: seriesOf(linear, 'detector:a|pinned|band'),
      linearAffine: seriesOf(linear, 'detector:a|affine|line|'),
      table: rs.fitTableRows(payload, lin), tableE: rs.fitTableRows(payload, { ...lin, view: 'energy' }),
      eFits: { aPinned: eFits('detector:a', 'pinned'), bNoise: eFits('network:b', 'noise'), aNoise: eFits('detector:a', 'noise'),
        bQuad: eFits('network:b', 'quadrature'), nPinned: eFits('network:a', 'pinned') },
      eNA: [...seriesOf(energy, 'network:a|pinned|solid|'), ...seriesOf(energy, 'network:a|pinned|dashed|')],
      eNARatio: [...seriesOf(energy, 'network:a|ratio|pinned|solid|'), ...seriesOf(energy, 'network:a|ratio|pinned|dashed|')],
      eBands: seriesOf(energy, '').filter((x) => /\|(band|edges)\|/.test(x.id)),
      eLineOpacity: Object.fromEntries(em.series.map((s) => [s.key, [s.lineOpacity(false), s.lineOpacity(true)]])),
      eA: [...seriesOf(energy, 'detector:a|pinned|solid|'), ...seriesOf(energy, 'detector:a|pinned|dashed|')],
      eABand: seriesOf(energy, 'detector:a|pinned|band|'),
      eB: [...seriesOf(energy, 'network:b|noise|solid|'), ...seriesOf(energy, 'network:b|noise|dashed|')],
      eBBand: seriesOf(energy, 'network:b|noise|band|'), eBEdges: seriesOf(energy, 'network:b|noise|edges|'),
      eBQuad: seriesOf(energy, 'network:b|quadrature|'),
      eBRatio: [...seriesOf(energy, 'network:b|ratio|noise|solid|'), ...seriesOf(energy, 'network:b|ratio|noise|dashed|')],
      eBRatioBand: seriesOf(energy, 'network:b|ratio|noise|band|'),
      eARatio: [...seriesOf(energy, 'detector:a|ratio|pinned|solid|'), ...seriesOf(energy, 'detector:a|ratio|pinned|dashed|')],
      eARatioBand: seriesOf(energy, 'detector:a|ratio|pinned|band|'),
      endLabels: em.endLabels, k: em.ratio.k, bandAlpha: scale.THEME.bandAlpha,
      notes: packN(mn.resolutionScalingNotes({ payload, state: stubState, experiment: { display_name: 'Demo' }, ...lin })),
      notesE: packN(mn.resolutionScalingNotes({ payload, state: stubState, experiment: { display_name: 'Demo' }, ...eo })),
      hazards: mn.modelsHazards(payload, 'res-scaling', lin), hazardsE: mn.modelsHazards(payload, 'res-scaling', eo),
    };
  }
  // The ratio panel's k follows the windows alone: the deposit A pinned fit made extreme (a₀ × 4), flagged a misfit or
  // not, leaves k the base's; its ratio leaves the axis and is clipped with a caret, true values and a count.
  // The drawn a₀/√E is the fallback since the single-curve round: the network A's, on the copy without its noise fit.
  const wild = (flag) => {
    const p = flag ? misfitted(fb, [['network:a', 'all', 'pinned']]) : clone(fb);
    const f = p.series.find((x) => x.key === 'network:a').fits.all.pinned;
    f.params.a0 *= 4; f.params.se_a0 *= 4; f.params.se_a0_stat *= 4;
    const mm = rs.energyModel(p, eo);
    const ff = mm.series.find((x) => x.key === 'network:a').fits.pinned;
    const built = rs.energyViewOption(p, eo, RE).option;
    const carets = walk(built).series.filter((x) => x.id === 'network:a|ratio|carets').flatMap((x) => x.items.map((i) => i.tip));
    const notes = packN(mn.resolutionScalingNotes({ payload: p, ...eo }));
    // Since review-ui F5 (19f6ab2) the fallback's ratio takes the entry treatment: it may come into [1/k, k] from
    // beyond it as E rises from 4 GeV, or stay beyond it over the whole axis (`whole`), a caret either way.
    const ratioTips = walk(built).series.filter((x) => /^network:a\|ratio\|(pinned)\|(solid|dashed)\|/.test(x.id ?? ''))
      .flatMap((x) => x.items.map((i) => i.tip)).filter(Boolean);
    return { k: mm.ratio.k, provisional: mm.ratio.provisional, cut: ff.ratio?.cut ?? null, fits: mm.ratio.clipped.fits,
      entry: ff.ratio?.entry ?? null, firstRow: ff.ratio?.rows?.[0] ?? null, curveMin: mm.curveMinGev, xMax: mm.x.max,
      ratioRuns: (ff.ratio?.solid?.length ?? 0) + (ff.ratio?.dashed?.length ?? 0), ratioTips,
      carets: carets.filter((t) => t.includes('leaves the ratio axis')),
      entryCarets: carets.filter((t) => t.includes('the ratio axis (') && !t.includes('leaves the ratio axis')), notes };
  };
  m.ratioK = { base: rs.energyModel(fb, eo).ratio.k, misfit: wild(true), unflagged: wild(false) };
  // A fit line or band above the top: a clone whose tops are the windows' alone (the server's rule since 2026-11-11),
  // so the non-provisional fits leave them, each with a caret, its true values and a count.
  const windowsTop = (payload, energy) => {
    let top = 0;
    for (const s of payload.series) {
      for (const w of s.windows) {
        if (!Number.isFinite(w.value)) continue;
        const robust = energy ? (w.n >= 20 && w.p_lo >= 2 && w.se_delta > 0) : w.eligible;
        if (robust) top = Math.max(top, w.value, w.whisker && w.ci95 ? w.ci95[1] : w.value);
      }
    }
    return top;
  };
  const low = clone(two);
  low.axis.y.hi = Math.ceil(windowsTop(two, false) * 1.05); low.axis.y.interval = low.axis.y.hi / 5;
  low.axis.energy.y.hi = Math.ceil(windowsTop(two, true) * 1.05); low.axis.energy.y.interval = low.axis.energy.y.hi / 5;
  const cutOf = (model, forms) => model.series.flatMap((s) => forms.map((form) => [s, form, s.fits[form]])
    .filter(([, , f]) => f && (f.drawable ?? true)).map(([s, form, f]) => ({
      key: s.key, form, provisional: f.provisional, misfit: f.misfit, cut: f.cut ? { at: f.cut.at, peak: f.cut.peak } : null,
      // The 1/√E view's rows are [x, y, lo, hi] (its band's upper edge the highest mark); the E view's [E, y], its line alone.
      peak: Math.max(...(f.curve ?? s.raw.fits.all[form].curve).map((c) => (c.length > 3 ? c[3] : c[1]))),
      linePeak: Math.max(...(f.curve ?? s.raw.fits.all[form].curve).map((c) => c[1])),
      rowWidth: [...new Set((f.curve ?? s.raw.fits.all[form].curve).map((c) => c.length))],
      entry: f.entry ? { lineAt: f.entry.lineAt, above: f.entry.above, retired: ['bandAt', 'lowAt', 'bandAbove'].filter((k) => k in f.entry) } : null,
    })));
  const lowLinear = rs.resolutionModel(low, lin);
  // One curve per series (single-curve round): every noise curve enters from the top and none leaves it again on this
  // clone, so the curve that leaves is the a₀/√E fallback of the deposit B without its noise fit (from 4 GeV, above
  // the windows' top there).
  const lowFb = clone(low);
  { const mf = lowFb.series.find((x) => x.key === 'detector:b').fits.all; mf.noise = null;
    mf.noise_reason = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.'; }
  const lowEnergy = rs.energyModel(lowFb, eo);
  const caretTips = (built, ratio = false) => walk(built).series.filter((s) => (s.id ?? '').endsWith('|carets') && ((s.id ?? '').includes('|ratio|') === ratio))
    .flatMap((s) => s.items.map((i) => i.tip));
  m.lowTop = {
    yhi: low.axis.y.hi, ehi: low.axis.energy.y.hi,
    linear: { fits: cutOf(lowLinear, rs.DRAWN_FORMS), clipped: lowLinear.clipped,
      tips: caretTips(rs.resolutionScalingOption(low, lin, RW)) },
    energy: { fits: cutOf(lowEnergy, rs.ENERGY_FORMS), clipped: lowEnergy.clipped,
      tips: caretTips(rs.energyViewOption(lowFb, eo, RE).option),
      recording: { fits: cutOf(rs.energyModel(low, eo), rs.ENERGY_FORMS), clipped: rs.energyModel(low, eo).clipped,
        tips: caretTips(rs.energyViewOption(low, eo, RE).option) } },
    notes: packN(mn.resolutionScalingNotes({ payload: low, ...lin })), notesE: packN(mn.resolutionScalingNotes({ payload: lowFb, ...eo })),
  };
  // The drawer's range sentences on every fixture, both views and modes.
  m.fixtures = {};
  for (const name of %(res)s) {
    const payload = load(name);
    for (const windows of ['anchors', 'all']) {
      m.fixtures[`${name}:${windows}`] = {
        provisional: payload.axis.y.provisional, provisionalE: payload.axis.energy.y.provisional,
        linear: packN(mn.resolutionScalingNotes({ payload, windows })),
        energy: packN(mn.resolutionScalingNotes({ payload, windows, view: 'energy' })),
        misfits: rs.resolutionModel(payload, { windows }).series.flatMap((s) => rs.DRAWN_FORMS.filter((f) => s.fits[f]?.misfit)).length,
        misfitsE: rs.energyModel(payload, { windows }).series.flatMap((s) => rs.ENERGY_FORMS.filter((f) => s.fits[f]?.drawable && s.fits[f].misfit)).length,
      };
    }
  }
  // A ratio against a misfit reference is not robust (as against a provisional one): each shower's deposit without an
  // a/√E ⊕ b ⊕ c/E fit (the server's noise_reason with it), so the reference falls back to its pinned fit, a misfit.
  // Beside it the same clone with the pinned fit not a misfit, and the deposits' own noise fits made the misfit.
  const NO_NOISE = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.';
  const fallback = (flag) => {
    const p = clone(two);
    for (const key of ['detector:a', 'detector:b']) {
      const mf = p.series.find((x) => x.key === key).fits.all;
      mf.noise = null; mf.noise_reason = NO_NOISE;
    }
    return flag ? misfitted(p, [['detector:a', 'all', 'pinned'], ['detector:b', 'all', 'pinned']]) : p;
  };
  const refCase = (p) => {
    const mm = rs.energyModel(p, eo);
    const built = rs.energyViewOption(p, eo, RE).option;
    const w = walk(built);
    const tipsOf = (pred) => w.series.filter((x) => pred(x.id ?? '')).flatMap((x) => x.items.map((i) => i.tip)).filter(Boolean);
    return {
      refs: Object.values(mm.reference.byShower).map((r) => ({ shower: r.shower, form: r.form, misfit: r.misfit, provisional: r.provisional,
        label: r.label })),
      robust: mm.series.flatMap((s) => s.points.filter((pt) => pt.ratio.drawn).map((pt) => pt.ratio.robust)),
      windowsRobust: mm.series.flatMap((s) => s.points.filter((pt) => pt.ratio.drawn).map((pt) => pt.robust)),
      k: mm.ratio.k, provisional: mm.ratio.provisional, axisName: built.yAxis[1].name,
      pointTips: tipsOf((id) => /\|ratio\|markers$/.test(id)), referenceTips: tipsOf((id) => id.includes('|ratio|reference|')),
      unityTip: tipsOf((id) => id === 'ratio|unity'),
      notes: packN(mn.resolutionScalingNotes({ payload: p, ...eo })), hazards: mn.modelsHazards(p, 'res-scaling', eo),
    };
  };
  m.misfitRef = { misfit: refCase(fallback(true)), calm: refCase(fallback(false)),
    noise: refCase(misfitted(two, [['detector:a', 'all', 'noise'], ['detector:b', 'all', 'noise']])), noReason: NO_NOISE };
  // The 1/√E view's outline rule: the network B affine fit of the anchors mode with ν = 1, its errors scaled by S = 1.5,
  // so its band takes t₀.₉₇₅,₁ = 12.71 (its curve rows widened by the same factor, as the server would write them).
  const wide = clone(two);
  {
    const f = wide.series.find((x) => x.key === 'network:b').fits.anchors.affine;
    const factor = (12.7062 * 1.5) / f.band_quantile;
    f.scale_factor = 1.5; f.band_quantile = 12.7062;
    f.params.se_a *= 1.5; f.params.se_b *= 1.5;
    f.curve = f.curve.map(([cx, cy, lo, up]) => [cx, cy, cy - factor * (cy - lo), cy + factor * (up - cy)]);
  }
  const anc = { windows: 'anchors', shower: 'both' };
  {
    const lm = rs.resolutionModel(wide, anc);
    const ls = lm.series.find((x) => x.key === 'network:b');
    const f = ls.fits.affine;
    const built = rs.resolutionScalingOption(wide, { ...anc, palette: 'viridis', card: 'res-scaling' }, RW);
    const edges = built.series.filter((x) => (x.id ?? '').startsWith('network:b|affine|edges|')).map((x) => {
      const el = x.renderItem({ dataIndex: 0, coordSys }, api);
      return { id: x.id, name: x.name, stroke: el.style.stroke, width: el.style.lineWidth, opacity: el.style.opacity,
        dash: el.style.lineDash ?? null, points: el.shape.points, tip: x.tooltip.formatter({ dataIndex: 0 }) };
    });
    m.outline = {
      outlined: f.outlined, span: f.span, xSpan: f.xSpan, yhi: lm.y.hi, colour: ls.colour, label: ls.label,
      edgeOpacity: cp.legibleOpacity(ls.colour, 0.5), lineAxis: scale.THEME.lineAxis,
      bands: built.series.filter((x) => (x.id ?? '').startsWith('network:b|affine|band')).length, edges,
      lineTip: rs.lineTip(lm, ls, f, wide),
      notes: packN(mn.resolutionScalingNotes({ payload: wide, ...anc })),
      hazards: mn.modelsHazards(wide, 'res-scaling', anc), hazardsBase: mn.modelsHazards(two, 'res-scaling', anc),
      baseOutlined: rs.resolutionModel(two, anc).series.find((x) => x.key === 'network:b').fits.affine.outlined,
      outlinedCount: lm.series.reduce((a, x) => a + rs.DRAWN_FORMS.filter((form) => x.fits[form]?.outlined).length, 0),
    };
  }
  m.xSpans = [rs.xSpanOf([5, 20]), rs.xSpanOf([4, 5]), rs.xSpanOf(null), rs.xSpanOf([0, 5])];
  m.misfitText = rs.misfitText({ chi2: 64 * 3, ndf: 3, scale_factor: 8 });
  m.isMisfit = [rs.isMisfit({ misfit: true }), rs.isMisfit({ misfit: false }), rs.isMisfit({ scale_factor: 9, ndf: 3 }), rs.isMisfit(null)];
  out.resMisfit = m;
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
    noteFont: (built.option.graphic ?? []).map((g) => g.style?.fontSize), palette: scale.THEME.qualitativePalette,
    legendItems: [].concat(built.option.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => ({ name: d?.name ?? d, colour: d?.itemStyle?.color ?? null }))) };
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
    """One line and one band per drawn fit: the band a wash, or, where it spans half the axis or more over its fitted
    windows (Martin, 2026-11-11), its two edges and no wash."""
    payload = _load(name)
    for key in RES_KEYS:
        windows, shower = key.split(":")
        chart = out["res"][name]["charts"][key]
        model = {s["key"]: s for s in out["res"][name]["models"][key]["series"]}
        assert not [s for s in chart["series"] if "quadrature" in (s["id"] or "")]
        # a/√E ⊕ b ⊕ c/E is tabled on this view (its windows reach below its 4 GeV edge), never drawn.
        assert not [s for s in chart["series"] if "|noise|" in (s["id"] or "")]
        for s in _res_shown(payload, shower):
            mf = s["fits"][windows]
            for form in ("affine", "pinned"):
                lines = [x for x in chart["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|line|")]
                bands = _ids(chart, f"|{form}|band", s["key"])
                edges = [x for x in chart["series"] if (x["id"] or "").startswith(f"{s['key']}|{form}|edges|")]
                if mf[form] is None:
                    assert not lines and not bands and not edges
                    continue
                outlined = model[s["key"]]["fits"][form]["outlined"]
                assert len(lines) >= 1, (key, s["key"], form)
                if outlined:
                    assert not bands and edges, (key, s["key"], form)
                    assert all("so it is drawn as its edges, not as a wash" in _plain(e["items"][0]["tip"]) for e in edges)
                else:
                    assert len(bands) == 1 and not edges, (key, s["key"], form)
                for b in bands + edges:
                    tip = b["items"][0]["tip"]
                    assert "95% confidence band" in tip and "not the spread of the events" in tip
                    assert not b["silent"]
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
    """{series key: {form: cells}}, the cells from the Fit column on (Fit, a, b, c, χ²/ν, S, Status)."""
    return {r["key"]: {f["form"]: f["cells"] for f in r["fits"]} for r in table["rows"]}


RES_TABLE_COLUMNS = ["Series", "Fit", "a ± SE [%·√GeV]", "b ± SE [%]", "c ± SE [%·GeV]", "χ²/ν (p)", "S", "Windows fitted", "Status"]


def test_res_fit_table_rows(out):
    """One row group per series, one row per fit: a, b, c, χ²/ν (p), S and the status of each, the windows spanning
    the group. a/√E ⊕ b ⊕ c/E is the fourth row (Martin's decisions of 2026-11-13), and c belongs to it alone."""
    two = out["res"]["res_scaling_two"]["tables"]
    for key in RES_KEYS:
        table = two[key]
        assert table["columns"] == RES_TABLE_COLUMNS
        shower = key.split(":")[1]
        assert [r["key"] for r in table["rows"]] == [s["key"] for s in _res_shown(_load("res_scaling_two"), shower)]
        for r in table["rows"]:
            assert [f["form"] for f in r["fits"]] == ["affine", "pinned", "quadrature", "noise"]
            assert all(len(f["cells"]) == 7 for f in r["fits"]) and r["windows"]
            # c is the noise term's alone: every other row leaves its cell empty.
            assert [f["cells"][3] for f in r["fits"][:3]] == ["—", "—", "—"]
    payload = _load("res_scaling_two")
    fits = {s["key"]: s["fits"]["anchors"] for s in payload["series"]}
    rows = _fit_rows(two["anchors:both"])
    windows = {r["key"]: r["windows"] for r in two["anchors:both"]["rows"]}
    for key, by_form in rows.items():
        for form, cells in by_form.items():
            fit = fits[key][form]
            # The S column: S where it scaled the errors, 1 where they stand, — without a χ² test.
            if fit["ndf"] == 0:
                assert cells[5] == "—" and "ν = 0" in cells[4]
            elif fit["scale_factor"] > 1:
                assert cells[5] != "1" and cells[5] != "—"
            else:
                assert cells[5] == "1"
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
    assert "b undefined" in xrows["xgb:a"]["quadrature"][2] and "ν = 0" in xrows["xgb:a"]["affine"][4]
    assert all("provisional" in xrows["xgb:a"][form][6] for form in ("affine", "pinned", "quadrature", "noise"))
    assert "dropped" in xwin["xgb:a"]
    single = _fit_rows(out["res"]["res_scaling_single_hits"]["tables"]["anchors:both"])["detector:a"]
    assert all("provisional" in cells[6] for cells in single.values())
    assert "S = √(χ²/ν)" in xgb["caption"] and "Student's t" in xgb["caption"]


def _sig_cell(v: float) -> str:
    return _sf(v).replace("-", "−")


#: The unit of a term's square, as the fit table and the noise tooltip print it (review m4).
SQUARE_UNITS = {"a": "%²·GeV", "b": "%²", "c": "%²·GeV²"}


def _as_square(p: dict, t: str) -> bool:
    """Review m4: a free term whose SE exceeds its value is printed as its square with the square's SE."""
    return p.get("se_" + t) is not None and p.get(t) is not None and p["se_" + t] > p[t]


def _term_cell(p: dict, t: str, sep: str = "\u00a0") -> str:
    """A free term's table cell: a ± se, or its square with its SE where se > a (review m4), never a symmetric error
    larger than a term that cannot be negative."""
    if _as_square(p, t):
        return f"{t}²{sep}={sep}{_sig_cell(p[t + '2'])}{sep}±{sep}{_sig_cell(p['se_' + t + '2'])}{sep}{SQUARE_UNITS[t]}"
    return f"{_sig_cell(p[t])}{sep}±{sep}{_sig_cell(p['se_' + t])}"


@pytest.mark.parametrize("name", RES)
def test_res_the_noise_row_gives_each_term_or_zero_held(out, name):
    """The a/√E ⊕ b ⊕ c/E row of both views (Martin's decisions of 2026-11-13): a, b and c with their SEs, a term the
    constraint holds at 0 written "0 (held)"; χ²/ν and S from the block; its status the fit's own provisional flag;
    on the 1/√E view tabled only, on the E view drawn; the windows cell names the low anchor in the 3-anchor mode."""
    payload = _load(name)
    gates = payload["gates"]
    for windows in ("anchors", "all"):
        linear = _fit_rows(out["res"][name]["tables"][f"{windows}:both"])
        energy = _fit_rows(out["resE"]["fixtures"][name]["tables"][windows])
        cells_lin = {r["key"]: r["windows"] for r in out["res"][name]["tables"][f"{windows}:both"]["rows"]}
        for s in payload["series"]:
            nf = s["fits"][windows]["noise"]
            lin, en = linear[s["key"]]["noise"], energy[s["key"]]["noise"]
            assert lin[0] == "a/√E ⊕ b ⊕ c/E, tabled only: fitted to windows from 1 GeV, below this view's edge"
            # Every cell but the Fit cell is the same on both views.
            assert lin[1:] == en[1:], (name, windows, s["key"])
            if nf is None:
                assert en[0].startswith("a/√E ⊕ b ⊕ c/E — not drawn: ") and en[6].startswith("no fit: ")
                continue
            assert en[0] == "a/√E ⊕ b ⊕ c/E — drawn"
            p = nf["params"]
            for i, t in enumerate("abc", start=1):
                if t in p["held"]:
                    assert lin[i] == "0\u00a0(held)", (name, windows, s["key"], t)
                else:
                    assert lin[i] == _term_cell(p, t), (name, windows, s["key"], t)
                    # m4: never a symmetric error larger than the term.
                    assert ("²" in lin[i]) == _as_square(p, t)
            # The quadrature row's defined terms follow the same rule (m4); an undefined one is its square already.
            q = s["fits"][windows]["quadrature"]
            if q is not None:
                qp, qcells = q["params"], energy[s["key"]]["quadrature"]
                for i, t in enumerate("ab", start=1):
                    if qp[f"{t}_defined"] and qp.get(t) is not None:
                        assert qcells[i] == _term_cell(qp, t), (name, windows, s["key"], "quadrature", t)
            assert ("ν = 0" in lin[4]) == (nf["ndf"] == 0)
            if nf["ndf"] > 0:
                assert lin[4].startswith(f"{_sig_cell(nf['chi2'])}/{nf['ndf']} (p")
                assert lin[5] == ("1" if nf["scale_factor"] <= 1 else _sig_cell(nf["scale_factor"]))
            assert ("provisional" in lin[6]) == bool(nf["provisional"]), (name, windows, s["key"])
            assert ("form does not describe its windows" in lin[6]) == bool(nf["misfit"])
            if not nf["provisional"] and not nf["misfit"] and nf["converged"]:
                assert lin[6] == f"N\u00a0≥\u00a0{gates['fit_n']} throughout"
            # The windows cell: the noise fit's own list where it differs from the mode's, the low anchor named.
            same = sorted(nf["points"]) == sorted(s["fits"][windows]["points"]) and nf["low_anchor"] is None
            assert ("a/√E ⊕ b ⊕ c/E: " in cells_lin[s["key"]]) == (not same), (name, windows, s["key"])
            if nf["low_anchor"] is not None:
                low = next(w["label"] for w in s["windows"] if w["bin"] == nf["low_anchor"])
                assert f"{low} (the low anchor)" in cells_lin[s["key"]], (name, windows, s["key"])
            else:
                assert "(the low anchor)" not in cells_lin[s["key"]]
    # Both captions state the constraint, the window rule, "0 (held)" and that c is the noise term's alone.
    for table in (out["res"][name]["tables"]["anchors:both"], out["resE"]["fixtures"][name]["tables"]["anchors"],
                  out["res"][name]["tables"]["all:both"], out["resE"]["fixtures"][name]["tables"]["all"]):
        cap = table["caption"]
        assert "a/√E ⊕ b ⊕ c/E is fitted with a², b² and c² held non-negative" in cap
        assert 'written "0 (held)"' in cap and "its band is conditional on it" not in cap
        # The single-curve round (Martin's directive of 2026-11-15) retired FX1's envelope: neither view's caption
        # speaks of a noise band, and the E view's says it draws one curve per series with no band.
        assert "envelope" not in cap and "all three terms free" not in cap
        if table in (out["resE"]["fixtures"][name]["tables"]["anchors"], out["resE"]["fixtures"][name]["tables"]["all"]):
            assert ("This view draws one curve per series with no band: a/√E ⊕ b ⊕ c/E from 0 GeV, or, where a series has "
                    "none, the origin-pinned a₀/√E ⊕ 0 from 4 GeV, solid over the windows it was fitted to and dashed "
                    "beyond; the other fits are tabled only, the affine a/√E + b drawn in the 1/√E view.") in cap
            assert cap.count("band") == 1, "the no-band clause is the E caption's only band"
        # m4, said once.
        sq = ("Where a term's SE exceeds its value, a/√E ⊕ b ⊕ c/E and the quadrature form print its square with the "
              "square's SE (b² = 0.04 ± 8.1 %²)")
        assert cap.count(sq) == 1
        assert "exact" not in cap
        assert "c, the noise term c/E, belongs to that form alone." in cap
        assert ("the anchors and the lowest fittable window from 1 GeV, the low anchor" in cap) == (table["mode"] == "anchors")
        assert ("every fittable window from 1 GeV" in cap) == (table["mode"] == "all")
    lin_cap = out["res"][name]["tables"]["all:both"]["caption"]
    e_cap = out["resE"]["fixtures"][name]["tables"]["all"]["caption"]
    assert "a/√E ⊕ b ⊕ c/E, whose windows reach below this view's 4 GeV edge" in lin_cap
    assert "a/√E ⊕ b ⊕ c/E from 0 GeV" in e_cap and "the other fits are tabled only" in e_cap
    # One curve per series (D1): the E table's Fit cells name the one drawn and the other three as table only, and
    # never two drawn rows for one series.
    model = out["resE"]["fixtures"][name]["models"]
    for windows in ("anchors", "all"):
        energy = _fit_rows(out["resE"]["fixtures"][name]["tables"][windows])
        drawn_form = {s["key"]: s["drawnForm"] for s in model[f"{windows}:deposit"]["series"]}
        for key, rows in energy.items():
            drawn = [form for form, cells in rows.items() if cells[0].endswith(" — drawn") or " — drawn: " in cells[0]]
            assert len(drawn) <= 1, (name, windows, key, drawn)
            assert drawn == ([drawn_form[key]] if drawn_form[key] else []), (name, windows, key)
            if drawn_form[key] == "noise":
                assert rows["pinned"][0] == "Origin-pinned a₀/√E ⊕ 0 — table only on this view"
            elif drawn_form[key] == "pinned":
                assert rows["pinned"][0] == "Origin-pinned a₀/√E ⊕ 0 — drawn: no a/√E ⊕ b ⊕ c/E fit"


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
    # One tbody per series: its name heads the group and, with its windows, spans the four fit rows (the fourth
    # a/√E ⊕ b ⊕ c/E, Martin's decisions of 2026-11-13, with its c column).
    assert panel["tag"] == "table" and panel["kinds"] == ["caption", "thead"] + ["tbody"] * len(shown)
    assert panel["head"] == RES_TABLE_COLUMNS
    assert panel["headCls"] == ["text", "text", "num", "num", "num", "num", "num", "text", "text"]
    for label, body in zip(shown, panel["bodies"]):
        assert len(body) == 4 and [len(tr) for tr in body] == [9, 7, 7, 7]
        series, fit = body[0][0], body[0][1]
        assert (series["tag"], series["scope"], series["rowspan"], series["text"]) == ("th", "rowgroup", "4", label)
        assert (fit["tag"], fit["scope"]) == ("th", "row") and fit["text"].startswith("Affine")
        assert body[0][7]["rowspan"] == "4" and body[0][7]["cls"] == "text"
        assert [tr[0]["text"].split()[0] for tr in body[1:]] == ["Origin-pinned", "Quadrature", "a/√E"]
        assert [c["cls"] for c in body[1]] == ["text", "num", "num", "num", "num", "num", "text"]
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
    assert e["forms"] == ["noise", "pinned"], "a/√E ⊕ b ⊕ c/E replaces a/√E ⊕ b on the E view (Martin, 2026-11-13)"
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
        if not key.startswith(f"{name}:") or key.endswith((":quadrature", ":noise")):
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


def _noise_cov(face: dict, s_factor: float):
    """cov_stat of the constrained params: the unscaled SEs (se/S once S > 1) and ρ, zero at a held term."""
    import numpy as np

    se = [0.0 if face[k] is None else face[k] / s_factor / 1e4 for k in ("se_a2", "se_b2", "se_c2")]
    rho = {(0, 1): face["rho"]["a2b2"], (0, 2): face["rho"]["a2c2"], (1, 2): face["rho"]["b2c2"]}
    cov = np.diag([v * v for v in se])
    for (i, j), r in rho.items():
        if r is not None:
            cov[i, j] = cov[j, i] = r * se[i] * se[j]
    return cov


def _noise_fit(block: dict):
    """The server's noise Fit, rebuilt from a wire block: θ = (A, B, C) as fractions, cov_stat from the unscaled SEs
    and ρ, zero at a held term. The wire carries no all-free face since the single-curve round (Martin's directive
    of 2026-11-15), and the Fit none."""
    from calosrv.stats import resolution_fit as rfit

    p = block["params"]
    s_factor = block["scale_factor"] if block["scale_factor"] > 1 else 1.0
    return rfit.Fit("noise", block["n_points"], (p["a2"] / 1e4, p["b2"] / 1e4, p["c2"] / 1e4), _noise_cov(p, s_factor),
                    block["chi2"], block["ndf"], block["p_value"], block["scale_factor"], block["iterations"],
                    block["converged"])


def _noise_line(block: dict, energy: float) -> float:
    """ŷ in % at one energy, the server's Fit.predict on the rebuilt Fit (x = 1/√E)."""
    import numpy as np

    return 100 * float(_noise_fit(block).predict(np.array([1 / math.sqrt(energy)]))[0])


#: The twelve recorded resolution payloads.
RES_ALL = sorted(p.stem for p in FIXTURES.glob("res_scaling_*.json"))


def test_res_e_the_noise_line_equals_the_servers_fit_predict_and_carries_no_band(out):
    """a/√E ⊕ b ⊕ c/E on the E view, from the block's a2, b2, c2 alone, is the server's line: fitCurveE equals
    Fit.predict on the Fit rebuilt from the wire, to 10⁻¹², at every energy where it is defined, on every noise block
    of the twelve recordings (formerly pinned against rfit.band's envelope, retired with every band of this view by
    Martin's directive of 2026-11-15).

    No band comes out of the noise form: fitCurveE gives [E, y] rows, and evalFitAt (module-private, reached through
    a copy of the module) returns {y} alone, even on a block that still carries an old recording's band_quantile and
    all-free face and SEs a thousandfold; the server's rfit.band refuses the form. The pinned and affine evaluators
    keep their half-widths, which the 1/√E view draws."""
    import numpy as np
    from calosrv.stats import resolution_fit as rfit

    lines = out["resE"]["noiseLines"]["lines"]
    seen_recordings = set()
    checked = 0
    for name in RES_ALL:
        payload = _load(name)
        for s in payload["series"]:
            for mode in ("anchors", "all"):
                block = s["fits"][mode]["noise"]
                key = f"{name}:{mode}:{s['key']}"
                if not block:
                    assert key not in lines
                    continue
                assert "free" not in block["params"] and "band_quantile" not in block, key
                got = lines[key]
                fit = _noise_fit(block)
                assert fit.held == tuple(block["params"]["held"])
                flat = block["params"]["a2"] == 0 and block["params"]["c2"] == 0
                # E = 0 only for a flat curve (A = C = 0): the line is defined from 0 GeV there and nowhere else.
                assert [r[0] for r in got["js"]] == [e for e in got["energies"] if e > 0 or flat], key
                for e, y in got["js"]:
                    want = 100 * float(fit.predict(np.array([0.0 if e == 0 else 1 / math.sqrt(e)]))[0]) if e > 0 else \
                        100 * math.sqrt(fit.theta[1])
                    assert y == pytest.approx(want, rel=1e-12, abs=1e-12), (key, e, y, want)
                    checked += 1
                # No band: [E, y] rows; evalFitAt's {y} alone, the loud copy's too, and its line unchanged.
                assert {len(r) for r in got["js"]} == {2} and got["loud"] == got["js"], key
                assert got["evalKeys"] == ["y"] and got["evalLoudKeys"] == ["y"], key
                assert [v for v in got["evalY"] if v is not None] == [r[1] for r in got["js"]], key
                with pytest.raises(ValueError, match="No band is drawn for the noise form"):
                    rfit.band(fit, np.array([0.5]))
                seen_recordings.add(name)
    assert checked > 0
    # Every recording that serves a noise fit was checked (the robust single-shower ones serve none).
    served = {n for n in RES_ALL if any(s["fits"][m]["noise"] for s in _load(n)["series"] for m in ("anchors", "all"))}
    assert seen_recordings == served and len(served) >= 10
    assert out["resE"]["noiseLines"]["pinnedKeys"] == ["cutLo", "hi", "lo", "y"]
    assert out["resE"]["noiseLines"]["affineKeys"] == ["cutLo", "hi", "lo", "y"]


@pytest.mark.parametrize("name", RES)
def test_res_e_the_noise_evaluator_equals_the_servers_line(out, name):
    """The evaluators at fixed energies (the four sample recordings, as before the single-curve round): fitCurveE's
    [E, y] equals Fit.predict on the rebuilt Fit, and the block is drawable (`noiseDrawable`)."""
    payload = _load(name)
    checked = 0
    for s in payload["series"]:
        for mode in ("anchors", "all"):
            block = s["fits"][mode]["noise"]
            if not block:
                continue
            got = out["resE"]["evaluators"][f"{name}:{mode}:{s['key']}:noise"]
            assert [r[0] for r in got["js"]] == got["energies"]
            for e, y in got["js"]:
                assert y == pytest.approx(_noise_line(block, e), rel=1e-12), (s["key"], mode, e)
            assert got["drawable"] is True
            checked += 1
    assert checked > 0


#: Review m7 (brief-fix): where a noise curve enters below x.max·10⁻³, its caret and the drawer's entry line add this.
NOISE_AXIS_LINE = "less than 0.1% of the axis from E = 0: the curve runs up along the axis line there."

#: The roles of a window of 1–4 GeV on the E view (Martin's decisions of 2026-11-13).
LOW_ANCHOR_ROLE = ("the low anchor of the a/√E ⊕ b ⊕ c/E fit: the lowest fittable window from 1 GeV, since anchors from "
                   "5 GeV cannot fix a 1/E term; a₀/√E does not use it")
NOISE_ONLY_ROLE = "fitted by a/√E ⊕ b ⊕ c/E only: a₀/√E uses windows from 4 GeV"
BELOW_NOISE_ROLE = "below 1 GeV: no fit uses it; drawn as a point only"


@pytest.mark.parametrize("name", RES)
def test_res_e_windows_sit_at_e_equals_one_over_x_squared(out, name):
    """Every window at E = 1/x². The all mode draws every window with a value; the 3-anchor mode its fitted ones, the
    low anchor of a/√E ⊕ b ⊕ c/E included (the lead's decision of 2026-11-13). A window below 1 GeV is a point no fit
    uses; one of 1–4 GeV is fitted by a/√E ⊕ b ⊕ c/E only, is its low anchor, or says why neither."""
    payload = _load(name)
    ax = _e_axis(name)
    assert ax["noise_min_gev"] == 1.0
    for key in RES_E_KEYS:
        windows = key.split(":")[0]
        model = out["resE"]["fixtures"][name]["models"][key]
        assert model["noiseMinGev"] == 1.0
        for s, m in zip(payload["series"], model["series"]):
            nf = s["fits"][windows]["noise"]
            noise_bins = set(nf["points"]) if nf else set()
            for p in m["points"]:
                assert p["E"] == pytest.approx(1 / (p["x"] * p["x"]), rel=1e-12)
                assert 0 <= p["E"] <= ax["x"]["max"]
            eligible = [w for w in s["windows"] if w["value"] is not None and w["x"] and w["n"] >= 2
                        and 1 / w["x"] ** 2 <= ax["x"]["max"]]
            if windows == "anchors":
                eligible = [w for w in eligible if w["bin"] in set(s["fits"]["anchors"]["points"]) | noise_bins]
            assert [p["bin"] for p in m["points"]] == [w["bin"] for w in eligible], (key, s["key"])
            if windows == "anchors" and nf and nf["low_anchor"] is not None:
                assert nf["low_anchor"] in [p["bin"] for p in m["points"]], "the low anchor's window is drawn"
            for p in m["points"]:
                assert p["below4"] == (p["pLo"] < ax["curve_min_gev"])
                assert p["belowNoise"] == (p["pLo"] < ax["noise_min_gev"])
                assert p["noiseFitted"] == (p["bin"] in noise_bins)
                assert p["lowAnchor"] == (nf is not None and p["bin"] == nf["low_anchor"])
                if p["belowNoise"]:
                    assert p["roles"][0] == BELOW_NOISE_ROLE and not p["fitted"] and not p["noiseFitted"], (key, s["key"], p["bin"])
                elif p["below4"]:
                    assert not p["fitted"], (key, s["key"], p["bin"])
                    if p["lowAnchor"]:
                        assert p["roles"][0] == LOW_ANCHOR_ROLE and windows == "anchors"
                    elif p["noiseFitted"]:
                        assert p["roles"][0] == NOISE_ONLY_ROLE
                    else:
                        assert p["roles"][0].startswith("below 4 GeV, the floor of a₀/√E; ")
                assert not [r for r in p["roles"] if r.startswith("below 4 GeV: no fit uses it")], "the retired role"
    # Every fixture has windows below 4 GeV; the all mode draws them on this axis.
    assert any(p["below4"] for s in out["resE"]["fixtures"][name]["models"]["all:deposit"]["series"] for p in s["points"])


def test_res_e_the_low_anchor_is_drawn_named_and_ratioed_on_the_e_view_only(out):
    """3-anchor mode (the lead's decision of 2026-11-13): the low anchor's window is drawn, at the anchor marker; its role
    names it the low anchor and says a₀/√E does not use it; it gets a ratio mark against the deposit's noise fit; the
    1/√E view does not draw it."""
    seen = 0
    for name in RES:
        payload = _load(name)
        for s in payload["series"]:
            nf = s["fits"]["anchors"]["noise"]
            if not nf or nf["low_anchor"] is None:
                continue
            low = nf["low_anchor"]
            if low in s["fits"]["anchors"]["points"]:
                continue
            e_model = next(x for x in out["resE"]["fixtures"][name]["models"]["anchors:deposit"]["series"] if x["key"] == s["key"])
            (p,) = [x for x in e_model["points"] if x["bin"] == low]
            assert p["lowAnchor"] and p["anchor"] and p["noiseFitted"] and not p["fitted"]
            assert p["roles"][0] == LOW_ANCHOR_ROLE
            assert p["ratio"]["drawn"] and p["ratio"]["reason"] is None and p["ratio"]["value"] > 0, (name, s["key"])
            # The main chart draws it at the anchor marker: one marker more than the mode's own anchors.
            chart = out["resE"]["fixtures"][name]["charts"]["anchors:deposit"]["chart"]
            markers = [i for x in chart["series"] if x["id"] == f"{s['key']}|markers" for i in x["items"]]
            assert any(i["value"][0] == pytest.approx(p["E"]) for i in markers)
            low_tips = [_plain(i["tip"]) for i in markers if i["value"][0] == pytest.approx(p["E"])]
            assert low_tips and all(LOW_ANCHOR_ROLE in tip for tip in low_tips)
            # On the ratio panel: its marker, or its caret where the ratio lies beyond the axis.
            ratio = [i for x in chart["series"] if x["id"] in (f"{s['key']}|ratio|markers", f"{s['key']}|ratio|carets") for i in x["items"]]
            assert any(i["value"][0] == pytest.approx(p["E"]) for i in ratio), (name, s["key"])
            # The 1/√E view: the anchors alone.
            lin = next(x for x in out["res"][name]["models"]["anchors:both"]["series"] if x["key"] == s["key"])
            assert low not in [x["bin"] for x in lin["points"]]
            assert sorted(x["bin"] for x in lin["points"]) == sorted(
                b for b in s["fits"]["anchors"]["points"] if b in _res_drawn_bins(s, "anchors"))
            seen += 1
    assert seen >= 4


@pytest.mark.parametrize("name", RES)
def test_res_e_solid_over_the_fitted_span_dashed_beyond(out, name):
    """a₀/√E from 4 GeV (now the fallback only); a/√E ⊕ b ⊕ c/E from 0 GeV (Martin's decisions of 2026-11-13), from
    where its line comes down through the top (its band's lower edge before the single-curve round of 2026-11-15),
    solid over its own span_gev and dashed below it and above it to x.max. One curve per series, rows [E, y]."""
    ax = _e_axis(name)
    x_max, floor, top = ax["x"]["max"], ax["curve_min_gev"], ax["y"]["hi"]
    payload = {s["key"]: s for s in _load(name)["series"]}
    seen = {"pinned": 0, "noise": 0}
    for key in ("anchors:deposit", "all:deposit", "anchors:pi", "all:pi"):
        windows = key.split(":")[0]
        model = out["resE"]["fixtures"][name]["models"][key]
        drawn = list(_e_drawn_fits(model))
        # One curve per series (Martin's directive of 2026-11-15): never two drawable forms, the drawn one the model's.
        assert len({s["key"] for s, _, _ in drawn}) == len(drawn), key
        for s, form, f in drawn:
            assert form in ("pinned", "noise"), "a/√E ⊕ b is never drawn on this view"
            assert s["drawnForm"] == form and s["drawnIsFit"] is True, (key, s["key"])
            assert f["rowWidths"] == [2] and f["retired"] == [], (key, s["key"], f["rowWidths"], f["retired"])
            mf = payload[s["key"]]["fits"][windows]
            span = mf["span_gev"] if form == "pinned" else mf["noise"]["span_gev"]
            es = [c[0] for c in f["curve"]]
            assert f["span"] == span and max(es) == x_max, "the curve runs to the axis end"
            if form == "pinned":
                assert f["domain"] == [floor, x_max] and min(es) == floor, "no a₀/√E point below 4 GeV"
            else:
                p = mf["noise"]["params"]
                flat = p["a2"] == 0 and p["c2"] == 0
                e = f["entry"] or {}
                # From where the line comes down through the top (the XGBoost curves enter at 0.0035 GeV, below the
                # grid's 0.01 GeV start); a flat curve from 0.
                start = 0 if flat else (e["lineAt"] if e.get("lineAt") is not None else 0.01)
                assert f["domain"] == [pytest.approx(start), x_max] and min(es) == pytest.approx(start), (key, s["key"])
                # Below a₀/√E's 4 GeV wherever its line is inside the plot there (it enters from the top).
                assert min(es) < floor or e.get("lineAt", 0) >= floor, (key, s["key"])
            for run in f["solid"]:
                assert all(span[0] - 1e-9 <= pt[0] <= span[1] + 1e-9 for pt in run)
            for run in f["solid"] + f["dashed"]:
                assert all(pt[0] >= f["domain"][0] - 1e-9 and -1e-9 <= pt[1] <= top + 1e-9 for pt in run)
            by_e = {c[0]: c[1] for c in f["curve"]}
            ends = [pt for run in f["dashed"] for pt in (run[0], run[-1])]
            starts = [run[0] for run in f["solid"]] + [run[-1] for run in f["solid"]]
            for edge in span:
                if span[0] > f["domain"][0] or edge == span[1]:
                    if edge in by_e and 0 <= by_e[edge] <= top:
                        # The solid and the dashed part share the edge row exactly.
                        assert [edge, by_e[edge]] in ends and [edge, by_e[edge]] in starts, (s["key"], form, edge)
            if 0 <= by_e[x_max] <= top:
                assert [x_max, by_e[x_max]] in ends, "the dashed part runs to x.max"
            if form == "noise":
                # Dashed below its span too: from the entry (or 0) up to the span's low edge.
                assert any(run[0][0] < span[0] for run in f["dashed"]), (key, s["key"])
            seen[form] += 1
    # Every series of these recordings has a noise fit, so a₀/√E is table only here; the fallback is drawn on the
    # copy whose deposit A has none (`fallback`), from 4 GeV, solid over the mode's span and dashed beyond.
    assert seen["noise"] > 0 and seen["pinned"] == 0
    if name == "res_scaling_two":
        for windows in ("anchors", "all"):
            fb = next(x for x in out["resE"]["noise"]["fallback"][windows]["model"]["series"] if x["key"] == "detector:a")
            f = fb["fits"]["pinned"]
            assert fb["drawnForm"] == "pinned" and f["drawable"] and f["fallback"] is True
            assert f["domain"] == [floor, x_max] and min(c[0] for c in f["curve"]) == floor and f["rowWidths"] == [2]
            span = payload["detector:a"]["fits"][windows]["span_gev"]
            assert f["span"] == span and f["solid"]
            for run in f["solid"]:
                assert all(span[0] - 1e-9 <= pt[0] <= span[1] + 1e-9 for pt in run)
            for run in f["dashed"]:
                assert all(pt[0] <= span[0] + 1e-9 or pt[0] >= span[1] - 1e-9 for pt in run)


@pytest.mark.parametrize("name", RES)
def test_res_e_the_noise_curve_enters_at_the_top_where_its_quadratic_says(out, name):
    """Where a/√E ⊕ b ⊕ c/E comes down into the plot: its line at the root of C·u² + A·u + (B − y_hi²) = 0, u = 1/E;
    one caret at the line's entry carrying brief section 8's sentence; and the first drawn point of the line on the
    top. clipped.entries counts them, apart from the fits that leave the top. The line alone (Martin's directive of
    2026-11-15): the band edges' own entries (bandAt, lowAt, bandAbove) are retired, and a flat curve has no entry."""
    ax = _e_axis(name)
    top = ax["y"]["hi"]
    payload = {s["key"]: s for s in _load(name)["series"]}
    seen = 0
    for key in ("anchors:deposit", "all:deposit"):
        windows = key.split(":")[0]
        model = out["resE"]["fixtures"][name]["models"][key]
        chart = out["resE"]["fixtures"][name]["charts"][key]["chart"]
        entries = 0
        for s, form, f in _e_drawn_fits(model):
            if form != "noise":
                continue
            block = payload[s["key"]]["fits"][windows]["noise"]
            p = block["params"]
            A, B, C, H = p["a2"], p["b2"], p["c2"], top * top
            e = f["entry"]
            if A == 0 and C == 0:
                # A flat curve never comes down, and with no band nothing of it can lie above the top beside it.
                assert e is None, (key, s["key"])
                continue
            assert set(e) == {"at", "lineAt", "above", "term", "atAxis"}, (key, s["key"], sorted(e))
            assert B < H, "every recorded curve comes inside the plot"
            u = 2 * (H - B) / (A + math.sqrt(A * A + 4 * C * (H - B)))
            assert C * u * u + A * u + (B - H) == pytest.approx(0, abs=1e-9 * H)
            assert e["lineAt"] == pytest.approx(1 / u, rel=1e-9) and e["at"] == e["lineAt"], (key, s["key"])
            assert e["term"] == ("c" if C > 0 else "a") and e["above"] is False
            # The server's line agrees: on the top at the entry.
            assert _noise_line(block, e["lineAt"]) == pytest.approx(top, rel=1e-6)
            # No carets for a band: the series' carets are its windows', this entry and its exit, if any.
            carets = [i for x in chart["series"] if x["id"] == f"{s['key']}|carets" for i in x["items"]]
            assert not [i for i in carets if "band" in _plain(i["tip"])], (key, s["key"])
            # The line's first drawn point sits on the top, at its entry.
            first = min((run[0] for run in f["solid"] + f["dashed"]), key=lambda pt: pt[0])
            assert first[1] == pytest.approx(top, rel=1e-6) and first[0] == pytest.approx(e["lineAt"], rel=1e-6)
            # One caret at the entry, with the sentence; the term that rises as E → 0 named.
            term = "noise term c/E" if C > 0 else "stochastic term a/√E"
            sentence = (f"It comes down into the plot at E = {_sf(e['lineAt'])} GeV: a/√E ⊕ b ⊕ c/E rises without bound as "
                        f"E → 0, through its {term}.")
            # Review m7: an entry below 0.1% of the axis from E = 0 runs up the axis line, and the caret says so.
            assert e["atAxis"] is (e["at"] < ax["x"]["max"] * 1e-3), (key, s["key"])
            if e["atAxis"]:
                sentence += " " + NOISE_AXIS_LINE
            at_entry = [i for i in carets if i["value"][0] == pytest.approx(e["lineAt"]) and i["value"][1] == pytest.approx(top)]
            assert len(at_entry) == 1 and _plain(at_entry[0]["tip"]).endswith(sentence), (key, s["key"])
            entries += 1
            seen += 1
        assert model["clipped"]["entries"] == entries, key
        cut = sum(1 for _, _, f in _e_drawn_fits(model) if f["cut"])
        assert model["clipped"]["fits"] == cut, "an entry is not a fit leaving the top"
    assert seen > 0


def test_res_e_a_noise_line_above_the_whole_axis_says_so_and_an_se_moves_no_mark(out):
    """A curve above the top over the whole axis (a top of 30%, below every b) gets one caret at x.max with its own
    sentence, and nothing of it is drawn above the top. Before the single-curve round a flat curve inside whose
    band's upper edge lay above the top at every E (the network A's, SE(b²) raised) had a caret of its own; with no
    band on the view (Martin's directive of 2026-11-15) raising an SE moves no drawn mark and adds no caret: the
    same series, the same line, the same carets as the recording."""
    above = out["resE"]["noise"]["above"]
    for s in above["model"]["series"]:
        e = s["fits"]["noise"]["entry"]
        assert e["above"] is True and e["at"] == 80 and e["lineAt"] is None, s["key"]
        assert not s["fits"]["noise"]["solid"] and not s["fits"]["noise"]["dashed"], "nothing of it on the panel"
        (caret,) = [i for c in above["carets"] if c["id"] == f"{s['key']}|carets" for i in c["items"]
                    if "a/√E ⊕ b ⊕ c/E fit lies above the top" in i["tip"]]
        assert caret["value"][:2] == [80, 30]
        assert re.search(r"The a/√E ⊕ b ⊕ c/E fit lies above the top of the axis \(0 to 30%\) over the whole axis: at E = 80 GeV "
                         r"it reads [\d.]+%\.$", _plain(caret["tip"])), caret["tip"]
    assert above["model"]["clipped"]["entries"] == 4
    loud = out["resE"]["noise"]["bandAbove"]
    base_model = out["resE"]["fixtures"]["res_scaling_two"]["models"]["anchors:deposit"]
    base_chart = out["resE"]["fixtures"]["res_scaling_two"]["charts"]["anchors:deposit"]["chart"]
    s = next(x for x in loud["model"]["series"] if x["key"] == "network:a")
    b = next(x for x in base_model["series"] if x["key"] == "network:a")
    assert s["fits"]["noise"]["entry"] is None and s["fits"]["noise"]["solid"], "flat, and inside the plot"
    for part in ("curve", "solid", "dashed"):
        assert s["fits"]["noise"][part] == b["fits"]["noise"][part], part
    assert loud["ids"] == [x["id"] for x in base_chart["series"]]
    carets = [i for c in loud["carets"] for i in c["items"]]
    base_carets = [i for x in base_chart["series"] if (x["id"] or "").endswith("|carets") for i in x["items"]]
    assert [c["value"] for c in carets] == [c["value"] for c in base_carets]
    assert not [c for c in carets if "band" in _plain(c["tip"])]
    assert loud["model"]["clipped"] == base_model["clipped"]
    _no_hyphen_numbers(above["strings"] + loud["strings"])


def test_res_e_the_ratio_reference_falls_back_to_a0_from_four_gev_with_the_noise_reason(out):
    """A shower whose deposit has no a/√E ⊕ b ⊕ c/E fit (its noise_reason served): its ratio divides by the deposit's
    a₀/√E fit, from 4 GeV, its why giving the reason; its windows below 4 GeV are counted off the ratio panel apart from
    the other shower's below 1 GeV. The table says why the row is not drawn, the drawer says it once per series."""
    case = out["resE"]["noise"]["fallback"]
    reason = out["resE"]["noise"]["noReason"]
    clause = reason.removeprefix("No a/√E ⊕ b ⊕ c/E fit: ").removesuffix(".")
    for windows in ("anchors", "all"):
        got = case[windows]
        model = got["model"]
        a, b = model["reference"]["byShower"]["a"], model["reference"]["byShower"]["b"]
        assert (a["form"], a["floorGev"], a["floorBy"], a["noiseReason"]) == ("pinned", 4, "E", reason)
        assert a["label"] == "shower A's deposit a₀/√E fit" and a["why"] == f"its a₀/√E fit, since it has no a/√E ⊕ b ⊕ c/E fit ({clause})"
        assert (b["form"], b["floorGev"], b["floorBy"]) == ("noise", 1, "p_lo")
        s_a = next(s for s in model["series"] if s["key"] == "detector:a")
        assert s_a["fits"]["noise"]["drawable"] is False and s_a["fits"]["noise"]["reason"] == clause
        assert s_a["noise"]["reason"] == reason and not [i for i in got["ids"] if i.startswith("detector:a|noise|")]
        n_a = n_b = 0
        for s in model["series"]:
            for pt in s["points"]:
                r = pt["ratio"]
                if s["shower"] == "a" and pt["E"] < 4:
                    assert not r["drawn"] and r["reason"] == "below 4 GeV, where no fit is drawn, so shower A's deposit a₀/√E fit has no value there"
                    n_a += 1
                elif s["shower"] == "b" and pt["pLo"] < 1:
                    assert not r["drawn"]
                    n_b += 1
                else:
                    assert r["drawn"], (windows, s["key"], pt["bin"])
        groups = {(g["shower"], g["form"]): g for g in model["ratio"]["below"]}
        assert model["ratio"]["belowNotDrawn"] == n_a + n_b
        if n_a:
            assert groups[("a", "pinned")]["floorGev"] == 4 and groups[("a", "pinned")]["n"] == n_a
        # Shower B keeps its windows from 1 GeV: 3–4 GeV, below a₀/√E's floor, still takes a ratio mark.
        assert any(pt["ratio"]["drawn"] and pt["pLo"] < 4 for s in model["series"] if s["shower"] == "b" for pt in s["points"])
        # The table: the noise row of the deposit A is not drawn, with the reason, and its status says so.
        row = next(r for r in got["table"]["rows"] if r["key"] == "detector:a")
        cells = {f["form"]: f["cells"] for f in row["fits"]}["noise"]
        assert cells[0] == f"a/√E ⊕ b ⊕ c/E — not drawn: {clause}" and cells[6] == f"no fit: {clause}"
        assert cells[1:4] == ["—", "—", "—"]
        lrow = next(r for r in got["linearTable"]["rows"] if r["key"] == "detector:a")
        assert {f["form"]: f["cells"] for f in lrow["fits"]}["noise"][6] == f"no fit: {clause}"
        # The drawer: the series without a noise fit, once, with the served reason and the a₀/√E it draws instead
        # (one curve per series, Martin's directive of 2026-11-15); the ratio line names a₀/√E.
        dis = _lines(got["notes"], out, "disclosures")
        drawn = _lines(got["notes"], out, "drawn")
        assert sum(x == (f"Shower A · Calibrated deposit c·E_dep — linear-sum benchmark: {reason} Its origin-pinned a₀/√E ⊕ 0 "
                         "is drawn instead, from 4 GeV, as the thinner line.") for x in drawn) == 1
        assert not [x for x in dis if x.startswith("Shower A · Calibrated deposit") and reason in x]
        # The model draws its a₀/√E as the fallback, saying why, and its tooltip says so too.
        assert s_a["drawnForm"] == "pinned" and s_a["fits"]["pinned"]["fallback"] is True
        assert s_a["fits"]["pinned"]["noiseReason"] == clause
        tips = [t for i, ts in got["fallbackTips"].items() for t in ts]
        assert tips and all(f"This series has no a/√E ⊕ b ⊕ c/E fit ({clause}), so its origin-pinned a₀/√E is drawn "
                            "instead, from 4 GeV." in _plain(t) for t in tips)
        (line_a,) = [x for x in drawn if x.startswith("Shower A: the ratio divides")]
        assert f"its deposit's a₀/√E fit" in line_a and f"since it has no a/√E ⊕ b ⊕ c/E fit ({clause})" in line_a
        assert line_a.endswith("so a window gets a ratio mark from 4 GeV.")
        (line_b,) = [x for x in drawn if x.startswith("Shower B: the ratio divides")]
        assert "its deposit's a/√E ⊕ b ⊕ c/E fit" in line_b and "a window gets a ratio mark from 1 GeV" in line_b
        if n_a:
            assert sum(x.startswith(f"{_n(n_a, 'window')} below 4 GeV (shower A) ") and "not drawn on the ratio panel" in x for x in dis) == 1
        _no_hyphen_numbers(got["strings"] + dis + drawn)


#: The single-curve round's tooltip sentence on every fitted curve of the E view (the lead's wording of 2026-11-15,
#: 29c3ae8): no band, and where the fit's uncertainty is instead.
ENERGY_NO_BAND_TEXT = "No band is drawn on this view: the standard errors above and the fit table carry the fit's uncertainty."

#: The correlation rule (the lead's decision of 2026-11-13): §11's sentence where the largest |ρ| ≥ 0.7 and every ρ < 0;
#: "strongly correlated" without the trade-off where a strong ρ is positive; below 0.7 the largest |ρ|; nothing without a pair.
TRADE_OFF = ": the terms trade off against each other over the fitted windows, so the curve is better determined than its terms."
STRONG = ": the fitted squares are strongly correlated over the fitted windows, so the curve is better determined than its terms."


def _rho_line(rho: dict) -> str | None:
    pairs = [(k, n) for k, n in (("a2b2", "ρ(a², b²)"), ("a2c2", "ρ(a², c²)"), ("b2c2", "ρ(b², c²)")) if rho.get(k) is not None]
    if not pairs:
        return None
    listed = ", ".join(f"{n} = {_sf(rho[k])}" for k, n in pairs)
    largest = max(abs(rho[k]) for k, _ in pairs)
    if largest < 0.7:
        # As the list rounds, except where rounding would read as the threshold it lies below (lead's fix of
        # N-jstests' F3, 2026-11-13): 0.69999 is truncated to 0.699.
        shown = _sf(largest)
        if float(shown) >= 0.7:
            shown = _sf(math.floor(largest * 1000) / 1000)
        return f"{listed}: no pair of the fitted squares is strongly correlated here (largest |ρ| = {shown}, below 0.7)."
    return listed + (TRADE_OFF if all(rho[k] < 0 for k, _ in pairs) else STRONG)


def test_res_noise_words_are_the_briefs(out):
    """Section 8 and 11's sentences, verbatim, as the panel exports them for the drawer; the held phrases singular and
    plural; the correlation rule at and around its threshold."""
    w = out["resE"]["noise"]["words"]
    assert w["name"] == "a/√E ⊕ b ⊕ c/E" and w["strong"] == 0.7
    assert w["constraint"] == ("Fitted as (σ/E)² = A/E + B + C/E² by weighted least squares with A = a², B = b² and C = c² "
                               "held non-negative, so every term is real.")
    assert w["floor"] == ("It uses windows from 1 GeV: below that a 1 GeV window reaches momenta near zero, so its average of 1/E² "
                          "is far from what its plotted energy implies, and no single abscissa can carry the noise term c/E.")
    assert w["caveat"] == ("c/E is the calorimeter's conventional noise term. Here it takes up whatever grows like 1/E at low "
                           "momentum (for a network, its pull toward mid-range; under Median |rel. err.|, the response's bias as "
                           "well), so c is a fitted coefficient, not a measured noise level.")
    assert w["below"] == [
        "1 window below 1 GeV is not drawn on the ratio panel: no window below 1 GeV enters the deposit's a/√E ⊕ b ⊕ c/E fit.",
        "2 windows below 1 GeV are not drawn on the ratio panel: no window below 1 GeV enters the deposit's a/√E ⊕ b ⊕ c/E fit."]
    assert w["entry"] == [
        "It comes down into the plot at E = 1.25 GeV: a/√E ⊕ b ⊕ c/E rises without bound as E → 0, through its noise term c/E.",
        "It comes down into the plot at E = 0.0035 GeV: a/√E ⊕ b ⊕ c/E rises without bound as E → 0, through its stochastic term a/√E."]
    assert w["lowAnchor"] == [
        "In the 3-anchor mode it runs through the three anchors and the lowest fittable window from 1 GeV (3–4 GeV), since "
        "anchors from 5 GeV cannot fix a 1/E term.",
        "In the 3-anchor mode it runs through the two anchors and the lowest fittable window from 1 GeV (1–2 GeV), since "
        "anchors from 5 GeV cannot fix a 1/E term."]
    held = out["resE"]["noise"]["held"]
    # The held phrases stay; the conditional-band sentence beside each left with the band (single-curve round,
    # Martin's directive of 2026-11-15), and so did the FX1 band texts and the band tooltip's export.
    assert held[0] == [""]
    assert held[1] == ["b = 0, held there by the constraint b² ≥ 0"]
    assert held[2] == ["a = 0 and c = 0, held there by the constraints a² ≥ 0 and c² ≥ 0"]
    assert held[3] == ["a = 0, b = 0 and c = 0, held there by the constraints a² ≥ 0, b² ≥ 0 and c² ≥ 0"]
    assert out["resE"]["noise"]["retiredExports"] == []
    assert out["resE"]["noise"]["noBandText"] == ENERGY_NO_BAND_TEXT
    rhos = [{}, {"a2b2": None, "a2c2": None, "b2c2": None}, {"a2b2": -0.9, "a2c2": -0.8, "b2c2": 0.1},
            {"a2b2": -0.95, "a2c2": -0.71, "b2c2": -0.3}, {"a2b2": -0.837128}, {"b2c2": -0.292308},
            {"a2b2": 0.85, "a2c2": -0.2}, {"a2b2": -0.69999}, {"a2b2": -0.7}]
    got = out["resE"]["noise"]["correlation"]
    assert got[:2] == [None, None], "no free pair, no line"
    for rho, line in zip(rhos[2:], got[2:]):
        assert line == _rho_line(rho), rho
    assert got[3].endswith(TRADE_OFF) and got[2].endswith(STRONG) and "trade off" not in got[6]
    assert "strongly" not in got[7].replace("no pair of the fitted squares is strongly", "") and got[8].endswith(TRADE_OFF)


@pytest.mark.parametrize("name", RES)
def test_res_e_the_noise_curve_tooltip_names_terms_condition_and_correlation(out, name):
    """brief section 4.3, as the fix round left it: the equation; each term with its SE and unit, its square with the
    square's SE where the SE exceeds the term (review m4), or the held phrase; χ²/ν and S; the windows fitted, the low
    anchor named in the 3-anchor mode; the correlation line by the lead's rule; and, in place of FX1's band sentence
    (the envelope, retired with the band by Martin's directive of 2026-11-15), ENERGY_NO_BAND_TEXT, whatever is held.
    The floor sentence and the naming caveat are the drawer's alone (review m6)."""
    payload = {s["key"]: s for s in _load(name)["series"]}
    units = {"a": "%·√GeV", "b": "%", "c": "%·GeV"}
    seen = 0
    for key in ("anchors:deposit", "all:deposit"):
        windows = key.split(":")[0]
        chart = out["resE"]["fixtures"][name]["charts"][key]["chart"]
        for s in out["resE"]["fixtures"][name]["models"][key]["series"]:
            nf = payload[s["key"]]["fits"][windows]["noise"]
            tips = [x["items"][0]["tip"] for x in chart["series"] if (x["id"] or "").startswith(f"{s['key']}|noise|solid|")]
            if not nf:
                assert not tips
                continue
            p = nf["params"]
            for tip in tips:
                lines = tip.split("<br/>")
                assert lines[1] == "<b>σ/E = a/√E ⊕ b ⊕ c/E</b>"
                terms = []
                for t in "abc":
                    lead = "the noise term c/E: " if t == "c" else ""
                    if t in p["held"]:
                        terms.append(f"{lead}{t} = 0, held there by the constraint {t}² ≥ 0")
                    elif _as_square(p, t):
                        terms.append(f"{lead}{t}² = {_sf(p[t + '2'])} ± {_sf(p['se_' + t + '2'])} {SQUARE_UNITS[t]}")
                    else:
                        terms.append(f"{lead}{t} = {_sf(p[t])} ± {_sf(p['se_' + t])} {units[t]}")
                assert html.unescape(lines[2]) == "; ".join(terms), (key, s["key"])
                plain = _plain(tip)
                chi = (f"χ²/ν = {_sf(nf['chi2'])}/{nf['ndf']}" if nf["ndf"] > 0 else "ν = 0")
                assert chi in plain and (f"S = {_sf(max(nf['scale_factor'], 1))}" in plain or nf["ndf"] == 0)
                span = f"{nf['span_gev'][0]:g}–{nf['span_gev'][1]:g} GeV"
                assert f"Windows fitted ({nf['n_points']}, {span}): " in plain
                if windows == "anchors" and nf["low_anchor"] is not None:
                    low = next(w["label"] for w in payload[s["key"]]["windows"] if w["bin"] == nf["low_anchor"])
                    assert f"{low} (the low anchor)" in plain
                    n_anchors = len(nf["points"]) - 1
                    count = {2: "the two anchors", 3: "the three anchors"}[n_anchors]
                    assert f"In the 3-anchor mode it runs through {count} and the lowest fittable window from 1 GeV ({low})" in plain
                else:
                    assert "(the low anchor)" not in plain and "In the 3-anchor mode it runs through" not in plain
                # No band on this view (Martin's directive of 2026-11-15): FX1's "The band is …" line (the envelope, or
                # the conditional band) is gone whatever is held, and one muted line says where the uncertainty is.
                assert not [x for x in lines if _plain(x).startswith("The band is ")], (key, s["key"])
                assert [x for x in lines if _plain(x) == ENERGY_NO_BAND_TEXT], (key, s["key"])
                assert "envelope" not in plain and "conditional on" not in plain
                assert "exact" not in plain and "no delta method" not in plain
                rho = _rho_line(p["rho"])
                rho_lines = [x for x in lines if "ρ(" in x]
                assert ([_plain(x) for x in rho_lines] == [rho]) if rho else not rho_lines, (key, s["key"])
                if rho:
                    assert rho_lines[0].startswith("<span style=")
                # m6: the floor sentence and the naming caveat left the curve's tooltip; the drawer states both, once.
                assert _plain(out["resE"]["noise"]["words"]["floor"]) not in plain
                assert _plain(out["resE"]["noise"]["words"]["caveat"]) not in plain
                assert ("Provisional:" in plain) == bool(nf["provisional"])
                seen += 1
    assert seen > 0


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
        # No band about 1 or round a fit's ratio (single-curve round): the reference-band count left `ratio.clipped`.
        assert set(clipped) == {"markers", "whiskers", "fits", "literature"} and model["retired"] == {"bandsOutlined": False, "ratioBands": False}
        assert model["clipped"]["ratio"] == clipped["markers"] + clipped["whiskers"] + clipped["fits"] + clipped["literature"]
        carets = [i for s in out["resE"]["fixtures"][name]["charts"][key]["chart"]["series"] if (s["id"] or "").endswith("|ratio|carets")
                  for i in s["items"]]
        assert len(carets) >= over
        # A window's caret, a fit leaving the axis, or an a/√E ⊕ b ⊕ c/E ratio coming into it as E rises from 0.
        assert all("clipped at the ratio axis" in c["tip"] or "leaves the ratio axis" in c["tip"]
                   or "comes into the ratio axis" in c["tip"] or "over the whole axis" in c["tip"] for c in carets)
        assert not [c for c in carets if "band" in _plain(c["tip"])], "no band caret (single-curve round)"
        entries = sum(1 for s in model["series"] for f in s["fits"].values() if f["drawable"] and (f.get("ratio") or {}).get("entry"))
        assert entries == len([c for c in carets if "comes into the ratio axis" in c["tip"]
                               or ("over the whole axis" in c["tip"] and "The ratio of the a/√E ⊕ b ⊕ c/E fit" in c["tip"])])
    helpers = out["resE"]["helpers"]
    assert helpers["ranges"] == [{"k": 2, "provisional": False, "capped": 0}, {"k": 2, "provisional": True, "capped": 0},
                                 {"k": 2, "provisional": True, "capped": 0}, {"k": 50, "provisional": False, "capped": 0},
                                 {"k": 1.1, "provisional": False, "capped": 0}, {"k": 4, "provisional": False, "capped": 0}]
    for ticks in helpers["ticks"]:
        assert all(any(abs(t * u - 1) < 1e-9 for u in ticks) for t in ticks) and 1 in ticks
    assert helpers["grid"] == [4, 4.25, 4.5, 4.75, 5, 5.1, 5.25, 5.5, 5.75, 6]
    assert helpers["gridEnds"] == [4, 80, 305, True, True]
    # Nit 2: the quadrature form is tabled only, so it has no curve and no drawable test.
    assert helpers["quadratureCurve"] == [[], []]
    assert helpers["exportsQuadratureDrawable"] is False


@pytest.mark.parametrize("name", RES)
def test_res_e_the_deposit_reference_is_each_showers_own(out, name):
    payload = _load(name)
    for windows in ("anchors", "all"):
        model = out["resE"]["fixtures"][name]["models"][f"{windows}:deposit"]
        chart = out["resE"]["fixtures"][name]["charts"][f"{windows}:deposit"]
        # The reference is held exact, with no band about 1 (Martin's directive of 2026-11-15): interval null.
        assert model["reference"]["key"] == "deposit" and model["reference"]["interval"] is None and model["reference"]["flag"] is None
        floor_of = {}
        for shower, ref in model["reference"]["byShower"].items():
            det = next(s for s in payload["series"] if s["source"] == "detector" and s["shower"] == shower)
            # The deposit's a/√E ⊕ b ⊕ c/E fit (Martin's decisions of 2026-11-13), else its a₀/√E fit from 4 GeV.
            noise, pinned = det["fits"][windows]["noise"], det["fits"][windows]["pinned"]
            assert ref["series"] == det["key"] and ref["form"] == ("noise" if noise else "pinned")
            assert ref["interval"] is None and ref["retired"] == [], (windows, shower, ref["retired"])
            fit = noise or pinned
            p = fit["params"]
            value = (lambda e: (p["a2"] / e + p["b2"] + p["c2"] / e ** 2) ** 0.5) if noise else (lambda e: p["a0"] / e ** 0.5)
            if noise:
                assert (ref["floorGev"], ref["floorBy"], ref["noiseReason"]) == (1.0, "p_lo", None)
                owner = f"shower {shower.upper()}'s deposit" if model["nShowers"] > 1 else "the deposit"
                assert ref["label"] == f"{owner} a/√E ⊕ b ⊕ c/E fit" and ref["held"] == p["held"]
                assert ref["why"] == ("its a/√E ⊕ b ⊕ c/E fit, drawn from 0 GeV; its ratio marks start at 1 GeV, "
                                      "the lowest window edge the fit uses")
            floor_of[shower] = (lambda pt: pt["pLo"] < 1.0) if noise else (lambda pt: pt["E"] < model["curveMinGev"])
            below = 0
            for s in (x for x in model["series"] if x["shower"] == shower):
                for pt in s["points"]:
                    r = pt["ratio"]
                    if floor_of[shower](pt):
                        assert not r["drawn"], "no ratio below the reference's floor"
                        if noise:
                            assert r["reason"] == f"below 1 GeV: no window below 1 GeV enters {ref['label']}"
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
            assert below == sum(1 for s in model["series"] if s["shower"] == shower for pt in s["points"] if floor_of[shower](pt))
        assert model["ratio"]["belowNotDrawn"] == sum(1 for s in model["series"] for pt in s["points"] if floor_of[s["shower"]](pt))
        # The windows left off, by shower and reference form, with the floor in force.
        groups = {(g["shower"], g["form"]): (g["floorGev"], g["n"]) for g in model["ratio"]["below"]}
        assert sum(n for _, n in groups.values()) == model["ratio"]["belowNotDrawn"]
        for (shower, form), (floor, n) in groups.items():
            assert form == model["reference"]["byShower"][shower]["form"] and floor == (1.0 if form == "noise" else model["curveMinGev"])
        # No band about 1 for the deposit reference (Martin's directive of 2026-11-15): no wash, no edges, no muted
        # caret; the 1.0 rule's tooltip says the reference is held exact. (This replaces P1's outline rule and P13's
        # caret on the reference band, retired with it.)
        assert not [s for s in chart["chart"]["series"] if "|reference|" in (s["id"] or "")]
        assert "bands" not in model["ratio"]["clipped"]
        (unity,) = [s for s in chart["chart"]["series"] if s["id"] == "ratio|unity"]
        assert not [i for i in unity["items"] if i["tip"] and "band" in _plain(i["tip"])]
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
            assert all(r["form"] == "literature" and r["literature"] == ref and r["retired"] == [] and r["interval"] is None
                       for r in model["reference"]["byShower"].values())
            for s in model["series"]:
                for pt in s["points"]:
                    assert pt["ratio"]["drawn"], "a literature curve is defined over the whole axis"
                    assert pt["ratio"]["ref"] == pytest.approx(value(pt["E"]), rel=1e-12)
                for f in s["fits"].values():
                    if f["drawable"]:
                        assert f["isReference"] is False and f["ratio"] is not None
            assert model["ratio"]["belowNotDrawn"] == 0
            # Only the curve in force on the main panel (Martin, 2026-11-11), dotted, in its identity colour, named in
            # the legend; the other catalogue curve is not drawn at all.
            colour = out["resE"]["litColours"]["table"]["set2"][ref]
            assert [(l["key"], l["colour"]) for l in model["literature"]] == [(ref, colour)]
            lits = [s for s in chart["chart"]["series"] if (s["id"] or "").startswith("literature|")
                    and not s["id"].endswith(("|caret", "|endlabels"))]
            assert [s["id"] for s in lits] == [f"literature|{ref}"]
            assert {s["id"].split("|")[1] for s in chart["chart"]["series"] if (s["id"] or "").startswith("literature|")} == {ref}
            lit = model["literature"][0]
            s = lits[0]
            assert s["name"] == lit["legend"] and lit["legend"] in chart["chart"]["legend"] and s["colour"] == colour
            swatch = [x for x in chart["legendItems"] if x["name"] == lit["legend"]]
            assert len(swatch) == 1 and swatch[0]["colour"] == colour and swatch[0]["icon"].startswith("path://"), swatch
            group = s["items"][0]["el"]
            lines = [ch for ch in group["children"] if ch["type"] == "polyline"]
            assert lines and all(ch["dash"] == [1.5, 3] and ch["stroke"] == colour for ch in lines)
            # P2: the particle is its label, in the end column (an end-label series), never inside the plot.
            assert lit["label"] == {"pi": "π±", "e": "e±"}[lit["key"]]
            assert not [ch for ch in group["children"] if ch["type"] == "text"]
            tip = s["items"][0]["tip"]
            assert cat[ref]["equation"] in tip and "no interval reported" in tip and "not this detector" in tip
            # Drawn alone it is the ratio's divisor; the e± / π± toggles may draw the other beside it.
            assert "The ratio panel divides by this curve." in tip and "drawn beside it" not in tip
            assert all(v == pytest.approx((c["a"] ** 2 / e + c["b"] ** 2) ** 0.5, rel=1e-12) for e, v in lit["curve"])
            end = lit["curve"][-1][1]
            labelled = [x for x in model["endLabels"]["main"] if x["literature"]]
            assert len(labelled) == (1 if 0 <= end <= model["y"]["hi"] else 0)
            assert all(x["key"] == f"literature|{ref}" and x["text"] == lit["label"] and x["colour"] == colour for x in labelled)
            assert lit["curve"][0][0] == 0.25 and lit["curve"][-1][0] == _e_axis(name)["x"]["max"]
            assert not [s for s in chart["chart"]["series"] if "|ratio|reference|band|" in (s["id"] or "")], "no band for a literature reference"
            assert ("÷" in chart["yAxes"][1]["name"] or "ratio to" in chart["yAxes"][1]["name"])
        # The deposit reference draws no literature curve: no series, no end label, no legend entry.
        deposit = out["resE"]["fixtures"][name]["models"][f"{windows}:deposit"]
        dchart = out["resE"]["fixtures"][name]["charts"][f"{windows}:deposit"]
        assert not deposit["literature"] and not [x for x in deposit["endLabels"]["main"] if x["literature"]]
        assert not [s for s in dchart["chart"]["series"] if (s["id"] or "").startswith("literature|")]
        assert not [x for x in dchart["legendItems"] if " lit. — " in str(x["name"])]


#: palette.js LITERATURE_COLOURS, keyed by the series palette that names the card (tests/test_js_literature_colours.py
#: measures them): Set2 on the dark screen, Dark2 on white.
LIT_COLOURS = {"set2": {"pi": "#b15928", "e": "#984ea3"}, "dark2": {"pi": "#a65628", "e": "#6a3d9a"}}


def test_res_e_the_literature_curve_in_force_takes_its_identity_colour_on_each_card(out):
    """Martin (2026-11-11): only the chosen curve, in a colour of its own. π± and e± differ on every card; the dark
    screen picks Set2's pair and the light screen Dark2's (print, which is white too, in test_res_e_print_tokens_build);
    the line, the end label and the legend swatch take it; a card or a curve nobody measured is refused."""
    lc = out["resE"]["litColours"]
    assert lc["table"] == LIT_COLOURS and lc["hues"] == {"pi": "brown", "e": "purple"}
    for theme, palette in (("dark", "set2"), ("light", "dark2")):
        got = lc[theme]
        for ref in ("pi", "e"):
            assert got[ref]["palette"] == palette, (theme, ref)
            assert got[ref]["literature"] == [{"key": ref, "colour": LIT_COLOURS[palette][ref]}], (theme, ref)
            assert [(x["key"], x["colour"]) for x in got[ref]["endLabels"]] == [(f"literature|{ref}", LIT_COLOURS[palette][ref])]
        assert got["pi"]["literature"][0]["colour"] != got["e"]["literature"][0]["colour"], theme
    for ref, chart in (("pi", out["resE"]["lightChart"]), ("e", out["resE"]["lightChartE"])):
        ids = [s["id"] for s in chart["chart"]["series"] if (s["id"] or "").startswith("literature|")]
        assert ids and {i.split("|")[1] for i in ids} == {ref}, ids
        line = next(s for s in chart["chart"]["series"] if s["id"] == f"literature|{ref}")
        strokes = {ch["stroke"] for ch in line["items"][0]["el"]["children"] if ch["type"] == "polyline"}
        assert strokes == {LIT_COLOURS["dark2"][ref]} and line["colour"] == LIT_COLOURS["dark2"][ref]
        assert [x["colour"] for x in chart["legendItems"] if " lit. — " in str(x["name"])] == [LIT_COLOURS["dark2"][ref]]
        _no_hyphen_numbers(chart["chart"]["strings"])
    assert len(lc["refusals"]) == 3 and all(r.startswith("threw: ") for r in lc["refusals"]), lc["refusals"]


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
                assert form in ("noise", "pinned"), "a/√E ⊕ b is never drawn on this view"
                if form == "pinned":
                    assert "σ/E = (" in tip and "⊕ 0 (b ≡ 0, through the origin)" in tip
                else:
                    # The equation alone, bold; its terms on the next line.
                    lines = tip.split("<br/>")
                    # Each term as itself or, where its SE exceeds it, as its square (review m4).
                    assert lines[1] == "<b>σ/E = a/√E ⊕ b ⊕ c/E</b>" and lines[2].startswith(("a ", "a² "))
                    assert "; b " in lines[2] or "; b² " in lines[2]
                    assert "; the noise term c/E: c " in lines[2] or "; the noise term c/E: c² " in lines[2]
                assert ("Extrapolated: beyond the windows this fit used" in tip) == (x in dashed)
                # The band clause left with the band (single-curve round): the dashed part is the form assumed to hold.
                assert ("where the fitted form is assumed to hold and no window supports it" in tip) == (x in dashed)
            # No band round the curve (Martin's directive of 2026-11-15): no wash at any strength, over its windows or
            # beyond (formerly a third of it there), and no outline edges; its tooltip says where the errors are.
            assert not [x for x in chart["chart"]["series"] if (x["id"] or "").startswith((f"{s['key']}|{form}|band", f"{s['key']}|{form}|edges"))]
            assert all(not x["silent"] and ENERGY_NO_BAND_TEXT in _plain(x["items"][0]["tip"]) for x in solid + dashed)
            # Shower B: hollow markers, its lines at 70% strength and never below 3:1; no shower dash on this view.
            # A faded fit (provisional, or a form that does not describe its windows) is drawn fainter.
            for x in solid + dashed:
                assert x["items"][0]["el"]["opacity"] == pytest.approx(s["lineOpacityFaded"] if f["faded"] else s["lineOpacity"])
            # Faded exactly when provisional or a misfit (the single-shower and XGBoost noise fits are provisional).
            assert f["faded"] == (f["provisional"] or f["misfit"])
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
        # One curve per series (Martin's directive of 2026-11-15): a/√E ⊕ b ⊕ c/E, else a₀/√E; the rest tabled only.
        assert ("This view draws one curve per series with no band: a/√E ⊕ b ⊕ c/E from 0 GeV, or, where a series has "
                "none, the origin-pinned a₀/√E ⊕ 0 from 4 GeV") in table["caption"]
        assert "the other fits are tabled only, the affine a/√E + b drawn in the 1/√E view" in table["caption"]
        for row, lrow, s in zip(table["rows"], base["rows"], _res_shown(payload, "both")):
            assert [f["form"] for f in row["fits"]] == ["affine", "pinned", "quadrature", "noise"]
            for f, lf in zip(row["fits"], lrow["fits"]):
                assert f["cells"][1:] == lf["cells"][1:], "only the Fit column names the view"
            names = [f["cells"][0] for f in row["fits"]]
            assert names[0] == "Affine a/√E + b — drawn in the 1/√E view"
            nf = s["fits"][windows]["noise"]
            pinned = s["fits"][windows]["pinned"]
            # Beside a drawn a/√E ⊕ b ⊕ c/E, a₀/√E is table only; without one it is the fallback, drawn.
            assert names[1] == ("Origin-pinned a₀/√E ⊕ 0 — table only on this view" if nf
                                else "Origin-pinned a₀/√E ⊕ 0 — drawn: no a/√E ⊕ b ⊕ c/E fit" if pinned
                                else "Origin-pinned a₀/√E ⊕ 0 — not drawn: too few windows")
            q = s["fits"][windows]["quadrature"]["params"]
            assert names[2].startswith("Quadrature a/√E ⊕ b — table only")
            assert ("A ≤ 0" in names[2]) == (not q["a_defined"]) and ("B ≤ 0" in names[2]) == (not q["b_defined"])
            if q["a_defined"] and q["b_defined"]:
                assert names[2] == "Quadrature a/√E ⊕ b — table only"
            assert names[3] == ("a/√E ⊕ b ⊕ c/E — drawn" if nf else names[3])
            assert ("drawn" in names[3].split(" — ")[1]) and ("not drawn" in names[3]) == (nf is None)


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
            # Print is white paper: the π± curve takes the white card's identity colour, picked by Dark2.
            assert s["id"] in ("literature|pi", "literature|pi|endlabels"), s["id"]
            colour = out["resE"]["litColours"]["table"][printed["palette"]]["pi"]
            assert printed["palette"] == "dark2" and colour == "#a65628"
            assert all(ch["stroke"] == colour for ch in s["items"][0]["el"]["children"] if ch["type"] == "polyline")
            assert all(ch["fill"] == printed["ink"] for ch in s["items"][0]["el"]["children"] if ch["type"] == "text")
            assert all(ch["stroke"] == colour for ch in s["items"][0]["el"]["children"] if ch["type"] == "line")
    assert [x["colour"] for x in printed["legendItems"] if " lit. — " in str(x["name"])] == ["#a65628"]
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
#: As the figure's legend prints them, with no % sign by the values (Martin's request, 2026-11-15, c406217); the
#: units are said beside them wherever the equation is read away from the axes (`REFERENCE_UNITS`).
LIT_EQUATIONS = {"pi": "σ/E = 27.2/√E ⊕ 1.0", "e": "σ/E = 14.0/√E ⊕ 0.4"}
REFERENCE_UNITS = "σ/E in percent, E in GeV"
LIT_BUTTONS = ('The π± and e± buttons draw either curve, both (the default) or neither. The ratio panel divides by the curve '
               "drawn; with both drawn, by the one the windows lie farther from; with neither, by each shower's deposit fit.")


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
            if note.startswith("Each series draws one fitted curve with no band round it"):
                # The server's restatement of the one-curve rule (single-curve round) is not printed: the drawer's
                # own one-curve and no-band sentences say it, once (SC-notes).
                assert note not in drawn and drawn.count(SC_DRAWER_ONE_CURVE) == 1, (name, key)
                continue
            assert (_range_basis(note) if i == 0 else note) in drawn, (name, key, note)
        assert not [line for line in drawn if "clipped, not rescaled" in line]
        assert "the server's count" not in _text(n)
        # P15: the drawer names the section that derives the view; P11: no dodge.
        assert drawn[1] == ('Methodology §2.4.11, "Resolution scaling against E", derives this view, from E = 1/x² to the '
                            "ratio panel's axis; §3.6 audits its marks.")
        assert ("Windows of different series at one energy are drawn at that energy, not set apart: a window sits on its own "
                "curve, which no offset could follow.") in drawn


#: The drawer's one-curve sentence (SC-notes, 2026-11-15), verbatim.
SC_DRAWER_ONE_CURVE = ("One fitted curve per series is drawn on each panel (Martin's decision, 2026-11-15): its a/√E ⊕ b ⊕ c/E, "
                       "from 0 GeV, or, where the series has none, its origin-pinned a₀/√E ⊕ 0, from 4 GeV, the thinner line. "
                       "The quadrature a/√E ⊕ b, the affine a/√E + b and, beside a drawn a/√E ⊕ b ⊕ c/E, the origin-pinned "
                       "a₀/√E are in the fit table only; the affine fit is drawn in the 1/√E view.")


def test_res_notes_e_view_counts_equal_the_models(out):
    for name, key, rec in _e_notes(out):
        n, f = rec["notes"], rec["facts"]
        drawn, dis = _lines(n, out, "drawn"), _lines(n, out, "disclosures")
        where = (name, key)
        assert f"{_n(f['nPoints'], 'window')} and {_n(f['nLines'], 'fit curve')} are drawn in this view." in drawn, where
        # Clipped at the top of the main panel: markers, whiskers, fits and literature curves, with the server's count.
        c = f["clipped"]
        parts = [_n(c[k], word) for k, word in (("markers", "marker"), ("whiskers", "whisker"), ("fits", "fitted curve"),
                                                ("literature", "literature curve")) if c[k]]
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
        # Curves that leave the top (their line alone since the single-curve round: never "line or band"), fits not
        # drawn. Each cut curve is named with its true peak, `cut.peak[1]` (formerly the band's peak[3]).
        assert sum(d["cut"] for d in f["drawn"]) == c["fits"]
        assert not [line for line in dis if "line or band" in line], where
        leave = [line for line in dis if "the top of the main panel, each clipped there with a caret" in line]
        assert len(leave) == (1 if c["fits"] else 0), where
        if c["fits"]:
            assert leave[0].startswith(f"{_n(c['fits'], 'fitted curve')} {'leaves' if c['fits'] == 1 else 'leave'} ")
            assert leave[0].count(" curve, highest ") == c["fits"], where
            for d in f["drawn"]:
                if d["cut"]:
                    assert f"{d['label']}, " in leave[0] and f"at E = {_sf(d['cutPeak'][0])} GeV" in leave[0], (where, d["label"])
        # a/√E ⊕ b ⊕ c/E comes down into the plot (Martin's decisions of 2026-11-13): counted apart from the fits that
        # leave the top (clipped.entries), one line for the curves that enter and one per curve above at every E.
        noise = [d for d in f["drawn"] if d["form"] == "noise"]
        entering = [d for d in noise if d["entry"] and d["entry"]["lineAt"] is not None]
        above_all = [d for d in noise if d["entry"] and d["entry"]["above"]]
        # The band alone entering (bandAt with its line inside) is retired with the band: every entry is the line's.
        assert not [d for d in noise if d["entry"] and d["entry"]["lineAt"] is None and not d["entry"]["above"]], where
        assert c["entries"] == len(entering) + len(above_all), where
        come = [line for line in dis if "down into the main panel from its top" in line]
        assert len(come) == (1 if entering else 0), where
        if entering:
            n_in = len(entering)
            assert come[0].startswith(f"{_n(n_in, 'a/√E ⊕ b ⊕ c/E curve')} {'comes' if n_in == 1 else 'come'} down into the main panel"), where
            for d in entering:
                term = "noise term c/E" if d["entry"]["term"] == "c" else "stochastic term a/√E"
                assert f"{d['label']} at E = {_sf(d['entry']['lineAt'])} GeV, through its {term}" in come[0], (where, d["label"])
        for d in above_all:
            assert sum(line.startswith(f"{d['label']}: its a/√E ⊕ b ⊕ c/E curve lies above the top of the main panel") for line in dis) == 1
        # Bands cut at 0 (finding F1) are gone with the band: no line says so.
        assert not [line for line in dis if " cut at 0: " in line or "cut at σ/E = 0" in line], where
        # Nothing is "not drawn" on this view but a/√E ⊕ b, tabled only, and a series without a noise fit; neither is
        # said with the retired "is not drawn, … stays in the fit table" line.
        # One curve per series (single-curve round): a₀/√E beside a drawn a/√E ⊕ b ⊕ c/E is table only too.
        for d in f["notDrawn"]:
            assert d["form"] in ("quadrature", "noise", "pinned"), (where, d)
            if d["form"] == "pinned":
                assert d["reason"] in ("table only on this view: the a/√E ⊕ b ⊕ c/E curve is drawn", "too few windows"), (where, d)
            assert not [line for line in dis if line.startswith(f"{d['label']}: the ") and "is not drawn, " in line], (where, d)
        # Spans: said once in What is drawn when shared, per span under Disclosures when they differ.
        differ = [line for line in dis if line.startswith("The curves were not all fitted over the same windows")]
        if f["drawn"] and f["spansShared"]:
            assert not differ and any(f"here {_span(f['span'])}" in line for line in drawn), where
        elif f["drawn"]:
            assert len(differ) == 1
            for d in f["spanList"]:
                assert _span(d["span"]) in differ[0]
        else:
            assert any(line.startswith("No fitted curve is drawn for this selection") for line in dis)
        # Windows below 4 GeV: those a/√E ⊕ b ⊕ c/E fits and those no fit uses (the retired "no fit uses them, and no
        # curve is drawn there" is gone).
        p = f["points"]
        below = [line for line in dis if " below 4 GeV, where a₀/√E uses none: " in line]
        assert len(below) == (1 if p["below4"] else 0), where
        if p["below4"]:
            assert below[0].startswith(f"{_n(p['below4'], 'drawn window')} {'lies' if p['below4'] == 1 else 'lie'} below 4 GeV")
        assert not [line for line in dis if "no curve is drawn there" in line or "no curve is drawn below 4 GeV" in line], where
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
        assert "bands" not in rc and f["retired"] == {"bandsOutlined": False, "ratioBands": False}, where
        ratio_parts = [_n(rc[k], word) for k, word in (("markers", "marker"), ("whiskers", "whisker"), ("fits", "fitted curve"),
                                                       ("literature", "literature ratio line")) if rc[k]]
        clipped_ratio = _starts(dis, "Clipped at the ratio axis")
        if ratio_parts:
            assert len(clipped_ratio) == 1 and clipped_ratio[0].endswith(f": {', '.join(ratio_parts)}."), where
            assert f" {_in_force(f, key)}, each with a caret" in clipped_ratio[0], where
        else:
            assert not clipped_ratio
        assert c["ratio"] == rc["markers"] + rc["whiskers"] + rc["fits"] + rc["literature"]
        # P13's reference band clamped at the ratio axis and P1's bands drawn as their edges are retired with every
        # band of this view (Martin's directive of 2026-11-15): neither is drawn, so neither is counted or listed.
        assert not [line for line in dis if "muted wash" in line or "never as a wash" in line or "reference band" in line], where
        # P9: a cap is said, with its count.
        assert any(line.startswith("The ratio axis is capped at ×50") for line in dis) == bool(f["capped"]), where
        # Off the ratio panel below the floor of the reference in force: 1 GeV under the deposit's noise fit (brief
        # section 8's sentence), 4 GeV under the a₀/√E fallback; per floor, as the model groups them.
        gone = [line for line in dis if "not drawn on the ratio panel" in line]
        by_form = {}
        for g in f["ratioBelow"]:
            by_form[g["form"]] = by_form.get(g["form"], 0) + g["n"]
        assert sum(by_form.values()) == f["belowNotDrawn"], where
        assert len(gone) == len(by_form), where
        if "noise" in by_form:
            n_b = by_form["noise"]
            assert (f"{_n(n_b, 'window')} below 1 GeV {'is' if n_b == 1 else 'are'} not drawn on the ratio panel: no window below 1 GeV "
                    "enters the deposit's a/√E ⊕ b ⊕ c/E fit.") in gone, where
        if "pinned" in by_form:
            assert any(x.startswith(f"{_n(by_form['pinned'], 'window')} below 4 GeV") for x in gone), where
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
            # One line per shower: which fit divides its windows, from which floor, or why none does. The deposit's a/√E ⊕ b ⊕ c/E fit from 1 GeV (Martin's decisions of 2026-11-13),
            # else its a₀/√E fit from 4 GeV.
            payload = _load(name)
            windows = key.split(":")[0]
            ref_lines = [x for x in _lines(n, out, "drawn") if re.match(r"^(Shower [AB]|The deposit): (the ratio divides|no ratio marks)", x)]
            assert len(ref_lines) == len(f["deposit"]), (name, key)
            for d in f["deposit"]:
                det = next(s for s in payload["series"] if s["source"] == "detector" and s["shower"] == d["shower"])
                (line,) = [x for x in ref_lines if x.startswith(("The deposit" if f["nShowers"] < 2 else f"Shower {d['shower'].upper()}"))]
                if d["reason"]:
                    assert d["reason"] in " ".join(_lines(n, out, "drawn"))
                elif det["fits"][windows]["noise"]:
                    assert "its deposit's a/√E ⊕ b ⊕ c/E fit" in line and "ratio mark from 1 GeV" in line, (name, key, line)
                else:
                    assert "its deposit's a₀/√E fit" in line and "evaluated from 4 to 80 GeV only" in line, (name, key, line)
            # The reference's own band about 1 is retired (Martin's directive of 2026-11-15): it is held exact, and
            # the legend says so.
            assert "band" not in drawn.replace(SC_DRAWER_NO_BAND, ""), (name, key)
            assert "the reference is held exact" in " ".join(_lines(n, out, "legend")), (name, key)
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
        legend = " ".join(_lines(n, out, "legend"))
        hues = "π± a brown and e± a purple"
        if literature:
            # The provenance names the figure's two legend curves; only the one in force is drawn, in its own colour.
            particle = {"pi": "π±", "e": "e±"}[f["literature"]]
            assert LIT_EQUATIONS["pi"] in dis and LIT_EQUATIONS["e"] in dis, "the provenance names both legend curves"
            assert "Each is a documented point estimate with no interval reported and none derived" in dis
            assert f"Here the {particle} curve is the ratio's reference." in legend
            assert LIT_BUTTONS in legend
            assert f"Each literature curve has a colour of its own on every card, {hues}" in legend
            assert "No literature curve sets a range on either panel" in dis
            assert f"Literature curves drawn: {particle} (the ratio's reference)." in _lines(n, out, "selection")
            assert "evaluated at every E on the axis and drawn dotted on the main panel in its own colour" in " ".join(_lines(n, out, "drawn"))
            assert ("crosses the top of the main panel, clipped there with a caret" in dis) == bool(f["clipped"]["literature"])
        else:
            assert "ECCE" not in text and "none derived" not in text
            assert "A literature curve is a dotted line in its own colour; none is drawn now." in legend
            assert LIT_BUTTONS in legend and f"Each literature curve has a colour of its own on every card, {hues}" in legend
            assert "Literature curves drawn: none." in _lines(n, out, "selection")
        # Never the old wording: both curves drawn, or the muted ink for a literature curve.
        for stale in ("Both curves are drawn", "both literature curves", "Dotted muted", "draws both", "muted lines"):
            assert stale not in text, (name, key, stale)
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
    # The literature curve in force crossing the top is counted and said; it is the only one drawn, so the count is 1.
    lit = v["literatureClipped"]
    assert lit["facts"]["clipped"]["literature"] == 1 and "marks clipped at the axis" in lit["hazards"]
    crosses = [line for line in _lines(lit["notes"], out, "disclosures") if "crosses the top of the main panel, clipped there with a caret" in line]
    assert crosses == ["No literature curve sets a range on either panel; the π± curve crosses the top of the main panel, clipped there with a caret."]
    top = [line for line in _lines(lit["notes"], out, "disclosures") if line.startswith("Clipped at the top of the main panel")]
    assert len(top) == 1 and top[0].endswith("1 literature curve.")
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
    # a/√E ⊕ b is table only on this view (Martin's decisions of 2026-11-13): an undefined term no longer draws a
    # "not drawn (A = …, B = …)" line; the drawer says once that the form is in the fit table.
    ub = v["undefinedB"]
    assert {"label": "Shower B · Energy network · absolute frame", "form": "quadrature",
            "reason": "table only: a/√E ⊕ b ⊕ c/E takes its place on this view"} in ub["facts"]["notDrawn"]
    assert not [x for x in _text(ub["notes"]).split(". ") if "the quadrature fit a/√E ⊕ b is not drawn" in x]
    assert not re.search(r"\(A = [^)]*%²·GeV, B = ", _text(ub["notes"]))
    for n in (ub["notes"], out["resNotes"]["fixtures"]["res_scaling_two"]["all:deposit:both"]["notes"]):
        # Said once, inside the one-curve sentence (single-curve round), never as its own line.
        assert _text(n).count(SC_DRAWER_ONE_CURVE) == 1 and "a/√E ⊕ b is in the fit table, not drawn." not in _text(n)
    # No E-view axis, no response, nothing drawable.
    na = v["noAxis"]
    assert na["facts"] is None and na["hazards"] == []
    assert na["notes"]["headings"] == [out["notes"]["section"]["disclosures"]]
    assert "no energy-resolution series with an E-view axis" in _text(na["notes"])
    assert v["nothing"] == [None, []]
    empty = v["empty"]
    _check_notes(empty["notes"], out["notes"]["section"])
    assert empty["facts"]["nPoints"] == 0 and empty["facts"]["nLines"] == 0
    assert any(line.startswith("No fitted curve is drawn for this selection") for line in _lines(empty["notes"], out, "disclosures"))
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
        assert "−" in text, "a negative number is set with U+2212"
        _no_hyphen_numbers(line for lines in n["sections"].values() for line in lines)
    # The E view no longer prints a quadrature fit's negative A or B (tabled only, Martin's decisions of 2026-11-13);
    # its median-response range carries the minus, and the 1/√E drawer keeps the quadrature's A = −… and B = −….
    assert re.search(r"runs from −\d", _text(two)) and re.search(r"runs from −\d", _text(xgb))
    assert re.search(r"B = −\d", _text(out["res"]["res_scaling_xgb"]["notes"]["anchors"]))
    assert re.search(r"A = −\d", _text(out["res"]["res_scaling_two"]["notes"]["all"]))
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
    """A band is drawn as its edges once it spans half its axis or more at one E of its fitted span. The rule now
    serves the 1/√E view alone (the E view draws no band since the single-curve round); its helper is unchanged."""
    s = out["resFix"]["share"]
    assert s["value"] == 0.5
    assert s["half"] is True and s["under"] is False, "50 of 100 at 5 GeV is half; 45 is not"
    assert s["beyondSpan"] is False, "only the fitted span counts"
    assert s["clampedTop"] is True and s["clampedShort"] is False, "only the part inside the axis counts: 40-100 is 60%, 60-100 is 40%"
    assert s["logHalf"] is True and s["logUnder"] is False, "on the ratio panel the share is taken on the log scale"


def test_res_sc_a_wide_fit_draws_its_line_alone_with_no_edges_on_either_panel(out):
    """P1's case, retargeted (Martin's directive of 2026-11-15: no band on the E view, so none is outlined). The clone
    whose network A noise fit has S = 1.5 and a quantile of 12.71 on a top of 300% (P1 drew its band as two edges on
    both panels and listed it) now draws its line alone: no wash, no edges, no band caret, on either panel; its line
    and its ratio are the recording's at the same top (S and the quantile move no mark); its tooltips say no band is
    drawn; the drawer lists no outlined band and the model carries no `bandsOutlined`; and it raises no hazard of its
    own. The deposit reference whose S = 3 (P1 on the band about 1) moves no ratio mark and draws nothing about 1."""
    o = out["resFix"]["outlined"]
    assert o["retired"] == {"bandsOutlined": False, "fit": []} and o["drawnForm"] == "noise"
    assert o["edges"] == [] and not [i for i in o["ids"] if "|band|" in i or "|edges|" in i or "|reference|" in i]
    assert o["curve"] == o["baseCurve"] and o["ratioRows"] == o["baseRatioRows"] and o["curve"]
    assert {len(r) for r in o["curve"]} == {2}
    curves = [s["items"][0]["tip"] for s in o["chart"]["series"]
              if s["id"].startswith(("network:a|noise|solid|", "network:a|ratio|noise|solid|"))]
    assert len(curves) >= 2 and not [t for t in curves if "drawn as its edges" in t or "95% band" in t]
    main_tips = [s["items"][0]["tip"] for s in o["chart"]["series"] if s["id"].startswith("network:a|noise|")]
    assert main_tips and all(ENERGY_NO_BAND_TEXT in _plain(t) for t in main_tips)
    main_tip = next(s["items"][0]["tip"] for s in o["chart"]["series"] if s["id"].startswith("network:a|noise|solid|"))
    assert "S = 1.5" in _plain(main_tip), "the scaled errors stay in the tooltip"
    assert not [line for line in _dis(o["notes"], out) if "never as a wash" in line or "drawn as its edges" in line]
    assert set(o["hazards"]) <= set(o["hazardsBase"]) | {"marks clipped at the axis"}, "no hazard of its own"
    r = out["resFix"]["refOutlined"]
    assert r["retired"] == [] and r["interval"] is None and r["form"] == "noise" and r["ids"] == []
    assert r["ratios"] == r["baseRatios"] and r["clipped"] == r["baseClipped"]
    assert r["unityTip"] is None or "band" not in _plain(r["unityTip"])
    assert not [line for line in _dis(r["notes"], out) if "reference band" in line or "band about 1 of" in line]


def test_res_fix_p2_end_labels_name_the_shower_in_a_column_beside_the_plot(out):
    seen = {"ab": 0, "lit": 0}
    for key, rec in out["resFix"]["labels"].items():
        k, yhi, font = rec["k"], rec["yhi"], rec["fontTip"]
        want_main, want_ratio = [], []
        for f in rec["fits"] if rec["twoOnShow"] else []:
            tag = (f["key"], f["form"], f["shower"].upper(), f["colour"])
            if "end" not in f:
                # An a/√E ⊕ b ⊕ c/E curve above the top at every E has no row on the main panel, so no label there (its
                # caret says so); its ratio, defined from 0 GeV, keeps its own.
                assert f["form"] == "noise" and key.startswith("low:"), key
            else:
                assert f["end"][0] == pytest.approx(rec["xmax"])
                if 0 <= f["end"][1] <= yhi:
                    want_main.append(tag)
            if f["ratioEnd"] and 1 / k * (1 - 1e-9) <= f["ratioEnd"][1] <= k * (1 + 1e-9):
                want_ratio.append(tag)
        got = lambda panel: [(x["key"], x["form"], x["text"], x["colour"]) for x in rec["endLabels"][panel] if not x["literature"]]  # noqa: E731
        assert got("main") == want_main and got("ratio") == want_ratio, key
        # The width is the form: the key stroke of a/√E ⊕ b ⊕ c/E is the 1.6 px a/√E ⊕ b had, a₀/√E's 1 px.
        for x in rec["endLabels"]["main"] + rec["endLabels"]["ratio"]:
            if not x["literature"]:
                assert x["stroke"]["width"] == (1.6 if x["form"] == "noise" else 1), (key, x["key"], x["form"])
        seen["ab"] += len(want_main)
        # The literature curve's particle, in its identity colour (the dark card's, picked by Set2), main panel only;
        # only the curve in force has one.
        lits = [x for x in rec["endLabels"]["main"] if x["literature"]]
        assert [x["text"] for x in lits] == [l["label"] for l in rec["literature"]]
        assert all(x["colour"] == out["resE"]["litColours"]["table"]["set2"][x["key"].split("|")[1]] for x in lits)
        assert [x["key"] for x in lits] == [f"literature|{k}" for k in key.split(":")[2:3] if k in ("pi", "e")]
        assert not [x for x in rec["endLabels"]["ratio"] if x["literature"]]
        seen["lit"] += len(lits)
        # The column: both grids' right widened by the widest label and its gap; untouched without a label.
        g0, g1 = rec["grid"]
        labels = rec["endLabels"]["main"] + rec["endLabels"]["ratio"]
        # The column holds the gap, the key stroke and its gap, then the widest text.
        column = -(-((0.5 + 1.2 + 0.35) * font + max(_width(x["text"], font) for x in labels)) // 1) if labels else 0
        assert g0["right"] == g1["right"] == pytest.approx(rec["pad"]["right"] + column), key
        # One series per legend entry and panel, drawn outside the plot, the text left-aligned past x.max.
        texts = [t for s in rec["series"] for t in s["texts"]]
        assert sorted(t["text"] for t in texts) == sorted(x["text"] for x in labels)
        for s in rec["series"]:
            assert s["clip"] is False and s["silent"] is True and s["xAxisIndex"] == (1 if s["id"].endswith("|ratio|endlabels") else 0)
            assert all(t["align"] == "left" and t["x"] == pytest.approx(rec["xmax"] + (0.5 + 1.2 + 0.35) * font) for t in s["texts"])
            # Ink text (4.5:1 on every card); the curve's colour is carried by the key stroke before it.
            assert all(t["fill"] == s["ink"] for t in s["texts"]), s["id"]
            assert len(s["keys"]) == len(s["texts"])
            for key_stroke in s["keys"]:
                assert key_stroke["x1"] == pytest.approx(rec["xmax"] + 0.5 * font) and key_stroke["x2"] == pytest.approx(rec["xmax"] + 1.7 * font)
            colours = {x["colour"] for x in labels if x["name"] == s["name"]}
            assert {k["stroke"] for k in s["keys"]} <= colours, s["id"]
        # Shower B's strength, worded as drawn; the end labels named only where both showers are drawn.
        # A tooltip to read wherever a shower B curve is on the main panel (on a top of 30% they all lie above it:
        # one curve per series since the single-curve round, so no a₀/√E from 4 GeV is drawn beside them).
        assert bool(rec["bTips"]) == (bool(rec["bOpacity"]) and rec["bOnMain"]), key
        for tip in map(_plain, rec["bTips"]):
            assert "Shower B's lines are drawn at 70% strength, raised where the card needs it to keep 3:1 (this one at " in tip
            assert ("so the end labels name the shower" in tip) == rec["twoOnShow"]
            strength = int(re.search(r"\(this one at (\d+)%\)", tip).group(1))
            assert strength >= 70 or "Provisional" in tip or "does not describe these windows" in tip
    assert seen["ab"] and seen["lit"]
    assert not out["resFix"]["labels"]["two:all:deposit:a"]["endLabels"]["main"], "one shower, no literature: no label"
    assert not out["resFix"]["labels"]["two:all:deposit:a"]["twoOnShow"] and not out["resFix"]["labels"]["xgb:all:deposit:both"]["twoOnShow"]
    # A curve that leaves the plot before x.max has its caret and no label (a top of 30%: the deposit curves leave it).
    low = out["resFix"]["labels"]["low:all:deposit:both"]
    # One curve per series (single-curve round): on this top every noise curve lies above the plot, so none has a
    # main-panel label (the a₀/√E curves from 4 GeV that kept one are table only now); their ratios keep theirs.
    gone = [f for f in low["fits"] if "end" not in f or f["end"][1] > low["yhi"]]
    assert gone and low["endLabels"]["ratio"]
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

    # The drawn curve's ratio: a/√E ⊕ b ⊕ c/E since the single-curve round (a₀/√E only as a fallback).
    fits = tips(pi, r"\|ratio\|(noise|pinned)\|(solid|dashed)\|")
    assert not tips(pi, r"\|(band|edges)\|"), "no band on the ratio panel"
    carets = [t for t in tips(pi, r"\|ratio\|carets$") if "leaves the ratio axis" in t]
    unity, lit = tips(pi, r"^ratio\|unity$"), tips(pi, r"^literature\|\w+\|caret$")
    assert fits and carets and unity and lit, "the clone draws every kind of mark the rule names"
    # The π± curve's caret is the curve's only caret, in its identity colour; e± is not drawn, so it has none.
    caret = [s for s in pi["series"] if re.fullmatch(r"literature\|\w+\|caret", s["id"] or "")]
    pi_colour = out["resE"]["litColours"]["table"]["set2"]["pi"]
    assert [s["id"] for s in caret] == ["literature|pi|caret"] and caret[0]["colour"] == pi_colour
    assert all(i["el"]["fill"] == pi_colour for i in caret[0]["items"])
    for t in fits + carets + unity + lit:
        assert _plain(t).endswith(LIT_NO_INTERVAL), _plain(t)[-160:]
    held = "The fitted curve divided by the reference at each E, the reference held exact."
    assert all(held in _plain(t) for t in fits)
    assert all("its own uncertainty is not included" not in t for t in fits)
    # Under the deposit reference no tooltip says it; the reference is held exact there too, with no band about 1
    # drawn beside it (single-curve round: the former "(its own band about 1 is drawn beside it …)" is gone).
    assert not [t for s in deposit["series"] for i in s["items"] if (t := i["tip"]) and LIT_NO_INTERVAL in t]
    dep = tips(deposit, r"\|ratio\|(noise|pinned)\|(solid|dashed)\|")
    # review-ui F4 (19f6ab2): every ratio curve's tooltip says once that no band is drawn on this view; beyond that
    # sentence it speaks of no band.
    assert dep and all(held in _plain(t) for t in dep)
    for t in fits + dep:
        assert _plain(t).count(ENERGY_NO_BAND_TEXT) == 1, _plain(t)
        assert "band" not in _plain(t).replace(ENERGY_NO_BAND_TEXT, ""), _plain(t)
    assert not tips(deposit, r"\|(band|edges|reference)\|")


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


def test_res_sc_the_deposit_reference_draws_nothing_about_one(out):
    """P13, retargeted (Martin's directive of 2026-11-15): the deposit reference's band about 1, its outline and its
    muted caret are retired. In the anchors mode of the two-shower recording, whose reference bands reached the ratio
    axis before, no reference series is drawn, no reference caret, the references carry no band field and a null
    interval, the ratio's carets are the markers', whiskers', curves' and literature lines' alone, and the drawer
    names no reference band."""
    r = out["resFix"]["refCaret"]
    assert r["carets"] == [] and r["refIds"] == []
    assert r["refs"] and all(x["interval"] is None and x["retired"] == [] for x in r["refs"])
    assert set(r["clipped"]) == {"markers", "whiskers", "fits", "literature"}
    assert r["ratio"] == r["clipped"]["markers"] + r["clipped"]["whiskers"] + r["clipped"]["fits"] + r["clipped"]["literature"]
    assert not [line for line in _dis(r["notes"], out) if "reference band" in line or "muted caret" in line]


def test_res_fix_p14_a_provisional_sigma_axis_names_the_two_gev_floor(out):
    assert out["resFix"]["provisional"]["axisName"] == "σ/E [%] — provisional, no window from 2 GeV reaches N = 20"
    assert out["resE"]["provisional"]["yAxes"][0]["name"] == "σ/E [%] — provisional, no window from 2 GeV reaches N = 20"


def test_res_fix_n2_the_literature_provenance_says_its_range_is_unknown(out):
    for ref in ("pi", "e"):
        chart = out["resE"]["fixtures"]["res_scaling_two"]["charts"][f"all:{ref}"]
        lits = [s for s in chart["chart"]["series"] if re.fullmatch(r"literature\|\w+", s["id"] or "")]
        assert [s["id"] for s in lits] == [f"literature|{ref}"] and NO_RANGE in lits[0]["items"][0]["tip"]
    for name, key, rec in _e_notes(out):
        dis = _dis(rec["notes"], out)
        said = [line for line in dis if line.startswith("The figure does not state the energy range either curve was fitted over")]
        assert len(said) == (0 if key.split(":")[1] == "deposit" else 1), (name, key)


# ---------------------------------------- the literature curves as toggles (Martin, 2026-11-11) --

#: The catalogue's two curves, as resolution_references.md prints them: a (%·√GeV) and b (%).
LIT_AB = {"pi": (27.2, 1.0), "e": (14.0, 0.4)}


def _lit(key: str, e: float) -> float:
    a, b = LIT_AB[key]
    return (a * a / e + b * b) ** 0.5


def _sig3(v: float) -> str:
    """chart_panel.js sigFigs(v, 3) for a factor ≥ 1: three significant figures, trailing zeros dropped."""
    return f"{float(f'{v:.3g}'):g}"


def _lit_series(chart: dict, prefix: str = "literature|") -> dict:
    return {s["id"]: s for s in chart["chart"]["series"] if (s["id"] or "").startswith(prefix)}


def test_res_literature_drawn_follows_the_toggles_in_catalogue_order(out):
    # The toggles' keys, unknown ones dropped; without them the older single reference draws that curve alone.
    assert out["resE"]["litToggles"]["drawn"] == [["pi", "e"], ["pi", "e"], [], ["e"], [], [], []]


def test_res_the_ratio_reference_is_the_curve_that_needs_the_most_scaling(out):
    """Martin's request of 2026-11-11: with both curves drawn the ratio divides by the one the windows lie farther
    from, by the median |ln(σ/E ÷ curve)| over the robust windows (N ≥ 20 from 2 GeV), else every window on show;
    π±, the catalogue's first, on a tie or with no window. One curve is the reference; none leaves the deposit fit."""
    c = out["resE"]["litToggles"]["choices"]
    assert c["none"] == {"key": "deposit", "rule": "deposit", "basis": None, "n": 0, "scores": []}
    assert c["one"] == {"key": "e", "rule": "single", "basis": None, "n": 0, "scores": []}
    on_pi = {sc["key"]: sc for sc in c["onPi"]["scores"]}
    assert c["onPi"]["key"] == "e" and c["onPi"]["rule"] == "farther" and c["onPi"]["basis"] == "robust" and c["onPi"]["n"] == 3
    assert on_pi["pi"]["factor"] == pytest.approx(1.0, abs=1e-12)
    assert on_pi["e"]["factor"] == pytest.approx(statistics.median(_lit("pi", e) / _lit("e", e) for e in (5, 10, 15)), rel=1e-12)
    assert c["onE"]["key"] == "pi"
    assert c["tie"]["key"] == "pi" and c["tie"]["scores"][0]["factor"] == pytest.approx(c["tie"]["scores"][1]["factor"], rel=1e-9)
    assert c["empty"]["key"] == "pi" and c["empty"]["basis"] is None and all(sc["factor"] is None for sc in c["empty"]["scores"])
    assert c["markers"]["basis"] == "markers" and c["markers"]["n"] == 2
    # 2.0% and 2.2% lie below both curves at 10-12 GeV, nearer e± (3.8%) than π± (8.4%): π± needs the most scaling.
    assert c["markers"]["key"] == "pi"
    assert c["robustWins"]["basis"] == "robust" and c["robustWins"]["n"] == 1 and c["robustWins"]["key"] == "pi"


def test_res_both_literature_curves_by_default_divide_by_the_farther(out):
    """Both curves on: both drawn in their own colours; the ratio divides by the farther one, recomputed here from the
    windows on show; the other is drawn on the ratio panel divided by it, never setting k; the drawer, the tooltips and
    the hazard say why and what."""
    t = out["resE"]["litToggles"]
    colours = out["resE"]["litColours"]["dark"]
    particle = {"pi": "π±", "e": "e±"}
    for case in (t["both"], t["bothAnchors"]):
        robust = [p for p in case["points"] if p["n"] >= 20 and p["pLo"] >= 2 and p["value"] > 0]
        basis = robust or [p for p in case["points"] if p["value"] > 0]
        factor = {k: math.exp(statistics.median(abs(math.log(p["value"] / _lit(k, p["E"]))) for p in basis)) for k in ("pi", "e")}
        ref = "e" if factor["e"] > factor["pi"] * (1 + 1e-12) else "pi"
        other = "pi" if ref == "e" else "e"
        assert case["reference"] == ref and case["choice"]["rule"] == "farther", (case["reference"], factor)
        assert {sc["key"]: sc["factor"] for sc in case["choice"]["scores"]} == pytest.approx(factor, rel=1e-12)
        lits = {l["key"]: l for l in case["literature"]}
        assert [l["key"] for l in case["literature"]] == ["pi", "e"]
        assert lits[ref]["isReference"] is True and lits[ref]["ratio"] is None and lits[other]["isReference"] is False
        assert {k: lits[k]["colour"] for k in lits} == {k: colours[k]["literature"][0]["colour"] for k in ("pi", "e")}
        rows = lits[other]["ratio"]["rows"]
        assert rows and all(r == pytest.approx(_lit(other, e) / _lit(ref, e), rel=1e-12) for e, r in rows)
        k = case["k"]
        assert all(1 / k - 1e-12 <= v <= k + 1e-12 for run in lits[other]["ratio"]["runs"] for _, v in run)
        series = _lit_series(case["chart"])
        assert {f"literature|{ref}", f"literature|{other}", f"literature|{other}|ratio"} <= set(series)
        assert f"literature|{ref}|ratio" not in series, "the reference is the 1.0 rule, not a line"
        line, main = series[f"literature|{other}|ratio"], series[f"literature|{other}"]
        assert line["xAxisIndex"] == 1 and line["yAxisIndex"] == 1 and line["name"] == main["name"]
        assert f"{particle[other]} literature curve ÷ {particle[ref]}" in _plain(line["items"][0]["tip"])
        why = (f"With both curves drawn the ratio divides by {particle[ref]}, the curve the windows lie farther from and so the "
               "one that needs the most scaling: ")
        ref_tip = _plain(series[f"literature|{ref}"]["items"][0]["tip"])
        assert why in ref_tip and "drawn beside it is drawn there too, divided by it" in ref_tip
        assert why in _plain(case["unityTip"])
        assert particle[ref] in case["chart"]["yAxes"][1]["name"]
        n = case["notes"]
        assert f"Literature curves drawn: π±{' (the ratio' + chr(39) + 's reference)' if ref == 'pi' else ''} and e±{' (the ratio' + chr(39) + 's reference)' if ref == 'e' else ''}." in _lines(n, out, "selection")
        drawn = _lines(n, out, "drawn")
        (said,) = [x for x in drawn if x.startswith(why)]
        assert f"sit a median ×{_sig3(factor[ref])} from {particle[ref]} and ×{_sig3(factor[other])} from {particle[other]}" in said
        assert f"The {particle[other]} curve, drawn beside it, is drawn on the ratio panel too, divided by it, one line for every shower" in " ".join(drawn)
        assert LIT_BUTTONS in " ".join(_lines(n, out, "legend"))
        assert "no interval reported" in case["hazards"]


def test_res_one_curve_is_the_reference_and_none_leaves_the_deposit_fit(out):
    t = out["resE"]["litToggles"]
    for key in ("pi", "e"):
        case = t[key]
        assert case["reference"] == key and case["choice"]["rule"] == "single"
        assert [(l["key"], l["isReference"], l["ratio"]) for l in case["literature"]] == [(key, True, None)]
        assert not [x for x in _lines(case["notes"], out, "drawn") if x.startswith("With both curves drawn")]
        assert "no interval reported" in case["hazards"]
    none = t["none"]
    assert none["reference"] == "deposit" and not none["literature"] and "deposit fit" in none["chart"]["yAxes"][1]["name"]
    assert not _lit_series(none["chart"]) and "no interval reported" not in none["hazards"]
    assert "With no literature curve drawn, the ratio divides each shower by its own deposit fit." in _lines(none["notes"], out, "drawn")
    assert "Literature curves drawn: none." in _lines(none["notes"], out, "selection")


def test_res_a_literature_ratio_off_the_axis_is_clipped_and_counted(out):
    """Windows at 0.7 × π±: π± is the farther curve and the reference, k is 1.5, and e±/π± (about 0.51) lies below
    1/k: no line, one caret pointing down with its true value, a count in the drawer; k is still the windows' alone."""
    case = out["resE"]["litToggles"]["atSevenTenthsPi"]
    assert case["reference"] == "pi" and case["k"] == 1.5, (case["reference"], case["k"])
    (e,) = [l for l in case["literature"] if l["key"] == "e"]
    assert e["ratio"]["runs"] == [] and e["ratio"]["cut"]["dir"] == "down"
    assert e["ratio"]["cut"]["at"] == pytest.approx(e["ratio"]["rows"][0][0])
    clipped = case["ratioClipped"]
    assert clipped["literature"] == 1
    assert "bands" not in clipped, "no band about 1 or round a ratio to clip (single-curve round)"
    assert case["clippedRatio"] == clipped["markers"] + clipped["whiskers"] + clipped["fits"] + clipped["literature"]
    caret = _lit_series(case["chart"])["literature|e|ratio|caret"]
    assert caret["xAxisIndex"] == 1 and caret["yAxisIndex"] == 1
    assert not case["endRatio"], "a line off the axis has its caret, not an end label"
    dis = _dis(case["notes"], out)
    assert any(line.endswith("the e± curve's ratio leaves the ratio axis, clipped there with a caret.") for line in dis), dis
    assert any("1 literature ratio line" in line for line in dis if line.startswith("Clipped at the ratio axis")), dis


def test_res_fix_n3_no_noise_band_so_nothing_is_cut_at_zero(out):
    """N3 drew a/√E ⊕ b ⊕ c/E's band as √ of the z band with its lower edge cut at 0, flagged in the model, its tooltip
    and the drawer's legend. With no band on the E view (Martin's directive of 2026-11-15) there is no lower edge to
    cut: no drawn fit carries `floorCut`; no tooltip, legend or disclosure speaks of a band cut at 0; and the line
    itself, √max(z, 0), never goes below 0 on any recording (the deposit A of the two-shower recording, whose band was
    cut, included)."""
    for name, key, rec in _e_notes(out):
        text = _text(rec["notes"])
        assert "its lower edge cut at 0" not in text and " cut at 0: " not in text and "cut at σ/E = 0" not in text, (name, key)
    for name in RES:
        for key, model in out["resE"]["fixtures"][name]["models"].items():
            for s, form, f in _e_drawn_fits(model):
                assert "floorCut" not in f["retired"] and f["retired"] == [], (name, key, s["key"])
                for row in (f.get("curve") or []) + (f.get("full") or []):
                    assert row[1] >= 0, (name, key, s["key"], row)
        for x in out["resE"]["fixtures"][name]["charts"]["anchors:deposit"]["chart"]["series"]:
            for i in x["items"]:
                assert not i["tip"] or "Its lower edge is cut at 0" not in _plain(i["tip"]), (name, x["id"])


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
    _no_hyphen_numbers(e["tip"] for e in fix["outlined"]["edges"])
    _no_hyphen_numbers(c["tip"] for c in fix["refCaret"]["carets"])
    _no_hyphen_numbers(fix["literatureTips"]["pi"]["strings"] + fix["literatureTips"]["deposit"]["strings"])
    _no_hyphen_numbers([fix["capped"]["axisName"], fix["provisional"]["axisName"], *fix["tickLabels"]])
    for medium in ("screen", "print"):
        _no_hyphen_numbers(g["text"] for c in fix["note"][medium] for g in c["graphics"])
    notes = [fix["outlined"]["notes"], fix["refOutlined"]["notes"], fix["capped"]["notes"], fix["refCaret"]["notes"],
             fix["provisional"]["weaker"], fix["provisional"]["nothing"], fix["lightB"]["notes"],
             *(rec["notes"] for rec in fix["labels"].values())]
    _no_hyphen_numbers(line for n in notes for lines in n["sections"].values() for line in lines)


# ------------------------- res-scaling: the windows alone set the range; a misfit is faded --
#
# Martin's decision of 2026-11-11 (`out["resMisfit"]`): no fit sets either view's σ/E range, so a fitted line,
# curve or band above the windows' top is clipped with a caret, its true values and a count; and a fit whose form
# does not describe its windows (the server's `misfit`: ν ≥ 1 and S = √(χ²/ν) > 5) is drawn faded, as a
# provisional fit is, says so in its tooltips and the fit table's Status, is named in the drawer, never sets the
# ratio range either, and raises no hazard. The clones change only what the server would: the misfit's flag, S,
# χ² and p; the axes' tops to the windows' alone.

MISFIT_TEXT = ("Its form does not describe these windows: χ²/ν = 64, so its residuals average S = 8 times the windows' "
               "own errors (above 5); drawn faded, it never sets the range.")
MISFIT_STATUS = "form does not describe its windows (S = 8 > 5)"


def test_res_misfit_flag_is_the_servers_and_its_sentence(out):
    m = out["resMisfit"]
    assert m["misfitText"] == MISFIT_TEXT
    assert m["isMisfit"] == [True, False, False, False], "the server's flag alone decides; S without it is not a misfit"


def test_res_misfit_is_faded_in_the_linear_view_with_its_tooltip_and_status(out):
    base, mis = out["resMisfit"]["base"], out["resMisfit"]["mis"]
    assert (base["linearFit"]["misfit"], base["linearFit"]["faded"]) == (False, False)
    assert (mis["linearFit"]["misfit"], mis["linearFit"]["faded"], mis["linearFit"]["provisional"]) == (True, True, False)
    # Faded exactly as a provisional fit is: its line at the provisional opacity (never below 3:1), its band at 0.6.
    wanted = mis["linearFit"]["wanted"]
    assert base["linearLines"] and all(x["opacity"] == 1 for x in base["linearLines"])
    assert mis["linearLines"] and wanted < 1 and all(x["opacity"] == pytest.approx(wanted) for x in mis["linearLines"])
    (b_band,), (m_band,) = base["linearBand"], mis["linearBand"]
    assert m_band["opacity"] == pytest.approx(0.6 * b_band["opacity"])
    assert [x["opacity"] for x in mis["linearAffine"]] == [x["opacity"] for x in base["linearAffine"]], "only the misfit fades"
    assert MISFIT_TEXT in _plain(mis["linearFit"]["line"]) and MISFIT_TEXT in _plain(mis["linearLines"][0]["tip"])
    assert "does not describe" not in base["linearFit"]["line"]
    # The Status cell says so in both views; the caption states the rule.
    for table in ("table", "tableE"):
        rows = _fit_rows(mis[table])
        assert rows["detector:a"]["pinned"][6] == MISFIT_STATUS and rows["network:b"]["quadrature"][6] == MISFIT_STATUS
        assert rows["network:b"]["noise"][6] == MISFIT_STATUS
        assert "does not describe" not in rows["detector:a"]["affine"][6]
        assert "Above S = 5 a fit's form does not describe its windows, and a drawn one is faded." in mis[table]["caption"]
        assert not [c for r in _fit_rows(base[table]).values() for c in r.values() if "does not describe" in c[6]]
    # No new hazard: the deposit's pinned fit is a misfit on every real dataset, and an always-on dot says nothing.
    assert mis["hazards"] == base["hazards"] and mis["hazardsE"] == base["hazardsE"]


def test_res_misfit_is_faded_in_the_e_view_on_both_panels_extrapolation_included(out):
    """A drawn misfit fades whole, its solid part and its dashed extrapolation, on both panels, its tooltips saying
    why. One curve per series since the single-curve round (Martin's directive of 2026-11-15): the network B's noise
    curve, and, on the copy whose network A has no noise fit, its a₀/√E fallback. The deposit A's a₀/√E is tabled
    beside its noise curve, so its misfit is in the table only and draws nothing. No band of either is drawn (they
    were faded to 0.6 before)."""
    base, mis, fb, fb_mis = (out["resMisfit"][k] for k in ("base", "mis", "fb", "fbMis"))
    for key, want in (("bNoise", True), ("aNoise", False)):
        f = mis["eFits"][key]
        assert f["drawable"] and (f["misfit"], f["faded"], f["provisional"]) == (want, want, False), key
        assert base["eFits"][key]["faded"] is False
    # The deposit A's a₀/√E is tabled beside its noise curve: misfit or not, nothing of it is drawn.
    assert mis["eFits"]["aPinned"]["drawable"] is False and not mis["eA"] and not base["eA"]
    # The fallback: drawn, faded exactly when it is the misfit.
    f, g = fb_mis["eFits"]["nPinned"], fb["eFits"]["nPinned"]
    assert f["drawable"] and (f["misfit"], f["faded"], f["provisional"]) == (True, True, False)
    assert g["drawable"] and g["faded"] is False
    # a/√E ⊕ b is table only on this view (Martin's decisions of 2026-11-13): its misfit is not drawn at all.
    assert mis["eFits"]["bQuad"]["drawable"] is False and not mis["eBQuad"] and not base["eBQuad"]
    n_full, n_faded = fb_mis["eLineOpacity"]["network:a"]
    b_full, b_faded = mis["eLineOpacity"]["network:b"]
    assert n_faded < n_full and b_faded < b_full
    # The main panel: the solid part and its dashed extrapolation fade together; the base draws them at full strength.
    for faded, full, parts, base_parts in ((n_faded, n_full, fb_mis["eNA"], fb["eNA"]), (b_faded, b_full, mis["eB"], base["eB"])):
        assert {p["id"].split("|")[2] for p in parts} == {"solid", "dashed"}
        assert all(p["opacity"] == pytest.approx(faded) for p in parts)
        assert all(p["opacity"] == pytest.approx(full) for p in base_parts)
        assert all(MISFIT_TEXT in _plain(p["tip"]) for p in parts)
        assert not [p for p in base_parts if "does not describe" in (p["tip"] or "")]
    # No band at any strength (single-curve round).
    for case in (base, mis, fb, fb_mis):
        assert case["eBands"] == [] and not case["eABand"] and not case["eBBand"] and not case["eBEdges"]
        assert not case["eBRatioBand"] and not case["eARatioBand"]
    # The ratio panel: the network A's a₀/√E divided by its deposit's noise reference, and the network B's noise fit
    # divided by its deposit's, faded, their tips saying why.
    for parts, faded in ((fb_mis["eNARatio"], n_faded), (mis["eBRatio"], b_faded)):
        assert parts and all(p["opacity"] == pytest.approx(faded) and MISFIT_TEXT in _plain(p["tip"]) for p in parts)
    # The end labels' key strokes draw the curve as it is drawn, faded.
    for case, faded_keys in ((mis, {("network:b", "noise"): b_faded}), (fb_mis, {("network:a", "pinned"): n_faded})):
        keyed = [x for panel in ("main", "ratio") for x in case["endLabels"][panel] if (x["key"], x["form"]) in faded_keys]
        assert keyed and all(x["stroke"]["opacity"] == pytest.approx(faded_keys[(x["key"], x["form"])]) for x in keyed)
        assert all(x["stroke"]["width"] == (1 if x["form"] == "pinned" else 1.6) for x in keyed)


def test_res_no_fit_sets_the_ratio_range(out):
    """The ratio panel's k follows the windows alone (Martin, 2026-11-11). A drawn pinned fit with a₀ × 4 (the network
    A's a₀/√E fallback since the single-curve round, the deposit A's being tabled beside its noise curve), a misfit or
    not, leaves k the base's; its ratio lies beyond [1/k, k] and is clipped with a caret, its true values and a count.
    Since review-ui F5 (19f6ab2) the fallback's ratio takes the entry treatment, as the noise fit's does: starting
    above the axis at 4 GeV, it comes into it as E rises (formerly a cut "leaving" at 4 GeV), one caret there."""
    k = out["resMisfit"]["ratioK"]
    rule = ("the ratio range follows the windows of N ≥ 20 from 2 GeV alone; a fit summarises its windows, so no fit ratio "
            "sets it.")
    for case in ("misfit", "unflagged"):
        got = k[case]
        assert got["k"] == k["base"] and got["provisional"] is False, case
        assert (got["cut"] or got["entry"]) and got["fits"] >= 1, case
        # The a₀ × 4 ratio starts above k at 4 GeV and comes in as E rises: an entry, never a cut at its first row.
        e, (e0, r0) = got["entry"], got["firstRow"]
        assert e0 == got["curveMin"] == 4 and r0 > got["k"], case
        assert e["dir"] == "up" and e["whole"] is False and e["peak"] == [e0, r0] and e0 < e["at"] < got["xMax"], case
        assert got["cut"] is None and got["fits"] == 1 and not got["carets"], case
        (tip,) = got["entryCarets"]
        tip = _plain(tip)
        assert (f"The ratio of the origin-pinned fit a₀/√E ⊕ 0 to shower A's deposit a/√E ⊕ b ⊕ c/E fit comes into the "
                f"ratio axis (1/4 to 4) from above at E = ") in tip and "scanning up in E from 4 GeV, where it reads" in tip, case
        assert "a/√E ⊕ b ⊕ c/E fit to" not in tip, "the entry names the fallback's own form"
        assert rule in tip, case
        # The curve's own ratio tooltip says where it comes in, from 4 GeV (not "from 0").
        assert got["ratioRuns"] >= 1 and got["ratioTips"]
        assert all("It comes into the ratio axis from beyond it as E rises from 4 GeV: the caret there says where." in _plain(t)
                   for t in got["ratioTips"]), case
        for t in got["carets"]:
            assert "True values where it deviates most" in t and rule in _plain(t), case
        clipped = [x for x in _lines(got["notes"], out, "disclosures") if x.startswith("Clipped at the ratio axis")]
        assert len(clipped) == 1 and re.search(r"\b\d+ fitted curves?\b", clipped[0]), (case, clipped)


def test_res_the_drawer_names_each_misfit_with_s_and_chi2(out):
    base, mis = out["resMisfit"]["base"], out["resMisfit"]["mis"]
    dis = _lines(mis["notes"], out, "disclosures")
    (line,) = [x for x in dis if "drawn faded because" in x]
    assert line.startswith("1 fit is drawn faded because its form does not describe its windows: ν ≥ 1 and S = √(χ²/ν) > 5, "
                           "the residuals averaging more than 5 of the windows' own standard errors, so it never sets a range: ")
    assert "Shower A · Calibrated deposit c·E_dep — linear-sum benchmark, origin-pinned fit a₀/√E (S = 8, χ²/ν = 64)" in line
    assert "The size of the misfit decides, not the χ² p-value" in line
    dis_e = _lines(mis["notesE"], out, "disclosures")
    (line_e,) = [x for x in dis_e if "drawn faded because" in x]
    # One curve per series (single-curve round): the deposit A's a₀/√E is tabled beside its noise curve, and the
    # quadrature fit is tabled only, so only the drawn noise curve is in the line.
    assert line_e.startswith("1 fit is drawn faded because its form does not describe its windows")
    assert "Shower B · Energy network · absolute frame, a/√E ⊕ b ⊕ c/E fit (S = 8, χ²/ν = 64)" in line_e
    assert "origin-pinned" not in line_e and "quadrature fit a/√E ⊕ b" not in line_e
    # The drawn a₀/√E fallback, a misfit, is named there.
    (line_fb,) = [x for x in _lines(out["resMisfit"]["fbMis"]["notesE"], out, "disclosures") if "drawn faded because" in x]
    assert line_fb.startswith("1 fit is drawn faded because its form does not describe its windows")
    assert "Shower A · Energy network · absolute frame, origin-pinned fit a₀/√E ⊕ 0 (S = 8, χ²/ν = 64)" in line_fb
    for n in (base["notes"], base["notesE"]):
        assert not [x for x in _lines(n, out, "disclosures") if "drawn faded because" in x]


def test_res_a_fit_above_the_windows_top_gets_its_caret_true_values_and_count(out):
    """Tops set by the windows alone (a clone of the two-shower payload): every fit line or band above is clipped. On
    the 1/√E view the lines that leave the top are cut with a caret, their true values and a count. On the E view (one
    curve per series since the single-curve round, its line alone) every drawn curve falls with E, so none leaves the
    top: a noise curve comes down into the plot from it, and so, since review-ui F5 (19f6ab2), does the deposit B's
    a₀/√E fallback on a copy without its noise fit, at E = (a₀/y.hi)², with an entry caret and the drawer's line
    (fa85fe8), where it was formerly cut at 4 GeV as a curve "leaving" the top."""
    lt = out["resMisfit"]["lowTop"]
    payload = {s["key"]: s for s in _load("res_scaling_two")["series"]}
    # The 1/√E view: its lines and bands leave the top, each cut.
    hi, got = lt["yhi"], lt["linear"]
    above = [f for f in got["fits"] if f["form"] != "noise" and f["peak"] > hi]
    assert above and [f for f in above if not f["provisional"]], "a robust fit leaves a top the windows set"
    assert all(f["cut"] for f in above) and not [f for f in got["fits"] if f["cut"] and f["peak"] <= hi]
    assert got["clipped"]["fits"] == len(above)
    tips = [_plain(t) for t in got["tips"] if "leaves the top of the" in t]
    assert len(tips) == len(above) and all("True values" in t for t in tips)
    rule = "Clipped, not rescaled: the range follows the windows of N ≥ 20 alone; a fit summarises its windows, so no line, curve or band sets it."
    assert all(rule in t for t in tips), tips
    assert not [t for t in tips if "fitted lines through them" in t or "fitted curves over their windows" in t]
    (leave,) = [x for x in _lines(lt["notes"], out, "disclosures") if "the top of the" in x and "line or band, each clipped there" in x]
    assert leave.endswith("The range follows the windows alone, so no line or band sets it.")

    # The E view.
    hi, got = lt["ehi"], lt["energy"]
    # Its rows are [E, y]: its peak is its line's (no band), and nothing carries a band entry.
    assert all(f["rowWidth"] == [2] and f["peak"] == f["linePeak"] for f in got["fits"])
    assert all(f["entry"] is None or f["entry"]["retired"] == [] for f in got["fits"])
    p_of = lambda f: payload[f["key"]]["fits"]["all"]["noise"]["params"]  # noqa: E731
    # a/√E ⊕ b ⊕ c/E rises without bound as E → 0 (Martin's decisions of 2026-11-13): it comes down into the plot
    # rather than leaving it, each with its own caret, counted apart (clipped.entries). A flat curve (A = C = 0) does
    # not come down, and with no band nothing of it enters either.
    entering = [f for f in got["fits"] if f["form"] == "noise" and (p_of(f)["a2"] > 0 or p_of(f)["c2"] > 0)
                and p_of(f)["b2"] < hi * hi]
    flat = [f for f in got["fits"] if f["form"] == "noise" and p_of(f)["a2"] == 0 and p_of(f)["c2"] == 0]
    assert all(f["entry"] is None for f in flat)
    assert not [t for t in got["tips"] if "band" in _plain(t)]
    assert entering and sum(_plain(t).startswith(tuple(f"{payload[f['key']]['label']} It comes down into the plot at E = " for f in entering))
                            for t in got["tips"]) == len(entering)
    # The fallback a₀/√E of the deposit B starts above the top at 4 GeV and comes down at E = (a₀/y.hi)².
    (fb,) = [f for f in got["fits"] if f["form"] == "pinned"]
    a0 = payload["detector:b"]["fits"]["all"]["pinned"]["params"]["a0"]
    assert fb["key"] == "detector:b" and a0 / 2 > hi, "it starts above the top at 4 GeV"
    assert fb["entry"]["above"] is False and fb["entry"]["lineAt"] == pytest.approx((a0 / hi) ** 2, rel=1e-12)
    assert fb["cut"] is None and fb["linePeak"] == pytest.approx(hi, rel=1e-9), "drawn from where it meets the top"
    assert got["clipped"]["entries"] == len(entering) + 1
    fb_tips = [_plain(t) for t in got["tips"] if "The origin-pinned a₀/√E comes down into the plot at E = " in t]
    assert fb_tips == [f"{payload['detector:b']['label']} The origin-pinned a₀/√E comes down into the plot at E = "
                       f"{fb['entry']['lineAt']:.3g} GeV: it falls as 1/√E, so from 4 GeV up to that energy it lies above "
                       f"the top of the axis (0 to {hi:g}%)."]
    # Every drawn curve falls with E, so none leaves the top after entering, on the clone or on the recording.
    assert not [f for f in got["fits"] if f["cut"]] and got["clipped"]["fits"] == 0
    assert not [t for t in got["tips"] if "leaves the top of the" in t]
    rec = got["recording"]
    assert not [f for f in rec["fits"] if f["cut"]] and rec["clipped"]["fits"] == 0
    assert not [f for f in rec["fits"] if f["form"] == "pinned"], "on the recording every series draws its noise curve"
    # The drawer names the fallback's entry (fa85fe8) and says nothing leaves the top.
    dis_e = _lines(lt["notesE"], out, "disclosures")
    assert not [x for x in dis_e if "the top of the main panel, each clipped there" in x]
    assert (f"{payload['detector:b']['label']}: its origin-pinned a₀/√E comes down into the main panel from its top ({hi:g}%) at "
            f"E = {fb['entry']['lineAt']:.3g} GeV, with a caret there: it falls as 1/√E, so from 4 GeV up to that energy it "
            "lies above the top.") in dis_e


def test_res_the_drawers_say_the_windows_alone_set_the_range(out):
    stale = ("non-provisional fits", "lines fitted through them", "fitted lines through them", "and the fits through them",
             "fitted curves over their windows")
    for key, rec in out["resMisfit"]["fixtures"].items():
        lin_dis = _lines(rec["linear"], out, "disclosures")
        e_dis = _lines(rec["energy"], out, "disclosures")
        if rec["provisional"]:
            assert any(x.startswith("The y range is provisional") and x.endswith("; no fit sets it.") for x in lin_dis), key
        else:
            assert ("The y range follows the windows with N ≥ 20 (whiskers included) alone, from zero: a fit summarises its "
                    "windows and is not more evidence, so no fitted line or band sets it.") in lin_dis, key
        if not rec["provisionalE"]:
            # No band on the E view since the single-curve round, so the sentence names no band.
            assert ("The y range follows the windows alone, from zero: those with N ≥ 20 from 2 GeV, whiskers included. A fit "
                    "summarises its windows and is not more evidence, so no fitted curve or extrapolation sets it; a window "
                    "below 2 GeV never sets it, whatever its N.") in e_dis, key
        # The ratio range: the windows alone, against a reference neither provisional nor a misfit; no fit sets it.
        ratio = [x for x in e_dis if x.startswith("The ratio range, ")]
        assert len(ratio) == 1 and ratio[0].endswith("no fit sets it."), key
        assert "neither provisional nor of a form that does not describe its windows" in ratio[0], key
        assert ("follows the windows alone" in ratio[0]) or ("is provisional" in ratio[0]), key
        assert not [x for x in e_dis + _lines(rec["energy"], out, "drawn") if "drawn unfaded" in x], key
        assert any("that covers the robust ratio marks, the windows alone" in x and "No fitted curve sets it: a curve's ratio that "
                   "leaves the axis is clipped there with a caret." in x for x in _lines(rec["energy"], out, "drawn")), key
        # Faded fits in the legend of either view; no fit sets either range.
        assert any("A fit drawn faded, its line and its band alike, is provisional (fewer than two windows of N ≥ 20) or of a form "
                   "that does not describe its windows (S > 5); no fit, faded or not, sets the range." == x
                   for x in _lines(rec["linear"], out, "legend")), key
        assert any("A fit drawn fainter, its curve and dashed extrapolation alike, is provisional or of a form that does not "
                   "describe its windows (S > 5); no fit, faded or not, sets either panel's range." in x
                   for x in _lines(rec["energy"], out, "legend")), key
        # The 1/√E view's bands: the outline rule stated in the legend.
        assert any("A band that spans half its axis or more over its fitted windows (their momentum edges, mapped by x = 1/√E) is "
                   "drawn as two thin solid edges in the series' colour, never as a wash; this view marks no extrapolation, so the edges "
                   "are not dashed beyond those windows." in x
                   for x in _lines(rec["linear"], out, "legend")), key
        # No sentence the drawer writes itself says a fit sets the range (the server's own notes are held in Python).
        for n in (rec["linear"], rec["energy"]):
            owned = _lines(n, out, "disclosures") + _lines(n, out, "legend")
            assert not [x for x in owned for s in stale if s in x], key
        # A misfit is disclosed exactly where one is drawn.
        assert any("drawn faded because" in x for x in lin_dis) == bool(rec["misfits"]), key
        assert any("drawn faded because" in x for x in e_dis) == bool(rec["misfitsE"]), key


def test_res_misfit_no_rendered_number_uses_an_ascii_hyphen(out):
    m = out["resMisfit"]
    for case in (m["mis"], m["lowTop"]):
        for key in ("notes", "notesE"):
            _no_hyphen_numbers(line for lines in case[key]["sections"].values() for line in lines)
    _no_hyphen_numbers(_plain(x["tip"]) for x in m["mis"]["eA"] + m["mis"]["eB"] + m["mis"]["eARatio"] + m["mis"]["linearLines"])
    _no_hyphen_numbers(_plain(t) for view in ("linear", "energy") for t in m["lowTop"][view]["tips"])


# ------------------- res-scaling: the lead's follow-ups (2026-11-11): k, the misfit reference, the 1/√E outline --

def test_res_a_ratio_against_a_misfit_reference_is_not_robust(out):
    """As against a provisional reference (P10): each shower's deposit without an a/√E ⊕ b ⊕ c/E fit (its noise_reason
    served), so the reference falls back to its a₀/√E fit from 4 GeV, a misfit. No ratio mark sets k, which turns
    provisional and says so; the drawer, the 1.0 rule and every ratio mark's tooltip name the reference's S (its own
    band about 1, which did too, is retired: Martin's directive of 2026-11-15). The same holds where the deposits' noise fits, the reference by default, are the misfits."""
    got = out["resMisfit"]["misfitRef"]
    mis, calm, noise = got["misfit"], got["calm"], got["noise"]
    for case, want in ((mis, True), (calm, False)):
        assert [(r["form"], r["misfit"], r["provisional"]) for r in case["refs"]] == [("pinned", want, False)] * 2
    # The a₀/√E fallback (Martin's decisions of 2026-11-13): from 4 GeV, its why giving the server's noise_reason.
    reason = got["noReason"].removeprefix("No a/√E ⊕ b ⊕ c/E fit: ").removesuffix(".")
    for case in (mis, calm):
        lines = [x for x in _lines(case["notes"], out, "drawn") if x.startswith(("Shower A: the ratio divides", "Shower B: the ratio divides"))]
        assert len(lines) == 2 and all(f"its deposit's a₀/√E fit" in x and f"since it has no a/√E ⊕ b ⊕ c/E fit ({reason})" in x
                                       and x.endswith("so a window gets a ratio mark from 4 GeV.") for x in lines), lines
    assert [(r["form"], r["misfit"], r["provisional"]) for r in noise["refs"]] == [("noise", True, False)] * 2
    assert not any(noise["robust"]) and noise["provisional"] is True and noise["axisName"].endswith("— provisional")
    named_noise = [x for x in _lines(noise["notes"], out, "disclosures") if "does not describe its windows (S = 8 > 5, χ²/ν = 64)" in x]
    assert [x.split(" does not")[0] for x in named_noise] == ["Shower A's reference, its deposit's a/√E ⊕ b ⊕ c/E fit,",
                                                               "Shower B's reference, its deposit's a/√E ⊕ b ⊕ c/E fit,"]
    for tips in ("pointTips", "unityTip"):
        assert noise[tips] and all("The reference, shower " in _plain(t) and "a/√E ⊕ b ⊕ c/E fit, does not describe its windows: S = 8 > 5"
                                   in _plain(t) for t in noise[tips]), tips
    # The same windows are robust as windows; against the misfit reference none of their ratios is.
    assert mis["windowsRobust"] == calm["windowsRobust"] and any(mis["windowsRobust"])
    assert not any(mis["robust"]) and any(calm["robust"])
    assert mis["provisional"] is True and calm["provisional"] is False
    assert mis["axisName"].endswith("— provisional") and not calm["axisName"].endswith("— provisional")
    text = ("does not describe its windows: S = 8 > 5 (χ²/ν = 64), so a ratio against it is not robust and never sets the "
            "ratio range.")
    for tips in ("pointTips", "unityTip"):
        assert mis[tips] and all(text in _plain(t) for t in mis[tips]), tips
        assert not [t for t in calm[tips] if "does not describe its windows" in t], tips
    # The reference's own band about 1, which said it too, is retired with every band of this view (2026-11-15).
    assert mis["referenceTips"] == [] and calm["referenceTips"] == [] and noise["referenceTips"] == []
    dis = _lines(mis["notes"], out, "disclosures")
    named = [x for x in dis if "does not describe its windows (S = 8 > 5, χ²/ν = 64)" in x]
    assert [x.split(" does not")[0] for x in named] == ["Shower A's reference, its deposit's a₀/√E fit,",
                                                         "Shower B's reference, its deposit's a₀/√E fit,"]
    assert all("so none of them sets the ratio range" in x for x in named)
    (ratio,) = [x for x in dis if x.startswith("The ratio range, ")]
    assert "is provisional: no window of N ≥ 20 from 2 GeV gives a ratio mark against a reference that is neither provisional " \
           "nor of a form that does not describe its windows" in ratio
    drawn = _lines(mis["notes"], out, "drawn")
    assert sum("a form that does not describe the deposit's windows (S = 8 > 5)" in x for x in drawn) == 2
    # Its only flag is the existing provisional ratio range; no hazard of its own.
    assert set(calm["hazards"]) <= set(mis["hazards"]) and set(mis["hazards"]) - set(calm["hazards"]) == {"provisional ratio range"}


def _band_at(block: dict, x: float) -> tuple[float, float, float]:
    """A fit block's line and 95% band at x = 1/√E, from its params alone (the server's `rfit.band`)."""
    p, q = block["params"], block["band_quantile"]
    if block["form"] == "pinned":
        y, half = p["a0"] * x, q * p["se_a0"] * x
    else:
        y = p["a"] * x + p["b"]
        half = q * max((x * p["se_a"]) ** 2 + 2 * p["rho_ab"] * x * p["se_a"] * p["se_b"] + p["se_b"] ** 2, 0) ** 0.5
    return y, y - half, y + half


@pytest.mark.parametrize("name", RES)
def test_res_the_linear_bands_follow_the_outline_rule(out, name):
    """The 1/√E view's affine and pinned bands are outlined exactly where, at some x of the fitted windows' momentum edges
    mapped by x = 1/√E, the part of the band inside the axis covers half of it or more: re-derived from the payload."""
    payload = _load(name)
    for key in RES_KEYS:
        windows, shower = key.split(":")
        model = {s["key"]: s for s in out["res"][name]["models"][key]["series"]}
        top = out["res"][name]["models"][key]["y"]["hi"]
        for s in _res_shown(payload, shower):
            mf = s["fits"][windows]
            span = mf["span_gev"]
            for form in ("affine", "pinned"):
                block = mf[form]
                if block is None:
                    continue
                got = model[s["key"]]["fits"][form]
                x_span = [1 / span[1] ** 0.5, 1 / span[0] ** 0.5]
                assert got["span"] == span and got["xSpan"] == pytest.approx(x_span)
                rows = [(c[0], c[2], c[3]) for c in block["curve"] if x_span[0] - 1e-9 <= c[0] <= x_span[1] + 1e-9]
                rows += [(x, lo, hi) for x in x_span for _, lo, hi in [_band_at(block, x)]]
                want = any(min(hi, top) - max(lo, 0.0) >= 0.5 * top for _, lo, hi in rows)
                assert got["outlined"] is want, (name, key, s["key"], form)


def test_res_a_wide_linear_band_is_drawn_as_its_edges(out):
    """A ν = 1 affine band at t₀.₉₇₅,₁ = 12.71: two thin edges in the series' colour, solid along the whole axis (the 1/√E
    view marks no extrapolation, and its dash is shower B's), clipped to the plot; no wash; its line, its edges and the
    drawer say why; no hazard of its own."""
    o = out["resMisfit"]["outline"]
    assert o["outlined"] is True and o["baseOutlined"] is False and o["bands"] == 0
    x_lo, x_hi = o["xSpan"]
    assert (x_lo, x_hi) == pytest.approx((1 / o["span"][1] ** 0.5, 1 / o["span"][0] ** 0.5))
    assert {e["id"].split("|")[-2] for e in o["edges"]} == {"solid"}, "no dash on the 1/√E view"
    xs = [x for e in o["edges"] for x, _ in e["points"]]
    assert min(xs) < x_lo - 1e-6, "the edges run on past the fitted windows, undashed"
    why = ("Its 95% band spans half its axis or more over its fitted windows (S = 1.5, ν = 1, q = 12.71), so it is drawn as its "
           "edges, not as a wash.")
    for e in o["edges"]:
        part = e["id"].split("|")[-2]
        assert e["name"] == o["label"] and e["stroke"] == o["colour"]
        assert e["width"] == pytest.approx(0.8 * o["lineAxis"]) and e["opacity"] == pytest.approx(o["edgeOpacity"])
        assert part == "solid" and e["dash"] is None
        for x, y in e["points"]:  # identity coordinates
            assert 0 < y <= o["yhi"] + 1e-9
        tip = _plain(e["tip"])
        assert why in tip and "95% confidence band of the affine fit" in tip
        assert "Extrapolated" not in tip
    assert why in _plain(o["lineTip"]) and "The shaded band beside it" not in o["lineTip"]
    (listed,) = [x for x in _lines(o["notes"], out, "disclosures") if "never as a wash: " in x]
    n = o["outlinedCount"]
    assert n >= 1 and listed.startswith(
        f"{n} band{'s' if n > 1 else ''} span{'' if n > 1 else 's'} half {'their' if n > 1 else 'its'} axis or more at some x over "
        f"the fitted windows, so {'they are' if n > 1 else 'it is'} drawn as two thin solid edges in the series' colour, never "
        "as a wash: ")
    assert "Shower B · Energy network · absolute frame, affine fit a/√E + b (S = 1.5, ν = 1, q = 12.71)" in listed
    assert o["hazards"] == o["hazardsBase"], "no hazard of its own"
    assert out["resMisfit"]["xSpans"] == [pytest.approx([1 / 20 ** 0.5, 1 / 5 ** 0.5]), pytest.approx([0.4472136, 0.5]), None, None]


# ------------------------------------------- res-scaling: the three estimators --
# Martin's decisions of 2026-11-12 (brief section 4): an Estimator control, Median |rel. err.| by default, Robust σ
# (IQR) and Sample σ/μ. The window tooltips name the plotted value with its interval and weight, the median
# response, the two estimators not plotted and the tail share; the median's literature disclosure appears in the E
# view's note band, every literature-curve tooltip, every ratio tooltip against a literature curve and the drawer,
# and the Details hazard "median rel. against σ/E curve" with it, exactly there and never under robust or sample;
# perf-bins' energy Median rel. reconciles itself with the card.

RES_KINDS = ["two", "xgb", "single_hits", "single_events"]
RES_EST = {**{f"res_scaling_median_{k}": "median" for k in RES_KINDS},
           **{f"res_scaling_robust_{k}": "robust" for k in RES_KINDS},
           **{f"res_scaling_{k}": "sample" for k in RES_KINDS}}
#: The E view's literature states: none, either curve, both (the card's default).
RES_LIT = {"none": [], "pi": ["pi"], "e": ["e"], "both": ["pi", "e"]}
PERF_ALL = ["perf_two_energy", "perf_two_angle", "perf_xgb_energy", "perf_xgb_angle"]
RES_HAZARD = "median rel. against σ/E curve"
#: brief-fix.md (R-ui n5), verbatim: it names the card's section, whose card is titled by its estimator.
PERF_RECONCILIATION = ("Median rel. is median |pred − true| / true, not a σ: for unbiased Gaussian errors it is "
                       "0.6745·σ/E. The card of the Energy resolution section plots the same number by default "
                       "(Median |rel. err.|) and offers a robust σ/E (IQR) of the same showers for a σ-scaled comparison.")
#: The tooltip takes the first sentence only.
PERF_NOT_SIGMA = PERF_RECONCILIATION[:PERF_RECONCILIATION.index(" The card of the Energy resolution section")]

_EST_BODY = r"""
const est = { fixtures: {}, perf: {} };
const RE = { width: 760, height: 600 };
const LW = { width: 760, height: 420 };
const packN = (n) => (n ? { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
  sections: Object.fromEntries(n.sections.map((s) => [s.heading, s.lines])) } : null);
// Every tooltip of an option, by series: its name, its grid (0 the main panel, 1 the ratio panel) and its texts.
const tipsOf = (o) => o.series.map((s) => ({ name: s.name ?? '', id: s.id ?? null, grid: s.xAxisIndex ?? 0,
  tips: (s.data ?? []).map((d, i) => (typeof s.tooltip?.formatter === 'function'
    ? s.tooltip.formatter({ dataIndex: i, value: Array.isArray(d) ? d : d?.value }) : null)).filter(Boolean) }));
const graphicsOf = (o) => (o.graphic ?? []).map((g) => g.style?.text).filter(Boolean);
// The fit table's caption and every cell, the windows column included.
const tableOf = (t) => (t ? [t.caption, ...t.rows.flatMap((r) => [r.label, r.windows, ...r.fits.flatMap((f) => f.cells)])] : []);
const pointsOf = (m, tip) => m.series.flatMap((s) => s.points.map((p) => ({ key: s.key, source: s.raw.source, shower: s.raw.shower ?? null,
  bin: p.w.bin, n: p.w.n, tip: tip(m, s, p) })));
for (const [name, estimator] of Object.entries(%(est)s)) {
  const payload = load(name);
  const entry = { linear: {}, energy: {} };
  for (const windows of ['anchors', 'all']) {
    const opts = { windows, shower: 'both', estimator, palette: 'viridis', card: 'res-scaling' };
    const opt = rs.resolutionScalingOption(payload, opts, LW);
    entry.linear[windows] = {
      points: pointsOf(rs.resolutionModel(payload, opts), rs.pointTip), series: tipsOf(opt), graphics: graphicsOf(opt),
      notes: packN(mn.resolutionScalingNotes({ payload, windows, shower: 'both' })),
      hazards: mn.modelsHazards(payload, 'res-scaling', { windows, shower: 'both', view: 'linear', literature: ['pi', 'e'] }),
      table: tableOf(rs.fitTableRows(payload, { windows, shower: 'both' })),
    };
    for (const [lit, literature] of Object.entries(%(lit)s)) {
      const eo = { view: 'energy', windows, shower: 'both', literature, estimator, palette: 'viridis', card: 'res-scaling' };
      const model = rs.energyModel(payload, eo);
      const built = rs.energyViewOption(payload, eo, RE).option;
      entry.energy[`${windows}:${lit}`] = {
        warning: model.noteText.warning, reference: model.reference.key, nLiterature: model.literature.length,
        graphics: graphicsOf(built), series: tipsOf(built),
        literatureTips: model.literature.map((l) => rs.literatureTip(model, l)),
        ratioTips: model.series.flatMap((s) => s.points.filter((p) => p.ratio.drawn).map((p) => rs.ratioPointTip(model, s, p))),
        pointTips: pointsOf(model, rs.energyPointTip),
        notes: packN(mn.resolutionScalingNotes({ payload, view: 'energy', windows, shower: 'both', literature })),
        hazards: mn.modelsHazards(payload, 'res-scaling', { view: 'energy', windows, shower: 'both', literature }),
        table: tableOf(rs.fitTableRows(payload, { view: 'energy', windows, shower: 'both' })),
        // a/√E ⊕ b ⊕ c/E per series (Martin's decisions of 2026-11-13): where it comes down into the plot, its caret's count.
        noise: model.series.map((s) => ({ key: s.key, label: s.label, drawable: s.fits.noise?.drawable ?? false,
          entry: s.fits.noise?.entry ?? null,
          retired: ['band', 'outlined', 'edges', 'floorCut', 'envelope', 'singular'].filter((k) => s.fits.noise && k in s.fits.noise) })),
        clipped: model.clipped, yhi: model.y.hi,
      };
    }
  }
  est.fixtures[name] = entry;
}
// perf-bins: every quantity of every task, its tooltips and its drawer.
for (const name of %(perf)s) {
  const payload = load(name);
  est.perf[name] = Object.fromEntries(perf.perfQuantities(payload).map((q) => {
    const m = perf.perfModel(payload, { quantity: q.key });
    return [q.key, { task: m.model, energyMedian: perf.isEnergyMedianRel(m),
      tips: m.series.flatMap((x) => x.points.map((pt) => perf.perfTip(m, x, pt))),
      notes: packN(mn.perfBinsNotes({ payload, quantity: q.key })) }];
  }));
}
est.perfConsts = { notSigma: perf.MEDIAN_REL_NOT_SIGMA, reconciliation: perf.MEDIAN_REL_RECONCILIATION };
est.decomposition = { panel: rs.RES_DECOMPOSITION ?? null, notes: mn.RES_DECOMPOSITION ?? null };
console.log(JSON.stringify(est));
"""


@pytest.fixture(scope="module")
def est() -> dict:
    """The estimator harness: the panel's helpers and builders of `_SCRIPT`, then `_EST_BODY`."""
    prelude = _script()
    prelude = prelude[:prelude.index("const out = { perf")]
    body = _EST_BODY % {"est": json.dumps(RES_EST), "lit": json.dumps(RES_LIT), "perf": json.dumps(PERF_ALL)}
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", prelude + body, args],
                          capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _js_round(v: float, d: int) -> tuple[Decimal, int]:
    """JavaScript's `toPrecision(d)`: the exact binary value rounded half away from zero (Python's format rounds
    half to even, so 216.5 is "216" there and "217" here), as (mantissa in [1, 10), exponent)."""
    x = Decimal(v)
    exponent = x.copy_abs().adjusted()
    quantum = Decimal(1).scaleb(1 - d)
    m = x.scaleb(-exponent).quantize(quantum, rounding=ROUND_HALF_UP)
    if abs(m) >= 10:
        m, exponent = (m / 10).quantize(quantum, rounding=ROUND_HALF_UP), exponent + 1
    return m, exponent


def _sf(v: float, d: int = 3) -> str:
    """chart_panel.js `sigFigs(v, d)`: plain from 10⁻³ to 10⁵, else m×10ⁿ; U+2212 for a negative."""
    if v == 0:
        return "0"
    m, exponent = _js_round(v, d)
    if 1e-3 <= abs(v) < 1e5:
        text = f"{float(m.scaleb(exponent)):.15g}"
    else:
        text = f"{float(m):g}×10{str(exponent).translate(_SUPERSCRIPT)}"
    return text.replace("-", "−")


def _pc(v) -> str:
    """The panel's percent: three significant figures and %, or an em dash."""
    return "—" if v is None else f"{_sf(v)}%"


def _signed_pc(v: float) -> str:
    return f"{'+' if v > 0 else ''}{_sf(v)}%"


def _windows(payload: dict) -> dict:
    return {(s["key"], w["bin"]): w for s in payload["series"] for w in s["windows"]}


def _warning() -> str:
    return _load("res_scaling_median_two")["estimator"]["literature"]["warning"]


def _every_text(entry: dict):
    """Every tooltip, canvas text, fit-table caption and cell, and drawer line one fixture's harness entry produced."""
    for view in ("linear", "energy"):
        for e in entry[view].values():
            for s in e["series"]:
                yield from s["tips"]
            yield from e["graphics"]
            yield from e.get("table", [])
            yield from (p["tip"] for p in e.get("points", e.get("pointTips", [])))
            yield from e.get("literatureTips", [])
            yield from e.get("ratioTips", [])
            for lines in e["notes"]["sections"].values():
                yield from lines
            yield e["notes"]["title"]


def test_res_est_the_median_fixtures_carry_the_disclosure_and_the_others_none():
    for name, estimator in RES_EST.items():
        block = _load(name)["estimator"]
        assert block["name"] == estimator
        assert block["literature"]["drawn"] is True
        assert (block["literature"]["warning"] is not None) == (estimator == "median"), name
    assert _warning().startswith("Note: comparing Median |rel. err.| against a σ/E literature curve")


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_value_line_names_the_estimator_and_its_interval(est, name):
    """Median: "Median rel. = …, 95% bootstrap interval […]", order-statistic below N = 20 by the window's own
    method; robust: "Robust σ/E = …, 95% bootstrap interval […]"; sample: the χ² interval, as ever."""
    estimator = RES_EST[name]
    windows = _windows(_load(name))
    points = [p for v in est["fixtures"][name]["linear"].values() for p in v["points"]]
    assert points
    for p in points:
        w = windows[(p["key"], p["bin"])]
        tip = _plain(p["tip"])
        ci = w["ci95"] if w["ci95"] and all(x is not None for x in w["ci95"]) else None
        if estimator == "median":
            interval = {"order_statistic": "order-statistic", "bootstrap_percentile": "bootstrap"}[w["method"]] if ci else None
            line = f"Median rel. = {_pc(w['value'])}" + (f", 95% {interval} interval [{_pc(ci[0])}, {_pc(ci[1])}]" if ci else "")
        elif estimator == "robust":
            assert w["method"] == "bootstrap_percentile" and ci
            line = f"Robust σ/E = {_pc(w['value'])}, 95% bootstrap interval [{_pc(ci[0])}, {_pc(ci[1])}]"
        else:
            line = f"σ/E = {_pc(w['value'])}" + (f", 95% χ² interval [{_pc(ci[0])}, {_pc(ci[1])}]" if ci else "")
        assert line in tip, (name, p["key"], p["bin"], tip)
        if estimator != "sample":
            lines = [_plain(x) for x in p["tip"].split("<br/>")]
            assert not any(x.startswith("σ/E = ") for x in lines), "no σ/E value line under the median or robust width"


def test_res_est_the_median_quotes_its_order_statistic_interval_below_n_twenty(est):
    """The order-statistic branch is exercised: a median window of 6 ≤ N < 20 names it."""
    seen = 0
    for name, estimator in RES_EST.items():
        if estimator != "median":
            continue
        windows = _windows(_load(name))
        for p in (p for v in est["fixtures"][name]["linear"].values() for p in v["points"]):
            w = windows[(p["key"], p["bin"])]
            if w["method"] == "order_statistic":
                assert w["n"] < 20 and "95% order-statistic interval [" in _plain(p["tip"])
                seen += 1
            elif w["method"] == "bootstrap_percentile":
                assert w["n"] >= 20 and "95% bootstrap interval [" in _plain(p["tip"])
    assert seen > 0


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_se_line_names_the_weight(est, name):
    """Under the median and robust widths (brief-fix F1, F3): the bootstrap SE with its measured κ and the series'
    pooled scale c of the weight se = c·ŷ/√N, or, for a tied window (κ below the floor), the SE and "no fit weight";
    never a window's own κ applied at the fitted value. The delta-method SE under the sample width, as ever."""
    estimator = RES_EST[name]
    payload = _load(name)
    assert payload["estimator"]["weight"]["method"] == ("delta" if estimator == "sample" else "kappa")
    windows = _windows(payload)
    scale = {s["key"]: s["weight_scale"] for s in payload["series"]}
    for p in (p for v in est["fixtures"][name]["linear"].values() for p in v["points"]):
        w = windows[(p["key"], p["bin"])]
        tip = _plain(p["tip"])
        if estimator == "sample":
            assert w["se_rel"] is None and scale[p["key"]] is None
            if w["se_delta"] is not None:
                assert (f"delta-method SE {_pc(w['se_delta'])} (R̄'s error included): the fit weight 1/se², "
                        "recomputed at the fitted value") in tip
            assert "κ =" not in tip and "bootstrap SE" not in tip
        else:
            assert w["se_delta"] is None and "delta-method" not in tip
            ws = scale[p["key"]]
            # One pooled scale (Martin's directive of 2026-11-15): `weight_scale` is {c, n_windows, rule}.
            assert ws is not None and set(ws) == {"c", "n_windows", "rule"}
            assert w["p_lo"] >= 4, "the 1/√E view draws no window below 4 GeV"
            assert "c_low" not in tip
            assert "applied at the fitted value" not in tip and "its relative SE κ" not in tip
            if w["se"] is None:
                assert "bootstrap SE" not in tip
            elif w["se_rel"] is None:
                assert f"bootstrap SE {_pc(w['se'])}: below 10⁻⁶ of the value (tied replicates), so no fit weight" in tip
                assert "κ =" not in tip
            elif ws["c"] is not None:
                assert (f"bootstrap SE {_pc(w['se'])} (κ = {_sf(100 * w['se_rel'])}%); fit weight se = c·ŷ/√N, "
                        f"c = {_sf(ws['c'])} for this series") in tip, (name, p["key"], p["bin"], tip)
            else:
                assert (f"bootstrap SE {_pc(w['se'])} (κ = {_sf(100 * w['se_rel'])}%); no fit weight: no window of this "
                        "series from 4 GeV carries one, so it has no pooled scale c") in tip, (name, p["key"], p["bin"], tip)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_sc_a_window_below_4_gev_prints_its_weight_with_the_one_pooled_c(est, name):
    """FX2, retargeted (Martin's directive of 2026-11-15, one pooled scale): on the E view, which draws the windows of
    1–4 GeV, under the median and robust widths a window below 4 GeV prints its weight with the series' one pooled c,
    "c = … for this series, pooled over its windows from 4 GeV", which it does not enter; a window from 4 GeV
    (4–5 GeV included) prints "c = … for this series"; no tip names c_low; `weight_scale` is {c, n_windows, rule}
    and its rule says the noise fit weights its windows of 1–4 GeV by the same c. Under sample no scale exists and no
    tip names one."""
    estimator = RES_EST[name]
    payload = _load(name)
    windows = _windows(payload)
    scale = {s["key"]: s["weight_scale"] for s in payload["series"]}
    seen = {"low": 0, "high": 0}
    for s in payload["series"]:
        ws = s["weight_scale"]
        if estimator == "sample":
            assert ws is None
            continue
        assert set(ws) == {"c", "n_windows", "rule"}, (name, s["key"])
        if ws["c"] is not None:
            assert ws["rule"].endswith("The a/√E ⊕ b ⊕ c/E fit weights its windows of 1–4 GeV by the same c, which they do "
                                       "not enter."), (name, s["key"])
    for v in est["fixtures"][name]["energy"].values():
        for p in v["pointTips"]:
            w = windows[(p["key"], p["bin"])]
            tip = _plain(p["tip"])
            assert "c_low" not in tip, (name, p["key"], p["bin"])
            if estimator == "sample":
                continue
            ws = scale[p["key"]]
            if w["se"] is None or w["se_rel"] is None or ws["c"] is None:
                continue
            head = f"bootstrap SE {_pc(w['se'])} (κ = {_sf(100 * w['se_rel'])}%); fit weight se = c·ŷ/√N, c = {_sf(ws['c'])} for this series"
            if w["p_lo"] < 4:
                assert (head + ", pooled over its windows from 4 GeV") in tip, (name, p["key"], p["bin"], tip)
                seen["low"] += 1
            else:
                assert head in tip and ", pooled over its windows from 4 GeV" not in tip, (name, p["key"], p["bin"], tip)
                seen["high"] += 1
    if estimator != "sample":
        assert seen["high"] > 0
        # Every median and robust recording with a two-shower or single-shower table draws a window of 1–4 GeV.
        assert seen["low"] > 0, name


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_cross_references_and_the_tail_share(est, name):
    """The signed median response (R-ui n2), the two estimators not plotted in the brief's order (robust, sample,
    median; the deposit's median under c̃), and the share beyond 3 robust σ against 0.27% for a large Gaussian
    sample, reported from N = 300 only (brief-fix F5) and never where the IQR is 0 (F6)."""
    estimator = RES_EST[name]
    payload = _load(name)
    windows = _windows(payload)
    cal = payload["estimator"]["calibration"]["showers"]
    tail_min_n = payload["gates"]["tail_min_n"]
    assert tail_min_n == 300
    names = [("robust", "Robust σ/E"), ("sample", "sample σ/μ"), ("median", "median rel.")]
    signed = lambda v: "—" if v is None else _signed_pc(v)   # noqa: E731
    for p in (p for v in est["fixtures"][name]["linear"].values() for p in v["points"]):
        w = windows[(p["key"], p["bin"])]
        tip = _plain(p["tip"])
        if estimator == "sample":
            if w["median_response"] is not None:
                assert f"median response R̃ − 1 = {signed(w['median_response'])}" in tip
        elif w["median_response"] is not None or w["bias"] is not None:
            assert f"median response R̃ − 1 = {signed(w['median_response'])}; mean bias R̄ − 1 = {signed(w['bias'])}" in tip
        if w["median_response"] is not None and w["median_response"] > 0:
            assert f"R̃ − 1 = +{_sf(w['median_response'])}%" in tip, "a positive median response carries its sign"
        parts = []
        for key, label in names:
            if key == estimator:
                continue
            v = w["alt"].get(key)
            c_median = cal.get(p["shower"] or "a", {}).get("c_median")
            if v is not None:
                parts.append(f"{label} {_pc(v)}" + (f" (c̃·E_dep, c̃ = {_sf(c_median)})"
                                                    if key == "median" and p["source"] == "detector" and c_median is not None else ""))
            elif key == "robust" and w["n"] < 20:
                parts.append(f"{label} not reported below N = 20, the robust floor")
            else:
                parts.append(f"{label} not reported")
        assert f"Not plotted: {'; '.join(parts)}" in tip, (name, p["key"], p["bin"], tip)
        assert "(0.27% for a Gaussian)" not in tip and "share of events beyond 3 robust σ not reported below N = 20" not in tip
        if w["tail_share"] is not None:
            assert w["n"] >= tail_min_n
            assert f"{_pc(w['tail_share'])} of events beyond 3 robust σ (0.27% for a large Gaussian sample)" in tip
        elif w["n"] < tail_min_n:
            assert ("share beyond 3 robust σ not reported below N = 300: a Gaussian sample of fewer events exceeds "
                    "0.27% by chance") in tip, (name, p["key"], p["bin"], tip)
        else:
            assert ("share beyond 3 robust σ not reported: the window's IQR is 0, so there is no robust σ to "
                    "measure it in") in tip, (name, p["key"], p["bin"], tip)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_median_names_its_parity_and_the_deposits_median_calibration(est, name):
    """Under the median a model window is perf-bins' own Median rel. and the deposit is c̃·E_dep; under the two σ
    widths neither line appears."""
    estimator = RES_EST[name]
    payload = _load(name)
    cal = payload["estimator"]["calibration"]["showers"]
    parity = "the Median rel. of Model Error vs. Incident Momentum: the same events, seed and interval"
    for view in ("linear", "energy"):
        for e in est["fixtures"][name][view].values():
            for p in e.get("points", e.get("pointTips")):
                tip = _plain(p["tip"])
                deposit = p["source"] == "detector"
                assert (parity in tip) == (estimator == "median" and not deposit), (name, p["key"])
                c = cal[p["shower"] or "a"]
                line = (f"c̃·E_dep with the median calibration c̃ = {_sf(c['c_median'])} "
                        f"(the ratio of sums c = {_sf(c['c_sum'])})")
                assert (line in tip) == (estimator == "median" and deposit), (name, p["key"])
                assert ("median calibration" in tip) == (estimator == "median" and deposit)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_literature_disclosure_is_exactly_where_the_brief_puts_it(est, name):
    """Under the median with a curve on: one line of the note band, every literature curve's tooltip, every
    tooltip of the ratio panel (whose reference is then a literature curve). Nowhere else, never on the 1/√E view
    and never under robust or sample."""
    estimator = RES_EST[name]
    warning = _warning()
    entry = est["fixtures"][name]
    payload = _load(name)
    for key, e in entry["energy"].items():
        windows, lit = key.split(":")
        on = estimator == "median" and lit != "none"
        # With no curve on, the ratio divides by each shower's deposit fit; a deposit whose windows
        # tie (stats/robust_width.KAPPA_FLOOR, the synthetic median recording) has none, and then no
        # ratio mark exists: the drawer says so instead.
        deposit_fitted = any(s["source"] == "detector" and any(s["fits"][windows][f] for f in ("quadrature", "pinned"))
                             for s in payload["series"])
        assert e["warning"] == (warning if on else "")
        assert sum(g.replace("\n", " ") == warning for g in e["graphics"]) == (1 if on else 0), key
        assert all(warning not in g for g in e["graphics"] if g.replace("\n", " ") != warning)
        assert e["reference"] == ("deposit" if lit == "none" else e["reference"]) and (lit == "none") == (e["reference"] == "deposit")
        assert e["nLiterature"] == len(RES_LIT[lit]) and len(e["literatureTips"]) == len(RES_LIT[lit])
        for tip in e["literatureTips"]:
            assert (warning in tip) == on
        # Robust declines a single-shower series' one fittable window (brief-fix F4): the 3-anchor mode then draws
        # no window at all, and the view is its empty state (test_res_fix3_the_robust_decline_is_said_…).
        drawn = bool(e["pointTips"])
        assert bool(e["ratioTips"]) == (drawn and (lit != "none" or deposit_fitted)), key
        for tip in e["ratioTips"]:
            assert (warning in tip) == on
        main = [s for s in e["series"] if s["grid"] == 0]
        ratio = [s for s in e["series"] if s["grid"] == 1]
        lit_series = [s for s in main if re.match(r"^(π±|e±) lit\.", s["name"])]
        assert bool(lit_series) == (drawn and lit != "none")
        for s in main:
            for tip in s["tips"]:
                assert (warning in tip) == (on and s in lit_series), (key, s["name"])
        if drawn:
            assert any(s["tips"] for s in ratio)   # the 1.0 rule's own tip at least
        else:
            assert not ratio and not main, key
        for s in ratio:
            for tip in s["tips"]:
                assert (warning in tip) == on, (key, s["name"])
    for e in entry["linear"].values():
        assert not any(warning in t for s in e["series"] for t in s["tips"]) and not any(warning in g for g in e["graphics"])
        assert not any(warning in p["tip"] for p in e["points"])
    if estimator != "median":
        assert not any("Note: comparing" in t for t in _every_text(entry))


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_the_unity_rule_names_only_a_reference_that_exists(est, name):
    """The ratio panel's 1.0 rule says what it divides by, and never a deposit fit that does not exist. Under the
    deposit reference a shower whose deposit has no fit in the mode is named with its reason, word for word as the
    drawer's Disclosures name it; with no shower fitted the rule is the axis's centre with nothing to divide by.
    (F-jstests' nit, fixed by the lead on 2026-11-12: the tied median deposits and the robust single-shower
    all-windows view had a rule saying "equal to the reference: each shower's deposit fit".)"""
    entry = est["fixtures"][name]
    showers = {s["shower"] for s in _load(name)["series"]}
    seen_missing = False
    for key, e in entry["energy"].items():
        lit = key.split(":")[1]
        unity = [t for s in e["series"] if s["grid"] == 1 and s["name"] == "ratio = 1" for t in s["tips"]]
        if not e["pointTips"]:
            assert not unity, key                  # the empty state draws no panel at all
            continue
        (tip,) = unity
        tip = _plain(tip)
        missing = [line for line in e["notes"]["sections"].get("Disclosures", []) if " has no ratio marks: " in line]
        if lit != "none":
            assert not missing, key                # a literature curve is defined everywhere on the axis
        assert [line for line in missing if line not in tip] == [], key
        assert tip.count(" has no ratio marks: ") == len(missing), key
        nothing = lit == "none" and len(missing) == len(showers)
        assert ("no reference to divide by" in tip) == nothing, key
        assert ("equal to the reference: " in tip) == (not nothing), key
        seen_missing |= bool(missing)
    # The recordings that reach it: the tied median deposits of the two-shower recording (KAPPA_FLOOR), and robust's
    # single-shower series, declined through one fittable window (brief-fix F4).
    assert seen_missing == (name in {"res_scaling_median_two", "res_scaling_robust_single_hits",
                                     "res_scaling_robust_single_events"}), name


#: The E view's drawer on a/√E ⊕ b ⊕ c/E (brief section 5 and 11, N-notes): each sentence once where it applies.
NOISE_DRAWER_CONSTRAINT = ("a/√E ⊕ b ⊕ c/E is fitted as ({sym})² = A/E + B + C/E² by weighted least squares with A = a², B = b² "
                           "and C = c² held non-negative, so every term is real; a term the constraint holds at 0 is named under "
                           "Disclosures, and the fit's ν counts its free terms only.")
NOISE_DRAWER_FLOOR = ("The a/√E ⊕ b ⊕ c/E fit uses windows from 1 GeV: below that a 1 GeV window reaches momenta near zero, so "
                      "its average of 1/E² is far from what its plotted energy implies, and no single abscissa can carry the noise "
                      "term c/E.")
NOISE_CAVEAT = ("c/E is the calorimeter's conventional noise term. Here it takes up whatever grows like 1/E at low momentum (for a "
                "network, its pull toward mid-range; under Median |rel. err.|, the response's bias as well), so c is a fitted "
                "coefficient, not a measured noise level.")
NOISE_CORRELATED = ("Over the fitted windows 1/√E, 1 and 1/E change together, so the fitted squares are {how}: the curve is "
                    "better determined than its split into a, b and c, and each free term's standard error already carries "
                    "that correlation, conditional only on the held terms.")
#: Review m3: the held-term caveat, its own line wherever a drawn noise fit holds a term, with or without a ρ.
NOISE_HELD_CAVEAT = ("A term held at 0 means the windows need no separate term of that form once the others are free, not that "
                     "the detector has none.")
#: brief-fix FX2, the drawer's weights sentence (verbatim), under median and robust only.
#: The pooled-scale line's last sentence (SC-notes, 2026-11-15; one scale, Martin's directive of that day): the noise
#: fit's windows of 1–4 GeV take the same c, without entering it. It replaced FX2's two-scale weights sentence.
#: The pooled-scale line's last sentence (FX2's, under one scale since the single-curve round), with review-stats
#: S2's clause (28d58e5): a 1–4 GeV window's residual counts in S and the misfit verdict at c·ŷ/√N.
FX2_WEIGHTS = ("The a/√E ⊕ b ⊕ c/E fit weights its windows of 1–4 GeV by the same c, se = c·ŷ/√N, which they do not enter, "
               "so their residuals count in S and the misfit verdict at c·ŷ/√N, not at their own bootstrap errors.")
#: FX2's retired sentence: never printed again.
FX2_WEIGHTS_RETIRED = "se = c_low·ŷ/√N"
NOISE_TABLED_E = "a/√E ⊕ b is in the fit table, not drawn."
NOISE_TABLED_LINEAR = ("a/√E ⊕ b ⊕ c/E, fitted as ({sym})² = A/E + B + C/E² with A, B and C held non-negative, is tabled under "
                       "the plot as well, not drawn: it is fitted to windows from 1 GeV, and those below 4 GeV lie off this view's "
                       "axis, so it is drawn in the E (GeV) + ratio view.")
#: Claims the E view's drawer made before a/√E ⊕ b ⊕ c/E (Martin's decisions of 2026-11-13) and must no longer make.
NOISE_REMOVED_CLAIMS = ("no curve is drawn below 4 GeV", "no curve is drawn there", "drawn only where both terms are defined",
                        "where both terms are defined (A > 0 and B > 0)", "the quadrature fit a/√E ⊕ b is not drawn",
                        "the thicker line is the quadrature")


def _exact_band_sentences(texts) -> list[str]:
    """brief-fix FX1 Words: "exact" leaves every band sentence. The sentences (split at ". " and ";") that speak of a
    band and call anything exact, the one sanctioned phrase aside: the ratio tooltip's "the reference is held exact",
    which describes how the reference enters the ratio, not the band's coverage (NF-panel §2)."""
    out = []
    for t in texts:
        for sentence in re.split(r"(?<=\.)\s+|;\s*", _plain(t)):
            if "band" in sentence and re.search(r"\bexact\b", sentence.replace("the reference is held exact", "")):
                out.append(sentence)
    return out


def _held_line(label: str, held: list[str]) -> str:
    """The drawer's held line: the held terms and their constraints, and nothing after them. FX1's band sentence (the
    envelope, or the conditional band where the free face was singular) left with the band (single-curve round,
    Martin's directive of 2026-11-15; SC-notes)."""
    name = lambda t: "the noise term c/E" if t == "c" else t  # noqa: E731
    one = len(held) == 1
    return (f"{label}: {' and '.join(name(x) for x in held)} held at 0 by the constraint{'' if one else 's'} "
            f"{' and '.join(f'{x}² ≥ 0' for x in held)}.")


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_noise_drawer_sentences_are_each_said_once_where_they_apply(est, name):
    """Every recording, estimator, mode and literature state: the constraint, the floor, "a/√E ⊕ b is in the fit table",
    the server's E-view sentence, the naming caveat and the correlation sentence (by its rule) once; one held line per
    series that holds a term, one reason line per series without a fit, none otherwise; the low anchor in the 3-anchor
    mode only; none of the removed claims; and in the 1/√E drawer the tabled sentence once, the definition note never."""
    payload = _load(name)
    sym = payload["estimator"]["symbol"]
    for windows in ("anchors", "all"):
        series = payload["series"]
        drawn = [s for s in series if s["fits"][windows]["noise"]]
        for lit in RES_LIT:
            notes = est["fixtures"][name]["energy"][f"{windows}:{lit}"]["notes"]
            lines = [x for sec in notes["sections"].values() for x in sec]
            where = (name, windows, lit)
            text = " ".join(lines)
            assert len(lines) == len(set(lines)), (where, "a line is said twice")
            assert lines.count(NOISE_DRAWER_CONSTRAINT.format(sym=sym)) == 1, where
            assert lines.count(NOISE_DRAWER_FLOOR) == 1, where
            # a/√E ⊕ b is named once, inside the one-curve sentence (single-curve round); the server's restatement of
            # the rule (its E-view note) is not printed, the drawer's own sentences say it once.
            assert text.count(NOISE_TABLED_E) == 0 and lines.count(SC_DRAWER_ONE_CURVE) == 1, where
            assert payload["axis"]["energy"]["notes"][1].startswith("Each series draws one fitted curve with no band round it")
            assert lines.count(payload["axis"]["energy"]["notes"][1]) == 0, where
            assert lines.count(NOISE_CAVEAT) == (1 if drawn else 0), where
            rhos = [v for s in drawn for v in s["fits"][windows]["noise"]["params"]["rho"].values() if v is not None]
            corr = [x for x in lines if x.startswith("Over the fitted windows 1/√E, 1 and 1/E change together")]
            if rhos:
                top = max(abs(v) for v in rhos)
                how = ("strongly correlated (each curve's tooltip gives ρ)" if top >= 0.7
                       else f"correlated (here |ρ| ≤ {_sf(top)}; each curve's tooltip gives ρ)")
                assert corr == [NOISE_CORRELATED.format(how=how)], where
            else:
                assert not corr, where
            # m3: the held-term caveat whenever a drawn noise fit holds a term, ρ or no ρ.
            any_held = any(s["fits"][windows]["noise"]["params"]["held"] for s in drawn)
            assert lines.count(NOISE_HELD_CAVEAT) == (1 if any_held else 0), where
            assert "its band is conditional on" not in text, where
            assert not _exact_band_sentences(lines), where
            # The one-scale sentence once, under median and robust only (FX2's two-scale sentence retired).
            assert text.count(FX2_WEIGHTS) == (0 if RES_EST[name] == "sample" else 1), where
            assert FX2_WEIGHTS_RETIRED not in text and "c_low" not in text, where
            for s in series:
                nf = s["fits"][windows]["noise"]
                held = [x for x in lines if x.startswith(f"{s['label']}: ") and " held at 0 by the constraint" in x]
                if nf and nf["params"]["held"]:
                    assert held == [_held_line(s["label"], nf["params"]["held"])], (where, s["key"])
                else:
                    assert not held, (where, s["key"])
                reason = s["fits"][windows]["noise_reason"]
                if not nf:
                    # Said once, in What is drawn, with what the series draws instead (single-curve round): its a₀/√E as
                    # the fallback, or no curve at all.
                    said = [x for x in lines if x.startswith(f"{s['label']}: ") and reason in x]
                    assert len(said) == 1, (where, s["key"], said)
                    assert said[0] in (f"{s['label']}: {reason} Its origin-pinned a₀/√E ⊕ 0 is drawn instead, from 4 GeV, as the thinner line.",
                                       f"{s['label']}: {reason} Its origin-pinned a₀/√E ⊕ 0 is drawn instead, from 4 GeV, provisional, as the thinner line.") \
                        or said[0].startswith(f"{s['label']}: no fitted curve is drawn. {reason} Its origin-pinned a₀/√E ⊕ 0 has no curve either: "), \
                        (where, said)
            low = [x for x in lines if "a/√E ⊕ b ⊕ c/E runs through" in x]
            with_low = [s for s in drawn if s["fits"][windows]["noise"]["low_anchor"] is not None]
            if windows == "anchors" and with_low:
                assert len([x for x in low if x.startswith("In the 3-anchor mode")]) == 1, where
                assert all("lowest fittable window from 1 GeV" in x and "since anchors from 5 GeV cannot fix a 1/E term" in x
                           for x in low if x.startswith("In the 3-anchor mode")), where
                for s in with_low:
                    label = next(w["label"] for w in s["windows"] if w["bin"] == s["fits"][windows]["noise"]["low_anchor"])
                    assert any(f"({label})" in x or f"and {label}" in x for x in low), (where, s["key"])
            elif windows == "all":
                assert not low, where
            for claim in NOISE_REMOVED_CLAIMS:
                assert claim not in text, (where, claim)
        linear = est["fixtures"][name]["linear"][windows]["notes"]
        lin_lines = [x for sec in linear["sections"].values() for x in sec]
        assert lin_lines.count(NOISE_TABLED_LINEAR.format(sym=sym)) == 1, (name, windows)
        assert not [x for x in lin_lines if x.startswith("a/√E ⊕ b ⊕ c/E, the E view's second curve")], (name, windows)


def test_res_notes_e_view_counts_every_band_cut_at_zero(out, est):
    """The drawer's "n fits have the lower edges of their bands cut at 0" counted every drawn fit whose band the panel
    cut at 0, a/√E ⊕ b ⊕ c/E included. With no band on the E view (Martin's directive of 2026-11-15) no drawn fit
    carries `floorCut` or any other band field, on any recording, estimator, mode or literature state, and no drawer
    line speaks of a lower edge cut at 0."""
    for name, key, rec in _e_notes(out):
        assert not [line for line in _lines(rec["notes"], out, "disclosures") if " cut at 0: " in line or "lower edge" in line], (name, key)
    for name, entry in est["fixtures"].items():
        for key, e in entry["energy"].items():
            assert all(n["retired"] == [] for n in e["noise"]), (name, key)
            lines = [x for sec in e["notes"]["sections"].values() for x in sec]
            assert not [x for x in lines if "lower edge" in x or " cut at 0" in x], (name, key)


def test_res_notes_e_view_names_every_noise_curve_or_band_coming_from_the_top(out, est):
    """Every a/√E ⊕ b ⊕ c/E caret at the top of the main panel is named in the drawer: a curve that comes down (the
    "come down" line) and a curve above the top at every E (its own line), so the drawer's names equal the panel's
    clipped.entries. (A band above the top while its curve is inside, the third case before the single-curve round,
    is gone with the band: the copy that raised SE(b²) now has no entry at all.)"""
    cases = [("robust_two", est["fixtures"]["res_scaling_robust_two"]["energy"][f"{w}:none"]) for w in ("anchors", "all")]
    labels = {x["key"]: x["label"] for x in _load("res_scaling_two")["series"]}
    for tag in ("above", "bandAbove"):
        case = out["resE"]["noise"][tag]
        cases.append((tag, {"noise": [{"key": s["key"], "label": labels[s["key"]], "entry": s["fits"]["noise"].get("entry")}
                                      for s in case["model"]["series"]],
                            "clipped": case["model"]["clipped"], "notes": case["notes"]}))
    assert out["resE"]["noise"]["above"]["model"]["clipped"]["entries"] == 4
    for where, rec in cases:
        lines = [x for sec in rec["notes"]["sections"].values() for x in sec]
        named = 0
        for n in rec["noise"]:
            e = n["entry"]
            if not e:
                continue
            said = [x for x in lines if n["label"] in x and ("down into the main panel" in x or "above the top of the main panel" in x)]
            assert said, (where, n["key"], e)
            named += 1
        assert named == rec["clipped"]["entries"], where


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_sweeps_reach_the_noise_strings(est, name):
    """The hyphen and bare-σ/E sweeps (`_every_text`) read every new string: the noise curve's tooltip, its entry caret,
    the table's noise row and the drawer's sentences, under every estimator. Under the median the curve is named in its
    own symbol."""
    payload = _load(name)
    sym = payload["estimator"]["symbol"]
    texts = [_plain(t) for t in _every_text(est["fixtures"][name])]
    blob = "\n".join(texts)
    drawn = any(s["fits"][w]["noise"] for s in payload["series"] for w in ("anchors", "all"))
    assert NOISE_DRAWER_FLOOR in blob and "c, the noise term c/E, belongs to that form alone" in blob
    if drawn:
        assert f"{sym} = a/√E ⊕ b ⊕ c/E" in blob and f"Fitted as ({sym})² = A/E + B + C/E²" in blob
        assert NOISE_CAVEAT in blob and "a/√E ⊕ b ⊕ c/E — drawn" in blob
        rising = any(nf and (nf["params"]["a2"] > 0 or nf["params"]["c2"] > 0)
                     for s in payload["series"] for nf in (s["fits"]["anchors"]["noise"], s["fits"]["all"]["noise"]))
        if rising:
            assert "It comes down into the plot at E = " in blob or "a/√E ⊕ b ⊕ c/E fit lies above the top of the axis" in blob
    if RES_EST[name] == "median":
        assert "σ/E = a/√E ⊕ b ⊕ c/E" not in blob and "(σ/E)² = A/E" not in blob


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_median_hazard_sits_beside_no_interval_reported(est, name):
    """modelsHazards: "median rel. against σ/E curve" when the estimator is the median, the view is E and a curve
    is on; "no interval reported" whenever a curve is on; the drawer carries the same list."""
    estimator = RES_EST[name]
    entry = est["fixtures"][name]
    for key, e in entry["energy"].items():
        on = key.split(":")[1] != "none"
        assert (RES_HAZARD in e["hazards"]) == (estimator == "median" and on), key
        assert ("no interval reported" in e["hazards"]) == on
        assert e["notes"]["hazards"] == e["hazards"]
        if RES_HAZARD in e["hazards"]:
            assert e["hazards"].index(RES_HAZARD) == e["hazards"].index("no interval reported") + 1
    for e in entry["linear"].values():
        assert RES_HAZARD not in e["hazards"] and RES_HAZARD not in e["notes"]["hazards"]


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_drawer_says_the_disclosure_in_the_e_view_only_under_the_median(est, name):
    estimator = RES_EST[name]
    warning = _warning()
    entry = est["fixtures"][name]
    for key, e in entry["energy"].items():
        on = estimator == "median" and key.split(":")[1] != "none"
        dis = e["notes"]["sections"]["Disclosures"]
        assert dis.count(warning) == (1 if on else 0), key
        assert all(warning not in line for heading, lines in e["notes"]["sections"].items() for line in lines
                   if not (heading == "Disclosures" and line == warning))
    for e in entry["linear"].values():
        assert not any(warning in line for lines in e["notes"]["sections"].values() for line in lines)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_drawer_names_the_estimator_its_interval_and_weight(est, name):
    """Selection names the estimator; What is drawn the fit weight (κ or delta method); the legend the whisker by
    the payload's interval label; the relation sentence under the median and robust widths, never converting."""
    estimator = RES_EST[name]
    block = _load(name)["estimator"]
    entry = est["fixtures"][name]
    titles = {"median": ("Median Relative Error vs. 1/√E", "Median Relative Error vs. E"),
              "robust": ("Energy Resolution vs. 1/√E", "Energy Resolution vs. E"),
              "sample": ("Energy Resolution vs. 1/√E", "Energy Resolution vs. E")}[estimator]
    for view, title in zip(("linear", "energy"), titles):
        for e in entry[view].values():
            n = e["notes"]
            s = n["sections"]
            assert n["title"] == title
            assert f"Estimator: {block['label']}." in s["Selection"]
            drawn = " ".join(s["What is drawn"])
            text = " ".join(line for lines in s.values() for line in lines)
            # The 1/√E view words the weight law in its fits sentence; both views carry the payload's weight label
            # under the median and robust widths.
            if estimator == "sample":
                assert ("delta-method standard error of σ/μ" in drawn) == (view == "linear") and "κ" not in drawn
            else:
                assert ("se = c·ŷ/√N with c the series' pooled scale (below)" in drawn) == (view == "linear")
                assert "se = κ·ŷ" not in text and "window's bootstrap relative standard error" not in text
                assert block["weight"]["label"].rstrip(".") in drawn
                assert "delta-method" not in text and "χ² whisker" not in text
                assert block["interval"]["label"].rstrip(".") in " ".join(s["Marks and legend"])
                rel = [line for line in s["Disclosures"] if line.startswith(block["relation"])]
                assert len(rel) == 1
                # Alone on the 1/√E view; on the E view with the MAE/E sentence and what the card plots.
                if view == "linear":
                    assert rel[0] == block["relation"]
                else:
                    assert "MAE/E is not σ/E either" in rel[0]
                    assert rel[0].endswith("This card plots the median relative error and never converts it into σ/E." if estimator == "median"
                                           else "This card plots the robust width IQR(R) / (1.349 · median R) and never converts one into another.")


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_drawer_gives_c_tilde_beside_c_sum_under_the_median(est, name):
    estimator = RES_EST[name]
    showers = _load(name)["estimator"]["calibration"]["showers"]
    for view in ("linear", "energy"):
        for e in est["fixtures"][name][view].values():
            dis = e["notes"]["sections"]["Disclosures"]
            for key, c in showers.items():
                owner = f"Shower {key.upper()}" if len(showers) > 1 else "The deposit"
                line = f"{owner}: c̃ = {_sf(c['c_median'], 6)} beside c_sum = {_sf(c['c_sum'], 6)} ("
                assert any(x.startswith(line) for x in dis) == (estimator == "median"), (view, owner)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_drawer_counts_the_windows_below_the_robust_floor(est, name):
    """Under the robust width only: the windows of 2 ≤ N < 20, which have no value, counted over the series on show."""
    estimator = RES_EST[name]
    payload = _load(name)
    below = sum(1 for s in payload["series"] for w in s["windows"] if 2 <= (w["n"] or 0) < 20 and w["value"] is None)
    for view in ("linear", "energy"):
        for e in est["fixtures"][name][view].values():
            lines = [x for x in e["notes"]["sections"]["Disclosures"] if "below its floor of N = 20" in x]
            if estimator != "robust":
                assert not lines
                continue
            many = below != 1
            assert lines == [f"{below} window{'s' if many else ''} of 2 ≤ N < 20 {'have' if many else 'has'} no Robust σ/E, "
                             "below its floor of N = 20 (the CLAUDE.md robust floor), "
                             f"so {'they are' if many else 'it is'} not drawn; Sample σ/μ reports {'them' if many else 'it'} from N = 2."]
    if estimator == "robust" and name.endswith("_two"):
        assert below > 0, "the two-shower fixture holds windows below the floor"


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_est_the_drawer_gives_each_model_series_median_response_range(est, name):
    estimator = RES_EST[name]
    payload = _load(name)
    models = [s for s in payload["series"] if s["source"] != "detector"]
    tail = {"median": "The median relative error divides nothing out, so this bias is part of the plotted value there.",
            "robust": "The robust width divides the bias out, so it does not enter the plotted value, though the narrowing does.",
            "sample": "The sample width divides the bias out, so it does not enter the plotted value, though the narrowing does."}[estimator]
    for view in ("linear", "energy"):
        for key, e in est["fixtures"][name][view].items():
            mode = key.split(":")[0]
            dis = e["notes"]["sections"]["Disclosures"]
            for s in models:
                r = s["median_response_range"][mode]
                mode_text = "the 3-anchor mode" if mode == "anchors" else "the all-windows mode"
                line = (f"{s['label']}: the median response R̃ − 1 runs from {_signed_pc(r[0])} to {_signed_pc(r[1])} "
                        f"over the fitted windows of {mode_text}." if r else
                        f"{s['label']}: no median response range, fewer than two fitted windows of {mode_text}.")
                assert line in dis, (view, key, line)
            bounded = [x for x in dis if x.startswith("A regressor trained on a bounded momentum range")]
            assert len(bounded) == (1 if models else 0)
            if models:
                assert bounded[0].endswith(tail)


def test_res_est_no_rendered_number_uses_an_ascii_hyphen(est):
    for entry in est["fixtures"].values():
        _no_hyphen_numbers(_every_text(entry))
    for quantities in est["perf"].values():
        for q in quantities.values():
            _no_hyphen_numbers(q["tips"])
            _no_hyphen_numbers(line for lines in q["notes"]["sections"].values() for line in lines)


def test_perf_the_median_rel_reconciliation_is_the_briefs_sentence(est):
    assert est["perfConsts"] == {"notSigma": PERF_NOT_SIGMA, "reconciliation": PERF_RECONCILIATION}


@pytest.mark.parametrize("name", PERF_ALL)
def test_perf_the_energy_median_rel_says_it_is_not_a_sigma_and_never_the_angle_task(est, name):
    """The tooltip line on every bar of the energy task's Median rel. and the drawer's last Estimators line; no
    other quantity and never the angle task, whose relative error is not an energy's."""
    quantities = est["perf"][name]
    assert "median_rel" in quantities
    energy = not name.endswith("_angle")
    for key, q in quantities.items():
        mine = key == "median_rel" and energy
        assert q["energyMedian"] is mine and (q["task"] == "angle") is (not energy)
        assert q["tips"]
        for tip in q["tips"]:
            assert (PERF_NOT_SIGMA in _plain(tip)) is mine, (key, tip)
        lines = q["notes"]["sections"]["Estimators"]
        assert lines.count(PERF_RECONCILIATION) == (1 if mine else 0)
        if mine:
            assert lines[-1] == PERF_RECONCILIATION
        assert not any(PERF_NOT_SIGMA in line for line in lines if line != PERF_RECONCILIATION)


# ------------------------------------------------- res-robust fix round: the review's coverage gaps (R-ui)
# Each pin below failed on the pre-fix wording (017c845's panel, notes and fixtures) and passes on the fix round's.
#
# - No bare "σ/E" names the plotted value under the median (R-ui M2), in any drawer line, tooltip, canvas text, note
#   band or fit-table caption or cell. Allowed: the literature equations, the payload's relation sentence, the MAE/E
#   sentence, the server's definition sentence that contrasts the two, the literature disclosure and the name
#   "Robust σ/E" of the robust estimator in a cross-reference.
# - The tied, withheld and declined wording sits on exactly those windows and series (R-ui m2, brief-fix F3, F4, F7),
#   and the robust drawer never says a window is faded (R-ui m1).
# - The decomposition sentence, once per drawer under every estimator and view (R-ui M3).
# - The pooled-scale line under median and robust, never under sample, its c the payload's (brief-fix F1).
# - No role line says "holds too few events" for a substitution whose cause is not N (brief-fix F3).
# - The robust single-shower 3-anchor empty state names the decline, in both views (brief-fix F4).

#: brief-fix.md, "The drawer's decomposition sentence", verbatim.
RES_DECOMPOSITION = (
    "The three estimators differ for stated reasons: median|R − 1| is 0.6745 of a σ by definition and keeps the "
    "response's bias, which the two widths divide out by centring on the median; the sample width also counts the "
    "tails, which the robust width does not (each window's tooltip gives its share of events beyond 3 robust σ). "
    "Methodology §2.4 measures the three factors on one window.")
#: A literature curve's printed equation, the one σ/E a median text may carry as an equation.
_LIT_EQUATION = re.compile(r"σ/E = \d+(?:\.\d+)?/√E ⊕ \d+(?:\.\d+)?")
_MAE_SENTENCE = ("MAE/E is not σ/E either: for unbiased Gaussian errors MAE/E = √(2/π)·σ/E ≈ 0.798·σ/E, and MAE also "
                 "carries the bias that σ(R)/μ(R) divides out.")
#: substitutionWhy: the clause a stand-in anchor's role line gives for its nominal anchor, by the substitution's cause.
_CAUSE_WORDS = {
    "n": "which holds too few events for this series",
    "tied": "which carries no fit weight: its bootstrap SE is below 10⁻⁶ of its value (tied replicates)",
    "no_value": "which reports no {symbol}",
    "withheld": "whose robust interval is withheld, so it carries no fit weight",
    "no_se": "which has no positive standard error, so it carries no fit weight",
    "off_axis": "which lies off the axis, below 4 GeV",
}
_WITHHELD_NOTE = ("Robust interval withheld: 61 of the 2,000 bootstrap replicates (3.0%) have a median R ≤ 0, more "
                  "than 2.5%, and leaving them out would cut the interval's upper tail; no whisker, SE or fit weight.")
_SYN_CAUSES = [c for c in _CAUSE_WORDS if c != "n"]


def _synthetic_payloads() -> dict:
    """The cases the recordings do not hold, each a copy of a recording with one thing changed:

    - ``syn_robust_withheld``: one fitted, non-anchor window of the robust two-shower network A withheld (brief-fix
      F7): value kept; ci95, SE, κ and method null; the server's withheld note; out of the all-windows fits, the
      a/√E ⊕ b ⊕ c/E fit's window list included;
    - ``syn_median_tail``: on the median XGBoost recording's deposit, one window at N = 1,022 with a 4.31% tail share and one at
      N = 400 with none (IQR = 0, brief-fix F6);
    - ``syn_median_cause_<cause>``: the median two-shower recording with every stand-in anchor's substitution given
      that cause, so each role line's clause is exercised."""
    out = {}
    robust = _load("res_scaling_robust_two")
    s = next(x for x in robust["series"] if x["key"] == "network:a")
    w = next(x for x in s["windows"] if x["bin"] in s["fits"]["all"]["points"]
             and x["bin"] not in s["fits"]["anchors"]["points"] and x["n"] >= 20)
    w.update(ci95=None, se=None, se_rel=None, method=None, dof_note=_WITHHELD_NOTE)
    s["fits"]["all"]["points"] = [b for b in s["fits"]["all"]["points"] if b != w["bin"]]
    # A withheld window carries no fit weight, so it leaves the a/√E ⊕ b ⊕ c/E fit too (a real server would refit;
    # only the window list changes here).
    noise = s["fits"]["all"].get("noise")
    if noise:
        noise["points"] = [b for b in noise["points"] if b != w["bin"]]
    out["syn_robust_withheld"] = robust
    tail = _load("res_scaling_median_xgb")
    s = next(x for x in tail["series"] if x["key"] == "detector:a")
    big = [x for x in s["windows"] if x["n"] >= 20 and x["value"] is not None and not x.get("off_axis")]
    big[0].update(n=1022, tail_share=4.31)
    big[1].update(n=400, tail_share=None)
    out["syn_median_tail"] = tail
    for cause in _SYN_CAUSES:
        payload = _load("res_scaling_median_two")
        for s in payload["series"]:
            for sub in s["fits"]["anchors"].get("substitutions") or []:
                if sub["used"] is not None:
                    sub["cause"] = cause
        out[f"syn_median_cause_{cause}"] = payload
    return out


@pytest.fixture(scope="module")
def syn(tmp_path_factory) -> dict:
    """`_EST_BODY` over the synthetic payloads, written to a temporary fixture folder."""
    payloads = _synthetic_payloads()
    folder = tmp_path_factory.mktemp("res_fix3")
    for name, payload in payloads.items():
        (folder / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    names = {name: name.split("_")[1] for name in payloads}
    prelude = _script()
    prelude = prelude[:prelude.index("const out = { perf")]
    body = _EST_BODY % {"est": json.dumps(names), "lit": json.dumps(RES_LIT), "perf": json.dumps([])}
    done = subprocess.run([NODE, "--input-type=module", "-e", prelude + body, json.dumps([JS.as_uri(), str(folder)])],
                          capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    result["payloads"] = payloads
    return result


def _fix3_drawers(entry: dict):
    """(view, key, notes) for every drawer one fixture's harness entry built."""
    for view in ("linear", "energy"):
        for key, e in entry[view].items():
            yield view, key, e["notes"]


def _fix3_lines(notes: dict) -> list[str]:
    return [line for lines in notes["sections"].values() for line in lines]


def _fix3_point_tips(entry: dict):
    """(view, mode, point) for every drawn window's tooltip, both views."""
    for view in ("linear", "energy"):
        for key, e in entry[view].items():
            for p in e.get("points", e.get("pointTips", [])):
                yield view, key.split(":")[0], p


def _fix3_roles(tip: str) -> list[str]:
    return [line[len("Role: "):] for line in (_plain(x) for x in tip.split("<br/>")) if line.startswith("Role: ")]


def _fix3_tied(w: dict) -> bool:
    return w["se"] is not None and w["se_rel"] is None


def _fix3_fittable(w: dict, gates: dict) -> bool:
    """resolution_scaling.js `fittableWindow` off sample: N ≥ the fit gate, on the axis from 4 GeV, a value and a κ."""
    return (w["n"] or 0) >= gates["fit_n"] and not w.get("off_axis") and (w.get("p_lo") or 0) >= gates["e_min_gev"] \
        and w["value"] is not None and (w["se_rel"] or 0) > 0


@pytest.mark.parametrize("name", [n for n, e in RES_EST.items() if e == "median"])
def test_res_fix3_no_bare_sigma_e_names_the_median_value(est, name):
    """R-ui M2: under Median |rel. err.| the plotted value is "median rel." everywhere it is named."""
    block = _load(name)["estimator"]
    allowed = [block["literature"]["warning"], block["relation"], _MAE_SENTENCE,
               "This card plots the median relative error and never converts it into σ/E.",
               "unlike σ/E the median relative error keeps", "Robust σ/E",
               # A literature curve's units (c406217): σ/E there names the curve's own quantity, never the plotted one.
               REFERENCE_UNITS]
    texts = list(_every_text(est["fixtures"][name]))
    assert any(t for t in texts)
    for text in texts:
        rest = _plain(text)
        for phrase in allowed:
            rest = rest.replace(phrase, "")
        rest = _LIT_EQUATION.sub("", rest)
        assert "σ/E" not in rest, (name, rest)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_fix3_the_decomposition_sentence_is_once_in_every_drawer(est, name):
    """R-ui M3: the brief-fix sentence, verbatim, once in the Disclosures of every drawer, every estimator and view."""
    assert est["decomposition"] == {"panel": RES_DECOMPOSITION, "notes": RES_DECOMPOSITION}
    for view, key, notes in _fix3_drawers(est["fixtures"][name]):
        assert notes["sections"]["Disclosures"].count(RES_DECOMPOSITION) == 1, (view, key)
        assert sum(RES_DECOMPOSITION in line for line in _fix3_lines(notes)) == 1, (view, key)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_fix3_the_pooled_scale_line_gives_each_series_its_payload_c(est, name):
    """brief-fix F1, under the single-curve round's one scale (Martin's directive of 2026-11-15, replacing FX2's pair):
    one What-is-drawn line under median and robust names every series' c from `weight_scale` (or says it has none),
    says what c cancels in, and ends with the sentence that the noise fit weights its windows of 1–4 GeV by the same c,
    which they do not enter; it names no c_low. Under sample no text speaks of a pooled scale."""
    estimator = RES_EST[name]
    payload = _load(name)
    gates = payload["gates"]
    lead = ("The pooled scale, one per series, c over its windows from 4 GeV: it cancels in the fitted parameters and sets "
            "only their χ², S and errors. ")
    if estimator == "sample":
        assert all(s["weight_scale"] is None for s in payload["series"])
        assert not any("pooled scale" in t or "c·ŷ/√N" in t or "c_low" in t for t in _every_text(est["fixtures"][name]))
        return
    win = lambda n: f"{n} window{'' if n == 1 else 's'}"  # noqa: E731
    for view, key, notes in _fix3_drawers(est["fixtures"][name]):
        mine = [line for line in notes["sections"]["What is drawn"] if line.startswith(lead)]
        assert len(mine) == 1 and sum(line.startswith(lead) for line in _fix3_lines(notes)) == 1, (view, key)
        line = mine[0]
        assert line.endswith(". " + FX2_WEIGHTS), (view, key)
        assert "c_low" not in line and "one pair per series" not in line
        for s in payload["series"]:
            ws = s["weight_scale"]
            assert set(ws) == {"c", "n_windows", "rule"}
            last = s is payload["series"][-1]
            if ws["c"] is None:
                assert ws["n_windows"] == 0
                part = f"{s['label']}: none, no window from 4 GeV carries a fit weight, so no fit"
            else:
                strong = any(_fix3_fittable(w, gates) for w in s["windows"])
                part = (f"{s['label']}: c = {_sf(ws['c'])} over {win(ws['n_windows'])}"
                        + ("" if strong else " of N ≥ 8, since no window of N ≥ 20 carries a fit weight"))
                printed = re.search(re.escape(s["label"]) + r": c = ([\d.]+) over", line)
                assert printed and float(printed.group(1)) == pytest.approx(ws["c"], rel=5e-3)
            assert part + ("." if last else ";") in line, (view, key, part, line)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_fix3_tied_wording_is_on_exactly_the_tied_windows(est, name):
    """R-ui m2, brief-fix F3: a tied window (a bootstrap SE below 10⁻⁶ of its value) says so in its SE line and, at
    N ≥ 20, in its role line, "drawn in the all-windows mode only"; no other window speaks of tied replicates. The
    drawer names each series' tied windows of N ≥ 20 once, and never reprints the server's note of the same."""
    estimator = RES_EST[name]
    payload = _load(name)
    windows = _windows(payload)
    gates = payload["gates"]
    entry = est["fixtures"][name]
    role = ("not fitted: its bootstrap SE is below 10⁻⁶ of its value (tied replicates), so it carries no fit weight; "
            "drawn in the all-windows mode only")
    for view, mode, p in _fix3_point_tips(entry):
        w = windows[(p["key"], p["bin"])]
        tip = _plain(p["tip"])
        tied = estimator != "sample" and _fix3_tied(w)
        assert ("tied replicates" in tip) == tied, (view, mode, p["key"], p["bin"])
        if tied:
            assert "so no fit weight" in tip and "κ =" not in tip
            assert _fix3_roles(p["tip"]) == [role] if w["n"] >= gates["fit_n"] and not w.get("off_axis") else True
            assert mode == "all", "a tied window is drawn in the all-windows mode only"
    tied_series = {s["label"]: [w["label"] for w in s["windows"]
                                if estimator != "sample" and _fix3_tied(w) and w["n"] >= gates["fit_n"] and not w.get("off_axis")]
                   for s in payload["series"]}
    if name == "res_scaling_median_two":
        assert sum(map(len, tied_series.values())) >= 10, "the recording holds the synthetic deposits' tied windows"
    for view, key, notes in _fix3_drawers(entry):
        dis = notes["sections"]["Disclosures"]
        assert not any("tied values: the replicates differ by rounding alone" in line for line in _fix3_lines(notes)), (view, key)
        for label, labels in tied_series.items():
            mine = [line for line in dis if line.startswith(f"{label}: ") and "no fit weight: " in line and "tied replicates" in line]
            if not labels:
                assert not mine, (view, key, label)
                continue
            one = len(labels) == 1
            assert mine == [f"{label}: {len(labels)} window{'' if one else 's'} of N ≥ 20 ({', '.join(labels)}) "
                            f"{'carries' if one else 'carry'} no fit weight: {'its' if one else 'their'} bootstrap SE is "
                            f"below 10⁻⁶ of {'its' if one else 'their'} value (tied replicates, which differ by rounding "
                            f"alone), so {'it is' if one else 'they are'} drawn in the all-windows mode only, never fitted."], (view, key)


def test_res_fix3_withheld_wording_is_on_exactly_the_withheld_window(syn):
    """brief-fix F7: a robust window whose interval is withheld keeps its value, prints the server's note, is not
    fitted for that reason and has no whisker for it, never for N; no other window says withheld. The drawer counts
    it in the robust-floor line and, where the mode draws it, in its own line."""
    name = "syn_robust_withheld"
    payload = syn["payloads"][name]
    entry = syn["fixtures"][name]
    withheld = {(s["key"], w["bin"]) for s in payload["series"] for w in s["windows"] if w["dof_note"] == _WITHHELD_NOTE}
    assert len(withheld) == 1
    seen = 0
    for view, mode, p in _fix3_point_tips(entry):
        tip = _plain(p["tip"])
        if (p["key"], p["bin"]) in withheld:
            seen += 1
            assert _WITHHELD_NOTE in tip
            assert "Role: not fitted: its robust interval is withheld, so it carries no fit weight" in tip
            assert ("No whisker: this window's robust interval is withheld (the note above says why); its value is drawn "
                    "as a faded dashed ring.") in tip
            assert "No whisker: N =" not in tip and "bootstrap SE" not in tip and "Robust σ/E = " in tip
        else:
            assert "withheld" not in tip, (view, mode, p["key"], p["bin"])
    all_mode = sum(key.startswith("all") for view in ("linear", "energy") for key in entry[view])
    assert seen == all_mode == 5, "drawn in every all-windows entry of both views, never in the 3-anchor mode"
    for view, key, notes in _fix3_drawers(entry):
        lines = _fix3_lines(notes)
        floor = [line for line in lines if "below its floor of N = 20" in line]
        assert len(floor) == 1 and floor[0].endswith(
            " 1 window reports a Robust σ/E whose interval is withheld: more than 2.5% of its bootstrap replicates have "
            "a median R ≤ 0, so no whisker, SE or fit weight."), (view, key)
        own = [line for line in lines if line.startswith("1 window is drawn as a faded dashed ring with no whisker and not fitted: its robust interval is withheld")]
        assert len(own) == (1 if key.startswith("all") else 0), (view, key)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_fix3_withheld_and_declined_wording_is_absent_where_nothing_is(est, name):
    """The recordings hold no withheld window, and only the robust single-shower ones a declined series."""
    declined = name.startswith("res_scaling_robust_single")
    for text in _every_text(est["fixtures"][name]):
        t = _plain(text)
        assert "interval is withheld" not in t and "Robust interval withheld" not in t
        assert ("fits no line through fewer than two fittable windows, and only" in t) <= declined


@pytest.mark.parametrize("name", ["res_scaling_robust_single_hits", "res_scaling_robust_single_events"])
def test_res_fix3_the_robust_decline_is_said_in_the_empty_state_role_and_drawer(est, name):
    """brief-fix F4: Robust σ (IQR) fits no line through its one fittable window. The 3-anchor mode then draws nothing,
    and its empty state names the decline in both views (never "No window from 5 GeV reaches N = 20"); the
    all-windows mode draws the window unfitted, its role line saying why; each drawer has one line for the series."""
    payload = _load(name)
    gates = payload["gates"]
    entry = est["fixtures"][name]
    (s,) = payload["series"]
    assert all(not s["fits"][m]["points"] for m in ("anchors", "all"))
    fittable = [w for w in s["windows"] if _fix3_fittable(w, gates) and (w["p_lo"] or 0) >= gates["anchor_low_gev"]]
    assert len(fittable) == 1
    w = fittable[0]
    said = (f"Robust σ (IQR) fits no line through fewer than two fittable windows, and only {w['label']} "
            f"(N = {w['n']:,}) is fittable here")
    for view, all_name in (("linear", "All ≥ 4 GeV"), ("energy", "All windows")):
        for key, e in entry[view].items():
            mode = key.split(":")[0]
            canvas = [g.replace("\n", " ") for g in e["graphics"]]
            if mode == "anchors":
                assert any(g.startswith(f'{said}: no fit, so the 3-anchor mode draws nothing. "{all_name}" draws it, unfitted.')
                           for g in canvas), (view, key, canvas)
                assert not any("reaches N = 20" in g for g in canvas)
                assert not e.get("points", e.get("pointTips"))
            else:
                assert not any(said in g for g in canvas)
                tips = [p for p in e.get("points", e.get("pointTips")) if p["bin"] == w["bin"]]
                assert tips and all(_fix3_roles(p["tip"]) == [f"not fitted: {said}"] for p in tips), (view, key)
            verb = "line" if view == "linear" else "fit"
            tail = "the window is drawn in the all-windows mode" if mode == "anchors" else "the window is drawn unfitted"
            dis = e["notes"]["sections"]["Disclosures"]
            assert dis.count(f"{s['label']}: {said}, so no {verb} is drawn; {tail}.") == 1, (view, key)
            assert not any("fewer than two windows to fit" in line for line in dis), (view, key)


@pytest.mark.parametrize("name", [n for n, e in RES_EST.items() if e == "robust"])
def test_res_fix3_the_robust_drawer_never_says_a_window_is_faded(est, name):
    """R-ui m1: under Robust σ (IQR) no window below N = 20 is drawn, so no drawer sentence says one is faded; a
    faded mark there is a fit (a misfit), and no fit is provisional, so the legend never says so."""
    for view, key, notes in _fix3_drawers(est["fixtures"][name]):
        for heading, lines in notes["sections"].items():
            for line in lines:
                for sentence in re.split(r"(?<=[.;])\s+", line):
                    if "faded" in sentence:
                        assert re.search(r"\bfits?\b", sentence) or "withheld" in sentence, (view, key, sentence)
                        assert "N < " not in sentence and "windows below" not in sentence, (view, key, sentence)
                if heading == "Marks and legend":
                    assert "provisional" not in line, (view, key, line)
        legend = " ".join(notes["sections"]["Marks and legend"])
        if view == "linear":
            assert "It is drawn from N = 20, the robust floor, below which no window is drawn." in legend


def test_res_fix3_no_role_line_blames_n_for_another_cause(est, syn):
    """brief-fix F3: a stand-in anchor's role line gives its nominal anchor's cause; "holds too few events" only
    where N was the cause."""
    checked = 0
    cases = [(name, _load(name), est["fixtures"][name]) for name in RES_EST]
    cases += [(name, syn["payloads"][name], syn["fixtures"][name]) for name in syn["payloads"]]
    for name, payload, entry in cases:
        symbol = payload["estimator"].get("symbol") or "σ/E"
        subs = {(s["key"], sub["used"]): sub for s in payload["series"]
                for sub in s["fits"]["anchors"].get("substitutions") or [] if sub["used"] is not None}
        for view, mode, p in _fix3_point_tips(entry):
            tip = _plain(p["tip"])
            sub = subs.get((p["key"], p["bin"])) if mode == "anchors" else None
            if sub is None:
                assert "holds too few events" not in tip, (name, view, mode, p["key"], p["bin"])
                continue
            checked += 1
            words = _CAUSE_WORDS[sub["cause"]].format(symbol=symbol)
            assert any(r.startswith("anchor of this mode, standing in for the nominal anchor ") and r.endswith(words)
                       for r in _fix3_roles(p["tip"])), (name, sub["cause"], tip)
            assert ("holds too few events" in tip) == (sub["cause"] == "n"), (name, sub["cause"])
    assert checked > 0
    assert {name.rsplit("_", 1)[-1] for name in syn["payloads"] if name.startswith("syn_median_cause_")} >= {"tied", "withheld"}


def test_res_fix3_the_tail_share_from_n_300_and_never_at_iqr_zero(syn):
    """brief-fix F5, F6, on the synthetic windows: a finite share against 0.27% for a large Gaussian sample; at
    N ≥ 300 with no share, the IQR = 0 sentence."""
    payload = syn["payloads"]["syn_median_tail"]
    windows = _windows(payload)
    seen = {"share": 0, "iqr": 0}
    for view, mode, p in _fix3_point_tips(syn["fixtures"]["syn_median_tail"]):
        w = windows[(p["key"], p["bin"])]
        tip = _plain(p["tip"])
        if w["tail_share"] is not None:
            seen["share"] += 1
            assert "4.31% of events beyond 3 robust σ (0.27% for a large Gaussian sample)" in tip
        elif w["n"] >= 300:
            seen["iqr"] += 1
            assert ("share beyond 3 robust σ not reported: the window's IQR is 0, so there is no robust σ to measure it "
                    "in") in tip
            assert "not reported below N = 300" not in tip
    assert seen["share"] and seen["iqr"]


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_fix3_colour_is_the_series_and_the_status_names_no_estimator(est, name):
    """R-ui m8: the legend says "Colour is the series", since the Estimator control is not encoded by colour; R-ui n4:
    a fit table's plain status is "N ≥ 20 throughout" (no-break spaces kept), never "robust (N ≥ 20)", which read as
    the robust estimator under the other two."""
    entry = est["fixtures"][name]
    plain = "N ≥ 20 throughout"
    statuses = 0
    for view, key, notes in _fix3_drawers(entry):
        legend = notes["sections"]["Marks and legend"]
        assert sum(line.startswith("Colour is the series: ") for line in legend) == 1, (view, key)
        assert not any("Colour is the estimator" in line for line in _fix3_lines(notes))
    for view in ("linear", "energy"):
        for e in entry[view].values():
            assert not any("robust (N" in t for t in e["table"])
            statuses += sum(t == plain for t in e["table"])
    # A fit with nothing else to say: not provisional, not a misfit, converged and, if affine, b ≥ 0.
    plain_fits = [(s["key"], m, f) for s in _load(name)["series"] for m in ("anchors", "all")
                  for f in ("affine", "pinned", "quadrature")
                  if (fit := s["fits"][m][f]) and not s["fits"][m].get("provisional") and not fit.get("misfit")
                  and fit.get("converged") is not False and not (f == "affine" and fit.get("negative_intercept"))]
    assert (statuses > 0) == bool(plain_fits), (statuses, plain_fits)


@pytest.mark.parametrize("name", list(RES_EST))
def test_res_e_the_mode_line_names_both_floors(est, name):
    """The E view's "Mode drawn" line (the lead's fix of N-jstests' F4, 2026-11-13). All windows names both floors, a₀/√E
    from 4 GeV and a/√E ⊕ b ⊕ c/E from 1 GeV, never "every window from 4 GeV", which is the 1/√E view's; the 3-anchor
    mode names the low anchor exactly when a series on show has one."""
    payload = _load(name)
    low = any((s["fits"]["anchors"]["noise"] or {}).get("low_anchor") is not None for s in payload["series"])
    for key, e in est["fixtures"][name]["energy"].items():
        windows = key.split(":")[0]
        lines = [line for sec in e["notes"]["sections"].values() for line in sec if line.startswith("Mode drawn: ")]
        assert len(lines) == 1, key
        if windows == "all":
            assert lines[0].startswith("Mode drawn: every window; a₀/√E fits those from 4 GeV and a/√E ⊕ b ⊕ c/E those "
                                       "from 1 GeV, each with N ≥ "), (key, lines[0])
        else:
            assert ("with the low anchor of a/√E ⊕ b ⊕ c/E" in lines[0]) == low, (key, lines[0])
        assert "every window from 4 GeV" not in lines[0], key


@pytest.mark.parametrize("name", ["res_scaling_single_hits", "res_scaling_single_events"])
def test_res_e_a_reference_band_beyond_the_axis_is_said_never_listed_as_drawn(est, name):
    """F5 (the lead's fix of N-jstests' finding, 2026-11-13) said a deposit reference's band about 1 wider than the
    whole ratio axis lay beyond it. With no band about 1 (Martin's directive of 2026-11-15) the case is gone: in the
    sample single-shower recordings' 3-anchor E view with both literature curves off, which reached it, the 1.0 rule's
    tooltip names the reference alone, and no drawer line or tooltip of any recording or state speaks of a reference
    band, beyond the axis or drawn as edges."""
    e = est["fixtures"][name]["energy"]["anchors:none"]
    unity = [_plain(t) for s in e["series"] if s["grid"] == 1 and s["name"] == "ratio = 1" for t in s["tips"]]
    assert len(unity) == 1 and unity[0].startswith("ratio = 1 σ/E equal to the reference: the deposit a/√E ⊕ b ⊕ c/E fit.")
    assert "band" not in unity[0] and "beyond the ratio axis" not in unity[0]
    for other, entry in est["fixtures"].items():
        for key, e2 in entry["energy"].items():
            lines = [x for sec in e2["notes"]["sections"].values() for x in sec]
            assert not [x for x in lines if "lies beyond the ratio axis" in x or "reference band" in x], (other, key)
            tips = [_plain(t) for s in e2["series"] if s["grid"] == 1 for t in s["tips"]]
            assert not [t for t in tips if "reference band" in t or "own 95% band" in t], (other, key)


# ---- res-noise fix round (brief-fix, 2026-11-13): FX1–FX3 and the review's minors and nits ----------------------------
# FX1's envelope band was retired with every band of the E view by the single-curve round (Martin's directive of
# 2026-11-15): its two tests are retargeted at what replaced them.


def test_res_sc_the_fx1_band_texts_left_the_panel(out, est):
    """FX1's band sentences (`noiseBandText`: the envelope, and the conditional band where the free face was
    singular) and the conditional-band text and band tooltip (`noiseConditionalText`, `energyBandTip`) are no longer
    exported, and no E-view text of any recording, estimator, mode or literature state carries their words."""
    assert out["resE"]["noise"]["retiredExports"] == []
    for name, entry in est["fixtures"].items():
        for key, e in entry["energy"].items():
            texts = [_plain(t) for t in _every_text({"linear": {}, "energy": {key: e}})]
            for banned in ("envelope", "The band is conditional on", "all three terms free", FX1_SINGULAR_TAIL.strip(": ")):
                assert not [t for t in texts if banned in t], (name, key, banned)


#: brief-fix §Words: the singular-face sentence's tail (retired; kept to pin its absence).
FX1_SINGULAR_TAIL = ": the fit with all three terms free cannot be solved through these windows."


def test_res_sc_an_old_recordings_band_fields_change_nothing(out):
    """FX1's case with no free face is gone with the free face. What it protected, that the band a block carries is
    the one drawn and said, becomes: a recording from before the single-curve round (`params.free` on every block that
    holds a term, the noise block's `band_quantile`, `weight_scale.c_low` / `n_low`) draws exactly what the new wire
    draws. On the two-shower copy: the noise line equals the recording's at every energy, and the curve's tooltips and
    the drawer's held lines carry the held terms alone, never a band sentence. On all twelve recordings: both views'
    charts, tooltips, tables and drawers are unchanged, and no c_low value is printed."""
    payload = {s["key"]: s for s in _load("res_scaling_two")["series"]}
    sing = out["resE"]["noise"]["singular"]
    assert sing["curves"]
    for key, got in sing["curves"].items():
        assert got["js"] == got["base"] and {len(r) for r in got["js"]} == {2}, key
    seen = 0
    for mode in ("anchors", "all"):
        case = sing[mode]
        held_lines = [x for sec in case["notes"]["sections"].values() for x in sec if " held at 0 by the constraint" in x]
        for skey, s in payload.items():
            nf = s["fits"][mode]["noise"]
            if not nf or not nf["params"]["held"]:
                continue
            tips = [_plain(tip) for sid, items in case["noiseTips"].items() if sid.startswith(f"{skey}|noise|") for tip in items]
            assert tips and not [t for t in tips if "The band is" in t or "envelope" in t], (mode, skey)
            assert not [sid for sid in case["noiseTips"] if "|band|" in sid or "|edges|" in sid]
            assert [x for x in held_lines if x.startswith(f"{s['label']}: ")] == [_held_line(s["label"], nf["params"]["held"])], (mode, skey)
            seen += 1
        assert not [x for sec in case["notes"]["sections"].values() for x in sec if "envelope" in x or "c_low" in x], mode
    assert seen > 0
    old = out["resE"]["fixRound"]["oldWire"]
    assert sorted(old) == RES_ALL
    for name, got in old.items():
        assert got["same"] and got["touched"] > 0 and not got["cLow"], name


def test_res_fx1_no_band_sentence_says_exact_on_screen_or_in_the_drawer(est):
    """brief-fix FX1 §Words: "exact" goes from every band sentence, on every tooltip, canvas text, table and drawer of
    every recording, estimator, mode and literature state; nor does any text say "no delta method"."""
    for name, entry in est["fixtures"].items():
        texts = list(_every_text(entry))
        assert not _exact_band_sentences(texts), name
        assert not any("no delta method" in _plain(t) for t in texts), name


def test_res_fx3_no_client_code_reads_the_removed_fields(out):
    """brief-fix FX3: no client module names the quadrature `rho_a2b2`, `se_a2_stat` or `se_b2_stat`, or filters the
    retired definition note ("the E view's second curve"); and with every removed field put back on three recordings
    (each fit block's and noise block's `note` a sentinel, the three quadrature numbers arbitrary) both views' charts,
    tooltips, tables and drawers are unchanged, so nothing reads them."""
    for name, got in out["resE"]["fixRound"]["removedFields"].items():
        assert got["same"] and not got["sentinel"] and got["length"] > 0, name
    removed = re.compile(r"rho_a2b2|se_a2_stat|se_b2_stat|the E view's second cur")
    hits = []
    for path in sorted(JS.rglob("*.js")):
        # The vendored libraries and the article's prose (which may describe the form in words) are not client readers.
        if "vendor" in path.parts or "methodology" in path.parts:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if removed.search(line):
                hits.append(f"{path.relative_to(JS)}:{i}: {line.strip()}")
    assert not hits, hits


def test_res_m1_a_window_the_noise_fit_uses_is_never_not_fitted(out):
    """Review m1: the E-view drawer counts a weak window as fitted when the noise fit uses it, so a 1–4 GeV window of
    N < 20 that only a/√E ⊕ b ⊕ c/E runs through is never in the "not fitted" line."""
    seen = 0
    for name, key, rec in _e_notes(out):
        p = rec["facts"]["points"]
        dis = _lines(rec["notes"], out, "disclosures")
        alone = [line for line in dis if line.endswith("χ² whisker, not fitted.")]
        if p["weakNoiseOnly"]:
            seen += 1
            assert len(alone) == (1 if p["weakAlone"] else 0), (name, key)
            if alone:
                assert alone[0].startswith(_n(p["weakAlone"], "window") + " of N < 20"), (name, key)
    assert seen > 0, "single_events draws a weak window the noise fit alone uses"


def test_res_m2_the_e_view_says_from_4_gev(est):
    """Review m2: the other fits' provisional rule is decided on the windows from 4 GeV, so on the E view, whose noise
    fit reaches 1 GeV, every provisional sentence says "fewer than two windows from 4 GeV reach N = 20"; the 1/√E view's
    sentences, true there, keep "fewer than two windows reach N = 20"."""
    old, new = "fewer than two windows reach N = ", "fewer than two windows from 4 GeV reach N = "
    said = {"energy": 0, "linear": 0}
    for name, entry in est["fixtures"].items():
        energy = [_plain(t) for e in entry["energy"].values() for t in _every_text({"linear": {}, "energy": {"x": e}})]
        linear = [_plain(t) for e in entry["linear"].values() for t in _every_text({"energy": {}, "linear": {"x": e}})]
        assert not [t for t in energy if old in t], name
        assert not [t for t in linear if new in t], name
        said["energy"] += sum(new in t for t in energy)
        said["linear"] += sum(old in t for t in linear)
    assert said["energy"] > 0 and said["linear"] > 0


#: A term printed as "t = v ± se unit" (review m4): never with se > v.
_TERM = re.compile(r"(?<![\w²])([abc]) = ([\d.]+) ± ([\d.]+) %")


def test_res_m4_no_term_is_printed_with_an_error_larger_than_itself(est):
    """Review m4: a free term of the noise or quadrature form whose SE exceeds it is printed as its square with the
    square's SE, in the fit table and the noise tooltip, so no "t = v ± se" anywhere has se > v; and the squares are
    printed (the recordings hold such terms)."""
    squares = lines = 0
    for name, entry in est["fixtures"].items():
        for t in _every_text(entry):
            # The noise tooltip's term line (the affine a and b may be negative and are not under the rule).
            for line in (x for x in str(t).split("<br/>") if "the noise term c/E: c" in x):
                text = _plain(line)
                lines += 1
                for term, v, se in _TERM.findall(text):
                    assert float(se) <= float(v), (name, text)
                squares += len(re.findall(r"(?<![\w])[abc]² = [\d.]+ ± [\d.]+ %²", text))
    assert lines > 0 and squares > 0


def test_res_m7_an_entry_at_the_axis_line_says_so_on_its_caret_and_in_the_drawer(est):
    """Review m7: a noise curve entering below x.max·10⁻³ runs up the axis line; its caret's tooltip ends with the
    brief's sentence and the drawer's entering line carries it in brackets, once per such curve, and no other text does."""
    seen = 0
    for name, entry in est["fixtures"].items():
        x_max = _load(name)["axis"]["energy"]["x"]["max"]
        for key, e in entry["energy"].items():
            near = [n for n in e["noise"] if n["entry"] and not n["entry"]["above"] and n["entry"]["lineAt"] is not None
                    and n["entry"]["at"] < x_max * 1e-3]
            assert all(n["entry"]["atAxis"] for n in near)
            assert sum(bool(n["entry"] and n["entry"].get("atAxis")) for n in e["noise"]) == len(near), (name, key)
            carets = [_plain(t) for sx in e["series"] if (sx["id"] or "").endswith("|carets") and "|ratio|" not in sx["id"]
                      for t in sx["tips"] if "comes down into the plot" in t]
            assert sum(c.endswith(NOISE_AXIS_LINE) for c in carets) == len(near), (name, key)
            text = " ".join(x for sec in e["notes"]["sections"].values() for x in sec)
            assert text.count(f"({NOISE_AXIS_LINE[:-1]})") == len(near), (name, key)
            for n in near:
                assert f"{n['label']} at E = {_sf(n['entry']['lineAt'])} GeV, through its " in text, (name, key)
            seen += len(near)
    assert seen > 0, "median_xgb and xgb enter at 0.00236 GeV"


def test_res_nit1_a_declined_window_the_noise_fit_uses_says_it_is_declined(out):
    """Review nit 1: under Robust σ (IQR), all windows, a window from 4 GeV that a₀/√E declines (its one fittable
    window) while the noise fit uses it reads "fitted by a/√E ⊕ b ⊕ c/E only; declined by a₀/√E: …", never the false
    "a₀/√E uses windows from 4 GeV"."""
    d = out["resE"]["fixRound"]["declined"]
    assert d is not None
    lead = f"fitted by a/√E ⊕ b ⊕ c/E only; declined by a₀/√E: {d['declinedText']}"
    assert d["declinedText"] == (f"Robust σ (IQR) fits no line through fewer than two fittable windows, and only {d['label']} "
                                 f"(N = {d['n']}) is fittable here")
    assert d["roles"][0] == lead
    assert not [r for r in d["roles"] if "a₀/√E uses windows from 4 GeV" in r]
    assert lead in _plain(d["tip"])


def test_res_nit4_the_e_view_names_a0_where_the_1_over_sqrt_e_view_says_this_mode(est):
    """Review nit 4: the 4–5 GeV note of the all-windows mode reads "a₀/√E fits every window from 4 GeV …" on the E view,
    where the noise fit reaches 1 GeV, and keeps "This mode fits every window from 4 GeV …" on the 1/√E view."""
    seen = {"energy": 0, "linear": 0}
    for name, entry in est["fixtures"].items():
        for view in ("energy", "linear"):
            for e in entry[view].values():
                lines = [x for sec in e["notes"]["sections"].values() for x in sec]
                hits = [x for x in lines if "fits every window from 4 GeV, 4–5 GeV included" in x]
                want = "a₀/√E fits every window from 4 GeV" if view == "energy" else "This mode fits every window from 4 GeV"
                assert all(x.startswith(want) for x in hits), (name, view, hits)
                if view == "energy":
                    assert not [x for x in lines if "This mode fits every window from" in x], name
                seen[view] += len(hits)
    assert seen["energy"] > 0 and seen["linear"] > 0


def test_res_nit8_the_robust_floor_line_prints_no_zero_count(out):
    """Review nit 8: robustFloorLine prints each clause only where its count is above 0: with no window of 2 ≤ N < 20
    left without a value (a synthetic robust copy), no drawer says "0 windows …" or speaks of that floor's windows,
    while the recording itself still says it once per drawer."""
    clause = re.compile(r"\bwindows? of 2 ≤ N < 20 ha(?:s|ve) no Robust σ/E")
    for n in out["resE"]["fixRound"]["noThin"]:
        lines = [x for sec in n["sections"].values() for x in sec]
        assert not [x for x in lines if clause.search(x)]
        assert not [x for x in lines if re.search(r"(?<![\d.,])0 windows?\b", x)], lines
        assert all(x.strip() for x in lines), "no empty line where the robust floor line has nothing to say"
    for n in out["resE"]["fixRound"]["thin"]:
        lines = [x for sec in n["sections"].values() for x in sec]
        assert len([x for x in lines if clause.search(x)]) == 1
        assert not [x for x in lines if re.search(r"(?<![\d.,])0 windows?\b", x)]


# ---- the single-curve round (Martin's directive of 2026-11-15): structural pins over the twelve recordings ------------
#
# D1: one fitted curve per series and panel on the E view, a/√E ⊕ b ⊕ c/E where the series has a drawable one, else its
# origin-pinned a₀/√E from 4 GeV at 1 px, else none. D2: no band of any kind on the E view. Built as the golden builds
# them: `energyViewOption`, every renderItem with the identity api.coord (`walk`), every tooltip and caret formatter
# called per datum. The JS side reduces each case to its structure and to the texts that carry a watched word, so the
# Python side holds every case without shipping every tooltip.

_SC_BODY = r"""
const sc = { cases: [], fallback: [], neither: [], exports: {}, decline: null };
const RE = { width: 760, height: 600 };
const LITS = [[], ['pi'], ['e'], ['pi', 'e']];
const WATCH = /band|envelope|c_low|all three terms free|conditional on/i;
const NO_REASON = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.';
const names = fs.readdirSync(fixtureDir).filter((f) => /^res_scaling_.*\.json$/.test(f)).map((f) => f.slice(0, -5)).sort();
const notesLines = (n) => (n ? n.sections.flatMap((sec) => sec.lines) : []);
// Every text one E-view case shows: every tooltip of every datum (carets included), canvas text, axis text and legend.
const caseOf = (payload, opts, tag) => {
  const model = rs.energyModel(payload, opts);
  const built = rs.energyViewOption(payload, opts, RE).option;
  const w = walk(built);
  const ids = built.series.map((x) => x.id ?? '');
  const families = (key, ratio) => [...new Set(ids.map((id) => {
    const m = ratio ? id.match(new RegExp(`^${key.replace(/[|]/g, '\\|')}\\|ratio\\|([a-z]+)\\|(solid|dashed|band|edges)\\|`))
      : id.match(new RegExp(`^${key.replace(/[|]/g, '\\|')}\\|([a-z]+)\\|(solid|dashed|band|edges|line)\\|`));
    return m ? m[1] : null;
  }).filter(Boolean))];
  // The width of a drawn curve's runs (× lineAxis), and the least E it reaches, from the rendered polylines.
  const runsOf = (key, form, ratio) => built.series.filter((x) => new RegExp(`^${key.replace(/[|]/g, '\\|')}${ratio ? '\\|ratio' : ''}\\|${form}\\|(solid|dashed)\\|`).test(x.id ?? ''))
    .map((x) => { const el = x.renderItem({ dataIndex: 0, coordSys }, api); return { width: el.style.lineWidth / scale.THEME.lineAxis, minE: Math.min(...el.shape.points.map((p) => p[0])),
      dash: el.style.lineDash ?? null, part: x.id.split('|').at(-2), tip: x.tooltip.formatter({ dataIndex: 0 }) }; });
  const notes = mn.resolutionScalingNotes({ payload, view: 'energy', ...opts });
  const lines = notesLines(notes);
  const texts = [...w.strings];
  return {
    tag, windows: opts.windows, shower: opts.shower, literature: opts.literature, reference: model.reference.key,
    ids, bandIds: ids.filter((id) => /\|band\||\|edges\||\|reference\|/.test(id)),
    series: model.series.map((s) => ({
      key: s.key, label: s.label, drawnForm: s.drawnForm,
      drawable: { noise: s.fits.noise.drawable, pinned: s.fits.pinned.drawable, quadrature: s.fits.quadrature.drawable },
      pinnedReason: s.fits.pinned.reason ?? null, noiseReason: s.fits.noise.reason ?? null,
      mainRuns: s.drawn ? s.drawn.solid.length + s.drawn.dashed.length : 0,
      ratioRuns: s.drawn?.ratio ? s.drawn.ratio.solid.length + s.drawn.ratio.dashed.length : 0,
      mainFamilies: families(s.key, false), ratioFamilies: families(s.key, true),
      runs: s.drawn ? runsOf(s.key, s.drawnForm, false) : [], ratioRunsDrawn: s.drawn ? runsOf(s.key, s.drawnForm, true) : [],
      fallback: s.drawn?.fallback ?? null, noiseReasonClause: s.drawn?.noiseReason ?? null,
    })),
    curveMinGev: model.curveMinGev,
    watched: [...new Set(texts.filter((t) => WATCH.test(t)))],
    drawerWatched: lines.filter((t) => WATCH.test(t)),
    drawer: lines,
    hazards: notes?.hazards ?? [],
    ratioWhiskers: model.series.flatMap((s) => s.points).filter((p) => p.ratio.drawn && Number.isFinite(p.ratio.lo)).length,
  };
};
for (const name of names) {
  const payload = load(name);
  for (const windows of ['anchors', 'all']) {
    for (const literature of LITS) {
      for (const shower of ['both', 'a', 'b']) {
        if (shower !== 'both' && !payload.series.some((s) => s.shower === shower)) continue;
        sc.cases.push({ name, ...caseOf(payload, { windows, shower, literature }, 'recording') });
      }
    }
  }
  // Each series with a noise fit, as a copy without it (its noise blocks removed, the server's reason served): its
  // a₀/√E is the fallback where drawable. And as a copy without its a₀/√E either: no curve, and the drawer says why.
  for (const s0 of payload.series) {
    if (!['anchors', 'all'].some((m) => s0.fits[m].noise)) continue;
    for (const [list, strip] of [[sc.fallback, ['noise']], [sc.neither, ['noise', 'pinned']]]) {
      const copy = clone(payload);
      const sx = copy.series.find((x) => x.key === s0.key);
      for (const m of ['anchors', 'all']) {
        for (const k of strip) sx.fits[m][k] = null;
        sx.fits[m].noise_reason = NO_REASON;
      }
      for (const windows of ['anchors', 'all']) {
        for (const literature of [[], ['pi', 'e']]) {
          for (const shower of ['both', s0.shower ?? 'both']) {
            list.push({ name, key: s0.key, ...caseOf(copy, { windows, shower, literature }, list === sc.fallback ? 'fallback' : 'neither') });
          }
        }
      }
    }
  }
}
// The lead's fix (29c3ae8): a robust series that declines the fits from 4 GeV but draws its noise curve
// (scratch/lead_checks/decline_and_drawers.mjs): every other fittable window from 4 GeV thinned to N = 10.
{
  const payload = load('res_scaling_robust_two');
  const s = payload.series.find((x) => x.fits?.all?.noise);
  const keep = s.windows.filter((w) => w.p_lo >= 4 && w.eligible).sort((a, b) => b.n - a.n)[0];
  for (const w of s.windows) if (w.p_lo >= 4 && w !== keep) { w.n = 10; w.eligible = false; }
  s.fits.all.points = [];
  for (const k of ['affine', 'pinned', 'quadrature']) s.fits.all[k] = null;
  const energy = notesLines(mn.resolutionScalingNotes({ payload, windows: 'all', shower: 'both', view: 'energy', literature: [] }));
  const linear = notesLines(mn.resolutionScalingNotes({ payload, windows: 'all', shower: 'both', view: 'linear' }));
  const model = rs.energyModel(payload, { windows: 'all', shower: 'both', literature: [] });
  sc.decline = { key: s.key, label: s.label, keep: { bin: keep.bin, label: keep.label, n: keep.n }, declined: rs.declinedText(keep),
    noisePoints: s.fits.all.noise.points, drawnForm: model.series.find((x) => x.key === s.key).drawnForm,
    energy: energy.filter((l) => l.includes('fits no line through fewer than two fittable windows')),
    linear: linear.filter((l) => l.includes('fits no line through fewer than two fittable windows')) };
}
sc.exports = { noBand: rs.ENERGY_NO_BAND_TEXT, forms: rs.ENERGY_FORMS };
console.log(JSON.stringify(sc));
"""


@pytest.fixture(scope="module")
def sc() -> dict:
    """The single-curve harness: the panel's helpers of `_SCRIPT` (`walk`, the identity api.coord), then `_SC_BODY`."""
    prelude = _script()
    prelude = prelude[:prelude.index("const out = { perf")]
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", prelude + _SC_BODY, args],
                          capture_output=True, text=True, timeout=600, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


#: The literature lines that may say "band" on the E view: a literature curve carries no interval, so none is drawn.
SC_LITERATURE_BAND = re.compile(r"no band is drawn for it|no band about 1 is drawn, since the literature curve has no interval "
                                r"reported|The ratio panel draws no band about 1 for it: no interval reported", re.I)
#: The drawer's one no-band sentence (SC-notes, 2026-11-15).
SC_DRAWER_NO_BAND = ("No band is drawn round a fitted curve on this view: each curve's tooltip and the fit table give its "
                     "terms with their standard errors, χ²/ν and S, and every window keeps its whisker.")
SC_BANNED = ("envelope", "c_low", "all three terms free", "confidence band")


def _sc_strip(text: str) -> str:
    """A text with its sanctioned band sentences taken out: the no-band tooltip and drawer sentences and the
    literature lines."""
    text = _plain(text).replace(ENERGY_NO_BAND_TEXT, "").replace(SC_DRAWER_NO_BAND, "")
    return SC_LITERATURE_BAND.sub("", text)


def _sc_all(sc: dict):
    yield from sc["cases"]
    yield from sc["fallback"]
    yield from sc["neither"]


def test_sc_the_harness_covers_every_recording_mode_literature_state_and_shower(sc):
    """12 recordings × anchors/all × literature [], π±, e±, both × shower both/a/b (a and b on the two-shower ones)."""
    names = {c["name"] for c in sc["cases"]}
    assert sorted(names) == RES_ALL and len(RES_ALL) == 12
    for name in RES_ALL:
        showers = {s["shower"] for s in _load(name)["series"]}
        want = 2 * 4 * (1 + len({"a", "b"} & showers))
        assert len([c for c in sc["cases"] if c["name"] == name]) == want, name
    assert sc["fallback"] and sc["neither"]


def test_sc_one_fitted_curve_family_per_series_and_panel(sc):
    """D1: on each panel a series has at most one fitted-curve family (`<key>|noise|…` or `<key>|pinned|…`, on the ratio
    panel `<key>|ratio|<form>|…`), exactly one where its drawn curve has runs there, and it is its drawn form: noise
    wherever the series has a drawable noise fit, pinned only where it has none. Never the quadrature or affine form."""
    seen = {"noise": 0, "pinned": 0, "none": 0, "ratio": 0}
    for c in _sc_all(sc):
        where = (c["tag"], c.get("name"), c["windows"], c["shower"], tuple(c["literature"]))
        for s in c["series"]:
            d = s["drawable"]
            assert not d["quadrature"], where
            assert not (d["noise"] and d["pinned"]), (where, s["key"], "never two drawable fits")
            want = "noise" if d["noise"] else ("pinned" if d["pinned"] else None)
            assert s["drawnForm"] == want, (where, s["key"])
            if d["noise"]:
                assert s["pinnedReason"] == "table only on this view: the a/√E ⊕ b ⊕ c/E curve is drawn", (where, s["key"])
            assert len(s["mainFamilies"]) <= 1 and len(s["ratioFamilies"]) <= 1, (where, s["key"], s["mainFamilies"], s["ratioFamilies"])
            assert s["mainFamilies"] == ([want] if s["mainRuns"] else []), (where, s["key"], s["mainFamilies"])
            assert s["ratioFamilies"] == ([want] if s["ratioRuns"] else []), (where, s["key"], s["ratioFamilies"])
            seen[want or "none"] += 1
            seen["ratio"] += bool(s["ratioRuns"])
    assert min(seen.values()) > 0, seen


def test_sc_no_band_series_anywhere_on_the_e_view(sc):
    """D2: no series id carries '|band|', '|edges|' or '|reference|' (the deposit reference's band about 1 and its
    caret included), in any recording, mode, literature state, shower, fallback or no-curve copy."""
    for c in _sc_all(sc):
        assert c["bandIds"] == [], (c["tag"], c.get("name"), c["windows"], c["shower"], c["literature"], c["bandIds"])


def test_sc_no_tooltip_or_drawer_speaks_of_a_band_but_the_sanctioned_sentences(sc):
    """D2's words: no E-view tooltip, caret tooltip, canvas or axis text or drawer line contains "envelope", "c_low",
    "all three terms free" or "confidence band"; "band" appears only in ENERGY_NO_BAND_TEXT, the drawer's one no-band
    sentence and the literature lines. The tooltip sentence is on every drawn curve's tooltip and the drawer
    sentence in every drawer whose view draws a curve, once."""
    for c in _sc_all(sc):
        where = (c["tag"], c.get("name"), c["windows"], c["shower"], c["literature"])
        for t in c["watched"] + c["drawerWatched"]:
            plain = _plain(t)
            assert not [b for b in SC_BANNED if b in plain.lower()], (where, plain)
            assert "band" not in _sc_strip(plain).lower(), (where, plain)
            # "conditional on" survives only as the ratio's dependence on its reference and the ρ sentence's held terms.
            for m in re.finditer(r"conditional (only )?on (\S+ \S+)", plain):
                assert m.group(2) in ("the reference,", "the reference:", "the held", "a fit", "a form"), (where, plain)
        drawn = [s for s in c["series"] if s["drawnForm"]]
        if drawn:
            assert c["drawer"].count(SC_DRAWER_NO_BAND) == 1, where
            for s in drawn:
                assert all(ENERGY_NO_BAND_TEXT in _plain(r["tip"]) for r in s["runs"]), (where, s["key"])
            assert any(s["runs"] for s in drawn) or all(not s["mainRuns"] for s in drawn), where
        assert not [h for h in c["hazards"] if "band" in h], (where, c["hazards"])


def test_sc_a_fallback_series_draws_a0_from_4_gev_at_1_px_and_says_why(sc):
    """D1's fallback: a copy of a recording without one series' noise blocks (the server's noise_reason served) draws
    that series' a₀/√E where it has one: from 4 GeV, at 1 × lineAxis (the noise curve 1.6), solid over its windows and
    dashed beyond, each run's tooltip saying the series has no a/√E ⊕ b ⊕ c/E fit and why; the drawer says so once."""
    reason = "No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight."
    clause = reason.removeprefix("No a/√E ⊕ b ⊕ c/E fit: ").removesuffix(".")
    seen = 0
    for c in sc["fallback"]:
        where = (c["name"], c["key"], c["windows"], c["shower"], c["literature"])
        s = next((x for x in c["series"] if x["key"] == c["key"]), None)
        if s is None:
            continue
        if not s["drawable"]["pinned"]:
            assert s["drawnForm"] is None, where
            continue
        assert s["drawnForm"] == "pinned" and s["fallback"] is True and s["noiseReasonClause"] == clause, where
        if not s["runs"]:
            continue
        for r in s["runs"] + s["ratioRunsDrawn"]:
            assert r["width"] == pytest.approx(1.0), (where, r)
            assert r["minE"] >= c["curveMinGev"] - 1e-9, (where, r)
            assert (r["dash"] is not None) == (r["part"] == "dashed"), (where, r)
            assert (f"This series has no a/√E ⊕ b ⊕ c/E fit ({clause}), so its origin-pinned a₀/√E is drawn instead, "
                    f"from {_sf(c['curveMinGev'])} GeV.") in _plain(r["tip"]) or r in s["ratioRunsDrawn"], (where, r["tip"])
        assert c["curveMinGev"] == 4
        lines = [x for x in c["drawer"] if x.startswith(f"{s['label']}: {reason} Its origin-pinned a₀/√E ⊕ 0 is drawn instead, from 4 GeV")]
        assert len(lines) == 1 and lines[0].endswith("as the thinner line."), (where, lines)
        seen += 1
    assert seen > 0
    # The noise curve, where drawn, is the thicker line.
    widths = [r["width"] for c in sc["cases"] for s in c["series"] if s["drawnForm"] == "noise" for r in s["runs"] + s["ratioRunsDrawn"]]
    assert widths and all(w == pytest.approx(1.6) for w in widths)


def test_sc_a_series_with_neither_fit_draws_nothing_and_the_drawer_says_why(sc):
    """With neither a noise nor a pinned fit, a series draws no curve on either panel, and the drawer says why: the
    server's noise reason and the a₀/√E's own. The robust single-shower recordings serve it too (no noise fit, and no
    a₀/√E through a single fittable window)."""
    reason = "No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight."
    seen = 0
    for c in sc["neither"]:
        where = (c["name"], c["key"], c["windows"], c["shower"], c["literature"])
        s = next((x for x in c["series"] if x["key"] == c["key"]), None)
        if s is None:
            continue
        assert s["drawnForm"] is None and not s["mainFamilies"] and not s["ratioFamilies"] and not s["runs"], where
        lines = [x for x in c["drawer"] if x.startswith(f"{s['label']}: no fitted curve is drawn. {reason} ")]
        assert len(lines) == 1 and "Its origin-pinned a₀/√E ⊕ 0 has no curve either: " in lines[0], (where, lines)
        seen += 1
    assert seen > 0
    natural = [(c["name"], s["key"]) for c in sc["cases"] for s in c["series"] if s["drawnForm"] is None]
    assert natural, "a recording serves a series with neither fit"
    for c in sc["cases"]:
        for s in c["series"]:
            if s["drawnForm"] is None:
                assert [x for x in c["drawer"] if x.startswith(f"{s['label']}: no fitted curve is drawn. ")], (c["name"], s["key"])


def test_sc_the_leads_fixes_hold(sc):
    """The lead's fixes after Stages 1 and 2 (29c3ae8): ENERGY_NO_BAND_TEXT verbatim; the drawer's ratio-whisker
    sentence "it is conditional on the reference, …" wherever a ratio whisker is drawn; and on the E view a robust
    series that declines the fits from 4 GeV but draws its noise curve says the curve is drawn (never "so no fit is
    drawn"), while the 1/√E view keeps its own sentence."""
    assert sc["exports"]["noBand"] == ENERGY_NO_BAND_TEXT
    whiskered = 0
    for c in _sc_all(sc):
        lines = [x for x in c["drawer"] if x.startswith("A ratio whisker is ")]
        if c["ratioWhiskers"]:
            assert len(lines) == 1, (c["tag"], c.get("name"), c["windows"], c["shower"])
            assert ": it is conditional on the reference, " in lines[0] and lines[0].rstrip().endswith(
                ("and does not include the reference's own uncertainty.", "so none is carried.")), lines[0]
            whiskered += 1
        else:
            assert not lines
    assert whiskered > 0
    d = sc["decline"]
    assert d["drawnForm"] == "noise" and d["keep"]["bin"] in d["noisePoints"]
    among = f", {d['keep']['label']} among them"
    assert d["energy"] == [f"{d['label']}: {d['declined']}, so a₀/√E and the affine and quadrature fits are not fitted; its "
                           f"a/√E ⊕ b ⊕ c/E curve is drawn, through its own windows from 1 GeV{among}."]
    assert len(d["linear"]) == 1 and "a/√E ⊕ b ⊕ c/E curve is drawn" not in d["linear"][0]
    assert d["linear"][0].startswith(f"{d['label']}: {d['declined']}, so no ")


# ---- the single-curve round's fix round (review-ui, review-stats, review-docs; 2026-11-15) -----------------------------
#
# F1 (the E view toggle's title) is pinned in test_js_models_shell.py, the button titles' units there too. Here: F2/M3,
# the true cause of a missing fit from 4 GeV in the Fit and Status cells (19f6ab2, fa85fe8); F3, the "fit not
# converged" hazard reads the noise fit (28d58e5); F4, every ratio-panel curve tooltip carries the curve's terms, its
# χ²/ν line and the no-band sentence (19f6ab2); F5, a fallback a₀/√E above the top comes down into the plot, with an
# entry caret, never a cut, and its ratio takes the entry treatment (19f6ab2, fa85fe8); N1, the fallback's χ²/ν line
# writes S; the legend change (c406217): "π± lit. — σ/E = 27.2/√E ⊕ 1.0", the units in the tooltip and the drawer.

_FX_BODY = r"""
const fx = { tables: {}, hazards: [], ratioTips: [], entries: [], fallbackTips: [], literature: [] };
const RE = { width: 760, height: 600 };
const LITS = [[], ['pi'], ['e'], ['pi', 'e']];
const NO_REASON = 'No a/√E ⊕ b ⊕ c/E fit: fewer than three windows from 1 GeV hold N ≥ 20 with a fit weight.';
const names = fs.readdirSync(fixtureDir).filter((f) => /^res_scaling_.*\.json$/.test(f)).map((f) => f.slice(0, -5)).sort();
const notesLines = (n) => (n ? n.sections.flatMap((sec) => sec.lines) : []);
const tipsOf = (w, re) => w.series.filter((x) => re.test(x.id ?? '')).flatMap((x) => x.items.map((i) => i.tip)).filter(Boolean);
const esc = (key) => key.replace(/[|]/g, '\\|');
const stripNoise = (payload, key) => {
  const copy = clone(payload);
  const sx = copy.series.find((x) => x.key === key);
  for (const m of ['anchors', 'all']) { sx.fits[m].noise = null; sx.fits[m].noise_reason = NO_REASON; }
  return copy;
};

// F2/M3: both views' fit tables, the E model's pinned reason and the E drawer, per doctored state.
const tableCase = (payload, keys) => {
  const out = {};
  for (const windows of ['anchors', 'all']) {
    const o = { windows, shower: 'both' };
    const lin = rs.fitTableRows(payload, o);
    const en = rs.fitTableRows(payload, { ...o, view: 'energy' });
    const model = rs.energyModel(payload, { ...o, literature: [] });
    const drawer = notesLines(mn.resolutionScalingNotes({ payload, view: 'energy', ...o, literature: [] }));
    const rows = (t) => Object.fromEntries(t.rows.filter((r) => keys.includes(r.key)).map((r) => [r.key, Object.fromEntries(r.fits.map((f) => [f.form, f.cells]))]));
    out[windows] = {
      linear: rows(lin), energy: rows(en),
      model: Object.fromEntries(model.series.filter((s) => keys.includes(s.key)).map((s) => [s.key, {
        label: s.label, drawnForm: s.drawnForm, pinnedReason: s.fits.pinned.reason ?? null, pinnedDrawable: s.fits.pinned.drawable }])),
      drawer,
    };
  }
  return out;
};
{
  // A robust series that declines: the recordings of one shower, and the lead's copy of the two-shower recording
  // (every other fittable window from 4 GeV thinned to N = 10), which still draws its noise curve.
  for (const name of ['res_scaling_robust_single_hits', 'res_scaling_robust_single_events']) {
    fx.tables[name] = { payload: name, keys: ['detector:a'], ...tableCase(load(name), ['detector:a']) };
  }
  const rt = load('res_scaling_robust_two');
  const s = rt.series.find((x) => x.fits?.all?.noise);
  const keep = s.windows.filter((w) => w.p_lo >= 4 && w.eligible).sort((a, b) => b.n - a.n)[0];
  for (const w of s.windows) if (w.p_lo >= 4 && w !== keep) { w.n = 10; w.eligible = false; }
  s.fits.all.points = [];
  for (const k of ['affine', 'pinned', 'quadrature']) s.fits.all[k] = null;
  fx.tables.declineCopy = { payload: 'res_scaling_robust_two', keys: [s.key], declined: rs.declinedText(keep), ...tableCase(rt, [s.key]) };
  // c null: the recordings (median two-shower deposits, robust XGBoost) and a copy whose network A has no pooled
  // scale and no fit from 4 GeV, its noise fit kept (the reason holds whatever the noise fit does) or removed.
  fx.tables.medianTwo = { payload: 'res_scaling_median_two', keys: ['detector:a', 'detector:b'], ...tableCase(load('res_scaling_median_two'), ['detector:a', 'detector:b']) };
  fx.tables.robustXgb = { payload: 'res_scaling_robust_xgb', keys: ['xgb:a'], ...tableCase(load('res_scaling_robust_xgb'), ['xgb:a']) };
  for (const keepNoise of [true, false]) {
    const p = load('res_scaling_robust_two');
    const sx = p.series.find((x) => x.key === 'network:a');
    sx.weight_scale = { ...sx.weight_scale, c: null, n_windows: 0 };
    for (const m of ['anchors', 'all']) {
      for (const k of ['affine', 'pinned', 'quadrature']) sx.fits[m][k] = null;
      if (!keepNoise) { sx.fits[m].noise = null; sx.fits[m].noise_reason = NO_REASON; }
    }
    fx.tables[keepNoise ? 'cNullNoise' : 'cNull'] = { payload: 'res_scaling_robust_two', keys: ['network:a'], ...tableCase(p, ['network:a']) };
  }
  // Too few windows: a sample series (no pooled scale to miss) with no fit from 4 GeV, its noise fit kept.
  {
    const p = load('res_scaling_two');
    const sx = p.series.find((x) => x.key === 'network:a');
    for (const m of ['anchors', 'all']) for (const k of ['affine', 'pinned', 'quadrature']) sx.fits[m][k] = null;
    fx.tables.tooFew = { payload: 'res_scaling_two', keys: ['network:a'], ...tableCase(p, ['network:a']) };
  }
  // The fallback: the network A without its noise fit, its a₀/√E drawn.
  fx.tables.fallback = { payload: 'res_scaling_two', keys: ['network:a'], ...tableCase(stripNoise(load('res_scaling_two'), 'network:a'), ['network:a']) };
  // A recording with every fit in place: the cells as they were.
  fx.tables.plain = { payload: 'res_scaling_robust_two', keys: ['network:a'], ...tableCase(load('res_scaling_robust_two'), ['network:a']) };
}

// F3: the hazard on a copy whose drawn noise fit alone has converged: false, both views, both modes.
for (const name of names) {
  const payload = load(name);
  for (const s of payload.series) {
    for (const windows of ['anchors', 'all']) {
      if (!s.fits[windows].noise) continue;
      const copy = clone(payload);
      copy.series.find((x) => x.key === s.key).fits[windows].noise.converged = false;
      const o = { windows, shower: 'both' };
      const drawn = rs.energyModel(copy, { ...o, literature: [] }).series.find((x) => x.key === s.key).drawnForm;
      fx.hazards.push({ name, key: s.key, windows, drawn,
        base: { energy: mn.modelsHazards(payload, 'res-scaling', { ...o, view: 'energy', literature: [] }), linear: mn.modelsHazards(payload, 'res-scaling', o) },
        doctored: { energy: mn.modelsHazards(copy, 'res-scaling', { ...o, view: 'energy', literature: [] }), linear: mn.modelsHazards(copy, 'res-scaling', o) } });
    }
  }
}

// F4: every drawn curve's ratio tooltip beside its main-panel tooltip, on the recordings and the fallback copies.
const ratioCase = (payload, opts, tag, name) => {
  const model = rs.energyModel(payload, opts);
  const w = walk(rs.energyViewOption(payload, opts, RE).option);
  for (const s of model.series) {
    if (!s.drawn || !s.drawn.ratio) continue;
    const form = s.drawnForm;
    const fit = s.drawn.fit;
    fx.ratioTips.push({ tag, name, windows: opts.windows, literature: opts.literature, key: s.key, label: s.label, form,
      ndf: fit.ndf, p: fit.p_value, S: fit.scale_factor ?? null, chi2: fit.chi2,
      reference: model.reference.key, refLabel: s.reference?.label ?? null,
      ratio: tipsOf(w, new RegExp(`^${esc(s.key)}\\|ratio\\|${form}\\|(solid|dashed)\\|`)),
      main: tipsOf(w, new RegExp(`^${esc(s.key)}\\|${form}\\|(solid|dashed)\\|`)) });
  }
};
for (const name of names) {
  const payload = load(name);
  for (const windows of ['anchors', 'all']) {
    for (const literature of LITS) ratioCase(payload, { windows, shower: 'both', literature }, 'recording', name);
    for (const s of payload.series) {
      if (!s.fits[windows].noise) continue;
      for (const literature of [[], ['pi', 'e']]) ratioCase(stripNoise(payload, s.key), { windows, shower: 'both', literature }, 'fallback', name);
    }
  }
}

// F5 and N1: a fallback a₀/√E made to start above the top at 4 GeV (a₀ = 3·y.hi, entering at 9 GeV) or to lie above
// the whole axis (a₀ = 1.2·y.hi·√x.max), and as served (N1), on every recording series with a noise fit.
for (const name of names) {
  const payload = load(name);
  for (const s0 of payload.series) {
    for (const windows of ['anchors', 'all']) {
      if (!s0.fits[windows].noise || !s0.fits[windows].pinned) continue;
      for (const variant of ['served', 'above9', 'aboveAll']) {
        for (const literature of [[], ['pi', 'e']]) {
          const copy = stripNoise(payload, s0.key);
          const hi0 = copy.axis.energy.y.hi;
          const xmax0 = copy.axis.energy.x?.max ?? 80;
          const pin = copy.series.find((x) => x.key === s0.key).fits[windows].pinned;
          if (variant === 'above9') pin.params.a0 = 3 * hi0;
          if (variant === 'aboveAll') pin.params.a0 = 1.2 * hi0 * Math.sqrt(xmax0);
          const opts = { windows, shower: 'both', literature };
          const model = rs.energyModel(copy, opts);
          const ms = model.series.find((x) => x.key === s0.key);
          const f = ms.drawn;
          const w = walk(rs.energyViewOption(copy, opts, RE).option);
          const caretSeries = w.series.filter((x) => x.id === `${s0.key}|carets`);
          const ratioCarets = w.series.filter((x) => x.id === `${s0.key}|ratio|carets`);
          fx.entries.push({ name, key: s0.key, label: ms.label, windows, variant, literature,
            hi: model.y.hi, xMax: model.x.max, curveMin: model.curveMinGev, a0: pin.params.a0, ndf: pin.ndf, p: pin.p_value,
            drawnForm: ms.drawnForm, entry: f?.entry ?? null, cut: f?.cut ?? null, curve0: f?.curve?.[0] ?? null,
            curveMaxY: f?.curve?.length ? Math.max(...f.curve.map((r) => r[1])) : null, nCurve: f?.curve?.length ?? 0,
            full0: f?.full?.[0] ?? null, solid: f?.solid?.length ?? 0, dashed: f?.dashed?.length ?? 0,
            clipped: model.clipped,
            carets: caretSeries.flatMap((x) => x.items.map((i) => ({ at: i.value, tip: i.tip }))),
            mainTips: tipsOf(w, new RegExp(`^${esc(s0.key)}\\|pinned\\|(solid|dashed)\\|`)),
            ratio: f?.ratio ? { entry: f.ratio.entry, cut: f.ratio.cut, first: f.ratio.rows[0] ?? null, k: model.ratio.k,
              runs: f.ratio.solid.length + f.ratio.dashed.length,
              carets: ratioCarets.flatMap((x) => x.items.map((i) => ({ at: i.value, tip: i.tip }))),
              tips: tipsOf(w, new RegExp(`^${esc(s0.key)}\\|ratio\\|pinned\\|(solid|dashed)\\|`)) } : null,
            drawer: notesLines(mn.resolutionScalingNotes({ payload: copy, view: 'energy', ...opts })),
            hazards: mn.modelsHazards(copy, 'res-scaling', { ...opts, view: 'energy' }) });
        }
      }
    }
  }
}

// The legend change: the literature legend, tooltips and drawer on every recording with both curves on.
for (const name of names) {
  const payload = load(name);
  for (const windows of ['anchors', 'all']) {
    for (const literature of LITS) {
      const opts = { windows, shower: 'both', literature };
      const w = walk(rs.energyViewOption(payload, opts, RE).option);
      fx.literature.push({ name, windows, literature, legend: w.legend,
        litTips: Object.fromEntries(['pi', 'e'].map((k) => [k, tipsOf(w, new RegExp(`^literature\\|${k}$`))])),
        strings: w.strings,
        drawer: notesLines(mn.resolutionScalingNotes({ payload, view: 'energy', ...opts })) });
    }
  }
}
fx.exports = { noBand: rs.ENERGY_NO_BAND_TEXT, provenance: rs.LITERATURE_PROVENANCE };
console.log(JSON.stringify(fx));
"""


@pytest.fixture(scope="module")
def fx() -> dict:
    """The fix round's harness: the panel's helpers of `_SCRIPT` (`walk`, the identity api.coord), then `_FX_BODY`."""
    prelude = _script()
    prelude = prelude[:prelude.index("const out = { perf")]
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", prelude + _FX_BODY, args],
                          capture_output=True, text=True, timeout=600, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


#: fitMissingReason's three causes (19f6ab2), verbatim.
FX_DECLINED = "Robust σ (IQR) fits no line through fewer than two fittable windows"
FX_NO_SCALE = "no window from 4 GeV carries a fit weight, so this series has no pooled scale"
FX_TOO_FEW = "too few windows"


def _fx_cells(case: dict, windows: str, key: str, view: str) -> dict:
    """{form: (Fit cell, Status cell)} of one series' rows in one view's fit table."""
    return {form: (cells[0], cells[-1]) for form, cells in case[windows][view][key].items()}


@pytest.mark.parametrize("case, reason, windows", [
    ("res_scaling_robust_single_hits", FX_DECLINED, "anchors"), ("res_scaling_robust_single_hits", FX_DECLINED, "all"),
    ("res_scaling_robust_single_events", FX_DECLINED, "anchors"), ("res_scaling_robust_single_events", FX_DECLINED, "all"),
    ("declineCopy", FX_DECLINED, "all"),
    ("medianTwo", FX_NO_SCALE, "anchors"), ("medianTwo", FX_NO_SCALE, "all"),
    ("robustXgb", FX_NO_SCALE, "anchors"), ("robustXgb", FX_NO_SCALE, "all"),
    ("cNullNoise", FX_NO_SCALE, "anchors"), ("cNullNoise", FX_NO_SCALE, "all"),
    ("cNull", FX_NO_SCALE, "anchors"), ("cNull", FX_NO_SCALE, "all"),
    ("tooFew", FX_TOO_FEW, "anchors"), ("tooFew", FX_TOO_FEW, "all"),
])
def test_fx_f2_a_missing_fit_from_4_gev_gives_its_true_cause_in_every_cell(fx, case, reason, windows):
    """review-ui F2, review-docs M3 (19f6ab2, fa85fe8): a series with no fit from 4 GeV says why, from the payload, in
    the E view's affine, pinned and quadrature Fit cells, in both views' Status cells and in the E model's pinned
    reason: Robust σ (IQR) declines its one fittable window (the recordings of one shower and the lead's thinned copy
    of the two-shower one), no pooled scale (c null: the median two-shower deposits, the robust XGBoost series, and a
    copy of the robust network A with c null, its noise fit kept or removed), or else too few windows (a sample
    series). "too few windows" is never given for the first two, and no cell calls a fit that was never made "table
    only" or "drawn in the 1/√E view"."""
    c = fx["tables"][case]
    status = reason if reason == FX_TOO_FEW else f"no fit: {reason}"
    for key in c["keys"]:
        e = _fx_cells(c, windows, key, "energy")
        lin = _fx_cells(c, windows, key, "linear")
        assert e["affine"][0] == f"Affine a/√E + b — not fitted: {reason}", (case, key)
        assert e["pinned"][0] == f"Origin-pinned a₀/√E ⊕ 0 — not drawn: {reason}", (case, key)
        assert e["quadrature"][0] == f"Quadrature a/√E ⊕ b — not fitted: {reason}", (case, key)
        for form in ("affine", "pinned", "quadrature"):
            assert e[form][1] == lin[form][1] == status, (case, key, form)
        # The 1/√E view's Fit cells keep their form names.
        assert [lin[f][0] for f in ("affine", "pinned", "quadrature")] == [
            "Affine a/√E + b", "Origin-pinned a₀/√E", "Quadrature √(a²/E + b²), tabled only"]
        m = c[windows]["model"][key]
        assert m["pinnedReason"] == reason and m["pinnedDrawable"] is False, (case, key)
        cells = " ".join(x for pair in e.values() for x in pair) + " ".join(x for pair in lin.values() for x in pair)
        if reason != FX_TOO_FEW:
            assert FX_TOO_FEW not in cells, (case, key)
        assert "drawn in the 1/√E view" not in e["affine"][0] and "table only" not in e["pinned"][0]
        # The drawer: a series with no curve at all names the same cause for its a₀/√E.
        if m["drawnForm"] is None:
            (line,) = [x for x in c[windows]["drawer"] if x.startswith(f"{m['label']}: no fitted curve is drawn. ")]
            assert line.endswith(f"Its origin-pinned a₀/√E ⊕ 0 has no curve either: {reason}."), line
        else:
            assert m["drawnForm"] == "noise" and e["noise"][0] == "a/√E ⊕ b ⊕ c/E — drawn"


def test_fx_f2_the_fallback_and_a_complete_series_keep_their_cells(fx):
    """The cells the fix leaves alone: a drawn a₀/√E fallback says why it is drawn, a₀/√E beside a drawn noise curve is
    table only, the affine fit is drawn in the 1/√E view, and every Status reads as the fit's own."""
    for case, pinned in (("fallback", "Origin-pinned a₀/√E ⊕ 0 — drawn: no a/√E ⊕ b ⊕ c/E fit"),
                         ("plain", "Origin-pinned a₀/√E ⊕ 0 — table only on this view")):
        c = fx["tables"][case]
        for windows in ("anchors", "all"):
            e = _fx_cells(c, windows, "network:a", "energy")
            assert e["pinned"][0] == pinned and e["affine"][0] == "Affine a/√E + b — drawn in the 1/√E view"
            assert e["quadrature"][0].startswith("Quadrature a/√E ⊕ b — table only")
            assert not [f for f in ("affine", "pinned", "quadrature") if e[f][1].startswith("no fit") or e[f][1] == FX_TOO_FEW]
    assert fx["tables"]["fallback"]["all"]["model"]["network:a"]["drawnForm"] == "pinned"
    assert fx["tables"]["plain"]["all"]["model"]["network:a"]["pinnedReason"] == (
        "table only on this view: the a/√E ⊕ b ⊕ c/E curve is drawn")


def test_fx_f3_a_drawn_noise_fit_that_did_not_converge_raises_the_hazard(fx):
    """review-ui F3 (28d58e5): "fit not converged" reads the noise fit too, in both views, on a copy of every recording
    series whose noise fit alone is marked converged: false, and on none of the recordings themselves."""
    assert len(fx["hazards"]) >= 30 and any(h["drawn"] == "noise" for h in fx["hazards"])
    for h in fx["hazards"]:
        assert "fit not converged" not in h["base"]["energy"] and "fit not converged" not in h["base"]["linear"], h["name"]
        assert h["doctored"]["energy"].count("fit not converged") == 1, (h["name"], h["key"], h["windows"])
        assert h["doctored"]["linear"].count("fit not converged") == 1, (h["name"], h["key"], h["windows"])
        # Nothing else moves.
        assert [x for x in h["doctored"]["energy"] if x != "fit not converged"] == h["base"]["energy"]
        assert [x for x in h["doctored"]["linear"] if x != "fit not converged"] == h["base"]["linear"]


_FX_CHI2 = re.compile(r"^χ²/ν = \S+/\d+, p = \S+; S = \S+$")
_FX_EXACT = re.compile(r"^χ²/ν = .*: the curve passes through its \d+ points? exactly$")


def test_fx_f4_every_ratio_curve_tooltip_carries_its_terms_chi2_and_no_band(fx):
    """review-ui F4 (19f6ab2): every drawn curve's tooltip on the ratio panel gives, below its title, the fit ÷ the
    reference, its terms with their SEs (the same line its main-panel tooltip gives), its χ²/ν line ("; S = …" where
    ν ≥ 1, else the exact pass; the main tooltip's own), and ENERGY_NO_BAND_TEXT once. On the twelve recordings, both
    modes, every literature state, and on a fallback copy of every series with a noise fit."""
    tags = {(r["tag"], r["form"]) for r in fx["ratioTips"]}
    assert tags == {("recording", "noise"), ("fallback", "noise"), ("fallback", "pinned")}
    n = 0
    for r in fx["ratioTips"]:
        # A ratio that stays beyond the axis everywhere draws no run, so it has no run tooltip (its caret speaks).
        assert r["main"], (r["name"], r["key"], r["windows"], r["literature"])
        main_lines = {_plain(x) for t in r["main"] for x in t.split("<br/>")}
        for tip in r["ratio"]:
            lines = [_plain(x) for x in tip.split("<br/>")]
            head = "a/√E ⊕ b ⊕ c/E fit" if r["form"] == "noise" else "Origin-pinned fit a₀/√E ⊕ 0"
            assert lines[0] == r["label"] and lines[1] == f"{head} ÷ {r['refLabel']}", lines[:2]
            terms, chi2 = lines[2], lines[3]
            assert terms in main_lines and chi2 in main_lines, (terms, chi2)
            assert "±" in terms or "held there" in terms, terms
            if r["form"] == "pinned":
                assert terms.startswith("Origin-pinned fit ") and "%/√E ⊕ 0 (b ≡ 0, through the origin)" in terms
            if r["ndf"] >= 1 and r["p"] is not None:
                assert _FX_CHI2.match(chi2), chi2
            else:
                assert _FX_EXACT.match(chi2), chi2
            assert lines[4] == "The fitted curve divided by the reference at each E, the reference held exact."
            assert lines.count(ENERGY_NO_BAND_TEXT) == 1 and lines[5] == ENERGY_NO_BAND_TEXT
            n += 1
    assert n > 500


def _fx_entries(fx: dict, variant: str) -> list[dict]:
    return [e for e in fx["entries"] if e["variant"] == variant]


def _fx_served(fx: dict, e: dict) -> dict:
    (s,) = [x for x in _fx_entries(fx, "served") if (x["name"], x["key"], x["windows"], x["literature"])
            == (e["name"], e["key"], e["windows"], e["literature"])]
    return s


def _fx_pct(tip: str) -> str:
    """The axis top as a tooltip prints it, "(0 to 90%)"."""
    m = re.search(r"\(0 to ([^)]+%)\)", tip)
    assert m, tip
    return m.group(1)


def test_fx_f5_a_fallback_above_the_top_at_4_gev_comes_down_at_a0_over_the_top_squared(fx):
    """review-ui F5 (19f6ab2, fa85fe8): a₀/√E falls with E, so a fallback that starts above the top at 4 GeV (a₀ =
    3·y.hi, on a copy of every recording series with a noise fit, both modes, literature off and on) comes down into
    the plot at E = (a₀/y.hi)² = 9 GeV: an entry there, the curve drawn from the top on, no cut, one caret with its
    sentence, counted with the entries, never the leaving fits, and the drawer's line."""
    cases = _fx_entries(fx, "above9")
    assert len(cases) >= 60
    for e in cases:
        where = (e["name"], e["key"], e["windows"], e["literature"])
        hi, a0 = e["hi"], e["a0"]
        assert e["drawnForm"] == "pinned" and e["curveMin"] == 4 and a0 / 2 > hi
        at = (a0 / hi) ** 2
        assert at == pytest.approx(9)
        assert e["entry"] == {"at": pytest.approx(at), "lineAt": pytest.approx(at), "above": False, "term": "a", "atAxis": False}, where
        assert e["cut"] is None, where
        assert e["curve0"] == [pytest.approx(at), pytest.approx(hi)] and e["curveMaxY"] == pytest.approx(hi), where
        assert e["full0"] == [4, pytest.approx(a0 / 2)], "the ratio's source still starts at 4 GeV"
        served = _fx_served(fx, e)
        assert e["clipped"]["entries"] == served["clipped"]["entries"] + (0 if served["entry"] else 1), where
        assert e["clipped"]["fits"] == served["clipped"]["fits"], where
        tips = [c for c in e["carets"] if "origin-pinned a₀/√E" in c["tip"]]
        assert len(tips) == 1 and tips[0]["at"][:2] == [pytest.approx(at), pytest.approx(hi)], where
        tip = _plain(tips[0]["tip"])
        top = _fx_pct(tip)
        assert tip == (f"{e['label']} The origin-pinned a₀/√E comes down into the plot at E = 9 GeV: it falls as 1/√E, so "
                       f"from 4 GeV up to that energy it lies above the top of the axis (0 to {top}).")
        assert not [c for c in e["carets"] if "leaves the top" in c["tip"] and c["tip"].startswith(f"<b>{e['label']}")]
        assert e["mainTips"] and all("It comes down into the plot from the top: the caret there says where." in _plain(t)
                                     for t in e["mainTips"]), where
        assert not [t for t in e["mainTips"] if "It leaves the top of the plot" in t]
        lines = [x for x in e["drawer"] if x.startswith(f"{e['label']}: its origin-pinned a₀/√E ")]
        assert lines == [f"{e['label']}: its origin-pinned a₀/√E comes down into the main panel from its top ({top}) at "
                         "E = 9 GeV, with a caret there: it falls as 1/√E, so from 4 GeV up to that energy it lies above the top."], where


def test_fx_f5_a_fallback_above_the_whole_axis_has_one_caret_at_the_axis_end(fx):
    """A fallback above the top at every energy (a₀ = 1.2·y.hi·√x.max): no curve is drawn, one entry caret at x.max with
    its own sentence and its value there, counted with the entries, no cut, and the drawer's line."""
    cases = _fx_entries(fx, "aboveAll")
    assert len(cases) >= 60
    for e in cases:
        where = (e["name"], e["key"], e["windows"], e["literature"])
        hi, a0, xmax = e["hi"], e["a0"], e["xMax"]
        assert (a0 / hi) ** 2 > xmax
        assert e["entry"] == {"at": xmax, "lineAt": None, "above": True, "term": "a", "atAxis": False}, where
        assert e["cut"] is None and e["nCurve"] == 0 and e["solid"] == e["dashed"] == 0, where
        assert not e["mainTips"]
        served = _fx_served(fx, e)
        assert e["clipped"]["entries"] == served["clipped"]["entries"] + (0 if served["entry"] else 1), where
        assert e["clipped"]["fits"] == served["clipped"]["fits"]
        tips = [c for c in e["carets"] if "origin-pinned a₀/√E" in c["tip"]]
        assert len(tips) == 1 and tips[0]["at"][:2] == [xmax, pytest.approx(hi)], where
        tip = _plain(tips[0]["tip"])
        top = _fx_pct(tip)
        m = re.fullmatch(rf"{re.escape(e['label'])} The origin-pinned a₀/√E lies above the top of the axis \(0 to "
                         rf"{re.escape(top)}\) at every energy from 4 GeV: at 80 GeV it reads ([\d.,]+)%\.", tip)
        assert m, tip
        assert float(m.group(1).replace(",", "")) == pytest.approx(a0 / math.sqrt(xmax), rel=5e-3)
        lines = [x for x in e["drawer"] if x.startswith(f"{e['label']}: its origin-pinned a₀/√E ")]
        assert lines == [f"{e['label']}: its origin-pinned a₀/√E lies above the top of the main panel ({top}) at every "
                         "energy from 4 GeV; it is clipped there with a caret."], where
        # A curve the panel shows only as its caret is a clipped mark: the Details button says so (FX-jstests F-a).
        assert "marks clipped at the axis" in e["hazards"], where


def test_fx_f5_the_fallbacks_ratio_takes_the_entry_treatment(fx):
    """A fallback's ratio, defined from 4 GeV, that starts beyond [1/k, k] comes into it as E rises, or stays beyond it
    over the whole axis (`whole`): an entry with one caret naming the origin-pinned fit, never a cut at its first row;
    one that starts inside has no entry. On the doctored and the served fallbacks wherever the series is not the
    reference itself."""
    seen = {"inside": 0, "enters": 0, "whole": 0}
    for e in fx["entries"]:
        r = e["ratio"]
        if r is None:
            continue
        where = (e["variant"], e["name"], e["key"], e["windows"], e["literature"])
        k, (e0, r0) = r["k"], r["first"]
        assert e0 == pytest.approx(4), where
        outside = abs(math.log(r0)) > math.log(k) * (1 + 1e-9)
        carets = [_plain(c["tip"]) for c in r["carets"] if "The ratio of the origin-pinned fit a₀/√E ⊕ 0 to " in _plain(c["tip"])
                  and "leaves the ratio axis" not in c["tip"]]
        if not outside:
            assert r["entry"] is None and not carets, where
            seen["inside"] += 1
            continue
        ent = r["entry"]
        assert ent and ent["peak"] == [e0, r0] and ent["dir"] == ("up" if r0 > 1 else "down"), where
        assert len(carets) == 1, where
        side = "above" if r0 > 1 else "below"
        if ent["whole"]:
            assert r["runs"] == 0 and r["cut"] is None and not r["tips"], where
            assert f"stays {side} the ratio axis (" in carets[0] and ") over the whole axis, scanning up in E from 4 GeV" in carets[0]
            seen["whole"] += 1
        else:
            assert 4 < ent["at"] <= e["xMax"] and r["runs"] >= 1, where
            assert f"comes into the ratio axis (" in carets[0] and f") from {side} at E = " in carets[0]
            assert all("It comes into the ratio axis from beyond it as E rises from 4 GeV: the caret there says where." in _plain(t)
                       for t in r["tips"]), where
            seen["enters"] += 1
        assert "a/√E ⊕ b ⊕ c/E fit to" not in carets[0].split(" to ")[0]
    assert all(seen.values()), seen


def test_fx_n1_the_fallbacks_chi2_line_writes_s(fx):
    """review-ui N1 (19f6ab2): the fallback's main tooltip writes "χ²/ν = …, p = …; S = …" where ν ≥ 1, as the noise
    curve's does, and the exact-pass sentence otherwise."""
    n = 0
    for e in _fx_entries(fx, "served") + _fx_entries(fx, "above9"):
        for t in e["mainTips"]:
            (chi2,) = [_plain(x) for x in t.split("<br/>") if _plain(x).startswith("χ²/ν = ")]
            if e["ndf"] >= 1 and e["p"] is not None:
                assert _FX_CHI2.match(chi2), chi2
            else:
                assert _FX_EXACT.match(chi2) and "; S = " not in chi2, chi2
            n += 1
    assert n > 100


def test_fx_s2_the_pooled_scale_line_ends_with_the_residual_clause(fx, est):
    """review-stats S2 (28d58e5): under median and robust every drawer's pooled-scale line ends with the clause that a
    1–4 GeV window's residual counts in S and the misfit verdict at c·ŷ/√N, verbatim; under sample nothing says it."""
    clause = ("which they do not enter, so their residuals count in S and the misfit verdict at c·ŷ/√N, not at their own "
              "bootstrap errors.")
    assert FX2_WEIGHTS.endswith(clause)
    n = 0
    for name, estimator in RES_EST.items():
        for view, key, notes in _fix3_drawers(est["fixtures"][name]):
            hits = [x for x in _fix3_lines(notes) if x.endswith(clause)]
            assert len(hits) == (0 if estimator == "sample" else 1), (name, view, key)
            n += len(hits)
    assert n >= 64


_FX_LIT_PCT = re.compile(r"(?:27\.2|14\.0)\s*%\s*/√E|⊕\s*(?:1\.0|0\.4)\s*%")


def test_fx_the_literature_equations_carry_no_percent_sign_and_say_their_units(fx):
    """Martin's request (2026-11-15, c406217): the literature legend entries read "π± lit. — σ/E = 27.2/√E ⊕ 1.0" and
    "e± lit. — σ/E = 14.0/√E ⊕ 0.4", as the figure's legend prints them, and no literature equation anywhere on the
    card (canvas, axes, legend, every tooltip, the drawer) carries a % sign; REFERENCE_UNITS is said in each curve's
    tooltip and in the drawer's transcription line."""
    assert REFERENCE_UNITS in fx["exports"]["provenance"]
    legends = {"pi": "π± lit. — σ/E = 27.2/√E ⊕ 1.0", "e": "e± lit. — σ/E = 14.0/√E ⊕ 0.4"}
    drawn = 0
    for c in fx["literature"]:
        where = (c["name"], c["windows"], c["literature"])
        if c["legend"]:  # the empty state (robust, one shower, 3 anchors) draws no legend
            assert [x for x in c["legend"] if " lit. — " in x] == [legends[k] for k in c["literature"]], where
        for text in c["strings"] + c["drawer"]:
            assert not _FX_LIT_PCT.search(_plain(text)), (where, _plain(text)[:200])
        for k in ("pi", "e"):
            tips = c["litTips"][k]
            assert bool(tips) == (k in c["literature"] and bool(c["legend"])), where
            for t in tips:
                lines = [_plain(x) for x in t.split("<br/>")]
                assert lines[1] == LIT_EQUATIONS[k] and f"inlay, 2.55 < η < 3.98), {REFERENCE_UNITS}; no interval reported" in lines[2]
        units = [x for x in c["drawer"] if x.startswith("The literature curves are the two legend curves of one figure")]
        drawn += bool(c["legend"] and c["literature"])
        if c["literature"] and c["legend"]:
            assert units == [x for x in units if x.endswith(
                f"{LIT_EQUATIONS['pi']} and {LIT_EQUATIONS['e']}, transcribed as the legend prints them, {REFERENCE_UNITS}.")] and len(units) == 1
        elif not c["literature"]:
            assert not units
    assert drawn >= 60
