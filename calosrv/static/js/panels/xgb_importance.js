/* E5: the gain feature importance of the shipped booster and of its five
 * cross-validation refits.
 *
 * `/api/xgboost?view=importance&task=momentum|angle` ships every model
 * feature (52), sorted by the shipped booster's normalised gain
 * (`feature_importances_`, summing to 1), each with its frame, the raw
 * `get_score` gain, weight and cover, the five fold refits' normalised gain,
 * their mean, SD and the interval of the mean the server names
 * (`interval.label`, clipped to [0, 1], the range of a share).
 *
 * ## The bar is one model; the folds are the evidence about it
 *
 * Each feature is a row. The bar, from zero (CLAUDE.md section 2), is the
 * shipped model's share of the total gain: one booster, not an average. Under
 * it, on a line of their own, the five refits' shares are open dots - five
 * observations - and their mean is a short tick inside a thin capped bracket,
 * the 95 % interval of that mean: the uncertainty of an aggregate, named in
 * the legend and in every tooltip. The bar and the bracket never share a
 * line, so the bar cannot be read as the folds' mean, and a feature the
 * shipped model never split on but the refits did still shows its dots.
 *
 * ## Colour is the feature's frame
 *
 * The frame a feature is computed in (absolute, per-shower translated, local
 * or none, a count) is nominal, so it takes ColorBrewer's qualitative hues
 * from palette.js (`qualitativeStops`: Set2 on the dark screen, Dark2 in
 * print, the four checked colours), in the order the performance card uses
 * for the networks' frames, so absolute, translated and local read the same
 * on both cards. The legend names the frames present.
 *
 * ## How many rows
 *
 * The card's plot is a fixed 330 px (the section never moves under a late
 * card), which holds about fifteen readable rows; 52 rows would be 5 px each.
 * So the card draws the features that carry any gain - in the shipped model
 * or in any refit - up to TOP_N, in the shipped order, and counts the rest on
 * the plot: the used features beyond TOP_N, and the features no model ever
 * split on (every share exactly 0). The Details drawer lists all of them with
 * their numbers. Gain concentrates in a few features (electron momentum:
 * three features hold 70 %), so the rows past fifteen are the ones a bar
 * could not show anyway. An export draws the same rows, at a row height that
 * holds the print type.
 */

import { THEME, axisPadding, formatInt, formatPercent } from '../scale.js';
import { qualitativeStops } from '../palette.js';
import { measureText } from '../textfit.js';
import { customWhiskers } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, withColour, emptyChartOption,
  chartLegend, legendTop, niceCeil, niceInterval, FINE_STEPS, isPrintTheme, sigFigs,
} from './chart_panel.js';

/** Most feature rows the card draws. */
export const TOP_N = 15;
/** The order the frames take their hues in (as perf_bins.js SOURCE_ORDER). */
export const FRAME_ORDER = Object.freeze(['absolute', 'trans', 'local', 'none']);
export const FRAME_LABELS = Object.freeze({
  absolute: 'Absolute frame',
  trans: 'Per-shower translated',
  local: 'Local frame',
  none: 'No frame (a count)',
});

export const FOLD_NAME = 'Fold refit (5, one dot each)';
/** The envelope's legend name: the payload's interval label, as a fold-mean bracket. */
export function envelopeName(payload) {
  const label = payload?.interval?.label ?? '95% Student-t interval of the mean (4 d.o.f.)';
  return `Fold mean · ${label}`;
}
const ROW_HOVER_NAME = 'Feature readout';

const pc = (v, d = 1) => formatPercent(v, d);

/** The frame hues on the card in force: Set2 on screen, Dark2 on white paper. */
export function frameColours() {
  const hues = qualitativeStops(isPrintTheme() ? 'dark2' : 'set2', FRAME_ORDER.length);
  return Object.fromEntries(FRAME_ORDER.map((k, i) => [k, hues[i]]));
}

/** Whether a feature carries any gain, in the shipped model or in a refit. */
export function isUsed(f) {
  return (f.shipped ?? 0) > 0 || (f.folds ?? []).some((v) => (v ?? 0) > 0);
}

/* ---------------------------------------------------------------- model -- */

/**
 * The rows drawn and what is left out. Pure: `{shown: [feature], hiddenUsed:
 * [feature], unused: [feature], n, frames: [present frame keys], colours}`.
 * Null without features.
 */
export function importanceModel(payload, { topN = TOP_N } = {}) {
  const features = payload?.features;
  if (!Array.isArray(features) || !features.length) return null;
  const used = features.filter(isUsed);
  const shown = used.slice(0, topN);
  const colours = frameColours();
  return {
    shown,
    hiddenUsed: used.slice(topN),
    unused: features.filter((f) => !isUsed(f)),
    n: features.length,
    frames: FRAME_ORDER.filter((k) => shown.some((f) => (f.frame ?? 'none') === k)),
    colours,
    interval: payload.interval ?? null,
    envelope: envelopeName(payload),
  };
}

/** The sentence counting what the plot leaves out; null when nothing is. */
export function restText(model) {
  const parts = [];
  if (model.hiddenUsed.length) parts.push(`${formatInt(model.hiddenUsed.length)} more with gain`);
  if (model.unused.length) parts.push(`${formatInt(model.unused.length)} never split on (0 in every model)`);
  if (!parts.length) return null;
  return `Not drawn: ${parts.join('; ')} - listed in Details`;
}

/* ------------------------------------------------------------- tooltips -- */

/** The tooltip of one feature row. */
export function featureTip(f, model) {
  const folds = (f.folds ?? []).map((v) => pc(v, 2)).join(', ');
  const [lo, hi] = f.fold_t95 ?? [null, null];
  const lines = [
    `<b>${escapeHtml(f.name)}</b> ${mutedLine(`(${FRAME_LABELS[f.frame] ?? f.frame ?? 'no frame'})`)}`,
    `Shipped model: ${pc(f.shipped, 2)} of the total gain (rank ${formatInt(f.rank)} of ${formatInt(model.n)}) ${mutedLine('- the bar, one booster')}`,
    `raw get_score: gain ${sigFigs(f.raw?.gain, 4)} (mean per split) · weight ${sigFigs(f.raw?.weight, 4)} (splits) · cover ${sigFigs(f.raw?.cover, 4)} (mean rows per split)`,
    `fold refits: ${folds} ${mutedLine('- the dots')}`,
    `fold mean ${pc(f.fold_mean, 2)}; ${escapeHtml(model.interval?.label ?? '95% interval of the mean')} [${pc(lo, 2)}, ${pc(hi, 2)}]`
      + ` ${mutedLine('- the bracket, the uncertainty of the mean')}`,
    `SD of the folds ${pc(f.fold_sd, 2)} ${mutedLine('(their spread: the dots, not a whisker)')}`,
  ];
  if (f.clipped) lines.push(mutedLine(`the interval was clipped ${model.interval?.clip ?? 'to [0, 1], the range of a share'}`));
  return lines.join('<br/>');
}

/* --------------------------------------------------------------- layout -- */

/** The legend's names: the frames present, then the fold marks. */
export function importanceLegendNames(model, width = Infinity) {
  return [...model.frames.map((k) => FRAME_LABELS[k]), FOLD_NAME, envelopeLegend(model, width)];
}

/** The envelope's legend name at `width`: the full label where it fits a legend row, else the generic one. */
export function envelopeLegend(model, width = Infinity) {
  return fitName([model.envelope, 'Fold mean · 95% interval of the mean'], width - 2 * axisPadding().right - 26);
}

/** The grid at `width` × `height`; `height` null sizes the rows for print. */
export function importanceLayout(model, width, height = null) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const top = legendTop(importanceLegendNames(model, width), width - 2 * pad.right) + 0.4 * f;
  const labelW = Math.max(40, ...model.shown.map((x) => measureText(x.name, THEME.fontLabel, THEME.fontFamily)));
  const left = Math.min(0.45 * width, labelW + 1.2 * f);
  const rows = Math.max(1, model.shown.length);
  const restH = restText(model) ? 1.6 * f : 0;
  const gridH = height === null ? rows * 2.2 * f : Math.max(40, height - top - pad.bottom - restH);
  return {
    top,
    grid: { left, top, width: Math.max(80, width - left - pad.right), height: gridH },
    restY: top + gridH + pad.bottom + 0.2 * f,
    height: Math.ceil(height ?? top + gridH + pad.bottom + restH),
  };
}

/* --------------------------------------------------------------- option -- */

/**
 * The E5 option. Pure: `opts` = {tooltipPosition?};
 * `metrics` = {width, height}. y is the feature (inverse category), x the
 * share of the total gain in percent, from zero.
 */
export function xgbImportanceOption(payload, opts = {}, metrics = {}) {
  const model = importanceModel(payload);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no feature importances.');
  const width = metrics.width || 900;
  const height = metrics.height || 330;
  const layout = importanceLayout(model, width, height);
  const rows = model.shown;
  if (!rows.length) {
    return emptyChartOption(opts, metrics, `No feature carries any gain in the shipped model or its refits (${formatInt(model.n)} features).`);
  }
  const pitch = layout.grid.height / rows.length;
  const barH = Math.min(10, 0.36 * pitch);
  const off = Math.min(6, 0.22 * pitch);
  const values = rows.flatMap((x) => [x.shipped, ...(x.folds ?? []), ...(x.fold_t95 ?? [])]).filter(Number.isFinite);
  const xMax = Math.min(100, niceCeil(Math.max(...values, 0.01) * 100, FINE_STEPS));
  const ink = THEME.text;
  const series = [];

  series.push({
    type: 'custom',
    name: ROW_HOVER_NAME,
    clip: true,
    z: 1,
    silent: false,
    data: rows.map((x, i) => [0, i, i]),
    renderItem: (params, api) => {
      const c = api.coord([0, params.dataIndex]);
      const box = params.coordSys;
      return {
        type: 'rect',
        shape: { x: box.x, y: c[1] - pitch / 2, width: box.width, height: pitch },
        style: { fill: 'rgba(0,0,0,0)', stroke: 'none' },
      };
    },
    // A feature's summary - the bar, the dots, the bracket and the raw scores, six lines - is an
    // explanation, not a short bin readout: it leaves the chart (the chart-level placement), never
    // beside the pointer over the rows it explains (measured at 29% of the plot there).
    tooltip: { formatter: (p) => featureTip(rows[p.dataIndex], model) },
  });

  for (const frame of model.frames) {
    const colour = model.colours[frame];
    const mine = rows.map((x, i) => ({ x, i })).filter(({ x }) => (x.frame ?? 'none') === frame && Number.isFinite(x.shipped));
    series.push(withColour({
      type: 'custom',
      name: FRAME_LABELS[frame],
      clip: true,
      z: 4,
      data: mine.map(({ x, i }, k) => [100 * x.shipped, i, k]),
      renderItem: (params, api) => {
        const { x, i } = mine[params.dataIndex];
        const a = api.coord([0, i]);
        const b = api.coord([100 * x.shipped, i]);
        return {
          type: 'rect',
          shape: { x: a[0], y: a[1] - off - barH / 2, width: Math.max(0, b[0] - a[0]), height: barH },
          style: { fill: colour },
        };
      },
      tooltip: { formatter: (p) => featureTip(mine[p.dataIndex].x, model) },
    }, colour));
  }

  const dots = rows.flatMap((x, i) => (x.folds ?? []).map((v, k) => ({ x, i, k, v }))).filter((d) => Number.isFinite(d.v));
  series.push(withColour({
    type: 'custom',
    name: FOLD_NAME,
    clip: true,
    z: 7,
    data: dots.map((d, j) => [100 * d.v, d.i, j]),
    renderItem: (params, api) => {
      const d = dots[params.dataIndex];
      const c = api.coord([100 * d.v, d.i]);
      return {
        type: 'circle',
        shape: { cx: c[0], cy: c[1] + off, r: 2.4 },
        style: { fill: THEME.card, stroke: THEME.muted, lineWidth: 1.1 * THEME.lineAxis },
      };
    },
    tooltip: { formatter: (p) => featureTip(dots[p.dataIndex].x, model) },
  }, THEME.muted));

  const withCi = rows.map((x, i) => ({ x, i })).filter(({ x }) => Number.isFinite(x.fold_t95?.[0]) && Number.isFinite(x.fold_t95?.[1]));
  const envelope = customWhiskers({
    name: envelopeLegend(model, width),
    points: withCi.map(({ x, i }) => [i, 100 * x.fold_t95[0], 100 * x.fold_t95[1], { feature: x }]),
    horizontal: true,
    capPx: 3,
    color: ink,
    width: 0.8 * THEME.lineAxis,
    offsetPx: -off,
    z: 8,
    tooltip: (d) => featureTip(d.feature, model),
  });
  envelope.itemStyle = { color: ink };
  series.push(envelope);
  const means = rows.map((x, i) => ({ x, i })).filter(({ x }) => Number.isFinite(x.fold_mean));
  series.push(withColour({
    type: 'custom',
    name: envelopeLegend(model, width),
    clip: true,
    z: 9,
    data: means.map(({ x, i }, k) => [100 * x.fold_mean, i, k]),
    renderItem: (params, api) => {
      const { x, i } = means[params.dataIndex];
      const c = api.coord([100 * x.fold_mean, i]);
      return {
        type: 'line',
        shape: { x1: c[0], y1: c[1] + off - 4, x2: c[0], y2: c[1] + off + 4 },
        style: { stroke: ink, lineWidth: 1.6 * THEME.lineAxis },
      };
    },
    tooltip: { formatter: (p) => featureTip(means[p.dataIndex].x, model) },
  }, ink));

  const graphic = [];
  const rest = restText(model);
  if (rest) {
    graphic.push({
      type: 'text',
      silent: true,
      style: {
        x: layout.grid.left + layout.grid.width, y: layout.restY, textAlign: 'right',
        text: fitName([rest, `Not drawn: ${formatInt(model.hiddenUsed.length + model.unused.length)} features (Details)`], layout.grid.width),
        fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
      },
    });
  }

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    legend: chartLegend(importanceLegendNames(model, width), { left: axisPadding().right }),
    grid: layout.grid,
    xAxis: valueAxis({
      name: fitName(['Share of the total gain [%] (normalised gain)', 'Share of gain [%]'], layout.grid.width),
      min: 0, max: xMax, interval: niceInterval(xMax), split: true,
    }),
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((x) => x.name),
      axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
      axisTick: { show: false },
      axisLabel: { color: THEME.text, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily, interval: 0 },
      splitLine: { show: false },
    },
    graphic,
    series,
  };
}

export class XgbImportancePanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'xgb-importance', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: xgbImportanceOption(payload, opts, metrics) };
  }

  /** A figure with a print-legible height per row. */
  exportMetrics(width) {
    const model = importanceModel(this.lastPayload);
    if (!model || !model.shown.length) return super.exportMetrics(width);
    return { width, height: importanceLayout(model, width, null).height };
  }
}
