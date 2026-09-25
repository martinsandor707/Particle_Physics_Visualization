/* Publication style tokens and the unit conversions behind them.
 *
 * ## Why figures are authored in millimetres
 *
 * A journal specifies a figure by its printed width, not by a pixel count. So
 * the export canvas is sized in millimetres and converted at 96 DPI - the CSS
 * reference density - which makes one logical pixel exactly 1/96 inch on paper.
 * Rasterising that canvas at `PX_RATIO` then lands on 300 DPI by construction:
 *
 *     85 mm  -> 321.3 logical px -> x3.125 -> 1004 px  (single column)
 *    175 mm  -> 661.4 logical px -> x3.125 -> 2067 px  (double column)
 *
 * The convention also gives `pt` a meaning: under it, 1 pt = 96/72 = 4/3
 * logical px, so a size specified in points prints at that size.
 *
 * ## Why print fonts are *larger* than screen fonts
 *
 * This is the counter-intuitive consequence of the above, and getting it
 * backwards is the usual way a "publication export" fails its own requirement.
 * Legibility is set by the font's share of the figure width, not by its pixel
 * size. The interface draws 9-10 px labels in a ~600 px panel; reproducing 9 px
 * in a 321 px single-column figure prints at 6.8 pt, well under the 9 pt floor.
 * Nine points is 12 logical px here, so every print size is quoted in points and
 * converted, rather than carried over from the screen theme.
 *
 * ## Why the ink colours live in their own object
 *
 * `PRINT_INK` holds exactly those tokens that are drawn as text or as axis
 * chrome, and `tests/test_export_assets.py` parses this file and asserts each
 * one clears 4.5:1 contrast against white. Gridlines are deliberately *not* in
 * it: a gridline that cleared 4.5:1 would be competing with the data. Keeping
 * the two sets apart is what lets the contrast floor be checked mechanically
 * without also failing the tokens that are supposed to be subdued.
 */

/** CSS reference density: one logical pixel is 1/96 inch. */
export const MM_TO_PX = 96 / 25.4;

/** One point is 1/72 inch, so 96/72 logical pixels. */
export const PT_TO_PX = 96 / 72;

/** Raster multiplier taking the 96 DPI canvas to a 300 DPI image. */
export const PX_RATIO = 300 / 96;

/** Standard academic column widths, in millimetres. */
export const WIDTH_MM = { single: 85, double: 175 };

/** Smallest permitted type size, in points. */
export const MIN_PT = 9;

/**
 * Colours drawn as text or as axis chrome.
 *
 * Every value here is asserted to clear 4.5:1 against #FFFFFF by a Python test
 * that reads this literal. Keep it a flat object of hex strings.
 */
export const PRINT_INK = {
  text: '#111827',
  muted: '#374151',
  border: '#111827',
  accent: '#0b5fbe',
  warn: '#8a5a00',
  showerA: '#a3186b',
  showerB: '#0b5fbe',
};

/**
 * The full print style, swapped over `THEME` for the duration of one export.
 *
 * The shower hues are darkened members of the same families rather than new
 * colours: #f778ba and #58a6ff are chosen to clear a #0d1117 canvas and sit near
 * 2.4:1 on white, so they are re-anchored, not re-hued. Shower identity is also
 * carried by symbol shape (diamond / circle), which survives any restyling.
 */
export const PRINT_TOKENS = {
  ...PRINT_INK,

  canvas: '#FFFFFF',
  card: '#FFFFFF',
  grid: '#E5E7EB',
  labelBg: 'rgba(255,255,255,0.92)',
  chartBackground: '#FFFFFF',

  /* Single quotes inside, deliberately. zrender writes the font stack into an
   * SVG `style="..."` attribute without escaping, so a double-quoted family
   * name closes the attribute early and the whole declaration is discarded -
   * every label in the exported figure then falls back to the viewer's default
   * serif. Single quotes are equally valid CSS and survive the round trip. */
  fontFamily: "Arial, Helvetica, 'DejaVu Sans', sans-serif",
  fontMono: "'DejaVu Sans Mono', 'Courier New', monospace",
  fontSmall: MIN_PT * PT_TO_PX,
  fontLabel: MIN_PT * PT_TO_PX,
  fontName: 9.5 * PT_TO_PX,
  fontTip: MIN_PT * PT_TO_PX,

  lineAxis: 1 * PT_TO_PX,
  lineGrid: 0.75 * PT_TO_PX,
  gridOpacity: 1,
  markerScale: 0.75,
  axisOnZero: false,

  /* Semi-transparent fills are re-weighted for white paper. The screen values
   * are tuned against a dark canvas, where a light wash at 0.07 reads clearly;
   * the same wash on white is invisible in print and disappears entirely after
   * a downscale to one column. */
  envelopeAlpha: 0.18,
  bandAlpha: 0.22,
  stripAlpha: 0.07,

  /* The colour ramp sub-range inverts.
   *
   * `categoricalStops` samples the upper ramp on screen because Viridis begins
   * at #440154, invisible as a one-pixel line on #0d1117. On white the failure
   * is the mirror image: the #fde725 end vanishes. Sampling [0, 0.75] restores
   * the same guarantee against the opposite background. The ramp's identity and
   * its lightness ordering are untouched - this is a sub-range change, not the
   * palette inversion CLAUDE.md section 2 forbids. */
  categorical: { min: 0.0, max: 0.75 },

  /* A vertical colour bar costs ~7 label widths of horizontal room, which on a
   * 321 px single-column figure is a quarter of the canvas. Laid out below the
   * x axis it costs height instead, which a figure has more of to spare. */
  rampOrient: 'horizontal',
  legendWrap: true,

  /* Canonical-frame overlay chrome, deliberately outside PRINT_INK: none of it
   * is text, and the separation rule is a reference line that must stay
   * quieter than the data, so it is not held to the 4.5:1 ink floor.
   *
   * The screen rule is translucent white, which vanishes on paper and carries
   * an alpha channel PDF renderers composite unpredictably; a mid grey
   * replaces it. Anchors print at full opacity for the same reason. The floor
   * fade is 0: print shows a hard contour at the 10⁻³ display floor, and the
   * caption names it, rather than a gradient a printer may band or drop. */
  separationRule: '#6b7280',
  anchorOpacity: 1,
  floorFadeDecades: 0,
  // Standard PuOr on white paper: its light centre marks zero there.
  divergingPalette: 'puor',
  divergingLinearPalette: 'puor',
};

/** Logical pixels for a figure of the given printed width. */
export function widthToPx(widthMm) {
  return Math.round(widthMm * MM_TO_PX);
}
