/* perf-momentum-bias: the Absolute-frame momentum error and bias near 5, 10 and 15 GeV.
 *
 * The payload is static (`catalog/select.js` `catalogPayload('perf-momentum-bias', …)`): the report's table
 * of the energy (momentum) network in the Absolute frame, for the muon, electron and pion. Point estimates as
 * reported, no interval (Martin's recorded exception, 2026-11-05).
 *
 * ## Paired grids, one row per species
 *
 * - Left: the MAE per window, a bar from zero in the Absolute frame's E2 hue.
 * - Right: the bias, the report's mean signed error ("signed error as reported"; the report states no sign
 *   convention, so the card never writes "prediction − truth" as a definition; the drawer notes that the
 *   report's muon reading, an estimate pulled toward the middle of the range, implies it), as a dot on an
 *   axis symmetric about zero with an explicit zero rule.
 * - Windows: 4–6 GeV is the report's stated example ("például"); 9–11 and 14–16 GeV follow the same ±1 GeV
 *   rule. Each window's n is printed under its label, as reported.
 * - The windows are computed on the whole exported model output, training split included, and n counts no
 *   independent particles for the electron and pion (Σn 77,094 and 253,659 against 40,000 particles, F6). No
 *   interval is ever built from n, and the drawer carries both hazards.
 * - Where |bias| equals the MAE to the reported precision (the muon at 5 and 15 GeV, F7) the errors of the
 *   other sign are bounded by the rounding: MAE − |bias| = (2/n)·Σ|e| over them, and two printed values that
 *   agree to `dp` decimals leave at most 10^−dp for it, so those errors average under ½·10^−dp GeV per
 *   particle of the window. (Almost) every error has one sign; the dot is a diamond labelled "one sign", and
 *   the tooltip and the drawer state the bound, never an exact implication (`oneSignText`).
 * - Every header line wraps at the chart's width, each plot's sub-title keeps a label height clear of its
 *   top tick, and the two-line window labels have the room their two lines take: the 321 px single-column
 *   export holds every text.
 * - Under Compare all each species takes its own row, its axes zero-based (MAE) or zero-centred (bias) on its
 *   own values, and the card says so. The proton has no windows: alone it draws an empty state with the
 *   reason; under Compare all a note line says so.
 *
 * No colour literal: every colour is a THEME token or the Absolute frame's E2 hue.
 */

import { THEME, axisPadding, formatInt } from '../scale.js';
import { printed } from '../catalog/select.js';
import { tooltipOption } from './tooltip.js';
import {
  baseOption, wrapTooltip, valueAxis, mutedLine, escapeHtml, emptyChartOption, withColour, legibleOpacity,
  tickLabel, fitName,
} from './chart_panel.js';
import {
  AXIS_LABEL_MARGIN, DEFAULT_WIDTH, LINE_PITCH, CatalogChartPanel, categoryAxis, frameHues, labelOf, lineGraphics,
  niceStep, niceTop, textGraphic, textInk, tipFooter, withUnit, wrapLines, zeroRuleSeries,
} from './bench_catalog.js';

/** What the bias is, in the card's words (the report states no sign convention). */
export const BIAS_NAME = 'Mean signed error as reported';

const BAR_FILL = 0.78;
const DOT_PX = 4.5;
const ROW_PLOT_PX = 130;
/** The line pitch of the two-line window labels, in label heights: their lines stack apart, in SVG too. */
export const WINDOW_LABEL_PITCH = 1.45;
const MIN_SIDE_PX = 220;

/** The window label: "4–6 GeV". */
export function windowLabel(w) {
  return `${printed(w.window?.[0])}–${printed(w.window?.[1])} GeV`;
}

/**
 * The bound behind a one-signed window (F7), as the report's rounding allows it. MAE − |bias| equals
 * (2/n)·Σ|e| over the errors of the other sign; when both print the same to `dp` decimals their true values
 * differ by at most 10^−dp, so those errors average under ½·10^−dp of the unit per particle of the window.
 * `dp` is the coarser of the two printed decimals; null without one.
 */
export function oneSignBound(w) {
  const dps = [w?.dp?.mae, w?.dp?.bias].filter(Number.isInteger);
  if (!dps.length) return null;
  const dp = Math.min(...dps);
  return { dp, value: 0.5 * 10 ** -dp, text: printed(0.5 * 10 ** -dp, dp + 1) };
}

/** The F7 sentence of a one-signed window, with the bound the rounding leaves (never "every error"). */
export function oneSignText(w, unit = 'GeV') {
  const bound = oneSignBound(w);
  const rest = bound
    ? `errors of the other sign average under ${bound.text} ${unit} per particle of the window, so (almost) every error has one sign`
    : 'so (almost) every error has one sign; the rounding bounds the rest';
  return `to the report's rounding, |bias| = MAE: ${rest}`;
}

/** The window rule of one window: stated by the report, or by the same ±1 GeV rule. */
export function windowRule(w) {
  return w.windowStated
    ? `the report's own example window for ${printed(w.centre)} GeV`
    : `by the same ±1 GeV rule; the report states the window only for 5 GeV`;
}

/** The n sentence of a window: as reported, with what it does and does not count. */
export function windowN(w, consistent) {
  const base = `n = ${formatInt(w.n)} as reported, on the whole exported output (training split included)`;
  return consistent === false
    ? `${base}; for this species the windows' n sum beyond the 40,000 particles, so n does not count independent particles`
    : `${base}; never used for an interval`;
}

/** The most ticks a bias axis may carry over its plot height: a label line and a little air apiece. */
export function maxBiasIntervals(plotPx = ROW_PLOT_PX) {
  return Math.max(2, Math.floor(plotPx / (1.7 * THEME.fontLabel)));
}

/**
 * The bias axis's tick interval: it divides the bound exactly, so 0 and ±bound are ticks, and it leaves no
 * more than `maxBiasIntervals` intervals over the axis's 2 × bound (at 0.1 on ±0.5 the print labels touched).
 */
export function biasStep(bound, plotPx = ROW_PLOT_PX) {
  const step = niceStep(bound);
  const most = maxBiasIntervals(plotPx);
  const k0 = Math.round(bound / step);
  for (let k = k0; k >= 1; k -= 1) {
    const candidate = Number((bound / k).toPrecision(12));
    const mantissa = candidate / 10 ** Math.floor(Math.log10(candidate));
    const round = Number.isInteger(Number((mantissa * 10).toPrecision(12)));
    if (2 * k <= most && round && Number.isInteger(Number((bound / candidate).toPrecision(12)))) return candidate;
  }
  return bound;
}

/**
 * Everything the chart and the drawer need, decided once. Pure:
 * {unit, rows: [{species, windows, mae: {max, interval}, bias: {bound, interval}, consistent}], notReported,
 * empty, oneSigned: [window], windowsRule}.
 */
export function benchMomentumModel(payload) {
  if (!payload || !Array.isArray(payload.windows)) return null;
  const species = [...new Set(payload.windows.map((w) => w.species))];
  const rows = species.map((s) => {
    const windows = payload.windows.filter((w) => w.species === s).sort((a, b) => a.centre - b.centre);
    const maeTop = niceTop(Math.max(...windows.map((w) => w.mae).filter(Number.isFinite), 0));
    const bound = niceTop(Math.max(...windows.map((w) => Math.abs(w.bias)).filter(Number.isFinite), 0));
    return {
      species: s,
      windows,
      mae: { max: maeTop, interval: niceStep(maeTop) },
      bias: { bound, interval: biasStep(bound) },
      consistent: payload.nConsistent?.[s] ?? null,
    };
  });
  return {
    unit: payload.unit ?? 'GeV',
    rows,
    all: (payload.species ?? []).length > 1,
    notReported: payload.notReported ?? [],
    empty: rows.length ? null : (payload.empty ?? 'The report gives no momentum windows for this species.'),
    oneSigned: payload.windows.filter((w) => w.oneSigned),
    inconsistent: rows.filter((r) => r.consistent === false).map((r) => r.species),
    note: payload.note ?? '',
  };
}

/* ============================================================== layout == */

/** The note lines over the rows, before wrapping. */
function noteLines(model, payload) {
  const lines = ['Absolute frame · windows 4–6 GeV (stated), 9–11 and 14–16 GeV (same ±1 GeV rule) · training split included'];
  if (model.all) lines.push('Each species on its own axes.');
  if (model.notReported.length && model.rows.length) {
    lines.push(`${model.notReported.map((s) => labelOf(payload, 'species', s)).join(', ')}: no momentum windows in the report.`);
  }
  return lines;
}

/**
 * Where everything goes at `width`: {lines, rows: [{row, titleX, titleY, mae, bias}], height}.
 * The two grids of a row sit side by side, or stacked when the card is narrow.
 */
export function benchMomentumLayout(model, payload, width = DEFAULT_WIDTH) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const lines = noteLines(model, payload).flatMap((line) => wrapLines(line, width - 1.2 * f));
  const top = pad.top + lines.length * LINE_PITCH * f;
  const gap = 2.4 * f;
  const side = (width - gap) / 2 - pad.left - pad.right >= MIN_SIDE_PX;
  const titleH = 1.9 * f;
  // The sub-title's line, then the top tick label's upper half above the grid's top edge.
  const subH = 2.3 * f;
  // Under a plot: the two-line window labels (window, n) at their own line pitch, then air before the next
  // sub-title or row.
  const xLabelH = AXIS_LABEL_MARGIN + 2 * WINDOW_LABEL_PITCH * f + 0.8 * f;
  const plotH = ROW_PLOT_PX;
  const cellW = side ? (width - gap) / 2 : width;
  const blockH = titleH + (side ? 1 : 2) * (subH + plotH + xLabelH);
  const rows = model.rows.map((row, i) => {
    const y = top + i * blockH;
    const grid = (k) => {
      const x = side ? k * (cellW + gap) : 0;
      const yy = side ? y + titleH : y + titleH + k * (subH + plotH + xLabelH);
      return { left: x + pad.left, top: yy + subH, width: Math.max(60, cellW - pad.left - pad.right), height: plotH, subX: x + 0.6 * f, subY: yy + 0.2 * f, subW: cellW - 1.2 * f };
    };
    return { row, titleX: 0.6 * f, titleY: y + 0.35 * f, mae: grid(0), bias: grid(1) };
  });
  return { lines, top: pad.top, side, rows, height: Math.ceil(top + model.rows.length * blockH + 0.6 * f) };
}

/** The plot height the card needs (Compare all takes a row per species). Pure. */
export function plotHeight(payload, opts = {}, width = DEFAULT_WIDTH) {
  const model = benchMomentumModel(payload);
  if (!model || !model.rows.length) return 260;
  return Math.max(240, benchMomentumLayout(model, payload, width).height);
}

/* ============================================================ tooltips == */

/** The tooltip of a window's MAE bar or bias dot. */
export function momentumTip(model, payload, row, w, which) {
  const sp = labelOf(payload, 'species', row.species);
  const head = which === 'mae'
    ? `MAE ${withUnit(printed(w.mae, w.dp?.mae), model.unit)}`
    : `${BIAS_NAME} ${withUnit(printed(w.bias, w.dp?.bias, { sign: true }), model.unit)}`;
  const lines = [`<b>${escapeHtml(sp)} · Absolute · ${escapeHtml(windowLabel(w))}: ${escapeHtml(head)}</b>`];
  lines.push(escapeHtml(which === 'mae'
    ? `${BIAS_NAME}: ${withUnit(printed(w.bias, w.dp?.bias, { sign: true }), model.unit)} (the dot beside)`
    : `MAE ${withUnit(printed(w.mae, w.dp?.mae), model.unit)} (the bar beside)`));
  if (w.oneSigned) lines.push(escapeHtml(oneSignText(w, model.unit)));
  lines.push(mutedLine(`window: ${windowRule(w)}`));
  lines.push(...tipFooter(windowN(w, row.consistent)));
  return lines.join('<br/>');
}

/* ============================================================== option == */

/** The x labels of a row's windows: the window and, on a second line, its n as reported. */
function xLabels(row) {
  return (i) => {
    const w = row.windows[i];
    return w ? `${windowLabel(w)}\nn = ${formatInt(w.n)}` : '';
  };
}

/** The perf-momentum-bias option. Pure: `opts` = {tooltipPosition?}; `metrics` = {width, height}. */
export function benchMomentumOption(payload, opts = {}, metrics = {}) {
  const model = benchMomentumModel(payload);
  if (!model) return { option: emptyChartOption(opts, metrics, 'No catalogue payload.') };
  if (model.empty) return { option: emptyChartOption(opts, metrics, model.empty) };
  const width = metrics.width || DEFAULT_WIDTH;
  const layout = benchMomentumLayout(model, payload, width);
  const colour = frameHues().absolute;
  const ink = legibleOpacity(colour, 1);
  const f = THEME.fontLabel;
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = lineGraphics(layout.lines, 0.6 * f, layout.top);

  for (const { row, titleX, titleY, mae, bias } of layout.rows) {
    const sp = labelOf(payload, 'species', row.species);
    const consistentText = row.consistent === false ? ' · n exceeds the particles' : '';
    graphic.push(textGraphic(fitName([
      `${sp} · Absolute frame${consistentText}`, `${sp} · Absolute${consistentText}`, `${sp}${consistentText}`,
    ], width - 1.2 * f), titleX, titleY, { colour: THEME.text }));
    const categories = row.windows.map((w) => windowLabel(w));

    // ---- MAE bars from zero
    const mi = grids.length;
    grids.push({ left: mae.left, top: mae.top, width: mae.width, height: mae.height });
    graphic.push(textGraphic(fitName([`MAE [${model.unit}] — bars from zero`, `MAE [${model.unit}]`], mae.subW), mae.subX, mae.subY));
    xAxes.push(categoryAxis({ gridIndex: mi, data: categories, labels: xLabels(row), lineHeight: WINDOW_LABEL_PITCH * f }));
    yAxes.push(valueAxis({ gridIndex: mi, min: 0, max: row.mae.max, interval: row.mae.interval, split: true, formatter: tickLabel }));
    const slot = mae.width / Math.max(1, row.windows.length);
    const barW = Math.min(36, 0.5 * slot);
    series.push(withColour({
      type: 'custom',
      name: 'MAE',
      xAxisIndex: mi,
      yAxisIndex: mi,
      clip: true,
      z: 4,
      data: row.windows.map((w, i) => [i, w.mae, i]),
      renderItem: (params, api) => {
        const i = params.dataIndex;
        const w = row.windows[i];
        const base = api.coord([i, 0]);
        const end = api.coord([i, w.mae]);
        return {
          type: 'rect',
          shape: { x: base[0] - barW / 2, y: Math.min(base[1], end[1]), width: barW, height: Math.abs(base[1] - end[1]) },
          style: { fill: colour, opacity: 1, fillOpacity: BAR_FILL, stroke: colour, strokeOpacity: ink, lineWidth: THEME.lineAxis },
        };
      },
      tooltip: { formatter: (p) => momentumTip(model, payload, row, row.windows[p.dataIndex], 'mae') },
    }, colour));

    // ---- bias dots on a zero-centred axis
    const bi = grids.length;
    grids.push({ left: bias.left, top: bias.top, width: bias.width, height: bias.height });
    graphic.push(textGraphic(fitName([`${BIAS_NAME} [${model.unit}] — zero-centred`, `Bias [${model.unit}]`], bias.subW), bias.subX, bias.subY));
    xAxes.push(categoryAxis({ gridIndex: bi, data: categories, labels: xLabels(row), lineHeight: WINDOW_LABEL_PITCH * f }));
    yAxes.push(valueAxis({
      gridIndex: bi, min: -row.bias.bound, max: row.bias.bound, interval: row.bias.interval, split: true, formatter: tickLabel,
    }));
    series.push(zeroRuleSeries({
      name: 'zero', xAxisIndex: bi, yAxisIndex: bi,
      tooltip: `${escapeHtml('zero: no mean signed error')}<br/>${mutedLine('the reference rule of the bias axis')}`,
    }));
    series.push(withColour({
      type: 'custom',
      name: BIAS_NAME,
      xAxisIndex: bi,
      yAxisIndex: bi,
      clip: false,
      z: 6,
      data: row.windows.map((w, i) => [i, w.bias, i]),
      renderItem: (params, api) => {
        const i = params.dataIndex;
        const w = row.windows[i];
        const c = api.coord([i, w.bias]);
        const r = DOT_PX;
        const mark = w.oneSigned
          ? { type: 'polygon', shape: { points: [[c[0], c[1] - r - 1], [c[0] + r + 1, c[1]], [c[0], c[1] + r + 1], [c[0] - r - 1, c[1]]] } }
          : { type: 'circle', shape: { cx: c[0], cy: c[1], r } };
        mark.style = { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis };
        const children = [mark];
        if (w.oneSigned) {
          // Centred under the diamond: beside it, the last window's label left a 321 px figure.
          children.push({
            type: 'text',
            style: {
              x: c[0], y: c[1] + r + 3, text: 'one sign', fill: textInk(THEME.muted), fontSize: THEME.fontSmall,
              fontFamily: THEME.fontFamily, textAlign: 'center', textVerticalAlign: 'top',
            },
          });
        }
        return { type: 'group', children };
      },
      tooltip: { formatter: (p) => momentumTip(model, payload, row, row.windows[p.dataIndex], 'bias') },
    }, colour));
  }

  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      graphic,
      series,
    },
    plotGrid: grids,
  };
}

/** The colours a reader must see on this card, as {colour, role, opacity} (for the contrast tests). */
export function drawnColours() {
  const colour = frameHues().absolute;
  return [
    { colour, role: 'mark', opacity: legibleOpacity(colour, 1) },
    { colour: textInk(THEME.muted), role: 'text', opacity: 1 },
  ];
}

/* =============================================================== class == */

export class BenchMomentumPanel extends CatalogChartPanel {
  constructor(elementOrId, { card = 'perf-momentum-bias', aspect } = {}) {
    super(elementOrId, { card, kind: 'bench-momentum', aspect });
  }

  heightFor(width) {
    return plotHeight(this.lastPayload, this.lastOpts ?? {}, width);
  }

  buildOption({ payload, opts = {}, metrics }) {
    return benchMomentumOption(payload, opts, metrics);
  }
}
