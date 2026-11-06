/* perf-diagnostics: the proton segmentation's indecision, the H200 throughput, the architecture and the
 * report's own caveats.
 *
 * The payload is static (`catalog/select.js` `catalogPayload('perf-diagnostics', …)`). The exportable part is
 * one small chart, the segmentation indecision as dumbbells:
 *
 * - left, the energy-weighted ⟨|2f − 1|⟩ on 0–1 (1 = every voxel decided, 0 = every voxel at f = 0.5);
 * - right, the share of the energy in the undecided band 0.3 ≤ f ≤ 0.7, on 0–100 %;
 * - one row per frame; the network's prediction a filled dot, the truth a hollow one, joined by a thin line
 *   in the frame's E2 hue. Both axes start at zero and are the quantities' whole ranges.
 *
 * Both are measured on the proton models only, and so is the throughput: the report made no speed
 * measurement for the muon, electron and pion and says the proton's numbers must not be copied to them
 * (F10). The heading "Measured on the proton models only" is kept for every species: these blocks are never
 * relabelled with the species on show.
 *
 * After the card's `.plot-frame`, screen only: the throughput table, the architecture and dataset tables
 * (the report states the architecture is identical for the new species) and the caveats that apply to the
 * species and task on show, the report's text with its "translated" frame written Per-shower translated.
 *
 * The row-label gutter is measured from the widest frame label (textfit.js) plus the axis label margin, so
 * "Per-shower translated" starts inside the figure at every width, the 321 px export included.
 *
 * No colour literal: every colour is a THEME token or an E2 frame hue.
 */

import { THEME, axisPadding, formatInt } from '../scale.js';
import { printed, printedQualified } from '../catalog/select.js';
import { tooltipOption } from './tooltip.js';
import {
  baseOption, wrapTooltip, valueAxis, mutedLine, escapeHtml, emptyChartOption, withColour, wrappedLegend,
  legendTop, legibleOpacity, tickLabel, fitName,
} from './chart_panel.js';
import {
  AXIS_LABEL_MARGIN, CATALOG_FRAMES, DEFAULT_WIDTH, N_NOT_REPORTED, CatalogChartPanel, buildTable, categoryAxis,
  frameHues, frameWords, labelOf, textGraphic, textInk, tipFooter, widestLabel,
} from './bench_catalog.js';

/** The scope heading of every proton-only block, whatever species is on show. */
export const PROTON_ONLY = 'Measured on the proton models only';

const PREDICTED_NAME = 'Network prediction (filled)';
const TRUTH_NAME = 'Truth (hollow)';
const DOT_PX = 4.5;
const ROW_PX = 28;
const MIN_SIDE_PX = 200;

/**
 * Everything the chart, the tables and the drawer need. Pure:
 * {panels: [{key, title, unit, scale, max, dp, rows: [{frame, predicted, truth}]}], protonShown, species}.
 * `dp` is the report's printed decimals (INDECISION.dp: 0.69 with two, the shares as whole percentages).
 */
export function benchDiagnosticsModel(payload) {
  const ind = payload?.indecision;
  if (!ind) return null;
  const pol = ind.polarisation ?? {};
  const amb = ind.ambiguousShare ?? {};
  const rows = (block, factor) => CATALOG_FRAMES.map((frame) => ({
    frame,
    predicted: Number.isFinite(block.predicted?.[frame]) ? block.predicted[frame] * factor : null,
    truth: Number.isFinite(block.truth?.[frame]) ? block.truth[frame] * factor : null,
    raw: { predicted: block.predicted?.[frame] ?? null, truth: block.truth?.[frame] ?? null },
  }));
  const band = amb.band ?? [0.3, 0.7];
  return {
    panels: [
      {
        key: 'polarisation', title: 'Energy-weighted ⟨|2f − 1|⟩ [0–1]', short: '⟨|2f − 1|⟩', unit: '', max: 1, interval: 0.2,
        rows: rows(pol, 1), dp: ind.dp?.polarisation ?? null,
      },
      {
        key: 'ambiguous', title: `Energy share with ${printed(band[0])} ≤ f ≤ ${printed(band[1])} [%]`, short: 'Undecided energy share',
        unit: '%', max: 100, interval: 20, rows: rows(amb, 100), dp: ind.dp?.ambiguousSharePercent ?? null,
      },
    ],
    band,
    quantity: ind.quantity ?? 'energy-weighted |2f − 1|, f the predicted or true fraction',
    species: payload.species ?? [],
    protonShown: Boolean(payload.protonShown),
    scope: ind.scope ?? 'proton',
  };
}

/* ============================================================== layout == */

function legendEntries() {
  return [{ name: PREDICTED_NAME, icon: 'circle' }, { name: TRUTH_NAME, icon: 'emptyCircle' }];
}

/**
 * The row-label gutter of a dumbbell panel: the widest frame label at the label font, ECharts' label margin
 * and the panel's own left padding. Measured, never a fixed number of font sizes: at 9.5 font sizes the
 * label "Per-shower translated" started 11-17 px left of the canvas (R2-2).
 */
export function rowInset(payload) {
  const labels = CATALOG_FRAMES.map((fr) => labelOf(payload, 'frame', fr));
  return widestLabel(labels) + AXIS_LABEL_MARGIN + 0.6 * THEME.fontLabel;
}

/** Where everything goes at `width`: {top, headingY, inset, panels: [{panel, grid, titleX, titleY, titleW}], height}. */
export function benchDiagnosticsLayout(model, payload, width = DEFAULT_WIDTH) {
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const legend = legendEntries();
  const top = legendTop(legend, Math.max(80, width - pad.left - pad.right), { wrap: true });
  const headingH = 1.8 * f;
  const titleH = 1.8 * f;
  const xLabelH = 2.4 * f;
  const gridH = CATALOG_FRAMES.length * ROW_PX;
  const inset = rowInset(payload);
  const gap = 2.4 * f;
  const side = (width - gap) / 2 - inset - pad.right >= MIN_SIDE_PX;
  const cellW = side ? (width - gap) / 2 : width;
  const y0 = top + headingH;
  const panels = model.panels.map((panel, k) => {
    const x = side ? k * (cellW + gap) : 0;
    const y = side ? y0 : y0 + k * (titleH + gridH + xLabelH);
    return {
      panel,
      titleX: x + 0.6 * f,
      titleY: y + 0.3 * f,
      titleW: cellW - 1.2 * f,
      grid: { left: x + inset, top: y + titleH, width: Math.max(60, cellW - inset - pad.right), height: gridH },
    };
  });
  const blocks = side ? 1 : 2;
  return { legend, top, headingY: top, inset, panels, height: Math.ceil(y0 + blocks * (titleH + gridH + xLabelH) + 0.6 * f) };
}

/** The plot height the card needs. Pure. */
export function plotHeight(payload, opts = {}, width = DEFAULT_WIDTH) {
  const model = benchDiagnosticsModel(payload);
  if (!model) return 240;
  return Math.max(180, benchDiagnosticsLayout(model, payload, width).height);
}

/* ============================================================ tooltips == */

/** A dumbbell end as the report prints it, with its decimals (`panel.dp`). */
export function valueText(panel, v) {
  if (!Number.isFinite(v)) return 'not reported';
  const value = Number(v.toPrecision(12));
  return panel.unit === '%' ? `${printed(value, panel.dp ?? null)} %` : printed(value, panel.dp ?? null);
}

/** The tooltip of a row's dumbbell. */
export function indecisionTip(model, payload, panel, row) {
  const fr = labelOf(payload, 'frame', row.frame);
  return [
    `<b>Proton segmentation · ${escapeHtml(fr)} · ${escapeHtml(panel.short)}</b>`,
    escapeHtml(`network prediction ${valueText(panel, row.predicted)} (filled) · truth ${valueText(panel, row.truth)} (hollow)`),
    mutedLine(panel.key === 'polarisation'
      ? `${model.quantity}: 1 = every voxel decided, 0 = every voxel at f = 0.5`
      : `the share of the energy in voxels with ${printed(model.band[0])} ≤ f ≤ ${printed(model.band[1])}`),
    escapeHtml(`${PROTON_ONLY}; not reported for the muon, electron and pion`),
    ...tipFooter(N_NOT_REPORTED),
  ].join('<br/>');
}

/* ============================================================== option == */

/** The perf-diagnostics option (the indecision dumbbells). Pure: `opts` = {tooltipPosition?}. */
export function benchDiagnosticsOption(payload, opts = {}, metrics = {}) {
  const model = benchDiagnosticsModel(payload);
  if (!model) return { option: emptyChartOption(opts, metrics, 'No catalogue payload.') };
  const width = metrics.width || DEFAULT_WIDTH;
  const layout = benchDiagnosticsLayout(model, payload, width);
  const hues = frameHues();
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = [textGraphic(fitName([`Proton segmentation indecision — ${PROTON_ONLY.toLowerCase()}`, `Proton segmentation — ${PROTON_ONLY.toLowerCase()}`, PROTON_ONLY], width - 1.2 * f),
    0.6 * f, layout.headingY, { colour: THEME.text })];
  const frameLabels = CATALOG_FRAMES.map((fr) => labelOf(payload, 'frame', fr));

  layout.panels.forEach(({ panel, grid, titleX, titleY, titleW }, index) => {
    grids.push(grid);
    graphic.push(textGraphic(fitName([panel.title, panel.short], titleW), titleX, titleY));
    xAxes.push(valueAxis({ gridIndex: index, min: 0, max: panel.max, interval: panel.interval, split: true, formatter: tickLabel }));
    yAxes.push(categoryAxis({ gridIndex: index, data: frameLabels, inverse: true }));
    const rows = panel.rows.map((row, i) => ({ ...row, i })).filter((r) => Number.isFinite(r.predicted) || Number.isFinite(r.truth));
    const draw = (which, hollow) => (params, api) => {
      const r = rows[params.dataIndex];
      const colour = hues[r.frame];
      const children = [];
      if (!hollow && Number.isFinite(r.predicted) && Number.isFinite(r.truth)) {
        const a = api.coord([r.predicted, r.i]);
        const b = api.coord([r.truth, r.i]);
        children.push({ type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: colour, lineWidth: 1.2 * THEME.lineAxis, opacity: legibleOpacity(colour, 1) } });
      }
      if (Number.isFinite(r[which])) {
        const c = api.coord([r[which], r.i]);
        children.push({
          type: 'circle',
          shape: { cx: c[0], cy: c[1], r: DOT_PX },
          style: hollow
            ? { fill: THEME.card, stroke: colour, lineWidth: 1.6 * THEME.lineAxis }
            : { fill: colour, stroke: THEME.card, lineWidth: THEME.lineAxis },
        });
      }
      return { type: 'group', children };
    };
    series.push(withColour({
      type: 'custom', name: PREDICTED_NAME, xAxisIndex: index, yAxisIndex: index, clip: true, z: 5,
      data: rows.map((r, k) => [r.predicted ?? 0, r.i, k]),
      renderItem: draw('predicted', false),
      tooltip: { formatter: (p) => indecisionTip(model, payload, panel, rows[p.dataIndex]) },
    }, THEME.text));
    series.push(withColour({
      type: 'custom', name: TRUTH_NAME, xAxisIndex: index, yAxisIndex: index, clip: true, z: 6,
      data: rows.map((r, k) => [r.truth ?? 0, r.i, k]),
      renderItem: draw('truth', true),
      tooltip: { formatter: (p) => indecisionTip(model, payload, panel, rows[p.dataIndex]) },
    }, THEME.text));
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
    ...CATALOG_FRAMES.map((fr) => ({ colour: hues[fr], role: 'mark', opacity: legibleOpacity(hues[fr], 1) })),
    { colour: THEME.text, role: 'text', opacity: 1 },
    { colour: textInk(THEME.muted), role: 'text', opacity: 1 },
  ];
}

/* ============================================================== tables == */

/**
 * A qualified report value through `catalog/select.js` `printedQualified` (the one formatter), with the
 * tables' wording for a value the report does not give: "not reported" where select.js prints "none".
 */
function reportedOrNot(q, options = {}) {
  if (q && typeof q === 'object' && q.qualifier === 'none') return 'not reported';
  return printedQualified(q, options);
}

/** A rate and its unit; a rate the report does not give takes no unit ("not reported", not "not reported events/s"). */
function withRate(text, unit) {
  return text === 'not reported' || !unit ? text : `${text} ${unit}`;
}

const TASK_ORDER = ['segmentation', 'angle', 'energy'];

/** The left-aligned (prose) columns of each table; the rest are numbers. */
const TEXT_COLUMNS = Object.freeze({ throughput: [0, 4], architecture: [0, 1, 2, 5], frames: [0, 1, 5], datasets: [0] });

/**
 * The screen-only blocks after the plot frame, as plain data (strings only, U+2212 for a minus). Pure:
 * [{key, heading, scope, table?: {caption, columns, rows}, list?: [{text, scope}]}].
 */
export function diagnosticsBlocks(payload) {
  if (!payload) return [];
  const fl = (k) => labelOf(payload, 'frame', k);
  const tl = (k) => labelOf(payload, 'task', k);
  const blocks = [];
  const shownNames = (payload.species ?? []).map((s) => labelOf(payload, 'species', s)).join(', ');

  const t = payload.throughput;
  if (t) {
    const div = t.ttaDivisor ?? {};
    const tta = `÷${div.absolute ?? '—'} (${fl('absolute')}), ÷${div.trans ?? '—'} (${fl('trans')}), ÷${div.local ?? '—'} (${fl('local')})`;
    blocks.push({
      key: 'throughput',
      label: 'the H200 throughput table',
      heading: `Throughput on one ${t.gpu ?? 'H200'} (${t.mode ?? 'forward pass only'})`,
      scope: `${PROTON_ONLY}. The report made no speed measurement for the muon, electron and pion and says these numbers must not be copied to them${payload.protonShown ? '' : `; shown here for the proton, not for ${shownNames}`}.`,
      table: {
        caption: 'Rates as the report gives them (~ = about); no interval reported. TTA divides each forward-pass rate as listed.',
        columns: ['Task', 'Forward pass', 'With TTA', 'Grad-CAM / Shap-CAM', 'Note'],
        rows: TASK_ORDER.filter((k) => t.forward?.[k]).map((k) => {
          const fw = t.forward[k];
          const slow = fw.queryHeadSlowdown;
          // A share printed as a percentage: its decimals move two places (0.03 → 3 %).
          const slowPct = slow ? { ...slow, value: Number((slow.value * 100).toPrecision(12)),
            dp: Number.isInteger(slow.dp) ? Math.max(0, slow.dp - 2) : null } : null;
          const note = slowPct
            ? `the particle-query head (${fl('trans')} and ${fl('local')}) slows it by ${reportedOrNot(slowPct)} %`
            : '—';
          return [
            tl(k),
            withRate(reportedOrNot(fw, { thousands: true }), fw.unit ?? ''),
            tta,
            withRate(reportedOrNot(t.explain?.[k]), t.explain?.unit ?? 'events/s'),
            note,
          ];
        }),
      },
    });
  }

  const a = payload.architecture;
  if (a?.tasks) {
    const params = (p) => (typeof p === 'number' ? formatInt(p)
      : CATALOG_FRAMES.map((k) => `${formatInt(p?.[k])} (${fl(k)})`).join(', '));
    blocks.push({
      key: 'architecture',
      label: 'the architecture table',
      heading: 'Architecture and parameters',
      scope: a.identicalForNewSpecies
        ? 'The report states the architecture is identical for the muon, electron and pion; the parameter counts are the proton models\'.'
        : 'As the report gives it for the proton models.',
      table: {
        caption: 'One network per species, task and frame; parameters as reported.',
        columns: ['Task', 'Model', 'Target', 'Widths', 'Parameters', 'Encoder'],
        rows: TASK_ORDER.filter((k) => a.tasks[k]).map((k) => {
          const x = a.tasks[k];
          const widths = Array.isArray(x.widths) ? x.widths.join(' / ')
            : [x.cnnWidth ? `CNN ${x.cnnWidth}` : null, x.transformerD ? `transformer d = ${x.transformerD}` : null,
              x.tokensPerScale ? `${x.tokensPerScale} tokens per scale` : null].filter(Boolean).join(', ');
          return [tl(k), frameWords(x.model ?? '—'), frameWords(x.target ?? '—'), widths || '—', params(x.params), frameWords(x.encoder ?? 'none')];
        }),
      },
    });
    const v = a.voxels ?? {};
    const h = a.hitEncoder ?? {};
    const sym = a.symmetry ?? {};
    // One argument each: Array.map's index must never reach `printed` as a decimal count (R1-2).
    const sizeOf = (k) => (Array.isArray(v[k]) ? `${v.approx ? '≈ ' : ''}${v[k].map((x) => printed(x)).join(' × ')} ${v.unit ?? 'mm'}` : '—');
    blocks.push({
      key: 'frames',
      label: 'the voxel grid, hit encoder and TTA table per frame',
      heading: `Voxel grid, hit encoder and test-time augmentation per frame (${h.gridNote ?? 'at 32³'})`,
      scope: frameWords(sym.note ?? ''),
      table: {
        caption: 'As the report gives them; ≈ = approximately.',
        columns: ['Frame', 'Voxel size', 'Encoder slots', 'Mean hits per voxel', 'p99 hits per voxel', 'TTA symmetry'],
        rows: CATALOG_FRAMES.map((k) => [
          fl(k),
          sizeOf(k),
          printed(h.slots?.[k]),
          printed(k === 'absolute' ? h.meanHitsPerVoxel?.absolute : h.meanHitsPerVoxel?.other),
          printed(k === 'absolute' ? h.p99HitsPerVoxel?.absolute : h.p99HitsPerVoxel?.other),
          sym[k] ? `${sym[k].group}, ${formatInt(sym[k].transforms)} transforms` : '—',
        ]),
      },
    });
  }

  const ds = payload.datasets ?? {};
  const dsKeys = Object.keys(ds);
  if (dsKeys.length) {
    blocks.push({
      key: 'datasets',
      label: 'the datasets table',
      heading: 'Datasets',
      scope: 'Validation counts as reported; the particles of the muon, electron and pion are derived as 2 per combined event.',
      table: {
        caption: '— = not reported.',
        columns: ['Species', 'Combined events', 'Validation events', 'Validation particles', 'CSV rows', 'Checkpoints'],
        rows: dsKeys.map((s) => {
          const d = ds[s];
          return [
            labelOf(payload, 'species', s),
            formatInt(d.combinedEvents),
            formatInt(d.validationEvents),
            `${formatInt(d.validationParticles)}${s === 'proton' ? '' : ' (derived)'}`,
            d.csvRows ? reportedOrNot(d.csvRows, { thousands: true }) : '—',
            formatInt(d.checkpoints),
          ];
        }),
      },
    });
  }

  const caveats = payload.caveats ?? [];
  if (caveats.length) {
    blocks.push({
      key: 'caveats',
      label: 'the report\'s own caveats',
      heading: 'The report\'s own caveats',
      scope: `Those that apply to ${shownNames || 'the species on show'} and the ${labelOf(payload, 'task', payload.task).toLowerCase()} task; the report's "translated" frame is written Per-shower translated.`,
      list: caveats.map((c) => {
        const sp = c.scope?.species;
        const protonOnly = Array.isArray(sp) && sp.length === 1 && sp[0] === 'proton';
        return { id: c.id, text: frameWords(c.text), scope: protonOnly ? PROTON_ONLY : null };
      }),
    });
  }
  return blocks;
}

/* =============================================================== class == */

export class BenchDiagnosticsPanel extends CatalogChartPanel {
  constructor(elementOrId, { card = 'perf-diagnostics', aspect } = {}) {
    super(elementOrId, { card, kind: 'bench-diagnostics', aspect });
  }

  heightFor(width) {
    return plotHeight(this.lastPayload, this.lastOpts ?? {}, width);
  }

  buildOption({ payload, opts = {}, metrics }) {
    return benchDiagnosticsOption(payload, opts, metrics);
  }

  /** The tables and the caveat list after the plot frame: text nodes only. */
  renderExtra() {
    const host = this.ensureExtraHost('');
    if (!host) return;
    const doc = host.ownerDocument ?? globalThis.document;
    const nodes = diagnosticsBlocks(this.lastPayload).map((block) => {
      const section = doc.createElement('div');
      section.className = 'diag-block';
      if (section.dataset) section.dataset.block = block.key;
      const heading = doc.createElement('h3');
      heading.className = 'diag-heading';
      heading.textContent = block.heading;
      section.append(heading);
      if (block.scope) {
        const scope = doc.createElement('p');
        scope.className = 'diag-scope';
        scope.textContent = block.scope;
        section.append(scope);
      }
      if (block.table) {
        const wrap = doc.createElement('div');
        wrap.className = 'catalog-table';
        wrap.append(buildTable(doc, { ...block.table, textColumns: TEXT_COLUMNS[block.key] ?? [0] }));
        section.append(wrap);
      }
      if (block.list) {
        const list = doc.createElement('ul');
        list.className = 'caveat-list';
        for (const item of block.list) {
          const li = doc.createElement('li');
          if (li.dataset) li.dataset.caveat = item.id;
          if (item.scope) {
            const tag = doc.createElement('span');
            tag.className = 'badge-chip';
            if (tag.dataset) tag.dataset.kind = 'proton-only';
            tag.textContent = item.scope;
            li.append(tag, ' ');
          }
          li.append(item.text);
          list.append(li);
        }
        section.append(list);
      }
      return section;
    });
    host.replaceChildren(...nodes);
  }
}
