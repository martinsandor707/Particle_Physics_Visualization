"""The upload form inside Admin Settings, in Chromium: refusals asked before
sending, a Parquet upload end to end, and an ingest that outlives the panel.

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
    page = browser.new_page(color_scheme="dark", viewport={"width": 1600, "height": 900})
    page.goto(f"{base}/")
    page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')",
                           timeout=30_000)
    page.click("#open-admin")
    page.wait_for_function(
        "() => document.querySelector('#admin-modal [data-field=\"default_coord_system\"] .chip')"
        "?.textContent.trim()"
    )
    # The form readies itself on every open: the upload-info guidance arrives.
    page.wait_for_function(
        "() => !document.getElementById('upload-warning').hidden"
        " && document.getElementById('upload-warning').textContent.length > 0"
    )
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


def test_escape_from_the_upload_form_closes_the_panel_and_returns_focus(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        assert page.evaluate("() => document.activeElement.id") == "admin-dataset"
        page.focus("#upload-table")
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is True
        assert page.evaluate("() => document.activeElement.id") == "open-admin"
        browser.close()


def test_clear_form_empties_the_fields_after_a_refusal(live_server):
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        page.fill("#upload-table", "experiment_baseline")
        assert _visible(page, "#upload-replace-row")
        page.click("#upload-submit")
        assert "already exists" in page.inner_text("#upload-warning")
        page.click("#upload-clear")
        assert page.input_value("#upload-table") == ""
        assert not _visible(page, "#upload-replace-row")
        assert "already exists" not in page.inner_text("#upload-warning")
        browser.close()


def test_an_upload_survives_closing_and_reopening_the_panel(live_server, tmp_path):
    import duckdb

    from calosrv.ingest import csv_spec

    source = tmp_path / "browser_reopen.parquet"
    duckdb.connect().execute(
        f"COPY (SELECT * FROM {csv_spec.read_csv_expression(SEED_CSV)}) TO '{source}' "
        "(FORMAT parquet)"
    )
    with live_server["playwright"].sync_playwright() as p:
        browser, page = _page(p, live_server["base"])
        page.fill("#upload-table", "browser_reopen")
        page.set_input_files("#upload-file", str(source))
        page.click("#upload-submit")
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is True
        # Reopened while the job runs: the form is still busy, so nothing is reset.
        page.click("#open-admin")
        assert _visible(page, "#upload-progress-row")
        assert page.is_disabled("#upload-submit") and page.is_disabled("#upload-clear")
        page.wait_for_function(
            "() => !document.getElementById('upload-progress-row').hidden"
            " && document.getElementById('upload-status').textContent.startsWith('Ingested')",
            timeout=60_000,
        )
        page.wait_for_function(
            "() => document.getElementById('experiment-select').value === 'browser_reopen'",
            timeout=30_000,
        )
        assert not page.is_disabled("#upload-clear")
        browser.close()
