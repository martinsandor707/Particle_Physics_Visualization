/* C11: the share of events with no primary-tagged hit, per momentum bin.
 *
 * `/api/primaries` ships, per producer momentum bin, the number of selected
 * events `n`, how many hold no hit row with is_secondary = 0 (`k`), the
 * fraction k / n and its 95% Wilson score interval, plus the same for the
 * whole selection (`overall`). An event is the unit, so the fraction is a
 * proportion of independent trials.
 *
 * ## A point and its Wilson whisker
 *
 * Each bin is a point at its fraction with a capped, asymmetric whisker: the
 * Wilson interval, the uncertainty of the plotted proportion (CLAUDE.md
 * section 2). It is quoted from N = 1, where it is honestly wide; the Wald
 * interval, which collapses at k = 0 or k = n, is never used. The y axis is
 * the whole 0-100% scale a proportion can take, so nothing is ever clipped
 * and a bin's interval is read against the full range. The selection's
 * overall fraction is a dotted rule across the bins; its own Wilson interval
 * is in its tooltip, not drawn, so the rule does not read as a band of
 * dispersion.
 *
 * The x axis is the incident momentum in GeV: bin k is [k, k + 1), its point
 * at the centre, so an empty bin is a visible gap.
 */

import { THEME, axisPadding, formatInt, formatPercent } from '../scale.js';
import { customWhiskers, customLine } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, withColour, emptyChartOption,
  legibleOpacity,
} from './chart_panel.js';

/** A bin below this many events carries a "wide interval" note (the server's own figure). */
export const WIDE_BELOW_N = 20;

const pc = (v, d = 1) => formatPercent(v, d);

/** The bins of the response as points: {bin, label, n, k, fraction, lo, hi, x, x0, x1}. */
export function rateBins(payload) {
  const b = payload?.by_bin ?? {};
  const bins = b.bin ?? [];
  return bins.map((bin, i) => ({
    bin, label: b.label?.[i] ?? `${bin}–${bin + 1} GeV`, n: b.n?.[i] ?? 0, k: b.k?.[i] ?? 0,
    fraction: b.fraction?.[i] ?? null, lo: b.lo?.[i] ?? null, hi: b.hi?.[i] ?? null,
    x: bin + 0.5, x0: bin, x1: bin + 1,
  })).filter((p) => p.n > 0);
}

/** The tooltip of one bin. */
export function rateTip(p, payload) {
  const method = payload?.overall?.interval?.label ?? '95% Wilson score interval';
  return [
    `<b>${escapeHtml(p.label)}: ${pc(p.fraction)} of events have no primary-tagged hit</b>`,
    `${formatInt(p.k)} of ${formatInt(p.n)} event${p.n === 1 ? '' : 's'}`,
    `${escapeHtml(method)} [${pc(p.lo)}, ${pc(p.hi)}] ${mutedLine('(the uncertainty of the fraction, events being independent)')}`,
    ...(p.n < WIDE_BELOW_N ? [mutedLine(`fewer than ${WIDE_BELOW_N} events: the interval is correspondingly wide`)] : []),
  ].join('<br/>');
}

/** The tooltip of the overall rule: its value and its interval. */
export function overallTip(payload) {
  const o = payload?.overall ?? {};
  const ci = o.interval ?? {};
  return [
    `<b>Whole selection: ${pc(o.fraction)} of events have no primary-tagged hit</b>`,
    `${formatInt(o.n_no_primary)} of ${formatInt(o.n_events)} events`,
    `${escapeHtml(ci.label ?? '95% interval')} [${pc(ci.lo)}, ${pc(ci.hi)}]`,
    mutedLine('the dotted rule; its interval is quoted here, not drawn'),
  ].join('<br/>');
}

/**
 * The C11 option. Pure: `opts` = {tooltipPosition?}; `metrics` = {width,
 * height}. y in percent, 0-100.
 */
export function ratesOption(payload, opts = {}, metrics = {}) {
  const points = rateBins(payload);
  if (!points.length) return emptyChartOption(opts, metrics, 'No events in this selection.');
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 320;
  const plotW = Math.max(80, width - pad.left - pad.right);
  const plotH = Math.max(60, height - pad.top - pad.bottom);
  const colour = THEME.accent;
  const xMin = Math.min(...points.map((p) => p.x0));
  const xMax = Math.max(...points.map((p) => p.x1));
  const series = [];

  const withCi = points.filter((p) => Number.isFinite(p.lo) && Number.isFinite(p.hi));
  series.push(customWhiskers({
    name: 'Wilson 95% interval',
    points: withCi.map((p) => [p.x, 100 * p.lo, 100 * p.hi, { point: p }]),
    capPx: 4,
    color: colour,
    width: 1.2 * THEME.lineAxis,
    z: 6,
    tooltip: (d) => rateTip(d.point, payload),
  }));
  series.push(withColour({
    type: 'custom',
    name: 'Fraction without a primary',
    clip: true,
    z: 8,
    data: points.map((p, index) => [p.x, 100 * p.fraction, index]),
    renderItem: (params, api) => {
      const p = points[params.dataIndex];
      const c = api.coord([p.x, 100 * p.fraction]);
      return { type: 'circle', shape: { cx: c[0], cy: c[1], r: 3.5 }, style: { fill: colour, stroke: THEME.card, lineWidth: 1 } };
    },
    tooltip: { formatter: (prm) => rateTip(points[prm.dataIndex], payload) },
  }, colour));
  const o = payload?.overall ?? {};
  if (Number.isFinite(o.fraction)) {
    series.push(customLine({
      name: 'Whole selection',
      from: [xMin, 100 * o.fraction],
      to: [xMax, 100 * o.fraction],
      color: THEME.muted,
      width: THEME.lineAxis,
      opacity: legibleOpacity(THEME.muted, 1),
      dash: [2, 3],
      z: 4,
      tooltip: overallTip(payload),
    }));
  }
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top: pad.top + THEME.fontLabel, bottom: pad.bottom },
    xAxis: valueAxis({
      name: fitName(['Incident momentum p [GeV]', 'p [GeV]'], plotW), min: xMin, max: xMax,
      interval: xMax - xMin > 12 ? 2 : 1,
    }),
    yAxis: valueAxis({
      name: fitName(['Events with no primary-tagged hit [%]', 'No primary [%]'], plotH),
      min: 0, max: 100, interval: 20, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

export class RatesPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'rates', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: ratesOption(payload, opts, metrics) };
  }
}
