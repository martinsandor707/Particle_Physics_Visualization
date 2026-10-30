/* Number formatting and the ECharts visualMap configuration.
 *
 * The legend is always labelled in physical units - GeV, or a dimensionless
 * attention weight - never in colour codes. A reader should be able to take a
 * number off the legend and quote it.
 */

import { contrast, lookupTable } from './palette.js';
import { fitsWidth, measureText } from './textfit.js';
// A cycle (chart_panel.js imports this module), safe because neither module
// calls the other while it is being evaluated: both use these at call time.
import { isPrintTheme, legibleRamp } from './panels/chart_panel.js';
import { MINUS, formatSigned, typographic } from './format.js';

export { MINUS, formatSigned, typographic };

/* The screen style. Mirrors css/tokens.css, which ECharts cannot read.
 *
 * Typography and stroke widths are tokens rather than literals because the
 * publication exporter swaps this whole object out: a figure printed at 85 mm
 * needs 12 px type to clear the 9 pt floor, so a hardcoded `fontSize: 10` would
 * silently under-size every label in the exported figure. See
 * `export/tokens.js` for the unit argument. */
const SCREEN = {
  text: '#e6edf3',
  muted: '#8b949e',
  border: '#30363d',
  grid: '#30363d',
  canvas: '#0d1117',
  card: '#1c2128',
  accent: '#58a6ff',
  warn: '#d29922',
  showerA: '#f778ba',
  showerB: '#58a6ff',
  labelBg: 'rgba(13,17,23,0.88)',
  // Transparent on screen, so the .card background shows through. A print
  // figure must not carry an alpha channel, which PDF renderers composite
  // unpredictably, so the export swaps this for opaque white.
  chartBackground: 'transparent',

  // Single-quoted family names: see the note in export/tokens.js. Harmless on
  // canvas, required the moment a stack reaches an SVG style attribute.
  fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
  fontMono: "'JetBrains Mono', 'SF Mono', ui-monospace, monospace",
  fontSmall: 9,
  fontLabel: 10,
  fontName: 10,
  fontTip: 11,

  lineAxis: 1,
  lineGrid: 1,
  gridOpacity: 0.35,
  /* Whether an axis line may sit at the data origin instead of at the edge of
   * the plot.
   *
   * ECharts anchors a value axis to zero when the opposite axis spans it, which
   * on the XY panel draws the y axis as a rule up the middle of the detector -
   * fine as a reference line on screen, wrong as a figure spine, where the
   * frame is what bounds the plotted region. */
  axisOnZero: true,
  // A print figure is narrower than the on-screen panel, so a marker of fixed
  // pixel size occupies a larger share of it. Scaled down so the centroids stay
  // markers rather than becoming blobs over the shower they locate.
  markerScale: 1,

  envelopeAlpha: 0.07,
  bandAlpha: 0.18,
  stripAlpha: 0.045,

  /* Canonical-frame overlay chrome.
   *
   * The separation rule between the anchors is a reference line, not data, so
   * it is drawn as a faint 1 px dash that the shower cores show through. The
   * anchors are open outlines at 0.75 so they locate the core without
   * occluding it; a filled 15 px marker used to hide the brightest bins. */
  separationRule: 'rgba(255,255,255,0.4)',
  anchorOpacity: 0.75,
  /* Decades over which the canonical density ramp fades to transparent above
   * its 10⁻³ floor. A hard floor draws a rim: the dark end of Viridis against
   * the #1c2128 card is only 1.07:1 in WCAG contrast but ΔE76 ≈ 49 in colour,
   * so a sharp edge reads as a violet outline around the whole halo. Tapering
   * the bottom half decade removes the rim. Print sets 0: a hard contour, which
   * the figure caption names as the display floor. */
  floorFadeDecades: 0.5,
  /* The diverging ramps a signed quantity is painted with (palette.js): the
   * folded PuOr on the dark screen - signed log, and the linear raw Shap-CAM
   * whose zero is border grey - and standard PuOr in print. */
  divergingPalette: 'puor_screen',
  divergingLinearPalette: 'puor_screen_linear',
  /* The hatch of a correlation cell that pairs a circular variable: chrome,
   * not ink, at the muted grey (5.3:1 on the card). Print takes #6b7280. */
  hatch: '#8b949e',

  categorical: { min: 0.25, max: 1.0 },
  rampOrient: 'vertical',
  // A scrolling legend is right on screen, where the arrows are clickable and
  // the panel is wide. Printed, an entry behind a scroll arrow is an entry that
  // is not there, so the export wraps instead and pays for it in height.
  legendWrap: false,

  /* The medium, and the tokens that differ by the card rather than by it.
   *
   * `medium` is what `chart_panel.isPrintTheme` reads: print is a medium, not
   * a colour, and a white light-screen card must not be taken for paper. The
   * qualitative palettes are chosen per card (Set2's yellow is 11.7:1 here and
   * 1.38:1 on white), and so is the tooltip's ground. */
  medium: 'screen',
  qualitativePalette: 'set2',
  speciesPalette: 'species',
  tooltipBackground: 'rgba(22,27,34,0.95)',
};

/* The light screen style: the light block of css/tokens.css, which ECharts
 * cannot read either. Exactly SCREEN's keys, as a flat literal a Python test
 * parses (tests/test_export_assets.py); the typography, strokes and layout
 * are SCREEN's, and only what depends on the card changes.
 *
 * - Ink is measured against the white card: text 17.74:1, muted 6.11:1,
 *   accent and shower B 6.19:1, shower A 7.24:1, warn 5.93:1 (the CSS light
 *   block's values). The border and grid #d0d7de are chrome at 1.45:1, as
 *   #30363d is 1.33:1 on the dark card.
 * - The washes take print's white-paper weights: a 0.07 wash that reads on the
 *   dark card is invisible on white.
 * - The separation rule is the dark ink at 0.4 where the dark screen draws
 *   white at 0.4; the floor still fades over half a decade.
 * - The diverging ramps are PuOr's light arms (palette.js), the hatch the
 *   print grey #6b7280 (4.83:1).
 * - `categorical` is the reversed sub-range {0.75, 0}: on white the dark end
 *   of a ramp is the visible one, so a series index runs from the card
 *   outwards, as {0.25, 1} does on the dark card (whose bottom is 2.1:1, as
 *   Viridis 0.75 is on white). `seriesStops` narrows it to the 3:1 run.
 * - Dark2 for the networks and species_print for the species, the two
 *   qualitative palettes measured on white (palette.js). */
const SCREEN_LIGHT = {
  text: '#111827',
  muted: '#59636e',
  border: '#d0d7de',
  grid: '#d0d7de',
  canvas: '#f6f8fa',
  card: '#ffffff',
  accent: '#0b5fbe',
  warn: '#8a5a00',
  showerA: '#a3186b',
  showerB: '#0b5fbe',
  labelBg: 'rgba(255,255,255,0.92)',
  chartBackground: 'transparent',

  fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
  fontMono: "'JetBrains Mono', 'SF Mono', ui-monospace, monospace",
  fontSmall: 9,
  fontLabel: 10,
  fontName: 10,
  fontTip: 11,

  lineAxis: 1,
  lineGrid: 1,
  gridOpacity: 0.35,
  axisOnZero: true,
  markerScale: 1,

  envelopeAlpha: 0.18,
  bandAlpha: 0.22,
  stripAlpha: 0.07,

  // Translucent ink, as the dark rule is translucent white: 3.96:1 composited
  // on the card at 0.55, beside the dark rule's 3.74:1 (0.4 gave only 2.54:1).
  separationRule: 'rgba(17,24,39,0.55)',
  anchorOpacity: 0.75,
  floorFadeDecades: 0.5,
  divergingPalette: 'puor_light',
  divergingLinearPalette: 'puor_light_linear',
  hatch: '#6b7280',

  categorical: { min: 0.75, max: 0.0 },
  rampOrient: 'vertical',
  legendWrap: false,

  medium: 'screen',
  qualitativePalette: 'dark2',
  speciesPalette: 'species_print',
  tooltipBackground: 'rgba(255,255,255,0.97)',
};

/** The two screen styles by name, frozen: the dark one is the cold-boot default. */
export const SCREEN_THEMES = Object.freeze({
  dark: Object.freeze({ ...SCREEN }),
  light: Object.freeze({ ...SCREEN_LIGHT }),
});

/** The screen style in force between exports: 'dark' or 'light' (`setScreenTheme`). */
let activeScreen = 'dark';

/**
 * The active style, as a mutable singleton.
 *
 * Every chart option in this codebase reads `THEME.x` at build time, in some
 * forty places. Making the object mutable rather than replacing the binding
 * means the publication exporter can swap the whole style for the duration of
 * one synchronous render without touching a single call site. Nothing else may
 * mutate it - `setScreenTheme()` and `restoreScreenTheme()` are the only
 * sanctioned ways to change it. No module reads it at import time, so a theme
 * set before the first paint is the one every panel is built in.
 */
export const THEME = { ...SCREEN };

/** The dark screen style (methodology/constants.js pins its floor fade). */
export const SCREEN_THEME = Object.freeze({ ...SCREEN });

/**
 * Make `name` the screen style: 'light', or else 'dark'. THEME is emptied and
 * refilled in place, so every holder of the object sees the change, and the
 * style is recorded as the one `restoreScreenTheme` returns to. Returns the
 * name applied. The caller repaints; nothing here touches a chart.
 */
export function setScreenTheme(name) {
  activeScreen = name === 'light' ? 'light' : 'dark';
  restoreScreenTheme();
  return activeScreen;
}

/** The active screen style's name, 'dark' or 'light'. */
export function screenTheme() {
  return activeScreen;
}

/** Put the active screen style back: what the exporter calls after a print render. */
export function restoreScreenTheme() {
  for (const key of Object.keys(THEME)) delete THEME[key];
  Object.assign(THEME, SCREEN_THEMES[activeScreen]);
}

/**
 * Plot-area insets, derived from the active type size.
 *
 * These used to be the literals {left: 52, right: 74, top: 12, bottom: 40},
 * which are correct only at the screen's 10 px labels. At the 12 px print size
 * they leave the axis names clipped, and on a 321 px single-column figure the
 * old 74 px right inset - reserved for a vertical colour bar - would have eaten
 * a quarter of the canvas. Both now follow the font.
 */
export function axisPadding({ ramp = false, wideRamp = false } = {}) {
  const f = THEME.fontLabel;
  const horizontalRamp = ramp && THEME.rampOrient === 'horizontal';
  // A vertical ramp titled "Average hit density (a.u.)" is about 13 label
  // heights wide; the GeV ramp's exponent labels fit in 7.4.
  const rampInset = wideRamp ? 13.5 * f : 7.4 * f;
  return {
    nameGap: 2.6 * f,
    left: 5.2 * f,
    right: ramp && !horizontalRamp ? rampInset : 1.6 * f,
    top: 1.2 * f,
    bottom: 2.6 * f + 1.4 * f + (horizontalRamp ? 3.4 * f : 0),
  };
}

/** Compact scientific notation, e.g. 3.4e-5. */
export function formatSci(value, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value === 0) return '0';
  const exponent = Math.floor(Math.log10(Math.abs(value)));
  if (exponent >= -3 && exponent < 4) {
    return typographic(value.toFixed(Math.max(0, digits - 1 - exponent)));
  }
  return typographic(value.toExponential(digits));
}

export function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return typographic(value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }));
}

export function formatInt(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return typographic(Math.round(value).toLocaleString());
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return typographic(`${(value * 100).toFixed(digits)}%`);
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value < 10 && index > 0 ? 1 : 0)} ${units[index]}`;
}

/**
 * visualMap for one panel.
 *
 * For a logarithmic density scale the endpoints are exponents, so the formatter
 * renders them as powers of ten in GeV. For Grad-CAM the scale is linear and
 * fixed to [0, 1], which is what keeps attention maps comparable between
 * selections - the entire reason for looking at them.
 *
 * `seriesIndex` names the raster, which is always series 0. Without it a
 * visualMap colours *every* series by its data value, and the lab frame's
 * pink and blue centroid diamonds came out in whatever ramp colour their
 * coordinates happened to map to (measured on the vendored bundle: an anchor
 * fill of rgb(253,231,37), the top of Viridis).
 *
 * On a relative (a.u.) log ramp the legend mirrors the raster's floor taper
 * (`decode.codeTable`): its bottom stops fade to transparent over the same
 * `THEME.floorFadeDecades` above the same floor, and the bottom label says the
 * floor is not drawn. With the print value 0 the stops stay opaque, matching
 * the hard contour the figure caption names.
 */
export function visualMap(scale, palette, {
  bottomInset = 0, seriesIndex = 0, legible = true, signed = false,
} = {}) {
  // The table the colours are drawn from: the legible run on screen (above),
  // the same remapping `decode.codeTable` paints through.
  const table = rampTable(scale, palette, { legible, signed });
  const horizontal = THEME.rampOrient === 'horizontal';
  const place = horizontal
    /* Below the x-axis title, where a figure has height to spare, rather than
     * beside the plot, where a single-column figure has none.
     *
     * `bottomInset` is the caption's height. Without it the ramp would anchor
     * to the foot of the whole figure - which, once a caption was added below
     * the plot, meant anchoring on top of the caption's last lines. */
    ? {
      orient: 'horizontal',
      left: 'center',
      bottom: bottomInset + 2,
      itemWidth: 14,
      itemHeight: 90,
    }
    : { orient: 'vertical', right: 6, top: 'middle', itemWidth: 10, itemHeight: 140 };
  const textStyle = {
    color: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
  };
  const fade = THEME.floorFadeDecades;
  const floorExp = floorExponent(scale);
  const title = scale.unit === 'a.u.' && !horizontal ? `${rampTitleText(scale)}\n` : '';

  if (scale.scale === 'signed_log10') {
    /* The legend runs in signed position u in [-1, 1]: |u| is the position on
     * the three-decade log ramp of |value| / peak, the sign is the sign. An
     * odd stop count puts one stop exactly on zero, inside the |v| < 10^-3
     * band the raster leaves transparent. */
    const span = (scale.vmax - floorExp) || 1;
    const alphaAt = (t) => {
      const e = floorExp + Math.abs(2 * t - 1) * span;
      if (Math.abs(2 * t - 1) < 1e-9) return 0;
      return Number.isFinite(fade) && fade > 0 ? clip01((e - floorExp) / fade) : 1;
    };
    return {
      type: 'continuous', seriesIndex, min: -1, max: 1, calculable: false, ...place,
      precision: 2,
      text: [`${title}+10⁰ a.u.`, `${MINUS}10⁰ a.u.`],
      textGap: 6, textStyle,
      inRange: { color: tableStops(table, 49, alphaAt) },
      outOfRange: { color: ['rgba(0,0,0,0)'] },
      formatter: (u) => {
        const value = Number(u);
        if (Math.abs(value) < 1e-9) return `±${floorLabel(scale)} a.u.`;
        const e = floorExp + Math.abs(value) * span;
        return `${value < 0 ? MINUS : '+'}10${superscript(e.toFixed(1))} a.u.`;
      },
    };
  }

  if (isDiverging(scale)) {
    // Linear and symmetric about zero: nothing clipped, the ends are +-1.
    return {
      type: 'continuous', seriesIndex, min: scale.vmin, max: scale.vmax, calculable: false,
      ...place, precision: 2,
      text: [formatSigned(scale.vmax, 2, { plus: true }), formatSigned(scale.vmin, 2, { plus: true })],
      textGap: 6, textStyle,
      // A legible linear ramp (the 3-D cubes) samples its folded arms apart, so
      // the two 3:1 starts meet at the zero mark instead of blending over it.
      inRange: { color: signed && legible && !isPrintTheme()
        ? tableStops(table, 24, null, { arms: true }) : tableStops(table, 13) },
      formatter: (value) => formatSigned(Number(value), 2, { plus: true }),
    };
  }

  const isLog = scale.scale === 'log10';
  // A relative (a.u.) ramp is dimensionless: its ends are derived from the
  // scale's own bounds, which reach above 10^0 when a selection is brighter
  // than the dataset reference it is drawn against.
  const relative = scale.unit === 'a.u.';
  const unit = relative ? ' a.u.' : (isLog ? ` ${unitSuffix(scale.unit)}` : '');
  const label = (value) => (isLog
    ? `10${superscript(Number(value).toFixed(1))}`
    : typographic(Number(value).toFixed(2)));

  // The fade, when this ramp has one: alpha rises linearly in log density
  // from 0 at the floor to 1 a `fade` decades above it. 48 stops put about
  // eight inside the bottom half decade of a three-decade ramp, so the legend
  // gradient follows the raster's taper rather than a single coarse step.
  const tapered = fadesAtFloor(scale) && Number.isFinite(fade) && fade > 0
    && Number.isFinite(floorExp) && Number.isFinite(scale.vmin) && Number.isFinite(scale.vmax);
  const stops = tapered
    ? tableStops(table, 48, (t) => clip01(
      (scale.vmin + t * (scale.vmax - scale.vmin) - floorExp) / fade,
    ))
    : tableStops(table);
  // Two lines, not one: a one-line "10⁻³ a.u. — fades to not drawn" would
  // widen the vertical ramp group past the 13.5-label-height right inset.
  const bottom = tapered
    ? `${label(scale.vmin)}${unit} —\nfades to not drawn`
    : `${label(scale.vmin)}${unit}`;

  return {
    type: 'continuous',
    seriesIndex,
    min: scale.vmin,
    max: scale.vmax,
    calculable: false,
    ...place,
    precision: 2,
    // The endpoints are always labelled. A colour ramp without numbers cannot
    // be read off, and the units are what make the panel quotable: decade
    // exponents in GeV for density, a plain 0-1 weight for attention.
    text: [
      `${relative && !horizontal ? title : ''}${label(scale.vmax)}${unit}`,
      bottom,
    ],
    textGap: 6,
    textStyle,
    inRange: { color: stops },
    // The continuous legend paints an out-of-range bar underneath the ramp,
    // grey (#aaa) by default. Opaque stops hide it; faded ones let it show as
    // a light patch where the card should be. It colours nothing else here:
    // the raster's renderItem never reads a visual colour.
    ...(tapered ? { outOfRange: { color: ['rgba(0,0,0,0)'] } } : {}),
    formatter: (value) => (isLog
      ? `${label(value)}${unit}`
      : typographic(Number(value).toFixed(2))),
  };
}

/**
 * How a physical unit is written beside a ramp label: the lab's summed energy
 * in GeV, the Event Inspector's areal density in GeV per mm², the 3-D event
 * view's volumetric density in GeV per mm³.
 */
export function unitSuffix(unit) {
  if (unit === 'GeV/mm^2') return 'GeV/mm²';
  if (unit === 'GeV/mm^2/event') return 'GeV/mm²/event';
  if (unit === 'GeV/mm^3') return 'GeV/mm³';
  return unit === 'GeV' || !unit ? 'GeV' : String(unit);
}

/** Whether a scale is signed and takes the diverging PuOr ramp. */
export function isDiverging(scale) {
  return scale?.diverging === true || scale?.scale === 'signed_log10';
}

/**
 * The palette a scale is painted with: the chosen sequential ramp, or - for a
 * signed quantity, whatever was chosen - the diverging PuOr of the active
 * theme (folded on screen, standard in print; palette.js).
 */
export function rampPalette(scale, chosen) {
  if (!isDiverging(scale)) return chosen;
  return scale.scale === 'signed_log10' ? THEME.divergingPalette : THEME.divergingLinearPalette;
}

/** Whether a ramp fades to transparent above a stated display floor. */
export function fadesAtFloor(scale) {
  return (scale?.scale === 'log10' || scale?.scale === 'signed_log10')
    && (scale.floor === 'transparent' || scale.unit === 'a.u.');
}

/* ------------------------------------------------------ legible ramps --
 *
 * Every on-screen sequential colour starts at the ramp's first colour with at
 * least 3:1 contrast against the card #1c2128 (Martin's decision D-2, CLAUDE.md
 * section 2: "nothing a reader is asked to see is drawn below 3:1"). Viridis'
 * own first colour #440154 is 1.06:1 there: a 3-D cube coded near the bottom
 * vanished while being drawn, and a raster's faint halo was painted in colours
 * the card swallows. The run is chart_panel.js `legibleRamp`'s measured one:
 * t = 0.376 to 1 on Viridis, and the longest 3:1 run on the other palettes.
 *
 * - A ramp without a floor taper (the Absolute GeV ramp, the event's areal and
 *   volumetric densities, Grad-CAM's [0, 1]) is drawn on that run alone: its
 *   lowest code, a "below the ramp floor" cell included, is 3:1.
 * - A relative ramp that fades to transparent above its floor places its
 *   first 3:1 colour at the taper's full-opacity point (10^−2.5 of the
 *   reference on the three-decade ramp), as the folded PuOr does: the bottom
 *   half decade climbs from the palette's first colour to that point while its
 *   alpha rises from 0, so every opaque bin is 3:1 and the fade still
 *   dissolves into the card.
 * - The signed log (folded PuOr) is legible by construction and unchanged.
 *   The raw Shap-CAM linear ramp keeps its border-grey zero on the 2-D
 *   rasters, where the number is in the readout; the 3-D cubes, which print no
 *   number, ask for `signed: true`, which starts each arm at its own first 3:1
 *   colour (#b35806-ish orange, #8073ac-ish purple), so a cube near zero is
 *   drawn in its sign's hue rather than not at all.
 * - Print keeps the full ramp: white paper shows Viridis' dark end best, and
 *   the export swaps the card for white (`isPrintTheme`).
 *
 * On the light screen's white card the same rule runs the other way ("contrast
 * rises with value", Martin's decision of 2026-10-30). The 3:1 run against
 * white is a ramp's dark end - Viridis 0 to 0.600 (#440154 to #22a784),
 * Cividis 0 to 0.698, Plasma 0 to 0.639, Turbo's longest run 0.749 to 1
 * (#f6691b to #7a0403) - and `legibleRamp` hands it over oriented from the card outwards,
 * `from` above `to`: the lowest value takes the run's first 3:1 colour and the
 * highest its darkest, so the ramp still gains contrast against its card as
 * the value grows, as it does on the dark one. A floor taper then climbs from
 * the palette's *outer* end - Viridis' yellow, the end beyond `from` - to
 * `from` while its alpha rises from 0, so lightness composited on the card
 * falls monotonically from the white card at the floor. Turbo's lightness is
 * not monotone, but its light run is, and it is drawn on that run alone: its
 * run already rises in contrast (orange to dark red), and the end beyond its
 * `from` is the dark blue, not a light one, so its taper fades #f6691b alone
 * rather than sweep the rainbow (see `rampTable`). The legend is the same
 * table, so its bottom is the faded light end and the label "fades to not
 * drawn" still describes it.
 */

/** The contrast every opaque on-screen ramp colour clears against the card. */
export const RAMP_CONTRAST = 3;

/** Where in a floor taper the first 3:1 colour is placed: its full-opacity point, less one code step. */
export const TAPER_LEGIBLE = 0.97;

/** First index of a folded table's arm, scanning out from the centre, that clears `floor` on the card. */
function armStart(table, card, negative, floor = RAMP_CONTRAST) {
  for (let k = 0; k < 128; k += 1) {
    const i = negative ? 127 - k : 128 + k;
    if (contrast([table[i * 3], table[i * 3 + 1], table[i * 3 + 2]], card) >= floor) return k / 127;
  }
  return 1;
}

/**
 * The ramp position `[from, to]` (0..1) the on-screen colours run over, and
 * where the taper ends: `{from, to, taperEnd}`, or null when the ramp is
 * drawn in full (print, a diverging ramp, the `legible: false` opt-out).
 * `from` is the colour of the lowest value: below `to` on the dark card,
 * above it on the light one (`legibleRamp`'s orientation, see above).
 * `taperEnd` is the position (0..1 of the ramp's value range) where the floor
 * taper reaches full opacity, 0 on an untapered ramp.
 */
export function legibleSpan(scale, palette, { legible = true, fadeDecades = THEME.floorFadeDecades } = {}) {
  if (!legible || isDiverging(scale) || isPrintTheme()) return null;
  const { from, to } = legibleRamp(palette);
  if (!(from > 0 || to < 1)) return null;
  let taperEnd = 0;
  const floorExp = floorExponent(scale);
  if (Number.isFinite(fadeDecades) && fadeDecades > 0 && fadesAtFloor(scale)
      && Number.isFinite(floorExp) && Number.isFinite(scale?.vmin) && Number.isFinite(scale?.vmax)
      && scale.vmax > scale.vmin) {
    // At TAPER_LEGIBLE of the fade rather than its very end: an 8-bit code's colour index rounds by
    // up to half a table step (1.2% of a half-decade fade on the three-decade ramp), so every bin
    // drawn at 99% opacity or more - an opaque cube - is past the first 3:1 colour after quantisation.
    taperEnd = Math.min(1, Math.max(0,
      (floorExp + TAPER_LEGIBLE * fadeDecades - scale.vmin) / (scale.vmax - scale.vmin)));
  }
  return { from, to, taperEnd };
}

/**
 * The 256-entry RGB table a scale's colours are drawn from on screen: the
 * palette's own `lookupTable`, re-indexed onto its legible run (see above).
 * `signed: true` folds the raw Shap-CAM linear ramp's arms onto theirs.
 * Pure, and the one owner of the remapping: `decode.codeTable` paints codes
 * through it and `visualMap` samples its legend stops from it, so a bin, a
 * cube and the colour bar agree.
 */
export function rampTable(scale, palette, { legible = true, signed = false, fadeDecades = THEME.floorFadeDecades } = {}) {
  const base = lookupTable(palette);
  if (!legible || isPrintTheme()) return base;
  const out = new Uint8ClampedArray(256 * 3);
  const copy = (i, j) => out.set(base.subarray(j * 3, j * 3 + 3), i * 3);
  if (isDiverging(scale)) {
    // Only the linear ramp on request; the signed log's folded arms already start at 3:1.
    if (!signed || scale?.scale === 'signed_log10') return base;
    const card = rgbTriple(THEME.card);
    const starts = [armStart(base, card, true), armStart(base, card, false)];
    for (let i = 0; i < 256; i += 1) {
      const negative = i < 128;
      const p = negative ? (127 - i) / 127 : (i - 128) / 127;
      const s = starts[negative ? 0 : 1];
      const q = Math.round((s + p * (1 - s)) * 127);
      copy(i, negative ? 127 - q : 128 + q);
    }
    return out;
  }
  const span = legibleSpan(scale, palette, { legible, fadeDecades });
  if (!span) return base;
  const { from, to, taperEnd } = span;
  // The taper climbs from the palette's end beyond `from`: 0 on the dark card
  // (exactly the old `(f / taperEnd) * from`), 1 on the light one. Only from an
  // end fainter on the card than `from` itself, so the climb darkens on white
  // and brightens on the dark card: Turbo's light run starts at 0.749 with its
  // dark blue end beyond it, and a climb from there would sweep the whole
  // rainbow through the faded half decade, so it fades its first colour alone.
  const outer = from <= to ? 0 : 1;
  const card = rgbTriple(THEME.card);
  const climbs = contrast(tableRgb(base, outer), card) < contrast(tableRgb(base, from), card);
  for (let i = 0; i < 256; i += 1) {
    const f = i / 255;
    let t;
    if (taperEnd > 0 && f < taperEnd) t = climbs ? outer + (f / taperEnd) * (from - outer) : from;
    else if (taperEnd > 0) t = from + ((f - taperEnd) / Math.max(1e-9, 1 - taperEnd)) * (to - from);
    else t = from + f * (to - from);
    copy(i, Math.max(0, Math.min(255, Math.round(t * 255))));
  }
  return out;
}

/** [r, g, b] of a 256-entry table at ramp position t (0..1). */
function tableRgb(table, t) {
  const i = Math.max(0, Math.min(255, Math.round(t * 255)));
  return [table[i * 3], table[i * 3 + 1], table[i * 3 + 2]];
}

/** [r, g, b] of '#rrggbb', the card's dark grey when unparseable. */
function rgbTriple(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(String(hex ?? '').trim());
  if (!m) return [28, 33, 40];
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/**
 * `count` CSS colour stops of a `rampTable`, at uniform positions; `alphaAt(t)`
 * as palette.js `colorStops`. `arms: true` samples a folded table arm by arm,
 * so a legible linear Shap-CAM legend meets its two 3:1 starts at the centre
 * instead of blending them across a stop.
 */
export function tableStops(table, count = 12, alphaAt = null, { arms = false } = {}) {
  const rgb = (index) => `${table[index * 3]},${table[index * 3 + 1]},${table[index * 3 + 2]}`;
  const stop = (index, t) => {
    const alpha = alphaAt ? alphaAt(t) : 1;
    return Number.isFinite(alpha) && alpha < 1
      ? `rgba(${rgb(index)},${Math.max(0, alpha).toFixed(3)})`
      : `rgb(${rgb(index)})`;
  };
  if (arms) {
    const half = Math.max(2, Math.ceil(count / 2));
    const out = [];
    for (let k = 0; k < half; k += 1) out.push(stop(Math.round((k / (half - 1)) * 127), k / (2 * half - 1)));
    for (let k = 0; k < half; k += 1) out.push(stop(128 + Math.round((k / (half - 1)) * 127), (half + k) / (2 * half - 1)));
    return out;
  }
  const out = [];
  for (let i = 0; i < count; i += 1) {
    const t = count > 1 ? i / (count - 1) : 0;
    out.push(stop(Math.round(t * 255), t));
  }
  return out;
}

/** Colour-bar titles of the relative (a.u.) ramps, by quantity. */
export const RAMP_TITLES = {
  density: 'Average hit density (a.u.)',
  gradcam_energy: 'Σ E·Grad-CAM (a.u.)',
  shapcam_energy: 'Σ E·Shap-CAM (a.u., signed)',
};

export function rampTitleText(scale) {
  return RAMP_TITLES[scale?.quantity ?? 'density'] ?? RAMP_TITLES.density;
}

/**
 * The zero mark at a diverging ramp's midpoint: "0" on the linear ramp,
 * "±10⁻³" on the signed log, whose centre is the undrawn band. Null for a
 * sequential ramp.
 *
 * On the vertical screen ramp it sits just left of the bar. ECharts centres
 * the bar under its end labels, so the bar's position depends on the widest
 * label; a fixed offset put the mark under the bar of the narrow linear
 * ramp, where it could not be seen. The offset is measured from the labels
 * `visualMap` draws.
 */
export function rampMidLabel(scale, metrics = {}) {
  if (!isDiverging(scale)) return null;
  const text = scale.scale === 'signed_log10' ? `±${floorLabel(scale)}` : '0';
  const style = { text, fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily };
  if (THEME.rampOrient === 'horizontal') {
    const bottomInset = metrics.reservedBottom || 0;
    return { type: 'text', left: 'center', bottom: bottomInset + 2 + 14 + 2.0 * THEME.fontSmall,
      silent: true, style };
  }
  const map = visualMap(scale, 'viridis');
  const lines = map.text.flatMap((t) => String(t).split('\n'));
  const widths = lines.map((line) => {
    const w = measureText(line, THEME.fontSmall, THEME.fontFamily);
    return Number.isFinite(w) ? w : line.length * 0.6 * THEME.fontSmall;
  });
  const component = Math.max(map.itemWidth, ...widths);
  // map.right is the component's own inset; the bar is centred within it.
  const barLeft = map.right + component / 2 + map.itemWidth / 2;
  return { type: 'text', right: barLeft + 4, top: 'middle', silent: true, style };
}

/** The colour-bar title the directive specifies for the canonical panels. */
export const RAMP_TITLE_RELATIVE = RAMP_TITLES.density;

/**
 * log₁₀ of a ramp's display floor, in the units of its `vmin`/`vmax`.
 *
 * The canonical density scale states its floor as `floor_ratio` (10⁻³ of
 * ρ_ref); a scale that does not falls back to its own bottom, which is the
 * same number on every relative ramp the server builds today. Shared by the
 * raster's alpha table and the legend, so both fade from one floor. Returns
 * null when neither is a finite number.
 */
export function floorExponent(scale) {
  const ratio = scale?.floor_ratio;
  if (Number.isFinite(ratio) && ratio > 0) return Math.log10(ratio);
  return Number.isFinite(scale?.vmin) ? scale.vmin : null;
}

/** The floor as the reader writes it, e.g. 10⁻³. */
export function floorLabel(scale) {
  const exp = floorExponent(scale);
  if (!Number.isFinite(exp)) return 'the floor';
  const rounded = Math.round(exp * 10) / 10;
  return `10${superscript(Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1))}`;
}

/**
 * A graphic text titling a horizontal (print) relative ramp.
 *
 * Returns null when no separate title is needed: for the vertical screen ramp
 * the title travels as the first line of the top label inside `visualMap`.
 * `metrics.reservedBottom` is the caption height, which the ramp itself is
 * also offset by, so title and ramp move together.
 *
 * A ramp whose floor is transparent says so in the title, because in print the
 * floor is a hard contour and a reader would otherwise take it for the edge of
 * the shower. The long wording gives way to a shorter one on a single-column
 * figure it does not fit.
 */
export function rampTitle(scale, metrics) {
  if (!scale || scale.unit !== 'a.u.' || THEME.rampOrient !== 'horizontal') return null;
  const bottomInset = metrics.reservedBottom || 0;
  const base = rampTitleText(scale);
  let text = base;
  if (scale.floor === 'transparent') {
    const floor = scale.scale === 'signed_log10' ? `|v| ${floorLabel(scale)}` : floorLabel(scale);
    const long = `${base} · below ${floor} not drawn`;
    const width = Number.isFinite(metrics.width) ? metrics.width - 16 : Infinity;
    text = fitsWidth(long, width, THEME.fontSmall, THEME.fontFamily)
      ? long
      : `${base} · <${floor} not drawn`;
  }
  // The bar is 14 px thick with its labels beside it; sit just above it.
  return {
    type: 'text',
    left: 'center',
    bottom: bottomInset + 2 + 14 + 0.6 * THEME.fontSmall,
    silent: true,
    style: {
      text,
      fill: THEME.muted,
      fontSize: THEME.fontSmall,
      fontFamily: THEME.fontFamily,
    },
  };
}

function clip01(value) {
  if (!Number.isFinite(value)) return 1;
  return Math.min(1, Math.max(0, value));
}

/** Render an exponent with Unicode superscripts, e.g. -4.2 -> ⁻⁴·². */
function superscript(text) {
  const map = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '-': '⁻', '.': '·',
  };
  return String(text).split('').map((c) => map[c] || c).join('');
}

/**
 * Shared axis styling for the spatial panels, labelled in millimetres.
 *
 * `onZero` overrides the theme: the canonical panels pass false, because
 * their windows are symmetric about the origin and an axis line anchored at
 * zero would draw a crosshair through the middle of both showers.
 */
export function spatialAxis(name, lo, hi, { onZero } = {}) {
  return {
    type: 'value',
    name,
    nameLocation: 'middle',
    nameGap: axisPadding().nameGap,
    nameTextStyle: {
      color: THEME.muted, fontSize: THEME.fontName, fontFamily: THEME.fontFamily,
    },
    min: lo,
    max: hi,
    axisLine: {
      onZero: onZero ?? THEME.axisOnZero,
      lineStyle: { color: THEME.border, width: THEME.lineAxis },
    },
    // Outward-facing ticks, stated rather than left to the default, because a
    // publication figure is specified that way and a future default change
    // should not silently move them inside the plot area.
    axisTick: {
      show: true,
      inside: false,
      lineStyle: { color: THEME.border, width: THEME.lineAxis },
    },
    axisLabel: {
      color: THEME.muted,
      fontSize: THEME.fontLabel,
      fontFamily: THEME.fontFamily,
      // The data extents rarely land on round numbers, so ECharts adds a label
      // at the exact boundary that collides with the last tick. Dropping the
      // overlap keeps the axis readable; the true extent is still the axis end.
      hideOverlap: true,
      showMinLabel: false,
      showMaxLabel: false,
      formatter: (v) => typographic(`${Math.round(v)}`),
    },
    splitLine: { show: false },
  };
}
