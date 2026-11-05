/* perf-overlap: the training report's error by overlap bin, per species, task and frame.
 *
 * The payload is static (`catalog/select.js` `catalogPayload('perf-overlap', …)`): the report's overlap
 * tables, point estimates as reported with no interval (Martin's recorded exception, 2026-11-05).
 *
 * ## Marks
 *
 * - x is the five ordered overlap bins as the report prints them (0 %, 10 %, 20 %, 30 %, 40–100 %); y is the
 *   error from zero in the task's unit (segmentation E-MAE unitless, angle in mrad, energy in GeV).
 * - One series per frame: dots joined by thin lines, in the frame's E2 hue (`perf_bins.js` `sourceColours`).
 *   The lines only join ordered bins of one table; they claim nothing between them.
 * - "All" is the overlap table's own total ("összes"), not the headline metric of the accuracy table: a
 *   dotted horizontal rule per frame in the frame's hue, never a sixth category on the bin axis.
 * - An N strip under the plot: the proton's events per bin as bars from zero, with their counts; the report
 *   prints no per-bin N for the muon, electron and pion, so their strip says "N not reported" (F2) and no
 *   proton count is ever borrowed. The proton's bins hold 4,054 of its 4,065 events: the 11 in no bin are
 *   named on the strip (F1).
 * - Every facet carries the unit badge of its rows (F3): "per hit" (every segmentation row, and the proton's
 *   angle and energy rows, which the report titles hit-level) or "per particle" (the new species' angle and
 *   energy rows). The two are different estimands; Compare all never puts them on one axis.
 * - Compare all draws one facet per species, each zero-based on its own axis, and says so.
 * - The proton energy rows at the 30 % and 40–100 % bins carry the report's information-starvation note:
 *   one "info-starved" label over a bracket spanning both bins, in a band of its own between the facet
 *   title and the plot, so it never sits on a dot. The report's figures (mean momentum 3.3 GeV, about 8 MeV
 *   deposited) are one statement about the two bins together, and the tooltip says so.
 *
 * Every header line wraps at the chart's width, the N strip sits a label height below the plot (so the
 * plot's 0 and the strip's top tick never meet) under a line of its own for the unbinned count, and the
 * strip's axis name keeps a gap to the next facet's title: the 321 px single-column export holds every text.
 *
 * No colour literal: every colour is a THEME token or an E2 frame hue.
 */

import { THEME, axisPadding, formatInt } from '../scale.js';
import { printed, printedQualified } from '../catalog/select.js';
import { wrapText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import { LEAK_TEXT, leakFlags } from '../catalog/gating.js';
import {
  baseOption, wrapTooltip, valueAxis, mutedLine, escapeHtml, emptyChartOption, withColour, wrappedLegend,
  legendTop, legibleOpacity, tickLabel, noticeGraphic, fitName,
} from './chart_panel.js';
import {
  AXIS_LABEL_MARGIN, CATALOG_FRAMES, DEFAULT_WIDTH, LINE_PITCH, N_NOT_REPORTED, CatalogChartPanel, categoryAxis,
  frameHues, labelOf, lineGraphics, niceStep, niceTop, textGraphic, textInk, tipFooter, widestLabel, withUnit,
  wrapLines,
} from './bench_catalog.js';

/** The unit badges of the two levels (F3). */
export const LEVEL_BADGES = Object.freeze({ hit: 'per hit', particle: 'per particle' });

/** How each level is described in tooltips and the drawer. */
export const LEVEL_TEXT = Object.freeze({
  hit: 'hit-level MAE, weighted by the event energy',
  hitTitled: 'hit-level, as the report titles the proton\'s overlap table',
  particle: 'particle (shower) level MAE: one value per particle',
});

/** The level sentence of a facet: segmentation rows are energy-weighted hit-level MAEs; the proton's
 * angle and energy rows are hit-level only by the report's title (F3). */
export function levelText(level, task) {
  if (level === 'hit') return task === 'segmentation' ? LEVEL_TEXT.hit : LEVEL_TEXT.hitTitled;
  return LEVEL_TEXT[level] ?? 'level not stated';
}

/** What a facet title adds to its level badge, said once: the badge names the level, this its scope. */
export const LEVEL_TITLE_NOTE = Object.freeze({
  hit: 'energy-weighted',
  hitTitled: 'as the report titles its overlap table',
  particle: 'one value per shower',
});

/**
 * A facet's title, longest first for fitName: "Proton · per hit (as the report titles its overlap table)",
 * "Muon · per hit (energy-weighted)", "Muon · per particle (one value per shower)", then the bare
 * "Species · per hit". The level is named once, never "per hit · hit-level".
 */
export function facetTitle(speciesLabel, level, task) {
  const badge = LEVEL_BADGES[level] ?? '';
  if (!badge) return [speciesLabel];
  const note = level === 'hit' ? (task === 'segmentation' ? LEVEL_TITLE_NOTE.hit : LEVEL_TITLE_NOTE.hitTitled) : LEVEL_TITLE_NOTE[level];
  return [note ? `${speciesLabel} · ${badge} (${note})` : `${speciesLabel} · ${badge}`, `${speciesLabel} · ${badge}`];
}

/** What the "All" rule is (Stage 1 settled: the overlap table's own total). */
export const ALL_NOTE = 'All: the overlap table\'s own total ("összes"), not the headline metric of the accuracy table';

const DOT_PX = 3.5;
const LINE_PX = 1.2;
const MAIN_ONE_PX = 220;
const MAIN_ALL_PX = 150;
const STRIP_PX = 36;
/** The information-starvation band over the plot, in label heights (only where a facet is starved). */
const STARVED_BAND = 1.7;
/** A facet's plot must be at least this wide for two facets to share a row. */
const MIN_TWO_COL_PX = 260;
const ALL_RULE_NAME = 'All (the table\'s total): dotted rule';

/** The quantity's name for a task. */
function quantityName(task) {
  return task === 'segmentation' ? 'E-MAE' : 'MAE';
}

/**
 * Everything the chart and the drawer need, decided once. Pure:
 * {task, unit, bins, facets: [{species, level, events, series: [{frame, values, all, leaks, dp}], axis: {max,
 * interval}, starvation: [binIndex]}], mixedLevels, notReported: [species], unbinned}.
 */
export function benchOverlapModel(payload) {
  if (!payload || !Array.isArray(payload.series) || !Array.isArray(payload.bins)) return null;
  const task = payload.task;
  const species = payload.species ?? [];
  const starvation = (payload.starvation ?? []).filter((s) => s.task === task);
  const facets = species.map((s) => {
    const series = CATALOG_FRAMES.map((frame) => payload.series.find((r) => r.species === s && r.frame === frame))
      .filter(Boolean)
      .map((r) => ({
        frame: r.frame, values: r.values, all: r.all, level: r.level, leaks: leakFlags({ task, frame: r.frame }),
        dp: { all: r.dp?.all ?? null, values: r.dp?.values ?? r.values.map(() => null) },
      }));
    const marks = series.flatMap((r) => [...r.values, r.all]).filter((v) => Number.isFinite(v));
    const top = niceTop(Math.max(...marks, 0));
    const events = payload.events?.[s] ?? null;
    const starved = starvation.filter((st) => st.species === s)
      .flatMap((st) => st.bins.map((key) => payload.bins.findIndex((b) => b.key === key)))
      .filter((i) => i >= 0);
    const stripTop = events ? niceTop(Math.max(...events.bins, 1)) : null;
    return {
      species: s,
      level: payload.levels?.[s] ?? series[0]?.level ?? null,
      events,
      series,
      axis: { min: 0, max: top, interval: niceStep(top) },
      strip: stripTop ? { min: 0, max: stripTop } : null,
      starved,
      starvation: starvation.find((st) => st.species === s) ?? null,
    };
  });
  const levels = new Set(facets.map((f) => f.level).filter(Boolean));
  return {
    task,
    unit: payload.unit ?? '',
    bins: payload.bins,
    facets,
    all: species.length > 1,
    mixedLevels: levels.size > 1,
    notReported: facets.filter((f) => !f.events).map((f) => f.species),
    leaks: [...new Set(facets.flatMap((f) => f.series.flatMap((r) => r.leaks)))],
  };
}

/* ============================================================== layout == */

/** The legend: the three frames and the All rule. */
function legendEntries(payload) {
  return [
    ...CATALOG_FRAMES.map((f) => ({ name: labelOf(payload, 'frame', f), icon: 'circle' })),
    { name: ALL_RULE_NAME, icon: 'path://M0,4 L3,4 L3,6 L0,6 Z M5,4 L8,4 L8,6 L5,6 Z M10,4 L13,4 L13,6 L10,6 Z' },
  ];
}

/** The note under the legend (Compare all only); wrapped by the layout. */
function noteText(model) {
  if (!model.all) return '';
  return model.mixedLevels
    ? 'Each species on its own zero-based axis; per-hit and per-particle errors are different quantities.'
    : 'Each species on its own zero-based axis.';
}

/**
 * Where everything goes at `width`: {top, note, legend, facets: [{facet, titleX, titleY, titleW, main,
 * strip}], height}. Laid out from the width alone.
 */
export function benchOverlapLayout(model, payload, width = DEFAULT_WIDTH) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const legend = legendEntries(payload);
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const top = legendTop(legend, plotWidthPx, { wrap: true });
  const note = noteText(model);
  const noteLines = wrapLines(note, width - 1.2 * f);
  const noteH = noteLines.length * LINE_PITCH * f;
  const n = model.facets.length;
  const gap = 2.4 * f;
  const twoFit = (width - 2 * (pad.left + pad.right) - gap) / 2 >= MIN_TWO_COL_PX;
  const cols = n > 1 && twoFit ? 2 : 1;
  const facetW = (width - (cols - 1) * gap) / cols;
  // The title's line, then the top tick label's upper half above the plot's top edge.
  const titleH = 2.4 * f;
  // One band height for every facet, so the facets of a row stay aligned.
  const bandH = model.facets.some((x) => x.starved.length) ? STARVED_BAND * f : 0;
  const mainH = model.all ? MAIN_ALL_PX : MAIN_ONE_PX;
  // Between the plot and the N strip: the unbinned count's line, and room for the plot's 0 and the
  // strip's top tick, each centred on its grid edge.
  const stripGap = 1.9 * f;
  // Under the strip: its bin labels, its axis name, and a gap before the next facet's title.
  const nameGap = AXIS_LABEL_MARGIN + 1.5 * f;
  const xLabelH = nameGap + 1.4 * f + 0.6 * f;
  const blockH = titleH + bandH + mainH + stripGap + STRIP_PX + xLabelH;
  const placed = model.facets.map((facet, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = col * (facetW + gap);
    const y = top + noteH + row * blockH;
    const left = x + pad.left;
    const w = Math.max(60, facetW - pad.left - pad.right);
    return {
      facet,
      titleX: x + 0.6 * f,
      titleY: y + 0.35 * f,
      titleW: facetW - 1.2 * f,
      main: { left, top: y + titleH + bandH, width: w, height: mainH },
      strip: { left, top: y + titleH + bandH + mainH + stripGap, width: w, height: STRIP_PX },
    };
  });
  const rows = Math.ceil(n / cols);
  return {
    top, note, noteLines, noteH, legend, cols, nameGap, stripGap, facets: placed,
    height: Math.ceil(top + noteH + rows * blockH + 0.6 * f),
  };
}

/** The plot height the card needs (Compare all takes more rows). Pure. */
export function plotHeight(payload, opts = {}, width = DEFAULT_WIDTH) {
  const model = benchOverlapModel(payload);
  if (!model) return 330;
  return Math.max(220, benchOverlapLayout(model, payload, width).height);
}

/* ============================================================ tooltips == */

/** The N line of one bin (or of All) for a facet: the proton's reported count, else "N not reported". */
function binN(facet, i) {
  if (!facet.events) return N_NOT_REPORTED;
  if (i === null) return `N = ${formatInt(facet.events.all)} events (the report's total)`;
  return `N = ${formatInt(facet.events.bins[i])} events in this bin (the report's count)`;
}

/** The tooltip of one dot. */
export function overlapTip(model, payload, facet, series, i) {
  const sp = labelOf(payload, 'species', facet.species);
  const fr = labelOf(payload, 'frame', series.frame);
  const bin = model.bins[i]?.label ?? '';
  const lines = [
    `<b>${escapeHtml(sp)} · ${escapeHtml(fr)} · overlap bin ${escapeHtml(bin)}: ${escapeHtml(quantityName(model.task))} `
      + `${escapeHtml(withUnit(printed(series.values[i], series.dp?.values?.[i]), model.unit))}</b>`,
    escapeHtml(`${LEVEL_BADGES[facet.level] ?? ''}: ${levelText(facet.level, model.task)}`),
    escapeHtml(`All (the table's own total) ${withUnit(printed(series.all, series.dp?.all), model.unit)}: the dotted rule`),
  ];
  if (facet.starved.includes(i) && facet.starvation) lines.push(escapeHtml(starvationText(facet.starvation, model.bins)));
  for (const flag of series.leaks) lines.push(mutedLine(`leak: ${LEAK_TEXT[flag]}`));
  lines.push(...tipFooter(binN(facet, i)));
  return lines.join('<br/>');
}

/** The tooltip of one frame's All rule. */
function allTip(model, payload, facet, series) {
  return [
    `<b>${escapeHtml(labelOf(payload, 'species', facet.species))} · ${escapeHtml(labelOf(payload, 'frame', series.frame))} · All: `
      + `${escapeHtml(quantityName(model.task))} ${escapeHtml(withUnit(printed(series.all, series.dp?.all), model.unit))}</b>`,
    escapeHtml(`${ALL_NOTE}; drawn as a dotted rule, never as a bin`),
    escapeHtml(`${LEVEL_BADGES[facet.level] ?? ''}: ${levelText(facet.level, model.task)}`),
    ...tipFooter(binN(facet, null)),
  ].join('<br/>');
}

/** The printed labels of the starved bins: "30 % and 40–100 %". */
export function starvedBinsText(st, bins = []) {
  const labels = (st?.bins ?? []).map((key) => bins.find((b) => b.key === key)?.label ?? key);
  return labels.length > 1 ? `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}` : (labels[0] ?? '');
}

/**
 * The report's information-starvation sentence (proton energy, high-overlap bins). The report gives one
 * mean over the starved bins together ("in the 30 % and 40–100 % overlap bins the particles have low
 * momentum (mean 3.3 GeV)"), so the sentence names every bin it covers and never says "in this bin".
 */
export function starvationText(st, bins = []) {
  const where = starvedBinsText(st, bins);
  const together = (st?.bins ?? []).length > 1 ? ' together' : '';
  const deposit = st?.deposit?.qualifier === 'none' ? 'not reported' : printedQualified(st?.deposit);
  return `Information starvation (the report): in the ${where} bins${together} the particles have a mean momentum of `
    + `${printed(st?.meanMomentum?.value, st?.meanMomentum?.dp)} ${st?.meanMomentum?.unit ?? 'GeV'} and deposit ${deposit} `
    + `${st?.deposit?.unit ?? 'MeV'}; the larger error is missing information, not a model failure.`;
}

/**
 * The starved bins as runs of adjacent bins, [[first, last], …]: one bracket and one label per run, so the
 * 30 % and 40–100 % bins carry a single "info-starved" label instead of two that run together.
 */
export function starvedRuns(indices) {
  const sorted = [...new Set(indices)].sort((a, b) => a - b);
  const runs = [];
  for (const i of sorted) {
    const last = runs[runs.length - 1];
    if (last && i === last[1] + 1) last[1] = i;
    else runs.push([i, i]);
  }
  return runs;
}

/**
 * The notice of a strip with no reported counts: the longest wording whose wrapped lines fit the strip's
 * height (noticeGraphic wraps at the strip's width), so a narrow export never spills it onto the bin labels.
 */
export function stripNotice(speciesLabel, strip) {
  const candidates = [
    `${N_NOT_REPORTED}: the report prints no per-bin events for the ${speciesLabel.toLowerCase()}`,
    `${N_NOT_REPORTED}: no per-bin events in the report`,
    N_NOT_REPORTED,
  ];
  const fits = (text) => wrapText(text, Math.max(80, strip.width - 8), THEME.fontTip, THEME.fontFamily).length
    * 1.45 * THEME.fontTip <= strip.height;
  return candidates.find(fits) ?? N_NOT_REPORTED;
}

/**
 * The width of an N-strip bar in a bin `slot` px wide: at most 28 px and 0.4 of the slot, and narrow enough
 * that its count, printed right of it, ends before the next bar starts (at 321 px "1,297" ran onto the
 * 10 % bar). Never below 6 px.
 */
export function stripBarWidth(slot, countW) {
  return Math.max(6, Math.min(28, 0.4 * slot, slot - countW - 3 - 3));
}

/** The tooltip of one strip bar. */
function stripTip(model, facet, i) {
  const e = facet.events;
  return [
    `<b>${escapeHtml(model.bins[i]?.label ?? '')}: ${escapeHtml(formatInt(e.bins[i]))} events</b>`,
    escapeHtml(`the report's count; ${formatInt(e.bins.reduce((a, b) => a + b, 0))} of its ${formatInt(e.all)} events lie in the five bins, `
      + `${formatInt(e.unbinned)} in none`),
    mutedLine('a count, not an estimate'),
  ].join('<br/>');
}

/* ============================================================== option == */

/** The perf-overlap option. Pure: `opts` = {tooltipPosition?}; `metrics` = {width, height}. */
export function benchOverlapOption(payload, opts = {}, metrics = {}) {
  const model = benchOverlapModel(payload);
  if (!model) return { option: emptyChartOption(opts, metrics, 'No catalogue payload.') };
  const width = metrics.width || DEFAULT_WIDTH;
  const layout = benchOverlapLayout(model, payload, width);
  const hues = frameHues();
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = [];
  const binLabels = model.bins.map((b) => b.label);
  const unitText = model.unit ? ` [${model.unit}]` : '';

  graphic.push(...lineGraphics(layout.noteLines, 0.6 * f, layout.top));

  layout.facets.forEach(({ facet, titleX, titleY, titleW, main, strip }) => {
    const sp = labelOf(payload, 'species', facet.species);
    graphic.push(textGraphic(fitName(facetTitle(sp, facet.level, model.task), titleW),
      titleX, titleY, { colour: THEME.text }));

    // ---- the main grid
    const gi = grids.length;
    grids.push(main);
    xAxes.push(categoryAxis({ gridIndex: gi, data: binLabels, show: false }));
    yAxes.push(valueAxis({
      gridIndex: gi, min: 0, max: facet.axis.max, interval: facet.axis.interval, split: true,
      name: fitName([`${quantityName(model.task)}${unitText}`, quantityName(model.task)], main.height),
      nameGap: 3.6 * f, formatter: tickLabel,
    }));
    for (const s of facet.series) {
      const colour = hues[s.frame];
      const ink = legibleOpacity(colour, 1);
      const name = labelOf(payload, 'frame', s.frame);
      const points = s.values.map((v, i) => ({ v, i })).filter((p) => Number.isFinite(p.v));
      series.push(withColour({
        type: 'custom',
        name,
        xAxisIndex: gi,
        yAxisIndex: gi,
        clip: true,
        z: 5,
        data: points.map((p, k) => [p.i, p.v, k]),
        renderItem: (params, api) => {
          const p = points[params.dataIndex];
          const c = api.coord([p.i, p.v]);
          const children = [];
          const next = points[params.dataIndex + 1];
          if (next) {
            const d = api.coord([next.i, next.v]);
            children.push({ type: 'line', shape: { x1: c[0], y1: c[1], x2: d[0], y2: d[1] }, style: { stroke: colour, lineWidth: LINE_PX, opacity: ink } });
          }
          children.push({ type: 'circle', shape: { cx: c[0], cy: c[1], r: DOT_PX }, style: { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis } });
          return { type: 'group', children };
        },
        tooltip: { formatter: (p) => overlapTip(model, payload, facet, s, points[p.dataIndex].i) },
      }, colour));
      if (Number.isFinite(s.all)) {
        // Named as the frame, so its legend entry shows and hides the rule with the dots.
        series.push(withColour({
          type: 'custom',
          name,
          xAxisIndex: gi,
          yAxisIndex: gi,
          clip: true,
          z: 3,
          data: [[0, s.all, 0]],
          renderItem: (params, api) => {
            const box = params.coordSys;
            const y = api.coord([0, s.all])[1];
            return {
              type: 'line',
              shape: { x1: box.x, y1: y, x2: box.x + box.width, y2: y },
              style: { stroke: colour, lineWidth: THEME.lineAxis, lineDash: [2, 3], opacity: ink },
            };
          },
          tooltip: { formatter: () => allTip(model, payload, facet, s) },
        }, colour));
      }
    }
    // The legend entry of the All rule (the rules themselves are named as their frames).
    series.push(withColour({ type: 'custom', name: ALL_RULE_NAME, xAxisIndex: gi, yAxisIndex: gi, data: [], renderItem: () => null }, textInk(THEME.muted)));

    if (facet.starved.length && facet.starvation) {
      // One label per run of adjacent starved bins, over a bracket spanning them, in the band between the
      // title and the plot: never two labels side by side, never on a dot.
      const tip = `<b>${escapeHtml('Information-starved bins')}</b><br/>${escapeHtml(starvationText(facet.starvation, model.bins))}`;
      const runs = starvedRuns(facet.starved);
      series.push({
        type: 'custom',
        name: 'information starvation',
        xAxisIndex: gi,
        yAxisIndex: gi,
        clip: false,
        z: 8,
        data: runs.map(([first, last], k) => [first, facet.axis.max, last, k]),
        renderItem: (params, api) => {
          const [first, last] = runs[params.dataIndex];
          const a = api.coord([first, facet.axis.max]);
          const b = api.coord([last, facet.axis.max]);
          const slot = typeof api.size === 'function' ? api.size([1, 0])[0] : main.width / binLabels.length;
          const half = 0.36 * slot;
          const y = a[1] - 0.45 * f;
          const ink = textInk(THEME.muted);
          const line = (x1, y1, x2, y2) => ({ type: 'line', shape: { x1, y1, x2, y2 }, style: { stroke: ink, lineWidth: THEME.lineAxis } });
          return {
            type: 'group',
            children: [
              line(a[0] - half, y, b[0] + half, y),
              line(a[0] - half, y, a[0] - half, y + 0.3 * f),
              line(b[0] + half, y, b[0] + half, y + 0.3 * f),
              {
                type: 'text',
                style: {
                  x: (a[0] + b[0]) / 2, y: y - 0.15 * f, text: 'info-starved', fill: ink, fontSize: THEME.fontSmall,
                  fontFamily: THEME.fontFamily, textAlign: 'center', textVerticalAlign: 'bottom',
                },
              },
            ],
          };
        },
        tooltip: { formatter: () => tip },
      });
    }

    // ---- the N strip
    const si = grids.length;
    grids.push(strip);
    xAxes.push(categoryAxis({ gridIndex: si, data: binLabels, name: fitName(['Overlap bin', ''], strip.width), nameGap: layout.nameGap }));
    if (facet.events) {
      yAxes.push(valueAxis({
        gridIndex: si, min: 0, max: facet.strip.max, interval: facet.strip.max, formatter: tickLabel,
        name: 'N', nameGap: 3.6 * f,
      }));
      const ink = textInk(THEME.muted);
      const countW = widestLabel(facet.events.bins.map((n) => formatInt(n)), THEME.fontSmall);
      series.push(withColour({
        type: 'custom',
        name: 'Events per bin (N strip)',
        xAxisIndex: si,
        yAxisIndex: si,
        clip: false,
        z: 4,
        data: facet.events.bins.map((n, i) => [i, n, i]),
        renderItem: (params, api) => {
          const i = params.dataIndex;
          const n = facet.events.bins[i];
          const base = api.coord([i, 0]);
          const top = api.coord([i, n]);
          const w = stripBarWidth(strip.width / binLabels.length, countW);
          // The count beside its bar's top, but never below the strip's baseline, where the bin labels are.
          const textY = Math.min(Math.min(base[1], top[1]), base[1] - 1.3 * THEME.fontSmall);
          return {
            type: 'group',
            children: [
              {
                type: 'rect',
                shape: { x: base[0] - w / 2, y: Math.min(base[1], top[1]), width: w, height: Math.abs(base[1] - top[1]) },
                style: { fill: ink, opacity: 1, fillOpacity: 0.35, stroke: ink, lineWidth: THEME.lineAxis },
              },
              {
                type: 'text',
                style: {
                  x: base[0] + w / 2 + 3, y: textY, text: formatInt(n), fill: ink,
                  fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, textVerticalAlign: 'top',
                },
              },
            ],
          };
        },
        tooltip: { formatter: (p) => stripTip(model, facet, p.dataIndex) },
      }, ink));
      // On its own line between the plot and the strip, clear of the strip's counts and both grids' ticks.
      graphic.push(textGraphic(`${formatInt(facet.events.unbinned)} of ${formatInt(facet.events.all)} events in no bin`,
        strip.left + strip.width, strip.top - layout.stripGap + 0.65 * f, { align: 'right', size: THEME.fontSmall }));
    } else {
      yAxes.push(valueAxis({ gridIndex: si, min: 0, max: 1, labels: false }));
      graphic.push(noticeGraphic(stripNotice(labelOf(payload, 'species', facet.species), strip),
        strip.left + strip.width / 2, strip.top + strip.height / 2, strip.width));
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
export function drawnColours() {
  const hues = frameHues();
  return [
    ...CATALOG_FRAMES.map((f) => ({ colour: hues[f], role: 'mark', opacity: legibleOpacity(hues[f], 1) })),
    { colour: textInk(THEME.muted), role: 'text', opacity: 1 },
  ];
}

/* =============================================================== class == */

export class BenchOverlapPanel extends CatalogChartPanel {
  constructor(elementOrId, { card = 'perf-overlap', aspect } = {}) {
    super(elementOrId, { card, kind: 'bench-overlap', aspect });
  }

  heightFor(width) {
    return plotHeight(this.lastPayload, this.lastOpts ?? {}, width);
  }

  buildOption({ payload, opts = {}, metrics }) {
    return benchOverlapOption(payload, opts, metrics);
  }
}
