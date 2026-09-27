"""The upload dialog in Chromium: refusals asked before sending, a Parquet upload end to end.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the other browser checks.
"""

from __future__ import annotations

import os

import pytest

from conftest import SEED_CSV

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium upload-dialog check",
)


def _page(p, base):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(f"{base}/")
    page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')",
                           timeout=30_000)
    page.click("#open-upload")
    return browser, page


def _visible(page, selector):
    return page.evaluate(f"() => !document.querySelector('{selector}').hidden")


def test_a_taken_name_asks_for_replace_before_anything_is_sent(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        assert not _visible(page, "#upload-replace-row")
        page.fill("#upload-table", "experiment_baseline")
        assert _visible(page, "#upload-replace-row")
        assert "experiment_baseline" in page.inner_text("#upload-replace-text")
        page.set_input_files("#upload-file", str(SEED_CSV))
        page.click("#upload-submit")
        assert "already exists" in page.inner_text("#upload-warning")
        assert not _visible(page, "#upload-progress-row"), "nothing may be sent"
        browser.close()


def test_an_append_needs_an_existing_experiment_and_shows_the_offset(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        assert not _visible(page, "#upload-offset-row")
        page.check('input[name="upload-mode"][value="append"]')
        assert _visible(page, "#upload-offset-row")
        page.fill("#upload-table", "never_there")
        page.set_input_files("#upload-file", str(SEED_CSV))
        page.click("#upload-submit")
        assert "Cannot append to never_there" in page.inner_text("#upload-warning")
        browser.close()


def test_a_parquet_upload_is_ingested_and_opened(live_server, tmp_path):
    import duckdb

    from calosrv.ingest import csv_spec

    source = tmp_path / "browser_demo.parquet"
    duckdb.connect().execute(
        f"COPY (SELECT * FROM {csv_spec.read_csv_expression(SEED_CSV)}) TO '{source}' "
        "(FORMAT parquet)"
    )
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        page.fill("#upload-table", "browser_parquet")
        page.fill("#upload-display", "Parquet from the browser")
        page.set_input_files("#upload-file", str(source))
        assert "Ingestion needs about" in page.inner_text("#upload-file-info")
        page.click("#upload-submit")
        page.wait_for_function(
            "() => document.getElementById('upload-status').textContent.startsWith('Ingested')",
            timeout=60_000,
        )
        page.wait_for_function(
            "() => document.getElementById('experiment-select').value === 'browser_parquet'",
            timeout=30_000,
        )
        label = page.eval_on_selector(
            '#experiment-select option[value="browser_parquet"]', "el => el.textContent")
        assert label.startswith("Parquet from the browser")
        browser.close()


def test_escape_closes_the_dialog_and_returns_focus(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        assert page.evaluate("() => document.activeElement.id") == "upload-table"
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('upload-modal').hidden") is True
        assert page.evaluate("() => document.activeElement.id") == "open-upload"
        browser.close()
