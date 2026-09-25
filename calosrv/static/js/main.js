/* Application bootstrap and control wiring. */

import { getJson, debounce, ApiError, DEBOUNCE_MS } from './api.js';
import { State } from './state.js';
import { RangeSlider } from './controls/range_slider.js';
import { UploadModal } from './controls/upload.js';
import { ProjectionPanel } from './panels/projection.js';
import { EnergyPanel } from './panels/energy.js';
import { MetricsPanel } from './panels/metrics.js';
import { formatBytes, formatInt, formatNumber, formatSci, floorLabel } from './scale.js';
import { setText, setHtml, setHidden, setVal, setChecked, missingIds } from './dom.js';
import { attachExportMenus } from './export/menu.js';
import { figureDisclosure, ordinal } from './export/disclosure.js';
import { displayOf, kernelPhrase } from './export/caption.js';
import { centroidLegend } from './panels/canonical_overlays.js';

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

/* A canonical depth panel decides its 1:1 aspect from the card size
 * (`depthIsometric`), so a container resize must re-decide it before the
 * panel rebuilds its letterbox - and the footnote, which states the aspect,
 * must follow. The panel calls this from its ResizeObserver. */
for (const id of ['yz', 'xz']) {
  panels[id].onRelayout = (panel) => {
    if (!isCanonical(lastProjections) || !panel.payload) return;
    const next = depthIsometric(panel, panel.payload);
    if (next === panel.isometric) return;
    panel.isometric = next;
    renderCanonicalFootnotes(lastProjections);
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
let pendingWarnings = [];

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

/** Whether a projections payload is in the canonical centre-of-separation frame. */
function isCanonical(payload) {
  return payload?.frame?.kind === 'canonical';
}

const PANEL_TITLES = {
  lab: {
    xy: 'XY Projection — Shower Entry',
    yz: 'YZ Projection — Longitudinal Evolution',
    xz: 'XZ Projection — Lateral Profile',
  },
  canonical: {
    xy: 'X′Y′ Projection — Co-registered Shower Entry',
    yz: 'Y′Z′ Projection — Longitudinal Evolution, canonical frame',
    xz: 'X′Z′ Projection — Lateral Profile, canonical frame',
  },
};

function panelTitle(id, canonical) {
  return PANEL_TITLES[canonical ? 'canonical' : 'lab'][id];
}

/**
 * Whether a depth panel may keep a 1:1 metric aspect.
 *
 * In the laboratory frame the depth panels span 5200 mm against 1210 mm of
 * depth, where a true aspect would be an unusable sliver, so they fill the
 * card. The canonical frame crops each panel to where the energy is, and for
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
  const canonical = isCanonical(payload);
  const frame = canonical ? payload.frame : null;
  // `resolution` is retained in each panel's `lastOpts`, so the exporter
  // names the R and kernel the payload was built with - which the payload
  // guard may have lowered below what the slider says.
  const common = {
    palette, frame, tableName: payload.meta?.table_name,
    resolution: payload.meta?.resolution ?? null,
  };
  const ensemble = overlays.ensemble_axes || {};
  const anchors = canonical ? (overlays.anchors || null) : null;
  const depthBounds = canonical ? { front: 0, back: frame.depth_mm } : null;

  panels.xy.isometric = true;
  panels.xy.render(payload.panels.xy, {
    ...common, centroids: payload.centroids, showVector: true, anchors,
  });
  // The depth panels carry the measured shower axes always, and the individual
  // incident trajectories only when few enough events are selected to read.
  // `showerKey` names which transverse coordinate the panel plots, so the
  // projection of the direction vector picks sin(phi) or cos(phi) correctly.
  // In the canonical frame both give way to the two ensemble axes.
  for (const [id, key] of [['yz', 'y'], ['xz', 'x']]) {
    const panel = panels[id];
    panel.isometric = canonical && depthIsometric(panel, payload.panels[id]);
    panel.render(payload.panels[id], {
      ...common,
      axes: overlays.axes?.[id],
      trajectories: paths,
      showerKey: key,
      ensembleAxes: canonical ? ensemble[id] || null : null,
      ensembleMeta: frame?.ensemble || null,
      anchors,
      depthBounds,
    });
  }
}

async function loadProjections(preview = false) {
  const params = state.projectionParams(preview);
  const payload = await getJson('/api/projections', params, 'projections');
  lastProjections = payload;

  const canonical = isCanonical(payload);
  const overlays = payload.overlays || {};
  renderPanels(payload);
  for (const id of ['xy', 'yz', 'xz']) setText(`title-${id}`, panelTitle(id, canonical));
  if (canonical) {
    renderCanonicalFootnotes(payload);
  } else {
    renderDepthFootnotes(overlays, payload.selection);
  }

  const selection = payload.selection;
  setText('stat-events', formatInt(selection.n_events));
  setText('stat-hits', formatInt(selection.n_hits));
  setText('stat-edep', `${formatSci(selection.e_dep_total, 3)} GeV`);
  setText('stat-d', selection.d.mean !== null
    ? `${formatNumber(selection.d.mean, 0)} mm` : '—');
  setText('stat-nod', formatInt(selection.n_events_no_d));
  // The density reference is the canonical frame's "autoscaled" badge: a ramp
  // relative to the selection's own peak looks identical for a tenth of the
  // energy, so the reader is told which reference the colours are drawn against.
  setText('stat-rho', canonical
    ? (payload.frame.rho?.norm === 'dataset' ? 'dataset peak' : 'selection peak (autoscaled)')
    : '—');
  setText('stat-latency', `${formatNumber(payload.meta.total_ms, 1)} ms`);
  setText('stat-cache', payload.meta.cached ? 'cached' : 'scanned');

  const exact = payload.meta.exact;
  setText('badge-exact', exact ? 'Exact' : 'Preview (sampled)');
  dom.exactBadge.classList.toggle('is-warn', !exact);

  const resolution = payload.meta.resolution;
  const stagger = payload.meta.stagger || {};
  if (canonical) {
    setText('display-caption', canonicalDisplayCaption(resolution, payload.frame));
  } else {
    setText('display-caption', resolution.mode === 'native'
      ? `Native lattice: one bin per calorimeter cell (${resolution.r_x} × ${resolution.r_y} transverse, ${resolution.r_z} depth layers). Every bin is a real cell, so the depth axes carry no empty-bin comb.`
      : `Continuous field: ${resolution.r_x} × ${resolution.r_y} transverse bins by area-weighted splatting, depth locked to ${resolution.r_z} native layers.`);
  }
  setText('channel-caption', channelCaption(
    state.get('channel'), canonical, canonical ? payload.frame : null,
  ));

  const slabTag = `${payload.slab.layers} layers · ${payload.slab.mm.toFixed(0)} mm`;
  if (canonical) {
    // The mean entry separation, with its interval named, where the badge on
    // the plot used to sit over the shower cores. `.sym` keeps the tag's
    // uppercase transform off the symbols.
    const entry = entryTag(payload.frame);
    setHtml('tag-xy', entry ? `${slabTag} · <span class="sym">${entry}</span>` : slabTag);
  } else {
    setText('tag-xy', slabTag);
  }

  if (!canonical) {
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
  }

  // Persistent explanations go to the sidebar info dots; the banner keeps only
  // transient, actionable messages.
  const notices = payload.meta.notices || [];
  if (!canonical && stagger.staggered && resolution.mode === 'native' && stagger.note) {
    notices.push({ scope: 'resolution', text: stagger.note });
  }
  setNotices('resolution', notices);
  setNotices('separation', notices);
  setNotices('frame', notices);
  // Held rather than shown, so `refreshAll` can decide between these and any
  // endpoint failure - a failure must not be overwritten by a routine warning
  // arriving from a panel that happened to succeed.
  pendingWarnings = payload.meta.warnings || [];
  return payload;
}

/**
 * The canonical display caption, read from the payload.
 *
 * Names what a displayed bin is in each mode - the raw 20 mm accumulation bin,
 * or a sample of the kernel reconstruction - with the kernel, its width and
 * the total blur, because a smooth picture that does not say how it was
 * smoothed invites a reader to take its smoothness for the shower's.
 */
function canonicalDisplayCaption(resolution, frame) {
  const recon = frame?.reconstruction ?? null;
  const display = displayOf(resolution, frame);
  const layers = `${resolution.r_z} depth layers`;
  if (display.mode === 'native') {
    const merged = display.merge > 1
      ? `; merged ${display.merge}× to ${num(display.displayPitch, 0)} mm by the payload guard`
      : '';
    return `Native Grid: the raw ${num(resolution.pitch_mm, 0)} mm accumulation bins, no reconstruction `
      + `(${resolution.r_x} × ${resolution.r_y} transverse in the symmetric window, ${layers}) — `
      + `the audit view${merged}.`;
  }
  const kernel = kernelPhrase(display);
  if (!recon || !kernel) {
    // A payload that names no kernel: say what is known, nothing more.
    return `Continuous Field at R = ${resolution.r_x} (${num(resolution.display_pitch_mm, 1)} mm display bins), `
      + `depth locked to ${layers}.`;
  }
  const spread = Number.isFinite(recon.bin_spread_rms_mm)
    ? `${recon.bin_spread_rms_mm.toFixed(1)} mm RMS per ${num(resolution.pitch_mm, 0)} mm bin` : null;
  const blur = recon.blur_rms_mm;
  const total = Number.isFinite(blur?.x) && Number.isFinite(blur?.y)
    ? `total blur ${blur.x.toFixed(1)} × ${blur.y.toFixed(1)} mm RMS with the `
      + `${recon.subsample_k} × ${recon.subsample_k} footprint splat` : null;
  const detail = [spread, total].filter(Boolean).join('; ');
  const gate = Number.isFinite(recon.gaussian_below_n)
    ? ` Gaussian below N = ${recon.gaussian_below_n} events, tent above.` : '';
  return `Continuous Field: conservative ${kernel}${detail ? ` (${detail})` : ''}, x′/y′ only, `
    + `depth native (${layers}); ${num(resolution.display_pitch_mm, 1)} mm display bins `
    + `(R = ${resolution.r_x}).${gate}`;
}

/** ⟨D_entry⟩ with its interval, as HTML for the X′Y′ tag; '' without events. */
function entryTag(frame) {
  const entry = frame?.d_entry ?? {};
  if (!(frame?.n_events > 0) || !Number.isFinite(entry.mean)) return '';
  const symbol = '⟨D<sub>entry</sub>⟩';
  const n = Number.isFinite(entry.n) ? entry.n : frame.n_events;
  if (n === 1) return `${symbol} ${num(entry.mean)} mm (single event)`;
  if (!Number.isFinite(entry.ci95_half)) return `${symbol} ${num(entry.mean)} mm (N = ${formatInt(n)})`;
  return `${symbol} ${num(entry.mean)} ± ${num(entry.ci95_half)} mm (95% t, N = ${formatInt(n)})`;
}

function channelCaption(channel, canonical, frame = null) {
  const floor = floorLabel({ floor_ratio: frame?.reconstruction?.floor_ratio ?? 1e-3 });
  if (channel !== 'density') {
    const base = 'Energy-weighted mean Grad-CAM attention per cell, on a fixed 0–1 linear scale so maps stay comparable across selections.';
    if (!canonical) return base;
    const mode = frame?.reconstruction?.display ?? state.get('display');
    return mode === 'continuous'
      ? `${base} Bins whose reconstructed density falls below ${floor} of ρ_ref are not drawn: the kernel's tails would otherwise paint attention where there is no energy.`
      : `${base} Only bins without hits are left undrawn, so attention measured on real hits is never hidden.`;
  }
  if (!canonical) {
    return 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.';
  }
  const basis = frame?.rho?.basis ?? 'raw 20 mm-grid peak';
  return 'Average hit density ⟨ρ⟩ = ΣE / (N·ΔA) in GeV mm⁻² per event, drawn as a.u. relative to the stated '
    + `reference peak on a three-decade logarithmic ramp. Bins below ${floor} of ρ_ref are not drawn and the `
    + `bottom half decade fades out; ρ_ref is the ${basis}.`;
}

const FRAME_CAPTIONS = {
  canonical:
    'Every selected event is moved by one rigid-body motion: the midpoint of the '
    + 'two back-projected entry points goes to the origin, the A→B separation to '
    + '+x′, the front face to z′ = 0. Panels show the ensemble-averaged energy '
    + 'density, and two ensemble axes replace individual trajectories.',
  lab:
    'Detector coordinates as recorded. The depth panels draw individual '
    + 'trajectories for selections of 50 events or fewer, otherwise the measured '
    + 'shower axes; no averaged direction is drawn in this frame.',
};

/* The display radios' wording per frame. "Native" is the detector lattice in
 * the lab frame and the raw 20 mm accumulation grid in the canonical one, and
 * the two continuous modes are built differently, so the labels say which. */
const DISPLAY_LABELS = {
  lab: {
    native: 'Native Detector Lattice <span class="muted">(hardware truth)</span>',
    continuous: 'Continuous Field <span class="muted">(anti-aliased splatting)</span>',
  },
  canonical: {
    native: 'Native Grid <span class="muted">(raw 20 mm bins, audit)</span>',
    continuous: 'Continuous Field <span class="muted">(kernel reconstruction)</span>',
  },
};

const CANONICAL_RESOLUTION_HINT =
  'R sets the display bins across the X′Y′ window; the kernel, not R, sets the resolution — '
  + 'no detail exists below the 20 mm grid or the 48 mm cell. Depth stays at the native layers.';

/** The lab hint names the active experiment's lattice; set on activation. */
let labResolutionHint = 'Available in Continuous Field mode.';

/**
 * Bring the display radios, their labels and the R control into line with the
 * active frame's display mode.
 *
 * Each frame keeps its own mode (see state.js), so switching frame can change
 * the checked radio without the user touching it. Called on boot and on every
 * frame change, through `applyFrameControls`, and after a display change.
 */
function syncDisplayControls() {
  const canonical = state.get('frame') === 'canonical';
  const labels = DISPLAY_LABELS[canonical ? 'canonical' : 'lab'];
  const display = state.get('display');
  for (const input of document.querySelectorAll('input[name="display"]')) {
    input.checked = input.value === display;
  }
  setHtml('display-label-native', labels.native);
  setHtml('display-label-continuous', labels.continuous);
  dom.resolutionControl.classList.toggle('is-disabled', display !== 'continuous');
  setText('resolution-hint', canonical ? CANONICAL_RESOLUTION_HINT : labResolutionHint);
}

/** Show the controls that belong to the active frame. */
function applyFrameControls(frame) {
  const canonical = frame === 'canonical';
  setHidden('ctl-rho-norm', !canonical);
  setHidden('ctl-lock-scale', canonical);
  setText('frame-caption', FRAME_CAPTIONS[canonical ? 'canonical' : 'lab']);
  syncDisplayControls();
}

function offsetsText(offsets) {
  const pair = offsets?.truth_voxel;
  if (!pair || !pair.a || !pair.b) return '';
  const fmt = (v) => `${v[0] >= 0 ? '+' : ''}${v[0].toFixed(0)}, ${v[1] >= 0 ? '+' : ''}${v[1].toFixed(0)}`;
  return ` The measured ensemble entry centroids sit at (${fmt(pair.a)}) mm from the A anchor and (${fmt(pair.b)}) mm from the B anchor.`;
}

/** A number for prose: fixed decimals, or an em dash when undefined. */
function num(value, digits = 0) {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : '—';
}

/** A fraction as a percentage for prose, or an em dash when undefined. */
function pct(value, digits = 2) {
  return Number.isFinite(value) ? `${(100 * value).toFixed(digits)}%` : '—';
}

/**
 * The fitted display window of one canonical panel, as a phrase.
 *
 * The window is symmetric about the origin, so it is quoted as half-widths,
 * `x′ ±480 mm`, which is what the reader compares against ⟨D_entry⟩/2. Where
 * the floor or the accumulation window set a half-width rather than the
 * percentile, that is said: a floored window is wider than the energy needs.
 */
function windowPhrase(fit, id, sides) {
  const panelFit = fit[id] || {};
  const parts = [];
  const limits = [];
  for (const [side, symbol] of sides) {
    const axis = panelFit[side];
    if (!axis?.applied || !Array.isArray(axis.range)) {
      parts.push(`${symbol} full window`);
      continue;
    }
    if (fit.rule === 'symmetric') {
      const half = Number.isFinite(axis.half_width)
        ? axis.half_width
        : Math.max(Math.abs(axis.range[0]), Math.abs(axis.range[1]));
      parts.push(`${symbol} ±${Math.round(half)} mm`);
    } else {
      parts.push(`${symbol} ${Math.round(axis.range[0])}–${Math.round(axis.range[1])} mm`);
    }
    if (axis.floored) {
      limits.push(`${symbol} held at the ${num(fit.floor_mm)} mm `
        + `${fit.provisional ? 'provisional' : 'two-footprint'} floor`);
    }
    if (axis.clamped) limits.push(`${symbol} clamped to the accumulation window`);
  }
  const [p0, p1] = Array.isArray(fit.percentiles) && fit.percentiles.length >= 2
    ? fit.percentiles : [1, 99];
  const rule = `${fit.rule === 'symmetric' ? 'symmetric ' : ''}${ordinal(p0)}–${ordinal(p1)} energy percentile`;
  return `Window ${parts.join(', ')} (${[rule, ...limits].join('; ')})`;
}

/**
 * Whether a canonical panel's bins are a kernel reconstruction: its own
 * `kernel` when the payload names one ('none' is the raw Native Grid, and a
 * guard's box merge of it), else the frame's display mode.
 */
function reconstructedPanel(panel, continuous) {
  if (typeof panel?.kernel === 'string') return panel.kernel !== 'none';
  return Boolean(continuous);
}

/**
 * The display-floor sentence of one canonical panel.
 *
 * Density: the bins under 10⁻³ of ρ_ref are transparent and the bottom half
 * decade fades, so the reader must be told that the edge of the colour is the
 * floor and not the edge of the shower. Grad-CAM: the masking rule, which
 * differs by display mode - the continuous field masks where the kernel's
 * tails would paint attention over no energy, the Native Grid only where no
 * hit exists.
 */
function floorSentence(panel, continuous, floor) {
  if (!panel) return '';
  if (panel.scale?.unit === 'attention') {
    const mask = panel.attention_mask;
    if (!mask) return '';
    const lead = typeof mask.rule === 'string' && mask.rule
      ? mask.rule.replace(/\.?\s*$/, '.')
      : (continuous
        ? `Attention is not drawn where the reconstructed density is below ${floor} of ρ_ref.`
        : 'Only bins without hits are left undrawn.');
    const counts = mask.cells > 0
      ? ` ${formatInt(mask.cells)} bin${mask.cells === 1 ? '' : 's'} masked`
        + (Number.isFinite(mask.hit_fraction) ? `, holding ${pct(mask.hit_fraction)} of this panel's in-window hits` : '')
        + (Number.isFinite(mask.max_attention) ? `; largest masked attention ${mask.max_attention.toFixed(2)}` : '')
        + '.'
      : '';
    return ` ${lead}${counts}`;
  }
  if (panel.scale?.floor !== 'transparent') return '';
  const energy = reconstructedPanel(panel, continuous) ? 'in-window reconstructed energy' : 'in-window energy';
  const counts = Number.isFinite(panel.below_floor_cells)
    ? ` (${formatInt(panel.below_floor_cells)} bin${panel.below_floor_cells === 1 ? '' : 's'}`
      + (Number.isFinite(panel.below_floor_energy_fraction)
        ? `, ${pct(panel.below_floor_energy_fraction)} of this panel's ${energy}` : '')
      + ')'
    : '';
  return ` Bins below ${floor} of ρ_ref are not drawn${counts}; the bottom half decade fades to `
    + 'transparent, so the edge of the colour is the display floor, not the edge of the shower.';
}

/**
 * Footnotes for the canonical frame.
 *
 * Every number a reader needs to reproduce or discount the picture is on the
 * panel itself: the anchor definition, N and what was excluded, both separation
 * definitions, the density reference, the fitted window and what lies outside
 * it, the display floor, the reconstruction kernel, the sub-cell factor, the
 * measured comb, and the coherence of each axis.
 */
function renderCanonicalFootnotes(payload) {
  const f = payload.frame;
  const rho = f.rho || {};
  const comb = f.comb || {};
  const fit = f.fit || {};
  const recon = f.reconstruction || null;
  const panelPayloads = payload.panels || {};

  if (!(f.n_events > 0)) {
    // Nothing was co-registered: say so, rather than print zeros for means
    // that are undefined and windows that were never fitted.
    const empty =
      `Canonical centre-of-separation frame: no selected event has a defined frame `
      + `(${formatInt(f.n_selected)} selected, ${formatInt(f.n_excluded_no_frame)} without a shower-A `
      + 'centroid or direction). The panels are empty and no ensemble axis is drawn.';
    setText('foot-xy', `${payload.slab.note} ${empty}`);
    setText('foot-yz', empty);
    setText('foot-xz', empty);
    return;
  }

  const continuous = (recon?.display ?? payload.meta?.resolution?.mode) === 'continuous';
  const attention = panelPayloads.xy?.scale?.unit === 'attention';
  const floor = floorLabel({ floor_ratio: recon?.floor_ratio ?? 1e-3 });

  const ref = (value) => `${formatSci(value, 3)} GeV mm⁻² per event`;
  const norm = rho.norm === 'dataset'
    ? `the dataset peak${rho.ref_k && rho.ref_k !== rho.selection_k ? ` (measured with ${rho.ref_k} × ${rho.ref_k} sub-deposits per cell against ${rho.selection_k} × ${rho.selection_k} here)` : ''}`
    : 'this selection’s own peak (autoscaled; switch the density normalisation to compare colours across selections)';
  // Measured after reconstruction when the payload says so: energy the
  // kernel carries across the window edge is energy the reader cannot see.
  const outside = (id) => {
    const after = panelPayloads[id]?.energy_fraction_outside_window;
    const value = Number.isFinite(after) ? after : fit[id]?.energy_fraction_outside;
    return `${pct(value ?? 0)} of the ${id === 'xy' ? 'slab ' : ''}energy lies outside`
      + (Number.isFinite(after) && reconstructedPanel(panelPayloads[id], continuous)
        ? ' after reconstruction' : '');
  };
  // The kernel sentence, with the attenuation of the displayed peak against
  // this panel's raw 20 mm-grid peak - the reference ρ_ref is measured on.
  const kernel = (id) => {
    const note = typeof recon?.note === 'string' && recon.note ? ` ${recon.note}` : '';
    const a = rho.kernel_attenuation?.[id];
    const attenuation = continuous && !attention && Number.isFinite(a)
      ? ` The displayed peak is ${a.toFixed(2)} × this panel's raw 20 mm-grid peak.`
      : '';
    return `${note}${attenuation}`;
  };
  // The interval is named: at N = 2 the Student-t 95% half-width is 12.7
  // standard errors, so a bare "±" would mean whatever the reader assumes.
  const ci = Number.isFinite(f.d_entry?.ci95_half)
    ? ` (95% t-interval of the mean ± ${num(f.d_entry.ci95_half)} mm)`
    : '';
  const base =
    `Canonical centre-of-separation frame: N = ${formatInt(f.n_events)} co-registered event${f.n_events === 1 ? '' : 's'}`
    + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no shower-A centroid or direction)` : '')
    + `; ⟨D_entry⟩ = ${num(f.d_entry?.mean)} mm at the front face${ci}, ⟨D⟩ = ${num(f.d_dataset?.mean)} mm (dataset, 3-D centroid distance).`;
  const provisional = fit.provisional ? ` Fitted ranges are provisional (N = ${f.n_events}).` : '';
  const k = f.subsample_k;
  const splat = ` Cells (${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm) are splatted as ${k} × ${k} sub-deposits on a ${f.pitch_mm} mm grid.`;
  const combText = comb.note ? ` ${comb.staggered ? '⚠ ' : ''}${comb.note}` : '';
  const ill = f.n_ill_conditioned
    ? ` ${formatInt(f.n_ill_conditioned)} event(s) enter closer than ${f.ill_conditioned_threshold_mm} mm apart, so their orientation is effectively random: their energy enters ⟨ρ⟩ averaged over azimuth and their directions enter R̄′, the Rayleigh p and the dispersion band as noise.`
    : '';
  const colour = (value, shared = '') => (attention
    ? 'Colour: energy-weighted mean Grad-CAM attention on a fixed 0–1 scale.'
    : `Colour: average hit density (a.u.) relative to ρ_ref = ${ref(value)}${shared}, ${norm}.`);
  const centroids = centroidLegend(payload.centroids);

  setText('foot-xy',
    `${payload.slab.note} ${base} ${colour(rho.ref?.xy)} `
    + `${windowPhrase(fit, 'xy', [['col', 'x′'], ['row', 'y′']])}; ${outside('xy')}.${provisional}`
    + `${floorSentence(panelPayloads.xy, continuous, floor)}${kernel('xy')} `
    + 'Open diamond and circle: the A and B anchors at ∓⟨D_entry⟩/2; faint bar: sample spread (SD) of '
    + 'D_entry/2 across events; thin dashed rule: the mean entry separation (hover for ⟨D_entry⟩ with its '
    + `95% t-interval).${centroids ? ` ${centroids}` : ''}${offsetsText(f.anchor_offsets)}${splat}${combText}${ill}`);

  const axesText = (f.notes || []).join(' ');
  const marks = f.n_events === 1
    ? ' Dashed lines are this single event’s two incident directions, not an ensemble; no dispersion '
      + 'band or interval can be drawn from one event. Thin rules mark the front and back faces (first and '
      + 'last sampling layer); the transverse outline rotates with each event and has no ensemble image.'
    : ' Dashed lines are the two ensemble shower axes (mean incident direction in this frame); the shaded '
      + 'wedge behind each is the sample spread of the per-event slopes and the thin envelope the 95% '
      + 't-interval of the mean — two different quantities, so two different marks. Individual trajectories '
      + 'are not drawn in this frame. Thin rules mark the front and back faces (first and last sampling '
      + 'layer); the transverse outline rotates with each event and has no ensemble image.';
  const anchorsText = {
    yz: ' The open circle at the origin stands for both anchors, which this panel projects onto one point.',
    xz: ' Open diamond and circle at z′ = 0: the A and B anchors, with a faint bar for the sample spread '
      + '(SD) of D_entry/2.',
  };
  const aspect = (id) => (panels[id].isometric
    ? ' Drawn at a 1:1 metric aspect.'
    : ' Axes carry true extents; the aspect is not 1:1 here.');
  const depthRef = colour(rho.ref?.depth, ' (shared by both depth panels)');

  setText('foot-yz',
    `Transverse spread normal to the shower plane against depth. ${depthRef} `
    + `${windowPhrase(fit, 'yz', [['row', 'y′']])}; ${outside('yz')}.${provisional}`
    + `${floorSentence(panelPayloads.yz, continuous, floor)}${kernel('yz')}`
    + `${anchorsText.yz}${marks} ${axesText}${aspect('yz')}`);
  setText('foot-xz',
    `Lateral profile along the separation against depth. ${depthRef} `
    + `${windowPhrase(fit, 'xz', [['row', 'x′']])}; ${outside('xz')}.${provisional}`
    + `${floorSentence(panelPayloads.xz, continuous, floor)}${kernel('xz')}`
    + `${anchorsText.xz}${marks} ${axesText}${aspect('xz')}`);
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
  parts.push(
    'Solid curves are Gaussian fits and dashed curves mark shower B; a thinner, '
    + 'fainter curve is a thin slice, drawn but not allowed to set the density '
    + 'axis. Below the histogram floor the individual events appear as baseline '
    + 'ticks, with the sample dispersion as a shaded band and the mean with its '
    + '95% confidence interval as a capped whisker — two different quantities, '
    + 'so two different marks. Dotted verticals are the isolated single-shower '
    + 'reference benchmarks at μ ± σ: stated widths, not fits.'
  );
  setText('foot-energy', parts.join(' '));
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
  // Remembered rather than written: the canonical frame shows its own hint,
  // and a later switch to the lab must find this experiment's lattice.
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
    const canonical = state.get('frame') === 'canonical';
    setText('channel-caption', channelCaption(
      input.value, canonical, canonical && isCanonical(lastProjections) ? lastProjections.frame : null,
    ));
    refreshAll();
  });
}

for (const input of document.querySelectorAll('input[name="frame"]')) {
  input.addEventListener('change', () => {
    state.set({ frame: input.value });
    // Also resyncs the display radios: each frame returns to its own mode.
    applyFrameControls(input.value);
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
  xy: { panel: () => panels.xy, title: () => panelTitle('xy', isCanonical(lastProjections)), foot: 'foot-xy' },
  yz: { panel: () => panels.yz, title: () => panelTitle('yz', isCanonical(lastProjections)), foot: 'foot-yz' },
  xz: { panel: () => panels.xz, title: () => panelTitle('xz', isCanonical(lastProjections)), foot: 'foot-xz' },
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
    const canonical = isCanonical(lastProjections) && panelId !== 'energy';
    // In the canonical frame the on-screen footnote restates every number the
    // structured disclosure already carries; printing both would double the
    // caption. The figure gets the disclosure plus one legend sentence.
    const footnote = canonical
      ? canonicalLegend(panelId, lastProjections)
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

/**
 * The mark legend of an exported canonical figure.
 *
 * Same wording as the on-screen footnote, and the centroid sets named by the
 * same `centroidLegend`, so the screen, the footnote and the figure describe
 * one set of marks.
 */
function canonicalLegend(panelId, payload) {
  const axes = 'dashed lines: the two ensemble shower axes; shaded wedge: sample spread of per-event '
    + 'slopes; thin envelope: 95% t-interval of the mean; rules: front and back faces.';
  if (panelId === 'xy') {
    const centroids = centroidLegend(payload?.centroids);
    return 'Open diamond and circle: A and B anchors at ∓⟨D_entry⟩/2; faint bar: sample spread (SD) '
      + 'of D_entry/2 across events; thin dashed rule: the mean entry separation.'
      + (centroids ? ` ${centroids}` : '');
  }
  if (panelId === 'yz') {
    return `Open circle: both anchors, projected onto one point; ${axes}`;
  }
  return 'Open diamond and circle at z′ = 0: A and B anchors, with the faint spread bar; '
    + `${axes}`;
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
  // The display radios follow the active frame's mode; `applyFrameControls`
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
  applyFrameControls(v.frame);
  setVal('colormap', v.palette);
  setChecked('opt-lock-scale', v.lock_scale);
  setChecked('opt-undefined-d', v.include_undefined_d);
  setText('channel-caption', channelCaption(v.channel, v.frame === 'canonical'));
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
  'colormap', 'opt-lock-scale', 'opt-undefined-d',
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
