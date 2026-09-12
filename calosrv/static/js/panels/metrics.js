/* The model-performance KPI card.
 *
 * Which metrics lead depends on the selected model, because the three
 * architectures are read from the same stored inference columns and differ in
 * what they are being asked. The energy-weighted voxel error is the headline
 * for segmentation: the unweighted one is dominated by the sea of
 * sub-femto-GeV dust hits and flatters the model.
 */

import { formatInt, formatNumber, formatPercent } from '../scale.js';

function pick(source, path) {
  return path.split('.').reduce((acc, key) => (acc ? acc[key] : undefined), source);
}

const ROWS = {
  segmentation: [
    ['classification.accuracy', 'Voxel accuracy', 'assignment at fA ≥ 0.5', 'percent', true],
    ['regression.mae_energy_weighted', 'Energy-weighted MAE', 'fraction of energy mis-assigned', 'percent', true],
    ['regression.mae', 'Voxel MAE', 'unweighted; dominated by dust hits', 'sci', false],
    ['regression.rmse', 'Voxel RMSE', 'on the fraction itself', 'sci', false],
    ['classification.f1_a', 'F1 (shower A)', '', 'number', false],
    ['classification.shared_voxel_fraction', 'Shared voxels', "particle_origin = 'A+B'", 'percent', false],
  ],
  energy: [
    ['energy_residuals.a.relative_resolution', 'Energy resolution A', 'σ of (pred − true)/true', 'percent', true],
    ['energy_residuals.b.relative_resolution', 'Energy resolution B', 'σ of (pred − true)/true', 'percent', true],
    ['energy_residuals.a.relative_bias', 'Relative bias A', 'mean fractional residual', 'percent', false],
    ['energy_residuals.b.relative_bias', 'Relative bias B', 'mean fractional residual', 'percent', false],
    ['energy_residuals.a.correlation', 'Correlation A', 'pred vs. true', 'number', false],
    ['regression.mae_energy_weighted', 'Energy-weighted MAE', 'voxel assignment error', 'percent', false],
  ],
  angle: [
    ['classification.accuracy', 'Voxel accuracy', 'segmentation baseline', 'percent', true],
    ['regression.mae_energy_weighted', 'Energy-weighted MAE', 'segmentation baseline', 'percent', false],
  ],
};

function formatValue(value, kind) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (kind === 'percent') return formatPercent(value, 2);
  if (kind === 'sci') return value.toExponential(2);
  return formatNumber(value, 4);
}

export class MetricsPanel {
  constructor(elementId, captionId) {
    this.element = document.getElementById(elementId);
    this.caption = document.getElementById(captionId);
  }

  render(payload, model, latencyMs) {
    const rows = ROWS[model] || ROWS.segmentation;
    const html = [];

    html.push(row('Events in selection', formatInt(payload.n_events), '', false));
    html.push(row('Voxels', formatInt(payload.classification.n_voxels), '', false));

    for (const [path, label, sub, kind, primary] of rows) {
      html.push(row(label, formatValue(pick(payload, path), kind), sub, primary));
    }

    html.push(row('Query latency', `${formatNumber(latencyMs, 1)} ms`, '', false));

    this.element.innerHTML = html.join('');

    if (this.caption && payload.model) {
      const unavailable = payload.meta?.warnings?.length
        ? `<br/><span style="color:var(--warn)">${escapeHtml(payload.meta.warnings[0])}</span>`
        : '';
      this.caption.innerHTML = escapeHtml(payload.model.caption) + unavailable;
    }
  }

  renderError(message) {
    this.element.innerHTML = row('Metrics unavailable', '—', message, false);
  }
}

function row(label, value, sub, primary) {
  return `
    <div class="metric${primary ? ' is-primary' : ''}">
      <span class="k">${escapeHtml(label)}${sub ? `<small>${escapeHtml(sub)}</small>` : ''}</span>
      <span class="v">${value}</span>
    </div>`;
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
