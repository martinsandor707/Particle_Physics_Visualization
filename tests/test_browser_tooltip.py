"""Chart tooltips are readable and keep the hovered panel visible - measured in Chromium.

The source pins in `test_export_assets.py` check the option; this module
checks what a reader sees. It boots the real application on a local port,
loads the real page with the real stylesheet and the vendored ECharts, and
hovers each of the four charts: a 9 x 7 grid of pointer positions, a sweep
along the middle row of every projection's plot at 8 px steps, and on the
three projections every scatter mark (the centroid and anchor markers, whose
tooltips carry the longest explanations). It does so at three viewports:
1600 x 900 and 1280 x 800 (two columns) and 1024 x 768 (one column).

For every tooltip that appears it asserts that the tip

* is mounted on `#tooltip-layer`, a fixed layer the size of the viewport, and
  no ancestor clips it. The original bug was `.main`'s overflow box cutting
  the tip off where it met the sidebar.
* lies wholly inside the viewport, and is what `elementFromPoint` finds at its
  corners and centre (pointer events briefly enabled), so nothing covers it.
* does not sit on the pointer.
* if it is a plain bin readout (coordinates first, no overlay), sits exactly
  beside the pointer. Choosing by size once made it jump to the next panel
  from one bin to the next.
* if it is an explanation (a mark's or an overlay's, or any tip on plot 4),
  covers none of the hovered chart. `confine: true` had kept such tips inside
  the chart, over a median 35% of the plot at 1600 x 900.

Three scenarios from the review are replayed on their own:

* a scroll of `.main`, then a drag that leaves the chart, then a re-hover.
  zrender's cached transforms once drew the tip 120-240 px from its place.
* a window that shrinks after a hover. A hidden tip on `<body>` once made the
  document taller than the window.
* a scroll while a tip is shown. It must hide at once.

Opt-in (`CALOSRV_BROWSER_TESTS=1`): it needs Playwright's Chromium and takes
a few minutes, which the default suite should not.
"""

from __future__ import annotations

import os
import re
import socket
import threading
import time

import pytest

from conftest import SEED_CSV

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium tooltip check",
)

VIEWPORTS = ((1600, 900), (1280, 800), (1024, 768))
PLOTS = ("plot-xy", "plot-yz", "plot-xz", "plot-energy")
GRID_X = tuple(0.1 + 0.1 * i for i in range(9))    # 9 columns
GRID_Y = tuple(0.15 + 0.7 * j / 6 for j in range(7))  # 7 rows
SWEEP_STEP_PX = 8
#: `READOUT_GAP_PX` in static/js/panels/tooltip.js, and the readout's lift.
GAP_PX, LIFT_PX = 12, 8
#: The plain readout's first line: a coordinate in millimetres.
COORDINATE = re.compile(r"^\S+ = [\u2212-]?[\d.]+ mm$")

_PROBE = """([plotId, px, py]) => {
  const tips = [...document.querySelectorAll('.calo-tooltip')].filter((t) => {
    const cs = getComputedStyle(t);
    const b = t.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0.5
      && b.width > 0 && b.height > 0 && t.innerText.trim().length > 0;
  });
  if (!tips.length) return null;
  const tip = tips[tips.length - 1];
  const r = tip.getBoundingClientRect();
  const host = document.getElementById(plotId);
  const c = host.getBoundingClientRect();
  const g = echarts.getInstanceByDom(host).getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  const previous = tip.style.pointerEvents;
  tip.style.pointerEvents = 'auto';
  const points = [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2],
                  [r.right - 2, r.bottom - 2], [(r.left + r.right) / 2, (r.top + r.bottom) / 2]];
  const onTop = points.map(([x, y]) => {
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit && (hit === tip || tip.contains(hit)));
  });
  tip.style.pointerEvents = previous;
  const clippers = [];
  for (let a = tip.parentElement; a && a !== document.documentElement; a = a.parentElement) {
    const cs = getComputedStyle(a);
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
      const b = a.getBoundingClientRect();
      clippers.push({ id: a.id || a.className || a.tagName, rect: [b.left, b.top, b.right, b.bottom] });
    }
  }
  return {
    tip: { left: r.left, top: r.top, right: r.right, bottom: r.bottom },
    chart: { left: c.left, top: c.top, right: c.right, bottom: c.bottom },
    plot: { left: c.left + g.x, top: c.top + g.y, right: c.left + g.x + g.width, bottom: c.top + g.y + g.height },
    viewport: [vw, vh], onTop, clippers, parent: tip.parentElement.id, className: tip.className,
    overlay: /border-top:\\s*1px solid/.test(tip.innerHTML),
    firstLine: tip.innerText.split('\\n')[0].trim(), text: tip.innerText.slice(0, 120),
  };
}"""

_MARKS = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const c = host.getBoundingClientRect();
  const out = [];
  (inst.getOption().series || []).forEach((s, i) => {
    if (s.type !== 'scatter' || !s.data || !s.data.length || !s.tooltip) return;
    const d = Array.isArray(s.data[0]) ? s.data[0] : s.data[0].value;
    const p = inst.convertToPixel({ seriesIndex: i }, d);
    if (p && Number.isFinite(p[0]) && p[0] >= 0 && p[1] >= 0 && p[0] <= c.width && p[1] <= c.height) {
      out.push({ name: s.name, x: c.left + p[0], y: c.top + p[1] });
    }
  });
  return out;
}"""

_PLOT_RECT = """(plotId) => {
  const host = document.getElementById(plotId);
  const c = host.getBoundingClientRect();
  const g = echarts.getInstanceByDom(host).getModel().getComponent('grid', 0).coordinateSystem.getRect();
  return { left: c.left + g.x, top: c.top + g.y, right: c.left + g.x + g.width, bottom: c.top + g.y + g.height };
}"""

_DOCUMENT = """() => ({ sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight,
  cw: document.documentElement.clientWidth, ch: document.documentElement.clientHeight })"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """The real app on a real port, seeded from the demonstration CSV."""
    playwright = pytest.importorskip("playwright.sync_api")
    import uvicorn

    from calosrv.app import create_app
    from calosrv.config import load_settings
    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache

    if not SEED_CSV.is_file():
        pytest.skip("Demonstration CSV not present")

    reset_database()
    reset_job_store()
    reset_cache()
    os.environ["CALOSRV_DATA_DIR"] = str(tmp_path_factory.mktemp("browser-data"))
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(SEED_CSV)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(load_settings()), host="127.0.0.1", port=port, log_level="warning",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import httpx

    base = f"http://127.0.0.1:{port}"
    for _ in range(240):
        try:
            payload = httpx.get(f"{base}/api/experiments", timeout=2).json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
        except Exception:
            pass
        time.sleep(0.25)
    else:
        server.should_exit = True
        pytest.fail("the server never reported a ready experiment")

    yield {"base": base, "playwright": playwright}

    server.should_exit = True
    thread.join(timeout=10)
    reset_database()
    reset_job_store()
    reset_cache()


def _open(p, live_server, viewport, fragment):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    page.goto(f"{live_server['base']}/{fragment}")
    page.wait_for_function(
        "() => ['plot-xy','plot-yz','plot-xz','plot-energy'].every((id) => "
        "document.getElementById(id)?.querySelector('canvas'))",
        timeout=30_000,
    )
    page.wait_for_timeout(1500)  # the three projections and plot 4 settle
    return browser, page


def _measure(live_server, viewport, fragment):
    results = []
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server, viewport, fragment)
        for plot in PLOTS:
            element = page.locator(f"#{plot}")
            element.scroll_into_view_if_needed()
            page.wait_for_timeout(100)
            box = element.bounding_box()
            assert box, plot
            targets = [("grid", box["x"] + fx * box["width"], box["y"] + fy * box["height"])
                       for fx in GRID_X for fy in GRID_Y]
            if plot != "plot-energy":
                rect = page.evaluate(_PLOT_RECT, plot)
                y = (rect["top"] + rect["bottom"]) / 2
                x = rect["left"] + 2
                while x < rect["right"] - 2:
                    targets.append(("sweep", x, y))
                    x += SWEEP_STEP_PX
                targets += [(f"mark {m['name']}", m["x"], m["y"]) for m in page.evaluate(_MARKS, plot)]
            for kind, x, y in targets:
                page.mouse.move(x, y)
                page.wait_for_timeout(40)
                probe = page.evaluate(_PROBE, [plot, x, y])
                if probe is not None:
                    results.append((plot, kind, (x, y), probe))
            page.mouse.move(1, 1)
            page.wait_for_timeout(100)
        browser.close()
    return results


def _overlap(a, b) -> float:
    return max(0.0, min(a["right"], b["right"]) - max(a["left"], b["left"])) * max(
        0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))


def _room_outside(tip, around, vw, vh, edge=4) -> bool:
    """Whether a tip of this size fits on some side of `around` inside the viewport."""
    w, h = tip["right"] - tip["left"], tip["bottom"] - tip["top"]
    fits_w, fits_h = w <= vw - 2 * edge, h <= vh - 2 * edge
    return ((around["right"] + GAP_PX + w <= vw - edge and fits_h)
            or (around["left"] - GAP_PX - w >= edge and fits_h)
            or (around["bottom"] + GAP_PX + h <= vh - edge and fits_w)
            or (around["top"] - GAP_PX - h >= edge and fits_w))


def _is_readout(plot, probe) -> bool:
    return plot != "plot-energy" and not probe["overlay"] and bool(COORDINATE.match(probe["firstLine"]))


def _beside(tip, x, y) -> bool:
    """Right or left of the pointer by the gap, or above or below it by the gap."""
    horizontal = abs(tip["left"] - (x + GAP_PX)) < 1.5 or abs(tip["right"] - (x - GAP_PX)) < 1.5
    vertical = (abs(tip["bottom"] - (y - GAP_PX)) < 1.5 or abs(tip["top"] - (y + GAP_PX)) < 1.5) \
        and tip["left"] - 0.5 <= x <= tip["right"] + 0.5
    return horizontal or vertical


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize(
    "fragment", ["", "#frame=trans", "#frame=local", "#frame=canonical"],
    ids=["default-lab", "trans", "local", "canonical"],
)
def test_tooltips_are_readable_and_keep_the_hovered_panel_visible(live_server, viewport, fragment):
    results = _measure(live_server, viewport, fragment)
    assert results, "no tooltip appeared anywhere"
    shown = {plot for plot, *_ in results}
    assert {"plot-xy", "plot-yz", "plot-xz"} & shown, shown
    readouts = explanations = 0
    for plot, kind, (x, y), probe in results:
        where = f"{plot} {kind} at ({x:.0f}, {y:.0f}), viewport {viewport}"
        tip, (vw, vh) = probe["tip"], probe["viewport"]
        assert probe["className"] == "calo-tooltip", where
        assert probe["parent"] == "tooltip-layer", f"{where}: mounted in {probe['parent']!r}"
        assert probe["clippers"] == [], f"{where}: clipped by {probe['clippers']}"
        assert tip["left"] >= -0.5 and tip["top"] >= -0.5 and tip["right"] <= vw + 0.5 \
            and tip["bottom"] <= vh + 0.5, f"{where}: tooltip {tip} leaves the viewport"
        assert all(probe["onTop"]), f"{where}: something is drawn over the tooltip"
        assert not (tip["left"] <= x <= tip["right"] and tip["top"] <= y <= tip["bottom"]), (
            f"{where}: the tooltip sits on the pointer")
        if _is_readout(plot, probe):
            readouts += 1
            assert _beside(tip, x, y), f"{where}: the bin readout left the pointer ({tip})"
        else:
            # Off the chart wherever it fits on some side of it; failing that, off the
            # plot - only the panel's own axes and margins may then be covered.
            explanations += 1
            size = f"{tip['right'] - tip['left']:.0f} x {tip['bottom'] - tip['top']:.0f} px"
            if _room_outside(tip, probe["chart"], vw, vh):
                assert _overlap(tip, probe["chart"]) < 0.5, (
                    f"{where}: a {size} explanation covers the chart it explains ({probe['text'][:60]!r})")
            elif _room_outside(tip, probe["plot"], vw, vh):
                assert _overlap(tip, probe["plot"]) < 0.5, (
                    f"{where}: a {size} explanation covers the plot it explains ({probe['text'][:60]!r})")
    assert readouts and explanations, (readouts, explanations)


def _hover_readout(page, plot, fractions=(0.5, 0.4, 0.6, 0.3, 0.7)):
    """Hover `plot` until a plain bin readout shows; return the pointer and the probe."""
    rect = page.evaluate(_PLOT_RECT, plot)
    for fy in fractions:
        for fx in fractions:
            x = rect["left"] + fx * (rect["right"] - rect["left"])
            y = rect["top"] + fy * (rect["bottom"] - rect["top"])
            page.mouse.move(x, y)
            page.wait_for_timeout(60)
            probe = page.evaluate(_PROBE, [plot, x, y])
            if probe and _is_readout(plot, probe):
                return (x, y), probe
    return None, None


@pytest.mark.parametrize("plot,scroll_from,scroll_to", [("plot-xy", 0, 120), ("plot-xz", 600, 360)])
def test_a_tip_lands_where_it_was_placed_after_a_scroll_and_a_drag(live_server, plot, scroll_from, scroll_to):
    """zrender's forward and inverse transforms share one validity check."""
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server, (1600, 900), "#frame=canonical")
        page.evaluate(f"() => {{ document.querySelector('.main').scrollTop = {scroll_from}; }}")
        page.wait_for_timeout(200)
        point, probe = _hover_readout(page, plot)
        assert probe, "no readout before the scroll"
        page.mouse.move(100, 400)
        page.wait_for_timeout(200)
        page.evaluate(f"() => {{ document.querySelector('.main').scrollTop = {scroll_to}; }}")
        page.wait_for_timeout(200)
        box = page.locator(f"#{plot}").bounding_box()
        mx, my = box["x"] + 4, box["y"] + box["height"] - 4   # the chart margin, not the raster
        page.mouse.move(mx, my)
        page.mouse.down()
        page.mouse.move(mx + 2, my)
        page.mouse.move(60, my, steps=4)                       # leave the chart while captured
        page.mouse.up()
        # The drag panned the view; restore it from the card's own button, which
        # leaves zrender's cached transforms exactly as the drag left them.
        page.click(f"button[data-reset='{plot.removeprefix('plot-')}']")
        page.mouse.move(100, 400)
        page.wait_for_timeout(200)
        point, probe = _hover_readout(page, plot)
        browser.close()
    assert probe, "no readout after the scroll and the drag"
    x, y = point
    assert _beside(probe["tip"], x, y), f"the tip was drawn away from its place: {probe['tip']} for {point}"
    assert abs(probe["tip"]["top"] - (y - LIFT_PX)) < 1.5, (probe["tip"], point)


def test_a_hidden_tip_never_grows_the_document(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server, (1600, 900), "#frame=canonical")
        page.evaluate("() => { document.querySelector('.main').scrollTop = 360; }")
        page.wait_for_timeout(200)
        point, probe = _hover_readout(page, "plot-xz", fractions=(0.8, 0.9, 0.7, 0.6))
        assert probe, "no readout near the bottom of the window"
        page.mouse.move(100, 400)
        page.wait_for_timeout(200)
        page.set_viewport_size({"width": 1600, "height": 700})
        page.wait_for_timeout(300)
        after = page.evaluate(_DOCUMENT)
        browser.close()
    assert after["sh"] == after["ch"] and after["sw"] == after["cw"], after


def test_a_scroll_hides_the_tip_at_once(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server, (1600, 900), "")
        marks = page.evaluate(_MARKS, "plot-xy")
        assert marks, "no mark on the XY panel"
        page.mouse.move(marks[0]["x"], marks[0]["y"])
        page.wait_for_timeout(80)
        assert page.evaluate(_PROBE, ["plot-xy", marks[0]["x"], marks[0]["y"]]), "no tip on the mark"
        page.evaluate("() => { document.querySelector('.main').scrollTop += 150; }")
        page.wait_for_timeout(40)
        left = page.evaluate(_PROBE, ["plot-xy", marks[0]["x"], marks[0]["y"]])
        browser.close()
    assert left is None, f"the tip stayed after the scroll: {left}"
