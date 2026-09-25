/* Application bootstrap and control wiring. */

import { getJson, debounce, ApiError, DEBOUNCE_MS } from './api.js';
import { State, apiFrame, isCoregistered } from './state.js';
import { RangeSlider } from './controls/range_slider.js';
import { UploadModal } from './controls/upload.js';
import { ProjectionPanel } from './panels/projection.js';
import { EnergyPanel } from './panels/energy.js';
import { MetricsPanel } from './panels/metrics.js';
import { formatBytes, formatInt, formatNumber, formatSci, isDiverging } from './scale.js';
import { setText, setHtml, setHidden, setVal, setChecked, missingIds } from './dom.js';
import { attachExportMenus } from './export/menu.js';
import { figureDisclosure } from './export/disclosure.js';
import {
  FRAME_VIEWS, frameView, kindOf, panelTitle, displayCaption, channelCaption, entryTag,
  showerTag, footnotes, exportLegend, energyNetworkSentence,
} from './frame_views.js';

const state = new State();

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
 * panel rebuilds its letterbox - and the footnote, which states the aspect,
 * must follow. The panel calls this from its ResizeObserver. */
for (const id of ['yz', 'xz']) {
  panels[id].onRelayout = (panel) => {
    if (kindOf(lastProjections) === 'lab' || !panel.payload) return;
    const next = depthIsometric(panel, panel.payload);
    if (next === panel.isometric) return;
    panel.isometric = next;
    writeFootnotes(lastProjections);
  };
}
const energyPanel = new EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
const metricsPanel = new MetricsPanel('metrics', 'model-caption');

const dom = {
  experiment: document.getElementById('experiment-select'),
  banner: document.getElementById('banner'),
  bannerText: document.getElementById('banner-text'),
  bannerClose: document.getElementById('banner-close'),
  energySparse: document.getElementById('energy-sparse'),
  infoDots: {
    resolution: document.getElementById('info-resolution'),
    separation: document.getElementById('info-separation'),
    density: document.getElementById('info-density'),
    frame: document.getElementById('info-frame'),
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
  footXy: document.getElementById('foot-xy'),
  footYz: document.getElementById('foot-yz'),
  footXz: document.getElementById('foot-xz'),
  footEnergy: document.getElementById('foot-energy'),
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
  undefinedD: document.getElementById('opt-undefined-d'),
};

let experiments = [];
let activeExperiment = null;
let lastProjections = null;
let lastEnergy = null;
let showerFilter = 'both';
/* Warnings the projections and performance endpoints sent with their last
 * responses, merged into one banner. */
const endpointWarnings = { projections: [], performance: [] };

const DENSITY_EXPLAINER =
  'A probability density is not a probability. The curve integrates to 1.0 over '
  + 'the energy axis, so its height carries units of GeV⁻¹ and legitimately '
  + 'exceeds 1.0 wherever the distribution is narrow — a resolution of '
  + 'σ = 0.4 GeV already peaks near 1.0 GeV⁻¹, and anything sharper peaks higher. '
  + 'A tall peak therefore means good resolution, not a probability above one. '
  + 'For the same reason a curve integrating to 1.0 says nothing about how many '
  + 'events it was built from: the peak height of a fit from nine events and one '
  + 'from ninety thousand are equally tall for equal σ. The event ticks along the '
  + 'baseline are what carry the sample size, which is why a thin slice is drawn '
  + 'with its events beneath it and is never allowed to set the axis scale.';

/* ------------------------------------------------------------------ sliders */

/* Each axis is quantised to its numeric step, so typing 2.05 and dragging to
 * 2.05 address the same grid point and round-trip through the URL unchanged. */
const sliders = {
  e1: new RangeSlider({
    loId: 'e1-lo', hiId: 'e1-hi', fillId: 'e1-fill',
    numLoId: 'e1-num-lo', numHiId: 'e1-num-hi',
    step: 0.05, decimals: 2, unit: 'GeV',
    onInput: ([lo, hi]) => { state.markTouched('e1'); state.set({ e1_min: lo, e1_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.markTouched('e1'); state.set({ e1_min: lo, e1_max: hi }); refreshAll(); },
  }),
  e2: new RangeSlider({
    loId: 'e2-lo', hiId: 'e2-hi', fillId: 'e2-fill',
    numLoId: 'e2-num-lo', numHiId: 'e2-num-hi',
    step: 0.05, decimals: 2, unit: 'GeV',
    onInput: ([lo, hi]) => { state.markTouched('e2'); state.set({ e2_min: lo, e2_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.markTouched('e2'); state.set({ e2_min: lo, e2_max: hi }); refreshAll(); },
  }),
  d: new RangeSlider({
    loId: 'd-lo', hiId: 'd-hi', fillId: 'd-fill',
    numLoId: 'd-num-lo', numHiId: 'd-num-hi',
    step: 1, decimals: 0, unit: 'mm',
    onInput: ([lo, hi]) => { state.markTouched('d'); state.set({ d_min: lo, d_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.markTouched('d'); state.set({ d_min: lo, d_max: hi }); refreshAll(); },
  }),
};

/* ------------------------------------------------------------------ loading */

function setBusy(busy) {
  for (const panel of Object.values(panels)) panel.setBusy(busy);
  energyPanel.setBusy(busy);
}

/* Messages the user has dismissed, keyed by content.
 *
 * Keying by content rather than by a counter is what makes dismissal stick: the
 * same warning is re-sent on every response during a drag, and a naive banner
 * would pop straight back up. */
const dismissed = new Set();

function showBanner(messages, isError = false) {
  const list = (messages || []).filter(Boolean).filter((m) => !dismissed.has(m));
  if (!list.length) {
    setHidden('banner', true);
    return;
  }
  setHidden('banner', false);
  dom.banner.classList.toggle('is-error', isError);
  setHtml('banner-text', list.length === 1
    ? escapeHtml(list[0])
    : `<ul>${list.map((m) => `<li>${escapeHtml(m)}</li>`).join('')}</ul>`);
  dom.banner.dataset.messages = JSON.stringify(list);
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
  if (activePopover) {
    activePopover.remove();
    activePopover = null;
  }
}

let activePopover = null;

/* -------------------------------------------------------------- projections */

/**
 * Whether a depth panel may keep a 1:1 metric aspect.
 *
 * In the laboratory frame the depth panels span 5200 mm against 1210 mm of
 * depth, where a true aspect would be an unusable sliver, so they fill the
 * card. A co-registered frame crops each panel to where the energy is, and for
 * most selections the two spans are comparable, so 1:1 becomes affordable. It
 * is used when the letterboxed plot would still keep at least 45% of the
 * card's width and the span ratio sits inside the export clamp [0.45, 1.3].
 */
function depthIsometric(panel, payload) {
  const { col, row } = payload.axes;
  const colSpan = col.hi - col.lo;
  const rowSpan = row.hi - row.lo;
  if (!(colSpan > 0 && rowSpan > 0)) return false;
  const ratio = rowSpan / colSpan;
  if (ratio < 0.45 || ratio > 1.3) return false;
  const width = panel.element.clientWidth;
  const height = panel.element.clientHeight;
  if (!(width > 0 && height > 0)) return false;
  const scale = Math.min(width / colSpan, height / rowSpan);
  return colSpan * scale >= 0.45 * width;
}

/** Draw the three spatial panels from a projections payload. */
function renderPanels(payload) {
  const palette = state.get('palette');
  const overlays = payload.overlays || {};
  const paths = overlays.trajectories || [];
  const kind = kindOf(payload);
  const canonical = kind === 'canonical';
  const coregistered = kind !== 'lab';
  const frame = coregistered ? payload.frame : null;
  // `resolution` is retained in each panel's `lastOpts`, so the exporter
  // names the R and kernel the payload was built with - which the payload
  // guard may have lowered below what the slider says.
  const common = {
    palette, frame, tableName: payload.meta?.table_name,
    resolution: payload.meta?.resolution ?? null,
    weighting: payload.meta?.weighting ?? state.get('weighting'),
  };
  const ensemble = overlays.ensemble_axes || {};
  const anchors = canonical ? (overlays.anchors || null) : null;
  const depthBounds = canonical ? { front: 0, back: frame.depth_mm } : null;

  panels.xy.isometric = true;
  panels.xy.render(payload.panels.xy, {
    ...common, centroids: payload.centroids, showVector: kind === 'lab', anchors,
  });
  // The depth panels carry the measured shower axes (lab) and the individual
  // incident trajectories when few enough events are selected to read (lab,
  // and from the origin in the translated frame). `showerKey` names which
  // transverse coordinate the panel plots, so the projection of the direction
  // vector picks sin(phi) or cos(phi) correctly. In the canonical frame both
  // give way to the two ensemble axes; the local frame draws no direction.
  for (const [id, key] of [['yz', 'y'], ['xz', 'x']]) {
    const panel = panels[id];
    panel.isometric = coregistered && depthIsometric(panel, payload.panels[id]);
    panel.render(payload.panels[id], {
      ...common,
      axes: kind === 'lab' ? overlays.axes?.[id] : null,
      trajectories: kind === 'lab' || kind === 'trans' ? paths : null,
      showerKey: key,
      ensembleAxes: canonical ? ensemble[id] || null : null,
      ensembleMeta: canonical ? frame?.ensemble || null : null,
      anchors,
      depthBounds,
    });
  }
}

/** The three footnotes, from the payload and the panels' current aspect. */
function writeFootnotes(payload) {
  const notes = footnotes(payload, {
    isometric: { yz: panels.yz.isometric, xz: panels.xz.isometric },
  });
  setText('foot-xy', notes.xy);
  setText('foot-yz', notes.yz);
  setText('foot-xz', notes.xz);
}

async function loadProjections(preview = false) {
  const params = state.projectionParams(preview);
  const payload = await getJson('/api/projections', params, 'projections');
  lastProjections = payload;

  const kind = kindOf(payload);
  const coregistered = kind !== 'lab';
  renderPanels(payload);
  for (const id of ['xy', 'yz', 'xz']) setText(`title-${id}`, panelTitle(id, kind));
  writeFootnotes(payload);

  const selection = payload.selection;
  setText('stat-events', formatInt(selection.n_events));
  setText('stat-hits', formatInt(selection.n_hits));
  setText('stat-edep', `${formatSci(selection.e_dep_total, 3)} GeV`);
  setText('stat-d', selection.d.mean !== null
    ? `${formatNumber(selection.d.mean, 0)} mm` : '—');
  setText('stat-nod', formatInt(selection.n_events_no_d));
  // The density reference is a co-registered frame's "autoscaled" badge: a ramp
  // relative to the selection's own peak looks identical for a tenth of the
  // energy, so the reader is told which reference the colours are drawn against.
  setText('stat-rho', coregistered
    ? (payload.frame.rho?.norm === 'dataset' ? 'dataset peak' : 'selection peak (autoscaled)')
    : '—');
  setText('stat-latency', `${formatNumber(payload.meta.total_ms, 1)} ms`);
  setText('stat-cache', payload.meta.cached ? 'cached' : 'scanned');

  const exact = payload.meta.exact;
  setText('badge-exact', exact ? 'Exact' : 'Preview (sampled)');
  dom.exactBadge.classList.toggle('is-warn', !exact);

  const resolution = payload.meta.resolution;
  const stagger = payload.meta.stagger || {};
  setText('display-caption', displayCaption(kind, resolution, coregistered ? payload.frame : null));
  setText('channel-caption', currentChannelCaption(payload));

  const slabTag = `${payload.slab.layers} layers · ${payload.slab.mm.toFixed(0)} mm`;
  // The canonical tag carries the mean entry separation with its interval
  // named; a per-shower tag says how many showers are superimposed. `.sym`
  // keeps the tag's uppercase transform off the symbols.
  const extra = kind === 'canonical' ? entryTag(payload.frame)
    : coregistered ? showerTag(payload.frame) : '';
  if (extra) setHtml('tag-xy', `${slabTag} · <span class="sym">${extra}</span>`);
  else setText('tag-xy', slabTag);

  // Persistent explanations go to the sidebar info dots; the banner keeps only
  // transient, actionable messages.
  const notices = payload.meta.notices || [];
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
 * Show, hide and disable the controls the active frame and channel make
 * meaningful.
 *
 * The density normalisation belongs to the co-registered frames; the lock
 * belongs to the lab and to density; a signed channel is always drawn on the
 * diverging PuOr, so the sequential colour map is disabled and says why.
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
  setText('frame-caption', frameView(frame).caption);
  syncDisplayControls();
}

/**
 * Grey out every frame, channel and model the active experiment does not
 * serve (from `/api/experiments`), and fall back from one a link asked for.
 */
function applyCapabilities(experiment) {
  const frames = experiment?.frames ?? ['lab', 'canonical'];
  const coords = experiment?.coord_systems ?? ['lab'];
  const offered = {
    // A frame is offered when the experiment lists it and serves its
    // coordinate system (the canonical frame is built from lab coordinates).
    frame: Object.keys(FRAME_VIEWS).filter(
      (f) => frames.includes(f) && coords.includes(apiFrame(f).coord_system),
    ),
    channel: experiment?.channels ?? ['density', 'gradcam'],
    model: experiment?.models ?? ['segmentation'],
  };
  const fallbacks = [];
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
  if (fallbacks.length) {
    restoreControlsFromState();
    showBanner(fallbacks);
  }
}

async function loadEnergy() {
  const payload = await getJson('/api/energy-distribution', state.energyParams(), 'energy');
  lastEnergy = payload;
  energyPanel.render(payload, {
    palette: state.get('palette'), kind: 'pred', shower: showerFilter,
  });

  const calibration = payload.calibration;
  setText('tag-energy', calibration.applied ? 'calibrated' : 'deposited');
  const parts = [];
  if (calibration.applied) {
    parts.push(
      `Energies are calibrated to the incident-momentum scale by the fitted ` +
      `sampling fractions f_A = ${formatSci(calibration.sampling_fraction_a, 3)}, ` +
      `f_B = ${formatSci(calibration.sampling_fraction_b, 3)}.`
    );
  }
  const clipping = payload.axis.clipping;
  if (clipping && clipping.applied && clipping.n_outside) parts.push(clipping.note);
  const network = energyNetworkSentence(payload);
  if (network) parts.push(network);
  parts.push(
    'Solid curves are Gaussian fits and dashed curves mark shower B; a thinner, '
    + 'fainter curve is a thin slice, drawn but not allowed to set the density '
    + 'axis. Below the histogram floor the individual events appear as baseline '
    + 'ticks, with the sample dispersion as a shaded band and the mean with its '
    + '95% confidence interval as a capped whisker — two different quantities, '
    + 'so two different marks. Dotted verticals are the isolated single-shower '
    + 'reference benchmarks at μ ± σ: stated widths, not fits.'
  );
  // The energy panel's warnings describe its own slices and are stated in
  // its notices; only the payload guard's re-sampling is new, and it belongs
  // with the curves it changed.
  for (const warning of payload.meta?.warnings || []) {
    if (warning.startsWith('Density curves sampled')) parts.push(warning);
  }
  setText('foot-energy', parts.join(' '));
  return payload;
}

async function loadPerformance() {
  const payload = await getJson('/api/model-performance', state.performanceParams(), 'performance');
  metricsPanel.render(payload, payload.meta.total_ms);
  // The first performance warning is shown in the model caption; the rest
  // join the banner.
  endpointWarnings.performance = (payload.meta?.warnings || []).slice(1);
  return payload;
}

/**
 * The union of every endpoint's warnings, without duplicates and without any
 * text a footnote or caption already states.
 */
function mergedWarnings() {
  const shown = ['foot-xy', 'foot-yz', 'foot-xz', 'foot-energy', 'display-caption', 'channel-caption']
    .map((id) => document.getElementById(id)?.textContent || '').join(' ');
  const seen = new Set();
  const out = [];
  for (const text of [...endpointWarnings.projections, ...endpointWarnings.performance]) {
    if (!text || seen.has(text) || shown.includes(text)) continue;
    seen.add(text);
    out.push(text);
  }
  return out;
}

/* ------------------------------------------------------------- orchestration */

const requestPreview = debounce(async () => {
  try {
    await loadProjections(true);
    showBanner(mergedWarnings());
  } catch (error) {
    if (error.name !== 'AbortError') reportError(error, 'projection preview');
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
const refreshAll = debounce(async () => {
  requestPreview.cancel();
  setBusy(true);
  const jobs = [
    ['spatial projections', () => loadProjections(false)],
    ['energy distribution', () => loadEnergy()],
    ['model performance', () => loadPerformance()],
  ];
  try {
    const results = await Promise.allSettled(jobs.map(([, run]) => run()));
    const failures = [];
    results.forEach((result, index) => {
      if (result.status !== 'rejected') return;
      const error = result.reason;
      if (error?.name === 'AbortError') return;
      console.error(`[calosrv] ${jobs[index][0]} failed`, error);
      failures.push(`${jobs[index][0]}: ${describeError(error)}`);
    });
    if (failures.length) showBanner(failures, true);
    else showBanner(mergedWarnings());
  } finally {
    setBusy(false);
  }
}, DEBOUNCE_MS);

/** Redraw from the payload already in hand, without another request. */
function repaint() {
  if (!lastProjections) return;
  renderPanels(lastProjections);
}

function describeError(error) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) {
    // The signature of markup and script disagreeing about the document.
    return `${error.message} (the page and its scripts may be out of step; `
      + 'a hard reload should fix it)';
  }
  return String(error && error.message ? error.message : error);
}

function reportError(error, context = '') {
  console.error('[calosrv]', context || 'error', error);
  showBanner([context ? `${context}: ${describeError(error)}` : describeError(error)], true);
}

/* --------------------------------------------------------------- experiments */

async function loadExperiments({ selectFirst = false } = {}) {
  const payload = await getJson('/api/experiments', {}, 'experiments');
  experiments = payload.experiments;

  const compute = payload.compute;
  setText('badge-memory', `${compute.duckdb_memory_gb} GB`);
  setText('badge-threads', compute.threads);

  setHtml('experiment-select', experiments.map((e) => {
    const suffix = e.status === 'ready'
      ? ` — ${formatInt(e.n_events)} events`
      : ` — ${e.status}`;
    const title = e.error ? ` title="${escapeHtml(e.error)}"` : '';
    return `<option value="${escapeHtml(e.table_name)}"${e.status !== 'ready' ? ' disabled' : ''}${title}>`
      + `${escapeHtml(e.display_name)}${suffix}</option>`;
  }).join(''));
  // A failed experiment's reason, verbatim - for a retired schema it says
  // what to do about it.
  const failed = experiments.filter((e) => e.status === 'failed' && e.error)
    .map((e) => `${e.display_name || e.table_name}: ${e.error}`);
  if (failed.length) showBanner(failed);

  const ready = experiments.filter((e) => e.status === 'ready');
  if (!ready.length) {
    showBanner([
      'No experiment has finished ingesting yet. Use "Upload Dataset", or run ' +
      'the offline ingest CLI on the server.',
    ], true);
    return null;
  }

  const wanted = state.get('table_name');
  const chosen = (!selectFirst && ready.find((e) => e.table_name === wanted)) || ready[0];
  setVal('experiment-select', chosen.table_name);
  await activateExperiment(chosen);
  return chosen;
}

async function activateExperiment(experiment) {
  activeExperiment = experiment;
  state.set({ table_name: experiment.table_name }, { silent: true });
  applyCapabilities(experiment);

  const bounds = experiment.bounds;
  state.adoptBounds(bounds);

  // An axis the user has not narrowed takes the full snapped domain. Passing
  // the raw dataset bound instead would round it to the nearest grid point -
  // 0.380 becomes 0.40 against a domain starting at 0.35 - which is not the
  // full range, so the link would carry a bound that selects nothing.
  const v = state.values;
  const initial = (axis, lo, hi) => (state.isTouched(axis) ? [lo, hi] : null);

  sliders.e1.setBounds(bounds.e1[0], bounds.e1[1], initial('e1', v.e1_min, v.e1_max));
  sliders.e2.setBounds(bounds.e2[0], bounds.e2[1], initial('e2', v.e2_min, v.e2_max));

  const hasD = bounds.d[0] !== null && bounds.d[1] !== null;
  sliders.d.setDisabled(!hasD, 'N/A');
  if (hasD) sliders.d.setBounds(bounds.d[0], bounds.d[1], initial('d', v.d_min, v.d_max));

  // The sliders snap their domain outward to the step grid, so "the full range"
  // is the snapped bound. The hash omits a bound only when it matches this.
  state.setSliderDomains({
    e1: [sliders.e1.min, sliders.e1.max],
    e2: [sliders.e2.min, sliders.e2.max],
    d: hasD ? [sliders.d.min, sliders.d.max] : null,
  });

  // Adopt whatever the sliders actually resolved to. The dataset bound 0.408
  // snaps to 0.40, and leaving state on the raw value would both disagree with
  // what the control shows and defeat the full-range test above, so every link
  // would carry all six bounds.
  const [e1Lo, e1Hi] = sliders.e1.value();
  const [e2Lo, e2Hi] = sliders.e2.value();
  const adopted = { e1_min: e1Lo, e1_max: e1Hi, e2_min: e2Lo, e2_max: e2Hi };
  if (hasD) {
    const [dLo, dHi] = sliders.d.value();
    adopted.d_min = dLo;
    adopted.d_max = dHi;
  }
  state.set(adopted, { silent: true });
  state.writeHash();

  // The resolution slider's useful ceiling is set by the detector: beyond the
  // native cell count no further detail exists, though splatting keeps the
  // image free of gaps.
  const nx = experiment.native_resolution ? experiment.native_resolution.xy[1] : 200;
  dom.resolution.max = Math.max(100, Math.min(400, nx * 2));
  // Remembered rather than written: a co-registered frame shows its own
  // hint, and a later switch to the lab must find this experiment's lattice.
  labResolutionHint = `Native transverse lattice is ${nx} cells; depth is fixed at `
    + `${experiment.native_resolution ? experiment.native_resolution.yz[1] : '—'} sampling layers.`;
  syncDisplayControls();

  refreshAll.flush();
}

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

for (const input of document.querySelectorAll('input[name="frame"]')) {
  input.addEventListener('change', () => {
    state.set({ frame: input.value });
    // Also resyncs the display radios: each frame returns to its own mode.
    applyControlAvailability();
    setText('channel-caption', currentChannelCaption());
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
  // A palette change is a pure repaint of data already held; it must not cost
  // a round trip.
  repaint();
  if (lastEnergy) {
    // Carry the active shower filter across: re-rendering without it silently
    // reset the A/B toggle to Both on every colormap change.
    energyPanel.render(lastEnergy, {
      palette: state.get('palette'), kind: 'pred', shower: showerFilter,
    });
  }
});

dom.lockScale.addEventListener('change', () => {
  state.set({ lock_scale: dom.lockScale.checked });
  refreshAll();
});

dom.undefinedD.addEventListener('change', () => {
  state.set({ include_undefined_d: dom.undefinedD.checked });
  refreshAll();
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
    if (lastEnergy) {
      energyPanel.render(lastEnergy, {
        palette: state.get('palette'), kind: 'pred', shower: showerFilter,
      });
    }
  });
}

/* ------------------------------------------------------------ figure export */

/* What each panel contributes to its exported figure.
 *
 * The footnote is read live off the page rather than rebuilt, so the figure
 * carries the same disclosure the reader saw - the clipping count, the
 * staggered-comb warning, the measured R̄ - without a second copy of the
 * sentences that could drift out of step with the panel's own. */
const EXPORT_PANELS = {
  xy: { panel: () => panels.xy, title: () => panelTitle('xy', kindOf(lastProjections)), foot: 'foot-xy' },
  yz: { panel: () => panels.yz, title: () => panelTitle('yz', kindOf(lastProjections)), foot: 'foot-yz' },
  xz: { panel: () => panels.xz, title: () => panelTitle('xz', kindOf(lastProjections)), foot: 'foot-xz' },
  energy: {
    panel: () => energyPanel,
    title: () => 'Reconstructed Energy vs. Separation D',
    foot: 'foot-energy',
    extraFoot: 'energy-sparse',
  },
};

attachExportMenus({
  state,
  getExperiment: () => activeExperiment,
  onError: (message) => showBanner([message], true),
  resolve: (panelId) => {
    const spec = EXPORT_PANELS[panelId];
    if (!spec) return null;
    const panel = spec.panel();
    const ready = panelId === 'energy' ? panel.lastPayload : panel.payload;
    if (!ready) return null;

    const notes = [document.getElementById(spec.foot)?.textContent || ''];
    // The low-statistics notices are a separate block on screen but belong to
    // the same figure: they name the gating floors and the clipped peaks.
    // Read per paragraph, because `textContent` on the container would run the
    // last word of one notice into the first of the next.
    const extra = spec.extraFoot ? document.getElementById(spec.extraFoot) : null;
    if (extra && !extra.hidden) {
      for (const p of extra.querySelectorAll('p')) notes.push(p.textContent || '');
    }

    // Disclosures read structurally from the payload, so the figure states
    // the clipping counts, the frame, the density reference and the measured
    // comb even if the on-screen footnote were ever to drift.
    const disclosure = panelId === 'energy'
      ? []
      : figureDisclosure(lastProjections, panelId, state, { isometric: Boolean(panel.isometric) });
    const coregistered = kindOf(lastProjections) !== 'lab' && panelId !== 'energy';
    // In a co-registered frame the on-screen footnote restates every number
    // the structured disclosure already carries; printing both would double
    // the caption. The figure gets the disclosure plus one legend sentence.
    const footnote = coregistered
      ? exportLegend(panelId, lastProjections)
      : notes.map((n) => n.trim()).filter((n) => n && n !== '—').join(' ');

    return {
      panel,
      title: spec.title(),
      footnote,
      selection: lastProjections ? lastProjections.selection : null,
      frame: lastProjections?.frame ?? null,
      disclosure,
    };
  },
});

for (const [scope, dot] of Object.entries(dom.infoDots)) {
  if (!dot) continue;
  dot.addEventListener('click', (event) => {
    event.stopPropagation();
    if (activePopover) { hidePopover(); return; }
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

dom.bannerClose.addEventListener('click', () => {
  for (const message of JSON.parse(dom.banner.dataset.messages || '[]')) {
    dismissed.add(message);
  }
  setHidden('banner', true);
});

new UploadModal({
  onComplete: async () => {
    await loadExperiments({ selectFirst: false });
  },
});

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
  for (const input of document.querySelectorAll('input[name="frame"]')) {
    input.checked = input.value === v.frame;
  }
  for (const input of document.querySelectorAll('input[name="rho_norm"]')) {
    input.checked = input.value === v.rho_norm;
  }
  applyControlAvailability();
  setVal('colormap', v.palette);
  setChecked('opt-lock-scale', v.lock_scale);
  setChecked('opt-undefined-d', v.include_undefined_d);
  setText('channel-caption', currentChannelCaption(null));
}

/* Every element id the update routines write to.
 *
 * Audited once at startup so a markup/script mismatch is named immediately and
 * on screen, rather than surfacing as a null dereference somewhere deep in a
 * render. The helpers in dom.js already make each individual write survivable;
 * this is what turns "some readouts are blank" into a message that says why. */
const REQUIRED_IDS = [
  'stat-events', 'stat-hits', 'stat-edep', 'stat-d', 'stat-nod', 'stat-rho', 'stat-latency',
  'stat-cache', 'banner', 'banner-text', 'banner-close', 'energy-sparse',
  'badge-memory', 'badge-threads', 'badge-exact', 'exact-badge',
  'foot-xy', 'foot-yz', 'foot-xz', 'foot-energy', 'tag-xy', 'tag-energy',
  'title-xy', 'title-yz', 'title-xz', 'info-frame', 'frame-caption',
  'ctl-rho-norm', 'ctl-lock-scale',
  'display-caption', 'channel-caption', 'resolution', 'resolution-readout',
  'resolution-hint', 'display-label-native', 'display-label-continuous',
  'colormap', 'colormap-hint', 'opt-lock-scale', 'opt-undefined-d',
  'experiment-select', 'fit-table', 'metrics', 'model-caption',
  'plot-xy', 'plot-yz', 'plot-xz', 'plot-energy',
  'e1-lo', 'e1-hi', 'e1-fill', 'e1-num-lo', 'e1-num-hi',
  'e2-lo', 'e2-hi', 'e2-fill', 'e2-num-lo', 'e2-num-hi',
  'd-lo', 'd-hi', 'd-fill', 'd-num-lo', 'd-num-hi',
];

async function boot() {
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
}

// A failure anywhere above must not leave a blank page with a silent console.
window.addEventListener('error', (event) => {
  console.error('[calosrv] uncaught', event.error || event.message);
});
window.addEventListener('unhandledrejection', (event) => {
  console.error('[calosrv] unhandled rejection', event.reason);
});

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

boot();
