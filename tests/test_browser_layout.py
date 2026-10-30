"""The page shell in Chromium: the sidebar toggle, the Details drawer, the
two-tier frame control, the D axis and a plot-only export.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks. The grid
tracks snap and ``relayoutAll()`` runs synchronously after each toggle, so
every geometry assertion is taken right after the click, without waiting.
"""

from __future__ import annotations

import os
import struct

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium layout check",
)

_GEOMETRY = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const grid = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const option = inst.getOption();
  const x = option.xAxis[0];
  const y = option.yAxis[0];
  return {
    hostWidth: host.clientWidth, chartWidth: inst.getWidth(),
    gridWidth: grid.width, gridHeight: grid.height,
    xSpan: x.max - x.min, ySpan: y.max - y.min, xName: x.name, yName: y.name,
  };
}"""

_SIDEBAR_WIDTH = "() => document.getElementById('sidebar').getBoundingClientRect().width"
_APP_CLASSES = "() => document.querySelector('.app').className"
_FRAME = "() => document.getElementById('ctl-frame').dataset.frame"
_BODY_TEXT = "() => document.getElementById('inspector-body').textContent"


def _open(p, base, fragment="", viewport=(1600, 900)):
    browser = p.chromium.launch()
    page = browser.new_page(color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]})
    page.goto(f"{base}/{fragment}")
    page.wait_for_function(
        "() => ['plot-xy','plot-yz','plot-xz','plot-energy'].every((id) => "
        "document.getElementById(id)?.querySelector('canvas'))",
        timeout=30_000,
    )
    page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
    # The energy panel renders its fitted-parameter table after every paint.
    page.wait_for_function("() => document.getElementById('fit-table').children.length > 0", timeout=30_000)
    page.wait_for_timeout(200)  # the debounced performance cards settle
    return browser, page


def _px_per_mm(geometry) -> tuple[float, float]:
    return geometry["gridWidth"] / geometry["xSpan"], geometry["gridHeight"] / geometry["ySpan"]


def _assert_isometric(geometry, where: str) -> None:
    along_x, along_y = _px_per_mm(geometry)
    assert along_x == pytest.approx(along_y, rel=0.01), (where, along_x, along_y)


# ----------------------------------------------------------- the sidebar --


def test_the_sidebar_toggle_frees_width_and_keeps_the_xy_panel_isometric(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"])
        before = page.evaluate(_GEOMETRY, "plot-xy")
        _assert_isometric(before, "before")
        sidebar_before = page.evaluate(_SIDEBAR_WIDTH)
        assert sidebar_before > 300

        page.click("#sidebar-toggle")
        assert "is-sidebar-collapsed" in page.evaluate(_APP_CLASSES)
        assert page.evaluate(_SIDEBAR_WIDTH) < 1
        assert page.get_attribute("#sidebar-toggle", "aria-expanded") == "false"
        assert page.evaluate("() => localStorage.getItem('calosrv.sidebar')") == "collapsed"
        after = page.evaluate(_GEOMETRY, "plot-xy")
        assert after["hostWidth"] > before["hostWidth"] + 100
        assert after["chartWidth"] == after["hostWidth"], "the chart was not resized to its container"
        _assert_isometric(after, "collapsed")
        energy = page.evaluate(_GEOMETRY, "plot-energy")
        assert energy["chartWidth"] == energy["hostWidth"], "the energy chart was not resized"

        page.click("#sidebar-toggle")
        assert "is-sidebar-collapsed" not in page.evaluate(_APP_CLASSES)
        assert page.evaluate(_SIDEBAR_WIDTH) == pytest.approx(sidebar_before, abs=1)
        assert page.get_attribute("#sidebar-toggle", "aria-expanded") == "true"
        assert page.evaluate("() => localStorage.getItem('calosrv.sidebar')") == "open"
        restored = page.evaluate(_GEOMETRY, "plot-xy")
        assert restored["hostWidth"] == pytest.approx(before["hostWidth"], abs=1)
        _assert_isometric(restored, "restored")
        browser.close()


def test_the_collapsed_sidebar_is_remembered_across_loads(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"])
        page.evaluate("() => localStorage.setItem('calosrv.sidebar', 'collapsed')")
        page.reload()
        page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')", timeout=30_000)
        assert "is-sidebar-collapsed" in page.evaluate(_APP_CLASSES)
        assert page.evaluate(_SIDEBAR_WIDTH) < 1
        assert page.get_attribute("#sidebar-toggle", "aria-expanded") == "false"
        assert "sidebar" not in page.evaluate("() => window.location.hash")
        browser.close()


# ------------------------------------------------------------ the drawer --


def test_the_details_drawer_follows_the_inspected_card(live_server):
    base = live_server["base"]
    payload = httpx.get(f"{base}/api/projections", params={"table_name": "experiment_baseline"},
                        timeout=30).json()
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, base)
        assert page.evaluate("() => document.getElementById('inspector').hidden") is True

        page.click('button[data-inspect="xy"]')
        assert page.evaluate("() => document.getElementById('inspector').hidden") is False
        assert "is-inspector-open" in page.evaluate(_APP_CLASSES)
        assert page.inner_text("#inspector-title") == page.inner_text("#title-xy")
        assert page.evaluate("() => document.activeElement.id") == "inspector-title"
        assert page.evaluate("() => document.querySelector('.card[data-panel=xy]').classList.contains('is-inspected')")
        # textContent, not inner_text: the section headings are uppercased by CSS.
        body = page.evaluate(_BODY_TEXT)
        assert payload["slab"]["note"] in body
        assert "Selection" in body and "full kinematic range" in body
        assert "Disclosures" in body

        page.click('button[data-inspect="energy"]')
        assert page.inner_text("#inspector-title") == "Reconstructed Energy vs. Separation D"
        body = page.evaluate(_BODY_TEXT)
        assert "Gaussian fits" in body and "Reading the density axis" in body
        assert page.evaluate("() => document.querySelector('.card[data-panel=energy]').classList.contains('is-inspected')")
        assert not page.evaluate("() => document.querySelector('.card[data-panel=xy]').classList.contains('is-inspected')")

        page.click("#title-yz")
        assert page.inner_text("#inspector-title") == page.inner_text("#title-yz")

        page.click("#inspector-close")
        assert page.evaluate("() => document.getElementById('inspector').hidden") is True
        assert "is-inspector-open" not in page.evaluate(_APP_CLASSES)
        assert page.evaluate("() => document.activeElement.dataset.inspect") == "yz"
        browser.close()


def test_escape_closes_the_drawer_but_an_open_overlay_first(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"])
        page.click('button[data-inspect="xy"]')
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('inspector').hidden") is True
        assert page.evaluate("() => document.activeElement.dataset.inspect") == "xy"

        # A modal owns the keypress while it is open.
        page.click('button[data-inspect="xy"]')
        page.click("#open-admin")
        page.wait_for_function("() => !document.getElementById('admin-modal').hidden")
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is True
        assert page.evaluate("() => document.getElementById('inspector').hidden") is False

        # So does the export menu.
        page.click('button[data-export="xy"]')
        page.wait_for_selector(".menu")
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.querySelector('.menu')") is None
        assert page.evaluate("() => document.getElementById('inspector').hidden") is False

        # And a popover.
        page.click("#info-density")
        page.wait_for_selector(".popover")
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.querySelector('.popover')") is None
        assert page.evaluate("() => document.getElementById('inspector').hidden") is False

        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('inspector').hidden") is True
        browser.close()


@pytest.mark.parametrize("viewport", [(1600, 900), (1024, 768)])
def test_opening_the_drawer_relayouts_the_charts(live_server, viewport):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"], "#frame=canonical", viewport)
        before = page.evaluate(_GEOMETRY, "plot-xy")
        _assert_isometric(before, "before")
        yz_before = page.evaluate(_GEOMETRY, "plot-yz")
        page.click('button[data-inspect="xy"]')
        after = page.evaluate(_GEOMETRY, "plot-xy")
        assert after["hostWidth"] < before["hostWidth"] - 100
        assert after["chartWidth"] == after["hostWidth"]
        _assert_isometric(after, "drawer open")
        energy = page.evaluate(_GEOMETRY, "plot-energy")
        assert energy["chartWidth"] == energy["hostWidth"]
        # A D-frame depth panel decides its 1:1 aspect from its width: after the
        # toggle it is either still 1:1 or its notes say it no longer is.
        yz_after = page.evaluate(_GEOMETRY, "plot-yz")
        assert yz_after["chartWidth"] == yz_after["hostWidth"]
        along_x, along_y = _px_per_mm(yz_before)
        if abs(along_x - along_y) <= 0.01 * along_x:
            along_x, along_y = _px_per_mm(yz_after)
            if abs(along_x - along_y) > 0.01 * along_x:
                page.click('button[data-inspect="yz"]')
                assert "not 1:1" in page.evaluate(_BODY_TEXT)
                page.click('button[data-inspect="xy"]')
        page.click("#inspector-close")
        restored = page.evaluate(_GEOMETRY, "plot-xy")
        assert restored["hostWidth"] == pytest.approx(before["hostWidth"], abs=1)
        browser.close()


# ------------------------------------------------------ the frame control --


def test_the_frame_selector_walks_the_two_tiers(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"], "#frame=local")
        assert page.evaluate(_FRAME) == "local"
        assert page.evaluate("() => document.getElementById('frame-sub').hidden") is False
        assert page.is_checked('input[name="frame-sub"][value="local"]')

        page.check('input[name="frame-view"][value="absolute"]')
        assert page.evaluate(_FRAME) == "lab"
        assert page.evaluate("() => document.getElementById('frame-sub').hidden") is True
        # The built-in frame is omitted from the link (the experiment name stays).
        assert "frame=" not in page.evaluate("() => window.location.hash")

        page.check('input[name="frame-view"][value="aligned"]')
        assert page.evaluate(_FRAME) == "canonical", "entering Separation-Aligned lands on Translated"
        assert page.evaluate("() => document.getElementById('frame-sub').hidden") is False
        assert page.is_checked('input[name="frame-sub"][value="canonical"]')
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True
        assert "frame=canonical" in page.evaluate("() => window.location.hash")

        page.check('input[name="frame-sub"][value="local"]')
        assert page.evaluate(_FRAME) == "local"
        assert "frame=local" in page.evaluate("() => window.location.hash")
        browser.close()


def test_a_trans_link_reveals_the_legacy_sub_option(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"], "#frame=trans")
        assert page.evaluate(_FRAME) == "trans"
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is False
        assert page.is_checked('input[name="frame-sub"][value="trans"]')
        assert page.is_checked('input[name="frame-view"][value="aligned"]')
        page.check('input[name="frame-sub"][value="canonical"]')
        assert page.evaluate(_FRAME) == "canonical"
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True

        # Leaving the legacy frame through the primary tier never returns to it.
        browser.close()
        browser, page = _open(p, live_server["base"], "#frame=trans")
        page.check('input[name="frame-view"][value="absolute"]')
        assert page.evaluate(_FRAME) == "lab"
        assert page.evaluate("() => document.getElementById('frame-sub').hidden") is True
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True
        assert "frame=" not in page.evaluate("() => window.location.hash")
        page.check('input[name="frame-view"][value="aligned"]')
        assert page.evaluate(_FRAME) == "canonical"
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True
        browser.close()


def test_the_separation_aligned_entry_panel_writes_its_axis_as_d(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"], "#frame=canonical")
        page.wait_for_function("() => document.getElementById('title-xy').textContent.startsWith('D–Y′')",
                               timeout=30_000)
        xy = page.evaluate(_GEOMETRY, "plot-xy")
        assert xy["xName"].startswith("D") and xy["yName"].startswith("y′")
        xz = page.evaluate(_GEOMETRY, "plot-xz")
        assert xz["yName"].startswith("x′") and xz["xName"].startswith("z′")
        yz = page.evaluate(_GEOMETRY, "plot-yz")
        assert yz["xName"].startswith("z′") and yz["yName"].startswith("y′")
        # The hover readout names the axis the same way.
        box = page.locator("#plot-xy").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        page.wait_for_function("() => [...document.querySelectorAll('.calo-tooltip')]"
                               ".some((t) => t.innerText.trim().length > 0)", timeout=10_000)
        first_line = page.evaluate(
            "() => [...document.querySelectorAll('.calo-tooltip')]"
            ".map((t) => t.innerText.trim()).filter(Boolean).pop().split('\\n')[0]")
        assert first_line.startswith("D = "), first_line
        browser.close()


# ---------------------------------------------------- on-screen disclosures --


_LAST_PROJECTIONS_URL = """() => performance.getEntriesByType('resource')
  .map((e) => e.name).filter((n) => n.includes('/api/projections')).pop()"""


def _page_payload(page, base):
    """The projections response the page itself last asked for."""
    url = page.evaluate(_LAST_PROJECTIONS_URL)
    assert url, "the page made no projections request"
    return httpx.get(url, timeout=30).json()


def test_disclosures_stay_on_screen_without_the_drawer(live_server):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, base, "#frame=canonical")
        page.wait_for_function("() => document.getElementById('stat-rho').textContent !== '—'", timeout=30_000)
        payload = _page_payload(page, base)
        assert page.inner_text("#stat-rho").strip() != "—"
        below = payload["panels"]["xy"].get("below_floor_cells") or 0
        expected = f"{below:,} bin{'' if below == 1 else 's'} below floor" if below > 0 else "—"
        assert page.inner_text("#stat-clipped").strip() == expected
        notices = page.get_attribute("#info-frame", "data-notices") or "[]"
        assert payload["frame"]["comb"]["note"] in notices
        assert page.evaluate("() => document.getElementById('inspector').hidden") is True
        browser.close()

        # The absolute frame counts the cells clipped to the ends of the ramp.
        browser, page = _open(p, base)
        payload = _page_payload(page, base)
        scale = payload["panels"]["xy"]["scale"]
        n = (scale.get("clipped_low") or 0) + (scale.get("clipped_high") or 0)
        expected = f"{n:,} cell{'' if n == 1 else 's'}" if n > 0 else "—"
        assert page.inner_text("#stat-clipped").strip() == expected
        browser.close()


# ------------------------------------------------------------- the export --


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _download(page, panel_id: str, label: str):
    page.click(f'button[data-export="{panel_id}"]')
    page.wait_for_selector(".menu")
    with page.expect_download() as download:
        page.click(f".menu-item:has-text('{label}')")
    return download.value.path()


def test_exports_are_the_plot_alone(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _open(p, live_server["base"])
        svg = open(_download(page, "xy", "SVG — single column"), encoding="utf-8").read()
        assert "figure-disclosure" not in svg
        for text in ("Experiment ", "full kinematic range", "Window ", "Dashed line"):
            assert text not in svg, text
        assert 'width="321"' in svg
        svg_height = int(svg.split('height="', 1)[1].split('"', 1)[0])

        png = open(_download(page, "xy", "PNG 300 DPI — single column"), "rb").read()
        width, height = _png_size(png)
        assert width == pytest.approx(321 * 300 / 96, abs=2)
        assert height / (300 / 96) == pytest.approx(svg_height, abs=2)

        energy = open(_download(page, "energy", "SVG — single column"), encoding="utf-8").read()
        assert "figure-disclosure" not in energy and "μ [GeV]" not in energy and "Estimator" not in energy
        browser.close()
