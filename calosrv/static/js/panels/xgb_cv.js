/* E1: the XGBoost regressor's five-fold cross-validation, per metric.
 *
 * `/api/xgboost?view=cv&task=momentum|angle` ships the five folds of
 * KFold(5, shuffle=True, random_state=42) - each a refit of the notebook's
 * regressor scored on its held-out fifth - with MAE, MSE, RMSE and R² per
 * fold, and per metric the mean, the SD (ddof 1), the SE and a 95 %
 * Student-t interval of the mean (4 d.o.f., t = 2.776; the server may widen
 * the SE for the folds' overlapping training sets, and names the interval it
 * ships in `interval.label`, which the legend and tooltips print). The angle task adds
 * per-label blocks in mrad: θ's MAE, RMSE and R², and φ's MAE and RMSE of the
 * residual wrapped to (−π, π] (no R², undefined for an azimuth). The task's
 * top-level metrics are the notebook's parity numbers - sklearn's uniform
 * average over [φ, θ] on the raw labels in rad, φ unwrapped - and are drawn
 * in a row of their own, labelled so, never on one axis with the per-label
 * values: an unwrapped azimuth error of 2π − ε would set the scale and
 * flatten θ.
 *
 * ## Five dots and the mean's interval: two different marks
 *
 * A fold value is one observation, so each is a dot (an open ring, muted
 * ink). The aggregate is the mean of the five, a filled diamond with a capped
 * whisker that is its 95 % Student-t interval - the uncertainty of the mean
 * (CLAUDE.md section 2), named by the payload's label in its tooltip and in
 * the legend. The SD of
 * the folds is their spread, a different quantity: with the five folds drawn
 * it gets no mark at all, and is quoted in the mean's tooltip beside the SE.
 * The dots sit left of the slot's centre, the mean right of it, so the two
 * never overprint.
 *
 * ## One scale per metric
 *
 * Each metric is a small multiple with its own y axis: the units differ (GeV
 * against GeV²; rad against mrad) and R² is a dimensionless score. The error
 * metrics are magnitudes and start at zero. R² is read near 1, where the folds
 * differ in the third decimal or later: its axis runs from a round value
 * below the lowest fold or interval end up to 1, with a break mark on the
 * axis and the axis start in the panel title ("axis from 0.975"), the offset
 * label CLAUDE.md asks of a truncated scale. An R² at or below zero, or a
 * spread wider than half the unit range, gets the plain axis from zero.
 *
 * ## Layout
 *
 * The small multiples flow into lines: as many per line as keep every slot at
 * least MIN_SLOT_PX wide, so the momentum task's four panels sit in a row on
 * the card and in two lines of two in a single-column export (321 px), where
 * `exportMetrics` grows the figure by the lines it needs.
 */

import { THEME, axisPadding, formatInt, typographic } from '../scale.js';
import { measureText } from '../textfit.js';
import { customWhiskers } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, withColour, emptyChartOption,
  chartLegend, legendTop, niceCeil, niceInterval, FINE_STEPS, sigFigs,
} from './chart_panel.js';

/** Narrowest slot (px) a fold column and its mean are drawn in before a line breaks. */
export const MIN_SLOT_PX = 34;
/** Height of one line of plots in an exported figure, as a share of the figure width (clamped). */
const EXPORT_PLOT_SHARE = 0.34;
const FOLD_RADIUS_PX = 2.6;
const MEAN_RADIUS_PX = 4;
const CAP_PX = 4;

export const FOLD_NAME = 'Fold value (one observation each)';
export const MEAN_NAME = 'Mean of the folds';
/**
 * The whisker's legend name: the interval the payload names (its `label`),
 * never one computed here - the server may widen the plain Student-t SE for
 * the folds' overlapping training sets. The fallback is the plain interval.
 */
export function intervalName(payloadOrDof = 4) {
  if (payloadOrDof && typeof payloadOrDof === 'object') {
    const label = payloadOrDof.interval?.label;
    if (label) return label;
    return intervalName(payloadOrDof.interval?.dof ?? 4);
  }
  return `95% Student-t interval of the mean (${payloadOrDof} d.o.f.)`;
}
export const BREAK_NAME = 'Axis break: R² axis does not start at 0';

/**
 * How the SE of a fold mean is named: the server's `se` is the Nadeau–Bengio
 * corrected SE, √(variance_factor) × SD, when the interval says it is
 * (`interval.method` 'corrected_resampled_t'); the plain s/√k otherwise.
 */
export function seName(payload, summary = null) {
  const corrected = payload?.interval?.method === 'corrected_resampled_t';
  const factor = summary?.variance_factor ?? payload?.interval?.variance_factor;
  if (!corrected) return 'SE of the mean';
  return Number.isFinite(factor)
    ? `corrected SE of the mean (√${sigFigs(factor, 3)} × SD: the folds share training rows)`
    : 'corrected SE of the mean (the folds share training rows)';
}

const METRIC_TITLES = Object.freeze({ mae: 'MAE', mse: 'MSE', rmse: 'RMSE', r2: 'R²' });
const LABEL_SYMBOLS = Object.freeze({ theta: 'θ', phi: 'φ', momentum: 'p' });
const LABEL_LONG = Object.freeze({
  theta: 'θ (polar angle)',
  phi: 'φ (azimuth, residual wrapped to (−π, π])',
});

/** A value with its unit, to three significant figures. */
export function withUnit(value, unit) {
  const text = sigFigs(value, 3);
  return unit && text !== '—' ? `${text} ${unit}` : text;
}

/** The fewest decimals that print every multiple of `interval` exactly. */
export function decimalsFor(interval) {
  for (let d = 0; d <= 12; d += 1) {
    const scaled = interval * 10 ** d;
    if (Math.round(scaled) >= 1 && Math.abs(scaled - Math.round(scaled)) < 1e-6 * scaled) return d;
  }
  return 12;
}

/**
 * An R² with the digits that tell it from 1: three decimals, or one more
 * than the first significant digit of 1 − R² (0.9999990, never a rounded
 * "1" for a fold that is not perfect).
 */
export function r2Text(value) {
  if (!Number.isFinite(value)) return '—';
  if (value >= 1) return typographic(String(value === 1 ? 1 : Number(value.toPrecision(6))));
  const gap = 1 - value;
  const decimals = gap < 0.01 ? Math.min(9, Math.max(3, Math.ceil(-Math.log10(gap)) + 1)) : 3;
  return typographic(value.toFixed(decimals));
}

/** A metric's value as printed: an R² by `r2Text`, anything else by `withUnit`. */
export function metricText(value, metric, unit) {
  return metric === 'r2' ? r2Text(value) : withUnit(value, unit);
}

/* ---------------------------------------------------------------- model -- */

/**
 * The card's content, decided once. Pure: `{task, angle, dof, t,
 * intervalLabel, folds: [{fold, n_train, n_val}], rows: [{id, heading,
 * panels: [{id, metric, title, unit, definition, kind: 'zero' | 'r2', slots:
 * [{key, label, long, values[5], summary, family}]}]}], clipped: [names]}`.
 * `family` is the slot's metrics per fold, for the tooltips. Null without
 * folds.
 */
export function cvModel(payload) {
  const folds = payload?.folds;
  if (!Array.isArray(folds) || !folds.length || !payload?.summary) return null;
  const angle = payload.task === 'angle';
  const dof = payload.interval?.dof ?? folds.length - 1;
  const parityUnit = (payload.metrics ?? []).find((m) => m.id === 'mae')?.unit ?? '';
  const parityFamily = (payload.metrics ?? []).map((m) => ({ id: m.id, label: m.label, unit: m.unit }));
  const rows = [{
    id: 'parity',
    heading: angle ? 'parity' : null,
    unit: parityUnit,
    panels: (payload.metrics ?? []).map((m) => ({
      id: `parity:${m.id}`,
      metric: m.id,
      title: m.label ?? METRIC_TITLES[m.id] ?? m.id,
      unit: m.unit ?? '',
      definition: m.definition ?? '',
      kind: m.id === 'r2' ? 'r2' : 'zero',
      slots: [{
        key: 'parity',
        label: angle ? 'parity' : '',
        long: angle ? (payload.parity_label ?? 'notebook parity') : (payload.parity_label ?? payload.task ?? ''),
        values: folds.map((f) => f.metrics?.[m.id] ?? null),
        summary: payload.summary[m.id] ?? null,
        family: folds.map((f) => parityFamily.map((x) => ({ ...x, value: f.metrics?.[x.id] ?? null }))),
      }],
    })),
  }];
  const perLabel = payload.per_label;
  if (angle && perLabel) {
    const labels = (payload.labels ?? ['theta', 'phi']).filter((l) => perLabel[l]);
    const has = (l, id) => (perLabel[l].metrics ?? []).some((m) => m.id === id);
    const ids = ['mae', 'mse', 'rmse', 'r2'].filter((id) => labels.some((l) => has(l, id)));
    rows.push({
      id: 'per_label',
      heading: 'per_label',
      unit: perLabel[labels[0]]?.unit ?? 'mrad',
      panels: ids.map((id) => {
        const owners = labels.filter((l) => has(l, id));
        const m = perLabel[owners[0]].metrics.find((x) => x.id === id);
        return {
          id: `label:${id}`,
          metric: id,
          title: m.label ?? METRIC_TITLES[id] ?? id,
          unit: m.unit ?? '',
          definition: m.definition ?? '',
          kind: id === 'r2' ? 'r2' : 'zero',
          slots: owners.map((l) => ({
            key: l,
            label: LABEL_SYMBOLS[l] ?? l,
            long: LABEL_LONG[l] ?? l,
            values: folds.map((f) => f.per_label?.[l]?.[id] ?? null),
            summary: perLabel[l].summary?.[id] ?? null,
            family: folds.map((f) => (perLabel[l].metrics ?? []).map((x) => ({
              id: x.id, label: x.label, unit: x.unit, value: f.per_label?.[l]?.[x.id] ?? null,
            }))),
          })),
        };
      }),
    });
  }
  const clipped = [];
  for (const row of rows) {
    for (const panel of row.panels) {
      for (const slot of panel.slots) if (slot.summary?.clipped) clipped.push(`${slot.long} ${panel.title}`);
    }
  }
  return {
    task: payload.task,
    angle,
    dof,
    t: payload.interval?.t ?? null,
    intervalLabel: intervalName(payload),
    seName: (summary) => seName(payload, summary),
    folds: folds.map((f) => ({ fold: f.fold, n_train: f.n_train, n_val: f.n_val })),
    rows,
    clipped,
  };
}

/** The heading of a row of panels, longest first, for `fitName`. */
export function rowHeadings(row) {
  if (row.heading === 'parity') {
    return [
      `Notebook parity: the mean over φ and θ, φ unwrapped [${row.unit}]`,
      `Notebook parity, φ unwrapped [${row.unit}]`,
      `Parity [${row.unit}]`,
    ];
  }
  if (row.heading === 'per_label') {
    return [
      `Per label: θ, and φ with its residual wrapped to (−π, π] [${row.unit}]`,
      `Per label, φ wrapped [${row.unit}]`,
      `Per label [${row.unit}]`,
    ];
  }
  return [];
}

/**
 * The y axis of one panel: `{min, max, interval, decimals, truncated}`. Error
 * metrics from zero to a round top over every fold, mean and interval end;
 * R² truncated below 1 as the header says.
 */
export function cvAxis(panel) {
  const values = panel.slots.flatMap((s) => [...s.values, s.summary?.mean, ...(s.summary?.t95 ?? [])])
    .filter(Number.isFinite);
  if (panel.kind !== 'r2') {
    const top = niceCeil(Math.max(0, ...values) || 1, FINE_STEPS);
    const interval = niceInterval(top);
    return { min: 0, max: top, interval, decimals: null, truncated: false };
  }
  if (!values.length) return { min: 0, max: 1, interval: 0.2, decimals: 1, truncated: false };
  const lo = Math.min(...values);
  if (!(lo > 0) || 1 - lo > 0.5) {
    const min = lo < 0 ? -niceCeil(-lo) : 0;
    const interval = lo < 0 ? niceInterval(niceCeil(1 - min, FINE_STEPS)) : 0.2;
    return { min, max: 1, interval, decimals: decimalsFor(interval), truncated: false };
  }
  const span = niceCeil(Math.max((1 - lo) * 1.25, 1e-6), FINE_STEPS);
  const interval = niceInterval(span);
  const decimals = decimalsFor(interval);
  return { min: Number((1 - span).toFixed(decimals)), max: 1, interval, decimals, truncated: true };
}

/** The tick labels of an axis (for measuring the inset). */
function tickTexts(axis) {
  const out = [];
  const steps = Math.round((axis.max - axis.min) / axis.interval);
  for (let k = 0; k <= Math.min(steps, 20); k += 1) out.push(tickText(axis, axis.min + k * axis.interval));
  return out;
}

/** One tick label: significant figures for an error axis, fixed decimals for R². */
function tickText(axis, value) {
  if (axis.decimals !== null) return typographic(String(Number(value.toFixed(axis.decimals))));
  return sigFigs(value, 3);
}

/* --------------------------------------------------------------- layout -- */

/** The names in the legend, in order. */
export function cvLegendNames(model, width = Infinity) {
  return [FOLD_NAME, MEAN_NAME, intervalLegend(model, width)];
}

/**
 * The interval's name in the legend and on its series at `width`: the
 * payload's full label where it fits one legend row, else the generic name
 * (the tooltips and the drawer keep the full label). A printed legend entry
 * wider than the figure would be cut at its edge.
 */
export function intervalLegend(model, width = Infinity) {
  const px = width - 2 * axisPadding().right - 26;
  return fitName([model.intervalLabel, '95% interval of the mean'], px);
}

/**
 * Where every panel goes at `width` × `height`: `{top, lines: [{row,
 * heading, panels: [{panel, axis, inset, slotW, grid}]}], height}`. With
 * `height` null (an export) each line takes a plot height from the width and
 * `height` is what the figure needs.
 */
export function cvLayout(model, width, height = null) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const side = pad.right;
  const gap = 1.8 * f;
  const titleH = 1.9 * f;
  const headingH = 1.9 * f;
  const top = legendTop(cvLegendNames(model, width), width - 2 * side);
  const usable = Math.max(80, width - 2 * side);

  const prepared = model.rows.map((row) => ({
    row,
    panels: row.panels.map((panel) => {
      const axis = cvAxis(panel);
      const labelW = Math.max(...tickTexts(axis).map((t) => measureText(t, THEME.fontLabel, THEME.fontFamily)));
      return { panel, axis, inset: labelW + 0.9 * f + 4 };
    }),
  }));

  const lines = [];
  for (const { row, panels } of prepared) {
    let cols = panels.length;
    const slotW = (chunk) => {
      const slots = chunk.reduce((s, p) => s + p.panel.slots.length, 0);
      const inset = chunk.reduce((s, p) => s + p.inset, 0);
      return (usable - inset - (chunk.length - 1) * gap) / Math.max(1, slots);
    };
    const chunks = (c) => {
      const out = [];
      for (let i = 0; i < panels.length; i += c) out.push(panels.slice(i, i + c));
      return out;
    };
    while (cols > 1 && chunks(cols).some((chunk) => slotW(chunk) < MIN_SLOT_PX)) cols -= 1;
    // As few lines as that allows, filled evenly: 2 + 2, never 3 + 1.
    cols = Math.ceil(panels.length / Math.ceil(panels.length / cols));
    chunks(cols).forEach((chunk, index) => {
      const labelled = chunk.some((p) => p.panel.slots.some((s) => s.label));
      lines.push({
        row,
        heading: index === 0 && row.heading ? row.heading : null,
        chunk,
        slotW: Math.min(slotW(chunk), 6 * MIN_SLOT_PX),
        xLabelH: labelled ? 2.1 * f : 0.9 * f,
      });
    });
  }

  const fixed = lines.reduce((s, l) => s + titleH + l.xLabelH + (l.heading ? headingH : 0), 0);
  const plotH = height === null
    ? Math.max(90, Math.min(160, EXPORT_PLOT_SHARE * width))
    : Math.max(36, (height - top - fixed - 0.6 * f) / Math.max(1, lines.length));

  let y = top;
  const out = [];
  for (const line of lines) {
    const entry = { row: line.row, heading: line.heading, headingY: null, panels: [] };
    if (line.heading) {
      entry.headingY = y;
      y += headingH;
    }
    let x = side;
    for (const p of line.chunk) {
      const w = line.slotW * p.panel.slots.length;
      entry.panels.push({
        panel: p.panel, axis: p.axis, inset: p.inset, slotW: line.slotW,
        grid: { left: x + p.inset, top: y + titleH, width: w, height: plotH },
      });
      x += p.inset + w + gap;
    }
    y += titleH + plotH + line.xLabelH;
    out.push(entry);
  }
  return { top, lines: out, height: Math.ceil(y + 0.6 * f) };
}

/* ------------------------------------------------------------- tooltips -- */

/** The fold's metrics of the slot's family, as one line. */
function familyLine(slot, k) {
  return (slot.family?.[k] ?? []).map((m) => `${escapeHtml(m.label)} ${escapeHtml(metricText(m.value, m.id, m.unit))}`).join(' · ');
}

/** The tooltip of one fold's dot. */
export function foldTip(model, panel, slot, k) {
  const fold = model.folds[k] ?? {};
  return [
    `<b>Fold ${formatInt((fold.fold ?? k) + 1)} of ${formatInt(model.folds.length)} · ${escapeHtml(slot.long)}: `
      + `${escapeHtml(panel.title)} = ${escapeHtml(metricText(slot.values[k], panel.metric, panel.unit))}</b>`,
    `refitted on ${formatInt(fold.n_train)} rows, scored on its ${formatInt(fold.n_val)} held-out rows`,
    `this fold: ${familyLine(slot, k)}`,
    mutedLine('one observation, drawn as a dot; the folds\' spread is these dots, not a whisker'),
  ].join('<br/>');
}

/** The tooltip of a mean and its interval. */
export function meanTip(model, panel, slot) {
  const s = slot.summary ?? {};
  const u = (v) => escapeHtml(metricText(v, panel.metric, panel.unit));
  // A spread of an R² is a small number, not an R²: printed by significant figures.
  const spread = (v) => escapeHtml(withUnit(v, panel.unit));
  const [lo, hi] = s.t95 ?? [null, null];
  const lines = [
    `<b>${escapeHtml(panel.title)} · ${escapeHtml(slot.long)}: mean of ${formatInt(s.n ?? slot.values.length)} folds = ${u(s.mean)}</b>`,
    `${escapeHtml(model.intervalLabel)}: [${u(lo)}, ${u(hi)}]${Number.isFinite(s.t) ? ` (t = ${sigFigs(s.t, 4)})` : ''}`
      + ` ${mutedLine('- the capped whisker, the uncertainty of the mean')}`,
    `SD of the folds ${spread(s.sd)} (ddof 1): their spread, a different quantity, not drawn; `
      + `${escapeHtml(model.seName ? model.seName(s) : 'SE of the mean')} ${spread(s.se)}`,
    `folds: ${slot.values.map((v) => escapeHtml(metricText(v, panel.metric, ''))).join(', ')}`,
  ];
  if (s.clipped) lines.push(mutedLine('the interval was clipped by the server to the range the metric can take'));
  if (panel.kind === 'r2' && cvAxis(panel).truncated) lines.push(mutedLine(`the R² axis is truncated: it starts at ${tickText(cvAxis(panel), cvAxis(panel).min)}, not at 0`));
  return lines.join('<br/>');
}

/* --------------------------------------------------------------- option -- */

/**
 * The E1 option. Pure: `opts` = {tooltipPosition?}; `metrics` = {width,
 * height}. One grid per metric; the folds, the mean and its interval as
 * custom series per grid, sharing their legend names.
 */
export function xgbCvOption(payload, opts = {}, metrics = {}) {
  const model = cvModel(payload);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no cross-validation folds.');
  const width = metrics.width || 600;
  const height = metrics.height || 330;
  const layout = cvLayout(model, width, height);
  const f = THEME.fontLabel;
  const foldColour = THEME.muted;
  const meanColour = THEME.accent;
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = [];

  for (const line of layout.lines) {
    if (line.heading) {
      graphic.push({
        type: 'text',
        silent: true,
        style: {
          x: line.panels[0].grid.left - line.panels[0].inset,
          y: line.headingY + 0.25 * f,
          text: fitName(rowHeadings(line.row), width - 2 * axisPadding().right),
          fill: THEME.text,
          fontSize: THEME.fontName,
          fontFamily: THEME.fontFamily,
        },
      });
    }
    for (const placed of line.panels) {
      const { panel, axis, grid, slotW } = placed;
      const index = grids.length;
      grids.push(grid);
      const titleCandidates = [
        ...(axis.truncated ? [`${panel.title}${panel.unit ? ` [${panel.unit}]` : ''} · axis from ${tickText(axis, axis.min)}`] : []),
        `${panel.title}${panel.unit ? ` [${panel.unit}]` : ''}`,
        panel.title,
      ];
      graphic.push({
        type: 'text',
        silent: true,
        style: {
          x: grid.left - placed.inset,
          y: grid.top - 1.6 * f,
          text: fitName(titleCandidates, grid.width + placed.inset),
          fill: THEME.text,
          fontSize: THEME.fontLabel,
          fontFamily: THEME.fontFamily,
        },
      });
      const labelled = panel.slots.some((s) => s.label);
      xAxes.push({
        type: 'category',
        gridIndex: index,
        data: panel.slots.map((s) => s.label),
        boundaryGap: true,
        axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
        axisTick: { show: false },
        axisLabel: {
          show: labelled, color: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily, interval: 0,
        },
        splitLine: { show: false },
      });
      yAxes.push(valueAxis({
        gridIndex: index, min: axis.min, max: axis.max, interval: axis.interval, split: true,
        formatter: (v) => tickText(axis, v),
      }));

      const dotsAt = -0.2 * slotW;
      const meanAt = 0.16 * slotW;
      const spread = Math.min(3, 0.05 * slotW);
      const dots = [];
      panel.slots.forEach((slot, si) => slot.values.forEach((v, k) => {
        if (Number.isFinite(v)) dots.push({ si, k, v, slot });
      }));
      series.push(withColour({
        type: 'custom',
        name: FOLD_NAME,
        xAxisIndex: index,
        yAxisIndex: index,
        clip: true,
        z: 7,
        data: dots.map((d, i) => [d.si, d.v, i]),
        renderItem: (params, api) => {
          const d = dots[params.dataIndex];
          const c = api.coord([d.si, d.v]);
          return {
            type: 'circle',
            shape: { cx: c[0] + dotsAt + (d.k - 2) * spread, cy: c[1], r: FOLD_RADIUS_PX },
            style: { fill: THEME.card, stroke: foldColour, lineWidth: 1.2 * THEME.lineAxis },
          };
        },
        tooltip: { formatter: (p) => { const d = dots[p.dataIndex]; return foldTip(model, panel, d.slot, d.k); } },
      }, foldColour));

      const withCi = panel.slots.map((slot, si) => ({ slot, si })).filter(({ slot }) => (
        Number.isFinite(slot.summary?.t95?.[0]) && Number.isFinite(slot.summary?.t95?.[1])));
      series.push(customWhiskers({
        name: intervalLegend(model, width),
        points: withCi.map(({ slot, si }) => [si, slot.summary.t95[0], slot.summary.t95[1], { slot }]),
        capPx: CAP_PX,
        color: meanColour,
        width: 1.4 * THEME.lineAxis,
        offsetPx: meanAt,
        z: 8,
        tooltip: (d) => meanTip(model, panel, d.slot),
      }));
      series[series.length - 1].xAxisIndex = index;
      series[series.length - 1].yAxisIndex = index;
      series[series.length - 1].itemStyle = { color: meanColour };

      const means = panel.slots.map((slot, si) => ({ slot, si })).filter(({ slot }) => Number.isFinite(slot.summary?.mean));
      series.push(withColour({
        type: 'custom',
        name: MEAN_NAME,
        xAxisIndex: index,
        yAxisIndex: index,
        clip: true,
        z: 9,
        data: means.map(({ slot, si }, i) => [si, slot.summary.mean, i]),
        renderItem: (params, api) => {
          const { slot, si } = means[params.dataIndex];
          const c = api.coord([si, slot.summary.mean]);
          const x = c[0] + meanAt;
          const r = MEAN_RADIUS_PX;
          return {
            type: 'polygon',
            shape: { points: [[x, c[1] - r], [x + r, c[1]], [x, c[1] + r], [x - r, c[1]]] },
            style: { fill: meanColour, stroke: THEME.card, lineWidth: 1 },
          };
        },
        tooltip: { formatter: (p) => meanTip(model, panel, means[p.dataIndex].slot) },
      }, meanColour));

      if (axis.truncated) {
        const tip = [
          `<b>${escapeHtml(BREAK_NAME)}</b>`,
          `the axis runs from ${escapeHtml(tickText(axis, axis.min))} to 1: the folds differ only in the digits shown`,
        ].join('<br/>');
        series.push({
          type: 'custom',
          name: BREAK_NAME,
          xAxisIndex: index,
          yAxisIndex: index,
          clip: false,
          z: 10,
          data: [[0, axis.min]],
          renderItem: (params, api) => {
            const base = api.coord([0, axis.min]);
            const x = params.coordSys?.x ?? base[0];
            const y = base[1] - 7;
            const stroke = { stroke: THEME.text, lineWidth: THEME.lineAxis };
            return {
              type: 'group',
              children: [
                { type: 'rect', shape: { x: x - 4, y: y - 3, width: 8, height: 6 }, style: { fill: THEME.card } },
                { type: 'line', shape: { x1: x - 4, y1: y + 1, x2: x + 4, y2: y - 3 }, style: stroke },
                { type: 'line', shape: { x1: x - 4, y1: y + 4, x2: x + 4, y2: y }, style: stroke },
              ],
            };
          },
          tooltip: { formatter: () => tip },
        });
      }
    }
  }

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    legend: chartLegend(cvLegendNames(model, width), { left: axisPadding().right }),
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    graphic,
    series,
  };
}

export class XgbCvPanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'xgb-cv', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: xgbCvOption(payload, opts, metrics) };
  }

  /** A figure as tall as its lines of small multiples need at `width`. */
  exportMetrics(width) {
    const model = cvModel(this.lastPayload);
    if (!model) return super.exportMetrics(width);
    return { width, height: cvLayout(model, width, null).height };
  }
}
