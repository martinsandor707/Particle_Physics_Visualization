/* The Models page's 3-D views: one event as detector cells, and the
 * selection as a voxel cloud, each beside its three 2-D projections.
 *
 * `VoxelSection` builds its cards inside `#voxels-grid`, with the anatomy of
 * every other card (`.card[data-panel]`, the title row a direct child, Details
 * first in the toolbar): two `.voxel-pair`s, each a 3-D card (`.voxel-3d`,
 * spanning the pair's three rows) and three projection cards. The 3-D cards
 * carry Details, their own controls and a camera reset, and never an Export:
 * a rotated 3-D picture is not a publication figure (the recorded exception
 * of CLAUDE.md section 2, quoted in their drawers). The projections carry the
 * plot-only Export of every 2-D card. Card controls use attributes of their
 * own (`data-voxel-*`, `data-ens-channel`), never `data-shower`, `data-roi` or
 * `data-reset`, which the Physics page wires.
 *
 * ## What each pair asks for
 *
 * The event pair draws the event the link names (`voxel_event`) or, with
 * none, the densest event of the selection (`/api/event/pick?rule=densest`,
 * never written to the link): the Event Inspector's rasters
 * (`/api/event`, three panels of the drawn frame) and its cubes
 * (`/api/event?format=voxels`). The raster holds one shower in the Absolute,
 * per-shower translated and Local frames; the cubes are therefore asked for
 * in the same frame and shower, so the pair shows one picture twice. The
 * D-frame has no per-event raster, so the event pair draws Absolute there and
 * says so under its titles. The server draws both showers of an event at
 * once in the two frames that hold both, Absolute and the D-frame
 * (`query/voxel_event.py` `BOTH_FRAMES`); of the frames this pair draws, that
 * leaves the Absolute one, so "Both" is drawn there and a per-shower frame
 * draws shower A and says so. With both drawn, the projections show shower A,
 * and say so.
 *
 * The ensemble pair draws the selection's cloud (`/api/voxels`) in the Local
 * frame or the D-frame (an absolute or per-shower translated frame falls back
 * to Local, capabilities.js `viewFrame`), beside the Physics page's spatial
 * panels of the same frame and channel (`/api/projections`, Native Grid, so
 * the 2-D bins are raw accumulation bins like the cloud's).
 *
 * A frame change re-renders the raster in hand and asks for new cubes; a
 * channel change asks for new cubes only (the raster is energy density in
 * every channel). Responses are kept per request (`fetchShared`), so a card
 * that returns to an earlier view costs no request. Abort keys: `vox-pick`,
 * `vox-event-2d`, `vox-event-3d`, `vox-ens-2d`, `vox-ens-3d`.
 *
 * Each pair loads when it scrolls into view (LazyCards, rootMargin '0px',
 * plan decision D3) and again only when its request changes. The 2-D and the
 * 3-D half fail separately: a 422 refusal of the cubes (a shut gate, a shower
 * the frame cannot hold) is shown beside the 3-D card with the server's
 * reason, while the projections still draw.
 *
 * ## WebGL
 *
 * At most two WebGL contexts: the event and the ensemble chart, each holding
 * every GL series on one zlevel, created the first time its pair is drawn and
 * never disposed - an experiment change clears them. Availability is probed
 * once (page_common.js `webglAvailable`: a transient context, released at
 * once with `WEBGL_lose_context`);
 * without WebGL, or without the vendored echarts-gl, a 3-D card says so and
 * asks for nothing, and its projections still load. A lost context shows the
 * same kind of notice and, once restored, the chart is rebuilt from the
 * payload in hand.
 */

import { getJson, abortRequest, isAbort } from './api.js';
import { LazyCards, requestKey, isRefusal } from './lazy_cards.js';
import { describeError, writeSparseNote, webglAvailable } from './page_common.js';
import { apiFrame } from './state.js';
import { viewFrame } from './capabilities.js';
import { frameLabel, MODELS_LABELS } from './labels.js';
import { panelTitle } from './frame_views.js';
import { ProjectionPanel } from './panels/projection.js';
import { tooltipPosition, hideTooltipOnScroll } from './panels/tooltip.js';
import { formatInt, formatPercent, formatSci } from './scale.js';
import {
  decodeEventVoxels, decodeEnsembleVoxels, voxelOption, orthographicFit, glPlotHeight, speciesLegend, pairedWindow,
  cropToWindow,
} from './voxels.js';
import {
  ensembleCellOptions, depthIsometric, eventCellOptions, eventCellTitle,
} from './event_cells.js';
import {
  voxelEventNotes, voxelEnsembleNotes, voxelProjectionNotes, VOXEL_TITLES,
} from './voxel_notes.js';
import { SECTION, notesText, warningsNotShown } from './panel_notes.js';

/** The section's eight cards, in page order. */
export const VOXEL_CARDS = Object.freeze([
  { id: 'vox-event', pair: 'event', gl: true },
  { id: 'vproj-xy', pair: 'event', col: 'xy' },
  { id: 'vproj-xz', pair: 'event', col: 'xz' },
  { id: 'vproj-yz', pair: 'event', col: 'yz' },
  { id: 'vox-ensemble', pair: 'ensemble', gl: true },
  { id: 'eproj-xy', pair: 'ensemble', col: 'xy' },
  { id: 'eproj-yz', pair: 'ensemble', col: 'yz' },
  { id: 'eproj-xz', pair: 'ensemble', col: 'xz' },
]);

/** One abort key per request kind: a newer request of a kind supersedes the older. */
export const VOXEL_ABORT_KEYS = Object.freeze({
  pick: 'vox-pick',
  event2d: 'vox-event-2d',
  event3d: 'vox-event-3d',
  ensemble2d: 'vox-ens-2d',
  ensemble3d: 'vox-ens-3d',
});

/** The frames the Event Inspector's per-event rasters are served in. */
export const PAIRED_EVENT_FRAMES = Object.freeze(['lab', 'trans', 'local']);

/** The event channels that read a network's CAM column, and so name the network. */
const EVENT_CAM = new Set(['gradcam', 'shapcam']);
/** The ensemble channels that read a network's CAM column. */
const ENSEMBLE_CAM = new Set(['gradcam_energy', 'shapcam_energy']);

/** A channel choice as labels.js names it: its label and, when it has one, its detail. */
function choiceLabels(choices) {
  return Object.freeze(Object.fromEntries((choices ?? []).map((c) => [c.value, c.detail ? `${c.label} ${c.detail}` : c.label])));
}

/** The channel choices of each 3-D card (labels.js `MODELS_LABELS`, one owner of the wording). */
export const EVENT_CHANNEL_LABELS = choiceLabels(MODELS_LABELS.voxel_channel);
export const ENSEMBLE_CHANNEL_LABELS = choiceLabels(MODELS_LABELS.ens_channel);

/** The notebook's seed for the first "Pick" (the tilted rule); later picks take the next. */
const FIRST_SEED = 42;

/** How many responses the section keeps for views it may return to. */
const CACHE_SIZE = 16;

export const GL_UNAVAILABLE = 'WebGL is not available in this browser (or the 3-D renderer did not load), '
  + 'so the 3-D view is not drawn. The three 2-D projections beside it carry the same cells quantitatively.';
export const GL_LOST = 'The browser withdrew this view\'s WebGL context (the graphics driver reset, or too many '
  + '3-D views are open), so the 3-D view is not drawn until it is restored. The three 2-D projections beside '
  + 'it carry the same cells quantitatively.';

/** Why the event pair draws Absolute when the D-frame is selected. */
export const EVENT_CANONICAL_NOTE = 'Drawn in the Absolute frame: the 3-D event view stands beside the Event '
  + 'Inspector\'s rasters of the same event, which are served in the Absolute, per-shower translated and Local '
  + 'frames; no D-frame raster exists for one event, so the pair is drawn where both halves exist. The selected '
  + 'frame is kept for the other views.';

/** Why one shower is drawn when both are asked for outside the Absolute frame. */
export const BOTH_SHOWERS_NOTE = 'Both showers are drawn together in the Absolute frame only: each per-shower '
  + 'frame holds one shower at its own entry point, so shower A is drawn.';

/** What the projections say when the 3-D view draws both showers. */
export const PROJECTIONS_ONE_SHOWER = 'These projections show shower A: the Event Inspector\'s rasters hold '
  + 'one shower each, while the 3-D view beside them draws both.';

const DETAILS_TITLE = 'Methodology and disclosures for this panel';
const EXPORT_TITLE = 'Export this panel\'s plot as a publication figure (white background, 300 DPI, '
  + 'plot area only — see Details for its disclosures)';

/* ---------------------------------------------------------------- plan -- */

/**
 * The 3-D views' offer, from page2Plan's `voxels` block (or the whole plan):
 * `{shown, nShowers, event, ensemble}`, each view `{enabled, reason, frames,
 * channels, disabledChannels}`. Pure; a missing block offers nothing.
 */
export function normaliseOffer(block) {
  const v = block?.voxels && block?.sections ? block.voxels : block;
  const view = (x) => ({
    enabled: Boolean(x?.enabled),
    reason: x?.reason ?? null,
    frames: Array.isArray(x?.frames) ? [...x.frames] : [],
    channels: Array.isArray(x?.channels) ? [...x.channels] : [],
    disabledChannels: { ...(x?.disabledChannels ?? {}) },
  });
  return {
    shown: Boolean(v) && v.shown !== false,
    nShowers: v?.nShowers ?? 2,
    event: view(v?.event),
    ensemble: view(v?.ensemble),
  };
}

/** A channel the view cannot draw, as one sentence. */
function channelNote(asked, drawn, labels, reason) {
  return `Drawn by ${labels[drawn] ?? drawn}: ${labels[asked] ?? asked} is not available for this experiment`
    + `${reason ? ` (${reason.replace(/\.$/, '')})` : ''}. The selected channel is kept in the link.`;
}

/**
 * What the event pair draws for the view state `{frame, channel, shower}`:
 * `{frame, channel, shower, rasterShower, notes, projectionNote}`. `frame`
 * is null when the experiment offers the view in no frame. Pure.
 */
export function resolveEventView({ frame, channel, shower } = {}, offer) {
  const notes = [];
  const n = offer.nShowers ?? 2;
  const allowed = offer.event.frames.filter((f) => PAIRED_EVENT_FRAMES.includes(f));
  let drawn;
  if (frame === 'canonical' && allowed.includes('lab')) {
    drawn = 'lab';
    notes.push(EVENT_CANONICAL_NOTE);
  } else {
    const resolved = viewFrame('event', frame, allowed, n);
    drawn = resolved.frame;
    if (resolved.note) notes.push(resolved.note);
  }
  const channels = offer.event.channels;
  const ch = channels.includes(channel) ? channel : (channels.includes('energy') ? 'energy' : channels[0] ?? null);
  if (ch && channel && ch !== channel) {
    notes.push(channelNote(channel, ch, EVENT_CHANNEL_LABELS, offer.event.disabledChannels[channel]));
  }
  let three = n === 2 && ['a', 'b', 'both'].includes(shower) ? shower : 'a';
  if (three === 'both' && drawn !== 'lab') {
    three = 'a';
    notes.push(BOTH_SHOWERS_NOTE);
  }
  return {
    frame: drawn,
    channel: ch,
    shower: three,
    rasterShower: three === 'both' ? 'a' : three,
    notes,
    projectionNote: three === 'both' ? PROJECTIONS_ONE_SHOWER : null,
  };
}

/** What the ensemble pair draws for `{frame, channel}`: `{frame, channel, notes}`. Pure. */
export function resolveEnsembleView({ frame, channel } = {}, offer) {
  const notes = [];
  const resolved = viewFrame('ensemble', frame, offer.ensemble.frames, offer.nShowers ?? 2);
  if (resolved.note) notes.push(resolved.note);
  const channels = offer.ensemble.channels;
  const ch = channels.includes(channel) ? channel : (channels.includes('density') ? 'density' : channels[0] ?? null);
  if (ch && channel && ch !== channel) {
    notes.push(channelNote(channel, ch, ENSEMBLE_CHANNEL_LABELS, offer.ensemble.disabledChannels[channel]));
  }
  return { frame: resolved.frame, channel: ch, notes };
}

/* ------------------------------------------------------------ requests -- */

/** The densest event of the selection (the High_energy notebook's idxmax), never written to the link. */
export function pickRequest(filters) {
  return { route: '/api/event/pick', abortKey: VOXEL_ABORT_KEYS.pick, params: { ...filters, rule: 'densest' } };
}

/**
 * The event pair's two requests: the raster (one shower; all three paired
 * frames come in one response) and the cubes (null without WebGL). The
 * network is named only where a CAM channel reads it. Pure.
 */
export function eventRequests({ filters, eventNumber, view, model = 'segmentation', gl = true }) {
  const raster = {
    route: '/api/event',
    abortKey: VOXEL_ABORT_KEYS.event2d,
    params: { ...filters, event_number: eventNumber, shower: view.rasterShower },
  };
  const voxels = gl && view.frame && view.channel ? {
    route: '/api/event',
    abortKey: VOXEL_ABORT_KEYS.event3d,
    params: {
      ...filters,
      event_number: eventNumber,
      format: 'voxels',
      frame: view.frame,
      channel: view.channel,
      shower: view.shower,
      model: EVENT_CAM.has(view.channel) ? model : undefined,
    },
  } : null;
  return { raster, voxels };
}

/**
 * The ensemble pair's two requests: the cloud (null without WebGL) and the
 * spatial panels of the same frame, channel and network, on their Native
 * Grid and this selection's own reference. The D-frame's entry anchor goes
 * with both, and only there (elsewhere the API refuses it). Pure.
 */
export function ensembleRequests({ filters, view, model = 'segmentation', anchor = 'backprojected', gl = true }) {
  const canonical = view.frame === 'canonical';
  const network = ENSEMBLE_CAM.has(view.channel) ? model : undefined;
  const voxels = gl && view.frame && view.channel ? {
    route: '/api/voxels',
    abortKey: VOXEL_ABORT_KEYS.ensemble3d,
    params: {
      ...filters,
      frame: view.frame,
      channel: view.channel,
      model: network,
      anchor: canonical ? anchor : undefined,
    },
  } : null;
  const projections = view.frame && view.channel ? {
    route: '/api/projections',
    abortKey: VOXEL_ABORT_KEYS.ensemble2d,
    params: {
      ...filters,
      ...apiFrame(view.frame),
      channel: view.channel,
      model: network,
      display: 'native',
      rho_norm: 'selection',
      anchor: canonical ? anchor : undefined,
    },
  } : null;
  return { voxels, projections };
}

/* ---------------------------------------------------------------- DOM -- */

/**
 * Size a 3-D plot's height from its width (voxels.js `glPlotHeight`): an
 * inline height that overrides the stylesheet's 560 px, set synchronously so
 * the chart's ResizeObserver measures the final geometry. Returns the height
 * set, or null when the plot has no width yet (hidden), which keeps the
 * stylesheet's.
 */
export function fitPlotHeight(plot) {
  const width = plot?.clientWidth;
  if (!(width > 0)) return null;
  const height = glPlotHeight(width);
  const text = `${height}px`;
  if (plot.style.height !== text) plot.style.height = text;
  return height;
}

function make(tag, className = '', text = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== null) node.textContent = text;
  return node;
}

function miniButton(text, title, data) {
  const button = make('button', 'mini', text);
  button.type = 'button';
  button.title = title;
  for (const [key, value] of Object.entries(data)) button.dataset[key] = value;
  return button;
}

/* ------------------------------------------------------------- section -- */

export class VoxelSection {
  /**
   * @param {HTMLElement} hostEl  the `#voxels-grid` section
   * @param {object} options
   *   `state` the interface State; `getExperiment()` the active experiment;
   *   `onError(error, context)` for a load nobody awaits; `onRendered(id,
   *   payload|null)` after a card drew (or failed); `lazy` the LazyCards the
   *   section watches its pairs with (its own when omitted); `webgl` forces
   *   the availability probe's answer and `echarts` the library (tests);
   *   `ProjectionClass` replaces the 2-D panel class (tests).
   */
  constructor(hostEl, {
    state, getExperiment = () => null, onError = () => {}, onRendered = () => {}, lazy = null,
    webgl = null, echarts: lib = null, ProjectionClass = ProjectionPanel,
  } = {}) {
    this.host = hostEl;
    this.state = state;
    this.getExperiment = getExperiment;
    this.onError = onError;
    this.onRendered = onRendered;
    this.webgl = webgl;
    this.glChecked = null;
    this.lib = lib;
    this.ProjectionClass = ProjectionClass;
    this.offer = normaliseOffer(null);
    this.cards = new Map();
    this.pairs = {};
    this.cache = new Map();
    this.inflight = new Map();
    this.generation = 0;
    this.seed = FIRST_SEED;
    this.pickRule = null;
    this.lazy = lazy && typeof lazy.watch === 'function'
      ? lazy
      : new LazyCards({
        root: hostEl?.closest?.('.main') ?? null,
        rootMargin: '0px',
        onError: (error) => this.onError(error, '3-D views'),
      });
    if (!hostEl) return;
    for (const name of ['event', 'ensemble']) this.buildPair(name);
  }

  /* -------------------------------------------------------------- markup */

  buildPair(name) {
    const element = make('div', 'voxel-pair');
    element.dataset.voxelPair = name;
    element.hidden = true;
    const pair = {
      name, element, gl: null, cells: [], entry: null,
      view: null, payloads: {}, model: null, built: null, hidden: new Set(),
      pick: null, loading: null,
    };
    this.pairs[name] = pair;
    for (const spec of VOXEL_CARDS.filter((s) => s.pair === name)) {
      const record = this.buildCard(spec);
      if (spec.gl) pair.gl = record;
      else pair.cells.push(record);
      element.append(record.element);
    }
    this.host.append(element);
    pair.entry = this.lazy.watch(element, {
      key: () => this.keyOf(name),
      load: (key) => this.loadPair(name, key),
    });
  }

  buildCard(spec) {
    const { id } = spec;
    const card = make('div', `card voxel-card${spec.gl ? ' voxel-3d' : ''}`);
    card.dataset.panel = id;

    const heading = document.createElement('h2');
    const title = make('span', 'title', spec.gl ? VOXEL_TITLES[id] : 'Projection');
    title.id = `title-${id}`;
    title.title = 'Open the panel\'s methodology and disclosures';
    const tag = make('span', 'tag');
    tag.hidden = true;
    const actions = make('span', 'card-actions');
    const details = miniButton('Details', DETAILS_TITLE, { inspect: id });
    details.setAttribute('aria-controls', 'inspector');
    details.setAttribute('aria-expanded', 'false');
    actions.append(details);

    const record = {
      spec, element: card, title, tag, details, controls: {}, exporter: null,
      caption: null, plot: null, message: null, legend: null, sparse: null,
      panel: null, chart: null, watched: null, lost: false, disabled: null, error: null,
    };
    if (spec.gl) this.buildGlControls(record, actions);
    else {
      const exporter = miniButton('Export ', EXPORT_TITLE, { export: id });
      exporter.setAttribute('aria-haspopup', 'menu');
      exporter.append(document.createTextNode('▾'));
      actions.append(exporter);
      record.exporter = exporter;
    }
    heading.append(title, tag, actions);

    const caption = make('div', 'card-caption');
    caption.hidden = true;
    const frame = make('div', 'plot-frame');
    const plot = make('div', spec.gl ? 'plot gl' : 'plot');
    plot.id = `plot-${id}`;
    const message = make('div', `card-error${spec.gl ? ' gl-notice' : ''}`);
    message.setAttribute('role', 'status');
    message.hidden = true;
    frame.append(plot, message);
    card.append(heading, caption, frame);
    Object.assign(record, { caption, plot, message });
    if (spec.gl) {
      record.legend = make('div', 'voxel-legend');
      record.legend.hidden = true;
      record.sparse = make('div', 'sparse-note');
      record.sparse.id = `${id}-sparse`;
      record.sparse.hidden = true;
      card.append(record.legend, record.sparse);
    }
    this.cards.set(id, record);
    return record;
  }

  /** The 3-D cards' own controls: the event picker, the shower, the channel, the camera. */
  buildGlControls(record, actions) {
    const c = record.controls;
    if (record.spec.pair === 'event') {
      const number = make('input', 'mini-select');
      number.type = 'number';
      number.min = '0';
      number.step = '1';
      number.placeholder = 'densest';
      number.dataset.voxelEvent = '';
      number.setAttribute('aria-label', 'Event number (empty: the densest event of the selection)');
      number.title = 'Event number; empty draws the densest event of the selection';
      number.addEventListener('change', () => {
        const raw = number.value.trim();
        const n = Number(raw);
        if (raw === '') this.setEvent(null);
        else if (Number.isInteger(n) && n >= 0) this.setEvent(n);
        else this.syncControls();
      });
      const prev = miniButton('‹', 'The previous event of the selection', { voxelStep: 'prev' });
      const next = miniButton('›', 'The next event of the selection', { voxelStep: 'next' });
      prev.addEventListener('click', () => this.step('prev'));
      next.addEventListener('click', () => this.step('next'));
      const densest = miniButton('Densest', 'The event with the most detector cells in the selection (the '
        + 'High_energy notebook\'s idxmax; not written to the link)', { voxelDensest: '' });
      densest.addEventListener('click', () => this.setEvent(null));
      const pick = miniButton('Pick', 'A seeded draw from the most tilted of the dense events (the local-coords '
        + 'notebook\'s rule); each click takes the next seed', { voxelPick: '' });
      pick.addEventListener('click', () => this.pick());
      const showers = make('span', 'seg');
      showers.setAttribute('role', 'group');
      showers.setAttribute('aria-label', 'Showers');
      const showerButtons = new Map();
      for (const [value, label, title] of [['a', 'A', 'Shower A'], ['b', 'B', 'Shower B'],
        ['both', 'Both', 'Both showers (Absolute frame only)']]) {
        const button = miniButton(label, title, { voxelShower: value });
        button.addEventListener('click', () => this.setValue({ voxel_shower: value }));
        showerButtons.set(value, button);
        showers.append(button);
      }
      const channel = this.channelSelect('voxelChannel', 'Colour the cubes by', EVENT_CHANNEL_LABELS,
        (value) => this.setValue({ voxel_channel: value }));
      Object.assign(c, { number, prev, next, densest, pick, showers, showerButtons, channel });
      actions.append(number, prev, next, densest, pick, showers, channel);
    } else {
      c.channel = this.channelSelect('ensChannel', 'Colour the voxels by', ENSEMBLE_CHANNEL_LABELS,
        (value) => this.setValue({ ens_channel: value }));
      actions.append(c.channel);
    }
    c.reset = miniButton('Reset view', 'Back to the opening camera: orthographic, 1:1:1', { voxelReset: record.spec.id });
    c.reset.addEventListener('click', () => this.resetCamera(record.spec.pair));
    actions.append(c.reset);
  }

  channelSelect(attr, label, labels, onChange) {
    const select = make('select', 'mini-select');
    select.dataset[attr] = '';
    select.setAttribute('aria-label', label);
    select.title = label;
    for (const [value, text] of Object.entries(labels)) {
      const option = make('option', '', text);
      option.value = value;
      select.append(option);
    }
    select.addEventListener('change', () => onChange(select.value));
    return select;
  }

  /* ---------------------------------------------------------- the state */

  /** A view key, with its built-in default while the state does not hold it. */
  value(key) {
    const fallback = {
      voxel_event: null, voxel_shower: 'a', voxel_channel: 'energy', ens_channel: 'density',
      frame: 'lab', model: 'segmentation', anchor: 'backprojected', palette: 'viridis',
    }[key] ?? null;
    const v = this.state?.get?.(key);
    return v === undefined || (v === null && key !== 'voxel_event') ? fallback : v;
  }

  /** Write view keys and load what they change. */
  setValue(patch) {
    this.state?.set?.(patch);
    this.syncControls();
    this.refreshVisible();
  }

  setEvent(eventNumber) {
    this.pickRule = null;
    this.setValue({ voxel_event: eventNumber });
  }

  /** The neighbouring event within the selection, as the last response named it. */
  step(direction) {
    const event = this.pairs.event?.payloads.voxels?.event ?? this.pairs.event?.payloads.raster?.event;
    const n = event?.[direction];
    if (Number.isInteger(n)) this.setEvent(n);
  }

  /** The tilted rule's seeded draw on the current filters; each click takes the next seed. */
  async pick() {
    try {
      const payload = await getJson('/api/event/pick', { ...this.state.filterParams(), seed: this.seed },
        VOXEL_ABORT_KEYS.pick);
      this.seed += 1;
      this.setEvent(payload.event_number);
      this.pickRule = payload.rule ?? null;
    } catch (error) {
      if (!isAbort(error)) this.onError(error, 'pick an event');
    }
  }

  eventView() {
    return resolveEventView({
      frame: this.value('frame'), channel: this.value('voxel_channel'), shower: this.value('voxel_shower'),
    }, this.offer);
  }

  ensembleView() {
    return resolveEnsembleView({ frame: this.value('frame'), channel: this.value('ens_channel') }, this.offer);
  }

  /** Whether the 3-D charts can be drawn: WebGL and the vendored echarts-gl. */
  glAvailable() {
    if (this.glChecked === null) {
      this.glChecked = this.webgl ?? (Boolean(globalThis.window?.['echarts-gl']) && webglAvailable());
    }
    return this.glChecked;
  }

  /* ------------------------------------------------------------- plan */

  /**
   * Show the pairs of a plan: page2Plan's `voxels` block (the whole plan is
   * accepted too). A view the experiment cannot serve keeps its cards, shut
   * with the server's reason. Every pair goes stale.
   */
  applyPlan(plan) {
    this.offer = normaliseOffer(plan);
    for (const name of ['event', 'ensemble']) {
      const pair = this.pairs[name];
      if (!pair) continue;
      pair.element.hidden = !this.offer.shown;
      const view = this.offer[name];
      const reason = view.enabled ? null : (view.reason ?? 'This view is not available for this experiment.');
      for (const record of [pair.gl, ...pair.cells]) {
        record.disabled = this.offer.shown ? reason : null;
        if (record.disabled) {
          this.blank(record);
          this.showMessage(record, record.disabled, { kind: 'disabled' });
        } else if (record.message.dataset.kind === 'disabled') {
          this.hideMessage(record);
        }
      }
    }
    this.syncControls();
    this.lazy.forget();
  }

  ids() {
    return [...this.cards.keys()];
  }

  has(id) {
    return this.cards.has(id);
  }

  /** The request key of one pair now, or null when it does not load. */
  keyOf(name) {
    const pair = this.pairs[name];
    if (!pair || !this.offer.shown || pair.element.hidden || !this.offer[name].enabled) return null;
    const filters = this.state?.filterParams?.();
    if (!filters?.table_name) return null;
    const gl = this.glAvailable();
    if (name === 'event') {
      const view = this.eventView();
      if (!view.frame || !view.channel) return null;
      const event = this.value('voxel_event');
      return requestKey('vox-event', {
        ...filters, event: Number.isInteger(event) ? event : 'densest', frame: view.frame, channel: view.channel,
        shower: view.shower, model: EVENT_CAM.has(view.channel) ? this.value('model') : undefined, gl,
      });
    }
    const view = this.ensembleView();
    if (!view.frame || !view.channel) return null;
    return requestKey('vox-ensemble', {
      ...filters, frame: view.frame, channel: view.channel, gl,
      model: ENSEMBLE_CAM.has(view.channel) ? this.value('model') : undefined,
      anchor: view.frame === 'canonical' ? this.value('anchor') : undefined,
    });
  }

  /* ------------------------------------------------------------ loading */

  /**
   * Load every visible pair whose request changed. Rejects with one error
   * naming each pair that failed (each also says so on its cards); a
   * superseded request is not a failure.
   */
  async refresh() {
    if (!this.offer.shown) return [];
    const started = [];
    for (const pair of Object.values(this.pairs)) {
      const promise = pair.entry ? this.lazy.check(pair.entry) : null;
      if (promise) started.push([pair.name, promise]);
    }
    const results = await Promise.allSettled(started.map(([, p]) => p));
    const failures = results
      .map((result, i) => [started[i][0], result])
      .filter(([, result]) => result.status === 'rejected' && !isAbort(result.reason))
      .map(([name, result]) => `${name === 'event' ? 'the 3-D event' : 'the 3-D ensemble'}: ${describeError(result.reason)}`);
    if (failures.length) throw new Error(failures.join('; '));
    return results;
  }

  /** Load after a card's own control changed, reporting a failure without awaiting it. */
  refreshVisible() {
    this.refresh().catch((error) => {
      if (!isAbort(error)) this.onError(error, '3-D views');
    });
  }

  loadPair(name, key) {
    return name === 'event' ? this.loadEvent(key) : this.loadEnsemble(key);
  }

  /** One response per request: joined while in flight, kept for a view returned to. */
  fetchShared({ route, params, abortKey }) {
    const key = requestKey(route, params);
    if (this.cache.has(key)) {
      const payload = this.cache.get(key);
      this.cache.delete(key);
      this.cache.set(key, payload);
      return Promise.resolve(payload);
    }
    const pending = this.inflight.get(key);
    if (pending) return pending;
    const promise = getJson(route, params, abortKey);
    this.inflight.set(key, promise);
    const generation = this.generation;
    promise.then((payload) => {
      if (generation !== this.generation) return;
      this.cache.set(key, payload);
      while (this.cache.size > CACHE_SIZE) this.cache.delete(this.cache.keys().next().value);
    }, () => {}).finally(() => {
      if (this.inflight.get(key) === promise) this.inflight.delete(key);
    });
    return promise;
  }

  /**
   * The settled halves of a pair, rethrown for LazyCards: an abort first (a
   * newer request took over), then a failure that may pass (asked again),
   * then a refusal (loaded for its key). Each half has said so on its cards.
   */
  static settle(results) {
    const rejected = results.filter((r) => r.status === 'rejected').map((r) => r.reason);
    const aborted = rejected.find((e) => isAbort(e));
    if (aborted) throw aborted;
    const transient = rejected.find((e) => !isRefusal(e));
    if (transient) throw transient;
    if (rejected.length) throw rejected[0];
  }

  async loadEvent(key) {
    const pair = this.pairs.event;
    const loading = {};
    pair.loading = loading;
    this.setPairBusy(pair, true);
    let stage = 'pick';
    try {
      const filters = this.state.filterParams();
      const view = this.eventView();
      let eventNumber = this.value('voxel_event');
      let pick = null;
      if (!Number.isInteger(eventNumber)) {
        pick = await this.fetchShared(pickRequest(filters));
        eventNumber = pick.event_number;
      }
      if (this.keyOf('event') !== key) return;
      stage = 'draw';
      const gl = this.glAvailable();
      const requests = eventRequests({ filters, eventNumber, view, model: this.value('model'), gl });
      const results = await Promise.allSettled([
        this.fetchShared(requests.raster),
        requests.voxels ? this.fetchShared(requests.voxels) : Promise.resolve(null),
      ]);
      if (this.keyOf('event') !== key || results.some((r) => r.status === 'rejected' && isAbort(r.reason))) {
        VoxelSection.settle(results);
        return;
      }
      pair.view = view;
      pair.pick = pick;
      this.drawEventCells(pair, results[0]);
      this.drawGl(pair, results[1], gl, decodeEventVoxels);
      this.syncControls();
      VoxelSection.settle(results);
    } catch (error) {
      if (!isAbort(error) && stage === 'pick' && this.keyOf('event') === key) this.failPair(pair, error);
      throw error;
    } finally {
      if (pair.loading === loading) {
        pair.loading = null;
        this.setPairBusy(pair, false);
      }
    }
  }

  async loadEnsemble(key) {
    const pair = this.pairs.ensemble;
    const loading = {};
    pair.loading = loading;
    this.setPairBusy(pair, true);
    try {
      const view = this.ensembleView();
      const gl = this.glAvailable();
      const requests = ensembleRequests({
        filters: this.state.filterParams(), view, model: this.value('model'), anchor: this.value('anchor'), gl,
      });
      const results = await Promise.allSettled([
        this.fetchShared(requests.projections),
        requests.voxels ? this.fetchShared(requests.voxels) : Promise.resolve(null),
      ]);
      if (this.keyOf('ensemble') !== key || results.some((r) => r.status === 'rejected' && isAbort(r.reason))) {
        VoxelSection.settle(results);
        return;
      }
      pair.view = view;
      this.drawEnsembleCells(pair, results[0]);
      // The cloud's box is the paired projections' window (CLAUDE.md's recorded windows of the
      // co-registered frames), so the 3-D view and its 2-D projections show one region; the
      // accumulation grid's full extent and what the crop leaves out are in the drawer.
      const window = results[0].status === 'fulfilled' ? pairedWindow(results[0].value) : null;
      this.drawGl(pair, results[1], gl, (payload) => cropToWindow(decodeEnsembleVoxels(payload), window));
      this.syncControls();
      VoxelSection.settle(results);
    } finally {
      if (pair.loading === loading) {
        pair.loading = null;
        this.setPairBusy(pair, false);
      }
    }
  }

  /* ------------------------------------------------------------ drawing */

  ensureProjection(record) {
    if (!record.panel) record.panel = new this.ProjectionClass(record.plot.id, { isometric: true });
    return record.panel;
  }

  /** The event's three rasters, in the frame the pair draws. */
  drawEventCells(pair, result) {
    const view = pair.view;
    if (result.status !== 'fulfilled') {
      pair.payloads.raster = null;
      for (const record of pair.cells) this.failCard(record, result.reason);
      return;
    }
    const raster = result.value;
    pair.payloads.raster = raster;
    const frame = raster.frames?.[view.frame];
    const palette = this.value('palette');
    for (const record of pair.cells) {
      const col = record.spec.col;
      if (!frame?.panels?.[col]) {
        this.failCard(record, new Error(`The event response holds no ${col} panel in this frame.`));
        continue;
      }
      try {
        const panel = this.ensureProjection(record);
        panel.isometric = true;
        panel.render(frame.panels[col], eventCellOptions(raster, view.frame, col, palette));
      } catch (error) {
        // One card that cannot draw says so; its pair and its neighbours still draw.
        this.failCard(record, error);
        continue;
      }
      record.error = null;
      this.hideMessage(record);
      record.title.textContent = `Event ${eventCellTitle(frame, col)} Projection`;
      this.setTag(record, frame.title ?? frameLabel(view.frame, this.offer.nShowers));
      this.setCaption(record, [this.drawnIn(view, 'the 3-D event'), view.projectionNote]);
      this.onRendered(record.spec.id, raster);
    }
  }

  /** The selection's three spatial panels, in the cloud's frame. */
  drawEnsembleCells(pair, result) {
    if (result.status !== 'fulfilled') {
      pair.payloads.projections = null;
      for (const record of pair.cells) this.failCard(record, result.reason);
      return;
    }
    const payload = result.value;
    pair.payloads.projections = payload;
    const palette = this.value('palette');
    const kind = payload.frame?.kind ?? pair.view.frame;
    for (const record of pair.cells) {
      const col = record.spec.col;
      const panelPayload = payload.panels?.[col];
      if (!panelPayload) {
        this.failCard(record, new Error(`The projections response holds no ${col} panel.`));
        continue;
      }
      try {
        const panel = this.ensureProjection(record);
        panel.isometric = col === 'xy' || depthIsometric(panel, panelPayload);
        if (col !== 'xy') panel.onRelayout = (p) => { p.isometric = depthIsometric(p, p.payload); };
        panel.render(panelPayload, ensembleCellOptions(payload, col, palette));
      } catch (error) {
        this.failCard(record, error);
        continue;
      }
      record.error = null;
      this.hideMessage(record);
      record.title.textContent = panelTitle(col, kind, this.offer.nShowers);
      this.setTag(record, null);
      this.setCaption(record, [this.drawnIn(pair.view, 'the 3-D cloud')]);
      this.onRendered(record.spec.id, payload);
    }
  }

  /** The 3-D half of a pair: decode, build and draw, or say why not. */
  drawGl(pair, result, gl, decode) {
    const record = pair.gl;
    if (!gl) {
      pair.payloads.voxels = null;
      pair.model = null;
      pair.built = null;
      this.blank(record);
      this.showMessage(record, GL_UNAVAILABLE, { kind: 'notice' });
      this.onRendered(record.spec.id, null);
      return;
    }
    if (!result || result.status !== 'fulfilled' || !result.value) {
      pair.payloads.voxels = null;
      pair.model = null;
      pair.built = null;
      this.failCard(record, result?.reason ?? new Error('No cubes were returned.'));
      return;
    }
    let model;
    try {
      model = decode(result.value);
    } catch (error) {
      pair.payloads.voxels = null;
      this.failCard(record, error);
      return;
    }
    pair.payloads.voxels = result.value;
    pair.model = model;
    // Species hidden on one event stay hidden on the next only if it holds them.
    if (model.scale?.scale !== 'categorical') pair.hidden.clear();
    record.error = null;
    try {
      this.paintGl(pair);
    } catch (error) {
      pair.payloads.voxels = null;
      pair.model = null;
      pair.built = null;
      this.failCard(record, error);
      return;
    }
    this.onRendered(record.spec.id, result.value);
  }

  /** The 3-D chart, created once per card (one WebGL context) and never disposed. */
  ensureChart(record) {
    if (record.chart) return record.chart;
    const lib = this.lib ?? globalThis.echarts;
    // The height follows the width before the chart first measures its container.
    fitPlotHeight(record.plot);
    const chart = lib.init(record.plot, null, { renderer: 'canvas' });
    record.chart = chart;
    // Kept across a rebuild: a canvas is listened to once, whichever chart drew on it.
    record.watched ??= new WeakSet();
    // The whole chart is the plot: an explanatory tip is placed outside it.
    record.tooltipPosition = tooltipPosition(chart, () => ({
      left: 0, top: 0, width: chart.getWidth(), height: chart.getHeight(),
    }));
    hideTooltipOnScroll(chart);
    if (typeof ResizeObserver === 'function' && !record.resizeObserver) {
      let pending = 0;
      record.resizeObserver = new ResizeObserver(() => {
        if (pending) return;
        pending = requestAnimationFrame(() => {
          pending = 0;
          this.resizeChart(record);
        });
      });
      record.resizeObserver.observe(record.plot);
    }
    return chart;
  }

  resizeChart(record) {
    const chart = record.chart;
    if (!chart) return;
    // A new width sets a new height (voxels.js glPlotHeight), at once: no transition.
    fitPlotHeight(record.plot);
    const width = record.plot.clientWidth;
    const height = record.plot.clientHeight;
    if (!(width > 0 && height > 0)) return;
    if (chart.getWidth() !== width || chart.getHeight() !== height) chart.resize();
    // A new width moves the opening view's fit (voxels.js orthographicFit). The
    // camera keeps the reader's rotation and pan; only its zoom is refitted.
    if (!record.fit || record.lost) return;
    const size = orthographicFit(width, height, record.fit.right);
    if (Math.abs(size - record.fit.size) < 0.5) return;
    record.fit.size = size;
    chart.setOption({ grid3D: { viewControl: { orthographicSize: size } } });
  }

  /**
   * Draw a pair's model on its chart. `keepCamera` swaps the series and the
   * legend only (an isolate toggle, a palette change), so the reader's
   * rotation survives; otherwise the option is replaced whole and the camera
   * opens orthographic at its default angles.
   */
  paintGl(pair, { keepCamera = false } = {}) {
    const record = pair.gl;
    if (!pair.model || !this.glAvailable()) return;
    const chart = this.ensureChart(record);
    const built = voxelOption(pair.model, {
      palette: this.value('palette'), hidden: pair.hidden, position: record.tooltipPosition,
      viewport: { width: chart.getWidth(), height: chart.getHeight() },
    });
    pair.built = built;
    if (pair.name === 'event') {
      record.title.textContent = pair.model.regime === 'cells'
        ? VOXEL_TITLES['vox-event'] : 'One Event in 3-D — Sub-deposit Voxels';
    }
    this.setTag(record, frameLabel(pair.model.frame, this.offer.nShowers));
    this.setCaption(record, pair.view?.notes ?? []);
    this.renderLegend(pair);
    this.renderSparse(pair);
    if (record.lost) return;
    this.hideMessage(record);
    if (keepCamera) {
      chart.setOption({
        series: built.option.series,
        ...(built.option.visualMap ? { visualMap: built.option.visualMap } : {}),
      }, { replaceMerge: ['series', 'visualMap'] });
    } else {
      chart.setOption(built.option, { notMerge: true });
      const grid = built.option.grid3D;
      record.fit = { right: grid.right, size: grid.viewControl.orthographicSize };
    }
    this.watchContext(pair);
  }

  /** Listen for the loss and restoration of the chart's WebGL context, once per canvas. */
  watchContext(pair) {
    const record = pair.gl;
    for (const canvas of record.plot.querySelectorAll?.('canvas') ?? []) {
      if (record.watched.has(canvas)) continue;
      record.watched.add(canvas);
      canvas.addEventListener('webglcontextlost', (event) => {
        event.preventDefault();
        record.lost = true;
        this.showMessage(record, GL_LOST, { kind: 'notice' });
        this.onRendered(record.spec.id, pair.payloads.voxels ?? null);
      });
      canvas.addEventListener('webglcontextrestored', () => {
        record.lost = false;
        // The old chart's GPU resources died with the context: rebuild it.
        record.chart?.dispose?.();
        record.chart = null;
        record.fit = null;
        this.paintGl(pair);
        this.onRendered(record.spec.id, pair.payloads.voxels ?? null);
      });
    }
  }

  /** Back to the opening camera, from the model in hand. */
  resetCamera(name) {
    const pair = this.pairs[name];
    if (pair?.model && pair.gl.chart) this.paintGl(pair);
  }

  /** The species legend (with isolate toggles), or the degenerate-ramp line, under the plot. */
  renderLegend(pair) {
    const record = pair.gl;
    const box = record.legend;
    const model = pair.model;
    if (!box) return;
    if (model?.scale?.scale === 'categorical') {
      const rows = speciesLegend(model, pair.hidden);
      // Laid out by models.css (.voxel-species); only the swatch's colour is the row's own.
      const list = make('ul', 'voxel-species');
      for (const row of rows) {
        const item = make('li');
        const label = make('label');
        const box2 = make('input');
        box2.type = 'checkbox';
        box2.checked = !row.hidden;
        box2.dataset.voxelSpecies = String(row.code);
        box2.setAttribute('aria-label', `Show ${row.label}`);
        box2.addEventListener('change', () => this.toggleSpecies(row.code, !box2.checked));
        const swatch = make('span', 'voxel-swatch');
        swatch.style.setProperty('--swatch', row.colour);
        const name = make('span', 'voxel-species-name', row.label);
        label.append(box2, swatch, name);
        const counts = make('span', '', `${formatInt(row.cells)} cells (${formatInt(row.drawn)} drawn) · `
          + `${formatPercent(row.energyFraction, 1)} of the energy · ${formatInt(row.primaryCells)} primary-tagged`);
        if (row.members?.length) {
          counts.title = `Other: ${row.members.map((m) => `${m.name} (${formatInt(m.rows)} rows)`).join(', ')}`;
        }
        const only = miniButton('only', `Show ${row.label} alone; again to show every species`,
          { voxelSpeciesOnly: String(row.code) });
        only.addEventListener('click', () => this.isolateSpecies(row.code));
        item.append(label, counts, only);
        list.append(item);
      }
      box.replaceChildren(list);
      box.hidden = rows.length === 0;
      return;
    }
    if (model?.scale?.degenerate) {
      box.replaceChildren(make('p', '', 'Every drawn cube holds the same density, so the ramp has no range: '
        + 'each is drawn in its top colour.'));
      box.hidden = false;
      return;
    }
    box.replaceChildren();
    box.hidden = true;
  }

  toggleSpecies(code, hide) {
    const pair = this.pairs.event;
    if (hide) pair.hidden.add(code);
    else pair.hidden.delete(code);
    this.paintGl(pair, { keepCamera: true });
    this.onRendered(pair.gl.spec.id, pair.payloads.voxels ?? null);
  }

  /** Show one species alone, or every species when it already is. */
  isolateSpecies(code) {
    const pair = this.pairs.event;
    const codes = (pair.model?.species?.legend ?? []).map((e) => e.code);
    const alone = codes.every((c) => (c === code ? !pair.hidden.has(c) : pair.hidden.has(c)));
    pair.hidden = new Set(alone ? [] : codes.filter((c) => c !== code));
    this.paintGl(pair, { keepCamera: true });
    this.onRendered(pair.gl.spec.id, pair.payloads.voxels ?? null);
  }

  /** The key counts under a 3-D card, on screen without its drawer. */
  renderSparse(pair) {
    const payload = pair.payloads.voxels;
    const lines = [];
    if (payload && pair.name === 'event') {
      const event = payload.event ?? {};
      const cap = payload.voxels?.cap ?? {};
      // A single-shower experiment's one shower needs no name.
      const showers = (this.offer.nShowers ?? 2) === 2 ? (event.showers ?? []).map((s) => s.label).join(' and ') : '';
      const what = payload.voxels?.regime === 'cells' ? 'cells' : 'voxels';
      let lead = `Event ${formatInt(event.event_number)}${showers ? `, shower${(event.showers ?? []).length > 1 ? 's' : ''} ${showers}` : ''}: `
        + `${formatInt(cap.n_drawn)} of ${formatInt(cap.n_total)} ${what} drawn`;
      if (pair.pick && !Number.isInteger(this.value('voxel_event'))) lead += ' · the densest event of the selection';
      else if (this.pickRule) lead += ' · picked by the tilted rule';
      if (event.in_selection === false) lead += ' · outside the current selection';
      lines.push(`${lead}.`);
      if ((cap.n_beyond ?? 0) > 0) {
        lines.push(`Cap ${formatInt(cap.limit)}: the ${formatInt(cap.n_beyond)} weakest ${what} beyond it hold `
          + `${formatPercent(cap.fraction_beyond, 3)} of the energy, counted and not drawn.`);
      }
      const below = payload.voxels?.below_floor?.n ?? 0;
      if (below > 0 && payload.voxels?.channel === 'energy') {
        lines.push(`${formatInt(below)} below the ramp floor, drawn at its lowest colour and flagged.`);
      }
      if (pair.hidden.size) lines.push(`${formatInt(pair.built?.hidden ?? 0)} cubes hidden by the species toggles.`);
    } else if (payload && pair.name === 'ensemble') {
      const frame = payload.frame ?? {};
      const budget = payload.budget ?? {};
      if (frame.provisional || payload.rho?.provisional) lines.push(frame.n_label ?? 'Provisional range: weak evidence.');
      // The server's count of the voxels shipped, less those outside the paired projections' window.
      const cropped = pair.model?.crop?.nOutside ?? 0;
      const drawn = Number.isFinite(budget.n_drawn) ? budget.n_drawn - cropped : budget.n_drawn;
      lines.push(`${formatInt(drawn)} of ${formatInt(budget.n_populated)} populated voxels drawn; `
        + `${formatInt(budget.n_below_floor)} below the 10⁻³ floor hold ${formatPercent(budget.energy_fraction?.below_floor, 2)} `
        + 'of the energy, counted.');
      if (cropped > 0) {
        lines.push(`${formatInt(cropped)} outside the projections' window hold ${formatPercent(pair.model.crop.shareOutside, 2)} `
          + 'of the cloud shipped, counted and not drawn (Details).');
      }
      if ((budget.n_beyond_cap ?? 0) > 0) {
        lines.push(`Cap ${formatInt(budget.cap)}: ${formatInt(budget.n_beyond_cap)} voxels beyond it hold `
          + `${formatPercent(budget.energy_fraction?.beyond_cap, 2)} of the energy, counted and not drawn.`);
      }
      if (Number.isFinite(payload.rho?.rho_ref)) {
        lines.push(`ρ_ref = ${formatSci(payload.rho.rho_ref, 3)} GeV mm⁻³ per event, this selection's raw 3-D peak.`);
      }
    }
    writeSparseNote(pair.gl.sparse, lines);
  }

  /* -------------------------------------------------------- card chrome */

  /**
   * A projection's one-line caption when its pair draws in another frame
   * than the selected one: the full sentence stands under the 3-D card and in
   * the drawer, so the three projections say it in a few words.
   */
  drawnIn(view, beside) {
    const fallback = (view?.notes ?? []).some((n) => n.startsWith('Drawn in'));
    return fallback && view.frame
      ? `Drawn in ${frameLabel(view.frame, this.offer.nShowers)}, as ${beside} beside it (see its caption).`
      : null;
  }

  setTag(record, text) {
    record.tag.textContent = text ?? '';
    record.tag.hidden = !text;
  }

  setCaption(record, lines) {
    const kept = (lines ?? []).filter(Boolean);
    record.caption.textContent = kept.join(' ');
    record.caption.hidden = kept.length === 0;
  }

  setPairBusy(pair, busy) {
    for (const record of [pair.gl, ...pair.cells]) {
      record.element.classList.toggle('is-loading', busy);
      record.panel?.setBusy?.(busy);
    }
  }

  /** A card that failed: no stale picture, and the reason in its place. */
  failCard(record, error) {
    record.error = describeError(error);
    this.blank(record);
    this.showMessage(record, record.error, { kind: 'error', retry: !isRefusal(error) });
    this.onRendered(record.spec.id, null);
  }

  /** The whole pair failed before either half was asked for (the densest pick). */
  failPair(pair, error) {
    for (const record of [pair.gl, ...pair.cells]) this.failCard(record, error);
  }

  /** Take a card's picture down. */
  blank(record) {
    record.panel?.clear?.();
    record.chart?.clear?.();
    // A blank chart has no camera to refit: a resize must not draw an empty box.
    record.fit = null;
    if (record.legend) {
      record.legend.replaceChildren();
      record.legend.hidden = true;
    }
    if (record.sparse) writeSparseNote(record.sparse, []);
  }

  /**
   * Say on a card why it shows nothing: `kind` 'error' (a failed or refused
   * request; a fault that may pass offers a retry), 'disabled' (a shut gate)
   * or 'notice' (no WebGL, a lost context).
   */
  showMessage(record, text, { kind = 'error', retry = false } = {}) {
    const line = make('p', '', text);
    const nodes = [line];
    if (retry) {
      const button = make('button', 'action', 'Retry');
      button.type = 'button';
      button.dataset.retry = record.spec.id;
      button.title = 'Ask the server again for this view';
      button.addEventListener('click', () => {
        const pair = this.pairs[record.spec.pair];
        if (pair?.entry) this.lazy.invalidate(pair.element);
        this.refreshVisible();
      });
      nodes.push(button);
    }
    record.message.replaceChildren(...nodes);
    record.message.dataset.kind = kind;
    record.message.hidden = false;
  }

  hideMessage(record) {
    record.message.hidden = true;
    record.message.replaceChildren();
    delete record.message.dataset.kind;
  }

  /** Reflect the view state, the plan and the event in hand on the 3-D cards' controls. */
  syncControls() {
    const event = this.pairs.event;
    if (event?.gl) {
      const c = event.gl.controls;
      const n = this.value('voxel_event');
      if (c.number) c.number.value = Number.isInteger(n) ? String(n) : '';
      const shown = event.payloads.voxels?.event ?? event.payloads.raster?.event ?? null;
      if (c.prev) c.prev.disabled = !Number.isInteger(shown?.prev);
      if (c.next) c.next.disabled = !Number.isInteger(shown?.next);
      if (c.densest) c.densest.classList.toggle('is-active', !Number.isInteger(n));
      const view = this.eventView();
      if (c.showers) {
        c.showers.hidden = (this.offer.nShowers ?? 2) !== 2;
        for (const [value, button] of c.showerButtons) button.classList.toggle('is-active', value === view.shower);
      }
      this.syncChannel(c.channel, this.offer.event, view.channel);
      c.reset.disabled = !event.model;
    }
    const ensemble = this.pairs.ensemble;
    if (ensemble?.gl) {
      const c = ensemble.gl.controls;
      this.syncChannel(c.channel, this.offer.ensemble, this.ensembleView().channel);
      c.reset.disabled = !ensemble.model;
    }
  }

  /** A channel select: the drawn channel selected, the ones the experiment cannot serve disabled with why. */
  syncChannel(select, view, drawn) {
    if (!select) return;
    for (const option of select.options) {
      const shut = !view.channels.includes(option.value);
      option.disabled = shut;
      option.title = shut ? (view.disabledChannels[option.value] ?? 'Not available for this experiment.') : '';
    }
    if (drawn) select.value = drawn;
    select.disabled = view.channels.length < 2;
  }

  /* ---------------------------------------------------- page-level calls */

  /** Re-lay every created chart out at its container's size. */
  relayout() {
    for (const record of this.cards.values()) {
      if (record.chart) this.resizeChart(record);
      else record.panel?.relayout?.();
    }
  }

  /** Redraw everything in hand with the current palette; no request. */
  repaint() {
    for (const pair of Object.values(this.pairs)) {
      if (!pair.view) continue;
      if (pair.name === 'event' && pair.payloads.raster) {
        this.drawEventCells(pair, { status: 'fulfilled', value: pair.payloads.raster });
      }
      if (pair.name === 'ensemble' && pair.payloads.projections) {
        this.drawEnsembleCells(pair, { status: 'fulfilled', value: pair.payloads.projections });
      }
      if (pair.model) this.paintGl(pair, { keepCamera: true });
    }
  }

  /**
   * Forget everything this experiment showed: abort the requests in flight,
   * drop the kept responses, clear every chart (the WebGL charts stay, empty)
   * and blank every card. The next refresh (or scroll) loads afresh.
   */
  reset() {
    for (const key of Object.values(VOXEL_ABORT_KEYS)) abortRequest(key);
    this.generation += 1;
    this.cache.clear();
    this.inflight.clear();
    this.seed = FIRST_SEED;
    this.pickRule = null;
    for (const pair of Object.values(this.pairs)) {
      pair.view = null;
      pair.payloads = {};
      pair.model = null;
      pair.built = null;
      pair.pick = null;
      pair.hidden = new Set();
      pair.loading = null;
      this.setPairBusy(pair, false);
      for (const record of [pair.gl, ...pair.cells]) {
        this.blank(record);
        record.error = null;
        this.setCaption(record, []);
        if (!record.disabled) this.hideMessage(record);
      }
    }
    this.syncControls();
    this.lazy.forget();
  }

  /* ------------------------------------------------------ drawer, export */

  /** The sentences that tie a projection to its 3-D view. */
  pairing(pair) {
    if (pair.name === 'event') {
      const view = pair.view ?? {};
      const lines = [view.projectionNote];
      lines.push('Paired with the 3-D view of the same event, in the same frame; these are the Event '
        + 'Inspector\'s rasters of the energy density'
        + (view.channel && view.channel !== 'energy'
          ? `, while the 3-D view colours its cubes by ${EVENT_CHANNEL_LABELS[view.channel] ?? view.channel}.`
          : '.'));
      return lines;
    }
    return ['Paired with the 3-D cloud of the same selection, frame and channel: the Physics page\'s spatial '
      + 'panels on their Native Grid (raw 20 mm accumulation bins, no display smoothing), each with its own '
      + 'window, floor and disclosures.'];
  }

  /** The drawer's notes of one card. */
  notes(id, { state = this.state, experiment = this.getExperiment() } = {}) {
    const record = this.cards.get(id);
    if (!record) return null;
    const pair = this.pairs[record.spec.pair];
    const title = record.title.textContent;
    const shut = (text) => ({ title, hazards: [], sections: [{ heading: SECTION.disclosures, lines: [text] }] });
    if (record.disabled) return shut(record.disabled);
    if (record.spec.gl) {
      if (!this.glAvailable()) return shut(GL_UNAVAILABLE);
      const payload = pair.payloads.voxels;
      if (!payload) return record.error ? shut(record.error) : null;
      const drawn = pair.built ?? null;
      const gl = record.lost ? GL_LOST : null;
      if (pair.name === 'event') {
        return voxelEventNotes({
          payload, drawn, hidden: [...pair.hidden], gl, state, experiment, title,
          pick: Number.isInteger(this.value('voxel_event')) ? null : pair.pick,
          fallbacks: pair.view?.notes ?? [],
        });
      }
      return voxelEnsembleNotes({
        payload, drawn, gl, state, experiment, title, fallbacks: pair.view?.notes ?? [], crop: pair.model?.crop ?? null,
      });
    }
    const payload = pair.name === 'event' ? pair.payloads.raster : pair.payloads.projections;
    if (!payload) return record.error ? shut(record.error) : null;
    const col = record.spec.col;
    return voxelProjectionNotes({
      pair: pair.name, payload, panelId: col, frameKind: pair.view?.frame ?? 'lab',
      view: record.panel?.currentView?.() ?? null, isometric: { [col]: Boolean(record.panel?.isometric) },
      pairing: this.pairing(pair), state, experiment, title,
    });
  }

  /**
   * `{panel, meta}` for the exporter: the 2-D projections only (a 3-D card
   * never exports); null when nothing is drawn; undefined for a foreign id.
   */
  exportTarget(id) {
    const record = this.cards.get(id);
    if (!record) return undefined;
    if (record.spec.gl || record.disabled || !record.panel || record.error) return null;
    const pair = this.pairs[record.spec.pair];
    if (pair.name === 'event') {
      const raster = pair.payloads.raster;
      if (!raster) return null;
      const kind = pair.view?.frame ?? 'lab';
      return {
        panel: record.panel,
        meta: {
          ...raster.meta,
          frame: kind === 'lab' ? undefined : kind,
          channel: 'density',
          event: raster.event?.event_number,
          shower: raster.event?.shower?.key,
        },
      };
    }
    const payload = pair.payloads.projections;
    return payload ? { panel: record.panel, meta: { ...(payload.meta ?? {}) } } : null;
  }

  /** The warnings of the payloads in hand that their cards' drawers do not state. */
  warnings() {
    const out = [];
    for (const record of this.cards.values()) {
      const pair = this.pairs[record.spec.pair];
      const payload = record.spec.gl ? pair.payloads.voxels
        : (pair.name === 'event' ? pair.payloads.raster : pair.payloads.projections);
      if (!payload || record.disabled) continue;
      out.push(...warningsNotShown(payload.meta?.warnings ?? [], notesText(this.notes(record.spec.id))));
    }
    return warningsNotShown(out);
  }
}
