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
 */

import { THEME, axisPadding, formatNumber, formatInt, formatSigned, rampPalette, rampMidLabel, visualMap } from '../scale.js';
import { contrast, lookupTable } from '../palette.js';
import { tooltipOption } from './tooltip.js';
import { ChartPanel, baseOption, wrapTooltip, mutedLine, escapeHtml, rgbOf } from './chart_panel.js';

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
  if (cell.weighting === 'shower_by_hits') {
    return `N = ${formatInt(payload.n_showers)} showers, each weighted by its hits`;
  }
  return `N = ${formatInt(payload.n_hits)} hits in ${formatInt(payload.n_events)} events`;
}

/** The tooltip of one linear cell. */
export function cellTip(payload, vi, vj, cell) {
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

/**
 * The C8 option. Pure: `opts` = {palette, tooltipPosition?};
 * `metrics` = {width, height}.
 */
export function correlationOption(payload, opts = {}, metrics = {}) {
  const vars = payload?.variables ?? [];
  const k = vars.length;
  const matrix = payload?.matrix ?? [];
  const scale = { ...R_SCALE, ...(payload?.scale ?? {}), scale: 'linear', diverging: true };
  const palette = rampPalette(scale, opts.palette ?? 'viridis');
  const pad = axisPadding({ ramp: true });
  const width = metrics.width || 520;
  const height = metrics.height || 420;
  const symbols = vars.map(variableSymbol);

  // Square cells: the plot is the largest square the insets leave, centred.
  const availW = Math.max(80, width - pad.left - pad.right);
  const availH = Math.max(80, height - pad.top - pad.bottom);
  const side = Math.min(availW, availH);
  // The axes hold k − 1 categories each.
  const left = pad.left + (availW - side) / 2;
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
        const rgb = cellColour(cell.r, palette);
        linear.push({
          value: [j, i - 1, cell.r],
          label: { color: labelColour(rgb) },
          cell, i, j,
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
            formatter: hatched ? (Number.isFinite(R) ? `R ${formatNumber(R, 2)}` : '') : '—',
          },
          cell, i, j, hatched,
        });
      }
    }
  }

  const fontSize = Math.max(THEME.fontSmall, Math.min(THEME.fontTip, (side / Math.max(1, k)) * 0.22));
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
  const categoryAxis = (inverse, data) => ({
    type: 'category',
    data,
    inverse,
    axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: false },
    axisLabel: { color: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily },
    splitLine: { show: false },
    splitArea: { show: false },
  });

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left, top, width: side, height: side },
    xAxis: categoryAxis(false, symbols.slice(0, Math.max(0, k - 1))),
    yAxis: categoryAxis(true, symbols.slice(1)),
    visualMap: visualMap(scale, palette, { seriesIndex: 0, bottomInset: metrics.reservedBottom || 0 }),
    graphic: [...(mid ? [mid] : []), ...weak],
    series: [
      {
        type: 'heatmap',
        name: 'Pearson r',
        data: linear.map(({ value, label }) => ({ value, label })),
        label: {
          show: true,
          fontSize,
          fontFamily: THEME.fontFamily,
          formatter: (p) => formatSigned(p.value[2], 2),
        },
        itemStyle: { borderColor: THEME.card, borderWidth: 1 },
        emphasis: { disabled: true },
        tooltip: { formatter: (p) => cellTip(payload, vars[linear[p.dataIndex].i], vars[linear[p.dataIndex].j], linear[p.dataIndex].cell) },
      },
      {
        type: 'heatmap',
        name: 'circular or not estimable',
        data: other.map(({ value, itemStyle, label }) => ({ value, itemStyle, label })),
        label: { show: true, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily },
        emphasis: { disabled: true },
        tooltip: {
          formatter: (p) => {
            const it = other[p.dataIndex];
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
