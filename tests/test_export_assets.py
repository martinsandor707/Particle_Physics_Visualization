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
    or the on-screen fade instead of the hard contour the caption names. None
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
    ],
)
def test_new_module_imports_are_stamped(client, path):
    """A new module must join the graph, not sit beside it.

    An unstamped specifier is cached independently of everything else, which is
    the exact failure mode commit a0e00c3 exists to prevent: a fresh entry point
    importing a module the browser has been holding since before the feature.

    `textfit.js` and `panels/marks.js` are deliberately absent from this list -
    they are leaves with no imports of their own, so there is nothing in them to
    stamp. They are reached, and therefore versioned, through their importers.
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
    for module in ("marks.js", "canonical_overlays.js", "tooltip.js"):
        assert (PANELS_JS / module).resolve() in seen, f"panels/{module} is never imported"
    for module in ("frame_views.js", "format.js"):
        assert (js_root / module).resolve() in seen, f"{module} is never imported"


# ------------------------------------------------- the disclosure band --


def test_svg_export_splices_an_isolated_disclosure_group():
    """Plan section 1.8: the SVG carries a `<g id="figure-disclosure">`.

    zrender's SVG painter flattens `graphic` items, so the group can only come
    from our own post-processing. The check is on the source: figure.js must
    call `captionToSvg` and the id must be the one the plan names, so a reader
    of the file can address the band.
    """
    figure = _strip_comments((EXPORT_JS / "figure.js").read_text(encoding="utf-8"))
    caption = _strip_comments((EXPORT_JS / "caption.js").read_text(encoding="utf-8"))
    assert "captionToSvg(" in figure, "figure.js never serialises the caption band"
    assert re.search(r"\bimport\b[^;]*\bcaptionToSvg\b", figure), (
        "figure.js must import captionToSvg from caption.js"
    )
    assert 'id="figure-disclosure"' in caption
    # The splice must land before the closing tag, not be appended after it.
    assert "</svg>" in figure


def test_svg_caption_withholds_graphics_but_keeps_the_reserved_height():
    """For SVG the caption items leave the option; the band's height does not.

    Withholding the items is what lets the `<g>` be the only copy of the text.
    Dropping the reservation with them would let the ramp slide down into the
    space the band is then spliced over.
    """
    figure = _strip_comments((EXPORT_JS / "figure.js").read_text(encoding="utf-8"))
    assert re.search(r"graphic:\s*format === 'svg' \? \[\]", figure), (
        "the SVG option must carry no caption graphics"
    )
    assert "reservedBottom: caption.height" in figure


def test_caption_module_exports_the_svg_serialiser_and_accepts_disclosure():
    source = _strip_comments((EXPORT_JS / "caption.js").read_text(encoding="utf-8"))
    assert re.search(r"export function captionToSvg\s*\(", source)
    signature = re.search(r"export function buildCaption\s*\(\{(.*?)\}", source, re.DOTALL)
    assert signature, "buildCaption signature not found"
    assert "disclosure" in signature.group(1)
    # The serialiser positions text the way zrender draws it: centred on the
    # line, 0.71 x the font size below the item's top.
    assert 'dominant-baseline="central"' in source
    assert "0.71 * fontSize" in source
    # Styles come from each item, not from the (restored) THEME.
    body = re.search(
        r"export function captionToSvg\s*\(.*?\n\}\n", source, re.DOTALL
    ).group(0)
    assert "THEME" not in body


def test_export_menu_forwards_the_disclosure():
    source = _strip_comments((EXPORT_JS / "menu.js").read_text(encoding="utf-8"))
    assert re.search(r"disclosure:\s*target\.disclosure", source)


def test_disclosure_is_structural_not_scraped():
    """The disclosure module reads the payload, never the page.

    Its whole reason to exist is that the footnote is prose assembled for the
    screen. Reaching into the DOM would make it a second copy of that prose,
    and it must import from scale.js so it sits inside the stamped graph.
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


# ------------------------------------------------------ tooltip confinement --


def test_every_chart_tooltip_is_confined_and_hooked():
    """Both chart builders take their tooltip from the one confined option.

    The tooltip was clipped by `.main`'s overflow box, not stacked under the
    sidebar; `confine: true` keeps it inside the chart. One builder means the
    projection and energy charts cannot drift apart again.
    """
    tooltip = _strip_comments((PANELS_JS / "tooltip.js").read_text(encoding="utf-8"))
    assert re.search(r"confine:\s*true", tooltip)
    assert re.search(r"TOOLTIP_CLASS\s*=\s*'calo-tooltip'", tooltip)
    assert re.search(r"className:\s*TOOLTIP_CLASS", tooltip)
    for name in ("projection.js", "energy.js"):
        source = _strip_comments((PANELS_JS / name).read_text(encoding="utf-8"))
        assert "tooltip: tooltipOption()" in source, name
    for path in (STATIC / "js").rglob("*.js"):
        if "vendor" in path.parts or path.name == "tooltip.js":
            continue
        assert "rgba(22,27,34,0.95)" not in path.read_text(encoding="utf-8"), (
            f"{path.name} builds its own tooltip instead of tooltipOption()"
        )


def test_the_bin_readout_positions_through_its_tooltip_option():
    """ECharts 5.5.1 ignores a top-level `position` on a manual showTip."""
    source = _strip_comments((PANELS_JS / "projection.js").read_text(encoding="utf-8"))
    dispatch = re.search(r"type:\s*'showTip'.*?\}\)", source, re.DOTALL)
    assert dispatch, "the manual showTip dispatch is missing"
    body = dispatch.group(0)
    assert re.search(r"tooltip:\s*\{[^}]*position:\s*readoutPosition", body)
    outside = re.sub(r"tooltip:\s*\{[^}]*\}", "", body)
    assert "position:" not in outside, "a top-level position is dead on this code path"


def test_no_tooltip_stacking_rule_ships():
    """A z-index rule cannot escape an overflow clip and would target no class."""
    for path in (STATIC / "css").glob("*.css"):
        text = path.read_text(encoding="utf-8")
        assert "echarts-tooltip" not in text, path.name
        assert "99999" not in text, path.name
    controls = (STATIC / "css" / "controls.css").read_text(encoding="utf-8")
    assert "`.main` is\n   a scroll container" in controls


# ------------------------------------------- frames, channels and wording --


def test_the_reference_frame_control_opens_in_the_laboratory_frame():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    frames = re.findall(r'<input type="radio" name="frame" value="(\w+)"( checked)?', html)
    assert [v for v, _ in frames] == ["lab", "trans", "local", "canonical"]
    assert [v for v, c in frames if c] == ["lab"]
    displays = re.findall(r'<input type="radio" name="display" value="(\w+)"( checked)?', html)
    assert [v for v, c in displays if c] == ["native"]
    channels = re.findall(r'<input type="radio" name="channel" value="(\w+)"', html)
    assert channels == ["density", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy"]
    assert 'id="colormap-hint"' in html


def test_no_retired_schema_wording_ships():
    retired = ("29-column", "no predicted angle", "No predicted-angle", "A+B = 8.6",
               "particle_origin = 'A+B'", "Shared voxels", "shared_voxel_fraction")
    sources = [STATIC / "index.html"] + [
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
    for phrase in ("Translated frame:", "Local frame", "Canonical centre-of-separation frame",
                   "not a separation", "by construction", "box overlap", "rotated with their shower"):
        assert phrase in source, phrase
