/* The model-performance cards.
 *
 * Rendered generically from the server's `cards[]`: each card names its
 * label, unit, whether it is a headline figure, and the uncertainty of the
 * statistic - its standard error and a 95% interval named by method - so the
 * nine networks need no client-side table that could drift from the server.
 * CLAUDE.md section 2: an aggregate is never shown as a naked point estimate;
 * a card whose uncertainty cannot be estimated (N < 2) says why instead.
 */

import { formatInt, formatNumber, formatPercent, formatSci, formatSigned } from '../scale.js';

/** A card value in its own unit. */
function formatValue(value, unit, id = '') {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  switch (unit) {
    case 'fraction': return formatPercent(value, 2);
    case 'mrad': return `${formatSigned(value, 2)} mrad`;
    case 'GeV': return `${formatSci(value, 3)} GeV`;
    default:
      // Dimensionless: the voxel MAE and RMSE sit near 1e-1..1e-3, a
      // correlation or F1 near 1.
      return id === 'mae' || id === 'rmse' ? formatSci(value, 3) : formatNumber(value, 4);
  }
}

/** The uncertainty line of a card: the interval below N = 15, else the SE. */
function uncertainty(card) {
  const n = Number.isFinite(card.n) ? `N = ${formatInt(card.n)}` : '';
  if (card.show === 'ci' && card.interval) {
    const { lo, hi } = card.interval;
    return `95% [${formatValue(lo, card.unit, card.id)}, ${formatValue(hi, card.unit, card.id)}] · ${n}`;
  }
  if (Number.isFinite(card.se)) return `± ${formatValue(card.se, card.unit, card.id)} SE · ${n}`;
  return card.note ? `${n} · ${card.note}` : n;
}

export class MetricsPanel {
  constructor(elementId, captionId) {
    this.element = document.getElementById(elementId);
    this.caption = document.getElementById(captionId);
  }

  render(payload, latencyMs) {
    const html = [];
    html.push(row({ label: 'Events in selection', value: formatInt(payload.n_events) }));
    for (const card of payload.cards || []) {
      html.push(row({
        label: card.label,
        sub: card.sub,
        value: formatValue(card.value, card.unit, card.id),
        detail: uncertainty(card),
        title: card.interval?.label
          ? `${card.interval.label}${card.note ? `. ${card.note}` : ''}`
          : card.note,
        primary: card.primary,
      }));
    }
    html.push(row({ label: 'Query latency', value: `${formatNumber(latencyMs, 1)} ms` }));
    this.element.innerHTML = html.join('');

    if (this.caption && payload.model) {
      const warning = payload.meta?.warnings?.length
        ? `<br/><span style="color:var(--warn)">${escapeHtml(payload.meta.warnings[0])}</span>`
        : '';
      this.caption.innerHTML = escapeHtml(payload.model.caption) + warning;
    }
  }

  renderError(message) {
    this.element.innerHTML = row({ label: 'Metrics unavailable', value: '—', sub: message });
  }
}

function row({ label, value, sub = '', detail = '', title = '', primary = false }) {
  const tip = title ? ` title="${escapeHtml(title)}"` : '';
  return `
    <div class="metric${primary ? ' is-primary' : ''}"${tip}>
      <span class="k">${escapeHtml(label)}${sub ? `<small>${escapeHtml(sub)}</small>` : ''}</span>
      <span class="v">${value}${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</span>
    </div>`;
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
