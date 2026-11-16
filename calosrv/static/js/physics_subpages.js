/* The Physics page's two subpages: Entire selection and Event viewer.
 *
 * Both are grouped under one second-tier tab bar (`#physics-subnav`, a
 * WAI-ARIA tablist) into two wrappers, `#psub-selection` and `#psub-event`
 * (role tabpanel). The subpage on show is the State's `psub` key; Entire
 * selection is its default, so a link to it carries none (state.js).
 *
 * Each subpage has its own sidebar, status bar and requests. The sidebar and
 * the status bar are switched by CSS on `.app[data-psub]` and on
 * `[data-psub-only]` (css/controls.css), never through an element's own
 * `hidden`, which its owner controls. This module sets only the wrappers'
 * `hidden`, the tabs' ARIA state, `.app[data-psub]` and the status bar's mode
 * chip (`#stat-mode`).
 *
 * Each subpage's scroll position in `.main` is kept in memory and restored on
 * return. It is not view state, so it never enters the link.
 *
 * The tab bar sits in a sticky head at the top of `.main` (`#physics-head`).
 * Its height is measured into `.main`'s `--physics-head-h` (`watchHeadHeight`),
 * which every card takes as its scroll margin (css/controls.css), so a card
 * scrolled into view or deep-linked lands below the head, never beneath it.
 *
 * Modelled on models_subpages.js `mountSubnav`, but deliberately not
 * importing it: that module pulls the Models page's card graph, which the
 * Physics page never loads. The Event viewer tab can be shut with a reason
 * (`setEnabled`), as for an event-level aggregate that holds no hits: the
 * reason is its title and, since a title is hover-only, a visible sentence
 * under the tab bar (`#psub-shut`); the shut tab stays in the arrow keys'
 * order, so the keyboard reaches it, and activates nothing (review U3).
 *
 * Pure helpers (`psubOfCard`, `eventStatus`, `selectionTabTitle`,
 * `shutLine`) are DOM-free, so they run under Node.
 */

import { formatSigned } from './format.js';
import { formatInt, formatSci } from './scale.js';

/** The subpages, in tab order. */
const PSUBS = Object.freeze(['selection', 'event']);

/** Entire selection: the default, never written to the link. */
export const DEFAULT_PSUB = 'selection';

/** The tabs' text, and the status bar's mode chip. */
export const PSUB_LABELS = Object.freeze({ selection: 'Entire selection', event: 'Event viewer' });

/**
 * The subpage a Physics card lives on: `'event'` for an `event-` card (the
 * Event Inspector's nine panels), `'selection'` for every other one (`xy`,
 * `yz`, `xz`, `energy`, the `compare-*` panels and the physics cards). Pure.
 * Anything that is not a string, or an empty id, is not an event card either,
 * so it takes the default: the caller decides whether such an id exists.
 */
export function psubOfCard(id) {
  return typeof id === 'string' && id.startsWith('event-') ? 'event' : DEFAULT_PSUB;
}

/**
 * The Entire selection tab's title for an experiment's page plan
 * (capabilities.js `page1Plan`): what the subpage shows and the filter that
 * selects it. Two showers: the 2 × 2, the compare-frames view and the physics
 * cards under E₁, E₂ and D (the markup's own text); one shower: the same under
 * the p window; an event-level aggregate, which holds no hits: its physics
 * cards alone. Pure (review R3).
 */
export function selectionTabTitle(plan) {
  if (plan && plan.spatial === false) {
    return "Every selected event's physics cards, under the p window; this experiment has no hits to project.";
  }
  if (plan?.nShowers === 1) {
    return 'Every selected event: the 2 × 2 diagnostic, the compare-frames view and the physics cards, '
      + 'under the p window.';
  }
  return 'Every selected event: the 2 × 2 diagnostic, the compare-frames view and the physics cards, '
    + 'under E₁, E₂ and D.';
}

/** The visible sentence a shut tab gets (`#psub-shut`): its subpage and the reason. Pure. */
export function shutLine(psub, reason = '') {
  const label = PSUB_LABELS[psub] ?? String(psub);
  return `The ${label} is not available for this experiment: ${reason ?? ''}`.trim();
}

/** A finite number, or NaN: `Number(null)` is 0, which would print a missing field as a measurement. */
const num = (value) => (value === null || value === undefined || value === '' ? NaN : Number(value));

/** A display number, or the dash a missing one gets. */
const orDash = (text) => (text === '' || text === null || text === undefined ? '—' : text);

/**
 * The Event viewer's status-bar items, as display strings, from the payload of
 * GET /api/event (`payload.event`, or the event block itself):
 * `{event, shower, p, theta, cells, edep, place}`. A missing field is `'—'`.
 *
 * - `event`: the event number, grouped;
 * - `shower`: the drawn shower's label (A, B), `'—'` on one shower, where the
 *   item is hidden;
 * - `p`: "5.41 GeV" (two decimals); `theta`: "12.3°" (one decimal);
 * - `cells`: the shower's cell count; `edep`: its deposited energy as
 *   `eventRowLabel` writes it, "1.23e-2 GeV" style through `formatSci`;
 * - `place`: "12 of 107" in the pool, "not a candidate" outside it. A payload
 *   without a candidates block says nothing. Pure.
 */
export function eventStatus(payload, { nShowers = 2 } = {}) {
  const event = payload?.event ?? payload ?? null;
  const shower = event?.shower ?? null;
  const number = num(event?.event_number);
  const p = num(shower?.momentum_gev);
  const theta = num(shower?.theta_deg);
  const cells = num(shower?.n_hits);
  const edep = num(shower?.energy_gev);
  const label = shower ? (shower.label ?? String(shower.key ?? '').toUpperCase()) : '';
  const candidates = event?.candidates ?? null;
  let place = '—';
  if (candidates && candidates.in_pool === true) {
    const index = num(candidates.index);
    const total = num(candidates.n_events);
    place = Number.isFinite(index) && Number.isFinite(total)
      ? `${formatInt(index + 1)} of ${formatInt(total)}` : '—';
  } else if (candidates && candidates.in_pool === false) {
    place = 'not a candidate';
  }
  return {
    event: Number.isFinite(number) ? formatInt(number) : '—',
    shower: nShowers === 1 ? '—' : orDash(label),
    p: Number.isFinite(p) ? `${formatSigned(p, 2)} GeV` : '—',
    theta: Number.isFinite(theta) ? `${formatSigned(theta, 1)}°` : '—',
    cells: Number.isFinite(cells) ? formatInt(cells) : '—',
    edep: Number.isFinite(edep) ? `${formatSci(edep, 3)} GeV` : '—',
    place,
  };
}

/**
 * Keep the sticky head's height in a CSS custom property: `property` (default
 * `--physics-head-h`) on `target` (`.main`), in whole pixels, rounded up so a
 * card's scroll margin never falls a fraction of a pixel short. A
 * ResizeObserver remeasures whenever the head changes size (the banner above
 * it, a rewrapped tab bar, the column resized); `measure()` measures at once,
 * for a page that scrolls a card into view in the same task as the change.
 * Returns `{measure, disconnect}`. (Its own copy: models_subpages.js is not
 * imported here.)
 */
export function watchHeadHeight({ head, target, property = '--physics-head-h',
  Observer = globalThis.ResizeObserver } = {}) {
  const measure = () => {
    if (!head || !target?.style) return null;
    const height = Math.ceil(head.getBoundingClientRect?.().height ?? 0);
    target.style.setProperty(property, `${height}px`);
    return height;
  };
  const observer = head && typeof Observer === 'function' ? new Observer(() => measure()) : null;
  observer?.observe(head);
  measure();
  return { measure, disconnect: () => observer?.disconnect() };
}

/**
 * The tab a key moves to from `index` (WAI-ARIA tabs): arrows wrap, Home and
 * End jump to the first and last tab. A shut tab stays in this order, so the
 * keyboard reaches it and its reason (review U3); the caller only focuses it,
 * activating nothing. Null for any other key.
 */
function targetIndex(key, index, count) {
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  const step = key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0;
  if (!step) return null;
  return (((index + step) % count) + count) % count;
}

/**
 * Wire the tab bar and the two wrappers.
 *
 * `root` holds `#psub-tab-<psub>`, `#psub-<psub>`, `#physics-head`,
 * `#psub-shut`, `#stat-mode`, `.app` and `.main` (document by default). The
 * subpage the State holds is applied at once, silently: no write and no
 * `onSwitch`. Returns `{show, current, setEnabled, setTitle, measureHead}`:
 *
 * - `show(psub, {write = true})` switches (an unknown value means Entire
 *   selection), writes `psub` to the State unless `write` is false, and calls
 *   `onSwitch(psub)` after the switch. It returns false, changing nothing,
 *   when the subpage is already on show or its tab is disabled;
 * - `current()` is the subpage on show;
 * - `setEnabled(psub, enabled, reason)` shuts or opens a tab: shut, it carries
 *   `aria-disabled="true"`, the class `is-disabled`, the reason as its title
 *   and `aria-describedby="psub-shut"`, and `#psub-shut` shows `shutLine`;
 *   the arrows, Home and End still move focus onto it, but no key or click
 *   activates it. Opened again, it gets its own title back (the markup's, or
 *   the last `setTitle`) and the sentence goes. It never switches the subpage
 *   itself: a caller that shuts the tab on show shows Entire selection;
 * - `setTitle(psub, title)` replaces a tab's own title (shown while it is
 *   open), as each experiment's `selectionTabTitle`;
 * - `measureHead()` measures the sticky head into `--physics-head-h` at once.
 */
export function mountPhysicsSubnav({ state = null, root = document, onSwitch = () => {} } = {}) {
  const byId = (id) => root?.getElementById?.(id) ?? null;
  const tabs = new Map(PSUBS.map((psub) => [psub, byId(`psub-tab-${psub}`)]));
  const panels = new Map(PSUBS.map((psub) => [psub, byId(`psub-${psub}`)]));
  const app = root?.querySelector?.('.app') ?? null;
  const main = root?.querySelector?.('.main') ?? null;
  const chip = byId('stat-mode');
  const shutText = byId('psub-shut');
  const markupTitle = new Map(PSUBS.map((psub) => [psub, tabs.get(psub)?.getAttribute?.('title') ?? tabs.get(psub)?.title ?? '']));
  const disabled = new Set();
  // Each shut tab's reason, in tab order, for the visible sentence.
  const reasons = new Map();
  const scrollOf = new Map();
  let current = null;

  const valid = (psub) => (PSUBS.includes(psub) ? psub : DEFAULT_PSUB);

  /** The wrappers' hidden flags, the tabs' selection and roving tabindex, `.app[data-psub]` and the chip. */
  function apply(psub) {
    for (const key of PSUBS) {
      const on = key === psub;
      const panel = panels.get(key);
      if (panel) panel.hidden = !on;
      const tab = tabs.get(key);
      if (tab) {
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.setAttribute('tabindex', on ? '0' : '-1');
      }
    }
    if (app) app.dataset.psub = psub;
    if (chip) chip.textContent = PSUB_LABELS[psub];
  }

  function show(psub, { write = true } = {}) {
    const next = valid(psub);
    if (disabled.has(next)) return false;
    if (next === current) {
      if (write) state?.set?.({ psub: next });
      return false;
    }
    if (main && current) scrollOf.set(current, main.scrollTop);
    apply(next);
    current = next;
    if (write) state?.set?.({ psub: next });
    onSwitch(next);
    // Restored last: `onSwitch` shows or hides the banners and notices above
    // the subpages, and a scroll restored before it came back shifted by
    // their height. Writing scrollTop lays the page out first, so their
    // change is already absorbed here.
    if (main) main.scrollTop = scrollOf.get(next) ?? 0;
    return true;
  }

  /** The visible sentence under the tab bar: one per shut tab, hidden while none is shut. */
  function writeShut() {
    if (!shutText) return;
    const lines = PSUBS.filter((psub) => reasons.has(psub)).map((psub) => shutLine(psub, reasons.get(psub)));
    shutText.textContent = lines.join(' ');
    shutText.hidden = lines.length === 0;
  }

  function setEnabled(psub, enabled, reason = '') {
    const tab = tabs.get(psub);
    if (!tab) return;
    if (enabled) {
      disabled.delete(psub);
      reasons.delete(psub);
      tab.removeAttribute('aria-disabled');
      tab.removeAttribute('aria-describedby');
      tab.classList.remove('is-disabled');
      tab.setAttribute('title', markupTitle.get(psub) ?? '');
    } else {
      disabled.add(psub);
      reasons.set(psub, reason ?? '');
      tab.setAttribute('aria-disabled', 'true');
      if (shutText) tab.setAttribute('aria-describedby', 'psub-shut');
      tab.classList.add('is-disabled');
      tab.setAttribute('title', reason ?? '');
    }
    writeShut();
  }

  function setTitle(psub, title) {
    const tab = tabs.get(psub);
    if (!tab || typeof title !== 'string') return;
    markupTitle.set(psub, title);
    if (!disabled.has(psub)) tab.setAttribute('title', title);
  }

  PSUBS.forEach((psub, index) => {
    const tab = tabs.get(psub);
    if (!tab) return;
    tab.addEventListener('click', () => {
      if (disabled.has(psub)) return;
      show(psub);
    });
    tab.addEventListener('keydown', (event) => {
      // Handled on a shut tab too (it is reached by the arrows); Enter and Space reach the click, which ignores it.
      const target = targetIndex(event?.key, index, PSUBS.length);
      if (target === null) return;
      event.preventDefault?.();
      const next = PSUBS[target];
      // An open tab is activated (automatic activation); a shut one is only focused, so its reason can be read.
      if (!disabled.has(next)) show(next);
      tabs.get(next)?.focus?.();
    });
  });

  current = valid(state?.get?.('psub'));
  apply(current);

  const head = watchHeadHeight({ head: byId('physics-head'), target: main });

  return { show, current: () => current, setEnabled, setTitle, measureHead: head.measure };
}
