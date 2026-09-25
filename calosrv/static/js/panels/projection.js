/* One spatial projection panel: raster, axes in millimetres, overlays, zoom.
 *
 * ## Why the raster is a custom series and not a graphic
 *
 * It used to be an ECharts `graphic.image` pinned to a pixel rectangle. Pixel
 * space does not participate in axis transforms, so the moment zoom or pan was
 * introduced the image would sit still while the axes moved underneath it. A
 * `custom` series instead asks ECharts for the pixel position of two *data*
 * corners on every frame, so the bitmap follows the axes and is clipped to the
 * grid for free. That is the whole reason zooming works here.
 *
 * ## Aspect ratio under zoom
 *
 * One `inside` dataZoom naming both axes applies the same zoom ratio to each.
 * The initial window is isometric, and scaling both spans by an equal factor
 * over a fixed pixel rectangle preserves their ratio, so 1:1 metric aspect
 * survives zooming without any per-frame correction. CLAUDE.md section 2
 * requires that for detector geometry.
 *
 * The XY panel additionally letterboxes its grid so a millimetre along x and a
 * millimetre along y are the same number of pixels, and the separation vector D
 * can be measured off the picture. The depth panels span 5200 mm transverse
 * against 1210 mm of depth, where forcing 1:1 would leave an unusable sliver,
 * so they fill the card and carry their true extents on the axes instead.
 *
 * The letterbox is a function of the container, so it is recomputed whenever
 * the *container* resizes - a sidebar collapsing, the grid dropping to one
 * column - not only the window. `chart.resize()` alone keeps the old grid
 * rectangle in pixels and silently breaks 1:1 (see `observeResize`).
 *
 * ## Overlays
 *
 * Every overlay line is a custom series from `marks.js`, clipped to the grid
 * and hit-testable, so its tooltip naming the quantity actually fires. The
 * canonical anchors and centroids live in `canonical_overlays.js`; the lab
 * frame keeps its centroid markers and D vector here, unchanged.
 *
 * The bin readout answers everywhere on the plot. On an overlay's drawn ink the
 * overlay's own text leads it; the ensemble wedges are silent and are named in
 * the readout instead (see `attachCellTooltip`).
 */

import {
  renderRaster, exactValue, dequantize, cellAt, cellCentre, occupiedBounds,
} from '../decode.js';
import {
  THEME, formatSci, spatialAxis, visualMap, axisPadding, rampTitle, floorLabel,
} from '../scale.js';
import {
  customLine, customPolyline, symbolOf, onInk,
} from './marks.js';
import { addCanonicalAnchors, addCanonicalCentroids } from './canonical_overlays.js';

export { symbolOf } from './marks.js';

/* Axis titles, keyed by the axis *symbol*. The payload names every axis by
 * its semantic identity (x, y, z) and, in the canonical frame, adds the
 * symbol it is written with (x′, y′, z′); the name is what every consumer
 * indexes by, the symbol is what the reader sees. */
const AXIS_LABEL = {
  x: 'x [mm]',
  y: 'y [mm]',
  z: 'z — depth [mm]',
  'x′': 'x′ — along the A→B separation [mm]',
  'y′': 'y′ — normal to the shower plane [mm]',
  'z′': 'z′ — depth from the front face [mm]',
};

/* Short titles for plots too shallow to carry the full ones: a 1:1 canonical
 * entrance panel of a widely separated pair is a strip a few dozen pixels
 * tall, and a rotated 35-character y-axis title would overflow it at both
 * ends. The caption defines x′ and y′ in words. */
const AXIS_LABEL_COMPACT = {
  'x′': 'x′ [mm]',
  'y′': 'y′ [mm]',
  'z′': 'z′ — depth [mm]',
};

/** Plot heights and widths (px) below which the compact titles and labels are used. */
const COMPACT_LABEL_HEIGHT = 220;
const COMPACT_LABEL_WIDTH = 420;

function axisLabel(axis, compact = false) {
  const symbol = symbolOf(axis);
  if (compact && AXIS_LABEL_COMPACT[symbol]) return AXIS_LABEL_COMPACT[symbol];
  return AXIS_LABEL[symbol] || symbol;
}

/** Line opacity of an ensemble axis whose direction is not distinguishable
 * from uniform (Rayleigh p above the server's fade threshold, carried as
 * `faded` on the axis block). */
const FADE_OPACITY = 0.4;

/** Fraction of the fitted region added as breathing room on each side. */
const ROI_PADDING = 0.06;

/** Range multiplier per wheel notch. */
const ZOOM_STEP = 1.18;

/** Plot-area height as a fraction of its width, for the two depth panels. */
const DEPTH_PLOT_ASPECT = 0.55;

export class ProjectionPanel {
  constructor(elementId, { isometric = false } = {}) {
    this.element = document.getElementById(elementId);
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    this.kind = 'projection';
    this.isometric = isometric;
    this.payload = null;
    this.raster = null;
    this.view = null;   // {col: [lo, hi], row: [lo, hi]} in mm; null = full extent
    this.drag = null;
    this.lastOpts = null;
    // The container size the current option was laid out at; `relayout`
    // compares against it so a resize that changes nothing costs nothing.
    this.laidOut = null;
    // Set by main.js: called on a container resize before the option is
    // rebuilt, so the caller may re-decide `isometric` for the new size.
    this.onRelayout = null;
    window.addEventListener('resize', () => this.chart.resize());
    this.observeResize();
  }

  /**
   * Rebuild the option whenever the container changes size (guard 8b.2).
   *
   * The isometric letterbox is computed in pixels from the host size at
   * build time, so a container that grows or shrinks without a window resize
   * - the sidebar, the grid's one-column breakpoint - would otherwise keep the
   * old rectangle, and `chart.resize()` alone stretches it: 1 mm along x′
   * would no longer be 1 mm along y′. One observer per panel, debounced to an
   * animation frame so a drag of the window rebuilds once per frame.
   */
  observeResize() {
    if (typeof ResizeObserver !== 'function' || !this.element) return;
    if (this.resizeObserver) this.resizeObserver.disconnect();
    let pending = 0;
    this.resizeObserver = new ResizeObserver(() => {
      if (pending) return;
      pending = requestAnimationFrame(() => {
        pending = 0;
        this.relayout();
      });
    });
    this.resizeObserver.observe(this.element);
  }

  /** Re-lay the retained payload out at the container's current size. */
  relayout() {
    const width = this.element.clientWidth;
    const height = this.element.clientHeight;
    if (this.laidOut && this.laidOut.width === width && this.laidOut.height === height) return;
    this.chart.resize();
    this.laidOut = { width, height };
    if (!this.payload || !this.raster || !this.lastOpts) return;

    const wasIsometric = this.isometric;
    if (typeof this.onRelayout === 'function') this.onRelayout(this);
    if (this.view && this.isometric !== wasIsometric) {
      this.view = clampView(this.view, this.payload.axes, this.isometric);
    }
    this.chart.setOption(this.buildOption({
      payload: this.payload,
      opts: this.lastOpts,
      raster: this.raster,
      metrics: { width, height },
    }), { notMerge: true });
  }

  /**
   * Pixel rectangle the data region should occupy.
   *
   * With `isometric`, the shorter physical axis is letterboxed so both axes
   * share one millimetre-per-pixel factor.
   *
   * `metrics` carries the host size rather than being read off `this.element`,
   * because the publication exporter renders the same panel into an off-screen
   * container of a different size, and the letterboxing must be recomputed for
   * it. `reservedBottom` is room set aside below the plot for the caption.
   */
  gridRect(colSpan, rowSpan, metrics, wideRamp = false) {
    const pad = axisPadding({ ramp: true, wideRamp });
    const padding = {
      left: pad.left, right: pad.right, top: pad.top, bottom: pad.bottom,
    };
    const width = metrics.width - padding.left - padding.right;
    const height = metrics.height - (metrics.reservedBottom || 0)
      - padding.top - padding.bottom;
    if (!this.isometric || width <= 0 || height <= 0) {
      return { ...padding, width, height };
    }
    const scale = Math.min(width / colSpan, height / rowSpan);
    const drawWidth = colSpan * scale;
    const drawHeight = rowSpan * scale;
    return {
      left: padding.left + (width - drawWidth) / 2,
      top: padding.top + (height - drawHeight) / 2,
      width: drawWidth,
      height: drawHeight,
      right: padding.right,
      bottom: padding.bottom,
    };
  }

  render(payload, opts) {
    // The displayed window survives a change of *selection* - in the canonical
    // frame the fitted extents move with every slider tick, and discarding the
    // zoom on each debounce would make zooming during a drag impossible - but
    // not a change of frame or of experiment, where the old window would be
    // meaningless against the new coordinates. Within one frame the window is
    // clamped to the new extents instead.
    const viewKey = `${opts.frame?.kind ?? 'lab'}|${opts.tableName ?? ''}`;
    if (this.viewKey !== viewKey) {
      this.view = null;
      this.viewKey = viewKey;
    } else if (this.view && this.payload && !sameExtent(this.payload, payload)) {
      this.view = clampView(this.view, payload.axes, this.isometric);
    }

    this.payload = payload;
    this.palette = opts.palette;
    this.raster = renderRaster(payload, opts.palette);
    // Retained so the exporter can rebuild this exact panel at a different size
    // without a round trip or a second copy of the call site's arguments.
    this.lastOpts = opts;

    const metrics = {
      width: this.element.clientWidth, height: this.element.clientHeight,
    };
    this.laidOut = { ...metrics };
    this.chart.setOption(this.buildOption({
      payload,
      opts,
      raster: this.raster,
      metrics,
    }), { notMerge: true });

    this.attachCellTooltip(payload.axes.col, payload.axes.row);
    this.attachNavigation();
  }

  /**
   * The chart option for one render.
   *
   * Separated from `render` so the exporter can call it with print tokens
   * active, a different `metrics`, and room reserved for a caption - without
   * touching the live instance. It is not derived from `getOption()` because
   * the `renderItem` closures below capture the raster canvas and the host
   * size, neither of which survives a round trip through a plain option object.
   */
  buildOption({ payload, opts, raster, metrics, graphic = [] }) {
    const {
      palette, centroids = null, showVector = false,
      axes = null, trajectories = null, showerKey = null,
      frame = null, ensembleAxes = null, ensembleMeta = null,
      anchors = null, depthBounds = null,
    } = opts;

    const col = payload.axes.col;
    const row = payload.axes.row;
    const canonical = frame?.kind === 'canonical';
    // The displayed window. The grid is letterboxed from the *full* extent so
    // the plot area does not jump around as the view changes.
    const view = this.view || { col: [col.lo, col.hi], row: [row.lo, row.hi] };
    // The vertical a.u. ramp carries its title as a second label line, which
    // needs a wider right inset than the GeV ramp's exponent labels.
    const wideRamp = payload.scale?.unit === 'a.u.' && THEME.rampOrient !== 'horizontal';
    const rect = this.gridRect(col.hi - col.lo, row.hi - row.lo, metrics, wideRamp);
    const canvas = raster.canvas;
    const title = rampTitle(payload.scale, metrics);
    const graphics = title ? [...graphic, title] : graphic;

    const series = [{
      // The raster. renderItem re-runs on every zoom and pan, and `clip` keeps
      // it inside the plot area.
      type: 'custom',
      id: 'raster',
      silent: true,
      clip: true,
      z: 1,
      data: [[col.lo, row.lo]],
      renderItem: (params, api) => {
        const p0 = api.coord([col.lo, row.lo]);
        const p1 = api.coord([col.hi, row.hi]);
        return {
          type: 'image',
          style: {
            image: canvas,
            x: Math.min(p0[0], p1[0]),
            y: Math.min(p0[1], p1[1]),
            width: Math.abs(p1[0] - p0[0]),
            height: Math.abs(p1[1] - p0[1]),
          },
        };
      },
    }];

    if (depthBounds) this.addDepthBounds(series, depthBounds, col, row);
    if (axes) this.addShowerAxes(series, axes, col, row);
    if (trajectories && showerKey) {
      this.addTrajectories(series, trajectories, col, row, showerKey);
    }
    const compact = rect.height < COMPACT_LABEL_HEIGHT || rect.width < COMPACT_LABEL_WIDTH;

    if (ensembleAxes) this.addEnsembleAxes(series, ensembleAxes, ensembleMeta, col, row);
    if (canonical) {
      addCanonicalCentroids(series, centroids, col, row);
      addCanonicalAnchors(series, anchors, frame, col, row);
    } else if (centroids) {
      this.addCentroids(series, centroids, col, row, showVector);
    }

    const provisional = frame?.fit?.provisional
      ? ' (provisional range)' : '';

    const grid = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
    if (canonical) {
      // A frame around the plot area, drawn above the raster (z 3 > 1): once
      // the display floor is transparent, the fitted window has no painted
      // edge of its own, and without a frame the reader cannot tell where the
      // plotted region ends and the card begins.
      Object.assign(grid, {
        show: true,
        borderColor: THEME.border,
        borderWidth: THEME.lineAxis,
        backgroundColor: 'transparent',
        z: 3,
      });
    }
    // Canonical axis lines stay on the frame. Anchored at zero they drew a
    // crosshair through the origin, which the symmetric window now centres -
    // exactly between the two showers.
    const axisOptions = canonical ? { onZero: false } : {};

    return {
      backgroundColor: THEME.chartBackground,
      animation: false,
      textStyle: { fontFamily: THEME.fontFamily },
      grid,
      xAxis: spatialAxis(
        axisLabel(col, compact) + (col.name !== 'z' ? provisional : ''), view.col[0], view.col[1],
        axisOptions,
      ),
      yAxis: spatialAxis(
        axisLabel(row, compact) + provisional, view.row[0], view.row[1], axisOptions,
      ),
      // Series 0 is the raster; the visualMap must colour it and nothing else.
      visualMap: visualMap(payload.scale, palette, {
        bottomInset: metrics.reservedBottom || 0,
        seriesIndex: 0,
      }),
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(22,27,34,0.95)',
        borderColor: THEME.border,
        textStyle: { color: THEME.text, fontSize: THEME.fontTip },
      },
      graphic: graphics,
      series,
    };
  }

  /** The window currently displayed, in millimetres. */
  currentView() {
    if (this.view) return this.view;
    if (!this.payload) return null;
    const { col, row } = this.payload.axes;
    return { col: [col.lo, col.hi], row: [row.lo, row.hi] };
  }

  /**
   * Figure dimensions for a publication export of the given printed width.
   *
   * Called with the print tokens active, so `axisPadding` already reflects the
   * larger type. The isometric panel takes its plot aspect from the *displayed*
   * window, which is what makes a zoomed export frame the same region the
   * screen does; the depth panels span 5200 mm against 1210 mm, where a true
   * aspect would be an unreadable sliver, so they take a fixed one.
   */
  exportMetrics(width) {
    const pad = axisPadding({ ramp: true });
    const plotWidth = Math.max(80, width - pad.left - pad.right);
    const view = this.currentView();
    let ratio = DEPTH_PLOT_ASPECT;
    if (this.isometric && view) {
      const colSpan = view.col[1] - view.col[0];
      const rowSpan = view.row[1] - view.row[0];
      if (colSpan > 0 && rowSpan > 0) {
        // The floor keeps a figure from becoming a sliver, but an isometric
        // panel letterboxes its data inside whatever height it is given, so a
        // floor much above the data's own aspect only adds blank paper: the
        // canonical entrance panel of a widely separated pair is a 9:1 strip.
        ratio = Math.min(1.3, Math.max(0.25, rowSpan / colSpan));
      } else {
        ratio = 1;
      }
    }
    return {
      width,
      height: Math.round(pad.top + pad.bottom + plotWidth * ratio),
    };
  }

  /* ------------------------------------------------------------- overlays */

  /**
   * Energy-weighted transverse centroid against depth, per shower.
   *
   * Always valid, because it is measured from the binned data on screen rather
   * than from an averaged incident direction - which on this dataset would be
   * meaningless, since the azimuth is near-uniform at every selection size.
   */
  addShowerAxes(series, axes, col, row) {
    for (const [shower, colour] of [['a', THEME.showerA], ['b', THEME.showerB]]) {
      const points = (axes[shower] || []).filter(Boolean);
      if (points.length < 2) continue;
      series.push(customPolyline({
        name: `Measured axis — ${shower.toUpperCase()}`,
        points,
        color: colour,
        width: 1.8 * THEME.lineAxis,
        opacity: 0.95,
        smooth: 0.2,
        z: 8,
        tooltip: `Measured shower axis — ${shower.toUpperCase()}<br/>`
          + 'energy-weighted centroid per depth layer',
      }));
    }
  }

  /**
   * Individual per-event incident trajectories.
   *
   * Drawn only for small selections. A single averaged line is never drawn: the
   * mean resultant length of the azimuth is about 0.01 over the full dataset and
   * still only ~0.18 for a handful of events, so an "average direction" would
   * point somewhere arbitrary while looking authoritative.
   */
  addTrajectories(series, paths, col, row, showerKey) {
    const zLo = col.name === 'z' ? col.lo : row.lo;
    const zHi = col.name === 'z' ? col.hi : row.hi;

    for (const path of paths) {
      for (const [shower, colour] of [['a', THEME.showerA], ['b', THEME.showerB]]) {
        const p = path[shower];
        if (!p) continue;
        const slope = Math.tan(p.theta) *
          (showerKey === 'y' ? Math.sin(p.phi) : Math.cos(p.phi));
        const origin = showerKey === 'y' ? p.y : p.x;
        const at = (z) => origin + (z - p.z) * slope;

        // Depth is the column axis on both depth panels, so the point order is
        // [z, transverse].
        series.push({
          type: 'line',
          name: `Event ${path.event} — ${shower.toUpperCase()}`,
          data: [[zLo, at(zLo)], [zHi, at(zHi)]],
          symbol: 'none',
          lineStyle: {
            color: colour, width: THEME.lineAxis, type: 'dashed', opacity: 0.45,
          },
          z: 6,
          clip: true,
          silent: true,
        });
      }
    }
  }

  /**
   * The two ensemble shower axes of the canonical frame, each with its
   * dispersion band and its mean-uncertainty envelope.
   *
   * Three marks, three quantities, per CLAUDE.md section 2: the dashed line is
   * the mean of the per-event projected slopes; the shaded wedge behind it is
   * the sample spread of those slopes (where individual showers go); the thin
   * envelope is the Student-t 95% interval of the mean (how well the ensemble
   * axis is known). They differ by sqrt(N), so each names itself on hover. An
   * axis whose direction is not distinguishable from uniform (Rayleigh p above
   * the fade threshold) is drawn faded, never hidden.
   *
   * The two wedges are silent. At small N they are wide areas lying on the
   * data - the N = 3 Y′Z′ envelope spans −1172…+636 mm of a ±720 mm window -
   * and a hit-testable wedge would answer for every bin beneath it. The bin
   * readout names the wedges the pointer is inside instead (`wedgeNotes`), so
   * each still states its quantity on hover.
   */
  addEnsembleAxes(series, block, meta, col, row) {
    for (const [shower, colour] of [['a', THEME.showerA], ['b', THEME.showerB]]) {
      const lines = block[shower];
      if (!lines || !lines.axis) continue;
      const info = meta?.[shower] || {};
      const label = shower.toUpperCase();
      const faded = Boolean(info.faded);
      const n = info.n ?? '—';
      const coherence = Number.isFinite(info.resultant_transverse)
        ? `R̄′ = ${info.resultant_transverse.toFixed(3)}, Rayleigh p = ${Number(info.rayleigh_p).toPrecision(2)}`
        : (info.label || 'single event');

      const wedge = (points, name, alpha) => {
        if (!points) return;
        series.push({
          type: 'custom',
          name,
          silent: true,
          clip: true,
          z: 5,
          data: [points],
          renderItem: (params, api) => {
            const [[z0, lo0, hi0], [z1, lo1, hi1]] = points;
            const corners = [[z0, lo0], [z1, lo1], [z1, hi1], [z0, hi0]].map((p) => api.coord(p));
            return {
              type: 'polygon',
              shape: { points: corners },
              style: { fill: colour, opacity: alpha, stroke: 'none' },
            };
          },
        });
      };

      // The two showers' wedges overlap on the YZ panel (both axes start at
      // the origin), so each is drawn at a fraction of the band alpha the
      // energy panel uses for a single band.
      wedge(lines.band, `Ensemble axis ${label} — spread`, faded ? 0.05 : THEME.bandAlpha * 0.6);
      wedge(lines.envelope, `Ensemble axis ${label} — 95% interval`, faded ? 0.12 : THEME.bandAlpha * 1.4);

      series.push(customPolyline({
        name: `Ensemble axis — ${label}`,
        points: lines.axis,
        color: colour,
        width: 1.8 * THEME.lineAxis,
        dash: 'dashed',
        opacity: faded ? FADE_OPACITY : 0.95,
        z: 9,
        tooltip: () =>
          `Ensemble shower axis — ${label}<br/>` +
          `mean incident direction in the canonical frame (slope ${Number(lines.slope).toFixed(4)})<br/>` +
          `${coherence}, N = ${n}` +
          (faded ? '<br/><i>direction not distinguishable from uniform; drawn faded</i>' : '') +
          (info.label && !faded ? `<br/><i>${info.label}</i>` : ''),
      }));
    }
  }

  /** The front and back faces of the calorimeter on a depth panel. */
  addDepthBounds(series, bounds, col, row) {
    if (col.name !== 'z') return;
    for (const [depth, name] of [[bounds.front, 'front face'], [bounds.back, 'back face']]) {
      if (!Number.isFinite(depth)) continue;
      series.push(customLine({
        name: `Calorimeter ${name}`,
        from: [depth, row.lo],
        to: [depth, row.hi],
        color: THEME.muted,
        width: THEME.lineAxis,
        opacity: 0.7,
        z: 4,
        tooltip: `Calorimeter ${name} at z′ = ${depth.toFixed(1)} mm<br/>`
          + 'The transverse outline rotates with each event and has no ensemble image.',
      }));
    }
  }

  addCentroids(series, centroids, col, row, showVector) {
    for (const [key, pair] of Object.entries(centroids)) {
      if (!pair || !pair.a) continue;
      const style = CENTROID_STYLE[key];
      if (!style) continue;

      for (const [shower, point] of [['A', pair.a], ['B', pair.b]]) {
        const cx = point[col.name];
        const cy = point[row.name];
        if (cx === null || cy === null || cx === undefined || cy === undefined) continue;
        series.push({
          type: 'scatter',
          name: `${pair.label} — ${shower}`,
          symbol: shower === 'A' ? 'diamond' : 'circle',
          symbolSize: style.size * THEME.markerScale,
          data: [[cx, cy]],
          itemStyle: {
            color: shower === 'A' ? THEME.showerA : THEME.showerB,
            borderColor: THEME.canvas,
            borderWidth: 1.5 * THEME.lineAxis,
            opacity: style.opacity,
          },
          tooltip: {
            formatter: () =>
              `${pair.label}<br/>Shower ${shower}<br/>` +
              `${symbolOf(col)} = ${cx.toFixed(1)} mm<br/>` +
              `${symbolOf(row)} = ${cy.toFixed(1)} mm`,
          },
          z: 10,
        });
      }

      // The separation vector is drawn only for the ground-truth pair;
      // overlaying three dashed lines would obscure the shower it measures.
      if (!(showVector && style.vector && pair.separation_mm !== null)) continue;

      const ax = pair.a[col.name];
      const ay = pair.a[row.name];
      const bx = pair.b[col.name];
      const by = pair.b[row.name];
      if (![ax, ay, bx, by].every((v) => v !== null && v !== undefined)) continue;

      series.push({
        type: 'line',
        name: 'Separation D',
        data: [[ax, ay], [bx, by]],
        symbol: 'none',
        lineStyle: {
          color: THEME.text, width: 1.4 * THEME.lineAxis, type: 'dashed', opacity: 0.9,
        },
        silent: true,
        z: 11,
        clip: true,
        markPoint: {
          symbol: 'rect',
          symbolSize: 0,
          // Offset perpendicular to A->B so the label clears both the line and
          // the centroid markers when D is small.
          data: [{
            coord: [(ax + bx) / 2, (ay + by) / 2],
            label: {
              show: true,
              formatter: `D = ${pair.separation_mm.toFixed(0)} mm`,
              color: THEME.text,
              backgroundColor: THEME.labelBg,
              borderColor: THEME.border,
              borderWidth: 1,
              padding: [3, 5],
              borderRadius: 3,
              fontSize: THEME.fontLabel,
              fontFamily: THEME.fontFamily,
              offset: labelOffset(ax, ay, bx, by),
            },
          }],
        },
      });
    }
  }

  /* ----------------------------------------------------------- zoom / RoI */

  /**
   * Zoom to where the energy actually is: the box holding 99% of it.
   *
   * Weighted by dequantised energy, not by colour code (see `occupiedBounds`).
   * For an isometric panel the narrower span is widened so both axes keep the
   * same millimetre-per-pixel factor, and a window that then pokes past the
   * extent is slid back inside at its full size. Truncating it instead - as a
   * non-isometric panel still does - would shorten one axis and not the other,
   * and the "1:1" guarantee would hold only at full zoom-out.
   *
   * Returns 'fitted', 'full' when the hits already fill the detector and there
   * is nothing to tighten, or 'empty'. The caller reports the last two, because
   * a button that silently does nothing reads as broken.
   */
  autoFitRoI() {
    if (!this.payload || !this.raster) return 'empty';
    const bounds = occupiedBounds(this.payload, this.raster, 0.99, { weight: 'value' });
    if (!bounds) return 'empty';

    const col = this.payload.axes.col;
    const row = this.payload.axes.row;

    let [c0, c1] = pad(bounds.col, ROI_PADDING);
    let [r0, r1] = pad(bounds.row, ROI_PADDING);

    if (this.isometric) {
      // Widen the narrower axis so both keep one millimetre-per-pixel factor;
      // otherwise the 1:1 guarantee would hold only at full zoom-out. The plot
      // rectangle is letterboxed from the full extent, so the window must take
      // the full extent's span ratio - which is 1 for the detector face but
      // about 9 for the canonical entrance window of a widely separated pair.
      const target = (col.hi - col.lo) / (row.hi - row.lo);
      const ratio = (c1 - c0) / (r1 - r0);
      if (ratio < target) {
        [c0, c1] = centreOn(c0, c1, (r1 - r0) * target);
      } else {
        [r0, r1] = centreOn(r0, r1, (c1 - c0) / target);
      }
    }

    // Padding and squaring can push the window past the detector. Showing
    // empty space beyond the instrumented volume is worse than showing all of
    // it, so a fit that no longer tightens anything falls back to the full
    // extent - which is the honest answer when the selected showers are spread
    // across the whole face, as most multi-event selections are.
    const tightens =
      (c1 - c0) < (col.hi - col.lo) * 0.98 || (r1 - r0) < (row.hi - row.lo) * 0.98;
    if (!tightens) {
      this.resetView();
      return 'full';
    }

    this.setView(this.isometric
      ? { col: slideInside([c0, c1], col), row: slideInside([r0, r1], row) }
      : {
        col: [Math.max(col.lo, c0), Math.min(col.hi, c1)],
        row: [Math.max(row.lo, r0), Math.min(row.hi, r1)],
      });
    return 'fitted';
  }

  /**
   * Set the displayed window and repaint the axes.
   *
   * The window is applied as the axis min/max rather than through a `dataZoom`
   * component. A `dataZoom` cannot move an axis that carries explicit bounds,
   * and these axes must carry them: they are drawn from the payload's physical
   * millimetre extents, not inferred from series data, which is what keeps the
   * raster aligned with the detector coordinates.
   */
  setView(view) {
    this.view = view;
    this.chart.setOption({
      xAxis: { min: view.col[0], max: view.col[1] },
      yAxis: { min: view.row[0], max: view.row[1] },
    });
  }

  resetView() {
    this.view = null;
    if (!this.payload) return;
    const { col, row } = this.payload.axes;
    this.chart.setOption({
      xAxis: { min: col.lo, max: col.hi },
      yAxis: { min: row.lo, max: row.hi },
    });
  }

  /**
   * Wheel to zoom, drag to pan.
   *
   * Both axes are scaled by the *same* factor, so the isometric ratio survives
   * zooming exactly as it does the letterboxed grid. Zoom is anchored at the
   * cursor, so the feature under the pointer stays put.
   */
  attachNavigation() {
    const zr = this.chart.getZr();
    if (this.wheelHandler) zr.off('mousewheel', this.wheelHandler);
    if (this.downHandler) zr.off('mousedown', this.downHandler);
    if (this.moveHandler) zr.off('mousemove', this.moveHandler);
    if (this.upHandler) {
      zr.off('mouseup', this.upHandler);
      zr.off('globalout', this.upHandler);
    }

    const current = () => this.view || {
      col: [this.payload.axes.col.lo, this.payload.axes.col.hi],
      row: [this.payload.axes.row.lo, this.payload.axes.row.hi],
    };

    this.wheelHandler = (event) => {
      if (!this.payload) return;
      const anchor = this.chart.convertFromPixel(
        { gridIndex: 0 }, [event.offsetX, event.offsetY],
      );
      if (!anchor || !Number.isFinite(anchor[0])) return;
      event.event?.preventDefault?.();

      const factor = event.wheelDelta > 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
      const view = current();
      this.setView({
        col: scaleAbout(view.col, anchor[0], factor),
        row: scaleAbout(view.row, anchor[1], factor),
      });
    };

    this.downHandler = (event) => {
      this.drag = { x: event.offsetX, y: event.offsetY, view: current() };
    };

    this.moveHandler = (event) => {
      if (!this.drag) return;
      const rect = this.chart.getModel()
        .getComponent('grid').coordinateSystem.getRect();
      const { col, row } = this.drag.view;
      const dx = ((event.offsetX - this.drag.x) / rect.width) * (col[1] - col[0]);
      // Screen y grows downward while the axis grows upward.
      const dy = ((event.offsetY - this.drag.y) / rect.height) * (row[1] - row[0]);
      this.setView({
        col: [col[0] - dx, col[1] - dx],
        row: [row[0] + dy, row[1] + dy],
      });
    };

    this.upHandler = () => { this.drag = null; };

    zr.on('mousewheel', this.wheelHandler);
    zr.on('mousedown', this.downHandler);
    zr.on('mousemove', this.moveHandler);
    zr.on('mouseup', this.upHandler);
    zr.on('globalout', this.upHandler);
  }

  /* -------------------------------------------------------------- tooltip */

  /**
   * Hover readout for the raster itself.
   *
   * ECharts' own tooltip works on series items and the raster is not one, so
   * the pointer is inverted through `convertFromPixel`, which - unlike the
   * fixed pixel rectangle this used to assume - accounts for the current zoom
   * window.
   *
   * The raster is `silent`, so a pointer over it has no zrender target; a
   * target means the pointer is inside an overlay's hit area - an anchor, a
   * rule, an axis - whose own item tooltip ECharts has just shown (its
   * listener runs before this one). This readout then replaces it: with the
   * bin alone when the pointer is inside the hit area but off the drawn ink
   * (`onInk`), and with the overlay's own text followed by the bin when it is
   * on the ink. Standing aside for every target, as this once did, hid the
   * bin readout - the only place the exact top-k values and the below-floor
   * wording appear - exactly where the data matter: the open anchor rings sit
   * on the shower cores and hit-test their whole 13 px disc, a face rule's
   * ±2.5 px band covers most of a 6.6 px first or last layer, and the axis
   * lines run through the cores by construction. The ensemble wedges are
   * silent and named in the readout (`wedgeNotes`).
   *
   * On a canonical payload an undrawn bin still answers, because "nothing is
   * here" and "something is here, below the floor" are different statements
   * and both are invisible. The lab keeps hiding the tip over an empty cell.
   */
  attachCellTooltip(col, row) {
    const zr = this.chart.getZr();
    if (this.tooltipHandler) zr.off('mousemove', this.tooltipHandler);

    const { codes, rows, cols } = this.raster;
    const payload = this.payload;
    const floored = Number.isInteger(payload.below_code);
    const reconstructed = typeof payload.kernel === 'string' && payload.kernel !== 'none';
    const attention = payload.scale?.unit === 'attention';
    const floorRatio = this.lastOpts?.frame?.reconstruction?.floor_ratio
      ?? payload.scale?.floor_ratio ?? 1e-3;
    const floorText = floorLabel({ floor_ratio: floorRatio });
    const muted = (text) => `<span style="color:${THEME.muted}">${text}</span>`;

    this.tooltipHandler = (event) => {
      const px = event.offsetX;
      const py = event.offsetY;
      // On an overlay's ink its own text leads and the bin follows; an
      // element that is not one of these series keeps ECharts' behaviour.
      let overlay = null;
      if (event.target && onInk(event.target, px, py)) {
        overlay = this.overlayTip(event.target);
        if (overlay === null) return;
      }

      let data;
      try {
        data = this.chart.convertFromPixel({ gridIndex: 0 }, [px, py]);
      } catch {
        return;
      }
      if (!data || !Number.isFinite(data[0]) || !Number.isFinite(data[1])) return;

      const [mmX, mmY] = data;
      if (mmX < col.lo || mmX > col.hi || mmY < row.lo || mmY > row.hi) {
        if (!overlay) this.chart.dispatchAction({ type: 'hideTip' });
        return;
      }

      const c = cellAt(col, cols, mmX);
      const r = cellAt(row, rows, mmY);
      const code = codes[r * cols + c];
      const centreX = cellCentre(col, cols, c);
      const centreY = cellCentre(row, rows, r);
      const where =
        `${symbolOf(col)} = ${centreX.toFixed(1)} mm<br/>` +
        `${symbolOf(row)} = ${centreY.toFixed(1)} mm<br/>`;
      // Named at the pointer, not the bin centre: a wedge edge crosses bins.
      const wedges = col.name === 'z'
        ? wedgeNotes(this.lastOpts?.ensembleAxes, this.lastOpts?.ensembleMeta, mmX, mmY)
        : [];
      const inWedges = wedges.length ? `<br/>${wedges.map(muted).join('<br/>')}` : '';
      const lead = overlay
        ? `${overlay}<div style="border-top:1px solid ${THEME.border};margin:4px 0"></div>`
        : '';
      const show = (html) => this.chart.dispatchAction({
        type: 'showTip',
        x: px,
        y: py,
        position: [px + 12, py - 8],
        tooltip: { formatter: lead + html + inWedges },
      });

      if (code === (payload.empty_code ?? 0)) {
        if (!floored) {
          if (!overlay) this.chart.dispatchAction({ type: 'hideTip' });
          return;
        }
        let empty;
        if (attention) empty = 'no hits in this bin: attention undefined';
        else if (reconstructed) empty = 'no reconstructed energy in this bin';
        else empty = 'no energy in this bin';
        show(where + muted(empty));
        return;
      }
      if (floored && code === payload.below_code) {
        show(where + muted(attention
          ? `attention not drawn: density below ${floorText} of ρ<sub>ref</sub>`
          : `below the display floor (ρ/ρ<sub>ref</sub> &lt; ${floorText}): not drawn`));
        return;
      }

      const exact = exactValue(payload, r, c);
      const scale = payload.scale;
      let label = '(quantised)';
      if (exact !== null) label = reconstructed ? '(exact, reconstructed)' : '(exact)';
      const precision = muted(` ${label}`);

      let body;
      if (scale.unit === 'a.u.' && scale.rho_ref) {
        // Relative ramp: the raster holds ratios to rho_ref, the exact list
        // holds physical densities. Show both, plus the bin the value is a
        // density over, so the number can be quoted either way.
        const rho = exact !== null ? exact : dequantize(code, scale, payload) * scale.rho_ref;
        const ratio = rho / scale.rho_ref;
        const binW = (col.hi - col.lo) / cols;
        const binH = (row.hi - row.lo) / rows;
        body =
          `<b>${ratio.toFixed(3)} a.u.</b> of ρ<sub>ref</sub>${precision}<br/>` +
          `⟨ρ⟩ = ${formatSci(rho, 3)} GeV mm⁻² per event<br/>` +
          muted(`${binW.toFixed(1)} × ${binH.toFixed(1)} mm ${reconstructed ? 'display bin' : 'bin'} · ` +
            `ρ<sub>ref</sub> = ${formatSci(scale.rho_ref, 3)} (${scale.norm === 'dataset' ? 'dataset' : 'selection'} peak)`);
      } else {
        const value = exact !== null ? exact : dequantize(code, scale, payload);
        const unit = scale.unit === 'GeV' ? 'GeV' : '';
        body = `<b>${formatSci(value, 3)} ${unit}</b>${precision}`;
      }

      show(where + body);
    };
    zr.on('mousemove', this.tooltipHandler);
  }

  /**
   * The tooltip text of the overlay series a zrender element belongs to, or
   * null when it belongs to none (an axis label, the colour bar, a markPoint).
   *
   * Read from the series model, so it is the same formatter ECharts has just
   * shown; every overlay formatter here ignores its arguments.
   */
  overlayTip(target) {
    const getECData = globalThis.echarts?.helper?.getECData;
    if (typeof getECData !== 'function') return null;
    for (let el = target; el; el = el.parent) {
      const info = getECData(el);
      if (!Number.isInteger(info?.seriesIndex)) continue;
      if (info.componentMainType && info.componentMainType !== 'series') return null;
      const model = this.chart.getModel().getSeriesByIndex(info.seriesIndex);
      const formatter = model?.get(['tooltip', 'formatter']);
      if (typeof formatter === 'function') return formatter();
      return typeof formatter === 'string' ? formatter : null;
    }
    return null;
  }

  resize() {
    this.chart.resize();
  }

  setBusy(busy) {
    this.element.classList.toggle('is-busy', busy);
  }
}

/* ------------------------------------------------------------- helpers -- */

/**
 * The silent ensemble wedges the depth-panel point (z, t) lies inside, as
 * readout lines for the bin tooltip.
 *
 * A wedge is the quadrilateral through [z0, lo0, hi0] and [z1, lo1, hi1] with
 * straight edges, so containment is a linear interpolation of lo and hi at z.
 * Each line names its quantity: the dispersion band and the interval of the
 * mean differ by sqrt(N) and look alike (CLAUDE.md section 2).
 */
function wedgeNotes(block, meta, z, t) {
  if (!block) return [];
  const inside = (points) => {
    if (!Array.isArray(points) || points.length < 2) return false;
    const [[z0, lo0, hi0], [z1, lo1, hi1]] = points;
    if (!(z1 !== z0)) return false;
    const f = (z - z0) / (z1 - z0);
    if (!(f >= 0 && f <= 1)) return false;
    const lo = lo0 + f * (lo1 - lo0);
    const hi = hi0 + f * (hi1 - hi0);
    return t >= Math.min(lo, hi) && t <= Math.max(lo, hi);
  };
  const notes = [];
  for (const shower of ['a', 'b']) {
    const lines = block[shower];
    if (!lines || !lines.axis) continue;
    const label = shower.toUpperCase();
    if (inside(lines.band)) {
      notes.push(`in the dispersion band of axis ${label}: ± sample SD of the per-event slopes`
        + (lines.dof_note ? ` (${lines.dof_note})` : ''));
    }
    if (inside(lines.envelope)) {
      notes.push(`in the 95% interval of the mean of axis ${label}: `
        + `± t<sub>0.975,N−1</sub>·SD/√N, N = ${meta?.[shower]?.n ?? '—'}`);
    }
  }
  return notes;
}

function sameExtent(a, b) {
  return a.axes.col.lo === b.axes.col.lo && a.axes.col.hi === b.axes.col.hi
    && a.axes.row.lo === b.axes.row.lo && a.axes.row.hi === b.axes.row.hi;
}

/**
 * Keep a zoom window inside new extents, or drop it when nothing survives.
 *
 * The window keeps its size where it can (so a zoom level survives a slider
 * tick) and slides inward where the new extent is smaller; a window wider
 * than the whole new extent simply becomes the full extent (null).
 *
 * On an isometric panel the plot rectangle is letterboxed from the *full*
 * extent, so a window is drawn 1:1 only if its span ratio equals the full
 * extent's. The canonical fit window changes shape with every selection, so
 * the kept window is re-proportioned about its centre to the new ratio before
 * it is slid inside.
 */
function clampView(view, axes, isometric = false) {
  let colSpan = view.col[1] - view.col[0];
  let rowSpan = view.row[1] - view.row[0];
  const fullCol = axes.col.hi - axes.col.lo;
  const fullRow = axes.row.hi - axes.row.lo;
  if (isometric && fullCol > 0 && fullRow > 0 && colSpan > 0) {
    rowSpan = colSpan * (fullRow / fullCol);
  }
  const centre = (r) => (r[0] + r[1]) / 2;
  const fit = (mid, span, axis) => {
    const full = axis.hi - axis.lo;
    const width = Math.min(span, full);
    if (!(width > 0) || width >= full * 0.999) return null;
    let a = mid - width / 2;
    if (a < axis.lo) a = axis.lo;
    if (a + width > axis.hi) a = axis.hi - width;
    return [a, a + width];
  };
  const col = fit(centre(view.col), colSpan, axes.col);
  const row = fit(centre(view.row), rowSpan, axes.row);
  if (!col && !row) return null;
  // Both axes must shrink together on an isometric panel, or neither.
  if (isometric && (!col || !row)) return null;
  return {
    col: col || [axes.col.lo, axes.col.hi],
    row: row || [axes.row.lo, axes.row.hi],
  };
}

/**
 * Move a window inside an axis extent without changing its width.
 *
 * A window at least as wide as the extent becomes the extent. On an isometric
 * panel both axes share one span ratio, so they reach that case together.
 */
function slideInside([lo, hi], axis) {
  const width = hi - lo;
  if (!(width > 0) || width >= axis.hi - axis.lo) return [axis.lo, axis.hi];
  if (lo < axis.lo) return [axis.lo, axis.lo + width];
  if (hi > axis.hi) return [axis.hi - width, axis.hi];
  return [lo, hi];
}

function pad([lo, hi], fraction) {
  const width = hi - lo;
  const margin = Math.max(width * fraction, 1e-6);
  return [lo - margin, hi + margin];
}

function centreOn(lo, hi, width) {
  const mid = (lo + hi) / 2;
  return [mid - width / 2, mid + width / 2];
}

/** Scale a range about a fixed point, so the feature under the cursor stays. */
function scaleAbout([lo, hi], anchor, factor) {
  return [anchor + (lo - anchor) * factor, anchor + (hi - anchor) * factor];
}

/** Perpendicular pixel offset for the D label, away from the A->B line. */
function labelOffset(ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const length = Math.hypot(dx, dy) || 1;
  const magnitude = 16;
  // Screen y grows downward, so the perpendicular is (dy, -dx) negated in y.
  return [(-dy / length) * magnitude, (-dx / length) * magnitude];
}

const CENTROID_STYLE = {
  truth_voxel: { size: 15, opacity: 1.0, vector: true },
  pred_voxel: { size: 11, opacity: 0.75, vector: false },
  truth_dataset: { size: 9, opacity: 0.5, vector: false },
  // The canonical frame's replacement for truth_dataset: the dataset centroids
  // averaged after co-registration, where averaging a position is meaningful.
  canonical_mean: { size: 9, opacity: 0.5, vector: false },
};
