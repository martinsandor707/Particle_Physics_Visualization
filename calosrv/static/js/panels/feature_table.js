/* D2: the shower features described per momentum class, as a table.
 *
 * `/api/features?view=describe` ships one column block per feature
 * (`table[feature]`), each statistic an array over the classes: count, mean
 * with its Student-t 95% interval, SD with its χ² interval, its own standard
 * error `sd_se` and the bias factor `c4`, the ddof = 0 SD for the notebook,
 * the quartiles, min and max, and `robust` (N ≥ 20). An azimuth has no linear
 * mean, SD or quartile: its block carries `circular` instead (mean direction,
 * mean resultant length R̄, circular SD, Rayleigh p and a note when the
 * direction carries no information).
 *
 * A table, not a chart: no marks, no export. `featureRows(payload, stat)` is
 * the pure part, run under Node; the panel builds the DOM from it with
 * `textContent` only, because every label and note comes from a payload.
 *
 * ## One statistic per cell, its uncertainty one hover away
 *
 * `stat` picks what each cell prints: 'median' (median [25%, 75%], the
 * notebook's describe()), 'mean' (mean ± SD - the SD is the spread of the
 * showers, so it is written as ± SD, never as an interval) or 'range'
 * (min … max). The cell's title carries what the number needs: the mean's
 * Student-t interval, σ with its SE, χ² interval and c₄(N) below the
 * core-refit floor (CLAUDE.md section 2: at N = 3 a bare σ is the misleading
 * presentation), and the server's low-N note for the cell's own N
 * (`notes_by_n`). A cell from fewer than 20 showers is flagged ⚑; N = 2 says
 * "1 d.o.f." in the cell itself. A circular row prints the circular mean
 * direction and R̄ - never an arithmetic mean of a wrapped angle - and its
 * range in 'range' mode. Values floored at 10⁻⁶ mm by the producer are
 * counted in the row's note.
 */

import { formatNumber, formatInt, formatSci } from '../scale.js';

/** The statistics a cell can print, in the order the card offers them. */
export const FEATURE_STATS = Object.freeze([
  { key: 'median', label: 'median [IQR]' },
  { key: 'mean', label: 'mean ± SD' },
  { key: 'range', label: 'min … max' },
]);

/** Below this many showers a cell is flagged (the payload's robust floor). */
export const ROBUST_N = 20;
/** Below this many σ is quoted with its χ² interval and c₄ (the core-refit floor). */
export const CORE_N = 15;

/** A value in its feature's unit: radians to three places, everything else to three significant figures. */
export function featureValue(value, unit) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (unit === 'rad') return formatNumber(value, 3);
  return formatSci(value, 3);
}

/** The class columns: {label, n}. */
function columnsOf(payload) {
  return (payload?.classes ?? []).map((c) => ({ index: c.index, label: c.label, n: c.n ?? 0 }));
}

/** The server's low-N note for a cell of N = n, or ''. */
function nNote(payload, n) {
  return payload?.notes_by_n?.[String(n)] ?? '';
}

/** One linear cell. */
function linearCell(payload, t, i, stat, unit) {
  const n = t.n?.[i] ?? 0;
  const v = (key) => t[key]?.[i] ?? null;
  const f = (x) => featureValue(x, unit);
  const note = nNote(payload, n);
  const title = [`N = ${formatInt(n)}`];
  if (!n) return { text: '—', title: [note || 'No values in this class.'].join(' '), flag: false, n };
  let text;
  if (stat === 'mean') {
    const sd = v('sd');
    text = Number.isFinite(sd) ? `${f(v('mean'))} ± ${f(sd)}` : f(v('mean'));
    if (n === 2) text += ' (1 d.o.f.)';
    if (Number.isFinite(v('mean_lo')) && Number.isFinite(v('mean_hi'))) {
      title.push(`mean ${f(v('mean'))}, 95% Student-t interval [${f(v('mean_lo'))}, ${f(v('mean_hi'))}] (the precision of the mean)`);
    }
    if (Number.isFinite(sd)) {
      let s = `SD ${f(sd)} (ddof = 1, the spread of the showers)`;
      if (Number.isFinite(v('sd_se'))) s += ` ± ${f(v('sd_se'))} (SE)`;
      if (n < CORE_N) {
        if (Number.isFinite(v('sd_lo')) && Number.isFinite(v('sd_hi'))) s += `, χ² 95% interval [${f(v('sd_lo'))}, ${f(v('sd_hi'))}]`;
        if (Number.isFinite(v('c4'))) s += `, bias factor c₄(N) = ${formatNumber(v('c4'), 4)}`;
      }
      title.push(s);
      if (Number.isFinite(v('sd_population'))) title.push(`ddof = 0 SD ${f(v('sd_population'))} (the notebook's form)`);
    }
  } else if (stat === 'range') {
    text = `${f(v('min'))} … ${f(v('max'))}`;
  } else {
    const q = [v('q25'), v('q50'), v('q75')];
    text = Number.isFinite(q[0]) && Number.isFinite(q[2]) ? `${f(q[1])} [${f(q[0])}, ${f(q[2])}]` : f(q[1]);
    title.push('median [25%, 75%]: np.percentile, linear interpolation');
  }
  if (note) title.push(note);
  const eps = t.n_eps?.[i] ?? 0;
  if (eps) title.push(`${formatInt(eps)} value${eps === 1 ? '' : 's'} floored at 10⁻⁶ mm by the producer`);
  return { text, title: title.join('. '), flag: n < ROBUST_N || t.robust?.[i] === false, n };
}

/** One circular cell: the mean direction and R̄, never a linear mean. */
function circularCell(payload, t, i, stat) {
  const n = t.n?.[i] ?? 0;
  const c = t.circular ?? {};
  const note = nNote(payload, n);
  if (!n) return { text: '—', title: note || 'No values in this class.', flag: false, n };
  if (stat === 'range') {
    return {
      text: `${featureValue(t.min?.[i], 'rad')} … ${featureValue(t.max?.[i], 'rad')}`,
      title: `N = ${formatInt(n)}. min and max on (−π, π]; an azimuth has no linear spread.${note ? ` ${note}` : ''}`,
      flag: n < ROBUST_N,
      n,
    };
  }
  const dir = c.mean_direction?.[i];
  const R = c.resultant?.[i];
  const text = Number.isFinite(dir) ? `${featureValue(dir, 'rad')} · R̄ ${formatNumber(R, 3)}` : '—';
  const title = [`N = ${formatInt(n)}`, 'circular mean direction atan2(Σ sin φ, Σ cos φ) and mean resultant length R̄; an arithmetic mean of a wrapped angle is never printed'];
  if (Number.isFinite(c.circular_sd?.[i])) title.push(`circular SD ${formatNumber(c.circular_sd[i], 3)} rad`);
  if (Number.isFinite(c.rayleigh_p?.[i])) title.push(`Rayleigh p = ${formatSci(c.rayleigh_p[i], 2)}`);
  if (c.note?.[i]) title.push(c.note[i]);
  if (note) title.push(note);
  return { text, title: title.join('. '), flag: n < ROBUST_N || Boolean(c.note?.[i]), n };
}

/**
 * The table, as text. Pure: {stat, columns: [{label, n}], rows: [{key, label,
 * unit, circular, cells: [{text, title, flag, n}], note}]}. `stat` is one of
 * FEATURE_STATS (default 'median').
 */
export function featureRows(payload, stat = 'median') {
  const chosen = FEATURE_STATS.some((s) => s.key === stat) ? stat : 'median';
  const columns = columnsOf(payload);
  const rows = (payload?.features ?? []).map((feat) => {
    const t = payload.table?.[feat.id] ?? {};
    const circular = Boolean(feat.circular) || Boolean(t.circular);
    const cells = columns.map((_, i) => (circular ? circularCell(payload, t, i, chosen) : linearCell(payload, t, i, chosen, feat.unit)));
    const eps = (t.n_eps ?? []).reduce((sum, v) => sum + (Number.isFinite(v) ? v : 0), 0);
    const notes = [];
    if (eps) notes.push(`${formatInt(eps)} value${eps === 1 ? '' : 's'} floored at 10⁻⁶ mm (counted, not removed)`);
    if (feat.hatched) notes.push(feat.hatched);
    return {
      key: feat.id, label: feat.label ?? feat.id, unit: feat.unit ?? '', circular, cells,
      note: notes.join(' '), flags: feat.flags ?? [],
    };
  });
  return { stat: chosen, columns, rows, n_events: payload?.n_events ?? null, class_basis: payload?.class_basis ?? '' };
}

export class FeatureTablePanel {
  constructor(elementOrId) {
    this.element = typeof elementOrId === 'string' ? document.getElementById(elementOrId) : elementOrId;
    this.kind = 'table';
    this.lastPayload = null;
    this.lastOpts = null;
  }

  /** Text nodes only: every string comes from a payload. `opts.stat` picks the cell statistic. */
  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    if (!this.element) return;
    const doc = this.element.ownerDocument ?? globalThis.document;
    this.element.replaceChildren(this.table(featureRows(payload, opts.stat), doc));
  }

  table(model, doc) {
    const el = (tag, text, cls) => {
      const node = doc.createElement(tag);
      if (text !== undefined && text !== null) node.textContent = text;
      if (cls) node.className = cls;
      return node;
    };
    const table = el('table', null, 'fit-table stats-table feature-table');
    const head = el('thead');
    const names = el('tr');
    names.append(el('th', `Feature · ${FEATURE_STATS.find((s) => s.key === model.stat)?.label ?? model.stat}`, 'name'));
    for (const c of model.columns) {
      const th = el('th', c.label);
      const count = el('span', `N = ${formatInt(c.n)}`, 'uncert');
      count.style.display = 'block';
      th.append(count);
      names.append(th);
    }
    head.append(names);
    const body = el('tbody');
    for (const row of model.rows) {
      const tr = el('tr');
      const name = el('td', `${row.label}${row.unit ? ` [${row.unit}]` : ''}`, 'name');
      if (row.circular) name.append(el('span', ' ↻', 'flag'));
      if (row.note) {
        name.title = row.note;
        name.append(el('span', ' ⚑', 'flag'));
      }
      tr.append(name);
      for (const cell of row.cells) {
        const td = el('td', cell.text);
        if (cell.title) td.title = cell.title;
        if (cell.flag) td.append(el('span', ' ⚑', 'flag'));
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(head, body);
    return table;
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
