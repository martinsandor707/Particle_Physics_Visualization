/* Number formatting and the ECharts visualMap configuration.
 *
 * The legend is always labelled in physical units - GeV, or a dimensionless
 * attention weight - never in colour codes. A reader should be able to take a
 * number off the legend and quote it.
 */

import { colorStops } from './palette.js';
import { fitsWidth } from './textfit.js';

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

  categorical: { min: 0.25, max: 1.0 },
  rampOrient: 'vertical',
  // A scrolling legend is right on screen, where the arrows are clickable and
  // the panel is wide. Printed, an entry behind a scroll arrow is an entry that
  // is not there, so the export wraps instead and pays for it in height.
  legendWrap: false,
};

/**
 * The active style, as a mutable singleton.
 *
 * Every chart option in this codebase reads `THEME.x` at build time, in some
 * forty places. Making the object mutable rather than replacing the binding
 * means the publication exporter can swap the whole style for the duration of
 * one synchronous render without touching a single call site. Nothing else may
 * mutate it - `restoreScreenTheme()` is the only sanctioned way back.
 */
export const THEME = { ...SCREEN };

/** The screen style, for the exporter to restore. */
export const SCREEN_THEME = Object.freeze({ ...SCREEN });

export function restoreScreenTheme() {
  for (const key of Object.keys(THEME)) delete THEME[key];
  Object.assign(THEME, SCREEN);
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
    return value.toFixed(Math.max(0, digits - 1 - exponent));
  }
  return value.toExponential(digits);
}

export function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

export function formatInt(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return Math.round(value).toLocaleString();
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
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
export function visualMap(scale, palette, { bottomInset = 0, seriesIndex = 0 } = {}) {
  const isLog = scale.scale === 'log10';
  // A relative (a.u.) ramp is dimensionless: its ends are derived from the
  // scale's own bounds, which reach above 10^0 when a selection is brighter
  // than the dataset reference it is drawn against.
  const relative = scale.unit === 'a.u.';
  const unit = relative ? ' a.u.' : (isLog ? ' GeV' : '');
  const label = (value) => (isLog
    ? `10${superscript(Number(value).toFixed(1))}`
    : Number(value).toFixed(2));

  const horizontal = THEME.rampOrient === 'horizontal';
  // The ramp title. ECharts' continuous visualMap has no title of its own, so
  // on the vertical screen ramp it rides as a second line of the top label;
  // the horizontal print ramp gets a separate graphic from rampTitle().
  const title = relative && !horizontal ? `${RAMP_TITLE_RELATIVE}\n` : '';
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

  // The fade, when this ramp has one: alpha rises linearly in log density
  // from 0 at the floor to 1 a `fade` decades above it. 48 stops put about
  // eight inside the bottom half decade of a three-decade ramp, so the legend
  // gradient follows the raster's taper rather than a single coarse step.
  const fade = THEME.floorFadeDecades;
  const floorExp = floorExponent(scale);
  const tapered = relative && isLog && Number.isFinite(fade) && fade > 0
    && Number.isFinite(floorExp) && Number.isFinite(scale.vmin) && Number.isFinite(scale.vmax);
  const stops = tapered
    ? colorStops(palette, 48, (t) => clip01(
      (scale.vmin + t * (scale.vmax - scale.vmin) - floorExp) / fade,
    ))
    : colorStops(palette);
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
      `${title}${label(scale.vmax)}${unit}`,
      bottom,
    ],
    textGap: 6,
    textStyle: {
      color: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
    },
    inRange: { color: stops },
    // The continuous legend paints an out-of-range bar underneath the ramp,
    // grey (#aaa) by default. Opaque stops hide it; faded ones let it show as
    // a light patch where the card should be. It colours nothing else here:
    // the raster's renderItem never reads a visual colour.
    ...(tapered ? { outOfRange: { color: ['rgba(0,0,0,0)'] } } : {}),
    formatter: (value) => (isLog
      ? `${label(value)}${unit}`
      : Number(value).toFixed(2)),
  };
}

/** The colour-bar title the directive specifies for the canonical panels. */
export const RAMP_TITLE_RELATIVE = 'Average hit density (a.u.)';

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
  let text = RAMP_TITLE_RELATIVE;
  if (scale.floor === 'transparent') {
    const floor = floorLabel(scale);
    const long = `${RAMP_TITLE_RELATIVE} · below ${floor} not drawn`;
    const width = Number.isFinite(metrics.width) ? metrics.width - 16 : Infinity;
    text = fitsWidth(long, width, THEME.fontSmall, THEME.fontFamily)
      ? long
      : `${RAMP_TITLE_RELATIVE} · <${floor} not drawn`;
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
      formatter: (v) => `${Math.round(v)}`,
    },
    splitLine: { show: false },
  };
}
