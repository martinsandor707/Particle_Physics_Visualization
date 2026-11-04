/* The ECharts marks of the Longitudinal Channels on a depth panel.
 *
 * Pure builders over a spec from `layer_groups.js` `panelGroupSpec`. Every
 * colour and stroke is read from THEME when a builder is called, so a print
 * rebuild (the exporter swaps THEME for the print tokens) draws the print
 * marks and a theme switch repaints from the payload in hand.
 *
 * - **The strip**: 13 segments in a band reserved *above* the plot area
 *   (`stripReserve`, which the panel adds to its grid's top inset), so no
 *   segment ever covers a raster pixel. Each segment is clamped to the plot's
 *   horizontal range at any zoom, the segments alternate two subtle fills, a
 *   1 px edge marks each true end, "Ch m" is written where it fits, and the
 *   hovered group takes the hot fill. Every segment carries its group's
 *   tooltip. The strip stays when the Marks toggle hides the marks: it lies
 *   outside the plot and covers nothing.
 * - **The seams**: one 1 px dashed line across the plot at each stored edge
 *   between two groups, each with its tooltip. Lines, never a wash: a fill
 *   over the raster re-tints every bin beneath it (the slice bracket's rule,
 *   `ProjectionPanel.addDepthSlab`). Left out on a pooled raster, whose bin
 *   edges are the seams already, and when the marks are hidden.
 * - **The spotlight**: the highlighted group's two faces, solid, silent,
 *   never a fill; hidden with the marks.
 * - **The tilted planes** of one shower in Local, on u–w only, dashed, with
 *   their tooltips (`layer_groups.planeLine`).
 *
 * Positions are in the chart's own axis units: millimetres divided by
 * `spec.mmPerUnit` (1 here, 10 for a panel drawn in cm).
 */

import { THEME } from '../scale.js';
import { measureText } from '../textfit.js';
import { planeLine } from '../layer_groups.js';

/** The strip's height and its gap above the plot at screen size (px); print scales them with the type. */
export const STRIP_BAND_PX = 14;
export const STRIP_GAP_PX = 3;

/** Room a segment's label needs beyond its own width (px). */
const LABEL_PAD_PX = 6;

/** The series ids, so the panel can patch the strip and the spotlight on hover without a full redraw. */
export const STRIP_ID = 'layer-groups-strip';
export const SEAMS_ID = 'layer-groups-seams';
export const SPOT_ID = 'layer-groups-spot';
export const PLANES_ID = 'layer-groups-planes';

/** Screen type is 9 px; a band scales with the theme's small type, so print keeps its proportions. */
function typeScale() {
  return Number.isFinite(THEME.fontSmall) && THEME.fontSmall > 0 ? THEME.fontSmall / 9 : 1;
}

/** The band's height and gap in px under the theme in force. */
export function stripGeometry() {
  const s = typeScale();
  return { band: STRIP_BAND_PX * s, gap: STRIP_GAP_PX * s };
}

/** The px a spec reserves above the plot: the strip's band and gap, or a badge's; 0 for none. */
export function stripReserve(spec) {
  if (!spec || !(spec.strip || spec.badge)) return 0;
  const { band, gap } = stripGeometry();
  return band + gap;
}

function textWidth(text, px) {
  const w = measureText(text, px, THEME.fontFamily);
  return Number.isFinite(w) ? w : String(text).length * 0.6 * px;
}

const unit = (spec, value) => value / (spec?.mmPerUnit || 1);

/** A vertical line across the plot at column `x` (axis units). */
function verticalLine(api, params, x, style) {
  const px = api.coord([x, 0])[0];
  const cs = params.coordSys;
  if (!(px >= cs.x - 0.5 && px <= cs.x + cs.width + 0.5)) return null;
  return {
    type: 'polyline',
    shape: { points: [[px, cs.y], [px, cs.y + cs.height]] },
    style: { fill: 'none', ...style },
  };
}

/** The strip: one item per group, in the band above `grid.top`. */
function stripSeries(spec) {
  const { band, gap } = stripGeometry();
  const groups = spec.groups.filter((g) => Number.isFinite(g.lo) && Number.isFinite(g.hi));
  const fontPx = THEME.fontSmall;
  const colours = {
    a: THEME.groupStripFillA, b: THEME.groupStripFillB, hot: THEME.groupStripHot,
    edge: THEME.groupStripEdge, text: THEME.groupStripText,
  };
  const highlight = spec.highlight;
  const font = THEME.fontFamily;
  const lineWidth = THEME.lineAxis;
  return {
    type: 'custom',
    id: STRIP_ID,
    name: 'Longitudinal channels',
    clip: false,
    z: 6,
    data: groups.map((g) => [unit(spec, g.lo), unit(spec, g.hi), g.group]),
    renderItem: (params, api) => {
      const g = groups[params.dataIndex];
      if (!g) return null;
      const cs = params.coordSys;
      const a = api.coord([unit(spec, g.lo), 0])[0];
      const b = api.coord([unit(spec, g.hi), 0])[0];
      const left = Math.min(a, b);
      const right = Math.max(a, b);
      const x0 = Math.max(cs.x, left);
      const x1 = Math.min(cs.x + cs.width, right);
      if (!(x1 - x0 > 0.5)) return null;
      const y = cs.y - gap - band;
      const hot = highlight === g.group;
      const children = [{
        type: 'rect',
        shape: { x: x0, y, width: x1 - x0, height: band },
        style: { fill: hot ? colours.hot : (g.group % 2 ? colours.a : colours.b) },
      }];
      // An edge only at a true end of the group, never where the zoom cuts it.
      for (const [edge, real] of [[left, left >= cs.x - 0.5], [right, right <= cs.x + cs.width + 0.5]]) {
        if (!real) continue;
        children.push({
          type: 'polyline',
          shape: { points: [[edge, y], [edge, y + band]] },
          style: { fill: 'none', stroke: colours.edge, lineWidth },
          silent: true,
        });
      }
      const width = x1 - x0;
      const full = g.label;
      const bare = String(g.group);
      let text = null;
      if (width >= textWidth(full, fontPx) + LABEL_PAD_PX) text = full;
      else if (width >= textWidth(bare, fontPx) + LABEL_PAD_PX) text = bare;
      if (text) {
        children.push({
          type: 'text',
          silent: true,
          style: {
            text, x: (x0 + x1) / 2, y: y + band / 2, align: 'center', verticalAlign: 'middle',
            fill: colours.text, fontSize: fontPx, fontFamily: font, fontWeight: hot ? 'bold' : 'normal',
          },
        });
      }
      // No ECharts hover state: the hovered segment takes groupStripHot through setGroupHighlight,
      // never a lift of it, so the colour under the pointer is the one the contrast pins measure.
      // A custom series reads the switch from the element renderItem returns, not from the series.
      return { type: 'group', children, emphasisDisabled: true };
    },
    tooltip: {
      formatter: (params) => {
        const g = groups[params?.dataIndex] ?? groups.find((x) => x.group === highlight);
        return g ? g.tooltip : '';
      },
    },
  };
}

/** The seams: one dashed line per stored edge between two groups. */
function seamSeries(spec) {
  const seams = spec.seams;
  const style = { stroke: THEME.groupSeam, lineWidth: THEME.lineAxis, lineDash: [4, 3] };
  return {
    type: 'custom',
    id: SEAMS_ID,
    name: 'Longitudinal channel seams',
    clip: true,
    z: 4,
    data: seams.map((s) => [unit(spec, s.at), 0, s.seam]),
    renderItem: (params, api) => {
      const s = seams[params.dataIndex];
      return s ? verticalLine(api, params, unit(spec, s.at), style) : null;
    },
    tooltip: { formatter: (params) => seams[params?.dataIndex]?.tooltip ?? '' },
  };
}

/** The tilted layer planes of one shower in Local (u–w only). */
function planeSeries(spec, rowRange) {
  const lines = spec.lines
    .map((s) => ({ s, seg: planeLine(s.normal, s.at, spec.panelId, rowRange) }))
    .filter((x) => x.seg);
  const style = { stroke: THEME.groupSeam, lineWidth: THEME.lineAxis, lineDash: [4, 3] };
  return {
    type: 'custom',
    id: PLANES_ID,
    name: 'Layer planes',
    clip: true,
    z: 4,
    data: lines.map((x) => [unit(spec, x.seg.from[0]), unit(spec, x.seg.from[1]), x.s.seam]),
    renderItem: (params, api) => {
      const x = lines[params.dataIndex];
      if (!x) return null;
      const from = api.coord([unit(spec, x.seg.from[0]), unit(spec, x.seg.from[1])]);
      const to = api.coord([unit(spec, x.seg.to[0]), unit(spec, x.seg.to[1])]);
      return { type: 'polyline', shape: { points: [from, to] }, style: { fill: 'none', ...style } };
    },
    tooltip: { formatter: (params) => lines[params?.dataIndex]?.s.tooltip ?? '' },
  };
}

/** The spotlight: the highlighted group's two faces, solid and silent. Empty data without one. */
function spotSeries(spec, rowRange, shown) {
  const g = shown && spec.highlight ? spec.groups.find((x) => x.group === spec.highlight) : null;
  const segments = [];
  if (g) {
    if (Number.isFinite(g.lo) && Number.isFinite(g.hi)) {
      for (const at of [g.lo, g.hi]) segments.push({ vertical: unit(spec, at) });
    } else if (Array.isArray(g.faces) && Array.isArray(spec.axis?.normal)) {
      for (const at of g.faces) {
        const seg = planeLine(spec.axis.normal, at, spec.panelId, rowRange);
        if (seg) segments.push({ from: seg.from.map((v) => unit(spec, v)), to: seg.to.map((v) => unit(spec, v)) });
      }
    }
  }
  const style = { stroke: THEME.groupSpot, lineWidth: 1.5 * THEME.lineAxis, lineDash: null };
  return {
    type: 'custom',
    id: SPOT_ID,
    name: 'Longitudinal channel spotlight',
    clip: true,
    silent: true,
    z: 5,
    data: segments.map((s) => (s.vertical !== undefined ? [s.vertical, 0] : s.from)),
    renderItem: (params, api) => {
      const s = segments[params.dataIndex];
      if (!s) return null;
      if (s.vertical !== undefined) return verticalLine(api, params, s.vertical, style);
      return { type: 'polyline', shape: { points: [api.coord(s.from), api.coord(s.to)] }, style: { fill: 'none', ...style } };
    },
  };
}

/**
 * The series of a spec on one depth panel. `col`/`row` are the payload axes,
 * `view` the displayed window and `extent` the full one (mm, `{col, row}`),
 * which bound the tilted lines; `marks` false (the Marks toggle) leaves the
 * seams, the planes and the spotlight out and keeps the strip. The spotlight
 * series is always present (empty without a highlight), so a hover can patch
 * it in place.
 */
export function layerGroupSeries({ spec, col, row, view = null, extent = null, marks = true }) {
  if (!spec || spec.numbering === 'none' || !Array.isArray(spec.groups)) return [];
  if (col && col.name !== 'z') return [];
  const lo = Math.min(row?.lo ?? Infinity, view?.row?.[0] ?? Infinity, extent?.row?.[0] ?? Infinity);
  const hi = Math.max(row?.hi ?? -Infinity, view?.row?.[1] ?? -Infinity, extent?.row?.[1] ?? -Infinity);
  const rowRange = Number.isFinite(lo) && Number.isFinite(hi) ? [lo, hi] : [0, 0];
  const series = [];
  if (spec.strip) series.push(stripSeries(spec));
  if (marks) {
    if (!spec.pooled && spec.seams?.length) series.push(seamSeries(spec));
    if (spec.lines?.length) series.push(planeSeries(spec, rowRange));
  }
  series.push(spotSeries(spec, rowRange, marks));
  return series;
}

/**
 * The muted sentence a spec writes in the band instead of lines (`spec.badge`:
 * the Local ensemble, one shower's v–w), as a graphic over the plot's left
 * edge; `rect` the grid rectangle in px. Null without a badge.
 */
export function localBadge(spec, rect) {
  if (!spec?.badge || !rect) return null;
  const { band, gap } = stripGeometry();
  return {
    type: 'text',
    id: 'layer-groups-badge',
    left: rect.left,
    top: rect.top - gap - band,
    silent: false,
    style: {
      text: spec.badge,
      fill: THEME.muted,
      fontSize: THEME.fontSmall,
      fontFamily: THEME.fontFamily,
      lineHeight: band,
      // Kept to the plot's width: a long sentence on a narrow panel is cut, its full text in the drawer.
      width: Math.max(20, rect.width),
      overflow: 'truncate',
    },
  };
}
