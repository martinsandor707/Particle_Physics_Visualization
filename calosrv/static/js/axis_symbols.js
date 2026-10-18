/* The symbol each spatial axis is written with, and the one rule that names D.
 *
 * The server names every axis by its semantic identity (x, y, z) and, in a
 * co-registered frame, adds the symbol it is written with (x′, Δx, u …). One
 * exception is made here, on the client: the entry panel of the
 * Separation-Aligned (D-Frame) writes its horizontal axis as D. That axis is
 * the x′ coordinate along the A→B separation, with the two anchors at
 * ∓⟨D_entry⟩/2, so the panel reads as the separation it was built around. The
 * tick values stay the signed x′ coordinate in millimetres, and the depth
 * panels keep x′, y′ and z′. Every consumer that names that axis - the axis
 * title, the hover readout, the window phrase, the drawer's provenance line,
 * the centroid tooltips - reads it from here, so the screen cannot disagree
 * with itself about what the axis is called.
 *
 * A leaf module: no imports, so it runs under Node for the tests and is
 * versioned through its importers.
 */

export const SEPARATION_AXIS = 'D';

/** Fallback symbols per frame kind, for a payload that carries none. */
export const FRAME_SYMBOLS = Object.freeze({
  lab: { x: 'x', y: 'y', z: 'z' },
  canonical: { x: 'x′', y: 'y′', z: 'z′' },
  trans: { x: 'Δx', y: 'Δy', z: 'Δz' },
  local: { x: 'u', y: 'v', z: 'w' },
});

/** Semantic axis names of each panel: depth is the column axis of the depth panels. */
const PANEL_AXES = Object.freeze({
  xy: { col: 'x', row: 'y' },
  yz: { col: 'z', row: 'y' },
  xz: { col: 'z', row: 'x' },
});

/** Which panel a payload's axes belong to. */
export function panelOf(axes) {
  const col = axes?.col?.name;
  const row = axes?.row?.name;
  if (col !== 'z') return 'xy';
  return row === 'x' ? 'xz' : 'yz';
}

/** The symbol one axis is written with, on one panel of one frame kind. */
export function axisSymbol(axis, kind = 'lab', panelId = 'xy') {
  if (!axis) return '';
  if (kind === 'canonical' && panelId === 'xy' && axis.name === 'x') return SEPARATION_AXIS;
  return axis.symbol ?? FRAME_SYMBOLS[kind]?.[axis.name] ?? axis.name ?? '';
}

/**
 * Both symbols of a panel: from its axes when the payload is in hand, else
 * from the frame table (a disclosure built before the panel is rendered).
 */
export function panelSymbols(kind = 'lab', panelId = 'xy', axes = null) {
  const names = PANEL_AXES[panelId] ?? PANEL_AXES.xy;
  const col = axes?.col ?? { name: names.col };
  const row = axes?.row ?? { name: names.row };
  return { col: axisSymbol(col, kind, panelId), row: axisSymbol(row, kind, panelId) };
}
