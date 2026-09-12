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
 */

import { lookupTable } from './palette.js';

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
 * Render a panel payload to an offscreen canvas.
 *
 * Physical placement and any stretch to the panel's aspect are done by the
 * chart from the millimetre extents, so this never bakes an aspect ratio into
 * the bitmap - only the correct *relative* cell widths.
 *
 * Row 0 of the matrix is the lowest coordinate, but canvas y grows downward, so
 * rows are written bottom-up to keep the image the right way round.
 */
export function renderRaster(payload, paletteName) {
  const [rows, cols] = payload.shape;
  const codes = decodeBase64(payload.data);
  const table = lookupTable(paletteName);

  const colLookup = axisLookup(payload.axes.col, cols);
  const rowLookup = axisLookup(payload.axes.row, rows);
  const width = colLookup.length;
  const height = rowLookup.length;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(width, height);
  const out = image.data;

  const emptyCode = payload.empty_code ?? 0;

  for (let y = 0; y < height; y += 1) {
    const sourceRow = rowLookup[y] * cols;
    const targetRow = (height - 1 - y) * width;
    for (let x = 0; x < width; x += 1) {
      const code = codes[sourceRow + colLookup[x]];
      const o = (targetRow + x) * 4;
      if (code === emptyCode) {
        out[o + 3] = 0;
        continue;
      }
      const p = code * 3;
      out[o] = table[p];
      out[o + 1] = table[p + 1];
      out[o + 2] = table[p + 2];
      out[o + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
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
