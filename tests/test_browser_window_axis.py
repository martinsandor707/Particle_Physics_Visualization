"""The windowed ensemble axis in Chromium: zooming a depth panel of the
absolute frame asks for it and draws it; Reset drops it.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks. The
expectation is read from the API for the window the panel actually shows,
so the test holds whatever the demonstration events happen to be.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium windowed-axis check",
)

TABLE = "experiment_baseline"
# The raster series carries an id and no name, so names are read with a fallback.
_SERIES = "(plotId) => echarts.getInstanceByDom(document.getElementById(plotId)).getOption().series.map((s) => s.name || '')"
_VIEW = """(plotId) => {
  const o = echarts.getInstanceByDom(document.getElementById(plotId)).getOption();
  return { z: [o.xAxis[0].min, o.xAxis[0].max], t: [o.yAxis[0].min, o.yAxis[0].max] };
}"""
_WINDOWED = "(plotId) => %s(plotId).filter((n) => n.startsWith('Windowed axis'))" % f"({_SERIES})"
_BODY_TEXT = "() => document.getElementById('inspector-body').textContent"


def test_a_zoomed_depth_panel_draws_the_windowed_axis_and_reset_drops_it(live_server):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{base}/")
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
        page.wait_for_function("() => document.getElementById('plot-xz')?.querySelector('canvas')", timeout=30_000)
        page.wait_for_timeout(300)

        assert page.evaluate(_WINDOWED, "plot-xz") == [], "nothing of the kind at full extent"
        full = page.evaluate(_VIEW, "plot-xz")

        # One wheel notch over the plot zooms both axes by the same factor.
        plot = page.locator("#plot-xz")
        plot.scroll_into_view_if_needed()
        box = plot.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.5)
        page.mouse.wheel(0, -240)
        page.wait_for_function(
            f"() => ({_VIEW})('plot-xz').t[1] - ({_VIEW})('plot-xz').t[0] < {full['t'][1] - full['t'][0]} * 0.95",
            timeout=10_000)
        view = page.evaluate(_VIEW, "plot-xz")
        expected = httpx.get(f"{base}/api/window-axis", params={
            "table_name": TABLE, "panel": "xz", "t_min": view["t"][0], "t_max": view["t"][1]}, timeout=30).json()
        drawn = [s for s in ("a", "b") if expected[s]["axis"]]

        if drawn:
            page.wait_for_function(
                "([plotId, wanted]) => { const names = echarts.getInstanceByDom(document.getElementById(plotId))"
                ".getOption().series.map((s) => s.name || ''); return wanted.every((w) => names.includes(w)); }",
                arg=["plot-xz", [f"Windowed axis — {s.upper()}" for s in drawn]], timeout=10_000)
            names = page.evaluate(_WINDOWED, "plot-xz")
            for s in drawn:
                label = s.upper()
                assert f"Windowed axis — {label}" in names
                if expected[s]["band"]:
                    assert f"Windowed axis {label} — spread" in names and f"Windowed axis {label} — 95% interval" in names
                else:
                    assert f"Windowed axis {label} — spread" not in names, "one event gets no band"
            page.click('button[data-inspect="xz"]')
            body = page.evaluate(_BODY_TEXT)
            assert "Windowed ensemble axis" in body and "Marks and legend" in body
            assert expected["notes"][0] in body
            assert "centre of deposited energy" in body or "individual incident trajectories" in body
        else:
            page.wait_for_timeout(800)
            assert page.evaluate(_WINDOWED, "plot-xz") == []

        page.click('button[data-reset="xz"]')
        page.wait_for_function(f"() => ({_WINDOWED})('plot-xz').length === 0", timeout=10_000)
        assert page.evaluate(_VIEW, "plot-xz") == full
        assert errors == [], errors
        browser.close()
