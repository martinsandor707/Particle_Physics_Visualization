/* E3: the momentum regressor thresholded at 2 GeV, on a 99 : 1 sample.
 *
 * `/api/xgboost?view=binary` reproduces the notebook's experiment: from the
 * 20 % validation split, class 0 (p < 2 GeV) and class 1 (p > 10 GeV, or
 * p > 2 GeV when fewer than 50 rows lie above 10) are sampled 1,980 : 20 with
 * pandas' seeded sampler, and the shipped regressor's momentum is thresholded
 * at 2 GeV. The response carries the confusion counts, six rates with their
 * intervals, the notebook's support-weighted metrics for parity and the
 * minority class's size.
 *
 * ## Counts are not estimates
 *
 * The confusion matrix is four counts, printed in their cells: a count has
 * no interval, and the cells carry no colour ramp. At 99 : 1 a ramp over the
 * counts would paint one bright cell and three dark ones, which says "class 0
 * is large" and nothing else; the share of the true class printed under each
 * count is the comparison a reader wants, and it is a number. Each cell names
 * its role (TN, FP, FN, TP) and the two classes' rules and sizes stand under
 * the matrix, the minority's marked as such.
 *
 * ## Rates are proportions with intervals
 *
 * Accuracy and the per-class recall and precision are proportions k / n of
 * independent rows: a point with a capped, asymmetric whisker that is its
 * 95 % Wilson score interval (CLAUDE.md section 2: the uncertainty of the
 * plotted aggregate; the Wald interval, which collapses at k = 0 or k = n, is
 * never used). The balanced accuracy is a mean of two rates, so its whisker is
 * the interval the server names for it - Newcombe's MOVER interval from the
 * two class recalls' Wilson limits (`method` 'mover'), which keeps the
 * uncertainty of a class classified perfectly where a bootstrap of the rows
 * would collapse it - in a second legend entry carrying the payload's label,
 * so the methods never mix. The rates run
 * as rows against the full 0-100 % scale a proportion can take, so the
 * labels read horizontally and nothing is clipped. A rate whose denominator
 * is empty (precision with no row predicted in the class) is undefined: no
 * point, and the row says so.
 *
 * ## Layout
 *
 * Matrix left and rates right on the card; one above the other in a figure
 * narrower than STACK_BELOW_PX (a single-column export), where
 * `exportMetrics` grows the figure to hold both.
 */

import { THEME, axisPadding, formatInt, formatPercent } from '../scale.js';
import { measureText, wrapText } from '../textfit.js';
import { customWhiskers } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, withColour, emptyChartOption,
  chartLegend, legendTop, isPrintTheme,
} from './chart_panel.js';

/** Below this width the matrix stands above the rates. */
export const STACK_BELOW_PX = 520;
/** A rate resting on fewer rows than this says its interval is wide. */
export const WIDE_BELOW_N = 30;

export const POINT_NAME = 'Rate (point estimate)';
export const WILSON_NAME = '95% Wilson score interval';
/** The balanced accuracy's interval name when the payload names none (never assumed to be a method). */
export const OTHER_INTERVAL_NAME = '95% interval (balanced accuracy)';
export const CELL_NAME = 'Confusion counts';

/** Short row labels; the payload's long label is in the tooltip. */
const SHORT = Object.freeze({
  accuracy: 'Accuracy',
  balanced_accuracy: 'Balanced accuracy',
  recall_1: 'Recall, class 1',
  recall_0: 'Recall, class 0',
  precision_1: 'Precision, class 1',
  precision_0: 'Precision, class 0',
});

/** The order the rows are drawn in, top to bottom. */
export const RATE_ORDER = Object.freeze(['accuracy', 'balanced_accuracy', 'recall_1', 'recall_0', 'precision_1', 'precision_0']);

const pc = (v, d = 1) => formatPercent(v, d);

/* ---------------------------------------------------------------- model -- */

/**
 * Everything drawn, decided once. Pure: `{threshold, counts, confusion,
 * cells: [{role, trueClass, predClass, count, rowTotal, share}], rates:
 * [{id, short, label, definition, k, n, value, lo, hi, method, intervalLabel,
 * note, minority, undefined}], minority, design}`. Null without a matrix.
 */
export function binaryModel(payload) {
  const c = payload?.confusion;
  if (!c || !Array.isArray(c.matrix)) return null;
  const threshold = payload.threshold_gev ?? 2;
  const minorityClass = payload.minority?.class ?? 1;
  const rowTotal = (t) => (c.matrix[t] ?? []).reduce((a, v) => a + (v ?? 0), 0);
  const roles = [['TN', 'FP'], ['FN', 'TP']];
  const cells = [];
  for (let t = 0; t < 2; t += 1) {
    for (let p = 0; p < 2; p += 1) {
      const count = c.matrix[t]?.[p] ?? 0;
      const total = rowTotal(t);
      cells.push({ role: roles[t][p], trueClass: t, predClass: p, count, rowTotal: total, share: total > 0 ? count / total : null });
    }
  }
  const byId = new Map((payload.rates ?? []).map((r) => [r.id, r]));
  const ids = [...RATE_ORDER.filter((id) => byId.has(id)), ...[...byId.keys()].filter((id) => !RATE_ORDER.includes(id))];
  const rates = ids.map((id) => {
    const r = byId.get(id);
    const iv = r.interval ?? null;
    return {
      id,
      short: SHORT[id] ?? r.label ?? id,
      label: r.label ?? SHORT[id] ?? id,
      definition: r.definition ?? '',
      k: r.k,
      n: r.n,
      value: Number.isFinite(r.value) ? r.value : null,
      lo: Number.isFinite(iv?.lo) ? iv.lo : null,
      hi: Number.isFinite(iv?.hi) ? iv.hi : null,
      method: iv?.method ?? null,
      intervalLabel: iv?.label ?? null,
      note: r.note ?? '',
      // A rate whose denominator is the minority class rests on its rows.
      minority: id === `recall_${minorityClass}`,
      undefined: !Number.isFinite(r.value),
    };
  });
  return {
    threshold,
    counts: payload.counts ?? {},
    confusion: c,
    cells,
    rates,
    minority: payload.minority ?? null,
    design: payload.design ?? {},
  };
}

/** The rule and size of class `k`, as the matrix key prints it. */
export function classKey(model, k) {
  const n = model.counts?.[`class_${k}`];
  const rule = k === 0 ? `p < ${model.threshold} GeV` : `p > ${model.threshold} GeV`;
  const minority = model.minority?.class === k ? ' (minority)' : '';
  return `class ${k}: ${rule}, ${formatInt(n)} rows${minority}`;
}

/* ------------------------------------------------------------- tooltips -- */

/** The tooltip of one confusion cell. */
export function cellTip(model, cell) {
  const share = cell.share === null ? '—' : pc(cell.share);
  return [
    `<b>${cell.role}: true class ${cell.trueClass}, predicted class ${cell.predClass} - ${formatInt(cell.count)} row${cell.count === 1 ? '' : 's'}</b>`,
    `${share} of the ${formatInt(cell.rowTotal)} rows of true class ${cell.trueClass}`,
    escapeHtml(classKey(model, cell.trueClass)),
    mutedLine('a count, not an estimate: it carries no interval'),
  ].join('<br/>');
}

/** The tooltip of one rate. */
export function rateTip(rate, model) {
  if (rate.undefined) {
    return [
      `<b>${escapeHtml(rate.label)}: undefined</b>`,
      `${escapeHtml(rate.definition)}: its denominator is empty (n = ${formatInt(rate.n)})`,
    ].join('<br/>');
  }
  const lines = [
    `<b>${escapeHtml(rate.label)}: ${pc(rate.value)}</b>`,
    `${escapeHtml(rate.definition)}${Number.isFinite(rate.k) ? ` = ${formatInt(rate.k)} / ${formatInt(rate.n)}` : ` over ${formatInt(rate.n)} rows`}`,
  ];
  if (Number.isFinite(rate.lo) && Number.isFinite(rate.hi)) {
    lines.push(`${escapeHtml(rate.intervalLabel ?? '95% interval')} [${pc(rate.lo)}, ${pc(rate.hi)}] `
      + `${mutedLine('- the capped whisker, the uncertainty of the rate')}`);
  }
  if (rate.minority && model.minority) lines.push(mutedLine(`rests on the ${formatInt(model.minority.n)} rows of the minority class: the interval is correspondingly wide`));
  else if (Number.isFinite(rate.n) && rate.n < WIDE_BELOW_N) lines.push(mutedLine(`rests on ${formatInt(rate.n)} rows: the interval is correspondingly wide`));
  if (rate.note) lines.push(mutedLine(rate.note));
  return lines.join('<br/>');
}

/* --------------------------------------------------------------- layout -- */

/** The legend's names, in order (the balanced accuracy's own interval only when a rate carries one). */
export function binaryLegendNames(model, width = Infinity) {
  const names = [POINT_NAME, WILSON_NAME];
  if (model.rates.some((r) => r.method && r.method !== 'wilson')) names.push(otherIntervalLegend(model, width));
  return names;
}

const METHOD_WORDS = Object.freeze({ bootstrap_percentile: 'percentile bootstrap', newcombe: 'Newcombe', mover: 'MOVER' });

/**
 * The other interval's legend name at `width`: the payload's full label where
 * it fits one legend row, else its method in a word; the tooltip and the
 * drawer keep the full label.
 */
export function otherIntervalLegend(model, width = Infinity) {
  const r = model.rates.find((x) => x.method && x.method !== 'wilson');
  if (!r) return OTHER_INTERVAL_NAME;
  const word = METHOD_WORDS[r.method] ?? String(r.method).replace(/_/g, ' ');
  return fitName([otherIntervalName(model), `95% ${word} interval (${r.short.toLowerCase()})`, `95% ${word} interval`],
    width - 2 * axisPadding().right - 26);
}

/**
 * The legend name of the balanced accuracy's interval: the method the
 * payload names (Newcombe's MOVER combination of the two classes' Wilson
 * limits, as the server ships it), never assumed here.
 */
export function otherIntervalName(model) {
  const r = model.rates.find((x) => x.method && x.method !== 'wilson');
  if (!r) return OTHER_INTERVAL_NAME;
  return `${r.intervalLabel || r.method} (${r.short.toLowerCase()})`;
}

/**
 * Where the matrix and the rates go: `{stacked, top, matrix: {x, y, cell,
 * headW, headH, keyY, noteY}, grid: {left, top, width, height}, height}`.
 * `height` null (an export) sizes the figure from the width.
 */
export function binaryLayout(model, width, height = null) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const side = pad.right;
  const top = legendTop(binaryLegendNames(model, width), width - 2 * side);
  const stacked = width < STACK_BELOW_PX;
  const headW = measureText('true 0', THEME.fontLabel, THEME.fontFamily) + 0.8 * f;
  const headH = 3.0 * f;
  const keyH = 2 * 1.5 * f + 0.6 * f;
  const noteW = stacked ? width - 2 * side : Math.max(120, 0.42 * width - side);
  const noteLines = isPrintTheme() || !model.minority ? []
    : wrapText(model.minority.note ?? '', noteW, THEME.fontSmall, THEME.fontFamily);
  const noteH = noteLines.length ? noteLines.length * 1.35 * THEME.fontSmall + 0.4 * f : 0;
  const labelW = Math.max(...model.rates.map((r) => measureText(r.short, THEME.fontLabel, THEME.fontFamily))) + 1.2 * f;
  const rowsH = model.rates.length * 2.4 * f;
  const xAxisH = pad.bottom;

  if (!stacked) {
    const regionW = 0.42 * width - side;
    const avail = (height ?? 340) - top - headH - keyH - noteH - 0.4 * f;
    const cell = Math.max(28, Math.min((regionW - headW) / 2, avail / 2));
    const matrix = { x: side + headW, y: top + headH, cell, headW, headH, noteLines };
    matrix.keyY = matrix.y + 2 * cell + 0.6 * f;
    matrix.noteY = matrix.keyY + keyH;
    const gridLeft = side + regionW + 1.6 * f + labelW;
    const gridTop = top + headH;
    const h = height ?? Math.max(matrix.noteY + noteH, gridTop + rowsH + xAxisH) + 0.6 * f;
    const grid = { left: gridLeft, top: gridTop, width: Math.max(80, width - gridLeft - side - 0.6 * f), height: Math.max(60, h - gridTop - xAxisH) };
    return { stacked, top, matrix, grid, height: Math.ceil(h) };
  }
  const cell = Math.max(28, Math.min((width - 2 * side - headW) / 2, 64));
  const matrix = { x: side + headW, y: top + headH, cell, headW, headH, noteLines };
  matrix.keyY = matrix.y + 2 * cell + 0.6 * f;
  matrix.noteY = matrix.keyY + keyH;
  const gridTop = matrix.noteY + noteH + 1.4 * f;
  const gridH = height === null ? rowsH : Math.max(60, height - gridTop - xAxisH);
  const grid = { left: side + labelW, top: gridTop, width: Math.max(80, width - 2 * side - labelW - 0.6 * f), height: gridH };
  return { stacked, top, matrix, grid, height: Math.ceil(height ?? gridTop + gridH + xAxisH + 0.6 * f) };
}

/* --------------------------------------------------------------- option -- */

/** The custom series drawing the 2 × 2 matrix in pixels, one hover target per cell. */
function matrixSeries(model, m) {
  const ink = THEME.text;
  const big = Math.min(1.9 * THEME.fontTip, 0.34 * m.cell);
  return {
    type: 'custom',
    name: CELL_NAME,
    coordinateSystem: 'none',
    silent: false,
    z: 5,
    data: model.cells.map((c, i) => [i]),
    renderItem: (params) => {
      const c = model.cells[params.dataIndex];
      const x = m.x + c.predClass * m.cell;
      const y = m.y + c.trueClass * m.cell;
      const correct = c.trueClass === c.predClass;
      return {
        type: 'group',
        children: [
          {
            type: 'rect',
            shape: { x: x + 1, y: y + 1, width: m.cell - 2, height: m.cell - 2 },
            style: {
              fill: THEME.card,
              stroke: correct ? THEME.text : THEME.muted,
              lineWidth: THEME.lineAxis,
              lineDash: correct ? null : [3, 2],
            },
          },
          {
            type: 'text',
            style: {
              x: x + m.cell / 2, y: y + m.cell / 2 - 0.2 * big, text: formatInt(c.count), textAlign: 'center',
              textVerticalAlign: 'middle', fill: ink, fontSize: big, fontWeight: 'bold', fontFamily: THEME.fontFamily,
            },
          },
          {
            type: 'text',
            style: {
              x: x + m.cell / 2, y: y + m.cell / 2 + 0.75 * big, textAlign: 'center', textVerticalAlign: 'middle',
              text: `${c.role} · ${c.share === null ? '—' : pc(c.share, 0)}`,
              fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
            },
          },
        ],
      };
    },
    tooltip: { formatter: (p) => cellTip(model, model.cells[p.dataIndex]) },
  };
}

/** The matrix's headers, class key and (on screen) the minority sentence, as graphic text. */
function matrixGraphics(model, m) {
  const f = THEME.fontLabel;
  const text = (x, y, t, extra = {}) => ({
    type: 'text', silent: true,
    style: { x, y, text: t, fill: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily, ...extra },
  });
  const out = [
    text(m.x, m.y - m.headH + 0.1 * f, fitName(['Confusion matrix (counts)', 'Counts'], 2 * m.cell + m.headW), { fill: THEME.text }),
    text(m.x + m.cell / 2, m.y - 1.3 * f, 'pred. 0', { textAlign: 'center' }),
    text(m.x + 1.5 * m.cell, m.y - 1.3 * f, 'pred. 1', { textAlign: 'center' }),
    text(m.x - 0.5 * f, m.y + m.cell / 2, 'true 0', { textAlign: 'right', textVerticalAlign: 'middle' }),
    text(m.x - 0.5 * f, m.y + 1.5 * m.cell, 'true 1', { textAlign: 'right', textVerticalAlign: 'middle' }),
    text(m.x - m.headW, m.keyY, classKey(model, 0)),
    text(m.x - m.headW, m.keyY + 1.5 * f, classKey(model, 1)),
  ];
  m.noteLines.forEach((line, i) => {
    out.push(text(m.x - m.headW, m.noteY + i * 1.35 * THEME.fontSmall, line, { fontSize: THEME.fontSmall }));
  });
  return out;
}

/**
 * The E3 option. Pure: `opts` = {tooltipPosition?}; `metrics` = {width,
 * height}. Returns the option; `binaryPlotGrid` gives the area tips avoid.
 */
export function xgbBinaryOption(payload, opts = {}, metrics = {}) {
  const model = binaryModel(payload);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no confusion matrix.');
  const width = metrics.width || 600;
  const height = metrics.height || 330;
  const layout = binaryLayout(model, width, height);
  const colour = THEME.accent;
  const rows = model.rates;
  const series = [matrixSeries(model, layout.matrix)];

  const wilson = rows.map((r, i) => ({ r, i })).filter(({ r }) => r.method === 'wilson' && Number.isFinite(r.lo) && Number.isFinite(r.hi));
  const other = rows.map((r, i) => ({ r, i })).filter(({ r }) => r.method && r.method !== 'wilson' && Number.isFinite(r.lo) && Number.isFinite(r.hi));
  series.push(customWhiskers({
    name: WILSON_NAME,
    points: wilson.map(({ r, i }) => [i, 100 * r.lo, 100 * r.hi, { rate: r }]),
    horizontal: true,
    capPx: 4,
    color: colour,
    width: 1.3 * THEME.lineAxis,
    z: 6,
    tooltip: (d) => rateTip(d.rate, model),
  }));
  series[series.length - 1].itemStyle = { color: colour };
  if (other.length) {
    series.push(customWhiskers({
      name: otherIntervalLegend(model, width),
      points: other.map(({ r, i }) => [i, 100 * r.lo, 100 * r.hi, { rate: r }]),
      horizontal: true,
      capPx: 4,
      color: THEME.text,
      width: 1.3 * THEME.lineAxis,
      z: 6,
      tooltip: (d) => rateTip(d.rate, model),
    }));
    series[series.length - 1].itemStyle = { color: THEME.text };
  }
  const defined = rows.map((r, i) => ({ r, i })).filter(({ r }) => !r.undefined);
  series.push(withColour({
    type: 'custom',
    name: POINT_NAME,
    clip: true,
    z: 8,
    data: defined.map(({ r, i }, k) => [100 * r.value, i, k]),
    renderItem: (params, api) => {
      const { r, i } = defined[params.dataIndex];
      const c = api.coord([100 * r.value, i]);
      const fill = r.method && r.method !== 'wilson' ? THEME.text : colour;
      return { type: 'circle', shape: { cx: c[0], cy: c[1], r: 3.6 }, style: { fill, stroke: THEME.card, lineWidth: 1 } };
    },
    tooltip: { formatter: (p) => rateTip(defined[p.dataIndex].r, model) },
  }, colour));
  const missing = rows.map((r, i) => ({ r, i })).filter(({ r }) => r.undefined);
  if (missing.length) {
    series.push({
      type: 'custom',
      name: 'Undefined rate',
      clip: true,
      z: 8,
      data: missing.map(({ i }, k) => [0, i, k]),
      renderItem: (params, api) => {
        const { i } = missing[params.dataIndex];
        const c = api.coord([0, i]);
        return {
          type: 'text',
          style: { x: c[0] + 4, y: c[1], text: 'undefined: empty denominator', textVerticalAlign: 'middle',
            fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily },
        };
      },
      tooltip: { formatter: (p) => rateTip(missing[p.dataIndex].r, model) },
    });
  }

  const g = layout.grid;
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    legend: chartLegend(binaryLegendNames(model, width), { left: axisPadding().right }),
    grid: { left: g.left, top: g.top, width: g.width, height: g.height },
    xAxis: valueAxis({
      name: fitName(['Rate [%] (full 0–100% scale)', 'Rate [%]'], g.width), min: 0, max: 100, interval: 20, split: true,
    }),
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((r) => r.short),
      axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
      axisTick: { show: false },
      axisLabel: { color: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily, interval: 0 },
      splitLine: { show: false },
    },
    graphic: matrixGraphics(model, layout.matrix),
    series,
  };
}

/** The plot areas tips stay off: the matrix and the rates grid. */
export function binaryPlotGrid(payload, metrics) {
  const model = binaryModel(payload);
  if (!model) return null;
  const layout = binaryLayout(model, metrics.width || 600, metrics.height || 330);
  const m = layout.matrix;
  return [
    { left: m.x, top: m.y, width: 2 * m.cell, height: 2 * m.cell },
    { left: layout.grid.left, top: layout.grid.top, width: layout.grid.width, height: layout.grid.height },
  ];
}

export class XgbBinaryPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'xgb-binary', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: xgbBinaryOption(payload, opts, metrics), plotGrid: binaryPlotGrid(payload, metrics) };
  }

  /** A figure tall enough for the matrix and the rates at `width` (stacked when narrow). */
  exportMetrics(width) {
    const model = binaryModel(this.lastPayload);
    if (!model) return super.exportMetrics(width);
    return { width, height: binaryLayout(model, width, null).height };
  }
}
