/* The one hover-tooltip configuration every chart uses.
 *
 * ## Why `confine`, and why nothing else
 *
 * The tooltip is not stacked *under* the control sidebar; it is clipped. Its
 * element lives inside the chart container, and `.main` is a scroll container
 * (`overflow-y: auto`, which computes `overflow-x` to `auto` too), so it clips
 * every descendant at its padding box - whose left edge is the sidebar's right
 * edge. When the pointer sits right of a panel's centre ECharts flips the
 * readout left of the cursor, a wide readout crosses that edge, and the part
 * beyond it is cut off where it would overlap the sidebar. Measured in
 * Chromium on the real stylesheet at 1600 x 900: the tip started 41 px left of
 * `.main` and `elementFromPoint` there returned the sidebar.
 *
 * No z-index can escape an ancestor's overflow clip, and ECharts 5.5.1 gives
 * the tooltip no class to style (its z-index and `pointer-events: none` are
 * already set inline), so a stylesheet rule would change nothing. `confine`
 * keeps the tip inside the chart's own box, which always sits right of the
 * sidebar; that is the whole fix. `className` is a styling hook only.
 */

import { THEME } from '../scale.js';

/** Class on every chart tooltip element: a hook for styling, not for stacking. */
export const TOOLTIP_CLASS = 'calo-tooltip';

/** Gap between the pointer and the bin readout, in CSS pixels. */
export const READOUT_GAP_PX = 12;

/**
 * The chart-level tooltip option. Read at build time, like every THEME value,
 * so the print theme applies when a figure is exported.
 */
export function tooltipOption() {
  return {
    trigger: 'item',
    confine: true,
    className: TOOLTIP_CLASS,
    backgroundColor: 'rgba(22,27,34,0.95)',
    borderColor: THEME.border,
    textStyle: { color: THEME.text, fontSize: THEME.fontTip },
  };
}

/**
 * ECharts position callback for the bin readout: `(point, params, dom, rect,
 * size) -> [x, y]` in chart pixels.
 *
 * Right of the pointer when the readout fits, else flipped left of it, and when
 * the chart is narrower than the readout plus the gap on either side, pushed to
 * the far half and moved above or below the pointer so it never covers it.
 * `confine` then clamps the result into the chart box - that clamp, not this
 * function, is what keeps the tip off the sidebar. A literal `[x, y]` array
 * would switch off ECharts' own flip and leave a wide readout sitting on the
 * pointer over most of a panel.
 */
export function readoutPosition(point, _params, _dom, _rect, size) {
  const px = Number(point?.[0]) || 0;
  const py = Number(point?.[1]) || 0;
  const [w, h] = size?.contentSize ?? [0, 0];
  const [vw] = size?.viewSize ?? [Infinity, Infinity];
  const g = READOUT_GAP_PX;

  if (px + g + w <= vw) return [px + g, py - 8];
  if (px - g - w >= 0) return [px - g - w, py - 8];

  const x = px < vw / 2 ? Math.max(0, vw - w) : 0;
  const y = py - g - h >= 0 ? py - g - h : py + g;
  return [x, y];
}
