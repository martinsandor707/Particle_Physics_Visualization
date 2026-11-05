/* The distilled energy response p̂(E_sum) of the training report's PySR formulas (`distill-curves`).
 *
 * The payload is `catalog/select.js` `catalogPayload('distill-curves', { species })`: the energy formulas
 * in physical units that PySR gave (whatever task the bench bar shows), each with its tier, its R²_PySR
 * and the network's R² to truth, the secondary variables they read (centroid_r, max_hit_frac,
 * centroid_theta, rms_r) with a stated domain and a default at its midpoint, and the 20 GeV ceiling rule.
 * The curves are evaluated here by `catalog/formula.js`, a small parser of the formulas' explicit form:
 * never `eval`, never `Function`. Nothing is requested; a slider repaints.
 *
 * ## One facet per frame, species by end mark and label
 *
 * Three small multiples (Absolute, Per-shower translated, Local) side by side, stacked below 640 px, each
 * in its frame's hue (perf_bins.js `sourceColours`). A species is never a second hue: each curve ends in
 * its species' mark (Proton ●, Muon ■, Electron ▲, Pion ◆) with a direct label, so no legend is needed
 * to name it.
 *
 * ## The tier is the stroke
 *
 * A curve of the "Physical law" tier is a solid 2 px line. Below it the curve is dashed and faded (its
 * opacity never below 3:1 against the card, `legibleOpacity`) and thinner: dashed for a partial surrogate,
 * finely dashed for "not a law"; its end label names the tier and its tooltip and the drawer give the
 * reason. The muon curves are labelled as describing the network, whose R² to truth is far below the law
 * threshold (`weakTruth`).
 *
 * ## Axes from zero, and what leaves them
 *
 * x is E_sum [GeV] from 0 to the E_sum at which the Absolute formula of a shown species reaches 20 GeV at
 * the values in force (`curveDomain`, the largest over the species), exactly: that curve ends in the
 * plot's top-right corner, and the ticks are round steps that need not land on the end; y is p̂
 * [GeV] from 0 to the 20 GeV ceiling, the 0–20 GeV range of the datasets. A curve that leaves the range
 * (above 20 GeV, or below 0, where a negative coefficient wins) is clipped at the axis: a caret where it
 * leaves, its true values in the caret's tooltip, and a count in the drawer.
 *
 * ## The secondary variables
 *
 * The card's own slider row (after its `.plot-frame`, screen only) sets every secondary variable a drawn
 * curve reads, within its stated domain; each value in force is printed under the plot, in the key on the
 * canvas (so an export carries it) and in the drawer. The report gives no feature distributions, so a
 * curve is conditional at the stated values, not a marginal prediction, and every tooltip says so. The
 * values live on the instance (`values`, `notesState()`) and reach the builder through `opts.values`, so
 * an export draws what the screen shows.
 */

import { THEME, axisPadding, formatNumber, typographic } from '../scale.js';
import { compileFormula } from '../catalog/formula.js';
import { curveDomain } from '../catalog/select.js';
import { LEAK_TEXT, r2Text } from '../catalog/gating.js';
import { measureText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, FINE_STEPS, baseOption, caretSeries, emptyChartOption, escapeHtml, legibleOpacity, mutedLine,
  niceCeil, niceInterval, valueAxis, wrapTooltip,
} from './chart_panel.js';
import { CATALOG_FRAMES, catalogTipFoot, frameColours } from './distill_triangle.js';

/** The end mark of each species (zrender shapes drawn by the builder), never a hue. */
export const SPECIES_MARK = Object.freeze({ proton: 'circle', muon: 'square', electron: 'triangle', pion: 'diamond' });
/** The same marks as text, for the key and the drawer. */
export const SPECIES_GLYPH = Object.freeze({ proton: '●', muon: '■', electron: '▲', pion: '◆' });

/** The stroke of each tier: law solid; below it dashed, thinner and faded. */
export const TIER_STROKE = Object.freeze({
  law: Object.freeze({ dash: null, width: 2, alpha: 1, words: 'solid' }),
  unverified: Object.freeze({ dash: null, width: 2, alpha: 1, words: 'solid' }),
  partial: Object.freeze({ dash: [6, 3], width: 1.5, alpha: 0.55, words: 'dashed, faded' }),
  'not-law': Object.freeze({ dash: [3, 3], width: 1.25, alpha: 0.4, words: 'finely dashed, faded' }),
});

/** The short tier words an end label adds below the law. */
const TIER_SHORT = Object.freeze({ unverified: 'unverified', partial: 'partial', 'not-law': 'not a law' });

/** Samples along E_sum per curve. */
export const CURVE_SAMPLES = 240;

/** The facet layout switches to a stack below this width (px). */
export const STACK_BELOW_PX = 640;

const num = (v, d = 3) => formatNumber(v, d);

/** A value with its unit, for the values in force. */
export function valueText(spec, v) {
  const digits = spec.unit === 'mm' ? 0 : 2;
  return `${num(v, digits)}${spec.unit ? ` ${spec.unit}` : ''}`;
}

/** The values in force: the payload's defaults, overridden by `values`, each clamped to its domain. */
export function curvesValues(payload, values = null) {
  const out = {};
  for (const [key, spec] of Object.entries(payload?.variables ?? {})) {
    const [lo, hi] = spec.domain ?? [-Infinity, Infinity];
    const wanted = Number(values?.[key]);
    const v = Number.isFinite(wanted) ? wanted : spec.default;
    out[key] = Math.min(hi, Math.max(lo, v));
  }
  return out;
}

/** The variables a drawn curve reads: { key: spec } in the payload's order. */
export function usedVariables(payload) {
  return Object.fromEntries(Object.entries(payload?.variables ?? {}).filter(([, spec]) => (spec.usedBy ?? []).length));
}

/** "centroid_r = 2,500 mm, max_hit_frac = 0.5" for the variables a curve (or the card) reads. */
export function valuesSentence(payload, values, keys = null) {
  const used = usedVariables(payload);
  const list = (keys ?? Object.keys(used)).filter((k) => used[k]);
  return list.map((k) => `${used[k].label ?? k} = ${valueText(used[k], values[k])}`).join(', ');
}

/** The class of one value against the range [0, yTop]. */
function classOf(y, yTop) {
  if (!Number.isFinite(y)) return 'nan';
  // A formula that reaches the ceiling exactly at the axis end (the rule that sets x) stays inside.
  if (y > yTop * (1 + 1e-9)) return 'above';
  return y < 0 ? 'below' : 'in';
}

/** The boundary between x `a` (class `ca`) and x `b` of another class, by bisection on the formula. */
function crossing(fn, a, b, yTop) {
  const ca = classOf(fn(a), yTop);
  let lo = a;
  let hi = b;
  for (let i = 0; i < 60; i += 1) {
    const m = 0.5 * (lo + hi);
    if (classOf(fn(m), yTop) === ca) lo = m; else hi = m;
  }
  return 0.5 * (lo + hi);
}

/**
 * One curve sampled over [0, xTop] and clipped to [0, yTop]: { segments: [[[x, y], …]], runs: [{ dir:
 * 'above' | 'below' | 'nan', from, to, extreme, at, entry: [x, y] }] }, a run being one stretch outside
 * the range (or undefined), `entry` the point on the axis where it starts. A segment ends exactly on
 * the axis where its curve leaves it (the crossing is bisected on the formula, not interpolated).
 */
export function sampleCurve(fn, xTop, yTop, samples = CURVE_SAMPLES) {
  const xs = Array.from({ length: samples + 1 }, (_, i) => (xTop * i) / samples);
  const ys = xs.map((x) => fn(x));
  const cls = ys.map((y) => classOf(y, yTop));
  const bound = (c) => (c === 'above' ? yTop : 0);
  const segments = [];
  const runs = [];
  let current = [];
  let run = null;
  const closeRun = (to) => { if (run) { run.to = to; runs.push(run); run = null; } };
  const closeSegment = () => { if (current.length > 1) segments.push(current); current = []; };
  for (let i = 0; i < xs.length; i += 1) {
    const c = cls[i];
    const prev = i > 0 ? cls[i - 1] : null;
    if (c === 'in') {
      if (prev && prev !== 'in') {
        if (prev === 'nan') {
          closeRun(xs[i]);
        } else {
          const x = crossing(fn, xs[i], xs[i - 1], yTop);
          closeRun(x);
          current.push([x, bound(prev)]);
        }
      }
      current.push([xs[i], ys[i]]);
      continue;
    }
    if (run && run.dir === c) {
      run.to = xs[i];
      if ((c === 'above' && ys[i] > run.extreme) || (c === 'below' && ys[i] < run.extreme)) {
        run.extreme = ys[i];
        run.at = xs[i];
      }
      continue;
    }
    let start = xs[i];
    if (prev === 'in' && c !== 'nan') {
      start = crossing(fn, xs[i - 1], xs[i], yTop);
      current.push([start, bound(c)]);
    } else if (run) {
      start = xs[i];
    }
    closeRun(start);
    closeSegment();
    run = { dir: c, from: start, to: xs[i], extreme: ys[i], at: xs[i], entry: [start, c === 'nan' ? 0 : bound(c)] };
  }
  closeRun(xs[xs.length - 1]);
  closeSegment();
  return { segments, runs };
}

/** The curve's formula as a reader reads it: p̂ = 29.5·E_sum + 0.0024·centroid_r. */
export function formulaText(ascii) {
  const src = String(ascii ?? '');
  let out = '';
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i];
    if (ch === ' ') continue;
    if (ch === '*') { out += '·'; continue; }
    if (ch === '+') { out += ' + '; continue; }
    // A binary minus gets spaces; the sign of an exponent (6.713e-7) and a leading sign do not.
    const before = src.slice(0, i).replace(/\s+$/, '');
    const exponent = /\d[eE]$/.test(before);
    if (ch === '-' && before && /[\w)]$/.test(before) && !exponent) { out += ' - '; continue; }
    out += ch;
  }
  return `p̂ = ${typographic(out.replace(/\^2\b/g, '²').replace(/ - /g, ' − '))}`;
}

/**
 * Everything the chart and the drawer need, decided once. Pure: { values, used, domain, xTop, yTop,
 * facets: [{ frame, label, colour, curves, excluded }], curves (all), clipped (curves leaving the range),
 * carets (count), weakTruth, note, ceiling, compare }.
 */
export function curvesModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.formulas)) return null;
  const values = curvesValues(payload, opts.values ?? null);
  const domain = curveDomain(payload.formulas, values);
  // x runs exactly to the rule's E_sum: the formula that sets it ends on the ceiling, at the corner.
  const xTop = domain.xMax;
  const xTick = niceInterval(niceCeil(xTop, FINE_STEPS));
  const yTop = payload.ceiling?.value ?? 20;
  const colours = frameColours();
  const speciesLabels = payload.speciesLabels ?? {};
  const frameLabels = payload.frameLabels ?? {};
  const all = [];
  const facets = CATALOG_FRAMES.map((frame) => {
    const colour = colours[frame] ?? THEME.text;
    const curves = payload.formulas.filter((f) => f.frame === frame).map((f) => {
      const stroke = TIER_STROKE[f.tier?.tier] ?? TIER_STROKE['not-law'];
      let fn = null;
      let error = null;
      try {
        const compiled = compileFormula(f.ascii);
        fn = (x) => {
          try { return compiled({ ...values, E_sum: x }); } catch { return NaN; }
        };
      } catch (e) {
        error = e?.message ?? String(e);
      }
      const sampled = fn ? sampleCurve(fn, xTop, yTop) : { segments: [], runs: [] };
      const last = sampled.segments[sampled.segments.length - 1];
      const curve = {
        key: `${f.species}:${frame}`,
        species: f.species,
        speciesLabel: speciesLabels[f.species] ?? f.species,
        frame,
        frameLabel: frameLabels[frame] ?? frame,
        colour,
        tier: f.tier?.tier ?? 'not-law',
        tierLabel: f.tier?.label ?? f.tier?.tier ?? '',
        reasons: [...(f.tier?.reasons ?? [])],
        r2Text: r2Text(f.r2),
        netR2Text: f.netR2 ? r2Text(f.netR2) : 'not reported',
        ascii: f.ascii,
        formulaText: formulaText(f.ascii),
        variables: [...(f.variables ?? [])],
        stroke,
        opacity: legibleOpacity(colour, stroke.alpha),
        segments: sampled.segments,
        runs: sampled.runs.filter((r) => r.dir !== 'nan'),
        undefinedRuns: sampled.runs.filter((r) => r.dir === 'nan'),
        end: last ? last[last.length - 1] : null,
        weakTruth: payload.weakTruth?.[f.species]?.text ?? null,
        error,
        at: valuesSentence(payload, values, f.variables ?? []),
      };
      curve.clipped = curve.runs.length > 0;
      all.push(curve);
      return curve;
    });
    const excluded = (payload.absentOrExcluded ?? []).filter((x) => x.frame === frame);
    return { frame, label: frameLabels[frame] ?? frame, colour, curves, excluded };
  });
  return {
    values,
    used: usedVariables(payload),
    domain,
    xTop,
    xTick,
    yTop,
    facets,
    curves: all,
    clipped: all.filter((c) => c.clipped),
    carets: all.reduce((n, c) => n + c.runs.length, 0),
    weakTruth: payload.weakTruth ?? {},
    note: payload.note ?? '',
    ceiling: payload.ceiling ?? { value: yTop, unit: 'GeV', rule: '' },
    compare: (payload.species ?? []).length > 1,
    species: [...(payload.species ?? [])],
    speciesLabels,
    tiers: [...new Set(all.map((c) => c.tier))],
    valuesText: valuesSentence(payload, values),
  };
}

/* --------------------------------------------------------------- layout -- */

/** The key's items: one line sample per tier drawn, one end mark per species, the values in force. */
function keyItems(model) {
  const items = [];
  for (const tier of ['law', 'unverified', 'partial', 'not-law']) {
    if (!model.tiers.includes(tier)) continue;
    const label = { law: 'Physical law', unverified: 'High fidelity, truth R² not reported', partial: 'Partial surrogate', 'not-law': 'Not a law' }[tier];
    items.push({ kind: 'line', tier, text: label });
  }
  for (const s of model.species) items.push({ kind: 'mark', species: s, text: model.speciesLabels[s] ?? s });
  if (model.valuesText) items.push({ kind: 'text', text: `at ${model.valuesText}` });
  return items;
}

/** Flow the key's items into rows of `width` px: [{ item, x, row }] and the row count. */
function flowKey(items, width) {
  const f = THEME.fontLabel;
  const placed = [];
  let x = 0;
  let row = 0;
  for (const item of items) {
    const sample = item.kind === 'line' ? 22 : item.kind === 'mark' ? 12 : 0;
    const w = sample + measureText(item.text, f, THEME.fontFamily) + 1.4 * f;
    if (x > 0 && x + w > width) { row += 1; x = 0; }
    placed.push({ item, x, row, sample });
    x += w;
  }
  return { placed, rows: placed.length ? row + 1 : 0 };
}

/**
 * Where everything sits at `width` px: { stacked, key, facets: [{ left, top, width, height }], height }.
 * Side by side from 640 px, each facet's plot square-ish; stacked below.
 */
export function curvesLayout(model, width = 1100) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const w = Math.max(240, width || 1100);
  const stacked = w < STACK_BELOW_PX;
  const keyWidth = Math.max(120, w - pad.left - pad.right);
  const key = flowKey(keyItems(model), keyWidth);
  const keyTop = 0.4 * f;
  const titleH = 1.8 * f;
  const top = keyTop + key.rows * 1.7 * f + 0.6 * f + titleH;
  const n = model.facets.length;
  const facets = [];
  // A gutter at each facet's right for the labels of the curves that end on its right edge.
  const labelWidths = model.curves.map((c) => measureText(endLabelText(c), THEME.fontSmall, THEME.fontFamily));
  const gutter = labelWidths.length ? Math.ceil(Math.max(...labelWidths) + 1.2 * f) : 0;
  if (!stacked) {
    const gap = 2.2 * f;
    const plotW = Math.max(80, (w - pad.left - pad.right - n * gutter - (n - 1) * gap) / n);
    const plotH = Math.round(Math.min(Math.max(150, plotW * 0.85), 300));
    for (let i = 0; i < n; i += 1) facets.push({ left: pad.left + i * (plotW + gutter + gap), top, width: plotW, height: plotH, gutter });
    return { stacked, key, keyTop, keyLeft: pad.left, titleH, gutter, facets, height: Math.round(top + plotH + pad.bottom) };
  }
  const plotW = Math.max(80, w - pad.left - pad.right - gutter);
  const plotH = Math.round(Math.min(Math.max(140, plotW * 0.6), 260));
  const step = plotH + pad.bottom + titleH + 0.4 * f;
  for (let i = 0; i < n; i += 1) facets.push({ left: pad.left, top: top + i * step, width: plotW, height: plotH, gutter });
  return { stacked, key, keyTop, keyLeft: pad.left, titleH, gutter, facets, height: Math.round(top + (n - 1) * step + plotH + pad.bottom) };
}

/** The plot height the panel sets before ECharts measures. */
export function plotHeight(payload, opts = {}, width = 1100) {
  const model = curvesModel(payload, opts);
  if (!model) return 340;
  return curvesLayout(model, width).height;
}

/* -------------------------------------------------------------- tooltips -- */

/** The tooltip of one curve. */
export function curveTip(model, c) {
  const lines = [`<b>${escapeHtml(c.speciesLabel)} · ${escapeHtml(c.frameLabel)}: ${escapeHtml(c.formulaText)}</b>`];
  lines.push(`${escapeHtml(c.tierLabel)}${c.tier === 'law' ? '' : ` — ${escapeHtml(c.reasons.join(' '))}`}`);
  lines.push(`R²_PySR to the network ${escapeHtml(c.r2Text)}; the network's R² to truth ${escapeHtml(c.netR2Text)}`);
  if (c.weakTruth) lines.push(mutedLine(`${c.speciesLabel} curves ${c.weakTruth}.`));
  lines.push(mutedLine(c.at ? `At ${c.at}: conditional at these values, not a marginal prediction.` : 'Depends on E_sum alone.'));
  if (c.clipped) lines.push(mutedLine(`Leaves the 0–${num(model.yTop)} GeV range ${c.runs.length === 1 ? 'once' : `${c.runs.length} times`}: clipped at the axis (carets).`));
  if (c.undefinedRuns.length) lines.push(mutedLine('Undefined (a root or logarithm of a negative) over part of the range: not drawn there.'));
  lines.push(mutedLine(LEAK_TEXT['oracle-separation']));
  lines.push(catalogTipFoot());
  return lines.join('<br/>');
}

/** The tooltip of one caret: where the curve leaves the range, and its true values there. */
export function caretTip(model, c, run) {
  const where = run.dir === 'above' ? `above ${num(model.yTop)} GeV (the axis top)` : 'below 0 GeV';
  const lines = [`<b>${escapeHtml(c.speciesLabel)} · ${escapeHtml(c.frameLabel)}: p̂ ${where}</b>`];
  lines.push(`for E_sum from ${num(run.from)} to ${num(run.to)} GeV; it reaches ${num(run.extreme)} GeV at E_sum = ${num(run.at)} GeV`);
  lines.push(mutedLine('Clipped at the axis; these are the formula\'s own values.'));
  if (c.at) lines.push(mutedLine(`At ${c.at}.`));
  lines.push(catalogTipFoot());
  return lines.join('<br/>');
}

/* ---------------------------------------------------------------- marks -- */

/** A species' end mark at pixel (x, y): filled for the law, hollow below it. */
function endMark(species, x, y, colour, filled) {
  const r = 4;
  const style = filled
    ? { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis }
    : { fill: THEME.card, stroke: colour, lineWidth: 1.5 * THEME.lineAxis };
  const shape = SPECIES_MARK[species] ?? 'circle';
  if (shape === 'square') return { type: 'rect', shape: { x: x - r, y: y - r, width: 2 * r, height: 2 * r }, style };
  if (shape === 'triangle') return { type: 'polygon', shape: { points: [[x, y - 1.25 * r], [x + 1.15 * r, y + 0.85 * r], [x - 1.15 * r, y + 0.85 * r]] }, style };
  if (shape === 'diamond') return { type: 'polygon', shape: { points: [[x, y - 1.3 * r], [x + 1.3 * r, y], [x, y + 1.3 * r], [x - 1.3 * r, y]] }, style };
  return { type: 'circle', shape: { cx: x, cy: y, r }, style };
}

/** The direct label of a curve: its species, and its tier below the law. */
export function endLabelText(c) {
  return `${c.speciesLabel}${c.tier === 'law' ? '' : ` (${TIER_SHORT[c.tier] ?? c.tier})`}`;
}

/** Spread labels (sorted by y) at least `gap` apart inside [lo, hi], in place. */
function spread(labels, gap, lo, hi) {
  labels.sort((a, b) => a.ly - b.ly);
  for (let i = 1; i < labels.length; i += 1) {
    if (labels[i].ly - labels[i - 1].ly < gap) labels[i].ly = labels[i - 1].ly + gap;
  }
  for (let i = labels.length - 1; i >= 0; i -= 1) {
    const limit = i === labels.length - 1 ? hi : labels[i + 1].ly - gap;
    if (labels[i].ly > limit) labels[i].ly = limit;
  }
  for (const l of labels) l.ly = Math.max(lo, l.ly);
}

/**
 * The end labels of one facet in pixel space. A curve that ends on the right edge is labelled in the
 * facet's gutter, level with its end; one that leaves earlier (through the top or the bottom) is
 * labelled beside its last point inside the plot. Each group is spread so no label overprints another.
 */
function endLabels(model, facet, g) {
  const f = THEME.fontSmall;
  const px = (p) => [g.left + (p[0] / model.xTop) * g.width, g.top + (1 - p[1] / model.yTop) * g.height];
  const right = g.left + g.width;
  const gutter = [];
  const inner = [];
  for (const c of facet.curves.filter((x) => x.end)) {
    const [x, y] = px(c.end);
    const text = endLabelText(c);
    if (x >= right - 0.5 && g.gutter > 0) {
      gutter.push({ text, align: 'left', lx: right + 7, ly: y });
    } else {
      const width = measureText(text, f, THEME.fontFamily);
      const fits = x + 8 + width <= right;
      inner.push({ text, align: fits ? 'left' : 'right', lx: fits ? x + 7 : x - 7, ly: y + (y <= g.top + 1 ? f : 0) });
    }
  }
  spread(gutter, f + 2, g.top, g.top + g.height);
  spread(inner, f + 2, g.top + f / 2, g.top + g.height - f / 2);
  return [...gutter, ...inner].map((l) => ({
    type: 'text', silent: true,
    style: {
      x: l.lx, y: l.ly, text: l.text, textAlign: l.align, textVerticalAlign: 'middle',
      fill: THEME.text, fontSize: f, fontFamily: THEME.fontFamily,
    },
  }));
}

/** The key on the canvas: tier line samples, species end marks, the values in force. */
function keyGraphic(model, layout) {
  const f = THEME.fontLabel;
  const out = [];
  for (const { item, x, row, sample } of layout.key.placed) {
    const x0 = layout.keyLeft + x;
    const y = layout.keyTop + (row + 0.5) * 1.7 * f;
    if (item.kind === 'line') {
      const s = TIER_STROKE[item.tier];
      out.push({
        type: 'line', silent: true, shape: { x1: x0, y1: y, x2: x0 + 18, y2: y },
        style: { stroke: THEME.text, lineWidth: s.width, lineDash: s.dash, opacity: legibleOpacity(THEME.text, s.alpha) },
      });
    } else if (item.kind === 'mark') {
      out.push({ ...endMark(item.species, x0 + 5, y, THEME.text, true), silent: true });
    }
    out.push({
      type: 'text', silent: true,
      style: {
        x: x0 + sample + (sample ? 4 : 0), y, text: item.text, textVerticalAlign: 'middle',
        fill: item.kind === 'text' ? THEME.muted : THEME.text, fontSize: f, fontFamily: THEME.fontFamily,
      },
    });
  }
  return out;
}

/**
 * The option. Pure: `opts` = { species, values?, tooltipPosition? }; `metrics` = { width, height }.
 * Returns { option, plotGrid }.
 */
export function distillCurvesOption(payload, opts = {}, metrics = {}) {
  const model = curvesModel(payload, opts);
  if (!model || !model.curves.length) {
    return { option: emptyChartOption(opts, metrics, 'The training report gives no energy formula in physical units for this choice.') };
  }
  const layout = curvesLayout(model, metrics.width || 1100);
  const f = THEME.fontLabel;
  const grid = layout.facets.map((g) => ({ left: g.left, top: g.top, width: g.width, height: g.height }));
  const xAxis = [];
  const yAxis = [];
  const series = [];
  const graphic = keyGraphic(model, layout);
  model.facets.forEach((facet, k) => {
    const g = layout.facets[k];
    xAxis.push(valueAxis({
      gridIndex: k, name: 'E_sum [GeV]', min: 0, max: model.xTop, interval: model.xTick, split: true,
      nameGap: 2.4 * f, showMaxLabel: false,
    }));
    yAxis.push(valueAxis({
      gridIndex: k, name: k === 0 || layout.stacked ? 'p̂ [GeV]' : '', min: 0, max: model.yTop,
      interval: niceInterval(model.yTop), split: true, nameGap: 2.6 * f,
    }));
    // The facet's title, with a short stroke of its hue: the frame names the facet, the hue repeats it.
    const ty = g.top - 0.9 * f;
    graphic.push({ type: 'line', silent: true, shape: { x1: g.left, y1: ty, x2: g.left + 14, y2: ty }, style: { stroke: facet.colour, lineWidth: 3 } });
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: g.left + 19, y: ty, text: facet.label, textVerticalAlign: 'middle', fill: THEME.text,
        fontSize: THEME.fontName, fontFamily: THEME.fontFamily, fontWeight: 600,
      },
    });
    for (const c of facet.curves) {
      if (c.segments.length) series.push({
        type: 'custom',
        name: `${c.speciesLabel} · ${c.frameLabel}`,
        xAxisIndex: k,
        yAxisIndex: k,
        clip: true,
        z: c.tier === 'law' ? 5 : 4,
        data: [c.segments[0][0]],
        itemStyle: { color: c.colour },
        renderItem: (params, api) => {
          const children = c.segments.map((seg) => ({
            type: 'polyline',
            shape: { points: seg.map((p) => api.coord(p)) },
            style: { fill: 'none', stroke: c.colour, lineWidth: c.stroke.width, lineDash: c.stroke.dash, opacity: c.opacity },
          }));
          const e = api.coord(c.end);
          children.push(endMark(c.species, e[0], e[1], c.colour, c.tier === 'law' || c.tier === 'unverified'));
          return { type: 'group', children };
        },
        tooltip: { formatter: () => curveTip(model, c) },
      });
      // A clipped stretch keeps its caret even where nothing of the curve is left inside the range.
      if (c.runs.length) {
        series.push(caretSeries({
          name: `${c.speciesLabel} · ${c.frameLabel} (clipped)`,
          carets: c.runs.map((run) => ({
            // Where the curve leaves the range; a stretch that starts at E_sum = 0 is marked where it comes back.
            at: [Math.min(model.xTop, Math.max(0, run.from > 0 || run.to >= model.xTop ? run.from : run.to)), run.dir === 'above' ? model.yTop : 0],
            dir: run.dir === 'above' ? 'up' : 'down',
            tooltip: caretTip(model, c, run),
          })),
          color: c.colour,
        }));
        series[series.length - 1].xAxisIndex = k;
        series[series.length - 1].yAxisIndex = k;
      }
    }
    graphic.push(...endLabels(model, facet, g));
    if (!facet.curves.length) {
      const why = facet.excluded.map((x) => `${model.speciesLabels[x.species] ?? x.species}: ${x.reason}`).join(' ');
      graphic.push({
        type: 'text', silent: true,
        style: {
          x: g.left + g.width / 2, y: g.top + g.height / 2, text: why || 'No formula drawn in this frame.',
          textAlign: 'center', textVerticalAlign: 'middle', fill: THEME.muted, fontSize: THEME.fontSmall,
          fontFamily: THEME.fontFamily, width: g.width - 8, overflow: 'break',
        },
      });
    }
  });
  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      grid,
      xAxis,
      yAxis,
      graphic,
      series,
    },
    plotGrid: grid,
  };
}

/* ---------------------------------------------------------------- class -- */

export class DistillCurvesPanel extends ChartPanel {
  constructor(elementOrId, { card = null, aspect } = {}) {
    super(elementOrId, { kind: 'distill-curves', aspect });
    this.card = card;
    this.values = null;
    this.controlsHost = null;
    this.valuesNode = null;
    this.inputs = new Map();
  }

  /** The builder with the sliders' values: what the screen shows is what an export draws. */
  buildOption({ payload, opts = {}, metrics }) {
    const values = opts.values ?? this.values ?? null;
    return distillCurvesOption(payload, { ...opts, ...(values ? { values } : {}) }, metrics);
  }

  syncHeight() {
    if (!this.element?.style || !this.lastPayload) return false;
    const width = this.element.clientWidth || 1100;
    const px = `${plotHeight(this.lastPayload, this.lastOpts ?? {}, width)}px`;
    if (this.element.style.height === px) return false;
    this.element.style.height = px;
    return true;
  }

  render(payload, opts = {}) {
    // The values stay with the card across species, tasks and themes, clamped to the payload's domains.
    this.values = curvesValues(payload, this.values ?? opts.values ?? null);
    const withValues = { ...opts, values: { ...this.values } };
    this.lastPayload = payload;
    this.lastOpts = withValues;
    this.syncHeight();
    super.render(payload, withValues);
    this.renderControls();
  }

  relayout() {
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.relayout();
  }

  exportMetrics(width) {
    if (!this.lastPayload) return super.exportMetrics(width);
    return { width, height: plotHeight(this.lastPayload, this.lastOpts ?? {}, width) };
  }

  /** Set one secondary variable: repaint from the payload in hand, say the values, tell the drawer. */
  setValue(key, value) {
    if (!this.lastPayload || !this.values || !(key in this.values)) return;
    this.applyValues({ ...this.values, [key]: Number(value) });
  }

  /** Every variable back to its domain's midpoint. */
  resetValues() {
    if (this.lastPayload) this.applyValues(null);
  }

  /** Take `values` (clamped; null for the midpoints) and repaint without a request. */
  applyValues(values) {
    this.values = curvesValues(this.lastPayload, values);
    this.lastOpts = { ...(this.lastOpts ?? {}), values: { ...this.values } };
    if (this.syncHeight() && this.chart) this.chart.resize();
    this.paint();
    this.syncControls();
    const element = this.element;
    if (element && typeof element.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
      element.dispatchEvent(new CustomEvent('models:panelstate', { bubbles: true, detail: { card: this.card } }));
    }
  }

  notesState() {
    return { values: this.values ? { ...this.values } : null };
  }

  /** The slider row's host, created once after the card's plot frame; null outside a card. */
  ensureControlsHost() {
    if (this.controlsHost) return this.controlsHost;
    const frame = this.element?.closest?.('.plot-frame');
    if (!frame || typeof frame.after !== 'function') return null;
    const doc = this.element.ownerDocument ?? globalThis.document;
    const host = doc.createElement('div');
    host.className = 'curve-controls';
    host.setAttribute('role', 'group');
    host.setAttribute('aria-label', 'Secondary variables of the energy formulas');
    frame.after(host);
    this.controlsHost = host;
    return host;
  }

  renderControls() {
    const host = this.ensureControlsHost();
    if (!host) return;
    const doc = this.element.ownerDocument ?? globalThis.document;
    const el = (tag, className = '', text = null) => {
      const node = doc.createElement(tag);
      if (className) node.className = className;
      if (text !== null) node.textContent = text;
      return node;
    };
    const used = usedVariables(this.lastPayload);
    this.inputs = new Map();
    const nodes = [];
    for (const [key, spec] of Object.entries(used)) {
      const label = el('label', 'curve-control');
      const [lo, hi] = spec.domain;
      const name = el('span', 'curve-control-name', `${spec.label ?? key}${spec.unit ? ` [${spec.unit}]` : ''}`);
      const users = (spec.usedBy ?? []).map((u) => `${this.lastPayload.speciesLabels?.[u.species] ?? u.species} · ${this.lastPayload.frameLabels?.[u.frame] ?? u.frame}`);
      name.title = `Read by: ${users.join(', ')}. Domain ${valueText(spec, lo)} to ${valueText(spec, hi)}, a drawing choice; it starts at the midpoint.`;
      const input = el('input');
      input.type = 'range';
      input.min = String(lo);
      input.max = String(hi);
      input.step = String((hi - lo) / 100);
      input.value = String(this.values[key]);
      input.setAttribute('aria-label', `${spec.label ?? key}${spec.unit ? ` in ${spec.unit}` : ''}`);
      const output = el('output', 'curve-control-value', valueText(spec, this.values[key]));
      input.addEventListener('input', () => this.setValue(key, input.value));
      input.addEventListener('change', () => this.setValue(key, input.value));
      label.append(name, input, output);
      this.inputs.set(key, { input, output, spec });
      nodes.push(label);
    }
    if (nodes.length) {
      const reset = el('button', 'mini curve-reset', 'Midpoints');
      reset.type = 'button';
      reset.title = 'Set every variable back to the midpoint of its stated domain';
      reset.addEventListener('click', () => this.resetValues());
      nodes.push(reset);
    }
    this.valuesNode = el('p', 'curve-values', '');
    this.valuesNode.setAttribute('aria-live', 'polite');
    nodes.push(this.valuesNode);
    host.replaceChildren(...nodes);
    this.syncControls();
  }

  /** The inputs, outputs and the printed values, from the instance's values. */
  syncControls() {
    for (const [key, { input, output, spec }] of this.inputs) {
      if (String(input.value) !== String(this.values[key])) input.value = String(this.values[key]);
      output.textContent = valueText(spec, this.values[key]);
    }
    if (this.valuesNode && this.lastPayload) {
      const model = curvesModel(this.lastPayload, { values: this.values });
      const said = model.valuesText;
      this.valuesNode.textContent = said
        ? `Values in force: ${said}. Each curve is conditional at these values, not a marginal prediction. `
          + `x runs to ${num(model.xTop)} GeV; ${model.clipped.length ? `${model.clipped.length} curve${model.clipped.length === 1 ? '' : 's'} leave${model.clipped.length === 1 ? 's' : ''} the 0–${num(model.yTop)} GeV range (carets).` : `every curve stays inside 0–${num(model.yTop)} GeV.`}`
        : 'Every curve drawn depends on E_sum alone.';
    }
  }

  clear() {
    super.clear();
    this.controlsHost?.remove?.();
    this.controlsHost = null;
    this.valuesNode = null;
    this.inputs = new Map();
  }
}
