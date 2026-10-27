/* The 2-D cells beside the 3-D views: what each paired ProjectionPanel
 * renders with, so the 3-D cards' recorded exception holds - every 3-D view
 * stands beside three 2-D projections that carry its cells quantitatively.
 *
 * The event cells draw the Event Inspector's rasters: one shower of one event
 * in one frame, the frame's equal half-width window for the panel's two axes,
 * the frame's marks in the shower's colour, framed and isometric. The
 * Physics page's Event Inspector builds the same options (event_inspector.js
 * `cellOptions`, `cellTitle`), but that module drives the Physics page's own
 * picker and may not be loaded here; the pure options are restated from the
 * payload's fields instead, and the inspector may import them from here.
 *
 * The ensemble cells are the Physics page's spatial panels: one
 * `/api/projections` response in the cloud's frame. Their options are
 * `main.js`'s `panelOptions`, and the depth panels' aspect its
 * `depthIsometric`; both are private to the Physics page's entry module,
 * which cannot be imported (it builds the page at load), so they are
 * restated here, line for line, for the two co-registered frames the cloud
 * is drawn in. The entry module may import them from here instead, and then
 * this file is their one owner.
 */

import { THEME } from './scale.js';

/** Each event panel's two axes as semantic names: column (horizontal), row (vertical). */
export const EVENT_PANEL_AXES = Object.freeze({ xy: ['x', 'y'], xz: ['z', 'x'], yz: ['z', 'y'] });

/** An event panel's two symbols in the panel's own order (X-Y, X-Z, Y-Z), e.g. "u–w". */
export function eventCellTitle(frame, col) {
  const symbols = frame?.symbols ?? {};
  const [a, b] = { xy: ['x', 'y'], xz: ['x', 'z'], yz: ['y', 'z'] }[col] ?? ['x', 'y'];
  return `${symbols[a] ?? a}–${symbols[b] ?? b}`;
}

/**
 * The options one event cell renders with, from the `/api/event` raster
 * response: the frame's window for this panel's two axes, the frame's marks
 * in the drawn shower's colour, a framed plot, and `resolution: {mode:
 * 'native'}` - raw lattice cells or raw grid bins, no reconstruction - for
 * the drawer and the export file name.
 */
export function eventCellOptions(payload, kind, col, palette) {
  const frame = payload.frames[kind];
  const shower = payload.event.shower;
  const [c, r] = EVENT_PANEL_AXES[col];
  return {
    palette,
    framed: true,
    tableName: payload.meta?.table_name,
    viewKey: `${payload.event.event_number}|${shower.key}|${kind}`,
    window: { col: frame.window[c], row: frame.window[r] },
    marks: frame.marks,
    markColour: shower.key === 'b' ? THEME.showerB : THEME.showerA,
    resolution: { mode: 'native' },
  };
}

/** The co-registered frames of an ensemble response, by its payload. */
function kindOf(payload) {
  const kind = payload?.frame?.kind;
  return ['canonical', 'trans', 'local'].includes(kind) ? kind : 'lab';
}

/**
 * Whether a co-registered depth panel can afford a true 1:1 aspect.
 *
 * A co-registered frame crops each panel to where the energy is, and for most
 * selections the two spans are comparable, so 1:1 becomes affordable. It is
 * used when the letterboxed plot would still keep at least 45% of the card's
 * width and the span ratio sits inside the export clamp [0.45, 1.3]
 * (main.js `depthIsometric`).
 */
export function depthIsometric(panel, panelPayload) {
  const { col, row } = panelPayload?.axes ?? {};
  if (!col || !row) return false;
  const colSpan = col.hi - col.lo;
  const rowSpan = row.hi - row.lo;
  if (!(colSpan > 0 && rowSpan > 0)) return false;
  const ratio = rowSpan / colSpan;
  if (ratio < 0.45 || ratio > 1.3) return false;
  const width = panel?.element?.clientWidth ?? 0;
  const height = panel?.element?.clientHeight ?? 0;
  if (!(width > 0 && height > 0)) return false;
  const scale = Math.min(width / colSpan, height / rowSpan);
  return colSpan * scale >= 0.45 * width;
}

/**
 * The options one spatial panel of a projections payload renders with
 * (main.js `panelOptions`): the entry panel carries the centroids and, in the
 * D-frame, the entry anchors; the D-frame's depth panels carry its two
 * ensemble axes and depth bounds, the sanctioned exception of CLAUDE.md
 * section 2; the Local frame draws no direction, since every incident
 * direction is +w by construction. `weighting` is the one the response was
 * served with.
 */
export function ensembleCellOptions(payload, id, palette) {
  const overlays = payload?.overlays || {};
  const kind = kindOf(payload);
  const canonical = kind === 'canonical';
  const coregistered = kind !== 'lab';
  const frame = coregistered ? payload.frame : null;
  const common = {
    palette,
    frame,
    tableName: payload?.meta?.table_name,
    resolution: payload?.meta?.resolution ?? null,
    weighting: payload?.meta?.weighting ?? 'energy',
  };
  const anchors = canonical ? (overlays.anchors || null) : null;
  if (id === 'xy') {
    return { ...common, centroids: payload.centroids, showVector: kind === 'lab', anchors };
  }
  const ensemble = overlays.ensemble_axes || {};
  return {
    ...common,
    axes: kind === 'lab' ? overlays.axes?.[id] : null,
    trajectories: kind === 'lab' || kind === 'trans' ? (overlays.trajectories || []) : null,
    showerKey: id === 'yz' ? 'y' : 'x',
    ensembleAxes: canonical ? ensemble[id] || null : null,
    ensembleMeta: canonical ? frame?.ensemble || null : null,
    anchors,
    depthBounds: canonical ? { front: 0, back: frame.depth_mm } : null,
  };
}
