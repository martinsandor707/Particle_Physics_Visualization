"""The light / dark theme in Chromium: the boot, the toggle and the live repaint.

The theme is a per-browser convenience (theme.js): with nothing stored the
page follows the system's ``prefers-color-scheme``; a click on the header's
toggle switches and stores the choice, except that a click landing on the
system's own theme removes it, so the page follows the system again. A switch
redraws what is in hand and asks the service for nothing. This module checks
what a reader sees, on the three pages:

* the boot script sets ``data-theme`` before the first paint: the body's
  background at ``DOMContentLoaded`` is already the theme's canvas, so the
  wrong theme never flashes;
* a stored choice beats the system in both directions; a live system flip is
  followed when nothing is stored and ignored when a choice is;
* the toggle flips ``data-theme``, its own label and the stored value, the
  choice survives a reload, a click back to the system's theme forgets it, and
  the URL hash never moves;
* a switch makes no ``/api/`` request on either page, with the 2 x 2, the
  energy panel, physics cards, the Event Inspector and the compare grid, the
  Models cards and both 3-D views loaded;
* the charts are repainted: axis labels take the theme's muted ink, the XY
  raster's pixels change, an open Details drawer is rebuilt to exactly what
  a page booted in the new theme shows, and the 3-D views take the new chrome
  while keeping the reader's rotation, pan and zoom (the species legend, which
  needs the single-shower hits, is checked in test_browser_models.py: one
  module holds one server);
* exported figures do not depend on the screen theme: the SVG downloads are
  byte-identical, and the Methodology figures are unchanged;
* in light, every visible text of the page's chrome clears 4.5:1 against its
  own opaque ground (dark is measured as the control), the tooltip rule of
  test_browser_tooltip.py holds, the header fits at 1024 and 1600 px with a
  keyboard focus ring on the toggle, and in dark the controls keep today's
  computed colours.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import json
import os
import re

import httpx
import pytest

import test_browser_tooltip as tooltip_checks
from conftest import BASELINE_TABLE
from test_browser_models import _scroll_to as _models_card
from test_browser_physics import _download_svg, _scroll_to as _physics_card

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium theme check",
)

STORAGE_KEY = "calosrv.theme"
OTHER = {"dark": "light", "light": "dark"}
#: tokens.css `--canvas` per theme, as getComputedStyle reports it.
CANVAS = {"dark": "rgb(13, 17, 23)", "light": "rgb(246, 248, 250)"}
#: scale.js `SCREEN.muted` / `SCREEN_LIGHT.muted`: the chart's axis-label ink.
MUTED = {"dark": "#8b949e", "light": "#59636e"}
#: scale.js `SCREEN.border` / `SCREEN_LIGHT.border`: the 3-D box's axis line.
BORDER = {"dark": "#30363d", "light": "#d0d7de"}
#: SwiftShader's software WebGL (test_browser_models.py).
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
PAGES = {"physics": "/", "models": "/models", "methodology": "/methodology"}
#: The physics cards a toggle must find loaded (two are asked for).
PHYSICS_CARDS = ("profile-w", "response-b1")
MODELS_CARDS = ("perf-bins", "pred-truth", "feat-corr", "feat-hist2d")
GL_CARDS = ("vox-event", "vox-ensemble")
#: WCAG's floor for text.
TEXT_FLOOR = 4.5

#: The theme and the body's ground at DOMContentLoaded, before any module ran.
_RECORD_FIRST_PAINT = """(() => {
  document.addEventListener('DOMContentLoaded', () => {
    window.__firstPaint = {
      theme: document.documentElement.dataset.theme ?? null,
      background: getComputedStyle(document.body).backgroundColor,
    };
  }, { once: true });
})();"""

#: Seeds localStorage once per tab (sessionStorage survives a reload; the seed must not).
_SEED = """((key, value) => {
  try {
    if (sessionStorage.getItem('__themeSeeded')) return;
    sessionStorage.setItem('__themeSeeded', '1');
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch (e) { /* the test reads the result */ }
})(%s, %s);"""

_STATE = """(key) => {
  const button = document.getElementById('theme-toggle');
  let stored = null;
  try { stored = localStorage.getItem(key); } catch (e) { stored = 'unreadable'; }
  return {
    theme: document.documentElement.dataset.theme ?? null,
    label: button?.getAttribute('aria-label') ?? null,
    title: button?.getAttribute('title') ?? null,
    stored,
    hash: location.hash,
    background: getComputedStyle(document.body).backgroundColor,
  };
}"""

#: Every axis label colour of a chart, x then y.
_AXIS_INK = """(plotId) => {
  const inst = echarts.getInstanceByDom(document.getElementById(plotId));
  if (!inst) return null;
  const option = inst.getOption();
  return [...(option.xAxis || []), ...(option.yAxis || [])].map((a) => a.axisLabel?.color ?? null);
}"""

#: The XY raster's own pixels: the offscreen canvas the raster series draws.
_RASTER = """(plotId) => {
  const inst = echarts.getInstanceByDom(document.getElementById(plotId));
  const image = inst.getZr().storage.getDisplayList()
    .map((e) => e.style?.image).find((i) => i instanceof HTMLCanvasElement);
  return image ? image.toDataURL() : null;
}"""

#: A 3-D card's camera as the orbit control holds it, the model's view and the chrome's colours.
_CAMERA = """(id) => {
  const chart = echarts.getInstanceByDom(document.getElementById(`plot-${id}`));
  const model = chart.getModel().getComponent('grid3D');
  const control = chart.getViewOfComponentModel(model)._control;
  const option = chart.getOption();
  const view = option.grid3D[0].viewControl;
  const axis = (name) => option[name][0];
  return {
    control: { alpha: control.getAlpha(), beta: control.getBeta(), zoom: control.getOrthographicSize(),
               center: Array.from(control.getCenter()) },
    model: { alpha: view.alpha, beta: view.beta, size: view.orthographicSize, center: view.center,
             projection: view.projection },
    labels: ['xAxis3D', 'yAxis3D', 'zAxis3D'].map((n) => axis(n).axisLabel.color),
    names: ['xAxis3D', 'yAxis3D', 'zAxis3D'].map((n) => axis(n).nameTextStyle.color),
    axisLine: option.grid3D[0].axisLine.lineStyle.color,
    tooltip: option.tooltip[0].backgroundColor,
    series: option.series.length,
  };
}"""

#: Whether a 3-D card has drawn its cubes.
_GL_DRAWN = """(id) => {
  const host = document.getElementById(`plot-${id}`);
  const chart = host && echarts.getInstanceByDom(host);
  return Boolean(chart && (chart.getOption().series || []).some((s) => s.type === 'bar3D'));
}"""

#: Every visible text in `selectors`, its colour composited on its opaque ground, and the ratio.
_LEGIBILITY = """(selectors) => {
  const parse = (c) => {
    const m = c && c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3]));
  const lum = (rgb) => {
    const [r, g, b] = rgb.map((v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const ground = (el) => {
    const layers = [];
    for (let a = el; a; a = a.parentElement) {
      const c = parse(getComputedStyle(a).backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let rgb = parse(getComputedStyle(document.documentElement).backgroundColor);
    if (!rgb || rgb[3] < 1) rgb = [255, 255, 255, 1];
    let out = rgb.slice(0, 3);
    for (const layer of layers.reverse()) out = over(layer, out);
    return out;
  };
  const opacity = (el) => { let o = 1; for (let a = el; a; a = a.parentElement) o *= Number(getComputedStyle(a).opacity); return o; };
  const seen = new Set();
  const rows = [];
  for (const selector of selectors) {
    for (const root of document.querySelectorAll(selector)) {
      for (const el of [root, ...root.querySelectorAll('*')]) {
        if (seen.has(el) || el.closest('svg, canvas, script, style, [hidden]')) continue;
        seen.add(el);
        const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
        if (!own) continue;
        const cs = getComputedStyle(el);
        const box = el.getBoundingClientRect();
        if (cs.visibility !== 'visible' || cs.display === 'none' || box.width < 1 || box.height < 1) continue;
        if (el.closest(':disabled, [aria-disabled="true"], .is-disabled')) continue;
        const bg = ground(el);
        const ink = parse(cs.color);
        const alpha = ink[3] * opacity(el);
        const drawn = over([ink[0], ink[1], ink[2], alpha], bg);
        rows.push({
          selector, tag: el.tagName.toLowerCase(), id: el.id, cls: String(el.className),
          text: el.textContent.trim().slice(0, 40), ratio: Math.round(ratio(drawn, bg) * 100) / 100,
          color: cs.color, ground: `rgb(${bg.map(Math.round).join(', ')})`,
        });
      }
    }
  }
  return rows;
}"""


# ------------------------------------------------------------------ helpers --


def _open(p, base, path="/", *, scheme="dark", stored="unset", viewport=(1600, 900), fragment="",
          browser=None, gl=False, downloads=False, ready=None):
    """`path` in a page emulating the system's `scheme`, with `stored` seeded in localStorage first.

    Returns the browser, the page, the problems (console and page errors,
    failed responses) and every /api/ request, recorded from the first one.
    """
    browser = browser or p.chromium.launch(args=GL_ARGS if gl else None)
    page = browser.new_page(color_scheme=scheme, viewport={"width": viewport[0], "height": viewport[1]},
                            accept_downloads=downloads)
    problems, requests = [], []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    page.add_init_script(_RECORD_FIRST_PAINT)
    if stored != "unset":
        page.add_init_script(_SEED % (json.dumps(STORAGE_KEY), json.dumps(stored)))
    page.goto(f"{base}{path}{fragment}")
    _wait_drawn(page, path, ready)
    return browser, page, problems, requests


def _wait_drawn(page, path, ready=None):
    if ready:
        page.wait_for_function(ready, timeout=30_000)
    elif path == "/":
        page.wait_for_function(
            "() => ['plot-xy','plot-yz','plot-xz','plot-energy'].every((id) => "
            "document.getElementById(id)?.querySelector('canvas')) "
            "&& document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
    elif path == "/models":
        page.wait_for_function("() => document.getElementById('stat-kind')?.textContent.trim() !== '—'",
                               timeout=30_000)
    else:
        page.wait_for_function(
            "() => document.querySelector('#paper .front') "
            "&& document.getElementById('badge-memory')?.textContent.trim() !== '—'", timeout=30_000)
    page.wait_for_timeout(600)


def _state(page):
    return page.evaluate(_STATE, STORAGE_KEY)


def _toggle(page, requests):
    """Click the toggle; the /api/ requests it caused within a settle of 1.2 s."""
    before = len(requests)
    page.click("#theme-toggle")
    page.wait_for_timeout(1200)
    return requests[before:]


def _open_drawer(page, panel_id):
    page.click(f'.main button[data-inspect="{panel_id}"]')
    page.wait_for_function("() => !document.getElementById('inspector').hidden")
    page.wait_for_timeout(150)


def _mark_drawer(page):
    """Put a sentinel into the open drawer's body; a rebuild of the notes replaces it."""
    page.evaluate("() => { const p = document.createElement('p'); p.id = 'stale-notes'; "
                  "document.getElementById('inspector-body').append(p); }")


def _drawer_marked(page):
    return page.evaluate("() => Boolean(document.getElementById('stale-notes'))")


def _drawer_text(page):
    return page.evaluate("() => document.getElementById('inspector-body').innerText")


def _picked(base):
    return httpx.get(f"{base}/api/event/pick", params={"table_name": BASELINE_TABLE}, timeout=30).json()["event_number"]


# --------------------------------------------------------------- the boot --


@pytest.mark.parametrize("scheme", ["dark", "light"])
@pytest.mark.parametrize("name", list(PAGES))
def test_the_system_theme_is_in_force_before_the_first_paint(live_server, name, scheme):
    """Nothing stored: the boot script reads the system's scheme before the stylesheets paint."""
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, live_server["base"], PAGES[name], scheme=scheme)
        first = page.evaluate("() => window.__firstPaint")
        state = _state(page)
        browser.close()
    assert first["theme"] == scheme, first
    assert state["theme"] == scheme and state["stored"] is None, state
    # The ground at DOMContentLoaded is the one the page keeps: no flash of the other theme.
    assert first["background"] == state["background"] == CANVAS[scheme], (first, state)
    assert state["label"] == f"Switch to the {OTHER[scheme]} theme", state
    assert "follows your system" in state["title"], state
    assert problems == [], problems


@pytest.mark.parametrize("system,stored", [("light", "dark"), ("dark", "light")])
def test_a_stored_choice_beats_the_system_and_a_system_flip(live_server, system, stored):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, live_server["base"], "/", scheme=system, stored=stored)
        first = page.evaluate("() => window.__firstPaint")
        assert first["theme"] == stored and first["background"] == CANVAS[stored], first
        assert _state(page)["stored"] == stored
        # The system changes its mind while a choice is stored: the page keeps the choice.
        page.emulate_media(color_scheme=stored)
        page.wait_for_timeout(400)
        page.emulate_media(color_scheme=system)
        page.wait_for_timeout(400)
        state = _state(page)
        assert state["theme"] == stored and state["stored"] == stored, state
        assert "was chosen here" in state["title"], state
        browser.close()
    assert problems == [], problems


def test_a_live_system_flip_is_followed_when_nothing_is_stored(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, live_server["base"], "/", scheme="dark")
        before = len(requests)
        page.emulate_media(color_scheme="light")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'light'", timeout=5_000)
        page.wait_for_timeout(600)
        light = _state(page)
        ink = page.evaluate(_AXIS_INK, "plot-xy")
        page.emulate_media(color_scheme="dark")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'", timeout=5_000)
        page.wait_for_timeout(600)
        dark = _state(page)
        browser.close()
    assert light["stored"] is None and light["background"] == CANVAS["light"], light
    assert set(ink) == {MUTED["light"]}, ink
    assert dark["stored"] is None and dark["background"] == CANVAS["dark"], dark
    assert requests[before:] == [], requests[before:]
    assert problems == [], problems


# ------------------------------------------------------------- the toggle --


@pytest.mark.parametrize("system", ["dark", "light"])
def test_the_toggle_flips_stores_survives_a_reload_and_keeps_the_hash(live_server, system):
    fragment = f"#table_name={BASELINE_TABLE}&frame=local&model=energy"
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, live_server["base"], "/", scheme=system, fragment=fragment)
        start = _state(page)
        assert start["theme"] == system and start["stored"] is None, start

        # A click away from the system's theme stores the choice.
        _toggle(page, requests)
        chosen = _state(page)
        other = OTHER[system]
        assert chosen["theme"] == other and chosen["stored"] == other, chosen
        assert chosen["label"] == f"Switch to the {system} theme", chosen
        assert chosen["title"].startswith(f"Switch to the {system} theme.") and "was chosen here" in chosen["title"]
        assert chosen["background"] == CANVAS[other], chosen
        assert chosen["hash"] == start["hash"], (start["hash"], chosen["hash"])

        # It survives a reload.
        page.reload()
        _wait_drawn(page, "/")
        reloaded = _state(page)
        assert reloaded["theme"] == other and reloaded["stored"] == other, reloaded
        assert page.evaluate("() => window.__firstPaint.theme") == other

        # A click back to the system's theme forgets the choice: the page follows the system again.
        _toggle(page, requests)
        back = _state(page)
        assert back["theme"] == system and back["stored"] is None, back
        assert back["label"] == f"Switch to the {other} theme" and "follows your system" in back["title"], back
        assert back["hash"] == start["hash"], back
        page.reload()
        _wait_drawn(page, "/")
        assert _state(page)["theme"] == system
        browser.close()
    assert problems == [], problems


# ------------------------------------------------------ repaint, no request --


def test_a_switch_on_the_physics_page_repaints_everything_and_asks_nothing(live_server):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, "/", scheme="dark",
                                                  fragment=f"#table_name={BASELINE_TABLE}")
        for card_id in PHYSICS_CARDS:
            state = _physics_card(page, card_id)
            assert state["canvas"] and state["series"], (card_id, state)
        page.locator('.card[data-panel="xy"]').scroll_into_view_if_needed()
        plots = ["plot-xy", "plot-yz", "plot-xz", "plot-energy"] + [f"plot-{c}" for c in PHYSICS_CARDS]
        dark = {plot: page.evaluate(_AXIS_INK, plot) for plot in plots}
        raster = page.evaluate(_RASTER, "plot-xy")
        fit_table = page.evaluate("() => document.getElementById('fit-table')?.innerHTML ?? null")
        _open_drawer(page, "xy")
        _mark_drawer(page)

        asked = _toggle(page, requests)
        assert asked == [], f"a theme switch asked the service: {asked}"
        light = {plot: page.evaluate(_AXIS_INK, plot) for plot in plots}
        for plot in plots:
            assert dark[plot] and set(dark[plot]) <= {MUTED["dark"], None}, (plot, dark[plot])
            assert MUTED["light"] in light[plot] and MUTED["dark"] not in light[plot], (plot, light[plot])
        assert page.evaluate(_RASTER, "plot-xy") != raster, "the XY raster kept the dark theme's pixels"
        # The energy panel's HTML fit table: its slice swatches take the light theme's series colours.
        assert fit_table and page.evaluate("() => document.getElementById('fit-table').innerHTML") != fit_table
        # The open drawer is rebuilt, to exactly what a page booted in the light theme shows.
        assert not _drawer_marked(page)
        switched = _drawer_text(page)
        _, fresh, found, _ = _open(p, base, "/", scheme="light", fragment=f"#table_name={BASELINE_TABLE}",
                                   browser=browser)
        _open_drawer(fresh, "xy")
        assert switched == _drawer_text(fresh)
        fresh.close()

        # A card scrolled to after the switch draws in the theme in force.
        later = _physics_card(page, "distribution")
        assert later["canvas"] and later["series"], later
        assert MUTED["light"] in page.evaluate(_AXIS_INK, "plot-distribution")
        browser.close()
    assert problems == [] and found == [], problems + found


def test_a_switch_repaints_the_event_inspector_and_the_compare_grid_without_a_request(live_server):
    base = live_server["base"]
    n = _picked(base)
    cells = [f"plot-event-{r}-{c}" for r in ("lab", "trans", "local") for c in ("xy", "xz", "yz")]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, "/", fragment=f"#event={n}&shower=b", ready=(
            "() => ['lab','trans','local'].every((r) => ['xy','xz','yz'].every((c) => "
            "document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))"))
        _open_drawer(page, "event-local-xy")
        _mark_drawer(page)
        assert _toggle(page, requests) == []
        for plot in cells:
            ink = page.evaluate(_AXIS_INK, plot)
            assert MUTED["light"] in ink and MUTED["dark"] not in ink, (plot, ink)
        assert not _drawer_marked(page)
        browser.close()

        browser, page, problems2, requests = _open(p, base, "/", fragment="#compare=1", ready=(
            "() => !document.getElementById('compare-grid').hidden && "
            "[...document.querySelectorAll('#compare-grid .plot')].some((el) => el.querySelector('canvas'))"))
        page.wait_for_timeout(1500)
        plots = page.evaluate("() => [...document.querySelectorAll('#compare-grid .plot')]"
                              ".filter((el) => echarts.getInstanceByDom(el)).map((el) => el.id)")
        assert plots, "the compare grid drew nothing"
        assert _toggle(page, requests) == []
        for plot in plots:
            ink = page.evaluate(_AXIS_INK, plot)
            assert MUTED["light"] in ink and MUTED["dark"] not in ink, (plot, ink)
        browser.close()
    assert problems == [] and problems2 == [], problems + problems2


def test_a_switch_on_the_models_page_repaints_the_cards_and_the_3d_views(live_server):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(
            p, base, "/models", fragment=f"#table_name={BASELINE_TABLE}&model=energy", gl=True)
        for card_id in MODELS_CARDS:
            _models_card(page, card_id)
        for card_id in GL_CARDS:
            page.locator(f'.main .card[data-panel="{card_id}"]').scroll_into_view_if_needed()
            page.wait_for_function(_GL_DRAWN, arg=card_id, timeout=30_000)
            page.wait_for_timeout(800)
        dark_cards = {c: page.evaluate(_AXIS_INK, f"plot-{c}") for c in MODELS_CARDS}

        # The drawer opens first: it narrows the cards, and a narrower card refits the opening zoom.
        page.locator('.main .card[data-panel="vox-event"]').scroll_into_view_if_needed()
        _open_drawer(page, "vox-event")
        page.wait_for_timeout(800)
        # The reader turns, pans and zooms the event's cubes.
        page.locator('.main .card[data-panel="vox-event"]').scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        box = page.locator("#plot-vox-event").bounding_box()
        x, y = box["x"] + box["width"] * 0.4, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 60, y + 25, steps=8)
        page.mouse.up()
        page.mouse.move(x, y)
        page.mouse.down(button="middle")
        page.mouse.move(x + 30, y - 20, steps=8)
        page.mouse.up(button="middle")
        for _ in range(3):
            page.mouse.wheel(0, -200)
            page.wait_for_timeout(120)
        page.wait_for_timeout(500)
        # And the cloud is turned programmatically: echarts-gl writes the angles into the model.
        page.evaluate("() => echarts.getInstanceByDom(document.getElementById('plot-vox-ensemble'))"
                      ".dispatchAction({ type: 'grid3DChangeCamera', alpha: 10, beta: 70 })")
        page.wait_for_timeout(300)
        before = {c: page.evaluate(_CAMERA, c) for c in GL_CARDS}
        species = page.evaluate("() => [...document.querySelectorAll('.voxel-swatch')]"
                                ".map((s) => s.style.getPropertyValue('--swatch'))")
        _mark_drawer(page)

        asked = _toggle(page, requests)
        assert asked == [], f"a theme switch asked the service: {asked}"
        after = {c: page.evaluate(_CAMERA, c) for c in GL_CARDS}
        for c in MODELS_CARDS:
            ink = page.evaluate(_AXIS_INK, f"plot-{c}")
            assert MUTED["dark"] in dark_cards[c] and MUTED["light"] in ink and MUTED["dark"] not in ink, (c, ink)
        for c in GL_CARDS:
            b, a = before[c], after[c]
            assert set(b["labels"] + b["names"]) == {MUTED["dark"]} and b["axisLine"] == BORDER["dark"], b
            assert set(a["labels"] + a["names"]) == {MUTED["light"]} and a["axisLine"] == BORDER["light"], a
            assert a["tooltip"] != b["tooltip"], (b["tooltip"], a["tooltip"])
            assert a["model"]["projection"] == "orthographic" and a["series"] == b["series"], a
            # The model's angles and centre, and the camera the reader sees, zoom included.
            assert {k: a["model"][k] for k in ("alpha", "beta", "center")} == \
                {k: b["model"][k] for k in ("alpha", "beta", "center")}, (c, b["model"], a["model"])
        event_b, event_a = before["vox-event"], after["vox-event"]
        assert event_a["control"] == event_b["control"], (event_b["control"], event_a["control"])
        assert event_b["control"]["zoom"] != pytest.approx(event_b["model"]["size"] + 1), "the wheel did not zoom"
        assert (after["vox-ensemble"]["model"]["alpha"], after["vox-ensemble"]["model"]["beta"]) == (10, 70)
        if species:
            assert page.evaluate("() => [...document.querySelectorAll('.voxel-swatch')]"
                                 ".map((s) => s.style.getPropertyValue('--swatch'))") != species
        assert not _drawer_marked(page)
        # The paired projections follow.
        for plot in ("plot-vproj-xy", "plot-eproj-xy"):
            assert MUTED["light"] in page.evaluate(_AXIS_INK, plot), plot
        browser.close()
    assert problems == [], problems


# ------------------------------------------------------- export invariance --


#: zrender numbers every instance it creates (`zr<N>-c0`) and every style class across instances
#: (`zr<N>-cls-<M>`): two exports of one figure from one page, in one theme, differ in those numbers alone.
_ZR_INSTANCE = re.compile(r"\bzr\d+-")
_ZR_CLASS = re.compile(r"\bzr-cls-(\d+)\b")


def _unnumbered(svg):
    """An exported SVG with zrender's running numbers replaced by their order of first use."""
    svg = _ZR_INSTANCE.sub("zr-", svg)
    order = {}
    return _ZR_CLASS.sub(lambda m: f"zr-cls-{order.setdefault(m.group(1), len(order))}", svg)
#: The exported figures checked: the 2 x 2's entry panel, the energy panel and one physics card.
EXPORTED = ("xy", "energy", "profile-w")


def _exports(page):
    _physics_card(page, "profile-w")
    page.locator('.card[data-panel="xy"]').scroll_into_view_if_needed()
    return {panel: _download_svg(page, panel) for panel in EXPORTED}


def _same_name(a, b):
    # The name carries the export's time stamp; the rest of it names the figure.
    stamp = re.compile(r"_\d{8}_\d{6}")
    return stamp.sub("", a) == stamp.sub("", b)


def test_exported_figures_do_not_depend_on_the_screen_theme(live_server):
    """Byte for byte: a page booted dark and one booted light export the same SVG; and live, a dark
    export, a switch and a light export differ only in zrender's running numbers, as two exports in one theme do."""
    fragment = f"#table_name={BASELINE_TABLE}"
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        problems, booted = [], {}
        for scheme in ("dark", "light"):
            _, page, found, _ = _open(p, live_server["base"], "/", scheme=scheme, fragment=fragment,
                                      browser=browser, downloads=True)
            booted[scheme] = _exports(page)
            problems += found
            page.close()
        _, page, found, requests = _open(p, live_server["base"], "/", scheme="dark", fragment=fragment,
                                         browser=browser, downloads=True)
        dark = _exports(page)
        again = {panel: _download_svg(page, panel) for panel in EXPORTED}
        _toggle(page, requests)
        assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
        light = {panel: _download_svg(page, panel) for panel in EXPORTED}
        problems += found
        browser.close()
    for panel in EXPORTED:
        assert _same_name(booted["dark"][panel][0], booted["light"][panel][0]), panel
        assert booted["dark"][panel][1] == booted["light"][panel][1], f"the {panel} SVG depends on the boot theme"
        # In one page, a second export in the same theme already moves zrender's number, and only that.
        assert again[panel][1] != dark[panel][1]
        assert _unnumbered(again[panel][1]) == _unnumbered(dark[panel][1]), panel
        assert _same_name(dark[panel][0], light[panel][0]), panel
        assert _unnumbered(light[panel][1]) == _unnumbered(dark[panel][1]), (
            f"the {panel} SVG changed with a live theme switch")
        assert _unnumbered(light[panel][1]) == _unnumbered(booted["dark"][panel][1]), panel
    assert problems == [], problems


def test_the_methodology_figures_are_the_same_in_both_themes(live_server):
    """The figures, their legible runs (`data-from`, `data-to`) included, are identical when the page boots
    dark, boots light, or switches live; neither theme logs an error."""
    figures = """() => ({
      ramps: [...document.querySelectorAll('.ramp-legible')].map((r) =>
        [r.getAttribute('data-palette'), r.getAttribute('data-from'), r.getAttribute('data-to')]),
      svgs: Object.fromEntries([...document.querySelectorAll('#paper figure')].filter((f) => f.querySelector('svg'))
        .map((f) => [f.id, f.querySelector('svg').outerHTML])),
    })"""
    seen = {}
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        problems = []
        for scheme in ("dark", "light"):
            _, page, found, requests = _open(p, live_server["base"], "/methodology", scheme=scheme, browser=browser)
            assert page.evaluate("() => document.documentElement.dataset.theme") == scheme
            seen[scheme] = page.evaluate(figures)
            problems += found
            if scheme == "dark":
                # And live: a switch redraws nothing there, and asks for nothing.
                assert _toggle(page, requests) == []
                seen["switched"] = page.evaluate(figures)
            page.close()
        browser.close()
    # The two figures measured against the screen card - the sequential ramps (the four `.ramp-legible`
    # runs) and the folded PuOr - are pinned to the dark card (exhibits.js `CARD_HEX`); the SE(3)
    # schematic draws no ramp. Every article figure is compared.
    assert len(seen["dark"]["ramps"]) == 4, seen["dark"]["ramps"]
    assert {"fig-ramps", "fig-puor"} <= set(seen["dark"]["svgs"]), list(seen["dark"]["svgs"])
    assert seen["dark"] == seen["light"] == seen["switched"]
    assert problems == [], problems


# ----------------------------------------------------- legibility in place --

#: The page's chrome: header, sidebar, status bar, card titles and toolbars, the drawer and the banners.
CHROME = (".header", "#sidebar", ".statusbar", ".card > h2", "#inspector", ".banner")


def _legibility(page):
    page.evaluate("""() => {
      for (const [id, text] of [['banner', 'A warning the service sent with its response.'],
                                ['kind-banner', 'What this experiment cannot show, and why.']]) {
        const banner = document.getElementById(id);
        if (banner && banner.hidden) { banner.hidden = false; banner.querySelector('.banner-text').textContent = text; }
      }
    }""")
    page.wait_for_timeout(150)
    return page.evaluate(_LEGIBILITY, list(CHROME))


def test_the_chrome_text_is_legible_in_place(live_server):
    measured = {}
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        problems = []
        for scheme in ("dark", "light"):
            _, page, found, _ = _open(p, live_server["base"], "/", scheme=scheme, browser=browser,
                                      fragment=f"#table_name={BASELINE_TABLE}")
            _open_drawer(page, "xy")
            measured[scheme] = _legibility(page)
            problems += found
            page.close()
        browser.close()
    for scheme, rows in measured.items():
        worst = min(rows, key=lambda r: r["ratio"])
        print(f"{scheme}: {len(rows)} texts, worst {worst['ratio']}:1 "
              f"({worst['tag']}#{worst['id']}.{worst['cls']} {worst['text']!r} {worst['color']} on {worst['ground']})")
    assert len(measured["light"]) > 100, len(measured["light"])
    assert {r["selector"] for r in measured["light"]} == set(CHROME)
    # The banners' dismiss glyph is a control's glyph, held to 3:1 (layout.css: 0.85 of the warn
    # ink on the warn tint in light); every other text is held to 4.5:1.
    glyphs = [r for r in measured["light"] if "banner-close" in r["cls"]]
    assert glyphs and all(r["ratio"] >= GLYPH_FLOOR for r in glyphs), glyphs
    failing = [r for r in measured["light"] if r["ratio"] < TEXT_FLOOR and "banner-close" not in r["cls"]]
    assert not failing, failing
    # Dark is the control: held to what it meets today (DARK_FLOOR), not raised by this change.
    dark_failing = [r for r in measured["dark"] if r["ratio"] < DARK_FLOOR]
    assert not dark_failing, dark_failing
    assert problems == [], problems


#: WCAG's floor for a control's non-text glyph.
GLYPH_FLOOR = 3.0
#: The worst the dark chrome measures today: the metric cards' faded <small> lines in the sidebar, 3.74:1
#: (#8b949e at reduced opacity on #161b22), and the banners' dismiss glyph, 3.83:1. A control, not a target.
DARK_FLOOR = 3.7


# ------------------------------------------------------------ the tooltips --


@pytest.mark.parametrize("viewport", [(1600, 900), (1024, 768)], ids=lambda v: f"{v[0]}x{v[1]}")
def test_the_tooltip_rule_holds_in_the_light_theme(live_server, viewport, monkeypatch):
    """test_browser_tooltip.py's own measurement and assertions, on a page booted light."""
    def light_open(p, server, size, fragment):
        browser = p.chromium.launch()
        page = browser.new_page(color_scheme="light", viewport={"width": size[0], "height": size[1]})
        page.goto(f"{server['base']}/{fragment}")
        page.wait_for_function(
            "() => ['plot-xy','plot-yz','plot-xz','plot-energy'].every((id) => "
            "document.getElementById(id)?.querySelector('canvas'))", timeout=30_000)
        assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
        page.wait_for_timeout(1500)
        return browser, page

    monkeypatch.setattr(tooltip_checks, "_open", light_open)
    tooltip_checks.test_tooltips_are_readable_and_keep_the_hovered_panel_visible(live_server, viewport, "")


# ----------------------------------------------------------------- layout --

_HEADER = """() => {
  const header = document.querySelector('.header');
  const items = [...header.children].map((c) => c.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
  const toggle = document.getElementById('theme-toggle').getBoundingClientRect();
  return {
    height: header.getBoundingClientRect().height,
    overflow: header.scrollWidth - header.clientWidth,
    page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    // One line: every item's top above every item's bottom.
    oneLine: Math.max(...items.map((r) => r.top)) < Math.min(...items.map((r) => r.bottom)),
    toggle: { top: toggle.top, bottom: toggle.bottom, width: toggle.width },
    headerTop: header.getBoundingClientRect().top, headerBottom: header.getBoundingClientRect().bottom,
  };
}"""

_WITHOUT_TOGGLE = "() => { document.getElementById('theme-toggle').style.display = 'none'; }"


@pytest.mark.parametrize("viewport", [(1024, 768), (1600, 900)], ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("name", list(PAGES))
def test_the_header_fits_and_the_toggle_shows_a_focus_ring(live_server, name, viewport):
    """The toggle neither wraps nor widens the header past the window, in either theme.

    At 1024 px the Physics and Models headers already ran 460 / 394 px past
    the window before the toggle existed (their `nowrap` row holds the
    experiment badge, 480 px with the demonstration's name), and the
    Methodology header already took two lines; neither is the toggle's doing,
    so there the header is held to what it is without the toggle.
    """
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        layout, bare = {}, {}
        for scheme in ("dark", "light"):
            _, page, problems, _ = _open(p, live_server["base"], PAGES[name], scheme=scheme, viewport=viewport,
                                         browser=browser)
            layout[scheme] = page.evaluate(_HEADER)
            if scheme == "light":
                # Tab onto the toggle from the control before it: a keyboard focus, so :focus-visible applies.
                page.evaluate("() => { const b = document.getElementById('theme-toggle'); "
                              "const all = [...document.querySelectorAll('button, a[href], input, select')]; "
                              "all[all.indexOf(b) - 1]?.focus(); }")
                page.keyboard.press("Tab")
                ring = page.evaluate("() => { const b = document.activeElement; const cs = getComputedStyle(b); "
                                     "return { id: b.id, style: cs.outlineStyle, width: cs.outlineWidth, "
                                     "color: cs.outlineColor }; }")
            page.evaluate(_WITHOUT_TOGGLE)
            bare[scheme] = page.evaluate(_HEADER)
            assert problems == [], problems
            page.close()
        browser.close()
    print(f"{name} {viewport}: header {layout['dark']['height']} px, past the window by "
          f"{layout['dark']['overflow']} px ({bare['dark']['overflow']} px without the toggle)")
    for scheme, got in layout.items():
        without = bare[scheme]
        # No wrap: the toggle adds no height, and sits inside the header's band.
        assert got["height"] == without["height"], (scheme, got, without)
        assert got["headerTop"] <= got["toggle"]["top"] and got["toggle"]["bottom"] <= got["headerBottom"], got
        # No overflow the toggle caused.
        assert without["overflow"] > 0 or got["overflow"] <= 0, (scheme, got, without)
        assert without["page"] > 0 or got["page"] <= 0, (scheme, got, without)
        if viewport[0] >= 1600:
            assert got["oneLine"] and got["overflow"] <= 0 and got["page"] <= 0, (scheme, got)
    assert layout["light"]["height"] == layout["dark"]["height"], layout
    assert ring["id"] == "theme-toggle" and ring["style"] == "solid" and ring["width"] == "2px", ring
    # The light accent, #0b5fbe: 6.19:1 on the white card, 5.81:1 on the header's canvas.
    assert ring["color"] == "rgb(11, 95, 190)", ring


# -------------------------------------------------- dark keeps its colours --


def test_the_dark_controls_keep_todays_computed_colours(live_server):
    probe = """() => {
      const style = (el) => { const cs = getComputedStyle(el); return { bg: cs.backgroundColor, ink: cs.color }; };
      const mini = document.querySelector('.card .mini[data-reset]');
      const primary = document.createElement('button');
      primary.className = 'action primary';
      primary.textContent = 'probe';
      document.querySelector('.header').append(primary);
      const out = { body: style(document.body), card: style(document.querySelector('.card')),
                    mini: mini ? style(mini) : null, primary: style(primary) };
      primary.remove();
      return out;
    }"""
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, live_server["base"], "/", scheme="dark")
        got = page.evaluate(probe)
        browser.close()
    assert got["body"]["bg"] == "rgb(13, 17, 23)", got
    assert got["card"]["bg"] == "rgb(28, 33, 40)", got
    assert got["mini"] == {"bg": "rgb(33, 38, 45)", "ink": "rgb(201, 209, 217)"}, got
    assert got["primary"] == {"bg": "rgb(88, 166, 255)", "ink": "rgb(4, 16, 31)"}, got
    assert problems == [], problems
