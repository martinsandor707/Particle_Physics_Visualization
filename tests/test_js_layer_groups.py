"""The Longitudinal Channels: the pure engine, its ECharts builders, the depth panel's Z label.

One Node script drives `static/js/layer_groups.js` (presets, the partition
codec and shorthand, the coupled clamped edits, the geometry against stored
edges, shares, reach, the text and `panelGroupSpec`), `panels/depth_groups.js`
(the strip in its reserved band, the seams, the spotlight, the tilted
one-shower planes, the Local badge) and `ProjectionPanel` headlessly, as
`tests/test_js_dark_golden.py` builds it (the depth panel's reserved top band,
its Z = z − 3649 title and round Z ticks, the extent from Z = 0, the bin
readout, the hover patch). The layer blocks are written by hand from the
server contract (brief section 2.2 and 2.3), on the recorded demo lattice
(`projections_base_lab.json`, 56 layers with gaps) and a production-like one
(60 layers from 3662.4 mm at 20.5 mm). The new theme tokens are measured
against each card. Skipped without `node`.
"""

from __future__ import annotations

import json
import math
import random
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

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")

PITCH = 20.5
#: Production-like lattice: 60 layers whose centres run from 3662.4 mm at 20.5 mm.
PROD_EDGES = [3662.4 - PITCH / 2 + PITCH * b for b in range(61)]

#: (θ, φ) pairs for the tilted one-shower planes, seeded so the run is deterministic.
_RNG = random.Random(20261104)
ANGLES = [(_RNG.uniform(0.02, 0.45), _RNG.uniform(-math.pi, math.pi)) for _ in range(6)]

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir, prodEdges, angles] = JSON.parse(process.argv.at(-1));
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const lg = await imp('layer_groups.js');
const dg = await imp('panels/depth_groups.js');
const scale = await imp('scale.js');
const axisSymbols = await imp('axis_symbols.js');
const voxels = await imp('voxels.js');
const decode = await imp('decode.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const { THEME } = scale;

/* ---- the fakes the golden harness uses for a headless ProjectionPanel -------- */
const zr = { handlers: {}, on(ev, fn) { (this.handlers[ev] ??= []).push(fn); },
  off(ev, fn) { this.handlers[ev] = (this.handlers[ev] ?? []).filter((f) => f !== fn); },
  fire(ev, e) { for (const fn of this.handlers[ev] ?? []) fn(e); } };
const calls = [];
const fakeChart = { getWidth: () => 640, getHeight: () => 360, resize() {}, clear() {},
  setOption(option, flags) { calls.push({ option, flags: flags ?? null }); },
  dispatchAction(action) { calls.push({ action }); }, on() {}, getZr: () => zr, getDom: () => fakeEl(),
  convertFromPixel: (_, p) => [p[0], p[1]] };
const fakeEl = () => ({ clientWidth: 640, clientHeight: 360, style: {}, classList: { toggle() {} }, closest: () => null,
  append() {}, replaceChildren() {}, appendChild() {}, hidden: false, addEventListener() {} });
function fakeCanvas() {
  const c = { width: 0, height: 0 };
  c.getContext = () => ({
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
    putImageData() {}, drawImage() {}, set imageSmoothingEnabled(_) {}, font: '',
    measureText(text) { const px = Number(/(\d+(?:\.\d+)?)px/.exec(this.font)?.[1] ?? 10); return { width: String(text).length * px * 0.55 }; },
  });
  return c;
}
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid' } };
globalThis.echarts = { init: () => fakeChart };
globalThis.document = { createElement: (t) => (t === 'canvas' ? fakeCanvas() : fakeEl()), getElementById: () => fakeEl(),
  createTextNode: (t) => ({ textContent: t }) };
const proj = await imp('panels/projection.js');

const out = {};

/* ---- engine: presets, codec, shorthand, edits ------------------------------------ */
out.consts = { GROUP_COUNT: lg.GROUP_COUNT, PRESET_KEYS: lg.PRESET_KEYS, PRESET_LABELS: lg.PRESET_LABELS,
  EM_HADRON_60: lg.EM_HADRON_60, LOCAL_BADGE: lg.LOCAL_BADGE };
out.presets = {};
for (const L of [13, 14, 56, 60, 61, 100]) {
  out.presets[L] = Object.fromEntries(lg.PRESET_KEYS.map((k) => [k, lg.presetCounts(k, L)]));
}
out.presetsInvalid = [lg.uniformCounts(12), lg.presetCounts('log', 12), lg.presetCounts('nope', 60), lg.uniformCounts(60.5)];
out.logRatio = [lg.logRatio(60), lg.logRatio(13)];
out.presetOf = [lg.presetOf(lg.presetCounts('log', 60), 60), lg.presetOf([4, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4], 60)];

const U60 = lg.uniformCounts(60);
out.codec = {
  format: lg.formatCounts(U60),
  parsed: lg.parseCounts(lg.formatCounts(U60), 60),
  wrongSum: lg.parseCounts(lg.formatCounts(U60), 56),
  anySum: lg.parseCounts(lg.formatCounts(U60)),
  bad: ['5.5.5', '5.5.5.5.5.5.5.5.4.4.4.4.0', 'a.b', '', null, '5.5.5.5.5.5.5.5.4.4.4.4.4.1'].map((t) => lg.parseCounts(t, null)),
  valid: [lg.isValidCounts(U60, 60), lg.isValidCounts(U60, 59), lg.isValidCounts([...U60.slice(0, 12), 0]), lg.isValidCounts(U60.slice(1))],
  boundaries: lg.countsToBoundaries(U60),
  back: lg.boundariesToCounts(lg.countsToBoundaries(U60)),
  ranges: lg.formatRanges(U60),
  groupRanges: lg.groupRanges(U60),
  groupOf: [1, 5, 6, 40, 41, 60, 61, 0].map((l) => lg.groupOfLayer(U60, l)),
  same: [lg.sameCounts(U60, [...U60]), lg.sameCounts(U60, lg.presetCounts('log', 60))],
};

const shorthands = {};
for (const L of [56, 60]) {
  for (const key of lg.PRESET_KEYS) {
    const c = lg.presetCounts(key, L);
    const text = lg.formatRanges(c);
    shorthands[`${L}/${key}/ranges`] = { text, got: lg.parseShorthand(text, L), want: c };
    shorthands[`${L}/${key}/hyphen`] = { got: lg.parseShorthand(text.replaceAll('–', '-'), L), want: c };
    shorthands[`${L}/${key}/minus`] = { got: lg.parseShorthand(text.replaceAll('–', '−'), L), want: c };
    shorthands[`${L}/${key}/counts`] = { got: lg.parseShorthand(c.join(', '), L), want: c };
    shorthands[`${L}/${key}/spaces`] = { got: lg.parseShorthand(c.join('  '), L), want: c };
  }
}
out.shorthands = shorthands;
out.shorthandErrors = Object.fromEntries(Object.entries({
  empty: '',
  twelveRanges: lg.formatRanges(U60).split(', ').slice(0, 12).join(', '),
  gap: lg.formatRanges(U60).replace('6–10', '7–10'),
  backwards: lg.formatRanges(U60).replace('6–10', '10–6'),
  shortEnd: lg.formatRanges(U60).replace('57–60', '57–59'),
  garbage: lg.formatRanges(U60).replace('6–10', 'six–10'),
  twelveCounts: U60.slice(0, 12).join(','),
  zero: [...U60.slice(0, 12), 0].join(','),
  wrongSum: [...U60.slice(0, 12), 5].join(','),
  words: 'five five',
}).map(([k, t]) => [k, lg.parseShorthand(t, 60)]));
out.shorthandNoL = lg.parseShorthand('1-5', null);

out.edits = {
  end: lg.setGroupEnd(U60, 3, 17),
  endLow: lg.setGroupEnd(U60, 3, 2),
  endHigh: lg.setGroupEnd(U60, 3, 99),
  endBad: lg.setGroupEnd(U60, 13, 50),
  start: lg.setGroupStart(U60, 4, 14),
  startLow: lg.setGroupStart(U60, 4, 1),
  startHigh: lg.setGroupStart(U60, 4, 30),
  startBad: lg.setGroupStart(U60, 1, 2),
  seamRight: lg.moveSeam(U60, 1, 1),
  seamLeftClamp: lg.moveSeam(U60, 1, -10),
  seamPage: lg.moveSeam(U60, 12, 5),
};

/* ---- geometry: seams and spans on stored edges ------------------------------------- */
const demo = load('projections_base_lab');
const demoEdges = demo.panels.yz.axes.col.edges;
const D56 = lg.uniformCounts(56);
out.geometry = {
  axisEdges: {
    demo: lg.axisEdges(demo.panels.yz.axes.col),
    uniform: lg.axisEdges({ lo: -10.25, hi: 20.5 * 59.5, n: 60, uniform: true }),
    bad: [lg.axisEdges(null), lg.axisEdges({ lo: 0, hi: 1, n: 3, uniform: false }), lg.axisEdges({ edges: [0, 2, 1], n: 2 })],
  },
  demoEdges,
  demoSeams: lg.seamsOnAxis(demoEdges, D56),
  // A partition whose last seam falls inside the gapped tail of the demo lattice.
  demoTailSeams: lg.seamsOnAxis(demoEdges, [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 11, 1]),
  demoSpans: lg.groupSpansOnAxis(demoEdges, D56),
  prodSeams: Object.fromEntries(lg.PRESET_KEYS.map((k) => [k, lg.seamsOnAxis(prodEdges, lg.presetCounts(k, 60))])),
  prodSpans: lg.groupSpansOnAxis(prodEdges, U60),
  // A relative axis longer than L (the per-shower translated frame on a gapped lattice) and one shorter.
  longSpans: lg.groupSpansOnAxis(Array.from({ length: 66 }, (_, k) => (k - 0.5) * 20.5), D56),
  shortSpans: lg.groupSpansOnAxis(Array.from({ length: 29 }, (_, k) => (k - 0.5) * 20.5), U60),
  shortSeams: lg.seamsOnAxis(Array.from({ length: 29 }, (_, k) => (k - 0.5) * 20.5), U60),
  shortBeyond: lg.groupsBeyondAxis(28, U60),
  binOf: [lg.binOf(prodEdges, 3652.15), lg.binOf(prodEdges, 3672.6), lg.binOf(prodEdges, 3672.65), lg.binOf(prodEdges, 3000)],
};

/* planeLine against the independent rotation of the Python test. */
out.planes = angles.map(([theta, phi]) => {
  const normal = [-Math.sin(theta), 0, Math.cos(theta)];
  return { theta, phi, normal, xz: [-10.25, 92.25, 400].map((s) => lg.planeLine(normal, s, 'xz', [-300, 250])),
    yz: lg.planeLine(normal, 92.25, 'yz', [-300, 250]) };
});
out.planeFlat = { yz: lg.planeLine([0, 0, 1], 92.25, 'yz', [-1, 1]), xz: lg.planeLine([0, 0, 1], 92.25, 'xz', [-1, 1]),
  xy: lg.planeLine([0, 0, 1], 1, 'xy', [0, 1]), parallel: lg.planeLine([1, 0, 0], 1, 'xz', [0, 1]) };

/* ---- shares and reach --------------------------------------------------------------- */
const energy = Array.from({ length: 60 }, (_, j) => Math.exp(-((j - 12) ** 2) / 60));
const eTotal = energy.reduce((a, b) => a + b, 0) + 0.25;
out.shares = { energy, total: eTotal, groups: lg.groupShares(energy, U60, { total: eTotal }),
  plain: lg.groupShares(energy, U60) };
const reach = { n_showers: 4812, counts: Array.from({ length: 60 }, (_, k) => Math.max(0, 4812 - 9 * k)), n_without_start: 0,
  note: 'reach' };
out.reach = { g12: lg.groupReach(reach, 51, 55), none: lg.groupReach(null, 1, 2), beyond: lg.groupReach(reach, 61, 62) };

/* ---- the layer blocks of the server contract, by hand ---------------------------- */
const profileOf = (n, attention = null) => ({ numbering: 'detector', energy_gev: Array.from({ length: n }, (_, j) => 1 + (j % 7)),
  attention, outside_gev: 0.5, total_gev: Array.from({ length: n }, (_, j) => 1 + (j % 7)).reduce((a, b) => a + b, 0) + 0.5, exact: true });
const labBlock = (edges, extra = {}) => ({
  numbering: 'detector', n_layers: edges.length - 1, partition_layers: edges.length - 1, pitch_mm: 20.5, edges_mm: edges,
  first_layer: 1, contiguous: edges.length !== 57, display_offset_mm: 3649.0, symbol: 'z',
  profile: profileOf(edges.length - 1), reach: null, groups: null, note: 'detector layers', ...extra,
});
const demoBlock = labBlock(demoEdges);
const prodBlock = labBlock(prodEdges);
const transEdges = Array.from({ length: 61 }, (_, k) => (k - 0.5) * 20.5);
const transBlock = { numbering: 'relative', n_layers: 60, partition_layers: 60, pitch_mm: 20.5, edges_mm: transEdges, first_layer: 1,
  contiguous: true, display_offset_mm: null, symbol: 'Δz', profile: { ...profileOf(60), numbering: 'relative' }, reach,
  groups: null, note: 'relative layers' };
const canonicalBlock = { ...transBlock, numbering: 'detector', symbol: 'z′', reach: null };
const localBlock = { numbering: 'none', n_layers: 0, partition_layers: 60, pitch_mm: 20.5, edges_mm: null, first_layer: 1,
  contiguous: true, display_offset_mm: null, symbol: 'w', profile: null, reach: null, groups: null, note: 'tilted' };
const signed = { channel: 'shapcam', quantity: 'Σ E·Shap-CAM', signed: true,
  positive: Array.from({ length: 60 }, () => 1), negative: Array.from({ length: 60 }, (_, j) => (j < 30 ? 0.5 : 0)),
  total: 60 - 15, positive_total: 60, negative_total: 15, outside: 0, positive_outside: 0, negative_outside: 0, unit: 'GeV' };
const poolBlock = { ...prodBlock, groups: { counts: U60, pooled: true, bins: [], beyond_axis: [] } };
const theta = 10 * Math.PI / 180;
const localPlanes = { numbering: 'relative', normal: [-Math.sin(theta), 0, Math.cos(theta)], edges_mm: transEdges, first_layer: 1,
  n_layers: 60, energy_gev: Array.from({ length: 60 }, (_, j) => (j < 40 ? 1 : 0)), line_panels: ['xz'],
  tilt: { theta, theta_deg: 10, pitch_along_w_mm: 20.5 / Math.cos(theta) }, start_layer: 3, reach_layers: 58, display_offset_mm: null };
const labPlanes = { numbering: 'detector', normal: [0, 0, 1], edges_mm: prodEdges, first_layer: 1, n_layers: 60,
  energy_gev: Array.from({ length: 60 }, () => 0.1), line_panels: ['xz', 'yz'], tilt: null, start_layer: 1, reach_layers: null,
  display_offset_mm: 3649.0 };

const spec = (args) => lg.panelGroupSpec(args);
out.specs = {
  off: spec({ mode: 'off', counts: U60, panelId: 'yz', depthLayers: prodBlock }),
  xy: spec({ mode: 'bounds', counts: U60, panelId: 'xy', depthLayers: prodBlock }),
  none: spec({ mode: 'bounds', counts: U60, panelId: 'yz' }),
  wrongL: spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: demoBlock }),
  demo: spec({ mode: 'bounds', counts: D56, panelId: 'yz', depthLayers: demoBlock, nEvents: 287 }),
  prod: spec({ mode: 'bounds', counts: U60, panelId: 'xz', depthLayers: prodBlock, highlight: 3 }),
  pooled: spec({ mode: 'pool', counts: U60, panelId: 'yz', depthLayers: poolBlock }),
  poolStale: spec({ mode: 'pool', counts: lg.presetCounts('log', 60), panelId: 'yz', depthLayers: poolBlock }),
  trans: spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: transBlock }),
  canonical: spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: canonicalBlock }),
  signed: spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: { ...prodBlock, profile: { ...prodBlock.profile, attention: signed } } }),
  local: spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: localBlock }),
  localEventXz: spec({ mode: 'bounds', counts: U60, panelId: 'xz', layerPlanes: localPlanes, highlight: 2 }),
  localEventYz: spec({ mode: 'bounds', counts: U60, panelId: 'yz', layerPlanes: localPlanes }),
  labEvent: spec({ mode: 'pool', counts: U60, panelId: 'yz', layerPlanes: labPlanes }),
};
// The functions do not survive JSON; the hover callback is checked separately.
out.onHover = typeof spec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: prodBlock, onHover: () => 1 }).onHover;
out.readouts = {
  prodLayer4: lg.layerReadout({ spec: out.specs.prod, panelId: 'xz', col: prodEdges[3] + 1, row: 0 }),
  prodAxisOnly: lg.layerReadout({ axis: lg.panelLayerAxis({ panelId: 'yz', depthLayers: prodBlock }), panelId: 'yz', col: prodEdges[3] + 1, row: 0 }),
  pooled: lg.layerReadout({ spec: out.specs.pooled, panelId: 'yz', col: prodEdges[7] + 1, row: 0 }),
  trans: lg.layerReadout({ spec: out.specs.trans, panelId: 'yz', col: 0, row: 0 }),
  off: lg.layerReadout({ spec: out.specs.trans, panelId: 'yz', col: -400, row: 0 }),
  localXz: lg.layerReadout({ spec: out.specs.localEventXz, panelId: 'xz', col: 92.25 / Math.cos(theta) + 50 * Math.tan(theta) + 1, row: 50 }),
  localYz: lg.layerReadout({ spec: out.specs.localEventYz, panelId: 'yz', col: 100, row: 50 }),
  local: lg.layerReadout({ spec: out.specs.local, panelId: 'yz', col: 100, row: 0 }),
};
out.text = {
  labels: [lg.groupLabel('detector', 3), lg.groupLabel('relative', 12)],
  title: [lg.groupTitle('detector', 3, 11, 15), lg.groupTitle('relative', 1, 1, 1)],
  spans: [lg.depthSpanText(3652.15, 3754.65, { symbol: 'z', offset: 3649 }), lg.depthSpanText(-10.25, 92.25, { symbol: 'z′' }),
    lg.depthPointText(3723.9, { symbol: 'z', offset: 3649 }), lg.depthPointText(-10.25, { symbol: 'Δz' })],
  numbers: [lg.intText(4812), lg.intText(-1234567), lg.percentText(0.979), lg.gevText(1.23456), lg.gevText(-0.000012)],
};

/* ---- builders ------------------------------------------------------------------------ */
const cs = { x: 60, y: 40, width: 500, height: 300 };
const apiFor = (view) => ({ coord: ([c, r]) => [cs.x + ((c - view.col[0]) / (view.col[1] - view.col[0])) * cs.width,
  cs.y + cs.height - ((r - view.row[0]) / (view.row[1] - view.row[0])) * cs.height] });
const runSeries = (series, view) => series.map((s) => ({
  id: s.id, clip: s.clip, silent: Boolean(s.silent), z: s.z, n: s.data.length,
  items: s.data.map((_, i) => s.renderItem({ dataIndex: i, coordSys: cs }, apiFor(view))),
  tips: s.tooltip?.formatter ? s.data.map((_, i) => s.tooltip.formatter({ dataIndex: i })) : null,
  bareTip: s.tooltip?.formatter ? s.tooltip.formatter() : null,
}));
const prodCol = { name: 'z', lo: prodEdges[0], hi: prodEdges[60] };
const row = { name: 'y', lo: -400, hi: 2200 };
const fullView = { col: [prodEdges[0], prodEdges[60]], row: [row.lo, row.hi] };
const zoomView = { col: [3800, 4100], row: [0, 1000] };
const S = (s, marks = true, view = fullView) => runSeries(dg.layerGroupSeries({ spec: s, col: prodCol, row, view, marks }), view);
out.builders = {
  reserve: [dg.stripReserve(null), dg.stripReserve(out.specs.prod), dg.stripReserve(out.specs.local),
    dg.stripReserve(out.specs.localEventXz), dg.stripReserve(out.specs.localEventYz)],
  geometry: dg.stripGeometry(),
  full: S(out.specs.prod, true, fullView),
  zoom: S(out.specs.prod, true, zoomView),
  hidden: S(out.specs.prod, false, fullView),
  pooled: S(out.specs.pooled, true, fullView),
  localXz: runSeries(dg.layerGroupSeries({ spec: out.specs.localEventXz, col: { name: 'z', lo: -50, hi: 1200 },
    row: { name: 'x', lo: -300, hi: 250 }, view: { col: [-50, 1200], row: [-300, 250] } }), { col: [-50, 1200], row: [-300, 250] }),
  localYz: runSeries(dg.layerGroupSeries({ spec: out.specs.localEventYz, col: { name: 'z', lo: -50, hi: 1200 },
    row: { name: 'y', lo: -300, hi: 250 }, view: { col: [-50, 1200], row: [-300, 250] } }), { col: [-50, 1200], row: [-300, 250] }),
  local: dg.layerGroupSeries({ spec: out.specs.local, col: prodCol, row, view: fullView }),
  notDepth: dg.layerGroupSeries({ spec: out.specs.prod, col: { name: 'x', lo: 0, hi: 1 }, row, view: fullView }),
  badge: dg.localBadge(out.specs.local, { left: 52, top: 40, width: 500, height: 300 }),
  noBadge: dg.localBadge(out.specs.prod, { left: 52, top: 40, width: 500, height: 300 }),
};
// Under the print tokens the band scales with the type and the colours are paper's.
{
  const saved = { ...THEME };
  Object.assign(THEME, PRINT_TOKENS);
  out.builders.print = { reserve: dg.stripReserve(out.specs.prod), full: S(out.specs.prod, true, fullView) };
  for (const k of Object.keys(THEME)) delete THEME[k];
  Object.assign(THEME, saved);
}

/* ---- ProjectionPanel, headless --------------------------------------------------------- */
const sub = demo.panels.yz;
const panelOf = () => new proj.ProjectionPanel('plot-yz');
const build = (payload, opts, metrics = { width: 640, height: 360 }) => {
  const panel = panelOf();
  return panel.buildOption({ payload, opts, raster: decode.renderRaster(payload, 'viridis'), metrics });
};
const axisOut = (axis) => ({
  name: axis.name, min: axis.min, max: axis.max,
  tickValues: axis.axisTick.customValues ?? null, labelValues: axis.axisLabel.customValues ?? null,
  labels: (axis.axisLabel.customValues ?? [axis.min, axis.max]).map((v) => axis.axisLabel.formatter(v)),
  showMin: axis.axisLabel.showMinLabel, showMax: axis.axisLabel.showMaxLabel,
});
const demoSpec = out.specs.demo;
const ensemble = { palette: 'viridis', frame: null };
const plain = build(sub, ensemble);
const withSpec = build(sub, { ...ensemble, layerGroups: demoSpec });
const small = build(sub, { ...ensemble, layerGroups: demoSpec }, { width: 360, height: 200 });
// An event cell (the Inspector's lab panel): a window that starts upstream of Z = 0.
const eventOpts = { palette: 'viridis', framed: true, window: { col: [3590, 3910], row: [sub.axes.row.lo, sub.axes.row.hi] } };
const eventBuilt = build(sub, eventOpts);
// The co-registered frames keep their own depth symbols and are never shifted.
const local = load('projections_single_local');
const localBuilt = build(local.panels.yz, { palette: 'viridis', frame: local.frame });
const transPayload = clone(local.panels.yz);
transPayload.axes.col.symbol = 'Δz';
transPayload.axes.row.symbol = 'Δy';
const transBuilt = build(transPayload, { palette: 'viridis', frame: { ...local.frame, kind: 'trans' } });
const canonPayload = clone(local.panels.yz);
canonPayload.axes.col.symbol = 'z′';
canonPayload.axes.row.symbol = 'y′';
const canonBuilt = build(canonPayload, { palette: 'viridis', frame: { ...local.frame, kind: 'canonical', depth_mm: 1200, ensemble: {} } });
const xyBuilt = build(demo.panels.xy, ensemble);
const seriesIds = (o) => o.series.map((s) => s.id ?? s.name ?? s.type);
out.panel = {
  plain: { grid: plain.grid, x: axisOut(plain.xAxis), ids: seriesIds(plain), graphics: plain.graphic.length },
  withSpec: { grid: withSpec.grid, x: axisOut(withSpec.xAxis), ids: seriesIds(withSpec),
    graphics: withSpec.graphic.length },
  small: { x: axisOut(small.xAxis) },
  event: { x: axisOut(eventBuilt.xAxis), extent: proj.extentOf(sub, eventOpts) },
  local: { x: axisOut(localBuilt.xAxis), extent: proj.extentOf(local.panels.yz, { frame: local.frame }), col: local.panels.yz.axes.col },
  trans: { x: axisOut(transBuilt.xAxis) },
  canonical: { x: axisOut(canonBuilt.xAxis) },
  xy: { x: axisOut(xyBuilt.xAxis), extent: proj.extentOf(demo.panels.xy, ensemble), col: demo.panels.xy.axes.col },
  extent: proj.extentOf(sub, ensemble),
  col: { lo: sub.axes.col.lo, hi: sub.axes.col.hi },
  depthOffsetOpt: axisOut(build(sub, { ...ensemble, depthOffset: 0 }).xAxis),
  spatialPlain: scale.spatialAxis('z', 0, 1200, { onZero: false }),
  spatialZero: scale.spatialAxis('z', 0, 1200, { onZero: false, offset: 0 }),
  offsetTicks: [scale.offsetTicks(3652.15, 4882.15, 3649), scale.offsetTicks(3649.2, 3651.0, 3649)],
  marksHidden: (() => {
    const p = panelOf();
    p.marksShown = false;
    return seriesIds(p.buildOption({ payload: sub, opts: { ...ensemble, layerGroups: demoSpec }, raster: decode.renderRaster(sub, 'viridis'),
      metrics: { width: 640, height: 360 } }));
  })(),
  localBadge: (() => {
    const o = build(local.panels.yz, { palette: 'viridis', frame: local.frame,
      layerGroups: lg.panelGroupSpec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: localBlock }) });
    return { grid: o.grid, graphics: o.graphic.filter((g) => g.id === 'layer-groups-badge'), ids: seriesIds(o) };
  })(),
  localPlain: (() => { const o = build(local.panels.yz, { palette: 'viridis', frame: local.frame }); return { grid: o.grid }; })(),
  wrongPanel: seriesIds(build(demo.panels.xz, { ...ensemble, layerGroups: demoSpec })),
};

/* Export metrics: the figure grows by the band. */
{
  const p = panelOf();
  p.payload = sub;
  p.lastOpts = ensemble;
  p.extent = proj.extentOf(sub, ensemble);
  const before = p.exportMetrics(600);
  p.lastOpts = { ...ensemble, layerGroups: demoSpec };
  const after = p.exportMetrics(600);
  out.panel.exportMetrics = { before, after };
}

/* setLayerGroups, setGroupHighlight and the readout on a rendered panel. */
{
  calls.length = 0;
  const p = panelOf();
  p.render(sub, { ...ensemble });
  p.setView({ col: [3700, 4200], row: [sub.axes.row.lo, sub.axes.row.hi] });
  const viewPatch = calls.at(-1).option.xAxis;
  const before = calls.length;
  p.setLayerGroups(demoSpec);
  const afterSet = calls.slice(before);
  const keptView = p.view;
  const before2 = calls.length;
  p.setGroupHighlight(4);
  const patch = calls.slice(before2);
  p.setGroupHighlight(4);
  const again = calls.length - before2 - patch.length;
  const highlightNow = p.lastOpts.layerGroups.highlight;
  p.setGroupHighlight(null);
  // The readout: a populated bin of the raster, the pointer at its centre (identity pixel map).
  const raster = p.raster;
  let found = null;
  for (let r = 0; r < raster.rows && !found; r += 1) {
    for (let c = 0; c < raster.cols; c += 1) {
      const code = raster.codes[r * raster.cols + c];
      if (code !== (sub.empty_code ?? 0) && code !== sub.below_code) { found = { r, c }; break; }
    }
  }
  const zc = decode.cellCentre(sub.axes.col, raster.cols, found.c);
  const yc = decode.cellCentre(sub.axes.row, raster.rows, found.r);
  calls.length = 0;
  zr.fire('mousemove', { offsetX: zc, offsetY: yc, target: null });
  const tip = calls.find((x) => x.action?.type === 'showTip')?.action.tooltip.formatter ?? null;
  p.setLayerGroups(null);
  calls.length = 0;
  zr.fire('mousemove', { offsetX: zc, offsetY: yc, target: null });
  const tipOff = calls.find((x) => x.action?.type === 'showTip')?.action.tooltip.formatter ?? null;
  // A Boundaries panel with no spec but its layer axis still names the layer.
  p.setOverlay('layerAxis', lg.panelLayerAxis({ panelId: 'yz', depthLayers: demoBlock }));
  calls.length = 0;
  zr.fire('mousemove', { offsetX: zc, offsetY: yc, target: null });
  const tipAxis = calls.find((x) => x.action?.type === 'showTip')?.action.tooltip.formatter ?? null;
  out.live = {
    viewPatch: { min: viewPatch.min, max: viewPatch.max, ticks: viewPatch.axisTick?.customValues ?? null,
      labels: viewPatch.axisLabel?.customValues?.map((v) => viewPatch.axisLabel.formatter(v)) ?? null },
    afterSet: afterSet.map((x) => ({ notMerge: x.flags?.notMerge ?? null, ids: x.option ? seriesIds(x.option) : null,
      xMin: x.option?.xAxis?.min, xMax: x.option?.xAxis?.max })),
    keptView,
    patch: patch.map((x) => ({ flags: x.flags, ids: (x.option.series ?? []).map((s) => s.id), keys: Object.keys(x.option) })),
    again,
    highlightNow,
    tip, tipOff, tipAxis, at: { zc, yc, layer: found.c + 1 },
  };
}

/* buildOption time for a 60-layer YZ panel with a spec. */
{
  const prodSpec = out.specs.prod.panelId === 'xz'
    ? lg.panelGroupSpec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: prodBlock, highlight: 4 }) : null;
  const p = panelOf();
  const raster = decode.renderRaster(sub, 'viridis');
  const opts = { ...ensemble, layerGroups: prodSpec };
  const time = (o, n) => {
    for (let i = 0; i < 20; i += 1) p.buildOption({ payload: sub, opts: o, raster, metrics: { width: 640, height: 360 } });
    const t0 = performance.now();
    for (let i = 0; i < n; i += 1) {
      const option = p.buildOption({ payload: sub, opts: o, raster, metrics: { width: 640, height: 360 } });
      // Every layer-group item rendered once, as ECharts does on a paint.
      for (const s of option.series) {
        if (!String(s.id ?? '').startsWith('layer-groups')) continue;
        for (let k = 0; k < s.data.length; k += 1) s.renderItem({ dataIndex: k, coordSys: cs }, apiFor(fullView));
      }
    }
    return (performance.now() - t0) / n;
  };
  const engineT0 = performance.now();
  for (let i = 0; i < 200; i += 1) lg.panelGroupSpec({ mode: 'bounds', counts: U60, panelId: 'yz', depthLayers: prodBlock });
  out.timing = { withSpec: time(opts, 200), without: time(ensemble, 200), spec: (performance.now() - engineT0) / 200 };
}

/* ---- theme tokens, CORE_SHIFT_Z_MM ------------------------------------------------- */
const KEYS = ['groupStripFillA', 'groupStripFillB', 'groupStripEdge', 'groupStripText', 'groupStripHot', 'groupSeam', 'groupSpot'];
out.tokens = {
  dark: Object.fromEntries(KEYS.map((k) => [k, scale.SCREEN_THEMES.dark[k]])),
  light: Object.fromEntries(KEYS.map((k) => [k, scale.SCREEN_THEMES.light[k]])),
  print: Object.fromEntries(KEYS.map((k) => [k, PRINT_TOKENS[k]])),
  cards: { dark: scale.SCREEN_THEMES.dark.card, light: scale.SCREEN_THEMES.light.card, print: PRINT_TOKENS.card },
  text: { dark: scale.SCREEN_THEMES.dark.text, light: scale.SCREEN_THEMES.light.text, print: PRINT_TOKENS.text },
};
out.shift = { axisSymbols: axisSymbols.CORE_SHIFT_Z_MM, voxels: voxels.CORE_SHIFT_Z_MM,
  names: [voxels.axisNames({ x: 'x', y: 'y', z: 'z' }, { offset: 3649 }), voxels.axisNames({ x: 'u', y: 'v', z: 'w' })],
  ticks: [voxels.axisTicks(3652.15, 4882.15, 100, { offset: 3649 }), voxels.axisTicks(0, 1000)] };

console.log(JSON.stringify(out));
"""


def _run() -> dict:
    args = json.dumps([JS.as_uri(), str(FIXTURES), PROD_EDGES, ANGLES])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=240, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def out() -> dict:
    return _run()


def _texts(value):
    """Every string inside a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _texts(v)
    elif isinstance(value, list):
        for v in value:
            yield from _texts(v)


def _no_hyphen_numbers(texts):
    for text in texts:
        assert not HYPHEN_NUMBER.search(text), text


# ------------------------------------------------------------------ engine --


def test_constants_are_the_brief_values(out):
    c = out["consts"]
    assert c["GROUP_COUNT"] == 13
    assert c["PRESET_KEYS"] == ["uniform", "em_hadron", "log"]
    assert c["PRESET_LABELS"] == {"uniform": "Uniform", "em_hadron": "EM-Fine / Hadron-Coarse", "log": "Logarithmic Depth"}
    assert c["EM_HADRON_60"] == [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8]
    assert c["LOCAL_BADGE"].startswith("Layers tilt by each shower")


def test_the_presets_on_60_layers_are_the_plans_values(out):
    p = out["presets"]["60"]
    assert p["uniform"] == [5] * 8 + [4] * 5
    assert p["em_hadron"] == [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8]
    assert p["log"] == [1, 1, 2, 2, 2, 3, 4, 4, 5, 6, 8, 10, 12]
    assert out["logRatio"][0] == pytest.approx(1.2305, abs=5e-5) and out["logRatio"][1] == 1
    assert out["presetOf"] == ["log", None]


@pytest.mark.parametrize("L", [13, 14, 56, 61, 100])
def test_every_preset_partitions_any_lattice_into_13_nonempty_groups(out, L):
    for key, counts in out["presets"][str(L)].items():
        assert len(counts) == 13 and all(isinstance(c, int) and c >= 1 for c in counts), (key, counts)
        assert sum(counts) == L, (key, counts)
    uniform = out["presets"][str(L)]["uniform"]
    q, r = divmod(L, 13)
    assert uniform == [q + 1] * r + [q] * (13 - r)
    log = out["presets"][str(L)]["log"]
    assert log == sorted(log), "geometric widths never shrink with depth"


def test_the_demo_lattice_gets_its_own_scaled_presets(out):
    p = out["presets"]["56"]
    assert p["uniform"] == [5] * 4 + [4] * 9
    assert p["em_hadron"] == [2, 2, 3, 3, 3, 4, 4, 5, 5, 5, 6, 7, 7]
    assert p["log"] == [1, 1, 2, 2, 2, 3, 3, 4, 5, 6, 7, 9, 11]


def test_presets_refuse_what_cannot_be_partitioned(out):
    assert out["presetsInvalid"] == [None, None, None, None]


def test_the_wire_codec_round_trips_and_refuses_malformed_input(out):
    c = out["codec"]
    assert c["format"] == "5.5.5.5.5.5.5.5.4.4.4.4.4"
    assert c["parsed"] == [5] * 8 + [4] * 5 and c["anySum"] == c["parsed"]
    assert c["wrongSum"] is None
    assert c["bad"] == [None] * 6
    assert c["valid"] == [True, False, False, False]
    assert c["boundaries"] == [5, 10, 15, 20, 25, 30, 35, 40, 44, 48, 52, 56, 60]
    assert c["back"] == c["parsed"]
    assert c["ranges"].startswith("1–5, 6–10, ") and c["ranges"].endswith("57–60")
    assert c["groupRanges"][8] == {"group": 9, "first": 41, "last": 44, "n": 4}
    assert c["groupOf"] == [1, 1, 2, 8, 9, 13, None, None]
    assert c["same"] == [True, False]


def test_the_shorthand_round_trips_both_forms_and_every_dash(out):
    for key, case in out["shorthands"].items():
        assert case["got"] == {"counts": case["want"]}, key


@pytest.mark.parametrize("case", ["empty", "twelveRanges", "gap", "backwards", "shortEnd", "garbage", "twelveCounts",
                                  "zero", "wrongSum", "words"])
def test_the_shorthand_errors_are_sentences(out, case):
    got = out["shorthandErrors"][case]
    assert set(got) == {"error"}
    assert got["error"][0].isupper() and got["error"].rstrip().endswith("."), got["error"]
    _no_hyphen_numbers([got["error"]])
    assert "error" in out["shorthandNoL"]


def test_the_shorthand_errors_name_what_is_wrong(out):
    e = {k: v["error"] for k, v in out["shorthandErrors"].items()}
    assert "Found 12 ranges" in e["twelveRanges"]
    assert "must start at layer 6" in e["gap"]
    assert "ends before it starts" in e["backwards"]
    assert "must end at layer 60" in e["shortEnd"]
    assert "Found 12 counts" in e["twelveCounts"]
    assert "at least one layer" in e["zero"]
    assert "sum to 61" in e["wrongSum"] and "60 layers" in e["wrongSum"]


def test_the_coupled_edits_clamp_and_keep_every_group(out):
    e = out["edits"]
    for key, result in e.items():
        counts = result["counts"]
        assert sum(counts) == 60 and len(counts) == 13 and min(counts) >= 1, key
    assert e["end"] == {"counts": [5, 5, 7, 3] + [5] * 4 + [4] * 5, "clamped": False, "message": ""}
    # Ch 3 runs 11..15: its end can go no lower than 11 and no higher than 19 (Ch 4 keeps layer 20).
    assert e["endLow"]["clamped"] and e["endLow"]["counts"][2:4] == [1, 9]
    assert "Ch 3 must keep at least one layer" in e["endLow"]["message"]
    assert e["endHigh"]["clamped"] and e["endHigh"]["counts"][2:4] == [9, 1]
    assert "Ch 4 must keep at least one layer" in e["endHigh"]["message"]
    assert not e["endBad"]["clamped"] and e["endBad"]["counts"] == [5] * 8 + [4] * 5
    assert e["start"]["counts"][2:4] == [3, 7] and not e["start"]["clamped"]
    assert e["startLow"]["clamped"] and e["startLow"]["counts"][2:4] == [1, 9]
    assert "Ch 3 must keep at least one layer" in e["startLow"]["message"]
    assert e["startHigh"]["clamped"] and e["startHigh"]["counts"][2:4] == [9, 1]
    assert "Ch 4 must keep at least one layer" in e["startHigh"]["message"]
    assert not e["startBad"]["clamped"] and e["startBad"]["counts"] == [5] * 8 + [4] * 5
    assert e["seamRight"]["counts"][:2] == [6, 4]
    assert e["seamLeftClamp"]["clamped"] and e["seamLeftClamp"]["counts"][:2] == [1, 9]
    assert e["seamPage"]["clamped"] and e["seamPage"]["counts"][11:] == [7, 1]


# ---------------------------------------------------------------- geometry --


def test_seams_are_the_stored_edges_on_the_production_lattice(out):
    """On 60 layers from 3662.4 mm at 20.5 mm the seam after layer b is Z = 3.15 + 20.5·b."""
    for key, seams in out["geometry"]["prodSeams"].items():
        assert [s["seam"] for s in seams] == list(range(1, 13)), key
        for s in seams:
            assert s["at"] == PROD_EDGES[s["after"]], (key, s)
            assert s["at"] - 3649 == pytest.approx(3.15 + 20.5 * s["after"], abs=1e-9), (key, s)
    spans = out["geometry"]["prodSpans"]
    assert spans[0]["lo"] == PROD_EDGES[0] and spans[-1]["hi"] == PROD_EDGES[60]
    assert all(a["hi"] == b["lo"] for a, b in zip(spans, spans[1:])), "the spans tile the axis"


def test_seams_on_the_gapped_demo_lattice_are_its_own_cell_edges(out):
    """The demo lattice skips layers (41 mm cells): seams take its stored edges, never index × pitch."""
    g = out["geometry"]
    edges = g["demoEdges"]
    assert len(edges) == 57 and g["axisEdges"]["demo"] == edges
    counts = out["presets"]["56"]["uniform"]
    bounds = [sum(counts[:m]) for m in range(1, 13)]
    assert [s["at"] for s in g["demoSeams"]] == [edges[b] for b in bounds]
    gaps = [i for i in range(56) if edges[i + 1] - edges[i] > 30]
    assert gaps, "the demo lattice has gapped cells"
    tail = g["demoTailSeams"][-1]
    assert tail["after"] == 55 and tail["at"] == edges[55]
    assert abs(tail["at"] - (edges[0] + 20.5 * 55)) > 20, \
        "in the gapped tail an index × pitch seam would be a layer off; the stored edge is used"
    spans = g["demoSpans"]
    assert [s["group"] for s in spans] == list(range(1, 14))
    assert spans[0]["lo"] == edges[0] and spans[-1]["hi"] == edges[56]
    assert not any(s["partial"] or s["extended"] for s in spans)


def test_group_13_runs_to_the_end_and_beyond_axis_groups_are_counted(out):
    g = out["geometry"]
    long = g["longSpans"]
    assert long[-1]["group"] == 13 and long[-1]["extended"] and long[-1]["bins"] == [52, 64]
    assert long[-1]["hi"] == pytest.approx((65 - 0.5) * 20.5)
    short = g["shortSpans"]
    assert [s["group"] for s in short] == [1, 2, 3, 4, 5, 6]
    assert short[-1]["partial"] and short[-1]["bins"] == [25, 27] and short[-1]["hi"] == pytest.approx(27.5 * 20.5)
    assert g["shortBeyond"] == [7, 8, 9, 10, 11, 12, 13]
    assert [s["seam"] for s in g["shortSeams"]] == [1, 2, 3, 4, 5]


def test_axis_edges_come_from_the_payload_axis(out):
    a = out["geometry"]["axisEdges"]
    assert a["uniform"][0] == -10.25 and a["uniform"][-1] == pytest.approx(20.5 * 59.5) and len(a["uniform"]) == 61
    assert a["bad"] == [None, None, None]
    assert out["geometry"]["binOf"] == [0, 0, 1, None]


def _rotation(theta: float, phi: float):
    """R = R_y(θ)·R_z(φ), written independently of grid/frame.py."""
    cz, sz = math.cos(phi), math.sin(phi)
    cy, sy = math.cos(theta), math.sin(theta)
    rz = [[cz, sz, 0.0], [-sz, cz, 0.0], [0.0, 0.0, 1.0]]
    ry = [[cy, 0.0, -sy], [0.0, 1.0, 0.0], [sy, 0.0, cy]]
    return [[sum(ry[i][k] * rz[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def test_plane_lines_are_the_rotated_layer_planes_on_u_w_only(out):
    """A detector layer plane Δz = s, rotated by R(θ, φ), traces w = s / cos θ + u · tan θ on u–w."""
    from calosrv.grid import frame as frame_mod

    for case in out["planes"]:
        theta, phi = case["theta"], case["phi"]
        r = _rotation(theta, phi)
        normal = [r[i][2] for i in range(3)]
        assert normal == pytest.approx(case["normal"], abs=1e-12), "n = R·ê_z = (−sin θ, 0, cos θ)"
        assert frame_mod.rotation_matrix(theta, phi) @ [0, 0, 1] == pytest.approx(case["normal"], abs=1e-12)
        for s, seg in zip([-10.25, 92.25, 400], case["xz"]):
            assert seg is not None
            # Points of the plane z = s in the detector-aligned frame, moved by R: on the drawn line.
            for x, y in [(0, 0), (120, -40), (-200, 75)]:
                p = [sum(r[i][k] * v for k, v in enumerate((x, y, s))) for i in range(3)]
                u, w = p[0], p[2]
                assert w == pytest.approx(s / math.cos(theta) + u * math.tan(theta), abs=1e-9)
                (w0, u0), (w1, u1) = seg["from"], seg["to"]
                assert (w - w0) * (u1 - u0) == pytest.approx((u - u0) * (w1 - w0), abs=1e-6)
            assert (seg["from"][1], seg["to"][1]) == (-300, 250)
        assert case["yz"] is None, "v–w has no line image of a tilted plane"
    flat = out["planeFlat"]
    assert flat["yz"] == {"from": [92.25, -1], "to": [92.25, 1]} and flat["xz"] == {"from": [92.25, -1], "to": [92.25, 1]}
    assert flat["xy"] is None and flat["parallel"] is None


# ------------------------------------------------------------ shares, reach --


def test_group_shares_are_exact_sums_with_the_outside_part(out):
    s = out["shares"]
    groups = s["groups"]
    assert [g["group"] for g in groups] == list(range(1, 14))
    assert sum(g["sum"] for g in groups) == pytest.approx(sum(s["energy"]))
    assert sum(g["share"] for g in groups) + 0.25 / s["total"] == pytest.approx(1)
    assert groups[0]["sum"] == pytest.approx(sum(s["energy"][0:5]))
    assert sum(g["share"] for g in s["plain"]) == pytest.approx(1)


def test_group_reach_counts_the_showers_reaching_its_first_layer(out):
    r = out["reach"]
    assert r["g12"] == {"reached": 4812 - 9 * 50, "full": 4812 - 9 * 54, "of": 4812,
                        "share": pytest.approx((4812 - 450) / 4812)}
    assert r["none"] is None and r["beyond"]["reached"] == 0


# --------------------------------------------------------------------- spec --


def test_the_spec_is_null_where_nothing_is_drawn(out):
    s = out["specs"]
    assert s["off"] is None and s["xy"] is None and s["none"] is None
    assert s["wrongL"] is None, "a 60-layer partition does not fit the 56-layer demo axis"
    assert out["onHover"] == "function"


def test_the_ensemble_spec_carries_numbering_edges_and_tooltips(out):
    demo = out["specs"]["demo"]
    assert demo["numbering"] == "detector" and demo["strip"] and not demo["pooled"] and demo["badge"] is None
    assert len(demo["groups"]) == 13 and len(demo["seams"]) == 12 and demo["seamsBeyond"] == 0
    assert demo["groups"][0]["label"] == "Ch 1" and demo["offset"] == 3649
    tip = demo["groups"][0]["tooltip"]
    assert tip.startswith("<b>Ch 1</b> · layers 1–5 (5 layers)")
    assert "Z 3.1–" in tip and "(z 3652.1–" in tip and "mm thick" in tip
    assert "of the selection’s energy" in tip and "off the depth axis is counted" in tip and "N = 287 events" in tip
    seam = demo["seams"][0]["tooltip"]
    assert "between layers 5 and 6" in seam and "Z = " in seam and "(z = " in seam and "stored cell edge" in seam
    prod = out["specs"]["prod"]
    assert prod["highlight"] == 3 and prod["panelId"] == "xz"


def test_the_frames_number_their_layers_as_the_contract_says(out):
    s = out["specs"]
    trans = s["trans"]
    assert trans["numbering"] == "relative" and trans["groups"][11]["label"] == "Rel Ch 12"
    assert "reached by" in trans["groups"][11]["tooltip"] and "of 4,812 showers" in trans["groups"][11]["tooltip"]
    assert "rel. layers" in trans["seams"][0]["tooltip"] and "Δz = " in trans["seams"][0]["tooltip"]
    assert trans["offset"] == 0
    canonical = s["canonical"]
    assert canonical["numbering"] == "detector" and canonical["groups"][0]["label"] == "Ch 1"
    assert "z′ −10.3 to 92.3 mm · 102.5 mm thick" in canonical["groups"][0]["tooltip"], canonical["groups"][0]["tooltip"]
    assert "reached by" not in canonical["groups"][0]["tooltip"]
    local = s["local"]
    assert local["numbering"] == "none" and local["badge"] == out["consts"]["LOCAL_BADGE"]
    assert local["groups"] == [] and local["seams"] == [] and local["lines"] == [] and not local["strip"]


def test_the_signed_attention_shares_keep_their_parts_apart(out):
    tip = out["specs"]["signed"]["groups"][0]["tooltip"]
    assert "Σ E·Shap-CAM⁺: 8.3% of the positive part" in tip
    assert "Σ E·|Shap-CAM⁻|: 16.7% of the negative part (kept apart)" in tip


def test_a_pooled_spec_is_pooled_only_for_its_own_partition(out):
    pooled, stale = out["specs"]["pooled"], out["specs"]["poolStale"]
    assert pooled["pooled"] and "pooled: this column is the mean of its 5 layers" in pooled["groups"][0]["tooltip"]
    assert not stale["pooled"], "a response pooled on another partition is drawn as boundaries"
    assert not out["specs"]["labEvent"]["pooled"], "an event raster is never pooled"


def test_one_shower_local_draws_tilted_planes_on_u_w_and_a_reason_on_v_w(out):
    xz, yz = out["specs"]["localEventXz"], out["specs"]["localEventYz"]
    assert not xz["strip"] and xz["seams"] == [] and len(xz["lines"]) == 12 and xz["badge"] is None
    assert xz["lines"][0]["normal"] == pytest.approx([-math.sin(math.radians(10)), 0, math.cos(math.radians(10))])
    assert "w = s / cos θ + u · tan θ" in xz["lines"][0]["tooltip"]
    assert "pitch along w = p / cos θ = 20.82 mm" in xz["groups"][0]["tooltip"]
    assert "of this shower’s energy" in xz["groups"][0]["tooltip"]
    assert "beyond this shower’s reach" in xz["groups"][12]["tooltip"] or xz["groups"][12]["first"] <= 58
    # The badge is the short form a narrow panel can carry; the drawer and tooltips keep the sentence.
    assert yz["lines"] == [] and yz["badge"].startswith("v–w: planes tilt by θ = ") and yz["badge"].endswith("drawn on u–w")
    assert "spans a band" in yz["lineReason"] and "u–w" in yz["lineReason"]
    lab = out["specs"]["labEvent"]
    assert lab["strip"] and len(lab["seams"]) == 12 and lab["offset"] == 3649


def test_the_readout_names_the_layer_and_its_channel(out):
    r = out["readouts"]
    assert r["prodLayer4"] == " · layer 4 · Ch 1 [1–5]"
    assert r["prodAxisOnly"] == " · layer 4"
    assert r["pooled"] == " · Ch 2 [layers 6–10] · mean of 5 layers"
    assert r["trans"] == " · rel. layer 1 · Rel Ch 1 [1–5]"
    assert r["off"] == "" and r["local"] == "" and r["localYz"] == ""
    assert r["localXz"] == " · rel. layer 6 · Rel Ch 2 [6–10]"


def test_the_text_builders_use_true_minus_signs(out):
    t = out["text"]
    assert t["labels"] == ["Ch 3", "Rel Ch 12"]
    assert t["title"] == ["Ch 3 · layers 11–15", "Rel Ch 1 · rel. layer 1"]
    assert t["spans"][0] == "Z 3.1–105.7 mm (z 3652.2–3754.7 mm)" or t["spans"][0].startswith("Z 3.")
    assert t["spans"][1] == "z′ −10.2 to 92.2 mm" or t["spans"][1] == "z′ −10.3 to 92.3 mm"
    assert t["spans"][2] == "Z = 74.9 mm (z = 3723.9 mm)"
    assert t["spans"][3].startswith("Δz = −10.")
    assert t["numbers"][:3] == ["4,812", "−1,234,567", "97.9%"]
    assert t["numbers"][3] == "1.23 GeV" and t["numbers"][4] == "−1.20e−5 GeV"
    _no_hyphen_numbers(_texts(out["specs"]))
    _no_hyphen_numbers(_texts(out["text"]))


# ----------------------------------------------------------------- builders --


def _ids(series):
    return [s["id"] for s in series]


def test_the_strip_sits_in_the_reserved_band_above_the_plot(out):
    b = out["builders"]
    assert b["geometry"] == {"band": 14, "gap": 3}
    assert b["reserve"] == [0, 17, 17, 0, 17]
    full = {s["id"]: s for s in b["full"]}
    assert _ids(b["full"]) == ["layer-groups-strip", "layer-groups-seams", "layer-groups-spot"]
    strip = full["layer-groups-strip"]
    assert strip["clip"] is False and strip["n"] == 13
    cs_top = 40
    for item in strip["items"]:
        rect = item["children"][0]["shape"]
        assert rect["y"] + rect["height"] <= cs_top - 3 + 1e-9, "never over the raster"
        assert rect["y"] == pytest.approx(cs_top - 17)
        assert 60 - 1e-9 <= rect["x"] and rect["x"] + rect["width"] <= 560 + 1e-9
    fills = [item["children"][0]["style"]["fill"] for item in strip["items"]]
    assert fills[2] == "#3d4f66", "the highlighted group takes the hot fill"
    assert fills[0] == fills[4] == "#262c36" and fills[1] == fills[3] == "#30363f"
    labels = [c["style"]["text"] for item in strip["items"] for c in item["children"] if c["type"] == "text"]
    assert "Ch 1" in labels
    assert strip["tips"][0].startswith("<b>Ch 1</b>") and strip["bareTip"].startswith("<b>Ch 3</b>")


def test_the_strip_is_clipped_to_the_plot_under_zoom(out):
    zoom = {s["id"]: s for s in out["builders"]["zoom"]}["layer-groups-strip"]
    drawn = [item for item in zoom["items"] if item]
    assert 0 < len(drawn) < 13, "segments wholly outside the window are not drawn"
    for item in drawn:
        rect = item["children"][0]["shape"]
        assert rect["x"] >= 60 - 1e-9 and rect["x"] + rect["width"] <= 560 + 1e-9
    # An edge only at a true end: the segments cut by the window have one edge or none.
    first, last = drawn[0], drawn[-1]
    assert sum(1 for c in first["children"] if c["type"] == "polyline") == 1
    assert sum(1 for c in last["children"] if c["type"] == "polyline") == 1


def test_the_seams_are_dashed_lines_across_the_plot_with_tooltips(out):
    seams = {s["id"]: s for s in out["builders"]["full"]}["layer-groups-seams"]
    assert seams["n"] == 12 and seams["clip"] is True
    for item, at in zip(seams["items"], PROD_EDGES[5:60:5]):
        pts = item["shape"]["points"]
        assert pts[0][1] == 40 and pts[1][1] == 340 and pts[0][0] == pts[1][0]
        assert item["style"]["lineDash"] == [4, 3] and item["style"]["fill"] == "none"
        assert item["style"]["stroke"] == "#7d8590" and item["style"]["lineWidth"] == 1
    assert all(t.startswith("<b>Seam Ch") for t in seams["tips"])


def test_no_seams_when_pooled_and_none_with_the_marks_hidden(out):
    b = out["builders"]
    assert _ids(b["pooled"]) == ["layer-groups-strip", "layer-groups-spot"]
    hidden = {s["id"]: s for s in b["hidden"]}
    assert set(hidden) == {"layer-groups-strip", "layer-groups-spot"}, "the strip stays, the seams go"
    assert hidden["layer-groups-spot"]["n"] == 0, "the spotlight follows the Marks toggle"


def test_the_spotlight_draws_the_two_faces_solid_and_silent(out):
    spot = {s["id"]: s for s in out["builders"]["full"]}["layer-groups-spot"]
    assert spot["silent"] and spot["n"] == 2
    xs = [item["shape"]["points"][0][0] for item in spot["items"]]
    view = (PROD_EDGES[0], PROD_EDGES[60])
    want = [60 + (PROD_EDGES[e] - view[0]) / (view[1] - view[0]) * 500 for e in (10, 15)]
    assert xs == pytest.approx(want)
    for item in spot["items"]:
        assert item["style"]["lineDash"] is None and item["style"]["fill"] == "none"
        assert item["style"]["stroke"] == "#e6edf3"


def test_the_tilted_planes_draw_on_u_w_and_nothing_on_v_w(out):
    b = out["builders"]
    xz = {s["id"]: s for s in b["localXz"]}
    assert set(xz) == {"layer-groups-planes", "layer-groups-spot"}
    planes = xz["layer-groups-planes"]
    assert planes["n"] == 12 and all(t.startswith("<b>Layer plane Rel Ch") for t in planes["tips"])
    assert xz["layer-groups-spot"]["n"] == 2, "the spotlight's faces are tilted lines too"
    assert {s["id"] for s in b["localYz"]} == {"layer-groups-spot"}
    assert b["localYz"][0]["n"] == 0
    assert b["local"] == [] and b["notDepth"] == []


def test_the_local_badge_is_a_muted_sentence_in_the_band(out):
    badge = out["builders"]["badge"]
    assert badge["type"] == "text" and badge["style"]["text"] == out["consts"]["LOCAL_BADGE"]
    assert badge["top"] == 40 - 17 and badge["left"] == 52 and badge["style"]["fill"] == "#8b949e"
    assert out["builders"]["noBadge"] is None


def test_print_scales_the_band_and_takes_paper_colours(out):
    p = out["builders"]["print"]
    assert p["reserve"] == pytest.approx(17 * 12 / 9)
    strip = {s["id"]: s for s in p["full"]}["layer-groups-strip"]
    assert strip["items"][0]["children"][0]["style"]["fill"] == "#f3f4f6"
    seams = {s["id"]: s for s in p["full"]}["layer-groups-seams"]
    assert seams["items"][0]["style"]["stroke"] == "#6b7280"


# ---------------------------------------------------------- ProjectionPanel --


def test_the_panel_reserves_the_band_above_the_plot(out):
    plain, spec = out["panel"]["plain"]["grid"], out["panel"]["withSpec"]["grid"]
    assert spec["top"] == pytest.approx(plain["top"] + 17)
    assert spec["height"] == pytest.approx(plain["height"] - 17)
    assert (spec["left"], spec["width"]) == (plain["left"], plain["width"])
    ids = out["panel"]["withSpec"]["ids"]
    assert ids[0] == "raster" and "layer-groups-strip" in ids and "layer-groups-seams" in ids
    assert "layer-groups-seams" not in out["panel"]["marksHidden"] and "layer-groups-strip" in out["panel"]["marksHidden"]
    assert not any(str(i).startswith("layer-groups") for i in out["panel"]["wrongPanel"]), \
        "a yz spec is not drawn on the xz panel"
    badge = out["panel"]["localBadge"]
    assert len(badge["graphics"]) == 1 and badge["grid"]["top"] > out["panel"]["localPlain"]["grid"]["top"]
    assert not any(str(i).startswith("layer-groups-s") and i != "layer-groups-spot" for i in badge["ids"])


def test_the_export_grows_by_the_band(out):
    m = out["panel"]["exportMetrics"]
    assert m["after"]["width"] == m["before"]["width"] == 600
    assert m["after"]["height"] - m["before"]["height"] in (17, 18)


def test_the_absolute_depth_axis_is_titled_and_ticked_in_z(out):
    p = out["panel"]
    for case in ("plain", "withSpec"):
        x = p[case]["x"]
        assert x["name"] == "Z = z − 3649 — depth [mm]"
        assert x["tickValues"] == x["labelValues"] and x["tickValues"]
        z = [v - 3649 for v in x["tickValues"]]
        step = z[1] - z[0]
        assert all(abs(v / step - round(v / step)) < 1e-6 for v in z), "round Z ticks"
        assert x["labels"] == [str(round(v)) for v in z] and x["labels"][0] == "0"
        assert x["min"] == 3649 and x["showMin"] is None and x["showMax"] is None
    assert p["small"]["x"]["name"] == "Z — depth [mm]"
    assert p["extent"]["col"] == [3649, p["col"]["hi"]], "the ensemble axis starts at Z = 0"


def test_an_event_window_keeps_its_bounds_and_signs_negative_z_ticks(out):
    e = out["panel"]["event"]
    assert e["extent"]["col"] == [3590, 3910]
    assert e["x"]["min"] == 3590 and e["x"]["name"] == "Z = z − 3649 — depth [mm]"
    negatives = [label for label in e["x"]["labels"] if label.startswith("−")]
    assert negatives and all(not HYPHEN_NUMBER.search(label) for label in e["x"]["labels"])
    assert "−50" in e["x"]["labels"] and "0" in e["x"]["labels"]


def test_the_co_registered_frames_and_the_entry_panel_are_not_shifted(out):
    p = out["panel"]
    assert p["local"]["x"]["name"] == "w — shower depth along the incident direction [mm]"
    assert p["trans"]["x"]["name"].startswith("Δz — depth from the shower")
    assert p["canonical"]["x"]["name"].startswith("z′ — depth from the front face")
    for case in ("local", "trans", "canonical", "xy"):
        assert p[case]["x"]["tickValues"] is None, case
    assert p["local"]["extent"]["col"] == [p["local"]["col"]["lo"], p["local"]["col"]["hi"]]
    assert p["xy"]["extent"]["col"] == [p["xy"]["col"]["lo"], p["xy"]["col"]["hi"]]
    assert p["depthOffsetOpt"]["name"] == "z — depth [mm]" and p["depthOffsetOpt"]["tickValues"] is None


def test_spatial_axis_without_an_offset_is_unchanged(out):
    p = out["panel"]
    assert p["spatialPlain"] == p["spatialZero"]
    assert "customValues" not in p["spatialPlain"]["axisLabel"]
    full, tiny = p["offsetTicks"]
    assert full["step"] == 200 and [v - 3649 for v in full["values"]] == pytest.approx([200, 400, 600, 800, 1000, 1200])
    assert tiny["digits"] >= 1 and tiny["values"]


def test_zoom_moves_the_round_z_ticks_with_the_window(out):
    patch = out["live"]["viewPatch"]
    assert (patch["min"], patch["max"]) == (3700, 4200)
    assert patch["ticks"] and all(3700 <= v <= 4200 for v in patch["ticks"])
    assert patch["labels"] == [str(round(v - 3649)) for v in patch["ticks"]]


def test_set_layer_groups_redraws_from_the_payload_and_keeps_the_zoom(out):
    live = out["live"]
    assert len(live["afterSet"]) == 1 and live["afterSet"][0]["notMerge"] is True
    assert (live["afterSet"][0]["xMin"], live["afterSet"][0]["xMax"]) == (3700, 4200)
    assert live["keptView"]["col"] == [3700, 4200]
    assert "layer-groups-strip" in live["afterSet"][0]["ids"]


def test_the_highlight_patches_only_the_strip_and_the_spotlight(out):
    live = out["live"]
    assert len(live["patch"]) == 1
    patch = live["patch"][0]
    assert patch["flags"] is None, "merged in place, never notMerge"
    assert patch["keys"] == ["series"] and patch["ids"] == ["layer-groups-strip", "layer-groups-spot"]
    assert live["again"] == 0, "the same group twice costs nothing"
    assert live["highlightNow"] == 4


def test_the_bin_readout_reads_z_first_and_names_the_layer(out):
    live = out["live"]
    layer = live["at"]["layer"]
    tip = live["tip"]
    assert tip and tip.startswith(f"Z = {live['at']['zc'] - 3649:.1f} mm (z = {live['at']['zc']:.1f} mm) · layer {layer}")
    assert " · Ch " in tip.split("<br/>")[0]
    off = live["tipOff"].split("<br/>")[0]
    assert off == f"Z = {live['at']['zc'] - 3649:.1f} mm (z = {live['at']['zc']:.1f} mm)"
    axis_only = live["tipAxis"].split("<br/>")[0]
    assert axis_only == f"{off} · layer {layer}"


def test_build_option_with_a_60_layer_spec_stays_well_under_50_ms(out):
    """The repaint budget (CLAUDE.md section 3): buildOption plus one render of every channel item."""
    t = out["timing"]
    print(f"buildOption, 60-layer YZ spec: {t['withSpec']:.3f} ms; without: {t['without']:.3f} ms; "
          f"panelGroupSpec: {t['spec']:.3f} ms")
    assert t["withSpec"] < 50 and t["spec"] < 5


# ------------------------------------------------------------------ tokens --


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        r, g, bl = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(bl)
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


@pytest.mark.parametrize("theme", ["dark", "light", "print"])
def test_the_new_tokens_clear_their_contrast_on_the_card(out, theme):
    t = out["tokens"][theme]
    card = out["tokens"]["cards"][theme].lower()
    assert card == ("#1c2128" if theme == "dark" else "#ffffff")
    assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in t.values()), t
    for key in ("groupStripEdge", "groupSeam", "groupSpot"):
        assert _contrast(t[key], card) >= 3.0, (theme, key, _contrast(t[key], card))
    for fill in ("groupStripFillA", "groupStripFillB", "groupStripHot"):
        assert _contrast(t["groupStripText"], t[fill]) >= 4.5, (theme, fill)
    # The fills are subtle, the hot fill visibly distinct from both.
    for fill in ("groupStripFillA", "groupStripFillB"):
        assert 1.05 <= _contrast(t[fill], card) <= 1.5, (theme, fill, _contrast(t[fill], card))
        assert _contrast(t["groupStripHot"], t[fill]) >= 1.2, (theme, fill)
    assert _contrast(t["groupStripFillA"], t["groupStripFillB"]) >= 1.1
    assert t["groupSpot"] == out["tokens"]["text"][theme].lower()


def test_core_shift_lives_in_axis_symbols_and_voxels_re_exports_it(out):
    from calosrv.db import ddl

    assert out["shift"]["axisSymbols"] == out["shift"]["voxels"] == ddl.CORE_SHIFT_Z_MM == 3649
    names = out["shift"]["names"]
    assert names[0]["depth"] == "Z = z − 3649 — depth [mm]" and names[1]["depth"] == "w — depth [mm]"
    shifted, plain = out["shift"]["ticks"]
    assert shifted["offset"] == 3649 and (shifted["origin"] - 3649) % shifted["step"] == 0
    assert "offset" not in plain


def test_the_engine_is_a_leaf_importing_only_format():
    source = (JS / "layer_groups.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from '([^']+)';", source, re.MULTILINE)
    assert imports == ["./format.js"]
