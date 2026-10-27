/* What the Physics page shows for one experiment, read from its capability block.
 *
 * GET /api/experiments publishes, for every experiment, the block that
 * calosrv/query/capabilities.py builds: the experiment's kind, how many
 * showers an event holds, which filter axes, frames, channels and networks
 * it has, and one gate per card with the server's own sentence when a gate is
 * shut. That module owns every gate; this one only reads the block and turns
 * it into the page's plan (`page1Plan`), so a view the data cannot serve is
 * never offered - and when it is shut for a reason the operator can act on,
 * a stale derived table say, the card says so in the server's words instead
 * of disappearing.
 *
 * Pure and DOM-free: Node-tested against the recorded catalogue of all three
 * kinds (tests/fixtures/payloads/experiments.json), which is the backend's
 * payload and so the contract (where the design text and the payload
 * disagree, the payload wins).
 *
 * An experiment without the block - a server from before it existed - keeps
 * the two-shower contract and the fallbacks the page applied before the block
 * existed (frames ['lab', 'canonical'], channels ['density', 'gradcam'],
 * models ['segmentation']), and gets no physics cards.
 *
 * The Models page reads the same block (`page2Plan`): which of its sections
 * and cards the experiment can serve, the frames each of them draws in, the
 * XGBoost model runs paired with it, and what its 3-D views offer.
 *
 * Every text here is English and writes a negative number with U+2212.
 */

import { FRAMES, apiFrame } from './state.js';
import { offeredFrames, SINGLE_SHOWER_FRAME_LABELS, frameLabel } from './labels.js';

/** The three input kinds the server ingests. */
export const KIND = Object.freeze({
  TWO: 'two_shower_hits',
  ONE: 'single_shower_hits',
  EVENTS: 'single_shower_events',
});

/* Each filter axis the sidebar can carry, as the selection sentence, the
 * figure name and the sliders name it. `label` and `hint` are null where the
 * static markup already says it: only a single-shower experiment relabels the
 * E₁ control, at runtime, so the markup and its pinned strings never change. */
export const TWO_SHOWER_AXES = Object.freeze([
  Object.freeze({
    key: 'e1', symbol: 'E₁', token: 'E1-', unit: 'GeV', digits: 2, step: 0.05,
    label: null, hint: null, aria: null,
  }),
  Object.freeze({
    key: 'e2', symbol: 'E₂', token: 'E2-', unit: 'GeV', digits: 2, step: 0.05,
    label: null, hint: null, aria: null,
  }),
  Object.freeze({
    key: 'd', symbol: 'D', token: 'D-', unit: 'mm', digits: 0, step: 1,
    label: null, hint: null, aria: null,
  }),
]);

/* A single-shower experiment has one filter: the shower's own incident
 * momentum, sent as e1_min / e1_max (the server's filter-key contract). */
export const SINGLE_SHOWER_AXES = Object.freeze([
  Object.freeze({
    key: 'e1', symbol: 'p', token: 'p-', unit: 'GeV', digits: 2, step: 0.05,
    label: 'p — incident momentum [GeV]',
    hint: 'True incident momentum of the shower (incoming_momentum).',
    aria: 'p',
  }),
]);

/** The physics section's cards, in page order (card id = the server's gate). */
export const PHYSICS_CARD_IDS = Object.freeze([
  'profile-w', 'profile-r',
  'response-b1', 'response-b2', 'response-res', 'response-b3',
  'distribution', 'correlation', 'statistics',
]);

/** Cards that read hits; an event-level experiment has none to read. */
const HIT_CARDS = new Set(['profile-w', 'profile-r', 'correlation', 'statistics']);

/** The 2 x 2 diagnostic's plot 4 titles: the energy panel's (pinned) and B3's. */
export const PLOT4_TITLES = Object.freeze({
  'energy-d': 'Reconstructed Energy vs. Separation D',
  'response-b3': 'Response vs. Incident Momentum p',
});

/* CLAUDE.md section 3 ("Missing Column Handling"): an experiment without
 * model predictions falls back to the ground-truth baselines and says so in a
 * prominent banner. The server's own reason leads; this sentence follows. */
export const MISSING_PREDICTIONS =
  'No model predictions in this experiment: the panels show ground-truth baselines only — '
  + 'deposited energy, incident momenta and their distributions. The attention channels, the '
  + 'reconstruction-model cards and the network energy reconstruction are unavailable, and no '
  + 'prediction is substituted for them.';

/** What the events-only kind shows in place of the 2 x 2 diagnostic. */
export const EVENTS_ONLY_TITLE = 'No hits to project';
export const EVENTS_ONLY_NOTICE =
  'This experiment holds event-level features only (the 59-column aggregate): it has no hits.';
export const EVENTS_ONLY_FOLLOW =
  'There is nothing to draw in the spatial panels. The response and distribution cards below '
  + 'are computed from its per-event table.';
/* Why the sidebar is shorter for this kind (Martin's Phase 6 decision): the
 * groups that steer only the spatial panels are hidden, not left disabled. */
export const EVENTS_ONLY_CONTROLS =
  'The reference-frame, spatial-resolution, display-channel and colour-map controls steer the '
  + 'spatial panels only, so they are hidden for this experiment.';

/** Fallback when the server names no reason for a shut gate. */
const NO_REASON = 'Not available for this experiment.';

/** The Separation-Aligned frame needs two showers; the server's own sentence is preferred. */
export const CANONICAL_SINGLE_REASON =
  'Needs two showers per event: the Separation-Aligned (D-Frame) is built from the A→B '
  + 'separation of the two entry points.';

/* Gates a server without the capability block serves: the 2 x 2 and the views
 * built on it, never a physics card. */
const LEGACY_GATES = new Set([
  'xy', 'yz', 'xz', 'energy', 'window-axis', 'event-inspector', 'compare',
  'frame-lab', 'frame-trans', 'frame-local', 'frame-canonical',
]);

/** The distribution quantities by kind: the hit quantities need hits. */
const SHOWER_QUANTITIES = ['theta', 'phi', 'p'];
const HIT_QUANTITIES = ['u', 'v', 'w', 'energy'];

/**
 * The capability block normalised: every field present, the two-shower
 * contract (and today's fallbacks) where the server sent no block.
 */
export function capabilitiesOf(experiment) {
  const caps = experiment?.capabilities ?? null;
  const legacy = caps === null;
  const nShowers = caps?.n_showers === 1 ? 1 : 2;
  return {
    legacy,
    kind: caps?.kind ?? KIND.TWO,
    kindLabel: caps?.kind_label ?? 'two-shower hits',
    nShowers,
    showers: Array.isArray(caps?.showers) && caps.showers.length
      ? [...caps.showers] : (nShowers === 1 ? ['a'] : ['a', 'b']),
    hasHits: caps?.has_hits ?? true,
    networks: Array.isArray(caps?.networks) ? [...caps.networks]
      : (experiment?.models ?? ['segmentation']),
    filters: Array.isArray(caps?.filters) && caps.filters.length
      ? [...caps.filters] : ['e1', 'e2', 'd'],
    frames: experiment?.frames ?? ['lab', 'canonical'],
    coordSystems: experiment?.coord_systems ?? ['lab'],
    channels: experiment?.channels ?? ['density', 'gradcam'],
    models: experiment?.models ?? ['segmentation'],
    panels: caps?.panels ?? null,
    reasons: caps?.reasons ?? {},
    derived: caps?.derived ?? null,
    pages: caps?.pages ?? null,
  };
}

/** Whether a normalised block opens one gate. */
function gateOf(caps, id) {
  return caps.panels ? Boolean(caps.panels[id]) : LEGACY_GATES.has(id);
}

/** The server's sentence for a shut gate. */
function reasonOf(caps, id) {
  return caps.reasons[id] ?? NO_REASON;
}

/** The experiment's kind as the interface names it ('single-shower hits'). */
export function kindLabel(experiment) {
  return capabilitiesOf(experiment).kindLabel;
}

/** The filter axes the experiment carries, as descriptors. */
export function filterAxes(experiment) {
  const caps = capabilitiesOf(experiment);
  const table = caps.nShowers === 1 ? SINGLE_SHOWER_AXES : TWO_SHOWER_AXES;
  const axes = table.filter((axis) => caps.filters.includes(axis.key));
  return axes.length ? axes : [table[0]];
}

/**
 * The Physics page's plan for one experiment.
 *
 * - `spatial`: whether the 2 x 2 diagnostic draws at all; the events-only
 *   kind shows `notice` in its place.
 * - `plot4`: what the 2 x 2's fourth card draws - the separation-sliced
 *   energy reconstruction ('energy-d'), the momentum-sliced response grid
 *   ('response-b3', a single-shower kind with no network), or nothing.
 * - `physics`: the cards of the section below, in order; `disabled` maps a
 *   card whose gate is shut to the server's reason, shown on the card.
 * - `frames`: the frames offered, the server's reason for each one that is
 *   not, and the single-shower relabelling of the frame tier.
 * - `banner`: the missing-predictions banner (CLAUDE.md section 3), or null.
 * - `stale`: the derived-table notice when the experiment was built by an
 *   earlier release and can be rebuilt from its archive.
 */
export function page1Plan(experiment) {
  const caps = capabilitiesOf(experiment);
  const gate = (id) => gateOf(caps, id);
  const single = caps.nShowers === 1;
  const spatial = ['xy', 'yz', 'xz'].some(gate);

  let plot4 = null;
  if (spatial && gate('energy')) plot4 = 'energy-d';
  else if (spatial && single && gate('response-b3')) plot4 = 'response-b3';
  const plot4Reason = plot4 ? null : (spatial ? reasonOf(caps, single ? 'response-b3' : 'energy') : null);

  // A single-shower kind draws B3 as plot 4 too, always on the notebook's six
  // windows, which fit the 2 x 2 cell; the full-width card below keeps the
  // 1 GeV bins and grows to fit every slice (Martin's Phase 6 decision).
  const physics = caps.panels ? PHYSICS_CARD_IDS.filter((id) => !(HIT_CARDS.has(id) && !caps.hasHits)) : [];
  const disabled = {};
  for (const id of physics) if (!gate(id)) disabled[id] = reasonOf(caps, id);

  const offered = offeredFrames(experiment);
  const frameReasons = {};
  for (const frame of FRAMES) {
    if (!offered.includes(frame)) frameReasons[frame] = caps.reasons[`frame-${frame}`] ?? NO_REASON;
  }

  const networks = caps.networks.length > 0;
  const missing = networks ? null
    : `${caps.reasons.energy ? `${caps.reasons.energy} ` : ''}${MISSING_PREDICTIONS}`;
  const stale = caps.derived?.status === 'stale' ? {
    notice: caps.derived.notice ?? null,
    version: caps.derived.version ?? null,
    current: caps.derived.current ?? null,
  } : null;

  return {
    kind: caps.kind,
    kindLabel: caps.kindLabel,
    legacy: caps.legacy,
    nShowers: caps.nShowers,
    showers: caps.showers,
    hasHits: caps.hasHits,
    axes: filterAxes(experiment),
    spatial,
    notice: spatial ? null : {
      title: EVENTS_ONLY_TITLE,
      text: `${caps.reasons.xy ?? EVENTS_ONLY_NOTICE} ${EVENTS_ONLY_FOLLOW} ${EVENTS_ONLY_CONTROLS}`,
    },
    plot4,
    plot4Title: plot4 ? PLOT4_TITLES[plot4] : null,
    plot4Reason,
    frames: {
      offered,
      disabled: frameReasons,
      transPrimary: single && offered.includes('trans'),
      labels: single ? SINGLE_SHOWER_FRAME_LABELS : null,
    },
    coordSystems: [...caps.coordSystems],
    channels: [...caps.channels],
    models: [...caps.models],
    performance: networks,
    banner: missing,
    status: { d: caps.filters.includes('d') },
    eventInspector: spatial && gate('event-inspector'),
    compare: spatial && gate('compare'),
    windowAxis: spatial && gate('window-axis'),
    physics,
    disabled,
    reasons: { ...caps.reasons },
    quantities: caps.hasHits ? [...SHOWER_QUANTITIES, ...HIT_QUANTITIES] : [...SHOWER_QUANTITIES],
    stale,
  };
}

/**
 * The frames a plan's sidebar radios offer: every offered frame except the
 * legacy per-shower translated one (API `trans`), which on two showers has no
 * radio of its own - a link or a saved default opens it - and on a single
 * shower is that kind's own Translated frame.
 */
export function radioFrames(plan) {
  const offered = plan?.frames?.offered ?? [];
  return offered.filter((frame) => frame !== 'trans' || Boolean(plan.frames.transPrimary));
}

/**
 * The frame carried across a switch to an experiment of another kind (Martin's
 * Phase 6 decision), as `{frame, notice}`; `notice` is null when nothing moved.
 *
 * Local means the same on every kind with hits and carries over both ways. A
 * frame the new experiment's radios do not offer - the D-frame on a single
 * shower, a single shower's Translated, which is the legacy per-shower frame
 * on two showers - falls back to Absolute, with one line saying so. Opening a
 * `#frame=trans` link or a saved default is not a switch, so the legacy frame
 * still opens that way; nor is a switch between two experiments of one kind,
 * nor one to the event-level kind, whose frame tier is hidden. Pure.
 */
export function carriedFrame(previousPlan, plan, frame) {
  const kept = { frame, notice: null };
  if (!previousPlan || !plan?.spatial || previousPlan.kind === plan.kind) return kept;
  const radios = radioFrames(plan);
  if (radios.includes(frame)) return kept;
  const fallback = radios.includes('lab') ? 'lab' : (radios[0] ?? null);
  if (!fallback) return kept;
  return {
    frame: fallback,
    notice: `${frameLabel(frame, previousPlan.nShowers ?? 2)} is not offered for this experiment `
      + `(${plan.kindLabel}); showing ${frameLabel(fallback, plan.nShowers ?? 2)} instead.`,
  };
}

/* ------------------------------------------------------- the Models page */

/** The Models page's sections, in page order, and the cards each holds (card id = the server's gate). */
export const PAGE2_SECTIONS = Object.freeze({
  perf: Object.freeze(['perf-bins', 'pred-truth', 'pred-residuals']),
  xgb: Object.freeze(['xgb-cv', 'xgb-binary', 'xgb-surrogate', 'xgb-importance']),
  features: Object.freeze(['feat-table', 'feat-corr', 'feat-hist', 'feat-hist2d']),
  primaries: Object.freeze(['prim-rate']),
  voxels: Object.freeze(['vox-event', 'vox-ensemble']),
});

/* The XGBoost cards share one gate: the experiment's analysis is done and
 * current (calosrv/modelruns, xgboost.md section 2.4). */
const XGB_CARDS = new Set(PAGE2_SECTIONS.xgb);

/* CLAUDE.md section 3 on the Models page: an experiment without network
 * predictions shows ground truth and says so prominently. Where an XGBoost
 * regressor pairs with the experiment, its holdout predictions are real model
 * outputs and the performance cards draw them; nothing is substituted for
 * the networks either way. */
export const MODELS_MISSING_PREDICTIONS =
  'No reconstruction-network predictions in this experiment: the network performance cards and the '
  + 'attention channels of the 3-D views are unavailable, and no prediction is substituted for them. '
  + 'The feature explorer, the primaries and the 3-D energy views show ground truth only.';
export const MODELS_XGB_INSTEAD =
  'No reconstruction-network predictions in this experiment. The performance cards draw the XGBoost '
  + 'regressor paired with it, on its 20 % validation split; no network prediction is substituted.';

/* The XGBoost notice of an experiment no model run pairs with; the server's
 * own sentence follows it. */
export const XGB_NOTICE =
  'XGBoost views (E1 cross-validation, E3 99 : 1 binary thresholding, E4 depth-3 surrogate tree, '
  + 'E5 gain importance) are shown for an event-level aggregate paired with the XGBoost models of '
  + 'its species and seed; none pairs with this experiment.';

/* Why the hit sections are absent for the event-level kind. */
export const MODELS_EVENTS_ONLY =
  'This experiment holds event-level features only: the primaries and the 3-D views need hits, so '
  + 'they are not shown.';

/* The frames each of the Models page's views draws in. The shared `frame`
 * key may name a frame a view has no data for; the view then draws in its
 * fallback and says so on its card, and the fallback is never written back to
 * the link (frontend.md section 4.2). */
const VIEW_FRAMES = Object.freeze({
  // Per-event features are summed in the absolute, per-shower translated and
  // Local frames; the D-frame has none (calosrv features `group1_frames`).
  features: Object.freeze({ frames: ['lab', 'trans', 'local'], fallback: 'lab' }),
  // The 3-D event cubes: exact cells in lab and trans, splatted in local and
  // the D-frame.
  event: Object.freeze({ frames: ['lab', 'trans', 'local', 'canonical'], fallback: 'lab' }),
  // The ensemble cloud is co-registered only: trans has no 3-D accumulation.
  ensemble: Object.freeze({ frames: ['local', 'canonical'], fallback: 'local' }),
});

/** Why a view draws in another frame than the one selected, by view. */
const FALLBACK_WHY = {
  features: 'per-event features are summed in the Absolute, Per-shower translated and Local frames only',
  event: 'the 3-D event view is not offered in that frame for this experiment',
  ensemble: 'the ensemble cloud is accumulated in the co-registered frames only (Local and the D-frame)',
};

/**
 * The frame one Models-page view draws in for the selected `frame`.
 *
 * `use` is 'features', 'event', 'ensemble' or 'network'. A network reads the
 * input frame it was trained on: the D-frame uses the absolute-frame
 * networks (as on the Physics page), which is the definition of that frame's
 * networks rather than a fallback. Returns `{frame, fallback, note}`, `note`
 * the one sentence a card states when the view draws elsewhere. Pure.
 */
export function viewFrame(use, frame, offered = FRAMES, nShowers = 2) {
  if (use === 'network') {
    return { frame: apiFrame(frame).coord_system, fallback: false, note: null };
  }
  const spec = VIEW_FRAMES[use];
  if (!spec) return { frame, fallback: false, note: null };
  const allowed = spec.frames.filter((f) => offered.includes(f));
  if (allowed.includes(frame)) return { frame, fallback: false, note: null };
  const to = allowed.includes(spec.fallback) ? spec.fallback : (allowed[0] ?? null);
  if (!to) return { frame: null, fallback: true, note: null };
  return {
    frame: to,
    fallback: true,
    note: `Drawn in ${frameLabel(to, nShowers)}: ${FALLBACK_WHY[use]}, so ${frameLabel(frame, nShowers)} `
      + 'does not apply here. The selected frame is kept for the other views.',
  };
}

/** The XGBoost output label a model run names ('incoming_phi' -> 'phi'). */
function shortLabel(label) {
  const text = String(label ?? '');
  if (/phi/.test(text)) return 'phi';
  if (/theta/.test(text)) return 'theta';
  if (/momentum/.test(text)) return 'momentum';
  return text;
}

/**
 * The XGBoost block of a plan: the tasks the paired runs cover, each task's
 * output labels, and where the analysis stands - 'ready' (the gate is open),
 * 'pending' (queued or running), 'failed', 'stale', or 'none' (nothing pairs).
 */
function xgbBlock(caps, runs, open) {
  const tasks = [...new Set(runs.map((run) => run.task).filter(Boolean))];
  const labels = {};
  for (const run of runs) {
    if (!run.task) continue;
    labels[run.task] = Array.isArray(run.labels) ? run.labels.map(shortLabel) : [];
  }
  const statuses = runs.map((run) => run.status);
  let status = 'none';
  if (runs.length) {
    if (open) status = 'ready';
    else if (statuses.includes('failed')) status = 'failed';
    else if (statuses.some((s) => s === 'queued' || s === 'running')) status = 'pending';
    else if (statuses.includes('stale')) status = 'stale';
    else status = 'pending';
  }
  return {
    tasks, labels, status, runs,
    reason: open ? null : reasonOf(caps, 'xgboost'),
    splitReproduced: runs.every((run) => run.split_reproduced !== false),
  };
}

/**
 * The Models page's plan for one experiment.
 *
 * - `sections`: which of the page's sections are on show. The performance
 *   section shows when a network (or a paired XGBoost regressor, through the
 *   same gates) can serve one of its cards; the XGBoost section when a model
 *   run pairs with the experiment; the features section when its cards can
 *   be served or a rebuild would open them; the primaries and the 3-D views
 *   wherever there are hits (a shut card says why).
 * - `cards`: `{shown, enabled, reason}` for every card, the server's sentence
 *   on a shut one.
 * - `models` / `networks`: the reconstruction networks; `frames`: the frames
 *   the sidebar offers and the server's reason for each one it does not;
 *   `featureFrames`: the frames the feature explorer is served in (the
 *   server's `group1_frames`; an event-level aggregate, which has no sidebar
 *   frame control, offers them on the feature cards themselves).
 * - `xgb`: the paired model runs (`model_runs`), their tasks and labels, and
 *   where the analysis stands.
 * - `voxels`: what the 3-D views offer (VoxelSection.applyPlan reads it).
 * - `banner`: the missing-predictions banner; `xgbNotice`: the XGBoost notice
 *   (null when a run pairs); `notices`: the kind's own lines; `stale`: the
 *   derived-table notice.
 */
export function page2Plan(experiment) {
  const caps = capabilitiesOf(experiment);
  const gate = (id) => (caps.panels ? Boolean(caps.panels[id]) : false);
  const single = caps.nShowers === 1;
  const runs = Array.isArray(experiment?.capabilities?.model_runs) ? experiment.capabilities.model_runs : [];
  const xgbOpen = gate('xgboost') && runs.length > 0;
  const staleNotice = caps.derived?.status === 'stale' ? (caps.derived.notice ?? null) : null;
  const reasonFor = (id) => (XGB_CARDS.has(id) ? reasonOf(caps, 'xgboost') : reasonOf(caps, id));
  const enabledOf = (id) => (XGB_CARDS.has(id) ? xgbOpen : gate(id));
  const anyOpen = (ids) => ids.some(enabledOf);
  const rebuildable = (ids) => Boolean(staleNotice) && ids.some((id) => caps.reasons[id] === staleNotice);

  const sections = {
    perf: Boolean(caps.panels) && anyOpen(PAGE2_SECTIONS.perf),
    xgb: Boolean(caps.panels) && runs.length > 0,
    features: Boolean(caps.panels) && (anyOpen(PAGE2_SECTIONS.features) || rebuildable(PAGE2_SECTIONS.features)),
    primaries: Boolean(caps.panels) && caps.hasHits,
    voxels: Boolean(caps.panels) && caps.hasHits,
  };
  const cards = {};
  for (const [section, ids] of Object.entries(PAGE2_SECTIONS)) {
    for (const id of ids) {
      const enabled = sections[section] && enabledOf(id);
      cards[id] = { shown: sections[section], enabled, reason: enabled ? null : reasonFor(id) };
    }
  }

  const offered = offeredFrames(experiment);
  const frameReasons = {};
  for (const frame of FRAMES) {
    if (!offered.includes(frame)) frameReasons[frame] = caps.reasons[`frame-${frame}`] ?? NO_REASON;
  }

  // The 3-D views: their frames and channels, each with the server's reason
  // when it is shut. VoxelSection reads this block (`applyPlan(plan.voxels)`).
  const eventFrames = VIEW_FRAMES.event.frames.filter((f) => offered.includes(f));
  const ensembleFrames = VIEW_FRAMES.ensemble.frames.filter((f) => offered.includes(f));
  const channelSet = (channels) => {
    const open = [];
    const shut = {};
    for (const [channel, id] of channels) {
      if (gate(id)) open.push(channel);
      else shut[channel] = reasonOf(caps, id);
    }
    return { open, shut };
  };
  const eventChannels = channelSet([['energy', 'vox-event'], ['gradcam', 'vox-attention'],
    ['shapcam', 'vox-attention'], ['segerr', 'vox-attention'], ['species', 'vox-species']]);
  const ensembleChannels = channelSet([['density', 'vox-ensemble'], ['gradcam_energy', 'vox-attention'],
    ['shapcam_energy', 'vox-attention']]);
  const voxelReasons = {};
  for (const id of ['vox-event', 'vox-ensemble', 'vox-attention', 'vox-species']) {
    if (!gate(id)) voxelReasons[id] = reasonOf(caps, id);
  }
  const voxels = {
    shown: sections.voxels,
    kind: caps.kind,
    nShowers: caps.nShowers,
    showers: caps.showers,
    species: gate('vox-species'),
    networks: [...caps.networks],
    event: {
      enabled: sections.voxels && gate('vox-event'),
      reason: gate('vox-event') ? null : reasonOf(caps, 'vox-event'),
      frames: eventFrames,
      channels: eventChannels.open,
      disabledChannels: eventChannels.shut,
    },
    ensemble: {
      enabled: sections.voxels && gate('vox-ensemble'),
      reason: gate('vox-ensemble') ? null : reasonOf(caps, 'vox-ensemble'),
      frames: ensembleFrames,
      channels: ensembleChannels.open,
      disabledChannels: ensembleChannels.shut,
    },
    reasons: voxelReasons,
  };

  const networks = caps.networks.length > 0;
  const xgb = xgbBlock(caps, runs, xgbOpen);
  let banner = null;
  if (!networks) banner = runs.length && sections.perf ? MODELS_XGB_INSTEAD : MODELS_MISSING_PREDICTIONS;
  const notices = [];
  if (!caps.hasHits && caps.panels) notices.push(MODELS_EVENTS_ONLY);
  if (staleNotice) notices.push(staleNotice);

  return {
    kind: caps.kind,
    kindLabel: caps.kindLabel,
    legacy: caps.legacy,
    nShowers: caps.nShowers,
    showers: caps.showers,
    hasHits: caps.hasHits,
    // Read by `carriedFrame` and the shared frame logic: the page draws in a
    // frame wherever the experiment offers one.
    spatial: offered.length > 0,
    axes: filterAxes(experiment),
    sections,
    cards,
    networks,
    models: [...caps.networks],
    frames: {
      offered,
      disabled: frameReasons,
      transPrimary: single && offered.includes('trans'),
      labels: single ? SINGLE_SHOWER_FRAME_LABELS : null,
    },
    featureFrames: Array.isArray(experiment?.capabilities?.group1_frames)
      ? [...experiment.capabilities.group1_frames] : [],
    xgb,
    voxels,
    banner,
    xgbNotice: runs.length ? null : `${XGB_NOTICE} ${reasonOf(caps, 'xgboost')}`,
    notices,
    stale: staleNotice ? {
      notice: staleNotice,
      version: caps.derived.version ?? null,
      current: caps.derived.current ?? null,
    } : null,
    reasons: { ...caps.reasons },
  };
}
