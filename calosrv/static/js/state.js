/* Central interface state, and its serialisation to the URL hash.
 *
 * Keeping the whole selection in the hash means a physicist can bookmark or
 * paste a link to an exact view - experiment, slider bounds, display mode,
 * resolution and channel - and get that view back rather than the defaults.
 * For a diagnostic tool whose output ends up in a discussion, that is the
 * difference between "look at this" and "set these six controls".
 *
 * ## Four reference frames, one radio group
 *
 * `frame` is one of `lab | trans | local | canonical`, and the interface opens
 * in the laboratory frame. The API takes that choice as two parameters - the
 * coordinate system (lab, trans, local) and whether the lab coordinates are
 * co-registered into the canonical frame - and `apiFrame` is the one place
 * the mapping lives, so the two can never disagree. Links that relied on the
 * old canonical default now open in the laboratory frame; an explicit
 * `#frame=canonical` still opens the canonical frame.
 *
 * ## One display mode per frame
 *
 * The frames open in different display modes, because the same word means a
 * different thing in each. In the laboratory frame Native is the detector
 * lattice itself - one bin per cell, the hardware truth - so it is the default.
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
};
const NUMERIC_RANGE = { resolution: [50, 400] };

/** The filter sliders' steps (main.js), by which their domains snap outward. */
const SLIDER_STEP = { e1: 0.05, e2: 0.05, d: 1 };

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

const DEFAULTS = {
  table_name: null,
  e1_min: null, e1_max: null,
  e2_min: null, e2_max: null,
  d_min: null, d_max: null,
  include_undefined_d: false,
  // Reference frame of the three spatial panels. The interface opens in the
  // laboratory frame, on the detector's own coordinates; the translated,
  // local and canonical frames are one radio away.
  frame: 'lab',
  // Reference peak of a co-registered density ramp: this selection's own peak
  // (the directive's a.u.) or the whole dataset's, for cross-selection colour.
  rho_norm: 'selection',
  // Display mode per frame (see the header): the lab keeps the hardware
  // lattice, the co-registered frames open on their kernel reconstruction.
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
};

const NUMERIC = new Set([
  'e1_min', 'e1_max', 'e2_min', 'e2_max', 'd_min', 'd_max', 'resolution',
]);
const BOOLEAN = new Set(['include_undefined_d', 'lock_scale']);

export class State {
  constructor() {
    this.values = { ...DEFAULTS };
    this.bounds = null;       // kinematic bounds of the active experiment
    this.domains = null;      // snapped slider domains, for the full-range test
    this.touched = new Set(); // axes the user has deliberately narrowed
    this.listeners = new Set();
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

  /** Parameters for the filter-bearing endpoints. */
  filterParams() {
    const v = this.values;
    return {
      table_name: v.table_name,
      e1_min: v.e1_min, e1_max: v.e1_max,
      e2_min: v.e2_min, e2_max: v.e2_max,
      d_min: v.d_min, d_max: v.d_max,
      include_undefined_d: v.include_undefined_d,
    };
  }

  projectionParams(preview = false) {
    const v = this.values;
    const lab = v.frame === 'lab';
    return {
      ...this.filterParams(),
      ...apiFrame(v.frame),
      model: v.model,
      channel: v.channel,
      // Always sent, never left to the API default: the server keeps
      // `display=native` for its own contract, while the co-registered
      // frames here open in Continuous Field.
      display: this.get('display'),
      resolution: v.resolution,
      weighting: v.weighting,
      // Each control only where it means something; undefined is dropped
      // from the query, so a co-registered response never carries the
      // "lock_scale ignored" notice for a box nobody could see.
      rho_norm: lab ? undefined : v.rho_norm,
      lock_scale: lab ? v.lock_scale : undefined,
      preview,
    };
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
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return;
    const params = new URLSearchParams(hash);
    // A pre-split `display=` is held until the frame is known, because the
    // frame may come later in the hash than the display does.
    let legacyDisplay = null;
    for (const [key, raw] of params.entries()) {
      if (key === 'display') {
        if (DISPLAYS.has(raw)) legacyDisplay = raw;
        continue;
      }
      if (!(key in DEFAULTS)) continue;
      if (NUMERIC.has(key)) {
        const value = Number(raw);
        const range = NUMERIC_RANGE[key];
        if (Number.isFinite(value) && (!range || (value >= range[0] && value <= range[1]))) {
          this.values[key] = value;
        }
      } else if (BOOLEAN.has(key)) {
        this.values[key] = raw === 'true' || raw === '1';
      } else if (key.startsWith('display_')) {
        // An unknown mode would be sent to the API verbatim and rejected
        // there, blanking all three panels; the default is kept instead.
        if (DISPLAYS.has(raw)) this.values[key] = raw;
      } else if (ENUMS[key]) {
        // Likewise for every enumerated control: a stale or mistyped link
        // falls back to the default rather than to a 422.
        if (ENUMS[key].includes(raw)) this.values[key] = raw;
      } else {
        this.values[key] = raw;
      }
    }
    // The legacy key names the active frame's mode, unless the link also
    // carries that frame's own key, which is the more specific statement.
    const active = displayKey(this.values.frame);
    if (legacyDisplay && !params.has(active)) this.values[active] = legacyDisplay;
  }

  writeHash() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(this.values)) {
      if (value === null || value === undefined) continue;
      if (value === DEFAULTS[key]) continue;
      // A bound that spans the whole available range says nothing, so leave it
      // out and keep the link short enough to paste into a message.
      if (this.isFullRangeBound(key, value)) continue;
      params.set(key, NUMERIC.has(key) ? String(round(key, value)) : String(value));
    }
    const hash = params.toString();
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
};

function round(key, value) {
  const digits = PRECISION[key] ?? 2;
  return Number(Number(value).toFixed(digits));
}
