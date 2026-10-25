/* The Physics page's section below the 2 x 2 diagnostic: the reference
 * notebooks' physics figures as nine cards, each loaded when it scrolls into
 * view and again only when its request changes (lazy_cards.js).
 *
 * The cards are built here, at construction, with the anatomy of every other
 * card on the page (`.card[data-panel]`, Details first in the toolbar, the
 * plot-only Export last), so the shell's Details delegation and the export
 * menu's `[data-export]` wiring cover them: main.js constructs the section
 * before `attachExportMenus`. Card-local controls use attributes of their own
 * (`data-profile-axis`, `data-physics-shower`, ...) and never `data-shower`,
 * `data-roi` or `data-reset`, which main.js wires on the 2 x 2; no id starts
 * with `event-` or `compare-`, which the drawer and the exporter route to the
 * frame grids.
 *
 * Which cards are on show, and which are shut with the server's reason, is
 * the experiment's plan (capabilities.js `page1Plan`); a shut card says why in
 * its plot area and, when a rebuild of the derived tables would open it,
 * offers the Admin Settings panel that runs one.
 *
 * Requests are shared: B1, B2 and the resolution card are three readings of
 * one /api/response, and the two profile cards of one /api/profiles (the ρ
 * axis is served with either depth), so one key feeds every card that needs
 * it - joined while in flight, and kept in a small cache so a card scrolled to
 * later costs no second request. A palette change, an A/B/Both filter and the
 * y-scale are repaints of the payload in hand.
 *
 * The panel classes are fetched the first time a card that needs one is
 * drawn (`import()`, stamped like every static import), so the cards nobody
 * scrolls to cost nothing, and a panel module that fails to load fails its
 * cards, with the reason on them, never the page. Tests inject classes of
 * their own (`panelClasses`).
 *
 * The notes of each card - the Details drawer - come from panel_notes.js by
 * name (`profileNotes`, `responseNotes`, ...), read off the module at call
 * time; a builder that does not exist yet falls back to the payload's own
 * notes rather than to nothing.
 */

import { getJson, abortRequest, isAbort } from './api.js';
import { LazyCards, requestKey, isRefusal } from './lazy_cards.js';
import * as notesModule from './panel_notes.js';
import { describeError, writeSparseNote } from './page_common.js';

/** Where each panel class lives; fetched on first use. */
const PANEL_MODULES = {
  ProfilePanel: () => import('./panels/profile.js'),
  ResponsePanel: () => import('./panels/response.js'),
  ResponseGridPanel: () => import('./panels/response_grid.js'),
  DistributionPanel: () => import('./panels/distribution.js'),
  CorrelationPanel: () => import('./panels/correlation.js'),
  StatisticsPanel: () => import('./panels/statistics.js'),
};

/** B3 is served by the energy panel's route, sliced by momentum. */
export const B3_ROUTE = '/api/energy-distribution';

const EXPORT_TITLE = 'Export this panel\'s plot as a publication figure (white background, 300 DPI, '
  + 'plot area only — see Details for its disclosures)';
const DETAILS_TITLE = 'Methodology and disclosures for this panel';

/**
 * The nine cards, in page order. `group` is the request a card shares;
 * `mode` is the ResponsePanel reading; `table` is a DOM table, not a chart.
 */
export const PHYSICS_CARDS = Object.freeze([
  { id: 'profile-w', title: 'Longitudinal Profile along w', panel: 'ProfilePanel', group: 'profile', exportable: true },
  { id: 'profile-r', title: 'Radial Profile along ρ', panel: 'ProfilePanel', group: 'profile', exportable: true },
  {
    id: 'response-b1', title: 'Sampling Fraction — Per-Event Distribution', panel: 'ResponsePanel',
    mode: 'b1', group: 'response', exportable: true,
  },
  {
    id: 'response-b2', title: 'Sampling Fraction vs. Incident Momentum', panel: 'ResponsePanel',
    mode: 'b2', group: 'response', exportable: true,
  },
  {
    id: 'response-res', title: 'Relative Resolution σ/μ vs. Incident Momentum', panel: 'ResponsePanel',
    mode: 'resolution', group: 'response', exportable: true,
  },
  {
    id: 'response-b3', title: 'Response vs. Incident Momentum p', panel: 'ResponseGridPanel',
    group: 'b3', exportable: true, wide: true, tall: true, fitTable: true,
  },
  { id: 'distribution', title: 'Distributions by Momentum Bin', panel: 'DistributionPanel', group: 'distribution', exportable: true },
  { id: 'correlation', title: 'Hit-level Pearson Correlation', panel: 'CorrelationPanel', group: 'correlation', exportable: true },
  {
    id: 'statistics', title: 'Selection Statistics — describe()', panel: 'StatisticsPanel',
    group: 'statistics', exportable: false, wide: true, table: true,
  },
]);

const SPEC = Object.fromEntries(PHYSICS_CARDS.map((spec) => [spec.id, spec]));

/* One abort key per shared request group: a newer request of a group
 * supersedes the older, and the cards that read one response share its key.
 * The design listed one key per profile card; the two profile cards share a
 * request whenever their parameters agree, so they share its key too, and
 * take one each (`-w`, `-r`) only while their notebook conventions differ
 * and they read two responses (cardRequest). */
const ABORT_KEYS = {
  profile: 'physics-profile',
  response: 'physics-response',
  b3: 'physics-b3',
  distribution: 'physics-distribution',
  correlation: 'physics-correlation',
  statistics: 'physics-statistics',
};

/** The drawer's builder of each card, by its name in panel_notes.js. */
const NOTE_BUILDERS = {
  'profile-w': 'profileNotes',
  'profile-r': 'profileNotes',
  'response-b1': 'responseNotes',
  'response-b2': 'responseNotes',
  'response-res': 'responseNotes',
  'response-b3': 'responseGridNotes',
  distribution: 'distributionNotes',
  correlation: 'correlationNotes',
  statistics: 'statisticsNotes',
};

/** The incident-kinematics quantities, which take a per-shower or a per-hit weighting. */
const SHOWER_QUANTITIES = new Set(['theta', 'phi', 'p']);

/* The cards' own controls. Ephemeral, like the energy panel's A/B/Both: they
 * belong to a card, not to the view a link restores. Two-shower experiments
 * pool A and B under `both`; a single-shower one has one shower and no toggle.
 * The resolution card draws one of its two quantities at a time - σ/μ of the
 * calibrated energy or of the response ratio - so both showers make two
 * series, not four. */
export const DEFAULT_CONTROLS = Object.freeze({
  profileShower: 'both',
  profileDepth: 'w',
  profileNotebook: false,
  profileRNotebook: false,
  b1Shower: 'both',
  b2Shower: 'both',
  resShower: 'both',
  resQuantity: 'calibrated_energy',
  b3Slices: 'notebook',
  b3Shower: 'both',
  distQuantity: 'theta',
  distWeighting: 'shower',
  distScale: 'linear',
  distShower: 'both',
  corrCoord: 'local',
  corrScale: 'linear',
  corrShower: 'both',
  statCoord: 'local',
  statShower: 'both',
});

const SHOWER_CHOICES = [
  { value: 'a', label: 'A', title: 'Shower A only' },
  { value: 'b', label: 'B', title: 'Shower B only' },
  { value: 'both', label: 'Both', title: 'Showers A and B' },
];

const QUANTITY_LABELS = {
  theta: 'θ — incident polar angle',
  phi: 'φ — incident azimuth',
  p: 'p — incident momentum',
  u: 'u — Local lateral',
  v: 'v — Local lateral',
  w: 'w — Local depth',
  energy: 'Hit energy',
};

/** The coordinate frame of the hit-level cards, as each experiment kind names it. */
function coordChoices(plan) {
  const single = plan?.nShowers === 1;
  const all = [
    { value: 'local', label: 'Local (u, v, w)' },
    { value: 'trans', label: single ? 'Translated (Δx, Δy, layer)' : 'Per-shower translated (Δx, Δy, layer)' },
    { value: 'lab', label: 'Absolute (x, y, z)' },
  ];
  const offered = plan?.coordSystems ?? ['local'];
  return all.filter((choice) => offered.includes(choice.value));
}

const twoShowers = (plan) => (plan?.nShowers ?? 2) === 2;

/**
 * The toolbar controls of each card. `request: true` changes the card's
 * request (a reload), otherwise the control repaints the payload in hand.
 * `disabled` returns the reason a control is off, or null.
 */
const CARD_CONTROLS = {
  'profile-w': [
    {
      name: 'profileDepth', kind: 'seg', attr: 'profileAxis', label: 'Depth axis', request: true,
      choices: () => [
        { value: 'w', label: 'w (Local)', title: 'Depth along each shower\'s incident direction, Local frame, layer-pitch bins anchored at w = 0' },
        { value: 'native', label: 'Layers (native)', title: 'Each shower\'s own sampling layers counted from its first, not rotated' },
      ],
    },
    {
      name: 'profileNotebook', kind: 'toggle', attr: 'profileNotebook', label: 'Notebook convention', request: true,
      title: 'The reference notebook\'s convention: hits behind the entry plane (w < −10⁻⁶ mm) are '
        + 'dropped from every bin and from each shower\'s normaliser',
      disabled: (plan, c) => (c.profileDepth === 'native'
        ? 'The notebook convention is defined along w: it is not available with native layers.' : null),
    },
    {
      name: 'profileShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', request: true,
      choices: () => SHOWER_CHOICES, visible: twoShowers,
    },
  ],
  'profile-r': [
    {
      // The radial card's own flag: the convention changes each shower's
      // normaliser, so it changes this card's numbers, and this card says so.
      name: 'profileRNotebook', kind: 'toggle', attr: 'profileNotebook', label: 'Notebook convention', request: true,
      title: 'The reference notebook\'s convention on the radial profile: hits behind the entry plane '
        + '(w < −10⁻⁶ mm) are dropped from every bin and from each shower\'s normaliser',
    },
    {
      name: 'profileShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', request: true,
      choices: () => SHOWER_CHOICES, visible: twoShowers,
    },
  ],
  'response-b1': [
    { name: 'b1Shower', kind: 'seg', attr: 'physicsShower', label: 'Showers', choices: () => SHOWER_CHOICES, visible: twoShowers },
  ],
  'response-b2': [
    { name: 'b2Shower', kind: 'seg', attr: 'physicsShower', label: 'Showers', choices: () => SHOWER_CHOICES, visible: twoShowers },
  ],
  'response-res': [
    {
      name: 'resQuantity', kind: 'seg', attr: 'resolutionQuantity', label: 'Quantity',
      choices: () => [
        { value: 'calibrated_energy', label: 'c · E_dep', title: 'σ/μ of the calibrated energy c · E_dep' },
        { value: 'response_ratio', label: 'E_dep / p', title: 'σ/μ of the response ratio E_dep / p' },
      ],
    },
    { name: 'resShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', choices: () => SHOWER_CHOICES, visible: twoShowers },
  ],
  'response-b3': [
    {
      name: 'b3Slices', kind: 'seg', attr: 'b3Slices', label: 'Momentum slices', request: true,
      choices: () => [
        { value: 'notebook', label: 'Windows', title: 'The calibration notebook\'s windows: 1, 2, 5, 10, 15 and 19 GeV ± 0.5 GeV' },
        { value: 'bins', label: '1 GeV bins', title: 'The producer\'s 1 GeV momentum bins' },
      ],
    },
    { name: 'b3Shower', kind: 'seg', attr: 'physicsShower', label: 'Showers', choices: () => SHOWER_CHOICES, visible: twoShowers },
  ],
  distribution: [
    {
      name: 'distQuantity', kind: 'select', attr: 'distributionQuantity', label: 'Quantity', request: true,
      choices: (plan) => (plan?.quantities ?? ['theta', 'phi', 'p'])
        .map((value) => ({ value, label: QUANTITY_LABELS[value] ?? value })),
    },
    {
      name: 'distWeighting', kind: 'seg', attr: 'distributionWeighting', label: 'Weighting', request: true,
      choices: () => [
        { value: 'shower', label: 'Per shower', title: 'Each shower counted once' },
        { value: 'hit', label: 'Per hit', title: 'Each shower weighted by its hit count: the reference notebook\'s hit sample, computed exactly' },
      ],
      visible: (plan, c) => SHOWER_QUANTITIES.has(c.distQuantity),
    },
    {
      name: 'distScale', kind: 'seg', attr: 'distributionY', label: 'Vertical scale',
      choices: () => [
        { value: 'linear', label: 'Linear', title: 'Counts from zero' },
        { value: 'log', label: 'Log y', title: 'Counts on a logarithmic axis from one; empty bins are not drawn' },
      ],
    },
    {
      name: 'distShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', request: true,
      choices: () => SHOWER_CHOICES, visible: twoShowers,
    },
  ],
  correlation: [
    { name: 'corrCoord', kind: 'select', attr: 'physicsFrame', label: 'Coordinates', request: true, choices: coordChoices },
    {
      name: 'corrScale', kind: 'seg', attr: 'physicsEnergyScale', label: 'Energy scale', request: true,
      choices: () => [
        { value: 'linear', label: 'E', title: 'Hit energy in GeV, as the notebook' },
        { value: 'log10', label: 'log₁₀ E', title: 'The base-10 logarithm of the hit energy' },
      ],
    },
    {
      name: 'corrShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', request: true,
      choices: () => SHOWER_CHOICES, visible: twoShowers,
    },
  ],
  statistics: [
    { name: 'statCoord', kind: 'select', attr: 'physicsFrame', label: 'Coordinates', request: true, choices: coordChoices },
    {
      name: 'statShower', kind: 'seg', attr: 'physicsShower', label: 'Showers', request: true,
      choices: () => SHOWER_CHOICES, visible: twoShowers,
    },
  ],
};

/** The control specs of one card. */
export function cardControls(id) {
  return CARD_CONTROLS[id] ?? [];
}

/**
 * Bring the controls into line with a plan: a choice the experiment does not
 * offer falls back to its first offered one, and a single-shower experiment
 * asks for its one shower. Returns a new object.
 */
export function reconcileControls(controls, plan) {
  const out = { ...DEFAULT_CONTROLS, ...controls };
  const quantities = plan?.quantities ?? ['theta', 'phi', 'p'];
  if (!quantities.includes(out.distQuantity)) out.distQuantity = quantities[0];
  const coords = coordChoices(plan).map((c) => c.value);
  for (const key of ['corrCoord', 'statCoord']) {
    if (!coords.includes(out[key])) out[key] = coords.includes('local') ? 'local' : (coords[0] ?? 'local');
  }
  if (!twoShowers(plan)) {
    for (const key of ['profileShower', 'b1Shower', 'b2Shower', 'resShower', 'b3Shower', 'distShower',
      'corrShower', 'statShower']) out[key] = 'both';
  }
  if (out.profileDepth === 'native') out.profileNotebook = false;
  return out;
}

/* Appended to a profile card's title while the card draws the notebook's
 * convention, so the card, its drawer and the reader agree on which numbers
 * are shown. */
export const NOTEBOOK_SUFFIX = ' (notebook convention)';

/** Whether a profile card draws the notebook's convention: each card owns its flag. */
export function notebookOf(id, controls = DEFAULT_CONTROLS) {
  if (id === 'profile-r') return Boolean(controls.profileRNotebook);
  if (id === 'profile-w') return Boolean(controls.profileNotebook) && controls.profileDepth === 'w';
  return false;
}

/**
 * The card's title: the longitudinal profile names its depth axis, with the
 * native-layer title its Details drawer gives itself (panel_notes.js), so the
 * card and its drawer never disagree; a profile card under the notebook's
 * convention says so.
 */
export function cardTitle(id, controls = DEFAULT_CONTROLS) {
  const c = { ...DEFAULT_CONTROLS, ...controls };
  const suffix = notebookOf(id, c) ? NOTEBOOK_SUFFIX : '';
  if (id === 'profile-w') {
    return c.profileDepth === 'native'
      ? (notesModule.PHYSICS_TITLES?.['profile-native'] ?? 'Longitudinal Profile (native layers)')
      : `Longitudinal Profile along w${suffix}`;
  }
  return `${SPEC[id]?.title ?? id}${suffix}`;
}

/**
 * One profile card's parameters: its own notebook flag, and the longitudinal
 * card's depth axis - the ρ axis is served with either depth, so the radial
 * card asks with it and the two cards share one response whenever their
 * conventions agree. The notebook's convention is defined along w (a 422 on
 * native layers), so a card under it asks along w.
 */
function profileParams(id, c, filters, shower) {
  const notebook = notebookOf(id, c);
  return {
    ...filters,
    shower,
    depth: notebook ? 'w' : c.profileDepth,
    notebook: notebook ? true : undefined,
  };
}

/**
 * The request of one card: `{route, params, abortKey}`, or null when the card
 * does not apply. `filters` is `State.filterParams()`, which already holds
 * only the experiment's own filter axes. Pure.
 */
export function cardRequest(id, { filters, controls = DEFAULT_CONTROLS, plan = null }) {
  const spec = SPEC[id];
  if (!spec || !filters?.table_name) return null;
  const c = reconcileControls(controls, plan);
  const two = twoShowers(plan);
  const shower = (value) => (two ? value : undefined);
  const abortKey = ABORT_KEYS[spec.group];
  switch (spec.group) {
    case 'profile': {
      // The two cards read one response while their parameters agree, under
      // the group's key; apart, each takes a key of its own so neither
      // request supersedes the other's.
      const params = profileParams(id, c, filters, shower(c.profileShower));
      const other = profileParams(id === 'profile-r' ? 'profile-w' : 'profile-r', c, filters, shower(c.profileShower));
      const shared = requestKey('/api/profiles', params) === requestKey('/api/profiles', other);
      return {
        route: '/api/profiles',
        abortKey: shared ? abortKey : `${abortKey}-${id === 'profile-r' ? 'r' : 'w'}`,
        params,
      };
    }
    case 'response':
      return { route: '/api/response', abortKey, params: { ...filters } };
    case 'b3':
      return {
        route: B3_ROUTE,
        abortKey,
        params: { ...filters, slice_by: 'momentum', p_slices: c.b3Slices === 'bins' ? 'bins' : 'notebook' },
      };
    case 'distribution':
      return {
        route: '/api/distributions',
        abortKey,
        params: {
          ...filters,
          quantity: c.distQuantity,
          weighting: SHOWER_QUANTITIES.has(c.distQuantity) ? c.distWeighting : undefined,
          shower: shower(c.distShower),
        },
      };
    case 'correlation':
      return {
        route: '/api/correlations',
        abortKey,
        params: { ...filters, coord_system: c.corrCoord, energy_scale: c.corrScale, shower: shower(c.corrShower) },
      };
    case 'statistics':
      return {
        route: '/api/statistics',
        abortKey,
        params: { ...filters, coord_system: c.statCoord, shower: shower(c.statShower) },
      };
    default:
      return null;
  }
}

/**
 * What a card's panel is rendered with. `axis` is the key of `payload.axes`
 * a profile card draws ('w' or 'kt' for the longitudinal card, 'r' for the
 * radial one); `card` is the card id; `mode` the ResponsePanel reading;
 * `shower` the A/B/Both filter of the payload in hand; `yScale` and
 * `quantity` the distribution card's. Pure.
 */
export function cardOptions(id, { controls = DEFAULT_CONTROLS, palette = 'viridis', plan = null, payload = null } = {}) {
  const spec = SPEC[id];
  const c = reconcileControls(controls, plan);
  const opts = { palette, card: id };
  if (!spec) return opts;
  if (spec.group === 'profile') {
    opts.axis = id === 'profile-r' ? 'r' : (payload?.depth === 'native' || payload?.axes?.kt ? 'kt' : 'w');
    opts.shower = c.profileShower;
  } else if (spec.group === 'response') {
    opts.mode = spec.mode;
    opts.shower = { 'response-b1': c.b1Shower, 'response-b2': c.b2Shower, 'response-res': c.resShower }[id];
    if (id === 'response-res') opts.quantity = c.resQuantity;
  } else if (spec.group === 'b3') {
    opts.shower = c.b3Shower;
  } else if (spec.group === 'distribution') {
    opts.yScale = c.distScale;
    opts.quantity = payload?.meta?.quantity ?? c.distQuantity;
  }
  return opts;
}

/** What an exported physics figure is named by: its response's meta and frame. */
export function exportMeta(payload) {
  const meta = { ...(payload?.meta ?? {}) };
  const coord = meta.coord_system ?? payload?.coord_system;
  if (coord) meta.coord_system = coord;
  return meta;
}

/** Plain notes from the payload's own lines, when no builder exists for a card. */
function fallbackNotes(title, payload) {
  const lines = [...(payload?.notes ?? []), ...(payload?.meta?.warnings ?? [])].filter((l) => typeof l === 'string');
  return {
    title,
    hazards: [],
    sections: lines.length ? [{ heading: notesModule.SECTION?.drawn ?? 'What is drawn', lines }] : [],
  };
}

/** The drawer of a card that is shut: the server's reason, nothing else. */
function shutNotes(title, reason) {
  return {
    title,
    hazards: [],
    sections: [{ heading: notesModule.SECTION?.disclosures ?? 'Disclosures', lines: [reason] }],
  };
}

/**
 * The notes of one card for a payload, from panel_notes.js by name. Pure in
 * everything but the module it reads.
 */
export function physicsNotes(id, payload, { state = null, experiment = null, opts = {}, title = null } = {}) {
  const heading = title ?? cardTitle(id);
  if (!payload) return null;
  const builder = notesModule[NOTE_BUILDERS[id]];
  if (typeof builder !== 'function') return fallbackNotes(heading, payload);
  const notes = builder({
    payload, state, experiment, title: heading, card: id,
    mode: opts.mode, axis: opts.axis, shower: opts.shower, yScale: opts.yScale, quantity: opts.quantity,
  });
  return notes ?? fallbackNotes(heading, payload);
}

/** Every line of a notes object, joined; '' for none. */
function notesText(notes) {
  if (typeof notesModule.notesText === 'function') return notesModule.notesText(notes);
  return (notes?.sections ?? []).flatMap((section) => section.lines).join(' ');
}

/** The warnings `text` does not already state. */
function unsaid(warnings, text) {
  if (typeof notesModule.warningsNotShown === 'function') return notesModule.warningsNotShown(warnings, text);
  return warnings.filter((w) => !String(text).includes(w));
}

/** A panel class by name: an injected one, else its module's export. */
export async function loadPanelClass(name, injected = null) {
  if (injected && typeof injected[name] === 'function') return injected[name];
  const load = PANEL_MODULES[name];
  if (!load) throw new Error(`Unknown panel ${name}.`);
  const module = await load();
  const Class = module[name];
  if (typeof Class !== 'function') throw new Error(`The ${name} module does not export ${name}.`);
  return Class;
}

/** How many responses the section keeps for cards scrolled to later. */
const CACHE_SIZE = 24;

export class PhysicsSection {
  /**
   * @param {HTMLElement} section  the `#physics-grid` section
   * @param {object} options
   *   `state` the interface State; `getExperiment()` the active experiment;
   *   `onRendered(id, payload|null)` after a card drew (or failed), so the
   *   page can rebuild its notes; `onError(error, context)` for a load the
   *   observer started; `onOpenAdmin()` for a shut card's rebuild offer;
   *   `root` the scroll container; `panelClasses` overrides the panel
   *   classes by name (tests).
   */
  constructor(section, {
    state, getExperiment = () => null, onRendered = () => {}, onError = () => {},
    onOpenAdmin = null, root = null, panelClasses = null,
  } = {}) {
    this.section = section;
    this.state = state;
    this.getExperiment = getExperiment;
    this.onRendered = onRendered;
    this.onError = onError;
    this.onOpenAdmin = onOpenAdmin;
    this.panelClasses = panelClasses;
    this.plan = null;
    this.controls = { ...DEFAULT_CONTROLS };
    this.cards = new Map();
    this.cache = new Map();
    this.inflight = new Map();
    // Bumped by `reset()` and `invalidate()`: a response that lands after
    // either belongs to what was forgotten and is not cached.
    this.generation = 0;
    // What the 2 x 2's plot 4 is (page1Plan), which sets the response grid's slices.
    this.plot4 = undefined;
    this.lazy = new LazyCards({
      root,
      // In view means in view: the plan's decision D3 (Martin), not the
      // design's '200px 0px' prefetch margin.
      rootMargin: '0px',
      onError: (error, element) => this.onError(error, this.titleOf(element)),
    });
    if (!section) return;
    for (const spec of PHYSICS_CARDS) this.buildCard(spec);
  }

  /* ------------------------------------------------------------- markup */

  buildCard(spec) {
    const { id } = spec;
    const card = document.createElement('div');
    card.className = `card physics-card${spec.wide ? ' is-wide' : ''}`;
    card.dataset.panel = id;
    card.hidden = true;

    const heading = document.createElement('h2');
    const title = document.createElement('span');
    title.className = 'title';
    title.id = `title-${id}`;
    title.title = 'Open the panel\'s methodology and disclosures';
    title.textContent = cardTitle(id, this.controls);
    const actions = document.createElement('span');
    actions.className = 'card-actions';

    const details = document.createElement('button');
    details.type = 'button';
    details.className = 'mini';
    details.dataset.inspect = id;
    details.setAttribute('aria-controls', 'inspector');
    details.setAttribute('aria-expanded', 'false');
    details.title = DETAILS_TITLE;
    details.textContent = 'Details';
    actions.append(details);

    const controls = {};
    for (const control of cardControls(id)) {
      const built = this.buildControl(id, control);
      controls[control.name] = built;
      actions.append(built.element);
    }

    let exporter = null;
    if (spec.exportable) {
      exporter = document.createElement('button');
      exporter.type = 'button';
      exporter.className = 'mini';
      exporter.dataset.export = id;
      exporter.setAttribute('aria-haspopup', 'menu');
      exporter.title = EXPORT_TITLE;
      exporter.append('Export ', document.createTextNode('▾'));
      actions.append(exporter);
    }
    heading.append(title, actions);

    const frame = document.createElement('div');
    frame.className = 'plot-frame';
    const plot = document.createElement('div');
    plot.className = spec.table ? 'card-table' : `plot${spec.tall ? ' tall' : ''}`;
    plot.id = `plot-${id}`;
    const message = document.createElement('div');
    message.className = 'card-error';
    message.setAttribute('role', 'status');
    message.hidden = true;
    frame.append(plot, message);
    card.append(heading, frame);
    // The response grid's key counts and its fitted μ and σ, as plot 4 carries
    // them on the energy card: the panel writes both after each draw.
    let sparse = null;
    let table = null;
    if (spec.fitTable) {
      sparse = document.createElement('div');
      sparse.className = 'sparse-note';
      sparse.id = `energy-sparse-${id}`;
      sparse.hidden = true;
      table = document.createElement('div');
      table.className = 'card-fit-table';
      table.id = `fit-table-${id}`;
      card.append(sparse, table);
    }
    this.section.append(card);

    const record = {
      spec, element: card, title, details, plot, message, exporter, controls, sparse, table,
      panel: null, panelPromise: null, payload: null, opts: null, disabled: null, error: null, loading: null,
    };
    this.cards.set(id, record);
    this.lazy.watch(card, {
      key: () => this.keyOf(id),
      load: (key) => this.loadCard(record, key),
    });
    return record;
  }

  /** One toolbar control: a segmented group of buttons, a select, or a toggle button. */
  buildControl(id, control) {
    if (control.kind === 'select') {
      const select = document.createElement('select');
      select.className = 'mini-select';
      select.dataset[control.attr] = id;
      select.setAttribute('aria-label', control.label);
      select.title = control.label;
      select.addEventListener('change', () => this.setControl(control, select.value));
      return { element: select, select, control };
    }
    if (control.kind === 'toggle') {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      button.dataset[control.attr] = id;
      button.setAttribute('aria-pressed', 'false');
      button.textContent = control.label;
      button.addEventListener('click', () => this.setControl(control, !this.controls[control.name]));
      return { element: button, button, control };
    }
    const group = document.createElement('span');
    group.className = 'seg';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', control.label);
    const buttons = new Map();
    for (const choice of control.choices(this.plan, this.controls)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      button.dataset[control.attr] = choice.value;
      button.textContent = choice.label;
      if (choice.title) button.title = choice.title;
      button.addEventListener('click', () => this.setControl(control, choice.value));
      buttons.set(choice.value, button);
      group.append(button);
    }
    return { element: group, buttons, control };
  }

  /** Reflect the controls' values, visibility and availability on every card. */
  syncControls() {
    for (const record of this.cards.values()) {
      for (const built of Object.values(record.controls)) {
        const { control, element } = built;
        const value = this.controls[control.name];
        // A shut card has nothing to steer: its controls go with its picture.
        element.hidden = Boolean(record.disabled)
          || (control.visible ? !control.visible(this.plan, this.controls) : false);
        const reason = control.disabled ? control.disabled(this.plan, this.controls) : null;
        if (built.select) {
          const choices = control.choices(this.plan, this.controls);
          const current = [...built.select.options].map((o) => o.value).join('|');
          if (current !== choices.map((c) => c.value).join('|')) {
            built.select.replaceChildren(...choices.map((choice) => {
              const option = document.createElement('option');
              option.value = choice.value;
              option.textContent = choice.label;
              return option;
            }));
          }
          built.select.value = value;
          built.select.disabled = Boolean(reason) || choices.length < 2;
        } else if (built.button) {
          built.button.classList.toggle('is-active', Boolean(value) && !reason);
          built.button.setAttribute('aria-pressed', String(Boolean(value) && !reason));
          built.button.disabled = Boolean(reason);
          built.button.title = reason ?? control.title ?? '';
        } else {
          for (const [choice, button] of built.buttons) button.classList.toggle('is-active', choice === value);
        }
      }
      record.title.textContent = cardTitle(record.spec.id, this.controls);
      if (record.exporter) record.exporter.disabled = Boolean(record.disabled);
    }
  }

  /* ------------------------------------------------------------- plan */

  /**
   * Show the cards of a plan: the applicable ones, each shut card with the
   * server's reason. Every card goes stale; the visible ones load on the
   * caller's next `refresh()`, the others when they scroll into view.
   */
  applyPlan(plan) {
    this.plan = plan;
    // The response grid's slices follow the kind: where plot 4 draws the
    // notebook's six windows (a single shower), the full-width card opens on
    // the 1 GeV bins it alone holds; elsewhere on the windows.
    const plot4 = plan?.plot4 ?? null;
    if (plot4 !== this.plot4) {
      this.plot4 = plot4;
      this.controls = { ...this.controls, b3Slices: plot4 === 'response-b3' ? 'bins' : 'notebook' };
    }
    this.controls = reconcileControls(this.controls, plan);
    const shown = new Set(plan?.physics ?? []);
    for (const [id, record] of this.cards) {
      record.element.hidden = !shown.has(id);
      record.disabled = shown.has(id) ? (plan.disabled?.[id] ?? null) : null;
      if (record.disabled) {
        this.blank(record);
        // The rebuild is offered where it is the reason: the server words a
        // stale experiment's shut gates exactly as its derived-table notice.
        const stale = plan.stale && (!plan.stale.notice || plan.stale.notice === record.disabled);
        this.showMessage(record, record.disabled, { offerRebuild: Boolean(stale) });
      } else if (record.message.dataset.kind === 'disabled') {
        this.hideMessage(record);
      }
    }
    this.syncControls();
    this.lazy.forget();
  }

  /** Every card id of the section (whether or not on show). */
  ids() {
    return [...this.cards.keys()];
  }

  /** Whether `id` is one of this section's cards. */
  has(id) {
    return this.cards.has(id);
  }

  /** The request key of one card now, or null when it does not load. */
  keyOf(id) {
    const record = this.cards.get(id);
    if (!record || !this.plan || record.element.hidden || record.disabled) return null;
    const request = cardRequest(id, { filters: this.state.filterParams(), controls: this.controls, plan: this.plan });
    return request ? requestKey(request.route, request.params) : null;
  }

  /* ------------------------------------------------------------ loading */

  /** Change one control: a request control reloads its cards, the others repaint. */
  setControl(control, value) {
    if (this.controls[control.name] === value) return;
    if (control.disabled && control.disabled(this.plan, { ...this.controls, [control.name]: value })) return;
    this.controls = reconcileControls({ ...this.controls, [control.name]: value }, this.plan);
    this.syncControls();
    if (control.request) {
      // The new key makes its cards stale; the visible ones load now.
      this.refreshVisible();
      return;
    }
    for (const record of this.cards.values()) {
      if (cardControls(record.spec.id).some((c) => c.name === control.name)) this.paint(record);
    }
  }

  /** The title of the card an element belongs to, for an error's context. */
  titleOf(element) {
    const record = [...this.cards.values()].find((r) => r.element === element);
    return record ? cardTitle(record.spec.id, this.controls) : 'physics card';
  }

  /** Load the visible stale cards after a card's own control changed, reporting failures one by one. */
  refreshVisible() {
    this.lazy.refresh().then((results) => {
      for (const result of results) {
        if (result.status === 'rejected' && !isAbort(result.reason)) {
          this.onError(result.reason, this.titleOf(result.element));
        }
      }
    });
  }

  /**
   * Load every visible card whose request changed. Rejects with one error
   * naming each card that failed (each also says so on itself); a superseded
   * request is not a failure.
   */
  async refresh() {
    if (!this.plan?.physics?.length) return [];
    const results = await this.lazy.refresh();
    const failures = results
      .filter((result) => result.status === 'rejected' && !isAbort(result.reason))
      .map((result) => `${this.titleOf(result.element)}: ${describeError(result.reason)}`);
    if (failures.length) throw new Error(failures.join('; '));
    return results;
  }

  /** The card's panel, created on first use. */
  async ensurePanel(record) {
    if (record.panel) return record.panel;
    if (!record.panelPromise) {
      record.panelPromise = (async () => {
        const Class = await loadPanelClass(record.spec.panel, this.panelClasses);
        // The card's own reading: the ResponsePanel part, the profile axis.
        const panel = new Class(record.plot, {
          mode: record.spec.mode,
          axis: record.spec.id === 'profile-r' ? 'r' : undefined,
        });
        record.panel = panel;
        return panel;
      })();
      // A failed import may succeed later (a transient network fault).
      record.panelPromise.catch(() => { record.panelPromise = null; });
    }
    return record.panelPromise;
  }

  async loadCard(record, key) {
    const request = cardRequest(record.spec.id, {
      filters: this.state.filterParams(), controls: this.controls, plan: this.plan,
    });
    if (!request || requestKey(request.route, request.params) !== key) return;
    // The load in charge of the card's busy state: one superseded by a newer
    // load (or forgotten by `reset`) leaves the newer one's state alone.
    const loading = {};
    record.loading = loading;
    this.setCardBusy(record, true);
    try {
      const panel = await this.ensurePanel(record);
      const payload = await this.fetchShared(request);
      // A newer request, or another experiment, may have taken the card over.
      if (this.keyOf(record.spec.id) !== key) return;
      record.payload = payload;
      record.error = null;
      this.hideMessage(record);
      this.draw(record, panel, payload);
      this.onRendered(record.spec.id, payload);
    } catch (error) {
      if (isAbort(error)) throw error;
      if (this.keyOf(record.spec.id) === key) {
        record.payload = null;
        record.error = describeError(error);
        this.blank(record);
        // A refusal is the server's answer to this request; anything else may
        // pass, and the card is asked again on its next visibility, the next
        // refresh, or now.
        this.showMessage(record, record.error, { offerRetry: !isRefusal(error) });
        this.onRendered(record.spec.id, null);
      }
      throw error;
    } finally {
      if (record.loading === loading) {
        record.loading = null;
        this.setCardBusy(record, false);
      }
    }
  }

  /** One response per key: joined while in flight, kept for a card scrolled to later. */
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
      // A response that lands after a reset belongs to what was forgotten.
      if (generation !== this.generation) return;
      this.cache.set(key, payload);
      while (this.cache.size > CACHE_SIZE) this.cache.delete(this.cache.keys().next().value);
    }, () => {}).finally(() => {
      if (this.inflight.get(key) === promise) this.inflight.delete(key);
    });
    return promise;
  }

  /** Draw a payload on its card's panel with the card's current options. */
  draw(record, panel, payload) {
    record.opts = cardOptions(record.spec.id, {
      controls: this.controls, palette: this.state.get('palette'), plan: this.plan, payload,
    });
    panel.render(payload, record.opts);
    // The response grid's fitted μ and σ and its key counts, from the panel.
    if (record.table && typeof panel.renderTable === 'function') panel.renderTable(record.table);
    if (record.sparse) writeSparseNote(record.sparse, typeof panel.sparseLines === 'function' ? panel.sparseLines() : []);
  }

  /** Redraw one card from the payload in hand (a palette or a render-only control). */
  paint(record) {
    if (!record.panel || !record.payload || record.element.hidden) return;
    this.draw(record, record.panel, record.payload);
    this.onRendered(record.spec.id, record.payload);
  }

  /** Every drawn card again, with the current palette; no request. */
  repaint() {
    for (const record of this.cards.values()) this.paint(record);
  }

  /** Re-lay every created chart out at its container's size. */
  relayout() {
    for (const record of this.cards.values()) {
      if (record.panel && !record.element.hidden) record.panel.relayout?.();
    }
  }

  setCardBusy(record, busy) {
    record.element.classList.toggle('is-loading', busy);
    record.panel?.setBusy?.(busy);
  }

  /** Take a card's picture down: a failed or shut card keeps no stale picture. */
  blank(record) {
    record.payload = null;
    record.opts = null;
    record.panel?.clear?.();
    record.table?.replaceChildren();
    if (record.sparse) writeSparseNote(record.sparse, []);
  }

  /**
   * Say on the card why it shows nothing: a load that failed, or a gate the
   * server shut. A card shut for want of a derived-table rebuild offers the
   * Admin Settings panel that runs one.
   */
  showMessage(record, text, { offerRebuild = false, offerRetry = false } = {}) {
    const line = document.createElement('p');
    line.textContent = text;
    const nodes = [line];
    if (offerRetry) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'action';
      button.dataset.retry = record.spec.id;
      button.textContent = 'Retry';
      button.title = 'Ask the server again for this card';
      button.addEventListener('click', () => {
        this.lazy.invalidate(record.element);
        this.refreshVisible();
      });
      nodes.push(button);
    }
    if (offerRebuild && typeof this.onOpenAdmin === 'function') {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'action';
      button.dataset.openAdmin = record.spec.id;
      button.textContent = 'Rebuild derived tables…';
      button.title = 'Open Admin Settings, where an experiment\'s derived tables are rebuilt from its archive';
      button.addEventListener('click', () => this.onOpenAdmin());
      nodes.push(button);
    }
    record.message.replaceChildren(...nodes);
    record.message.dataset.kind = record.disabled ? 'disabled' : 'error';
    record.message.hidden = false;
  }

  hideMessage(record) {
    record.message.hidden = true;
    record.message.replaceChildren();
    delete record.message.dataset.kind;
  }

  /**
   * Forget everything this experiment showed: abort the requests in flight,
   * drop the cached responses, blank every card. The next refresh (or scroll)
   * loads afresh.
   */
  reset() {
    for (const key of Object.values(ABORT_KEYS)) {
      abortRequest(key);
      // The per-card keys the profile cards take while their requests differ.
      if (key === ABORT_KEYS.profile) for (const part of ['w', 'r']) abortRequest(`${key}-${part}`);
    }
    this.generation += 1;
    this.cache.clear();
    this.inflight.clear();
    for (const record of this.cards.values()) {
      this.blank(record);
      record.error = null;
      // No load of the previous experiment holds the card busy any more.
      record.loading = null;
      this.setCardBusy(record, false);
      if (!record.disabled) this.hideMessage(record);
    }
    this.lazy.forget();
  }

  /** Drop cached responses without blanking: the same experiment, reactivated. */
  invalidate() {
    this.generation += 1;
    this.cache.clear();
    this.inflight.clear();
    this.lazy.forget();
  }

  /**
   * Bring a card into view with some of its controls set - plot 4's link to
   * the full-width response grid, which alone holds the 1 GeV bins. A card
   * already in view loads its new request at once; one scrolled to loads as
   * it comes in. Returns whether the card is on show.
   */
  reveal(id, controls = {}) {
    const record = this.cards.get(id);
    if (!record || record.element.hidden) return false;
    const next = reconcileControls({ ...this.controls, ...controls }, this.plan);
    const changed = Object.keys(controls).some((name) => next[name] !== this.controls[name]);
    this.controls = next;
    this.syncControls();
    record.element.scrollIntoView?.({ block: 'start' });
    record.details?.focus?.({ preventScroll: true });
    if (changed) this.refreshVisible();
    return true;
  }

  /**
   * The response a card reads, through the shared request and its cache, for
   * a page readout that needs it whether or not the card is in view (the
   * event-level kind's Events count). Null when the card does not load.
   */
  async payloadOf(id) {
    const record = this.cards.get(id);
    if (!record || !this.plan || record.element.hidden || record.disabled) return null;
    const request = cardRequest(id, { filters: this.state.filterParams(), controls: this.controls, plan: this.plan });
    return request ? this.fetchShared(request) : null;
  }

  /* ------------------------------------------------------ drawer, export */

  /** The drawer's notes of one card. */
  notes(id, { state = this.state, experiment = this.getExperiment() } = {}) {
    const record = this.cards.get(id);
    if (!record) return null;
    const title = cardTitle(id, this.controls);
    if (record.disabled) return shutNotes(title, record.disabled);
    if (!record.payload) return record.error ? shutNotes(title, record.error) : null;
    return physicsNotes(id, record.payload, { state, experiment, opts: record.opts ?? {}, title });
  }

  /** `{panel, meta}` for the exporter; null when nothing is drawn; undefined for a foreign id. */
  exportTarget(id) {
    const record = this.cards.get(id);
    if (!record) return undefined;
    if (!record.spec.exportable || record.element.hidden || record.disabled) return null;
    if (!record.panel || !record.payload) return null;
    return { panel: record.panel, meta: exportMeta(record.payload) };
  }

  /**
   * The warnings of the cards on show that their own drawer does not state,
   * for the page's banner: a disclosure lives in the Details drawer, and the
   * banner keeps what the reader could not otherwise see.
   */
  warnings() {
    const out = [];
    for (const record of this.cards.values()) {
      if (record.element.hidden || !record.payload) continue;
      const said = notesText(this.notes(record.spec.id));
      out.push(...unsaid(record.payload.meta?.warnings ?? [], said));
    }
    return out;
  }

  /** A panel of this section's classes on another host (plot 4's response grid). */
  async createPanel(name, element, options = {}) {
    const Class = await loadPanelClass(name, this.panelClasses);
    return new Class(element, options);
  }
}
