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
 *   convention, so the card never writes "prediction − truth"), as a dot on an axis symmetric about zero with
 *   an explicit zero rule.
 * - Windows: 4–6 GeV is the report's stated example ("például"); 9–11 and 14–16 GeV follow the same ±1 GeV
 *   rule. Each window's n is printed under its label, as reported.
 * - The windows are computed on the whole exported model output, training split included, and n counts no
 *   independent particles for the electron and pion (Σn 77,094 and 253,659 against 40,000 particles, F6). No
 *   interval is ever built from n, and the drawer carries both hazards.
 * - Where |bias| equals the MAE to the reported precision (the muon at 5 and 15 GeV, F7) every error in the
 *   window has one sign: the dot is a diamond labelled "one sign".
 * - Under Compare all each species takes its own row, its axes zero-based (MAE) or zero-centred (bias) on its
 *   own values, and the card says so. The proton has no windows: alone it draws an empty state with the
 *   reason; under Compare all a note line says so.
 *
 * No colour literal: every colour is a THEME token or the Absolute frame's E2 hue.
 */

import { THEME, axisPadding, formatInt } from '../scale.js';
import { tooltipOption } from './tooltip.js';
import {
  baseOption, wrapTooltip, valueAxis, mutedLine, escapeHtml, emptyChartOption, withColour, legibleOpacity,
  tickLabel, fitName,
} from './chart_panel.js';
import {
  DEFAULT_WIDTH, CatalogChartPanel, categoryAxis, frameHues, labelOf, niceStep, niceTop, reported, signedReported,
  textGraphic, textInk, tipFooter, withUnit, zeroRuleSeries,
} from './bench_catalog.js';

/** What the bias is, in the card's words (the report states no sign convention). */
export const BIAS_NAME = 'Mean signed error as reported';

const BAR_FILL = 0.78;
const DOT_PX = 4.5;
const ROW_PLOT_PX = 130;
const MIN_SIDE_PX = 220;

/** The window label: "4–6 GeV". */
export function windowLabel(w) {
  return `${reported(w.window?.[0])}–${reported(w.window?.[1])} GeV`;
}

/** The window rule of one window: stated by the report, or by the same ±1 GeV rule. */
export function windowRule(w) {
  return w.windowStated
    ? `the report's own example window for ${reported(w.centre)} GeV`
    : `by the same ±1 GeV rule; the report states the window only for 5 GeV`;
}

/** The n sentence of a window: as reported, with what it does and does not count. */
export function windowN(w, consistent) {
  const base = `n = ${formatInt(w.n)} as reported, on the whole exported output (training split included)`;
  return consistent === false
    ? `${base}; for this species the windows' n sum beyond the 40,000 particles, so n does not count independent particles`
    : `${base}; never used for an interval`;
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
      bias: { bound, interval: niceStep(bound) },
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

/** The note lines over the rows. */
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
  const lines = noteLines(model, payload);
  const top = pad.top + lines.length * 1.6 * f;
  const gap = 2.4 * f;
  const side = (width - gap) / 2 - pad.left - pad.right >= MIN_SIDE_PX;
  const titleH = 1.9 * f;
  const subH = 1.6 * f;
  const xLabelH = 3.2 * f;
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
    ? `MAE ${withUnit(reported(w.mae, w.dp?.mae), model.unit)}`
    : `${BIAS_NAME} ${withUnit(signedReported(w.bias, w.dp?.bias), model.unit)}`;
  const lines = [`<b>${escapeHtml(sp)} · Absolute · ${escapeHtml(windowLabel(w))}: ${escapeHtml(head)}</b>`];
  lines.push(escapeHtml(which === 'mae'
    ? `${BIAS_NAME}: ${withUnit(signedReported(w.bias, w.dp?.bias), model.unit)} (the dot beside)`
    : `MAE ${withUnit(reported(w.mae, w.dp?.mae), model.unit)} (the bar beside)`));
  if (w.oneSigned) {
    lines.push(escapeHtml('|bias| = MAE to the reported precision: every error in this window has one sign'));
  }
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
  const graphic = layout.lines.map((t, i) => textGraphic(t, 0.6 * f, layout.top + i * 1.6 * f));

  for (const { row, titleX, titleY, mae, bias } of layout.rows) {
    const consistentText = row.consistent === false ? ' · n exceeds the particles' : '';
    graphic.push(textGraphic(`${labelOf(payload, 'species', row.species)} · Absolute frame${consistentText}`, titleX, titleY, { colour: THEME.text }));
    const categories = row.windows.map((w) => windowLabel(w));

    // ---- MAE bars from zero
    const mi = grids.length;
    grids.push({ left: mae.left, top: mae.top, width: mae.width, height: mae.height });
    graphic.push(textGraphic(fitName([`MAE [${model.unit}] — bars from zero`, `MAE [${model.unit}]`], mae.subW), mae.subX, mae.subY));
    xAxes.push(categoryAxis({ gridIndex: mi, data: categories, labels: xLabels(row) }));
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
    xAxes.push(categoryAxis({ gridIndex: bi, data: categories, labels: xLabels(row) }));
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
          children.push({
            type: 'text',
            style: {
              x: c[0] + r + 5, y: c[1], text: 'one sign', fill: textInk(THEME.muted), fontSize: THEME.fontSmall,
              fontFamily: THEME.fontFamily, textVerticalAlign: 'middle',
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
