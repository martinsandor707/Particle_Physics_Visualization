/* The Models page (/models): bootstrap and control wiring.
 *
 * What the page shows is decided per experiment from its capability block
 * (capabilities.js `page2Plan`): the network performance cards where there
 * are networks (or an XGBoost regressor paired with an event-level
 * aggregate), the XGBoost views where a model run pairs with the experiment,
 * the feature explorer, the primaries and the 3-D views where there are hits.
 * A card the experiment cannot serve is shut with the server's sentence; an
 * experiment without network predictions says so in a prominent banner
 * (CLAUDE.md section 3), and one no model run pairs with says why the XGBoost
 * views are absent.
 *
 * The page shares one view with the Physics page through the URL hash (the
 * experiment, the filters, the frame and the network), so its tabs carry the
 * hash across; its own keys - the feature, the 3-D event, the XGBoost task -
 * travel in the same hash and are never written by the Physics page away.
 *
 * Switching experiment clears every picture of the previous one first: the
 * requests in flight are aborted, the cached responses dropped, the cards
 * blanked, and every card checks its request key after its response lands,
 * so a late response never draws the previous experiment's data under the
 * new one's name.
 *
 * The 3-D views (js/voxel_views.js `VoxelSection`) and the 2-D panel modules
 * are imported on first use by dynamic import. A module that fails to load
 * (the network, a stale cache) says so where it would have drawn instead of
 * taking the page down.
 */

import { getJson, debounce, DEBOUNCE_MS, isAbort } from './api.js';
import { State } from './state.js';
import { Shell } from './shell.js';
import { FilterBlock } from './controls/filter_block.js';
import { attachExportMenus } from './export/menu.js';
import { LazyCards } from './lazy_cards.js';
import { page2Plan, viewFrame } from './capabilities.js';
import { CHOICE_LABELS, isLegacyFrame } from './labels.js';
import {
  Banner, describeError, fillComputeBadges, fillExperimentSelect, chooseExperiment, choiceGroup,
  wirePageTabs, tabHref, readDeepLink, returnLink, revealPanel, revealNotice,
} from './page_common.js';
import { ModelsSection } from './models_cards.js';
import { formatInt, formatNumber } from './scale.js';
import { setText, setHidden, setVal, missingIds } from './dom.js';
import { notesText, warningsNotShown } from './panel_notes.js';

const state = new State();

/* The two side panels; constructed before any chart, so a sidebar stored as
 * collapsed is already collapsed when the panels first measure. */
const shell = new Shell({
  getNotes: (panelId) => buildNotes(panelId),
  onLayoutChange: () => relayoutAll(),
});

/* Transient messages (dismissal keyed by content); what the experiment
 * cannot show and why; the missing-predictions banner (CLAUDE.md section 3). */
const banner = new Banner();
const kindBanner = new Banner({ root: 'kind-banner', text: 'kind-banner-text', close: 'kind-banner-close' });

const main = document.querySelector('.main');

let experiments = [];
let activeExperiment = null;
let plan = page2Plan(null);

/* -------------------------------------------------------------- the cards */

/* The 2-D cards (models_cards.js), built now, before the export menus are
 * wired, so their Export buttons are wired with the rest. */
const models = new ModelsSection({
  perf: document.getElementById('perf-grid'),
  xgb: document.getElementById('xgb-grid'),
  features: document.getElementById('features-grid'),
  primaries: document.getElementById('primaries-grid'),
}, {
  state,
  root: main,
  getExperiment: () => activeExperiment,
  onRendered: (id, payload) => {
    buildNotes(id);
    updateStatus(payload);
  },
  onError: (error, context) => reportError(error, context),
  onStateChange: (patch) => onSharedChange(patch),
  onOpenAdmin: () => openAdmin(),
});

/* The 3-D views, mounted by `mountVoxels` once their module has loaded. */
let voxels = null;

/** What the 3-D views' host says when their module failed to load. */
const VOXELS_FAILED = 'The 3-D views could not be loaded; reload the page (Ctrl+Shift+R) to try again.';

/**
 * Mount the 3-D views into `#voxels-grid`: a guarded dynamic import, so a
 * module that fails to load leaves a sentence in the host and the rest of the
 * page working.
 */
async function mountVoxels() {
  const host = document.getElementById('voxels-grid');
  if (!host) return null;
  let module = null;
  try {
    module = await import('./voxel_views.js');
  } catch (error) {
    reportError(error, '3-D views');
  }
  if (typeof module?.VoxelSection !== 'function') {
    const note = document.createElement('p');
    note.className = 'voxels-pending';
    note.textContent = VOXELS_FAILED;
    host.replaceChildren(note);
    return null;
  }
  try {
    return new module.VoxelSection(host, {
      state,
      getExperiment: () => activeExperiment,
      onError: (error, context) => reportError(error, context),
      onRendered: (id, payload) => {
        buildNotes(id);
        updateStatus(payload);
      },
      // The section's own lazy loader over the page's scroll container: in
      // view means in view (decision D3), as for every other card.
      lazy: new LazyCards({
        root: main,
        rootMargin: '0px',
        onError: (error) => { if (!isAbort(error)) reportError(error, '3-D views'); },
      }),
    });
  } catch (error) {
    reportError(error, '3-D views');
    return null;
  }
}

/* ------------------------------------------------------------- the drawer */

/* What the Details drawer says about each card, built from the payloads by
 * the notes builders and never read off the page. */
const notesStore = {};

/** Rebuild one card's notes, flag its Details button and refresh the drawer. */
function buildNotes(panelId) {
  let notes = null;
  const context = { state, experiment: activeExperiment };
  if (models.has(panelId)) notes = models.notes(panelId, context);
  else if (voxels?.has?.(panelId)) notes = voxels.notes(panelId, context) ?? null;
  notesStore[panelId] = notes;
  markDetails(panelId, notes);
  shell.refresh(panelId, notes);
  return notes;
}

/** Flag a card's Details button when its notes name a hazard the reader should open. */
function markDetails(panelId, notes) {
  const button = document.querySelector(`[data-inspect="${panelId}"]`);
  if (!button) return;
  const hazards = notes?.hazards ?? [];
  button.classList.toggle('is-flagged', hazards.length > 0);
  button.title = hazards.length
    ? `Details — ${hazards.join('; ')}`
    : 'Methodology and disclosures for this panel';
}

/** Re-lay every chart out at its container's current size (the tracks snap, so this is the final geometry). */
function relayoutAll() {
  models.relayout();
  voxels?.relayout?.();
}

/* ------------------------------------------------------------- the status */

/**
 * The status bar's readouts from a card's response: the selection's event
 * count (a whole-experiment XGBoost view states `filtered: false` and counts
 * no selection) and the query time.
 */
function updateStatus(payload) {
  if (!payload) return;
  if (payload.filtered !== false) {
    const n = [payload.n_selected, payload.n_events, payload.overall?.n_events, payload.selection?.n_events]
      .find((value) => Number.isFinite(value));
    if (n !== undefined) setText('stat-events', formatInt(n));
  }
  const ms = payload.meta?.total_ms ?? payload.meta?.elapsed_ms;
  if (Number.isFinite(ms)) setText('stat-latency', `${formatNumber(ms, 1)} ms`);
}

function reportError(error, context = '') {
  if (isAbort(error)) return;
  console.error('[calosrv]', context || 'error', error);
  banner.show([context ? `${context}: ${describeError(error)}` : describeError(error)], true);
}

/**
 * The union of every card's warnings, without the text the reader can
 * already see: the notes of the card whose drawer is open.
 */
function mergedWarnings() {
  const shown = shell.inspected ? notesText(notesStore[shell.inspected]) : '';
  return warningsNotShown([...models.warnings(), ...(voxels?.warnings?.() ?? [])], shown);
}

/* ------------------------------------------------------------ the sidebar */

/* The network: drives the performance cards' task (energy or angle) and the
 * network whose attention maps the 3-D views draw. */
const modelGroup = choiceGroup(document.getElementById('m-model'), {
  name: 'm-model',
  choices: CHOICE_LABELS.model,
  value: state.get('model'),
  onChange: (value) => {
    state.set({ model: value });
    onSharedChange({ model: value });
  },
});

/* The reference frame, flat: one radio per frame the experiment offers. */
let frameGroup = null;

/** The frame radios for a plan: a single shower names its frames as its own tier does. */
function frameChoices(current) {
  const single = plan.nShowers === 1;
  const relabel = plan.frames.labels;
  return CHOICE_LABELS.frame.map((choice) => {
    if (single && choice.value === 'trans' && relabel?.trans) {
      return { value: 'trans', label: relabel.trans.label, detail: relabel.trans.detail, title: relabel.trans.title };
    }
    if (single && choice.value === 'local' && relabel?.aligned) {
      return { value: 'local', label: `${relabel.aligned.label} › Local`, detail: choice.detail };
    }
    // The legacy per-shower frame has no radio of its own on two showers:
    // only a link or a saved default that holds it shows it.
    const hidden = !single && isLegacyFrame(choice.value) && current !== choice.value;
    return { ...choice, hidden };
  });
}

/** The frame the page draws in: the selected one where offered, else the fallback (never written). */
function effectiveFrame() {
  const frame = state.get('frame');
  const offered = plan.frames.offered;
  if (offered.includes(frame)) return frame;
  return offered.includes('lab') ? 'lab' : (offered[0] ?? frame);
}

function syncFrameControl() {
  const host = document.getElementById('m-frame');
  const current = state.get('frame');
  const shown = effectiveFrame();
  if (!frameGroup) {
    frameGroup = choiceGroup(host, {
      name: 'm-frame',
      choices: frameChoices(current),
      value: shown,
      onChange: (value) => {
        state.set({ frame: value });
        syncFrameControl();
        onSharedChange({ frame: value });
      },
    });
  } else {
    frameGroup.setChoices(frameChoices(current), shown);
  }
  frameGroup.setDisabled(plan.frames.disabled);
  setHidden('group-m-frame', plan.frames.offered.length === 0);
  const lines = [];
  if (current !== shown) {
    lines.push(`The link's frame is not offered for this experiment (${plan.kindLabel}); the page draws in `
      + `${frameChoices(current).find((c) => c.value === shown)?.label ?? shown}.`);
  }
  const ensemble = viewFrame('ensemble', shown, plan.frames.offered, plan.nShowers);
  lines.push('The feature explorer and the 3-D event view draw in this frame where they can; the ensemble '
    + `cloud draws in a co-registered frame${ensemble.fallback && ensemble.frame ? ' (Local here)' : ''}. A card `
    + 'drawn in another frame says so under its title.');
  setText('m-frame-caption', lines.join(' '));
}

function syncModelControl() {
  const offered = new Set(plan.models);
  const reason = plan.networks ? 'Not in this experiment.' : 'No reconstruction networks in this experiment.';
  modelGroup.set(state.get('model'));
  modelGroup.setDisabled(Object.fromEntries(CHOICE_LABELS.model
    .filter((choice) => !offered.has(choice.value)).map((choice) => [choice.value, reason])));
  let caption = 'Drives the performance cards (energy or angle) and the network whose attention maps the 3-D '
    + 'views draw.';
  if (!plan.networks) {
    caption = plan.xgb.tasks.length
      ? 'No reconstruction networks in this experiment: the performance cards draw the paired XGBoost '
        + 'regressor, whose task is chosen on the cards.'
      : 'No reconstruction networks in this experiment: the network choice has nothing to drive.';
  }
  setText('m-model-caption', caption);
}

/** A card control or the sidebar wrote a shared key: every view that reads it follows. */
function onSharedChange() {
  syncModelControl();
  syncFrameControl();
  models.sync();
  refreshAll();
}

/* -------------------------------------------------------------- the plan */

/** The page around the cards for a plan: banners, sections, sidebar, status. */
function applyPagePlan(notices = []) {
  // The XGBoost notice: hidden once a model run pairs with the experiment.
  setHidden('xgb-notice', !plan.xgbNotice);
  setText('xgb-notice-text', plan.xgbNotice ?? '');
  // The missing-predictions banner (CLAUDE.md section 3).
  setHidden('networks-notice', !plan.banner);
  setText('networks-notice-text', plan.banner ?? '');
  kindBanner.show([...plan.notices, ...notices]);

  const sections = {
    perf: 'perf-grid', xgb: 'xgb-grid', features: 'features-grid', primaries: 'primaries-grid', voxels: 'voxels-grid',
  };
  for (const [key, id] of Object.entries(sections)) setHidden(id, !plan.sections[key]);
  const run = plan.xgb.runs[0];
  setText('xgb-grid-title', run
    ? `XGBoost model — ${run.species ?? 'species unknown'}, seed ${run.seed ?? '—'}` : 'XGBoost model');

  setText('stat-kind', plan.kindLabel);
  syncModelControl();
  syncFrameControl();
}

/* --------------------------------------------------------- orchestration */

/* The refresh in charge of the banner: a refresh that a newer one overtook
 * leaves it to the newer one. */
let refreshToken = 0;

/**
 * Refresh every visible card. The two sections settle independently, so a
 * failing card degrades itself, not the page.
 */
const refreshAll = debounce(async () => {
  const token = ++refreshToken;
  const jobs = [['model cards', () => models.refresh()]];
  if (voxels && plan.sections.voxels) jobs.push(['3-D views', () => voxels.refresh()]);
  const results = await Promise.allSettled(jobs.map(([, run]) => run()));
  if (token !== refreshToken) return;
  const failures = [];
  results.forEach((result, index) => {
    if (result.status !== 'rejected' || isAbort(result.reason)) return;
    console.error(`[calosrv] ${jobs[index][0]} failed`, result.reason);
    failures.push(`${jobs[index][0]}: ${describeError(result.reason)}`);
  });
  if (failures.length) banner.show(failures, true);
  else banner.show(mergedWarnings());
}, DEBOUNCE_MS);

/** Redraw from the payloads in hand, without a request (a palette change). */
function repaint() {
  models.repaint();
  voxels?.repaint?.();
}

/** Admin Settings live on the Physics page; `/?admin=1` opens them there, with this view. */
function openAdmin() {
  window.location.assign(tabHref('/?admin=1', window.location.hash));
}

/* ---------------------------------------------------------- experiments */

async function loadCatalogue() {
  const payload = await getJson('/api/experiments', {}, 'experiments');
  experiments = payload.experiments;
  fillComputeBadges(payload.compute);

  // A link without view state opens on the Admin Settings panel's defaults,
  // as the Physics page does.
  const notices = [];
  if (state.applyDefaults(payload.defaults)) {
    restoreControlsFromState();
    notices.push(...(payload.defaults?.notices || []));
  }

  fillExperimentSelect(document.getElementById('experiment-select'), experiments);
  const failed = experiments.filter((e) => e.status === 'failed' && e.error)
    .map((e) => `${e.display_name || e.table_name}: ${e.error}`);
  if (failed.length || notices.length) banner.show([...notices, ...failed]);

  const chosen = chooseExperiment(experiments, state.get('table_name'));
  if (!chosen) {
    banner.show([
      'No experiment has finished ingesting yet. Open Admin Settings on the Physics page → Upload dataset, '
      + 'or run the offline ingest CLI on the server.',
    ], true);
    return null;
  }
  setVal('experiment-select', chosen.table_name);
  activate(chosen);
  return chosen;
}

/**
 * Open one experiment: its plan, its banners and sidebar, its filters and
 * bounds, every card stale, then one refresh of the visible ones.
 */
function activate(experiment) {
  const previous = activeExperiment;
  activeExperiment = experiment;
  plan = page2Plan(experiment);
  state.set({ table_name: experiment.table_name }, { silent: true });
  if (previous && previous.table_name !== experiment.table_name) {
    clearExperimentViews();
    kindBanner.dismissed.clear();
  }
  applyPagePlan();
  // The experiment's own filter axes and bounds; the domains are recorded
  // before the one hash write, so a link carries no raw dataset bound.
  filters.adopt(experiment, plan.axes);
  models.applyPlan(plan);
  if (previous && previous.table_name === experiment.table_name) models.invalidate();
  voxels?.applyPlan?.(plan.voxels);
  refreshAll.flush();
}

/**
 * Take down everything the previous experiment drew: the requests in flight
 * (aborted), the cached responses, every card, the status readouts and the
 * notes.
 */
function clearExperimentViews() {
  refreshAll.cancel();
  models.reset();
  voxels?.reset?.();
  for (const id of STATUS_IDS) setText(id, '—');
  for (const id of Object.keys(notesStore)) {
    notesStore[id] = null;
    markDetails(id, null);
    shell.refresh(id, null);
  }
}

/* The status bar's readouts of one selection. */
const STATUS_IDS = ['stat-events', 'stat-kind', 'stat-latency'];

/* ------------------------------------------------------------- wiring */

/* The filter sliders, adopted per experiment: a release refreshes the cards
 * in view (the Models page draws no sampled preview while dragging). */
const filters = new FilterBlock({ state, onCommit: () => refreshAll() });

document.getElementById('experiment-select')?.addEventListener('change', (event) => {
  const experiment = experiments.find((e) => e.table_name === event.target.value);
  if (experiment) activate(experiment);
});

document.getElementById('m-colormap')?.addEventListener('change', (event) => {
  state.set({ palette: event.target.value });
  // A pure repaint of the data in hand: no round trip.
  repaint();
});

function restoreControlsFromState() {
  setVal('m-colormap', state.get('palette'));
  modelGroup.set(state.get('model'));
}

/* Every element id this page's modules write to, audited at startup so a
 * markup/script mismatch is named on screen rather than surfacing as a
 * blank readout. */
const MODELS_REQUIRED_IDS = [
  'sidebar', 'sidebar-toggle', 'inspector', 'inspector-title', 'inspector-body', 'inspector-close',
  'banner', 'banner-text', 'banner-close', 'kind-banner', 'kind-banner-text', 'kind-banner-close',
  'xgb-notice', 'xgb-notice-text', 'networks-notice', 'networks-notice-text',
  'stat-events', 'stat-kind', 'stat-latency', 'experiment-select', 'badge-memory', 'badge-threads',
  'perf-grid', 'xgb-grid', 'xgb-grid-title', 'features-grid', 'primaries-grid', 'voxels-grid',
  'group-m-model', 'm-model', 'm-model-caption', 'group-m-frame', 'm-frame', 'm-frame-caption', 'm-colormap',
  'e1-lo', 'e1-hi', 'e1-fill', 'e1-num-lo', 'e1-num-hi', 'e2-lo', 'e2-hi', 'e2-fill', 'e2-num-lo', 'e2-num-hi',
  'd-lo', 'd-hi', 'd-fill', 'd-num-lo', 'd-num-hi', 'e1-label', 'e1-hint', 'filter-logic', 'ctl-undefined-d',
  'opt-undefined-d', 'ctl-e1', 'ctl-e2', 'ctl-d', 'page-tabs',
];

/**
 * Land a Methodology badge's link: the card scrolled into view (which starts
 * its lazy load), its Details drawer open with the way back to the article, or
 * the reason on the kind banner when this experiment does not show the card.
 * Without an open experiment there is nothing to land on, and the banner
 * already says why.
 */
function landDeepLink(link) {
  if (!activeExperiment) return;
  const back = returnLink(link);
  if (link.panel && back) shell.setReturnLink(link.panel, back);
  const result = revealPanel(link.panel ?? '', { shell });
  if (result.ok) return;
  const title = result.card?.querySelector('.title')?.textContent?.trim() ?? '';
  const notice = revealNotice(result, { requested: link.requested, title, kind: plan.kindLabel });
  kindBanner.show([...kindBanner.shown, notice]);
}

async function boot() {
  // Read before anything writes the hash, which drops the query.
  const deepLink = readDeepLink(location.search);
  const missing = missingIds(MODELS_REQUIRED_IDS);
  if (missing.length) {
    console.error('[calosrv] missing element ids:', missing);
    banner.show([
      `The page and its scripts are out of step — ${missing.length} expected `
      + `element(s) are missing (${missing.slice(0, 4).join(', ')}`
      + `${missing.length > 4 ? ', …' : ''}). Reload with cache disabled `
      + '(Ctrl+Shift+R). The page will continue with those readouts blank.',
    ], true);
  }
  try {
    restoreControlsFromState();
  } catch (error) {
    reportError(error, 'restoring controls');
  }
  // The 3-D views first, then the export menus - which wire every
  // `[data-export]` on the page once, the 3-D section's projections included.
  voxels = await mountVoxels();
  attachExportMenus({
    state,
    onError: (message) => banner.show([message], true),
    resolve: (panelId) => {
      const target = models.exportTarget(panelId);
      if (target !== undefined) return target;
      // The 3-D cards never export; their paired 2-D projections do.
      return voxels?.exportTarget?.(panelId) ?? null;
    },
  });
  try {
    await loadCatalogue();
  } catch (error) {
    reportError(error, 'loading experiments');
  }
  if (deepLink) {
    history.replaceState(null, '', location.pathname + location.hash);
    landDeepLink(deepLink);
  }
}

// The page tabs and the Admin Settings link carry the view across.
wirePageTabs();

// A failure anywhere above must not leave a blank page with a silent console.
window.addEventListener('error', (event) => {
  console.error('[calosrv] uncaught', event.error || event.message);
});
window.addEventListener('unhandledrejection', (event) => {
  console.error('[calosrv] unhandled rejection', event.reason);
});

boot();
