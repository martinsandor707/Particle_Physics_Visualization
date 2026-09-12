/* Reconstructed energy distribution against separation distance D.
 *
 * Each distance slice contributes a step histogram of the model's reconstructed
 * energies and the fitted Gaussian describing their core. The dashed benchmark
 * curves mark the isolated, non-overlapping reference at the selection's mean
 * true E1 and E2, so the degradation with decreasing separation can be read
 * directly.
 *
 * The y axis starts strictly at zero, as CLAUDE.md section 2 requires of a
 * probability density. Slices with too few events are listed in the table as
 * "insufficient" rather than being drawn with a fitted width, and a slice whose
 * moment width disagrees with its robust width is flagged as non-Gaussian
 * rather than presented as if the curve described it.
 */

import { THEME, formatNumber, formatInt, formatPercent } from '../scale.js';
import { colorStops } from '../palette.js';

export class EnergyPanel {
  constructor(elementId, tableId) {
    this.element = document.getElementById(elementId);
    this.tableElement = document.getElementById(tableId);
    this.chart = echarts.init(this.element, null, { renderer: 'canvas' });
    window.addEventListener('resize', () => this.chart.resize());
  }

  render(payload, { palette = 'viridis', kind = 'pred' } = {}) {
    const slices = payload.slices || [];
    const counts = payload.slice_counts || {};

    // Slices are ordered by separation, so a sequential ramp encodes them in a
    // way that is both perceptually uniform and ordered - the closer pairs read
    // as darker, the well-separated ones as brighter.
    const stops = colorStops(palette, Math.max(3, slices.length));
    const sliceColor = new Map(slices.map((s, i) => [s.index, stops[i]]));

    const series = [];
    const legend = [];
    const shown = payload.series.filter((s) => s.kind === kind);

    for (const entry of shown) {
      const color = sliceColor.get(entry.slice) || THEME.accent;
      const slice = slices.find((s) => s.index === entry.slice);
      const label = `${slice ? slice.label : entry.slice} · ${entry.shower.toUpperCase()}`;
      const dashed = entry.shower === 'b';

      if (entry.histogram && entry.histogram.n_in_range > 0) {
        series.push({
          type: 'line',
          name: label,
          step: 'middle',
          symbol: 'none',
          data: entry.histogram.centres.map((x, i) => [x, entry.histogram.counts[i]]),
          lineStyle: { color, width: 1, opacity: 0.45, type: dashed ? 'dashed' : 'solid' },
          areaStyle: { color, opacity: 0.07 },
          z: 2,
        });
        legend.push(label);
      }

      if (entry.curve && entry.curve.y.length) {
        series.push({
          type: 'line',
          name: `${label} fit`,
          symbol: 'none',
          smooth: true,
          data: entry.curve.x.map((x, i) => [x, entry.curve.y[i]]),
          lineStyle: { color, width: 2, type: dashed ? 'dashed' : 'solid' },
          z: 5,
          tooltip: {
            formatter: () =>
              `${label}<br/>μ = ${formatNumber(entry.fit.mu_core, 3)} GeV` +
              `<br/>σ = ${formatNumber(entry.fit.sigma_core, 3)} GeV`,
          },
        });
      }
    }

    for (const benchmark of payload.benchmarks || []) {
      series.push({
        type: 'line',
        name: benchmark.label,
        symbol: 'none',
        smooth: true,
        data: benchmark.x.map((x, i) => [x, benchmark.y[i]]),
        lineStyle: {
          color: benchmark.shower === 'a' ? THEME.showerA : THEME.showerB,
          width: 1.6,
          type: [6, 4],
          opacity: 0.9,
        },
        z: 6,
        tooltip: { formatter: () => `${benchmark.label}<br/>μ = ${formatNumber(benchmark.mu, 2)} GeV` },
      });
      legend.push(benchmark.label);
    }

    this.chart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      grid: { left: 56, right: 16, top: 34, bottom: 42 },
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
        trigger: 'axis',
        backgroundColor: 'rgba(22,27,34,0.95)',
        borderColor: THEME.border,
        textStyle: { color: THEME.text, fontSize: 11 },
        axisPointer: { type: 'line', lineStyle: { color: THEME.border } },
      },
      xAxis: {
        type: 'value',
        name: `Reconstructed energy [${payload.axis.unit}]`,
        nameLocation: 'middle',
        nameGap: 26,
        nameTextStyle: { color: THEME.muted, fontSize: 10 },
        min: payload.axis.lo,
        max: payload.axis.hi,
        axisLine: { lineStyle: { color: THEME.border } },
        axisLabel: { color: THEME.muted, fontSize: 10 },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: 'Probability density',
        nameLocation: 'middle',
        nameGap: 40,
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

    this.renderTable(payload, shown, sliceColor, counts);
  }

  renderTable(payload, shown, sliceColor, counts) {
    const rows = [];
    for (const slice of payload.slices) {
      const n = counts[String(slice.index)] ?? 0;
      const entries = shown.filter((s) => s.slice === slice.index);
      if (!entries.length) {
        rows.push(`
          <tr>
            <td class="name">
              <span class="swatch" style="background:${sliceColor.get(slice.index) || THEME.border}"></span>
              ${escapeHtml(slice.label)}
            </td>
            <td class="na" colspan="4">no events in selection</td>
          </tr>`);
        continue;
      }
      for (const entry of entries) {
        const fit = entry.fit;
        const flag = fit.insufficient
          ? `<span class="na" title="${escapeHtml(fit.note)}">insufficient (n=${fit.n})</span>`
          : fit.non_gaussian
            ? `<span style="color:var(--warn)" title="${escapeHtml(fit.note)}">non-Gaussian</span>`
            : 'Gaussian core';
        rows.push(`
          <tr>
            <td class="name">
              <span class="swatch" style="background:${sliceColor.get(slice.index) || THEME.border}"></span>
              ${escapeHtml(slice.label)} · ${entry.shower.toUpperCase()}
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

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
