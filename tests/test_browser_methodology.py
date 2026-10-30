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
* print emulation hides the header and the outline and paints black on white;
* the Export button downloads one zip (busy while it works): the TeX, the
  BibTeX and each figure as a well-formed SVG and a 1890 px PNG with a 300 dpi
  ``pHYs``; every text of each paper figure, laid out by Chromium, stays on its
  canvas and clear of every other; with ``pdflatex`` and ``bibtex`` on the PATH
  the archive compiles as it is.

Screenshots (1600 × 900, 1100 × 800, print) and the exported figures (SVG and
PNG) are written to ``CALOSRV_METHODOLOGY_SCREENS`` when it names a folder,
else to the test's temporary folder. ``CALOSRV_METHODOLOGY_PAGE`` names another page path to
check instead of ``/methodology`` - a preview of content not yet merged.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import zlib
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
    context = browser.new_context(color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]})
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
        # The article has its equations: none would be a regression, not a reason to skip.
        assert page.locator("#paper .math-display").count() > 0
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
        assert badges.count() > 0
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


#: Each distinct badge target, read off the page once its links are live.
_BADGE_TARGETS = """() => {
  const seen = new Map();
  for (const a of document.querySelectorAll('#paper a[data-badge]')) {
    const key = `${a.dataset.page}|${a.dataset.panel}|${a.dataset.set || ''}`;
    if (!seen.has(key)) seen.set(key, { key, href: a.href, page: a.dataset.page, panel: a.dataset.panel });
  }
  return [...seen.values()];
}"""

#: The landing's outcome: the drawer open, or the kind banner's sentence.
_LANDED = """() => !location.search && (!document.getElementById('inspector').hidden
  || (document.getElementById('kind-banner-text')?.textContent ?? '').includes('The Methodology linked'))"""


def test_every_badge_lands_on_its_card_or_says_why(live_server):
    """Each distinct badge target opens its card with the drawer and the way back, or the banner says the
    experiment does not show that card. None names a card its page lacks, and none is hidden by a view mode
    the reader brought: the page arrives with an event pinned, which every Physics badge leaves."""
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"], fragment=f"{VIEW}&event=0")
        targets = page.evaluate(_BADGE_TARGETS)
        assert targets
        outcomes = []
        for target in targets:
            page.goto(target["href"])
            page.wait_for_function(_LANDED, timeout=30_000)
            outcomes.append((target, page.evaluate("""() => ({
              drawer: !document.getElementById('inspector').hidden,
              inspected: document.querySelector('.card.is-inspected')?.dataset.panel ?? null,
              back: Boolean(document.querySelector('#inspector-body .inspector-return a')),
              banner: document.getElementById('kind-banner-text')?.textContent ?? '' })""")))
        browser.close()
    assert problems == [], problems
    landed = [t["key"] for t, o in outcomes if o["drawer"]]
    for target, outcome in outcomes:
        if outcome["drawer"]:
            assert outcome["inspected"] == target["panel"] and outcome["back"], (target["key"], outcome)
        else:
            assert "does not show" in outcome["banner"], (target["key"], outcome["banner"])
    # The demonstration experiment serves every spatial panel, and the compare view.
    for target, _ in outcomes:
        if target["page"] == "physics" and (target["panel"] in ("xy", "yz", "xz", "energy")
                                            or target["panel"].startswith("compare-")):
            assert target["key"] in landed, target["key"]


def test_a_phone_width_reads_without_sideways_scroll(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"], viewport=(390, 844))
        folded = page.evaluate("""() => ({
          scroll: document.documentElement.scrollWidth, width: innerWidth,
          paper: document.getElementById('paper').getBoundingClientRect().width,
          collapsed: document.querySelector('.app').classList.contains('is-sidebar-collapsed'),
          header: document.querySelector('.header').scrollWidth <= document.querySelector('.header').clientWidth + 1 })""")
        page.click("#sidebar-toggle")
        unfolded = page.evaluate("""() => {
          const outline = document.getElementById('sidebar').getBoundingClientRect();
          const main = document.getElementById('main').getBoundingClientRect();
          return { above: outline.bottom <= main.top + 1, width: outline.width,
                   scroll: document.documentElement.scrollWidth, viewport: innerWidth }; }""")
        browser.close()
    assert problems == [], problems
    # The outline starts folded, the page never scrolls sideways, and the article has a reading width.
    assert folded["collapsed"] and folded["header"], folded
    assert folded["scroll"] <= folded["width"] and folded["paper"] >= 300, folded
    # Unfolded, the outline sits above the article, across the screen.
    assert unfolded["above"] and unfolded["width"] >= 300 and unfolded["scroll"] <= unfolded["viewport"], unfolded


def test_print_keeps_every_table_and_equation_on_the_page(live_server):
    """On paper nothing scrolls: no table or equation may be wider than the A4 text block."""
    with live_server["playwright"].sync_playwright() as p:
        # A4 less the print sheet's 16 mm margins: 178 mm, about 673 CSS px.
        browser, page, problems = _open(p, live_server["base"], viewport=(673, 900))
        page.emulate_media(media="print")
        over = page.evaluate("""() => [...document.querySelectorAll('#paper .table-scroll, #paper .eq-math')]
          .filter((el) => el.scrollWidth > el.clientWidth + 1)
          .map((el) => `${el.closest('[id]')?.id ?? el.className}: ${el.scrollWidth} > ${el.clientWidth}`)""")
        browser.close()
    assert problems == [], problems
    assert over == [], over


def test_a_folded_outline_comes_back_unshifted(live_server):
    """The scroll-spy never scrolls the outline sideways, folded or not."""
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"])
        page.click("#sidebar-toggle")
        page.evaluate("() => document.getElementById('sec-frames').scrollIntoView({ block: 'start' })")
        page.wait_for_function(
            "() => document.querySelector('#toc a[aria-current=\"location\"]')?.dataset.goto?.startsWith('sec-frames')",
            timeout=10_000)
        page.click("#sidebar-toggle")
        left = page.evaluate("() => document.getElementById('sidebar').scrollLeft")
        browser.close()
    assert problems == [], problems
    assert left == 0


#: Every text of an SVG laid out by the browser: those leaving the viewBox, and pairs that overlap.
_TEXT_BOXES = """(svg) => {
  const vb = svg.viewBox.baseVal;
  const boxes = [...svg.querySelectorAll('text')].map((t) => { const b = t.getBBox();
    return { t: t.textContent, x: b.x, y: b.y, w: b.width, h: b.height }; });
  const out = boxes.filter((b) => b.x < 0 || b.y < 0 || b.x + b.w > vb.width || b.y + b.h > vb.height).map((b) => b.t);
  const overlaps = [];
  for (let i = 0; i < boxes.length; i += 1) for (let j = i + 1; j < boxes.length; j += 1) {
    const a = boxes[i]; const b = boxes[j];
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ox > 0.5 && oy > 0.5) overlaps.push([a.t, b.t]);
  }
  return { n: boxes.length, out, overlaps };
}"""


def _png_chunks(png: bytes) -> dict:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    chunks, at = [], 8
    while at < len(png):
        (length,) = struct.unpack(">I", png[at:at + 4])
        kind, data = png[at + 4:at + 8], png[at + 8:at + 8 + length]
        (crc,) = struct.unpack(">I", png[at + 8 + length:at + 12 + length])
        assert crc == zlib.crc32(kind + data), kind
        chunks.append((kind.decode(), data))
        at += 12 + length
    return chunks


def test_export_downloads_the_article_as_one_zip(live_server, tmp_path):
    folder = _screens(tmp_path)
    with live_server["playwright"].sync_playwright() as p:
        browser, page, problems = _open(p, live_server["base"])
        # The article's own figures, as the screen draws them, beside the exported ones.
        for figure in page.locator("#paper figure.article-figure").all():
            figure.screenshot(path=str(folder / f"screen-{figure.get_attribute('id')}.png"))
        button = page.locator("#export-article")
        assert button.text_content() == "Export"
        assert "LaTeX" in button.get_attribute("title") and "zip" in button.get_attribute("title")
        with page.expect_download(timeout=60_000) as caught:
            busy = page.evaluate("""() => { const b = document.getElementById('export-article'); b.click();
              return [b.disabled, b.getAttribute('aria-busy'), b.textContent]; }""")
        download = caught.value
        page.wait_for_function("() => !document.getElementById('export-article').disabled", timeout=30_000)
        after = page.evaluate("""() => { const b = document.getElementById('export-article');
          return [b.disabled, b.getAttribute('aria-busy'), b.textContent, document.getElementById('banner').hidden,
                  location.hash]; }""")
        name = download.suggested_filename
        data = Path(download.path()).read_bytes()
        archive = zipfile.ZipFile(io.BytesIO(data))
        figures = {n: archive.read(n) for n in archive.namelist() if n.startswith("calosrv-methodology/figures/")}
        layout = {}
        for path, svg in figures.items():
            if path.endswith(".svg"):
                page.set_content(f"<body style='margin:0'>{svg.decode('utf-8').split('?>', 1)[1]}</body>")
                layout[path] = page.eval_on_selector("svg", _TEXT_BOXES)
        browser.close()
    assert problems == [], problems
    assert busy == [True, "true", "Exporting…"]
    assert after[:4] == [False, None, "Export", True], after
    assert "at=" not in after[4] and "table_name=experiment_baseline" in after[4]
    assert re.fullmatch(r"calosrv-methodology-\d{4}-\d{2}-\d{2}\.zip", name), name

    assert archive.testzip() is None
    names = archive.namelist()
    assert names[:2] == ["calosrv-methodology/methodology.tex", "calosrv-methodology/references.bib"]
    ids = [n.removeprefix("calosrv-methodology/figures/").removesuffix(".svg") for n in names[2::2]]
    assert sorted(ids) == ["fig-puor", "fig-ramps", "fig-se3"]
    assert names[2:] == [f"calosrv-methodology/figures/{i}.{ext}" for i in ids for ext in ("svg", "png")]
    assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
    tex = archive.read(names[0]).decode("utf-8")
    for fid in ids:
        assert f"figures/{fid}.png" in tex

    for fid in ids:
        svg = figures[f"calosrv-methodology/figures/{fid}.svg"]
        root = ET.fromstring(svg)
        assert root.get("width") == "160mm"
        png = figures[f"calosrv-methodology/figures/{fid}.png"]
        chunks = _png_chunks(png)
        assert [k for k, _ in chunks[:2]] == ["IHDR", "pHYs"]
        width, height = struct.unpack(">II", chunks[0][1][:8])
        assert width == 1890
        assert height == round(float(root.get("height").removesuffix("mm")) / 25.4 * 300)
        assert struct.unpack(">IIB", chunks[1][1]) == (11811, 11811, 1)
        (folder / f"{fid}.svg").write_bytes(svg)
        (folder / f"{fid}.png").write_bytes(png)
        boxes = layout[f"calosrv-methodology/figures/{fid}.svg"]
        assert boxes["n"] > 0 and boxes["out"] == [] and boxes["overlaps"] == [], (fid, boxes)

    if not (shutil.which("pdflatex") and shutil.which("bibtex")):
        return
    build = tmp_path / "latex"
    archive.extractall(build)
    root = build / "calosrv-methodology"
    steps = [["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "methodology"], ["bibtex", "methodology"],
             ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "methodology"],
             ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "methodology"]]
    for step in steps:
        done = subprocess.run(step, cwd=root, capture_output=True, text=True, timeout=180, check=False)
        assert done.returncode == 0, f"{step[0]} failed:\n{done.stdout[-3000:]}"
    assert (root / "methodology.pdf").stat().st_size > 0


def test_the_export_button_stays_in_the_header_at_every_width(live_server, tmp_path):
    """The header does not wrap above the phone layout: the button must fit beside the chip and the badge."""
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        seen = {}
        for width in (1600, 1280, 1100, 900, 780, 600):
            _, page, problems = _open(p, live_server["base"], viewport=(width, 800), browser=browser)
            seen[width] = page.evaluate("""() => { const b = document.getElementById('export-article').getBoundingClientRect();
              const h = document.querySelector('.header');
              return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: innerWidth,
                       header: h.getBoundingClientRect().bottom, over: h.scrollWidth - h.clientWidth }; }""")
            assert problems == [], (width, problems)
            if width in (1100, 900):
                page.screenshot(path=str(_screens(tmp_path) / f"methodology-header-{width}.png"), clip={"x": 0, "y": 0, "width": width, "height": 160})
            page.context.close()
        browser.close()
    for width, box in seen.items():
        assert box["left"] >= 0 and box["right"] <= box["width"], (width, box)
        assert box["bottom"] <= box["header"] and box["over"] <= 0, (width, box)
