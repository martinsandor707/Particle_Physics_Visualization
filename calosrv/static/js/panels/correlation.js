/* C8: the hit-level Pearson correlation matrix (and D3's feature matrix later).
 *
 * ## Lower triangle on a signed, symmetric ramp
 *
 * r is signed, so it is painted on PuOr symmetric about zero, linear on
 * [−1, +1]: the folded screen variant on the dark card, the standard scheme in
 * print (scale.js `rampPalette`, CLAUDE.md section 2), with the zero marked at
 * the ramp's midpoint. The matrix is symmetric and its diagonal is 1 by
 * construction, so only the lower triangle is drawn and the diagonal is left
 * blank. Every cell carries its r as text, in whichever of the theme's text
 * and canvas colours contrasts more with the cell, so a near-zero cell - drawn
 * close to the card on the folded ramp - is read by its number.
 *
 * ## A circular quantity has no linear correlation
 *
 * Azimuth φ wraps, so a Pearson r with it is meaningless (CLAUDE.md "Never
 * average a circular quantity"). Its cells are never on the colour scale:
 * they are hatched, in a series the visual map does not colour, and carry
 * Mardia's circular-linear R in the tooltip where the server quotes one (from
 * eight distinct azimuths), with its reference null_R2. Below that the cell is
 * empty and the tooltip gives the server's reason.
 *
 * ## Intervals
 *
 * The 95% interval is the server's: Fisher z with an event-grouped jackknife
 * (hits of one shower are not independent pairs), its method, group count and
 * n_eff in the tooltip beside the naive hit count. r is absent below N = 3
 * and the interval below N = 4: the cell then reads "—".
 *
 * ## D3: the shower-feature matrix (`/api/features?view=corr`)
 *
 * The features payload ships the upper triangle with its diagonal as flat
 * arrays (`r`, `lo`, `hi`, `n_pairs`, row-major over `order`); the panel
 * reads it through `featureCorrMatrix`, into the same lower-triangle picture.
 * Its azimuth cells (`circular_cells`) are never on the colour scale: they are
 * hatched and carry Mardia's circular–linear R with its jackknife SE and
 * null_R2 (from eight distinct azimuths), or the circular–circular r_c of the
 * two azimuths with its jackknife interval on Fisher z, or the server's reason
 * when neither can be quoted. The notebook's linear r of avg_phi travels as
 * `parity_r`, in the tooltip only and without an interval: a number to compare
 * with the notebook, never a correlation. angular_spread is a linear quantity
 * whose r is coloured, but its cells are hatched too and carry the server's
 * caution (`hatched`): part of its variance is where the ±π cut falls. With
 * twenty-one variables the cells are small, so the printed r is dropped when
 * it would not fit its cell and the tooltip carries it; the axis labels are
 * the feature ids, the x labels turned upright.
 *
 * ## Weak correlations are faded (opt-in, decision D-10)
 *
 * With `opts.fadeNull` (the feature card sets it; the Physics page's C8 does
 * not, so its picture is unchanged) a linear cell whose 95% interval contains
 * zero, or that has no interval, is drawn at `NULL_OPACITY` over the card: at
 * N = 4 the Fisher interval spans nearly [−1, 1], and a full-strength colour
 * would claim an association the sample cannot tell from none. Its r is still
 * printed, in the ink that contrasts with the faded colour, and its tooltip
 * says why it is faded.
 */

import { THEME, axisPadding, formatNumber, formatInt, formatSigned, rampPalette, rampMidLabel, visualMap } from '../scale.js';
import { contrast, lookupTable } from '../palette.js';
import { measureText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import { ChartPanel, baseOption, wrapTooltip, mutedLine, escapeHtml, rgbOf, blendOver } from './chart_panel.js';

/** How each variable is written on the matrix axes. */
const SYMBOLS = {
  x: 'x', y: 'y', z: 'z', u: 'u', v: 'v', w: 'w', energy: 'E', p: 'p', theta: 'θ', phi: 'φ',
  rho: 'ρ', r: 'r',
};

/** The diagonal hatch of a circular cell (spike S9: renders on canvas and in SVG). */
export function hatchDecal() {
  return {
    symbol: 'rect',
    symbolSize: 1,
    dashArrayX: [1, 0],
    dashArrayY: [2, 4],
    rotation: Math.PI / 4,
    color: THEME.hatch,
  };
}

/** The opacity of a faded cell (`opts.fadeNull`): its 95% interval contains zero, or it has none. */
export const NULL_OPACITY = 0.35;

/** Whether a linear cell's correlation is indistinguishable from none: its interval contains 0, or is absent. */
export function containsZero(cell) {
  const ci = cell?.ci95;
  if (!Array.isArray(ci) || !Number.isFinite(ci[0]) || !Number.isFinite(ci[1])) return true;
  return ci[0] <= 0 && ci[1] >= 0;
}

/** The linear diverging scale of r. */
export const R_SCALE = Object.freeze({ scale: 'linear', diverging: true, vmin: -1, vmax: 1 });

/** The axis label of one variable. */
export function variableSymbol(v) {
  return v.symbol ?? SYMBOLS[v.key] ?? v.label ?? v.key;
}

/** Whether a variable is circular (true or 'derived', as D3's catalogue marks it). */
function isCircular(v) {
  return v?.circular === true || v?.circular === 'derived';
}

/** The colour r is painted with on `palette` (a diverging table, index 0 = −1). */
export function cellColour(r, palette) {
  const table = lookupTable(palette);
  const i = Math.max(0, Math.min(255, Math.round(((r + 1) / 2) * 255)));
  return [table[i * 3], table[i * 3 + 1], table[i * 3 + 2]];
}

/** The label colour that contrasts more with `rgb`: the theme's text or canvas. */
export function labelColour(rgb) {
  const text = rgbOf(THEME.text) ?? [230, 237, 243];
  const canvas = rgbOf(THEME.canvas) ?? [13, 17, 23];
  return contrast(rgb, text) >= contrast(rgb, canvas) ? THEME.text : THEME.canvas;
}

/** The sample size a cell's r was computed from, as the tooltip names it. */
function sampleText(payload, cell) {
  if (Number.isFinite(cell.n_pairs)) {
    const left = Number.isFinite(payload.n_events) && cell.n_pairs < payload.n_events
      ? `; ${formatInt(payload.n_events - cell.n_pairs)} with a floored factor left out of this pair` : '';
    return `N = ${formatInt(cell.n_pairs)} showers${left}`;
  }
  if (cell.weighting === 'shower_by_hits') {
    return `N = ${formatInt(payload.n_showers)} showers, each weighted by its hits`;
  }
  return `N = ${formatInt(payload.n_hits)} hits in ${formatInt(payload.n_events)} events`;
}

/** The tooltip of one linear cell; `faded` adds why it is drawn faint (D-10). */
export function cellTip(payload, vi, vj, cell, faded = false) {
  const a = variableSymbol(vj);
  const b = variableSymbol(vi);
  const lines = [`<b>r(${escapeHtml(a)}, ${escapeHtml(b)}) = ${formatSigned(cell.r, 3)}</b>`];
  lines.push(cell.ci95
    ? `95% interval [${formatSigned(cell.ci95[0], 3)}, ${formatSigned(cell.ci95[1], 3)}] ${mutedLine(payload.interval ?? 'Fisher z')}`
    : `95% interval — ${mutedLine('not testable at this sample size')}`);
  lines.push(sampleText(payload, cell));
  if (Number.isFinite(cell.n_eff)) {
    lines.push(mutedLine(`n_eff = ${formatInt(cell.n_eff)} independent pairs; a naive hit count would claim SE ${formatNumber(cell.se_iid, 4)}`));
  }
  if (Number.isFinite(cell.per_shower_r)) {
    lines.push(`each shower counted once: r = ${formatSigned(cell.per_shower_r, 3)}`
      + (cell.per_shower_ci95 ? ` [${formatSigned(cell.per_shower_ci95[0], 3)}, ${formatSigned(cell.per_shower_ci95[1], 3)}]` : ''));
  }
  const weighting = payload.weightings?.[cell.weighting];
  if (weighting) lines.push(mutedLine(weighting));
  if (payload.method) lines.push(mutedLine(payload.method));
  if (cell.caution) lines.push(mutedLine(`hatched: ${cell.caution}`));
  if (faded) {
    lines.push(mutedLine(cell.ci95
      ? 'faded: the 95% interval contains 0, so this sample cannot tell the correlation from none'
      : 'faded: no 95% interval at this sample size, so nothing says the correlation differs from none'));
  }
  return lines.join('<br/>');
}

/** The tooltip of a hatched (circular) cell. */
export function circularTip(payload, vi, vj, cell) {
  const a = variableSymbol(vj);
  const b = variableSymbol(vi);
  const lines = [`<b>${escapeHtml(a)} × ${escapeHtml(b)}: no linear correlation</b>`,
    mutedLine('φ is circular: a Pearson r with it is meaningless, so the cell is hatched and off the colour scale')];
  const m = cell.mardia;
  if (m && Number.isFinite(m.R)) {
    lines.push(`Mardia circular–linear R = ${formatNumber(m.R, 3)}${Number.isFinite(m.se) ? ` (jackknife SE ${formatNumber(m.se, 3)})` : ''}`
      + ` ${mutedLine('from 0, no association, to 1; unsigned')}`);
    if (Number.isFinite(m.per_shower_R)) {
      lines.push(`each shower counted once: R = ${formatNumber(m.per_shower_R, 3)}`
        + (Number.isFinite(m.per_shower_se) ? ` (SE ${formatNumber(m.per_shower_se, 3)})` : ''));
    }
    if (Number.isFinite(m.null_R2)) lines.push(mutedLine(`with no association R² still averages ${formatNumber(m.null_R2, 4)} (null_R2)`));
  } else if (payload.mardia?.reason) {
    lines.push(mutedLine(payload.mardia.reason));
  }
  return lines.join('<br/>');
}

/* ------------------------------------------------------------------- D3 -- */

/** Whether a payload is D3's feature matrix rather than C8's. */
export function isFeatureCorr(payload) {
  return payload?.view === 'corr' && Array.isArray(payload?.order) && Array.isArray(payload?.r);
}

/** Index of (i, j), i ≤ j, in an upper triangle with its diagonal stored row-major over k variables. */
export function upperIndex(i, j, k) {
  const [a, b] = i <= j ? [i, j] : [j, i];
  return a * k - (a * (a - 1)) / 2 + (b - a);
}

/**
 * D3's payload as C8's shape: {variables, matrix[i][j] (j < i), ...}. A cell
 * is {r, ci95, n_pairs} for a linear pair, with `caution` where the server
 * hatches a linear feature, or {hatched: true, circular} for a pair with an
 * azimuth, `circular` being the server's circular cell. Pure.
 */
export function featureCorrMatrix(payload) {
  const order = payload.order ?? [];
  const k = order.length;
  const features = new Map((payload.features ?? []).map((f) => [f.id, f]));
  const circularCells = new Map((payload.circular_cells ?? []).map((c) => [c.position, c]));
  const cautions = payload.hatched ?? {};
  const variables = order.map((id) => {
    const f = features.get(id) ?? {};
    return { key: id, symbol: id, label: f.label ?? id, unit: f.unit ?? '', circular: f.circular === true };
  });
  const matrix = order.map((_, i) => order.map((__, j) => {
    if (j >= i) return null;
    const pos = upperIndex(i, j, k);
    const circular = circularCells.get(pos) ?? null;
    if (circular || variables[i].circular || variables[j].circular) {
      return { hatched: true, circular, r: null, n_pairs: payload.n_pairs?.[pos] ?? null };
    }
    const lo = payload.lo?.[pos];
    const hi = payload.hi?.[pos];
    const caution = [order[i], order[j]].map((id) => cautions[id]).find(Boolean) ?? null;
    return {
      r: payload.r?.[pos] ?? null,
      ci95: Number.isFinite(lo) && Number.isFinite(hi) ? [lo, hi] : null,
      n_pairs: payload.n_pairs?.[pos] ?? null,
      caution,
    };
  }));
  return {
    ...payload,
    variables,
    matrix,
    n_events: payload.n ?? payload.n_events,
    // The interval sentence names the method; the bare 'fisher_z' key is not prose.
    method: null,
    d3: true,
  };
}

/** The text a hatched D3 cell prints: its circular measure where one is quoted. */
export function featureCircularLabel(cell) {
  const c = cell?.circular;
  if (!c || !Number.isFinite(c.value)) return '';
  return c.measure === 'mardia' ? `R ${formatNumber(c.value, 2)}` : `r_c ${formatSigned(c.value, 2)}`;
}

/** The tooltip of a hatched D3 cell: the circular measure, or why none is quoted, and parity r. */
export function featureCircularTip(payload, vi, vj, cell) {
  const a = variableSymbol(vj);
  const b = variableSymbol(vi);
  const c = cell.circular ?? {};
  const lines = [`<b>${escapeHtml(a)} × ${escapeHtml(b)}: no linear correlation</b>`,
    mutedLine('an azimuth wraps: a Pearson r with it changes with where the ±π cut falls, so the cell is hatched and off the colour scale')];
  if (c.measure === 'mardia') {
    if (Number.isFinite(c.value)) {
      lines.push(`Mardia circular–linear R = ${formatNumber(c.value, 3)}${Number.isFinite(c.se) ? ` (jackknife SE ${formatNumber(c.se, 3)})` : ''} `
        + mutedLine('from 0, no association, to 1; unsigned'));
    } else if (c.reason) {
      lines.push(mutedLine(c.reason));
    }
    if (Number.isFinite(c.null_R2)) lines.push(mutedLine(`with no association R² still averages ${formatNumber(c.null_R2, 4)} (null_R2 = 2/(N − 1))`));
  } else if (c.measure === 'circular_circular') {
    if (Number.isFinite(c.value)) {
      lines.push(`circular–circular r_c = ${formatSigned(c.value, 3)}`
        + (Array.isArray(c.ci95) ? `, 95% interval [${formatSigned(c.ci95[0], 3)}, ${formatSigned(c.ci95[1], 3)}] ${mutedLine('(event-grouped jackknife on Fisher z)')}` : ` ${mutedLine('(no interval at this sample size)')}`));
    } else if (c.reason) {
      lines.push(mutedLine(c.reason));
    }
  } else if (c.reason) {
    lines.push(mutedLine(c.reason));
  }
  if (Number.isFinite(c.n)) lines.push(`N = ${formatInt(c.n)} showers${Number.isFinite(c.n_azimuths) ? `, ${formatInt(c.n_azimuths)} distinct azimuths` : ''}`);
  if (Number.isFinite(c.parity_r)) {
    lines.push(mutedLine(`the notebook's linear r = ${formatSigned(c.parity_r, 3)}, kept for parity only: no interval, not a correlation of a direction`));
  }
  const measures = payload.circular_measures?.[c.measure];
  if (measures) lines.push(mutedLine(measures));
  return lines.join('<br/>');
}

/**
 * The C8 option (and D3's, through `featureCorrMatrix`). Pure: `opts` =
 * {palette, tooltipPosition?, fadeNull?}; `metrics` = {width, height}.
 */
export function correlationOption(payload, opts = {}, metrics = {}) {
  if (isFeatureCorr(payload)) payload = featureCorrMatrix(payload);
  const d3 = Boolean(payload?.d3);
  const vars = payload?.variables ?? [];
  const k = vars.length;
  const matrix = payload?.matrix ?? [];
  const scale = { ...R_SCALE, ...(payload?.scale ?? {}), scale: 'linear', diverging: true };
  const palette = rampPalette(scale, opts.palette ?? 'viridis');
  const pad = axisPadding({ ramp: true });
  const width = metrics.width || 520;
  const height = metrics.height || 420;
  const symbols = vars.map(variableSymbol);

  // D3's axis labels are feature ids: the insets grow to hold the longest, x upright.
  const labelPx = d3 ? Math.max(0, ...symbols.map((t) => measureText(t, THEME.fontSmall, THEME.fontFamily) || 0.6 * THEME.fontSmall * t.length)) : 0;
  const insetL = d3 ? labelPx + 10 : pad.left;
  const insetB = d3 ? labelPx + 10 : pad.bottom;

  // Square cells: the plot is the largest square the insets leave, centred.
  const availW = Math.max(80, width - insetL - pad.right);
  const availH = Math.max(80, height - pad.top - insetB);
  const side = Math.min(availW, availH);
  // The axes hold k − 1 categories each.
  const left = insetL + (availW - side) / 2;
  const top = pad.top + (availH - side) / 2;

  const linear = [];
  const other = [];
  for (let i = 0; i < k; i += 1) {
    for (let j = 0; j < i; j += 1) {
      const cell = matrix[i]?.[j];
      if (!cell) continue;
      const hatched = Boolean(cell.hatched) || isCircular(vars[i]) || isCircular(vars[j]);
      // Row i is drawn at y = i − 1: the first variable has no cell below the diagonal.
      if (!hatched && Number.isFinite(cell.r)) {
        const faded = Boolean(opts.fadeNull) && containsZero(cell);
        const rgb = cellColour(cell.r, palette);
        // A faded cell's label is set against the colour as drawn, over the card.
        const shown = faded ? blendOver(`rgb(${rgb.join(',')})`, NULL_OPACITY) : rgb;
        const style = {
          ...(cell.caution ? { decal: hatchDecal() } : {}),
          ...(faded ? { opacity: NULL_OPACITY } : {}),
        };
        linear.push({
          value: [j, i - 1, cell.r],
          label: { color: labelColour(shown) },
          ...(Object.keys(style).length ? { itemStyle: style } : {}),
          cell, i, j, faded,
        });
      } else {
        const R = cell.mardia?.R;
        other.push({
          value: [j, i - 1, 0],
          itemStyle: {
            color: THEME.card,
            borderColor: THEME.grid,
            borderWidth: 1,
            ...(hatched ? { decal: hatchDecal() } : {}),
          },
          label: {
            color: THEME.muted,
            formatter: hatched
              ? (cell.circular !== undefined ? featureCircularLabel(cell) : (Number.isFinite(R) ? `R ${formatNumber(R, 2)}` : ''))
              : '—',
          },
          cell, i, j, hatched,
        });
      }
    }
  }

  const fontSize = Math.max(THEME.fontSmall, Math.min(THEME.fontTip, (side / Math.max(1, k)) * 0.22));
  // D3's cells can be too small for a printed r: then the tooltip carries it.
  const cellPx = side / Math.max(1, k - 1);
  const showLabels = !d3 || cellPx >= (measureText('−0.00', fontSize, THEME.fontFamily) || 3 * fontSize) + 4;
  const mid = rampMidLabel(scale, metrics);
  // In the empty upper triangle, right-aligned at the grid's top-right corner:
  // inside row 0 it sat under the first cell, which hid "weak:".
  const weak = payload?.weak
    ? [{
      type: 'text', silent: true,
      style: {
        x: left + side - 4, y: top + 4, text: `weak: ${formatInt(payload.n_events)} events`, textAlign: 'right',
        textVerticalAlign: 'top', fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, fontStyle: 'italic',
      },
    }] : [];

  // Columns are the first k − 1 variables, rows the last k − 1: the lower
  // triangle without its empty first row and last column.
  const categoryAxis = (inverse, data, rotate = 0) => ({
    type: 'category',
    data,
    inverse,
    axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: false },
    axisLabel: {
      color: THEME.muted, fontSize: d3 ? THEME.fontSmall : THEME.fontLabel, fontFamily: THEME.fontFamily,
      ...(d3 ? { interval: 0, rotate } : {}),
    },
    splitLine: { show: false },
    splitArea: { show: false },
  });

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left, top, width: side, height: side },
    xAxis: categoryAxis(false, symbols.slice(0, Math.max(0, k - 1)), 90),
    yAxis: categoryAxis(true, symbols.slice(1)),
    visualMap: visualMap(scale, palette, { seriesIndex: 0, bottomInset: metrics.reservedBottom || 0 }),
    graphic: [...(mid ? [mid] : []), ...weak],
    series: [
      {
        type: 'heatmap',
        name: 'Pearson r',
        data: linear.map(({ value, label, itemStyle }) => ({ value, label, ...(itemStyle ? { itemStyle } : {}) })),
        label: {
          show: showLabels,
          fontSize,
          fontFamily: THEME.fontFamily,
          formatter: (p) => formatSigned(p.value[2], 2),
        },
        itemStyle: { borderColor: THEME.card, borderWidth: 1 },
        emphasis: { disabled: true },
        tooltip: {
          formatter: (p) => {
            const it = linear[p.dataIndex];
            return cellTip(payload, vars[it.i], vars[it.j], it.cell, it.faded);
          },
        },
      },
      {
        type: 'heatmap',
        name: 'circular or not estimable',
        data: other.map(({ value, itemStyle, label }) => ({ value, itemStyle, label })),
        label: { show: showLabels, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily },
        emphasis: { disabled: true },
        tooltip: {
          formatter: (p) => {
            const it = other[p.dataIndex];
            if (it.hatched && it.cell.circular !== undefined) return featureCircularTip(payload, vars[it.i], vars[it.j], it.cell);
            if (it.hatched) return circularTip(payload, vars[it.i], vars[it.j], it.cell);
            return `<b>r(${escapeHtml(symbols[it.j])}, ${escapeHtml(symbols[it.i])})</b> — ${mutedLine('not estimable below N = 3')}`;
          },
        },
      },
    ],
  };
}

export class CorrelationPanel extends ChartPanel {
  constructor(elementOrId, { aspect = 0.9 } = {}) {
    super(elementOrId, { kind: 'correlation', aspect });
  }

  exportMetrics(width) {
    const pad = axisPadding({ ramp: true });
    const side = Math.max(80, width - pad.left - pad.right);
    return { width, height: Math.round(pad.top + pad.bottom + side * this.aspect) };
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: correlationOption(payload, opts, metrics) };
  }
}
