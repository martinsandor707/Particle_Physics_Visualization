"""The Models page (/models), driven in Chromium on every kind it serves.

One server (``models_live_server``) holds the two-shower demonstration, the
synthetic single-shower hits and an event-level aggregate paired with its
XGBoost models, whose analysis has finished before the first page opens. The
page is checked as a reader meets it:

* the page tabs carry the view (the hash) across both pages, and the Physics
  page keeps the Models page's keys;
* no card asks before it scrolls into view, the 3-D pairs included;
* every 2-D card renders with no console error, page error or failed
  request, opens its Details drawer with the standard sections, and draws
  every negative number with U+2212;
* every tooltip is mounted on ``#tooltip-layer`` and leaves the hovered
  panel's plot: an explanation sits outside the chart, a bin readout beside
  the pointer covering at most a fifth of the plot (a paired projection's
  coordinate readout at most 40%);
* the 2-D cards export their plot alone; the 3-D cards have no export;
* the 3-D cards draw in SwiftShader WebGL with at most two live contexts,
  open at a zoom that keeps their axis titles inside the card (refitted when
  the card narrows, the reader's rotation kept), and say "WebGL is not
  available" when there is none, while their paired projections still draw;
* the four XGBoost cards draw both tasks, the surrogate's φ / θ output is a
  repaint, and the prediction cards' φ / θ switch asks for the other output;
* the φ residual card draws no arithmetic-mean marker, whisker or σ band;
* the feature explorer's A / B toggle (two showers) goes on every feature
  request and round-trips in the hash;
* Admin Settings lists the model runs and rescans them;
* the energy-resolution card (``res-scaling``) draws its reversed 1/√E axis
  ending at the origin corner, the Energy (GeV) axis on top over the same
  range with ∞ at 0, a y axis from 0 and its fit table under the plot; its
  window, shower and theme switches repaint with no request (the two-shower
  baseline's two events draw its empty state, with the table still there);
* the 3-D cards' slice mode: K slices stepped with Previous, Next and the
  scrubber, K clamped to the volume's depth, the slices' cubes adding up to
  the whole volume's, the paired depth projections banding the slice drawn,
  with no request and the reader's turned and zoomed camera kept, and the
  slice row hidden without WebGL.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import base64
import os
import re
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import BASELINE_TABLE, MODELS_XGB_TABLE, SINGLE_HITS_TABLE
from test_browser_physics import (
    _PROBE, _RECORD_CANVAS_TEXT, _WATCH_EXPORTS, _WATCH_HOVER, _assert_sections, _beside, _check_tips,
    _download_svg, _hyphen_negatives, _live_series, _overlap, _route_requests,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Models-page check",
)

#: SwiftShader's software WebGL, as the 3-D spike measured it (design/two-page/spike).
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]

PERF = ["perf-bins", "pred-truth", "pred-residuals"]
#: The energy-resolution section (capabilities.js PAGE2_SECTIONS.resolution): its detector series needs no
#: model, so it shows on every kind, between the performance and the XGBoost sections.
RES = ["res-scaling"]
XGB =["xgb-cv", "xgb-binary", "xgb-surrogate", "xgb-importance"]
FEATURES = ["feat-table", "feat-corr", "feat-hist", "feat-hist2d"]
EVENT_PAIR = ["vox-event", "vproj-xy", "vproj-xz", "vproj-yz"]
ENSEMBLE_PAIR = ["vox-ensemble", "eproj-xy", "eproj-yz", "eproj-xz"]
GL_CARDS = ("vox-event", "vox-ensemble")

#: The cards each kind shows, in page order. The two-shower page opens on the
#: energy network, so its performance cards draw rather than state the
#: segmentation network's notice.
CARDS = {
    BASELINE_TABLE: PERF + RES + FEATURES + ["prim-rate"] + EVENT_PAIR + ENSEMBLE_PAIR,
    SINGLE_HITS_TABLE: RES + FEATURES + ["prim-rate"] + EVENT_PAIR + ENSEMBLE_PAIR,
    MODELS_XGB_TABLE: PERF + RES + XGB + FEATURES,
}
#: The tables whose selection holds momentum windows the resolution card can draw: the baseline's two
#: events hold none from 4 GeV with two events, so it draws its empty state there.
RES_DRAWN = (SINGLE_HITS_TABLE, MODELS_XGB_TABLE)
FRAGMENT = {BASELINE_TABLE: "&model=energy", SINGLE_HITS_TABLE: "", MODELS_XGB_TABLE: ""}
#: Cards shut by the server's gate on a kind, with the reason on the card.
SHUT = {BASELINE_TABLE: {"prim-rate"}}

GL_UNAVAILABLE = "WebGL is not available in this browser"

#: voxels.js: the 3-D plot's height bounds (`glPlotHeight`), the px every opening mark keeps from the
#: canvas's edges (`FIT_PAD` is 8; 4 is asserted), and the least share of the limiting dimension it spans.
GL_HEIGHTS, GL_SPARE, GL_FILL = (360, 560), 4, 0.80

#: A 3-D card's plot size and camera, as echarts-gl holds it: the opening view's size and viewport.
_ZOOM = """(id) => {
  const el = document.getElementById(`plot-${id}`);
  const grid = echarts.getInstanceByDom(el).getOption().grid3D[0];
  return { w: el.clientWidth, h: el.clientHeight, size: grid.viewControl.orthographicSize, right: grid.right,
           left: grid.left, top: grid.top, vw: grid.width, vh: grid.height,
           alpha: grid.viewControl.alpha, beta: grid.viewControl.beta };
}"""

#: The drawn pixels' extent on a PNG of a plot, against the card colour, left of column `limit`
#: (the scan of data/dev/scratch_wavec/extent_scan.py).
_EXTENT = """async ([url, limit]) => {
  const img = new Image(); img.src = url; await img.decode();
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const card = [28, 33, 40];
  let x0 = c.width, x1 = -1, y0 = c.height, y1 = -1;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < Math.min(limit, c.width); x++) {
    const k = 4 * (y * c.width + x);
    if (Math.abs(d[k] - card[0]) + Math.abs(d[k + 1] - card[1]) + Math.abs(d[k + 2] - card[2]) > 24) {
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  }
  return { w: c.width, h: c.height, x0, x1, y0, y1 };
}"""


def _gl_extent(page, card_id):
    """A 3-D card's opening view, measured on its canvas pixels: the 3-D marks (left of the legend's strip)
    and everything drawn (the legend included), with the px each keeps from the edges and the share of the
    limiting dimension the 3-D marks span."""
    zoom = page.evaluate(_ZOOM, card_id)
    png = page.locator(f"#plot-{card_id}").screenshot()
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    area = zoom["w"] - (zoom["right"] or 0)
    marks = page.evaluate(_EXTENT, [url, area])
    drawn = page.evaluate(_EXTENT, [url, 10 ** 6])
    # A plot at a fractional page offset screenshots one px larger than its client size.
    assert abs(marks["w"] - zoom["w"]) <= 1 and abs(marks["h"] - zoom["h"]) <= 1, (marks, zoom)
    spare = {"left": marks["x0"], "right": area - 1 - marks["x1"], "top": marks["y0"], "bottom": marks["h"] - 1 - marks["y1"]}
    whole = {"left": drawn["x0"], "right": drawn["w"] - 1 - drawn["x1"], "top": drawn["y0"], "bottom": drawn["h"] - 1 - drawn["y1"]}
    fill = max((marks["x1"] - marks["x0"] + 1) / area, (marks["y1"] - marks["y0"] + 1) / marks["h"])
    return {"zoom": zoom, "spare": spare, "whole": whole, "fill": round(fill, 3)}

#: Every live WebGL context, by canvas, recorded before any script runs.
_COUNT_GL = """(() => {
  window.__gl = new Map();
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    const ctx = original.call(this, type, ...rest);
    if (ctx && /webgl/i.test(String(type))) window.__gl.set(this, ctx);
    return ctx;
  };
})();"""

#: A browser without WebGL: every WebGL context request fails.
_NO_WEBGL = """(() => {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    if (/webgl/i.test(String(type))) return null;
    return original.call(this, type, ...rest);
  };
})();"""

#: The live WebGL contexts: on a canvas in the page, not lost (the availability probe's is neither).
_LIVE_GL = """() => [...(window.__gl ?? new Map()).entries()]
  .filter(([canvas, ctx]) => canvas.isConnected && !ctx.isContextLost())
  .map(([canvas]) => canvas.closest('.card')?.dataset.panel ?? null)"""

#: Where a card stands: shown, loading, drawn, or saying why it is not.
_CARD = """(id) => {
  const card = document.querySelector(`.main .card[data-panel="${id}"]`);
  if (!card) return null;
  const host = card.querySelector('.plot, .card-table');
  const message = card.querySelector('.card-error');
  const inst = host && host.classList.contains('plot') ? echarts.getInstanceByDom(host) : null;
  const option = inst ? inst.getOption() : null;
  return {
    hidden: card.hidden,
    loading: card.classList.contains('is-loading'),
    message: message && !message.hidden ? message.textContent.trim() : null,
    kind: message && !message.hidden ? message.dataset.kind ?? null : null,
    canvas: Boolean(host && host.querySelector('canvas')),
    table: Boolean(host && host.querySelector('table')),
    series: option ? (option.series || []).length : 0,
    seriesTypes: option ? (option.series || []).map((s) => s.type) : [],
    graphic: option ? (option.graphic || []).length : 0,
    title: card.querySelector('.title')?.textContent ?? '',
    width: host ? host.clientWidth : 0,
    height: host ? host.clientHeight : 0,
    exportButtons: card.querySelectorAll('[data-export]').length,
  };
}"""

#: A chart's box and its plot in viewport pixels: the union of its grids, or
#: the whole chart where it draws without a grid (the surrogate tree, the 3-D views).
_BOXES = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const chart = { left: c.left, top: c.top, right: c.right, bottom: c.bottom };
  const model = inst.getModel();
  const grids = (inst.getOption().grid || []).map((_, i) => model.getComponent('grid', i)?.coordinateSystem?.getRect())
    .filter(Boolean);
  if (!grids.length) return { chart, plot: chart, grids: 0 };
  return {
    chart,
    plot: { left: c.left + Math.min(...grids.map((g) => g.x)), top: c.top + Math.min(...grids.map((g) => g.y)),
            right: c.left + Math.max(...grids.map((g) => g.x + g.width)),
            bottom: c.top + Math.max(...grids.map((g) => g.y + g.height)) },
    grids: grids.length,
  };
}"""

#: Every text an option's graphic elements and titles state.
_CHART_TEXTS = """(plotId) => {
  const inst = echarts.getInstanceByDom(document.getElementById(plotId));
  const option = inst.getOption();
  const walk = (items) => (items || []).flatMap((g) => [g.style?.text, ...walk(g.elements || g.children)]);
  return [...walk(option.graphic), ...(option.title || []).map((t) => t.text)].filter(Boolean);
}"""


# ------------------------------------------------------------------ helpers --


def _open(p, base, table, *, fragment=None, viewport=(1600, 900), init=(), browser=None, path="/models"):
    """The Models page on `table`, with every console error, page error and failed request recorded."""
    browser = browser or p.chromium.launch(args=GL_ARGS)
    page = browser.new_page(
        color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]}, accept_downloads=True,
    )
    problems, requests = [], []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.on("request", lambda r: requests.append((r.method, r.url)) if "/api/" in r.url else None)
    page.add_init_script(_RECORD_CANVAS_TEXT)
    for script in init:
        page.add_init_script(script)
    page.goto(f"{base}{path}#table_name={table}{FRAGMENT.get(table, '') if fragment is None else fragment}")
    page.wait_for_function(
        "(table) => document.getElementById('experiment-select')?.value === table "
        "&& document.getElementById('stat-kind')?.textContent.trim() !== '—'",
        arg=table, timeout=30_000,
    )
    page.wait_for_timeout(600)
    return browser, page, problems, requests


def _urls(requests, method="GET"):
    return [url for m, url in requests if m == method]


def _settled(page, card_id, timeout=30_000):
    """Wait until a card has drawn, or says why it has not; return its state."""
    page.wait_for_function(
        f"""() => {{ const s = ({_CARD})({card_id!r});
          return s && !s.loading && (s.message !== null || s.table || (s.canvas && (s.series || s.graphic))); }}""",
        timeout=timeout,
    )
    page.wait_for_timeout(150)
    return page.evaluate(_CARD, card_id)


def _scroll_to(page, card_id):
    page.locator(f'.main .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
    return _settled(page, card_id)


def _shown_cards(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('.main .card[data-panel]')]"
        ".filter((c) => !c.hidden && c.offsetParent !== null).map((c) => c.dataset.panel)")


def _requests_of(requests, route, **params):
    return _route_requests(_urls(requests), route, **params)


def _hover_chart(page, plot_id, columns=9, rows=6):
    """Hover a grid of points over a chart's plot; every tooltip that showed, probed."""
    page.locator(f"#{plot_id}").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    page.evaluate(_WATCH_HOVER, plot_id)
    boxes = page.evaluate(_BOXES, plot_id)
    plot = boxes["plot"]
    found = []
    for i in range(columns):
        for j in range(rows):
            x = plot["left"] + (i + 0.5) / columns * (plot["right"] - plot["left"])
            y = plot["top"] + (j + 0.5) / rows * (plot["bottom"] - plot["top"])
            page.mouse.move(x, y)
            page.wait_for_timeout(40)
            probe = page.evaluate(_PROBE)
            if probe is not None:
                found.append(((x, y), probe, boxes))
    page.mouse.move(2, 2)
    page.wait_for_timeout(60)
    return found


#: The most of a paired projection's plot its plain readout may cover beside the pointer: Page 1's cap
#: (test_browser_physics.py READOUT_SHARE, Martin's tooltip rule). A larger readout leaves the plot
#: as an explanation does (panels/tooltip.js placeTooltip); the 1 : 1 pair's five-line readout is 33%.
PROJECTION_READOUT_SHARE = 0.2
#: A projection's plain bin readout opens on a coordinate in millimetres (test_browser_tooltip.py's rule):
#: ProjectionPanel places it from its own cell handler, not from a series-level `position`.
COORDINATE = re.compile(r"^\S+ = [\u2212-]?[\d.]+ mm$")


def _projection_readouts(found, where):
    """The projections' plain bin readouts, checked by test_browser_tooltip.py's rule; the rest returned.

    ProjectionPanel is the Physics page's spatial panel. Its plain readout (a coordinate first, no
    overlay above it) stays beside the pointer, read against the bin under it, on the tooltip layer
    and never on the pointer - the rule Page 1's tooltip test holds it to, without the physics cards'
    area cap (an event cell is 278 px square, and its four-line readout covers about a fifth of it).
    Returns the other probes, for `_check_tips`, and the largest share of the plot a readout covered.
    """
    rest, worst = [], 0.0
    for (x, y), probe, boxes in found:
        first = probe["text"].strip().splitlines()[0] if probe["text"].strip() else ""
        if not COORDINATE.match(first):
            rest.append(((x, y), probe, boxes))
            continue
        at = f"{where} at ({x:.0f}, {y:.0f}): {probe['text'][:60]!r}"
        tip, (vw, vh) = probe["tip"], probe["viewport"]
        assert probe["parent"] == "tooltip-layer" and probe["clippers"] == [], at
        assert tip["left"] >= -0.5 and tip["top"] >= -0.5 and tip["right"] <= vw + 0.5 and tip["bottom"] <= vh + 0.5, at
        assert all(probe["onTop"]), at
        assert not (tip["left"] <= x <= tip["right"] and tip["top"] <= y <= tip["bottom"]), f"{at}: on the pointer"
        plot = boxes["plot"]
        area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
        share = _overlap(tip, plot) / area if area else 0.0
        if _beside(tip, x, y):
            # Beside the pointer, read against the bin under it, only while it covers at most the cap.
            assert share <= PROJECTION_READOUT_SHARE + 1e-3, f"{at}: a readout covers {share:.0%} of the plot ({tip})"
        else:
            # One that would cover more would hide the panel: it leaves the plot like an explanation.
            assert share == 0.0, f"{at}: the bin readout left the pointer but stayed over the plot ({tip})"
        worst = max(worst, share)
    return rest, worst


def _drawer(page, card_id):
    """Open a card's Details drawer; its title, section headings and text; closed again."""
    page.click(f'.main button[data-inspect="{card_id}"]')
    page.wait_for_function("() => !document.getElementById('inspector').hidden")
    title = page.inner_text("#inspector-title")
    headings = page.evaluate(
        "() => [...document.querySelectorAll('#inspector-body .inspector-section h3')].map((h) => h.textContent)")
    body = page.evaluate("() => document.getElementById('inspector-body').textContent")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('inspector').hidden")
    return title, headings, body


def _hash(page):
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).fragment).items()}


# ------------------------------------------------------------ the page tabs --


def test_the_page_tabs_carry_the_view_across_both_pages(models_live_server):
    base = models_live_server["base"]
    view = "&model=energy&fclass=label&fshower=b&xgb_task=angle&xgb_label=phi&feature=depth"
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, BASELINE_TABLE, fragment=view)
        tabs = page.evaluate("() => [...document.querySelectorAll('#page-tabs a.page-tab')].map((a) => "
                             "[a.dataset.page, a.classList.contains('is-current'), a.getAttribute('aria-current')])")
        assert tabs == [["physics", False, None], ["models", True, "page"], ["methodology", False, None]], tabs
        # The feature cards read the link's shower: B is pressed.
        _scroll_to(page, "feat-corr")
        pressed = page.get_attribute('.card[data-panel="feat-corr"] button[data-feature-shower="b"]', "aria-pressed")
        assert pressed == "true"

        page.click('#page-tabs a[data-page="physics"]')
        page.wait_for_url(re.compile(r"^[^#]*/#"), timeout=30_000)
        page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')", timeout=30_000)
        assert urlparse(page.url).path == "/"
        on_physics = _hash(page)
        for key, value in (("table_name", BASELINE_TABLE), ("model", "energy"), ("fclass", "label"),
                           ("fshower", "b"), ("xgb_task", "angle"), ("xgb_label", "phi"), ("feature", "depth")):
            assert on_physics.get(key) == value, (key, on_physics)
        current = page.evaluate("() => document.querySelector('#page-tabs a.is-current')?.dataset.page")
        assert current == "physics"

        page.click('#page-tabs a[data-page="models"]')
        page.wait_for_url(re.compile(r"/models#"), timeout=30_000)
        page.wait_for_function("(t) => document.getElementById('experiment-select')?.value === t",
                               arg=BASELINE_TABLE, timeout=30_000)
        back = _hash(page)
        assert {k: back.get(k) for k in ("fclass", "fshower", "xgb_task", "xgb_label", "feature")} == {
            "fclass": "label", "fshower": "b", "xgb_task": "angle", "xgb_label": "phi", "feature": "depth"}, back
        browser.close()
    assert problems == [], problems


# -------------------------------------------------------------- the loading --


def test_no_card_asks_before_it_scrolls_into_view(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, MODELS_XGB_TABLE)
        page.wait_for_timeout(800)
        assert page.evaluate("() => document.querySelector('.main').scrollTop") == 0
        # The performance cards stand at the top of the page and load; nothing below them asks.
        assert _requests_of(requests, "/api/model-performance")
        assert not _requests_of(requests, "/api/xgboost"), _urls(requests)
        assert not _requests_of(requests, "/api/features"), _urls(requests)

        state = _scroll_to(page, "xgb-importance")
        assert state["canvas"] and state["series"], state
        assert _requests_of(requests, "/api/xgboost", view="importance", task="momentum")
        assert not _requests_of(requests, "/api/features", view="hist2d")
        state = _scroll_to(page, "feat-hist2d")
        assert state["canvas"] and (state["series"] or state["graphic"]), state
        assert len(_requests_of(requests, "/api/features", view="hist2d")) == 1
        browser.close()

        # The 3-D pairs load on view too: nothing of either before they are scrolled to.
        browser, page, problems2, requests = _open(p, base, SINGLE_HITS_TABLE)
        page.wait_for_timeout(800)
        for route in ("/api/event", "/api/event/pick", "/api/voxels", "/api/projections"):
            assert not _requests_of(requests, route), (route, _urls(requests))
        _scroll_to(page, "vox-ensemble")
        assert _requests_of(requests, "/api/voxels", frame="local")
        assert _requests_of(requests, "/api/projections", coord_system="local", display="native")
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


# ------------------------------------------------------------ every card --


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_every_2d_card_renders_without_a_console_error(models_live_server, table):
    """Every card draws (or states the server's reason), opens its drawer, and draws U+2212."""
    base = models_live_server["base"]
    drawers = []
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, table)
        assert _shown_cards(page) == CARDS[table]
        for card_id in CARDS[table]:
            state = _scroll_to(page, card_id)
            where = f"{table} {card_id}"
            if card_id in SHUT.get(table, ()):
                assert state["kind"] == "disabled" and state["message"], (where, state)
                continue
            assert state["message"] is None, f"{where}: {state['message']}"
            assert state["width"] > 200 and state["height"] > 100, (where, state)
            if card_id == "feat-table":
                assert state["table"], where
            elif card_id in GL_CARDS:
                assert state["canvas"] and "bar3D" in state["seriesTypes"], (where, state)
            else:
                assert state["canvas"] and (state["series"] or state["graphic"]), (where, state)
            title, headings, body = _drawer(page, card_id)
            assert title == state["title"], where
            _assert_sections(headings, where)
            drawers.append(body)
        drawn = page.evaluate("() => window.__drawnText")
        dom = page.evaluate("() => document.querySelector('.main').innerText")
        browser.close()
    assert problems == [], problems
    assert len(drawn) > 100, "no canvas text was recorded"
    assert _hyphen_negatives(drawn) == [], "canvas text with an ASCII hyphen-minus"
    assert _hyphen_negatives([dom]) == [], "card text with an ASCII hyphen-minus"
    assert _hyphen_negatives(drawers) == [], "drawer text with an ASCII hyphen-minus"


#: The cards on show, and any element that runs past its card's left or right edge. Content inside a
#: horizontal scroller of the card (the resolution card's fit table, `.res-fit-table { overflow-x: auto }`)
#: is clipped there and judged by its scroller, which is itself checked as an element of the card.
_OVERFLOW = """() => {
  const main = document.querySelector('.main');
  const cards = [];
  const scrolled = (el, card) => {
    for (let a = el.parentElement; a && a !== card; a = a.parentElement) {
      if (['auto', 'scroll'].includes(getComputedStyle(a).overflowX)) return true;
    }
    return false;
  };
  for (const card of document.querySelectorAll('.main .card[data-panel]')) {
    if (card.hidden || !card.offsetParent) continue;
    const r = card.getBoundingClientRect();
    const out = [...card.querySelectorAll('*')].filter((el) => {
      const b = el.getBoundingClientRect();
      return b.width > 0 && (b.right > r.right + 0.5 || b.left < r.left - 0.5) && !scrolled(el, card);
    }).map((el) => `${el.tagName}.${el.className}`);
    if (out.length) cards.push([card.dataset.panel, out.slice(0, 3)]);
  }
  return { main: [main.scrollWidth, main.clientWidth], cards };
}"""


@pytest.mark.parametrize("viewport", [(1600, 900), (1280, 800)], ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_no_card_runs_past_its_edge(models_live_server, table, viewport):
    """The toolbars wrap inside their cards (models.css): unwrapped, the feature histogram's ran 212 px
    past its card at 1280 px, and the 3-D event's past its column on two showers."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], table, viewport=viewport)
        for card_id in CARDS[table]:
            _scroll_to(page, card_id)
        measured = page.evaluate(_OVERFLOW)
        browser.close()
    assert measured["cards"] == [], measured
    assert measured["main"][0] <= measured["main"][1], measured
    assert problems == [], problems


# --------------------------------------------------------------- tooltips --


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_tooltips_use_the_layer_and_never_cover_the_hovered_plot(models_live_server, table):
    base = models_live_server["base"]
    totals = {"readouts": 0, "explanations": 0}
    tips = []
    shares = {}
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, table)
        for card_id in CARDS[table]:
            if card_id == "feat-table" or card_id in SHUT.get(table, ()):
                continue
            _scroll_to(page, card_id)
            columns, rows = (7, 5) if card_id in GL_CARDS else (9, 6)
            found = _hover_chart(page, f"plot-{card_id}", columns=columns, rows=rows)
            rest, worst = _projection_readouts(found, f"{table} {card_id}")
            shares[card_id] = round(worst, 3)
            readouts, explanations = _check_tips(rest, f"{table} {card_id}")
            totals["readouts"] += len(found) - len(rest)
            totals["readouts"] += readouts
            totals["explanations"] += explanations
            tips += [probe["text"] for _, probe, _ in found]
            if card_id == "res-scaling" and table in RES_DRAWN:
                # Its markers, lines and bands explain themselves on the layer, and none covers more than the
                # cap of the plot being read (a band's or a fit's tooltip is an explanation: it leaves the plot).
                assert found, f"{table} res-scaling: no tooltip over its fits and bands"
                covered = []
                for (x, y), probe, boxes in found:
                    plot = boxes["plot"]
                    area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
                    covered.append(_overlap(probe["tip"], plot) / area)
                    assert covered[-1] <= PROJECTION_READOUT_SHARE, (table, (x, y), probe["text"][:60], covered[-1])
                shares[card_id] = round(max(covered), 3)
        browser.close()
    assert totals["explanations"], totals
    print(f"largest share of a plot under a projection readout, {table}: {shares}")
    # The paired projections' column is as wide as the 3-D card's (models.css): the Local entry
    # panel's readout covered up to 64% of its plot at 3 : 2, 33% at 1 : 1.
    assert max(shares.values(), default=0) <= PROJECTION_READOUT_SHARE, shares
    assert _hyphen_negatives(tips) == [], "tooltip text with an ASCII hyphen-minus"
    assert problems == [], problems


# ----------------------------------------------------------------- export --


@pytest.mark.parametrize("table", [SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_the_2d_cards_export_their_plot_alone_and_the_3d_cards_have_no_export(models_live_server, table):
    base = models_live_server["base"]
    exported, series = {}, {}
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, table)
        page.evaluate(_WATCH_EXPORTS)
        for card_id in CARDS[table]:
            state = _scroll_to(page, card_id)
            if card_id in GL_CARDS or card_id == "feat-table":
                assert state["exportButtons"] == 0, (card_id, "a 3-D view or a table is not a figure")
                continue
            assert state["exportButtons"] == 1, card_id
            live = _live_series(page, f"plot-{card_id}")
            exported[card_id] = _download_svg(page, card_id)
            series[card_id] = (live, page.evaluate("() => window.__exportSeries.at(-1)"))
        browser.close()
    assert problems == [], problems
    for card_id, (name, svg) in exported.items():
        texts = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
        assert name.startswith(f"{card_id}_") and name.endswith(".svg"), name
        assert 'width="321"' in svg, card_id
        assert re.search(r'<rect[^>]*fill="#FFFFFF"', svg), f"{card_id}: not on white"
        assert "figure-disclosure" not in svg and "Experiment " not in svg, card_id
        assert texts, card_id
        assert _hyphen_negatives(texts) == [], (card_id, _hyphen_negatives(texts))
        if card_id == "res-scaling":
            # The plot alone: both x axes (the top one's ∞ at the origin) and no row of the screen's fit table.
            assert "∞" in texts and any("1/√E" in t for t in texts), texts
            assert not [t for t in texts if "Windows fitted" in t or "Quadrature" in t or "SE(a" in t], texts
    for card_id, (live, printed) in series.items():
        assert printed is not None and printed > 0, (card_id, live, printed)


# ------------------------------------------------- the energy-resolution card --

#: The resolution card's axes as the chart holds them, the top axis's labels through its own formatter,
#: any series not on the bottom axis, and where the axes put values on the canvas.
_RES_AXES = """() => {
  const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
  const o = inst.getOption();
  const x = (o.xAxis || []).map((a) => ({
    position: a.position ?? null, inverse: Boolean(a.inverse), min: a.min, max: a.max, name: a.name,
    values: a.axisLabel?.customValues ?? null, ticks: a.axisTick?.customValues ?? null,
    labels: (a.axisLabel?.customValues ?? []).map((v) =>
      (typeof a.axisLabel.formatter === 'function' ? a.axisLabel.formatter(v) : String(v))),
  }));
  const y = (o.yAxis || []).map((a) => ({ min: a.min, max: a.max, name: a.name }));
  const offBottom = (o.series || []).filter((s) => (s.xAxisIndex ?? 0) !== 0).map((s) => s.id ?? s.name);
  let px = null;
  if (x.length === 2 && y.length) {
    const rect = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
    const at = (i, v) => inst.convertToPixel({ xAxisIndex: i }, v);
    px = { grid: { left: rect.x, right: rect.x + rect.width, top: rect.y, bottom: rect.y + rect.height },
           bottom: [0, 0.1, 0.25, 0.5].map((v) => at(0, v)), top: [0, 0.1, 0.25, 0.5].map((v) => at(1, v)),
           y0: inst.convertToPixel({ yAxisIndex: 0 }, 0) };
  }
  return { x, y, offBottom, px, series: (o.series || []).length, graphic: (o.graphic || []).length };
}"""

#: The card's fit table: where it sits against the plot, and what it says.
_RES_TABLE = """() => {
  const card = document.querySelector('.main .card[data-panel="res-scaling"]');
  const host = card.querySelector('.res-fit-table');
  if (!host) return null;
  const frame = card.querySelector('.plot-frame');
  const plot = document.getElementById('plot-res-scaling');
  const box = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
  return {
    inFrame: frame.contains(host), afterFrame: frame.nextElementSibling === host, inCard: card.contains(host),
    host: box(host), plot: box(plot),
    caption: host.querySelector('caption')?.textContent ?? null,
    heads: [...host.querySelectorAll('thead th')].map((th) => th.textContent),
    rows: [...host.querySelectorAll('tbody tr')].map((tr) => tr.cells[0].textContent),
  };
}"""

#: Every series the resolution card draws, with its data: what a repaint changes.
_RES_SERIES = """() => JSON.stringify((echarts.getInstanceByDom(document.getElementById('plot-res-scaling'))
  .getOption().series || []).map((s) => [s.id ?? s.name, s.data]))"""


def _res_press(page, attr, value):
    """Click one of the resolution card's segmented buttons; whether it is then the pressed one."""
    button = page.locator(f'.main .card[data-panel="res-scaling"] button[data-{attr}="{value}"]')
    button.click()
    page.wait_for_timeout(250)
    return button.get_attribute("aria-pressed") == "true"


def _theme_module():
    """test_browser_theme.py's probes (`_AXIS_INK`, `MUTED`, `_CAMERA`, `_GL_DRAWN`). Imported when a test runs:
    that module imports this one at its top."""
    import test_browser_theme
    return test_browser_theme


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_the_resolution_card_draws_its_axes_and_fit_table_and_repaints_without_a_request(models_live_server, table):
    """The res-scaling card (plan §2.6-§2.7): the bottom axis 1/√E runs reversed over [0, 0.5], so x = 0 is the
    right border; the top axis is the same range relabelled E = 1/x² with ∞ at 0, carries no series and puts every
    value at the bottom axis's pixel; the y axis starts at 0 on the plot's bottom edge, so the bottom-right corner is
    the origin. The fit table sits under the plot, outside the chart. "3 anchors" / "All ≥ 4 GeV", the shower
    buttons (two showers) and a theme switch repaint from the response in hand."""
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], table)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        asked = _requests_of(requests, "/api/resolution-scaling")
        assert len(asked) == 1, _urls(requests)
        # A networked plan names the energy network's frame (models_cards.js cardRequest).
        assert (asked[0].get("coord_system") == "lab") is (table == BASELINE_TABLE), asked
        axes = page.evaluate(_RES_AXES)
        fit = page.evaluate(_RES_TABLE)
        series = page.evaluate(_RES_SERIES)
        before = len(requests)

        # The fit table: after the plot frame, inside the card, below the plot and clear of it.
        assert fit is not None and fit["inCard"] and fit["afterFrame"] and not fit["inFrame"], fit
        assert fit["host"]["top"] >= fit["plot"]["bottom"] - 0.5, fit
        assert fit["caption"].startswith("Fits through the 3 anchor windows"), fit
        assert fit["heads"][0] == "Series" and "Windows fitted" in fit["heads"], fit
        assert fit["rows"], fit

        if table in RES_DRAWN:
            assert state["series"] > 0, state
            bottom, top = axes["x"]
            assert bottom["position"] in (None, "bottom") and bottom["inverse"], bottom
            assert (bottom["min"], bottom["max"]) == (0, 0.5) and "1/√E" in bottom["name"], bottom
            assert top["position"] == "top" and top["inverse"] and (top["min"], top["max"]) == (0, 0.5), top
            assert top["name"].startswith("Energy (GeV)"), top
            assert top["values"] == top["ticks"] and 0 in top["values"], top
            assert top["labels"][top["values"].index(0)] == "∞", top
            assert "5" in top["labels"] and "10" in top["labels"], top
            # E = 1/x²: every labelled energy sits at its own 1/√E.
            for x, label in zip(top["values"], top["labels"]):
                if label != "∞":
                    assert x == pytest.approx(1 / float(label) ** 0.5, abs=1e-5), (x, label)
            assert axes["offBottom"] == [], "no series is drawn against the top axis"
            assert [a["min"] for a in axes["y"]] == [0] and axes["y"][0]["max"] > 0, axes["y"]
            # The origin corner: x = 0 at the right border, 0.5 at the left, y = 0 on the bottom edge,
            # and the top axis an exact relabelling of the bottom one.
            px = axes["px"]
            assert px["bottom"][0] == pytest.approx(px["grid"]["right"], abs=0.5), px
            assert px["bottom"][-1] == pytest.approx(px["grid"]["left"], abs=0.5), px
            assert px["top"] == pytest.approx(px["bottom"], abs=0.01), px
            assert px["y0"] == pytest.approx(px["grid"]["bottom"], abs=0.5), px

            # Every window from 4 GeV, then the anchors again: a repaint, back to the same picture.
            assert _res_press(page, "res-windows", "all")
            assert page.evaluate(_RES_SERIES) != series
            assert page.evaluate(_RES_TABLE)["caption"] != fit["caption"]
            assert _res_press(page, "res-windows", "anchors")
            assert page.evaluate(_RES_SERIES) == series and page.evaluate(_RES_TABLE) == fit
            # One shower: no shower buttons.
            assert page.evaluate("() => document.querySelector('.main .card[data-panel=\"res-scaling\"] "
                                 "[aria-label=\"Showers\"]').hidden") is True
        else:
            # Two events hold no window of two events from 4 GeV: the empty state, said on the chart.
            assert state["series"] == 0 and state["graphic"] == 1, state
            texts = page.evaluate(_CHART_TEXTS, "plot-res-scaling")
            assert any("no σ/E can be drawn" in t for t in texts), texts
            assert {r.split(" · ")[0] for r in fit["rows"]} == {"Shower A", "Shower B"}, fit
            assert _res_press(page, "res-windows", "all")
            assert page.evaluate(_RES_TABLE)["caption"] != fit["caption"]
            assert _res_press(page, "res-windows", "anchors")
            # Each shower alone, then both: the table follows, the chart is repainted from the same response.
            for shower, letters in (("a", {"Shower A"}), ("b", {"Shower B"}), ("both", {"Shower A", "Shower B"})):
                assert _res_press(page, "models-shower", shower), shower
                rows = page.evaluate(_RES_TABLE)["rows"]
                assert rows and {r.split(" · ")[0] for r in rows} == letters, (shower, rows)
            assert page.evaluate(_RES_TABLE) == fit
        assert requests[before:] == [], f"a render-only control asked the service: {requests[before:]}"

        # A theme switch repaints the chart and the table from the response in hand.
        dark = page.evaluate(theme._AXIS_INK, "plot-res-scaling")
        page.click("#theme-toggle")
        page.wait_for_timeout(1200)
        assert requests[before:] == [], f"a theme switch asked the service: {requests[before:]}"
        assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
        if table in RES_DRAWN:
            light = page.evaluate(theme._AXIS_INK, "plot-res-scaling")
            assert theme.MUTED["dark"] in dark and theme.MUTED["light"] in light and theme.MUTED["dark"] not in light, \
                (dark, light)
            # The picture is the same one: the same axes and the same series, in the new ink.
            assert page.evaluate(_RES_AXES)["x"] == axes["x"]
        assert page.evaluate(_RES_TABLE)["rows"] == fit["rows"]
        browser.close()
    assert problems == [], problems


# ---------------------------------------------------------------- 3-D views --


def test_the_3d_cards_render_in_swiftshader_with_at_most_two_gl_contexts(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE, init=(_COUNT_GL,))
        for card_id in EVENT_PAIR + ENSEMBLE_PAIR:
            state = _scroll_to(page, card_id)
            assert state["message"] is None, (card_id, state)
        for card_id in GL_CARDS:
            state = page.evaluate(_CARD, card_id)
            # The plot's height follows its width and its box (P-18, voxels.js glPlotHeight).
            assert "bar3D" in state["seriesTypes"] and GL_HEIGHTS[0] <= state["height"] <= GL_HEIGHTS[1], state
            assert page.evaluate(f"() => echarts.getInstanceByDom(document.getElementById('plot-{card_id}'))"
                                 ".getOption().grid3D[0].viewControl.projection") == "orthographic"
        live = page.evaluate(_LIVE_GL)
        assert sorted(live) == ["vox-ensemble", "vox-event"], live
        # A change of the 3-D event's channel redraws on the same chart: still two contexts.
        page.select_option('.card[data-panel="vox-event"] select[data-voxel-channel]', "species")
        _settled(page, "vox-event")
        page.wait_for_timeout(800)
        assert len(page.evaluate(_LIVE_GL)) <= 2
        # The ensemble box is the paired projections' window; its drawer gives the grid's extent.
        title, headings, body = _drawer(page, "vox-ensemble")
        assert "cropped to the paired projections' window" in body and "The accumulation grid spans" in body
        # The opening view is fitted to the box (test_the_3d_cards_open_fitted_to_their_box). A narrower
        # window refits the zoom and the camera's viewport alone, and the reader's rotation stays.
        for card_id in GL_CARDS:
            zoom = page.evaluate(_ZOOM, card_id)
            # The viewport keeps the area left of the legend's aspect and covers it.
            assert zoom["vw"] / zoom["vh"] == pytest.approx((zoom["w"] - zoom["right"]) / zoom["h"], rel=2e-3), zoom
            assert zoom["left"] <= 0.05 and zoom["left"] + zoom["vw"] >= zoom["w"] - zoom["right"] - 0.05, zoom
        page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-vox-event'))"
                      ".dispatchAction({ type: 'grid3DChangeCamera', alpha: 10, beta: 70 })")
        wide = page.evaluate(_ZOOM, "vox-event")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(1500)
        zoom = page.evaluate(_ZOOM, "vox-event")
        assert zoom["w"] < wide["w"] and GL_HEIGHTS[0] <= zoom["h"] <= wide["h"], (wide, zoom)
        assert (zoom["size"], zoom["vw"], zoom["vh"]) != (wide["size"], wide["vw"], wide["vh"]), (wide, zoom)
        assert zoom["vw"] / zoom["vh"] == pytest.approx((zoom["w"] - zoom["right"]) / zoom["h"], rel=2e-3), zoom
        assert (zoom["alpha"], zoom["beta"]) == (10, 70), zoom
        browser.close()

        # Without WebGL the 3-D cards say so, ask for no cubes, and their projections still draw.
        browser, page, problems2, requests = _open(p, base, SINGLE_HITS_TABLE, init=(_NO_WEBGL,))
        for card_id in GL_CARDS:
            page.locator(f'.card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            state = _settled(page, card_id)
            assert state["kind"] == "notice" and state["message"].startswith(GL_UNAVAILABLE), state
            # No volume, so no slice row: K = 1 … L has nothing to cut.
            row = page.evaluate(_SLICE_ROW, card_id)
            assert row is not None and row["hidden"] and not row["visible"], (card_id, row)
            title, headings, body = _drawer(page, card_id)
            assert GL_UNAVAILABLE in body
        for card_id in ("vproj-xy", "vproj-xz", "vproj-yz", "eproj-xy", "eproj-yz", "eproj-xz"):
            state = _scroll_to(page, card_id)
            assert state["message"] is None and state["canvas"] and state["series"], (card_id, state)
        assert not _requests_of(requests, "/api/voxels")
        assert not [u for u in _urls(requests) if "format=voxels" in u]
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


def test_both_showers_draw_in_the_absolute_frame_and_are_shut_with_a_reason_elsewhere(models_live_server):
    """"Both" draws the event's two showers where one coordinate system holds them, and only there.

    In a per-shower frame each shower sits at its own entry point, so the
    button is shut with that reason as its title, rather than offered and then
    drawn as shower A.
    """
    base = models_live_server["base"]
    both = '.card[data-panel="vox-event"] [data-voxel-shower="both"]'
    lit = ("() => [...document.querySelectorAll('.card[data-panel=\"vox-event\"] [data-voxel-shower].is-active')]"
           ".map((b) => b.dataset.voxelShower)")
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, fragment="&model=energy&frame=local")
        _scroll_to(page, "vox-event")
        shut = page.evaluate(f"() => {{ const b = document.querySelector('{both}'); return [b.disabled, b.title]; }}")
        assert shut[0] is True and "Absolute frame only" in shut[1], shut
        assert page.evaluate(lit) == ["a"]
        browser.close()

        browser, page, problems2, requests = _open(p, base, BASELINE_TABLE, fragment="&model=energy&frame=lab")
        _scroll_to(page, "vox-event")
        assert page.evaluate(f"() => document.querySelector('{both}').disabled") is False
        page.click(both)
        page.wait_for_function(
            "() => /showers A and B/.test(document.querySelector('.card[data-panel=\"vox-event\"]').textContent)",
            timeout=30_000)
        assert [u for u in _urls(requests) if "format=voxels" in u and "shower=both" in u]
        assert page.evaluate(lit) == ["both"]
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


@pytest.mark.parametrize("width", [1440, 1600, 1920])
def test_the_3d_cards_open_fitted_to_their_box(models_live_server, width):
    """Fix round Z: the opening zoom fits the drawn box, whatever its shape. On the synthetic single-shower
    event (a flat 7.4 x 100 x 36.6 box) and the two-shower event, at three window widths, every drawn pixel of
    both 3-D cards stays inside the canvas with GL_SPARE px to spare (the 3-D marks inside the area left of the
    legend's strip), and the marks span at least GL_FILL of the limiting dimension."""
    base = models_live_server["base"]
    seen = {}
    with models_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        problems = []
        for table in (SINGLE_HITS_TABLE, BASELINE_TABLE):
            _, page, found, _ = _open(p, base, table, viewport=(width, 900), browser=browser)
            problems += found
            for card_id in GL_CARDS:
                state = _scroll_to(page, card_id)
                assert state["message"] is None and "bar3D" in state["seriesTypes"], (table, card_id, state)
                page.wait_for_timeout(600)
                got = _gl_extent(page, card_id)
                seen[(table, card_id)] = got
                assert GL_HEIGHTS[0] <= got["zoom"]["h"] <= GL_HEIGHTS[1], (table, card_id, got)
                assert min(got["spare"].values()) >= GL_SPARE, (table, card_id, got)
                assert min(got["whole"].values()) >= GL_SPARE, (table, card_id, got)
                assert got["fill"] >= GL_FILL, (table, card_id, got)
            page.close()
        browser.close()
    print(f"3-D opening fill at {width} px: " + ", ".join(f"{t} {c} {g['fill']}" for (t, c), g in seen.items()))
    assert problems == [], problems


# ------------------------------------------------------------ the slice mode --

#: A 3-D card's slice row (voxel_views.js buildSliceRow): shown, the count and its bound, the scrubber,
#: the step buttons and the readout, and where the row sits in the card.
_SLICE_ROW = """(id) => {
  const card = document.querySelector(`.main .card[data-panel="${id}"]`);
  const row = card?.querySelector('.voxel-slices');
  if (!row) return null;
  const q = (s) => row.querySelector(s);
  const count = q('[data-voxel-slices]'), range = q('[data-voxel-slice]');
  return {
    hidden: row.hidden, visible: row.offsetParent !== null,
    K: count.value, max: count.max, k: range.value, kMax: range.max, rangeDisabled: range.disabled,
    prev: q('[data-voxel-slice-step="prev"]').disabled, next: q('[data-voxel-slice-step="next"]').disabled,
    readout: q('.voxel-slice-readout').textContent, live: q('.voxel-slice-readout').getAttribute('aria-live'),
    beforePlot: row.nextElementSibling === card.querySelector('.plot-frame'),
  };
}"""

#: The cubes a 3-D card draws: every bar3D series' data.
_CUBES = """(id) => echarts.getInstanceByDom(document.getElementById(`plot-${id}`)).getOption().series
  .filter((s) => s.type === 'bar3D').reduce((n, s) => n + (s.data || []).length, 0)"""

#: A projection's slice band (projection.js addDepthSlab): the wash's depth range and its two faces, or null.
_DEPTH_BAND = """(id) => {
  const series = echarts.getInstanceByDom(document.getElementById(`plot-${id}`)).getOption().series || [];
  const wash = series.find((s) => s.name === 'Depth slice drawn in 3-D');
  const faces = series.filter((s) => (s.name || '').startsWith('Depth slice drawn in 3-D — ')).length;
  if (!wash) return faces ? { lo: null, hi: null, faces } : null;
  const points = wash.data[0];
  return { lo: points[0][0], hi: points[points.length - 1][0], faces };
}"""

#: Each 3-D card, its XY projection and its two depth projections (voxel_views.js: `col.name === 'z'`).
SLICE_PAIRS = {"vox-event": ("vproj-xy", ("vproj-xz", "vproj-yz")),
               "vox-ensemble": ("eproj-xy", ("eproj-yz", "eproj-xz"))}


def _set_slices(page, card_id, value):
    """Type K into a 3-D card's count and commit it (`change`, as the input does on Enter or blur)."""
    count = page.locator(f'.main .card[data-panel="{card_id}"] [data-voxel-slices]')
    count.fill(str(value))
    count.dispatch_event("change")
    page.wait_for_timeout(250)


def _step_slice(page, card_id, direction):
    page.click(f'.main .card[data-panel="{card_id}"] [data-voxel-slice-step="{direction}"]')
    page.wait_for_timeout(250)


def _scrub_slice(page, card_id, k):
    """Drag the scrubber to slice k: the range input's value and its `input` event, as a drag fires."""
    page.locator(f'.main .card[data-panel="{card_id}"] [data-voxel-slice]').evaluate(
        "(el, k) => { el.value = String(k); el.dispatchEvent(new Event('input', { bubbles: true })); }", k)
    page.wait_for_timeout(250)


def _turn_and_zoom(page, card_id):
    """The reader turns the cubes with a drag and zooms with the wheel (test_browser_theme.py's gesture)."""
    page.locator(f'.main .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    box = page.locator(f"#plot-{card_id}").bounding_box()
    x, y = box["x"] + box["width"] * 0.4, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y + 25, steps=8)
    page.mouse.up()
    for _ in range(3):
        page.mouse.wheel(0, -200)
        page.wait_for_timeout(120)
    page.wait_for_timeout(500)


def _slice_view(page, card_id, camera):
    """What a slice step must and must not move: the row, the cubes, the bands and the camera."""
    xy, depth = SLICE_PAIRS[card_id]
    return {
        "row": page.evaluate(_SLICE_ROW, card_id),
        "cubes": page.evaluate(_CUBES, card_id),
        "xy": page.evaluate(_DEPTH_BAND, xy),
        "bands": [page.evaluate(_DEPTH_BAND, c) for c in depth],
        "camera": page.evaluate(camera, card_id)["control"],
    }


def test_the_3d_slices_step_with_no_request_and_keep_the_turned_and_zoomed_camera(models_live_server):
    """The slice mode (plan §3.4-§3.6) on the two-shower event in the Absolute frame (37 layers) and on the
    co-registered cloud, in Chromium with SwiftShader WebGL.

    The row shows once the cubes are drawn, at K = 1 (the whole volume, no band). After the reader has turned
    and wheel-zoomed the view: K = 6 reads "Slice 1 of 6", Next twice "Slice 3 of 6", Previous and the
    scrubber step, each button is disabled at its end, and a K above the volume's depth L is drawn as L, the
    count's max. The cubes drawn change with the slice and the six slices' cubes add up to the whole
    volume's. The paired depth projections band the slice drawn (moving with Next), the XY projection never,
    and the band prints in the depth projection's export only while a slice is shown. Across every step the
    request log gains nothing and the camera (alpha, beta, the orthographic zoom, the centre) does not move;
    the page still holds at most two WebGL contexts.
    """
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, models_live_server["base"], BASELINE_TABLE, fragment="&model=energy&frame=lab", init=(_COUNT_GL,))
        page.evaluate(_WATCH_EXPORTS)
        for card_id, (xy, depth) in SLICE_PAIRS.items():
            for cell in (card_id, xy, *depth):
                state = _scroll_to(page, cell)
                assert state["message"] is None, (cell, state)
            page.wait_for_function(theme._GL_DRAWN, arg=card_id, timeout=30_000)
            page.wait_for_timeout(600)
            where = card_id

            # K = 1: the whole volume, the row shown with nothing to step, no band anywhere.
            whole = _slice_view(page, card_id, theme._CAMERA)
            row = whole["row"]
            assert row["visible"] and not row["hidden"] and row["beforePlot"], (where, row)
            assert row["K"] == "1" and row["k"] == "1" and row["rangeDisabled"], (where, row)
            assert row["prev"] and row["next"] and row["live"] == "polite", (where, row)
            assert row["readout"].startswith("Slice 1 of 1 — "), (where, row)
            depth_bins = int(row["max"])
            assert depth_bins > 6, (where, row)
            assert whole["xy"] is None and whole["bands"] == [None, None], (where, whole)
            if card_id == "vox-event":
                assert "layers 1–" in row["readout"] and "z − 3649 = " in row["readout"], row["readout"]
                page.locator(f'.main .card[data-panel="{depth[0]}"]').scroll_into_view_if_needed()
                _download_svg(page, depth[0])
                unsliced_export = page.evaluate("() => window.__exportSeries.at(-1)")

            _turn_and_zoom(page, card_id)
            camera = page.evaluate(theme._CAMERA, card_id)
            assert camera["control"]["zoom"] != pytest.approx(camera["model"]["size"]), (where, "the wheel did not zoom")
            assert (camera["control"]["alpha"], camera["control"]["beta"]) != (25, 40), (where, "the drag did not turn")
            before = len(requests)

            # K = 6: the first slice, at the entrance.
            _set_slices(page, card_id, 6)
            views = {1: _slice_view(page, card_id, theme._CAMERA)}
            row = views[1]["row"]
            assert row["readout"].startswith("Slice 1 of 6 — "), (where, row)
            assert (row["K"], row["k"], row["kMax"]) == ("6", "1", "6") and not row["rangeDisabled"], (where, row)
            assert row["prev"] and not row["next"], (where, "Previous is shut at slice 1", row)
            assert views[1]["xy"] is None, (where, "the XY projection sums every layer and carries no band")
            assert all(b and b["faces"] == 2 and b["hi"] > b["lo"] for b in views[1]["bands"]), (where, views[1])

            # Next twice: slice 3; the band moves downstream.
            _step_slice(page, card_id, "next")
            views[2] = _slice_view(page, card_id, theme._CAMERA)
            _step_slice(page, card_id, "next")
            views[3] = _slice_view(page, card_id, theme._CAMERA)
            assert views[3]["row"]["readout"].startswith("Slice 3 of 6 — "), (where, views[3]["row"])
            assert views[3]["row"]["k"] == "3" and not views[3]["row"]["prev"] and not views[3]["row"]["next"]
            for b1, b2, b3 in zip(views[1]["bands"], views[2]["bands"], views[3]["bands"]):
                assert b1["hi"] == pytest.approx(b2["lo"]) and b2["hi"] == pytest.approx(b3["lo"]), (where, b1, b2, b3)
            # Previous: slice 2 again, the same picture.
            _step_slice(page, card_id, "prev")
            again = _slice_view(page, card_id, theme._CAMERA)
            assert again["row"]["readout"] == views[2]["row"]["readout"] and again["cubes"] == views[2]["cubes"]
            assert again["bands"] == views[2]["bands"], where
            # The scrubber: the last slice, where Next is shut; then the rest of the six.
            _scrub_slice(page, card_id, 6)
            views[6] = _slice_view(page, card_id, theme._CAMERA)
            assert views[6]["row"]["readout"].startswith("Slice 6 of 6 — "), (where, views[6]["row"])
            assert views[6]["row"]["next"] and not views[6]["row"]["prev"], (where, "Next is shut at the last slice")
            for k in (5, 4):
                _scrub_slice(page, card_id, k)
                views[k] = _slice_view(page, card_id, theme._CAMERA)
                assert views[k]["row"]["readout"].startswith(f"Slice {k} of 6 — "), (where, k, views[k]["row"])
            counts = [views[k]["cubes"] for k in range(1, 7)]
            assert sum(counts) == whole["cubes"], (where, counts, whole["cubes"])
            assert len(set(counts)) > 1 and max(counts) < whole["cubes"], (where, counts)
            # The six bands tile the depth the slices cover, entrance first.
            for column in range(2):
                bands = [views[k]["bands"][column] for k in range(1, 7)]
                assert all(a["hi"] == pytest.approx(b["lo"]) for a, b in zip(bands, bands[1:])), (where, bands)

            if card_id == "vox-event":
                # The band prints with the depth projection while a slice is shown (wash and two faces).
                page.locator(f'.main .card[data-panel="{depth[0]}"]').scroll_into_view_if_needed()
                _download_svg(page, depth[0])
                assert page.evaluate("() => window.__exportSeries.at(-1)") == unsliced_export + 3
                page.locator(f'.main .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
                page.wait_for_timeout(300)

            # A K above the volume's depth is drawn as L, the count's own bound.
            _set_slices(page, card_id, depth_bins + 7)
            row = page.evaluate(_SLICE_ROW, card_id)
            assert (row["K"], row["max"], row["kMax"]) == (str(depth_bins),) * 3, (where, row)
            assert re.match(rf"^Slice \d+ of {depth_bins} — ", row["readout"]), (where, row)
            # And K = 1 is the whole volume again, the bands gone.
            _set_slices(page, card_id, 1)
            back = _slice_view(page, card_id, theme._CAMERA)
            assert back["cubes"] == whole["cubes"] and back["bands"] == [None, None], (where, back)
            assert back["row"]["readout"] == whole["row"]["readout"], where

            assert requests[before:] == [], f"{where}: a slice step asked the service: {requests[before:]}"
            for k, view in {**views, "again": again, "back": back}.items():
                assert view["camera"] == camera["control"], (where, k, camera["control"], view["camera"])
        assert len(page.evaluate(_LIVE_GL)) <= 2, page.evaluate(_LIVE_GL)
        browser.close()
    assert problems == [], problems


# ------------------------------------------------------------------ XGBoost --


def _xgb_view(requests, view, task=None):
    params = {"view": view, **({"task": task} if task else {})}
    return _requests_of(requests, "/api/xgboost", **params)


def test_the_xgboost_cards_render_for_both_tasks_with_the_output_switch(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, MODELS_XGB_TABLE)
        for card_id in XGB:
            state = _scroll_to(page, card_id)
            assert state["message"] is None and state["canvas"] and state["series"], (card_id, state)
        for view in ("cv", "surrogate", "importance"):
            assert _xgb_view(requests, view, "momentum"), view
        assert _xgb_view(requests, "binary")
        # The momentum surrogate is coloured on the ramp; its fidelity is printed per output.
        texts = page.evaluate(_CHART_TEXTS, "plot-xgb-surrogate")
        assert any(t.startswith("Fidelity to the booster: R²") for t in texts), texts
        assert page.evaluate("() => document.querySelector('.card[data-panel=\"xgb-surrogate\"] "
                             "[aria-label=\"Output\"]').hidden") is True

        # The angle task, from the cross-validation card: the shared key, so every task card follows.
        _scroll_to(page, "xgb-cv")
        page.click('.card[data-panel="xgb-cv"] button[data-xgb-task="angle"]')
        assert _hash(page).get("xgb_task") == "angle"
        for card_id in ("xgb-cv", "xgb-surrogate", "xgb-importance"):
            page.locator(f'.card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            state = _settled(page, card_id)
            assert state["message"] is None and state["series"], (card_id, state)
        for view in ("cv", "surrogate", "importance"):
            assert _xgb_view(requests, view, "angle"), view
        # One recorded angle split is not reproduced: every angle card flags it.
        flagged = page.evaluate("() => [...document.querySelectorAll('#xgb-grid button[data-inspect].is-flagged')]"
                                ".map((b) => b.dataset.inspect)")
        assert {"xgb-cv", "xgb-surrogate", "xgb-importance"} <= set(flagged), flagged

        # The surrogate's output switch is a repaint: θ coloured, φ not, no new request.
        _scroll_to(page, "xgb-surrogate")
        assert page.evaluate("() => document.querySelector('.card[data-panel=\"xgb-surrogate\"] "
                             "[aria-label=\"Output\"]').hidden") is False
        asked = len(_xgb_view(requests, "surrogate"))
        page.click('.card[data-panel="xgb-surrogate"] button[data-xgb-label="theta"]')
        page.wait_for_timeout(300)
        theta = page.evaluate(_CHART_TEXTS, "plot-xgb-surrogate")
        assert any("polar angle θ" in t for t in theta) and any("θ R²" in t for t in theta), theta
        page.click('.card[data-panel="xgb-surrogate"] button[data-xgb-label="phi"]')
        page.wait_for_timeout(300)
        phi = page.evaluate(_CHART_TEXTS, "plot-xgb-surrogate")
        assert any(t.startswith("φ is not coloured") or t.startswith("φ: not coloured") for t in phi), phi
        # Each output's own fidelity: φ judged on the circle (decision D-5), θ on the linear R².
        assert any("φ circular R²" in t and "θ R²" in t for t in phi), ("each output's own fidelity is printed", phi)
        assert len(_xgb_view(requests, "surrogate")) == asked, "the output switch is a repaint"
        assert _hash(page).get("xgb_label") == "phi"

        # The prediction cards' φ / θ switch asks for the other output and relabels the axes.
        _scroll_to(page, "pred-truth")
        page.click('.card[data-panel="pred-truth"] button[data-xgb-label="theta"]')
        page.wait_for_timeout(300)
        state = _settled(page, "pred-truth")
        assert state["message"] is None, state
        assert _requests_of(requests, "/api/prediction-density", model="angle", label="theta")
        axes = page.evaluate("() => { const o = echarts.getInstanceByDom(document.getElementById('plot-pred-truth'))"
                             ".getOption(); return [...o.xAxis, ...o.yAxis].map((a) => a.name).join(' | '); }")
        assert "θ" in axes and "φ" not in axes, axes
        page.click('.card[data-panel="pred-truth"] button[data-xgb-label="phi"]')
        page.wait_for_timeout(300)
        _settled(page, "pred-truth")
        assert _requests_of(requests, "/api/prediction-density", model="angle", label="phi")
        axes = page.evaluate("() => { const o = echarts.getInstanceByDom(document.getElementById('plot-pred-truth'))"
                             ".getOption(); return [...o.xAxis, ...o.yAxis].map((a) => a.name).join(' | '); }")
        assert "φ" in axes and "θ" not in axes, axes
        browser.close()
    assert problems == [], problems


def _residual_series(page):
    return page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-pred-residuals'))"
                         ".getOption().series.map((s) => ({ name: s.name, type: s.type }))")


def test_the_phi_residual_card_draws_no_mean_marker_whisker_or_sigma_band(models_live_server):
    """φ wraps: its residual is drawn on (−π, π] with no arithmetic-mean mark (CLAUDE.md section 2)."""
    base = models_live_server["base"]
    mean_marks = re.compile(r"· mean|mean 95%|SD band|σ band|interval|whisker", re.IGNORECASE)
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, MODELS_XGB_TABLE, fragment="&xgb_task=angle&xgb_label=phi")
        state = _scroll_to(page, "pred-residuals")
        assert state["message"] is None and state["series"], state
        phi = _residual_series(page)
        assert phi and not [s["name"] for s in phi if mean_marks.search(s["name"] or "")], phi
        axis = page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-pred-residuals'))"
                             ".getOption().xAxis[0].name")
        # The axis is in mrad, so its period is written in mrad too (P-24: one unit per label).
        assert "wrapped to (−3142, 3142]" in axis, axis
        title, headings, body = _drawer(page, "pred-residuals")
        assert "circular" in body.lower() and "R̄" in body
        # θ is linear: the same card draws its mean and the mean's interval (the control).
        # The output switch lives on the prediction-against-truth card; both cards read one request.
        page.click('.card[data-panel="pred-truth"] button[data-xgb-label="theta"]')
        page.wait_for_timeout(400)
        _settled(page, "pred-residuals")
        theta = _residual_series(page)
        assert any((s["name"] or "").endswith("· mean") for s in theta), theta
        browser.close()
    assert problems == [], problems


# ------------------------------------------------------ the shower toggle --


def test_the_feature_explorer_asks_for_one_shower_and_keeps_it_in_the_link(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE)
        for card_id in FEATURES:
            _scroll_to(page, card_id)
        for view in ("describe", "corr", "hist", "hist2d"):
            assert _requests_of(requests, "/api/features", view=view, shower="a"), view
        assert "fshower" not in _hash(page), "the default is never written"
        before = len(_requests_of(requests, "/api/features", shower="b"))
        page.click('.card[data-panel="feat-hist"] button[data-feature-shower="b"]')
        assert _hash(page).get("fshower") == "b"
        for card_id in FEATURES:
            page.locator(f'.card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            state = _settled(page, card_id)
            assert state["message"] is None, (card_id, state)
            pressed = page.get_attribute(f'.card[data-panel="{card_id}"] button[data-feature-shower="b"]',
                                         "aria-pressed")
            assert pressed == "true", card_id
        asked = _requests_of(requests, "/api/features", shower="b")
        assert sorted({q["view"] for q in asked[before:]}) == ["corr", "describe", "hist", "hist2d"]
        assert "event" not in _hash(page) and "shower" not in _hash(page)
        title, headings, body = _drawer(page, "feat-corr")
        assert "shower B" in body
        browser.close()

        # One shower: no toggle, and a link's B never reaches the server.
        browser, page, problems2, requests = _open(p, base, SINGLE_HITS_TABLE, fragment="&fshower=b")
        _scroll_to(page, "feat-hist")
        assert page.evaluate("() => document.querySelector('.card[data-panel=\"feat-hist\"] "
                             "[aria-label=\"Shower\"]').hidden") is True
        assert all("shower" not in q for q in _requests_of(requests, "/api/features"))
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


# ------------------------------------------------------------------- admin --


def test_admin_lists_the_model_runs_and_rescans_them(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, MODELS_XGB_TABLE)
        # The Models page's Admin link opens the panel on the Physics page, with this view.
        page.click('header a.action[data-page-tab]')
        page.wait_for_function("() => !document.getElementById('admin-modal')?.hidden", timeout=30_000)
        page.wait_for_function("() => document.querySelectorAll('.admin-modelruns tbody tr').length > 0",
                               timeout=30_000)
        assert urlparse(page.url).path == "/" and _hash(page).get("table_name") == MODELS_XGB_TABLE
        section = page.evaluate("""() => {
          const s = document.querySelector('.admin-modelruns');
          const cs = getComputedStyle(s);
          return { style: s.getAttribute('style'), marginTop: cs.marginTop, borderTop: cs.borderTopWidth,
                   rows: [...s.querySelectorAll('tbody tr')].map((r) => [...r.cells].map((c) => c.textContent.trim())) };
        }""")
        assert section["style"] is None, "spaced by controls.css, not an inline style"
        assert section["marginTop"] == "18px" and section["borderTop"] == "1px"
        (row,) = [r for r in section["rows"] if r[0].startswith("electron_standalone")]
        assert row[1].startswith("electron, seed 1") and row[2].startswith("done") and row[3] == "Re-analyse"
        # The synthetic angle model barely overfits its labels: its split check fails, and the row says so.
        assert "split not reproduced (angle: " in row[2] and "momentum" not in row[2].split("split not reproduced")[1]
        assert page.evaluate("() => [...document.querySelectorAll('.admin-modelruns tbody td.admin-warning')].length") == 1
        gets = len([u for u in _urls(requests) if urlparse(u).path == "/api/admin/model-runs"])
        assert gets >= 1 and not [u for u in _urls(requests, "POST") if "/model-runs" in u], "the list is read-only"

        with page.expect_response(lambda r: r.url.endswith("/api/admin/model-runs/scan")
                                  and r.request.method == "POST") as scan:
            page.click(".admin-modelruns button[data-rescan-models]")
        assert scan.value.status == 200
        page.wait_for_function(
            "(n) => performance.getEntriesByType('resource').filter((e) => "
            "new URL(e.name).pathname === '/api/admin/model-runs').length > n", arg=gets, timeout=30_000)
        page.wait_for_timeout(300)
        posts = [u for u in _urls(requests, "POST") if "/model-runs" in u]
        assert [urlparse(u).path for u in posts] == ["/api/admin/model-runs/scan"], posts
        status = page.evaluate("() => document.getElementById('admin-status')?.textContent ?? ''")
        rows = page.evaluate("() => [...document.querySelectorAll('.admin-modelruns tbody tr')]"
                             ".map((r) => r.cells[2].textContent.trim())")
        assert rows and all(text.startswith("done") for text in rows), rows
        # Nothing was stale: the scan queued nothing, and says so.
        assert status.startswith("Models rescanned: every paired analysis is current"), status
        browser.close()
    assert problems == [], problems


# ------------------------------------------- landing a Methodology badge link --


def test_a_badge_link_lands_on_its_models_card_with_the_way_back(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        problems = []
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.goto(f"{base}/models?panel=feat-corr&from=lnk-results-features&from_sec=3.5#table_name={BASELINE_TABLE}")
        page.wait_for_function("() => !location.search && !document.getElementById('inspector').hidden", timeout=30_000)
        assert urlparse(page.url).query == ""
        # The cards above load as they come into view; wait for the layout to put this one in view.
        page.wait_for_function("""() => {
          const card = document.querySelector('.main .card[data-panel="feat-corr"]').getBoundingClientRect();
          const main = document.querySelector('.main').getBoundingClientRect();
          return card.top >= main.top - 2 && card.top < main.bottom; }""", timeout=15_000)
        assert page.locator("#inspector-body .inspector-return a").inner_text() \
            == "↩ Continue reading §3.5 in the Methodology"
        browser.close()
    assert problems == [], problems


def test_every_models_drawer_links_to_the_section_explaining_its_panel(models_live_server):
    """A drawer opened by hand links to the article's section on its card, with the view on screen."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        problems = []
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.goto(f"{base}/models#table_name={BASELINE_TABLE}")
        page.wait_for_function("(t) => document.getElementById('experiment-select')?.value === t",
                               arg=BASELINE_TABLE, timeout=30_000)
        page.click('button[data-inspect="perf-bins"]')
        page.wait_for_function("() => !document.getElementById('inspector').hidden", timeout=10_000)
        assert page.locator("#inspector-body .inspector-return").count() == 0
        link = page.locator("#inspector-body .inspector-method a")
        assert link.inner_text() == ("How it is drawn: Methodology §3.6 Model evaluation, the surrogate "
                                     "tree and the 3-D views (E1–E5, C5, C6, C11)")
        # A long title keeps to one line, cut with an ellipsis; the tooltip carries it whole.
        line = page.evaluate("""() => { const a = document.querySelector('#inspector-body .inspector-method a');
          const size = parseFloat(getComputedStyle(a).fontSize);
          return { height: a.getBoundingClientRect().height, size, cut: a.scrollWidth > a.clientWidth }; }""")
        assert line["height"] < 2 * line["size"] and line["cut"], line
        assert link.get_attribute("title").endswith("(E1–E5, C5, C6, C11), in the Methodology, with the view on screen now")
        link.focus()
        href = link.get_attribute("href")
        assert href == f"/methodology#{urlparse(page.url).fragment}&at=lnk-results-models", href
        link.click()
        page.wait_for_url(re.compile(r"/methodology"), timeout=15_000)
        view = {k: v[0] for k, v in parse_qs(urlparse(page.url).fragment).items()}
        assert view.get("table_name") == BASELINE_TABLE and view.get("at") == "lnk-results-models", view
        page.wait_for_function("() => document.activeElement?.id === 'lnk-results-models'", timeout=30_000)
        top = page.evaluate("() => document.getElementById('lnk-results-models').getBoundingClientRect().top "
                            "- document.getElementById('main').getBoundingClientRect().top")
        assert -2 <= top <= 40, top
        browser.close()
    assert problems == [], problems


# -------------------------------------------------------------- the theme --


def test_the_species_legend_and_cubes_follow_a_theme_switch(models_live_server):
    """The 3-D event's species legend (the HTML swatches under the card) and its cubes take the screen
    theme's qualitative palette (scale.js `speciesPalette`: `species` on dark, `species_print` on light),
    on a switch with no request, and back again. The species channel needs the single-shower hits'
    particle columns, which only this module's server holds (test_browser_theme.py covers the rest)."""
    swatches = "() => [...document.querySelectorAll('.voxel-swatch')].map((s) => s.style.getPropertyValue('--swatch'))"
    cubes = ("() => echarts.getInstanceByDom(document.getElementById('plot-vox-event')).getOption().series"
             ".filter((s) => s.type === 'bar3D').flatMap((s) => (s.data || []).slice(0, 50)"
             ".map((d) => d.itemStyle?.color ?? null))")
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], SINGLE_HITS_TABLE)
        assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
        _scroll_to(page, "vox-event")
        page.select_option('.card[data-panel="vox-event"] select[data-voxel-channel]', "species")
        page.wait_for_function("() => document.querySelectorAll('.voxel-swatch').length > 0", timeout=30_000)
        page.wait_for_timeout(600)
        seen = []
        for _ in range(3):
            seen.append((page.evaluate(swatches), page.evaluate(cubes)))
            before = len(requests)
            page.click("#theme-toggle")
            page.wait_for_timeout(1200)
            assert requests[before:] == [], requests[before:]
        browser.close()
    (dark, dark_cubes), (light, light_cubes), (again, again_cubes) = seen
    assert dark and len(dark) == len(light) and dark != light, (dark, light)
    assert dark_cubes and len(dark_cubes) == len(light_cubes) and dark_cubes != light_cubes
    assert (again, again_cubes) == (dark, dark_cubes)
    assert problems == [], problems
