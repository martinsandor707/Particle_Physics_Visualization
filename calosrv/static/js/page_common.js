/* DOM helpers the page entry shares: the banner, error wording, the
 * experiment picker and runtime relabelling.
 *
 * Moved out of main.js so a second entry point can reuse them without
 * importing the Physics page's module (whose literal element ids belong to
 * index.html alone). Everything that writes text writes text nodes: a banner
 * line or an experiment name comes from a payload or an upload form, and is
 * never parsed as markup.
 *
 * `relabel` / `relabelChoice` exist because some labels depend on the active
 * experiment - a single-shower experiment filters on the incident momentum p
 * rather than E₁, and has a Shower-Aligned rather than a Separation-Aligned
 * frame tier - while the static markup keeps the two-shower wording the tests
 * pin. The original nodes are cloned once, on first relabel, and restored
 * exactly, so switching back to a two-shower experiment shows the markup as
 * shipped.
 */

import { ApiError } from './api.js';
import { formatInt } from './scale.js';

/** Escape text for the few places that still build markup from a template. */
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** A failure as one sentence for the banner. */
export function describeError(error) {
  if (error instanceof ApiError) return error.message;
  // The server was not reached: not the module-skew hint below.
  if (error?.name === 'NetworkError') return error.message;
  if (error instanceof TypeError) {
    // The signature of markup and script disagreeing about the document.
    return `${error.message} (the page and its scripts may be out of step; `
      + 'a hard reload should fix it)';
  }
  return String(error && error.message ? error.message : error);
}

/**
 * Fill a card's sparse-statistics note (`.sparse-note`) with one paragraph
 * per line, as text nodes, and hide it when there is nothing to say: the key
 * counts a panel states on screen without its Details drawer being opened.
 */
export function writeSparseNote(element, lines) {
  if (!element) return;
  const list = (lines || []).filter((line) => typeof line === 'string' && line);
  element.replaceChildren(...list.map((line) => {
    const p = document.createElement('p');
    p.textContent = line;
    return p;
  }));
  element.hidden = list.length === 0;
}

/** Log a failure and raise it on the banner as an error. */
export function reportError(banner, error, context = '') {
  console.error('[calosrv]', context || 'error', error);
  banner?.show([context ? `${context}: ${describeError(error)}` : describeError(error)], true);
}

/**
 * The page's message banner.
 *
 * Dismissal is keyed by content rather than by a counter, which is what makes
 * it stick: the same warning is re-sent on every response during a drag, and
 * a naive banner would pop straight back up.
 */
export class Banner {
  constructor({ root = 'banner', text = 'banner-text', close = 'banner-close' } = {}) {
    this.root = document.getElementById(root);
    this.text = document.getElementById(text);
    this.close = document.getElementById(close);
    this.dismissed = new Set();
    this.shown = [];
    this.close?.addEventListener('click', () => this.dismiss());
  }

  /** Show `messages` (those not dismissed), or hide the banner when none is left. */
  show(messages, isError = false) {
    const list = (messages || []).filter(Boolean).filter((m) => !this.dismissed.has(m));
    this.shown = list;
    if (!this.root) return;
    if (!list.length) {
      this.root.hidden = true;
      return;
    }
    this.root.hidden = false;
    this.root.classList.toggle('is-error', isError);
    if (this.text) {
      if (list.length === 1) {
        this.text.replaceChildren(document.createTextNode(String(list[0])));
      } else {
        const ul = document.createElement('ul');
        for (const message of list) {
          const li = document.createElement('li');
          li.textContent = String(message);
          ul.append(li);
        }
        this.text.replaceChildren(ul);
      }
    }
    this.root.dataset.messages = JSON.stringify(list);
  }

  /** Hide the banner and keep its messages from returning this session. */
  dismiss() {
    for (const message of this.shown) this.dismissed.add(message);
    this.shown = [];
    if (this.root) this.root.hidden = true;
  }
}

/** The compute badges of the header: DuckDB's memory ceiling and threads. */
export function fillComputeBadges(compute) {
  const memory = document.getElementById('badge-memory');
  const threads = document.getElementById('badge-threads');
  if (memory) memory.textContent = `${compute?.duckdb_memory_gb ?? '—'} GB`;
  if (threads) threads.textContent = String(compute?.threads ?? '—');
}

/**
 * The experiment picker's options, built as nodes.
 *
 * A ready experiment shows its event count and, when the catalogue names it,
 * its kind; one that is not ready shows its status and cannot be chosen. A
 * failed experiment's reason is its option's title.
 */
export function fillExperimentSelect(select, experiments) {
  if (!select) return;
  select.replaceChildren(...(experiments || []).map((e) => {
    const option = document.createElement('option');
    option.value = e.table_name;
    const kind = e.capabilities?.kind_label;
    const suffix = e.status === 'ready'
      ? ` — ${formatInt(e.n_events)} events${kind ? ` · ${kind}` : ''}`
      : ` — ${e.status}`;
    option.textContent = `${e.display_name || e.table_name}${suffix}`;
    option.disabled = e.status !== 'ready';
    if (e.error) option.title = e.error;
    return option;
  }));
}

/**
 * The experiment to open: the one the link names when it is ready, else the
 * first ready one; null when nothing is ready.
 */
export function chooseExperiment(experiments, wanted, { selectFirst = false } = {}) {
  const ready = (experiments || []).filter((e) => e.status === 'ready');
  if (!ready.length) return null;
  return (!selectFirst && ready.find((e) => e.table_name === wanted)) || ready[0];
}

/* The original children (and title) of every relabelled element, cloned once. */
const originals = new WeakMap();

function remember(el) {
  if (!originals.has(el)) {
    originals.set(el, {
      nodes: [...el.childNodes].map((node) => node.cloneNode(true)),
      title: el.getAttribute('title'),
      aria: el.getAttribute('aria-label'),
    });
  }
}

/** Replace an element's text, keeping its original children for `restoreLabel`. */
export function relabel(el, text) {
  if (!el) return;
  remember(el);
  el.replaceChildren(document.createTextNode(text));
}

/** Put a relabelled element back exactly as the markup shipped it. */
export function restoreLabel(el) {
  const saved = el ? originals.get(el) : null;
  if (!saved) return;
  el.replaceChildren(...saved.nodes.map((node) => node.cloneNode(true)));
  if (saved.title === null) el.removeAttribute('title');
  else el.setAttribute('title', saved.title);
  if (saved.aria === null) el.removeAttribute('aria-label');
  else el.setAttribute('aria-label', saved.aria);
}

/** Set an element's aria-label, keeping the shipped one for `restoreLabel`. */
export function relabelAria(el, text) {
  if (!el) return;
  remember(el);
  el.setAttribute('aria-label', text);
}

/**
 * Relabel a radio's `<label class="choice">`: its text and the muted detail
 * after it, and its title. The input itself is kept - it carries the checked
 * state and its listeners - so only the text around it changes. `null`
 * restores the shipped label.
 */
export function relabelChoice(input, spec) {
  const label = input?.closest('label');
  if (!label) return;
  remember(label);
  const saved = originals.get(label);
  if (!spec) {
    // The live input goes back where the markup had it; the clone of it is dropped.
    const nodes = saved.nodes.map((node) => (node.nodeName === 'INPUT' ? input : node.cloneNode(true)));
    label.replaceChildren(...nodes);
    baseTitles.set(label, saved.title);
  } else {
    const nodes = [input, document.createTextNode(` ${spec.label} `)];
    if (spec.detail) {
      const muted = document.createElement('span');
      muted.className = 'muted';
      muted.textContent = spec.detail;
      nodes.push(muted);
    }
    label.replaceChildren(...nodes);
    baseTitles.set(label, spec.title ?? saved.title);
  }
  setTitle(label, baseTitles.get(label));
}

/* The title a choice shows when nothing overrides it: the shipped one, or the
 * relabelled one. */
const baseTitles = new WeakMap();

function setTitle(el, title) {
  if (title === null || title === undefined || title === '') el.removeAttribute('title');
  else el.setAttribute('title', title);
}

/**
 * Override the title of a radio's `.choice` label - a disabled frame states
 * the server's reason - or, with null, give it back its own description.
 */
export function choiceTitle(input, title) {
  const label = input?.closest('label');
  if (!label) return;
  remember(label);
  if (!baseTitles.has(label)) baseTitles.set(label, originals.get(label).title);
  setTitle(label, title ?? baseTitles.get(label));
}
