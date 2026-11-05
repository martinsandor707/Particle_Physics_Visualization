"""The Models page (/models), driven in Chromium on every kind it serves.

One server (``models_live_server``) holds the two-shower demonstration, the
synthetic single-shower hits and an event-level aggregate paired with its
XGBoost models, whose analysis has finished before the first page opens. The
page is checked as a reader meets it:

* the page tabs carry the view (the hash) across both pages, and the Physics
  page keeps the Models page's keys;
* the three subpages (Views, Distillations, Performance; models_subpages.js,
  state key ``msub``): the tab bar's roles, click and keyboard, the hash, each
  subpage's scroll position, the sidebar per subpage (Martin's decision 3), a
  deep link switching to its card's subpage first, and the 3-D views keeping
  their canvases, contexts, cameras and slices across switches with no request;
  every helper below reaches a card through its own tab;
* no card asks before it scrolls into view, the 3-D pairs included; Views is
  the cold boot's subpage, and nothing on another subpage asks before its tab;
* the benchmark catalogue's seven cards (the training report, no request ever)
  draw in both themes, open their drawers with the hazard "no interval
  reported", and repaint on a species, task or theme switch with no fetch;
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
  the whole volume's, the paired depth projections bracketing the slice drawn,
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
#: The XGBoost analysis, split across two subpages behind one gate: E1 and E3 on Performance (`xgb`), E4 and E5
#: on Distillations (`xgbDistill`).
XGB_PERF = ["xgb-cv", "xgb-binary"]
XGB_DISTILL = ["xgb-surrogate", "xgb-importance"]
XGB = XGB_PERF + XGB_DISTILL
FEATURES = ["feat-table", "feat-corr", "feat-hist", "feat-hist2d"]
EVENT_PAIR = ["vox-event", "vproj-xy", "vproj-xz", "vproj-yz"]
ENSEMBLE_PAIR = ["vox-ensemble", "eproj-xy", "eproj-yz", "eproj-xz"]
GL_CARDS = ("vox-event", "vox-ensemble")
#: The benchmark catalogue (catalog/select.js CATALOG_CARDS): static documentation from the training report,
#: shown for every experiment. Its Distillations half, then its Performance half.
DISTILL = ["distill-pysr", "distill-triangle", "distill-curves"]
BENCH = ["perf-catalog", "perf-overlap", "perf-momentum-bias", "perf-diagnostics"]
CATALOG = DISTILL + BENCH
#: The catalogue's chart cards; the PySR matrix is a DOM table, with no export.
CATALOG_CHARTS = [c for c in CATALOG if c != "distill-pysr"]
#: The three subpages, in tab order (capabilities.js SUBPAGES); Views is the cold boot's.
SUBPAGES = ("views", "distill", "perf")

#: The cards each kind shows, by subpage, each in page order (capabilities.js SUBPAGE_SECTIONS). The
#: two-shower page opens on the energy network, so its performance cards draw rather than state the
#: segmentation network's notice.
BY_SUBPAGE = {
    BASELINE_TABLE: {"views": EVENT_PAIR + ENSEMBLE_PAIR + FEATURES + ["prim-rate"], "distill": DISTILL,
                     "perf": PERF + RES + BENCH},
    SINGLE_HITS_TABLE: {"views": EVENT_PAIR + ENSEMBLE_PAIR + FEATURES + ["prim-rate"], "distill": DISTILL,
                        "perf": RES + BENCH},
    MODELS_XGB_TABLE: {"views": FEATURES, "distill": DISTILL + XGB_DISTILL, "perf": PERF + RES + XGB_PERF + BENCH},
}
#: Every card a kind shows, across the subpages, in page order (views, distill, perf).
CARDS = {table: [c for msub in SUBPAGES for c in by[msub]] for table, by in BY_SUBPAGE.items()}
#: The subpage of every card on any kind.
SUBPAGE_OF = {c: msub for by in BY_SUBPAGE.values() for msub, ids in by.items() for c in ids}
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
    // A table card: the feature table's <table>, the PySR matrix's role=table grid.
    table: Boolean(host && host.querySelector('table, [role="table"]')),
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


def _open(p, base, table, *, fragment=None, viewport=(1600, 900), init=(), browser=None, path="/models",
          scheme="dark"):
    """The Models page on `table`, with every console error, page error and failed request recorded."""
    browser = browser or p.chromium.launch(args=GL_ARGS)
    page = browser.new_page(
        color_scheme=scheme, viewport={"width": viewport[0], "height": viewport[1]}, accept_downloads=True,
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


def _frames(page, n=2):
    """Let the page run `n` animation frames: what a switch, a scroll or a click schedules for the next frame
    (an IntersectionObserver callback, a scroll event, a repaint) has run. A wait on the frame clock, never a
    guessed delay."""
    page.evaluate("""(n) => new Promise((done) => {
      const step = (k) => (k > 0 ? requestAnimationFrame(() => step(k - 1)) : done());
      step(n);
    })""", n)


#: No card laid out on the subpage on show is still waiting for its response.
_QUIET = """() => [...document.querySelectorAll('.main .card[data-panel]')]
  .filter((c) => !c.hidden && c.offsetParent !== null).every((c) => !c.classList.contains('is-loading'))"""


def _quiet(page, timeout=30_000):
    """Wait until what came into view has asked and answered: a frame for the observers to fire, then no card on
    show loading, then a frame for the repaint. Before an assertion that something was NOT asked, this is the
    settle that lets a wrong request happen first."""
    _frames(page)
    page.wait_for_function(_QUIET, timeout=timeout)
    _frames(page)


def _until(page, check, what, timeout=30_000):
    """Wait until `check()` (a condition the test holds on the Python side, such as the requests recorded so far)
    is true, polling on the frame clock; fail naming `what` when it never is."""
    waited = 0
    while not check():
        if waited >= timeout:
            raise AssertionError(f"timed out after {timeout} ms waiting for {what}")
        _frames(page)
        page.wait_for_timeout(50)
        waited += 66
    return True


#: The subpage on show (`.app[data-msub]`, models_subpages.js) and the one holding a card (its wrapper).
_SUBPAGE_OF_CARD = """(id) => document.querySelector(`.main .card[data-panel="${id}"]`)
  ?.closest('.models-subpage')?.dataset.msub ?? null"""


def _subpage(page):
    return page.evaluate("() => document.querySelector('.app')?.dataset.msub ?? null")


def _show_subpage(page, msub):
    """Click a subpage's tab (unless it is on show); wait for its wrapper to be the one shown, its tab selected and
    the catalogue's bar shown off Views, then a frame for the switch's relayout and repaint."""
    if _subpage(page) != msub:
        page.click(f"#msub-tab-{msub}")
    _wait_subpage(page, msub)


def _wait_subpage(page, msub):
    """Wait, without touching the tabs, until `msub` is the subpage on show (as `_show_subpage` states it)."""
    page.wait_for_function(
        """(m) => document.querySelector('.app')?.dataset.msub === m
          && !document.getElementById(`msub-${m}`).hidden
          && ['views', 'distill', 'perf'].filter((k) => k !== m).every((k) => document.getElementById(`msub-${k}`).hidden)
          && document.getElementById(`msub-tab-${m}`).getAttribute('aria-selected') === 'true'
          && document.getElementById('bench-bar').hidden === (m === 'views')""",
        arg=msub, timeout=10_000)
    _frames(page)


#: The sticky block at the top of `.main` (Martin's decision 6, 2026-11-05: the tab bar, with the catalogue's
#: species bar on Distillations and Performance), and a card against it. `block` is the lowest edge of the tab bar
#: and the catalogue's bar where either is laid out over `.main`'s visible area: a card scrolled into view or
#: deep-linked must start below it. `onTop` says the bar is what a reader sees at its own left edge: nothing
#: scrolled over it.
_STICKY = """(id) => {
  const scroller = document.querySelector('.main');
  const main = scroller.getBoundingClientRect();
  const probe = (el) => {
    if (!el || el.hidden || !el.getClientRects().length) return null;
    const r = el.getBoundingClientRect();
    if (r.height <= 0) return null;
    const y = Math.min(Math.max((r.top + r.bottom) / 2, main.top + 1), main.bottom - 1);
    const hit = document.elementFromPoint(r.left + 3, y);
    return { top: r.top, bottom: r.bottom, height: r.height, onTop: Boolean(hit && el.contains(hit)) };
  };
  const nav = probe(document.getElementById('models-subnav'));
  const bench = probe(document.getElementById('bench-bar'));
  const over = [nav, bench].filter((b) => b && b.bottom > main.top + 1 && b.top < main.bottom - 1);
  const block = Math.max(main.top, ...over.map((b) => b.bottom));
  const el = id ? document.querySelector(`.main .card[data-panel="${id}"]`) : null;
  const card = el ? el.getBoundingClientRect() : null;
  return { main: { top: main.top, bottom: main.bottom }, scrollTop: scroller.scrollTop,
           room: scroller.scrollHeight - scroller.clientHeight, nav, bench, block,
           card: card ? { top: card.top, bottom: card.bottom } : null,
           margin: el ? parseFloat(getComputedStyle(el).scrollMarginTop) || 0 : null };
}"""

#: A card brought to the top of `.main`, as a reader's jump puts it there: `block: 'start'`, so its
#: `scroll-margin-top` (the sticky block's height, models.css) applies.
_SCROLL_START = """(id) => document.querySelector(`.main .card[data-panel="${id}"]`)
  .scrollIntoView({ block: 'start', inline: 'nearest' })"""


def _clear_of_sticky(page, card_id, where=""):
    """Assert a card in view starts below the sticky tab bar and catalogue bar (decision 6); the probe."""
    got = page.evaluate(_STICKY, card_id)
    assert got["card"]["top"] >= got["block"] - 1, (
        f"{where or card_id}: the card's top is {got['block'] - got['card']['top']:.0f} px under the sticky bar", got)
    return got


def _scroll_to(page, card_id):
    """Bring a card to the top of `.main` on its own subpage (its tab clicked first when another is on show), wait
    until it has drawn or says why not, and assert it starts below the sticky bar (decision 6). It is scrolled
    again once drawn, since a card above it may have changed height while it loaded."""
    msub = page.evaluate(_SUBPAGE_OF_CARD, card_id)
    if msub:
        _show_subpage(page, msub)
    page.evaluate(_SCROLL_START, card_id)
    _frames(page)
    state = _settled(page, card_id)
    page.evaluate(_SCROLL_START, card_id)
    _frames(page)
    _clear_of_sticky(page, card_id)
    return state


def _shown_cards(page):
    """The cards the plan shows, on every subpage, in page order: a card is shown when neither it nor anything
    holding it is hidden, its subpage's wrapper aside (a subpage off show hides nothing the plan shows)."""
    return page.evaluate("""() => [...document.querySelectorAll('.main .card[data-panel]')].filter((c) => {
      for (let a = c; a && a !== document.body; a = a.parentElement) {
        if (a.hidden && !a.classList.contains('models-subpage')) return false;
      }
      return true;
    }).map((c) => c.dataset.panel)""")


def _visible_cards(page):
    """The cards laid out now: on the subpage on show, neither hidden nor in a hidden section."""
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


#: Where a chart draws its data items, in viewport pixels: the centre of every element a series painted, at most
#: `cap` spread over every series, for a chart whose marks are too sparse for a grid of pointer positions.
_MARK_POINTS = """([plotId, cap]) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const out = [];
  inst.getModel().eachSeries((series) => {
    if (series.get('silent') || series.get('tooltip')?.show === false) return;
    // Every drawn element of the series (a custom series' marks have no item layout): its painted box's centre.
    inst.getViewOfSeriesModel(series).group.traverse((el) => {
      if (el.isGroup || el.silent || el.ignore || el.invisible || typeof el.getPaintRect !== 'function') return;
      const r = el.getPaintRect();
      if (r && r.width > 0 && r.height > 0) out.push([c.left + r.x + r.width / 2, c.top + r.y + r.height / 2]);
    });
  });
  const step = Math.max(1, Math.ceil(out.length / cap));
  return out.filter((_, i) => i % step === 0)
    .filter(([x, y]) => x > c.left + 1 && x < c.right - 1 && y > c.top + 1 && y < c.bottom - 1);
}"""


def _hover_marks(page, plot_id, cap=30):
    """Hover a chart's own data items; every tooltip that showed, probed (as `_hover_chart` returns them). The
    tooltips have no show delay and no transition (panels/tooltip.js), so a frame after each move is enough."""
    page.locator(f"#{plot_id}").scroll_into_view_if_needed()
    _frames(page)
    page.evaluate(_WATCH_HOVER, plot_id)
    boxes = page.evaluate(_BOXES, plot_id)
    found = []
    for x, y in page.evaluate(_MARK_POINTS, [plot_id, cap]):
        page.mouse.move(x, y)
        _frames(page)
        probe = page.evaluate(_PROBE)
        if probe is not None:
            found.append(((x, y), probe, boxes))
    page.mouse.move(2, 2)
    _frames(page)
    return found


#: The most of a paired projection's plot its plain readout may cover beside the pointer: Page 1's cap
#: (test_browser_physics.py READOUT_SHARE, Martin's tooltip rule). A larger readout leaves the plot
#: as an explanation does (panels/tooltip.js placeTooltip); the 1 : 1 pair's five-line readout is 33%.
PROJECTION_READOUT_SHARE = 0.2
#: A projection's plain bin readout opens on a coordinate in millimetres (test_browser_tooltip.py's rule):
#: ProjectionPanel places it from its own cell handler, not from a series-level `position`.
COORDINATE = re.compile(r"^\S+ = [\u2212-]?[\d.]+ mm(?: \(\S+ = [\u2212-]?[\d.]+ mm\))?(?: \u00b7 .+)?$")


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
    """Open a card's Details drawer (on its own subpage); its title, section headings and text; closed again."""
    msub = page.evaluate(_SUBPAGE_OF_CARD, card_id)
    if msub:
        _show_subpage(page, msub)
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
    """Views is the cold boot's subpage: the cards at its top load at open, and nothing on Distillations or
    Performance asks until its tab is chosen (a card on a hidden subpage never meets `.main`)."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, MODELS_XGB_TABLE)
        page.wait_for_timeout(800)
        assert _subpage(page) == "views"
        assert page.evaluate("() => document.querySelector('.main').scrollTop") == 0
        # The feature explorer stands at the top of Views (no 3-D views on an aggregate) and loads.
        assert _requests_of(requests, "/api/features", view="describe"), _urls(requests)
        # Nothing on the other two subpages has asked.
        for route in ("/api/model-performance", "/api/prediction-density", "/api/resolution-scaling", "/api/xgboost"):
            assert not _requests_of(requests, route), (route, _urls(requests))

        # Distillations: E4 / E5 load with their tab; the Performance cards still ask nothing.
        state = _scroll_to(page, "xgb-importance")
        assert state["canvas"] and state["series"], state
        assert _requests_of(requests, "/api/xgboost", view="importance", task="momentum")
        assert not _requests_of(requests, "/api/xgboost", view="cv"), _urls(requests)
        assert not _requests_of(requests, "/api/model-performance"), _urls(requests)
        # Performance: the cards at its top load once its tab is chosen.
        _show_subpage(page, "perf")
        _until(page, lambda: _requests_of(requests, "/api/model-performance"), "E2's request once Performance shows")
        state = _scroll_to(page, "xgb-cv")
        assert state["canvas"] and state["series"], state
        assert _requests_of(requests, "/api/xgboost", view="cv", task="momentum")
        # Back on Views, a feature card below the fold loads when scrolled to, once.
        state = _scroll_to(page, "feat-hist2d")
        assert state["canvas"] and (state["series"] or state["graphic"]), state
        assert len(_requests_of(requests, "/api/features", view="hist2d")) == 1
        browser.close()

        # On hits, the 3-D pairs head Views: the event's pair loads at open; Performance asks nothing yet.
        browser, page, problems2, requests = _open(p, base, SINGLE_HITS_TABLE)
        page.wait_for_timeout(800)
        assert _subpage(page) == "views"
        assert _requests_of(requests, "/api/projections"), _urls(requests)
        assert not _requests_of(requests, "/api/resolution-scaling"), _urls(requests)
        assert not _requests_of(requests, "/api/primaries"), _urls(requests)
        _scroll_to(page, "vox-ensemble")
        assert _requests_of(requests, "/api/voxels", frame="local")
        assert _requests_of(requests, "/api/projections", coord_system="local", display="native")
        _scroll_to(page, "res-scaling")
        assert len(_requests_of(requests, "/api/resolution-scaling")) == 1
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


# ------------------------------------------------------------ every card --


#: The hazard every catalogue card's Details button carries (Martin's decision 1, 2026-11-05).
NO_INTERVAL = "no interval reported"
#: The Details button of a card: flagged, and its title naming the hazards.
_DETAILS = """(id) => { const b = document.querySelector(`.main button[data-inspect="${id}"]`);
  return b ? { flagged: b.classList.contains('is-flagged'), title: b.title } : null; }"""


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_every_2d_card_renders_without_a_console_error(models_live_server, table):
    """Every card on every subpage draws (or states the server's reason), opens its drawer, and draws U+2212.

    The cold boot lays out Views alone; every card the plan shows is listed across the three subpages, and
    each is reached through its own tab. The catalogue's cards carry the hazard "no interval reported"."""
    base = models_live_server["base"]
    drawers = []
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, table)
        assert _subpage(page) == "views" and "msub" not in _hash(page)
        assert _shown_cards(page) == CARDS[table]
        assert _visible_cards(page) == BY_SUBPAGE[table]["views"]
        for card_id in CARDS[table]:
            state = _scroll_to(page, card_id)
            where = f"{table} {card_id}"
            assert _subpage(page) == SUBPAGE_OF[card_id], where
            if card_id in SHUT.get(table, ()):
                assert state["kind"] == "disabled" and state["message"], (where, state)
                continue
            assert state["message"] is None, f"{where}: {state['message']}"
            assert state["width"] > 200 and state["height"] > 100, (where, state)
            if card_id in ("feat-table", "distill-pysr"):
                assert state["table"], where
            elif card_id in GL_CARDS:
                assert state["canvas"] and "bar3D" in state["seriesTypes"], (where, state)
            else:
                assert state["canvas"] and (state["series"] or state["graphic"]), (where, state)
            title, headings, body = _drawer(page, card_id)
            assert title == state["title"], where
            _assert_sections(headings, where)
            if card_id in CATALOG:
                details = page.evaluate(_DETAILS, card_id)
                assert details["flagged"] and NO_INTERVAL in details["title"], (where, details)
                assert "models_performance.md" in body, where
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
        measured = {}
        # A subpage lays out only its own cards: each is measured while it is on show.
        for msub in SUBPAGES:
            for card_id in BY_SUBPAGE[table][msub]:
                _scroll_to(page, card_id)
            measured[msub] = page.evaluate(_OVERFLOW)
        browser.close()
    for msub, found in measured.items():
        assert found["cards"] == [], (msub, found)
        assert found["main"][0] <= found["main"][1], (msub, found)
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
            if card_id in ("feat-table", "distill-pysr") or card_id in SHUT.get(table, ()):
                continue
            _scroll_to(page, card_id)
            columns, rows = (7, 5) if card_id in GL_CARDS else (9, 6)
            found = _hover_chart(page, f"plot-{card_id}", columns=columns, rows=rows)
            if card_id in CATALOG_CHARTS:
                # Its bars, dots and rules too: a grid of pointer positions can miss every mark of a sparse chart.
                found += _hover_marks(page, f"plot-{card_id}")
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
            if card_id in CATALOG_CHARTS:
                # The catalogue's tooltips explain a documented point estimate: each covers at most the cap of the
                # plot being read, and they say the value is a point estimate with no interval and name its N.
                assert found, f"{table} {card_id}: no tooltip over the catalogue chart"
                covered = []
                for (x, y), probe, boxes in found:
                    plot = boxes["plot"]
                    area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
                    covered.append(_overlap(probe["tip"], plot) / area)
                    assert covered[-1] <= PROJECTION_READOUT_SHARE, (table, card_id, (x, y), probe["text"][:60], covered[-1])
                shares[card_id] = round(max(covered), 3)
                texts = [probe["text"] for _, probe, _ in found]
                assert any("point estimate as reported" in t for t in texts), (table, card_id, texts[:3])
                assert any(re.search(r"\bN not reported\b|\b[Nn] = \d", t) for t in texts), (table, card_id, texts[:3])
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
            if card_id in GL_CARDS or card_id in ("feat-table", "distill-pysr"):
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
        if card_id in ("perf-catalog", "perf-diagnostics"):
            # The plot alone: none of the screen's tables or blocks under the plot frame.
            assert not [t for t in texts if "Secondary metrics" in t or "Validation N" in t or "Throughput on one" in t
                        or "Architecture and parameters" in t or "own caveats" in t], (card_id, texts)
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
    // One tbody per series, headed by its name across its fit rows (panels/resolution_scaling.js renderTable).
    rows: [...host.querySelectorAll('tbody th[scope="rowgroup"]')].map((th) => th.textContent),
    fits: [...host.querySelectorAll('tbody th[scope="row"]')].map((th) => th.textContent),
    overflow: host.scrollWidth - host.clientWidth,
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
        assert fit["rows"] and len(fit["fits"]) == 3 * len(fit["rows"]), fit
        # Its text columns wrap, so at 1600 px the table keeps to its card (it ran 1721 px in 1212 kept on one line).
        assert fit["overflow"] <= 1, fit

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
        # The card opens on the selection; one event, and a change of its channel, redraw on the same chart:
        # still two contexts. (The selection draws energy only here: species belong to one event.)
        page.click('.card[data-panel="vox-event"] [data-voxel-scope="event"]')
        _settled(page, "vox-event")
        page.wait_for_timeout(800)
        assert len(page.evaluate(_LIVE_GL)) <= 2
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

        # In the Absolute frame the card opens on the selection, whose showers are summed; Both is one event's.
        browser, page, problems2, requests = _open(p, base, BASELINE_TABLE, fragment="&model=energy&frame=lab&voxel_scope=event")
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

#: A projection's slice bracket (projection.js addDepthSlab): the depths of its two faces, their count and whether
#: anything was laid over the raster as a wash (never), or null without a bracket.
_DEPTH_BAND = """(id) => {
  const series = echarts.getInstanceByDom(document.getElementById(`plot-${id}`)).getOption().series || [];
  const faces = series.filter((s) => (s.name || '').startsWith('Depth slice drawn in 3-D — '));
  if (!faces.length) return null;
  const at = faces.map((s) => s.data[0][0]);
  const wash = series.some((s) => s.name === 'Depth slice drawn in 3-D' || (s.name || '').includes('wash'));
  return { lo: Math.min(...at), hi: Math.max(...at), faces: faces.length, wash };
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


#: The 3-D event card's scope buttons and title, and whether its event picker shows.
_SCOPE = """() => {
  const card = document.querySelector('.main .card[data-panel="vox-event"]');
  const button = (v) => card.querySelector(`[data-voxel-scope="${v}"]`);
  const visible = (el) => Boolean(el) && !el.hidden && el.getClientRects().length > 0;
  return {
    title: card.querySelector('.title')?.textContent ?? null,
    selection: { pressed: button('selection').getAttribute('aria-pressed'), disabled: button('selection').disabled,
      title: button('selection').title },
    event: { pressed: button('event').getAttribute('aria-pressed') },
    picker: visible(card.querySelector('[data-voxel-event]')),
    showersShut: [...card.querySelectorAll('[data-voxel-shower]')].every((b) => b.disabled),
    projection: document.querySelector('.main .card[data-panel="vproj-xz"] .title')?.textContent ?? null,
  };
}"""


def test_the_absolute_3d_card_opens_on_the_selection_and_one_event_is_a_click_away(models_live_server):
    """Martin's directive (2026-10-31): in the Absolute frame the 3-D event card draws the whole selection by
    default - its cells from /api/selection-cells, its projections the Physics page's - with no pick and no event
    request. "One event" loads the densest event; "Selection" returns with no request. An older link that names an
    event opens it, and outside the Absolute frame the Selection button is shut with its reason."""
    base = models_live_server["base"]
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE)
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        for card in ("vproj-xy", "vproj-xz", "vproj-yz"):
            _scroll_to(page, card)
        state = page.evaluate(_SCOPE)
        assert state["title"] == "The Selection in 3-D — Detector Cells", state
        assert state["selection"]["pressed"] == "true" and state["event"]["pressed"] == "false", state
        assert not state["picker"] and state["showersShut"], state
        assert not (state["projection"] or "").startswith("Event "), state
        assert _requests_of(requests, "/api/selection-cells"), _urls(requests)
        assert _requests_of(requests, "/api/projections", coord_system="lab", frame="lab", channel="density")
        assert not _requests_of(requests, "/api/event/pick") and not _requests_of(requests, "/api/event"), _urls(requests)
        assert "voxel_scope" not in _hash(page), "the cold-boot scope is not written to the link"

        # One event: the densest, picked and drawn; the link says so.
        page.click('.main .card[data-panel="vox-event"] [data-voxel-scope="event"]')
        page.wait_for_function("() => document.querySelector('.main .card[data-panel=\"vox-event\"] .title')"
                               "?.textContent === 'One Event in 3-D — Detector Cells'", timeout=30_000)
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        one = page.evaluate(_SCOPE)
        assert one["event"]["pressed"] == "true" and one["picker"] and not one["showersShut"], one
        assert _requests_of(requests, "/api/event/pick") and _requests_of(requests, "/api/event", format="voxels")
        assert _hash(page).get("voxel_scope") == "event"

        # Back to the selection: drawn from the responses in hand, no request.
        before = len(_requests_of(requests, "/api/selection-cells"))
        page.click('.main .card[data-panel="vox-event"] [data-voxel-scope="selection"]')
        page.wait_for_function("() => document.querySelector('.main .card[data-panel=\"vox-event\"] .title')"
                               "?.textContent === 'The Selection in 3-D — Detector Cells'", timeout=30_000)
        assert len(_requests_of(requests, "/api/selection-cells")) == before
        assert "voxel_scope" not in _hash(page) and "voxel_event" not in _hash(page)
        browser.close()
        assert problems == [], problems

        # An older link names an event and no scope: it opens that event.
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, fragment="&voxel_event=0")
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        assert page.evaluate(_SCOPE)["title"] == "One Event in 3-D — Detector Cells"
        assert not _requests_of(requests, "/api/selection-cells")
        browser.close()
        assert problems == [], problems

        # Outside the Absolute frame: one event, the Selection button shut with its reason.
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, fragment="&frame=local")
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        local = page.evaluate(_SCOPE)
        assert local["selection"]["disabled"] and local["selection"]["title"].startswith("The selection is drawn on the detector cells")
        assert local["event"]["pressed"] == "true" and not _requests_of(requests, "/api/selection-cells")
        browser.close()
        assert problems == [], problems


def test_the_3d_slices_step_with_no_request_and_keep_the_turned_and_zoomed_camera(models_live_server):
    """The slice mode (plan §3.4-§3.6) on the two-shower event in the Absolute frame (37 layers) and on the
    co-registered cloud, in Chromium with SwiftShader WebGL.

    The row shows once the cubes are drawn, at K = 1 (the whole volume, no band). After the reader has turned
    and wheel-zoomed the view: K = 6 reads "Slice 1 of 6", Next twice "Slice 3 of 6", Previous and the
    scrubber step, each button is disabled at its end, and a K above the volume's depth L is drawn as L, the
    count's max. The cubes drawn change with the slice and the six slices' cubes add up to the whole
    volume's. The paired depth projections bracket the slice drawn (moving with Next), the XY projection never,
    and the bracket prints in the depth projection's export only while a slice is shown. Across every step the
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
                assert "layers 1–" in row["readout"] and " · Z " in row["readout"] and "(z " in row["readout"], row["readout"]
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
            assert all(b and b["faces"] == 2 and b["hi"] > b["lo"] and not b["wash"] for b in views[1]["bands"]), \
                (where, views[1])

            # Next twice: slice 3; the bracket moves downstream.
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
            # The six brackets tile the depth the slices cover, entrance first.
            for column in range(2):
                bands = [views[k]["bands"][column] for k in range(1, 7)]
                assert all(a["hi"] == pytest.approx(b["lo"]) for a, b in zip(bands, bands[1:])), (where, bands)
            # A keyboard reader whose Enter lands on the last slice keeps their place: Next shuts, focus moves to
            # the scrubber rather than falling back to the top of the page.
            _scrub_slice(page, card_id, 5)
            page.locator(f'.main .card[data-panel="{card_id}"] [data-voxel-slice-step="next"]').focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(250)
            assert page.evaluate(_SLICE_ROW, card_id)["k"] == "6", where
            assert page.evaluate("() => document.activeElement?.matches('[data-voxel-slice]') === true"), where

            if card_id == "vox-event":
                # The bracket prints with the depth projection while a slice is shown (its two faces).
                page.locator(f'.main .card[data-panel="{depth[0]}"]').scroll_into_view_if_needed()
                _download_svg(page, depth[0])
                assert page.evaluate("() => window.__exportSeries.at(-1)") == unsliced_export + 2
                page.locator(f'.main .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
                page.wait_for_timeout(300)

            # A K above the volume's depth is drawn as L, the count's own bound.
            _set_slices(page, card_id, depth_bins + 7)
            row = page.evaluate(_SLICE_ROW, card_id)
            assert (row["K"], row["max"], row["kMax"]) == (str(depth_bins),) * 3, (where, row)
            assert re.match(rf"^Slice \d+ of {depth_bins} — ", row["readout"]), (where, row)
            # And K = 1 is the whole volume again, the brackets gone.
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
            _show_subpage(page, SUBPAGE_OF[card_id])
            page.locator(f'.card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            state = _settled(page, card_id)
            assert state["message"] is None and state["series"], (card_id, state)
        for view in ("cv", "surrogate", "importance"):
            assert _xgb_view(requests, view, "angle"), view
        # One recorded angle split is not reproduced: every angle card flags it, on either subpage.
        flagged = page.evaluate("() => [...document.querySelectorAll('#xgb-grid button[data-inspect].is-flagged, "
                                "#xgb-distill-grid button[data-inspect].is-flagged')]"
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
        # E2 is on Performance: its tab first (the cold boot shows Views).
        _show_subpage(page, "perf")
        page.click('button[data-inspect="perf-bins"]')
        page.wait_for_function("() => !document.getElementById('inspector').hidden", timeout=10_000)
        assert page.locator("#inspector-body .inspector-return").count() == 0
        link = page.locator("#inspector-body .inspector-method a")
        assert link.inner_text() == ("How it is drawn: Methodology §3.6 Model evaluation, resolution "
                                     "scaling, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)")
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


# ------------------------------------------------------------- the subpages --

#: The tab bar and the three wrappers as a reader and a screen reader meet them (models_subpages.js).
_TABS = """() => {
  const nav = document.getElementById('models-subnav');
  const tabs = [...nav.querySelectorAll('[role="tab"]')];
  return {
    role: nav.getAttribute('role'), label: nav.getAttribute('aria-label'),
    tabs: tabs.map((t) => ({ id: t.id, msub: t.dataset.msub, text: t.textContent.trim(), controls: t.getAttribute('aria-controls'),
      selected: t.getAttribute('aria-selected'), tabindex: t.getAttribute('tabindex'), title: t.title })),
    panels: ['views', 'distill', 'perf'].map((m) => { const w = document.getElementById(`msub-${m}`);
      return { msub: m, role: w.getAttribute('role'), labelledby: w.getAttribute('aria-labelledby'), hidden: w.hidden }; }),
    app: document.querySelector('.app')?.dataset.msub ?? null,
    focus: document.activeElement?.id ?? null,
    scroll: document.querySelector('.main').scrollTop,
  };
}"""

#: The sidebar per subpage (Martin's decision 3): the Longitudinal Channels hidden off Views by CSS alone (their
#: own `hidden` is the control's), the Colour Map by `hidden`; the catalogue's bar shown off Views.
_SIDEBAR = """() => {
  const shown = (id) => { const el = document.getElementById(id); return Boolean(el) && !el.hidden && getComputedStyle(el).display !== 'none'; };
  return {
    lgroups: shown('group-lgroups'), lgroupsHidden: document.getElementById('group-lgroups')?.hidden ?? null,
    colormap: shown('group-m-colormap'), model: shown('group-m-model'), frame: shown('group-m-frame'),
    bench: shown('bench-bar'),
  };
}"""


def _tab_state(page, msub):
    """Assert the tab bar shows `msub` alone, with the roving tabindex; return the probe."""
    got = page.evaluate(_TABS)
    assert got["app"] == msub, got
    for tab in got["tabs"]:
        on = tab["msub"] == msub
        assert (tab["selected"], tab["tabindex"]) == (("true", "0") if on else ("false", "-1")), (msub, tab)
    for panel in got["panels"]:
        assert panel["hidden"] is (panel["msub"] != msub), (msub, panel)
    assert _hash(page).get("msub") == (None if msub == "views" else msub), (msub, page.url)
    return got


#: Scroll `.main` to `top` and resolve after its `scroll` event has been handled (a frame later): the subpage
#: router may remember the position on that event. Resolves at once when `.main` is already there.
_SCROLL_MAIN = """(top) => new Promise((done) => {
  const main = document.querySelector('.main');
  const settle = () => requestAnimationFrame(() => requestAnimationFrame(() => done(main.scrollTop)));
  if (Math.abs(main.scrollTop - Math.min(top, main.scrollHeight - main.clientHeight)) < 1) { settle(); return; }
  main.addEventListener('scroll', settle, { once: true });
  main.scrollTop = top;
})"""


def _scroll_main(page, top):
    """Scroll `.main` to `top`; its scrollTop once the scroll has been handled."""
    return page.evaluate(_SCROLL_MAIN, top)


def test_the_subpage_tabs_switch_by_click_and_keyboard_and_keep_their_scroll(models_live_server):
    """The tab bar (WAI-ARIA tabs, automatic activation): one tablist, three tabs each controlling its wrapper;
    a click or Left / Right (wrapping) / Home / End selects, moves the focus and the roving tabindex, writes
    `msub` (Views, the default, never), and each subpage's scroll position comes back with it. A link's
    `msub` opens its subpage."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE)
        got = _tab_state(page, "views")
        assert (got["role"], got["label"]) == ("tablist", "Models page views"), got
        assert [(t["id"], t["msub"], t["text"], t["controls"]) for t in got["tabs"]] == [
            ("msub-tab-views", "views", "Views", "msub-views"),
            ("msub-tab-distill", "distill", "Distillations", "msub-distill"),
            ("msub-tab-perf", "perf", "Performance", "msub-perf")], got["tabs"]
        assert all(t["title"] for t in got["tabs"]), got["tabs"]
        assert [(w["role"], w["labelledby"]) for w in got["panels"]] == [
            ("tabpanel", f"msub-tab-{m}") for m in SUBPAGES], got["panels"]

        # A click.
        page.click("#msub-tab-distill")
        _wait_subpage(page, "distill")
        _tab_state(page, "distill")
        assert _visible_cards(page) == BY_SUBPAGE[BASELINE_TABLE]["distill"]
        # The keyboard, from the focused tab: Right, Right (wraps), Left (wraps), End, Home.
        page.focus("#msub-tab-distill")
        for key, msub in (("ArrowRight", "perf"), ("ArrowRight", "views"), ("ArrowLeft", "perf"), ("Home", "views"),
                          ("End", "perf")):
            page.keyboard.press(key)
            page.wait_for_function("(m) => document.activeElement?.id === `msub-tab-${m}`", arg=msub, timeout=10_000)
            _wait_subpage(page, msub)
            got = _tab_state(page, msub)
            assert got["focus"] == f"msub-tab-{msub}", (key, got)
        # Tab leaves the tablist: the one tab in the order is the selected one.
        page.keyboard.press("Tab")
        assert not page.evaluate("() => document.activeElement?.matches('[role=\"tab\"]')")

        # Scroll memory: each subpage comes back where it was left; the first visit opens at the top. The tabs
        # are clicked in place (a DOM click): a pointer click would first scroll the tab bar, at the top of
        # `.main`, into view, and so record the top.
        def switch(msub):
            page.evaluate("(m) => document.getElementById(`msub-tab-${m}`).click()", msub)
            _wait_subpage(page, msub)
            return page.evaluate("() => document.querySelector('.main').scrollTop")

        switch("views")
        views_at = _scroll_main(page, 700)
        assert views_at > 300, views_at
        assert switch("perf") == 0
        perf_at = _scroll_main(page, 400)
        assert perf_at > 100, perf_at
        assert switch("distill") == 0
        assert abs(switch("perf") - perf_at) <= 1
        # Views has no catalogue bar above its sections: it must come back exactly where it was left too.
        assert abs(switch("views") - views_at) <= 1, "Views came back shifted (by the catalogue bar's height?)"
        # The scroll position is not view state.
        assert set(_hash(page)) & {"scroll", "msub_scroll"} == set()
        browser.close()

        # A link's msub opens that subpage, and the Physics page's tab carries it there and back.
        browser, page, problems2, _ = _open(p, base, BASELINE_TABLE, fragment="&model=energy&msub=perf")
        _tab_state(page, "perf")
        assert _visible_cards(page) == BY_SUBPAGE[BASELINE_TABLE]["perf"]
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, MODELS_XGB_TABLE])
def test_the_sidebar_follows_the_subpage(models_live_server, table):
    """Martin's decision 3: the Longitudinal Channels on Views only (hidden by CSS, their own `hidden` untouched);
    the Colour Map on Views, on Distillations while the XGBoost surrogate shows, on Performance while the
    prediction density shows; the network and frame on every subpage; the catalogue's bar off Views."""
    colour = {BASELINE_TABLE: {"views": True, "distill": False, "perf": True},
              SINGLE_HITS_TABLE: {"views": True, "distill": False, "perf": False},
              MODELS_XGB_TABLE: {"views": True, "distill": True, "perf": True}}[table]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], table)
        at_boot = page.evaluate(_SIDEBAR)
        lgroups_views = at_boot["lgroups"]
        for msub in ("distill", "perf", "views", "perf", "distill"):
            _show_subpage(page, msub)
            got = page.evaluate(_SIDEBAR)
            where = (table, msub, got)
            assert got["colormap"] is colour[msub], where
            # The network and the frame stay as they are on Views, on every subpage.
            assert got["model"] and (got["model"], got["frame"]) == (at_boot["model"], at_boot["frame"]), where
            assert got["bench"] is (msub != "views"), where
            if msub == "views":
                assert got["lgroups"] is lgroups_views, where
            else:
                assert got["lgroups"] is False, where
            # Hidden by the page's CSS, never through the control's own flag.
            assert got["lgroupsHidden"] is (not lgroups_views), where
        browser.close()
    # The two kinds with hits offer the Longitudinal Channels on Views; the aggregate offers none.
    assert lgroups_views is (table != MODELS_XGB_TABLE), (table, lgroups_views)
    assert problems == [], problems


#: Every canvas inside the 3-D cards' plots, tagged once so a later probe can tell the same node from a new one.
_TAG_GL_CANVASES = """() => {
  window.__glTag = window.__glTag ?? 0;
  return ['vox-event', 'vox-ensemble'].map((id) => [...document.querySelectorAll(`#plot-${id} canvas`)].map((c) => {
    if (!c.__tag) c.__tag = `${id}-${++window.__glTag}`;
    return { tag: c.__tag, connected: c.isConnected };
  }));
}"""

#: Context losses, recorded from the first script on (the event does not bubble: listen in the capture phase).
_COUNT_LOST = """(() => {
  window.__lost = 0;
  window.addEventListener('webglcontextlost', () => { window.__lost += 1; }, true);
})();"""


def test_the_3d_views_keep_their_contexts_cameras_and_slices_across_subpage_switches(models_live_server):
    """A switch only hides and shows (models_subpages.js): with the event cut into slices and both 3-D views
    turned, leaving Views for Distillations and Performance and coming back keeps the same canvas nodes, the
    same two live WebGL contexts, no context loss, each camera's angles and zoom, the slice count, the slice
    shown and its cubes, and asks the service nothing."""
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, models_live_server["base"], BASELINE_TABLE, fragment="&model=energy&frame=lab",
            init=(_COUNT_GL, _COUNT_LOST))
        # The other subpages once, so what they hold in view has loaded before the measured round trip.
        for msub in ("perf", "distill", "views"):
            _show_subpage(page, msub)
            _quiet(page)
        for card_id, (xy, depth) in SLICE_PAIRS.items():
            for cell in (card_id, xy, *depth):
                state = _scroll_to(page, cell)
                assert state["message"] is None, (cell, state)
            page.wait_for_function(theme._GL_DRAWN, arg=card_id, timeout=30_000)
        _quiet(page)
        # The reader turns and zooms the event and cuts it into six slices, at the third; the cloud is turned
        # through echarts-gl's camera action.
        _turn_and_zoom(page, "vox-event")
        _set_slices(page, "vox-event", 6)
        _step_slice(page, "vox-event", "next")
        _step_slice(page, "vox-event", "next")
        page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-vox-ensemble'))"
                      ".dispatchAction({ type: 'grid3DChangeCamera', alpha: 10, beta: 70 })")
        page.wait_for_function(f"() => {{ const m = ({theme._CAMERA})('vox-ensemble').model; "
                               "return m.alpha === 10 && m.beta === 70; }", timeout=10_000)
        _frames(page)

        def view():
            return {
                "canvases": page.evaluate(_TAG_GL_CANVASES),
                "live": sorted(page.evaluate(_LIVE_GL)),
                "lost": page.evaluate("() => window.__lost"),
                "cameras": {c: page.evaluate(theme._CAMERA, c)["control"] for c in GL_CARDS},
                "models": {c: {k: page.evaluate(theme._CAMERA, c)["model"][k] for k in ("alpha", "beta")} for c in GL_CARDS},
                "row": page.evaluate(_SLICE_ROW, "vox-event"),
                "cubes": {c: page.evaluate(_CUBES, c) for c in GL_CARDS},
                "bands": [page.evaluate(_DEPTH_BAND, c) for c in SLICE_PAIRS["vox-event"][1]],
            }

        before = view()
        assert before["row"]["readout"].startswith("Slice 3 of 6 — ") and before["row"]["K"] == "6", before["row"]
        assert before["live"] == ["vox-ensemble", "vox-event"] and before["lost"] == 0, before
        assert all(len(c) >= 1 for c in before["canvases"]), before["canvases"]
        assert before["models"]["vox-ensemble"] == {"alpha": 10, "beta": 70}, before["models"]
        asked = len(requests)

        for msub in ("distill", "perf", "views", "perf", "views"):
            _show_subpage(page, msub)
            _quiet(page)
            if msub != "views":
                # Off show, the 3-D cards stay in the page with their contexts.
                assert sorted(page.evaluate(_LIVE_GL)) == ["vox-ensemble", "vox-event"], msub
        page.locator('.main .card[data-panel="vox-event"]').scroll_into_view_if_needed()
        _quiet(page)
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        after = view()
        assert after == before, (before, after)
        assert requests[asked:] == [], f"a subpage switch asked the service: {requests[asked:]}"
        browser.close()
    assert problems == [], problems


def _catalog_texts(page):
    """Every text the catalogue cards on show put on the page: the cards' DOM text (tables, blocks, MathML's
    fallbacks included) and every text their canvases drew."""
    return page.evaluate("""() => [...document.querySelectorAll('.main .card[data-panel]')]
      .filter((c) => c.offsetParent !== null && /^(distill|perf)-(pysr|triangle|curves|catalog|overlap|momentum-bias|diagnostics)$/.test(c.dataset.panel))
      .map((c) => c.innerText)""")


#: Every request of any kind, as the page makes it (static modules included).
def _all_requests(page):
    seen = []
    page.on("request", lambda r: seen.append((r.method, r.url)))
    return seen


#: The option JSON of a chart, for a theme or a species switch to change.
_OPTION = """(id) => { const inst = echarts.getInstanceByDom(document.getElementById(`plot-${id}`));
  return inst ? JSON.stringify(inst.getOption(), (k, v) => (typeof v === 'function' ? undefined : v)) : null; }"""


def _wait_pressed(page, selector, timeout=10_000):
    """Wait until a segmented button is the pressed one (what its click handler sets)."""
    page.wait_for_function("(sel) => document.querySelector(sel)?.getAttribute('aria-pressed') === 'true'",
                           arg=selector, timeout=timeout)
    _frames(page)


def _wait_options(page, cards, ok, *, any_of=False, timeout=10_000):
    """Wait, on the frame clock, until `ok(option_json, card)` holds for every card (or, `any_of`, for one); the
    cards for which it held when the wait ended. A repaint compared against the option before it is waited for,
    never assumed done after a fixed delay."""
    waited, held = 0, []
    while True:
        held = [c for c in cards if ok(page.evaluate(_OPTION, c) or "", c)]
        if (held if any_of else len(held) == len(cards)) or waited >= timeout:
            return held
        _frames(page)
        page.wait_for_timeout(50)
        waited += 66


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_catalogue_draws_opens_its_drawers_and_switches_species_task_and_theme_without_a_request(
        models_live_server, scheme):
    """The seven catalogue cards (training report, catalog/select.js) in either theme: each draws (the PySR matrix
    as MathML), opens its drawer with the four standard sections and the hazard 'no interval reported', and sets
    every negative number with U+2212. A two-shower file names no species, so the bar opens on Compare all and
    says so. Every species and every task button repaints the catalogue from the module in hand: no `/api/`
    request and no fetch at all once the catalogue has loaded; the species is written to the link and Compare
    all, the experiment's own choice, leaves it. A theme switch repaints every catalogue chart with no request."""
    base = models_live_server["base"]
    texts, drawers = [], []
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, scheme=scheme)
        assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
        everything = _all_requests(page)
        for card_id in CATALOG:
            state = _scroll_to(page, card_id)
            where = f"{scheme} {card_id}"
            assert state["message"] is None, (where, state)
            if card_id == "distill-pysr":
                assert state["table"] and state["exportButtons"] == 0, (where, state)
                pysr = page.evaluate("""() => { const c = document.querySelector('.main .card[data-panel="distill-pysr"]');
                  return { cells: c.querySelectorAll('.pysr-cell[role="cell"]').length, math: c.querySelectorAll('.pysr-formula math').length,
                           entries: c.querySelectorAll('.pysr-entry[data-tier]').length, copy: c.querySelectorAll('button.pysr-copy').length,
                           tiers: [...new Set([...c.querySelectorAll('.pysr-entry[data-tier]')].map((e) => e.dataset.tier))].sort() }; }""")
                assert pysr["cells"] == 9 and pysr["entries"] == 9 * 4 and pysr["math"] > 0 and pysr["copy"] > 0, (where, pysr)
                assert set(pysr["tiers"]) <= {"law", "unverified", "partial", "not-law"} and len(pysr["tiers"]) >= 3, pysr
            else:
                assert state["canvas"] and (state["series"] or state["graphic"]) and state["exportButtons"] == 1, (where, state)
            title, headings, body = _drawer(page, card_id)
            assert title == state["title"], where
            _assert_sections(headings, where)
            assert [h for h in headings if h in ("Selection", "What is drawn", "Disclosures", "Marks and legend")] == [
                "Selection", "What is drawn", "Disclosures", "Marks and legend"], (where, headings)
            details = page.evaluate(_DETAILS, card_id)
            assert details["flagged"] and NO_INTERVAL in details["title"], (where, details)
            drawers.append(body)
        # A two-shower file names no species: Compare all, said on the bar.
        _show_subpage(page, "distill")
        bar = page.evaluate("""() => ({ species: [...document.querySelectorAll('#bench-bar [data-bench-species]')].map((b) => [b.dataset.benchSpecies, b.getAttribute('aria-pressed')]),
          task: [...document.querySelectorAll('#bench-bar [data-bench-task]')].map((b) => [b.dataset.benchTask, b.getAttribute('aria-pressed')]),
          caption: document.getElementById('bench-caption').textContent })""")
        assert [v for v, on in bar["species"] if on == "true"] == ["all"], bar
        assert [v for v, on in bar["task"] if on == "true"] == ["energy"], bar
        assert "does not name its species" in bar["caption"] and "models_performance.md" in bar["caption"], bar

        # Species and task switches on Distillations, species switches on Performance: nothing is fetched. Every
        # other card of Performance is brought into view once first, so scrolling past it later asks nothing.
        for card_id in BY_SUBPAGE[BASELINE_TABLE]["perf"]:
            _scroll_to(page, card_id)
        _quiet(page)
        for msub in ("distill", "perf"):
            _show_subpage(page, msub)
            ids = DISTILL if msub == "distill" else BENCH
            fetched, api = len(everything), len(requests)
            charts = [c for c in ids if c != "distill-pysr"]
            seen = {c: page.evaluate(_OPTION, c) for c in charts}
            for species in ("proton", "muon", "electron", "pion", "all"):
                page.click(f'#bench-bar button[data-bench-species="{species}"]')
                _wait_pressed(page, f'#bench-bar button[data-bench-species="{species}"]')
                assert _hash(page).get("bench_species") == (None if species == "all" else species), (species, page.url)
                for c in ids:
                    # A card out of view repaints when it comes into view.
                    state = _scroll_to(page, c)
                    assert state["message"] is None, (msub, species, c, state)
                if species == "muon":
                    # A species switch repaints the catalogue: some chart's option leaves the Compare-all one.
                    changed = _wait_options(page, charts, lambda option, c: option != seen[c], any_of=True)
                    assert changed, (msub, "a species switch repaints the catalogue")
                texts += _catalog_texts(page)
                texts += page.evaluate("() => window.__drawnText.slice(-400)")
            if msub == "distill":
                for task in ("segmentation", "angle", "energy"):
                    page.click(f'#bench-bar button[data-bench-task="{task}"]')
                    _wait_pressed(page, f'#bench-bar button[data-bench-task="{task}"]')
                    # The shared `model` key; segmentation is its default, so the link leaves it out.
                    assert _hash(page).get("model") == (None if task == "segmentation" else task), (task, page.url)
                    for c in ids:
                        assert _scroll_to(page, c)["message"] is None, (task, c)
                    texts += _catalog_texts(page)
            assert requests[api:] == [], f"{msub}: a catalogue switch asked the service: {requests[api:]}"
            assert everything[fetched:] == [], f"{msub}: a catalogue switch fetched {everything[fetched:]}"

        # The theme: every catalogue chart repainted in the new ink, with no request. A card on the subpage off
        # show repaints when its tab brings it back.
        other = "light" if scheme == "dark" else "dark"
        theme = _theme_module()
        before = {c: page.evaluate(_OPTION, c) for c in CATALOG_CHARTS}
        api = len(requests)
        page.click("#theme-toggle")
        page.wait_for_function("(t) => document.documentElement.dataset.theme === t", arg=other, timeout=10_000)
        stale = []

        def repainted(option, card_id):
            # The screen ink of the new theme (its text or muted token), none of the old one's.
            ink = {t: [theme.MUTED[t] in option, theme.TEXT[t] in option] for t in (scheme, other)}
            return option != before[card_id] and any(ink[other]) and not any(ink[scheme])

        for card_id in CATALOG_CHARTS:
            _scroll_to(page, card_id)
            if not _wait_options(page, [card_id], repainted):
                option = page.evaluate(_OPTION, card_id)
                stale.append((card_id, {t: [theme.MUTED[t] in option, theme.TEXT[t] in option] for t in (scheme, other)}))
        assert stale == [], f"still in the {scheme} ink after the switch to {other}: {stale}"
        texts += _catalog_texts(page)
        assert requests[api:] == [], f"a theme switch asked the service: {requests[api:]}"
        browser.close()
    assert problems == [], problems
    assert _hyphen_negatives(texts) == [], "catalogue text with an ASCII hyphen-minus"
    assert _hyphen_negatives(drawers) == [], "catalogue drawer text with an ASCII hyphen-minus"


#: Where a deep link landed: the subpage, the drawer and its card, whether that card is in view.
_LANDED = """(id) => {
  const card = document.querySelector(`.main .card[data-panel="${id}"]`).getBoundingClientRect();
  const main = document.querySelector('.main').getBoundingClientRect();
  return { msub: document.querySelector('.app')?.dataset.msub ?? null,
           open: !document.getElementById('inspector').hidden,
           title: document.getElementById('inspector-title').textContent,
           cardTitle: document.querySelector(`.main .card[data-panel="${id}"] .title`)?.textContent ?? null,
           inView: card.top >= main.top - 2 && card.top < main.bottom,
           back: document.querySelector('#inspector-body .inspector-return a')?.textContent ?? null };
}"""


@pytest.mark.parametrize("panel,msub,hash_msub", [
    ("perf-catalog", "perf", None), ("distill-pysr", "distill", None), ("feat-corr", "views", "perf"),
], ids=["perf-catalog", "distill-pysr", "feat-corr-over-msub-perf"])
def test_a_deep_link_opens_its_cards_subpage_first(models_live_server, panel, msub, hash_msub):
    """A badge link (`?panel=…&from=…&from_sec=…`) switches to its card's subpage before anything loads, even
    over a link whose own `msub` names another; the card comes into view with its drawer open and the way back,
    and nothing on another subpage asks the service."""
    base = models_live_server["base"]
    fragment = f"#table_name={BASELINE_TABLE}" + (f"&msub={hash_msub}" if hash_msub else "")
    with models_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        problems, requests = [], []
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("request", lambda r: requests.append((r.method, r.url)) if "/api/" in r.url else None)
        page.goto(f"{base}/models?panel={panel}&from=lnk-results-models&from_sec=3.6{fragment}")
        page.wait_for_function("() => !location.search && !document.getElementById('inspector').hidden", timeout=30_000)
        page.wait_for_function(f"""() => {{ const s = ({_LANDED})({panel!r}); return s.inView && s.title === s.cardTitle; }}""",
                               timeout=30_000)
        got = page.evaluate(_LANDED, panel)
        assert got["msub"] == msub and got["open"] and got["title"] == got["cardTitle"], got
        # Its top is not under the sticky tab bar (decision 6: the cards' scroll margin).
        _clear_of_sticky(page, panel, f"deep link to {panel}")
        assert got["back"] == "↩ Continue reading §3.6 in the Methodology", got
        assert _hash(page).get("msub") == (None if msub == "views" else msub), page.url
        _quiet(page)
        # No request for a card the link did not open a subpage for.
        others = {"views": ("/api/model-performance", "/api/resolution-scaling", "/api/xgboost"),
                  "distill": ("/api/features", "/api/projections", "/api/selection-cells", "/api/model-performance",
                              "/api/resolution-scaling"),
                  "perf": ("/api/features", "/api/projections", "/api/selection-cells", "/api/primaries")}[msub]
        for route in others:
            assert not _requests_of(requests, route), (panel, route, _urls(requests))
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
        # Species belong to one event: the card's selection scope draws energy alone.
        browser, page, problems, requests = _open(p, models_live_server["base"], SINGLE_HITS_TABLE,
                                                  fragment=FRAGMENT.get(SINGLE_HITS_TABLE, "") + "&voxel_scope=event")
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


# ------------------------------------------- the sticky tab bar (decision 6) --


#: Where the sticky block must stand once `.main` has scrolled: the tab bar at the top of `.main`'s visible area
#: (within a few px, for the scroller's own padding), the catalogue's bar below it on Distillations and
#: Performance, both entirely in view and nothing drawn over them.
STICKY_SLACK = 24


def _assert_pinned(got, msub, where):
    nav, bench, main = got["nav"], got["bench"], got["main"]
    assert nav is not None, (where, "no tab bar laid out", got)
    assert main["top"] - 1 <= nav["top"] <= main["top"] + STICKY_SLACK, (where, "the tab bar scrolled away", got)
    assert nav["bottom"] <= main["bottom"] and nav["onTop"], (where, "the tab bar is covered", got)
    if msub == "views":
        assert bench is None, (where, "the catalogue's bar shows on Views", got)
        return
    assert bench is not None, (where, "no catalogue bar laid out", got)
    assert nav["bottom"] - 1 <= bench["top"] <= nav["bottom"] + STICKY_SLACK, (where, "the species bar scrolled away", got)
    assert bench["bottom"] <= main["bottom"] and bench["onTop"], (where, "the species bar is covered", got)


@pytest.mark.parametrize("viewport", [(1024, 768), (1600, 900)], ids=lambda v: f"{v[0]}x{v[1]}")
def test_the_tab_bar_and_the_species_bar_stay_in_view_and_no_card_lands_under_them(models_live_server, viewport):
    """Martin's decision 6 (2026-11-05): the tab bar is sticky at the top of `.main` on every subpage, with the
    catalogue's species bar under it on Distillations and Performance. Once `.main` has scrolled both are still
    in view with nothing over them; every card brought to the top (`scrollIntoView({block: 'start'})`, so the
    cards' scroll margin applies) starts below them; and a badge's deep link lands its card below them too.
    At 1024 px the species bar wraps, so the block is at its tallest."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, BASELINE_TABLE, viewport=viewport)
        for msub in SUBPAGES:
            _show_subpage(page, msub)
            room = page.evaluate("() => { const m = document.querySelector('.main'); return m.scrollHeight - m.clientHeight; }")
            assert room > 300, (msub, "the subpage is too short to scroll", room)
            for top in (room // 2, room):
                _scroll_main(page, top)
                got = page.evaluate(_STICKY, None)
                assert got["scrollTop"] > 200, (msub, got)
                _assert_pinned(got, msub, f"{msub} scrolled to {got['scrollTop']:.0f}")
            # Every card of the subpage, brought to the top: its top below the block, the block still pinned.
            for card_id in BY_SUBPAGE[BASELINE_TABLE][msub]:
                _scroll_to(page, card_id)
                got = _clear_of_sticky(page, card_id, f"{msub} {card_id}")
                if got["scrollTop"] > got["nav"]["height"] + (got["bench"]["height"] if got["bench"] else 0):
                    _assert_pinned(got, msub, f"{msub} {card_id}")
                    # The card's own scroll margin is what keeps it there (models.css `scroll-margin-top`).
                    assert got["margin"] >= got["block"] - got["main"]["top"] - 1, (msub, card_id, got)
        browser.close()

        # A badge's deep link: the card's subpage, its top below the block (the scroll margin), the block pinned.
        landed = {}
        for panel, msub in (("perf-catalog", "perf"), ("perf-diagnostics", "perf"), ("distill-curves", "distill"),
                            ("feat-corr", "views")):
            browser = p.chromium.launch(args=GL_ARGS)
            page = browser.new_page(color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]})
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            page.goto(f"{base}/models?panel={panel}&from=lnk-results-models&from_sec=3.6#table_name={BASELINE_TABLE}")
            page.wait_for_function(f"""() => {{ const s = ({_LANDED})({panel!r});
              return !location.search && s.open && s.inView && s.title === s.cardTitle; }}""", timeout=30_000)
            _quiet(page)
            got = _clear_of_sticky(page, panel, f"deep link to {panel}")
            landed[panel] = got
            if got["scrollTop"] > 0:
                _assert_pinned(got, msub, f"deep link to {panel}")
            browser.close()
    assert problems == [], problems
    # The cards a link lands mid-page are scrolled: the check above is not vacuous.
    assert landed["perf-catalog"]["scrollTop"] > 0 and landed["distill-curves"]["scrollTop"] > 0, landed


# ------------------------------------------------ the accuracy card's Log10 axis --


#: The validation-accuracy card's facets as a chart holds them: each x axis's type, and per facet the frame
#: series (Absolute, Per-shower translated, Local; the proton's TTA ticks and RMSE dots aside) with their series
#: type and the kinds of element they drew. A `custom` series' circles or a `scatter` series are dots; a rect is
#: a bar.
_FACET_MARKS_FN = """(inst) => {
  const frames = ['Absolute', 'Per-shower translated', 'Local'];
  const o = inst.getOption();
  const axes = (o.xAxis || []).map((a) => a.type ?? 'value');
  const facets = axes.map(() => []);
  inst.getModel().eachSeries((series) => {
    if (!frames.includes(series.name)) return;
    const kinds = new Set();
    inst.getViewOfSeriesModel(series)?.group.traverse((el) => {
      if (!el.isGroup && !el.ignore && !el.invisible && el.type !== 'text' && el.type !== 'tspan') kinds.add(el.type);
    });
    const i = series.get('xAxisIndex') ?? 0;
    (facets[i] ??= []).push({ name: series.name, type: series.subType, kinds: [...kinds].sort(), n: series.getData().count() });
  });
  return { axes, facets };
}"""

_FACET_MARKS = f"""(plotId) => ({_FACET_MARKS_FN})(echarts.getInstanceByDom(document.getElementById(plotId)))"""

#: The marks of every SVG export as it is serialised (the exporter's own chart, under the print tokens).
_WATCH_EXPORT_MARKS = f"""() => {{
  if (window.__exportMarks) return;
  window.__exportMarks = [];
  const init = echarts.init;
  echarts.init = function (dom, theme, opts) {{
    const chart = init.call(this, dom, theme, opts);
    if (opts && opts.renderer === 'svg') {{
      const render = chart.renderToSVGString.bind(chart);
      chart.renderToSVGString = (...args) => {{
        window.__exportMarks.push(({_FACET_MARKS_FN})(chart));
        return render(...args);
      }};
    }}
    return chart;
  }};
}}"""

#: The angle facet: the accuracy card's second facet (catalog/select.js `perf-catalog` facets: segmentation,
#: angle, energy, energy R²).
ANGLE_FACET = 1


def _dots(facet):
    """Every frame series of a facet draws dots: a scatter series, or a custom series whose elements are circles."""
    return bool(facet) and all(f["n"] == 0 or f["type"] == "scatter" or (f["kinds"] and set(f["kinds"]) <= {"circle"})
                               for f in facet) and any(f["n"] for f in facet)


def _bars(facet):
    return bool(facet) and all(f["n"] == 0 or "rect" in f["kinds"] for f in facet) and any(f["n"] for f in facet)


def test_the_accuracy_cards_log10_button_puts_the_angle_facet_on_a_log_axis_drawn_as_dots(models_live_server):
    """R2-1 / R3-1: the Log10 button (the control stores 'log10') puts the angle facet on a log₁₀ axis drawn as
    dots, never bars, on screen and in the exported SVG; the other facets keep their zero-based linear axes, and
    Linear brings the bars back. A repaint: no request."""
    card = '.main .card[data-panel="perf-catalog"]'
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE,
                                                  fragment="&model=angle")
        page.evaluate(_WATCH_EXPORT_MARKS)
        _scroll_to(page, "perf-catalog")
        linear = page.evaluate(_FACET_MARKS, "plot-perf-catalog")
        assert linear["axes"] == ["value"] * 4, linear
        assert _bars(linear["facets"][ANGLE_FACET]), linear
        assert page.get_attribute(f'{card} button[data-bench-scale="linear"]', "aria-pressed") == "true"
        # The linear export: its circles are the proton's RMSE dots alone.
        _, linear_svg = _download_svg(page, "perf-catalog")
        asked = len(requests)

        page.click(f'{card} button[data-bench-scale="log10"]')
        _wait_pressed(page, f'{card} button[data-bench-scale="log10"]')
        try:
            page.wait_for_function(f"() => ({_FACET_MARKS})('plot-perf-catalog').axes[{ANGLE_FACET}] === 'log'",
                                   timeout=5_000)
        except Exception:  # noqa: BLE001 - the assertion below names what the chart holds instead
            pass
        log = page.evaluate(_FACET_MARKS, "plot-perf-catalog")
        assert log["axes"][ANGLE_FACET] == "log", ("Log10 pressed, the angle axis is not logarithmic", log)
        assert [a for i, a in enumerate(log["axes"]) if i != ANGLE_FACET] == ["value"] * 3, log
        assert _dots(log["facets"][ANGLE_FACET]), ("Log10 draws dots, never bars", log)
        for i in (0, 2, 3):
            assert log["facets"][i] == linear["facets"][i], (i, "only the angle facet changes", log)

        # The export draws what the screen shows.
        name, svg = _download_svg(page, "perf-catalog")
        exported = page.evaluate("() => window.__exportMarks.at(-1)")
        assert name.startswith("perf-catalog_") and name.endswith(".svg"), name
        assert exported["axes"][ANGLE_FACET] == "log", ("the exported angle axis is not logarithmic", exported)
        assert _dots(exported["facets"][ANGLE_FACET]), ("the export draws bars on the log axis", exported)
        # In the SVG itself: one more <circle> for every angle value a custom series draws as a dot, beside the RMSE
        # dots (a scatter series' symbols are paths; the exporter's own chart, above, already holds them).
        dots = sum(f["n"] for f in exported["facets"][ANGLE_FACET] if f["type"] == "custom")
        assert svg.count("<circle") - linear_svg.count("<circle") == dots, (
            "the exported SVG does not draw the angle values as dots", svg.count("<circle"), linear_svg.count("<circle"), dots)

        # Linear again: the bars, as at first.
        page.click(f'{card} button[data-bench-scale="linear"]')
        _wait_pressed(page, f'{card} button[data-bench-scale="linear"]')
        page.wait_for_function(f"() => ({_FACET_MARKS})('plot-perf-catalog').axes[{ANGLE_FACET}] === 'value'",
                               timeout=5_000)
        assert page.evaluate(_FACET_MARKS, "plot-perf-catalog") == linear
        assert requests[asked:] == [], f"the angle axis control asked the service: {requests[asked:]}"
        browser.close()
    assert problems == [], problems


# ---------------------------------------- the catalogue's text on its canvas --


#: Every text a chart drew (zrender's text and tspan elements, through their transforms), in the chart's own
#: pixels, and those that leave its canvas: a row label or a direct label cut at the edge.
_CANVAS_TEXT_EDGES = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const w = inst.getWidth(); const h = inst.getHeight();
  const out = [];
  let n = 0;
  for (const el of inst.getZr().storage.getDisplayList(true)) {
    if ((el.type !== 'text' && el.type !== 'tspan') || el.ignore || el.invisible) continue;
    const text = String(el.style?.text ?? '').trim();
    if (!text) continue;
    const r = el.getBoundingRect().clone();
    if (el.transform) r.applyTransform(el.transform);
    n += 1;
    if (r.x < -0.5 || r.y < -0.5 || r.x + r.width > w + 0.5 || r.y + r.height > h + 0.5) {
      out.push({ text, x: Math.round(r.x), y: Math.round(r.y), right: Math.round(r.x + r.width),
                 bottom: Math.round(r.y + r.height) });
    }
  }
  return { w, h, n, out };
}"""

#: Every text of an exported SVG, laid out by the browser in the page's own fonts (the SVG mounted in a fixed host
#: and removed again): those leaving the viewBox, and the pairs that overlap.
_SVG_TEXT_LAYOUT = """(svgText) => {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:0;top:0;margin:0;padding:0;border:0;z-index:-1;';
  const svg = document.importNode(doc.documentElement, true);
  host.append(svg);
  document.body.append(host);
  try {
    const vb = svg.viewBox?.baseVal;
    const width = vb && vb.width ? vb.width : parseFloat(svg.getAttribute('width'));
    const height = vb && vb.height ? vb.height : parseFloat(svg.getAttribute('height'));
    const s = svg.getBoundingClientRect();
    const kx = width / s.width; const ky = height / s.height;
    // Each text's box: the browser's horizontal extent, and vertically one em about its centre (ECharts lays its
    // text out on a line one font size tall; the browser's line box adds the font's leading, so two tick labels
    // 13 px apart at 12 px would read as overlapping where no glyph does).
    const boxes = [...svg.querySelectorAll('text')].filter((t) => t.textContent.trim()).map((t) => {
      const r = t.getBoundingClientRect();
      const em = parseFloat(getComputedStyle(t).fontSize) || r.height;
      const mid = (r.top + r.bottom) / 2 - s.top;
      return { t: t.textContent.trim(), x: (r.left - s.left) * kx, y: (mid - em / 2) * ky, w: r.width * kx, h: em * ky };
    });
    const out = boxes.filter((b) => b.x < -0.5 || b.y < -0.5 || b.x + b.w > width + 0.5 || b.y + b.h > height + 0.5)
      .map((b) => ({ text: b.t, x: Math.round(b.x), right: Math.round(b.x + b.w), y: Math.round(b.y),
                     bottom: Math.round(b.y + b.h) }));
    const overlaps = [];
    for (let i = 0; i < boxes.length; i += 1) for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i]; const b = boxes[j];
      const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 0.5 && oy > 0.5) overlaps.push([a.t, b.t]);
    }
    return { width, height, n: boxes.length, out, overlaps };
  } finally {
    host.remove();
  }
}"""


@pytest.mark.parametrize("species", ["all", "electron"])
def test_the_catalogue_text_stays_on_its_canvas_on_screen_and_in_the_single_column_export(models_live_server, species):
    """R2-2, R2-3, R2-4: no catalogue row label, direct label, facet title or note is cut at its canvas's edge on
    screen (the diagnostics' 'Per-shower translated' ran 17 px off the left edge), and in the single-column SVG
    export of every exportable catalogue card (321 px) every text lies inside the viewBox and clear of every other
    (subtitle lines ran to 590 px; axis names sat over the top ticks; the curves' labels sat on each other). On
    Compare all (the two-shower file's own choice: the most rows) and on one species, energy task."""
    found = {"screen": {}, "export": {}, "overlap": {}}
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], BASELINE_TABLE)
        _show_subpage(page, "distill")
        if species != "all":
            page.click(f'#bench-bar button[data-bench-species="{species}"]')
            _wait_pressed(page, f'#bench-bar button[data-bench-species="{species}"]')
        for card_id in CATALOG_CHARTS:
            state = _scroll_to(page, card_id)
            assert state["message"] is None and state["canvas"] and state["exportButtons"] == 1, (card_id, state)
            screen = page.evaluate(_CANVAS_TEXT_EDGES, f"plot-{card_id}")
            assert screen["n"] > 5, (card_id, "no canvas text measured", screen)
            if screen["out"]:
                found["screen"][card_id] = screen["out"]
            name, svg = _download_svg(page, card_id)
            assert 'width="321"' in svg, (card_id, name)
            layout = page.evaluate(_SVG_TEXT_LAYOUT, svg)
            assert layout["width"] == 321 and layout["n"] > 5, (card_id, layout)
            if layout["out"]:
                found["export"][card_id] = layout["out"]
            if layout["overlaps"]:
                found["overlap"][card_id] = layout["overlaps"]
        browser.close()
    assert problems == [], problems
    # One assertion, so a failure names every defect at once.
    report = [f"cut at the canvas edge on screen, {c}: {v}" for c, v in found["screen"].items()]
    report += [f"outside the 321 px viewBox of the export, {c}: {v}" for c, v in found["export"].items()]
    report += [f"drawn over each other in the export, {c}: {v}" for c, v in found["overlap"].items()]
    assert not report, f"{species}: catalogue text off its canvas or on another text:\n  " + "\n  ".join(report)
