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
 *
 * ## The light screen: PuOr in its standard direction, re-anchored on white
 *
 * On the light theme's white card (#ffffff) the failure is the mirror image:
 * PuOr's light centre vanishes (#f7f7f7 1.07:1, #fee0b6 1.27:1, #d8daeb
 * 1.39:1) and its dark extremes are the colours that show (#7f3b08 8.30:1,
 * #2d004b 17.31:1). So the light arms keep PuOr's standard order, dark
 * extremes outermost, and are folded the same way: each arm runs from the
 * card outwards through PuOr's own colours, darkness rising with |value| and
 * hue alone giving the sign. `puor_light` (signed log) and `puor_light_linear`
 * (raw Shap-CAM and the correlation matrices) are measured against white in
 * WCAG contrast and placed by CIE L*, as the dark arms are; the numbers are
 * in the comment above their anchors. The standard table `puor` stays print's.
 *
 * ## The light screen's sequential ramps: white-grounded, not inverted
 *
 * Viridis, Cividis, Plasma and Turbo were made for a dark ground or for paper,
 * and none can be turned or cut into a good ramp on the light card. Viridis
 * and Plasma end in a yellow the white card swallows (1.26:1 and 1.15:1), so a
 * Viridis reversed onto white faded in through yellow and chartreuse and
 * ringed every shower with them. Reversed Cividis ran from khaki through a
 * muddy grey. Turbo's only long stretch at 3:1 on white is its orange-to-red
 * end, a quarter of the ramp. So on the light screen each colour-map slot
 * draws a ramp made for white (`scale.js` THEME.sequentialPalettes; Martin's
 * directive of 2026-10-30). Each runs from a pale tint at the display floor to
 * a deep tone at the peak, so contrast with the card rises with the value and a
 * continuous raster spans the whole ramp, fading into the card:
 *
 * - `viridis_light`: aqua, emerald-teal, azure, indigo, from ColorBrewer
 *   GnBu/YlGnBu, without yellow (L* 95.8 to 13.4).
 * - `cividis_light`: ice-azure to deep navy from ColorBrewer Blues/PuBu, one
 *   hue, so its order survives every colour-vision deficiency (L* 95.5 to 7.6).
 * - `plasma_light`: apricot, coral-red, plum from ColorBrewer OrRd/RdPu, a warm
 *   thermal ramp with no lemon-yellow end (L* 95.4 to 12.7).
 * - `turbo_light`: ice, pale sky, cerulean, emerald, amber, vermilion, crimson,
 *   garnet, ColorBrewer colours, keeping Turbo's whole cool-to-hot detail.
 *   Like Turbo its lightness is not monotone (it rises at the amber, L* 77)
 *   and its green and its orange-reds sit near one lightness, so it is offered
 *   for detail, never as the default and never as colour-vision-safe. Its peak,
 *   #67001f, is 13.2:1 on white. The ice #ebf3fb (L* 95.5, the Cividis slot's
 *   floor) leads it in: from pale sky it reached cerulean (L* 58) within a
 *   sixth of the ramp, so under the light transfer (`scale.js`
 *   LIGHT_FIELD_GAMMA) its bottom decade fell to L* 65 where the other slots'
 *   stay above 88; with it, Turbo's stays above 90 too.
 *
 * The anchors are spaced evenly and interpolated in CIELAB, so the steps
 * between table entries are close to even in perceived colour (at most
 * ΔE 1.3-2.5 per entry); the three monotone ramps lose lightness at every
 * entry. One anchor of the directive was left out after measuring it: an
 * emerald #2ca25f (L* 59.2) between #66c2a4 and #1d91c0 (L* 56.4) sat at
 * nearly one lightness with its neighbour, so `viridis_light` either rose in
 * lightness there or, spaced by lightness, swung from green to blue within
 * nine entries, which reads as a contour. Without it the ramp falls at every
 * entry and keeps its emerald-teal through #66c2a4.
 *
 * Where these ramps meet the 3:1 rule: a continuous raster spans each in
 * full, through the light transfer on a log scale (t^1.85, its bottom 0.8
 * decade fading into the card; `scale.js` LIGHT_FIELD_GAMMA), because a raster
 * bin sits among its neighbours and the faint halo is meant to be faint. A mark
 * that stands alone on the card - a series line, a 3-D cube, a 2-D histogram
 * cell, a surrogate-tree leaf - keeps the ramp's run at 3:1 or more, as on the
 * dark card (`chart_panel.legibleRamp`).
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

const WHITE = [255, 255, 255];      // the light card #ffffff
const LIGHT_BORDER = [208, 215, 222]; // #d0d7de

/* The light screen's arms, from zero outwards: [arm position p, rgb], measured
 * against the white card (WCAG contrast, CIE L* from the same luminance).
 *
 * Both arms of each ramp follow one L* line, so equal |value| reads equally
 * dark whatever its sign. Three of the anchors are not ColorBrewer classes
 * but points on PuOr's own path between two of them, chosen by L*:
 *
 * - #d37610 (3.30:1, L* 58.8), 29% of the way from #e08214 to #b35806, and
 *   #9287b9 (3.29:1, L* 58.9), 64% from #b2abd2 to #8073ac: each arm's first
 *   colour at 3:1 with the dark arms' margin (#b35806 is 3.33:1 on #1c2128),
 *   at one lightness on both arms. The class colours past 3:1, #b35806
 *   (4.87:1) and #8073ac (4.23:1), would have spent all but L* 15 of the arm
 *   on the faded bottom half decade.
 * - #603b91 (8.29:1, L* 33.3), 73% from #8073ac to #542788: the purple arm's
 *   end, at the lightness of the orange arm's #7f3b08 (8.30:1, L* 33.3).
 *   PuOr has no orange as dark as #542788 (10.38:1, L* 27.1) or #2d004b
 *   (17.31:1, L* 9.5), so a purple arm run to either would draw a positive
 *   value darker, and so stronger, than a negative one of the same size.
 *
 * Signed log (`puor_light`). Each arm starts at the card (p = 0) and reaches
 * its 3:1 colour at p = 1/6, 10^-2.5 of the peak on the three-decade ramp,
 * where the taper of `decode.codeTable` turns opaque; the faded bottom half
 * decade climbs through PuOr's light classes on the L* line from the card's
 * 100 to 58.9 (orange #fee0b6 L* 90.7, #fdb863 79.7, #e08214 63.2; purple
 * #d8daeb 87.4, #b2abd2 71.7), and the opaque arm runs on one line from 58.9
 * to 33.3 (#b35806 L* 47.7, #8073ac 51.6). Every colour from p = 1/6 out is
 * 3.29:1 or more, and code 107, the first at 10^-2.5 (p = 20/127), 3.05:1.
 *
 * Linear (`puor_light_linear`). Zero is the light border #d0d7de (L* 85.7,
 * 1.45:1 against the card, mirroring #30363d's 1.33:1 on the dark one), so a
 * populated bin with zero attribution, or r = 0, stays distinct from an empty
 * one. Both arms follow one L* line from it to the shared dark end at L* 33.3
 * (#fdb863 79.7, #b2abd2 71.7, #e08214 63.2, #8073ac 51.6, #b35806 47.7). The
 * classes lighter than the zero, #fee0b6 and #d8daeb, are left out, so
 * lightness falls from the zero on both arms; 3:1 is crossed at |v| ≈ 0.46.
 *
 * Measured on the 256-entry tables: L* never rises outwards on either arm
 * (the 8-bit table repeats a colour where the purple arm's last segment
 * changes by less than one code value per step), and the contrasts of
 * mirrored codes agree within 1.4% on the signed log and 1.8% on the linear
 * ramp, against the dark design's 15% and 9%. */
const ARM_NEG_LIGHT = [[0, WHITE], [0.038, [254, 224, 182]], [0.082, [253, 184, 99]],
  [0.149, [224, 130, 20]], [1 / 6, [211, 118, 16]], [0.529, [179, 88, 6]], [1, [127, 59, 8]]];
const ARM_POS_LIGHT = [[0, WHITE], [0.051, [216, 218, 235]], [0.115, [178, 171, 210]],
  [1 / 6, [146, 135, 185]], [0.402, [128, 115, 172]], [1, [96, 59, 145]]];
const ARM_NEG_LIGHT_LINEAR = [[0, LIGHT_BORDER], [0.114, [253, 184, 99]], [0.428, [224, 130, 20]],
  [0.724, [179, 88, 6]], [1, [127, 59, 8]]];
const ARM_POS_LIGHT_LINEAR = [[0, LIGHT_BORDER], [0.266, [178, 171, 210]], [0.649, [128, 115, 172]],
  [1, [96, 59, 145]]];

/* The light screen's sequential ramps, from the display floor (a pale tint) to
 * the peak (a deep tone): ColorBrewer colours, spaced evenly and interpolated
 * in CIELAB (`buildLabTable`). See the header for why and what was measured. */
const LIGHT_ANCHORS = {
  viridis_light: [[232, 246, 243], [178, 226, 226], [102, 194, 164], [29, 145, 192], [34, 94, 168], [8, 29, 88]],
  cividis_light: [[235, 243, 251], [198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 81, 156], [8, 48, 107],
    [4, 22, 51]],
  plasma_light: [[255, 240, 217], [253, 212, 158], [252, 141, 89], [227, 74, 51], [179, 0, 0], [122, 1, 119],
    [63, 0, 71]],
  turbo_light: [[235, 243, 251], [209, 229, 240], [67, 147, 195], [44, 162, 95], [253, 174, 97], [244, 109, 67],
    [215, 48, 39], [103, 0, 31]],
};

/* CIELAB (D65) of an sRGB triple, and back, clamped to the sRGB gamut. */
const D65 = [0.95047, 1, 1.08883];
const toLinear = (c) => { const v = c / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const toGamma = (c) => 255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/** CIELAB [L*, a*, b*] of an sRGB triple (0-255), D65. */
export function toLab([R, G, B]) {
  const [r, g, b] = [R, G, B].map(toLinear);
  const xyz = [0.4124 * r + 0.3576 * g + 0.1805 * b, 0.2126 * r + 0.7152 * g + 0.0722 * b,
    0.0193 * r + 0.1192 * g + 0.9505 * b];
  const [fx, fy, fz] = xyz.map((v, i) => {
    const t = v / D65[i];
    return t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
  });
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function fromLab([L, a, b]) {
  const fy = (L + 16) / 116;
  const [X, Y, Z] = [fy + a / 500, fy, fy - b / 200].map((f, i) => (f ** 3 > 0.008856 ? f ** 3 : (f - 16 / 116) / 7.787) * D65[i]);
  return [3.2406 * X - 1.5372 * Y - 0.4986 * Z, -0.9689 * X + 1.8758 * Y + 0.0415 * Z,
    0.0557 * X - 0.204 * Y + 1.057 * Z].map((c) => toGamma(Math.max(0, Math.min(1, c))));
}

/** A 256-entry table through evenly spaced anchors, interpolated in CIELAB. */
function buildLabTable(anchors) {
  const labs = anchors.map(toLab);
  const table = new Uint8ClampedArray(256 * 3);
  const segments = anchors.length - 1;
  for (let i = 0; i < 256; i += 1) {
    const t = (i / 255) * segments;
    const index = Math.min(segments - 1, Math.floor(t));
    const frac = t - index;
    const a = labs[index];
    const b = labs[index + 1];
    table.set(fromLab([0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * frac)), i * 3);
  }
  return table;
}

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
  puor_light: () => buildFolded(ARM_NEG_LIGHT, ARM_POS_LIGHT),
  puor_light_linear: () => buildFolded(ARM_NEG_LIGHT_LINEAR, ARM_POS_LIGHT_LINEAR),
};

const CACHE = new Map();

export function lookupTable(name) {
  const key = ANCHORS[name] || DIVERGING[name] || LIGHT_ANCHORS[name] ? name : 'viridis';
  if (!CACHE.has(key)) {
    let table;
    if (DIVERGING[key]) table = DIVERGING[key]();
    else if (LIGHT_ANCHORS[key]) table = buildLabTable(LIGHT_ANCHORS[key]);
    else table = buildTable(ANCHORS[key]);
    CACHE.set(key, table);
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

/** The light screen's ramps, by the slot they draw for (THEME.sequentialPalettes in scale.js). */
export const LIGHT_SEQUENTIAL = Object.freeze({
  viridis: 'viridis_light', cividis: 'cividis_light', plasma: 'plasma_light', turbo: 'turbo_light',
});

/** Their anchors, floor first, as '#rrggbb', for the tests and the article to measure. */
export const LIGHT_RAMP_ANCHORS = Object.freeze(Object.fromEntries(Object.entries(LIGHT_ANCHORS).map(
  ([name, anchors]) => [name, Object.freeze(anchors.map((c) => `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`))],
)));

/** The diverging ramps: print, and the folded screen arms (signed log / linear) of the dark and light cards. */
export const DIVERGING_PALETTES = Object.keys(DIVERGING);

const frozenArm = (arm) => Object.freeze(arm.map(([p, rgb]) => Object.freeze([p, Object.freeze([...rgb])])));

/** The light arms' anchors, [p, rgb] from zero outwards, for the tests and the article to measure. */
export const PUOR_LIGHT_ARMS = Object.freeze({
  puor_light: Object.freeze({ neg: frozenArm(ARM_NEG_LIGHT), pos: frozenArm(ARM_POS_LIGHT) }),
  puor_light_linear: Object.freeze({ neg: frozenArm(ARM_NEG_LIGHT_LINEAR), pos: frozenArm(ARM_POS_LIGHT_LINEAR) }),
});
export const PUOR_ANCHORS = PUOR;
/** The dark screen card #1c2128, which the dark arms are measured against. */
export const SCREEN_CARD = CARD;
/** The light screen card #ffffff, which the light arms are measured against. */
export const LIGHT_CARD = WHITE;

/* ## Nominal categories: qualitative palettes
 *
 * A nominal category - a particle species, a network - takes a qualitative
 * palette, never a sequential ramp, whose lightness order would claim an order
 * the categories do not have. These are kept apart from `ANCHORS` and
 * `DIVERGING`: they are not colormaps, never interpolated, and never a value
 * of the colour-map control.
 *
 * Every colour is a ColorBrewer qualitative colour (CLAUDE.md section 2), and
 * every one was measured before adoption, as tests/test_js_voxels.py measures
 * it again: WCAG contrast against the surface it is drawn on (the #1c2128
 * card on screen, white paper in print), and the CIEDE2000 distance between
 * every pair under normal vision and under simulated deuteranopia and
 * protanopia (Machado, Oliveira & Fernandes 2009, severity 1, in linear RGB).
 *
 * - `set2` / `dark2` are ColorBrewer's own colours, for a few series (the
 *   networks and the XGBoost regressor of the performance card). ColorBrewer
 *   rates them colourblind-safe at three classes; the schemes' own fourth
 *   colours fail here - Set2's #e78ac3 sits ΔE00 1.6 from #8da0cb under
 *   protanopia, Dark2's #e7298a 4.9 from #d95f02 under deuteranopia - so the
 *   fourth slot takes the scheme's best later colour instead: Set2's yellow
 *   #ffd92f (worst pair of the four ΔE00 14.0, deuteranopia; 11.7:1 on the
 *   card) and Dark2's grey #666666 (14.6; 5.7:1 on white). The remaining
 *   colours follow in the schemes' order, unchecked: past four, Dark2's green
 *   and yellow fall below 3:1 on white (2.98 and 2.06), so `qualitativeStops`
 *   refuses more than `QUALITATIVE_CHECKED` colours of a palette.
 * - `species` / `species_print` colour the eight stable species codes of the
 *   3-D displays (e⁻, e⁺, γ, n, p, π⁺, π⁻, other; query/voxel_event.py), the
 *   last slot the neutral grey of "other". No single ColorBrewer scheme keeps
 *   eight colours apart for a colour-vision-deficient reader, so these are
 *   chosen from the union of the qualitative schemes by the largest worst-pair
 *   distance over the three visions. Screen (every colour at least 3.5:1 on
 *   the card): worst pair e⁺ #ff7f00 against p #bf5b17, ΔE00 15.6 under
 *   deuteranopia; the design's Set2-without-yellow measured 1.6. Print (3:1
 *   on white leaves 19 ColorBrewer colours): worst pair e⁺ #d95f02 against
 *   π⁺ #33a02c, ΔE00 6.0 under deuteranopia - weak, and stated so; the 3-D
 *   cards that draw species are never exported, so no figure carries it.
 */
export const QUALITATIVE = Object.freeze({
  set2: Object.freeze(['#66c2a5', '#fc8d62', '#8da0cb', '#ffd92f', '#e78ac3', '#a6d854', '#e5c494', '#b3b3b3']),
  dark2: Object.freeze(['#1b9e77', '#d95f02', '#7570b3', '#666666', '#e7298a', '#66a61e', '#e6ab02', '#a6761d']),
  // e⁻ Set3, e⁺ Set1, γ Set1, n Dark2, p Accent, π⁺ Dark2, π⁻ Pastel1, other Pastel2.
  species: Object.freeze(['#80b1d3', '#ff7f00', '#ffff33', '#7570b3', '#bf5b17', '#1b9e77', '#ffffcc', '#cccccc']),
  // e⁻ Paired, e⁺ Dark2, γ Paired, n Set1, p Dark2, π⁺ Paired, π⁻ Set3, other Dark2.
  species_print: Object.freeze(['#1f78b4', '#d95f02', '#6a3d9a', '#a65628', '#1b9e77', '#33a02c', '#bc80bd', '#666666']),
});

/** How many leading colours of each qualitative palette pass the contrast and CVD checks. */
export const QUALITATIVE_CHECKED = Object.freeze({ set2: 4, dark2: 4, species: 8, species_print: 8 });

/**
 * The first `count` colours of a qualitative palette, as CSS hex strings.
 *
 * Throws for an unknown palette or for more colours than were checked
 * (`QUALITATIVE_CHECKED`): a colour nobody measured must not reach a chart.
 */
export function qualitativeStops(name, count) {
  const colours = QUALITATIVE[name];
  if (!colours) throw new Error(`Unknown qualitative palette ${name}.`);
  const n = Math.max(0, Math.floor(count));
  if (n > QUALITATIVE_CHECKED[name]) {
    throw new Error(`Only the first ${QUALITATIVE_CHECKED[name]} colours of ${name} are checked for contrast and colour-vision deficiency; ${n} were asked for.`);
  }
  return colours.slice(0, n);
}
