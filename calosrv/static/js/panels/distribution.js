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
 */

import { THEME, axisPadding, formatNumber, formatInt, formatSci, formatPercent, typographic } from '../scale.js';
import { legendRows } from '../textfit.js';
import { customPolyline, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries, seriesStops, niceCeil,
  niceInterval, withColour, chartLegend, FINE_STEPS,
} from './chart_panel.js';

/** A series below this many showers is drawn dashed (CLAUDE.md histogram floor). */
export const SHAPE_FLOOR_SHOWERS = 15;

const num = (v, d = 3) => formatNumber(v, d);

/** Tick labels of a full-period azimuth axis. */
function piLabel(value) {
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

export class DistributionPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'distribution', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: distributionOption(payload, opts, metrics) };
  }
}
