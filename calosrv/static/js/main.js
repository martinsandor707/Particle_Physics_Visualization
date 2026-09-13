/* Application bootstrap and control wiring. */

import { getJson, debounce, ApiError, DEBOUNCE_MS } from './api.js';
import { State } from './state.js';
import { RangeSlider } from './controls/range_slider.js';
import { UploadModal } from './controls/upload.js';
import { ProjectionPanel } from './panels/projection.js';
import { EnergyPanel } from './panels/energy.js';
import { MetricsPanel } from './panels/metrics.js';
import { formatBytes, formatInt, formatNumber, formatSci } from './scale.js';
import { setText, setHtml, setHidden, setVal, setChecked, missingIds } from './dom.js';

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
  },
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
let pendingWarnings = [];

const DENSITY_EXPLAINER =
  'A probability density is not a probability. The curve integrates to 1.0 over '
  + 'the energy axis, so its height carries units of GeV⁻¹ and legitimately '
  + 'exceeds 1.0 wherever the distribution is narrow — a resolution of '
  + 'σ = 0.4 GeV already peaks near 1.0 GeV⁻¹, and anything sharper peaks higher. '
  + 'A tall peak therefore means good resolution, not a probability above one.';

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

async function loadProjections(preview = false) {
  const params = state.projectionParams(preview);
  const payload = await getJson('/api/projections', params, 'projections');
  lastProjections = payload;

  const palette = state.get('palette');
  const centroids = payload.centroids;
  const overlays = payload.overlays || {};
  const paths = overlays.trajectories || [];

  panels.xy.render(payload.panels.xy, { palette, centroids, showVector: true });
  // The depth panels carry the measured shower axes always, and the individual
  // incident trajectories only when few enough events are selected to read.
  // `showerKey` names which transverse coordinate the panel plots, so the
  // projection of the direction vector picks sin(phi) or cos(phi) correctly.
  panels.yz.render(payload.panels.yz, {
    palette, axes: overlays.axes?.yz, trajectories: paths, showerKey: 'y',
  });
  panels.xz.render(payload.panels.xz, {
    palette, axes: overlays.axes?.xz, trajectories: paths, showerKey: 'x',
  });
  renderDepthFootnotes(overlays, payload.selection);

  const selection = payload.selection;
  setText('stat-events', formatInt(selection.n_events));
  setText('stat-hits', formatInt(selection.n_hits));
  setText('stat-edep', `${formatSci(selection.e_dep_total, 3)} GeV`);
  setText('stat-d', selection.d.mean !== null
    ? `${formatNumber(selection.d.mean, 0)} mm` : '—');
  setText('stat-nod', formatInt(selection.n_events_no_d));
  setText('stat-latency', `${formatNumber(payload.meta.total_ms, 1)} ms`);
  setText('stat-cache', payload.meta.cached ? 'cached' : 'scanned');

  const exact = payload.meta.exact;
  setText('badge-exact', exact ? 'Exact' : 'Preview (sampled)');
  dom.exactBadge.classList.toggle('is-warn', !exact);

  const resolution = payload.meta.resolution;
  const stagger = payload.meta.stagger || {};
  setText('display-caption', resolution.mode === 'native'
    ? `Native lattice: one bin per calorimeter cell (${resolution.r_x} × ${resolution.r_y} transverse, ${resolution.r_z} depth layers). Every bin is a real cell, so the depth axes carry no empty-bin comb.`
    : `Continuous field: ${resolution.r_x} × ${resolution.r_y} transverse bins by area-weighted splatting, depth locked to ${resolution.r_z} native layers.`);

  setText('tag-xy', `${payload.slab.layers} layers · ${payload.slab.mm.toFixed(0)} mm`);

  // The staggered-lattice comb is detector segmentation, not shower structure.
  // Saying so on the panel itself matters more than saying it in a banner,
  // because the panel is what gets screenshotted into a discussion.
  const combNote = stagger.staggered && resolution.mode === 'native'
    ? ` ⚠ ${stagger.note}`
    : '';
  setText('foot-xy',
    `${payload.slab.note} Diamond marks shower A, circle shower B; the dashed `
    + `line is the transverse separation between the ground-truth voxel-weighted `
    + `entry centroids.${combNote}`);

  // Persistent explanations go to the sidebar info dots; the banner keeps only
  // transient, actionable messages.
  const notices = payload.meta.notices || [];
  if (stagger.staggered && resolution.mode === 'native' && stagger.note) {
    notices.push({ scope: 'resolution', text: stagger.note });
  }
  setNotices('resolution', notices);
  setNotices('separation', notices);
  // Held rather than shown, so `refreshAll` can decide between these and any
  // endpoint failure - a failure must not be overwritten by a routine warning
  // arriving from a panel that happened to succeed.
  pendingWarnings = payload.meta.warnings || [];
  return payload;
}

/**
 * Footnotes for the two depth panels.
 *
 * States plainly why an averaged trajectory is absent. The mean resultant
 * length of the incident azimuth is ~0.01 over the full dataset, so a single
 * "average direction" line would point somewhere arbitrary; quoting the
 * measured number on the page is what keeps the omission honest rather than
 * merely silent.
 */
function renderDepthFootnotes(overlays, selection) {
  const coherence = overlays.coherence || {};
  const paths = overlays.trajectories || [];
  const limit = overlays.max_trajectory_events ?? 50;

  let direction;
  if (paths.length) {
    direction =
      ` Dashed lines are the ${paths.length} individual incident trajectories, ` +
      "projected from each event's centroid and (θ, φ) — magenta for shower A, " +
      'blue for shower B. The ensemble shower axis is withheld at this size: ' +
      'averaging the transverse position of a handful of showers that sit in ' +
      'different places has no common centre to converge on.';
  } else {
    const r = coherence.r_a;
    const spread = Number.isFinite(r) ? `R̄ = ${r.toFixed(3)}` : 'near-uniform';
    direction =
      ' Solid lines are the energy-weighted shower axes measured from the binned ' +
      'data on screen — magenta for shower A, blue for shower B. Individual ' +
      `trajectories are drawn only for selections of ${limit} events or fewer; ` +
      `this one holds ${formatInt(selection.n_events)}. No single averaged ` +
      'trajectory is drawn either: the incident azimuth is near-uniform ' +
      `(${spread}), so its mean would point in an arbitrary direction.`;
  }

  setText('foot-yz', `Transverse spread against calorimeter depth.${direction}`);
  setText('foot-xz',
    'Lateral profile against depth, sharing the YZ colour scale so the two may '
    + `be read against one another.${direction}`);
}

async function loadEnergy() {
  const payload = await getJson('/api/energy-distribution', state.filterParams(), 'energy');
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
  setText('foot-energy', parts.join(' ')
    || 'Solid curves are Gaussian core fits; dashed curves mark shower B; '
       + 'dotted verticals are the isolated single-shower references at μ ± σ.');
  return payload;
}

async function loadPerformance() {
  const params = { ...state.filterParams(), model: state.get('model') };
  const payload = await getJson('/api/model-performance', params, 'performance');
  metricsPanel.render(payload, state.get('model'), payload.meta.total_ms);
  return payload;
}

/* ------------------------------------------------------------- orchestration */

const requestPreview = debounce(async () => {
  try {
    await loadProjections(true);
    showBanner(pendingWarnings);
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
    else showBanner(pendingWarnings);
  } finally {
    setBusy(false);
  }
}, DEBOUNCE_MS);

/** Redraw from the payload already in hand, without another request. */
function repaint() {
  if (!lastProjections) return;
  const palette = state.get('palette');
  const overlays = lastProjections.overlays || {};
  const paths = overlays.trajectories || [];
  panels.xy.render(lastProjections.panels.xy, {
    palette, centroids: lastProjections.centroids, showVector: true,
  });
  panels.yz.render(lastProjections.panels.yz, {
    palette, axes: overlays.axes?.yz, trajectories: paths, showerKey: 'y',
  });
  panels.xz.render(lastProjections.panels.xz, {
    palette, axes: overlays.axes?.xz, trajectories: paths, showerKey: 'x',
  });
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
    return `<option value="${escapeHtml(e.table_name)}"${e.status !== 'ready' ? ' disabled' : ''}>`
      + `${escapeHtml(e.display_name)}${suffix}</option>`;
  }).join(''));

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
  setText('resolution-hint',
    `Native transverse lattice is ${nx} cells; depth is fixed at `
    + `${experiment.native_resolution ? experiment.native_resolution.yz[1] : '—'} sampling layers.`);

  refreshAll.flush();
}

/* ------------------------------------------------------------------- wiring */

dom.experiment.addEventListener('change', async () => {
  const experiment = experiments.find((e) => e.table_name === dom.experiment.value);
  if (experiment) await activateExperiment(experiment);
});

for (const input of document.querySelectorAll('input[name="display"]')) {
  input.addEventListener('change', () => {
    const display = input.value;
    state.set({ display });
    dom.resolutionControl.classList.toggle('is-disabled', display !== 'continuous');
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
    setText('channel-caption', input.value === 'density'
      ? 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.'
      : 'Energy-weighted mean Grad-CAM attention per cell, on a fixed 0–1 linear scale so maps stay comparable across selections.');
    refreshAll();
  });
}

for (const input of document.querySelectorAll('input[name="model"]')) {
  input.addEventListener('change', async () => {
    state.set({ model: input.value });
    try {
      await loadPerformance();
    } catch (error) {
      if (error.name !== 'AbortError') reportError(error);
    }
  });
}

dom.colormap.addEventListener('change', () => {
  state.set({ palette: dom.colormap.value });
  // A palette change is a pure repaint of data already held; it must not cost
  // a round trip.
  repaint();
  if (lastEnergy) {
    energyPanel.render(lastEnergy, { palette: state.get('palette'), kind: 'pred' });
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
  const v = state.values;
  for (const input of document.querySelectorAll('input[name="display"]')) {
    input.checked = input.value === v.display;
  }
  dom.resolutionControl.classList.toggle('is-disabled', v.display !== 'continuous');
  setVal('resolution', v.resolution);
  setText('resolution-readout', v.resolution);
  for (const input of document.querySelectorAll('input[name="channel"]')) {
    input.checked = input.value === v.channel;
  }
  for (const input of document.querySelectorAll('input[name="model"]')) {
    input.checked = input.value === v.model;
  }
  setVal('colormap', v.palette);
  setChecked('opt-lock-scale', v.lock_scale);
  setChecked('opt-undefined-d', v.include_undefined_d);
  setText('channel-caption', v.channel === 'density'
    ? 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.'
    : 'Energy-weighted mean Grad-CAM attention per cell, on a fixed 0–1 linear scale so maps stay comparable across selections.');
}

/* Every element id the update routines write to.
 *
 * Audited once at startup so a markup/script mismatch is named immediately and
 * on screen, rather than surfacing as a null dereference somewhere deep in a
 * render. The helpers in dom.js already make each individual write survivable;
 * this is what turns "some readouts are blank" into a message that says why. */
const REQUIRED_IDS = [
  'stat-events', 'stat-hits', 'stat-edep', 'stat-d', 'stat-nod', 'stat-latency',
  'stat-cache', 'banner', 'banner-text', 'banner-close', 'energy-sparse',
  'badge-memory', 'badge-threads', 'badge-exact', 'exact-badge',
  'foot-xy', 'foot-yz', 'foot-xz', 'foot-energy', 'tag-xy', 'tag-energy',
  'display-caption', 'channel-caption', 'resolution', 'resolution-readout',
  'resolution-hint', 'colormap', 'opt-lock-scale', 'opt-undefined-d',
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
