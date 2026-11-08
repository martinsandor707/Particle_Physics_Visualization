"""Drawn bins beyond a capped D-frame window get an edge caret (``canonical_overlays.js``).

The server may cap the D-frame's x′ window at the drawn field's connected
extent instead of its 0.1st–99.9th percentile half-width, and reports the
drawn bins it leaves outside on ``frame.fit.xy.col.cap`` (the entry panel's
horizontal axis) and ``frame.fit.xz.row.cap`` (the X′Z′ panel's vertical
axis). CLAUDE.md section 2 says to clip it and say so: an out-of-bounds
indicator at the overflow, the true values in its tooltip, a count in the
drawer. The recorded fixture carries no ``cap`` yet, so one is injected here.

Pinned: the caret series exists only when ``outside.sides`` is non-empty; it
sits on the window edge of the clipped side, at the bins' energy-weighted
position along the other axis, pointing out of the plot; it hides when a zoom
leaves that edge out of view; its tooltip names the count, the range and the
share, with U+2212 for negative numbers; the Marks toggle leaves it; the
export draws it; its ink clears 3:1 on both screen cards and on paper.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
PAYLOADS = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: A hyphen-minus that signs a number (CLAUDE.md: U+2212 for every rendered negative).
HYPHEN_NUMBER = re.compile(r"(?<![\w])-\d")

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir] = JSON.parse(process.argv.at(-1));
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const element = { clientWidth: 600, clientHeight: 330, style: {}, classList: { toggle() {} }, closest: () => null,
  append() {}, replaceChildren() {}, appendChild() {}, hidden: false, addEventListener() {} };
const live = [];
const makeChart = () => ({
  getWidth: () => 600, getHeight: () => 330, resize() {}, clear() {}, on() {}, dispatchAction() {},
  getZr: () => ({ on() {}, off() {} }), getDom: () => element, convertFromPixel: () => [0, 0],
  setOption(option, flags) { if (flags?.notMerge) live.push(option); },
});
function fakeCanvas() {
  const c = { width: 0, height: 0 };
  c.getContext = () => ({
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
    putImageData() {}, drawImage() {}, set imageSmoothingEnabled(_) {}, font: '',
    measureText(text) { return { width: String(text).length * 5.5 }; },
  });
  return c;
}
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid' } };
globalThis.echarts = { init: () => makeChart() };
globalThis.document = { createElement: (t) => (t === 'canvas' ? fakeCanvas() : { ...element }),
  getElementById: () => element, createTextNode: (t) => ({ textContent: t }) };

const proj = await imp('panels/projection.js');
const ov = await imp('panels/canonical_overlays.js');
const cells = await imp('event_cells.js');
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const { THEME } = scale;

const base = load('projections_base_canonical');
const capOf = (sides) => ({
  rule: 'drawn_extent', applied: true, percentile_half_width: 1740.0, drawn_half_width: 186.0,
  reach_mm: 20.0, limit: 220.0, gap_mm: 48.6, floor_ratio: 0.001, rho_ref: 7.26e-05,
  outside: { bins: sides.reduce((n, s) => n + s.bins, 0),
    energy_fraction: sides.reduce((n, s) => n + s.energy_fraction, 0), sides },
});
const withCaps = (xySides, xzSides) => {
  const payload = clone(base);
  payload.frame.fit.xy.col.cap = capOf(xySides);
  payload.frame.fit.xz.row.cap = capOf(xzSides);
  payload.frame.fit.xy.row.cap = null;
  return payload;
};
const XY_SIDES = [
  { side: 1, bins: 2, energy_fraction: 0.00012, range: [1260.0, 1300.0], at: 4.0 },
  { side: -1, bins: 1, energy_fraction: 0.0000004, range: [-1340.0, -1300.0], at: -30.0 },
];
const XZ_SIDES = [{ side: 1, bins: 3, energy_fraction: 0.002, range: [1260.0, 1320.0], at: 250.0 }];
const capped = withCaps(XY_SIDES, XZ_SIDES);
const empty = withCaps([], []);

const metrics = { width: 600, height: 330 };
const build = (payload, panelId, { marksShown = true, view = null } = {}) => {
  const panel = new proj.ProjectionPanel('plot-x', { isometric: true });
  panel.marksShown = marksShown;
  panel.view = view;
  const sub = payload.panels[panelId];
  const opts = cells.ensembleCellOptions(payload, panelId, 'viridis');
  const option = panel.buildOption({ payload: sub, opts, raster: { canvas: null }, metrics });
  return { option, sub, opts };
};
const caretOf = (option) => option.series.find((s) => s.id === ov.OVERFLOW_ID) ?? null;

/* Render every caret item against a coordinate system with the grid's rectangle and the given window. */
function rendered(option, view) {
  const series = caretOf(option);
  if (!series) return null;
  const g = option.grid;
  const box = { x: g.left, y: g.top, width: g.width, height: g.height };
  const api = { coord: ([x, y]) => [g.left + ((x - view.col[0]) / (view.col[1] - view.col[0])) * g.width,
    g.top + ((view.row[1] - y) / (view.row[1] - view.row[0])) * g.height] };
  return series.data.map((datum, dataIndex) => {
    const el = series.renderItem({ dataIndex, coordSys: box }, api);
    return {
      datum, el: el ? { type: el.type, points: el.shape.points, fill: el.style.fill } : null,
      tip: series.tooltip.formatter({ dataIndex }), box,
    };
  });
}

const out = { ids: ov.OVERFLOW_ID };
for (const panelId of ['xy', 'xz', 'yz']) {
  const { option, sub, opts } = build(capped, panelId);
  const extent = proj.extentOf(sub, opts);
  out[panelId] = { present: Boolean(caretOf(option)), extent, items: rendered(option, extent),
    z: caretOf(option)?.z ?? null, silent: caretOf(option)?.silent ?? null };
}
out.none = { xy: Boolean(caretOf(build(empty, 'xy').option)), xz: Boolean(caretOf(build(empty, 'xz').option)),
  fixture: Boolean(caretOf(build(base, 'xy').option)) };
// The cap not applied: the percentile rule itself cut drawn bins (production's
// 15 x′ bins). They are still marked, with the percentile rule as the reason.
{
  const cut = withCaps(XY_SIDES, []);
  cut.frame.fit.xy.col.cap.applied = false;
  const { option } = build(cut, 'xy');
  const ext = proj.extentOf(cut.panels.xy, cells.ensembleCellOptions(cut, 'xy', 'viridis'));
  out.percentileCut = { present: Boolean(caretOf(option)), items: rendered(option, ext) };
  // The recorded base fixture: its X′Z′ cap is not applied but one drawn row lies beyond.
  out.fixtureXz = Boolean(caretOf(build(base, 'xz').option));
}
// The Marks toggle leaves the caret: it is a disclosure, not an overlay.
out.marksHidden = Boolean(caretOf(build(capped, 'xy', { marksShown: false }).option));
// Zoomed so the +x′ edge is out of view and the −x′ edge in view.
{
  const ext = out.xy.extent;
  const view = { col: [ext.col[0], 0], row: [ext.row[0], ext.row[1]] };
  const { option } = build(capped, 'xy', { view });
  out.zoomed = rendered(option, view);
}
// A lab payload never draws it, whatever its fit says.
{
  const lab = load('projections_base_lab');
  const panel = new proj.ProjectionPanel('plot-x', { isometric: true });
  const opts = { ...cells.ensembleCellOptions(lab, 'xy', 'viridis'), frame: { ...capped.frame, kind: 'lab' } };
  out.lab = Boolean(caretOf(panel.buildOption({ payload: lab.panels.xy, opts, raster: { canvas: null }, metrics })));
}
// The live panel: render, hide the marks, show them: the caret stays in every option put on screen.
{
  live.length = 0;
  const panel = new proj.ProjectionPanel('plot-xy', { isometric: true });
  panel.render(capped.panels.xy, cells.ensembleCellOptions(capped, 'xy', 'viridis'));
  panel.setMarksShown(false);
  panel.setMarksShown(true);
  out.live = live.map((o) => Boolean(caretOf(o)));
}
// Its ink, per theme: the warn token of the dark and light screens, and of print.
out.ink = {};
for (const theme of ['dark', 'light']) {
  scale.setScreenTheme(theme);
  const items = rendered(build(capped, 'xy').option, out.xy.extent);
  out.ink[theme] = { fill: items[0].el.fill, card: THEME.card };
}
scale.setScreenTheme('dark');
{
  const saved = { ...THEME };
  Object.assign(THEME, PRINT_TOKENS);
  const items = rendered(build(capped, 'xy').option, out.xy.extent);
  out.ink.print = { fill: items[0].el.fill, card: '#ffffff' };
  for (const k of Object.keys(THEME)) delete THEME[k];
  Object.assign(THEME, saved);
}
out.text = ov.windowOverflowText({ ...XY_SIDES[1], cap: capOf(XY_SIDES) }, { symbol: 'D', other: 'y′', edge: -1740 });
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _SCRIPT, json.dumps([JS.as_uri(), str(PAYLOADS)])],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_caret_is_drawn_only_where_the_window_clips_drawn_bins(out):
    assert out["xy"]["present"] is True
    assert out["xz"]["present"] is True
    # No cap on the Y′Z′ panel, empty sides, the recorded fixture and a lab payload: nothing.
    assert out["yz"]["present"] is False
    assert out["none"] == {"xy": False, "xz": False, "fixture": False}
    assert out["lab"] is False
    # Hoverable, above every mark.
    assert out["xy"]["silent"] is False
    assert out["xy"]["z"] >= 12


def test_the_entry_panel_caret_sits_on_the_clipped_edge_at_the_bins_centroid(out):
    xy = out["xy"]
    ext = xy["extent"]
    right, left = xy["items"]
    assert right["datum"][:2] == [ext["col"][1], 4.0]
    assert left["datum"][:2] == [ext["col"][0], -30.0]
    box = right["box"]
    # The tip on the right edge, pointing right; the body inside the plot.
    tip, *wings = right["el"]["points"]
    assert tip[0] == pytest.approx(box["x"] + box["width"])
    assert all(w[0] < tip[0] for w in wings)
    tip, *wings = left["el"]["points"]
    assert tip[0] == pytest.approx(box["x"])
    assert all(w[0] > tip[0] for w in wings)
    for item in xy["items"]:
        for x, y in item["el"]["points"]:
            assert box["x"] - 1e-6 <= x <= box["x"] + box["width"] + 1e-6
            assert box["y"] - 1e-6 <= y <= box["y"] + box["height"] + 1e-6


def test_the_x_prime_z_prime_caret_sits_on_the_vertical_x_prime_axis(out):
    xz = out["xz"]
    ext = xz["extent"]
    (item,) = xz["items"]
    # Columns are z′, rows x′: the +x′ edge is the top of the plot, at z′ = at.
    assert item["datum"][:2] == [250.0, ext["row"][1]]
    tip, *wings = item["el"]["points"]
    assert tip[1] == pytest.approx(item["box"]["y"])
    assert all(w[1] > tip[1] for w in wings)


def test_drawn_bins_the_percentile_rule_cut_are_marked_with_that_reason(out):
    """Every drawn bin the notes count beyond the window is marked, whoever cut it."""
    cut = out["percentileCut"]
    assert cut["present"] is True and len(cut["items"]) == 2
    for item in cut["items"]:
        assert "the 0.1st–99.9th percentile window ends inside the drawn field here" in item["tip"]
        assert "capped at the drawn field" not in item["tip"]
    assert out["fixtureXz"] is True


def test_the_tooltip_names_the_count_range_and_share(out):
    right, left = out["xy"]["items"]
    assert "2 drawn bins" in right["tip"]
    assert "D = 1,260–1,300 mm" in right["tip"]
    assert "0.012% of this panel’s energy" in right["tip"]
    assert "capped at the drawn field’s connected extent" in right["tip"]
    assert "see Details" in right["tip"]
    assert "1 drawn bin " in left["tip"]
    assert "< 0.001%" in left["tip"]
    # Negative numbers use U+2212.
    assert "D = −1,340 to −1,300 mm" in left["tip"]
    assert "y′ = −30.0 mm" in left["tip"]
    (xz,) = out["xz"]["items"]
    assert "3 drawn bins" in xz["tip"] and "x′ = 1,260–1,320 mm" in xz["tip"] and "z′ = 250.0 mm" in xz["tip"]
    for text in [right["tip"], left["tip"], xz["tip"], out["text"]]:
        assert not HYPHEN_NUMBER.search(re.sub(r"<[^>]+>", "", text)), text
    assert "D = −1,740 mm" in out["text"]


def test_the_caret_survives_the_marks_toggle_and_reaches_the_screen(out):
    assert out["marksHidden"] is True
    assert out["live"] and all(out["live"])


def test_a_zoom_hides_the_caret_whose_edge_is_out_of_view(out):
    right, left = out["zoomed"]
    assert right["el"] is None
    assert left["el"] is not None


def test_the_caret_ink_clears_three_to_one_on_every_card(out):
    for theme, ink in out["ink"].items():
        assert _contrast(ink["fill"], ink["card"]) >= 3.0, (theme, ink)
