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
 * `species` palette (`palette.QUALITATIVE`, checked for contrast and colour-
 * vision deficiency), with "other" in grey.
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

/** Pixels the colour legend reserves on the right of the 3-D viewport (grid3D `right`). */
export const LEGEND_RIGHT = 60;

/**
 * The narrowest viewport, width over height, that holds the opening view at
 * `CAMERA.orthographicSize`. echarts-gl fixes an orthographic camera's
 * height at that size and derives its width from the viewport, so a narrower
 * viewport cuts the view's sides, the vertical axis title first. Measured in
 * Chromium on a 100-unit cube (an event's window, the widest box) at the
 * opening angles: the box, its ticks and its axis titles span 1.134 times the
 * viewport's height (636 of 561 px), plus 8 px each side. A flatter box (a
 * co-registered cloud) needs less.
 */
export const FIT_ASPECT = 1.16;

/**
 * The opening orthographic size for a `width` × `height` px chart whose
 * viewport gives up `right` px to the legend: the camera's own wherever the
 * viewport is wide enough, else widened just enough that the opening view
 * keeps every cube, tick and axis title inside the canvas.
 */
export function orthographicFit(width, height, right = 0) {
  const w = width - right;
  if (!(w > 0 && height > 0)) return CAMERA.orthographicSize;
  const need = (FIT_ASPECT * height) / w;
  return need > 1 ? Math.round(CAMERA.orthographicSize * need * 10) / 10 : CAMERA.orthographicSize;
}

/** The 3-D plot's height bounds, px: a stacked or wide card is 560 px tall, a narrow one no less than 360. */
export const GL_HEIGHT_MIN = 360;
export const GL_HEIGHT_MAX = 560;

/**
 * The 3-D plot's height for a plot `width` px wide: the height at which the
 * opening view exactly fills the viewport left of the legend,
 * `(width − LEGEND_RIGHT) / FIT_ASPECT`, within [360, 560] px. A narrow card
 * then needs no widened zoom (`orthographicFit` stays at the camera's own
 * size) and leaves no empty band above and below the box; only below
 * 360 px of height does the zoom widen again. Set by voxel_views.js on the
 * plot element before the chart is created and on every resize, never
 * through CSS, so the layout snaps with no transition.
 */
export function glPlotHeight(width) {
  if (!(width > 0)) return GL_HEIGHT_MAX;
  const fit = Math.round((width - LEGEND_RIGHT) / FIT_ASPECT);
  return Math.max(GL_HEIGHT_MIN, Math.min(GL_HEIGHT_MAX, fit));
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
 * `window` the server's equal half-width window `{x, y, z: [lo, hi]}`.
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
 * `fadeDecades` is the floor taper of the relative ramps (THEME's on screen).
 */
export function voxelCodeTable(model, palette = 'viridis', { fadeDecades = THEME.floorFadeDecades, qualitative = 'species' } = {}) {
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
export function speciesLegend(model, hidden = new Set(), qualitative = 'species') {
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
 */
export function axisTicks(lo, hi, world = BOX_UNITS) {
  const splitNumber = Math.max(2, Math.round((5 * world) / BOX_UNITS));
  const step = niceStep(hi - lo, splitNumber);
  const origin = Math.floor(lo / step + 1e-9) * step;
  return {
    step, origin, splitNumber, min: lo - origin, max: hi - origin,
    showMin: onStep(lo - origin, step), showMax: onStep(hi - origin, step),
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
      formatter: (v) => (onStep(Number(v), ticks.step)
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
 * Returns `{option, roles, bounds, box, drawn, skipped, noValue, hidden,
 * translucent, cropped, primaries, halos}`: `roles[seriesIndex]`
 * says what each series is (`spacer`, `cube` with the payload indices of its
 * items in data order, or `halo`), which the tooltip and the tests read.
 * `opts`: `palette`; `hidden` a Set of species codes the isolate toggles
 * hide; `position` the tooltip's placement callback (tooltip.js); `qualitative`
 * the species palette name; `viewport` the chart's `{width, height}` in px,
 * which sets the opening orthographic size (`orthographicFit`).
 */
export function voxelOption(model, {
  palette = 'viridis', hidden = null, position = null, qualitative = 'species', viewport = null,
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
    // Outer light line, inner dark line: the directive's black edge is about
    // 1.2:1 on the #1c2128 card, so the halo pairs the text colour (14.4:1)
    // with the canvas colour, legible on any cube colour beneath it.
    for (const [color, width] of [[THEME.text, 3], [THEME.canvas, 1.2]]) {
      series.push({ type: 'line3D', name: 'primary halo', silent: true, animation: false, lineStyle: { color, width, opacity: 1 }, data: path });
      roles.push({ role: 'halo', members: [i] });
    }
  }

  const names = axisNames(model.symbols);
  const legend = voxelLegend(model, palette);
  const formatter = (params) => {
    const role = roles[params?.seriesIndex];
    if (!role || role.role !== 'cube') return '';
    return voxelTooltip(model, role.members[params.dataIndex]);
  };
  // Room on the right for the 2-D colour legend.
  const right = legend ? LEGEND_RIGHT : 0;
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
        orthographicSize: orthographicFit(viewport?.width, viewport?.height, right),
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
      right,
    },
    xAxis3D: axis3D(names.depth, ticks.z, { nameGap: AXIS_NAME_GAP }),
    yAxis3D: axis3D(names.x, ticks.x, { nameGap: AXIS_NAME_GAP }),
    zAxis3D: axis3D(names.y, ticks.y, { nameGap: AXIS_NAME_GAP }),
    series,
  };
  if (legend) {
    option.visualMap = legend;
    // A diverging ramp marks its zero ("0", or the undrawn ±10⁻³ band), as the 2-D panels do.
    const mid = rampMidLabel(model.scale);
    if (mid) option.graphic = [mid];
  }
  return {
    option,
    roles,
    bounds,
    box,
    ticks,
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
