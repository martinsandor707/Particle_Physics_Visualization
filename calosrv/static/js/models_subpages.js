/* The Models page's three subpages: Views, Distillations and Performance.
 *
 * The page's sections are grouped under one second-tier tab bar
 * (`#models-subnav`, a WAI-ARIA tablist) into three wrappers,
 * `#msub-views`, `#msub-distill` and `#msub-perf` (role tabpanel), whose
 * sections are capabilities.js `SUBPAGE_SECTIONS`. The subpage on show is the
 * State's `msub` key; Views is its default, so a link to Views carries none.
 *
 * A switch only toggles `hidden` on the three wrappers. It never creates or
 * disposes a card, a chart or a WebGL context: a card on a hidden subpage
 * keeps its panel, the 3-D views keep their two contexts and their cameras,
 * and a chart measured at zero size returns early (chart_panel.js,
 * voxel_views.js). A card on a hidden subpage never intersects `.main`, so
 * it never loads; a switch loads only the stale cards that come into view.
 *
 * Each subpage's scroll position in `.main` is kept in memory and restored on
 * return. It is not view state, so it never enters the link.
 *
 * The tab bar and the catalogue's bar share one sticky head at the top of
 * `.main` (`#models-head`, Martin's decision 6, 2026-11-05). Its height is
 * measured into `.main`'s `--models-head-h` (`watchHeadHeight`), which every
 * card takes as its scroll margin (css/models.css), so a card scrolled into
 * view or deep-linked lands below the head, never beneath it.
 *
 * Also here, as pure functions the page and its tests share: the subpage of a
 * card (`subpageOfCard`) and the cards of a subpage (`onSubpage`, which
 * filters the page banner's warnings); what the sidebar and the notices show
 * on a subpage (`colourMapShown`, `xgbNoticeShown`); and the benchmark
 * catalogue's species bar - the value a species button stores
 * (`benchSpeciesToStore`) and the caption under the bar (`benchCaption`).
 */

import { MODELS_CARDS } from './models_cards.js';
import {
  SUBPAGES, CATALOG_SPECIES, subpageOfSection, experimentSpecies, effectiveSpecies,
} from './capabilities.js';
import { MODELS_LABELS } from './labels.js';

/** The subpage a link without `msub` opens on (state.js DEFAULTS.msub). */
export const DEFAULT_SUBPAGE = 'views';

/** The 3-D views' card ids (voxel_views.js VOXEL_CARDS), all on Views: none is a MODELS_CARDS id. */
export const VOXEL_FAMILY = /^(vox|vproj|eproj)-/;

/**
 * The subpage that holds a card: a `MODELS_CARDS` id through its section's
 * subpage (capabilities.js `SUBPAGE_SECTIONS`), a 3-D card (`VOXEL_FAMILY`)
 * on Views, anything else null. Pure.
 */
export function subpageOfCard(id, cards = MODELS_CARDS) {
  const key = String(id ?? '');
  const spec = cards.find((card) => card.id === key);
  if (spec) return subpageOfSection(spec.section);
  return VOXEL_FAMILY.test(key) ? 'views' : null;
}

/**
 * A predicate on card ids: whether a card is on subpage `msub`. The page
 * banner shows the warnings of these cards only, so a warning never stands
 * above cards it does not describe. Pure.
 */
export function onSubpage(msub) {
  return (id) => subpageOfCard(id) === msub;
}

/**
 * Whether a subpage shows the sidebar's Colour Map (Martin's decision 3,
 * 2026-11-05): Views always (the 3-D views and the 2-D histograms);
 * Distillations while the XGBoost surrogate tree is on show; Performance while
 * the prediction density is. The catalogue's cards read no palette. Pure.
 */
export function colourMapShown(msub, plan) {
  if (msub === 'distill') return Boolean(plan?.sections?.xgbDistill);
  if (msub === 'perf') return Boolean(plan?.cards?.['pred-truth']?.shown);
  return true;
}

/**
 * Whether the notice saying why the XGBoost views are absent shows: only where
 * the XGBoost sections live, Distillations (E4, E5) and Performance (E1, E3),
 * and only while the plan has the notice. Views holds no XGBoost card. Pure.
 */
export function xgbNoticeShown(msub, plan) {
  return Boolean(plan?.xgbNotice) && (msub === 'distill' || msub === 'perf');
}

/**
 * The provenance sentence the catalogue's bar always ends with: the same text
 * as catalog/select.js `PROVENANCE`, which every catalogue payload carries (a
 * test holds the two equal). Written out here rather than imported: nothing
 * of the catalogue may load on Views or on the Physics page.
 */
export const BENCH_PROVENANCE = 'From the training report (models_performance.md; proton results dated '
  + '2026-09-24): documented point estimates, no intervals reported; the selection and the experiment do not '
  + 'apply.';

/** A catalogue species value as its button names it ('all' is Compare all). */
function speciesName(value) {
  return MODELS_LABELS.bench_species.find((choice) => choice.value === value)?.label ?? String(value);
}

/** Whether a stored `bench_species` names a choice (else it counts as none, as effectiveSpecies reads it). */
function isChoice(stored) {
  return stored === 'all' || CATALOG_SPECIES.includes(stored);
}

/**
 * What a click on a species button stores in `bench_species`: null when the
 * button is the species the experiment would show by itself
 * (`effectiveSpecies(null, plan)`), so the catalogue follows the experiment
 * again (the theme toggle's rule); the value otherwise. Pure.
 */
export function benchSpeciesToStore(value, plan) {
  return value === effectiveSpecies(null, plan) ? null : value;
}

/**
 * The sentence under the catalogue's bar: whether the species follows the
 * experiment or was chosen, and how to follow it again, then the provenance.
 * `open` is whether an experiment is open at all. Pure.
 */
export function benchCaption(stored, plan, { open = true } = {}) {
  const own = experimentSpecies(plan);
  const follow = effectiveSpecies(null, plan);
  let lead;
  if (!isChoice(stored)) {
    if (own) lead = `Following the experiment: ${speciesName(own)}, the species of its paired XGBoost models.`;
    else if (open) lead = 'This experiment does not name its species, so the catalogue shows all four.';
    else lead = 'No experiment is open, so the catalogue shows all four.';
  } else if (stored === follow) {
    lead = `Chosen: ${speciesName(stored)}, which is also what the experiment would show; the choice stays when `
      + 'the experiment changes.';
  } else {
    lead = `Chosen: ${speciesName(stored)}. Choose ${speciesName(follow)} to follow the experiment again.`;
  }
  return `${lead} ${BENCH_PROVENANCE}`;
}

/**
 * Keep the sticky head's height in a CSS custom property: `property` (default
 * `--models-head-h`) on `target` (`.main`), in whole pixels, rounded up so a
 * card's scroll margin never falls a fraction of a pixel short. A
 * ResizeObserver remeasures whenever the head changes size (the catalogue's
 * bar shown or hidden, its caption rewrapped, the column resized); `measure()`
 * measures at once, for a page that scrolls a card into view in the same task
 * as the change, before the observer has run. Returns `{measure, disconnect}`.
 */
export function watchHeadHeight({ head, target, property = '--models-head-h',
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

/** The keys that move the selection along the tab bar (WAI-ARIA tabs, automatic activation). */
function targetIndex(key, index, count) {
  if (key === 'ArrowRight') return (index + 1) % count;
  if (key === 'ArrowLeft') return (index - 1 + count) % count;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  return null;
}

/**
 * Wire the tab bar and the three wrappers.
 *
 * `root` holds `#msub-tab-<msub>`, `#msub-<msub>`, `.app` and `.main`
 * (document by default). The subpage the State holds is applied at once,
 * silently: no write and no `onSwitch`. Returns `{show, current}`:
 * `show(msub, {write = true})` switches (an unknown value means Views),
 * writes `msub` to the State unless `write` is false, and calls
 * `onSwitch(msub)` after the switch; showing the subpage already on show
 * changes nothing and returns false. `current()` is the subpage on show.
 */
export function mountSubnav({ state = null, root = document, onSwitch = () => {} } = {}) {
  const byId = (id) => root?.getElementById?.(id) ?? null;
  const tabs = new Map(SUBPAGES.map((msub) => [msub, byId(`msub-tab-${msub}`)]));
  const panels = new Map(SUBPAGES.map((msub) => [msub, byId(`msub-${msub}`)]));
  const app = root?.querySelector?.('.app') ?? null;
  const main = root?.querySelector?.('.main') ?? null;
  const scrollOf = new Map();
  let current = null;

  const valid = (msub) => (SUBPAGES.includes(msub) ? msub : DEFAULT_SUBPAGE);

  /** The wrappers' hidden flags, the tabs' selection and roving tabindex, and `.app[data-msub]`. */
  function apply(msub) {
    for (const key of SUBPAGES) {
      const on = key === msub;
      const panel = panels.get(key);
      if (panel) panel.hidden = !on;
      const tab = tabs.get(key);
      if (tab) {
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.setAttribute('tabindex', on ? '0' : '-1');
      }
    }
    if (app) app.dataset.msub = msub;
  }

  function show(msub, { write = true } = {}) {
    const next = valid(msub);
    if (next === current) {
      if (write) state?.set?.({ msub: next });
      return false;
    }
    if (main && current) scrollOf.set(current, main.scrollTop);
    apply(next);
    current = next;
    if (write) state?.set?.({ msub: next });
    onSwitch(next);
    // Restored last: `onSwitch` shows or hides the species bar in the sticky
    // head and the banners above the subpages, and a scroll restored before it
    // came back shifted by their height (scroll anchoring moved Views 77 px).
    // Writing scrollTop lays the page out first, so their change is already
    // absorbed here.
    if (main) main.scrollTop = scrollOf.get(next) ?? 0;
    return true;
  }

  SUBPAGES.forEach((msub, index) => {
    const tab = tabs.get(msub);
    if (!tab) return;
    tab.addEventListener('click', () => show(msub));
    tab.addEventListener('keydown', (event) => {
      const target = targetIndex(event?.key, index, SUBPAGES.length);
      if (target === null) return;
      event.preventDefault?.();
      const next = SUBPAGES[target];
      show(next);
      tabs.get(next)?.focus?.();
    });
  });

  current = valid(state?.get?.('msub'));
  apply(current);

  return { show, current: () => current };
}
