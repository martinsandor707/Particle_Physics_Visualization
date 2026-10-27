/* C4: distributions by incident-momentum bin, as overlaid step outlines.
 *
 * `/api/distributions` ships one series per 1 GeV momentum bin on one shared
 * set of display bins: exact counts (footprint-splatted hit counts for u, v
 * and w, so a count may be a multiple of 1/8), each series a run of counts
 * from `offset` into `edges`. Every series is drawn as a step outline - the
 * notebook's `element='step'` - because twenty filled histograms over each
 * other would hide one another.
 *
 * ## Encoding
 *
 * The momentum bins are ordered, so they take ordered stops of the chosen
 * sequential ramp, each clearing 3:1 against the card (chart_panel.js
 * `seriesStops`). A series of fewer than 15 showers is dashed: its counts are
 * exact, but the shape of a handful of showers is not a distribution, as the
 * server's note says. Counts start at zero on the linear axis; on the log axis
 * empty bins are not drawn and each run of counts closes at the axis floor,
 * which the axis name states. Hit energy runs on a log x axis over the 1st to
 * 99th percentile; φ always shows its full period (−π, π], never cropped and
 * never averaged - each series' R̄ and Rayleigh p are in its tooltip.
 *
 * ## Disclosure
 *
 * Counts beyond the display range are not dropped by the server; they are
 * counted per series (`below`, `above`). A caret at each axis end carries them
 * and the Details drawer the total (`display.n_outside`). The comb statistic
 * of the splatted u/v/w profiles goes to the drawer, `combed: null` read as
 * unmeasurable rather than as clean.
 *
 * The same builder serves D4 and residual histograms later: a series may
 * carry `density` instead of `counts`, and a `kde` {x, y} curve, drawn when
 * present.
 *
 * ## Page 2: feature and residual densities (`featureHistOption`, `residualOption`)
 *
 * The models page draws two more payloads with this panel, both on the energy
 * panel's low-N ladder rather than as raw counts: D4 (`/api/features?view=hist`,
 * one series per momentum class) and the residual histogram of the prediction
 * density (`/api/prediction-density`, one series per shower). The server says
 * what each series may draw (`draw`, `drives_scale`) and the client never
 * draws what it withheld:
 *
 *   N ≥ 15   density histogram, from zero; it sets the density axis
 *   N ≥ 8    the density curve (D4: a Gaussian KDE; residual: the fitted
 *            Gaussian), thinner and fainter, plus the events beneath it
 *   N <  8   the events only (D4), or the events and the summary marks
 *
 * The y range is set by the robust series only (D4: the server's `y_max`;
 * residual: the driving series' histogram and curve peaks). A weak curve above
 * it is clipped with a caret carrying its true peak, and with no robust series
 * the axis says "provisional"; with no estimable density at all it is left
 * unlabelled and the panel says so. The events, and the residual's summary
 * marks of a series below the histogram floor - its mean with the capped
 * Student-t interval and its uncapped ± 1 SD bar - sit in a tinted, captioned
 * reserved band at the foot of the plot, every tooltip there saying its height
 * is a drawing offset. A histogram series' mean is a long-dashed rule from the
 * band's top with its interval as a thin envelope, and its SD is the
 * histogram's own spread, as B1 draws it. The residual's zero is a dotted rule:
 * prediction equals truth there. D4 offers a count axis too (`opts.quantity:
 * 'count'`), the notebook's stat=count, on which the KDE is the expected count
 * per bin. Momentum classes are ordered and take `seriesStops`; the showers
 * take their colours with B dashed. An azimuth is drawn on its full period and
 * never gets a linear kernel (its `kde` is null). Counts beyond the axis, and
 * D4's eps-floored values, are counted per series in the tooltips and the
 * drawer.
 *
 * The XGBoost azimuth residual (`residual.statistics: 'circular'`) is wrapped
 * to (−π, π] and has no line statistics: the server sends no markers, so no
 * mean rule, whisker or SD bar is drawn, and its tooltip quotes the circular
 * mean direction, R̄ and the circular SD instead of a mean and σ. Its curve,
 * where there is one, is the Gaussian fit of the core, named so.
 */

import { THEME, axisPadding, formatNumber, formatInt, formatSci, formatPercent, typographic } from '../scale.js';
import { legendRows } from '../textfit.js';
import { customPolyline, customWhiskers, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries, seriesStops, niceCeil,
  niceInterval, withColour, chartLegend, FINE_STEPS, legendTop, legibleOpacity, showerColour, sigmaText,
  referenceRule, dispersionBar, clampInterval, liftedSeries, reservedBand, bandCaption, noticeGraphic, tickLabel,
  coarseInterval, OFFSET_NOTE,
} from './chart_panel.js';

/** A series below this many showers is drawn dashed (CLAUDE.md histogram floor). */
export const SHAPE_FLOOR_SHOWERS = 15;

const num = (v, d = 3) => formatNumber(v, d);

/** Tick labels of a full-period azimuth axis. */
export function piLabel(value) {
  const k = Math.round((value / Math.PI) * 2);
  // The server rounds π to six figures, so a tick sits within 10⁻³ of its multiple.
  if (Math.abs(value - (k * Math.PI) / 2) > 1e-3) return typographic(Number(value).toFixed(2));
  return { '-2': '−π', '-1': '−π/2', 0: '0', 1: 'π/2', 2: 'π' }[k] ?? typographic(Number(value).toFixed(2));
}

/** A log-axis tick: plain between 10⁻³ and 10⁶, else 1e−10 style, U+2212 throughout. */
export function logTick(value) {
  const v = Number(value);
  if (!(v > 0)) return typographic(String(v));
  if (v >= 1e-3 && v < 1e6) return num(v, 6);
  return formatSci(v, 0).replace('e+', 'e');
}

/** How a count is written: integers as integers, splatted eighths with their fraction. */
function countText(value) {
  if (!Number.isFinite(value)) return '—';
  return Number.isInteger(value) ? formatInt(value) : num(value, 3);
}

/** The y axis noun, from the payload's own weighting. */
export function countNoun(payload) {
  const w = String(payload?.quantity?.weighting ?? 'count');
  const head = w.split(' (')[0];
  return `${head.charAt(0).toUpperCase()}${head.slice(1)} per bin`;
}

/** The values of series `s` over the shared bins (counts or density). */
function valuesOf(s) {
  return s.counts ?? s.density ?? [];
}

/** The largest value any series draws. */
function peakOf(series) {
  let max = 0;
  for (const s of series) for (const v of valuesOf(s)) if (Number.isFinite(v) && v > max) max = v;
  for (const s of series) for (const v of s.kde?.y ?? []) if (Number.isFinite(v) && v > max) max = v;
  return max;
}

/** The smallest positive value any series draws: the log axis' floor decade. */
export function logFloor(series) {
  let min = Infinity;
  for (const s of series) for (const v of valuesOf(s)) if (v > 0 && v < min) min = v;
  if (!Number.isFinite(min)) return 1;
  return 10 ** Math.floor(Math.log10(Math.min(1, min)));
}

/**
 * Step-outline polylines of one series. Linear: one outline over the whole
 * run, from zero and back to zero. Log: one outline per run of non-empty bins,
 * each closing at `floor`, so an empty bin splits the outline.
 */
export function stepOutlines(edges, s, { log = false, floor = 1 } = {}) {
  const values = valuesOf(s);
  const offset = s.offset ?? 0;
  const base = log ? floor : 0;
  const runs = [];
  if (!log) {
    if (values.length) runs.push([0, values.length - 1]);
  } else {
    let start = null;
    for (let i = 0; i <= values.length; i += 1) {
      const ok = i < values.length && values[i] > 0;
      if (ok && start === null) start = i;
      if (!ok && start !== null) { runs.push([start, i - 1]); start = null; }
    }
  }
  return runs.map(([a, b]) => {
    const points = [[edges[offset + a], base]];
    for (let i = a; i <= b; i += 1) {
      const v = Number.isFinite(values[i]) ? values[i] : 0;
      const y = log ? Math.max(v, floor) : v;
      points.push([edges[offset + i], y], [edges[offset + i + 1], y]);
    }
    points.push([edges[offset + b + 1], base]);
    return points;
  });
}

function seriesTip(payload, s) {
  const q = payload.quantity ?? {};
  const lines = [`<b>${escapeHtml(s.label)}</b>: ${formatInt(s.n)} ${escapeHtml(q.source === 'hits' ? 'hits' : 'entries')}`
    + ` from ${formatInt(s.n_showers)} shower${s.n_showers === 1 ? '' : 's'}`];
  if (s.below || s.above) {
    lines.push(mutedLine(`${countText(s.below)} below and ${countText(s.above)} above the display range (counted, not drawn)`));
  }
  if (Number.isFinite(s.resultant)) {
    lines.push(`R̄ = ${num(s.resultant, 3)}, Rayleigh p = ${formatSci(s.rayleigh_p, 2)} `
      + mutedLine('(mean resultant length; φ is never averaged linearly)'));
  } else if (q.key === 'phi') {
    lines.push(mutedLine('R̄ needs two showers'));
  }
  if ((s.n_showers ?? 0) < SHAPE_FLOOR_SHOWERS) {
    lines.push(mutedLine(`fewer than ${SHAPE_FLOOR_SHOWERS} showers: exact counts, but not a distribution (dashed)`));
  }
  return lines.join('<br/>');
}

/**
 * The C4 option. Pure: `opts` = {palette, yScale: 'linear' | 'log',
 * tooltipPosition?}; `metrics` = {width, height}. The per-bin count list is
 * as tall as the series are many, so it takes the explanation placement.
 */
export function distributionOption(payload, opts = {}, metrics = {}) {
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const q = payload?.quantity ?? {};
  const edges = payload?.edges ?? [];
  const list = payload?.series ?? [];
  const display = payload?.display ?? {};
  const log = opts.yScale === 'log';
  const logX = q.scale === 'log10';
  const colours = seriesStops(opts.palette ?? 'viridis', Math.max(1, list.length));
  const floor = log ? logFloor(list) : 0;
  const series = [];
  const legend = [];

  list.forEach((s, k) => {
    const colour = colours[k];
    const weak = (s.n_showers ?? 0) < SHAPE_FLOOR_SHOWERS;
    const tip = seriesTip(payload, s);
    for (const points of stepOutlines(edges, s, { log, floor })) {
      series.push(withColour(customPolyline({
        name: s.label, points, color: colour, width: 1.4 * THEME.lineAxis,
        dash: weak ? 'dashed' : null, z: 5 + (k % 3), tooltip: tip,
      }), colour));
    }
    if (s.kde?.x?.length) {
      const points = s.kde.x.map((x, i) => [x, s.kde.y[i]]).filter((p) => Number.isFinite(p[1]) && (!log || p[1] > 0));
      if (points.length > 1) {
        series.push(withColour(customPolyline({
          name: s.label, points, color: colour, width: 1.6 * THEME.lineAxis, z: 6,
          tooltip: `${escapeHtml(s.label)}: kernel density estimate${s.kde.bandwidth ? `, bandwidth ${num(s.kde.bandwidth)}` : ''}`,
        }), colour));
      }
    }
    legend.push(s.label);
  });

  /* Counts beyond the display range: a caret at each end, listing the series. */
  const below = list.filter((s) => s.below > 0);
  const above = list.filter((s) => s.above > 0);
  const listTip = (rows, where) => {
    const of = (s) => (where === 'below' ? s.below : s.above);
    const total = rows.reduce((sum, s) => sum + of(s), 0);
    return `<b>${countText(total)} counted ${where} the display range</b><br/>`
      + rows.map((s) => `${escapeHtml(s.label)}: ${countText(of(s))}`).join('<br/>')
      + `<br/>${mutedLine('counted per series, never dropped from the counts; not drawn')}`;
  };
  const carets = [];
  if (below.length && Number.isFinite(display.lo)) carets.push({ at: [display.lo, floor], dir: 'left', tooltip: listTip(below, 'below') });
  if (above.length && Number.isFinite(display.hi)) carets.push({ at: [display.hi, floor], dir: 'right', tooltip: listTip(above, 'above') });
  if (carets.length) series.push(caretSeries({ name: 'beyond the display range', carets, color: THEME.muted, liftPx: 6 }));

  if (edges.length > 1) {
    series.push(binHoverSeries({
      name: 'bin readout',
      edges,
      y: log ? floor : 0,
      // One count per momentum bin, up to twenty lines: too tall to sit beside
      // the pointer, so it leaves the hovered chart like every explanation.
      tooltip: (i) => distributionReadout(payload, colours, i),
    }));
  }

  /* Axes. */
  const wraps = THEME.legendWrap;
  const rows = wraps ? Math.max(1, legendRows(legend, plotWidthPx, THEME.fontLabel, { fontFamily: THEME.fontFamily })) : 1;
  const top = pad.top + rows * 1.6 * THEME.fontLabel;
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  const unit = q.unit ? ` [${q.unit}]` : '';
  const provisional = display.provisional ? ' — provisional' : '';
  const xName = fitName([`${q.label ?? q.key}${unit}${provisional}`, `${q.key}${unit}${provisional}`], plotWidthPx);
  const noun = payload?.y_label ?? countNoun(payload);
  const floorText = logTick(floor);
  const yName = fitName(log
    ? [`${noun} (log scale, from ${floorText}; empty bins not drawn)`, `${noun} (log scale, from ${floorText})`,
      `Count per bin (log scale, from ${floorText})`, `${noun} (log scale)`]
    : [noun], plotHeightPx);
  const peak = peakOf(list);
  // The fine ladder wastes at most a quarter of the axis; the coarse one took a peak of 50 to 100.
  const yMax = log ? 10 ** Math.ceil(Math.log10(Math.max(peak, floor * 10))) : niceCeil(peak * 1.05, FINE_STEPS);
  const xAxis = logX
    ? valueAxis({ type: 'log', name: xName, min: display.lo, max: display.hi, formatter: logTick })
    : valueAxis({
      name: xName, min: display.lo, max: display.hi,
      ...(q.key === 'phi' ? { interval: Math.PI / 2, formatter: piLabel } : {}),
    });
  const yAxis = log
    ? valueAxis({ type: 'log', name: yName, min: floor, max: yMax, split: true, nameGap: 3.6 * THEME.fontLabel, formatter: logTick })
    : valueAxis({ name: yName, min: 0, max: yMax, interval: niceInterval(yMax), split: true, nameGap: 3.6 * THEME.fontLabel });

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend),
    xAxis,
    yAxis,
    graphic: list.length ? [] : [{
      type: 'text', silent: true,
      style: { x: width / 2, y: height / 2, text: 'No entries in this selection.', textAlign: 'center',
        fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily },
    }],
    series,
  };
}

/** The readout of display bin i: every series' count there, colour-keyed. */
export function distributionReadout(payload, colours, i) {
  const q = payload.quantity ?? {};
  const edges = payload.edges;
  const fmt = (v) => (q.scale === 'log10' ? formatSci(v, 2) : num(v, 3));
  const symbol = { phi: 'φ', theta: 'θ', energy: 'E' }[q.key] ?? q.key ?? '';
  const lines = [`<b>${escapeHtml(symbol)} ${fmt(edges[i])} … ${fmt(edges[i + 1])}${q.unit ? ` ${escapeHtml(q.unit)}` : ''}</b>`];
  let empty = 0;
  (payload.series ?? []).forEach((s, k) => {
    const j = i - (s.offset ?? 0);
    const v = j >= 0 && j < valuesOf(s).length ? valuesOf(s)[j] : 0;
    if (!(v > 0)) { empty += 1; return; }
    lines.push(`<span style="color:${colours[k]}">■</span> ${escapeHtml(s.label)}: ${countText(v)}`);
  });
  if (empty) lines.push(mutedLine(`${empty} series empty in this bin`));
  return lines.join('<br/>');
}

/** The share of entries beyond the display range, for the drawer. */
export function distributionOutside(payload) {
  const d = payload?.display ?? {};
  return { n: d.n_outside ?? 0, fraction: d.fraction_outside ?? 0, text: formatPercent(d.fraction_outside ?? 0, 2) };
}

/* ========================================== Page 2: D4 and residuals == */

/* Pixel geometry of the reserved band above the y = 0 baseline (response.js's B1 values). */
const BAND_BASE_PX = 6;
const ROW_MAX_PX = 11;
const ROW_MIN_PX = 7;
const BAND_SHARE = 0.32;
const TICK_HALF_PX = 4;
const SD_BAND_PX = 6;
const CAP_PX = 4;
/** Headroom above the tallest robust mark. */
const DENSITY_HEADROOM = 1.15;
/** Fewest events whose histogram is drawn (CLAUDE.md's histogram floor). */
export const HISTOGRAM_FLOOR = 15;

/** A round axis top at or above `value`, free of float noise (0.6, not 0.6000000000000001). */
function roundTop(value) {
  return Number(niceCeil(value, FINE_STEPS).toPrecision(12));
}

/** Whether a payload is a D4 feature histogram. */
export function isFeatureHist(payload) {
  return payload?.view === 'hist' && Array.isArray(payload?.series) && Boolean(payload?.axis);
}

/** Whether a payload is a prediction-density response, whose residual this panel draws. */
export function isResidual(payload) {
  return Boolean(payload?.residual?.series && payload?.residual?.axis);
}

/** `count` evenly spaced values over [lo, hi]. */
function evenly(lo, hi, count) {
  return Array.from({ length: count }, (_, i) => lo + (i * (hi - lo)) / Math.max(1, count - 1));
}

/** The density axis' unit: per unit of x, per decade on a log10 axis, nothing for a pure number. */
export function densityUnit(unit, log10 = false) {
  if (log10) return ' [per decade]';
  if (!unit || unit === 'fraction' || unit === 'count') return '';
  return /^[A-Za-z]+$/.test(unit) ? ` [${unit}⁻¹]` : ` [1/${unit}]`;
}

/** A value on an x axis that may hold log10 values. */
function xText(model, v, digits = 3) {
  if (!Number.isFinite(v)) return '—';
  if (model.log10) return `${logTick(10 ** v)}`;
  return num(v, digits);
}

/** A span of x with its unit. */
function xSpan(model, a, b) {
  return `${xText(model, a)} … ${xText(model, b)}${model.unit && model.unit !== 'fraction' ? ` ${model.unit}` : ''}`;
}

/** The tooltip of one D4 class. */
function featureClassTip(payload, s, quantity) {
  const lines = [`<b>${escapeHtml(s.label)}</b>: ${formatInt(s.n)} event${s.n === 1 ? '' : 's'}`
    + `${Number.isFinite(s.n_in_range) && s.n_in_range !== s.n ? `, ${formatInt(s.n_in_range)} inside the axis` : ''}`];
  if (s.draw === 'histogram') {
    lines.push(quantity === 'count'
      ? mutedLine('events per bin (the notebook\'s stat=count)')
      : mutedLine(`density histogram: count / (N · bin width), from zero (${escapeHtml(payload.y_axis?.density ?? '')})`));
  }
  if (s.kde) lines.push(mutedLine(`Gaussian KDE, bandwidth ${num(s.kde.bandwidth)}: ${s.kde.rule ?? ''}`));
  if (s.message) lines.push(mutedLine(s.message));
  if (s.n_floored) lines.push(mutedLine(`${formatInt(s.n_floored)} value${s.n_floored === 1 ? '' : 's'} floored at 10⁻⁶ mm by the producer: counted, piled in the lowest bin`));
  if (s.n_excluded_eps) lines.push(mutedLine(`${formatInt(s.n_excluded_eps)} floored value${s.n_excluded_eps === 1 ? '' : 's'} left out`));
  if (s.n_nonpositive) lines.push(mutedLine(`${formatInt(s.n_nonpositive)} non-positive value${s.n_nonpositive === 1 ? '' : 's'}: no logarithm, counted and left out`));
  if (s.n_below || s.n_above) lines.push(mutedLine(`${formatInt(s.n_below)} below and ${formatInt(s.n_above)} above the axis (counted, not drawn)`));
  return lines.join('<br/>');
}

/**
 * The D4 model: one entry per momentum class. Pure; `opts.quantity` is
 * 'density' (default) or 'count'.
 */
export function featureHistModel(payload, opts = {}) {
  const axis = payload.axis ?? {};
  const quantity = opts.quantity === 'count' ? 'count' : 'density';
  const edges = axis.edges ?? [];
  const width = edges.length > 1 ? edges[1] - edges[0] : 1;
  const list = payload.series ?? [];
  const colours = seriesStops(opts.palette ?? 'viridis', Math.max(1, list.length));
  const labels = new Map((payload.classes ?? []).map((c) => [c.index, c.label]));
  const curveX = payload.curve_x ?? [];
  const circular = axis.scale === 'circular';
  const entries = list.map((s, k) => {
    const label = s.label ?? labels.get(s.index) ?? `class ${s.index}`;
    const counts = s.draw === 'histogram' && Array.isArray(s.counts) && s.counts.length ? s.counts : null;
    const hist = counts ? counts.map((c) => (quantity === 'count' ? c : c * (s.density_scale ?? 0))) : null;
    const pdf = s.kde?.pdf ?? null;
    const curve = pdf && curveX.length === pdf.length
      ? curveX.map((x, i) => [x, quantity === 'count' ? pdf[i] * s.n * width : pdf[i]]) : null;
    const strip = s.draw !== 'histogram' && Array.isArray(s.strip) ? s.strip : null;
    const entry = { ...s, label };
    return {
      key: s.index, label, colour: colours[k], dash: null, n: s.n,
      hist, curve, curveDrives: Boolean(s.drives_scale), strip, stripTruncated: false,
      markers: null, band: Boolean(strip?.length), none: s.draw === 'none' || (!hist && !curve && !strip?.length),
      below: s.n_below ?? 0, above: s.n_above ?? 0, message: s.message ?? '',
      tip: featureClassTip(payload, entry, quantity),
      curveName: 'Gaussian KDE',
    };
  });
  const yMax = payload.y_max?.[quantity];
  const unit = axis.unit ?? '';
  const feature = (payload.features ?? []).find((f) => f.id === payload.feature) ?? {};
  const unitText = unit ? ` [${unit}]` : '';
  const log = axis.log10 ? ' (log₁₀ axis)' : '';
  return {
    kind: 'feature', quantity, lo: axis.lo, hi: axis.hi, edges, unit, log10: Boolean(axis.log10), circular,
    xNames: [`${axis.label ?? feature.label ?? payload.feature}${unitText}${log}`, `${payload.feature}${unitText}${log}`],
    xProvisional: Boolean(axis.provisional), xInterval: circular ? Math.PI / 2 : (axis.interval ?? undefined),
    xFormatter: axis.log10 ? (v) => logTick(10 ** Number(v)) : (circular ? piLabel : tickLabel),
    yMax: Number.isFinite(yMax) && yMax > 0 ? roundTop(yMax * 1.05) : null,
    provisional: Boolean(payload.y_max?.provisional),
    yNames: quantity === 'count'
      ? ['Events per bin']
      : [`Probability density${densityUnit(unit, axis.log10)}`, 'Probability density'],
    entries, rules: [], noun: 'events',
  };
}

/** The circular sentences of an azimuth residual: mean direction with its interval, R̄, circular SD. */
export function circularResidualLines(r, s) {
  const c = s.circular ?? {};
  const unit = r.unit && r.unit !== 'fraction' ? ` ${r.unit}` : '';
  const lines = [];
  if (Number.isFinite(c.mean_direction)) {
    const iv = c.mean_direction_interval;
    lines.push(`circular mean direction ${num(c.mean_direction)}${unit}`
      + (iv ? `, 95% interval [${num(iv.lo)}, ${num(iv.hi)}]${unit} ${mutedLine(`(${iv.label ?? 'large-sample'}: the precision of the direction)`)}` : ''));
  }
  if (Number.isFinite(c.resultant)) {
    lines.push(`mean resultant length R̄ = ${num(c.resultant, 4)}${Number.isFinite(c.circular_sd) ? `, circular SD ${num(c.circular_sd)}${unit}` : ''} `
      + mutedLine('(the spread of the residuals on the circle)'));
  }
  const core = s.core_fit;
  if (core && Number.isFinite(core.sigma)) {
    lines.push(`Gaussian fit of the core: centre ${num(core.mu)}${unit}, width ${num(core.sigma)}${unit} over ${formatInt(core.n)} residuals `
      + mutedLine('(the core\'s shape only, not the width of the whole distribution)'));
  }
  if (s.estimates?.rmse && Number.isFinite(s.estimates.rmse.value)) {
    const e = s.estimates.rmse;
    lines.push(`RMSE ${num(e.value)}${unit}${e.interval ? `, 95% interval [${num(e.interval.lo)}, ${num(e.interval.hi)}]` : ''}`);
  }
  lines.push(mutedLine('an azimuth: no arithmetic mean, bias or σ is quoted or drawn'));
  if (c.note) lines.push(mutedLine(c.note));
  return lines;
}

/** The fit sentence of a residual series: mean with its interval, σ with its SE (and χ² and c₄ below the floor). */
function residualFitLines(r, s) {
  if (r.statistics === 'circular' || s.circular) return circularResidualLines(r, s);
  const fit = s.fit ?? {};
  const m = s.markers ?? {};
  const unit = r.unit && r.unit !== 'fraction' ? ` ${r.unit}` : '';
  const lines = [];
  if (Number.isFinite(m.mu)) {
    lines.push(`mean residual (bias) ${num(m.mu)}${unit}, 95% interval [${num(m.ci95_lo)}, ${num(m.ci95_hi)}]${unit} `
      + mutedLine(`(${s.estimates?.bias?.interval?.label ?? 'Student-t'}: the precision of the mean)`));
  }
  const sigma = sigmaText(fit, { unit });
  if (sigma) lines.push(`${sigma} ${mutedLine('(the spread of the showers)')}`);
  if (s.estimates?.rmse && Number.isFinite(s.estimates.rmse.value)) {
    const e = s.estimates.rmse;
    lines.push(`RMSE ${num(e.value)}${unit}${e.interval ? `, 95% interval [${num(e.interval.lo)}, ${num(e.interval.hi)}]` : ''}`);
  }
  if (fit.estimator_note) lines.push(mutedLine(fit.estimator_note));
  if (fit.note) lines.push(mutedLine(fit.note));
  return lines;
}

/**
 * The drawn curve's area, as a tooltip line; null without a curve (decision D-7).
 *
 * Beside a histogram the server draws the Gaussian on the bars' normalisation:
 * its area is the events it describes over the `n_in_range` the bars are divided
 * by, read back here as curve_peak · σ_core · √(2π). Below one when the ±2.5σ core
 * window cut a tail the curve does not describe; above one when events it
 * describes lie outside the axis. With no histogram it is a unit-area density.
 */
export function curveAreaLine(s, noun = 'events') {
  const peak = s?.curve_peak;
  const sigma = s?.core_fit?.sigma ?? s?.fit?.sigma_core;
  if (!Number.isFinite(peak) || !(sigma > 0) || !s?.curve?.y) return null;
  const area = peak * sigma * Math.sqrt(2 * Math.PI);
  const held = s.draw === 'histogram' ? s.histogram?.n_in_range : null;
  if (!Number.isFinite(held) || held <= 0) {
    return `curve area 1: a density of the ${formatInt(s.fit?.n)} ${noun} it was fitted to `
      + mutedLine('(no histogram shares its scale)');
  }
  if (Math.abs(area - 1) < 5e-4) {
    return `curve area 1: the Gaussian describes all ${formatInt(held)} ${noun} the histogram holds`;
  }
  if (area < 1) {
    return `area = share of ${noun} in the Gaussian core, ${formatPercent(area, 0)}: `
      + `it describes ${num(area * held, 1)} of the ${formatInt(held)} ${noun} the histogram holds `
      + mutedLine('(the core window cut a tail the curve does not describe; '
        + 'the core count is divided by 0.981, the window\'s own coverage of the Gaussian)');
  }
  return `curve area ${num(area, 3)}: the Gaussian describes ${num(area * held, 1)} ${noun}, `
    + `${formatInt(held)} of them inside the axis ${mutedLine('(the rest lie outside the histogram\'s range)')}`;
}

/** The residual model: one entry per shower. Pure; `opts.shower` is 'a' | 'b' | 'both'. */
export function residualModel(payload, opts = {}) {
  const r = payload.residual;
  const axis = r.axis;
  const edges = evenly(axis.lo, axis.hi, (axis.bins ?? axis.hist_centres?.length ?? 0) + 1);
  const all = Object.values(r.series ?? {}).filter((s) => (s.fit?.n ?? 0) > 0);
  const nShowers = all.length;
  const shown = all.filter((s) => !opts.shower || opts.shower === 'both' || s.shower === opts.shower);
  const unit = r.unit ?? '';
  const curveX = axis.curve_x ?? [];
  const entries = shown.map((s) => {
    const colour = showerColour(s.shower, nShowers);
    const hist = s.draw === 'histogram' && s.histogram?.counts ? s.histogram.counts : null;
    const ys = s.curve?.y ?? null;
    const xs = ys && curveX.length === ys.length ? curveX : (ys ? evenly(axis.lo, axis.hi, ys.length) : []);
    const curve = ys ? xs.map((x, i) => [x, ys[i]]) : null;
    const strip = s.draw !== 'histogram' ? (s.strip?.values ?? []) : null;
    const out = axis.outside?.[s.shower] ?? {};
    const circular = r.statistics === 'circular' || Boolean(s.circular);
    const head = `<b>${escapeHtml(s.label)}</b>: ${formatInt(s.fit?.n)} shower${s.fit?.n === 1 ? '' : 's'}`
      + `${hist ? `, density histogram: count / (N · bin width), from zero` : ''}`;
    return {
      key: s.shower, label: s.label, colour, dash: s.shower === 'b' && nShowers > 1 ? 'dashed' : null, n: s.fit?.n ?? 0,
      hist, curve, curveDrives: Boolean(s.drives_scale), curvePeak: s.curve_peak ?? null,
      strip, stripTruncated: Boolean(s.strip?.truncated), stripShown: s.strip?.n_shown ?? null,
      // An azimuth's residual has no mean or SD to mark, whatever a payload sends.
      markers: circular ? null : (s.markers ?? null), band: s.draw !== 'histogram',
      none: !hist && !curve && !strip?.length && !(circular ? null : s.markers),
      below: out.below ?? 0, above: out.above ?? 0, message: s.message ?? '',
      tip: [head, ...residualFitLines(r, s), ...(s.message ? [mutedLine(s.message)] : [])].join('<br/>'),
      curveName: s.core_fit ? 'Gaussian fit of the core' : 'fitted Gaussian',
      curveArea: curveAreaLine(s, 'showers'),
      circular: s.circular ?? null,
      // An azimuth's ticks carry its circular summary: it has no marker row to hold it.
      circularTip: circular ? circularResidualLines(r, s).join('<br/>') : null,
      fit: s.fit ?? {},
    };
  });
  /* The density range from the driving series only: histogram and curve peaks. */
  const peaks = [];
  for (const e of entries.filter((x) => x.curveDrives)) {
    if (e.hist) peaks.push(Math.max(0, ...e.hist.filter(Number.isFinite)));
    if (e.curve) peaks.push(Math.max(0, ...e.curve.map((p) => p[1]).filter(Number.isFinite)));
  }
  let provisional = false;
  if (!peaks.some((p) => p > 0)) {
    for (const e of entries) if (e.curve) peaks.push(Math.max(0, ...e.curve.map((p) => p[1]).filter(Number.isFinite)));
    provisional = peaks.some((p) => p > 0);
  }
  const top = Math.max(0, ...peaks);
  const unitText = unit && unit !== 'fraction' ? ` [${unit}]` : '';
  return {
    kind: 'residual', quantity: 'density', lo: axis.lo, hi: axis.hi, edges, unit, log10: false, circular: false,
    xNames: [`${r.quantity}${unitText}`, `Residual${unitText}`],
    xProvisional: Boolean(axis.provisional), xInterval: axis.interval ?? undefined, xFormatter: tickLabel,
    yMax: top > 0 ? roundTop(DENSITY_HEADROOM * top) : null,
    provisional,
    yNames: [`Probability density${densityUnit(unit)}`, 'Probability density'],
    entries,
    rules: [{
      name: 'zero residual (prediction = truth)', at: 0, label: '0',
      tooltip: `<b>zero residual</b>: prediction equals truth<br/>${mutedLine('a reference, not a measurement')}`,
    }],
    noun: 'showers',
  };
}

/** The readout of one bin: every histogram entry's height there and its count. */
function fittedReadout(model, i) {
  const e0 = model.edges[i];
  const e1 = model.edges[i + 1];
  const lines = [`<b>${escapeHtml(xSpan(model, e0, e1))}</b>`];
  let any = false;
  for (const e of model.entries) {
    if (!e.hist) continue;
    any = true;
    const v = e.hist[i];
    const count = model.quantity === 'count' ? v : (Number.isFinite(v) ? Math.round(v * e.n * (e1 - e0)) : null);
    lines.push(`<span style="color:${e.colour}">■</span> ${escapeHtml(e.label)}: `
      + `${model.quantity === 'count' ? `${formatInt(v)} ${model.noun}` : `density ${num(v, 4)} (${formatInt(count)} of ${formatInt(e.n)} ${model.noun})`}`);
  }
  if (!any) lines.push(mutedLine('no histogram is drawn at this sample size'));
  return lines.join('<br/>');
}

/**
 * The option of a fitted-density model (D4, residual). The rows of the
 * reserved band: a series below the histogram floor takes a row of event
 * ticks and, when it carries summary marks, a row for its mean, its capped
 * interval and its SD bar.
 */
function fittedOption(model, opts = {}, metrics = {}) {
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const { lo, hi, edges } = model;
  const series = [];
  const legend = [];
  const yMax = model.yMax;
  const hasDensity = Number.isFinite(yMax) && yMax > 0;
  const yTop = hasDensity ? yMax : 1;

  for (const e of model.entries) {
    legend.push(e.none ? `${e.label} (not drawn)` : e.label);
    if (e.none) series.push({ type: 'custom', name: `${e.label} (not drawn)`, silent: true, data: [], renderItem: () => null, itemStyle: { color: e.colour } });
  }

  /* ---- histograms from zero: robust series, they set the range --------- */
  for (const e of model.entries) {
    if (!e.hist || !hasDensity) continue;
    const points = [[edges[0], 0]];
    for (let i = 0; i < e.hist.length; i += 1) {
      const d = Number.isFinite(e.hist[i]) ? Math.min(e.hist[i], yTop) : 0;
      points.push([edges[i], d], [edges[i + 1], d]);
    }
    points.push([edges[e.hist.length], 0]);
    series.push(withColour({
      type: 'custom', name: e.label, silent: true, clip: true, z: 2, data: [[edges[0], 0]],
      renderItem: (params, api) => ({
        type: 'polygon', shape: { points: points.map((p) => api.coord(p)) }, style: { fill: e.colour, opacity: 0.08, stroke: 'none' },
      }),
    }, e.colour));
    series.push(withColour(customPolyline({
      name: e.label, points, color: e.colour, width: 1.4 * THEME.lineAxis, opacity: legibleOpacity(e.colour, 0.9),
      dash: e.dash, z: 3, tooltip: e.tip,
    }), e.colour));
  }

  /* ---- curves: thin and faint below the floor, clipped at the range ----- */
  for (const e of model.entries) {
    if (!e.curve || !hasDensity) continue;
    const peak = Math.max(0, ...e.curve.map((p) => p[1]).filter(Number.isFinite));
    const clipped = peak > yTop;
    const points = e.curve.filter((p) => Number.isFinite(p[1])).map((p) => [p[0], Math.min(p[1], yTop)]);
    const robust = e.curveDrives;
    const tip = `${e.tip}<br/>${mutedLine(`${e.curveName}${robust ? '' : `, from fewer than ${HISTOGRAM_FLOOR}: drawn thin and faint, never setting the axis`}`)}`
      + (e.curveArea ? `<br/>${e.curveArea}` : '')
      + (clipped ? `<br/>${mutedLine(`peak ${num(peak, 4)} lies above the axis: clipped at the caret`)}` : '');
    series.push(withColour(customPolyline({
      name: e.label, points, color: e.colour, width: (robust ? 1.6 : 1.1) * THEME.lineAxis,
      opacity: legibleOpacity(e.colour, robust ? 0.95 : 0.6), dash: e.dash, z: 4, tooltip: tip,
    }), e.colour));
    if (clipped) {
      const at = e.curve.reduce((best, p) => (p[1] > best[1] ? p : best), e.curve[0]);
      series.push(caretSeries({
        name: `${e.label} · ${e.curveName} (clipped)`, carets: [{ at: [at[0], yTop], dir: 'up', tooltip: tip }], color: e.colour,
      }));
    }
  }

  const top = legendTop(legend, plotWidthPx);
  const plotHeightPx = Math.max(60, height - top - pad.bottom);

  /* ---- the reserved band, only for the series below the histogram floor - */
  const bandEntries = model.entries.filter((e) => e.band && (e.strip?.length || e.markers));
  const captionPx = 1.6 * THEME.fontSmall;
  const rowCount = bandEntries.reduce((sum, e) => sum + (e.strip?.length ? 1 : 0) + (e.markers ? 1 : 0), 0);
  const pitch = Math.max(ROW_MIN_PX, Math.min(ROW_MAX_PX,
    (plotHeightPx * BAND_SHARE - captionPx - BAND_BASE_PX) / Math.max(1, rowCount)));
  let cursor = BAND_BASE_PX;
  const rows = bandEntries.map((e) => {
    const row = { e };
    if (e.strip?.length) { row.ticks = cursor + pitch / 2; cursor += pitch; }
    if (e.markers) { row.marker = cursor + pitch / 2; cursor += pitch; }
    return row;
  });
  const bandTop = rows.length ? cursor + captionPx : 0;
  if (rows.length) series.push(reservedBand({ lo, hi, bandTop, caption: bandCaption(plotWidthPx) }));
  for (const row of rows) addBandRow(series, model, row, { lo, hi });

  /* ---- a histogram series' mean: a rule above the band, its interval an envelope - */
  for (const e of model.entries) {
    if (e.band || !e.markers || !Number.isFinite(e.markers.mu)) continue;
    const m = e.markers;
    series.push(...referenceRule({
      name: `${e.label} · mean`, at: m.mu, lo: m.ci95_lo, hi: m.ci95_hi, xMin: lo, xMax: hi, yMax: yTop, colour: e.colour,
      liftPx: bandTop, dash: [7, 3], label: 'mean', labelDy: e.key === 'b' ? 1.4 * THEME.fontSmall : 0,
      tooltip: `${e.tip}<br/>${mutedLine('long-dashed: the mean; its two hairlines, the 95% interval of the mean (a thin envelope, not the spread); the histogram is the spread')}`,
    }));
    const carets = [];
    const tip = `${e.tip}<br/>${mutedLine('the mean or its interval lies beyond the axis')}`;
    if (m.mu < lo || (Number.isFinite(m.ci95_lo) && m.ci95_lo < lo)) carets.push({ at: [lo, yTop / 2], dir: 'left', tooltip: tip });
    if (m.mu > hi || (Number.isFinite(m.ci95_hi) && m.ci95_hi > hi)) carets.push({ at: [hi, yTop / 2], dir: 'right', tooltip: tip });
    if (carets.length) series.push(caretSeries({ name: `${e.label} · mean (clipped)`, carets, color: e.colour }));
  }

  /* ---- reference rules (the residual's zero) ------------------------------ */
  for (const rule of model.rules) {
    series.push(...referenceRule({
      name: rule.name, at: rule.at, xMin: lo, xMax: hi, yMax: yTop, colour: THEME.muted, liftPx: bandTop,
      dash: [1, 3], tooltip: rule.tooltip, z: 3,
    }));
  }

  /* ---- counts beyond the axis, per series --------------------------------- */
  const beyond = (where) => model.entries.filter((e) => (where === 'below' ? e.below : e.above) > 0);
  const listTip = (rows2, where) => `<b>${formatInt(rows2.reduce((s2, e) => s2 + (where === 'below' ? e.below : e.above), 0))} ${model.noun} ${where} the axis</b><br/>`
    + rows2.map((e) => `${escapeHtml(e.label)}: ${formatInt(where === 'below' ? e.below : e.above)}`).join('<br/>')
    + `<br/>${mutedLine('counted per series, in every statistic; not drawn')}`;
  const outside = [];
  if (beyond('below').length) outside.push({ at: [lo, 0], dir: 'left', tooltip: listTip(beyond('below'), 'below') });
  if (beyond('above').length) outside.push({ at: [hi, 0], dir: 'right', tooltip: listTip(beyond('above'), 'above') });
  if (outside.length) series.push(caretSeries({ name: 'beyond the axis', carets: outside, color: THEME.muted, liftPx: bandTop + 6 }));

  if (hasDensity && edges.length > 1 && model.entries.some((e) => e.hist)) {
    // A list over every drawn series, as C4's: it takes the explanation placement and leaves the chart.
    series.push(binHoverSeries({ name: 'bin readout', edges, tooltip: (i) => fittedReadout(model, i) }));
  }

  const prov = model.xProvisional ? ' — provisional' : '';
  const xName = fitName(model.xNames.map((n) => `${n}${prov}`), plotWidthPx);
  const yName = hasDensity ? fitName(model.yNames.map((n) => `${n}${model.provisional ? ' — provisional' : ''}`), plotHeightPx) : '';
  const xInterval = Number.isFinite(model.xInterval) ? (model.circular ? model.xInterval : coarseInterval(lo, hi, model.xInterval, plotWidthPx, THEME.fontLabel)) : undefined;
  const nothing = !model.entries.length;
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend),
    xAxis: valueAxis({ name: xName, min: lo, max: hi, formatter: model.xFormatter, ...(xInterval ? { interval: xInterval } : {}) }),
    yAxis: valueAxis({
      name: yName, min: 0, max: yTop, labels: hasDensity, split: hasDensity, interval: hasDensity ? niceInterval(yTop) : undefined,
      nameGap: 3.6 * THEME.fontLabel,
    }),
    graphic: hasDensity ? [] : [noticeGraphic(
      nothing ? 'Nothing to draw in this selection.'
        : 'No density estimate at this sample size — the individual events only; the density axis is left unlabelled',
      pad.left + plotWidthPx / 2, top + (plotHeightPx - bandTop) / 2, plotWidthPx,
    )],
    series,
  };
}

/** One band entry's marks: its events, and its SD bar, mean and capped interval. */
function addBandRow(series, model, row, { lo, hi }) {
  const { e } = row;
  const unit = model.unit && model.unit !== 'fraction' ? ` ${model.unit}` : '';
  if (row.ticks !== undefined) {
    const values = e.strip;
    const inside = values.filter((v) => v >= lo && v <= hi).map((v) => ({ x: v }));
    const below = values.filter((v) => v < lo);
    const above = values.filter((v) => v > hi);
    const truncated = e.stripTruncated ? ` (${formatInt(e.stripShown ?? values.length)} of ${formatInt(e.n)} shown)` : '';
    series.push(withColour(liftedSeries({
      name: `${e.label} (events)`,
      data: inside,
      z: 7,
      render: (d, api) => {
        const p = api.coord([d.x, 0]);
        const y = p[1] - row.ticks;
        return {
          type: 'line',
          shape: { x1: p[0], y1: y - TICK_HALF_PX, x2: p[0], y2: y + TICK_HALF_PX },
          style: { stroke: e.colour, lineWidth: 1.5, opacity: legibleOpacity(e.colour, 0.9) },
        };
      },
      tooltip: (d) => `${escapeHtml(e.label)}: one ${model.noun.replace(/s$/, '')} at ${xText(model, d.x, 4)}${unit}`
        + `<br/>${mutedLine(`one of ${formatInt(e.n)}${truncated}`)}`
        + (e.message ? `<br/>${mutedLine(e.message)}` : '')
        + (e.circularTip ? `<br/>${e.circularTip}` : '')
        + `<br/>${mutedLine(OFFSET_NOTE)}`,
    }), e.colour));
    const out = [];
    if (below.length) out.push({ at: [lo, 0], dir: 'left', tooltip: `${escapeHtml(e.label)}: ${formatInt(below.length)} below the axis<br/>${mutedLine(OFFSET_NOTE)}` });
    if (above.length) out.push({ at: [hi, 0], dir: 'right', tooltip: `${escapeHtml(e.label)}: ${formatInt(above.length)} beyond the axis<br/>${mutedLine(OFFSET_NOTE)}` });
    if (out.length) series.push(caretSeries({ name: `${e.label} (events beyond the axis)`, carets: out, color: e.colour, liftPx: row.ticks }));
  }
  const m = e.markers;
  if (row.marker === undefined || !m || !Number.isFinite(m.mu)) return;
  const sigma = sigmaText(e.fit, { unit });
  const sd = clampInterval(m.dispersion_lo, m.dispersion_hi, lo, hi);
  const sdTip = `${escapeHtml(e.label)}: <b>sample dispersion</b>, mean ± 1 SD = ${num(m.dispersion_lo)} … ${num(m.dispersion_hi)}${unit}`
    + (sigma ? `<br/>${sigma}` : '')
    + `<br/>${mutedLine(`the spread of the ${formatInt(e.n)} ${model.noun} (ddof = 1), not the precision of the mean`)}`
    + `<br/>${mutedLine(OFFSET_NOTE)}`;
  if (sd.lo !== null && sd.hi !== null && sd.hi > sd.lo) {
    series.push(liftedSeries({
      name: `${e.label} · SD band`,
      data: [{ x: m.mu }],
      z: 5,
      render: (d, api) => {
        const a = api.coord([sd.lo, 0]);
        const b = api.coord([sd.hi, 0]);
        return dispersionBar(a[0], b[0], a[1] - row.marker, SD_BAND_PX, e.colour);
      },
      tooltip: () => sdTip,
    }));
  }
  const ci = clampInterval(m.ci95_lo, m.ci95_hi, lo, hi);
  const meanTip = `${escapeHtml(e.label)}: <b>mean with its 95% confidence interval</b>`
    + `<br/>mean ${num(m.mu)}${unit}, 95% interval ${num(m.ci95_lo)} … ${num(m.ci95_hi)}${unit} ${mutedLine(`(Student-t, ν = ${formatInt((e.n ?? 1) - 1)})`)}`
    + (sigma ? `<br/>${sigma}` : '')
    + (ci.cutLo || ci.cutHi ? `<br/>${mutedLine('the interval extends past the axis; the values above are its true ends')}` : '')
    + `<br/>${mutedLine('the precision of the mean, not the spread')}`
    + `<br/>${mutedLine(OFFSET_NOTE)}`;
  if (ci.lo !== null && ci.hi !== null) {
    series.push(customWhiskers({
      name: `${e.label} · mean 95% interval`,
      points: [[0, ci.lo, ci.hi, { caps: ci.caps }]],
      horizontal: true, offsetPx: row.marker, capPx: CAP_PX, color: e.colour, width: 1.4 * THEME.lineAxis, z: 8,
      tooltip: () => meanTip,
    }));
  }
  const inside = m.mu >= lo && m.mu <= hi;
  if (inside) {
    series.push(liftedSeries({
      name: `${e.label} · mean`,
      data: [{ x: m.mu }],
      z: 9,
      render: (d, api) => {
        const p = api.coord([d.x, 0]);
        return { type: 'circle', shape: { cx: p[0], cy: p[1] - row.marker, r: 3 }, style: { fill: e.colour } };
      },
      tooltip: () => meanTip,
    }));
  }
  const carets = [];
  if (ci.cutLo || sd.cutLo || (!inside && m.mu < lo)) carets.push({ at: [lo, 0], dir: 'left', tooltip: meanTip });
  if (ci.cutHi || sd.cutHi || (!inside && m.mu > hi)) carets.push({ at: [hi, 0], dir: 'right', tooltip: meanTip });
  if (carets.length) series.push(caretSeries({ name: `${e.label} · mean (clipped)`, carets, color: e.colour, liftPx: row.marker }));
}

/**
 * The D4 option. Pure: `opts` = {palette, quantity?: 'density' | 'count',
 * tooltipPosition?}; `metrics` = {width, height}.
 */
export function featureHistOption(payload, opts = {}, metrics = {}) {
  return fittedOption(featureHistModel(payload, opts), opts, metrics);
}

/**
 * The residual-histogram option of a prediction-density response. Pure:
 * `opts` = {shower?: 'a' | 'b' | 'both', tooltipPosition?}.
 */
export function residualOption(payload, opts = {}, metrics = {}) {
  return fittedOption(residualModel(payload, opts), opts, metrics);
}

export class DistributionPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'distribution', aspect });
  }

  /** C4, or on Page 2 a D4 feature histogram or the residual histogram, by the payload's shape. */
  buildOption({ payload, opts = {}, metrics }) {
    if (isFeatureHist(payload)) return { option: featureHistOption(payload, opts, metrics) };
    if (isResidual(payload)) return { option: residualOption(payload, opts, metrics) };
    return { option: distributionOption(payload, opts, metrics) };
  }
}
