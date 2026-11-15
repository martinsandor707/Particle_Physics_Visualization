/* The sidebar's Particle Filter block, on both pages, and the one owner of
 * GET /api/event/candidates.
 *
 * Two range sliders - p, the incident momentum in GeV (step 0.05), and θ, the
 * incident polar angle in degrees (step 0.1) - narrow which events the event
 * pickers offer (event_picker.js says what that means). Their domains are the
 * dataset's own range of p and θ over the showers that deposited energy
 * (`bounds` of the candidates response), snapped outward to whole steps
 * (`state.js` `snapDomain`, RangeSlider's own arithmetic). Until the first
 * bounds arrive the sliders are disabled.
 *
 * A commit - release, Enter, blur, or Clear - writes the four view-state keys
 * and asks for the pool again; a bound left at its domain's edge is stored as
 * null, so a link carries only a bound that narrows. A drag previews nothing:
 * the count is cheap and is asked for on release. After its own commit the
 * block refreshes itself, then calls `onCommit()`; the page calls `refresh()`
 * after a filter (E₁, E₂, D) commit, since that moves the pool too. A count
 * that fails leaves no stale line or pool behind: the block says it could not
 * count, the pages are told there is no count, and a failure after the
 * block's own commit is reported through `onError` (the pages' banner).
 *
 * On an experiment switch (`adopt`) a bound that no longer fits the new
 * domain is dropped, with its axis's other bound, as E₁'s is, and the block
 * says so once. A single-shower experiment filters on θ alone: p is its
 * selection already, so the p control is hidden and its keys cleared
 * silently. The event-level kind has no event to pick, and the block hides.
 *
 * Text nodes only: a line holds payload numbers and is never parsed as markup.
 */

import { RangeSlider } from './range_slider.js';
import { getJson, isAbort } from '../api.js';
import { relabel, restoreLabel } from '../page_common.js';
import { snapDomain } from '../state.js';
import { typographic } from '../format.js';
import {
  CANDIDATES_ROUTE, PARTICLE_STEP, countLine, emptyLine, intervalText, scopeNote, unplaceableLine,
} from '../event_picker.js';

/** Each axis: its keys, its step and decimals, the payload's bounds field and its DOM ids. */
export const PARTICLE_AXES = Object.freeze({
  p: Object.freeze({
    key: 'p', min: 'particle_p_min', max: 'particle_p_max', step: PARTICLE_STEP.p, decimals: 2, unit: 'GeV',
    bounds: 'p_gev', symbol: 'p', unitText: ' GeV',
    ids: Object.freeze({ control: 'ctl-particle-p', lo: 'pp-lo', hi: 'pp-hi', fill: 'pp-fill',
      numLo: 'pp-num-lo', numHi: 'pp-num-hi' }),
  }),
  theta: Object.freeze({
    key: 'theta', min: 'particle_theta_min', max: 'particle_theta_max', step: PARTICLE_STEP.theta, decimals: 1,
    unit: '°', bounds: 'theta_deg', symbol: 'θ', unitText: '°',
    ids: Object.freeze({ control: 'ctl-particle-theta', lo: 'pt-lo', hi: 'pt-hi', fill: 'pt-fill',
      numLo: 'pt-num-lo', numHi: 'pt-num-hi' }),
  }),
});

/** The block's own element ids (static/index.html, static/models.html). */
export const PARTICLE_IDS = Object.freeze({
  group: 'group-particle',
  count: 'particle-count',
  scope: 'particle-scope',
  clear: 'particle-clear',
  thetaHint: 'particle-theta-hint',
});

/** The θ hint on single-shower data, whose one shower has its own column (the markup names A and B). */
export const SINGLE_THETA_HINT = 'Incident polar angle of the shower (incoming_theta), in degrees.';

/* ------------------------------------------------------------ pure parts -- */

/** A number rounded to `decimals`, so float dust never reaches a comparison or the state. */
function rounded(value, decimals) {
  return Number(Number(value).toFixed(decimals));
}

/**
 * An axis's slider domain from the payload's `bounds` pair: snapped outward
 * to whole steps and rounded to the axis's decimals; null when the pair is not
 * two finite numbers (no shower deposited energy), which keeps the slider
 * disabled.
 */
export function particleDomain(pair, axis) {
  const spec = typeof axis === 'string' ? PARTICLE_AXES[axis] : axis;
  if (!Array.isArray(pair) || !Number.isFinite(pair[0]) || !Number.isFinite(pair[1])) return null;
  const [lo, hi] = snapDomain(pair[0], pair[1], spec.step);
  return [rounded(lo, spec.decimals), rounded(hi, spec.decimals)];
}

/** Whether a value sits on a domain edge, to the axis's decimals. */
function atEdge(value, edge, decimals) {
  return Math.abs(rounded(value, decimals) - rounded(edge, decimals)) < 10 ** -(decimals + 3);
}

/**
 * The state patch a committed slider value writes: each bound rounded to the
 * axis's decimals, and a bound on its domain's edge stored as null (it narrows
 * nothing, so the link leaves it out and the filter stays off).
 */
export function boundsPatch(axis, [lo, hi], domain) {
  const spec = typeof axis === 'string' ? PARTICLE_AXES[axis] : axis;
  const d = spec.decimals;
  const low = lo === null || lo === undefined || (domain && atEdge(lo, domain[0], d)) ? null : rounded(lo, d);
  const high = hi === null || hi === undefined || (domain && atEdge(hi, domain[1], d)) ? null : rounded(hi, d);
  return { [spec.min]: low, [spec.max]: high };
}

/**
 * The bounds of the stored filter a new domain cannot hold: for each axis
 * whose stored bound lies outside its domain (or whose pair is inverted), a
 * patch setting both its keys to null, and the interval that was dropped.
 * An axis with no domain keeps its bounds (nothing to judge them against).
 */
export function droppedBounds(values, domains) {
  const patch = {};
  const dropped = [];
  for (const spec of Object.values(PARTICLE_AXES)) {
    const domain = domains?.[spec.key];
    const lo = values?.[spec.min] ?? null;
    const hi = values?.[spec.max] ?? null;
    if (!domain || (lo === null && hi === null)) continue;
    const eps = 10 ** -(spec.decimals + 3);
    const outside = (lo !== null && (lo < domain[0] - eps || lo > domain[1] + eps))
      || (hi !== null && (hi < domain[0] - eps || hi > domain[1] + eps))
      || (lo !== null && hi !== null && lo > hi);
    if (!outside) continue;
    patch[spec.min] = null;
    patch[spec.max] = null;
    dropped.push({ axis: spec.key, lo, hi, domain });
  }
  return { patch, dropped };
}

/**
 * The once-only line naming what an experiment switch dropped ('' when nothing
 * was): each dropped interval, and the domain it was judged against, both as
 * `intervalText` writes them (θ in degrees with radians beside them, so the
 * domain follows the interval rather than nesting in a parenthesis).
 */
export function droppedLine(dropped) {
  if (!dropped?.length) return '';
  const parts = dropped.map(({ axis, lo, hi, domain }) => {
    const spec = PARTICLE_AXES[axis];
    const was = intervalText({ [`particle_${axis}_min`]: lo, [`particle_${axis}_max`]: hi });
    const range = intervalText({ [`particle_${axis}_min`]: domain[0], [`particle_${axis}_max`]: domain[1] })
      .replace(`${spec.symbol} in `, '');
    return `${was}, against a range of ${range}`;
  });
  return `Dropped from the particle filter, outside this experiment's range: ${parts.join('; ')}.`;
}

/**
 * The block's lines for a candidates payload, in order: the count (at N = 0
 * the empty line in its place), the unplaceable events, and a once-only
 * notice. Empty lines are left out.
 */
export function blockLines(payload, { nShowers, notice = '' } = {}) {
  const empty = emptyLine(payload, { nShowers });
  return [empty || countLine(payload, { nShowers }), unplaceableLine(payload, { nShowers }), notice]
    .filter(Boolean);
}

/** The block's line in place of the count when the count could not be had. */
export function failedLine(error) {
  const why = typographic(String(error?.message ?? error ?? '').trim());
  return `The candidates could not be counted${why ? ` (${why})` : ''}; the pickers still draw from them.`;
}

/* ------------------------------------------------------------ the block -- */

export class ParticleFilter {
  /**
   * @param {object} options
   * @param {State} options.state the page's view state
   * @param {Document} [options.doc] where the block's own elements are found
   * @param {() => void} [options.onCommit] after a particle commit (the block has refreshed itself)
   * @param {(payload: object) => void} [options.onCandidates] every candidates payload, as it lands
   * @param {string} [options.abortKey] the request's abort key, aborted with the page's others on a switch
   * @param {(error: Error, context: string) => void} [options.onError] a count that failed after the
   *   block's own commit or Clear (the pages wire their `reportError`, so the banner says so)
   */
  constructor({ state, doc = globalThis.document, onCommit = () => {}, onCandidates = () => {},
    abortKey = 'event-candidates', onError = (error) => globalThis.console?.error?.(error) } = {}) {
    this.state = state;
    this.doc = doc;
    this.onCommit = onCommit;
    this.onCandidates = onCandidates;
    this.onError = onError;
    this.abortKey = abortKey;
    this.enabled = false;
    this.nShowers = 2;
    this.reason = null;
    this.domains = { p: null, theta: null };
    this.notice = '';
    this.last = null;
    this.el = Object.fromEntries(Object.entries(PARTICLE_IDS).map(([k, id]) => [k, doc?.getElementById?.(id) ?? null]));
    this.sliders = {};
    for (const spec of Object.values(PARTICLE_AXES)) {
      if (!doc?.getElementById?.(spec.ids.lo)) continue;
      this.sliders[spec.key] = new RangeSlider({
        loId: spec.ids.lo, hiId: spec.ids.hi, fillId: spec.ids.fill, numLoId: spec.ids.numLo, numHiId: spec.ids.numHi,
        step: spec.step, decimals: spec.decimals, unit: spec.unit,
        onInput: () => {},
        onCommit: (value) => this.commitAxis(spec.key, value),
      });
      this.disableAxis(spec.key);
    }
    this.el.clear?.addEventListener?.('click', () => { this.clear(); });
  }

  /** The last candidates payload, or null. */
  get payload() {
    return this.last;
  }

  /** Whether any particle bound is set. */
  get active() {
    return this.state.particleActive();
  }

  /**
   * Adopt an experiment: shown when `enabled` (the Event Inspector, or the
   * 3-D event pair, is offered), on one shower θ alone, hidden for the
   * event-level kind. Returns the first refresh (null when disabled), which
   * resolves once the domains are known and any bound they cannot hold is
   * dropped.
   */
  adopt(experiment, { enabled, nShowers, reason = null } = {}) {
    this.experiment = experiment ?? null;
    this.enabled = Boolean(enabled);
    this.nShowers = nShowers === 1 ? 1 : 2;
    this.reason = reason;
    this.last = null;
    this.notice = '';
    this.domains = { p: null, theta: null };
    this.adopting = true;
    if (this.el.group) this.el.group.hidden = !this.enabled;
    const pControl = this.doc?.getElementById?.(PARTICLE_AXES.p.ids.control);
    if (pControl) pControl.hidden = this.nShowers === 1;
    if (this.nShowers === 1) {
      const { min, max } = PARTICLE_AXES.p;
      if (this.state.set({ [min]: null, [max]: null }, { silent: true })) this.state.writeHash?.();
    }
    if (this.el.scope) this.el.scope.textContent = scopeNote({ nShowers: this.nShowers });
    // One shower: the θ hint names its own column; two showers get the markup's back.
    if (this.nShowers === 1) relabel(this.el.thetaHint, SINGLE_THETA_HINT);
    else restoreLabel(this.el.thetaHint);
    for (const key of Object.keys(this.sliders)) this.disableAxis(key);
    this.syncClear();
    this.writeLines(['—']);
    if (!this.enabled) return Promise.resolve(null);
    return this.refresh();
  }

  /**
   * GET /api/event/candidates under the filters and the particle filter:
   * the slider domains from its `bounds`, the block's lines, then
   * `onCandidates(payload)`. Null when the block is disabled or the request
   * was superseded; any other error leaves no stale count behind (`failed`)
   * and is rethrown.
   */
  async refresh() {
    if (!this.enabled) return null;
    let payload;
    try {
      payload = await getJson(CANDIDATES_ROUTE, this.params(), this.abortKey);
    } catch (error) {
      if (isAbort(error)) return null;
      this.failed(error);
      throw error;
    }
    this.applyBounds(payload?.bounds);
    if (this.adopting) {
      this.adopting = false;
      const { patch, dropped } = droppedBounds(this.state.values, this.domains);
      if (dropped.length) {
        this.state.set(patch);
        this.notice = droppedLine(dropped);
        this.syncSliders();
        const again = await this.refresh();
        this.onCommit();
        return again;
      }
    }
    this.last = payload;
    this.writeLines(blockLines(payload, { nShowers: this.nShowers, notice: this.notice }));
    this.notice = '';
    this.syncClear();
    this.onCandidates(payload);
    return payload;
  }

  /** The candidates request's query: the filters and the set particle bounds. */
  params() {
    return { ...this.state.filterParams(), ...this.state.particleParams() };
  }

  /** Every bound to null, then a refresh and `onCommit()`. */
  async clear() {
    const patch = {};
    for (const spec of Object.values(PARTICLE_AXES)) {
      patch[spec.min] = null;
      patch[spec.max] = null;
    }
    this.state.set(patch);
    this.syncSliders();
    this.syncClear();
    return this.committed();
  }

  /* ---------------------------------------------------------- internals -- */

  /** A slider's commit: the patch (edge bounds as null), then a refresh and `onCommit()`. */
  commitAxis(key, value) {
    const spec = PARTICLE_AXES[key];
    const before = [this.state.get(spec.min), this.state.get(spec.max)];
    const patch = boundsPatch(spec, value, this.domains[key]);
    if (before[0] === patch[spec.min] && before[1] === patch[spec.max]) return null;
    this.state.set(patch);
    this.syncClear();
    return this.committed();
  }

  /**
   * After the block's own commit or Clear: the count again, then `onCommit()`.
   * Nothing awaits the returned promise (the slider and the Clear button drop
   * it), so a failed count is reported here, through `onError`, never left as
   * an unhandled rejection; `refresh` has already dropped the stale count.
   */
  async committed() {
    let result = null;
    try {
      result = await this.refresh();
    } catch (error) {
      this.onError(error, 'particle filter');
    } finally {
      this.onCommit();
    }
    return result;
  }

  /**
   * A count that failed: the block says so in place of its lines, forgets the
   * last payload, and tells the page there is no count (`onCandidates(null)`),
   * so neither page keeps the previous filter's pool, nor its N = 0 lock.
   */
  failed(error) {
    this.last = null;
    this.notice = '';
    this.writeLines([failedLine(error)]);
    this.onCandidates(null);
  }

  /**
   * Take the payload's bounds as the slider domains, enabling a slider once its
   * domain is known. The slider is given the raw bounds and snaps them itself,
   * with the arithmetic `particleDomain` repeats: snapping an already snapped
   * 16.2 again would floor it to 16.1 through float dust.
   */
  applyBounds(bounds) {
    for (const spec of Object.values(PARTICLE_AXES)) {
      const raw = bounds?.[spec.bounds];
      const domain = particleDomain(raw, spec);
      const known = this.domains[spec.key];
      this.domains[spec.key] = domain;
      const slider = this.sliders[spec.key];
      if (!slider) continue;
      if (!domain || !(domain[1] > domain[0])) {
        this.disableAxis(spec.key);
        continue;
      }
      if (!known || known[0] !== domain[0] || known[1] !== domain[1]) {
        slider.setDisabled(false);
        slider.setBounds(raw[0], raw[1], this.valueOf(spec, domain));
      } else {
        // The same domain: follow the stored bounds (a link, back / forward, Clear).
        slider.setValue(...this.valueOf(spec, domain), { silent: true });
      }
    }
  }

  /** The slider position for the stored bounds: an unset bound at its domain's edge. */
  valueOf(spec, domain) {
    const lo = this.state.get(spec.min);
    const hi = this.state.get(spec.max);
    return [lo ?? domain[0], hi ?? domain[1]];
  }

  /** Put every enabled slider back on the stored bounds, firing nothing. */
  syncSliders() {
    for (const spec of Object.values(PARTICLE_AXES)) {
      const domain = this.domains[spec.key];
      const slider = this.sliders[spec.key];
      if (slider && domain) slider.setValue(...this.valueOf(spec, domain), { silent: true });
    }
  }

  disableAxis(key) {
    const spec = PARTICLE_AXES[key];
    const slider = this.sliders[key];
    slider?.setDisabled(true);
    for (const id of Object.values(spec.ids)) {
      if (id === spec.ids.control || id === spec.ids.fill) continue;
      const input = this.doc?.getElementById?.(id);
      if (input) input.disabled = true;
    }
  }

  /** Clear is offered while any bound is set. */
  syncClear() {
    if (this.el.clear) this.el.clear.disabled = !this.state.particleActive();
  }

  /** The count element's lines, one block element each, as text. */
  writeLines(lines) {
    const host = this.el.count;
    if (!host) return;
    const make = (text) => {
      const line = this.doc.createElement('div');
      line.className = 'particle-line';
      line.textContent = text;
      return line;
    };
    if (lines.length === 1) host.replaceChildren(this.doc.createTextNode(lines[0]));
    else host.replaceChildren(...lines.map(make));
  }
}

export function mountParticleFilter(options) {
  return new ParticleFilter(options);
}
