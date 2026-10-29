/* The Methodology page's links: the badges into the other two pages, the
 * view they carry, and the article's one key of its own, `at`.
 *
 * ## The view a badge opens
 *
 * The article reads the reader's view and never writes it. A badge opens a
 * panel on the Physics or Models page with the view the reader came with, so
 * the panel shows their experiment, frame and model, not the built-in ones:
 *
 * - a hash carrying any view key (a State built from it is not a cold boot)
 *   travels verbatim, minus `at`, with the badge's own patch on top;
 * - a hash carrying none would open the other page on a cold boot, where the
 *   saved Admin Settings defaults apply. The link is then written out as the
 *   view that cold boot would give - the defaults applied in memory, the
 *   experiment the page would choose - so the badge and the page agree even
 *   if the defaults change later. That needs the catalogue
 *   (`/api/experiments`); until it arrives, and when it fails, the raw hash is
 *   used and the other page makes the same choice itself.
 *
 * The effective view is computed and never written to the address bar: a
 * cold hash stays cold, so the saved defaults keep governing this page's tabs.
 *
 * A Physics badge leaves the Event Inspector and the compare-frames view
 * (`event`, `compare`) unless it sets them itself: either replaces the
 * ensemble panels a badge opens, so a reader who pinned an event before
 * reading would otherwise land on a panel the view hides.
 *
 * ## `at`
 *
 * The page keeps the reader's place in `at=<id>`, which no State reads. It is
 * written in exactly one place (`writeAt`), when the reader clicks a TOC
 * entry, a heading's anchor or an equation's number; scrolling never writes
 * it, so the address bar does not churn while the article is read.
 */

import { SECTION_NUMBER, chooseExperiment, hashWith, tabHref } from '../page_common.js';
import { State } from '../state.js';
import { CHOICE_LABELS, frameLabel } from '../labels.js';

/** The pages a badge opens: their route and the name the badge reads. */
export const PAGES = Object.freeze({
  physics: Object.freeze({ route: '/', name: 'Physics' }),
  models: Object.freeze({ route: '/models', name: 'Models' }),
});

/** A badge's text: "Open in Physics → <label>". */
export function badgeText(item) {
  const page = PAGES[item?.page];
  return `Open in ${page ? page.name : String(item?.page ?? '')} → ${item?.label ?? ''}`;
}

/**
 * The query of a badge: `?panel=<card>&from=<row id>&from_sec=<section>`.
 * A section that is not a number (an appendix) is left out, and the landing
 * page names "the Methodology" alone. Pure.
 */
export function badgeQuery({ panel, from = null, section = null } = {}) {
  const params = new URLSearchParams();
  params.set('panel', String(panel ?? ''));
  if (from) params.set('from', String(from));
  if (section && SECTION_NUMBER.test(String(section))) params.set('from_sec', String(section));
  return `?${params.toString()}`;
}

/**
 * The view as the other pages would read it from this page's hash: a State,
 * never written. `at` is no State key, so it is read past.
 */
function readView() {
  return new State();
}

/**
 * The view a cold boot of the other pages would open, as a hash without '#':
 * the built-in view with the saved defaults applied, and the experiment the
 * page would choose (the default's, if ready, else the first ready one) first.
 * `state` is a cold State, which `applyDefaults` changes in memory only. Null
 * without a catalogue.
 */
export function effectiveColdHash(catalogue, state = readView()) {
  if (!catalogue || !Array.isArray(catalogue.experiments) || !state.coldBoot) return null;
  state.applyDefaults(catalogue.defaults ?? null);
  const chosen = chooseExperiment(catalogue.experiments, state.get('table_name'));
  const rest = hashWith(state.hashString(), {}, { drop: ['table_name'] });
  const head = chosen ? hashWith('', { table_name: chosen.table_name }) : '';
  return [head, rest].filter(Boolean).join('&');
}

/**
 * The hash a badge carries for `set`, without '#': the current view minus
 * `at` when the hash carries a view key, else the effective cold view once
 * `catalogue` has loaded, else the raw hash minus `at`. Reads
 * `window.location.hash`.
 */
export function viewHash(set = {}, { catalogue = null } = {}) {
  const state = readView();
  if (state.coldBoot) {
    const cold = effectiveColdHash(catalogue, state);
    if (cold !== null) return hashWith(cold, set ?? {});
  }
  return hashWith(window.location.hash, set ?? {}, { drop: ['at'] });
}

/**
 * A badge's href: the page's route, the badge's query, then the view.
 * `item` is the content's `{page, panel, set}`; `from` the badge row's id and
 * `section` its section number.
 */
export function badgeHref(item, { from = null, section = null, catalogue = null } = {}) {
  return tabHref(badgeBase(item, { from, section }), viewHash(badgeSet(item), { catalogue }));
}

/* The Physics view modes that replace the ensemble panels (main.js applyViewMode). */
const PHYSICS_VIEW_MODES = Object.freeze({ event: null, compare: null });

/** The patch a badge applies: its own `set`, on a Physics badge over leaving the view modes. Pure. */
export function badgeSet(item) {
  const set = item?.set ?? {};
  return item?.page === 'physics' ? { ...PHYSICS_VIEW_MODES, ...set } : set;
}

/** A badge's route and query, without the view: what the markup ships before the view is known. Pure. */
export function badgeBase(item, { from = null, section = null } = {}) {
  const route = PAGES[item?.page]?.route ?? '/';
  return `${route}${badgeQuery({ panel: item?.panel, from, section })}`;
}

/**
 * The view chip's text: the experiment, frame and model the badges open, or
 * null for "the default view" (a cold hash before the catalogue arrives).
 */
export function viewChipText({ catalogue = null } = {}) {
  const state = readView();
  if (state.coldBoot) {
    if (!catalogue) return null;
    state.applyDefaults(catalogue.defaults ?? null);
  }
  const chosen = chooseExperiment(catalogue?.experiments ?? [], state.get('table_name'));
  // Without a catalogue the link's own experiment is named; with one, only an experiment that is ready.
  let name = state.get('table_name') ?? 'the first ready experiment';
  if (chosen) name = chosen.display_name || chosen.table_name;
  else if (catalogue) name = 'no experiment ready';
  const showers = chosen?.capabilities?.n_showers === 1 ? 1 : 2;
  const model = CHOICE_LABELS.model.find((choice) => choice.value === state.get('model'))?.label ?? state.get('model');
  return `${name} · ${frameLabel(state.get('frame'), showers)} · ${model}`;
}

/** The anchor `at` names in `hash`, or null. */
export function readAt(hash = window.location.hash) {
  const value = new URLSearchParams(String(hash ?? '').replace(/^#/, '')).get('at');
  return value || null;
}

/**
 * Record the reader's place: `at=<id>` in the hash, every other key kept.
 * The page's only write to the address bar.
 */
export function writeAt(id) {
  const url = tabHref(`${window.location.pathname}${window.location.search}`, hashWith(window.location.hash, { at: id }));
  window.history.replaceState(window.history.state, '', url);
}
