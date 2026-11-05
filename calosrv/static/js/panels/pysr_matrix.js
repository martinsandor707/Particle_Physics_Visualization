/* The PySR formulas of the training report as a 3 × 3 matrix: tasks are rows, frames are columns
 * (`distill-pysr`, a DOM card: `table: true`, never exported).
 *
 * The payload is `catalog/select.js` `catalogPayload('distill-pysr', { species })`: nine cells, task-major,
 * each with one entry per species shown (all four under Compare all, stacked in the cell). An entry
 * carries the formula (`source` as printed, `ascii` explicit, `tex` for math.js), its R²_PySR (the
 * formula's fidelity to the network's own validation predictions, not to the truth), the network's R² to
 * the truth where the report prints one, the tier `catalog/gating.js` `tier()` gives it, the tree's top
 * features (the chips) and the formula's own variables, the leak flags of its frame and whether its
 * variable names were mapped from the report's Hungarian by inference.
 *
 * ## What each entry shows
 *
 *  - the species, and the tier as a text chip AND a border style (solid for a physical law and for a
 *    high-fidelity formula whose truth R² is not reported, dashed for a partial surrogate, dotted and in
 *    muted ink for "not a law"): never colour alone;
 *  - the formula as native MathML (`math.js` `texToTree` → `mountMath`, `createElementNS` only), falling
 *    back to its explicit text when the compiler refuses it; where PySR gave no meaningful formula the
 *    entry says so in place, with the R² the report still prints;
 *  - its LaTeX source in a `<code>` with a Copy button (`navigator.clipboard.writeText`; a refusal is said
 *    in the button's title), as the article's display equations carry theirs;
 *  - R²_PySR and the network's R² to truth with their qualifiers (F9), "N not reported" and "point
 *    estimate as reported; no interval" in the title;
 *  - badges: standardised voxel features, label leakage (F8), R² < 0, names mapped by inference;
 *  - the reason for any tier below "Physical law", printed;
 *  - the tree's top features as chips, and the formula's variables that are not among them.
 *
 * ## Cross-highlighting
 *
 * A click on a feature chip highlights every chip of that feature and every entry whose tree features or
 * formula variables use it, across the whole matrix; a second click clears it. The state lives on the
 * instance (`highlight`, `notesState()`), survives a repaint while the feature is still drawn, and each
 * change dispatches `models:panelstate` so the drawer can say what is highlighted. Nothing is requested.
 *
 * ## Long formulas
 *
 * A formula is set at the math size its length allows (`formulaFit`): 14 px up to 40 characters of its
 * explicit form, 12 px up to 70, and 11 px beyond, the stated floor (FORMULA_FIT). A formula still wider
 * than its cell at the floor scrolls sideways inside its own box, never the page: the box keeps a visible
 * scrollbar (css/catalog.css), is marked `data-scrolls`, and a muted line under it says so. The overflow is
 * measured on render and on every relayout (a hidden subpage measures nothing), and the ids of the
 * formulas that scroll travel in `notesState().scrolling`, so the drawer names them.
 *
 * ## Printed decimals
 *
 * R² values are printed with the report's own decimals (select.js `printedQualified`): 1.000 stays 1.000.
 *
 * Every label comes from the payload, so the DOM is built with `createElement`, `createElementNS` and
 * `textContent` only, never `innerHTML`; every colour comes from css/catalog.css tokens.
 */

import { formatInt, typographic } from '../scale.js';
import { mountMath, texToTree } from '../math.js';
import { printed, printedQualified } from '../catalog/select.js';
import { N_NOT_REPORTED, POINT_ESTIMATE, frameColours } from './distill_triangle.js';

/** The tier marks, in the payload's order: the border style each takes (css/catalog.css). */
export const TIER_BORDERS = Object.freeze({ law: 'solid', unverified: 'solid', partial: 'dashed', 'not-law': 'dotted' });

/** The badges an entry can carry: kind → text. */
export const PYSR_BADGES = Object.freeze({
  standardised: 'standardised voxel features',
  leak: 'label leakage',
  negative: 'R² < 0',
  inferred: 'names mapped by inference',
});

/** What a chip says of a feature the report does not define. */
export const UNDEFINED_FEATURE = 'The report gives no definition; it lives in the report\'s distill/surrogate.json, which is not shipped.';

/**
 * The math size of a formula by the length of its explicit form: the first step whose `maxChars` holds
 * it, else the floor. 11 px is the floor: below it a subscripted feature name stops being legible.
 */
export const FORMULA_FIT = Object.freeze({
  normal: Object.freeze({ maxChars: 40, px: 14 }),
  compact: Object.freeze({ maxChars: 70, px: 12 }),
  floor: Object.freeze({ maxChars: Infinity, px: 11 }),
});

/** What the muted line under a formula that scrolls says. */
export const SCROLL_HINT = 'Wider than its cell at the smallest math size: scroll sideways inside the box to read it all.';

/** The printed length of a formula: its explicit form without the product stars and spaces. */
export function formulaLength(ascii) {
  return String(ascii ?? '').replace(/[*\s]/g, '').replace(/\bsqrt\b/g, '√').length;
}

/** The size step of a formula: 'normal' | 'compact' | 'floor' (FORMULA_FIT). */
export function formulaFit(ascii) {
  const n = formulaLength(ascii);
  if (n <= FORMULA_FIT.normal.maxChars) return 'normal';
  if (n <= FORMULA_FIT.compact.maxChars) return 'compact';
  return 'floor';
}

/** The sentence every R² line carries in its title. */
export const R2_TITLE = `${N_NOT_REPORTED}; ${POINT_ESTIMATE}.`;

const text = (v) => typographic(String(v ?? ''));

/** The chip title of one feature: its definition where the report gives one, its mapping where inferred. */
export function featureTitle(key, feature, { entryInferred = false } = {}) {
  const parts = [`${feature?.label ?? key}.`];
  parts.push(feature?.definition ? `${feature.definition[0].toUpperCase()}${feature.definition.slice(1)} (the report's definition).` : UNDEFINED_FEATURE);
  if (feature?.inferred) {
    parts.push('The English name is mapped from the report\'s Hungarian name by inference: the report does not state the mapping.');
  }
  if (entryInferred) {
    parts.push('In this entry the formula\'s variable names were mapped from the report\'s Hungarian names by inference (featureMapInferred).');
  }
  parts.push('Click to highlight every model that uses it; click again to clear.');
  return parts.join(' ');
}

/**
 * The matrix as plain data, decided once (the notes reuse it). Pure:
 * { species, compare, tasks, frames, cells: [{ task, frame, taskLabel, frameLabel, entries }], features,
 *   usage: { key: [entry id] }, counts: { tier: n }, highlight, entries: [all], thresholds, leakText }.
 */
export function pysrModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.cells)) return null;
  const speciesLabels = payload.speciesLabels ?? {};
  const frameLabels = payload.frameLabels ?? {};
  const taskLabels = payload.taskLabels ?? {};
  const tierLabels = payload.tierLabels ?? {};
  const features = payload.features ?? {};
  const usage = {};
  const counts = Object.fromEntries((payload.tiers ?? Object.keys(TIER_BORDERS)).map((t) => [t, 0]));
  const all = [];
  const cells = payload.cells.map((cell) => {
    const entries = (cell.entries ?? []).map((e) => {
      const id = `${e.species}:${cell.task}:${cell.frame}`;
      const r2 = e.r2 ?? null;
      const negative = Boolean(r2 && (r2.qualifier === 'lt' || (Number.isFinite(r2.value) && r2.value < 0)));
      const badges = [];
      if (e.formula?.units === 'standardised') badges.push({ kind: 'standardised', text: PYSR_BADGES.standardised, title: 'The report: the segmentation formulas use standardised voxel features, so their coefficients have no physical unit.' });
      for (const flag of e.leaks ?? []) badges.push({ kind: 'leak', text: PYSR_BADGES.leak, title: payload.leakText?.[flag] ?? flag, flag });
      if (negative) badges.push({ kind: 'negative', text: PYSR_BADGES.negative, title: `R²_PySR ${r2.qualifier === 'lt' ? 'is reported only as < 0, with no number' : `is ${printed(r2.value, r2.dp)}`}: worse than predicting the mean.` });
      if (e.featureMapInferred) badges.push({ kind: 'inferred', text: PYSR_BADGES.inferred, title: 'The proton\'s formula variables are written in Hungarian in the report; their English keys are mapped by inference (the report does not state the mapping).' });
      const featureKeys = [...(e.features ?? [])];
      const extraVariables = (e.variables ?? []).filter((k) => !featureKeys.includes(k));
      for (const k of new Set([...featureKeys, ...(e.variables ?? [])])) (usage[k] ??= []).push(id);
      const tierKey = e.tier?.tier ?? 'not-law';
      counts[tierKey] = (counts[tierKey] ?? 0) + 1;
      const entry = {
        id,
        species: e.species,
        speciesLabel: speciesLabels[e.species] ?? e.species,
        task: cell.task,
        frame: cell.frame,
        tier: tierKey,
        tierLabel: e.tier?.label ?? tierLabels[tierKey] ?? tierKey,
        reasons: [...(e.tier?.reasons ?? [])],
        absent: Boolean(e.formula?.absent),
        tex: e.formula?.tex ?? null,
        ascii: e.formula?.ascii ?? null,
        units: e.formula?.units ?? 'physical',
        fallbackText: text(e.formula?.ascii ?? ''),
        fit: formulaFit(e.formula?.ascii ?? e.formula?.source ?? ''),
        r2Text: printedQualified(r2),
        netR2Text: e.netR2 ? printedQualified(e.netR2) : 'not reported',
        netR2Reported: Boolean(e.netR2),
        negative,
        badges,
        features: featureKeys,
        extraVariables,
        variables: [...(e.variables ?? [])],
        featureMapInferred: Boolean(e.featureMapInferred),
        leaks: [...(e.leaks ?? [])],
        caveats: [...(e.caveats ?? [])],
      };
      all.push(entry);
      return entry;
    });
    return {
      task: cell.task,
      frame: cell.frame,
      taskLabel: taskLabels[cell.task] ?? cell.task,
      frameLabel: frameLabels[cell.frame] ?? cell.frame,
      entries,
    };
  });
  const tasks = [...new Set(cells.map((c) => c.task))];
  const frames = [...new Set(cells.map((c) => c.frame))];
  const wanted = opts.highlight ?? null;
  const highlight = wanted && usage[wanted] ? wanted : null;
  return {
    species: [...(payload.species ?? [])],
    compare: (payload.species ?? []).length > 1,
    speciesLabels,
    tasks,
    frames,
    taskLabels,
    frameLabels,
    tierLabels,
    cells,
    entries: all,
    features,
    usage,
    counts,
    highlight,
    matches: highlight ? [...usage[highlight]] : [],
    thresholds: payload.thresholds ?? {},
    leakText: payload.leakText ?? {},
    provenance: payload.provenance ?? '',
  };
}

/** The status line under the legend: what is highlighted, or how to highlight. */
export function highlightStatus(model) {
  if (!model?.highlight) return 'Click a feature chip to highlight every model whose tree or formula uses it.';
  const n = model.matches.length;
  const label = model.features[model.highlight]?.label ?? model.highlight;
  return `Highlighted: ${label}, used by ${formatInt(n)} of the ${formatInt(model.entries.length)} models shown (tree features or formula variables). Click it again to clear.`;
}

/* ------------------------------------------------------------------ DOM -- */

export class PysrMatrixPanel {
  constructor(elementOrId, { card = null } = {}) {
    this.element = typeof elementOrId === 'string' ? document.getElementById(elementOrId) : elementOrId;
    this.card = card;
    this.kind = 'table';
    this.lastPayload = null;
    this.lastOpts = null;
    this.highlight = null;
    this.chips = [];
    this.entryNodes = new Map();
    this.statusNode = null;
    this.model = null;
    this.formulaBoxes = new Map();
    this.scrolling = [];
  }

  /** The document the card lives in (a test's fake one under Node). */
  doc() {
    return this.element?.ownerDocument ?? globalThis.document;
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    if (!this.element) return;
    this.model = pysrModel(payload, { highlight: this.highlight });
    // A highlight whose feature is no longer drawn is dropped silently: nothing shows it.
    this.highlight = this.model?.highlight ?? null;
    this.chips = [];
    this.entryNodes = new Map();
    this.formulaBoxes = new Map();
    if (!this.model) {
      this.element.replaceChildren();
      this.scrolling = [];
      return;
    }
    this.element.replaceChildren(this.build(this.model));
    this.applyHighlight();
    this.measureScroll();
  }

  /**
   * Which formulas are wider than their box at their size: marks each box (`data-scrolls`), shows its
   * hint, and says so to the drawer when the set changes. A hidden card measures zero widths: nothing.
   */
  measureScroll() {
    const next = [];
    for (const [id, { box, hint }] of this.formulaBoxes) {
      const sw = Number(box.scrollWidth);
      const cw = Number(box.clientWidth);
      const scrolls = Number.isFinite(sw) && Number.isFinite(cw) && cw > 0 && sw > cw + 1;
      if (scrolls) next.push(id);
      if (box.dataset) box.dataset.scrolls = scrolls ? 'true' : 'false';
      if (hint) hint.hidden = !scrolls;
    }
    const changed = next.join('|') !== this.scrolling.join('|');
    this.scrolling = next;
    if (changed) this.announce();
    return next;
  }

  /** Tell the page the drawer's view of this card changed (no request). */
  announce() {
    const element = this.element;
    if (element && typeof element.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
      element.dispatchEvent(new CustomEvent('models:panelstate', { bubbles: true, detail: { card: this.card } }));
    }
  }

  el(tag, className = '', content = null) {
    const node = this.doc().createElement(tag);
    if (className) node.className = className;
    if (content !== null && content !== undefined) node.textContent = content;
    return node;
  }

  build(model) {
    const root = this.el('div', 'pysr-matrix');
    root.append(this.el('p', 'pysr-caption',
      `${model.provenance} R²_PySR is the formula's fidelity to the network's own validation predictions, not to the truth; `
      + `${N_NOT_REPORTED} for any distillation number; ${POINT_ESTIMATE}.`));
    root.append(this.legend(model));
    this.statusNode = this.el('p', 'pysr-status', highlightStatus(model));
    this.statusNode.setAttribute('role', 'status');
    this.statusNode.setAttribute('aria-live', 'polite');
    root.append(this.statusNode);

    const grid = this.el('div', 'pysr-grid');
    grid.setAttribute('role', 'table');
    grid.setAttribute('aria-label', 'PySR formulas by task (rows) and frame (columns)');
    const colours = frameColours();
    const head = this.el('div', 'pysr-row');
    head.setAttribute('role', 'row');
    const corner = this.el('div', 'pysr-head pysr-corner', 'Task / frame');
    corner.setAttribute('role', 'columnheader');
    head.append(corner);
    for (const frame of model.frames) {
      const h = this.el('div', 'pysr-head', model.frameLabels[frame] ?? frame);
      h.setAttribute('role', 'columnheader');
      h.dataset.frame = frame;
      if (typeof h.style?.setProperty === 'function') h.style.setProperty('--frame-hue', colours[frame]);
      head.append(h);
    }
    grid.append(head);
    for (const task of model.tasks) {
      const row = this.el('div', 'pysr-row');
      row.setAttribute('role', 'row');
      const h = this.el('div', 'pysr-head', model.taskLabels[task] ?? task);
      h.setAttribute('role', 'rowheader');
      h.dataset.task = task;
      row.append(h);
      for (const cell of model.cells.filter((c) => c.task === task)) {
        const node = this.el('div', 'pysr-cell');
        node.setAttribute('role', 'cell');
        node.dataset.task = cell.task;
        node.dataset.frame = cell.frame;
        for (const entry of cell.entries) node.append(this.entry(model, entry));
        row.append(node);
      }
      grid.append(row);
    }
    root.append(grid);
    return root;
  }

  /** The tier key: one chip per tier with its rule, so the border styles are named on the card. */
  legend(model) {
    const box = this.el('div', 'pysr-legend');
    box.setAttribute('aria-label', 'Tiers');
    const t = model.thresholds;
    const rules = {
      law: `R²_PySR ≥ ${text(t.lawMinPysrR2 ?? 0.75)} and network R² to truth ≥ ${text(t.lawMinNetR2 ?? 0.7)}, physical units, no leak flag (solid border)`,
      unverified: `R²_PySR ≥ ${text(t.lawMinPysrR2 ?? 0.75)}, but the report gives no network R² to truth (solid border)`,
      partial: `${text(t.partialMinPysrR2 ?? 0.25)} ≤ R²_PySR < ${text(t.lawMinPysrR2 ?? 0.75)}, or capped by a leak flag or standardised features (dashed border)`,
      'not-law': `R²_PySR < ${text(t.partialMinPysrR2 ?? 0.25)}, "< 0", "≈ 0", no formula, or network R² to truth < ${text(t.lawMinNetR2 ?? 0.7)} (dotted border, muted)`,
    };
    for (const tier of Object.keys(TIER_BORDERS)) {
      const chip = this.el('span', 'tier-chip', `${model.tierLabels[tier] ?? tier} (${formatInt(model.counts[tier] ?? 0)})`);
      chip.dataset.tier = tier;
      chip.title = rules[tier];
      box.append(chip);
    }
    return box;
  }

  entry(model, entry) {
    const node = this.el('div', 'pysr-entry');
    node.dataset.tier = entry.tier;
    node.dataset.species = entry.species;
    node.dataset.entry = entry.id;
    this.entryNodes.set(entry.id, node);

    const top = this.el('div', 'pysr-entry-head');
    top.append(this.el('span', 'pysr-species', entry.speciesLabel));
    const chip = this.el('span', 'tier-chip', entry.tierLabel);
    chip.dataset.tier = entry.tier;
    chip.title = entry.reasons.join(' ');
    top.append(chip);
    node.append(top);

    if (entry.absent) {
      node.append(this.el('p', 'pysr-absent',
        `PySR gives no meaningful formula for this model; the report still prints R²_PySR ${entry.r2Text}.`));
    } else {
      const box = this.formula(entry);
      const hint = this.el('p', 'pysr-scroll-hint', SCROLL_HINT);
      hint.hidden = true;
      this.formulaBoxes.set(entry.id, { box, hint });
      node.append(box, hint);
      if (entry.tex) node.append(this.source(entry));
    }

    const r2 = this.el('p', 'pysr-r2', `R²_PySR ${entry.r2Text} · network R² to truth ${entry.netR2Text}`);
    r2.title = R2_TITLE;
    node.append(r2);

    if (entry.badges.length) {
      const badges = this.el('div', 'pysr-badges');
      for (const b of entry.badges) {
        const chipNode = this.el('span', 'badge-chip', b.text);
        chipNode.dataset.kind = b.kind;
        chipNode.title = b.title;
        badges.append(chipNode);
      }
      node.append(badges);
    }

    if (entry.tier !== 'law' && entry.reasons.length) {
      node.append(this.el('p', 'pysr-reason', `${entry.tierLabel}: ${entry.reasons.join(' ')}`));
    }

    if (entry.features.length || entry.extraVariables.length) {
      const feats = this.el('div', 'pysr-features');
      if (entry.features.length) {
        feats.append(this.el('span', 'pysr-features-label', 'Tree\'s top features:'));
        for (const key of entry.features) feats.append(this.chip(model, key, entry));
      }
      if (entry.extraVariables.length) {
        feats.append(this.el('span', 'pysr-features-label', entry.features.length ? 'Also in the formula:' : 'Formula variables:'));
        for (const key of entry.extraVariables) feats.append(this.chip(model, key, entry));
      }
      node.append(feats);
    }
    return node;
  }

  /** The formula: MathML from math.js, its explicit text when the compiler refuses the TeX. */
  formula(entry) {
    const box = this.el('div', 'pysr-formula');
    box.dataset.fit = entry.fit ?? 'normal';
    box.tabIndex = 0;
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', `${entry.speciesLabel} formula`);
    if (entry.tex) {
      try {
        box.append(mountMath(texToTree(entry.tex, { display: true }), this.doc()));
        return box;
      } catch (error) {
        box.dataset.fallback = 'text';
        box.title = `The formula is shown as text: the equation compiler refused its TeX (${error?.message ?? error}).`;
      }
    }
    box.append(this.el('span', 'pysr-fallback', entry.fallbackText));
    return box;
  }

  /** The LaTeX source in a <code>, and a Copy button whose title says what happened. */
  source(entry) {
    const row = this.el('div', 'pysr-tex');
    const code = this.el('code', 'pysr-source', entry.tex);
    code.title = 'LaTeX source of the formula (the equation compiler\'s input)';
    const copy = this.el('button', 'mini pysr-copy', 'Copy');
    copy.type = 'button';
    copy.title = 'Copy the LaTeX source to the clipboard';
    copy.setAttribute('aria-label', `Copy the LaTeX source of the ${entry.speciesLabel} formula`);
    copy.addEventListener('click', () => this.copy(copy, entry.tex));
    row.append(code, copy);
    return row;
  }

  copy(button, tex) {
    const fail = (why) => {
      button.dataset.state = 'failed';
      button.title = `Copy failed: ${why}. Select the source beside the button and copy it by hand.`;
    };
    const clipboard = globalThis.navigator?.clipboard;
    if (!clipboard || typeof clipboard.writeText !== 'function') {
      fail('the clipboard is not available on this page');
      return null;
    }
    let promise;
    try {
      promise = Promise.resolve(clipboard.writeText(tex));
    } catch (error) {
      fail(error?.message ?? String(error));
      return null;
    }
    return promise.then(() => {
      button.dataset.state = 'copied';
      button.textContent = 'Copied';
      button.title = 'The LaTeX source is on the clipboard';
    }, (error) => fail(error?.message ?? String(error)));
  }

  chip(model, key, entry) {
    const feature = model.features[key];
    const chip = this.el('button', 'feature-chip', feature?.label ?? key);
    chip.type = 'button';
    chip.dataset.feature = key;
    chip.setAttribute('aria-pressed', 'false');
    chip.title = featureTitle(key, feature, { entryInferred: entry.featureMapInferred });
    chip.addEventListener('click', () => this.setHighlight(this.highlight === key ? null : key));
    this.chips.push(chip);
    return chip;
  }

  /** Highlight a feature (or clear with null); keeps the state on the instance and says so. */
  setHighlight(key) {
    const next = key && this.model?.usage?.[key] ? key : null;
    if (next === this.highlight) return;
    this.highlight = next;
    if (this.model) this.model = { ...this.model, highlight: next, matches: next ? [...this.model.usage[next]] : [] };
    this.applyHighlight();
    this.announce();
  }

  applyHighlight() {
    const key = this.highlight;
    const matches = new Set(key ? this.model?.usage?.[key] ?? [] : []);
    for (const chip of this.chips) {
      const on = Boolean(key) && chip.dataset.feature === key;
      chip.classList.toggle('is-highlighted', on);
      chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    for (const [id, node] of this.entryNodes) node.classList.toggle('is-match', matches.has(id));
    if (this.statusNode && this.model) this.statusNode.textContent = highlightStatus(this.model);
  }

  /** What the drawer needs of the card's own state. */
  notesState() {
    return { highlight: this.highlight, scrolling: [...this.scrolling] };
  }

  relayout() {
    if (this.model) this.measureScroll();
  }

  clear() {
    this.lastPayload = null;
    this.lastOpts = null;
    this.model = null;
    this.chips = [];
    this.entryNodes = new Map();
    this.formulaBoxes = new Map();
    this.scrolling = [];
    this.statusNode = null;
    this.element?.replaceChildren();
  }

  setBusy(busy) {
    this.element?.classList?.toggle('is-busy', Boolean(busy));
  }
}
