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
 * construction. A card hidden with its section (the Event Inspector, compare,
 * a Models subpage off show) has a zero-size plot: `relayout` is then a no-op
 * and `paint` holds the picture and forgets its layout, so the ResizeObserver
 * rebuilds it, with the tokens in force, once the card is shown again. The observer is
 * debounced to one animation frame, as in EnergyPanel; the shell also calls
 * `relayout()` synchronously after a width change (main.js `relayoutAll`),
 * and the observer's own tick then finds nothing left to do. No CSS
 * transition may run on anything measured here.
 *
 * ## The legend remembers what the reader switched off
 *
 * Every paint is `setOption(option, {notMerge: true})`, and with notMerge
 * ECharts builds a new GlobalModel: the legend's `selected` state went with
 * the old one, so a series the reader had switched off came back on every
 * repaint (a theme switch, a palette, a card control, a relayout). The panel
 * therefore listens to the legend's events (`LEGEND_EVENTS`: a click on an
 * entry, and the scripted select, unselect, select-all and inverse) and
 * records what each changed in `legendSelected`, {name: shown}; every paint
 * lays it over the builder's option (`withLegendMemory`). The builder's own
 * `selected` defaults survive wherever the reader has not changed them, and a
 * name the legend on show does not list stays in the memory for the view,
 * mode or payload that lists it again. The memory lives as long as the
 * panel: across payloads, views, themes, card controls and `clear()`. It is
 * the reader's, like the Physics page's Marks toggle, and never enters the
 * URL hash, the view state or the Admin defaults. The exporter applies it
 * too (export/figure.js), so a figure leaves out what the screen hides, with
 * their legend entries (below), and every mark of a switched-off entry leaves
 * the screen with it (below). Page 1's energy panel is
 * not a ChartPanel and keeps the same memory through the same helpers
 * (`listenToLegend`, `setOptionWithLegend`).
 *
 * A hidden entry stays legible. ECharts draws it, text and swatch, in the
 * legend's `inactiveColor`, which `chartLegend` sets to `THEME.border`: 1.33:1
 * on the dark card and 1.45:1 on the light one, too faint for the reader to
 * find the entry and switch it back on. While the memory hides an entry its
 * legend takes `legendInactiveInk()`, the faintest tint of the muted ink of
 * the entries on show that still clears 4.5:1 on the card, for the text, the
 * swatch and a line series' swatch line (`withInactiveInk`). The builders and
 * the dark golden keep `THEME.border`: the ink is laid at paint time, and only
 * while something is hidden. A click that hides an entry merges the ink into
 * the legend on show at once, before the repaint it asks for at the next frame
 * (below), and that repaint keeps the legend's page.
 *
 * ## A switched-off entry takes every mark of it along
 *
 * ECharts' legend filter hides only the series named after an entry. Many
 * builders draw an entry's companions under other names (an interval, a
 * dispersion, a mean, a "(clipped)" caret, an events-beyond caret shared with
 * other entries, a bin readout naming every series) and text of their own (the
 * resolution card's note band and end labels), which the filter cannot reach.
 * So every builder reads one legend context, `hiddenEntries()`, the entries
 * whose marks it leaves out: each mark of such an entry, its companions and
 * any text drawn only for it; a mark shared with entries still on show stays
 * and names only those. The screen and an export set it alike:
 *
 * - On screen, a paint builds under the names the reader switched off
 *   (`screenBuild`, `withScreenHidden`), and a legend event repaints the panel
 *   at the next frame (`repaintForLegend`), so the companions leave with their
 *   entry and come back with it (Martin's decision, 2026-11-17: the screen
 *   draws what its export would). The legend keeps the entry, greyed, so a
 *   click brings it back: a builder that left out every series of the entry
 *   is given one back as its legend carrier (`withLegendCarriers`), because
 *   ECharts draws an entry only for a name some series carries. With nothing
 *   switched off a paint builds once with no context, so the builders' outputs
 *   and the dark golden do not move.
 * - An export leaves out a switched-off series together with its legend entry,
 *   and lays the legend rows out without it. export/figure.js sets the export's
 *   legend context (`setExportHidden`, the names `legendOffNames` reads off the
 *   legend on show: the reader's memory and a builder's own defaults) inside
 *   its synchronous window, where it already swaps the print tokens, and clears
 *   it in the same `finally`. Only in an export does `chartLegend` list none of
 *   those names, mark each it dropped false in its `selected` (so its series is
 *   filtered with no entry listing it) and hide a legend left with no entry;
 *   `legendTop` count the rows of the kept names only, so the figure's height
 *   is laid out without them; and `legendShown` give a custom legend layout the
 *   same list. On screen each of these is the identity.
 *
 * Each legend event also tells the panel's `onLegendChange`: the page then
 * rebuilds the card's Details drawer, whose Marks and legend section names the
 * series the reader hid (`legendHiddenNames`, `legendHiddenLine`; added by
 * panel_notes.js `withHiddenLegend` where a section assembles a drawer).
 *
 * While the memory hides anything, and on every repaint for a legend event,
 * `paint` clears the chart before the new option, which disposes every series
 * view. ECharts 5.5.1 reuses a custom
 * series' view across `setOption(notMerge)` when the series id is the same.
 * When the legend filters a series, its view's group is emptied, but the
 * view keeps its old data, whose elements are now detached. The next render
 * of that series (shown again, or the legend memory gone) with fewer items
 * then removes one of those elements through `el.parent.remove(el)`, and
 * throws "TypeError: Cannot read properties of null (reading 'remove')" (the
 * vendored stack: gR ← t._remove ← t._executeOneToOne ← execute ← e.render).
 * The throw stops the render loop midway: the series already drawn (a
 * series' markers come first) show, and its lines and bands never draw. The
 * chart is not cleared on every paint, because `clear` rebuilds every
 * element, a big raster's on each resize.
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
 * - The light screen card #ffffff: each slot draws its white-grounded ramp
 *   (palette.js, `scale.screenPalette`), which runs from a pale tint to a deep
 *   tone, so the sub-range is 0.25-1 as on the dark card and the 3:1 runs are
 *   the deep ends: the Viridis slot from 0.537, Cividis 0.384, Plasma 0.420.
 *   On both screen cards the first series and the lowest value take the run's
 *   faintest 3:1 colour, and contrast rises from there.
 * - White paper (print): the sub-range is 0-0.75 of the standard ramps, as
 *   print always drew them.
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

import { THEME, axisPadding, typographic, formatNumber, screenPalette } from '../scale.js';
import { categoricalStops, contrast, lookupTable } from '../palette.js';
import { fitsWidth, legendRows, wrapText } from '../textfit.js';
import {
  PREFER_POINTER, hideTooltipOnScroll, plotBoxFromGrid, tooltipPosition, tooltipOption,
} from './tooltip.js';

/** Plot-area height as a fraction of its width, for a publication figure. */
export const DEFAULT_ASPECT = 0.62;

/** Contrast every series colour must clear against the card it is drawn on. */
export const INK_CONTRAST = 3;

/** Contrast every text colour must clear against the card it is drawn on (CLAUDE.md section 2). */
export const TEXT_CONTRAST = 4.5;

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
 * ramp has no legible colour at all. `chosen` is the colour-map slot; on the
 * light screen it draws its white-grounded ramp (`scale.screenPalette`), so
 * the first series is the faintest 3:1 colour on either screen card; a single
 * series takes the run's far end.
 */
export function seriesStops(chosen, count) {
  // The ramp the slot draws in the theme in force (the light screen's own).
  const palette = screenPalette(chosen);
  const range = THEME.categorical ?? { min: 0.25, max: 1 };
  const legible = legibleRange(palette, THEME.card, range) ?? legibleRange(palette, THEME.card);
  if (!legible) return categoricalStops(palette, count, range);
  return categoricalStops(palette, count, { min: legible[0], max: legible[1] });
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
  const legend = {
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
  // An export in progress leaves out what the legend on show switched off (see the header); on screen the legend
  // keeps every entry, a switched-off one greyed, so a click brings it back.
  if (!exportContext || !hiddenNames || !Array.isArray(legend.data)) return legend;
  const kept = legendShown(legend.data);
  if (kept === legend.data) return legend;
  const keptNames = new Set(kept.map(entryName));
  const dropped = legend.data.map(entryName).filter((name) => !keptNames.has(name));
  return {
    ...legend,
    show: legend.show !== false && kept.length > 0,
    data: kept,
    selected: { ...(legend.selected ?? {}), ...Object.fromEntries(dropped.map((name) => [name, false])) },
  };
}

/* ------------------------------------------------------- the legend context -- */

/**
 * The entries whose marks every builder leaves out (a Set), or null when none is (see the header). A paint sets it
 * for the names the reader switched off on the legend on show (`withScreenHidden`, through `screenBuild`); an
 * export sets it for the names its figure leaves out (`setExportHidden`, export/figure.js). Builders read it
 * through `hiddenEntries()`.
 */
let hiddenNames = null;

/** True while an export sets the context: its legends then list none of the hidden names and lay out without them. */
let exportContext = false;

/** The name of a legend entry: a string, or an object's `name`. */
function entryName(entry) {
  return String(entry !== null && typeof entry === 'object' ? entry.name : entry);
}

/** `names` as a Set of strings, or null when it holds none. */
function nameSet(names) {
  const list = Array.isArray(names) ? names.filter((n) => n !== null && n !== undefined).map(String) : [];
  return list.length ? new Set(list) : null;
}

/** Set the export's legend context: the names its legends leave out (an array of strings), or null/empty to clear it. */
export function setExportHidden(names) {
  hiddenNames = nameSet(names);
  exportContext = hiddenNames !== null;
}

/**
 * Run `fn` under the screen's legend context: every builder leaves out each mark of the entries `names` (the
 * ones the reader switched off on the legend on show), while the legends keep listing them, greyed, so a click
 * brings them back. The context in force before is restored however `fn` ends. Returns what `fn` returns.
 */
export function withScreenHidden(names, fn) {
  const before = [hiddenNames, exportContext];
  hiddenNames = nameSet(names);
  exportContext = false;
  try {
    return fn();
  } finally {
    [hiddenNames, exportContext] = before;
  }
}

/**
 * The Set of entries whose marks a builder leaves out: those the reader switched off, while a paint draws on
 * screen, or those an export leaves out; null when there are none. A builder leaves out each mark of such an
 * entry: its own series and its companions (an interval, a dispersion, a mean, a "(clipped)" caret, a value
 * label) and any text on the canvas drawn only for it; a mark shared with entries still on show stays and
 * names only those.
 */
export function hiddenEntries() {
  return hiddenNames;
}

/** Whether the context in force is an export's: its legends then drop the hidden entries (`chartLegend`, `legendTop`). */
export function isExportContext() {
  return exportContext;
}

/**
 * An entry whose legend name is chosen by width (`fitName` over `candidates`) is left out of an export under the
 * name it takes at the export's width, `chosen`, when the legend on show switched it off under another of its names
 * (review R2-3: a card about 1100 px wide names an envelope in full, a single-column figure in short). Export only:
 * a paint on screen lays out at the width the reader clicked at, where the names are the legend's own. The
 * name-choosing function calls it, so every reader of the name agrees.
 */
export function exportAlias(candidates, chosen) {
  if (!exportContext || !hiddenNames || chosen === null || chosen === undefined) return;
  if ((candidates ?? []).some((n) => hiddenNames.has(String(n)))) hiddenNames.add(String(chosen));
}

/**
 * `entries` (strings or {name}) without the export's left-out names; the same array object when nothing is left
 * out, and always on screen, where the legend keeps a switched-off entry.
 */
export function legendShown(entries) {
  if (!exportContext || !hiddenNames || !Array.isArray(entries)) return entries;
  const kept = entries.filter((entry) => !hiddenNames.has(entryName(entry)));
  return kept.length === entries.length ? entries : kept;
}

/** The names the memory ({name: shown}) switches off, in its order. */
function memoryOff(memory) {
  return Object.entries(memory ?? {}).filter(([, shown]) => shown === false).map(([name]) => name);
}

/**
 * The names the legends of `option` list, as a Set: each shown legend's `data`, or, for a legend without `data`,
 * every named series (ECharts lists each there). A hidden legend (`show: false`) lists none.
 */
export function listedNames(option) {
  const out = new Set();
  const series = [option?.series ?? []].flat();
  for (const legend of [option?.legend ?? []].flat()) {
    if (!legend || typeof legend !== 'object' || legend.show === false) continue;
    if (Array.isArray(legend.data)) {
      for (const d of legend.data) out.add(entryName(d));
    } else {
      for (const s of series) if (s && s.name !== undefined && s.name !== null && s.name !== '') out.add(String(s.name));
    }
  }
  return out;
}

/**
 * The names `panel`'s memory switches off that the legends of `option` list (`listedNames`): the entries a paint
 * of that option leaves out on screen, in the memory's order. A remembered name the option does not list is not
 * among them: nothing of it is drawn, and no entry would bring back a mark left out for it.
 */
export function screenHiddenNames(panel, option) {
  const off = memoryOff(panel?.legendSelected);
  if (!off.length) return [];
  const listed = listedNames(option);
  return off.filter((name) => listed.has(name));
}

/**
 * `option` (built under the screen context) with a legend carrier for each name of `off` that none of its series
 * carries: the first series of that name in `plain`, the same option built with no context. ECharts draws a
 * legend entry only for a name some series carries (LegendView: `getSeriesByName(name)[0]`), so without one the
 * switched-off entry would leave the legend and could not be clicked back on. The carrier is the very series
 * whose look the entry had, so its swatch does not change; the legend filter hides it, as it hid the series.
 * An `id` another series already holds is dropped. `option` itself when nothing is carried.
 */
function withLegendCarriers(option, plain, off) {
  if (!option?.legend) return option;
  const series = [option.series ?? []].flat();
  const carried = new Set(series.filter((s) => s && s.name !== undefined && s.name !== null).map((s) => String(s.name)));
  const ids = new Set(series.filter((s) => s && s.id !== undefined && s.id !== null).map((s) => String(s.id)));
  const carriers = [];
  for (const name of off) {
    if (carried.has(name)) continue;
    const first = [plain?.series ?? []].flat().find((s) => s && String(s.name) === name);
    if (!first) continue;
    const carrier = { ...first };
    if (carrier.id !== undefined && carrier.id !== null && ids.has(String(carrier.id))) delete carrier.id;
    carriers.push(carrier);
  }
  return carriers.length ? { ...option, series: [...series, ...carriers] } : option;
}

/**
 * What a paint of `panel` sets on screen: `build()` (a builder's {option, ...}) under the screen's legend context.
 * With nothing switched off in the reader's memory, one build with no context, exactly as before (the dark golden
 * does not move). Otherwise the option is built once with no context (`plain`), which says what its legends list;
 * with no listed name switched off, that is the result. Else it is built again with those names hidden
 * (`withScreenHidden`), so every builder leaves out their marks, companions and text as an export does, and given
 * their legend carriers (`withLegendCarriers`). The result is the second build's, with `plain` (the first build,
 * for what never depends on the legend: the energy card's notices and table) and `hidden` (the names left out).
 */
export function screenBuild(panel, build) {
  if (!memoryOff(panel?.legendSelected).length) return build();
  const plain = build();
  const off = screenHiddenNames(panel, plain?.option);
  if (!off.length) return plain;
  const built = withScreenHidden(off, build);
  return { ...built, option: withLegendCarriers(built.option, plain.option, off), plain, hidden: off };
}

/**
 * The names the legends on show (`panel.liveLegend`, an object or an array)
 * list that their `selected` marks false, in legend order, once each: the
 * reader's memory and a builder's own defaults, which is what an export
 * leaves out. A legend lists its `data`, or the keys of its `selected` when it
 * has none; a hidden legend (`show: false`) is skipped. [] without one.
 */
export function legendOffNames(panel) {
  const out = [];
  // The reader's memory laid over the legend on show first: a legend click repaints only at the next frame, so the
  // live legend's own `selected` can be as of an earlier paint, and a second click, or a click that turns an entry
  // back on, is in the memory alone until then (review R2-1, R2-2). A true in the memory clears a stale false.
  const live = panel?.liveLegend ?? null;
  const laid = live ? withLegendMemory({ legend: live }, panel?.legendSelected).legend : null;
  for (const legend of [laid ?? []].flat()) {
    if (!legend || typeof legend !== 'object' || legend.show === false) continue;
    const selected = legend.selected ?? {};
    const names = Array.isArray(legend.data) ? legend.data.map(entryName) : Object.keys(selected);
    for (const name of names) if (selected[name] === false && !out.includes(name)) out.push(name);
  }
  return out;
}

/**
 * The chart events that carry a reader's legend choice (ECharts 5.5.1,
 * `installLegendAction`): a click on an entry dispatches `legendToggleSelect`,
 * whose event is `legendselectchanged`; the others answer the scripted
 * `legendSelect`, `legendUnSelect`, `legendAllSelect` and
 * `legendInverseSelect`. Each event carries every legend's `selected` map as
 * the action left it, and the named ones the entry acted on.
 */
export const LEGEND_EVENTS = Object.freeze([
  'legendselectchanged', 'legendselected', 'legendunselected', 'legendselectall', 'legendinverseselect',
]);

/**
 * What one legend event changed, as {name: shown}. A named event changes its
 * entry alone; select-all and inverse change every entry, so their whole
 * `selected` map is taken. Only the named entry is taken from a named event,
 * because its `selected` map also holds every entry the reader did not touch,
 * and recording those would pin the builder's defaults. (A legend with
 * `selectedMode: 'single'` would change the other entries too; no builder
 * sets one.) A batched dispatch carries its events in `batch`.
 */
export function legendChange(event) {
  const out = {};
  for (const e of Array.isArray(event?.batch) ? event.batch : [event]) {
    const selected = e?.selected;
    if (!selected || typeof selected !== 'object') continue;
    const named = e.name !== undefined && e.name !== null;
    for (const name of named ? [String(e.name)] : Object.keys(selected)) {
      if (typeof selected[name] === 'boolean') out[name] = selected[name];
    }
  }
  return out;
}

/** Whether a legend memory ({name: shown}) hides any entry. */
export function legendHides(memory) {
  return Object.values(memory ?? {}).some((shown) => shown === false);
}

/**
 * `option` with the reader's legend choices laid over it (see the header):
 * each legend's `selected` becomes `{...builder's selected, ...memory}`, for
 * an object legend or for each legend of an array. Only the names a legend
 * lists are applied when it lists its entries (`data`): ECharts' legend
 * filter hides a series of any name its `selected` marks false, listed or
 * not, so a remembered name the legend on show does not list would hide a
 * series with no entry to bring it back. A legend that lists none (`data`
 * absent) has an entry for every named series, and takes the whole memory; a
 * hidden legend (`show: false`) takes none. The option is returned as it is,
 * the same object, when the memory is empty or changes no legend, so the pure
 * builders' outputs and the dark golden do not move. `memory` is not changed.
 */
export function withLegendMemory(option, memory) {
  const entries = Object.entries(memory ?? {}).filter(([, shown]) => typeof shown === 'boolean');
  if (!option?.legend || !entries.length) return option;
  const apply = (legend) => {
    if (!legend || typeof legend !== 'object' || legend.show === false) return legend;
    const listed = Array.isArray(legend.data)
      ? new Set(legend.data.map((d) => String(d !== null && typeof d === 'object' ? d.name : d)))
      : null;
    const remembered = entries.filter(([name]) => !listed || listed.has(name));
    if (!remembered.length) return legend;
    return { ...legend, selected: { ...(legend.selected ?? {}), ...Object.fromEntries(remembered) } };
  };
  if (Array.isArray(option.legend)) {
    const legends = option.legend.map(apply);
    return legends.every((l, i) => l === option.legend[i]) ? option : { ...option, legend: legends };
  }
  const legend = apply(option.legend);
  return legend === option.legend ? option : { ...option, legend };
}

/**
 * The ink of a legend entry the reader switched off, its text and its swatch,
 * on the card in force: the faintest tint of `THEME.muted`, the ink of the
 * entries on show, that still clears TEXT_CONTRAST against `THEME.card`, so
 * the entry reads as off and can be found again. Each channel of the tint is
 * rounded towards the muted ink, which can only raise its contrast, and the
 * rounded colour is measured again. From the tokens, so it follows the theme:
 *
 * - the dark screen card #1c2128: #808993 at 4.56:1, beside the muted #8b949e
 *   at 5.26:1. The card leaves little room under the muted ink, so the grey
 *   swatch is what mostly says "off";
 * - the light screen card #ffffff: #6e7780 at 4.55:1, beside #59636e at 6.11:1.
 *
 * Screen only: an export greys nothing. It leaves a switched-off entry out of
 * its legend together with its series (export/figure.js `printLegendOption`).
 */
export function legendInactiveInk() {
  const card = rgbOf(THEME.card) ?? [28, 33, 40];
  const muted = rgbOf(THEME.muted) ?? [139, 148, 158];
  for (let step = Math.round(100 * legibleOpacity(THEME.muted, 0, TEXT_CONTRAST)); step <= 100; step += 1) {
    const rgb = blendOver(THEME.muted, step / 100, THEME.card)
      .map((v, i) => Math.max(0, Math.min(255, muted[i] >= card[i] ? Math.ceil(v) : Math.floor(v))));
    if (contrast(rgb, card) >= TEXT_CONTRAST) return `#${rgb.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  }
  return THEME.muted;
}

/**
 * `option` with each legend that hides an entry (a false in its `selected`,
 * which `withLegendMemory` lays there) drawing that entry in `ink`: its text
 * and swatch (`inactiveColor`, `inactiveBorderColor`) and a line series'
 * swatch line (`lineStyle.inactiveColor`, ECharts' own #ccc otherwise, 1.6:1
 * on white). `ink` defaults to `legendInactiveInk()` on the card in force,
 * measured only when a legend hides something. The option is returned as it
 * is, the same object, when no legend hides an entry, so the ink is laid only
 * while the reader hides one and the builders' outputs do not move. A hidden
 * legend (`show: false`) is left alone. `option` is not changed.
 */
export function withInactiveInk(option, ink = null) {
  if (!option?.legend) return option;
  let colour = ink;
  const inked = (legend) => {
    if (!legend || typeof legend !== 'object' || legend.show === false
      || !Object.values(legend.selected ?? {}).includes(false)) return legend;
    colour = colour ?? legendInactiveInk();
    return {
      ...legend,
      inactiveColor: colour,
      inactiveBorderColor: colour,
      lineStyle: { ...(legend.lineStyle ?? {}), inactiveColor: colour },
    };
  };
  if (Array.isArray(option.legend)) {
    const legends = option.legend.map(inked);
    return legends.every((l, i) => l === option.legend[i]) ? option : { ...option, legend: legends };
  }
  const legend = inked(option.legend);
  return legend === option.legend ? option : { ...option, legend };
}

/**
 * Set `option` on `panel.chart` with the reader's legend laid over it (see the
 * header): the memory (`withLegendMemory`), the legible ink of an entry it
 * hides (`withInactiveInk`) and, while it hides anything, the clear that
 * disposes every series view first: a custom series' view that the legend
 * emptied keeps its old data, and ECharts 5.5.1 throws when it next draws
 * fewer items from it. Only then: a clear rebuilds every element. The legend
 * set is kept as `panel.liveLegend`, which a legend event and the drawer
 * read. Returns the option set. ChartPanel and EnergyPanel paint through it.
 */
export function setOptionWithLegend(panel, option) {
  let shown = withInactiveInk(withLegendMemory(option, panel.legendSelected));
  // A repaint for a legend event keeps the page the reader had scrolled the legend to.
  if (panel.legendRepainting) shown = withLegendPage(shown, panel.chart);
  panel.liveLegend = shown.legend ?? null;
  if (legendHides(panel.legendSelected) || panel.legendRepainting) panel.chart.clear();
  panel.chart.setOption(shown, { notMerge: true });
  return shown;
}

/**
 * `option` with each scroll legend at the page the chart's legend of the same index is on (`scrollDataIndex`, which
 * ECharts' legendScroll action keeps in the legend's model): a repaint for a legend event would otherwise send the
 * reader back to the first page of a legend they had scrolled. The option itself when no page is to be kept.
 */
function withLegendPage(option, chart) {
  if (!option?.legend || typeof chart?.getModel !== 'function') return option;
  const model = chart.getModel();
  const pageOf = (i) => {
    const index = model?.getComponent?.('legend', i)?.get?.('scrollDataIndex');
    return Number.isFinite(index) && index > 0 ? index : null;
  };
  const paged = (legend, i) => {
    const index = legend && typeof legend === 'object' && legend.type === 'scroll' ? pageOf(i) : null;
    return index === null ? legend : { ...legend, scrollDataIndex: index };
  };
  if (Array.isArray(option.legend)) {
    const legends = option.legend.map(paged);
    return legends.every((l, i) => l === option.legend[i]) ? option : { ...option, legend: legends };
  }
  const legend = paged(option.legend, 0);
  return legend === option.legend ? option : { ...option, legend };
}

/**
 * Listen to the legend events of `panel.chart` (a ChartPanel, the energy
 * panel), once: each records what it changed in `panel.legendSelected`, an
 * entry it hides takes the legible ink at once (`inkLiveLegend`), the panel is
 * repainted at the next frame so every mark of the entry follows it
 * (`repaintForLegend`), and `panel.onLegendChange(panel)` is told, so the page
 * can rebuild the card's drawer. Guarded on `chart.on`, so the Node fakes keep
 * working.
 */
export function listenToLegend(panel) {
  const chart = panel.chart;
  if (typeof chart?.on !== 'function') return;
  const remember = (event) => {
    Object.assign(panel.legendSelected, legendChange(event));
    inkLiveLegend(panel);
    repaintForLegend(panel);
    if (typeof panel.onLegendChange === 'function') panel.onLegendChange(panel);
  };
  for (const type of LEGEND_EVENTS) chart.on(type, remember);
}

/**
 * Repaint `panel` at the next animation frame after a legend event (see the header). ECharts' own legend filter
 * hides only the series named after the entry, at once; the repaint draws the option again under the screen's
 * legend context (`screenBuild`), so the entry's companions and the text drawn only for it leave with it, and come
 * back with it. Coalesced: one repaint per frame however many events land. The chart is cleared first, so no
 * series view is reused across the legend's filter (see the header), and a scroll legend keeps its page. Nothing
 * for a panel without a picture; synchronous where there is no animation frame (the Node fakes).
 */
function repaintForLegend(panel) {
  if (typeof panel.paint !== 'function' || panel.legendRepaint) return;
  const run = () => {
    panel.legendRepaint = 0;
    if (!panel.lastPayload) return;
    panel.legendRepainting = true;
    try {
      panel.paint();
    } finally {
      panel.legendRepainting = false;
    }
  };
  if (typeof requestAnimationFrame === 'function') panel.legendRepaint = requestAnimationFrame(run);
  else run();
}

/**
 * Give the legend on show the legible ink of the entries the memory now
 * hides at once, before the repaint the event asks for: the legend still
 * carries the ink of its last paint, `THEME.border` while nothing was hidden,
 * and a frame is not to pass with an entry off in an illegible ink. Only the inks are merged
 * (`setOption` without notMerge), into each legend whose ink must change, so
 * the legend keeps its `selected` state and its page, and every series its
 * view. Nothing when no listed entry is hidden or the ink is already there.
 */
function inkLiveLegend(panel) {
  const live = panel.liveLegend;
  if (!live || typeof panel.chart?.setOption !== 'function') return;
  const next = withInactiveInk(withLegendMemory({ legend: live }, panel.legendSelected)).legend;
  const before = [live].flat();
  const patch = [next].flat().map((legend, i) => (legend?.inactiveColor !== before[i]?.inactiveColor
    ? { inactiveColor: legend.inactiveColor, inactiveBorderColor: legend.inactiveBorderColor,
      lineStyle: { inactiveColor: legend.lineStyle?.inactiveColor } }
    : {}));
  // The legend kept is the memory's whether or not its ink changes (review R2-1): every later reader sees every click.
  panel.liveLegend = next;
  if (!patch.some((p) => 'inactiveColor' in p)) return;
  panel.chart.setOption({ legend: Array.isArray(live) ? patch : patch[0] });
}

/**
 * The names the reader switched off on `panel`'s legend that the legend on
 * show lists (`panel.liveLegend`), in its order: what the drawer names. A
 * remembered name of another view, mode or payload is left out: nothing of it
 * is drawn, and the legend on show has no entry for it. A legend without
 * `data` lists every named series; its painted `selected` holds the names the
 * memory gave it. [] for a panel without a memory, or with nothing on show.
 */
export function legendHiddenNames(panel) {
  const memory = panel?.legendSelected ?? {};
  const out = [];
  for (const legend of [panel?.liveLegend ?? []].flat()) {
    if (!legend || typeof legend !== 'object' || legend.show === false) continue;
    const names = Array.isArray(legend.data)
      ? legend.data.map((d) => String(d !== null && typeof d === 'object' ? d.name : d))
      : Object.keys(legend.selected ?? {});
    for (const name of names) if (memory[name] === false && !out.includes(name)) out.push(name);
  }
  return out;
}

/**
 * The drawer's line naming the series the reader switched off on the legend
 * (`legendHiddenNames`), or null when there are none. The reader's own choice,
 * like the Marks toggle: said, never a hazard.
 */
export function legendHiddenLine(names) {
  const list = (names ?? []).filter((n) => n !== null && n !== undefined && String(n) !== '');
  if (!list.length) return null;
  const tail = list.length === 1
    ? 'Click its entry to show it again; an export leaves it out.'
    : 'Click an entry to show it again; an export leaves them out.';
  return `Hidden on the legend by the reader: ${list.join('; ')}. ${tail}`;
}

/**
 * The grid's top inset under a legend of `names`: one row on screen (it
 * scrolls), as many as the printed legend wraps to (THEME.legendWrap), so a
 * second row never overprints the plot. `ChartPanel.exportMetrics` reads it.
 * `wrap: true` (opt-in) counts the rows on screen too, for a legend built with
 * `wrappedLegend`, which wraps instead of paging. An export counts the rows of
 * the names it keeps (`legendShown`).
 */
export function legendTop(names, plotWidthPx, { wrap = false } = {}) {
  const pad = axisPadding();
  const names2 = (legendShown(names ?? []) ?? []).map((n) => String(n?.name ?? n));
  // An export that leaves every entry out lays out no legend row (review R2-6); on screen, and for a legend that never
  // had an entry, the one row stays as before.
  if (!names2.length && exportContext && (names ?? []).length) return pad.top;
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
 * A sequential ramp narrowed to the run that clears 3:1 against `background`
 * (`legibleRange`; the card in force by default): `{palette, from, to}`. A fill
 * a reader must see standing alone on the card - a surrogate leaf, a cube, a
 * 2-D histogram cell - is then never fainter than the card can show: Viridis
 * from 0.376 to 1 on the dark #1c2128, the light screen's Viridis slot from
 * 0.537 to 1 on white. The caller passes the ramp it draws (`screenPalette`).
 * A figure measured against a fixed card (the Methodology exhibits) passes
 * that card, so it never depends on the screen theme.
 */
export function legibleRamp(palette, background = THEME.card) {
  const range = legibleRange(palette, background) ?? [0, 1];
  return { palette, from: range[0], to: range[1] };
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
    // What the reader switched on and off on the legend, {name: shown}, for as
    // long as the panel lives (see the header); `clear()` keeps it.
    this.legendSelected = {};
    // The legend last set on the chart, memory and ink laid over it (`setOptionWithLegend`).
    this.liveLegend = null;
    // Told after each legend event, with the panel: the page rebuilds the card's drawer.
    this.onLegendChange = null;
    // The entries the last paint left out on screen (`screenBuild`), and the repaint a legend event asked for.
    this.screenHidden = [];
    this.legendRepaint = 0;
    this.legendRepainting = false;
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
    this.rememberLegend();
    this.observeResize();
    return this.chart;
  }

  /** Record each legend choice the reader makes, so every later paint keeps it (see the header). */
  rememberLegend() {
    listenToLegend(this);
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
    if (!width || !height) {
      // Held at zero size (a card on a hidden subpage or section): forget the
      // layout, so the relayout that shows the card again rebuilds the option
      // with the tokens in force. Without this a theme switched meanwhile left
      // the old ink: the card came back at its old size, which `relayout`
      // took for an option already laid out.
      this.laidOut = null;
      return null;
    }
    const opts = {
      ...(this.lastOpts || {}),
      tooltipPosition: this.tooltipPosition,
      readoutPosition: this.readoutPosition,
    };
    const metrics = { width, height };
    // Under the screen's legend context: the marks of an entry the reader switched off leave with it (see the header).
    const built = screenBuild(this, () => this.buildOption({ payload: this.lastPayload, opts, metrics }));
    const { option, plotGrid = null } = built;
    this.screenHidden = built.hidden ?? [];
    this.laidOut = { width, height };
    this.liveGrid = option.grid ?? null;
    // A builder that draws outside any cartesian grid (a tree, a matrix)
    // names the plot area its tips must stay off as `plotGrid`.
    if (plotGrid) this.liveGrid = plotGrid;
    // The reader's legend choices laid over the builder's, a hidden entry in
    // a legible ink, and the clear while the legend hides a series (see the
    // header, which has the ECharts stack).
    return setOptionWithLegend(this, option);
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

  /** Forget the picture and the payload: nothing stale stays on screen. The legend memory stays with the panel. */
  clear() {
    this.chart?.clear();
    this.lastPayload = null;
    this.lastOpts = null;
    this.liveGrid = null;
    this.liveLegend = null;
    this.laidOut = null;
  }

  setBusy(busy) {
    this.element?.classList.toggle('is-busy', Boolean(busy));
  }
}
