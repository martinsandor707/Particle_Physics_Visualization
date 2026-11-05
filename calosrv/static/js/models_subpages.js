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
 * Also here, as pure functions the page and its tests share: the subpage of a
 * card (`subpageOfCard`), and the benchmark catalogue's species bar - the
 * value a species button stores (`benchSpeciesToStore`) and the caption under
 * the bar (`benchCaption`).
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

/** The provenance sentence the catalogue's bar always ends with. */
export const BENCH_PROVENANCE = 'From the training report (models_performance.md): documented point estimates, '
  + 'no intervals reported; the selection and the experiment do not apply.';

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
    // Restored last: `onSwitch` shows or hides the species bar above the
    // subpages, and a scroll restored before it came back shifted by the bar's
    // height (scroll anchoring moved Views 77 px). Writing scrollTop lays the
    // page out first, so the bar's change is already absorbed here.
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
