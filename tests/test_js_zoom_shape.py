"""An isometric panel's plot follows the displayed window (``panels/projection.js``).

Executed under Node against the recorded payloads, with a headless ECharts
stand-in that keeps the merged axis bounds and the grid of the option on
screen, and maps pixels to millimetres through them, as ECharts does.

What is pinned (CLAUDE.md section 2, "Zero Axis Distortion": detector
geometry keeps 1:1 at every zoom):

* the plot rectangle of an isometric panel is letterboxed from the displayed
  window, so one millimetre is the same number of pixels on both axes at
  every zoom, whatever the window's shape;
* a zoomed window is shaped to the card (``shapeToCard``): a wheel zoom into
  a D-frame entry strip grows the plot into the card's height until the full
  y′ extent is on show, Auto-fit RoI fills the card within the extent, and a
  zoom out or Reset returns to the strip's own letterbox;
* a pan keeps the rectangle and patches the axes alone; a change of shape
  rebuilds the option;
* a kept zoom across a selection change, and a container relayout while
  zoomed, are re-shaped to the card and stay 1:1;
* the absolute frame's depth panels (not isometric) keep their old
  behaviour: the card is filled at every zoom and both spans scale equally.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
PAYLOADS = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir] = JSON.parse(process.argv.at(-1));
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

/* ---- a headless chart: the merged axis bounds and grid, and a pixel map through them ---- */
let size = { width: 600, height: 330 };
const element = { get clientWidth() { return size.width; }, get clientHeight() { return size.height; },
  style: {}, classList: { toggle() {} }, closest: () => null, append() {}, replaceChildren() {}, appendChild() {},
  hidden: false, addEventListener() {} };
const calls = [];
/* One chart per panel, each with its own pointer handlers and merged option state. */
const makeChart = () => {
  const zr = { handlers: {}, on(ev, fn) { (this.handlers[ev] ??= []).push(fn); },
    off(ev, fn) { this.handlers[ev] = (this.handlers[ev] ?? []).filter((f) => f !== fn); },
    fire(ev, e) { for (const fn of this.handlers[ev] ?? []) fn(e); } };
  const state = { grid: null, x: null, y: null };
  return {
    zr, state,
    getWidth: () => size.width, getHeight: () => size.height, resize() {}, clear() {}, on() {},
    getZr: () => zr, getDom: () => element, dispatchAction() {},
    setOption(option, flags) {
      calls.push({ option, notMerge: Boolean(flags?.notMerge) });
      if (flags?.notMerge) {
        state.grid = { ...option.grid };
        state.x = { min: option.xAxis.min, max: option.xAxis.max };
        state.y = { min: option.yAxis.min, max: option.yAxis.max };
        return;
      }
      if (option.xAxis) state.x = { ...state.x, min: option.xAxis.min, max: option.xAxis.max };
      if (option.yAxis) state.y = { ...state.y, min: option.yAxis.min, max: option.yAxis.max };
    },
    convertFromPixel: (_, [px, py]) => {
      const g = state.grid;
      return [state.x.min + ((px - g.left) / g.width) * (state.x.max - state.x.min),
        state.y.max - ((py - g.top) / g.height) * (state.y.max - state.y.min)];
    },
    getModel: () => ({ getComponent: () => ({ coordinateSystem: { getRect: () => ({ x: state.grid.left,
      y: state.grid.top, width: state.grid.width, height: state.grid.height }) } }) }),
  };
};
function fakeCanvas() {
  const c = { width: 0, height: 0 };
  c.getContext = () => ({
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
    putImageData() {}, drawImage() {}, set imageSmoothingEnabled(_) {}, font: '',
    measureText(text) { const px = Number(/(\d+(?:\.\d+)?)px/.exec(this.font)?.[1] ?? 10); return { width: String(text).length * px * 0.55 }; },
  });
  return c;
}
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid' } };
globalThis.echarts = { init: () => makeChart() };
globalThis.document = { createElement: (t) => (t === 'canvas' ? fakeCanvas() : { ...element }),
  getElementById: () => element, createTextNode: (t) => ({ textContent: t }) };

const proj = await imp('panels/projection.js');
const cells = await imp('event_cells.js');

/* What the screen shows: the grid, the axes, px/mm on each axis and the stored view. */
const snap = (panel) => {
  const { state } = panel.chart;
  const g = state.grid;
  const colSpan = state.x.max - state.x.min;
  const rowSpan = state.y.max - state.y.min;
  return { grid: { left: g.left, top: g.top, width: g.width, height: g.height },
    x: [state.x.min, state.x.max], y: [state.y.min, state.y.max],
    pxCol: g.width / colSpan, pxRow: g.height / rowSpan, view: panel.view ? clone(panel.view) : null };
};
const wheel = (panel, inward, at = null) => {
  const g = panel.chart.state.grid;
  const [px, py] = at ?? [g.left + g.width / 2, g.top + g.height / 2];
  panel.chart.zr.fire('mousewheel', { offsetX: px, offsetY: py, wheelDelta: inward ? 1 : -1 });
};
const rebuilt = (from) => calls.slice(from).some((c) => c.notMerge);
const out = {};

/* ---- 1. a D-frame entry strip: ±2,400 × ±140 mm ---- */
const canonical = load('projections_base_canonical');
const strip = clone(canonical.panels.xy);
strip.axes.col.lo = -2400; strip.axes.col.hi = 2400;
strip.axes.row.lo = -140; strip.axes.row.hi = 140;
const stripOpts = cells.ensembleCellOptions(canonical, 'xy', 'viridis');
{
  size = { width: 600, height: 330 };
  const p = new proj.ProjectionPanel('plot-xy', { isometric: true });
  p.render(strip, stripOpts);
  const rest = snap(p);
  const aspect = p.cardAspect();
  const zoomIn = [];
  for (let i = 0; i < 30; i += 1) {
    const from = calls.length;
    wheel(p, true);
    zoomIn.push({ ...snap(p), rebuilt: rebuilt(from) });
  }
  const zoomOut = [];
  for (let i = 0; i < 40; i += 1) {
    wheel(p, false);
    zoomOut.push(snap(p));
  }
  // A pan of a zoomed window keeps the rectangle and patches the axes alone.
  for (let i = 0; i < 6; i += 1) wheel(p, true);
  const beforePan = snap(p);
  let from = calls.length;
  const g = p.chart.state.grid;
  p.chart.zr.fire('mousedown', { offsetX: g.left + 50, offsetY: g.top + 10 });
  p.chart.zr.fire('mousemove', { offsetX: g.left + 80, offsetY: g.top + 12 });
  p.chart.zr.fire('mouseup', {});
  const pan = { before: beforePan, after: snap(p), rebuilt: rebuilt(from) };
  // Reset returns to the strip.
  from = calls.length;
  p.resetView();
  const reset = { ...snap(p), rebuilt: rebuilt(from) };
  // Auto-fit RoI fills the card's aspect within the extent. The fixture's two events sit at
  // ∓D/2, so its 99% box spans the strip: keep only the 20 columns round the brightest one.
  const { codes, rows, cols } = p.raster;
  let peak = 0;
  for (let i = 0; i < codes.length; i += 1) if (codes[i] > codes[peak]) peak = i;
  const peakCol = peak % cols;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) if (Math.abs(c - peakCol) > 10) codes[r * cols + c] = strip.empty_code;
  }
  const roi = p.autoFitRoI();
  const fitted = snap(p);
  // A kept zoom across a selection change: a narrower x′ window, one view key.
  const narrower = clone(strip);
  narrower.axes.col.lo = -1800; narrower.axes.col.hi = 1800;
  narrower.axes.row.lo = -160; narrower.axes.row.hi = 160;
  p.render(narrower, stripOpts);
  const kept = snap(p);
  // A container relayout while zoomed: a taller card.
  size = { width: 600, height: 520 };
  p.relayout();
  const relaid = { ...snap(p), aspect: p.cardAspect() };
  // Export: the figure takes the displayed window's aspect, and the letterbox at print geometry is 1:1.
  const metrics = p.exportMetrics(900);
  const printed = p.buildOption({ payload: p.payload, opts: p.lastOpts, raster: p.raster, metrics });
  const exported = { metrics, pxCol: printed.grid.width / (printed.xAxis.max - printed.xAxis.min),
    pxRow: printed.grid.height / (printed.yAxis.max - printed.yAxis.min) };
  size = { width: 600, height: 330 };
  out.strip = { rest, aspect, zoomIn, zoomOut, pan, reset, roi, fitted, kept, relaid, exported,
    extent: { col: [-2400, 2400], row: [-140, 140] }, narrowExtent: { col: [-1800, 1800], row: [-160, 160] } };
}

/* ---- 2. the absolute frame's XY panel: 1:1 at every zoom, and back ---- */
const lab = load('projections_base_lab');
{
  size = { width: 600, height: 330 };
  const p = new proj.ProjectionPanel('plot-xy', { isometric: true });
  p.render(lab.panels.xy, cells.ensembleCellOptions(lab, 'xy', 'viridis'));
  const rest = snap(p);
  const steps = [];
  // Off-centre, so the slide inside the extent is exercised too.
  for (let i = 0; i < 20; i += 1) {
    const g = p.chart.state.grid;
    wheel(p, true, [g.left + 0.8 * g.width, g.top + 0.3 * g.height]);
    steps.push(snap(p));
  }
  for (let i = 0; i < 30; i += 1) { wheel(p, false); steps.push(snap(p)); }
  const roi = p.autoFitRoI();
  out.lab = { rest, steps, end: steps.at(-1), roi, fitted: snap(p),
    extent: proj.extentOf(lab.panels.xy, cells.ensembleCellOptions(lab, 'xy', 'viridis')) };
}

/* ---- 3. an absolute depth panel (not isometric): unchanged ---- */
{
  size = { width: 600, height: 330 };
  const p = new proj.ProjectionPanel('plot-yz');
  p.render(lab.panels.yz, cells.ensembleCellOptions(lab, 'yz', 'viridis'));
  const rest = snap(p);
  const steps = [];
  for (let i = 0; i < 5; i += 1) {
    const from = calls.length;
    wheel(p, true);
    steps.push({ ...snap(p), rebuilt: rebuilt(from) });
  }
  out.depth = { rest, steps };
}

/* ---- 4. an Event Inspector cell: a framed panel on the caller's equal window ---- */
{
  size = { width: 400, height: 300 };
  const sub = lab.panels.xy;
  const window = { col: [-600, 600], row: [-600, 600] };
  const p = new proj.ProjectionPanel('plot-event', { isometric: true });
  p.render(sub, { palette: 'viridis', framed: true, window });
  const steps = [snap(p)];
  for (let i = 0; i < 8; i += 1) { wheel(p, true); steps.push(snap(p)); }
  for (let i = 0; i < 20; i += 1) { wheel(p, false); steps.push(snap(p)); }
  out.inspector = { steps, window };
  size = { width: 600, height: 330 };
}

/* ---- 5. a band reserved above the plot (the Longitudinal Channels' grid band) re-shapes a zoom ---- */
{
  size = { width: 600, height: 330 };
  const p = new proj.ProjectionPanel('plot-xy', { isometric: true });
  p.render(strip, stripOpts);
  for (let i = 0; i < 30; i += 1) wheel(p, true);
  const before = { ...snap(p), aspect: p.cardAspect() };
  let changed = 0;
  p.onViewChange = () => { changed += 1; };
  p.setReserveTop('strip');
  out.band = { before, after: { ...snap(p), aspect: p.cardAspect() }, changed };
}

/* ---- 6. shapeToCard on its own ---- */
const E = { col: [-2400, 2400], row: [-140, 140] };
out.shape = {
  // A wide window under a 2:1 card: the row is widened to the card, then capped at its extent.
  capped: proj.shapeToCard({ col: [-1000, 1000], row: [-50, 50] }, E, 2),
  // A small window: widened to the card's ratio and kept where it was.
  inside: proj.shapeToCard({ col: [-100, 100], row: [-20, 20] }, E, 2),
  // Near an edge: slid back inside at its full size.
  edge: proj.shapeToCard({ col: [2300, 2500], row: [100, 160] }, E, 2),
  // Covering both extents: the full view.
  full: proj.shapeToCard({ col: [-3000, 3000], row: [-200, 200] }, E, 2),
  // A tall card: the column is widened instead.
  tall: proj.shapeToCard({ col: [-50, 50], row: [-50, 50] }, E, 0.5),
  noAspect: proj.shapeToCard({ col: [-3000, 1000], row: [-50, 50] }, E, null),
};
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


def _one_to_one(snap: dict, rel: float = 1e-6) -> None:
    assert snap["pxCol"] == pytest.approx(snap["pxRow"], rel=rel), snap


def _inside(snap: dict, extent: dict) -> None:
    assert snap["x"][0] >= extent["col"][0] - 1e-6 and snap["x"][1] <= extent["col"][1] + 1e-6, snap
    assert snap["y"][0] >= extent["row"][0] - 1e-6 and snap["y"][1] <= extent["row"][1] + 1e-6, snap


# ------------------------------------------------------------- the strip --

def test_a_strip_at_rest_is_letterboxed_from_its_full_extent(out):
    rest = out["strip"]["rest"]
    assert rest["view"] is None
    _one_to_one(rest)
    # 4,800 × 280 mm: a strip some 17 times wider than tall.
    assert rest["grid"]["width"] / rest["grid"]["height"] == pytest.approx(4800 / 280)


def test_a_wheel_zoom_into_a_strip_grows_the_plot_and_keeps_one_to_one(out):
    strip = out["strip"]
    heights = [strip["rest"]["grid"]["height"]] + [s["grid"]["height"] for s in strip["zoomIn"]]
    for snap in strip["zoomIn"]:
        _one_to_one(snap)
        _inside(snap, strip["extent"])
    # The plot only grows while zooming in, and it does grow: the first notch already rebuilds.
    assert all(b >= a - 1e-9 for a, b in zip(heights, heights[1:]))
    assert heights[1] > heights[0]
    assert strip["zoomIn"][0]["rebuilt"] is True
    # It ends at the card's full plot height, the plot's span ratio the card's own.
    last = strip["zoomIn"][-1]
    assert last["grid"]["width"] / last["grid"]["height"] == pytest.approx(strip["aspect"], rel=1e-6)
    assert last["grid"]["height"] > 8 * strip["rest"]["grid"]["height"]


def test_while_the_strip_shows_less_than_its_row_extent_the_window_fills_the_card(out):
    strip = out["strip"]
    for snap in strip["zoomIn"]:
        row_span = snap["y"][1] - snap["y"][0]
        col_span = snap["x"][1] - snap["x"][0]
        if row_span < 280 - 1e-6:
            # The row is zoomed: the window takes the card's aspect exactly.
            assert col_span / row_span == pytest.approx(strip["aspect"], rel=1e-6)
        else:
            # The full y′ extent is on show and the plot letterboxes on x′.
            assert col_span / row_span >= strip["aspect"] - 1e-6


def test_a_zoom_out_returns_to_the_strip(out):
    strip = out["strip"]
    for snap in strip["zoomOut"]:
        _one_to_one(snap)
        _inside(snap, strip["extent"])
    end = strip["zoomOut"][-1]
    assert end["view"] is None
    assert end["grid"] == pytest.approx(strip["rest"]["grid"])
    assert end["x"] == pytest.approx(strip["rest"]["x"])
    assert end["y"] == pytest.approx(strip["rest"]["y"])


def test_a_pan_keeps_the_rectangle_and_patches_the_axes_alone(out):
    pan = out["strip"]["pan"]
    assert pan["rebuilt"] is False
    assert pan["after"]["grid"] == pan["before"]["grid"]
    assert pan["after"]["x"] != pan["before"]["x"]
    _one_to_one(pan["after"])


def test_reset_restores_the_full_extent_letterbox(out):
    strip = out["strip"]
    reset = strip["reset"]
    assert reset["view"] is None
    assert reset["rebuilt"] is True
    assert reset["grid"] == pytest.approx(strip["rest"]["grid"])


def test_auto_fit_fills_the_card_within_the_extent(out):
    strip = out["strip"]
    assert strip["roi"] == "fitted"
    fitted = strip["fitted"]
    _one_to_one(fitted)
    _inside(fitted, strip["extent"])
    col_span = fitted["x"][1] - fitted["x"][0]
    row_span = fitted["y"][1] - fitted["y"][0]
    # Either the window takes the card's aspect, or its y′ is the full extent (the plot letterboxes on x′).
    assert (col_span / row_span == pytest.approx(strip["aspect"], rel=1e-6)) or row_span == pytest.approx(280)
    assert fitted["grid"]["height"] > 3 * strip["rest"]["grid"]["height"]


def test_a_kept_zoom_across_a_selection_change_is_reshaped_and_stays_one_to_one(out):
    strip = out["strip"]
    kept = strip["kept"]
    assert kept["view"] is not None
    _one_to_one(kept)
    _inside(kept, strip["narrowExtent"])


def test_a_relayout_while_zoomed_reshapes_to_the_new_card(out):
    strip = out["strip"]
    relaid = strip["relaid"]
    _one_to_one(relaid)
    _inside(relaid, strip["narrowExtent"])
    col_span = relaid["x"][1] - relaid["x"][0]
    row_span = relaid["y"][1] - relaid["y"][0]
    assert (col_span / row_span == pytest.approx(relaid["aspect"], rel=1e-6)) or row_span == pytest.approx(320)


def test_the_export_of_a_zoomed_strip_is_one_to_one(out):
    exported = out["strip"]["exported"]
    assert exported["pxCol"] == pytest.approx(exported["pxRow"], rel=1e-6)


# ----------------------------------------------------- the absolute frame --

def test_the_absolute_xy_panel_is_one_to_one_at_every_zoom(out):
    lab = out["lab"]
    _one_to_one(lab["rest"])
    for snap in lab["steps"]:
        _one_to_one(snap)
        _inside(snap, lab["extent"])
    # A zoom out ends at the full extent and its own letterbox.
    assert lab["end"]["view"] is None
    assert lab["end"]["grid"] == pytest.approx(lab["rest"]["grid"])
    _one_to_one(lab["fitted"])


def test_an_absolute_depth_panel_is_unchanged(out):
    depth = out["depth"]
    rest = depth["rest"]
    for snap in depth["steps"]:
        # The card is filled at every zoom: the rectangle never moves and nothing is rebuilt.
        assert snap["grid"] == rest["grid"]
        assert snap["rebuilt"] is False
    # Both spans scale by the same factor per notch.
    first = depth["steps"][0]
    col_ratio = (first["x"][1] - first["x"][0]) / (rest["x"][1] - rest["x"][0])
    row_ratio = (first["y"][1] - first["y"][0]) / (rest["y"][1] - rest["y"][0])
    assert col_ratio == pytest.approx(row_ratio)
    assert col_ratio == pytest.approx(1 / 1.18)


def test_an_event_inspector_cell_stays_one_to_one_on_its_window(out):
    inspector = out["inspector"]
    window = inspector["window"]
    for snap in inspector["steps"]:
        _one_to_one(snap)
        _inside(snap, window)
    assert inspector["steps"][-1]["view"] is None
    assert inspector["steps"][-1]["x"] == pytest.approx(window["col"])


# ------------------------------------------------------------ shapeToCard --

def test_shape_to_card(out):
    shape = out["shape"]
    # Row widened to 1000 (2000 / 2), then capped at its 280 mm extent.
    assert shape["capped"] == {"col": [-1000, 1000], "row": [-140, 140]}
    assert shape["inside"] == {"col": [-100, 100], "row": [-50, 50]}
    # 200 × 60 mm is wider than the card: the row is widened to 100 about 130, then slid back inside.
    assert shape["edge"] == {"col": [2200, 2400], "row": [40, 140]}
    assert shape["full"] is None
    assert shape["tall"] == {"col": [-50, 50], "row": [-100, 100]}
    # Without a card the window is only capped and slid inside.
    assert shape["noAspect"] == {"col": [-2400, 1600], "row": [-50, 50]}


def test_a_band_reserved_above_the_plot_reshapes_a_zoom_to_the_smaller_card(out):
    band = out["band"]
    before, after = band["before"], band["after"]
    assert after["aspect"] > before["aspect"]
    _one_to_one(after)
    col_span = after["x"][1] - after["x"][0]
    row_span = after["y"][1] - after["y"][0]
    assert col_span / row_span == pytest.approx(after["aspect"], rel=1e-6)
    assert after["grid"]["top"] > before["grid"]["top"]
    assert band["changed"] == 1
