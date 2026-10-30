/* The base of every 2-D physics panel below the 2 × 2, and the helpers they share.
 *
 * ## One class, pure builders
 *
 * Each physics panel (profile, response, response grid, distribution,
 * correlation) is a pure option builder - `profileOption(payload, opts,
 * metrics)` and so on - exported so Node can run it against the recorded
 * payloads, plus a thin subclass of `ChartPanel` that only delegates. Nothing
 * a reader sees is decided in the class: what is drawn, how it is clipped and
 * what every tooltip says live in the builder, where a test can reach them.
 *
 * ## The chart is made lazily, and only measured when it has a size
 *
 * The cards sit below the fold and load when scrolled into view, so the
 * ECharts instance is created on the first `render`/`ensureChart`, never at
 * construction. A card hidden with its section (the Event Inspector, compare)
 * has a zero-size plot: `relayout` and `paint` are then no-ops, and the
 * ResizeObserver repaints once the card is shown again. The observer is
 * debounced to one animation frame, as in EnergyPanel; the shell also calls
 * `relayout()` synchronously after a width change (main.js `relayoutAll`),
 * and the observer's own tick then finds nothing left to do. No CSS
 * transition may run on anything measured here.
 *
 * ## Tooltips
 *
 * Every chart takes its tooltip from `tooltip.js`: mounted on the fixed
 * `#tooltip-layer`, never confined, placed off the hovered plot. Two
 * placements are injected by `paint()` into the builder's `opts`:
 * `tooltipPosition` (explanations leave the chart) and `readoutPosition` (the
 * per-bin readout stays beside the pointer). They are absent when the
 * exporter rebuilds the option for print, where `tooltipOption(null)` is
 * valid. `liveGrid`, recorded at each live `setOption` and never inside the
 * builder, is the plot area the tips are kept off; small multiples record an
 * array and the union of their grids is used.
 *
 * ## Series colours that a reader can see
 *
 * A step outline or a marker is ink the reader must see, so its colour clears
 * 3:1 WCAG contrast against the card it is drawn on (CLAUDE.md section 2;
 * measured, not assumed). `categoricalStops` samples the theme's sub-range,
 * whose card-side end is below the floor on each card. `seriesStops` keeps
 * the part of that sub-range that clears 3:1 against `THEME.card`, so the
 * ordered lightness ramp survives and no series is drawn below the floor.
 * What holds on each card:
 *
 * - The dark screen card #1c2128: the sub-range is 0.25-1, whose lower end
 *   is only 2.1:1 on Viridis (1.7:1 on Cividis, 1.9:1 on Plasma). The 3:1
 *   runs of the whole ramp (`legibleRamp`): Viridis from 0.376, Cividis
 *   0.482, Plasma 0.431, Turbo 0.102-0.859; inside the sub-range Turbo's is
 *   0.251-0.859.
 * - The light screen card #ffffff: the sub-range is 0.75-0, reversed, and the
 *   3:1 runs are the dark ends: Viridis 0-0.600, Cividis 0-0.698, Plasma
 *   0-0.639, Turbo 0.749-1 (inside the sub-range, Turbo's dark blue end,
 *   0-0.176). Each is handed over oriented from the card outwards
 *   (`orientRun`), so on both screen cards the first series and the lowest
 *   value take the run's faintest 3:1 colour and contrast rises from there.
 * - White paper (print): the sub-range is 0-0.75 and the runs are the light
 *   card's, in the palette's standard direction, as print always drew them.
 *
 * The same floor holds for a mark drawn translucent: its colour is measured
 * composited over the card at the opacity it is drawn with
 * (`legibleOpacity`). A dispersion fill is a wash (bandAlpha, 1.4:1 on the
 * dark card) that only tints; the extent a reader must read is carried by a
 * dashed edge at ≥ 3:1 along the mark's long sides, dashed so it never reads
 * as a cap.
 *
 * ## Page 2
 *
 * The models page's panels (perf_bins, hist2d, rates, and the feature and
 * residual modes of distribution) reuse this base unchanged. Their shared
 * helpers are appended below the carets: the reserved band and its lifted
 * rows (the same mark response.js draws for B1), and the notice of a plot
 * with nothing estimable on it. The XGBoost cards add significant-figure
 * numbers, the ink on a coloured fill and the legible part of a ramp; a
 * builder that draws outside a cartesian grid returns its plot area as
 * `plotGrid` beside the option, for the tooltip placement.
 */

import { THEME, axisPadding, typographic, formatNumber } from '../scale.js';
import { categoricalStops, contrast, lookupTable } from '../palette.js';
import { fitsWidth, legendRows, wrapText } from '../textfit.js';
import {
  PREFER_POINTER, hideTooltipOnScroll, plotBoxFromGrid, tooltipPosition, tooltipOption,
} from './tooltip.js';

/** Plot-area height as a fraction of its width, for a publication figure. */
export const DEFAULT_ASPECT = 0.62;

/** Contrast every series colour must clear against the card it is drawn on. */
export const INK_CONTRAST = 3;

/* ------------------------------------------------------------- colour -- */

/** An [r, g, b] triple from '#rrggbb', '#rgb' or 'rgb(r, g, b)'; null otherwise. */
export function rgbOf(colour) {
  const text = String(colour ?? '').trim();
  let m = /^#([0-9a-f]{6})$/i.exec(text);
  if (m) {
    const v = parseInt(m[1], 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  m = /^#([0-9a-f]{3})$/i.exec(text);
  if (m) return [...m[1]].map((c) => parseInt(c + c, 16));
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i.exec(text);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  return null;
}

/**
 * The longest run of ramp positions inside [min, max] whose colour clears
 * `floor` contrast against `background`, as [lo, hi] in 0..1; null when no
 * position does. Turbo's lightness is not monotone, so the run is searched
 * rather than taken from one end.
 */
export function legibleRange(palette, background, { min = 0, max = 1 } = {}, floor = INK_CONTRAST) {
  const table = lookupTable(palette);
  const bg = rgbOf(background) ?? [28, 33, 40];
  const first = Math.max(0, Math.ceil(min * 255));
  const last = Math.min(255, Math.floor(max * 255));
  let best = null;
  let start = null;
  for (let i = first; i <= last + 1; i += 1) {
    const ok = i <= last
      && contrast([table[i * 3], table[i * 3 + 1], table[i * 3 + 2]], bg) >= floor;
    if (ok && start === null) start = i;
    if (!ok && start !== null) {
      if (!best || i - 1 - start > best[1] - best[0]) best = [start, i - 1];
      start = null;
    }
  }
  return best ? [best[0] / 255, best[1] / 255] : null;
}

/**
 * `count` ordered colours from `palette` for series a reader must see: the
 * theme's categorical sub-range, narrowed to where every colour clears 3:1
 * against the card (see the header). Falls back to the whole ramp's legible
 * run when the sub-range holds none, and to the plain sub-range only if the
 * ramp has no legible colour at all. On the light screen card the run is
 * oriented as `legibleRamp` orients it, so the first series is the faintest
 * 3:1 colour on either screen card; a single series takes the run's far end.
 */
export function seriesStops(palette, count) {
  const range = THEME.categorical ?? { min: 0.25, max: 1 };
  // The light sub-range is written reversed ({0.75, 0}); the search needs min <= max.
  const sorted = { min: Math.min(range.min, range.max), max: Math.max(range.min, range.max) };
  const legible = legibleRange(palette, THEME.card, sorted) ?? legibleRange(palette, THEME.card);
  if (!legible) return categoricalStops(palette, count, range);
  const [from, to] = orientRun(palette, legible, THEME.card);
  return categoricalStops(palette, count, { min: from, max: to });
}

/** The two shower colours, or the accent for a single shower. */
export function showerColour(key, nShowers = 2) {
  if (nShowers < 2) return THEME.accent;
  return key === 'b' ? THEME.showerB : THEME.showerA;
}

/** `colour` composited at `alpha` over `background` (both '#rrggbb' or rgb()), as [r, g, b]. */
export function blendOver(colour, alpha, background = THEME.card) {
  const c = rgbOf(colour) ?? [139, 148, 158];
  const bg = rgbOf(background) ?? [28, 33, 40];
  return c.map((v, i) => alpha * v + (1 - alpha) * bg[i]);
}

/**
 * The opacity a mark a reader must see is drawn at: `wanted`, raised to the
 * smallest alpha at which `colour` composited over the card clears `floor`
 * WCAG contrast against it (CLAUDE.md section 2, measured, not assumed). A
 * faded weak-bin mark or a de-weighted curve keeps its fading where the
 * colour allows it and stops at the floor where it does not: shower B's
 * #58a6ff needs 0.57 on the dark #1c2128 card, its light-screen and print
 * #0b5fbe 0.65 on white.
 */
export function legibleOpacity(colour, wanted = 1, floor = INK_CONTRAST) {
  const bg = rgbOf(THEME.card) ?? [28, 33, 40];
  const base = Math.min(1, Math.max(0, wanted));
  if (contrast(blendOver(colour, base), bg) >= floor) return base;
  for (let a = Math.ceil(base * 100); a <= 100; a += 1) {
    if (contrast(blendOver(colour, a / 100), bg) >= floor) return a / 100;
  }
  return 1;
}

/** Dash of the edges that outline a dispersion mark: never solid, so an edge cannot read as a cap. */
export const EDGE_DASH = [2, 2];

/**
 * A horizontal dispersion bar in pixel space (B1's and B3's ± 1 SD band in a
 * reserved-band row): a wash of `colour` from x `a` to `b`, `heightPx` tall
 * about `y`, with dashed edges along its two long sides at ≥ 3:1. No edge at
 * its ends: an end stroke would stand where a cap stands, and this is the
 * uncapped mark. A zrender group for `renderItem`.
 */
export function dispersionBar(a, b, y, heightPx, colour, { fillAlpha = THEME.bandAlpha } = {}) {
  const x = Math.min(a, b);
  const width = Math.abs(b - a);
  const top = y - heightPx / 2;
  const edge = { stroke: colour, lineWidth: THEME.lineAxis, lineDash: EDGE_DASH, opacity: legibleOpacity(colour, 0.7) };
  return {
    type: 'group',
    children: [
      { type: 'rect', shape: { x, y: top, width, height: heightPx }, style: { fill: colour, opacity: fillAlpha } },
      { type: 'line', shape: { x1: x, y1: top, x2: x + width, y2: top }, style: edge },
      { type: 'line', shape: { x1: x, y1: top + heightPx, x2: x + width, y2: top + heightPx }, style: edge },
    ],
  };
}

/**
 * A dispersion box in pixel space (B2's mean ± 1 SD over a momentum bin): a
 * wash with a dashed outline at ≥ 3:1 - dashed and as wide as its bin, so it
 * reads as a region, never as the solid, short caps of the whisker inside it.
 */
export function dispersionBox(x0, y0, x1, y1, colour, { fillAlpha = THEME.bandAlpha, edgeOpacity = 0.7 } = {}) {
  const x = Math.min(x0, x1);
  const y = Math.min(y0, y1);
  const width = Math.abs(x1 - x0);
  const height = Math.abs(y1 - y0);
  return {
    type: 'rect',
    shape: { x, y, width, height },
    style: {
      fill: colour,
      // Separate fill and stroke opacities: a faint wash, a legible edge.
      opacity: 1,
      fillOpacity: fillAlpha,
      stroke: colour,
      strokeOpacity: legibleOpacity(colour, edgeOpacity),
      lineWidth: THEME.lineAxis,
      lineDash: EDGE_DASH,
    },
  };
}

/**
 * The series with its colour as `itemStyle.color`, which is what the legend
 * swatch is painted with. A custom series draws itself in `renderItem` and
 * would otherwise show ECharts' default palette in the legend - a swatch
 * that names the wrong mark.
 */
export function withColour(series, color) {
  return { ...series, itemStyle: { ...(series.itemStyle ?? {}), color } };
}

/* --------------------------------------------------------------- text -- */

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** A muted line of tooltip HTML; `text` is escaped. */
export function mutedLine(text) {
  return `<span style="color:${THEME.muted}">${escapeHtml(text)}</span>`;
}

/** A tick label: three significant figures, trailing zeros dropped, U+2212. */
export function tickLabel(value) {
  const rounded = Number(Number(value).toPrecision(3));
  return typographic(String(rounded));
}

/** The first of `candidates` that fits `px` at the name font; else the last. */
export function fitName(candidates, px) {
  const list = candidates.filter(Boolean);
  return list.find((c) => fitsWidth(c, px, THEME.fontName, THEME.fontFamily)) ?? list[list.length - 1] ?? '';
}

/* --------------------------------------------------------------- axes -- */

/**
 * A value axis in the shared style: outward ticks, typographic labels, no
 * split lines unless asked. `labels: false` leaves the axis unlabelled - the
 * density axis with nothing estimable on it, which must not show a scale
 * nothing on the canvas is measured against.
 */
export function valueAxis({
  name = '', min, max, interval, labels = true, split = false, gridIndex,
  nameGap, nameLocation = 'middle', type = 'value', formatter = tickLabel,
  fontSize, splitNumber, nameSize, showMaxLabel,
} = {}) {
  const pad = axisPadding();
  return {
    type,
    ...(gridIndex !== undefined ? { gridIndex } : {}),
    name,
    nameLocation,
    nameGap: nameGap ?? pad.nameGap,
    nameTextStyle: { color: THEME.muted, fontSize: nameSize ?? THEME.fontName, fontFamily: THEME.fontFamily },
    ...(min !== undefined ? { min } : {}),
    ...(max !== undefined ? { max } : {}),
    ...(interval !== undefined && type === 'value' ? { interval } : {}),
    ...(splitNumber !== undefined ? { splitNumber } : {}),
    axisLine: { onZero: false, lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: labels, inside: false, lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisLabel: {
      show: labels,
      color: THEME.muted,
      fontSize: fontSize ?? THEME.fontLabel,
      fontFamily: THEME.fontFamily,
      hideOverlap: true,
      ...(showMaxLabel !== undefined ? { showMaxLabel } : {}),
      formatter,
    },
    splitLine: {
      show: split && labels,
      lineStyle: { color: THEME.grid, width: THEME.lineGrid, opacity: THEME.gridOpacity },
    },
  };
}

/**
 * A round axis top at or above `value` (1, 2, 2.5 or 5 × 10^k). Set
 * explicitly on the axes of custom series, whose data hold one point each,
 * so ECharts cannot take the extent from them; round so the top tick label
 * is a tick, not a stray value beside the last one.
 */
export function niceCeil(value, steps = NICE_STEPS) {
  if (!(value > 0)) return 1;
  const decade = 10 ** Math.floor(Math.log10(value));
  for (const step of steps) if (step * decade >= value * (1 - 1e-12)) return step * decade;
  return 10 * decade;
}

/** The mantissas `niceCeil` rounds to; FINE_STEPS wastes at most a quarter of the axis. */
export const NICE_STEPS = Object.freeze([1, 2, 2.5, 5, 10]);
export const FINE_STEPS = Object.freeze([1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]);

/** Divisions of a FINE_STEPS top that give round ticks, by its mantissa. */
const DIVISIONS = new Map([[1, 5], [1.2, 4], [1.5, 3], [2, 4], [2.5, 5], [3, 3], [4, 4], [5, 5], [6, 3], [8, 4], [10, 5]]);

/** A tick interval that lands on `top` exactly, for a top from `niceCeil(…, FINE_STEPS)`. */
export function niceInterval(top) {
  if (!(top > 0)) return 1;
  const decade = 10 ** Math.floor(Math.log10(top));
  const mantissa = Math.round((top / decade) * 10) / 10;
  return top / (DIVISIONS.get(mantissa) ?? 5);
}

/**
 * The server's tick interval, widened by a round factor until the ticks fit
 * `widthPx` at the label font: a small multiple keeps the server's range and
 * drops ticks rather than overprinting them.
 */
export function coarseInterval(lo, hi, interval, widthPx, fontPx = THEME.fontSmall) {
  if (!(interval > 0) || !(hi > lo)) return interval;
  const allowed = Math.max(2, Math.floor(widthPx / (3.2 * fontPx)));
  for (const factor of [1, 2, 4, 5, 10, 20, 25, 50, 100]) {
    if ((hi - lo) / (interval * factor) <= allowed) return interval * factor;
  }
  return (hi - lo) / allowed;
}

/** Widest a physics tooltip grows before its prose wraps (CSS px). */
export const TIP_MAX_WIDTH_PX = 400;

/**
 * The shared tooltip option (tooltip.js `tooltipOption`), with wrapped prose.
 *
 * ECharts styles every tip `white-space: nowrap`. The physics tips carry the
 * server's own sentences - an estimator note, a low-N message - and on one
 * line a B3 fit tip ran 1,760 px wide, off the side of a 1,600 px window.
 * `extraCssText` is appended after ECharts' style, so the tip wraps at
 * TIP_MAX_WIDTH_PX (never wider than the viewport less its margins); the
 * placement then measures the wrapped tip. Print never shows a tooltip.
 */
export function wrapTooltip(tooltip) {
  return {
    ...tooltip,
    extraCssText: `max-width: min(${TIP_MAX_WIDTH_PX}px, calc(100vw - 16px)); white-space: normal; overflow-wrap: break-word;`,
  };
}

/**
 * The shared legend: scrolls on screen, wraps in print (THEME.legendWrap).
 *
 * The scroll legend's page controls default to ECharts' #2f4554 arrow and
 * #333 page text, 1.62:1 and 1.28:1 against #1c2128, while the inactive
 * arrow (#aaa) is 6.97:1 - the live control was the one a reader could not
 * see. The active arrow takes the text ink, the page count the muted ink, and
 * the inactive arrow the border, which reads as disabled (the light card's
 * #d0d7de border is 1.45:1 there, as #30363d is 1.33:1 on the dark one).
 */
export function chartLegend(data, extra = {}) {
  return {
    show: data.length > 0,
    type: THEME.legendWrap ? 'plain' : 'scroll',
    top: 0,
    data,
    textStyle: { color: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily },
    inactiveColor: THEME.border,
    pageIconColor: THEME.text,
    pageIconInactiveColor: THEME.border,
    pageTextStyle: { color: THEME.muted, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily },
    itemWidth: 16,
    itemHeight: 8,
    ...extra,
  };
}

/**
 * The grid's top inset under a legend of `names`: one row on screen (it
 * scrolls), as many as the printed legend wraps to (THEME.legendWrap), so a
 * second row never overprints the plot. `ChartPanel.exportMetrics` reads it.
 * `wrap: true` (opt-in) counts the rows on screen too, for a legend built with
 * `wrappedLegend`, which wraps instead of paging.
 */
export function legendTop(names, plotWidthPx, { wrap = false } = {}) {
  const pad = axisPadding();
  const names2 = (names ?? []).map((n) => String(n?.name ?? n));
  const rows = !names2.length ? 1
    : ((THEME.legendWrap || wrap) ? Math.max(1, legendRows(names2, plotWidthPx, THEME.fontLabel, { fontFamily: THEME.fontFamily })) : 1);
  return pad.top + rows * 1.6 * THEME.fontLabel;
}

/**
 * A legend that wraps into rows over the plot's width on screen as in print,
 * never paging: every entry, interval names included, stays readable. Pair it
 * with `legendTop(names, plotWidthPx, {wrap: true})`, which counts the same
 * rows over the same width (`left` and `right` are the grid's insets).
 */
export function wrappedLegend(data, { left, right, ...extra } = {}) {
  return chartLegend(data, { type: 'plain', left, right, ...extra });
}

/**
 * σ of a fitted series as a reader must get it below the core-refit floor
 * (CLAUDE.md section 2): with its standard error, its asymmetric 95% χ²
 * interval and the bias factor c₄(N) - at N = 3 the true σ lies in
 * [0.52σ̂, 6.29σ̂], so a bare number is the misleading presentation. Above
 * the floor σ ± SE is enough. `unit` is appended to each value ('%', ' GeV').
 * Null when the fit has no σ (a single event).
 */
export function sigmaText(fit, { unit = '', coreFloor = 15, digits = 3 } = {}) {
  const f = fit ?? {};
  const sigma = f.sigma_core ?? f.sigma;
  if (!Number.isFinite(sigma)) return null;
  const n = f.n ?? 0;
  const fmt = (v) => `${formatNumber(v, digits)}${unit}`;
  let text = `σ = ${fmt(sigma)}${Number.isFinite(f.sigma_error) ? ` ± ${fmt(f.sigma_error)} (SE)` : ''}`;
  if (n < coreFloor) {
    if (Array.isArray(f.sigma_ci95) && Number.isFinite(f.sigma_ci95[0]) && Number.isFinite(f.sigma_ci95[1])) {
      text += `, χ² 95% interval ${fmt(f.sigma_ci95[0])} … ${fmt(f.sigma_ci95[1])}`;
    }
    if (Number.isFinite(f.sigma_bias_factor)) text += `, bias factor c₄(N) = ${formatNumber(f.sigma_bias_factor, 4)}`;
  }
  return text;
}

/**
 * A vertical reference rule at `at` (a plotted aggregate: B1's 1/c, B3's mean
 * incident momentum) with its 95% interval as a thin envelope - two hairlines
 * at the interval's ends, never a shaded band, which on this page means a
 * dispersion. The rule runs from `liftPx` above the baseline (the top of its
 * row in a reserved band, or the baseline itself) to the top of the plot, so
 * it makes no claim about a height. Returns the series to push.
 */
export function referenceRule({
  name, at, lo, hi, xMin, xMax, yMax, colour, liftPx = 0, label = null, labelDy = 0, tooltip, z = 4,
  dash = [2, 3],
}) {
  const out = [];
  const opacity = legibleOpacity(colour, 0.85);
  if (Number.isFinite(at) && at >= xMin && at <= xMax) {
    out.push({
      type: 'custom',
      name,
      clip: true,
      z,
      data: [[at, 0]],
      renderItem: (params, api) => {
        const base = api.coord([at, 0]);
        const top = api.coord([at, yMax]);
        const children = [{
          type: 'line',
          shape: { x1: base[0], y1: base[1] - liftPx, x2: top[0], y2: top[1] },
          style: { stroke: colour, lineWidth: THEME.lineAxis, lineDash: dash, opacity },
        }];
        if (label) {
          children.push({
            type: 'text',
            style: {
              x: top[0] + 4, y: top[1] + 2 + labelDy, text: label,
              fill: colour, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
            },
          });
        }
        return { type: 'group', children };
      },
      tooltip: { formatter: () => tooltip },
    });
  }
  const ends = [lo, hi].filter((v) => Number.isFinite(v) && v >= xMin && v <= xMax);
  if (ends.length) {
    const hairline = legibleOpacity(colour, 0.7);
    out.push({
      type: 'custom',
      name: `${name} · 95% interval`,
      clip: true,
      z,
      data: ends.map((v, index) => [v, 0, index]),
      renderItem: (params, api) => {
        const v = ends[params.dataIndex];
        const base = api.coord([v, 0]);
        const top = api.coord([v, yMax]);
        return {
          type: 'line',
          shape: { x1: base[0], y1: base[1] - liftPx, x2: top[0], y2: top[1] },
          style: { stroke: colour, lineWidth: 0.75 * THEME.lineAxis, opacity: hairline },
        };
      },
      tooltip: { formatter: () => tooltip },
    });
  }
  return out;
}

/** The common chart-level keys every builder starts from. */
export function baseOption() {
  return {
    backgroundColor: THEME.chartBackground,
    animation: false,
    textStyle: { fontFamily: THEME.fontFamily },
  };
}

/** The union of one or many grid options as a chart-local plot box. */
export function plotBoxOf(grid, width, height) {
  if (!Array.isArray(grid) || grid.length <= 1) return plotBoxFromGrid(grid, width, height);
  const boxes = grid.map((g) => plotBoxFromGrid(g, width, height));
  const left = Math.min(...boxes.map((b) => b.left));
  const top = Math.min(...boxes.map((b) => b.top));
  const right = Math.max(...boxes.map((b) => b.left + b.width));
  const bottom = Math.max(...boxes.map((b) => b.top + b.height));
  return { left, top, width: right - left, height: bottom - top };
}

/* ------------------------------------------------------------- carets -- */

/** Unit vectors of the four caret directions, in pixel space (y down). */
const CARET_DIRECTION = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

/**
 * Out-of-range indicators as one custom series, one hoverable item each: the
 * end of a mark clipped at the axis (CLAUDE.md section 2: clip it and say so,
 * with the true value in the tooltip). `carets` is `[{ at: [x, y], dir:
 * 'up' | 'down' | 'left' | 'right', tooltip, color? }]`; the tip sits on `at`
 * (a point on the axis edge) and the body inside the plot, so it is clipped
 * with the plot like every other mark. `offsetPx` shifts every caret as
 * `customWhiskers` does, `liftPx` raises every caret above its point (for
 * the reserved summary band). The multi-item twin of marks.js `customCaret`.
 */
export function caretSeries({
  name, carets, color, sizePx = 6, opacity = 1, z = 10, offsetPx = 0, liftPx = 0,
}) {
  const items = carets.filter((c) => Number.isFinite(c.at?.[0]) && Number.isFinite(c.at?.[1]));
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: false,
    data: items.map((c, index) => [c.at[0], c.at[1], index]),
    renderItem: (params, api) => {
      const c = items[params.dataIndex];
      const p = api.coord(c.at);
      const tip = [p[0] + offsetPx, p[1] - liftPx];
      const [ux, uy] = CARET_DIRECTION[c.dir] ?? CARET_DIRECTION.up;
      const base = [tip[0] - ux * sizePx, tip[1] - uy * sizePx];
      const wing = 0.6 * sizePx;
      return {
        type: 'polygon',
        shape: { points: [tip, [base[0] - uy * wing, base[1] + ux * wing], [base[0] + uy * wing, base[1] - ux * wing]] },
        style: { fill: c.color ?? color, opacity },
      };
    },
    tooltip: { formatter: (p) => items[p.dataIndex]?.tooltip ?? name },
  };
}

/**
 * Clamp the interval [lo, hi] to the window [min, max]: the drawn ends, which
 * ends were cut, and the caps to keep (a cut end loses its cap, a caret marks
 * it instead). Null ends stay null.
 */
export function clampInterval(lo, hi, min, max) {
  const cutLo = Number.isFinite(lo) && lo < min;
  const cutHi = Number.isFinite(hi) && hi > max;
  const drawLo = Number.isFinite(lo) ? Math.min(Math.max(lo, min), max) : null;
  const drawHi = Number.isFinite(hi) ? Math.max(Math.min(hi, max), min) : null;
  return { lo: drawLo, hi: drawHi, cutLo, cutHi, caps: [!cutLo, !cutHi] };
}

/* ------------------------------------------------- reserved band (Page 2) -- */

/**
 * What every tooltip in a reserved band says (CLAUDE.md section 2: a mark on
 * the density axis at a height that is not a density lives in a tinted,
 * captioned band, and says so).
 */
export const OFFSET_NOTE = 'vertical position is a drawing offset, not a density';

/** The band captions, longest first; the first that fits the plot is drawn. */
export const BAND_CAPTIONS = Object.freeze([
  'events and summary marks — vertical positions are drawing offsets, not densities',
  'events and summary marks — offsets, not densities',
  'offsets, not densities',
]);

/**
 * A custom series of marks lifted in pixels above the y = 0 baseline: the
 * rows of a reserved band. `data` items carry their data x as `x`; `render(d,
 * api)` returns the zrender element. One hover target per item.
 */
export function liftedSeries({ name, data, render, tooltip = null, z = 8 }) {
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    data: data.map((d, index) => [d.x, 0, index]),
    renderItem: (params, api) => render(data[params.dataIndex], api, params),
    ...(tooltip ? { tooltip: { formatter: (p) => tooltip(data[p.dataIndex], p.dataIndex) } } : {}),
  };
}

/**
 * The tinted, captioned reserved band at the foot of a density plot, `bandTop`
 * pixels tall, with a rule along its top edge: one axis with a reserved zone,
 * not a second scale. The Page 2 twin of response.js's private band, so the
 * feature and residual histograms draw the same mark B1 does.
 */
export function reservedBand({ lo, hi, bandTop, caption, name = 'reserved summary band' }) {
  return {
    type: 'custom',
    name,
    silent: true,
    clip: true,
    z: 1,
    data: [[lo, 0]],
    renderItem: (params, api) => {
      const left = api.coord([lo, 0]);
      const right = api.coord([hi, 0]);
      const top = left[1] - bandTop;
      return {
        type: 'group',
        children: [
          {
            type: 'rect',
            shape: { x: left[0], y: top, width: right[0] - left[0], height: bandTop },
            style: { fill: THEME.muted, opacity: THEME.stripAlpha },
          },
          {
            // The band's edge is read, so it is muted ink (5.3:1), not the 1.3:1 border.
            type: 'line',
            shape: { x1: left[0], y1: top, x2: right[0], y2: top },
            style: { stroke: THEME.muted, lineWidth: THEME.lineGrid, lineDash: [3, 3] },
          },
          {
            type: 'text',
            style: {
              x: left[0] + 6, y: top + 3, text: caption, fill: THEME.muted,
              fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, opacity: 0.85,
            },
          },
        ],
      };
    },
  };
}

/** The first band caption that fits `plotWidthPx`. */
export function bandCaption(plotWidthPx) {
  return BAND_CAPTIONS.find((c) => fitsWidth(c, plotWidthPx - 12, THEME.fontSmall, THEME.fontFamily))
    ?? BAND_CAPTIONS[BAND_CAPTIONS.length - 1];
}

/** A centred, wrapped notice on an empty or unlabelled plot (a graphic element). */
export function noticeGraphic(text, x, y, widthPx) {
  return {
    type: 'text',
    silent: true,
    style: {
      x,
      y,
      text: wrapText(text, Math.max(80, widthPx - 8), THEME.fontTip, THEME.fontFamily).join('\n'),
      textAlign: 'center',
      textVerticalAlign: 'middle',
      fill: THEME.muted,
      fontSize: THEME.fontTip,
      fontFamily: THEME.fontFamily,
      lineHeight: 1.45 * THEME.fontTip,
    },
  };
}

/** The option of a plot with nothing to draw: unlabelled axes and one notice, never an empty scale. */
export function emptyChartOption(opts, metrics, text) {
  const pad = axisPadding();
  const width = metrics?.width || 600;
  const height = metrics?.height || 340;
  const plotW = Math.max(80, width - pad.left - pad.right);
  const plotH = Math.max(40, height - pad.top - pad.bottom);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOptionOf(opts)),
    grid: { left: pad.left, right: pad.right, top: pad.top, bottom: pad.bottom },
    xAxis: valueAxis({ labels: false }),
    yAxis: valueAxis({ labels: false }),
    graphic: [noticeGraphic(text, pad.left + plotW / 2, pad.top + plotH / 2, plotW - 8)],
    series: [],
  };
}

/** The shared tooltip with the panel's explanation placement, when one is injected. */
function tooltipOptionOf(opts) {
  return tooltipOption(opts?.tooltipPosition ?? null);
}

/* ------------------------------------------------ XGBoost panels (Page 2) -- */

const SUPERSCRIPT = {
  0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹', '-': '⁻', '+': '',
};

/**
 * `value` to `digits` significant figures, trailing zeros dropped: plain
 * between 10⁻³ and 10⁵, else "6.04×10⁻⁵" (the exponent's sign is the
 * superscript minus, never a hyphen). The XGBoost metrics span that range in
 * one card - a parity MSE of 5.8×10⁻⁹ rad² beside an R² of 0.99 - which a
 * fixed number of decimals cannot show.
 */
export function sigFigs(value, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value === 0) return '0';
  const a = Math.abs(value);
  if (a >= 1e-3 && a < 1e5) return typographic(String(Number(value.toPrecision(digits))));
  const [mantissa, exponent] = value.toExponential(digits - 1).split('e');
  const sup = [...String(Number(exponent))].map((c) => SUPERSCRIPT[c] ?? c).join('');
  return typographic(`${Number(mantissa)}×10${sup}`);
}

/**
 * Whether the print theme is in force: the medium, not the card's colour.
 *
 * This used to ask whether the card was near-white, which was the same
 * question while only print had a white card. The light screen theme has one
 * too, and is still a screen: the legible remap, the screen legend layout and
 * the screen notes all apply to it. A question about the card's colour is
 * `onLightCard`.
 */
export function isPrintTheme() {
  return THEME.medium === 'print';
}

/**
 * Whether `card` is a light ground (contrast below 2:1 against white): the
 * light screen card or white paper. The old print test, kept for what
 * depends on the ground rather than the medium.
 */
export function onLightCard(card = THEME.card) {
  const rgb = rgbOf(card) ?? [28, 33, 40];
  return contrast(rgb, [255, 255, 255]) < 2;
}

/**
 * The ink a label printed on `fill` takes: the theme's text colour, white or
 * black, whichever contrasts most. Mid-ramp fills need the extremes: Viridis
 * at 0.5 (#218e8c) is 4.49:1 against the print text #111827 and 5.2:1
 * against black.
 */
export function inkOn(fill) {
  const rgb = rgbOf(fill) ?? [128, 128, 128];
  const candidates = [THEME.text, '#ffffff', '#000000'];
  let best = candidates[0];
  let bestRatio = -1;
  for (const c of candidates) {
    const ratio = contrast(rgb, rgbOf(c) ?? [0, 0, 0]);
    if (ratio > bestRatio) { best = c; bestRatio = ratio; }
  }
  return best;
}

/**
 * A legible run `[lo, hi]` of `palette` as `[from, to]`: reversed when the
 * medium is the screen, `background` is a light card and the run's low end
 * has more contrast against it than its high end, so that contrast against
 * the card rises with value as it does on the dark card. Otherwise as given:
 * the dark card and print keep today's order exactly.
 */
function orientRun(palette, [lo, hi], background) {
  if (isPrintTheme() || !onLightCard(background)) return [lo, hi];
  const table = lookupTable(palette);
  const bg = rgbOf(background) ?? [255, 255, 255];
  const at = (t) => {
    const i = Math.max(0, Math.min(255, Math.round(t * 255)));
    return contrast([table[i * 3], table[i * 3 + 1], table[i * 3 + 2]], bg);
  };
  return at(lo) > at(hi) ? [hi, lo] : [lo, hi];
}

/**
 * A sequential ramp narrowed to the run that clears 3:1 against `background`
 * (`legibleRange`; the card in force by default): `{palette, from, to}`, the
 * colour of the lowest value at `from`. A fill a reader must see - a surrogate
 * leaf, a raster bin, a cube - is then never fainter than the card can show.
 *
 * On the light screen card the run is oriented from the card outwards (from
 * above to; `orientRun`), Martin's "contrast rises with value": Viridis from
 * 0.600 (#22a784) to 0 (#440154) on white. On the dark card and in print it is
 * the run in the palette's own order, as it always was: Viridis from 0.376 to
 * 1 on #1c2128. A figure measured against a fixed card (the Methodology
 * exhibits) passes that card, so it never depends on the screen theme.
 */
export function legibleRamp(palette, background = THEME.card) {
  const range = legibleRange(palette, background) ?? [0, 1];
  const [from, to] = orientRun(palette, range, background);
  return { palette, from, to };
}

/** The colour at fraction `f` (0..1) of a `legibleRamp`, as '#rrggbb'. */
export function rampColour(ramp, f) {
  const table = lookupTable(ramp.palette);
  const clamped = Math.max(0, Math.min(1, Number.isFinite(f) ? f : 0));
  const t = ramp.from + clamped * (ramp.to - ramp.from);
  const i = Math.max(0, Math.min(255, Math.round(t * 255)));
  return `#${[table[i * 3], table[i * 3 + 1], table[i * 3 + 2]].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

/* -------------------------------------------------------------- class -- */

export class ChartPanel {
  /**
   * `elementOrId` is the plot element or its id; `kind` names the panel for
   * the exporter (anything but 'projection' takes figure.js's plain branch);
   * `aspect` is the plot-area height over its width in an exported figure.
   */
  constructor(elementOrId, { kind = 'chart', aspect = DEFAULT_ASPECT } = {}) {
    this.element = typeof elementOrId === 'string' ? document.getElementById(elementOrId) : elementOrId;
    this.kind = kind;
    this.aspect = aspect;
    this.chart = null;
    this.liveGrid = null;
    this.lastPayload = null;
    this.lastOpts = null;
    // The container size the current option was laid out at.
    this.laidOut = null;
    this.tooltipPosition = null;
    this.readoutPosition = null;
    this.resizeObserver = null;
  }

  /** Create the chart on first use; idempotent. */
  ensureChart() {
    if (this.chart || !this.element) return this.chart;
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    const plotBox = () => plotBoxOf(this.liveGrid, this.chart.getWidth(), this.chart.getHeight());
    // Explanations leave the chart; the per-bin readout stays beside the pointer.
    this.tooltipPosition = tooltipPosition(this.chart, plotBox);
    this.readoutPosition = tooltipPosition(this.chart, plotBox, { prefer: PREFER_POINTER });
    hideTooltipOnScroll(this.chart);
    this.observeResize();
    return this.chart;
  }

  observeResize() {
    if (typeof ResizeObserver !== 'function' || !this.element) return;
    if (this.resizeObserver) this.resizeObserver.disconnect();
    let pending = 0;
    this.resizeObserver = new ResizeObserver(() => {
      if (pending) return;
      pending = requestAnimationFrame(() => {
        pending = 0;
        this.relayout();
      });
    });
    this.resizeObserver.observe(this.element);
  }

  /** The element's current size; zero when the card is hidden. */
  size() {
    return { width: this.element?.clientWidth ?? 0, height: this.element?.clientHeight ?? 0 };
  }

  /** Draw `payload`; held for a hidden card and painted when it is shown. */
  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    this.ensureChart();
    this.paint();
  }

  /** Build and show the option for the retained payload at the current size. */
  paint() {
    if (!this.chart || !this.lastPayload) return null;
    const { width, height } = this.size();
    if (!width || !height) return null;
    const opts = {
      ...(this.lastOpts || {}),
      tooltipPosition: this.tooltipPosition,
      readoutPosition: this.readoutPosition,
    };
    const { option, plotGrid = null } = this.buildOption({ payload: this.lastPayload, opts, metrics: { width, height } });
    this.laidOut = { width, height };
    this.liveGrid = option.grid ?? null;
    // A builder that draws outside any cartesian grid (a tree, a matrix)
    // names the plot area its tips must stay off as `plotGrid`.
    if (plotGrid) this.liveGrid = plotGrid;
    this.chart.setOption(option, { notMerge: true });
    return option;
  }

  /** Re-lay the retained payload out at the container's current size. */
  relayout() {
    if (!this.chart) return;
    const { width, height } = this.size();
    if (!width || !height) return;
    const sized = this.chart.getWidth() === width && this.chart.getHeight() === height;
    if (sized && this.laidOut && this.laidOut.width === width && this.laidOut.height === height) return;
    if (!sized) this.chart.resize();
    this.laidOut = { width, height };
    if (this.lastPayload) this.paint();
  }

  /**
   * Figure dimensions for a publication export of the given printed width.
   *
   * A printed legend wraps (THEME.legendWrap), and how many rows it takes
   * depends on the figure width, so the option is built once at that width
   * and its grid's top inset - which the builder grows by the legend rows -
   * is what the figure reserves above the plot, as EnergyPanel measures it.
   */
  exportMetrics(width) {
    const pad = axisPadding();
    const plotWidth = Math.max(80, width - pad.left - pad.right);
    let top = pad.top;
    if (this.lastPayload) {
      const { option } = this.buildOption({ payload: this.lastPayload, opts: this.lastOpts || {}, metrics: { width, height: 400 } });
      const grid = Array.isArray(option.grid) ? option.grid[0] : option.grid;
      if (Number.isFinite(grid?.top)) top = grid.top;
    }
    return { width, height: Math.round(top + pad.bottom + plotWidth * this.aspect) };
  }

  /** The option for `payload`; subclasses delegate to their pure builder. */
  buildOption() {
    return { option: baseOption() };
  }

  /** Forget the picture and the payload: nothing stale stays on screen. */
  clear() {
    this.chart?.clear();
    this.lastPayload = null;
    this.lastOpts = null;
    this.liveGrid = null;
    this.laidOut = null;
  }

  setBusy(busy) {
    this.element?.classList.toggle('is-busy', Boolean(busy));
  }
}
