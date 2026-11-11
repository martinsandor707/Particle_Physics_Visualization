"""The Admin Settings panel, driven in Chromium the way an operator uses it.

Saving a default must change what a *new* session opens on and nothing else: a
link that carries view state keeps it, and the session that saved keeps its
own view. The unit tests prove the rules (``test_admin_config.py``,
``test_js_behaviour.py``); this proves the panel wires them to the page.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the tooltip check: it needs
Playwright's Chromium.

Source files (``test_a_changed_file_is_re_ingested_from_the_panel``,
``test_a_failed_experiment_is_retried_from_the_panel``) are driven end to end
in both themes: a file dropped in the folder and ingested, changed on disk,
compared again, then re-ingested - or failed in the registry, then retried.
``GET /api/admin/experiments`` and the POST route are the backend's
(``tests/test_reingest.py``); the pure row models are ``test_js_admin_sources.py``.
"""

from __future__ import annotations

import os
import re
import shutil

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium admin-panel check",
)

FIELDS = ("default_dataset", "default_coord_system", "default_model", "default_channel",
          "default_display_mode", "default_rho_norm")


@pytest.fixture
def clean(live_server):
    """Every test starts from nothing saved."""
    import httpx

    httpx.post(f"{live_server['base']}/api/admin/config",
               json={field: None for field in FIELDS}, timeout=10).raise_for_status()
    return live_server


def _page(p, base, fragment="", scheme="dark"):
    browser = p.chromium.launch()
    page = browser.new_page(color_scheme=scheme, viewport={"width": 1600, "height": 900})
    page.goto(f"{base}/{fragment}")
    page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')",
                           timeout=30_000)
    return browser, page


def _checked(page, name):
    return page.eval_on_selector(f'input[name="{name}"]:checked', "el => el.value")


def _frame(page):
    """The frame key the two-tier control reflects (main.js `syncFrameControl`)."""
    return page.get_attribute("#ctl-frame", "data-frame")


def _chip(page, field):
    return page.inner_text(f'#admin-modal [data-field="{field}"] .chip').strip()


def _open_panel(page):
    page.click("#open-admin")
    page.wait_for_function(
        "() => document.querySelector('#admin-modal [data-field=\"default_coord_system\"] .chip')"
        "?.textContent.trim()"
    )


def _choose(page, field, value):
    page.check(f'#admin-modal [data-field="{field}"] input[value="{value}"]')


def test_saving_in_the_panel_changes_what_a_new_session_opens_on(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        assert _chip(page, "default_coord_system") == "built-in"
        assert _chip(page, "default_dataset") == "built-in"

        _choose(page, "default_coord_system", "trans")
        _choose(page, "default_channel", "gradcam")
        assert _chip(page, "default_coord_system") == "not saved"
        page.click("#admin-save")
        page.wait_for_function(
            "() => document.getElementById('admin-status').textContent.startsWith('Saved')")
        assert _chip(page, "default_coord_system") == "set here"
        # The session that saved keeps its own view.
        assert _frame(page) == "lab"
        browser.close()

        browser, page = _page(p, clean["base"])
        assert (_frame(page), _checked(page, "channel")) == ("trans", "gradcam")
        assert "frame=trans" in page.evaluate("() => window.location.hash")
        # The legacy per-shower frame has no radio of its own: a saved default
        # reveals the hidden sub-option so the control reflects the state.
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is False
        assert page.is_checked('input[name="frame-sub"][value="trans"]')
        browser.close()

        browser, page = _page(p, clean["base"], "#frame=lab")
        assert (_frame(page), _checked(page, "channel")) == ("lab", "density")
        assert page.evaluate("() => document.getElementById('frame-sub-trans').hidden") is True
        browser.close()


def test_use_current_view_fills_the_form_with_the_view_on_screen(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"], "#frame=canonical&channel=shapcam&model=energy")
        _open_panel(page)
        page.click("#admin-use-current")
        form = page.evaluate("""() => Object.fromEntries(
            [...document.querySelectorAll('#admin-modal input[type=radio]:checked')]
              .map((el) => [el.name, el.value]))""")
        assert form["admin-default_coord_system"] == "canonical"
        assert form["admin-default_channel"] == "shapcam"
        assert form["admin-default_model"] == "energy"
        assert _chip(page, "default_coord_system") == "not saved"
        browser.close()


def test_reset_removes_the_saved_value(clean):
    import httpx

    httpx.post(f"{clean['base']}/api/admin/config", json={"default_coord_system": "local"},
               timeout=10).raise_for_status()
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"], "#frame=lab")
        _open_panel(page)
        assert _chip(page, "default_coord_system") == "set here"
        page.click('#admin-modal [data-field="default_coord_system"] [data-reset]')
        assert _chip(page, "default_coord_system") == "reset on save"
        page.click("#admin-save")
        page.wait_for_function(
            "() => document.getElementById('admin-status').textContent.startsWith('Saved')")
        assert _chip(page, "default_coord_system") == "built-in"
        browser.close()


def test_the_panels_frame_choices_are_the_sidebar_tree_composed(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        labels = page.evaluate("""() => Object.fromEntries(
            [...document.querySelectorAll('#admin-modal input[name="admin-default_coord_system"]')]
              .map((el) => [el.value, el.closest('label').textContent.replace(/\\s+/g, ' ').trim()]))""")
        assert labels["lab"].startswith("Absolute (detector coordinates)")
        assert labels["canonical"].startswith("Separation-Aligned (D-Frame) › Translated")
        assert labels["local"].startswith("Separation-Aligned (D-Frame) › Local (shower-fixed)")
        assert labels["trans"].startswith("Per-shower translated (legacy")
        browser.close()


def test_escape_closes_the_panel_and_returns_focus(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is False
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is True
        assert page.evaluate("() => document.activeElement.id") == "open-admin"
        browser.close()


def test_scan_now_ingests_a_file_dropped_into_the_folder(clean):
    """The live server's drop folder starts empty; a file dropped in is one click away."""
    import shutil

    from conftest import SEED_CSV

    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        assert "no CSV or Parquet files found" in page.inner_text("#admin-ingest-where")
        shutil.copyfile(SEED_CSV, clean["drop"] / "panel_drop.csv")
        page.click("#admin-scan")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#admin-ingest-rows tr')].some((row) =>"
            " row.cells[0].textContent === 'panel_drop.csv'"
            " && row.cells[2].textContent === 'ingested — ready')",
            timeout=60_000,
        )
        # The experiment joins the header's list without a reload.
        page.wait_for_function(
            "() => !!document.querySelector('#experiment-select option[value=\"panel_drop\"]')",
            timeout=30_000,
        )
        browser.close()


# --------------------------------------------------------------- Source files

THEMES = ("dark", "light")


def _ingest_copy(page, drop, name):
    """Drop a copy of the seed into the folder as `<name>.parquet`, Scan now, wait until it is an experiment."""
    from conftest import SEED_FILE

    shutil.copyfile(SEED_FILE, drop / f"{name}.parquet")
    page.click("#admin-scan")
    page.wait_for_function(
        "(file) => [...document.querySelectorAll('#admin-ingest-rows tr')].some((row) =>"
        " row.cells[0].textContent === file && row.cells[2].textContent === 'ingested — ready')",
        arg=f"{name}.parquet", timeout=60_000,
    )


def _row(name):
    return f'#admin-sources-rows tr[data-table="{name}"]'


def _check_again(page, name, badge):
    """Press Check again until the experiment's row carries `badge`."""
    page.click("#admin-sources-refresh")
    page.wait_for_function(
        "([selector, text]) => document.querySelector(selector + ' .chip')?.textContent.trim() === text",
        arg=[_row(name), badge], timeout=30_000,
    )


def _status_has(page, text):
    page.wait_for_function(
        "(text) => document.getElementById('admin-status').textContent.includes(text)",
        arg=text, timeout=120_000,
    )


@pytest.mark.parametrize("scheme", THEMES)
def test_a_changed_file_is_re_ingested_from_the_panel(clean, scheme, tmp_path):
    """Changed on disk -> "Source updated on disk" -> Re-ingest (disabled at once) -> "Current", "Re-ingested - ready"."""
    import duckdb

    from conftest import SEED_FILE

    name = f"reingest_{scheme}"
    drop = clean["drop"]
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"], scheme=scheme)
        _open_panel(page)
        _ingest_copy(page, drop, name)
        _check_again(page, name, "Current")
        assert page.query_selector(f'{_row(name)} button') is None

        # The same rows, another compression: a valid file of another size, written after it was ingested.
        rewritten = tmp_path / f"{name}.parquet"
        duckdb.connect().execute(
            f"COPY (SELECT * FROM read_parquet('{SEED_FILE}')) TO '{rewritten}' (FORMAT parquet, COMPRESSION snappy)")
        assert rewritten.stat().st_size != (drop / f"{name}.parquet").stat().st_size
        shutil.copyfile(rewritten, drop / f"{name}.parquet")

        _check_again(page, name, "Source updated on disk")
        assert page.get_attribute(_row(name), "data-state") == "changed"
        assert "Size" in page.inner_text(f"{_row(name)} .source-detail")
        # Looking re-ingested nothing: the row shows the original ingest's job, not a re-ingest.
        assert "Re-ingest" not in (page.text_content(f"{_row(name)} .source-job") or "")

        # The click renders the row again before the request is answered: the new button is already disabled.
        disabled = page.evaluate(
            """(name) => {
                document.querySelector(`button[data-reingest="${name}"]`).click();
                return document.querySelector(`button[data-reingest="${name}"]`)?.disabled ?? null;
            }""", name)
        assert disabled is True
        page.wait_for_function(
            "(selector) => document.querySelector(selector + ' .chip')?.textContent.trim() === 'Current'"
            " && document.querySelector(selector + ' .source-job')?.textContent.trim() === 'Re-ingested — ready'",
            arg=_row(name), timeout=120_000,
        )
        _status_has(page, f"{name} was re-ingested from {name}.parquet.")
        assert page.query_selector(f'{_row(name)} button') is None
        browser.close()


@pytest.mark.parametrize("scheme", THEMES)
def test_a_failed_experiment_is_retried_from_the_panel(clean, scheme):
    """Failed in the registry -> "Ingestion failed" + Retry ingest -> the row ends ready."""
    from calosrv.db import registry
    from calosrv.db.connection import get_database

    name = f"retry_{scheme}"
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"], scheme=scheme)
        _open_panel(page)
        _ingest_copy(page, clean["drop"], name)

        with get_database().write_lock() as con:
            registry.set_status(con, name, "failed", "Ingestion was interrupted before it completed.")
        _check_again(page, name, "Ingestion failed")
        assert page.is_enabled(f'{_row(name)} button[data-retry="{name}"]')
        assert page.inner_text(f'{_row(name)} button[data-retry="{name}"]') == "Retry ingest"
        assert page.query_selector(f'{_row(name)} button[data-reingest]') is None

        page.click(f'{_row(name)} button[data-retry="{name}"]')
        page.wait_for_function(
            "(selector) => document.querySelector(selector + ' .chip')?.textContent.trim() === 'Current'"
            " && document.querySelector(selector + ' .source-job')?.textContent.trim() === 'Ingested — ready'",
            arg=_row(name), timeout=120_000,
        )
        _status_has(page, f"{name} was ingested again from {name}.parquet.")
        with get_database().read_cursor() as con:
            assert con.execute('SELECT status FROM "experiment" WHERE table_name = ?', [name]).fetchone() == ("ready",)
        browser.close()


def _rgb(text):
    """The three channels of a computed `rgb(...)` / `rgba(...)` colour."""
    numbers = [float(n) for n in re.findall(r"[\d.]+", text)]
    assert len(numbers) in (3, 4), text
    return numbers[:3]


def _contrast(a, b):
    def luminance(rgb):
        lin = [(c / 255 / 12.92) if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((luminance(_rgb(a)), luminance(_rgb(b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("scheme", THEMES)
def test_the_state_chips_use_their_tokens_and_read_on_the_modal_ground(clean, scheme):
    """Each chip's colour is its token's in the theme on show, and every text colour clears 4.5:1 on the modal."""
    tokens = {"changed": "--warn", "failed": "--danger", "busy": "--accent"}
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"], scheme=scheme)
        _open_panel(page)
        page.wait_for_function(
            "() => !document.getElementById('admin-sources-where').textContent.startsWith('\u2014')",
            timeout=30_000)
        # One row of each kind, built as controls/admin.js builds its rows, so the section's own selectors apply.
        measured = page.evaluate(
            """(tokens) => {
                const body = document.getElementById('admin-sources-rows');
                document.getElementById('admin-sources-table').hidden = false;
                const colourOf = (value) => {
                  const probe = document.createElement('span');
                  probe.style.color = value;
                  document.body.append(probe);
                  const colour = getComputedStyle(probe).color;
                  probe.remove();
                  return colour;
                };
                const rows = [];
                for (const kind of ['changed', 'failed', 'busy', 'current', 'muted']) {
                  const tr = document.createElement('tr');
                  const state = document.createElement('td');
                  state.className = 'source-state';
                  const chip = document.createElement('span');
                  chip.className = 'chip';
                  chip.dataset.state = kind;
                  chip.textContent = kind;
                  const detail = document.createElement('div');
                  detail.className = 'source-detail';
                  detail.textContent = 'detail';
                  const job = document.createElement('div');
                  job.className = 'source-job';
                  job.textContent = 'job';
                  const failed = document.createElement('div');
                  failed.className = 'source-job admin-error';
                  failed.textContent = 'failed job';
                  state.append(chip, detail, job, failed);
                  tr.append(state);
                  rows.push([kind, tr, chip, detail, job, failed]);
                }
                body.replaceChildren(...rows.map((r) => r[1]));
                const colour = (el) => getComputedStyle(el).color;
                return {
                  ground: getComputedStyle(document.querySelector('#admin-modal .modal')).backgroundColor,
                  groundToken: colourOf('var(--canvas-alt)'),
                  chips: Object.fromEntries(rows.map((r) => [r[0], colour(r[2])])),
                  tokens: Object.fromEntries(Object.entries(tokens).map(([k, v]) => [k, colourOf(`var(${v})`)])),
                  detail: colour(rows[0][3]),
                  job: colour(rows[0][4]),
                  failedJob: colour(rows[0][5]),
                  danger: colourOf('var(--danger)'),
                };
            }""", tokens)
        assert measured["ground"] == measured["groundToken"], "the modal ground is --canvas-alt"
        for kind in tokens:
            assert measured["chips"][kind] == measured["tokens"][kind], f"{kind} chip is not {tokens[kind]}"
        for kind, colour in measured["chips"].items():
            assert _contrast(colour, measured["ground"]) >= 4.5, f"{kind} chip {colour} on {measured['ground']}"
        for key in ("detail", "job", "failedJob"):
            assert _contrast(measured[key], measured["ground"]) >= 4.5, key
        assert measured["failedJob"] == measured["danger"]
        browser.close()
