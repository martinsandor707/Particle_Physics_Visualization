/* C1 + C9: the selection's describe() table and its negative-depth block.
 *
 * A table, not a chart: no marks, no export. `statisticsRows(payload)` is the
 * pure part, run under Node against the recorded payloads; the panel builds
 * the DOM from it with `textContent` only, because every label and note comes
 * from a payload.
 *
 * ## What the columns are
 *
 * count, mean, SD, min, the quartiles and max are unweighted: every hit is
 * one observation (the pandas describe() convention, SD with ddof = 1). The
 * energy-weighted mean and quartiles sit under their own header: they say
 * where the energy is, a different weighting rather than a correction. No
 * standard error of a mean is quoted - the hits of one shower are correlated,
 * so a hit count would claim a precision the events do not have; the server
 * says so in `estimator`, which the Details drawer carries. A row computed
 * from few hits carries the server's note (1 d.o.f., quartiles that
 * interpolate between hits) as a flag on its label.
 *
 * The laboratory frame's "z − 3649 mm" row is the reference notebook's display
 * offset, labelled by the server; the client does no z arithmetic.
 *
 * ## C9: hits behind the entry plane
 *
 * The share of energy, of hits and of events (or showers) with any hit at
 * w < −10⁻⁶ mm, each with the interval the server names (a cluster ratio
 * interval for the fractions, Wilson for the shares), by momentum split. A
 * share of showers is given only where each event contributes one shower.
 */

import { formatNumber, formatInt, formatSci, formatPercent, typographic } from '../scale.js';

/** The column groups and their columns, in display order. */
export const STAT_COLUMNS = Object.freeze([
  { key: 'count', label: 'count', group: 'unweighted' },
  { key: 'mean', label: 'mean', group: 'unweighted' },
  { key: 'sd', label: 'SD', group: 'unweighted' },
  { key: 'min', label: 'min', group: 'unweighted' },
  { key: 'q25', label: '25%', group: 'unweighted' },
  { key: 'q50', label: 'median', group: 'unweighted' },
  { key: 'q75', label: '75%', group: 'unweighted' },
  { key: 'max', label: 'max', group: 'unweighted' },
  { key: 'ew_mean', label: 'mean', group: 'energy-weighted' },
  { key: 'ew_q25', label: '25%', group: 'energy-weighted' },
  { key: 'ew_q50', label: 'median', group: 'energy-weighted' },
  { key: 'ew_q75', label: '75%', group: 'energy-weighted' },
]);

/** A value in its row's unit: millimetres to 0.1, GeV in scientific form, radians to 4 places. */
export function formatStat(value, unit, key) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (key === 'count') return formatInt(value);
  if (unit === 'mm') return formatNumber(value, 1);
  if (unit === 'rad') return formatNumber(value, 4);
  return formatSci(value, 3);
}

/** One table row of a describe() row. */
function rowOf(row) {
  return {
    key: row.key,
    label: row.label,
    unit: row.unit ?? '',
    cells: STAT_COLUMNS.map((c) => formatStat(row[c.key], row.unit, c.key)),
    note: row.note || '',
    offset: Number.isFinite(row.display_offset_mm) ? row.display_offset_mm : null,
  };
}

/** A fraction with its interval in brackets, e.g. "7.12% [6.00, 8.23]". */
export function fractionText(value, ci, digits = 2) {
  if (!Number.isFinite(value)) return '—';
  const head = formatPercent(value, digits);
  if (!ci || !Number.isFinite(ci[0]) || !Number.isFinite(ci[1])) return head;
  const fixed = (v) => typographic((v * 100).toFixed(digits));
  return `${head} [${fixed(ci[0])}, ${fixed(ci[1])}]`;
}

/** The C9 block as rows; null when the payload has none. */
export function negativeRows(block) {
  if (!block) return null;
  if (block.available === false) {
    return { available: false, reason: block.reason ?? '', summary: block.summary ?? '', rows: [] };
  }
  const perShower = (block.showers_per_event ?? 2) === 1;
  const rows = (block.splits ?? []).map((s) => ({
    key: s.key,
    label: s.label,
    events: formatInt(s.n_events),
    energy: fractionText(s.energy_fraction, s.energy_fraction_ci95),
    hits: fractionText(s.hits_fraction, s.hits_fraction_ci95),
    eventsWith: s.n_events ? `${formatInt(s.events_with_any)} · ${fractionText(s.events_with_any / s.n_events, s.events_with_any_ci95, 1)}` : '—',
    showersWith: perShower && s.n_showers
      ? `${formatInt(s.showers_with_any)} · ${fractionText(s.showers_with_any / s.n_showers, s.showers_with_any_ci95, 1)}` : '—',
    note: s.note || '',
  }));
  return {
    available: true,
    summary: block.summary ?? '',
    perShower,
    threshold: block.threshold_mm,
    intervals: block.intervals ?? {},
    rows,
  };
}

/**
 * The table, as text. Pure: {columns, groups, rows: [{key, label, unit,
 * cells[], note, offset}], negative: {...} | null, n_hits, n_events}.
 * The shifted laboratory row follows the z row it is derived from.
 */
export function statisticsRows(payload) {
  const describe = payload?.describe ?? {};
  const rows = [];
  for (const row of describe.rows ?? []) {
    rows.push(rowOf(row));
    if (describe.shifted_row && row.key === 'z') rows.push(rowOf(describe.shifted_row));
  }
  if (describe.shifted_row && !rows.some((r) => r.key === describe.shifted_row.key)) rows.push(rowOf(describe.shifted_row));
  return {
    columns: STAT_COLUMNS.map((c) => c.label),
    groups: [
      { label: 'unweighted (every hit one observation)', span: STAT_COLUMNS.filter((c) => c.group === 'unweighted').length },
      { label: 'energy-weighted', span: STAT_COLUMNS.filter((c) => c.group === 'energy-weighted').length },
    ],
    rows,
    negative: negativeRows(payload?.negative_w ?? null),
    n_hits: describe.n_hits ?? null,
    n_events: payload?.n_events ?? null,
    coord_system: describe.coord_system ?? null,
  };
}

/** C9 column headings, by whether a share of showers is defined. */
export function negativeColumns(perShower) {
  return ['Split', 'Events', 'Energy at w < 0', 'Hits at w < 0', 'Events with any',
    ...(perShower ? ['Showers with any'] : [])];
}

export class StatisticsPanel {
  constructor(elementOrId) {
    this.element = typeof elementOrId === 'string' ? document.getElementById(elementOrId) : elementOrId;
    this.kind = 'table';
    this.lastPayload = null;
    this.lastOpts = null;
  }

  /** Text nodes only: every string comes from a payload. */
  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    if (!this.element) return;
    const model = statisticsRows(payload);
    const nodes = [this.table(model)];
    if (model.negative) nodes.push(this.negativeTable(model.negative));
    this.element.replaceChildren(...nodes);
  }

  table(model) {
    const el = (tag, text, cls) => {
      const node = document.createElement(tag);
      if (text !== undefined && text !== null) node.textContent = text;
      if (cls) node.className = cls;
      return node;
    };
    const table = el('table', null, 'fit-table stats-table');
    const head = el('thead');
    const groups = el('tr');
    groups.append(el('th', '', 'name'));
    for (const g of model.groups) {
      const th = el('th', g.label, 'group');
      th.colSpan = g.span;
      groups.append(th);
    }
    const names = el('tr');
    names.append(el('th', 'Quantity', 'name'));
    for (const c of model.columns) names.append(el('th', c));
    head.append(groups, names);
    const body = el('tbody');
    for (const row of model.rows) {
      const tr = el('tr');
      const name = el('td', `${row.label}${row.unit ? ` [${row.unit}]` : ''}`, 'name');
      if (row.note) {
        name.title = row.note;
        name.append(el('span', ' ⚑', 'flag'));
      }
      tr.append(name);
      for (const cell of row.cells) tr.append(el('td', cell));
      body.append(tr);
    }
    table.append(head, body);
    return table;
  }

  negativeTable(block) {
    const wrap = document.createElement('div');
    wrap.className = 'stats-c9';
    const title = document.createElement('p');
    title.className = 'stats-c9-summary';
    title.textContent = block.available ? block.summary : (block.reason || block.summary);
    wrap.append(title);
    if (!block.available) return wrap;
    const table = document.createElement('table');
    table.className = 'fit-table';
    const head = document.createElement('tr');
    for (const text of negativeColumns(block.perShower)) {
      const th = document.createElement('th');
      th.textContent = text;
      head.append(th);
    }
    const thead = document.createElement('thead');
    thead.append(head);
    const body = document.createElement('tbody');
    for (const row of block.rows) {
      const tr = document.createElement('tr');
      const cells = [row.label, row.events, row.energy, row.hits, row.eventsWith, ...(block.perShower ? [row.showersWith] : [])];
      cells.forEach((text, i) => {
        const td = document.createElement('td');
        td.textContent = text;
        if (i === 0) {
          td.className = 'name';
          if (row.note) td.title = row.note;
        }
        tr.append(td);
      });
      body.append(tr);
    }
    table.append(thead, body);
    wrap.append(table);
    return wrap;
  }

  relayout() {}

  clear() {
    this.lastPayload = null;
    this.lastOpts = null;
    this.element?.replaceChildren();
  }

  setBusy(busy) {
    this.element?.classList.toggle('is-busy', Boolean(busy));
  }
}
