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


# ------------------------------------------------------- the frame grids --


def test_the_frame_grids_sit_in_main_after_the_ensemble_grid():
    html = _html()
    assert html.count('id="ensemble-grid"') == 1
    assert '<section class="grid" id="ensemble-grid">' in html
    for section in ("compare-grid", "event-grid"):
        assert html.count(f'id="{section}"') == 1, section
        assert f'<section class="frame-grid" id="{section}" hidden aria-labelledby="{section}-title">' in html
        assert html.index('id="ensemble-grid"') < html.index(f'id="{section}"') < html.index("</main>")
        for part in ("title", "label", "close", "rows"):
            assert html.count(f'id="{section}-{part}"') == 1, f"{section}-{part}"
    assert html.index('id="compare-grid"') < html.index('id="event-grid"')


def test_the_event_picker_and_the_compare_toggle_live_in_the_sidebar():
    html = _html()
    sidebar = html[html.index('<aside class="sidebar"'):html.index("</aside>")]
    for element_id in ("event-number", "event-prev", "event-next", "event-pick", "event-close",
                       "event-status", "event-caption", "info-event", "opt-compare", "ctl-event"):
        assert sidebar.count(f'id="{element_id}"') == 1, element_id
    assert sidebar.count('name="event-shower"') == 2
    assert 'id="event-close" type="button" hidden' in sidebar
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
    order = [html.index(f'id="{section}"') for section in ("ensemble-grid", "kind-notice", "physics-grid",
                                                            "compare-grid", "event-grid")]
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
    assert '<span id="stat-wneg-item" hidden' in html
    # The upload hint is schema-neutral: it names every accepted schema.
    upload = html[html.index('<section class="admin-upload"'):html.index('<section class="admin-ingest"')]
    for schema in ("hits_all_models", "standalone_hits", "standalone_events"):
        assert schema in upload, schema
    # The rebuild section lives in the admin panel, after the automatic ingest.
    assert html.index('<section class="admin-ingest"') < html.index('<section class="admin-rebuild"') \
        < html.index('id="tooltip-layer"')
    admin = _strip_comments((JS / "controls" / "admin.js").read_text(encoding="utf-8"))
    assert "/api/admin/experiments/${encodeURIComponent(name)}/rebuild" in admin
    assert "innerHTML" not in admin


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
                "'window-axis-yz'", "'window-axis-xz'", "'event'", "'event-pick'"):
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
    # The filters, the Event Inspector and the model controls stay outside every group.
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
    assert html.index('id="tooltip-layer"') < html.index("<script")
    # Admin Settings live on the Physics page: a link, no modal and no upload form.
    assert 'id="admin-modal"' not in html and 'id="upload-' not in html and "modal-backdrop" not in html
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
    assert [src for _, src in scripts] == ["/static/js/vendor/echarts.min.js", "/static/js/vendor/echarts-gl.min.js",
                                           "/static/js/models_main.js"]
    assert 'type="module"' not in scripts[1][0], "echarts-gl is a classic script"
    assert 'type="module"' in scripts[2][0]
    assert "echarts-gl" not in _html()
    assert html.index("css/controls.css") < html.index("css/models.css")


def test_the_models_page_banners_status_and_sections_are_in_order():
    html = _models_html()
    main = html[html.index('<main class="main">'):html.index("</main>")]
    order = ['id="banner"', 'id="xgb-notice"', 'id="networks-notice"', 'class="statusbar"', 'id="perf-grid"',
             'id="xgb-grid"', 'id="features-grid"', 'id="primaries-grid"', 'id="voxels-grid"']
    positions = [main.index(token) for token in order]
    assert positions == sorted(positions)
    assert '<div class="banner is-info" id="xgb-notice"' in main
    assert '<div class="banner" id="networks-notice" role="status" hidden>' in main
    assert 'id="networks-notice-text"' in main and 'id="xgb-notice-text"' in main
    status = main[main.index('class="statusbar"'):main.index("</div>", main.index('class="statusbar"'))]
    for token in ('id="stat-events"', 'id="stat-kind"', 'class="spacer"', 'id="stat-latency"'):
        assert token in status, token
    for section in ("perf-grid", "xgb-grid", "features-grid", "primaries-grid"):
        assert f'<section class="grid models-grid" id="{section}" hidden' in main, section
    # The 3-D host is empty: VoxelSection builds its own cards.
    assert re.search(r'<section class="voxels-grid" id="voxels-grid" hidden aria-label="3-D views"></section>', main)


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
    assert "storageKey: 'calosrv.methodology.outline'" in main
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
    for module in ("perf_bins", "hist2d", "distribution", "feature_table", "correlation", "rates", "xgb_cv",
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
    # The XGBoost notice is hidden only while a model run pairs with the experiment.
    caps = _strip_comments((JS / "capabilities.js").read_text(encoding="utf-8"))
    assert "xgbNotice: runs.length ? null :" in caps
    assert "setHidden('xgb-notice', !plan.xgbNotice);" in main
