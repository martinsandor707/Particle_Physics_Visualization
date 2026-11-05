/* The distillation triangle of the training report: tree, formula and network (`distill-triangle`).
 *
 * The payload is `catalog/select.js` `catalogPayload('distill-triangle', { species, task })`: one row per
 * (species, frame) of the task on the bench bar, species-major, with the report's distillation numbers in
 * the task's display unit (angles in mrad, converted from the triad's radians, F4). Nothing is derived
 * here: every number is a documented point estimate, drawn as reported with "N not reported" (or the
 * accuracy table's validation N, for the proton's network MAE) and "point estimate as reported; no
 * interval" in its tooltip (Martin's recorded exception, 2026-11-05).
 *
 * ## Two panels on one row axis
 *
 * Left, the R² fidelities on a fixed 0–1 axis, bars from zero:
 *  - Tree → Network, a solid bar (upper half of the row);
 *  - PySR formula → Network, an outlined bar (lower half), dashed where PySR gave no meaningful formula
 *    (its printed R² is kept, F9);
 *  - Tree → Truth, a tick across the row at its value (the proton only; the capacity limit of the tree).
 * An R² below zero, or reported only as "< 0", is clamped at 0 and marked there with a caret pointing left
 * and the text "R² < 0"; the tooltip and the drawer give the exact value or say it was reported only as
 * "< 0". "≈ 0" is drawn at 0 and labelled "≈ 0".
 *
 * Right, the MAE dumbbell on an axis from zero in the task's display unit: Network → Truth (filled
 * circle) and Tree → Truth (hollow circle) joined by a thin line, Tree → Network (hollow square, a little
 * below the line) and, for the angle task, the PySR formula's MAE to truth (filled diamond, a little above).
 * The segmentation MAEs are voxel-sample MAEs (F5): the axis and every tooltip say so, and the proton's
 * validation E-MAE is never drawn against them. The proton has no tree MAEs in the report: only its
 * network MAE (from the accuracy table) is drawn, and the gap is stated in the row.
 *
 * ## Colour is the frame; species are rows
 *
 * Every mark takes its frame's hue (perf_bins.js `sourceColours`), so a frame has one colour on every
 * catalogue card; the measure is told apart by fill and shape, never by hue. Under Compare all the rows are
 * grouped by species (labelled "Proton · Absolute" …, groups ruled apart): species are never a second hue
 * family.
 *
 * ## Badges
 *
 * A reserved column at the right prints the row's flags in the warning ink, as text: "label leakage" for a
 * leak flag of the report (F8), and "leakage signal" where the tree fitted to truth beats the network on
 * truth (`leakSignal`). In the per-shower translated and Local segmentation frames that signal matches the
 * report's own leakage caveat; elsewhere the report gives no reason, so it is a warning, not a finding.
 *
 * `triangleModel` decides everything (the notes reuse it); `triangleLayout` places it at a width;
 * `distillTriangleOption` draws it; `plotHeight` is what the panel sets on its plot before ECharts measures.
 */

import { THEME, axisPadding, formatInt, typographic } from '../scale.js';
import { DATASETS } from '../catalog/benchmarks.js';
import { LEAK_TEXT, r2Text } from '../catalog/gating.js';
import { measureText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import { sourceColours } from './perf_bins.js';
import {
  ChartPanel, FINE_STEPS, baseOption, emptyChartOption, escapeHtml, fitName, legendTop,
  legibleOpacity, mutedLine, niceCeil, niceInterval, valueAxis, wrapTooltip, wrappedLegend,
} from './chart_panel.js';

/* ------------------------------------------------------- shared wording -- */

/** What every catalogue tooltip and drawer says of an uncertainty (Martin's recorded exception). */
export const POINT_ESTIMATE = 'point estimate as reported; no interval';
/** What a catalogue mark says when the report prints no sample size for it. */
export const N_NOT_REPORTED = 'N not reported';
/** The report's frames, in the dashboard's order. */
export const CATALOG_FRAMES = Object.freeze(['absolute', 'trans', 'local']);

/** The frame hues of every catalogue card: E2's qualitative hues (perf_bins.js), measured on the card in force. */
export function frameColours() {
  return sourceColours([...CATALOG_FRAMES]);
}

/** A number as the report prints it: its shortest decimal form, U+2212 for a minus. */
export function reported(value) {
  return Number.isFinite(value) ? typographic(String(value)) : '—';
}

/** A reported number with its display unit. */
export function reportedWithUnit(value, unit) {
  if (!Number.isFinite(value)) return '—';
  return `${reported(value)}${unit ? ` ${unit}` : ''}`;
}

/** The muted closing line of every catalogue tooltip: the N and the absent interval. */
export function catalogTipFoot(nText = N_NOT_REPORTED) {
  return mutedLine(`${nText} · ${POINT_ESTIMATE}`);
}

/** The proton accuracy table's validation sample, as the perf-catalog card states it. */
export function protonValidationN() {
  const d = DATASETS.proton;
  return `N = ${formatInt(d.validationEvents)} validation events (${formatInt(d.validationParticles)} particles), the accuracy table's sample`;
}

/** The short names a narrow row label takes: never "Translated" alone (CLAUDE.md, F11). */
const SHORT_FRAME = Object.freeze({ absolute: 'Abs.', trans: 'Per-shower tr.', local: 'Local' });

/* ------------------------------------------------------------- measures -- */

/** The R² measures of the left panel, in drawing order. */
export const R2_MEASURES = Object.freeze([
  Object.freeze({
    key: 'treeNet', name: 'Tree → Network R²', mark: 'solid bar',
    definition: 'the depth-4 surrogate tree\'s R² against the network\'s own validation predictions',
  }),
  Object.freeze({
    key: 'pysrNet', name: 'PySR formula → Network R²', mark: 'outlined bar',
    definition: 'the PySR formula\'s R² against the network\'s own validation predictions (its fidelity to the network, not to the truth)',
  }),
  Object.freeze({
    key: 'treeTruth', name: 'Tree → Truth R² (proton only)', mark: 'tick',
    definition: 'the same depth-4 tree fitted directly to the truth: the capacity limit of the tree',
  }),
]);

/** The MAE measures of the right panel, in drawing order. */
export const MAE_MEASURES = Object.freeze([
  Object.freeze({ key: 'netTruth', name: 'Network → Truth MAE', mark: 'filled circle', definition: 'the network\'s mean absolute error against the truth' }),
  Object.freeze({ key: 'treeTruth', name: 'Tree → Truth MAE', mark: 'hollow circle', definition: 'the tree fitted to the truth: its mean absolute error against the truth' }),
  Object.freeze({ key: 'treeNet', name: 'Tree → Network MAE', mark: 'hollow square', definition: 'the tree\'s mean absolute error against the network\'s predictions' }),
  Object.freeze({ key: 'formula', name: 'PySR formula → Truth MAE', mark: 'filled diamond', definition: 'the PySR formula\'s mean absolute error against the true angle (the report\'s angle table)' }),
]);

/** The badge texts of the reserved column, full and short. */
export const BADGE_TEXT = Object.freeze({
  leak: Object.freeze({ full: 'label leakage', short: 'leak' }),
  signal: Object.freeze({ full: 'leakage signal', short: 'signal' }),
});

/* ---------------------------------------------------------------- model -- */

/** One R² mark: what is drawn and what is said. Null when the report gives none. */
export function r2Mark(q) {
  if (!q) return null;
  const lt = q.qualifier === 'lt';
  const none = q.qualifier === 'none' || (!lt && !Number.isFinite(q.value));
  if (none) return { q, reported: false, drawn: null, clamped: false, text: r2Text(q), exact: 'the report gives no value' };
  const negative = lt || q.value < 0;
  const drawn = negative ? 0 : Math.min(1, q.value);
  let exact;
  if (lt) exact = 'reported only as < 0, with no number';
  else if (q.qualifier === 'approx') exact = `reported as ≈ ${reported(q.value)}`;
  else if (q.qualifier === 'about') exact = `reported as ~${reported(q.value)}`;
  else exact = `${reported(q.value)} exactly as reported`;
  return {
    q, reported: true, drawn, clamped: negative, approx: q.qualifier === 'approx',
    text: r2Text(q), exact,
  };
}

/** The leakage-signal sentence in the wording the lead fixed (brief section 11). */
export function leakSignalWording(row, frameLabels = {}) {
  if (!row?.leakSignal) return null;
  const frame = frameLabels[row.frame] ?? row.frame;
  const caveat = (row.leaks ?? []).length > 0;
  const base = row.leakSignalText ?? 'The tree fitted to the truth beats the network on the truth.';
  return caveat
    ? `${base} In the ${frame} frame this matches the report's own leakage caveat (${(row.leaks ?? []).map((f) => LEAK_TEXT[f] ?? f).join(' ')}).`
    : `${base} In the ${frame} frame the report gives no reason for it, so it is a warning, not a finding.`;
}

/**
 * Everything the chart and the drawer need, decided once. Pure:
 * { task, unit, unitLabel, scope, compare, species, rows, groups, maeMax, maeTop, hasTreeTruth, hasFormula,
 *   clamped: [{ row, measure, text }], badges }.
 */
export function triangleModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.rows)) return null;
  const unit = payload.unit ?? '';
  const task = payload.task ?? opts.task ?? 'energy';
  const colours = frameColours();
  const speciesLabels = payload.speciesLabels ?? {};
  const frameLabels = payload.frameLabels ?? {};
  const species = [...(payload.species ?? [])];
  const compare = species.length > 1;
  const clamped = [];
  const rows = payload.rows.map((r, index) => {
    const r2 = {};
    for (const m of R2_MEASURES) {
      r2[m.key] = r2Mark(r.r2?.[m.key] ?? null);
      if (r2[m.key]?.clamped) clamped.push({ index, measure: m.key, text: r2[m.key].exact });
    }
    const mae = {};
    for (const m of MAE_MEASURES) {
      const v = r.mae?.[m.key];
      mae[m.key] = Number.isFinite(v) ? v : null;
    }
    const sLabel = speciesLabels[r.species] ?? r.species;
    const fLabel = frameLabels[r.frame] ?? r.frame;
    const badges = [];
    if ((r.leaks ?? []).length) badges.push('leak');
    if (r.leakSignal) badges.push('signal');
    return {
      index,
      key: `${r.species}:${r.frame}`,
      species: r.species,
      frame: r.frame,
      speciesLabel: sLabel,
      frameLabel: fLabel,
      label: compare ? `${sLabel} · ${fLabel}` : fLabel,
      shortLabel: compare ? `${sLabel} · ${SHORT_FRAME[r.frame] ?? fLabel}` : (SHORT_FRAME[r.frame] ?? fLabel),
      colour: colours[r.frame] ?? THEME.text,
      r2,
      mae,
      maeSource: r.maeSource ?? {},
      maeScope: r.maeScope ?? 'validation',
      formulaAbsent: Boolean(r.formulaAbsent),
      leaks: [...(r.leaks ?? [])],
      leakSignal: Boolean(r.leakSignal),
      leakSignalText: leakSignalWording(r, frameLabels),
      missing: [...(r.missing ?? [])],
      badges,
      noTreeMae: mae.treeTruth === null && mae.treeNet === null,
      noMae: MAE_MEASURES.every((m) => mae[m.key] === null),
    };
  });
  const groups = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.species === row.species) last.end = row.index;
    else groups.push({ species: row.species, label: row.speciesLabel, start: row.index, end: row.index });
  }
  const values = rows.flatMap((r) => MAE_MEASURES.map((m) => r.mae[m.key])).filter(Number.isFinite);
  const maeMax = values.length ? Math.max(...values) : null;
  const maeTop = maeMax === null ? null : niceCeil(maeMax, FINE_STEPS);
  const segmentation = task === 'segmentation';
  return {
    task,
    unit,
    unitLabel: unit ? ` [${unit}]` : '',
    scope: segmentation ? 'voxel-sample' : 'validation',
    compare,
    species,
    speciesLabels,
    frameLabels,
    rows,
    groups,
    maeMax,
    maeTop,
    hasTreeTruth: rows.some((r) => r.r2.treeTruth?.reported),
    hasFormula: rows.some((r) => r.mae.formula !== null),
    clamped,
    leakRows: rows.filter((r) => r.leaks.length),
    signalRows: rows.filter((r) => r.leakSignal),
  };
}

/** The N sentence of one MAE value. */
export function maeNText(row, key) {
  if (key === 'netTruth' && row.maeSource?.netTruth === 'accuracy') return protonValidationN();
  return N_NOT_REPORTED;
}

/** Where one MAE value comes from, in words. */
function maeProvenance(model, row, key) {
  if (model.task === 'segmentation') return 'voxel-sample MAE (energy-weighted), not the validation E-MAE (F5)';
  if (key === 'netTruth' && row.maeSource?.netTruth === 'accuracy') return 'the accuracy table\'s validation MAE';
  if (key === 'formula') return 'the report\'s angle table (formula against the true angle)';
  return model.task === 'angle' ? 'the distillation table, converted from rad (× 1000)' : 'the distillation table';
}

/* --------------------------------------------------------------- layout -- */

/** Row height in px: a compact row under Compare all. */
function rowPxOf(model) {
  const f = THEME.fontLabel;
  return model.compare ? Math.max(22, 2.3 * f) : Math.max(34, 3.4 * f);
}

/** The legend names, in the order drawn. */
function legendNames(model) {
  const names = [R2_MEASURES[0].name, R2_MEASURES[1].name];
  if (model.hasTreeTruth) names.push(R2_MEASURES[2].name);
  for (const m of MAE_MEASURES) {
    if (m.key === 'formula' && !model.hasFormula) continue;
    if (m.key !== 'netTruth' && model.rows.every((r) => r.mae[m.key] === null)) continue;
    if (m.key === 'netTruth' && model.rows.every((r) => r.mae.netTruth === null)) continue;
    names.push(m.name);
  }
  return names;
}

/** Each legend entry's swatch: the mark's own shape and fill, in the text ink (the hue is the frame's). */
function legendIcon(name) {
  const solid = { color: THEME.text, borderColor: THEME.text, borderWidth: 0 };
  const hollow = { color: THEME.card, borderColor: THEME.text, borderWidth: 1.25 };
  const byName = {
    [R2_MEASURES[0].name]: { icon: 'rect', itemStyle: solid },
    [R2_MEASURES[1].name]: { icon: 'rect', itemStyle: hollow },
    // A tick: a thin vertical bar.
    [R2_MEASURES[2].name]: { icon: 'path://M0,0 L2,0 L2,10 L0,10 Z', itemStyle: solid },
    [MAE_MEASURES[0].name]: { icon: 'circle', itemStyle: solid },
    [MAE_MEASURES[1].name]: { icon: 'circle', itemStyle: hollow },
    [MAE_MEASURES[2].name]: { icon: 'rect', itemStyle: hollow },
    [MAE_MEASURES[3].name]: { icon: 'diamond', itemStyle: solid },
  };
  return byName[name] ?? {};
}

/**
 * Where everything sits at `width` px: { stacked, short, labelW, badgeW, rowPx, top, r2: grid, mae: grid,
 * height }. Side by side from 600 px; stacked (R² above, MAE below, each with its row labels) below that.
 */
export function triangleLayout(model, width = 1100) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const w = Math.max(240, width || 1100);
  const stacked = w < 600;
  const n = Math.max(1, model.rows.length);
  const rowPx = rowPxOf(model);
  const fullLabel = Math.max(...model.rows.map((r) => measureText(r.label, f, THEME.fontFamily)), 40);
  const short = fullLabel > 0.26 * w;
  const labelText = short ? Math.max(...model.rows.map((r) => measureText(r.shortLabel, f, THEME.fontFamily)), 30) : fullLabel;
  const labelW = Math.ceil(labelText + 1.2 * f);
  const badgeTexts = model.rows.map((r) => badgeLine(r, short));
  const badgeW = badgeTexts.some(Boolean)
    ? Math.ceil(Math.max(...badgeTexts.map((t) => measureText(t, THEME.fontSmall, THEME.fontFamily))) + 1.2 * f)
    : Math.ceil(0.6 * f);
  const plotWidth = Math.max(80, w - pad.left - pad.right);
  const top = legendTop(legendNames(model), plotWidth, { wrap: true }) + 0.4 * f;
  const blockH = n * rowPx;
  const left = Math.ceil(0.6 * f + labelW);
  const right = Math.ceil(badgeW + pad.right * 0.6);
  if (!stacked) {
    const avail = Math.max(160, w - left - right);
    const gap = 3 * f;
    const r2W = Math.round((avail - gap) * 0.44);
    const maeW = Math.max(60, avail - gap - r2W);
    return {
      stacked, short, labelW, badgeW, rowPx, top, width: w,
      r2: { left, top, width: r2W, height: blockH },
      mae: { left: left + r2W + gap, top, width: maeW, height: blockH },
      badgeX: left + r2W + gap + maeW + 0.6 * f,
      height: Math.round(top + blockH + pad.bottom),
    };
  }
  const avail = Math.max(80, w - left - right);
  const secondTop = top + blockH + pad.bottom + 0.8 * f;
  return {
    stacked, short, labelW, badgeW, rowPx, top, width: w,
    r2: { left, top, width: avail, height: blockH },
    mae: { left, top: secondTop, width: avail, height: blockH },
    badgeX: left + avail + 0.6 * f,
    height: Math.round(secondTop + blockH + pad.bottom),
  };
}

/** The badge text of a row, full or short; '' for none. */
function badgeLine(row, short) {
  if (!row.badges.length) return '';
  return `⚑ ${row.badges.map((b) => (short ? BADGE_TEXT[b].short : BADGE_TEXT[b].full)).join(' · ')}`;
}

/** The plot height the panel sets before ECharts measures: rows × row height, plus the legend and axis. */
export function plotHeight(payload, opts = {}, width = 1100) {
  const model = triangleModel(payload, opts);
  if (!model) return 340;
  return triangleLayout(model, width).height;
}

/* -------------------------------------------------------------- tooltips -- */

function leakLines(row) {
  const out = row.leaks.map((f) => mutedLine(`Label leakage: ${LEAK_TEXT[f] ?? f}`));
  if (row.leakSignalText) out.push(mutedLine(row.leakSignalText));
  return out;
}

/** The tooltip of one R² mark. */
export function r2Tip(model, row, measure) {
  const mark = row.r2[measure.key];
  const lines = [`<b>${escapeHtml(row.speciesLabel)} · ${escapeHtml(row.frameLabel)} — ${escapeHtml(measure.name)}</b>`];
  if (!mark) {
    lines.push('not reported');
  } else {
    lines.push(`R² = ${escapeHtml(mark.text)}${mark.clamped ? ' — drawn at 0: worse than predicting the mean' : ''}`);
    lines.push(mutedLine(mark.exact));
  }
  if (measure.key === 'pysrNet' && row.formulaAbsent) lines.push(mutedLine('PySR gives no meaningful formula for this model; the printed R² is kept (dashed outline).'));
  lines.push(mutedLine(measure.definition));
  lines.push(...leakLines(row));
  lines.push(catalogTipFoot());
  return lines.join('<br/>');
}

/** The tooltip of one MAE mark. */
export function maeTip(model, row, measure) {
  const v = row.mae[measure.key];
  const lines = [`<b>${escapeHtml(row.speciesLabel)} · ${escapeHtml(row.frameLabel)} — ${escapeHtml(measure.name)}: ${escapeHtml(reportedWithUnit(v, model.unit))}</b>`];
  lines.push(mutedLine(measure.definition));
  lines.push(mutedLine(maeProvenance(model, row, measure.key)));
  lines.push(...leakLines(row));
  lines.push(catalogTipFoot(maeNText(row, measure.key)));
  return lines.join('<br/>');
}

/* ---------------------------------------------------------------- marks -- */

const caretPoints = (x, y, size) => [[x, y], [x + size, y - 0.6 * size], [x + size, y + 0.6 * size]];

/** The R² series: one custom series per measure, so the legend toggles each. */
function r2Series(model, layout) {
  const rowPx = layout.rowPx;
  const half = Math.max(5, 0.3 * rowPx);
  const label = !model.compare;
  const font = THEME.fontSmall;
  const out = [];
  const textOf = (text, x, y, fill = THEME.text) => ({
    type: 'text',
    silent: true,
    style: { x, y, text, fill, fontSize: font, fontFamily: THEME.fontFamily, textVerticalAlign: 'middle' },
  });
  for (const m of R2_MEASURES) {
    const rows = model.rows.filter((r) => r.r2[m.key]?.reported);
    if (!rows.length) continue;
    const solidSwatch = m.key === 'treeNet';
    out.push({
      type: 'custom',
      name: m.name,
      xAxisIndex: 0,
      yAxisIndex: 0,
      clip: false,
      z: m.key === 'treeTruth' ? 6 : 4,
      itemStyle: solidSwatch ? { color: THEME.text } : { color: THEME.card, borderColor: THEME.text, borderWidth: 1 },
      data: rows.map((r) => [r.r2[m.key].drawn, r.index]),
      renderItem: (params, api) => {
        const row = rows[params.dataIndex];
        const mark = row.r2[m.key];
        const c0 = api.coord([0, row.index]);
        const c1 = api.coord([mark.drawn, row.index]);
        const colour = row.colour;
        const children = [];
        if (m.key === 'treeTruth') {
          children.push({
            type: 'line',
            shape: { x1: c1[0], y1: c0[1] - 0.42 * rowPx, x2: c1[0], y2: c0[1] + 0.42 * rowPx },
            style: { stroke: colour, lineWidth: 2.5 * THEME.lineAxis, opacity: legibleOpacity(colour, 1) },
          });
        } else {
          const upper = m.key === 'treeNet';
          const y = upper ? c0[1] - half - 1 : c0[1] + 1;
          const width = Math.max(0, c1[0] - c0[0]);
          if (width > 0) {
            children.push(upper
              ? { type: 'rect', shape: { x: c0[0], y, width, height: half }, style: { fill: colour, opacity: legibleOpacity(colour, 0.9) } }
              : {
                type: 'rect',
                shape: { x: c0[0] + 0.5, y: y + 0.5, width: Math.max(0, width - 1), height: half - 1 },
                style: {
                  fill: colour, opacity: 1, fillOpacity: THEME.bandAlpha * 0.6, stroke: colour,
                  strokeOpacity: legibleOpacity(colour, 1), lineWidth: 1.25 * THEME.lineAxis,
                  lineDash: row.formulaAbsent ? [3, 2] : null,
                },
              });
          }
          const yMid = y + half / 2;
          if (mark.clamped) {
            children.push({ type: 'polygon', shape: { points: caretPoints(c0[0] + 1, yMid, Math.max(5, half * 0.8)) }, style: { fill: THEME.text } });
            const exact = label && Number.isFinite(mark.q.value) ? ` (${reported(mark.q.value)})` : '';
            children.push(textOf(`R² < 0${exact}`, c0[0] + Math.max(5, half * 0.8) + 4, yMid));
          } else if (mark.approx && mark.drawn === 0) {
            children.push(textOf('≈ 0', c0[0] + 4, yMid));
          } else if (label) {
            children.push(textOf(mark.text, c1[0] + 4, yMid, THEME.muted));
          }
          if (!upper && row.formulaAbsent && label) {
            const at = Math.max(c1[0], c0[0]) + 4 + (mark.clamped ? 52 : 28);
            children.push(textOf('no formula', at, yMid, THEME.muted));
          }
        }
        return { type: 'group', children };
      },
      tooltip: { formatter: (p) => r2Tip(model, rows[p.dataIndex], m) },
    });
  }
  return out;
}

/** The MAE dumbbells: the connector, then one custom series per measure. */
function maeSeries(model, layout) {
  const out = [];
  const rowPx = layout.rowPx;
  const offset = Math.max(5, 0.27 * rowPx);
  const r = Math.max(3, Math.min(4.5, 0.18 * rowPx));
  const pairs = model.rows.filter((row) => row.mae.netTruth !== null && row.mae.treeTruth !== null);
  if (pairs.length) {
    out.push({
      type: 'custom',
      name: 'Network vs tree on truth',
      xAxisIndex: 1,
      yAxisIndex: 1,
      clip: true,
      z: 3,
      silent: true,
      data: pairs.map((row) => [row.mae.netTruth, row.index]),
      renderItem: (params, api) => {
        const row = pairs[params.dataIndex];
        const a = api.coord([row.mae.netTruth, row.index]);
        const b = api.coord([row.mae.treeTruth, row.index]);
        return {
          type: 'line',
          shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
          style: { stroke: row.colour, lineWidth: 1.5 * THEME.lineAxis, opacity: legibleOpacity(row.colour, 0.6) },
        };
      },
    });
  }
  for (const m of MAE_MEASURES) {
    const rows = model.rows.filter((row) => row.mae[m.key] !== null);
    if (!rows.length) continue;
    const filled = m.key === 'netTruth' || m.key === 'formula';
    out.push({
      type: 'custom',
      name: m.name,
      xAxisIndex: 1,
      yAxisIndex: 1,
      clip: true,
      z: 5,
      itemStyle: filled ? { color: THEME.text } : { color: THEME.card, borderColor: THEME.text, borderWidth: 1 },
      data: rows.map((row) => [row.mae[m.key], row.index]),
      renderItem: (params, api) => {
        const row = rows[params.dataIndex];
        const c = api.coord([row.mae[m.key], row.index]);
        const colour = row.colour;
        const stroke = { stroke: colour, lineWidth: 1.5 * THEME.lineAxis, strokeOpacity: legibleOpacity(colour, 1) };
        if (m.key === 'netTruth') return { type: 'circle', shape: { cx: c[0], cy: c[1], r }, style: { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis } };
        if (m.key === 'treeTruth') return { type: 'circle', shape: { cx: c[0], cy: c[1], r }, style: { fill: THEME.card, ...stroke } };
        if (m.key === 'treeNet') {
          const y = c[1] + offset;
          return { type: 'rect', shape: { x: c[0] - r, y: y - r, width: 2 * r, height: 2 * r }, style: { fill: THEME.card, ...stroke } };
        }
        const y = c[1] - offset;
        return {
          type: 'polygon',
          shape: { points: [[c[0], y - 1.3 * r], [c[0] + 1.3 * r, y], [c[0], y + 1.3 * r], [c[0] - 1.3 * r, y]] },
          style: { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis },
        };
      },
      tooltip: { formatter: (p) => maeTip(model, rows[p.dataIndex], m) },
    });
  }
  // What the report does not give, said in the row itself.
  const gaps = model.rows.filter((row) => row.noMae || (row.noTreeMae && row.mae.netTruth !== null));
  if (gaps.length) {
    out.push({
      type: 'custom',
      name: 'not reported',
      xAxisIndex: 1,
      yAxisIndex: 1,
      clip: false,
      z: 2,
      data: gaps.map((row) => [row.mae.netTruth ?? 0, row.index]),
      renderItem: (params, api) => {
        const row = gaps[params.dataIndex];
        const c = api.coord([row.mae.netTruth ?? 0, row.index]);
        const long = row.noMae
          ? (model.task === 'segmentation' && row.species === 'proton' ? 'no voxel-sample MAE in the report' : 'no MAE in the report')
          : 'tree MAEs not reported';
        const text = layout.short ? (row.noMae ? 'no MAE reported' : 'no tree MAE') : long;
        // Beside the marker; before it where the plot ends first and there is room on that side.
        const right = api.coord([model.maeTop ?? 1, row.index])[0];
        const gap = row.noMae ? 4 : r + 6;
        const width = measureText(text, THEME.fontSmall, THEME.fontFamily);
        const left = api.coord([0, row.index])[0];
        const before = !row.noMae && c[0] + gap + width > right && c[0] - gap - width >= left;
        return {
          type: 'text',
          style: {
            x: before ? c[0] - gap : c[0] + gap, y: c[1], text, textAlign: before ? 'right' : 'left',
            fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, textVerticalAlign: 'middle',
          },
        };
      },
      tooltip: { formatter: (p) => [`<b>${escapeHtml(gaps[p.dataIndex].label)}</b>`, ...gaps[p.dataIndex].missing.map((t) => mutedLine(t)), catalogTipFoot()].join('<br/>') },
    });
  }
  return out;
}

/** The species-group rules and the badge column, as graphic elements. */
function decorations(model, layout) {
  const out = [];
  const f = THEME.fontLabel;
  const blocks = layout.stacked ? [layout.r2, layout.mae] : [layout.r2];
  const xRight = layout.stacked ? layout.r2.left + layout.r2.width : layout.mae.left + layout.mae.width;
  for (const block of blocks) {
    for (const g of model.groups.slice(1)) {
      const y = block.top + g.start * layout.rowPx;
      out.push({
        type: 'line', silent: true,
        shape: { x1: 0.4 * f, y1: y, x2: xRight, y2: y },
        style: { stroke: THEME.muted, lineWidth: THEME.lineGrid, lineDash: [2, 3], opacity: 0.8 },
      });
    }
  }
  for (const block of (layout.stacked ? [layout.r2, layout.mae] : [layout.r2])) {
    for (const row of model.rows) {
      const text = badgeLine(row, layout.short);
      if (!text) continue;
      out.push({
        type: 'text', silent: true,
        style: {
          x: layout.badgeX, y: block.top + (row.index + 0.5) * layout.rowPx, text, fill: THEME.warn,
          fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, textVerticalAlign: 'middle',
        },
      });
    }
  }
  return out;
}

/** A category axis over the rows: labels on the left (hidden on the second panel side by side). */
function rowAxis(model, gridIndex, labels, short) {
  return {
    type: 'category',
    gridIndex,
    inverse: true,
    data: model.rows.map((r) => r.key),
    axisLine: { show: true, lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: {
      show: labels,
      color: THEME.muted,
      fontSize: THEME.fontLabel,
      fontFamily: THEME.fontFamily,
      formatter: (value) => {
        const row = model.rows.find((r) => r.key === value);
        return row ? (short ? row.shortLabel : row.label) : value;
      },
    },
  };
}

/**
 * The option. Pure: `opts` = { species, task, tooltipPosition? }; `metrics` = { width, height }.
 * Returns { option, plotGrid } (the union of the two grids, for the tooltip placement).
 */
export function distillTriangleOption(payload, opts = {}, metrics = {}) {
  const model = triangleModel(payload, opts);
  if (!model || !model.rows.length) return { option: emptyChartOption(opts, metrics, 'The training report has no distillation rows for this choice.') };
  const layout = triangleLayout(model, metrics.width || 1100);
  const f = THEME.fontLabel;
  const segmentation = model.task === 'segmentation';
  const maeName = segmentation
    ? fitName(['Voxel-sample MAE (energy-weighted; not the validation E-MAE)', 'Voxel-sample MAE (not the E-MAE)', 'Voxel-sample MAE'], layout.mae.width)
    : fitName([`MAE${model.unitLabel} — from zero`, `MAE${model.unitLabel}`], layout.mae.width);
  const r2Name = fitName(['R² — fidelity, 0 to 1 (R² < 0 drawn at 0)', 'R² (0 to 1)', 'R²'], layout.r2.width);
  const grid = [
    { left: layout.r2.left, top: layout.r2.top, width: layout.r2.width, height: layout.r2.height },
    { left: layout.mae.left, top: layout.mae.top, width: layout.mae.width, height: layout.mae.height },
  ];
  const maeTop = model.maeTop ?? 1;
  const xAxis = [
    valueAxis({ gridIndex: 0, name: r2Name, min: 0, max: 1, interval: 0.25, split: true, nameGap: 2.4 * f }),
    valueAxis({
      gridIndex: 1, name: maeName, min: 0, max: maeTop, interval: niceInterval(maeTop), split: true,
      labels: model.maeTop !== null, nameGap: 2.4 * f,
    }),
  ];
  const yAxis = [rowAxis(model, 0, true, layout.short), rowAxis(model, 1, layout.stacked, layout.short)];
  const series = [...r2Series(model, layout), ...maeSeries(model, layout)];
  const legendData = legendNames(model).map((name) => ({ name, ...legendIcon(name) }));
  const graphic = decorations(model, layout);
  if (model.maeTop === null) {
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: layout.mae.left + layout.mae.width / 2, y: layout.mae.top + layout.mae.height / 2,
        text: 'The report gives no MAE for these models.', textAlign: 'center', textVerticalAlign: 'middle',
        fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily,
      },
    });
  }
  const pad = axisPadding();
  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      legend: wrappedLegend(legendData, { left: pad.left, right: pad.right }),
      grid,
      xAxis,
      yAxis,
      graphic,
      series,
    },
    plotGrid: grid,
  };
}

/* ---------------------------------------------------------------- class -- */

export class DistillTrianglePanel extends ChartPanel {
  constructor(elementOrId, { card = null, aspect } = {}) {
    super(elementOrId, { kind: 'distill-triangle', aspect });
    this.card = card;
  }

  buildOption({ payload, opts = {}, metrics }) {
    return distillTriangleOption(payload, opts, metrics);
  }

  /** Set the plot's height from the rows before ECharts measures (Compare all needs more). */
  syncHeight() {
    if (!this.element?.style || !this.lastPayload) return;
    const width = this.element.clientWidth || 1100;
    const px = `${plotHeight(this.lastPayload, this.lastOpts ?? {}, width)}px`;
    if (this.element.style.height !== px) {
      this.element.style.height = px;
      return true;
    }
    return false;
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    this.syncHeight();
    super.render(payload, opts);
  }

  relayout() {
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.relayout();
  }

  exportMetrics(width) {
    if (!this.lastPayload) return super.exportMetrics(width);
    return { width, height: plotHeight(this.lastPayload, this.lastOpts ?? {}, width) };
  }
}
