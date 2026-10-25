"""The Physics page's shell, executed under Node against the recorded payloads.

What the page shows for an experiment is decided from its capability block
(``capabilities.js`` ``page1Plan``), so the plan is checked on the recorded
catalogue of all three kinds (``tests/fixtures/payloads/experiments.json``),
which is the backend's payload and so the contract. Around it:

* ``state.js``: the experiment's own filter axes (a single shower filters on
  its incident momentum p alone, sent as e1), and bounds adopted onto the
  snapped slider domains with no raw bound ever written to the link;
* ``controls/filter_block.js``: the E1 control relabelled "p — incident
  momentum" and the E2, D and undefined-D controls hidden, then restored
  exactly for a two-shower experiment;
* ``export/caption.js`` / ``export/filename.js``: provenance named by the
  experiment's axes (``p 2.00–5.00 GeV``, ``p-2.00-5.00``);
* ``lazy_cards.js``: a card loads when visible, again only when its request
  changes, never twice for one key, and a superseded load marks nothing;
* ``physics_section.js``: the nine cards' anatomy, their requests per kind
  (a single shower never sends e2, d, include_undefined_d or a shower), one
  request shared by the cards that read it, the server's reason on a shut
  card and the rebuild offer on a stale one;
* ``frame_views.js`` / ``export/disclosure.js``: single-shower wording keyed
  off the experiment's showers per event, and the Local frame's C9 sentence.

The DOM-bound modules run against a minimal fake document (below): enough of
createElement, text nodes, attributes, classes and listeners for the code
paths under test, nothing more. Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
PAYLOADS = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: A hyphen-minus that signs a number (CLAUDE.md: U+2212 for every rendered negative).
HYPHEN_NUMBER = re.compile(r"(?<![\w])-\d")


def _payload(name: str) -> dict:
    return json.loads((PAYLOADS / f"{name}.json").read_text(encoding="utf-8"))


def _path(name: str) -> str:
    """A recorded payload's path, for the script to read: payloads are too large for argv."""
    return str(PAYLOADS / f"{name}.json")


def _run(script: str, args: list) -> dict:
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script, json.dumps(args)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# A minimal document: elements with children, text nodes, attributes,
# dataset, classList, listeners and `closest`, plus a window with a hash.
_FAKE_DOM = r"""
const { readFileSync } = await import('node:fs');
const load = (path) => JSON.parse(readFileSync(path, 'utf8'));
const loadAll = (paths) => Object.fromEntries(Object.entries(paths).map(([k, p]) => [k, load(p)]));
class FakeText {
  constructor(text) { this.nodeName = '#text'; this.data = String(text); this.parent = null; }
  get textContent() { return this.data; }
  cloneNode() { return new FakeText(this.data); }
}
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.nodeName = this.tagName;
    this.childNodes = [];
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.className = '';
    this.id = '';
    this.title = '';
    this.value = '';
    this.parent = null;
  }
  get children() { return this.childNodes.filter((n) => n instanceof FakeElement); }
  get classList() {
    const el = this;
    const set = () => new Set(el.className.split(/\s+/).filter(Boolean));
    return {
      toggle(name, on) {
        const s = set(); const want = on === undefined ? !s.has(name) : Boolean(on);
        if (want) s.add(name); else s.delete(name);
        el.className = [...s].join(' '); return want;
      },
      add(name) { const s = set(); s.add(name); el.className = [...s].join(' '); },
      remove(name) { const s = set(); s.delete(name); el.className = [...s].join(' '); },
      contains(name) { return set().has(name); },
    };
  }
  append(...nodes) {
    for (const n of nodes) {
      const node = typeof n === 'string' ? new FakeText(n) : n;
      if (node.parent) node.parent.childNodes = node.parent.childNodes.filter((c) => c !== node);
      node.parent = this;
      this.childNodes.push(node);
    }
  }
  replaceChildren(...nodes) { for (const c of this.childNodes) c.parent = null; this.childNodes = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'title') this.title = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : (k === 'title' && this.title ? this.title : null); }
  removeAttribute(k) { delete this.attrs[k]; if (k === 'title') this.title = ''; }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  dispatch(type) { for (const fn of this.listeners[type] ?? []) fn({ target: this, stopPropagation() {} }); }
  click() { this.dispatch('click'); }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(''); }
  set textContent(v) { this.replaceChildren(); if (v !== '' && v !== null && v !== undefined) this.append(new FakeText(v)); }
  get options() { return this.children.filter((c) => c.tagName === 'OPTION'); }
  get clientWidth() { return 600; }
  get clientHeight() { return 330; }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    return this.tagName === selector.toUpperCase();
  }
  closest(selector) {
    for (let el = this; el; el = el.parent) if (el instanceof FakeElement && el.matches(selector)) return el;
    return null;
  }
  cloneNode(deep) {
    const copy = new FakeElement(this.tagName);
    Object.assign(copy.attrs, this.attrs);
    Object.assign(copy.dataset, this.dataset);
    copy.className = this.className; copy.id = this.id; copy.title = this.title;
    if (deep) copy.append(...this.childNodes.map((c) => c.cloneNode(true)));
    return copy;
  }
  walk(fn) { fn(this); for (const c of this.children) c.walk(fn); }
  find(fn) { let hit = null; this.walk((el) => { if (!hit && fn(el)) hit = el; }); return hit; }
  findAll(fn) { const out = []; this.walk((el) => { if (fn(el)) out.push(el); }); return out; }
}
const registry = new Map();
const byId = (id) => {
  if (!registry.has(id)) { const el = new FakeElement('div'); el.id = id; registry.set(id, el); }
  return registry.get(id);
};
globalThis.document = {
  createElement: (tag) => new FakeElement(tag),
  createTextNode: (text) => new FakeText(text),
  getElementById: (id) => registry.get(id) ?? null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  activeElement: null,
};
let replaced = [];
globalThis.window = {
  location: { hash: '', pathname: '/', origin: 'http://calosrv.test' },
  history: {
    replaceState(_s, _t, url) {
      replaced.push(url);
      const at = url.indexOf('#');
      window.location.hash = at >= 0 ? url.slice(at) : '';
    },
  },
  addEventListener() {},
};
class FakeObserver {
  constructor(callback, options) { this.callback = callback; this.options = options; this.targets = []; FakeObserver.last = this; }
  observe(target) { this.targets.push(target); }
  unobserve(target) { this.targets = this.targets.filter((t) => t !== target); }
  disconnect() {}
  show(targets, visible = true) { this.callback(targets.map((target) => ({ target, isIntersecting: visible }))); }
}
globalThis.IntersectionObserver = FakeObserver;
const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setTimeout(r, 0)); };
"""


# ----------------------------------------------------------- the plan --

_PLAN_SCRIPT = _FAKE_DOM + r"""
const [capsUrl, stateUrl, captionUrl, filenameUrl, notesUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const caps = await import(capsUrl);
const { State, snapDomain } = await import(stateUrl);
const caption = await import(captionUrl);
const { figureName } = await import(filenameUrl);
const notes = await import(notesUrl);
const out = {};

const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
out.plans = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, caps.page1Plan(e)]));
out.legacy = caps.page1Plan({ table_name: 'old', status: 'ready', bounds: {} });
out.legacyNull = caps.page1Plan(null);
out.legacyCaps = caps.capabilitiesOf({ table_name: 'old' });

const stale = structuredClone(exps.two_shower_hits);
const notice = 'Built by an earlier release (derived tables v1); rebuild it (Admin Settings › Rebuild derived tables).';
stale.capabilities.derived = { version: 1, current: 2, status: 'stale', notice };
for (const id of ['profile-w', 'profile-r']) {
  stale.capabilities.panels[id] = false;
  stale.capabilities.reasons[id] = notice;
}
out.stale = caps.page1Plan(stale);
out.notice = notice;
out.energyTitle = notes.ENERGY_TITLE;
out.plot4Titles = caps.PLOT4_TITLES;
out.axes = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, caps.filterAxes(e)]));
out.kindLabels = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, caps.kindLabel(e)]));
out.texts = [caps.MISSING_PREDICTIONS, caps.EVENTS_ONLY_NOTICE, caps.EVENTS_ONLY_FOLLOW, caps.CANONICAL_SINGLE_REASON,
  caps.EVENTS_ONLY_CONTROLS];

// The frame across a switch of kind (Martin's Phase 6 decision).
const P = { two: out.plans.two_shower_hits, one: out.plans.single_shower_hits, events: out.plans.single_shower_events };
const carry = (from, to, frame) => caps.carriedFrame(P[from], P[to], frame);
out.radios = { two: caps.radioFrames(P.two), one: caps.radioFrames(P.one), events: caps.radioFrames(P.events) };
out.carry = {
  oneTransToTwo: carry('one', 'two', 'trans'),
  twoCanonicalToOne: carry('two', 'one', 'canonical'),
  oneLocalToTwo: carry('one', 'two', 'local'),
  twoLocalToOne: carry('two', 'one', 'local'),
  twoLabToOne: carry('two', 'one', 'lab'),
  // A link's legacy frame between two experiments of one kind is not a switch of kind.
  twoTransToTwo: carry('two', 'two', 'trans'),
  // The event-level kind hides its frame tier: the frame waits there untouched...
  oneTransToEvents: carry('one', 'events', 'trans'),
  // ...and the kind after it decides.
  eventsTransToTwo: carry('events', 'two', 'trans'),
  eventsLocalToOne: carry('events', 'one', 'local'),
  firstActivation: caps.carriedFrame(null, P.two, 'trans'),
};

// The slider domains: the RangeSlider arithmetic, outward to whole steps.
out.snap = { e1: snapDomain(0.408, 19.997, 0.05), d: snapDomain(2.4, 5307.6, 1) };

const fresh = (hash) => { window.location.hash = hash; replaced = []; return new State(); };
const bounds = { e1: [0.408, 19.99], e2: [0.5, 18.2], d: [2.4, 5307.6] };
let s = fresh('');
out.defaultParams = Object.keys(s.filterParams());
s.restrictAxes(caps.TWO_SHOWER_AXES);
out.twoParams = Object.keys(s.filterParams());
replaced = [];
out.twoDomains = s.adoptSnappedBounds(bounds);
out.twoWrites = [...replaced];
out.twoHash = window.location.hash;
out.twoValues = { ...s.values };

s = fresh('#e2_min=3&d_max=500&include_undefined_d=true&e1_max=5');
out.linkTouched = [...s.touched].sort();
s.restrictAxes(caps.SINGLE_SHOWER_AXES);
out.singleTouched = [...s.touched];
out.singleParams = s.filterParams();
replaced = [];
out.singleDomains = s.adoptSnappedBounds({ e1: [0.408, 19.99], e2: [null, null], d: [null, null] });
out.singleWrites = [...replaced];
out.singleHash = window.location.hash;
out.singleValues = { e1_min: s.values.e1_min, e1_max: s.values.e1_max, e2_min: s.values.e2_min,
  d_max: s.values.d_max, undefinedD: s.values.include_undefined_d };

s = fresh('#e1_min=2&e1_max=30');
s.restrictAxes(caps.TWO_SHOWER_AXES);
s.adoptSnappedBounds(bounds);
out.foreign = [s.values.e1_min, s.values.e1_max];
s = fresh('#e1_max=5');
s.restrictAxes(caps.TWO_SHOWER_AXES);
s.adoptSnappedBounds(bounds);
out.upperOnly = [s.values.e1_min, s.values.e1_max];

// Provenance by the experiment's axes.
const defaults = { display: 'native', resolution: 150, frame: 'lab', channel: 'density', model: 'segmentation',
  include_undefined_d: false, anchor: 'backprojected' };
const stub = (axes, touched, values, frame = 'lab') => ({
  filterAxes: axes,
  isTouched: (axis) => touched.includes(axis),
  get: (key) => (key in values ? values[key] : (key === 'frame' ? frame : (defaults[key] ?? null))),
});
const single = stub(caps.SINGLE_SHOWER_AXES, ['e1'], { e1_min: 2, e1_max: 5, include_undefined_d: true });
const two = stub(null, ['e1', 'd'], { e1_min: 2, e1_max: 5, d_min: 10, d_max: 200, include_undefined_d: true });
out.caption = {
  single: caption.describeSelection(single, null, null, null, null, { filtersOnly: true }),
  two: caption.describeSelection(two, null, null, null, null, { filtersOnly: true }),
};
out.names = {
  single: figureName('xy', 'svg', { state: single }),
  two: figureName('xy', 'svg', { state: two }),
  correlation: figureName('correlation', 'svg', { state: stub(null, [], {}, 'canonical'), spatial: false,
    meta: { table_name: 'x', coord_system: 'local' } }),
  distribution: figureName('distribution', 'png', { state: stub(null, [], {}), spatial: false,
    meta: { table_name: 'x', quantity: 'u' } }),
  b3: figureName('energy', 'svg', { state: stub(caps.SINGLE_SHOWER_AXES, [], {}, 'local'), spatial: false,
    meta: { table_name: 'x', network: null } }),
  energyNoMeta: figureName('energy', 'svg', { state: stub(null, [], {}, 'local'), spatial: false, meta: null }),
  energyNetwork: figureName('energy', 'svg', { state: stub(null, [], {}, 'lab'), spatial: false,
    meta: { network: { frame: 'local' } } }),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def plan_results() -> dict:
    return _run(_PLAN_SCRIPT, [
        (JS / "capabilities.js").as_uri(), (JS / "state.js").as_uri(),
        (JS / "export" / "caption.js").as_uri(), (JS / "export" / "filename.js").as_uri(),
        (JS / "panel_notes.js").as_uri(), _path("experiments"),
    ])


ALL_PHYSICS = ["profile-w", "profile-r", "response-b1", "response-b2", "response-res", "response-b3",
               "distribution", "correlation", "statistics"]


def test_the_two_shower_plan_is_todays_page_plus_every_physics_card(plan_results):
    plan = plan_results["plans"]["two_shower_hits"]
    assert plan["spatial"] is True and plan["notice"] is None
    assert plan["plot4"] == "energy-d" and plan["plot4Title"] == plan_results["energyTitle"]
    assert plan["physics"] == ALL_PHYSICS and plan["disabled"] == {}
    assert [a["key"] for a in plan["axes"]] == ["e1", "e2", "d"]
    assert plan["frames"]["offered"] == ["lab", "trans", "local", "canonical"]
    assert plan["frames"]["labels"] is None and plan["frames"]["transPrimary"] is False
    assert plan["performance"] is True and plan["banner"] is None and plan["stale"] is None
    assert plan["status"] == {"d": True}
    assert plan["eventInspector"] and plan["compare"] and plan["windowAxis"]
    assert plan["nShowers"] == 2 and plan["showers"] == ["a", "b"]


def test_a_single_shower_plan_draws_b3_as_plot_4_and_shuts_the_d_frame_with_the_servers_reason(plan_results):
    plan = plan_results["plans"]["single_shower_hits"]
    reasons = plan["reasons"]
    assert plan["spatial"] is True and plan["notice"] is None
    assert plan["plot4"] == "response-b3"
    assert plan["plot4Title"] == "Response vs. Incident Momentum p"
    # Plot 4 draws the notebook's windows; the full-width card below keeps the
    # 1 GeV bins (Martin's Phase 6 decision), so the section holds all nine.
    assert plan["physics"] == ALL_PHYSICS
    assert plan["disabled"] == {}
    assert [a["key"] for a in plan["axes"]] == ["e1"]
    assert plan["axes"][0]["label"] == "p — incident momentum [GeV]" and plan["axes"][0]["token"] == "p-"
    assert plan["frames"]["offered"] == ["lab", "trans", "local"]
    assert plan["frames"]["disabled"]["canonical"] == reasons["frame-canonical"]
    assert plan["frames"]["transPrimary"] is True
    assert plan["frames"]["labels"]["aligned"]["label"] == "Shower-Aligned"
    assert plan["frames"]["labels"]["trans"]["label"] == "Translated"
    assert plan["channels"] == ["density"] and plan["models"] == []
    assert plan["performance"] is False and plan["status"] == {"d": False}
    # CLAUDE.md section 3: no predictions, a prominent banner; the server's reason leads.
    assert plan["banner"].startswith(reasons["energy"]) and "No model predictions" in plan["banner"]
    assert plan["eventInspector"] and plan["compare"]
    assert plan["showers"] == ["a"] and plan["nShowers"] == 1
    assert {"u", "v", "w", "energy", "theta", "phi", "p"} == set(plan["quantities"])


def test_the_events_only_plan_shows_the_notice_and_the_event_level_cards(plan_results):
    plan = plan_results["plans"]["single_shower_events"]
    assert plan["spatial"] is False and plan["plot4"] is None
    assert plan["notice"]["title"] == "No hits to project"
    assert plan["notice"]["text"].startswith(plan["reasons"]["xy"])
    # The hidden spatial sidebar groups are explained by the notice.
    assert plan["notice"]["text"].endswith(plan_results["texts"][4])
    for group in ("reference-frame", "spatial-resolution", "display-channel", "colour-map"):
        assert group in plan["notice"]["text"], group
    assert plan["physics"] == ["response-b1", "response-b2", "response-res", "response-b3", "distribution"]
    assert plan["eventInspector"] is False and plan["compare"] is False and plan["windowAxis"] is False
    assert plan["quantities"] == ["theta", "phi", "p"]
    assert plan["banner"] and plan["frames"]["offered"] == []
    assert [a["key"] for a in plan["axes"]] == ["e1"]


def test_an_experiment_without_the_block_keeps_todays_fallbacks_and_no_physics_cards(plan_results):
    for plan in (plan_results["legacy"], plan_results["legacyNull"]):
        assert plan["physics"] == [] and plan["plot4"] == "energy-d" and plan["spatial"] is True
        assert plan["frames"]["offered"] == ["lab", "canonical"]
        assert plan["channels"] == ["density", "gradcam"] and plan["models"] == ["segmentation"]
        assert [a["key"] for a in plan["axes"]] == ["e1", "e2", "d"]
    caps = plan_results["legacyCaps"]
    assert caps["frames"] == ["lab", "canonical"] and caps["legacy"] is True


def test_a_stale_experiment_shuts_its_cards_with_the_servers_reason(plan_results):
    plan = plan_results["stale"]
    assert plan["stale"]["notice"] == plan_results["notice"]
    assert plan["disabled"] == {"profile-w": plan_results["notice"], "profile-r": plan_results["notice"]}
    # Shut, not hidden: the card says why.
    assert "profile-w" in plan["physics"] and "profile-r" in plan["physics"]


def test_the_sidebar_radios_offer_the_legacy_frame_only_where_it_is_primary(plan_results):
    radios = plan_results["radios"]
    assert radios["two"] == ["lab", "local", "canonical"]
    assert radios["one"] == ["lab", "trans", "local"]
    assert radios["events"] == []


def test_a_switch_of_kind_carries_local_and_falls_back_to_absolute_with_one_line(plan_results):
    carry = plan_results["carry"]
    # Local means the same on every kind with hits: kept both ways, silently.
    for key in ("oneLocalToTwo", "twoLocalToOne", "twoLabToOne", "eventsLocalToOne"):
        assert carry[key] == {"frame": carry[key]["frame"], "notice": None}, key
    assert carry["oneLocalToTwo"]["frame"] == "local" and carry["twoLocalToOne"]["frame"] == "local"
    # A single shower's Translated is the legacy frame on two showers: Absolute, said once.
    moved = carry["oneTransToTwo"]
    assert moved["frame"] == "lab"
    assert moved["notice"].startswith("Translated is not offered for this experiment (two-shower hits)")
    assert moved["notice"].endswith("showing Absolute instead.")
    # The D-frame on a single shower: Absolute, said once.
    moved = carry["twoCanonicalToOne"]
    assert moved["frame"] == "lab" and "Separation-Aligned (D-Frame)" in moved["notice"]
    assert "single-shower hits" in moved["notice"]
    # Not switches of kind: a #frame=trans link keeps the legacy frame, and the
    # first activation (a link or a saved default) is never remapped.
    assert carry["twoTransToTwo"] == {"frame": "trans", "notice": None}
    assert carry["firstActivation"] == {"frame": "trans", "notice": None}
    # The event-level kind has no frame tier; the next kind with hits decides.
    assert carry["oneTransToEvents"] == {"frame": "trans", "notice": None}
    assert carry["eventsTransToTwo"]["frame"] == "lab" and carry["eventsTransToTwo"]["notice"]
    for value in carry.values():
        assert not HYPHEN_NUMBER.search(value["notice"] or ""), value


def test_kind_labels_and_texts_are_clean(plan_results):
    assert plan_results["kindLabels"] == {
        "two_shower_hits": "two-shower hits", "single_shower_hits": "single-shower hits",
        "single_shower_events": "single-shower event features"}
    texts = list(plan_results["texts"])
    for plan in plan_results["plans"].values():
        texts += [plan["banner"] or "", (plan["notice"] or {}).get("text", ""), plan["plot4Title"] or ""]
        texts += [a["label"] or "" for a in plan["axes"]] + [a["hint"] or "" for a in plan["axes"]]
    for text in texts:
        assert not HYPHEN_NUMBER.search(text), text


def test_snap_domain_is_the_sliders_arithmetic(plan_results):
    lo, hi = plan_results["snap"]["e1"]
    assert lo == pytest.approx(0.40, abs=1e-12) and hi == pytest.approx(20.0, abs=1e-12)
    assert plan_results["snap"]["d"] == [2, 5308]


def test_filter_params_send_only_the_experiments_axes(plan_results):
    seven = ["table_name", "e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d"]
    assert plan_results["defaultParams"] == seven
    assert plan_results["twoParams"] == seven
    assert list(plan_results["singleParams"]) == ["table_name", "e1_min", "e1_max"]


def test_adopting_bounds_never_writes_a_raw_bound_to_the_link(plan_results):
    assert len(plan_results["twoWrites"]) == 1
    for url in plan_results["twoWrites"]:
        for key in ("e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max"):
            assert key not in url, url
    # The single-shower link's own e1_max=5 is a deliberate bound and stays.
    for url in plan_results["singleWrites"]:
        for key in ("e1_min", "e2_min", "e2_max", "d_min", "d_max"):
            assert key not in url, url
    assert plan_results["twoHash"] == ""
    values = plan_results["twoValues"]
    assert values["e1_min"] == pytest.approx(0.40) and values["e1_max"] == pytest.approx(20.0)
    assert values["d_min"] == 2 and values["d_max"] == 5308


def test_a_two_shower_link_on_a_single_shower_experiment_drops_e2_and_d(plan_results):
    assert plan_results["linkTouched"] == ["d", "e1", "e2"]
    assert plan_results["singleTouched"] == ["e1"]
    values = plan_results["singleValues"]
    assert values["e2_min"] is None and values["d_max"] is None and values["undefinedD"] is False
    # The link's own e1 maximum survives; the full-range minimum is left out of the link.
    assert values["e1_max"] == 5 and values["e1_min"] == pytest.approx(0.40)
    assert plan_results["singleHash"] == "#e1_max=5"
    assert plan_results["singleDomains"]["e2"] is None and plan_results["singleDomains"]["d"] is None


def test_link_bounds_are_kept_in_range_and_reset_out_of_it(plan_results):
    assert plan_results["upperOnly"][1] == 5 and plan_results["upperOnly"][0] == pytest.approx(0.40)
    lo, hi = plan_results["foreign"]
    assert lo == pytest.approx(0.40) and hi == pytest.approx(20.0)


def test_provenance_names_the_experiments_axes(plan_results):
    assert plan_results["caption"]["single"] == "selection p 2.00–5.00 GeV."
    assert plan_results["caption"]["two"] == (
        "selection E₁ 2.00–5.00 GeV, D 10–200 mm · including events with undefined D.")
    assert "_p-2.00-5.00_" in plan_results["names"]["single"]
    assert "_E1-2.00-5.00_" in plan_results["names"]["two"]


def test_a_physics_figure_is_named_by_its_own_response(plan_results):
    names = plan_results["names"]
    assert names["correlation"].startswith("correlation_full_local_")
    assert "canonical" not in names["correlation"]
    assert names["distribution"].startswith("distribution_full_u_")
    # The momentum-sliced grid has no network: no frame token from the sidebar.
    assert names["b3"].startswith("energy_full_2")
    # The energy panel keeps its rules: its network, else the sidebar's frame.
    assert names["energyNoMeta"].startswith("energy_full_local_")
    assert names["energyNetwork"].startswith("energy_full_local_")


# ------------------------------------------------------- the filter block --

_FILTER_SCRIPT = _FAKE_DOM + r"""
const [filterUrl, stateUrl, capsUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const ids = ['e1', 'e2', 'd'];
for (const axis of ids) {
  for (const part of ['lo', 'hi', 'fill', 'num-lo', 'num-hi']) {
    const el = byId(`${axis}-${part}`);
    el.tagName = part === 'fill' ? 'DIV' : 'INPUT';
  }
  byId(`ctl-${axis}`).className = 'control';
}
for (const id of ['filter-logic', 'ctl-undefined-d', 'opt-undefined-d']) byId(id);
for (const [id, value] of [['e1-num-lo', 'E1 minimum [GeV]'], ['e1-num-hi', 'E1 maximum [GeV]'],
                           ['e1-lo', 'E1 minimum slider'], ['e1-hi', 'E1 maximum slider']]) {
  byId(id).setAttribute('aria-label', value);
}
const label = byId('e1-label');
const sub = document.createElement('sub');
sub.append('1');
label.append('E', sub, ' — Shower A momentum [GeV]');
byId('e1-hint').append('True incident momentum of shower A (incoming_momentum_A).');

const { FilterBlock } = await import(filterUrl);
const { State } = await import(stateUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
window.location.hash = '#d_max=900';
const state = new State();
let commits = 0;
const block = new FilterBlock({ state, onCommit: () => { commits += 1; } });
const snapshot = () => ({
  hidden: Object.fromEntries(['ctl-e1', 'ctl-e2', 'ctl-d', 'filter-logic', 'ctl-undefined-d']
    .map((id) => [id, byId(id).hidden])),
  label: label.textContent,
  labelChildren: label.childNodes.length,
  hint: byId('e1-hint').textContent,
  aria: byId('e1-num-lo').getAttribute('aria-label'),
  params: state.filterParams(),
  hash: window.location.hash,
});
const out = {};
replaced = [];
block.adopt(exps.single_shower_hits);
out.single = snapshot();
out.singleWrites = [...replaced];
replaced = [];
block.adopt(exps.two_shower_hits);
out.two = snapshot();
out.twoWrites = [...replaced];
out.e1Domain = [block.sliders.e1.min, block.sliders.e1.max];
byId('opt-undefined-d').checked = true;
byId('opt-undefined-d').dispatch('change');
out.undefinedD = { value: state.get('include_undefined_d'), commits };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def filter_results() -> dict:
    return _run(_FILTER_SCRIPT, [
        (JS / "controls" / "filter_block.js").as_uri(), (JS / "state.js").as_uri(),
        (JS / "capabilities.js").as_uri(), _path("experiments"),
    ])


def test_a_single_shower_filters_on_p_alone(filter_results):
    single = filter_results["single"]
    assert single["hidden"] == {"ctl-e1": False, "ctl-e2": True, "ctl-d": True, "filter-logic": True,
                                "ctl-undefined-d": True}
    assert single["label"] == "p — incident momentum [GeV]"
    assert single["hint"] == "True incident momentum of the shower (incoming_momentum)."
    assert single["aria"] == "p minimum [GeV]"
    assert list(single["params"]) == ["table_name", "e1_min", "e1_max"]
    # The link's d_max had no axis to apply to: gone from the link too.
    assert "d_max" not in single["hash"]
    for url in filter_results["singleWrites"]:
        assert "e1_min" not in url and "e1_max" not in url, url


def test_a_two_shower_experiment_gets_the_markup_back_exactly(filter_results):
    two = filter_results["two"]
    assert not any(two["hidden"].values())
    assert two["label"] == "E1 — Shower A momentum [GeV]" and two["labelChildren"] == 3
    assert two["hint"].startswith("True incident momentum of shower A")
    assert two["aria"] == "E1 minimum [GeV]"
    assert list(two["params"]) == ["table_name", "e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max",
                                   "include_undefined_d"]
    lo, hi = filter_results["e1Domain"]
    assert lo == pytest.approx(2.70) and hi == pytest.approx(17.90)
    assert filter_results["undefinedD"] == {"value": True, "commits": 1}


# --------------------------------------------------------- lazy loading --

_LAZY_SCRIPT = _FAKE_DOM + r"""
const [lazyUrl] = JSON.parse(process.argv[1]);
const { LazyCards, shouldLoad, requestKey, isRefusal } = await import(lazyUrl);
const out = {};
out.truth = {
  visibleStale: shouldLoad({ visible: true, key: 'k', loadedKey: null, pendingKey: null }),
  visibleCurrent: shouldLoad({ visible: true, key: 'k', loadedKey: 'k', pendingKey: null }),
  pendingSame: shouldLoad({ visible: true, key: 'k', loadedKey: null, pendingKey: 'k' }),
  pendingOther: shouldLoad({ visible: true, key: 'k2', loadedKey: null, pendingKey: 'k' }),
  hidden: shouldLoad({ visible: false, key: 'k', loadedKey: null, pendingKey: null }),
  notApplicable: shouldLoad({ visible: true, key: null, loadedKey: null, pendingKey: null }),
};
out.keys = {
  orderFree: requestKey('/a', { b: 1, a: 2, c: null, d: undefined, e: '' }) === requestKey('/a', { a: 2, b: 1 }),
  value: requestKey('/a', { a: 1 }) !== requestKey('/a', { a: 2 }),
  route: requestKey('/a', { a: 1 }) !== requestKey('/b', { a: 1 }),
};
const errors = [];
const lazy = new LazyCards({ root: 'ROOT', rootMargin: '0px', onError: (e, el) => errors.push([e.message, el.name]) });
out.observerOptions = FakeObserver.last.options;
const loads = [];
let keyA = 'a1';
let keyB = 'b1';
let failB = null;
let gate = null;
const a = { name: 'a' };
const b = { name: 'b' };
lazy.watch(a, { key: () => keyA, load: async (k) => { loads.push(['a', k]); if (gate) await gate; } });
lazy.watch(b, {
  key: () => keyB,
  load: async (k) => {
    loads.push(['b', k]);
    if (failB) { const e = new Error(failB.message); e.name = failB.name; e.status = failB.status; throw e; }
  },
});
out.hiddenRefresh = (await lazy.refresh()).length;
FakeObserver.last.show([a]);
await settle();
out.afterScroll = [...loads];
out.sameKey = (await lazy.refresh()).length;
keyA = 'a2';
await lazy.refresh();
out.afterChange = loads.slice(-1);
// A fault that may pass - the network, a 5xx - is not loaded: the next
// refresh (or visibility) asks again, for the same request.
failB = { message: 'Failed to fetch', name: 'NetworkError' };
FakeObserver.last.show([b]);
await settle();
out.transientRetried = (await lazy.refresh()).length;
failB = { message: 'DuckDB fell over', name: 'Error', status: 503 };
out.serverRetried = (await lazy.refresh()).length;
FakeObserver.last.show([b], false);
FakeObserver.last.show([b]);
await settle();
out.retriedOnVisibility = loads.filter(([card, k]) => card === 'b' && k === 'b1').length;
// A refusal - the server's 422 - is the answer to this request: not asked again.
failB = { message: 'refused', name: 'ApiError', status: 422 };
out.refused = (await lazy.refresh()).length;
out.errors = [...errors];
out.noRetry = (await lazy.refresh()).length;
out.refusalTruth = [422, 400, 404, 408, 429, 500, 503, 0, undefined].map((status) => isRefusal({ status }));
keyB = 'b2';
failB = { message: 'superseded', name: 'AbortError' };
out.abort = (await lazy.refresh()).map((r) => r.status);
out.errorsAfterAbort = errors.length;
failB = null;
out.retried = (await lazy.refresh()).length;
lazy.forget();
// Visibility is measured again: nothing loads until the observer reports.
out.afterForget = (await lazy.refresh()).length;
out.reobserved = FakeObserver.last.targets.length;
FakeObserver.last.show([a, b]);
await settle();
out.afterReport = loads.slice(-2).map(([card]) => card).sort();
// A load overtaken by a newer key marks nothing.
let release;
gate = new Promise((resolve) => { release = resolve; });
keyA = 'a3';
const first = lazy.refresh();
keyA = 'a4';
gate = null;
const second = lazy.refresh();
release();
await first; await second;
out.overtaken = { loads: loads.slice(-2), current: lazy.isCurrent(a) };
keyA = 'a3';
out.a3Stale = (await lazy.refresh()).length;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def lazy_results() -> dict:
    return _run(_LAZY_SCRIPT, [(JS / "lazy_cards.js").as_uri()])


def test_should_load_truth_table(lazy_results):
    assert lazy_results["truth"] == {"visibleStale": True, "visibleCurrent": False, "pendingSame": False,
                                     "pendingOther": True, "hidden": False, "notApplicable": False}


def test_request_keys_are_canonical(lazy_results):
    assert all(lazy_results["keys"].values())


def test_a_card_loads_when_it_scrolls_in_and_again_only_when_its_request_changes(lazy_results):
    assert lazy_results["observerOptions"]["root"] == "ROOT"
    assert lazy_results["observerOptions"]["rootMargin"] == "0px"
    assert lazy_results["hiddenRefresh"] == 0
    assert lazy_results["afterScroll"] == [["a", "a1"]]
    assert lazy_results["sameKey"] == 0
    assert lazy_results["afterChange"] == [["a", "a2"]]


def test_a_refused_load_is_not_retried_for_the_same_request(lazy_results):
    assert lazy_results["refused"] == 1
    assert lazy_results["noRetry"] == 0
    assert lazy_results["refusalTruth"] == [True, True, True, False, False, False, False, False, False]


def test_a_transient_failure_is_retried_on_the_next_refresh_or_visibility(lazy_results):
    # The network failure, then the 5xx, then a scroll back into view: each asks again.
    assert lazy_results["transientRetried"] == 1
    assert lazy_results["serverRetried"] == 1
    assert lazy_results["retriedOnVisibility"] == 4
    # Only the loads the observer started report through onError (refresh's are the caller's).
    assert [message for message, _ in lazy_results["errors"]] == ["Failed to fetch", "DuckDB fell over"]


def test_a_superseded_load_is_neither_reported_nor_counted_as_loaded(lazy_results):
    assert lazy_results["abort"] == ["rejected"]
    assert lazy_results["errorsAfterAbort"] == len(lazy_results["errors"])
    assert lazy_results["retried"] == 1
    assert lazy_results["afterForget"] == 0 and lazy_results["reobserved"] == 2
    assert lazy_results["afterReport"] == ["a", "b"]
    assert lazy_results["overtaken"]["loads"] == [["a", "a3"], ["a", "a4"]]
    assert lazy_results["overtaken"]["current"] is True
    assert lazy_results["a3Stale"] == 1


# ----------------------------------------------------- the physics section --

_SECTION_SCRIPT = _FAKE_DOM + r"""
const [sectionUrl, stateUrl, capsUrl, cataloguePath, fixturePaths] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const fixtures = loadAll(fixturePaths);
const calls = [];
globalThis.fetch = async (url) => {
  const u = new URL(url);
  calls.push(u.pathname + u.search);
  const q = u.searchParams;
  let body;
  if (u.pathname === '/api/profiles') body = q.get('depth') === 'native' ? fixtures.profilesNative : fixtures.profilesW;
  else if (u.pathname === '/api/response') body = q.get('table_name') === 'single_events' ? fixtures.responseEvents : fixtures.response;
  else if (u.pathname === '/api/energy-distribution') body = fixtures.b3;
  else if (u.pathname === '/api/distributions') body = q.get('quantity') === 'u' ? fixtures.distU : fixtures.distPhi;
  else if (u.pathname === '/api/correlations') body = fixtures.correlation;
  else if (u.pathname === '/api/statistics') body = fixtures.statistics;
  else return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: 'no route' }) };
  return { ok: true, status: 200, json: async () => body };
};
const sectionModule = await import(sectionUrl);
const { PhysicsSection, cardRequest, cardOptions, reconcileControls, exportMeta, PHYSICS_CARDS } = sectionModule;
const { State } = await import(stateUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const plans = Object.fromEntries(Object.entries(exps).map(([k, e]) => [k, caps.page1Plan(e)]));
const out = {};

// ---- pure: requests per kind
const single = plans.single_shower_hits;
const two = plans.two_shower_hits;
const filtersOne = { table_name: 'single_hits', e1_min: 1, e1_max: 20 };
const filtersTwo = { table_name: 'experiment_baseline', e1_min: 1, e1_max: 20, e2_min: 1, e2_max: 20,
  d_min: 0, d_max: 900, include_undefined_d: false };
out.requests = {};
for (const spec of PHYSICS_CARDS) {
  out.requests[spec.id] = {
    single: cardRequest(spec.id, { filters: filtersOne, plan: single }),
    two: cardRequest(spec.id, { filters: filtersTwo, plan: two }),
  };
}
out.native = cardRequest('profile-w', { filters: filtersOne, plan: single,
  controls: { profileDepth: 'native', profileNotebook: true } });
out.notebook = cardRequest('profile-r', { filters: filtersOne, plan: single, controls: { profileRNotebook: true } });
// Each profile card owns its notebook flag; one request while their parameters agree.
const profilePair = (controls) => Object.fromEntries(['profile-w', 'profile-r'].map((id) => {
  const r = cardRequest(id, { filters: filtersOne, plan: single, controls });
  return [id, { abortKey: r.abortKey, params: r.params, title: sectionModule.cardTitle(id, controls) }];
}));
out.profiles = {
  plain: profilePair({}),
  wOnly: profilePair({ profileNotebook: true }),
  rOnly: profilePair({ profileRNotebook: true }),
  both: profilePair({ profileNotebook: true, profileRNotebook: true }),
  nativeR: profilePair({ profileDepth: 'native', profileRNotebook: true }),
  native: profilePair({ profileDepth: 'native' }),
};
out.bins = cardRequest('response-b3', { filters: filtersOne, plan: single, controls: { b3Slices: 'bins' } });
out.hitQuantity = cardRequest('distribution', { filters: filtersOne, plan: single, controls: { distQuantity: 'u', distWeighting: 'hit' } });
out.eventsQuantity = cardRequest('distribution', { filters: filtersOne, plan: plans.single_shower_events, controls: { distQuantity: 'u' } });
out.noTable = cardRequest('statistics', { filters: { table_name: null }, plan: single });
out.reconciled = reconcileControls({ corrCoord: 'canonical', statCoord: 'lab', profileShower: 'b' },
  { ...single, coordSystems: ['lab', 'trans'] });
out.options = {
  native: cardOptions('profile-w', { payload: fixtures.profilesNative, plan: single }),
  w: cardOptions('profile-w', { payload: fixtures.profilesW, plan: single }),
  r: cardOptions('profile-r', { payload: fixtures.profilesW, plan: single }),
  res: cardOptions('response-res', { plan: two, controls: { resShower: 'b', resQuantity: 'response_ratio' } }),
  dist: cardOptions('distribution', { payload: fixtures.distU, plan: single, controls: { distScale: 'log' } }),
};
out.exportMeta = exportMeta(fixtures.correlation);

// ---- the section, on a fake document
const rendered = [];
const created = [];
class FakePanel {
  constructor(element, options) { this.element = element; this.options = options; this.kind = 'fake'; created.push(element.id); }
  render(payload, opts) { this.lastPayload = payload; this.lastOpts = opts; rendered.push([this.element.id, opts]); }
  clear() { this.cleared = (this.cleared ?? 0) + 1; this.lastPayload = null; }
  relayout() { this.relaid = (this.relaid ?? 0) + 1; }
  setBusy() {}
}
// The response grid's interface (fixed between the shell and the panels).
class FakeGridPanel extends FakePanel {
  tableRows() { return [{ slice: 0, n: 3 }]; }
  renderTable(host) {
    const table = document.createElement('table');
    table.className = 'fit-table';
    table.textContent = `fitted μ and σ of ${this.lastOpts.shower}`;
    host.replaceChildren(table);
  }
  sparseLines() { return ['2 series below N = 15 drawn as event strips.', '1 low-N curve clipped at the axis top.']; }
}
const panelClasses = Object.fromEntries(['ProfilePanel', 'ResponsePanel', 'ResponseGridPanel', 'DistributionPanel',
  'CorrelationPanel', 'StatisticsPanel'].map((name) => [name, name === 'ResponseGridPanel' ? FakeGridPanel : FakePanel]));
window.location.hash = '';
const state = new State();
state.restrictAxes(caps.SINGLE_SHOWER_AXES);
state.set({ table_name: 'single_hits' }, { silent: true });
state.adoptSnappedBounds(exps.single_shower_hits.bounds);
const section = document.createElement('section');
const renderedIds = [];
const errors = [];
let opened = 0;
const physics = new PhysicsSection(section, {
  state, panelClasses, root: 'MAIN',
  onRendered: (id, payload) => renderedIds.push([id, Boolean(payload)]),
  onError: (error, context) => errors.push([context, error.message]),
  onOpenAdmin: () => { opened += 1; },
});
const cards = section.children;
out.anatomy = cards.map((card) => {
  const h2 = card.children[0];
  const actions = h2.children[1];
  const buttons = actions.children;
  const exporter = buttons.find((b) => b.dataset.export);
  return {
    panel: card.dataset.panel,
    hidden: card.hidden,
    firstInspect: buttons[0].dataset.inspect,
    firstControls: buttons[0].getAttribute('aria-controls'),
    lastExport: buttons[buttons.length - 1].dataset.export ?? null,
    exportTitle: exporter ? exporter.title : null,
    plotId: card.children[1].children[0].id,
    titleId: h2.children[0].id,
    wide: card.classList.contains('is-wide'),
  };
});
out.observer = FakeObserver.last.options;

physics.applyPlan(single);
out.singleHidden = Object.fromEntries(cards.map((c) => [c.dataset.panel, c.hidden]));
out.showerControls = cards.flatMap((c) => c.findAll((el) => el.dataset.physicsShower !== undefined && el.tagName === 'BUTTON'))
  .map((el) => el.parent.hidden);
FakeObserver.last.show(cards.filter((c) => !c.hidden));
await settle();
out.calls = [...calls];
out.created = [...created];
out.rendered = Object.fromEntries(rendered.map(([id, opts]) => [id, opts]));
out.renderedIds = [...renderedIds];
out.notes = Object.fromEntries(physics.ids().map((id) => {
  const n = physics.notes(id);
  return [id, n ? { title: n.title, headings: n.sections.map((s) => s.heading), lines: n.sections.flatMap((s) => s.lines),
    hazards: n.hazards } : null];
}));
const b3Card = cards.find((c) => c.dataset.panel === 'response-b3');
const b3Table = b3Card.find((el) => el.id === 'fit-table-response-b3');
const b3Sparse = b3Card.find((el) => el.id === 'energy-sparse-response-b3');
out.b3Hosts = {
  order: b3Card.children.map((el) => el.id || el.className),
  table: b3Table.textContent, tableTag: b3Table.children[0]?.tagName,
  sparse: b3Sparse.children.map((el) => [el.tagName, el.textContent]), sparseHidden: b3Sparse.hidden,
  request: calls.find((c) => c.startsWith('/api/energy-distribution')),
};
out.exportTargets = {
  profile: Boolean(physics.exportTarget('profile-w')?.panel),
  meta: physics.exportTarget('correlation')?.meta ?? null,
  statistics: physics.exportTarget('statistics'),
  foreign: physics.exportTarget('xy') === undefined,
  b3: Boolean(physics.exportTarget('response-b3')?.meta),
};
out.warnings = physics.warnings();

// A request control reloads; a render-only control repaints.
const before = calls.length;
const quantity = cards.find((c) => c.dataset.panel === 'distribution')
  .find((el) => el.tagName === 'SELECT');
out.quantityOptions = quantity.options.map((o) => o.value);
quantity.value = 'u';
quantity.dispatch('change');
await settle();
out.afterQuantity = calls.slice(before);
const logButton = cards.find((c) => c.dataset.panel === 'distribution').find((el) => el.dataset.distributionY === 'log');
const beforeLog = calls.length;
logButton.click();
await settle();
out.afterLog = { calls: calls.length - beforeLog, opts: rendered.filter(([id]) => id === 'plot-distribution').pop()[1] };
const nativeButton = cards.find((c) => c.dataset.panel === 'profile-w').find((el) => el.dataset.profileAxis === 'native');
nativeButton.click();
await settle();
out.afterNative = calls.slice(-1);
const notebook = cards.find((c) => c.dataset.panel === 'profile-w').find((el) => el.dataset.profileNotebook !== undefined);
out.notebookDisabled = { disabled: notebook.disabled, title: notebook.title };
out.profileTitle = cards.find((c) => c.dataset.panel === 'profile-w').children[0].children[0].textContent;
// The radial card's own notebook toggle: its own request, its own title.
const radial = cards.find((c) => c.dataset.panel === 'profile-r');
const radialToggle = radial.find((el) => el.dataset.profileNotebook !== undefined);
const beforeRadial = calls.length;
radialToggle.click();
await settle();
out.radial = {
  calls: calls.slice(beforeRadial),
  pressed: radialToggle.getAttribute('aria-pressed'),
  title: radial.children[0].children[0].textContent,
  wTitle: cards.find((c) => c.dataset.panel === 'profile-w').children[0].children[0].textContent,
  notes: physics.notes('profile-r').title,
};

// The palette is a repaint: no request.
const beforePaint = calls.length;
state.set({ palette: 'cividis' }, { silent: true });
physics.repaint();
out.repaint = { calls: calls.length - beforePaint,
  palettes: [...new Set(rendered.slice(-3).map(([, opts]) => opts.palette))] };

// Events-only kind: the hit cards go, B3 joins.
physics.reset();
out.cleared = cards.filter((c) => !c.hidden).length;
physics.applyPlan(plans.single_shower_events);
out.eventsHidden = Object.fromEntries(cards.map((c) => [c.dataset.panel, c.hidden]));

// A stale two-shower experiment: shut cards say why and offer the rebuild.
const stale = structuredClone(exps.two_shower_hits);
const notice = 'Built by an earlier release (derived tables v1); rebuild it (Admin Settings › Rebuild derived tables).';
stale.capabilities.derived = { version: 1, current: 2, status: 'stale', notice };
for (const id of ['profile-w', 'profile-r']) { stale.capabilities.panels[id] = false; stale.capabilities.reasons[id] = notice; }
physics.applyPlan(caps.page1Plan(stale));
const shut = cards.find((c) => c.dataset.panel === 'profile-w');
const message = shut.find((el) => el.classList.contains('card-error'));
const rebuild = message.find((el) => el.dataset.openAdmin !== undefined);
rebuild.click();
out.stale = {
  hidden: message.hidden,
  text: message.children[0].textContent,
  kind: message.dataset.kind,
  opened,
  exportDisabled: shut.find((el) => el.dataset.export !== undefined).disabled,
  notes: physics.notes('profile-w'),
  key: physics.keyOf('profile-w'),
  showerToggles: cards.flatMap((c) => c.findAll((el) => el.dataset.physicsShower !== undefined && el.tagName === 'BUTTON'))
    .map((el) => el.parent.hidden),
  shutControls: shut.findAll((el) => el.dataset.profileAxis !== undefined || el.dataset.physicsShower !== undefined)
    .map((el) => el.parent.hidden),
};
out.errors = errors;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def section_results() -> dict:
    fixtures = {
        "profilesW": _path("profiles_single_w"), "profilesNative": _path("profiles_single_native"),
        "response": _path("response_single_hits"), "responseEvents": _path("response_single_events"),
        "b3": _path("b3_single_notebook"), "distU": _path("distribution_single_u"),
        "distPhi": _path("distribution_single_phi"), "correlation": _path("correlation_single_local"),
        "statistics": _path("statistics_single_local"),
    }
    return _run(_SECTION_SCRIPT, [
        (JS / "physics_section.js").as_uri(), (JS / "state.js").as_uri(), (JS / "capabilities.js").as_uri(),
        _path("experiments"), fixtures,
    ])


def test_a_single_shower_request_carries_no_second_shower_axis(section_results):
    for card, pair in section_results["requests"].items():
        params = pair["single"]["params"]
        for key in ("e2_min", "e2_max", "d_min", "d_max", "include_undefined_d", "shower"):
            assert params.get(key) is None, (card, key)
        assert params["table_name"] == "single_hits"
        two = pair["two"]["params"]
        assert two["include_undefined_d"] is False and two["d_max"] == 900, card


def test_cards_that_read_one_response_build_one_request(section_results):
    requests = section_results["requests"]
    key = lambda r: json.dumps([r["route"], sorted((k, v) for k, v in r["params"].items() if v is not None)])  # noqa: E731
    assert key(requests["profile-w"]["single"]) == key(requests["profile-r"]["single"])
    assert len({key(requests[c]["two"]) for c in ("response-b1", "response-b2", "response-res")}) == 1
    assert requests["response-b3"]["single"]["route"] == "/api/energy-distribution"
    assert requests["response-b3"]["single"]["params"]["slice_by"] == "momentum"
    assert requests["profile-w"]["two"]["params"]["shower"] == "both"
    assert requests["correlation"]["single"]["params"]["coord_system"] == "local"
    assert requests["correlation"]["single"]["params"]["energy_scale"] == "linear"
    assert requests["distribution"]["single"]["params"] | {} == {
        **requests["distribution"]["single"]["params"], "quantity": "theta", "weighting": "shower"}
    assert {r["single"]["abortKey"] for r in requests.values()} == {
        "physics-profile", "physics-response", "physics-b3", "physics-distribution",
        "physics-correlation", "physics-statistics"}


def test_card_requests_follow_their_controls(section_results):
    assert section_results["native"]["params"]["depth"] == "native"
    assert section_results["native"]["params"].get("notebook") is None, "the notebook convention is w-only (422)"
    assert section_results["notebook"]["params"]["notebook"] is True
    assert section_results["bins"]["params"]["p_slices"] == "bins"
    hit = section_results["hitQuantity"]["params"]
    assert hit["quantity"] == "u" and hit.get("weighting") is None
    # The event-level kind has no hit quantities: back to the first it offers.
    assert section_results["eventsQuantity"]["params"]["quantity"] == "theta"
    assert section_results["noTable"] is None
    reconciled = section_results["reconciled"]
    # A frame the experiment does not offer falls back in the order local, trans, lab;
    # an offered one is kept.
    assert reconciled["corrCoord"] == "trans" and reconciled["statCoord"] == "lab"
    assert reconciled["profileShower"] == "both"


def test_card_options_name_the_axis_mode_and_filters(section_results):
    options = section_results["options"]
    assert options["native"]["axis"] == "kt" and options["w"]["axis"] == "w" and options["r"]["axis"] == "r"
    assert options["res"] == {"palette": "viridis", "card": "response-res", "mode": "resolution",
                              "shower": "b", "quantity": "response_ratio"}
    assert options["dist"]["yScale"] == "log" and options["dist"]["quantity"] == "u"
    assert section_results["exportMeta"]["coord_system"] == "local"


def test_every_card_has_the_page_anatomy(section_results):
    anatomy = {card["panel"]: card for card in section_results["anatomy"]}
    assert list(anatomy) == ALL_PHYSICS
    for card_id, card in anatomy.items():
        assert card["hidden"] is True, "no card shows before a plan"
        assert card["firstInspect"] == card_id and card["firstControls"] == "inspector"
        assert card["plotId"] == f"plot-{card_id}" and card["titleId"] == f"title-{card_id}"
        assert not card_id.startswith(("event-", "compare-"))
        if card_id == "statistics":
            assert card["lastExport"] is None and card["exportTitle"] is None and card["wide"]
        else:
            assert card["lastExport"] == card_id
            assert "plot area only" in card["exportTitle"]
    assert section_results["observer"] == {"root": "MAIN", "rootMargin": "0px", "threshold": 0}


def test_a_single_shower_section_loads_each_response_once(section_results):
    hidden = section_results["singleHidden"]
    # Every card: the full-width response grid too, which holds the 1 GeV bins.
    assert [c for c, h in hidden.items() if h] == []
    assert all(section_results["showerControls"]), "no shower toggle for one shower"
    calls = section_results["calls"]
    routes = sorted(c.split("?")[0] for c in calls)
    assert routes == ["/api/correlations", "/api/distributions", "/api/energy-distribution", "/api/profiles",
                      "/api/response", "/api/statistics"]
    for call in calls:
        for key in ("e2_min", "d_min", "include_undefined_d", "shower="):
            assert key not in call, call
    rendered = section_results["rendered"]
    assert rendered["plot-profile-w"]["axis"] == "w" and rendered["plot-profile-r"]["axis"] == "r"
    assert [rendered[f"plot-response-{p}"]["mode"] for p in ("b1", "b2", "res")] == ["b1", "b2", "resolution"]
    assert sorted(section_results["created"]) == sorted(f"plot-{c}" for c, h in hidden.items() if not h)
    assert all(ok for _, ok in section_results["renderedIds"])
    assert section_results["errors"] == []


def test_every_drawn_card_has_notes_and_an_export_target(section_results):
    notes = section_results["notes"]
    for card_id in ("profile-w", "profile-r", "response-b1", "response-b2", "response-res", "distribution",
                    "correlation", "statistics"):
        assert notes[card_id] and notes[card_id]["lines"], card_id
        for line in notes[card_id]["lines"]:
            assert not HYPHEN_NUMBER.search(line), (card_id, line)
    assert notes["response-b3"]["title"] == "Response vs. Incident Momentum p"
    targets = section_results["exportTargets"]
    assert targets["profile"] is True and targets["meta"]["coord_system"] == "local"
    assert targets["statistics"] is None and targets["foreign"] is True and targets["b3"] is True
    # A warning the card's drawer states is not repeated on the banner.
    said = " ".join(line for card in notes.values() if card for line in card["lines"])
    for warning in section_results["warnings"]:
        assert " ".join(warning.split()) not in said, warning


def test_card_controls_reload_or_repaint(section_results):
    assert section_results["quantityOptions"] == ["theta", "phi", "p", "u", "v", "w", "energy"]
    after = section_results["afterQuantity"]
    assert len(after) == 1 and after[0].startswith("/api/distributions") and "quantity=u" in after[0]
    assert section_results["afterLog"]["calls"] == 0
    assert section_results["afterLog"]["opts"]["yScale"] == "log"
    assert len(section_results["afterNative"]) == 1 and "depth=native" in section_results["afterNative"][0]
    assert section_results["notebookDisabled"]["disabled"] is True
    assert "native layers" in section_results["notebookDisabled"]["title"]
    # The card is titled as its Details drawer titles a native-depth profile (panel_notes.js).
    assert section_results["profileTitle"] == "Longitudinal Profile (native layers)"
    assert section_results["repaint"]["calls"] == 0
    assert section_results["repaint"]["palettes"] == ["cividis"]


def test_each_profile_card_owns_its_notebook_flag(section_results):
    profiles = section_results["profiles"]
    plain = profiles["plain"]
    assert plain["profile-w"]["params"] == plain["profile-r"]["params"]
    assert plain["profile-w"]["abortKey"] == plain["profile-r"]["abortKey"] == "physics-profile"
    # The longitudinal card's flag no longer reaches the radial card.
    w_only = profiles["wOnly"]
    assert w_only["profile-w"]["params"]["notebook"] is True
    assert w_only["profile-r"]["params"].get("notebook") is None
    # Two responses: each its own abort key, so neither request supersedes the other.
    assert (w_only["profile-w"]["abortKey"], w_only["profile-r"]["abortKey"]) == (
        "physics-profile-w", "physics-profile-r")
    assert w_only["profile-w"]["title"] == "Longitudinal Profile along w (notebook convention)"
    assert w_only["profile-r"]["title"] == "Radial Profile along ρ"
    r_only = profiles["rOnly"]
    assert r_only["profile-r"]["params"]["notebook"] is True and r_only["profile-r"]["params"]["depth"] == "w"
    assert r_only["profile-w"]["params"].get("notebook") is None
    assert r_only["profile-r"]["title"] == "Radial Profile along ρ (notebook convention)"
    # Equal parameters again: one shared request under the group's key.
    both = profiles["both"]
    assert both["profile-w"]["params"] == both["profile-r"]["params"]
    assert both["profile-r"]["abortKey"] == "physics-profile"
    # The convention is defined along w: the radial card asks along w even beside native layers.
    native_r = profiles["nativeR"]
    assert native_r["profile-w"]["params"]["depth"] == "native" and native_r["profile-r"]["params"]["depth"] == "w"
    assert native_r["profile-w"]["title"] == "Longitudinal Profile (native layers)"
    native = profiles["native"]
    assert native["profile-r"]["params"]["depth"] == "native" and native["profile-r"]["abortKey"] == "physics-profile"


def test_the_radial_card_says_when_the_notebook_convention_applies(section_results):
    radial = section_results["radial"]
    # Its own request (along w, under the convention); the longitudinal card is not asked again.
    assert len(radial["calls"]) == 1, radial["calls"]
    assert "notebook=true" in radial["calls"][0] and "depth=w" in radial["calls"][0]
    assert radial["pressed"] == "true"
    assert radial["title"] == "Radial Profile along ρ (notebook convention)"
    assert radial["notes"] == radial["title"]
    assert radial["wTitle"] == "Longitudinal Profile (native layers)"


def test_the_response_grid_card_carries_its_fit_table_and_key_counts(section_results):
    hosts = section_results["b3Hosts"]
    # Heading, plot, then the sparse note and the fit table, as plot 4 has them on the energy card.
    assert hosts["order"][-2:] == ["energy-sparse-response-b3", "fit-table-response-b3"]
    assert hosts["tableTag"] == "TABLE" and "fitted μ and σ" in hosts["table"]
    assert hosts["sparse"] == [["P", "2 series below N = 15 drawn as event strips."],
                               ["P", "1 low-N curve clipped at the axis top."]]
    assert hosts["sparseHidden"] is False
    # Plot 4 draws the notebook's windows on a single shower; this card opens on the 1 GeV bins.
    assert "p_slices=bins" in hosts["request"]


def test_the_events_kind_shows_only_its_event_level_cards(section_results):
    hidden = section_results["eventsHidden"]
    assert [c for c, h in hidden.items() if not h] == [
        "response-b1", "response-b2", "response-res", "response-b3", "distribution"]


def test_a_stale_card_says_why_and_offers_the_rebuild(section_results):
    stale = section_results["stale"]
    assert stale["hidden"] is False and stale["kind"] == "disabled"
    assert stale["text"].startswith("Built by an earlier release")
    assert stale["opened"] == 1
    assert stale["exportDisabled"] is True
    assert stale["key"] is None, "a shut card never loads"
    assert stale["notes"]["sections"][0]["lines"] == [stale["text"]]
    # Two showers: the shower toggles are back, except on the shut cards.
    assert not all(stale["showerToggles"])
    assert stale["shutControls"] and all(stale["shutControls"])


# ------------------------------------------------- the section's lifecycle --

_LIFECYCLE_SCRIPT = _FAKE_DOM + r"""
const [sectionUrl, stateUrl, capsUrl, cataloguePath, fixturePaths] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const fixtures = loadAll(fixturePaths);
// A fetch the script answers by hand: each request waits until it is told
// how to settle, and an abort that still reaches it rejects it.
const requests = [];
globalThis.fetch = (url, { signal } = {}) => new Promise((resolve, reject) => {
  const u = new URL(url);
  const entry = { path: u.pathname, search: u.search, aborted: false, resolve, reject };
  signal?.addEventListener?.('abort', () => {
    entry.aborted = true;
    const error = new Error('aborted');
    error.name = 'AbortError';
    reject(error);
  });
  requests.push(entry);
});
const bodyOf = (entry) => ({
  '/api/statistics': fixtures.statistics, '/api/response': fixtures.response,
  '/api/energy-distribution': fixtures.b3,
}[entry.path] ?? {});
const answer = (entry, body = bodyOf(entry)) => entry.resolve({ ok: true, status: 200, json: async () => body });
const refuse = (entry, status, detail) => entry.resolve({ ok: false, status, statusText: 'x', json: async () => ({ detail }) });
const lose = (entry) => entry.reject(new TypeError('Failed to fetch'));
const last = (path) => [...requests].reverse().find((r) => r.path === path);

const { PhysicsSection } = await import(sectionUrl);
const { State } = await import(stateUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const plans = Object.fromEntries(Object.entries(exps).map(([k, e]) => [k, caps.page1Plan(e)]));

const drawn = [];
class FakePanel {
  constructor(element) { this.element = element; }
  render(payload, opts) { this.lastPayload = payload; this.lastOpts = opts; drawn.push([this.element.id, payload]); }
  clear() { this.lastPayload = null; }
  relayout() {}
  setBusy(busy) { this.element.classList.toggle('is-busy', busy); }
}
class FakeGridPanel extends FakePanel {
  renderTable(host) { const t = document.createElement('table'); t.textContent = 'fit'; host.replaceChildren(t); }
  sparseLines() { return ['3 low-N series.']; }
}
const panelClasses = Object.fromEntries(['ProfilePanel', 'ResponsePanel', 'ResponseGridPanel', 'DistributionPanel',
  'CorrelationPanel', 'StatisticsPanel'].map((name) => [name, name === 'ResponseGridPanel' ? FakeGridPanel : FakePanel]));

window.location.hash = '';
const state = new State();
state.restrictAxes(caps.SINGLE_SHOWER_AXES);
state.set({ table_name: 'single_hits' }, { silent: true });
state.adoptSnappedBounds(exps.single_shower_hits.bounds);
const section = document.createElement('section');
const errors = [];
const physics = new PhysicsSection(section, {
  state, panelClasses, root: 'MAIN', onError: (error, context) => errors.push([context, error.message]),
});
physics.applyPlan(plans.single_shower_hits);
const card = (id) => section.children.find((c) => c.dataset.panel === id);
const stats = card('statistics');
const message = stats.find((el) => el.classList.contains('card-error'));
const busy = () => ({ loading: stats.classList.contains('is-loading'),
  busy: stats.find((el) => el.id === 'plot-statistics').classList.contains('is-busy') });
const out = {};

// ---- a superseded load leaves the newer load's busy state alone
FakeObserver.last.show([stats]);
await settle();
answer(last('/api/statistics'));
await settle();
state.set({ e1_min: 5 }, { silent: true });
const first = physics.refresh();
await settle();
out.firstPending = busy();
state.set({ e1_min: 8 }, { silent: true });
const second = physics.refresh();
await settle();
out.secondPending = { ...busy(), aborted: requests.filter((r) => r.path === '/api/statistics').map((r) => r.aborted) };
answer(last('/api/statistics'));
await Promise.allSettled([first, second]);
await settle();
out.settled = busy();

// ---- a fault that may pass: its error, a Retry, and asked again on the next refresh
state.set({ e1_min: 9 }, { silent: true });
const failing = physics.refresh().catch((e) => e.message);
await settle();
lose(last('/api/statistics'));
out.lost = { reported: await failing, text: message.children[0]?.textContent, kind: message.dataset.kind,
  retry: Boolean(message.find((el) => el.dataset.retry === 'statistics')) };
const beforeRetry = requests.length;
message.find((el) => el.dataset.retry === 'statistics').click();
await settle();
out.retried = requests.slice(beforeRetry).map((r) => r.path);
refuse(last('/api/statistics'), 503, 'The database is restarting.');
await settle();
out.serverError = { text: message.children[0]?.textContent, retry: Boolean(message.find((el) => el.dataset.retry)) };
const beforeRefresh = requests.length;
const again = physics.refresh().catch(() => null);
await settle();
out.refreshAsked = requests.length - beforeRefresh;
refuse(last('/api/statistics'), 422, 'Not available for this experiment: no hits.');
await again;
await settle();
out.refused = { text: message.children[0]?.textContent, retry: Boolean(message.find((el) => el.dataset.retry)) };
const beforeRefused = requests.length;
await physics.refresh().catch(() => null);
out.refusedAsked = requests.length - beforeRefused;

// ---- a response that lands after an experiment switch draws nothing and is not kept
state.set({ e1_min: 10 }, { silent: true });
const late = physics.refresh().catch(() => null);
await settle();
// The headers are in, so the abort no longer reaches the request; the body comes later.
let releaseBody;
const body = new Promise((resolve) => { releaseBody = resolve; });
last('/api/statistics').resolve({ ok: true, status: 200, json: () => body });
await settle();
const drawnBefore = drawn.length;
state.set({ table_name: 'experiment_baseline' }, { silent: true });
physics.reset();
out.resetBusy = busy();
releaseBody({ late: true });
await late;
await settle();
out.late = { drawn: drawn.slice(drawnBefore).map(([id]) => id), cached: physics.cache.size,
  messageHidden: message.hidden };

// ---- plot 4's link: the full-width card, scrolled to, on the 1 GeV bins
state.set({ table_name: 'single_hits' }, { silent: true });
physics.applyPlan(plans.single_shower_hits);
const b3 = card('response-b3');
let scrolled = null;
b3.scrollIntoView = (options) => { scrolled = options; };
const windows = b3.find((el) => el.dataset.b3Slices === 'notebook');
windows.click();
out.beforeReveal = b3.find((el) => el.dataset.b3Slices === 'bins').classList.contains('is-active');
out.revealed = physics.reveal('response-b3', { b3Slices: 'bins' });
out.reveal = { scrolled, binsActive: b3.find((el) => el.dataset.b3Slices === 'bins').classList.contains('is-active'),
  windowsActive: windows.classList.contains('is-active') };
FakeObserver.last.show([b3]);
await settle();
out.revealRequest = last('/api/energy-distribution')?.search ?? null;
answer(last('/api/energy-distribution'));
await settle();
out.b3Table = b3.find((el) => el.id === 'fit-table-response-b3').textContent;
out.b3Sparse = b3.find((el) => el.id === 'energy-sparse-response-b3').textContent;
physics.reset();
out.b3AfterReset = { table: b3.find((el) => el.id === 'fit-table-response-b3').children.length,
  sparseHidden: b3.find((el) => el.id === 'energy-sparse-response-b3').hidden };
out.hiddenReveal = (() => { physics.applyPlan(plans.single_shower_events); return physics.reveal('profile-w'); })();

// ---- the event-level kind's Events count: one shared request with the response cards
state.set({ table_name: 'single_events' }, { silent: true });
physics.reset();
physics.applyPlan(plans.single_shower_events);
const beforeCount = requests.length;
const count = physics.payloadOf('response-b1');
const b1 = card('response-b1');
FakeObserver.last.show([b1, card('response-b2')]);
await settle();
out.countRequests = requests.slice(beforeCount).map((r) => r.path);
answer(last('/api/response'), fixtures.responseEvents);
out.count = (await count)?.n_events ?? null;
await settle();
out.countDrawn = drawn.filter(([id]) => id === 'plot-response-b1' || id === 'plot-response-b2').length;
out.shutCount = await (async () => {
  const stale = caps.page1Plan(exps.single_shower_events);
  stale.disabled = { 'response-b1': 'shut' };
  physics.applyPlan(stale);
  return physics.payloadOf('response-b1');
})();
out.errors = errors;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def lifecycle_results() -> dict:
    fixtures = {"statistics": _path("statistics_single_local"), "response": _path("response_single_hits"),
                "responseEvents": _path("response_single_events"), "b3": _path("b3_single_notebook")}
    return _run(_LIFECYCLE_SCRIPT, [
        (JS / "physics_section.js").as_uri(), (JS / "state.js").as_uri(), (JS / "capabilities.js").as_uri(),
        _path("experiments"), fixtures,
    ])


def test_a_superseded_load_never_clears_the_busy_state_of_the_load_that_replaced_it(lifecycle_results):
    assert lifecycle_results["firstPending"] == {"loading": True, "busy": True}
    second = lifecycle_results["secondPending"]
    # The first filter change's request was aborted by the second; the card is still busy with it.
    assert second["aborted"][-2:] == [True, False]
    assert (second["loading"], second["busy"]) == (True, True)
    assert lifecycle_results["settled"] == {"loading": False, "busy": False}


def test_a_transient_failure_shows_its_error_offers_a_retry_and_is_asked_again(lifecycle_results):
    lost = lifecycle_results["lost"]
    assert "could not be reached" in lost["text"] and "out of step" not in lost["text"]
    assert lost["kind"] == "error" and lost["retry"] is True
    assert "could not be reached" in lost["reported"]
    assert lifecycle_results["retried"] == ["/api/statistics"]
    assert lifecycle_results["serverError"] == {"text": "The database is restarting.", "retry": True}
    assert lifecycle_results["refreshAsked"] == 1


def test_a_refusal_is_shown_without_a_retry_and_not_asked_again(lifecycle_results):
    assert lifecycle_results["refused"] == {"text": "Not available for this experiment: no hits.", "retry": False}
    assert lifecycle_results["refusedAsked"] == 0


def test_a_response_landing_after_an_experiment_switch_draws_nothing_and_is_not_kept(lifecycle_results):
    assert lifecycle_results["resetBusy"] == {"loading": False, "busy": False}
    late = lifecycle_results["late"]
    assert late["drawn"] == [] and late["cached"] == 0 and late["messageHidden"] is True


def test_plot_4s_link_reveals_the_full_width_card_on_its_1_gev_bins(lifecycle_results):
    assert lifecycle_results["beforeReveal"] is False
    assert lifecycle_results["revealed"] is True
    reveal = lifecycle_results["reveal"]
    assert reveal["scrolled"] == {"block": "start"}
    assert reveal["binsActive"] is True and reveal["windowsActive"] is False
    assert "p_slices=bins" in lifecycle_results["revealRequest"]
    assert lifecycle_results["b3Table"] == "fit" and lifecycle_results["b3Sparse"] == "3 low-N series."
    assert lifecycle_results["b3AfterReset"] == {"table": 0, "sparseHidden": True}
    # A card not on show is not revealed.
    assert lifecycle_results["hiddenReveal"] is False


def test_the_event_level_count_shares_the_response_cards_request(lifecycle_results):
    assert lifecycle_results["countRequests"] == ["/api/response"]
    assert lifecycle_results["count"] == 286
    assert lifecycle_results["countDrawn"] == 2
    assert lifecycle_results["shutCount"] is None


# ------------------------------------- clearing, rebuild polling, names --

_CLEAR_SCRIPT = _FAKE_DOM + r"""
const [projectionUrl, energyUrl, adminUrl, filenameUrl] = JSON.parse(process.argv[1]);
const zrCalls = [];
const charts = [];
globalThis.echarts = {
  init: (element) => {
    const chart = {
      cleared: 0, getDom: () => element,
      clear() { this.cleared += 1; },
      setOption() {}, resize() {}, getWidth: () => 600, getHeight: () => 330, on() {}, off() {},
      getZr: () => ({ on: (event) => zrCalls.push(['on', event]), off: (event) => zrCalls.push(['off', event]) }),
      convertFromPixel: () => [0, 0], dispatchAction() {},
    };
    charts.push(chart);
    return chart;
  },
};
const out = {};

// ---- ProjectionPanel.clear: the picture, what it retains and its pointer handlers
const { ProjectionPanel } = await import(projectionUrl);
byId('plot-xy');
const projection = new ProjectionPanel('plot-xy', { isometric: true });
projection.attachNavigation();
projection.tooltipHandler = () => {};
Object.assign(projection, { payload: { axes: {} }, raster: {}, lastOpts: { palette: 'viridis' }, extent: {},
  view: { col: [0, 1], row: [0, 1] }, viewKey: 'lab|single_hits|', laidOut: { width: 1, height: 1 }, liveGrid: {} });
const attached = zrCalls.filter(([kind]) => kind === 'on').length;
projection.clear();
out.projection = {
  attached,
  detached: zrCalls.filter(([kind]) => kind === 'off').map(([, event]) => event).sort(),
  cleared: charts[0].cleared,
  retained: ['payload', 'raster', 'lastOpts', 'extent', 'view', 'viewKey', 'laidOut', 'liveGrid', 'drag',
    'wheelHandler', 'downHandler', 'moveHandler', 'upHandler', 'tooltipHandler'].filter((key) => projection[key] != null),
  view: projection.currentView(),
  roi: projection.autoFitRoI(),
};

// ---- EnergyPanel.clear: the picture, the fit table and the card's notices
const { EnergyPanel } = await import(energyUrl);
byId('plot-energy'); byId('fit-table'); byId('energy-sparse');
const energy = new EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
byId('fit-table').append(document.createElement('table'));
byId('energy-sparse').append(document.createElement('p'));
byId('energy-sparse').hidden = false;
Object.assign(energy, { lastPayload: {}, lastOpts: {}, laidOut: { width: 1, height: 1 }, liveGrid: {}, lastNotices: ['x'] });
energy.clear();
energy.relayout();
out.energy = {
  cleared: charts[1].cleared,
  retained: ['lastPayload', 'lastOpts', 'liveGrid'].filter((key) => energy[key] != null),
  notices: energy.lastNotices, table: byId('fit-table').children.length,
  sparse: byId('energy-sparse').children.length, sparseHidden: byId('energy-sparse').hidden,
};

// ---- pollRebuilds: a finished rebuild is not polled again
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...rest) => realSetTimeout(fn, ms === 1500 ? 0 : ms, ...rest);
const polls = [];
const script = { a: ['done'], b: ['running', 'running', 'running', 'done'] };
globalThis.fetch = async (url) => {
  const id = new URL(url).pathname.split('/').pop();
  polls.push(id);
  const status = script[id].length > 1 ? script[id].shift() : script[id][0];
  return { ok: true, status: 200, json: async () => ({ job_id: id, status, progress: 0.5 }) };
};
const { AdminModal } = await import(adminUrl);
const admin = Object.create(AdminModal.prototype);
let ingested = 0;
Object.assign(admin, {
  rebuilds: new Map([['exp_a', { job: { job_id: 'a', status: 'running' } }],
                     ['exp_b', { job: { job_id: 'b', status: 'queued' } }]]),
  rebuildTimer: null, rebuildLoop: null, shell: { isOpen: true },
  renderRebuild() {}, setStatus() {}, onIngested: async () => { ingested += 1; },
});
admin.pollRebuilds();
for (let i = 0; i < 20; i += 1) await settle();
globalThis.setTimeout = realSetTimeout;
out.polls = { a: polls.filter((id) => id === 'a').length, b: polls.filter((id) => id === 'b').length, ingested,
  left: admin.rebuilds.size, timer: admin.rebuildTimer };

// ---- a profile under the notebook's convention is named so
const { figureName } = await import(filenameUrl);
const stub = { filterAxes: null, isTouched: () => false, get: (key) => (key === 'frame' ? 'lab' : null) };
out.names = {
  notebook: figureName('profile-r', 'svg', { state: stub, spatial: false, meta: { table_name: 'x', notebook: true } }),
  plain: figureName('profile-r', 'svg', { state: stub, spatial: false, meta: { table_name: 'x', notebook: false } }),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def clear_results() -> dict:
    return _run(_CLEAR_SCRIPT, [
        (JS / "panels" / "projection.js").as_uri(), (JS / "panels" / "energy.js").as_uri(),
        (JS / "controls" / "admin.js").as_uri(), (JS / "export" / "filename.js").as_uri(),
    ])


def test_a_cleared_projection_panel_keeps_nothing_to_repaint(clear_results):
    projection = clear_results["projection"]
    assert projection["cleared"] == 1
    assert projection["retained"] == []
    # Every pointer handler is detached (they read the payload): wheel, drag, release, readout.
    assert projection["attached"] == 5
    assert projection["detached"] == ["globalout", "mousedown", "mousemove", "mousemove", "mouseup", "mousewheel"]
    assert projection["view"] is None and projection["roi"] == "empty"


def test_a_cleared_energy_panel_keeps_no_picture_table_or_notice(clear_results):
    energy = clear_results["energy"]
    assert energy["cleared"] == 1 and energy["retained"] == [] and energy["notices"] == []
    assert energy["table"] == 0 and energy["sparse"] == 0 and energy["sparseHidden"] is True


def test_a_finished_rebuild_is_not_polled_again(clear_results):
    polls = clear_results["polls"]
    # Rebuild a finishes on the first tick and is never asked about again; b is
    # followed until it finishes. Each finished rebuild reloads the catalogue once.
    assert polls["a"] == 1 and polls["b"] == 4
    assert polls["ingested"] == 2 and polls["left"] == 0 and polls["timer"] is None


def test_a_notebook_profile_figure_is_named_so(clear_results):
    assert "_notebook_" in clear_results["names"]["notebook"]
    assert "notebook" not in clear_results["names"]["plain"]


# ------------------------------------------------------- frame wording --

_WORDING_SCRIPT = _FAKE_DOM + r"""
const [framesUrl, disclosureUrl, fixturePaths, labelsUrl, notesUrl, stateUrl, capsUrl, captionUrl] = JSON.parse(process.argv[1]);
const caption = await import(captionUrl);
const fixtures = loadAll(fixturePaths);
const fv = await import(framesUrl);
const ds = await import(disclosureUrl);
const out = {};
const { singleLocal, singleLab, baseLab } = fixtures;
out.showers = { singleLocal: ds.showersPerEvent(singleLocal), singleLab: ds.showersPerEvent(singleLab),
  baseLab: ds.showersPerEvent(baseLab), stated: ds.showersPerEvent(baseLab, 1) };
out.footnotes = { local: fv.footnotes(singleLocal, { isometric: {} }), lab: fv.footnotes(singleLab),
  base: fv.footnotes(baseLab) };
out.stated = fv.footnotes(singleLocal, { isometric: {}, nShowers: 1 });
out.disclosure = {};
for (const id of ['xy', 'yz', 'xz']) out.disclosure[id] = ds.figureDisclosure(singleLocal, id, null, { isometric: true });
out.disclosureLab = ds.figureDisclosure(singleLab, 'xy', null, {});
out.legend = { local: fv.exportLegend('xy', singleLocal), lab: fv.labLegend(singleLab) };
out.captions = { trans: fv.frameCaption('trans', 1), local: fv.frameCaption('local', 1), lab: fv.frameCaption('lab', 1),
  twoTrans: fv.frameCaption('trans', 2) };
out.tags = { single: fv.showerTag(singleLocal.frame, 1), two: fv.showerTag({ n_events: 7, n_showers: 14 }, 2) };
out.channel = {
  single: fv.channelCaption({ channel: 'density', frame: 'local', payload: singleLocal, nShowers: 1 }),
  two: fv.channelCaption({ channel: 'density', frame: 'local', payload: singleLocal, nShowers: 2 }),
};
out.titles = Object.fromEntries(['lab', 'trans', 'local'].flatMap((kind) => ['xy', 'yz', 'xz']
  .map((id) => [`${kind}|${id}`, [fv.panelTitle(id, kind, 1), fv.panelTitle(id, kind)]])));
const labels = await import(labelsUrl);
out.frameLabels = Object.fromEntries(['lab', 'trans', 'local', 'canonical']
  .map((f) => [f, [labels.frameLabel(f, 1), labels.frameLabel(f)]]));
out.c9 = ds.negativeDepthSentence(singleLocal.frame.negative_w);
out.c9Unavailable = ds.negativeDepthSentence({ available: false, summary: 'Negative-depth counts are unavailable: stale.' });
out.summary = singleLocal.frame.negative_w.summary;
// The spatial panels' drawers: titled and worded for one shower, from the
// experiment's capabilities or, failing those, from the payload.
const pn = await import(notesUrl);
const single = { capabilities: { n_showers: 1 } };
out.projectionNotes = Object.fromEntries(['xy', 'yz', 'xz'].map((id) => {
  const n = pn.projectionNotes({ payload: singleLocal, panelId: id, isometric: {}, experiment: single });
  return [id, { title: n.title, expected: fv.panelTitle(id, 'local', 1), lines: n.sections.flatMap((x) => x.lines) }];
}));
out.projectionTitleFromPayload = pn.projectionNotes({ payload: singleLocal, panelId: 'yz', isometric: {} }).title;
// The Selection line names the single-shower frames too: it goes into a caption.
const { State } = await import(stateUrl);
const caps = await import(capsUrl);
window.location.hash = '';
const st = new State();
st.restrictAxes(caps.SINGLE_SHOWER_AXES);
const transPayload = { ...singleLocal, frame: { ...singleLocal.frame, kind: 'trans' } };
out.selection = {
  local: Object.fromEntries(['xy', 'yz', 'xz'].map((id) => [id,
    pn.projectionNotes({ payload: singleLocal, panelId: id, isometric: {}, state: st,
      experiment: { table_name: 'single_hits', capabilities: { n_showers: 1 } } })])
    .map(([id, n]) => [id, { selection: n.sections[0].lines, all: n.sections.flatMap((x) => x.lines) }])),
  fromPayload: pn.projectionNotes({ payload: singleLocal, panelId: 'xy', isometric: {}, state: st }).sections[0].lines[0],
  trans: caption.describeSelection(st, { table_name: 'single_hits', capabilities: { n_showers: 1 } },
    transPayload.selection, transPayload.frame, null),
  twoLocal: caption.describeSelection(st, { table_name: 'x', capabilities: { n_showers: 2 } },
    null, { kind: 'local' }, null),
  twoTrans: caption.describeSelection(st, null, { n_events_no_d: 3 }, { kind: 'trans' }, null),
};
out.projectionTitleTwo = pn.projectionNotes({ payload: baseLab, panelId: 'yz', isometric: {} }).title;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def wording_results() -> dict:
    fixtures = {"singleLocal": _path("projections_single_local"), "singleLab": _path("projections_single_lab"),
                "baseLab": _path("projections_base_lab")}
    return _run(_WORDING_SCRIPT, [(JS / "frame_views.js").as_uri(), (JS / "export" / "disclosure.js").as_uri(),
                                  fixtures, (JS / "labels.js").as_uri(), (JS / "panel_notes.js").as_uri(),
                                  (JS / "state.js").as_uri(), (JS / "capabilities.js").as_uri(),
                                  (JS / "export" / "caption.js").as_uri()])


TWO_SHOWER_PHRASES = ("shower B", "A–B", "A-B", "⟨D⟩", "D is the absolute-frame", "Both showers", "both showers",
                      "Diamond marks", "two showers")


def test_single_shower_drawers_are_titled_and_worded_for_one_shower(wording_results):
    for panel_id, notes in wording_results["projectionNotes"].items():
        assert notes["title"] == notes["expected"], panel_id
        assert "D-Frame" not in notes["title"] and "Shower-Aligned" in notes["title"], notes["title"]
        for line in notes["lines"]:
            for phrase in TWO_SHOWER_PHRASES:
                assert phrase not in line, (panel_id, phrase, line)
    assert wording_results["projectionTitleFromPayload"] == wording_results["projectionNotes"]["yz"]["title"]
    assert wording_results["projectionTitleTwo"] == "YZ Projection — Longitudinal Evolution"


def test_the_single_shower_selection_line_names_its_own_frames(wording_results):
    selection = wording_results["selection"]
    for panel_id, notes in selection["local"].items():
        line = notes["selection"][0]
        assert "Shower-Aligned, Local (shower-fixed, R(θ, φ))" in line, (panel_id, line)
        # The whole drawer, which is what goes into a manuscript caption.
        for text in notes["all"]:
            assert "D-Frame" not in text and "legacy" not in text, (panel_id, text)
    # Without the experiment's capabilities the response says one shower per event.
    assert "Shower-Aligned, Local" in selection["fromPayload"] and "D-Frame" not in selection["fromPayload"]
    assert "Translated (each shower from its own entry point P₀, no rotation)" in selection["trans"]
    assert "legacy" not in selection["trans"]
    # Two showers keep their names.
    assert "Separation-Aligned (D-Frame), Local" in selection["twoLocal"]
    assert "per-shower translated frame (legacy" in selection["twoTrans"]


def test_showers_per_event_is_read_from_the_payload_or_stated(wording_results):
    assert wording_results["showers"] == {"singleLocal": 1, "singleLab": 1, "baseLab": 2, "stated": 1}


def test_single_shower_footnotes_name_no_partner_and_no_separation(wording_results):
    texts = list(wording_results["footnotes"]["local"].values()) + list(wording_results["footnotes"]["lab"].values())
    texts += [line for lines in wording_results["disclosure"].values() for line in lines]
    texts += wording_results["disclosureLab"] + list(wording_results["legend"].values())
    texts += [wording_results["captions"][k] for k in ("trans", "local", "lab")]
    texts += [wording_results["tags"]["single"], wording_results["channel"]["single"]]
    for text in texts:
        for phrase in TWO_SHOWER_PHRASES:
            assert phrase not in text, (phrase, text)
        assert not HYPHEN_NUMBER.search(text), text
    assert "one per event" in wording_results["footnotes"]["local"]["xy"]
    assert "no separation vector" in wording_results["footnotes"]["lab"]["xy"]
    assert "Shower centroid (energy-weighted voxels)" in wording_results["footnotes"]["lab"]["xy"]
    assert wording_results["stated"] == wording_results["footnotes"]["local"]
    assert wording_results["tags"] == {"single": "N = 287 showers", "two": "N = 7 · 14 showers"}


def test_two_shower_wording_is_unchanged(wording_results):
    assert "Diamond marks shower A, circle shower B" in wording_results["footnotes"]["base"]["xy"]
    assert "both showers of every event sit at the origin" in wording_results["captions"]["twoTrans"]
    assert "Both showers of every event are superimposed" in wording_results["channel"]["two"]


def test_the_local_frame_states_its_negative_depth_on_the_depth_panels(wording_results):
    c9 = wording_results["c9"]
    assert wording_results["summary"] in c9 and c9.startswith("Hits behind their shower's entry plane")
    assert any(wording_results["summary"] in line for line in wording_results["disclosure"]["yz"])
    assert any(wording_results["summary"] in line for line in wording_results["disclosure"]["xz"])
    assert not any(wording_results["summary"] in line for line in wording_results["disclosure"]["xy"])
    assert wording_results["c9Unavailable"] == "Negative-depth counts are unavailable: stale."


def test_a_single_showers_frames_are_titled_without_the_d_frame(wording_results):
    for key, (single, two) in wording_results["titles"].items():
        kind = key.split("|")[0]
        if kind == "lab":
            assert single == two, key
            continue
        assert "Separation-Aligned (D-Frame)" not in single and "legacy" not in single, (key, single)
        assert single != two, key
    labels = wording_results["frameLabels"]
    assert labels["trans"] == ["Translated", "Per-shower translated"]
    assert labels["local"] == ["Shower-Aligned › Local", "Separation-Aligned (D-Frame) › Local"]
    assert labels["lab"] == ["Absolute", "Absolute"]

