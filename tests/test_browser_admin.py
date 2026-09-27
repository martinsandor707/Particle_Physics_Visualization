"""The Admin Settings panel, driven in Chromium the way an operator uses it.

Saving a default must change what a *new* session opens on and nothing else: a
link that carries view state keeps it, and the session that saved keeps its
own view. The unit tests prove the rules (``test_admin_config.py``,
``test_js_behaviour.py``); this proves the panel wires them to the page.

Opt-in (``CALOSRV_BROWSER_TESTS=1``), like the tooltip check: it needs
Playwright's Chromium.
"""

from __future__ import annotations

import os

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


def _page(p, base, fragment=""):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(f"{base}/{fragment}")
    page.wait_for_function("() => document.getElementById('plot-xy')?.querySelector('canvas')",
                           timeout=30_000)
    return browser, page


def _checked(page, name):
    return page.eval_on_selector(f'input[name="{name}"]:checked', "el => el.value")


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
        assert _checked(page, "frame") == "lab"
        browser.close()

        browser, page = _page(p, clean["base"])
        assert (_checked(page, "frame"), _checked(page, "channel")) == ("trans", "gradcam")
        assert "frame=trans" in page.evaluate("() => window.location.hash")
        browser.close()

        browser, page = _page(p, clean["base"], "#frame=lab")
        assert (_checked(page, "frame"), _checked(page, "channel")) == ("lab", "density")
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


def test_escape_closes_the_panel_and_returns_focus(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is False
        page.keyboard.press("Escape")
        assert page.evaluate("() => document.getElementById('admin-modal').hidden") is True
        assert page.evaluate("() => document.activeElement.id") == "open-admin"
        browser.close()


def test_the_panel_says_when_automatic_ingest_is_off(clean):
    with clean["playwright"].sync_playwright() as p:
        browser, page = _page(p, clean["base"])
        _open_panel(page)
        assert "Automatic ingest is off" in page.inner_text("#admin-ingest-where")
        assert page.is_disabled("#admin-scan")
        browser.close()
