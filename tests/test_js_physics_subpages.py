"""The Physics page's subpage router under Node: ``static/js/physics_subpages.js``.

Brief ``data/dev/design/physics-subpages/brief.md`` §8:

* the pure helpers: ``psubOfCard`` for every Physics card id family, and
  ``eventStatus`` on the Stage 1 recordings of ``GET /api/event`` under
  ``basis=experiment`` (``event_raster_base_experiment.json``, two showers;
  ``event_raster_single_experiment.json``, one shower), in the pool, outside it
  and with fields missing;
* ``mountPhysicsSubnav`` on a fake page: the tablist (``aria-selected``, roving
  ``tabindex``, arrows, Home and End with a disabled tab skipped, clicks on a
  disabled tab ignored), ``show()`` and its write / ``onSwitch`` order and its
  false returns, the silent apply at mount, ``#stat-mode``, ``.app[data-psub]``,
  the scroll kept per subpage, ``setEnabled`` and its restore, the head-height
  watcher;
* ``methodology/links.js``: a Physics badge carries ``psub: null``, so it
  opens Entire selection.

The router is driven with a recording stand-in for the State (``get`` / ``set``),
so this file does not depend on ``state.js``'s ``psub`` key (``ps-core``).

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, HYPHEN_NUMBER, JS, NODE, _path, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MINUS = "−"

_SCRIPT = _FAKE_DOM + r"""
const [subUrl, linksUrl, paths] = JSON.parse(process.argv[1]);
const P = loadAll(paths);
const sub = await import(subUrl);
const links = await import(linksUrl);
const out = {};

// ---- constants and psubOfCard
out.constants = { default: sub.DEFAULT_PSUB, labels: sub.PSUB_LABELS };
const ids = [
  'xy', 'yz', 'xz', 'energy', 'compare-grid', 'compare-lab', 'compare-trans', 'compare-local', 'compare-canonical',
  'profile-w', 'profile-r', 'response-b1', 'response-b2', 'response-res', 'response-b3', 'distribution',
  'correlation', 'statistics',
  'event-lab-xy', 'event-lab-xz', 'event-lab-yz', 'event-trans-xy', 'event-trans-xz', 'event-trans-yz',
  'event-local-xy', 'event-local-xz', 'event-local-yz',
  'event', 'eventual', 'events-xy', '', null, undefined, 7,
];
out.ofCard = ids.map((id) => [String(id), sub.psubOfCard(id)]);

// ---- eventStatus
const base = P.base;
const single = P.single;
out.statusBase = sub.eventStatus(base, { nShowers: 2 });
out.statusSingle = sub.eventStatus(single, { nShowers: 1 });
// One shower: the shower item is hidden, so its text is the dash even where a label exists.
out.statusSingleAsTwo = sub.eventStatus(single, { nShowers: 2 }).shower;
// Default nShowers is two showers.
out.statusDefault = sub.eventStatus(base);
// The event block itself, without the payload around it.
out.statusBlock = sub.eventStatus(base.event, { nShowers: 2 });
// Outside the pool.
const outside = structuredClone(base);
outside.event.candidates.in_pool = false;
outside.event.candidates.index = null;
out.statusOutside = sub.eventStatus(outside, { nShowers: 2 });
// A later place in a large pool: grouped counts.
const later = structuredClone(base);
later.event.candidates.index = 11;
later.event.candidates.n_events = 20325;
out.statusLater = sub.eventStatus(later, { nShowers: 2 }).place;
// Large event number and cell count are grouped.
const large = structuredClone(base);
large.event.event_number = 20123;
large.event.shower.n_hits = 12345;
const big = sub.eventStatus(large, { nShowers: 2 });
out.statusLarge = { event: big.event, cells: big.cells };
// Missing fields are dashes.
out.statusEmpty = [sub.eventStatus(null), sub.eventStatus({}), sub.eventStatus({ event: {} }),
  sub.eventStatus(undefined, { nShowers: 1 })];
const holes = structuredClone(base);
delete holes.event.shower.momentum_gev;
holes.event.shower.theta_deg = null;
delete holes.event.shower.n_hits;
delete holes.event.shower.energy_gev;
delete holes.event.candidates;
out.statusHoles = sub.eventStatus(holes, { nShowers: 2 });
const noPlace = structuredClone(base);
noPlace.event.candidates = { basis: 'experiment', in_pool: true, index: null, n_events: null };
out.statusNoIndex = sub.eventStatus(noPlace, { nShowers: 2 }).place;
// A negative number is set with U+2212.
const neg = structuredClone(base);
neg.event.shower.theta_deg = -3.14;
neg.event.shower.momentum_gev = -0.5;
neg.event.shower.energy_gev = -0.00123;
const n = sub.eventStatus(neg, { nShowers: 2 });
out.statusNegative = { p: n.p, theta: n.theta, edep: n.edep };

// ---- the router on a fake page
const PSUBS = ['selection', 'event'];
const TITLES = { selection: 'Every selected event: the 2 x 2 diagnostic.', event: 'One event at a time.' };
const calls = { focus: [] };
const page = ({ withChip = true, withHead = true } = {}) => {
  const els = new Map();
  const make = (tag, id) => { const el = document.createElement(tag); if (id) { el.id = id; els.set(id, el); } return el; };
  const app = make('div'); app.className = 'app';
  const main = make('main'); main.className = 'main'; main.scrollTop = 0;
  const props = {};
  main.style = { setProperty: (k, v) => { props[k] = v; } };
  app.append(main);
  let headHeight = 61.2;
  const head = withHead ? make('div', 'physics-head') : null;
  if (head) { head.getBoundingClientRect = () => ({ height: headHeight }); main.append(head); }
  const nav = make('nav', 'physics-subnav'); (head ?? main).append(nav);
  for (const psub of PSUBS) {
    const tab = make('button', `psub-tab-${psub}`);
    tab.title = TITLES[psub];
    tab.focus = () => { calls.focus.push(tab.id); };
    nav.append(tab);
    const panel = make('div', `psub-${psub}`);
    panel.hidden = psub !== 'selection';
    main.append(panel);
  }
  const chip = withChip ? make('span', 'stat-mode') : null;
  if (chip) chip.textContent = 'Entire selection';
  return {
    app, main, els, props, chip, head, setHeight: (h) => { headHeight = h; },
    root: {
      getElementById: (id) => els.get(id) ?? null,
      querySelector: (sel) => (sel === '.app' ? app : sel === '.main' ? main : null),
    },
  };
};
// A recording stand-in for the State: get/set of `psub` only.
const fakeState = (psub) => {
  const writes = [];
  const values = { psub };
  return { writes, get: (k) => values[k], set: (patch) => { writes.push({ ...patch }); Object.assign(values, patch); } };
};
const snap = (p) => ({
  hidden: PSUBS.map((k) => p.els.get(`psub-${k}`).hidden),
  selected: PSUBS.map((k) => p.els.get(`psub-tab-${k}`).getAttribute('aria-selected')),
  tabindex: PSUBS.map((k) => p.els.get(`psub-tab-${k}`).getAttribute('tabindex')),
  app: p.app.dataset.psub,
  chip: p.chip ? p.chip.textContent : null,
  scroll: p.main.scrollTop,
});
const tabSnap = (p, psub) => {
  const t = p.els.get(`psub-tab-${psub}`);
  return { ariaDisabled: t.getAttribute('aria-disabled'), disabled: t.classList.contains('is-disabled'),
    title: t.getAttribute('title') };
};
const key = (p, psub, k) => {
  let prevented = false;
  for (const fn of p.els.get(`psub-tab-${psub}`).listeners.keydown ?? []) fn({ key: k, preventDefault() { prevented = true; } });
  return prevented;
};

// -- mount: default State, silent
let st = fakeState(undefined);
let p = page();
const order = [];
const switched = [];
let router = sub.mountPhysicsSubnav({ state: st, root: p.root, onSwitch: (m) => { switched.push(m); order.push(['switch', st.writes.length]); } });
out.mount = { ...snap(p), current: router.current(), writes: st.writes.length, switched: [...switched],
  keys: Object.keys(router).sort() };

// -- mount from a link: the viewer, silently
st = fakeState('event');
p = page();
const quiet = [];
router = sub.mountPhysicsSubnav({ state: st, root: p.root, onSwitch: (m) => quiet.push(m) });
out.linked = { ...snap(p), current: router.current(), writes: st.writes.length, switched: quiet };

// -- an unknown stored value means Entire selection
st = fakeState('bogus');
p = page();
router = sub.mountPhysicsSubnav({ state: st, root: p.root });
out.bogusMount = { ...snap(p), current: router.current() };

// -- show(): the write comes before onSwitch; the scroll is kept per subpage
st = fakeState('selection');
p = page();
order.length = 0; switched.length = 0;
router = sub.mountPhysicsSubnav({ state: st, root: p.root, onSwitch: (m) => { switched.push(m); order.push(['switch', st.writes.length]); } });
p.main.scrollTop = 420;
out.show = { changed: router.show('event') };
out.show.snap = snap(p);
out.show.writes = st.writes.map((w) => ({ ...w }));
out.show.order = [...order];
out.show.switched = [...switched];
// The viewer had never been scrolled; scroll it, go back: the first page's place returns.
p.main.scrollTop = 75;
out.back = { changed: router.show('selection'), ...snap(p) };
out.again = { changed: router.show('event'), ...snap(p) };
// Already on show: false, no onSwitch.
const n0 = switched.length;
out.same = { changed: router.show('event'), switched: switched.length - n0 };
// Unknown means Entire selection.
router.show('bogus');
out.bogusShow = snap(p);
// write: false makes the switch and leaves the State alone.
const w0 = st.writes.length;
router.show('event', { write: false });
out.noWrite = { ...snap(p), writes: st.writes.length - w0, state: st.get('psub') };
// A click on a tab switches.
p.els.get('psub-tab-selection').click();
out.click = { ...snap(p), current: router.current() };

// -- the keys (WAI-ARIA tabs, automatic activation)
st = fakeState('selection');
p = page();
router = sub.mountPhysicsSubnav({ state: st, root: p.root });
calls.focus.length = 0;
const seq = [];
const step = (from, k) => { const prevented = key(p, from, k); seq.push({ k, prevented, current: router.current(), focus: calls.focus.at(-1) ?? null }); };
step('selection', 'ArrowRight');   // -> event
step('event', 'ArrowRight');       // wraps -> selection
step('selection', 'ArrowLeft');    // wraps -> event
step('event', 'Home');             // -> selection
step('selection', 'End');          // -> event
step('event', 'Tab');              // the browser's
out.keys = seq;
out.keysAfter = snap(p);

// -- a disabled tab: skipped by the keys, ignored by clicks, restored
st = fakeState('selection');
p = page();
switched.length = 0;
router = sub.mountPhysicsSubnav({ state: st, root: p.root, onSwitch: (m) => switched.push(m) });
out.beforeDisable = tabSnap(p, 'event');
router.setEnabled('event', false, 'No hits in this experiment.');
out.disabled = { event: tabSnap(p, 'event'), selection: tabSnap(p, 'selection') };
calls.focus.length = 0;
const prevented = [key(p, 'selection', 'ArrowRight'), key(p, 'selection', 'ArrowLeft')];
out.disabledKeys = { prevented, current: router.current(), focus: [...calls.focus], switched: [...switched], writes: st.writes.length };
// Home and End land on the one enabled tab, which is the one on show: no switch.
const edge = [key(p, 'selection', 'Home'), key(p, 'selection', 'End')];
out.disabledEdges = { prevented: edge, current: router.current(), switched: [...switched] };
st.writes.length = 0;
p.els.get('psub-tab-event').click();
out.disabledClick = { ...snap(p), current: router.current(), switched: [...switched], writes: st.writes.length };
out.disabledShow = { changed: router.show('event'), writes: st.writes.length, current: router.current() };
// Keys on the disabled tab itself do nothing either.
out.disabledOwnKey = { prevented: key(p, 'event', 'Home'), current: router.current() };
// Re-enabled: the markup's title returns, the tab works.
router.setEnabled('event', true);
out.reenabled = tabSnap(p, 'event');
p.els.get('psub-tab-event').click();
out.reenabledClick = { ...snap(p), current: router.current() };
// setEnabled on an unknown subpage is harmless.
router.setEnabled('nowhere', false, 'x');
// Shutting the tab on show does not switch by itself; keys then have nowhere to go.
router.setEnabled('selection', false, 'closed');
out.bothShut = { prevented: key(p, 'event', 'ArrowRight'), current: router.current() };
router.setEnabled('selection', true);

// -- the head height: measured at mount, again on a resize, on demand, rounded up
const observers = [];
globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; observers.push(this); } observe(t) { this.target = t; } disconnect() { this.gone = true; } };
p = page();
router = sub.mountPhysicsSubnav({ state: fakeState('selection'), root: p.root });
out.head = { mounted: p.props['--physics-head-h'], observed: observers[0]?.target === p.head };
p.setHeight(140);
observers[0].cb();
out.head.resized = p.props['--physics-head-h'];
p.setHeight(90.01);
out.head.measured = [router.measureHead(), p.props['--physics-head-h']];
// The standalone watcher, with its own property name and without an observer.
const bare = { style: { props: {}, setProperty(k, v) { this.props[k] = v; } } };
const w = sub.watchHeadHeight({ head: p.head, target: bare, property: '--x', Observer: undefined });
out.head.standalone = [bare.style.props['--x'], w.measure()];
w.disconnect();
out.head.noHead = sub.watchHeadHeight({ head: null, target: bare }).measure();
delete globalThis.ResizeObserver;

// -- a page without the optional parts (no chip, no head) still mounts and switches
p = page({ withChip: false, withHead: false });
router = sub.mountPhysicsSubnav({ state: fakeState('selection'), root: p.root });
out.minimal = { switched: router.show('event'), ...snap(p), measured: router.measureHead() };

// -- the source never touches the card graph
// (checked in Python)

// ---- links.js: a Physics badge opens Entire selection
const physicsBadge = { page: 'physics', panel: 'xy', set: { frame: 'canonical' } };
out.badge = {
  physics: links.badgeSet(physicsBadge),
  physicsBare: links.badgeSet({ page: 'physics', panel: 'xy' }),
  physicsOwn: links.badgeSet({ page: 'physics', panel: 'event-lab-xy', set: { psub: 'event', event: 3 } }),
  models: links.badgeSet({ page: 'models', panel: 'vox-event', set: { frame: 'lab' } }),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def r() -> dict:
    return _run(_SCRIPT, [
        (JS / "physics_subpages.js").as_uri(), (JS / "methodology" / "links.js").as_uri(),
        {"base": _path("event_raster_base_experiment"), "single": _path("event_raster_single_experiment")},
    ])


# ------------------------------------------------------------- the constants --

def test_the_default_subpage_and_labels(r):
    assert r["constants"] == {"default": "selection",
                              "labels": {"selection": "Entire selection", "event": "Event viewer"}}


# -------------------------------------------------------------- psubOfCard --

def test_every_event_card_is_on_the_viewer_and_every_other_physics_card_on_entire_selection(r):
    of = dict(r["ofCard"])
    event_cards = [f"event-{frame}-{plane}" for frame in ("lab", "trans", "local") for plane in ("xy", "xz", "yz")]
    assert all(of[c] == "event" for c in event_cards) and len(event_cards) == 9
    selection_cards = ["xy", "yz", "xz", "energy", "compare-grid", "compare-lab", "compare-trans", "compare-local",
                       "compare-canonical", "profile-w", "profile-r", "response-b1", "response-b2",
                       "response-res", "response-b3", "distribution", "correlation", "statistics"]
    assert all(of[c] == "selection" for c in selection_cards)


def test_only_an_event_dash_prefix_names_the_viewer(r):
    of = dict(r["ofCard"])
    # Look-alikes and non-ids take the default; the caller decides whether such a card exists.
    for look_alike in ("event", "eventual", "events-xy", "", "null", "undefined", "7"):
        assert of[look_alike] == "selection", look_alike


# ------------------------------------------------------------- eventStatus --

def test_the_status_of_a_two_shower_event(r):
    s = r["statusBase"]
    # formatSci(0.0498..., 3) prints four decimals: the helper eventRowLabel uses.
    assert s == {"event": "0", "shower": "A", "p": "2.71 GeV", "theta": "22.3°", "cells": "170",
                 "edep": "0.0498 GeV", "place": "1 of 2"}
    assert r["statusDefault"] == s and r["statusBlock"] == s


def test_the_status_of_a_one_shower_event_has_no_shower_label(r):
    s = r["statusSingle"]
    assert s["event"] == "3" and s["shower"] == "—"
    assert s["p"] == "7.31 GeV" and s["theta"] == "16.3°" and s["cells"] == "66"
    assert s["edep"] == "0.0189 GeV"
    assert s["place"] == "3 of 287"
    # The item is hidden on one shower whatever the payload's label.
    assert r["statusSingleAsTwo"] == "Shower"


def test_outside_the_pool_the_place_says_so(r):
    assert r["statusOutside"]["place"] == "not a candidate"
    assert r["statusOutside"]["event"] == "0"


def test_place_and_counts_are_grouped(r):
    assert r["statusLater"] == "12 of 20,325"
    assert r["statusLarge"] == {"event": "20,123", "cells": "12,345"}


def test_a_missing_field_is_a_dash(r):
    for empty in r["statusEmpty"]:
        assert empty == {"event": "—", "shower": "—", "p": "—", "theta": "—", "cells": "—", "edep": "—",
                         "place": "—"}
    h = r["statusHoles"]
    assert h["p"] == "—" and h["theta"] == "—" and h["cells"] == "—" and h["edep"] == "—" and h["place"] == "—"
    assert h["event"] == "0" and h["shower"] == "A"
    assert r["statusNoIndex"] == "—"


def test_a_negative_number_is_set_with_the_true_minus(r):
    n = r["statusNegative"]
    assert n["p"] == f"{MINUS}0.50 GeV" and n["theta"] == f"{MINUS}3.1°"
    assert n["edep"].startswith(MINUS)
    for status in (r["statusBase"], r["statusSingle"], r["statusOutside"], r["statusHoles"], n):
        for text in status.values():
            assert not HYPHEN_NUMBER.search(text), text


# ----------------------------------------------------------------- mounting --

def test_the_router_starts_on_the_states_subpage_silently(r):
    m = r["mount"]
    assert m["hidden"] == [False, True] and m["selected"] == ["true", "false"] and m["tabindex"] == ["0", "-1"]
    assert m["app"] == "selection" and m["chip"] == "Entire selection" and m["current"] == "selection"
    assert m["writes"] == 0 and m["switched"] == []
    assert m["keys"] == ["current", "measureHead", "setEnabled", "show"]
    linked = r["linked"]
    assert linked["hidden"] == [True, False] and linked["selected"] == ["false", "true"]
    assert linked["tabindex"] == ["-1", "0"] and linked["app"] == "event" and linked["chip"] == "Event viewer"
    assert linked["current"] == "event" and linked["writes"] == 0 and linked["switched"] == []
    bogus = r["bogusMount"]
    assert bogus["current"] == "selection" and bogus["hidden"] == [False, True] and bogus["chip"] == "Entire selection"


# ------------------------------------------------------------------- show() --

def test_show_switches_writes_and_then_tells_the_page(r):
    s = r["show"]
    assert s["changed"] is True
    assert s["snap"]["hidden"] == [True, False] and s["snap"]["selected"] == ["false", "true"]
    assert s["snap"]["tabindex"] == ["-1", "0"] and s["snap"]["app"] == "event"
    assert s["snap"]["chip"] == "Event viewer"
    assert s["writes"] == [{"psub": "event"}]
    # onSwitch runs after the write: it saw one write already.
    assert s["switched"] == ["event"] and s["order"] == [["switch", 1]]


def test_each_subpage_keeps_its_own_scroll_position(r):
    assert r["show"]["snap"]["scroll"] == 0, "the viewer had never been scrolled"
    assert r["back"]["changed"] is True and r["back"]["scroll"] == 420
    assert r["again"]["changed"] is True and r["again"]["scroll"] == 75


def test_showing_the_subpage_on_show_is_a_no_op_and_an_unknown_one_is_entire_selection(r):
    assert r["same"] == {"changed": False, "switched": 0}
    assert r["bogusShow"]["hidden"] == [False, True] and r["bogusShow"]["app"] == "selection"
    assert r["bogusShow"]["chip"] == "Entire selection"


def test_a_switch_without_a_write_leaves_the_state_alone(r):
    n = r["noWrite"]
    assert n["writes"] == 0 and n["hidden"] == [True, False] and n["app"] == "event"
    assert n["state"] == "selection"


def test_a_click_switches(r):
    c = r["click"]
    assert c["current"] == "selection" and c["hidden"] == [False, True] and c["app"] == "selection"


# --------------------------------------------------------------------- keys --

def test_the_tab_keys_follow_the_wai_aria_pattern(r):
    keys = r["keys"]
    assert keys[0] == {"k": "ArrowRight", "prevented": True, "current": "event", "focus": "psub-tab-event"}
    assert keys[1] == {"k": "ArrowRight", "prevented": True, "current": "selection", "focus": "psub-tab-selection"}
    assert keys[2] == {"k": "ArrowLeft", "prevented": True, "current": "event", "focus": "psub-tab-event"}
    assert keys[3] == {"k": "Home", "prevented": True, "current": "selection", "focus": "psub-tab-selection"}
    assert keys[4] == {"k": "End", "prevented": True, "current": "event", "focus": "psub-tab-event"}
    # Any other key is the browser's.
    assert keys[5]["prevented"] is False and keys[5]["current"] == "event"
    assert r["keysAfter"]["tabindex"] == ["-1", "0"]


# ------------------------------------------------------------ a shut tab --

def test_setenabled_shuts_a_tab_with_its_reason_and_restores_the_markups_title(r):
    assert r["beforeDisable"] == {"ariaDisabled": None, "disabled": False, "title": "One event at a time."}
    d = r["disabled"]
    assert d["event"] == {"ariaDisabled": "true", "disabled": True, "title": "No hits in this experiment."}
    assert d["selection"] == {"ariaDisabled": None, "disabled": False,
                              "title": "Every selected event: the 2 x 2 diagnostic."}
    assert r["reenabled"] == {"ariaDisabled": None, "disabled": False, "title": "One event at a time."}


def test_a_disabled_tab_is_skipped_by_the_keys_and_ignores_clicks(r):
    k = r["disabledKeys"]
    # Every navigation key has nowhere to go: no switch, no write, no focus move; the keys are still the tab list's.
    assert k["prevented"] == [True, True]
    assert k["current"] == "selection" and k["focus"] == [] and k["switched"] == [] and k["writes"] == 0
    c = r["disabledClick"]
    assert c["current"] == "selection" and c["hidden"] == [False, True] and c["switched"] == [] and c["writes"] == 0
    s = r["disabledShow"]
    assert s == {"changed": False, "writes": 0, "current": "selection"}
    e = r["disabledEdges"]
    assert e == {"prevented": [True, True], "current": "selection", "switched": []}
    assert r["disabledOwnKey"] == {"prevented": False, "current": "selection"}


def test_an_enabled_tab_works_again(r):
    c = r["reenabledClick"]
    assert c["current"] == "event" and c["hidden"] == [True, False] and c["app"] == "event"


def test_with_both_tabs_shut_the_keys_go_nowhere(r):
    assert r["bothShut"] == {"prevented": True, "current": "event"}


# ----------------------------------------------------------------- the head --

def test_the_sticky_heads_height_is_measured_rounded_up_and_followed(r):
    h = r["head"]
    assert h["mounted"] == "62px" and h["observed"] is True
    assert h["resized"] == "140px"
    assert h["measured"] == [91, "91px"]
    assert h["standalone"] == ["91px", 91]
    assert h["noHead"] is None


def test_a_page_without_the_chip_or_the_head_still_switches(r):
    m = r["minimal"]
    assert m["switched"] is True and m["hidden"] == [True, False] and m["chip"] is None
    assert m["measured"] is None


# ------------------------------------------------------------- the source --

def _strip_comments(source: str) -> str:
    import re
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def test_the_module_stays_out_of_the_models_card_graph_and_touches_no_chart_or_innerhtml():
    source = _strip_comments((JS / "physics_subpages.js").read_text(encoding="utf-8"))
    imports = [line for line in source.splitlines() if line.startswith("import")]
    assert all("models_subpages" not in line and "models_cards" not in line for line in imports)
    assert imports == ["import { formatSigned } from './format.js';", "import { formatInt, formatSci } from './scale.js';"]
    for forbidden in ("innerHTML", "createElement", "echarts", "dispose", "transition"):
        assert forbidden not in source, forbidden


def test_the_models_router_does_not_import_the_physics_one():
    source = (JS / "models_subpages.js").read_text(encoding="utf-8")
    assert "physics_subpages" not in source


# ------------------------------------------------------------------ badges --

def test_a_physics_badge_opens_entire_selection(r):
    b = r["badge"]
    assert b["physics"] == {"event": None, "compare": None, "psub": None, "frame": "canonical"}
    assert b["physicsBare"] == {"event": None, "compare": None, "psub": None}
    # A badge that sets its own view modes keeps them.
    assert b["physicsOwn"] == {"event": 3, "compare": None, "psub": "event"}
    # Models badges are untouched.
    assert b["models"] == {"frame": "lab"}
    source = (JS / "methodology" / "links.js").read_text(encoding="utf-8")
    assert "Entire selection" in source
