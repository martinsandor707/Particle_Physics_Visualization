"""An isometric panel's plot follows the displayed window, in Chromium.

The D-frame's entry panel (D–Y′) of the demonstration selection is a strip
some four times wider than tall at rest. A wheel zoom or Auto-fit RoI shapes
the window to the card (``projection.js`` ``shapeToCard``) and the plot is
letterboxed from the window, so the plot grows into the card while one
millimetre stays the same number of pixels on both axes (CLAUDE.md section 2,
1:1 for detector geometry); Reset returns to the strip.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium zoom check",
)

#: Where a screenshot of the panel before and after a zoom is left, when the folder exists.
SHOTS = Path(os.environ.get("CALOSRV_ZOOM_SHOTS", ""))

_GEOMETRY = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const grid = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const option = inst.getOption();
  const x = option.xAxis[0];
  const y = option.yAxis[0];
  return { gridWidth: grid.width, gridHeight: grid.height, x: [x.min, x.max], y: [y.min, y.max],
    hostWidth: host.clientWidth, hostHeight: host.clientHeight };
}"""


def _px_per_mm(g) -> tuple[float, float]:
    return g["gridWidth"] / (g["x"][1] - g["x"][0]), g["gridHeight"] / (g["y"][1] - g["y"][0])


def _assert_isometric(g, where: str) -> None:
    along_x, along_y = _px_per_mm(g)
    assert along_x == pytest.approx(along_y, rel=0.01), (where, g)


def _shot(page, name: str) -> None:
    if SHOTS.name and SHOTS.is_dir():
        page.locator('.card[data-panel="xy"]').screenshot(path=str(SHOTS / name))


def test_a_zoom_of_the_d_frame_entry_panel_grows_the_plot_and_keeps_one_to_one(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{live_server['base']}/#frame=canonical")
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
        page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')", timeout=30_000)
        page.wait_for_timeout(300)

        rest = page.evaluate(_GEOMETRY, "plot-xy")
        _assert_isometric(rest, "at rest")
        # A strip at rest: it does not fill the card's height.
        assert rest["gridHeight"] < 0.7 * rest["hostHeight"]
        _shot(page, "zoom_canonical_xy_rest.png")

        plot = page.locator("#plot-xy")
        plot.scroll_into_view_if_needed()
        box = plot.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        heights = [rest["gridHeight"]]
        for _ in range(4):
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(80)
            g = page.evaluate(_GEOMETRY, "plot-xy")
            _assert_isometric(g, "wheel zoom")
            heights.append(g["gridHeight"])
        assert all(b >= a - 0.5 for a, b in zip(heights, heights[1:])), heights
        assert heights[-1] > 1.3 * heights[0], heights
        _shot(page, "zoom_canonical_xy_wheel.png")

        page.click('button[data-reset="xy"]')
        reset = page.evaluate(_GEOMETRY, "plot-xy")
        assert reset["gridHeight"] == pytest.approx(rest["gridHeight"], abs=0.5)
        assert reset["x"] == pytest.approx(rest["x"]) and reset["y"] == pytest.approx(rest["y"])

        page.click('button[data-roi="xy"]')
        page.wait_for_timeout(80)
        fitted = page.evaluate(_GEOMETRY, "plot-xy")
        _assert_isometric(fitted, "auto-fit")
        if fitted["x"] != pytest.approx(rest["x"]):
            # A fit tightened something: its window fills the card, the plot taller than the strip.
            assert fitted["gridHeight"] > rest["gridHeight"] + 1
            _shot(page, "zoom_canonical_xy_autofit.png")
        assert errors == []
        browser.close()
