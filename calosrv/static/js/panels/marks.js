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
 *
 * `casing` ({color, width}, opt-in; absent by default, so every existing
 * chart draws exactly as before) lays a wider, solid stroke under the line: on
 * the light screen a white halo, so an overlay drawn across the deep shower
 * core stays visible there and on the white card alike (`overlayCasing`).
 */
export function customPolyline({
  name, points, color, width, opacity = 1, dash = null, smooth = 0, z = 5, tooltip = null, casing = null,
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
    renderItem: (params, api) => {
      const shape = { points: points.map((p) => api.coord(p)), smooth };
      const line = {
        type: 'polyline',
        shape,
        style: {
          fill: 'none',
          stroke: color,
          lineWidth: width,
          opacity,
          lineDash: dash,
        },
      };
      if (!casing) return line;
      return {
        type: 'group',
        children: [
          { type: 'polyline', shape, silent: true,
            style: { fill: 'none', stroke: casing.color, lineWidth: casing.width, opacity } },
          line,
        ],
      };
    },
    ...(tooltip ? { tooltip: { formatter } } : {}),
  };
}

/**
 * Many capped whiskers as one custom series, one hoverable item per whisker.
 *
 * The physics panels draw an interval at every bin - the Student-t envelope of
 * a profile mean, the χ² interval of σ/μ - and one series per whisker would
 * mean dozens of series per chart. `points` is `[[at, lo, hi, datum], ...]`:
 * a vertical whisker at x = `at` from y = `lo` to `hi`, or with `horizontal` a
 * horizontal one at y = `at` from x = `lo` to `hi`.
 *
 * Reserved for the uncertainty of an aggregate, as `customWhisker` is
 * (CLAUDE.md section 2). Per item, `datum.caps` ([lo, hi] booleans) drops the
 * cap of an end clipped to the window, where `customCaret` marks it instead,
 * and `datum.color` / `datum.opacity` override the series style.
 * `offsetPx` shifts every whisker perpendicular to its shaft, in pixels (right
 * for a vertical whisker, up for a horizontal one), so two showers measured at
 * the same position stay apart and a summary row can sit above a baseline.
 * `tooltip(datum, index)` returns the HTML of one item.
 *
 * `casing` ({color, width}, opt-in; absent by default, so every existing
 * chart draws exactly as before) lays a wider stroke under each whisker: a
 * whisker drawn over a filled bar clears 3:1 against the fill and the card
 * alike when a dark casing frames its light ink (E2, review P-3).
 */
export function customWhiskers({
  name, points, capPx = 4, color, width, opacity = 1, z = 9, tooltip = null,
  horizontal = false, offsetPx = 0, casing = null,
}) {
  const items = points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]) && Number.isFinite(p[2]));
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    // One datum per whisker, so each is its own hover target.
    data: items.map((p, index) => (horizontal ? [p[1], p[0], index] : [p[0], p[1], index])),
    renderItem: (params, api) => {
      const [at, lo, hi, datum = {}] = items[params.dataIndex];
      const shift = (pt) => (horizontal ? [pt[0], pt[1] - offsetPx] : [pt[0] + offsetPx, pt[1]]);
      const a = shift(api.coord(horizontal ? [lo, at] : [at, lo]));
      const b = shift(api.coord(horizontal ? [hi, at] : [at, hi]));
      const caps = datum.caps ?? [true, true];
      // The cap runs perpendicular to the shaft.
      const cap = (pt) => (horizontal
        ? [[pt[0], pt[1] - capPx], [pt[0], pt[1] + capPx]]
        : [[pt[0] - capPx, pt[1]], [pt[0] + capPx, pt[1]]]);
      const ink = {
        type: 'polyline',
        shape: {
          points: [...(caps[0] ? cap(a) : []), a, b, ...(caps[1] ? cap(b) : [])],
        },
        style: {
          fill: 'none',
          stroke: datum.color ?? color,
          lineWidth: width,
          opacity: datum.opacity ?? opacity,
        },
      };
      if (!casing) return ink;
      // The casing first, so the ink sits on it; square ends so it frames the caps too.
      const under = {
        ...ink,
        style: { ...ink.style, stroke: casing.color, lineWidth: casing.width, lineCap: 'square' },
      };
      return { type: 'group', children: [under, ink] };
    },
    ...(tooltip ? { tooltip: { formatter: (p) => tooltip(items[p.dataIndex][3], p.dataIndex) } } : {}),
  };
}

/**
 * Invisible full-height hover targets, one per bin: the readout of a binned
 * chart. `edges` are the n + 1 bin edges on the x axis; each bin's rect spans
 * the whole plot height (`params.coordSys`), so the readout answers wherever
 * the pointer is over the bin, not only on the ink of a thin step line.
 *
 * The fill is transparent but present, which zrender counts as fill when hit
 * testing (see the header). Drawn under every mark (`z` 1), so a mark with a
 * tooltip of its own still wins its hover. `tooltip(binIndex)` returns the
 * readout's HTML; `position` is the panel's readout placement (beside the
 * pointer), absent in print. `y` is any value inside the y axis, carried by
 * each datum so it is valid on a log axis too (zero is not).
 */
export function binHoverSeries({ name, edges, tooltip, position = null, z = 1, y = 0 }) {
  const bins = [];
  for (let i = 0; i + 1 < (edges?.length ?? 0); i += 1) {
    if (Number.isFinite(edges[i]) && Number.isFinite(edges[i + 1])) bins.push(i);
  }
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: false,
    data: bins.map((i) => [0.5 * (edges[i] + edges[i + 1]), y, i]),
    renderItem: (params, api) => {
      const i = bins[params.dataIndex];
      const box = params.coordSys;
      const x0 = api.coord([edges[i], y])[0];
      const x1 = api.coord([edges[i + 1], y])[0];
      return {
        type: 'rect',
        shape: { x: Math.min(x0, x1), y: box.y, width: Math.abs(x1 - x0), height: box.height },
        style: { fill: 'rgba(0,0,0,0)', stroke: 'none' },
      };
    },
    tooltip: {
      formatter: (p) => tooltip(bins[p.dataIndex]),
      ...(position ? { position } : {}),
    },
  };
}

/** A straight segment `from` → `to`; the same options as `customPolyline`. */
export function customLine({ from, to, ...options }) {
  return customPolyline({ ...options, points: [from, to] });
}

/**
 * A capped whisker `from` → `to` (data coordinates), caps `capPx` either side.
 *
 * Reserved for the uncertainty of an aggregate - a 95% interval of a mean -
 * never for sample dispersion (CLAUDE.md section 2). One polyline traced cap
 * → shaft → cap in pixel space, so the caps keep their size at every zoom and
 * `onInk`'s polyline branch covers the whole mark. `caps` drops a cap at an
 * end clipped to the panel window, where a cap would claim the interval ends
 * there; `customCaret` marks that end instead.
 */
export function customWhisker({
  name, from, to, capPx = 4, color, width, opacity = 1, z = 9, tooltip = null,
  caps = [true, true], casing = null,
}) {
  const formatter = typeof tooltip === 'function' ? tooltip : () => tooltip;
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    data: [from],
    renderItem: (params, api) => {
      const a = api.coord(from);
      const b = api.coord(to);
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const length = Math.hypot(dx, dy) || 1;
      // The cap runs perpendicular to the shaft.
      const nx = (-dy / length) * capPx;
      const ny = (dx / length) * capPx;
      const shape = {
        points: [
          ...(caps[0] ? [[a[0] + nx, a[1] + ny], [a[0] - nx, a[1] - ny]] : []), a,
          b, ...(caps[1] ? [[b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny]] : []),
        ],
      };
      const whisker = { type: 'polyline', shape, style: { fill: 'none', stroke: color, lineWidth: width, opacity } };
      // `casing` as `customPolyline`'s: a wider stroke under the whole whisker.
      if (!casing) return whisker;
      return {
        type: 'group',
        children: [
          { type: 'polyline', shape, silent: true,
            style: { fill: 'none', stroke: casing.color, lineWidth: casing.width, opacity } },
          whisker,
        ],
      };
    },
    ...(tooltip ? { tooltip: { formatter } } : {}),
  };
}

/**
 * A caret at `to` pointing away from `from`: the end of a range clipped to the
 * panel window (CLAUDE.md section 2: clip it and say so, with the true value
 * in the tooltip). Its tip sits on the window edge and its body inside, so it
 * is clipped with the plot area like every other mark and stays in the window
 * at any zoom.
 */
export function customCaret({
  name, from, to, sizePx = 6, color, opacity = 1, z = 9, tooltip = null,
}) {
  const formatter = typeof tooltip === 'function' ? tooltip : () => tooltip;
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    data: [to],
    renderItem: (params, api) => {
      const tip = api.coord(to);
      const back = api.coord(from);
      const length = Math.hypot(tip[0] - back[0], tip[1] - back[1]) || 1;
      const ux = (tip[0] - back[0]) / length;
      const uy = (tip[1] - back[1]) / length;
      const base = [tip[0] - ux * sizePx, tip[1] - uy * sizePx];
      const wing = 0.6 * sizePx;
      return {
        type: 'polygon',
        shape: {
          points: [tip, [base[0] - uy * wing, base[1] + ux * wing], [base[0] + uy * wing, base[1] - ux * wing]],
        },
        style: { fill: color, opacity },
      };
    },
    ...(tooltip ? { tooltip: { formatter } } : {}),
  };
}

/**
 * A small cross at `at` (data coordinates), `sizePx` from centre to tip: the
 * reference notebook's ✕ at the shower origin. Drawn in pixel space so it
 * keeps its size at every zoom, as the caps of a whisker do. `casing` as
 * `customPolyline`'s: a wider stroke under both arms.
 */
export function customMarker({
  name, at, color, sizePx = 6, width = 1.5, opacity = 1, z = 12, tooltip = null, casing = null,
}) {
  const formatter = typeof tooltip === 'function' ? tooltip : () => tooltip;
  return {
    type: 'custom',
    name,
    clip: true,
    z,
    silent: !tooltip,
    data: [at],
    renderItem: (params, api) => {
      const [cx, cy] = api.coord(at);
      const s = sizePx;
      const arms = [{ x1: cx - s, y1: cy - s, x2: cx + s, y2: cy + s }, { x1: cx - s, y1: cy + s, x2: cx + s, y2: cy - s }];
      const under = casing
        ? arms.map((shape) => ({ type: 'line', shape, silent: true,
          style: { stroke: casing.color, lineWidth: casing.width, opacity } }))
        : [];
      return {
        type: 'group',
        children: [
          ...under,
          { type: 'line', shape: arms[0], style: { stroke: color, lineWidth: width, opacity } },
          { type: 'line', shape: arms[1], style: { stroke: color, lineWidth: width, opacity } },
        ],
      };
    },
    ...(tooltip ? { tooltip: { formatter } } : {}),
  };
}

/** Index of a semantic axis name in a 3-D mark coordinate. */
const AXIS_INDEX = { x: 0, y: 1, z: 2 };

/**
 * Project the Event Inspector's 3-D marks onto a panel with column axis
 * `colName` and row axis `rowName` (semantic names x | y | z).
 *
 * Pure, so it runs under Node. Returns 2-D marks in (col, row) data
 * coordinates: a `line` with `from`, `to`, `style` and `name`, or a `point`
 * with `at`. Lines of style 'forward' and 'backward' run from the origin a
 * long way (`reach`, a multiple of the window) in their direction; a 'plane'
 * with a `direction` runs both ways; a 'plane' with an `axis` and `at` is a
 * rule across the panel at that coordinate when the axis is one of the
 * panel's. A line whose direction has no component in the panel's plane, or
 * a mark that names other panels, is left out.
 */
export function projectMarks(marks, colName, rowName, panelId, reach) {
  const c = AXIS_INDEX[colName];
  const r = AXIS_INDEX[rowName];
  const out = [];
  if (!Array.isArray(marks) || c === undefined || r === undefined) return out;
  const far = Math.max(1, Number(reach) || 1) * 100;
  for (const mark of marks) {
    if (Array.isArray(mark.panels) && !mark.panels.includes(panelId)) continue;
    if (mark.type === 'point' && Array.isArray(mark.at)) {
      out.push({ type: 'point', at: [mark.at[c], mark.at[r]], name: mark.name, tooltip: mark.tooltip ?? null });
      continue;
    }
    if (mark.type === 'plane' && mark.axis && Number.isFinite(mark.at)) {
      if (mark.axis === colName) {
        out.push({ type: 'line', style: 'plane', name: mark.name, tooltip: mark.tooltip ?? null,
          from: [mark.at, -far], to: [mark.at, far] });
      } else if (mark.axis === rowName) {
        out.push({ type: 'line', style: 'plane', name: mark.name, tooltip: mark.tooltip ?? null,
          from: [-far, mark.at], to: [far, mark.at] });
      }
      continue;
    }
    if (mark.type !== 'line' || !Array.isArray(mark.origin) || !Array.isArray(mark.direction)) continue;
    const o = [mark.origin[c], mark.origin[r]];
    const d = [mark.direction[c], mark.direction[r]];
    const length = Math.hypot(d[0], d[1]);
    if (!(length > 1e-9)) continue;
    const u = [d[0] / length, d[1] / length];
    const tip = [o[0] + far * u[0], o[1] + far * u[1]];
    const tail = mark.style === 'plane' ? [o[0] - far * u[0], o[1] - far * u[1]] : o;
    out.push({ type: 'line', style: mark.style, name: mark.name, tooltip: mark.tooltip ?? null, from: tail, to: tip });
  }
  return out;
}

/**
 * Whether the depth-panel point (z, t) lies inside a band given as stations
 * `[[z, lo, hi], ...]` in increasing z. The band is linear between
 * consecutive stations, so a two-station wedge is the special case and the
 * windowed axis's exact band (nine stations) needs nothing more. Pure, so it
 * runs under Node.
 */
export function insideWedge(points, z, t) {
  if (!Array.isArray(points) || points.length < 2) return false;
  for (let i = 0; i + 1 < points.length; i += 1) {
    const [z0, lo0, hi0] = points[i];
    const [z1, lo1, hi1] = points[i + 1];
    if (!(z1 !== z0)) continue;
    const f = (z - z0) / (z1 - z0);
    if (!(f >= 0 && f <= 1)) continue;
    const lo = lo0 + f * (lo1 - lo0);
    const hi = hi0 + f * (hi1 - hi0);
    return t >= Math.min(lo, hi) && t <= Math.max(lo, hi);
  }
  return false;
}

/**
 * A silent filled band through stations `[[z, lo, hi], ...]`: the lower
 * edge station by station, then the upper edge back. The ensemble axes'
 * two-station wedges and the windowed axis's nine-station band are both
 * drawn with it, so one polygon rule serves every dispersion mark.
 */
export function customBand({ name, points, color, opacity, z = 5, edge = null }) {
  return {
    type: 'custom',
    name,
    silent: true,
    clip: true,
    z,
    data: [points],
    renderItem: (params, api) => {
      const lower = points.map(([depth, lo]) => api.coord([depth, lo]));
      const upper = points.slice().reverse().map(([depth, , hi]) => api.coord([depth, hi]));
      const fill = {
        type: 'polygon',
        shape: { points: [...lower, ...upper] },
        style: { fill: color, opacity, stroke: 'none' },
      };
      if (!edge) return fill;
      // `edge` ({color, width, dash, opacity}, opt-in): the band's extent drawn
      // along its two long sides, never across its ends, so a light wash keeps
      // a readable outline and still reads as an uncapped spread.
      const side = (pts) => ({ type: 'polyline', shape: { points: pts },
        style: { fill: 'none', stroke: edge.color, lineWidth: edge.width, lineDash: edge.dash, opacity: edge.opacity } });
      return { type: 'group', children: [fill, side(lower), side(upper)] };
    },
  };
}
