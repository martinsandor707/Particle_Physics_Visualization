"""The energy-resolution card's Deposit toggle, E max and active-only export, run under Node on the recordings.

Martin's decisions of 2026-11-17 (brief res-emax, section 5): the calibrated deposit is a card toggle on both views
whose error-scale range follows the series on show (`axis.y_model`, `axis.energy.y_model`); the E view ends at an
E max slider's value, from the data's top edge to the server's axis end, with nothing drawn beyond it on either
panel; with the deposit hidden and no literature curve on, the ratio panel draws no ratio mark and says so; the
canvas notes describe drawn marks only; and an export leaves out every mark of a legend entry the reader switched
off, with its end labels and its off-scale values.

The script runs the panel's pure builders (`resolution_scaling.js`) on every recorded `res_scaling*` payload
(`tests/fixtures/payloads/`), renders every custom series' `renderItem` and calls every tooltip formatter, and
hands back what was drawn. The identity cases hold the dark golden's promise from this side: without the new
options, and with no export in progress, every builder returns exactly what it returned before. Skipped without
`node`.
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

#: The recordings with a model series beside the deposit (two showers, or the XGBoost hold-out).
WITH_MODELS = ["res_scaling_two", "res_scaling_median_two", "res_scaling_robust_two",
               "res_scaling_xgb", "res_scaling_median_xgb", "res_scaling_robust_xgb"]
#: The recordings whose only series is the deposit: the toggle cannot hide it there.
DEPOSIT_ONLY = ["res_scaling_single_hits", "res_scaling_single_events", "res_scaling_median_single_hits",
                "res_scaling_median_single_events", "res_scaling_robust_single_hits", "res_scaling_robust_single_events"]
#: The recordings whose model series draw on the E view with the deposit hidden (robust_xgb has no robust model window).
DRAWING = ["res_scaling_two", "res_scaling_median_two", "res_scaling_robust_two", "res_scaling_xgb", "res_scaling_median_xgb"]

EMPTY_SENTENCE = ("The calibrated deposit is hidden, and the model series have no window to draw in this selection; "
                  "switch on Deposit to draw it.")
NONE_TEXT = "No ratio drawn: no reference is on show."
NONE_SCREEN = " Switch on π±, e± or the deposit to draw one."

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir, opts] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const cp = await imp('panels/chart_panel.js');
const rs = await imp('panels/resolution_scaling.js');
const ra = await imp('res_axis.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const NAMES = fs.readdirSync(fixtureDir).filter((f) => /^res_scaling.*\.json$/.test(f)).map((f) => f.slice(0, -5)).sort();
const RW = { width: 760, height: 420 };
const RE = { width: 760, height: rs.ENERGY_VIEW_PX };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const identity = { coord: (p) => [Number(p[0]), Number(p[1])] };
// E stretched a millionfold: a pixel offset (a cap, a caret's wing, an end label's gap) is then a micro-GeV, so
// every rendered x divided back is the energy the mark is drawn at.
const SCALE = 1e6;
const stretched = { coord: (p) => [Number(p[0]) * SCALE, Number(p[1])] };
const SAMPLES = [0, 0.5, 1, 2, 5, 10, 20, 35, 40, 45, 80, -1];
const showersOf = (p) => (p.series.some((s) => s.shower === 'b') ? ['both', 'a', 'b'] : ['both']);
const legendNames = (o) => [].concat(o.legend ?? []).flatMap((l) => (l.data ?? []).map((d) => String(d?.name ?? d)));
const graphicsOf = (o) => [].concat(o.graphic ?? []).map((g) => g.style?.text).filter(Boolean);
const gridOf = (o) => [].concat(o.grid ?? []);
const out = {};

/** An option with every function exercised: each renderItem and tooltip per datum, each axis label at SAMPLES. */
function snap(option) {
  const series = [].concat(option.series ?? []).map((s) => ({
    rendered: typeof s.renderItem === 'function' ? (s.data ?? []).map((_, i) => s.renderItem({ dataIndex: i, coordSys }, identity)) : null,
    tips: typeof s.tooltip?.formatter === 'function'
      ? (s.data ?? []).map((d, i) => s.tooltip.formatter({ dataIndex: i, value: Array.isArray(d) ? d : d?.value })) : null,
  }));
  const axes = [...[].concat(option.xAxis ?? []), ...[].concat(option.yAxis ?? [])]
    .map((a) => (typeof a.axisLabel?.formatter === 'function' ? SAMPLES.map((v) => String(a.axisLabel.formatter(v))) : null));
  return JSON.stringify({ option, series, axes }, (k, v) => (typeof v === 'function' ? `fn:${v.toString()}` : v));
}

/** A model with its closures exercised: a reference's value over the axis, a series' line strengths. */
function snapModel(m) {
  return JSON.stringify(m, (k, v) => {
    if (typeof v !== 'function') return v;
    if (k === 'valueAt') return ['valueAt', ...[0, 0.5, 1, 2, 4, 5, 10, 20, 40, 80].map((e) => v(e))];
    if (k === 'lineOpacity') return ['lineOpacity', v(false), v(true)];
    return `fn:${v.toString()}`;
  });
}

/** Every mark drawn at an E beyond `xmax` (GeV), by its datum or its rendered geometry; [] when none is. */
function beyond(option, xmax) {
  const bad = [];
  const xs = (el, acc) => {
    if (!el) return;
    if (el.type === 'group') { for (const c of el.children ?? []) xs(c, acc); return; }
    const s = el.shape ?? {};
    if (Array.isArray(s.points)) for (const q of s.points) acc.push(q[0]);
    if (Number.isFinite(s.cx)) acc.push(s.cx);
    if (Number.isFinite(s.x1)) acc.push(s.x1, s.x2);
    if (el.type === 'text' && Number.isFinite(el.style?.x)) acc.push(el.style.x);
  };
  for (const s of [].concat(option.series ?? [])) {
    const id = s.id ?? s.name ?? '';
    (s.data ?? []).forEach((d, i) => {
      const v = Array.isArray(d) ? d : d?.value;
      if (Array.isArray(v) && Number.isFinite(v[0]) && v[0] > xmax + 1e-9) bad.push({ id, kind: 'datum', x: v[0] });
      if (typeof s.renderItem !== 'function') return;
      const acc = [];
      xs(s.renderItem({ dataIndex: i, coordSys }, stretched), acc);
      for (const x of acc) if (x / SCALE > xmax + 1e-4) bad.push({ id, kind: 'rendered', x: x / SCALE });
    });
  }
  return bad;
}

/** The end labels an option draws on one panel, {text, y} in identity coordinates, and their series' data. */
function endLabelsOf(option, ratio) {
  return [].concat(option.series ?? []).filter((s) => (s.id ?? '').endsWith('|endlabels') && Boolean(s.xAxisIndex) === ratio)
    .flatMap((s) => (s.renderItem({ dataIndex: 0, coordSys }, identity).children ?? [])
      .filter((c) => c.type === 'text').map((c) => ({ text: c.style.text, y: c.style.y, name: s.name, datum: s.data[0] })));
}

/* ---- identity: without the new options, every builder is today's ------------------------------------------- */
if (opts.part === 'identity') {
  out.identity = [];
  out.defaults = [];
  for (const name of NAMES) {
    const p = load(name);
    for (const windows of ['anchors', 'all']) {
      for (const shower of showersOf(p)) {
        for (const literature of [[], ['pi', 'e']]) {
          const base = { windows, shower, literature, palette: 'viridis', card: 'res-scaling' };
          const run = (o) => ({
            linear: snap(rs.resolutionScalingOption(p, o, RW)),
            energy: snap(rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option),
            dispatched: snap(rs.resolutionScalingOption(p, { ...o, view: 'energy' }, RE)),
            tableLinear: JSON.stringify(rs.fitTableRows(p, o)),
            tableEnergy: JSON.stringify(rs.fitTableRows(p, { ...o, view: 'energy' })),
            resolutionModel: snapModel(rs.resolutionModel(p, o)),
            energyModel: snapModel(rs.energyModel(p, o)),
            drawsPanels: String(rs.energyDrawsPanels(p, o)),
          });
          const ref = run(base);
          for (const [tag, o] of [['undefined', { ...base, deposit: undefined, eMax: undefined }], ['depositTrue', { ...base, deposit: true }]]) {
            const got = run(o);
            out.identity.push({ name, windows, shower, literature, tag, equal: Object.fromEntries(Object.keys(ref).map((k) => [k, got[k] === ref[k]])) });
          }
          const em = rs.energyModel(p, base);
          const rm = rs.resolutionModel(p, base);
          out.defaults.push({ name, windows, shower, literature, x: em.x, eY: em.y, rY: rm.y, eDeposit: em.deposit, rDeposit: rm.deposit,
            none: em.ratio.none, reference: em.reference.key });
        }
      }
    }
  }
}

/* ---- the Deposit toggle ---------------------------------------------------------------------------------- */
if (opts.part === 'deposit') {
  out.hidden = [];
  for (const name of %(with_models)s) {
    const p = load(name);
    const depositLabels = p.series.filter((s) => ra.isDepositSeries(s)).map((s) => s.label);
    for (const windows of ['anchors', 'all']) {
      for (const shower of showersOf(p)) {
        for (const literature of [[], ['pi', 'e']]) {
          for (const eMax of [undefined, null]) {
            const o = { windows, shower, literature, deposit: false, eMax, palette: 'viridis', card: 'res-scaling' };
            const rm = rs.resolutionModel(p, o);
            const em = rs.energyModel(p, o);
            const lin = rs.resolutionScalingOption(p, o, RW);
            const en = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
            const tl = rs.fitTableRows(p, o);
            const te = rs.fitTableRows(p, { ...o, view: 'energy' });
            out.hidden.push({
              name, windows, shower, literature, eMax: eMax === undefined ? 'undefined' : eMax, depositLabels,
              rKeys: rm.series.map((s) => s.key), eKeys: em.series.map((s) => s.key),
              tableKeys: [...tl.rows.map((r) => r.key), ...te.rows.map((r) => r.key)],
              legends: [...legendNames(lin), ...legendNames(en)],
              seriesNames: [lin, en].flatMap((x) => [].concat(x.series ?? []).map((s) => s.name ?? null)),
              rY: rm.y, eY: em.y, rDeposit: rm.deposit, eDeposit: em.deposit,
              linYMax: lin.legend ? [].concat(lin.yAxis)[0].max : null, enYMax: en.legend ? [].concat(en.yAxis)[0].max : null,
              offScale: em.offScale.flatMap((g) => g.entries.map((e) => e.key)),
            });
          }
        }
      }
    }
  }
  out.forced = [];
  for (const name of %(deposit_only)s) {
    const p = load(name);
    for (const windows of ['anchors', 'all']) {
      const base = { windows, shower: 'both', literature: [], palette: 'viridis', card: 'res-scaling' };
      const o = { ...base, deposit: false };
      const em = rs.energyModel(p, o);
      const rm = rs.resolutionModel(p, o);
      out.forced.push({
        name, windows, eKeys: em.series.map((s) => s.key), rKeys: rm.series.map((s) => s.key), eDeposit: em.deposit, rDeposit: rm.deposit,
        eY: em.y, rY: rm.y, tableKeys: rs.fitTableRows(p, o).rows.map((r) => r.key), reference: em.reference.key,
        sameLinear: snap(rs.resolutionScalingOption(p, o, RW)) === snap(rs.resolutionScalingOption(p, base, RW)),
        sameEnergy: snap(rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option) === snap(rs.energyViewOption(p, { ...base, view: 'energy' }, RE).option),
      });
    }
  }
  // The empty state: the deposit hidden where the model series draw nothing; and nowhere else.
  out.empty = [];
  for (const name of %(with_models)s) {
    const p = load(name);
    for (const windows of ['anchors', 'all']) {
      for (const literature of [[], ['pi', 'e']]) {
        for (const deposit of [undefined, false]) {
          const o = { windows, shower: 'both', literature, deposit, palette: 'viridis', card: 'res-scaling' };
          const lin = rs.resolutionScalingOption(p, o, RW);
          const en = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
          const em = rs.energyModel(p, o);
          out.empty.push({ name, windows, literature, deposit: deposit === undefined ? 'undefined' : deposit,
            linear: graphicsOf(lin), energy: graphicsOf(en), drawsPanels: rs.energyDrawsPanels(p, o),
            modelDraws: em.nPoints + em.nLines, hidden: em.deposit.hidden });
        }
      }
    }
  }
  // A shower whose only series is its deposit (shower B's network taken out of the two-shower recording): with the
  // deposit hidden it draws nothing, so both views say the deposit is hidden; with the deposit shown it draws.
  {
    const p = clone(load('res_scaling_two'));
    p.series = p.series.filter((s) => s.key !== 'network:b');
    const o = { windows: 'all', shower: 'b', literature: [], palette: 'viridis', card: 'res-scaling' };
    out.depositOnlyShower = {
      hidden: [graphicsOf(rs.energyViewOption(p, { ...o, view: 'energy', deposit: false }, RE).option),
        graphicsOf(rs.resolutionScalingOption(p, { ...o, deposit: false }, RW))],
      shown: rs.energyDrawsPanels(p, o),
    };
  }
  // The same state in print (review R2-4): no hidden series named, no screen instruction.
  {
    const p = load('res_scaling_robust_xgb');
    const o = { windows: 'anchors', shower: 'both', literature: ['pi', 'e'], deposit: false, palette: 'viridis', card: 'res-scaling' };
    Object.assign(scale.THEME, PRINT_TOKENS);
    try {
      out.emptyPrint = [graphicsOf(rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option),
        graphicsOf(rs.resolutionScalingOption(p, o, RW))];
    } finally {
      scale.restoreScreenTheme();
    }
  }
}

/* ---- E max -------------------------------------------------------------------------------------------- */
if (opts.part === 'emax') {
  out.emax = [];
  for (const name of NAMES) {
    const p = load(name);
    for (const asked of ['undefined', null, 20, 22.4, 22.5, 37, 45, 1000]) {
      for (const windows of ['anchors', 'all']) {
        for (const literature of [[], ['pi', 'e']]) {
          for (const deposit of [undefined, false]) {
            const o = { windows, shower: 'both', literature, deposit, palette: 'viridis', card: 'res-scaling', ...(asked === 'undefined' ? {} : { eMax: asked }) };
            const m = rs.energyModel(p, o);
            const built = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
            const drawn = gridOf(built).length === 2;
            const xa = [].concat(built.xAxis);
            out.emax.push({
              name, asked, windows, literature, deposit: deposit === undefined ? 'undefined' : deposit, drawn,
              x: { min: m.x.min, max: m.x.max, interval: m.x.interval, name: m.x.name, serverMax: m.x.serverMax, ticks: m.x.ticks, eMax: m.x.eMax },
              axes: drawn ? xa.map((a) => ({ min: a.min ?? null, max: a.max ?? null, tick: a.axisTick?.customValues ?? null,
                label: a.axisLabel?.customValues ?? null, show: a.axisLabel?.show !== false, interval: a.interval ?? null })) : null,
              beyond: beyond(built, m.x.max),
              endLabels: drawn ? [...endLabelsOf(built, false), ...endLabelsOf(built, true)].map((l) => l.datum[0]) : [],
              ratioMarks: m.series.flatMap((s) => s.points).filter((pt) => pt.ratio.drawn).length,
              curves: m.series.filter((s) => s.drawn).length,
              dataMax: p.axis.energy.data_max_gev, server: p.axis.energy.x,
            });
          }
        }
      }
    }
  }
  // The windows set on show and the y range never depend on E max: no fit is refitted, no range recomputed.
  out.unchanged = [];
  for (const name of NAMES) {
    const p = load(name);
    const o = { windows: 'all', shower: 'both', literature: ['pi', 'e'] };
    const a = rs.energyModel(p, o);
    const b = rs.energyModel(p, { ...o, eMax: null });
    out.unchanged.push({ name, y: [a.y, b.y], points: [a.nPoints, b.nPoints],
      fits: [a.series.map((s) => JSON.stringify(s.drawn?.fit ?? null)), b.series.map((s) => JSON.stringify(s.drawn?.fit ?? null))] });
  }
}

/* ---- no reference, and the canvas notes -------------------------------------------------------------- */
if (opts.part === 'none') {
  out.none = [];
  for (const name of %(drawing)s) {
    const p = load(name);
    for (const windows of ['anchors', 'all']) {
      for (const shower of showersOf(p)) {
        for (const eMax of [undefined, null]) {
          const o = { windows, shower, literature: [], deposit: false, eMax, palette: 'viridis', card: 'res-scaling' };
          const m = rs.energyModel(p, o);
          const built = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
          const g = gridOf(built);
          const ratioAxis = [].concat(built.yAxis)[1] ?? null;
          const pad = scale.axisPadding();
          const noneGraphic = [].concat(built.graphic ?? []).find((x) => String(x.style?.text ?? '').startsWith('No ratio drawn')) ?? null;
          out.none.push({
            name, windows, shower, eMax: eMax === undefined ? 'undefined' : eMax, drawn: g.length === 2,
            reference: { key: m.reference.key, choice: m.reference.choice, label: m.reference.label, literature: m.reference.literature,
              flag: m.reference.flag,
              byShower: Object.fromEntries(Object.entries(m.reference.byShower).map(([k, r]) => [k, { ...r, valueAt: [0, 1, 5, 20, 80].map((e) => r.valueAt(e)) }])) },
            ratio: { none: m.ratio.none, provisional: m.ratio.provisional, capped: m.ratio.capped, belowNotDrawn: m.ratio.belowNotDrawn,
              below: m.ratio.below, noReference: m.ratio.noReference, reference: m.ratio.reference, clipped: m.ratio.clipped },
            pointRatios: m.series.flatMap((s) => s.points.map((pt) => ({ drawn: pt.ratio.drawn, reason: pt.ratio.reason }))),
            curveRatios: m.series.map((s) => s.drawn?.ratio ?? null),
            ratioEndLabels: m.endLabels.ratio.length,
            choiceText: rs.referenceChoiceText(m),
            ids: [].concat(built.series ?? []).map((s) => s.id ?? ''),
            onRatio: [].concat(built.series ?? []).filter((s) => s.xAxisIndex === 1).map((s) => s.id ?? s.name),
            ratioAxis: ratioAxis ? { name: ratioAxis.name, labels: ratioAxis.axisLabel?.show !== false, ticks: ratioAxis.axisTick?.show !== false,
              split: ratioAxis.splitLine?.show === true, type: ratioAxis.type, line: ratioAxis.axisLine?.show !== false, grid: ratioAxis.gridIndex } : null,
            graphics: graphicsOf(built),
            noneGraphic: noneGraphic ? { ...noneGraphic.style, expectX: pad.left + (760 - pad.left - g[0].right) / 2,
              expectY: g[1].top + g[1].height / 2 } : null,
            muted: scale.THEME.muted, fontTip: scale.THEME.fontTip,
          });
        }
      }
    }
  }
  // Under the print tokens the sentence stands alone: a printed figure cannot switch anything on.
  Object.assign(scale.THEME, PRINT_TOKENS);
  try {
    const built = rs.energyViewOption(load('res_scaling_two'), { view: 'energy', windows: 'all', shower: 'both', literature: [], deposit: false, eMax: null },
      { width: 321, height: 600 }).option;
    out.print = { graphics: graphicsOf(built), muted: scale.THEME.muted };
  } finally {
    scale.restoreScreenTheme();
  }
  // The deposit hidden with one literature curve on: that curve is the reference, and the windows take ratio marks.
  out.withCurve = [];
  for (const name of %(drawing)s) {
    for (const key of ['pi', 'e']) {
      const p = load(name);
      const o = { windows: 'all', shower: 'both', literature: [key], deposit: false, eMax: null };
      const m = rs.energyModel(p, o);
      const built = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
      out.withCurve.push({ name, key, reference: m.reference.key, none: m.ratio.none, marks: m.series.flatMap((s) => s.points).filter((pt) => pt.ratio.drawn).length,
        ids: [].concat(built.series ?? []).map((s) => s.id ?? ''), graphics: graphicsOf(built), choiceText: rs.referenceChoiceText(m) });
    }
  }
  // The dashed gate: a series whose one curve is solid to the axis end on both panels says no extrapolation rule.
  // A single-shower recording whose a/√E ⊕ b ⊕ c/E fit is taken out, so its a₀/√E is the fallback from 4 GeV, and
  // whose windows span 4–20 GeV: at E max = 20 GeV the curve is solid from end to end; at 80 GeV it is dashed above 20.
  out.gate = [];
  for (const name of ['res_scaling_single_events', 'res_scaling_single_hits', 'res_scaling_median_single_events']) {
    const p = clone(load(name));
    for (const m of ['anchors', 'all']) {
      p.series[0].fits[m].noise = null;
      p.series[0].fits[m].noise_reason = 'No a/√E ⊕ b ⊕ c/E fit: synthetic.';
      p.series[0].fits[m].span_gev = [4, 20];
    }
    for (const eMax of [null, 'undefined', 1000]) {
      const o = { windows: 'all', shower: 'both', literature: [], ...(eMax === 'undefined' ? {} : { eMax }) };
      const m = rs.energyModel(p, o);
      const built = rs.energyViewOption(p, { ...o, view: 'energy' }, RE).option;
      const s = m.series[0];
      out.gate.push({ name, eMax, drawnForm: s.drawnForm, solid: s.drawn?.solid.length ?? 0, dashed: s.drawn?.dashed.length ?? 0,
        ratioDashed: s.drawn?.ratio?.dashed?.length ?? 0, extrapolation: m.noteText.extrapolation, graphics: graphicsOf(built),
        dashIds: [].concat(built.series ?? []).map((x) => x.id ?? '').filter((id) => /\|dashed\|/.test(id)) });
    }
  }
}

/* ---- the export's legend context ------------------------------------------------------------------------ */
if (opts.part === 'export') {
  out.cases = [];
  const sig = (v) => cp.sigFigs(v, 3);
  // No recording has a window above its E-view top, so one copy lowers it as the server would for a narrower range:
  // the two-shower sample recording at 40 %%, where both showers' deposit and network windows run off scale.
  const lowered = (() => {
    const p = clone(load('res_scaling_two'));
    p.axis.energy.y = { ...p.axis.energy.y, hi: 40, interval: 10, n_clipped: 12 };
    p.axis.energy.y_model = { ...p.axis.energy.y_model, hi: 40, interval: 10, n_clipped: 8 };
    return p;
  })();
  const sources = [
    ...['res_scaling_two', 'res_scaling_median_two', 'res_scaling_robust_two', 'res_scaling_xgb', 'res_scaling_median_xgb'].map((n) => [n, load(n)]),
    ['res_scaling_two@40', lowered],
  ];
  for (const [name, p] of sources) {
    for (const windows of ['anchors', 'all']) {
      for (const literature of [[], ['pi', 'e']]) {
        for (const [deposit, eMax] of [[undefined, undefined], [false, null], [undefined, null]]) {
          const o = { view: 'energy', windows, shower: 'both', literature, deposit, eMax, palette: 'viridis', card: 'res-scaling' };
          const m = rs.energyModel(p, o);
          const A = rs.energyViewOption(p, o, RE).option;
          if (gridOf(A).length !== 2) continue;
          const plain = snap(A);
          const linA = rs.resolutionScalingOption(p, { ...o, view: 'linear' }, RW);
          const linPlain = snap(linA);
          const names = legendNames(A);
          const groups = [...names.map((n) => [n]), names.filter((n) => n.includes(' lit. — '))].filter((g) => g.length);
          for (const off of groups) {
            cp.setExportHidden(off);
            let B;
            let linB;
            try {
              B = rs.energyViewOption(p, o, RE).option;
              linB = rs.resolutionScalingOption(p, { ...o, view: 'linear' }, RW);
            } finally {
              cp.setExportHidden(null);
            }
            const keys = m.series.filter((s) => off.includes(s.label)).map((s) => s.key);
            const lits = m.literature.filter((l) => off.includes(l.legend)).map((l) => l.key);
            const offTokens = m.offScale.flatMap((g) => g.entries.filter((e) => keys.includes(e.key)).map((e) => `${e.short} ${sig(e.value)}%%`));
            // The kept end labels, spread as `endLabelPlaces` spreads them (identity coordinates).
            const font = scale.THEME.fontTip;
            const expected = (panel) => {
              const kept = m.endLabels[panel].filter((l) => !off.includes(l.name));
              const ends = panel === 'ratio' ? [m.ratio.k, 1 / m.ratio.k] : [m.y.hi, 0];
              const ys = rs.spreadLabels(kept.map((l) => l.value), 1.1 * font, Math.min(...ends) + font / 2, Math.max(...ends) - font / 2);
              return kept.map((l, i) => ({ text: l.text, y: ys[i] }));
            };
            const legendB = [].concat(B.legend ?? []);
            const linLegendB = [].concat(linB.legend ?? []);
            out.cases.push({
              name, windows, literature, deposit: deposit === undefined ? 'undefined' : deposit, eMax: eMax === undefined ? 'undefined' : eMax, off,
              keys, lits,
              legendA: names, legendB: legendNames(B), selectedB: Object.assign({}, ...legendB.map((l) => l.selected ?? {})),
              seriesB: [].concat(B.series ?? []).map((s) => ({ name: s.name ?? null, id: s.id ?? '' })),
              seriesA: [].concat(A.series ?? []).map((s) => ({ name: s.name ?? null, id: s.id ?? '' })),
              graphicsA: graphicsOf(A), graphicsB: graphicsOf(B), offTokens,
              topA: gridOf(A)[0].top, topB: gridOf(B)[0].top, rightA: gridOf(A)[0].right, rightB: gridOf(B)[0].right,
              labelsB: { main: endLabelsOf(B, false).map(({ text, y }) => ({ text, y })), ratio: endLabelsOf(B, true).map(({ text, y }) => ({ text, y })) },
              nLabelsA: endLabelsOf(A, false).length + endLabelsOf(A, true).length,
              labelsExpected: { main: expected('main'), ratio: expected('ratio') },
              linLegendB: legendNames(linB), linSelectedB: Object.assign({}, ...linLegendB.map((l) => l.selected ?? {})),
              linTopA: gridOf(linA)[0].top, linTopB: gridOf(linB)[0].top,
              restored: snap(rs.energyViewOption(p, o, RE).option) === plain,
              linRestored: snap(rs.resolutionScalingOption(p, { ...o, view: 'linear' }, RW)) === linPlain,
              exportHiddenAfter: cp.exportHidden(),
            });
          }
        }
      }
    }
  }
  // The figure's height follows the legend it keeps (energyExportMetrics lays out under the same context).
  {
    const p = load('res_scaling_two');
    const o = { view: 'energy', windows: 'all', shower: 'both', literature: ['pi', 'e'] };
    const names = legendNames(rs.energyViewOption(p, o, RE).option);
    const plainH = rs.energyExportMetrics(p, o, 760, 0.62).height;
    cp.setExportHidden(names.slice(0, 3));
    let hiddenH;
    try { hiddenH = rs.energyExportMetrics(p, o, 760, 0.62).height; } finally { cp.setExportHidden(null); }
    out.metrics = { plainH, hiddenH, after: rs.energyExportMetrics(p, o, 760, 0.62).height };
  }
}

console.log(JSON.stringify(out));
"""


def _run(part: str) -> dict:
    script = _SCRIPT % {"with_models": json.dumps(WITH_MODELS), "deposit_only": json.dumps(DEPOSIT_ONLY),
                        "drawing": json.dumps(DRAWING)}
    args = json.dumps([JS.as_uri(), str(FIXTURES), {"part": part}])
    done = subprocess.run([NODE, "--input-type=module", "-e", script, args],
                          capture_output=True, text=True, timeout=600, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def identity() -> dict:
    return _run("identity")


@pytest.fixture(scope="module")
def deposit() -> dict:
    return _run("deposit")


@pytest.fixture(scope="module")
def emax() -> dict:
    return _run("emax")


@pytest.fixture(scope="module")
def none() -> dict:
    return _run("none")


@pytest.fixture(scope="module")
def export() -> dict:
    return _run("export")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """A canvas text with its wrapping undone: the notice graphic breaks a sentence at its spaces."""
    return re.sub(r"\s+", " ", str(text)).strip()


def _range_of(axis: dict) -> dict:
    return {"hi": axis["hi"], "interval": axis["interval"], "provisional": bool(axis["provisional"]),
            "n_clipped": axis.get("n_clipped", 0)}


# ------------------------------------------------------------------------------------------------- identity --


def test_without_the_new_options_every_builder_is_todays(identity):
    """Brief 5.1 and section 1: `deposit` and `eMax` absent (or undefined), and `deposit: true`, give exactly the
    builders' output without them: both views' options (every renderItem and tooltip exercised), the dispatcher, both
    fit tables, both models and the panel-height test, on every recording, mode, shower and literature choice."""
    assert len(identity["identity"]) >= 12 * 2 * 2 * 2
    for case in identity["identity"]:
        assert all(case["equal"].values()), case


def test_without_the_new_options_the_models_say_the_server_axis_and_a_shown_deposit(identity):
    """The added model fields name today's state: the server's axis end and interval with no ticks and no E max, the
    full range with no basis, the deposit shown and not forced, and a ratio that is taken against something."""
    for case in identity["defaults"]:
        payload = _load(case["name"])
        x = case["x"]
        server = payload["axis"]["energy"]["x"]
        assert (x["max"], x["interval"], x["serverMax"]) == (server["max"], server["interval"], server["max"])
        assert x["ticks"] is None and x["eMax"] is None
        assert case["eY"]["basis"] is None and case["rY"]["basis"] is None
        assert case["eY"]["hi"] == payload["axis"]["energy"]["y"]["hi"] and case["rY"]["hi"] == payload["axis"]["y"]["hi"]
        for dep in (case["eDeposit"], case["rDeposit"]):
            assert dep == {"shown": True, "hidden": False, "forced": False}
        assert case["none"] is False and case["reference"] != "none"


# -------------------------------------------------------------------------------------------------- deposit --


def test_a_hidden_deposit_leaves_no_trace_in_either_model_legend_series_or_table(deposit):
    """Brief 5.2: one series gate. With `deposit: false` on a recording with model series, no series key starts with
    'detector:' in either model or in either view's fit table, and no legend entry or series of either view's option
    carries a deposit series' label; nor does the E view's off-scale list."""
    assert deposit["hidden"]
    for case in deposit["hidden"]:
        for key in case["rKeys"] + case["eKeys"] + case["tableKeys"] + case["offScale"]:
            assert not key.startswith("detector:"), case["name"]
        labels = set(case["depositLabels"])
        assert labels, case["name"]
        assert not labels & set(case["legends"]), case
        assert not labels & {n for n in case["seriesNames"] if n}, case
        for dep in (case["rDeposit"], case["eDeposit"]):
            assert dep == {"shown": False, "hidden": True, "forced": False}


def test_a_hidden_deposit_puts_the_model_series_range_in_force_with_its_basis(deposit):
    """Brief 5.3: while the deposit is hidden, the 1/√E view's y is the server's `axis.y_model` and the E view's
    `axis.energy.y_model`, `y.basis` their sentence; the drawn y axes end there."""
    for case in deposit["hidden"]:
        payload = _load(case["name"])
        ym = payload["axis"]["y_model"]
        eym = payload["axis"]["energy"]["y_model"]
        assert isinstance(ym, dict) and isinstance(eym, dict)
        assert _range_of(case["rY"]) == _range_of(ym) and case["rY"]["basis"] == ym["note"]
        assert _range_of(case["eY"]) == _range_of(eym) and case["eY"]["basis"] == eym["note"]
        assert case["rY"]["name"] == ym["name"] and case["eY"]["name"] == eym["name"]
        if case["linYMax"] is not None:
            assert case["linYMax"] == ym["hi"]
        if case["enYMax"] is not None:
            assert case["enYMax"] == eym["hi"]
    # The range moves where the deposit set it: on the two-shower sample recording 180 % falls to 140 %.
    two = [c for c in deposit["hidden"] if c["name"] == "res_scaling_two"]
    assert two and all(c["eY"]["hi"] == 140 for c in two)


def test_the_deposit_is_forced_on_where_it_is_the_only_series(deposit):
    """Brief 5.3, `forced`: on a deposit-only recording hiding was asked but nothing would be left, so the deposit is
    drawn, the range stays the full one with no basis, and both views draw exactly what they draw without the
    option."""
    assert len(deposit["forced"]) == len(DEPOSIT_ONLY) * 2
    for case in deposit["forced"]:
        payload = _load(case["name"])
        assert case["eKeys"] == case["rKeys"] == case["tableKeys"] == ["detector:a"]
        for dep in (case["eDeposit"], case["rDeposit"]):
            assert dep == {"shown": True, "hidden": False, "forced": True}
        assert case["eY"]["basis"] is None and case["rY"]["basis"] is None
        assert case["eY"]["hi"] == payload["axis"]["energy"]["y"]["hi"] and case["rY"]["hi"] == payload["axis"]["y"]["hi"]
        assert case["reference"] == "deposit"
        assert case["sameLinear"] and case["sameEnergy"], case


def test_the_empty_state_in_print_names_no_hidden_series_and_gives_no_instruction(deposit):
    # Review R2-4: an exported figure of the deposit-hidden empty state says what is missing, nothing more.
    for texts in deposit["emptyPrint"]:
        assert [_flat(t) for t in texts] == ["The model series have no window to draw in this selection."], texts


def test_the_empty_state_names_the_hidden_deposit_where_the_model_series_draw_nothing(deposit):
    """Brief 5.6: where the deposit is hidden and the series on show draw nothing (res_scaling_robust_xgb has no
    robust model window), both views say exactly the one sentence; it is said nowhere else."""
    seen = set()
    for case in deposit["empty"]:
        linear = [_flat(t) for t in case["linear"]]
        energy = [_flat(t) for t in case["energy"]]
        if case["hidden"] and case["modelDraws"] == 0:
            seen.add(case["name"])
            assert energy == [EMPTY_SENTENCE], case
            assert linear == [EMPTY_SENTENCE], case
            assert case["drawsPanels"] is False
        else:
            assert EMPTY_SENTENCE not in linear + energy, case
    assert "res_scaling_robust_xgb" in seen
    assert [c for c in deposit["empty"] if c["name"] == "res_scaling_robust_xgb" and c["deposit"] == "undefined"
            and c["drawsPanels"]], "with the deposit shown the robust XGBoost recording draws"
    # A shower whose only series is its deposit draws nothing once it is hidden, and says so on both views.
    only = deposit["depositOnlyShower"]
    assert all([_flat(t) for t in texts] == [EMPTY_SENTENCE] for texts in only["hidden"]), only
    assert only["shown"] is True


# ---------------------------------------------------------------------------------------------------- E max --


def test_e_max_null_ends_the_axis_on_the_datas_top_edge_with_five_gev_ticks(emax):
    """Brief 5.4: `eMax: null` is the slider's lower end, the data's top edge rounded up to 5 GeV: 20 GeV on every
    recording (data edges 18 and 20 GeV), ticked every 5 GeV, the slider's range carried as `x.eMax`."""
    cases = [c for c in emax["emax"] if c["asked"] is None]
    assert cases and {c["dataMax"] for c in cases} == {18.0, 20.0}
    for c in cases:
        assert c["x"]["max"] == 20 and c["x"]["interval"] == 5 and c["x"]["ticks"] == [0, 5, 10, 15, 20], c["name"]
        assert c["x"]["eMax"] == {"value": 20, "min": 20, "max": 80, "step": 5}
        assert c["x"]["serverMax"] == 80 and c["x"]["min"] == 0


@pytest.mark.parametrize(("asked", "end", "ticks", "interval"), [
    (20, 20, [0, 5, 10, 15, 20], 5),
    (22.4, 20, [0, 5, 10, 15, 20], 5),
    (22.5, 25, [0, 5, 10, 15, 20, 25], 5),
    (37, 35, [0, 5, 10, 15, 20, 25, 30, 35], 5),
    (45, 45, [0, 10, 20, 30, 40, 45], 10),
    (1000, 80, [0, 10, 20, 30, 40, 50, 60, 70, 80], 10),
])
def test_e_max_snaps_to_the_slider_and_ticks_both_x_axes(emax, asked, end, ticks, interval):
    """Brief 5.4: an asked value is clamped and snapped to the slider's 5 GeV grid; both x axes then run from 0 to
    it with `customValues` = `x.ticks` (the top axis's labels hidden). 1000 GeV is the server's end with its own
    10 GeV interval."""
    cases = [c for c in emax["emax"] if c["asked"] == asked]
    assert cases
    for c in cases:
        assert (c["x"]["max"], c["x"]["ticks"], c["x"]["interval"]) == (end, ticks, interval), c["name"]
        if c["axes"] is None:
            continue
        top, bottom = c["axes"]
        for axis in (top, bottom):
            assert (axis["min"], axis["max"]) == (0, end)
            assert axis["tick"] == ticks and axis["label"] == ticks
        assert not top["show"] and bottom["show"]


def test_without_e_max_the_axis_is_the_servers_with_no_custom_ticks(emax):
    """`eMax` undefined: today's axis, the server's end and interval, no custom tick values."""
    for c in (c for c in emax["emax"] if c["asked"] == "undefined"):
        assert c["x"]["max"] == c["server"]["max"] and c["x"]["interval"] == c["server"]["interval"]
        assert c["x"]["ticks"] is None and c["x"]["eMax"] is None
        if c["axes"]:
            assert all(a["tick"] is None and a["label"] is None for a in c["axes"])
            assert all(a["max"] == c["server"]["max"] for a in c["axes"])


def test_nothing_is_drawn_beyond_e_max_on_either_panel(emax):
    """Brief 5.4: no marker, whisker, curve point, literature point, ratio point, caret or end label lies beyond
    `x.max`, on either panel, at every E max: every series' data and every rendered element (E stretched so a pixel
    offset is a micro-GeV) is held to it; the end labels are anchored at `x.max` exactly."""
    drawn = [c for c in emax["emax"] if c["drawn"]]
    assert len(drawn) > 100
    assert any(c["ratioMarks"] for c in drawn) and any(c["curves"] for c in drawn)
    assert any(c["endLabels"] for c in drawn if c["asked"] is None)
    for c in drawn:
        assert c["beyond"] == [], (c["name"], c["asked"], c["windows"], c["literature"], c["beyond"][:5])
        assert all(x == c["x"]["max"] for x in c["endLabels"]), c["name"]


def test_e_max_moves_no_fit_and_no_range(emax):
    """No fit is refitted and no range recomputed: the y range, the windows on show and every drawn fit block are
    the same at the server's end and at E max = 20 GeV."""
    for c in emax["unchanged"]:
        assert c["y"][0] == c["y"][1] and c["points"][0] == c["points"][1] and c["fits"][0] == c["fits"][1], c["name"]


# -------------------------------------------------------------------------------------------- no reference --


def test_with_no_reference_on_show_no_ratio_is_taken(none):
    """Brief 5.5: the deposit hidden and no literature curve on: the reference is 'none', every shower's entry says
    'no reference is on show' and has no value, no window has a ratio mark, no curve a ratio, and the ratio block is
    `none` with nothing provisional, capped or counted below."""
    assert none["none"]
    for c in none["none"]:
        ref = c["reference"]
        assert ref["key"] == "none" and ref["label"] == "no reference" and ref["literature"] is None and ref["flag"] is None
        assert ref["choice"] == {"key": "none", "rule": "none", "basis": None, "n": 0, "scores": []}
        for shower, entry in ref["byShower"].items():
            assert entry == {"key": "none", "shower": shower, "literature": None, "interval": None, "series": None, "form": None,
                             "fit": None, "span": None, "provisional": False, "misfit": False, "label": "no reference",
                             "why": None, "reason": "no reference is on show", "valueAt": [None] * 5}
        r = c["ratio"]
        assert r["none"] is True and r["provisional"] is False and r["capped"] == 0 and r["belowNotDrawn"] == 0
        assert r["below"] == [] and r["noReference"] == [] and r["reference"] == "none"
        assert sum(r["clipped"].values()) == 0
        assert c["pointRatios"] and all(p == {"drawn": False, "reason": "no reference is on show"} for p in c["pointRatios"])
        assert all(x is None for x in c["curveRatios"]) and c["ratioEndLabels"] == 0
        assert c["choiceText"] is None


def test_with_no_reference_the_ratio_panel_keeps_its_frame_and_says_so(none):
    """Brief 5.5: the ratio grid keeps its frame and the E axis under it; its y axis draws no tick, label, split line
    or name; no 'ratio|unity' series and nothing at all on the ratio panel; one centred sentence in it, muted, at
    the tooltip size, with the screen's hint."""
    for c in none["none"]:
        assert c["drawn"], c["name"]
        assert "ratio|unity" not in c["ids"] and c["onRatio"] == []
        axis = c["ratioAxis"]
        assert axis["name"] == "" and not axis["labels"] and not axis["ticks"] and not axis["split"]
        assert axis["line"] and axis["grid"] == 1 and axis["type"] == "log"
        texts = [t for t in c["graphics"] if t.startswith("No ratio drawn")]
        assert texts == [NONE_TEXT + NONE_SCREEN]
        g = c["noneGraphic"]
        assert g["fill"] == c["muted"] and g["fontSize"] == c["fontTip"]
        assert g["textAlign"] == "center" and g["textVerticalAlign"] == "middle"
        assert g["x"] == pytest.approx(g["expectX"]) and g["y"] == pytest.approx(g["expectY"])


def test_the_printed_no_reference_sentence_has_no_screen_hint(none):
    """Brief 5.5: the hint ' Switch on π±, e± or the deposit to draw one.' is the screen's alone."""
    texts = [t for t in none["print"]["graphics"] if t.startswith("No ratio drawn")]
    assert texts == [NONE_TEXT]


def test_a_literature_curve_with_the_deposit_hidden_is_the_reference(none):
    """With the deposit hidden and one literature curve on, that curve is the reference: ratio marks are drawn, the
    1.0 rule is back and no 'No ratio drawn' sentence is shown."""
    for c in none["withCurve"]:
        assert c["reference"] == c["key"] and c["none"] is False and c["marks"] > 0, c
        assert "ratio|unity" in c["ids"]
        assert not [t for t in c["graphics"] if t.startswith("No ratio drawn")]


def test_the_extrapolation_rule_is_said_only_while_a_dashed_run_is_drawn(none):
    """Brief 5.7: a curve fitted to 4–20 GeV is solid to the end at E max = 20 GeV, so no extrapolation rule is on
    the canvas; at the server's end (or 1000 GeV, snapped to it) its run above 20 GeV is dashed and the rule is
    back."""
    assert len(none["gate"]) == 9
    for c in none["gate"]:
        assert c["drawnForm"] == "pinned" and c["solid"] > 0, c
        if c["eMax"] is None:
            assert c["dashed"] == 0 and c["ratioDashed"] == 0 and c["dashIds"] == []
            assert c["extrapolation"] == ""
            assert not [t for t in c["graphics"] if t.startswith("dashed:")]
        else:
            assert c["dashed"] > 0 and c["dashIds"]
            assert c["extrapolation"] == "dashed: fit extrapolated beyond its fitted windows (4–20 GeV)"
            assert [t for t in c["graphics"] if "dashed: fit extrapolated" in _flat(t)]


# --------------------------------------------------------------------------------------------------- export --


def _companion(name: str, entry: str) -> bool:
    return name == entry or name.startswith(f"{entry} ") or name.startswith(f"{entry}·")


def test_an_export_leaves_out_every_mark_of_a_left_out_legend_entry(export):
    """Brief 5.7: under `setExportHidden([N])` the E view's legend lists no N and marks it false; no series of the
    option is N or a companion of N (its markers, whiskers, carets, curves and end labels on both panels all carry
    its name); a left-out literature curve's line, carets and ratio line are gone; no canvas text names N or one of
    its off-scale values; the legend and note band never grow, the end column never widens."""
    cases = export["cases"]
    assert len(cases) > 40
    assert any(c["offTokens"] for c in cases), "some left-out series had off-scale values"
    assert any(any(t in " ".join(_flat(g) for g in c["graphicsA"]) for t in c["offTokens"]) for c in cases), \
        "some left-out off-scale value was on the screen's canvas"
    assert any(c["lits"] for c in cases), "some literature curve was left out"
    for c in cases:
        off = c["off"]
        assert not set(off) & set(c["legendB"]), c["off"]
        assert all(c["selectedB"].get(n) is False for n in off)
        assert set(c["legendB"]) == set(c["legendA"]) - set(off)
        for s in c["seriesB"]:
            assert not any(_companion(s["name"] or "", n) for n in off), (s, off)
        for key in c["lits"]:
            assert any(s["id"].startswith(f"literature|{key}") for s in c["seriesA"])
            assert not any(s["id"].startswith(f"literature|{key}") for s in c["seriesB"]), key
        for key in c["keys"]:
            assert any(s["id"].startswith(f"{key}|") for s in c["seriesA"])
            assert not any(s["id"].startswith(f"{key}|") for s in c["seriesB"]), key
        text = " ".join(_flat(t) for t in c["graphicsB"])
        assert not any(n in text for n in off)
        for token in c["offTokens"]:
            assert token not in text, (token, off)
        assert c["topB"] <= c["topA"] and c["rightB"] <= c["rightA"]


def test_an_export_spreads_the_end_labels_it_keeps_without_the_left_out_ones(export):
    """Brief 5.7: the end labels of a left-out entry are gone, and the kept ones are placed as `spreadLabels` places
    them without it; hiding both literature curves narrows the end column, whose widest labels they were."""
    for c in export["cases"]:
        for panel in ("main", "ratio"):
            got = sorted((x["text"], round(x["y"], 9)) for x in c["labelsB"][panel])
            want = sorted((x["text"], round(x["y"], 9)) for x in c["labelsExpected"][panel])
            assert got == want, (c["name"], c["off"], panel)
    assert any(c["nLabelsA"] > len(c["labelsB"]["main"]) + len(c["labelsB"]["ratio"]) for c in export["cases"])
    both = [c for c in export["cases"] if len(c["lits"]) == 2]
    assert both
    assert any(c["rightB"] < c["rightA"] for c in both)


def test_an_export_keeps_the_literature_warning_while_a_curve_is_on(export):
    """Brief 5.7: under the median estimator the literature disclosure stays on the canvas while a literature curve
    is on, its legend entry left out or not: the ratio may still divide by it."""
    warning = _load("res_scaling_median_two")["estimator"]["literature"]["warning"]
    cases = [c for c in export["cases"] if c["name"] in {"res_scaling_median_two", "res_scaling_median_xgb"} and c["literature"]]
    assert cases and any(c["lits"] for c in cases)
    for c in cases:
        assert warning in " ".join(_flat(t) for t in c["graphicsA"])
        assert warning in " ".join(_flat(t) for t in c["graphicsB"]), c["off"]


def test_the_extrapolation_rule_counts_the_series_an_export_keeps(export):
    """Brief 5.7: the rule names the dashed runs of the series still drawn: leaving out a series never adds a rule,
    and a figure that keeps no fitted curve says none."""
    for c in export["cases"]:
        a = [t for t in c["graphicsA"] if _flat(t).startswith("dashed:") or "dashed:" in _flat(t)]
        b = [t for t in c["graphicsB"] if _flat(t).startswith("dashed:") or "dashed:" in _flat(t)]
        if not a:
            assert not b, c["off"]


def test_the_one_over_root_e_view_export_takes_the_shared_legend(export):
    """Brief 5.7: the 1/√E view needs nothing beyond `chartLegend` and `legendTop`: the left-out entry is not listed,
    is marked false, and never adds a legend row."""
    for c in export["cases"]:
        for n in c["off"]:
            if n in c["legendA"] and " lit. — " not in n:
                assert n not in c["linLegendB"] and c["linSelectedB"].get(n) is False
        assert c["linTopB"] <= c["linTopA"]


def test_after_the_export_the_options_are_the_screens_again(export):
    """`setExportHidden(null)` restores the screen: both views deep-equal the option built before the export, and
    the context is null."""
    for c in export["cases"]:
        assert c["restored"] and c["linRestored"], (c["name"], c["off"])
        assert c["exportHiddenAfter"] is None
    m = export["metrics"]
    assert m["hiddenH"] <= m["plainH"] and m["after"] == m["plainH"]
