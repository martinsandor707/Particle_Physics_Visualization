/* Central interface state, and its serialisation to the URL hash.
 *
 * Keeping the whole selection in the hash means a physicist can bookmark or
 * paste a link to an exact view - experiment, slider bounds, display mode,
 * resolution and channel - and get that view back rather than the defaults.
 * For a diagnostic tool whose output ends up in a discussion, that is the
 * difference between "look at this" and "set these six controls".
 *
 * ## Four reference frames, one stored key
 *
 * `frame` is one of `lab | trans | local | canonical`, and the interface opens
 * in the Absolute view (`lab`). The sidebar shows the key as two tiers -
 * Absolute | Separation-Aligned (D-Frame), with Translated (`canonical`) and
 * Local (`local`) nested under the second, and the legacy per-shower `trans`
 * revealed only while a link or a saved default holds it (labels.js
 * FRAME_TREE) - but only the key is stored, written to the hash and saved as
 * a default. The API takes that choice as two parameters - the coordinate
 * system (lab, trans, local) and whether the lab coordinates are
 * co-registered into the canonical frame - and `apiFrame` is the one place
 * the mapping lives, so the two can never disagree. Links that relied on the
 * old canonical default now open in the Absolute view; an explicit
 * `#frame=canonical` still opens the D-frame.
 *
 * ## One display mode per frame
 *
 * The frames open in different display modes, because the same word means a
 * different thing in each. In the absolute (detector) frame Native is the
 * detector lattice itself - one bin per cell, the hardware truth - so it is
 * the default.
 * In a co-registered frame (translated, local, canonical) Native is the raw
 * 20 mm accumulation grid, the audit view, and the kernel reconstruction is
 * the picture.
 *
 * So the state holds `display_<frame>` for each frame, and `display`
 * addresses whichever belongs to the active frame: `get('display')` and
 * `set({display})` keep their meaning for every caller, and switching frame
 * and back returns each frame to the mode it was left in. The hash writes a key
 * only when it differs from its default, as for every other value.
 *
 * Links written before the split carried at most one `display=`. It is read as
 * the active frame's mode, so `#display=native` still opens whichever frame the
 * link names in Native.
 */

import { SEQUENTIAL_PALETTES } from './palette.js';

export const FRAMES = ['lab', 'trans', 'local', 'canonical'];
export const CHANNELS = ['density', 'gradcam', 'gradcam_energy', 'shapcam', 'shapcam_energy'];
export const MODELS = ['segmentation', 'energy', 'angle'];
/* The D-frame's two entry-anchor definitions (API `anchor`): each shower's
 * back-projected 3-D centroid, or its first-layer entry point P₀. */
export const ANCHORS = ['backprojected', 'p0'];
/* The Event Inspector draws one of an event's two showers at a time. */
export const SHOWERS = ['a', 'b'];

/* ## The Models page's keys
 *
 * The Models page (/models) shares `table_name`, the filters, `frame` and
 * `model` with the Physics page, so a tab switch carries the view across, and
 * adds keys of its own. Neither page strips the other's keys: each writes
 * every value that differs from the built-in one, so a link opened on either
 * page keeps both pages' state. `event` and `shower` pin the Physics page's
 * Event Inspector and are never reused here: the 3-D event view has its own
 * `voxel_event` and `voxel_shower`, so opening the Models page never pins an
 * event on the Physics page, nor the reverse. */

/* The per-event features the explorer offers (GET /api/features?view=catalog):
 * the 19 features of the aggregate, plus the two circular companions a hit
 * experiment adds. labels.js names them; a test keeps the two lists equal. */
export const FEATURE_KEYS = Object.freeze([
  'width', 'height', 'depth', 'depth_range', 'volume', 'num_hits', 'total_hit_energy',
  'centroid_x', 'centroid_y', 'centroid_z', 'mean_r', 'std_r', 'max_r', 'weighted_r_mean',
  'avg_theta', 'avg_phi', 'avg_phi_circ', 'angular_spread', 'angular_spread_circ',
  'numerical_density', 'energy_density',
]);
/* The feature explorer's momentum classes: the features notebook's windows,
 * or the aggregate's stored label (p < 2 against p ≥ 2 GeV). */
export const FEATURE_CLASSES = Object.freeze(['windows', 'label']);
/* Whose features the explorer draws on two-shower data (a new key: `shower`
 * is the Physics page's Event Inspector's). One-shower data has only A. */
export const FEATURE_SHOWERS = Object.freeze(['a', 'b']);
/* The 3-D event view: one shower of the event, or both (two-shower data). */
export const VOXEL_SHOWERS = Object.freeze(['a', 'b', 'both']);
/* The 3-D views' channels (GET /api/event?format=voxels, GET /api/voxels). */
export const VOXEL_CHANNELS = Object.freeze(['energy', 'gradcam', 'shapcam', 'segerr', 'species']);
export const ENSEMBLE_CHANNELS = Object.freeze(['density', 'gradcam_energy', 'shapcam_energy']);
/* The XGBoost views: the regressor's task, and which of the angle model's two
 * outputs a per-label view draws. */
export const XGB_TASKS = Object.freeze(['momentum', 'angle']);
export const XGB_LABELS = Object.freeze(['phi', 'theta']);

/** The two display modes the API accepts. */
const DISPLAYS = new Set(['native', 'continuous']);

/** Values a link may carry for each enumerated key; anything else keeps the default. */
const ENUMS = {
  frame: FRAMES,
  channel: CHANNELS,
  model: MODELS,
  rho_norm: ['selection', 'dataset'],
  weighting: ['energy', 'count'],
  palette: SEQUENTIAL_PALETTES,
  anchor: ANCHORS,
  shower: SHOWERS,
  feature: FEATURE_KEYS,
  fclass: FEATURE_CLASSES,
  fshower: FEATURE_SHOWERS,
  voxel_shower: VOXEL_SHOWERS,
  voxel_channel: VOXEL_CHANNELS,
  ens_channel: ENSEMBLE_CHANNELS,
  xgb_task: XGB_TASKS,
  xgb_label: XGB_LABELS,
};
const NUMERIC_RANGE = { resolution: [50, 400] };

/** The filter sliders' steps (controls/filter_block.js), by which their domains snap outward. */
export const SLIDER_STEP = Object.freeze({ e1: 0.05, e2: 0.05, d: 1 });

/** The three filter axes a link can carry, each a `<key>_min` / `<key>_max` pair. */
const FILTER_KEYS = ['e1', 'e2', 'd'];

/**
 * A slider's domain: the physical range snapped outward to whole steps.
 *
 * The same arithmetic as RangeSlider.setBounds, so the domain the hash is
 * compared against and the one the slider draws can never disagree.
 */
export function snapDomain(lo, hi, step) {
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
}

/** Each interface frame as the API's (coord_system, frame) pair. */
export const API_FRAME = {
  lab: { coord_system: 'lab', frame: 'lab' },
  trans: { coord_system: 'trans', frame: 'lab' },
  local: { coord_system: 'local', frame: 'lab' },
  canonical: { coord_system: 'lab', frame: 'canonical' },
};

export function apiFrame(frame) {
  return API_FRAME[frame] ?? API_FRAME.lab;
}

/** Whether a frame co-registers events or showers (everything but the lab). */
export function isCoregistered(frame) {
  return FRAMES.includes(frame) && frame !== 'lab';
}

/** The state key holding one frame's display mode. */
function displayKey(frame) {
  return FRAMES.includes(frame) ? `display_${frame}` : 'display_lab';
}

/* The built-in view, and the reference every link is written against.
 *
 * Frozen, and never to be edited in place: writeHash omits every value equal to
 * these, so an absent key in a saved link means "the built-in value". Changing
 * one would silently re-read every bookmark that relied on it. A team's own
 * opening view is set in the Admin Settings panel instead (applyDefaults), and
 * calosrv/admin/schema.py holds the same values (a test keeps them equal). */
export const DEFAULTS = Object.freeze({
  table_name: null,
  e1_min: null, e1_max: null,
  e2_min: null, e2_max: null,
  d_min: null, d_max: null,
  include_undefined_d: false,
  // Reference frame of the three spatial panels. The interface opens in the
  // Absolute view, on the detector's own coordinates; the Separation-Aligned
  // frames are one radio away.
  frame: 'lab',
  // Reference peak of a co-registered density ramp: this selection's own peak
  // (the directive's a.u.) or the whole dataset's, for cross-selection colour.
  rho_norm: 'selection',
  // The D-frame's entry anchor: the back-projected 3-D centroid the frame
  // shipped with, or the first-layer entry point P₀ (the notebook's origin).
  anchor: 'backprojected',
  // Display mode per frame (see the header): the absolute frame keeps the
  // hardware lattice, the co-registered frames open on their kernel
  // reconstruction.
  display_lab: 'native',
  display_trans: 'continuous',
  display_local: 'continuous',
  display_canonical: 'continuous',
  resolution: 150,
  channel: 'density',
  weighting: 'energy',
  palette: 'viridis',
  lock_scale: true,
  model: 'segmentation',
  // The Event Inspector: the pinned event (null = the ensemble panels) and
  // which of its two showers is drawn; and the compare-frames view, which
  // lays the selection out in the Absolute, per-shower translated and Local
  // frames at once. All three are view state, so a link carries them.
  event: null,
  shower: 'a',
  compare: false,
  // The Models page (see "The Models page's keys" above). The feature the
  // explorer's histograms draw, the classes it splits the selection into and,
  // on two-shower data, whose features (shower A or B); the 3-D event view's
  // event (null = none chosen yet: the view offers the densest), shower and
  // channel; the ensemble cloud's channel; the XGBoost task and, for the angle
  // model, which output a per-label view draws.
  feature: 'num_hits',
  fclass: 'windows',
  fshower: 'a',
  voxel_event: null,
  voxel_shower: 'a',
  voxel_channel: 'energy',
  ens_channel: 'density',
  xgb_task: 'momentum',
  xgb_label: 'theta',
});

const NUMERIC = new Set([
  'e1_min', 'e1_max', 'e2_min', 'e2_max', 'd_min', 'd_max', 'resolution', 'event', 'voxel_event',
]);
/* Whole, non-negative numbers: an event number is an identifier, so a
 * fraction or a negative in a link names nothing and keeps the default. */
const INTEGER = new Set(['event', 'voxel_event']);
const BOOLEAN = new Set(['include_undefined_d', 'lock_scale', 'compare']);

/* The keys the Admin Settings panel's defaults may set on a cold boot. */
const DEFAULTABLE = ['table_name', 'frame', 'model', 'channel', 'rho_norm'];

/**
 * The value `raw` gives `key`, or undefined when it may not set it.
 *
 * One rule for a link and for a saved default alike: an unknown mode or a
 * mistyped enum keeps the built-in value rather than reaching the API, where it
 * would be rejected and blank every panel.
 */
function acceptValue(key, raw) {
  if (!(key in DEFAULTS)) return undefined;
  if (NUMERIC.has(key)) {
    const value = Number(raw);
    const range = NUMERIC_RANGE[key];
    if (INTEGER.has(key) && !(Number.isInteger(value) && value >= 0)) return undefined;
    return Number.isFinite(value) && (!range || (value >= range[0] && value <= range[1]))
      ? value : undefined;
  }
  if (BOOLEAN.has(key)) return raw === true || raw === 'true' || raw === '1';
  if (key.startsWith('display_')) return DISPLAYS.has(raw) ? raw : undefined;
  if (ENUMS[key]) return ENUMS[key].includes(raw) ? raw : undefined;
  // table_name: checked against the experiment list when the view loads.
  return typeof raw === 'string' && raw ? raw : undefined;
}

export class State {
  constructor() {
    this.values = { ...DEFAULTS };
    this.bounds = null;       // kinematic bounds of the active experiment
    this.domains = null;      // snapped slider domains, for the full-range test
    this.touched = new Set(); // axes the user has deliberately narrowed
    // The active experiment's filter axes, as capabilities.js describes them;
    // null until one is adopted, which means the two-shower set (e1, e2, d).
    this.filterAxes = null;
    this.listeners = new Set();
    this.defaultsApplied = false; // applyDefaults runs at most once
    this.readHash();
    // A bound arriving in the URL is a deliberate selection, so it must survive
    // the first adoptBounds rather than being reset to the dataset range.
    for (const axis of ['e1', 'e2', 'd']) {
      // Either bound: a link omits a bound left at the full range, so one
      // narrowed only from above carries only its maximum.
      if (this.values[`${axis}_min`] !== null || this.values[`${axis}_max`] !== null) {
        this.touched.add(axis);
      }
    }
  }

  get(key) {
    if (key === 'display') return this.values[displayKey(this.values.frame)];
    return this.values[key];
  }

  /** Whether the page opened on a link without any view state. */
  get coldBoot() {
    return this.hashKeys.size === 0;
  }

  /**
   * Adopt the Admin Settings panel's defaults, on a cold boot only, and once.
   *
   * A link carrying any view state keeps all of it. An absent key in a link
   * means "built-in value", because writeHash omits exactly those, so filling
   * the gaps from today's defaults would re-read an old bookmark whenever new
   * ones were saved. Nothing is written or marked touched here: the first
   * writeHash then records every value that differs from the built-in view, so
   * the session's own link never depends on the defaults again.
   *
   * `defaults.display` (null for "each frame's own") applies to the default
   * frame. Returns whether this was the cold boot that took them.
   */
  applyDefaults(defaults) {
    if (this.defaultsApplied || !this.coldBoot || !defaults) return false;
    this.defaultsApplied = true;
    const patch = {};
    for (const key of DEFAULTABLE) {
      if (defaults[key] === null || defaults[key] === undefined) continue;
      const value = acceptValue(key, defaults[key]);
      if (value !== undefined) patch[key] = value;
    }
    if (defaults.display !== null && defaults.display !== undefined) {
      const key = displayKey(patch.frame ?? this.values.frame);
      const value = acceptValue(key, defaults.display);
      if (value !== undefined) patch[key] = value;
    }
    Object.assign(this.values, patch);
    return true;
  }

  /** Apply a patch, notify listeners, and sync the URL. Returns true if changed. */
  set(patch, { silent = false } = {}) {
    let changed = false;
    // `display` is written onto the frame the patch leaves active, so a patch
    // carrying both a frame and a display does not depend on key order.
    // Listeners still receive the caller's own patch.
    const entries = Object.entries(patch).map(([key, value]) => (key === 'display'
      ? [displayKey(patch.frame ?? this.values.frame), value]
      : [key, value]));
    for (const [key, value] of entries) {
      if (this.values[key] !== value) {
        this.values[key] = value;
        changed = true;
      }
    }
    if (changed && !silent) {
      this.writeHash();
      for (const listener of this.listeners) listener(this.values, patch);
    }
    return changed;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Parameters for the filter-bearing endpoints.
   *
   * Only the active experiment's axes are sent: a single-shower experiment
   * filters on e1 alone (its incident momentum p), and the server refuses an
   * e2, d or include_undefined_d it has no axis for. Before an experiment is
   * adopted, and for every two-shower one, these are the seven keys they
   * always were, in the same order.
   */
  filterParams() {
    const v = this.values;
    const active = this.activeAxes();
    const params = { table_name: v.table_name };
    for (const key of FILTER_KEYS) {
      if (!active.has(key)) continue;
      params[`${key}_min`] = v[`${key}_min`];
      params[`${key}_max`] = v[`${key}_max`];
    }
    if (active.has('d')) params.include_undefined_d = v.include_undefined_d;
    return params;
  }

  /** The keys of the active filter axes; all three while none is adopted. */
  activeAxes() {
    return new Set(this.filterAxes ? this.filterAxes.map((axis) => axis.key) : FILTER_KEYS);
  }

  /**
   * Adopt an experiment's filter axes (capabilities.js `filterAxes`).
   *
   * An axis the experiment does not have is cleared and untouched, and with D
   * goes the undefined-D option: a two-shower link opened on a single-shower
   * experiment must not carry an E₂ window into a request that would be
   * refused, nor into the next link written. Silent; the caller writes the
   * hash once the new bounds are adopted.
   */
  restrictAxes(axes) {
    this.filterAxes = Array.isArray(axes) && axes.length ? axes : null;
    const active = this.activeAxes();
    const patch = {};
    for (const key of FILTER_KEYS) {
      if (active.has(key)) continue;
      this.touched.delete(key);
      patch[`${key}_min`] = null;
      patch[`${key}_max`] = null;
    }
    if (!active.has('d')) patch.include_undefined_d = false;
    this.set(patch, { silent: true });
    return [...active];
  }

  /**
   * Adopt an experiment's bounds onto the snapped slider domains, with one
   * hash write.
   *
   * `adoptBounds` writes the hash before the slider domains are known, so for
   * an instant a link carries the raw dataset bounds (0.408 rather than the
   * full-range 0.40, which it then omits). Here the domains are recorded
   * first - `snapDomain`, the sliders' own arithmetic - then every axis takes
   * the bounds `adoptBounds` would give it, an untouched axis the whole
   * snapped domain, and the hash is written once, already free of full-range
   * bounds. An axis whose bounds are null (no D defined) keeps null values
   * and no domain. Returns the domains by axis.
   */
  adoptSnappedBounds(bounds) {
    this.bounds = bounds;
    const active = this.activeAxes();
    const domains = {};
    for (const key of FILTER_KEYS) {
      const range = bounds?.[key];
      const valid = active.has(key) && Array.isArray(range)
        && Number.isFinite(range[0]) && Number.isFinite(range[1]);
      domains[key] = valid
        ? snapDomain(range[0], range[1], this.stepOf(key)) : null;
    }
    this.setSliderDomains(domains);

    const patch = {};
    for (const key of FILTER_KEYS) {
      const domain = domains[key];
      if (!domain) continue;
      const [lo, hi] = domain;
      const loKey = `${key}_min`;
      const hiKey = `${key}_max`;
      if (!this.touched.has(key)) {
        patch[loKey] = lo;
        patch[hiKey] = hi;
        continue;
      }
      // A touched axis may carry one bound only; the other is the full range.
      const vlo = this.values[loKey] ?? lo;
      const vhi = this.values[hiKey] ?? hi;
      // The domain is already snapped outward, so a bound at its edge is in
      // range; one beyond it (by more than rounding) is from another dataset.
      const outOfRange = vlo < lo - 1e-9 || vhi > hi + 1e-9 || vlo > vhi;
      patch[loKey] = outOfRange ? lo : vlo;
      patch[hiKey] = outOfRange ? hi : vhi;
    }
    this.set(patch, { silent: true });
    this.writeHash();
    return domains;
  }

  /** The slider step of one axis: the adopted descriptor's, else the built-in one. */
  stepOf(key) {
    const axis = this.filterAxes?.find((a) => a.key === key);
    return Number.isFinite(axis?.step) && axis.step > 0 ? axis.step : SLIDER_STEP[key];
  }

  /**
   * Parameters of one projections request: the active frame's, or `frame`'s
   * - the compare-frames view asks for each frame in turn, each in the
   * display mode it keeps for itself.
   */
  projectionParams(preview = false, frame = this.values.frame) {
    const v = this.values;
    const lab = frame === 'lab';
    return {
      ...this.filterParams(),
      ...apiFrame(frame),
      model: v.model,
      channel: v.channel,
      // Always sent, never left to the API default: the server keeps
      // `display=native` for its own contract, while the co-registered
      // frames here open in Continuous Field.
      display: this.values[displayKey(frame)],
      resolution: v.resolution,
      weighting: v.weighting,
      // Each control only where it means something; undefined is dropped
      // from the query, so a co-registered response never carries the
      // "lock_scale ignored" notice for a box nobody could see.
      rho_norm: lab ? undefined : v.rho_norm,
      lock_scale: lab ? v.lock_scale : undefined,
      // The anchor is a D-frame choice; the API refuses it elsewhere.
      anchor: frame === 'canonical' ? v.anchor : undefined,
      preview,
    };
  }

  /** The Event Inspector: the pinned event and its shower, under the same filters. */
  eventParams() {
    const v = this.values;
    return { ...this.filterParams(), event_number: v.event, shower: v.shower };
  }

  /** The energy panel: the selected frame's segmentation network. */
  energyParams() {
    return { ...this.filterParams(), coord_system: apiFrame(this.values.frame).coord_system };
  }

  /** The metric cards: the selected network, in the selected frame. */
  performanceParams() {
    return { ...this.energyParams(), model: this.values.model };
  }

  /**
   * Record that the user has deliberately narrowed an axis.
   *
   * Tracked explicitly rather than inferred by comparing the current value
   * against the dataset bound. That inference used to work, but the sliders now
   * snap their domain to the step grid, so an untouched axis sits at 0.40 while
   * the dataset bound is 0.408067 - the comparison fails, and switching
   * experiments would carry the previous run's window across and silently
   * filter the new dataset down to a handful of events.
   */
  markTouched(axis) {
    this.touched.add(axis);
  }

  isTouched(axis) {
    return this.touched.has(axis);
  }

  /**
   * Adopt an experiment's bounds, resetting any axis the user has not narrowed.
   *
   * A bound the user actually moved is kept, so switching between two runs of
   * the same detector does not discard a selection. A bound that no longer fits
   * the new dataset is dropped rather than clamped, because a clamped bound
   * looks deliberate and is not.
   */
  adoptBounds(bounds) {
    this.bounds = bounds;
    const patch = {};
    for (const [axis, range] of Object.entries(bounds)) {
      const [lo, hi] = range;
      if (lo === null || hi === null) continue;
      const loKey = `${axis}_min`;
      const hiKey = `${axis}_max`;
      if (!this.touched.has(axis)) {
        patch[loKey] = lo;
        patch[hiKey] = hi;
        continue;
      }
      // A touched axis may carry one bound only; the other is the full range.
      const vlo = this.values[loKey] ?? lo;
      const vhi = this.values[hiKey] ?? hi;
      // The sliders snap their domain outward by up to one step, so a bound
      // left at the snapped edge lies just outside the raw range and is still
      // in range; only a bound past that is from another dataset.
      const step = SLIDER_STEP[axis] ?? 0;
      const outOfRange = vlo < lo - step - 1e-9 || vhi > hi + step + 1e-9 || vlo > vhi;
      if (outOfRange) {
        patch[loKey] = lo;
        patch[hiKey] = hi;
      } else {
        if (this.values[loKey] !== vlo) patch[loKey] = vlo;
        if (this.values[hiKey] !== vhi) patch[hiKey] = vhi;
      }
    }
    this.set(patch, { silent: true });
    this.writeHash();
    return patch;
  }

  /**
   * Record the snapped slider domains, so the hash can omit untouched axes.
   *
   * The sliders snap their domain outward to the step grid, so "the whole
   * range" is the snapped bound rather than the raw dataset bound; comparing
   * against the latter would never match and every link would carry all six.
   */
  setSliderDomains(domains) {
    this.domains = domains;
  }

  isFullRangeBound(key, value) {
    if (!this.domains) return false;
    const match = /^(e1|e2|d)_(min|max)$/.exec(key);
    if (!match) return false;
    const domain = this.domains[match[1]];
    if (!domain) return false;
    const edge = match[2] === 'min' ? domain[0] : domain[1];
    return Math.abs(value - edge) < 1e-9;
  }

  readHash() {
    // Every recognised key the link carries, valid or not: a link naming any
    // part of the view is a view link, and the saved defaults stay out of it.
    this.hashKeys = new Set();
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return;
    const params = new URLSearchParams(hash);
    // A pre-split `display=` is held until the frame is known, because the
    // frame may come later in the hash than the display does.
    let legacyDisplay = null;
    for (const [key, raw] of params.entries()) {
      if (key === 'display') {
        this.hashKeys.add(key);
        if (DISPLAYS.has(raw)) legacyDisplay = raw;
        continue;
      }
      if (!(key in DEFAULTS)) continue;
      this.hashKeys.add(key);
      const value = acceptValue(key, raw);
      if (value !== undefined) this.values[key] = value;
    }
    // The legacy key names the active frame's mode, unless the link also
    // carries that frame's own key, which is the more specific statement.
    const active = displayKey(this.values.frame);
    if (legacyDisplay && !params.has(active)) this.values[active] = legacyDisplay;
  }

  /**
   * The view as a link's hash, without the '#': every value that differs from
   * the built-in view. Pure - `writeHash` puts it in the address bar, and the
   * Methodology page builds its deep links from it without writing anything.
   */
  hashString() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(this.values)) {
      if (value === null || value === undefined) continue;
      if (value === DEFAULTS[key]) continue;
      // A bound that spans the whole available range says nothing, so leave it
      // out and keep the link short enough to paste into a message.
      if (this.isFullRangeBound(key, value)) continue;
      params.set(key, NUMERIC.has(key) ? String(round(key, value)) : String(value));
    }
    return params.toString();
  }

  writeHash() {
    const hash = this.hashString();
    const url = `${window.location.pathname}${hash ? `#${hash}` : ''}`;
    window.history.replaceState(null, '', url);
  }
}

/* Decimal places each filter bound is written with.
 *
 * These match the step of the matching numeric input, so a value the user typed
 * round-trips through the URL unchanged. The old rule - four decimals for
 * anything under 1000 - produced links full of 2.0455-style noise, which was a
 * symptom of the slider quantisation rather than of the formatting. */
const PRECISION = {
  e1_min: 2, e1_max: 2,
  e2_min: 2, e2_max: 2,
  d_min: 0, d_max: 0,
  resolution: 0,
  event: 0,
  voxel_event: 0,
};

function round(key, value) {
  const digits = PRECISION[key] ?? 2;
  return Number(Number(value).toFixed(digits));
}
