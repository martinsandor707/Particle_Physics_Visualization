/* The one hover-tooltip configuration every chart uses, and where the tip goes.
 *
 * ## Mounted on a fixed layer, so nothing can clip it
 *
 * The tooltip was once cut off where it met the control sidebar. It was not
 * stacked under the sidebar; it was clipped. Its element lived inside the chart
 * container, and `.main` is a scroll container (`overflow-y: auto`, so
 * `overflow-x` computes to `auto` as well). That clips every descendant at its
 * padding box, whose left edge is the sidebar's right edge. No z-index escapes
 * an ancestor's overflow clip.
 *
 * `confine` fixed the clipping by keeping the tip inside its own chart, but
 * that traded one problem for another. A rich tip, such as an overlay's
 * explanation above the bin readout (about 360 × 180 px), was then pushed back
 * over the plot it explains. Measured on the demonstration data, it covered a
 * median 35% of the plot area at 1600 × 900 and up to 98% at 1280 × 800, and
 * often sat on the pointer.
 *
 * So every tip is mounted on `#tooltip-layer` (`appendTo`), a viewport-sized
 * `position: fixed` layer outside `.main` (index.html, layout.css), where
 * nothing clips it. Fixed rather than plain `<body>`, because ECharts hides a
 * tip without moving it. On `<body>`, a hidden tip left near the old bottom
 * edge made the document taller than a window that had since shrunk, and the
 * whole app shell could then scroll. A fixed box's contents never add to the
 * page's scroll size. `confine` is off, so nothing clamps the position below
 * back into the chart; ECharts maps it from chart-local pixels into the layer.
 *
 * ## Placed so the hovered panel stays visible
 *
 * Which rule applies depends on the kind of tip, not its size. Size varies from
 * bin to bin, so a size rule made the readout jump between the pointer and the
 * next panel as the pointer moved.
 *
 * - The plain bin readout (coordinates and the bin's value, no overlay above
 *   it) stays beside the pointer, as it always did: right of it, or left when
 *   the right side has no room (`prefer: 'pointer'`). It is small, and it is
 *   read against the bin under the pointer.
 * - Every explanatory tip leaves the hovered chart (`prefer: 'outside'`). That
 *   covers a mark's or an overlay's explanation (the text led by an overlay
 *   above the readout), and every tip on plot 4. It sits just outside the
 *   chart's element, on the side with the most room: over the neighbouring
 *   panel in the two-column layout, above or below in the one-column one.
 *
 * `placeTooltip` then works down a list, in viewport pixels. Each step is taken
 * only when the tip fits in the area and stays off the pointer:
 *
 * 1. beside the pointer, for a readout;
 * 2. outside the chart, inside the visible content area (`.main` within the
 *    viewport), then anywhere in the viewport, where the tip may cover the
 *    sidebar or the header (it is drawn above both, so it stays readable);
 * 3. outside the plot area, covering only this panel's axes and margins;
 * 4. failing all of those, the position that covers the least of the plot.
 *
 * The side depends on the layout (where the room is), not on the pointer. A tip
 * therefore does not hop from side to side as the pointer moves across a mark
 * or along a curve.
 *
 * `transitionDuration: 0` stops ECharts gliding a tip across the plot it has
 * just been moved off. `hideDelay: 0` hides a tip at once (these tips are
 * never `enterable`, so the delay bought nothing). A tip no longer moves with
 * its chart, so it would otherwise float for 100 ms after a scroll.
 *
 * ## One ECharts internal, pinned
 *
 * To place a tip in a container, zrender converts through transforms it
 * caches on the chart's viewport root (`___zrEVENTSAVED`: `trans` for pointer
 * capture, `invTrans` for the tooltip). Both are validated against one shared
 * `srcCoords`. After `.main` scrolls, whichever is rebuilt first marks the
 * other as current while it still holds the old geometry. Measured: a tip was
 * drawn 120-240 px from where it was placed, and a drag leaving the chart
 * panned from the wrong row. `resetPointerTransforms` drops both before every
 * placement and on every scroll, so each is rebuilt from the page as it is.
 * `tests/test_export_assets.py` pins the internal in the vendored bundle.
 */

import { THEME } from '../scale.js';

/** Class on every chart tooltip element: a hook for styling, not for stacking. */
export const TOOLTIP_CLASS = 'calo-tooltip';

/** The fixed, viewport-sized layer every tip is mounted on (index.html). */
export const TOOLTIP_LAYER = '#tooltip-layer';

/** Gap between the pointer, or the edge of the hovered chart, and the tip (CSS px). */
export const READOUT_GAP_PX = 12;

/** Distance a tip keeps from the edge of the area it is placed in (CSS px). */
export const EDGE_MARGIN_PX = 4;

/** The two placement preferences. */
export const PREFER_POINTER = 'pointer';
export const PREFER_OUTSIDE = 'outside';

/**
 * The chart-level tooltip option. Read at build time, like every THEME value,
 * so the print theme applies when a figure is exported. `position` is the
 * chart's placement callback (`tooltipPosition`); without one, ECharts' own
 * follow-the-pointer placement applies.
 */
export function tooltipOption(position = null) {
  return {
    trigger: 'item',
    confine: false,
    appendTo: TOOLTIP_LAYER,
    transitionDuration: 0,
    hideDelay: 0,
    className: TOOLTIP_CLASS,
    ...(position ? { position } : {}),
    backgroundColor: 'rgba(22,27,34,0.95)',
    borderColor: THEME.border,
    textStyle: { color: THEME.text, fontSize: THEME.fontTip },
  };
}

/* ------------------------------------------------------------ geometry -- */

/** A {left, top, right, bottom} rectangle from a DOMRect-like object. */
export function rectOf(r) {
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
}

function intersect(a, b) {
  return {
    left: Math.max(a.left, b.left),
    top: Math.max(a.top, b.top),
    right: Math.min(a.right, b.right),
    bottom: Math.min(a.bottom, b.bottom),
  };
}

function inset(r, by) {
  return { left: r.left + by, top: r.top + by, right: r.right - by, bottom: r.bottom - by };
}

function area(r) {
  return Math.max(0, r.right - r.left) * Math.max(0, r.bottom - r.top);
}

/** `v` limited to [lo, hi]; `lo` wins when the range is empty. */
function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(v, hi));
}

function box(x, y, w, h) {
  return { left: x, top: y, right: x + w, bottom: y + h };
}

function fits(r, within) {
  return r.left >= within.left - 0.5 && r.top >= within.top - 0.5
    && r.right <= within.right + 0.5 && r.bottom <= within.bottom + 0.5;
}

function covers(r, [px, py]) {
  return px >= r.left && px <= r.right && py >= r.top && py <= r.bottom;
}

function distance(r, [px, py]) {
  const dx = Math.max(r.left - px, 0, px - r.right);
  const dy = Math.max(r.top - py, 0, py - r.bottom);
  return Math.hypot(dx, dy);
}

/**
 * The plot area of a grid option as a chart-local {left, top, width, height}.
 * Numbers are pixels and 'n%' strings fractions of the chart; a missing
 * `width`/`height` is what `right`/`bottom` leave.
 */
export function plotBoxFromGrid(grid, width, height) {
  const g = Array.isArray(grid) ? grid[0] : grid;
  const px = (value, total) => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim().endsWith('%')) return (parseFloat(value) / 100) * total;
    return null;
  };
  if (!g) return { left: 0, top: 0, width, height };
  const left = px(g.left, width) ?? 0;
  const top = px(g.top, height) ?? 0;
  const w = px(g.width, width) ?? Math.max(0, width - left - (px(g.right, width) ?? 0));
  const h = px(g.height, height) ?? Math.max(0, height - top - (px(g.bottom, height) ?? 0));
  return { left, top, width: w, height: h };
}

/* ----------------------------------------------------------- placement -- */

/** Beside the pointer within `within`: right, else left, else above or below. */
function besidePointer([px, py], w, h, within) {
  const g = READOUT_GAP_PX;
  const y = clamp(py - 8, within.top, within.bottom - h);
  if (px + g + w <= within.right) return box(px + g, y, w, h);
  if (px - g - w >= within.left) return box(px - g - w, y, w, h);
  const x = clamp(px - w / 2, within.left, within.right - w);
  if (py - g - h >= within.top) return box(x, py - g - h, w, h);
  return box(x, clamp(py + g, within.top, within.bottom - h), w, h);
}

/**
 * The four positions just outside `around`, most room first, horizontal
 * before vertical. Each is aligned with the pointer on its free axis and
 * clamped into `within` there.
 */
function outside(around, [px, py], w, h, within) {
  const g = READOUT_GAP_PX;
  const y = clamp(py - h / 2, within.top, within.bottom - h);
  const x = clamp(px - w / 2, within.left, within.right - w);
  const right = { side: 'right', room: within.right - around.right, rect: box(around.right + g, y, w, h) };
  const left = { side: 'left', room: around.left - within.left, rect: box(around.left - g - w, y, w, h) };
  const below = { side: 'below', room: within.bottom - around.bottom, rect: box(x, around.bottom + g, w, h) };
  const above = { side: 'above', room: around.top - within.top, rect: box(x, around.top - g - h, w, h) };
  const horizontal = right.room >= left.room ? [right, left] : [left, right];
  const vertical = below.room >= above.room ? [below, above] : [above, below];
  return [...horizontal, ...vertical];
}

/**
 * Where a tip of `size` goes, in viewport pixels. Pure: every rectangle is
 * given, as {left, top, right, bottom}.
 *
 * - `pointer`: [x, y] of the pointer.
 * - `size`: the tip's [width, height].
 * - `chart`: the hovered chart's element.
 * - `plot`: its plot area.
 * - `usable`: the visible content area, `.main` within the viewport; the
 *   viewport when omitted.
 * - `viewport`: the window's client area.
 * - `prefer`: `'pointer'` for the plain bin readout, `'outside'` (the
 *   default) for every explanatory tip.
 *
 * Returns {x, y, mode}, where `mode` names the rule that placed the tip:
 * 'pointer', 'outside-chart', 'outside-plot' or 'least-overlap'.
 */
export function placeTooltip({ pointer, size, chart, plot, usable = null, viewport, prefer = PREFER_OUTSIDE }) {
  const [w, h] = size;
  const view = inset(viewport, EDGE_MARGIN_PX);
  const content = usable ? intersect(inset(usable, EDGE_MARGIN_PX), view) : view;
  const result = (rect, mode) => ({ x: rect.left, y: rect.top, mode });
  const clean = (rect, within) => fits(rect, within) && !covers(rect, pointer);

  if (prefer === PREFER_POINTER) {
    for (const within of [content, view]) {
      const near = besidePointer(pointer, w, h, within);
      if (clean(near, within)) return result(near, 'pointer');
    }
  }

  for (const [around, mode] of [[chart, 'outside-chart'], [plot, 'outside-plot']]) {
    for (const within of [content, view]) {
      const found = outside(around, pointer, w, h, within).find((c) => clean(c.rect, within));
      if (found) return result(found.rect, mode);
    }
  }

  // Nothing fits cleanly: the least plot covered, then off the pointer, then nearest.
  const candidates = [
    ...outside(chart, pointer, w, h, view).map((c) => c.rect),
    ...outside(plot, pointer, w, h, view).map((c) => c.rect),
    besidePointer(pointer, w, h, view),
  ].map((r) => {
    const x = clamp(r.left, view.left, view.right - w);
    const y = clamp(r.top, view.top, view.bottom - h);
    return box(x, y, w, h);
  });
  let best = null;
  let bestKey = null;
  for (const r of candidates) {
    const key = [area(intersect(r, plot)), covers(r, pointer) ? 1 : 0, distance(r, pointer)];
    if (!best || key[0] < bestKey[0] - 0.5
        || (Math.abs(key[0] - bestKey[0]) <= 0.5
          && (key[1] < bestKey[1] || (key[1] === bestKey[1] && key[2] < bestKey[2])))) {
      best = r;
      bestKey = key;
    }
  }
  return result(best, 'least-overlap');
}

/* ------------------------------------------------------------- binding -- */

/**
 * Drop zrender's cached client transforms on `chart`'s viewport root, so the
 * next conversion rebuilds them from the page as it is now (see the header:
 * the forward and inverse transforms share one validity check, and a scroll
 * leaves one of them stale).
 */
export function resetPointerTransforms(chart) {
  const root = chart?.getZr?.()?.painter?.getViewportRoot?.();
  const saved = root?.___zrEVENTSAVED;
  if (!saved) return;
  saved.srcCoords = null;
  saved.trans = null;
  saved.invTrans = null;
}

/**
 * The ECharts position callback for `chart`: `(point, params, dom, rect,
 * size) -> [x, y]`, both in chart-local pixels, as ECharts expects.
 *
 * `plotBox()` returns the live plot area in chart-local pixels. It is asked
 * on every call, so a relayout or a resize is followed without re-binding.
 * The tip is placed by `placeTooltip` in viewport pixels and translated back.
 * ECharts converts the result into the layer right after this returns, so the
 * cached transforms are dropped first.
 */
export function tooltipPosition(chart, plotBox, { prefer = PREFER_OUTSIDE } = {}) {
  return (point, _params, _dom, _rect, size) => {
    resetPointerTransforms(chart);
    const host = chart.getDom();
    const c = host.getBoundingClientRect();
    const doc = document.documentElement;
    const viewport = { left: 0, top: 0, right: doc.clientWidth, bottom: doc.clientHeight };
    const main = host.closest('.main');
    const usable = main ? rectOf(main.getBoundingClientRect()) : null;
    const b = plotBox?.() ?? { left: 0, top: 0, width: c.width, height: c.height };
    const plot = { left: c.left + b.left, top: c.top + b.top, right: c.left + b.left + b.width, bottom: c.top + b.top + b.height };
    const pointer = [c.left + (Number(point?.[0]) || 0), c.top + (Number(point?.[1]) || 0)];
    const [w, h] = size?.contentSize ?? [0, 0];
    const { x, y } = placeTooltip({ pointer, size: [w, h], chart: rectOf(c), plot, usable, viewport, prefer });
    return [x - c.left, y - c.top];
  };
}

/**
 * Hide `chart`'s tip when the content area scrolls. On the fixed layer the tip
 * no longer moves with its chart, so a scroll would otherwise leave it
 * floating over whatever slides underneath. The scroll also moves the chart
 * under zrender's cached transforms, which are dropped with it.
 */
export function hideTooltipOnScroll(chart) {
  const main = chart.getDom().closest('.main');
  if (!main) return;
  main.addEventListener('scroll', () => {
    resetPointerTransforms(chart);
    chart.dispatchAction({ type: 'hideTip' });
  }, { passive: true });
}
