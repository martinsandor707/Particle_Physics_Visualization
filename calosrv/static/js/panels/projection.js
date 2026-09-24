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
 */

import {
  renderRaster, exactValue, dequantize, cellAt, cellCentre, occupiedBounds,
} from '../decode.js';
import { THEME, formatSci, spatialAxis, visualMap, axisPadding, rampTitle } from '../scale.js';

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

/** The symbol an axis is written with on screen. */
export function symbolOf(axis) {
  return axis.symbol ?? axis.name;
}

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
    window.addEventListener('resize', () => this.chart.resize());
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

    this.chart.setOption(this.buildOption({
      payload,
      opts,
      raster: this.raster,
      metrics: {
        width: this.element.clientWidth, height: this.element.clientHeight,
      },
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
    if (centroids) this.addCentroids(series, centroids, col, row, showVector && !anchors);
    if (anchors) this.addAnchors(series, anchors, frame, col, row, compact);

    const provisional = frame?.fit?.provisional
      ? ' (provisional range)' : '';

    return {
      backgroundColor: THEME.chartBackground,
      animation: false,
      textStyle: { fontFamily: THEME.fontFamily },
      grid: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      },
      xAxis: spatialAxis(
        axisLabel(col, compact) + (col.name !== 'z' ? provisional : ''), view.col[0], view.col[1],
      ),
      yAxis: spatialAxis(axisLabel(row, compact) + provisional, view.row[0], view.row[1]),
      visualMap: visualMap(payload.scale, palette, {
        bottomInset: metrics.reservedBottom || 0,
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
      series.push({
        type: 'line',
        name: `Measured axis — ${shower.toUpperCase()}`,
        data: points,
        symbol: 'none',
        smooth: 0.2,
        lineStyle: { color: colour, width: 1.8 * THEME.lineAxis, opacity: 0.95 },
        z: 8,
        clip: true,
        tooltip: {
          formatter: () =>
            `Measured shower axis — ${shower.toUpperCase()}<br/>` +
            'energy-weighted centroid per depth layer',
        },
      });
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

      const wedge = (points, name, alpha, tip) => {
        if (!points) return;
        series.push({
          type: 'custom',
          name,
          silent: false,
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
          tooltip: { formatter: () => tip },
        });
      };

      // The two showers' wedges overlap on the YZ panel (both axes start at
      // the origin), so each is drawn at a fraction of the band alpha the
      // energy panel uses for a single band.
      wedge(lines.band, `Ensemble axis ${label} — spread`, faded ? 0.05 : THEME.bandAlpha * 0.6,
        `Ensemble axis ${label} — dispersion band<br/>` +
        `± sample SD of the per-event slopes${lines.dof_note ? ` (${lines.dof_note})` : ''}: ` +
        'where individual showers go, not the uncertainty of the mean.');
      wedge(lines.envelope, `Ensemble axis ${label} — 95% interval`, faded ? 0.12 : THEME.bandAlpha * 1.4,
        `Ensemble axis ${label} — 95% interval of the mean<br/>` +
        `± t<sub>0.975,N−1</sub>·SD/√N over N = ${n} events: how well the ensemble axis is known.`);

      series.push({
        type: 'line',
        name: `Ensemble axis — ${label}`,
        data: lines.axis,
        symbol: 'none',
        lineStyle: {
          color: colour, width: 1.8 * THEME.lineAxis, type: 'dashed',
          opacity: faded ? FADE_OPACITY : 0.95,
        },
        z: 9,
        clip: true,
        tooltip: {
          formatter: () =>
            `Ensemble shower axis — ${label}<br/>` +
            `mean incident direction in the canonical frame (slope ${Number(lines.slope).toFixed(4)})<br/>` +
            `${coherence}, N = ${n}` +
            (faded ? '<br/><i>direction not distinguishable from uniform; drawn faded</i>' : '') +
            (info.label && !faded ? `<br/><i>${info.label}</i>` : ''),
        },
      });
    }
  }

  /**
   * The anchors of the canonical frame: shower A at (−⟨D_entry⟩/2, 0), B at
   * (+⟨D_entry⟩/2, 0), each with an uncapped bar for the sample spread of the
   * entry separation, and the labelled separation vector between them.
   */
  addAnchors(series, anchors, frame, col, row, compact = false) {
    const depthPanel = col.name === 'z';
    const place = (anchor) => {
      // XY: (x', y'). Depth panels: [z' = 0, transverse]; on YZ both anchors
      // sit at the origin because the frame puts the showers on y' = 0.
      if (!depthPanel) return [anchor.x, anchor.y];
      return [0.0, row.name === 'x' ? anchor.x : anchor.y];
    };
    const spreadPoints = (anchor) => {
      if (!anchor.spread) return null;
      if (!depthPanel) return [[anchor.spread[0], anchor.y], [anchor.spread[1], anchor.y]];
      if (row.name !== 'x') return null;
      return [[0.0, anchor.spread[0]], [0.0, anchor.spread[1]]];
    };

    if (depthPanel && row.name !== 'x' && anchors.a && anchors.b) {
      // On the Y′Z′ panel both anchors project onto the origin: one marker,
      // one honest tooltip, instead of a circle hiding a diamond.
      series.push({
        type: 'scatter',
        name: 'Anchors A and B',
        symbol: 'circle',
        symbolSize: 12 * THEME.markerScale,
        data: [[0.0, 0.0]],
        itemStyle: {
          color: THEME.text, borderColor: THEME.canvas, borderWidth: 1.5 * THEME.lineAxis,
        },
        z: 11,
        tooltip: {
          formatter: () =>
            'Canonical anchors — showers A and B<br/>' +
            'both entry points lie on the shower plane y′ = 0; they are separated along x′, ' +
            `at ∓⟨D_entry⟩/2 = ∓${Math.abs(anchors.b.x).toFixed(1)} mm, which this panel projects out.`,
        },
      });
      return;
    }

    for (const [shower, anchor] of Object.entries(anchors)) {
      if (!anchor) continue;
      const label = shower.toUpperCase();
      const colour = shower === 'a' ? THEME.showerA : THEME.showerB;
      const spread = spreadPoints(anchor);
      if (spread) {
        series.push({
          type: 'line',
          name: `Anchor ${label} — spread`,
          data: spread,
          symbol: 'none',
          lineStyle: { color: colour, width: 6 * THEME.lineAxis, opacity: 0.35 },
          z: 9,
          clip: true,
          tooltip: {
            formatter: () =>
              `Anchor ${label} — spread of D_entry/2 across events<br/>` +
              `± sample SD${anchor.dof_note ? ` (${anchor.dof_note})` : ''}: dispersion, not uncertainty of the mean.`,
          },
        });
      }
      series.push({
        type: 'scatter',
        name: `Anchor ${label}`,
        symbol: shower === 'a' ? 'diamond' : 'circle',
        symbolSize: 15 * THEME.markerScale,
        data: [place(anchor)],
        itemStyle: {
          color: colour, borderColor: THEME.canvas, borderWidth: 1.5 * THEME.lineAxis,
        },
        z: 11,
        tooltip: {
          formatter: () =>
            `Canonical anchor — shower ${label}<br/>` +
            `back-projected entry point at ${shower === 'a' ? '−' : '+'}⟨D_entry⟩/2 = ${anchor.x.toFixed(1)} mm` +
            (Number.isFinite(anchor.se95) ? `<br/>95% interval of the mean anchor ± ${anchor.se95.toFixed(1)} mm (N = ${anchor.n})` : ''),
        },
      });
    }

    if (depthPanel || !anchors.a || !anchors.b) return;
    const dEntry = frame?.d_entry?.mean;
    const dData = frame?.d_dataset?.mean;
    // The long form names both definitions; a single-column figure has no
    // room for it, and its caption spells the two out anyway.
    const text = compact
      ? [
        Number.isFinite(dEntry) ? `⟨D_entry⟩ ${dEntry.toFixed(0)} mm` : null,
        Number.isFinite(dData) ? `⟨D⟩ ${dData.toFixed(0)} mm` : null,
      ].filter(Boolean).join(' · ')
      : [
        Number.isFinite(dEntry) ? `⟨D_entry⟩ = ${dEntry.toFixed(0)} mm (entry)` : null,
        Number.isFinite(dData) ? `⟨D⟩ = ${dData.toFixed(0)} mm (dataset, 3-D)` : null,
      ].filter(Boolean).join(' · ');
    series.push({
      type: 'line',
      name: 'Entry separation',
      data: [[anchors.a.x, anchors.a.y], [anchors.b.x, anchors.b.y]],
      symbol: 'none',
      lineStyle: { color: THEME.text, width: 1.4 * THEME.lineAxis, type: 'dashed', opacity: 0.9 },
      silent: true,
      z: 11,
      clip: true,
      markPoint: {
        symbol: 'rect',
        symbolSize: 0,
        data: [{
          coord: [0, 0],
          label: {
            show: true,
            formatter: text,
            color: THEME.text,
            backgroundColor: THEME.labelBg,
            borderColor: THEME.border,
            borderWidth: 1,
            padding: [3, 5],
            borderRadius: 3,
            fontSize: THEME.fontLabel,
            fontFamily: THEME.fontFamily,
            offset: [0, -18],
          },
        }],
      },
    });
  }

  /** The front and back faces of the calorimeter on a depth panel. */
  addDepthBounds(series, bounds, col, row) {
    if (col.name !== 'z') return;
    for (const [depth, name] of [[bounds.front, 'front face'], [bounds.back, 'back face']]) {
      if (!Number.isFinite(depth)) continue;
      series.push({
        type: 'line',
        name: `Calorimeter ${name}`,
        data: [[depth, row.lo], [depth, row.hi]],
        symbol: 'none',
        lineStyle: { color: THEME.muted, width: THEME.lineAxis, opacity: 0.7 },
        z: 4,
        clip: true,
        tooltip: {
          formatter: () =>
            `Calorimeter ${name} at z′ = ${depth.toFixed(1)} mm<br/>` +
            'The transverse outline rotates with each event and has no ensemble image.',
        },
      });
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
   * Zoom to the bounding box of the active hits.
   *
   * For the isometric panel the narrower span is widened so both axes keep the
   * same millimetre-per-pixel factor; without that the "1:1" guarantee would
   * hold only at full zoom-out.
   */
  /**
   * Zoom to where the energy actually is.
   *
   * Returns 'fitted', 'full' when the hits already fill the detector and there
   * is nothing to tighten, or 'empty'. The caller reports the last two, because
   * a button that silently does nothing reads as broken.
   */
  autoFitRoI() {
    if (!this.payload || !this.raster) return 'empty';
    const bounds = occupiedBounds(this.payload, this.raster);
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

    this.setView({
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
   */
  attachCellTooltip(col, row) {
    const zr = this.chart.getZr();
    if (this.tooltipHandler) zr.off('mousemove', this.tooltipHandler);

    const { codes, rows, cols } = this.raster;
    const payload = this.payload;

    this.tooltipHandler = (event) => {
      const px = event.offsetX;
      const py = event.offsetY;

      let data;
      try {
        data = this.chart.convertFromPixel({ gridIndex: 0 }, [px, py]);
      } catch {
        return;
      }
      if (!data || !Number.isFinite(data[0]) || !Number.isFinite(data[1])) return;

      const [mmX, mmY] = data;
      if (mmX < col.lo || mmX > col.hi || mmY < row.lo || mmY > row.hi) {
        this.chart.dispatchAction({ type: 'hideTip' });
        return;
      }

      const c = cellAt(col, cols, mmX);
      const r = cellAt(row, rows, mmY);
      const code = codes[r * cols + c];
      if (code === (payload.empty_code ?? 0)) {
        this.chart.dispatchAction({ type: 'hideTip' });
        return;
      }

      const exact = exactValue(payload, r, c);
      const centreX = cellCentre(col, cols, c);
      const centreY = cellCentre(row, rows, r);
      const scale = payload.scale;
      const where =
        `${symbolOf(col)} = ${centreX.toFixed(1)} mm<br/>` +
        `${symbolOf(row)} = ${centreY.toFixed(1)} mm<br/>`;
      const precision = `<span style="color:${THEME.muted}"> ${exact !== null ? '(exact)' : '(quantised)'}</span>`;

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
          `<span style="color:${THEME.muted}">${binW.toFixed(0)} × ${binH.toFixed(1)} mm bin · ` +
          `ρ<sub>ref</sub> = ${formatSci(scale.rho_ref, 3)} (${scale.norm === 'dataset' ? 'dataset' : 'selection'} peak)</span>`;
      } else {
        const value = exact !== null ? exact : dequantize(code, scale, payload);
        const unit = scale.unit === 'GeV' ? 'GeV' : '';
        body = `<b>${formatSci(value, 3)} ${unit}</b>${precision}`;
      }

      this.chart.dispatchAction({
        type: 'showTip',
        x: px,
        y: py,
        position: [px + 12, py - 8],
        tooltip: { formatter: where + body },
      });
    };
    zr.on('mousemove', this.tooltipHandler);
  }

  resize() {
    this.chart.resize();
  }

  setBusy(busy) {
    this.element.classList.toggle('is-busy', busy);
  }
}

/* ------------------------------------------------------------- helpers -- */

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
