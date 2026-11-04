"""Longitudinal Channels: the view state and the shared control, under Node.

Brief §4 of the layer-groups work (``data/dev/design/layer-groups/brief.md``):

* ``state.js``: the ``lgmode`` / ``lgroups`` keys round-trip through the
  hash; an invalid value keeps the built-in one; a partition that does not
  fit the experiment's layer count L falls back to Uniform and says so,
  without rewriting the link; writing Uniform stores null; and
  ``projectionParams`` sends ``depth_groups`` only for a pooling caller in
  Pooled outside the Local frame with L known, leaving every other request
  exactly as it was.
* ``controls/layer_groups_control.js``: its pure helpers (the mini bar's
  segments, the summary, the table rows with their locks and limits, the
  seam handles' ARIA model and keys, the clamping announcements, the scales
  and the profile, the guarded storage), then the controller itself on the
  fake document of ``test_js_physics_shell.py``: the sidebar, Pooled disabled
  with its reason, the modal's drafts (zero requests, nothing written until
  Apply), Cancel restoring, Apply writing null for Uniform and Off becoming
  Boundaries, the last custom partition, and a blocked localStorage.

Depth edges are built here as the lattice stores them (production: cells at
3662.4 + 20.5 k mm, edges 3652.15 + 20.5 b; the demo lattice ends in 41 mm
cells), never derived from an index times a pitch by the code under test.
Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MINUS = "−"
UNIFORM_60 = [5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4]
UNIFORM_56 = [5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4]
EM_60 = [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8]
CUSTOM_60 = [3, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7]


def _dots(counts):
    return ".".join(str(n) for n in counts)


# ------------------------------------------------------------------ state.js --

_STATE_SCRIPT = r"""
const [stateUrl] = JSON.parse(process.argv[1]);
globalThis.window = {
  location: { hash: '', pathname: '/' },
  history: { replaceState(_s, _t, url) { const at = url.indexOf('#'); window.location.hash = at >= 0 ? url.slice(at) : ''; } },
};
const { State, DEFAULTS, LG_MODES } = await import(stateUrl);
const fresh = (hash) => { window.location.hash = hash; return new State(); };
const out = { defaults: { lgmode: DEFAULTS.lgmode, lgroups: DEFAULTS.lgroups }, modes: LG_MODES };

// Round trip.
const em = '2.2.3.3.3.4.4.5.5.6.7.8.8';
let s = fresh(`#lgmode=bounds&lgroups=${em}`);
out.read = { lgmode: s.get('lgmode'), lgroups: s.get('lgroups'), coldBoot: s.coldBoot };
s.writeHash();
out.written = window.location.hash;
const again = fresh(window.location.hash);
out.reread = { lgmode: again.get('lgmode'), lgroups: again.get('lgroups') };
out.cold = { coldBoot: fresh('').coldBoot, hash: fresh('').hashString() };
out.leadingZeros = fresh('#lgroups=02.2.3.3.3.4.4.5.5.6.7.8.08').get('lgroups');

// Invalid values keep the built-in ones.
out.invalid = {};
for (const hash of ['#lgmode=pooled', '#lgmode=', '#lgmode=POOL',
                    '#lgroups=5.5.5', '#lgroups=0.5.5.5.5.5.5.5.5.5.5.5.5', '#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.',
                    '#lgroups=a.5.5.5.5.5.5.5.5.4.4.4.4', '#lgroups=-5.5.5.5.5.5.5.5.4.4.4.4.4',
                    '#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.1', '#lgroups=5,5,5,5,5,5,5,5,4,4,4,4,4',
                    '#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.5']) {
  const t = fresh(hash);
  out.invalid[hash] = { lgmode: t.get('lgmode'), lgroups: t.get('lgroups'), coldBoot: t.coldBoot };
}

// Fallback for a partition that does not fit L, which stays stored.
s = fresh(`#lgmode=bounds&lgroups=${em}`);
out.unknownL = s.layerGroups();
s.setLayerCount(56);
out.wrongL = { ...s.layerGroups(), stored: s.get('lgroups') };
s.setLayerCount(60);
out.rightL = s.layerGroups();
s.setLayerCount(12);
out.tooFew = s.layerGroups();
s = fresh('');
s.setLayerCount(60);
out.nullUniform = s.layerGroups();
s.setLayerCount(56);
out.nullUniform56 = s.layerGroups();

// projectionParams: depth_groups only for a pooling caller in Pooled outside Local with L known.
const custom = '3.3.3.3.4.4.4.5.5.6.6.7.7';
s = fresh('#table_name=t');
const before = {};
for (const frame of ['lab', 'trans', 'local', 'canonical']) before[frame] = s.projectionParams(false, frame);
out.baseline = before;
out.params = {};
const record = (label) => {
  out.params[label] = {};
  for (const frame of ['lab', 'trans', 'local', 'canonical']) {
    const plain = s.projectionParams(false, frame);
    const pooled = s.projectionParams(true, frame, { layerPool: true });
    out.params[label][frame] = { plain, pooled, defaultFrame: s.projectionParams(false, undefined, { layerPool: true }) };
  }
};
record('offNoL');
s.set({ lgmode: 'pool' });
record('poolNoL');
s.setLayerCount(60);
record('poolUniform');
s.set({ lgroups: custom });
record('poolCustom');
s.set({ lgmode: 'bounds' });
record('boundsCustom');
s.set({ lgmode: 'pool', frame: 'local' });
out.localDefault = s.projectionParams(false, undefined, { layerPool: true });
s.set({ frame: 'lab' });
s.setLayerCount(56);
out.poolFallback = s.projectionParams(false, 'lab', { layerPool: true }).depth_groups;

// Storing Uniform gives null; a custom partition is stored as its string.
s = fresh('');
s.setLayerCount(60);
out.store = {};
s.set({ lgroups: [5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4] });
out.store.uniformArray = s.get('lgroups');
s.set({ lgroups: '5.5.5.5.5.5.5.5.4.4.4.4.4' });
out.store.uniformString = s.get('lgroups');
s.set({ lgroups: [3, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7] });
out.store.customArray = s.get('lgroups');
out.store.customHash = window.location.hash;
s.set({ lgroups: [5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4] });
out.store.backToUniformHash = window.location.hash;
s.set({ lgroups: [0, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 5] });
out.store.invalidArray = s.get('lgroups');
s.set({ lgroups: 'nonsense' });
out.store.invalidString = s.get('lgroups');
const u = fresh('');
u.set({ lgroups: '5.5.5.5.5.5.5.5.4.4.4.4.4' });
out.store.uniformUnknownL = u.get('lgroups');
u.setLayerCount(56);
out.store.uniformAt56 = u.layerGroups();

// No saved default may set them.
s = fresh('');
s.applyDefaults({ lgmode: 'pool', lgroups: custom, frame: 'trans' });
out.adminDefaults = { lgmode: s.get('lgmode'), lgroups: s.get('lgroups'), frame: s.get('frame') };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def state_out() -> dict:
    return _run(_STATE_SCRIPT, [(JS / "state.js").as_uri()])


def test_the_built_in_view_has_the_channels_off_and_uniform(state_out):
    assert state_out["defaults"] == {"lgmode": "off", "lgroups": None}
    assert state_out["modes"] == ["off", "bounds", "pool"]
    assert state_out["cold"] == {"coldBoot": True, "hash": ""}


def test_lgmode_and_lgroups_round_trip_through_the_hash(state_out):
    em = _dots(EM_60)
    assert state_out["read"] == {"lgmode": "bounds", "lgroups": em, "coldBoot": False}
    assert state_out["written"] == f"#lgmode=bounds&lgroups={em}"
    assert state_out["reread"] == {"lgmode": "bounds", "lgroups": em}


def test_a_partition_has_one_spelling(state_out):
    assert state_out["leadingZeros"] == _dots(EM_60)


@pytest.mark.parametrize("fragment", [
    "#lgmode=pooled", "#lgmode=", "#lgmode=POOL",
    "#lgroups=5.5.5", "#lgroups=0.5.5.5.5.5.5.5.5.5.5.5.5", "#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.",
    "#lgroups=a.5.5.5.5.5.5.5.5.4.4.4.4", "#lgroups=-5.5.5.5.5.5.5.5.4.4.4.4.4",
    "#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.1", "#lgroups=5,5,5,5,5,5,5,5,4,4,4,4,4",
    "#lgroups=5.5.5.5.5.5.5.5.4.4.4.4.4.5",
])
def test_an_invalid_value_keeps_the_built_in_one(state_out, fragment):
    got = state_out["invalid"][fragment]
    assert got["lgmode"] == "off" and got["lgroups"] is None
    # A recognised key is still a view link, as for every other key.
    assert got["coldBoot"] is False


def test_a_partition_is_unchecked_until_the_layer_count_is_known(state_out):
    assert state_out["unknownL"] == {"mode": "bounds", "counts": EM_60, "fallback": False, "L": None}


def test_a_partition_that_does_not_fit_falls_back_to_uniform_and_stays_stored(state_out):
    assert state_out["wrongL"] == {"mode": "bounds", "counts": UNIFORM_56, "fallback": True, "L": 56,
                                   "stored": _dots(EM_60)}
    assert state_out["rightL"] == {"mode": "bounds", "counts": EM_60, "fallback": False, "L": 60}
    # Fewer than 13 layers: no partition is possible, so L is unknown.
    assert state_out["tooFew"]["L"] is None and state_out["tooFew"]["fallback"] is False


def test_null_resolves_to_uniform_for_each_lattice(state_out):
    assert state_out["nullUniform"] == {"mode": "off", "counts": UNIFORM_60, "fallback": False, "L": 60}
    assert state_out["nullUniform56"] == {"mode": "off", "counts": UNIFORM_56, "fallback": False, "L": 56}


def test_no_request_carries_depth_groups_unless_a_pooling_caller_is_in_pooled(state_out):
    params = state_out["params"]
    for label in ("offNoL", "poolNoL", "boundsCustom"):
        for frame, got in params[label].items():
            assert "depth_groups" not in got["plain"], (label, frame)
            assert "depth_groups" not in got["pooled"], (label, frame)
            assert "depth_groups" not in got["defaultFrame"], (label, frame)
    for label in ("poolUniform", "poolCustom"):
        for frame, got in params[label].items():
            assert "depth_groups" not in got["plain"], (label, frame)


def test_existing_requests_are_unchanged(state_out):
    """Every key and value of a request without pooling is today's."""
    for label in ("offNoL", "poolNoL", "poolUniform", "poolCustom", "boundsCustom"):
        for frame, got in state_out["params"][label].items():
            assert got["plain"] == state_out["baseline"][frame], (label, frame)
            pooled = {k: v for k, v in got["pooled"].items() if k not in ("depth_groups", "preview")}
            plain = {k: v for k, v in got["plain"].items() if k != "preview"}
            assert pooled == plain, (label, frame)


def test_pooled_sends_the_partition_outside_local(state_out):
    for label, counts in (("poolUniform", UNIFORM_60), ("poolCustom", CUSTOM_60)):
        for frame in ("lab", "trans", "canonical"):
            assert state_out["params"][label][frame]["pooled"]["depth_groups"] == _dots(counts), (label, frame)
        assert "depth_groups" not in state_out["params"][label]["local"]["pooled"], label
    assert state_out["params"]["poolCustom"]["lab"]["defaultFrame"]["depth_groups"] == _dots(CUSTOM_60)
    assert "depth_groups" not in state_out["localDefault"]
    # A partition that no longer fits L is sent as the Uniform the panels draw.
    assert state_out["poolFallback"] == _dots(UNIFORM_56)


def test_writing_uniform_stores_null(state_out):
    store = state_out["store"]
    assert store["uniformArray"] is None and store["uniformString"] is None
    assert store["customArray"] == _dots(CUSTOM_60)
    assert store["customHash"] == f"#lgroups={_dots(CUSTOM_60)}"
    assert store["backToUniformHash"] == ""
    assert store["invalidArray"] is None and store["invalidString"] is None
    # With L unknown the string is kept; it still resolves as Uniform once L is.
    assert store["uniformUnknownL"] == _dots(UNIFORM_60)
    assert store["uniformAt56"]["fallback"] is True


def test_no_saved_default_sets_the_channels(state_out):
    assert state_out["adminDefaults"] == {"lgmode": "off", "lgroups": None, "frame": "trans"}


# ------------------------------------------------------ the control's helpers --

_HELPERS_SCRIPT = r"""
const [controlUrl] = JSON.parse(process.argv[1]);
globalThis.window = { location: { hash: '', pathname: '/' }, history: { replaceState() {} } };
const c = await import(controlUrl);
const out = {};
const uniform = [5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4];
const em = [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8];
const custom = [3, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7];
// Stored lattice edges: production lab (raw z), trans (Δz), and a gapped demo lattice.
const labEdges = Array.from({ length: 61 }, (_, b) => 3652.15 + 20.5 * b);
const transEdges = Array.from({ length: 61 }, (_, b) => (b - 0.5) * 20.5);
const demoEdges = Array.from({ length: 57 }, (_, b) => 3652.15 + 20.5 * Math.min(b, 52) + 41 * Math.max(0, b - 52));
const lab = { numbering: 'detector', edgesMm: labEdges, displayOffsetMm: 3649, symbol: 'z',
  profile: { energy_gev: Array.from({ length: 60 }, (_, k) => (k === 7 ? 4 : k < 30 ? 1 : 0)), exact: true } };
const trans = { numbering: 'relative', edgesMm: transEdges, displayOffsetMm: null, symbol: 'Δz', profile: null };
const demo = { numbering: 'detector', edgesMm: demoEdges, displayOffsetMm: 3649, symbol: 'z', contiguous: false, profile: null };

out.reasons = c.POOL_REASONS;
out.storageKey = c.LG_STORAGE_KEY;
out.pool = {
  physicsLab: c.poolAvailability({ page: 'physics', frame: 'lab' }),
  physicsLocal: c.poolAvailability({ page: 'physics', frame: 'local' }),
  models: c.poolAvailability({ page: 'models', frame: 'lab' }),
};
out.effective = {
  physicsPool: c.effectiveMode('pool', { page: 'physics', frame: 'trans' }),
  localPool: c.effectiveMode('pool', { page: 'physics', frame: 'local' }),
  modelsPool: c.effectiveMode('pool', { page: 'models', frame: 'lab' }),
  modelsBounds: c.effectiveMode('bounds', { page: 'models', frame: 'lab' }),
  junk: c.effectiveMode('nope', { page: 'physics', frame: 'lab' }),
};
out.numbering = ['lab', 'canonical', 'trans', 'local'].map((f) => c.numberingOf(null, f));
out.bar = c.barSegments(uniform);
out.barRel = c.barSegments(custom, { numbering: 'relative' }).map((s) => s.title);
out.summary = {
  uniform: c.summaryText(uniform, 60), em: c.summaryText(em, 60), custom: c.summaryText(custom, 60),
  log: c.summaryText([1, 1, 2, 2, 2, 3, 4, 4, 5, 6, 8, 10, 12], 60), wrong: c.summaryText(uniform, 56),
};
out.match = { uniform: c.matchPreset(uniform, 60), custom: c.matchPreset(custom, 60), wrongL: c.matchPreset(uniform, 56) };
out.rowsLab = c.tableRows(uniform, 60, lab);
out.rowsNone = c.tableRows(uniform, 60, null);
out.rowsDemo = c.tableRows([5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4], 56, demo);
out.seamLab = [1, 6, 12].map((seam) => c.seamModel(uniform, seam, lab));
out.seamTrans = c.seamModel(uniform, 1, trans);
out.seamBare = c.seamModel(uniform, 1, null);
const model = c.seamModel(uniform, 2, lab);
out.keys = Object.fromEntries(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown', 'Tab', 'a']
  .map((key) => [key, c.seamKeyTarget(model, key)]));
out.snap = [c.snapSeam(0, 60), c.snapSeam(0.1, 60), c.snapSeam(0.1041, 60), c.snapSeam(-1, 60), c.snapSeam(2, 60), c.snapSeam(NaN, 60)];
out.announce = {
  clampedEnd: c.editAnnouncement({ counts: [5, 9, 1, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4], clamped: true }, { seam: 2, requested: 30, field: 'end' }),
  clampedStart: c.editAnnouncement({ counts: [1, 9, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4], clamped: true }, { seam: 1, requested: 1, field: 'start', numbering: 'relative' }),
  plain: c.editAnnouncement({ counts: [6, 4, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4], clamped: false }, { seam: 1, requested: 6 }),
  single: c.editAnnouncement({ counts: [1, 9, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4], clamped: false }, { seam: 1, requested: 1 }),
};
out.profile = c.profileHeights(lab.profile, 60);
out.profileNone = [c.profileHeights(null, 60), c.profileHeights({ energy_gev: new Array(60).fill(0) }, 60)];
out.profileShift = c.profileHeights({ energy_gev: [2, 1] }, 13, 2);
out.layerTicks = { l60: c.layerTicks(60), l56: c.layerTicks(56), rel: c.layerTicks(20, { numbering: 'relative' }) };
out.depthTicks = { lab: c.depthTicks(lab, 60), trans: c.depthTicks(trans, 60), none: c.depthTicks(null, 60) };
out.depthNote = { lab: c.depthNote(lab, 60), trans: c.depthNote(trans, 60, { frame: 'trans' }),
  demo: c.depthNote(demo, 56), local: c.depthNote({ numbering: 'none' }, 60, { frame: 'local' }),
  preview: c.depthNote({ ...lab, profile: { ...lab.profile, exact: false } }, 60) };
out.mm = [c.formatMm(-10.25), c.formatMm(3.15), c.formatMm(-0.001), c.formatMm(102.50000001), c.formatMm(NaN)];
out.patch = { uniformOff: c.applyPatch(uniform, 60, 'off'), customBounds: c.applyPatch(custom, 60, 'bounds'),
  emPool: c.applyPatch(em, 60, 'pool') };
out.notices = {
  fallback: c.sidebarNotices({ mode: 'bounds', fallback: true, L: 56 }, '2.2.3.3.3.4.4.5.5.6.7.8.8', { page: 'physics', frame: 'lab' }),
  localPool: c.sidebarNotices({ mode: 'pool', fallback: false, L: 60 }, null, { page: 'physics', frame: 'local' }),
  modelsBounds: c.sidebarNotices({ mode: 'bounds', fallback: false, L: 60 }, null, { page: 'models', frame: 'lab' }),
  none: c.sidebarNotices({ mode: 'pool', fallback: false, L: 60 }, null, { page: 'physics', frame: 'canonical' }),
};

// Storage: per-L map, guarded against every failure.
const map = new Map();
const good = { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)) };
const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
out.storage = {
  emptyRead: c.readLastCustom(good, 60),
  wrote60: c.writeLastCustom(good, custom, 60),
  wrote56: c.writeLastCustom(good, [5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4], 56),
  refusesInvalid: c.writeLastCustom(good, custom, 56),
  read60: c.readLastCustom(good, 60),
  read56: c.readLastCustom(good, 56),
  read50: c.readLastCustom(good, 50),
  raw: map.get(c.LG_STORAGE_KEY),
  throwingRead: c.readLastCustom(throwing, 60),
  throwingWrite: c.writeLastCustom(throwing, custom, 60),
  nullRead: c.readLastCustom(null, 60),
  nullWrite: c.writeLastCustom(null, custom, 60),
};
map.set(c.LG_STORAGE_KEY, '{not json');
out.storage.corrupt = c.readLastCustom(good, 60);
out.storage.overwriteCorrupt = c.writeLastCustom(good, custom, 60);
out.storage.afterCorrupt = c.readLastCustom(good, 60);
map.set(c.LG_STORAGE_KEY, JSON.stringify({ 60: '5.5.5' }));
out.storage.badEntry = c.readLastCustom(good, 60);
out.fromPayload = {
  lab: c.depthContextFromPayload({ numbering: 'detector', n_layers: 60, partition_layers: 60, pitch_mm: 20.5,
    edges_mm: labEdges, first_layer: 1, contiguous: true, display_offset_mm: 3649, symbol: 'z',
    profile: { numbering: 'detector', energy_gev: [1, 2], exact: false } }),
  local: c.depthContextFromPayload({ numbering: 'none', n_layers: 0, edges_mm: null, display_offset_mm: null, symbol: 'w', profile: null }),
  eventLab: c.depthContextFromPayload({ numbering: 'detector', normal: [0, 0, 1], edges_mm: labEdges, first_layer: 1,
    energy_gev: [3, 4], display_offset_mm: 3649 }),
  eventTrans: c.depthContextFromPayload({ numbering: 'relative', normal: [0, 0, 1], edges_mm: transEdges, first_layer: 1,
    energy_gev: [3], display_offset_mm: null }),
  eventLocal: c.depthContextFromPayload({ numbering: 'relative', normal: [-0.17, 0, 0.98], edges_mm: transEdges,
    energy_gev: [3], display_offset_mm: null }),
  none: [c.depthContextFromPayload(null), c.depthContextFromPayload({})],
};
Object.defineProperty(globalThis, 'localStorage', { get() { throw new Error('SecurityError'); }, configurable: true });
out.storage.viewerBlocked = c.viewerStorage();
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def helpers() -> dict:
    return _run(_HELPERS_SCRIPT, [(JS / "controls" / "layer_groups_control.js").as_uri()])


def test_pooled_is_withheld_on_the_models_page_and_in_local_with_its_reason(helpers):
    assert helpers["pool"]["physicsLab"] == {"enabled": True, "reason": None}
    assert helpers["pool"]["physicsLocal"] == {"enabled": False, "reason": helpers["reasons"]["local"]}
    assert helpers["pool"]["models"] == {"enabled": False, "reason": helpers["reasons"]["models"]}
    assert "draws boundaries" in helpers["reasons"]["models"]
    assert "no common layer grid" in helpers["reasons"]["local"]
    assert helpers["effective"] == {"physicsPool": "pool", "localPool": "bounds", "modelsPool": "bounds",
                                    "modelsBounds": "bounds", "junk": "off"}
    assert helpers["storageKey"] == "calosrv.layerGroups.custom"


def test_each_frame_numbers_its_layers_as_the_brief_says(helpers):
    assert helpers["numbering"] == ["detector", "detector", "relative", "none"]


def test_the_mini_bar_has_13_segments_weighted_by_their_layers(helpers):
    bar = helpers["bar"]
    assert len(bar) == 13
    assert [s["grow"] for s in bar] == UNIFORM_60
    assert [s["alt"] for s in bar] == [m % 2 == 0 for m in range(1, 14)]
    assert bar[0]["title"] == "Ch 1 · layers 1–5"
    assert bar[12]["title"] == "Ch 13 · layers 57–60"
    assert helpers["barRel"][0] == "Rel Ch 1 · layers 1–3"


def test_the_summary_names_the_preset_or_custom(helpers):
    assert helpers["summary"] == {
        "uniform": "13 channels over 60 layers · Uniform",
        "em": "13 channels over 60 layers · EM-Fine / Hadron-Coarse",
        "custom": "13 channels over 60 layers · custom",
        "log": "13 channels over 60 layers · Logarithmic Depth",
        "wrong": "—",
    }
    assert helpers["match"] == {"uniform": "uniform", "custom": None, "wrongL": None}


def test_the_table_locks_the_ends_and_bounds_each_field(helpers):
    rows = helpers["rowsLab"]
    assert len(rows) == 13
    assert rows[0]["startLocked"] and not rows[0]["endLocked"]
    assert rows[12]["endLocked"] and not rows[12]["startLocked"]
    assert all(not r["startLocked"] and not r["endLocked"] for r in rows[1:12])
    assert [(r["first"], r["last"], r["n"]) for r in rows[:2]] == [(1, 5, 5), (6, 10, 5)]
    # Ch 2's start may run from layer 2 (Ch 1 keeps one) to its own last layer.
    assert (rows[1]["startMin"], rows[1]["startMax"]) == (2, 10)
    # Ch 1's end may run from layer 1 to layer 9 (Ch 2 keeps one).
    assert (rows[0]["endMin"], rows[0]["endMax"]) == (1, 9)
    assert (rows[12]["endMin"], rows[12]["endMax"]) == (60, 60)
    assert (rows[0]["startMin"], rows[0]["startMax"]) == (1, 1)
    assert rows[1]["label"] == "Ch 2"


def test_thickness_comes_from_the_stored_edges(helpers):
    lab = helpers["rowsLab"]
    assert lab[0]["thicknessMm"] == pytest.approx(102.5)
    assert lab[0]["thicknessText"] == "102.5 mm"
    assert lab[12]["thicknessMm"] == pytest.approx(82.0)
    assert all(r["thicknessMm"] is None and r["thicknessText"] == "—" for r in helpers["rowsNone"])
    # The demo lattice's last four layers are 41 mm cells: Ch 13 (layers 53-56) is 164 mm.
    demo = helpers["rowsDemo"]
    assert demo[12]["first"] == 53 and demo[12]["thicknessMm"] == pytest.approx(164.0)
    assert demo[0]["thicknessMm"] == pytest.approx(102.5)


def test_a_seam_handle_carries_its_aria_model(helpers):
    first, sixth, last = helpers["seamLab"]
    assert (first["value"], first["min"], first["max"]) == (5, 1, 9)
    assert (sixth["value"], sixth["min"], sixth["max"]) == (30, 26, 34)
    assert (last["value"], last["min"], last["max"]) == (56, 53, 59)
    assert first["label"] == "Seam between Ch 1 and Ch 2"
    # Z = 3652.15 + 20.5·5 − 3649 = 105.65 mm, the stored edge less the display offset.
    assert first["valueText"] == "Ch 1 ends at layer 5, Ch 2 starts at layer 6 · seam at Z = 105.65 mm"
    assert helpers["seamTrans"]["valueText"].endswith("seam at Δz = 92.25 mm")
    assert helpers["seamTrans"]["label"] == "Seam between Rel Ch 1 and Rel Ch 2"
    assert helpers["seamBare"]["valueText"] == "Ch 1 ends at layer 5, Ch 2 starts at layer 6"


def test_the_keys_move_a_seam_as_a_slider_does(helpers):
    # Seam 2 sits after layer 10, between layers 6 and 14.
    assert helpers["keys"] == {"ArrowLeft": 9, "ArrowRight": 11, "ArrowUp": 11, "ArrowDown": 9,
                               "Home": 6, "End": 14, "PageUp": 15, "PageDown": 5, "Tab": None, "a": None}


def test_a_pointer_snaps_to_the_nearest_whole_seam(helpers):
    assert helpers["snap"] == [0, 6, 6, 0, 60, None]


def test_clamping_is_announced_with_its_reason(helpers):
    a = helpers["announce"]
    assert a["clampedEnd"] == "Ch 2 ends at layer 14: layer 30 was asked for, but every channel keeps at least one layer."
    assert a["clampedStart"] == "Rel Ch 2 starts at layer 2: layer 1 was asked for, but every channel keeps at least one layer."
    assert a["plain"] == "Ch 1: layers 1–6; Ch 2: layers 7–10."
    assert a["single"] == "Ch 1: layer 1; Ch 2: layers 2–10."


def test_the_profile_is_relative_to_its_peak_layer(helpers):
    profile = helpers["profile"]
    assert len(profile) == 60 and max(profile) == 1 and profile[7] == 1 and profile[0] == 0.25 and profile[40] == 0
    assert helpers["profileNone"] == [None, None]
    # A payload whose first native bin is layer 2 is read from its own offset.
    assert helpers["profileShift"][:3] == [0, 1, 0.5]


def test_the_scales_read_layers_above_and_stored_depths_below(helpers):
    l60 = helpers["layerTicks"]["l60"]
    assert [t["layer"] for t in l60] == [1, 10, 20, 30, 40, 50, 60]
    assert l60[0]["text"] == "layer 1" and l60[0]["at"] == pytest.approx(0.5 / 60)
    assert [t["layer"] for t in helpers["layerTicks"]["l56"]] == [1, 10, 20, 30, 40, 50, 56]
    assert helpers["layerTicks"]["rel"][0]["text"] == "rel. layer 1"
    lab = helpers["depthTicks"]["lab"]
    assert lab[0]["text"] == "Z = 3.15 mm" and lab[0]["at"] == 0
    assert [t["text"] for t in lab[1:]] == ["208.15", "413.15", "618.15", "823.15", "1028.15", "1233.15"]
    trans = helpers["depthTicks"]["trans"]
    assert trans[0]["text"] == f"Δz = {MINUS}10.25 mm"
    assert helpers["depthTicks"]["none"] == []
    for t in lab + trans:
        assert "-" not in t["text"]


def test_the_depth_note_states_the_numbering_and_the_offset(helpers):
    note = helpers["depthNote"]
    assert note["lab"].startswith("Detector layers 1–60")
    assert f"Z = z {MINUS} 3649 mm" in note["lab"]
    assert "relative to its peak layer." in note["lab"]
    assert "preview sample" in note["preview"]
    assert note["trans"].startswith("Relative layers 1–60") and "Δz" in note["trans"]
    assert "skips unpopulated layers" in note["demo"]
    assert note["local"].startswith("Local:") and "no common layer grid" in note["local"]
    for text in note.values():
        assert " - " not in text


def test_millimetres_are_printed_with_a_true_minus(helpers):
    assert helpers["mm"] == [f"{MINUS}10.25", "3.15", "0", "102.5", "—"]


def test_apply_writes_null_for_uniform_and_turns_off_into_boundaries(helpers):
    assert helpers["patch"] == {
        "uniformOff": {"lgroups": None, "lgmode": "bounds"},
        "customBounds": {"lgroups": _dots(CUSTOM_60)},
        "emPool": {"lgroups": _dots(EM_60)},
    }


def test_the_sidebar_notices_name_the_fallback_and_the_pooling_reason(helpers):
    n = helpers["notices"]
    assert n["fallback"] == ["This link’s channels (2.2.3.3.3.4.4.5.5.6.7.8.8) do not fit this experiment’s "
                             "56 layers: Uniform is drawn."]
    assert n["localPool"] == [helpers["reasons"]["local"] + " Boundaries are drawn instead."]
    assert n["modelsBounds"] == [helpers["reasons"]["models"]]
    assert n["none"] == []


def test_the_last_custom_partition_is_kept_per_layer_count_and_every_access_is_guarded(helpers):
    s = helpers["storage"]
    assert s["emptyRead"] is None
    assert s["wrote60"] is True and s["wrote56"] is True and s["refusesInvalid"] is False
    assert s["read60"] == CUSTOM_60 and s["read56"] == UNIFORM_56 and s["read50"] is None
    assert s["throwingRead"] is None and s["throwingWrite"] is False
    assert s["nullRead"] is None and s["nullWrite"] is False
    assert s["corrupt"] is None and s["overwriteCorrupt"] is True and s["afterCorrupt"] == CUSTOM_60
    assert s["badEntry"] is None
    assert s["viewerBlocked"] is None


def test_the_depth_context_is_read_from_either_payload_block(helpers):
    p = helpers["fromPayload"]
    lab = p["lab"]
    assert (lab["numbering"], lab["displayOffsetMm"], lab["symbol"], lab["firstLayer"], lab["contiguous"]) == (
        "detector", 3649, "z", 1, True)
    assert len(lab["edgesMm"]) == 61 and lab["profile"]["exact"] is False
    assert p["local"]["numbering"] == "none" and p["local"]["edgesMm"] is None and p["local"]["symbol"] == "w"
    assert p["eventLab"]["symbol"] == "z" and p["eventLab"]["profile"] == {"energy_gev": [3, 4], "exact": True}
    assert p["eventTrans"]["symbol"] == "Δz"
    assert p["eventLocal"]["symbol"] is None, "a tilted normal has no depth scale on the ribbon"
    assert p["none"] == [None, None]


# ------------------------------------------------------ the controller, faked --

_CONTROL_SCRIPT = _FAKE_DOM + r"""
const [stateUrl, controlUrl] = JSON.parse(process.argv[1]);
// What the control reads beyond the shared fake: attribute selectors, querySelector(All),
// focus, geometry, pointer capture, and document listeners (ModalShell's Escape).
const proto = FakeElement.prototype;
const baseMatches = proto.matches;
proto.matches = function matches(selector) {
  const attr = /^\[data-([a-z-]+)\]$/.exec(selector);
  if (attr) return attr[1] in this.dataset;
  return baseMatches.call(this, selector);
};
proto.querySelector = function querySelector(sel) { return this.find((el) => el !== this && el.matches(sel)); };
proto.querySelectorAll = function querySelectorAll(sel) {
  if (sel.includes(',')) return [];
  return this.findAll((el) => el !== this && el.matches(sel));
};
proto.focus = function focus() { document.activeElement = this; };
proto.getBoundingClientRect = function rect() { return { left: 100, top: 0, width: 600, height: 64 }; };
proto.setPointerCapture = function capture() {};
const docListeners = {};
document.addEventListener = (type, fn) => { (docListeners[type] ??= []).push(fn); };
const fire = (el, type, props = {}) => {
  let prevented = false;
  const event = { target: el, key: undefined, button: 0, pointerId: 1, clientX: 0,
    preventDefault() { prevented = true; }, stopPropagation() {}, ...props };
  for (const fn of el.listeners[type] ?? []) fn(event);
  return prevented;
};
const keyDoc = (key) => { for (const fn of docListeners.keydown ?? []) fn({ key, shiftKey: false, preventDefault() {} }); };
const store = new Map();
let storageBlocked = false;
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  get() {
    if (storageBlocked) throw new Error('SecurityError');
    return { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
  },
});

// The §5 markup, as the two pages carry it.
const ids = ['group-lgroups', 'info-lgroups', 'lgmode-off', 'lgmode-bounds', 'lgmode-pool', 'lgmode-off-label',
  'lgmode-bounds-label', 'lgmode-pool-label', 'lgroups-bar', 'lgroups-edit', 'lgroups-summary', 'lgroups-notice',
  'lgroups-modal', 'lgroups-title', 'lgroups-depth-note', 'lgroups-ribbon-top', 'lgroups-ribbon', 'lgroups-ribbon-bottom',
  'lgroups-presets', 'lgroups-preset-custom', 'lgroups-shorthand', 'lgroups-shorthand-apply', 'lgroups-shorthand-error',
  'lgroups-rows', 'lgroups-live', 'lgroups-reset', 'lgroups-cancel', 'lgroups-apply'];
const build = () => {
  registry.clear();
  for (const id of ids) byId(id);
  byId('group-lgroups').hidden = true;
  byId('info-lgroups').hidden = true;
  for (const [mode, id] of [['off', 'lgmode-off'], ['bounds', 'lgmode-bounds'], ['pool', 'lgmode-pool']]) {
    const input = byId(id); input.value = mode; input.checked = mode === 'off';
    byId(`${id}-label`).className = 'choice';
    byId(`${id}-label`).append(input);
  }
  const backdrop = byId('lgroups-modal');
  backdrop.className = 'modal-backdrop'; backdrop.hidden = true;
  const dialog = new FakeElement('div'); dialog.className = 'modal lg-modal';
  backdrop.append(dialog);
  const presets = byId('lgroups-presets');
  for (const key of ['uniform', 'em_hadron', 'log']) {
    const button = new FakeElement('button'); button.dataset.preset = key; presets.append(button);
  }
  const custom = byId('lgroups-preset-custom'); custom.dataset.preset = 'custom'; custom.hidden = true; presets.append(custom);
  byId('lgroups-shorthand-error').hidden = true;
  byId('lgroups-notice').hidden = true;
};

const { State } = await import(stateUrl);
const { mountLayerGroupControl } = await import(controlUrl);
const fresh = (hash) => { window.location.hash = hash; return new State(); };
const out = {};
const sidebar = () => ({
  hidden: byId('group-lgroups').hidden,
  reason: byId('group-lgroups').dataset.reason ?? null,
  checked: ['off', 'bounds', 'pool'].filter((m) => byId(`lgmode-${m}`).checked),
  poolDisabled: byId('lgmode-pool').disabled,
  poolTitle: byId('lgmode-pool-label').title,
  poolClass: byId('lgmode-pool-label').className,
  notice: byId('lgroups-notice').hidden ? null : byId('lgroups-notice').textContent,
  info: byId('info-lgroups').hidden ? null : JSON.parse(byId('info-lgroups').dataset.notices),
  segments: byId('lgroups-bar').children.map((s) => [s.className, s.style.flexGrow, s.title]),
  barLabel: byId('lgroups-bar').getAttribute('aria-label'),
  summary: byId('lgroups-summary').textContent,
  editDisabled: byId('lgroups-edit').disabled,
});
const ribbon = () => byId('lgroups-ribbon');
const handles = () => ribbon().children.filter((c) => c.className.includes('lg-handle'));
const cells = () => ribbon().children.filter((c) => c.className.startsWith('lg-cell'));
const rows = () => byId('lgroups-rows').children;
const field = (group, kind) => rows()[group - 1].children[kind === 'start' ? 1 : 2].children[0];

// --- the sidebar on the Physics page
build();
let drafts = [];
let s = fresh('#table_name=t');
let control = mountLayerGroupControl({ state: s, page: 'physics', doc: document, onDraft: (c) => drafts.push(c) });
out.beforeExperiment = sidebar();
control.setExperiment({ nLayers: 60 });
out.adopted = sidebar();
out.stateL = s.layerGroups();
const bounds = byId('lgmode-bounds');
bounds.checked = true; fire(bounds, 'change');
out.afterRadio = { lgmode: s.get('lgmode'), hash: window.location.hash, side: sidebar().checked };
s.set({ lgmode: 'pool' });
control.setFrame('local');
out.local = sidebar();
out.localMode = s.get('lgmode');
control.setFrame('lab');
out.labAgain = sidebar();

// --- the modal: drafts cost nothing until Apply
s.set({ lgmode: 'off' });
control.setDepthContext({ numbering: 'detector', edgesMm: Array.from({ length: 61 }, (_, b) => 3652.15 + 20.5 * b),
  displayOffsetMm: 3649, symbol: 'z', profile: { energy_gev: new Array(60).fill(1), exact: true } });
fire(byId('lgroups-edit'), 'click');
out.opened = {
  modalHidden: byId('lgroups-modal').hidden,
  cells: cells().length,
  cellAlt: cells().slice(0, 7).map((c) => c.className),
  cellTitle: cells()[5].title,
  handles: handles().length,
  aria: { ...handles()[0].attrs },
  left: handles().map((h) => h.style.left),
  tabIndex: handles()[0].tabIndex,
  focused: document.activeElement === handles()[0],
  rows: rows().length,
  row1: rows()[0].children.map((td) => [td.className, td.textContent]),
  locks: [field(1, 'start').disabled, field(13, 'end').disabled, field(2, 'start').disabled, field(12, 'end').disabled],
  field2: [field(2, 'start').value, field(2, 'start').min, field(2, 'start').max],
  thickness: rows()[0].children[4].textContent,
  top: byId('lgroups-ribbon-top').children.map((t) => [t.textContent, t.style.left]),
  bottom: byId('lgroups-ribbon-bottom').children.map((t) => t.textContent),
  note: byId('lgroups-depth-note').textContent,
  shorthand: byId('lgroups-shorthand').value,
  pressed: byId('lgroups-presets').children.map((b) => b.getAttribute('aria-pressed')),
  canvas: ribbon().children[0].className,
};
const hash0 = window.location.hash;
out.keyRight = fire(handles()[0], 'keydown', { key: 'ArrowRight' });
out.afterKey = { draft: drafts.at(-1), now: handles()[0].attrs['aria-valuenow'], text: handles()[0].attrs['aria-valuetext'],
  state: s.get('lgroups'), hash: window.location.hash === hash0, row2: field(2, 'start').value };
fire(handles()[0], 'keydown', { key: 'End' });
out.afterEnd = drafts.at(-1);
fire(handles()[0], 'keydown', { key: 'ArrowRight' });
out.clampKey = { draft: drafts.at(-1), live: byId('lgroups-live').textContent };
// Pointer drag: snap to whole seams; the ribbon spans x = 100..700 px, 10 px per layer.
fire(handles()[1], 'pointerdown', { clientX: 200 });
out.dragging = handles()[1].className;
fire(handles()[1], 'pointermove', { clientX: 231 });
out.dragDraft = drafts.at(-1);
fire(handles()[1], 'pointermove', { clientX: 120 });
fire(handles()[1], 'pointerup');
out.dragEnd = { draft: drafts.at(-1), cls: handles()[1].className, live: byId('lgroups-live').textContent };
keyDoc('Escape');
out.escaped = { hidden: byId('lgroups-modal').hidden, last: drafts.at(-1), state: s.get('lgroups'), mode: s.get('lgmode') };

// Table fields, clamping, presets, shorthand.
fire(byId('lgroups-edit'), 'click');
const end2 = field(2, 'end');
end2.value = '30'; fire(end2, 'change');
out.clampField = { draft: drafts.at(-1), live: byId('lgroups-live').textContent, value: end2.value,
  cls: end2.parent.className };
const start3 = field(3, 'start');
start3.value = '12'; fire(start3, 'change');
out.startField = { draft: drafts.at(-1), live: byId('lgroups-live').textContent };
start3.value = 'x'; fire(start3, 'change');
out.badField = { live: byId('lgroups-live').textContent, draft: drafts.at(-1) };
const presetButtons = byId('lgroups-presets').children;
fire(byId('lgroups-presets'), 'click', { target: presetButtons[1] });
out.preset = { draft: drafts.at(-1), pressed: presetButtons.map((b) => b.getAttribute('aria-pressed')) };
byId('lgroups-shorthand').value = '1-3, 4-6';
fire(byId('lgroups-shorthand-apply'), 'click');
out.shortError = { hidden: byId('lgroups-shorthand-error').hidden, text: byId('lgroups-shorthand-error').textContent,
  invalid: byId('lgroups-shorthand').attrs['aria-invalid'] ?? null };
byId('lgroups-shorthand').value = '3, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7';
fire(byId('lgroups-shorthand'), 'keydown', { key: 'Enter' });
out.shortOk = { draft: drafts.at(-1), hidden: byId('lgroups-shorthand-error').hidden,
  value: byId('lgroups-shorthand').value };
out.beforeApply = { state: s.get('lgroups'), mode: s.get('lgmode'), stored: store.get('calosrv.layerGroups.custom') ?? null };
fire(byId('lgroups-apply'), 'click');
out.applied = { state: s.get('lgroups'), mode: s.get('lgmode'), hidden: byId('lgroups-modal').hidden,
  last: drafts.at(-1), stored: store.get('calosrv.layerGroups.custom') ?? null, summary: byId('lgroups-summary').textContent,
  hash: window.location.hash };

// Reopen: the last custom is offered; Reset and Apply store null.
fire(byId('lgroups-edit'), 'click');
out.reopened = { custom: !byId('lgroups-preset-custom').hidden, pressed: presetButtons.map((b) => b.getAttribute('aria-pressed')) };
fire(byId('lgroups-reset'), 'click');
out.reset = drafts.at(-1);
fire(byId('lgroups-presets'), 'click', { target: byId('lgroups-preset-custom') });
out.customPreset = drafts.at(-1);
fire(byId('lgroups-reset'), 'click');
fire(byId('lgroups-apply'), 'click');
out.uniformApplied = { state: s.get('lgroups'), mode: s.get('lgmode'), hash: window.location.hash };
// Cancel restores, and a blocked storage changes nothing but the custom preset.
storageBlocked = true;
fire(byId('lgroups-edit'), 'click');
out.blockedCustom = byId('lgroups-preset-custom').hidden;
fire(handles()[0], 'keydown', { key: 'ArrowLeft' });
fire(byId('lgroups-cancel'), 'click');
out.cancelled = { hidden: byId('lgroups-modal').hidden, last: drafts.at(-1), state: s.get('lgroups') };
fire(byId('lgroups-edit'), 'click');
fire(handles()[0], 'keydown', { key: 'ArrowLeft' });
fire(byId('lgroups-apply'), 'click');
out.blockedApply = s.get('lgroups');
storageBlocked = false;

// The experiment changes: a lattice too short hides the group with its reason.
control.setExperiment({ nLayers: 8 });
out.short = sidebar();
control.setExperiment({ nLayers: null });
out.noLattice = sidebar();
control.setExperiment({ nLayers: 60 });
control.setAvailable(false, 'This experiment has no hits to project.');
out.unavailable = sidebar();
control.setAvailable(true);
out.available = sidebar().hidden;
control.destroy();
s.set({ lgmode: 'off' });
out.destroyed = sidebar().checked;

// The Models page, and a link that does not fit.
build();
s = fresh('#table_name=t&lgmode=pool&lgroups=2.2.3.3.3.4.4.5.5.6.7.8.8');
control = mountLayerGroupControl({ state: s, page: 'models', doc: document });
control.setExperiment({ nLayers: 56 });
out.models = sidebar();
out.modelsResolved = control.resolved();
out.modelsMode = s.get('lgmode');
s.set({ frame: 'trans' });
control.setDepthContext({ numbering: 'relative' });
out.relBar = sidebar().segments[0];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ui() -> dict:
    return _run(_CONTROL_SCRIPT, [(JS / "state.js").as_uri(), (JS / "controls" / "layer_groups_control.js").as_uri()])


def test_the_group_stays_hidden_until_a_lattice_of_13_layers_is_adopted(ui):
    assert ui["beforeExperiment"]["hidden"] is True and ui["beforeExperiment"]["editDisabled"] is True
    assert ui["adopted"]["hidden"] is False and ui["adopted"]["reason"] is None
    assert ui["stateL"]["L"] == 60, "setExperiment tells the state its layer count"
    assert ui["short"]["hidden"] is True and "fewer than the 13 channels" in ui["short"]["reason"]
    assert ui["noLattice"]["hidden"] is True and "no depth-layer lattice" in ui["noLattice"]["reason"]
    assert ui["unavailable"]["hidden"] is True and ui["unavailable"]["reason"] == "This experiment has no hits to project."
    assert ui["available"] is False


def test_the_sidebar_shows_the_partition(ui):
    side = ui["adopted"]
    assert side["checked"] == ["off"]
    assert len(side["segments"]) == 13
    assert [int(seg[1]) for seg in side["segments"]] == UNIFORM_60
    assert side["segments"][0] == ["lg-bar-seg", "5", "Ch 1 · layers 1–5"]
    assert side["segments"][1][0] == "lg-bar-seg is-alt"
    assert side["summary"] == "13 channels over 60 layers · Uniform"
    assert side["barLabel"].startswith("The 13 Longitudinal Channels: layers 1–5, 6–10")
    assert side["notice"] is None and side["info"] is None


def test_the_mode_radios_write_the_state(ui):
    assert ui["afterRadio"] == {"lgmode": "bounds", "hash": "#table_name=t&lgmode=bounds", "side": ["bounds"]}


def test_pooled_is_disabled_in_local_with_its_reason_and_the_mode_is_kept(ui):
    local = ui["local"]
    assert local["poolDisabled"] is True and "is-disabled" in local["poolClass"]
    assert "no common layer grid to pool" in local["poolTitle"]
    assert local["notice"].endswith("Boundaries are drawn instead.")
    assert local["info"] == [local["notice"]]
    assert local["checked"] == ["pool"] and ui["localMode"] == "pool"
    lab = ui["labAgain"]
    assert lab["poolDisabled"] is False and lab["poolTitle"] == "" and lab["notice"] is None


def test_pooled_is_disabled_on_the_models_page_and_a_misfit_link_falls_back(ui):
    models = ui["models"]
    assert models["poolDisabled"] is True and "this page draws boundaries" in models["poolTitle"]
    assert "do not fit this experiment’s 56 layers: Uniform is drawn." in models["notice"]
    assert "Boundaries are drawn instead." in models["notice"]
    assert ui["modelsMode"] == "pool"
    assert ui["modelsResolved"] == {"mode": "pool", "counts": UNIFORM_56, "fallback": True, "L": 56}
    assert models["summary"] == "13 channels over 56 layers · Uniform"
    assert ui["relBar"][2] == "Rel Ch 1 · layers 1–5"


def test_the_modal_builds_the_ribbon_the_handles_and_the_table(ui):
    o = ui["opened"]
    assert o["modalHidden"] is False
    assert o["cells"] == 60 and o["handles"] == 12 and o["rows"] == 13
    assert o["canvas"] == "lg-profile"
    assert o["cellAlt"] == ["lg-cell"] * 5 + ["lg-cell is-alt"] * 2
    assert o["cellTitle"] == "Layer 6 · Ch 2"
    aria = o["aria"]
    assert aria["role"] == "slider" and aria["aria-orientation"] == "horizontal"
    assert (aria["aria-valuemin"], aria["aria-valuemax"], aria["aria-valuenow"]) == ("1", "9", "5")
    assert aria["aria-label"] == "Seam between Ch 1 and Ch 2"
    assert aria["aria-valuetext"] == "Ch 1 ends at layer 5, Ch 2 starts at layer 6 · seam at Z = 105.65 mm"
    assert o["tabIndex"] == 0 and o["focused"] is True
    assert o["left"][0] == f"{5 / 60 * 100}%"
    assert o["row1"][0] == ["", "Ch 1"] and o["row1"][3] == ["lg-num", "5"]
    assert o["row1"][1][0] == "lg-start lg-locked"
    assert o["locks"] == [True, True, False, False]
    assert o["field2"] == ["6", "2", "10"]
    assert o["thickness"] == "102.5 mm"
    assert o["top"][0] == ["layer 1", f"{0.5 / 60 * 100}%"]
    assert o["bottom"][0] == "Z = 3.15 mm"
    assert f"Z = z {MINUS} 3649 mm" in o["note"]
    assert o["shorthand"].startswith("1–5, 6–10, 11–15")
    assert o["pressed"] == ["true", "false", "false", "false"]


def test_a_draft_reaches_the_page_and_nothing_is_written(ui):
    assert ui["keyRight"] is True, "the key is consumed"
    k = ui["afterKey"]
    assert k["draft"] == [6, 4] + UNIFORM_60[2:]
    assert k["now"] == "6" and k["text"].startswith("Ch 1 ends at layer 6")
    assert k["state"] is None and k["hash"] is True
    assert k["row2"] == "7"
    assert ui["afterEnd"] == [9, 1] + UNIFORM_60[2:]
    clamp = ui["clampKey"]
    assert clamp["draft"] == [9, 1] + UNIFORM_60[2:]
    assert clamp["live"] == "Ch 1 ends at layer 9: layer 10 was asked for, but every channel keeps at least one layer."


def test_a_pointer_drag_snaps_and_announces_its_clamp_once(ui):
    assert "is-dragging" in ui["dragging"]
    # x = 231 px is 13.1 layers along: the seam after Ch 2 snaps to layer 13.
    assert ui["dragDraft"] == [9, 4, 2] + UNIFORM_60[3:]
    end = ui["dragEnd"]
    # Dragged to layer 2, the seam stops at layer 10 so Ch 2 keeps one layer.
    assert end["draft"] == [9, 1, 5] + UNIFORM_60[3:]
    assert "is-dragging" not in end["cls"]
    assert end["live"].startswith("Ch 2 ends at layer 10: layer 2 was asked for")


def test_escape_drops_the_draft(ui):
    assert ui["escaped"] == {"hidden": True, "last": None, "state": None, "mode": "off"}


def test_the_table_fields_edit_the_seams_and_announce_clamping(ui):
    f = ui["clampField"]
    assert f["draft"] == [5, 9, 1] + UNIFORM_60[3:]
    assert f["value"] == "14"
    assert "lg-clamped" in f["cls"]
    assert f["live"] == "Ch 2 ends at layer 14: layer 30 was asked for, but every channel keeps at least one layer."
    st = ui["startField"]
    assert st["draft"] == [5, 6, 4] + UNIFORM_60[3:]
    assert st["live"] == "Ch 2: layers 6–11; Ch 3: layers 12–15."
    bad = ui["badField"]
    assert bad["live"] == "Ch 3 start: enter a whole layer number; it was kept."
    assert bad["draft"] == st["draft"]


def test_presets_and_the_shorthand_set_the_draft(ui):
    assert ui["preset"]["draft"] == EM_60
    assert ui["preset"]["pressed"] == ["false", "true", "false", "false"]
    err = ui["shortError"]
    # The sentence is the engine's (layer_groups.js parseShorthand); the control shows it.
    assert err["hidden"] is False and "13" in err["text"] and err["invalid"] == "true"
    ok = ui["shortOk"]
    assert ok["draft"] == CUSTOM_60 and ok["hidden"] is True and ok["value"].startswith("1–3, 4–6, 7–9")


def test_apply_writes_the_state_and_remembers_a_custom_partition(ui):
    assert ui["beforeApply"] == {"state": None, "mode": "off", "stored": None}
    a = ui["applied"]
    assert a["state"] == _dots(CUSTOM_60) and a["mode"] == "bounds"
    assert a["hidden"] is True and a["last"] is None
    assert a["stored"] == '{"60":"%s"}' % _dots(CUSTOM_60)
    assert a["summary"] == "13 channels over 60 layers · custom"
    assert a["hash"] == f"#table_name=t&lgmode=bounds&lgroups={_dots(CUSTOM_60)}"
    assert ui["reopened"] == {"custom": True, "pressed": ["false", "false", "false", "true"]}
    assert ui["reset"] == UNIFORM_60
    assert ui["customPreset"] == CUSTOM_60


def test_applying_uniform_stores_null(ui):
    assert ui["uniformApplied"] == {"state": None, "mode": "bounds", "hash": "#table_name=t&lgmode=bounds"}


def test_cancel_restores_and_a_blocked_storage_is_survived(ui):
    assert ui["blockedCustom"] is True
    assert ui["cancelled"] == {"hidden": True, "last": None, "state": None}
    assert ui["blockedApply"] == _dots([4, 6] + UNIFORM_60[2:])


def test_a_destroyed_control_stops_listening(ui):
    assert ui["destroyed"] == ["bounds"], "the radios are no longer synced"
