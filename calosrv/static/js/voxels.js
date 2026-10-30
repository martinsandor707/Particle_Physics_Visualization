/* The 3-D voxel views of Page 2: payload decoders and the echarts-gl option,
 * all pure, so Node runs every function here against the recorded payloads.
 *
 * ## The recorded exception these views live under
 *
 * CLAUDE.md section 2 forbids decorative 3-D. The reference notebooks' 3-D
 * event and species displays (C5, C6) are kept under a stated exception: an
 * *orthographic* camera, so no perspective foreshortening distorts a length;
 * a box of equal millimetres on all three axes (1:1:1, from the physical
 * spans, never from a matrix shape); every cube the measured size of what it
 * stands for - a detector cell's 48.27 × 48.60 × 20.5 mm, or the axis-aligned
 * voxel of a sub-deposit splat - placed through the payload's coordinates;
 * flat, unlit shading (`shading: 'color'`), because lighting modulates
 * luminance and on Viridis luminance *is* the value channel; always beside
 * three 2-D projections that carry the same cells quantitatively; and no
 * export, since a rotated 3-D picture is not a publication figure. Nothing in
 * this module may relax any of these.
 *
 * ## Placement: through the payload's coordinates, never index × pitch
 *
 * The transverse x lattice is irregular (twinned cells 4.4 mm apart, pair
 * groups 43.87 / 48.27 mm apart), so a lattice ordinal is never turned into a
 * position by multiplying a pitch. One event's cubes (`/api/event?format=
 * voxels`) come in two regimes:
 *
 * - `cells` (Absolute, per-shower translated): centre =
 *   `geometry.axes.<a>.coords[index] − geometry.origin_mm[a]`, the measured
 *   lattice coordinate of the cell (the payload crops the axis and re-bases
 *   the index, `i0` is informational).
 * - `subdeposit_splat` (Local, D-frame): the cells are tilted or turned and a
 *   bar3D cube cannot tilt, so the server splits each footprint into
 *   sub-deposits binned on an axis-aligned *uniform display grid*. There the
 *   grid's own rule applies, `grid.x0 + (index + 0.5) × grid.pitch_mm`; depth
 *   is `grid.z0 + (index + 0.5) × pitch_z_mm` on a uniform w axis (Local) and
 *   `geometry.axes.z.coords[index]` on the native layers (D-frame, where
 *   `grid.z0` is null).
 *
 * The ensemble cloud (`/api/voxels`) is layer-run encoded: one u16 count per
 * depth layer, then interleaved (x, y) ordinals and one code per voxel. Its
 * transverse grid is uniform and stated in `voxels.layout`; its depth is
 * `grid.z_centres[layer]`, never assumed uniform (`grid.z_uniform` is false
 * on the D-frame's native layers).
 *
 * ## Floating cubes by stacking (the spike, SPIKE-REPORT.md)
 *
 * echarts-gl's bar3D draws columns from z = 0. A cube floating at height b is
 * an invisible *spacer* bar of height b with the cube stacked on it: bar3D
 * stacks by data index within a stack name (`enableDataStack(…, {byIndex:
 * true})`), so the cube at index j sits on the spacer at index j, and the
 * spacer's alpha-0 item is never added to the mesh (`u[3] > 0` in the bundle),
 * so it occludes nothing. Because the stack matches by index, one spacer
 * series carries every cube's own height, so a payload is two series (four
 * with translucent cubes), not two per row as the spike's first sketch had:
 * measured in Chromium on the recorded payloads, every cube's base equals its
 * spacer's top exactly and its height the cube's. Every coordinate is shifted
 * by a round origin at or below the box minimum (`axisTicks`), so spacer
 * heights are never negative and the default `samesign` stacking holds, and
 * the ticks fall on round millimetres once the labels add the origin back.
 *
 * The display axes follow the notebook: x3D is the frame's depth, y3D its x,
 * z3D (vertical) its y.
 *
 * ## Colour: one code-to-colour owner
 *
 * A code is painted through `decode.codeTable`, the same 256-entry table the
 * 2-D rasters use, so a cube and the projection bin beside it take the same
 * colour for the same code: the index arithmetic, the folded PuOr arms of the
 * signed channels (zero at border grey on the linear Shap-CAM ramp, the
 * transparent |v| < 10⁻³ band on the signed log), and the floor taper of the
 * relative ramps. A cube the taper makes translucent is drawn in a series of
 * its own, because echarts-gl turns a whole series' depth writes off once any
 * of its items is translucent; the opaque cubes keep theirs. Code 0 is "no
 * value" on every channel and is not drawn. Species take the qualitative
 * palette the card in force names (`THEME.speciesPalette`: `species` on the
 * dark card, `species_print` on white; `palette.QUALITATIVE`, checked for
 * contrast and colour-vision deficiency), with "other" in grey.
 *
 * The colour legend is the 2-D visualMap of the 2-D panels (`scale.visualMap`)
 * over the GL layer. It targets no series (`seriesIndex: []`): the cubes carry
 * their colours, so the legend can never recolour them.
 */

import { decodeBase64, codeTable, dequantize } from './decode.js';
import {
  THEME, MINUS, visualMap, rampPalette, rampMidLabel, typographic, formatSci, formatInt, formatPercent,
  formatSigned, unitSuffix,
} from './scale.js';
import { QUALITATIVE } from './palette.js';
import { measureText } from './textfit.js';
import { tooltipOption } from './panels/tooltip.js';
import { escapeHtml, mutedLine, wrapTooltip } from './panels/chart_panel.js';

/** World units of the longest box side; every side is S = BOX_UNITS / longest span per mm. */
export const BOX_UNITS = 100;

/** The opening camera: orthographic, never perspective (the recorded exception). */
export const CAMERA = Object.freeze({
  projection: 'orthographic',
  orthographicSize: 160,
  alpha: 25,
  beta: 40,
});

/**
 * The least strip, px, the colour legend reserves on the right of the 3-D
 * plot (grid3D `right`); a legend whose labels are wider takes more
 * (`legendStrip`).
 */
export const LEGEND_RIGHT = 60;

/** Pixels every mark of the opening view keeps from each edge of its viewport. */
export const FIT_PAD = 8;

/**
 * echarts-gl's grid3D tick-label margin (its `axisLabel.margin` default),
 * in world units: the label's anchor sits this far off the axis line, so the
 * gap scales with the zoom while the text itself stays a constant size in
 * pixels. The axis title's gap is `AXIS_NAME_GAP`, also in world units.
 */
export const AXIS_LABEL_MARGIN = 8;

/** echarts-gl's grid3D tick length (`axisTick.length` default), world units. */
export const AXIS_TICK_LENGTH = 3;

/**
 * How close to echarts-gl's 1 : 2 label-alignment threshold an axis's
 * normalised screen slope must be for the fit to hold both of its
 * placements (`viewItems`).
 */
export const ALIGN_BAND = 0.08;

/** The height, px, of one line of axis text in echarts-gl's label atlas: zrender's line height for 10 px type (read from the live labels). */
export const AXIS_TEXT_LINE = 10;

/** echarts-gl adds this to `orthographicSize` (`setFromViewControlModel`, `baseOrthoSize`). */
export const BASE_ORTHO_SIZE = 1;

/** The zoom range the reader may scroll through; the opening fit is clamped to it. */
export const ORTHO_SIZE_RANGE = Object.freeze([20, 600]);

/**
 * The narrowest plot, width over height, that holds a 100-unit cube at the
 * camera's own size, measured in Chromium at the opening angles (636 of
 * 561 px, plus 8 px a side). Only the plot's height before its first model
 * uses it (`glPlotHeight` without a frame); every drawn box is fitted from
 * its own projection (`orthographicFit`).
 */
export const FIT_ASPECT = 1.16;

/** The 3-D plot's height bounds, px: a stacked or wide card is at most 560 px tall, a narrow one no less than 360. */
export const GL_HEIGHT_MIN = 360;
export const GL_HEIGHT_MAX = 560;

/** Degrees to radians. */
const RAD = Math.PI / 180;

/**
 * The screen axes of echarts-gl's orbit camera at `alpha`, `beta` degrees,
 * as world vectors: `u` right, `v` up, `w` towards the viewer.
 *
 * Read from the vendored OrbitControl: `setAlpha` stores θ = α, `setBeta`
 * φ = −β, and `_updateTransform` sets the camera's rotation to
 * `rotateY(−φ) · rotateX(−θ)` (quaternion, right-multiplied), so the
 * camera's local axes are the columns of R_y(β) R_x(−α). Its position
 * direction there, (sin(θ + π/2) cos(φ + π/2), −cos(θ + π/2),
 * sin(θ + π/2) sin(φ + π/2)), is `w`, as it must be. An orthographic
 * camera then maps a world point P to the screen plane (u·P, v·P), at
 * `viewport height / (orthographicSize + 1)` px per world unit on both axes
 * (`_setOrthoSize`: height `size + baseOrthoSize`, width from the viewport's
 * aspect), about the camera's centre, the box's centre at the opening view.
 */
export function cameraAxes(alpha = CAMERA.alpha, beta = CAMERA.beta) {
  const a = alpha * RAD;
  const b = beta * RAD;
  return {
    u: [Math.cos(b), 0, -Math.sin(b)],
    v: [-Math.sin(a) * Math.sin(b), Math.cos(a), -Math.sin(a) * Math.cos(b)],
    w: [Math.cos(a) * Math.sin(b), Math.sin(a), Math.cos(a) * Math.cos(b)],
  };
}

const dot = (p, q) => p[0] * q[0] + p[1] * q[1] + p[2] * q[2];

/** A text's width in px for the fit: measured on a canvas, estimated without one (Node). */
function textWidth(text, fontPx) {
  const w = measureText(text, fontPx, THEME.fontFamily);
  return Number.isFinite(w) ? w : String(text).length * 0.6 * fontPx;
}

/**
 * The opening view's frame: what `openingView` keeps inside the canvas.
 * `box` the grid3D box (`boxSizes`); `ticks` the three tick plans
 * (`axisTicks`, keyed by frame axis z, x, y) and `names` the axis titles
 * (`axisNames`), both optional; `cloud` the drawn cubes' extent on the
 * opening camera's screen plane (`cloudExtent`), or null, when the box's
 * eight corners stand in for them. Returns `{box: {width, height, depth},
 * cloud, x, y, z}`: per echarts-gl axis (x3D the depth, y3D the frame's x,
 * z3D its y), its labelled ticks `{at, w, h}` (`at` the fraction along the
 * axis from its minimum, `w` × `h` the text in px) and its title `{w, h}` or
 * null.
 */
export function glFrame(box, ticks = null, names = null, cloud = null) {
  const axis = (plan, name) => {
    const labels = [];
    if (plan) {
      const lo = plan.min + plan.origin;
      const hi = plan.max + plan.origin;
      const step = plan.labelStep ?? plan.step;
      if (hi > lo && step > 0 && (hi - lo) / step < 200) {
        for (let k = Math.ceil(lo / step - 1e-6); k * step <= hi + step * 1e-6; k += 1) {
          const value = k * step;
          labels.push({
            at: Math.min(1, Math.max(0, (value - lo) / (hi - lo))),
            w: textWidth(typographic(String(Math.round(value))), THEME.fontLabel),
            h: AXIS_TEXT_LINE,
          });
        }
      }
    }
    return { labels, name: name ? { w: textWidth(name, THEME.fontName), h: AXIS_TEXT_LINE } : null };
  };
  return {
    box: { width: box.boxWidth, height: box.boxHeight, depth: box.boxDepth },
    cloud,
    x: axis(ticks?.z, names?.depth),
    y: axis(ticks?.x, names?.x),
    z: axis(ticks?.y, names?.y),
  };
}

/**
 * The drawn cubes' extent on the opening camera's screen plane, in world
 * units about the box centre: `{alpha, beta, left, right, bottom, top}`, each
 * cube's centre projected and widened by its own projected half-size, or
 * null with no cube. The box is the server's window, so its corners are often
 * empty: the fit holds the cubes, the axes and their text, not the corners.
 * `lo` the box minimum in mm (`voxelBounds`), `box` its grid3D sizes.
 */
export function cloudExtent(model, lo, box, camera = CAMERA) {
  const { u, v } = cameraAxes(camera.alpha, camera.beta);
  const S = box.S;
  const W = box.boxWidth;
  const H = box.boxHeight;
  const D = box.boxDepth;
  const hX = (S * model.box.z) / 2;
  const hY = (S * model.box.y) / 2;
  const hZ = (S * model.box.x) / 2;
  const ex = Math.abs(u[0]) * hX + Math.abs(u[1]) * hY + Math.abs(u[2]) * hZ;
  const ey = Math.abs(v[0]) * hX + Math.abs(v[1]) * hY + Math.abs(v[2]) * hZ;
  let left = Infinity;
  let right = -Infinity;
  let bottom = Infinity;
  let top = -Infinity;
  for (let i = 0; i < model.n; i += 1) {
    if (!inCrop(model, i)) continue;
    const p = [S * (model.z[i] - lo.z) - W / 2, S * (model.y[i] - lo.y) - H / 2, D / 2 - S * (model.x[i] - lo.x)];
    const x = dot(u, p);
    const y = dot(v, p);
    if (x - ex < left) left = x - ex;
    if (x + ex > right) right = x + ex;
    if (y - ey < bottom) bottom = y - ey;
    if (y + ey > top) top = y + ey;
  }
  if (!(right >= left)) return null;
  return { alpha: camera.alpha, beta: camera.beta, left, right, bottom, top };
}

/** A sprite's px extent about its anchor for echarts-gl's alignment (`setSpriteAlign`, margin 0). */
function spriteSpan(size, align) {
  if (align === 'left' || align === 'bottom') return [0, size];
  if (align === 'right' || align === 'top') return [-size, 0];
  return [-size / 2, size / 2];
}

/**
 * Every mark of a frame's opening view on the screen plane, as echarts-gl
 * lays it out: `[{x, y, l, r, b, t}]`, the anchor (x, y) in world units
 * about the box centre (x right, y up) and the px it spans left, right,
 * below and above it (negative l, b to the left and below). `aspect` is the
 * viewport's width over its height.
 *
 * The cubes are the frame's cloud (`cloudExtent`), four untexted points at
 * its extremes; a frame without one stands the box's eight corners in for
 * them. Each axis's line and ticks are drawn about a pixel wide, a tick
 * `AXIS_TICK_LENGTH` units long at both ends of the axis and at every round
 * value. Each axis follows the grid3D view
 * (`_updateFaceVisibility`, `_updateAxisLinePosition`,
 * `_updateAxisLabelAlign`): of each pair of opposite faces the one nearer the
 * camera is hidden, the axis lines run along edges of the visible faces, and
 * their labels and title sit `AXIS_LABEL_MARGIN` and `AXIS_NAME_GAP` world
 * units off the line, mirrored with the line where its face flips. An axis
 * whose line runs flatter than 1 : 2 on the normalised screen centres its
 * text above or below its anchor, by the side of the box centre its middle
 * is on; a steeper one sets its text to the left or right, by the same rule.
 * Within `ALIGN_BAND` of that threshold both placements are held.
 *
 * Confirmed in Chromium: the box's corners projected through the chart's own
 * camera (`viewMatrix`, `projectionMatrix`) land where `cameraAxes` puts
 * them to 0.1 px, and the label sprites' measured sizes and alignments are
 * the ones assumed here (design/two-page/fix-z-report.md).
 */
export function viewItems(frame, aspect = 1, camera = CAMERA) {
  const { u, v, w } = cameraAxes(camera.alpha, camera.beta);
  const W = frame.box.width;
  const H = frame.box.height;
  const D = frame.box.depth;
  const items = [];
  const push = (p, l = 0, r = 0, b = 0, t = 0) => items.push({ x: dot(u, p), y: dot(v, p), l, r, b, t });
  const cloud = frame.cloud;
  if (cloud && cloud.alpha === camera.alpha && cloud.beta === camera.beta) {
    for (const x of [cloud.left, cloud.right]) for (const y of [cloud.bottom, cloud.top]) items.push({ x, y, l: 0, r: 0, b: 0, t: 0 });
  } else {
    for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) push([sx * W / 2, sy * H / 2, sz * D / 2]);
  }
  // grid3D's world: x3D along X over ±W/2, z3D (up) along Y over ±H/2, y3D along Z from +D/2 (its minimum) to −D/2.
  const flipX = w[0] < 0; // the +X face is nearer: hidden
  const flipY = w[1] < 0;
  const flipZ = w[2] < 0;
  const m = flipY ? H / 2 : -H / 2;
  const p = flipZ ? -D / 2 : D / 2;
  const axes = {
    x: { at: (f) => [-W / 2 + f * W, m, p], off: [0, 0, flipZ ? -1 : 1] },
    y: { at: (f) => [flipX ? -W / 2 : W / 2, m, D / 2 - f * D], off: [flipX ? -1 : 1, 0, 0] },
    z: { at: (f) => [flipX ? W / 2 : -W / 2, -H / 2 + f * H, p], off: [0, 0, flipZ ? -1 : 1] },
  };
  for (const [dim, geo] of Object.entries(axes)) {
    const spec = frame[dim];
    if (!spec) continue;
    const e0 = geo.at(0);
    const e1 = geo.at(1);
    const mid = geo.at(0.5);
    // The axis line and its ticks, each about a pixel wide. echarts places a
    // tick at both ends of the axis, so the ticks' outer ends span a segment
    // parallel to the line from end to end.
    const tick = (f) => geo.at(f).map((c, k) => c + geo.off[k] * AXIS_TICK_LENGTH);
    for (const p of [e0, e1, tick(0), tick(1)]) push(p, -1, 1, -1, 1);
    const dx = dot(u, e1) - dot(u, e0);
    const dy = dot(v, e1) - dot(v, e0);
    const slope = Math.abs((dy / dx) * aspect);
    const flat = [['center', dot(v, mid) > 0 ? 'bottom' : 'top']];
    const steep = [[dot(u, mid) > 0 ? 'left' : 'right', 'middle']];
    // Near echarts-gl's 1 : 2 threshold a pixel of layout can flip it: hold both placements.
    const aligns = Math.abs(slope - 0.5) < ALIGN_BAND ? [...flat, ...steep] : (slope < 0.5 ? flat : steep);
    const place = (f, gap, text) => {
      const at = geo.at(f).map((c, k) => c + geo.off[k] * gap);
      for (const [h, vAlign] of aligns) {
        const [l, r] = spriteSpan(text.w, h);
        const [b, t] = spriteSpan(text.h, vAlign);
        push(at, l, r, b, t);
      }
    };
    for (const label of spec.labels ?? []) place(label.at, AXIS_LABEL_MARGIN, label);
    if (spec.name) place(0.5, AXIS_NAME_GAP, spec.name);
  }
  return items;
}

/**
 * How far a frame's marks reach from the box centre at `s` px per world
 * unit: `{left, right, top, bottom}` in px.
 */
export function viewExtents(items, s) {
  const e = { left: -Infinity, right: -Infinity, top: -Infinity, bottom: -Infinity };
  for (const it of items) {
    e.left = Math.max(e.left, -(s * it.x + it.l));
    e.right = Math.max(e.right, s * it.x + it.r);
    e.top = Math.max(e.top, s * it.y + it.t);
    e.bottom = Math.max(e.bottom, -(s * it.y + it.b));
  }
  return e;
}

/**
 * The largest px-per-world-unit scale at which the marks span at most
 * `spanW` px across and `spanH` px down (`viewExtents`, left + right and
 * top + bottom). Both spans grow with the scale (a maximum of lines in s),
 * so the bound is found by bisection. 0 when even the text alone does not
 * fit, Infinity when nothing grows.
 */
export function fitScale(items, spanW, spanH) {
  const fits = (s) => {
    const e = viewExtents(items, s);
    return e.left + e.right <= spanW && e.top + e.bottom <= spanH;
  };
  if (!fits(0)) return 0;
  let hi = 1;
  while (fits(hi)) {
    hi *= 2;
    if (hi > 1e6) return Infinity;
  }
  let lo = hi / 2 > 0 && fits(hi / 2) ? hi / 2 : 0;
  for (let k = 0; k < 60; k += 1) {
    const mid = (lo + hi) / 2;
    if (fits(mid)) lo = mid; else hi = mid;
  }
  return lo;
}

/** A frame for a box alone, no text: a 100-unit cube by default. */
export function boxFrame(boxWidth = BOX_UNITS, boxDepth = BOX_UNITS, boxHeight = BOX_UNITS) {
  return glFrame({ boxWidth, boxDepth, boxHeight });
}

/**
 * The opening view of a `width` × `height` px plot whose right `right` px
 * are the legend's: `{size, left, top, width, height}`, the orthographic
 * size and the camera's viewport (grid3D `left`, `top`, `width`, `height`,
 * px). `size` is the smallest at which every corner of the frame's box,
 * every tick label and every axis title (`viewItems`) keeps `FIT_PAD` px
 * from each edge of the area left of the legend.
 *
 * The marks are not symmetric about the box (the titles hang below and to
 * one side), so the box is not centred in the area: its marks are. The
 * viewport is centred on the box's centre, where the camera puts it, keeps
 * the area's aspect (the labels' alignment follows the viewport's aspect)
 * and is scaled up until it covers the whole area, so no mark is clipped;
 * where it reaches past the canvas nothing is drawn. The camera keeps its
 * pivot at the box's centre, so the box turns in place.
 */
export function openingView(width, height, right = 0, frame = null) {
  const w = width - right;
  // No size known: the camera's own size over the area left of the legend (echarts lays it out from `right`).
  const fallback = { size: CAMERA.orthographicSize, left: 0, top: 0, width: null, height: null };
  if (!(w > 2 * FIT_PAD && height > 2 * FIT_PAD)) return fallback;
  const items = viewItems(frame ?? boxFrame(), w / height);
  const s = fitScale(items, w - 2 * FIT_PAD, height - 2 * FIT_PAD);
  if (!(s > 0) || !Number.isFinite(s)) return fallback;
  const e = viewExtents(items, s);
  // The box centre, with the marks centred in the area.
  const cx = FIT_PAD + e.left + (w - 2 * FIT_PAD - e.left - e.right) / 2;
  const cy = FIT_PAD + e.top + (height - 2 * FIT_PAD - e.top - e.bottom) / 2;
  const k = Math.max((2 * Math.max(cx, w - cx)) / w, (2 * Math.max(cy, height - cy)) / height);
  const vw = k * w;
  const vh = k * height;
  const round = (x) => Math.round(x * 10) / 10;
  const size = Math.ceil(((vh / s) - BASE_ORTHO_SIZE) * 10) / 10;
  return {
    size: Math.max(ORTHO_SIZE_RANGE[0], Math.min(ORTHO_SIZE_RANGE[1], size)),
    left: round(cx - vw / 2),
    top: round(cy - vh / 2),
    width: round(vw),
    height: round(vh),
  };
}

/** The opening orthographic size alone (`openingView`). */
export function orthographicFit(width, height, right = 0, frame = null) {
  return openingView(width, height, right, frame).size;
}

/**
 * The 3-D plot's height for a plot `width` px wide, `right` px of it the
 * legend's: with a `frame`, the height the box's opening view needs once its
 * marks fill the width left of the legend (`viewExtents` at the
 * width-limited scale, plus `FIT_PAD` above and below), within
 * [360, 560] px. A flat or wide box then takes a lower card, with no empty
 * band above and below; a tall one is 560 px and fitted to that height.
 * Without a frame (before the first model), `(width − right) / FIT_ASPECT`,
 * the cube's. It depends on the box, the width and the opening angles only,
 * never on the reader's rotation, so the card does not move while it turns.
 * Set by voxel_views.js on the plot element, never through CSS, so the
 * layout snaps with no transition.
 */
export function glPlotHeight(width, right = LEGEND_RIGHT, frame = null) {
  if (!(width > 0)) return GL_HEIGHT_MAX;
  const clamp = (h) => Math.max(GL_HEIGHT_MIN, Math.min(GL_HEIGHT_MAX, h));
  const w = width - right;
  if (!frame || !(w > 2 * FIT_PAD)) return clamp(Math.round(w / FIT_ASPECT));
  let height = GL_HEIGHT_MAX;
  // The labels' alignment follows the viewport's aspect, so settle it in a few passes.
  for (let pass = 0; pass < 4; pass += 1) {
    const items = viewItems(frame, w / height);
    const s = fitScale(items, w - 2 * FIT_PAD, Infinity);
    if (!(s > 0) || !Number.isFinite(s)) return GL_HEIGHT_MAX;
    const e = viewExtents(items, s);
    const next = clamp(Math.ceil(e.top + e.bottom + 2 * FIT_PAD));
    if (next === height) break;
    height = next;
  }
  return height;
}

/**
 * The px the colour legend takes from the right of the 3-D plot: the
 * vertical visualMap (`scale.visualMap`: inset `right`, as wide as its bar
 * or its widest label line) and a diverging ramp's zero label left of its
 * bar (`scale.rampMidLabel`), plus `FIT_PAD`; at least `LEGEND_RIGHT`, and
 * 0 with no legend.
 */
export function legendStrip(legend, mid = null) {
  if (!legend) return 0;
  const lines = (Array.isArray(legend.text) ? legend.text : []).flatMap((t) => String(t).split('\n'));
  const component = Math.max(legend.itemWidth ?? 0, ...lines.map((line) => textWidth(line, THEME.fontSmall)));
  let strip = (legend.right ?? 0) + component;
  if (mid?.style?.text && Number.isFinite(mid.right)) strip = Math.max(strip, mid.right + textWidth(mid.style.text, THEME.fontSmall));
  return Math.max(LEGEND_RIGHT, Math.ceil(strip + FIT_PAD));
}

/**
 * A model's opening fit before its option is built: `{frame, right}`, the
 * frame `orthographicFit` and `glPlotHeight` keep inside the canvas and the
 * legend's strip. voxel_views.js sizes the plot from it, then builds the
 * option at that size.
 */
export function voxelFit(model, palette = 'viridis') {
  const { lo, hi, span } = voxelBounds(model);
  const box = boxSizes(span);
  const ticks = {
    z: axisTicks(lo.z, hi.z, box.boxWidth),
    x: axisTicks(lo.x, hi.x, box.boxDepth),
    y: axisTicks(lo.y, hi.y, box.boxHeight),
  };
  const legend = voxelLegend(model, palette);
  return {
    frame: glFrame(box, ticks, model.symbols ? axisNames(model.symbols) : null, cloudExtent(model, lo, box)),
    right: legendStrip(legend, legend ? rampMidLabel(model.scale) : null),
  };
}

/** echarts-gl draws a series without depth writes once an item's alpha is below this. */
export const OPAQUE_ALPHA = 0.99;

/** Most primary-tagged cubes that get a halo; the rest are counted in the drawer. */
export const HALO_LIMIT = 12;

/** The halo's outward pad, so its lines never z-fight the cube's faces. */
export const HALO_PAD = 1.03;

/** A cube's 12 edges as one 16-point polyline over its 8 corners. */
export const WIREFRAME_PATH = Object.freeze([0, 1, 2, 3, 0, 4, 5, 1, 5, 6, 2, 6, 7, 3, 7, 4]);

/** The server's species codes (query/voxel_event.py SPECIES_ORDER + other), as a reader writes them. */
export const SPECIES_LABELS = Object.freeze({
  'e-': 'e⁻', 'e+': 'e⁺', gamma: 'γ', neutron: 'n', proton: 'p', 'pi+': 'π⁺', 'pi-': 'π⁻', other: 'other',
});

/** The default flag bits, as every voxel payload states them (`cubes.flag_bits`). */
const FLAG_BITS = Object.freeze({ shower: [0, 1], primary: 2, below_floor: 3 });

/* ------------------------------------------------------------ decoding -- */

/**
 * A base64 array of ordinals: 'u8', or 'u16le' (two bytes per value, little
 * endian) once an index passes 255.
 */
export function decodeOrdinals(b64, dtype = 'u8') {
  const bytes = decodeBase64(String(b64 ?? ''));
  if (dtype === 'u8') return bytes;
  if (dtype === 'u16le') {
    if (bytes.length % 2) throw new Error('A u16le voxel array has an odd byte count.');
    const out = new Uint16Array(bytes.length / 2);
    for (let i = 0; i < out.length; i += 1) out[i] = bytes[2 * i] | (bytes[2 * i + 1] << 8);
    return out;
  }
  throw new Error(`Unknown voxel array type ${dtype}.`);
}

function checkLength(array, n, what) {
  if (array.length !== n) throw new Error(`The voxel payload's ${what} holds ${array.length} values for ${n} cubes.`);
}

/** A measured coordinate by ordinal; an ordinal off the shipped axis is a malformed payload. */
function coordAt(coords, index, axis) {
  const value = coords?.[index];
  if (!Number.isFinite(value)) throw new Error(`Cube ordinal ${index} lies off the shipped ${axis} axis.`);
  return value;
}

/** The exact values of the brightest cubes, by payload index. */
function topkMap(entries) {
  const map = new Map();
  for (const entry of entries ?? []) if (Number.isInteger(entry?.i)) map.set(entry.i, entry);
  return map;
}

/**
 * One event's cubes, decoded and placed in millimetres of its frame.
 *
 * Returns `{kind: 'event', frame, regime, channel, n, x, y, z, box, code,
 * flags, shower, primary, below, window, scale, symbols, topk, ...}`, the
 * arrays in payload order (ascending energy: the notebook's draw order, the
 * brightest cubes last). `box` is the cube size `{x, y, z}` in mm and
 * `window` the server's window `{x, y, z: [lo, hi]}`: one half-width per axis
 * by default (`window.mode` 'per_axis'), the spans then unequal and the box
 * still 1:1:1 (`boxSizes`); one for all three under 'shared'.
 */
export function decodeEventVoxels(payload) {
  const vox = payload?.voxels;
  const cubes = vox?.cubes;
  if (!cubes || !vox.geometry) throw new Error('Not an event voxel payload.');
  const n = cubes.n;
  const dtype = cubes.dtype ?? {};
  const ix = decodeOrdinals(cubes.ix, dtype.ix ?? 'u8');
  const iy = decodeOrdinals(cubes.iy, dtype.iy ?? 'u8');
  const iz = decodeOrdinals(cubes.iz, dtype.iz ?? 'u8');
  const code = decodeOrdinals(cubes.code, 'u8');
  const flags = decodeOrdinals(cubes.flags, 'u8');
  for (const [array, what] of [[ix, 'ix'], [iy, 'iy'], [iz, 'iz'], [code, 'code'], [flags, 'flags']]) {
    checkLength(array, n, what);
  }

  const geometry = vox.geometry;
  const [bx, by, bz] = geometry.cube_mm;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  const z = new Float64Array(n);
  if (vox.regime === 'cells') {
    const axes = geometry.axes;
    const origin = geometry.origin_mm ?? [0, 0, 0];
    for (let i = 0; i < n; i += 1) {
      x[i] = coordAt(axes.x.coords, ix[i], 'x') - origin[0];
      y[i] = coordAt(axes.y.coords, iy[i], 'y') - origin[1];
      z[i] = coordAt(axes.z.coords, iz[i], 'z') - origin[2];
    }
  } else if (vox.regime === 'subdeposit_splat') {
    const grid = geometry.grid;
    const uniformZ = grid.z_axis === 'uniform';
    if (!uniformZ && grid.z_axis !== 'native_layers') throw new Error(`Unknown splat depth axis ${grid.z_axis}.`);
    for (let i = 0; i < n; i += 1) {
      x[i] = grid.x0 + (ix[i] + 0.5) * grid.pitch_mm;
      y[i] = grid.y0 + (iy[i] + 0.5) * grid.pitch_mm;
      z[i] = uniformZ
        ? grid.z0 + (iz[i] + 0.5) * grid.pitch_z_mm
        : coordAt(geometry.axes.z.coords, iz[i], 'z');
    }
  } else {
    throw new Error(`Unknown voxel regime ${vox.regime}.`);
  }

  const bits = cubes.flag_bits ?? FLAG_BITS;
  const shower = new Uint8Array(n);
  const primary = new Uint8Array(n);
  const below = new Uint8Array(n);
  const [s0, s1] = bits.shower ?? FLAG_BITS.shower;
  for (let i = 0; i < n; i += 1) {
    shower[i] = ((flags[i] >> s0) & 1) | (((flags[i] >> s1) & 1) << 1);
    primary[i] = (flags[i] >> bits.primary) & 1;
    below[i] = (flags[i] >> bits.below_floor) & 1;
  }

  const species = vox.species ? decodeSpecies(vox.species, n) : null;
  return {
    kind: 'event',
    frame: vox.frame,
    regime: vox.regime,
    channel: vox.channel,
    network: vox.model ?? null,
    n,
    x, y, z,
    ix, iy, iz,
    box: { x: bx, y: by, z: bz },
    code, flags, shower, primary, below,
    window: payload.window?.axes ?? null,
    scale: vox.scale,
    // The ramp's first code: 1 on every event channel (no transparent floor code).
    codes: { empty: 0, min: vox.scale?.min_code ?? 1, max: 255, below: null },
    symbols: vox.symbols ?? { x: 'x', y: 'y', z: 'z' },
    topk: topkMap(vox.topk),
    topkQuantity: vox.topk_quantity ?? null,
    topkUnit: vox.topk_unit ?? null,
    showerCodes: cubes.shower_codes ?? [],
    species,
    nShowers: (payload.event?.showers ?? []).length || 1,
  };
}

/** The species block's per-cube detail: parent, daughters, purity (u8 arrays; 255 = none). */
function decodeSpecies(block, n) {
  const optional = (b64) => {
    if (typeof b64 !== 'string') return null;
    const values = decodeOrdinals(b64, 'u8');
    checkLength(values, n, 'species detail');
    return values;
  };
  return {
    legend: block.legend ?? [],
    parents: block.parents ?? [],
    daughters: block.daughters ?? [],
    parent: optional(block.parent),
    nDaughters: optional(block.n_daughters),
    daughterMode: optional(block.daughter_mode),
    purity: optional(block.purity),
    none: block.none_code ?? 255,
  };
}

/**
 * The ensemble cloud, decoded from its layer runs and placed in millimetres.
 *
 * Voxel i of layer L sits at `x_centre0 + voxel_mm[0] · xy[2i]`, `y_centre0 +
 * voxel_mm[1] · xy[2i + 1]` (the uniform display grid's stated layout) and
 * `z_centres[L]`. Returns `{kind: 'ensemble', frame, n, x, y, z, layer, box,
 * code, extent, scale, symbols, topk, ...}`.
 */
export function decodeEnsembleVoxels(payload) {
  const vox = payload?.voxels;
  const grid = payload?.grid;
  if (!vox || !grid) throw new Error('Not an ensemble voxel payload.');
  if (vox.encoding !== 'layer-run-u8') throw new Error(`Unknown voxel encoding ${vox.encoding}.`);
  const layers = grid.n[2];
  const counts = decodeOrdinals(vox.layer_counts, vox.dtype?.layer_counts ?? 'u16le');
  if (counts.length !== layers) throw new Error(`${counts.length} layer counts for ${layers} depth layers.`);
  if ((grid.z_centres ?? []).length !== layers) throw new Error('The grid states a depth centre per layer.');
  const n = vox.n;
  let total = 0;
  for (const c of counts) total += c;
  if (total !== n) throw new Error(`The layer counts sum to ${total}, not to the ${n} voxels shipped.`);
  const xy = decodeOrdinals(vox.xy, vox.dtype?.xy ?? 'u8');
  const code = decodeOrdinals(vox.code, 'u8');
  checkLength(xy, 2 * n, 'xy pairs');
  checkLength(code, n, 'code');

  const [vx, vy, vz] = grid.voxel_mm;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  const z = new Float64Array(n);
  const layer = new Uint16Array(n);
  let i = 0;
  for (let L = 0; L < layers; L += 1) {
    for (let k = 0; k < counts[L]; k += 1, i += 1) {
      x[i] = grid.x_centre0 + vx * xy[2 * i];
      y[i] = grid.y_centre0 + vy * xy[2 * i + 1];
      z[i] = grid.z_centres[L];
      layer[i] = L;
    }
  }
  const scale = payload.scale ?? {};
  const frame = payload.frame ?? {};
  return {
    kind: 'ensemble',
    frame: frame.kind ?? payload.meta?.frame ?? null,
    channel: payload.meta?.channel ?? 'density',
    n,
    x, y, z, layer,
    counts,
    box: { x: vx, y: vy, z: vz },
    code,
    extent: grid.extent_mm,
    zUniform: grid.z_uniform === true,
    scale,
    // Code 1 (below the floor) is never shipped; 0 is empty; the ramp is 2..255.
    codes: { empty: 0, min: vox.min_code ?? 2, max: 255, below: 1, split: scale.split_code ?? null },
    symbols: frame.symbols ?? { x: 'x', y: 'y', z: 'z' },
    topk: topkMap(payload.topk),
    // What a voxel's value is read against: ρ_ref for density, cam_ref for attention.
    ref: scale.ref ?? scale.rho_ref ?? payload.rho?.rho_ref ?? null,
    refName: scale.ref_name ?? 'rho_ref',
    provisional: Boolean(frame.provisional || payload.rho?.provisional),
    nLabel: frame.n_label ?? null,
  };
}

/** Per-layer counts of a decoded cloud (the layer runs, recounted from the placed voxels). */
export function layerCounts(model) {
  const out = new Array(model.counts?.length ?? 0).fill(0);
  for (let i = 0; i < model.n; i += 1) out[model.layer[i]] += 1;
  return out;
}

/* -------------------------------------------------------------- colour -- */

/**
 * The colours of a qualitative palette as rgb triples, the last one being the
 * "other" slot.
 */
function qualitativeRgb(name) {
  const hexes = QUALITATIVE[name] ?? QUALITATIVE.species;
  return hexes.map((hex) => [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16)));
}

/**
 * The 256-entry RGBA table one model's codes are painted through.
 *
 * Continuous channels go through `decode.codeTable` (see the header); the
 * species channel indexes the qualitative palette by species code, with every
 * code past the named ones taking the palette's last ("other") colour.
 * `fadeDecades` is the floor taper of the relative ramps (THEME's on screen);
 * `qualitative` the species palette, the card's (THEME's) when not given.
 */
export function voxelCodeTable(model, palette = 'viridis', {
  fadeDecades = THEME.floorFadeDecades, qualitative = THEME.speciesPalette,
} = {}) {
  if (model.scale?.scale === 'categorical') {
    const colours = qualitativeRgb(qualitative);
    const otherCode = model.scale.other_code ?? 7;
    const table = new Uint8ClampedArray(256 * 4);
    for (let code = 0; code < 256; code += 1) {
      const rgb = code < otherCode && code < colours.length - 1 ? colours[code] : colours[colours.length - 1];
      table.set([...rgb, 255], code * 4);
    }
    return table;
  }
  const c = model.codes;
  return codeTable({
    scale: model.scale,
    empty_code: c.empty,
    min_code: c.min,
    max_code: c.max,
    ...(Number.isInteger(c.below) ? { below_code: c.below } : {}),
    ...(Number.isInteger(c.split) ? { split_code: c.split } : {}),
  }, palette, fadeDecades, { legible: true, signed: true });
}

/** Each cube's RGBA, from the model's code table. */
export function cubeColours(model, palette = 'viridis', options = {}) {
  const table = voxelCodeTable(model, palette, options);
  const rgba = new Uint8ClampedArray(model.n * 4);
  for (let i = 0; i < model.n; i += 1) {
    const t = model.code[i] * 4;
    rgba.set(table.subarray(t, t + 4), i * 4);
  }
  return rgba;
}

/**
 * The value a cube's code encodes, in the scale's units (null for no value):
 * GeV/mm³ on the event's energy ramp, the attention or attribution on a
 * linear one, the ratio to the reference (signed on Shap-CAM) on a relative
 * ensemble ramp. The quantisation step is about 5.6% on the six-decade event
 * ramp; the brightest cubes carry exact values in `topk`.
 */
export function codeValue(model, code) {
  if (model.scale?.scale === 'categorical') return null;
  const c = model.codes;
  if (code === c.empty || code === c.below || code < c.min) return null;
  return dequantize(code, model.scale, {
    min_code: c.min, max_code: c.max, ...(Number.isInteger(c.split) ? { split_code: c.split } : {}),
  });
}

/* ------------------------------------------------------------- legends -- */

/** A species code as the legend and tooltips write it. */
export function speciesLabel(name) {
  return SPECIES_LABELS[name] ?? String(name ?? '—');
}

/**
 * The species legend: one row per species the event holds, in code order,
 * with the server's counts (cells, energy fraction, primary-tagged cells), the
 * cubes of that species drawn in this payload (recounted from the decoded
 * codes, so the legend never states a count the picture does not hold), its
 * swatch and whether it is hidden by an isolate toggle.
 */
export function speciesLegend(model, hidden = new Set(), qualitative = THEME.speciesPalette) {
  if (!model?.species) return [];
  const colours = qualitativeRgb(qualitative);
  const other = model.scale?.other_code ?? 7;
  const drawn = new Map();
  for (let i = 0; i < model.n; i += 1) drawn.set(model.code[i], (drawn.get(model.code[i]) ?? 0) + 1);
  return model.species.legend.map((entry) => {
    const rgb = entry.code < other && entry.code < colours.length - 1 ? colours[entry.code] : colours[colours.length - 1];
    return {
      code: entry.code,
      name: entry.name,
      label: speciesLabel(entry.name),
      colour: `rgb(${rgb.join(',')})`,
      cells: entry.cells,
      cubes: entry.cubes,
      drawn: drawn.get(entry.code) ?? 0,
      energyGev: entry.energy_gev,
      energyFraction: entry.energy_fraction,
      primaryCells: entry.primary_cells,
      members: entry.members ?? null,
      hidden: hidden.has(entry.code),
    };
  });
}

/** The label a provisional ramp carries on its top line (CLAUDE.md: provisional on the scale itself). */
export const PROVISIONAL_TAG = 'provisional';

/**
 * The colour legend of a model, or null: a categorical channel has the HTML
 * species legend instead, and a degenerate ramp (every cube one density) has
 * no range to show - the card says so in words.
 */
export function voxelLegend(model, palette = 'viridis') {
  const scale = model.scale;
  if (!scale || scale.scale === 'categorical' || scale.degenerate) return null;
  // The ramp's unit is written by scale.js `unitSuffix` (GeV/mm^3 as GeV/mm³), as on every 2-D ramp.
  const legend = visualMap(scale, rampPalette(scale, palette), { seriesIndex: [], signed: true });
  const top = referenceTopLabel(model);
  if (top && Array.isArray(legend.text)) {
    // The relative ramp's top is the reference itself: "1 = ρ_ref", not "10⁰·⁰ a.u." (P-25).
    const lines = String(legend.text[0]).split('\n');
    lines[lines.length - 1] = top;
    legend.text = [lines.join('\n'), ...legend.text.slice(1)];
  }
  if (model.provisional && Array.isArray(legend.text)) {
    legend.text = [`${PROVISIONAL_TAG}\n${legend.text[0]}`, ...legend.text.slice(1)];
  }
  return legend;
}

/**
 * The top label of an ensemble's relative ramp, written against its
 * reference: "1 = ρ_ref" (or cam_ref) where the ramp tops out at the
 * reference, "3.2 × ρ_ref" where the selection is brighter. Null for every
 * other ramp (an event's physical units, a signed log, a linear ramp).
 */
export function referenceTopLabel(model) {
  const scale = model?.scale;
  if (model?.kind !== 'ensemble' || scale?.unit !== 'a.u.' || scale.scale !== 'log10') return null;
  if (!Number.isFinite(scale.vmax)) return null;
  const ref = model.refName === 'cam_ref' ? 'cam_ref' : 'ρ_ref';
  if (Math.abs(scale.vmax) < 0.05) return `1 = ${ref}`;
  const factor = 10 ** scale.vmax;
  return `${typographic(factor >= 10 ? factor.toFixed(0) : factor.toPrecision(2))} × ${ref}`;
}

/* ------------------------------------------------------------ geometry -- */

/**
 * The window of the 2-D projections paired with the cloud, per axis of the
 * cloud's frame, `{x: [lo, hi], y, z}` in mm, or null when the response does
 * not give all three.
 *
 * Each projection crops to its own window: in a co-registered frame
 * symmetric about the origin on the transverse axes, at the energy-weighted
 * 0.1st-99.9th percentile with the floors and 20 mm snapping of CLAUDE.md's
 * recorded exceptions (calosrv/query/window.py `symmetric_axis`). The entry
 * panel (xy) and the two depth panels each window a transverse axis, so an
 * axis takes the widest of the panels that show it: every bin a projection
 * draws lies inside the 3-D box, and the box is never narrower than any
 * projection on that axis. Depth is the depth panels' own range.
 */
export function pairedWindow(projections) {
  const panels = projections?.panels;
  if (!panels) return null;
  const out = {};
  for (const id of ['xy', 'yz', 'xz']) {
    for (const side of ['col', 'row']) {
      const axis = panels[id]?.axes?.[side];
      if (!axis || !['x', 'y', 'z'].includes(axis.name) || !Number.isFinite(axis.lo) || !Number.isFinite(axis.hi)) continue;
      const seen = out[axis.name];
      out[axis.name] = seen ? [Math.min(seen[0], axis.lo), Math.max(seen[1], axis.hi)] : [axis.lo, axis.hi];
    }
  }
  return ['x', 'y', 'z'].every((a) => out[a] && out[a][1] > out[a][0]) ? out : null;
}

/** The magnitude a cube's colour code stands for, for the cropped share (null without one). */
function codeMagnitude(model, i) {
  const value = codeValue(model, model.code[i]);
  return Number.isFinite(value) ? Math.abs(value) : null;
}

/**
 * The ensemble cloud cropped to `window` (`pairedWindow`): a copy of the model
 * whose `crop` says which cubes lie inside - a cube belongs where its centre
 * is, as a bin does - and what the crop leaves out: the number of cubes and
 * their share of the drawn cloud's summed value, read back from the colour
 * codes (every voxel has the same volume, so for the density channel it is
 * the energy share, to the codes' quantisation). The box is then the window,
 * widened to whole cubes; the grid extent stays on the model for the drawer.
 * `window` null: no crop (the projections did not load), and `crop.window`
 * is null so the drawer says the box is the whole grid.
 */
export function cropToWindow(model, window) {
  if (!model || model.kind !== 'ensemble') return model;
  const inside = new Uint8Array(model.n);
  let nInside = 0;
  let sumIn = 0;
  let sumOut = 0;
  for (let i = 0; i < model.n; i += 1) {
    const keep = !window || ['x', 'y', 'z'].every((a) => model[a][i] >= window[a][0] && model[a][i] <= window[a][1]);
    inside[i] = keep ? 1 : 0;
    const m = codeMagnitude(model, i);
    if (keep) {
      nInside += 1;
      if (m !== null) sumIn += m;
    } else if (m !== null) {
      sumOut += m;
    }
  }
  const total = sumIn + sumOut;
  return {
    ...model,
    crop: {
      window: window ?? null,
      extent: model.extent,
      inside,
      nInside,
      nOutside: model.n - nInside,
      shareOutside: total > 0 ? sumOut / total : 0,
    },
  };
}

/** Whether cube `i` is drawn by the model's crop (every cube without one). */
function inCrop(model, i) {
  return !model.crop || model.crop.inside[i] === 1;
}

/**
 * The box the cubes are drawn in, per axis `[lo, hi]` in mm: the server's
 * window (event), or the paired projections' window where the cloud was
 * cropped to it (`cropToWindow`), else the grid extent (ensemble), widened to
 * hold every whole cube drawn, so a shifted coordinate is never negative.
 */
export function voxelBounds(model) {
  const base = model.kind === 'ensemble' ? (model.crop?.window ?? model.extent) : model.window;
  const lo = {};
  const hi = {};
  for (const a of ['x', 'y', 'z']) {
    lo[a] = Number.isFinite(base?.[a]?.[0]) ? base[a][0] : Infinity;
    hi[a] = Number.isFinite(base?.[a]?.[1]) ? base[a][1] : -Infinity;
  }
  for (let i = 0; i < model.n; i += 1) {
    if (!inCrop(model, i)) continue;
    for (const a of ['x', 'y', 'z']) {
      const half = model.box[a] / 2;
      const c = model[a][i];
      if (c - half < lo[a]) lo[a] = c - half;
      if (c + half > hi[a]) hi[a] = c + half;
    }
  }
  for (const a of ['x', 'y', 'z']) {
    if (!(hi[a] > lo[a])) {
      // Nothing to bound: one box of the cube's own size about zero.
      lo[a] = -model.box[a] / 2;
      hi[a] = model.box[a] / 2;
    }
  }
  return { lo, hi, span: { x: hi.x - lo.x, y: hi.y - lo.y, z: hi.z - lo.z } };
}

/**
 * The grid3D box of a span: one world-units-per-mm factor S on every axis,
 * so a millimetre is the same length along each (1:1:1). x3D is the frame's
 * depth, y3D its x, z3D its y.
 */
export function boxSizes(span) {
  const S = BOX_UNITS / Math.max(span.x, span.y, span.z);
  return { S, boxWidth: S * span.z, boxDepth: S * span.x, boxHeight: S * span.y };
}

/**
 * One cube's 12 edges as the 16-point polyline `WIREFRAME_PATH`, in shifted
 * display coordinates [depth, x, y] (millimetres minus `lo`, the axes' round
 * origins), padded outward by `pad`.
 */
export function cubeWireframe(model, i, lo, pad = HALO_PAD) {
  const h = { x: (model.box.x * pad) / 2, y: (model.box.y * pad) / 2, z: (model.box.z * pad) / 2 };
  const cx = model.x[i] - lo.x;
  const cy = model.y[i] - lo.y;
  const cz = model.z[i] - lo.z;
  const corners = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]]
    .map(([sz, sx, sy]) => [cz + sz * h.z, cx + sx * h.x, cy + sy * h.y]);
  return WIREFRAME_PATH.map((k) => corners[k]);
}

/* ------------------------------------------------------------- tooltip -- */

const fixed = (value, digits = 1) => typographic(Number(value).toFixed(digits));

/** The unit a model's values are written in, for a reader. */
function valueUnit(model) {
  if (model.kind === 'event' && model.scale?.unit === 'GeV/mm^3') return unitSuffix(model.scale.unit);
  return '';
}

/** One cube's value line: exact for the brightest, otherwise from its colour code. */
function valueLine(model, i) {
  const exact = model.topk.get(i);
  if (model.kind === 'ensemble') {
    const refWord = model.refName === 'cam_ref' ? 'cam_ref' : 'ρ_ref';
    const what = { density: 'ρ', gradcam_energy: 'Σ E·Grad-CAM', shapcam_energy: 'Σ E·Shap-CAM' }[model.channel] ?? 'value';
    if (exact && Number.isFinite(exact.value)) {
      const ratio = Number.isFinite(model.ref) && model.ref !== 0 ? exact.value / model.ref : null;
      return `${what} = ${formatSci(exact.value, 3)} GeV mm⁻³ per event`
        + (ratio === null ? '' : ` = ${formatSci(ratio, 3)} ${refWord} (exact)`)
        + (Number.isFinite(exact.energy_gev) ? ` · ${formatSci(exact.energy_gev, 3)} GeV in the voxel` : '');
    }
    const value = codeValue(model, model.code[i]);
    if (value === null) return `${what}: no value`;
    const text = model.scale?.scale === 'signed_log10'
      ? `${value < 0 ? MINUS : '+'}${formatSci(Math.abs(value), 2)}`
      : formatSci(value, 2);
    return `${what} ≈ ${text} ${refWord} (from the colour code)`;
  }
  const quantity = model.channel;
  if (quantity === 'species') {
    const name = model.scale?.codes?.find((c) => c.code === model.code[i])?.name;
    const parts = [`Species ${speciesLabel(name)}`];
    if (exact && Number.isFinite(exact.energy_gev)) parts.push(`${formatSci(exact.energy_gev, 3)} GeV`);
    return parts.join(' · ');
  }
  const label = { energy: 'E/V', gradcam: 'Grad-CAM', shapcam: 'Shap-CAM', segerr: '|f_A,pred − f_A,true|' }[quantity] ?? 'value';
  const unit = valueUnit(model);
  const write = (v) => (quantity === 'shapcam' ? formatSigned(v, 3, { plus: true })
    : quantity === 'energy' ? formatSci(v, 3) : typographic(Number(v).toFixed(3)));
  if (exact && Number.isFinite(exact.value)) {
    return `${label} = ${write(exact.value)}${unit ? ` ${unit}` : ''} (exact)`
      + (Number.isFinite(exact.energy_gev) ? ` · ${formatSci(exact.energy_gev, 3)} GeV in the cube` : '');
  }
  const value = codeValue(model, model.code[i]);
  if (value === null) return `${label}: no value`;
  return `${label} ≈ ${write(value)}${unit ? ` ${unit}` : ''} (from the colour code)`;
}

/** The species detail of one cube: parent and daughters in the cell frames, purity in a splat. */
function speciesDetail(model, i) {
  const s = model.species;
  if (!s) return [];
  const out = [];
  if (s.parent) {
    const p = s.parent[i];
    out.push(`parent ${p === s.none ? 'none' : speciesLabel(s.parents[p] ?? '—')}`);
  }
  if (s.nDaughters) {
    const k = s.nDaughters[i];
    const mode = s.daughterMode?.[i];
    out.push(k > 0
      ? `${formatInt(k)} daughter${k === 1 ? '' : 's'}${mode !== undefined && mode !== s.none ? `, mostly ${speciesLabel(s.daughters[mode] ?? '—')}` : ''}`
      : 'no daughters');
  }
  if (s.purity) out.push(`purity ${formatPercent(s.purity[i] / 255, 0)} (the leading species' share of the voxel's energy)`);
  return out;
}

/**
 * One cube's tooltip, as HTML (every value escaped): its centre in the
 * frame's symbols, its value (exact for the 64 brightest, otherwise read back
 * from its colour code, and labelled as such), its flags and what one cube is.
 */
export function voxelTooltip(model, i) {
  if (!(i >= 0 && i < model.n)) return '';
  const s = model.symbols;
  const lines = [
    `(${s.x}, ${s.y}, ${s.z}) = (${fixed(model.x[i])}, ${fixed(model.y[i])}, ${fixed(model.z[i])}) mm`,
    valueLine(model, i),
  ];
  if (model.kind === 'event') {
    const tags = [];
    if (model.nShowers > 1 || model.shower[i] !== 0) {
      const label = model.showerCodes[model.shower[i]];
      if (label && label !== '—') tags.push(label);
    }
    if (model.primary[i]) tags.push('primary-tagged');
    if (model.below[i]) tags.push('below the ramp floor, drawn at its lowest colour');
    tags.push(...speciesDetail(model, i));
    if (tags.length) lines.push(tags.join(' · '));
    const b = model.box;
    lines.push(model.regime === 'cells'
      ? `One detector cell, ${fixed(b.x, 2)} × ${fixed(b.y, 2)} × ${fixed(b.z, 1)} mm, at its measured lattice position.`
      : `One axis-aligned ${fixed(b.x, 0)} × ${fixed(b.y, 0)} × ${fixed(b.z, 1)} mm voxel of the sub-deposit splat.`);
  } else {
    const b = model.box;
    lines.push(`One ${fixed(b.x, 0)} × ${fixed(b.y, 0)} × ${fixed(b.z, 1)} mm voxel of the selection's cloud.`);
  }
  const [head, ...rest] = lines;
  return [escapeHtml(head), ...rest.slice(0, -1).map((l) => escapeHtml(l)), mutedLine(rest[rest.length - 1])].join('<br>');
}

/* -------------------------------------------------------------- option -- */

/**
 * An axis title's offset from its axis, in grid3D world units (echarts-gl places
 * an axis name `nameGap` units out from the axis, perpendicular to it, and its
 * tick labels `axisLabel.margin`, 8 units, out). At the default 20 the long
 * "z — depth [mm]" title crossed the middle depth tick label at 1440 px
 * (P-18), and "y [mm]" touched its middle tick at 1440 and 1600 px. At 30,
 * checked in Chromium at 1440, 1600 and 1920 px, every title clears its
 * labels and stays inside the canvas.
 */
export const AXIS_NAME_GAP = 30;

/**
 * ECharts' own tick step for a value axis of `span` split `splitNumber` ways:
 * its `nice(span / splitNumber, true)`, a 1, 2, 3 or 5 times a power of ten.
 * echarts-gl's axes take it from `splitNumber` and place their ticks on its
 * multiples in data coordinates; an explicit `interval` would instead start
 * them at the axis minimum, off the round grid (measured in Chromium).
 */
export function niceStep(span, splitNumber = 5) {
  const raw = span / Math.max(1, splitNumber);
  if (!(raw > 0) || !Number.isFinite(raw)) return 1;
  const exp10 = 10 ** Math.floor(Math.log10(raw));
  const f = raw / exp10;
  const nf = f < 1.5 ? 1 : f < 2.5 ? 2 : f < 4 ? 3 : f < 7 ? 5 : 10;
  return nf * exp10;
}

/** Whether `v` is a multiple of `step` (to a millionth of a step). */
function onStep(v, step) {
  return Number.isFinite(v) && step > 0 && Math.abs(v / step - Math.round(v / step)) < 1e-6;
}

/**
 * The least distance, in box units, between two labelled ticks. At the
 * opening zoom a box unit is about 2.3 px at a 1600 px window for a cube
 * (a flat box opens closer, about 5-6 px, which only spreads its labels),
 * and a label such as "3600" about 26 px wide, so ticks closer than this overprint. A
 * per-axis event window makes a short side (the synthetic single-shower
 * event 3's 300 mm depth in a 4,040 mm box is 7.4 units) where two ticks
 * would sit 5 units apart; there only every k-th tick is labelled.
 */
export const MIN_LABEL_UNITS = 10;

/**
 * The tick plan of one display axis over `[lo, hi]` mm whose box side is
 * `world` units long (P-17): `splitNumber` about five ticks on the longest
 * side and fewer on a short one, so a co-registered cloud's depth does not
 * pile its labels up at the corner; `step`, the interval ECharts will choose
 * for it (`niceStep`); and the round `origin` the axis is shifted by,
 * `floor(lo / step) · step`. Cubes are placed at `mm − origin` (never
 * negative, so the spacer stacking holds), the axis spans `[lo − origin,
 * hi − origin]`, and ECharts' ticks fall on multiples of `step` there: round
 * millimetres once the labels add the origin back. An axis end is labelled
 * only where it is itself a tick (`showMin`, `showMax`, and the formatter
 * blanks any off-grid value), so no end overprints its neighbouring round tick.
 * `labelStep` is the step of the labelled ticks: `step`, or a whole multiple
 * of it on a side too short for every tick to carry a label
 * (`MIN_LABEL_UNITS`); every tick is still drawn.
 */
export function axisTicks(lo, hi, world = BOX_UNITS) {
  const splitNumber = Math.max(2, Math.round((5 * world) / BOX_UNITS));
  const step = niceStep(hi - lo, splitNumber);
  const origin = Math.floor(lo / step + 1e-9) * step;
  const units = hi > lo ? (step * world) / (hi - lo) : Infinity;
  const labelStep = units >= MIN_LABEL_UNITS ? step : step * Math.ceil(MIN_LABEL_UNITS / units);
  return {
    step, labelStep, origin, splitNumber, min: lo - origin, max: hi - origin,
    showMin: onStep(lo, labelStep), showMax: onStep(hi, labelStep),
  };
}

/** A grid3D value axis on a tick plan (`axisTicks`), labelled in the frame's own millimetres. */
function axis3D(name, ticks, { nameGap = null } = {}) {
  return {
    type: 'value',
    name,
    min: ticks.min,
    max: ticks.max,
    // Not `interval`: echarts-gl would start an explicit interval at `min`. From splitNumber it
    // picks `ticks.step` itself and puts the ticks on its multiples, which the origin makes round.
    splitNumber: ticks.splitNumber,
    ...(Number.isFinite(nameGap) ? { nameGap } : {}),
    nameTextStyle: { color: THEME.muted, fontSize: THEME.fontName, fontFamily: THEME.fontFamily },
    axisLine: { lineStyle: { color: THEME.border, width: THEME.lineAxis } },
    axisTick: { show: true, lineStyle: { color: THEME.border } },
    axisLabel: {
      color: THEME.muted,
      fontSize: THEME.fontLabel,
      fontFamily: THEME.fontFamily,
      showMinLabel: ticks.showMin,
      showMaxLabel: ticks.showMax,
      // echarts-gl ignores showMin/MaxLabel and labels the axis ends it adds, so an end
      // off the step grid is blanked here: only the round ticks are labelled.
      // On a short side only every labelStep-th millimetre is labelled (`axisTicks`).
      formatter: (v) => (onStep(Number(v) + ticks.origin, ticks.labelStep ?? ticks.step)
        ? typographic(String(Math.round(Number(v) + ticks.origin))) : ''),
    },
    splitLine: { show: false },
    splitArea: { show: false },
    axisPointer: { show: false },
  };
}

/** Axis titles of the three display axes, by the frame's symbols. */
export function axisNames(symbols) {
  return {
    depth: `${symbols.z} — depth [mm]`,
    x: `${symbols.x} [mm]`,
    y: `${symbols.y} [mm]`,
  };
}

/**
 * Which cubes are drawn, and how: `{opaque, translucent}` index lists in
 * payload order, and the counts of those not drawn - `noValue`, whose code
 * carries no colour (alpha 0: code 0, or the bottom of a floor taper), and
 * `hidden`, whose species an isolate toggle hides.
 */
export function partitionCubes(model, rgba, hidden = null) {
  const opaque = [];
  const translucent = [];
  let noValue = 0;
  let hiddenCount = 0;
  let cropped = 0;
  const categorical = model.scale?.scale === 'categorical';
  for (let i = 0; i < model.n; i += 1) {
    const alpha = rgba[i * 4 + 3] / 255;
    if (!inCrop(model, i)) {
      // Outside the paired projections' window: counted apart, never "skipped" by the taper.
      cropped += 1;
    } else if (!(alpha > 0)) {
      noValue += 1;
    } else if (categorical && hidden?.has(model.code[i])) {
      hiddenCount += 1;
    } else {
      (alpha >= OPAQUE_ALPHA ? opaque : translucent).push(i);
    }
  }
  return { opaque, translucent, noValue, hidden: hiddenCount, skipped: noValue + hiddenCount, cropped };
}

/**
 * The echarts-gl option of one model.
 *
 * Returns `{option, roles, bounds, box, ticks, fit, drawn, skipped, noValue,
 * hidden, translucent, cropped, primaries, halos}`: `fit` is `{frame,
 * right}` (`voxelFit`), which the section keeps to refit on resize;
 * `roles[seriesIndex]`
 * says what each series is (`spacer`, `cube` with the payload indices of its
 * items in data order, or `halo`), which the tooltip and the tests read.
 * `opts`: `palette`; `hidden` a Set of species codes the isolate toggles
 * hide; `position` the tooltip's placement callback (tooltip.js); `qualitative`
 * the species palette name (the card's, THEME's, by default); `viewport` the
 * chart's `{width, height}` in px, which sets the opening view (`openingView`:
 * the orthographic size and the camera's viewport).
 */
export function voxelOption(model, {
  palette = 'viridis', hidden = null, position = null, qualitative = THEME.speciesPalette, viewport = null,
} = {}) {
  const rgba = cubeColours(model, palette, { qualitative });
  const bounds = voxelBounds(model);
  const { lo, hi, span } = bounds;
  const box = boxSizes(span);
  // Round ticks: each axis is shifted by its tick plan's round origin, not by the box minimum.
  const ticks = {
    z: axisTicks(lo.z, hi.z, box.boxWidth),
    x: axisTicks(lo.x, hi.x, box.boxDepth),
    y: axisTicks(lo.y, hi.y, box.boxHeight),
  };
  const origin = { x: ticks.x.origin, y: ticks.y.origin, z: ticks.z.origin };
  const barSize = [box.S * model.box.z, box.S * model.box.x];
  const parts = partitionCubes(model, rgba, hidden);

  const series = [];
  const roles = [];
  // No value label, at rest or on hover: echarts-gl's default emphasis label
  // prints the bar's raw height (the cube size, unformatted) beside the cube.
  const common = {
    type: 'bar3D', shading: 'color', bevelSize: 0, barSize, animation: false,
    label: { show: false }, emphasis: { label: { show: false } },
  };
  const colourOf = (i) => `rgb(${rgba[i * 4]},${rgba[i * 4 + 1]},${rgba[i * 4 + 2]})`;
  for (const [name, members] of [['opaque', parts.opaque], ['translucent', parts.translucent]]) {
    if (!members.length) continue;
    const stack = `cubes-${name}`;
    series.push({
      ...common,
      name: `spacers (${name})`,
      stack,
      silent: true,
      itemStyle: { opacity: 0 },
      data: members.map((i) => [model.z[i] - origin.z, model.x[i] - origin.x, model.y[i] - model.box.y / 2 - origin.y]),
    });
    roles.push({ role: 'spacer', members });
    series.push({
      ...common,
      name: `cubes (${name})`,
      stack,
      data: members.map((i) => ({
        value: [model.z[i] - origin.z, model.x[i] - origin.x, model.box.y, i],
        itemStyle: { color: colourOf(i), opacity: rgba[i * 4 + 3] / 255 },
      })),
    });
    roles.push({ role: 'cube', members });
  }

  // Halos on the primary-tagged cubes that are drawn, the most energetic
  // first (payload order is ascending energy, so from the end).
  const drawnPrimaries = [];
  if (model.kind === 'event') {
    const drawn = new Set([...parts.opaque, ...parts.translucent]);
    for (let i = model.n - 1; i >= 0; i -= 1) if (model.primary[i] && drawn.has(i)) drawnPrimaries.push(i);
  }
  const halos = drawnPrimaries.slice(0, HALO_LIMIT);
  for (const i of halos) {
    const path = cubeWireframe(model, i, origin);
    // An outer line in the text colour, an inner one in the canvas colour: the
    // directive's black edge is about 1.2:1 on the dark #1c2128 card, so the
    // halo pairs the text colour (14.4:1 there; #111827 is 17.7:1 on the light
    // card) with the canvas colour, legible on any cube colour beneath it. On
    // the light card the pair is simply the other way round, dark outside.
    for (const [color, width] of [[THEME.text, 3], [THEME.canvas, 1.2]]) {
      series.push({ type: 'line3D', name: 'primary halo', silent: true, animation: false, lineStyle: { color, width, opacity: 1 }, data: path });
      roles.push({ role: 'halo', members: [i] });
    }
  }

  const names = axisNames(model.symbols);
  const legend = voxelLegend(model, palette);
  // A diverging ramp marks its zero ("0", or the undrawn ±10⁻³ band), as the 2-D panels do.
  const mid = legend ? rampMidLabel(model.scale) : null;
  const frame = glFrame(box, ticks, names, cloudExtent(model, lo, box));
  const formatter = (params) => {
    const role = roles[params?.seriesIndex];
    if (!role || role.role !== 'cube') return '';
    return voxelTooltip(model, role.members[params.dataIndex]);
  };
  // Room on the right for the 2-D colour legend; the opening view fits the area left of it.
  const right = legendStrip(legend, mid);
  const view = openingView(viewport?.width, viewport?.height, right, frame);
  const option = {
    backgroundColor: THEME.chartBackground,
    animation: false,
    textStyle: { fontFamily: THEME.fontFamily },
    tooltip: wrapTooltip({ ...tooltipOption(position), formatter }),
    grid3D: {
      boxWidth: box.boxWidth,
      boxDepth: box.boxDepth,
      boxHeight: box.boxHeight,
      viewControl: {
        ...CAMERA,
        orthographicSize: view.size,
        minOrthographicSize: ORTHO_SIZE_RANGE[0],
        maxOrthographicSize: ORTHO_SIZE_RANGE[1],
        damping: 0,
        autoRotate: false,
        animation: false,
      },
      light: { main: { intensity: 0, shadow: false }, ambient: { intensity: 1 } },
      postEffect: { enable: false },
      temporalSuperSampling: { enable: false },
      environment: 'none',
      axisPointer: { show: false },
      axisLine: { lineStyle: { color: THEME.border } },
      splitLine: { show: false },
      splitArea: { show: false },
      // The camera's viewport (`openingView`): centred on the box, sized to cover the area.
      left: view.left,
      top: view.top,
      width: view.width,
      height: view.height,
      right,
    },
    xAxis3D: axis3D(names.depth, ticks.z, { nameGap: AXIS_NAME_GAP }),
    yAxis3D: axis3D(names.x, ticks.x, { nameGap: AXIS_NAME_GAP }),
    zAxis3D: axis3D(names.y, ticks.y, { nameGap: AXIS_NAME_GAP }),
    series,
  };
  if (legend) {
    option.visualMap = legend;
    if (mid) option.graphic = [mid];
  }
  return {
    option,
    roles,
    bounds,
    box,
    ticks,
    fit: { frame, right },
    drawn: parts.opaque.length + parts.translucent.length,
    skipped: parts.skipped,
    noValue: parts.noValue,
    hidden: parts.hidden,
    translucent: parts.translucent.length,
    cropped: parts.cropped,
    primaries: drawnPrimaries.length,
    halos: halos.length,
  };
}
