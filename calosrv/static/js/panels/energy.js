/* Reconstructed energy distribution against separation distance D.
 *
 * ## Encoding
 *
 * Separation slice is carried by *colour*, shower identity by *line style*:
 *
 *   D-slice              a distinct stop from a sequential ramp
 *   Shower A             solid
 *   Shower B             dashed
 *   Isolated reference   dotted, in neutral text/muted grey, its own legend
 *
 * Slice-as-colour is what makes the broadening of the resolution with D visible
 * at a glance, which is the panel's whole point. The stops are drawn from
 * `categoricalStops`, which samples a restricted sub-range of the ramp: the
 * full Viridis range starts at #440154, which as a one-pixel line on the
 * #0d1117 canvas is effectively invisible.
 *
 * Moving the isolated references to a neutral dotted style frees the shower
 * pink and blue for the centroid markers on the spatial panels, so one colour
 * no longer means two different things across the dashboard.
 *
 * ## Low statistics: numbers and marks are gated separately
 *
 * The server reports mu and sigma from N = 2 and says which estimator produced
 * them. What the sample size gates is which *marks* are drawn, because a mark
 * makes a claim about shape that a table cell does not:
 *
 *   N >= 15   density histogram + fitted curve
 *   N >= 8    fitted curve, de-weighted, plus the events beneath it
 *   N <  8    the events and the summary markers only
 *
 * A `density=True` histogram divides by N * bin_width, so at small N a single
 * event produces a spike whose height is set by the binning rather than by
 * physics - that is why the histogram, specifically, has the highest floor.
 *
 * ## Two interval marks, deliberately different
 *
 * The capped whisker on the mean marker is the *inferential uncertainty of the
 * mean*: mu +/- t(0.975, N-1) * s/sqrt(N). The uncapped shaded band behind it is
 * the *dispersion of the events*, mu +/- s. They differ by a factor of sqrt(N)
 * and answer opposite questions, so they never share a mark, and each tooltip
 * names which one it is.
 *
 * ## The y axis is set by robust evidence only
 *
 * yMax comes from the N >= 15 series alone. A curve peak is 1/(sigma*sqrt(2pi))
 * with a poorly determined sigma, so letting a thin slice set the scale would
 * flatten every well-measured slice beside it. Thin curves adapt to the range
 * and, where they overflow it, are clipped with a caret and named in the
 * footnote. The axis starts strictly at zero, as CLAUDE.md section 2 requires
 * of a probability density.
 */

import {
  THEME, formatNumber, formatInt, formatPercent, axisPadding, typographic,
} from '../scale.js';
import { categoricalStops } from '../palette.js';
import { fitsWidth, legendRows, wrapText } from '../textfit.js';
import { hideTooltipOnScroll, plotBoxFromGrid, tooltipOption, tooltipPosition } from './tooltip.js';

/** Headroom above the tallest robust mark. */
const Y_HEADROOM = 1.15;

/** Density range used only when nothing estimable is drawn; axis is unlabelled. */
const FALLBACK_Y_MAX = 1.0;

/* Pixel offsets above the y = 0 baseline. Nothing here is a density value: the
 * strip occupies a reserved band at the foot of the plot whose height is a
 * drawing decision, and every tooltip in it says so.
 *
 * Every low-statistics series gets a row of its own. Line style separates the
 * showers everywhere else on the panel, but a tick, a band and a whisker have
 * no line style to carry it, and two showers of one slice share a colour by
 * design - so rows are what keep them apart, across slices as well as showers. */
const STRIP_BASE_PX = 8;
const ROW_GAP_MIN_PX = 14;
const ROW_GAP_MAX_PX = 22;
/** Share of the plot height the strip band may occupy before rows tighten. */
const STRIP_BAND_SHARE = 0.32;
/** Offset of the summary marks above their row's event ticks. */
const MARKER_LIFT_PX = 9;
const BAND_HEIGHT_PX = 7;
const CAP_PX = 4;

/** Plot-area height as a fraction of its width, for a publication figure. */
const ENERGY_PLOT_ASPECT = 0.62;

const STRIP_CAPTION =
  'event strip — vertical positions here are drawing offsets, not densities';
const STRIP_CAPTION_SHORT = 'event strip — offsets, not densities';

export class EnergyPanel {
  constructor(elementId, tableId, noteId) {
    this.element = document.getElementById(elementId);
    this.tableElement = document.getElementById(tableId);
    this.noteElement = noteId ? document.getElementById(noteId) : null;
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    // As in ProjectionPanel: the on-screen grid, recorded at each live
    // setOption, is the plot area the tooltip is kept off. Every tip here
    // explains a curve or a mark, so all of them leave the chart.
    this.liveGrid = null;
    this.tooltipPosition = tooltipPosition(this.chart, () => plotBoxFromGrid(
      this.liveGrid, this.chart.getWidth(), this.chart.getHeight(),
    ));
    hideTooltipOnScroll(this.chart);
    this.kind = 'energy';
    this.lastPayload = null;
    this.lastOpts = null;
    this.lastAxis = null;
    window.addEventListener('resize', () => this.chart.resize());
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;

    const { option, notices, table } = this.buildOption({
      payload,
      opts,
      metrics: {
        width: this.element.clientWidth, height: this.element.clientHeight,
      },
    });
    this.liveGrid = option.grid ?? null;
    this.chart.setOption(option, { notMerge: true });
    this.renderNotices(payload, notices.shown, notices);
    this.renderTable(payload, table.shown, table.sliceColor, table.counts);
  }

  /**
   * Figure dimensions for a publication export of the given printed width.
   *
   * The legend allowance is measured rather than assumed: at single-column
   * width a five-slice selection wraps its legend over several rows, and a
   * fixed reservation would either clip it or leave a band of white.
   */
  exportMetrics(width) {
    const pad = axisPadding();
    const plotWidth = Math.max(80, width - pad.left - pad.right);
    // Legend wrapping is a function of the figure width, so the row count is
    // measured at that width rather than carried over from the on-screen
    // render, where the panel is twice as wide and the type two points smaller.
    // The option built here is discarded; only the row count it records is kept.
    this.buildOption({
      payload: this.lastPayload,
      opts: this.lastOpts || {},
      metrics: { width, height: 400 },
    });
    const rows = this.lastLegendRows || 1;
    const legendPx = rows * 1.6 * THEME.fontLabel;
    return {
      width,
      height: Math.round(pad.top + pad.bottom + legendPx
        + plotWidth * ENERGY_PLOT_ASPECT),
    };
  }

  /**
   * The chart option, plus the data the HTML side-panels need.
   *
   * Split out of `render` so the exporter can rebuild the panel under print
   * tokens at a different size. The strip-row pitch, the reserved-band height
   * and the legend row count are all functions of the host geometry, so they
   * must be recomputed for the figure rather than carried over from the screen.
   */
  buildOption({ payload, opts, metrics, graphic = [] }) {
    const { palette = 'viridis', kind = 'pred', shower = 'both' } = opts;
    const pad = axisPadding();
    const plotWidthPx = Math.max(
      80, (metrics.width || 600) - pad.left - pad.right,
    );
    const slices = payload.slices || [];
    const counts = payload.slice_counts || {};
    const axis = payload.axis || {};
    const thresholds = payload.thresholds || {};

    const stops = categoricalStops(
      palette, Math.max(3, slices.length), THEME.categorical,
    );
    const sliceColor = new Map(slices.map((s, i) => [s.index, stops[i]]));

    const shown = (payload.series || []).filter(
      (s) => s.kind === kind && (shower === 'both' || s.shower === shower),
    );

    /* ---- pass 1: density marks, and the peaks they are allowed to scale --- */
    const series = [];
    const legendNames = [];
    const robustPeaks = [];
    const softPeaks = [];
    const softCurves = [];

    for (const entry of shown) {
      const colour = sliceColor.get(entry.slice) || THEME.accent;
      const slice = slices.find((s) => s.index === entry.slice);
      const sliceLabel = slice ? slice.label : String(entry.slice);
      const name = `E_${entry.shower.toUpperCase()} · ${sliceLabel}`;
      const dashed = entry.shower === 'b';
      const curveX = axis.curve_x || [];

      if (entry.histogram && entry.histogram.n_in_range > 0) {
        const centres = axis.hist_centres || [];
        const counts2 = entry.histogram.counts;
        series.push({
          type: 'line',
          name,
          step: 'middle',
          symbol: 'none',
          data: centres.map((x, i) => [x, counts2[i]]),
          lineStyle: {
            color: colour, width: THEME.lineAxis, opacity: 0.4,
            type: dashed ? 'dashed' : 'solid',
          },
          areaStyle: { color: colour, opacity: 0.06 },
          z: 2,
          tooltip: {
            formatter: (p) =>
              `${name}<br/>binned density at ${formatNumber(p.value[0], 3)} GeV`
              + ` = ${formatNumber(p.value[1], 3)} GeV⁻¹`
              + `<br/><span style="color:${THEME.muted}">${formatInt(entry.histogram.n_in_range)}`
              + ` of ${formatInt(entry.histogram.n)} events in range</span>`,
          },
        });
        legendNames.push(name);
        if (entry.drives_scale) robustPeaks.push(arrayPeak(counts2));
      }

      if (entry.curve && entry.curve.y && entry.curve.y.length) {
        const peak = entry.curve_peak ?? arrayPeak(entry.curve.y);
        // A curve from a thin slice is de-weighted: it is an assumption
        // imported from the populated slices, not a measurement.
        const thin = !entry.drives_scale;
        const curveName = thin ? `${name} fit (N=${entry.fit.n})` : `${name} fit`;
        series.push({
          type: 'line',
          name: curveName,
          symbol: 'none',
          smooth: true,
          data: curveX.map((x, i) => [x, entry.curve.y[i]]),
          lineStyle: {
            color: colour,
            width: thin ? 1.2 : 2,
            opacity: thin ? 0.6 : 1,
            type: dashed ? 'dashed' : 'solid',
          },
          z: 5,
          tooltip: { formatter: () => this.fitTooltip(entry, curveName, thresholds) },
        });
        legendNames.push(curveName);
        if (entry.drives_scale) {
          robustPeaks.push(peak);
        } else {
          softPeaks.push(peak);
          softCurves.push({ entry, peak, colour, name: curveName });
        }
      }
    }

    /* ---- the scale: robust evidence first, weak evidence only if alone ---- */
    const robustPeak = arrayPeak(robustPeaks);
    const provisional = !(robustPeak > 0);
    const basis = provisional ? arrayPeak(softPeaks) : robustPeak;
    const hasDensity = basis > 0;
    const yMax = hasDensity ? Y_HEADROOM * basis : FALLBACK_Y_MAX;
    const clipped = softCurves.filter((c) => c.peak > yMax);

    /* ---- pass 2: the events, and the two interval marks ------------------- */
    const xLo = axis.lo ?? this.dataFloor(shown);
    const xHi = axis.hi ?? this.dataCeiling(shown);

    // Each low-statistics series gets its own row, tightening as their number
    // grows so the reserved band never eats the plot.
    const stripEntries = shown.filter((e) => e.draw !== 'histogram');
    const plotPx = Math.max(140, (metrics.height || 340)
      - (metrics.reservedBottom || 0) - 100);
    const rowGap = stripEntries.length
      ? Math.max(ROW_GAP_MIN_PX, Math.min(
        ROW_GAP_MAX_PX, (plotPx * STRIP_BAND_SHARE) / stripEntries.length,
      ))
      : ROW_GAP_MAX_PX;

    stripEntries.forEach((entry, row) => {
      const colour = sliceColor.get(entry.slice) || THEME.accent;
      const slice = slices.find((s) => s.index === entry.slice);
      const sliceLabel = slice ? slice.label : String(entry.slice);
      const name = `E_${entry.shower.toUpperCase()} · ${sliceLabel}`;
      const dashed = entry.shower === 'b';
      const rowY = STRIP_BASE_PX + row * rowGap;

      const values = (entry.strip && entry.strip.values) || [];
      if (values.length) {
        // One tick per event along the row. Not a density, and deliberately
        // not drawn as one: its height is a fixed pixel count.
        series.push({
          type: 'scatter',
          name: `${name} (events)`,
          data: values.map((x) => [x, 0]),
          symbol: 'rect',
          symbolSize: [1.5, 8],
          symbolOffset: [0, -rowY],
          itemStyle: { color: colour, opacity: dashed ? 0.65 : 0.95 },
          z: 7,
          tooltip: {
            formatter: (p) =>
              `${name}<br/>event energy = ${formatNumber(p.value[0], 3)} GeV`
              + `<br/><span style="color:${THEME.muted}">one of ${formatInt(entry.fit.n)}`
              + ' individual events</span>',
          },
        });
        legendNames.push(`${name} (events)`);
      }

      const m = entry.markers;
      if (!m) return;
      const markerY = rowY + MARKER_LIFT_PX;
      series.push(this.dispersionSeries(entry, m, colour, name, markerY));
      series.push(this.meanSeries(entry, m, colour, name, xLo, xHi, markerY));
    });
    const stripCount = stripEntries.length;

    /* The strip rows sit on the density axis at heights that are not densities.
     * That is the one place this panel comes close to CLAUDE.md section 2's
     * dual-axis prohibition, so it is disclosed rather than merely styled: the
     * rows occupy a tinted, labelled band with a rule along its top edge, which
     * makes it one axis with a reserved zone rather than two scales. */
    if (stripCount) {
      // Clearance above the topmost row for the band's own caption, which is
      // drawn downward from the rule and would otherwise land on that row.
      const bandTopPx = STRIP_BASE_PX + (stripCount - 1) * rowGap
        + MARKER_LIFT_PX + CAP_PX + 2.4 * THEME.fontSmall;
      // The caption must fit the plot area it labels. A single-column figure is
      // a third the width of the on-screen panel, where the full sentence would
      // run off the grid; the short form states the same thing, and the footnote
      // and every tooltip in the band repeat it in full.
      const bandLabel = fitsWidth(
        STRIP_CAPTION, plotWidthPx - 12, THEME.fontSmall,
      ) ? STRIP_CAPTION : STRIP_CAPTION_SHORT;
      series.push({
        type: 'custom',
        name: 'event strip',
        data: [[xLo, 0]],
        z: 1,
        silent: true,
        clip: true,
        renderItem: (params, api) => {
          const left = api.coord([xLo, 0]);
          const right = api.coord([xHi, 0]);
          const top = left[1] - bandTopPx;
          return {
            type: 'group',
            children: [
              {
                type: 'rect',
                shape: {
                  x: left[0], y: top,
                  width: right[0] - left[0], height: bandTopPx,
                },
                style: { fill: THEME.muted, opacity: THEME.stripAlpha },
              },
              {
                type: 'line',
                shape: { x1: left[0], y1: top, x2: right[0], y2: top },
                style: {
                  stroke: THEME.border,
                  lineWidth: THEME.lineGrid,
                  lineDash: [3, 3],
                },
              },
              {
                type: 'text',
                style: {
                  x: left[0] + 6,
                  y: top + 3,
                  text: bandLabel,
                  fill: THEME.muted,
                  fontSize: THEME.fontSmall,
                  fontFamily: THEME.fontFamily,
                  opacity: 0.85,
                },
              },
            ],
          };
        },
      });
    }

    /* ---- clipped low-N curves are disclosed, not silently cut ------------- */
    for (const c of clipped) {
      series.push({
        type: 'custom',
        name: `${c.name} (clipped)`,
        data: [[c.entry.fit.mu_core, yMax]],
        z: 9,
        clip: false,
        renderItem: (params, api) => {
          const p = api.coord([api.value(0), yMax]);
          return {
            type: 'polygon',
            shape: {
              points: [
                [p[0], p[1] + 1],
                [p[0] - 5, p[1] + 9],
                [p[0] + 5, p[1] + 9],
              ],
            },
            style: { fill: c.colour, opacity: 0.9 },
          };
        },
        tooltip: {
          formatter: () =>
            `${c.name}<br/><span style="color:${THEME.warn || THEME.muted}">clipped:`
            + ` peak ${formatNumber(c.peak, 3)} GeV⁻¹ exceeds the axis</span>`
            + `<br/><span style="color:${THEME.muted}">the axis is set by the`
            + ' N ≥ 15 slices; this curve is too thin to scale it</span>',
        },
      });
    }

    /* The isolated references are drawn as a position and a width, not as a
     * density curve.
     *
     * Their stated resolution is 5%, while the reconstructed distributions run
     * far wider. A unit-area Gaussian that narrow peaks around 3 GeV^-1,
     * roughly an order of magnitude above the data, so plotting it as a curve
     * hands the y axis to the reference and squashes everything the panel is
     * actually about. A dotted rule at mu with a shaded mu +/- sigma band states
     * the same two numbers without competing for the density axis - and still
     * encodes dispersion, as CLAUDE.md section 2 requires. They live in their
     * own legend so a benchmark can never be read as a measured slice. */
    const benchmarkNames = [];
    for (const benchmark of payload.benchmarks || []) {
      if (shower !== 'both' && benchmark.shower !== shower) continue;
      const colour = benchmark.shower === 'a' ? THEME.text : THEME.muted;
      const prefix = benchmark.tooltip_prefix || '[Reference Benchmark]';
      const legendName = `[Ref] ${benchmark.label}`;
      benchmarkNames.push(legendName);
      const tooltipText = () =>
        `<span style="color:${THEME.muted}">${prefix}</span><br/>`
        + `${benchmark.label}<br/>μ = ${formatNumber(benchmark.mu, 2)} GeV`
        + `<br/>σ = ${formatNumber(benchmark.sigma, 2)} GeV`
        + `<br/><span style="color:${THEME.muted}">stated `
        + `${formatPercent(benchmark.resolution, 0)} single-shower width, not a`
        + ' fit; drawn as a position and a width, never as a density</span>';
      series.push({
        type: 'line',
        name: legendName,
        data: [],
        silent: false,
        z: 4,
        lineStyle: {
          color: colour, type: 'dotted', width: 1.5 * THEME.lineAxis,
        },
        itemStyle: { color: colour },
        markArea: {
          silent: true,
          itemStyle: { color: colour, opacity: THEME.envelopeAlpha },
          data: [[
            { xAxis: benchmark.mu - benchmark.sigma },
            { xAxis: benchmark.mu + benchmark.sigma },
          ]],
        },
        markLine: {
          symbol: 'none',
          silent: false,
          lineStyle: {
            color: colour,
            type: 'dotted',
            width: 1.5 * THEME.lineAxis,
            opacity: 0.9,
          },
          label: {
            show: true,
            position: 'insideEndTop',
            distance: 4,
            color: colour,
            fontSize: THEME.fontSmall,
            fontFamily: THEME.fontFamily,
            formatter: benchmark.shower === 'a' ? 'E₁ ref' : 'E₂ ref',
          },
          data: [{ xAxis: benchmark.mu, tooltip: { formatter: tooltipText } }],
        },
      });
    }

    /* Legend rows, and the inset they force on the grid.
     *
     * On screen the legend scrolls: the panel is wide, and a scroll arrow
     * costs less room than wrapping. A printed figure has no scroll arrow to
     * click, so entries the reader cannot reach are entries that are not there
     * - the legend must wrap and the grid must make room for it. */
    const wraps = THEME.legendWrap;
    const mainRows = wraps
      ? legendRows(legendNames, plotWidthPx, THEME.fontLabel,
        { fontFamily: THEME.fontFamily })
      : 1;
    const benchRows = wraps && benchmarkNames.length
      ? legendRows(benchmarkNames, plotWidthPx, THEME.fontSmall,
        { fontFamily: THEME.fontFamily })
      : (benchmarkNames.length ? 1 : 0);
    this.lastLegendRows = mainRows + benchRows;

    const rowPx = 1.6 * THEME.fontLabel;
    const benchTop = mainRows * rowPx;
    const legendPx = (mainRows + benchRows) * rowPx;

    const gridTop = pad.top + legendPx;
    const gridBottom = pad.bottom + (metrics.reservedBottom || 0);
    const plotHeightPx = Math.max(
      60, (metrics.height || 340) - gridTop - gridBottom,
    );

    /* The y-axis name is rotated, so the plot *height* is what it has to fit.
     *
     * The long forms were written for a 380 px panel. In an 85 mm figure the
     * plot is barely 200 px tall, and the full sentence overruns the axis at
     * both ends - over the legend above and into the caption below. Each has a
     * shorter form; the qualification the short form drops is stated in full by
     * the caption, which is drawn from the same footnote either way. */
    const yNames = hasDensity
      ? (provisional
        ? ['Probability Density [GeV⁻¹] — provisional scale, no slice above N = 15',
          'Probability Density [GeV⁻¹] — provisional']
        : ['Probability Density [GeV⁻¹]'])
      : ['Probability density — not estimable at this sample size',
        'Probability density — not estimable'];
    const yName = yNames.find(
      (candidate) => fitsWidth(candidate, plotHeightPx, THEME.fontName,
        THEME.fontFamily),
    ) || yNames[yNames.length - 1];

    const option = {
      backgroundColor: THEME.chartBackground,
      animation: false,
      textStyle: { fontFamily: THEME.fontFamily },
      // The references keep a second legend row of their own, above the plot
      // rather than below it: at the bottom it overlapped the x-axis title.
      grid: {
        left: pad.left, right: pad.right, top: gridTop, bottom: gridBottom,
      },
      legend: [
        {
          show: true,
          type: wraps ? 'plain' : 'scroll',
          top: 0,
          data: legendNames,
          textStyle: {
            color: THEME.muted,
            fontSize: THEME.fontLabel,
            fontFamily: THEME.fontFamily,
          },
          inactiveColor: THEME.border,
          itemWidth: 16,
          itemHeight: 8,
        },
        {
          show: benchmarkNames.length > 0,
          type: wraps ? 'plain' : 'scroll',
          top: wraps ? benchTop : 20,
          data: benchmarkNames,
          textStyle: {
            color: THEME.muted,
            fontSize: THEME.fontSmall,
            fontFamily: THEME.fontFamily,
            fontStyle: 'italic',
          },
          inactiveColor: THEME.border,
          itemWidth: 16,
          itemHeight: 8,
        },
      ],
      tooltip: tooltipOption(this.tooltipPosition),
      xAxis: {
        type: 'value',
        name: `Reconstructed energy [${axis.unit || 'GeV'}]`,
        nameLocation: 'middle',
        nameGap: pad.nameGap,
        nameTextStyle: {
          color: THEME.muted,
          fontSize: THEME.fontName,
          fontFamily: THEME.fontFamily,
        },
        min: xLo,
        max: xHi,
        // The range was rounded to clean boundaries server-side, so a fixed
        // interval lands on whole numbers and a raw percentile bound such as
        // 9.197060758 can never reach a tick label.
        interval: axis.interval,
        axisLine: {
          onZero: THEME.axisOnZero,
          lineStyle: { color: THEME.border, width: THEME.lineAxis },
        },
        axisTick: {
          show: true,
          inside: false,
          lineStyle: { color: THEME.border, width: THEME.lineAxis },
        },
        axisLabel: {
          color: THEME.muted,
          fontSize: THEME.fontLabel,
          fontFamily: THEME.fontFamily,
          formatter: (v) => trimFloat(v),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: yName,
        nameLocation: 'middle',
        nameGap: 4.2 * THEME.fontLabel,
        nameTextStyle: {
          color: THEME.muted,
          fontSize: THEME.fontName,
          fontFamily: THEME.fontFamily,
        },
        // Strictly zero-based: this is a density, and a truncated baseline
        // would exaggerate differences between slices.
        min: 0,
        max: yMax,
        splitNumber: 4,
        axisLine: {
          onZero: THEME.axisOnZero,
          lineStyle: { color: THEME.border, width: THEME.lineAxis },
        },
        axisTick: {
          show: true,
          inside: false,
          lineStyle: { color: THEME.border, width: THEME.lineAxis },
        },
        // With no estimable density the grid is left unlabelled rather than
        // showing a 0-1 scale nothing on the canvas is measured against.
        axisLabel: {
          show: hasDensity,
          color: THEME.muted,
          fontSize: THEME.fontLabel,
          fontFamily: THEME.fontFamily,
          formatter: (v) => trimFloat(v),
        },
        splitLine: {
          show: hasDensity,
          lineStyle: {
            color: THEME.grid,
            width: THEME.lineGrid,
            opacity: THEME.gridOpacity,
          },
        },
      },
      graphic: [
        /* Centred on the *plot area*, not on the chart.
         *
         * `top: 'middle'` centres against the whole canvas, which once the
         * exporter began reserving room below the plot for a caption put this
         * notice across the caption's first lines. The grid rectangle is known
         * here, so the position is computed from it. */
        ...(hasDensity ? [] : [{
          type: 'text',
          silent: true,
          style: {
            // Anchored through style.x/y with a centre alignment, not through
            // `left`/`top`, which place the box's corner and so pushed a
            // centred label off the right edge of a single-column figure.
            x: pad.left + plotWidthPx / 2,
            y: gridTop + plotHeightPx / 2,
            // Wrapped to the plot width rather than carrying fixed line breaks:
            // the breaks that suit a 600 px panel overrun an 85 mm figure.
            text: wrapText(
              'No density estimate at this sample size — individual events and'
              + ' summary markers only',
              plotWidthPx - 8, THEME.fontTip, THEME.fontFamily,
            ).join('\n'),
            textAlign: 'center',
            textVerticalAlign: 'middle',
            fill: THEME.muted,
            fontSize: THEME.fontTip,
            fontFamily: THEME.fontFamily,
            lineHeight: 1.45 * THEME.fontTip,
          },
        }]),
        ...graphic,
      ],
      series,
    };

    // The axis window, for the exporter's caption. Kept on the instance because
    // these are locals of one render and the caption is assembled afterwards.
    this.lastAxis = { xLo, xHi, yMax, hasDensity, provisional };

    return {
      option,
      notices: { shown, stripCount, clipped, provisional, hasDensity },
      table: { shown, sliceColor, counts },
    };
  }

  /** mu +/- s: the spread of the events. Uncapped, behind the marker. */
  dispersionSeries(entry, m, colour, name, markerY) {
    return {
      type: 'custom',
      name: `${name} · dispersion`,
      data: [[m.mu, 0]],
      z: 3,
      clip: true,
      renderItem: (params, api) => {
        const lo = api.coord([m.dispersion_lo, 0]);
        const hi = api.coord([m.dispersion_hi, 0]);
        const y = lo[1] - markerY;
        return {
          type: 'rect',
          shape: {
            x: Math.min(lo[0], hi[0]),
            y: y - BAND_HEIGHT_PX / 2,
            width: Math.abs(hi[0] - lo[0]),
            height: BAND_HEIGHT_PX,
          },
          style: { fill: colour, opacity: THEME.bandAlpha },
        };
      },
      tooltip: {
        formatter: () =>
          `${name}<br/><b>sample dispersion</b>: μ ± 1σ = `
          + `${formatNumber(m.dispersion_lo, 3)} … ${formatNumber(m.dispersion_hi, 3)} GeV`
          + `<br/><span style="color:${THEME.muted}">the spread of the ${formatInt(entry.fit.n)}`
          + ' events, <i>not</i> the precision of the mean</span>'
          + `<br/><span style="color:${THEME.muted}">vertical position is a drawing`
          + ' offset, not a density</span>',
      },
    };
  }

  /** mu +/- t(0.975) * SE: the precision of the mean. Capped whisker + dot. */
  meanSeries(entry, m, colour, name, xLo, xHi, markerY) {
    const loClamped = m.ci95_lo < xLo;
    const hiClamped = m.ci95_hi > xHi;
    const lo = Math.max(m.ci95_lo, xLo);
    const hi = Math.min(m.ci95_hi, xHi);
    return {
      type: 'custom',
      name: `${name} · mean ±95% CI`,
      data: [[m.mu, 0]],
      z: 8,
      clip: true,
      renderItem: (params, api) => {
        const base = api.coord([m.mu, 0]);
        const a = api.coord([lo, 0]);
        const b = api.coord([hi, 0]);
        const y = base[1] - markerY;
        const children = [{
          type: 'line',
          shape: { x1: a[0], y1: y, x2: b[0], y2: y },
          style: { stroke: colour, lineWidth: 1.4 * THEME.lineAxis },
        }];
        // A clamped end gets an open arrowhead, not a cap: the interval
        // continues past the axis and must not look as if it stopped there.
        children.push(endMark(a[0], y, colour, loClamped, -1));
        children.push(endMark(b[0], y, colour, hiClamped, 1));
        children.push({
          type: 'circle',
          shape: { cx: base[0], cy: y, r: 3 },
          style: { fill: colour },
        });
        return { type: 'group', children };
      },
      tooltip: {
        formatter: () => {
          const fit = entry.fit;
          const clampNote = (loClamped || hiClamped)
            ? `<br/><span style="color:${THEME.muted}">interval extends past the`
              + ` axis: true range ${formatNumber(m.ci95_lo, 3)} … `
              + `${formatNumber(m.ci95_hi, 3)} GeV</span>`
            : '';
          return `${name}<br/><b>mean with 95% confidence interval</b>`
            + `<br/>μ = ${formatNumber(m.mu, 3)} GeV`
            + `<br/>CI = ${formatNumber(m.ci95_lo, 3)} … ${formatNumber(m.ci95_hi, 3)} GeV`
            + ` <span style="color:${THEME.muted}">(Student-t, ν = ${fit.n - 1})</span>`
            + clampNote
            + `<br/><span style="color:${THEME.muted}">the precision of the mean,`
            + ' <i>not</i> the spread of the events</span>'
            + `<br/><span style="color:${THEME.muted}">vertical position is a drawing`
            + ' offset, not a density</span>';
        },
      },
    };
  }

  fitTooltip(entry, name, thresholds) {
    const fit = entry.fit;
    const lines = [
      name,
      `μ = ${formatNumber(fit.mu_core, 3)} ± ${formatNumber(fit.mu_error, 3)} GeV`,
      `σ = ${formatNumber(fit.sigma_core, 3)} ± ${formatNumber(fit.sigma_error, 3)} GeV`,
    ];
    if (fit.mu_ci95) {
      lines.push(`<span style="color:${THEME.muted}">μ 95% CI `
        + `${formatNumber(fit.mu_ci95[0], 3)} … ${formatNumber(fit.mu_ci95[1], 3)}</span>`);
    }
    if (fit.sigma_ci95) {
      lines.push(`<span style="color:${THEME.muted}">σ 95% CI `
        + `${formatNumber(fit.sigma_ci95[0], 3)} … ${formatNumber(fit.sigma_ci95[1], 3)}`
        + ' (asymmetric)</span>');
    }
    lines.push(`<span style="color:${THEME.muted}">N = ${formatInt(fit.n)}, `
      + `${estimatorLabel(fit)}</span>`);
    if (!entry.drives_scale) {
      lines.push(`<span style="color:${THEME.muted}">below N = `
        + `${thresholds.histogram ?? 15}: de-weighted, and does not set the axis`
        + ' scale</span>');
    }
    return lines.join('<br/>');
  }

  dataFloor(shown) {
    let lo = Infinity;
    for (const entry of shown) {
      for (const v of (entry.strip && entry.strip.values) || []) {
        if (v < lo) lo = v;
      }
    }
    return Number.isFinite(lo) ? lo : 0;
  }

  dataCeiling(shown) {
    let hi = -Infinity;
    for (const entry of shown) {
      for (const v of (entry.strip && entry.strip.values) || []) {
        if (v > hi) hi = v;
      }
    }
    return Number.isFinite(hi) && hi > 0 ? hi : 1;
  }

  renderNotices(payload, shown, { stripCount, clipped, provisional, hasDensity }) {
    if (!this.noteElement) return;
    const thresholds = payload.thresholds || {};
    const notices = [];

    if (stripCount) {
      const noCurve = shown.filter((s) => s.draw === 'strip').length;
      const withCurve = shown.filter((s) => s.draw === 'curve+strip').length;
      const parts = [];
      if (withCurve) {
        parts.push(`${withCurve} below N = ${thresholds.histogram ?? 15}`
          + ' (histogram suppressed; curve drawn de-weighted)');
      }
      if (noCurve) {
        parts.push(`${noCurve} below N = ${thresholds.curve ?? 8}`
          + ' (no density curve: too few events to constrain a shape)');
      }
      notices.push(`Low-statistics series — ${parts.join('; ')}. `
        + 'Individual events are drawn as ticks, with the sample dispersion as a '
        + 'shaded band and the mean with its 95% confidence interval as a capped '
        + 'whisker. μ and σ are reported in the table for every series.');
    }

    if (provisional && hasDensity) {
      // Only meaningful when low-N curves are what the scale was taken from.
      // With nothing drawn at all the axis is unlabelled instead, and calling
      // that "provisional" would imply a scale the panel is not showing.
      notices.push(`No slice reaches N = ${thresholds.histogram ?? 15}, so the `
        + 'density axis is scaled from low-N estimates and is provisional.');
    } else if (!hasDensity && stripCount) {
      notices.push('No density is estimable from this selection, so the '
        + 'density axis is left unlabelled rather than showing a scale that '
        + 'nothing on the plot is measured against.');
    }

    if (clipped.length) {
      const peaks = clipped
        .map((c) => `${formatNumber(c.peak, 3)} GeV⁻¹ at N = ${c.entry.fit.n}`)
        .join('; ');
      notices.push(`${clipped.length} low-N curve`
        + `${clipped.length === 1 ? '' : 's'} clipped at the axis top (${peaks}). `
        + 'The axis is set by the statistically robust slices; a thin curve '
        + 'adapts to it rather than rescaling the panel.');
    }

    const outside = shown.filter(
      (s) => s.fit.n_in_range != null && s.fit.n_in_range < s.fit.n,
    );
    if (outside.length) {
      notices.push('μ and σ are taken on all events in the slice, while the '
        + 'histogram normalises over the events inside the displayed range; '
        + `${outside.length} series has events outside it.`);
    }

    if (!notices.length) {
      this.noteElement.hidden = true;
      return;
    }
    this.noteElement.hidden = false;
    this.noteElement.innerHTML = notices
      .map((n) => `<p>${escapeHtml(n)}</p>`)
      .join('');
  }

  renderTable(payload, shown, sliceColor, counts) {
    const thresholds = payload.thresholds || {};
    const rows = [];
    for (const slice of payload.slices) {
      const n = counts[String(slice.index)] ?? 0;
      const entries = shown.filter((s) => s.slice === slice.index);
      const swatch = `<span class="swatch" style="background:${sliceColor.get(slice.index) || THEME.border}"></span>`;

      if (!entries.length) {
        rows.push(`
          <tr>
            <td class="name">${swatch}${escapeHtml(slice.label)}</td>
            <td class="na" colspan="6">no events in selection</td>
          </tr>`);
        continue;
      }

      for (const entry of entries) {
        const fit = entry.fit;
        const shape = fit.non_gaussian === null
          ? `<span class="na" title="The interquartile width is estimated by interpolating between individual events at this sample size, so the Gaussian assumption cannot be tested.">not testable (N &lt; ${thresholds.robust ?? 20})</span>`
          : fit.non_gaussian
            ? `<span style="color:var(--warn)" title="${escapeHtml(fit.note)}">non-Gaussian</span>`
            : 'Gaussian';
        rows.push(`
          <tr>
            <td class="name">
              ${swatch}${escapeHtml(slice.label)} · E<sub>${entry.shower.toUpperCase()}</sub>
            </td>
            <td>${formatInt(n)}</td>
            <td title="Standard error of the mean; 95% CI ${ciText(fit.mu_ci95)}">
              ${formatNumber(fit.mu_core, 3)}${uncert(fit.mu_error)}
            </td>
            <td title="Standard error of sigma; 95% CI ${ciText(fit.sigma_ci95)} (asymmetric)">
              ${fit.sigma_core === null ? '—' : formatNumber(fit.sigma_core, 3)}${uncert(fit.sigma_error)}
            </td>
            <td>${fit.resolution_core == null ? '—' : formatPercent(fit.resolution_core, 1)}${
              fit.resolution_error == null ? '' : uncert(fit.resolution_error * 100, '%')}</td>
            <td title="${escapeHtml(fit.estimator_note || '')}">${estimatorLabel(fit)}</td>
            <td>${shape}</td>
          </tr>`);
      }
    }

    const refRows = (payload.benchmarks || []).map((b) => `
      <tr class="ref-row">
        <td class="name">${escapeHtml(b.label)}</td>
        <td class="na">—</td>
        <td>${formatNumber(b.mu, 3)}</td>
        <td>${formatNumber(b.sigma, 3)}</td>
        <td>${formatPercent(b.resolution, 1)}</td>
        <td class="na" title="${escapeHtml(b.note || '')}">stated, not fitted</td>
        <td class="na">—</td>
      </tr>`).join('');

    this.tableElement.innerHTML = `
      <table class="fit-table">
        <thead>
          <tr>
            <th class="name">Separation slice</th>
            <th>Events</th><th>μ ± δμ [GeV]</th><th>σ ± δσ [GeV]</th>
            <th>σ/μ</th><th>Estimator</th><th>Shape</th>
          </tr>
        </thead>
        <tbody>${rows.join('')}</tbody>
        ${refRows ? `<tbody class="ref-group">
          <tr><td class="group" colspan="7">Reference benchmarks (stated, not fitted)</td></tr>
          ${refRows}
        </tbody>` : ''}
      </table>`;
  }

  setBusy(busy) {
    this.element.classList.toggle('is-busy', busy);
  }
}

/** A whisker end: a cap when the interval ends here, an arrow when it does not. */
function endMark(x, y, colour, clamped, direction) {
  if (!clamped) {
    return {
      type: 'line',
      shape: { x1: x, y1: y - CAP_PX, x2: x, y2: y + CAP_PX },
      style: { stroke: colour, lineWidth: 1.4 * THEME.lineAxis },
    };
  }
  return {
    type: 'polygon',
    shape: {
      points: [
        [x, y],
        [x - direction * 6, y - CAP_PX],
        [x - direction * 6, y + CAP_PX],
      ],
    },
    style: { fill: 'transparent', stroke: colour, lineWidth: 1.2 * THEME.lineAxis },
  };
}

/** Largest finite value, by loop: these arrays are 200 long and there are many. */
function arrayPeak(values) {
  let peak = 0;
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (Number.isFinite(v) && v > peak) peak = v;
  }
  return peak;
}

function estimatorLabel(fit) {
  switch (fit.estimator) {
    case 'core_refit': return `core refit (n = ${formatInt(fit.n_core)})`;
    case 'moments': return 'moments (ddof = 1)';
    case 'moments_1dof': return 'moments (1 d.o.f.)';
    case 'mean_only': return 'mean only';
    case 'degenerate': return 'degenerate (σ = 0)';
    default: return '—';
  }
}

function uncert(value, suffix = '') {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  return ` <span class="uncert">± ${formatNumber(value, 3)}${suffix}</span>`;
}

function ciText(interval) {
  if (!interval) return 'not available';
  return `${formatNumber(interval[0], 3)} … ${formatNumber(interval[1], 3)}`;
}

/** Drop trailing zeros so a 0.5 GeV interval does not print "10.00". */
function trimFloat(value) {
  const rounded = Number(Number(value).toPrecision(3));
  return typographic(String(rounded));
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
