"""The Methodology page (``/methodology``), driven in Chromium.

The article is drawn from its content modules (``methodology/render.js``),
so what is checked here is what only a browser can tell:

* the page loads without a console error, a page error or a failed request,
  and fills its compute badge, view chip and provenance line from the service;
* every ``<math>`` element has a box, and the numbered equations run 1..n;
* an equation's TeX panel opens from its toggle and from a click on the math,
  closes on Escape, and its Copy button writes the source to the clipboard;
* a TOC click scrolls the article column to the section, moves the focus
  there, keeps every view key in the hash and adds ``at``;
* the Physics and Models tabs carry the hash without ``at``;
* a badge opens ``/?panel=…&from=…&from_sec=…`` (or ``/models?…``) with the
  view keys (where it lands is the landing pages' own test);
* print emulation hides the header and the outline and paints black on white.

Screenshots (1600 × 900, 1100 × 800, print) are written to
``CALOSRV_METHODOLOGY_SCREENS`` when it names a folder, else to the test's
temporary folder. ``CALOSRV_METHODOLOGY_PAGE`` names another page path to
check instead of ``/methodology`` - a preview of content not yet merged.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Methodology check",
)

PAGE = os.environ.get("CALOSRV_METHODOLOGY_PAGE", "/methodology")
#: A view a reader brings: every key of it must survive the page.
VIEW = "table_name=experiment_baseline&frame=canonical&model=energy"
VIEW_KEYS = {"table_name": "experiment_baseline", "frame": "canonical", "model": "energy"}


def _screens(tmp_path: Path) -> Path:
    folder = Path(os.environ.get("CALOSRV_METHODOLOGY_SCREENS") or tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _open(p, base, *, fragment=VIEW, viewport=(1600, 900), browser=None, clipboard=False):
    """The page with `fragment`, with every console error, page error and failed request recorded."""
    browser = browser or p.chromium.launch()
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    if clipboard:
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    page = context.new_page()
    problems = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.goto(f"{base}{PAGE}{'#' + fragment if fragment else ''}")
    # Drawn, and the service's answers in: the compute badge and the provenance line.
    page.wait_for_function(
        "() => document.querySelector('#paper .front') "
        "&& document.getElementById('badge-memory')?.textContent.trim() !== '—' "
        "&& document.querySelector('[data-provenance=\"version\"]')?.textContent !== '…'",
        timeout=30_000,
    )
    return browser, page, problems


def _hash(page) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).fragment).items()}


def test_the_page_draws_cleanly_and_fills_from_the_service(live_server, tmp_path):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"])
        state = page.evaluate("""() => ({
          chip: document.getElementById('view-chip-text').textContent,
          provenance: document.querySelector('.provenance').textContent,
          title: document.querySelector('.article-title')?.textContent ?? '',
          toc: document.querySelectorAll('#toc a[data-goto]').length,
          sections: document.querySelectorAll('#paper section[data-section]').length,
          banner: document.getElementById('banner').hidden,
          maths: [...document.querySelectorAll('#paper math')].map((m) => {
            const r = m.getBoundingClientRect(); return [r.width, r.height]; }),
          numbers: [...document.querySelectorAll('#paper .eq-number')].map((a) => a.textContent),
          equations: document.querySelectorAll('#paper .equation').length,
          wide: document.getElementById('main').scrollWidth - document.getElementById('main').clientWidth,
        })""")
        page.screenshot(path=str(_screens(tmp_path) / "methodology-1600x900.png"))
        browser.close()
    assert problems == []
    assert state["banner"] is True, "no problem to report"
    assert state["title"] and state["toc"] == state["sections"] > 0
    assert state["chip"] == "Baseline (demonstration dataset) · Separation-Aligned (D-Frame) › Translated · Energy Estimation Model"
    assert re.fullmatch(r"calosrv \S+ · static build ([0-9a-f]{12}|unstamped) · rendered \d{4}-\d{2}-\d{2}", state["provenance"]), \
        state["provenance"]
    # Every equation is drawn, and numbered 1..n.
    assert all(w > 0 and h > 0 for w, h in state["maths"]), state["maths"]
    assert state["numbers"] == [f"({n})" for n in range(1, state["equations"] + 1)]
    # The article column never scrolls sideways: a long equation or table scrolls inside itself.
    assert state["wide"] <= 0


def test_the_narrow_window_and_the_default_view(live_server, tmp_path):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"], fragment="", viewport=(1100, 800))
        chip = page.evaluate("document.getElementById('view-chip-text').textContent")
        wide = page.evaluate("document.getElementById('main').scrollWidth - document.getElementById('main').clientWidth")
        page.screenshot(path=str(_screens(tmp_path) / "methodology-1100x800.png"))
        browser.close()
    assert problems == []
    # A cold link: the chip names the view a cold boot of the other pages would open.
    assert chip == "Baseline (demonstration dataset) · Absolute · Segmentation Model"
    assert wide <= 0


def test_the_tex_panel_opens_closes_and_copies(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"], clipboard=True)
        if not page.locator("#paper .math-display").count():
            browser.close()
            pytest.skip("the article has no display equation yet")
        figure = page.locator("#paper .math-display").first
        toggle = figure.locator(".tex-toggle")
        panel_id = toggle.get_attribute("aria-controls")
        panel = page.locator(f"#{panel_id}")
        assert panel.is_hidden() and toggle.get_attribute("aria-expanded") == "false"
        assert figure.locator(".eq-math").get_attribute("title") == "Show the LaTeX source"
        toggle.click()
        assert panel.is_visible() and toggle.get_attribute("aria-expanded") == "true"
        source = panel.locator("code").text_content()
        annotation = figure.locator("annotation").first.text_content()
        panel.locator(".tex-copy").click()
        page.wait_for_function("(id) => document.querySelector(`#${id} .tex-status`).textContent !== ''", arg=panel_id)
        copied = page.evaluate("navigator.clipboard.readText()")
        status = panel.locator(".tex-status").text_content()
        # Escape closes it; a click on the math opens it again, and again closes it.
        page.keyboard.press("Escape")
        closed = panel.is_hidden() and toggle.get_attribute("aria-expanded") == "false"
        figure.locator(".eq-math").click()
        reopened = panel.is_visible()
        figure.locator(".eq-math").click()
        reclosed = panel.is_hidden()
        browser.close()
    assert problems == []
    assert source and copied == source == annotation and status == "Copied."
    assert closed and reopened and reclosed


def test_a_toc_click_scrolls_keeps_the_view_and_marks_the_place(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"])
        links = page.locator("#toc a[data-goto]")
        target = links.nth(min(2, links.count() - 1))
        anchor = target.get_attribute("data-goto")
        # The live href already carries the view and the place.
        target.focus()
        href = target.get_attribute("href")
        target.click()
        page.wait_for_function("(id) => document.activeElement?.id === id", arg=anchor)
        where = page.evaluate("""(id) => {
          const main = document.getElementById('main');
          return { top: document.getElementById(id).getBoundingClientRect().top - main.getBoundingClientRect().top,
                   scrolled: main.scrollTop, window: window.scrollY };
        }""", anchor)
        hashed = _hash(page)
        # A reload at that place opens there.
        page.reload()
        page.wait_for_function("(id) => document.activeElement?.id === id", arg=anchor, timeout=30_000)
        reloaded = page.evaluate("(id) => document.getElementById(id).getBoundingClientRect().top "
                                 "- document.getElementById('main').getBoundingClientRect().top", anchor)
        # The tabs carry the view without the page's own key.
        tabs = {}
        for name in ("physics", "models"):
            tab = page.locator(f'a[data-page-tab][data-page="{name}"]')
            tab.focus()
            tabs[name] = tab.get_attribute("href")
        browser.close()
    assert problems == []
    assert href.startswith(f"/methodology#{VIEW}") and href.endswith(f"at={anchor}")
    assert where["scrolled"] > 0 and -2 <= where["top"] <= 40 and where["window"] == 0
    assert hashed == {**VIEW_KEYS, "at": anchor}
    assert -2 <= reloaded <= 40
    assert tabs == {"physics": f"/#{VIEW}", "models": f"/models#{VIEW}"}


def test_a_badge_opens_its_panel_with_the_view(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"])
        badges = page.locator("#paper a[data-badge]")
        if not badges.count():
            browser.close()
            pytest.skip("the article has no badge yet")
        badge = badges.first
        badge.scroll_into_view_if_needed()
        expected = {"panel": badge.get_attribute("data-panel"), "from": badge.get_attribute("data-from"),
                    "page": badge.get_attribute("data-page"), "section": badge.get_attribute("data-from-sec"),
                    "set": badge.get_attribute("data-set")}
        before = list(problems)
        with page.expect_navigation():
            badge.click()
        url = urlparse(page.url)
        browser.close()
    assert before == []
    assert url.path == ("/" if expected["page"] == "physics" else "/models")
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert query["panel"] == expected["panel"] and query["from"] == expected["from"]
    if expected["section"]:
        assert query["from_sec"] == expected["section"]
    import json

    view = {**VIEW_KEYS, **{k: str(v).lower() if isinstance(v, bool) else str(v)
                            for k, v in json.loads(expected["set"]).items()}}
    fragment = {k: v[0] for k, v in parse_qs(url.fragment).items()}
    for key, value in view.items():
        assert fragment.get(key) == value, (key, fragment)
    assert "at" not in fragment


def test_print_hides_the_shell_and_paints_white(live_server, tmp_path):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"], viewport=(1100, 800))
        page.emulate_media(media="print")
        state = page.evaluate("""() => {
          const css = (sel, prop) => { const el = document.querySelector(sel); return el ? getComputedStyle(el)[prop] : null; };
          return { header: css('.header', 'display'), sidebar: css('.sidebar', 'display'), banner: css('.banner', 'display'),
                   badges: [...document.querySelectorAll('.links-row')].map((el) => getComputedStyle(el).display),
                   toggles: [...document.querySelectorAll('.tex-toggle')].map((el) => getComputedStyle(el).display),
                   body: css('body', 'backgroundColor'), ink: css('.paper', 'color'), app: css('.app', 'display'),
                   overflow: css('.main', 'overflowY') };
        }""")
        page.screenshot(path=str(_screens(tmp_path) / "methodology-print.png"))
        browser.close()
    assert problems == []
    assert state["header"] == "none" and state["sidebar"] == "none" and state["banner"] == "none"
    assert set(state["badges"]) <= {"none"} and set(state["toggles"]) <= {"none"}
    assert state["body"] == "rgb(255, 255, 255)" and state["ink"] == "rgb(17, 24, 39)"
    assert state["app"] == "block" and state["overflow"] == "visible"
