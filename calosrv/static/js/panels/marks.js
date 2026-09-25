/* Line marks for the spatial panels, drawn as custom series.
 *
 * ## Why not a `line` series
 *
 * Every overlay line on these panels carries a tooltip that names its quantity
 * - the spread bar says it is a dispersion, the ensemble axis states R̄′ and N,
 * a face rule says where the calorimeter ends - because CLAUDE.md section 2
 * makes that naming mandatory for marks that look alike. An ECharts `line`
 * series drawn with `symbol: 'none'` never fires an item tooltip: the
 * formatter was attached, and no reader could ever see it. A `custom` series
 * returning a zrender polyline is an ordinary hit-testable element, so its
 * series tooltip fires on hover.
 *
 * ## The two settings that are load-bearing
 *
 * `clip: true`. A custom series defaults to `clip: false`, and a line from the
 * origin to the back face runs straight out of a zoomed plot area across the
 * axes and the colour bar. Clipped, it stops at the grid exactly as the `line`
 * series did (measured on the vendored 5.5.1 bundle: the SVG carries a
 * `<clipPath>` wrapping the element).
 *
 * `style.fill: 'none'`. Without it zrender gives the path its default black
 * fill, `hasFill()` is true, and the hover test becomes "inside the filled
 * shape" - for a line, just its own 1 px stroke. With no fill the stroke test
 * applies its 5 px `strokeContainThreshold`, a ±2.5 px band that a pointer can
 * actually find. It also keeps a polyline from painting its closing chord.
 *
 * ## Hit area against ink
 *
 * That band, and the whole disc of an open outline marker (its transparent
 * fill still counts as fill for zrender), is wider than what the reader sees.
 * Several of these marks sit on the data by construction: a face rule on the
 * centre of the first or last sampling layer, an anchor ring on a shower core.
 * `onInk` decides whether a hovered mark adds its own text to the panel's bin
 * readout, which answers everywhere (see `ProjectionPanel.attachCellTooltip`).
 */

/** How far past half its stroke width the pointer may be and still be on a mark (px). */
export const INK_TOLERANCE_PX = 1;

/** A fill that paints nothing: absent, 'none', 'transparent' or zero alpha.
 * ECharts lifts 'transparent' to `rgba(0,0,0,0)` in a marker's hover state. */
function isClear(fill) {
  if (fill === null || fill === undefined || fill === 'none' || fill === 'transparent') return true;
  return typeof fill === 'string' && /^rgba\([^)]*,\s*0(\.0*)?\s*\)$/.test(fill.replace(/\s+/g, ''));
}

/** Pixel distance from `p` to the segment a–b. */
function segmentDistance(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length2 = dx * dx + dy * dy;
  const t = length2 > 0
    ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/**
 * Whether the pointer at pixel (px, py) is on the drawn ink of a zrender
 * hit-test target, rather than merely inside its hit area.
 *
 * - A polyline (every `customPolyline`): within half its stroke plus
 *   `INK_TOLERANCE_PX` of one of its segments. A smoothed polyline is measured
 *   against its chords, which on these many-point axes lie within a fraction
 *   of a pixel of the curve.
 * - A scatter symbol with a clear fill (the open anchor and centroid rings):
 *   on its outline, by the same tolerance. The symbol is built in a unit box
 *   centred on its local origin, so the outline is local radius 1 for a circle
 *   and |x| + |y| = 1 for a diamond.
 * - A filled symbol: anywhere inside it, since all of it is ink.
 * - Any other element (labels, the colour bar): always, which keeps whatever
 *   it did before.
 */
export function onInk(target, px, py) {
  if (!target || typeof target.transformCoordToLocal !== 'function') return true;
  const style = target.style || {};
  const half = (Number.isFinite(style.lineWidth) ? style.lineWidth : 1) / 2;
  const reach = half + INK_TOLERANCE_PX;

  if (target.type === 'polyline') {
    const points = target.shape?.points;
    if (!Array.isArray(points) || points.length < 2) return true;
    const p = target.transformCoordToLocal(px, py);
    for (let i = 1; i < points.length; i++) {
      if (segmentDistance(p, points[i - 1], points[i]) <= reach) return true;
    }
    return false;
  }

  // An ECharts symbol reports type 'path'; its shape names the symbol.
  if (typeof target.shape?.symbolType === 'string') {
    if (!isClear(style.fill)) return true;
    const [lx, ly] = target.transformCoordToLocal(px, py);
    // Pixels per local unit, from the element's own transform (it grows on hover).
    const origin = target.transformCoordToGlobal(0, 0);
    const unit = target.transformCoordToGlobal(1, 0);
    const scale = Math.hypot(unit[0] - origin[0], unit[1] - origin[1]);
    const diamond = target.shape?.symbolType === 'diamond';
    const offOutline = diamond
      ? (Math.abs(Math.abs(lx) + Math.abs(ly) - 1) * scale) / Math.SQRT2
      : Math.abs(Math.hypot(lx, ly) - 1) * scale;
    return offOutline <= reach;
  }

  return true;
}

/** The symbol an axis is written with on screen. */
export function symbolOf(axis) {
  return axis.symbol ?? axis.name;
}

/**
 * A polyline through `points` (data coordinates), as one custom series.
 *
 * `dash` takes zrender's names ('dashed', 'dotted') or an array; the dash
 * pattern scales with the width, as the `line` series' did. `tooltip` is the
 * HTML string or a function returning it; without one the series is silent.
 */
export function customPolyline({
  name, points, color, width, opacity = 1, dash = null, smooth = 0, z = 5, tooltip = null,
}) {
  const formatter = typeof tooltip === 'function' ? tooltip : () => tooltip;
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    // One datum, so the series has exactly one element to render and hover;
    // the geometry itself comes from the closure, not from the data.
    data: [points[0]],
    renderItem: (params, api) => ({
      type: 'polyline',
      shape: { points: points.map((p) => api.coord(p)), smooth },
      style: {
        fill: 'none',
        stroke: color,
        lineWidth: width,
        opacity,
        lineDash: dash,
      },
    }),
    ...(tooltip ? { tooltip: { formatter } } : {}),
  };
}

/** A straight segment `from` → `to`; the same options as `customPolyline`. */
export function customLine({ from, to, ...options }) {
  return customPolyline({ ...options, points: [from, to] });
}
