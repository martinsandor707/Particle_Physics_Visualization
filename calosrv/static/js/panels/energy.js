/* Reconstructed energy distribution against separation distance D.
 *
 * ## Encoding
 *
 * Separation slice is carried by *colour*, shower identity by *line style*:
 *
 *   D-slice              a distinct stop from a sequential ramp
 *   Shower A             solid
 *   Shower B             dashed
 *   Isolated reference   dotted, in neutral text/muted grey
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
 * ## Low statistics
 *
 * A `density=True` histogram divides by N * bin_width, so at small N a single
 * event produces a spike whose height is set by the binning rather than by
 * physics. Below the server's threshold no histogram or fit is drawn at all;
 * the individual events are plotted as a rug strip instead, and the panel says
 * so. The decision is made server-side so the payload never carries a
 * distribution that should not be drawn.
 *
 * The y axis starts strictly at zero, as CLAUDE.md section 2 requires of a
 * probability density.
 */

import { THEME, formatNumber, formatInt, formatPercent } from '../scale.js';
import { categoricalStops } from '../palette.js';

export class EnergyPanel {
  constructor(elementId, tableId, noteId) {
    this.element = document.getElementById(elementId);
    this.tableElement = document.getElementById(tableId);
    this.noteElement = noteId ? document.getElementById(noteId) : null;
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    window.addEventListener('resize', () => this.chart.resize());
  }

  render(payload, { palette = 'viridis', kind = 'pred', shower = 'both' } = {}) {
    const slices = payload.slices || [];
    const counts = payload.slice_counts || {};

    const stops = categoricalStops(palette, Math.max(3, slices.length));
    const sliceColor = new Map(slices.map((s, i) => [s.index, stops[i]]));

    const shown = (payload.series || []).filter(
      (s) => s.kind === kind && (shower === 'both' || s.shower === shower),
    );

    const series = [];
    let sparseCount = 0;

    for (const entry of shown) {
      const colour = sliceColor.get(entry.slice) || THEME.accent;
      const slice = slices.find((s) => s.index === entry.slice);
      const sliceLabel = slice ? slice.label : String(entry.slice);
      const name = `E_${entry.shower.toUpperCase()} · ${sliceLabel}`;
      const dashed = entry.shower === 'b';

      if (entry.sparse) {
        sparseCount += 1;
        if (entry.rug && entry.rug.length) {
          // A rug strip: one tick per event along the bottom of the axis. Not a
          // density, and deliberately not drawn as one.
          series.push({
            type: 'scatter',
            name: `${name} (events)`,
            data: entry.rug.map((x) => [x, 0]),
            symbol: 'rect',
            symbolSize: [1.5, 11],
            symbolOffset: [0, -6],
            itemStyle: { color: colour, opacity: dashed ? 0.65 : 0.95 },
            z: 7,
            tooltip: {
              formatter: (p) =>
                `${name}<br/>event energy = ${formatNumber(p.value[0], 3)} GeV` +
                `<br/><span style="color:${THEME.muted}">individual event (N=${entry.fit.n})</span>`,
            },
          });
        }
        continue;
      }

      if (entry.histogram && entry.histogram.n_in_range > 0) {
        series.push({
          type: 'line',
          name,
          step: 'middle',
          symbol: 'none',
          data: entry.histogram.centres.map((x, i) => [x, entry.histogram.counts[i]]),
          lineStyle: {
            color: colour, width: 1, opacity: 0.4,
            type: dashed ? 'dashed' : 'solid',
          },
          areaStyle: { color: colour, opacity: 0.06 },
          z: 2,
        });
      }

      if (entry.curve && entry.curve.y.length) {
        series.push({
          type: 'line',
          name: `${name} fit`,
          symbol: 'none',
          smooth: true,
          data: entry.curve.x.map((x, i) => [x, entry.curve.y[i]]),
          lineStyle: {
            color: colour, width: 2, type: dashed ? 'dashed' : 'solid',
          },
          z: 5,
          tooltip: {
            formatter: () =>
              `${name}<br/>μ = ${formatNumber(entry.fit.mu_core, 3)} GeV` +
              `<br/>σ = ${formatNumber(entry.fit.sigma_core, 3)} GeV`,
          },
        });
      }
    }

    /* The isolated references are drawn as a position and a width, not as a
     * density curve.
     *
     * Their stated resolution is 5%, while the reconstructed distributions run
     * 55-104%. A unit-area Gaussian that narrow peaks around 3 GeV^-1, roughly
     * an order of magnitude above the data, so plotting it as a curve hands the
     * y axis to the reference and squashes everything the panel is actually
     * about. A dotted rule at mu with a shaded mu +/- sigma band states the same
     * two numbers without competing for the density axis - and still encodes
     * dispersion, as CLAUDE.md section 2 requires. */
    for (const benchmark of payload.benchmarks || []) {
      if (shower !== 'both' && benchmark.shower !== shower) continue;
      const colour = benchmark.shower === 'a' ? THEME.text : THEME.muted;
      series.push({
        type: 'line',
        name: benchmark.label,
        data: [],
        silent: false,
        z: 4,
        lineStyle: { color: colour, type: 'dotted', width: 1.5 },
        itemStyle: { color: colour },
        markArea: {
          silent: true,
          itemStyle: { color: colour, opacity: 0.07 },
          data: [[
            { xAxis: benchmark.mu - benchmark.sigma },
            { xAxis: benchmark.mu + benchmark.sigma },
          ]],
        },
        markLine: {
          symbol: 'none',
          silent: false,
          lineStyle: { color: colour, type: 'dotted', width: 1.5, opacity: 0.9 },
          label: {
            show: true,
            position: 'insideEndTop',
            distance: 4,
            color: colour,
            fontSize: 9,
            formatter: benchmark.shower === 'a' ? 'E₁ ref' : 'E₂ ref',
          },
          data: [{
            xAxis: benchmark.mu,
            tooltip: {
              formatter: () =>
                `${benchmark.label}<br/>μ = ${formatNumber(benchmark.mu, 2)} GeV` +
                `<br/>σ = ${formatNumber(benchmark.sigma, 2)} GeV` +
                `<br/><span style="color:${THEME.muted}">stated ${formatPercent(benchmark.resolution, 0)} single-shower width, not a fit</span>`,
            },
          }],
        },
      });
    }

    const axis = payload.axis || {};
    this.chart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      grid: { left: 58, right: 16, top: 34, bottom: 44 },
      legend: {
        show: true,
        type: 'scroll',
        top: 0,
        textStyle: { color: THEME.muted, fontSize: 10 },
        inactiveColor: THEME.border,
        itemWidth: 16,
        itemHeight: 8,
      },
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(22,27,34,0.95)',
        borderColor: THEME.border,
        textStyle: { color: THEME.text, fontSize: 11 },
      },
      xAxis: {
        type: 'value',
        name: `Reconstructed energy [${axis.unit || 'GeV'}]`,
        nameLocation: 'middle',
        nameGap: 26,
        nameTextStyle: { color: THEME.muted, fontSize: 10 },
        min: axis.lo ?? 0,
        max: axis.hi ?? 1,
        // The range was rounded to clean boundaries server-side, so a fixed
        // interval lands on whole numbers and a raw percentile bound such as
        // 9.197060758 can never reach a tick label.
        interval: axis.interval,
        axisLine: { lineStyle: { color: THEME.border } },
        axisLabel: {
          color: THEME.muted,
          fontSize: 10,
          formatter: (v) => trimFloat(v),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: 'Probability Density [GeV⁻¹]',
        nameLocation: 'middle',
        nameGap: 42,
        nameTextStyle: { color: THEME.muted, fontSize: 10 },
        // Strictly zero-based: this is a density, and a truncated baseline
        // would exaggerate differences between slices.
        min: 0,
        axisLine: { lineStyle: { color: THEME.border } },
        axisLabel: { color: THEME.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: THEME.border, opacity: 0.35 } },
      },
      series,
    }, { notMerge: true });

    this.renderNote(payload, shown, sparseCount);
    this.renderTable(payload, shown, sliceColor, counts);
  }

  renderNote(payload, shown, sparseCount) {
    if (!this.noteElement) return;
    if (!sparseCount || !shown.length) {
      this.noteElement.hidden = true;
      return;
    }
    const message = shown.find((s) => s.sparse && s.message)?.message
      || `Insufficient sample size (N < ${payload.density_threshold}) for `
         + 'continuous density estimation; plotting individual event points.';
    this.noteElement.hidden = false;
    this.noteElement.textContent = message;
  }

  renderTable(payload, shown, sliceColor, counts) {
    const rows = [];
    for (const slice of payload.slices) {
      const n = counts[String(slice.index)] ?? 0;
      const entries = shown.filter((s) => s.slice === slice.index);
      const swatch = `<span class="swatch" style="background:${sliceColor.get(slice.index) || THEME.border}"></span>`;

      if (!entries.length) {
        rows.push(`
          <tr>
            <td class="name">${swatch}${escapeHtml(slice.label)}</td>
            <td class="na" colspan="5">no events in selection</td>
          </tr>`);
        continue;
      }

      for (const entry of entries) {
        const fit = entry.fit;
        const flag = fit.insufficient
          ? `<span class="na" title="${escapeHtml(fit.note)}">N&nbsp;&lt;&nbsp;${payload.density_threshold} — points only</span>`
          : fit.non_gaussian
            ? `<span style="color:var(--warn)" title="${escapeHtml(fit.note)}">non-Gaussian</span>`
            : 'Gaussian core';
        rows.push(`
          <tr>
            <td class="name">
              ${swatch}${escapeHtml(slice.label)} · E<sub>${entry.shower.toUpperCase()}</sub>
            </td>
            <td>${formatInt(n)}</td>
            <td>${fit.insufficient ? '—' : formatNumber(fit.mu_core, 3)}</td>
            <td>${fit.insufficient ? '—' : formatNumber(fit.sigma_core, 3)}</td>
            <td>${fit.insufficient || !fit.resolution ? '—' : formatPercent(fit.resolution, 1)}</td>
            <td>${flag}</td>
          </tr>`);
      }
    }

    this.tableElement.innerHTML = `
      <table class="fit-table">
        <thead>
          <tr>
            <th class="name">Separation slice</th>
            <th>Events</th><th>μ [GeV]</th><th>σ [GeV]</th><th>σ/μ</th><th>Shape</th>
          </tr>
        </thead>
        <tbody>${rows.join('')}</tbody>
      </table>`;
  }

  setBusy(busy) {
    this.element.classList.toggle('is-busy', busy);
  }
}

/** Drop trailing zeros so a 0.5 GeV interval does not print "10.00". */
function trimFloat(value) {
  const rounded = Math.round(value * 1000) / 1000;
  return String(rounded);
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
