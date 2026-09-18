/* Number formatting and the ECharts visualMap configuration.
 *
 * The legend is always labelled in physical units - GeV, or a dimensionless
 * attention weight - never in colour codes. A reader should be able to take a
 * number off the legend and quote it.
 */

import { colorStops } from './palette.js';

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
export function axisPadding({ ramp = false } = {}) {
  const f = THEME.fontLabel;
  const horizontalRamp = ramp && THEME.rampOrient === 'horizontal';
  return {
    nameGap: 2.6 * f,
    left: 5.2 * f,
    right: ramp && !horizontalRamp ? 7.4 * f : 1.6 * f,
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
 */
export function visualMap(scale, palette, { bottomInset = 0 } = {}) {
  const isLog = scale.scale === 'log10';
  const label = (value) => (isLog
    ? `10${superscript(Number(value).toFixed(1))}`
    : Number(value).toFixed(2));

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

  return {
    type: 'continuous',
    min: scale.vmin,
    max: scale.vmax,
    calculable: false,
    ...place,
    precision: 2,
    // The endpoints are always labelled. A colour ramp without numbers cannot
    // be read off, and the units are what make the panel quotable: decade
    // exponents in GeV for density, a plain 0-1 weight for attention.
    text: [
      `${label(scale.vmax)}${isLog ? ' GeV' : ''}`,
      `${label(scale.vmin)}${isLog ? ' GeV' : ''}`,
    ],
    textGap: 6,
    textStyle: {
      color: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
    },
    inRange: { color: colorStops(palette) },
    formatter: (value) => (isLog
      ? `${label(value)} GeV`
      : Number(value).toFixed(2)),
  };
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

/** Shared axis styling for the spatial panels, labelled in millimetres. */
export function spatialAxis(name, lo, hi) {
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
      onZero: THEME.axisOnZero,
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
