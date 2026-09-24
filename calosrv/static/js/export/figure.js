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
 *
 * ## Why the SVG caption is spliced rather than drawn
 *
 * The PNG carries its caption as ECharts `graphic` text, painted inside the
 * synchronous block. The SVG does not: zrender's SVG painter flattens the
 * display list, so `graphic` items come out as loose `<text>` with no group a
 * reader could address, and the deliverable wants an isolated
 * `<g id="figure-disclosure">`. So for SVG the chart is rendered with the
 * caption's *height reserved but its items withheld*, and the same laid-out
 * items are serialised by `captionToSvg` and spliced before `</svg>` in the
 * post-processing step, alongside `sharpenRasterHints`. That step runs after
 * the theme is restored, which is why `captionToSvg` reads styles from the
 * items and never from `THEME`.
 */

import { THEME, restoreScreenTheme, axisPadding } from '../scale.js';
import { renderRaster } from '../decode.js';
import { PRINT_TOKENS, PX_RATIO, widthToPx } from './tokens.js';
import {
  buildCaption, captionToSvg, describeSelection, describeView, fitTableRows,
} from './caption.js';
import { downloadBlob, dataUrlToBlob } from './download.js';
import { figureName } from './filename.js';

/** Long side, in pixels, beyond which the raster is not upscaled further. */
const MAX_RASTER_PX = 4096;

/**
 * Export one panel.
 *
 * `panel` is a `ProjectionPanel` or `EnergyPanel`; `context` carries the
 * `State`, the active experiment, the live footnote text and the structured
 * `disclosure` sentences from `export/disclosure.js`.
 */
export function exportPanel(panel, {
  panelId, format = 'svg', widthMm, title, footnote, state, experiment, selection,
  frame = null, disclosure = [],
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
  // Laid out inside the synchronous block, consumed after it: the SVG splice
  // below needs the caption's items and the plot height they sit under.
  let caption = null;
  let metrics = null;

  try {
    chart = echarts.init(host, null, {
      renderer: format === 'svg' ? 'svg' : 'canvas',
    });

    const saved = { ...THEME };
    try {
      /* ---- the synchronous window: no await, no timer, no yield --------- */
      Object.assign(THEME, PRINT_TOKENS);

      metrics = panel.exportMetrics(width);
      caption = buildCaption({
        title,
        provenance: provenanceFor(panel, state, experiment, selection, frame),
        footnote,
        table: tableFor(panel, width),
        disclosure,
      }, width);

      const figureHeight = metrics.height + caption.height;
      host.style.height = `${figureHeight}px`;
      chart.resize({ width, height: figureHeight });

      // SVG: the band's height is reserved so the ramp and axes stay clear of
      // it, but its items are withheld from the chart and spliced in as a
      // `<g>` after serialisation (see the header). PNG: drawn as graphics.
      const option = buildPrintOption(panel, {
        width,
        height: figureHeight,
        reservedBottom: caption.height,
        graphic: format === 'svg' ? [] : offsetCaption(caption.graphic, metrics.height),
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
      ? new Blob([
        spliceCaption(sharpenRasterHints(serialized), caption.graphic, metrics.height),
      ], { type: mime })
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

function provenanceFor(panel, state, experiment, selection, frameBlock = null) {
  // The frame block rides on the top-level projections response, which the
  // caller passes in; a projection panel only holds its own panel payload.
  // Fall back to anything the panel itself carries, and to null for the lab.
  const frame = frameBlock
    ?? (panel.kind === 'energy' ? panel.lastPayload?.frame : panel.payload?.frame)
    ?? null;
  const parts = [describeSelection(state, experiment, selection, frame)];
  if (typeof panel.currentView === 'function') {
    const view = panel.currentView();
    const axes = panel.payload?.axes;
    if (view && axes?.col && axes?.row) {
      parts.push(describeView(
        view, axes.col.symbol ?? axes.col.name, axes.row.symbol ?? axes.row.name,
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

/**
 * Insert the caption band as `<g id="figure-disclosure">` before `</svg>`.
 *
 * The root element zrender writes carries width, height and viewBox in the
 * same logical pixels the caption was laid out in, so the items' positions
 * transfer unchanged. Placed last in document order, the band paints over
 * nothing: its height was reserved below the plot when the chart was built.
 */
function spliceCaption(svg, graphic, plotHeight) {
  const band = captionToSvg(graphic, plotHeight);
  if (!band) return svg;
  const close = svg.lastIndexOf('</svg>');
  if (close < 0) return svg;
  return `${svg.slice(0, close)}${band}${svg.slice(close)}`;
}
