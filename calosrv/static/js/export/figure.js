/* Render a panel off-screen under print styling and serialise it.
 *
 * ## The invariant this file exists to protect
 *
 * `THEME` is a mutable singleton that every chart option reads at build time.
 * Swapping it is what lets one set of option builders serve both the screen and
 * the page without a second implementation - but a swapped theme is a global,
 * and a live chart that repainted while it was swapped would flash white.
 *
 * It cannot, because **the swap, the render and the serialisation are one
 * synchronous block.** `setOption`, `renderToSVGString` and `getDataURL` are all
 * synchronous, so no timer, no fetch continuation and no resize handler can run
 * between the swap and the restore. Nothing in `exportPanel` may become
 * `async`, and no `await` may be introduced inside the try block. The Blob
 * conversion and the download happen afterwards, once the screen theme is back.
 *
 * ## Why the panel is re-rendered rather than cloned
 *
 * `getOption()` returns an option whose `renderItem` closures have already
 * captured the raster canvas, the host element's pixel height and the axis
 * window of the render that produced them. Replaying it at a different size
 * would draw the screen's geometry into a figure of another shape: the strip
 * rows and the isometric letterboxing are both functions of the container.
 * Asking the panel to build a fresh option for the figure's own metrics is the
 * only way those come out right.
 *
 * ## Why the off-screen container is positioned, not hidden
 *
 * `display: none` and `visibility: hidden` both give a zero-size box, and
 * ECharts measures its container. The node is therefore a normally laid-out
 * element parked outside the viewport, and it is removed before this returns.
 *
 * ## What the figure is
 *
 * The plot canvas and nothing else: the axes, the data raster, the vector
 * overlays and the colour-scale legend, on #FFFFFF in #111827 ink. No band is
 * laid out under the plot, no height is reserved for one, and nothing is
 * spliced into the SVG after serialisation; the only post-processing is
 * `sharpenRasterHints`. The methodology and the statistical disclosures a
 * reader needs - the clipping counts, the display window and the energy it
 * leaves out, the density reference, the measured comb - are the panel's
 * Details drawer (panel_notes.js), which is what an author carries into the
 * manuscript caption. The ramp's print title still names the display floor.
 */

import { THEME, restoreScreenTheme } from '../scale.js';
import { renderRaster } from '../decode.js';
import { PRINT_TOKENS, PX_RATIO, widthToPx } from './tokens.js';
import { displayOf } from './caption.js';
import { downloadBlob, dataUrlToBlob } from './download.js';
import { figureName } from './filename.js';

/** Long side, in pixels, beyond which the raster is not upscaled further. */
const MAX_RASTER_PX = 4096;

/**
 * Export one panel.
 *
 * `panel` is a `ProjectionPanel` or `EnergyPanel`; `state` names the selection
 * for the file name and `meta` is the response's own statement of what the
 * panel holds (channel, network, frame), so the name never comes from controls
 * that may have moved on since.
 */
export function exportPanel(panel, { panelId, format = 'svg', widthMm, state, meta = null }) {
  const width = widthToPx(widthMm);
  const host = document.createElement('div');
  // Parked off-screen at a real size: ECharts measures its container, so a
  // hidden node would render into a zero-pixel box.
  host.style.cssText = `position:fixed;left:-20000px;top:0;width:${width}px;`
    + 'height:100px;pointer-events:none;';
  document.body.appendChild(host);

  let chart = null;
  let serialized = null;
  let mime = null;
  // What the displayed bins are - R, merge, kernel - as the payload states
  // them, for the file name. Read before the synchronous block; it depends on
  // nothing the theme swap changes. The energy panel has no spatial bins, so
  // it names none (`spatial: false`).
  const spatial = panel.kind === 'projection';
  const display = spatial
    ? displayOf(panel.lastOpts?.resolution, panel.lastOpts?.frame ?? null, panel.payload)
    : null;

  try {
    chart = echarts.init(host, null, {
      renderer: format === 'svg' ? 'svg' : 'canvas',
    });

    const saved = { ...THEME };
    try {
      /* ---- the synchronous window: no await, no timer, no yield --------- */
      Object.assign(THEME, PRINT_TOKENS);

      const metrics = panel.exportMetrics(width);
      host.style.height = `${metrics.height}px`;
      chart.resize({ width, height: metrics.height });
      chart.setOption(buildPrintOption(panel, metrics), { notMerge: true });

      if (format === 'svg') {
        serialized = chart.renderToSVGString();
        mime = 'image/svg+xml;charset=utf-8';
      } else {
        serialized = chart.getDataURL({
          type: 'png',
          pixelRatio: PX_RATIO,
          backgroundColor: THEME.chartBackground,
        });
        mime = 'image/png';
      }
    } finally {
      restoreScreenTheme();
      Object.assign(THEME, saved);
    }
    /* ---- screen theme is back; everything below may yield --------------- */

    const blob = format === 'svg'
      ? new Blob([sharpenRasterHints(serialized)], { type: mime })
      : dataUrlToBlob(serialized);

    downloadBlob(blob, figureName(panelId, format, { state, display, spatial, meta }));
  } finally {
    if (chart) chart.dispose();
    host.remove();
  }
}

/**
 * Ask the panel for a print option at the figure's own geometry.
 *
 * The two panel classes return different shapes - the energy panel also hands
 * back the data its HTML side-tables need - so the difference is absorbed here
 * rather than forcing one of them to pretend it is the other.
 */
function buildPrintOption(panel, { width, height }) {
  const metrics = { width, height };

  if (panel.kind === 'projection') {
    // The raster is rebuilt rather than borrowed, so it can be upscaled for
    // print without disturbing the bitmap the live chart is drawing.
    return panel.buildOption({
      payload: panel.payload,
      opts: panel.lastOpts || { palette: panel.palette },
      raster: printRaster(panel, width),
      metrics,
    });
  }

  const { option } = panel.buildOption({
    payload: panel.lastPayload,
    opts: panel.lastOpts || {},
    metrics,
  });
  return option;
}

/**
 * The density raster, upscaled for print by an integer factor.
 *
 * Nearest-neighbour, never smoothed. Each pixel block here is one *payload
 * bin*: a detector cell in the absolute frame, a raw 20 mm accumulation bin
 * in a co-registered Native Grid, a reconstructed display bin in the
 * Continuous Field. Every one of them is a value the server computed;
 * interpolating between them would invent values the payload does not
 * contain - and on the detector lattice would resample it by point
 * interpolation, which CLAUDE.md section 2 forbids. The smoothing the
 * Continuous Field shows was done by a stated, conservative kernel on the
 * server, not by the image scaler. An integer factor also keeps every bin
 * boundary on a whole pixel, so the upscale adds resolution to the *chrome*
 * around the image without blurring the image.
 *
 * So the raster is taken at one pixel per payload bin (`screen: false`),
 * without the on-screen enlargements `renderRaster` applies to the Native
 * Grid and to the depth axis of the Continuous Field, and enlarged here by one
 * factor for both axes.
 */
function printRaster(panel, width) {
  const base = renderRaster(panel.payload, panel.palette, { screen: false });
  const target = width * PX_RATIO;
  // The cap is on the long side. A depth raster is 60 layer columns by a few
  // hundred transverse rows, so a factor chosen from its width alone grew its
  // height to 7 000-17 000 px.
  const longSide = Math.max(1, base.canvas.width, base.canvas.height);
  const factor = Math.max(1, Math.min(
    Math.floor(target / Math.max(1, base.canvas.width)),
    Math.floor(MAX_RASTER_PX / longSide),
  ));
  if (factor <= 1) return base;

  const scaled = document.createElement('canvas');
  scaled.width = base.canvas.width * factor;
  scaled.height = base.canvas.height * factor;
  const ctx = scaled.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(base.canvas, 0, 0, scaled.width, scaled.height);
  return { ...base, canvas: scaled };
}

/**
 * Tell SVG consumers not to smooth the embedded raster.
 *
 * zrender writes the density field as an <image> holding a PNG data URL. A
 * viewer scaling that up will interpolate by default, which re-introduces
 * exactly the blurring the integer upscale above avoided. `pixelated` asks for
 * nearest-neighbour; viewers that ignore it still get the pre-upscaled bitmap.
 */
function sharpenRasterHints(svg) {
  return svg.replace(/<image /g, '<image style="image-rendering:pixelated" ');
}
