/* Two-dimensional count histograms as small multiples: the networks'
 * prediction against truth (pred-truth) and one feature against the
 * deposited energy per momentum class (D5).
 *
 * Both responses ship exact integer counts on a dense, row-major raster with
 * the y bins as rows (`counts[iy * nx + ix]`), one raster per shower (pred-
 * truth: A and B, kept apart because an event's two showers are two
 * predictions) or per class (D5: shared edges, so the classes are comparable
 * cell by cell).
 *
 * ## Counts on a logarithmic, legible ramp; empty bins transparent
 *
 * A cell's colour is log10 of its count. An empty cell is not drawn at all -
 * the card shows through - so "nothing here" never reads as "a little here".
 * A count of one must still be seen, so the ramp starts where its colour
 * clears 3:1 against the card: pred-truth reads the server's measurement for
 * the user's palette (`color.ramp.by_palette[palette]`, never the top-level
 * Viridis ramp for another palette), D5 measures the palette here
 * (`legibleRamp`, the same rule). The server measures against the dark card,
 * and its block is used only while that is the card in force: on the light
 * screen card the ramp is measured against white and runs from the card
 * outwards (a count of one is the run's faintest 3:1 colour, Viridis #22a784,
 * and the darkest colour the highest count), and in print against white paper
 * in the palette's own order. Every multiple shares one colour scale
 * (`color.vmin`/`vmax`), so the same colour is the same count in every grid.
 *
 * ## No density below N = 15
 *
 * A shower or class of fewer than 15 pairs gets its individual pairs as
 * points instead of a raster: a 2-D histogram of a handful is a scatter of
 * single counts whose look the binning sets. Pairs beyond the axes are not
 * drawn; the server counts them (`outside`) and the drawer says how many.
 *
 * ## Equal axes for prediction against truth
 *
 * Truth and prediction share one dataset-wide range in one unit, so each
 * pred-truth grid is square - 1:1, as the identity line ŷ = y needs to be
 * the diagonal - and the identity is drawn as a named dashed line. D5's two
 * axes are different quantities, so its grids take a plain aspect. A log10
 * feature axis carries log10 values (edges, pairs) and says so in its name;
 * its end labels are printed only where an end is a decade, so no tick reads
 * 0.316228. An azimuth axis (XGBoost's φ, in rad or mrad) spans its period
 * with ticks at multiples of π/2, written in π whatever the unit.
 *
 * The panel sizes its own height from its width (`autoHeight`, the
 * ResponseGridPanel pattern), so a 19-class D5 grows rather than shrinking
 * every multiple below legibility.
 */

import { THEME, axisPadding, formatInt, formatNumber } from '../scale.js';
import { lookupTable } from '../palette.js';
import { customLine } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, emptyChartOption, legibleRamp,
  showerColour, tickLabel, coarseInterval, rgbOf,
} from './chart_panel.js';
import { logTick, piLabel } from './distribution.js';

/** Fewest pairs drawn as a density rather than as points (the payload's `thresholds.density2d`). */
export const DENSITY2D_FLOOR = 15;
/** Narrowest multiple before a column is dropped (px). */
const MIN_CELL_PX = 170;
/** Height over width of a D5 multiple. */
const CELL_ASPECT = 0.72;
const PAIR_RADIUS_PX = 3;

const num = (v, d = 3) => formatNumber(v, d);

/** `count` evenly spaced edges over [lo, hi]. */
function linspace(lo, hi, count) {
  return Array.from({ length: count }, (_, i) => lo + (i * (hi - lo)) / (count - 1));
}

/**
 * The ramp a count is painted on: {palette, from, to}, the colour of a count
 * of one at `from`. Pred-truth passes the server's measured block for the
 * palette, which applies only when the card it was measured against is the
 * card in force; without one (D5), on the light screen card or in print, the
 * longest run of the palette that clears 3:1 against the card in force,
 * oriented as `legibleRamp` orients it.
 */
export function countRamp(palette, measured = null) {
  const card = THEME.card;
  if (measured && Number.isFinite(measured.from) && Number.isFinite(measured.to)
    && String(measured.first_level?.against ?? '').toLowerCase() === String(card).toLowerCase()) {
    return { palette, from: measured.from, to: measured.to, measured: true };
  }
  const { from, to } = legibleRamp(palette, card);
  return { palette, from, to, measured: false };
}

/** The colour of `count` on `ramp` over the shared log10 scale [vmin, vmax]: [r, g, b]. */
export function countColour(count, ramp, vmin, vmax) {
  const table = lookupTable(ramp.palette);
  const span = vmax - vmin;
  const f = span > 0 ? Math.max(0, Math.min(1, (Math.log10(count) - vmin) / span)) : 0;
  const t = ramp.from + f * (ramp.to - ramp.from);
  const i = Math.max(0, Math.min(255, Math.round(t * 255)));
  return [table[i * 3], table[i * 3 + 1], table[i * 3 + 2]];
}

function rgbText(rgb) {
  return `rgb(${rgb.map((v) => Math.round(v)).join(',')})`;
}

/** Legend stops of the ramp, for the visualMap. */
function rampStops(ramp, count = 9) {
  const table = lookupTable(ramp.palette);
  return Array.from({ length: count }, (_, k) => {
    const t = ramp.from + (k / (count - 1)) * (ramp.to - ramp.from);
    const i = Math.round(t * 255) * 3;
    return `rgb(${table[i]},${table[i + 1]},${table[i + 2]})`;
  });
}

/* ------------------------------------------------------------- models -- */

/** Whether a payload is a pred-truth response (else D5). */
export function isPredTruth(payload) {
  return Boolean(payload?.density && payload?.axes?.truth);
}

/** The showers pred-truth draws: those present and holding a shower, honouring `shower`. */
function predShowers(payload, shower) {
  const keys = Object.keys(payload?.density ?? {}).filter((k) => !shower || shower === 'both' || k === shower);
  return keys.filter((k) => (payload.density[k]?.n ?? 0) > 0 || keys.length === 1);
}

/** How many axis units one radian is, for an azimuth axis: 1 in rad, 1000 in mrad; null otherwise. */
export function radianScale(unit) {
  if (unit === 'rad') return 1;
  if (unit === 'mrad') return 1000;
  return null;
}

/** An axis description of the pred-truth response. */
function predAxis(ax) {
  // An azimuth axis (XGBoost's φ) is flagged by the server; its ticks are then written in π.
  const perRad = ax.circular === true ? radianScale(ax.unit) : null;
  return {
    lo: ax.lo, hi: ax.hi, n: ax.n, unit: ax.unit, label: ax.label, log10: false,
    circular: perRad !== null, perRad: perRad ?? 1,
  };
}

/**
 * The pred-truth model: one multiple per shower. Pure:
 * {kind: 'pred', panels: [...], x, y, square: true, ramp, vmin, vmax, noun, identity}.
 */
export function predTruthModel(payload, opts = {}) {
  const color = payload.color ?? {};
  const ramp = countRamp(opts.palette ?? 'viridis', color.ramp?.by_palette?.[opts.palette ?? 'viridis'] ?? null);
  const x = predAxis(payload.axes.truth);
  const y = predAxis(payload.axes.pred);
  const xEdges = linspace(x.lo, x.hi, x.n + 1);
  const yEdges = linspace(y.lo, y.hi, y.n + 1);
  const keys = predShowers(payload, opts.shower);
  const nShowers = Object.keys(payload.density ?? {}).length;
  const panels = keys.map((key) => {
    const d = payload.density[key];
    return {
      key,
      label: nShowers > 1 ? `Shower ${key.toUpperCase()}` : 'Shower',
      colour: showerColour(key, nShowers),
      draw: d.encoding === 'counts' ? 'histogram' : 'pairs',
      counts: d.encoding === 'counts' ? d.counts : null,
      nx: d.shape?.[1] ?? x.n,
      ny: d.shape?.[0] ?? y.n,
      pairs: d.encoding === 'pairs' ? d.pairs : null,
      n: d.n,
      n_in_range: d.n_in_range,
      outside: d.outside ?? null,
      n_missing: d.n_missing ?? null,
      max_count: d.max_count ?? null,
    };
  });
  return {
    kind: 'pred', panels, x, y, xEdges, yEdges, square: true, ramp,
    vmin: color.vmin ?? 0, vmax: color.vmax ?? 0, noun: 'showers', unit: color.unit ?? 'showers per bin',
    identity: payload.identity ? { from: payload.identity.from, to: payload.identity.to, label: payload.identity.label } : null,
    floor: payload.thresholds?.density2d ?? DENSITY2D_FLOOR,
  };
}

/** A D5 axis description. */
function featureAxis(ax) {
  return {
    lo: ax.lo, hi: ax.hi, n: ax.bins, unit: ax.unit, label: ax.label, feature: ax.feature,
    log10: Boolean(ax.log10), circular: ax.scale === 'circular', perRad: radianScale(ax.unit) ?? 1, interval: ax.interval ?? null,
    provisional: Boolean(ax.provisional),
  };
}

/** The D5 model: one multiple per class, shared edges and colour scale. */
export function featureHist2dModel(payload, opts = {}) {
  const color = payload.color ?? {};
  const ramp = countRamp(opts.palette ?? 'viridis', null);
  const x = featureAxis(payload.x);
  const y = featureAxis(payload.y);
  const labels = new Map((payload.classes ?? []).map((c) => [c.index, c.label]));
  const panels = (payload.series ?? []).map((s) => ({
    key: s.index,
    label: s.label ?? labels.get(s.index) ?? `class ${s.index}`,
    colour: THEME.accent,
    draw: s.draw,
    counts: s.draw === 'histogram' ? s.counts : null,
    nx: x.n,
    ny: y.n,
    pairs: s.draw === 'pairs' ? s.pairs : null,
    n: s.n,
    outside: s.outside ? {
      truth_below: s.outside.x_below, truth_above: s.outside.x_above,
      pred_below: s.outside.y_below, pred_above: s.outside.y_above, total: s.outside.total,
    } : null,
    n_floored: s.n_floored ?? 0,
    n_excluded_eps: s.n_excluded_eps ?? 0,
    n_nonpositive: (s.n_nonpositive_x ?? 0) + (s.n_nonpositive_y ?? 0),
    max_count: s.max_count ?? null,
  }));
  return {
    kind: 'feature', panels, x, y, xEdges: payload.x.edges, yEdges: payload.y.edges, square: false, ramp,
    vmin: color.vmin ?? 0, vmax: color.vmax ?? 0, noun: 'events', unit: color.unit ?? 'events per bin',
    identity: null, floor: payload.thresholds?.histogram ?? DENSITY2D_FLOOR, provisional: Boolean(color.provisional),
  };
}

/** The model of either response. */
export function hist2dModel(payload, opts = {}) {
  if (isPredTruth(payload)) return predTruthModel(payload, opts);
  if (payload?.view === 'hist2d') return featureHist2dModel(payload, opts);
  return null;
}

/* ------------------------------------------------------------- layout -- */

/**
 * Where `n` multiples go at `width`: {cols, rows, cells: [{left, top, width,
 * height}], height, titleH}. Square cells for pred-truth; with `height` the
 * cells shrink to fit it, else the layout grows to hold them.
 */
export function hist2dLayout(n, width, { square = false, height = null } = {}) {
  const pad = axisPadding({ ramp: true });
  const titleH = 1.8 * THEME.fontSmall;
  const gapX = 4.2 * THEME.fontLabel;
  const gapY = 3.2 * THEME.fontLabel;
  const plotW = Math.max(80, width - pad.left - pad.right);
  const count = Math.max(1, n);
  const cols = Math.max(1, Math.min(count, Math.floor((plotW + gapX) / (MIN_CELL_PX + gapX)) || 1));
  const rows = Math.ceil(count / cols);
  let cellW = (plotW - (cols - 1) * gapX) / cols;
  let cellH = square ? cellW : cellW * CELL_ASPECT;
  if (Number.isFinite(height) && height > 0) {
    const room = (height - pad.top - pad.bottom - rows * titleH - (rows - 1) * gapY) / rows;
    if (room < cellH) {
      cellH = Math.max(40, room);
      if (square) cellW = Math.min(cellW, cellH);
    }
  }
  const cells = [];
  for (let k = 0; k < count; k += 1) {
    const r = Math.floor(k / cols);
    const c = k % cols;
    cells.push({
      left: pad.left + c * (cellW + gapX),
      top: pad.top + titleH + r * (cellH + titleH + gapY),
      width: cellW,
      height: cellH,
      row: r,
      col: c,
    });
  }
  const total = pad.top + rows * (cellH + titleH) + (rows - 1) * gapY + pad.bottom;
  return { cols, rows, cells, height: Math.ceil(total), titleH };
}

/* ------------------------------------------------------------- option -- */

/** Tick labels of an axis: log10 values as their powers, azimuths in π (from rad or mrad). */
function axisFormatter(ax) {
  if (ax.log10) return (v) => logTick(10 ** Number(v));
  if (ax.circular) return (v) => piLabel(Number(v) / (ax.perRad ?? 1));
  return tickLabel;
}

/** Whether a log10 axis end is a whole decade, which alone gets an end label. */
export function isDecade(v) {
  return Number.isFinite(v) && Math.abs(v - Math.round(v)) < 1e-9;
}

/** The tick options of one axis: π/2 steps on an azimuth, end labels only at decades on a log10 axis. */
function tickOptions(ax, interval) {
  if (ax.circular) return { interval: (Math.PI / 2) * (ax.perRad ?? 1) };
  return interval ? { interval } : {};
}

/** A value axis with its end labels shown only at decades when it is a log10 axis (P-23). */
function withDecadeEnds(axis, ax) {
  if (!ax.log10) return axis;
  return { ...axis, axisLabel: { ...axis.axisLabel, showMinLabel: isDecade(ax.lo), showMaxLabel: isDecade(ax.hi) } };
}

/** An axis name with its unit, log flag and provisional flag. */
function axisName(ax, symbol, px) {
  const unit = ax.unit ? ` [${ax.unit}]` : '';
  const log = ax.log10 ? ' (log₁₀ axis)' : '';
  const prov = ax.provisional ? ' — provisional' : '';
  return fitName([`${ax.label}${unit}${log}${prov}`, `${ax.feature ?? symbol}${unit}${log}${prov}`, `${symbol}${unit}`], px);
}

/** A bin span on one axis, as a reader reads it. */
function spanText(ax, a, b) {
  if (ax.log10) return `${logTick(10 ** a)} … ${logTick(10 ** b)}`;
  return `${num(a)} … ${num(b)}`;
}

/** The tooltip of one counted cell. */
function cellTip(model, panel, ix, iy, count) {
  const x = model.x;
  const y = model.y;
  const xName = model.kind === 'pred' ? 'truth' : (x.feature ?? 'x');
  const yName = model.kind === 'pred' ? 'prediction' : (y.feature ?? 'E');
  return [
    `<b>${escapeHtml(panel.label)}: ${formatInt(count)} ${model.noun.replace(/s$/, count === 1 ? '' : 's')}</b>`,
    `${escapeHtml(xName)} ${spanText(x, model.xEdges[ix], model.xEdges[ix + 1])}${x.unit ? ` ${escapeHtml(x.unit)}` : ''}`,
    `${escapeHtml(yName)} ${spanText(y, model.yEdges[iy], model.yEdges[iy + 1])}${y.unit ? ` ${escapeHtml(y.unit)}` : ''}`,
    mutedLine('an exact count; the colour is log₁₀ of it on the shared scale, an empty bin is not drawn'),
  ].join('<br/>');
}

/** The tooltip of one pair drawn as a point. */
function pairTip(model, panel, pair) {
  const xName = model.kind === 'pred' ? 'truth' : (model.x.feature ?? 'x');
  const yName = model.kind === 'pred' ? 'prediction' : (model.y.feature ?? 'E');
  const show = (ax, v) => (ax.log10 ? `${logTick(10 ** v)} (log₁₀ ${num(v)})` : num(v, 4));
  return [
    `<b>${escapeHtml(panel.label)}: one ${model.noun.replace(/s$/, '')}</b>`,
    `${escapeHtml(xName)} ${show(model.x, pair[0])}${model.x.unit ? ` ${escapeHtml(model.x.unit)}` : ''}, `
      + `${escapeHtml(yName)} ${show(model.y, pair[1])}${model.y.unit ? ` ${escapeHtml(model.y.unit)}` : ''}`,
    mutedLine(`fewer than ${model.floor} pairs (N = ${formatInt(panel.n)}): the pairs themselves, not a density`),
  ].join('<br/>');
}

/** The title of one multiple: its label, N and what it draws. */
export function multipleTitle(model, panel) {
  const parts = [`${panel.label} · N = ${formatInt(panel.n)}`];
  if (panel.draw === 'pairs') parts.push('pairs (N < 15)');
  else if (panel.draw !== 'histogram') parts.push('nothing drawn');
  const out = panel.outside?.total ?? 0;
  if (out) parts.push(`${formatInt(out)} outside`);
  return parts.join(' · ');
}

/**
 * The option of either 2-D response. Pure: `opts` = {palette, shower?
 * (pred-truth), tooltipPosition?}; `metrics` = {width, height} with a null
 * height for a self-sizing layout.
 */
export function hist2dOption(payload, opts = {}, metrics = {}) {
  const model = hist2dModel(payload, opts);
  if (!model) return emptyChartOption(opts, metrics, 'No two-dimensional histogram in this response.');
  if (!model.panels.length) return emptyChartOption(opts, metrics, 'No shower in this selection.');
  const width = metrics.width || 760;
  const layout = hist2dLayout(model.panels.length, width, { square: model.square, height: metrics.height ?? null });
  const series = [];
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const graphic = [];
  const rectSeries = [];
  const { x, y, xEdges, yEdges, ramp, vmin, vmax } = model;
  const xInterval = (cell) => (x.interval ? coarseInterval(x.lo, x.hi, x.interval, cell.width) : undefined);
  const yInterval = (cell) => (y.interval ? coarseInterval(y.lo, y.hi, y.interval, cell.height) : undefined);

  model.panels.forEach((panel, k) => {
    const cell = layout.cells[k];
    grids.push({ left: cell.left, top: cell.top, width: cell.width, height: cell.height });
    const bottomRow = cell.row === layout.rows - 1 || k + layout.cols >= model.panels.length;
    xAxes.push(withDecadeEnds(valueAxis({
      gridIndex: k, min: x.lo, max: x.hi, formatter: axisFormatter(x), fontSize: THEME.fontSmall,
      name: bottomRow ? axisName(x, model.kind === 'pred' ? 'truth' : (x.feature ?? 'x'), cell.width) : '',
      ...tickOptions(x, xInterval(cell)),
    }), x));
    // D5's y axis is the deposited energy: its last-resort name is E [GeV], never the
    // transverse coordinate's letter (P-21).
    yAxes.push(withDecadeEnds(valueAxis({
      gridIndex: k, min: y.lo, max: y.hi, formatter: axisFormatter(y), fontSize: THEME.fontSmall,
      name: cell.col === 0 ? axisName(y, model.kind === 'pred' ? 'prediction' : 'E', cell.height) : '',
      nameGap: 3.4 * THEME.fontLabel,
      ...tickOptions(y, yInterval(cell)),
    }), y));
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: cell.left, y: cell.top - layout.titleH + 2, text: multipleTitle(model, panel),
        fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
      },
    });

    if (panel.draw === 'histogram' && Array.isArray(panel.counts)) {
      const cells = [];
      for (let iy = 0; iy < panel.ny; iy += 1) {
        for (let ix = 0; ix < panel.nx; ix += 1) {
          const c = panel.counts[iy * panel.nx + ix];
          if (c > 0) cells.push({ ix, iy, c, rgb: rgbText(countColour(c, ramp, vmin, vmax)) });
        }
      }
      rectSeries.push(series.length);
      series.push({
        type: 'custom',
        name: `${panel.label} · counts`,
        xAxisIndex: k,
        yAxisIndex: k,
        clip: true,
        z: 2,
        data: cells.map((d, index) => [
          0.5 * (xEdges[d.ix] + xEdges[d.ix + 1]), 0.5 * (yEdges[d.iy] + yEdges[d.iy + 1]), Math.log10(d.c), index]),
        renderItem: (params, api) => {
          const d = cells[params.dataIndex];
          const a = api.coord([xEdges[d.ix], yEdges[d.iy]]);
          const b = api.coord([xEdges[d.ix + 1], yEdges[d.iy + 1]]);
          return {
            type: 'rect',
            shape: { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), width: Math.abs(b[0] - a[0]), height: Math.abs(b[1] - a[1]) },
            style: { fill: d.rgb, stroke: null },
          };
        },
        tooltip: { formatter: (p) => { const d = cells[p.dataIndex]; return cellTip(model, panel, d.ix, d.iy, d.c); } },
      });
    } else if (panel.draw === 'pairs' && Array.isArray(panel.pairs)) {
      // Only the pairs inside the axes; the rest are counted by the server.
      const inside = panel.pairs.filter((p) => p[0] >= x.lo && p[0] <= x.hi && p[1] >= y.lo && p[1] <= y.hi);
      series.push({
        type: 'custom',
        name: `${panel.label} · pairs`,
        xAxisIndex: k,
        yAxisIndex: k,
        clip: true,
        z: 5,
        itemStyle: { color: panel.colour },
        data: inside.map((p, index) => [p[0], p[1], index]),
        renderItem: (params, api) => {
          const p = api.coord(inside[params.dataIndex]);
          return {
            type: 'circle',
            shape: { cx: p[0], cy: p[1], r: PAIR_RADIUS_PX },
            style: { fill: panel.colour, stroke: THEME.card, lineWidth: 1 },
          };
        },
        tooltip: { formatter: (p) => pairTip(model, panel, inside[p.dataIndex]) },
      });
    }

    if (model.identity) {
      series.push({
        ...customLine({
          name: 'identity: prediction = truth',
          from: [model.identity.from, model.identity.from],
          to: [model.identity.to, model.identity.to],
          color: THEME.muted,
          width: THEME.lineAxis,
          dash: [5, 4],
          z: 4,
          tooltip: `<b>identity ŷ = y</b>: ${escapeHtml(model.identity.label ?? 'prediction = truth')}`
            + `<br/>${mutedLine('a perfect network puts every shower on this line; the axes share one range in one unit, drawn 1:1')}`,
        }),
        xAxisIndex: k,
        yAxisIndex: k,
      });
    }
  });

  const maxCount = Math.round(10 ** vmax);
  const visualMap = rectSeries.length ? [{
    type: 'continuous',
    seriesIndex: rectSeries,
    dimension: 2,
    min: vmin,
    max: vmax > vmin ? vmax : vmin + 1,
    calculable: false,
    orient: 'vertical',
    right: 6,
    top: 'middle',
    itemWidth: 10,
    itemHeight: Math.min(140, Math.max(60, layout.height - 80)),
    text: [`${formatInt(maxCount)} ${model.noun}`, `1 ${model.noun.replace(/s$/, '')}`],
    textGap: 6,
    textStyle: { color: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily },
    inRange: { color: rampStops(ramp) },
    formatter: (v) => formatInt(10 ** Number(v)),
  }] : [];

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    visualMap,
    graphic,
    series,
  };
}

/** The colours a reader must see on this panel, as [r, g, b] (for the contrast tests). */
export function drawnColours(payload, opts = {}) {
  const model = hist2dModel(payload, opts);
  if (!model) return [];
  const out = [];
  for (const panel of model.panels) {
    if (panel.draw === 'pairs') out.push(rgbOf(panel.colour));
    if (panel.draw === 'histogram') {
      out.push(countColour(1, model.ramp, model.vmin, model.vmax));
      out.push(countColour(10 ** model.vmax, model.ramp, model.vmin, model.vmax));
    }
  }
  return out;
}

export class Hist2dPanel extends ChartPanel {
  /** `autoHeight` (default true): the panel sets its own height from its width, as B3's grid does. */
  constructor(elementOrId, { aspect, autoHeight = true } = {}) {
    super(elementOrId, { kind: 'hist2d', aspect });
    this.autoHeight = autoHeight;
  }

  /** The height the layout wants at `width`, from the retained payload. */
  wantedHeight(width) {
    const model = hist2dModel(this.lastPayload, this.lastOpts || {});
    if (!model) return null;
    return hist2dLayout(model.panels.length, width, { square: model.square }).height;
  }

  paint() {
    if (this.autoHeight && this.chart && this.lastPayload && this.element) {
      const { width } = this.size();
      const wanted = width ? this.wantedHeight(width) : null;
      if (wanted && this.element.clientHeight !== wanted) {
        this.element.style.height = `${wanted}px`;
        this.chart.resize();
      }
    }
    return super.paint();
  }

  exportMetrics(width) {
    const wanted = this.lastPayload ? this.wantedHeight(width) : null;
    return wanted ? { width, height: wanted } : super.exportMetrics(width);
  }

  buildOption({ payload, opts = {}, metrics }) {
    const height = this.autoHeight || THEME.legendWrap ? null : metrics?.height ?? null;
    return { option: hist2dOption(payload, opts, { ...metrics, height }) };
  }
}
