"""The Event Inspector and the compare-frames view in Chromium.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks. One
event of the demonstration dataset is pinned through the link, the picker
and the notebook's seeded rule; the nine panels are read back for their
geometry - isometric, one window - and the drawer and the export are checked
to be what the directive asks for.

The Event Inspector is the Physics page's Event viewer subpage (brief
physics-subpages §9-§10): an ``event`` link opens it, the tab is the way back
to Entire selection (the "Back to the ensemble" buttons are gone), and its
pickers draw from the whole experiment under the particle filter, so every
sentence reads "of the experiment".

The particle filter (brief particle-filter §5-§8): the sidebar block's count
line, a typed p interval, Pick for me pinning a matching shower with the
caption's place and match lines and the particle keys in the hash; a particle
commit asking for the pool and the pinned event alone; a picked event that
leaves the pool replaced (the caption's replaced line, the shower focused), a
linked one kept and flagged; N = 0 shutting every picker with its reason, the
viewer's empty state saying it, and no banner; and "Open in 3-D" carrying the
event to the Models page's 3-D card.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Event Inspector check",
)
#: --dist loadgroup (README's testing section): one worker runs this module's tests and boots its server once.
#: A test with a group mark of its own is sent apart: xdist joins its name to this one.
pytestmark = [pytestmark, pytest.mark.xdist_group("event")]

TABLE = "experiment_baseline"
ROWS = ("lab", "trans", "local")
COLS = ("xy", "xz", "yz")

_GEOMETRY = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  if (!inst) return null;
  const grid = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const option = inst.getOption();
  const x = option.xAxis[0];
  const y = option.yAxis[0];
  return {
    hostWidth: host.clientWidth, chartWidth: inst.getWidth(),
    gridWidth: grid.width, gridHeight: grid.height,
    xSpan: x.max - x.min, ySpan: y.max - y.min, xName: x.name, yName: y.name,
    series: option.series.length,
  };
}"""
_HIDDEN = "(id) => document.getElementById(id).hidden"
_TEXT = "(id) => document.getElementById(id).textContent"
_HASH = "() => window.location.hash"


#: The subpage on show has drawn: the Event viewer its event (an `event` link opens it, §4's legacy rule) or
#: its empty state, Entire selection its Events count (each fills its own status bar, §9.1).
_SUBPAGE_READY = """() => document.getElementById('stat-mode')?.textContent === 'Event viewer'
  ? (document.getElementById('event-grid-label').textContent !== '—' || !document.getElementById('event-empty').hidden)
  : document.getElementById('stat-events').textContent !== '—'"""
_MODE = "() => document.getElementById('stat-mode').textContent"


def _open(p, base, fragment="", viewport=(1600, 900)):
    browser = p.chromium.launch()
    page = browser.new_page(color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/{fragment}")
    page.wait_for_function(_SUBPAGE_READY, timeout=30_000)
    return browser, page, errors


def _absent(page, *ids):
    """The ids of `ids` that the page still holds."""
    return page.evaluate("(ids) => ids.filter((id) => document.getElementById(id))", list(ids))


def _wait_for_event_grid(page):
    page.wait_for_function("() => document.getElementById('event-grid-label').textContent !== '—'", timeout=30_000)
    page.wait_for_function(
        "() => ['lab','trans','local'].every((r) => ['xy','xz','yz'].every((c) => "
        "document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))", timeout=30_000)


def _px_per_mm(geometry) -> tuple[float, float]:
    return geometry["gridWidth"] / geometry["xSpan"], geometry["gridHeight"] / geometry["ySpan"]


def _picked(base) -> int:
    return httpx.get(f"{base}/api/event/pick", params={"table_name": TABLE}, timeout=30).json()["event_number"]


# ------------------------------------------------------ the nine panels --


def test_the_event_inspector_draws_nine_isometric_panels_in_one_window(live_server):
    base = live_server["base"]
    n = _picked(base)
    body = httpx.get(f"{base}/api/event", params={"table_name": TABLE, "event_number": n, "shower": "b"},
                     timeout=30).json()
    half = body["window"]["half_mm"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, f"#event={n}&shower=b")
        _wait_for_event_grid(page)
        # An `event` link opens the Event viewer (§4's legacy rule): its subpage on show, Entire selection's
        # off. The pinned event no longer hides the 2 x 2 itself; the subpage wrapper holds it off screen.
        assert page.evaluate(_MODE) == "Event viewer"
        assert page.evaluate(_HIDDEN, "psub-event") is False
        assert page.evaluate(_HIDDEN, "psub-selection") is True
        assert page.evaluate(_HIDDEN, "ensemble-grid") is False
        assert page.evaluate(_HIDDEN, "event-grid") is False
        assert page.evaluate(_HIDDEN, "compare-grid") is True
        for row in ROWS:
            for col in COLS:
                g = page.evaluate(_GEOMETRY, f"plot-event-{row}-{col}")
                assert g, (row, col)
                along_x, along_y = _px_per_mm(g)
                assert along_x == pytest.approx(along_y, rel=0.01), (row, col, along_x, along_y)
                # The axes span the notebook's one window, on every panel of every frame.
                assert g["xSpan"] == pytest.approx(2 * half, rel=1e-6), (row, col)
                assert g["ySpan"] == pytest.approx(2 * half, rel=1e-6), (row, col)
                assert g["chartWidth"] == g["hostWidth"]
        symbols = body["frames"]["local"]["symbols"]
        local_xz = page.evaluate(_GEOMETRY, "plot-event-local-xz")
        assert local_xz["xName"].startswith(symbols["z"]) and local_xz["yName"].startswith(symbols["x"])
        lab_xy = page.evaluate(_GEOMETRY, "plot-event-lab-xy")
        assert lab_xy["xName"].startswith("x") and lab_xy["yName"].startswith("y")
        # The picker reflects the link, and the label is the notebook's row label.
        assert page.input_value("#event-number") == str(n)
        assert page.is_checked('input[name="event-shower"][value="b"]')
        assert page.evaluate(_TEXT, "event-status") == f"event {n}"
        label = page.evaluate(_TEXT, "event-grid-label")
        assert label.startswith(f"Event {n:,}, shower B:") and "θ = " in label and "P₀ = " in label
        assert "principal axis" in label
        # The tab is the way back: neither "Back to the ensemble" button exists any more (brief §9.1).
        assert _absent(page, "event-close", "event-grid-close") == []
        assert page.evaluate(_HIDDEN, "event-open-3d") is False

        # The bin readout over the brightest local bin names the areal density and its unit.
        panel = body["frames"]["local"]["panels"]["xy"]
        top, axes, (rows, cols) = panel["topk"][0], panel["axes"], panel["shape"]
        cx = axes["col"]["lo"] + (top["j"] + 0.5) * (axes["col"]["hi"] - axes["col"]["lo"]) / cols
        cy = axes["row"]["lo"] + (top["i"] + 0.5) * (axes["row"]["hi"] - axes["row"]["lo"]) / rows
        plot = page.locator("#plot-event-local-xy")
        plot.scroll_into_view_if_needed()
        px = page.evaluate("([x, y]) => echarts.getInstanceByDom(document.getElementById('plot-event-local-xy'))"
                           ".convertToPixel({gridIndex: 0}, [x, y])", [cx, cy])
        box = plot.bounding_box()
        page.mouse.move(box["x"] + px[0] - 2, box["y"] + px[1] - 2)
        page.mouse.move(box["x"] + px[0], box["y"] + px[1], steps=2)
        page.wait_for_function("() => [...document.querySelectorAll('.calo-tooltip')]"
                               ".some((t) => t.innerText.trim().length > 0)", timeout=10_000)
        tip = page.evaluate("() => [...document.querySelectorAll('.calo-tooltip')]"
                            ".map((t) => t.innerText.trim()).filter(Boolean).pop()")
        assert tip.startswith("u = ") and "GeV mm⁻²" in tip and "projected energy per mm²" in tip, tip
        assert errors == [], errors
        browser.close()


# ----------------------------------------------------------- the picker --


def test_the_picker_walks_the_candidates_and_the_tab_is_the_way_back(live_server):
    """The viewer's tab draws the first event (Pick for me, seed 42, draw 0); previous / next walk the candidates
    and the link follows; the shower radio redraws the event; the Entire selection tab is the way back (the link
    loses the event and the subpage, the 2 x 2 re-lays itself out), and the Event viewer tab brings the parked
    event back with no request; a typed number pins again."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base)
        net = _watch(page)
        assert page.evaluate(_MODE) == "Entire selection"
        assert page.evaluate(_HIDDEN, "psub-event") is True
        assert page.evaluate(_TEXT, "event-status") == "off"

        page.click("#psub-tab-event")
        _wait_for_event_grid(page)
        _idle(page, net)
        first = int(page.input_value("#event-number"))
        hash_ = _fragment(page.evaluate(_HASH))
        assert hash_["event"] == str(first) and hash_["psub"] == "event", hash_
        caption = page.evaluate(_TEXT, "event-caption")
        assert "seed 42, draw 0" in caption and POOL_OFF in caption, caption
        assert "inside the current selection" not in caption, caption
        assert page.evaluate(_HIDDEN, "psub-selection") is True

        # Previous / next walk the candidates; the link follows; the other step then leads back.
        back, forth = ("#event-prev", "#event-next") if not page.is_disabled("#event-prev") \
            else ("#event-next", "#event-prev")
        page.click(back)
        page.wait_for_function(f"() => document.getElementById('event-number').value !== '{first}'", timeout=30_000)
        second = int(page.input_value("#event-number"))
        assert second != first and f"event={second}" in page.evaluate(_HASH)
        page.wait_for_function(f"() => !document.querySelector('{forth}').disabled", timeout=30_000)
        page.click(forth)
        page.wait_for_function(f"() => document.getElementById('event-number').value === '{first}'", timeout=30_000)

        # The shower radio redraws the same event for the other shower.
        page.check('input[name="event-shower"][value="b"]')
        page.wait_for_function(f"() => document.getElementById('event-grid-label').textContent.startsWith('Event {first:,}, shower B')",
                               timeout=30_000)
        assert "shower=b" in page.evaluate(_HASH)
        _idle(page, net)
        label = page.evaluate(_TEXT, "event-grid-label")

        # The Entire selection tab is the way back: the 2 x 2 returns, the link loses its event and the subpage.
        start = len(net["urls"])
        page.click("#psub-tab-selection")
        assert page.evaluate(_HIDDEN, "psub-event") is True
        assert page.evaluate(_HIDDEN, "psub-selection") is False
        assert page.evaluate(_HIDDEN, "ensemble-grid") is False
        hash_ = page.evaluate(_HASH)
        assert "event=" not in hash_ and "psub=" not in hash_, hash_
        assert page.evaluate(_TEXT, "event-status") == "off"
        xy = page.evaluate(_GEOMETRY, "plot-xy")
        assert xy["chartWidth"] == xy["hostWidth"], "the ensemble panels re-laid themselves out"

        # And back: the parked event and its shower, drawn from the response in hand.
        page.click("#psub-tab-event")
        _idle(page, net)
        assert net["urls"][start:] == [], net["urls"][start:]
        assert page.evaluate(_TEXT, "event-grid-label") == label
        hash_ = _fragment(page.evaluate(_HASH))
        assert hash_["event"] == str(first) and hash_["shower"] == "b" and hash_["psub"] == "event", hash_

        # A typed number pins again.
        other = 1 - first
        page.fill("#event-number", str(other))
        page.press("#event-number", "Enter")
        page.wait_for_function(f"() => document.getElementById('event-grid-label').textContent.startsWith('Event {other},')",
                               timeout=30_000)
        _wait_for_event_grid(page)
        assert f"event={other}" in page.evaluate(_HASH)
        assert errors == [], errors
        browser.close()


# ------------------------------------------------ the drawer and export --


def _download(page, panel_id: str, label: str):
    page.click(f'button[data-export="{panel_id}"]')
    page.wait_for_selector(".menu")
    with page.expect_download() as download:
        page.click(f".menu-item:has-text('{label}')")
    return download.value


def test_the_event_drawer_states_the_frame_and_the_export_is_plot_only(live_server):
    base = live_server["base"]
    n = _picked(base)
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, f"#event={n}")
        _wait_for_event_grid(page)
        page.click('button[data-inspect="event-local-xz"]')
        assert page.evaluate(_HIDDEN, "inspector") is False
        title = page.inner_text("#inspector-title")
        assert title.startswith("Local") and title.endswith("u–w")
        body = page.evaluate(_TEXT, "inspector-body")
        for text in ("Selection", f"Event {n:,}, shower A", "What is drawn", "Local: every cell moved by −P₀",
                     "One half-width for every panel of this event", "Disclosures",
                     "One logarithmic ramp for every panel of this event", "0.1st–99.9th percentile",
                     "Coordinates:", "Marks and legend", "Dashed line = the incident direction", "Principal axis"):
            assert text in body, text
        assert page.evaluate("() => document.querySelector('.card[data-panel=\"event-local-xz\"]').classList.contains('is-inspected')")
        # The title row of a grid card opens the drawer too.
        page.click("#title-event-lab-xy")
        assert page.inner_text("#inspector-title").endswith("x–y")

        download = _download(page, "event-local-xz", "SVG — single column")
        assert download.suggested_filename.startswith(f"event-local-xz_ev{n}A_")
        assert "_native_local_" in download.suggested_filename
        svg = open(download.path(), encoding="utf-8").read()
        assert "figure-disclosure" not in svg
        for text in ("Experiment ", "One half-width", "Dashed line"):
            assert text not in svg, text
        assert 'width="321"' in svg
        assert errors == [], errors
        browser.close()


# --------------------------------------------------- the compare view --


def test_the_compare_view_lays_the_three_frames_out_in_rows(live_server):
    base = live_server["base"]
    experiment = next(e for e in httpx.get(f"{base}/api/experiments", timeout=30).json()["experiments"]
                      if e["table_name"] == TABLE)
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, "#compare=true")
        page.wait_for_function("() => document.getElementById('compare-grid-label').textContent !== '—'", timeout=30_000)
        # The compare grid is Entire selection's; its own close button stays (brief §0).
        assert page.evaluate(_MODE) == "Entire selection"
        assert page.evaluate(_HIDDEN, "ensemble-grid") is True
        assert page.evaluate(_HIDDEN, "compare-grid") is False
        assert page.is_checked("#opt-compare")
        label = page.evaluate(_TEXT, "compare-grid-label")
        assert label.startswith("Absolute: native") and "own response" in label
        offered = [kind for kind in ROWS if kind in experiment["frames"]
                   and {"lab": "lab", "trans": "trans", "local": "local"}[kind] in experiment["coord_systems"]]
        for row in ROWS:
            hidden = page.evaluate(f"() => document.querySelector('#compare-grid-rows [data-row={row}]').hidden")
            assert hidden is (row not in offered), row
            if hidden:
                continue
            page.wait_for_function(
                f"() => ['xy','xz','yz'].every((c) => document.getElementById(`plot-compare-{row}-${{c}}`)?.querySelector('canvas'))",
                timeout=30_000)
            xy = page.evaluate(_GEOMETRY, f"plot-compare-{row}-xy")
            along_x, along_y = _px_per_mm(xy)
            assert along_x == pytest.approx(along_y, rel=0.01), (row, along_x, along_y)
            title = page.evaluate(f"() => document.querySelector('#compare-grid-rows [data-row={row}] .frame-grid-row-title').textContent")
            assert "event" in title
        lab = page.evaluate(_GEOMETRY, "plot-compare-lab-xy")
        assert lab["xName"].startswith("x") and lab["yName"].startswith("y")
        if "local" in offered:
            local = page.evaluate(_GEOMETRY, "plot-compare-local-xy")
            assert local["xName"].startswith("u") and local["yName"].startswith("v")
            page.click('button[data-inspect="compare-local-xy"]')
            body = page.evaluate(_TEXT, "inspector-body")
            assert "Separation-Aligned (D-Frame), Local" in body and "Disclosures" in body

        page.click("#compare-grid-close")
        assert page.evaluate(_HIDDEN, "compare-grid") is True
        assert page.evaluate(_HIDDEN, "ensemble-grid") is False
        assert not page.is_checked("#opt-compare")
        assert "compare=" not in page.evaluate(_HASH)

        page.check("#opt-compare")
        page.wait_for_function("() => !document.getElementById('compare-grid').hidden", timeout=30_000)
        assert "compare=true" in page.evaluate(_HASH)
        assert errors == [], errors
        browser.close()


# ---------------------------------------------------- the particle filter --
#
# The sidebar's Particle Filter block (brief particle-filter §5-§8, as built at c14f9a2): one particle's
# momentum p and polar angle θ narrow which events the pickers offer. It is the Event viewer's (physics-subpages
# §9.2) and its pool is the whole experiment (basis=experiment, §2): E₁, E₂ and D never narrow it. The two-event
# demonstration file (brief §3.6c, θ in degrees):
#   event 0: A p 2.713, θ 22.30; B p 12.541, θ 26.40;
#   event 1: A p 17.876, θ 16.27; B p 6.386, θ 18.16;
# so p 2-3 GeV selects event 0 through A, p 6-7 GeV event 1 through B, and p 7-8 GeV nothing. The p slider's
# domain is the showers' own range snapped outward, 2.70-17.90 GeV, so a typed 2 is the domain's edge: stored
# as null, the interval reads "p ≤ 3.00 GeV". With no bound the seeded shuffle's draw 0 is event 1, draw 1
# event 0.

#: The sentences of physics-subpages §5.1 and §3.4 (the experiment basis), on the demonstration file.
COUNT_OFF = "Particle filter off: the pickers draw from all 2 events of the experiment."
COUNT_P67 = ("N = 1 event holds a matching particle (1 matching shower: 0 A, 1 B), "
             "of the 2 events of the experiment.")
EMPTY_P78 = ("N = 0: no event of the experiment with a defined separation holds a shower with p in 7.00–8.00 GeV "
             "that deposited energy. Widen the particle filter.")
POOL_OFF = ("The candidates are the events of the whole experiment that the pickers can place; "
            "E₁, E₂ and D do not narrow them.")
POOL_P67 = ("The candidates are the events of the whole experiment holding a matching particle "
            "(p in 6.00–7.00 GeV); E₁, E₂ and D do not narrow them.")
ONLY_CANDIDATE = "Candidate 1 of 1, in event-number order."
MATCH_B = "Shower B matches the particle filter: p = 6.39 GeV."
MATCH_A = "Shower A matches the particle filter: p = 2.71 GeV."
REPLACED_1_BY_0 = "Event 1 left the candidates; event 0 replaces it."
NOT_A_CANDIDATE = ("Not a candidate: no shower matches the particle filter; drawn as asked, and previous / next "
                   "walk the candidates.")
OUTSIDE_HAZARD = "event outside the candidates"
#: The viewer's cleared-number line (physics-subpages §10.1).
CLEARED = "No event drawn: type an event number, or press Pick for me or Most tilted."
#: The first draw with no bound (seed 42, draw 0: event 1 of the two).
FIRST_DRAW = ("Drawn uniformly at random from the 2 events of the experiment with a defined separation: entry 1 of a "
              "seeded shuffle of them in event-number order (seed 42, draw 0), so no event repeats until all 2 have "
              "been drawn.")


def _only_one(interval, draw):
    """The uniform rule's sentence when the pool holds one event (brief §3.6), under the experiment basis (§3.4)."""
    return (f"The only one of the events of the experiment with a defined separation holding a shower with "
            f"{interval} that deposited energy (seed 42, draw {draw}).")


#: Every picker and step of the Event Inspector.
PICKERS = ("event-pick", "event-pick-tilted", "event-prev", "event-next")
#: The E₁/E₂/D keys, which no event request carries under basis=experiment (§3.1, §4).
SELECTION_KEYS = ("e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d")


def _watch(page):
    """Record every /api/ request the page sends, and which are still in flight."""
    net = {"urls": [], "pending": set()}

    def sent(request):
        if "/api/" in request.url:
            net["urls"].append(request.url)
            net["pending"].add(request)

    page.on("request", sent)
    page.on("requestfinished", lambda r: net["pending"].discard(r))
    page.on("requestfailed", lambda r: net["pending"].discard(r))
    return net


def _idle(page, net, quiet_ms=400, timeout_ms=30_000):
    """Wait until no /api/ request has been in flight for `quiet_ms`: every request a commit causes, chained ones
    (the candidates, then the event, then a replacement's pick and its event) included, has been sent and answered."""
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


def _fragment(url_or_hash):
    text = url_or_hash.split("#", 1)[1] if "#" in url_or_hash else url_or_hash
    return {k: v[0] for k, v in parse_qs(text).items()}


def _open_particle(p, base, fragment="", *, scheme="dark", viewport=(1600, 900), args=None, drawn=True):
    """The Event viewer (`psub=event` in front of `fragment`) with its particle block's first count in and, when
    `drawn`, its event drawn (the link's, else the first draw); failed responses are recorded, and so is every
    /api/ request from the first."""
    browser = p.chromium.launch(args=args)
    page = browser.new_page(color_scheme=scheme, viewport={"width": viewport[0], "height": viewport[1]})
    problems: list[str] = []
    page.on("pageerror", lambda error: problems.append(f"pageerror: {error}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    net = _watch(page)
    page.goto(f"{base}/#psub=event{fragment}")
    _wait_count(page)
    if drawn:
        _wait_for_event_grid(page)
    _idle(page, net)
    return browser, page, problems, net


def _wait_count(page, text=None):
    """Wait until the block is shown and its count line is in (`text`, when given, in it)."""
    page.wait_for_function(
        """(text) => { const g = document.getElementById('group-particle');
          const c = document.getElementById('particle-count');
          return g && !g.hidden && g.getClientRects().length > 0 && c && c.textContent !== '—'
            && c.textContent.trim() !== '' && (text === null || c.textContent.includes(text)); }""",
        arg=text, timeout=30_000)


def _type_bound(page, field, value):
    """Type one bound into the block's numeric field and press Enter: one commit."""
    page.fill(f"#{field}", str(value))
    page.press(f"#{field}", "Enter")


def _commit(page, net, fields, wait_for=None):
    """Type each (field, value) in turn, waiting after each for the page to fall quiet; the requests they sent."""
    start = len(net["urls"])
    for field, value in fields:
        _type_bound(page, field, value)
        _idle(page, net)
    if wait_for:
        _wait_count(page, wait_for)
        _idle(page, net)
    return net["urls"][start:]


def _caption(page):
    return page.evaluate(_TEXT, "event-caption")


def _details(page, panel):
    return page.evaluate("(id) => { const b = document.querySelector(`button[data-inspect=\"${id}\"]`);"
                         " return { flagged: b.classList.contains('is-flagged'), title: b.title }; }", panel)


def _no_selection_keys(urls):
    """Every event request of `urls` says basis=experiment and carries no E₁/E₂/D key."""
    for url in urls:
        query = _query(url)
        assert query.get("basis") == "experiment", url
        assert not set(SELECTION_KEYS) & set(query), url


def test_the_particle_block_counts_its_pool_and_pick_for_me_pins_a_matching_shower(live_server):
    """The block is shown with its count line; with the event number cleared (the viewer's empty state says how
    to draw one) a typed p interval sends the candidates request alone and updates the count; Pick for me then
    pins the one candidate with its matching shower at the next draw (the first draw took draw 0), the caption
    carries the place, match and pool lines, and the hash the particle keys."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base)
        assert page.evaluate(_HIDDEN, "group-particle") is False
        assert page.evaluate(_TEXT, "particle-count") == COUNT_OFF
        assert page.is_disabled("#particle-clear")
        # The first draw: the candidates, the pick at draw 0 and its event, all under basis=experiment.
        assert _paths(net["urls"]) == ["/api/experiments", "/api/event/candidates", "/api/event/pick", "/api/event"], \
            net["urls"]
        _no_selection_keys(net["urls"][1:])
        assert FIRST_DRAW in _caption(page), _caption(page)

        # The reader empties the event number: nothing is drawn, and the empty state says how to draw one.
        page.fill("#event-number", "")
        page.press("#event-number", "Enter")
        page.wait_for_function("() => !document.getElementById('event-empty').hidden", timeout=10_000)
        assert page.evaluate(_TEXT, "event-empty-text") == CLEARED
        assert page.evaluate(_HIDDEN, "event-grid") is True
        assert "event=" not in page.evaluate(_HASH)

        sent = _commit(page, net, [("pp-num-hi", 7), ("pp-num-lo", 6)], wait_for="N = 1 event")
        assert page.evaluate(_TEXT, "particle-count") == COUNT_P67
        # Nothing is pinned: each commit asks for the pool alone.
        assert _paths(sent) == ["/api/event/candidates"] * 2, sent
        _no_selection_keys(sent)
        last = _query(sent[-1])
        assert float(last["particle_p_min"]) == 6 and float(last["particle_p_max"]) == 7, last
        assert not page.is_disabled("#particle-clear")
        hash_ = _fragment(page.evaluate(_HASH))
        assert float(hash_["particle_p_min"]) == 6 and float(hash_["particle_p_max"]) == 7, hash_

        start = len(net["urls"])
        page.click("#event-pick")
        _wait_for_event_grid(page)
        _idle(page, net)
        assert _paths(net["urls"][start:]) == ["/api/event/pick", "/api/event"], net["urls"][start:]
        _no_selection_keys(net["urls"][start:])
        pick = _query(net["urls"][start])
        # The draw counter carries on from the first draw (draw 0).
        assert pick["rule"] == "uniform" and pick["seed"] == "42" and pick["draw"] == "1", pick
        assert float(pick["particle_p_min"]) == 6 and float(pick["particle_p_max"]) == 7, pick
        event = _query(net["urls"][start + 1])
        # The matching shower is asked for in the event's first request.
        assert event["event_number"] == "1" and event["shower"] == "b", event
        assert page.input_value("#event-number") == "1"
        assert page.is_checked('input[name="event-shower"][value="b"]')
        assert page.evaluate(_TEXT, "event-grid-label").startswith("Event 1, shower B:")
        assert page.evaluate(_HIDDEN, "event-empty") is True
        caption = _caption(page)
        for line in (ONLY_CANDIDATE, MATCH_B, POOL_P67, _only_one("p in 6.00–7.00 GeV", 1)):
            assert line in caption, (line, caption)
        hash_ = _fragment(page.evaluate(_HASH))
        assert hash_["event"] == "1" and hash_["shower"] == "b", hash_
        assert float(hash_["particle_p_min"]) == 6 and float(hash_["particle_p_max"]) == 7, hash_
        assert OUTSIDE_HAZARD not in _details(page, "event-lab-xy")["title"]
        browser.close()
    assert problems == [], problems


def test_a_link_with_a_particle_bound_draws_a_matching_shower_first(live_server):
    """Entering the viewer with a bound in the link: the first draw is Pick for me at draw 0 under the bound,
    and it pins the one candidate with its matching shower."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base, "&particle_p_min=6&particle_p_max=7")
        assert _paths(net["urls"])[1:] == ["/api/event/candidates", "/api/event/pick", "/api/event"], net["urls"]
        pick = _query(net["urls"][2])
        assert pick["rule"] == "uniform" and pick["draw"] == "0" and float(pick["particle_p_min"]) == 6, pick
        event = _query(net["urls"][3])
        assert event["event_number"] == "1" and event["shower"] == "b", event
        assert page.evaluate(_TEXT, "particle-count") == COUNT_P67
        caption = _caption(page)
        for line in (ONLY_CANDIDATE, MATCH_B, POOL_P67, _only_one("p in 6.00–7.00 GeV", 0)):
            assert line in caption, (line, caption)
        browser.close()
    assert problems == [], problems


def test_a_particle_commit_asks_only_for_the_pool_and_the_event_and_replaces_a_picked_event_that_left(live_server):
    """A particle commit sends /api/event/candidates and /api/event alone (never /api/projections or a card);
    an event a pick brought that leaves the pool is replaced by the next uniform draw, with the caption's
    replaced line and the shower focused on the replacement's match."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base)
        # The first draw (a pick: draw 0) pinned event 1.
        assert page.input_value("#event-number") == "1"

        # p 6-7 GeV, then p ≤ 7 GeV: event 1 stays a candidate (its B, 6.39 GeV), so it is kept; one pool and
        # one event request per commit.
        sent = _commit(page, net, [("pp-num-hi", 7), ("pp-num-lo", 6)], wait_for="N = 1 event")
        assert _paths(sent) == ["/api/event/candidates", "/api/event"] * 2, sent
        sent = _commit(page, net, [("pp-num-lo", 2)], wait_for="N = 2 events")
        assert _paths(sent) == ["/api/event/candidates", "/api/event"], sent
        assert page.input_value("#event-number") == "1"
        assert "particle_p_min" not in _fragment(page.evaluate(_HASH)), "a bound at the domain's edge is stored as null"

        # p ≤ 3 GeV: event 1 has left; the next uniform draw pins event 0 with its matching shower A. The counter
        # carries across commits, so after the first draw (draw 0) the replacement is draw 1.
        sent = _commit(page, net, [("pp-num-hi", 3)], wait_for="N = 1 event")
        assert _paths(sent) == ["/api/event/candidates", "/api/event", "/api/event/pick", "/api/event"], sent
        _no_selection_keys(sent)
        pick = _query(sent[2])
        assert pick["rule"] == "uniform" and pick["draw"] == "1" and float(pick["particle_p_max"]) == 3, pick
        assert _query(sent[3])["event_number"] == "0" and _query(sent[3])["shower"] == "a", sent[3]
        page.wait_for_function("() => document.getElementById('event-number').value === '0'", timeout=30_000)
        page.wait_for_function("() => document.getElementById('event-grid-label').textContent.startsWith('Event 0,')",
                               timeout=30_000)
        assert page.is_checked('input[name="event-shower"][value="a"]')
        caption = _caption(page)
        for line in (REPLACED_1_BY_0, MATCH_A, ONLY_CANDIDATE, _only_one("p ≤ 3.00 GeV", 1)):
            assert line in caption, (line, caption)
        assert OUTSIDE_HAZARD not in _details(page, "event-lab-xy")["title"]
        browser.close()
    assert problems == [], problems


def test_an_event_from_a_link_is_kept_and_flagged_when_it_leaves_the_pool(live_server):
    """The reader's own event (from the link) is never replaced: drawn as asked, its caption's place line says it
    is not a candidate, and every event panel's Details button carries the hazard."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base, "&event=1&shower=b")
        # A link's event: no pick.
        assert "/api/event/pick" not in _paths(net["urls"]), net["urls"]
        before = _details(page, "event-lab-xy")
        assert OUTSIDE_HAZARD not in before["title"], before

        sent = _commit(page, net, [("pp-num-hi", 3)], wait_for="N = 1 event")
        assert _paths(sent) == ["/api/event/candidates", "/api/event"], sent
        assert page.input_value("#event-number") == "1"
        assert page.is_checked('input[name="event-shower"][value="b"]')
        caption = _caption(page)
        assert NOT_A_CANDIDATE in caption, caption
        assert "replaces it" not in caption, caption
        # Review U5 = R5: the status item reads "Place not a candidate", never "Candidate not a candidate".
        item = page.evaluate("() => document.getElementById('stat-place').parentElement.textContent")
        assert " ".join(item.split()) == "Place not a candidate", item
        for panel in (f"event-{row}-{col}" for row in ROWS for col in COLS):
            details = _details(page, panel)
            assert details["flagged"] and OUTSIDE_HAZARD in details["title"], (panel, details)
        page.click('button[data-inspect="event-lab-xy"]')
        body = page.evaluate(_TEXT, "inspector-body")
        assert NOT_A_CANDIDATE in body and "Particle filter: p ≤ 3.00 GeV." in body, body[:600]

        # Clear: event 1 is a candidate again, still the reader's, and the hazard goes.
        start = len(net["urls"])
        page.click("#particle-clear")
        _wait_count(page, COUNT_OFF)
        _idle(page, net)
        assert _paths(net["urls"][start:]) == ["/api/event/candidates", "/api/event"], net["urls"][start:]
        assert page.input_value("#event-number") == "1"
        assert _details(page, "event-lab-xy") == before, "the hazard goes with the filter"
        assert NOT_A_CANDIDATE not in _caption(page)
        browser.close()
    assert problems == [], problems


#: The viewer's empty state once the reader has emptied the event number (event_inspector.js CLEARED_LINE).
CLEARED_LINE = "No event drawn: type an event number, or press Pick for me or Most tilted."
#: The server's warning for a drawn event inside the experiment but outside the particle filter's pool.
OUTSIDE_WARNING = "Event 1 holds no shower matching the particle filter"


def test_clearing_the_event_number_takes_its_warning_off_the_banner(live_server):
    """A flagged event's warning leaves the banner with the event: once the reader empties the event number, the
    viewer shows its empty state and the banner no longer speaks of an event that is not drawn (found by the
    Stage 4 browser tests, fixed by the lead)."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base, "&event=1&shower=b")
        _commit(page, net, [("pp-num-hi", 3)], wait_for="N = 1 event")
        page.wait_for_function("(w) => !document.getElementById('banner').hidden"
                               " && document.getElementById('banner-text').textContent.includes(w)",
                               arg=OUTSIDE_WARNING, timeout=10_000)
        page.fill("#event-number", "")
        page.press("#event-number", "Enter")
        page.wait_for_function("() => !document.getElementById('event-empty').hidden", timeout=10_000)
        _idle(page, net)
        assert page.evaluate(_TEXT, "event-empty-text") == CLEARED_LINE
        # Review U6: the empty state's text is announced through the always-rendered live region, which is
        # rendered (not display: none) and drawn nowhere; the empty state itself is no live region.
        live = page.evaluate("""() => { const el = document.getElementById('event-live'); const r = el.getBoundingClientRect();
          return { text: el.textContent, role: el.getAttribute('role'), live: el.getAttribute('aria-live'),
                   rendered: getComputedStyle(el).display !== 'none', area: r.width * r.height,
                   emptyLive: document.getElementById('event-empty').getAttribute('aria-live') }; }""")
        assert live == {"text": CLEARED_LINE, "role": "status", "live": "polite", "rendered": True,
                        "area": live["area"], "emptyLive": None}, live
        assert live["area"] <= 1, live
        banner = page.evaluate("() => ({ hidden: document.getElementById('banner').hidden,"
                               " text: document.getElementById('banner-text').textContent })")
        assert banner["hidden"] or OUTSIDE_WARNING not in banner["text"], banner
        browser.close()
    assert problems == [], problems


def test_an_empty_pool_shuts_every_picker_with_its_reason_and_raises_no_banner(live_server):
    """N = 0 on entering the viewer: no request but the pool's (no pick), every picker and step disabled with the
    empty line as its title, the block's count line replaced by that line, the viewer's empty state showing it,
    and no error banner; a wider filter gives the pickers back and the first draw, armed meanwhile, fires."""
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base, "&particle_p_min=7&particle_p_max=8", drawn=False)
        page.wait_for_function("() => !document.getElementById('event-empty').hidden", timeout=30_000)
        _idle(page, net)
        assert _paths(net["urls"]) == ["/api/experiments", "/api/event/candidates"], net["urls"]
        assert page.evaluate(_TEXT, "particle-count") == EMPTY_P78
        for button in PICKERS:
            assert page.is_disabled(f"#{button}"), button
            assert page.get_attribute(f"#{button}", "title") == EMPTY_P78, button
        assert page.evaluate(_HIDDEN, "banner") is True
        assert page.evaluate(_HIDDEN, "event-grid") is True
        assert page.evaluate(_HIDDEN, "event-open-3d") is True
        assert page.evaluate(_TEXT, "event-empty-title") == "No event drawn"
        assert page.evaluate(_TEXT, "event-empty-text") == EMPTY_P78

        start = len(net["urls"])
        page.click("#particle-clear")
        _wait_count(page, COUNT_OFF)
        _wait_for_event_grid(page)
        _idle(page, net)
        assert _paths(net["urls"][start:]) == ["/api/event/candidates", "/api/event/pick", "/api/event"], \
            net["urls"][start:]
        assert _query(net["urls"][start + 1])["draw"] == "0"
        for button in ("event-pick", "event-pick-tilted"):
            assert not page.is_disabled(f"#{button}"), button
            assert page.get_attribute(f"#{button}", "title") != EMPTY_P78, button
        assert page.get_attribute("#event-pick", "title").startswith("A candidate event drawn uniformly at random")
        assert page.evaluate(_HIDDEN, "banner") is True
        assert page.evaluate(_HIDDEN, "event-empty") is True
        browser.close()
    assert problems == [], problems


def test_open_in_3d_carries_the_event_shower_and_particle_keys_to_the_models_page(live_server):
    """"Open in 3-D" shows while an event is pinned; its href carries the event, the shower, the particle keys and
    voxel_scope=event (Page 1's own event, shower and subpage kept); followed, the Models page's 3-D event card
    draws that event and shower under the particle filter."""
    from test_browser_models import GL_ARGS, _scroll_to
    from test_browser_theme import _GL_DRAWN

    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, net = _open_particle(p, base, "&particle_p_min=6&particle_p_max=7", args=GL_ARGS)
        # The first draw pinned the one candidate, event 1, on its matching shower B.
        assert page.input_value("#event-number") == "1"
        assert page.evaluate(_HIDDEN, "event-open-3d") is False
        assert page.get_attribute("#event-open-3d", "title").startswith(
            "Open this event and shower in the Models page's 3-D view")
        href = page.get_attribute("#event-open-3d", "href")
        assert urlparse(href).path == "/models", href
        target = _fragment(href)
        assert target["voxel_event"] == "1" and target["voxel_shower"] == "b" and target["voxel_scope"] == "event"
        assert float(target["particle_p_min"]) == 6 and float(target["particle_p_max"]) == 7, target
        assert target["event"] == "1" and target["shower"] == "b", target
        # Page 1's subpage rides along, so the Physics tab returns to the viewer (brief §5.2).
        assert target["psub"] == "event", target
        assert "frame" not in target, target

        start = len(net["urls"])
        page.click("#event-open-3d")
        page.wait_for_url("**/models#*", timeout=30_000)
        page.wait_for_function("() => document.getElementById('stat-kind')?.textContent.trim() !== '—'",
                               timeout=30_000)
        _scroll_to(page, "vox-event")
        page.wait_for_function(_GL_DRAWN, arg="vox-event", timeout=30_000)
        _idle(page, net)
        assert page.evaluate("() => document.querySelector('.main .card[data-panel=\"vox-event\"] .title')"
                             "?.textContent") == "One Event in 3-D — Detector Cells"
        assert page.input_value('.main .card[data-panel="vox-event"] [data-voxel-event]') == "1"
        voxels = [_query(u) for u in net["urls"][start:]
                  if urlparse(u).path == "/api/event" and _query(u).get("format") == "voxels"]
        assert voxels, net["urls"][start:]
        assert all(v["event_number"] == "1" and v["shower"] == "b" and float(v["particle_p_min"]) == 6
                   for v in voxels), voxels
        # A linked event: neither the densest pick nor a uniform draw replaces it.
        assert "/api/event/pick" not in _paths(net["urls"][start:]), net["urls"][start:]
        browser.close()
    assert problems == [], problems
