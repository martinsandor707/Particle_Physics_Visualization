"""The Entry anchor's i button in Chromium: the popup states both definitions.

Its three formulas are set as MathML through math.js; each must have a real
box inside its block, and the page must log no error.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks. The
distances the popup quotes are read back from the D-frame response the page
itself asked for, so the test holds whatever the demonstration events are.
"""

from __future__ import annotations

import math
import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium entry-anchor check",
)

_TEXT = "() => document.querySelector('.popover.is-explainer')?.textContent ?? null"
_BOX = """() => {
  const r = document.querySelector('.popover.is-explainer').getBoundingClientRect();
  return { top: r.top, bottom: r.bottom, left: r.left, right: r.right,
           vh: window.innerHeight, vw: window.innerWidth };
}"""
_IN_USE = """() => [...document.querySelectorAll('.popover.is-explainer h4')]
  .filter((h) => h.querySelector('.in-use')).map((h) => h.firstChild.textContent.trim())"""
_FORMULAS = """() => [...document.querySelectorAll('.popover.is-explainer .formula')].map((f) => {
  const math = f.querySelector('math');
  if (!math) return { missing: f.textContent };
  const r = math.getBoundingClientRect();
  return { display: math.getAttribute('display'), width: r.width, height: r.height,
           box: f.clientWidth, annotation: math.querySelector('annotation')?.textContent ?? '' };
})"""
_LAST_PROJECTIONS_URL = """() => performance.getEntriesByType('resource')
  .map((e) => e.name).filter((n) => n.includes('/api/projections')).pop()"""


def _js_round(value: float) -> str:
    """`Number.toFixed(0)` for a positive millimetre value."""
    return str(math.floor(value + 0.5))


def _open(p, base, viewport):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.goto(f"{base}/#frame=canonical")
    page.wait_for_function("() => document.getElementById('title-xy').textContent.startsWith('D–Y′')",
                           timeout=30_000)
    page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
    return browser, page, errors


@pytest.mark.parametrize("viewport", [(1600, 900), (1280, 600)])
def test_the_entry_anchor_i_button_explains_both_definitions(live_server, viewport):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, viewport)
        url = page.evaluate(_LAST_PROJECTIONS_URL)
        residual = httpx.get(url, timeout=30).json()["frame"]["anchor_residual"]

        assert page.is_visible("#info-anchor")
        assert page.get_attribute("#info-anchor", "aria-expanded") == "false"
        page.click("#info-anchor")
        page.wait_for_selector(".popover.is-explainer")
        text = page.evaluate(_TEXT)
        for phrase in ("Entry anchor of the D-frame", "Back-projected 3-D centroid (default)",
                       "First-layer entry point P₀", "What switching changes",
                       "The file records no true entry point"):
            assert phrase in text, phrase
        assert (f"a median {_js_round(residual['a']['median'])} mm apart for shower A and "
                f"{_js_round(residual['b']['median'])} mm for shower B") in text
        assert page.evaluate(_IN_USE) == ["Back-projected 3-D centroid (default)"]

        # The three formulas are MathML set by math.js, each with a real box, the TeX kept as its annotation.
        formulas = page.evaluate(_FORMULAS)
        assert len(formulas) == 3, formulas
        for formula in formulas:
            assert formula["display"] == "block" and formula["width"] > 40 and formula["height"] > 10, formula
            assert formula["width"] <= formula["box"] + 1, formula
            assert formula["annotation"].startswith(("\\begin{aligned}", "\\text{entry}")), formula

        # Inside the window however short it is, beside the sidebar so neither the
        # button nor the radios it explains are covered, with the focus in it.
        box = page.evaluate(_BOX)
        assert box["top"] >= 0 and box["bottom"] <= box["vh"], box
        assert box["left"] >= 0 and box["right"] <= box["vw"], box
        sidebar = page.evaluate("() => document.getElementById('sidebar').getBoundingClientRect().right")
        assert box["left"] >= sidebar, (box, sidebar)
        assert page.evaluate("() => document.activeElement.classList.contains('is-explainer')")
        assert page.get_attribute("#info-anchor", "aria-expanded") == "true"

        # A click inside keeps it open; Escape closes it and returns the focus.
        page.click(".popover.is-explainer h3")
        assert page.evaluate(_TEXT) is not None
        page.keyboard.press("Escape")
        assert page.evaluate(_TEXT) is None
        assert page.evaluate("() => document.activeElement.id") == "info-anchor"
        assert page.get_attribute("#info-anchor", "aria-expanded") == "false"

        # The definition in use follows the control.
        page.check('input[name="anchor"][value="p0"]')
        page.click("#info-anchor")
        page.wait_for_selector(".popover.is-explainer")
        assert page.evaluate(_IN_USE) == ["First-layer entry point P₀"]
        page.mouse.click(viewport[0] - 20, viewport[1] - 20)
        assert page.evaluate(_TEXT) is None, "a click elsewhere closes it"
        assert errors == [], errors
        browser.close()


def test_the_i_button_is_hidden_outside_the_translated_view(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(f"{live_server['base']}/")
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
        assert not page.is_visible("#info-anchor")
        page.check('input[name="frame-view"][value="aligned"]')
        page.wait_for_function("() => !document.getElementById('anchor-sub').hidden", timeout=10_000)
        assert page.is_visible("#info-anchor")
        browser.close()
