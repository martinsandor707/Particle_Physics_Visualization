"""The page shell: the Details drawer, the collapsible sidebar, the two-tier
frame control and the upload form inside Admin Settings - pinned at the source.

The behaviour runs in a browser (``tests/test_browser_layout.py``, opt-in);
what can be checked here is everything the acceptance criteria state as a
property of the markup, the stylesheet or the module text: that the on-card
footnotes are gone, that the drawer and the toggle exist once and sit where
they must, that the grid tracks snap rather than animate, that the energy
panel re-lays itself out from its container, that the drawer renders text
nodes only, and that the upload form lives in the admin panel.

The particle filter (2026-11-15): the `#group-particle` block, identical on
both pages and hidden until a page adopts it, in its place in each sidebar
and outside every other group; Most tilted and Open in 3-D on the Physics
page; models.css keeping the block to Views; both entries mounting it and
aborting its request on a switch; the Event Inspector keeping its pick route
and taking its sentences from `event_picker.js`; text nodes only.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
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


# ------------------------------------------------------- the frame grids --


def test_the_frame_grids_sit_in_main_after_the_ensemble_grid():
    html = _html()
    assert html.count('id="ensemble-grid"') == 1
    assert '<section class="grid" id="ensemble-grid">' in html
    for section in ("compare-grid", "event-grid"):
        assert html.count(f'id="{section}"') == 1, section
        assert f'<section class="frame-grid" id="{section}" hidden aria-labelledby="{section}-title">' in html
        assert html.index('id="ensemble-grid"') < html.index(f'id="{section}"') < html.index("</main>")
        # The Event viewer has no button back to the ensemble: the tab is the way back (brief 9.1).
        for part in ("title", "label", "rows") + (("close",) if section == "compare-grid" else ()):
            assert html.count(f'id="{section}-{part}"') == 1, f"{section}-{part}"
    assert html.count('id="event-grid-close"') == 0
    assert html.index('id="compare-grid"') < html.index('id="event-grid"')
    # Each grid sits in its subpage's wrapper: the compare grid with the ensemble, the event grid in the viewer.
    assert 'id="compare-grid"' in _div_span(html, '<div class="physics-subpage" id="psub-selection"')
    assert 'id="event-grid"' not in _div_span(html, '<div class="physics-subpage" id="psub-selection"')
    assert 'id="event-grid"' in _div_span(html, '<div class="physics-subpage" id="psub-event"')


def test_the_event_picker_and_the_compare_toggle_live_in_the_sidebar():
    html = _html()
    sidebar = html[html.index('<aside class="sidebar"'):html.index("</aside>")]
    for element_id in ("event-number", "event-prev", "event-next", "event-pick",
                       "event-status", "event-caption", "info-event", "opt-compare", "ctl-event"):
        assert sidebar.count(f'id="{element_id}"') == 1, element_id
    assert sidebar.count('name="event-shower"') == 2
    # The Back-to-the-ensemble buttons are gone: the Entire selection tab is the way back.
    assert 'id="event-close"' not in html
    assert html.count("Back to the ensemble") == 1 and 'id="compare-grid-close"' in html  # the compare grid keeps its own
    assert 'type="number" id="event-number" min="0" step="1"' in sidebar
    # The toggle belongs to the reference-frame block, after its caption.
    assert sidebar.index('id="frame-caption"') < sidebar.index('id="opt-compare"') < sidebar.index('id="ctl-event"')


def test_the_frame_grid_cells_are_three_across_and_snap():
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    cells = re.search(r"\.frame-grid-cells \{\s*display: grid;\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);"
                      r"\s*gap: var\(--gap\);\s*\}", css)
    assert cells, "the grid cells rule is missing"
    assert re.search(r"@container main \(max-width: \d+px\) \{\s*\.frame-grid-cells \{ grid-template-columns: minmax\(0, 1fr\); \}", css)
    breakpoint = re.search(r"@media \(max-width: 1100px\) \{(.*?)\n\}", css, re.DOTALL)
    assert ".frame-grid-cells { grid-template-columns: minmax(0, 1fr); }" in breakpoint.group(1)
    assert ".frame-grid[hidden] { display: none; }" in css
    assert ".frame-grid-row[hidden] { display: none; }" in css
    section = css[css.index("3 x 3 frame grids"):css.index("details drawer")]
    assert "transition" not in _strip_comments(section), "the frame grids snap, like every other track"


def test_the_frame_grid_builds_cards_the_shell_and_the_export_menu_recognise():
    grid = _strip_comments((JS / "panels" / "frame_grid.js").read_text(encoding="utf-8"))
    for token in ("card.dataset.panel = id", "details.dataset.inspect = id", "exporter.dataset.export = id",
                  "details.setAttribute('aria-controls', 'inspector')",
                  "new ProjectionPanel(`plot-${id}`, { isometric: true })",
                  "export const GRID_ROWS = ['lab', 'trans', 'local'];",
                  "export const GRID_COLS = ['xy', 'xz', 'yz'];"):
        assert token in grid, token
    assert "innerHTML" not in grid
    assert "plot area only" in (JS / "panels" / "frame_grid.js").read_text(encoding="utf-8")
    # The charts are created when the grid is first shown, never into a hidden section.
    assert re.search(r"show\(visible\) \{.*?this\.ensurePanels\(\);", grid, re.DOTALL)
    shell = _strip_comments((JS / "shell.js").read_text(encoding="utf-8"))
    assert "closest('[data-inspect]')" in shell and "'.card[data-panel] > h2'" in shell
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "eventGrid.relayout()" in main and "compareGrid.relayout()" in main
    assert "function applyViewMode()" in main and "setHidden('ensemble-grid'" in main
    inspector = _strip_comments((JS / "event_inspector.js").read_text(encoding="utf-8"))
    assert "'/api/event'" in inspector and "'/api/event/pick'" in inspector
    assert "innerHTML" not in inspector


# ------------------------------------------------- the entry-anchor explainer --


def test_the_entry_anchor_has_an_explainer_button_inside_its_control():
    html = _html()
    assert html.count('id="info-anchor"') == 1
    sub = re.search(r'<fieldset class="choice-sub" id="anchor-sub"(.*?)</fieldset>', html, re.DOTALL)
    assert sub, "the anchor control is missing"
    button = re.search(r'<button class="info-dot is-neutral" id="info-anchor"([^>]*)>i</button>', sub.group(1))
    assert button, "the i button lives inside the anchor control, beside its heading"
    for token in ('type="button"', 'aria-haspopup="dialog"', 'aria-expanded="false"',
                  'aria-label="How the two entry anchors are computed"'):
        assert token in button.group(1), token
    assert sub.group(1).index('id="info-anchor"') < sub.group(1).index('name="anchor"')

    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    body = re.search(r"function showExplainer\(trigger, explainer\) \{(.*?)\n\}", main, re.DOTALL)
    assert body, "showExplainer is missing"
    assert "textContent" in body.group(1) and "innerHTML" not in body.group(1), "text nodes only"
    assert "stopPropagation" in body.group(1) and ".focus(" in body.group(1)
    assert "anchorExplainer(frame, state.get('anchor'))" in main
    assert "anchor: document.getElementById('info-anchor')" in main
    css = (STATIC / "css" / "controls.css").read_text(encoding="utf-8")
    rule = _rule(css, ".popover.is-explainer")
    assert "max-height: calc(100vh - 16px)" in rule and "overflow-y: auto" in rule


# ------------------------------------------------------ the physics section --


def test_the_physics_section_sits_below_the_ensemble_grid():
    html = _html()
    assert html.count('<section class="grid physics-grid" id="physics-grid"') == 1
    assert html.count('id="kind-notice"') == 1
    order = [html.index(f'id="{section}"') for section in ("psub-selection", "ensemble-grid", "kind-notice",
                                                            "physics-grid", "compare-grid", "psub-event",
                                                            "event-empty", "event-grid")]
    assert order == sorted(order)
    assert html.index('id="physics-grid"') < html.index("</main>")
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    assert ".grid[hidden] { display: none; }" in css
    # Right after the .grid rule, outside the pinned @container and @media blocks.
    assert css.index(".grid[hidden]") < css.index("@container main (max-width: 820px)")
    for rule in (".card[hidden] { display: none; }", ".kind-notice[hidden] { display: none; }",
                 ".card-error[hidden] { display: none; }"):
        assert rule in css, rule


def test_the_physics_section_snaps_like_every_other_track():
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    section = css[css.index("physics section"):]
    assert "transition" not in _strip_comments(section)
    controls = (STATIC / "css" / "controls.css").read_text(encoding="utf-8")
    tail = controls[controls.index("physics card controls"):]
    assert "transition" not in _strip_comments(tail)
    assert ".seg[hidden] { display: none; }" in controls
    assert "prefers-reduced-motion" not in css + controls


def test_main_hides_the_physics_cards_with_the_ensemble_grid_and_lays_them_out():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    view = re.search(r"function applyViewMode\(\) \{(.*?)\n\}", main, re.DOTALL)
    assert view, "applyViewMode is missing"
    for token in ("setHidden('ensemble-grid'", "setHidden('physics-grid'", "setHidden('kind-notice'"):
        assert token in view.group(1), token
    # The router (physics-subpages §10.1): only the compare view hides the 2 x 2 and the cards, never a
    # pinned event, which lives on the Event viewer; each grid is shown only on its subpage on show.
    for token in ("setHidden('ensemble-grid', compare || !pagePlan.spatial);",
                  "setHidden('kind-notice', compare || pagePlan.spatial);",
                  "setHidden('physics-grid', compare || !pagePlan.physics.length);",
                  "compareGrid.show(compare && psub === 'selection');",
                  "eventGrid.show(pinned && psub === 'event');"):
        assert token in view.group(1), token
    relayout = re.search(r"function relayoutAll\(\) \{(.*?)\n\}", main, re.DOTALL)
    assert "physics.relayout()" in relayout.group(1)
    # The cards exist before the export menus are wired, so their Export buttons are.
    assert main.index("new PhysicsSection(") < main.index("attachExportMenus({")
    # The capability plan decides; a single shower's translated frame is shown.
    assert "page1Plan(experiment)" in main
    assert "if (pagePlan.frames.transPrimary) setHidden('frame-sub-trans', false);" in main
    assert main.index("setHidden('frame-sub-trans', frame !== 'trans')") < main.index("pagePlan.frames.transPrimary")


def test_the_physics_cards_have_the_page_card_anatomy():
    source = (JS / "physics_section.js").read_text(encoding="utf-8")
    code = _strip_comments(source)
    for token in ("card.dataset.panel = id", "details.dataset.inspect = id", "exporter.dataset.export = id",
                  "details.setAttribute('aria-controls', 'inspector')"):
        assert token in code, token
    assert "plot area only" in source
    for forbidden in ("innerHTML", "insertAdjacentHTML", "dataset.shower", "dataset.roi", "dataset.reset"):
        assert forbidden not in code, forbidden
    lazy = _strip_comments((JS / "lazy_cards.js").read_text(encoding="utf-8"))
    assert "new IntersectionObserver(" in lazy
    # rootMargin '0px' is the plan's decision D3 (Martin): no card is asked for
    # before it is in view, not the design's '200px 0px' prefetch margin.
    assert "rootMargin = '0px'" in lazy


def test_the_filter_block_and_the_kind_markup_carry_their_ids():
    html = _html()
    sidebar = html[html.index('<aside class="sidebar"'):html.index("</aside>")]
    for element_id in ("e1-label", "e1-hint", "filter-logic", "ctl-undefined-d", "ctl-e1", "ctl-e2", "ctl-d"):
        assert sidebar.count(f'id="{element_id}"') == 1, element_id
    for element_id in ("stat-d-item", "stat-nod-item", "stat-wneg-item", "stat-wneg", "energy-shower-toggle",
                       "energy-b3-slices", "plot-energy-b3", "kind-banner", "kind-notice-title",
                       "kind-notice-text"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    assert '<span id="stat-wneg-item" data-psub-only="selection" hidden' in html
    # The upload hint is schema-neutral: it names every accepted schema.
    upload = html[html.index('<section class="admin-upload"'):html.index('<section class="admin-ingest"')]
    for schema in ("hits_all_models", "standalone_hits", "standalone_events"):
        assert schema in upload, schema
    # The Source files section sits after the automatic ingest and before the rebuild section, which
    # stays in the admin panel, ahead of the tooltip layer.
    assert html.index('<section class="admin-ingest"') < html.index('<section class="admin-sources"') \
        < html.index('<section class="admin-rebuild"') < html.index('id="tooltip-layer"')
    admin = _strip_comments((JS / "controls" / "admin.js").read_text(encoding="utf-8"))
    assert "/api/admin/experiments/${encodeURIComponent(name)}/rebuild" in admin
    assert "innerHTML" not in admin


def test_the_admin_panel_lists_each_experiment_against_its_source_file():
    """Source files: the section's markup, in its place, and the routes `admin.js` calls for it."""
    html = _html()
    start, end = html.index('id="admin-modal"'), html.index('id="tooltip-layer"')
    order = ["admin-upload", "admin-ingest", "admin-sources", "admin-rebuild"]
    places = [html.index(f'<section class="{name}"') for name in order]
    assert places == sorted(places) and start < places[0] and places[-1] < end
    section = html[places[2]:html.index("</section>", places[2])]
    assert 'aria-labelledby="admin-sources-title"' in section
    for element_id in ("admin-sources-title", "admin-sources-refresh", "admin-sources-where",
                       "admin-sources-table", "admin-sources-rows"):
        assert html.count(f'id="{element_id}"') == 1, element_id
        assert f'id="{element_id}"' in section, element_id
    assert "Check again" in section and "Source files" in section
    raw = (JS / "controls" / "admin.js").read_text(encoding="utf-8")
    admin = _strip_comments(raw)
    # The one read, and the one write: the route template carries the encoded name.
    assert "'/api/admin/experiments'" in admin
    assert "/api/admin/experiments/${encodeURIComponent(name)}/reingest" in admin
    assert "'admin-sources'" in admin
    for element_id in ("admin-sources-where", "admin-sources-table", "admin-sources-rows",
                       "admin-sources-refresh"):
        assert f"getElementById('{element_id}')" in admin, element_id
    # Rows are built with the DOM's own text nodes, never parsed from a string.
    assert "innerHTML" not in admin and "insertAdjacentHTML" not in admin
    # The drop-folder sentence names the folder the compose file mounts now.
    assert "/app/host" not in raw
    assert "file uses /app/ingest, which is ./ingest on the host" in raw


def _function_body(source: str, name: str) -> str:
    """The body of a top-level `function name(` or `async function name(` in a module."""
    match = re.search(rf"(?:async )?function {name}\(.*?\) \{{(.*?)\n\}}", source, re.DOTALL)
    assert match, f"{name} is missing"
    return match.group(1)


def test_every_loader_drops_a_response_that_lands_after_an_experiment_switch():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    # Each loader takes the generation before its request and checks it after:
    # getJson lets go of a request once its headers are in, so an abort cannot
    # stop its body landing on the next experiment's views.
    for loader in ("loadProjections", "loadEnergy", "loadPlot4Grid", "loadPerformance", "loadCompare",
                   "loadWindowAxis", "loadEventCount"):
        body = _function_body(main, loader)
        assert "const generation = viewGeneration;" in body, loader
        assert "checkCurrent(generation);" in body, loader
        assert body.index("const generation = viewGeneration;") < body.index("checkCurrent(generation);"), loader
    clear = _function_body(main, "clearExperimentViews")
    for token in ("viewGeneration += 1", "abortRequest(key)", "SPATIAL_ABORT_KEYS", "requestPreview.cancel()",
                  "physics.reset()", "panel.clear()", "energyPanel.clear()", "plot4Grid?.clear()"):
        assert token in clear, token
    keys = re.search(r"const SPATIAL_ABORT_KEYS = \[(.*?)\];", main, re.DOTALL).group(1)
    for key in ("'projections'", "'energy'", "'performance'", "'compare-lab'", "'compare-trans'", "'compare-local'",
                "'window-axis-yz'", "'window-axis-xz'", "'event'", "'event-pick'", "'event-candidates'"):
        assert key in keys, key
    # The workaround for panels without clear() is gone.
    assert "clearPanel" not in main


def test_only_the_latest_refresh_clears_the_busy_state_and_speaks():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    refresh = re.search(r"const refreshAll = debounce\(async \(\) => \{(.*?)\n\}, DEBOUNCE_MS\);", main, re.DOTALL)
    assert refresh, "refreshAll is missing"
    body = refresh.group(1)
    assert "const token = ++refreshToken;" in body
    assert "if (token !== refreshToken) return;" in body
    assert "if (token === refreshToken) setBusy(false);" in body
    # The event-level kind's Events count comes from /api/response's n_events.
    assert "loadEventCount()" in body
    assert "physics.payloadOf('response-b1')" in _function_body(main, "loadEventCount")


def test_the_frame_carries_across_a_switch_of_kind_with_a_notice_in_the_kind_banner():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    activate = _function_body(main, "activateExperiment")
    assert "carriedFrame(previousPlan, pagePlan, state.get('frame'))" in activate
    assert activate.index("clearExperimentViews()") < activate.index("carriedFrame(")
    assert "applyKindPlan(pagePlan, notices)" in activate
    kind = _function_body(main, "applyKindPlan")
    assert "kindBanner.show([plan.banner, plan.stale?.notice, ...notices].filter(Boolean))" in kind
    # The fallback notices live in the kind banner, never the transient one a refresh rewrites.
    assert "showBanner(fallbacks)" not in main


def _div_span(html: str, start_tag: str) -> str:
    """The markup of the `<div>` that opens with `start_tag`, up to its matching close."""
    start = html.index(start_tag)
    depth = 0
    for match in re.finditer(r"<div\b|</div>", html[start:]):
        depth += 1 if match.group(0) == "<div" else -1
        if depth == 0:
            return html[start:start + match.end()]
    raise AssertionError(f"{start_tag} is never closed")


def test_the_event_level_kind_hides_the_spatial_sidebar_groups():
    html = _html()
    sidebar = html[html.index('<aside class="sidebar"'):html.index("</aside>")]
    groups = {
        "group-frame": ('Reference Frame', 'id="ctl-frame"', 'id="frame-caption"', 'id="opt-compare"'),
        "group-resolution": ('Spatial Resolution', 'name="display"', 'id="resolution"', 'id="display-caption"'),
        "group-channel": ('Display Channel', 'name="channel"', 'id="channel-caption"'),
        "group-colormap": ('Colour Map', 'id="colormap"', 'id="opt-lock-scale"', 'id="ctl-rho-norm"'),
    }
    spans = {group: _div_span(sidebar, f'<div class="sidebar-group" id="{group}">') for group in groups}
    for group, members in groups.items():
        for member in members:
            assert member in spans[group], (group, member)
    # The filters, the event picker and the model controls stay outside these four spatial groups: they have
    # wrappers of their own (group-filters, group-event, group-model), which the event-level kind never hides.
    for kept in ('id="ctl-e1"', 'id="ctl-event"', 'name="model"', 'id="metrics"', 'id="opt-undefined-d"'):
        assert kept in sidebar and not any(kept in span for span in spans.values()), kept
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "for (const id of SPATIAL_GROUPS) setHidden(id, !plan.spatial);" in _function_body(main, "applyKindPlan")
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    assert ".sidebar-group[hidden] { display: none; }" in css
    # A group's own first heading keeps its gap: only the sidebar's first heading loses it.
    assert ".sidebar > h2:first-child { margin-top: 0; }" in css and ".sidebar h2:first-child" not in css


def test_single_shower_plot_4_is_the_notebook_windows_with_a_link_to_the_1_gev_bins():
    html = _html()
    energy = html[html.index('data-panel="energy"'):html.index('id="kind-notice"')]
    assert 'id="energy-b3-link"' in energy and "data-b3-slices" not in energy
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "const PLOT4_CONTROLS = Object.freeze({ b3Slices: 'notebook' });" in main
    assert "plot4Slices" not in main and "[data-b3-slices]" not in main
    assert "physics.reveal('response-b3', { b3Slices: 'bins' })" in main
    render = _function_body(main, "renderPlot4")
    # The fit table and the key counts under the grid, as the energy panel has them.
    assert "plot4Grid.renderTable(table)" in render and "writeSparseNote(dom.energySparse, plot4Sparse())" in render
    kind = _function_body(main, "applyKindPlan")
    assert "setHidden('fit-table', !plan.plot4);" in kind



# ------------------------------------------------------- the Models page --


def _models_html() -> str:
    return (STATIC / "models.html").read_text(encoding="utf-8")


def _sidebar_filters(html: str) -> str:
    start = html.index("<h2>Filtering Parameters</h2>")
    end = html.index("Include events with undefined D", start)
    return html[start:html.index("</label>", end)]


def test_the_models_page_has_the_physics_pages_shell():
    html = _models_html()
    for element_id in ("sidebar", "sidebar-toggle", "inspector", "inspector-title", "inspector-body",
                       "inspector-close", "banner", "banner-text", "banner-close", "tooltip-layer",
                       "experiment-select", "badge-memory", "badge-threads", "page-tabs"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    assert '<aside class="sidebar" id="sidebar">' in html and html.count('<main class="main">') == 1
    # The drawer is the Physics page's, outside main; the tooltip layer is outside
    # .main's overflow box and exists before any chart is created.
    assert re.search(r'<aside class="inspector" id="inspector" aria-labelledby="inspector-title" hidden>', html)
    assert html.index("</main>") < html.index('id="inspector"') < html.index('id="tooltip-layer"')
    assert html.index('id="tooltip-layer"') < html.index("<script", html.index("<body"))
    # Admin Settings live on the Physics page: a link, no modal and no upload form.
    assert 'id="admin-modal"' not in html and 'id="upload-' not in html
    # The one modal it carries is the Longitudinal Channels editor, not Admin.
    assert html.count('class="modal-backdrop lg-backdrop" id="lgroups-modal"') == 1
    assert len(re.findall(r'<div class="modal-backdrop', html)) == 1
    assert re.search(r'<a class="action" href="/\?admin=1" data-page-tab', html)
    # The same toggle as the Physics page's.
    header = html[html.index("<header"):html.index("</header>")]
    toggle = re.search(r'<button class="icon-button" id="sidebar-toggle"(.*?)</button>', header, re.DOTALL)
    assert toggle and 'aria-controls="sidebar"' in toggle.group(1) and "<svg" in toggle.group(1)


def test_the_filter_block_is_the_physics_pages_byte_for_byte():
    assert _sidebar_filters(_models_html()) == _sidebar_filters(_html())


def test_the_models_page_loads_echarts_gl_and_its_own_entry_in_order():
    html = _models_html()
    scripts = re.findall(r'<script([^>]*)src="([^"]+)"', html)
    assert [src for _, src in scripts] == ["/static/js/theme_boot.js", "/static/js/vendor/echarts.min.js",
                                           "/static/js/vendor/echarts-gl.min.js", "/static/js/models_main.js"]
    assert 'type="module"' not in scripts[0][0], "the boot script is classic"
    assert 'type="module"' not in scripts[2][0], "echarts-gl is a classic script"
    assert 'type="module"' in scripts[3][0]
    assert "echarts-gl" not in _html()
    assert html.index("css/controls.css") < html.index("css/models.css")


#: The Models page's subpages, in tab order, and their sections in page order.
_SUBPAGES = {
    "views": ["voxels-grid", "features-grid", "primaries-grid"],
    "distill": ["distill-grid", "xgb-distill-grid"],
    "perf": ["perf-grid", "resolution-grid", "xgb-grid", "bench-grid"],
}


def _subpage_block(main: str, msub: str) -> str:
    start = main.index(f'<div class="models-subpage" id="msub-{msub}"')
    ends = [main.index(f'<div class="models-subpage" id="msub-{other}"') for other in _SUBPAGES
            if main.index(f'<div class="models-subpage" id="msub-{other}"') > start]
    return main[start:min(ends) if ends else len(main)]


def _models_head(main: str) -> str:
    """The sticky head's markup: from its opening tag to its matching close."""
    start = main.index('<div class="models-head" id="models-head">')
    depth, at = 0, start
    for match in re.finditer(r"<(/?)div\b", main[start:]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            at = start + match.end()
            break
    return main[start:at]


def test_the_models_page_banners_status_and_sections_are_in_order():
    html = _models_html()
    main = html[html.index('<main class="main">'):html.index("</main>")]
    # The sticky head first (the tab bar, then the catalogue's bar), then the banners and the status bar,
    # before every subpage.
    order = ['<div class="models-head" id="models-head">', 'id="models-subnav"', 'id="bench-bar"', 'id="banner"',
             'id="xgb-notice"', 'id="networks-notice"', 'id="kind-banner"', 'class="statusbar"', 'id="msub-views"',
             'id="msub-distill"', 'id="msub-perf"']
    positions = [main.index(token) for token in order]
    assert positions == sorted(positions)
    first = re.sub(r"<!--.*?-->", "", main, flags=re.DOTALL)[len('<main class="main">'):].lstrip()
    assert first.startswith('<div class="models-head" id="models-head">'), "the head is .main's first child"
    head = _models_head(main)
    assert 'id="models-subnav"' in head and 'id="bench-bar"' in head
    for outside in ('id="banner"', 'id="xgb-notice"', 'id="networks-notice"', 'id="kind-banner"', 'class="statusbar"'):
        assert outside not in head, outside
    assert '<div class="banner is-info" id="xgb-notice"' in main
    assert '<div class="banner" id="networks-notice" role="status" hidden>' in main
    assert 'id="networks-notice-text"' in main and 'id="xgb-notice-text"' in main
    status = main[main.index('class="statusbar"'):main.index("</div>", main.index('class="statusbar"'))]
    for token in ('id="stat-events"', 'id="stat-kind"', 'class="spacer"', 'id="stat-latency"'):
        assert token in status, token
    # Each section in its subpage, in that subpage's order.
    for msub, sections in _SUBPAGES.items():
        block = _subpage_block(main, msub)
        positions = [block.index(f'id="{section}"') for section in sections]
        assert positions == sorted(positions), msub
        others = [s for m, ss in _SUBPAGES.items() if m != msub for s in ss]
        assert not any(f'id="{section}"' in block for section in others), msub
    for section in ("perf-grid", "resolution-grid", "xgb-grid", "xgb-distill-grid", "distill-grid", "bench-grid",
                    "features-grid", "primaries-grid"):
        assert f'<section class="grid models-grid" id="{section}" hidden' in main, section
        assert f'aria-labelledby="{section}-title"' in main and f'id="{section}-title"' in main, section
    # The 3-D host is empty: VoxelSection builds its own cards.
    assert re.search(r'<section class="voxels-grid" id="voxels-grid" hidden aria-label="3-D views"></section>', main)
    # A 3-D pair the selected frame does not draw is hidden (voxel_views.js syncPairs); `display: grid` would
    # otherwise beat the user agent's [hidden] rule and leave it on screen, empty.
    css = (STATIC / "css" / "models.css").read_text(encoding="utf-8")
    assert ".voxel-pair[hidden] { display: none; }" in css
    assert ".voxels-frame-note[hidden] { display: none; }" in css


def test_the_models_subpages_are_a_tablist_of_three_tabpanels():
    html = _models_html()
    main = html[html.index('<main class="main">'):html.index("</main>")]
    nav = re.search(r'<nav class="models-subnav" id="models-subnav" role="tablist" aria-label="Models page views">'
                    r'(.*?)</nav>', main, re.DOTALL)
    assert nav
    tabs = re.findall(r"<button ([^>]*)>([^<]+)</button>", nav.group(1))
    assert [label for _, label in tabs] == ["Views", "Distillations", "Performance"]
    titles = {"views": "The 3-D views, the event-feature explorer and the primaries",
              "distill": "Symbolic formulas, surrogate trees and feature importance",
              "perf": "Network and XGBoost accuracy, resolution scaling and the benchmark catalogue"}
    for (attrs, _), msub in zip(tabs, _SUBPAGES):
        attrs = " ".join(attrs.split())
        assert 'class="models-subtab"' in attrs and 'role="tab"' in attrs and 'type="button"' in attrs
        assert f'id="msub-tab-{msub}"' in attrs and f'data-msub="{msub}"' in attrs
        assert f'aria-controls="msub-{msub}"' in attrs and f'title="{titles[msub]}"' in attrs
        # Views is the cold-boot subpage: the one tab in the tab order (roving tabindex).
        selected = msub == "views"
        assert f'aria-selected="{"true" if selected else "false"}"' in attrs, msub
        assert f'tabindex="{"0" if selected else "-1"}"' in attrs, msub
    for msub in _SUBPAGES:
        hidden = "" if msub == "views" else " hidden"
        assert (f'<div class="models-subpage" id="msub-{msub}" role="tabpanel" aria-labelledby="msub-tab-{msub}" '
                f'data-msub="{msub}"{hidden}>') in main, msub
        assert main.count(f'id="msub-{msub}"') == 1 and main.count(f'id="msub-tab-{msub}"') == 1


def test_the_bench_bar_holds_its_two_groups_and_its_caption_follows_the_head():
    """The sticky head holds the controls alone; the provenance caption follows it and scrolls away."""
    html = _models_html()
    main = html[html.index('<main class="main">'):html.index("</main>")]
    head = _models_head(main)
    bar = head[head.index('<div class="bench-bar" id="bench-bar" hidden>'):]
    assert '<span class="bench-group" id="bench-species" role="group" aria-label="Species">' in bar
    assert '<span class="bench-group" id="bench-task" role="group" aria-label="Task">' in bar
    assert 'id="bench-caption"' not in head
    after = main[main.index(head) + len(head):]
    assert after.index('<p class="bench-caption" id="bench-caption" hidden></p>') < after.index('id="banner"')
    for element_id in ("bench-bar", "bench-species", "bench-task", "bench-caption"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    colour = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    nav = main[main.index('id="models-subnav"'):main.index("</nav>")]
    for part in (head, bar, nav):
        assert not colour.search(part) and "style=" not in part
    # The catalogue's notes say the selection does not apply, as E4/E5's does.
    for section in ("distill-grid", "xgb-distill-grid", "bench-grid"):
        head = main[main.index(f'id="{section}"'):main.index("</section>", main.index(f'id="{section}"'))]
        assert "the selection does not apply" in head.lower() or "selection and the experiment do not apply" in head


def test_the_catalogue_stylesheet_follows_the_models_one():
    html = _models_html()
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)
    assert links == ["/static/css/tokens.css", "/static/css/layout.css", "/static/css/controls.css",
                     "/static/css/models.css", "/static/css/catalog.css"]


def test_the_subpage_styles_are_tokens_only_and_still():
    css = _strip_comments((STATIC / "css" / "models.css").read_text(encoding="utf-8"))
    section = css[css.index(".models-subnav {"):css.index(".models-grid {")]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", section)
    assert "transition" not in section and "animation" not in section
    assert ".models-subpage[hidden] { display: none; }" in section and ".bench-bar[hidden] { display: none; }" in section
    assert ".models-subtab:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }" in section
    assert '.models-subtab[aria-selected="true"]' in section
    # The Longitudinal Channels leave the sidebar off Views by CSS, never through their hidden attribute.
    assert ('.app[data-msub="distill"] #group-lgroups,\n.app[data-msub="perf"] #group-lgroups { display: none; }'
            in section)


def _css_block(css: str, selector: str) -> dict:
    """One rule's declarations, as a dict."""
    body = css[css.index(selector + " {") + len(selector) + 2:]
    body = body[:body.index("}")]
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in body.split(";") if d.strip())}


def test_the_models_head_is_sticky_measured_and_still():
    """Decision 6: one sticky block, the tab bar and the bench bar, over the canvas, under every overlay."""
    css = _strip_comments((STATIC / "css" / "models.css").read_text(encoding="utf-8"))
    head = _css_block(css, ".models-head")
    assert head["position"] == "sticky" and head["background"] == "var(--canvas)"
    assert head["border-bottom"] == "1px solid var(--border)"
    # Above the cards' own stacking, under the modal backdrop (100), the tooltip layer (150) and the menus (200).
    layout = _strip_comments((STATIC / "css" / "layout.css").read_text(encoding="utf-8"))
    controls = _strip_comments((STATIC / "css" / "controls.css").read_text(encoding="utf-8"))
    z = int(head["z-index"])
    assert 2 < z < 100
    assert _css_block(layout, ".tooltip-layer")["z-index"] == "150" and _css_block(layout, ".modal-backdrop")["z-index"] == "100"
    assert _css_block(controls, ".menu")["z-index"] == "200" and _css_block(controls, ".popover")["z-index"] == "200"
    # It cancels .main's padding with its own, so it is flush with the scrollport and covers the gutters.
    vertical, horizontal = _css_block(layout, ".main")["padding"].split()[:2]
    assert head["margin"] == f"-{vertical} -{horizontal} var(--gap)"
    assert head["padding"].split()[:2] == [vertical, horizontal]
    # A sticky offset counts from the scroll container's padding edge: -14px is flush with the scrollport's top.
    assert head["top"] == f"-{vertical}"
    # Every card keeps the head's measured height as its scroll margin.
    assert ".main .card { scroll-margin-top: var(--models-head-h, 0px); }" in css
    section = css[css.index(".models-head {"):css.index(".models-grid {")]
    assert "transition" not in section and "animation" not in section
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", section)
    # The tab bar keeps no margin of its own: the head spaces the page.
    assert "margin" not in _css_block(css, ".models-subnav")


def _methodology_html() -> str:
    return (STATIC / "methodology.html").read_text(encoding="utf-8")


def test_every_page_carries_the_page_tabs_with_the_current_one_marked():
    routes = {"physics": "/", "models": "/models", "methodology": "/methodology"}
    labels = (JS / "labels.js").read_text(encoding="utf-8")
    for html, current in ((_html(), "physics"), (_models_html(), "models"), (_methodology_html(), "methodology")):
        header = html[html.index("<header"):html.index("</header>")]
        nav = re.search(r'<nav class="page-tabs" id="page-tabs" aria-label="Dashboard pages">(.*?)</nav>',
                        header, re.DOTALL)
        assert nav, current
        tabs = re.findall(r"<a ([^>]*)>([^<]+)</a>", nav.group(1))
        assert [label for _, label in tabs] == ["Physics", "Models", "Methodology"]
        for attrs, label in tabs:
            page = re.search(r'data-page="(\w+)"', attrs).group(1)
            assert "data-page-tab" in attrs
            assert f'href="{routes[page]}"' in attrs
            assert ("is-current" in attrs) == (page == current), (current, page)
            assert ('aria-current="page"' in attrs) == (page == current), (current, page)
            # labels.js PAGE_TABS names the same pages, routes and titles.
            title = re.search(r'title="([^"]+)"', attrs).group(1)
            assert f"{{ page: '{page}', label: '{label}', href: '{routes[page]}', title: '{title}' }}" in labels, page


def test_the_methodology_page_has_the_shell_and_its_own_key():
    html = _methodology_html()
    for element_id in ("sidebar", "sidebar-toggle", "toc", "paper", "banner", "banner-text", "banner-close",
                       "page-tabs", "view-chip", "badge-memory", "badge-threads"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    # No Details drawer and no chart: no tooltip layer, no modal.
    assert 'id="inspector"' not in html and 'id="tooltip-layer"' not in html and "modal-backdrop" not in html
    assert '<aside class="sidebar" id="sidebar">' in html and html.count('<main class="main"') == 1
    assert html.index("css/controls.css") < html.index("css/methodology.css")
    main = _strip_comments((JS / "methodology_main.js").read_text(encoding="utf-8"))
    # Its tabs drop the page's own key, and its outline is not the configuration sidebar.
    assert "wirePageTabs(document, { drop: ['at'] })" in main
    assert "OUTLINE_KEY = 'calosrv.methodology.outline'" in main and "storageKey: OUTLINE_KEY" in main
    # A narrow screen starts with the outline folded, unless the reader chose otherwise before.
    assert "readSidebarPreference(OUTLINE_KEY) === null" in main and "(max-width: 760px)" in main
    # It never writes a view key: none of State's writers (the browser test checks the behaviour).
    for forbidden in ("writeHash(", "state.set(", "adoptBounds(", "adoptSnappedBounds(", "restrictAxes(",
                      "pushState("):
        assert forbidden not in main, forbidden
    css = _strip_comments((STATIC / "css" / "methodology.css").read_text(encoding="utf-8"))
    assert "transition" not in css and "animation" not in css and "scroll-behavior: smooth" not in css


def test_the_tabs_are_wired_and_the_admin_link_opens_admin_settings():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "wirePageTabs();" in main
    boot = re.search(r"async function boot\(\) \{(.*?)\n\}", main, re.DOTALL).group(1)
    # Read before the first hash write (which drops the query), acted on once the experiments are in.
    assert "const openAdmin = new URLSearchParams(location.search).has('admin');" in boot
    assert boot.index("openAdmin = ") < boot.index("loadExperiments(") < boot.index("adminModal?.open()")
    assert "history.replaceState(null, '', location.pathname + location.hash);" in boot
    models = _strip_comments((JS / "models_main.js").read_text(encoding="utf-8"))
    assert "wirePageTabs();" in models
    common = _strip_comments((JS / "page_common.js").read_text(encoding="utf-8"))
    assert "a[data-page-tab]" in common and "capture: true" in common
    for event in ("'pointerdown'", "'focus'", "'click'", "'auxclick'", "'contextmenu'"):
        assert event in common, event


def test_both_pages_land_a_methodology_badge_link_after_the_experiments_load():
    for name, loader in (("main.js", "loadExperiments("), ("models_main.js", "loadCatalogue(")):
        source = _strip_comments((JS / name).read_text(encoding="utf-8"))
        assert re.search(r"import \{[^}]*\breadDeepLink\b[^}]*\brevealPanel\b[^}]*\} from './page_common.js'", source), name
        for helper in ("returnLink", "revealNotice"):
            assert helper in source.split("from './page_common.js'")[0], (name, helper)
        boot = re.search(r"async function boot\(\) \{(.*?)\n\}", source, re.DOTALL).group(1)
        strip = "history.replaceState(null, '', location.pathname + location.hash);"
        assert boot.index("readDeepLink(location.search)") < boot.index(loader) < boot.index(strip), name
        assert boot.index(strip) < boot.index("landDeepLink(deepLink)"), name
        land = re.search(r"function landDeepLink\(link\) \{(.*?)\n\}", source, re.DOTALL).group(1)
        assert land.index("setReturnLink(") < land.index("revealPanel("), name
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    assert "reveal: (id) => physics.reveal(id)" in main


def test_the_models_page_snaps_like_every_other_track():
    css = (STATIC / "css" / "models.css").read_text(encoding="utf-8")
    assert "transition" not in _strip_comments(css) and "animation" not in _strip_comments(css)
    layout = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    tabs = layout[layout.index("page tabs"):]
    assert "transition" not in _strip_comments(tabs)
    assert "prefers-reduced-motion" not in css + layout
    assert ".voxels-grid[hidden] { display: none; }" in css and ".card-caption[hidden] { display: none; }" in css
    assert re.search(r"@container main \(max-width: \d+px\) \{\s*\.voxel-pair \{ grid-template-columns: "
                     r"minmax\(0, 1fr\); \}", css)


def test_the_models_cards_have_the_page_card_anatomy():
    source = (JS / "models_cards.js").read_text(encoding="utf-8")
    code = _strip_comments(source)
    for token in ("card.dataset.panel = id", "details.dataset.inspect = id", "exporter.dataset.export = id",
                  "details.setAttribute('aria-controls', 'inspector')", "plot.id = `plot-${id}`"):
        assert token in code, token
    assert "plot area only" in source
    for forbidden in ("innerHTML", "insertAdjacentHTML", "dataset.shower", "dataset.roi", "dataset.reset",
                      "getElementById"):
        assert forbidden not in code, forbidden
    # Every panel and notes module is a guarded dynamic import with a literal specifier.
    for module in ("perf_bins", "resolution_scaling", "hist2d", "distribution", "feature_table", "correlation", "rates", "xgb_cv",
                   "xgb_binary", "xgb_tree", "xgb_importance"):
        assert f"import('./panels/{module}.js')" in code, module
    for module in ("models_notes", "xgb_notes"):
        assert f"import('./{module}.js')" in code, module
    assert "typeof Class !== 'function'" in code
    assert "rootMargin: '0px'" in code
    main = _strip_comments((JS / "models_main.js").read_text(encoding="utf-8"))
    assert "import('./voxel_views.js')" in main and "typeof module?.VoxelSection !== 'function'" in main
    # The cards exist before the export menus are wired, and the 3-D section too.
    assert main.index("new ModelsSection(") < main.index("attachExportMenus({")
    assert main.index("voxels = await mountVoxels();") < main.index("attachExportMenus({")
    body = re.search(r"function relayoutAll\(\) \{(.*?)\n\}", main, re.DOTALL).group(1)
    assert "models.relayout()" in body and "voxels?.relayout?.()" in body
    # The XGBoost notice is hidden while a model run pairs with the experiment, and on Views (no XGBoost card
    # there; the behaviour is run in tests/test_js_models_shell.py).
    caps = _strip_comments((JS / "capabilities.js").read_text(encoding="utf-8"))
    assert "xgbNotice: runs.length ? null :" in caps
    assert "setHidden('xgb-notice', !xgbNoticeShown(msub, plan));" in main


# ------------------------------------------------------------- the theme --


def _methodology_page() -> str:
    return (STATIC / "methodology.html").read_text(encoding="utf-8")


def _all_pages():
    return (("physics", _html(), 'id="open-admin"'), ("models", _models_html(), 'href="/?admin=1"'),
            ("methodology", _methodology_page(), 'id="export-article"'))


def test_the_first_script_of_every_page_is_the_classic_theme_boot_in_the_head():
    for name, html, _ in _all_pages():
        first = re.search(r"<script\b[^>]*>", html)
        assert first and first.group(0) == '<script src="/static/js/theme_boot.js">', name
        assert not re.search(r"\b(type|defer|async)\b", first.group(0)), name
        assert html.index("<head>") < first.start() < html.index("</head>"), name
        assert first.start() < html.index('<link rel="stylesheet"'), name


def test_every_header_has_one_theme_toggle_before_the_admin_or_export_control():
    for name, html, control in _all_pages():
        assert html.count('id="theme-toggle"') == 1, name
        header = html[html.index("<header"):html.index("</header>")]
        assert 'id="theme-toggle"' in header, name
        button = re.search(r'<button class="icon-button theme-toggle" id="theme-toggle" type="button"(.*?)</button>',
                           header, re.DOTALL)
        assert button, name
        body = button.group(1)
        for attribute in ("aria-label", "title"):
            assert re.search(rf'{attribute}="[^"]+"', body), (name, attribute)
        svgs = re.findall(r"<svg\b([^>]*)>", body)
        assert len(svgs) == 2 and all('aria-hidden="true"' in s for s in svgs), name
        assert 'class="theme-icon theme-icon-sun"' in svgs[0] and 'class="theme-icon theme-icon-moon"' in svgs[1], name
        after = header[button.end():]
        assert control in after, name
        # Nothing but whitespace and comments between the toggle and the control.
        gap = after[:after.index(control)]
        assert re.sub(r"<!--.*?-->|\s|<(?:button|a)\b[^>]*?class=\"action\"[^>]*?(?=$)", "", gap, flags=re.DOTALL) in (
            "", "<buttonclass=\"action\"", "<aclass=\"action\""), name


def _header_of(html: str) -> str:
    return html[html.index("<header"):html.index("</header>")]


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Parents(HTMLParser):
    """Each element's parent, every element named by its id, else its first class, else its tag."""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.parent: dict[str, str | None] = {}

    @staticmethod
    def _key(tag, attrs):
        attrs = dict(attrs)
        return attrs.get("id") or (attrs.get("class") or tag).split()[0]

    def handle_starttag(self, tag, attrs):
        key = self._key(tag, attrs)
        self.parent.setdefault(key, self.stack[-1] if self.stack else None)
        if tag not in _VOID:
            self.stack.append(key)

    def handle_startendtag(self, tag, attrs):
        self.parent.setdefault(self._key(tag, attrs), self.stack[-1] if self.stack else None)

    def handle_endtag(self, tag):
        if tag not in _VOID and self.stack:
            self.stack.pop()


def _parents(markup: str) -> dict[str, str | None]:
    parser = _Parents()
    parser.feed(markup)
    return parser.parent


#: The page action's name in `_Parents` terms: its id, or the Models link's class.
_ACTION_KEY = {"physics": "open-admin", "models": "action", "methodology": "export-article"}


def test_every_header_is_two_rows_with_the_application_bar_above_one_context_pill():
    """Row 1 is the identical application bar; row 2 holds one pill centred under the tabs.

    The order of the markup is checked, and so is its nesting: a tab strip
    moved into the start group, or the action out of the end group, would keep
    the order and break the layout.
    """
    for name, html, action in _all_pages():
        header = _header_of(html)
        expected = {"header-bar": "header", "header-context": "header", "header-start": "header-bar",
                    "page-tabs": "header-bar", "header-end": "header-bar", "sidebar-toggle": "header-start",
                    "brand": "header-start", "compute-badge": "header-end", "theme-toggle": "header-end",
                    _ACTION_KEY[name]: "header-end"}
        if name == "methodology":
            expected.update({"view-chip": "header-context", "view-chip-text": "view-chip"})
        else:
            expected.update({"context-field": "header-context", "experiment-select": "context-field"})
        if name == "physics":
            expected["exact-badge"] = "header-context"
        parents = _parents(header)
        assert {key: parents.get(key) for key in expected} == expected, (name, parents)
        order = ['<div class="header-bar">', '<div class="header-start">', 'id="sidebar-toggle"', 'class="brand"',
                 '<nav class="page-tabs" id="page-tabs"', '<div class="header-end">', 'id="compute-badge"',
                 'id="theme-toggle"', action, '<div class="header-context">', 'class="context-field"']
        at = -1
        for token in order:
            found = header.find(token, at + 1)
            assert found > at, (name, token, "missing or out of order")
            at = found
        context = header[header.index('<div class="header-context">'):]
        if name in ("physics", "models"):
            label = '<label class="context-label" for="experiment-select">Experiment</label>'
            select = '<select class="picker" id="experiment-select"></select>'
            assert label in context and select in context, name
            assert context.index(label) < context.index(select), name
        else:
            chip = re.search(r'<div\b[^>]*\bid="view-chip"[^>]*>', context)
            assert chip and 'class="context-field"' in chip.group(0), name
            inner = context[chip.end():]
            span = '<span class="context-label">Links open</span>'
            value = re.search(r'<b\b[^>]*(?=[^>]*\bclass="context-value")[^>]*\bid="view-chip-text"[^>]*>', inner) \
                or re.search(r'<b\b[^>]*(?=[^>]*\bid="view-chip-text")[^>]*\bclass="context-value"[^>]*>', inner)
            assert span in inner and value and inner.index(span) < value.start(), name
        if name == "physics":
            exact = 'class="badge context-end" id="exact-badge"'
            assert exact in context and context.index('class="context-field"') < context.index(exact), name
        else:
            assert 'id="exact-badge"' not in html, name
        assert 'style="' not in header and 'class="spacer"' not in header, name


def test_the_header_css_holds_two_rows_that_wrap_instead_of_overflowing():
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    flat = _strip_comments(css)
    norm = lambda body: re.sub(r"\s+", " ", body)  # noqa: E731
    assert re.search(r"flex-direction:\s*column", _rule(flat, ".header"))
    assert re.search(r"flex-wrap:\s*wrap", _rule(flat, ".header-bar"))
    ends = norm(_rule(flat, ".header-start, .header-end"))
    assert "flex: 1 1 0" in ends and "min-width: max-content" in ends, ends
    columns = norm(_rule(flat, ".header-context"))
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, max-content) minmax(max-content, 1fr)" in columns, columns
    start = css.index("/* ------------------------------------------------------------------ header */")
    end = css.index("/* ----", start + 10)
    block = _strip_comments(css[start:end])
    assert "transition" not in block and "animation" not in block
    methodology = (STATIC / "css" / "methodology.css").read_text(encoding="utf-8")
    assert "100vw - 1000px" not in methodology


def test_every_colour_map_option_names_what_it_draws_on_the_light_theme():
    """On the light theme a slot draws a ramp made for white (palette.js); its option says which."""
    for html in (_html(), _models_html()):
        for value in ("viridis", "cividis", "plasma", "turbo"):
            option = re.search(rf'<option value="{value}"([^>]*)>', html)
            assert option, value
            title = re.search(r'title="([^"]+)"', option.group(1))
            assert title and "On the light theme this slot draws a ramp made for white" in title.group(1), value
        turbo = re.search(r'<option value="turbo"[^>]*title="([^"]+)"', html).group(1)
        assert "3:1" in turbo and "not monotone" in turbo


def _browser_page_calls():
    """Every Playwright page or context creation in tests/test_browser_*.py.

    Yields `(where, keywords, from_context)`: the call's file and line, the
    keyword names it passes, and whether its receiver is a context this module
    made with `new_context(...)` (whose pages inherit the context's scheme).
    """
    import ast

    for path in sorted(Path(__file__).resolve().parent.glob("test_browser_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        contexts = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "new_context"):
                contexts.update(t.id for t in node.targets if isinstance(t, ast.Name))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("new_page", "new_context")):
                continue
            receiver = node.func.value
            from_context = (node.func.attr == "new_page" and isinstance(receiver, ast.Name)
                            and receiver.id in contexts)
            yield (f"{path.name}:{node.lineno}", {k.arg for k in node.keywords}, from_context)


def test_every_browser_page_names_its_colour_scheme():
    """Playwright emulates `prefers-color-scheme: light` unless told otherwise.

    The page follows the system's theme when nothing is stored (theme.js), so a
    browser test that names no scheme would silently boot the light theme and
    check that instead of the dark one it was written for. Every page and
    context a browser test opens therefore names its scheme; a page made from a
    context inherits the context's.
    """
    calls = list(_browser_page_calls())
    assert len(calls) >= 16, calls
    unnamed = [where for where, keywords, from_context in calls
               if not from_context and "color_scheme" not in keywords]
    assert not unnamed, f"name color_scheme= at {unnamed}"


# ------------------------------------------------ Longitudinal Channels --


def _group_block(html: str) -> str:
    start = html.index('<div class="sidebar-group" id="group-lgroups" hidden>')
    end = html.index('<div class="sidebar-group"', start + 10)
    return html[start:end]


def test_the_channels_group_sits_in_each_pages_sidebar_between_its_neighbours():
    """Physics: after the resolution group, before the display channel. Models: after
    the frame group, before the colour map. Once per page, inside the sidebar."""
    for html, before, after in ((_html(), "group-resolution", "group-channel"),
                                (_models_html(), "group-m-frame", "group-m-colormap")):
        assert html.count('id="group-lgroups"') == 1
        position = html.index('id="group-lgroups"')
        assert html.index(f'id="{before}"') < position < html.index(f'id="{after}"')
        assert html.index('<aside class="sidebar" id="sidebar">') < position < html.index("</aside>")
        assert position < html.index('<main class="main">')


def test_the_channels_group_is_the_same_markup_on_both_pages_and_starts_hidden():
    physics, models = _group_block(_html()), _group_block(_models_html())
    assert physics == models
    for element_id in ("lgroups-heading", "info-lgroups", "ctl-lgroups-mode", "lgroups-bar", "lgroups-edit",
                       "lgroups-summary", "lgroups-notice"):
        assert physics.count(f'id="{element_id}"') == 1, element_id
    assert 'id="group-lgroups" hidden' in physics
    assert 'aria-controls="lgroups-modal"' in physics


def test_the_channels_modal_is_present_exactly_once_per_page_outside_sidebar_and_main():
    for html in (_html(), _models_html()):
        assert html.count('id="lgroups-modal"') == 1
        assert html.count('aria-labelledby="lgroups-title"') == 1
        assert html.count('id="lgroups-title"') == 1
        modal = html.index('id="lgroups-modal"')
        assert modal > html.index("</main>")
        assert modal > html.index("</aside>")
        assert re.search(r'id="lgroups-modal" hidden>', html)
        body = html[modal:html.index('id="lgroups-apply"', modal)]
        for element_id in ("lgroups-ribbon", "lgroups-presets", "lgroups-shorthand", "lgroups-table", "lgroups-rows",
                           "lgroups-live", "lgroups-reset", "lgroups-cancel"):
            assert f'id="{element_id}"' in body, element_id
    # No id the channel block or modal owns is declared twice on a page.
    for html in (_html(), _models_html()):
        ids = re.findall(r'id="(lgroups-[\w-]+|group-lgroups|ctl-lgroups-mode|info-lgroups)"', html)
        assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)


def test_the_channels_markup_and_styles_carry_no_colour_literal():
    colour = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for html in (_html(), _models_html()):
        group = _group_block(html)
        modal = html[html.index('id="lgroups-modal"'):html.index('id="lgroups-apply"')]
        for part in (group, modal):
            assert not colour.search(part)
            assert "style=" not in part
    css = _strip_comments((STATIC / "css" / "controls.css").read_text(encoding="utf-8"))
    section = css[css.index("#group-lgroups[hidden]"):]
    assert not colour.search(section)
    assert "transition" not in section and "animation" not in section


def test_the_channels_modules_name_no_colour_literal():
    colour = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for name in ("layer_groups.js", "panels/depth_groups.js", "controls/layer_groups_control.js"):
        source = _strip_comments((JS / name).read_text(encoding="utf-8"))
        assert not colour.search(re.sub(r"'[^'\n]*&#\d+;[^'\n]*'", "", source)), name


def test_the_channel_shorthand_is_described_by_its_error_on_both_pages():
    """UI-11: a field announced as invalid is linked to its reason."""
    for html in (_html(), _models_html()):
        field = re.search(r'<input[^>]*id="lgroups-shorthand"[^>]*>', html, re.DOTALL)
        assert field and 'aria-describedby="lgroups-shorthand-error"' in field.group(0)
        assert html.count('id="lgroups-shorthand-error"') == 1


# ------------------------------------------------------ the particle filter --

#: Every id of the block (brief section 7), once per page, inside `#group-particle`.
PARTICLE_IDS = ("group-particle", "particle-heading", "ctl-particle-p", "particle-p-label", "pp-num-lo", "pp-num-hi",
                "pp-fill", "pp-lo", "pp-hi", "particle-p-hint", "ctl-particle-theta", "particle-theta-label",
                "pt-num-lo", "pt-num-hi", "pt-fill", "pt-lo", "pt-hi", "particle-theta-hint", "particle-count",
                "particle-scope", "particle-clear")
_PARTICLE_OPEN = '<div class="sidebar-group" id="group-particle" hidden>'
SCOPE_NOTE_TWO = ("Narrows which events the pickers offer (Pick for me, Most tilted, previous / next, and the 3-D view's "
                  "Densest), drawn from the whole experiment. E₁, E₂ and D do not narrow them; they steer the ensemble "
                  "views alone.")
#: Brief section 5.1's PICK_TITLE, which `event_picker.js` carries and index.html copies by hand.
PICK_TITLE_NEW = ("A candidate event drawn uniformly at random from the whole experiment under the particle filter: a "
                  "seeded shuffle, so no event repeats until all have been drawn. Each click takes the next draw.")


def _particle_block(html: str) -> str:
    return _div_span(html, _PARTICLE_OPEN)


def _sidebar(html: str) -> str:
    return html[html.index('<aside class="sidebar"'):html.index("</aside>")]


def _tag(html: str, element_id: str) -> str:
    """The opening tag of the element with `element_id`."""
    match = re.search(r'<[a-z]+\b[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>', html, re.DOTALL)
    assert match, element_id
    return match.group(0)


def _js_string(source: str, name: str) -> str:
    """The value of `export const NAME = '...' + '...';`, its literals joined (event_picker.js's titles)."""
    match = re.search(rf"export const {name} = (.*?);\n", source, re.DOTALL)
    assert match, name
    parts = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", match.group(1))
    return "".join(a or b for a, b in parts).replace("\\'", "'")


def _unescape(text: str) -> str:
    import html as _h
    return _h.unescape(text)


def test_the_particle_block_is_the_same_markup_on_both_pages_and_starts_hidden():
    physics, models = _particle_block(_html()), _particle_block(_models_html())
    assert physics == models
    for html in (_html(), _models_html()):
        assert html.count('id="group-particle"') == 1
        block = _particle_block(html)
        for element_id in PARTICLE_IDS:
            assert html.count(f'id="{element_id}"') == 1, element_id
            assert f'id="{element_id}"' in block, element_id
    block = physics
    assert '<h2><span id="particle-heading">Particle Filter</span> <span class="muted">(event pickers)</span></h2>' in block
    # The momentum pair: GeV, step 0.05; the angle pair: degrees, step 0.1; each label names its first field.
    assert '<label for="pp-num-lo" id="particle-p-label">p &mdash; particle momentum [GeV]</label>' in block
    assert '<label for="pt-num-lo" id="particle-theta-label">&theta; &mdash; incident polar angle [&deg;]</label>' in block
    for element_id, step in (("pp-num-lo", "0.05"), ("pp-num-hi", "0.05"), ("pt-num-lo", "0.1"), ("pt-num-hi", "0.1")):
        tag = _tag(block, element_id)
        assert 'type="number"' in tag and f'step="{step}"' in tag and "aria-label=" in tag, element_id
    assert 'aria-label="Particle momentum minimum [GeV]"' in _tag(block, "pp-num-lo")
    assert 'aria-label="Particle momentum maximum [GeV]"' in _tag(block, "pp-num-hi")
    for element_id in ("pp-lo", "pp-hi", "pt-lo", "pt-hi"):
        assert 'type="range"' in _tag(block, element_id), element_id
    for fill in ("pp-fill", "pt-fill"):
        assert f'<div class="fill" id="{fill}"></div>' in block
    # The hints name the columns in mono.
    p_hint = block[block.index('id="particle-p-hint"'):block.index("</div>", block.index('id="particle-p-hint"'))]
    assert '<span class="mono">incoming_momentum_A</span>' in p_hint and '<span class="mono">_B</span>' in p_hint
    assert _unescape(re.sub(r"<[^>]+>", "", p_hint)).endswith("), in GeV.")
    t_hint = block[block.index('id="particle-theta-hint"'):block.index("</div>", block.index('id="particle-theta-hint"'))]
    assert '<span class="mono">incoming_theta_A</span>' in t_hint and "in degrees" in t_hint
    # The count speaks politely; the scope note is the two-shower sentence; Clear waits for a bound.
    assert '<div class="caption" id="particle-count" role="status" aria-live="polite">&mdash;</div>' in block
    picker = (JS / "event_picker.js").read_text(encoding="utf-8")
    scope = re.search(r'<div class="hint" id="particle-scope">(.*?)</div>', block, re.DOTALL).group(1)
    scope_text = _unescape(re.sub(r"</?sub>", "", scope))
    # The two-shower scopeNote of brief section 5.1, which the script rewrites per experiment.
    assert scope_text == SCOPE_NOTE_TWO
    assert "export function scopeNote" in picker
    assert '<button class="mini" id="particle-clear" type="button" disabled>Clear particle filter</button>' in block
    # Tokens only: no colour literal, no inline style.
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", block) and "style=" not in block


def test_the_particle_block_sits_between_its_neighbours_outside_every_other_group():
    # Physics: after the Reference Frame group closes, before the Event Picker's group.
    html = _html()
    sidebar = _sidebar(html)
    frame = _div_span(sidebar, '<div class="sidebar-group" id="group-frame">')
    frame_end = sidebar.index(frame) + len(frame)
    position = sidebar.index(_PARTICLE_OPEN)
    inspector = re.search(r"<h2>\s*Event Picker", sidebar)
    assert inspector, "the Event Picker heading is missing"
    assert frame_end <= position < inspector.start()
    # Nothing but a comment between the frame group's close and the block.
    assert re.fullmatch(r"\s*(<!--.*?-->\s*)*", sidebar[frame_end:position], re.DOTALL)
    block = _particle_block(sidebar)
    assert sidebar.index(block) + len(block) < inspector.start()
    for other in ("group-filters", "group-frame", "group-event", "group-resolution", "group-channel", "group-colormap",
                  "group-lgroups", "group-model"):
        opening = re.search(rf'<div class="sidebar-group" id="{other}"( hidden)?>', sidebar)
        assert opening, other
        assert 'id="group-particle"' not in _div_span(sidebar, opening.group(0)), other
    # The Event Inspector's controls and the compare toggle stay outside it, in their order.
    for kept in ('id="ctl-event"', 'id="opt-compare"', 'id="event-pick"', 'id="frame-caption"'):
        assert kept not in block, kept
    assert sidebar.index('id="frame-caption"') < sidebar.index('id="opt-compare"') < sidebar.index('id="ctl-event"')
    # Models: after the undefined-D choice, before the Reconstruction Model group.
    html = _models_html()
    sidebar = _sidebar(html)
    position = sidebar.index(_PARTICLE_OPEN)
    assert sidebar.index('id="ctl-undefined-d"') < position < sidebar.index('id="group-m-model"')
    block = _particle_block(sidebar)
    assert sidebar.index(block) + len(block) < sidebar.index('<div class="sidebar-group" id="group-m-model">')
    for other in ("group-m-model", "group-m-frame", "group-lgroups", "group-m-colormap"):
        opening = re.search(rf'<div class="sidebar-group" id="{other}"( hidden)?>', sidebar)
        assert opening, other
        assert 'id="group-particle"' not in _div_span(sidebar, opening.group(0)), other
    assert 'id="ctl-undefined-d"' not in block and 'id="filter-logic"' not in block


def test_the_module_ids_are_the_markups():
    """Every id `controls/particle_filter.js` looks up is in both pages' block."""
    source = _strip_comments((JS / "controls" / "particle_filter.js").read_text(encoding="utf-8"))
    ids = set(re.findall(r"'((?:pp|pt|particle|ctl-particle|group-particle)[\w-]*)'", source))
    ids -= {"particle-line", "particle_p_min", "particle_p_max", "particle_theta_min", "particle_theta_max"}
    ids = {i for i in ids if "_" not in i}
    assert ids >= {"group-particle", "particle-count", "particle-scope", "particle-clear", "particle-theta-hint",
                   "ctl-particle-p", "ctl-particle-theta", "pp-lo", "pp-hi", "pp-fill", "pp-num-lo", "pp-num-hi",
                   "pt-lo", "pt-hi", "pt-fill", "pt-num-lo", "pt-num-hi"}, ids
    for html in (_html(), _models_html()):
        block = _particle_block(html)
        for element_id in ids:
            assert f'id="{element_id}"' in block, element_id


def test_the_event_pickers_and_the_open_in_3d_link_on_the_physics_page():
    html = _html()
    picker = (JS / "event_picker.js").read_text(encoding="utf-8")
    actions = _div_span(_sidebar(html), '<div class="event-actions">')
    # Most tilted follows Pick for me in the actions row; both are typed buttons titled by event_picker.js.
    assert actions.index('id="event-pick"') < actions.index('id="event-pick-tilted"')
    assert 'id="event-close"' not in actions
    pick, tilted = _tag(actions, "event-pick"), _tag(actions, "event-pick-tilted")
    assert pick.startswith('<button class="action" id="event-pick" type="button"')
    assert tilted.startswith('<button class="action" id="event-pick-tilted" type="button"')
    assert re.search(r'id="event-pick-tilted"[^>]*>Most tilted</button>', actions, re.DOTALL)
    assert re.search(r'id="event-pick"[^>]*>Pick for me</button>', actions, re.DOTALL)
    # index.html's title is a hand copy of PICK_TITLE (brief 3.8): the literal, and the module's own string.
    assert _unescape(re.search(r'title="([^"]*)"', pick).group(1)) == PICK_TITLE_NEW
    assert _unescape(re.search(r'title="([^"]*)"', pick).group(1)) == _js_string(picker, "PICK_TITLE")
    assert _unescape(re.search(r'title="([^"]*)"', tilted).group(1)) == _js_string(picker, "TILTED_TITLE")
    assert html.count('id="event-pick-tilted"') == 1
    # Open in 3-D: an anchor styled as a mini button in the Event Inspector grid's head, hidden until an event is
    # drawn, pointing at the Models page. The head's close button is gone (the Entire selection tab is the way back).
    grid = html[html.index('<section class="frame-grid" id="event-grid"'):]
    grid = grid[:grid.index("</section>")]
    head = _div_span(grid, '<div class="frame-grid-head">')
    assert html.count('id="event-open-3d"') == 1 and 'id="event-open-3d"' in head
    assert 'id="event-grid-close"' not in head
    link = _tag(head, "event-open-3d")
    assert link.startswith('<a class="mini" id="event-open-3d" href="/models" hidden')
    assert _unescape(re.search(r'title="([^"]*)"', link).group(1)) == _js_string(picker, "OPEN_3D_TITLE")
    assert re.search(r'id="event-open-3d"[^>]*>Open in 3-D &rarr;</a>', head, re.DOTALL)
    # The Models page has neither: its pickers are built on the 3-D card (voxel_views.js).
    models = _models_html()
    assert 'id="event-pick-tilted"' not in models and 'id="event-open-3d"' not in models


def test_the_particle_block_styles_are_tokens_only_and_kept_to_views_on_the_models_page():
    models_css = _strip_comments((STATIC / "css" / "models.css").read_text(encoding="utf-8"))
    assert re.search(r'\.app\[data-msub="distill"\] #group-particle,\s*\.app\[data-msub="perf"\] #group-particle'
                     r'\s*\{\s*display: none;\s*\}', models_css)
    controls = _strip_comments((STATIC / "css" / "controls.css").read_text(encoding="utf-8"))
    colour = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for rule in re.findall(r"[^{}]*(?:#group-particle|#particle-[\w-]+|a\.mini|\.event-actions)[^{}]*\{[^}]*\}", controls):
        assert not colour.search(rule), rule
        assert "transition" not in rule and "animation" not in rule, rule
    # A hidden group is hidden; the actions row wraps its three buttons.
    assert ".sidebar-group[hidden] { display: none; }" in (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    assert re.search(r"\.event-actions\s*\{[^}]*flex-wrap: wrap", controls)


def test_both_pages_mount_the_particle_filter_and_abort_its_request_on_a_switch():
    main = _strip_comments((JS / "main.js").read_text(encoding="utf-8"))
    models = _strip_comments((JS / "models_main.js").read_text(encoding="utf-8"))
    for source in (main, models):
        assert "import { mountParticleFilter } from './controls/particle_filter.js';" in source
        assert "mountParticleFilter({" in source
    keys = re.search(r"const SPATIAL_ABORT_KEYS = \[(.*?)\];", main, re.DOTALL).group(1)
    assert "'event-candidates'" in keys
    # The Models page aborts the block's own key with its other requests.
    assert "abortRequest(particle.abortKey)" in _function_body(models, "clearExperimentViews")
    # The particle block's ids are among the ids each page audits.
    physics_ids = re.search(r"const REQUIRED_IDS = \[(.*?)\];", main, re.DOTALL).group(1)
    models_ids = re.search(r"const MODELS_REQUIRED_IDS = \[(.*?)\];", models, re.DOTALL).group(1)
    for element_id in PARTICLE_IDS:
        assert f"'{element_id}'" in physics_ids, element_id
        assert f"'{element_id}'" in models_ids, element_id
    for element_id in ("event-pick-tilted", "event-open-3d"):
        assert f"'{element_id}'" in physics_ids, element_id


def test_the_event_inspector_keeps_its_pick_route_and_takes_its_sentences_from_the_picker_module():
    inspector = _strip_comments((JS / "event_inspector.js").read_text(encoding="utf-8"))
    assert "'/api/event/pick'" in inspector
    imported = re.search(r"import \{([^}]*)\} from './event_picker\.js';", inspector, re.DOTALL)
    assert imported, "event_inspector.js must import event_picker.js"
    names = {n.strip() for n in imported.group(1).split(",") if n.strip()}
    for name in ("FIRST_SEED", "pickParams", "followDecision", "focusShower", "emptyLine", "placeLine", "matchLine",
                 "replacedLine", "pickerTitle", "open3dTitle", "eventIn3dHref"):
        assert name in names, name
    # No sentence of event_picker.js is written here again.
    for fragment in ("Candidate ", "left the candidates", "Not a candidate", "matches the particle filter",
                     "N = 0", "drawn uniformly at random", "Open this event", "no shower matches"):
        assert fragment not in inspector, fragment
    assert "const FIRST_SEED" not in inspector


def test_the_picker_modules_write_text_nodes_only():
    for name in ("event_picker.js", "controls/particle_filter.js"):
        source = _strip_comments((JS / name).read_text(encoding="utf-8"))
        for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert token not in source, (name, token)
    # The picker module is pure: no DOM.
    picker = _strip_comments((JS / "event_picker.js").read_text(encoding="utf-8"))
    for token in ("document.", "window.", "getElementById", "createElement"):
        assert token not in picker, token


# ------------------------------------------- the Physics page's subpages --
# Brief 9.1 and 9.2 (physics-subpages, 2026-11-16): Entire selection | Event viewer.

SIDEBAR_GROUP_ORDER = ("group-filters", "group-frame", "group-particle", "group-event", "group-resolution",
                       "group-lgroups", "group-channel", "group-colormap", "group-model")
TAB_TITLES = {
    "selection": ("Entire selection", "Every selected event: the 2 × 2 diagnostic, the compare-frames view and the "
                                      "physics cards, under E₁, E₂ and D."),
    "event": ("Event viewer", "One event at a time, drawn from the whole experiment under the particle filter: one "
                              "shower in the Absolute, per-shower translated and Local frames."),
}
EVENT_ITEMS = ("stat-event", "stat-shower", "stat-p", "stat-theta", "stat-cells", "stat-ev-edep", "stat-place")
SELECTION_ITEMS = ("stat-events", "stat-hits", "stat-edep", "stat-d", "stat-nod", "stat-rho", "stat-clipped",
                   "stat-wneg")


def _main(html: str) -> str:
    return html[html.index('<main class="main">'):html.index("</main>")]


def _controls_css() -> str:
    return _strip_comments((STATIC / "css" / "controls.css").read_text(encoding="utf-8"))


def test_the_app_opens_on_entire_selection():
    assert '<div class="app" data-psub="selection">' in _html()


def test_the_sidebar_groups_are_in_order_and_each_wraps_its_controls():
    html = _html()
    sidebar = _sidebar(html)
    positions = [sidebar.index(f'id="{group}"') for group in SIDEBAR_GROUP_ORDER]
    assert positions == sorted(positions), "the sidebar groups keep their order"
    for group in SIDEBAR_GROUP_ORDER:
        assert sidebar.count(f'id="{group}"') == 1, group
        assert re.search(rf'<div class="sidebar-group" id="{group}"( hidden)?>', sidebar), group
    spans = {g: _div_span(sidebar, re.search(rf'<div class="sidebar-group" id="{g}"( hidden)?>', sidebar).group(0))
             for g in SIDEBAR_GROUP_ORDER}
    # Nothing but comments between one group's close and the next's open: every control is in a group.
    for before, after in zip(SIDEBAR_GROUP_ORDER, SIDEBAR_GROUP_ORDER[1:]):
        gap = sidebar[sidebar.index(spans[before]) + len(spans[before]):sidebar.index(spans[after])]
        assert re.fullmatch(r"\s*(<!--.*?-->\s*)*", gap, re.DOTALL), (before, after)
    members = {
        "group-filters": ("Filtering Parameters", 'id="ctl-e1"', 'id="ctl-e2"', 'id="ctl-d"', 'id="filter-logic"',
                          'id="ctl-undefined-d"'),
        "group-event": ("Event Picker", 'id="info-event"', 'id="ctl-event"', 'id="event-pick"',
                        'id="event-pick-tilted"', 'id="event-caption"'),
        "group-model": ("Reconstruction Model", 'name="model"', 'id="model-caption"', "Model Performance",
                        'id="metrics"'),
        "group-channel": ('id="channel-caption"', 'id="channel-shut"'),
    }
    for group, tokens in members.items():
        for token in tokens:
            assert token in spans[group], (group, token)
    # The sidebar's headings: the event group is the Event Picker, never "Event Inspector" (the figure's name).
    assert re.search(r"<h2>\s*Event Picker\s*<button[^>]*id=\"info-event\"", spans["group-event"], re.DOTALL)
    assert not re.search(r"<h2>\s*Event Inspector", sidebar)
    # The picker's hint: the whole experiment's candidates, narrowed by the particle filter.
    hint = re.search(r'<div class="hint">(Draws one shower.*?)</div>', spans["group-event"], re.DOTALL).group(1)
    assert " ".join(_unescape(hint).split()) == (
        "Draws one shower of one event in all three frames — original, translated only, and local — with the "
        "incident direction, the first-layer plane and the origin, one shared colour ramp and one window on all "
        "nine panels. The candidates are the whole experiment's, narrowed by the particle filter.")
    # The group-model wrapper is the last thing in the sidebar.
    assert sidebar.rstrip().endswith("</div>") and sidebar.index(spans["group-model"]) + len(spans["group-model"]) \
        == len(sidebar.rstrip())


def test_the_channel_shut_line_follows_the_channel_caption_and_starts_hidden():
    html = _html()
    channel = _div_span(html, '<div class="sidebar-group" id="group-channel">')
    assert html.count('id="channel-shut"') == 1
    assert '<div class="hint" id="channel-shut" hidden></div>' in channel
    assert channel.index('id="channel-caption"') < channel.index('id="channel-shut"')
    assert "channel-shut" not in _models_html()


def test_the_tab_bar_is_a_tablist_of_two_tabs_at_the_top_of_main():
    html = _html()
    main = _main(html)
    head = _div_span(main, '<div class="physics-head" id="physics-head">')
    # First in main, before the banners and the status bar.
    assert main.index("physics-head") < main.index('id="banner"') < main.index('id="kind-banner"') < main.index('class="statusbar"')
    nav = re.search(r'<nav class="physics-subnav" id="physics-subnav" role="tablist" aria-label="Physics page views">',
                    head)
    assert nav, "the tab bar is a tablist named for the page"
    for psub, (label, title) in TAB_TITLES.items():
        tag = _tag(head, f"psub-tab-{psub}")
        assert tag.startswith('<button class="physics-subtab" id="psub-tab-' + psub + '"'), psub
        for attr in (f'data-psub="{psub}"', 'role="tab"', 'type="button"', f'aria-controls="psub-{psub}"'):
            assert attr in tag, (psub, attr)
        assert _unescape(re.search(r'title="([^"]*)"', tag).group(1)) == title
        assert re.search(rf'id="psub-tab-{psub}"[^>]*>{label}</button>', head, re.DOTALL), psub
    # Roving tabindex: the selected tab is in the order, the other is reached by the arrows.
    assert 'aria-selected="true" tabindex="0"' in _tag(head, "psub-tab-selection")
    assert 'aria-selected="false" tabindex="-1"' in _tag(head, "psub-tab-event")
    assert head.index('id="psub-tab-selection"') < head.index('id="psub-tab-event"')


def test_the_subpages_are_tabpanels_in_main_and_only_the_viewer_starts_hidden():
    html = _html()
    main = _main(html)
    selection = _div_span(main, '<div class="physics-subpage" id="psub-selection"')
    event = _div_span(main, '<div class="physics-subpage" id="psub-event"')
    assert 'role="tabpanel" aria-labelledby="psub-tab-selection" data-psub="selection">' in selection
    assert 'role="tabpanel" aria-labelledby="psub-tab-event" data-psub="event" hidden>' in event
    assert main.index(selection) < main.index(event)
    # Today's order inside Entire selection; the empty state before the grid inside the viewer.
    inside = [selection.index(f'id="{x}"') for x in ("ensemble-grid", "kind-notice", "physics-grid", "compare-grid")]
    assert inside == sorted(inside)
    assert 'id="event-empty"' not in selection and 'id="event-grid"' not in selection
    for kept in ("ensemble-grid", "kind-notice", "physics-grid", "compare-grid"):
        assert f'id="{kept}"' not in event, kept
    assert event.index('id="event-empty"') < event.index('id="event-grid"')
    empty = re.search(r'<section class="kind-notice" id="event-empty" hidden aria-live="polite">\s*'
                      r'<h2 id="event-empty-title">No event drawn</h2>\s*<p id="event-empty-text">&mdash;</p>\s*</section>',
                      event)
    assert empty, "the empty state is a polite kind-notice with its own title and text"
    # The status bar and the banners sit outside both subpages: they are the page's.
    for outside in ('id="banner"', 'id="kind-banner"', 'class="statusbar"', 'id="physics-head"'):
        assert outside not in selection and outside not in event, outside


def test_the_status_bar_names_the_mode_and_each_subpage_owns_its_items():
    html = _html()
    bar = _div_span(html, '<div class="statusbar">')
    assert bar.index('<span class="mode-chip" id="stat-mode" role="status">Entire selection</span>') \
        < bar.index('id="stat-events"')
    def owner(element_id: str):
        """The data-psub-only of the status item that holds `element_id`: its last opening <span> before it."""
        tag = re.findall(r"<span\b[^>]*>", bar[:bar.index(f'id="{element_id}"') + len(element_id)])[-1]
        found = re.search(r'data-psub-only="(selection|event)"', tag)
        return found.group(1) if found else None

    for element_id in SELECTION_ITEMS:
        assert owner(element_id) == "selection", element_id
    for element_id in EVENT_ITEMS:
        assert owner(element_id) == "event", element_id
    # The shared items carry no attribute: the Query latency and the cache note.
    for element_id in ("stat-latency", "stat-cache"):
        assert owner(element_id) is None, element_id
    # The item the page hides on one shower keeps its own id, and the other items keep their hidden attributes.
    assert re.search(r'<span id="stat-shower-item" data-psub-only="event">Shower <b id="stat-shower">', bar)
    assert re.search(r'<span id="stat-wneg-item" data-psub-only="selection" hidden', bar)
    assert re.search(r'<span id="stat-d-item" data-psub-only="selection">', bar)
    assert re.search(r'<span id="stat-nod-item" data-psub-only="selection">', bar)
    assert 'data-psub-only="selection">Events <b id="stat-events">' in bar
    for label, element_id in (("Event", "stat-event"), ("p", "stat-p"), ("θ", "stat-theta"), ("Cells", "stat-cells"),
                              ("Deposited", "stat-ev-edep"), ("Candidate", "stat-place")):
        assert f'data-psub-only="event">{label} <b id="{element_id}">—</b></span>' in bar, element_id
    assert bar.index('class="spacer"') > bar.index('id="stat-place"') and bar.index('class="spacer"') < bar.index('id="stat-latency"')


def test_the_subpage_visibility_rules_select_on_data_psub_never_on_hidden():
    css = _controls_css()
    event_hides = ("#group-filters", "#group-frame", "#group-resolution", "#group-channel", "#group-model",
                   "#ctl-lock-scale", "#ctl-rho-norm")
    rule = re.search(r"((?:\.app\[data-psub=\"event\"\] #[\w-]+,\s*)+\.app\[data-psub=\"event\"\] #[\w-]+)\s*"
                     r"\{\s*display: none;\s*\}", css)
    assert rule, "the Event viewer's hidden controls are one rule"
    assert set(re.findall(r"#[\w-]+", rule.group(1))) == set(event_hides)
    assert re.search(r'\.app\[data-psub="selection"\] #group-particle,\s*\.app\[data-psub="selection"\] #group-event'
                     r"\s*\{\s*display: none;\s*\}", css)
    assert re.search(r'\.app\[data-psub="event"\] \[data-psub-only="selection"\],\s*'
                     r'\.app\[data-psub="selection"\] \[data-psub-only="event"\]\s*\{\s*display: none;\s*\}', css)
    # The wrappers a subpage owns hide by their own hidden attribute; the group visibility is not that.
    assert ".physics-subpage { min-width: 0; }" in css and ".physics-subpage[hidden] { display: none; }" in css
    # Longitudinal Channels and Colour Map stay on both subpages: neither is in a hiding rule.
    for kept in ("#group-lgroups", "#group-colormap"):
        assert not re.search(r'data-psub="[a-z]+"\][^{]*' + kept, css), kept


def test_the_sticky_head_is_the_models_heads_with_a_scoped_scroll_margin():
    css = _controls_css()
    models = _strip_comments((STATIC / "css" / "models.css").read_text(encoding="utf-8"))
    head = _rule(css, ".physics-head")
    reference = _rule(models, ".models-head")
    assert " ".join(head.split()) == " ".join(reference.split())
    assert "position: sticky" in head and "top: -14px" in head and "z-index: 10" in head
    assert "background: var(--canvas)" in head and "border-bottom: 1px solid var(--border)" in head
    # Scoped to the Physics page's data-psub, so the Models page's own rule is untouched.
    assert ".app[data-psub] .main .card { scroll-margin-top: var(--physics-head-h, 0px); }" in css
    assert ".main .card { scroll-margin-top: var(--models-head-h, 0px); }" in models
    assert "data-psub" not in models


def test_the_tabs_style_like_the_models_tabs_and_a_disabled_tab_stays_text():
    css = _controls_css()
    models = _strip_comments((STATIC / "css" / "models.css").read_text(encoding="utf-8"))
    assert " ".join(_rule(css, ".physics-subnav").split()) == " ".join(_rule(models, ".models-subnav").split())
    assert " ".join(_rule(css, ".physics-subtab").split()) == " ".join(_rule(models, ".models-subtab").split())
    selected = _rule(css, '.physics-subtab[aria-selected="true"]')
    for token in ("background: var(--accent-wash)", "border-color: var(--accent)", "color: var(--accent)",
                  "font-weight: 600", "box-shadow: inset 0 -2px 0 var(--accent)"):
        assert token in selected, token
    disabled = _rule(css, '.physics-subtab.is-disabled,\n.physics-subtab[aria-disabled="true"]')
    assert "cursor: not-allowed" in disabled and "color: var(--muted)" in disabled
    hover = _rule(css, '.physics-subtab.is-disabled:hover,\n.physics-subtab[aria-disabled="true"]:hover')
    assert "background: var(--control-bg)" in hover and "color: var(--muted)" in hover
    chip = _rule(css, ".mode-chip")
    for token in ("border: 1px solid var(--accent)", "background: var(--accent-wash)", "color: var(--accent)"):
        assert token in chip, token


def test_the_particle_block_texts_are_the_same_on_both_pages():
    for html in (_html(), _models_html()):
        block = _particle_block(html)
        scope = re.search(r'<div class="hint" id="particle-scope">(.*?)</div>', block, re.DOTALL).group(1)
        assert _unescape(scope) == SCOPE_NOTE_TWO
        hint = re.search(r'<div class="hint" id="particle-p-hint">(.*?)</div>', block, re.DOTALL).group(1)
        assert _unescape(re.sub(r"<[^>]+>", "", hint)) == (
            "Incident momentum of either shower (incoming_momentum_A or _B), in GeV.")
