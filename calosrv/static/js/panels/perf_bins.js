/* E2: each network's error per 1 GeV momentum bin, as grouped bars.
 *
 * `/api/model-performance?slice_by=momentum_bin` ships, under
 * `by_momentum_bin`, one series per (input frame, shower) - and on an
 * aggregate experiment one more, the XGBoost hold-out (code `xgb`) - with one
 * point per producer momentum bin for every statistic named in `quantities`
 * (RMSE, MAE, the median relative error, the bias; the angle task adds the
 * median absolute error). The panel draws one statistic at a time
 * (`opts.quantity`, a key of `quantities`): nothing is hard-wired to a
 * network, a frame or a statistic, so a series or a quantity the server adds
 * (XGBoost's azimuth group, with its wrapped residual and no relative error)
 * draws without a special case. A series that does not report a statistic is
 * left out of that statistic and named in the drawer.
 *
 * ## Bars from zero at explicit offsets
 *
 * Every bar starts at zero (CLAUDE.md section 2; a signed bias runs down from
 * zero) and sits inside its momentum bin at an offset `groupedBarGeometry`
 * computes, so the x axis stays the physical momentum in GeV and a missing bin
 * is a visible gap, never a squeezed category.
 *
 * ## The whisker is the interval of the bar's own statistic
 *
 * A capped whisker on a bar is the 95% interval of the plotted aggregate, as
 * the server names it per quantity: for the RMSE a χ² interval under normal
 * residuals to N = 19 and the seeded percentile bootstrap from N = 20
 * (decision D-4), Student-t for the MAE and the bias, the exact
 * order-statistic or the seeded percentile-bootstrap interval for the median
 * (`<q>_method` per point). Where the server has none (a median below N = 6)
 * there is no whisker and the bar is faded: a point is weak exactly when it
 * has no interval, whatever its N, so no aggregate is ever a naked solid bar.
 * The whisker is light ink on a dark casing (`customWhiskers` `casing`), so it
 * clears 3:1 over any bar fill and over the card. The spread of the showers is
 * never drawn here.
 *
 * A bin of one shower is not an aggregate but an observation (decision D-9):
 * it is drawn as a dot at its value, labelled one shower, never as a bar.
 *
 * ## The y range follows robust evidence
 *
 * The range is the server's (`y_max[quantity]`): set by the points with N ≥ 15
 * (`drives_scale`), or, with none, by the weak points' values alone and
 * labelled provisional on the axis. A bar or whisker beyond it is clipped at
 * the axis with a caret whose tooltip gives the true values, and the server's
 * `overflow` list is the drawer's count.
 *
 * ## Colour is the network, fill is the shower
 *
 * The input frames are nominal categories, so they take ColorBrewer's
 * qualitative hues from palette.js (`qualitativeStops`: Set2 on the dark
 * screen, its Dark2 partner on white - the light screen card and paper -
 * as `THEME.qualitativePalette` names them, the four colours measured there
 * for contrast and colour-vision deficiency), in the fixed order absolute,
 * per-shower translated, Local, XGBoost - the order the importance card gives
 * absolute, translated, local and no frame - so a frame keeps its colour across
 * selections and cards. Shower A is a solid bar, shower B a light wash with a
 * solid outline, so the two read apart in greyscale too; the legend's swatches
 * are drawn the same way, and the legend wraps into rows rather than paging.
 */

import { THEME, axisPadding, formatNumber, formatInt } from '../scale.js';
import { contrast, qualitativeStops } from '../palette.js';
import { customWhiskers, customLine, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries, clampInterval,
  withColour, wrappedLegend, legendTop, legibleOpacity, rgbOf, emptyChartOption, INK_CONTRAST,
} from './chart_panel.js';

/** Tick-step mantissas: a step is one of these times a power of ten. */
const STEP_MANTISSAS = [1, 2, 2.5, 4, 5];
/** The round steps a top off the step grid falls back to (never 4: 0.04 reads as arbitrary). */
const ROUND_MANTISSAS = [1, 2, 2.5, 5];

/**
 * A round tick interval that lands on both ends of [lo, hi] (the server's
 * rounded top, `performance_bins.TOP_MANTISSAS`, and minus it for a signed
 * statistic), with at most `maxTicks` steps: 16 → 2, 140 → 20, 0.35 → 0.05,
 * ±16 → 4, 0.12 → 0.02, 0.25 → 0.05. A top no round step lands on (a payload
 * from before that rounding) takes the finest 1-2-2.5-5 step that fits, its
 * top tick off the grid, never a quarter of the span (0.055 for 0.22).
 */
export function dividingInterval(lo, hi, maxTicks = 8) {
  const span = hi - lo;
  if (!(span > 0)) return 1;
  const ends = [lo, hi].filter((v) => v !== 0).map(Math.abs);
  const fits = (step) => ends.every((v) => Math.abs(v / step - Math.round(v / step)) < 1e-6);
  const decade = 10 ** Math.floor(Math.log10(span / maxTicks));
  for (const scale of [1, 10, 100]) {
    for (const m of STEP_MANTISSAS) {
      const step = m * decade * scale;
      if (span / step <= maxTicks + 1e-9 && fits(step)) return step;
    }
  }
  for (const scale of [1, 10, 100]) {
    for (const m of ROUND_MANTISSAS) {
      const step = Number((m * decade * scale).toPrecision(12));
      if (span / step <= maxTicks + 1e-9) return step;
    }
  }
  return span / 4;
}

/** The statistics whose interval is the median's (order statistics from N = 6). */
const MEDIAN_QUANTITIES = new Set(['median_rel', 'median_abs', 'phi_median_abs']);

/** The sample size from which the plotted statistic has an interval at all. */
export function intervalFloorOf(quantity, thresholds = {}) {
  return MEDIAN_QUANTITIES.has(quantity) ? (thresholds.order_statistic ?? 6) : (thresholds.interval ?? 2);
}

/** Whether an aggregate experiment's XGBoost momentum regressor is what the card draws. */
export function isMomentumRegressor(payload) {
  const block = payload?.by_momentum_bin ?? {};
  const xgb = block.source === 'xgb' || payload?.network?.frame === 'xgb'
    || (block.series ?? []).some((s) => sourceOf(s) === 'xgb');
  return xgb && (block.model ?? payload?.network?.model) === 'energy';
}

/** The order the networks' hues are given in, so a frame keeps its colour whatever else is drawn. */
export const SOURCE_ORDER = Object.freeze(['absolute', 'trans', 'local', 'xgb']);

/** How each source is named when the series carries no label of its own. */
export const SOURCE_LABELS = Object.freeze({
  absolute: 'Absolute-frame network',
  trans: 'Per-shower translated network (legacy)',
  local: 'Local-frame network',
  xgb: 'XGBoost',
});

/** Fill opacity of shower A's bar and shower B's wash. */
const FILL_A = 0.78;
const FILL_B = 0.22;
/** Share of a momentum bin the group of bars takes. */
const GROUP_FILL = 0.84;
const CAP_PX = 3;
/** The casing under a whisker, and the radius of a one-shower dot (px). */
const CASING_PX = 3;
const DOT_PX = 3.5;

/** A series colour as the light wash of shower B's bars. */
function washOf(colour) {
  const rgb = rgbOf(colour);
  return rgb ? `rgba(${rgb.join(',')},${FILL_B})` : colour;
}

const num = (v, d = 3) => formatNumber(v, d);

/**
 * Where `nSeries` bars sit inside a band of width `band` (data units): each
 * bar's width and its centre's offset from the band's centre. The group takes
 * `fill` of the band, so neighbouring bins stay apart. `nGroups` is the number
 * of bands, carried so a caller can size the chart from one call.
 */
export function groupedBarGeometry(nGroups, nSeries, band = 1, { fill = GROUP_FILL } = {}) {
  const n = Math.max(1, nSeries);
  const total = fill * band;
  const width = total / n;
  return {
    groups: Math.max(0, nGroups),
    width,
    offsets: Array.from({ length: n }, (_, k) => -total / 2 + (k + 0.5) * width),
  };
}

/** The source a series belongs to: an input frame, or 'xgb'. */
export function sourceOf(s) {
  if (s?.code === 'xgb' || s?.source === 'xgb' || /^xgb\b/.test(String(s?.key ?? ''))) return 'xgb';
  return s?.network?.frame ?? String(s?.key ?? '').split(':')[0];
}

/** The qualitative hue of each source, on the card in force (dark or light screen, or print). */
export function sourceColours(sources) {
  const card = rgbOf(THEME.card) ?? [28, 33, 40];
  const hues = qualitativeStops(THEME.qualitativePalette, SOURCE_ORDER.length);
  const out = {};
  // A known source keeps its place in SOURCE_ORDER; another takes the next free hue.
  const rest = sources.filter((k) => !SOURCE_ORDER.includes(k));
  for (const k of sources) {
    const i = SOURCE_ORDER.includes(k) ? SOURCE_ORDER.indexOf(k) : SOURCE_ORDER.length + rest.indexOf(k);
    const hue = hues[i % hues.length];
    // Every hue is measured against the card; a hue that ever fell short takes the text ink.
    out[k] = contrast(rgbOf(hue), card) >= INK_CONTRAST ? hue : THEME.text;
  }
  return out;
}

/**
 * The statistics the response offers, in its order: the shell's segmented
 * control. `group` is the label a statistic belongs to where the server groups
 * them (`quantity_groups`: the XGBoost angle task's θ and φ), else null.
 */
export function perfQuantities(payload) {
  const block = payload?.by_momentum_bin ?? {};
  const groups = Object.entries(block.quantity_groups ?? {});
  const groupOf = (key) => groups.find(([, keys]) => Array.isArray(keys) && keys.includes(key))?.[0] ?? null;
  return Object.entries(block.quantities ?? {}).map(([key, v]) => ({
    key, label: v.label, unit: v.unit, signed: Boolean(v.signed), group: groupOf(key),
  }));
}

/** The statistic drawn: `wanted` when the response has it, else its first. */
export function perfQuantity(payload, wanted) {
  const keys = perfQuantities(payload).map((q) => q.key);
  return keys.includes(wanted) ? wanted : (keys[0] ?? null);
}

/** A unit as drawn: a fraction is read in percent. */
export function displayUnit(unit) {
  return unit === 'fraction' ? { unit: '%', factor: 100 } : { unit: unit ?? '', factor: 1 };
}

/** The series a card draws: one shower, or both. */
function shownSeries(series, shower) {
  return (series ?? []).filter((s) => !shower || shower === 'both' || !s.shower || s.shower === shower);
}

/** The name of a series in the legend and every tooltip. */
export function seriesLabel(s, nShowers) {
  const source = sourceOf(s);
  const base = s.label ?? SOURCE_LABELS[source] ?? source;
  return nShowers > 1 && s.shower ? `${base} · shower ${String(s.shower).toUpperCase()}` : base;
}

/** The bins' edges as a contiguous list, and the payload bin each edge interval holds (−1 for a gap). */
function binEdges(bins) {
  const lo = bins.p_lo ?? [];
  const hi = bins.p_hi ?? [];
  const edges = [...new Set([...lo, ...hi].filter(Number.isFinite))].sort((a, b) => a - b);
  const owner = [];
  for (let i = 0; i + 1 < edges.length; i += 1) owner.push(lo.findIndex((v, k) => v === edges[i] && hi[k] === edges[i + 1]));
  return { edges, owner };
}

/**
 * Everything the chart and the drawer need, decided once. Pure:
 * {quantity, q, unit, factor, y: {min, max, provisional, note, overflow,
 * n_overflow}, series: [{key, label, source, shower, colour, points}],
 * omitted: [labels], clipped: {bars, whiskers}, thresholds, bins, nShowers}.
 * A point is {i, x, x0, x1, value, lo, hi, n, n_missing, method, weak, drives,
 * theta_min, n_small_theta, ...draw} with values already in display units.
 */
export function perfModel(payload, opts = {}) {
  const block = payload?.by_momentum_bin;
  if (!block) return null;
  const quantity = perfQuantity(payload, opts.quantity);
  const q = block.quantities?.[quantity] ?? {};
  const { unit, factor } = displayUnit(q.unit);
  const yRaw = block.y_max?.[quantity] ?? {};
  const scaled = (v) => (Number.isFinite(v) ? v * factor : null);
  const y = {
    min: Number.isFinite(yRaw.min) ? yRaw.min * factor : 0,
    max: scaled(yRaw.value),
    provisional: Boolean(yRaw.provisional),
    note: yRaw.note ?? '',
    overflow: yRaw.overflow ?? [],
    n_overflow: yRaw.n_overflow ?? 0,
    signed: Boolean(yRaw.signed ?? q.signed),
  };
  const thresholds = block.thresholds ?? {};
  const intervalFloor = intervalFloorOf(quantity, thresholds);
  const all = block.series ?? [];
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const shown = shownSeries(all, opts.shower);
  const reporting = shown.filter((s) => Array.isArray(s[quantity]));
  const omitted = shown.filter((s) => !Array.isArray(s[quantity])).map((s) => seriesLabel(s, nShowers));
  const colours = sourceColours([...new Set(reporting.map(sourceOf))]);
  const bins = block.bins ?? {};
  const nBins = (bins.p_lo ?? []).length;
  const geometry = groupedBarGeometry(nBins, reporting.length, 1);
  const clipped = { bars: 0, whiskers: 0 };

  const series = reporting.map((s, k) => {
    const points = [];
    const values = s[quantity];
    const los = s[`${quantity}_lo`] ?? [];
    const his = s[`${quantity}_hi`] ?? [];
    const methods = s[`${quantity}_method`] ?? [];
    for (let i = 0; i < nBins; i += 1) {
      const value = scaled(values[i]);
      if (value === null) continue;
      const band = (bins.p_hi[i] - bins.p_lo[i]) || 1;
      const centre = 0.5 * (bins.p_lo[i] + bins.p_hi[i]) + geometry.offsets[k] * band;
      const half = 0.5 * geometry.width * band;
      const point = {
        i, x: centre, x0: centre - half, x1: centre + half, value,
        lo: scaled(los[i]), hi: scaled(his[i]), method: methods[i] ?? null,
        n: s.n?.[i] ?? null, n_missing: s.n_missing?.[i] ?? 0, drives: Boolean(s.drives_scale?.[i]),
        theta_min: s.theta_min?.[i] ?? null, n_small_theta: s.n_small_theta?.[i] ?? 0,
      };
      // Weak exactly when there is no interval to say how precise the value is (P-4).
      point.weak = !(Number.isFinite(point.lo) && Number.isFinite(point.hi));
      // One shower is an observation, not an aggregate: a dot, never a bar (D-9).
      point.single = point.n === 1;
      if (Number.isFinite(y.max)) {
        point.barCut = value > y.max || value < y.min;
        const c = clampInterval(point.lo, point.hi, y.min, y.max);
        point.whisker = c;
        if (point.barCut) clipped.bars += 1;
        if (c.cutLo || c.cutHi) clipped.whiskers += 1;
      }
      points.push(point);
    }
    return {
      key: s.key, label: seriesLabel(s, nShowers), source: sourceOf(s), shower: s.shower ?? null,
      colour: colours[sourceOf(s)], points, raw: s,
    };
  });
  return {
    quantity, q, unit, factor, y, series, omitted, clipped, thresholds, bins, nShowers, intervalFloor,
    model: block.model ?? payload?.network?.model ?? null, notes: block.notes ?? {},
    momentum: isMomentumRegressor(payload),
    // The XGBoost series has one shower per event, and counts events.
    noun: block.source === 'xgb' || (reporting.length > 0 && reporting.every((s) => sourceOf(s) === 'xgb')) ? 'event' : 'shower',
  };
}

/** A value with its display unit. */
function withUnit(v, unit, digits = 3) {
  if (!Number.isFinite(v)) return '—';
  return `${num(v, digits)}${unit === '%' ? '%' : (unit ? ` ${unit}` : '')}`;
}

/** The method of one point's interval, as the server names it per quantity and point (`<q>_method`). */
function methodText(model, p) {
  const median = MEDIAN_QUANTITIES.has(model.quantity);
  if (p.method === 'order_statistic') return 'exact order-statistic interval of the median';
  if (p.method === 'bootstrap_percentile') {
    return median ? 'seeded percentile bootstrap of the median' : `seeded percentile bootstrap of the ${model.q.label ?? model.quantity}`;
  }
  if (p.method === 'chi2_rmse') {
    return `χ² interval of the RMSE on ${formatInt(p.n)} degrees of freedom, which assumes normally distributed residuals `
      + 'centred on zero (approximate otherwise, and with a bias)';
  }
  return model.q.interval ?? '';
}

/** The interval sentence of one point: the server's method for the bar's own statistic. */
function intervalText(model, p) {
  const noun = model.noun;
  if (!Number.isFinite(p.lo) || !Number.isFinite(p.hi)) {
    return mutedLine(p.single
      ? `no interval: one ${noun} is an observation, not an aggregate, and has nothing to say how precise it is`
      : `no interval: the ${model.q.label ?? model.quantity} has one from N = ${formatInt(model.intervalFloor)}`);
  }
  return `95% interval [${withUnit(p.lo, model.unit)}, ${withUnit(p.hi, model.unit)}] ${mutedLine(`(${methodText(model, p)}: the precision of the ${model.q.label ?? model.quantity}, not the spread of the ${noun}s)`)}`;
}

/** The tooltip of one bar. */
export function perfTip(model, s, p) {
  const bins = model.bins;
  const binLabel = bins.label?.[p.i] ?? `${num(bins.p_lo?.[p.i])}–${num(bins.p_hi?.[p.i])} GeV`;
  const lines = [`<b>${escapeHtml(model.q.label ?? model.quantity)} of ${escapeHtml(s.label)}, ${escapeHtml(binLabel)}: ${withUnit(p.value, model.unit)}</b>`];
  lines.push(intervalText(model, p));
  const noun = model.noun;
  let mark = '';
  if (p.single) mark = ` — one ${noun}: drawn as a dot, an observation, not as a bar`;
  else if (p.weak) mark = ` — below the ${model.q.label ?? model.quantity}'s interval floor, N = ${formatInt(model.intervalFloor)}: the bar is faded`;
  lines.push(`N = ${formatInt(p.n)} ${noun}${p.n === 1 ? '' : 's'}${mark}`);
  if (model.q.definition) lines.push(mutedLine(model.q.definition));
  if (p.n_missing) lines.push(mutedLine(`${formatInt(p.n_missing)} ${noun}${p.n_missing === 1 ? '' : 's'} without a prediction in this bin: dropped, never zero-filled`));
  if (Number.isFinite(p.theta_min)) {
    lines.push(mutedLine(`smallest true θ in the bin ${num(p.theta_min, 4)} rad; ${formatInt(p.n_small_theta)} shower${p.n_small_theta === 1 ? '' : 's'} with θ < 0.1 rad`
      + `${p.n_small_theta && model.quantity === 'median_rel' ? ': |Δθ| / θ grows like 1 / θ there, so read the median absolute error beside it' : ''}`));
  }
  if (p.barCut || p.whisker?.cutLo || p.whisker?.cutHi) {
    lines.push(mutedLine(`clipped at the ${model.y.provisional ? 'provisional ' : ''}axis (${withUnit(model.y.min, model.unit)} to ${withUnit(model.y.max, model.unit)}); the values above are the true ones`));
  }
  if (!p.drives) lines.push(mutedLine('below N = 15: does not set the y range'));
  return lines.join('<br/>');
}

/** The readout of one momentum bin: every series' value there. */
function perfReadout(model, owner, i) {
  const k = owner[i];
  if (k < 0) return mutedLine('no momentum bin here');
  const bins = model.bins;
  const lines = [`<b>${escapeHtml(bins.label?.[k] ?? '')}</b> · ${escapeHtml(model.q.label ?? model.quantity)}`];
  for (const s of model.series) {
    const p = s.points.find((pt) => pt.i === k);
    if (!p) { lines.push(mutedLine(`${s.label}: no ${model.noun}`)); continue; }
    const ci = Number.isFinite(p.lo) && Number.isFinite(p.hi) ? ` [${withUnit(p.lo, model.unit)}, ${withUnit(p.hi, model.unit)}]`
      : (p.single ? ` (one ${model.noun}, a dot)` : ' (no interval)');
    lines.push(`<span style="color:${s.colour}">${p.single ? '●' : '■'}</span> ${escapeHtml(s.label)}: ${withUnit(p.value, model.unit)}${ci} · N = ${formatInt(p.n)}`);
  }
  lines.push(mutedLine('brackets: the 95% interval of the statistic (the capped whisker)'));
  return lines.join('<br/>');
}

/**
 * The E2 option. Pure: `opts` = {quantity?, shower?: 'a' | 'b' | 'both',
 * tooltipPosition?}; `metrics` = {width, height}.
 */
export function perfBinsOption(payload, opts = {}, metrics = {}) {
  const model = perfModel(payload, opts);
  if (!model) return emptyChartOption(opts, metrics, 'No per-bin performance in this response.');
  if (!model.series.length || !Number.isFinite(model.y.max) || !(model.y.max > model.y.min)) {
    return emptyChartOption(opts, metrics, `No ${model.q.label ?? 'statistic'} can be estimated in this selection.`);
  }
  const pad = axisPadding();
  const width = metrics.width || 760;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const { y, unit } = model;
  const series = [];
  const legend = [];

  for (const s of model.series) {
    const colour = s.colour;
    const isB = s.shower === 'b' && model.nShowers > 1;
    const base = Math.min(Math.max(0, y.min), y.max);
    series.push(withColour({
      type: 'custom',
      name: s.label,
      clip: true,
      z: 4,
      data: s.points.map((p, index) => [p.x, p.value, index]),
      renderItem: (params, api) => {
        const p = s.points[params.dataIndex];
        const top = Math.min(Math.max(p.value, y.min), y.max);
        if (p.single) {
          // An observation: a dot at its value, in the series' own fill, outlined.
          const c = api.coord([p.x, top]);
          return {
            type: 'circle',
            shape: { cx: c[0], cy: c[1], r: DOT_PX },
            style: {
              fill: isB ? washOf(colour) : colour, stroke: isB ? colour : THEME.canvas,
              lineWidth: THEME.lineAxis,
            },
          };
        }
        const a = api.coord([p.x0, base]);
        const b = api.coord([p.x1, top]);
        const fill = (isB ? FILL_B : FILL_A) * (p.weak ? 0.45 : 1);
        return {
          type: 'rect',
          shape: { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), width: Math.abs(b[0] - a[0]), height: Math.abs(b[1] - a[1]) },
          style: {
            fill: colour, opacity: 1, fillOpacity: fill,
            stroke: colour, strokeOpacity: legibleOpacity(colour, p.weak ? 0.5 : 1),
            lineWidth: THEME.lineAxis, lineDash: p.weak ? [2, 2] : null,
          },
        };
      },
      tooltip: { formatter: (prm) => perfTip(model, s, s.points[prm.dataIndex]) },
    }, colour));
    // B's swatch is its bars' wash with their outline, so the legend matches the marks (P-15).
    if (isB) series[series.length - 1].itemStyle = { color: washOf(colour), borderColor: colour, borderWidth: 1 };
    legend.push({ name: s.label, icon: 'rect' });

    const whiskers = s.points
      .filter((p) => !p.single && p.whisker && p.whisker.lo !== null && p.whisker.hi !== null && Number.isFinite(p.lo) && Number.isFinite(p.hi))
      .map((p) => [p.x, p.whisker.lo, p.whisker.hi, { caps: p.whisker.caps, point: p, opacity: p.weak ? legibleOpacity(THEME.text, 0.6) : 1 }]);
    if (whiskers.length) {
      series.push(customWhiskers({
        name: `${s.label} · 95% interval`,
        points: whiskers,
        capPx: CAP_PX,
        color: THEME.text,
        width: THEME.lineAxis,
        // A dark casing under the ink: 3:1 against any bar fill and the card (P-3).
        casing: { color: THEME.canvas, width: CASING_PX },
        z: 6,
        tooltip: (d) => perfTip(model, s, d.point),
      }));
    }
    const carets = [];
    for (const p of s.points) {
      const tip = perfTip(model, s, p);
      if (p.value > y.max || p.whisker?.cutHi) carets.push({ at: [p.x, y.max], dir: 'up', tooltip: tip });
      if (p.value < y.min || p.whisker?.cutLo) carets.push({ at: [p.x, y.min], dir: 'down', tooltip: tip });
    }
    if (carets.length) series.push(caretSeries({ name: `${s.label} (clipped)`, carets, color: colour }));
  }

  const { edges, owner } = binEdges(model.bins);
  if (y.signed && y.min < 0) {
    series.push(customLine({
      name: 'zero', from: [edges[0], 0], to: [edges[edges.length - 1], 0], color: THEME.muted, width: THEME.lineAxis,
      z: 3, tooltip: `zero ${escapeHtml(model.q.label ?? '')}: prediction and truth agree on average`,
    }));
  }
  if (edges.length > 1) {
    // One line per series: a list, so it leaves the chart like every explanation.
    series.push(binHoverSeries({
      name: 'bin readout', edges, y: Math.max(y.min, 0), tooltip: (i) => perfReadout(model, owner, i),
    }));
  }

  const top = legendTop(legend, plotWidthPx, { wrap: true });
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  const unitText = unit ? ` [${unit}]` : '';
  const prov = y.provisional ? ' — provisional' : '';
  // The XGBoost regressor of an aggregate predicts momentum, and its axis says so (P-5).
  const of = model.momentum && !model.quantity.startsWith('phi') ? ' of the momentum' : '';
  const yName = fitName([`${model.q.label ?? model.quantity}${of}${unitText}${prov}`, `${model.q.label ?? model.quantity}${unitText}${prov}`,
    `${model.quantity}${unitText}${prov}`], plotHeightPx);
  const xName = fitName(['Incident momentum p [GeV]', 'p [GeV]'], plotWidthPx);
  const span = edges[edges.length - 1] - edges[0];
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: wrappedLegend(legend, { left: pad.left, right: pad.right }),
    xAxis: valueAxis({ name: xName, min: edges[0], max: edges[edges.length - 1], interval: span > 12 ? 2 : 1 }),
    yAxis: valueAxis({
      name: yName, min: y.min, max: y.max, interval: dividingInterval(y.min, y.max), split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

export class PerfBinsPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'perf-bins', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: perfBinsOption(payload, opts, metrics) };
  }
}
