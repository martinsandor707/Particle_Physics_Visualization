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
 * the *container* resizes - the sidebar collapsing, the Details drawer
 * opening, the grid dropping to one column - not only the window.
 * `chart.resize()` alone keeps the old grid rectangle in pixels and silently
 * breaks 1:1 (see `observeResize`).
 *
 * ## Overlays
 *
 * Every overlay line is a custom series from `marks.js`, clipped to the grid
 * and hit-testable, so its tooltip naming the quantity actually fires. The
 * canonical anchors and centroids live in `canonical_overlays.js`; the lab
 * frame keeps its centroid markers and D vector here, unchanged. The card's
 * Marks toggle (`setMarksShown`) leaves every overlay out.
 *
 * The bin readout answers everywhere on the plot. On an overlay's drawn ink the
 * overlay's own text leads it; the ensemble wedges are silent and are named in
 * the readout instead (see `attachCellTooltip`).
 */

import {
  renderRaster, exactValue, dequantize, cellAt, cellCentre, occupiedBounds,
} from '../decode.js';
import {
  THEME, formatSci, formatInt, spatialAxis, visualMap, axisPadding, rampTitle, floorLabel,
  rampMidLabel, rampPalette, typographic, unitSuffix,
} from '../scale.js';
import {
  customLine, customPolyline, customMarker, customBand, insideWedge, symbolOf, onInk, projectMarks,
} from './marks.js';
import {
  addCanonicalAnchors, addCanonicalCentroids, addFrameMeanSpread, stripMarks,
} from './canonical_overlays.js';
import { isPrintTheme, onLightCard } from './chart_panel.js';
import { formatSigned } from '../format.js';
import { axisSymbol, panelOf } from '../axis_symbols.js';
import {
  PREFER_POINTER, hideTooltipOnScroll, plotBoxFromGrid, tooltipOption, tooltipPosition,
} from './tooltip.js';

export { symbolOf } from './marks.js';

/* Axis titles, keyed by the axis *symbol*. The payload names every axis by
 * its semantic identity (x, y, z) and, in a co-registered frame, adds the
 * symbol it is written with (x′, y′, z′); the name is what every consumer
 * indexes by, the symbol is what the reader sees. The Separation-Aligned
 * entry panel writes its horizontal axis as D (axis_symbols.js): the signed
 * x′ coordinate along the A→B separation, anchors at ∓⟨D_entry⟩/2. */
const AXIS_LABEL = {
  x: 'x [mm]',
  y: 'y [mm]',
  z: 'z — depth [mm]',
  D: 'D — along the A→B separation [mm]',
  'x′': 'x′ — along the A→B separation [mm]',
  'y′': 'y′ — normal to the shower plane [mm]',
  'z′': 'z′ — depth from the front face [mm]',
  'Δx': 'Δx — from the shower entry point [mm]',
  'Δy': 'Δy — from the shower entry point [mm]',
  'Δz': 'Δz — depth from the shower’s first layer [mm]',
  u: 'u — lateral spread, in the incidence plane [mm]',
  v: 'v — lateral spread, normal to the incidence plane [mm]',
  w: 'w — shower depth along the incident direction [mm]',
};

/* Short titles for plots too shallow to carry the full ones: a 1:1 D-frame
 * entrance panel of a widely separated pair is a strip a few dozen pixels
 * tall, and a rotated 35-character y-axis title would overflow it at both
 * ends. The Details drawer defines D, x′ and y′ in words. */
const AXIS_LABEL_COMPACT = {
  D: 'D [mm]',
  'x′': 'x′ [mm]',
  'y′': 'y′ [mm]',
  'z′': 'z′ — depth [mm]',
  'Δx': 'Δx [mm]',
  'Δy': 'Δy [mm]',
  'Δz': 'Δz — depth [mm]',
  u: 'u [mm]',
  v: 'v [mm]',
  w: 'w — depth [mm]',
};

/** How a physical unit of the payload is written in a readout. */
const UNIT_TEXT = { 'GeV/mm^2/event': 'GeV mm⁻² per event', 'GeV/mm^2': 'GeV mm⁻²', GeV: 'GeV' };

/** Plot heights and widths (px) below which the compact titles and labels are used. */
const COMPACT_LABEL_HEIGHT = 220;
const COMPACT_LABEL_WIDTH = 420;

function axisLabel(symbol, compact = false) {
  if (compact && AXIS_LABEL_COMPACT[symbol]) return AXIS_LABEL_COMPACT[symbol];
  return AXIS_LABEL[symbol] || symbol;
}

/**
 * The symbols a panel's two axes are written with: the payload's own, except
 * that the Separation-Aligned entry panel writes x′ as D (axis_symbols.js).
 * One rule for the axis titles, the hover readout and the overlay tooltips.
 */
function displaySymbols(payload, opts) {
  const kind = opts?.frame?.kind ?? 'lab';
  const panelId = panelOf(payload.axes);
  return {
    col: axisSymbol(payload.axes.col, kind, panelId),
    row: axisSymbol(payload.axes.row, kind, panelId),
  };
}

/** Line opacity of an ensemble axis whose direction is not distinguishable
 * from uniform (Rayleigh p above the server's fade threshold, carried as
 * `faded` on the axis block). */
const FADE_OPACITY = 0.4;

/**
 * The outline of a spread wedge on the light screen (THEME.wedgeEdge), or null.
 * Its wash is light there, so its extent is carried by its two long sides,
 * dashed so they never read as caps, at 0.7 opacity, where both shower inks
 * stay above 3:1 on white (3.9:1 and 3.5:1). A faded axis keeps a faint
 * outline. Null on the dark card and in print, whose wedges are as before.
 */
function wedgeEdge(colour, faded) {
  if (!THEME.wedgeEdge) return null;
  return { color: colour, width: THEME.lineAxis, dash: [4, 3], opacity: faded ? 0.25 : 0.7 };
}

/**
 * The outline of a 95% envelope on the light screen: thin solid sides, so it
 * reads as the thin envelope of the mean beside the spread's dashed outline,
 * two marks for two quantities. Null on the dark card and in print.
 */
function envelopeEdge(colour, faded) {
  if (!THEME.wedgeEdge) return null;
  return { color: colour, width: 0.75 * THEME.lineAxis, dash: null, opacity: faded ? 0.2 : 0.55 };
}

/**
 * The wash of an ensemble axis's spread wedge (`part` 'spread') or 95% envelope
 * ('envelope'). On the dark card and in print, as always: THEME.wedgeAlpha
 * scaled by 0.6 and 1.4, and 0.05 and 0.12 for a faded axis. On the light
 * screen (THEME.wedgeEdge) both are light washes their outlines carry - at N = 2
 * the envelope spans the panel, and any heavier wash lay over the raster as
 * smoke - and a faded axis takes half of each.
 */
function wedgeOpacity(part, faded) {
  const factor = part === 'spread' ? 0.6 : 1.4;
  if (!THEME.wedgeEdge) return faded ? (part === 'spread' ? 0.05 : 0.12) : THEME.wedgeAlpha * factor;
  return THEME.wedgeAlpha * factor * (faded ? 0.5 : 1);
}

/** Stroke (px) of an ensemble or windowed axis on the light screen. */
export const LIGHT_AXIS_WIDTH = 1.25;

/**
 * The stroke of an ensemble or windowed axis: 1.8 px on the dark card and in
 * print, as always; on the light screen one clean 1.25 px dash with nothing
 * under it (Martin's directive of 2026-10-30: a white casing under the dashes
 * read as a white band through the shower core).
 */
function axisWidth() {
  return !isPrintTheme() && onLightCard() ? LIGHT_AXIS_WIDTH : 1.8 * THEME.lineAxis;
}

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
    // The grid of the option on screen, recorded at each live setOption (never
    // in buildOption, which the exporter also calls at print geometry), so the
    // tooltip keeps the plot area it is placed around current.
    this.liveGrid = null;
    // Two placements over one plot box: an explanation (a mark's, an
    // overlay's) leaves the chart; the plain bin readout stays at the pointer
    // where it covers at most 20% of the plot, and leaves it like an
    // explanation otherwise (tooltip.js placeTooltip), so it never hides
    // the panel being hovered.
    const plotBox = () => plotBoxFromGrid(this.liveGrid, this.chart.getWidth(), this.chart.getHeight());
    this.tooltipPosition = tooltipPosition(this.chart, plotBox);
    this.readoutPosition = tooltipPosition(this.chart, plotBox, { prefer: PREFER_POINTER });
    hideTooltipOnScroll(this.chart);
    this.kind = 'projection';
    this.isometric = isometric;
    this.payload = null;
    this.raster = null;
    // The Marks toggle (`setMarksShown`): false draws the raster, axes and
    // colour bar alone. Kept across renders; the export follows it.
    this.marksShown = true;
    this.view = null;   // {col: [lo, hi], row: [lo, hi]} in mm; null = full extent
    this.drag = null;
    this.lastOpts = null;
    // The container size the current option was laid out at; `relayout`
    // compares against it so a resize that changes nothing costs nothing.
    this.laidOut = null;
    // Set by main.js: called on a container resize before the option is
    // rebuilt, so the caller may re-decide `isometric` for the new size.
    this.onRelayout = null;
    // Set by main.js: called after the displayed window changes (zoom, pan,
    // Auto-fit RoI, Reset, a clamp), so text that states the window follows.
    this.onViewChange = null;
    window.addEventListener('resize', () => this.chart.resize());
    this.observeResize();
  }

  /**
   * Rebuild the option whenever the container changes size (guard 8b.2).
   *
   * The isometric letterbox is computed in pixels from the host size at
   * build time, so a container that grows or shrinks without a window resize
   * - the sidebar, the Details drawer, the grid's one-column breakpoint -
   * would otherwise keep the old rectangle, and `chart.resize()` alone
   * stretches it: 1 mm along x′ would no longer be 1 mm along y′. One
   * observer per panel, debounced to an animation frame so a drag of the
   * window rebuilds once per frame. The shell also calls `relayout()`
   * directly after a sidebar or drawer toggle (main.js `relayoutAll`); the
   * grid tracks snap, so that call measures the final geometry and the
   * observer's own tick then finds nothing to do.
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
    // A hidden host - a grid that is not on show - has no size to lay out
    // at. The payload is kept; the relayout that follows the host being shown
    // (its ResizeObserver, or the shell's relayoutAll) builds the option.
    if (!(width > 0 && height > 0)) {
      this.laidOut = null;
      return;
    }
    // The canvas is checked as well as the option: a render that measured the
    // new size before this ran would otherwise leave the canvas at the old one.
    const sized = this.chart.getWidth() === width && this.chart.getHeight() === height;
    if (sized && this.laidOut && this.laidOut.width === width && this.laidOut.height === height) return;
    if (!sized) this.chart.resize();
    this.laidOut = { width, height };
    if (!this.payload || !this.raster || !this.lastOpts) return;

    const wasIsometric = this.isometric;
    if (typeof this.onRelayout === 'function') this.onRelayout(this);
    if (this.view && this.isometric !== wasIsometric) {
      this.view = clampView(this.view, this.extent ?? extentOf(this.payload, this.lastOpts), this.isometric);
      this.viewChanged();
    }
    this.setLiveOption(this.buildOption({
      payload: this.payload,
      opts: this.lastOpts,
      raster: this.raster,
      metrics: { width, height },
    }));
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
   * it. `reservedBottom`, when a caller sets it, is room kept clear below the
   * plot; the exporter reserves none, so the figure is the plot alone.
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
    const viewKey = `${opts.frame?.kind ?? 'lab'}|${opts.tableName ?? ''}|${opts.viewKey ?? ''}`;
    const extent = extentOf(payload, opts);
    if (this.viewKey !== viewKey) {
      this.view = null;
      this.viewKey = viewKey;
    } else if (this.view && this.extent && !sameExtent(this.extent, extent)) {
      this.view = clampView(this.view, extent, this.isometric);
    }

    this.payload = payload;
    this.extent = extent;
    this.palette = opts.palette;
    this.raster = renderRaster(payload, opts.palette);
    // Retained so the exporter can rebuild this exact panel at a different size
    // without a round trip or a second copy of the call site's arguments.
    this.lastOpts = opts;
    this.symbols = displaySymbols(payload, opts);

    const metrics = {
      width: this.element.clientWidth, height: this.element.clientHeight,
    };
    if (metrics.width > 0 && metrics.height > 0) {
      this.laidOut = { ...metrics };
      this.setLiveOption(this.buildOption({
        payload,
        opts,
        raster: this.raster,
        metrics,
      }));
    } else {
      // Rendered into a hidden host: everything is retained, and relayout()
      // builds the option once the host has a size.
      this.laidOut = null;
    }

    this.attachCellTooltip(payload.axes.col, payload.axes.row);
    this.attachNavigation();
  }

  /** Put an option on screen and record its grid for the tooltip placement. */
  setLiveOption(option) {
    this.liveGrid = option.grid ?? null;
    this.chart.setOption(option, { notMerge: true });
  }

  /**
   * The chart option for one render.
   *
   * Separated from `render` so the exporter can call it with print tokens
   * active and a different `metrics` - without touching the live instance. It is not derived from `getOption()` because
   * the `renderItem` closures below capture the raster canvas and the host
   * size, neither of which survives a round trip through a plain option object.
   */
  buildOption({ payload, opts, raster, metrics, graphic = [] }) {
    const {
      palette, centroids = null, showVector = false,
      axes = null, trajectories = null, showerKey = null,
      frame = null, ensembleAxes = null, ensembleMeta = null,
      anchors = null, depthBounds = null, marks = null, markColour = null, markShower = null,
      framed = false, windowAxis = null,
    } = opts;
    // A shower's marks take its ink from the theme in force at build time, so a
    // print rebuild draws them in the print ink, never in the screen's.
    const markInk = markShower === 'a' ? THEME.showerA : markShower === 'b' ? THEME.showerB : markColour;

    const col = payload.axes.col;
    const row = payload.axes.row;
    const symbols = displaySymbols(payload, opts);
    const canonical = frame?.kind === 'canonical';
    // Every co-registered frame (canonical, translated, local) draws a symmetric
    // window about its origin, framed and with the axis lines on the frame.
    // The Event Inspector's nine panels are framed the same way (`framed`).
    const coregistered = ['canonical', 'trans', 'local'].includes(frame?.kind) || framed;
    // The extent the axes span: the caller's window (the inspector's equal
    // half-width window, wider than the raster) or the raster's own edges.
    const extent = extentOf(payload, opts);
    // The displayed window. The grid is letterboxed from the *full* extent so
    // the plot area does not jump around as the view changes.
    const view = this.view || { col: [...extent.col], row: [...extent.row] };
    // The vertical a.u. ramp carries its title as a second label line, which
    // needs a wider right inset than the GeV ramp's exponent labels.
    const wideRamp = payload.scale?.unit === 'a.u.' && THEME.rampOrient !== 'horizontal';
    const rect = this.gridRect(extent.col[1] - extent.col[0], extent.row[1] - extent.row[0], metrics, wideRamp);
    const canvas = raster.canvas;
    const title = rampTitle(payload.scale, metrics);
    const mid = rampMidLabel(payload.scale, metrics);
    const graphics = [...graphic, ...(title ? [title] : []), ...(mid ? [mid] : [])];

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
    const compact = rect.height < COMPACT_LABEL_HEIGHT || rect.width < COMPACT_LABEL_WIDTH;
    // On the light screen a plot a few dozen pixels tall draws its marks small.
    const strip = stripMarks(rect.height);

    // The overlay marks, unless the Marks toggle has hidden them.
    if (this.marksShown !== false) {
      if (marks) this.addMarks(series, marks, col, row, extent, markInk, panelOf(payload.axes));
      if (axes) this.addShowerAxes(series, axes, col, row);
      if (trajectories && showerKey) {
        this.addTrajectories(series, trajectories, col, row, showerKey);
      }
      if (ensembleAxes) this.addEnsembleAxes(series, ensembleAxes, ensembleMeta, col, row);
      if (windowAxis) this.addWindowAxis(series, windowAxis, col, row);
      if (canonical) {
        addCanonicalCentroids(series, centroids, col, row, symbols, strip);
        addCanonicalAnchors(series, anchors, frame, col, row, symbols, strip);
      } else if (coregistered) {
        // Superimposed showers: the centroid sets by shape, and the mean
        // per-event centroid with its SD cross and 95% t-whiskers.
        addCanonicalCentroids(series, centroids, col, row, symbols, strip);
        addFrameMeanSpread(series, centroids?.frame_mean, col, row, strip);
      } else if (centroids) {
        this.addCentroids(series, centroids, col, row, showVector, strip);
      }
    }

    const provisional = frame?.fit?.provisional
      ? ' (provisional range)' : '';

    const grid = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
    if (coregistered) {
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
    const axisOptions = coregistered ? { onZero: false } : {};

    return {
      backgroundColor: THEME.chartBackground,
      animation: false,
      textStyle: { fontFamily: THEME.fontFamily },
      grid,
      xAxis: spatialAxis(
        axisLabel(symbols.col, compact) + (col.name !== 'z' ? provisional : ''), view.col[0], view.col[1],
        axisOptions,
      ),
      yAxis: spatialAxis(
        axisLabel(symbols.row, compact) + provisional, view.row[0], view.row[1], axisOptions,
      ),
      // Series 0 is the raster; the visualMap must colour it and nothing else.
      visualMap: visualMap(payload.scale, rampPalette(payload.scale, palette), {
        bottomInset: metrics.reservedBottom || 0,
        seriesIndex: 0,
        // The raster's own table: a continuous field (decode.js `renderRaster`).
        field: true,
      }),
      tooltip: tooltipOption(this.tooltipPosition),
      graphic: graphics,
      series,
    };
  }

  /**
   * Replace one overlay of the retained options and redraw at the current
   * size, keeping the displayed window: the windowed axis arrives after the
   * zoom that asked for it, and must not reset the zoom.
   */
  setOverlay(key, value) {
    if (!this.lastOpts) return;
    this.lastOpts = { ...this.lastOpts, [key]: value };
    this.redraw();
  }

  /**
   * Show or hide the overlay marks - anchors, centroids, the ensemble and
   * windowed axes with their wedges, the centre of deposited energy, the
   * trajectories, the D vector - and redraw from the payload in hand at the
   * displayed window, with no request: the card's Marks toggle, so the shower
   * core can be read unobstructed. The raster, the axes, the colour bar and
   * the calorimeter faces stay. The export follows it.
   */
  setMarksShown(shown) {
    this.marksShown = Boolean(shown);
    this.redraw();
  }

  /** Rebuild the option from the retained payload at the current size, keeping the displayed window. */
  redraw() {
    if (!this.payload || !this.raster || !this.lastOpts) return;
    const width = this.element.clientWidth;
    const height = this.element.clientHeight;
    if (!(width > 0 && height > 0)) {
      this.laidOut = null;
      return;
    }
    this.laidOut = { width, height };
    this.setLiveOption(this.buildOption({
      payload: this.payload,
      opts: this.lastOpts,
      raster: this.raster,
      metrics: { width, height },
    }));
  }

  /** The window currently displayed, in millimetres. */
  currentView() {
    if (this.view) return this.view;
    if (!this.payload) return null;
    const extent = this.extent ?? extentOf(this.payload, this.lastOpts ?? {});
    return { col: [...extent.col], row: [...extent.row] };
  }

  /**
   * The Event Inspector's marks: three-dimensional lines and points in the
   * frame's own coordinates, projected onto this panel's two axes.
   *
   * The incident direction forward (dashed) and extrapolated backward
   * (dotted), the first-layer plane (dash-dot; a tilted line on the local
   * X′Z′ panel, a rule at z = z₀ on the others) and the shower's origin (a
   * cross in the shower's colour) - the overlays of the reference notebook's
   * figure. A line whose direction has no component in the panel's plane is
   * skipped, and a mark may name the panels it belongs on.
   */
  addMarks(series, marks, col, row, extent, colour, panelId) {
    const span = Math.max(extent.col[1] - extent.col[0], extent.row[1] - extent.row[0]);
    for (const mark of projectMarks(marks, col.name, row.name, panelId, span)) {
      if (mark.type === 'point') {
        series.push(customMarker({
          name: mark.name, at: mark.at, color: colour ?? THEME.text, sizePx: 6,
          width: 1.6 * THEME.lineAxis, z: 12, tooltip: mark.tooltip,
        }));
        continue;
      }
      const style = {
        forward: { color: THEME.text, width: 1.6 * THEME.lineAxis, dash: 'dashed', opacity: 0.9 },
        backward: { color: THEME.muted, width: 1.4 * THEME.lineAxis, dash: 'dotted', opacity: 0.9 },
        plane: { color: THEME.muted, width: THEME.lineAxis, dash: [6, 3, 2, 3], opacity: 0.8 },
      }[mark.style] ?? { color: THEME.muted, width: THEME.lineAxis, dash: null, opacity: 0.8 };
      series.push(customLine({
        name: mark.name, from: mark.from, to: mark.to, ...style, z: 7, tooltip: mark.tooltip,
      }));
    }
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
        name: `Centre of deposited energy — ${shower.toUpperCase()}`,
        points,
        color: colour,
        width: 1.8 * THEME.lineAxis,
        opacity: 0.95,
        smooth: 0.2,
        z: 8,
        tooltip: `Centre of deposited energy — ${shower.toUpperCase()}<br/>`
          + 'energy-weighted centre of the selection’s summed deposit, per depth layer<br/>'
          + 'a property of the summed picture, not a direction',
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

      const wedge = (points, name, alpha, edge = null) => {
        if (!points) return;
        series.push(customBand({ name, points, color: colour, opacity: alpha, edge }));
      };

      // The two showers' wedges overlap on the YZ panel (both axes start at
      // the origin), so each is drawn at a fraction of the wedge alpha
      // (`wedgeOpacity`: the energy panel's band alpha on the dark card and in
      // print; on the light screen faint washes whose outlines carry them, the
      // spread's dashed and the envelope's thin and solid).
      wedge(lines.band, `Ensemble axis ${label} — spread`, wedgeOpacity('spread', faded), wedgeEdge(colour, faded));
      wedge(lines.envelope, `Ensemble axis ${label} — 95% interval`, wedgeOpacity('envelope', faded),
        envelopeEdge(colour, faded));

      series.push(customPolyline({
        name: `Ensemble axis — ${label}`,
        points: lines.axis,
        color: colour,
        width: axisWidth(),
        dash: 'dashed',
        opacity: faded ? FADE_OPACITY : 0.95,
        z: 9,
        tooltip: () =>
          `Ensemble shower axis — ${label}<br/>` +
          `mean incident direction in the Separation-Aligned (D-Frame) (slope ${formatSigned(Number(lines.slope), 4)})<br/>` +
          `${coherence}, N = ${n}` +
          (faded ? '<br/><i>direction not distinguishable from uniform; drawn faded</i>' : '') +
          (info.label && !faded ? `<br/><i>${info.label}</i>` : ''),
      }));
    }
  }

  /**
   * The windowed ensemble axis of the absolute frame (query/window_axis.py):
   * the mean trajectory of the selected events whose entry point lies in
   * this panel's displayed transverse window, with the sample SD of the
   * per-event trajectories at each depth as an uncapped band and the
   * Student-t 95% interval of the mean as a thin envelope - two quantities,
   * two marks. Faded when the mean lean lies within the fan, which the
   * tooltip says; nothing of the kind is drawn at full extent.
   */
  addWindowAxis(series, block, col, row) {
    if (col.name !== 'z') return;
    for (const [shower, colour] of [['a', THEME.showerA], ['b', THEME.showerB]]) {
      const lines = block?.[shower];
      if (!lines || !lines.axis) continue;
      const label = shower.toUpperCase();
      const faded = Boolean(lines.faded);
      const n = Number.isFinite(lines.n) ? formatInt(lines.n) : '—';
      const of = Number.isFinite(lines.n_selection) ? ` of ${formatInt(lines.n_selection)} selected` : '';
      if (lines.band) {
        series.push(customBand({
          name: `Windowed axis ${label} — spread`, points: lines.band, color: colour,
          opacity: wedgeOpacity('spread', faded), edge: wedgeEdge(colour, faded),
        }));
      }
      if (lines.envelope) {
        series.push(customBand({
          name: `Windowed axis ${label} — 95% interval`, points: lines.envelope, color: colour,
          opacity: wedgeOpacity('envelope', faded), z: 6, edge: envelopeEdge(colour, faded),
        }));
      }
      let coherence;
      if (Number.isFinite(lines.lean_ratio)) coherence = `lean / fan = ${lines.lean_ratio.toFixed(2)}`;
      else if (lines.n >= 2) coherence = 'every direction identical';
      else coherence = lines.label || 'single event';
      const fan = Number.isFinite(lines.fan_deg) ? `, fan ± ${lines.fan_deg.toFixed(1)}°` : '';
      series.push(customPolyline({
        name: `Windowed axis — ${label}`,
        points: lines.axis,
        color: colour,
        width: axisWidth(),
        dash: 'dashed',
        opacity: faded ? FADE_OPACITY : 0.95,
        z: 9,
        tooltip: () =>
          `Windowed ensemble axis — ${label}<br/>` +
          `mean incident trajectory of the ${n} events entering this window${of} ` +
          `(slope ${formatSigned(Number(lines.slope), 4)})<br/>` +
          `${coherence}${fan}` +
          (faded ? '<br/><i>the mean lean lies within the fan: these showers go straight on average; drawn faded</i>' : '') +
          (lines.label && !faded && lines.n >= 2 ? `<br/><i>${lines.label}</i>` : ''),
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

  addCentroids(series, centroids, col, row, showVector, strip = null) {
    for (const [key, pair] of Object.entries(centroids)) {
      if (!pair || !pair.a) continue;
      const style = CENTROID_STYLE[key];
      if (!style) continue;

      // A single-shower experiment has one shower: b is null, and the lone
      // marker is named without a shower letter.
      const lone = pair.b === null || pair.b === undefined;
      for (const [shower, point] of [['A', pair.a], ['B', pair.b]]) {
        if (!point) continue;
        const cx = point[col.name];
        const cy = point[row.name];
        if (cx === null || cy === null || cx === undefined || cy === undefined) continue;
        series.push({
          type: 'scatter',
          name: lone ? pair.label : `${pair.label} — ${shower}`,
          symbol: shower === 'A' ? 'diamond' : 'circle',
          // On a strip the sets keep their order of size, the largest at the strip's anchor size.
          symbolSize: strip ? style.size * (strip.anchor / LARGEST_CENTROID) : style.size * THEME.markerScale,
          data: [[cx, cy]],
          itemStyle: {
            color: shower === 'A' ? THEME.showerA : THEME.showerB,
            borderColor: THEME.canvas,
            borderWidth: strip ? strip.border : 1.5 * THEME.lineAxis,
            opacity: style.opacity,
          },
          tooltip: {
            formatter: () =>
              `${pair.label}<br/>${lone ? '' : `Shower ${shower}<br/>`}` +
              `${symbolOf(col)} = ${formatSigned(cx, 1)} mm<br/>` +
              `${symbolOf(row)} = ${formatSigned(cy, 1)} mm`,
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
          color: THEME.text, width: strip ? strip.line : 1.4 * THEME.lineAxis, type: 'dashed', opacity: 0.9,
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

    const extent = this.extent ?? extentOf(this.payload, this.lastOpts ?? {});
    const col = { lo: extent.col[0], hi: extent.col[1] };
    const row = { lo: extent.row[0], hi: extent.row[1] };

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
    this.viewChanged();
  }

  resetView() {
    this.view = null;
    if (!this.payload) return;
    const extent = this.extent ?? extentOf(this.payload, this.lastOpts ?? {});
    this.chart.setOption({
      xAxis: { min: extent.col[0], max: extent.col[1] },
      yAxis: { min: extent.row[0], max: extent.row[1] },
    });
    this.viewChanged();
  }

  /** Tell the owner the displayed window changed, so text that states it can follow. */
  viewChanged() {
    if (typeof this.onViewChange === 'function') this.onViewChange(this);
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

    const current = () => this.view || this.currentView();

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
    const quantity = payload.scale?.quantity ?? 'density';
    // A mean CAM (attention or attribution) is undefined where no hit is.
    const ratioChannel = quantity === 'gradcam' || quantity === 'shapcam';
    const what = quantity === 'shapcam' ? 'attribution' : 'attention';
    const camEnergy = quantity === 'gradcam_energy' || quantity === 'shapcam_energy';
    const floorRatio = this.lastOpts?.frame?.reconstruction?.floor_ratio
      ?? payload.scale?.floor_ratio ?? 1e-3;
    const floorText = floorLabel({ floor_ratio: floorRatio });
    const muted = (text) => `<span style="color:${THEME.muted}">${text}</span>`;
    // The axes as this panel writes them (D on the D-frame entry panel).
    const symbols = this.symbols ?? { col: symbolOf(col), row: symbolOf(row) };

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
        `${symbols.col} = ${formatSigned(centreX, 1)} mm<br/>` +
        `${symbols.row} = ${formatSigned(centreY, 1)} mm<br/>`;
      // Named at the pointer, not the bin centre: a wedge edge crosses bins.
      // Hidden marks (the Marks toggle) are not named.
      const wedges = col.name === 'z' && this.marksShown !== false
        ? wedgeNotes(this.lastOpts?.ensembleAxes, this.lastOpts?.ensembleMeta, mmX, mmY,
          this.lastOpts?.windowAxis)
        : [];
      const inWedges = wedges.length ? `<br/>${wedges.map(muted).join('<br/>')}` : '';
      const lead = overlay
        ? `${overlay}<div style="border-top:1px solid ${THEME.border};margin:4px 0"></div>`
        : '';
      // The position lives inside `tooltip`: ECharts ignores a top-level
      // `position` on a manual showTip (measured on 5.5.1 - the tip kept the
      // default flip) and honours one given with the formatter. The plain
      // readout stays at the pointer; led by an overlay's explanation, the tip
      // leaves the chart instead.
      const show = (html) => this.chart.dispatchAction({
        type: 'showTip',
        x: px,
        y: py,
        tooltip: {
          formatter: lead + html + inWedges,
          position: overlay ? this.tooltipPosition : this.readoutPosition,
        },
      });

      if (code === (payload.empty_code ?? 0)) {
        if (!floored) {
          if (!overlay) this.chart.dispatchAction({ type: 'hideTip' });
          return;
        }
        let empty;
        if (ratioChannel) empty = `no hits in this bin: ${what} undefined`;
        else if (camEnergy) empty = 'no hits in this bin: Σ E·CAM = 0 (not drawn)';
        else if (reconstructed) empty = 'no reconstructed energy in this bin';
        else empty = 'no energy in this bin';
        show(where + muted(empty));
        return;
      }
      if (floored && code === payload.below_code) {
        let below;
        if (ratioChannel) below = `${what} not drawn: density below ${floorText} of ρ<sub>ref</sub>`;
        else if (quantity === 'shapcam_energy') below = `|Σ E·CAM| below ${floorText} of the selection peak: not drawn`;
        else if (quantity === 'gradcam_energy') below = `Σ E·CAM below ${floorText} of the selection peak: not drawn`;
        else below = `below the display floor (ρ/ρ<sub>ref</sub> &lt; ${floorText}): not drawn`;
        show(where + muted(below));
        return;
      }

      const exact = exactValue(payload, r, c);
      const scale = payload.scale;
      let label = '(quantised)';
      if (exact !== null) label = reconstructed ? '(exact, reconstructed)' : '(exact)';
      const precision = muted(` ${label}`);

      const unitText = UNIT_TEXT[payload.rho_unit ?? scale.rho_unit] ?? 'GeV mm⁻² per event';
      let body;
      if (quantity === 'gradcam') {
        const value = exact !== null ? exact : dequantize(code, scale, payload);
        const weight = this.lastOpts?.weighting === 'count' ? 'count-weighted' : 'energy-weighted';
        body = `<b>${formatSigned(value, 3)}</b> mean Grad-CAM attention${precision}<br/>`
          + muted(`${weight} over this bin's hits`);
      } else if (quantity === 'shapcam') {
        const value = exact !== null ? exact : dequantize(code, scale, payload);
        body = `<b>${formatSigned(value, 3, { plus: true })}</b> mean Shap-CAM attribution (signed)${precision}`;
      } else if (camEnergy && scale.ref) {
        // The raster holds signed ratios to the selection's own peak; the
        // exact list holds the physical sum per bin.
        const physical = exact !== null ? exact : dequantize(code, scale, payload) * scale.ref;
        const ratio = physical / scale.ref;
        const symbol = quantity === 'shapcam_energy' ? 'Σ E·S' : 'Σ E·G';
        const peak = quantity === 'shapcam_energy' ? 'of peak |Σ E·S|' : 'of the selection peak';
        body = `<b>${formatSigned(ratio, 3, { plus: quantity === 'shapcam_energy' })} a.u.</b> ${peak}${precision}<br/>`
          + `${symbol} = ${formatSci(physical, 3)} ${unitText}`;
      } else if (scale.unit === 'a.u.' && scale.rho_ref) {
        // Relative ramp: the raster holds ratios to rho_ref, the exact list
        // holds physical densities. Show both, plus the bin the value is a
        // density over, so the number can be quoted either way.
        const rho = exact !== null ? exact : dequantize(code, scale, payload) * scale.rho_ref;
        const ratio = rho / scale.rho_ref;
        const binW = (col.hi - col.lo) / cols;
        const binH = (row.hi - row.lo) / rows;
        body =
          `<b>${ratio.toFixed(3)} a.u.</b> of ρ<sub>ref</sub>${precision}<br/>` +
          `⟨ρ⟩ = ${formatSci(rho, 3)} ${unitText}<br/>` +
          muted(`${binW.toFixed(1)} × ${binH.toFixed(1)} mm ${reconstructed ? 'display bin' : 'bin'} · ` +
            `ρ<sub>ref</sub> = ${formatSci(scale.rho_ref, 3)} (${scale.norm === 'dataset' ? 'dataset' : 'selection'} peak)`);
      } else {
        const value = exact !== null ? exact : dequantize(code, scale, payload);
        const unit = scale.unit === 'GeV' ? 'GeV' : (UNIT_TEXT[scale.unit] ?? '');
        // The inspector's panels hold an areal density: say what it is per.
        const cell = scale.unit === 'GeV/mm^2'
          ? `<br/>${muted(`projected energy per mm² of this ${payload.axes.col.uniform ? 'bin' : 'cell'}`)}`
          : '';
        body = `<b>${formatSci(value, 3)} ${unit}</b>${precision}${cell}`;
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

  /**
   * Take the picture down and let go of everything retained, so neither a
   * relayout nor a zoom can repaint it: the page's experiment changed, and
   * the previous experiment's data must not stay on screen. The pointer
   * handlers go too (they read the payload); the next `render` attaches them
   * afresh, and starts from the full extent.
   */
  clear() {
    this.chart.clear();
    const zr = this.chart.getZr?.();
    for (const [event, key] of [['mousewheel', 'wheelHandler'], ['mousedown', 'downHandler'],
      ['mousemove', 'moveHandler'], ['mouseup', 'upHandler'], ['globalout', 'upHandler'],
      ['mousemove', 'tooltipHandler']]) {
      if (this[key]) zr?.off(event, this[key]);
    }
    for (const key of ['wheelHandler', 'downHandler', 'moveHandler', 'upHandler', 'tooltipHandler']) this[key] = null;
    this.payload = null;
    this.raster = null;
    this.lastOpts = null;
    this.extent = null;
    this.symbols = null;
    this.view = null;
    this.viewKey = null;
    this.drag = null;
    this.liveGrid = null;
    this.laidOut = null;
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
function wedgeNotes(block, meta, z, t, windowAxis = null) {
  const notes = [];
  for (const shower of ['a', 'b']) {
    const label = shower.toUpperCase();
    const lines = block?.[shower];
    if (lines && lines.axis) {
      if (insideWedge(lines.band, z, t)) {
        notes.push(`in the dispersion band of axis ${label}: ± sample SD of the per-event slopes`
          + (lines.dof_note ? ` (${lines.dof_note})` : ''));
      }
      if (insideWedge(lines.envelope, z, t)) {
        notes.push(`in the 95% interval of the mean of axis ${label}: `
          + `± t<sub>0.975,N−1</sub>·SD/√N, N = ${meta?.[shower]?.n ?? '—'}`);
      }
    }
    const windowed = windowAxis?.[shower];
    if (windowed && windowed.axis) {
      if (insideWedge(windowed.band, z, t)) {
        notes.push(`in the dispersion band of the windowed axis ${label}: ± sample SD of the per-event `
          + `trajectories at this depth${windowed.dof_note ? ` (${windowed.dof_note})` : ''}`);
      }
      if (insideWedge(windowed.envelope, z, t)) {
        notes.push(`in the 95% interval of the mean of the windowed axis ${label}: `
          + `± t<sub>0.975,N−1</sub>·SD/√N, N = ${windowed.n ?? '—'}`);
      }
    }
  }
  return notes;
}

/**
 * The extent a panel's axes span: the caller's `window` ({col, row} in
 * millimetres) when given - the Event Inspector draws one equal half-width
 * window round a raster that covers only the populated part - else the
 * raster's own edges.
 */
export function extentOf(payload, opts) {
  const win = opts?.window;
  const { col, row } = payload.axes;
  const ok = (r) => Array.isArray(r) && r.length === 2 && r.every(Number.isFinite) && r[1] > r[0];
  return {
    col: ok(win?.col) ? [win.col[0], win.col[1]] : [col.lo, col.hi],
    row: ok(win?.row) ? [win.row[0], win.row[1]] : [row.lo, row.hi],
  };
}

function sameExtent(a, b) {
  return a.col[0] === b.col[0] && a.col[1] === b.col[1] && a.row[0] === b.row[0] && a.row[1] === b.row[1];
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
function clampView(view, extent, isometric = false) {
  const axes = { col: { lo: extent.col[0], hi: extent.col[1] }, row: { lo: extent.row[0], hi: extent.row[1] } };
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
  // A single-shower experiment's energy-weighted centroid: one shower, no
  // network split and no separation vector.
  energy_voxel: { size: 15, opacity: 1.0, vector: false },
  pred_voxel: { size: 11, opacity: 0.75, vector: false },
  truth_dataset: { size: 9, opacity: 0.5, vector: false },
  // The canonical frame's replacement for truth_dataset: the dataset centroids
  // averaged after co-registration, where averaging a position is meaningful.
  canonical_mean: { size: 9, opacity: 0.5, vector: false },
};

/** The largest lab centroid marker, which a strip draws at its anchor size (`stripMarks`). */
const LARGEST_CENTROID = Math.max(...Object.values(CENTROID_STYLE).map((style) => style.size));
