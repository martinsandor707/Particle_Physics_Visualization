/* C7: the longitudinal and radial energy profiles of the selected showers.
 *
 * One `/api/profiles` response carries both axes - depth (`w` in the Local
 * frame, or `kt`, each shower's own native layers, with `depth=native`) and
 * the transverse radius `r` (ρ) - so the two cards share one request and each
 * draws one axis (`opts.axis`: 'depth' | 'w' | 'kt' | 'r').
 *
 * ## Four marks, four quantities (CLAUDE.md section 2)
 *
 *   Per-shower mean          solid step line: every shower weighs the same.
 *                            The primary line; at N = 1 that shower's own profile.
 *   SD band                  uncapped shaded band, mean ± sample SD (ddof = 1):
 *                            where individual showers lie. A dispersion, so no caps.
 *   95% Student-t envelope   thin capped whiskers at the bin centres: how well
 *                            the mean is known (cluster-robust when both showers
 *                            of an event are pooled). A capped mark, so an interval.
 *   Pooled ratio of sums     dashed step line, the notebook's estimator, with its
 *                            own capped 95% interval; energy-weighted, so a
 *                            different number from the mean. Drawn from N = 2.
 *
 * Which marks exist is the server's call (`marks[].drawn`): the band and the
 * envelope from N = 2, the pooled line from N = 2 (at N = 1 it equals the
 * shower's own profile and is not drawn twice). Nothing withheld is drawn.
 *
 * ## The y range follows the two lines
 *
 * The server sets `y` from the mean and the pooled line only, zero-based.
 * Band and intervals that leave it are clipped at the axis and get a caret at
 * every over/under index the payload lists, their true values in the tooltip
 * and readout, and a count in the Details drawer. A band that dips below zero
 * (mean − SD of a non-negative fraction) is cut at the axis the same way. The
 * axis name says "provisional" when the server does (N < 20), and the
 * ensemble's low-N label ("single shower, not an ensemble", "weak (N = n)",
 * "1 d.o.f.") is written on the plot as the payload gives it.
 *
 * x is in cm, as the notebook and the "% per cm" y unit are; the readout adds
 * millimetres. On the w axis the shower's entry point w = 0 is a dashed rule.
 */

import { THEME, axisPadding, formatNumber, formatInt, formatPercent } from '../scale.js';
import { legendRows } from '../textfit.js';
import { customBand, customPolyline, customLine, customWhiskers, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries,
  clampInterval, showerColour, withColour, legibleOpacity, chartLegend, EDGE_DASH,
} from './chart_panel.js';

/** Legend text of each mark: short, the full name lives in the tooltip and drawer. */
const SHORT = {
  mean: 'Per-shower mean',
  pooled: 'Pooled ratio of sums',
  band: 'SD band',
  envelope: '95% t envelope',
};

/**
 * Legend icons drawn as the marks are: a shaded block for the uncapped band,
 * a capped whisker for the envelope, a solid and a dashed line for the two
 * estimators. The three accent-coloured marks would otherwise share one swatch.
 */
const ICON = {
  [SHORT.band]: 'rect',
  [SHORT.envelope]: 'path://M0,0h10v1.5h-10z M4.25,0h1.5v10h-1.5z M0,8.5h10v1.5h-10z',
  [SHORT.mean]: 'path://M0,4h10v2.4h-10z',
  [SHORT.pooled]: 'path://M0,4h2.6v2h-2.6z M3.7,4h2.6v2h-2.6z M7.4,4h2.6v2h-2.6z',
};

/** Pixel separation of the envelope and the pooled interval at one bin centre. */
const INTERVAL_OFFSET_PX = 2;

const MM_PER_CM = 10;

/** Axis names between the server's full label and the bare symbol, for narrow figures. */
const MID_NAME = {
  w: 'Depth w (Local frame)',
  kt: 'Δz, native layers from the first',
  r: 'Transverse radius ρ (Local frame)',
};

/** The payload's axis key a card draws: depth is `w` or `kt`, whichever is present. */
export function profileAxisKey(payload, axis = 'depth') {
  const axes = payload?.axes ?? {};
  if (axis === 'r') return axes.r ? 'r' : null;
  if ((axis === 'w' || axis === 'kt') && axes[axis]) return axis;
  if (axes.w) return 'w';
  if (axes.kt) return 'kt';
  return null;
}

/** The marks the server drew, by key. */
function drawnMarks(payload) {
  const out = {};
  for (const mark of payload?.marks ?? []) out[mark.key] = mark;
  return out;
}

/** Contiguous runs of bins with a finite value. */
function finiteRuns(values) {
  const runs = [];
  let start = null;
  for (let i = 0; i <= values.length; i += 1) {
    const ok = i < values.length && Number.isFinite(values[i]);
    if (ok && start === null) start = i;
    if (!ok && start !== null) { runs.push([start, i - 1]); start = null; }
  }
  return runs;
}

/** Step-line points of `values` over `edges` for bins first..last. */
function stepPoints(edges, values, first, last) {
  const points = [];
  for (let i = first; i <= last; i += 1) {
    points.push([edges[i], values[i]], [edges[i + 1], values[i]]);
  }
  return points;
}

const num = (v, d = 3) => formatNumber(v, d);

/** "lo … hi" with typographic signs; '—' when either end is missing. */
function span(lo, hi, digits = 3) {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return '—';
  return `${num(lo, digits)} … ${num(hi, digits)}`;
}

/**
 * The inks of one profile. A single shower, or a two-shower request for A or
 * B alone, takes its own colour (the accent for one shower). The pooled A + B
 * profile of a two-shower experiment belongs to neither shower, so it takes a
 * neutral ink - the text colour, its ratio of sums the muted grey - and never
 * the accent, which is shower B's blue on the same page.
 */
export function profileColours(payload) {
  const two = payload?.kind === 'two_shower_hits';
  if (two && (payload.shower === 'a' || payload.shower === 'b')) {
    return { colour: showerColour(payload.shower), pooledColour: THEME.text };
  }
  if (two) return { colour: THEME.text, pooledColour: THEME.muted };
  return { colour: THEME.accent, pooledColour: THEME.text };
}

/** The low-N label the server gives the ensemble, written on the plot. */
export function ensembleLabel(payload) {
  const e = payload?.ensemble ?? {};
  return [e.label, e.dof_note].filter(Boolean).join(' · ');
}

/**
 * The C7 chart option. Pure: `opts` = {axis, tooltipPosition?}, `metrics`
 * = {width, height} of the plot element. Every tip, the bin summary included,
 * takes the explanation placement: off the hovered chart.
 */
export function profileOption(payload, opts = {}, metrics = {}) {
  const key = profileAxisKey(payload, opts.axis ?? 'depth');
  const ax = key ? payload.axes[key] : null;
  const pad = axisPadding();
  const width = metrics.width || 600;
  const height = metrics.height || 360;
  const option = { ...baseOption(), tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)) };
  const nShowers = payload?.ensemble?.n_showers ?? 0;
  if (!ax || !nShowers) {
    return {
      ...option,
      grid: { left: pad.left, right: pad.right, top: pad.top, bottom: pad.bottom },
      xAxis: valueAxis({ labels: false }),
      yAxis: valueAxis({ labels: false }),
      graphic: [noticeText(ax ? 'No showers in this selection.' : 'This profile axis is not in the response.',
        width, height)],
      series: [],
    };
  }

  const marks = drawnMarks(payload);
  const edges = ax.edges_cm;
  const n = Math.max(0, edges.length - 1);
  const centres = Array.from({ length: n }, (_, i) => 0.5 * (edges[i] + edges[i + 1]));
  const y = ax.y ?? { lo: 0, hi: 1, interval: 0.2, provisional: true };
  const yLo = y.lo ?? 0;
  const yHi = y.hi;
  const { colour, pooledColour } = profileColours(payload);
  const unit = ax.value_unit ?? '% per cm';
  const series = [];
  const legend = [];

  /* ---- SD band: uncapped, clipped at the axis, a caret where cut -------- */
  const band = ax.band && marks.band?.drawn ? ax.band : null;
  if (band) {
    const lo = band.lo.map((v) => (Number.isFinite(v) ? Math.max(yLo, Math.min(v, yHi)) : null));
    const hi = band.hi.map((v) => (Number.isFinite(v) ? Math.max(yLo, Math.min(v, yHi)) : null));
    const both = lo.map((v, i) => (Number.isFinite(v) && Number.isFinite(hi[i]) ? v : null));
    for (const [first, last] of finiteRuns(both)) {
      const stations = [];
      for (let i = first; i <= last; i += 1) {
        stations.push([edges[i], lo[i], hi[i]], [edges[i + 1], lo[i], hi[i]]);
      }
      series.push(withColour(customBand({ name: SHORT.band, points: stations, color: colour, opacity: THEME.bandAlpha, z: 2 }), colour));
      // The wash is 1.4:1 against the card; the extent a reader must read is
      // its two edges, at ≥ 3:1: short dashes, thinner than the pooled line's
      // long ones, so an edge reads neither as a cap nor as an estimator.
      for (const k of [1, 2]) {
        series.push(customPolyline({
          name: SHORT.band, points: stations.map((st) => [st[0], st[k]]), color: colour, width: 0.75 * THEME.lineAxis,
          dash: EDGE_DASH, opacity: legibleOpacity(colour, 0.7), z: 2,
        }));
      }
    }
    legend.push(SHORT.band);
    const sdTip = (i, where) => `${escapeHtml(marks.band.label)} — ${where}<br/>`
      + `true range ${span(band.lo[i], band.hi[i])} ${escapeHtml(unit)} in ${binText(ax, edges, i)}<br/>`
      + mutedLine('Dispersion of the sample, not an uncertainty of the mean; clipped at the axis, not rescaled.');
    series.push(caretSeries({
      name: `${SHORT.band} (clipped)`,
      color: colour,
      opacity: legibleOpacity(colour, 0.55),
      sizePx: 4,
      carets: [
        ...(band.over ?? []).map((i) => ({ at: [centres[i], yHi], dir: 'up', tooltip: sdTip(i, 'beyond the axis top') })),
        ...(band.under ?? []).map((i) => ({ at: [centres[i], yLo], dir: 'down', tooltip: sdTip(i, 'below zero') })),
      ],
    }));
  }

  /* ---- the 95% Student-t envelope: capped, at the bin centres ----------- */
  const envelope = ax.envelope && marks.envelope?.drawn ? ax.envelope : null;
  if (envelope) {
    const label = marks.envelope.label;
    const clusterText = envelope.cluster === 'event' ? 'events as clusters' : 'each shower its own unit';
    const tip = (i) => {
      const cut = clampInterval(envelope.lo[i], envelope.hi[i], yLo, yHi);
      return `${escapeHtml(label)}<br/>${binText(ax, edges, i)}: ${span(envelope.lo[i], envelope.hi[i])} ${escapeHtml(unit)}`
        + `<br/>${mutedLine(`t = ${num(envelope.t, 4)}, ${formatInt(envelope.dof)} d.o.f., ${clusterText}`)}`
        + (cut.cutLo || cut.cutHi ? `<br/>${mutedLine('clipped at the axis; the values above are the true ends')}` : '')
        + `<br/>${mutedLine('How well the mean is known, not the spread of the showers.')}`;
    };
    const points = [];
    const carets = [];
    for (let i = 0; i < n; i += 1) {
      const cut = clampInterval(envelope.lo[i], envelope.hi[i], yLo, yHi);
      if (cut.lo === null || cut.hi === null) continue;
      points.push([centres[i], cut.lo, cut.hi, { caps: cut.caps, index: i }]);
      if (cut.cutHi) carets.push({ at: [centres[i], yHi], dir: 'up', tooltip: tip(i) });
      if (cut.cutLo) carets.push({ at: [centres[i], yLo], dir: 'down', tooltip: tip(i) });
    }
    series.push(withColour(customWhiskers({
      name: SHORT.envelope, points, color: colour, width: THEME.lineAxis, capPx: 3,
      offsetPx: -INTERVAL_OFFSET_PX, z: 8, tooltip: (datum) => tip(datum.index),
    }), colour));
    if (carets.length) {
      series.push(caretSeries({ name: `${SHORT.envelope} (clipped)`, carets, color: colour, offsetPx: -INTERVAL_OFFSET_PX }));
    }
    legend.push(SHORT.envelope);
  }

  /* ---- the per-shower mean: the primary line ----------------------------- */
  const meanTip = `${escapeHtml(marks.mean?.label ?? SHORT.mean)}<br/>${mutedLine(marks.mean?.meaning ?? '')}`
    + (ensembleLabel(payload) ? `<br/><i>${escapeHtml(ensembleLabel(payload))}</i>` : '');
  if (marks.mean?.drawn !== false) {
    for (const [first, last] of finiteRuns(ax.mean)) {
      series.push(withColour(customPolyline({
        name: SHORT.mean, points: stepPoints(edges, ax.mean, first, last),
        color: colour, width: 2 * THEME.lineAxis, z: 6, tooltip: meanTip,
      }), colour));
    }
    legend.push(SHORT.mean);
  }

  /* ---- the pooled ratio of sums, dashed, with its own capped interval ---- */
  const pooled = marks.pooled?.drawn ? ax.pooled : null;
  if (pooled) {
    const pooledTip = `${escapeHtml(marks.pooled.label)}<br/>${mutedLine(marks.pooled.meaning ?? '')}`;
    for (const [first, last] of finiteRuns(pooled.value)) {
      series.push(withColour(customPolyline({
        name: SHORT.pooled, points: stepPoints(edges, pooled.value, first, last),
        color: pooledColour, width: 1.4 * THEME.lineAxis, dash: 'dashed', z: 7, tooltip: pooledTip,
      }), pooledColour));
    }
    legend.push(SHORT.pooled);
    const tip = (i) => `${escapeHtml(marks.pooled.label)}<br/>${binText(ax, edges, i)}: `
      + `${num(pooled.value[i])} ${escapeHtml(unit)}, 95% interval ${span(pooled.ci95_lo[i], pooled.ci95_hi[i])}`
      + (pooled.label ? `<br/>${mutedLine(pooled.label)}` : '');
    const points = [];
    const carets = [];
    for (let i = 0; i < n; i += 1) {
      const cut = clampInterval(pooled.ci95_lo[i], pooled.ci95_hi[i], yLo, yHi);
      if (cut.lo === null || cut.hi === null) continue;
      points.push([centres[i], cut.lo, cut.hi, { caps: cut.caps, index: i }]);
      if (cut.cutHi) carets.push({ at: [centres[i], yHi], dir: 'up', tooltip: tip(i) });
      if (cut.cutLo) carets.push({ at: [centres[i], yLo], dir: 'down', tooltip: tip(i) });
    }
    series.push(customWhiskers({
      name: `${SHORT.pooled} 95% interval`, points, color: pooledColour, width: THEME.lineAxis,
      capPx: 3, opacity: 0.8, offsetPx: INTERVAL_OFFSET_PX, z: 8, tooltip: (datum) => tip(datum.index),
    }));
    if (carets.length) {
      series.push(caretSeries({ name: `${SHORT.pooled} 95% interval (clipped)`, carets, color: pooledColour, offsetPx: INTERVAL_OFFSET_PX }));
    }
  }

  /* ---- w = 0: the shower's entry point ----------------------------------- */
  const rule = key === 'w' ? ax.w_zero_rule : null;
  if (rule && Number.isFinite(rule.at_cm)) {
    series.push(customLine({
      name: 'w = 0 — the shower’s entry point P₀',
      from: [rule.at_cm, yLo],
      to: [rule.at_cm, yHi],
      color: THEME.muted,
      width: THEME.lineAxis,
      dash: 'dashed',
      z: 4,
      tooltip: 'w = 0 — the shower’s entry point P₀<br/>'
        + mutedLine(`Below it: ${formatPercent(rule.energy_fraction_below, 2)} of the pooled energy `
          + `(${formatPercent(rule.mean_fraction_below, 2)} by the per-shower mean)`
          + (Number.isFinite(rule.hit_level_c9) ? `; ${formatPercent(rule.hit_level_c9, 2)} in hits at w < −10⁻⁶ mm` : '')
          + '. No bin straddles it.'),
    }));
  }

  /* ---- the readout: every number of the bin under the pointer ------------ */
  series.push(binHoverSeries({
    name: 'bin readout',
    edges,
    // A bin summary, not a plain readout: every mark of the bin with its interval,
    // N and notes, often 150-230 px tall. Like every explanation it leaves the
    // hovered chart (the chart-level placement, tooltip.js), so it never covers
    // the plot it explains; only a short readout stays beside the pointer.
    tooltip: (i) => profileReadout(payload, key, i),
  }));

  /* ---- axes, legend, the low-N label -------------------------------------- */
  const wraps = THEME.legendWrap;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const rows = wraps ? Math.max(1, legendRows(legend, plotWidthPx, THEME.fontLabel, { fontFamily: THEME.fontFamily })) : 1;
  const top = pad.top + rows * 1.6 * THEME.fontLabel;
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  const provisional = Boolean(y.provisional);
  const weak = ensembleLabel(payload);
  const yName = fitName(provisional
    ? [`Energy fraction [${unit}] — provisional${weak ? `, ${weak}` : ''}`, `Energy fraction [${unit}] — provisional`,
      `[${unit}] — provisional`]
    : [`Energy fraction [${unit}]`, `[${unit}]`], plotHeightPx);
  const xName = fitName([`${ax.label} [cm]`, `${MID_NAME[key] ?? ax.symbol} [cm]`, `${ax.symbol} [cm]`], plotWidthPx);
  const graphic = weak ? [{
    type: 'text',
    silent: true,
    right: pad.right + 6,
    top: top + 4,
    style: { text: weak, fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, fontStyle: 'italic' },
  }] : [];

  return {
    ...option,
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: chartLegend(legend.map((name) => ({
      name,
      icon: ICON[name],
      ...(name === SHORT.band ? { itemStyle: { opacity: 0.45 } } : {}),
    }))),
    xAxis: valueAxis({ name: xName, min: edges[0], max: edges[n] }),
    yAxis: valueAxis({
      name: yName, min: yLo, max: yHi, interval: y.interval, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    graphic,
    series,
  };
}

/** "w 0 – 2.05 cm (0 – 20.5 mm)" for bin i. */
function binText(ax, edges, i) {
  const a = edges[i];
  const b = edges[i + 1];
  return `${escapeHtml(ax.symbol)} ${num(a, 3)} – ${num(b, 3)} cm (${num(a * MM_PER_CM, 1)} – ${num(b * MM_PER_CM, 1)} mm)`;
}

/** The per-bin readout: every mark's value at bin i, each named. */
export function profileReadout(payload, key, i) {
  const ax = payload.axes[key];
  const marks = drawnMarks(payload);
  const unit = escapeHtml(ax.value_unit ?? '% per cm');
  const lines = [`<b>${binText(ax, ax.edges_cm, i)}</b>`];
  lines.push(`Per-shower mean: ${num(ax.mean[i])} ${unit}`);
  if (ax.band && marks.band?.drawn) {
    lines.push(`SD band (sample dispersion): ${span(ax.band.lo[i], ax.band.hi[i])} ${unit}`
      + ((ax.band.over ?? []).includes(i) || (ax.band.under ?? []).includes(i) ? ' (clipped on the plot)' : ''));
  }
  if (ax.envelope && marks.envelope?.drawn) {
    lines.push(`95% t envelope of the mean: ${span(ax.envelope.lo[i], ax.envelope.hi[i])} ${unit}`);
  }
  if (marks.pooled?.drawn) {
    lines.push(`Pooled ratio of sums: ${num(ax.pooled.value[i])} ${unit}, `
      + `95% interval ${span(ax.pooled.ci95_lo[i], ax.pooled.ci95_hi[i])}`);
  }
  const reached = ax.n_present?.[i];
  if (Number.isFinite(reached)) {
    lines.push(mutedLine(`${formatInt(reached)} of ${formatInt(payload.ensemble?.n_showers)} showers deposit in this bin`));
  }
  const label = ensembleLabel(payload);
  if (label) lines.push(`<i>${escapeHtml(label)}</i>`);
  return lines.join('<br/>');
}

function noticeText(text, width, height) {
  return {
    type: 'text',
    silent: true,
    style: {
      x: width / 2,
      y: height / 2,
      text,
      textAlign: 'center',
      textVerticalAlign: 'middle',
      fill: THEME.muted,
      fontSize: THEME.fontTip,
      fontFamily: THEME.fontFamily,
    },
  };
}

/** Clipped-mark counts of one axis, for the Details drawer. */
export function profileClipCounts(payload, key) {
  return payload?.axes?.[key]?.y?.clipped ?? null;
}

export class ProfilePanel extends ChartPanel {
  /** `axis` ('depth' | 'r') is the card's default; `opts.axis` overrides it per render. */
  constructor(elementOrId, { aspect, axis = 'depth' } = {}) {
    super(elementOrId, { kind: 'profile', aspect });
    this.axis = axis;
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: profileOption(payload, { axis: this.axis, ...opts }, metrics) };
  }
}
