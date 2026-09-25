"""The hover tooltip never slips under the control sidebar - measured in Chromium.

The source pins in `test_export_assets.py` check that `confine: true` is set;
this module checks what a reader sees. It boots the real application on a local
port, loads the real page with the real stylesheet and the vendored ECharts,
and hovers a 9 x 7 grid of pointer positions over each of the four charts at
two viewports: 1600 x 900 (two columns) and 1024 x 768 (one column, where every
chart sits against the sidebar). For every tooltip that appears it asserts

* the tooltip's left edge is not left of its chart's left edge (`confine`), and
* none of the tooltip's four corners resolves to the sidebar under
  `elementFromPoint` - the symptom the user reported.

Before the fix the XY readout started 41 px left of `.main` at 1600 x 900 and
`elementFromPoint` there returned the sidebar.

Opt-in (`CALOSRV_BROWSER_TESTS=1`): it needs Playwright's Chromium and takes
tens of seconds, which the default suite should not.
"""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest

from conftest import SEED_CSV

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium tooltip check",
)

VIEWPORTS = ((1600, 900), (1024, 768))
PLOTS = ("plot-xy", "plot-yz", "plot-xz", "plot-energy")
GRID_X = tuple(0.1 + 0.1 * i for i in range(9))    # 9 columns
GRID_Y = tuple(0.15 + 0.7 * j / 6 for j in range(7))  # 7 rows

_PROBE = """([plotId]) => {
  const tips = [...document.querySelectorAll('.calo-tooltip')].filter((t) => {
    const cs = getComputedStyle(t);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0.01
      && t.getBoundingClientRect().width > 0;
  });
  if (!tips.length) return null;
  const tip = tips[tips.length - 1];
  const r = tip.getBoundingClientRect();
  const plot = document.getElementById(plotId).getBoundingClientRect();
  const sidebar = document.querySelector('.sidebar');
  const previous = tip.style.pointerEvents;
  tip.style.pointerEvents = 'auto';
  const corners = [[r.left + 1, r.top + 1], [r.right - 1, r.top + 1],
                   [r.left + 1, r.bottom - 1], [r.right - 1, r.bottom - 1]];
  const inSidebar = corners.map(([x, y]) => {
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit && sidebar.contains(hit));
  });
  tip.style.pointerEvents = previous;
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
           plotLeft: plot.left, plotRight: plot.right, inSidebar,
           className: tip.className };
}"""


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


def _measure(live_server, viewport, fragment):
    results = []
    with live_server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        page.goto(f"{live_server['base']}/{fragment}")
        page.wait_for_function(
            "() => ['plot-xy','plot-yz','plot-xz','plot-energy'].every((id) => "
            "document.getElementById(id)?.querySelector('canvas'))",
            timeout=30_000,
        )
        page.wait_for_timeout(1500)  # the three projections and plot 4 settle
        for plot in PLOTS:
            element = page.locator(f"#{plot}")
            element.scroll_into_view_if_needed()
            box = element.bounding_box()
            assert box, plot
            for fx in GRID_X:
                for fy in GRID_Y:
                    page.mouse.move(box["x"] + fx * box["width"], box["y"] + fy * box["height"])
                    page.wait_for_timeout(40)
                    probe = page.evaluate(_PROBE, [plot])
                    if probe is not None:
                        results.append((plot, fx, fy, probe))
            page.mouse.move(1, 1)
        browser.close()
    return results


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("fragment", ["", "#frame=lab"], ids=["default", "lab"])
def test_no_tooltip_is_clipped_behind_the_sidebar(live_server, viewport, fragment):
    results = _measure(live_server, viewport, fragment)
    assert results, "no tooltip appeared anywhere on the grid"
    shown = {plot for plot, *_ in results}
    assert {"plot-xy", "plot-yz", "plot-xz"} & shown, shown
    for plot, fx, fy, probe in results:
        where = f"{plot} at ({fx:.2f}, {fy:.2f}) of the chart, viewport {viewport}"
        assert probe["className"] == "calo-tooltip", where
        assert probe["left"] >= probe["plotLeft"] - 0.5, (
            f"{where}: tooltip left {probe['left']:.1f} is left of the chart edge "
            f"{probe['plotLeft']:.1f}"
        )
        assert not any(probe["inSidebar"]), f"{where}: a tooltip corner is behind the sidebar"
