"""The shared range-input style, read as text (legend-sliders, 2026-11-17).

Every range input's unfilled track was the browser's grey, 1.44:1 on the dark
card and 1.15:1 on white, under the 3:1 a mark a reader must see clears
(CLAUDE.md section 2). One style now draws every single slider: a track in the
``--range-track`` token and the dual sliders' thumb, in controls.css, which all
three pages load. The dual sliders keep their own track, fill and thumbs; only
their track's colour moves to the token.
"""

from __future__ import annotations

import re

from test_theme_css import CSS, _block, _dark, _light, _read, _strip_comments, contrast

HTML_PAGES = [CSS.parent / name for name in ("index.html", "models.html", "methodology.html")]
GROUNDS = ("--card", "--canvas", "--canvas-alt")
SINGLE = 'input[type="range"]:not(.dual input)'


def _rule(source: str, selector: str) -> str:
    return _block(_strip_comments(source), selector + " {")


def _rules(source: str) -> list[tuple[str, str]]:
    """(selector list, body) of every innermost rule, comments stripped."""
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _strip_comments(source))]


def test_track_token_values_and_contrast_in_both_themes():
    assert _dark()["--range-track"] == "#6e7681"
    assert _light()["--range-track"] == "#818b98"
    for tokens in (_dark(), _light()):
        for ground in GROUNDS:
            assert contrast(tokens["--range-track"], tokens[ground]) >= 3.0, ground
        # The thumb's disc, on the card it sits on.
        assert contrast(tokens["--text"], tokens["--card"]) >= 3.0


def test_controls_carries_the_shared_rule_for_both_engines():
    c = _read("controls.css")
    base = _rule(c, SINGLE)
    assert "appearance: none" in base and "background: transparent" in base
    for sel in (f"{SINGLE}::-webkit-slider-runnable-track", f"{SINGLE}::-moz-range-track"):
        body = _rule(c, sel)
        assert "var(--range-track)" in body and "height: 4px" in body and "border-radius: 2px" in body
    for sel in (f"{SINGLE}::-webkit-slider-thumb", f"{SINGLE}::-moz-range-thumb"):
        body = _rule(c, sel)
        assert "var(--text)" in body and "var(--accent)" in body and "14px" in body
    assert "transparent" in _rule(c, f"{SINGLE}::-moz-range-progress")
    assert "2px solid var(--accent)" in _rule(c, f"{SINGLE}:focus-visible")
    # appearance: none removes the engine's disabled look, so the shared rule states one.
    assert "opacity: 0.6" in _rule(c, f"{SINGLE}:disabled")


def test_no_selector_list_mixes_the_two_engines_pseudo_elements():
    """An engine drops a whole rule whose selector list holds a pseudo-element it does not know."""
    for sheet in CSS.glob("*.css"):
        for selectors, _body in _rules(sheet.read_text(encoding="utf-8")):
            assert not ("::-webkit-" in selectors and "::-moz-" in selectors), (sheet.name, selectors)


def test_the_dual_sliders_keep_their_geometry_and_take_the_token():
    c = _read("controls.css")
    assert re.search(r"\.dual \.track \{[^}]*background: var\(--range-track\)", _strip_comments(c))
    assert re.search(r"\.dual \.fill \{[^}]*background: var\(--accent\)", _strip_comments(c))
    dual = _rule(c, '.dual input[type="range"]')
    assert "height: 22px" in dual and "pointer-events: none" in dual
    # No dual-specific track rule and no thumb offset: the shared rules never reach a dual input.
    for selectors, body in _rules(c):
        if selectors.startswith(".dual input") and "-slider-thumb" in selectors:
            assert "margin-top" not in body, selectors
        if selectors.startswith(".dual") and ("runnable-track" in selectors or "range-track" in selectors):
            raise AssertionError(f"a dual track rule: {selectors}")
    for selectors, _body in _rules(c):
        if selectors.startswith('input[type="range"]'):
            assert selectors.startswith(SINGLE), selectors


def test_the_dual_fill_stands_proud_of_the_track_against_the_ground():
    """Review R-M1: the accent fill of the selected interval and --range-track are only about 1.8:1 apart, and no
    track colour can clear 3:1 on the card and 3:1 from the accent at once. So the fill is 2 px taller than the
    track and centred on it: its edges stand against the sidebar's ground, where the accent clears 3:1."""
    c = _strip_comments(_read("controls.css"))
    shared = re.search(r"\.dual \.track,\s*\.dual \.fill \{([^}]*)\}", c).group(1)
    # The fill's own rule, not the selector list it shares with the track.
    fill = re.search(r"(?m)(?<!,\n)^\.dual \.fill \{([^}]*)\}", c).group(1)
    px = lambda body, prop: float(re.search(rf"{prop}:\s*([\d.]+)px", body).group(1))  # noqa: E731
    track_top, track_h = px(shared, "top"), px(shared, "height")
    fill_top, fill_h = px(fill, "top"), px(fill, "height")
    assert fill_h == track_h + 2 and fill_top == track_top - 1, (fill, shared)
    assert fill_top + fill_h / 2 == track_top + track_h / 2
    for tokens in (_dark(), _light()):
        assert contrast(tokens["--accent"], tokens["--canvas-alt"]) >= 3.0
        # The fill against the track: under 3:1, which is why the fill's edges must face the ground.
        assert contrast(tokens["--accent"], tokens["--range-track"]) < 3.0


def test_no_accent_color_on_a_range_input():
    for sheet in CSS.glob("*.css"):
        for selectors, body in _rules(sheet.read_text(encoding="utf-8")):
            if "accent-color" in body:
                assert "range" not in selectors and "mini-range-input" not in selectors, (sheet.name, selectors)
    for page in HTML_PAGES:
        for tag in re.findall(r"<input[^>]*type=\"range\"[^>]*>", page.read_text(encoding="utf-8")):
            assert "accent-color" not in tag, (page.name, tag)
