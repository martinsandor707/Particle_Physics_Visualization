"""The light theme's stylesheet contract, read as text.

Dark is frozen: every token the dark ``:root`` block carries today, and the
eleven the light work added with the literals they replaced, are pinned
verbatim. The light block must restate exactly the colour tokens, inside
``@media screen`` (so methodology.css's print block keeps winning), and its
text roles must clear WCAG on the grounds they are drawn on. The rendering
rules are checked in a browser elsewhere; here is what the sheets state.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "calosrv" / "static" / "css"
SHEETS = ("tokens.css", "layout.css", "controls.css", "models.css", "methodology.css")

DARK = {
    "--canvas": "#0d1117",
    "--canvas-alt": "#161b22",
    "--card": "#1c2128",
    "--border": "#30363d",
    "--text": "#e6edf3",
    "--muted": "#8b949e",
    "--accent": "#58a6ff",
    "--warn": "#d29922",
    "--warn-bg": "rgba(210, 153, 34, 0.12)",
    "--danger": "#f85149",
    "--danger-bg": "rgba(248, 81, 73, 0.12)",
    "--ok": "#3fb950",
    "--shower-a": "#f778ba",
    "--shower-b": "#58a6ff",
    "--disabled": "#484f58",
    "--radius": "6px",
    "--gap": "14px",
    "--sidebar-width": "330px",
    "--inspector-width": "360px",
    "--mono": '"JetBrains Mono", "SF Mono", ui-monospace, "Cascadia Code", monospace',
    "--sans": '"Inter", "Segoe UI", system-ui, -apple-system, sans-serif',
    # Added with the light theme, each exactly the literal it replaced.
    "--control-bg": "#21262d",
    "--control-text": "#c9d1d9",
    "--control-hover": "#2d333b",
    "--on-accent": "#04101f",
    "--accent-ring": "rgba(88, 166, 255, 0.18)",
    "--accent-wash": "rgba(88, 166, 255, 0.15)",
    "--accent-wash-soft": "rgba(88, 166, 255, 0.12)",
    "--muted-wash": "rgba(139, 148, 158, 0.14)",
    "--muted-wash-soft": "rgba(139, 148, 158, 0.08)",
    "--shadow": "rgba(1, 4, 9, 0.6)",
    "--backdrop": "rgba(1, 4, 9, 0.78)",
}
NON_COLOUR = {"--radius", "--gap", "--sidebar-width", "--inspector-width", "--mono", "--sans"}
COLOUR_TOKENS = set(DARK) - NON_COLOUR

TEXT_ROLES = ("--text", "--muted", "--accent", "--warn", "--danger", "--ok", "--shower-a", "--shower-b")
GROUNDS = ("--card", "--canvas", "--canvas-alt")

COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")


def _read(name: str) -> str:
    return (CSS / name).read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def _block(source: str, opener: str) -> str:
    """The body of the first brace block opened by `opener`, nesting honoured."""
    start = source.index(opener) + len(opener)
    depth, i = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
    return source[start : i - 1]


def _declarations(body: str) -> dict[str, str]:
    return {
        name: " ".join(value.split())
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", _strip_comments(body))
    }


def _dark() -> dict[str, str]:
    return _declarations(_block(_read("tokens.css"), "\n:root {"))


def _light() -> dict[str, str]:
    media = _block(_read("tokens.css"), "@media screen {")
    return _declarations(_block(media, ':root[data-theme="light"] {'))


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ------------------------------------------------------------------ dark --


def test_dark_root_is_frozen():
    assert _dark() == {**DARK}


def test_dark_root_declares_color_scheme_dark():
    assert re.search(r"color-scheme:\s*dark;", _block(_read("tokens.css"), "\n:root {"))


# ----------------------------------------------------------------- light --


def test_light_block_is_inside_media_screen_and_sets_color_scheme():
    light = _block(_block(_read("tokens.css"), "@media screen {"), ':root[data-theme="light"] {')
    assert re.search(r"color-scheme:\s*light;", light)


def test_light_tokens_never_sit_outside_media_screen():
    for name in SHEETS:
        text = _strip_comments(_read(name))
        # Remove every @media screen block; a light selector may not remain
        # carrying a custom property.
        rest = text
        while "@media screen {" in rest:
            inner = _block(rest, "@media screen {")
            rest = rest.replace("@media screen {" + inner + "}", "", 1)
        for match in re.finditer(r':root\[data-theme="light"\]\s*\{', rest):
            assert "--" not in _block(rest[match.start() :], match.group(0)), name


def test_light_block_defines_exactly_the_dark_colour_tokens():
    assert set(_light()) == COLOUR_TOKENS


def test_light_text_roles_clear_4_5_on_every_ground():
    light = _light()
    for role in TEXT_ROLES:
        for ground in GROUNDS:
            ratio = contrast(light[role], light[ground])
            assert ratio >= 4.5, (role, ground, round(ratio, 2))


def test_light_control_and_accent_pairs():
    light = _light()
    for ground in ("--control-bg", "--control-hover"):
        assert contrast(light["--control-text"], light[ground]) >= 4.5, ground
    assert contrast(light["--on-accent"], light["--accent"]) >= 4.5


def test_light_border_is_a_quiet_line():
    ratio = contrast(_light()["--border"], _light()["--card"])
    assert 1.3 <= ratio <= 1.8, ratio


def test_dark_control_pairs_that_hold_today():
    """The dark control: pairs asserted only where they hold now.

    Every dark text role clears 4.5:1 on the card today. Not asserted:
    --disabled (a placeholder / disabled tone, not a text role), 1.95:1.
    """
    dark = _dark()
    assert contrast(dark["--control-text"], dark["--control-bg"]) >= 4.5
    assert contrast(dark["--control-text"], dark["--control-hover"]) >= 4.5
    assert contrast(dark["--on-accent"], dark["--accent"]) >= 4.5
    for role in TEXT_ROLES:
        ratio = contrast(dark[role], dark["--card"])
        if ratio >= 4.5:
            continue
        raise AssertionError((role, round(ratio, 2)))
    assert 1.2 <= contrast(dark["--border"], dark["--card"]) <= 1.5  # 1.33


def test_contrast_helper_matches_known_values():
    assert abs(contrast("#000000", "#ffffff") - 21.0) < 0.01
    assert abs(contrast("#767676", "#ffffff") - 4.54) < 0.02


# ------------------------------------------------------------- literals --


def _without_print(source: str) -> str:
    if "@media print {" not in source:
        return source
    inner = _block(source, "@media print {")
    return source.replace("@media print {" + inner + "}", "", 1)


def test_no_colour_literal_outside_tokens_and_print():
    for name in ("layout.css", "controls.css", "models.css", "methodology.css"):
        text = _strip_comments(_without_print(_read(name)))
        assert not COLOUR_LITERAL.findall(text), (name, COLOUR_LITERAL.findall(text))


def test_every_replaced_literal_is_now_a_var():
    controls = _read("controls.css") + _read("layout.css")
    for token in (
        "--control-bg", "--control-text", "--control-hover", "--on-accent", "--accent-ring",
        "--accent-wash", "--accent-wash-soft", "--muted-wash", "--muted-wash-soft",
        "--shadow", "--backdrop",
    ):
        assert f"var({token})" in controls, token


# --------------------------------------------------------------- toggle --


def test_toggle_icon_rules_exist():
    tokens = _strip_comments(_read("tokens.css"))
    assert ".theme-toggle .theme-icon-moon { display: none; }" in tokens
    assert ':root[data-theme="light"] .theme-toggle .theme-icon-sun { display: none; }' in tokens
    assert ':root[data-theme="light"] .theme-toggle .theme-icon-moon { display: inline; }' in tokens


# ----------------------------------------------------------- transitions --


def test_transition_declarations_are_todays():
    """The snap rule: the sheets' transitions are the two layout.css has
    always had (the busy fade and one width), and the theme adds none."""
    expected = {"tokens.css": 0, "layout.css": 2, "controls.css": 0, "models.css": 0, "methodology.css": 0}
    for name, count in expected.items():
        found = re.findall(r"\btransition\s*:", _strip_comments(_read(name)))
        assert len(found) == count, (name, len(found))


# ------------------------------------------- the CSS and the chart tokens --

#: The screen style that ECharts reads (js/scale.js) mirrors the stylesheet,
#: which it cannot read: each pair names the same colour in both places.
CSS_TO_THEME = {
    "--text": "text", "--muted": "muted", "--border": "border", "--card": "card", "--canvas": "canvas",
    "--accent": "accent", "--warn": "warn", "--shower-a": "showerA", "--shower-b": "showerB",
}


def _screen_literal(name: str) -> dict[str, str]:
    """The `#rrggbb` entries of a top-level object literal in js/scale.js, comments dropped."""
    source = _strip_comments((CSS.parent / "js" / "scale.js").read_text(encoding="utf-8"))
    body = source[source.index(f"const {name} = {{"):]
    body = body[:body.index("\n};")]
    return dict(re.findall(r"^\s*(\w+):\s*'(#[0-9a-fA-F]{6})'", body, re.MULTILINE))


def test_the_chart_tokens_mirror_the_stylesheet_in_both_themes():
    """A chart and the card it sits on take one colour from two files; they must agree."""
    for css, screen in ((_dark(), _screen_literal("SCREEN")), (_light(), _screen_literal("SCREEN_LIGHT"))):
        for token, key in CSS_TO_THEME.items():
            assert css[token].lower() == screen[key].lower(), (token, css[token], key, screen[key])
