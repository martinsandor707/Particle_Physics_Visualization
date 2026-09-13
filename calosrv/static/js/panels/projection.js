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
import { THEME, formatSci, spatialAxis, visualMap } from '../scale.js';

const AXIS_LABEL = {
  x: 'x [mm]',
  y: 'y [mm]',
  z: 'z — depth [mm]',
};

/** Fraction of the fitted region added as breathing room on each side. */
const ROI_PADDING = 0.06;

/** Range multiplier per wheel notch. */
const ZOOM_STEP = 1.18;

export class ProjectionPanel {
  constructor(elementId, { isometric = false } = {}) {
    this.element = document.getElementById(elementId);
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    this.isometric = isometric;
    this.payload = null;
    this.raster = null;
    this.view = null;   // {col: [lo, hi], row: [lo, hi]} in mm; null = full extent
    this.drag = null;
    window.addEventListener('resize', () => this.chart.resize());
  }

  /**
   * Pixel rectangle the data region should occupy.
   *
   * With `isometric`, the shorter physical axis is letterboxed so both axes
   * share one millimetre-per-pixel factor.
   */
  gridRect(colSpan, rowSpan) {
    const padding = { left: 52, right: 74, top: 12, bottom: 40 };
    const width = this.element.clientWidth - padding.left - padding.right;
    const height = this.element.clientHeight - padding.top - padding.bottom;
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

  render(payload, {
    palette, centroids = null, showVector = false,
    axes = null, trajectories = null, showerKey = null,
  }) {
    // A different detector extent means a different experiment, and a window
    // panned over the previous one would be meaningless against the new.
    if (this.payload && !sameExtent(this.payload, payload)) this.view = null;

    this.payload = payload;
    this.palette = palette;
    this.raster = renderRaster(payload, palette);

    const col = payload.axes.col;
    const row = payload.axes.row;
    // The displayed window. The grid is letterboxed from the *full* extent so
    // the plot area does not jump around as the view changes.
    const view = this.view || { col: [col.lo, col.hi], row: [row.lo, row.hi] };
    const rect = this.gridRect(col.hi - col.lo, row.hi - row.lo);
    const canvas = this.raster.canvas;

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

    if (axes) this.addShowerAxes(series, axes, col, row);
    if (trajectories && showerKey) {
      this.addTrajectories(series, trajectories, col, row, showerKey);
    }
    if (centroids) this.addCentroids(series, centroids, col, row, showVector);

    this.chart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      grid: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      },
      xAxis: spatialAxis(AXIS_LABEL[col.name] || col.name, view.col[0], view.col[1]),
      yAxis: spatialAxis(AXIS_LABEL[row.name] || row.name, view.row[0], view.row[1]),
      visualMap: visualMap(payload.scale, palette),
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(22,27,34,0.95)',
        borderColor: THEME.border,
        textStyle: { color: THEME.text, fontSize: 11 },
      },
      series,
    }, { notMerge: true });

    this.attachCellTooltip(col, row);
    this.attachNavigation();
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
        lineStyle: { color: colour, width: 1.8, opacity: 0.95 },
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
            color: colour, width: 1, type: 'dashed', opacity: 0.45,
          },
          z: 6,
          clip: true,
          silent: true,
        });
      }
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
          symbolSize: style.size,
          data: [[cx, cy]],
          itemStyle: {
            color: shower === 'A' ? THEME.showerA : THEME.showerB,
            borderColor: THEME.canvas,
            borderWidth: 1.5,
            opacity: style.opacity,
          },
          tooltip: {
            formatter: () =>
              `${pair.label}<br/>Shower ${shower}<br/>` +
              `${col.name} = ${cx.toFixed(1)} mm<br/>` +
              `${row.name} = ${cy.toFixed(1)} mm`,
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
        lineStyle: { color: THEME.text, width: 1.4, type: 'dashed', opacity: 0.9 },
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
              backgroundColor: 'rgba(13,17,23,0.88)',
              borderColor: THEME.border,
              borderWidth: 1,
              padding: [3, 5],
              borderRadius: 3,
              fontSize: 10,
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
      // otherwise the 1:1 guarantee would hold only at full zoom-out.
      const want = Math.max(c1 - c0, r1 - r0);
      [c0, c1] = centreOn(c0, c1, want);
      [r0, r1] = centreOn(r0, r1, want);
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
      const value = exact !== null ? exact : dequantize(code, payload.scale, payload);
      const centreX = cellCentre(col, cols, c);
      const centreY = cellCentre(row, rows, r);
      const unit = payload.scale.unit === 'GeV' ? 'GeV' : '';

      this.chart.dispatchAction({
        type: 'showTip',
        x: px,
        y: py,
        position: [px + 12, py - 8],
        tooltip: {
          formatter:
            `${col.name} = ${centreX.toFixed(1)} mm<br/>` +
            `${row.name} = ${centreY.toFixed(1)} mm<br/>` +
            `<b>${formatSci(value, 3)} ${unit}</b>` +
            `<span style="color:${THEME.muted}"> ${exact !== null ? '(exact)' : '(quantised)'}</span>`,
        },
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
};
