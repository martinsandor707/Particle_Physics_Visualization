/* B3: the energy response in momentum slices, as small multiples.
 *
 * `/api/energy-distribution?slice_by=momentum` ships one energy axis per
 * slice (`slice_axes`), because a 1 GeV slice and a 19 GeV slice share no
 * useful range: one sub-plot per slice, each on its own axis, never a shared
 * x axis that would squash the low slices into a corner. The response card
 * and plot 4 of a single-shower experiment both draw it.
 *
 * ## What each sub-plot draws, by the energy panel's ladder
 *
 *   N ≥ 15   density histogram + fitted Gaussian; they set the density axis
 *   N ≥ 8    the fitted curve, thinner and fainter, plus the events beneath it
 *   N <  8   the events and the summary marks only
 *
 * The server says which (`draw`, `drives_scale`); the client never draws what
 * it withheld. The curve's x grid and the histogram edges are rebuilt from the
 * slice's own axis as `axis.grid` states (linspace over [lo, hi]), since the
 * payload no longer ships them per slice. Every series' μ and σ - σ with its
 * standard error, and below the core-refit floor its χ² interval and c₄(N) -
 * are in the fit table (`renderTable`), which the drawer's "reported in the
 * table" points at.
 *
 * ## The density axis follows robust evidence (CLAUDE.md section 2)
 *
 * Each sub-plot's y range comes from its series with `drives_scale` (N ≥ 15).
 * A thin curve adapts to it; where it overflows, it is clipped with a caret
 * whose tooltip carries the true peak, and the count goes to the Details
 * drawer and the card's notice (`sparseLines`). A sub-plot with no robust
 * series takes its range from the thin curves and says "provisional" on its
 * y axis; one with no curve at all leaves the axis unlabelled and says so.
 * The energy axis is the server's, zero-based, "provisional" where
 * `slice_axes[].provisional` says so, and the values beyond it are counted
 * (`n_outside_axis`) and marked with a caret.
 *
 * ## The reserved band, only where a series needs it
 *
 * As in the energy panel, the band exists only in a sub-plot holding a series
 * below the histogram floor: its events as ticks, its mean with the capped
 * Student-t 95% interval and its uncapped ± 1 SD band. It grows with the rows
 * up to BAND_SHARE of the sub-plot, is tinted and captioned with a rule along
 * its top, and every tooltip in it says its height is a drawing offset. A
 * sub-plot of robust histograms has no band over their tails.
 *
 * The slice's measured mean incident momentum p (`momentum_marker`) is a
 * reference on the energy axis, not a height: a dotted rule in the shower's
 * colour, with its Student-t 95% interval as a thin envelope of two hairlines
 * (never a shaded band, which on this page means a dispersion). The SD of p
 * and its low-N interval are in its tooltip.
 *
 * ## Sub-plots that do not fit
 *
 * A self-sizing grid (the response card) grows to hold every slice. A grid
 * fitted into a fixed height (plot 4) never shrinks a sub-plot below
 * MIN_FIXED_PLOT_PX: it draws the slices that fit, says on the canvas how many
 * more there are, and lists every slice in the fit table. Nothing is drawn off
 * the canvas.
 *
 * Shower identity is colour (A pink, B blue; one shower takes the accent) and
 * a network's prediction is dashed, its truth or deposit solid.
 */

import { THEME, axisPadding, formatNumber, formatInt, formatPercent } from '../scale.js';
import { fitsWidth, legendRows } from '../textfit.js';
import { customWhiskers, binHoverSeries } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, mutedLine, escapeHtml, caretSeries, clampInterval,
  showerColour, niceCeil, coarseInterval, FINE_STEPS, legibleOpacity, sigmaText, referenceRule, dispersionBar,
  chartLegend,
} from './chart_panel.js';

/** Smallest sub-plot width before a column is dropped (px), on screen. */
export const GRID_MIN_CELL_PX = 150;
/** The same in print, where a single-column figure is 321 px wide: two columns, not one. */
const PRINT_MIN_CELL_PX = 100;
const GRID_MAX_COLS = 5;
/** Sub-plot height over its width when the panel sizes itself. */
const CELL_ASPECT = 0.62;
/** Shortest sub-plot a fixed-height grid draws; slices that would need less are listed, not squeezed. */
export const MIN_FIXED_PLOT_PX = 70;
/** Narrowest one: below it a sub-plot's two energy ticks no longer fit. */
const MIN_FIXED_PLOT_W_PX = 60;
const Y_HEADROOM = 1.15;
/** Share of a sub-plot the reserved band may take before its rows tighten (energy.js STRIP_BAND_SHARE). */
const BAND_SHARE = 0.32;
const ROW_MAX_PX = 8;
const ROW_MIN_PX = 6;
const TICK_HALF_PX = 2.5;
const SD_BAND_PX = 5;
const CAP_PX = 3.5;

const CAPTIONS = [
  'events and summary marks — offsets, not densities',
  'summary marks — offsets, not densities',
  'offsets, not densities',
  'not densities',
];
const OFFSET_NOTE = 'vertical position is a drawing offset, not a density';

const num = (v, d = 3) => formatNumber(v, d);

function span(lo, hi, digits = 3, unit = '') {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return '—';
  return `${num(lo, digits)} … ${num(hi, digits)}${unit}`;
}

/** `count` evenly spaced values over [lo, hi], `axis.grid`'s linspace. */
export function linspace(lo, hi, count) {
  if (count <= 1) return count === 1 ? [lo] : [];
  return Array.from({ length: count }, (_, i) => lo + (i * (hi - lo)) / (count - 1));
}

/**
 * The sentence a low-statistics series carries, from the payload's `texts`:
 * `prefix` filled with fit.n, then the degenerate message when the series is
 * degenerate, else the message of its `draw`. Null for a histogram.
 */
export function seriesMessage(payload, entry) {
  const texts = payload?.texts;
  if (!texts || !entry) return entry?.message ?? null;
  const key = entry.fit?.degenerate ? 'degenerate' : entry.draw;
  const message = texts.message?.[key];
  if (!message) return entry.message ?? null;
  return `${String(texts.prefix ?? '').replace('{n}', formatInt(entry.fit?.n ?? 0))}${message}`;
}

/** The estimator sentence of a series: its own note for a core refit, else the shared one. */
export function estimatorNote(payload, entry) {
  const fit = entry?.fit ?? {};
  if (fit.estimator === 'core_refit') return fit.estimator_note ?? null;
  return payload?.texts?.estimator_note?.[fit.estimator] ?? fit.estimator_note ?? null;
}

/** The series one sub-plot draws, honouring the A/B/Both toggle. */
function entriesOf(payload, slice, shower) {
  return (payload.series ?? []).filter(
    (s) => s.slice === slice && (!shower || shower === 'both' || s.shower === shower),
  );
}

/** Whether the payload holds two showers (B's per-shower blocks are not null). */
function twoShowers(payload) {
  return payload?.slice_counts_by_shower?.b != null;
}

/** The slices that get a sub-plot: those with an axis, in slice order. */
export function gridSlices(payload) {
  const axes = new Map((payload?.slice_axes ?? []).map((a) => [a.slice, a]));
  return (payload?.slices ?? []).filter((s) => axes.has(s.index)).map((s) => ({ slice: s, axis: axes.get(s.index) }));
}

/** Legend names: one per series key, in payload order. */
function legendNames(payload, shower) {
  const names = [];
  for (const s of payload?.series ?? []) {
    if (shower && shower !== 'both' && s.shower !== shower) continue;
    if (!names.includes(s.label)) names.push(s.label);
  }
  return names;
}

/**
 * Where every sub-plot goes. `height` null sizes the grid from the width
 * (each sub-plot CELL_ASPECT of its width) and lays out all `n`; a number
 * fits the grid into it, choosing the column count that gives the sub-plots
 * the most room - ties go to fewer rows - and never a sub-plot shorter than
 * MIN_FIXED_PLOT_PX. When no column count holds all `n` at that height, the
 * first `shown` slices that fit are laid out, `hidden` counts the rest and a
 * line is reserved above the shared axis name to say so (`noticeY`). Every
 * cell lies inside `height`. Pure.
 */
export function responseGridLayout(n, width, height = null, { legend = [] } = {}) {
  const pad = axisPadding();
  const f = THEME.fontSmall;
  const outerLeft = 2.2 * THEME.fontName;
  const outerRight = 0.8 * THEME.fontLabel;
  const avail = Math.max(60, width - outerLeft - outerRight);
  const legendPx = legend.length
    ? (THEME.legendWrap ? Math.max(1, legendRows(legend, avail, THEME.fontLabel, { fontFamily: THEME.fontFamily })) : 1)
      * 1.6 * THEME.fontLabel
    : 0;
  const top = pad.top + legendPx;
  const baseBottom = 2.6 * THEME.fontName;
  const noticePx = 1.5 * Math.max(f, THEME.fontTip);
  const titleH = 1.7 * f;
  // Room for the tick labels and, beside them, a "provisional" axis name.
  const yLabelW = 4.8 * f;
  const xLabelH = 3.3 * f;
  const gapX = 0.9 * THEME.fontLabel;
  const gapY = 0.6 * THEME.fontLabel;
  if (n === 0) {
    // Nothing to lay out: room for the one line that says so, not an empty grid.
    return {
      cols: 1, rows: 0, cells: [], shown: 0, hidden: 0, top, bottom: 0, outerLeft, noticeY: null,
      height: Math.round(top + 8 * THEME.fontName),
    };
  }
  const maxCols = Math.max(1, Math.min(GRID_MAX_COLS, n));
  const columns = (cols) => {
    const cellW = (avail - (cols - 1) * gapX) / cols;
    return { cellW, plotW: Math.max(30, cellW - yLabelW) };
  };
  const plotHeight = (rows, bottom) => (height - top - bottom - (rows - 1) * gapY) / rows - titleH - xLabelH;

  let best = null;
  let bottom = baseBottom;
  if (height === null) {
    const minCell = THEME.legendWrap ? PRINT_MIN_CELL_PX : GRID_MIN_CELL_PX;
    const cols = Math.max(1, Math.min(maxCols, Math.floor((avail + gapX) / (minCell + gapX))));
    const { cellW, plotW } = columns(cols);
    best = { cols, rows: Math.ceil(n / cols), cellW, plotW, plotH: Math.max(60, plotW * CELL_ASPECT), shown: n };
  } else {
    for (let cols = 1; cols <= maxCols; cols += 1) {
      const rows = Math.ceil(n / cols);
      const { cellW, plotW } = columns(cols);
      const plotH = plotHeight(rows, baseBottom);
      if (plotH < MIN_FIXED_PLOT_PX || (cols > 1 && plotW < MIN_FIXED_PLOT_W_PX)) continue;
      const room = Math.min(plotW * CELL_ASPECT, plotH);
      if (!best || room > best.room || (room === best.room && rows < best.rows)) {
        best = { cols, rows, cellW, plotW, plotH, room, shown: n };
      }
    }
    if (!best) {
      // Not every slice fits: draw as many as fit at the minimum height, in
      // slice order, and keep a line to say how many more there are.
      bottom = baseBottom + noticePx;
      for (let cols = 1; cols <= maxCols; cols += 1) {
        const { cellW, plotW } = columns(cols);
        const rowsFit = Math.floor((height - top - bottom + gapY) / (titleH + MIN_FIXED_PLOT_PX + xLabelH + gapY));
        if (rowsFit < 1 || (cols > 1 && plotW < MIN_FIXED_PLOT_W_PX)) continue;
        const shown = Math.min(n, rowsFit * cols);
        const rows = Math.ceil(shown / cols);
        const plotH = plotHeight(rows, bottom);
        const room = Math.min(plotW * CELL_ASPECT, plotH);
        if (!best || shown > best.shown || (shown === best.shown && room > best.room)) {
          best = { cols, rows, cellW, plotW, plotH, room, shown };
        }
      }
      if (!best) {
        // Too short for even one sub-plot at the minimum: one row, as tall as it can be.
        const cols = Math.max(1, Math.min(maxCols, Math.floor((avail + gapX) / (MIN_FIXED_PLOT_W_PX + yLabelW + gapX))));
        const { cellW, plotW } = columns(cols);
        best = { cols, rows: 1, cellW, plotW, plotH: Math.max(30, plotHeight(1, bottom)), shown: Math.min(n, cols) };
      }
    }
  }
  const { cols, rows, cellW, plotW, plotH, shown } = best;
  const cellH = titleH + plotH + xLabelH;
  const cells = Array.from({ length: shown }, (_, k) => {
    const r = Math.floor(k / cols);
    const c = k % cols;
    const x = outerLeft + c * (cellW + gapX);
    const y = top + r * (cellH + gapY);
    return {
      left: x + yLabelW, top: y + titleH, width: plotW, height: plotH, titleX: x + yLabelW, titleY: y,
      x, cellWidth: cellW,
    };
  });
  const total = Math.round(top + rows * cellH + (rows - 1) * gapY + bottom);
  const hidden = n - shown;
  return {
    cols, rows, cells, shown, hidden, top, bottom, outerLeft,
    height: height === null ? total : Math.min(total, Math.round(height)),
    // The notice sits under the last row's tick labels, above the shared axis name.
    noticeY: hidden ? top + rows * cellH + (rows - 1) * gapY + 0.2 * THEME.fontName : null,
  };
}

/** Which marks a series draws, for the sub-plot and the drawer. */
function curveOf(entry) {
  return entry.curve?.y?.length ? entry.curve.y : null;
}

function peakOf(values) {
  let peak = 0;
  for (const v of values ?? []) if (Number.isFinite(v) && v > peak) peak = v;
  return peak;
}

/**
 * The y scale of one sub-plot: robust peaks set it; thin curves only when
 * nothing robust is drawn (then provisional); null when nothing is estimable.
 */
export function subplotScale(entries) {
  const robust = [];
  const soft = [];
  for (const e of entries) {
    if (e.draw === 'histogram' && e.histogram && e.drives_scale) robust.push(peakOf(e.histogram.counts));
    const curve = curveOf(e);
    if (curve) (e.drives_scale ? robust : soft).push(e.curve_peak ?? peakOf(curve));
  }
  const robustPeak = Math.max(0, ...robust);
  const provisional = !(robustPeak > 0);
  const basis = provisional ? Math.max(0, ...soft) : robustPeak;
  const hasDensity = basis > 0;
  // Two ticks per sub-plot (0, yMax/2, yMax), so the top is rounded on a finer ladder.
  return {
    yMax: hasDensity ? niceCeil(Y_HEADROOM * basis, FINE_STEPS) : 1, provisional: provisional && hasDensity, hasDensity,
  };
}

/** The fit text of one series (curve tooltip, drawer). */
export function fitText(payload, entry, sliceLabel) {
  const fit = entry.fit ?? {};
  const lines = [`<b>${escapeHtml(entry.label)} · ${escapeHtml(sliceLabel)}</b>, N = ${formatInt(fit.n)}`];
  const mu = fit.mu_core ?? fit.mu;
  const sigma = fit.sigma_core ?? fit.sigma;
  if (Number.isFinite(mu)) {
    lines.push(`μ = ${num(mu)}${Number.isFinite(fit.mu_error) ? ` ± ${num(fit.mu_error)}` : ''} GeV`
      + (fit.mu_ci95 ? ` ${mutedLine(`(95% interval ${span(fit.mu_ci95[0], fit.mu_ci95[1])})`)}` : ''));
  }
  if (Number.isFinite(sigma)) {
    lines.push(`σ = ${num(sigma)}${Number.isFinite(fit.sigma_error) ? ` ± ${num(fit.sigma_error)}` : ''} GeV`
      + (fit.sigma_ci95 ? ` ${mutedLine(`(95% interval ${span(fit.sigma_ci95[0], fit.sigma_ci95[1])}, asymmetric)`)}` : ''));
  }
  if (Number.isFinite(fit.sigma_bias_factor) && (fit.n ?? 0) < (payload.thresholds?.core ?? 15)) {
    lines.push(mutedLine(`bias factor c₄(N) = ${num(fit.sigma_bias_factor, 4)}`));
  }
  const note = estimatorNote(payload, entry);
  if (note) lines.push(mutedLine(note));
  const message = seriesMessage(payload, entry);
  if (message && entry.draw !== 'histogram') lines.push(mutedLine(message));
  if (fit.non_gaussian === null || fit.non_gaussian === undefined) {
    lines.push(mutedLine(`Gaussian shape: untestable below N = ${payload.thresholds?.robust ?? 20}`));
  } else if (fit.non_gaussian) {
    lines.push(mutedLine('Gaussian shape: rejected (non-Gaussian)'));
  }
  if (!entry.drives_scale && curveOf(entry)) {
    lines.push(mutedLine(`below N = ${payload.thresholds?.histogram ?? 15}: drawn de-weighted, and does not set the density axis`));
  }
  return lines.join('<br/>');
}

/** The momentum marker's text: mean p, its interval, its spread, the low-N label. */
export function momentumText(payload, marker, showerLabel, sliceLabel) {
  const names = payload.momentum_marker ?? {};
  const lines = [`<b>${escapeHtml(showerLabel)} · ${escapeHtml(sliceLabel)}</b>: measured incident momentum`];
  lines.push(`mean p = ${num(marker.mean)} GeV, N = ${formatInt(marker.n)} ${mutedLine(names.mean ?? '')}`);
  if (marker.ci95) lines.push(`95% interval ${span(marker.ci95[0], marker.ci95[1], 3, ' GeV')} ${mutedLine(names.ci95?.label ?? '')}`);
  if (Number.isFinite(marker.sd)) lines.push(`SD = ${num(marker.sd)} GeV ${mutedLine(names.sd ?? '')}`);
  const low = marker.low_n;
  if (low) {
    const parts = [low.label, low.dof_note].filter(Boolean).join(' · ');
    if (parts) lines.push(`<i>${escapeHtml(parts)}</i>`);
    if (low.sd_ci95) {
      lines.push(mutedLine(`SD ${names.sd_ci95?.label ?? '95% χ² interval'}: ${span(low.sd_ci95[0], low.sd_ci95[1], 3, ' GeV')}`
        + (Number.isFinite(low.sd_se) ? `, SE ${num(low.sd_se)}` : '')
        + (Number.isFinite(low.c4) ? `, c₄ = ${num(low.c4, 4)}` : '')));
    }
  }
  lines.push(mutedLine('the dotted rule; its two hairlines are the 95% interval of the mean, a thin envelope'));
  return lines.join('<br/>');
}

/** Every series of the grid, tagged with its sub-plot's axes. */
function onGrid(series, k) {
  return { ...series, xAxisIndex: k, yAxisIndex: k };
}

/**
 * The counts a sub-plot's title gives: of the showers drawn, never of a
 * shower the A/B toggle hides. Two showers shown give both counts, since the
 * 15- and 20-shower gates act on each series, not on their sum.
 */
export function sliceCounts(payload, sliceIndex, shower = 'both') {
  const key = String(sliceIndex);
  const total = payload?.slice_counts?.[key] ?? 0;
  const by = payload?.slice_counts_by_shower ?? {};
  if (!twoShowers(payload)) return { n: total };
  if (shower === 'a' || shower === 'b') return { n: by[shower]?.[key] ?? 0, shower };
  return { n: total, a: by.a?.[key] ?? 0, b: by.b?.[key] ?? 0 };
}

/** A slice label without the spaces around ± and before the unit, for a narrow title. */
function compactLabel(label) {
  return String(label).replace(/\s*±\s*/g, '±').replace(/\s*–\s*/g, '–');
}

/**
 * The title of one sub-plot, fitted to its width: first over the plot, then
 * over the whole cell (the y tick-label column included); the slice label is
 * shortened, and at last cut with an ellipsis, but the count is always given
 * in full - a title that loses digits misstates N. Pure: {text, wide}.
 */
export function subplotTitle(label, counts, plotW, cellW, fontPx = THEME.fontSmall) {
  const both = Number.isFinite(counts.a) && Number.isFinite(counts.b);
  const tag = counts.shower ? `N_${counts.shower.toUpperCase()}` : 'N';
  const long = both ? `N_A = ${formatInt(counts.a)}, N_B = ${formatInt(counts.b)}` : `${tag} = ${formatInt(counts.n)}`;
  const short = both ? `N ${formatInt(counts.a)} + ${formatInt(counts.b)}` : `${tag} ${formatInt(counts.n)}`;
  const compact = compactLabel(label);
  // Longest first, each over the plot and then over the whole cell, before a shorter form is tried.
  const groups = [[`${label} · ${long}`, `${label}, ${long}`], [`${label} · ${short}`, `${label} (${short})`],
    [`${compact} · ${short}`, `${compact} (${short})`, `${compact} ${short}`]];
  const fits = (t, w) => fitsWidth(t, w, fontPx, THEME.fontFamily);
  for (const group of groups) {
    for (const [w, wide] of [[plotW, false], [cellW, true]]) {
      const hit = group.find((t) => fits(t, w));
      if (hit) return { text: hit, wide };
    }
  }
  let base = compact;
  while (base.length > 1 && !fits(`${base}… ${short}`, cellW)) base = base.slice(0, -1);
  return { text: `${base}… ${short}`, wide: true };
}

/** The notice of a sub-plot with no estimable density, fitted to its width. */
function noDensityText(width) {
  return ['no density estimate', 'no density', 'none'].find(
    (t) => fitsWidth(t, width - 4, THEME.fontSmall, THEME.fontFamily),
  ) ?? '';
}

/**
 * The B3 option. Pure: `opts` = {shower?: 'a' | 'b' | 'both',
 * tooltipPosition?, readoutPosition?}; `metrics` = {width, height}, where a
 * null height lays the grid out from the width alone.
 */
export function responseGridOption(payload, opts = {}, metrics = {}) {
  const width = metrics.width || 600;
  const shower = opts.shower ?? 'both';
  const allSlices = gridSlices(payload);
  const legend = legendNames(payload, shower);
  const layout = responseGridLayout(allSlices.length, width, metrics.height ?? null, { legend });
  const slices = allSlices.slice(0, layout.cells.length);
  const nShowers = twoShowers(payload) ? 2 : 1;
  const unit = payload?.axis?.unit ?? 'GeV';
  const grids = [];
  const xAxes = [];
  const yAxes = [];
  const series = [];
  const graphic = [];
  // Whether any sub-plot draws a density: the shared axis name is only given then.
  let anyDensity = false;

  slices.forEach(({ slice, axis }, k) => {
    const cell = layout.cells[k];
    grids.push({ left: cell.left, top: cell.top, width: cell.width, height: cell.height });
    const entries = entriesOf(payload, slice.index, shower);
    const scale = subplotScale(entries);
    anyDensity = anyDensity || scale.hasDensity;
    const lo = axis.lo;
    const hi = axis.hi;

    // "provisional" sits under the tick labels and beside them, inside the sub-plot's own margins.
    const xStep = coarseInterval(lo, hi, axis.interval, cell.width);
    // The axis end is labelled only when it is a tick, never as a stray label beside the last one.
    const onTick = Math.abs((hi - lo) / xStep - Math.round((hi - lo) / xStep)) < 1e-6;
    xAxes.push(valueAxis({
      gridIndex: k, min: lo, max: hi, interval: xStep, fontSize: THEME.fontSmall, showMaxLabel: onTick,
      name: axis.provisional ? 'provisional' : '', nameGap: 1.9 * THEME.fontSmall, nameSize: THEME.fontSmall,
    }));
    yAxes.push(valueAxis({
      gridIndex: k, min: 0, max: scale.yMax, interval: scale.yMax / 2, labels: scale.hasDensity, split: scale.hasDensity,
      fontSize: THEME.fontSmall, name: scale.provisional ? 'provisional' : '', nameGap: 3.9 * THEME.fontSmall,
      nameSize: THEME.fontSmall,
    }));
    const title = subplotTitle(slice.label, sliceCounts(payload, slice.index, shower), cell.width, cell.cellWidth ?? cell.width);
    graphic.push({
      type: 'text',
      silent: true,
      style: {
        x: title.wide ? (cell.x ?? cell.titleX) : cell.titleX, y: cell.titleY + 1, text: title.text,
        fill: THEME.text, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
      },
    });
    if (!scale.hasDensity) {
      // At the top of the plot: the band, when there is one, is at its foot.
      graphic.push({
        type: 'text',
        silent: true,
        style: {
          x: cell.left + cell.width / 2, y: cell.top + 2,
          text: noDensityText(cell.width), textAlign: 'center', textVerticalAlign: 'top',
          fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
        },
      });
    }

    const cellSeries = [];
    addDensityMarks(cellSeries, payload, entries, { slice, lo, hi, scale, nShowers });
    const bandTop = addBandMarks(cellSeries, payload, entries, { slice, axis, lo, hi, nShowers, plotH: cell.height, plotW: cell.width });
    addMomentumRules(cellSeries, payload, entries, { slice, axis, lo, hi, nShowers, yMax: scale.yMax, liftPx: bandTop });

    const histEdges = (() => {
      const h = entries.find((e) => e.draw === 'histogram' && e.histogram);
      return h ? linspace(lo, hi, h.histogram.counts.length + 1) : null;
    })();
    if (histEdges) {
      cellSeries.push(binHoverSeries({
        name: 'bin readout',
        edges: histEdges,
        position: opts.readoutPosition ?? null,
        tooltip: (i) => gridReadout(payload, entries, slice, histEdges, i),
      }));
    }
    for (const s of cellSeries) series.push(onGrid(s, k));
  });

  const plotWidth = width - layout.outerLeft;
  // The shared axis name fits the figure: a single column cannot hold the unit's long form.
  const shortUnit = String(unit).split(' (')[0];
  const xName = (payload?.scale === 'calibrated'
    ? [`Calibrated energy c · E [${unit}]`, `Calibrated energy c · E [${shortUnit}]`, `c · E [${shortUnit}]`]
    : [`Deposited energy [${unit}]`, `Deposited energy [${shortUnit}]`, `E [${shortUnit}]`])
    .find((t, i, all) => i === all.length - 1 || fitsWidth(t, plotWidth - 8, THEME.fontName, THEME.fontFamily));
  if (slices.length) {
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: layout.outerLeft + plotWidth / 2, y: layout.height - 0.4 * THEME.fontName,
        text: xName, textAlign: 'center', textVerticalAlign: 'bottom',
        fill: THEME.muted, fontSize: THEME.fontName, fontFamily: THEME.fontFamily,
      },
    });
  }
  if (layout.hidden > 0) {
    // CLAUDE.md section 2: clip it and say so. The slices that do not fit are
    // named and are in the fit table; none is drawn off the canvas.
    const rest = allSlices.slice(layout.cells.length).map(({ slice }) => slice.label);
    const text = `${formatInt(layout.cells.length)} of ${formatInt(allSlices.length)} slices fit at this height; `
      + `the other ${formatInt(layout.hidden)} (${rest[0]}${rest.length > 1 ? ` … ${rest[rest.length - 1]}` : ''}) are in the fit table, not drawn.`;
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: layout.outerLeft, y: layout.noticeY,
        text: fitsWidth(text, plotWidth - 8, THEME.fontSmall, THEME.fontFamily) ? text : hiddenShort(layout, allSlices.length),
        textVerticalAlign: 'top', fill: THEME.warn, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
      },
    });
  }
  // CLAUDE.md section 2: with no estimable density anywhere, no axis is
  // labelled as one; each sub-plot says "no density estimate" instead.
  if (anyDensity) {
    graphic.push({
      type: 'text', silent: true, rotation: Math.PI / 2,
      x: 0.9 * THEME.fontName, y: layout.top + (layout.height - layout.top - layout.bottom) / 2,
      style: {
        text: 'Probability density [GeV⁻¹]', textAlign: 'center', textVerticalAlign: 'middle',
        fill: THEME.muted, fontSize: THEME.fontName, fontFamily: THEME.fontFamily,
      },
    });
  }
  if (!allSlices.length) {
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: width / 2, y: layout.top + 1.2 * THEME.fontName, text: 'No showers of this selection fall in any momentum slice.',
        textAlign: 'center', textVerticalAlign: 'top', fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily,
      },
    });
  }

  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    legend: chartLegend(legend),
    grid: grids.length ? grids : [{ left: 0, top: 0, width: 1, height: 1, show: false }],
    xAxis: xAxes.length ? xAxes : [valueAxis({ labels: false })],
    yAxis: yAxes.length ? yAxes : [valueAxis({ labels: false })],
    graphic,
    series,
  };
}

/** The hidden-slices notice when the full sentence does not fit one line. */
function hiddenShort(layout, n) {
  return `${formatInt(layout.cells.length)} of ${formatInt(n)} slices shown; ${formatInt(layout.hidden)} more in the fit table`;
}

/** Histograms and fitted curves of one sub-plot; thin curves clipped with a caret. */
function addDensityMarks(out, payload, entries, { slice, lo, hi, scale, nShowers }) {
  for (const e of entries) {
    const colour = showerColour(e.shower, nShowers);
    const dash = e.kind === 'pred' ? 'dashed' : null;
    if (e.draw === 'histogram' && e.histogram) {
      const counts = e.histogram.counts;
      const edges = linspace(lo, hi, counts.length + 1);
      const points = [[edges[0], 0]];
      for (let i = 0; i < counts.length; i += 1) {
        const d = Number.isFinite(counts[i]) ? counts[i] : 0;
        points.push([edges[i], d], [edges[i + 1], d]);
      }
      points.push([edges[counts.length], 0]);
      out.push({
        type: 'custom', name: e.label, silent: true, clip: true, z: 2, data: [[lo, 0]], itemStyle: { color: colour },
        renderItem: (params, api) => ({
          type: 'polygon', shape: { points: points.map((p) => api.coord(p)) },
          style: { fill: colour, opacity: 0.07, stroke: 'none' },
        }),
      });
      // The outline is what a reader reads: 0.45 measured 2.34:1 against the card.
      const outline = legibleOpacity(colour, 0.6);
      out.push({
        type: 'custom', name: e.label, clip: true, z: 3, data: [[lo, 0]], itemStyle: { color: colour },
        renderItem: (params, api) => ({
          type: 'polyline', shape: { points: points.map((p) => api.coord(p)) },
          style: { fill: 'none', stroke: colour, lineWidth: THEME.lineAxis, opacity: outline, lineDash: dash },
        }),
        tooltip: {
          formatter: () => `${escapeHtml(e.label)} · ${escapeHtml(slice.label)}: density histogram`
            + `<br/>${mutedLine(`${formatInt(e.histogram.n_in_range)} of ${formatInt(e.histogram.n)} events inside the axis`)}`,
        },
      });
    }
    const curve = curveOf(e);
    if (!curve) continue;
    const xs = linspace(lo, hi, curve.length);
    const points = xs.map((x, i) => [x, curve[i]]).filter((p) => Number.isFinite(p[1]));
    const thin = !e.drives_scale;
    const opacity = thin ? legibleOpacity(colour, 0.6) : 1;
    out.push({
      type: 'custom', name: e.label, clip: true, z: 5, data: [[lo, 0]], itemStyle: { color: colour },
      renderItem: (params, api) => ({
        type: 'polyline', shape: { points: points.map((p) => api.coord(p)) },
        style: {
          fill: 'none', stroke: colour, lineWidth: (thin ? 1.1 : 1.8) * THEME.lineAxis,
          opacity, lineDash: dash,
        },
      }),
      tooltip: { formatter: () => fitText(payload, e, slice.label) },
    });
    const peak = e.curve_peak ?? peakOf(curve);
    if (thin && peak > scale.yMax) {
      const mu = e.fit?.mu_core ?? e.fit?.mu;
      const at = Number.isFinite(mu) ? Math.min(Math.max(mu, lo), hi) : 0.5 * (lo + hi);
      out.push(caretSeries({
        name: `${e.label} fit (clipped)`,
        color: colour,
        carets: [{
          at: [at, scale.yMax],
          dir: 'up',
          tooltip: `${fitText(payload, e, slice.label)}<br/><span style="color:${THEME.warn}">clipped: peak `
            + `${num(peak)} GeV⁻¹ exceeds the axis, which the N ≥ ${payload.thresholds?.histogram ?? 15} series set</span>`,
        }],
      }));
    }
  }
}

/** The series of a sub-plot that take rows in its reserved band: those below the histogram floor. */
function bandEntries(entries) {
  return entries.filter((e) => e.draw !== 'histogram' && (e.strip?.values?.length || e.markers));
}

/**
 * The reserved band of one sub-plot, only when a series below the histogram
 * floor needs it: its events and its summary marks, row by row. Returns the
 * band's height in pixels above the baseline (0 when there is none).
 */
function addBandMarks(out, payload, entries, { slice, axis, lo, hi, nShowers, plotH, plotW }) {
  const low = bandEntries(entries);
  const rowsNeeded = low.reduce((sum, e) => sum + (e.strip?.values?.length ? 1 : 0) + (e.markers ? 1 : 0), 0);
  if (!rowsNeeded) return 0;
  const caption = CAPTIONS.find((c) => fitsWidth(c, plotW - 8, THEME.fontSmall, THEME.fontFamily)) ?? CAPTIONS[CAPTIONS.length - 1];
  const captionPx = 1.3 * THEME.fontSmall;
  const pitch = Math.max(ROW_MIN_PX, Math.min(ROW_MAX_PX, (plotH * BAND_SHARE - captionPx - 4) / rowsNeeded));
  let cursor = 4 + pitch / 2;
  const rows = [];
  for (const e of low) {
    const row = { e, colour: showerColour(e.shower, nShowers) };
    if (e.strip?.values?.length) { row.ticks = cursor; cursor += pitch; }
    if (e.markers) { row.marker = cursor; cursor += pitch; }
    rows.push(row);
  }
  const bandTop = cursor - pitch / 2 + captionPx + 2;

  out.push({
    type: 'custom', name: 'reserved summary band', silent: true, clip: true, z: 1, data: [[lo, 0]],
    renderItem: (params, api) => {
      const left = api.coord([lo, 0]);
      const right = api.coord([hi, 0]);
      const top = left[1] - bandTop;
      return {
        type: 'group',
        children: [
          { type: 'rect', shape: { x: left[0], y: top, width: right[0] - left[0], height: bandTop },
            style: { fill: THEME.muted, opacity: THEME.stripAlpha } },
          // The band's edge is read, so it is muted ink (5.3:1), not the 1.3:1 border.
          { type: 'line', shape: { x1: left[0], y1: top, x2: right[0], y2: top },
            style: { stroke: THEME.muted, lineWidth: THEME.lineGrid, lineDash: [3, 3] } },
          { type: 'text', style: { x: left[0] + 4, y: top + 2, text: caption, fill: THEME.muted,
            fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, opacity: 0.85 } },
        ],
      };
    },
  });

  for (const row of rows) addLowNRow(out, payload, row, { slice, lo, hi });

  // Values beyond this slice's axis: counted by the server, marked here.
  const beyond = [];
  for (const row of rows) {
    const values = row.e.strip?.values ?? [];
    const below = values.filter((v) => v < lo).length;
    const above = values.filter((v) => v > hi).length;
    const tip = (count, where) => `${escapeHtml(row.e.label)} · ${escapeHtml(slice.label)}: ${formatInt(count)} event(s) ${where} the axis`
      + `<br/>${mutedLine(`${formatInt(axis.n_outside_axis)} of ${formatInt(axis.n_values)} values of this slice lie beyond its axis`)}`
      + `<br/>${mutedLine(OFFSET_NOTE)}`;
    if (below && row.ticks !== undefined) beyond.push({ at: [lo, 0], dir: 'left', lift: row.ticks, tooltip: tip(below, 'below'), color: row.colour });
    if (above && row.ticks !== undefined) beyond.push({ at: [hi, 0], dir: 'right', lift: row.ticks, tooltip: tip(above, 'beyond'), color: row.colour });
  }
  for (const c of beyond) {
    out.push(caretSeries({ name: 'events beyond the axis', carets: [c], color: c.color, liftPx: c.lift, sizePx: 5 }));
  }
  return bandTop;
}

/** A custom series of pixel-lifted marks over the baseline. */
function lifted({ name, data, render, tooltip, z = 8 }) {
  return {
    type: 'custom', name, clip: true, z, silent: !tooltip,
    data: data.map((d, index) => [d.x, 0, index]),
    renderItem: (params, api) => render(data[params.dataIndex], api),
    ...(tooltip ? { tooltip: { formatter: (p) => tooltip(data[p.dataIndex]) } } : {}),
  };
}

function addLowNRow(out, payload, row, { slice, lo, hi }) {
  const { e, colour } = row;
  const label = `${e.label} · ${slice.label}`;
  const coreFloor = payload.thresholds?.core ?? 15;
  // σ below the core-refit floor travels with its SE, its χ² interval and c₄.
  const sigma = sigmaText(e.fit, { unit: ' GeV', coreFloor });
  if (row.ticks !== undefined) {
    const inside = (e.strip.values ?? []).filter((v) => v >= lo && v <= hi).map((x) => ({ x }));
    const tickOpacity = legibleOpacity(colour, e.kind === 'pred' ? 0.7 : 0.95);
    out.push(lifted({
      name: `${e.label} (events)`,
      data: inside,
      z: 7,
      render: (d, api) => {
        const p = api.coord([d.x, 0]);
        const y = p[1] - row.ticks;
        return { type: 'line', shape: { x1: p[0], y1: y - TICK_HALF_PX, x2: p[0], y2: y + TICK_HALF_PX },
          style: { stroke: colour, lineWidth: 1.4, opacity: tickOpacity } };
      },
      tooltip: (d) => `${escapeHtml(label)}: event energy = ${num(d.x)} GeV`
        + `<br/>${mutedLine(`one of ${formatInt(e.fit?.n)} individual events`
          + (e.strip.truncated ? ` (${formatInt(e.strip.n_shown)} shown)` : ''))}`
        + (seriesMessage(payload, e) ? `<br/>${mutedLine(seriesMessage(payload, e))}` : '')
        + `<br/>${mutedLine(OFFSET_NOTE)}`,
    }));
  }
  const m = e.markers;
  if (!m || row.marker === undefined) return;
  const sd = clampInterval(m.dispersion_lo, m.dispersion_hi, lo, hi);
  const sdTip = `${escapeHtml(label)}: <b>sample dispersion</b>, μ ± 1σ = ${span(m.dispersion_lo, m.dispersion_hi, 3, ' GeV')}`
    + (sigma ? `<br/>${sigma}` : '')
    + `<br/>${mutedLine(`the spread of the ${formatInt(e.fit?.n)} events, not the precision of the mean`)}`
    + `<br/>${mutedLine(OFFSET_NOTE)}`;
  if (sd.lo !== null && sd.hi !== null && sd.hi > sd.lo) {
    out.push(lifted({
      name: `${e.label} · SD band`,
      data: [{ x: m.mu }],
      z: 5,
      render: (d, api) => {
        const a = api.coord([sd.lo, 0]);
        const b = api.coord([sd.hi, 0]);
        return dispersionBar(a[0], b[0], a[1] - row.marker, SD_BAND_PX, colour);
      },
      tooltip: () => sdTip,
    }));
  }
  const ci = clampInterval(m.ci95_lo, m.ci95_hi, lo, hi);
  const meanTip = `${escapeHtml(label)}: <b>mean with its 95% confidence interval</b>`
    + `<br/>μ = ${num(m.mu)} GeV, interval ${span(m.ci95_lo, m.ci95_hi, 3, ' GeV')} `
    + mutedLine(`(Student-t, ν = ${formatInt((e.fit?.n ?? 1) - 1)})`)
    + (sigma ? `<br/>${sigma}` : '')
    + (ci.cutLo || ci.cutHi ? `<br/>${mutedLine('the interval extends past the axis; these are its true ends')}` : '')
    + `<br/>${mutedLine('the precision of the mean, not the spread of the events')}`
    + `<br/>${mutedLine(OFFSET_NOTE)}`;
  if (ci.lo !== null && ci.hi !== null) {
    out.push(customWhiskers({
      name: `${e.label} · mean 95% interval`, points: [[0, ci.lo, ci.hi, { caps: ci.caps }]],
      horizontal: true, offsetPx: row.marker, capPx: CAP_PX, color: colour, width: 1.2 * THEME.lineAxis, z: 8,
      tooltip: () => meanTip,
    }));
  }
  const inside = m.mu >= lo && m.mu <= hi;
  if (inside) {
    out.push(lifted({
      name: `${e.label} · mean`, data: [{ x: m.mu }], z: 9,
      render: (d, api) => {
        const p = api.coord([d.x, 0]);
        return { type: 'circle', shape: { cx: p[0], cy: p[1] - row.marker, r: 2.6 }, style: { fill: colour } };
      },
      tooltip: () => meanTip,
    }));
  }
  const carets = [];
  if (sd.cutLo || ci.cutLo || (!inside && m.mu < lo)) carets.push({ at: [lo, 0], dir: 'left', tooltip: ci.cutLo || !inside ? meanTip : sdTip });
  if (sd.cutHi || ci.cutHi || (!inside && m.mu > hi)) carets.push({ at: [hi, 0], dir: 'right', tooltip: ci.cutHi || !inside ? meanTip : sdTip });
  if (carets.length) out.push(caretSeries({ name: `${e.label} · summary (clipped)`, carets, color: colour, liftPx: row.marker, sizePx: 5 }));
}

/**
 * The slice's measured mean incident momentum p per shower drawn: a dotted
 * rule from the band top (or the baseline) to the top of the sub-plot, its
 * Student-t 95% interval a thin envelope; clipped with a caret when it lies
 * beyond the slice's energy axis.
 */
function addMomentumRules(out, payload, entries, { slice, axis, lo, hi, nShowers, yMax, liftPx }) {
  const momenta = ['a', 'b']
    .map((key) => ({ key, marker: axis.momentum?.[key] }))
    .filter(({ key, marker }) => marker && Number.isFinite(marker.mean)
      && (entries.some((e) => e.shower === key) || !entries.length));
  for (const { key, marker } of momenta) {
    const colour = showerColour(key, nShowers);
    const showerLabel = nShowers > 1 ? `Shower ${key.toUpperCase()}` : 'Shower';
    const tip = momentumText(payload, marker, showerLabel, slice.label);
    const name = `${showerLabel} · mean incident momentum p`;
    out.push(...referenceRule({
      name, at: marker.mean, lo: marker.ci95?.[0], hi: marker.ci95?.[1], xMin: lo, xMax: hi, yMax, colour, liftPx,
      tooltip: tip, z: 4,
    }));
    if (marker.mean < lo || marker.mean > hi) {
      out.push(caretSeries({
        name: `${name} (clipped)`, carets: [{ at: [marker.mean < lo ? lo : hi, yMax / 2], dir: marker.mean < lo ? 'left' : 'right', tooltip: tip }],
        color: colour, sizePx: 5,
      }));
    }
  }
}

/** The readout of histogram bin i of one sub-plot. */
function gridReadout(payload, entries, slice, edges, i) {
  const lines = [`<b>${escapeHtml(slice.label)}</b>: E ${span(edges[i], edges[i + 1], 3, ' GeV')}`];
  const centre = 0.5 * (edges[i] + edges[i + 1]);
  for (const e of entries) {
    if (e.draw === 'histogram' && e.histogram) {
      const d = e.histogram.counts[i];
      lines.push(`${escapeHtml(e.label)}: binned density ${num(d)} GeV⁻¹`);
    }
    const curve = curveOf(e);
    if (curve) {
      const t = (centre - edges[0]) / (edges[edges.length - 1] - edges[0]);
      const j = Math.round(t * (curve.length - 1));
      if (j >= 0 && j < curve.length) lines.push(mutedLine(`${e.label} fit at ${num(centre)} GeV: ${num(curve[j])} GeV⁻¹`));
    }
  }
  return lines.join('<br/>');
}

/* ------------------------------------------------------- the fit table -- */

/** How each estimator is named in the table; its full sentence is the cell's title. */
const ESTIMATOR_LABELS = Object.freeze({
  core_refit: 'core refit',
  moments: 'sample moments',
  moments_1dof: 'moments, 1 d.o.f.',
  mean_only: 'mean only',
  degenerate: 'degenerate',
  none: '—',
});

/**
 * The fit table's rows: every slice of the payload in order, one row per
 * series the A/B toggle shows - μ and σ, each with its standard error, N and
 * the estimator - and below the core-refit floor σ's χ² 95% interval and its
 * bias factor c₄(N) (CLAUDE.md section 2). A slice with no shower of the
 * selection gets one row that says so, so the table names every slice the
 * grid does not draw. Pure.
 */
export function responseGridRows(payload, shower = 'both') {
  const rows = [];
  if (!payload) return rows;
  const t = payload.thresholds ?? {};
  const coreFloor = t.core ?? 15;
  const axes = new Map((payload.slice_axes ?? []).map((a) => [a.slice, a]));
  const nShowers = twoShowers(payload) ? 2 : 1;
  for (const slice of payload.slices ?? []) {
    const axis = axes.get(slice.index) ?? null;
    const entries = axis ? entriesOf(payload, slice.index, shower) : [];
    if (!entries.length) {
      rows.push({ slice: slice.label, sliceIndex: slice.index, empty: true, counts: sliceCounts(payload, slice.index, shower) });
      continue;
    }
    for (const e of entries) {
      const fit = e.fit ?? {};
      const n = fit.n ?? 0;
      const below = n < coreFloor;
      const marker = axis?.momentum?.[e.shower] ?? null;
      rows.push({
        slice: slice.label,
        sliceIndex: slice.index,
        shower: e.shower,
        kind: e.kind,
        label: e.label,
        colour: showerColour(e.shower, nShowers),
        dashed: e.kind === 'pred',
        n,
        draw: e.draw,
        mu: fit.mu_core ?? fit.mu ?? null,
        mu_error: fit.mu_error ?? null,
        mu_ci95: fit.mu_ci95 ?? null,
        sigma: fit.sigma_core ?? fit.sigma ?? null,
        sigma_error: fit.sigma_error ?? null,
        belowCore: below,
        // Below the core-refit floor σ is never quoted without these.
        sigma_ci95: below ? fit.sigma_ci95 ?? null : null,
        c4: below ? fit.sigma_bias_factor ?? null : null,
        resolution: fit.resolution_core ?? fit.resolution ?? null,
        resolution_error: fit.resolution_error ?? null,
        estimator: fit.estimator ?? e.estimator ?? null,
        estimatorLabel: ESTIMATOR_LABELS[fit.estimator ?? e.estimator] ?? String(fit.estimator ?? '—'),
        note: estimatorNote(payload, e),
        message: seriesMessage(payload, e),
        non_gaussian: fit.non_gaussian ?? null,
        robustFloor: t.robust ?? 20,
        momentum: marker && Number.isFinite(marker.mean)
          ? { mean: marker.mean, ci95: marker.ci95 ?? null, sd: marker.sd ?? null, n: marker.n ?? null } : null,
      });
    }
  }
  return rows;
}

/** The text of the fit table's cells: header and rows, every string through the formatters (U+2212). */
export function responseGridTable(payload, shower = 'both') {
  const unit = 'GeV';
  const columns = ['Momentum slice', 'N', `μ ± SE [${unit}]`, `σ ± SE [${unit}]`, 'σ/μ', 'Estimator', 'Shape'];
  const rows = responseGridRows(payload, shower).map((r) => {
    if (r.empty) {
      return { empty: true, name: r.slice, text: 'no showers of this selection', cells: [] };
    }
    const sigmaSub = [];
    if (r.belowCore && Array.isArray(r.sigma_ci95)) sigmaSub.push(`χ² 95% ${span(r.sigma_ci95[0], r.sigma_ci95[1])}`);
    if (r.belowCore && Number.isFinite(r.c4)) sigmaSub.push(`c₄ = ${num(r.c4, 3)}`);
    const shape = r.non_gaussian === null
      ? { text: `not testable (N < ${r.robustFloor})`, cls: 'na' }
      : { text: r.non_gaussian ? 'non-Gaussian' : 'Gaussian', warn: Boolean(r.non_gaussian) };
    return {
      name: `${r.slice} · ${r.label}`,
      colour: r.colour,
      dashed: r.dashed,
      momentum: r.momentum
        ? `⟨p⟩ = ${num(r.momentum.mean)} GeV${Array.isArray(r.momentum.ci95) ? `, 95% ${span(r.momentum.ci95[0], r.momentum.ci95[1])}` : ''}`
        : null,
      cells: [
        { text: formatInt(r.n) },
        {
          text: Number.isFinite(r.mu) ? num(r.mu) : '—',
          uncert: Number.isFinite(r.mu_error) ? `± ${num(r.mu_error)}` : null,
          title: Array.isArray(r.mu_ci95) ? `95% interval of the mean ${span(r.mu_ci95[0], r.mu_ci95[1])} GeV (Student-t)` : null,
        },
        {
          text: Number.isFinite(r.sigma) ? num(r.sigma) : '—',
          uncert: Number.isFinite(r.sigma_error) ? `± ${num(r.sigma_error)}` : (Number.isFinite(r.sigma) ? null : 'no width from one event'),
          sub: sigmaSub.length ? sigmaSub.join(' · ') : null,
          title: r.belowCore ? 'Below the core-refit floor: σ with its standard error, its asymmetric χ² 95% interval and its bias factor c₄(N).' : null,
        },
        {
          text: Number.isFinite(r.resolution) ? formatPercent(r.resolution, 1) : '—',
          uncert: Number.isFinite(r.resolution_error) ? `± ${formatPercent(r.resolution_error, 1)}` : null,
        },
        { text: r.estimatorLabel, title: r.note ?? r.message ?? null },
        shape,
      ],
    };
  });
  return { columns, rows };
}

/**
 * The key counts the card states on screen (the energy panel's sparse
 * notice): series below the floors, low-N curves clipped at their sub-plot's
 * top, values beyond a slice's energy axis, provisional axes, showers in no
 * slice, and slices a fixed-height grid could not draw. Counted over the
 * series the A/B toggle shows. Pure: string[].
 */
export function responseGridSparse(payload, shower = 'both', { hidden = 0, shown = null } = {}) {
  const lines = [];
  if (!payload) return lines;
  const t = payload.thresholds ?? {};
  const histFloor = t.histogram ?? 15;
  const slices = gridSlices(payload);
  const drawn = slices.flatMap(({ slice }) => entriesOf(payload, slice.index, shower));
  const withCurve = drawn.filter((e) => e.draw === 'curve+strip').length;
  const noCurve = drawn.filter((e) => e.draw !== 'histogram' && e.draw !== 'curve+strip').length;
  if (withCurve || noCurve) {
    const parts = [];
    if (withCurve) parts.push(`${formatInt(withCurve)} below N = ${histFloor} (histogram suppressed; curve drawn de-weighted)`);
    if (noCurve) parts.push(`${formatInt(noCurve)} below N = ${t.curve ?? 8} (no density curve: too few events to constrain a shape)`);
    lines.push(`Low-statistics series — ${parts.join('; ')}. Their events are ticks in the tinted band, with the sample `
      + 'dispersion as a shaded band and the mean with its 95% confidence interval as a capped whisker. μ and σ are in the '
      + `table for every series, σ with its standard error and, below N = ${t.core ?? 15}, its χ² interval and c₄.`);
  }
  const clipped = [];
  let provisionalY = 0;
  for (const { slice } of slices) {
    const entries = entriesOf(payload, slice.index, shower);
    const scale = subplotScale(entries);
    if (scale.provisional) provisionalY += 1;
    for (const e of entries) {
      const curve = curveOf(e);
      const peak = curve ? (e.curve_peak ?? peakOf(curve)) : 0;
      if (curve && !e.drives_scale && peak > scale.yMax) clipped.push(`${slice.label}: ${num(peak)} GeV⁻¹ at N = ${formatInt(e.fit?.n)}`);
    }
  }
  if (clipped.length) {
    lines.push(`${formatInt(clipped.length)} low-N curve${clipped.length === 1 ? '' : 's'} clipped at the top of its sub-plot `
      + `(${clipped.join('; ')}), each with a caret: the density axis is set by the N ≥ ${histFloor} series.`);
  }
  if (provisionalY) {
    lines.push(`${formatInt(provisionalY)} sub-plot${provisionalY === 1 ? ' takes its' : 's take their'} density axis from low-N curves `
      + 'alone and say "provisional" on it.');
  }
  const beyond = slices.filter(({ axis }) => axis.n_outside_axis > 0);
  if (beyond.length) {
    const total = beyond.reduce((sum, { axis }) => sum + axis.n_outside_axis, 0);
    const of = slices.reduce((sum, { axis }) => sum + (axis.n_values ?? 0), 0);
    const filtered = twoShowers(payload) && (shower === 'a' || shower === 'b');
    lines.push(`${formatInt(total)} of ${formatInt(of)} values lie beyond their slice's energy axis `
      + `(${beyond.map(({ slice, axis }) => `${slice.label}: ${formatInt(axis.n_outside_axis)}`).join('; ')})`
      + `${filtered ? ', counted over both showers' : ''}: excluded from the view, kept in the statistics.`);
  }
  const provisionalX = slices.filter(({ axis }) => axis.provisional).length;
  if (provisionalX) {
    lines.push(`${formatInt(provisionalX)} ${provisionalX === 1 ? 'energy axis is' : 'energy axes are'} provisional: no series there reaches N = ${histFloor}.`);
  }
  const outside = Object.entries(payload.outside_slices ?? {})
    .filter(([key, n]) => n && (shower === 'both' || !twoShowers(payload) || key === shower));
  const nOutside = outside.reduce((sum, [, n]) => sum + n, 0);
  if (nOutside) {
    lines.push(`${formatInt(nOutside)} shower${nOutside === 1 ? '' : 's'}`
      + `${twoShowers(payload) ? ` (${outside.map(([k, n]) => `${k.toUpperCase()} ${formatInt(n)}`).join(', ')})` : ''}`
      + ' of this selection fall in no slice: counted and calibrated, drawn nowhere.');
  }
  if (hidden > 0) {
    lines.push(`${formatInt(shown ?? slices.length - hidden)} of ${formatInt(slices.length)} slices fit the plot at this height; `
      + `the other ${formatInt(hidden)} are in the table, not drawn.`);
  }
  return lines;
}

export class ResponseGridPanel extends ChartPanel {
  /**
   * `autoHeight` (the response card): the panel sets its element's height
   * from the rows the width allows. Off (plot 4 in the 2 × 2), the grid fits
   * the height the layout gives it, never below MIN_FIXED_PLOT_PX a sub-plot.
   * `onLayout` is told when a repaint changes how many slices a fixed host
   * hides - a resize the page does not see, caught by the panel's own
   * ResizeObserver - so the card's sparse note never goes stale.
   */
  constructor(elementOrId, { aspect, autoHeight = true, onLayout = null } = {}) {
    super(elementOrId, { kind: 'response-grid', aspect });
    this.autoHeight = autoHeight;
    this.onLayout = typeof onLayout === 'function' ? onLayout : null;
    this.hiddenSlices = 0;
  }

  /** The height the grid wants at `width`, from the retained payload. */
  wantedHeight(width) {
    const payload = this.lastPayload;
    const shower = this.lastOpts?.shower ?? 'both';
    return responseGridLayout(gridSlices(payload).length, width, null, { legend: legendNames(payload, shower) }).height;
  }

  paint() {
    if (this.autoHeight && this.chart && this.lastPayload) {
      const { width } = this.size();
      if (width) {
        const wanted = this.wantedHeight(width);
        if (this.element.clientHeight !== wanted) {
          this.element.style.height = `${wanted}px`;
          this.chart.resize();
        }
      }
    }
    const option = super.paint();
    if (option && this.onLayout && !this.autoHeight) {
      const { hidden } = this.layoutCounts();
      if (hidden !== this.hiddenSlices) {
        this.hiddenSlices = hidden;
        this.onLayout();
      }
    }
    return option;
  }

  exportMetrics(width) {
    if (!this.lastPayload) return super.exportMetrics(width);
    return { width, height: this.wantedHeight(width) };
  }

  /**
   * A self-sizing grid is laid out from the width alone, on screen and in
   * print; a fixed one too in print (THEME.legendWrap), where a figure holds
   * every slice at the height `exportMetrics` asked for.
   */
  buildOption({ payload, opts = {}, metrics }) {
    const height = this.autoHeight || THEME.legendWrap ? null : metrics?.height ?? null;
    return { option: responseGridOption(payload, opts, { ...metrics, height }) };
  }

  /** How many slices the current host draws and hides: none hidden when the grid sizes itself. */
  layoutCounts() {
    const n = gridSlices(this.lastPayload).length;
    if (this.autoHeight || !this.lastPayload) return { shown: n, hidden: 0 };
    const { width, height } = this.size();
    if (!width || !height) return { shown: n, hidden: 0 };
    const layout = responseGridLayout(n, width, height, { legend: legendNames(this.lastPayload, this.lastOpts?.shower ?? 'both') });
    return { shown: layout.shown, hidden: layout.hidden };
  }

  /** The fitted μ and σ per (slice, series) of the retained payload; see `responseGridRows`. */
  tableRows() {
    return responseGridRows(this.lastPayload, this.lastOpts?.shower ?? 'both');
  }

  /** The key counts for the card's sparse notice; see `responseGridSparse`. */
  sparseLines() {
    if (!this.lastPayload) return [];
    return responseGridSparse(this.lastPayload, this.lastOpts?.shower ?? 'both', this.layoutCounts());
  }

  /**
   * Build the fit table into `host` (the card's `fit-table-*` element, or
   * plot 4's), with text nodes only: every label comes from a payload. An
   * empty host when nothing is retained.
   */
  renderTable(host) {
    if (!host) return;
    const doc = host.ownerDocument ?? globalThis.document;
    if (!this.lastPayload || !doc) {
      host.replaceChildren?.();
      return;
    }
    const model = responseGridTable(this.lastPayload, this.lastOpts?.shower ?? 'both');
    const el = (tag, text, cls) => {
      const node = doc.createElement(tag);
      if (text !== undefined && text !== null) node.textContent = text;
      if (cls) node.className = cls;
      return node;
    };
    const table = el('table', null, 'fit-table');
    const head = el('thead');
    const headRow = el('tr');
    model.columns.forEach((c, i) => headRow.append(el('th', c, i === 0 ? 'name' : null)));
    head.append(headRow);
    const body = el('tbody');
    for (const row of model.rows) {
      const tr = el('tr');
      const name = el('td', null, 'name');
      if (!row.empty) {
        const swatch = el('span', null, 'swatch');
        swatch.style.background = row.colour;
        name.append(swatch);
      }
      name.append(row.name);
      if (row.momentum) {
        const sub = el('span', row.momentum, 'uncert');
        sub.style.display = 'block';
        name.append(sub);
      }
      tr.append(name);
      if (row.empty) {
        const td = el('td', row.text, 'na');
        td.colSpan = model.columns.length - 1;
        tr.append(td);
      } else {
        for (const cell of row.cells) {
          const td = el('td', cell.text, cell.cls ?? null);
          if (cell.warn) td.style.color = 'var(--warn)';
          if (cell.title) td.title = cell.title;
          if (cell.uncert) td.append(' ', el('span', cell.uncert, 'uncert'));
          if (cell.sub) {
            const sub = el('span', cell.sub, 'uncert');
            sub.style.display = 'block';
            td.append(sub);
          }
          tr.append(td);
        }
      }
      body.append(tr);
    }
    table.append(head, body);
    host.replaceChildren(table);
  }
}
