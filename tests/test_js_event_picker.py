"""The particle filter's client half, under Node: state, sentences, links and the sidebar block.

Brief ``data/dev/design/particle-filter/brief.md`` §4–§6:

* ``state.js``: the four particle keys are view state (null by default,
  checked and rounded like every numeric key, never Admin defaults);
  ``filterParams()`` is unchanged, ``particleParams()`` holds only the set
  bounds; ``eventPoolParams()`` is the experiment, ``basis=experiment`` and
  those bounds, never an E₁/E₂/D key, and ``eventParams()`` adds the event to
  it; ``psub`` and its legacy rule (physics-subpages brief §4);
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

The physics-subpages brief (``data/dev/design/physics-subpages/brief.md``
§4–§6) adds the experiment basis: every sentence under ``basis=experiment`` is
checked on the Stage 1 recordings (``candidates_*_experiment*``,
``pick_*_experiment``, ``event_raster_*_experiment``), and every sentence
without ``basis`` keeps its earlier wording, checked on the older recordings.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import math

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
out.state.legacyPsub = s.get('psub');
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
// The pickers' pool: the experiment and the particle bounds, never an E₁/E₂/D key, whatever the link narrows.
s = fresh('#table_name=demo&e1_min=2&e1_max=9&e2_max=4&d_min=100&include_undefined_d=true&particle_theta_min=10&event=4');
out.state.pool = s.eventPoolParams();
out.state.poolEvent = s.eventParams();
out.state.poolFilters = s.filterParams();
out.state.poolNone = fresh('#table_name=demo').eventPoolParams();
// psub: Entire selection by default and never written; a pre-split `event=` link opens the Event viewer.
const psubOf = (hash) => { const t = fresh(hash); return { psub: t.get('psub'), hash: t.hashString() }; };
out.psub = {
  constants: { psubs: st.PSUBS, frozen: Object.isFrozen(st.PSUBS), defaultPsub: st.DEFAULTS.psub,
    after: Object.keys(st.DEFAULTS)[Object.keys(st.DEFAULTS).indexOf('compare') + 1] },
  cold: psubOf(''),
  legacy: psubOf('#event=5'),
  legacyZero: psubOf('#event=0&shower=b'),
  explicitSelection: psubOf('#event=5&psub=selection'),
  explicitEvent: psubOf('#psub=event'),
  explicitBoth: psubOf('#psub=event&event=5'),
  invalidPsub: psubOf('#event=5&psub=bogus'),
  invalidEvent: psubOf('#event=1.5'),
  bogusAlone: psubOf('#psub=bogus'),
};
s = fresh('');
s.set({ psub: 'event' });
out.psub.writtenEvent = window.location.hash;
s.set({ psub: 'selection' });
out.psub.writtenSelection = window.location.hash;
s.set({ event: 7 });
out.psub.setEventOnly = { psub: s.get('psub'), hash: window.location.hash };
s = fresh('');
out.psub.defaultable = s.applyDefaults({ table_name: 'x', psub: 'event' });
out.psub.afterDefaults = s.get('psub');
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
s = fresh('#table_name=demo&e1_min=2&particle_theta_min=10');
out.pick.fromPool = ep.pickParams({ filters: s.eventPoolParams(), particle: s.particleParams(), draw: 2 });
out.candidates_fromPool = ep.candidatesParams({ filters: s.eventPoolParams(), particle: s.particleParams(),
  eventNumber: 5 });
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
  offGated: ep.countLine(two({ particle: echo(), n_selection: 20325, n_unplaceable: 57, n_events: 20268 })),
  offGatedSingle: ep.countLine(one({ particle: echo(), n_selection: 5000, n_unplaceable: 3, n_events: 4997 })),
  offGatedOne: ep.countLine(two({ particle: echo(), n_selection: 2, n_unplaceable: 1, n_events: 1 })),
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
  // Review S2: the only match is a shower of an event the frame gate refuses.
  gated: ep.emptyLine(two({ n_selection: 2, n_unplaceable: 1, n_events: 0, particle: echo([6, 7]) })),
};
out.unplaceable = {
  two: ep.unplaceableLine(two({ n_unplaceable: 57 })),
  twoOne: ep.unplaceableLine(two({ n_unplaceable: 1 })),
  single: ep.unplaceableLine(one({ n_unplaceable: 57 })),
  singleOne: ep.unplaceableLine(one({ n_unplaceable: 1 })),
  none: ep.unplaceableLine(P.off),
};
// The experiment basis (physics-subpages brief §5.1).
const twoX = (over) => two({ basis: 'experiment', n_selection: 20325, ...over });
const oneX = (over) => one({ basis: 'experiment', ...over });
out.exp = {
  count: {
    brief: ep.countLine(twoX()),
    noBoth: ep.countLine(twoX({ n_both: 0 })),
    twoBoth: ep.countLine(twoX({ n_both: 2 })),
    singular: ep.countLine(twoX({ n_selection: 3, n_events: 1, n_showers: 1, by_shower: { a: 1, b: 0 }, n_both: 0 })),
    oneTotal: ep.countLine(twoX({ n_selection: 1, n_events: 1, n_showers: 1, by_shower: { a: 1, b: 0 }, n_both: 0 })),
    single: ep.countLine(oneX()),
    singleOne: ep.countLine(oneX({ n_events: 1, n_showers: 1 })),
    off: ep.countLine(twoX({ particle: echo(), n_selection: 20268, n_events: 20268 })),
    offOne: ep.countLine(twoX({ particle: echo(), n_selection: 1, n_events: 1 })),
    offEmpty: ep.countLine(twoX({ particle: echo(), n_selection: 4, n_unplaceable: 4, n_events: 0 })),
    offGated: ep.countLine(twoX({ particle: echo(), n_unplaceable: 57, n_events: 20268 })),
    offGatedOne: ep.countLine(twoX({ particle: echo(), n_selection: 2, n_unplaceable: 1, n_events: 1 })),
    offGatedSingle: ep.countLine(oneX({ particle: echo(), n_unplaceable: 3, n_events: 4997 })),
    fixtureOff: ep.countLine(P.expOff),
    fixtureParticle: ep.countLine(P.expParticle),
    fixtureSingle: ep.countLine(P.expSingle),
    fixtureSingleNamed: ep.countLine(P.expSingle, { nShowers: 1 }),
  },
  empty: {
    off: ep.emptyLine(twoX({ particle: echo(), n_events: 0 })),
    offSingle: ep.emptyLine(oneX({ particle: echo(), n_events: 0 })),
    two: ep.emptyLine(twoX({ n_events: 0, particle: echo([5, 6]) })),
    single: ep.emptyLine(oneX({ n_events: 0 })),
    nonEmpty: ep.emptyLine(P.expParticle),
    titles: ep.PICK_RULES.map((rule) => ep.pickerTitle(rule, twoX({ n_events: 0, particle: echo([5, 6]) }))),
  },
  unplaceable: {
    two: ep.unplaceableLine(twoX({ n_unplaceable: 57 })),
    twoOne: ep.unplaceableLine(twoX({ n_unplaceable: 1 })),
    single: ep.unplaceableLine(oneX({ n_unplaceable: 57 })),
    singleOne: ep.unplaceableLine(oneX({ n_unplaceable: 1 })),
    none: ep.unplaceableLine(P.expOff),
  },
  pool: {
    fixtureOff: ep.poolLine(P.expOff),
    fixtureParticle: ep.poolLine(P.expParticle),
    fixtureSingle: ep.poolLine(P.expSingle),
    fixtureSingleBlock: ep.poolLine(P.expSingle.candidates),
    singleActive: ep.poolLine(oneX(), { nShowers: 1 }),
    twoActive: ep.poolLine(twoX()),
    rasterTwo: ep.poolLine(P.rasterExp.event),
    rasterSingle: ep.poolLine(P.rasterSingleExp.event),
    voxels: ep.poolLine(P.voxelsExp.event),
    pickTwo: ep.poolLine(P.pickBase, { nShowers: 2 }),
    pickSingle: ep.poolLine(P.pickSingle, { nShowers: 1 }),
    explicitOne: ep.poolLine(P.expOff, { nShowers: 1 }),
    oldCandidates: ep.poolLine(P.off),
    oldParticle: ep.poolLine(P.particle),
    oldRaster: ep.poolLine(P.raster.event),
    none: ep.poolLine(null),
  },
  place: {
    raster: ep.placeLine(P.rasterExp.event),
    rasterSingle: ep.placeLine(P.rasterSingleExp.event),
    membership: ep.placeLine(P.expParticle.event),
    voxels: ep.placeLine(P.voxelsExp.event),
  },
  match: {
    raster: ep.matchLine({ candidates: P.rasterExp.event.candidates, drawn: 'a', showers: P.rasterExp.event.shower }),
  },
  picks: { two: P.pickBase.rule, single: P.pickSingle.rule, basis: [P.pickBase.basis, P.pickSingle.basis],
    keys: [Object.keys(P.pickBase), Object.keys(P.pickSingle)] },
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
  twoDKeepsSelection: ep.eventIn2dHref({ hash: 'psub=selection&e1_min=2', event: 9, shower: 'a' }),
  viewer3d: ep.eventIn3dHref({ hash: 'psub=event&event=9&shower=b', event: 9, shower: 'b', frame: 'lab' }),
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
out.pure.droppedTwo = pf.droppedLine([...out.pure.dropOutside.dropped,
  { axis: 'theta', lo: 30, hi: 40, domain: [16.2, 26.5] }]);
out.pure.failedLine = pf.failedLine(Object.assign(new Error('Service Unavailable'), { status: 503 }));
out.pure.failedBare = pf.failedLine(null);
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
const P_HINT = 'Incident momentum of either shower (incoming_momentum_A or _B), in GeV.';
byId('particle-p-hint').append(document.createTextNode(P_HINT));
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
window.location.hash = '#table_name=experiment_baseline&particle_theta_max=40&particle_p_max=3&e1_min=3&d_max=900';
const state = new st.State();
let commits = 0;
const seen = [];
const reported = [];
const control = pf.mountParticleFilter({ state, onCommit: () => { commits += 1; },
  onCandidates: (payload) => seen.push(payload?.candidates?.n_events ?? null),
  onError: (error, context) => reported.push(`${context}: ${error.message}`) });
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

// A single-shower experiment: p and θ both shown, p's keys kept (the pool ignores the ensemble's p window).
state.set({ table_name: 'single_hits', particle_p_min: 3 }, { silent: true });
requests.length = 0;
await control.adopt({ table_name: 'single_hits' }, { enabled: true, nShowers: 1 });
block.single = { pHidden: byId('ctl-particle-p').hidden, params: state.particleParams(),
  scope: byId('particle-scope').textContent, requests: requests.map((r) => r.query),
  count: byId('particle-count').textContent, thetaHint: byId('particle-theta-hint').textContent,
  singleHint: pf.SINGLE_THETA_HINT, pHint: byId('particle-p-hint').textContent, singlePHint: pf.SINGLE_P_HINT };
state.set({ particle_p_min: null }, { silent: true });

// Disabled: hidden, no request, refresh null.
requests.length = 0;
const disabled = await control.adopt({ table_name: 'events' }, { enabled: false, nShowers: 1, reason: 'No events.' });
block.disabled = { hidden: byId('group-particle').hidden, requests: requests.length, adopted: disabled,
  refresh: await control.refresh(), reason: control.reason };

// A failure that is not an abort is rethrown; an abort is null.
await control.adopt({ table_name: 'experiment_baseline' }, { enabled: true, nShowers: 2 });
block.restoredHint = { text: byId('particle-theta-hint').textContent, markup: THETA_HINT,
  pText: byId('particle-p-hint').textContent, pMarkup: P_HINT };

// Counted only while shown: hidden, a refresh, an adopt and a commit send nothing and leave the count stale;
// shown again, one count; shown when fresh, none.
const shownCommits = commits;
state.set({ table_name: 'experiment_baseline' }, { silent: true });
await control.setShown(false);
requests.length = 0;
const hiddenRefresh = await control.refresh();
const hiddenAdopt = await control.adopt({ table_name: 'experiment_baseline' }, { enabled: true, nShowers: 2 });
const hiddenCount = byId('particle-count').textContent;
byId('particle-clear').disabled = false;
state.set({ particle_theta_min: 20 });
byId('particle-clear').click();
await settle();
block.hiddenState = { refresh: hiddenRefresh, adopt: hiddenAdopt, requests: requests.length, stale: control.stale,
  shown: control.shown, count: hiddenCount, commits: commits - shownCommits, params: state.particleParams() };
const shownPayload = await control.setShown(true);
block.shownAgain = { requests: requests.map((r) => r.query), n: shownPayload?.candidates?.n_events ?? null,
  stale: control.stale, count: byId('particle-count').textContent, domains: control.domains };
requests.length = 0;
block.shownFresh = { result: await control.setShown(true), requests: requests.length };
const failingFetch = globalThis.fetch;
await control.setShown(false);
await control.refresh();
const reportedBefore = reported.length;
globalThis.fetch = async () => ({ ok: false, status: 500, statusText: 'Boom', json: async () => ({ detail: 'Boom.' }) });
block.shownFails = { result: await control.setShown(true), reported: reported.slice(reportedBefore),
  count: byId('particle-count').textContent };
globalThis.fetch = failingFetch;
await control.refresh();
reported.length = 0;
const okFetch = globalThis.fetch;
globalThis.fetch = async () => ({ ok: false, status: 500, statusText: 'Boom', json: async () => ({ detail: 'Boom.' }) });
seen.length = 0;
try { await control.refresh(); block.error = 'none'; } catch (error) { block.error = error.message; }
// Review U3: the failed count leaves no stale line or pool behind.
block.failed = { count: byId('particle-count').textContent, payload: control.payload, seen: [...seen],
  reported: [...reported] };
globalThis.fetch = async () => { const e = new Error('gone'); e.name = 'AbortError'; throw e; };
block.abort = await control.refresh();
// Review U3: a count that fails after the block's own commit is caught and reported through onError, never
// left as an unhandled rejection; onCommit still runs.
const unhandled = [];
const onUnhandled = (reason) => unhandled.push(String(reason?.message ?? reason));
process.on('unhandledRejection', onUnhandled);
globalThis.fetch = okFetch;
await control.refresh();
const commitsBefore = commits;
seen.length = 0;
globalThis.fetch = async () => ({ ok: false, status: 503, statusText: 'Service Unavailable',
  json: async () => ({ detail: 'Service Unavailable' }) });
byId('pp-hi').value = String(Math.round((3 - control.sliders.p.min) / 0.05));
byId('pp-hi').dispatch('change');
await settle();
const afterSlider = { count: byId('particle-count').textContent, payload: control.payload, seen: [...seen],
  reported: [...reported], commits: commits - commitsBefore };
byId('particle-clear').click();
await settle();
await new Promise((resolve) => setTimeout(resolve, 5));
process.off('unhandledRejection', onUnhandled);
block.commitFailure = { afterSlider, afterClear: { count: byId('particle-count').textContent,
  reported: [...reported], commits: commits - commitsBefore }, unhandled };
globalThis.fetch = okFetch;
out.block = block;

// Every sentence written above.
out.sentences = [
  ...Object.values(out.count), ...Object.values(out.empty), ...Object.values(out.unplaceable),
  ...Object.values(out.place), ...Object.values(out.match), ...Object.values(out.misc).flat(),
  ...out.intervals, out.pure.droppedLine, block.adopt.count, ...block.adopt.lines,
  ...Object.values(out.exp).flatMap((group) => Object.values(group)).flat(),
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
        "expOff": _path("candidates_base_experiment"),
        "expParticle": _path("candidates_base_experiment_particle"),
        "expSingle": _path("candidates_single_experiment"),
        "pickBase": _path("pick_base_uniform_experiment"),
        "pickSingle": _path("pick_single_uniform_experiment"),
        "rasterExp": _path("event_raster_base_experiment"),
        "rasterSingleExp": _path("event_raster_single_experiment"),
        "voxelsExp": _path("event_voxels_base_lab_experiment"),
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
    # The Event Inspector asks in the pickers' pool, which no E₁/E₂/D key narrows (physics-subpages §4).
    assert list(state["eventNone"]) == ["table_name", "basis", "event_number", "shower"]
    assert state["eventNone"]["basis"] == "experiment"


def test_a_link_carries_the_set_bounds_rounded_to_their_steps(r):
    state = r["state"]
    assert state["read"] == {"p_min": 5.123, "theta_max": 15.04, "coldBoot": False}
    assert state["params"] == {"particle_p_min": 5.123, "particle_theta_max": 15.04}
    assert state["active"] is True
    assert state["eventKeys"] == ["table_name", "basis", "particle_p_min", "particle_theta_max",
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


def test_the_pickers_pool_carries_no_selection_key(r):
    """physics-subpages §4: the experiment, basis=experiment and the set bounds, whatever E₁, E₂ and D say."""
    state = r["state"]
    assert state["pool"] == {"table_name": "demo", "basis": "experiment", "particle_theta_min": 10}
    assert state["poolEvent"] == {**state["pool"], "event_number": 4, "shower": "a"}
    assert state["poolNone"] == {"table_name": "demo", "basis": "experiment"}
    for params in (state["pool"], state["poolEvent"], state["poolNone"], state["eventNone"]):
        assert not {"e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d"} & set(params)
    # The ensemble's own filter params are untouched: the seven keys, the narrowed bounds kept.
    filters = state["poolFilters"]
    assert list(filters) == state["filterKeys"]
    assert filters["e1_min"] == 2 and filters["d_min"] == 100 and filters["include_undefined_d"] is True


def test_psub_is_entire_selection_by_default_and_never_written(r):
    ps = r["psub"]
    assert ps["constants"] == {"psubs": ["selection", "event"], "frozen": True, "defaultPsub": "selection",
                               "after": "psub"}
    assert ps["cold"] == {"psub": "selection", "hash": ""}
    assert ps["explicitEvent"] == {"psub": "event", "hash": "psub=event"}
    assert ps["writtenEvent"] == "#psub=event"
    assert ps["writtenSelection"] == "", "psub=selection is never written"
    assert ps["bogusAlone"] == {"psub": "selection", "hash": ""}


def test_a_pre_split_event_link_opens_the_event_viewer(r):
    """The legacy rule: a valid `event` and no valid `psub` open the viewer; an explicit psub always wins."""
    ps = r["psub"]
    assert ps["legacy"] == {"psub": "event", "hash": "event=5&psub=event"}
    assert ps["legacyZero"]["psub"] == "event", "event 0 is an event"
    assert ps["explicitSelection"] == {"psub": "selection", "hash": "event=5"}
    assert ps["explicitBoth"]["psub"] == "event"
    assert ps["invalidPsub"]["psub"] == "event", "an unreadable psub names nothing, so the legacy rule holds"
    assert ps["invalidEvent"]["psub"] == "selection", "an unreadable event pins nothing"
    assert r["state"]["legacyPsub"] == "event", "the particle link of the state tests pins event 12"
    # Pinning an event by hand is not a subpage switch: the page writes psub itself (physics_subpages.js).
    assert ps["setEventOnly"] == {"psub": "selection", "hash": "#event=7"}


def test_psub_is_never_an_admin_default(r):
    assert r["psub"]["defaultable"] is True and r["psub"]["afterDefaults"] == "selection"


def test_the_ranges_admit_their_ends(r):
    assert r["state"]["edges"] == {"particle_p_min": 0, "particle_theta_min": 0, "particle_theta_max": 180}


def test_the_particle_filter_is_never_an_admin_default(r):
    assert r["state"]["defaultable"] is True
    assert r["state"]["afterDefaults"] == {}


# ------------------------------------------------------------- intervalText --


def test_the_interval_is_the_servers_own_string(r):
    # Fails in a worktree that has the client's θ radians and not yet the server's (pf-fixs changes
    # ParticleSpec.interval_text in lockstep, brief-fix decision 2); kept as the parity check.
    for bounds, client, echo in zip(INTERVALS, r["intervals"], r["intervalsEcho"], strict=True):
        p_min, p_max, t_min, t_max = bounds
        server = ParticleSpec(p_min=p_min, p_max=p_max, theta_min_deg=t_min, theta_max_deg=t_max).interval_text()
        assert client == server, bounds
        assert echo == server, bounds


def _agreed_interval(p_min, p_max, t_min, t_max) -> str:
    """Brief-fix decision 2, written out in Python: p to 2 decimals; θ to 1 with math.radians(θ) to 3 beside it."""
    def axis(symbol, lo, hi, digits, unit, rad):
        extra = (lambda *v: f" ({EN.join(f'{math.radians(x):.{3}f}' for x in v)} rad)") if rad else (lambda *v: "")
        if lo is not None and hi is not None:
            return f"{symbol} in {lo:.{digits}f}{EN}{hi:.{digits}f}{unit}{extra(lo, hi)}"
        if lo is not None:
            return f"{symbol} ≥ {lo:.{digits}f}{unit}{extra(lo)}"
        if hi is not None:
            return f"{symbol} ≤ {hi:.{digits}f}{unit}{extra(hi)}"
        return ""
    return " and ".join(x for x in (axis("p", p_min, p_max, 2, " GeV", False),
                                    axis("θ", t_min, t_max, 1, "°", True)) if x)


def test_the_interval_writes_theta_in_degrees_with_radians_beside_them(r):
    """Review S5, brief-fix decision 2: the agreed format, exactly, from the view-state keys and from the echo."""
    assert r["intervals"][0] == f"p in 5.00{EN}6.00 GeV and θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)"
    assert r["intervals"][1:5] == ["p ≥ 5.00 GeV", "p ≤ 6.00 GeV", "θ ≥ 10.0° (0.175 rad)", "θ ≤ 15.0° (0.262 rad)"]
    assert r["intervals"][6] == f"θ in 20.0{EN}25.0° (0.349{EN}0.436 rad)"
    assert r["intervals"][-1] == ""
    for bounds, client, echo in zip(INTERVALS, r["intervals"], r["intervalsEcho"], strict=True):
        assert client == _agreed_interval(*bounds), bounds
        assert echo == client, bounds


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


def test_pick_and_candidates_params_from_the_pool(r):
    """physics-subpages §5.2: the callers pass state.eventPoolParams(); its bounds again as `particle` are harmless."""
    pool = {"table_name": "demo", "basis": "experiment", "particle_theta_min": 10}
    assert r["pick"]["fromPool"] == {**pool, "rule": "uniform", "seed": 42, "draw": 2}
    assert r["candidates_fromPool"] == {**pool, "event_number": 5}


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
    t1015 = f"θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)"
    assert c["single"] == f"N = 312 events whose shower has {t1015}, of the 5,000 selected by p."
    assert c["singleOne"] == f"N = 1 event whose shower has {t1015}, of the 5,000 selected by p."
    assert c["fixtureSingle"] == (f"N = 73 events whose shower has θ in 20.0{EN}25.0° (0.349{EN}0.436 rad), of the "
                                  "287 selected by p.")
    assert c["off"] == "Particle filter off: the pickers draw from all 20,268 selected events."
    assert c["offSingle"] == "Particle filter off: the pickers draw from all 5,000 selected events."
    assert c["fixtureOff"] == "Particle filter off: the pickers draw from all 2 selected events."
    assert c["offOne"] == "Particle filter off: the pickers draw from the 1 selected event."
    # Review U6: with selected events the frame gate refuses, never "all".
    assert c["offGated"] == ("Particle filter off: the pickers draw from the 20,268 of the 20,325 selected events "
                             "with a defined separation.")
    assert c["offGatedSingle"] == ("Particle filter off: the pickers draw from the 4,997 of the 5,000 selected events "
                                   "with an incident direction and an entry point.")
    assert c["offGatedOne"] == ("Particle filter off: the pickers draw from the 1 of the 2 selected events with a "
                                "defined separation.")


def test_count_lines_under_the_experiment_basis(r):
    """physics-subpages §5.1: the pool counted against the whole experiment, one shower and two."""
    c = r["exp"]["count"]
    t1015 = f"θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)"
    assert c["brief"] == ("N = 107 events hold a matching particle (108 matching showers: 43 A, 65 B; 1 event "
                          "matches with both), of the 20,325 events of the experiment.")
    assert c["noBoth"] == ("N = 107 events hold a matching particle (108 matching showers: 43 A, 65 B), of the "
                           "20,325 events of the experiment.")
    assert "; 2 events match with both), of the 20,325 events of the experiment." in c["twoBoth"]
    assert c["singular"] == ("N = 1 event holds a matching particle (1 matching shower: 1 A, 0 B), of the 3 events "
                             "of the experiment.")
    assert c["oneTotal"].endswith("of the 1 event of the experiment.")
    assert c["fixtureParticle"] == ("N = 1 event holds a matching particle (1 matching shower: 1 A, 0 B), of the 2 "
                                    "events of the experiment.")
    assert c["single"] == f"N = 312 events whose shower has {t1015}, of the 5,000 events of the experiment."
    assert c["singleOne"] == f"N = 1 event whose shower has {t1015}, of the 5,000 events of the experiment."
    assert c["off"] == "Particle filter off: the pickers draw from all 20,268 events of the experiment."
    assert c["offOne"] == "Particle filter off: the pickers draw from the 1 event of the experiment."
    assert c["offEmpty"] == "Particle filter off: the experiment holds no event the pickers can place."
    assert c["offGated"] == ("Particle filter off: the pickers draw from the 20,268 of the experiment's 20,325 events "
                             "with a defined separation.")
    assert c["offGatedOne"] == ("Particle filter off: the pickers draw from the 1 of the experiment's 2 events with a "
                                "defined separation.")
    assert c["offGatedSingle"] == ("Particle filter off: the pickers draw from the 4,997 of the experiment's 5,000 "
                                   "events with an incident direction and an entry point.")
    assert c["fixtureOff"] == "Particle filter off: the pickers draw from all 2 events of the experiment."
    assert c["fixtureSingle"] == "Particle filter off: the pickers draw from all 287 events of the experiment."
    assert c["fixtureSingleNamed"] == c["fixtureSingle"]
    assert not any("selected" in line for line in c.values()), "the experiment basis never names the selection"


def test_empty_and_unplaceable_lines_under_the_experiment_basis(r):
    e = r["exp"]["empty"]
    assert e["off"] == "N = 0: the experiment holds no event the pickers can place."
    assert e["offSingle"] == e["off"]
    assert e["two"] == (f"N = 0: no event of the experiment with a defined separation holds a shower with p in "
                        f"5.00{EN}6.00 GeV that deposited energy. Widen the particle filter.")
    assert e["single"] == (f"N = 0: no event of the experiment with an incident direction and an entry point has its "
                           f"shower at θ in 10.0{EN}15.0° (0.175{EN}0.262 rad). Widen the particle filter.")
    assert e["nonEmpty"] == ""
    assert e["titles"] == [e["two"]] * 3, "at N = 0 every picker's title is the empty line"
    u = r["exp"]["unplaceable"]
    assert u["two"] == ("57 events of the experiment have no defined separation (shower A deposited no energy) and "
                        "are never offered; to draw one, type its number and choose shower B.")
    assert u["twoOne"] == ("1 event of the experiment has no defined separation (shower A deposited no energy) and "
                           "is never offered; to draw it, type its number and choose shower B.")
    assert u["single"] == ("57 events of the experiment have no incident direction or entry point, so the per-shower "
                           "frames cannot place them and they are never offered.")
    assert u["singleOne"] == ("1 event of the experiment has no incident direction or entry point, so the per-shower "
                              "frames cannot place it and it is never offered.")
    assert u["none"] == ""


def test_the_pool_line(r):
    """physics-subpages §5.1 poolLine: '' without basis; the whole experiment, and what does not narrow it."""
    p = r["exp"]["pool"]
    off_two = ("The candidates are the events of the whole experiment that the pickers can place; E₁, E₂ and D do "
               "not narrow them.")
    off_one = ("The candidates are the events of the whole experiment that the pickers can place; the ensemble "
               "views' p window does not narrow them.")
    assert p["fixtureOff"] == off_two
    assert p["fixtureParticle"] == (f"The candidates are the events of the whole experiment holding a matching "
                                    f"particle (p in 2.00{EN}3.00 GeV); E₁, E₂ and D do not narrow them.")
    assert p["twoActive"] == (f"The candidates are the events of the whole experiment holding a matching particle "
                              f"(p in 5.00{EN}6.00 GeV and θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)); E₁, E₂ and D do "
                              "not narrow them.")
    assert p["singleActive"] == (f"The candidates are the events of the whole experiment whose shower has θ in "
                                 f"10.0{EN}15.0° (0.175{EN}0.262 rad); the ensemble views' p window does not narrow "
                                 "them.")
    # One shower is read from the payload: the candidates' `showers`, or the drawn event's shower label.
    assert p["fixtureSingle"] == off_one and p["fixtureSingleBlock"] == off_one
    assert p["rasterTwo"] == off_two and p["voxels"] == off_two
    assert p["rasterSingle"] == off_one
    assert p["pickTwo"] == off_two and p["pickSingle"] == off_one
    assert p["explicitOne"] == off_one, "an explicit nShowers wins"
    for key in ("oldCandidates", "oldParticle", "oldRaster", "none"):
        assert p[key] == "", key


def test_the_drawn_events_lines_under_the_experiment_basis(r):
    """placeLine and matchLine are unchanged; every event of the experiment is in its basis."""
    p = r["exp"]["place"]
    assert p["raster"] == "Candidate 1 of 2, in event-number order."
    assert p["rasterSingle"] == "Candidate 3 of 287, in event-number order."
    assert p["voxels"] == p["raster"]
    assert p["membership"] == ("Not a candidate: no shower matches the particle filter; drawn as asked, and "
                               "previous / next walk the candidates.")
    assert r["exp"]["match"]["raster"] == "", "the particle filter is off in the recording"


def test_the_recorded_pick_sentences_name_the_experiment(r):
    """The server's sentences (Stage 1) that the captions carry beside these lines."""
    picks = r["exp"]["picks"]
    assert picks["basis"] == ["experiment", "experiment"]
    assert picks["two"].startswith("Drawn uniformly at random from the 2 events of the experiment with a defined "
                                   "separation: ")
    assert picks["single"].startswith("Drawn uniformly at random from the 287 events of the experiment with an "
                                      "incident direction and an entry point: ")
    for keys in picks["keys"]:
        assert {"rule_id", "seed_used", "matched", "particle"} <= set(keys)


def test_empty_lines(r):
    e = r["empty"]
    # Review S2: qualified as the server's 404 detail is, by the frame gate.
    assert e["fixture"] == (f"N = 0: no selected event with a defined separation holds a shower with p in "
                            f"5.00{EN}6.00 GeV that deposited energy. Widen the particle filter, or E₁, E₂ and D.")
    assert e["gated"] == (f"N = 0: no selected event with a defined separation holds a shower with p in "
                          f"6.00{EN}7.00 GeV that deposited energy. Widen the particle filter, or E₁, E₂ and D.")
    assert e["nonEmpty"] == ""
    assert e["off"] == "N = 0: the selection holds no event to draw. Widen E₁, E₂ or D."
    assert e["offSingle"] == "N = 0: the selection holds no event to draw. Widen p."
    assert e["single"] == (f"N = 0: no selected event with an incident direction and an entry point has its shower "
                           f"at θ in 10.0{EN}15.0° (0.175{EN}0.262 rad). Widen the particle filter, or p.")
    assert e["singleNamed"] == (f"N = 0: no selected event with an incident direction and an entry point has its "
                                f"shower at θ in 20.0{EN}25.0° (0.349{EN}0.436 rad). Widen the particle filter, or p.")


def test_unplaceable_lines(r):
    u = r["unplaceable"]
    # Review S6, brief-fix: such an event has no shower A, so it is drawn by number with shower B.
    assert u["two"] == ("57 selected events have no defined separation (shower A deposited no energy) and are never "
                        "offered; to draw one, type its number and choose shower B.")
    assert u["twoOne"] == ("1 selected event has no defined separation (shower A deposited no energy) and is never "
                           "offered; to draw it, type its number and choose shower B.")
    assert u["single"] == ("57 selected events have no incident direction or entry point, so the per-shower frames "
                           "cannot place them and they are never offered.")
    assert u["singleOne"] == ("1 selected event has no incident direction or entry point, so the per-shower frames "
                              "cannot place it and it is never offered.")
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
    assert m["replacedBig"] == "Event 20,123 left the candidates; event 4 replaces it.", \
        "grouped as every client caption writes an event number"
    assert m["ensemble"] == (f"The particle filter (p in 5.00{EN}6.00 GeV and θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)) "
                             "narrows the event pickers only; this view draws the whole selection of E₁, E₂ and D.")
    assert m["ensembleSingle"] == (f"The particle filter (θ in 10.0{EN}15.0° (0.175{EN}0.262 rad)) narrows the event "
                                   "pickers only; this view draws the whole selection of p.")
    assert m["ensembleState"] == ("The particle filter (θ ≥ 10.0° (0.175 rad)) narrows the event pickers only; this "
                                  "view draws the whole selection of E₁, E₂ and D.")
    assert m["ensembleOff"] == "" and m["ensembleEmpty"] == ""
    assert m["scope"] == ("Narrows which events the pickers offer (Pick for me, Most tilted, previous / next, and "
                          "the 3-D view's Densest), drawn from the whole experiment. E₁, E₂ and D do not narrow "
                          "them; they steer the ensemble views alone.")
    assert m["scopeSingle"] == ("Narrows which events the pickers offer (Pick for me, Most tilted, previous / next, "
                                "and the 3-D view's Densest), drawn from the whole experiment. The ensemble views' p "
                                "window does not narrow them.")
    assert m["pickTitle"] == ("A candidate event drawn uniformly at random from the whole experiment under the "
                              "particle filter: a seeded shuffle, so no event repeats until all have been drawn. "
                              "Each click takes the next draw.")
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
    assert m["open2d"] == ("Open this event in the Physics page's Event viewer: one shower in the Absolute, "
                           "per-shower translated and Local frames, with the particle filter.")


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


def test_the_2d_link_draws_one_shower_in_the_event_viewer(r):
    links = r["links"]
    assert links["twoD"] == ("/#voxel_event=7&voxel_shower=b&voxel_scope=event&particle_theta_min=10&msub=views"
                             "&event=7&shower=b&psub=event")
    assert links["twoDBoth"] == "/#voxel_event=7&voxel_shower=both&event=7&shower=b&psub=event"
    assert links["twoDBothNone"] == "/#event=7&psub=event", "no match: shower A, the built-in, left out"
    assert links["twoDA"] == "/#event=9&psub=event"
    assert links["twoDKeepsSelection"] == "/#psub=event&e1_min=2&event=9", "the link lands in the viewer"


def test_the_3d_link_keeps_page_1s_subpage(r):
    """physics-subpages §5.2: the hash keeps psub and event, so the Physics tab returns to the viewer."""
    assert r["links"]["viewer3d"] == ("/models#psub=event&event=9&shower=b&voxel_event=9&voxel_shower=b"
                                      "&voxel_scope=event")


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
    assert pure["droppedLine"] == ("Dropped from the particle filter, outside this experiment's range: p ≥ 18.50 GeV, "
                                   f"against a range of 2.70{EN}17.90 GeV.")
    assert pure["droppedTwo"] == ("Dropped from the particle filter, outside this experiment's range: p ≥ 18.50 GeV, "
                                  f"against a range of 2.70{EN}17.90 GeV; θ in 30.0{EN}40.0° (0.524{EN}0.698 rad), "
                                  f"against a range of 16.2{EN}26.5° (0.283{EN}0.463 rad).")
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
    # The pickers' pool: the experiment, basis=experiment, never the link's E₁ or D window (physics-subpages §6).
    for query in adopt["requests"]:
        assert query["basis"] == "experiment" and query["table_name"] == "experiment_baseline"
        assert not {"e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d"} & set(query)
    assert adopt["params"] == {"particle_p_max": 3}
    assert "particle_theta_max" not in adopt["hash"] and "particle_p_max=3" in adopt["hash"]
    assert adopt["lines"] == [
        r["count"]["fixtureParticle"],
        f"Dropped from the particle filter, outside this experiment's range: θ ≤ 40.0° (0.698 rad), against a range "
        f"of 16.2{EN}26.5° (0.283{EN}0.463 rad).",
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


def test_one_shower_filters_on_p_and_theta(r):
    """physics-subpages §6: the pool ignores the ensemble's p window, so p is shown and its bounds kept."""
    single = r["block"]["single"]
    assert single["pHidden"] is False
    assert single["params"] == {"particle_p_min": 3}, "p's keys are kept"
    assert single["scope"] == r["misc"]["scopeSingle"]
    assert [q["table_name"] for q in single["requests"]] == ["single_hits"]
    assert single["requests"][0]["particle_p_min"] == "3" and single["requests"][0]["basis"] == "experiment"
    assert single["count"] == r["count"]["fixtureSingle"]
    # The hints name the one shower's own columns, and two showers get the markup's text back.
    assert single["thetaHint"] == single["singleHint"]
    assert "incoming_theta)" in single["thetaHint"] and "_A" not in single["thetaHint"]
    assert single["singlePHint"] == "Incident momentum of the shower (incoming_momentum), in GeV."
    assert single["pHint"] == single["singlePHint"]
    restored = r["block"]["restoredHint"]
    assert restored["text"] == restored["markup"]
    assert restored["pText"] == restored["pMarkup"]


def test_the_block_counts_only_while_shown(r):
    """physics-subpages §6 setShown: hidden, nothing is asked and the count goes stale; shown, one count."""
    hidden = r["block"]["hiddenState"]
    assert hidden["requests"] == 0, "no refresh, adopt or commit asks while the block is hidden"
    assert hidden["refresh"] is None and hidden["adopt"] is None
    assert hidden["stale"] is True and hidden["shown"] is False
    assert hidden["count"] == "—"
    assert hidden["commits"] == 1, "a commit while hidden still tells the page"
    assert hidden["params"] == {}
    again = r["block"]["shownAgain"]
    assert len(again["requests"]) == 1 and again["requests"][0]["basis"] == "experiment"
    assert again["n"] == 2 and again["stale"] is False
    assert again["count"] == r["count"]["fixtureOff"]
    assert again["domains"] == {"p": [2.7, 17.9], "theta": [16.2, 26.5]}
    assert r["block"]["shownFresh"] == {"result": None, "requests": 0}, "a fresh count is not asked again"
    fails = r["block"]["shownFails"]
    assert fails["result"] is None and fails["reported"] == ["particle filter: Boom."]
    assert fails["count"].startswith("The candidates could not be counted")


def test_a_disabled_block_hides_and_asks_nothing(r):
    disabled = r["block"]["disabled"]
    assert disabled == {"hidden": True, "requests": 0, "adopted": None, "refresh": None, "reason": "No events."}


def test_a_failure_is_rethrown_and_an_abort_is_null(r):
    assert r["block"]["error"] == "Boom."
    assert r["block"]["abort"] is None


def test_a_failed_count_leaves_no_stale_line_or_pool(r):
    """Review U3: refresh() rethrows (the pages report it), after dropping the previous filter's count and pool."""
    failed = r["block"]["failed"]
    assert failed["count"] == r["pure"]["failedLine"].replace("Service Unavailable", "Boom.")
    assert failed["payload"] is None and failed["seen"] == [None], "the page is told there is no count"
    assert failed["reported"] == [], "a page-driven refresh is reported by the page, not twice"
    assert r["pure"]["failedLine"] == ("The candidates could not be counted (Service Unavailable); the pickers still "
                                       "draw from them.")
    assert r["pure"]["failedBare"] == "The candidates could not be counted; the pickers still draw from them."


def test_a_count_that_fails_after_the_blocks_own_commit_is_reported_and_caught(r):
    """Review U3: a slider commit and Clear: the failure goes to onError, never to an unhandled rejection."""
    got = r["block"]["commitFailure"]
    assert got["unhandled"] == []
    slider = got["afterSlider"]
    assert slider["commits"] == 1, "onCommit still runs, so the page follows the new state"
    assert slider["payload"] is None and slider["seen"] == [None]
    assert slider["reported"] == ["particle filter: Service Unavailable"]
    assert slider["count"] == r["pure"]["failedLine"]
    clear = got["afterClear"]
    assert clear["commits"] == 2 and clear["reported"] == ["particle filter: Service Unavailable"] * 2
    assert clear["count"] == r["pure"]["failedLine"]


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
