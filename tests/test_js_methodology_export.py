"""The Methodology export (``methodology/export.js``) and its paper figures, under Node.

The Export button writes each of the article's three figures drawn for paper
(``methodology/exhibits.js``, ``medium: 'paper'``), as SVG and PNG. What is
checked here, without a browser:

* each paper figure, serialised by ``serialiseSvg``, is well-formed XML with
  the SVG namespace and an XML declaration, sized ``160mm`` wide on a
  640-unit viewBox, with one font family on its root (export/tokens.js
  ``PRINT_TOKENS.fontFamily``) and a white rectangle covering it first;
* no dark ground: every plainly filled rectangle is white, a PuOr class's
  swatch or the small key swatch of the screen card; the gradient strips
  (the ramps themselves) keep their colours;
* self-contained: no ``currentColor``, no ``var(``, no ``style``, no class
  but the three data-marker classes the tests select by; every text names
  its fill, every line its stroke, every shape its fill or stroke;
* every text is at least 9 pt at 160 mm, and every text colour clears 4.5:1
  on white;
* the same data marks as the screen figure: the legible spans of the ramps,
  the PuOr anchors with their contrasts (and the printed number is the
  marked one), the folded ramp's first legible colours, and the SE(3)
  schematic's marks at the same place in their frames, at one scale;
* no hyphen-minus signs a number;
* ``withPhys`` puts one 300 dpi ``pHYs`` right after IHDR, replacing any
  other, with every chunk's CRC valid;
* ``exportFiles`` with a stub rasteriser names the files in order (TeX, BibTeX,
  then each figure's SVG and PNG in document order) and asks for 1890 px
  wide PNGs, as tall as the figure is at 300 dpi.

The browser half (the real rasteriser, the download) is
``tests/test_browser_methodology.py``. Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import struct
import xml.etree.ElementTree as ET
import zlib

import pytest
from test_js_physics_shell import JS, NODE

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SVG = "{http://www.w3.org/2000/svg}"
#: 9 pt at 160 mm on a 640-unit viewBox, in viewBox units.
MIN_FONT = 9 * 25.4 / 72 * 640 / 160
DATA_CLASSES = {"ramp-legible", "puor-anchor", "puor-first-legible"}
HYPHEN = re.compile(r"(?<![\w)\]])-(?=\.?\d)")

_URLS = {
    "exhibits": (JS / "methodology" / "exhibits.js").as_uri(),
    "export": (JS / "methodology" / "export.js").as_uri(),
    "tokens": (JS / "export" / "tokens.js").as_uri(),
    "article": (JS / "methodology" / "content" / "index.js").as_uri(),
}

_SCRIPT = r"""
const urls = JSON.parse(process.argv[1]);
const exhibits = await import(urls.exhibits);
const ex = await import(urls.export);
const { PRINT_TOKENS } = await import(urls.tokens);
const { ARTICLE } = await import(urls.article);
const out = { fontFamily: PRINT_TOKENS.fontFamily, figures: {}, screen: {} };
for (const [name, build] of Object.entries(exhibits.EXHIBITS)) {
  const paper = build(`fig-${name}`, { medium: 'paper' });
  out.figures[name] = { svg: ex.serialiseSvg(paper), size: ex.paperSize(paper) };
  const screen = build(`fig-${name}`);
  out.screen[name] = { svg: ex.serialiseSvg(screen),
    same: JSON.stringify(screen) === JSON.stringify(build(`fig-${name}`, { medium: 'screen' })) };
}
out.paperWidth = exhibits.PAPER_WIDTH_MM;
out.minFont = exhibits.PAPER_MIN_FONT;
out.escaped = ex.serialiseSvg({ tag: 'svg', attrs: { 'data-q': `a "b" & 'c' <d>` },
  children: [{ tag: 'text', attrs: {}, children: [{ text: `x < y & "z" − 1` }] }] });

/* withPhys on the PNGs the test built. */
const [plain, withOld] = JSON.parse(process.argv[2]).map((b64) => new Uint8Array(Buffer.from(b64, 'base64')));
out.phys = [plain, withOld].map((png) => Buffer.from(ex.withPhys(png)).toString('base64'));
try { ex.withPhys(new Uint8Array([1, 2, 3])); out.notPng = null; } catch (error) { out.notPng = error.message; }

/* exportFiles with a stub rasteriser. */
const asked = [];
const files = await ex.exportFiles(ARTICLE, {
  provenance: { version: '9.9.9', stamp: 'abcdef012345', date: '2026-10-29' },
  rasterise: async (svg, size) => { asked.push({ size, svg: svg.slice(0, 60) }); return new Uint8Array([7, asked.length]); },
});
out.files = files.map((f) => [f.name, f.bytes.length, Array.from(f.bytes.slice(0, 2))]);
out.errors = files.errors;
out.asked = asked;
out.folder = ex.EXPORT_FOLDER;
const ids = [];
const walk = (part) => { for (const b of part?.blocks ?? []) if (b?.kind === 'figure') ids.push(b.id);
  for (const c of part?.sections ?? []) walk(c); };
for (const part of [...ARTICLE.sections, ...(ARTICLE.appendices ?? [])]) walk(part);
out.figureIds = ids;
console.log(JSON.stringify(out));
"""


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png(*, phys: bytes | None = None) -> bytes:
    """A valid 2 × 1 RGB PNG; with `phys`, a pHYs chunk (as an encoder may write) after IDAT's predecessor."""
    ihdr = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\xff\x00\x00\x00\x00\xff")
    chunks = [_chunk(b"IHDR", ihdr)]
    if phys is not None:
        chunks.append(_chunk(b"pHYs", phys))
    chunks += [_chunk(b"IDAT", idat), _chunk(b"IEND", b"")]
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


def _chunks(png: bytes) -> list[tuple[bytes, bytes, bool]]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    out, at = [], 8
    while at < len(png):
        (length,) = struct.unpack(">I", png[at:at + 4])
        kind = png[at + 4:at + 8]
        data = png[at + 8:at + 8 + length]
        (crc,) = struct.unpack(">I", png[at + 8 + length:at + 12 + length])
        out.append((kind, data, crc == zlib.crc32(kind + data)))
        at += 12 + length
    return out


@pytest.fixture(scope="module")
def result() -> dict:
    """The script's findings; the two PNGs for ``withPhys`` go as a second argument (``_run`` passes one)."""
    plain = _png()
    old = _png(phys=struct.pack(">IIB", 2835, 2835, 1))   # 72 dpi, as an encoder might write
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _SCRIPT, json.dumps(_URLS),
         json.dumps([base64.b64encode(p).decode() for p in (plain, old)])],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast_on_white(hex_colour: str) -> float:
    return 1.05 / (_luminance(hex_colour) + 0.05)


def _parse(svg: str) -> ET.Element:
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"')
    return ET.fromstring(svg.encode("utf-8"))


def _walk(element, ancestors=()):
    yield element, ancestors
    for child in element:
        yield from _walk(child, (*ancestors, element))


def _classes(element) -> set[str]:
    return set((element.get("class") or "").split())


FIGURES = ["ramps", "puor", "se3"]


@pytest.mark.parametrize("name", FIGURES)
def test_a_paper_figure_is_a_self_contained_svg_sized_for_the_page(result, name):
    figure = result["figures"][name]
    svg = figure["svg"]
    root = _parse(svg)
    assert root.tag == f"{SVG}svg"
    assert result["paperWidth"] == 160
    assert root.get("width") == "160mm"
    _, _, width, height = (float(v) for v in root.get("viewBox").split())
    assert width == 640
    assert float(root.get("height").removesuffix("mm")) == pytest.approx(height * 160 / 640, abs=0.01)
    assert root.get("font-family") == result["fontFamily"]
    assert figure["size"]["widthPx"] == 1890
    assert figure["size"]["heightPx"] == round(height / 4 / 25.4 * 300)
    # A white ground first: the first drawn child covers the whole viewBox.
    drawn = [c for c in root if c.tag not in (f"{SVG}title", f"{SVG}desc", f"{SVG}defs")]
    first = drawn[0]
    assert first.tag == f"{SVG}rect" and first.get("fill").lower() == "#ffffff"
    assert (float(first.get("x")), float(first.get("y")), float(first.get("width")), float(first.get("height"))) \
        == (0, 0, width, height)
    # Nothing left to a stylesheet.
    assert "currentColor" not in svg and "var(" not in svg
    for element, _ in _walk(root):
        assert element.get("style") is None, element.tag
        assert _classes(element) <= DATA_CLASSES, (element.tag, element.get("class"))
        tag = element.tag.removeprefix(SVG)
        if tag == "text":
            assert element.get("fill"), element.text
        elif tag == "line":
            assert element.get("stroke"), element.attrib
        elif tag in ("rect", "path", "circle"):
            assert element.get("fill") or element.get("stroke"), element.attrib


@pytest.mark.parametrize("name", FIGURES)
def test_no_dark_ground_remains(result, name):
    root = _parse(result["figures"][name]["svg"])
    for element, ancestors in _walk(root):
        if element.tag != f"{SVG}rect":
            continue
        fill = (element.get("fill") or "").lower()
        if fill in ("#ffffff", "none") or fill.startswith("url(#"):
            continue   # white, unfilled, or a ramp's gradient strip (data)
        in_anchor = any("puor-anchor" in _classes(a) for a in ancestors)
        key = element.get("data-key") == "screen-card" and float(element.get("width")) * float(element.get("height")) <= 26 * 14
        assert in_anchor or key, f"a filled rectangle that is not data: {element.attrib}"


@pytest.mark.parametrize("name", FIGURES)
def test_every_text_is_nine_points_and_legible_on_white(result, name):
    root = _parse(result["figures"][name]["svg"])
    texts = [e for e, _ in _walk(root) if e.tag == f"{SVG}text"]
    assert texts
    assert result["minFont"] == pytest.approx(MIN_FONT)
    for text in texts:
        assert float(text.get("font-size")) >= MIN_FONT, (text.text, text.get("font-size"))
        assert _contrast_on_white(text.get("fill")) >= 4.5, (text.text, text.get("fill"))
        assert not HYPHEN.search(text.text or ""), text.text


def _marks(root, cls):
    return [e for e, _ in _walk(root) if cls in _classes(e)]


def test_the_ramps_mark_the_same_legible_spans(result):
    paper = _parse(result["figures"]["ramps"]["svg"])
    screen = _parse(result["screen"]["ramps"]["svg"])
    spans = lambda root: [(m.get("data-palette"), m.get("data-from"), m.get("data-to")) for m in _marks(root, "ramp-legible")]
    assert spans(paper) == spans(screen) and len(spans(paper)) == 4
    for mark in _marks(paper, "ramp-legible"):
        words = [t.text for t in mark.iter(f"{SVG}text")]
        assert words == [f"from {mark.get('data-from')}", f"to {mark.get('data-to')}"]
    # The page says what the spans are measured against, never "on" a ground it does not paint.
    words = " ".join(t.text or "" for t in paper.iter(f"{SVG}text"))
    assert "against the screen card" in words and "#1c2128" in words and "on #1c2128" not in words


def test_puor_keeps_every_anchor_and_contrast(result):
    paper = _parse(result["figures"]["puor"]["svg"])
    screen = _parse(result["screen"]["puor"]["svg"])
    anchors = lambda root: [(m.get("data-ground"), m.get("data-index"), m.get("data-hex"), m.get("data-contrast"))
                            for m in _marks(root, "puor-anchor")]
    assert anchors(paper) == anchors(screen) and len(anchors(paper)) == 22
    for mark in _marks(paper, "puor-anchor"):
        [shown] = [t.text for t in mark.iter(f"{SVG}text")]
        assert shown == mark.get("data-contrast")
        [swatch] = list(mark.iter(f"{SVG}rect"))
        assert swatch.get("fill") == mark.get("data-hex")
        bold = float(mark.get("data-contrast")) >= 3
        assert (next(mark.iter(f"{SVG}text")).get("font-weight") == "700") == bold
    first = lambda root: [(m.get("data-arm"), m.get("data-index"), m.get("data-contrast")) for m in _marks(root, "puor-first-legible")]
    assert first(paper) == first(screen) and [arm for arm, *_ in first(paper)] == ["neg", "pos"]
    words = " ".join(t.text or "" for t in paper.iter(f"{SVG}text"))
    assert "Against the screen card #1c2128" in words and "on #1c2128" not in words


def _centre(element) -> tuple[float, float]:
    if element.tag == f"{SVG}circle":
        return float(element.get("cx")), float(element.get("cy"))
    # A diamond path: M x (y − r) L (x + r) y ... — its centre is the first point moved down by r.
    numbers = [float(v) for v in re.findall(r"-?[\d.]+", element.get("d"))]
    return numbers[0], numbers[3]


def test_the_se3_schematic_draws_the_same_events_at_one_scale(result):
    paper = _parse(result["figures"]["se3"]["svg"])
    screen = _parse(result["screen"]["se3"]["svg"])
    paper_frames = [e for e, _ in _walk(paper) if e.get("data-mark") == "frame"]
    screen_frames = [e for e in screen.iter(f"{SVG}rect") if "se3-frame" in _classes(e)]
    assert len(paper_frames) == len(screen_frames) == 2
    box = lambda f: tuple(float(f.get(k)) for k in ("x", "y", "width", "height"))
    (pw, ph), (sw, sh) = box(paper_frames[0])[2:], box(screen_frames[0])[2:]
    assert box(paper_frames[0])[2:] == box(paper_frames[1])[2:]
    assert pw / ph == pytest.approx(sw / sh, rel=1e-3)   # isometric, as on screen

    def relative(root, frames, select):
        marks = [e for e, _ in _walk(root) if select(e)]
        out = []
        for mark in marks:
            x, y = _centre(mark)
            frame = next(f for f in frames if box(f)[0] <= x <= box(f)[0] + box(f)[2])
            fx, fy, fw, fh = box(frame)
            out.append((round((x - fx) / fw, 2), round((y - fy) / fh, 2)))
        return out

    for shower, cls in (("a", "se3-a"), ("b", "se3-b")):
        on_paper = relative(paper, paper_frames, lambda e, s=shower: e.get("data-mark") == s)
        on_screen = relative(screen, screen_frames, lambda e, c=cls: c in _classes(e))
        assert len(on_paper) == 4 and on_paper == on_screen
    colours = {e.get("data-mark"): e.get("fill") for e, _ in _walk(paper) if e.get("data-mark") in ("a", "b")}
    assert colours == {"a": "#a3175f", "b": "#1d4ed8"}   # the article's print palette
    words = " ".join(t.text or "" for t in paper.iter(f"{SVG}text"))
    assert "Schematic, not measured data" in words and "−D₁/2" in words


def test_the_screen_figures_are_the_default_and_unchanged_in_kind(result):
    for name in FIGURES:
        assert result["screen"][name]["same"], name
        root = _parse(result["screen"][name]["svg"])
        assert root.get("width") == "100%" and root.get("data-medium") is None
        assert "exhibit-svg" in _classes(root)


def test_the_serialiser_escapes_text_and_attributes(result):
    root = _parse(result["escaped"])
    assert root.get("data-q") == "a \"b\" & 'c' <d>"
    assert root[0].text == 'x < y & "z" − 1'


def test_phys_is_inserted_after_ihdr_with_valid_crcs(result):
    for b64 in result["phys"]:
        chunks = _chunks(base64.b64decode(b64))
        assert all(ok for _, _, ok in chunks)
        kinds = [k for k, _, _ in chunks]
        assert kinds == [b"IHDR", b"pHYs", b"IDAT", b"IEND"]
        x, y, unit = struct.unpack(">IIB", chunks[1][1])
        assert (x, y, unit) == (11811, 11811, 1)   # 300 dpi in pixels per metre
    assert result["notPng"] and "PNG" in result["notPng"]


def test_export_files_are_named_in_order(result):
    folder = result["folder"]
    assert folder == "calosrv-methodology"
    names = [name for name, _, _ in result["files"]]
    expected = [f"{folder}/methodology.tex", f"{folder}/references.bib"]
    for fid in result["figureIds"]:
        expected += [f"{folder}/figures/{fid}.svg", f"{folder}/figures/{fid}.png"]
    assert names == expected and len(result["figureIds"]) == 3
    # Each PNG is the stub rasteriser's bytes, asked for at 300 dpi of the figure's printed size.
    pngs = [first for name, _, first in result["files"] if name.endswith(".png")]
    assert pngs == [[7, i] for i in range(1, 4)]
    for asked in result["asked"]:
        assert asked["size"]["widthPx"] == 1890 and asked["size"]["widthMm"] == 160
        assert asked["size"]["heightPx"] == round(asked["size"]["heightMm"] / 25.4 * 300)
        assert asked["svg"].startswith("<?xml")
    assert isinstance(result["errors"], list)
