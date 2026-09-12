/* Central interface state, and its serialisation to the URL hash.
 *
 * Keeping the whole selection in the hash means a physicist can bookmark or
 * paste a link to an exact view - experiment, slider bounds, display mode,
 * resolution and channel - and get that view back rather than the defaults.
 * For a diagnostic tool whose output ends up in a discussion, that is the
 * difference between "look at this" and "set these six controls".
 */

const DEFAULTS = {
  table_name: null,
  e1_min: null, e1_max: null,
  e2_min: null, e2_max: null,
  d_min: null, d_max: null,
  include_undefined_d: false,
  display: 'native',
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
    this.listeners = new Set();
    this.readHash();
  }

  get(key) { return this.values[key]; }

  /** Apply a patch, notify listeners, and sync the URL. Returns true if changed. */
  set(patch, { silent = false } = {}) {
    let changed = false;
    for (const [key, value] of Object.entries(patch)) {
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
    return {
      ...this.filterParams(),
      display: v.display,
      resolution: v.resolution,
      mode: v.channel,
      weighting: v.weighting,
      lock_scale: v.lock_scale,
      preview,
    };
  }

  /**
   * Adopt an experiment's bounds, resetting any slider still at full range.
   *
   * A bound the user has actually moved is kept when possible, so switching
   * between two runs of the same detector does not silently discard a
   * selection. A bound that no longer fits the new dataset is dropped rather
   * than clamped, because a clamped bound looks deliberate and is not.
   */
  adoptBounds(bounds) {
    const previous = this.bounds;
    this.bounds = bounds;
    const patch = {};
    for (const [axis, range] of Object.entries(bounds)) {
      const [lo, hi] = range;
      if (lo === null || hi === null) continue;
      const loKey = `${axis}_min`;
      const hiKey = `${axis}_max`;
      const wasDefault =
        this.values[loKey] === null ||
        (previous && previous[axis] &&
          this.values[loKey] === previous[axis][0] &&
          this.values[hiKey] === previous[axis][1]);
      const outOfRange =
        this.values[loKey] !== null &&
        (this.values[loKey] < lo || this.values[hiKey] > hi);
      if (wasDefault || outOfRange) {
        patch[loKey] = lo;
        patch[hiKey] = hi;
      }
    }
    this.set(patch, { silent: true });
    this.writeHash();
    return patch;
  }

  readHash() {
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return;
    const params = new URLSearchParams(hash);
    for (const [key, raw] of params.entries()) {
      if (!(key in DEFAULTS)) continue;
      if (NUMERIC.has(key)) {
        const value = Number(raw);
        if (Number.isFinite(value)) this.values[key] = value;
      } else if (BOOLEAN.has(key)) {
        this.values[key] = raw === 'true' || raw === '1';
      } else {
        this.values[key] = raw;
      }
    }
  }

  writeHash() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(this.values)) {
      if (value === null || value === undefined) continue;
      if (value === DEFAULTS[key]) continue;
      params.set(key, NUMERIC.has(key) ? String(round(value)) : String(value));
    }
    const hash = params.toString();
    const url = `${window.location.pathname}${hash ? `#${hash}` : ''}`;
    window.history.replaceState(null, '', url);
  }
}

function round(value) {
  return Math.abs(value) >= 1000 ? Math.round(value) : Number(value.toFixed(4));
}
