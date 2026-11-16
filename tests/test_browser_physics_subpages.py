"""The Physics page's two subpages, Entire selection and Event viewer, in Chromium.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks, on the
``physics_live_server`` (the two-shower demonstration, the single-shower hits
and their event-level aggregate). Brief physics-subpages §13, the Physics
half:

- the tabs: Entire selection by default; the mode said by the tab
  (``aria-selected``), the ``#stat-mode`` chip and the sidebar (which groups
  each subpage shows); the arrows, Home and End; ``psub`` never written for
  Entire selection;
- request isolation, read off the request log: Entire selection sends no
  ``/api/event*``; the viewer sends nothing else;
- the viewer's first draw (seed 42, draw 0, said in the caption); parking
  (back and forth with no request, the event leaving the link and coming
  back); an E₁ commit on Entire selection leaving the viewer's event, its
  caption and its N alone;
- a legacy ``#event=N`` link opening the viewer on N with no ensemble request;
  ``#psub=selection&event=N`` parking N;
- standalone hits: p and θ in the particle block, no shower B, no
  ``#stat-shower-item``; on Entire selection the attention channels and the
  models greyed with their reason as title and the ``#channel-shut`` line, the
  density drawn;
- the aggregate: the Event viewer tab shut with its reason; a ``#psub=event``
  link falling back with the kind banner's line and no ``/api/event*``;
- the header and the tab bar at 1024 and 1600 px in both themes, with no
  overflow, and the tab bar's and the chip's text legible on both.

The particle filter's own flows (the follow policy, N = 0) are in
``test_browser_event.py``, on the same subpage.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Physics subpage checks",
)

_TEXT = "(id) => document.getElementById(id).textContent"
_HIDDEN = "(id) => document.getElementById(id).hidden"
_HASH = "() => window.location.hash"
#: Rendered at all: the element and every ancestor take part in layout (CSS `display: none` anywhere hides it).
_SHOWN = "(id) => { const el = document.getElementById(id); return Boolean(el) && el.getClientRects().length > 0; }"

#: The sidebar per subpage (brief §9.2): what Entire selection shows, and what the viewer shows. The
#: Longitudinal Channels and the Colour Map steer both subpages' rasters.
SELECTION_GROUPS = ("group-filters", "group-frame", "group-resolution", "group-lgroups", "group-channel",
                    "group-colormap", "group-model")
VIEWER_GROUPS = ("group-particle", "group-event", "group-lgroups", "group-colormap")
SIDEBAR = ("group-filters", "group-frame", "group-particle", "group-event", "group-resolution", "group-lgroups",
           "group-channel", "group-colormap", "group-model", "ctl-lock-scale", "ctl-rho-norm")
#: The status bar's own items per subpage (§9.1 `data-psub-only`), by the id each holds.
SELECTION_STATUS = ("stat-events", "stat-hits", "stat-edep", "stat-clipped")
VIEWER_STATUS = ("stat-event", "stat-shower", "stat-p", "stat-theta", "stat-cells", "stat-ev-edep", "stat-place")
#: The ensemble's routes: the projections, plot 4, the model cards, the physics cards and the compare grid.
ENSEMBLE_ROUTES = ("/api/projections", "/api/energy-distribution", "/api/model-performance", "/api/response",
                   "/api/profiles", "/api/correlations", "/api/statistics", "/api/window-axis", "/api/layer-profile")
SELECTION_KEYS = ("e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d")
TAB_TITLES = {
    "selection": ("Every selected event: the 2 × 2 diagnostic, the compare-frames view and the physics cards, "
                  "under E₁, E₂ and D."),
    "event": ("One event at a time, drawn from the whole experiment under the particle filter: one shower in the "
              "Absolute, per-shower translated and Local frames."),
}
#: physics-subpages §6 and §9.3.
SINGLE_P_HINT = "Incident momentum of the shower (incoming_momentum), in GeV."
TWO_P_HINT = "Incident momentum of either shower (incoming_momentum_A or _B), in GeV."
#: WCAG's text floor, as test_browser_theme.py holds the chrome to it.
TEXT_FLOOR = 4.5

#: One element's text against the ground it is painted on (its own and its ancestors' backgrounds, composited),
#: the alpha of its ink and every ancestor's opacity applied.
_CONTRAST = """(id) => {
  const parse = (c) => { const m = c && c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3]));
  const lum = (rgb) => { const [r, g, b] = rgb.map((v) => { const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const el = document.getElementById(id);
  const layers = [];
  for (let a = el; a; a = a.parentElement) {
    const c = parse(getComputedStyle(a).backgroundColor);
    if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
  }
  let ground = parse(getComputedStyle(document.documentElement).backgroundColor);
  if (!ground || ground[3] < 1) ground = [255, 255, 255, 1];
  ground = ground.slice(0, 3);
  for (const layer of layers.reverse()) ground = over(layer, ground);
  let opacity = 1;
  for (let a = el; a; a = a.parentElement) opacity *= Number(getComputedStyle(a).opacity);
  const ink = parse(getComputedStyle(el).color);
  const drawn = over([ink[0], ink[1], ink[2], ink[3] * opacity], ground);
  const [x, y] = [lum(drawn), lum(ground)].sort((p, q) => q - p);
  return { ratio: Math.round(((x + 0.05) / (y + 0.05)) * 100) / 100, color: getComputedStyle(el).color };
}"""


# ------------------------------------------------------------------ helpers --


def _open(p, base, fragment="", *, scheme="dark", viewport=(1600, 900), browser=None):
    """The Physics page on `fragment`, with every console error, page error and failed response recorded and
    every /api/ request logged (with what is still in flight), once the subpage on show has drawn."""
    browser = browser or p.chromium.launch()
    page = browser.new_page(color_scheme=scheme, viewport={"width": viewport[0], "height": viewport[1]})
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}")
            if r.status >= 400 and "/api/" in r.url else None)
    net = {"urls": [], "pending": set()}

    def sent(request):
        if "/api/" in request.url:
            net["urls"].append(request.url)
            net["pending"].add(request)

    page.on("request", sent)
    page.on("requestfinished", lambda r: net["pending"].discard(r))
    page.on("requestfailed", lambda r: net["pending"].discard(r))
    page.goto(f"{base}/{fragment}")
    page.wait_for_function(
        """() => document.getElementById('stat-mode')?.textContent === 'Event viewer'
          ? (document.getElementById('event-grid-label').textContent !== '—'
             || !document.getElementById('event-empty').hidden)
          : document.getElementById('stat-events').textContent !== '—'""", timeout=30_000)
    _idle(page, net)
    return browser, page, problems, net


def _idle(page, net, quiet_ms=500, timeout_ms=30_000):
    """Wait until no /api/ request has been in flight for `quiet_ms`."""
    waited = quiet = 0
    while quiet < quiet_ms:
        if waited > timeout_ms:
            raise AssertionError(f"requests still in flight: {[r.url for r in net['pending']]}")
        page.wait_for_timeout(100)
        waited += 100
        quiet = quiet + 100 if not net["pending"] else 0


def _paths(urls):
    return [urlparse(u).path for u in urls]


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _fragment(page):
    text = page.evaluate(_HASH).lstrip("#")
    return {k: v[0] for k, v in parse_qs(text).items()}


def _wait_event(page):
    page.wait_for_function("() => document.getElementById('event-grid-label').textContent !== '—'", timeout=30_000)
    page.wait_for_function(
        "() => ['lab','trans','local'].every((r) => ['xy','xz','yz'].every((c) => "
        "document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))", timeout=30_000)


def _tabs(page):
    """Each tab's aria-selected, tabindex, aria-disabled, class list and title."""
    return page.evaluate("""() => Object.fromEntries(['selection', 'event'].map((s) => {
      const b = document.getElementById('psub-tab-' + s);
      return [s, { selected: b.getAttribute('aria-selected'), tabindex: b.tabIndex,
                   disabled: b.getAttribute('aria-disabled'), classes: b.className, title: b.title }]; }))""")


def _mode(page):
    """Everything that says which subpage is on show."""
    return {
        "chip": page.evaluate(_TEXT, "stat-mode"),
        "app": page.evaluate("() => document.querySelector('.app').dataset.psub"),
        "panels": {s: page.evaluate(_HIDDEN, f"psub-{s}") for s in ("selection", "event")},
        "tabs": {s: (t["selected"], t["tabindex"]) for s, t in _tabs(page).items()},
        "focus": page.evaluate("() => document.activeElement?.id ?? null"),
    }


def _assert_on(page, psub):
    other = "event" if psub == "selection" else "selection"
    got = _mode(page)
    assert got["chip"] == {"selection": "Entire selection", "event": "Event viewer"}[psub], got
    assert got["app"] == psub, got
    assert got["panels"] == {psub: False, other: True}, got
    assert got["tabs"] == {psub: ("true", 0), other: ("false", -1)}, got
    return got


def _assert_sidebar(page, psub):
    shown = {g for g in SIDEBAR if page.evaluate(_SHOWN, g)}
    want = set(SELECTION_GROUPS if psub == "selection" else VIEWER_GROUPS)
    # ρ-norm shows only in a co-registered frame, so on Entire selection it is not asserted either way.
    if psub == "selection":
        shown.discard("ctl-rho-norm")
        want |= {"ctl-lock-scale"}
    assert shown == want, (psub, sorted(shown), sorted(want))
    status = {i for i in SELECTION_STATUS + VIEWER_STATUS if page.evaluate(_SHOWN, i)}
    assert status == set(SELECTION_STATUS if psub == "selection" else VIEWER_STATUS), (psub, sorted(status))


def _experiment(base, table):
    return next(e for e in httpx.get(f"{base}/api/experiments", timeout=30).json()["experiments"]
                if e["table_name"] == table)


# ---------------------------------------------------------------- the tabs --


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_tabs_say_the_mode_in_the_tab_the_chip_and_the_sidebar(physics_live_server, scheme):
    """Entire selection by default, `psub` unwritten; the Event viewer tab switches the tab's aria-selected and
    roving tabindex, the `.app` attribute, the chip, the two wrappers, the sidebar's groups and the status bar's
    items, and writes `psub=event`; back, `psub` leaves the link. The tabs keep the markup's titles, and the
    chip's and both tabs' text clear 4.5:1 on their ground in either theme."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}", scheme=scheme)
        assert page.evaluate("() => document.documentElement.dataset.theme ?? null") in (scheme, None)
        _assert_on(page, "selection")
        _assert_sidebar(page, "selection")
        assert "psub" not in _fragment(page), page.evaluate(_HASH)
        assert {s: t["title"] for s, t in _tabs(page).items()} == TAB_TITLES
        legible = {"chip": page.evaluate(_CONTRAST, "stat-mode"),
                   "selected": page.evaluate(_CONTRAST, "psub-tab-selection"),
                   "unselected": page.evaluate(_CONTRAST, "psub-tab-event")}

        page.click("#psub-tab-event")
        _wait_event(page)
        _idle(page, net)
        _assert_on(page, "event")
        _assert_sidebar(page, "event")
        assert _fragment(page).get("psub") == "event", page.evaluate(_HASH)
        legible["viewer chip"] = page.evaluate(_CONTRAST, "stat-mode")
        legible["viewer selected"] = page.evaluate(_CONTRAST, "psub-tab-event")

        page.click("#psub-tab-selection")
        _idle(page, net)
        _assert_on(page, "selection")
        _assert_sidebar(page, "selection")
        assert "psub" not in _fragment(page) and "event" not in _fragment(page), page.evaluate(_HASH)
        browser.close()
    for where, got in legible.items():
        assert got["ratio"] >= TEXT_FLOOR, (scheme, where, got)
    assert problems == [], problems


def test_the_arrows_home_and_end_move_between_the_tabs(physics_live_server):
    """WAI-ARIA tabs with automatic activation: ArrowRight and ArrowLeft move (and wrap), End and Home jump; the
    focus follows the tab on show, and `psub` is written for the viewer only."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}")
        page.focus("#psub-tab-selection")
        for key, psub in (("ArrowRight", "event"), ("ArrowLeft", "selection"), ("ArrowLeft", "event"),
                          ("ArrowRight", "selection"), ("End", "event"), ("Home", "selection")):
            page.keyboard.press(key)
            got = _assert_on(page, psub)
            assert got["focus"] == f"psub-tab-{psub}", (key, got)
            written = _fragment(page).get("psub")
            assert written == ("event" if psub == "event" else None), (key, page.evaluate(_HASH))
            _idle(page, net)
        browser.close()
    assert problems == [], problems


# --------------------------------------------------------- request isolation --


def test_entire_selection_asks_no_event_route_and_the_viewer_asks_nothing_else(physics_live_server):
    """Read off the request log: Entire selection's boot, an E₁ commit and its cards scrolled into view send no
    /api/event* request; the viewer's first draw, a step, a shower and a Longitudinal Channels change send only
    /api/event* requests, and every one says basis=experiment with no E₁/E₂/D key."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}")
        page.fill("#e1-num-lo", "3")
        page.press("#e1-num-lo", "Enter")
        _idle(page, net)
        page.evaluate("() => { const m = document.querySelector('.main'); m.scrollTop = m.scrollHeight; }")
        page.wait_for_timeout(800)
        _idle(page, net)
        selection = _paths(net["urls"])
        assert "/api/projections" in selection, selection
        assert not [u for u in selection if u.startswith("/api/event")], selection

        start = len(net["urls"])
        page.click("#psub-tab-event")
        _wait_event(page)
        _idle(page, net)
        step = "#event-prev" if not page.is_disabled("#event-prev") else "#event-next"
        page.click(step)
        _idle(page, net)
        _wait_event(page)
        page.check('input[name="event-shower"][value="b"]')
        _idle(page, net)
        # Pooled is an ensemble operator: chosen in the viewer it asks for nothing until Entire selection is back.
        page.check("#lgmode-pool")
        _idle(page, net)
        page.evaluate("() => { const m = document.querySelector('.main'); m.scrollTop = m.scrollHeight; }")
        page.wait_for_timeout(800)
        _idle(page, net)
        viewer = net["urls"][start:]
        assert viewer, "the viewer asked for nothing"
        assert set(_paths(viewer)) <= {"/api/event/candidates", "/api/event/pick", "/api/event"}, viewer
        assert not [u for u in _paths(viewer) if u in ENSEMBLE_ROUTES], viewer
        for url in viewer:
            query = _query(url)
            assert query.get("basis") == "experiment" and not set(SELECTION_KEYS) & set(query), url
        browser.close()
    assert problems == [], problems


# ----------------------------------------------- first draw, parking, E₁ --


def test_the_first_draw_parking_and_an_e1_commit_that_leaves_the_viewer_alone(physics_live_server):
    """Entering the viewer with no event draws Pick for me at seed 42, draw 0, and the caption says so; the status
    bar is the event's (eventStatus, §8). Back to Entire selection parks the event (the link loses it and `psub`)
    with no request; back again restores it, written, with no request. An E₁ commit on Entire selection asks for
    the ensemble alone and leaves the viewer's event, its caption and its N as they were."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}")
        start = len(net["urls"])
        page.click("#psub-tab-event")
        _wait_event(page)
        _idle(page, net)
        entered = net["urls"][start:]
        assert _paths(entered) == ["/api/event/candidates", "/api/event/pick", "/api/event"], entered
        pick = _query(entered[1])
        assert (pick["rule"], pick["seed"], pick["draw"], pick["basis"]) == ("uniform", "42", "0", "experiment"), pick
        caption = page.evaluate(_TEXT, "event-caption")
        assert "(seed 42, draw 0)" in caption, caption
        n = int(page.input_value("#event-number"))
        assert _query(entered[2])["event_number"] == str(n)
        # The status bar, from the response the page drew.
        body = httpx.get(f"{base}/api/event", params=_query(entered[2]), timeout=30).json()
        shower, cands = body["event"]["shower"], body["event"]["candidates"]
        status = {i: page.evaluate(_TEXT, i).strip() for i in VIEWER_STATUS}
        assert status["stat-event"] == f"{n:,}", status
        assert status["stat-shower"] == shower["label"], status
        assert status["stat-p"] == f"{shower['momentum_gev']:.2f} GeV", status
        assert status["stat-theta"] == f"{shower['theta_deg']:.1f}°", status
        assert status["stat-cells"] == f"{shower['n_hits']:,}", status
        assert status["stat-ev-edep"].endswith(" GeV"), status
        assert status["stat-place"] == f"{cands['index'] + 1} of {cands['n_events']}", status
        count = page.evaluate(_TEXT, "particle-count")
        label = page.evaluate(_TEXT, "event-grid-label")

        # Parking: back to Entire selection and forth, with no request.
        start = len(net["urls"])
        page.click("#psub-tab-selection")
        _idle(page, net)
        hash_ = _fragment(page)
        assert "event" not in hash_ and "psub" not in hash_, hash_
        page.click("#psub-tab-event")
        _idle(page, net)
        assert net["urls"][start:] == [], net["urls"][start:]
        hash_ = _fragment(page)
        assert hash_.get("event") == str(n) and hash_.get("psub") == "event", hash_
        assert page.evaluate(_TEXT, "event-caption") == caption
        assert page.evaluate(_TEXT, "event-grid-label") == label

        # An E₁ commit on Entire selection: the ensemble alone; the viewer's event, caption and N untouched.
        page.click("#psub-tab-selection")
        _idle(page, net)
        events_before = page.evaluate(_TEXT, "stat-events")
        start = len(net["urls"])
        page.fill("#e1-num-lo", "3")
        page.press("#e1-num-lo", "Enter")
        page.wait_for_function("(before) => document.getElementById('stat-events').textContent !== before",
                               arg=events_before, timeout=30_000)
        _idle(page, net)
        committed = _paths(net["urls"][start:])
        assert "/api/projections" in committed, committed
        assert not [u for u in committed if u.startswith("/api/event")], committed
        assert "e1_min" in _fragment(page)

        start = len(net["urls"])
        page.click("#psub-tab-event")
        _idle(page, net)
        assert net["urls"][start:] == [], net["urls"][start:]
        assert page.input_value("#event-number") == str(n)
        assert page.evaluate(_TEXT, "event-caption") == caption
        assert page.evaluate(_TEXT, "particle-count") == count
        assert page.evaluate(_TEXT, "stat-event") == f"{n:,}"
        browser.close()
    assert problems == [], problems


# ---------------------------------------------------------------- the links --


def test_a_legacy_event_link_opens_the_viewer_on_its_event(physics_live_server):
    """`#event=N` with no `psub` opens the Event viewer on N (the legacy rule): the link's event, no pick, and not
    one ensemble request."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}&event=0")
        _wait_event(page)
        _idle(page, net)
        _assert_on(page, "event")
        assert page.evaluate(_TEXT, "stat-event") == "0"
        assert page.input_value("#event-number") == "0"
        paths = _paths(net["urls"])
        assert "/api/event" in paths and "/api/event/pick" not in paths, paths
        assert not [u for u in paths if u in ENSEMBLE_ROUTES], paths
        assert "Drawn uniformly" not in page.evaluate(_TEXT, "event-caption")
        browser.close()
    assert problems == [], problems


def test_an_explicit_selection_link_parks_its_event(physics_live_server):
    """`#psub=selection&event=N`: Entire selection on show, the event parked (gone from the link, nothing of the
    viewer asked); the Event viewer tab then draws N, written, without a pick."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}&psub=selection&event=0")
        _assert_on(page, "selection")
        hash_ = _fragment(page)
        assert "event" not in hash_ and "psub" not in hash_, hash_
        assert not [u for u in _paths(net["urls"]) if u.startswith("/api/event")], net["urls"]

        start = len(net["urls"])
        page.click("#psub-tab-event")
        _wait_event(page)
        _idle(page, net)
        assert _paths(net["urls"][start:]) == ["/api/event/candidates", "/api/event"], net["urls"][start:]
        assert _query(net["urls"][-1])["event_number"] == "0"
        hash_ = _fragment(page)
        assert hash_.get("event") == "0" and hash_.get("psub") == "event", hash_
        assert page.evaluate(_TEXT, "stat-event") == "0"
        browser.close()
    assert problems == [], problems


# --------------------------------------------------------------- standalone --


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_standalone_hits_get_the_viewer_and_a_greyed_attention_with_its_reason(physics_live_server, scheme):
    """single_hits: the viewer draws its one shower (no shower B, no Shower item in the status bar), the particle
    block shows p (relabelled for one shower) and θ and counts against the experiment; on Entire selection every
    attention channel and model is shut with the server's reason as its title, `#channel-shut` says it in
    visible, legible text, and the density is drawn."""
    base = physics_live_server["base"]
    reasons = _experiment(base, SINGLE_HITS_TABLE)["capabilities"]["reasons"]
    reason = reasons.get("vox-attention") or reasons.get("energy")
    assert reason, reasons
    n_events = httpx.get(f"{base}/api/event/candidates", params={"table_name": SINGLE_HITS_TABLE,
                         "basis": "experiment"}, timeout=30).json()["candidates"]["n_events"]
    low = httpx.get(f"{base}/api/event/candidates", params={"table_name": SINGLE_HITS_TABLE, "basis": "experiment",
                    "particle_p_max": 3}, timeout=30).json()["candidates"]["n_events"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={SINGLE_HITS_TABLE}&psub=event", scheme=scheme)
        _wait_event(page)
        _idle(page, net)
        _assert_on(page, "event")
        assert set(_paths(net["urls"])) <= {"/api/experiments", "/api/event/candidates", "/api/event/pick",
                                            "/api/event"}, net["urls"]
        assert page.evaluate(_SHOWN, "stat-shower-item") is False
        assert page.evaluate(_SHOWN, "stat-p") and page.evaluate(_SHOWN, "stat-theta")
        assert not page.evaluate(
            "() => [...document.querySelectorAll('input[name=\"event-shower\"][value=\"b\"]')]"
            ".some((i) => i.getClientRects().length > 0 && !i.disabled)"), "a shower B is offered on one shower"
        caption = page.evaluate(_TEXT, "event-caption")
        assert ", p = " in caption and "E₂" not in caption and "(seed 42, draw 0)" in caption, caption
        # p and θ, p's hint for one shower; the count against the experiment's events.
        assert page.evaluate(_SHOWN, "ctl-particle-p") and page.evaluate(_SHOWN, "ctl-particle-theta")
        assert page.evaluate(_TEXT, "particle-p-hint").strip() == SINGLE_P_HINT
        assert page.evaluate(_TEXT, "particle-count") == \
            f"Particle filter off: the pickers draw from all {n_events:,} events of the experiment."
        start = len(net["urls"])
        page.fill("#pp-num-hi", "3")
        page.press("#pp-num-hi", "Enter")
        page.wait_for_function("() => document.getElementById('particle-count').textContent.startsWith('N = ')",
                               timeout=30_000)
        _idle(page, net)
        assert page.evaluate(_TEXT, "particle-count") == (
            f"N = {low:,} event{'s' if low != 1 else ''} whose shower has p ≤ 3.00 GeV, "
            f"of the {n_events:,} events of the experiment.")
        assert set(_paths(net["urls"][start:])) <= {"/api/event/candidates", "/api/event/pick", "/api/event"}

        # Entire selection: the attention shut with its reason, the density drawn.
        page.click("#psub-tab-selection")
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
        page.wait_for_function("() => ['plot-xy','plot-yz','plot-xz'].every((id) => "
                               "document.getElementById(id)?.querySelector('canvas'))", timeout=30_000)
        _idle(page, net)
        _assert_on(page, "selection")
        shut = page.evaluate(
            """() => [...document.querySelectorAll('input[name="channel"], input[name="model"]')].map((i) =>
              ({ name: i.name, value: i.value, disabled: i.disabled, checked: i.checked,
                 title: i.closest('label')?.getAttribute('title') ?? null }))""")
        channels = {c["value"]: c for c in shut if c["name"] == "channel"}
        models = {c["value"]: c for c in shut if c["name"] == "model"}
        assert channels["density"]["checked"] and not channels["density"]["disabled"], channels
        for value in ("gradcam", "gradcam_energy", "shapcam", "shapcam_energy"):
            assert channels[value]["disabled"] and channels[value]["title"] == reason, channels[value]
        for value, model in models.items():
            assert model["disabled"] and model["title"] == reason, model
        assert page.evaluate(_SHOWN, "channel-shut")
        line = page.evaluate(_TEXT, "channel-shut")
        assert line == (f"Grad-CAM and Shap-CAM, raw and energy-weighted, are not available for this experiment: "
                        f"{reason} The panels show the summed energy density."), line
        legible = page.evaluate(_CONTRAST, "channel-shut")
        assert legible["ratio"] >= TEXT_FLOOR, (scheme, legible)
        asked = [_query(u) for u in net["urls"] if urlparse(u).path == "/api/projections"]
        assert asked and all(q.get("channel") == "density" for q in asked), asked
        series = page.evaluate("() => (echarts.getInstanceByDom(document.getElementById('plot-xy'))"
                               "?.getOption().series || []).length")
        assert series > 0
        browser.close()
    assert problems == [], problems


def test_two_showers_show_the_shower_item_and_no_shut_line(physics_live_server):
    """The two-shower baseline, for contrast: the viewer's Shower item is shown, p's hint names both showers, and
    Entire selection has no `#channel-shut` line and no shut channel."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={BASELINE_TABLE}&psub=event")
        _wait_event(page)
        assert page.evaluate(_SHOWN, "stat-shower-item") is True
        assert page.evaluate(_TEXT, "particle-p-hint").strip() == TWO_P_HINT
        page.click("#psub-tab-selection")
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
        _idle(page, net)
        assert page.evaluate(_SHOWN, "channel-shut") is False
        assert not page.evaluate("() => [...document.querySelectorAll('input[name=\"channel\"]')].some((i) => i.disabled)")
        browser.close()
    assert problems == [], problems


# ---------------------------------------------------------------- aggregate --


def test_the_aggregate_shuts_the_viewer_tab_with_its_reason(physics_live_server):
    """single_events holds no hits: the Event viewer tab is shut (aria-disabled, `is-disabled`, the server's reason
    as its title) and ignores a click and the arrows; a default boot says nothing about it on the banner, and no
    /api/event* request is sent."""
    base = physics_live_server["base"]
    reason = _experiment(base, SINGLE_EVENTS_TABLE)["capabilities"]["reasons"]["event-inspector"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={SINGLE_EVENTS_TABLE}", scheme="light")
        _assert_on(page, "selection")
        tab = _tabs(page)["event"]
        assert tab["disabled"] == "true" and "is-disabled" in tab["classes"].split() and tab["title"] == reason, tab
        assert "The Event viewer is not available" not in page.evaluate(_TEXT, "kind-banner-text")
        legible = page.evaluate(_CONTRAST, "psub-tab-event")
        assert legible["ratio"] >= TEXT_FLOOR, legible
        page.click("#psub-tab-event", force=True)
        page.focus("#psub-tab-selection")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("End")
        _idle(page, net)
        _assert_on(page, "selection")
        assert "psub" not in _fragment(page)
        assert not [u for u in _paths(net["urls"]) if u.startswith("/api/event")], net["urls"]
        browser.close()
    assert problems == [], problems


def test_a_viewer_link_to_the_aggregate_falls_back_with_the_banner_line(physics_live_server):
    """`#psub=event` on the aggregate: Entire selection is shown and written (no `psub` in the link), the kind
    banner says why, and no /api/event* request is sent."""
    base = physics_live_server["base"]
    reason = _experiment(base, SINGLE_EVENTS_TABLE)["capabilities"]["reasons"]["event-inspector"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open(p, base, f"#table_name={SINGLE_EVENTS_TABLE}&psub=event")
        page.wait_for_function("() => document.getElementById('kind-banner').hidden === false", timeout=30_000)
        _idle(page, net)
        _assert_on(page, "selection")
        assert (f"The Event viewer is not available for this experiment: {reason} Showing Entire selection."
                in page.evaluate(_TEXT, "kind-banner-text"))
        assert "psub" not in _fragment(page), page.evaluate(_HASH)
        assert not [u for u in _paths(net["urls"]) if u.startswith("/api/event")], net["urls"]
        assert page.evaluate(_HIDDEN, "banner") is True
        browser.close()
    assert problems == [], problems


# ------------------------------------------------------------------- layout --

#: The tab bar against `.main`: no overflow, both tabs on one line inside it, and the head's top before and after
#: `.main` is scrolled (it is sticky).
_TAB_BAR = """() => {
  const main = document.querySelector('.main');
  const head = document.getElementById('physics-head');
  const nav = document.getElementById('physics-subnav');
  const tabs = [...nav.querySelectorAll('[role="tab"]')].map((t) => t.getBoundingClientRect());
  const m = main.getBoundingClientRect();
  const before = head.getBoundingClientRect().top - m.top;
  main.scrollTop = 600;
  const after = head.getBoundingClientRect().top - m.top;
  const scrolled = main.scrollTop;
  main.scrollTop = 0;
  return {
    navOverflow: nav.scrollWidth - nav.clientWidth, headOverflow: head.scrollWidth - head.clientWidth,
    mainOverflow: main.scrollWidth - main.clientWidth,
    page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    oneLine: Math.max(...tabs.map((r) => r.top)) < Math.min(...tabs.map((r) => r.bottom)),
    inside: tabs.every((r) => r.left >= m.left - 0.5 && r.right <= m.right + 0.5),
    before, after, scrolled,
  };
}"""


@pytest.mark.parametrize("viewport", [(1024, 768), (1600, 900)], ids=lambda v: f"{v[0]}x{v[1]}")
def test_the_header_and_the_tab_bar_hold_at_1024_and_1600_in_both_themes(physics_live_server, viewport):
    """On either subpage, in either theme: the header keeps its two rows with nothing overflowing (the rule
    test_browser_theme.py holds), the tab bar holds both tabs on one line inside `.main` with no overflow, the
    page never scrolls sideways, and the tab bar stays at the top of `.main` when it scrolls."""
    from test_browser_theme import _HEADER, _assert_two_rows

    base = physics_live_server["base"]
    got = {}
    with physics_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("dark", "light"):
            for psub in ("selection", "event"):
                fragment = f"#table_name={BASELINE_TABLE}" + ("&psub=event" if psub == "event" else "")
                _, page, problems, net = _open(p, base, fragment, scheme=scheme, viewport=viewport, browser=browser)
                if psub == "event":
                    _wait_event(page)
                _assert_on(page, psub)
                got[(scheme, psub)] = {"header": page.evaluate(_HEADER), "bar": page.evaluate(_TAB_BAR)}
                assert problems == [], (scheme, psub, problems)
                page.close()
        browser.close()
    for key, measured in got.items():
        _assert_two_rows(measured["header"], key, wide=viewport[0] >= 1600)
        bar = measured["bar"]
        assert bar["navOverflow"] <= 0 and bar["headOverflow"] <= 0 and bar["mainOverflow"] <= 0, (key, bar)
        assert bar["page"] <= 0, (key, bar)
        assert bar["oneLine"] and bar["inside"], (key, bar)
        assert abs(bar["before"]) <= 1, (key, bar)
        if bar["scrolled"] > 0:
            assert abs(bar["after"]) <= 1, f"the tab bar scrolled away: {key} {bar}"
    heights = {key: m["header"]["height"] for key, m in got.items()}
    assert len(set(heights.values())) == 1, heights
