"""Source pins of the Methodology page (``/methodology``).

The article is data, so every sentence of it reaches the page as text nodes:
nothing in ``math.js``, ``methodology_main.js`` or ``methodology/`` may parse
a string as markup. The page is served offline (no URL of another host in its
markup), prints (``@media print``), carries the reader's view to its tabs
without its own key, and writes the hash in one place only, for ``at``.

The behaviour is checked by ``test_js_methodology.py`` (Node) and
``test_browser_methodology.py`` (Chromium, opt-in).
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "calosrv" / "static"
JS = STATIC / "js"

#: The modules that build the article.
MODULES = sorted([JS / "math.js", JS / "methodology_main.js", *(JS / "methodology").rglob("*.js")])


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)(^|[^:'\"])//.*$", r"\1", source)


def test_the_article_modules_exist():
    names = {path.relative_to(JS).as_posix() for path in MODULES}
    for name in ("math.js", "methodology_main.js", "methodology/render.js", "methodology/links.js",
                 "methodology/exhibits.js", "methodology/constants.js", "methodology/content/index.js"):
        assert name in names, name


def test_nothing_parses_a_string_as_markup():
    for path in MODULES:
        code = _strip_comments(path.read_text(encoding="utf-8"))
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser",
                          "createContextualFragment"):
            assert forbidden not in code, f"{path.relative_to(JS)} uses {forbidden}"


def test_the_markup_loads_nothing_from_another_host():
    html = (STATIC / "methodology.html").read_text(encoding="utf-8")
    for value in re.findall(r'(?:src|href)="([^"]*)"', html):
        assert not re.match(r"(?i)https?:|//", value), value
    css = (STATIC / "css" / "methodology.css").read_text(encoding="utf-8")
    assert "@import" not in css and "url(http" not in css and "@font-face" not in css


def test_one_module_script_and_the_shell_ids_are_kept():
    html = (STATIC / "methodology.html").read_text(encoding="utf-8")
    assert re.findall(r"<script\b[^>]*>", html) == ['<script type="module" src="/static/js/methodology_main.js">']
    for element_id in ("sidebar", "sidebar-toggle", "toc", "toc-heading", "main", "paper", "banner", "banner-text",
                       "banner-close", "page-tabs", "view-chip", "view-chip-text", "compute-badge", "badge-memory",
                       "badge-threads"):
        assert html.count(f'id="{element_id}"') == 1, element_id


def test_the_page_prints():
    css = (STATIC / "css" / "methodology.css").read_text(encoding="utf-8")
    assert "@media print" in css
    printed = css[css.index("@media print"):]
    for token in ("#FFFFFF", "#111827", ".header", ".sidebar", ".links-row", ".tex-toggle", ".tex-panel", ".banner",
                  "display: block", "overflow: visible", "break-inside: avoid", "break-after: avoid"):
        assert token in printed, token


def test_nothing_is_animated_or_smoothly_scrolled():
    css = _strip_comments((STATIC / "css" / "methodology.css").read_text(encoding="utf-8"))
    for forbidden in ("transition", "animation", "scroll-behavior: smooth"):
        assert forbidden not in css, forbidden
    for path in MODULES:
        assert "behavior: 'smooth'" not in _strip_comments(path.read_text(encoding="utf-8")), path.name


def test_the_tabs_drop_the_page_key():
    main = _strip_comments((JS / "methodology_main.js").read_text(encoding="utf-8"))
    assert "wirePageTabs(document, { drop: ['at'] })" in main


def test_the_only_hash_write_is_at():
    writes = []
    for path in MODULES:
        code = _strip_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"history\.(replaceState|pushState)\(", code):
            writes.append((path.relative_to(JS).as_posix(), match.group(1), code[max(0, match.start() - 300):match.end() + 80]))
        assert "location.hash =" not in code and "location.href =" not in code, path.name
        assert "writeHash(" not in code, path.name
    assert [(name, kind) for name, kind, _ in writes] == [("methodology/links.js", "replaceState")]
    assert "{ at: id }" in writes[0][2]
