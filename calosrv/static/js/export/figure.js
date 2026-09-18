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
 * between the swap and the restore. Nothing in `renderExport` may become
 * `async`, and no `await` may be introduced inside the try block. The Blob
 * conversion and the download happen afterwards, once the screen theme is back.
 *
 * ## Why the panel is re-rendered rather than cloned
 *
 * `getOption()` returns an option whose `renderItem` closures have already
 * captured the raster canvas, the host element's pixel height and the axis
 * window of the render that produced them. Replaying it at a different size
 * would draw the screen's geometry into a figure of another shape: the strip
 * rows, the reserved-band clearance and the isometric letterboxing are all
 * functions of the container. Asking the panel to build a fresh option for the
 * figure's own metrics is the only way those come out right.
 *
 * ## Why the off-screen container is positioned, not hidden
 *
 * `display: none` and `visibility: hidden` both give a zero-size box, and
 * ECharts measures its container. The node is therefore a normally laid-out
 * element parked outside the viewport, and it is removed before this returns.
 */

import { THEME, restoreScreenTheme, axisPadding } from '../scale.js';
import { renderRaster } from '../decode.js';
import { PRINT_TOKENS, PX_RATIO, widthToPx } from './tokens.js';
import { buildCaption, describeSelection, describeView, fitTableRows } from './caption.js';
import { downloadBlob, dataUrlToBlob } from './download.js';
import { figureName } from './filename.js';

/** Long side, in pixels, beyond which the raster is not upscaled further. */
const MAX_RASTER_PX = 4096;

/**
 * Export one panel.
 *
 * `panel` is a `ProjectionPanel` or `EnergyPanel`; `context` carries the
 * `State`, the active experiment and the live footnote text.
 */
export function exportPanel(panel, {
  panelId, format = 'svg', widthMm, title, footnote, state, experiment, selection,
}) {
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

  try {
    chart = echarts.init(host, null, {
      renderer: format === 'svg' ? 'svg' : 'canvas',
    });

    const saved = { ...THEME };
    try {
      /* ---- the synchronous window: no await, no timer, no yield --------- */
      Object.assign(THEME, PRINT_TOKENS);

      const metrics = panel.exportMetrics(width);
      const caption = buildCaption({
        title,
        provenance: provenanceFor(panel, state, experiment, selection),
        footnote,
        table: tableFor(panel, width),
      }, width);

      const figureHeight = metrics.height + caption.height;
      host.style.height = `${figureHeight}px`;
      chart.resize({ width, height: figureHeight });

      const option = buildPrintOption(panel, {
        width,
        height: figureHeight,
        reservedBottom: caption.height,
        graphic: offsetCaption(caption.graphic, metrics.height),
      });
      chart.setOption(option, { notMerge: true });

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

    downloadBlob(blob, figureName(panelId, format, { state }));
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
function buildPrintOption(panel, { width, height, reservedBottom, graphic }) {
  const metrics = { width, height, reservedBottom };

  if (panel.kind === 'projection') {
    // The raster is rebuilt rather than borrowed, so it can be upscaled for
    // print without disturbing the bitmap the live chart is drawing.
    return panel.buildOption({
      payload: panel.payload,
      opts: panel.lastOpts || { palette: panel.palette },
      raster: printRaster(panel, width),
      metrics,
      graphic,
    });
  }

  const { option } = panel.buildOption({
    payload: panel.lastPayload,
    opts: panel.lastOpts || {},
    metrics,
    graphic,
  });
  return option;
}

/**
 * The density raster, upscaled for print by an integer factor.
 *
 * Nearest-neighbour, never smoothed. Each pixel here is one detector cell - a
 * discrete measurement - so interpolating between them would invent values
 * across a lattice CLAUDE.md section 2 specifically forbids resampling by
 * point-binning or aliasing. An integer factor also keeps every cell boundary
 * on a whole pixel, so the upscale adds resolution to the *chrome* around the
 * image without blurring the image itself.
 */
function printRaster(panel, width) {
  const base = renderRaster(panel.payload, panel.palette);
  const target = width * PX_RATIO;
  const factor = Math.max(1, Math.min(
    Math.floor(target / Math.max(1, base.canvas.width)),
    Math.floor(MAX_RASTER_PX / Math.max(1, base.canvas.width)),
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

/** Move the caption graphics below the plot area. */
function offsetCaption(graphic, plotHeight) {
  return graphic.map((item) => ({ ...item, top: item.top + plotHeight }));
}

function provenanceFor(panel, state, experiment, selection) {
  const parts = [describeSelection(state, experiment, selection)];
  if (typeof panel.currentView === 'function') {
    const view = panel.currentView();
    if (view && panel.payload) {
      parts.push(describeView(
        view, panel.payload.axes.col.name, panel.payload.axes.row.name,
      ));
    }
  }
  return parts.filter(Boolean).join(' ');
}

function tableFor(panel, width) {
  if (panel.kind !== 'energy') return [];
  if (!panel.lastPayload || !panel.lastPayload.series) return [];
  const opts = panel.lastOpts || {};
  const kind = opts.kind || 'pred';
  const shower = opts.shower || 'both';
  const shown = panel.lastPayload.series.filter(
    (s) => s.kind === kind && (shower === 'both' || s.shower === shower),
  );
  const pad = axisPadding();
  return fitTableRows(
    panel.lastPayload, shown, panel.lastPayload.slice_counts || {},
    width - pad.left / 2,
  );
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
