"""The Event Inspector and the compare-frames view in Chromium.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks. One
event of the demonstration dataset is pinned through the link, the picker
and the notebook's seeded rule; the nine panels are read back for their
geometry - isometric, one window - and the drawer and the export are checked
to be what the directive asks for.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Event Inspector check",
)

TABLE = "experiment_baseline"
ROWS = ("lab", "trans", "local")
COLS = ("xy", "xz", "yz")

_GEOMETRY = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  if (!inst) return null;
  const grid = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const option = inst.getOption();
  const x = option.xAxis[0];
  const y = option.yAxis[0];
  return {
    hostWidth: host.clientWidth, chartWidth: inst.getWidth(),
    gridWidth: grid.width, gridHeight: grid.height,
    xSpan: x.max - x.min, ySpan: y.max - y.min, xName: x.name, yName: y.name,
    series: option.series.length,
  };
}"""
_HIDDEN = "(id) => document.getElementById(id).hidden"
_TEXT = "(id) => document.getElementById(id).textContent"
_HASH = "() => window.location.hash"


def _open(p, base, fragment="", viewport=(1600, 900)):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/{fragment}")
    page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
    return browser, page, errors


def _wait_for_event_grid(page):
    page.wait_for_function("() => document.getElementById('event-grid-label').textContent !== '—'", timeout=30_000)
    page.wait_for_function(
        "() => ['lab','trans','local'].every((r) => ['xy','xz','yz'].every((c) => "
        "document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))", timeout=30_000)


def _px_per_mm(geometry) -> tuple[float, float]:
    return geometry["gridWidth"] / geometry["xSpan"], geometry["gridHeight"] / geometry["ySpan"]


def _picked(base) -> int:
    return httpx.get(f"{base}/api/event/pick", params={"table_name": TABLE}, timeout=30).json()["event_number"]


# ------------------------------------------------------ the nine panels --


def test_the_event_inspector_draws_nine_isometric_panels_in_one_window(live_server):
    base = live_server["base"]
    n = _picked(base)
    body = httpx.get(f"{base}/api/event", params={"table_name": TABLE, "event_number": n, "shower": "b"},
                     timeout=30).json()
    half = body["window"]["half_mm"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, f"#event={n}&shower=b")
        _wait_for_event_grid(page)
        assert page.evaluate(_HIDDEN, "ensemble-grid") is True
        assert page.evaluate(_HIDDEN, "event-grid") is False
        assert page.evaluate(_HIDDEN, "compare-grid") is True
        for row in ROWS:
            for col in COLS:
                g = page.evaluate(_GEOMETRY, f"plot-event-{row}-{col}")
                assert g, (row, col)
                along_x, along_y = _px_per_mm(g)
                assert along_x == pytest.approx(along_y, rel=0.01), (row, col, along_x, along_y)
                # The axes span the notebook's one window, on every panel of every frame.
                assert g["xSpan"] == pytest.approx(2 * half, rel=1e-6), (row, col)
                assert g["ySpan"] == pytest.approx(2 * half, rel=1e-6), (row, col)
                assert g["chartWidth"] == g["hostWidth"]
        symbols = body["frames"]["local"]["symbols"]
        local_xz = page.evaluate(_GEOMETRY, "plot-event-local-xz")
        assert local_xz["xName"].startswith(symbols["z"]) and local_xz["yName"].startswith(symbols["x"])
        lab_xy = page.evaluate(_GEOMETRY, "plot-event-lab-xy")
        assert lab_xy["xName"].startswith("x") and lab_xy["yName"].startswith("y")
        # The picker reflects the link, and the label is the notebook's row label.
        assert page.input_value("#event-number") == str(n)
        assert page.is_checked('input[name="event-shower"][value="b"]')
        assert page.evaluate(_TEXT, "event-status") == f"event {n}"
        label = page.evaluate(_TEXT, "event-grid-label")
        assert label.startswith(f"Event {n:,}, shower B:") and "θ = " in label and "P₀ = " in label
        assert "principal axis" in label
        assert page.evaluate(_HIDDEN, "event-close") is False

        # The bin readout over the brightest local bin names the areal density and its unit.
        panel = body["frames"]["local"]["panels"]["xy"]
        top, axes, (rows, cols) = panel["topk"][0], panel["axes"], panel["shape"]
        cx = axes["col"]["lo"] + (top["j"] + 0.5) * (axes["col"]["hi"] - axes["col"]["lo"]) / cols
        cy = axes["row"]["lo"] + (top["i"] + 0.5) * (axes["row"]["hi"] - axes["row"]["lo"]) / rows
        plot = page.locator("#plot-event-local-xy")
        plot.scroll_into_view_if_needed()
        px = page.evaluate("([x, y]) => echarts.getInstanceByDom(document.getElementById('plot-event-local-xy'))"
                           ".convertToPixel({gridIndex: 0}, [x, y])", [cx, cy])
        box = plot.bounding_box()
        page.mouse.move(box["x"] + px[0] - 2, box["y"] + px[1] - 2)
        page.mouse.move(box["x"] + px[0], box["y"] + px[1], steps=2)
        page.wait_for_function("() => [...document.querySelectorAll('.calo-tooltip')]"
                               ".some((t) => t.innerText.trim().length > 0)", timeout=10_000)
        tip = page.evaluate("() => [...document.querySelectorAll('.calo-tooltip')]"
                            ".map((t) => t.innerText.trim()).filter(Boolean).pop()")
        assert tip.startswith("u = ") and "GeV mm⁻²" in tip and "projected energy per mm²" in tip, tip
        assert errors == [], errors
        browser.close()


# ----------------------------------------------------------- the picker --


def test_the_picker_walks_the_selection_and_the_link_follows(live_server):
    base = live_server["base"]
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base)
        assert page.evaluate(_HIDDEN, "event-grid") is True
        assert page.evaluate(_TEXT, "event-status") == "off"

        page.click("#event-pick")
        _wait_for_event_grid(page)
        first = int(page.input_value("#event-number"))
        assert f"event={first}" in page.evaluate(_HASH)
        caption = page.evaluate(_TEXT, "event-caption")
        assert "inside the current selection" in caption and "seed 42" in caption
        assert page.evaluate(_HIDDEN, "ensemble-grid") is True

        # Next walks the selection; the link follows; Prev then leads back.
        if not page.is_disabled("#event-next"):
            page.click("#event-next")
            page.wait_for_function(f"() => document.getElementById('event-number').value !== '{first}'", timeout=30_000)
            second = int(page.input_value("#event-number"))
            assert second > first and f"event={second}" in page.evaluate(_HASH)
            page.wait_for_function("() => !document.getElementById('event-prev').disabled", timeout=30_000)
            page.click("#event-prev")
            page.wait_for_function(f"() => document.getElementById('event-number').value === '{first}'", timeout=30_000)

        # The shower radio redraws the same event for the other shower.
        page.check('input[name="event-shower"][value="b"]')
        page.wait_for_function(f"() => document.getElementById('event-grid-label').textContent.startsWith('Event {first:,}, shower B')",
                               timeout=30_000)
        assert "shower=b" in page.evaluate(_HASH)

        # Back to the ensemble: the grid returns, the link loses its event.
        page.click("#event-close")
        assert page.evaluate(_HIDDEN, "event-grid") is True
        assert page.evaluate(_HIDDEN, "ensemble-grid") is False
        assert "event=" not in page.evaluate(_HASH)
        assert page.evaluate(_TEXT, "event-status") == "off"
        xy = page.evaluate(_GEOMETRY, "plot-xy")
        assert xy["chartWidth"] == xy["hostWidth"], "the ensemble panels re-laid themselves out"

        # A typed number pins again.
        page.fill("#event-number", str(first))
        page.press("#event-number", "Enter")
        _wait_for_event_grid(page)
        assert f"event={first}" in page.evaluate(_HASH)
        assert errors == [], errors
        browser.close()


# ------------------------------------------------ the drawer and export --


def _download(page, panel_id: str, label: str):
    page.click(f'button[data-export="{panel_id}"]')
    page.wait_for_selector(".menu")
    with page.expect_download() as download:
        page.click(f".menu-item:has-text('{label}')")
    return download.value


def test_the_event_drawer_states_the_frame_and_the_export_is_plot_only(live_server):
    base = live_server["base"]
    n = _picked(base)
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, f"#event={n}")
        _wait_for_event_grid(page)
        page.click('button[data-inspect="event-local-xz"]')
        assert page.evaluate(_HIDDEN, "inspector") is False
        title = page.inner_text("#inspector-title")
        assert title.startswith("Local") and title.endswith("u–w")
        body = page.evaluate(_TEXT, "inspector-body")
        for text in ("Selection", f"Event {n:,}, shower A", "What is drawn", "Local: every cell moved by −P₀",
                     "One half-width for every panel of this event", "Disclosures",
                     "One logarithmic ramp for every panel of this event", "0.1st–99.9th percentile",
                     "Coordinates:", "Marks and legend", "Dashed line = the incident direction", "Principal axis"):
            assert text in body, text
        assert page.evaluate("() => document.querySelector('.card[data-panel=\"event-local-xz\"]').classList.contains('is-inspected')")
        # The title row of a grid card opens the drawer too.
        page.click("#title-event-lab-xy")
        assert page.inner_text("#inspector-title").endswith("x–y")

        download = _download(page, "event-local-xz", "SVG — single column")
        assert download.suggested_filename.startswith(f"event-local-xz_ev{n}A_")
        assert "_native_local_" in download.suggested_filename
        svg = open(download.path(), encoding="utf-8").read()
        assert "figure-disclosure" not in svg
        for text in ("Experiment ", "One half-width", "Dashed line"):
            assert text not in svg, text
        assert 'width="321"' in svg
        assert errors == [], errors
        browser.close()


# --------------------------------------------------- the compare view --


def test_the_compare_view_lays_the_three_frames_out_in_rows(live_server):
    base = live_server["base"]
    experiment = next(e for e in httpx.get(f"{base}/api/experiments", timeout=30).json()["experiments"]
                      if e["table_name"] == TABLE)
    with live_server["playwright"].sync_playwright() as p:
        browser, page, errors = _open(p, base, "#compare=true")
        page.wait_for_function("() => document.getElementById('compare-grid-label').textContent !== '—'", timeout=30_000)
        assert page.evaluate(_HIDDEN, "ensemble-grid") is True
        assert page.evaluate(_HIDDEN, "compare-grid") is False
        assert page.is_checked("#opt-compare")
        label = page.evaluate(_TEXT, "compare-grid-label")
        assert label.startswith("Absolute: native") and "own response" in label
        offered = [kind for kind in ROWS if kind in experiment["frames"]
                   and {"lab": "lab", "trans": "trans", "local": "local"}[kind] in experiment["coord_systems"]]
        for row in ROWS:
            hidden = page.evaluate(f"() => document.querySelector('#compare-grid-rows [data-row={row}]').hidden")
            assert hidden is (row not in offered), row
            if hidden:
                continue
            page.wait_for_function(
                f"() => ['xy','xz','yz'].every((c) => document.getElementById(`plot-compare-{row}-${{c}}`)?.querySelector('canvas'))",
                timeout=30_000)
            xy = page.evaluate(_GEOMETRY, f"plot-compare-{row}-xy")
            along_x, along_y = _px_per_mm(xy)
            assert along_x == pytest.approx(along_y, rel=0.01), (row, along_x, along_y)
            title = page.evaluate(f"() => document.querySelector('#compare-grid-rows [data-row={row}] .frame-grid-row-title').textContent")
            assert "event" in title
        lab = page.evaluate(_GEOMETRY, "plot-compare-lab-xy")
        assert lab["xName"].startswith("x") and lab["yName"].startswith("y")
        if "local" in offered:
            local = page.evaluate(_GEOMETRY, "plot-compare-local-xy")
            assert local["xName"].startswith("u") and local["yName"].startswith("v")
            page.click('button[data-inspect="compare-local-xy"]')
            body = page.evaluate(_TEXT, "inspector-body")
            assert "Separation-Aligned (D-Frame), Local" in body and "Disclosures" in body

        page.click("#compare-grid-close")
        assert page.evaluate(_HIDDEN, "compare-grid") is True
        assert page.evaluate(_HIDDEN, "ensemble-grid") is False
        assert not page.is_checked("#opt-compare")
        assert "compare=" not in page.evaluate(_HASH)

        page.check("#opt-compare")
        page.wait_for_function("() => !document.getElementById('compare-grid').hidden", timeout=30_000)
        assert "compare=true" in page.evaluate(_HASH)
        assert errors == [], errors
        browser.close()
