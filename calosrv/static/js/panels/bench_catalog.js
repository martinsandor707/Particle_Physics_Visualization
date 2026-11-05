/* perf-catalog: the training report's validation accuracy, by species, task and frame.
 *
 * The payload is static (`catalog/select.js` `catalogPayload('perf-catalog', …)`, see its header): the
 * report's documented point estimates (`models_performance.md`). The report prints no interval for any of
 * them and nothing here derives one (Martin's recorded exception, 2026-11-05): every mark is a point
 * estimate as reported, every tooltip names its N, and the drawer's hazard is "no interval reported".
 *
 * ## Four facets, never a dual axis
 *
 * Segmentation E-MAE, Angle MAE [mrad], Energy MAE [GeV] and Energy R² [0–1] each take a facet of their own
 * with their own zero-based value axis; no two quantities share an axis. A facet is a horizontal bar chart:
 * one bar per frame, coloured by the frame's E2 hue (`perf_bins.js` `sourceColours`, ≥ 3:1 on the card), so a
 * frame keeps its colour across every card. Under Compare all the rows are grouped by species, which is
 * named by a direct label, never by a second hue family.
 *
 * - A bar starts at zero. An R² below zero (or reported only as "< 0") is clamped at zero with an "R² < 0"
 *   mark; the exact or qualified value is in its tooltip and the drawer.
 * - The proton's TTA value is a tick across its bar, its RMSE a hollow marker in the same unit; the report
 *   gives neither for the other species, and the card says "TTA not reported" for them.
 * - The angle facet takes `opts.angleScale` 'linear' | 'log'. On Log10 the bars become dots (a Cleveland
 *   dot plot): a bar measured from an arbitrary log floor encodes nothing, so a bar is never drawn on log.
 * - A frame the report flags for label leakage (Local angle: rotated by the true θ; Per-shower translated
 *   and Local segmentation: defined per particle) carries a "leak" label beside its mark.
 *
 * The secondary metrics (bias, R², the overlap-core MAE, the tree's R² to the network) go into a compact
 * screen-only table after the card's `.plot-frame`, and into the tooltips; the export is the plot alone.
 *
 * The module also holds the helpers the other three Performance catalogue cards share (frame hues, the
 * "as reported" number text, the tooltip footer, the self-sizing panel class and the DOM table builder).
 * No colour literal: every colour is a THEME token or an E2 frame hue.
 */

import { THEME, axisPadding, formatInt } from '../scale.js';
import { contrast } from '../palette.js';
import { measureText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import { leakFlags, LEAK_TEXT } from '../catalog/gating.js';
import { printed, printedQualified } from '../catalog/select.js';
import { sourceColours } from './perf_bins.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, emptyChartOption, withColour,
  wrappedLegend, legendTop, legibleOpacity, rgbOf, niceCeil, niceInterval, FINE_STEPS, tickLabel,
} from './chart_panel.js';

/* ================================================================ shared == */

/** What every catalogue tooltip and drawer says about a mark's precision. */
export const POINT_ESTIMATE = 'point estimate as reported; no interval';

/** The hazard every catalogue card's Details button carries. */
export const NO_INTERVAL = 'no interval reported';

/** The words of a species without a count. */
export const N_NOT_REPORTED = 'N not reported';

/** The report's frames, in E2's order. */
export const CATALOG_FRAMES = Object.freeze(['absolute', 'trans', 'local']);

/** The card width a layout assumes when the element has none yet (a wide Models card). */
export const DEFAULT_WIDTH = 1100;

/** A round zero-based axis top at or above `value` (FINE_STEPS mantissas), free of binary noise. */
export function niceTop(value) {
  return Number(niceCeil(value > 0 ? value : 1, FINE_STEPS).toPrecision(12));
}

/** The tick interval that lands on `niceTop`'s top exactly. */
export function niceStep(top) {
  return Number(niceInterval(top).toPrecision(12));
}

/** The frame hues on the card in force: E2's qualitative hues, each ≥ 3:1 (perf_bins.js). */
export function frameHues() {
  return sourceColours([...CATALOG_FRAMES]);
}

/**
 * A stored number as the report printed it, with the report's own decimals `dp` (the payload's `dp`;
 * select.js `printed`), never re-rounded, U+2212 for a minus; '—' when absent. Without a count it prints in
 * its shortest form, which is only right for an integer.
 */
export function reported(value, dp = null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return printed(value, dp);
}

/** A signed number as reported, with an explicit + for a positive value (the report prints "+11,9"). */
export function signedReported(value, dp = null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return printed(value, dp, { sign: true });
}

/** `text` followed by its unit ('' for a unitless quantity). */
export function withUnit(text, unit) {
  return unit ? `${text} ${unit}` : text;
}

/** A qualified scalar ({value, qualifier}) as the report printed it: "~1,050", "≈ 0", "< 0", "20–40". */
export function qualifiedText(q, { thousands = false } = {}) {
  if (q === null || q === undefined) return 'not reported';
  if (typeof q === 'number') return thousands ? formatInt(q) : reported(q);
  const n = (v) => (thousands ? formatInt(v) : reported(v, q.dp ?? null));
  if (Array.isArray(q.range)) {
    const range = `${n(q.range[0])}–${n(q.range[1])}`;
    return q.qualifier === 'about' ? `~${range}` : q.qualifier === 'approx' ? `≈ ${range}` : range;
  }
  if (q.qualifier === 'none') return 'not reported';
  if (q.qualifier === 'lt') return `< ${n(q.bound ?? 0)}`;
  if (!Number.isFinite(q.value)) return 'not reported';
  if (q.qualifier === 'about') return `~${n(q.value)}`;
  if (q.qualifier === 'approx') return `≈ ${n(q.value)}`;
  return n(q.value);
}

/** A label from the payload's own label maps, else the key. */
export function labelOf(payload, kind, key) {
  const map = { frame: payload?.frameLabels, species: payload?.speciesLabels, task: payload?.taskLabels }[kind] ?? {};
  return map?.[key] ?? String(key ?? '');
}

/**
 * The report's English wording of a frame, in the dashboard's vocabulary: its `trans` frame is the
 * Per-shower translated frame (CLAUDE.md, F11), never "translated" alone, which names the D-frame.
 */
export function frameWords(text) {
  return String(text ?? '').replace(/\b([Tt])ranslated\b/g, (match, t, offset, whole) => {
    if (/per-shower\s$/i.test(whole.slice(Math.max(0, offset - 11), offset))) return match;
    return t === 'T' ? 'Per-shower translated' : 'per-shower translated';
  });
}

/** The N sentence of an accuracy row: the validation events and particles, derived ones said so. */
export function accuracyN(n) {
  if (!n || !Number.isFinite(n.events)) return N_NOT_REPORTED;
  const particles = Number.isFinite(n.particles)
    ? ` (${formatInt(n.particles)} particles${n.nDerived ? ', derived as 2 per combined event' : ''})` : '';
  return `N = ${formatInt(n.events)} validation combined events${particles}`;
}

/** The common footer of every catalogue tooltip: the N line and the point-estimate line. */
export function tipFooter(nLine) {
  return [escapeHtml(nLine ?? N_NOT_REPORTED), mutedLine(POINT_ESTIMATE)];
}

/** Text ink on the card: a THEME text token, raised to 4.5:1 if it ever fell short (it does not). */
export function textInk(colour = THEME.muted) {
  const card = rgbOf(THEME.card) ?? [28, 33, 40];
  const rgb = rgbOf(colour);
  return rgb && contrast(rgb, card) >= 4.5 ? colour : THEME.text;
}

/** A plain text graphic in the chart's type (a facet title, a note line). */
export function textGraphic(text, x, y, { colour = THEME.muted, size = THEME.fontLabel, align = 'left', weight = 'normal' } = {}) {
  return {
    type: 'text',
    silent: true,
    style: {
      x, y, text, fill: textInk(colour), fontSize: size, fontFamily: THEME.fontFamily, textAlign: align,
      fontWeight: weight,
    },
  };
}

/** A category axis in the shared style; `labels` maps an index to its text ('' to hide it). */
export function categoryAxis({ gridIndex, data, labels = null, inverse = false, show = true, name = '', nameGap }) {
  return {
    type: 'category',
    gridIndex,
    data,
    inverse,
    name,
    nameLocation: 'middle',
    ...(nameGap !== undefined ? { nameGap } : {}),
    nameTextStyle: { color: THEME.muted, fontSize: THEME.fontName, fontFamily: THEME.fontFamily },
    boundaryGap: true,
    axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: false },
    axisLabel: {
      show,
      interval: 0,
      color: THEME.muted,
      fontSize: THEME.fontLabel,
      fontFamily: THEME.fontFamily,
      ...(labels ? { formatter: (value, index) => labels(index, value) } : {}),
    },
    splitLine: { show: false },
  };
}

/** A horizontal zero rule across a grid: a thin muted line at y = 0, named so its tooltip can explain it. */
export function zeroRuleSeries({ name, xAxisIndex, yAxisIndex, tooltip }) {
  return {
    type: 'custom',
    name,
    xAxisIndex,
    yAxisIndex,
    clip: true,
    z: 3,
    data: [[0, 0, 0]],
    renderItem: (params, api) => {
      const box = params.coordSys;
      const y = api.coord([0, 0])[1];
      return {
        type: 'line',
        shape: { x1: box.x, y1: y, x2: box.x + box.width, y2: y },
        style: { stroke: textInk(THEME.muted), lineWidth: 1.2 * THEME.lineAxis, opacity: 1 },
      };
    },
    tooltip: { formatter: () => tooltip },
  };
}

/**
 * The base of the Performance catalogue's chart cards: a ChartPanel that sets its own plot height
 * synchronously from the payload and the width (`heightFor`), before ECharts measures, and that may hang
 * screen-only DOM after the card's `.plot-frame` (`renderExtra`), removed again by `clear()`.
 */
export class CatalogChartPanel extends ChartPanel {
  constructor(elementOrId, { card = null, kind = 'catalog', aspect } = {}) {
    super(elementOrId, { kind, aspect });
    this.card = card;
    this.extraHost = null;
  }

  /** The plot height the layout wants at `width`; subclasses delegate to their pure `plotHeight`. */
  heightFor() {
    return null;
  }

  /** Size the plot element for the retained payload at its width (the default width before layout). */
  fitHeight(width = null) {
    if (!this.element || !this.lastPayload) return false;
    const w = width || this.element.clientWidth || DEFAULT_WIDTH;
    const wanted = this.heightFor(w);
    if (!wanted) return false;
    const now = Number.parseFloat(this.element.style?.height ?? '');
    if (now === wanted) return false;
    if (this.element.style) this.element.style.height = `${wanted}px`;
    return true;
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    // Before ECharts creates or measures the chart: the card is born at the height it needs.
    this.fitHeight();
    super.render(payload, opts);
    this.renderExtra();
  }

  paint() {
    if (this.chart && this.lastPayload) {
      const { width } = this.size();
      if (width && this.fitHeight(width)) this.chart.resize();
    }
    const option = super.paint();
    // Held while the card has no size (its subpage hidden): forget when it was laid out, so the relayout
    // that shows it builds the option afresh. Without this, a theme switch made on another subpage left
    // the dark picture on the light card (ChartPanel.relayout returns early when the size is unchanged).
    if (option === null && this.lastPayload) this.laidOut = null;
    return option;
  }

  exportMetrics(width) {
    const wanted = this.lastPayload ? this.heightFor(width) : null;
    return wanted ? { width, height: wanted } : super.exportMetrics(width);
  }

  /** Screen-only DOM after the plot frame; none by default. */
  renderExtra() {}

  /** The host of the screen-only DOM, created once after the card's `.plot-frame`; null outside a card. */
  ensureExtraHost(className = '') {
    if (this.extraHost) return this.extraHost;
    const card = this.element?.closest?.('.card');
    const frame = card?.querySelector?.('.plot-frame');
    if (!frame || typeof frame.after !== 'function') return null;
    const doc = frame.ownerDocument ?? globalThis.document;
    const host = doc.createElement('div');
    if (className) host.className = className;
    if (host.dataset) host.dataset.catalogExtra = this.card ?? this.kind;
    frame.after(host);
    this.extraHost = host;
    return host;
  }

  clear() {
    super.clear();
    if (this.extraHost) {
      this.extraHost.remove?.();
      this.extraHost = null;
    }
  }
}

/**
 * A table from plain cells, text nodes only (never parsed markup): `{caption, columns, rows: [[cell]],
 * textColumns: [index], rowHeaders: true}`. A cell is a string, or `{text, title}`.
 */
export function buildTable(doc, { caption = null, columns, rows, textColumns = [0], rowHeader = true }) {
  const el = (tag, text = null) => {
    const node = doc.createElement(tag);
    if (text !== null && text !== undefined) node.textContent = text;
    return node;
  };
  const table = el('table');
  if (caption) table.append(el('caption', caption));
  const head = el('thead');
  const tr = el('tr');
  columns.forEach((c, i) => {
    const th = el('th', c);
    th.setAttribute?.('scope', 'col');
    th.className = textColumns.includes(i) ? 'text' : 'num';
    tr.append(th);
  });
  head.append(tr);
  table.append(head);
  const body = el('tbody');
  for (const row of rows) {
    const line = el('tr');
    row.forEach((cell, i) => {
      const text = typeof cell === 'object' && cell !== null ? cell.text : cell;
      const node = el(i === 0 && rowHeader ? 'th' : 'td', text);
      if (i === 0 && rowHeader) node.setAttribute?.('scope', 'row');
      node.className = textColumns.includes(i) ? 'text' : 'num';
      if (typeof cell === 'object' && cell?.title) node.title = cell.title;
      line.append(node);
    });
    body.append(line);
  }
  table.append(body);
  return table;
}

/* ============================================================ the model == */

/** Bar thickness as a share of a row's slot. */
const BAR_SHARE = 0.64;
const BAR_MAX_PX = 16;
/** Fill opacity of a bar (E2's solid bar); its outline is the ink a reader must see. */
const BAR_FILL = 0.78;
const DOT_PX = 4;
const MARKER_PX = 3.5;
/** Row slot heights: one species, and the grouped rows of Compare all. */
const SLOT_ONE_PX = 26;
const SLOT_ALL_PX = 14;
/** The narrowest a facet's plot may be before the facets take fewer columns. */
const MIN_FACET_PLOT_PX = 150;
/** Room right of each facet for the "leak" label and the bar's end. */
const RIGHT_INSET_PX = 34;

/** The value a facet draws for a row: its metric, or the energy R². */
function facetValue(facet, row) {
  if (facet.key === 'energy-r2') return row.r2 ?? null;
  return row.value;
}

/** The leak flags drawn on a facet's row (the report's own caveats; never a tier cap here). */
function rowLeaks(facet, row) {
  return facet.key === 'energy-r2' ? [] : leakFlags({ task: row.task, frame: row.frame });
}

/**
 * Everything the chart, the table and the drawer need, decided once. Pure:
 * {species, scale, facets: [{key, label, unit, task, rows: [{key, species, frame, row, value, r2, clamped,
 * qualifier, leaks}], axis: {type, min, max, interval}, dots}], rowsOf, notReported, ttaSpecies, rmseSpecies,
 * clamped, leaks}.
 */
export function benchCatalogModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.rows) || !Array.isArray(payload.facets)) return null;
  const species = payload.species ?? [];
  const scale = opts.angleScale === 'log' ? 'log' : 'linear';
  const all = species.length > 1;
  // The rows of every facet, in order: species groups (a spacer between them), frames within.
  const keys = [];
  species.forEach((s, i) => {
    if (i > 0) keys.push(`gap:${i}`);
    for (const f of CATALOG_FRAMES) keys.push(`${s}:${f}`);
  });
  let clamped = 0;
  const leaksDrawn = new Set();
  const facets = payload.facets.map((facet) => {
    const rows = [];
    for (const s of species) {
      for (const frame of CATALOG_FRAMES) {
        const row = payload.rows.find((r) => r.species === s && r.task === facet.task && r.frame === frame);
        if (!row) continue;
        const raw = facetValue(facet, row);
        const q = raw && typeof raw === 'object' ? raw : (Number.isFinite(raw) ? { value: raw, qualifier: null } : null);
        const negative = q && (q.qualifier === 'lt' || (Number.isFinite(q.value) && q.value < 0));
        const value = !q || !Number.isFinite(q.value) ? (negative ? 0 : null) : (negative ? 0 : q.value);
        if (negative) clamped += 1;
        const leaks = rowLeaks(facet, row);
        leaks.forEach((l) => leaksDrawn.add(l));
        const dp = row.dp ?? {};
        rows.push({
          key: `${s}:${frame}`, index: keys.indexOf(`${s}:${frame}`), species: s, frame, row, value,
          q: q && facet.key !== 'energy-r2' ? { ...q, dp: dp.value ?? null } : q, clamped: Boolean(negative), leaks,
          dp: { value: facet.key === 'energy-r2' ? q?.dp ?? null : dp.value ?? null, tta: dp.tta ?? null, rmse: dp.rmse ?? null },
          tta: facet.key === 'energy-r2' ? null : row.tta, rmse: facet.key === 'energy-r2' ? null : row.rmse,
        });
      }
    }
    const dots = facet.key === 'angle' && scale === 'log';
    const marks = rows.flatMap((r) => [r.value, r.tta, r.rmse]).filter((v) => Number.isFinite(v));
    let axis;
    if (facet.key === 'energy-r2') {
      axis = { type: 'value', min: 0, max: 1, interval: 0.2 };
    } else if (dots) {
      const positive = marks.filter((v) => v > 0);
      const lo = positive.length ? 10 ** Math.floor(Math.log10(Math.min(...positive))) : 0.1;
      const hi = positive.length ? 10 ** Math.ceil(Math.log10(Math.max(...positive))) : 1;
      axis = { type: 'log', min: lo, max: hi > lo ? hi : lo * 10 };
    } else {
      const top = niceTop(Math.max(...marks, 0));
      axis = { type: 'value', min: 0, max: top, interval: niceStep(top) };
    }
    const label = dots ? `${facet.label}, log₁₀ axis` : facet.label;
    return { ...facet, label, rows, axis, dots };
  });
  const has = (field) => species.filter((s) => payload.rows.some((r) => r.species === s && Number.isFinite(r[field])));
  return {
    species,
    all,
    scale,
    keys,
    facets,
    notReported: payload.notReported ?? { tta: [], rmse: [], bias: [] },
    ttaSpecies: has('tta'),
    rmseSpecies: has('rmse'),
    clamped,
    leaks: [...leaksDrawn],
  };
}

/* ============================================================ the layout == */

/** How many facet columns fit `width`: 4, 2 or 1. */
export function facetColumns(width, insetPx) {
  const pad = axisPadding();
  const usable = Math.max(80, width - pad.left - pad.right);
  for (const cols of [4, 2]) {
    const facetW = (usable - (cols - 1) * 1.2 * THEME.fontLabel) / cols;
    if (facetW - insetPx - RIGHT_INSET_PX >= MIN_FACET_PLOT_PX) return cols;
  }
  return 1;
}

/** The y labels of the facets' rows: the frame (one species) or the species on its group's middle row. */
function rowLabels(model, payload) {
  return model.keys.map((key) => {
    if (key.startsWith('gap:')) return '';
    const [s, f] = key.split(':');
    if (!model.all) return labelOf(payload, 'frame', f);
    return f === 'trans' ? labelOf(payload, 'species', s) : '';
  });
}

/** The legend entries: the frames, and the proton's TTA tick and RMSE marker where drawn. */
function legendEntries(model, payload) {
  const out = CATALOG_FRAMES.map((f) => ({ name: labelOf(payload, 'frame', f), icon: 'rect' }));
  if (model.ttaSpecies.length) out.push({ name: TTA_NAME, icon: 'path://M3,0 L5,0 L5,10 L3,10 Z' });
  if (model.rmseSpecies.length) out.push({ name: RMSE_NAME, icon: 'emptyCircle' });
  return out;
}

const TTA_NAME = 'TTA value (tick)';
const RMSE_NAME = 'RMSE (hollow marker)';

/** The note line under the legend: the species without TTA, and the axes rule under Compare all. */
function noteText(model, payload) {
  const parts = [];
  const without = model.species.filter((s) => !model.ttaSpecies.includes(s));
  if (without.length) parts.push(`TTA not reported: ${without.map((s) => labelOf(payload, 'species', s)).join(', ')}`);
  if (model.scale === 'log') parts.push('angle on a log₁₀ axis: dots, never bars');
  return parts.join(' · ');
}

/**
 * Where everything goes at `width`: {top, noteY, cols, inset, facets: [{facet, grid, titleY}], height}.
 * Laid out from the width alone, so `plotHeight` and the builder agree.
 */
export function benchCatalogLayout(model, payload, width = DEFAULT_WIDTH) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const legend = legendEntries(model, payload);
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const top = legendTop(legend, plotWidthPx, { wrap: true });
  const note = noteText(model, payload);
  const noteH = note ? 1.6 * f : 0;
  const labels = rowLabels(model, payload);
  const inset = Math.max(...labels.map((t) => measureText(t, THEME.fontLabel, THEME.fontFamily)), 20) + 0.9 * f + 6;
  const cols = facetColumns(width, inset);
  const gap = 1.2 * f;
  const titleH = 1.9 * f;
  const xLabelH = 2.2 * f;
  const slot = model.all ? SLOT_ALL_PX : SLOT_ONE_PX;
  const gridH = Math.max(60, model.keys.length * slot);
  const facetW = (plotWidthPx + pad.left + pad.right - 2 * (0.6 * f) - (cols - 1) * gap) / cols;
  const placed = [];
  let y = top + noteH;
  model.facets.forEach((facet, i) => {
    const col = i % cols;
    if (col === 0 && i > 0) y += titleH + gridH + xLabelH;
    const x = 0.6 * f + col * (facetW + gap);
    placed.push({
      facet,
      titleX: x,
      titleY: y + 0.35 * f,
      grid: { left: x + inset, top: y + titleH, width: Math.max(40, facetW - inset - RIGHT_INSET_PX), height: gridH },
      titleW: facetW,
    });
  });
  const height = Math.ceil(y + titleH + gridH + xLabelH + 0.6 * f);
  return { top, noteY: top, note, cols, inset, slot, labels, legend, facets: placed, height };
}

/** The plot height the card needs (Compare all takes more rows). Pure. */
export function plotHeight(payload, opts = {}, width = DEFAULT_WIDTH) {
  const model = benchCatalogModel(payload, opts);
  if (!model) return 330;
  return Math.max(200, benchCatalogLayout(model, payload, width).height);
}

/* ============================================================ tooltips == */

/** The tooltip of one mark: the quantity and value, the proton's extras, the N and the point-estimate line. */
export function catalogTip(payload, facet, r) {
  const sp = labelOf(payload, 'species', r.species);
  const fr = labelOf(payload, 'frame', r.frame);
  const unit = facet.unit;
  const name = facet.key === 'energy-r2' ? 'Energy R² to truth' : facet.label.replace(/ \[.*$/, '').replace(/, log₁₀ axis$/, '');
  const shown = facet.key === 'energy-r2' ? printedQualified(r.q) : reported(r.value, r.dp?.value);
  const lines = [`<b>${escapeHtml(sp)} · ${escapeHtml(fr)} · ${escapeHtml(name)}: ${escapeHtml(withUnit(shown, unit))}</b>`];
  if (r.clamped) {
    lines.push(escapeHtml(`R² < 0: drawn clamped at 0 with an "R² < 0" mark; the report prints ${printedQualified(r.q)}`));
  }
  if (facet.key !== 'energy-r2') {
    lines.push(Number.isFinite(r.tta)
      ? escapeHtml(`with test-time augmentation (TTA): ${withUnit(reported(r.tta, r.dp?.tta), unit)} — the tick across the bar`)
      : escapeHtml(`TTA not reported for the ${sp.toLowerCase()}`));
    const extra = [];
    if (Number.isFinite(r.rmse)) extra.push(`RMSE ${withUnit(reported(r.rmse, r.dp?.rmse), unit)} (hollow marker)`);
    if (Number.isFinite(r.row.bias)) extra.push(`bias ${withUnit(signedReported(r.row.bias, r.row.dp?.bias), unit)} (signed error as reported)`);
    if (Number.isFinite(r.row.coreMae)) extra.push(`overlap-core MAE ${reported(r.row.coreMae, r.row.dp?.coreMae)}`);
    if (r.row.r2 && facet.key !== 'segmentation') extra.push(`R² to truth ${printedQualified(r.row.r2)}`);
    if (Number.isFinite(r.row.treeR2Net)) extra.push(`tree R² to the network ${reported(r.row.treeR2Net, r.row.dp?.treeR2Net)}`);
    if (extra.length) lines.push(escapeHtml(extra.join(' · ')));
  }
  for (const flag of r.leaks) lines.push(mutedLine(`leak: ${LEAK_TEXT[flag]}`));
  if (r.row.task === 'angle' || r.row.task === 'energy') lines.push(mutedLine(LEAK_TEXT['oracle-separation']));
  lines.push(...tipFooter(accuracyN(r.row.n)));
  return lines.join('<br/>');
}

/* ============================================================== option == */

/**
 * The perf-catalog option. Pure: `opts` = {angleScale?: 'linear' | 'log', tooltipPosition?}; `metrics` =
 * {width, height}. Returns {option, plotGrid}.
 */
export function benchCatalogOption(payload, opts = {}, metrics = {}) {
  const model = benchCatalogModel(payload, opts);
  if (!model) return { option: emptyChartOption(opts, metrics, 'No catalogue payload.') };
  const width = metrics.width || DEFAULT_WIDTH;
  const layout = benchCatalogLayout(model, payload, width);
  const hues = frameHues();
  const pad = axisPadding();
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = [];
  const ink = THEME.text;

  if (layout.note) graphic.push(textGraphic(layout.note, 0.6 * THEME.fontLabel, layout.noteY));

  layout.facets.forEach(({ facet, grid, titleX, titleY, titleW }, index) => {
    grids.push(grid);
    graphic.push(textGraphic(fitName([facet.label, facet.label.replace(/ \[.*$/, '')], titleW), titleX, titleY,
      { colour: THEME.text }));
    xAxes.push(valueAxis({
      gridIndex: index, type: facet.axis.type, min: facet.axis.min, max: facet.axis.max,
      ...(facet.axis.interval ? { interval: facet.axis.interval } : {}), split: true, formatter: tickLabel,
    }));
    yAxes.push(categoryAxis({
      gridIndex: index, data: model.keys, inverse: true, labels: (i) => layout.labels[i] ?? '',
    }));
    const thick = Math.min(BAR_MAX_PX, BAR_SHARE * layout.slot);
    const at = (api, v, idx) => api.coord([v, idx]);
    const base = facet.axis.type === 'log' ? facet.axis.min : 0;

    for (const frame of CATALOG_FRAMES) {
      const rows = facet.rows.filter((r) => r.frame === frame && r.value !== null);
      const colour = hues[frame];
      const stroke = legibleOpacity(colour, 1);
      series.push(withColour({
        type: 'custom',
        name: labelOf(payload, 'frame', frame),
        xAxisIndex: index,
        yAxisIndex: index,
        clip: true,
        z: 4,
        data: rows.map((r, i) => [r.value, r.index, i]),
        renderItem: (params, api) => {
          const r = rows[params.dataIndex];
          const end = at(api, r.value, r.index);
          if (facet.dots) {
            return {
              type: 'circle',
              shape: { cx: end[0], cy: end[1], r: DOT_PX },
              style: { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis },
            };
          }
          const start = at(api, base, r.index);
          return {
            type: 'rect',
            shape: { x: Math.min(start[0], end[0]), y: end[1] - thick / 2, width: Math.abs(end[0] - start[0]), height: thick },
            style: {
              fill: colour, opacity: 1, fillOpacity: BAR_FILL, stroke: colour, strokeOpacity: stroke,
              lineWidth: THEME.lineAxis,
            },
          };
        },
        tooltip: { formatter: (p) => catalogTip(payload, facet, rows[p.dataIndex]) },
      }, colour));
    }

    // The proton's TTA tick: text ink on a canvas casing, so it reads over the bar and over the card.
    const tta = facet.rows.filter((r) => Number.isFinite(r.tta));
    if (tta.length) {
      series.push(withColour({
        type: 'custom',
        name: TTA_NAME,
        xAxisIndex: index,
        yAxisIndex: index,
        clip: true,
        z: 6,
        data: tta.map((r, i) => [r.tta, r.index, i]),
        renderItem: (params, api) => {
          const r = tta[params.dataIndex];
          const c = at(api, r.tta, r.index);
          const half = thick / 2 + 2;
          const shape = { x1: c[0], y1: c[1] - half, x2: c[0], y2: c[1] + half };
          return {
            type: 'group',
            children: [
              { type: 'line', shape, style: { stroke: THEME.canvas, lineWidth: 3.2 * THEME.lineAxis } },
              { type: 'line', shape, style: { stroke: ink, lineWidth: 1.4 * THEME.lineAxis } },
            ],
          };
        },
        tooltip: { formatter: (p) => catalogTip(payload, facet, tta[p.dataIndex]) },
      }, ink));
    }
    const rmse = facet.rows.filter((r) => Number.isFinite(r.rmse));
    if (rmse.length) {
      series.push(withColour({
        type: 'custom',
        name: RMSE_NAME,
        xAxisIndex: index,
        yAxisIndex: index,
        clip: true,
        z: 7,
        data: rmse.map((r, i) => [r.rmse, r.index, i]),
        renderItem: (params, api) => {
          const r = rmse[params.dataIndex];
          const c = at(api, r.rmse, r.index);
          return {
            type: 'circle',
            shape: { cx: c[0], cy: c[1], r: MARKER_PX },
            style: { fill: THEME.card, stroke: ink, lineWidth: 1.3 * THEME.lineAxis },
          };
        },
        tooltip: { formatter: (p) => catalogTip(payload, facet, rmse[p.dataIndex]) },
      }, ink));
    }

    // Text marks beside the mark's end: "R² < 0" on a clamped R², "leak" on a flagged frame.
    const labelled = facet.rows.filter((r) => r.clamped || r.leaks.length);
    if (labelled.length) {
      series.push({
        type: 'custom',
        name: 'catalogue marks',
        xAxisIndex: index,
        yAxisIndex: index,
        clip: false,
        z: 8,
        data: labelled.map((r, i) => [r.value ?? 0, r.index, i]),
        renderItem: (params, api) => {
          const r = labelled[params.dataIndex];
          const reach = Math.max(...[r.value, r.tta, r.rmse].filter(Number.isFinite), base);
          const c = at(api, reach, r.index);
          const text = [r.clamped ? 'R² < 0' : null, r.leaks.length ? 'leak' : null].filter(Boolean).join(' · ');
          return {
            type: 'text',
            style: {
              x: c[0] + MARKER_PX + 4, y: c[1], text, fill: textInk(THEME.muted), fontSize: THEME.fontSmall,
              fontFamily: THEME.fontFamily, textVerticalAlign: 'middle',
            },
          };
        },
        tooltip: { formatter: (p) => catalogTip(payload, facet, labelled[p.dataIndex]) },
      });
    }
  });

  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      legend: wrappedLegend(layout.legend, { left: pad.left, right: pad.right }),
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
export function drawnColours(payload, opts = {}) {
  const model = benchCatalogModel(payload, opts);
  if (!model) return [];
  const hues = frameHues();
  const out = CATALOG_FRAMES.map((f) => ({ colour: hues[f], role: 'mark', opacity: legibleOpacity(hues[f], 1) }));
  out.push({ colour: THEME.text, role: 'mark', opacity: 1 });
  out.push({ colour: textInk(THEME.muted), role: 'text', opacity: 1 });
  return out;
}

/** The secondary-metrics table's rows, as strings (U+2212 for a minus). Pure. */
export function secondaryTableRows(payload) {
  if (!payload || !Array.isArray(payload.rows)) return null;
  const order = (r) => [payload.species.indexOf(r.species), ['segmentation', 'angle', 'energy'].indexOf(r.task), CATALOG_FRAMES.indexOf(r.frame)];
  const rows = [...payload.rows].sort((a, b) => {
    const x = order(a);
    const y = order(b);
    return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
  });
  const unitOf = (r) => (r.task === 'segmentation' ? '' : r.unit);
  return {
    caption: 'Secondary metrics as the training report gives them: point estimates, no interval; '
      + '— = not reported. Angle in mrad, energy in GeV; the segmentation E-MAE and every R² are unitless.',
    columns: ['Species', 'Task', 'Frame', 'Main metric', 'TTA', 'RMSE', 'Bias (signed, as reported)', 'R² to truth',
      'Overlap-core MAE', 'Tree R² to the network', 'Validation N'],
    rows: rows.map((r) => [
      labelOf(payload, 'species', r.species),
      labelOf(payload, 'task', r.task),
      labelOf(payload, 'frame', r.frame),
      `${r.metric === 'e-mae' ? 'E-MAE' : 'MAE'} ${withUnit(reported(r.value, r.dp?.value), unitOf(r))}`,
      Number.isFinite(r.tta) ? withUnit(reported(r.tta, r.dp?.tta), unitOf(r)) : '—',
      Number.isFinite(r.rmse) ? withUnit(reported(r.rmse, r.dp?.rmse), unitOf(r)) : '—',
      Number.isFinite(r.bias) ? withUnit(signedReported(r.bias, r.dp?.bias), unitOf(r)) : '—',
      r.r2 ? printedQualified(r.r2) : '—',
      reported(r.coreMae, r.dp?.coreMae),
      reported(r.treeR2Net, r.dp?.treeR2Net),
      r.n ? `${formatInt(r.n.events)} events / ${formatInt(r.n.particles)} particles${r.n.nDerived ? ' (derived)' : ''}` : N_NOT_REPORTED,
    ]),
  };
}

/* =============================================================== class == */

export class BenchCatalogPanel extends CatalogChartPanel {
  constructor(elementOrId, { card = 'perf-catalog', aspect } = {}) {
    super(elementOrId, { card, kind: 'bench-catalog', aspect });
  }

  heightFor(width) {
    return plotHeight(this.lastPayload, this.lastOpts ?? {}, width);
  }

  buildOption({ payload, opts = {}, metrics }) {
    return benchCatalogOption(payload, opts, metrics);
  }

  /** The screen-only secondary-metrics table after the plot frame. */
  renderExtra() {
    const host = this.ensureExtraHost('catalog-table');
    if (!host) return;
    const model = secondaryTableRows(this.lastPayload);
    if (!model) {
      host.replaceChildren();
      return;
    }
    const doc = host.ownerDocument ?? globalThis.document;
    host.replaceChildren(buildTable(doc, { ...model, textColumns: [0, 1, 2] }));
  }
}
