"""The Physics page's Longitudinal Channels wiring, executed under Node.

``main.js`` runs whole against a permissive fake document (every id exists),
a recording ECharts (one chart per plot element, every ``setOption`` kept)
and a recording ``fetch`` that answers from the recorded payloads
(``tests/fixtures/payloads``). Each scenario boots the page afresh on a link
(the hash) and drives it as a reader would: the mode radios, the editor's
presets and Cancel, the compare toggle, the theme toggle, a hover on the
channel strip. What is checked is what leaves the page - the requests, by
path and parameters - and what reaches the charts - the series and graphics
of each option.

* the control is mounted, told the experiment's L and fed the depth context;
* ``depth_groups`` is sent only by the 2 x 2 and the compare grid's
  Absolute and per-shower translated rows, in Pooled; never by Local, the
  Event Inspector or the profile card (C7);
* Boundaries, Off, a live draft and a theme switch cost no request;
* entering or leaving Pooled asks once per panel set whose request changed;
* hovering a channel on YZ spotlights it on XZ too, and leaving clears both;
  the same within an Event Inspector or compare row;
* the Event Inspector's specs: the tilted Local planes on u-w, the badge on
  v-w, detector and relative numbering on the other rows, never pooled;
* C7: the relative strip and seams on the native-layer axis in cm, the
  reach in their tooltips, the no-grid badge on w, nothing on rho.

Skipped when ``node`` is not on the PATH.
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

#: The base table's lattice has 56 layers; Uniform(56) is 4 x 5 then 9 x 4.
UNIFORM_56 = "5.5.5.5.4.4.4.4.4.4.4.4.4"
#: Another valid partition of 56, for an Apply while Pooled.
OTHER_56 = "4.4.4.4.4.4.4.4.4.4.4.4.8"

_HARNESS = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir, hash, scenario] = JSON.parse(process.argv.at(-1));
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));

/* ---- a permissive fake document: every id exists, an id set registers ---- */
const registry = new Map();
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.childNodes = []; this.attrs = {}; this.dataset = {};
    this.style = {}; this.listeners = {}; this.hidden = false; this.disabled = false; this.checked = false;
    this.className = ''; this._id = ''; this.title = ''; this.value = ''; this.parent = null;
    this.offsetHeight = 20; this.offsetWidth = 100;
  }
  get id() { return this._id; }
  set id(v) { this._id = String(v); if (v) registry.set(String(v), this); }
  get children() { return this.childNodes.filter((n) => n instanceof FakeElement); }
  get options() { return this.children.filter((c) => c.tagName === 'OPTION'); }
  get classList() {
    const el = this; const set = () => new Set(el.className.split(/\s+/).filter(Boolean));
    return {
      toggle(n, on) { const s = set(); const w = on === undefined ? !s.has(n) : Boolean(on); if (w) s.add(n); else s.delete(n); el.className = [...s].join(' '); return w; },
      add(...ns) { const s = set(); for (const n of ns) s.add(n); el.className = [...s].join(' '); },
      remove(...ns) { const s = set(); for (const n of ns) s.delete(n); el.className = [...s].join(' '); },
      contains(n) { return set().has(n); },
    };
  }
  append(...nodes) { for (const n of nodes) { const node = typeof n === 'string' ? { textContent: n } : n; node.parent = this; this.childNodes.push(node); } }
  appendChild(n) { this.append(n); return n; }
  prepend(...nodes) { this.append(...nodes); }
  insertBefore(n) { this.append(n); return n; }
  before() {} after() {} remove() {}
  replaceChildren(...nodes) { this.childNodes = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  toggleAttribute(k, on) { if (on) this.attrs[k] = ''; else delete this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  removeEventListener() {}
  dispatch(type, extra = {}) {
    for (const fn of this.listeners[type] ?? []) {
      fn({ target: this, currentTarget: this, key: '', preventDefault() {}, stopPropagation() {}, ...extra });
    }
  }
  click() { this.dispatch('click'); }
  focus() {} blur() {}
  get textContent() { return this.childNodes.map((c) => c.textContent ?? '').join(''); }
  set textContent(v) { this.childNodes = []; if (v !== '' && v != null) this.append(String(v)); }
  set innerHTML(v) { this._html = v; }
  get innerHTML() { return this._html ?? ''; }
  get clientWidth() { return 600; }
  get clientHeight() { return 330; }
  get isConnected() { return true; }
  getBoundingClientRect() { return { left: 0, top: 0, right: 600, bottom: 330, width: 600, height: 330 }; }
  closest() { return null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  contains() { return false; }
  scrollIntoView() {}
  setPointerCapture() {}
  getContext() {
    return { createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
      putImageData() {}, drawImage() {}, clearRect() {}, fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {},
      closePath() {}, stroke() {}, fill() {}, scale() {}, setTransform() {},
      set imageSmoothingEnabled(_) {}, font: '', measureText(t) { return { width: String(t).length * 5 }; } };
  }
  toDataURL() { return 'data:,'; }
}
const byId = (id) => { if (!registry.has(id)) { const el = new FakeElement('div'); el.id = id; } return registry.get(id); };
globalThis.document = {
  createElement: (t) => new FakeElement(t),
  createElementNS: (_ns, t) => new FakeElement(t),
  createTextNode: (t) => ({ textContent: String(t) }),
  getElementById: byId,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  removeEventListener() {},
  body: new FakeElement('body'),
  documentElement: new FakeElement('html'),
  activeElement: null,
};
const storage = new Map();
globalThis.localStorage = { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v)), removeItem: (k) => storage.delete(k) };
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = { hash, search: '', pathname: '/', origin: 'http://calosrv.test', href: 'http://calosrv.test/' };
globalThis.history = { replaceState(_s, _t, url) { const at = url.indexOf('#'); location.hash = at >= 0 ? url.slice(at) : ''; } };
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.innerWidth = 1600;
globalThis.innerHeight = 1000;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = (h) => clearTimeout(h);
globalThis.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
globalThis.MutationObserver = class { observe() {} disconnect() {} };
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '', color: '#888888' });
// The page reports a few faults of the fake document (the Admin panel's markup) on stderr; stdout is the result.
console.error = () => {};
console.warn = () => {};

/* ---- ECharts: one recording chart per plot element ---- */
const charts = new Map();
globalThis.echarts = {
  init(el) {
    const handlers = {};
    const zr = { on() {}, off() {} };
    const chart = {
      el, options: [], handlers,
      getWidth: () => 600, getHeight: () => 330, resize() {}, clear() {}, dispose() {},
      setOption(option, flags) { this.options.push({ option, flags: flags ?? null }); },
      dispatchAction() {}, on(ev, fn) { (handlers[ev] ??= []).push(fn); }, off() {},
      fire(ev, params) { for (const fn of handlers[ev] ?? []) fn(params); },
      getZr: () => zr, getDom: () => el, convertFromPixel: (_, p) => p, convertToPixel: (_, p) => p,
      getModel: () => ({ getComponent: () => null }),
    };
    charts.set(el.id, chart);
    return chart;
  },
};

/* ---- fetch: the recorded payloads; every request logged ---- */
const requests = [];
const projections = (q) => {
  const coord = q.get('coord_system');
  const pooled = q.has('depth_groups');
  if (q.get('frame') === 'canonical') return load('projections_base_canonical');
  if (coord === 'trans') return load(pooled ? 'projections_base_trans_pooled' : 'projections_base_trans');
  if (coord === 'local') return load('projections_single_local');
  return load(pooled ? 'projections_base_lab_pooled' : 'projections_base_lab');
};
const ROUTES = {
  '/api/experiments': () => load('experiments'),
  '/api/projections': projections,
  '/api/energy-distribution': () => load('energy_d_two'),
  '/api/model-performance': () => load('perf_two_energy'),
  '/api/event': () => load('event_raster_base'),
};
globalThis.fetch = async (url) => {
  const u = new URL(String(url));
  requests.push({ path: u.pathname, params: Object.fromEntries(u.searchParams) });
  const route = ROUTES[u.pathname];
  const body = route ? route(u.searchParams) : { detail: 'not recorded' };
  return {
    ok: Boolean(route), status: route ? 200 : 404, headers: { get: () => 'application/json' },
    json: async () => body, text: async () => JSON.stringify(body),
  };
};
const settle = async (n = 40) => { for (let i = 0; i < n; i += 1) await new Promise((r) => setTimeout(r, 5)); };

/* ---- what reached the charts ---- */
const STRIP = 'layer-groups-strip';
const SEAMS = 'layer-groups-seams';
const SPOT = 'layer-groups-spot';
const PLANES = 'layer-groups-planes';
const chartOf = (id) => charts.get(`plot-${id}`) ?? null;
const full = (id) => [...(chartOf(id)?.options ?? [])].reverse().find((o) => o.flags?.notMerge)?.option ?? null;
const seriesById = (option, sid) => (option?.series ?? []).find((s) => s.id === sid) ?? null;
const graphics = (option) => {
  const g = option?.graphic;
  const list = Array.isArray(g) ? g : (Array.isArray(g?.elements) ? g.elements : []);
  return list;
};
const groupsOf = (id) => {
  const option = full(id);
  const strip = seriesById(option, STRIP);
  const seams = seriesById(option, SEAMS);
  const planes = seriesById(option, PLANES);
  const badge = graphics(option).find((x) => x?.id === 'layer-groups-badge') ?? null;
  return {
    drawn: Boolean(option),
    strip: strip ? strip.data.length : 0,
    stripGroups: strip ? strip.data.map((d) => d[2]) : [],
    stripTips: strip ? strip.data.map((_, i) => strip.tooltip.formatter({ dataIndex: i })) : [],
    seams: seams ? seams.data.length : 0,
    seamTips: seams ? seams.data.map((_, i) => seams.tooltip.formatter({ dataIndex: i })) : [],
    planes: planes ? planes.data.length : 0,
    badge: badge ? badge.style.text : null,
    gridTop: option ? (Array.isArray(option.grid) ? option.grid[0].top : option.grid?.top) : null,
  };
};
const lastPatch = (id) => {
  const entry = [...(chartOf(id)?.options ?? [])].reverse().find((o) => !o.flags?.notMerge);
  return entry ? entry.option : null;
};
const spotData = (id) => {
  const patch = lastPatch(id);
  const spot = patch ? seriesById(patch, SPOT) : null;
  return spot ? spot.data.length : null;
};
const projectionRequests = (from = 0) => requests.slice(from).filter((r) => r.path === '/api/projections').map((r) => r.params);
const since = (from) => requests.slice(from).map((r) => r.path);
const radio = (mode) => {
  const el = byId(`lgmode-${mode}`);
  el.value = mode;
  el.checked = true;
  el.dispatch('change');
};

await import(`${jsRoot}/main.js`);
await settle();
const out = { boot: { requests: requests.map((r) => r.path), projections: projectionRequests() } };
const group = byId('group-lgroups');
out.control = {
  hidden: group.hidden,
  summary: byId('lgroups-summary').textContent,
  bar: byId('lgroups-bar').children.length,
  infoDotHidden: byId('info-lgroups').hidden,
};

if (scenario === 'modes') {
  out.bounds = { yz: groupsOf('yz'), xz: groupsOf('xz'), xy: groupsOf('xy') };
  // Boundaries -> Off -> Boundaries: no request.
  let at = requests.length;
  // The repaint is synchronous: its cost here is the page's own (option
  // building and notes), the ECharts paint being stubbed.
  const t0 = performance.now();
  radio('off');
  const offMs = performance.now() - t0;
  await settle();
  out.off = { requests: since(at), yz: groupsOf('yz'), ms: offMs };
  at = requests.length;
  const t1 = performance.now();
  radio('bounds');
  const backMs = performance.now() - t1;
  await settle();
  out.back = { requests: since(at), yz: groupsOf('yz'), ms: backMs };
  // Entering Pooled: one projections request, with the partition.
  at = requests.length;
  radio('pool');
  await settle();
  out.pool = { requests: since(at), projections: projectionRequests(at), yz: groupsOf('yz'), xz: groupsOf('xz') };
  // A live draft (a preset in the editor) and its Cancel: no request.
  byId('lgroups-edit').click();
  at = requests.length;
  const presetButton = { closest: () => ({ dataset: { preset: 'log' } }) };
  byId('lgroups-presets').dispatch('click', { target: presetButton });
  await settle();
  out.draft = { requests: since(at), yz: groupsOf('yz') };
  byId('lgroups-cancel').click();
  await settle();
  out.cancel = { requests: since(at), yz: groupsOf('yz') };
  // A theme switch: no request.
  at = requests.length;
  byId('theme-toggle').click();
  await settle();
  out.theme = { requests: since(at), yz: groupsOf('yz') };
  // The Marks toggle is a card control the fake document has no button for;
  // leaving Pooled asks once, without the partition.
  at = requests.length;
  radio('bounds');
  await settle();
  out.leave = { requests: since(at), projections: projectionRequests(at), yz: groupsOf('yz') };
  // A new partition outside Pooled: no request.
  at = requests.length;
  byId('lgroups-edit').click();
  byId('lgroups-presets').dispatch('click', { target: { closest: () => ({ dataset: { preset: 'em_hadron' } }) } });
  byId('lgroups-apply').click();
  await settle();
  out.applyBounds = { requests: since(at), hash: location.hash, yz: groupsOf('yz') };
}

if (scenario === 'hover') {
  const yz = chartOf('yz');
  yz.fire('mouseover', { seriesId: STRIP, value: [0, 0, 3] });
  out.over = { yz: spotData('yz'), xz: spotData('xz') };
  yz.fire('mouseout', { seriesId: STRIP });
  out.out = { yz: spotData('yz'), xz: spotData('xz') };
  chartOf('xz').fire('mouseover', { seriesId: STRIP, value: [0, 0, 7] });
  out.fromXz = { yz: spotData('yz'), xz: spotData('xz') };
}

if (scenario === 'compare') {
  const toggle = byId('opt-compare');
  toggle.checked = true;
  toggle.dispatch('change');
  await settle();
  out.compareOpen = { projections: projectionRequests(out.boot.requests.length) };
  out.rows = Object.fromEntries(['lab', 'trans', 'local'].map((k) => [k, groupsOf(`compare-${k}-yz`)]));
  let at = requests.length;
  radio('pool');
  await settle();
  out.pool = {
    requests: since(at),
    projections: projectionRequests(at),
    rows: Object.fromEntries(['lab', 'trans', 'local'].map((k) => [k, groupsOf(`compare-${k}-yz`)])),
  };
  // A row's two depth panels spotlight together; the other rows are untouched.
  const before = chartOf('compare-trans-xz').options.length;
  chartOf('compare-lab-yz').fire('mouseover', { seriesId: STRIP, value: [0, 0, 2] });
  out.rowHover = {
    labYz: spotData('compare-lab-yz'), labXz: spotData('compare-lab-xz'),
    transTouched: chartOf('compare-trans-xz').options.length !== before,
  };
  // An Apply of another partition while Pooled: one request per pooling row and one for the 2 x 2.
  at = requests.length;
  byId('lgroups-edit').click();
  byId('lgroups-shorthand').value = __OTHER__;
  byId('lgroups-shorthand-apply').click();
  byId('lgroups-apply').click();
  await settle();
  out.apply = { projections: projectionRequests(at) };
}

if (scenario === 'event') {
  out.event = {
    requests: requests.filter((r) => r.path === '/api/event').map((r) => r.params),
    labXz: groupsOf('event-lab-xz'), labYz: groupsOf('event-lab-yz'),
    transXz: groupsOf('event-trans-xz'),
    localXz: groupsOf('event-local-xz'), localYz: groupsOf('event-local-yz'),
    labXy: groupsOf('event-lab-xy'),
  };
  // Hover on one row's strip: its partner spotlights; Pooled asks nothing of the event.
  chartOf('event-trans-yz').fire('mouseover', { seriesId: STRIP, value: [0, 0, 4] });
  out.hover = { transXz: spotData('event-trans-xz'), transYz: spotData('event-trans-yz') };
  chartOf('event-trans-yz').fire('mouseout', { seriesId: STRIP });
  out.hoverOut = { transXz: spotData('event-trans-xz') };
  const at = requests.length;
  radio('pool');
  await settle();
  out.pool = {
    events: requests.slice(at).filter((r) => r.path === '/api/event').length,
    projections: projectionRequests(at),
    labXz: groupsOf('event-lab-xz'),
  };
}

if (scenario === 'fallback') {
  const dot = byId('info-lgroups');
  out.fallback = { dotHidden: dot.hidden, notices: JSON.parse(dot.dataset.notices ?? '[]') };
  dot.click();
  const popover = document.body.children.at(-1) ?? null;
  out.popover = popover ? { className: popover.className, html: popover.innerHTML } : null;
  out.yz = groupsOf('yz');
}

if (scenario === 'local') {
  out.local = { yz: groupsOf('yz'), xz: groupsOf('xz') };
}

console.log(JSON.stringify(out));
"""


def _run(hash_: str, scenario: str) -> dict:
    script = _HARNESS.replace("__OTHER__", json.dumps(OTHER_56.replace(".", ", ")))
    args = [str(JS), str(PAYLOADS), hash_, scenario]
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script, json.dumps(args)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def modes():
    return _run("#lgmode=bounds", "modes")


@pytest.fixture(scope="module")
def hover():
    return _run("#lgmode=bounds", "hover")


@pytest.fixture(scope="module")
def compare():
    return _run("#lgmode=bounds", "compare")


@pytest.fixture(scope="module")
def event():
    return _run("#lgmode=bounds&event=0", "event")


@pytest.fixture(scope="module")
def fallback():
    # A 60-layer partition on the 56-layer base table: Uniform is drawn and the sidebar says so.
    return _run("#lgmode=bounds&lgroups=4.4.4.4.4.4.4.4.4.4.4.4.12", "fallback")


@pytest.fixture(scope="module")
def local():
    return _run("#frame=local&lgmode=pool", "local")


# ------------------------------------------------------------ the control --

def test_the_control_is_mounted_and_told_the_experiments_layers(modes):
    control = modes["control"]
    assert control["hidden"] is False
    assert control["summary"] == "13 channels over 56 layers · Uniform"
    assert control["bar"] == 13
    assert control["infoDotHidden"] is True


def test_the_channels_info_dot_opens_its_notices_like_the_other_dots(fallback):
    assert fallback["fallback"]["dotHidden"] is False
    notices = fallback["fallback"]["notices"]
    assert any("do not fit this experiment’s 56 layers" in text for text in notices)
    assert fallback["popover"]["className"].startswith("popover")
    assert "do not fit" in fallback["popover"]["html"]
    # Uniform(56) is drawn in its place.
    assert fallback["yz"]["strip"] == 13


def test_a_cold_boot_in_boundaries_asks_nothing_pooled(modes):
    assert modes["boot"]["projections"], modes["boot"]
    assert all("depth_groups" not in p for p in modes["boot"]["projections"])


# --------------------------------------------------------- the 2 x 2 grid --

def test_boundaries_draw_the_strip_and_seams_on_both_depth_panels_only(modes):
    bounds = modes["bounds"]
    for panel in ("yz", "xz"):
        assert bounds[panel]["strip"] == 13
        assert bounds[panel]["seams"] == 12
        assert bounds[panel]["stripGroups"] == list(range(1, 14))
    assert bounds["xy"]["strip"] == 0 and bounds["xy"]["seams"] == 0
    # The seams sit at the stored edges, labelled in Z on the Absolute frame.
    assert all("Z = " in tip and "stored cell edge" in tip for tip in bounds["yz"]["seamTips"])


def test_a_boundaries_repaint_stays_inside_the_50_ms_budget(modes):
    # Headless: the page's own work (specs, options, notes) for both depth panels.
    assert modes["off"]["ms"] < 50
    assert modes["back"]["ms"] < 50


def test_off_and_back_repaint_with_no_request(modes):
    assert modes["off"]["requests"] == []
    assert modes["off"]["yz"]["strip"] == 0 and modes["off"]["yz"]["seams"] == 0
    assert modes["back"]["requests"] == []
    assert modes["back"]["yz"]["strip"] == 13


def test_entering_pooled_sends_exactly_one_projections_request_with_the_partition(modes):
    pool = modes["pool"]
    assert pool["requests"] == ["/api/projections"]
    assert pool["projections"][0]["depth_groups"] == UNIFORM_56
    # The pooled raster's bin edges are the seams: the strip stays, the seams go.
    for panel in ("yz", "xz"):
        assert pool[panel]["strip"] == 13
        assert pool[panel]["seams"] == 0
    assert any("mean of" in tip for tip in pool["yz"]["stripTips"])


def test_a_live_draft_and_its_cancel_cost_no_request(modes):
    # Pooled, with the editor's Logarithmic preset live: drawn over the pooled
    # picture in hand as its own strip and seams, never asked for.
    assert modes["draft"]["requests"] == []
    assert modes["draft"]["yz"]["seams"] == 12
    assert modes["cancel"]["requests"] == []
    assert modes["cancel"]["yz"]["seams"] == 0


def test_a_theme_switch_costs_no_request_and_keeps_the_channels(modes):
    assert modes["theme"]["requests"] == []
    assert modes["theme"]["yz"]["strip"] == 13


def test_leaving_pooled_asks_once_without_the_partition(modes):
    leave = modes["leave"]
    assert leave["requests"] == ["/api/projections"]
    assert "depth_groups" not in leave["projections"][0]
    assert leave["yz"]["seams"] == 12


def test_a_new_partition_outside_pooled_costs_no_request(modes):
    apply = modes["applyBounds"]
    assert apply["requests"] == []
    assert "lgroups=" in apply["hash"]
    assert apply["yz"]["strip"] == 13 and apply["yz"]["seams"] == 12


def test_hovering_a_channel_on_one_depth_panel_spotlights_both(hover):
    # The spotlight is two faces on each panel, patched in place.
    assert hover["over"] == {"yz": 2, "xz": 2}
    assert hover["out"] == {"yz": 0, "xz": 0}
    assert hover["fromXz"] == {"yz": 2, "xz": 2}


def test_local_never_pools_and_draws_the_no_grid_badge(local):
    assert local["boot"]["projections"]
    assert all("depth_groups" not in p for p in local["boot"]["projections"])
    for panel in ("yz", "xz"):
        assert local["local"][panel]["strip"] == 0
        assert local["local"][panel]["seams"] == 0
        assert local["local"][panel]["badge"].startswith("Layers tilt by each shower")


# ------------------------------------------------------- the compare grid --

def test_the_compare_grid_pools_its_absolute_and_translated_rows_only(compare):
    opened = compare["compareOpen"]["projections"]
    assert len(opened) == 3 and all("depth_groups" not in p for p in opened)
    assert compare["rows"]["lab"]["strip"] == 13
    assert compare["rows"]["trans"]["strip"] == 13
    assert compare["rows"]["local"]["badge"]
    pool = compare["pool"]["projections"]
    # One for the 2 x 2 and one per pooling row; the Local row is not asked again.
    assert len(pool) == 3
    coords = sorted(p.get("coord_system") for p in pool)
    assert coords == ["lab", "lab", "trans"]
    assert all(p["depth_groups"] == UNIFORM_56 for p in pool)
    rows = compare["pool"]["rows"]
    assert rows["lab"]["seams"] == 0 and rows["trans"]["seams"] == 0
    assert any("Rel Ch" in tip for tip in rows["trans"]["stripTips"])


def test_a_compare_rows_depth_panels_spotlight_together(compare):
    hover = compare["rowHover"]
    assert hover["labYz"] == 2 and hover["labXz"] == 2
    assert hover["transTouched"] is False


def test_a_new_partition_while_pooled_asks_once_per_pooling_panel_set(compare):
    pool = compare["apply"]["projections"]
    assert len(pool) == 3
    assert all(p["depth_groups"] == OTHER_56 for p in pool)


# --------------------------------------------------- the Event Inspector --

def test_the_inspector_draws_each_frames_own_layer_planes(event):
    ev = event["event"]
    assert ev["requests"] and all("depth_groups" not in p for p in ev["requests"])
    # Detector numbering on the original frame, relative on the translated one.
    assert ev["labXz"]["strip"] == 13 and ev["labXz"]["seams"] == 12
    assert ev["labYz"]["strip"] == 13
    assert all(tip.startswith("<b>Ch ") for tip in ev["labXz"]["stripTips"])
    assert ev["transXz"]["strip"] == 13
    assert all(tip.startswith("<b>Rel Ch ") for tip in ev["transXz"]["stripTips"])
    # Local: the tilted planes on u-w, the badge on v-w, no strip on either.
    assert ev["localXz"]["planes"] == 12 and ev["localXz"]["strip"] == 0
    assert ev["localYz"]["planes"] == 0
    assert ev["localYz"]["badge"].startswith("v–w: a layer plane tilted by θ = ")
    assert ev["labXy"]["strip"] == 0


def test_an_inspector_rows_depth_panels_spotlight_together(event):
    assert event["hover"] == {"transXz": 2, "transYz": 2}
    assert event["hoverOut"] == {"transXz": 0}


def test_pooled_never_reaches_the_inspector(event):
    pool = event["pool"]
    assert pool["events"] == 0
    # The hidden 2 x 2 is asked once, pooled, so it is right when the event is unpinned.
    assert len(pool["projections"]) == 1 and pool["projections"][0]["depth_groups"] == UNIFORM_56
    # One event is drawn at its native layers: the seams stay.
    assert pool["labXz"]["seams"] == 12


# -------------------------------------------------- C7, the profile card --

_C7 = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv.at(-1));
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid' } };
globalThis.document = {
  createElement: () => ({ getContext: () => ({ font: '', measureText: (t) => ({ width: String(t).length * 5 }) }) }),
  getElementById: () => null,
};
const section = await import(`${jsRoot}/physics_section.js`);
const profile = await import(`${jsRoot}/panels/profile.js`);
const lg = await import(`${jsRoot}/layer_groups.js`);
const native = load('profiles_single_native');
const w = load('profiles_two_w');
const counts = lg.uniformCounts(25);
const layer = (mode) => ({ mode, counts, L: 25, highlight: null, onHover: null });
const summary = (option) => {
  const s = (id) => option.series.find((x) => x.id === id) ?? null;
  const strip = s('layer-groups-strip');
  const seams = s('layer-groups-seams');
  const badge = (option.graphic ?? []).find((g) => g.id === 'layer-groups-badge') ?? null;
  return {
    strip: strip ? strip.data.length : 0,
    first: strip ? strip.data[0] : null,
    last: strip ? strip.data.at(-1) : null,
    tips: strip ? strip.data.map((_, i) => strip.tooltip.formatter({ dataIndex: i })) : [],
    seams: seams ? seams.data.map((d) => d[0]) : [],
    badge: badge ? badge.style.text : null,
    top: option.grid.top,
  };
};
const optionOf = (payload, id, mode) => {
  const opts = section.cardOptions(id, { controls: { ...section.DEFAULT_CONTROLS }, payload, layer: mode ? layer(mode) : null });
  return { opts, option: profile.profileOption(payload, opts, { width: 640, height: 360 }) };
};
const out = {};
const nativeB = optionOf(native, 'profile-w', 'bounds');
out.kt = { axis: nativeB.opts.axis, ...summary(nativeB.option), spec: { mmPerUnit: nativeB.opts.layerGroups.mmPerUnit, numbering: nativeB.opts.layerGroups.numbering } };
out.ktPool = summary(optionOf(native, 'profile-w', 'pool').option);
out.ktOff = { has: 'layerGroups' in optionOf(native, 'profile-w', 'off').opts, ...summary(optionOf(native, 'profile-w', 'off').option) };
out.ktNone = summary(optionOf(native, 'profile-w', null).option);
out.edgesCm = native.axes.kt.edges_cm;
out.readout = profile.profileReadout(native, 'kt', 30, nativeB.opts.layerGroups);
const wB = optionOf(w, 'profile-w', 'bounds');
out.w = { axis: wB.opts.axis, ...summary(wB.option) };
const rB = optionOf(native, 'profile-r', 'bounds');
out.r = { has: 'layerGroups' in rB.opts, ...summary(rB.option) };
// The request is the card's own: the partition never reaches /api/profiles.
const { page1Plan } = await import(`${jsRoot}/capabilities.js`);
const single = load('experiments').experiments.find((e) => e.table_name === 'single_hits');
const req = section.cardRequest('profile-w', {
  filters: { table_name: 'single_hits' }, controls: { ...section.DEFAULT_CONTROLS, profileDepth: 'native' }, plan: page1Plan(single),
});
out.request = req ? req.params : null;
// The card's own hover: a strip segment spotlights its channel, patched in place.
const handlers = {};
const sets = [];
const zr = { on() {}, off() {} };
const chart = { getWidth: () => 640, getHeight: () => 360, resize() {}, clear() {}, dispatchAction() {},
  setOption(option, flags) { sets.push({ option, flags: flags ?? null }); },
  on(ev, fn) { (handlers[ev] ??= []).push(fn); }, getZr: () => zr, getDom: () => host,
  fire(ev, params) { for (const fn of handlers[ev] ?? []) fn(params); } };
const host = { clientWidth: 640, clientHeight: 360, style: {}, addEventListener() {}, classList: { toggle() {} }, closest: () => null };
globalThis.echarts = { init: () => chart };
const panel = new profile.ProfilePanel(host, { axis: 'depth' });
panel.render(native, nativeB.opts);
const spot = () => {
  const patch = [...sets].reverse().find((s) => !s.flags?.notMerge)?.option;
  const series = patch?.series?.find((x) => x.id === 'layer-groups-spot');
  return series ? series.data.length : null;
};
const fulls = sets.filter((s) => s.flags?.notMerge).length;
chart.fire('mouseover', { seriesId: 'layer-groups-strip', value: [0, 0, 5] });
out.hover = { over: spot(), highlight: panel.lastOpts.layerGroups.highlight };
chart.fire('mouseout', { seriesId: 'layer-groups-strip' });
out.hover.out = spot();
out.hover.fullRedraws = sets.filter((s) => s.flags?.notMerge).length - fulls;
panel.setLayerGroups(null);
out.hover.cleared = summary(sets.filter((s) => s.flags?.notMerge).at(-1).option).strip;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def c7():
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _C7, json.dumps([str(JS), str(PAYLOADS)])],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_c7_draws_the_relative_strip_and_seams_on_the_native_axis_in_cm(c7):
    kt = c7["kt"]
    assert kt["axis"] == "kt"
    assert kt["spec"] == {"mmPerUnit": 10, "numbering": "relative"}
    assert kt["strip"] == 13
    # Positions are the card's own bin edges: the spec holds mm, the chart
    # draws cm (mmPerUnit 10), so the series data sit on the cm edges.
    edges = c7["edgesCm"]
    assert kt["first"][0] == pytest.approx(edges[0])
    # Group 13 runs to the end of the axis, past the partition's 25 layers.
    assert kt["last"][1] == pytest.approx(edges[-1])
    assert len(kt["seams"]) == 12
    for at in kt["seams"]:
        assert any(abs(at - e) < 1e-9 for e in edges)
    assert all(tip.startswith("<b>Rel Ch ") for tip in kt["tips"])
    assert all("reached by " in tip for tip in kt["tips"])
    # The first channel starts half a pitch upstream, written with U+2212.
    assert "Δz −10.3 to " in kt["tips"][0]
    assert not any(HYPHEN_NUMBER.search(tip) for tip in kt["tips"])
    assert "rel. layer 31 · Rel Ch 13 · reached by " in c7["readout"]


def test_c7_spotlights_a_hovered_channel_within_the_card(c7):
    hover = c7["hover"]
    assert hover["over"] == 2 and hover["highlight"] == 5
    assert hover["out"] == 0
    # The strip and the spotlight are patched in place, never a full redraw.
    assert hover["fullRedraws"] == 0
    # A new spec (here none) is drawn from the payload in hand.
    assert hover["cleared"] == 0


def test_c7_reserves_the_band_above_the_plot(c7):
    assert c7["kt"]["top"] > c7["ktNone"]["top"]
    assert c7["w"]["top"] > c7["ktNone"]["top"]


def test_c7_pooled_draws_boundaries(c7):
    assert c7["ktPool"]["strip"] == 13
    assert len(c7["ktPool"]["seams"]) == 12


def test_c7_off_draws_nothing(c7):
    assert c7["ktOff"]["has"] is False
    assert c7["ktOff"]["strip"] == 0 and c7["ktOff"]["seams"] == []
    assert c7["ktOff"]["top"] == c7["ktNone"]["top"]


def test_c7_w_has_the_no_grid_badge_and_no_lines(c7):
    w = c7["w"]
    assert w["axis"] == "w"
    assert w["strip"] == 0 and w["seams"] == []
    assert w["badge"].startswith("Layers tilt by each shower")


def test_the_radial_card_gets_nothing(c7):
    assert c7["r"]["has"] is False
    assert c7["r"]["strip"] == 0 and c7["r"]["badge"] is None


def test_c7_never_asks_for_a_partition(c7):
    assert c7["request"] is not None
    assert "depth_groups" not in c7["request"]
