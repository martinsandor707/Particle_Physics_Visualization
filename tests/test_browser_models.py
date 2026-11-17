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
* the energy-resolution card (``res-scaling``) opens (res-emax, Martin's
  decisions of 2026-11-17) on the E (GeV) + ratio view, Median |rel. err.|,
  both showers, the calibrated deposit hidden and E max at the data's edge
  (20 GeV on the recordings), in both themes; the E max slider repaints with
  no request, ticks the axis it ends and draws nothing beyond it on either
  panel; the Deposit toggle shows and hides the deposit on both views, the
  range following the series on show (``y_model``), and is shut, pressed,
  where the deposit is the only series; with the deposit hidden and no
  literature curve on the ratio panel draws no mark and says why;
* in its 1/√E view (pressed explicitly) it draws its reversed 1/√E axis
  ending at the origin corner, the Energy (GeV) axis on top over the same
  range with ∞ at 0, a y axis from 0 and its fit table under the plot; its
  window, shower and theme switches repaint with no request (the two-shower
  baseline's two events draw its empty state, with the table still there);
  its "E (GeV) + ratio" view, from the same response and with no request,
  stacks two grids on one E axis (0-80 GeV with E max at the server's end),
  σ/E from 0 over a log ratio axis
  symmetric about 1, one fitted curve per series and panel (its a/√E ⊕ b ⊕ c/E,
  else its a₀/√E from 4 GeV) solid over its windows and dashed beyond, with no
  band anywhere on the view (Martin's directive of 2026-11-15), a 600 px plot,
  a title naming the view, an export of both grids and tooltips under the 20%
  rule on either grid; "Ratio to" and the shower buttons repaint it, and the
  1/√E view, which keeps its bands, comes back identical;
* the resolution card's Estimator control (Martin's decisions of 2026-11-12), on the recorded two-shower responses
  served by the request's estimator: View, Estimator, Windows, Shower, Deposit, Literature in that order, Median |rel. err.|
  pressed by default, the View and literature buttons with their titles (the E view's naming one curve per series
  and no band; each equation without a % sign, its units beside it); each switch one request carrying the new
  estimator, the other choices kept; the title, the
  y axis and the export's est-<name> follow it; under the median in the E view with a curve on, the note band, the
  drawer, the Details hazard and the curve and ratio tooltips carry the literature disclosure, and under Robust σ
  (IQR) or with no curve none do; every tooltip keeps to the 20% cap under each estimator; screens of both views
  under each estimator in both themes (CALOSRV_RES_SCREENS);
* the single-curve round (Martin's directive of 2026-11-15), read back from the live chart in both themes, under
  each estimator, both window modes, the literature curves on and off: one fitted-curve family per series and
  panel, no band, edge or reference-band series, each ratio curve's tooltip with its terms, χ²/ν and S and the
  no-band line once, the literature legend entries and tooltips without a % sign by the values and with their
  units, a 1–4 GeV window's tooltip naming the one pooled scale c, and the drawer's no-band sentence once with no
  envelope, its pooled-scale clause on the 1–4 GeV windows' residuals under median and robust;
* a series switched off on the resolution card's legend (Martin's bugs of
  2026-11-11, both views, on the recorded two-shower response) stays off
  across the window switch with no page error, and switched back on draws
  every one of its marks as a fresh render does; it stays off across a theme
  switch with no request, and the export leaves it out with its legend
  entry, its end label and its off-scale values (res-emax: no exported entry
  is greyed); on screen its entry is drawn in the card's legible inactive
  ink, and the open drawer names it in Marks and legend until it is switched
  back on; the exported file name carries energy, emax-<n>, deposit-off and
  ratio-none as the card's state says;
* the particle filter on Views (brief particle-filter §8): the 3-D event card's
  Pick for me, Most tilted and Densest drawing from the pool, the densest
  candidate drawn with its matching shower, "2-D ↗" opening the Physics page's
  Event viewer (``psub=event``) on the same event and shower; N = 0 showing the
  empty line on the event pair with no pick or event request; the block on
  Views only;
* the pool of the whole experiment (brief physics-subpages §10.2, Martin's
  decision of 2026-11-16): every One event request (raster, cubes, Pick for
  me, Most tilted, Densest, the steps) carries ``basis=experiment`` and no E₁,
  E₂ or D key; an E₁ commit on Views asks nothing of ``/api/event*`` and leaves
  the 3-D event, its caption and the draw counter, while the Selection scope
  and the cloud reload under the cut; "Open in 3-D →" from the Physics Event
  viewer and "2-D ↗" back land on the same event and shower, both drawn;
* the standing "Unavailable for this experiment" line of the channels an
  experiment cannot serve, visible on the 3-D cards of the single-shower hits
  (event and cloud) and on the two-shower baseline's event card, in both
  themes, its text at 4.5:1 or more on the card;
* the 3-D cards' slice mode: K slices stepped with Previous, Next and the
  scrubber, K clamped to the volume's depth, the slices' cubes adding up to
  the whole volume's, the paired depth projections bracketing the slice drawn,
  with no request and the reader's turned and zoomed camera kept, and the
  slice row hidden without WebGL.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import BASELINE_TABLE, MODELS_XGB_TABLE, SINGLE_HITS_TABLE
from test_browser_physics import (
    _PROBE, _RECORD_CANVAS_TEXT, _WATCH_EXPORTS, _WATCH_HOVER, _assert_sections, _beside, _check_tips,
    _download_svg, _hyphen_negatives, _live_series, _overlap, _route_requests,
    _DRAWN as _CHART_DRAWN, _click_legend as _click_chart_legend,
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
#: Views draws the 3-D pair of the selected frame only (Martin's directives, 2026-11-06): the cold boot's Absolute
#: frame draws the event pair alone; Local draws both, one at a time, and opens on the selection, the cloud there
#: (`LOCAL_VIEWS`).
BY_SUBPAGE = {
    BASELINE_TABLE: {"views": EVENT_PAIR + FEATURES + ["prim-rate"], "distill": DISTILL,
                     "perf": PERF + RES + BENCH},
    SINGLE_HITS_TABLE: {"views": EVENT_PAIR + FEATURES + ["prim-rate"], "distill": DISTILL,
                        "perf": RES + BENCH},
    MODELS_XGB_TABLE: {"views": FEATURES, "distill": DISTILL + XGB_DISTILL, "perf": PERF + RES + XGB_PERF + BENCH},
}
#: Every card a kind shows, across the subpages, in page order (views, distill, perf).
CARDS = {table: [c for msub in SUBPAGES for c in by[msub]] for table, by in BY_SUBPAGE.items()}
#: The cards Views shows in Local on the selection, its cold-boot scope: the ensemble cloud and its projections.
#: Local draws one 3-D pair at a time; the 3-D card's Selection | One event chooses.
LOCAL_VIEWS = {BASELINE_TABLE: ENSEMBLE_PAIR, SINGLE_HITS_TABLE: ENSEMBLE_PAIR}
#: The subpage of every card on any kind.
SUBPAGE_OF = {c: msub for by in BY_SUBPAGE.values() for msub, ids in by.items() for c in ids}
SUBPAGE_OF.update({c: "views" for c in ENSEMBLE_PAIR})
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


def _choose_frame(page, frame):
    """Choose a reference frame on the sidebar's radio, as a reader does: Views then draws that frame's 3-D pair."""
    _show_subpage(page, "views")
    page.check(f'#m-frame input[value="{frame}"]')
    page.wait_for_function(
        "(f) => (new URLSearchParams(location.hash.slice(1)).get('frame') ?? 'lab') === f", arg=frame, timeout=10_000)
    page.wait_for_timeout(300)


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
        # The Absolute frame draws the event pair alone: the cloud is not asked for. Local draws it, on view.
        assert not _requests_of(requests, "/api/voxels"), _urls(requests)
        _choose_frame(page, "local")
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

        def check(card_id):
            state = _scroll_to(page, card_id)
            where = f"{table} {card_id}"
            assert _subpage(page) == SUBPAGE_OF[card_id], where
            if card_id in SHUT.get(table, ()):
                assert state["kind"] == "disabled" and state["message"], (where, state)
                return
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

        for card_id in CARDS[table]:
            check(card_id)
        # Local opens on the selection, the cloud there: the cloud and its projections, checked the same way.
        if table in LOCAL_VIEWS:
            _choose_frame(page, "local")
            visible = _visible_cards(page)
            assert visible[:4] == LOCAL_VIEWS[table] and not set(EVENT_PAIR) & set(visible), visible
            for card_id in LOCAL_VIEWS[table]:
                check(card_id)
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
        if table in LOCAL_VIEWS:
            _choose_frame(page, "local")
            for card_id in LOCAL_VIEWS[table]:
                _scroll_to(page, card_id)
            measured["views (Local)"] = page.evaluate(_OVERFLOW)
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

        def probe(card_id):
            nonlocal tips
            if card_id in ("feat-table", "distill-pysr") or card_id in SHUT.get(table, ()):
                return
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

        for card_id in CARDS[table]:
            probe(card_id)
        if table in LOCAL_VIEWS:
            _choose_frame(page, "local")
            for card_id in LOCAL_VIEWS[table]:
                probe(card_id)
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

        def export(card_id):
            state = _scroll_to(page, card_id)
            if card_id in GL_CARDS or card_id in ("feat-table", "distill-pysr"):
                assert state["exportButtons"] == 0, (card_id, "a 3-D view or a table is not a figure")
                return
            assert state["exportButtons"] == 1, card_id
            live = _live_series(page, f"plot-{card_id}")
            exported[card_id] = _download_svg(page, card_id)
            series[card_id] = (live, page.evaluate("() => window.__exportSeries.at(-1)"))

        for card_id in CARDS[table]:
            export(card_id)
        if table in LOCAL_VIEWS:
            _choose_frame(page, "local")
            for card_id in LOCAL_VIEWS[table]:
                export(card_id)
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
            # The card's default (res-emax, Martin's decisions of 2026-11-17): the E view, its E axis named and no
            # 1/√E axis, and no row of the screen's fit table. Its name: the E view's tokens, the axis end at the
            # data's edge and, where a model series is on show, the deposit hidden (forced on for the deposit-only
            # single-shower hits, so their name says nothing of it).
            assert "Energy E [GeV]" in texts and "∞" not in texts, texts
            assert not [t for t in texts if "1/√E" in t and "/√E ⊕" not in t], texts
            assert not [t for t in texts if "Windows fitted" in t or "Quadrature" in t or "SE(a" in t], texts
            assert "_energy_emax-20_" in name and re.search(r"_est-median_\d{8}_\d{6}\.svg$", name), name
            assert ("_deposit-off_" in name) is (table == MODELS_XGB_TABLE), name
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


#: The E view (panels/resolution_scaling.js energyViewOption) as the chart holds it and as it drew it: its grids
#: and axes, the crosshair, and every fitted curve's drawn geometry read back from the polylines ECharts painted
#: (a custom series keeps its geometry in a closure, so `getOption()` holds one datum), each point converted to
#: data on its own grid. Keyed by series id: `<series key>|[ratio|]<form>|<solid|dashed>|<run>`.
_RES_ENERGY = """() => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const o = inst.getOption();
  const model = inst.getModel();
  const rects = (o.grid || []).map((_, i) => {
    const r = model.getComponent('grid', i)?.coordinateSystem?.getRect();
    return r ? { left: r.x, top: r.y, right: r.x + r.width, bottom: r.y + r.height } : null;
  });
  const curves = {};
  model.eachSeries((s) => {
    const id = s.get('id') || '';
    if (!/\\|(noise|quadrature|pinned)\\|(solid|dashed)\\|\\d+$/.test(id)) return;
    const grid = s.get('yAxisIndex') ?? 0;
    const pts = [];
    let dash = null;
    let opacity = null;
    inst.getViewOfSeriesModel(s).group.traverse((el) => {
      if (el.type !== 'polyline' || !el.shape?.points) return;
      dash = el.style?.lineDash ? Array.from(el.style.lineDash) : null;
      opacity = el.style?.opacity ?? 1;
      for (const [px, py] of el.shape.points) pts.push(inst.convertFromPixel({ gridIndex: grid }, [px, py]));
    });
    curves[id] = { grid, dash, opacity, points: pts };
  });
  // Each window marker series' paint: the fills and strokes of its drawn circles (a hollow marker is filled with
  // the card's ground and stroked in its series' colour).
  const markers = {};
  model.eachSeries((s) => {
    const id = s.get('id') || '';
    if (!/\\|markers$/.test(id)) return;
    const fills = new Set();
    const strokes = new Set();
    inst.getViewOfSeriesModel(s).group.traverse((el) => {
      if (el.type !== 'circle') return;
      fills.add(String(el.style?.fill ?? 'none').toLowerCase());
      strokes.add(String(el.style?.stroke ?? 'none').toLowerCase());
    });
    markers[id] = { fills: [...fills].sort(), strokes: [...strokes].sort() };
  });
  const pointer = [].concat(o.axisPointer || []);
  return {
    grids: (o.grid || []).length, rects,
    x: (o.xAxis || []).map((a) => ({ gridIndex: a.gridIndex ?? 0, min: a.min, max: a.max, interval: a.interval ?? null,
      name: a.name ?? '', labels: a.axisLabel?.show !== false,
      pointer: a.axisPointer ? { show: a.axisPointer.show, type: a.axisPointer.type,
        triggerTooltip: a.axisPointer.triggerTooltip, snap: a.axisPointer.snap,
        label: Boolean(a.axisPointer.label?.show) } : null })),
    y: (o.yAxis || []).map((a) => ({ gridIndex: a.gridIndex ?? 0, type: a.type ?? 'value', min: a.min, max: a.max,
      name: a.name ?? '', ticks: a.axisLabel?.customValues ?? null })),
    link: pointer.map((p) => p.link ?? null),
    ids: (o.series || []).map((s) => s.id ?? s.name),
    curves, markers,
  };
}"""

#: The resolution card's title and plot height, and the toolbar's buttons that are on show.
_RES_CHROME = """() => {
  const card = document.querySelector('.main .card[data-panel="res-scaling"]');
  const plot = document.getElementById('plot-res-scaling');
  const shown = (sel) => [...card.querySelectorAll(sel)].filter((b) => !b.closest('[hidden]'))
    .map((b) => [b.textContent, b.getAttribute('aria-pressed')]);
  return {
    title: card.querySelector('.title')?.textContent ?? '',
    height: plot.getBoundingClientRect().height, styleHeight: plot.style.height,
    views: shown('button[data-res-view]'), windows: shown('button[data-res-windows]'),
    references: shown('button[data-res-reference]'), literature: shown('button[data-res-literature]'),
  };
}"""

#: The literature toggles' state: [particle, aria-pressed, disabled, title] per button.
_RES_LIT_TOGGLES = """() => [...document.querySelectorAll('.main .card[data-panel="res-scaling"] button[data-res-literature]')]
  .map((b) => [b.textContent, b.getAttribute('aria-pressed'), b.disabled, b.title])"""

#: Every chart the SVG export builds (echarts.init with the svg renderer), its option's shape when exported.
_WATCH_EXPORT_GRIDS = """() => {
  if (window.__exportShapes) return;
  window.__exportShapes = [];
  const init = echarts.init;
  echarts.init = function (dom, theme, opts) {
    const chart = init.call(this, dom, theme, opts);
    if (opts && opts.renderer === 'svg') {
      const render = chart.renderToSVGString.bind(chart);
      chart.renderToSVGString = (...args) => {
        const o = chart.getOption();
        window.__exportShapes.push({
          grids: (o.grid || []).length, x: (o.xAxis || []).map((a) => [a.gridIndex ?? 0, a.min, a.max]),
          y: (o.yAxis || []).map((a) => [a.gridIndex ?? 0, a.type ?? 'value', a.min, a.max]),
          series: (o.series || []).length, height: chart.getHeight(), width: chart.getWidth(),
        });
        return render(...args);
      };
    }
    return chart;
  };
}"""

#: The view's E axis: where a fitted curve may start (`axis.energy.curve_min_gev`).
CURVE_MIN_GEV = 4.0
#: Where a/√E ⊕ b ⊕ c/E's windows start (`axis.energy.noise_min_gev`, resolution_scaling.py NOISE_MIN_GEV): the
#: 1–4 GeV windows enter it, the 0–1 GeV window never does (res-noise brief §0 decision 3).
NOISE_MIN_GEV = 1.0


def _res_payload(base, asked):
    """The response the card drew, asked again from the Python side (not the page, whose requests are counted)."""
    import httpx

    return httpx.get(f"{base}/api/resolution-scaling", params=asked, timeout=60).json()


def _res_press(page, attr, value):
    """Click one of the resolution card's segmented buttons; whether it is then the pressed one."""
    button = page.locator(f'.main .card[data-panel="res-scaling"] button[data-{attr}="{value}"]')
    button.click()
    page.wait_for_timeout(250)
    return button.get_attribute("aria-pressed") == "true"


#: The resolution card's Deposit toggle (models_cards.js RES_DEPOSIT_CONTROL: one button, value 'on', in the
#: "Benchmark" group) and its E max slider (RES_EMAX_CONTROL, the `range` kind), res-emax brief §6.2.
RES_DEPOSIT = '.main .card[data-panel="res-scaling"] button[data-res-deposit="on"]'
RES_EMAX = '.main .card[data-panel="res-scaling"] label.mini-range[data-res-emax="res-scaling"]'
#: Their fixed text (labels.js MODELS_LABELS.res_deposit, res_deposit_forced, res_emax; brief §6.3), verbatim.
RES_DEPOSIT_TITLE = ("Draw or hide the calibrated deposit c·E_dep, the linear-sum benchmark, on both views: its windows, "
                     "its fitted curve and its fit-table rows. Hidden, the error-scale range follows the model series "
                     "alone, and the ratio panel divides by the literature curve on show (with both on, the one the "
                     "model series' windows lie farther from), or draws nothing with none on.")
RES_DEPOSIT_FORCED = "The calibrated deposit is this response's only series, so it is always drawn."
RES_EMAX_TITLE = ("The upper end of the E view's energy axis, in 5 GeV steps: from the data's highest window edge "
                  "rounded up to 5 GeV, so every window stays on the axis, to the axis end the server sets. Nothing beyond it is drawn on either "
                  "panel, and no fit is refitted; the card repaints without a request.")
RES_EMAX_ARIA = "E max, the upper end of the energy axis in GeV"
#: The empty state with the deposit hidden (brief §5.6) and the ratio panel's sentence with no reference (§5.5).
RES_DEPOSIT_HIDDEN_EMPTY = ("The calibrated deposit is hidden, and the model series have no window to draw in this "
                            "selection; switch on Deposit to draw it.")
RATIO_NONE_TEXT = "No ratio drawn: no reference is on show."
RATIO_NONE_SCREEN_TEXT = " Switch on π±, e± or the deposit to draw one."

#: The E max slider as the reader meets it: whether it is laid out, its bounds, value and text.
_RES_EMAX_STATE = """(sel) => {
  const label = document.querySelector(sel);
  if (!label) return null;
  const input = label.querySelector('input');
  return {
    hidden: label.hidden, shown: label.getClientRects().length > 0, type: input.type, disabled: input.disabled,
    min: input.min, max: input.max, step: input.step, value: input.value,
    output: label.querySelector('output.mini-range-value')?.textContent ?? null,
    name: label.querySelector('.mini-range-name')?.textContent ?? null,
    title: label.title, aria: input.getAttribute('aria-label'),
  };
}"""


def _res_deposit(page, on):
    """Put the resolution card's Deposit toggle in the state asked: a click only when its aria-pressed differs (a
    forced deposit's button is shut and pressed, so asking for it on clicks nothing). Whether it is then pressed."""
    button = page.locator(RES_DEPOSIT)
    want = "true" if on else "false"
    if button.get_attribute("aria-pressed") != want:
        button.click()
        page.wait_for_function("([sel, want]) => document.querySelector(sel)?.getAttribute('aria-pressed') === want",
                               arg=[RES_DEPOSIT, want], timeout=10_000)
    _frames(page)
    return button.get_attribute("aria-pressed") == "true"


def _set_emax(page, value, event="change"):
    """Move the E max slider to `value` as a reader's drag or key does (Playwright's fill() cannot drive a range
    input): its value set and one `input` (coalesced to one repaint per frame) or `change` (at once) event."""
    page.evaluate("""([sel, v, ev]) => {
      const input = document.querySelector(`${sel} input`);
      input.value = String(v);
      input.dispatchEvent(new Event(ev, { bubbles: true }));
    }""", [RES_EMAX, value, event])
    _frames(page, 3)


def _default_emax(payload):
    """The slider's lower end, where the card opens (res_axis.js eMaxRange): the data's top window edge rounded up to
    5 GeV, at least 5, at most the server's axis end."""
    energy = payload["axis"]["energy"]
    top = energy["x"]["max"]
    # The data's top edge as res_axis.js eDataTop takes it: data_max_gev and every window's own p_hi (review R3-8).
    edges = [energy.get("data_max_gev")] + [w.get("p_hi") for s in payload.get("series", []) for w in s.get("windows", [])]
    edges = [e for e in edges if isinstance(e, (int, float)) and math.isfinite(e)]
    if not edges:
        return top
    return min(top, max(5, math.ceil(max(edges) / 5) * 5))


def _has_model_series(payload):
    """Whether the response holds a series other than the calibrated deposit (res_axis.js hasModelSeries): where it
    does not, the deposit is forced on."""
    return any(s.get("source") != "detector" for s in payload["series"])


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
    buttons (two showers) and a theme switch repaint from the response in hand.

    The card opens on the E view (res-emax, Martin's decisions of 2026-11-17), so the 1/√E view is pressed first,
    with the card's other defaults kept: the calibrated deposit hidden where a model series is on show. On the
    baseline's two events the 1/√E view then says the deposit-hidden empty state; the deposit switched on, the
    empty state it always said."""
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], table)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        asked = _requests_of(requests, "/api/resolution-scaling")
        assert len(asked) == 1, _urls(requests)
        # A networked plan names the energy network's frame (models_cards.js cardRequest).
        assert (asked[0].get("coord_system") == "lab") is (table == BASELINE_TABLE), asked
        # The default estimator goes on the request (brief §3), and the title names what it plots (brief §4) in the
        # view the card opens on, then in the 1/√E view.
        assert asked[0].get("estimator") == DEFAULT_ESTIMATOR, asked
        assert state["title"] == "Median Relative Error vs. E", state
        assert _res_press(page, "res-view", "linear")
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        state = page.evaluate(_CARD, "res-scaling")
        assert state["title"] == "Median Relative Error vs. 1/√E", state
        if table == BASELINE_TABLE:
            # The deposit hidden and the networks' two events holding no window, nor the deposit's: the view's own
            # empty state, never the advice to switch the deposit on, which would draw nothing either (B's finding);
            # with the deposit on, the empty state of a selection with no window, as below.
            texts = page.evaluate(_CHART_TEXTS, "plot-res-scaling")
            assert not any(_flat(t) == RES_DEPOSIT_HIDDEN_EMPTY for t in texts), texts
            assert any(_flat(t).startswith("No momentum window") for t in texts), texts
            assert _res_deposit(page, True)
            state = page.evaluate(_CARD, "res-scaling")
        axes = page.evaluate(_RES_AXES)
        fit = page.evaluate(_RES_TABLE)
        series = page.evaluate(_RES_SERIES)
        before = len(requests)

        # The fit table: after the plot frame, inside the card, below the plot and clear of it.
        assert fit is not None and fit["inCard"] and fit["afterFrame"] and not fit["inFrame"], fit
        assert fit["host"]["top"] >= fit["plot"]["bottom"] - 0.5, fit
        # The caption names the quantity under the median (S2-panel decision 7).
        assert fit["caption"].startswith("Fits of the median rel. through the 3 anchor windows"), fit
        assert fit["heads"][0] == "Series" and "Windows fitted" in fit["heads"], fit
        # Four fits per series: the affine, the pinned, a/√E ⊕ b and a/√E ⊕ b ⊕ c/E (res-noise, tabled here).
        assert fit["rows"] and len(fit["fits"]) == 4 * len(fit["rows"]), fit
        # Its text columns wrap, so at 1600 px the table keeps to its card (it ran 1721 px in 1212 kept on one line).
        assert fit["overflow"] <= 1, fit

        if table in RES_DRAWN:
            assert state["series"] > 0, state
            bottom, top = axes["x"]
            assert bottom["position"] in (None, "bottom") and bottom["inverse"], bottom
            assert (bottom["min"], bottom["max"]) == (0, 0.5) and "1/√E" in bottom["name"], bottom
            assert top["position"] == "top" and top["inverse"] and (top["min"], top["max"]) == (0, 0.5), top
            assert top["name"].startswith("Energy (GeV)"), top
            # The y axis is named by the estimator in force (brief §3 `axis.y.name`).
            assert axes["y"][0]["name"].startswith("Median |E_est − p| / p [%]"), axes["y"]
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
            # Two events hold no window of two events from 4 GeV: the empty state, said on the chart, naming the
            # quantity of the estimator in force.
            assert state["series"] == 0 and state["graphic"] == 1, state
            texts = page.evaluate(_CHART_TEXTS, "plot-res-scaling")
            assert any("no median rel. can be drawn" in t for t in texts), texts
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


#: A curve point read back from its pixel lands within this of where it was drawn, in GeV (float round trip).
E_TOL = 1e-6


def _noise_entry(params, top):
    """Where a/√E ⊕ b ⊕ c/E comes down into the main panel, in GeV: the root u = 1/E of
    C·u² + A·u + (B − top²) = 0 in its stable form (res-noise brief §4.1), the squares in %² as served; None for a
    flat curve (A = C = 0), drawn from 0 GeV, or one above the top at every E (B ≥ top²)."""
    a2, b2, c2 = params["a2"], params["b2"], params["c2"]
    room = top * top - b2
    if (a2 <= 0 and c2 <= 0) or room <= 0:
        return None
    u = 2 * room / (a2 + (a2 * a2 + 4 * c2 * room) ** 0.5)
    return 1 / u


def _noise_drawable(block):
    """Whether a noise block can be drawn (panels/resolution_scaling.js `noiseDrawable`): its three squares finite
    and non-negative, one of them positive."""
    params = (block or {}).get("params") or {}
    squares = [params.get(k) for k in ("a2", "b2", "c2")]
    return (bool(block) and block.get("form") == "noise"
            and all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in squares) and sum(squares) > 0)


def _drawn_form(mf):
    """The one curve a series draws on the E view in a mode (Martin's directive of 2026-11-15, CLAUDE.md §5 "One
    fitted curve per series"): its a/√E ⊕ b ⊕ c/E where drawable, else its origin-pinned a₀/√E, else none."""
    if _noise_drawable(mf.get("noise")):
        return "noise"
    a0 = ((mf.get("pinned") or {}).get("params") or {}).get("a0")
    return "pinned" if isinstance(a0, (int, float)) and math.isfinite(a0) else None


#: Why a series has no fit from 4 GeV (panels/resolution_scaling.js `fitMissingReason`, review-ui F2 and
#: review-docs M3, 19f6ab2), verbatim, as the fit table's cells and the drawer give it.
DECLINED_REASON = "Robust σ (IQR) fits no line through fewer than two fittable windows"
NO_SCALE_REASON = "no window from 4 GeV carries a fit weight, so this series has no pooled scale"
TOO_FEW_WINDOWS = "too few windows"


def _fit_missing_reason(payload, s, mode):
    """The causes `fitMissingReason` can give for a series' missing fit from 4 GeV, as a tuple of the ones the payload
    allows: no pooled scale where `weight_scale.c` is null; under the robust estimator with no fitted window, the
    decline or too few windows (which of the two turns on the windows' fittability, the panel's to judge); else too
    few windows."""
    ws = s.get("weight_scale")
    if payload["estimator"]["name"] == "robust" and not s["fits"][mode].get("points"):
        return (DECLINED_REASON, NO_SCALE_REASON, TOO_FEW_WINDOWS) if ws and ws.get("c") is None \
            else (DECLINED_REASON, TOO_FEW_WINDOWS)
    if ws and ws.get("c") is None:
        return (NO_SCALE_REASON,)
    return (TOO_FEW_WINDOWS,)


def _assert_e_view_curves(view, payload, mode):
    """The E view's fitted curves as drawn (res-noise brief §0 decision 2, §4.1; CLAUDE.md §5 "One fitted curve per
    series", "Solid and dashed").

    One curve per series on each panel (Martin's directive of 2026-11-15): its a/√E ⊕ b ⊕ c/E where it has a
    drawable one, else its a₀/√E, never both, and no band. a₀/√E: nothing below `curve_min_gev` (4 GeV).
    a/√E ⊕ b ⊕ c/E: drawn from 0 GeV, coming down into the main panel from its top at the energy where its line
    reaches the axis top (the root of C·u² + A·u + (B − top²)), or from E = 0 when flat (A = C = 0). Each solid run
    inside its fit's own span (`span_gev`) and meeting it at both edges, unless the curve is above the plot at the
    span's low edge (CLAUDE.md §5: a fit is never a range setter, so its solid run then starts on the axis's top
    edge); each dashed run [6, 4] and wholly outside the span; on the main panel the dashed part beyond the span runs
    to the axis end. a/√E ⊕ b is never drawn on this view (it is tabled). Returns the forms drawn per series.

    The axis end is the chart's: E max (res-emax), from the data's edge to the server's `axis.energy.x.max`; nothing
    is drawn past it, and a run fitted up to it is solid to the end with no dashed part beyond."""
    energy = payload["axis"]["energy"]
    x_max, curve_min = view["x"][-1]["max"], energy["curve_min_gev"]
    assert all(a["max"] == x_max for a in view["x"]) and _default_emax(payload) <= x_max <= energy["x"]["max"], \
        (view["x"], energy["x"])
    assert curve_min == CURVE_MIN_GEV and energy["noise_min_gev"] == NOISE_MIN_GEV, energy
    by_key = {s["key"]: s for s in payload["series"]}
    top = view["y"][0]["max"]
    drawn = {}
    on_ratio = {}
    # No band, outline edge or reference band on this view (§2's recorded exception): every series id says so.
    assert not [i for i in view["ids"] if "|band|" in i or i.endswith("|band") or "|edges|" in i
                or "|reference|" in i], view["ids"]

    def at_top(value):
        # A point read back from its pixel on the main panel's top edge (the float round trip of a 600 px plot).
        return value == pytest.approx(top, rel=1e-3, abs=1e-6)

    def fit_of(key, form):
        mf = by_key[key]["fits"][mode]
        return mf["noise"] if form == "noise" else mf

    for cid, curve in view["curves"].items():
        parts = cid.split("|")
        key, run_part, form = parts[0], parts[-2], parts[-3]
        on_ratio_panel = parts[1] == "ratio"
        es = [pt[0] for pt in curve["points"]]
        assert es, (cid, curve)
        assert curve["grid"] == (1 if on_ratio_panel else 0), (cid, curve["grid"])
        # a/√E ⊕ b is tabled on this view, never drawn (res-noise decision 2).
        assert form in ("noise", "pinned"), cid
        # a₀/√E: nothing below 4 GeV, which it cannot use. a/√E ⊕ b ⊕ c/E: from 0 GeV. Nothing past the axis end.
        assert min(es) >= (curve_min if form == "pinned" else 0) - E_TOL, (cid, min(es))
        assert max(es) <= x_max + E_TOL, (cid, max(es))
        lo, hi = fit_of(key, form)["span_gev"]
        if run_part == "solid":
            assert curve["dash"] is None, (cid, curve["dash"])
            assert lo - E_TOL <= min(es) and max(es) <= hi + E_TOL, (cid, (min(es), max(es)), (lo, hi))
        else:
            assert curve["dash"] == [6, 4], (cid, curve["dash"])
            assert max(es) <= lo + E_TOL or min(es) >= hi - E_TOL, (cid, (min(es), max(es)), (lo, hi))
        if on_ratio_panel:
            on_ratio.setdefault(key, set()).add(form)
        else:
            first = min(curve["points"], key=lambda pt: pt[0])
            drawn.setdefault(key, {}).setdefault(form, []).append((run_part, min(es), max(es), first[1]))
    # Every series on show (its window markers drawn) whose one curve reaches the main panel draws it there: the noise
    # fit unless its line is above the axis top at every E (B ≥ top², where its caret at the axis end says so
    # instead), the a₀/√E fallback unless it is above the top even at the axis end, where it is lowest.
    shown = {i.split("|")[0] for i in view["ids"] if i.endswith("|markers") and "|ratio|" not in i}
    x_end = x_max
    for key in shown:
        mf = by_key[key]["fits"][mode]
        expected = _drawn_form(mf)
        visible = (expected == "noise" and mf["noise"]["params"]["b2"] < top * top) or \
                  (expected == "pinned" and mf["pinned"]["params"]["a0"] / x_end ** 0.5 < top)
        assert (key in drawn) is visible, (key, expected, sorted(drawn.get(key, {})), mf["noise_reason"])
    for key, forms in on_ratio.items():
        # The ratio panel divides the same one curve, never another form.
        assert forms == {_drawn_form(by_key[key]["fits"][mode])}, (key, forms)
    for key, forms in drawn.items():
        mf = by_key[key]["fits"][mode]
        # One curve per series: its a/√E ⊕ b ⊕ c/E where drawable, else its a₀/√E, never a second line beside it.
        assert sorted(forms) == [_drawn_form(mf)], (key, sorted(forms), mf["noise_reason"])
        for form, runs in forms.items():
            lo, hi = fit_of(key, form)["span_gev"]
            solid = [r for r in runs if r[0] == "solid"]
            assert len(solid) == 1, (key, form, runs)
            # Solid over the fitted windows, meeting the dashed parts exactly at the span's edges; a curve that is
            # above the plot at the span's low edge (every fitted form falls with E) comes in at the top edge instead.
            clipped_low = solid[0][1] > lo + E_TOL
            if clipped_low:
                assert at_top(solid[0][3]), (key, form, runs, top)
            else:
                assert solid[0][1] == pytest.approx(lo, abs=E_TOL), (key, form, runs)
            assert solid[0][2] == pytest.approx(hi, abs=E_TOL), (key, form, runs)
            beyond = [r for r in runs if r[0] == "dashed" and r[1] >= hi - E_TOL]
            if hi < x_max:
                assert len(beyond) == 1 and beyond[0][1] == pytest.approx(hi, abs=E_TOL), (key, form, runs)
                assert beyond[0][2] == pytest.approx(x_max, abs=E_TOL), (key, form, runs)
            below = [r for r in runs if r[0] == "dashed" and r[2] <= lo + E_TOL]
            if clipped_low:
                # Above the plot from the span's low edge down: nothing is drawn below the span.
                assert below == [], (key, form, runs)
            elif form == "pinned" and lo > curve_min:
                # Down to 4 GeV, or to where the curve leaves the top of the axis on its way there.
                assert len(below) == 1 and below[0][2] == pytest.approx(lo, abs=E_TOL), (key, form, runs)
                assert below[0][1] == pytest.approx(curve_min, abs=E_TOL) or at_top(below[0][3]), (key, form, runs)
            elif form == "noise":
                # Down from the span towards 0 GeV: from the top edge, where the line comes down into the plot at
                # the root's energy, or from E = 0 when the curve is flat.
                assert len(below) == 1 and below[0][2] == pytest.approx(lo, abs=E_TOL), (key, form, runs)
                entry = _noise_entry(mf["noise"]["params"], top)
                if entry is None:
                    assert below[0][1] == pytest.approx(0, abs=1e-3), (key, runs, mf["noise"]["params"])
                else:
                    assert at_top(below[0][3]), (key, runs, top)
                    assert below[0][1] == pytest.approx(entry, rel=1e-3, abs=1e-4), (key, runs, entry)
    return {key: sorted(forms) for key, forms in drawn.items()}


def _main_curves(view):
    """The main panel's curves as data, flattened for an approximate comparison (each point is read back through
    its pixel, so a grid moved by the legend shifts the last digits)."""
    return {cid: [c["opacity"], *(v for pt in c["points"] for v in pt)]
            for cid, c in view["curves"].items() if "|ratio|" not in cid}


def _within(point, rect):
    return rect["left"] <= point[0] <= rect["right"] and rect["top"] <= point[1] <= rect["bottom"]


#: The card's estimators, in the Estimator control's order (brief §4; models_cards.js RES_ESTIMATOR_CONTROL), and
#: the one a request carries when the reader has chosen none.
RES_ESTIMATORS = ("median", "robust", "sample")
DEFAULT_ESTIMATOR = "median"
#: The recorded responses (tests/test_payload_fixtures.py), one per estimator and kind: the sample estimator's keeps
#: the older name `res_scaling_<kind>`, the others are `res_scaling_<estimator>_<kind>`.
PAYLOADS = Path(__file__).resolve().parent / "fixtures" / "payloads"
#: The recorded two-shower kind, served to the baseline's page in place of its own: the live two-shower baseline
#: holds two events, too few for any window, and the E view's two-shower grammar (shower B hollow, its lines at
#: 70%, the A / B / Both buttons) needs one drawn.
RES_TWO = "two"
#: The E view's cases: each live kind, and the baseline's page drawing the recorded two-shower response.
E_VIEW_CASES = [pytest.param(BASELINE_TABLE, None, id="baseline"), pytest.param(SINGLE_HITS_TABLE, None, id="single"),
                pytest.param(MODELS_XGB_TABLE, None, id="xgb"),
                pytest.param(BASELINE_TABLE, RES_TWO, id="two-shower-fixture")]


def _res_fixture(kind, estimator=DEFAULT_ESTIMATOR):
    """The recorded response of one kind (`two`, `xgb`, `single_hits`, `single_events`) under one estimator."""
    stem = f"res_scaling_{kind}" if estimator == "sample" else f"res_scaling_{estimator}_{kind}"
    return PAYLOADS / f"{stem}.json"


def _fixture_payload(kind, estimator=DEFAULT_ESTIMATOR):
    return json.loads(_res_fixture(kind, estimator).read_text(encoding="utf-8"))


def _serve_res_fixture(page, kind):
    """Answer the page's /api/resolution-scaling with the recorded response of `kind` for the estimator the request
    names; the request is still made and counted. A request naming no estimator, or another one, is answered 422,
    so it shows in the page's problems."""
    _serve_res_bodies(page, {est: _res_fixture(kind, est).read_text(encoding="utf-8") for est in RES_ESTIMATORS})


def _serve_res_bodies(page, bodies):
    """Answer the page's /api/resolution-scaling with `bodies[estimator]` (JSON text), as `_serve_res_fixture` does;
    an estimator with no body is answered 422."""

    def answer(route):
        asked = parse_qs(urlparse(route.request.url).query).get("estimator", [None])[0]
        if asked in bodies:
            route.fulfill(status=200, content_type="application/json", body=bodies[asked])
        else:
            route.fulfill(status=422, content_type="application/json",
                          body=json.dumps({"detail": f"the test serves no estimator {asked!r}"}))

    page.route("**/api/resolution-scaling?*", answer)


@pytest.mark.parametrize(("table", "fixture"), E_VIEW_CASES)
def test_the_resolution_cards_e_view_draws_two_grids_and_switches_back_without_a_request(models_live_server, table,
                                                                                         fixture):
    """The res-scaling card's second view (brief §8; CLAUDE.md §5 "Its second view: E (GeV) + ratio").

    "1/√E linear | E (GeV) + ratio" repaints the one response: no request on the view, the windows or the "Ratio
    to" switch. The E view stacks two grids on one E axis 0 → `axis.energy.x.max` (the top one's labels hidden, a
    crosshair linked across both, no axis-trigger tooltip); σ/E from 0 to `axis.energy.y.hi`; one fitted curve per
    series and panel with no band (Martin's directive of 2026-11-15), solid over its fitted windows and dashed
    beyond, a/√E ⊕ b ⊕ c/E from 0 GeV or else a₀/√E from 4 GeV, the fit table's Fit cells naming the one drawn and
    a/√E ⊕ b only tabled (res-noise); a log ratio axis symmetric about 1 (min · max =
    1). The title names the view, the plot is 600 px tall (420 px in the 1/√E view), its export holds both grids,
    and every tooltip over either grid keeps to the 20% rule. Back in the 1/√E view the axes, the series and the
    fit table are exactly what they were. The baseline's two events draw the E view's empty state; the recorded
    two-shower response draws both showers, and A / B / Both repaint the E view with no request.

    The card opens on the E view with the deposit hidden and E max at the data's edge (res-emax, Martin's decisions
    of 2026-11-17; their own tests below). This test reads the views with the deposit on and, in the E view, E max
    at the server's end (the slider's upper end), so every mark these checks read is drawn over the server's axis:
    the deposit and E max set first, then the 1/√E view as the picture to come back to."""
    base = models_live_server["base"]
    drawn = fixture is not None or table in RES_DRAWN
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, table)
        if fixture is not None:
            _serve_res_fixture(page, fixture)
        page.evaluate(_WATCH_EXPORT_GRIDS)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        asked = _requests_of(requests, "/api/resolution-scaling")
        assert len(asked) == 1, _urls(requests)
        assert asked[0].get("estimator") == DEFAULT_ESTIMATOR, asked
        payload = _fixture_payload(fixture) if fixture else _res_payload(base, asked[0])
        assert payload["estimator"]["name"] == DEFAULT_ESTIMATOR, payload["estimator"]
        energy = payload["axis"]["energy"]
        # The deposit on (a forced one is already), then the 1/√E view: the picture the switch back must return.
        assert _res_deposit(page, True)
        assert _res_press(page, "res-view", "linear")
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        axes, fit, series = page.evaluate(_RES_AXES), page.evaluate(_RES_TABLE), page.evaluate(_RES_SERIES)
        linear = page.evaluate(_RES_CHROME)
        # Under the default median the card plots a median relative error, never called a resolution (brief §4).
        assert linear["title"] == "Median Relative Error vs. 1/√E", linear
        assert linear["height"] == 420 and linear["styleHeight"] == "", linear
        assert [v for v, _ in linear["views"]] == ["1/√E linear", "E (GeV) + ratio"], linear
        assert linear["views"][0][1] == "true" and linear["references"] == [] and linear["literature"] == [], linear
        # The E max slider is the E view's alone: hidden here.
        assert page.evaluate(_RES_EMAX_STATE, RES_EMAX)["shown"] is False
        before = len(requests)

        # The toggle: the E view from the response in hand; E max at the server's end, a repaint too.
        assert _res_press(page, "res-view", "energy")
        _set_emax(page, energy["x"]["max"])
        emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
        assert emax["shown"] and float(emax["value"]) == energy["x"]["max"], emax
        chrome = page.evaluate(_RES_CHROME)
        assert chrome["title"] == "Median Relative Error vs. E", chrome
        # 600 px for the two panels; an empty state keeps the card's 420 px (the review's U-F11).
        if drawn:
            assert chrome["height"] == 600 and chrome["styleHeight"] == "600px", chrome
        else:
            assert chrome["height"] == 420 and chrome["styleHeight"] == "", chrome
        assert [w for w, _ in chrome["windows"]] == ["3 anchors", "All windows"], chrome
        # One pair of literature toggles (Martin, 2026-11-11), both on by default; no separate reference buttons.
        assert chrome["references"] == [] and chrome["literature"] == [["π±", "true"], ["e±", "true"]], chrome
        title, headings, _ = _drawer(page, "res-scaling")
        assert title == "Median Relative Error vs. E", title
        _assert_sections(headings, f"{table} res-scaling (E view)")
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)

        if not drawn:
            # Two events hold no window of two events: the E view's empty state, said on the chart.
            assert page.evaluate(_CARD, "res-scaling")["series"] == 0
            texts = page.evaluate(_CHART_TEXTS, "plot-res-scaling")
            assert any("no median rel. can be drawn" in t for t in texts), texts
        else:
            # The default draws both curves; the ratio divides by the farther one (e± on every stored response, whose
            # windows all lie above both curves), and the other is drawn on the ratio panel divided by it.
            lit_ids = lambda got: sorted(i for i in got["ids"] if i.startswith("literature|")
                                         and not i.endswith("endlabels") and not i.endswith("caret"))
            both = page.evaluate(_RES_ENERGY)
            ref = "e" if "e±" in both["y"][1]["name"] else "pi"
            other = "pi" if ref == "e" else "e"
            assert lit_ids(both) == sorted(["literature|pi", "literature|e", f"literature|{other}|ratio"]), both["ids"]
            assert ({"pi": "π±", "e": "e±"}[ref] in both["y"][1]["name"]
                    and {"pi": "π±", "e": "e±"}[other] not in both["y"][1]["name"]), both["y"][1]
            flagged = page.evaluate(_DETAILS, "res-scaling")
            assert flagged["flagged"] and NO_INTERVAL in flagged["title"], flagged
            name, _ = _download_svg(page, "res-scaling")
            # The E view's tokens (res-emax): the axis end right after `energy`, the deposit on (no deposit-off).
            assert f"_energy_emax-{round(energy['x']['max'])}_lit-pi-e_est-median_" in name, name
            # Both off: each shower's deposit fit is the reference, as the checks below take it.
            assert not _res_press(page, "res-literature", "pi") and not _res_press(page, "res-literature", "e")
            assert [t[:3] for t in page.evaluate(_RES_LIT_TOGGLES)] == [["π±", "false", False], ["e±", "false", False]]
            view = page.evaluate(_RES_ENERGY)
            # Two grids, the main panel over the ratio panel, on one E axis.
            assert view["grids"] == 2 and len(view["rects"]) == 2, view["rects"]
            main, ratio = view["rects"]
            assert (main["left"], main["right"]) == (ratio["left"], ratio["right"]), view["rects"]
            assert ratio["top"] >= main["bottom"], view["rects"]
            assert [a["gridIndex"] for a in view["x"]] == [0, 1], view["x"]
            # E max at the server's end: the server's axis and interval (res_axis.js eAxisTicks at serverMax).
            assert {(a["min"], a["max"], a["interval"]) for a in view["x"]} == \
                {(0, energy["x"]["max"], energy["x"]["interval"])}, (view["x"], energy["x"])
            assert energy["x"]["max"] >= 80, energy["x"]
            top, bottom = view["x"]
            assert not top["labels"] and top["name"] == "", top
            assert bottom["labels"] and bottom["name"] == energy["x"]["name"] == "Energy E [GeV]", bottom
            # The crosshair: linked across both grids, never a tooltip trigger, its E label on the bottom axis.
            assert view["link"] == [[{"xAxisIndex": "all"}]], view["link"]
            for a in view["x"]:
                assert a["pointer"]["type"] == "line" and a["pointer"]["triggerTooltip"] is False, a
            assert (top["pointer"]["label"], bottom["pointer"]["label"]) == (False, True), view["x"]
            # σ/E from zero to the server's E-view range.
            y_main, y_ratio = view["y"]
            assert y_main["gridIndex"] == 0 and y_main["type"] == "value", y_main
            assert y_main["min"] == 0 and y_main["max"] == energy["y"]["hi"], (y_main, energy["y"])
            # The ratio axis: log, [1/k, k], so 1 is its geometric centre; its ticks symmetric about 1.
            assert y_ratio["gridIndex"] == 1 and y_ratio["type"] == "log", y_ratio
            assert y_ratio["min"] * y_ratio["max"] == pytest.approx(1, abs=1e-12) and y_ratio["max"] > 1, y_ratio
            assert 1 in y_ratio["ticks"], y_ratio
            assert sorted(y_ratio["ticks"]) == pytest.approx(sorted(1 / t for t in y_ratio["ticks"])), y_ratio
            assert "deposit fit" in y_ratio["name"], y_ratio
            forms = _assert_e_view_curves(view, payload, "anchors")
            assert forms, view["curves"].keys()
            assert any("|dashed|" in c for c in view["curves"]), "no extrapolated part drawn"
            # The fit table names what this view draws (panels/resolution_scaling.js energyTableName).
            table_e = page.evaluate(_RES_TABLE)
            assert any(f.startswith("Affine a/√E + b — drawn in the 1/√E view") for f in table_e["fits"]), table_e
            # a/√E ⊕ b is tabled on this view (res-noise §4.4).
            assert any(f.startswith("Quadrature a/√E ⊕ b — table only") for f in table_e["fits"]), table_e
            assert not any(f.startswith("Quadrature a/√E ⊕ b — drawn") for f in table_e["fits"]), table_e
            # One curve per series (Martin's directive of 2026-11-15): the Fit cells name the one drawn, a/√E ⊕ b ⊕ c/E
            # where drawable, else a₀/√E; beside a drawn a/√E ⊕ b ⊕ c/E, a₀/√E is table only. Four rows per series.
            # Each cell, series by series, as `energyTableName` writes it (review-ui F2 and fa85fe8): a missing fit
            # from 4 GeV gives its true cause (`_fit_missing_reason`) in the a₀/√E cell, and the affine and
            # quadrature cells say "— not fitted: <the same cause>"; a₀/√E is "table only" only beside a drawn
            # a/√E ⊕ b ⊕ c/E. The cells come in series order, four per series.
            forms = [_drawn_form(s["fits"]["anchors"]) for s in payload["series"]]
            cells = table_e["fits"]
            assert len([f for f in cells if f.startswith("Origin-pinned a₀/√E ⊕ 0 — ")]) == len(forms), cells
            assert cells.count("a/√E ⊕ b ⊕ c/E — drawn") == forms.count("noise"), (cells, forms)
            assert cells.count("Origin-pinned a₀/√E ⊕ 0 — drawn: no a/√E ⊕ b ⊕ c/E fit") == forms.count("pinned"), \
                (cells, forms)
            assert len([f for f in cells if f.startswith("a/√E ⊕ b ⊕ c/E — not drawn: ")]) == \
                len(forms) - forms.count("noise"), cells
            pinned_cells = [f for f in cells if f.startswith("Origin-pinned a₀/√E ⊕ 0 — ")]
            affine_cells = [f for f in cells if f.startswith("Affine a/√E + b — ")]
            quad_cells = [f for f in cells if f.startswith("Quadrature a/√E ⊕ b — ")]
            assert len(affine_cells) == len(quad_cells) == len(forms), cells
            for s, form, pinned, affine, quad in zip(payload["series"], forms, pinned_cells, affine_cells, quad_cells):
                mf = s["fits"]["anchors"]
                reasons = _fit_missing_reason(payload, s, "anchors")
                if mf.get("pinned") is None or mf["pinned"]["params"].get("a0") is None:
                    assert any(pinned == f"Origin-pinned a₀/√E ⊕ 0 — not drawn: {r}" for r in reasons), \
                        (s["key"], pinned, reasons)
                elif form == "noise":
                    assert pinned == "Origin-pinned a₀/√E ⊕ 0 — table only on this view", (s["key"], pinned)
                if mf.get("affine") is None:
                    assert any(affine == f"Affine a/√E + b — not fitted: {r}" for r in reasons), (s["key"], affine)
                else:
                    assert affine == "Affine a/√E + b — drawn in the 1/√E view", (s["key"], affine)
                if mf.get("quadrature") is None:
                    assert any(quad == f"Quadrature a/√E ⊕ b — not fitted: {r}" for r in reasons), (s["key"], quad)
                else:
                    assert quad.startswith("Quadrature a/√E ⊕ b — table only"), (s["key"], quad)
            e_series = page.evaluate(_RES_SERIES)

            # Every window, then the anchors again: a repaint, and the curves keep the rules.
            assert _res_press(page, "res-windows", "all")
            assert page.evaluate(_RES_SERIES) != e_series
            _assert_e_view_curves(page.evaluate(_RES_ENERGY), payload, "all")
            assert _res_press(page, "res-windows", "anchors")
            assert page.evaluate(_RES_SERIES) == e_series

            # One curve on: it is drawn and the ratio divides by it; off again, back to the deposit fit, which draws none.
            assert not [i for i in view["ids"] if i.startswith("literature|")], view["ids"]
            details = page.evaluate(_DETAILS, "res-scaling")
            for key, particle in (("pi", "π±"), ("e", "e±")):
                assert _res_press(page, "res-literature", key)
                got = page.evaluate(_RES_ENERGY)
                # Only the chosen curve is drawn: its line, and any end label or caret, are its own.
                assert f"literature|{key}" in got["ids"], got["ids"]
                assert {i.split("|")[1] for i in got["ids"] if i.startswith("literature|")} == {key}, got["ids"]
                assert particle in got["y"][1]["name"], got["y"][1]
                assert got["y"][1]["min"] * got["y"][1]["max"] == pytest.approx(1, abs=1e-12), got["y"][1]
                # The main panel and its curves do not move: only the ratio panel and the literature curve do.
                assert got["y"][0] == y_main and got["x"] == view["x"], (got["y"][0], y_main)
                now, then = _main_curves(got), _main_curves(view)
                assert now.keys() == then.keys(), (key, now.keys() ^ then.keys())
                assert all(now[c] == pytest.approx(then[c], abs=E_TOL) for c in now), key
                _assert_e_view_curves(got, payload, "anchors")
                # A literature reference is a documented point estimate: the Details button carries the hazard.
                flagged = page.evaluate(_DETAILS, "res-scaling")
                assert flagged["flagged"] and NO_INTERVAL in flagged["title"], flagged
                assert not _res_press(page, "res-literature", key)
            assert page.evaluate(_RES_SERIES) == e_series
            assert page.evaluate(_DETAILS, "res-scaling") == details, details

            # Both on again: exactly the default picture, the farther curve the reference; then both off for the rest.
            assert _res_press(page, "res-literature", "pi") and _res_press(page, "res-literature", "e")
            again = page.evaluate(_RES_ENERGY)
            assert lit_ids(again) == lit_ids(both) and again["y"][1]["name"] == both["y"][1]["name"], again["ids"]
            assert not _res_press(page, "res-literature", "pi") and not _res_press(page, "res-literature", "e")
            assert page.evaluate(_RES_SERIES) == e_series

            showers = sorted({s["shower"] for s in payload["series"]})
            if len(showers) > 1:
                # Two showers (brief §1): A filled, B hollow (filled with the card's ground, stroked in its colour);
                # B's lines at 70% strength and never dashed for the shower (the dash means extrapolation here).
                card = {f for k, m in view["markers"].items() if ":b|" in k and "|ratio|" not in k for f in m["fills"]}
                assert len(card) == 1, view["markers"]
                for k, m in view["markers"].items():
                    if ":a|" in k:
                        assert card.isdisjoint(m["fills"]) and card <= set(m["strokes"]), (k, m, card)
                    else:
                        assert card.isdisjoint(m["strokes"]), (k, m, card)
                for cid, curve in view["curves"].items():
                    key, form = cid.split("|")[0], cid.split("|")[-3]
                    fitted = next(s for s in payload["series"] if s["key"] == key)["fits"]["anchors"][form]
                    if key.endswith(":b"):
                        assert curve["opacity"] < 1, (cid, curve["opacity"])
                    elif not fitted["provisional"] and not fitted.get("misfit"):
                        # Shower A at full strength, unless the fit is provisional or a misfit (S > 5, drawn faded:
                        # the median's deposit pinned fits are, on the recorded two-shower response).
                        assert curve["opacity"] == 1, (cid, curve["opacity"])
                # A / B / Both repaint the E view from the response in hand.
                for shower in ("a", "b"):
                    assert _res_press(page, "models-shower", shower), shower
                    got = page.evaluate(_RES_ENERGY)
                    keys = {i.split("|")[0] for i in got["ids"] if ":" in i.split("|")[0]}
                    assert keys and {k.split(":")[1] for k in keys} == {shower}, (shower, keys)
                    assert got["x"] == view["x"] and got["y"][0] == y_main, shower
                    _assert_e_view_curves(got, payload, "anchors")
                assert _res_press(page, "models-shower", "both")
                assert page.evaluate(_RES_SERIES) == e_series

            # With both curves off the ratio panel divides each shower's windows by its deposit's a/√E ⊕ b ⊕ c/E
            # fit, else its a₀/√E fit (res-noise §4.2), so a shower whose deposit has neither in this mode has no
            # ratio marks. Under the default median the recorded two-shower deposits tie (every bootstrap replicate
            # the same value, SE below 10⁻⁶ of it): they carry no fit weight and no fit of either form (review-ui M1;
            # their noise_reason says so), and that panel holds nothing to read.
            fitted = {s["shower"] for s in payload["series"]
                      if s["source"] == "detector" and (s["fits"]["anchors"]["noise"] or s["fits"]["anchors"]["pinned"])}
            marked = {k.split("|")[0].split(":")[1] for k, m in view["markers"].items()
                      if k.endswith("|ratio|markers") and m["fills"]}
            assert marked == fitted, (marked, fitted)
            # The tooltips are read on the default picture, both curves on: a literature reference is drawn under
            # every estimator, so every series on show has ratio marks to hover.
            assert _res_press(page, "res-literature", "pi") and _res_press(page, "res-literature", "e")
            assert lit_ids(page.evaluate(_RES_ENERGY)) == lit_ids(both)
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)

            # Tooltips over both grids: on the layer, beside or off the plot, none over more than the cap.
            found = _hover_chart(page, "plot-res-scaling", columns=12, rows=10)
            found += _hover_marks(page, "plot-res-scaling", cap=60)
            _check_tips(found, f"{table} res-scaling (E view)")
            chart = page.evaluate(_BOXES, "plot-res-scaling")["chart"]
            grids = [{k: v + (chart["left"] if k in ("left", "right") else chart["top"]) for k, v in r.items()}
                     for r in view["rects"]]
            on_grid, worst = [0, 0], [0.0, 0.0]
            for (x, y), probe, boxes in found:
                plot = boxes["plot"]
                area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
                assert _overlap(probe["tip"], plot) / area <= PROJECTION_READOUT_SHARE, (table, (x, y), probe["text"][:60])
                for i, g in enumerate(grids):
                    if _within((x, y), g):
                        on_grid[i] += 1
                        # The grid being read, alone: the ratio panel is a quarter of the plot, so a tip the
                        # union's cap allows could still hide it.
                        share = _overlap(probe["tip"], g) / ((g["right"] - g["left"]) * (g["bottom"] - g["top"]))
                        worst[i] = max(worst[i], share)
                        assert share <= PROJECTION_READOUT_SHARE, (table, i, (x, y), probe["text"][:60], share)
            assert all(on_grid), f"{table}: tooltips on the main and ratio grids: {on_grid}"
            print(f"res-scaling E view, {table}: tooltips on the main / ratio grid {on_grid}, "
                  f"largest share of the grid read {[round(w, 3) for w in worst]}")
            texts = [probe["text"] for _, probe, _ in found]
            assert any("plotted at E = 1/⟨1/√p⟩²" in t for t in texts), texts[:5]
            assert any("conditional on" in t for t in texts), texts[:5]
            assert _hyphen_negatives(texts) == [], _hyphen_negatives(texts)

            # The export: the plot alone, both grids, on one E axis, taller than the 1/√E view's figure.
            name, svg = _download_svg(page, "res-scaling")
            shape = page.evaluate("() => window.__exportShapes.at(-1)")
            assert name.startswith("res-scaling_") and name.endswith(".svg"), name
            assert shape["grids"] == 2, shape
            assert [x[0] for x in shape["x"]] == [0, 1] and {tuple(x[1:]) for x in shape["x"]} == {(0, energy["x"]["max"])}, shape
            assert shape["y"][1][1] == "log" and shape["y"][1][2] * shape["y"][1][3] == pytest.approx(1, abs=1e-12), shape
            svg_texts = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
            assert "Energy E [GeV]" in svg_texts, svg_texts
            assert not [t for t in svg_texts if "1/√E" in t and "/√E ⊕" not in t], svg_texts
            assert not [t for t in svg_texts if "Windows fitted" in t or "SE(a" in t], svg_texts
            assert re.search(r'<rect[^>]*fill="#FFFFFF"', svg) and "figure-disclosure" not in svg
            assert _hyphen_negatives(svg_texts) == [], _hyphen_negatives(svg_texts)

        # Back to the 1/√E view: exactly the picture and the table it was.
        assert _res_press(page, "res-view", "linear")
        back = page.evaluate(_RES_CHROME)
        assert back["title"] == linear["title"] and back["height"] == 420 and back["styleHeight"] == "", back
        assert back["references"] == [] and back["windows"] == linear["windows"], back
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        assert page.evaluate(_RES_AXES) == axes
        assert page.evaluate(_RES_SERIES) == series
        assert page.evaluate(_RES_TABLE) == fit
        if drawn:
            _download_svg(page, "res-scaling")
            linear_shape = page.evaluate("() => window.__exportShapes.at(-1)")
            assert linear_shape["width"] == shape["width"] and linear_shape["height"] < shape["height"], (linear_shape, shape)
            assert linear_shape["grids"] == 1, linear_shape
        assert requests[before:] == [], f"a render-only control asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


# ------------------------------------------------ the resolution card's estimator --

#: The card's toolbar groups in page order (models_cards.js CARD_CONTROLS['res-scaling'], brief §4): each group's
#: label, whether it is on show, and its buttons as [text, aria-pressed, title].
_RES_CONTROLS = """() => {
  const card = document.querySelector('.main .card[data-panel="res-scaling"]');
  return [...card.querySelectorAll('.seg[role="group"]')].map((g) => ({
    label: g.getAttribute('aria-label'), shown: !g.closest('[hidden]'),
    buttons: [...g.querySelectorAll('button')].map((b) => [b.textContent, b.getAttribute('aria-pressed'), b.title]),
  }));
}"""

#: The button groups in the brief's order: View, Estimator, Windows, Shower, Deposit (the "Benchmark" group,
#: res-emax brief §6.2), Literature; the E max slider follows them, a `label.mini-range`, not a group.
RES_CONTROL_LABELS = ["View", "Estimator", "Windows", "Showers", "Benchmark", "Literature curves"]
#: The Estimator buttons, verbatim from brief §4 (labels.js MODELS_LABELS.res_estimator).
RES_ESTIMATOR_BUTTONS = {
    "median": ("Median |rel. err.|",
               "median |E_est − p| / p per window: the Median rel. of Model Error vs. Incident Momentum, same events, "
               "seed and interval. Not a σ: for unbiased Gaussian errors it is 0.6745·σ/E."),
    "robust": ("Robust σ (IQR)",
               "IQR(R) / (1.349 · median R), R = E_est / p: a σ-consistent width that a few badly reconstructed events "
               "cannot inflate; the σ-scaled comparison with the π± and e± curves."),
    "sample": ("Sample σ/μ",
               "s(R) / R̄ over every event of the window, tails included: the Physics page resolution card's "
               "estimator."),
}
#: The View buttons, verbatim (labels.js MODELS_LABELS.res_view): the E view's title names one fitted curve per
#: series with no band (Martin's directive of 2026-11-15; review-ui F1, 19f6ab2).
RES_VIEW_BUTTONS = {
    "linear": ("1/√E linear",
               "The error scale against a reversed 1/√E axis: a pure stochastic term is a straight line into the origin"),
    "energy": ("E (GeV) + ratio",
               "The error scale against the energy in GeV: one fitted curve per series, its a/√E ⊕ b ⊕ c/E from 0 GeV "
               "(a₀/√E from 4 GeV where a series has none), solid over its windows and dashed beyond, with no band; and "
               "a ratio panel"),
}
#: The card's title per estimator and view (brief §4 `cardTitle`): a median relative error is not a resolution.
RES_TITLES = {
    "median": {"linear": "Median Relative Error vs. 1/√E", "energy": "Median Relative Error vs. E"},
    "robust": {"linear": "Energy Resolution vs. 1/√E", "energy": "Energy Resolution vs. E"},
    "sample": {"linear": "Energy Resolution vs. 1/√E", "energy": "Energy Resolution vs. E"},
}
#: The literature disclosure, verbatim from brief §2.7 (resolution_scaling.py LITERATURE_WARNING), with its U+2212.
LITERATURE_WARNING = ("Note: comparing Median |rel. err.| against a σ/E literature curve (for unbiased Gaussian "
                      "errors, median|R − 1| = 0.6745·σ/E; use Robust σ (IQR) for a σ-scaled comparison).")
#: The hazard the Details button carries with it (brief §4, models_notes.js modelsHazards).
MEDIAN_HAZARD = "median rel. against σ/E curve"
#: How a window tooltip's value line opens under each estimator (brief §4, "Tooltip value line").
VALUE_LINE = {"median": "Median rel. = ", "robust": "Robust σ/E = ", "sample": "σ/E = "}
#: The two estimators a window tooltip names as not plotted, by the words it uses for them (brief §4).
CROSS_REFERENCES = {"median": ("Robust σ/E", "sample σ/μ"), "robust": ("sample σ/μ", "median rel."),
                    "sample": ("Robust σ/E", "median rel.")}


def _flat(text):
    """Text with every run of white space made one space: a canvas note wraps at spaces, a drawer at its width."""
    return " ".join(text.split())


def _res_note(page):
    """Every text the resolution card's chart states (the note band, an empty state), flattened into one line."""
    return _flat(" ".join(page.evaluate(_CHART_TEXTS, "plot-res-scaling")))


def _res_pressed(page):
    """{group label: [pressed buttons' texts]} of the resolution card's toolbar."""
    return {g["label"]: [text for text, pressed, _ in g["buttons"] if pressed == "true"]
            for g in page.evaluate(_RES_CONTROLS)}


def _res_ids(page):
    return page.evaluate("""() => (echarts.getInstanceByDom(document.getElementById('plot-res-scaling'))
      .getOption().series || []).map((s) => s.id ?? s.name)""")


def _literature_drawn(page):
    """The literature curves drawn on the main panel: their keys."""
    return sorted(i.split("|")[1] for i in _res_ids(page) if re.fullmatch(r"literature\|[a-z]+", i))


def _res_y_name(page):
    return page.evaluate("""() => (echarts.getInstanceByDom(document.getElementById('plot-res-scaling'))
      .getOption().yAxis || [])[0]?.name ?? ''""")


def _res_estimator(page, requests, estimator, axis_name, *, asks=1):
    """Press an Estimator button the card is not on; wait for the card to draw that estimator's response (its y axis
    named by the estimator, brief §3). A first switch to an estimator sends exactly one request, whose query is
    returned; a switch back to one already loaded (`asks=0`) is answered from the cards' shared response cache
    (models_cards.js `fetchShared`, as every Models card is) and sends none."""
    count = len(_requests_of(requests, "/api/resolution-scaling"))
    page.locator(f'.main .card[data-panel="res-scaling"] button[data-res-estimator="{estimator}"]').click()
    if asks:
        _until(page, lambda: len(_requests_of(requests, "/api/resolution-scaling")) > count,
               f"the {estimator} request")
    page.wait_for_function(
        """(name) => { const card = document.querySelector('.main .card[data-panel="res-scaling"]');
          const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
          return !card.classList.contains('is-loading')
            && String((inst?.getOption().yAxis || [])[0]?.name ?? '').startsWith(name); }""",
        arg=axis_name, timeout=30_000)
    _frames(page, 4)
    new = _requests_of(requests, "/api/resolution-scaling")[count:]
    assert len(new) == asks, f"the {estimator} switch asked {len(new)} times, not {asks}: {new}"
    return new[0] if new else None


def _without(query, *keys):
    return {k: v for k, v in query.items() if k not in keys}


def test_the_estimator_control_reloads_the_card_once_and_keeps_every_other_choice(models_live_server):
    """The res-scaling card's Estimator control (Martin's decision 1 of 2026-11-12; brief §4), on the recorded
    two-shower responses served by the request's estimator.

    The toolbar reads View, Estimator, Windows, Shower, Literature; the Estimator offers Median |rel. err.|, Robust σ
    (IQR) and Sample σ/μ, with the brief's titles, Median pressed at open and on the first request. A switch to an
    estimator not yet loaded sends exactly one /api/resolution-scaling request, carrying the new estimator and
    otherwise the request it replaces; a switch back is answered from the cards' shared response cache with none.
    Every switch keeps the view, the windows mode, the shower and the literature toggles as the reader left them,
    and the estimator never enters the link. The title follows the estimator in both views, the y axis takes the estimator's name, and a
    figure exported under each estimator carries est-<name> in its file name."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        first = _requests_of(requests, "/api/resolution-scaling")
        assert len(first) == 1 and first[0].get("estimator") == DEFAULT_ESTIMATOR, first
        # The card opens on the E view (res-emax, Martin's decisions of 2026-11-17).
        assert state["title"] == RES_TITLES["median"]["energy"], state

        controls = page.evaluate(_RES_CONTROLS)
        assert [g["label"] for g in controls] == RES_CONTROL_LABELS, controls
        estimator = next(g for g in controls if g["label"] == "Estimator")
        assert estimator["shown"], estimator
        assert estimator["buttons"] == [[label, "true" if value == DEFAULT_ESTIMATOR else "false", title]
                                        for value, (label, title) in RES_ESTIMATOR_BUTTONS.items()], estimator
        assert [page.get_attribute(f'.main .card[data-panel="res-scaling"] .seg[aria-label="Estimator"] '
                                   f'button:nth-child({i + 1})', "data-res-estimator")
                for i in range(3)] == list(RES_ESTIMATORS)
        # The View buttons and their titles (labels.js res_view; the E view's title says one curve per series and
        # no band, review-ui F1, 19f6ab2), the E view pressed at open (res-emax).
        view = next(g for g in controls if g["label"] == "View")
        assert view["buttons"] == [[label, "true" if value == "energy" else "false", title]
                                   for value, (label, title) in RES_VIEW_BUTTONS.items()], view
        # The Deposit toggle: one button, not pressed at open, its title verbatim (labels.js res_deposit).
        deposit = next(g for g in controls if g["label"] == "Benchmark")
        assert deposit["shown"] and deposit["buttons"] == [["Deposit", "false", RES_DEPOSIT_TITLE]], deposit
        # The literature toggles' titles: the equation without a % sign, its units beside it (c406217).
        assert [[t[0], t[3]] for t in page.evaluate(_RES_LIT_TOGGLES)] == \
            [[LITERATURE[key][0], LITERATURE_TITLE[key]] for key in ("pi", "e")]

        # The reader's other choices, none of them the defaults: every window, shower B, the deposit on, e± alone,
        # E max at 45 GeV (the E view, the default, pressed again changes nothing).
        before = len(requests)
        assert _res_press(page, "res-view", "energy")
        assert _res_press(page, "res-windows", "all")
        assert _res_press(page, "models-shower", "b")
        assert _res_deposit(page, True)
        assert not _res_press(page, "res-literature", "pi")
        _set_emax(page, 45)
        assert requests[before:] == [], f"a render-only control asked the service: {requests[before:]}"
        kept = {k: v for k, v in _res_pressed(page).items() if k != "Estimator"}
        assert kept == {"View": ["E (GeV) + ratio"], "Windows": ["All windows"], "Showers": ["B"],
                        "Benchmark": ["Deposit"], "Literature curves": ["e±"]}, kept
        assert page.evaluate(_RES_EMAX_STATE, RES_EMAX)["output"] == "45 GeV"
        assert _literature_drawn(page) == ["e"]
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)

        exported = {}
        # Robust and sample are asked once each; the median, loaded at open, and robust again come from the cache.
        for est, asks in (("robust", 1), ("sample", 1), ("median", 0), ("robust", 0)):
            served = _fixture_payload(RES_TWO, est)
            asked = _res_estimator(page, requests, est, served["estimator"]["axis_name"], asks=asks)
            where = f"switched to {est}"
            if asks:
                assert asked.get("estimator") == est, (where, asked)
                assert _without(asked, "estimator") == _without(first[0], "estimator"), (where, asked, first[0])
            pressed = _res_pressed(page)
            assert pressed["Estimator"] == [RES_ESTIMATOR_BUTTONS[est][0]], (where, pressed)
            assert {k: v for k, v in pressed.items() if k != "Estimator"} == kept, (where, pressed)
            # E max as the reader left it, on the new response's slider too (its range is the same 20–80 GeV).
            assert page.evaluate(_RES_EMAX_STATE, RES_EMAX)["output"] == "45 GeV", where
            # The literature toggle the reader left: e± alone is drawn, under every estimator.
            assert _literature_drawn(page) == ["e"], (where, _res_ids(page))
            assert _res_y_name(page).startswith(served["axis"]["energy"]["y"]["name"]), (where, _res_y_name(page))
            assert page.evaluate(_RES_CHROME)["title"] == RES_TITLES[est]["energy"], where
            assert not {"estimator", "resEstimator", "res_estimator"} & set(_hash(page)), (where, _hash(page))
            assert not {"resDeposit", "resEMax", "res_deposit", "res_emax", "emax"} & set(_hash(page)), \
                (where, _hash(page))
            name, _ = _download_svg(page, "res-scaling")
            assert name.startswith("res-scaling_") and "_energy_emax-45_ratio-e_" in name, (where, name)
            assert "deposit-off" not in name, (where, name)
            assert re.search(rf"_est-{est}_\d{{8}}_\d{{6}}\.svg$", name), (where, name)
            exported.setdefault((est, "energy"), name)
            # The 1/√E view of the same response: its title, its axis name and its export, with no request.
            count = len(requests)
            assert _res_press(page, "res-view", "linear")
            assert page.evaluate(_RES_CHROME)["title"] == RES_TITLES[est]["linear"], where
            assert _res_y_name(page).startswith(served["axis"]["y"]["name"]), (where, _res_y_name(page))
            name, _ = _download_svg(page, "res-scaling")
            assert name.startswith("res-scaling_") and "_energy" not in name, (where, name)
            assert re.search(rf"_est-{est}_\d{{8}}_\d{{6}}\.svg$", name), (where, name)
            exported.setdefault((est, "linear"), name)
            assert _res_press(page, "res-view", "energy")
            assert requests[count:] == [], f"{where}: the view asked the service: {requests[count:]}"
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)
        print(f"res-scaling export names: {exported}")
        # One request per estimator in all: the median's at open, robust's and sample's on their first switch.
        assert [q.get("estimator") for q in _requests_of(requests, "/api/resolution-scaling")] == \
            ["median", "robust", "sample"], _urls(requests)
        browser.close()
    assert problems == [], problems


def test_the_median_estimator_discloses_its_comparison_with_the_literature_curves(models_live_server):
    """Martin's override (brief §1 decision 2, §2.7, §4): the literature curves stay on under every estimator, and
    under the median, in the E view with a curve on, the comparison is disclosed.

    Median, E view, both curves on (the default): both curves are drawn; the note band shows the verbatim
    disclosure; the Details button is flagged and names the hazard "median rel. against σ/E curve" beside "no
    interval reported"; the drawer states the disclosure. Under Robust σ (IQR) the curves stay, the disclosure and
    that hazard go. Back under the median, both curves switched off take the disclosure and the hazards with them,
    and one curve on brings them back. The 1/√E view, which draws no curve, carries neither."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state

        def disclosed(where, *, warning, hazard, no_interval):
            note = _res_note(page)
            assert (LITERATURE_WARNING in note) is warning, (where, note[-400:])
            details = page.evaluate(_DETAILS, "res-scaling")
            assert (MEDIAN_HAZARD in details["title"]) is hazard, (where, details)
            assert (NO_INTERVAL in details["title"]) is no_interval, (where, details)
            if hazard or no_interval:
                assert details["flagged"], (where, details)
            _, _, body = _drawer(page, "res-scaling")
            assert (LITERATURE_WARNING in _flat(body)) is warning, (where, _flat(body)[:300])
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)
            return details

        # The 1/√E view (pressed: the card opens on the E view, res-emax) draws no curve: nothing to disclose.
        assert _res_press(page, "res-view", "linear")
        assert _literature_drawn(page) == []
        disclosed("median, 1/√E view", warning=False, hazard=False, no_interval=False)

        assert _res_press(page, "res-view", "energy")
        assert [t[:2] for t in page.evaluate(_RES_LIT_TOGGLES)] == [["π±", "true"], ["e±", "true"]]
        assert _literature_drawn(page) == ["e", "pi"]
        details = disclosed("median, E view, both curves", warning=True, hazard=True, no_interval=True)
        # One line of the note band at this width (S2-panel: two lines at 760 px).
        texts = page.evaluate(_CHART_TEXTS, "plot-res-scaling")
        assert any(LITERATURE_WARNING in _flat(t) for t in texts), texts
        print(f"res-scaling, median, E view: Details title {details['title']!r}")

        # Robust σ (IQR): the σ-scaled comparison; the curves stay, the disclosure and its hazard go.
        robust = _fixture_payload(RES_TWO, "robust")
        _res_estimator(page, requests, "robust", robust["estimator"]["axis_name"])
        assert _literature_drawn(page) == ["e", "pi"], _res_ids(page)
        disclosed("robust, E view, both curves", warning=False, hazard=False, no_interval=True)

        # Back under the median: the disclosure comes back; both curves off take it and every hazard with them.
        median = _fixture_payload(RES_TWO, "median")
        _res_estimator(page, requests, "median", median["estimator"]["axis_name"], asks=0)
        disclosed("median again, both curves", warning=True, hazard=True, no_interval=True)
        before = len(requests)
        assert not _res_press(page, "res-literature", "pi") and not _res_press(page, "res-literature", "e")
        assert _literature_drawn(page) == []
        disclosed("median, no curve", warning=False, hazard=False, no_interval=False)
        assert _res_press(page, "res-literature", "pi")
        assert _literature_drawn(page) == ["pi"]
        disclosed("median, π± alone", warning=True, hazard=True, no_interval=True)
        assert requests[before:] == [], f"a literature toggle asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


#: A window tooltip's SE line under the median and the robust estimators (brief-fix F1 and F3, "The tooltip's SE
#: line"): a window whose bootstrap SE is below 10⁻⁶ of its value is tied replicates and carries no fit weight; any
#: other is weighted with its series' one pooled scale c, printed to three significant figures; below 4 GeV, where
#: only a/√E ⊕ b ⊕ c/E uses the window, by the same c, which the line says it does not enter (Martin's directive of
#: 2026-11-15, D3: one pooled scale, no c_low).
SE_TIED = ": below 10⁻⁶ of the value (tied replicates), so no fit weight"
SE_WEIGHTED = re.compile(r"^bootstrap SE \S+ \(κ = [\d.]+%\); fit weight se = c·ŷ/√N, c = ([\d.]+) for this series$")
SE_WEIGHTED_LOW = re.compile(r"^bootstrap SE \S+ \(κ = [\d.]+%\); fit weight se = c·ŷ/√N, c = ([\d.]+) for this "
                             r"series, pooled over its windows from 4 GeV$")
#: A window tooltip's second line: the window and its count.
WINDOW_LINE = re.compile(r"^(\d+–\d+ GeV) · N = ")


def _se_lines(texts, payload, where):
    """Every window tooltip's SE line, checked against the window it names: under the median and the robust
    estimators a tied window (an SE but no κ) says so and no c; every other window prints its series' one pooled
    scale c, one below 4 GeV adding that c is pooled over the windows from 4 GeV (D3), and none names c_low; under
    the sample estimator there is no bootstrap SE line. Returns (tied, weighted, of those weighted the windows below
    4 GeV, the series hovered)."""
    by_label = {s["label"]: s for s in payload["series"]}
    tied, weighted, low, hovered = 0, 0, 0, set()
    for text in texts:
        # The second scale is retired (D3): no tooltip names it, under any estimator.
        assert "c_low" not in text, (where, text[:300])
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        se = [line for line in lines if line.startswith("bootstrap SE ")]
        if payload["estimator"]["name"] == "sample":
            assert se == [], (where, se)
            continue
        if not se:
            continue
        assert len(se) == 1, (where, se)
        s = by_label.get(lines[0])
        label = next((m.group(1) for line in lines[1:3] if (m := WINDOW_LINE.match(line))), None)
        assert s is not None and label is not None, (where, lines[:3])
        w = next(w for w in s["windows"] if w["label"] == label)
        hovered.add(s["key"])
        if w["se_rel"] is None:
            # Tied: never a κ, never a c, never blamed on N.
            assert w["se"] is not None, (where, s["key"], label)
            assert se[0].endswith(SE_TIED) and "κ" not in se[0] and " c = " not in se[0], (where, se[0])
            tied += 1
        elif w["p_lo"] < CURVE_MIN_GEV:
            # Below 4 GeV only a/√E ⊕ b ⊕ c/E fits the window, weighted by the series' one c, which it does not enter.
            assert set(s["weight_scale"]) == {"c", "n_windows", "rule"}, (where, s["key"], s["weight_scale"])
            got = SE_WEIGHTED_LOW.match(se[0])
            assert got, (where, s["key"], label, se[0])
            assert float(got.group(1)) == pytest.approx(s["weight_scale"]["c"], rel=5e-3), \
                (where, s["key"], se[0], s["weight_scale"])
            weighted += 1
            low += 1
        else:
            got = SE_WEIGHTED.match(se[0])
            assert got, (where, s["key"], label, se[0])
            assert float(got.group(1)) == pytest.approx(s["weight_scale"]["c"], rel=5e-3), \
                (where, s["key"], se[0], s["weight_scale"])
            weighted += 1
    return tied, weighted, low, hovered


#: The centre of every window marker the resolution card drew (series `<key>|markers` and `<key>|ratio|markers`), in
#: viewport pixels: the marks `_hover_marks` spreads its cap over every element for, hovered one by one here.
_RES_WINDOW_MARKS = """() => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const out = [];
  inst.getModel().eachSeries((series) => {
    if (!/\\|markers$/.test(series.get('id') || '')) return;
    inst.getViewOfSeriesModel(series).group.traverse((el) => {
      if (el.type !== 'circle' || el.invisible || el.ignore) return;
      // The circle's centre through its current transform (a cached paint rect can still hold the previous
      // render's place while a reused element moves to its new one).
      el.updateTransform();
      const [x, y] = el.transformCoordToGlobal(el.shape.cx ?? 0, el.shape.cy ?? 0);
      out.push([c.left + x, c.top + y]);
    });
  });
  return out.filter(([x, y]) => x > c.left + 1 && x < c.right - 1 && y > c.top + 1 && y < c.bottom - 1);
}"""


def _hover_windows(page):
    """Hover every window marker of the resolution card; every tooltip that showed, probed (as `_hover_marks`)."""
    page.evaluate(_WATCH_HOVER, "plot-res-scaling")
    boxes = page.evaluate(_BOXES, "plot-res-scaling")
    # The marks where they come to rest: a repaint moves a reused element over its update animation.
    marks, waited = page.evaluate(_RES_WINDOW_MARKS), 0
    while waited < 3_000:
        page.wait_for_timeout(100)
        waited += 100
        again = page.evaluate(_RES_WINDOW_MARKS)
        if again == marks:
            break
        marks = again
    found = []
    for x, y in marks:
        page.mouse.move(x, y)
        _frames(page)
        probe = page.evaluate(_PROBE)
        if probe is not None:
            found.append(((x, y), probe, boxes))
    page.mouse.move(2, 2)
    _frames(page)
    return found


@pytest.mark.parametrize("estimator", RES_ESTIMATORS)
def test_the_resolution_tooltips_name_the_estimator_and_keep_to_the_cap(models_live_server, estimator):
    """Every tooltip over the resolution card's windows, curves and ratio marks, under each estimator, in both
    views and both window modes of the recorded two-shower response: on the tooltip layer, beside or off the plot,
    none over more than a fifth of the plot or of the grid being read (the 20% readout cap), with U+2212 for every
    negative number. A window's value line names the estimator's quantity and its cross-references the two not
    plotted (brief §4). Under the median in the E view the literature curves' and the ratio marks' tooltips carry
    the verbatim disclosure (the ratio divides by a literature curve while both are on); no tooltip carries it
    otherwise. The SE line (brief-fix F1, F3; the single-curve round's D3): under the median and the robust estimators
    a weighted window prints "c = … for this series", its series' one pooled scale, and below 4 GeV (the E view's 1–4
    GeV windows) the same c ", pooled over its windows from 4 GeV", never c_low; under the median the recorded
    deposits' tied windows say "below 10⁻⁶ of the value (tied replicates), so no fit weight" and are drawn in the
    all-windows mode only."""
    served = _fixture_payload(RES_TWO, estimator)
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        if estimator != DEFAULT_ESTIMATOR:
            _res_estimator(page, requests, estimator, served["estimator"]["axis_name"])
        # The deposit on (hidden at open since res-emax): its windows' tooltips are among those read.
        assert _res_deposit(page, True)
        shares, counts = {}, {}
        # Each view in both modes; the E view's anchors after its all-windows render, the switch that reuses and
        # moves the markers. Each view pressed: the card opens on the E view.
        for view, mode in (("linear", "anchors"), ("linear", "all"), ("energy", "all"), ("energy", "anchors")):
            assert _res_press(page, "res-view", view)
            assert _res_press(page, "res-windows", mode)
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)
            where = f"res-scaling, {estimator}, {view} view, {mode}"
            found = _hover_chart(page, "plot-res-scaling", columns=12, rows=10)
            found += _hover_marks(page, "plot-res-scaling", cap=60)
            found += _hover_windows(page)
            assert found, f"{where}: no tooltip"
            _check_tips(found, where)
            boxes = page.evaluate(_BOXES, "plot-res-scaling")
            chart = boxes["chart"]
            rects = page.evaluate(_RES_ENERGY)["rects"]
            grids = [{k: v + (chart["left"] if k in ("left", "right") else chart["top"]) for k, v in r.items()}
                     for r in rects]
            worst, on_ratio = 0.0, []
            for (x, y), probe, box in found:
                plot = box["plot"]
                area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
                share = _overlap(probe["tip"], plot) / area
                assert share <= PROJECTION_READOUT_SHARE, (where, (x, y), probe["text"][:60], share)
                for i, g in enumerate(grids):
                    if _within((x, y), g):
                        part = _overlap(probe["tip"], g) / ((g["right"] - g["left"]) * (g["bottom"] - g["top"]))
                        assert part <= PROJECTION_READOUT_SHARE, (where, i, (x, y), probe["text"][:60], part)
                        worst = max(worst, part)
                        if i == 1:
                            on_ratio.append(probe["text"])
            shares[f"{view}/{mode}"] = round(worst, 3)
            texts = [probe["text"] for _, probe, _ in found]
            tied, weighted, low, hovered = _se_lines(texts, served, where)
            counts[f"{view}/{mode}"] = (tied, weighted, low)
            if estimator != "sample":
                assert weighted, f"{where}: no weighted window's tooltip read"
                # The 1/√E view draws no window below 4 GeV; the E view draws the 1–4 GeV windows in the all-windows
                # mode (and the low anchor in the 3-anchor mode), each weighted by the series' one c (D3).
                assert bool(low) is (view == "energy"), (where, low)
            if estimator == "median":
                # The tied deposits are drawn in the all-windows mode only, never fitted (brief-fix F3).
                deposits = {k for k in hovered if k.startswith("detector:")}
                assert bool(tied) is (mode == "all") and bool(deposits) is (mode == "all"), (where, tied, hovered)
            else:
                assert tied == 0, (where, tied)
            assert _hyphen_negatives(texts) == [], (where, _hyphen_negatives(texts))
            assert _says_exact(texts) == [], (where, _says_exact(texts))
            lines = [line.strip() for t in texts for line in t.splitlines()]
            assert any(line.startswith(VALUE_LINE[estimator]) for line in lines), (where, texts[:4])
            for name in CROSS_REFERENCES[estimator]:
                assert any(name in t for t in texts), (where, name, texts[:4])
            warned = [t for t in texts if LITERATURE_WARNING in _flat(t)]
            if estimator == "median" and view == "energy":
                assert on_ratio, f"{where}: no tooltip over the ratio panel"
                # The ratio panel divides by a literature curve (both on): every mark there says what it compares.
                assert all(LITERATURE_WARNING in _flat(t) for t in on_ratio), (where, [t[:80] for t in on_ratio
                                                                                      if LITERATURE_WARNING not in _flat(t)])
                assert any("literature" in t.lower() or "π±" in t or "e±" in t for t in warned), (where, warned[:2])
            else:
                assert warned == [], (where, warned[:2])
        print(f"res-scaling, {estimator}: largest share of the grid read {shares}; "
              f"tooltips read (tied, weighted, of those below 4 GeV) {counts}")
        browser.close()
    assert problems == [], problems


def test_the_robust_single_shower_card_names_its_decline_in_both_views(models_live_server):
    """Brief-fix F4 on the live single-shower hit experiment: under Robust σ (IQR) its one series, the calibrated
    deposit, has a single fittable window (N ≥ 20, from 5 GeV, with a fit weight), and the robust estimator fits no
    line through fewer than two, so the 3-anchor mode draws nothing. The empty state of both views names that
    decline and the window, never "no window reaches N = 20", and says which button draws it; the all-windows mode
    draws the window unfitted, and its tooltip's role line names the decline; the drawer says it in both views. Only
    the estimator switch asks the service."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        count = len(_requests_of(requests, "/api/resolution-scaling"))
        page.locator('.main .card[data-panel="res-scaling"] button[data-res-estimator="robust"]').click()
        _until(page, lambda: len(_requests_of(requests, "/api/resolution-scaling")) > count, "the robust request")
        _until(page, lambda: "fits no line" in _res_note(page), "the robust empty state")
        asked = _requests_of(requests, "/api/resolution-scaling")[count:]
        assert len(asked) == 1 and asked[0].get("estimator") == "robust", asked
        payload = _res_payload(base, asked[0])
        assert payload["estimator"]["name"] == "robust" and len(payload["series"]) == 1, payload["estimator"]
        series = payload["series"][0]
        gates = payload["gates"]
        # The decline as the payload states it: no fit in either mode, one fittable window in the anchors' pool.
        assert series["fits"]["anchors"]["points"] == [] and series["fits"]["all"]["points"] == [], series["fits"]
        fittable = [w for w in series["windows"] if (w["n"] or 0) >= 20 and w.get("se_rel") and w["value"] is not None
                    and (w.get("p_lo") or 0) >= gates["anchor_low_gev"]]
        assert len(fittable) == 1, [(w["label"], w["n"], w.get("se_rel")) for w in series["windows"]]
        window = fittable[0]
        assert window["n"] < 1000, window  # formatInt's digit grouping is not this test's subject
        declined = (f"Robust σ (IQR) fits no line through fewer than two fittable windows, and only {window['label']} "
                    f"(N = {window['n']}) is fittable here")
        before = len(requests)

        all_names = {"linear": f"All ≥ {gates['e_min_gev']:g} GeV", "energy": "All windows"}
        for view in ("linear", "energy"):
            assert _res_press(page, "res-view", view)
            assert _res_press(page, "res-windows", "anchors")
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)
            note = _res_note(page)
            # The empty state says why, by the decline, never by N.
            # (The 1/√E view adds the count of windows below 4 GeV that its Details drawer lists.)
            assert note.startswith(f"{declined}: no fit, so the 3-anchor mode draws nothing. "
                                   f"\"{all_names[view]}\" draws it, unfitted."), (view, note)
            assert "reaches N = " not in note, (view, note)
            _, _, body = _drawer(page, "res-scaling")
            assert declined in _flat(body), (view, _flat(body)[:400])
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)

            # The all-windows mode draws the window, unfitted, and its tooltip names the decline.
            assert _res_press(page, "res-windows", "all")
            page.evaluate(_SCROLL_START, "res-scaling")
            _frames(page)
            assert "fits no line" not in _res_note(page), (view, _res_note(page))
            found = _hover_windows(page)
            _check_tips(found, f"single robust {view} view, all windows")
            tips = [probe["text"] for _, probe, _ in found if f"{window['label']} · N = " in probe["text"]]
            assert tips and all(declined in _flat(t) for t in tips), (view, [t[:200] for t in tips])
            for (x, y), probe, box in found:
                plot = box["plot"]
                area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
                assert _overlap(probe["tip"], plot) / area <= PROJECTION_READOUT_SHARE, (view, (x, y), probe["text"][:60])
        assert requests[before:] == [], f"a render-only control asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


#: The part of a card `.main` shows, in viewport pixels: a screenshot clip.
_VISIBLE_CARD = """(id) => {
  const r = document.querySelector(`.main .card[data-panel="${id}"]`).getBoundingClientRect();
  const m = document.querySelector('.main').getBoundingClientRect();
  const top = Math.max(r.top, m.top);
  const bottom = Math.min(r.bottom, m.bottom);
  return { x: r.left, y: top, width: r.width, height: Math.max(0, bottom - top) };
}"""


#: Where the resolution card's screens go: CALOSRV_RES_SCREENS, else the test's temporary folder.
def _res_screens(tmp_path):
    folder = Path(os.environ.get("CALOSRV_RES_SCREENS") or tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_resolution_card_screens_under_each_estimator(models_live_server, scheme, tmp_path):
    """The resolution card at 1600 × 900 under the three estimators, on the recorded two-shower responses, saved as
    PNG (CALOSRV_RES_SCREENS, else the temporary folder) for a reader's eye: the 1/√E view once per estimator (3
    anchors), and the E view in both window modes with both literature curves on and with both off (the single-curve
    round's screens), each with its fit table on its own. Each screen is the card as drawn: its title follows the
    estimator, its y axis is named by it, and the disclosure is on the canvas exactly under the median in the E view
    with a curve on."""
    folder = _res_screens(tmp_path)
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE, scheme=scheme)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
        card = page.locator('.main .card[data-panel="res-scaling"]')

        def shoot(stem, where, *, table):
            page.evaluate(_SCROLL_START, "res-scaling")
            page.mouse.move(2, 2)
            _frames(page, 4)
            # The card from its top as far as `.main` shows it (its plot whole; an element screenshot of a card
            # taller than the scroller is cut there and padded with the page), then its fit table on its own.
            clip = page.evaluate(_VISIBLE_CARD, "res-scaling")
            assert clip["height"] > 500, (where, clip)
            target = folder / f"{stem}.png"
            page.screenshot(path=str(target), clip=clip)
            assert target.stat().st_size > 20_000, target
            if table:
                # The table with its caption, clear of the sticky tab and species bars: in a window tall enough to
                # hold it whole below them, its top scrolled to just under them; then the 900 px window again.
                page.set_viewport_size({"width": 1600, "height": 2200})
                _frames(page, 4)
                page.evaluate("""() => {
                  const host = document.querySelector('.main .card[data-panel="res-scaling"] .res-fit-table');
                  const main = document.querySelector('.main');
                  const sticky = [...main.querySelectorAll('*')].filter((el) => getComputedStyle(el).position === 'sticky')
                    .reduce((b, el) => Math.max(b, el.getBoundingClientRect().bottom), main.getBoundingClientRect().top);
                  main.scrollTop += host.getBoundingClientRect().top - sticky - 8;
                }""")
                _frames(page, 4)
                card.locator(".res-fit-table").screenshot(path=str(folder / f"{stem}_table.png"))
                page.set_viewport_size({"width": 1600, "height": 900})
                _frames(page, 4)

        for est in RES_ESTIMATORS:
            served = _fixture_payload(RES_TWO, est)
            if est != DEFAULT_ESTIMATOR:
                _res_estimator(page, requests, est, served["estimator"]["axis_name"])
            cases = [("linear", "anchors", True)] + [("energy", mode, lit) for mode in ("anchors", "all")
                                                     for lit in (True, False)]
            for view, mode, lit in cases:
                _res_press(page, "res-view", view)
                _res_press(page, "res-windows", mode)
                if view == "energy":
                    _set_literature(page, lit)
                page.evaluate(_SCROLL_START, "res-scaling")
                page.mouse.move(2, 2)
                _frames(page, 4)
                where = f"{scheme} {est} {view} {mode} literature {'on' if lit else 'off'}"
                assert page.evaluate(_RES_CHROME)["title"] == RES_TITLES[est][view], where
                axis = served["axis"]["energy"]["y"] if view == "energy" else served["axis"]["y"]
                assert _res_y_name(page).startswith(axis["name"]), (where, _res_y_name(page))
                assert (LITERATURE_WARNING in _res_note(page)) is (est == "median" and view == "energy" and lit), where
                if view == "linear":
                    shoot(f"res-scaling_{scheme}_linear_{est}", where, table=True)
                else:
                    # Named as the card's export names the state (res-emax): the default E max and the deposit hidden;
                    # with both curves off, no reference (`ratio-none`), the ratio panel's sentence on screen.
                    stem = (f"res-scaling_{scheme}_energy_emax-20_{'lit-pi-e' if lit else 'ratio-none'}_deposit-off"
                            f"_{est}_{mode}")
                    if not lit:
                        assert RATIO_NONE_TEXT in _res_note(page), (where, _res_note(page)[-300:])
                    # The fit table does not follow the literature toggles: one per mode.
                    shoot(stem, where, table=lit)
            _res_press(page, "res-windows", "anchors")
            _res_press(page, "res-view", "energy")
            _set_literature(page, True)
            _res_press(page, "res-view", "linear")
        browser.close()
    print(f"res-scaling screens in {folder}")
    assert problems == [], problems


# ------------------------------------------- the resolution card's noise term --

#: The E view's a/√E ⊕ b ⊕ c/E marks in viewport pixels (res-noise brief §4.1): per series key, every run of its
#: main-panel curve (`<key>|noise|<solid|dashed>|<i>`, the polyline's pixel points), and the centroid of every
#: caret its `<key>|carets` series drew (a window's, an entry's or a cut's: the tooltip tells them apart).
_RES_NOISE_TARGETS = """() => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const lines = {};
  const carets = {};
  inst.getModel().eachSeries((s) => {
    const id = s.get('id') || '';
    const line = /^([^|]+)\\|noise\\|(solid|dashed)\\|\\d+$/.exec(id);
    const caret = /^([^|]+)\\|carets$/.exec(id);
    if (!line && !caret) return;
    inst.getViewOfSeriesModel(s).group.traverse((el) => {
      if (el.isGroup || el.invisible || el.ignore) return;
      if (line && el.type === 'polyline' && el.shape?.points) {
        (lines[line[1]] ??= []).push({ id, part: line[2], points: el.shape.points.map(([x, y]) => [c.left + x, c.top + y]) });
      } else if (caret && el.type === 'polygon' && el.shape?.points?.length) {
        // The caret's centroid from its own pixel points (a reused element's cached paint rect can still hold the
        // previous render's place).
        const n = el.shape.points.length;
        const sx = el.shape.points.reduce((t, [x]) => t + x, 0) / n;
        const sy = el.shape.points.reduce((t, [, y]) => t + y, 0) / n;
        (carets[caret[1]] ??= []).push([c.left + sx, c.top + sy]);
      }
    });
  });
  return { lines, carets };
}"""

#: Every window mark's E on each grid, by series key, from the option (`<key>|markers`, `<key>|ratio|markers`: a
#: datum [E, value, index]; `<key>|ratio|carets`: [E, the axis end, index], a ratio beyond [1/k, k]).
_RES_MARK_ES = """() => {
  const out = {};
  for (const s of echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().series || []) {
    const m = /^([^|]+)\\|(markers|ratio\\|markers|ratio\\|carets)$/.exec(s.id || '');
    if (m) ((out[m[1]] ??= {})[m[2]] = (s.data || []).map((d) => d[0]));
  }
  return out;
}"""

#: brief §8, verbatim: the floor sentence and the naming caveat (panels/resolution_scaling.js noiseFloorText,
#: NOISE_NAMING_CAVEAT). The drawer's alone since brief-fix m6: no curve tooltip carries either.
NOISE_FLOOR = ("It uses windows from 1 GeV: below that a 1 GeV window reaches momenta near zero, so its average of 1/E² is "
               "far from what its plotted energy implies, and no single abscissa can carry the noise term c/E.")
NOISE_CAVEAT = ("c/E is the calorimeter's conventional noise term. Here it takes up whatever grows like 1/E at low "
                "momentum (for a network, its pull toward mid-range; under Median |rel. err.|, the response's bias as "
                "well), so c is a fitted coefficient, not a measured noise level.")
NOISE_ENTRY = re.compile(r"It comes down into the plot at E = ([\d.]+(?:e[−-]?\d+)?) GeV: a/√E ⊕ b ⊕ c/E rises "
                         r"without bound as E → 0, through its (noise term c/E|stochastic term a/√E)\.")
NOISE_UNITS = {"a": "%·√GeV", "b": "%", "c": "%·GeV"}
#: A term's square's unit, where the term is printed as its square (brief-fix m4: its SE exceeds its value).
NOISE_SQUARE_UNITS = {"a": "%²·GeV", "b": "%²", "c": "%²·GeV²"}
#: A non-negative number as the panel prints it to three significant figures (chart_panel.js `sigFigs`: plain from
#: 10⁻³ to 10⁵, else a mantissa × a power of ten in superscript digits).
_NUM = r"[\d.]+(?:×10⁻?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)?"


#: The line every fitted curve's main-panel tooltip ends with on the E view (panels/resolution_scaling.js
#: `ENERGY_NO_BAND_TEXT`, the lead's wording of 2026-11-15), verbatim.
ENERGY_NO_BAND_TEXT = "No band is drawn on this view: the standard errors above and the fit table carry the fit's uncertainty."
#: The drawer's one no-band sentence on the E view (models_notes.js `resolutionEnergyNotes`, What is drawn), verbatim.
DRAWER_NO_BAND = ("No band is drawn round a fitted curve on this view: each curve's tooltip and the fit table give its "
                  "terms with their standard errors, χ²/ν and S, and every window keeps its whisker.")
#: The drawer's pooled-scale line ends with this clause under the median and the robust estimators, in both views
#: (models_notes.js `pooledScaleLine`; review-stats S2, FX-notes, 28d58e5), verbatim; the sample estimator has no
#: pooled scale and no such line.
POOLED_CLAUSE = ("The a/√E ⊕ b ⊕ c/E fit weights its windows of 1–4 GeV by the same c, se = c·ŷ/√N, which they do not "
                 "enter, so their residuals count in S and the misfit verdict at c·ŷ/√N, not at their own bootstrap errors.")
#: The ratio panel's curve tooltip (panels/resolution_scaling.js `ratioFitTip`, review-ui F4, 19f6ab2): its title
#: line per drawn form, and the explanation it gives before the no-band line, verbatim.
RATIO_FIT_NAME = {"noise": "a/√E ⊕ b ⊕ c/E fit", "pinned": "Origin-pinned fit a₀/√E ⊕ 0"}
RATIO_FIT_EXPLAINED = "The fitted curve divided by the reference at each E, the reference held exact."


def _assert_noise_terms(line, params, where):
    """The terms line of an a/√E ⊕ b ⊕ c/E tooltip (`noiseTermsText`): every term with its SE and unit, its square
    with the square's SE where the term's SE exceeds it (brief-fix m4), or the held phrase."""
    held = params["held"]
    terms = line.split("; ")
    assert len(terms) == 3, (where, line)
    for t, term in zip("abc", terms):
        body = term.removeprefix("the noise term c/E: ") if t == "c" else term
        assert (t == "c") is term.startswith("the noise term c/E: "), (where, term)
        if t in held:
            assert body == f"{t} = 0, held there by the constraint {t}² ≥ 0", (where, term)
        elif params[f"se_{t}"] > params[t]:
            # A symmetric error larger than the value would reach below 0 for a term that cannot: its square.
            assert re.fullmatch(rf"{t}² = {_NUM} ± {_NUM} {re.escape(NOISE_SQUARE_UNITS[t])}", body), (where, term)
        else:
            assert re.fullmatch(rf"{t} = {_NUM} ± {_NUM} {re.escape(NOISE_UNITS[t])}", body), (where, term)


def _assert_chi2_line(line, fit, where):
    """A drawn fit's χ²/ν line on the E view (`energyChi2Line`, review-ui N1 and F4): "χ²/ν = …/ν, p = …; S = …" with
    its S where ν ≥ 1, else the ν = 0 sentence that the curve passes through its points."""
    if fit["ndf"] > 0 and fit.get("p_value") is not None:
        m = re.fullmatch(rf"χ²/ν = {_NUM}/(\d+), p = {_NUM}; S = ([\d.]+)", line)
        assert m and int(m.group(1)) == fit["ndf"], (where, line, fit["ndf"])
        scale = fit["scale_factor"] if fit.get("scale_factor") is not None else 1
        assert float(m.group(2)) == pytest.approx(scale, rel=5e-3), (where, line, scale)
    else:
        assert re.fullmatch(r"ν = 0: no χ² test: the curve passes through its \d+ points? exactly", line), (where, line)


def _assert_ratio_fit_tip(text, s, payload, mode, where):
    """A fitted curve's tooltip on the ratio panel (review-ui F4, 19f6ab2): the series; "<fit> ÷ <reference>"; the
    drawn fit's terms with their SEs (a/√E ⊕ b ⊕ c/E's terms, or a₀/√E with ± SE(a₀)); its χ²/ν line with S; the
    explanation; and the no-band line, once, the one mention of a band. A literature reference is named without a
    % sign by its values (c406217)."""
    lines = _noise_tip_lines(text)
    flat = _flat(text)
    mf = s["fits"][mode]
    form = _drawn_form(mf)
    assert form in RATIO_FIT_NAME, (where, s["key"], form)
    fit = mf[form]
    assert lines[0] == s["label"], (where, lines[:2])
    head = f"{RATIO_FIT_NAME[form]} ÷ "
    assert lines[1].startswith(head) and len(lines[1]) > len(head), (where, lines[1])
    assert "%" not in lines[1], (where, lines[1])
    if form == "noise":
        _assert_noise_terms(lines[2], fit["params"], where)
    else:
        sym = payload["estimator"].get("symbol") or "σ/E"
        assert re.fullmatch(rf"{re.escape(sym)} = \({_NUM} ± {_NUM}\)%/√E ⊕ 0 \(b ≡ 0, through the origin\)",
                            lines[2]), (where, lines[2])
    _assert_chi2_line(lines[3], fit, where)
    assert lines[4] == RATIO_FIT_EXPLAINED, (where, lines[4])
    assert lines[5] == ENERGY_NO_BAND_TEXT, (where, lines[5])
    # The no-band line is the one place the word "band" appears, and it appears once.
    assert flat.count(ENERGY_NO_BAND_TEXT) == 1, (where, flat[-500:])
    assert "band" not in flat.replace(ENERGY_NO_BAND_TEXT, "").lower(), (where, flat[-500:])
    assert "envelope" not in flat.lower() and "conditional on" not in flat, (where, flat[-500:])


def _noise_tip_lines(text):
    return [_flat(line) for line in text.splitlines() if line.strip()]


def _assert_noise_tip(text, s, noise, payload, mode, where):
    """A curve tooltip of a/√E ⊕ b ⊕ c/E (brief §4.3, §8, §11): its series and equation; every term with its SE
    and unit, its square with the square's SE where the term's SE exceeds it (brief-fix m4), or the held phrase;
    χ²/ν and S; the windows fitted, the low anchor named in the 3-anchor mode, with its sentence; the correlations of
    the fitted squares where any pair is free; no band sentence, only the no-band line, once (Martin's directive of
    2026-11-15). The floor sentence and the naming caveat are the drawer's alone (brief-fix m6), so the tooltip
    carries neither."""
    lines = _noise_tip_lines(text)
    flat = _flat(text)
    params = noise["params"]
    held = params["held"]
    sym = payload["estimator"]["symbol"] if "symbol" in payload["estimator"] else None
    assert lines[0] == s["label"], (where, lines[:2])
    assert lines[1].endswith(" = a/√E ⊕ b ⊕ c/E") and (sym is None or lines[1] == f"{sym} = a/√E ⊕ b ⊕ c/E"), \
        (where, lines[1])
    _assert_noise_terms(lines[2], params, where)
    assert "held non-negative, so every term is real." in flat, where
    if noise["ndf"] > 0:
        assert re.search(r"χ²/ν = .+; S = [\d.]+", flat), (where, flat[:300])
    windows = next((line for line in lines if line.startswith("Windows fitted (")), None)
    assert windows and windows.startswith(f"Windows fitted ({noise['n_points']}, "), (where, windows)
    low = noise["low_anchor"]
    labels = {w["bin"]: w["label"] for w in s["windows"]}
    if mode == "anchors" and low is not None:
        assert f"{labels[low]} (the low anchor)" in windows, (where, windows)
        others = len([b for b in noise["points"] if b != low])
        count = {1: "the one anchor", 2: "the two anchors", 3: "the three anchors"}[others]
        assert (f"In the 3-anchor mode it runs through {count} and the lowest fittable window from 1 GeV "
                f"({labels[low]}), since anchors from 5 GeV cannot fix a 1/E term.") in flat, (where, flat[-600:])
    else:
        assert "(the low anchor)" not in windows, (where, windows)
    # No band on the E view (Martin's directive of 2026-11-15): no band sentence, envelope or conditional, held term
    # or not; the one no-band line says where the fit's uncertainty is instead, once.
    assert "The band is" not in flat and "envelope" not in flat.lower() and "conditional on" not in flat, \
        (where, held, flat[-800:])
    assert flat.count(ENERGY_NO_BAND_TEXT) == 1, (where, flat[-400:])
    rho ={k: v for k, v in params["rho"].items() if v is not None}
    names = {"a2b2": "ρ(a², b²)", "a2c2": "ρ(a², c²)", "b2c2": "ρ(b², c²)"}
    if rho:
        line = next((x for x in lines if x.startswith("ρ(")), None)
        assert line is not None, (where, rho, lines)
        assert [n for k, n in names.items() if k in rho] == re.findall(r"ρ\([abc]², [abc]²\)", line.split(":")[0]), \
            (where, line)
        if max(abs(v) for v in rho.values()) >= 0.7 and all(v < 0 for v in rho.values()):
            assert line.endswith("the terms trade off against each other over the fitted windows, so the curve is "
                                 "better determined than its terms."), (where, line)
        elif max(abs(v) for v in rho.values()) < 0.7:
            assert "no pair of the fitted squares is strongly correlated here" in line, (where, line)
    else:
        assert "ρ(" not in flat, (where, flat[-600:])
    # brief-fix m6: the floor sentence and the naming caveat are the drawer's, stated there once.
    assert NOISE_FLOOR not in flat and NOISE_CAVEAT not in flat, (where, flat[-700:])
    assert "It uses windows from 1 GeV" not in flat and "not a measured noise level" not in flat, (where, flat[-700:])
    assert _hyphen_negatives([text]) == [], (where, text)


def _hover_points(page, points, where):
    """Hover each point; every tooltip that showed, probed (as `_hover_marks` returns them)."""
    page.evaluate(_WATCH_HOVER, "plot-res-scaling")
    boxes = page.evaluate(_BOXES, "plot-res-scaling")
    found = []
    for x, y in points:
        page.mouse.move(x, y)
        _frames(page)
        probe = page.evaluate(_PROBE)
        if probe is not None:
            found.append(((x, y), probe, boxes))
    page.mouse.move(2, 2)
    _frames(page)
    return found


def _assert_capped(page, found, where):
    """Every probe on the tooltip layer, beside or off the plot, and over at most a fifth of the plot and of the
    grid being read (the 20% readout cap)."""
    _check_tips(found, where)
    chart = page.evaluate(_BOXES, "plot-res-scaling")["chart"]
    grids = [{k: v + (chart["left"] if k in ("left", "right") else chart["top"]) for k, v in r.items()}
             for r in page.evaluate(_RES_ENERGY)["rects"]]
    for (x, y), probe, box in found:
        plot = box["plot"]
        area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
        assert _overlap(probe["tip"], plot) / area <= PROJECTION_READOUT_SHARE, (where, (x, y), probe["text"][:80])
        for g in grids:
            if _within((x, y), g):
                share = _overlap(probe["tip"], g) / ((g["right"] - g["left"]) * (g["bottom"] - g["top"]))
                assert share <= PROJECTION_READOUT_SHARE, (where, (x, y), probe["text"][:80], share)


#: The estimators the noise checks read on the recorded two-shower response: the median (the default; both networks
#: come down from the top through c/E, the tied deposits have no fit of any form) and the sample estimator (both
#: deposits fitted: shower A's through c/E, shower B's through a/√E with c held; network A flat, b alone).
NOISE_ESTIMATORS = ("median", "sample")


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_noise_fit_comes_down_from_the_top_and_the_ratio_marks_start_at_one_gev(models_live_server, scheme):
    """The res-noise change on the recorded two-shower response, in both themes (brief §0, §4; Martin's decisions
    of 2026-11-13), under the median and the sample estimators, both literature curves off.

    - **The entry.** Each a/√E ⊕ b ⊕ c/E curve with A > 0 or C > 0 comes down into the main panel at its top, from
      the left: its first point lies on the axis top at the energy where its line reaches it (the root of
      C·u² + A·u + (B − top²)), and it falls from there; a flat one (b alone) starts at E = 0. Hovered, the curve
      names its terms with their SEs (a term's square where its SE exceeds it) or the held phrase, the correlation
      of the free squares and the windows (the low anchor named), the no-band line and no band sentence (Martin's
      directive of 2026-11-15), and no longer the floor sentence or the naming caveat (the drawer's, brief-fix m6); the
      entry caret says where the curve comes down and through which term (§8). Every tooltip keeps to the 20% cap.
    - **The low anchor.** In the 3-anchor mode the low anchor's window is drawn on the E view (on neither the 1/√E
      view's axis nor its anchors), and its tooltip's role line names it the low anchor.
    - **Ratio marks from 1 GeV.** With both literature curves off, every window from 1 GeV the mode draws, those of
      1–4 GeV included, carries a ratio mark against its shower's deposit a/√E ⊕ b ⊕ c/E fit where it has one; a
      shower whose deposit has no fit of any form has none.
    - **No request.** Views and window modes repaint the response in hand; only the estimator asks the service."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE, scheme=scheme)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
        before = len(requests)
        assert _res_press(page, "res-view", "energy")
        # The deposit on (hidden at open since res-emax): its fits are the ratio's reference with both curves off.
        assert _res_deposit(page, True)
        assert not _res_press(page, "res-literature", "pi") and not _res_press(page, "res-literature", "e")
        assert requests[before:] == [], f"the view, the deposit or a literature toggle asked the service: {requests[before:]}"
        seen = {"curve": 0, "entry": 0, "low": 0, "ratio": 0}
        for est in NOISE_ESTIMATORS:
            payload = _fixture_payload(RES_TWO, est)
            if est != DEFAULT_ESTIMATOR:
                # The one control that asks: exactly one request (`_res_estimator` counts it).
                _res_estimator(page, requests, est, payload["estimator"]["axis_name"])
            mark = len(requests)
            by_key = {s["key"]: s for s in payload["series"]}
            deposit = {s["shower"]: s for s in payload["series"] if s["source"] == "detector"}
            for mode in ("anchors", "all"):
                assert _res_press(page, "res-windows", mode)
                page.evaluate(_SCROLL_START, "res-scaling")
                page.mouse.move(2, 2)
                _frames(page, 4)
                where = f"{scheme}, {est}, {mode}"
                view = page.evaluate(_RES_ENERGY)
                _assert_e_view_curves(view, payload, mode)
                top = view["y"][0]["max"]
                targets = page.evaluate(_RES_NOISE_TARGETS)
                fitted = {k: s["fits"][mode]["noise"] for k, s in by_key.items() if s["fits"][mode]["noise"]}
                assert set(targets["lines"]) == set(fitted), (where, sorted(targets["lines"]), sorted(fitted))
                found = []
                for key, noise in fitted.items():
                    s = by_key[key]
                    # Comes down from the top-left: the main curve's lowest-E point on the axis top at the root's E,
                    # and below the top just after it; a flat curve from E = 0 at b.
                    pts = sorted(pt for cid, c in view["curves"].items() if cid.startswith(f"{key}|noise|")
                                 for pt in c["points"])
                    entry = _noise_entry(noise["params"], top)
                    if entry is None:
                        assert pts[0][0] == pytest.approx(0, abs=1e-3), (where, key, pts[:2])
                        assert pts[0][1] == pytest.approx(noise["params"]["b"], rel=1e-3), (where, key, pts[:2])
                    else:
                        assert pts[0][0] == pytest.approx(entry, rel=1e-3, abs=1e-4), (where, key, pts[0], entry)
                        assert pts[0][1] == pytest.approx(top, rel=1e-3), (where, key, pts[0], top)
                        later = [pt for pt in pts if pt[0] > pts[0][0] * 1.5 + 0.05]
                        assert later and later[0][1] < top and min(pt[1] for pt in pts) < top, (where, key, pts[:4])

                    # Hover the curve: points along its runs until one of its own tooltips shows (a marker or a
                    # crossing curve may lie over a point), one on its solid run and one on a dashed run.
                    tips = {}
                    for run in sorted(targets["lines"][key], key=lambda r: r["part"] != "solid"):
                        if run["part"] in tips:
                            continue
                        pts_px = run["points"]
                        step = max(1, len(pts_px) // 12)
                        for got in _hover_points(page, pts_px[step // 2::step], where):
                            lines = _noise_tip_lines(got[1]["text"])
                            if len(lines) > 1 and lines[0] == s["label"] and lines[1].endswith("= a/√E ⊕ b ⊕ c/E"):
                                tips[run["part"]] = got
                                break
                    assert "solid" in tips, (where, key, "no a/√E ⊕ b ⊕ c/E tooltip on its solid run")
                    for part, got in tips.items():
                        _assert_noise_tip(got[1]["text"], s, noise, payload, mode, f"{where}, {key}, {part}")
                        assert (part == "dashed") is ("Extrapolated: beyond the windows this fit used" in got[1]["text"]), \
                            (where, key, part)
                        found.append(got)
                    seen["curve"] += 1

                    # The entry caret: §8's sentence, at the root's energy, through the term that dominates as E → 0.
                    hovered = _hover_points(page, targets["carets"].get(key, []), where)
                    # Its own entry tooltips: a caret within a pixel or two of another series' (both near E = 0) may
                    # show that one's, read under its own key.
                    entries = [got for got in hovered if NOISE_ENTRY.search(_flat(got[1]["text"]))
                               and _noise_tip_lines(got[1]["text"])[0] == s["label"]]
                    found += entries
                    if entry is None:
                        assert entries == [], (where, key, [g[1]["text"][:120] for g in entries])
                        continue
                    for got in entries:
                        m = NOISE_ENTRY.search(_flat(got[1]["text"]))
                        assert float(m.group(1)) == pytest.approx(entry, rel=6e-3), (where, key, m.group(0), entry)
                        term = "noise term c/E" if noise["params"]["c2"] > 0 else "stochastic term a/√E"
                        assert m.group(2) == term, (where, key, m.group(0))
                    # A caret within a few pixels of E = 0 may lie under another series' caret; one at 0.5 GeV or
                    # more is found (a window caret beside it may show the same tip, every one checked above).
                    if entry >= 0.5:
                        assert entries, (where, key, entry, "its entry caret shows no entry tooltip")
                        seen["entry"] += 1

                # The low anchor: drawn on the E view in the 3-anchor mode, and named so by its tooltip.
                marks = page.evaluate(_RES_MARK_ES)
                windows = _hover_windows(page)
                found += windows
                texts = [probe["text"] for _, probe, _ in windows]
                for key, noise in fitted.items():
                    s = by_key[key]
                    low = noise["low_anchor"]
                    if mode != "anchors":
                        assert low is None, (where, key, low)
                        continue
                    assert low is not None, (where, key, noise)
                    w = next(w for w in s["windows"] if w["bin"] == low)
                    assert w["p_lo"] < CURVE_MIN_GEV and low not in s["fits"]["anchors"]["points"], (where, key, w)
                    assert any(e == pytest.approx(1 / w["x"] ** 2, rel=1e-6) for e in marks[key]["markers"]), \
                        (where, key, w["label"], marks[key]["markers"])
                    tip = [t for t in texts if _noise_tip_lines(t)[0] == s["label"] and f"{w['label']} · N = " in t
                           and "Ratio to " not in t]
                    assert tip, (where, key, w["label"])
                    assert all("the low anchor of the a/√E ⊕ b ⊕ c/E fit: the lowest fittable window from 1 GeV, "
                               "since anchors from 5 GeV cannot fix a 1/E term; a₀/√E does not use it" in _flat(t)
                               for t in tip), (where, key, [t[-400:] for t in tip])
                    seen["low"] += 1

                # Ratio marks from 1 GeV: every drawn window of a shower whose deposit has a noise fit, against it.
                for key, s in by_key.items():
                    ref = deposit[s["shower"]]["fits"][mode]
                    drawn = sorted(marks.get(key, {}).get("markers", []))
                    on_ratio = sorted(marks.get(key, {}).get("ratio|markers", []) + marks.get(key, {}).get("ratio|carets", []))
                    if ref["noise"] is None:
                        if not ref["pinned"]:
                            assert on_ratio == [], (where, key, on_ratio)
                        continue
                    low_windows = [w for w in s["windows"] if w["value"] is not None
                                   and NOISE_MIN_GEV <= w["p_lo"] < CURVE_MIN_GEV
                                   and any(e == pytest.approx(1 / w["x"] ** 2, rel=1e-6) for e in drawn)]
                    if mode == "all":
                        assert low_windows, (where, key, "no 1–4 GeV window drawn")
                    for w in low_windows:
                        assert any(e == pytest.approx(1 / w["x"] ** 2, rel=1e-6) for e in on_ratio), \
                            (where, key, w["label"], on_ratio)
                        seen["ratio"] += 1
                    # Every window marker from 1 GeV on the main panel has its ratio mark (a marker, or a caret beyond
                    # [1/k, k]), and no window below 1 GeV has one. (A ratio caret at no window's E is a fit's.)
                    for e in drawn:
                        if e >= NOISE_MIN_GEV:
                            assert any(r == pytest.approx(e, rel=1e-6) for r in on_ratio), (where, key, e, on_ratio)
                    for w in s["windows"]:
                        if w["p_lo"] < NOISE_MIN_GEV and w.get("x"):
                            assert not any(r == pytest.approx(1 / w["x"] ** 2, rel=1e-6) for r in on_ratio), \
                                (where, key, w["label"], on_ratio)
                    label = f"shower {s['shower'].upper()}'s deposit a/√E ⊕ b ⊕ c/E fit"
                    ratio_tips = [t for t in texts if _noise_tip_lines(t)[0] == s["label"] and "Ratio to " in t]
                    assert ratio_tips and all(f"Ratio to {label} = " in _flat(t) for t in ratio_tips), \
                        (where, key, [t[:300] for t in ratio_tips[:2]])
                assert found, where
                _assert_capped(page, found, where)
                # brief-fix FX1: no tooltip calls anything exact, the kept reference phrase aside.
                said = _says_exact([probe["text"] for _, probe, _ in found])
                assert said == [], (where, said)
            # The 1/√E view and back, both window modes: repaints of the response in hand.
            assert _res_press(page, "res-view", "linear")
            assert _res_press(page, "res-windows", "anchors")
            assert _res_press(page, "res-view", "energy")
            assert requests[mark:] == [], f"{scheme}, {est}: a view or a window mode asked the service: {requests[mark:]}"
        print(f"res-scaling noise, {scheme}: curves {seen['curve']}, entry carets {seen['entry']}, low anchors "
              f"{seen['low']}, 1–4 GeV ratio marks {seen['ratio']}")
        assert all(seen.values()), seen
        assert [q.get("estimator") for q in _requests_of(requests, "/api/resolution-scaling")] == list(NOISE_ESTIMATORS)
        browser.close()
    assert problems == [], problems


# --------------------------------- one fitted curve per series, no band (single-curve round) --

#: The tooltip phrases with the word "exact" the card keeps: the ratio-fit tooltip's statement that the reference is
#: held fixed (panels/resolution_scaling.js `ratioFitTip`; NF-panel kept it for the lead's call, NF-panel.md §2, and
#: the single-curve round reworded it). They name the reference's treatment, not a band's coverage. `_says_exact`
#: holds every other tooltip line to the fix round's brief.
EXACT_KEPT = ("the reference is held exact", "the reference held exact")


def _says_exact(texts):
    """Every tooltip line that says "exact" (brief-fix FX1: the word went from every band sentence), the kept phrases
    aside. "exactly" is not the word: a ν = 0 fit "passes through its points exactly", which is no band claim."""
    out = []
    for t in texts:
        for line in (_flat(x) for x in t.splitlines()):
            rest = line
            for kept in EXACT_KEPT:
                rest = rest.replace(kept, "")
            if re.search(r"\bexact\b", rest):
                out.append(line)
    return out


#: Every series of the live chart as its option holds it (`getOption().series`): [id, yAxisIndex, legend name].
_RES_OPTION_SERIES = """() => (echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().series || [])
  .map((s) => [s.id ?? '', s.yAxisIndex ?? 0, s.name ?? ''])"""

#: A fitted-curve family's series id: `<series key>|[ratio|]<form>|<rest>` (panels/resolution_scaling.js
#: `energySeriesMarks`, whose curve runs are `<rest>` = `<solid|dashed>|<i>`; a band, edge or reference band would be
#: any other `<rest>`).
FIT_FAMILY_ID = re.compile(r"^(?P<key>[^|]+)\|(?P<ratio>ratio\|)?(?P<form>noise|pinned|quadrature|affine)\|(?P<rest>.+)$")
CURVE_RUN = re.compile(r"^(solid|dashed)\|\d+$")

#: Every fitted-curve run the E view drew, on both grids, read back from the elements ECharts painted (a custom
#: series keeps its geometry in a closure): per series id, its grid, form and part and its polylines' points in
#: viewport pixels, to hover.
_RES_CURVE_RUNS = """() => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const out = [];
  inst.getModel().eachSeries((s) => {
    const id = s.get('id') || '';
    const m = /^([^|]+)\\|(ratio\\|)?(noise|pinned|quadrature|affine)\\|(solid|dashed)\\|\\d+$/.exec(id);
    if (!m) return;
    const px = [];
    inst.getViewOfSeriesModel(s).group.traverse((el) => {
      if (el.isGroup || el.invisible || el.ignore || el.type !== 'polyline' || !el.shape?.points?.length) return;
      px.push(...el.shape.points.map(([x, y]) => [c.left + x, c.top + y]));
    });
    out.push({ id, key: m[1], ratio: Boolean(m[2]), form: m[3], part: m[4], px });
  });
  return out;
}"""


#: The literature curves' runs on both grids, as `_RES_CURVE_RUNS` reads the fitted curves: per series id
#: `literature|<key>[|ratio]`, its key, panel and polylines' points in viewport pixels, to hover.
_RES_LIT_RUNS = """() => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const out = [];
  inst.getModel().eachSeries((s) => {
    const m = /^literature\\|([a-z]+)(\\|ratio)?$/.exec(s.get('id') || '');
    if (!m) return;
    const px = [];
    inst.getViewOfSeriesModel(s).group.traverse((el) => {
      if (el.isGroup || el.invisible || el.ignore || el.type !== 'polyline' || !el.shape?.points?.length) return;
      px.push(...el.shape.points.map(([x, y]) => [c.left + x, c.top + y]));
    });
    out.push({ key: m[1], ratio: Boolean(m[2]), px });
  });
  return out;
}"""

#: The legend entries of the live chart: every name its legend lists.
_RES_LEGEND_NAMES = """() => ((echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().legend
  || [])[0]?.data || []).map((d) => (typeof d === 'string' ? d : d.name))"""

#: The two literature curves as the card writes them (catalog/resolution_refs.js `referenceEquation`, Martin's request
#: of 2026-11-15, c406217): the figure's legend, no % sign by the values; the units said apart (`REFERENCE_UNITS`).
LITERATURE = {"pi": ("π±", "σ/E = 27.2/√E ⊕ 1.0"), "e": ("e±", "σ/E = 14.0/√E ⊕ 0.4")}
REFERENCE_UNITS = "σ/E in percent, E in GeV"
#: The legend entry of each curve (panels/resolution_scaling.js `energyModel`: `${particle} lit. — ${equation}`).
LITERATURE_LEGEND = {key: f"{particle} lit. — {eq}" for key, (particle, eq) in LITERATURE.items()}
#: Each toggle's title (models_cards.js `RES_LITERATURE_CONTROL`), verbatim.
LITERATURE_TITLE = {key: (f"Draw or hide {eq} ({REFERENCE_UNITS}); transcribed from the supplied figure's legend; no "
                          "interval reported. The ratio panel divides by the curve drawn, by the one the windows lie "
                          "farther from when both are, and by each shower's deposit fit when neither is.")
                    for key, (_, eq) in LITERATURE.items()}
#: The drawer's transcription line (models_notes.js `resolutionEnergyNotes`), verbatim from the equations on.
LITERATURE_TRANSCRIBED = (f"{LITERATURE['pi'][1]} and {LITERATURE['e'][1]}, transcribed as the legend prints them, "
                          f"{REFERENCE_UNITS}.")
#: A literature curve that rises less than this above its panel's floor lies on the axis line and on the other curve,
#: so its own tooltip cannot be hovered apart (robust on the recorded two-shower response: 0 to 5,500%).
LIT_SQUEEZED_PX = 6
#: Either literature equation, written anywhere: its two % slots, which must stay empty (c406217).
LITERATURE_ANY = re.compile(r"(?:27\.2|14\.0)(%?)/√E ⊕ (?:1\.0|0\.4)(%?)")


def _percent_literature(texts):
    """Every text that writes a literature equation with a % sign by its values."""
    return [t for t in texts for m in LITERATURE_ANY.finditer(_flat(t)) if m.group(1) or m.group(2)]


#: A literature equation as `referenceEquation` writes it (the label form "π± 27.2/√E ⊕ 1.0" is not one).
LITERATURE_EQUATION = re.compile(r"σ/E = (?:27\.2|14\.0)/√E ⊕ (?:1\.0|0\.4)")


def _unitless_literature(texts):
    """Every tooltip that writes a literature equation without REFERENCE_UNITS (FX-browser's finding, 2026-11-15:
    the 1.0 rule, the other curve on the ratio panel and the caret above the main panel wrote it without them)."""
    return [t for t in texts if LITERATURE_EQUATION.search(_flat(t)) and REFERENCE_UNITS not in _flat(t)]


def _set_literature(page, on):
    """Both literature curves on or both off (`π± | e±`, card controls): click each toggle not already as asked."""
    for key, particle in (("pi", "π±"), ("e", "e±")):
        pressed = dict((t[0], t[1]) for t in page.evaluate(_RES_LIT_TOGGLES))[particle] == "true"
        if pressed is not on:
            assert _res_press(page, "res-literature", key) is on, (key, on)


def _curve_families(option_series, payload, mode, where):
    """The fitted-curve families of the live chart, from its option (`getOption().series`), against the payload.
    Every curve series id is a run `<solid|dashed>|<i>`, never a band, an edge or a reference band, and none of
    those exists under any id; each family lies on its own grid (the ratio panel's on grid 1); each series draws one
    form per panel, the one `_drawn_form` names. Returns {(series key, panel): form}."""
    ids = [sid for sid, _, _ in option_series]
    assert not [i for i in ids if "|band|" in i or i.endswith("|band") or "|edges|" in i or "|reference|" in i], \
        (where, ids)
    by_key = {s["key"]: s for s in payload["series"]}
    families = {}
    for sid, grid, _ in option_series:
        m = FIT_FAMILY_ID.match(sid)
        if not m:
            continue
        assert CURVE_RUN.match(m["rest"]), (where, sid)
        panel = "ratio" if m["ratio"] else "main"
        assert grid == (1 if panel == "ratio" else 0), (where, sid, grid)
        families.setdefault((m["key"], panel), set()).add(m["form"])
    for (key, panel), forms in families.items():
        # Exactly one fitted-curve family per series and panel, the one curve the series draws.
        assert len(forms) == 1, (where, key, panel, sorted(forms))
        expected = _drawn_form(by_key[key]["fits"][mode])
        assert forms == {expected}, (where, key, panel, sorted(forms), expected)
    return {k: next(iter(v)) for k, v in families.items()}


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_e_view_draws_one_curve_per_series_with_no_band_and_one_pooled_scale(models_live_server, scheme):
    """The single-curve round (Martin's directive of 2026-11-15; CLAUDE.md §2 "Recorded exception: the E view's fitted
    curves carry no band", §5 "One fitted curve per series", "Retired: the envelope band", "One pooled scale") on the
    recorded two-shower response, in both themes, under every estimator, in both window modes, with both literature
    curves on and with both off, both showers on show. Read back from the live chart:

    - **One family.** Every series draws one fitted-curve family on each panel (`getOption().series`): its
      a/√E ⊕ b ⊕ c/E where drawable, else its a₀/√E; a series whose curve reaches the main panel draws it there; the
      curves keep the solid-and-dashed rules (`_assert_e_view_curves`).
    - **No band.** No series id contains `|band|`, `|edges|` or `|reference|`. Every fitted curve's main-panel
      tooltip carries the no-band line once; no tooltip read names a band sentence, the envelope or c_low.
    - **The ratio curve's tooltip** (review-ui F4): every series whose curve reaches the ratio panel yields one; it
      names "<fit> ÷ <reference>", the drawn fit's terms with their SEs, its χ²/ν line with S, the explanation, and
      the no-band line once, the only mention of a band (`_assert_ratio_fit_tip`).
    - **The literature curves** (c406217): with the curves on, both legend entries read "<particle> lit. — σ/E =
      27.2/√E ⊕ 1.0" (and 14.0/√E ⊕ 0.4); no legend entry, tooltip or drawer writes a literature equation with a %
      sign by its values; each main-panel curve's tooltip gives its equation and says "σ/E in percent, E in GeV".
    - **One pooled scale.** Under the median and the robust estimators a 1–4 GeV window's tooltip prints its series'
      one c, "pooled over its windows from 4 GeV", never c_low (`_se_lines`).
    - **The drawer.** The Details drawer carries the no-band sentence once and never says "envelope" or "c_low";
      under median and robust its pooled-scale line ends with the clause on the 1–4 GeV windows' residuals
      (review-stats S2), under sample there is none; with the curves on, its transcription line names the units.
    - **The cap, and no "exact".** Every tooltip read keeps to the 20% readout cap and says "exact" only in the kept
      reference phrase.
    - **No request** but the estimator's."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE, scheme=scheme)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
        before = len(requests)
        assert _res_press(page, "res-view", "energy")
        both = '.main .card[data-panel="res-scaling"] button[data-models-shower="both"]'
        assert page.get_attribute(both, "aria-pressed") == "true", "both showers on show"
        # The deposit on (hidden at open since res-emax): every series of the response draws its one curve.
        assert _res_deposit(page, True)
        assert requests[before:] == [], f"the view or the deposit asked the service: {requests[before:]}"
        seen = {"families": 0, "noise": 0, "curve tips": 0, "ratio tips": 0, "literature tips": 0,
                "literature ratio tips": 0, "low": 0, "drawers": 0, "tips": 0}
        squeezed = {"literature squeezed": 0}
        for est in RES_ESTIMATORS:
            payload = _fixture_payload(RES_TWO, est)
            if est != DEFAULT_ESTIMATOR:
                _res_estimator(page, requests, est, payload["estimator"]["axis_name"])
            mark = len(requests)
            by_label = {s["label"]: s for s in payload["series"]}
            for mode in ("anchors", "all"):
                assert _res_press(page, "res-windows", mode)
                for lit in (True, False):
                    _set_literature(page, lit)
                    page.evaluate(_SCROLL_START, "res-scaling")
                    page.mouse.move(2, 2)
                    _frames(page, 4)
                    where = f"{scheme}, {est}, {mode}, literature {'on' if lit else 'off'}"
                    assert _literature_drawn(page) == (["e", "pi"] if lit else []), where

                    # One family per series and panel, from the option; the curves' geometry, from the paint.
                    families = _curve_families(page.evaluate(_RES_OPTION_SERIES), payload, mode, where)
                    view = page.evaluate(_RES_ENERGY)
                    drawn = _assert_e_view_curves(view, payload, mode)
                    assert {k for k, panel in families if panel == "main"} == set(drawn), (where, families, drawn)
                    seen["families"] += len(families)
                    seen["noise"] += sum(form == "noise" for form in families.values())

                    # Each curve's tooltips: points along every run, until one of the series' own curve tips shows.
                    runs = page.evaluate(_RES_CURVE_RUNS)
                    found, curve_tips = [], {}
                    for run in runs:
                        panel = "ratio" if run["ratio"] else "main"
                        if (run["key"], panel) in curve_tips or not run["px"]:
                            continue
                        label = next(s["label"] for s in payload["series"] if s["key"] == run["key"])
                        step = max(1, len(run["px"]) // 10)
                        for got in _hover_points(page, run["px"][step // 2::step], where):
                            found.append(got)
                            lines = _noise_tip_lines(got[1]["text"])
                            if len(lines) < 2 or lines[0] != label:
                                continue
                            # The curve's own tip: its equation on the main panel, "… ÷ <reference>" on the ratio.
                            if panel == "ratio" and " ÷ " in lines[1] and "fit" in lines[1]:
                                curve_tips[(run["key"], panel)] = got[1]["text"]
                                break
                            if panel == "main" and ENERGY_NO_BAND_TEXT in _flat(got[1]["text"]):
                                curve_tips[(run["key"], panel)] = got[1]["text"]
                                break
                    by_key = {s["key"]: s for s in payload["series"]}
                    for (key, panel), text in curve_tips.items():
                        flat = _flat(text)
                        if panel == "main":
                            assert flat.count(ENERGY_NO_BAND_TEXT) == 1, (where, key, flat[-500:])
                            seen["curve tips"] += 1
                        else:
                            # The ratio of a curve (review-ui F4): its terms with their SEs, its χ²/ν line with S,
                            # and the no-band line once, the one mention of a band; no band is drawn round it.
                            _assert_ratio_fit_tip(text, by_key[key], payload, mode, f"{where}, {key}, ratio")
                            seen["ratio tips"] += 1
                    shown_main = {k for k, panel in families if panel == "main"}
                    assert shown_main <= {k for k, panel in curve_tips if panel == "main"}, \
                        (where, sorted(shown_main), sorted(curve_tips))
                    # Every series whose one curve reaches the ratio panel yields its own ratio-curve tooltip there.
                    ratio_runs = {r["key"] for r in runs if r["ratio"] and r["px"]}
                    assert ratio_runs <= {k for k, panel in curve_tips if panel == "ratio"}, \
                        (where, sorted(ratio_runs), sorted(curve_tips))

                    # The literature curves (c406217): each legend entry and equation without a % sign by its values;
                    # the main curve's tooltip says the units (REFERENCE_UNITS).
                    legend = page.evaluate(_RES_LEGEND_NAMES)
                    assert _percent_literature(legend) == [], (where, legend)
                    if lit:
                        assert set(LITERATURE_LEGEND.values()) <= set(legend), (where, legend)
                        lit_tips, lit_heads, rise = {}, {}, {}
                        # A curve's points inside its own grid (part of it is clipped above the top), up to 40 of
                        # them spread along it: a window marker or a fitted curve can lie over any one of them.
                        chart = page.evaluate(_BOXES, "plot-res-scaling")["chart"]
                        grids = [{k: v + (chart["left"] if k in ("left", "right") else chart["top"])
                                  for k, v in r.items()} for r in view["rects"]]
                        for run in page.evaluate(_RES_LIT_RUNS):
                            panel = "ratio" if run["ratio"] else "main"
                            particle = LITERATURE[run["key"]][0]
                            box = grids[1 if run["ratio"] else 0]
                            inside = [pt for pt in run["px"] if _within(pt, box)]
                            # How far the curve rises above the grid's floor, in pixels, where it is drawn.
                            rise[(run["key"], panel)] = max((box["bottom"] - y for _, y in inside), default=0)
                            step = max(1, len(inside) // 40)
                            for got in _hover_points(page, inside[step // 2::step], where):
                                found.append(got)
                                head = _noise_tip_lines(got[1]["text"])[0]
                                lit_heads.setdefault((run["key"], panel), []).append(head)
                                if head == f"{particle} literature curve" or head.startswith(f"{particle} literature curve ÷ "):
                                    lit_tips[(run["key"], panel)] = got[1]["text"]
                                    break
                        for key, (particle, eq) in LITERATURE.items():
                            text = lit_tips.get((key, "main"))
                            if text is None and rise.get((key, "main"), 0) < LIT_SQUEEZED_PX:
                                # Under a tall axis both curves lie in the panel's bottom pixels, on the axis line
                                # and on each other (robust, 0 to 5,500% on the recording): nothing to hover apart.
                                squeezed["literature squeezed"] += 1
                                continue
                            assert text is not None, (where, key, "no main-panel literature tooltip read",
                                                      lit_heads, rise, view["y"][0])
                            lines = _noise_tip_lines(text)
                            assert lines[1] == eq, (where, key, lines[:3])
                            assert f", {REFERENCE_UNITS}; no interval reported;" in _flat(text), (where, key, text[:400])
                            seen["literature tips"] += 1
                        for (key, panel), text in lit_tips.items():
                            # The other curve on the ratio panel writes both equations and their units (FX-browser's
                            # finding, 2026-11-15); its caret, which writes no equation, may be the one hovered.
                            line = _noise_tip_lines(text)[1]
                            if panel != "ratio" or line.startswith("It leaves the ratio axis"):
                                continue
                            assert line.startswith(f"{LITERATURE[key][1]} divided by σ/E = ") \
                                and f" (in both, {REFERENCE_UNITS}): " in line, (where, key, line)
                            seen["literature ratio tips"] += 1
                        assert any(panel == "main" for _, panel in lit_tips), (where, sorted(lit_tips), lit_heads)
                        assert any(panel == "ratio" for _, panel in lit_tips), (where, sorted(lit_tips))

                    # Every window: its SE line names the one pooled scale (D3).
                    windows = _hover_windows(page)
                    found += windows
                    assert found, where
                    texts = [probe["text"] for _, probe, _ in found]
                    seen["tips"] += len(texts)
                    _, weighted, low, _ = _se_lines([probe["text"] for _, probe, _ in windows], payload, where)
                    if est != "sample":
                        assert weighted and low, (where, "no 1–4 GeV window's tooltip read", weighted, low)
                        seen["low"] += low
                    for text in texts:
                        flat = _flat(text)
                        assert "envelope" not in flat.lower() and "c_low" not in flat, (where, flat[:300])
                        assert "The band is" not in flat and "95% confidence band" not in flat, (where, flat[:300])
                        if ENERGY_NO_BAND_TEXT in flat:
                            assert flat.count(ENERGY_NO_BAND_TEXT) == 1, (where, flat[-400:])
                            assert _noise_tip_lines(text)[0] in by_label, (where, flat[:120])
                    assert _says_exact(texts) == [], (where, _says_exact(texts))
                    assert _hyphen_negatives(texts) == [], (where, _hyphen_negatives(texts))
                    assert _percent_literature(texts) == [], (where, _percent_literature(texts)[:2])
                    assert _unitless_literature(texts) == [], (where, _unitless_literature(texts)[:2])
                    _assert_capped(page, found, where)

                    # The drawer: the no-band sentence once, no envelope, no second scale; the pooled-scale line
                    # ends with the clause on the 1–4 GeV windows (review-stats S2) under median and robust only;
                    # the literature transcription line names the units.
                    _, _, body = _drawer(page, "res-scaling")
                    flat = _flat(body)
                    assert flat.count(DRAWER_NO_BAND) == 1, (where, flat[:600])
                    assert "envelope" not in flat.lower() and "c_low" not in flat, (where, flat[:600])
                    assert flat.count(POOLED_CLAUSE) == (0 if est == "sample" else 1), (where, flat[:900])
                    assert flat.count(LITERATURE_TRANSCRIBED) == (1 if lit else 0), (where, flat[-900:])
                    assert _percent_literature([body]) == [], where
                    seen["drawers"] += 1
            assert _res_press(page, "res-windows", "anchors")
            _set_literature(page, True)
            assert requests[mark:] == [], f"{scheme}, {est}: a card control asked the service: {requests[mark:]}"
        print(f"res-scaling single curve, {scheme}: {seen}, {squeezed}")
        assert all(seen.values()), seen
        assert [q.get("estimator") for q in _requests_of(requests, "/api/resolution-scaling")] == list(RES_ESTIMATORS)
        browser.close()
    assert problems == [], problems


# ------------------------------------------------- the resolution card's legend --

#: The legend entry switched off, in the recorded two-shower response: every mark of shower A's energy network
#: (markers, whiskers, carets and fitted lines, with bands in the 1/√E view, on both grids in the E view) carries it. Martin switched off
#: the calibrated deposit (2026-11-11); under the default median estimator the recorded deposits tie (bootstrap SE
#: below 10⁻⁶ of the value), carry no fit weight and in the 3-anchor mode draw nothing (review-ui M1), so the tests
#: take the network, which every estimator draws and fits in both window modes.
LEGEND_ENTRY = "Shower A · Energy network · absolute frame"
#: Another entry, on show while LEGEND_ENTRY is hidden: the export keeps it, and its legend lists it.
LEGEND_ON_SHOW = "Shower B · Energy network · absolute frame"

#: The resolution card as ECharts drew it: per series, its id, its name, whether the legend filters it, its data
#: items and the elements its view holds now; the legend's selected state.
_RES_DRAWN = """() => {
  const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
  const model = inst.getModel();
  const series = model.getSeries().map((s) => {
    let drawn = 0;
    inst.getViewOfSeriesModel(s)?.group?.traverse((el) => { if (!el.isGroup) drawn += 1; });
    return [s.id, s.name, model.isSeriesFiltered(s), s.getData().count(), drawn];
  });
  const legend = model.getComponent('legend');
  return { series, selected: legend ? { ...(legend.option.selected || {}) } : null };
}"""

#: Where the resolution card's legend draws an entry's name, in viewport pixels: the centre of its text.
_LEGEND_ITEM = """(name) => {
  const host = document.getElementById('plot-res-scaling');
  const inst = echarts.getInstanceByDom(host);
  const legend = inst.getModel().getComponent('legend');
  const view = legend && inst.getViewOfComponentModel(legend);
  if (!view) return null;
  const c = host.getBoundingClientRect();
  let at = null;
  view.group.traverse((el) => {
    if (at || el.type !== 'text' || el.style?.text !== name) return;
    const r = el.getPaintRect();
    at = [c.left + r.x + r.width / 2, c.top + r.y + r.height / 2];
  });
  return at;
}"""

#: Every chart the export builds (SVG, or the PNG's own canvas chart), its legend state (the first legend's
#: selected map, and every legend's listed names and whether it is shown), which of its series the legend filters
#: when serialised, and its grids' tops.
_WATCH_EXPORT_LEGEND = """() => {
  if (window.__exportLegend) return;
  window.__exportLegend = [];
  const record = (chart, renderer) => {
    const model = chart.getModel();
    const o = chart.getOption();
    window.__exportLegend.push({
      renderer,
      selected: { ...((o.legend || [])[0]?.selected || {}) },
      legends: (o.legend || []).map((l) => ({ show: l.show !== false,
        names: (l.data || []).map((d) => (typeof d === 'string' ? d : d?.name)) })),
      series: model.getSeries().map((s) => [s.id, s.name, model.isSeriesFiltered(s)]),
      gridTops: (o.grid || []).map((g) => g.top),
      height: chart.getHeight(),
    });
  };
  const init = echarts.init;
  echarts.init = function (dom, theme, opts) {
    const chart = init.call(this, dom, theme, opts);
    if (opts && opts.renderer === 'svg') {
      const render = chart.renderToSVGString.bind(chart);
      chart.renderToSVGString = (...args) => {
        record(chart, 'svg');
        return render(...args);
      };
    } else if (opts && opts.renderer === 'canvas') {
      const url = chart.getDataURL.bind(chart);
      chart.getDataURL = (...args) => {
        record(chart, 'png');
        return url(...args);
      };
    }
    return chart;
  };
}"""


def _click_legend(page, name):
    """Click a legend entry of the resolution card, as a reader does (ECharts dispatches `legendToggleSelect`)."""
    at = page.evaluate(_LEGEND_ITEM, name)
    assert at is not None, f"no legend entry {name!r} on the resolution card"
    page.mouse.click(*at)
    page.mouse.move(2, 2)
    _frames(page)


def _drawn(page):
    """The resolution card as drawn: {series id: (name, filtered, items, elements)} and the legend's selected map."""
    got = page.evaluate(_RES_DRAWN)
    return {sid: (name, filtered, items, drawn) for sid, name, filtered, items, drawn in got["series"]}, got["selected"]


def _assert_hidden(drawn, fresh, where):
    """The entry's series are all filtered and draw nothing; every other series draws as a fresh render did."""
    series, selected = drawn
    assert selected.get(LEGEND_ENTRY) is False, (where, selected)
    own = {sid for sid, (name, *_) in series.items() if name == LEGEND_ENTRY}
    assert own, (where, "no series of the entry", sorted(series))
    for sid, (name, filtered, items, elements) in series.items():
        if sid in own:
            assert filtered and elements == 0, (where, sid, filtered, elements)
        else:
            assert not filtered and (name, False, items, elements) == fresh[sid], (where, sid, fresh.get(sid),
                                                                                (name, filtered, items, elements))


@pytest.mark.parametrize("view", ["linear", "energy"])
def test_a_series_switched_off_on_the_legend_stays_off_across_the_window_switch_and_comes_back_whole(
        models_live_server, view):
    """Martin's bug 3 (2026-11-11), in both views of the resolution card on the recorded two-shower response.

    A series switched off on the legend, then "All" → "3 anchors": its markers came back, its lines and bands did
    not. The window switch is a repaint with notMerge, which forgot the legend, and ECharts 5.5.1 threw inside the
    render (a custom series view the legend had emptied removing a detached element), so every series after the
    throw stayed undrawn. Now the entry stays off across All → anchors → All → anchors, with no page error; switched
    back on, every one of its series (markers, whiskers, carets, lines, bands) draws exactly what a fresh render of
    that window mode draws, and so does every other series; no request is made. The last anchors switch is what
    catches a memory without the clear: the entry's views then hold the more numerous items of the "All" render."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        # Each view pressed: the card opens on the E view (res-emax), so the 1/√E case asks for its own.
        assert _res_press(page, "res-view", view)
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        before = len(requests)

        # Fresh renders of both window modes, nothing switched off: what each draws, series by series.
        assert _res_press(page, "res-windows", "anchors")
        fresh = {"anchors": _drawn(page)[0]}
        assert _res_press(page, "res-windows", "all")
        fresh["all"] = _drawn(page)[0]
        own = sorted(sid for sid, (name, *_) in fresh["all"].items() if name == LEGEND_ENTRY)
        assert any(fresh["all"][sid][3] for sid in own), own
        # The entry draws fitted lines in both modes, as well as its markers: what the bug lost. In the 1/√E view
        # its fits carry bands, a wash or its two edges where it spans half its axis or more (OUTLINE_SHARE); the E
        # view draws its one curve, a/√E ⊕ b ⊕ c/E, and no band (Martin's directive of 2026-11-15).
        for mode in ("anchors", "all"):
            drawn = [sid for sid, (name, _, _, elements) in fresh[mode].items() if name == LEGEND_ENTRY and elements]
            if view == "linear":
                assert any("|pinned|line|" in sid for sid in drawn), (mode, drawn)
                assert any("|band" in sid or "|edges|" in sid for sid in drawn), (mode, drawn)
            else:
                assert any("|noise|solid|" in sid for sid in drawn), (mode, drawn)
                assert not any("|pinned|" in sid or "|band" in sid or "|edges|" in sid for sid in drawn), (mode, drawn)
        # The switch removes items from a series of the entry: the path ECharts threw on.
        assert any(sid in fresh["anchors"] and fresh["anchors"][sid][2] < fresh["all"][sid][2] for sid in own), \
            {sid: (fresh["anchors"].get(sid), fresh["all"][sid]) for sid in own}

        _click_legend(page, LEGEND_ENTRY)
        _assert_hidden(_drawn(page), fresh["all"], f"{view}: switched off")
        # Off and on again: each click repaints the card (legend-sliders); back on, the entry draws again, all of it.
        _click_legend(page, LEGEND_ENTRY)
        assert _drawn(page) == (fresh["all"], {LEGEND_ENTRY: True}), view
        _click_legend(page, LEGEND_ENTRY)
        _assert_hidden(_drawn(page), fresh["all"], f"{view}: switched off again")
        for mode in ("anchors", "all", "anchors"):
            assert _res_press(page, "res-windows", mode)
            _assert_hidden(_drawn(page), fresh[mode], f"{view}: switched off, then {mode}")
            assert problems == [], (view, mode, problems)

        # Back on, in the anchors mode: every series draws as the fresh render did, the entry's lines and bands too.
        # Without the clear, this is where ECharts threw (a view holding the "All" render's detached elements).
        _click_legend(page, LEGEND_ENTRY)
        assert problems == [], (view, "switched back on", problems)
        series, selected = _drawn(page)
        assert selected.get(LEGEND_ENTRY) is True, selected
        assert series == fresh["anchors"], {s: (series.get(s), fresh["anchors"].get(s))
                                           for s in set(series) | set(fresh["anchors"])
                                           if series.get(s) != fresh["anchors"].get(s)}
        assert _res_press(page, "res-windows", "all")
        assert _drawn(page)[0] == fresh["all"]
        assert requests[before:] == [], f"a render-only control asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


@pytest.mark.parametrize("view", ["linear", "energy"])
def test_a_series_switched_off_on_the_legend_stays_off_across_a_theme_switch_and_out_of_the_export(
        models_live_server, view):
    """Martin's bug 2 (2026-11-11): a series switched off on the legend came back on a theme switch, whose repaint
    (setOption with notMerge) forgot the legend. Now it stays off in the light theme and again in the dark one, with
    no request; switched on again it draws whole, and off again it keeps the reader's last choice. The export
    follows the screen and describes only what is on show (Martin's decision of 2026-11-17, replacing the greyed
    entry of 2026-11-11): its legend lists every entry the whole figure listed but the hidden one, and marks that
    one off; no series of the entry is drawn (the E view leaves them out, the 1/√E view's legend filters them) and
    no other is filtered; no text of the SVG names the entry, and the entry on show is printed as it was."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        page.evaluate(_WATCH_EXPORT_LEGEND)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        # Each view pressed: the card opens on the E view (res-emax), so the 1/√E case asks for its own.
        assert _res_press(page, "res-view", view)
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        fresh, selected = _drawn(page)
        assert LEGEND_ENTRY not in selected, selected
        # The whole figure first: what an export prints with nothing switched off.
        _, whole_svg = _download_svg(page, "res-scaling")
        whole = page.evaluate("() => window.__exportLegend.at(-1)")
        whole_inks = {text: fill.lower()
                      for fill, text in re.findall(r'<text[^>]*?fill="([^"]+)"[^>]*>([^<]+)</text>', whole_svg)}
        assert LEGEND_ENTRY in whole_inks and LEGEND_ON_SHOW in whole_inks, sorted(whole_inks)
        before = len(requests)

        _click_legend(page, LEGEND_ENTRY)
        _assert_hidden(_drawn(page), fresh, f"{view}: switched off")
        for theme in ("light", "dark"):
            page.click("#theme-toggle")
            page.wait_for_function("(t) => document.documentElement.dataset.theme === t", arg=theme, timeout=10_000)
            _frames(page)
            # Still off, in the new ink; every other series draws as before the switch.
            _assert_hidden(_drawn(page), fresh, f"{view}: switched off, then the {theme} theme")
        assert requests[before:] == [], f"a theme switch asked the service: {requests[before:]}"

        # The export: the figure leaves the entry out with its legend entry, and its legend marks it off.
        name, svg = _download_svg(page, "res-scaling")
        assert name.startswith("res-scaling_") and name.endswith(".svg"), name
        exported = page.evaluate("() => window.__exportLegend.at(-1)")
        assert exported["selected"].get(LEGEND_ENTRY) is False, exported["selected"]
        listed = [n for legend in exported["legends"] for n in legend["names"]]
        whole_listed = [n for legend in whole["legends"] for n in legend["names"]]
        assert LEGEND_ENTRY in whole_listed and listed == [n for n in whole_listed if n != LEGEND_ENTRY], \
            (whole_listed, listed)
        # No series of the entry draws (the entry's key is network:a: its markers, whiskers, carets, curves, end
        # labels), and no other series is filtered.
        own = [(sid, filtered) for sid, sname, filtered in exported["series"]
               if sname == LEGEND_ENTRY or str(sid).startswith("network:a|")]
        if view == "linear":
            # The 1/√E view names every mark of a series after its entry: they are in the export, every one filtered
            # (never an empty list passing for a check; review R3-3).
            assert own, exported["series"]
        assert all(filtered for _, filtered in own), own
        assert not [sid for sid, sname, filtered in exported["series"] if filtered and (sid, filtered) not in own], \
            exported["series"]
        if view == "energy":
            # The E view leaves the entry's marks out of the export altogether (brief §5.7).
            assert own == [], own
        inks = {text: fill.lower() for fill, text in re.findall(r'<text[^>]*?fill="([^"]+)"[^>]*>([^<]+)</text>', svg)}
        # No text names the hidden entry, greyed or not (PRINT_INACTIVE is retired); the entry on show is printed
        # in the ink it had in the whole figure.
        assert not [t for t in inks if LEGEND_ENTRY in t], sorted(inks)
        assert inks.get(LEGEND_ON_SHOW) == whole_inks[LEGEND_ON_SHOW], (inks.get(LEGEND_ON_SHOW), whole_inks)

        # Back on, then off again: the memory holds the last click.
        _click_legend(page, LEGEND_ENTRY)
        assert _drawn(page) == (fresh, {LEGEND_ENTRY: True}), view
        _click_legend(page, LEGEND_ENTRY)
        _assert_hidden(_drawn(page), fresh, f"{view}: switched off again")
        assert requests[before:] == [], f"the legend asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


#: The ink of a hidden legend entry on each screen card (chart_panel.js `legendInactiveInk`, the faintest tint of the
#: muted ink at 4.5:1; tests/test_js_chart_legend.py derives them).
SCREEN_INACTIVE = {"dark": "#808993", "light": "#6e7780"}

#: How the resolution card's legend draws an entry: the legend's inks (text and swatch, swatch border, a line series'
#: swatch line) and the colours the entry's text and swatch are painted in now. A line paints its stroke only, and so
#: does a hollow symbol, whose interior ECharts fills with a fixed #fff in either state.
_RES_LEGEND_INK = """(name) => {
  const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
  const legend = inst.getModel().getComponent('legend');
  const out = { inks: [legend.get('inactiveColor'), legend.get('inactiveBorderColor'),
    legend.get(['lineStyle', 'inactiveColor'])], text: null, swatch: [] };
  inst.getViewOfComponentModel(legend)?.group.traverse((el) => {
    if (out.text !== null || el.type !== 'text' || el.style?.text !== name) return;
    out.text = el.style.fill;
    el.parent?.traverse((part) => {
      if (part === el || part.isGroup || part.invisible || part.type === 'text') return;
      const symbol = String(part.shape?.symbolType ?? '');
      const line = part.type === 'line' || symbol === 'line' || part.__isEmptyBrush === true;
      for (const paint of line ? [part.style?.stroke] : [part.style?.fill, part.style?.stroke]) {
        if (paint && paint !== 'none' && paint !== 'transparent') out.swatch.push(paint);
      }
    });
  });
  return out;
}"""

#: The open drawer's sections, as [heading, [lines]].
_DRAWER_SECTIONS = """() => [...document.querySelectorAll('#inspector-body .inspector-section')].map((s) =>
  [s.querySelector('h3').textContent, [...s.querySelectorAll('p')].map((p) => p.textContent)])"""


def test_the_open_drawer_names_the_series_the_legend_hides_and_the_entry_stays_legible(models_live_server):
    """Martin's approval (2026-11-11), on the resolution card's recorded two-shower response, with its drawer open.

    Switched off with a click, the entry is drawn, text and swatch, in the legible inactive ink of the card (4.5:1 on
    #1c2128 and on white), never the 1.33:1 border; the drawer's Marks and legend section gains one line naming it,
    first, the rest of the drawer unchanged and no hazard raised. A switch to the light theme repaints it in the
    light card's ink and keeps the line. Switched back on, the drawer is as it was. No request."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        details = '.main button[data-inspect="res-scaling"]'
        page.click(details)
        page.wait_for_function("() => !document.getElementById('inspector').hidden")
        _frames(page)
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        opened = dict(page.evaluate(_DRAWER_SECTIONS))
        assert opened.get("Marks and legend"), list(opened)
        flagged = page.get_attribute(details, "class")
        line = (f"Hidden on the legend by the reader: {LEGEND_ENTRY}. Click its entry to show it again; "
                "an export leaves it out.")
        before = len(requests)

        _click_legend(page, LEGEND_ENTRY)
        hidden = dict(page.evaluate(_DRAWER_SECTIONS))
        assert hidden["Marks and legend"] == [line, *opened["Marks and legend"]], hidden["Marks and legend"]
        assert {k: v for k, v in hidden.items() if k != "Marks and legend"} == \
            {k: v for k, v in opened.items() if k != "Marks and legend"}
        assert page.get_attribute(details, "class") == flagged, "the reader's own choice raised a hazard"
        for theme in ("dark", "light"):
            if theme == "light":
                page.click("#theme-toggle")
                page.wait_for_function("(t) => document.documentElement.dataset.theme === t", arg=theme,
                                       timeout=10_000)
                _frames(page)
                assert dict(page.evaluate(_DRAWER_SECTIONS))["Marks and legend"][0] == line, theme
            ink = SCREEN_INACTIVE[theme]
            got = page.evaluate(_RES_LEGEND_INK, LEGEND_ENTRY)
            assert got["inks"] == [ink, ink, ink], (theme, got)
            assert got["text"] == ink and got["swatch"] and set(got["swatch"]) == {ink}, (theme, got)
        page.click("#theme-toggle")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'", timeout=10_000)
        _frames(page)

        _click_legend(page, LEGEND_ENTRY)
        assert dict(page.evaluate(_DRAWER_SECTIONS)) == opened
        assert requests[before:] == [], f"the legend or the theme asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


# --------------------------- the resolution card's defaults, E max and Deposit (res-emax) --

#: What the E view draws against E max: every series datum's E beyond `eMax` (end labels apart, whose datum sits at
#: the axis end by design), the end labels' data E, and every painted point beyond the pixel of E max on its own
#: grid (a polyline's or a line's points, a caret's centroid, any other element's centre), end labels apart, which
#: are drawn in the column beside the plot.
_RES_BEYOND = """(eMax) => {
  const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
  const o = inst.getOption();
  const out = { data: [], endLabels: [], paint: [], painted: 0 };
  for (const s of o.series || []) {
    const id = s.id ?? s.name;
    for (const d of s.data || []) {
      const x = Array.isArray(d) ? d[0] : (Array.isArray(d?.value) ? d.value[0] : null);
      if (typeof x !== 'number' || !Number.isFinite(x)) continue;
      if (/\\|endlabels$/.test(id)) out.endLabels.push(x);
      else if (x > eMax + 1e-9) out.data.push([id, x]);
    }
  }
  inst.getModel().eachSeries((s) => {
    const id = s.get('id') || s.name;
    if (/\\|endlabels$/.test(id)) return;
    const limit = inst.convertToPixel({ xAxisIndex: s.get('xAxisIndex') ?? 0 }, eMax);
    inst.getViewOfSeriesModel(s)?.group?.traverse((el) => {
      if (el.isGroup || el.invisible || el.ignore) return;
      el.updateTransform();
      const g = (x, y) => el.transformCoordToGlobal(x, y)[0];
      const sh = el.shape || {};
      let xs;
      if (Array.isArray(sh.points) && sh.points.length) {
        xs = el.type === 'polygon'
          ? [g(sh.points.reduce((t, p) => t + p[0], 0) / sh.points.length, sh.points.reduce((t, p) => t + p[1], 0) / sh.points.length)]
          : sh.points.map((p) => g(p[0], p[1]));
      } else if (Number.isFinite(sh.x1)) {
        xs = [g(sh.x1, sh.y1), g(sh.x2, sh.y2)];
      } else {
        const r = el.getBoundingRect();
        xs = [g(r.x + r.width / 2, r.y + r.height / 2)];
      }
      out.painted += 1;
      const far = Math.max(...xs);
      if (far > limit + 0.5) out.paint.push([id, el.type, far - limit]);
    });
  });
  return out;
}"""

#: Every series that paints on the ratio panel (yAxisIndex 1) with its painted element count, and the end labels'
#: texts as drawn.
_RES_PANEL_MARKS = """() => {
  const inst = echarts.getInstanceByDom(document.getElementById('plot-res-scaling'));
  const out = { ratio: [], endLabels: [] };
  inst.getModel().eachSeries((s) => {
    const id = s.get('id') || '';
    let n = 0;
    const texts = [];
    inst.getViewOfSeriesModel(s)?.group?.traverse((el) => {
      if (el.isGroup || el.invisible || el.ignore) return;
      n += 1;
      if (el.type === 'text' && el.style?.text) texts.push(el.style.text);
    });
    if ((s.get('yAxisIndex') ?? 0) === 1 && n) out.ratio.push([id, n]);
    if (/\\|endlabels$/.test(id)) out.endLabels.push(...texts);
  });
  return out;
}"""

#: The ratio panel's y axis as the option holds it: whether it draws labels, ticks and split lines, and its name.
_RES_RATIO_AXIS = """() => {
  const a = (echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().yAxis || [])[1] || {};
  return { type: a.type, name: a.name ?? '', labels: a.axisLabel?.show !== false, ticks: a.axisTick?.show !== false,
           split: a.splitLine?.show === true, values: a.axisLabel?.customValues ?? null };
}"""

#: The time from one `input` event on the E max slider to the chart's two x axes ending at the new value, in ms
#: (the event coalesced to the next animation frame's repaint, polled on the frame clock); null after 5 s.
_EMAX_LATENCY = """([sel, v]) => new Promise((done) => {
  const input = document.querySelector(`${sel} input`);
  const t0 = performance.now();
  input.value = String(v);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  const check = () => {
    const x = echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().xAxis || [];
    if (x.length === 2 && x.every((a) => a.max === v)) done(performance.now() - t0);
    else if (performance.now() - t0 > 5000) done(null);
    else requestAnimationFrame(check);
  };
  check();
})"""

#: The E view's x axis ticks at each E max the tests set (res_axis.js eAxisTicks: every 5 GeV up to 40, every 10
#: above, the end always ticked; at the server's end, the server's interval).
E_TICKS = {20: [0, 5, 10, 15, 20], 45: [0, 10, 20, 30, 40, 45], 80: [0, 10, 20, 30, 40, 50, 60, 70, 80]}


def _svg_texts(svg):
    """Every <text> of an SVG figure, unescaped."""
    return [html.unescape(t) for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg)]


def _download_png(page, panel_id):
    """Export a card as a 300 dpi single-column PNG; its file name and bytes."""
    page.click(f'button[data-export="{panel_id}"]')
    page.wait_for_selector(".menu")
    with page.expect_download() as download:
        page.click(".menu-item:has-text('PNG 300 DPI — single column')")
    with open(download.value.path(), "rb") as handle:
        return download.value.suggested_filename, handle.read()


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_resolution_card_opens_on_the_e_view_with_the_deposit_hidden_and_e_max_at_the_datas_edge(
        models_live_server, scheme):
    """res-emax (Martin's decisions of 2026-11-17; brief §6.1, CLAUDE.md §5 "Its defaults"), on the recorded
    two-shower response in both themes: one /api/resolution-scaling request, under the median; the title "Median
    Relative Error vs. E"; pressed: the E (GeV) + ratio view, Median |rel. err.|, 3 anchors, Both showers and both
    literature curves, the Deposit button not pressed (its title verbatim); the E max slider laid out with 20–80 GeV
    in 5 GeV steps, at 20, "20 GeV", its name, title and aria-label verbatim; both x axes from 0 to 20 ticked
    [0, 5, 10, 15, 20]; no deposit series, legend entry, fit-table row or chart text; the y range the model series'
    own (`axis.energy.y_model`); the curves within the 20 GeV axis; a 600 px plot."""
    payload = _fixture_payload(RES_TWO)
    energy = payload["axis"]["energy"]
    assert _default_emax(payload) == 20 and energy["x"]["max"] == 80, energy["x"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE, scheme=scheme)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
        asked = _requests_of(requests, "/api/resolution-scaling")
        assert len(asked) == 1 and asked[0].get("estimator") == "median", _urls(requests)
        before = len(requests)

        chrome = page.evaluate(_RES_CHROME)
        assert chrome["title"] == "Median Relative Error vs. E", chrome
        assert chrome["height"] == 600 and chrome["styleHeight"] == "600px", chrome
        assert _res_pressed(page) == {
            "View": ["E (GeV) + ratio"], "Estimator": ["Median |rel. err.|"], "Windows": ["3 anchors"],
            "Showers": ["Both"], "Benchmark": [], "Literature curves": ["π±", "e±"],
        }, _res_pressed(page)
        button = page.locator(RES_DEPOSIT)
        assert button.text_content() == "Deposit" and button.get_attribute("aria-pressed") == "false"
        assert not button.is_disabled() and button.get_attribute("title") == RES_DEPOSIT_TITLE
        emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
        assert emax == {
            "hidden": False, "shown": True, "type": "range", "disabled": False, "min": "20", "max": "80", "step": "5",
            "value": "20", "output": "20 GeV", "name": "E max", "title": RES_EMAX_TITLE, "aria": RES_EMAX_ARIA,
        }, emax

        axes = page.evaluate(_RES_AXES)
        assert len(axes["x"]) == 2, axes["x"]
        for a in axes["x"]:
            assert (a["min"], a["max"]) == (0, 20) and a["ticks"] == a["values"] == E_TICKS[20], a
        ids = _res_ids(page)
        assert not [i for i in ids if str(i).startswith("detector:")], ids
        assert any(str(i).startswith("network:a|") for i in ids) and any(str(i).startswith("network:b|") for i in ids)
        legend = page.evaluate(_RES_LEGEND_NAMES)
        assert LEGEND_ENTRY in legend and LEGEND_ON_SHOW in legend, legend
        assert not [n for n in legend if "deposit" in n.lower()], legend
        rows = page.evaluate(_RES_TABLE)["rows"]
        assert rows and not [r for r in rows if "deposit" in r.lower()], rows
        assert not [t for t in page.evaluate(_CHART_TEXTS, "plot-res-scaling") if "deposit" in t.lower()]
        view = page.evaluate(_RES_ENERGY)
        assert view["y"][0]["max"] == energy["y_model"]["hi"], (view["y"][0], energy["y_model"])
        _assert_e_view_curves(view, payload, "anchors")
        assert page.evaluate(_RES_BEYOND, 20)["paint"] == []
        assert requests[before:] == [], f"reading the card asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


def test_the_e_max_slider_repaints_with_no_request_and_draws_nothing_beyond_it(models_live_server):
    """The E max slider (res-emax brief §5.4, §6.2; CLAUDE.md §5 "E max, the axis end") on the recorded two-shower
    response: moved to 45 and 80 by `input` events (coalesced to one repaint a frame) and back to 20 by a `change`,
    it sends no request; its value and its "<n> GeV" follow; both x axes end at it, ticked [0, 10, …, 40, 45] at 45
    and at the server's 10 GeV interval at 80; at every value no series datum, no painted point on either panel and
    no end label lies beyond it (the end labels sit at it), the curves keep their rules, and neither the y ranges nor
    the fit table move (no fit is refitted). The slider is hidden on the 1/√E view and back, at its value, on the E
    view. The time from one `input` event to the axes ending at the new value is measured over 12 moves, printed,
    and its median held under the 50 ms of CLAUDE.md §3."""
    payload = _fixture_payload(RES_TWO)
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        before = len(requests)
        start = page.evaluate(_RES_ENERGY)
        table = page.evaluate(_RES_TABLE)
        assert page.evaluate(_RES_BEYOND, 20)["paint"] == []

        for value, event in ((45, "input"), (80, "input"), (20, "change")):
            where = f"E max {value} ({event})"
            _set_emax(page, value, event)
            page.wait_for_function(
                """(v) => (echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().xAxis || [])
                  .every((a) => a.max === v)""", arg=value, timeout=10_000)
            _frames(page)
            emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
            assert emax["shown"] and emax["value"] == str(value) and emax["output"] == f"{value} GeV", (where, emax)
            axes = page.evaluate(_RES_AXES)
            for a in axes["x"]:
                assert (a["min"], a["max"]) == (0, value) and a["ticks"] == a["values"] == E_TICKS[value], (where, a)
            beyond = page.evaluate(_RES_BEYOND, value)
            assert beyond["painted"] > 0 and beyond["data"] == [] and beyond["paint"] == [], (where, beyond)
            assert beyond["endLabels"] and all(x == pytest.approx(value) for x in beyond["endLabels"]), (where, beyond)
            view = page.evaluate(_RES_ENERGY)
            _assert_e_view_curves(view, payload, "anchors")
            # The ranges and the fits never depend on E max: it only cuts extrapolation.
            assert [(a["min"], a["max"]) for a in view["y"]] == [(a["min"], a["max"]) for a in start["y"]], where
            assert page.evaluate(_RES_TABLE) == table, where
        assert requests[before:] == [], f"the E max slider asked the service: {requests[before:]}"

        # The E view's alone: hidden on the 1/√E view, back at its value on the E view.
        assert _res_press(page, "res-view", "linear")
        emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
        assert emax["hidden"] and not emax["shown"], emax
        assert _res_press(page, "res-view", "energy")
        emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
        assert emax["shown"] and emax["value"] == "20" and emax["output"] == "20 GeV", emax

        # How long one `input` takes to reach the axes: the repaint of the next animation frame.
        times = []
        for value in (25, 30, 35, 40, 50, 60, 70, 80, 65, 45, 30, 20):
            got = page.evaluate(_EMAX_LATENCY, [RES_EMAX, value])
            assert got is not None, f"the axes never reached E max {value}"
            times.append(got)
            _frames(page)
        times.sort()
        print(f"E max input to axes: median {times[len(times) // 2]:.1f} ms, max {times[-1]:.1f} ms over "
              f"{len(times)} moves: {[round(t, 1) for t in times]}")
        # CLAUDE.md §3: client-side UI latency below 50 ms (review R3-7a), on the median of the moves.
        assert times[len(times) // 2] < 50, times
        assert requests[before:] == [], f"the E max slider asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


def test_the_e_max_slider_answers_the_keyboard_keeps_its_focus_and_fits_the_toolbar_at_1024_px(models_live_server):
    """Review R3-7: the E max slider driven by real keys (ArrowRight, End, Home) moves in its 5 GeV steps between the
    data's edge and the server's end, the axes follow, the input keeps the focus across each repaint, and no request
    is sent; at 1024 × 768 the card's toolbar, the slider in it, stays inside the card (brief §6.4)."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE, viewport=(1024, 768))
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        found = page.evaluate(_OVERFLOW)
        assert "res-scaling" not in json.dumps(found["cards"]), found
        assert page.evaluate(_RES_EMAX_STATE, RES_EMAX)["shown"]
        before = len(requests)
        page.focus(f"{RES_EMAX} input")
        steps = []
        for key, value in (("ArrowRight", 25), ("ArrowRight", 30), ("End", 80), ("Home", 20)):
            page.keyboard.press(key)
            page.wait_for_function(
                """(v) => (echarts.getInstanceByDom(document.getElementById('plot-res-scaling')).getOption().xAxis || [])
                  .every((a) => a.max === v)""", arg=value, timeout=10_000)
            _frames(page)
            emax = page.evaluate(_RES_EMAX_STATE, RES_EMAX)
            focused = page.evaluate("(sel) => document.activeElement === document.querySelector(sel + ' input')", RES_EMAX)
            steps.append((key, emax["value"], emax["output"], focused))
            assert (emax["value"], emax["output"]) == (str(value), f"{value} GeV"), (key, emax)
            assert focused, (key, "the slider lost the focus in the repaint")
        assert requests[before:] == [], f"the keyboard asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


def test_the_deposit_toggle_shows_the_deposit_and_its_range_on_both_views_with_no_request(models_live_server):
    """The Deposit toggle (res-emax brief §5.2-§5.3, §6.2; CLAUDE.md §5 "The Deposit toggle") on the recorded XGBoost
    aggregate's response, whose deposit sets a wider range than the XGBoost series (E view 90% against 24%, 1/√E
    view 90% against 9%): off, on and off again in each view, no request; on, the deposit's series, legend entry and
    fit-table row are drawn and the y range is the full one (`axis.energy.y`, `axis.y`); off, none of them, and the
    range is the model series' own (`axis.energy.y_model`, `axis.y_model`). On the recorded deposit-only single-shower
    hits the button is shut and pressed, its title the forced reason, and the deposit is drawn in both views."""
    payload = _fixture_payload("xgb")
    deposit = next(s["label"] for s in payload["series"] if s["source"] == "detector")
    axis = payload["axis"]
    ranges = {"energy": (axis["energy"]["y"]["hi"], axis["energy"]["y_model"]["hi"]),
              "linear": (axis["y"]["hi"], axis["y_model"]["hi"])}
    assert all(full != model for full, model in ranges.values()), ranges
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], MODELS_XGB_TABLE)
        _serve_res_fixture(page, "xgb")
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert len(_requests_of(requests, "/api/resolution-scaling")) == 1, _urls(requests)
        before = len(requests)
        button = page.locator(RES_DEPOSIT)
        for view in ("energy", "linear"):
            assert _res_press(page, "res-view", view)
            for on in (False, True, False):
                where = f"{view} view, deposit {'on' if on else 'off'}"
                assert _res_deposit(page, on) is on, where
                assert not button.is_disabled() and button.get_attribute("title") == RES_DEPOSIT_TITLE, where
                page.evaluate(_SCROLL_START, "res-scaling")
                _frames(page)
                ids = _res_ids(page)
                assert any(str(i).startswith("detector:") for i in ids) is on, (where, ids)
                assert any(str(i).startswith("xgb:") for i in ids), (where, ids)
                legend = page.evaluate(_RES_LEGEND_NAMES)
                assert (deposit in legend) is on, (where, legend)
                rows = page.evaluate(_RES_TABLE)["rows"]
                assert any(deposit in r for r in rows) is on and rows, (where, rows)
                y = page.evaluate(_RES_ENERGY)["y"][0] if view == "energy" else page.evaluate(_RES_AXES)["y"][0]
                full, model = ranges[view]
                assert y["max"] == (full if on else model), (where, y, ranges[view])
        assert requests[before:] == [], f"the Deposit toggle asked the service: {requests[before:]}"
        browser.close()

        # The deposit as the response's only series: forced on, the button shut and pressed with the reason.
        browser, page, problems_single, requests = _open(p, models_live_server["base"], SINGLE_HITS_TABLE)
        _serve_res_fixture(page, "single_hits")
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        button = page.locator(RES_DEPOSIT)
        for view in ("energy", "linear"):
            assert _res_press(page, "res-view", view)
            assert button.is_disabled() and button.get_attribute("aria-pressed") == "true", view
            assert button.get_attribute("title") == RES_DEPOSIT_FORCED, view
            assert any(str(i).startswith("detector:") for i in _res_ids(page)), (view, _res_ids(page))
        # A name with the deposit drawn carries no deposit-off.
        name, _ = _download_svg(page, "res-scaling")
        assert "deposit-off" not in name, name
        browser.close()
    assert problems == [], problems
    assert problems_single == [], problems_single


def test_with_the_deposit_hidden_and_no_literature_curve_the_ratio_panel_draws_no_ratio(models_live_server):
    """No reference, no ratio (res-emax brief §5.5; CLAUDE.md §5 "No reference, no ratio"), on the recorded
    two-shower response: the deposit hidden and both literature curves switched off, the ratio panel paints no mark
    and no 1.0 rule (no `ratio|unity` series, no `|ratio|` series with data), its y axis has no labels, ticks, split
    lines or name, and one sentence says "No ratio drawn: no reference is on show. Switch on π±, e± or the deposit
    to draw one." (the second sentence on screen only); no hazard says the ratio range is provisional. e± back on
    brings the ratio marks, the rule and the axis back. No request."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        before = len(requests)
        assert not _res_deposit(page, False)
        # Drawn first, against the farther curve: the panel holds ratio marks and the rule.
        marks = page.evaluate(_RES_PANEL_MARKS)
        assert any("|ratio|markers" in i for i, _ in marks["ratio"]) and any(i == "ratio|unity" for i, _ in marks["ratio"])
        _set_literature(page, False)
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)

        note = _res_note(page)
        assert _flat(RATIO_NONE_TEXT + RATIO_NONE_SCREEN_TEXT) in note, note
        assert "ratio|unity" not in _res_ids(page), _res_ids(page)
        data = json.loads(page.evaluate(_RES_SERIES))
        assert not [i for i, d in data if "|ratio|" in str(i) and d], [i for i, d in data if "|ratio|" in str(i)]
        assert page.evaluate(_RES_PANEL_MARKS)["ratio"] == [], page.evaluate(_RES_PANEL_MARKS)
        axis = page.evaluate(_RES_RATIO_AXIS)
        assert axis["type"] == "log" and axis["name"] == "" and not axis["labels"] and not axis["ticks"] \
            and not axis["split"], axis
        details = page.evaluate(_DETAILS, "res-scaling")
        assert "provisional ratio range" not in details["title"], details
        # The same picture is not rescaled: the main panel keeps its axes.
        view = page.evaluate(_RES_ENERGY)
        assert view["grids"] == 2 and view["x"][1]["max"] == 20, view["x"]

        # e± on: its ratio marks, the rule and a named axis come back.
        assert _res_press(page, "res-literature", "e")
        marks = page.evaluate(_RES_PANEL_MARKS)
        assert any("|ratio|markers" in i for i, _ in marks["ratio"]) and any(i == "ratio|unity" for i, _ in marks["ratio"])
        axis = page.evaluate(_RES_RATIO_AXIS)
        assert "e±" in axis["name"] and axis["labels"], axis
        assert RATIO_NONE_TEXT not in _res_note(page)
        assert requests[before:] == [], f"the toggles asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems


def test_the_resolution_cards_export_describes_only_what_is_on_show(models_live_server, tmp_path):
    """The export rule (Martin's decision of 2026-11-17; CLAUDE.md §5 "The export follows it, and describes only
    what is on show"; brief §5.7, §7) on the recorded two-shower response.

    - The default card's SVG holds no text of the hidden deposit, and its name carries energy, emax-20, deposit-off
      and est-median in that order.
    - Shower A's energy network switched off on the legend: the SVG holds no text of its entry and not its end label
      "A" (shower B's "B" stays); its legend lists every entry of the whole figure but that one and marks it off; no
      series of its key is in the figure. A PNG of the same state is a PNG, laid out from the same legend.
    - Both literature curves off with the deposit hidden: the SVG says "No ratio drawn: no reference is on show."
      without the screen's second sentence, and the name carries ratio-none.
    - On a copy of the response whose model-series E range is cut to 60% (so windows of both networks are off
      scale), the entry switched off takes its off-scale values out of the SVG's note band; shower B's stay."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        page.evaluate(_WATCH_EXPORT_LEGEND)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        before = len(requests)
        # On screen, both showers' curves end in a labelled column.
        assert sorted(set(page.evaluate(_RES_PANEL_MARKS)["endLabels"]) & {"A", "B"}) == ["A", "B"]

        name, svg = _download_svg(page, "res-scaling")
        texts = _svg_texts(svg)
        tokens = name.split("_")
        assert [t for t in tokens if t in ("energy", "emax-20", "deposit-off", "est-median")] == \
            ["energy", "emax-20", "deposit-off", "est-median"], name
        assert tokens.index("emax-20") == tokens.index("energy") + 1, name
        assert "_energy_emax-20_lit-pi-e_deposit-off_est-median_" in name, name
        assert not [t for t in texts if "deposit" in t.lower()], texts
        assert "A" in texts and "B" in texts and LEGEND_ENTRY in texts, texts
        whole = page.evaluate("() => window.__exportLegend.at(-1)")
        whole_listed = [n for legend in whole["legends"] for n in legend["names"]]

        _click_legend(page, LEGEND_ENTRY)
        name, svg = _download_svg(page, "res-scaling")
        texts = _svg_texts(svg)
        exported = page.evaluate("() => window.__exportLegend.at(-1)")
        assert not [t for t in texts if LEGEND_ENTRY in t] and "A" not in texts, texts
        assert "B" in texts and LEGEND_ON_SHOW in texts, texts
        listed = [n for legend in exported["legends"] for n in legend["names"]]
        assert listed == [n for n in whole_listed if n != LEGEND_ENTRY] and len(listed) == len(whole_listed) - 1, \
            (whole_listed, listed)
        assert exported["selected"].get(LEGEND_ENTRY) is False, exported["selected"]
        assert not [sid for sid, *_ in exported["series"] if str(sid).startswith("network:a|")], exported["series"]
        # A PNG of the same state: a PNG, built from the same legend.
        png_name, png = _download_png(page, "res-scaling")
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and png_name.endswith(".png"), png_name
        printed = page.evaluate("() => window.__exportLegend.at(-1)")
        assert printed["renderer"] == "png" and printed["legends"] == exported["legends"], printed
        _click_legend(page, LEGEND_ENTRY)

        # No reference: the ratio panel's sentence, without the screen's call to act; ratio-none in the name.
        _set_literature(page, False)
        name, svg = _download_svg(page, "res-scaling")
        joined = _flat(" ".join(_svg_texts(svg)))
        assert RATIO_NONE_TEXT in joined and "Switch on" not in joined, joined[-400:]
        assert "_energy_emax-20_ratio-none_deposit-off_est-median_" in name, name
        assert requests[before:] == [], f"an export asked the service: {requests[before:]}"
        browser.close()

        # The off-scale list: a copy whose model-series E range ends at 60%.
        bodies = {}
        for est in RES_ESTIMATORS:
            served = _fixture_payload(RES_TWO, est)
            served["axis"]["energy"]["y_model"].update(hi=60.0, interval=10.0)
            bodies[est] = json.dumps(served)
        browser, page, problems_cut, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_bodies(page, bodies)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        note = _res_note(page)
        assert "off scale" in note and "A network" in note and "B network" in note, note
        _click_legend(page, LEGEND_ENTRY)
        _, svg = _download_svg(page, "res-scaling")
        joined = _flat(" ".join(_svg_texts(svg)))
        assert "off scale" in joined and "B network" in joined, joined[:600]
        assert "A network" not in joined, joined[:600]
        browser.close()
    assert problems == [], problems
    assert problems_cut == [], problems_cut


def _assert_carried(drawn, name, key, where):
    """The entry `name` is off and every mark of it has left the canvas (legend-sliders, Martin's decision of
    2026-11-17): the legend marks it off, exactly one series of its name is left (its legend carrier, the entry's
    first series), filtered and drawing nothing, and no other series of its key (`<key>|…`) is on the chart."""
    series, selected = drawn
    assert selected.get(name) is False, (where, selected)
    own = [(sid, v) for sid, v in series.items() if v[0] == name]
    assert len(own) == 1, (where, "not exactly one series of the entry (its legend carrier)", own)
    assert own[0][1][1] is True and own[0][1][3] == 0, (where, "the carrier is drawn", own)
    others = [sid for sid in series if str(sid).startswith(f"{key}|") and sid != own[0][0]]
    assert others == [], (where, "marks of the entry left on the chart", others)


def test_a_resolution_entry_switched_off_takes_its_end_label_and_off_scale_values_off_the_screen(models_live_server):
    """The screen draws what the export draws (legend-sliders, Martin's decision of 2026-11-17), on the resolution
    card's E view with the recorded two-shower response (the card's defaults: E view, deposit hidden, both showers).

    Shower B's energy network switched off with a click on its legend entry: after the repaint, every mark of its key
    (`network:b|…`) has left the chart but one legend carrier, filtered and drawing nothing; the end-label column
    holds "A" and no "B"; the legend still lists the entry, in the legible inactive ink. Switched back on, "B"
    returns and every series draws as the fresh render did. The recording draws no off-scale window, so the note band
    is checked on a copy whose model-series E range ends at 60% (as the export test does): both networks' off-scale
    values are named, and shower B's leave the note band with its entry and come back with it, shower A's staying.
    No request, no page error."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_fixture(page, RES_TWO)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        assert _res_press(page, "res-view", "energy")
        page.evaluate(_SCROLL_START, "res-scaling")
        _frames(page)
        fresh = _drawn(page)
        assert LEGEND_ON_SHOW not in fresh[1], fresh[1]
        labels = page.evaluate(_RES_PANEL_MARKS)["endLabels"]
        assert sorted(set(labels) & {"A", "B"}) == ["A", "B"], labels
        assert any(str(sid).startswith("network:b|") and v[3] for sid, v in fresh[0].items()), sorted(fresh[0])
        # The recording itself draws no off-scale window (what the note band would name).
        assert "off scale" not in _res_note(page), _res_note(page)
        before = len(requests)

        _click_legend(page, LEGEND_ON_SHOW)
        _assert_carried(_drawn(page), LEGEND_ON_SHOW, "network:b", "B switched off")
        labels = page.evaluate(_RES_PANEL_MARKS)["endLabels"]
        assert "A" in labels and "B" not in labels, labels
        assert LEGEND_ON_SHOW in page.evaluate(_RES_LEGEND_NAMES), page.evaluate(_RES_LEGEND_NAMES)
        ink = page.evaluate(_RES_LEGEND_INK, LEGEND_ON_SHOW)
        assert ink["text"] == SCREEN_INACTIVE["dark"] and set(ink["swatch"]) == {SCREEN_INACTIVE["dark"]}, ink

        _click_legend(page, LEGEND_ON_SHOW)
        assert problems == [], problems
        assert _drawn(page) == (fresh[0], {LEGEND_ON_SHOW: True})
        labels = page.evaluate(_RES_PANEL_MARKS)["endLabels"]
        assert sorted(set(labels) & {"A", "B"}) == ["A", "B"], labels
        assert requests[before:] == [], f"the legend asked the service: {requests[before:]}"
        browser.close()

        # The note band's off-scale values: a copy whose model-series E range ends at 60%.
        bodies = {}
        for est in RES_ESTIMATORS:
            served = _fixture_payload(RES_TWO, est)
            served["axis"]["energy"]["y_model"].update(hi=60.0, interval=10.0)
            bodies[est] = json.dumps(served)
        browser, page, problems_cut, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        _serve_res_bodies(page, bodies)
        state = _scroll_to(page, "res-scaling")
        assert state["message"] is None and state["canvas"], state
        note = _res_note(page)
        assert "off scale" in note and "A network" in note and "B network" in note, note
        before = len(requests)
        _click_legend(page, LEGEND_ON_SHOW)
        note = _res_note(page)
        assert "off scale" in note and "A network" in note and "B network" not in note, note
        _click_legend(page, LEGEND_ON_SHOW)
        note = _res_note(page)
        assert "A network" in note and "B network" in note, note
        assert requests[before:] == [], f"the legend asked the service: {requests[before:]}"
        browser.close()
    assert problems == [], problems
    assert problems_cut == [], problems_cut


# ---------------------------------------------------------------- 3-D views --


def test_the_3d_cards_render_in_swiftshader_with_at_most_two_gl_contexts(models_live_server):
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, SINGLE_HITS_TABLE, init=(_COUNT_GL,))
        # The Absolute frame draws the event pair alone: one context, and no cloud asked for.
        for card_id in EVENT_PAIR:
            state = _scroll_to(page, card_id)
            assert state["message"] is None, (card_id, state)
        page.wait_for_timeout(600)
        assert page.evaluate(_LIVE_GL) == ["vox-event"], page.evaluate(_LIVE_GL)
        assert not _requests_of(requests, "/api/voxels"), _urls(requests)
        # The card opens on the selection; one event, and a change of its channel, redraw on the same chart:
        # still one context. (The selection draws energy only here: species belong to one event.)
        page.click('.card[data-panel="vox-event"] [data-voxel-scope="event"]')
        _settled(page, "vox-event")
        page.wait_for_timeout(800)
        assert page.evaluate(_LIVE_GL) == ["vox-event"]
        page.select_option('.card[data-panel="vox-event"] select[data-voxel-channel]', "species")
        _settled(page, "vox-event")
        page.wait_for_timeout(800)
        assert page.evaluate(_LIVE_GL) == ["vox-event"]
        page.select_option('.card[data-panel="vox-event"] select[data-voxel-channel]', "energy")
        _settled(page, "vox-event")
        # Local draws both pairs, one at a time: one event (the scope in hand), then the cloud on the event card's
        # Selection, whose context is the second; the event's stays while the cloud is on show.
        _choose_frame(page, "local")

        def gl_card(card_id, cells):
            for cell in (card_id, *cells):
                state = _scroll_to(page, cell)
                assert state["message"] is None, (cell, state)
            state = page.evaluate(_CARD, card_id)
            # The plot's height follows its width and its box (P-18, voxels.js glPlotHeight).
            assert "bar3D" in state["seriesTypes"] and GL_HEIGHTS[0] <= state["height"] <= GL_HEIGHTS[1], state
            assert page.evaluate(f"() => echarts.getInstanceByDom(document.getElementById('plot-{card_id}'))"
                                 ".getOption().grid3D[0].viewControl.projection") == "orthographic"
            # The opening view is fitted to the box (test_the_3d_cards_open_fitted_to_their_box): the viewport
            # keeps the area left of the legend's aspect and covers it.
            zoom = page.evaluate(_ZOOM, card_id)
            assert zoom["vw"] / zoom["vh"] == pytest.approx((zoom["w"] - zoom["right"]) / zoom["h"], rel=2e-3), zoom
            assert zoom["left"] <= 0.05 and zoom["left"] + zoom["vw"] >= zoom["w"] - zoom["right"] - 0.05, zoom

        gl_card("vox-event", EVENT_PAIR[1:])
        page.click('.card[data-panel="vox-event"] [data-voxel-scope="selection"]')
        gl_card("vox-ensemble", ENSEMBLE_PAIR[1:])
        live = page.evaluate(_LIVE_GL)
        assert sorted(live) == ["vox-ensemble", "vox-event"], live
        # The ensemble box is the paired projections' window; its drawer gives the grid's extent.
        title, headings, body = _drawer(page, "vox-ensemble")
        assert "cropped to the paired projections' window" in body and "The accumulation grid spans" in body
        # One event again, on the cloud card's own button: the same chart and context. A narrower window
        # refits the zoom and the camera's viewport alone, and the reader's rotation stays.
        page.click('.card[data-panel="vox-ensemble"] [data-voxel-scope="event"]')
        _scroll_to(page, "vox-event")
        assert sorted(page.evaluate(_LIVE_GL)) == ["vox-ensemble", "vox-event"], "no context made or lost"
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

        # Without WebGL the 3-D cards say so, ask for no cubes, and their projections still draw. In Local, which
        # draws both pairs.
        browser, page, problems2, requests = _open(p, base, SINGLE_HITS_TABLE, fragment="&frame=local",
                                                   init=(_NO_WEBGL,))
        # Local opens on the cloud; One event, on its card, brings the event pair.
        for card_id, cells, switch in (("vox-ensemble", ENSEMBLE_PAIR[1:], "event"), ("vox-event", EVENT_PAIR[1:], None)):
            page.locator(f'.card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            state = _settled(page, card_id)
            assert state["kind"] == "notice" and state["message"].startswith(GL_UNAVAILABLE), state
            # No volume, so no slice row: K = 1 … L has nothing to cut.
            row = page.evaluate(_SLICE_ROW, card_id)
            assert row is not None and row["hidden"] and not row["visible"], (card_id, row)
            title, headings, body = _drawer(page, card_id)
            assert GL_UNAVAILABLE in body
            for cell in cells:
                state = _scroll_to(page, cell)
                assert state["message"] is None and state["canvas"] and state["series"], (cell, state)
            if switch:
                page.click(f'.card[data-panel="{card_id}"] [data-voxel-scope="{switch}"]')
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
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE,
                                                  fragment="&model=energy&frame=local&voxel_scope=event")
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
                if card_id == "vox-ensemble":
                    _choose_frame(page, "local")  # the cloud is drawn in Local (one 3-D pair per frame)
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

#: Which 3-D pairs are laid out: on screen, not merely flagged (a `hidden` that CSS overrides draws an empty pair).
_PAIRS_SHOWN = """() => Object.fromEntries([...document.querySelectorAll('.voxel-pair')]
  .map((p) => [p.dataset.voxelPair, p.getClientRects().length > 0]))"""
#: The line above the 3-D views naming the pair the selected frame does not draw, or None.
_FRAME_NOTE = """() => { const n = document.querySelector('.voxels-frame-note'); return n && !n.hidden ? n.textContent : null; }"""


def test_views_draws_the_3d_pair_of_the_selected_frame_only(models_live_server):
    """Martin's directives (2026-11-06): one coordinate system at a time. The Absolute frame draws the event pair
    alone (the cloud would fall back to Local), the D-frame the cloud alone (the event view would fall back to
    Absolute); a line names the frames to choose to see the other. Local draws both, one at a time: the 3-D card's
    Selection | One event chooses, the cloud first. Hiding a pair keeps its chart and WebGL context; a Methodology
    link to a pair the frame cannot draw says which frames draw it, and one to a pair Local's scope hides brings it
    on show."""
    base = models_live_server["base"]
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, init=(_COUNT_GL,))
        _scroll_to(page, "vox-event")
        assert page.evaluate(_PAIRS_SHOWN) == {"event": True, "ensemble": False}
        note = page.evaluate(_FRAME_NOTE)
        assert note and note.startswith("The 3-D ensemble cloud is not drawn in Absolute: choose ") and "Reference Frame" in note, note
        assert not _requests_of(requests, "/api/voxels"), _urls(requests)
        assert page.evaluate(_LIVE_GL) == ["vox-event"]

        _choose_frame(page, "canonical")
        _scroll_to(page, "vox-ensemble")
        assert page.evaluate(_PAIRS_SHOWN) == {"event": False, "ensemble": True}
        assert page.evaluate(_FRAME_NOTE).startswith("The 3-D event view is not drawn in ")
        assert _requests_of(requests, "/api/voxels", frame="canonical")
        # The event view's chart stays in the page, off show, with its context.
        assert sorted(page.evaluate(_LIVE_GL)) == ["vox-ensemble", "vox-event"]

        _choose_frame(page, "local")
        _scroll_to(page, "vox-ensemble")
        assert page.evaluate(_PAIRS_SHOWN) == {"event": False, "ensemble": True}
        assert page.evaluate(_FRAME_NOTE) is None
        assert _requests_of(requests, "/api/voxels", frame="local")
        # One event, on the cloud card's button, from the keyboard: the cloud's card leaves the screen with its
        # pair, and focus moves to the same button on the event's card (review finding 3, 2026-11-06).
        page.focus('.main .card[data-panel="vox-ensemble"] [data-voxel-scope="event"]')
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.activeElement?.closest('.card')?.dataset.panel === 'vox-event'"
                               " && document.activeElement.dataset.voxelScope === 'event'", timeout=10_000)
        # Then the selection again, on the event card's button: no request back.
        _scroll_to(page, "vox-event")
        assert page.evaluate(_PAIRS_SHOWN) == {"event": True, "ensemble": False}
        assert _requests_of(requests, "/api/event", format="voxels", frame="local")
        asked = len(requests)
        page.click('.main .card[data-panel="vox-event"] [data-voxel-scope="selection"]')
        _scroll_to(page, "vox-ensemble")
        _quiet(page)
        assert page.evaluate(_PAIRS_SHOWN) == {"event": False, "ensemble": True}
        assert requests[asked:] == [], f"the cloud's response is in hand: {requests[asked:]}"

        _choose_frame(page, "lab")
        _scroll_to(page, "vox-event")
        assert page.evaluate(_PAIRS_SHOWN) == {"event": True, "ensemble": False}
        assert sorted(page.evaluate(_LIVE_GL)) == ["vox-ensemble", "vox-event"], "no context made or lost"
        assert _hyphen_negatives([note, page.evaluate(_FRAME_NOTE) or ""]) == []
        browser.close()

        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.goto(f"{base}/models?panel=vox-ensemble&from=lnk-results-models&from_sec=3.6#table_name={BASELINE_TABLE}")
        page.wait_for_function("() => !location.search && !document.getElementById('kind-banner').hidden",
                               timeout=30_000)
        banner = page.locator("#kind-banner-text").inner_text()
        assert "3-D ensemble cloud" in banner and "Reference Frame" in banner, banner
        assert "does not show" not in banner, banner
        browser.close()

        # In Local, a link to the cloud while one event is on show switches the card to the selection first.
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.goto(f"{base}/models?panel=vox-ensemble&from=lnk-results-models&from_sec=3.6"
                  f"#table_name={BASELINE_TABLE}&frame=local&voxel_scope=event")
        page.wait_for_function("() => !location.search && !document.getElementById('inspector').hidden",
                               timeout=30_000)
        assert page.evaluate(_PAIRS_SHOWN) == {"event": False, "ensemble": True}
        assert _hash(page).get("voxel_scope") != "event", _hash(page)
        assert page.locator("#kind-banner").is_hidden() or "3-D" not in page.locator("#kind-banner-text").inner_text()
        browser.close()
    assert problems == [], problems


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
    event opens it; the per-shower translated frame shuts the Selection button with its reason, and Local opens
    on the selection, which is the cloud there (Martin, 2026-11-06)."""
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

        # The per-shower translated frame: one event, the Selection button shut with its reason.
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, fragment="&frame=trans")
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        trans = page.evaluate(_SCOPE)
        assert trans["selection"]["disabled"] and trans["selection"]["title"].startswith(
            "The selection is not drawn in Per-shower translated"), trans
        assert trans["event"]["pressed"] == "true" and not _requests_of(requests, "/api/selection-cells")
        browser.close()
        assert problems == [], problems

        # Local: the selection is the cloud, its card lit on Selection; no selection cells, no event asked for.
        browser, page, problems, requests = _open(p, base, BASELINE_TABLE, fragment="&frame=local")
        _scroll_to(page, "vox-ensemble")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-ensemble", timeout=30_000)
        lit = page.evaluate("() => [...document.querySelectorAll('.main .card[data-panel=\"vox-ensemble\"] [data-voxel-scope]')]"
                            ".map((b) => [b.dataset.voxelScope, b.getAttribute('aria-pressed'), b.disabled])")
        assert lit == [["selection", "true", False], ["event", "false", False]], lit
        assert not _requests_of(requests, "/api/selection-cells") and not _requests_of(requests, "/api/event")
        browser.close()
        assert problems == [], problems


# ------------------------------------------------- the particle filter, 3-D --
#
# The particle filter on the 3-D event card (brief particle-filter §8.3-§8.5, as built at c14f9a2), on the
# two-event demonstration file: p 6-7 GeV selects event 1 through its shower B, p 7-8 GeV nothing. Since the
# physics-subpages change (Martin's decision of 2026-11-16) the pickers draw from the whole experiment, narrowed
# by the particle filter alone: every One event request carries basis=experiment and never an E₁, E₂ or D key.

#: The block's sentences under basis=experiment (brief physics-subpages §5.1) on the demonstration file: both of
#: its events have a defined separation; event 0's showers carry p = 2.71 and 12.54 GeV, event 1's 17.88 and 6.39.
POOL_COUNT_OFF = "Particle filter off: the pickers draw from all 2 events of the experiment."
POOL_COUNT_P67 = ("N = 1 event holds a matching particle (1 matching shower: 0 A, 1 B), "
                  "of the 2 events of the experiment.")
POOL_EMPTY_P78 = ("N = 0: no event of the experiment with a defined separation holds a shower with p in "
                  "7.00–8.00 GeV that deposited energy. Widen the particle filter.")
#: The E₁/E₂/D selection's keys: no event-picker request may carry one under basis=experiment (brief §3.1: the
#: server refuses them with a 422).
SELECTION_KEYS = ("e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max", "include_undefined_d")
#: The 3-D event card's caption: the key counts under its plot (voxel_views.js `renderSparse`), which name the
#: event, its place among the candidates, the pool and the pick's rule sentence (seed and draw).
_EVENT_CAPTION = """() => document.querySelector('.main .card[data-panel="vox-event"] .sparse-note')?.textContent ?? null"""


def _event_urls(urls):
    """The /api/event* requests among `urls`: the raster, the cubes, the picks and the candidates."""
    return [u for u in urls if urlparse(u).path.startswith("/api/event")]


def _assert_pool(urls, where):
    """Every /api/event* request among `urls` draws on the whole experiment: basis=experiment and no E₁/E₂/D key.
    Returns those requests as (path, query), in order."""
    sent = []
    for url in _event_urls(urls):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q.get("basis") == "experiment", f"{where}: {url}"
        assert not [k for k in SELECTION_KEYS if k in q], f"{where}: {url}"
        sent.append((urlparse(url).path, q))
    return sent


#: The Physics page's Event viewer has drawn its event: the subpage on show, the grid's label in and every one of
#: its nine panels holding a canvas (the waits of data/dev/design/physics-subpages/smoke_ps-page1.py).
_VIEWER_DRAWN = """(label) => document.querySelector('.app')?.dataset.psub === 'event'
  && !document.getElementById('psub-event').hidden && document.getElementById('psub-selection').hidden
  && (document.getElementById('event-grid-label')?.textContent ?? '').startsWith(label)
  && ['lab', 'trans', 'local'].every((r) => ['xy', 'xz', 'yz'].every((c) =>
       document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))"""


def _wait_viewer(page, event, shower):
    """Wait until the Physics page's Event viewer draws `event` with `shower` ('A' or 'B'); return its status bar."""
    page.wait_for_function(_VIEWER_DRAWN, arg=f"Event {event}, shower {shower}:", timeout=30_000)
    return page.evaluate("""() => Object.fromEntries(['stat-mode', 'stat-event', 'stat-shower']
      .map((id) => [id, document.getElementById(id).textContent.trim()]))""")

#: The 3-D event card's "2-D ↗" link, by the selector the brief fixes (particle-filter §3.6c and §7).
OPEN_2D = 'a[data-voxel-open-2d]'
#: The 3-D event card's pickers and steps (voxel_views.js), and its "2-D ↗" link.
_VOXEL_PICKERS = """(open2d) => {
  const card = document.querySelector('.main .card[data-panel="vox-event"]');
  const visible = (el) => Boolean(el) && !el.hidden && el.getClientRects().length > 0;
  const state = (sel) => { const b = card.querySelector(sel);
    return b ? { visible: visible(b), disabled: b.disabled, title: b.title, text: b.textContent.trim() } : null; };
  const link = card.querySelector(open2d);
  return {
    pick: state('[data-voxel-pick]'), tilted: state('[data-voxel-tilted]'), densest: state('[data-voxel-densest]'),
    prev: state('[data-voxel-step="prev"]'), next: state('[data-voxel-step="next"]'),
    open2d: link ? { visible: visible(link), href: link.getAttribute('href'), title: link.title,
                     text: link.textContent.trim() } : null,
  };
}"""

#: Whether the sidebar's particle block is laid out on the subpage on show.
_PARTICLE_SHOWN = """() => { const g = document.getElementById('group-particle');
  return Boolean(g) && !g.hidden && getComputedStyle(g).display !== 'none' && g.getClientRects().length > 0; }"""


def test_the_3d_event_card_picks_from_the_particle_pool_and_links_to_the_event_viewer(models_live_server):
    """On Views, with the One event scope and a p interval in the link: the block shows its count of the whole
    experiment; Densest (the scope's default) draws the densest candidate, event 1, with its matching shower B
    asked for in the cubes' request; the toolbar carries Pick for me, Most tilted and Densest; Pick for me sends a
    uniform draw under the particle keys; every /api/event* request carries basis=experiment and no E₁/E₂/D key
    (brief physics-subpages §10.2); "2-D ↗" carries the drawn event and shower with psub=event, and followed it
    opens the Physics page's Event viewer on them (§5.2)."""
    from test_browser_event import _fragment, _idle, _query, _wait_count, _watch

    base = models_live_server["base"]
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, base, BASELINE_TABLE, fragment="&model=energy&voxel_scope=event&particle_p_min=6&particle_p_max=7")
        net = _watch(page)
        _wait_count(page, POOL_COUNT_P67)
        assert page.evaluate(_PARTICLE_SHOWN)
        assert page.evaluate("() => document.getElementById('particle-count').textContent") == POOL_COUNT_P67
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        for card in ("vproj-xy", "vproj-xz", "vproj-yz"):
            _scroll_to(page, card)
        _idle(page, net)

        picks = _requests_of(requests, "/api/event/pick")
        assert picks and all(q["rule"] == "densest" and float(q["particle_p_min"]) == 6
                             and float(q["particle_p_max"]) == 7 for q in picks), picks
        voxels = _requests_of(requests, "/api/event", format="voxels")
        assert voxels and voxels[-1]["event_number"] == "1" and voxels[-1]["shower"] == "b", voxels
        assert float(voxels[-1]["particle_p_min"]) == 6, voxels[-1]
        rasters = [q for q in _requests_of(requests, "/api/event") if "format" not in q]
        assert rasters and rasters[-1]["event_number"] == "1" and rasters[-1]["shower"] == "b", rasters
        _assert_pool(_urls(requests), "the densest event's requests")

        tools = page.evaluate(_VOXEL_PICKERS, OPEN_2D)
        for name, label in (("pick", "Pick for me"), ("tilted", "Most tilted"), ("densest", "Densest")):
            assert tools[name]["visible"] and not tools[name]["disabled"], (name, tools)
            assert tools[name]["text"] == label, (name, tools)
        assert tools["pick"]["title"].startswith("A candidate event drawn uniformly at random"), tools
        assert tools["tilted"]["title"].startswith("The reference notebook's showcase rule on the candidates"), tools

        # Pick for me: the uniform draw of the pool, under the particle keys; the one candidate is event 1.
        start = len(net["urls"])
        page.click('.main .card[data-panel="vox-event"] [data-voxel-pick]')
        _idle(page, net)
        sent = [_query(u) for u in net["urls"][start:] if urlparse(u).path == "/api/event/pick"]
        assert len(sent) == 1, net["urls"][start:]
        assert sent[0]["rule"] == "uniform" and sent[0]["seed"] == "42" and sent[0]["draw"] == "0", sent
        assert float(sent[0]["particle_p_min"]) == 6 and float(sent[0]["particle_p_max"]) == 7, sent
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        assert _hash(page).get("voxel_event") == "1" and _hash(page).get("voxel_shower") == "b", _hash(page)

        # Densest: back to the densest candidate, re-picked under the particle keys; the link names no event.
        start = len(net["urls"])
        page.click('.main .card[data-panel="vox-event"] [data-voxel-densest]')
        _idle(page, net)
        sent = [_query(u) for u in net["urls"][start:] if urlparse(u).path == "/api/event/pick"]
        assert all(q["rule"] == "densest" and float(q["particle_p_min"]) == 6 for q in sent), sent
        assert "voxel_event" not in _hash(page) and _hash(page).get("voxel_shower") == "b", _hash(page)
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        sent = _assert_pool(_urls(requests), "the pickers' requests")
        assert {path for path, _ in sent} >= {"/api/event", "/api/event/pick", "/api/event/candidates"}, sent

        # "2-D ↗": the live link carries the drawn event and shower, the particle keys kept, and the viewer.
        link = f'.main .card[data-panel="vox-event"] {OPEN_2D}'
        tools = page.evaluate(_VOXEL_PICKERS, OPEN_2D)
        assert tools["open2d"], f"no {OPEN_2D} on the 3-D event card"
        assert tools["open2d"]["visible"] and tools["open2d"]["text"] == "2-D ↗", tools
        assert tools["open2d"]["title"].startswith("Open this event in the Physics page's Event viewer"), tools
        page.hover(link)
        href = page.get_attribute(link, "href")
        assert urlparse(href).path == "/", href
        target = _fragment(href)
        assert target["event"] == "1" and target["shower"] == "b" and target["psub"] == "event", target
        assert float(target["particle_p_min"]) == 6 and float(target["particle_p_max"]) == 7, target
        page.click(link)
        page.wait_for_url(re.compile(r"/#"), timeout=30_000)
        status = _wait_viewer(page, 1, "B")
        assert status == {"stat-mode": "Event viewer", "stat-event": "1", "stat-shower": "B"}, status
        assert page.input_value("#event-number") == "1"
        assert page.is_checked('input[name="event-shower"][value="b"]')
        _wait_count(page, POOL_COUNT_P67)
        # The viewer's own requests draw on the whole experiment too.
        _assert_pool(_urls(requests), "the Physics page's Event viewer")
        browser.close()
    assert problems == [], problems


def _assert_empty_pair(page, line):
    """The four cards of the event pair show `line` as a notice (data-kind "empty", not an error), and every
    picker and step of the 3-D event card is shut with `line` as its title."""
    page.wait_for_function(
        f"""() => {EVENT_PAIR!r}.every((id) => {{ const s = ({_CARD})(id);
          return s && s.kind === 'empty' && !s.loading; }})""", timeout=30_000)
    for card in EVENT_PAIR:
        state = page.evaluate(_CARD, card)
        assert state["message"] == line and state["kind"] == "empty", (card, state)
    tools = page.evaluate(_VOXEL_PICKERS, OPEN_2D)
    for name in ("pick", "tilted", "densest", "prev", "next"):
        assert tools[name]["disabled"] and tools[name]["title"] == line, (name, tools)


def test_an_empty_pool_shows_the_empty_line_on_the_3d_event_pair_and_asks_for_no_event(models_live_server):
    """N = 0 on the One event scope: after a particle commit that empties the pool, the four cards of the event
    pair show the empty line as a notice (not an error), the pickers are shut with that line as their title, and
    the commit sends no /api/event/pick or /api/event request: the pool's request alone. No banner, no failed
    response."""
    from test_browser_event import _commit, _idle, _paths, _watch

    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], BASELINE_TABLE,
                                           fragment="&model=energy&voxel_scope=event")
        net = _watch(page)
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        _idle(page, net)

        _commit(page, net, [("pp-num-hi", 8)], wait_for="N = 2 events")
        # The commit that empties the pool asks for the pool alone: no pick, no event.
        sent = _commit(page, net, [("pp-num-lo", 7)], wait_for="N = 0")
        _assert_empty_pair(page, POOL_EMPTY_P78)
        _idle(page, net)
        assert _paths(sent) == ["/api/event/candidates"], sent
        _assert_pool(sent, "the pool's count")
        assert page.evaluate("() => document.getElementById('particle-count').textContent") == POOL_EMPTY_P78
        assert page.evaluate("() => document.getElementById('banner').hidden")
        browser.close()
    assert problems == [], problems


def test_a_link_opened_on_an_empty_pool_asks_for_no_pick_and_no_event(models_live_server):
    """Brief particle-filter §8.3: "Page 2 with no voxel_event shows the emptyLine in place of the event pair's
    plots and requests neither /api/event/pick nor /api/event", here for a link that opens the One event scope on
    an empty pool (p 7-8 GeV): the same line, no event drawn, no pick asked for, and so no failed response."""
    from test_browser_event import _wait_count

    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, models_live_server["base"], BASELINE_TABLE,
            fragment="&model=energy&voxel_scope=event&particle_p_min=7&particle_p_max=8")
        _wait_count(page, POOL_EMPTY_P78)
        _scroll_to(page, "vox-event")
        _assert_empty_pair(page, POOL_EMPTY_P78)
        _quiet(page)
        assert not _requests_of(requests, "/api/event"), _urls(requests)
        assert page.evaluate("() => document.getElementById('banner').hidden")
        assert not _requests_of(requests, "/api/event/pick"), _urls(requests)
        browser.close()
    assert problems == [], problems


def test_the_particle_block_shows_on_views_only(models_live_server):
    """The block belongs to the 3-D event pair's pickers: shown on Views, hidden (by CSS) on Distillations and
    Performance, and shown again on Views with its count kept."""
    from test_browser_event import _wait_count

    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], BASELINE_TABLE)
        _wait_count(page, POOL_COUNT_OFF)
        assert page.evaluate(_PARTICLE_SHOWN)
        for msub in ("distill", "perf"):
            _show_subpage(page, msub)
            assert not page.evaluate(_PARTICLE_SHOWN), msub
        _show_subpage(page, "views")
        assert page.evaluate(_PARTICLE_SHOWN)
        assert page.evaluate("() => document.getElementById('particle-count').textContent") == POOL_COUNT_OFF
        browser.close()
    assert problems == [], problems


# ------------------------------------------- the pool of the whole experiment --
#
# Brief physics-subpages §10.2 (Martin's decision of 2026-11-16): the 3-D event's pickers draw from every event of
# the experiment, narrowed by the particle filter alone. An E₁/E₂/D commit steers the Selection scope and the cloud
# and never touches the One event scope.

def _commit_e1(page, net, value):
    """Type E₁'s lower bound and press Enter: one commit. Wait until the link carries a new `e1_min`, then until the
    page has asked and answered everything the commit caused. The requests it sent."""
    from test_browser_event import _idle

    before = page.evaluate("() => new URLSearchParams(location.hash.slice(1)).get('e1_min')")
    start = len(net["urls"])
    page.fill("#e1-num-lo", f"{value:.2f}")
    page.press("#e1-num-lo", "Enter")
    page.wait_for_function("(prev) => { const v = new URLSearchParams(location.hash.slice(1)).get('e1_min');"
                           " return v !== null && v !== prev; }", arg=before, timeout=10_000)
    _idle(page, net)
    _quiet(page)
    _idle(page, net)
    return net["urls"][start:]


def _paths_of(urls, path):
    return [{k: v[0] for k, v in parse_qs(urlparse(u).query).items()} for u in urls if urlparse(u).path == path]


def test_an_e1_commit_on_views_leaves_the_3d_event_and_reloads_the_selection_and_the_cloud(models_live_server):
    """On the One event scope, two Pick for me draws (seed 42, draws 0 and 1: events 1 then 0 on this file) leave
    event 0, whose E₁ = 2.71 GeV a cut at 4 GeV takes out of the selection. The commit sends no /api/event*
    request: the event, its shower, its caption and the drawn cubes stay, and the next Pick for me is draw 2 with
    no E₁ key (the counter is carried). The Selection scope then draws under the cut and reloads on the next
    commit, and so does the D-frame's cloud: their requests carry e1_min, and still no /api/event* request is
    sent. Every One event request carries basis=experiment and no E₁/E₂/D key."""
    from test_browser_event import _idle, _watch

    theme = _theme_module()
    card = '.main .card[data-panel="vox-event"]'
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE,
                                                  fragment="&model=energy&voxel_scope=event")
        net = _watch(page)
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        _idle(page, net)
        for _ in range(2):
            page.click(f"{card} [data-voxel-pick]")
            _idle(page, net)
            page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        picks = [q for path, q in _assert_pool(net["urls"], "the two picks") if path == "/api/event/pick"]
        assert [(q["rule"], q["seed"], q["draw"]) for q in picks] == [("uniform", "42", "0"), ("uniform", "42", "1")]
        pinned = _hash(page)
        assert pinned.get("voxel_event") == "0", pinned
        caption = page.evaluate(_EVENT_CAPTION)
        assert caption and "draw 1" in caption, caption

        # E₁ ≥ 4 GeV: event 0 leaves the selection, but not the pool; nothing of the One event scope moves.
        sent = _commit_e1(page, net, 4.0)
        assert _event_urls(sent) == [], sent
        kept = _hash(page)
        assert kept.get("e1_min") and float(kept["e1_min"]) == pytest.approx(4.0, abs=0.05), kept
        assert (kept.get("voxel_event"), kept.get("voxel_shower")) == (pinned.get("voxel_event"),
                                                                     pinned.get("voxel_shower")), kept
        assert page.evaluate(_EVENT_CAPTION) == caption
        assert page.evaluate(_SCOPE)["title"] == "One Event in 3-D — Detector Cells"
        assert page.evaluate(_CARD, "vox-event")["message"] is None
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)

        # The draw counter is carried: the next Pick for me is draw 2, from the whole experiment.
        start = len(net["urls"])
        page.click(f"{card} [data-voxel-pick]")
        _idle(page, net)
        picks = [q for path, q in _assert_pool(net["urls"][start:], "the pick after the commit")
                 if path == "/api/event/pick"]
        assert [(q["rule"], q["draw"]) for q in picks] == [("uniform", "2")], picks
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)

        # The Selection scope draws under the cut, and reloads on the next commit.
        start = len(net["urls"])
        page.click(f'{card} [data-voxel-scope="selection"]')
        page.wait_for_function(f"() => document.querySelector('{card} .title')?.textContent"
                               " === 'The Selection in 3-D — Detector Cells'", timeout=30_000)
        _idle(page, net)
        _settled(page, "vox-event")
        cells = _paths_of(net["urls"][start:], "/api/selection-cells")
        assert cells and all(float(q["e1_min"]) == pytest.approx(4.0, abs=0.05) for q in cells), cells
        sent = _commit_e1(page, net, 3.5)
        cells = _paths_of(sent, "/api/selection-cells")
        assert cells and all(float(q["e1_min"]) == pytest.approx(3.5, abs=0.05) for q in cells), sent
        assert _event_urls(sent) == [], sent

        # The D-frame's cloud reloads on a commit; the One event scope still asks for nothing.
        _choose_frame(page, "canonical")
        _scroll_to(page, "vox-ensemble")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-ensemble", timeout=30_000)
        _idle(page, net)
        sent = _commit_e1(page, net, 3.0)
        cloud = _paths_of(sent, "/api/voxels")
        assert cloud and all(float(q["e1_min"]) == pytest.approx(3.0, abs=0.05) for q in cloud), sent
        assert _event_urls(sent) == [], sent
        page.wait_for_function(theme._GL_DRAWN, arg="vox-ensemble", timeout=30_000)

        _assert_pool(_urls(requests), "every One event request")
        browser.close()
    assert problems == [], problems


def test_every_one_event_request_draws_on_the_whole_experiment(models_live_server):
    """With an E₁/E₂/D cut and a p bound in the link, the One event scope's every request - the Densest pick, the
    raster and the cubes, Pick for me, Most tilted, Densest again, previous / next - carries basis=experiment, the
    particle keys and no E₁/E₂/D key (a 422 otherwise, brief §3.1), and none of them fails. The link's cut keeps
    event 1 alone in the selection; the pool (p ≤ 13 GeV: every event, through a shower of each) holds both."""
    from test_browser_event import _idle, _watch

    theme = _theme_module()
    card = '.main .card[data-panel="vox-event"]'
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, models_live_server["base"], BASELINE_TABLE,
            fragment="&model=energy&voxel_scope=event&e1_min=4&particle_p_max=13")
        net = _watch(page)
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        _idle(page, net)
        for button in ("[data-voxel-pick]", "[data-voxel-tilted]", "[data-voxel-densest]", "[data-voxel-pick]"):
            page.click(f"{card} {button}")
            _idle(page, net)
            page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        for step in ("next", "prev"):
            if page.evaluate(f"() => !document.querySelector('{card} [data-voxel-step=\"{step}\"]').disabled"):
                page.click(f'{card} [data-voxel-step="{step}"]')
                _idle(page, net)
                page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        sent = _assert_pool(_urls(requests), "the One event scope")
        rules = [q["rule"] for path, q in sent if path == "/api/event/pick"]
        assert {"densest", "uniform", "tilted"} <= set(rules), rules
        events = [q for path, q in sent if path == "/api/event"]
        assert any(q.get("format") == "voxels" for q in events) and any("format" not in q for q in events), events
        assert all(q.get("particle_p_max") and float(q["particle_p_max"]) == 13 for _, q in sent), sent
        # Both events were drawn at some point: the E₁ cut, which holds event 0 out of the selection, did not
        # narrow the pickers.
        assert {q["event_number"] for q in events} == {"0", "1"}, events
        # The Physics-page key the link brought stays a selection key: the cut is still in the hash.
        assert float(_hash(page).get("e1_min", "nan")) == pytest.approx(4.0, abs=0.05), _hash(page)
        browser.close()
    assert problems == [], problems


#: A text's contrast against the ground it is drawn on, read off the computed styles: its colour (alpha blended)
#: against the first opaque background among its ancestors (the card), as WCAG 2 defines the ratio.
_TEXT_CONTRAST = """(el) => {
  // Any CSS colour syntax (rgb, color(srgb ...), oklch ...) resolved by painting it on a 1 x 1 canvas.
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
  const g = canvas.getContext('2d', { willReadFrequently: true });
  const paint = (colour, alpha = 1) => { g.globalAlpha = alpha; g.fillStyle = '#000'; g.fillStyle = colour;
    g.fillRect(0, 0, 1, 1); g.globalAlpha = 1; };
  const read = () => [...g.getImageData(0, 0, 1, 1).data];
  let ground = null;
  for (let a = el; a && !ground; a = a.parentElement) {
    g.clearRect(0, 0, 1, 1); paint(getComputedStyle(a).backgroundColor);
    const c = read(); if (c[3] === 255) ground = getComputedStyle(a).backgroundColor;
  }
  ground = ground || '#ffffff';
  let opacity = 1;
  for (let a = el; a; a = a.parentElement) opacity *= Number(getComputedStyle(a).opacity);
  g.clearRect(0, 0, 1, 1); paint(ground); const bg = read().slice(0, 3);
  paint(getComputedStyle(el).color, opacity); const ink = read().slice(0, 3);
  const lum = (rgb) => rgb.map((c) => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; })
    .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  const [hi, lo] = [lum(ink), lum(bg)].sort((a, b) => b - a);
  return { ratio: (hi + 0.05) / (lo + 0.05), ink: `rgb(${ink})`, ground: `rgb(${bg})` };
}"""

#: A 3-D card's standing line of the channels the experiment cannot serve (voxel_views.js `syncShutLines`): its
#: text, whether it is laid out, its box against the card's plot, and its contrast.
_SHUT_LINE = """(id) => {
  const card = document.querySelector(`.main .card[data-panel="${id}"]`);
  const el = card?.querySelector('[data-voxel-shut]');
  if (!el) return null;
  const box = el.getBoundingClientRect();
  const plot = card.querySelector('.plot-frame').getBoundingClientRect();
  return { text: el.textContent, hidden: el.hidden, laidOut: el.offsetParent !== null && box.height > 0 && box.width > 0,
           abovePlot: box.bottom <= plot.top + 0.5 };
}"""

#: The standing lines brief physics-subpages §10.2 fixes, by experiment and card: the labels in menu order, then
#: the reason (labels.js labels; the reason is the server's, pinned by the Node tests, and read as a sentence here).
#: They name the network channels alone (Martin's decision of 2026-11-16), so the two-shower baseline, which lacks
#: only the species columns, has none (`test_a_two_shower_card_has_no_line_and_the_species_option_its_title`).
SHUT_LINES = [
    (SINGLE_HITS_TABLE, "&voxel_scope=event", "vox-event",
     "Unavailable for this experiment: Grad-CAM Model Attention, Shap-CAM Attribution, Segmentation error. "),
    (SINGLE_HITS_TABLE, "&frame=local", "vox-ensemble", "Unavailable for this experiment: Energy-weighted Grad-CAM"),
]


@pytest.mark.parametrize("scheme", ["dark", "light"])
@pytest.mark.parametrize(("table", "fragment", "card", "prefix"), SHUT_LINES, ids=["single-event", "single-cloud"])
def test_the_3d_card_states_the_channels_the_experiment_cannot_serve(models_live_server, table, fragment, card,
                                                                     prefix, scheme):
    """The standing "Unavailable for this experiment" line (brief §10.2): visible text between the caption and the
    plot, never a tooltip alone, on the single-shower hits' event and cloud cards, in both themes, its text at 4.5:1
    or more on the card."""
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], table, fragment=fragment, scheme=scheme)
        _scroll_to(page, card)
        page.wait_for_function(theme._GL_DRAWN, arg=card, timeout=30_000)
        page.wait_for_function("(id) => (document.querySelector(`.main .card[data-panel=\"${id}\"] [data-voxel-shut]`)"
                               "?.textContent ?? '').startsWith('Unavailable')", arg=card, timeout=10_000)
        line = page.evaluate(_SHUT_LINE, card)
        if line is not None:
            line.update(page.eval_on_selector(f'.main .card[data-panel="{card}"] [data-voxel-shut]', _TEXT_CONTRAST))
        browser.close()
    assert problems == [], problems
    assert line is not None, f"no standing line on {card}"
    assert line["text"].startswith(prefix), line["text"]
    # One sentence per reason: the labels, then a reason of its own, closed by a full stop.
    reason = line["text"][len("Unavailable for this experiment: "):].split(". ", 1)
    assert len(reason) == 2 and reason[1].strip().endswith("."), line["text"]
    assert not line["hidden"] and line["laidOut"] and line["abovePlot"], line
    assert line["ratio"] >= 4.5, (scheme, line)


def test_a_two_shower_card_has_no_line_and_the_species_option_its_title(models_live_server):
    """Martin's decision of 2026-11-16: the standing line names the network channels alone. The two-shower baseline
    serves every network channel and lacks only the species columns, so its 3-D event card shows no line, and the
    species option stays in the menu, disabled, with the server's reason as its title, as before the line existed."""
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, models_live_server["base"], BASELINE_TABLE,
                                           fragment="&model=energy&voxel_scope=event")
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        line = page.evaluate(_SHUT_LINE, "vox-event")
        species = page.evaluate("""() => { const o = document.querySelector(
          '.main .card[data-panel="vox-event"] select option[value="species"]');
          return o ? { disabled: o.disabled, title: o.title } : null; }""")
        browser.close()
    assert problems == [], problems
    assert line is not None and line["hidden"] and line["text"] == "", line
    assert species is not None and species["disabled"], species
    assert species["title"].startswith("Needs the particle_type and is_secondary columns"), species


def test_open_in_3d_from_the_event_viewer_and_2d_back_land_on_the_same_event_and_shower(models_live_server):
    """The round trip of brief physics-subpages §5.2 and §13: the Physics page's Event viewer on event 1, shower B;
    its "Open in 3-D →" carries the event and shower as voxel_event / voxel_shower with the One event scope, and
    followed lands on Views with the 3-D event card drawing event 1 (no pick: a linked event is drawn as asked),
    its raster and cubes asked for under basis=experiment. That card's "2-D ↗" carries event 1, shower B and
    psub=event, and followed lands in the Physics page's Event viewer on them, its nine panels drawn."""
    from test_browser_event import _fragment

    base = models_live_server["base"]
    theme = _theme_module()
    with models_live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        problems, requests = [], []
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
        page.on("request", lambda r: requests.append((r.method, r.url)) if "/api/" in r.url else None)
        page.goto(f"{base}/#table_name={BASELINE_TABLE}&psub=event&event=1&shower=b")
        status = _wait_viewer(page, 1, "B")
        assert status == {"stat-mode": "Event viewer", "stat-event": "1", "stat-shower": "B"}, status
        _assert_pool(_urls(requests), "the Event viewer")

        # "Open in 3-D →": a live link to Views, the event and shower in the Models page's own keys.
        page.wait_for_function("() => { const a = document.getElementById('event-open-3d');"
                               " return a && !a.hidden && a.getClientRects().length > 0; }", timeout=10_000)
        page.hover("#event-open-3d")
        href = page.get_attribute("#event-open-3d", "href")
        assert urlparse(href).path == "/models", href
        target = _fragment(href)
        assert (target.get("voxel_event"), target.get("voxel_shower"), target.get("voxel_scope")) == ("1", "b", "event"), \
            target
        assert "msub" not in target, target
        start = len(requests)
        page.click("#event-open-3d")
        page.wait_for_url(re.compile(r"/models#"), timeout=30_000)
        page.wait_for_function(
            "(t) => document.getElementById('experiment-select')?.value === t "
            "&& document.getElementById('stat-kind')?.textContent.trim() !== '—'", arg=BASELINE_TABLE, timeout=30_000)
        _wait_subpage(page, "views")
        _scroll_to(page, "vox-event")
        page.wait_for_function(theme._GL_DRAWN, arg="vox-event", timeout=30_000)
        for card in ("vproj-xy", "vproj-xz", "vproj-yz"):
            _scroll_to(page, card)
        scope = page.evaluate(_SCOPE)
        assert scope["title"] == "One Event in 3-D — Detector Cells" and scope["event"]["pressed"] == "true", scope
        landed = _hash(page)
        assert (landed.get("voxel_event"), landed.get("voxel_shower")) == ("1", "b"), landed
        sent = _assert_pool([u for m, u in requests[start:] if m == "GET"], "the 3-D event's requests")
        rasters = [q for path, q in sent if path == "/api/event" and "format" not in q]
        cubes = [q for path, q in sent if path == "/api/event" and q.get("format") == "voxels"]
        assert rasters and all((q["event_number"], q["shower"]) == ("1", "b") for q in rasters), rasters
        assert cubes and all(q["event_number"] == "1" for q in cubes), cubes
        assert not [q for path, q in sent if path == "/api/event/pick"], sent

        # "2-D ↗": back to the Physics page's Event viewer on the same event and shower.
        link = f'.main .card[data-panel="vox-event"] {OPEN_2D}'
        page.hover(link)
        back = page.get_attribute(link, "href")
        assert urlparse(back).path == "/", back
        fragment = _fragment(back)
        assert (fragment.get("event"), fragment.get("shower"), fragment.get("psub")) == ("1", "b", "event"), fragment
        page.click(link)
        page.wait_for_url(re.compile(r"^[^#]*/#"), timeout=30_000)
        status = _wait_viewer(page, 1, "B")
        assert status == {"stat-mode": "Event viewer", "stat-event": "1", "stat-shower": "B"}, status
        assert page.input_value("#event-number") == "1"
        _assert_pool(_urls(requests), "the round trip")
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
            if card_id == "vox-ensemble":
                # The cloud is drawn in Local, which opens on the selection (the cloud there): the event pair is
                # hidden, so nothing of it lands inside the cloud's no-request window below.
                _choose_frame(page, "local")
                _quiet(page)
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
        # Local draws both 3-D pairs, one at a time (the card's Selection | One event): one event first, then
        # the cloud, then one event again for the slices; both contexts live.
        browser, page, problems, requests = _open(
            p, models_live_server["base"], BASELINE_TABLE, fragment="&model=energy&frame=local&voxel_scope=event",
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
            if card_id == "vox-ensemble":
                # The cloud is turned through echarts-gl's camera action while it is on show.
                page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-vox-ensemble'))"
                              ".dispatchAction({ type: 'grid3DChangeCamera', alpha: 10, beta: 70 })")
                page.wait_for_function(f"() => {{ const m = ({theme._CAMERA})('vox-ensemble').model; "
                                       "return m.alpha === 10 && m.beta === 70; }", timeout=10_000)
            switch = "selection" if card_id == "vox-event" else "event"
            page.click(f'.main .card[data-panel="{card_id}"] [data-voxel-scope="{switch}"]')
        _scroll_to(page, "vox-event")
        _quiet(page)
        # The reader turns and zooms the event and cuts it into six slices, at the third.
        _turn_and_zoom(page, "vox-event")
        _set_slices(page, "vox-event", 6)
        _step_slice(page, "vox-event", "next")
        _step_slice(page, "vox-event", "next")
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


#: The catalogue card as a chart holds it: each facet's category rows (benchCatalogModel keys, `<species>:<frame>`
#: and `gap:<i>`), each value axis's type and range, the legend's names and selected map, and the plot's height
#: (the element ECharts draws in, sized by CatalogChartPanel.fitHeight) and the chart's.
_CATALOG_ROWS_FN = """(inst) => {
  const o = inst.getOption();
  const legend = (o.legend || [])[0] || {};
  return {
    rows: (o.yAxis || []).map((a) => [...(a.data || [])].map((d) => (typeof d === 'object' ? d.value : d))),
    x: (o.xAxis || []).map((a) => [a.type ?? 'value', a.min ?? null, a.max ?? null]),
    legend: (legend.data || []).map((d) => (typeof d === 'string' ? d : d?.name)),
    selected: { ...(legend.selected || {}) },
    chart: inst.getHeight(),
  };
}"""

_CATALOG_ROWS = f"""(plotId) => {{
  const host = document.getElementById(plotId);
  return {{ ...({_CATALOG_ROWS_FN})(echarts.getInstanceByDom(host)), plot: host.getBoundingClientRect().height }};
}}"""

#: The same, for every SVG export as it is serialised (the exporter's own chart).
_WATCH_EXPORT_ROWS = f"""() => {{
  if (window.__exportRows) return;
  window.__exportRows = [];
  const init = echarts.init;
  echarts.init = function (dom, theme, opts) {{
    const chart = init.call(this, dom, theme, opts);
    if (opts && opts.renderer === 'svg') {{
      const render = chart.renderToSVGString.bind(chart);
      chart.renderToSVGString = (...args) => {{
        window.__exportRows.push(({_CATALOG_ROWS_FN})(chart));
        return render(...args);
      }};
    }}
    return chart;
  }};
}}"""

#: The catalogue's legend entry of the Local frame (bench_catalog.js labelOf(payload, 'frame', 'local')).
CATALOG_LOCAL = "Local"


def _svg_height(svg):
    return float(re.search(r'<svg[^>]*?\sheight="([\d.]+)', svg).group(1))


def test_the_catalogue_card_lays_out_its_facets_without_a_frame_switched_off(models_live_server):
    """Review R2-7 on screen and in the export (legend-sliders, 2026-11-17; bench_catalog.js benchCatalogModel): the
    Local frame switched off on the accuracy card's legend takes its rows out of every facet, so no empty, unlabelled
    slot is left. The live chart's category axes hold no `<species>:local` row, the card's plot element is shorter,
    the value axes do not move, and the legend still lists Local, marked off. The SVG export lays its facets out
    without those rows too: no `:local` row, no "Local" text (its legend entry and any row label), and a figure
    shorter than the whole figure's. Switched back on, the rows, the plot's height and the chart return. No request,
    no page error."""
    with models_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, models_live_server["base"], BASELINE_TABLE)
        page.evaluate(_WATCH_EXPORT_ROWS)
        _scroll_to(page, "perf-catalog")
        _frames(page, 3)
        whole = page.evaluate(_CATALOG_ROWS, "plot-perf-catalog")
        assert whole["rows"] and all(any(r.endswith(":local") for r in rows) for rows in whole["rows"]), whole["rows"]
        assert CATALOG_LOCAL in whole["legend"], whole["legend"]
        _, whole_svg = _download_svg(page, "perf-catalog")
        whole_export = page.evaluate("() => window.__exportRows.at(-1)")
        assert CATALOG_LOCAL in _svg_texts(whole_svg), sorted(set(_svg_texts(whole_svg)))
        before = len(requests)

        _click_chart_legend(page, "plot-perf-catalog", CATALOG_LOCAL)
        _frames(page, 3)
        off = page.evaluate(_CATALOG_ROWS, "plot-perf-catalog")
        assert off["selected"].get(CATALOG_LOCAL) is False and CATALOG_LOCAL in off["legend"], off
        assert not [r for rows in off["rows"] for r in rows if r.endswith(":local")], off["rows"]
        assert [[r for r in rows if not r.endswith(":local")] for rows in whole["rows"]] == off["rows"], \
            (whole["rows"], off["rows"])
        assert off["x"] == whole["x"], ("the value axes moved", whole["x"], off["x"])
        assert off["plot"] < whole["plot"] and off["chart"] < whole["chart"], (whole["plot"], off["plot"])
        drawn = page.evaluate(_CHART_DRAWN, "plot-perf-catalog")["series"]
        own = [s for s in drawn if s[0] == CATALOG_LOCAL]
        assert len(own) == 1 and own[0][1] is True and own[0][3] == 0, own

        name, svg = _download_svg(page, "perf-catalog")
        exported = page.evaluate("() => window.__exportRows.at(-1)")
        assert not [r for rows in exported["rows"] for r in rows if r.endswith(":local")], exported["rows"]
        assert CATALOG_LOCAL not in exported["legend"], exported["legend"]
        assert CATALOG_LOCAL not in _svg_texts(svg), sorted(set(_svg_texts(svg)))
        assert _svg_height(svg) < _svg_height(whole_svg), (_svg_height(whole_svg), _svg_height(svg))
        assert exported["chart"] < whole_export["chart"], (whole_export["chart"], exported["chart"])
        print("catalogue heights", {"plot": [whole["plot"], off["plot"]], "chart": [whole["chart"], off["chart"]],
                                    "svg": [_svg_height(whole_svg), _svg_height(svg)], "name": name})

        _click_chart_legend(page, "plot-perf-catalog", CATALOG_LOCAL)
        _frames(page, 3)
        back = page.evaluate(_CATALOG_ROWS, "plot-perf-catalog")
        assert back["rows"] == whole["rows"] and back["x"] == whole["x"], back
        assert back["plot"] == whole["plot"] and back["chart"] == whole["chart"], (whole, back)
        assert back["selected"].get(CATALOG_LOCAL) is not False, back["selected"]
        assert requests[before:] == [], f"the legend or an export asked the service: {requests[before:]}"
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
