/* Application bootstrap and control wiring.
 *
 * What the page shows is decided per experiment from its capability block
 * (capabilities.js `page1Plan`): the 2 x 2 diagnostic for an experiment with
 * hits, a notice in its place for the event-level aggregate; plot 4 as the
 * separation-sliced energy reconstruction where networks exist, as the
 * momentum-sliced response grid (B3) for a single shower; the physics cards
 * below (physics_section.js) the experiment can serve, each shut card with
 * the server's reason; the filter axes it has (controls/filter_block.js); and
 * the missing-predictions banner where it has no networks (CLAUDE.md
 * section 3). Switching experiment clears every picture of the previous one
 * first, so a failed load never leaves another experiment's data on screen,
 * and every loader drops a response that lands after the switch, so a late
 * one never draws the previous experiment's data under the new one's name.
 */

import { getJson, debounce, DEBOUNCE_MS, isAbort, abortRequest } from './api.js';
import { State, isCoregistered } from './state.js';
import { UploadForm } from './controls/upload.js';
import { AdminModal } from './controls/admin.js';
import { FilterBlock } from './controls/filter_block.js';
import { ProjectionPanel } from './panels/projection.js';
import { FrameGrid, GRID_ROWS, GRID_COLS } from './panels/frame_grid.js';
import { EventInspector } from './event_inspector.js';
import { depthIsometric, ensembleCellOptions } from './event_cells.js';
import { EnergyPanel } from './panels/energy.js';
import { MetricsPanel } from './panels/metrics.js';
import { formatInt, formatNumber, formatSci, isDiverging } from './scale.js';
import { setText, setHtml, setHidden, setVal, setChecked, missingIds } from './dom.js';
import { attachExportMenus } from './export/menu.js';
import {
  frameView, kindOf, panelTitle, displayCaption, channelCaption, entryTag, showerTag,
  anchorExplainer, frameCaption, pct, frameNotices,
} from './frame_views.js';
import { frameLabel, viewOf, enteringSub, offeredFrames as offeredFramesOf } from './labels.js';
import {
  projectionNotes, energyNotes, eventNotes, notesText, warningsNotShown, DENSITY_EXPLAINER,
} from './panel_notes.js';
import { Shell } from './shell.js';
import { page1Plan, carriedFrame } from './capabilities.js';
import {
  Banner, describeError, escapeHtml, fillComputeBadges, fillExperimentSelect, chooseExperiment,
  relabel, restoreLabel, relabelChoice, choiceTitle, writeSparseNote, wirePageTabs,
  readDeepLink, returnLink, revealPanel, revealNotice,
} from './page_common.js';
import {
  PhysicsSection, cardRequest, cardOptions, physicsNotes, exportMeta as physicsExportMeta,
} from './physics_section.js';

const state = new State();

/* The two side panels: the collapsible sidebar and the Details drawer.
 * Constructed before the charts, so a sidebar stored as collapsed is already
 * collapsed when the panels first measure their containers. */
const shell = new Shell({
  // The store first; a panel inspected before its first payload builds then.
  getNotes: (panelId) => panelNotes[panelId] ?? buildNotes(panelId),
  onLayoutChange: () => relayoutAll(),
});

const panels = {
  // The XY panel is locked to a 1:1 metric aspect so the separation vector D
  // can be measured off the picture. The depth panels span 5200 mm transverse
  // against 1210 mm of depth, where enforcing 1:1 would leave an unusable
  // sliver, so they fill the card and carry their true extents on the axes.
  xy: new ProjectionPanel('plot-xy', { isometric: true }),
  yz: new ProjectionPanel('plot-yz'),
  xz: new ProjectionPanel('plot-xz'),
};

/* A co-registered depth panel decides its 1:1 aspect from the card size
 * (`depthIsometric`), so a container resize must re-decide it before the
 * panel rebuilds its letterbox - and the panel's notes, which state the
 * aspect, must follow. The panel calls this from its ResizeObserver. */
for (const id of ['yz', 'xz']) {
  panels[id].onRelayout = (panel) => {
    if (kindOf(lastProjections) === 'lab' || !panel.payload) return;
    const next = depthIsometric(panel, panel.payload);
    if (next === panel.isometric) return;
    panel.isometric = next;
    writePanelNotes();
  };
}

/* The drawer's Selection line states the displayed window, so a zoom, a pan,
 * Auto-fit RoI or Reset rebuilds that panel's notes - once per frame during a
 * drag; the notes are text only. */
function notesOnViewChange(id) {
  let pending = 0;
  return () => {
    if (!pending) {
      pending = requestAnimationFrame(() => {
        pending = 0;
        buildNotes(id);
      });
    }
    // A depth panel of the absolute frame asks for the ensemble axis of the
    // events entering its new window, or drops it back at full extent.
    if (id === 'yz' || id === 'xz') requestWindowAxis(id);
  };
}
for (const id of ['xy', 'yz', 'xz']) panels[id].onViewChange = notesOnViewChange(id);

/* The two 3 x 3 grids shown in place of the ensemble grid: the Event
 * Inspector (one shower of one event in the original, translated and local
 * frames) and the compare-frames view (the selection in the Absolute,
 * per-shower translated and Local frames). Their cards exist from the start,
 * so the Details delegation and the export menus cover them; their charts are
 * created the first time each grid is shown. */
const eventGrid = new FrameGrid(document.getElementById('event-grid-rows'), {
  prefix: 'event',
  onPanelCreated: (id, panel) => { panel.onViewChange = notesOnViewChange(id); },
});
const compareGrid = new FrameGrid(document.getElementById('compare-grid-rows'), {
  prefix: 'compare',
  onPanelCreated: (id, panel) => {
    panel.onViewChange = notesOnViewChange(id);
    if (panel.gridCol === 'xy') return;
    // A co-registered depth panel re-decides its 1:1 aspect from its size,
    // exactly as the ensemble grid's depth panels do.
    panel.onRelayout = (p) => {
      const payload = comparePayloads[p.gridRow];
      if (!payload || kindOf(payload) === 'lab' || !p.payload) return;
      const next = depthIsometric(p, p.payload);
      if (next === p.isometric) return;
      p.isometric = next;
      buildNotes(id);
    };
  },
});
const energyPanel = new EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
const metricsPanel = new MetricsPanel('metrics', 'model-caption');

/* The page's two banners: transient messages (dismissal keyed by content),
 * and what the active experiment cannot show and why. */
const banner = new Banner();
const kindBanner = new Banner({ root: 'kind-banner', text: 'kind-banner-text', close: 'kind-banner-close' });

/* What the page shows for the active experiment (capabilities.js); before one
 * is adopted, the two-shower page with no physics cards. */
let pagePlan = page1Plan(null);

/* The physics cards below the 2 x 2 grid. Built now, before the export menus
 * are wired, so their Export buttons are wired with the static ones; each
 * card loads when it scrolls into view (.main is the scroll container). */
const physics = new PhysicsSection(document.getElementById('physics-grid'), {
  state,
  root: document.querySelector('.main'),
  getExperiment: () => activeExperiment,
  onRendered: (id, payload) => {
    buildNotes(id);
    // The event-level kind has no projections to count its selection: any
    // card's response that states the count (B1-B3 do) keeps it current.
    if (!pagePlan.spatial && Number.isFinite(payload?.n_events)) setText('stat-events', formatInt(payload.n_events));
  },
  onError: (error, context) => reportError(error, context),
  onOpenAdmin: () => adminModal?.open(),
});

/* Plot 4 of a single-shower experiment: the momentum-sliced response grid
 * (B3), drawn by the physics section's ResponseGridPanel on its own host in
 * the fourth card, created the first time it is needed. It always draws the
 * calibration notebook's six windows, which fit the 2 x 2 cell; the 1 GeV
 * bins are the full-width response card's below, which grows to fit every
 * slice, and plot 4's link scrolls there (Martin's Phase 6 decision). */
let plot4Grid = null;
let lastPlot4 = null;
const PLOT4_CONTROLS = Object.freeze({ b3Slices: 'notebook' });

/* Every view of one experiment is drawn under this generation. Taking the
 * views down for another experiment bumps it, so a response that arrives
 * afterwards - its request already past the point an abort reaches, since
 * getJson lets go of a request once its headers are in - is dropped instead
 * of drawing the previous experiment's data under the new one's name. */
let viewGeneration = 0;

/** A response for a view that was taken down: dropped, like a superseded request. */
function superseded() {
  const error = new Error('Superseded by an experiment switch.');
  error.name = 'AbortError';
  return error;
}

/** Throw `superseded()` when the views were taken down since `generation`. */
function checkCurrent(generation) {
  if (generation !== viewGeneration) throw superseded();
}

const dom = {
  experiment: document.getElementById('experiment-select'),
  energySparse: document.getElementById('energy-sparse'),
  infoDots: {
    resolution: document.getElementById('info-resolution'),
    separation: document.getElementById('info-separation'),
    density: document.getElementById('info-density'),
    frame: document.getElementById('info-frame'),
    event: document.getElementById('info-event'),
    anchor: document.getElementById('info-anchor'),
  },
  frameCaption: document.getElementById('frame-caption'),
  rhoNormControl: document.getElementById('ctl-rho-norm'),
  lockScaleControl: document.getElementById('ctl-lock-scale'),
  badgeMemory: document.getElementById('badge-memory'),
  badgeThreads: document.getElementById('badge-threads'),
  badgeExact: document.getElementById('badge-exact'),
  exactBadge: document.getElementById('exact-badge'),
  statEvents: document.getElementById('stat-events'),
  statHits: document.getElementById('stat-hits'),
  statEdep: document.getElementById('stat-edep'),
  statD: document.getElementById('stat-d'),
  statNoD: document.getElementById('stat-nod'),
  statLatency: document.getElementById('stat-latency'),
  statCache: document.getElementById('stat-cache'),
  tagXy: document.getElementById('tag-xy'),
  tagEnergy: document.getElementById('tag-energy'),
  displayCaption: document.getElementById('display-caption'),
  channelCaption: document.getElementById('channel-caption'),
  resolutionControl: document.getElementById('ctl-resolution'),
  resolution: document.getElementById('resolution'),
  resolutionReadout: document.getElementById('resolution-readout'),
  resolutionHint: document.getElementById('resolution-hint'),
  colormap: document.getElementById('colormap'),
  lockScale: document.getElementById('opt-lock-scale'),
  compare: document.getElementById('opt-compare'),
};

let experiments = [];
let activeExperiment = null;
let lastProjections = null;
let lastEnergy = null;
let showerFilter = 'both';
/* The compare-frames view's three responses, by frame kind. */
const comparePayloads = { lab: null, trans: null, local: null };

/* The windowed ensemble axis of the absolute frame's depth panels
 * (query/window_axis.py): asked for whenever a depth panel is zoomed to a
 * transverse window narrower than the detector, debounced like the sliders,
 * and dropped at full extent. The response replaces one overlay of the
 * panel's retained options, so the zoom that asked for it is kept. */
const windowAxisRequests = {
  yz: debounce(() => loadWindowAxis('yz'), DEBOUNCE_MS),
  xz: debounce(() => loadWindowAxis('xz'), DEBOUNCE_MS),
};

/** The transverse window a depth panel shows, or null at full extent. */
function windowOf(panel) {
  const view = panel?.view;
  if (!view || !panel.payload || panel.payload.axes.col.name !== 'z') return null;
  return { t_min: view.row[0], t_max: view.row[1] };
}

/** Ask for a depth panel's windowed axis, or drop it when the panel is back at full extent. */
function requestWindowAxis(id) {
  const panel = panels[id];
  if (!panel || !panel.payload) return;
  if (kindOf(lastProjections) !== 'lab' || !windowOf(panel)) {
    windowAxisRequests[id]?.cancel();
    if (panel.lastOpts?.windowAxis) {
      panel.setOverlay('windowAxis', null);
      buildNotes(id);
    }
    return;
  }
  windowAxisRequests[id]();
}

async function loadWindowAxis(id) {
  const panel = panels[id];
  const asked = windowOf(panel);
  if (!asked || kindOf(lastProjections) !== 'lab') return;
  const generation = viewGeneration;
  try {
    const payload = await getJson('/api/window-axis', {
      ...state.filterParams(), panel: id, t_min: asked.t_min, t_max: asked.t_max,
    }, `window-axis-${id}`);
    checkCurrent(generation);
    // The window may have moved on while the request was in flight.
    const now = windowOf(panel);
    if (!now || now.t_min !== asked.t_min || now.t_max !== asked.t_max) return;
    panel.setOverlay('windowAxis', payload);
    buildNotes(id);
  } catch (error) {
    if (error?.name !== 'AbortError') reportError(error, `windowed axis (${id})`);
  }
}
/* The frame keys the active experiment serves (labels.js `offeredFrames`). */
let offeredFrames = offeredFramesOf(null);
/* Warnings the projections, performance, event and comparison endpoints sent
 * with their last responses, merged into one banner. */
const endpointWarnings = { projections: [], performance: [], event: [], compare: [], plot4: [] };

/* The Event Inspector's controller: the sidebar picker, the pinned event and
 * the nine panels of the event grid. */
const inspector = new EventInspector({
  state,
  grid: eventGrid,
  palette: () => state.get('palette'),
  onRendered: (payload) => {
    for (const id of eventGrid.ids()) buildNotes(id);
    setNotices('event', payload.meta?.notices || []);
    endpointWarnings.event = payload.meta?.warnings || [];
    showBanner(mergedWarnings());
  },
  onError: (error, context) => reportError(error, context),
  onViewMode: () => applyViewMode(),
});

/* ------------------------------------------------------------------ filters */

/* The E1, E2 and D sliders and the undefined-D option, adopted per experiment:
 * a single shower filters on its incident momentum p alone. Dragging asks for
 * the sampled preview, a release for the exact refresh. */
const filters = new FilterBlock({
  state,
  onPreview: () => requestPreview(),
  onCommit: () => refreshAll(),
});

/* ------------------------------------------------------------------ loading */

function setBusy(busy) {
  for (const panel of Object.values(panels)) panel.setBusy(busy);
  energyPanel.setBusy(busy);
  plot4Grid?.setBusy?.(busy);
  eventGrid.setBusy(busy);
  compareGrid.setBusy(busy);
}

/* Transient messages on the banner (page_common.js Banner): dismissal is keyed
 * by content, so a warning re-sent on every response during a drag stays
 * dismissed. */
function showBanner(messages, isError = false) {
  banner.show(messages, isError);
}

/**
 * Attach a set of notices to a sidebar info dot.
 *
 * Persistent, control-scoped explanations live here rather than in the banner.
 * A notice that is re-sent on every response is not meaningfully dismissible,
 * and stacking two or three of them across the top was costing the plots about
 * a sixth of their height.
 */
function setNotices(scope, notices) {
  const dot = dom.infoDots[scope];
  if (!dot) return;
  const texts = notices.filter((n) => n.scope === scope).map((n) => n.text);
  dot.hidden = texts.length === 0;
  dot.dataset.notices = JSON.stringify(texts);
}

function showPopover(anchor, texts, { neutral = false } = {}) {
  hidePopover();
  if (!texts.length) return;
  const node = document.createElement('div');
  node.className = `popover${neutral ? ' is-neutral' : ''}`;
  node.innerHTML = texts.length === 1
    ? escapeHtml(texts[0])
    : `<ul>${texts.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>`;
  document.body.appendChild(node);

  const box = anchor.getBoundingClientRect();
  node.style.top = `${Math.min(window.innerHeight - node.offsetHeight - 8, box.bottom + 6)}px`;
  node.style.left = `${Math.min(window.innerWidth - node.offsetWidth - 8, box.left)}px`;
  activePopover = node;
}

function hidePopover() {
  if (!activePopover) return;
  const hadFocus = activePopover.contains(document.activeElement);
  activePopover.remove();
  activePopover = null;
  // An explainer took the focus when it opened; give it back to its button.
  if (popoverTrigger) {
    popoverTrigger.setAttribute('aria-expanded', 'false');
    if (hadFocus && popoverTrigger.isConnected) popoverTrigger.focus();
    popoverTrigger = null;
  }
}

/**
 * A popover holding a methodology explainer (`frame_views.js`): a title,
 * then sections of paragraphs and formulas, the one in use tagged.
 *
 * Text nodes only. Unlike a notice popover it is long, so it scrolls when
 * taller than the window, a click inside it (on its scrollbar, or to select a
 * formula) does not close it, and it takes the focus so a keyboard or
 * screen-reader user lands in it; Escape or a click elsewhere closes it and
 * returns the focus to its button.
 */
function showExplainer(trigger, explainer) {
  hidePopover();
  const node = document.createElement('div');
  node.className = 'popover is-neutral is-explainer';
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-label', explainer.title);
  node.tabIndex = -1;
  const title = document.createElement('h3');
  title.textContent = explainer.title;
  node.append(title);
  for (const section of explainer.sections) {
    const heading = document.createElement('h4');
    heading.textContent = section.heading;
    if (section.current) {
      const tag = document.createElement('span');
      tag.className = 'in-use';
      tag.textContent = 'in use';
      heading.append(' ', tag);
    }
    node.append(heading);
    for (const block of section.blocks) {
      const element = document.createElement('p');
      if (block.kind === 'formula') element.className = 'formula';
      element.textContent = block.text;
      node.append(element);
    }
  }
  node.addEventListener('click', (event) => event.stopPropagation());
  document.body.appendChild(node);

  // Beside the sidebar, level with its button: the control it explains stays
  // in view, and so does the button, however near the window's foot it sits.
  const box = trigger.getBoundingClientRect();
  const sidebar = trigger.closest('.sidebar')?.getBoundingClientRect();
  const left = sidebar ? sidebar.right + 10 : box.left;
  node.style.top = `${Math.max(8, Math.min(window.innerHeight - node.offsetHeight - 8, box.top - 12))}px`;
  node.style.left = `${Math.max(8, Math.min(window.innerWidth - node.offsetWidth - 8, left))}px`;
  activePopover = node;
  popoverTrigger = trigger;
  trigger.setAttribute('aria-expanded', 'true');
  node.focus({ preventScroll: true });
}

let activePopover = null;
/* The button an explainer popover was opened from, while it is open. */
let popoverTrigger = null;

/* -------------------------------------------------------------- projections */

/**
 * The options one spatial panel of a projections payload renders with - the
 * ensemble grid's and the compare-frames view's cells alike (event_cells.js
 * `ensembleCellOptions`, shared with the Models page's projections).
 *
 * The entry panel carries the centroids and, in the absolute frame, the
 * separation vector; the depth panels carry the measured shower axes (lab)
 * and the individual incident trajectories when few enough events are
 * selected to read (lab, and from the origin in the translated frame). In
 * the canonical frame both give way to the two ensemble axes; the local frame
 * draws no direction. Whether a depth panel keeps a 1:1 aspect is
 * `depthIsometric`, from the same module.
 */
function panelOptions(payload, id) {
  return ensembleCellOptions(payload, id, state.get('palette'), state.get('weighting'));
}

/** Draw the three spatial panels from a projections payload. */
function renderPanels(payload) {
  const coregistered = kindOf(payload) !== 'lab';
  panels.xy.isometric = true;
  panels.xy.render(payload.panels.xy, panelOptions(payload, 'xy'));
  for (const id of ['yz', 'xz']) {
    const panel = panels[id];
    panel.isometric = coregistered && depthIsometric(panel, payload.panels[id]);
    // A zoomed absolute-frame depth panel keeps its windowed axis across the
    // redraw and asks for a fresh one for the new selection.
    const windowAxis = coregistered ? null : (panel.lastOpts?.windowAxis ?? null);
    panel.render(payload.panels[id], { ...panelOptions(payload, id), windowAxis });
    requestWindowAxis(id);
  }
}

/* ------------------------------------------------------ compare frames */

/** The row title of one frame in the compare-frames view. */
function compareRowTitle(kind, payload) {
  const sym = frameView(kind).symbols;
  const n = payload?.selection?.n_events;
  return `${frameLabel(kind, pagePlan.nShowers)} (${sym.x}, ${sym.y}, ${sym.z})`
    + (Number.isFinite(n) ? ` · ${formatInt(n)} event${n === 1 ? '' : 's'}` : '');
}

/**
 * Fetch the selection in every frame the experiment serves - Absolute,
 * per-shower translated, Local - and draw them as the rows of the compare
 * grid. Each frame is asked for in the display mode it keeps for itself, so
 * every row is exactly what that frame shows on its own.
 */
async function loadCompare() {
  const generation = viewGeneration;
  const kinds = GRID_ROWS.filter((kind) => offeredFrames.includes(kind));
  const results = await Promise.all(kinds.map((kind) => getJson(
    '/api/projections', state.projectionParams(false, kind), `compare-${kind}`,
  )));
  checkCurrent(generation);
  for (const kind of GRID_ROWS) comparePayloads[kind] = null;
  kinds.forEach((kind, index) => { comparePayloads[kind] = results[index]; });
  endpointWarnings.compare = results.flatMap((payload) => payload.meta?.warnings || []);
  renderCompare();
  return results;
}

/** Draw the compare grid from the responses in hand, and rebuild its notes. */
function renderCompare() {
  const rows = {};
  const modes = [];
  for (const kind of GRID_ROWS) {
    const payload = comparePayloads[kind];
    if (!payload) continue;
    const frameKind = kindOf(payload);
    const cells = {};
    for (const col of GRID_COLS) {
      const panel = compareGrid.panel(kind, col);
      cells[col] = {
        title: panelTitle(col, frameKind, pagePlan.nShowers),
        payload: payload.panels[col],
        opts: panelOptions(payload, col),
        isometric: col === 'xy' || (frameKind !== 'lab' && panel
          ? depthIsometric(panel, payload.panels[col]) : false),
      };
    }
    rows[kind] = { title: compareRowTitle(kind, payload), cells };
    const mode = payload.meta?.resolution?.mode === 'native' ? 'native' : 'Continuous Field';
    modes.push(`${frameLabel(kind, pagePlan.nShowers)}: ${mode}`);
  }
  const missing = GRID_ROWS.filter((kind) => !comparePayloads[kind]).map((kind) => frameLabel(kind, pagePlan.nShowers));
  compareGrid.show(true);
  compareGrid.render(rows);
  setText('compare-grid-label', `${modes.join(' · ')}`
    + (missing.length ? ` · not served by this experiment: ${missing.join(', ')}` : '')
    + '. Each row is that frame\'s own response, with its own window, ramp and disclosures.');
  for (const id of compareGrid.ids()) buildNotes(id);
}

/** Refresh the compare grid alone, when its toggle is switched on. */
async function refreshCompare() {
  compareGrid.setBusy(true);
  try {
    await loadCompare();
    showBanner(mergedWarnings());
  } catch (error) {
    if (error?.name !== 'AbortError') reportError(error, 'frame comparison');
  } finally {
    compareGrid.setBusy(false);
  }
}

/**
 * Show whichever grid the view state asks for: the Event Inspector while an
 * event is pinned, else the compare-frames grid while its toggle is on, else
 * the ensemble grid. The grid tracks snap, so one call is one layout.
 */
function applyViewMode() {
  const pinned = state.get('event') !== null && pagePlan.eventInspector;
  const compare = !pinned && state.get('compare') && pagePlan.compare;
  setHidden('ensemble-grid', pinned || compare || !pagePlan.spatial);
  // An experiment without hits shows why, in place of the 2 x 2 grid.
  setHidden('kind-notice', pinned || compare || pagePlan.spatial);
  // The physics cards belong to the ensemble view: hidden with the 2 x 2.
  setHidden('physics-grid', pinned || compare || !pagePlan.physics.length);
  eventGrid.show(pinned);
  compareGrid.show(compare);
  inspector.syncControls();
  setChecked('opt-compare', state.get('compare'));
  relayoutAll();
}

/* ------------------------------------------------------------ panel notes */

/* What the Details drawer says about each panel - methodology and
 * disclosures - built from the payloads by panel_notes.js and never read off
 * the page. The store is what the drawer shows and what the banner
 * de-duplicates against. */
const panelNotes = { xy: null, yz: null, xz: null, energy: null };
for (const id of physics.ids()) panelNotes[id] = null;

/** Rebuild one panel's notes, flag its Details button and refresh the drawer. */
function buildNotes(panelId) {
  let notes = null;
  if (panelId === 'energy' && pagePlan.plot4 === 'response-b3') {
    // Plot 4 of a single shower is the response grid: its notes are B3's.
    notes = lastPlot4 ? physicsNotes('response-b3', lastPlot4, {
      state,
      experiment: activeExperiment,
      opts: plot4Grid?.lastOpts ?? {},
      title: pagePlan.plot4Title,
    }) : null;
  } else if (panelId === 'energy') {
    notes = lastEnergy ? energyNotes({
      payload: lastEnergy,
      notices: energyPanel.lastNotices,
      selection: lastProjections?.selection ?? null,
      state,
      experiment: activeExperiment,
    }) : null;
  } else if (panelId.startsWith('event-')) {
    // One cell of the Event Inspector: `event-<frame>-<panel>`.
    const [, kind, col] = panelId.split('-');
    const panel = eventGrid.panelById(panelId);
    notes = inspector.payload ? eventNotes({
      payload: inspector.payload,
      kind,
      panelId: col,
      view: panel?.currentView() ?? null,
      state,
      experiment: activeExperiment,
    }) : null;
  } else if (panelId.startsWith('compare-')) {
    // One cell of the compare-frames view: that frame's own projections
    // payload, so its notes are exactly the ensemble panel's in that frame.
    const [, kind, col] = panelId.split('-');
    const payload = comparePayloads[kind];
    const panel = compareGrid.panelById(panelId);
    notes = payload && panel ? projectionNotes({
      payload,
      panelId: col,
      isometric: { [col]: col === 'xy' ? true : panel.isometric },
      view: panel.currentView(),
      state,
      experiment: activeExperiment,
    }) : null;
  } else if (physics.has(panelId)) {
    notes = physics.notes(panelId, { state, experiment: activeExperiment });
  } else if (lastProjections && panels[panelId]) {
    notes = projectionNotes({
      payload: lastProjections,
      panelId,
      isometric: { xy: true, yz: panels.yz.isometric, xz: panels.xz.isometric },
      view: panels[panelId].currentView(),
      windowAxis: panelId === 'xy' ? null : (panels[panelId].lastOpts?.windowAxis ?? null),
      state,
      experiment: activeExperiment,
    });
  }
  panelNotes[panelId] = notes;
  markDetails(panelId, notes);
  shell.refresh(panelId, notes);
  return notes;
}

/** The three spatial panels' notes, from the payload and the panels' current aspect. */
function writePanelNotes() {
  for (const id of ['xy', 'yz', 'xz']) buildNotes(id);
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

/**
 * Re-lay every chart out at its container's current size.
 *
 * Called by the shell after the sidebar or the drawer toggles. The grid tracks
 * snap, so this measures the final geometry at once; each panel's own
 * ResizeObserver fires once more on the next frame and finds nothing to do.
 */
function relayoutAll() {
  for (const panel of Object.values(panels)) panel.relayout();
  energyPanel.relayout();
  plot4Grid?.relayout?.();
  // How many slices plot 4's fixed-height grid fits depends on its width.
  if (pagePlan.plot4 === 'response-b3' && lastPlot4) writeSparseNote(dom.energySparse, plot4Sparse());
  eventGrid.relayout();
  compareGrid.relayout();
  physics.relayout();
}

/** The entry panel's clipping count, kept on the status bar. */
function clippedReadout(payload) {
  const panel = payload?.panels?.xy;
  if (!panel) return '—';
  if (kindOf(payload) === 'lab') {
    const scale = panel.scale || {};
    const n = (scale.clipped_low || 0) + (scale.clipped_high || 0);
    return n > 0 ? `${formatInt(n)} cell${n === 1 ? '' : 's'}` : '—';
  }
  const n = panel.below_floor_cells;
  return Number.isFinite(n) && n > 0 ? `${formatInt(n)} bin${n === 1 ? '' : 's'} below floor` : '—';
}

/**
 * The status bar's C9 readout: the share of the selection's energy behind its
 * showers' entry plane, with its 95% interval, from the server's `all` split.
 */
function negativeReadout(block) {
  if (!block) return '—';
  if (block.available === false) return 'unavailable';
  const all = (block.splits || []).find((split) => split.key === 'all') ?? block.splits?.[0];
  const fraction = all?.energy_fraction;
  if (!Number.isFinite(fraction)) return '—';
  const ci = all.energy_fraction_ci95;
  const interval = Array.isArray(ci) && ci.every(Number.isFinite) ? ` [${pct(ci[0])}, ${pct(ci[1])}]` : '';
  return `${pct(fraction)}${interval} of energy`;
}

async function loadProjections(preview = false) {
  const generation = viewGeneration;
  const params = state.projectionParams(preview);
  const payload = await getJson('/api/projections', params, 'projections');
  checkCurrent(generation);
  lastProjections = payload;

  const kind = kindOf(payload);
  const coregistered = kind !== 'lab';
  renderPanels(payload);
  for (const id of ['xy', 'yz', 'xz']) setText(`title-${id}`, panelTitle(id, kind, pagePlan.nShowers));
  writePanelNotes();

  const selection = payload.selection;
  setText('stat-events', formatInt(selection.n_events));
  setText('stat-hits', formatInt(selection.n_hits));
  setText('stat-edep', `${formatSci(selection.e_dep_total, 3)} GeV`);
  // One shower per event has no separation: no D, and no undefined-D count.
  setText('stat-d', Number.isFinite(selection.d?.mean)
    ? `${formatNumber(selection.d.mean, 0)} mm` : '—');
  setText('stat-nod', Number.isFinite(selection.n_events_no_d) ? formatInt(selection.n_events_no_d) : '—');
  // The density reference is a co-registered frame's "autoscaled" badge: a ramp
  // relative to the selection's own peak looks identical for a tenth of the
  // energy, so the reader is told which reference the colours are drawn against.
  // An energy-weighted CAM panel is always relative to this selection's own
  // raw-grid peak of Σ E·CAM, whatever the density normalisation says, and a
  // mean-CAM panel has a fixed scale; the badge says which.
  const quantity = payload.panels?.xy?.scale?.quantity;
  let rhoBadge = '—';
  if (coregistered && (quantity === 'gradcam_energy' || quantity === 'shapcam_energy')) {
    rhoBadge = 'selection Σ E·CAM peak (autoscaled)';
  } else if (coregistered && (quantity === 'gradcam' || quantity === 'shapcam')) {
    rhoBadge = 'fixed scale';
  } else if (coregistered) {
    rhoBadge = payload.frame.rho?.norm === 'dataset' ? 'dataset peak' : 'selection peak (autoscaled)';
  }
  setText('stat-rho', rhoBadge);
  setText('stat-clipped', clippedReadout(payload));
  // C9: the Local frame states how much of the selection lies behind its
  // own entry plane (w < −10⁻⁶ mm); the full summary is the readout's title.
  const negative = kind === 'local' ? (payload.frame?.negative_w ?? null) : null;
  setHidden('stat-wneg-item', !negative);
  setText('stat-wneg', negativeReadout(negative));
  const negativeItem = document.getElementById('stat-wneg-item');
  if (negativeItem && negative?.summary) negativeItem.title = negative.summary;
  setText('stat-latency', `${formatNumber(payload.meta.total_ms, 1)} ms`);
  setText('stat-cache', payload.meta.cached ? 'cached' : 'scanned');

  const exact = payload.meta.exact;
  setText('badge-exact', exact ? 'Exact' : 'Preview (sampled)');
  dom.exactBadge.classList.toggle('is-warn', !exact);

  const resolution = payload.meta.resolution;
  // The co-registered frames ship the comb once, in frame.comb (review R-4).
  const stagger = payload.meta.stagger ?? payload.frame?.comb ?? {};
  setText('display-caption', displayCaption(kind, resolution, coregistered ? payload.frame : null));
  setText('channel-caption', currentChannelCaption(payload));

  const slabTag = `${payload.slab.layers} layers · ${payload.slab.mm.toFixed(0)} mm`;
  // The canonical tag carries the mean entry separation with its interval
  // named; a per-shower tag says how many showers are superimposed. `.sym`
  // keeps the tag's uppercase transform off the symbols.
  const extra = kind === 'canonical' ? entryTag(payload.frame)
    : coregistered ? showerTag(payload.frame, pagePlan.nShowers) : '';
  if (extra) setHtml('tag-xy', `${slabTag} · <span class="sym">${extra}</span>`);
  else setText('tag-xy', slabTag);

  // Persistent explanations go to the sidebar info dots; the banner keeps only
  // transient, actionable messages.
  const notices = frameNotices(payload);
  if (!coregistered && stagger.staggered && resolution.mode === 'native' && stagger.note) {
    notices.push({ scope: 'resolution', text: stagger.note });
  }
  setNotices('resolution', notices);
  setNotices('separation', notices);
  setNotices('frame', notices);
  // Held rather than shown, so `refreshAll` can decide between these and any
  // endpoint failure - a failure must not be overwritten by a routine warning
  // arriving from a panel that happened to succeed.
  endpointWarnings.projections = payload.meta.warnings || [];
  return payload;
}

/** The channel caption for the active controls, worded from `payload` when it matches. */
function currentChannelCaption(payload = lastProjections) {
  return channelCaption({
    channel: state.get('channel'),
    model: state.get('model'),
    frame: state.get('frame'),
    payload: kindOf(payload) === state.get('frame') ? payload : null,
    display: state.get('display'),
    weighting: state.get('weighting'),
    nShowers: pagePlan.nShowers,
  });
}

/** The lab hint names the active experiment's lattice; set on activation. */
let labResolutionHint = 'Available in Continuous Field mode.';

/**
 * Bring the display radios, their labels and the R control into line with the
 * active frame's display mode.
 *
 * Each frame keeps its own mode (see state.js), so switching frame can change
 * the checked radio without the user touching it. Called on boot and on every
 * frame change, through `applyControlAvailability`, and after a display change.
 */
function syncDisplayControls() {
  const view = frameView(state.get('frame'));
  const display = state.get('display');
  for (const input of document.querySelectorAll('input[name="display"]')) {
    input.checked = input.value === display;
  }
  setHtml('display-label-native', view.displayLabels.native);
  setHtml('display-label-continuous', view.displayLabels.continuous);
  dom.resolutionControl.classList.toggle('is-disabled', display !== 'continuous');
  setText('resolution-hint', view.resolutionHint ?? labResolutionHint);
}

/**
 * Bring the two-tier frame control into line with the stored frame key.
 *
 * The primary radio shows the view, the nested radio the sub-frame, and the
 * legacy per-shower option is revealed only while a link or a saved default
 * holds the frame on it. `data-frame` on the fieldset is the key the control
 * reflects, for anything that needs to read it back.
 */
function syncFrameControl() {
  const frame = state.get('frame');
  const { view, sub } = viewOf(frame);
  for (const input of document.querySelectorAll('input[name="frame-view"]')) {
    input.checked = input.value === view;
  }
  for (const input of document.querySelectorAll('input[name="frame-sub"]')) {
    input.checked = input.value === sub;
  }
  setHidden('frame-sub', view !== 'aligned');
  setHidden('frame-sub-trans', frame !== 'trans');
  // A single shower's per-shower translated frame is its own Translated
  // frame, offered beside Local rather than revealed only as a legacy link.
  if (pagePlan.frames.transPrimary) setHidden('frame-sub-trans', false);
  // The entry anchor is a choice of the D-frame alone.
  setHidden('anchor-sub', frame !== 'canonical');
  for (const input of document.querySelectorAll('input[name="anchor"]')) {
    input.checked = input.value === state.get('anchor');
  }
  const control = document.getElementById('ctl-frame');
  if (control) control.dataset.frame = frame;
  setText('frame-caption', frameCaption(frame, pagePlan.nShowers));
}

/** Switch the reference frame and refresh everything that depends on it. */
function changeFrame(frame) {
  state.set({ frame });
  // Also resyncs the display radios: each frame returns to its own mode.
  applyControlAvailability();
  setText('channel-caption', currentChannelCaption());
  refreshAll();
}

/**
 * Show, hide and disable the controls the active frame and channel make
 * meaningful.
 *
 * The density normalisation belongs to the co-registered frames; the lock
 * belongs to the absolute frame and to density; a signed channel is always
 * drawn on the diverging PuOr, so the sequential colour map is disabled and
 * says why.
 */
function applyControlAvailability() {
  const frame = state.get('frame');
  const channel = state.get('channel');
  const coregistered = isCoregistered(frame);
  setHidden('ctl-rho-norm', !coregistered);
  setHidden('ctl-lock-scale', coregistered);
  dom.lockScaleControl?.classList.toggle('is-disabled', channel !== 'density');
  const signed = isDiverging({ diverging: channel.startsWith('shapcam') });
  dom.colormap.disabled = signed;
  setHidden('colormap-hint', !signed);
  setText('colormap-hint', signed
    ? 'Shap-CAM is signed: it is always drawn on the diverging ColorBrewer PuOr, orange for '
      + 'negative and purple for positive attribution. The sequential map applies to the other channels.'
    : '');
  syncFrameControl();
  syncDisplayControls();
}

/**
 * Grey out every frame, channel and model the active experiment does not
 * serve (from `/api/experiments`), and fall back from one a link asked for.
 *
 * A greyed frame carries the server's reason as its title; a single-shower
 * experiment's frame tier is relabelled (Shower-Aligned, with its per-shower
 * Translated frame) at runtime, the markup keeping the two-shower labels.
 * A frame the experiment does not serve falls back to Absolute. Returns the
 * one-line notices of every fallback, for the kind banner.
 */
function applyCapabilities(experiment) {
  offeredFrames = offeredFramesOf(experiment);
  const plan = pagePlan;
  const offered = {
    channel: plan.channels,
    model: plan.models,
  };
  const fallbacks = [];

  // The two-tier frame control: a sub-frame the experiment does not serve is
  // greyed, and Separation-Aligned itself when none of its sub-frames is.
  for (const input of document.querySelectorAll('input[name="frame-sub"]')) {
    const ok = offeredFrames.includes(input.value);
    input.disabled = !ok;
    input.closest('.choice')?.classList.toggle('is-disabled', !ok);
    relabelChoice(input, plan.frames.labels?.[input.value] ?? null);
    choiceTitle(input, ok ? null : (plan.frames.disabled[input.value] ?? null));
  }
  for (const input of document.querySelectorAll('input[name="frame-view"]')) {
    const ok = input.value === 'aligned'
      ? enteringSub(offeredFrames) !== null
      : offeredFrames.includes('lab');
    input.disabled = !ok;
    input.closest('.choice')?.classList.toggle('is-disabled', !ok);
    relabelChoice(input, input.value === 'aligned' ? (plan.frames.labels?.aligned ?? null) : null);
    const shut = plan.frames.disabled;
    const reason = input.value === 'aligned' ? (shut.local ?? shut.canonical ?? shut.trans) : shut.lab;
    choiceTitle(input, ok ? null : (reason ?? null));
  }
  if (!offeredFrames.includes(state.get('frame')) && offeredFrames.length) {
    const fallback = offeredFrames.includes('lab') ? 'lab' : offeredFrames[0];
    fallbacks.push(`${frameLabel(state.get('frame'))} is not available for this experiment; `
      + `showing ${frameLabel(fallback, plan.nShowers)} instead.`);
    state.set({ frame: fallback }, { silent: true });
  }
  syncFrameControl();

  for (const [name, values] of Object.entries(offered)) {
    for (const input of document.querySelectorAll(`input[name="${name}"]`)) {
      const ok = values.includes(input.value);
      input.disabled = !ok;
      input.closest('.choice')?.classList.toggle('is-disabled', !ok);
    }
    if (!values.includes(state.get(name)) && values.length) {
      fallbacks.push(`${name} "${state.get(name)}" is not available for this experiment; `
        + `showing "${values[0]}" instead.`);
      state.set({ [name]: values[0] }, { silent: true });
    }
  }
  // Held in the kind banner, which stays until the experiment changes: the
  // transient banner is rewritten by the refresh that follows at once.
  if (fallbacks.length) restoreControlsFromState();
  return fallbacks;
}

/* The sidebar groups that steer only the spatial panels: the frame tier
 * (with the compare-frames toggle under it), the display resolution, the
 * channels and the colour map. Hidden for an experiment with no hits to
 * project (Martin's Phase 6 decision); its kind notice says why. */
const SPATIAL_GROUPS = ['group-frame', 'group-resolution', 'group-channel', 'group-colormap'];

/**
 * The parts of the page the experiment's kind decides: plot 4, the status
 * readouts, the Event Inspector and compare controls, the model cards, the
 * sidebar groups and the banner that says what is missing - with `notices`,
 * the one-line fallbacks of the activation, under it.
 */
function applyKindPlan(plan, notices = []) {
  // Plot 4: the energy reconstruction, or a single shower's response grid,
  // each with its fitted μ and σ in the table below it.
  const grid = plan.plot4 === 'response-b3';
  setHidden('plot-energy', plan.plot4 !== 'energy-d');
  setHidden('plot-energy-b3', !grid);
  setHidden('fit-table', !plan.plot4);
  setHidden('energy-shower-toggle', plan.plot4 !== 'energy-d');
  // The grid's link to the full-width card holding the 1 GeV bins.
  setHidden('energy-b3-slices', !(grid && plan.physics.includes('response-b3') && !plan.disabled['response-b3']));
  const title = document.getElementById('title-energy');
  if (plan.plot4 && plan.plot4 !== 'energy-d') relabel(title, plan.plot4Title);
  else restoreLabel(title);
  if (plan.plot4 !== 'energy-d') {
    // The energy panel's notices belong to its own payload; a card with
    // nothing to draw says why instead.
    setText('energy-sparse', plan.plot4Reason ?? '');
    setHidden('energy-sparse', !plan.plot4Reason);
  }

  // No hits to project: the controls that steer only the projections go.
  for (const id of SPATIAL_GROUPS) setHidden(id, !plan.spatial);

  // A single shower has no separation to report.
  setHidden('stat-d-item', !plan.status.d);
  setHidden('stat-nod-item', !plan.status.d);
  if (!plan.spatial) setHidden('stat-wneg-item', true);

  // The Event Inspector and the compare view need hits; a single shower has
  // one shower to inspect, so the shower choice goes.
  const eventControl = document.getElementById('ctl-event');
  eventControl?.classList.toggle('is-disabled', !plan.eventInspector);
  if (eventControl) {
    if (plan.eventInspector) eventControl.removeAttribute('title');
    else eventControl.title = plan.reasons['event-inspector'] ?? 'Not available for this experiment.';
  }
  dom.compare.disabled = !plan.compare;
  const compareControl = document.getElementById('ctl-compare');
  compareControl?.classList.toggle('is-disabled', !plan.compare);
  choiceTitle(dom.compare, plan.compare ? null : (plan.reasons.compare ?? null));
  if (!plan.eventInspector && state.get('event') !== null) state.set({ event: null }, { silent: true });
  if (!plan.compare && state.get('compare')) state.set({ compare: false }, { silent: true });
  const twoShowers = plan.showers.includes('b');
  for (const input of document.querySelectorAll('input[name="event-shower"]')) {
    if (input.value === 'b') {
      const choice = input.closest('.choice');
      if (choice) choice.hidden = !twoShowers;
    } else {
      relabelChoice(input, twoShowers ? null : {
        label: 'Shower',
        detail: '(one per event)',
        title: "The event's one shower: its own entry point P₀ and rotation R(θ, φ).",
      });
    }
  }
  if (!twoShowers && state.get('shower') === 'b') state.set({ shower: 'a' }, { silent: true });

  // No networks: no model cards, and the banner CLAUDE.md section 3 asks for.
  if (!plan.performance) {
    metricsPanel.renderError('This experiment carries no reconstruction-network outputs.');
    setText('model-caption', 'No reconstruction networks in this experiment: the model choice has nothing to drive.');
  }
  kindBanner.show([plan.banner, plan.stale?.notice, ...notices].filter(Boolean));
  if (plan.notice) {
    setText('kind-notice-title', plan.notice.title);
    setText('kind-notice-text', plan.notice.text);
  }
}

async function loadEnergy() {
  const generation = viewGeneration;
  const payload = await getJson('/api/energy-distribution', state.energyParams(), 'energy');
  checkCurrent(generation);
  lastEnergy = payload;
  renderEnergy();
  setText('tag-energy', payload.calibration.applied ? 'calibrated' : 'deposited');
  return payload;
}

/** Draw the energy panel from the payload in hand, and rebuild its notes. */
function renderEnergy() {
  if (!lastEnergy) return;
  energyPanel.render(lastEnergy, {
    palette: state.get('palette'), kind: 'pred', shower: showerFilter,
  });
  buildNotes('energy');
}

/** Plot 4 of a single shower: the response grid, B3, on its own host, on the notebook's windows. */
async function loadPlot4Grid() {
  const generation = viewGeneration;
  const request = cardRequest('response-b3', {
    filters: state.filterParams(), controls: PLOT4_CONTROLS, plan: pagePlan,
  });
  if (!request) return null;
  if (!plot4Grid) {
    // The 2 x 2 card has a fixed height: the grid fits it rather than growing the card.
    // A resize that changes how many slices fit - one only the panel's own
    // ResizeObserver sees - rewrites the card's sparse note with it.
    plot4Grid = await physics.createPanel('ResponseGridPanel', document.getElementById('plot-energy-b3'), {
      autoHeight: false,
      onLayout: () => {
        if (pagePlan.plot4 === 'response-b3' && lastPlot4) writeSparseNote(dom.energySparse, plot4Sparse());
      },
    });
  }
  // Plot 4 is one request at a time, whichever panel draws it.
  const payload = await getJson(request.route, request.params, 'energy');
  checkCurrent(generation);
  lastPlot4 = payload;
  endpointWarnings.plot4 = payload.meta?.warnings || [];
  renderPlot4();
  setText('tag-energy', payload.calibration?.applied ? 'calibrated' : 'deposited');
  return payload;
}

/**
 * Draw plot 4's response grid from the payload in hand, with its fitted μ
 * and σ in the card's table and its key counts - low-N series, clipped
 * curves, values beyond a slice axis, slices that did not fit - in the
 * card's sparse note, as the energy panel does; then rebuild its notes.
 */
function renderPlot4() {
  if (!lastPlot4 || !plot4Grid || pagePlan.plot4 !== 'response-b3') return;
  plot4Grid.render(lastPlot4, cardOptions('response-b3', {
    controls: PLOT4_CONTROLS, palette: state.get('palette'), plan: pagePlan, payload: lastPlot4,
  }));
  const table = document.getElementById('fit-table');
  if (table && typeof plot4Grid.renderTable === 'function') plot4Grid.renderTable(table);
  writeSparseNote(dom.energySparse, plot4Sparse());
  buildNotes('energy');
}

/** Plot 4's response grid's key counts for the card's sparse note; [] without one. */
function plot4Sparse() {
  return plot4Grid && lastPlot4 && typeof plot4Grid.sparseLines === 'function' ? plot4Grid.sparseLines() : [];
}

async function loadPerformance() {
  const generation = viewGeneration;
  const payload = await getJson('/api/model-performance', state.performanceParams(), 'performance');
  checkCurrent(generation);
  metricsPanel.render(payload, payload.meta.total_ms);
  // The first performance warning is shown in the model caption; the rest
  // join the banner.
  endpointWarnings.performance = (payload.meta?.warnings || []).slice(1);
  return payload;
}

/**
 * The union of every endpoint's warnings, without duplicates and without any
 * text the reader can already see: the two captions, the energy card's
 * notices and the notes of the panel whose drawer is open. A closed drawer
 * does not count - a warning is dropped only because it is visible.
 */
function mergedWarnings() {
  const shown = [
    ...['display-caption', 'channel-caption'].map((id) => document.getElementById(id)?.textContent || ''),
    ...(energyPanel.lastNotices || []),
    shell.inspected ? notesText(panelNotes[shell.inspected]) : '',
    // Plot 4's response grid states its own warnings in its drawer and its sparse note.
    pagePlan.plot4 === 'response-b3' ? notesText(panelNotes.energy) : '',
    pagePlan.plot4 === 'response-b3' ? plot4Sparse().join(' ') : '',
  ].join(' ');
  return warningsNotShown([
    ...endpointWarnings.projections, ...endpointWarnings.performance,
    ...endpointWarnings.event, ...endpointWarnings.compare,
    ...endpointWarnings.plot4, ...physics.warnings(),
  ], shown);
}

/**
 * The event-level kind's Events count. It has no projections response to
 * count its selection; /api/response states the selection's event count
 * (`n_events`), read through the physics section's shared request, so the
 * status bar is current whether or not a response card is in view and the
 * cards that read it cost no second request. A failure is the cards' to
 * report; the readout says '—'.
 */
async function loadEventCount() {
  const generation = viewGeneration;
  let payload = null;
  try {
    payload = await physics.payloadOf('response-b1');
  } catch (error) {
    if (isAbort(error)) throw error;
  }
  checkCurrent(generation);
  setText('stat-events', Number.isFinite(payload?.n_events) ? formatInt(payload.n_events) : '—');
  return payload;
}

/* ------------------------------------------------------------- orchestration */

const requestPreview = debounce(async () => {
  // The preview is the spatial panels' alone; the physics cards wait for the release.
  if (!pagePlan.spatial) return;
  try {
    await loadProjections(true);
    showBanner(mergedWarnings());
  } catch (error) {
    if (!isAbort(error)) reportError(error, 'projection preview');
  }
}, DEBOUNCE_MS);

/**
 * Refresh every panel.
 *
 * The three loads are settled independently rather than with `Promise.all`, so
 * one failing endpoint degrades one panel instead of blanking the dashboard.
 * That matters here because the panels answer different questions: a selection
 * that breaks the energy fit still has perfectly good spatial projections, and
 * the physicist should keep them.
 */
/* The refresh in charge of the panels' busy state and of the banner: a
 * refresh that a newer one overtook leaves both to the newer one. */
let refreshToken = 0;

const refreshAll = debounce(async () => {
  requestPreview.cancel();
  const token = ++refreshToken;
  setBusy(true);
  // What the experiment can show (capabilities.js): no projections without
  // hits, plot 4 as the energy reconstruction or the response grid, no
  // model cards without networks, and the physics cards in view.
  const jobs = [];
  if (pagePlan.spatial) jobs.push(['spatial projections', () => loadProjections(false)]);
  else if (pagePlan.physics.includes('response-b1')) jobs.push(['selection count', () => loadEventCount()]);
  if (pagePlan.plot4 === 'energy-d') jobs.push(['energy distribution', () => loadEnergy()]);
  else if (pagePlan.plot4 === 'response-b3') jobs.push(['response grid', () => loadPlot4Grid()]);
  if (pagePlan.performance) jobs.push(['model performance', () => loadPerformance()]);
  if (pagePlan.physics.length) jobs.push(['physics panels', () => physics.refresh()]);
  // The grid on show follows the selection too: the pinned event's neighbours
  // and in-selection flag, or the three frames of the comparison.
  if (state.get('event') !== null && pagePlan.eventInspector) jobs.push(['event inspector', () => inspector.load()]);
  else if (state.get('compare') && pagePlan.compare) jobs.push(['frame comparison', () => loadCompare()]);
  try {
    const results = await Promise.allSettled(jobs.map(([, run]) => run()));
    // Overtaken - by a newer refresh or an experiment switch: the newer one speaks.
    if (token !== refreshToken) return;
    const failures = [];
    results.forEach((result, index) => {
      if (result.status !== 'rejected') return;
      const error = result.reason;
      if (isAbort(error)) return;
      console.error(`[calosrv] ${jobs[index][0]} failed`, error);
      failures.push(`${jobs[index][0]}: ${describeError(error)}`);
    });
    if (failures.length) showBanner(failures, true);
    else showBanner(mergedWarnings());
  } finally {
    if (token === refreshToken) setBusy(false);
  }
}, DEBOUNCE_MS);

/** Redraw from the payloads already in hand, without another request. */
function repaint() {
  if (lastProjections) renderPanels(lastProjections);
  if (inspector.payload && state.get('event') !== null) inspector.render(inspector.payload);
  if (state.get('compare') && compareGrid.visible) renderCompare();
  renderPlot4();
  physics.repaint();
}

function reportError(error, context = '') {
  console.error('[calosrv]', context || 'error', error);
  showBanner([context ? `${context}: ${describeError(error)}` : describeError(error)], true);
}

/* --------------------------------------------------------------- experiments */

async function loadExperiments({ selectFirst = false } = {}) {
  const payload = await getJson('/api/experiments', {}, 'experiments');
  experiments = payload.experiments;

  fillComputeBadges(payload.compute);

  // A link without view state opens on the Admin Settings panel's defaults.
  // Taken once, before an experiment is chosen and before the first render,
  // so the radios are repainted without a single request for the built-in view.
  const defaultNotices = [];
  if (state.applyDefaults(payload.defaults)) {
    restoreControlsFromState();
    defaultNotices.push(...(payload.defaults.notices || []));
  }

  fillExperimentSelect(dom.experiment, experiments);
  // A failed experiment's reason, verbatim - for a retired schema it says
  // what to do about it.
  const failed = experiments.filter((e) => e.status === 'failed' && e.error)
    .map((e) => `${e.display_name || e.table_name}: ${e.error}`);
  if (failed.length || defaultNotices.length) showBanner([...defaultNotices, ...failed]);

  const chosen = chooseExperiment(experiments, state.get('table_name'), { selectFirst });
  if (!chosen) {
    showBanner([
      'No experiment has finished ingesting yet. Open Admin Settings → Upload dataset, ' +
      'or run the offline ingest CLI on the server.',
    ], true);
    return null;
  }

  setVal('experiment-select', chosen.table_name);
  await activateExperiment(chosen);
  return chosen;
}

/**
 * Open one experiment: its plan (what the page shows), its controls, its
 * filters and bounds, then one refresh.
 *
 * Switching to another experiment first takes every picture of the previous
 * one down, so a request that fails leaves an empty panel saying why rather
 * than the last experiment's data under the new experiment's name.
 */
async function activateExperiment(experiment) {
  const previous = activeExperiment;
  const previousPlan = pagePlan;
  activeExperiment = experiment;
  pagePlan = page1Plan(experiment);
  state.set({ table_name: experiment.table_name }, { silent: true });
  const notices = [];
  if (previous && previous.table_name !== experiment.table_name) {
    clearExperimentViews();
    kindBanner.dismissed.clear();
    // The frame across a change of kind: Local carries over; a frame the new
    // experiment's radios do not offer falls back to Absolute, with one line
    // saying so. A #frame=trans link or a saved default is not a switch, so
    // it still opens the legacy per-shower frame.
    const carried = carriedFrame(previousPlan, pagePlan, state.get('frame'));
    if (carried.notice) {
      state.set({ frame: carried.frame }, { silent: true });
      notices.push(carried.notice);
    }
  }
  notices.push(...applyCapabilities(experiment));
  applyKindPlan(pagePlan, notices);
  // The experiment's own filter axes and bounds; the domains are recorded
  // before the one hash write, so a link carries no raw dataset bound.
  filters.adopt(experiment, pagePlan.axes);

  if (pagePlan.spatial) {
    // The resolution slider's useful ceiling is set by the detector: beyond the
    // native cell count no further detail exists, though splatting keeps the
    // image free of gaps.
    const nx = experiment.native_resolution ? experiment.native_resolution.xy[1] : 200;
    dom.resolution.max = Math.max(100, Math.min(400, nx * 2));
    // Remembered rather than written: a co-registered frame shows its own
    // hint, and a later switch to the lab must find this experiment's lattice.
    labResolutionHint = `Native transverse lattice is ${nx} cells; depth is fixed at `
      + `${experiment.native_resolution ? experiment.native_resolution.yz[1] : '—'} sampling layers.`;
  }
  // The frame may have moved (a fallback, or a switch of kind): the controls
  // it decides - the frame tier, the display radios, the density
  // normalisation and the scale lock - follow it.
  applyControlAvailability();
  setText('channel-caption', currentChannelCaption(lastProjections));

  physics.applyPlan(pagePlan);
  if (previous && previous.table_name === experiment.table_name) physics.invalidate();
  applyViewMode();
  refreshAll.flush();
}

/**
 * Take down everything the previous experiment drew: the spatial panels,
 * plot 4, the model cards, the status readouts, the notes and warnings, the
 * physics cards and the comparison rows.
 */
function clearExperimentViews() {
  // Every response still in flight belongs to the previous experiment: the
  // ones an abort still reaches are aborted, and the generation drops the rest.
  viewGeneration += 1;
  requestPreview.cancel();
  for (const request of Object.values(windowAxisRequests)) request.cancel();
  for (const key of SPATIAL_ABORT_KEYS) abortRequest(key);
  lastProjections = null;
  lastEnergy = null;
  lastPlot4 = null;
  for (const panel of Object.values(panels)) panel.clear();
  // The energy panel's clear empties the card's fit table and sparse note,
  // which plot 4's response grid writes into too.
  energyPanel.clear();
  plot4Grid?.clear();
  metricsPanel.renderError('—');
  for (const id of STATUS_IDS) setText(id, '—');
  setHidden('stat-wneg-item', true);
  for (const key of Object.keys(endpointWarnings)) endpointWarnings[key] = [];
  for (const kind of GRID_ROWS) comparePayloads[kind] = null;
  physics.reset();
  for (const id of Object.keys(panelNotes)) {
    panelNotes[id] = null;
    markDetails(id, null);
    shell.refresh(id, null);
  }
}

/* The status bar's readouts of one selection. */
const STATUS_IDS = ['stat-events', 'stat-hits', 'stat-edep', 'stat-d', 'stat-nod', 'stat-rho', 'stat-clipped',
  'stat-wneg', 'stat-latency', 'stat-cache'];

/* The abort keys of every request outside the physics section (whose own
 * keys `physics.reset()` aborts): the projections, plot 4, the model cards,
 * the comparison rows, the windowed axes and the Event Inspector. */
const SPATIAL_ABORT_KEYS = ['projections', 'energy', 'performance', 'compare-lab', 'compare-trans',
  'compare-local', 'compare-canonical', 'window-axis-yz', 'window-axis-xz', 'event', 'event-pick'];

/* ------------------------------------------------------------------- wiring */

dom.experiment.addEventListener('change', async () => {
  const experiment = experiments.find((e) => e.table_name === dom.experiment.value);
  if (experiment) await activateExperiment(experiment);
});

for (const input of document.querySelectorAll('input[name="display"]')) {
  input.addEventListener('change', () => {
    // Written onto the active frame's mode only (state.js).
    state.set({ display: input.value });
    syncDisplayControls();
    refreshAll();
  });
}

dom.resolution.addEventListener('input', () => {
  setText('resolution-readout', dom.resolution.value);
});
dom.resolution.addEventListener('change', () => {
  state.set({ resolution: Number(dom.resolution.value) });
  refreshAll();
});

for (const input of document.querySelectorAll('input[name="channel"]')) {
  input.addEventListener('change', () => {
    state.set({ channel: input.value });
    applyControlAvailability();
    setText('channel-caption', currentChannelCaption());
    refreshAll();
  });
}

for (const input of document.querySelectorAll('input[name="frame-view"]')) {
  input.addEventListener('change', () => {
    // Entering Separation-Aligned always lands on Translated, the D-frame;
    // the legacy per-shower frame is never entered from the sidebar.
    changeFrame(input.value === 'aligned' ? (enteringSub(offeredFrames) ?? 'canonical') : 'lab');
  });
}

for (const input of document.querySelectorAll('input[name="frame-sub"]')) {
  input.addEventListener('change', () => changeFrame(input.value));
}

for (const input of document.querySelectorAll('input[name="anchor"]')) {
  input.addEventListener('change', () => {
    state.set({ anchor: input.value });
    refreshAll();
  });
}

for (const input of document.querySelectorAll('input[name="rho_norm"]')) {
  input.addEventListener('change', () => {
    state.set({ rho_norm: input.value });
    refreshAll();
  });
}

for (const input of document.querySelectorAll('input[name="model"]')) {
  input.addEventListener('change', () => {
    // The model drives the CAM projections and the cards, so everything
    // refreshes; a density request is served from any network's bundle.
    state.set({ model: input.value });
    setText('channel-caption', currentChannelCaption());
    refreshAll();
  });
}

dom.colormap.addEventListener('change', () => {
  state.set({ palette: dom.colormap.value });
  // A palette change is a pure repaint of data already held - the physics
  // cards' and plot 4's included; it must not cost a round trip.
  repaint();
  // Carry the active shower filter across: re-rendering without it silently
  // reset the A/B toggle to Both on every colormap change.
  renderEnergy();
});

dom.lockScale.addEventListener('change', () => {
  state.set({ lock_scale: dom.lockScale.checked });
  refreshAll();
});

dom.compare.addEventListener('change', () => {
  state.set({ compare: dom.compare.checked });
  applyViewMode();
  // Three requests for the comparison alone; the ensemble panels keep theirs.
  if (state.get('compare') && state.get('event') === null) refreshCompare();
});
document.getElementById('compare-grid-close')?.addEventListener('click', () => {
  state.set({ compare: false });
  applyViewMode();
});

/* ------------------------------------------- RoI, popovers, shower toggle */

for (const button of document.querySelectorAll('[data-roi]')) {
  button.addEventListener('click', () => {
    const panel = panels[button.dataset.roi];
    if (!panel) return;
    const outcome = panel.autoFitRoI();
    if (outcome === 'empty') {
      showBanner(['No active hits in this panel to fit a region of interest to.']);
    } else if (outcome === 'full') {
      // Most multi-event selections put showers all across the detector face,
      // so there is genuinely nothing to crop to. Say so rather than let the
      // button look broken.
      showBanner([
        'The selected hits already span the detector, so there is no tighter '
        + 'region to fit. Scroll to zoom and drag to pan into a single cluster.',
      ]);
    }
  });
}

for (const button of document.querySelectorAll('[data-reset]')) {
  button.addEventListener('click', () => panels[button.dataset.reset]?.resetView());
}

for (const button of document.querySelectorAll('[data-shower]')) {
  button.addEventListener('click', () => {
    showerFilter = button.dataset.shower;
    for (const other of document.querySelectorAll('[data-shower]')) {
      other.classList.toggle('is-active', other === button);
    }
    // A pure re-filter of data already in hand; no round trip.
    renderEnergy();
  });
}

/* Plot 4 on a single shower draws the notebook's six windows; its link takes
 * the reader to the full-width response card below, set to the producer's
 * 1 GeV bins, which that card alone holds. */
document.getElementById('energy-b3-link')?.addEventListener('click', () => {
  physics.reveal('response-b3', { b3Slices: 'bins' });
});

/* ------------------------------------------------------------ figure export */

/* The figure is the plot alone. What it shows is named from the response's
 * own meta - channel, network, weighting, frame - never from controls that may
 * have moved on since; the methodology and disclosures are the panel's
 * Details drawer, not the file. */
const EXPORT_PANELS = {
  xy: () => panels.xy,
  yz: () => panels.yz,
  xz: () => panels.xz,
  energy: () => energyPanel,
};

attachExportMenus({
  state,
  onError: (message) => showBanner([message], true),
  resolve: (panelId) => {
    if (panelId.startsWith('event-')) {
      // An Event Inspector cell: the event response's meta, with the row's frame.
      const panel = eventGrid.panelById(panelId);
      return panel?.payload ? { panel, meta: inspector.exportMeta(panelId.split('-')[1]) } : null;
    }
    if (panelId.startsWith('compare-')) {
      const panel = compareGrid.panelById(panelId);
      return panel?.payload ? { panel, meta: comparePayloads[panelId.split('-')[1]]?.meta ?? null } : null;
    }
    const target = physics.exportTarget(panelId);
    if (target !== undefined) return target;
    if (panelId === 'energy' && pagePlan.plot4 === 'response-b3') {
      // A single shower's plot 4 is the response grid; its own response names it.
      return plot4Grid?.lastPayload && lastPlot4 ? { panel: plot4Grid, meta: physicsExportMeta(lastPlot4) } : null;
    }
    const get = EXPORT_PANELS[panelId];
    if (!get) return null;
    const panel = get();
    const ready = panelId === 'energy' ? panel.lastPayload : panel.payload;
    if (!ready) return null;
    return {
      panel,
      meta: panelId === 'energy' ? (lastEnergy?.meta ?? null) : (lastProjections?.meta ?? null),
    };
  },
});

for (const [scope, dot] of Object.entries(dom.infoDots)) {
  if (!dot) continue;
  dot.addEventListener('click', (event) => {
    event.stopPropagation();
    if (activePopover) { hidePopover(); return; }
    if (scope === 'anchor') {
      // The definitions, and the distance between them measured on the
      // selection the panels show, when a D-frame response is in hand.
      const frame = kindOf(lastProjections) === 'canonical' ? lastProjections.frame : null;
      showExplainer(dot, anchorExplainer(frame, state.get('anchor')));
      return;
    }
    const texts = scope === 'density'
      ? [DENSITY_EXPLAINER]
      : JSON.parse(dot.dataset.notices || '[]');
    showPopover(dot, texts, { neutral: scope === 'density' });
  });
}
dom.infoDots.density?.classList.add('is-neutral');

document.addEventListener('click', hidePopover);
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') hidePopover();
});

/* The Admin Settings panel hosts the upload form. Each is constructed in its
 * own guard: a failure in either must not take the dashboard with it - the
 * panel is an operator's tool, the plots are everyone's - and a fault in the
 * form's markup must not take the panel down either. */
let adminModal = null;
let uploadForm = null;
try {
  uploadForm = new UploadForm({
    // The form asks this before sending: whether a name is taken, and by what.
    getExperiments: () => experiments,
    onComplete: async (job) => {
      // Open the experiment that was just ingested, not the one on screen.
      if (job && job.table_name) state.set({ table_name: job.table_name }, { silent: true });
      await loadExperiments({ selectFirst: false });
      await adminModal?.refreshDatasets();
    },
  });
} catch (error) {
  reportError(error, 'upload form');
}
try {
  adminModal = new AdminModal({
    state,
    upload: uploadForm,
    // The catalogue carries each experiment's derived-table status, for the
    // panel's Rebuild derived tables section.
    getExperiments: () => experiments,
    // An automatic ingest that finishes while the panel is open joins the
    // experiment list at once, without switching away from the current view.
    onIngested: async () => { await loadExperiments({ selectFirst: false }); },
  });
} catch (error) {
  reportError(error, 'admin settings');
}

/* --------------------------------------------------------------------- boot */

function restoreControlsFromState() {
  // Checked state only - never synthesised clicks, which would fire the change
  // handlers and trigger a refresh before an experiment has been selected.
  // The display radios follow the active frame's mode; `applyControlAvailability`
  // below sets them, their labels and the R control together.
  const v = state.values;
  setVal('resolution', v.resolution);
  setText('resolution-readout', v.resolution);
  for (const input of document.querySelectorAll('input[name="channel"]')) {
    input.checked = input.value === v.channel;
  }
  for (const input of document.querySelectorAll('input[name="model"]')) {
    input.checked = input.value === v.model;
  }
  for (const input of document.querySelectorAll('input[name="rho_norm"]')) {
    input.checked = input.value === v.rho_norm;
  }
  applyControlAvailability();
  setVal('colormap', v.palette);
  setChecked('opt-lock-scale', v.lock_scale);
  setChecked('opt-undefined-d', v.include_undefined_d);
  setText('channel-caption', currentChannelCaption(null));
  applyViewMode();
}

/* Every element id the update routines write to.
 *
 * Audited once at startup so a markup/script mismatch is named immediately and
 * on screen, rather than surfacing as a null dereference somewhere deep in a
 * render. The helpers in dom.js already make each individual write survivable;
 * this is what turns "some readouts are blank" into a message that says why. */
const REQUIRED_IDS = [
  'stat-events', 'stat-hits', 'stat-edep', 'stat-d', 'stat-nod', 'stat-rho', 'stat-clipped',
  'stat-latency', 'stat-cache', 'banner', 'banner-text', 'banner-close', 'energy-sparse',
  'badge-memory', 'badge-threads', 'badge-exact', 'exact-badge',
  'tag-xy', 'tag-energy', 'title-xy', 'title-yz', 'title-xz', 'info-frame', 'frame-caption',
  'ctl-frame', 'frame-sub', 'frame-sub-trans', 'anchor-sub', 'info-anchor', 'ctl-rho-norm', 'ctl-lock-scale',
  'sidebar', 'sidebar-toggle', 'inspector', 'inspector-title', 'inspector-body', 'inspector-close',
  'display-caption', 'channel-caption', 'resolution', 'resolution-readout',
  'resolution-hint', 'display-label-native', 'display-label-continuous',
  'colormap', 'colormap-hint', 'opt-lock-scale', 'opt-undefined-d',
  'experiment-select', 'fit-table', 'metrics', 'model-caption',
  'plot-xy', 'plot-yz', 'plot-xz', 'plot-energy', 'ensemble-grid',
  'event-grid', 'event-grid-rows', 'event-grid-label', 'event-grid-close', 'info-event',
  'event-number', 'event-prev', 'event-next', 'event-pick', 'event-close', 'event-status', 'event-caption',
  'compare-grid', 'compare-grid-rows', 'compare-grid-label', 'compare-grid-close', 'opt-compare',
  'e1-lo', 'e1-hi', 'e1-fill', 'e1-num-lo', 'e1-num-hi',
  'e2-lo', 'e2-hi', 'e2-fill', 'e2-num-lo', 'e2-num-hi',
  'd-lo', 'd-hi', 'd-fill', 'd-num-lo', 'd-num-hi',
  'physics-grid', 'kind-notice', 'kind-notice-title', 'kind-notice-text', 'kind-banner',
  'kind-banner-text', 'kind-banner-close', 'stat-d-item', 'stat-nod-item', 'stat-wneg-item', 'stat-wneg',
  'e1-label', 'e1-hint', 'filter-logic', 'ctl-undefined-d', 'energy-shower-toggle', 'energy-b3-slices',
  'energy-b3-link', 'plot-energy-b3', 'ctl-e1', 'ctl-e2', 'ctl-d', 'ctl-event', 'ctl-compare',
  'group-frame', 'group-resolution', 'group-channel', 'group-colormap',
];

/**
 * Land a Methodology badge's link: the card scrolled into view, its Details
 * drawer open with the way back to the article, or - when this experiment, or
 * the view on screen, does not show the card - the reason on the kind banner,
 * which outlives the refresh that follows (the transient banner would be
 * rewritten by it). Without an open experiment there is nothing to land on,
 * and the banner already says why.
 */
function landDeepLink(link) {
  if (!activeExperiment) return;
  const back = returnLink(link);
  if (link.panel && back) shell.setReturnLink(link.panel, back);
  let result = revealPanel(link.panel ?? '', { shell, reveal: (id) => physics.reveal(id) });
  if (result.ok) return;
  // A pinned event or the compare view replaces the ensemble panels (applyViewMode): that is the view's doing.
  const viewHides = (state.get('event') !== null && pagePlan.eventInspector) || (state.get('compare') && pagePlan.compare);
  if (result.reason === 'hidden' && viewHides && result.card?.closest?.('#ensemble-grid, #physics-grid')) {
    result = { ...result, reason: 'view' };
  }
  const title = result.card?.querySelector('.title')?.textContent?.trim() ?? '';
  const notice = revealNotice(result, { requested: link.requested, title, kind: pagePlan.kindLabel });
  kindBanner.show([...kindBanner.shown, notice]);
}

async function boot() {
  // Read before anything writes the hash: State.writeHash replaces the URL
  // with path and hash alone, so the query is gone once an experiment loads.
  const openAdmin = new URLSearchParams(location.search).has('admin');
  const deepLink = readDeepLink(location.search);
  const missing = missingIds(REQUIRED_IDS);
  if (missing.length) {
    // Almost always a cached script against fresh markup. Say so, because the
    // symptom otherwise looks like a server fault.
    console.error('[calosrv] missing element ids:', missing);
    showBanner([
      `The page and its scripts are out of step — ${missing.length} expected `
      + `element(s) are missing (${missing.slice(0, 4).join(', ')}`
      + `${missing.length > 4 ? ', …' : ''}). Reload with cache disabled `
      + '(Ctrl+Shift+R). The dashboard will continue with those readouts blank.',
    ], true);
  }

  try {
    restoreControlsFromState();
  } catch (error) {
    reportError(error, 'restoring controls');
  }

  try {
    await loadExperiments({ selectFirst: false });
  } catch (error) {
    reportError(error, 'loading experiments');
  }

  // The Models page's Admin Settings link (/?admin=1) opens the panel here,
  // with the view its hash carries; the query is dropped so a reload or a
  // bookmark of this page does not open it again. A Methodology badge's link
  // (?panel=...) is landed the same way.
  if (openAdmin || deepLink) {
    history.replaceState(null, '', location.pathname + location.hash);
  }
  if (deepLink) landDeepLink(deepLink);
  if (openAdmin) {
    adminModal?.open();
  }
}

// The header's page tabs carry the view (the hash) to the Models page and back.
wirePageTabs();

// A failure anywhere above must not leave a blank page with a silent console.
window.addEventListener('error', (event) => {
  console.error('[calosrv] uncaught', event.error || event.message);
});
window.addEventListener('unhandledrejection', (event) => {
  console.error('[calosrv] unhandled rejection', event.reason);
});


boot();
