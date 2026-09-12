/* Number formatting and the ECharts visualMap configuration.
 *
 * The legend is always labelled in physical units - GeV, or a dimensionless
 * attention weight - never in colour codes. A reader should be able to take a
 * number off the legend and quote it.
 */

import { colorStops } from './palette.js';

const THEME = {
  text: '#e6edf3',
  muted: '#8b949e',
  border: '#30363d',
  canvas: '#0d1117',
  card: '#1c2128',
  accent: '#58a6ff',
  showerA: '#f778ba',
  showerB: '#58a6ff',
};

export { THEME };

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
export function visualMap(scale, palette) {
  const isLog = scale.scale === 'log10';
  const label = (value) => (isLog
    ? `10${superscript(Number(value).toFixed(1))}`
    : Number(value).toFixed(2));

  return {
    type: 'continuous',
    min: scale.vmin,
    max: scale.vmax,
    calculable: false,
    orient: 'vertical',
    right: 6,
    top: 'middle',
    itemWidth: 10,
    itemHeight: 140,
    precision: 2,
    // The endpoints are always labelled. A colour ramp without numbers cannot
    // be read off, and the units are what make the panel quotable: decade
    // exponents in GeV for density, a plain 0-1 weight for attention.
    text: [
      `${label(scale.vmax)}${isLog ? ' GeV' : ''}`,
      `${label(scale.vmin)}${isLog ? ' GeV' : ''}`,
    ],
    textGap: 6,
    textStyle: { color: THEME.muted, fontSize: 9 },
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
    nameGap: 26,
    nameTextStyle: { color: THEME.muted, fontSize: 10 },
    min: lo,
    max: hi,
    axisLine: { lineStyle: { color: THEME.border } },
    axisTick: { lineStyle: { color: THEME.border } },
    axisLabel: {
      color: THEME.muted,
      fontSize: 10,
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
