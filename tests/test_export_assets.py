"""The publication-figure export: contrast floor, markup wiring, stamping.

The export itself runs in a browser and cannot be executed here. What *can* be
checked from Python is everything the acceptance criteria state as a property of
the source rather than of a rendered pixel: that the print ink clears the
contrast floor, that every panel actually carries a control, and that the new
modules are inside the cache-stamping graph rather than beside it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "calosrv" / "static"
EXPORT_JS = STATIC / "js" / "export"
PANELS_JS = STATIC / "js" / "panels"

#: Panels that must offer an export control.
PANEL_IDS = ("xy", "yz", "xz", "energy")

#: WCAG 2.1 minimum for normal-size text, and what criterion 4 of the request
#: asks of every axis title, tick label and legend entry.
MIN_CONTRAST = 4.5


# --------------------------------------------------------------- helpers --


def _relative_luminance(hex_colour: str) -> float:
    """WCAG relative luminance of an #rrggbb colour."""
    value = hex_colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _strip_comments(source: str) -> str:
    """Drop /* */ and // comments, so prose is never read as a value."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _print_ink() -> dict[str, str]:
    """Parse the `PRINT_INK` literal out of the token module.

    Read as text rather than executed, because there is no JavaScript runtime in
    this suite. The object is kept deliberately flat - one level, hex strings
    only - so that this stays a parse and not an interpreter.
    """
    source = (EXPORT_JS / "tokens.js").read_text(encoding="utf-8")
    block = re.search(
        r"export const PRINT_INK = \{(.*?)\n\};", source, re.DOTALL
    )
    assert block, "PRINT_INK literal not found in export/tokens.js"
    pairs = re.findall(r"(\w+):\s*'(#[0-9a-fA-F]{6})'", block.group(1))
    assert pairs, "PRINT_INK holds no #rrggbb entries"
    return dict(pairs)


# ------------------------------------------------------ contrast on white --


def test_contrast_helper_matches_known_values():
    """Guard the checker itself, so a broken formula cannot pass the suite."""
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)
    # #767676 is the canonical grey that sits exactly at the 4.5:1 threshold.
    assert contrast_ratio("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.02)


def test_every_print_ink_colour_is_legible_on_white():
    """Acceptance criterion 4, checked mechanically rather than by eye.

    A figure exported on a white background is worthless if its labels carry the
    dark theme's #8b949e, which sits at 2.8:1 there. Every token that is drawn as
    text or as axis chrome has to clear the floor.
    """
    failures = {
        name: round(contrast_ratio(colour, "#FFFFFF"), 2)
        for name, colour in _print_ink().items()
        if contrast_ratio(colour, "#FFFFFF") < MIN_CONTRAST
    }
    assert not failures, f"below {MIN_CONTRAST}:1 on white: {failures}"


def test_no_dark_theme_colour_leaks_into_the_print_tokens():
    """The screen palette and the print palette must not intersect.

    Criterion 1 is that the figure contains no muted dark-theme text. The direct
    way to fail it is to leave one token behind during a future edit, which this
    catches at the source rather than in a rendered file.
    """
    source = (EXPORT_JS / "tokens.js").read_text(encoding="utf-8")
    # Values only. The prose in this file names the dark tokens on purpose, to
    # explain what each print value replaces and why; a comment is not a colour
    # anything is drawn in.
    values = {
        colour.lower()
        for colour in re.findall(r":\s*'(#[0-9a-fA-F]{3,8})'", _strip_comments(source))
    }
    dark = {"#0d1117", "#161b22", "#1c2128", "#30363d", "#e6edf3", "#8b949e"}
    found = sorted(values & dark)
    assert not found, f"dark-theme colours present in the print tokens: {found}"


def _object_literal(source: str, header: str) -> str:
    """The body of a top-level `header {...};` object literal, comments dropped.

    Brace-matched rather than cut at the first `};`, because the print tokens
    hold nested objects (`categorical: { ... }`).
    """
    source = _strip_comments(source)
    start = source.index(header) + len(header)
    assert source[start - 1] == "{", f"{header!r} does not open an object"
    depth = 1
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
    raise AssertionError(f"unterminated object after {header!r}")


def _top_level_tokens(body: str) -> dict[str, str]:
    """`key: value` pairs at the top level of an object body, as raw text."""
    pairs: dict[str, str] = {}
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            match = re.match(r"(\w+):\s*(.+?),?$", stripped)
            if match:
                pairs[match.group(1)] = match.group(2)
        depth += stripped.count("{") - stripped.count("}")
    return pairs


#: Canonical-overlay tokens both themes must define.
FLOOR_TOKENS = ("separationRule", "anchorOpacity", "floorFadeDecades")


def test_floor_tokens_exist_on_screen_and_in_print():
    """The canonical floor, rule and anchor tokens exist in both themes.

    The exporter swaps `THEME` wholesale, so a token defined only on screen
    would print in its screen value - a translucent white rule on white paper,
    or the on-screen fade instead of the hard contour the drawer's disclosure
    names. None
    of them is ink, so none may sit in `PRINT_INK`, whose members must clear
    4.5:1: a reference rule that did would compete with the data.
    """
    screen = _top_level_tokens(_object_literal(
        (STATIC / "js" / "scale.js").read_text(encoding="utf-8"), "const SCREEN = {",
    ))
    tokens_js = (EXPORT_JS / "tokens.js").read_text(encoding="utf-8")
    printed = _top_level_tokens(_object_literal(tokens_js, "export const PRINT_TOKENS = {"))
    ink = _top_level_tokens(_object_literal(tokens_js, "export const PRINT_INK = {"))

    for token in FLOOR_TOKENS:
        assert token in screen, f"screen theme lacks {token}"
        assert token in printed, f"print tokens lack {token}"
        assert token not in ink, f"{token} is chrome, not ink, and must stay out of PRINT_INK"

    assert re.fullmatch(r"'#[0-9a-fA-F]{6}'", printed["separationRule"]), (
        "the print separation rule must be an opaque #rrggbb"
    )
    assert float(printed["floorFadeDecades"]) == 0, "print must draw a hard floor contour"
    assert float(screen["floorFadeDecades"]) > 0, "the screen floor must fade"
    assert float(printed["anchorOpacity"]) == 1


def test_print_type_clears_the_nine_point_floor():
    """Nine points is 12 logical px under the 96 DPI authoring convention.

    Carrying the screen's 9-10 px sizes into an 85 mm figure would print them at
    under 7 pt, which is the requirement's own failure case. The conversion is
    asserted rather than trusted because it is the counter-intuitive half of the
    design: print type is *larger* in pixels than screen type, not smaller.
    """
    source = (EXPORT_JS / "tokens.js").read_text(encoding="utf-8")
    assert "MIN_PT = 9" in source.replace(" ", " ")
    for token in ("fontSmall", "fontLabel", "fontTip"):
        assert re.search(rf"{token}: MIN_PT \* PT_TO_PX", source), token
    # 9 pt * 96/72 = 12 px.
    assert (96 / 72) * 9 == pytest.approx(12.0)


def test_raster_multiplier_lands_on_300_dpi():
    source = (EXPORT_JS / "tokens.js").read_text(encoding="utf-8")
    assert "PX_RATIO = 300 / 96" in source
    assert 300 / 96 == pytest.approx(3.125)
    # 85 mm and 175 mm at 96 DPI, times the multiplier, are the figure widths
    # the request specifies.
    assert round(85 * 96 / 25.4) == 321
    assert round(321 * 300 / 96) == pytest.approx(1003, abs=2)
    assert round(175 * 96 / 25.4) == 661
    assert round(661 * 300 / 96) == pytest.approx(2066, abs=2)


# ------------------------------------------------------------- the markup --


def test_every_panel_offers_an_export_control():
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    for panel_id in PANEL_IDS:
        assert f'data-export="{panel_id}"' in markup, panel_id


def test_export_controls_live_in_the_card_toolbars():
    """Beside Auto-fit RoI and Reset, not floating over the plot."""
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    for block in re.findall(
        r'<span class="card-actions">(.*?)</span>\s*</h2>', markup, re.DOTALL
    ):
        assert "data-export=" in block, "a card toolbar carries no export control"


def test_export_is_wired_by_attribute_not_by_id():
    """Delegation keeps the id audit honest.

    `test_every_id_the_scripts_write_to_exists_in_the_markup` compares the ids
    the scripts touch against the markup. The export menu builds its dropdown at
    runtime, so addressing it by id would either fail that test or force a
    placeholder element into the page for no reason.
    """
    source = (EXPORT_JS / "menu.js").read_text(encoding="utf-8")
    assert "[data-export]" in source
    assert "getElementById" not in source


# ----------------------------------------------------------- the stamping --


@pytest.mark.parametrize(
    "path",
    [
        "/static/js/export/figure.js",
        "/static/js/export/menu.js",
        "/static/js/export/caption.js",
        "/static/js/export/disclosure.js",
        "/static/js/textfit.js",
        "/static/js/panels/marks.js",
        "/static/js/panels/canonical_overlays.js",
        "/static/js/panels/tooltip.js",
        "/static/js/frame_views.js",
        "/static/js/format.js",
        "/static/js/axis_symbols.js",
        "/static/js/panel_notes.js",
        "/static/js/shell.js",
        "/static/js/panels/frame_grid.js",
        "/static/js/event_inspector.js",
        "/static/js/capabilities.js",
        "/static/js/page_common.js",
        "/static/js/lazy_cards.js",
        "/static/js/physics_section.js",
        "/static/js/controls/filter_block.js",
        "/static/js/models_main.js",
        "/static/js/models_cards.js",
    ],
)
def test_new_modules_are_served(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize(
    "path",
    [
        "/static/js/export/figure.js",
        "/static/js/export/menu.js",
        "/static/js/export/caption.js",
        "/static/js/export/disclosure.js",
        "/static/js/panels/canonical_overlays.js",
        "/static/js/panels/tooltip.js",
        "/static/js/frame_views.js",
        "/static/js/panel_notes.js",
        "/static/js/labels.js",
        "/static/js/panels/frame_grid.js",
        "/static/js/event_inspector.js",
        "/static/js/capabilities.js",
        "/static/js/page_common.js",
        "/static/js/physics_section.js",
        "/static/js/controls/filter_block.js",
        "/static/js/models_main.js",
        "/static/js/models_cards.js",
    ],
)
def test_new_module_imports_are_stamped(client, path):
    """A new module must join the graph, not sit beside it.

    An unstamped specifier is cached independently of everything else, which is
    the exact failure mode commit a0e00c3 exists to prevent: a fresh entry point
    importing a module the browser has been holding since before the feature.

    `textfit.js`, `panels/marks.js`, `axis_symbols.js` and `shell.js` are
    deliberately absent from this list - they are leaves with no imports of
    their own, so there is nothing in them to stamp. They are reached, and
    therefore versioned, through their importers.
    """
    response = client.get(path)
    specifiers = re.findall(r"from\s+'(\.\.?/[^']+)'", response.text)
    assert specifiers, f"{path} should import sibling modules"
    for spec in specifiers:
        assert "?v=" in spec, f"unstamped module specifier in {path}: {spec}"


def test_the_export_directory_is_reached_from_the_entry_point_graph(client):
    """One stamp must govern the path from main.js into export/.

    Walks the served graph rather than the files on disk, so a module that is
    served unstamped - because it sits under a skipped path, say - is caught
    even though the import specifier on disk looks correct.
    """
    served = client.get("/static/js/main.js").text
    assert "./export/menu.js?v=" in served

    menu = client.get("/static/js/export/menu.js").text
    assert "./figure.js?v=" in menu
    assert "./tokens.js?v=" in menu

    figure = client.get("/static/js/export/figure.js").text
    assert "../scale.js?v=" in figure
    assert "../decode.js?v=" in figure


def test_the_new_panel_modules_are_stamped_through_projection(client):
    """The overlay modules are imported by projection.js under the same stamp."""
    projection = client.get("/static/js/panels/projection.js").text
    assert "./marks.js?v=" in projection
    assert "./canonical_overlays.js?v=" in projection
    assert "./tooltip.js?v=" in projection
    energy = client.get("/static/js/panels/energy.js").text
    assert "./tooltip.js?v=" in energy


def test_export_modules_are_reachable_from_the_entry_point():
    """An orphaned module is dead code that still ships.

    Walks the real import graph from main.js rather than asserting a file list,
    so a module that stops being imported is caught even though it still exists.
    """
    js_root = STATIC / "js"
    pattern = re.compile(
        r"""(?:\bfrom\s*|\bimport\s*\(?\s*)(['"])(\.{1,2}/[^'"?]+?\.js)\1"""
    )

    seen: set[Path] = set()

    def walk(path: Path) -> None:
        if path in seen:
            return
        seen.add(path)
        for _, spec in pattern.findall(path.read_text(encoding="utf-8")):
            target = (path.parent / spec).resolve()
            assert target.is_file(), f"{path.name} imports missing {spec}"
            walk(target)

    walk((js_root / "main.js").resolve())

    for module in EXPORT_JS.glob("*.js"):
        assert module.resolve() in seen, f"{module.name} is never imported"
    assert (js_root / "textfit.js").resolve() in seen
    for module in ("marks.js", "canonical_overlays.js", "tooltip.js", "frame_grid.js"):
        assert (PANELS_JS / module).resolve() in seen, f"panels/{module} is never imported"
    for module in ("frame_views.js", "format.js", "axis_symbols.js", "labels.js",
                   "panel_notes.js", "shell.js", "event_inspector.js", "capabilities.js",
                   "page_common.js", "lazy_cards.js", "physics_section.js", "controls/filter_block.js"):
        assert (js_root / module).resolve() in seen, f"{module} is never imported"


# ------------------------------------------------ the plot-only figure --


def _js_sources():
    """Every non-vendor script under static/js, as (path, raw text)."""
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in sorted((STATIC / "js").rglob("*.js"))
        if "vendor" not in path.parts
    ]


def test_no_disclosure_group_is_spliced_into_any_export():
    """The figure is the plot: nothing names, builds or splices a disclosure band.

    The earlier export laid out a caption band and inserted it before `</svg>`
    as `<g id="figure-disclosure">`. By directive the figure now carries no
    caption; the disclosures live in the panel's Details drawer instead.
    """
    for path, source in _js_sources():
        assert "figure-disclosure" not in source, f"{path.name} still names the disclosure band"
    figure = _strip_comments((EXPORT_JS / "figure.js").read_text(encoding="utf-8"))
    assert "</svg>" not in figure, "figure.js still post-processes the SVG at its closing tag"
    assert "captionToSvg" not in figure


def test_the_exported_figure_is_strictly_the_plot_canvas():
    """Plot area, axes, overlays and the colour-scale legend; no reserved height.

    The bare word `caption` is not forbidden, because figure.js keeps
    `import { displayOf } from './caption.js'` for the file name; what must be
    gone is every caption-building symbol and every reservation of room below
    the plot.
    """
    figure = _strip_comments((EXPORT_JS / "figure.js").read_text(encoding="utf-8"))
    for token in ("buildCaption", "captionToSvg", "offsetCaption", "spliceCaption",
                  "caption.height", "reservedBottom", "fitTableRows", "describeSelection",
                  "graphic"):
        assert token not in figure, f"figure.js still carries {token}"
    assert "panel.exportMetrics(width)" in figure
    assert re.search(r"chart\.resize\(\{ width, height: metrics\.height \}\)", figure)
    assert re.search(r"host\.style\.height = `\$\{metrics\.height\}px`", figure)
    assert re.search(r"buildPrintOption\(panel, metrics\)", figure)
    assert re.search(r"new Blob\(\[sharpenRasterHints\(serialized\)\]", figure)
    assert "getDataURL(" in figure and "pixelRatio: PX_RATIO" in figure
    assert "backgroundColor: THEME.chartBackground" in figure
    build = re.search(r"function buildPrintOption\(.*?\n\}\n", figure, re.DOTALL)
    assert build, "buildPrintOption not found"
    assert "reservedBottom" not in build.group(0) and "graphic" not in build.group(0)


def test_the_caption_module_keeps_only_provenance_and_the_display_descriptor():
    """caption.js names the selection and the display; it draws nothing."""
    stripped = _strip_comments((EXPORT_JS / "caption.js").read_text(encoding="utf-8"))
    exported = set(re.findall(r"export function (\w+)", stripped))
    assert exported == {"describeSelection", "describeView", "displayOf", "kernelPhrase"}
    for token in ("textfit", "THEME", "<g", "dominant-baseline"):
        assert token not in stripped, f"caption.js still carries {token}"
    assert re.search(r"from\s+'\.\./scale\.js'", stripped), "caption.js must keep a stamped sibling import"


def test_export_menu_passes_only_the_figure_geometry_and_meta():
    source = _strip_comments((EXPORT_JS / "menu.js").read_text(encoding="utf-8"))
    call = re.search(r"exportPanel\(target\.panel, \{(.*?)\}\);", source, re.DOTALL)
    assert call, "menu.js no longer calls exportPanel"
    body = call.group(1)
    for token in ("panelId", "format: choice.format", "widthMm: choice.widthMm",
                  "meta: target.meta", "state"):
        assert token in body, token
    for token in ("footnote", "disclosure", "title:", "frame:", "selection:", "experiment"):
        assert token not in body, f"menu.js still forwards {token}"
    assert "getExperiment" not in source


def test_the_export_resolver_hands_over_no_page_text():
    """main.js resolves a panel and its response meta; it scrapes nothing off the page."""
    source = _strip_comments((STATIC / "js" / "main.js").read_text(encoding="utf-8"))
    block = re.search(r"attachExportMenus\(\{.*?\n\}\);", source, re.DOTALL)
    assert block, "attachExportMenus block not found"
    body = block.group(0)
    assert "meta:" in body
    for token in ("getElementById", "textContent", "figureDisclosure(", "exportLegend(",
                  "footnote", "disclosure"):
        assert token not in body, f"the export resolver still touches {token}"


def test_the_models_export_resolver_hands_over_no_page_text():
    """models_main.js resolves a card's panel and its response meta, as main.js does."""
    source = _strip_comments((STATIC / "js" / "models_main.js").read_text(encoding="utf-8"))
    block = re.search(r"attachExportMenus\(\{.*?\n  \}\);", source, re.DOTALL)
    assert block, "attachExportMenus block not found"
    body = block.group(0)
    assert "exportTarget(panelId)" in body
    for token in ("getElementById", "textContent", "figureDisclosure(", "exportLegend(",
                  "footnote", "disclosure"):
        assert token not in body, f"the export resolver still touches {token}"
    cards = _strip_comments((STATIC / "js" / "models_cards.js").read_text(encoding="utf-8"))
    assert "return { panel: record.panel, meta: exportMeta(record.payload) };" in cards


def test_the_export_menu_is_reached_from_the_models_entry_point(client):
    """One stamp governs the Models page's path into export/ too."""
    served = client.get("/static/js/models_main.js").text
    assert "./export/menu.js?v=" in served
    assert "./models_cards.js?v=" in served and "./voxel_views.js?v=" in served
    cards = client.get("/static/js/models_cards.js").text
    for spec in re.findall(r"import\('(\.\.?/[^']+)'\)", cards):
        assert "?v=" in spec, f"unstamped dynamic import: {spec}"


def test_export_controls_say_the_figure_is_plot_only():
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    titles = re.findall(r'<button class="mini" data-export="\w+"[^>]*title="([^"]*)"', markup)
    assert len(titles) == len(PANEL_IDS)
    for title in titles:
        assert "plot area only" in title


def test_disclosure_is_structural_not_scraped():
    """The disclosure module reads the payload, never the page.

    Its sentences feed the Details drawer (panel_notes.js) beside the prose the
    reader saw. Reaching into the DOM would make it a second copy of that
    prose, and it must import from scale.js so it sits inside the stamped graph.
    """
    source = _strip_comments((EXPORT_JS / "disclosure.js").read_text(encoding="utf-8"))
    for forbidden in ("getElementById", "querySelector", "textContent", "innerText", "document."):
        assert forbidden not in source, f"disclosure.js touches the DOM: {forbidden}"
    assert re.search(r"import\s*\{[^}]*\bformatSci\b[^}]*\}\s*from\s*'\.\./scale\.js'", source)
    assert re.search(r"import\s*\{[^}]*\bformatInt\b[^}]*\}\s*from\s*'\.\./scale\.js'", source)
    assert re.search(r"export function figureDisclosure\s*\(", source)


def test_filename_carries_the_frame_token():
    source = _strip_comments((EXPORT_JS / "filename.js").read_text(encoding="utf-8"))
    assert re.search(r"state\.get\('frame'\) === 'canonical'", source)
    assert "'canonical'" in source


def test_export_modules_avoid_the_vendor_path():
    """Anything under a `vendor` path is served byte-identical and unrewritten.

    Project code placed there would silently drop out of the stamping graph.
    """
    assert "vendor" not in EXPORT_JS.parts
    for module in EXPORT_JS.glob("*.js"):
        assert "vendor" not in module.parts


# ------------------------------------------- canonical floor and overlays --


def test_visualmap_is_bound_to_the_raster_series():
    """Unbound, a visualMap recolours every series by its data value.

    That is how the lab frame's pink and blue centroid diamonds came out in the
    ramp's colours. The option must name the raster, series 0.
    """
    source = _strip_comments((STATIC / "js" / "scale.js").read_text(encoding="utf-8"))
    body = re.search(r"export function visualMap\s*\(.*?\n\}\n", source, re.DOTALL)
    assert body, "visualMap not found in scale.js"
    assert re.search(r"\bseriesIndex\b", body.group(0))
    projection = _strip_comments((PANELS_JS / "projection.js").read_text(encoding="utf-8"))
    assert re.search(r"seriesIndex:\s*0", projection)


def test_floor_fade_is_guarded_before_it_divides():
    """Guard 8b.1: a zero or non-finite fade width is a pure step, never NaN.

    Print sets the fade to 0. Dividing by it would write NaN alpha into the
    ImageData, which the canvas reads as 0 and paints the whole field clear.
    """
    source = _strip_comments((STATIC / "js" / "decode.js").read_text(encoding="utf-8"))
    body = re.search(r"export function codeTable\s*\(.*?\n\}\n", source, re.DOTALL)
    assert body, "codeTable not found in decode.js"
    text = body.group(0)
    guard = re.search(r"Number\.isFinite\(fadeDecades\)\s*&&\s*fadeDecades\s*>\s*0", text)
    division = text.find("/ fadeDecades")
    assert guard, "the fade width is not checked finite and positive"
    assert division > guard.start(), "the fade is divided by before it is checked"


def test_print_disclosure_names_the_hard_floor_contour():
    """Print draws a hard contour at the floor; the drawer says it is not a shower edge."""
    source = (EXPORT_JS / "disclosure.js").read_text(encoding="utf-8")
    assert "not a shower edge" in source


def test_custom_line_marks_clip_and_have_no_fill():
    """Both settings are load-bearing (see panels/marks.js).

    `clip: true` keeps a line inside a zoomed plot; `fill: 'none'` is what
    gives the stroke its ±2.5 px hover band instead of the 1 px default.
    """
    source = _strip_comments((PANELS_JS / "marks.js").read_text(encoding="utf-8"))
    assert re.search(r"clip:\s*true", source)
    assert re.search(r"fill:\s*'none'", source)


def test_open_markers_do_not_use_the_empty_symbols():
    """`emptyCircle` / `emptyDiamond` are filled white with a forced 2 px stroke."""
    source = _strip_comments((PANELS_JS / "canonical_overlays.js").read_text(encoding="utf-8"))
    assert "emptyCircle" not in source and "emptyDiamond" not in source
    assert re.search(r"color:\s*'transparent'", source)
    # The floating ⟨D_entry⟩ badge sat on the shower cores; it is gone.
    assert "markPoint" not in source


def test_print_raster_takes_one_pixel_per_payload_bin():
    """The exporter enlarges the raw payload bins by one factor on both axes.

    On screen ``renderRaster`` enlarges the canonical Native Grid uniformly and
    the Continuous Field's depth columns only (so the browser's bilinear
    upscale cannot interpolate between sampling layers). Print must not
    inherit either: it asks for one pixel per bin and applies its own integer
    nearest-neighbour factor to both axes.
    """
    decode = _strip_comments((STATIC / "js" / "decode.js").read_text(encoding="utf-8"))
    assert re.search(r"export function renderRaster\s*\([^)]*\{\s*screen\s*=\s*true\s*\}", decode)
    figure = _strip_comments((EXPORT_JS / "figure.js").read_text(encoding="utf-8"))
    assert re.search(r"renderRaster\([^)]*\{\s*screen:\s*false\s*\}\s*\)", figure)


# ------------------------------------------------------ tooltip placement --


def test_every_chart_tooltip_is_mounted_on_the_layer_and_placed_by_one_module():
    """Both chart builders take their tooltip from the one option.

    The tooltip was clipped by `.main`'s overflow box, not stacked under the
    sidebar. Mounted on the fixed `#tooltip-layer` nothing clips it, and it is
    not confined, so an explanation can leave the plot it explains. One
    builder and one placement module mean the projection and energy charts
    cannot drift apart again.
    """
    tooltip = _strip_comments((PANELS_JS / "tooltip.js").read_text(encoding="utf-8"))
    assert re.search(r"TOOLTIP_LAYER\s*=\s*'#tooltip-layer'", tooltip)
    assert re.search(r"appendTo:\s*TOOLTIP_LAYER", tooltip)
    assert re.search(r"confine:\s*false", tooltip)
    assert re.search(r"hideDelay:\s*0", tooltip)
    assert re.search(r"TOOLTIP_CLASS\s*=\s*'calo-tooltip'", tooltip)
    assert re.search(r"className:\s*TOOLTIP_CLASS", tooltip)
    for name in ("projection.js", "energy.js"):
        source = _strip_comments((PANELS_JS / name).read_text(encoding="utf-8"))
        assert "tooltip: tooltipOption(this.tooltipPosition)" in source, name
        assert "this.tooltipPosition = tooltipPosition(this.chart" in source, name
        assert "hideTooltipOnScroll(this.chart)" in source, name
    for path in (STATIC / "js").rglob("*.js"):
        if "vendor" in path.parts or path.name == "tooltip.js":
            continue
        text = path.read_text(encoding="utf-8")
        assert "rgba(22,27,34,0.95)" not in text, (
            f"{path.name} builds its own tooltip instead of tooltipOption()"
        )
        assert not re.search(r"confine:\s*true", _strip_comments(text)), (
            f"{path.name} confines a tooltip to its chart, over the plot it explains"
        )


def test_the_tooltip_layer_is_fixed_to_the_viewport_and_clips_nothing_else():
    """The layer exists once, outside `.main`, fixed and viewport-sized.

    `position: fixed` is what keeps a hidden tip - ECharts leaves it where it
    last stood - from growing the document after the window shrinks: a fixed
    box's contents never add to the page's scroll size.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count('id="tooltip-layer"') == 1
    main_start = html.index('<main class="main">')
    main_end = html.index("</main>")
    layer = html.index('id="tooltip-layer"')
    assert not main_start < layer < main_end, "the layer must sit outside .main's overflow box"
    assert layer < html.index("echarts.min.js"), "the layer must exist before any chart is created"
    css = (STATIC / "css" / "layout.css").read_text(encoding="utf-8")
    rule = re.search(r"\.tooltip-layer\s*\{([^}]*)\}", css)
    assert rule, "the .tooltip-layer rule is missing"
    body = rule.group(1)
    for decl in (r"position:\s*fixed", r"inset:\s*0", r"pointer-events:\s*none"):
        assert re.search(decl, body), decl
    assert not re.search(r"overflow:\s*(hidden|clip|auto|scroll)", body), "the layer must clip nothing"


def test_the_zrender_transform_cache_the_placement_resets_still_exists():
    """`resetPointerTransforms` clears an ECharts internal; an upgrade must be re-checked.

    zrender caches the client transforms of a chart's viewport root on
    `___zrEVENTSAVED` as `trans` and `invTrans`, validated against one shared
    `srcCoords`. If a new bundle renames them, the reset silently does nothing
    and a scroll can leave a tip drawn 120-240 px from where it was placed.
    """
    bundle = (STATIC / "js" / "vendor" / "echarts.min.js").read_text(encoding="utf-8")
    assert "___zrEVENTSAVED" in bundle
    assert re.search(r'"invTrans":"trans"', bundle) and "srcCoords" in bundle
    tooltip = _strip_comments((PANELS_JS / "tooltip.js").read_text(encoding="utf-8"))
    reset = re.search(r"export function resetPointerTransforms.*?\n\}", tooltip, re.DOTALL)
    assert reset, "resetPointerTransforms is missing"
    for key in ("___zrEVENTSAVED", "srcCoords", "trans", "invTrans"):
        assert key in reset.group(0), key
    position = re.search(r"export function tooltipPosition.*?\n\}", tooltip, re.DOTALL)
    assert position and "resetPointerTransforms(chart)" in position.group(0)


def test_the_live_grid_is_recorded_outside_build_option():
    """`buildOption` also runs at print geometry for the exporter.

    The plot box the tooltip is kept off must come from the option on screen,
    so it is recorded where the live option is set, never inside `buildOption`.
    """
    for name in ("projection.js", "energy.js"):
        source = _strip_comments((PANELS_JS / name).read_text(encoding="utf-8"))
        build = re.search(r"\n  buildOption\(.*?\n  \}\n", source, re.DOTALL)
        assert build, name
        assert "liveGrid" not in build.group(0), name
        assert re.search(r"this\.liveGrid = option\.grid", source), name
    projection = _strip_comments((PANELS_JS / "projection.js").read_text(encoding="utf-8"))
    # Every full re-render goes through setLiveOption, which records the grid.
    assert "notMerge: true" in re.search(r"setLiveOption\(option\) \{.*?\n  \}", projection, re.DOTALL).group(0)
    assert projection.count("notMerge: true") == 1


def test_the_bin_readout_positions_through_its_tooltip_option():
    """ECharts ignores a top-level `position` on a manual showTip (measured on 5.5.1).

    The plain readout stays at the pointer; once an overlay's explanation leads
    it, the tip leaves the chart like every other explanation.
    """
    source = _strip_comments((PANELS_JS / "projection.js").read_text(encoding="utf-8"))
    assert "this.readoutPosition = tooltipPosition(this.chart, plotBox, { prefer: PREFER_POINTER })" in source
    dispatch = re.search(r"type:\s*'showTip'.*?\}\)", source, re.DOTALL)
    assert dispatch, "the manual showTip dispatch is missing"
    body = dispatch.group(0)
    assert re.search(r"position:\s*overlay \? this\.tooltipPosition : this\.readoutPosition", body)
    outside = re.sub(r"tooltip:\s*\{.*\}", "", body, flags=re.DOTALL)
    assert "position:" not in outside, "a top-level position is dead on this code path"


def test_no_tooltip_stacking_rule_ships():
    """No z-index rule on the tip itself: it cannot escape an overflow clip.

    The tip is moved out of the clip onto `#tooltip-layer` instead, and the
    only z-index involved is the layer's own.
    """
    for path in (STATIC / "css").glob("*.css"):
        text = path.read_text(encoding="utf-8")
        assert "echarts-tooltip" not in text, path.name
        assert "99999" not in text, path.name
    controls = (STATIC / "css" / "controls.css").read_text(encoding="utf-8")
    assert "`.main` is\n   a scroll container" in controls


# ------------------------------------------- frames, channels and wording --


def test_the_reference_frame_control_opens_in_the_absolute_frame():
    """Two tiers, one stored key: Absolute checked, Translated the sub-default.

    The primary radios name the view, the nested radios the sub-frame; no
    radio named `frame` remains, and the legacy per-shower sub-option ships
    hidden, to be revealed only while a link or a saved default holds the
    frame on it (main.js `syncFrameControl`).
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    views = re.findall(r'<input type="radio" name="frame-view" value="(\w+)"( checked)?', html)
    assert [v for v, _ in views] == ["absolute", "aligned"]
    assert [v for v, c in views if c] == ["absolute"]
    subs = re.findall(r'<input type="radio" name="frame-sub" value="(\w+)"( checked)?', html)
    assert [v for v, _ in subs] == ["canonical", "local", "trans"]
    assert [v for v, c in subs if c] == ["canonical"]
    assert 'name="frame"' not in html
    assert re.search(r'<fieldset class="choice-sub" id="frame-sub"[^>]*\shidden(?:\s|>)', html)
    assert '<label class="choice" id="frame-sub-trans" hidden' in html
    assert 'id="ctl-frame"' in html and 'data-frame="lab"' in html
    displays = re.findall(r'<input type="radio" name="display" value="(\w+)"( checked)?', html)
    assert [v for v, c in displays if c] == ["native"]
    channels = re.findall(r'<input type="radio" name="channel" value="(\w+)"', html)
    assert channels == ["density", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy"]
    assert 'id="colormap-hint"' in html


def test_no_retired_schema_wording_ships():
    retired = ("29-column", "no predicted angle", "No predicted-angle", "A+B = 8.6",
               "particle_origin = 'A+B'", "Shared voxels", "shared_voxel_fraction")
    sources = [STATIC / "index.html", STATIC / "models.html"] + [
        path for path in (STATIC / "js").rglob("*.js") if "vendor" not in path.parts
    ]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for phrase in retired:
            assert phrase not in text, f"{path.name} still says {phrase!r}"


def test_puor_anchors_are_the_colorbrewer_values():
    source = (STATIC / "js" / "palette.js").read_text(encoding="utf-8")
    anchors = ("[127, 59, 8], [179, 88, 6], [224, 130, 20], [253, 184, 99], [254, 224, 182],\n"
               "  [247, 247, 247], [216, 218, 235], [178, 171, 210], [128, 115, 172], [84, 39, 136],\n"
               "  [45, 0, 75]")
    assert anchors in source


def test_filename_names_frame_channel_and_model():
    source = (EXPORT_JS / "filename.js").read_text(encoding="utf-8")
    assert "else if (frame && frame !== 'lab') tokens.push(frame);" in source
    assert "shapcam_energy: 'shapcamE'" in source and "segmentation: 'seg'" in source
    assert "apiFrame(state.get('frame')).coord_system" in source


def test_disclosure_covers_every_frame_kind():
    source = (EXPORT_JS / "disclosure.js").read_text(encoding="utf-8")
    for phrase in ("Per-shower translated frame (legacy):", "Separation-Aligned (D-Frame), Local",
                   "Separation-Aligned (D-Frame), Translated", "not a separation", "by construction",
                   "box overlap", "rotated with their shower", "written D on the entry panel"):
        assert phrase in source, phrase


def test_no_retired_frame_vocabulary_ships():
    """Laboratory → Absolute and Canonical → Separation-Aligned, everywhere a reader looks."""
    retired = ("Laboratory", "laboratory frame", "laboratory 3-D", "laboratory (absolute)",
               "Canonical centre-of-separation", "centre-of-separation frame")
    js = STATIC / "js"
    sources = [STATIC / "index.html", STATIC / "models.html", js / "labels.js", js / "frame_views.js", js / "main.js",
               js / "models_main.js", js / "models_cards.js", js / "capabilities.js",
               PANELS_JS / "projection.js", PANELS_JS / "canonical_overlays.js",
               EXPORT_JS / "disclosure.js", EXPORT_JS / "caption.js", js / "controls" / "admin.js"]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        text = (re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL) if path.suffix == ".html"
                else _strip_comments(text))
        for phrase in retired:
            assert phrase not in text, f"{path.name} still says {phrase!r}"


def test_the_physics_panels_load_through_stamped_dynamic_imports(client):
    """physics_section.js fetches each panel module on first use, under the page's stamp.

    A dynamic `import('./panels/profile.js')` is requested at a bare URL of
    its own like any static one, so it must carry the stamp too, or a fresh
    page could pair with a panel module cached before it.
    """
    served = client.get("/static/js/physics_section.js").text
    dynamic = re.findall(r"import\('(\.\.?/[^']+)'\)", served)
    assert len(dynamic) == 6, dynamic
    for spec in dynamic:
        assert "?v=" in spec, f"unstamped dynamic import: {spec}"
    main = client.get("/static/js/main.js").text
    assert "./physics_section.js?v=" in main and "./capabilities.js?v=" in main
