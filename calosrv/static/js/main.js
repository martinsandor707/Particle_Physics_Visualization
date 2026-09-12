/* Application bootstrap and control wiring. */

import { getJson, debounce, ApiError, DEBOUNCE_MS } from './api.js';
import { State } from './state.js';
import { RangeSlider } from './controls/range_slider.js';
import { UploadModal } from './controls/upload.js';
import { ProjectionPanel } from './panels/projection.js';
import { EnergyPanel } from './panels/energy.js';
import { MetricsPanel } from './panels/metrics.js';
import { formatBytes, formatInt, formatNumber, formatSci } from './scale.js';

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
const energyPanel = new EnergyPanel('plot-energy', 'fit-table');
const metricsPanel = new MetricsPanel('metrics', 'model-caption');

const dom = {
  experiment: document.getElementById('experiment-select'),
  banner: document.getElementById('banner'),
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

/* ------------------------------------------------------------------ sliders */

const sliders = {
  e1: new RangeSlider({
    loId: 'e1-lo', hiId: 'e1-hi', fillId: 'e1-fill', readoutId: 'e1-readout',
    format: (v) => `${v.toFixed(2)} GeV`,
    onInput: ([lo, hi]) => { state.set({ e1_min: lo, e1_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.set({ e1_min: lo, e1_max: hi }); refreshAll(); },
  }),
  e2: new RangeSlider({
    loId: 'e2-lo', hiId: 'e2-hi', fillId: 'e2-fill', readoutId: 'e2-readout',
    format: (v) => `${v.toFixed(2)} GeV`,
    onInput: ([lo, hi]) => { state.set({ e2_min: lo, e2_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.set({ e2_min: lo, e2_max: hi }); refreshAll(); },
  }),
  d: new RangeSlider({
    loId: 'd-lo', hiId: 'd-hi', fillId: 'd-fill', readoutId: 'd-readout',
    format: (v) => `${v.toFixed(0)} mm`,
    onInput: ([lo, hi]) => { state.set({ d_min: lo, d_max: hi }); requestPreview(); },
    onCommit: ([lo, hi]) => { state.set({ d_min: lo, d_max: hi }); refreshAll(); },
  }),
};

/* ------------------------------------------------------------------ loading */

function setBusy(busy) {
  for (const panel of Object.values(panels)) panel.setBusy(busy);
  energyPanel.setBusy(busy);
}

function showBanner(messages, isError = false) {
  const list = (messages || []).filter(Boolean);
  if (!list.length) {
    dom.banner.hidden = true;
    return;
  }
  dom.banner.hidden = false;
  dom.banner.classList.toggle('is-error', isError);
  dom.banner.innerHTML = list.length === 1
    ? escapeHtml(list[0])
    : `<ul>${list.map((m) => `<li>${escapeHtml(m)}</li>`).join('')}</ul>`;
}

/* -------------------------------------------------------------- projections */

async function loadProjections(preview = false) {
  const params = state.projectionParams(preview);
  const payload = await getJson('/api/projections', params, 'projections');
  lastProjections = payload;

  const palette = state.get('palette');
  const centroids = payload.centroids;

  panels.xy.render(payload.panels.xy, { palette, centroids, showVector: true });
  panels.yz.render(payload.panels.yz, { palette });
  panels.xz.render(payload.panels.xz, { palette });

  const selection = payload.selection;
  dom.statEvents.textContent = formatInt(selection.n_events);
  dom.statHits.textContent = formatInt(selection.n_hits);
  dom.statEdep.textContent = `${formatSci(selection.e_dep_total, 3)} GeV`;
  dom.statD.textContent = selection.d.mean !== null
    ? `${formatNumber(selection.d.mean, 0)} mm` : '—';
  dom.statNoD.textContent = formatInt(selection.n_events_no_d);
  dom.statLatency.textContent = `${formatNumber(payload.meta.total_ms, 1)} ms`;
  dom.statCache.textContent = payload.meta.cached ? 'cached' : 'scanned';

  const exact = payload.meta.exact;
  dom.badgeExact.textContent = exact ? 'Exact' : 'Preview (sampled)';
  dom.exactBadge.classList.toggle('is-warn', !exact);

  const resolution = payload.meta.resolution;
  const stagger = payload.meta.stagger || {};
  dom.displayCaption.textContent = resolution.mode === 'native'
    ? `Native lattice: one bin per calorimeter cell (${resolution.r_x} × ${resolution.r_y} transverse, ${resolution.r_z} depth layers). Every bin is a real cell, so the depth axes carry no empty-bin comb.`
    : `Continuous field: ${resolution.r_x} × ${resolution.r_y} transverse bins by area-weighted splatting, depth locked to ${resolution.r_z} native layers.`;

  dom.tagXy.textContent = `${payload.slab.layers} layers · ${payload.slab.mm.toFixed(0)} mm`;

  // The staggered-lattice comb is detector segmentation, not shower structure.
  // Saying so on the panel itself matters more than saying it in a banner,
  // because the panel is what gets screenshotted into a discussion.
  const combNote = stagger.staggered && resolution.mode === 'native'
    ? ` ⚠ ${stagger.note}`
    : '';
  dom.footXy.textContent =
    `${payload.slab.note} Diamond marks shower A, circle shower B; the dashed ` +
    `line is the transverse separation between the ground-truth voxel-weighted ` +
    `entry centroids.${combNote}`;

  showBanner(payload.meta.warnings);
  return payload;
}

async function loadEnergy() {
  const payload = await getJson('/api/energy-distribution', state.filterParams(), 'energy');
  lastEnergy = payload;
  energyPanel.render(payload, { palette: state.get('palette'), kind: 'pred' });

  const calibration = payload.calibration;
  dom.tagEnergy.textContent = calibration.applied ? 'calibrated' : 'deposited';
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
  dom.footEnergy.textContent = parts.join(' ') ||
    'Solid curves are Gaussian core fits; dashed curves are the isolated single-shower references.';
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
  } catch (error) {
    if (error.name !== 'AbortError') reportError(error);
  }
}, DEBOUNCE_MS);

const refreshAll = debounce(async () => {
  requestPreview.cancel();
  setBusy(true);
  try {
    await Promise.all([loadProjections(false), loadEnergy(), loadPerformance()]);
  } catch (error) {
    if (error.name !== 'AbortError') reportError(error);
  } finally {
    setBusy(false);
  }
}, DEBOUNCE_MS);

/** Redraw from the payload already in hand, without another request. */
function repaint() {
  if (!lastProjections) return;
  const palette = state.get('palette');
  panels.xy.render(lastProjections.panels.xy, {
    palette, centroids: lastProjections.centroids, showVector: true,
  });
  panels.yz.render(lastProjections.panels.yz, { palette });
  panels.xz.render(lastProjections.panels.xz, { palette });
}

function reportError(error) {
  const message = error instanceof ApiError ? error.message : String(error);
  showBanner([message], true);
  console.error(error);
}

/* --------------------------------------------------------------- experiments */

async function loadExperiments({ selectFirst = false } = {}) {
  const payload = await getJson('/api/experiments', {}, 'experiments');
  experiments = payload.experiments;

  const compute = payload.compute;
  dom.badgeMemory.textContent = `${compute.duckdb_memory_gb} GB`;
  dom.badgeThreads.textContent = compute.threads;

  dom.experiment.innerHTML = experiments.map((e) => {
    const suffix = e.status === 'ready'
      ? ` — ${formatInt(e.n_events)} events`
      : ` — ${e.status}`;
    return `<option value="${escapeHtml(e.table_name)}"${e.status !== 'ready' ? ' disabled' : ''}>` +
      `${escapeHtml(e.display_name)}${suffix}</option>`;
  }).join('');

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
  dom.experiment.value = chosen.table_name;
  await activateExperiment(chosen);
  return chosen;
}

async function activateExperiment(experiment) {
  activeExperiment = experiment;
  state.set({ table_name: experiment.table_name }, { silent: true });

  const bounds = experiment.bounds;
  state.adoptBounds(bounds);

  const v = state.values;
  sliders.e1.setBounds(bounds.e1[0], bounds.e1[1], [v.e1_min, v.e1_max]);
  sliders.e2.setBounds(bounds.e2[0], bounds.e2[1], [v.e2_min, v.e2_max]);

  const hasD = bounds.d[0] !== null && bounds.d[1] !== null;
  sliders.d.setDisabled(!hasD, 'N/A');
  if (hasD) sliders.d.setBounds(bounds.d[0], bounds.d[1], [v.d_min, v.d_max]);

  // The resolution slider's useful ceiling is set by the detector: beyond the
  // native cell count no further detail exists, though splatting keeps the
  // image free of gaps.
  const nx = experiment.native_resolution ? experiment.native_resolution.xy[1] : 200;
  dom.resolution.max = Math.max(100, Math.min(400, nx * 2));
  dom.resolutionHint.textContent =
    `Native transverse lattice is ${nx} cells; depth is fixed at ` +
    `${experiment.native_resolution ? experiment.native_resolution.yz[1] : '—'} sampling layers.`;

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
  dom.resolutionReadout.textContent = dom.resolution.value;
});
dom.resolution.addEventListener('change', () => {
  state.set({ resolution: Number(dom.resolution.value) });
  refreshAll();
});

for (const input of document.querySelectorAll('input[name="channel"]')) {
  input.addEventListener('change', () => {
    state.set({ channel: input.value });
    dom.channelCaption.textContent = input.value === 'density'
      ? 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.'
      : 'Energy-weighted mean Grad-CAM attention per cell, on a fixed 0–1 linear scale so maps stay comparable across selections.';
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
  dom.resolution.value = v.resolution;
  dom.resolutionReadout.textContent = v.resolution;
  for (const input of document.querySelectorAll('input[name="channel"]')) {
    input.checked = input.value === v.channel;
  }
  for (const input of document.querySelectorAll('input[name="model"]')) {
    input.checked = input.value === v.model;
  }
  dom.colormap.value = v.palette;
  dom.lockScale.checked = v.lock_scale;
  dom.undefinedD.checked = v.include_undefined_d;
  dom.channelCaption.textContent = v.channel === 'density'
    ? 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.'
    : 'Energy-weighted mean Grad-CAM attention per cell, on a fixed 0–1 linear scale so maps stay comparable across selections.';
}

async function boot() {
  restoreControlsFromState();
  try {
    await loadExperiments({ selectFirst: false });
  } catch (error) {
    reportError(error);
  }
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

boot();
