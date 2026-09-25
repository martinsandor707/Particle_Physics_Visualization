/* Decode a base64 uint8 raster into a canvas image.
 *
 * ECharts' own heatmap series emits one element per cell. At the native lattice
 * resolution the XY panel holds over twenty thousand cells, and the depth
 * panels more; that approach does not survive it. The payload is already an
 * 8-bit raster, so the fast path is to map it through a 256-entry RGBA lookup
 * table straight into ImageData and let the GPU composite one bitmap.
 *
 * Code 0 means "no deposit" and is painted fully transparent, letting the card
 * background show through. That distinction matters: an unlit detector cell and
 * a cell holding the faintest measurable deposit are different statements, and
 * painting both with the bottom colour of the ramp would make empty regions
 * look like a faint halo.
 *
 * ## The canonical display floor
 *
 * A canonical payload also carries `below_code` (1): bins holding energy below
 * the 10⁻³ ρ_ref floor of the ramp. Those used to be clamped into the opaque
 * bottom colour, which painted the whole fitted window as a dark-purple
 * rectangle around the shower. They are transparent now, and the ramp starts
 * at `min_code` (2) with 253 levels to `max_code`. The colour table is indexed
 * at `round((code − min_code) / (max_code − min_code) · 255)`, so a drawn
 * colour sits at the same place on the ramp as the legend and `dequantize`
 * put it. A lab payload carries no `below_code` and indexes by the code itself,
 * byte for byte as before.
 *
 * On a relative (a.u.) log ramp the bottom `THEME.floorFadeDecades` above the
 * floor also fade in alpha, linearly in log density, so the field dissolves
 * into the card instead of ending in a rim (see the token's note in scale.js).
 * Print sets the token to 0, which makes the alpha a pure step: a hard contour
 * that the caption names as the display floor.
 */

import { lookupTable } from './palette.js';
import { THEME, floorExponent } from './scale.js';

/** base64 -> Uint8Array, without a data: URL round trip. */
export function decodeBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Longest side of the resampling canvas when an axis is irregular. */
const MAX_PIXELS = 1024;

/**
 * Map uniformly spaced destination pixels onto source cells.
 *
 * This is what keeps the picture geometrically honest on this detector. The
 * transverse x lattice is *not* uniformly spaced: cells sit in tight pairs
 * 4.4 mm apart with roughly 44 mm between pair groups. Drawing one raster
 * column per cell would give the 4.4 mm gap and the 44 mm gap identical widths
 * on screen - a tenfold local distortion that appears as false vertical
 * striping and reads as detector structure that does not exist.
 *
 * So for an irregular axis the canvas is a uniform grid in *millimetres*, and
 * each pixel takes the value of whichever cell physically contains it. Wide
 * cells therefore occupy proportionally more pixels, which is the whole point.
 * A uniform axis short-circuits to the identity and costs nothing.
 */
function axisLookup(axis, cells) {
  if (axis.uniform || !axis.edges) {
    const identity = new Int32Array(cells);
    for (let i = 0; i < cells; i += 1) identity[i] = i;
    return identity;
  }

  const edges = axis.edges;
  const lo = edges[0];
  const hi = edges[edges.length - 1];
  const pixels = Math.min(MAX_PIXELS, Math.max(cells, 512));
  const lookup = new Int32Array(pixels);

  let cell = 0;
  for (let i = 0; i < pixels; i += 1) {
    const position = lo + ((i + 0.5) / pixels) * (hi - lo);
    while (cell < cells - 1 && position >= edges[cell + 1]) cell += 1;
    lookup[i] = cell;
  }
  return lookup;
}

/**
 * The 256-entry RGBA table a payload's codes are painted through.
 *
 * Pure, so it can be checked outside a browser. Transparent: `empty_code`,
 * `below_code`, and anything under `min_code`. Colour index: the code itself
 * on a lab payload; rescaled onto the full table when the payload carries a
 * `below_code`, because its ramp spans only codes `min_code`..`max_code`.
 *
 * Alpha is a pure step - 255 on the ramp, 0 off it - unless the ramp is a
 * relative log density *and* `fadeDecades` is a finite positive number. Only
 * then is it tapered, and only then is anything divided by it: the print
 * token is 0, and a NaN or ±Infinity must not reach a division that would
 * write NaN into ImageData (which the canvas silently reads as 0).
 */
export function codeTable(payload, paletteName, fadeDecades = THEME.floorFadeDecades) {
  const rgb = lookupTable(paletteName);
  const table = new Uint8ClampedArray(256 * 4);
  const scale = payload.scale || {};
  const emptyCode = payload.empty_code ?? 0;
  const belowCode = Number.isInteger(payload.below_code) ? payload.below_code : null;
  const minCode = payload.min_code ?? 1;
  const maxCode = payload.max_code ?? 255;
  const span = maxCode - minCode;

  const floorExp = floorExponent(scale);
  const taper = Number.isFinite(fadeDecades) && fadeDecades > 0
    && scale.unit === 'a.u.' && scale.scale === 'log10'
    && Number.isFinite(floorExp) && Number.isFinite(scale.vmin) && Number.isFinite(scale.vmax)
    && span > 0;

  for (let code = 0; code < 256; code += 1) {
    if (code === emptyCode || code === belowCode || code < minCode) continue;
    let index = code;
    if (belowCode !== null) {
      index = span > 0 ? Math.round(((code - minCode) / span) * 255) : 255;
    }
    index = Math.min(255, Math.max(0, index));
    const o = code * 4;
    table[o] = rgb[index * 3];
    table[o + 1] = rgb[index * 3 + 1];
    table[o + 2] = rgb[index * 3 + 2];

    let alpha = 255;
    if (taper) {
      const fraction = (code - minCode) / span;
      const value = scale.vmin + fraction * (scale.vmax - scale.vmin);
      const a = (value - floorExp) / fadeDecades;
      alpha = Number.isFinite(a) ? Math.round(255 * Math.min(1, Math.max(0, a))) : 255;
    }
    table[o + 3] = alpha;
  }
  return table;
}

/** Longest side of the nearest-neighbour pre-upscale of a raw-bin raster. */
const BLOCK_UPSCALE_PX = 2048;
/** Largest integer factor of that pre-upscale. */
const BLOCK_UPSCALE_MAX = 32;

/**
 * Render a panel payload to an offscreen canvas.
 *
 * Physical placement and any stretch to the panel's aspect are done by the
 * chart from the millimetre extents, so this never bakes an aspect ratio into
 * the bitmap - only the correct *relative* cell widths.
 *
 * Row 0 of the matrix is the lowest coordinate, but canvas y grows downward, so
 * rows are written bottom-up to keep the image the right way round.
 *
 * A payload with `kernel: 'none'` - the canonical Native Grid - is the raw
 * 20 mm accumulation bins, and the browser's bilinear upscale of a 33 × 20
 * bitmap would blur them into a field the payload does not contain. So it is
 * first enlarged by an integer nearest-neighbour factor, which keeps every bin
 * a crisp block on screen as the exporter already did in print. Continuous
 * Field keeps the smooth upscale along x′ and y′: its bins *are* samples of a
 * smooth field. Its depth axis is not - the payload's sampling layers are
 * never smoothed or interpolated - so a canonical depth panel is enlarged by a
 * nearest-neighbour factor along its depth columns only, which keeps every
 * layer a crisp band while the transverse rows stay smooth. The returned codes
 * and lookups stay at the payload's own size, so tooltips and the RoI fit
 * address bins, not pixels.
 *
 * `screen: false` skips both enlargements and returns one pixel per payload
 * bin, for the exporter, which applies its own uniform integer factor.
 */
export function renderRaster(payload, paletteName, { screen = true } = {}) {
  const [rows, cols] = payload.shape;
  const codes = decodeBase64(payload.data);
  const table = codeTable(payload, paletteName);

  const colLookup = axisLookup(payload.axes.col, cols);
  const rowLookup = axisLookup(payload.axes.row, rows);
  const width = colLookup.length;
  const height = rowLookup.length;

  let canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(width, height);
  const out = image.data;

  for (let y = 0; y < height; y += 1) {
    const sourceRow = rowLookup[y] * cols;
    const targetRow = (height - 1 - y) * width;
    for (let x = 0; x < width; x += 1) {
      const t = codes[sourceRow + colLookup[x]] * 4;
      const o = (targetRow + x) * 4;
      out[o] = table[t];
      out[o + 1] = table[t + 1];
      out[o + 2] = table[t + 2];
      out[o + 3] = table[t + 3];
    }
  }

  ctx.putImageData(image, 0, 0);

  if (screen && typeof payload.kernel === 'string') {
    const blocks = (n) => Math.max(1, Math.min(
      BLOCK_UPSCALE_MAX, Math.floor(BLOCK_UPSCALE_PX / Math.max(1, n)),
    ));
    let fx = 1;
    let fy = 1;
    if (payload.kernel === 'none') {
      fx = blocks(Math.max(width, height));
      fy = fx;
    } else if (payload.axes.col.name === 'z') {
      fx = blocks(width);
    }
    if (fx > 1 || fy > 1) {
      const scaled = document.createElement('canvas');
      scaled.width = width * fx;
      scaled.height = height * fy;
      const scaledCtx = scaled.getContext('2d');
      scaledCtx.imageSmoothingEnabled = false;
      scaledCtx.drawImage(canvas, 0, 0, scaled.width, scaled.height);
      canvas = scaled;
    }
  }
  return { canvas, codes, rows, cols, colLookup, rowLookup };
}

/** Cell index containing a millimetre position on a possibly irregular axis. */
export function cellAt(axis, cells, position) {
  if (axis.uniform || !axis.edges) {
    const fraction = (position - axis.lo) / (axis.hi - axis.lo);
    return Math.min(cells - 1, Math.max(0, Math.floor(fraction * cells)));
  }
  const edges = axis.edges;
  let low = 0;
  let high = cells - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (position >= edges[mid]) low = mid;
    else high = mid - 1;
  }
  return low;
}

/** Centre of a cell in millimetres, honouring an irregular axis. */
export function cellCentre(axis, cells, index) {
  if (axis.uniform || !axis.edges) {
    return axis.lo + ((index + 0.5) / cells) * (axis.hi - axis.lo);
  }
  return 0.5 * (axis.edges[index] + axis.edges[index + 1]);
}

/**
 * Millimetre bounding box of the active hits, for the Auto-fit RoI control.
 *
 * Bounded by an energy percentile rather than by the outermost occupied cell.
 * A single stray hit at the detector edge would otherwise define the region of
 * interest and the zoom would achieve nothing - the same reasoning CLAUDE.md
 * section 2 applies to axis limits generally.
 *
 * `weight: 'value'` weights each bin by its dequantised value - energy, or
 * density - which is what "the box holding 99% of the energy" means. The
 * default code weighting is monotone in energy but not proportional to it: on
 * the three-decade canonical ramp a bin a tenth as bright as the peak still
 * carries two thirds of its weight, so the fitted box swells towards the halo
 * (five sixths on the lab's six-decade ramp). The panels
 * pass 'value'; 'code' is kept for compatibility. Empty bins and bins below
 * the display floor carry no weight in either mode: they are not drawn.
 */
export function occupiedBounds(payload, raster, fraction = 0.99, { weight = 'code' } = {}) {
  const { codes, rows, cols } = raster;
  const empty = payload.empty_code ?? 0;
  const below = Number.isInteger(payload.below_code) ? payload.below_code : null;
  const minCode = payload.min_code ?? 1;

  // One weight per code, so the scan below is a lookup rather than a pow().
  const weights = new Float64Array(256);
  for (let code = 0; code < 256; code += 1) {
    if (code === empty || code === below || code < minCode) continue;
    if (weight === 'value') {
      const value = payload.scale ? dequantize(code, payload.scale, payload) : null;
      weights[code] = Number.isFinite(value) && value > 0 ? value : 0;
    } else {
      weights[code] = code;
    }
  }

  const rowWeight = new Float64Array(rows);
  const colWeight = new Float64Array(cols);
  let total = 0;

  for (let r = 0; r < rows; r += 1) {
    const base = r * cols;
    for (let c = 0; c < cols; c += 1) {
      const w = weights[codes[base + c]];
      if (w === 0) continue;
      rowWeight[r] += w;
      colWeight[c] += w;
      total += w;
    }
  }
  if (total === 0) return null;

  // Trim (1 - fraction)/2 of the weight from each end of each marginal.
  const cut = total * ((1 - fraction) / 2);
  const span = (weight, n) => {
    let acc = 0;
    let lo = 0;
    let hi = n - 1;
    for (let i = 0; i < n; i += 1) {
      acc += weight[i];
      if (acc > cut) { lo = i; break; }
    }
    acc = 0;
    for (let i = n - 1; i >= 0; i -= 1) {
      acc += weight[i];
      if (acc > cut) { hi = i; break; }
    }
    return [Math.min(lo, hi), Math.max(lo, hi)];
  };

  const [r0, r1] = span(rowWeight, rows);
  const [c0, c1] = span(colWeight, cols);

  const edge = (axis, cells, index) => {
    const clamped = Math.max(0, Math.min(cells, index));
    if (axis.uniform || !axis.edges) {
      return axis.lo + (clamped / cells) * (axis.hi - axis.lo);
    }
    return axis.edges[clamped];
  };

  return {
    col: [edge(payload.axes.col, cols, c0), edge(payload.axes.col, cols, c1 + 1)],
    row: [edge(payload.axes.row, rows, r0), edge(payload.axes.row, rows, r1 + 1)],
  };
}

/** Invert the quantisation for a tooltip: colour code -> physical value. */
export function dequantize(code, scale, payload) {
  const minCode = payload.min_code ?? 1;
  const maxCode = payload.max_code ?? 255;
  if (code < minCode) return null;
  const fraction = (code - minCode) / (maxCode - minCode);
  const value = scale.vmin + fraction * (scale.vmax - scale.vmin);
  return scale.scale === 'log10' ? 10 ** value : value;
}

/**
 * Exact value for a cell, preferring the shipped top-k list.
 *
 * Quantisation costs about 5.6% of relative precision per step. That is
 * invisible in the image and unacceptable in a tooltip, so the brightest cells
 * carry their exact float64 value and are looked up here first.
 */
export function exactValue(payload, row, col) {
  if (!payload.topk) return null;
  for (const cell of payload.topk) {
    if (cell.i === row && cell.j === col) return cell.value;
  }
  return null;
}
