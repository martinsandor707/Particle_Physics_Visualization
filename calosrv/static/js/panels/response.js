/* B1, B2 and σ/μ: the sampling fraction and the relative resolution.
 *
 * One `/api/response` payload feeds three cards; `opts.mode` picks the part:
 *
 *   b1          the per-event sampling fraction f = E_dep / p of the selection
 *   b2          f against the incident momentum, per 1 GeV bin
 *   resolution  σ/μ against the incident momentum, per 1 GeV bin
 *
 * ## Two intervals, two marks (CLAUDE.md section 2)
 *
 * A capped whisker or a thin envelope is always an interval of a plotted
 * aggregate: the Student-t 95% interval of a mean (B1, B2), the cluster ratio
 * interval of the ratio of sums 1/c (B1, B2), the χ² interval of σ divided
 * by μ (σ/μ; μ's own error neglected, as the payload says). The sample SD -
 * the spread of the events - is an uncapped shaded mark with dashed edges: a
 * bar behind B1's mean marker, a box across each B2 bin (half of it each when
 * both showers are shown). They differ by √N and every tooltip names which
 * one it is. Below the core-refit floor σ is quoted with its standard error,
 * its χ² interval and c₄(N), never bare.
 *
 * ## B1: a band only below the histogram floor
 *
 * As in the energy panel, a reserved band exists only when a series is drawn
 * as its events (N < 15): a tinted band at the foot of the plot, captioned,
 * with a rule along its top edge - one axis with a reserved zone, not a second
 * scale - holding that series' event ticks, its mean with the capped interval,
 * its SD bar and its 1/c diamond with the capped interval, every tooltip
 * saying its height is a drawing offset. With no density anywhere the y axis
 * is left unlabelled and the panel says so. A series drawn as a histogram is
 * its own distribution: no band covers its tails, its mean and SD are quoted
 * in its tooltip, and its 1/c = Σ E_dep / Σ p - a different estimator from
 * the mean of the ratios - is a dotted rule from the baseline with its 95%
 * interval as a thin envelope of two hairlines.
 *
 * ## B2's 1/c
 *
 * The selection's 1/c, the calibration the energy panel applies, is a dotted
 * horizontal rule with its 95% interval - c's own, mapped to 100 / c - as a
 * capped whisker at the rule's right end, where its label is.
 *
 * ## Ranges come from the server
 *
 * B1's x range and B2's and σ/μ's y ranges are set by the robust series (or
 * bins, N ≥ 20) and are zero-based; the axis name says "provisional" where
 * the server does. A mark that leaves its range - a weak bin's whisker, a
 * 1 d.o.f. interval that would cross zero - is clipped at the axis with a
 * caret, its true values in the tooltip, and counted in the Details drawer
 * over the marks this card draws. Nothing is rescaled to fit a weak bin. A
 * part with nothing estimable says why, with no labelled scale.
 */

import { THEME, axisPadding, formatNumber, formatInt } from '../scale.js';
import { fitsWidth, wrapText } from '../textfit.js';
import { customWhiskers, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries,
  clampInterval, showerColour, withColour, niceCeil, niceInterval, FINE_STEPS, legibleOpacity, sigmaText,
  referenceRule, dispersionBar, dispersionBox, chartLegend, legendTop,
} from './chart_panel.js';

export const RESPONSE_MODES = Object.freeze(['b1', 'b2', 'resolution']);

/* Pixel geometry of B1's reserved band, above the y = 0 baseline. */
const BAND_BASE_PX = 6;
/** Row pitch of the band: shrinks toward the minimum so the band stays within BAND_SHARE of the plot. */
const ROW_MAX_PX = 11;
const ROW_MIN_PX = 7;
const BAND_SHARE = 0.32;
const TICK_HALF_PX = 4;
const SD_BAND_PX = 6;
const CAP_PX = 4;
/** Horizontal separation of two showers' marks at one momentum (px). */
const SHOWER_OFFSET_PX = 3;
/** Headroom above the tallest robust histogram bar. */
const Y_HEADROOM = 1.15;
/** Opacity of a weak bin's marks (N < 20). */
const WEAK_OPACITY = 0.6;

const BAND_CAPTIONS = [
  'summary marks — vertical positions are drawing offsets, not densities',
  'summary marks — offsets, not densities',
  'offsets, not densities',
];
const STRIP_CAPTIONS = [
  'events and summary marks — vertical positions are drawing offsets, not densities',
  'events and summary marks — offsets, not densities',
  'offsets, not densities',
];
const OFFSET_NOTE = 'vertical position is a drawing offset, not a density';

const num = (v, d = 3) => formatNumber(v, d);
const pct = (v, d = 3) => (Number.isFinite(v) ? `${formatNumber(v, d)}%` : '—');

function span(lo, hi, digits = 3, unit = '') {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return '—';
  return `${num(lo, digits)} … ${num(hi, digits)}${unit}`;
}

/** The series a card draws: one shower, or both. */
function shownOf(series, shower) {
  return (series ?? []).filter((s) => !shower || shower === 'both' || s.key === shower);
}

/** Distinct showers in a list of series, for the colour rule. */
function showerCount(series) {
  return new Set((series ?? []).map((s) => s.key)).size;
}

/** Pixel offset of a shower's marks at one momentum, when both are shown. */
function showerOffset(key, both) {
  if (!both) return 0;
  return key === 'b' ? SHOWER_OFFSET_PX : -SHOWER_OFFSET_PX;
}

function noticeGraphic(text, x, y, widthPx) {
  return {
    type: 'text',
    silent: true,
    style: {
      x,
      y,
      text: wrapText(text, Math.max(80, widthPx - 8), THEME.fontTip, THEME.fontFamily).join('\n'),
      textAlign: 'center',
      textVerticalAlign: 'middle',
      fill: THEME.muted,
      fontSize: THEME.fontTip,
      fontFamily: THEME.fontFamily,
      lineHeight: 1.45 * THEME.fontTip,
    },
  };
}

function emptyOption(opts, metrics, text) {
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  // Centred on, and wrapped inside, the empty plot area: never across its axis lines.
  const plotW = Math.max(80, width - pad.left - pad.right);
  const plotH = Math.max(40, height - pad.top - pad.bottom);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top: pad.top, bottom: pad.bottom },
    xAxis: valueAxis({ labels: false }),
    yAxis: valueAxis({ labels: false }),
    graphic: [noticeGraphic(text, pad.left + plotW / 2, pad.top + plotH / 2, plotW - 8)],
    series: [],
  };
}

/**
 * The chart option of one part of `/api/response`. Pure: `opts` =
 * {mode: 'b1' | 'b2' | 'resolution', shower?: 'a' | 'b' | 'both',
 * quantity?: 'calibrated_energy' | 'response_ratio' (resolution),
 * tooltipPosition?, readoutPosition?}; `metrics` = {width, height}.
 */
export function responseOption(payload, opts = {}, metrics = {}) {
  const mode = opts.mode ?? 'b1';
  if (mode === 'b2') return b2Option(payload, opts, metrics);
  if (mode === 'resolution') return resolutionOption(payload, opts, metrics);
  return b1Option(payload, opts, metrics);
}

/* ================================================================== B1 == */

/** The x range of B1 and whether the server calls it provisional. */
function b1Edges(axis) {
  const bins = Math.max(0, axis.bins ?? (axis.hist_centres?.length ?? 0));
  if (!bins) return [];
  return Array.from({ length: bins + 1 }, (_, i) => axis.lo + (i * (axis.hi - axis.lo)) / bins);
}

/** A custom series drawing pixel-lifted marks above the y = 0 baseline. */
function liftedSeries({ name, data, render, tooltip = null, z = 8 }) {
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    data: data.map((d, index) => [d.x, 0, index]),
    renderItem: (params, api) => render(data[params.dataIndex], api, params),
    ...(tooltip ? { tooltip: { formatter: (p) => tooltip(data[p.dataIndex], p.dataIndex) } } : {}),
  };
}

function b1Option(payload, opts, metrics) {
  const block = payload?.b1;
  if (!block) return emptyOption(opts, metrics, 'The per-event distribution is not in this response.');
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const axis = block.axis;
  const lo = axis.lo;
  const hi = axis.hi;
  const edges = b1Edges(axis);
  const nShowers = showerCount(block.series);
  const shown = shownOf(block.series, opts.shower);
  const series = [];
  const legend = [];

  /* ---- density histograms: robust (N ≥ 15), they set the y range -------- */
  const peaks = [];
  const histograms = shown.filter((s) => s.draw === 'histogram' && s.histogram);
  for (const s of histograms) {
    const colour = showerColour(s.key, nShowers);
    const density = s.histogram.density;
    const points = [[edges[0], 0]];
    for (let i = 0; i < density.length; i += 1) {
      const d = Number.isFinite(density[i]) ? density[i] : 0;
      points.push([edges[i], d], [edges[i + 1], d]);
    }
    points.push([edges[density.length], 0]);
    peaks.push(Math.max(0, ...density.filter(Number.isFinite)));
    series.push({
      type: 'custom',
      name: s.label,
      silent: true,
      clip: true,
      z: 2,
      itemStyle: { color: colour },
      data: [[edges[0], 0]],
      renderItem: (params, api) => ({
        type: 'polygon',
        shape: { points: points.map((p) => api.coord(p)) },
        style: { fill: colour, opacity: 0.08, stroke: 'none' },
      }),
    });
    series.push({
      type: 'custom',
      name: s.label,
      clip: true,
      z: 3,
      itemStyle: { color: colour },
      data: [[edges[0], 0]],
      renderItem: (params, api) => ({
        type: 'polyline',
        shape: { points: points.map((p) => api.coord(p)) },
        style: {
          fill: 'none', stroke: colour, lineWidth: 1.4 * THEME.lineAxis, opacity: legibleOpacity(colour, 0.9),
          lineDash: s.key === 'b' && nShowers > 1 ? 'dashed' : null,
        },
      }),
      tooltip: { formatter: () => histogramTip(s) },
    });
    legend.push(s.label);
  }
  const hasDensity = peaks.some((p) => p > 0);
  const yMax = hasDensity ? niceCeil(Y_HEADROOM * Math.max(...peaks), FINE_STEPS) : 1;
  const strips = shown.filter((s) => s.draw !== 'histogram' || !s.histogram);
  for (const s of strips) if (s.strip?.values?.length) legend.push(`${s.label} (events)`);
  const top = legendTop(legend, plotWidthPx);
  const plotHeightPx = Math.max(60, height - top - pad.bottom);

  /* ---- the reserved band: only for the series below the histogram floor --
   * As in the energy panel, the band exists only when strip rows need it and
   * grows with their number up to BAND_SHARE of the plot: a series drawn as a
   * histogram is its own distribution, so no band covers its tails. Each
   * strip series takes a row of events, a row for its mean and a row for 1/c. */
  const captionPx = 1.6 * THEME.fontSmall;
  const rowCount = strips.reduce((sum, s) => sum + 2 + (s.strip?.values?.length ? 1 : 0), 0);
  const pitch = Math.max(ROW_MIN_PX, Math.min(ROW_MAX_PX,
    (plotHeightPx * BAND_SHARE - captionPx - BAND_BASE_PX) / Math.max(1, rowCount)));
  let cursor = BAND_BASE_PX;
  const rows = strips.map((s) => {
    const row = { s, colour: showerColour(s.key, nShowers) };
    if (s.strip?.values?.length) { row.ticks = cursor + pitch / 2; cursor += pitch; }
    row.marker = cursor + pitch / 2;
    cursor += pitch;
    row.reference = cursor + pitch / 2;
    cursor += pitch;
    return row;
  });
  const anyTicks = rows.some((r) => r.ticks !== undefined);
  const captions = anyTicks ? STRIP_CAPTIONS : BAND_CAPTIONS;
  const caption = captions.find((c) => fitsWidth(c, plotWidthPx - 12, THEME.fontSmall, THEME.fontFamily))
    ?? captions[captions.length - 1];
  const bandTop = rows.length ? cursor + captionPx : 0;

  if (rows.length) series.push(reservedBand({ lo, hi, bandTop, caption }));
  for (const row of rows) addB1Marks(series, row, { lo, hi, yMax, nShowers });
  // A histogram series: its 1/c as a rule from the baseline, its interval a thin envelope.
  for (const s of histograms) {
    const colour = showerColour(s.key, nShowers);
    addB1Mean(series, s, { lo, hi, yMax, colour });
    addB1Reference(series, s, { lo, hi, yMax, colour });
  }

  /* ---- readout over the histogram bins ----------------------------------- */
  if (hasDensity && edges.length > 1) {
    series.push(binHoverSeries({
      name: 'bin readout',
      edges,
      position: opts.readoutPosition ?? null,
      tooltip: (i) => b1Readout(shown, edges, i),
    }));
  }

  // CLAUDE.md section 2: with no estimable density the axis is left unlabelled
  // and the panel says so, rather than naming a scale nothing is measured against.
  const yName = hasDensity ? fitName(['Probability density [%⁻¹]'], plotHeightPx) : '';
  const xName = fitName(axis.provisional
    ? ['Sampling fraction E_dep / p [%] — provisional', 'f [%] — provisional']
    : ['Sampling fraction E_dep / p [%]', 'f [%]'], plotWidthPx);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend),
    xAxis: valueAxis({ name: xName, min: lo, max: hi, interval: axis.interval }),
    yAxis: valueAxis({
      name: yName, min: 0, max: yMax, labels: hasDensity, split: hasDensity, interval: niceInterval(yMax),
      nameGap: 3.6 * THEME.fontLabel,
    }),
    graphic: hasDensity ? [] : [noticeGraphic(
      'No density estimate at this sample size — individual events and summary markers only',
      pad.left + plotWidthPx / 2, top + (plotHeightPx - bandTop) / 2, plotWidthPx,
    )],
    series,
  };
}

/** The tooltip of a B1 histogram: what it is, then its mean and SD. */
function histogramTip(s) {
  const fit = s.fit ?? {};
  const m = s.markers ?? {};
  const lines = [`${escapeHtml(s.label)}: density histogram of the per-event sampling fraction`,
    mutedLine(`counts / (N × bin width) over all N = ${formatInt(s.n)} events; ${formatInt(s.histogram.n_in_range)} inside the axis`)];
  if (Number.isFinite(m.mu)) {
    lines.push(`mean of the per-event fractions = ${pct(m.mu)}, 95% interval ${span(m.ci95_lo, m.ci95_hi, 3, '%')} `
      + mutedLine(`(Student-t, ν = ${formatInt((fit.n ?? s.n) - 1)})`));
  }
  const sigma = sigmaText(fit, { unit: '%' });
  if (sigma) lines.push(`${sigma} ${mutedLine('(sample SD, ddof = 1: the spread the histogram shows)')}`);
  lines.push(mutedLine('the mean is the long-dashed vertical with its Student-t envelope; the SD is the histogram\'s own spread, so no band is drawn over it'));
  return lines.join('<br/>');
}

/** The mean of the per-event fractions: a long-dashed rule from the baseline, its Student-t interval
 * a thin envelope. A vertical has no height on the density axis, so it needs no reserved band, and it
 * stands beside 1/c so the two estimators of one number differ visibly (3.04 % against 3.11 % on the
 * electron file). */
function addB1Mean(series, s, { lo, hi, yMax, colour }) {
  const m = s.markers ?? {};
  if (!Number.isFinite(m.mu)) return;
  const fit = s.fit ?? {};
  const tip = `${escapeHtml(s.label)}: <b>mean of the per-event fractions</b> = ${pct(m.mu)}`
    + `<br/>95% interval ${span(m.ci95_lo, m.ci95_hi, 3, '%')} ${mutedLine(`(Student-t, ν = ${formatInt((fit.n ?? s.n) - 1)}: the two hairlines, a thin envelope, the precision of the mean)`)}`
    + `<br/>${mutedLine('the notebook\'s estimator: every event weighs alike; 1/c weighs each by its momentum')}`;
  series.push(...referenceRule({
    name: `${s.label} · mean of f`, at: m.mu, lo: m.ci95_lo, hi: m.ci95_hi, xMin: lo, xMax: hi, yMax, colour,
    label: 'mean f', labelDy: (s.key === 'b' ? 1.4 : 0) * THEME.fontSmall + 2.8 * THEME.fontSmall,
    tooltip: tip, dash: [7, 3],
  }));
  const carets = [];
  if (m.mu < lo || (Number.isFinite(m.ci95_lo) && m.ci95_lo < lo)) carets.push({ at: [lo, yMax / 2], dir: 'left', tooltip: tip });
  if (m.mu > hi || (Number.isFinite(m.ci95_hi) && m.ci95_hi > hi)) carets.push({ at: [hi, yMax / 2], dir: 'right', tooltip: tip });
  if (carets.length) series.push(caretSeries({ name: `${s.label} · mean of f (clipped)`, carets, color: colour }));
}

/** 1/c of a histogram series: a dotted rule from the baseline, its 95% interval a thin envelope. */
function addB1Reference(series, s, { lo, hi, yMax, colour }) {
  const r = s.reference;
  if (!r || !Number.isFinite(r.value)) return;
  const tip = `${escapeHtml(s.label)}: <b>1/c = Σ E_dep / Σ p</b> = ${pct(r.value)}`
    + `<br/>95% interval ${span(r.ci95_lo, r.ci95_hi, 3, '%')} ${mutedLine('(the two hairlines: a thin envelope, the precision of the ratio)')}`
    + `<br/>${mutedLine(r.label ?? '')}`
    + `<br/>${mutedLine('a ratio of sums: a different number from the mean of the per-event ratios')}`;
  series.push(...referenceRule({
    name: `${s.label} · 1/c (Σ E / Σ p)`, at: r.value, lo: r.ci95_lo, hi: r.ci95_hi, xMin: lo, xMax: hi, yMax, colour,
    label: '1/c (Σ E / Σ p)', labelDy: s.key === 'b' ? 1.4 * THEME.fontSmall : 0, tooltip: tip,
  }));
  const carets = [];
  // A rule has no height, so its caret sits half-way up the edge it leaves by.
  if (r.value < lo || (Number.isFinite(r.ci95_lo) && r.ci95_lo < lo)) carets.push({ at: [lo, yMax / 2], dir: 'left', tooltip: tip });
  if (r.value > hi || (Number.isFinite(r.ci95_hi) && r.ci95_hi > hi)) carets.push({ at: [hi, yMax / 2], dir: 'right', tooltip: tip });
  if (carets.length) series.push(caretSeries({ name: `${s.label} · 1/c (clipped)`, carets, color: colour }));
}

/** The tinted, captioned band with a rule along its top edge. */
function reservedBand({ lo, hi, bandTop, caption }) {
  return {
    type: 'custom',
    name: 'reserved summary band',
    silent: true,
    clip: true,
    z: 1,
    data: [[lo, 0]],
    renderItem: (params, api) => {
      const left = api.coord([lo, 0]);
      const right = api.coord([hi, 0]);
      const top = left[1] - bandTop;
      return {
        type: 'group',
        children: [
          {
            type: 'rect',
            shape: { x: left[0], y: top, width: right[0] - left[0], height: bandTop },
            style: { fill: THEME.muted, opacity: THEME.stripAlpha },
          },
          {
            // The band's edge is read, so it is muted ink (5.3:1), not the 1.3:1 border.
            type: 'line',
            shape: { x1: left[0], y1: top, x2: right[0], y2: top },
            style: { stroke: THEME.muted, lineWidth: THEME.lineGrid, lineDash: [3, 3] },
          },
          {
            type: 'text',
            style: {
              x: left[0] + 6, y: top + 3, text: caption, fill: THEME.muted,
              fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, opacity: 0.85,
            },
          },
        ],
      };
    },
  };
}

/** One strip series' B1 marks in its band rows: events, SD band, mean and whisker, 1/c. */
function addB1Marks(series, row, { lo, hi, yMax }) {
  const { s, colour } = row;
  const label = s.label;
  const fit = s.fit ?? {};

  /* Events (strip mode): one tick each, clipped at the axis and counted. */
  if (row.ticks !== undefined) {
    const values = s.strip.values;
    const inside = values.filter((v) => v >= lo && v <= hi).map((v) => ({ x: v }));
    const below = values.filter((v) => v < lo);
    const above = values.filter((v) => v > hi);
    const truncated = s.strip.truncated
      ? ` (${formatInt(s.strip.n_shown ?? values.length)} of ${formatInt(s.n)} events shown)` : '';
    series.push(withColour(liftedSeries({
      name: `${label} (events)`,
      data: inside,
      z: 7,
      render: (d, api) => {
        const p = api.coord([d.x, 0]);
        const y = p[1] - row.ticks;
        return {
          type: 'line',
          shape: { x1: p[0], y1: y - TICK_HALF_PX, x2: p[0], y2: y + TICK_HALF_PX },
          style: { stroke: colour, lineWidth: 1.5, opacity: s.key === 'b' ? 0.7 : 0.95 },
        };
      },
      tooltip: (d) => `${escapeHtml(label)}: event sampling fraction = ${pct(d.x)}`
        + `<br/>${mutedLine(`one of ${formatInt(s.n)} individual events${truncated}`)}`
        + (s.message ? `<br/>${mutedLine(s.message)}` : '')
        + `<br/>${mutedLine(OFFSET_NOTE)}`,
    }), colour));
    const outside = [];
    if (below.length) {
      outside.push({ at: [lo, 0], dir: 'left', tooltip: `${escapeHtml(label)}: ${formatInt(below.length)} event(s) below the axis`
        + ` (${below.map((v) => pct(v)).slice(0, 8).join(', ')}${below.length > 8 ? ', …' : ''})<br/>${mutedLine(OFFSET_NOTE)}` });
    }
    if (above.length) {
      outside.push({ at: [hi, 0], dir: 'right', tooltip: `${escapeHtml(label)}: ${formatInt(above.length)} event(s) beyond the axis`
        + ` (${above.map((v) => pct(v)).slice(0, 8).join(', ')}${above.length > 8 ? ', …' : ''})<br/>${mutedLine(OFFSET_NOTE)}` });
    }
    if (outside.length) {
      series.push(caretSeries({ name: `${label} (events beyond the axis)`, carets: outside, color: colour, liftPx: row.ticks }));
    }
  }

  const m = s.markers;
  if (m && Number.isFinite(m.mu)) {
    /* SD band: the spread of the events, uncapped, behind the marker. */
    const sd = clampInterval(m.dispersion_lo, m.dispersion_hi, lo, hi);
    // σ below the core-refit floor travels with its SE, its χ² interval and c₄.
    const sigma = sigmaText(fit, { unit: '%' });
    const sdTip = `${escapeHtml(label)}: <b>sample dispersion</b>, mean ± 1 SD = ${span(m.dispersion_lo, m.dispersion_hi, 3, '%')}`
      + (sigma ? `<br/>${sigma}` : '')
      + `<br/>${mutedLine(`the spread of the ${formatInt(s.n)} events (ddof = 1), not the precision of the mean`)}`
      + `<br/>${mutedLine(OFFSET_NOTE)}`;
    if (sd.lo !== null && sd.hi !== null && sd.hi > sd.lo) {
      series.push(liftedSeries({
        name: `${label} · SD band`,
        data: [{ x: m.mu }],
        z: 5,
        render: (d, api) => {
          const a = api.coord([sd.lo, 0]);
          const b = api.coord([sd.hi, 0]);
          return dispersionBar(a[0], b[0], a[1] - row.marker, SD_BAND_PX, colour);
        },
        tooltip: () => sdTip,
      }));
    }
    const sdCarets = [];
    if (sd.cutLo) sdCarets.push({ at: [lo, 0], dir: 'left', tooltip: `${sdTip}<br/>${mutedLine('clipped at the axis')}` });
    if (sd.cutHi) sdCarets.push({ at: [hi, 0], dir: 'right', tooltip: `${sdTip}<br/>${mutedLine('clipped at the axis')}` });
    if (sdCarets.length) {
      series.push(caretSeries({
        name: `${label} · SD band (clipped)`, carets: sdCarets, color: colour, opacity: legibleOpacity(colour, 0.6), sizePx: 5, liftPx: row.marker,
      }));
    }

    /* Mean with its capped Student-t 95% interval. */
    const ci = clampInterval(m.ci95_lo, m.ci95_hi, lo, hi);
    const meanTip = `${escapeHtml(label)}: <b>mean with its 95% confidence interval</b>`
      + `<br/>mean of the per-event fractions = ${pct(m.mu)}`
      + `<br/>95% interval ${span(m.ci95_lo, m.ci95_hi, 3, '%')} `
      + mutedLine(`(Student-t, ν = ${formatInt((fit.n ?? s.n) - 1)})`)
      + (sigma ? `<br/>${sigma}` : '')
      + (ci.cutLo || ci.cutHi ? `<br/>${mutedLine('the interval extends past the axis; the values above are its true ends')}` : '')
      + `<br/>${mutedLine('the precision of the mean, not the spread of the events')}`
      + `<br/>${mutedLine(OFFSET_NOTE)}`;
    if (ci.lo !== null && ci.hi !== null) {
      series.push(customWhiskers({
        name: `${label} · mean 95% interval`,
        points: [[0, ci.lo, ci.hi, { caps: ci.caps }]],
        horizontal: true,
        offsetPx: row.marker,
        capPx: CAP_PX,
        color: colour,
        width: 1.4 * THEME.lineAxis,
        z: 8,
        tooltip: () => meanTip,
      }));
    }
    const inside = m.mu >= lo && m.mu <= hi;
    if (inside) {
      series.push(liftedSeries({
        name: `${label} · mean`,
        data: [{ x: m.mu }],
        z: 9,
        render: (d, api) => {
          const p = api.coord([d.x, 0]);
          return { type: 'circle', shape: { cx: p[0], cy: p[1] - row.marker, r: 3 }, style: { fill: colour } };
        },
        tooltip: () => meanTip,
      }));
    }
    const ciCarets = [];
    if (ci.cutLo || (!inside && m.mu < lo)) ciCarets.push({ at: [lo, 0], dir: 'left', tooltip: meanTip });
    if (ci.cutHi || (!inside && m.mu > hi)) ciCarets.push({ at: [hi, 0], dir: 'right', tooltip: meanTip });
    if (ciCarets.length) {
      series.push(caretSeries({ name: `${label} · mean (clipped)`, carets: ciCarets, color: colour, liftPx: row.marker }));
    }
  }

  /* The ratio of sums 1/c: a rule through the plot, a marker and its interval. */
  const r = s.reference;
  if (r && Number.isFinite(r.value)) {
    const refTip = `${escapeHtml(label)}: <b>1/c = Σ E_dep / Σ p</b> = ${pct(r.value)}`
      + `<br/>95% interval ${span(r.ci95_lo, r.ci95_hi, 3, '%')}`
      + `<br/>${mutedLine(r.label ?? '')}`
      + `<br/>${mutedLine('a ratio of sums: a different number from the mean of the per-event ratios')}`
      + `<br/>${mutedLine(`the diamond and its interval sit in the band: their ${OFFSET_NOTE}`)}`;
    const inside = r.value >= lo && r.value <= hi;
    if (inside) {
      series.push({
        type: 'custom',
        name: `${label} · 1/c (Σ E / Σ p)`,
        clip: true,
        z: 4,
        data: [[r.value, 0]],
        renderItem: (params, api) => {
          const base = api.coord([r.value, 0]);
          const top = api.coord([r.value, yMax]);
          return {
            type: 'group',
            children: [
              {
                type: 'line',
                shape: { x1: base[0], y1: base[1] - row.reference, x2: top[0], y2: top[1] },
                style: { stroke: colour, lineWidth: THEME.lineAxis, lineDash: [2, 3], opacity: 0.85 },
              },
              {
                type: 'polygon',
                shape: {
                  points: [[base[0], base[1] - row.reference - 4], [base[0] + 4, base[1] - row.reference],
                    [base[0], base[1] - row.reference + 4], [base[0] - 4, base[1] - row.reference]],
                },
                style: { fill: THEME.card, stroke: colour, lineWidth: 1.2 * THEME.lineAxis },
              },
              {
                type: 'text',
                style: {
                  x: top[0] + 4, y: top[1] + 2 + (s.key === 'b' ? 1.4 * THEME.fontSmall : 0), text: '1/c (Σ E / Σ p)',
                  fill: colour, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
                },
              },
            ],
          };
        },
        tooltip: { formatter: () => refTip },
      });
    }
    const rc = clampInterval(r.ci95_lo, r.ci95_hi, lo, hi);
    if (rc.lo !== null && rc.hi !== null) {
      series.push(customWhiskers({
        name: `${label} · 1/c 95% interval`,
        points: [[0, rc.lo, rc.hi, { caps: rc.caps }]],
        horizontal: true,
        offsetPx: row.reference,
        capPx: 3,
        color: colour,
        width: THEME.lineAxis,
        opacity: 0.85,
        z: 8,
        tooltip: () => refTip,
      }));
    }
    const refCarets = [];
    if (rc.cutLo || (!inside && r.value < lo)) refCarets.push({ at: [lo, 0], dir: 'left', tooltip: refTip });
    if (rc.cutHi || (!inside && r.value > hi)) refCarets.push({ at: [hi, 0], dir: 'right', tooltip: refTip });
    if (refCarets.length) {
      series.push(caretSeries({ name: `${label} · 1/c (clipped)`, carets: refCarets, color: colour, liftPx: row.reference }));
    }
  }
}

function b1Readout(shown, edges, i) {
  const lines = [`<b>f ${span(edges[i], edges[i + 1], 3, '%')}</b>`];
  for (const s of shown) {
    if (s.draw !== 'histogram' || !s.histogram) continue;
    const d = s.histogram.density[i];
    const width = edges[i + 1] - edges[i];
    const count = Number.isFinite(d) ? Math.round(d * s.n * width) : null;
    lines.push(`${escapeHtml(s.label)}: density ${num(d)} %⁻¹`
      + (count !== null ? ` (${formatInt(count)} of ${formatInt(s.n)} events)` : ''));
  }
  return lines.join('<br/>');
}

/* ================================================== momentum-bin parts == */

/** Bin edges [lo, hi] of every momentum bin a part draws. */
function binSpan(bin, b2Bins) {
  const known = b2Bins.get(bin.bin);
  if (known) return [known.lo, known.hi ?? known.lo + 1];
  if (Number.isFinite(bin.lo)) return [bin.lo, Number.isFinite(bin.hi) ? bin.hi : bin.lo + 1];
  // The producer's integer momentum bin k is [k, k + 1) GeV (README, B2 note).
  return [bin.bin, bin.bin + 1];
}

/** B2's bins by producer bin number, the edges every momentum part shares. */
function b2BinMap(payload) {
  const map = new Map();
  for (const s of payload?.b2?.series ?? []) for (const b of s.bins) if (!map.has(b.bin)) map.set(b.bin, b);
  return map;
}

/** Sorted unique edges of a list of [lo, hi] spans. */
function edgesOf(spans) {
  const set = new Set();
  for (const [a, b] of spans) { set.add(a); set.add(b); }
  return [...set].filter(Number.isFinite).sort((a, b) => a - b);
}

function momentumAxis(edges, plotWidthPx) {
  const lo = edges.length ? Math.floor(edges[0]) : 0;
  const hi = edges.length ? Math.ceil(edges[edges.length - 1]) : 20;
  return valueAxis({
    name: fitName(['Incident momentum p [GeV]', 'p [GeV]'], plotWidthPx),
    min: lo,
    max: hi,
    interval: hi - lo > 12 ? 2 : 1,
  });
}

/** A dot per bin with a pixel offset; hollow when `datum.hollow`. */
function dotSeries({ name, points, color, offsetPx, tooltip, z = 9 }) {
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    data: points.map((p, index) => [p.x, p.y, index]),
    renderItem: (params, api) => {
      const d = points[params.dataIndex];
      const c = api.coord([d.x, d.y]);
      return {
        type: 'circle',
        shape: { cx: c[0] + offsetPx, cy: c[1], r: 3.2 },
        style: d.hollow
          ? { fill: THEME.card, stroke: color, lineWidth: 1.4 * THEME.lineAxis, opacity: d.opacity ?? 1 }
          : { fill: color, opacity: d.opacity ?? 1 },
      };
    },
    tooltip: { formatter: (p) => tooltip(points[p.dataIndex]) },
  };
}

/** Marks of one value-with-interval per bin: dot, capped whisker, carets. */
function addBinPointMarks(series, { label, colour, offsetPx, items, yLo, yHi, tip }) {
  const dots = [];
  const whiskers = [];
  const carets = [];
  // A weak bin is faded, but never below the 3:1 a reader needs to see it.
  const weakOpacity = legibleOpacity(colour, WEAK_OPACITY);
  for (const it of items) {
    const opacity = it.weak ? weakOpacity : 1;
    const ci = clampInterval(it.ciLo, it.ciHi, yLo, yHi);
    if (ci.lo !== null && ci.hi !== null && ci.hi > ci.lo) {
      whiskers.push([it.x, ci.lo, ci.hi, { caps: ci.caps, opacity, item: it }]);
    }
    if (it.y >= yLo && it.y <= yHi) {
      dots.push({ x: it.x, y: it.y, hollow: it.hollow, opacity, item: it });
    }
    if (ci.cutHi || it.y > yHi) carets.push({ at: [it.x, yHi], dir: 'up', tooltip: tip(it) });
    if (ci.cutLo || it.y < yLo) carets.push({ at: [it.x, yLo], dir: 'down', tooltip: tip(it) });
  }
  series.push(customWhiskers({
    name: `${label} · 95% interval`, points: whiskers, color: colour, width: 1.2 * THEME.lineAxis,
    capPx: CAP_PX, offsetPx, z: 8, tooltip: (datum) => tip(datum.item),
  }));
  series.push(withColour(dotSeries({ name: label, points: dots, color: colour, offsetPx, tooltip: (d) => tip(d.item) }), colour));
  if (carets.length) {
    series.push(caretSeries({ name: `${label} (clipped)`, carets, color: colour, offsetPx }));
  }
}

function yAxisName(base, short, y, plotHeightPx) {
  return fitName(y?.provisional
    ? [`${base} — provisional, no bin reaches N = 20`, `${base} — provisional`, `${short} — provisional`]
    : [base, short], plotHeightPx);
}

/* ================================================================== B2 == */

function b2Option(payload, opts, metrics) {
  const block = payload?.b2;
  if (!block) return emptyOption(opts, metrics, 'The momentum-binned sampling fraction is not in this response.');
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const y = block.y;
  const nShowers = showerCount(block.series);
  const shown = shownOf(block.series, opts.shower);
  const both = shown.length > 1;
  const b2Bins = b2BinMap(payload);
  const series = [];
  const legend = [];
  const spans = [];
  const calibrations = [];
  let anyMark = false;

  shown.forEach((s, k) => {
    const colour = showerColour(s.key, nShowers);
    const offsetPx = showerOffset(s.key, both);
    const label = s.label;
    const boxes = [];
    const boxCarets = [];
    const items = [];
    for (const b of s.bins) {
      const [bLo, bHi] = binSpan(b, b2Bins);
      spans.push([bLo, bHi]);
      if (!Number.isFinite(b.mean) || !(b.n >= 1)) continue;
      const x = Number.isFinite(b.p_mean) ? b.p_mean : 0.5 * (bLo + bHi);
      const item = { x, y: b.mean, ciLo: b.ci95?.[0], ciHi: b.ci95?.[1], weak: b.weak, hollow: b.n < 2, bin: b, label };
      items.push(item);
      if (Number.isFinite(b.sd)) {
        // With both showers shown each takes its own half of the bin (A left,
        // B right), so neither spread is hidden under the other's.
        const mid = 0.5 * (bLo + bHi);
        const x0 = both && s.key === 'b' ? mid : bLo;
        const x1 = both && s.key !== 'b' ? mid : bHi;
        const sd = clampInterval(b.mean - b.sd, b.mean + b.sd, y.lo, y.hi);
        if (sd.hi > sd.lo) boxes.push({ x0, x1, lo: sd.lo, hi: sd.hi, weak: b.weak });
        const sdTip = `${escapeHtml(label)}, ${escapeHtml(b.label)}: <b>SD box</b>, mean ± 1 SD = `
          + `${span(b.mean - b.sd, b.mean + b.sd, 3, '%')}<br/>${mutedLine('sample dispersion of the events (ddof = 1), uncapped; clipped at the axis')}`;
        const centre = 0.5 * (x0 + x1);
        if (sd.cutHi) boxCarets.push({ at: [centre, y.hi], dir: 'up', tooltip: sdTip });
        if (sd.cutLo) boxCarets.push({ at: [centre, y.lo], dir: 'down', tooltip: sdTip });
      }
    }
    if (items.length) {
      legend.push(label);
      anyMark = true;
    }
    // The SD boxes: silent, named in the readout; a dashed outline carries their extent.
    series.push({
      type: 'custom',
      name: `${label} · SD box`,
      silent: true,
      clip: true,
      z: 2,
      data: boxes.map((bx, index) => [bx.x0, bx.lo, index]),
      renderItem: (params, api) => {
        const bx = boxes[params.dataIndex];
        const a = api.coord([bx.x0, bx.hi]);
        const c = api.coord([bx.x1, bx.lo]);
        // One pixel of gutter either side keeps neighbouring boxes apart.
        return dispersionBox(Math.min(a[0], c[0]) + 1, a[1], Math.max(a[0], c[0]) - 1, c[1], colour, {
          fillAlpha: THEME.bandAlpha * (bx.weak ? 0.7 : 1), edgeOpacity: bx.weak ? WEAK_OPACITY : 0.8,
        });
      },
    });
    if (boxCarets.length) {
      series.push(caretSeries({
        name: `${label} · SD box (clipped)`, carets: boxCarets, color: colour, opacity: legibleOpacity(colour, 0.6), sizePx: 5,
      }));
    }
    addBinPointMarks(series, {
      label, colour, offsetPx, items, yLo: y.lo, yHi: y.hi, tip: (it) => b2Tip(it.bin, it.label),
    });
    const cal = payload.calibration?.[s.key];
    if (cal && Number.isFinite(cal.sampling_fraction_pct)) calibrations.push({ s, cal, colour, index: k });
  });

  const edges = edgesOf(spans);
  const xHi = edges.length ? Math.ceil(edges[edges.length - 1]) : 20;
  for (const entry of calibrations) addCalibration(series, entry, { y, xHi, both, count: calibrations.length });
  series.push(binHoverSeries({
    name: 'bin readout',
    edges,
    // A bin summary, not a plain readout: every mark of the bin with its interval,
    // N and notes, often 150-230 px tall. Like every explanation it leaves the
    // hovered chart (the chart-level placement, tooltip.js), so it never covers
    // the plot it explains; only a short readout stays beside the pointer.
    tooltip: (i) => momentumReadout(shown, b2Bins, edges, i, b2Tip, (b) => b.mean),
  }));
  if (!anyMark) {
    return emptyOption(opts, metrics, 'No momentum bin holds an event of this selection: there is no sampling fraction to draw.');
  }

  const top = legendTop(legend, plotWidthPx);
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend),
    xAxis: momentumAxis(edges, plotWidthPx),
    yAxis: valueAxis({
      name: yAxisName('Sampling fraction E_dep / p [%]', 'f [%]', y, plotHeightPx),
      min: y.lo, max: y.hi, interval: y.interval, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

/** Horizontal distance (px) between the 1/c whiskers of two showers at the rule's right end. */
const CAL_WHISKER_GAP_PX = 7;

/** The sampling-fraction interval [100/c_hi, 100/c_lo] (%) of a calibration's c interval. */
export function calibrationInterval(cal) {
  const ci = cal?.ci95;
  if (!Array.isArray(ci) || !Number.isFinite(ci[0]) || !Number.isFinite(ci[1])) return null;
  return [ci[1] > 0 ? 100 / ci[1] : null, ci[0] > 0 ? 100 / ci[0] : Infinity];
}

/**
 * The selection's 1/c in B2: a dotted horizontal rule across the plot, and
 * its 95% interval - the calibration's own, mapped from c to 100/c - as a
 * capped whisker at the rule's right end, where its label is. The rule is a
 * plotted aggregate, so it never goes without its interval.
 */
function addCalibration(series, { s, cal, colour, index }, { y, xHi, both, count }) {
  const v = cal.sampling_fraction_pct;
  const interval = calibrationInterval(cal);
  const insetPx = 6 + (count - 1 - index) * CAL_WHISKER_GAP_PX;
  const labelInset = 6 + count * CAL_WHISKER_GAP_PX;
  const calTip = `${escapeHtml(s.label)}: <b>1/c = Σ E_dep / Σ p</b> over the selection = ${pct(v)}`
    + (interval ? `<br/>95% interval ${span(interval[0], interval[1], 3, '%')} `
      + mutedLine(`(100 / c over c's interval ${span(cal.ci95[0], cal.ci95[1], 2)}: the capped whisker at the rule's right end)`) : '')
    + `<br/>${mutedLine(cal.label ?? '')}`;
  if (v > y.hi || v < y.lo) {
    series.push(caretSeries({
      name: `${s.label} · 1/c (clipped)`,
      carets: [{ at: [xHi, v > y.hi ? y.hi : y.lo], dir: v > y.hi ? 'up' : 'down', tooltip: `${calTip}<br/>${mutedLine('beyond the axis: clipped, not rescaled')}` }],
      color: colour, offsetPx: -insetPx,
    }));
    return;
  }
  const opacity = legibleOpacity(colour, 0.8);
  series.push({
    type: 'custom',
    name: `${s.label} · 1/c (selection)`,
    clip: true,
    z: 4,
    data: [[0, v]],
    renderItem: (params, api) => {
      const box = params.coordSys;
      const yy = api.coord([0, v])[1];
      return {
        type: 'group',
        children: [
          { type: 'line', shape: { x1: box.x, y1: yy, x2: box.x + box.width, y2: yy },
            style: { stroke: colour, lineWidth: THEME.lineAxis, lineDash: [2, 3], opacity } },
          { type: 'text', style: { x: box.x + box.width - labelInset, y: yy - 2 - (both && s.key === 'b' ? 1.4 * THEME.fontSmall : 0),
            text: `1/c = ${pct(v)}`, textAlign: 'right', textVerticalAlign: 'bottom', fill: colour,
            fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily } },
        ],
      };
    },
    tooltip: { formatter: () => calTip },
  });
  if (!interval) return;
  const cut = clampInterval(interval[0], interval[1], y.lo, y.hi);
  if (cut.lo !== null && cut.hi !== null && cut.hi > cut.lo) {
    series.push(customWhiskers({
      name: `${s.label} · 1/c 95% interval`, points: [[xHi, cut.lo, cut.hi, { caps: cut.caps }]], color: colour,
      width: 1.2 * THEME.lineAxis, capPx: 3, offsetPx: -insetPx, z: 8, tooltip: () => calTip,
    }));
  }
  const carets = [];
  if (cut.cutHi) carets.push({ at: [xHi, y.hi], dir: 'up', tooltip: calTip });
  if (cut.cutLo) carets.push({ at: [xHi, y.lo], dir: 'down', tooltip: calTip });
  if (carets.length) series.push(caretSeries({ name: `${s.label} · 1/c interval (clipped)`, carets, color: colour, offsetPx: -insetPx }));
}

function lowNText(b) {
  const parts = [];
  if (b.dof_note) parts.push(b.dof_note);
  if (b.weak && !String(b.dof_note ?? '').startsWith('N = 1')) parts.push(`weak (N = ${formatInt(b.n)})`);
  return parts.length ? `<br/><i>${escapeHtml(parts.join(' · '))}</i>` : '';
}

/** B2's per-bin text: every number of the bin, each named. */
export function b2Tip(b, label) {
  const lines = [`<b>${escapeHtml(label)}, ${escapeHtml(b.label)}</b>, N = ${formatInt(b.n)}`];
  if (Number.isFinite(b.p_mean)) {
    lines.push(`⟨p⟩ = ${num(b.p_mean)} GeV` + (Number.isFinite(b.p_sd) ? ` (SD ${num(b.p_sd)})` : ''));
  }
  lines.push(`mean sampling fraction = ${pct(b.mean)}`);
  if (b.ci95) lines.push(`95% interval of the mean ${span(b.ci95[0], b.ci95[1], 3, '%')} ${mutedLine('(Student-t, capped whisker)')}`);
  if (Number.isFinite(b.sd)) {
    // Below the core-refit floor the SD travels with its SE, its χ² interval and c₄.
    lines.push(`SD = ${pct(b.sd)}${Number.isFinite(b.sd_se) ? ` ± ${pct(b.sd_se)} (SE)` : ''} `
      + `${mutedLine('(sample dispersion, ddof = 1: the uncapped box)')}`
      + (b.sd_ci95 ? `, χ² 95% interval ${span(b.sd_ci95[0], b.sd_ci95[1], 3, '%')}` : '')
      + (Number.isFinite(b.c4) ? `, bias factor c₄ = ${num(b.c4, 4)}` : ''));
  }
  const ros = b.ratio_of_sums;
  if (ros && Number.isFinite(ros.value)) {
    lines.push(`ratio of sums Σ E_dep / Σ p = ${pct(ros.value)}`
      + (ros.ci95 ? ` [${span(ros.ci95[0], ros.ci95[1], 3, '%')}]` : '') + ` ${mutedLine('(never calibrates)')}`);
  }
  if (Number.isFinite(b.scaling_factor)) lines.push(mutedLine(`scaling factor 1 / mean = ${num(b.scaling_factor, 4)}`));
  return lines.join('<br/>') + lowNText(b);
}

/* ========================================================== resolution == */

function resolutionOption(payload, opts, metrics) {
  const block = payload?.resolution;
  if (!block) return emptyOption(opts, metrics, 'The relative resolution is not in this response.');
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 340;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const y = block.y;
  const quantity = opts.quantity ?? 'calibrated_energy';
  const ofKind = (block.series ?? []).filter((s) => s.kind === quantity);
  const nShowers = showerCount(ofKind);
  const shown = shownOf(ofKind, opts.shower);
  const both = shown.length > 1;
  const b2Bins = b2BinMap(payload);
  const series = [];
  const legend = [];
  const spans = [];

  for (const s of shown) {
    const colour = showerColour(s.key, nShowers);
    const label = s.label;
    const items = [];
    for (const b of s.bins) {
      const [bLo, bHi] = binSpan(b, b2Bins);
      spans.push([bLo, bHi]);
      if (!Number.isFinite(b.value)) continue;
      const x = Number.isFinite(b.p_mean) ? b.p_mean : 0.5 * (bLo + bHi);
      items.push({
        x, y: b.value, ciLo: b.ci95?.[0], ciHi: b.ci95?.[1], weak: b.weak,
        hollow: b.dof_note === '1 d.o.f.', bin: b, series: s,
      });
    }
    // A series that draws nothing gets no legend entry.
    if (items.length) legend.push(label);
    addBinPointMarks(series, {
      label, colour, offsetPx: showerOffset(s.key, both), items, yLo: y.lo, yHi: y.hi,
      tip: (it) => resolutionTip(it.bin, it.series, block),
    });
  }

  if (!legend.length) {
    // No bin holds two showers: no σ/μ exists, so no scale is shown for one
    // (CLAUDE.md section 2), and the card says why rather than leaving a grid.
    const bins = shown.flatMap((s) => s.bins ?? []);
    const allOne = bins.length > 0 && bins.every((b) => (b.n ?? 0) <= 1);
    return emptyOption(opts, metrics, bins.length
      ? `No momentum bin holds two showers: σ/μ is not estimable${allOne ? ' (N = 1 in every bin)' : ''}.`
      : 'No showers in this selection: σ/μ is not estimable.');
  }

  const edges = edgesOf(spans);
  series.push(binHoverSeries({
    name: 'bin readout',
    edges,
    // A bin summary, not a plain readout: every mark of the bin with its interval,
    // N and notes, often 150-230 px tall. Like every explanation it leaves the
    // hovered chart (the chart-level placement, tooltip.js), so it never covers
    // the plot it explains; only a short readout stays beside the pointer.
    tooltip: (i) => momentumReadout(shown, b2Bins, edges, i, (b, label, s) => resolutionTip(b, s, block), (b) => b.value),
  }));

  const top = legendTop(legend, plotWidthPx);
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend),
    xAxis: momentumAxis(edges, plotWidthPx),
    yAxis: valueAxis({
      name: yAxisName('Relative resolution σ/μ [%]', 'σ/μ [%]', y, plotHeightPx),
      min: y.lo, max: y.hi, interval: y.interval, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

/** σ/μ's per-bin text: the χ² whisker, σ's own interval, the delta-method SE. */
export function resolutionTip(b, s, block) {
  const unit = s.unit === '%' ? '%' : ` ${s.unit}`;
  const lines = [`<b>${escapeHtml(s.label)}, ${escapeHtml(b.label)}</b>, N = ${formatInt(b.n)}`];
  if (Number.isFinite(b.p_mean)) lines.push(`⟨p⟩ = ${num(b.p_mean)} GeV`);
  if (Number.isFinite(b.value)) {
    lines.push(`σ/μ = ${pct(b.value, 2)}`);
    if (b.ci95) {
      lines.push(`95% interval ${span(b.ci95[0], b.ci95[1], 2, '%')} `
        + mutedLine(`(${block?.whisker?.method === 'chi2_over_mu' ? 'χ² interval of σ over μ' : 'capped whisker'}, asymmetric)`));
    }
    if (Number.isFinite(b.se_delta)) {
      lines.push(mutedLine(`delta-method SE of σ/μ, μ's error included: ${pct(b.se_delta, 2)}`));
    }
  }
  if (Number.isFinite(b.mu)) lines.push(`μ = ${num(b.mu, 4)}${unit}`);
  if (Number.isFinite(b.sigma)) {
    lines.push(`σ = ${num(b.sigma, 4)}${unit} (ddof = 1)`
      + (b.sigma_ci95 ? `, χ² 95% interval ${span(b.sigma_ci95[0], b.sigma_ci95[1], 4, unit)}` : '')
      + (Number.isFinite(b.sigma_se) ? `, SE ${num(b.sigma_se, 4)}` : ''));
  }
  if (Number.isFinite(b.c4)) lines.push(mutedLine(`bias factor c₄(N) = ${num(b.c4, 4)}`));
  if (Number.isFinite(b.momentum_spread)) {
    lines.push(mutedLine(`momentum spread in the bin σ_p/⟨p⟩ = ${pct(b.momentum_spread, 2)}`));
  }
  lines.push(mutedLine(b.non_gaussian === null || b.non_gaussian === undefined
    ? 'Gaussian shape: untestable below N = 20'
    : `Gaussian shape: ${b.non_gaussian ? 'rejected (non-Gaussian)' : 'consistent'}`));
  return lines.join('<br/>') + lowNText(b);
}

/** The readout of momentum bin i over every shown series. */
function momentumReadout(shown, b2Bins, edges, i, tip, valueOf) {
  const parts = [];
  for (const s of shown) {
    const b = s.bins.find((bin) => {
      const [a, c] = binSpan(bin, b2Bins);
      return a <= edges[i] && c >= edges[i + 1];
    });
    if (b && Number.isFinite(valueOf(b))) parts.push(tip(b, s.label, s));
    else if (b) parts.push(`<b>${escapeHtml(s.label)}, ${escapeHtml(b.label)}</b>, N = ${formatInt(b.n)}${lowNText(b)}`);
  }
  if (!parts.length) return `p ${span(edges[i], edges[i + 1], 2, ' GeV')}: no events in this bin`;
  return parts.join('<br/><br/>');
}

export class ResponsePanel extends ChartPanel {
  /** `mode` is the card's part; `opts.mode` overrides it per render. */
  constructor(elementOrId, { aspect, mode = 'b1' } = {}) {
    super(elementOrId, { kind: 'response', aspect });
    this.mode = mode;
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: responseOption(payload, { mode: this.mode, ...opts }, metrics) };
  }
}

