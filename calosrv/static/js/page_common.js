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
 *
 * The three pages (Physics at /, Models at /models, Methodology at
 * /methodology) share one view through the URL hash, so the header's page tabs
 * carry the hash across (`wirePageTabs`): state.js writes the hash with
 * `history.replaceState`, which fires no event, so each tab's href is computed
 * when it is about to be followed - pressed, focused, clicked, middle-clicked
 * or opened from the context menu - never stored once at boot. The same
 * mechanism (`wireLiveLinks`) keeps the Methodology page's own links current.
 *
 * The Methodology page keeps the reader's place in one key of its own, `at`,
 * which no State reads or writes. Its badges open a panel on the other pages
 * with `?panel=<card>&from=<anchor>&from_sec=<section>`; `revealPanel` brings
 * the card into view and opens its Details drawer, and `returnLink` builds the
 * drawer's way back to the place in the article the reader left.
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

/**
 * A radio group built from labels.js choices (the Admin Settings pattern):
 * one `<label class="choice">` per choice, the text in a span of its own so a
 * wrapped line hangs under the text, the muted detail after it. `disabled`
 * maps a value to the reason it is not offered, shown as the label's title.
 * Returns `{set(value), setDisabled(map), inputs}`; `onChange(value)` hears a
 * choice the reader made, never one `set` made.
 */
export function choiceGroup(host, { name, choices, value = null, disabled = {}, onChange = () => {} }) {
  const inputs = new Map();
  const labels = new Map();
  if (!host) return { set() {}, setDisabled() {}, setChoices() {}, inputs };
  const build = (list) => {
    inputs.clear();
    labels.clear();
    host.replaceChildren(...list.map((choice) => {
      const label = document.createElement('label');
      label.className = 'choice';
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = name;
      input.value = choice.value;
      input.addEventListener('change', () => { if (input.checked) onChange(choice.value); });
      const text = document.createElement('span');
      text.append(choice.label);
      if (choice.detail) {
        const muted = document.createElement('span');
        muted.className = 'muted';
        muted.textContent = ` ${choice.detail}`;
        text.append(muted);
      }
      label.append(input, text);
      if (choice.title) label.title = choice.title;
      if (choice.hidden) label.hidden = true;
      inputs.set(choice.value, input);
      labels.set(choice.value, { label, title: choice.title ?? '' });
      return label;
    }));
  };
  const group = {
    inputs,
    set(next) {
      for (const [v, input] of inputs) input.checked = v === next;
    },
    setDisabled(map = {}) {
      for (const [v, input] of inputs) {
        const reason = map[v] ?? null;
        input.disabled = Boolean(reason);
        const { label, title } = labels.get(v);
        label.classList.toggle('is-disabled', Boolean(reason));
        if (reason) label.title = reason;
        else if (title) label.title = title;
        else label.removeAttribute('title');
      }
    },
    /** Rebuild with another list of choices (a relabelled tier), keeping `value` checked. */
    setChoices(list, next = null) {
      build(list);
      group.set(next);
    },
  };
  build(choices);
  group.set(value);
  group.setDisabled(disabled);
  return group;
}

/**
 * A page tab's href for the view in hand: its base path and query, then the
 * current hash (a link carries the whole view in its hash). A base that
 * carries a hash of its own has it replaced. Pure.
 */
export function tabHref(base, hash = '') {
  const path = String(base ?? '/').split('#')[0] || '/';
  const tail = String(hash ?? '').replace(/^#/, '');
  return tail ? `${path}#${tail}` : path;
}

/**
 * A hash with some keys set and some dropped, every other key kept as it
 * stands and in its place. `patch` maps a key to its new value; null or
 * undefined removes it. `drop` lists keys removed outright. Returns the hash
 * without its '#'. Pure.
 */
export function hashWith(hash = '', patch = {}, { drop = [] } = {}) {
  const params = new URLSearchParams(String(hash ?? '').replace(/^#/, ''));
  for (const key of drop) params.delete(key);
  for (const [key, value] of Object.entries(patch ?? {})) {
    if (value === null || value === undefined) params.delete(key);
    else params.set(key, String(value));
  }
  return params.toString();
}

/* The moments a link may be followed or copied: pointer, keyboard focus,
 * click, middle click and the context menu (copy link address). */
const TAB_EVENTS = ['pointerdown', 'focus', 'click', 'auxclick', 'contextmenu'];

/**
 * Keep links current: each link's href is recomputed by `hrefOf(link)` when it
 * is about to be followed or copied, in the capture phase, so the browser
 * reads the fresh href. Returns the links.
 */
export function wireLiveLinks(links, hrefOf) {
  const list = [...(links ?? [])];
  for (const link of list) {
    const update = () => { link.href = hrefOf(link); };
    for (const type of TAB_EVENTS) link.addEventListener(type, update, { capture: true });
  }
  return list;
}

/**
 * Keep every `a[data-page-tab]` link carrying the current view: the page
 * tabs and the Models page's Admin Settings link. Each link's base href is
 * kept in `dataset.base` and the hash is appended when it is about to be
 * followed. `drop` names keys of this page's own that the other pages have no
 * use for (the Methodology page's `at`); with none, the hash travels verbatim.
 */
export function wirePageTabs(root = document, { drop = [] } = {}) {
  const links = [...(root?.querySelectorAll?.('a[data-page-tab]') ?? [])];
  for (const link of links) {
    if (!link.dataset.base) link.dataset.base = link.getAttribute('href') || '/';
  }
  return wireLiveLinks(links, (link) => tabHref(link.dataset.base, drop.length
    ? hashWith(window.location.hash, {}, { drop })
    : window.location.hash));
}

/* ------------------------------------------- the Methodology's deep links */

/** A card id, an article anchor: lower-case words joined by hyphens. */
export const LINK_ID = /^[a-z][a-z0-9-]{0,63}$/;

/** A section number of the article: 2, 2.1 or 2.1.3. */
export const SECTION_NUMBER = /^\d{1,2}(\.\d{1,2}){0,2}$/;

/**
 * The deep link a Methodology badge carried, read from a page's query:
 * `{panel, from, section}` with each part validated (`LINK_ID`,
 * `SECTION_NUMBER`) and null where absent or malformed; null when the query
 * names no panel. Read before the first hash write, which drops the query.
 */
export function readDeepLink(search = '') {
  const params = new URLSearchParams(String(search ?? ''));
  const panel = params.get('panel');
  if (!panel) return null;
  const from = params.get('from');
  const section = params.get('from_sec');
  return {
    panel: LINK_ID.test(panel) ? panel : null,
    requested: panel,
    from: from && LINK_ID.test(from) ? from : null,
    section: section && SECTION_NUMBER.test(section) ? section : null,
  };
}

/**
 * The Methodology at one anchor, with the view in `hash`: the page's route,
 * the hash with `at` set to the anchor. Pure.
 */
export function methodologyHref(anchor, hash = '') {
  return tabHref('/methodology', hashWith(hash, { at: anchor }));
}

/**
 * The Details drawer's way back to the article: `{anchor, label, title}`, or
 * null when the deep link named no valid anchor. The label names the section
 * when its number came through, and says only "the Methodology" otherwise.
 */
export function returnLink(deepLink) {
  const anchor = deepLink?.from;
  if (!anchor || !LINK_ID.test(anchor)) return null;
  const section = deepLink.section && SECTION_NUMBER.test(deepLink.section) ? deepLink.section : null;
  return {
    anchor,
    label: section ? `↩ Continue reading §${section} in the Methodology` : '↩ Continue reading the Methodology',
    title: 'Back to the place in the Methodology this panel was opened from, with the view on screen now',
  };
}

/** Whether an element and every ancestor are shown (no `hidden` on the way up). */
function shownInPage(element) {
  for (let el = element; el; el = el.parentElement ?? el.parent ?? null) {
    if (el.hidden) return false;
  }
  return true;
}

/**
 * Bring one card into view and open its Details drawer: the landing of a
 * Methodology badge. `root` is searched for `.card[data-panel=<id>]`;
 * `reveal(id)`, when given, scrolls a card that loads lazily through its own
 * section (physics_section.js) and returns whether it did; otherwise the card
 * is scrolled into view here. Returns `{ok: true, card}`, or `{ok: false,
 * reason}` with reason 'unknown' (no such card on this page) or 'hidden' (the
 * experiment does not show it), for the caller's banner (`revealNotice`).
 */
export function revealPanel(panelId, { root = document, shell = null, reveal = null } = {}) {
  const id = String(panelId ?? '');
  const card = LINK_ID.test(id) ? root?.querySelector?.(`.card[data-panel="${id}"]`) ?? null : null;
  if (!card) return { ok: false, reason: 'unknown' };
  if (!shownInPage(card)) return { ok: false, reason: 'hidden', card };
  if (!reveal?.(id)) card.scrollIntoView?.({ block: 'start' });
  shell?.openInspector?.(id, { trigger: card.querySelector?.('[data-inspect]') ?? null });
  return { ok: true, card };
}

/**
 * The banner sentence for a deep link that could not land: `result` is
 * `revealPanel`'s, `title` the card's title, `kind` the experiment's kind
 * label. Empty for a link that landed.
 */
export function revealNotice(result, { requested = '', title = '', kind = '' } = {}) {
  if (!result || result.ok) return '';
  if (result.reason === 'hidden') {
    const name = title ? `the ${title} panel` : 'that panel';
    return `The Methodology linked to ${name}, which this experiment${kind ? ` (${kind})` : ''} does not show.`;
  }
  // The query is the link's, not this page's: a malformed name is not repeated.
  const named = LINK_ID.test(String(requested ?? '')) ? ` (${requested})` : '';
  return `The Methodology linked to a panel this page does not have${named}.`;
}

/**
 * Whether this browser can create a WebGL context, released at once: the 3-D
 * views are offered only where they can draw, and the page keeps no context
 * of its own (the views hold at most two).
 */
export function webglAvailable() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!gl) return false;
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}
