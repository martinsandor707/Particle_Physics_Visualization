/* Colourblind-safe sequential palettes, as 256-entry RGB lookup tables.
 *
 * CLAUDE.md section 2 permits Viridis, Cividis, Plasma, Turbo and ColorBrewer,
 * and strictly forbids rainbow/jet ramps. Viridis is the default for density
 * because its lightness is *monotone*: on a six-decade logarithmic ramp the eye
 * orders the decades by brightness before it decodes any hue, which is what
 * makes a faint halo legible next to a bright core.
 *
 * Turbo is offered because the brief lists it, but it is not the default. It is
 * an improved rainbow and its lightness is not monotone, so across a wide
 * dynamic range it produces false bright bands at the hue transitions that read
 * as structure which is not in the data.
 *
 * The tables are generated from the published anchor points by linear
 * interpolation in sRGB. That is accurate to a fraction of a colour step
 * against the reference implementations - far below what the eye resolves and
 * far below the 5.6% quantisation step of the encoded raster.
 */

const ANCHORS = {
  viridis: [
    [68, 1, 84], [72, 34, 115], [64, 67, 135], [52, 94, 141], [41, 120, 142],
    [32, 144, 140], [34, 167, 132], [68, 190, 112], [121, 209, 81],
    [189, 222, 38], [253, 231, 37],
  ],
  cividis: [
    [0, 32, 76], [0, 42, 102], [0, 52, 110], [39, 63, 108], [60, 74, 107],
    [76, 85, 107], [91, 97, 109], [108, 110, 111], [125, 123, 110],
    [145, 137, 106], [165, 152, 99], [187, 168, 88], [209, 185, 73],
    [232, 202, 51], [255, 221, 0],
  ],
  plasma: [
    [13, 8, 135], [70, 3, 159], [114, 1, 168], [156, 23, 158], [189, 55, 134],
    [216, 87, 107], [237, 121, 83], [251, 159, 58], [253, 202, 38],
    [240, 249, 33],
  ],
  turbo: [
    [48, 18, 59], [70, 107, 227], [40, 187, 236], [49, 242, 153],
    [136, 255, 63], [211, 231, 41], [253, 165, 49], [243, 84, 19],
    [190, 29, 3], [122, 4, 3],
  ],
};

/** Build a 256-entry Uint8 RGB table by interpolating the anchor points. */
function buildTable(anchors) {
  const table = new Uint8ClampedArray(256 * 3);
  const segments = anchors.length - 1;
  for (let i = 0; i < 256; i += 1) {
    const t = (i / 255) * segments;
    const index = Math.min(segments - 1, Math.floor(t));
    const frac = t - index;
    const a = anchors[index];
    const b = anchors[index + 1];
    table[i * 3] = a[0] + (b[0] - a[0]) * frac;
    table[i * 3 + 1] = a[1] + (b[1] - a[1]) * frac;
    table[i * 3 + 2] = a[2] + (b[2] - a[2]) * frac;
  }
  return table;
}

const CACHE = new Map();

export function lookupTable(name) {
  const key = ANCHORS[name] ? name : 'viridis';
  if (!CACHE.has(key)) CACHE.set(key, buildTable(ANCHORS[key]));
  return CACHE.get(key);
}

/** CSS colour stops for the ECharts visualMap legend. */
export function colorStops(name, count = 12) {
  const table = lookupTable(name);
  const stops = [];
  for (let i = 0; i < count; i += 1) {
    const index = Math.round((i / (count - 1)) * 255) * 3;
    stops.push(`rgb(${table[index]},${table[index + 1]},${table[index + 2]})`);
  }
  return stops;
}

/**
 * Discrete, well-separated colours for a handful of ordered categories.
 *
 * Sampling a sequential ramp across its full extent is right for a continuous
 * surface and wrong for thin lines on a dark canvas: Viridis starts at
 * #440154, which against the #0d1117 background is very nearly invisible at one
 * pixel wide. That is why the five separation slices in the energy panel read
 * as ambiguous.
 *
 * Restricting the sampled sub-range keeps the ordered lightness ramp - so the
 * slice order is still legible as brightness - while guaranteeing every stop
 * clears the background.
 */
export function categoricalStops(name, count, { min = 0.25, max = 1.0 } = {}) {
  const table = lookupTable(name);
  const stops = [];
  const n = Math.max(1, count);
  for (let i = 0; i < n; i += 1) {
    const t = n === 1 ? max : min + (i / (n - 1)) * (max - min);
    const index = Math.round(t * 255) * 3;
    stops.push(`rgb(${table[index]},${table[index + 1]},${table[index + 2]})`);
  }
  return stops;
}

export const PALETTES = Object.keys(ANCHORS);
