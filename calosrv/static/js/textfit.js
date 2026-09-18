/* Text measurement, for layouts that must hold at more than one figure width.
 *
 * The panels were written against a single on-screen size, so captions and
 * legends could be positioned with pixel literals that happened to fit. A
 * publication export renders the same panel at 321 px (one journal column) as
 * well as at 661 px, and at a larger type size, so those literals stop holding:
 * a caption that fits the screen runs off the grid of a single-column figure.
 *
 * Measuring against a 2D context is exact for the canvas renderer and a close
 * approximation for the SVG one, which is enough - every consumer here is
 * deciding how to break or shorten a line, not placing a glyph.
 */

let context = null;

function measurer() {
  if (!context) context = document.createElement('canvas').getContext('2d');
  return context;
}

/** Width of `text` in pixels at the given size and family. */
export function measureText(text, fontPx, fontFamily = 'sans-serif', weight = '') {
  const ctx = measurer();
  if (!ctx) return String(text).length * fontPx * 0.55;
  ctx.font = `${weight} ${fontPx}px ${fontFamily}`.trim();
  return ctx.measureText(String(text)).width;
}

/** Whether `text` fits `maxWidth`. */
export function fitsWidth(text, maxWidth, fontPx, fontFamily = 'sans-serif') {
  return measureText(text, fontPx, fontFamily) <= maxWidth;
}

/**
 * Break `text` into lines no wider than `maxWidth`.
 *
 * A word longer than the line is left to overflow rather than hyphenated:
 * the long tokens here are column names and numbers, and breaking `incoming_
 * momentum_A` across a line would be harder to read than letting it run.
 */
export function wrapText(text, maxWidth, fontPx, fontFamily = 'sans-serif') {
  const words = String(text ?? '').split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const lines = [];
  let line = words[0];
  for (let i = 1; i < words.length; i += 1) {
    const candidate = `${line} ${words[i]}`;
    if (measureText(candidate, fontPx, fontFamily) <= maxWidth) {
      line = candidate;
    } else {
      lines.push(line);
      line = words[i];
    }
  }
  lines.push(line);
  return lines;
}

/**
 * Rows an ECharts `plain` legend will occupy.
 *
 * ECharts wraps a plain legend itself but does not report how many rows it
 * used, and the grid above it has to be inset by that amount. Mirrors the
 * layout rule: each entry is its marker, a gap, its label, then the item gap.
 */
export function legendRows(names, maxWidth, fontPx, {
  fontFamily = 'sans-serif', itemWidth = 16, itemGap = 10,
} = {}) {
  if (!names.length || maxWidth <= 0) return 0;
  let rows = 1;
  let used = 0;
  for (const name of names) {
    const entry = itemWidth + 5 + measureText(name, fontPx, fontFamily);
    if (used > 0 && used + entry > maxWidth) {
      rows += 1;
      used = entry + itemGap;
    } else {
      used += entry + itemGap;
    }
  }
  return rows;
}
