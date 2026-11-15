"""The particle filter's client half, under Node: state, sentences, links and the sidebar block.

Brief ``data/dev/design/particle-filter/brief.md`` §4–§6:

* ``state.js``: the four particle keys are view state (null by default,
  checked and rounded like every numeric key, never Admin defaults);
  ``filterParams()`` is unchanged, ``particleParams()`` holds only the set
  bounds and ``eventParams()`` adds them;
* ``event_picker.js``: the pick and candidates queries, the follow policy, the
  shower focus, every sentence of §5.1 on the recorded payloads of the
  backend (``tests/fixtures/payloads/candidates_*.json``,
  ``event_raster_base_particle.json``, ``event_voxels_base_lab_particle.json``),
  ``intervalText`` against the server's own ``ParticleSpec.interval_text()``,
  and the two links between the 2-D Event Inspector and the 3-D event view;
* ``controls/particle_filter.js``: its pure parts (the snapped domains, a
  bound at the domain edge stored as null, the bounds a new domain cannot
  hold, the block's lines), then the block itself on the fake document of
  ``test_js_physics_shell.py`` with a recorded fetch.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, HYPHEN_NUMBER, JS, NODE, _path, _payload, _run

from calosrv.query.particle import ParticleSpec

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

EN = "–"

#: Particle filters whose interval the client and the server must write alike,
#: as (p_min, p_max, theta_min, theta_max). Exact binary ties (2.125, 0.25,
#: 0.375) are where JavaScript's toFixed and Python's format part ways.
INTERVALS = [
    (5.0, 6.0, 10.0, 15.0),
    (5.0, None, None, None),
    (None, 6.0, None, None),
    (None, None, 10.0, None),
    (None, None, None, 15.0),
    (2.0, 3.0, None, None),
    (None, None, 20.0, 25.0),
    (2.125, 2.375, 0.25, 0.35),
    (0.0, 19.95, 0.0, 180.0),
    (0.005, 0.015, 12.25, 12.35),
    (None, None, None, None),
]


# ----------------------------------------------------------------- the script --

_SCRIPT = _FAKE_DOM + r"""
const [stateUrl, pickerUrl, controlUrl, paths, intervals] = JSON.parse(process.argv[1]);
const P = loadAll(paths);
const st = await import(stateUrl);
const ep = await import(pickerUrl);
const pf = await import(controlUrl);
const out = {};
const fresh = (hash) => { window.location.hash = hash; replaced = []; return new st.State(); };

// ---- state.js
let s = fresh('');
out.state = {
  defaults: Object.fromEntries(ep.PARTICLE_KEYS.map((k) => [k, st.DEFAULTS[k]])),
  keys: st.PARTICLE_PARAM_KEYS,
  filterKeys: Object.keys(s.filterParams()),
  none: s.particleParams(),
  noneActive: s.particleActive(),
  eventNone: s.eventParams(),
};
s = fresh('#event=12&shower=b&particle_p_min=5.123&particle_theta_max=15.04');
out.state.read = { p_min: s.get('particle_p_min'), theta_max: s.get('particle_theta_max'), coldBoot: s.coldBoot };
out.state.params = s.particleParams();
out.state.active = s.particleActive();
out.state.event = s.eventParams();
out.state.eventKeys = Object.keys(s.eventParams());
out.state.filterWith = Object.keys(s.filterParams());
out.state.hash = s.hashString();
s.set({ particle_p_min: null, particle_theta_max: null });
out.state.cleared = { hash: window.location.hash, params: s.particleParams() };
out.state.invalid = {};
for (const hash of ['#particle_p_min=-1', '#particle_theta_min=200', '#particle_theta_max=-0.5', '#particle_p_max=abc',
                    '#particle_p_max=Infinity', '#particle_p_min=6&particle_p_max=5',
                    '#particle_theta_min=20&particle_theta_max=10&particle_p_min=1']) {
  const t = fresh(hash);
  out.state.invalid[hash] = { params: t.particleParams(), coldBoot: t.coldBoot };
}
out.state.edges = fresh('#particle_p_min=0&particle_theta_min=0&particle_theta_max=180').particleParams();
s = fresh('');
out.state.defaultable = s.applyDefaults({ table_name: 'x', particle_p_min: 5, particle_theta_max: 10 });
out.state.afterDefaults = s.particleParams();

// ---- intervalText against the server
out.intervals = intervals.map(([a, b, c, d]) => ep.intervalText({
  particle_p_min: a, particle_p_max: b, particle_theta_min: c, particle_theta_max: d }));
out.intervalsEcho = intervals.map(([a, b, c, d]) => ep.intervalText({
  active: [a, b, c, d].some((v) => v !== null), p_gev: [a, b], theta_deg: [c, d] }));
out.serverWarning = P.voxelsParticle.meta.warnings[0];
out.voxelsInterval = ep.intervalText(P.voxelsParticle.event.candidates.particle);

// ---- requests
const filters = { table_name: 'demo', e1_min: 1, e1_max: 2, e2_min: null, e2_max: null, d_min: null, d_max: null,
  include_undefined_d: false };
const bounded = { particle_p_min: 5, particle_p_max: null, particle_theta_min: 10, particle_theta_max: 15 };
out.pick = {};
for (const rule of ep.PICK_RULES) {
  out.pick[rule] = {
    plain: ep.pickParams({ filters, rule }),
    bounded: ep.pickParams({ filters, particle: bounded, rule, seed: 44, draw: 3 }),
    empty: ep.pickParams({ filters, particle: {}, rule }),
  };
}
out.pick.default = ep.pickParams({ filters });
s = fresh('#particle_theta_min=10');
out.pick.fromState = ep.pickParams({ filters: s.filterParams(), particle: s.particleParams(), rule: 'tilted', seed: 43 });
out.candidates = {
  plain: ep.candidatesParams({ filters }),
  bounded: ep.candidatesParams({ filters, particle: bounded }),
  event: ep.candidatesParams({ filters, particle: bounded, eventNumber: 0 }),
  nullEvent: ep.candidatesParams({ filters, eventNumber: null }),
};
out.constants = { seed: ep.FIRST_SEED, rules: ep.PICK_RULES, keys: ep.PARTICLE_KEYS, step: ep.PARTICLE_STEP,
  route: ep.CANDIDATES_ROUTE, frozen: [Object.isFrozen(ep.PICK_RULES), Object.isFrozen(ep.PARTICLE_KEYS),
    Object.isFrozen(ep.PARTICLE_STEP)] };

// ---- follow and focus
out.follow = {};
for (const origin of ['link', 'typed', 'pick', 'tilted', 'step', 'replace', 'densest']) {
  for (const inPool of [true, false]) {
    for (const nEvents of [0, 5]) {
      out.follow[`${origin}|${inPool}|${nEvents}`] = ep.followDecision({ origin, inPool, nEvents });
    }
  }
}
out.focus = {
  keepA: ep.focusShower({ current: 'a', matched: ['a', 'b'] }),
  keepB: ep.focusShower({ current: 'b', matched: ['b'] }),
  toB: ep.focusShower({ current: 'a', matched: ['b'] }),
  toA: ep.focusShower({ current: 'b', matched: ['a'] }),
  none: ep.focusShower({ current: 'b', matched: [] }),
  nullMatched: ep.focusShower({ current: 'a', matched: null }),
  bothAllowed: ep.focusShower({ current: 'both', matched: ['b'], allowBoth: true }),
  bothRefused: ep.focusShower({ current: 'both', matched: ['b'] }),
  single: ep.focusShower({ current: 'a', matched: ['a'] }),
};

// ---- sentences
const echo = (p = [null, null], t = [null, null]) => ({
  active: [...p, ...t].some((v) => v !== null), p_gev: p, theta_deg: t,
  theta_rad: t.map((v) => (v === null ? null : (v * Math.PI) / 180)) });
const two = (over) => ({ candidates: { particle: echo([5, 6], [10, 15]), n_selection: 20268, n_unplaceable: 0,
  n_events: 107, n_showers: 108, by_shower: { a: 43, b: 65 }, n_both: 1, showers: ['a', 'b'], ...over } });
const one = (over) => ({ candidates: { particle: echo([null, null], [10, 15]), n_selection: 5000, n_unplaceable: 0,
  n_events: 312, n_showers: 312, by_shower: { a: 312 }, n_both: null, showers: ['a'], ...over } });
out.count = {
  brief: ep.countLine(two()),
  noBoth: ep.countLine(two({ n_both: 0 })),
  twoBoth: ep.countLine(two({ n_both: 2 })),
  singular: ep.countLine(two({ n_selection: 3, n_events: 1, n_showers: 1, by_shower: { a: 1, b: 0 }, n_both: 0 })),
  single: ep.countLine(one()),
  singleOne: ep.countLine(one({ n_events: 1, n_showers: 1 })),
  off: ep.countLine(two({ particle: echo(), n_events: 20268 })),
  offOne: ep.countLine(two({ particle: echo(), n_events: 1 })),
  offSingle: ep.countLine(one({ particle: echo(), n_events: 5000 })),
  fixtureOff: ep.countLine(P.off),
  fixtureParticle: ep.countLine(P.particle),
  fixtureEmpty: ep.countLine(P.empty),
  fixtureSingle: ep.countLine(P.single),
  explicitTwo: ep.countLine(P.particle, { nShowers: 2 }),
};
out.empty = {
  fixture: ep.emptyLine(P.empty),
  nonEmpty: ep.emptyLine(P.particle),
  off: ep.emptyLine(two({ particle: echo(), n_events: 0 })),
  offSingle: ep.emptyLine(one({ particle: echo(), n_events: 0 })),
  single: ep.emptyLine(one({ n_events: 0 })),
  singleNamed: ep.emptyLine(two({ n_events: 0, particle: echo([null, null], [20, 25]) }), { nShowers: 1 }),
};
out.unplaceable = {
  two: ep.unplaceableLine(two({ n_unplaceable: 57 })),
  twoOne: ep.unplaceableLine(two({ n_unplaceable: 1 })),
  single: ep.unplaceableLine(one({ n_unplaceable: 57 })),
  none: ep.unplaceableLine(P.off),
};
out.place = {
  brief: ep.placeLine({ in_pool: true, index: 36, n_events: 107, matched: ['a'] }),
  raster: ep.placeLine(P.rasterParticle.event),
  rasterOff: ep.placeLine(P.raster.event),
  voxels: ep.placeLine(P.voxelsParticle.event),
  membership: ep.placeLine(P.single.event),
  gateTwo: ep.placeLine({ particle: echo(), in_pool: false, index: null, n_events: 3, matched: ['b'] }),
  gateMatched: ep.placeLine({ particle: echo([5, 6]), in_pool: false, index: null, n_events: 3, matched: ['b'] }),
  gateSingle: ep.placeLine({ particle: echo(), in_pool: false, index: null, n_events: 3, matched: ['a'] },
    { nShowers: 1 }),
  gateSingleFixture: ep.placeLine({ ...P.voxelsSingle.event, candidates: { ...P.voxelsSingle.event.candidates,
    in_pool: false, index: null } }),
  outside: ep.placeLine({ ...P.voxelsParticle.event, in_selection: false }),
  outsideOpt: ep.placeLine(P.voxelsParticle.event.candidates, { inSelection: false }),
  none: ep.placeLine(null),
};
const shower = { key: 'a', label: 'A', momentum_gev: 5.4123, theta_deg: 12.31, theta: 0.21485 };
const showerB = { key: 'b', label: 'B', momentum_gev: 8.0, theta_deg: 30.0, theta: 0.5236 };
const both = echo([5, 6], [10, 15]);
out.match = {
  brief: ep.matchLine({ candidates: { particle: both, matched: ['a'] }, drawn: 'a', showers: [shower, showerB] }),
  rasterFixture: ep.matchLine({ candidates: P.rasterParticle.event.candidates, drawn: 'a',
    showers: P.rasterParticle.event.shower }),
  both: ep.matchLine({ candidates: { particle: both, matched: ['a', 'b'] }, drawn: 'b', showers: [shower, showerB] }),
  other: ep.matchLine({ candidates: { particle: both, matched: ['a'] }, drawn: 'b', showers: [shower, showerB] }),
  drawnBoth: ep.matchLine({ candidates: { particle: both, matched: ['a'] }, drawn: 'both', showers: [shower, showerB] }),
  neither: ep.matchLine({ candidates: P.voxelsParticle.event.candidates, drawn: 'both',
    showers: P.voxelsParticle.event.showers }),
  single: ep.matchLine({ candidates: { particle: echo([null, null], [10, 15]), matched: ['a'] }, drawn: 'a',
    showers: [{ ...shower, label: 'Shower' }] }),
  singleNamed: ep.matchLine({ candidates: { particle: echo([null, null], [10, 15]), matched: ['a'] }, drawn: 'a',
    showers: [shower], nShowers: 1 }),
  singleMiss: ep.matchLine({ candidates: { particle: echo([null, null], [20, 25]), matched: [] }, drawn: 'a',
    showers: P.voxelsSingle.event.showers }),
  off: ep.matchLine({ candidates: P.raster.event.candidates, drawn: 'a', showers: P.raster.event.shower }),
  noValues: ep.matchLine({ candidates: { particle: both, matched: ['a'] }, drawn: 'a', showers: [] }),
};
out.misc = {
  replaced: ep.replacedLine(123, 456),
  replacedBig: ep.replacedLine(20123, 4),
  ensemble: ep.ensembleLine(both),
  ensembleSingle: ep.ensembleLine(echo([null, null], [10, 15]), { nShowers: 1 }),
  ensembleState: ep.ensembleLine({ particle_theta_min: 10 }),
  ensembleOff: ep.ensembleLine(echo()),
  ensembleEmpty: ep.ensembleLine({}),
  scope: ep.scopeNote({ nShowers: 2 }),
  scopeSingle: ep.scopeNote({ nShowers: 1 }),
  pickTitle: ep.pickerTitle('uniform', P.off),
  tiltedTitle: ep.pickerTitle('tilted', P.off),
  densestTitle: ep.pickerTitle('densest', P.off),
  emptyTitles: ep.PICK_RULES.map((rule) => ep.pickerTitle(rule, P.empty)),
  noPayload: ep.pickerTitle('uniform'),
  open3d: ep.open3dTitle({ frame: 'lab' }),
  open3dCanonical: ep.open3dTitle({ frame: 'canonical' }),
  open2d: ep.OPEN_2D_TITLE,
};

// ---- links
const hash = 'table_name=demo&e1_min=2&particle_p_min=5&particle_theta_max=15&event=12&shower=b&frame=canonical&msub=perf';
out.links = {
  canonical: ep.eventIn3dHref({ hash, event: 12, shower: 'b', frame: 'canonical' }),
  canonicalFromHash: ep.eventIn3dHref({ hash: `#${hash}`, event: 12, shower: 'b' }),
  lab: ep.eventIn3dHref({ hash: 'frame=lab&voxel_shower=both', event: 7, shower: 'a', frame: 'lab' }),
  local: ep.eventIn3dHref({ hash: 'frame=local&e2_max=9', event: 7, shower: 'a', frame: 'local' }),
  trans: ep.eventIn3dHref({ hash: '', event: 0, shower: 'b', frame: 'trans' }),
  empty: ep.eventIn3dHref({ hash: '', event: 3, shower: 'a', frame: 'lab' }),
  twoD: ep.eventIn2dHref({ hash: 'voxel_event=7&voxel_shower=b&voxel_scope=event&particle_theta_min=10&msub=views',
    event: 7, shower: 'b' }),
  twoDBoth: ep.eventIn2dHref({ hash: 'voxel_event=7&voxel_shower=both', event: 7, shower: 'both', matched: ['b'] }),
  twoDBothNone: ep.eventIn2dHref({ hash: 'shower=b', event: 7, shower: 'both', matched: [] }),
  twoDA: ep.eventIn2dHref({ hash: 'event=3&shower=b', event: 9, shower: 'a' }),
};

// ---- the block's pure parts
out.pure = {
  domainP: pf.particleDomain(P.off.bounds.p_gev, 'p'),
  domainTheta: pf.particleDomain(P.off.bounds.theta_deg, 'theta'),
  domainSingle: pf.particleDomain(P.single.bounds.theta_deg, pf.PARTICLE_AXES.theta),
  domainNull: pf.particleDomain([null, null], 'p'),
  domainMissing: pf.particleDomain(undefined, 'theta'),
  edges: pf.boundsPatch('p', [2.7, 17.9], [2.7, 17.9]),
  inside: pf.boundsPatch('p', [5, 6], [2.7, 17.9]),
  loEdge: pf.boundsPatch('theta', [16.2, 20.000000001], [16.2, 26.5]),
  hiEdge: pf.boundsPatch('theta', [18.3, 26.5], [16.2, 26.5]),
  dust: pf.boundsPatch('p', [0.4 + 33 * 0.05, 17.9], [2.7, 17.9]),
  noDomain: pf.boundsPatch('p', [5, 6], null),
  dropFits: pf.droppedBounds({ particle_p_min: 5, particle_p_max: null, particle_theta_min: 16.2,
    particle_theta_max: 26.5 }, { p: [2.7, 17.9], theta: [16.2, 26.5] }),
  dropOutside: pf.droppedBounds({ particle_p_min: 18.5, particle_p_max: null, particle_theta_min: 20,
    particle_theta_max: 25 }, { p: [2.7, 17.9], theta: [16.2, 26.5] }),
  dropInverted: pf.droppedBounds({ particle_p_min: 6, particle_p_max: 5 }, { p: [2.7, 17.9], theta: null }),
  dropNoDomain: pf.droppedBounds({ particle_theta_min: 40 }, { p: [2.7, 17.9], theta: null }),
  lines: {
    off: pf.blockLines(P.off),
    particle: pf.blockLines(P.particle),
    empty: pf.blockLines(P.empty),
    single: pf.blockLines(P.single, { nShowers: 1 }),
    unplaceable: pf.blockLines(two({ n_unplaceable: 57 }), { notice: 'Note.' }),
  },
};
out.pure.droppedLine = pf.droppedLine(out.pure.dropOutside.dropped);
out.pure.droppedNone = pf.droppedLine([]);

// ---- the block on the fake document
const ids = ['group-particle', 'ctl-particle-p', 'ctl-particle-theta', 'particle-count', 'particle-scope',
  'particle-clear', 'pp-lo', 'pp-hi', 'pp-fill', 'pp-num-lo', 'pp-num-hi', 'pt-lo', 'pt-hi', 'pt-fill',
  'pt-num-lo', 'pt-num-hi'];
for (const id of ids) byId(id);
for (const id of ['pp-lo', 'pp-hi', 'pt-lo', 'pt-hi']) {
  const el = byId(id);
  const control = byId(id.startsWith('pp') ? 'ctl-particle-p' : 'ctl-particle-theta');
  control.className = 'control';
  control.append(el);
}
byId('group-particle').hidden = true;
byId('particle-clear').disabled = true;
byId('particle-count').textContent = '—';
const THETA_HINT = 'Polar angle of the same shower (incoming_theta_A or _B), in degrees.';
byId('particle-theta-hint').append(document.createTextNode(THETA_HINT));
const requests = [];
let respond = () => P.off;
globalThis.fetch = async (url) => {
  const u = new URL(String(url));
  const query = Object.fromEntries(u.searchParams.entries());
  requests.push({ path: u.pathname, query });
  return { ok: true, status: 200, json: async () => respond(query) };
};
const byQuery = (query) => {
  if (query.table_name === 'single_hits') return P.single;
  if (query.particle_p_min === '5' || query.particle_p_min === '5.5') return P.empty;
  if ('particle_p_min' in query || 'particle_p_max' in query) return P.particle;
  return P.off;
};
respond = byQuery;
const block = {};
window.location.hash = '#table_name=experiment_baseline&particle_theta_max=40&particle_p_max=3';
const state = new st.State();
let commits = 0;
const seen = [];
const control = pf.mountParticleFilter({ state, onCommit: () => { commits += 1; },
  onCandidates: (payload) => seen.push(payload.candidates.n_events) });
block.before = {
  disabled: ['pp-lo', 'pp-num-lo', 'pt-hi', 'pt-num-hi'].map((id) => byId(id).disabled),
  payload: control.payload, active: control.active,
};
const adopted = await control.adopt({ table_name: 'experiment_baseline' }, { enabled: true, nShowers: 2 });
block.adopt = {
  hidden: byId('group-particle').hidden,
  pHidden: byId('ctl-particle-p').hidden,
  requests: requests.map((r) => r.query),
  params: state.particleParams(),
  hash: window.location.hash,
  count: byId('particle-count').textContent,
  lines: byId('particle-count').children.map((c) => c.textContent),
  domains: control.domains,
  sliderP: [control.sliders.p.min, control.sliders.p.max, control.sliders.p.value()],
  sliderTheta: [control.sliders.theta.min, control.sliders.theta.max, control.sliders.theta.value()],
  enabled: ['pp-lo', 'pp-num-lo', 'pt-hi', 'pt-num-hi'].map((id) => byId(id).disabled),
  scope: byId('particle-scope').textContent,
  clearDisabled: byId('particle-clear').disabled,
  commits,
  adoptedN: adopted?.candidates?.n_events ?? null,
  seen: [...seen],
};
// A refresh repeats nothing but the request.
requests.length = 0;
await control.refresh();
block.refresh = { requests: requests.map((r) => r.query), count: byId('particle-count').textContent,
  commits };

// A drag previews nothing; a release commits, the upper bound at the edge stored as null.
requests.length = 0;
const lo = byId('pp-lo');
byId('pp-hi').value = String(control.sliders.p.steps);
lo.value = String(Math.round((5.5 - control.sliders.p.min) / 0.05));
lo.dispatch('input');
block.drag = { requests: requests.length, params: state.particleParams() };
lo.dispatch('change');
await settle();
block.commit = { params: state.particleParams(), requests: requests.map((r) => r.query), commits,
  count: byId('particle-count').textContent, clearDisabled: byId('particle-clear').disabled,
  hash: window.location.hash, payload: control.payload?.candidates?.n_events };
// The same value again (a blur after the change) sends nothing.
requests.length = 0;
lo.dispatch('blur');
await settle();
block.blur = { requests: requests.length, commits };
// Clear.
requests.length = 0;
byId('particle-clear').click();
await settle();
block.clear = { params: state.particleParams(), requests: requests.map((r) => r.query), commits,
  sliderP: control.sliders.p.value(), active: control.active, clearDisabled: byId('particle-clear').disabled,
  count: byId('particle-count').textContent };

// A single-shower experiment: θ alone, p's keys cleared silently.
state.set({ table_name: 'single_hits', particle_p_min: 3 }, { silent: true });
requests.length = 0;
await control.adopt({ table_name: 'single_hits' }, { enabled: true, nShowers: 1 });
block.single = { pHidden: byId('ctl-particle-p').hidden, params: state.particleParams(),
  scope: byId('particle-scope').textContent, requests: requests.map((r) => r.query),
  count: byId('particle-count').textContent, thetaHint: byId('particle-theta-hint').textContent,
  singleHint: pf.SINGLE_THETA_HINT };

// Disabled: hidden, no request, refresh null.
requests.length = 0;
const disabled = await control.adopt({ table_name: 'events' }, { enabled: false, nShowers: 1, reason: 'No events.' });
block.disabled = { hidden: byId('group-particle').hidden, requests: requests.length, adopted: disabled,
  refresh: await control.refresh(), reason: control.reason };

// A failure that is not an abort is rethrown; an abort is null.
await control.adopt({ table_name: 'experiment_baseline' }, { enabled: true, nShowers: 2 });
block.restoredHint = { text: byId('particle-theta-hint').textContent, markup: THETA_HINT };
globalThis.fetch = async () => ({ ok: false, status: 500, statusText: 'Boom', json: async () => ({ detail: 'Boom.' }) });
try { await control.refresh(); block.error = 'none'; } catch (error) { block.error = error.message; }
globalThis.fetch = async () => { const e = new Error('gone'); e.name = 'AbortError'; throw e; };
block.abort = await control.refresh();
out.block = block;

// Every sentence written above.
out.sentences = [
  ...Object.values(out.count), ...Object.values(out.empty), ...Object.values(out.unplaceable),
  ...Object.values(out.place), ...Object.values(out.match), ...Object.values(out.misc).flat(),
  ...out.intervals, out.pure.droppedLine, block.adopt.count, ...block.adopt.lines,
].filter((x) => typeof x === 'string');
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def r() -> dict:
    paths = {
        "off": _path("candidates_base_off"), "particle": _path("candidates_base_particle"),
        "empty": _path("candidates_base_empty"), "single": _path("candidates_single_theta"),
        "raster": _path("event_raster_base"), "rasterParticle": _path("event_raster_base_particle"),
        "voxelsParticle": _path("event_voxels_base_lab_particle"),
        "voxelsSingle": _path("event_voxels_single_local"),
    }
    return _run(_SCRIPT, [(JS / "state.js").as_uri(), (JS / "event_picker.js").as_uri(),
                          (JS / "controls" / "particle_filter.js").as_uri(), paths, INTERVALS])


# ------------------------------------------------------------------ state.js --


def test_the_particle_keys_are_null_by_default_and_out_of_the_filter_params(r):
    state = r["state"]
    keys = ["particle_p_min", "particle_p_max", "particle_theta_min", "particle_theta_max"]
    assert state["defaults"] == dict.fromkeys(keys)
    assert state["keys"] == keys
    assert state["filterKeys"] == ["table_name", "e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max",
                                   "include_undefined_d"]
    assert state["filterWith"] == state["filterKeys"], "filterParams never carries a particle bound"
    assert state["none"] == {} and state["noneActive"] is False
    assert list(state["eventNone"]) == [*state["filterKeys"], "event_number", "shower"]


def test_a_link_carries_the_set_bounds_rounded_to_their_steps(r):
    state = r["state"]
    assert state["read"] == {"p_min": 5.123, "theta_max": 15.04, "coldBoot": False}
    assert state["params"] == {"particle_p_min": 5.123, "particle_theta_max": 15.04}
    assert state["active"] is True
    assert state["eventKeys"] == [*state["filterKeys"], "particle_p_min", "particle_theta_max",
                                  "event_number", "shower"]
    assert state["event"]["event_number"] == 12 and state["event"]["shower"] == "b"
    assert "particle_p_min=5.12" in state["hash"] and "particle_theta_max=15" in state["hash"]
    assert "particle_theta_max=15.04" not in state["hash"]
    assert "particle" not in state["cleared"]["hash"] and state["cleared"]["params"] == {}


@pytest.mark.parametrize("link", ["#particle_p_min=-1", "#particle_theta_min=200", "#particle_theta_max=-0.5",
                                  "#particle_p_max=abc", "#particle_p_max=Infinity",
                                  "#particle_p_min=6&particle_p_max=5"])
def test_an_invalid_or_inverted_bound_keeps_the_built_in_null(r, link):
    assert r["state"]["invalid"][link] == {"params": {}, "coldBoot": False}


def test_an_inverted_angle_drops_only_its_own_pair(r):
    got = r["state"]["invalid"]["#particle_theta_min=20&particle_theta_max=10&particle_p_min=1"]
    assert got["params"] == {"particle_p_min": 1}


def test_the_ranges_admit_their_ends(r):
    assert r["state"]["edges"] == {"particle_p_min": 0, "particle_theta_min": 0, "particle_theta_max": 180}


def test_the_particle_filter_is_never_an_admin_default(r):
    assert r["state"]["defaultable"] is True
    assert r["state"]["afterDefaults"] == {}


# ------------------------------------------------------------- intervalText --


def test_the_interval_is_the_servers_own_string(r):
    for bounds, client, echo in zip(INTERVALS, r["intervals"], r["intervalsEcho"], strict=True):
        p_min, p_max, t_min, t_max = bounds
        server = ParticleSpec(p_min=p_min, p_max=p_max, theta_min_deg=t_min, theta_max_deg=t_max).interval_text()
        assert client == server, bounds
        assert echo == server, bounds
    assert r["intervals"][0] == f"p in 5.00{EN}6.00 GeV and θ in 10.0{EN}15.0°"
    assert r["intervals"][1:5] == ["p ≥ 5.00 GeV", "p ≤ 6.00 GeV", "θ ≥ 10.0°", "θ ≤ 15.0°"]
    assert r["intervals"][-1] == ""


def test_the_interval_matches_the_recorded_server_warning(r):
    interval = r["voxelsInterval"]
    assert interval == f"p in 2.00{EN}3.00 GeV"
    assert f"({interval})" in r["serverWarning"]


# ----------------------------------------------------------------- requests --


def test_pick_params_carry_each_rules_own_keys(r):
    pick = r["pick"]
    base = {"table_name": "demo", "e1_min": 1, "e1_max": 2, "e2_min": None, "e2_max": None, "d_min": None,
            "d_max": None, "include_undefined_d": False}
    assert pick["uniform"]["plain"] == {**base, "rule": "uniform", "seed": 42, "draw": 0}
    assert pick["tilted"]["plain"] == {**base, "rule": "tilted", "seed": 42}
    assert pick["densest"]["plain"] == {**base, "rule": "densest"}
    assert pick["default"] == pick["uniform"]["plain"]
    bounds = {"particle_p_min": 5, "particle_theta_min": 10, "particle_theta_max": 15}
    assert pick["uniform"]["bounded"] == {**base, **bounds, "rule": "uniform", "seed": 44, "draw": 3}
    assert pick["tilted"]["bounded"] == {**base, **bounds, "rule": "tilted", "seed": 44}
    assert pick["densest"]["bounded"] == {**base, **bounds, "rule": "densest"}


def test_no_particle_key_reaches_a_pick_without_a_bound(r):
    for rule in ("uniform", "tilted", "densest"):
        for case in ("plain", "empty"):
            assert not any(k.startswith("particle_") for k in r["pick"][rule][case]), (rule, case)
        assert "particle_p_max" not in r["pick"][rule]["bounded"], "a null bound is never sent"
    from_state = r["pick"]["fromState"]
    assert from_state["particle_theta_min"] == 10 and from_state["rule"] == "tilted" and from_state["seed"] == 43
    assert not {"particle_p_min", "particle_p_max", "particle_theta_max", "draw"} & set(from_state)


def test_candidates_params(r):
    c = r["candidates"]
    assert "event_number" not in c["plain"] and not any(k.startswith("particle_") for k in c["plain"])
    assert c["bounded"]["particle_p_min"] == 5 and "particle_p_max" not in c["bounded"]
    assert c["event"]["event_number"] == 0, "event 0 is an event"
    assert "event_number" not in c["nullEvent"]


def test_the_constants(r):
    c = r["constants"]
    assert c["seed"] == 42 and c["rules"] == ["uniform", "tilted", "densest"]
    assert c["keys"] == ["particle_p_min", "particle_p_max", "particle_theta_min", "particle_theta_max"]
    assert c["step"] == {"p": 0.05, "theta": 0.1}
    assert c["route"] == "/api/event/candidates" and c["frozen"] == [True, True, True]


# ------------------------------------------------------- follow and focus --

FOLLOW = {
    # origin: (in pool, out N > 0, out N = 0)
    "link": ("keep", "flag", "flag"),
    "typed": ("keep", "flag", "flag"),
    "pick": ("keep", "replace", "flag"),
    "tilted": ("keep", "replace", "flag"),
    "step": ("keep", "replace", "flag"),
    "replace": ("keep", "replace", "flag"),
    "densest": ("keep", "flag", "flag"),
}


@pytest.mark.parametrize("origin", list(FOLLOW))
def test_the_follow_decision(r, origin):
    in_pool, out_some, out_none = FOLLOW[origin]
    got = r["follow"]
    assert got[f"{origin}|true|5"] == in_pool and got[f"{origin}|true|0"] == in_pool
    assert got[f"{origin}|false|5"] == out_some
    assert got[f"{origin}|false|0"] == out_none


def test_the_shower_focus(r):
    assert r["focus"] == {"keepA": "a", "keepB": "b", "toB": "b", "toA": "a", "none": "b", "nullMatched": "a",
                          "bothAllowed": "both", "bothRefused": "b", "single": "a"}


# ----------------------------------------------------------------- sentences --


def test_count_lines_two_showers(r):
    c = r["count"]
    assert c["brief"] == ("N = 107 events hold a matching particle (108 matching showers: 43 A, 65 B; 1 event "
                          "matches with both), of the 20,268 selected by E₁, E₂ and D.")
    assert c["noBoth"] == ("N = 107 events hold a matching particle (108 matching showers: 43 A, 65 B), of the "
                           "20,268 selected by E₁, E₂ and D.")
    assert "; 2 events match with both)" in c["twoBoth"]
    assert c["singular"] == ("N = 1 event holds a matching particle (1 matching shower: 1 A, 0 B), of the 3 "
                             "selected by E₁, E₂ and D.")
    assert c["fixtureParticle"] == ("N = 1 event holds a matching particle (1 matching shower: 1 A, 0 B), of the 2 "
                                    "selected by E₁, E₂ and D.")
    assert c["explicitTwo"] == c["fixtureParticle"]
    assert c["fixtureEmpty"] == ("N = 0 events hold a matching particle (0 matching showers: 0 A, 0 B), of the 2 "
                                 "selected by E₁, E₂ and D.")


def test_count_lines_one_shower_and_off(r):
    c = r["count"]
    assert c["single"] == f"N = 312 events whose shower has θ in 10.0{EN}15.0°, of the 5,000 selected by p."
    assert c["singleOne"] == f"N = 1 event whose shower has θ in 10.0{EN}15.0°, of the 5,000 selected by p."
    assert c["fixtureSingle"] == f"N = 73 events whose shower has θ in 20.0{EN}25.0°, of the 287 selected by p."
    assert c["off"] == "Particle filter off: the pickers draw from all 20,268 selected events."
    assert c["offSingle"] == "Particle filter off: the pickers draw from all 5,000 selected events."
    assert c["fixtureOff"] == "Particle filter off: the pickers draw from all 2 selected events."
    assert c["offOne"] == "Particle filter off: the pickers draw from the 1 selected event."


def test_empty_lines(r):
    e = r["empty"]
    assert e["fixture"] == (f"N = 0: no selected event holds a shower with p in 5.00{EN}6.00 GeV that deposited "
                            "energy. Widen the particle filter, or E₁, E₂ and D.")
    assert e["nonEmpty"] == ""
    assert e["off"] == "N = 0: the selection holds no event to draw. Widen E₁, E₂ or D."
    assert e["offSingle"] == "N = 0: the selection holds no event to draw. Widen p."
    assert e["single"] == (f"N = 0: no selected event holds its shower at θ in 10.0{EN}15.0°. Widen the particle "
                           "filter, or p.")
    assert e["singleNamed"] == (f"N = 0: no selected event holds its shower at θ in 20.0{EN}25.0°. Widen the "
                                "particle filter, or p.")


def test_unplaceable_lines(r):
    u = r["unplaceable"]
    assert u["two"] == ("57 selected events have no defined separation (shower A deposited no energy) and are never "
                        "offered; type an event number to draw one.")
    assert u["twoOne"] == ("1 selected event has no defined separation (shower A deposited no energy) and is never "
                           "offered; type an event number to draw it.")
    assert u["single"] == ("57 selected events have no incident direction or entry point and are never offered; "
                           "type an event number to draw one.")
    assert u["none"] == ""


def test_place_lines(r):
    p = r["place"]
    tail = "drawn as asked, and previous / next walk the candidates."
    assert p["brief"] == "Candidate 37 of 107, in event-number order."
    assert p["raster"] == "Candidate 1 of 1, in event-number order."
    assert p["rasterOff"] == "Candidate 1 of 2, in event-number order."
    assert p["voxels"] == f"Not a candidate: no shower matches the particle filter; {tail}"
    assert p["membership"] == p["voxels"], "the candidates route's event block reads alike"
    assert p["gateTwo"] == f"Not a candidate: it has no defined separation, which the pickers need; {tail}"
    assert p["gateMatched"] == p["gateTwo"], "a matching shower outside the pool was refused by the frame gate"
    single = ("Not a candidate: its shower has no incident direction or entry point, which the pickers need; "
              f"{tail}")
    assert p["gateSingle"] == single
    assert p["gateSingleFixture"] == single, "a single-shower voxel block is read as one shower"
    assert p["outside"] == "" and p["outsideOpt"] == "" and p["none"] == ""


def test_match_lines(r):
    m = r["match"]
    assert m["brief"] == "Shower A matches the particle filter: p = 5.41 GeV, θ = 12.3° (0.215 rad)."
    assert m["rasterFixture"] == "Shower A matches the particle filter: p = 2.71 GeV."
    assert m["both"] == "Showers A and B both match the particle filter."
    assert m["other"] == "Shower B is drawn as asked and does not match the particle filter; shower A does."
    assert m["drawnBoth"] == m["brief"]
    assert m["neither"] == "Neither shower matches the particle filter."
    assert m["single"] == "The shower matches the particle filter: θ = 12.3° (0.215 rad)."
    assert m["singleNamed"] == m["single"]
    assert m["singleMiss"] == "The shower does not match the particle filter: θ = 16.3° (0.284 rad)."
    assert m["off"] == ""
    assert m["noValues"] == "Shower A matches the particle filter."


def test_the_other_lines_and_titles(r):
    m = r["misc"]
    assert m["replaced"] == "Event 123 left the candidates; event 456 replaces it."
    assert m["replacedBig"] == "Event 20123 left the candidates; event 4 replaces it.", "event numbers are ids"
    assert m["ensemble"] == (f"The particle filter (p in 5.00{EN}6.00 GeV and θ in 10.0{EN}15.0°) narrows the event "
                             "pickers only; this view draws the whole selection of E₁, E₂ and D.")
    assert m["ensembleSingle"] == (f"The particle filter (θ in 10.0{EN}15.0°) narrows the event pickers only; this "
                                   "view draws the whole selection of p.")
    assert m["ensembleState"] == ("The particle filter (θ ≥ 10.0°) narrows the event pickers only; this view draws "
                                  "the whole selection of E₁, E₂ and D.")
    assert m["ensembleOff"] == "" and m["ensembleEmpty"] == ""
    assert m["scope"] == ("Narrows only which events the pickers offer (Pick for me, Most tilted, previous / next, "
                          "and the 3-D view's Densest). The ensemble panels follow E₁, E₂ and D.")
    assert m["scopeSingle"] == m["scope"].replace("follow E₁, E₂ and D.", "follow p.")
    assert m["pickTitle"] == ("A candidate event drawn uniformly at random under the filters and the particle "
                              "filter: a seeded shuffle, so no event repeats until all have been drawn. Each click "
                              "takes the next draw.")
    assert m["tiltedTitle"] == ("The reference notebook's showcase rule on the candidates: events with more hits "
                                "than the mean, the 20 with the largest incident angle of a matching shower, one "
                                "drawn at random. Each click takes the next seed.")
    assert m["densestTitle"] is None
    empty = r["empty"]["fixture"]
    assert m["emptyTitles"] == [empty, empty, empty]
    assert m["noPayload"] == m["pickTitle"]
    assert m["open3d"] == ("Open this event and shower in the Models page's 3-D view, with every filter; the "
                           "Physics page keeps its own event.")
    assert m["open3dCanonical"] == (m["open3d"] + " The D-frame draws no single event, so the 3-D view opens in "
                                    "the Absolute frame.")
    assert m["open2d"] == ("Open this event in the Physics page's Event Inspector: one shower in the Absolute, "
                           "per-shower translated and Local frames, with every filter.")


def test_no_sentence_signs_a_number_with_a_hyphen(r):
    assert len(r["sentences"]) > 50
    for text in r["sentences"]:
        assert not HYPHEN_NUMBER.search(text), text


# ----------------------------------------------------------------- the links --


def test_the_3d_link_keeps_every_filter_and_opens_the_absolute_frame_for_the_d_frame(r):
    links = r["links"]
    assert links["canonical"] == ("/models#table_name=demo&e1_min=2&particle_p_min=5&particle_theta_max=15&event=12"
                                  "&shower=b&voxel_event=12&voxel_shower=b&voxel_scope=event")
    assert links["canonicalFromHash"] == links["canonical"]
    assert links["lab"] == "/models#voxel_event=7&voxel_scope=event", "shower A and the Absolute frame are built in"
    assert links["local"] == "/models#frame=local&e2_max=9&voxel_event=7&voxel_scope=event"
    assert links["trans"] == "/models#voxel_event=0&voxel_shower=b&voxel_scope=event&frame=trans"
    assert links["empty"] == "/models#voxel_event=3&voxel_scope=event"


def test_the_2d_link_draws_one_shower(r):
    links = r["links"]
    assert links["twoD"] == ("/#voxel_event=7&voxel_shower=b&voxel_scope=event&particle_theta_min=10&msub=views"
                             "&event=7&shower=b")
    assert links["twoDBoth"] == "/#voxel_event=7&voxel_shower=both&event=7&shower=b"
    assert links["twoDBothNone"] == "/#event=7", "no match: shower A, the built-in, left out"
    assert links["twoDA"] == "/#event=9"


# ------------------------------------------------------------ the block's parts --


def test_the_slider_domains_snap_outward(r):
    pure = r["pure"]
    assert pure["domainP"] == [2.7, 17.9]
    assert pure["domainTheta"] == [16.2, 26.5]
    assert pure["domainSingle"] == [16.2, 26.5]
    assert pure["domainNull"] is None and pure["domainMissing"] is None


def test_a_bound_at_its_domain_edge_is_stored_as_null(r):
    pure = r["pure"]
    assert pure["edges"] == {"particle_p_min": None, "particle_p_max": None}
    assert pure["inside"] == {"particle_p_min": 5, "particle_p_max": 6}
    assert pure["loEdge"] == {"particle_theta_min": None, "particle_theta_max": 20}
    assert pure["hiEdge"] == {"particle_theta_min": 18.3, "particle_theta_max": None}
    assert pure["dust"] == {"particle_p_min": 2.05, "particle_p_max": None}
    assert pure["noDomain"] == {"particle_p_min": 5, "particle_p_max": 6}


def test_a_new_domain_drops_the_bounds_it_cannot_hold(r):
    pure = r["pure"]
    assert pure["dropFits"] == {"patch": {}, "dropped": []}
    assert pure["dropOutside"]["patch"] == {"particle_p_min": None, "particle_p_max": None}
    assert [d["axis"] for d in pure["dropOutside"]["dropped"]] == ["p"]
    assert pure["dropInverted"]["patch"] == {"particle_p_min": None, "particle_p_max": None}
    assert pure["dropNoDomain"] == {"patch": {}, "dropped": []}
    assert pure["droppedLine"] == ("Dropped from the particle filter, outside this experiment's range: p ≥ 18.50 GeV "
                                   f"(this experiment's range: 2.70{EN}17.90 GeV).")
    assert pure["droppedNone"] == ""


def test_the_blocks_lines(r):
    lines = r["pure"]["lines"]
    assert lines["off"] == [r["count"]["fixtureOff"]]
    assert lines["particle"] == [r["count"]["fixtureParticle"]]
    assert lines["empty"] == [r["empty"]["fixture"]], "at N = 0 the empty line takes the count's place"
    assert lines["single"] == [r["count"]["fixtureSingle"]]
    assert lines["unplaceable"][1] == r["unplaceable"]["two"] and lines["unplaceable"][2] == "Note."


# ------------------------------------------------------------ the block itself --


def test_the_block_is_disabled_until_the_first_bounds(r):
    before = r["block"]["before"]
    assert before["disabled"] == [True, True, True, True]
    assert before["payload"] is None


def test_adopting_an_experiment_takes_its_domains_and_drops_what_does_not_fit(r):
    adopt = r["block"]["adopt"]
    assert adopt["hidden"] is False and adopt["pHidden"] is False
    # The link's θ ≤ 40° lies beyond 16.2–26.5°: asked once with it, dropped, asked again.
    assert [q.get("particle_theta_max") for q in adopt["requests"]] == ["40", None]
    assert all(q["particle_p_max"] == "3" for q in adopt["requests"])
    assert adopt["params"] == {"particle_p_max": 3}
    assert "particle_theta_max" not in adopt["hash"] and "particle_p_max=3" in adopt["hash"]
    assert adopt["lines"] == [
        r["count"]["fixtureParticle"],
        f"Dropped from the particle filter, outside this experiment's range: θ ≤ 40.0° (this experiment's range: "
        f"16.2{EN}26.5°).",
    ]
    assert adopt["domains"] == {"p": [2.7, 17.9], "theta": [16.2, 26.5]}
    # RangeSlider snaps its own domain again (17.900000000000002); its values are rounded.
    assert adopt["sliderP"] == [pytest.approx(2.7), pytest.approx(17.9), [2.7, 3]]
    assert adopt["sliderTheta"] == [pytest.approx(16.2), pytest.approx(26.5), [16.2, 26.5]]
    assert adopt["enabled"] == [False, False, False, False]
    assert adopt["scope"] == r["misc"]["scope"]
    assert adopt["clearDisabled"] is False
    assert adopt["commits"] == 1, "the dropped bound moved the pool, so the page follows"
    assert adopt["adoptedN"] == 1 and adopt["seen"] == [1]


def test_a_refresh_says_the_drop_only_once(r):
    refresh = r["block"]["refresh"]
    assert len(refresh["requests"]) == 1 and refresh["requests"][0]["particle_p_max"] == "3"
    assert refresh["count"] == r["count"]["fixtureParticle"]
    assert refresh["commits"] == 1, "a refresh is not a commit"


def test_a_drag_previews_nothing_and_a_release_commits(r):
    block = r["block"]
    assert block["drag"] == {"requests": 0, "params": {"particle_p_max": 3}}
    commit = block["commit"]
    assert commit["params"] == {"particle_p_min": 5.5}, "the upper bound at the domain's edge is stored as null"
    assert len(commit["requests"]) == 1
    query = commit["requests"][0]
    assert query["particle_p_min"] == "5.5" and "particle_p_max" not in query
    assert query["table_name"] == "experiment_baseline"
    assert commit["commits"] == 2 and commit["payload"] == 0
    assert commit["count"] == r["empty"]["fixture"]
    assert commit["clearDisabled"] is False and "particle_p_min=5.5" in commit["hash"]
    assert block["blur"] == {"requests": 0, "commits": 2}


def test_clear_sets_every_bound_to_null_and_asks_again(r):
    clear = r["block"]["clear"]
    assert clear["params"] == {} and clear["active"] is False
    assert len(clear["requests"]) == 1 and not any(k.startswith("particle_") for k in clear["requests"][0])
    assert clear["commits"] == 3
    assert clear["sliderP"] == [2.7, 17.9]
    assert clear["clearDisabled"] is True
    assert clear["count"] == r["count"]["fixtureOff"]


def test_one_shower_filters_on_theta_alone(r):
    single = r["block"]["single"]
    assert single["pHidden"] is True
    assert single["params"] == {}, "p's keys are cleared silently"
    assert single["scope"] == r["misc"]["scopeSingle"]
    assert [q["table_name"] for q in single["requests"]] == ["single_hits"]
    assert single["count"] == r["count"]["fixtureSingle"]
    # The θ hint names the one shower's own column, and two showers get the markup's text back.
    assert single["thetaHint"] == single["singleHint"]
    assert "incoming_theta)" in single["thetaHint"] and "_A" not in single["thetaHint"]
    restored = r["block"]["restoredHint"]
    assert restored["text"] == restored["markup"]


def test_a_disabled_block_hides_and_asks_nothing(r):
    disabled = r["block"]["disabled"]
    assert disabled == {"hidden": True, "requests": 0, "adopted": None, "refresh": None, "reason": "No events."}


def test_a_failure_is_rethrown_and_an_abort_is_null(r):
    assert r["block"]["error"] == "Boom."
    assert r["block"]["abort"] is None


def test_the_recorded_fixtures_are_the_shapes_read_here():
    """The sentences above read these fields; the backend's recordings must keep them."""
    for name in ("candidates_base_off", "candidates_base_particle", "candidates_base_empty",
                 "candidates_single_theta"):
        c = _payload(name)["candidates"]
        assert {"particle", "n_selection", "n_unplaceable", "n_events", "n_showers", "by_shower", "n_both",
                "showers"} <= set(c), name
    for name in ("event_raster_base_particle", "event_voxels_base_lab_particle"):
        cands = _payload(name)["event"]["candidates"]
        assert {"particle", "in_pool", "index", "n_events", "matched", "prev_matched", "next_matched"} <= set(cands)
    shower = _payload("event_raster_base_particle")["event"]["shower"]
    assert {"key", "label", "momentum_gev", "theta", "theta_deg"} <= set(shower)
