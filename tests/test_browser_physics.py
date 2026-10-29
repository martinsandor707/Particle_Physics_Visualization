"""The Physics page's physics section, driven in Chromium on every kind it serves.

Below the 2 x 2 diagnostic sit nine cards (physics_section.js), each loaded
when it scrolls into view (lazy_cards.js) and again only when its request
changes. This module boots one server holding the two-shower demonstration
experiment, the synthetic single-shower hits and event-level aggregate, and a
two-shower copy whose registry claims derived tables v1
(``physics_live_server``), and checks what a reader sees:

* no physics request is made before a card scrolls into view, and each card
  then renders without a console error, a page error or a failed request;
* a filter change reloads the cards on show and the cards scrolled to later
  ask with the new filter;
* a shut card says why in the server's words, and offers the rebuild that
  would open it;
* a load that fails on a fault that may pass (a 5xx) says so on its card
  and is asked again - on Retry, or the next time the card comes into view -
  while a refusal (422) stays the server's answer to that request;
* an experiment switch takes the previous experiment's views down: a
  response of the previous experiment that lands afterwards draws nothing,
  a frame the new radios do not offer falls back to Absolute with one line
  saying so, and Local carries over both ways;
* the event-level kind shows its notice in place of the 2 x 2, hides the
  sidebar groups that steer only the spatial panels, and counts its events;
* on single-shower hits plot 4 is the B3 small multiples on the notebook's
  windows, every slice on its canvas, and its link reaches the 1 GeV bins
  of the full-width card, which grows to hold every slice;
* every card's Details drawer opens with the four standard sections;
* every tooltip is mounted on ``#tooltip-layer``, unclipped, inside the
  viewport and on top; a bin readout sits beside the pointer, and an
  explanation leaves the hovered plot wherever there is room;
* every negative number drawn on a canvas or set as text uses U+2212.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE, STALE_TWO_TABLE

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium physics-section check",
)

#: The routes only the physics cards ask (B3 is the energy route sliced by momentum).
PHYSICS_ROUTES = ("/api/profiles", "/api/response", "/api/distributions", "/api/correlations",
                  "/api/statistics")
#: The cards each kind shows, in page order. On single-shower hits plot 4 draws B3 on the
#: notebook's windows and the full-width B3 card below holds the 1 GeV bins.
CARDS = {
    BASELINE_TABLE: ["profile-w", "profile-r", "response-b1", "response-b2", "response-res",
                     "response-b3", "distribution", "correlation", "statistics"],
    SINGLE_HITS_TABLE: ["profile-w", "profile-r", "response-b1", "response-b2", "response-res",
                        "response-b3", "distribution", "correlation", "statistics"],
    SINGLE_EVENTS_TABLE: ["response-b1", "response-b2", "response-res", "response-b3", "distribution"],
}
STANDARD_SECTIONS = ("Selection", "What is drawn", "Disclosures", "Marks and legend")
#: The sidebar groups that steer only the spatial panels (hidden on the event-level kind).
SPATIAL_GROUPS = ("group-frame", "group-resolution", "group-channel", "group-colormap")

#: A number set with the ASCII hyphen-minus: a hyphen that does not follow a
#: word character (so not "lag-1", "2026-10-25" or "1-2") and precedes a digit.
HYPHEN_NEGATIVE = re.compile(r"(?<![\w)\]])-(?=\.?\d)")

#: Every string the page draws on a canvas, recorded before any script runs.
_RECORD_CANVAS_TEXT = """(() => {
  window.__drawnText = [];
  const proto = CanvasRenderingContext2D.prototype;
  for (const name of ['fillText', 'strokeText']) {
    const original = proto[name];
    proto[name] = function (text, ...rest) {
      if (window.__drawnText.length < 400000) window.__drawnText.push(String(text));
      return original.call(this, text, ...rest);
    };
  }
})();"""

#: Where a card stands: shown, loading, drawn, or saying why it is not.
_CARD = """(id) => {
  const card = document.querySelector(`#physics-grid .card[data-panel="${id}"]`);
  if (!card) return null;
  const host = card.querySelector('.plot, .card-table');
  const message = card.querySelector('.card-error');
  const inst = host && host.classList.contains('plot') ? echarts.getInstanceByDom(host) : null;
  const option = inst ? inst.getOption() : null;
  return {
    hidden: card.hidden,
    loading: card.classList.contains('is-loading'),
    message: message && !message.hidden ? message.textContent.trim() : null,
    rebuild: Boolean(message && !message.hidden && message.querySelector('button[data-open-admin]')),
    canvas: Boolean(host && host.querySelector('canvas')),
    table: Boolean(host && host.querySelector('table')),
    series: option ? (option.series || []).length : 0,
    graphic: option ? (option.graphic || []).length : 0,
    texts: option ? (option.graphic || []).flatMap((g) => g.elements || [g]).map((g) => g.style?.text).filter(Boolean) : [],
    title: card.querySelector('.title')?.textContent ?? '',
    width: host ? host.clientWidth : 0,
    height: host ? host.clientHeight : 0,
  };
}"""

#: The union of a chart's grids in viewport pixels, and the chart's own box.
_BOXES = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const model = inst.getModel();
  const grids = (inst.getOption().grid || []).map((_, i) => model.getComponent('grid', i).coordinateSystem.getRect());
  const left = Math.min(...grids.map((g) => g.x));
  const top = Math.min(...grids.map((g) => g.y));
  const right = Math.max(...grids.map((g) => g.x + g.width));
  const bottom = Math.max(...grids.map((g) => g.y + g.height));
  return {
    chart: { left: c.left, top: c.top, right: c.right, bottom: c.bottom },
    plot: { left: c.left + left, top: c.top + top, right: c.left + right, bottom: c.top + bottom },
    grids: grids.length,
  };
}"""

#: Every grid rect of a chart, in the chart's own pixels, and the chart's size.
_GRID_RECTS = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const model = inst.getModel();
  const grids = (inst.getOption().grid || []).map((_, i) => model.getComponent('grid', i).coordinateSystem.getRect());
  return { width: inst.getWidth(), height: inst.getHeight(),
           grids: grids.map((g) => ({ x: g.x, y: g.y, w: g.width, h: g.height })) };
}"""

#: Every text a chart's graphic elements and titles state.
_CHART_TEXTS = """(plotId) => {
  const inst = echarts.getInstanceByDom(document.getElementById(plotId));
  const option = inst.getOption();
  const walk = (items) => (items || []).flatMap((g) => [g.style?.text, ...walk(g.elements || g.children)]);
  return [...walk(option.graphic), ...(option.title || []).map((t) => t.text)].filter(Boolean);
}"""

#: Remember which series the pointer is over, and whether it is a bin readout
#: (a series-level tooltip `position`: the readout placement beside the pointer).
_WATCH_HOVER = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  if (host.__probeWatched) return;
  host.__probeWatched = true;
  inst.on('mouseover', (e) => {
    const s = inst.getOption().series[e.seriesIndex];
    window.__hovered = { plot: host.id, name: e.seriesName, readout: typeof s?.tooltip?.position === 'function' };
  });
  inst.on('globalout', () => { window.__hovered = null; });
}"""

_PROBE = """() => {
  const tips = [...document.querySelectorAll('.calo-tooltip')].filter((t) => {
    const cs = getComputedStyle(t);
    const b = t.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0.5
      && b.width > 0 && b.height > 0 && t.innerText.trim().length > 0;
  });
  if (!tips.length) return null;
  const tip = tips[tips.length - 1];
  const r = tip.getBoundingClientRect();
  const previous = tip.style.pointerEvents;
  tip.style.pointerEvents = 'auto';
  const points = [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2],
                  [r.right - 2, r.bottom - 2], [(r.left + r.right) / 2, (r.top + r.bottom) / 2]];
  const onTop = points.map(([x, y]) => {
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit && (hit === tip || tip.contains(hit)));
  });
  tip.style.pointerEvents = previous;
  const clippers = [];
  for (let a = tip.parentElement; a && a !== document.documentElement; a = a.parentElement) {
    const cs = getComputedStyle(a);
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') clippers.push(a.id || a.className || a.tagName);
  }
  return {
    tip: { left: r.left, top: r.top, right: r.right, bottom: r.bottom },
    viewport: [document.documentElement.clientWidth, document.documentElement.clientHeight],
    onTop, clippers, parent: tip.parentElement.id, className: tip.className,
    hovered: window.__hovered ?? null, text: tip.innerText,
  };
}"""

#: `READOUT_GAP_PX` and `EDGE_MARGIN_PX` in static/js/panels/tooltip.js.
GAP_PX, EDGE_PX = 12, 4
#: The most of a plot a readout beside the pointer may cover (B1 and B3 measure 6-10%).
READOUT_SHARE = 0.2


# ------------------------------------------------------------------ helpers --


def _open(p, base, table, *, viewport=(1600, 900), fragment="", init=(), browser=None):
    """The page on `table`, with every console error, page error and failed request recorded.

    `init` are scripts run before the page's own; `browser` opens the page in
    a browser already launched (a second page of one test)."""
    browser = browser or p.chromium.launch()
    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    problems, requests = [], []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    page.add_init_script(_RECORD_CANVAS_TEXT)
    for script in init:
        page.add_init_script(script)
    page.goto(f"{base}/#table_name={table}{fragment}")
    page.wait_for_function(
        "(table) => document.getElementById('experiment-select')?.value === table && ("
        "!document.getElementById('kind-notice').hidden "
        "|| ['plot-xy','plot-yz','plot-xz'].every((id) => document.getElementById(id)?.querySelector('canvas')))",
        arg=table, timeout=30_000,
    )
    page.wait_for_timeout(600)
    return browser, page, problems, requests


def _settled(page, card_id, timeout=30_000):
    """Wait until a card has drawn, or says why it has not; return its state."""
    page.wait_for_function(
        f"""() => {{ const s = ({_CARD})({card_id!r});
          return s && !s.loading && (s.message !== null || s.table || (s.canvas && (s.series || s.graphic))); }}""",
        timeout=timeout,
    )
    page.wait_for_timeout(120)
    return page.evaluate(_CARD, card_id)


def _scroll_to(page, card_id):
    page.locator(f'#physics-grid .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
    return _settled(page, card_id)


def _shown_cards(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#physics-grid .card')].filter((c) => !c.hidden).map((c) => c.dataset.panel)"
    )


def _route_requests(requests, route, **params):
    """The recorded requests of one route, optionally with the given query values."""
    out = []
    for url in requests:
        parsed = urlparse(url)
        if parsed.path != route:
            continue
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if all(query.get(k) == v for k, v in params.items()):
            out.append(query)
    return out


def _digits(text) -> int | None:
    """An integer readout as the status bar sets it (thin-space or comma grouping), or None."""
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _hyphen_negatives(texts):
    return sorted({t for t in texts if HYPHEN_NEGATIVE.search(t)})


def _overlap(a, b) -> float:
    return max(0.0, min(a["right"], b["right"]) - max(a["left"], b["left"])) * max(
        0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))


def _room_outside(tip, around, vw, vh):
    """Whether a tip of this size fits on some side of `around` inside the viewport."""
    w, h = tip["right"] - tip["left"], tip["bottom"] - tip["top"]
    fits_w, fits_h = w <= vw - 2 * EDGE_PX, h <= vh - 2 * EDGE_PX
    return ((around["right"] + GAP_PX + w <= vw - EDGE_PX and fits_h)
            or (around["left"] - GAP_PX - w >= EDGE_PX and fits_h)
            or (around["bottom"] + GAP_PX + h <= vh - EDGE_PX and fits_w)
            or (around["top"] - GAP_PX - h >= EDGE_PX and fits_w))


def _beside(tip, x, y) -> bool:
    """Right or left of the pointer by the gap, or above or below it by the gap."""
    horizontal = abs(tip["left"] - (x + GAP_PX)) < 1.5 or abs(tip["right"] - (x - GAP_PX)) < 1.5
    vertical = (abs(tip["bottom"] - (y - GAP_PX)) < 1.5 or abs(tip["top"] - (y + GAP_PX)) < 1.5) \
        and tip["left"] - 0.5 <= x <= tip["right"] + 0.5
    return horizontal or vertical


def _hover_chart(page, plot_id, columns=9, rows=6):
    """Hover a grid of points over a chart's plot area; every tooltip that showed, probed."""
    page.locator(f"#{plot_id}").scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    page.evaluate(_WATCH_HOVER, plot_id)
    boxes = page.evaluate(_BOXES, plot_id)
    plot = boxes["plot"]
    found = []
    for i in range(columns):
        for j in range(rows):
            x = plot["left"] + (i + 0.5) / columns * (plot["right"] - plot["left"])
            y = plot["top"] + (j + 0.5) / rows * (plot["bottom"] - plot["top"])
            page.mouse.move(x, y)
            page.wait_for_timeout(35)
            probe = page.evaluate(_PROBE)
            if probe is not None:
                found.append(((x, y), probe, boxes))
    page.mouse.move(2, 2)
    page.wait_for_timeout(60)
    return found


def _check_tips(found, where):
    """The tooltip rules of CLAUDE.md and test_browser_tooltip.py, for one chart."""
    readouts = explanations = 0
    for (x, y), probe, boxes in found:
        at = f"{where} at ({x:.0f}, {y:.0f}): {probe['text'][:70]!r}"
        tip, (vw, vh) = probe["tip"], probe["viewport"]
        assert probe["className"] == "calo-tooltip", at
        assert probe["parent"] == "tooltip-layer", f"{at}: mounted in {probe['parent']!r}"
        assert probe["clippers"] == [], f"{at}: clipped by {probe['clippers']}"
        assert tip["left"] >= -0.5 and tip["top"] >= -0.5 and tip["right"] <= vw + 0.5 \
            and tip["bottom"] <= vh + 0.5, f"{at}: tooltip {tip} leaves the viewport"
        assert all(probe["onTop"]), f"{at}: something is drawn over the tooltip"
        assert not (tip["left"] <= x <= tip["right"] and tip["top"] <= y <= tip["bottom"]), (
            f"{at}: the tooltip sits on the pointer")
        if (probe["hovered"] or {}).get("readout"):
            readouts += 1
            assert _beside(tip, x, y), f"{at}: the bin readout left the pointer ({tip})"
            # Only a short readout may sit on the plot: a bin summary leaves it.
            plot = boxes["plot"]
            area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
            assert _overlap(tip, plot) <= READOUT_SHARE * area, f"{at}: a readout covers much of the plot ({tip})"
        else:
            explanations += 1
            if _room_outside(tip, boxes["chart"], vw, vh):
                assert _overlap(tip, boxes["chart"]) < 0.5, f"{at}: an explanation covers the chart it explains"
            elif _room_outside(tip, boxes["plot"], vw, vh):
                assert _overlap(tip, boxes["plot"]) < 0.5, f"{at}: an explanation covers the plot it explains"
    return readouts, explanations


def _assert_sections(headings, where):
    """The standard sections lead, in order; a section with nothing to say is left out,
    but a drawer always says what is selected, what is drawn and how to read its marks."""
    standard = [h for h in headings if h in STANDARD_SECTIONS]
    assert headings[:len(standard)] == standard, (where, headings)
    assert standard == [h for h in STANDARD_SECTIONS if h in standard], (where, headings)
    assert {"Selection", "What is drawn", "Marks and legend"} <= set(standard), (where, headings)


def _experiments(base):
    listed = httpx.get(f"{base}/api/experiments", timeout=30).json()["experiments"]
    return {e["table_name"]: e for e in listed}


# -------------------------------------------------------------- the loading --


def test_no_card_asks_before_it_scrolls_into_view(physics_live_server):
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, physics_live_server["base"], BASELINE_TABLE)
        page.wait_for_timeout(800)
        before = [u for u in requests if urlparse(u).path in PHYSICS_ROUTES
                  or "slice_by=momentum" in u]
        assert before == [], f"physics requests before any card was in view: {before}"
        assert page.evaluate("() => document.querySelector('.main').scrollTop") == 0

        state = _scroll_to(page, "profile-w")
        assert state["canvas"] and state["series"], state
        assert _route_requests(requests, "/api/profiles"), requests
        # The cards further down have not asked yet.
        assert not _route_requests(requests, "/api/statistics"), requests
        assert not _route_requests(requests, "/api/correlations"), requests

        # One /api/profiles response feeds both profile cards: no second request.
        n_profiles = len(_route_requests(requests, "/api/profiles"))
        _scroll_to(page, "profile-r")
        assert len(_route_requests(requests, "/api/profiles")) == n_profiles
        browser.close()
    assert problems == []


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_every_card_renders_and_opens_its_drawer(physics_live_server, table):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, table)
        assert _shown_cards(page) == CARDS[table]
        for card_id in CARDS[table]:
            state = _scroll_to(page, card_id)
            where = f"{table} {card_id}"
            assert state["message"] is None, f"{where}: {state['message']}"
            if card_id == "response-b3" and not state["series"]:
                # The two-event demonstration puts no shower in any notebook window:
                # one line says so, in a short card, with no empty density grid.
                assert state["texts"] == ["No showers of this selection fall in any momentum slice."], state
                assert 60 < state["height"] < 200, state
            else:
                assert state["width"] > 200 and state["height"] > 100, (where, state)
            if card_id == "statistics":
                assert state["table"], where
            else:
                assert state["canvas"] and (state["series"] or state["graphic"]), (where, state)

            # The Details drawer: the card's title, the four standard sections.
            page.click(f'#physics-grid button[data-inspect="{card_id}"]')
            assert page.evaluate("() => document.getElementById('inspector').hidden") is False
            assert page.inner_text("#inspector-title") == state["title"], where
            headings = page.evaluate(
                "() => [...document.querySelectorAll('#inspector-body .inspector-section h3')].map((h) => h.textContent)")
            _assert_sections(headings, where)
            assert page.get_attribute(f'#physics-grid button[data-inspect="{card_id}"]', "aria-expanded") == "true"
            page.keyboard.press("Escape")
            assert page.evaluate("() => document.getElementById('inspector').hidden") is True, where
        browser.close()
    assert problems == [], problems


def test_the_cards_follow_a_filter_change(physics_live_server):
    base = physics_live_server["base"]
    bodies = []
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE)
        page.on("response", lambda r: bodies.append(r.json()) if urlparse(r.url).path == "/api/response" else None)
        _scroll_to(page, "response-b1")
        assert _route_requests(requests, "/api/response")
        first = _route_requests(requests, "/api/response")[-1]
        # One filter axis, p: E2, D and the undefined-D switch are never sent.
        assert not {"e2_min", "e2_max", "d_min", "d_max", "include_undefined_d"} & set(first), first
        assert first.get("e1_min") != "10", first

        # Narrow p from the sidebar's number field, as a reader types it.
        page.fill("#e1-num-lo", "10")
        page.press("#e1-num-lo", "Enter")
        page.wait_for_function(
            "() => [...performance.getEntriesByType('resource')].some((e) => "
            "e.name.includes('/api/response') && e.name.includes('e1_min=10'))",
            timeout=30_000,
        )
        state = _settled(page, "response-b1")
        assert state["message"] is None, state
        later = _route_requests(requests, "/api/response", e1_min="10")
        assert later, requests
        assert all(k not in later[-1] for k in ("e2_min", "e2_max", "d_min", "d_max", "include_undefined_d"))
        # Plot 4's response grid follows the same filter.
        assert _route_requests(requests, "/api/energy-distribution", slice_by="momentum", e1_min="10")

        # The drawn response narrowed with it.
        page.wait_for_timeout(300)
        assert len(bodies) >= 2
        n_before = bodies[0]["b1"]["series"][0]["n"]
        n_after = bodies[-1]["b1"]["series"][0]["n"]
        assert bodies[-1]["filter"]["e1"][0] == pytest.approx(10.0)
        assert 0 < n_after < n_before, (n_before, n_after)

        # A card scrolled to after the change asks with the new filter.
        assert not _route_requests(requests, "/api/statistics")
        _scroll_to(page, "statistics")
        asked = _route_requests(requests, "/api/statistics")
        assert asked and asked[0].get("e1_min") == "10", asked
        browser.close()
    assert problems == [], problems


# --------------------------------------------------------- faults and retry --


def _fail_once(page, route, status, detail):
    """Answer `route`'s first request with `status` and a problem `detail`; let every later one through."""
    calls = []

    def handle(r):
        calls.append(r.request.url)
        if len(calls) == 1:
            r.fulfill(status=status, content_type="application/problem+json",
                      body=f'{{"title": "Probe", "status": {status}, "detail": "{detail}"}}')
        else:
            r.continue_()

    page.route(f"**{route}?*", handle)
    return calls


def _expected(problems, *routes):
    """The problems a test caused on purpose taken out: the failed responses of `routes`, Chromium's
    console line for each, and the page's own log of the probe's failures."""
    return [m for m in problems if not any(r in m for r in routes)
            and not ("Failed to load resource" in m and "status of" in m)
            and not (m.startswith("console.error: [calosrv]") and "Probe " in m)]


def _scroll_top(page):
    page.evaluate("() => document.querySelector('.main').scrollTo(0, 0)")
    page.wait_for_timeout(400)


def test_a_transient_failure_is_asked_again_and_a_refusal_is_not(physics_live_server):
    """A 5xx may pass: the card says so with a Retry, and recovers on Retry or on its next
    visibility. A 422 is the server's answer to that request: no Retry, and not asked again."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE)
        profiles = _fail_once(page, "/api/profiles", 500, "Probe fault: the query failed.")
        statistics = _fail_once(page, "/api/statistics", 503, "Probe fault: busy.")
        refused = []

        def refuse(r):
            refused.append(r.request.url)
            r.fulfill(status=422, content_type="application/problem+json",
                      body='{"title": "Probe", "status": 422, "detail": "Probe refusal: this selection is refused."}')

        page.route("**/api/correlations?*", refuse)

        # 500: both profile cards (one shared request) say so in the server's words, each with a
        # Retry; neither is asked again on its own, and one Retry brings both back.
        state = _scroll_to(page, "profile-w")
        assert state["message"] and "Probe fault: the query failed." in state["message"], state
        assert not state["canvas"] or not state["series"], state
        retry = '#physics-grid .card[data-panel="profile-w"] button[data-retry]'
        assert page.locator(retry).count() == 1
        page.wait_for_timeout(800)
        assert len(profiles) == 1, profiles
        page.click(retry)
        state = _settled(page, "profile-w")
        assert state["message"] is None and state["canvas"] and state["series"], state
        state = _scroll_to(page, "profile-r")
        assert state["message"] is None and state["canvas"] and state["series"], state
        assert len(profiles) == 2, profiles

        # 503: recovers the next time the card comes into view, without a click.
        state = _scroll_to(page, "statistics")
        assert state["message"] and "Probe fault: busy." in state["message"], state
        assert page.locator('#physics-grid .card[data-panel="statistics"] button[data-retry]').count() == 1
        page.wait_for_timeout(800)
        assert len(statistics) == 1, statistics
        _scroll_top(page)
        state = _scroll_to(page, "statistics")
        assert state["message"] is None and state["table"], state
        assert len(statistics) == 2, statistics

        # 422: the refusal stays; no Retry, and coming back into view does not ask again.
        state = _scroll_to(page, "correlation")
        assert state["message"] and "Probe refusal: this selection is refused." in state["message"], state
        assert not state["canvas"] or not state["series"], state
        assert page.locator('#physics-grid .card[data-panel="correlation"] button[data-retry]').count() == 0
        _scroll_top(page)
        _scroll_to(page, "correlation")
        page.wait_for_timeout(800)
        assert len(refused) == 1, refused
        page.click('#physics-grid button[data-inspect="correlation"]')
        assert "Probe refusal" in page.evaluate("() => document.getElementById('inspector-body').textContent")
        page.keyboard.press("Escape")
        browser.close()
    assert _expected(problems, "/api/profiles", "/api/statistics", "/api/correlations") == [], problems


# ------------------------------------------------------- experiment switch --


#: Hold the responses of the routes listed in `window.__holdRoutes` until
#: `window.__release()`. The held request ignores its abort signal, as a
#: response whose headers were already in does (api.js `getJson` lets go of
#: its controller then), so only the page's own guard can keep a late
#: response of the previous experiment from drawing.
_HOLD_FETCH = """(() => {
  window.__holdRoutes = ['/api/model-performance'];
  window.__held = [];
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = String(input instanceof Request ? input.url : input);
    if (!window.__holdRoutes.some((route) => url.includes(route))) return realFetch(input, init);
    const { signal, ...rest } = init;
    return new Promise((resolve, reject) => {
      window.__held.push({ url, release: () => realFetch(input, rest).then(resolve, reject) });
    });
  };
  window.__release = () => {
    const held = window.__held.splice(0);
    held.forEach((h) => h.release());
    return held.map((h) => h.url);
  };
})();"""

#: The three spatial panels each draw a series (or the event-level kind's notice is up).
_SPATIAL_DRAWN = """(table) => document.getElementById('experiment-select').value === table && (
  !document.getElementById('kind-notice').hidden
  || ['plot-xy', 'plot-yz', 'plot-xz'].every((id) => {
    const h = document.getElementById(id); const i = h && echarts.getInstanceByDom(h);
    return i && (i.getOption().series || []).length > 0; }))"""


def _switch(page, table):
    """Choose another experiment in the sidebar and wait for its views."""
    page.select_option("#experiment-select", table)
    page.wait_for_function(_SPATIAL_DRAWN, arg=table, timeout=30_000)
    page.wait_for_timeout(600)


def _status(page):
    return page.evaluate("() => Object.fromEntries(['stat-events', 'stat-hits', 'stat-edep']"
                         ".map((id) => [id, document.getElementById(id).textContent.trim()]))")


def test_an_experiment_switch_drops_the_previous_experiments_late_responses(physics_live_server):
    """baseline -> single_hits -> single_events -> baseline, with the previous experiment's model
    performance and projections answering only after the switch: neither draws."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, init=(_HOLD_FETCH,))
        # The baseline's model performance is held.
        page.wait_for_function("() => window.__held.some((h) => h.url.includes('/api/model-performance'))",
                               timeout=30_000)

        # To single-shower hits, which asks for no model performance at all.
        _switch(page, SINGLE_HITS_TABLE)
        metrics = page.inner_text("#metrics")
        assert "carries no reconstruction-network outputs" in metrics, metrics
        hits_status = _status(page)
        assert _digits(hits_status["stat-events"]), hits_status

        # A filter change on single_hits whose projections are held past the next switch.
        page.evaluate("() => { window.__holdRoutes = ['/api/projections']; }")
        page.fill("#e1-num-lo", "10")
        page.press("#e1-num-lo", "Enter")
        page.wait_for_function("() => window.__held.some((h) => h.url.includes('/api/projections'))",
                               timeout=30_000)

        # The baseline's model performance lands now, on single_hits: it draws nothing.
        released = page.evaluate("() => { const out = window.__held.filter((h) => h.url.includes('model-performance'));"
                                 " window.__held = window.__held.filter((h) => !out.includes(h));"
                                 " out.forEach((h) => h.release()); return out.map((h) => h.url); }")
        assert released and all(BASELINE_TABLE in u for u in released), released
        page.wait_for_timeout(1500)
        assert page.inner_text("#metrics") == metrics

        # To the event-level kind; single_hits' projections land afterwards and draw nothing.
        _switch(page, SINGLE_EVENTS_TABLE)
        page.wait_for_function("() => /\\d/.test(document.getElementById('stat-events').textContent)",
                               timeout=30_000)
        events_status = _status(page)
        late = page.evaluate("() => { window.__holdRoutes = []; return window.__release(); }")
        assert late and all(SINGLE_HITS_TABLE in u and "/api/projections" in u for u in late), late
        page.wait_for_timeout(1500)
        assert _status(page) == events_status, (events_status, _status(page))
        assert events_status["stat-hits"] == "—" and events_status["stat-edep"] == "—", events_status
        asked = _route_requests(requests, "/api/response", table_name=SINGLE_EVENTS_TABLE)
        expected = httpx.get(f"{base}/api/response", params=asked[-1], timeout=30).json()["n_events"]
        assert _digits(events_status["stat-events"]) == expected, (events_status, expected)
        for plot_id in ("plot-xy", "plot-yz", "plot-xz"):
            series = page.evaluate(f"() => (echarts.getInstanceByDom(document.getElementById('{plot_id}'))"
                                   "?.getOption().series || []).length")
            assert series == 0, plot_id
        assert "carries no reconstruction-network outputs" in page.inner_text("#metrics")

        # Back to the baseline: its own views, drawn afresh.
        _switch(page, BASELINE_TABLE)
        page.wait_for_function("() => !document.getElementById('metrics').textContent.includes('Metrics unavailable')",
                               timeout=30_000)
        assert _status(page)["stat-hits"] != "—"
        browser.close()
    assert problems == [], problems


def _kind_banner(page):
    """The kind banner's text while it is on show; '' when it is not."""
    return page.evaluate("() => document.getElementById('kind-banner').hidden ? ''"
                         " : document.getElementById('kind-banner-text').innerText")


def _frame(page):
    return page.evaluate("() => document.getElementById('ctl-frame').dataset.frame")


def _choose_frame(page, view, sub=None):
    page.locator(f'input[name="frame-view"][value="{view}"]').check(force=True)
    if sub:
        page.locator(f'input[name="frame-sub"][value="{sub}"]').check(force=True)
    page.wait_for_function(_SPATIAL_DRAWN, arg=page.evaluate("() => document.getElementById('experiment-select').value"),
                           timeout=30_000)
    page.wait_for_timeout(600)


def _projections_frame(requests, table):
    asked = _route_requests(requests, "/api/projections", table_name=table)
    return (asked[-1].get("coord_system"), asked[-1].get("frame")) if asked else None


def test_the_frame_across_a_switch_of_kind(physics_live_server):
    """A frame the new experiment's radios do not offer falls back to Absolute with one line
    saying so; Local carries over both ways; a #frame=trans link still opens the legacy frame."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE, fragment="&frame=trans")
        assert _frame(page) == "trans"
        assert _projections_frame(requests, SINGLE_HITS_TABLE) == ("trans", "lab")

        # A single shower's Translated is the legacy per-shower frame on two showers: Absolute instead.
        _switch(page, BASELINE_TABLE)
        assert _frame(page) == "lab"
        assert _projections_frame(requests, BASELINE_TABLE) == ("lab", "lab")
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True
        banner = _kind_banner(page)
        assert "Translated is not offered for this experiment" in banner and "showing Absolute" in banner, banner

        # The D-frame on two showers has no single-shower radio: Absolute again, said once.
        _choose_frame(page, "aligned")
        assert _frame(page) == "canonical"
        _switch(page, SINGLE_HITS_TABLE)
        assert _frame(page) == "lab"
        assert _projections_frame(requests, SINGLE_HITS_TABLE) == ("lab", "lab")
        banner = _kind_banner(page)
        assert banner.count("is not offered for this experiment") == 1 and "showing Absolute" in banner, banner

        # Local carries over, both ways, with nothing to say.
        _choose_frame(page, "aligned", "local")
        assert _frame(page) == "local"
        _switch(page, BASELINE_TABLE)
        assert _frame(page) == "local"
        assert _projections_frame(requests, BASELINE_TABLE) == ("local", "lab")
        assert "not offered" not in _kind_banner(page)
        _switch(page, SINGLE_HITS_TABLE)
        assert _frame(page) == "local"
        assert _projections_frame(requests, SINGLE_HITS_TABLE) == ("local", "lab")
        assert "not offered" not in _kind_banner(page)

        # A link to the legacy per-shower frame still opens it on two showers.
        _, linked, more_problems, linked_requests = _open(p, base, BASELINE_TABLE, fragment="&frame=trans",
                                                          browser=browser)
        assert _frame(linked) == "trans"
        assert _projections_frame(linked_requests, BASELINE_TABLE) == ("trans", "lab")
        assert linked.evaluate("() => document.getElementById('frame-sub-trans').hidden") is False
        assert "not offered" not in _kind_banner(linked)
        browser.close()
    assert problems == [] and more_problems == [], problems + more_problems


# ----------------------------------------------------------- shut and kinds --


def test_a_stale_experiment_shuts_its_cards_with_the_servers_reason(physics_live_server):
    base = physics_live_server["base"]
    caps = _experiments(base)[STALE_TWO_TABLE]["capabilities"]
    assert caps["derived"]["status"] == "stale"
    shut = [card for card in ("profile-w", "profile-r") if not caps["panels"][card]]
    assert shut == ["profile-w", "profile-r"], caps["panels"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, STALE_TWO_TABLE)
        assert _shown_cards(page) == CARDS[BASELINE_TABLE]
        for card_id in shut:
            state = _scroll_to(page, card_id)
            assert state["message"].startswith(caps["reasons"][card_id]), state
            assert state["rebuild"], state
            assert not state["canvas"], state
            # Nothing to steer on a shut card: its controls go with its picture.
            hidden = page.evaluate(
                f"""() => [...document.querySelectorAll('#physics-grid .card[data-panel="{card_id}"] .card-actions > :not([data-inspect])')]
                    .every((el) => el.hidden || el.disabled)""")
            assert hidden, card_id
            page.click(f'#physics-grid button[data-inspect="{card_id}"]')
            assert caps["reasons"][card_id] in page.evaluate("() => document.getElementById('inspector-body').textContent")
            page.keyboard.press("Escape")
        # The open cards of the same experiment load as usual.
        state = _scroll_to(page, "response-b1")
        assert state["message"] is None and state["canvas"], state
        assert not _route_requests(requests, "/api/profiles"), "a shut card asked the server"

        # The offer opens Admin Settings, where the rebuild runs.
        _scroll_to(page, "profile-w")
        page.click('#physics-grid .card[data-panel="profile-w"] button[data-open-admin]')
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is False
        browser.close()
    assert problems == [], problems


def test_the_event_level_kind_shows_its_notice_in_place_of_the_2x2(physics_live_server):
    base = physics_live_server["base"]
    caps = _experiments(base)[SINGLE_EVENTS_TABLE]["capabilities"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_EVENTS_TABLE)
        assert page.evaluate("() => document.getElementById('kind-notice').hidden") is False
        assert page.evaluate("() => getComputedStyle(document.getElementById('ensemble-grid')).display") == "none"
        text = page.inner_text("#kind-notice-text")
        assert text.startswith(caps["reasons"]["xy"]), text
        assert page.inner_text("#kind-notice-title") == "No hits to project"
        # Missing predictions (CLAUDE.md section 3): a prominent banner, no fabricated output.
        assert page.evaluate("() => document.getElementById('kind-banner').hidden") is False
        assert "No model predictions" in page.inner_text("#kind-banner-text")
        assert _shown_cards(page) == CARDS[SINGLE_EVENTS_TABLE]
        # The sidebar groups that steer only the spatial panels are hidden, and the notice says why.
        for group in SPATIAL_GROUPS:
            assert page.evaluate(f"() => {{ const g = document.getElementById('{group}');"
                                 " return g.hidden && g.offsetParent === null; }") is True, group
        assert "hidden for this experiment" in text, text
        # The Events count, from /api/response's n_events, without a card being scrolled to.
        page.wait_for_function("() => /\\d/.test(document.getElementById('stat-events').textContent)", timeout=30_000)
        assert page.evaluate("() => document.querySelector('.main').scrollTop") == 0
        asked = _route_requests(requests, "/api/response", table_name=SINGLE_EVENTS_TABLE)
        assert asked, requests
        expected = httpx.get(f"{base}/api/response", params=asked[-1], timeout=30).json()["n_events"]
        assert _digits(page.inner_text("#stat-events")) == expected, (page.inner_text("#stat-events"), expected)
        # The count rode on the cards' own request: one /api/response for the count and B1, B2, sigma/mu.
        _scroll_to(page, "response-b2")
        assert len(_route_requests(requests, "/api/response")) == 1, _route_requests(requests, "/api/response")
        # No hit route is ever asked for an experiment without hits, and every card's
        # drawer says the aggregate is a censored sample (it drops the single-hit events).
        for card_id in CARDS[SINGLE_EVENTS_TABLE]:
            _scroll_to(page, card_id)
            page.click(f'#physics-grid button[data-inspect="{card_id}"]')
            body = page.evaluate("() => document.getElementById('inspector-body').textContent")
            assert "censored sample" in body, card_id
            page.keyboard.press("Escape")
        assert not [u for u in requests if urlparse(u).path in
                    ("/api/projections", "/api/profiles", "/api/correlations", "/api/statistics")], requests
        browser.close()
    assert problems == [], problems


def _momentum_slices(base, table, p_slices):
    """The momentum-sliced energy response the server ships for `p_slices`."""
    return httpx.get(f"{base}/api/energy-distribution",
                     params={"table_name": table, "slice_by": "momentum", "p_slices": p_slices}, timeout=30).json()


def _grids_inside(page, plot_id):
    """Every grid rect of a chart against the chart's own box: the rects outside it, and how many there are."""
    found = page.evaluate(_GRID_RECTS, plot_id)
    outside = [g for g in found["grids"]
               if g["x"] < -0.5 or g["y"] < -0.5 or g["x"] + g["w"] > found["width"] + 0.5
               or g["y"] + g["h"] > found["height"] + 0.5]
    return found, outside


def test_single_shower_plot_4_is_the_b3_small_multiples(physics_live_server):
    """Plot 4 on single-shower hits draws the notebook's six windows, which fit the 2 x 2 cell;
    the 1 GeV bins are the full-width card's, which grows to hold every slice, and plot 4's link
    takes the reader there with them selected (Martin's Phase 6 decision). At 1280 px, where the
    1 GeV bins once squeezed plot 4's sub-plots to 30 px, every slice lies on its canvas."""
    base = physics_live_server["base"]
    n_windows = len(_momentum_slices(base, SINGLE_HITS_TABLE, "notebook")["slice_axes"])
    n_bins = len(_momentum_slices(base, SINGLE_HITS_TABLE, "bins")["slice_axes"])
    assert 2 <= n_windows < n_bins, (n_windows, n_bins)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE, viewport=(1280, 900))
        page.wait_for_function(
            "() => { const h = document.getElementById('plot-energy-b3'); const i = h && echarts.getInstanceByDom(h);"
            " return i && (i.getOption().series || []).length > 0; }", timeout=30_000)
        assert page.inner_text("#title-energy").startswith("Response vs. Incident Momentum p")
        assert page.evaluate("() => document.getElementById('plot-energy').hidden") is True
        assert page.evaluate("() => document.getElementById('plot-energy-b3').hidden") is False
        assert page.evaluate("() => document.getElementById('energy-shower-toggle').hidden") is True
        # Plot 4 asks for the notebook's windows only.
        plot4 = _route_requests(requests, "/api/energy-distribution", slice_by="momentum")
        assert plot4 and {q.get("p_slices") for q in plot4} == {"notebook"}, plot4
        # Every window on the canvas, inside the 2 x 2 cell, with nothing said to be left out.
        found, outside = _grids_inside(page, "plot-energy-b3")
        assert len(found["grids"]) == n_windows and outside == [], found
        assert min(g["h"] for g in found["grids"]) >= 70, found
        cell = page.evaluate("() => { const r = document.getElementById('plot-energy-b3').getBoundingClientRect();"
                             " const x = document.getElementById('plot-xy').getBoundingClientRect();"
                             " return [r.height, x.height]; }")
        assert cell[0] <= cell[1] * 1.25, cell
        texts = page.evaluate(_CHART_TEXTS, "plot-energy-b3")
        assert not [t for t in texts if "fit at this height" in t], texts
        # Its fitted mu and sigma in the card's table; its key counts in the sparse note.
        rows = page.evaluate("() => document.querySelectorAll('#fit-table table tbody tr').length")
        assert rows >= n_windows, rows
        # Wider than the 2 x 2 cell, it scrolls inside its card instead of spilling over the next panel.
        fit = page.evaluate("() => { const h = document.getElementById('fit-table');"
                            " const c = h.closest('.card').getBoundingClientRect(); const r = h.getBoundingClientRect();"
                            " return { fits: h.scrollWidth <= h.clientWidth + 1, overflow: getComputedStyle(h).overflowX,"
                            " inside: r.left >= c.left - 0.5 && r.right <= c.right + 0.5 }; }")
        assert fit["inside"] and (fit["fits"] or fit["overflow"] in ("auto", "scroll")), fit
        assert page.evaluate("() => document.getElementById('fit-table').hidden") is False
        sparse = page.evaluate("() => { const n = document.getElementById('energy-sparse');"
                               " return { hidden: n.hidden, lines: [...n.querySelectorAll('p')].map((x) => x.textContent) }; }")
        # The synthetic shower's windows hold low-N series: their counts are on screen, not only in the drawer.
        assert not sparse["hidden"] and any("Low-statistics series" in line for line in sparse["lines"]), sparse
        assert not [line for line in sparse["lines"] if "at this height" in line], sparse

        # The full-width card is on show below, and plot 4's link reaches its 1 GeV bins.
        assert "response-b3" in _shown_cards(page)
        assert page.evaluate("() => document.getElementById('energy-b3-slices').hidden") is False
        # The card set to the windows first (without scrolling it into view), so the link has a choice to make.
        page.evaluate("() => document.querySelector('#physics-grid .card[data-panel=\"response-b3\"] "
                      "button[data-b3-slices=\"notebook\"]').click()")
        assert not _route_requests(requests, "/api/energy-distribution", slice_by="momentum", p_slices="bins")
        page.click("#energy-b3-link")
        state = _settled(page, "response-b3")
        assert state["message"] is None and state["series"], state
        assert _route_requests(requests, "/api/energy-distribution", slice_by="momentum", p_slices="bins")
        active = page.evaluate("() => [...document.querySelectorAll('#physics-grid .card[data-panel=\"response-b3\"] "
                               "button[data-b3-slices].is-active')].map((b) => b.dataset.b3Slices)")
        assert active == ["bins"], active
        # Scrolled to, with its Details button holding the focus.
        place = page.evaluate("() => { const c = document.querySelector('#physics-grid .card[data-panel=\"response-b3\"]');"
                              " return { top: c.getBoundingClientRect().top, focus: document.activeElement?.dataset?.inspect ?? null }; }")
        assert -1 <= place["top"] < 900 * 0.5 and place["focus"] == "response-b3", place
        # Every 1 GeV bin on the card's canvas: the card grew to hold them.
        found, outside = _grids_inside(page, "plot-response-b3")
        assert len(found["grids"]) == n_bins and outside == [], found
        assert min(g["h"] for g in found["grids"]) >= 70, found
        assert page.evaluate("() => document.querySelectorAll('#fit-table-response-b3 table tbody tr').length") >= n_bins
        # The bins never reach plot 4.
        assert len(page.evaluate(_GRID_RECTS, "plot-energy-b3")["grids"]) == n_windows

        page.click('button[data-inspect="energy"]')
        assert page.inner_text("#inspector-title") == "Response vs. Incident Momentum p"
        headings = page.evaluate(
            "() => [...document.querySelectorAll('#inspector-body .inspector-section h3')].map((h) => h.textContent)")
        _assert_sections(headings, "plot 4")
        assert "Reading the density axis" in headings
        browser.close()
    assert problems == [], problems


def test_single_shower_frames_are_worded_for_one_shower(physics_live_server):
    base = physics_live_server["base"]
    payload = httpx.get(f"{base}/api/projections", params={"table_name": SINGLE_HITS_TABLE, "coord_system": "local"},
                        timeout=30).json()
    block = payload["frame"]["negative_w"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE, fragment="&frame=local")
        page.wait_for_function("() => !document.getElementById('stat-wneg-item').hidden", timeout=30_000)
        # p alone: E2, D and the undefined-D switch are hidden and never sent.
        for control in ("ctl-e2", "ctl-d", "ctl-undefined-d"):
            assert page.evaluate(f"() => document.getElementById('{control}').hidden") is True, control
        assert page.inner_text("#e1-label").startswith("p")
        # C9 in the status bar: the Local frame's share behind the entry plane, its summary on hover.
        assert "%" in page.inner_text("#stat-wneg")
        assert block["summary"] in page.get_attribute("#stat-wneg-item", "title")
        for panel_id in ("yz", "xz"):
            title = page.inner_text(f"#title-{panel_id}")
            assert "Shower-Aligned" in title and "D-Frame" not in title, title
            page.click(f'button[data-inspect="{panel_id}"]')
            assert page.inner_text("#inspector-title") == title
            body = page.evaluate("() => document.getElementById('inspector-body').textContent")
            assert "Hits behind their shower's entry plane" in body
            assert "Shower B" not in body and "separation D" not in body
            page.keyboard.press("Escape")
        # Every spatial drawer - the text a manuscript caption is taken from - names the
        # single shower's frames, never the two-shower D-frame or the legacy frame.
        for frame in ("local", "trans"):
            if frame == "trans":
                with page.expect_response(lambda r: urlparse(r.url).path == "/api/projections"
                                          and "coord_system=trans" in r.url, timeout=30_000):
                    page.locator('input[name="frame-sub"][value="trans"]').check(force=True)
                page.wait_for_timeout(800)
                assert page.evaluate("() => document.getElementById('ctl-frame').dataset.frame") == "trans"
            for panel_id in ("xy", "yz", "xz"):
                page.click(f'button[data-inspect="{panel_id}"]')
                body = page.evaluate("() => document.getElementById('inspector-body').textContent")
                assert "D-Frame" not in body and "legacy" not in body, (frame, panel_id, body[:400])
                page.keyboard.press("Escape")
        browser.close()
    assert problems == [], problems


#: Record the series count of every SVG figure the exporter renders, read
#: from its own chart just before serialisation.
_WATCH_EXPORTS = """() => {
  if (window.__exportSeries) return;
  window.__exportSeries = [];
  const init = echarts.init;
  echarts.init = function (dom, theme, opts) {
    const chart = init.call(this, dom, theme, opts);
    if (opts && opts.renderer === 'svg') {
      const render = chart.renderToSVGString.bind(chart);
      chart.renderToSVGString = (...args) => {
        window.__exportSeries.push((chart.getOption().series || []).length);
        return render(...args);
      };
    }
    return chart;
  };
}"""


def _live_series(page, plot_id):
    return page.evaluate(f"() => (echarts.getInstanceByDom(document.getElementById('{plot_id}'))"
                         "?.getOption().series || []).length")


def _download_svg(page, panel_id):
    page.click(f'button[data-export="{panel_id}"]')
    page.wait_for_selector(".menu")
    with page.expect_download() as download:
        page.click(".menu-item:has-text('SVG — single column')")
    with open(download.value.path(), encoding="utf-8") as handle:
        return download.value.suggested_filename, handle.read()


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE])
def test_every_physics_card_exports_its_plot_alone(physics_live_server, table):
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, physics_live_server["base"], table)
        page.evaluate(_WATCH_EXPORTS)
        exported, series = {}, {}
        for card_id in CARDS[table]:
            _scroll_to(page, card_id)
            if card_id == "statistics":
                # A table, not a figure: no export button.
                assert page.locator('#physics-grid button[data-export="statistics"]').count() == 0
                continue
            live = _live_series(page, f"plot-{card_id}")
            exported[card_id] = _download_svg(page, card_id)
            series[card_id] = (live, page.evaluate("() => window.__exportSeries.at(-1)"))
        if table == SINGLE_HITS_TABLE:
            page.locator('.card[data-panel="energy"]').scroll_into_view_if_needed()
            live = _live_series(page, "plot-energy-b3")
            exported["energy"] = _download_svg(page, "energy")
            series["energy"] = (live, page.evaluate("() => window.__exportSeries.at(-1)"))
        browser.close()
    # The figure is the plot the card draws: the same series, none dropped on the way to print.
    for card_id, (live, printed) in series.items():
        assert printed == live, (card_id, live, printed)
    if table == SINGLE_HITS_TABLE:
        # Every card of the synthetic single shower draws series (the two-event demonstration
        # leaves some with a notice alone: no momentum bin of two showers, no shower in a window).
        assert all(printed for live, printed in series.values()), series
    for card_id, (name, svg) in exported.items():
        texts = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
        assert name.startswith(f"{card_id}_") and name.endswith(".svg"), name
        assert 'width="321"' in svg, card_id
        assert re.search(r'<rect[^>]*fill="#FFFFFF"', svg), f"{card_id}: not on white"
        assert "figure-disclosure" not in svg and "Experiment " not in svg, card_id
        assert texts, card_id
        assert _hyphen_negatives(texts) == [], (card_id, _hyphen_negatives(texts))
    assert problems == [], problems


# ---------------------------------------------------- tooltips and minus --


@pytest.mark.parametrize("viewport", [(1600, 900), (1024, 768)], ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_physics_tooltips_are_readable_and_keep_the_hovered_plot_visible(physics_live_server, table, viewport):
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, physics_live_server["base"], table, viewport=viewport)
        plots = [f"plot-{card}" for card in CARDS[table] if card != "statistics"]
        if table == SINGLE_HITS_TABLE:
            plots.insert(0, "plot-energy-b3")
        totals = {"readouts": 0, "explanations": 0}
        for plot_id in plots:
            card_id = plot_id.removeprefix("plot-")
            if card_id != "energy-b3":
                _scroll_to(page, card_id)
            found = _hover_chart(page, plot_id)
            readouts, explanations = _check_tips(found, f"{table} {plot_id} {viewport}")
            totals["readouts"] += readouts
            totals["explanations"] += explanations
        browser.close()
    assert totals["explanations"], totals
    if table != BASELINE_TABLE:
        # The two-event demonstration draws no histogram, so it has no bin readout to hover.
        assert totals["readouts"], totals
    assert problems == [], problems


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_every_rendered_negative_uses_the_unicode_minus(physics_live_server, table):
    tips = []
    drawers = []
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, physics_live_server["base"], table, fragment="&frame=local"
                                                  if table == SINGLE_HITS_TABLE else "")
        for card_id in CARDS[table]:
            _scroll_to(page, card_id)
            if card_id != "statistics":
                tips += [probe["text"] for _, probe, _ in _hover_chart(page, f"plot-{card_id}", columns=7, rows=4)]
            page.click(f'#physics-grid button[data-inspect="{card_id}"]')
            drawers.append(page.evaluate("() => document.getElementById('inspector-body').textContent"))
            page.keyboard.press("Escape")
        drawn = page.evaluate("() => window.__drawnText")
        dom = page.evaluate("() => document.getElementById('physics-grid').innerText")
        status = page.evaluate("() => document.querySelector('.statusbar').innerText")
        browser.close()
    assert len(drawn) > 100, "no canvas text was recorded"
    assert any("−" in t for t in drawn + [dom] + tips + drawers), "no negative number was drawn at all"
    assert _hyphen_negatives(drawn) == [], "canvas text with an ASCII hyphen-minus"
    assert _hyphen_negatives([dom, status]) == [], "card text with an ASCII hyphen-minus"
    assert _hyphen_negatives(tips) == [], "tooltip text with an ASCII hyphen-minus"
    assert _hyphen_negatives(drawers) == [], "drawer text with an ASCII hyphen-minus"
    assert problems == [], problems


# ------------------------------------------- landing a Methodology badge link --


def _land(p, base, query, table, fragment=""):
    """The Physics page opened on a Methodology badge's link (query and hash), once it has settled."""
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    problems = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.goto(f"{base}/?{query}#table_name={table}{fragment}")
    page.wait_for_function(
        "(table) => document.getElementById('experiment-select')?.value === table && !location.search", arg=table,
        timeout=30_000)
    page.wait_for_timeout(800)
    return browser, page, problems


def _drawer_open(page):
    return page.evaluate("() => !document.getElementById('inspector').hidden")


def test_a_badge_link_lands_on_its_card_with_the_way_back(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _land(
            p, base, "panel=response-b1&from=lnk-statistics-b1&from_sec=2.4", BASELINE_TABLE)
        assert urlparse(page.url).query == ""
        inside = page.evaluate("""() => {
          const card = document.querySelector('#physics-grid .card[data-panel="response-b1"]').getBoundingClientRect();
          const main = document.querySelector('.main').getBoundingClientRect();
          return card.top >= main.top - 2 && card.top < main.bottom; }""")
        assert inside
        assert _drawer_open(page)
        assert page.inner_text("#inspector-title") == "Sampling Fraction — Per-Event Distribution"
        first = page.evaluate("() => document.querySelector('#inspector-body').firstElementChild.className")
        assert "inspector-return" in first
        link = page.locator("#inspector-body .inspector-return a")
        assert link.inner_text() == "↩ Continue reading §2.4 in the Methodology"
        page.check('input[name="model"][value="energy"]')
        page.wait_for_timeout(300)
        link.click()
        page.wait_for_url(re.compile(r"/methodology"), timeout=15_000)
        view = {k: v[0] for k, v in parse_qs(urlparse(page.url).fragment).items()}
        assert view.get("table_name") == BASELINE_TABLE and view.get("model") == "energy", view
        assert view.get("at") == "lnk-statistics-b1", view
        browser.close()
    assert problems == [], problems


def test_a_badge_link_lands_on_a_spatial_card(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _land(p, base, "panel=xy", BASELINE_TABLE)
        assert _drawer_open(page)
        assert page.get_attribute('button[data-inspect="xy"]', "aria-expanded") == "true"
        browser.close()
    assert problems == [], problems


@pytest.mark.parametrize("query, sentence", [
    ("panel=xy", "does not show."),
    ("panel=nope", "does not have (nope)."),
])
def test_a_badge_link_that_cannot_land_says_why(physics_live_server, query, sentence):
    base = physics_live_server["base"]
    table = SINGLE_EVENTS_TABLE if query == "panel=xy" else BASELINE_TABLE
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _land(p, base, query, table)
        text = page.inner_text("#kind-banner-text")
        assert "The Methodology linked to" in text and sentence in text, text
        assert page.evaluate("() => document.getElementById('kind-banner').hidden") is False
        assert not _drawer_open(page)
        browser.close()
    assert problems == [], problems
