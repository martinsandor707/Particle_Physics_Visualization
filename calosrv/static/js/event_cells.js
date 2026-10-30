/* The options of the 2-D spatial cells, on both pages: what each
 * ProjectionPanel of an event raster or of a projections response renders
 * with. This module is their one owner.
 *
 * The event cells draw the Event Inspector's rasters: one shower of one event
 * in one frame, the frame's window for the panel's two axes - one half-width
 * for every axis on the Physics page, one per axis on the Models page
 * (`window=per_axis`), the panel isometric either way, letterboxed from its
 * millimetre spans - the frame's marks in the shower's colour, framed. The Physics
 * page's Event Inspector (event_inspector.js, as `cellOptions` and
 * `cellTitle`) and the Models page's 3-D event view draw them alike.
 *
 * The ensemble cells are the spatial panels of one `/api/projections`
 * response: the Physics page's 2 x 2 diagnostic and compare-frames grid
 * (main.js `panelOptions`), and the Models page's projections beside the 3-D
 * cloud. `depthIsometric` decides the depth panels' aspect for both.
 *
 * Both pages import it, so it imports nothing either page owns: the Models
 * page's module graph may hold no Physics page module (tests/test_api.py).
 */

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
    // The shower, not its colour: the panel resolves the ink when it builds an
    // option, so an export (built under the print tokens) prints the print ink
    // and is the same figure from either screen theme.
    markShower: shower.key === 'b' ? 'b' : 'a',
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
 * served with, else `weighting` (the page's own choice).
 */
export function ensembleCellOptions(payload, id, palette, weighting = 'energy') {
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
    weighting: payload?.meta?.weighting ?? weighting,
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
