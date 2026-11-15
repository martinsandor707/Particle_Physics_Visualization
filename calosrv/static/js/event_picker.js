/* The event pickers' one source of words and requests: the particle filter,
 * filter-aware picking, and the links between the 2-D Event Inspector and the
 * 3-D event view. Pure and DOM-free, so it runs under Node.
 *
 * ## What the particle filter is
 *
 * Up to four inclusive bounds on one particle, with no A/B choice: the
 * incident momentum p in GeV and the incident polar angle θ in degrees
 * (`state.js` `particle_p_min` … `particle_theta_max`). A shower matches when
 * it deposited energy and every set bound holds for its own p and θ. The
 * pool - the candidates - is the selection (E₁, E₂ and D, or p on one
 * shower), AND the frame gate (a defined separation; on one shower an
 * incident direction and an entry point), AND, while any bound is set, at
 * least one matching shower (calosrv/query/particle.py). Pick for me, Most
 * tilted, Densest and previous / next all draw from it; the ensemble panels
 * never read it.
 *
 * ## Why here
 *
 * The two pages, their captions and their drawers all say the same things
 * about the pool, so every sentence is built here once, and every number in
 * one goes through the U+2212 helpers (format.js, scale.js). `intervalText`
 * writes exactly the string the server's `ParticleSpec.interval_text()`
 * writes, so a server warning and a client caption name one interval: p to
 * two decimals and θ to one, an en dash between two bounds, rounded half to
 * even on an exact tie as Python's format does.
 *
 * ## The follow policy and the shower focus
 *
 * `followDecision` says what a page does with its pinned event after a
 * filter or particle commit: keep it, replace it by a fresh uniform draw, or
 * draw it as asked and flag it. `focusShower` says which of an event's showers
 * a picker should ask for, so the shower drawn is one that matches.
 */

import { typographic } from './format.js';
import { formatInt } from './scale.js';
import { hashWith, tabHref } from './page_common.js';

/** The uniform draw's seed, and Most tilted's first (the server's DEFAULT_SEED). */
export const FIRST_SEED = 42;
/** The server's pick rules: Pick for me, Most tilted, Densest. */
export const PICK_RULES = Object.freeze(['uniform', 'tilted', 'densest']);
/** The particle filter's four view-state keys, which are also its API parameters. */
export const PARTICLE_KEYS = Object.freeze(['particle_p_min', 'particle_p_max', 'particle_theta_min',
  'particle_theta_max']);
/** The sliders' steps: GeV and degrees. */
export const PARTICLE_STEP = Object.freeze({ p: 0.05, theta: 0.1 });
/** The pool's own route: counts, slider bounds and one event's membership, never a hit. */
export const CANDIDATES_ROUTE = '/api/event/candidates';

const EN_DASH = '–';

/* --------------------------------------------------------------- requests -- */

/** Only the particle keys that carry a bound: a null or absent key is unbounded and never sent. */
function setBounds(particle) {
  const out = {};
  for (const key of PARTICLE_KEYS) {
    const value = particle?.[key];
    if (value !== null && value !== undefined && value !== '') out[key] = value;
  }
  return out;
}

/**
 * The query of GET /api/event/pick for one rule: the filters, the set
 * particle bounds, and the rule's own keys. `uniform` takes its seed and draw
 * (the k-th entry of the seeded shuffle), `tilted` its seed, `densest`
 * neither. With no bound set the request carries no particle key at all.
 */
export function pickParams({ filters = {}, particle = {}, rule = 'uniform', seed = FIRST_SEED, draw = 0 } = {}) {
  const base = { ...filters, ...setBounds(particle), rule };
  if (rule === 'uniform') return { ...base, seed, draw };
  if (rule === 'tilted') return { ...base, seed };
  return base;
}

/** The query of GET /api/event/candidates: the filters, the set bounds and, when given, the event to place. */
export function candidatesParams({ filters = {}, particle = {}, eventNumber = null } = {}) {
  const params = { ...filters, ...setBounds(particle) };
  if (eventNumber !== null && eventNumber !== undefined) params.event_number = eventNumber;
  return params;
}

/* --------------------------------------------------------------- policies -- */

/** Origins whose event the page chose itself, and so may replace when it leaves the pool. */
const REPLACEABLE = new Set(['pick', 'tilted', 'step', 'replace']);

/**
 * After a filter or particle commit, what becomes of the pinned event, from
 * its fresh response: `keep` while it is in the pool; `replace` (a uniform
 * draw) when it left and the page picked it itself (Pick for me, Most tilted,
 * previous / next, an earlier replacement) and the pool is not empty;
 * otherwise `flag`: drawn as asked and flagged. A linked or typed event is
 * the reader's own and is never replaced.
 */
export function followDecision({ origin, inPool, nEvents } = {}) {
  if (inPool === true) return 'keep';
  if (REPLACEABLE.has(origin) && Number(nEvents) > 0) return 'replace';
  return 'flag';
}

/**
 * The shower a picker asks for: the current one when it matches, else the
 * first of `matched`. With `allowBoth` (Page 2's Absolute frame) "both" is
 * kept. With nothing matched the current shower stays.
 */
export function focusShower({ current, matched, allowBoth = false } = {}) {
  if (allowBoth && current === 'both') return 'both';
  const list = Array.isArray(matched) ? matched : [];
  if (!list.length || list.includes(current)) return current;
  return list[0];
}

/* --------------------------------------------------------------- numbers -- */

/**
 * `value.toFixed(digits)` as Python's format writes it: identical except on
 * an exact binary tie (2.125 at two decimals), which Python rounds to even
 * and JavaScript away from zero. The exact expansion is read from
 * toFixed(100), which is exact for every |value| ≥ 2⁻⁴⁸.
 */
function pyFixed(value, digits) {
  const x = Number(value);
  const plain = x.toFixed(digits);
  if (!Number.isFinite(x)) return plain;
  const exact = Math.abs(x).toFixed(100);
  const [whole, frac = ''] = exact.split('.');
  if (!/^50*$/.test(frac.slice(digits))) return plain;
  const kept = digits > 0 ? frac.slice(0, digits) : whole;
  if (Number(kept.at(-1)) % 2 === 1) return plain;
  const truncated = digits > 0 ? `${whole}.${kept}` : whole;
  return x < 0 && Number(truncated) !== 0 ? `-${truncated}` : truncated;
}

/** A number with U+2212 for its sign, fixed to `digits`. */
function fixed(value, digits) {
  return typographic(pyFixed(value, digits));
}

/** An integer count, grouped (20,268). */
function count(value) {
  return formatInt(Number(value) || 0);
}

/** An event number: an identifier, never grouped. */
function eventId(value) {
  return typographic(String(Math.trunc(Number(value))));
}

/** "1 event" / "107 events". */
function plural(n, one, many = `${one}s`) {
  return `${count(n)} ${Number(n) === 1 ? one : many}`;
}

/* --------------------------------------------------------------- interval -- */

/**
 * The particle filter as `{p: [lo, hi], theta: [lo, hi]}` (degrees), from
 * the server's echo (`p_gev`, `theta_deg`) or from the view-state keys
 * (`particle_p_min` …, which `State.particleParams()` returns).
 */
export function particleBounds(particle) {
  const pair = (value) => (Array.isArray(value) ? [value[0] ?? null, value[1] ?? null] : null);
  const fromEcho = pair(particle?.p_gev) || pair(particle?.theta_deg);
  if (fromEcho) {
    return { p: pair(particle.p_gev) ?? [null, null], theta: pair(particle.theta_deg) ?? [null, null] };
  }
  const read = (key) => {
    const value = particle?.[key];
    return value === null || value === undefined || value === '' ? null : Number(value);
  };
  return {
    p: [read('particle_p_min'), read('particle_p_max')],
    theta: [read('particle_theta_min'), read('particle_theta_max')],
  };
}

/** Whether any bound is set, from the echo (its `active`) or from the view-state keys. */
export function particleIsActive(particle) {
  if (typeof particle?.active === 'boolean') return particle.active;
  const { p, theta } = particleBounds(particle);
  return [...p, ...theta].some((v) => v !== null);
}

function interval(symbol, [lo, hi], digits, unit) {
  if (lo !== null && hi !== null) return `${symbol} in ${fixed(lo, digits)}${EN_DASH}${fixed(hi, digits)}${unit}`;
  if (lo !== null) return `${symbol} ≥ ${fixed(lo, digits)}${unit}`;
  if (hi !== null) return `${symbol} ≤ ${fixed(hi, digits)}${unit}`;
  return '';
}

/**
 * "p in 5.00–6.00 GeV and θ in 10.0–15.0°" ('' when no bound is set): the
 * server's `ParticleSpec.interval_text()`, character for character.
 */
export function intervalText(particle) {
  const { p, theta } = particleBounds(particle);
  return [interval('p', p, 2, ' GeV'), interval('θ', theta, 1, '°')].filter(Boolean).join(' and ');
}

/* --------------------------------------------------------------- sentences -- */

/** Whether the experiment's events hold two showers: an explicit count, else the payload's own. */
function twoShowers(nShowers, candidates) {
  if (nShowers === 1 || nShowers === 2) return nShowers === 2;
  const keys = candidates?.showers;
  return Array.isArray(keys) ? keys.length !== 1 : true;
}

/** The selection's own filter words. */
function selectionWords(two) {
  return two ? 'E₁, E₂ and D' : 'p';
}

/**
 * Whether a drawn event's shower blocks say it has two showers: a
 * single-shower block is labelled "Shower", a two-shower one "A" or "B". An
 * explicit `nShowers` always wins; with nothing to go on, two.
 */
function twoFromShowers(nShowers, showers) {
  if (nShowers === 1 || nShowers === 2) return nShowers === 2;
  const list = (Array.isArray(showers) ? showers : [showers]).filter(Boolean);
  return !(list.length === 1 && !/^[AB]$/.test(String(list[0].label ?? '')));
}

/** A shower's letter, from its key. */
function letter(key) {
  return String(key ?? '').toUpperCase();
}

/**
 * The block's count line, from GET /api/event/candidates (the whole payload
 * or its `candidates` block).
 */
export function countLine(payload, { nShowers } = {}) {
  const c = payload?.candidates ?? payload ?? {};
  const two = twoShowers(nShowers, c);
  const n = Number(c.n_events ?? 0);
  if (!particleIsActive(c.particle)) {
    if (n === 0) return 'Particle filter off: the selection holds no event the pickers can draw.';
    if (n === 1) return 'Particle filter off: the pickers draw from the 1 selected event.';
    return `Particle filter off: the pickers draw from all ${count(n)} selected events.`;
  }
  const of = `of the ${count(c.n_selection ?? 0)} selected by ${selectionWords(two)}.`;
  if (!two) {
    return `N = ${plural(n, 'event')} whose shower has ${intervalText(c.particle)}, ${of}`;
  }
  const verb = n === 1 ? 'holds' : 'hold';
  const keys = Array.isArray(c.showers) && c.showers.length ? c.showers : Object.keys(c.by_shower ?? {});
  const per = keys.map((key) => `${count(c.by_shower?.[key] ?? 0)} ${letter(key)}`).join(', ');
  const both = Number(c.n_both ?? 0);
  const bothText = both > 0 ? `; ${plural(both, 'event')} ${both === 1 ? 'matches' : 'match'} with both` : '';
  return `N = ${plural(n, 'event')} ${verb} a matching particle `
    + `(${plural(c.n_showers ?? 0, 'matching shower')}: ${per}${bothText}), ${of}`;
}

/** The empty pool's line ('' unless N = 0): what holds nothing, and what to widen. */
export function emptyLine(payload, { nShowers } = {}) {
  const c = payload?.candidates ?? payload ?? {};
  if (Number(c.n_events ?? 0) !== 0) return '';
  const two = twoShowers(nShowers, c);
  if (!particleIsActive(c.particle)) {
    return `N = 0: the selection holds no event to draw. Widen ${two ? 'E₁, E₂ or D' : 'p'}.`;
  }
  const text = intervalText(c.particle);
  return two
    ? `N = 0: no selected event holds a shower with ${text} that deposited energy. `
      + 'Widen the particle filter, or E₁, E₂ and D.'
    : `N = 0: no selected event holds its shower at ${text}. Widen the particle filter, or p.`;
}

/** The selected events the frame gate refuses ('' when none): never offered, still drawable by number. */
export function unplaceableLine(payload, { nShowers } = {}) {
  const c = payload?.candidates ?? payload ?? {};
  const n = Number(c.n_unplaceable ?? 0);
  if (!(n > 0)) return '';
  const two = twoShowers(nShowers, c);
  const one = n === 1;
  const what = two ? 'no defined separation (shower A deposited no energy)' : 'no incident direction or entry point';
  return `${plural(n, 'selected event')} ${one ? 'has' : 'have'} ${what} and ${one ? 'is' : 'are'} never offered; `
    + `type an event number to draw ${one ? 'it' : 'one'}.`;
}

/**
 * Where a drawn event stands among the candidates. `source` is the event
 * block of GET /api/event (its `candidates` and `in_selection` are read),
 * its `candidates` block, or the `event` block of GET /api/event/candidates.
 * In the pool: its place. In the selection but not the pool: why not, and
 * that previous / next walk the candidates. Outside the selection: '' (the
 * selection line says so already).
 */
export function placeLine(source, { inSelection, nShowers } = {}) {
  const c = source?.candidates ?? source;
  if (!c) return '';
  const selected = inSelection ?? source?.in_selection ?? c.in_selection ?? true;
  if (selected === false) return '';
  if (c.in_pool) {
    return `Candidate ${count(Number(c.index ?? 0) + 1)} of ${count(c.n_events ?? 0)}, in event-number order.`;
  }
  const tail = 'drawn as asked, and previous / next walk the candidates.';
  const matched = Array.isArray(c.matched) ? c.matched : [];
  // An empty `matched` is a filter no shower meets, unless the echo says no
  // bound is set (then it is the frame gate that refused the event).
  const active = c.particle ? particleIsActive(c.particle) : true;
  if (!matched.length && active) {
    return `Not a candidate: no shower matches the particle filter; ${tail}`;
  }
  const two = twoFromShowers(nShowers, source?.showers ?? source?.shower);
  return two
    ? `Not a candidate: it has no defined separation, which the pickers need; ${tail}`
    : `Not a candidate: its shower has no incident direction or entry point, which the pickers need; ${tail}`;
}

/** A shower's tested values: "p = 5.41 GeV, θ = 12.3° (0.215 rad)", the quantities the filter bounds. */
function valuesText(shower, particle) {
  if (!shower) return '';
  const { p, theta } = particleBounds(particle);
  const parts = [];
  const pSet = p.some((v) => v !== null);
  const tSet = theta.some((v) => v !== null);
  if (pSet && Number.isFinite(shower.momentum_gev)) parts.push(`p = ${fixed(shower.momentum_gev, 2)} GeV`);
  if (tSet && Number.isFinite(shower.theta_deg)) {
    const rad = Number.isFinite(shower.theta) ? shower.theta : (shower.theta_deg * Math.PI) / 180;
    parts.push(`θ = ${fixed(shower.theta_deg, 1)}° (${fixed(rad, 3)} rad)`);
  }
  return parts.join(', ');
}

/**
 * How the drawn shower stands against an active particle filter ('' when it
 * is off). `drawn` is 'a', 'b' or 'both'; `showers` the drawn event's shower
 * blocks (`event.shower` of the raster, `event.showers` of the voxels), whose
 * p and θ are quoted.
 */
export function matchLine({ candidates, drawn = 'a', showers = [], nShowers } = {}) {
  const c = candidates?.candidates ?? candidates;
  if (!c || !particleIsActive(c.particle)) return '';
  const matched = Array.isArray(c.matched) ? c.matched : [];
  const list = (Array.isArray(showers) ? showers : [showers]).filter(Boolean);
  const showerOf = (key) => list.find((s) => s.key === key) ?? null;
  const said = (key) => {
    const values = valuesText(showerOf(key), c.particle);
    return values ? `: ${values}.` : '.';
  };
  const two = twoFromShowers(nShowers, list);
  if (!two) {
    return matched.length
      ? `The shower matches the particle filter${said(matched[0])}`
      : `The shower does not match the particle filter${said(list[0]?.key ?? 'a')}`;
  }
  if (matched.length >= 2) {
    return `Showers ${matched.slice(0, -1).map(letter).join(', ')} and ${letter(matched.at(-1))} both match the particle filter.`;
  }
  if (!matched.length) return 'Neither shower matches the particle filter.';
  const [hit] = matched;
  if (drawn === 'both' || drawn === hit) return `Shower ${letter(hit)} matches the particle filter${said(hit)}`;
  return `Shower ${letter(drawn)} is drawn as asked and does not match the particle filter; shower ${letter(hit)} does.`;
}

/** The caption's line when a replacement took the pinned event's place. */
export function replacedLine(oldEvent, newEvent) {
  return `Event ${eventId(oldEvent)} left the candidates; event ${eventId(newEvent)} replaces it.`;
}

/** The ensemble views' disclosure while the particle filter is active ('' when it is off). */
export function ensembleLine(particle, { nShowers } = {}) {
  const echo = particle?.particle ?? particle;
  if (!particleIsActive(echo)) return '';
  const words = nShowers === 1 ? 'p' : 'E₁, E₂ and D';
  return `The particle filter (${intervalText(echo)}) narrows the event pickers only; `
    + `this view draws the whole selection of ${words}.`;
}

/** The sidebar block's hint. */
export function scopeNote({ nShowers } = {}) {
  const words = nShowers === 1 ? 'p' : 'E₁, E₂ and D';
  return 'Narrows only which events the pickers offer (Pick for me, Most tilted, previous / next, '
    + `and the 3-D view's Densest). The ensemble panels follow ${words}.`;
}

/* --------------------------------------------------------------- titles -- */

export const PICK_TITLE = 'A candidate event drawn uniformly at random under the filters and the particle '
  + 'filter: a seeded shuffle, so no event repeats until all have been drawn. Each click takes the next draw.';
export const TILTED_TITLE = "The reference notebook's showcase rule on the candidates: events with more hits "
  + 'than the mean, the 20 with the largest incident angle of a matching shower, one drawn at random. '
  + 'Each click takes the next seed.';
export const OPEN_3D_TITLE = "Open this event and shower in the Models page's 3-D view, with every filter; "
  + 'the Physics page keeps its own event.';
export const OPEN_3D_DFRAME_NOTE = ' The D-frame draws no single event, so the 3-D view opens in the Absolute frame.';
export const OPEN_2D_TITLE = "Open this event in the Physics page's Event Inspector: one shower in the Absolute, "
  + 'per-shower translated and Local frames, with every filter.';

/**
 * A picker button's title: at N = 0 the emptyLine (every picker), else the
 * rule's own (Pick for me, Most tilted); null for a rule whose title the page
 * keeps (Densest).
 */
export function pickerTitle(rule, payload = null, { nShowers } = {}) {
  const empty = payload ? emptyLine(payload, { nShowers }) : '';
  if (empty) return empty;
  if (rule === 'uniform') return PICK_TITLE;
  if (rule === 'tilted') return TILTED_TITLE;
  return null;
}

/** "Open in 3-D →"'s title, with the D-frame's note in that frame. */
export function open3dTitle({ frame } = {}) {
  return frame === 'canonical' ? `${OPEN_3D_TITLE}${OPEN_3D_DFRAME_NOTE}` : OPEN_3D_TITLE;
}

/* --------------------------------------------------------------- links -- */

/**
 * Page 1 → Page 2: the Models page's 3-D view of this event and shower.
 * Every filter and particle key, and Page 1's own `event` / `shower`, stay in
 * the hash; `msub` is dropped so the link lands on Views; the D-frame, which
 * draws no single event, becomes the Absolute frame. Built-in values (shower
 * A, the Absolute frame) are left out, as the state's own links leave them.
 */
export function eventIn3dHref({ hash = '', event, shower = 'a', frame } = {}) {
  const current = frame ?? new URLSearchParams(String(hash ?? '').replace(/^#/, '')).get('frame') ?? 'lab';
  const target = current === 'canonical' || current === 'lab' ? null : current;
  return tabHref('/models', hashWith(hash, {
    voxel_event: event,
    voxel_shower: shower === 'a' ? null : shower,
    voxel_scope: 'event',
    frame: target,
  }, { drop: ['msub'] }));
}

/**
 * Page 2 → Page 1: the Physics page's Event Inspector on this event, drawing
 * one shower: the given one, or for 'both' its match (the first of
 * `matched`), else A. Shower A, the built-in, is left out.
 */
export function eventIn2dHref({ hash = '', event, shower = 'a', matched = [] } = {}) {
  const single = shower === 'both' ? ((Array.isArray(matched) && matched[0]) || 'a') : (shower || 'a');
  return tabHref('/', hashWith(hash, { event, shower: single === 'a' ? null : single }));
}
