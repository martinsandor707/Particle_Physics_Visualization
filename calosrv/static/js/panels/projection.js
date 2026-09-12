/* One spatial projection panel: raster, axes in millimetres, centroid overlay.
 *
 * The raster is drawn as an ECharts `graphic.image` positioned from the
 * panel's *physical extents*, never from the matrix shape. That separation is
 * what satisfies the isometric requirement in CLAUDE.md section 2: the native
 * lattice is 211 x 104 over a region that is very nearly square, so a panel
 * sized from the matrix shape would stretch the x axis by a factor of two. The
 * bitmap is simply scaled to whatever pixel rectangle the millimetre extents
 * map to.
 *
 * For the XY panel the aspect ratio is additionally *enforced* to 1:1, so a
 * millimetre along x is the same number of pixels as a millimetre along y and
 * the separation vector D can be read directly off the picture. The depth
 * panels span 5200 mm transverse against 1210 mm of depth; forcing 1:1 there
 * would leave a sliver of usable height, so they fill the card and are labelled
 * with their true extents instead.
 */

import { renderRaster, exactValue, dequantize, cellAt, cellCentre } from '../decode.js';
import { THEME, formatSci, spatialAxis, visualMap } from '../scale.js';

const AXIS_LABEL = {
  x: 'x [mm]',
  y: 'y [mm]',
  z: 'z — depth [mm]',
};

export class ProjectionPanel {
  constructor(elementId, { isometric = false } = {}) {
    this.element = document.getElementById(elementId);
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    this.isometric = isometric;
    this.payload = null;
    this.raster = null;
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

  render(payload, { palette, centroids = null, showVector = false }) {
    this.payload = payload;
    this.palette = palette;
    this.raster = renderRaster(payload, palette);

    const col = payload.axes.col;
    const row = payload.axes.row;
    const rect = this.gridRect(col.hi - col.lo, row.hi - row.lo);

    const series = [];
    const graphics = [];

    // The bitmap is placed by pixel rectangle; ECharts converts data
    // coordinates to pixels only after the grid is laid out, so the image is
    // positioned with the same rect the grid uses.
    graphics.push({
      type: 'image',
      id: 'raster',
      style: {
        image: this.raster.canvas,
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      },
      z: -10,
      silent: true,
    });

    if (centroids) {
      for (const [key, pair] of Object.entries(centroids)) {
        if (!pair || !pair.a) continue;
        const style = CENTROID_STYLE[key];
        if (!style) continue;
        for (const [shower, point] of [['A', pair.a], ['B', pair.b]]) {
          const cx = point[col.name];
          const cy = point[row.name];
          if (cx === null || cy === null) continue;
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
        if (showVector && style.vector && pair.separation_mm !== null) {
          const ax = pair.a[col.name];
          const ay = pair.a[row.name];
          const bx = pair.b[col.name];
          const by = pair.b[row.name];
          if ([ax, ay, bx, by].every((v) => v !== null && v !== undefined)) {
            series.push({
              type: 'line',
              name: 'Separation D',
              data: [[ax, ay], [bx, by]],
              symbol: 'none',
              lineStyle: { color: THEME.text, width: 1.2, type: 'dashed', opacity: 0.8 },
              silent: true,
              z: 9,
              markPoint: {
                symbol: 'rect',
                symbolSize: 0,
                data: [{
                  coord: [(ax + bx) / 2, (ay + by) / 2],
                  label: {
                    show: true,
                    formatter: `D = ${pair.separation_mm.toFixed(0)} mm`,
                    color: THEME.text,
                    backgroundColor: 'rgba(13,17,23,0.82)',
                    padding: [3, 5],
                    borderRadius: 3,
                    fontSize: 10,
                  },
                }],
              },
            });
          }
        }
      }
    }

    this.chart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      grid: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      },
      xAxis: spatialAxis(AXIS_LABEL[col.name] || col.name, col.lo, col.hi),
      yAxis: spatialAxis(AXIS_LABEL[row.name] || row.name, row.lo, row.hi),
      visualMap: visualMap(payload.scale, palette),
      graphic: graphics,
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(22,27,34,0.95)',
        borderColor: THEME.border,
        textStyle: { color: THEME.text, fontSize: 11 },
      },
      series,
    }, { notMerge: true });

    this.attachCellTooltip(rect, col, row);
  }

  /**
   * Hover readout for the raster itself.
   *
   * ECharts' own tooltip works on series items, and the raster is not one, so
   * pointer position is inverted through the extents to recover a cell index.
   * The exact value is preferred where the payload carries one; otherwise the
   * quantised code is inverted, and the tooltip says which it is showing so a
   * reader is never misled about precision.
   */
  attachCellTooltip(rect, col, row) {
    const zr = this.chart.getZr();
    if (this.tooltipHandler) zr.off('mousemove', this.tooltipHandler);

    const { codes, rows, cols } = this.raster;
    const payload = this.payload;

    this.tooltipHandler = (event) => {
      const px = event.offsetX;
      const py = event.offsetY;
      if (px < rect.left || px > rect.left + rect.width ||
          py < rect.top || py > rect.top + rect.height) {
        this.chart.dispatchAction({ type: 'hideTip' });
        return;
      }
      // Pointer position converts to millimetres first, then to a cell index
      // through the real edges. Assuming uniform cells here would name the
      // wrong cell on the irregular transverse axis.
      const mmX = col.lo + ((px - rect.left) / rect.width) * (col.hi - col.lo);
      const mmY = row.lo + (1 - (py - rect.top) / rect.height) * (row.hi - row.lo);
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

const CENTROID_STYLE = {
  truth_voxel: { size: 15, opacity: 1.0, vector: true },
  pred_voxel: { size: 11, opacity: 0.75, vector: false },
  truth_dataset: { size: 9, opacity: 0.5, vector: false },
};
