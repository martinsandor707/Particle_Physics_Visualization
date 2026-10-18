"""The page shell: the Details drawer, the collapsible sidebar, the two-tier
frame control and the upload form inside Admin Settings - pinned at the source.

The behaviour runs in a browser (``tests/test_browser_layout.py``, opt-in);
what can be checked here is everything the acceptance criteria state as a
property of the markup, the stylesheet or the module text: that the on-card
footnotes are gone, that the drawer and the toggle exist once and sit where
they must, that the grid tracks snap rather than animate, that the energy
panel re-lays itself out from its container, that the drawer renders text
nodes only, and that the upload form lives in the admin panel.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "calosrv" / "static"
JS = STATIC / "js"
PANEL_IDS = ("xy", "yz", "xz", "energy")


def _html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _rule(css: str, selector: str) -> str:
    """The body of the first rule whose selector list is exactly `selector`.

    Anchored at a rule boundary, so `.sidebar` cannot match the tail of
    `.app.is-sidebar-collapsed .sidebar`.
    """
    match = re.search(r"(?:^|\}|\*/)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css, re.MULTILINE)
    assert match, f"no rule for {selector}"
    return match.group(1)


# ------------------------------------------------------------- the drawer --


def test_the_on_card_footnotes_are_gone():
    html = _html()
    assert 'id="foot-' not in html and 'class="footnote"' not in html
    main = (JS / "main.js").read_text(encoding="utf-8")
    assert "'foot-" not in main
    # The on-card notices and the fitted-parameter table stay on the card.
    assert 'id="energy-sparse"' in html and 'id="fit-table"' in html


def test_the_details_drawer_exists_once_outside_main():
    html = _html()
    for element_id in ("inspector", "inspector-title", "inspector-body", "inspector-close"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    aside = html.index('id="inspector"')
    assert html.index("</main>") < aside < html.index('id="admin-modal"')
    assert aside < html.index('id="tooltip-layer"')
    assert re.search(r'<aside class="inspector" id="inspector" aria-labelledby="inspector-title" hidden>', html)
    assert '<h2 id="inspector-title" tabindex="-1">' in html


def test_every_card_has_a_details_trigger_in_its_toolbar():
    html = _html()
    for panel_id in PANEL_IDS:
        assert html.count(f'data-panel="{panel_id}"') == 1, panel_id
        card = re.search(rf'<div class="card" data-panel="{panel_id}">(.*?)(?=<div class="card" |</section>)',
                         html, re.DOTALL)
        assert card, panel_id
        toolbar = re.search(r'<span class="card-actions">(.*?)</span>\s*</h2>', card.group(1), re.DOTALL)
        assert toolbar, panel_id
        first = re.search(r"<button\b[^>]*>", toolbar.group(1))
        assert first and f'data-inspect="{panel_id}"' in first.group(0), f"{panel_id}: Details must lead the toolbar"
        assert 'aria-controls="inspector"' in first.group(0) and 'aria-expanded="false"' in first.group(0)


def test_the_drawer_is_rendered_with_text_nodes_only():
    shell = _strip_comments((JS / "shell.js").read_text(encoding="utf-8"))
    for forbidden in ("innerHTML", "insertAdjacentHTML", "setHtml"):
        assert forbidden not in shell, forbidden
    assert "textContent" in shell and "replaceChildren" in shell
    notes = _strip_comments((JS / "panel_notes.js").read_text(encoding="utf-8"))
    for forbidden in ("getElementById", "querySelector", "textContent", "innerText", "document."):
        assert forbidden not in notes, f"panel_notes.js touches the DOM: {forbidden}"
    for spec, name in (("./frame_views.js", "footnotes"), ("./export/disclosure.js", "figureDisclosure"),
                       ("./export/caption.js", "describeSelection"), ("./export/caption.js", "describeView"),
                       ("./axis_symbols.js", "panelSymbols")):
        assert re.search(rf"import\s*\{{[^}}]*\b{name}\b[^}}]*\}}\s*from\s*'{re.escape(spec)}'", notes), (spec, name)


def test_escape_in_the_drawer_yields_to_open_overlays():
    shell = _strip_comments((JS / "shell.js").read_text(encoding="utf-8"))
    listener = re.search(r"document\.addEventListener\('keydown'.*?\{ capture: true \}\)", shell, re.DOTALL)
    assert listener, "the drawer's Escape listener must run in the capture phase"
    assert ".modal-backdrop:not([hidden])" in listener.group(0)
    assert ".popover" in listener.group(0) and ".menu" in listener.group(0)


# ------------------------------------------------------------ the sidebar --


def test_one_sidebar_toggle_in_the_header():
    html = _html()
    assert html.count('id="sidebar-toggle"') == 1
    header = html[html.index("<header"):html.index("</header>")]
    toggle = re.search(r'<button class="icon-button" id="sidebar-toggle"(.*?)</button>', header, re.DOTALL)
    assert toggle, "the toggle must live in the header"
    assert 'aria-controls="sidebar"' in toggle.group(1)
    assert 'aria-expanded="true"' in toggle.group(1)
    assert "aria-label=" in toggle.group(1) and "<svg" in toggle.group(1)
    assert '<aside class="sidebar" id="sidebar">' in html
    assert html.count('<main class="main">') == 1


def test_the_shell_grid_has_three_tracks_that_snap():
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    app = _rule(css, ".app")
    columns = re.search(r"grid-template-columns:\s*([^;]+);", app).group(1)
    tracks = re.findall(r"var\([^)]*\)|minmax\([^)]*\)|\S+", columns)
    assert len(tracks) == 3 and tracks[1] == "minmax(0, 1fr)", tracks
    assert '"header header header" "sidebar main inspector"' in app
    assert "transition" not in app, "the grid tracks must snap, not animate"
    assert "transition" not in _rule(css, ".sidebar")
    assert "transition" not in _rule(css, ".app.is-sidebar-collapsed .sidebar")
    assert "--sidebar-col: 0px" in _rule(css, ".app.is-sidebar-collapsed")
    assert "--inspector-col" in _rule(css, ".app.is-inspector-open")
    assert "min-width: 0" in _rule(css, ".main")
    # The 2x2 grid follows the chart column's width, so a card never has to
    # hold its toolbar in less room than it needs when the drawer is open.
    assert "container-type: inline-size" in _rule(css, ".main")
    assert re.search(r"@container main \(max-width: \d+px\) \{\s*\.grid \{ grid-template-columns: minmax\(0, 1fr\); \}", css)
    assert "z-index" not in _rule(css, ".inspector")
    assert "auto" in _rule(css, ".inspector").split("overflow", 1)[1]
    breakpoint = re.search(r"@media \(max-width: 1100px\) \{(.*?)\n\}", css, re.DOTALL)
    assert breakpoint, "the 1100px breakpoint is missing"
    assert "--sidebar-width" in breakpoint.group(1)
    assert not re.search(r"\.app\s*\{[^}]*grid-template-columns", breakpoint.group(1))
    assert "prefers-reduced-motion" not in css


def test_the_energy_panel_relayouts_from_its_container():
    energy = _strip_comments((JS / "panels" / "energy.js").read_text(encoding="utf-8"))
    assert "new ResizeObserver(" in energy and "requestAnimationFrame" in energy
    relayout = re.search(r"\n  relayout\(\) \{(.*?)\n  \}\n", energy, re.DOTALL)
    assert relayout, "EnergyPanel.relayout is missing"
    assert "this.laidOut" in relayout.group(1) and "this.chart.resize()" in relayout.group(1)
    assert "this.liveGrid = option.grid" in energy
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    body = re.search(r"function relayoutAll\(\) \{(.*?)\n\}", main, re.DOTALL)
    assert body and "panel.relayout()" in body.group(1) and "energyPanel.relayout()" in body.group(1)
    shell = _strip_comments((JS / "shell.js").read_text(encoding="utf-8"))
    assert "transitionend" not in shell


def test_the_sidebar_preference_lives_in_local_storage_not_the_link():
    shell = _strip_comments((JS / "shell.js").read_text(encoding="utf-8"))
    assert "'calosrv.sidebar'" in shell
    uses = list(re.finditer(r"localStorage", shell))
    assert uses, "shell.js must persist the preference"
    for match in uses:
        assert "try {" in shell[max(0, match.start() - 80):match.start()], "every storage access is guarded"
    # The stored view (state.js) never carries layout: no storage, no sidebar key.
    state = _strip_comments((JS / "state.js").read_text(encoding="utf-8"))
    assert "localStorage" not in state and "sidebar" not in state


# ----------------------------------------------------- the frame control --


def test_the_frame_control_carries_both_tiers_and_the_hidden_legacy_option():
    html = _html()
    assert html.count('name="frame-view"') == 2 and html.count('name="frame-sub"') == 3
    assert 'id="ctl-frame"' in html and 'id="frame-sub"' in html and 'id="frame-sub-trans"' in html
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "setHidden('frame-sub-trans', frame !== 'trans')" in main
    assert "enteringSub(offeredFrames)" in main
    assert 'input[name="frame"]' not in main


# ------------------------------------------------------- upload in admin --


def test_the_upload_form_lives_inside_the_admin_panel():
    html = _html()
    assert 'id="open-upload"' not in html and 'id="upload-modal"' not in html
    assert "Upload Dataset" not in html
    assert html.count('class="modal-backdrop"') == 1
    start = html.index('id="admin-modal"')
    end = html.index('id="tooltip-layer"')
    for element_id in ("upload-table", "upload-display", "upload-replace", "upload-offset", "upload-file",
                       "upload-file-info", "upload-server-file", "upload-server-info", "upload-status",
                       "upload-progress-bar", "upload-warning", "upload-clear", "upload-submit"):
        where = html.index(f'id="{element_id}"')
        assert start < where < end, element_id
    assert html.index('<section class="admin-upload"') < html.index('<section class="admin-ingest"')
    upload = _strip_comments((JS / "controls" / "upload.js").read_text(encoding="utf-8"))
    assert "export class UploadForm" in upload and "prepare()" in upload
    for forbidden in ("ModalShell", "open-upload", "upload-cancel"):
        assert forbidden not in upload, forbidden
    admin = _strip_comments((JS / "controls" / "admin.js").read_text(encoding="utf-8"))
    assert "this.upload?.prepare()" in admin
    main = (JS / "main.js").read_text(encoding="utf-8")
    assert "Upload Dataset" not in main and "Open Admin Settings" in main
