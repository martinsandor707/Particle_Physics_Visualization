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
 *
 * ## Signed quantities: ColorBrewer PuOr, folded on screen
 *
 * Shap-CAM is signed, so it takes a diverging ramp symmetric about zero:
 * ColorBrewer PuOr (colourblind-safe, CLAUDE.md section 2), orange for
 * negative and purple for positive. Index 0 is the most negative value, 255
 * the most positive, and 127/128 zero.
 *
 * Print keeps the standard 11-class scheme, whose light centre marks zero on
 * white paper. On the dark screen that centre is wrong twice over: its
 * #f7f7f7 makes a bright halo round every near-zero bin, and its strongest
 * colours vanish into the #1c2128 card (#2d004b at 1.07:1, #7f3b08 at 1.95:1
 * in WCAG contrast). So the screen *folds* it: each arm runs from the card
 * outwards through PuOr's own colours in reverse, brightness rising steadily
 * with |value| and hue alone giving the sign. The anchors sit at explicit arm
 * positions p = |value| on the arm's own scale (the log position on a signed-
 * log ramp): the first colour at 3:1 against the card - #b35806 (3.3:1),
 * #8073ac (3.8:1) - lands at p = 1/6, which is 10^-2.5 of the peak on the
 * three-decade ramp. Below it the taper of `decode.codeTable` fades the bin
 * into the card, so nothing the reader is asked to see is drawn at under 3:1.
 * The raw (linear) Shap-CAM puts zero at border grey #30363d instead, so a
 * populated bin with zero attribution stays distinct from an empty one.
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

const CARD = [28, 33, 40];      // #1c2128
const BORDER = [48, 54, 61];    // #30363d

/** Standard 11-class ColorBrewer PuOr, most negative first (print). */
const PUOR = [
  [127, 59, 8], [179, 88, 6], [224, 130, 20], [253, 184, 99], [254, 224, 182],
  [247, 247, 247], [216, 218, 235], [178, 171, 210], [128, 115, 172], [84, 39, 136],
  [45, 0, 75],
];

/* The folded screen arms, from zero outwards: [arm position p, rgb].
 *
 * Anchors are placed by CIE lightness L*, so equal |value| reads equally bright
 * on both arms (orange L* 47, 63, 79, 90; purple 27, 51, 71, 87). On the signed
 * log the 3:1 anchors sit at p = 1/6 (10^-2.5 of the peak) and each arm's later
 * anchors follow its own L* line from there. On the linear raw Shap-CAM ramp
 * both arms follow one L* line from the #30363d zero (L* 22) to the dimmer end
 * (L* 87): a positive arm running through #542788 at p = 0.25 had stayed below
 * 3:1 until |v| = 0.43 while the orange arm crossed it at 0.24. */
const ARM_NEG = [[0, CARD], [1 / 6, [179, 88, 6]], [0.468, [224, 130, 20]],
  [0.786, [253, 184, 99]], [1, [254, 224, 182]]];
const ARM_POS = [[0, CARD], [0.08, [84, 39, 136]], [1 / 6, [128, 115, 172]],
  [0.635, [178, 171, 210]], [1, [216, 218, 235]]];
const ARM_NEG_LINEAR = [[0, BORDER], [0.391, [179, 88, 6]], [0.630, [224, 130, 20]],
  [0.881, [253, 184, 99]], [1, [254, 224, 182]]];
const ARM_POS_LINEAR = [[0, BORDER], [0.072, [84, 39, 136]], [0.451, [128, 115, 172]],
  [0.760, [178, 171, 210]], [1, [216, 218, 235]]];

/** The colour at arm position p of positioned anchors [[p, rgb], ...]. */
function armColour(arm, p) {
  let i = 0;
  while (i < arm.length - 2 && p > arm[i + 1][0]) i += 1;
  const [p0, a] = arm[i];
  const [p1, b] = arm[i + 1];
  const f = p1 > p0 ? Math.min(1, Math.max(0, (p - p0) / (p1 - p0))) : 0;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** A 256-entry diverging table from two arms: 0..127 negative (outermost at
 * 0), 128..255 positive (outermost at 255). */
function buildFolded(neg, pos) {
  const table = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const rgb = i < 128 ? armColour(neg, (127 - i) / 127) : armColour(pos, (i - 128) / 127);
    table.set(rgb, i * 3);
  }
  return table;
}

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

const DIVERGING = {
  puor: () => buildTable(PUOR),
  puor_screen: () => buildFolded(ARM_NEG, ARM_POS),
  puor_screen_linear: () => buildFolded(ARM_NEG_LINEAR, ARM_POS_LINEAR),
};

const CACHE = new Map();

export function lookupTable(name) {
  const key = ANCHORS[name] || DIVERGING[name] ? name : 'viridis';
  if (!CACHE.has(key)) {
    CACHE.set(key, DIVERGING[key] ? DIVERGING[key]() : buildTable(ANCHORS[key]));
  }
  return CACHE.get(key);
}

/** WCAG relative luminance of an sRGB triple (0-255). */
export function luminance([r, g, b]) {
  const lin = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio of two sRGB triples. */
export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * CSS colour stops for the ECharts visualMap legend.
 *
 * `alphaAt(t)`, given, returns the opacity at ramp position t in [0, 1]; a stop
 * below 1 is emitted as rgba so the legend can show the same fade to
 * transparent that the raster draws at its floor. ECharts interpolates the
 * alpha between rgba stops (measured on the vendored 5.5.1 bundle: the SVG
 * gradient carries `stop-opacity` from 0 to 0.99 across the bottom stops).
 * Without it the output is the plain rgb list it always was.
 */
export function colorStops(name, count = 12, alphaAt = null) {
  const table = lookupTable(name);
  const stops = [];
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    const index = Math.round(t * 255) * 3;
    const rgb = `${table[index]},${table[index + 1]},${table[index + 2]}`;
    const alpha = alphaAt ? alphaAt(t) : 1;
    stops.push(Number.isFinite(alpha) && alpha < 1
      ? `rgba(${rgb},${Math.max(0, alpha).toFixed(3)})`
      : `rgb(${rgb})`);
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

/** The sequential ramps the colour-map control offers. */
export const SEQUENTIAL_PALETTES = Object.keys(ANCHORS);
export const PALETTES = SEQUENTIAL_PALETTES;

/** The diverging ramps: print, and the folded screen arms (signed log / linear). */
export const DIVERGING_PALETTES = Object.keys(DIVERGING);
export const PUOR_ANCHORS = PUOR;
export const SCREEN_CARD = CARD;
