"""One Playwright driver and one Chromium per launch flavour, shared by the browser tests.

The live-server fixtures in ``conftest.py`` yield a :class:`BrowserPool` under ``"playwright"`` in
place of the ``playwright.sync_api`` module, so every test keeps its own spelling unchanged::

    with server["playwright"].sync_playwright() as p:
        browser = p.chromium.launch(args=GL_ARGS)
        page = browser.new_page(color_scheme="dark")
        ...
        browser.close()

What changes underneath:

- ``sync_playwright()`` opens a *session*. Playwright itself starts once, on the first session.
- ``chromium.launch(args=...)`` returns a :class:`BrowserHandle` on a shared Chromium, one per
  launch flavour keyed ``tuple(args or ())`` (so ``None`` and ``[]`` share the plain browser),
  launched on first use with exactly those ``args`` and kept for later sessions.
- The handle opens pages and contexts on that browser and records each context; its ``close()``
  closes those contexts only, never the shared browser.

Isolation is the contexts': every page still gets a fresh context, as a fresh browser gave it
(storage, permissions, colour scheme, viewport, init scripts, routes, downloads, cache). The session
proves it: at its start it refuses to run while any context of the pool's browsers is open, and at
its end it closes every context its handles recorded, then any other context still open.

A session that ended with an exception, a close that raised, a stray context, or a failed test
report (the ``pytest_runtest_makereport`` hook in ``conftest.py``) marks the pool *dirty*: the next
session closes every pool browser first, so they relaunch on the next ``launch``.

The ``browser_pool`` fixture in ``conftest.py`` holds one pool per test module, not per session:
while Playwright runs, the main thread's asyncio loop reads as running (``BROWSER_POOL_SCOPE`` says
why), and the module's end stops it.

This module imports no Playwright at import time; the fixture hands it ``playwright.sync_api``.
"""

from __future__ import annotations

from typing import Any

#: The pools alive in this process; the report hook marks them dirty when a test fails.
_ACTIVE: list["BrowserPool"] = []


def active_pools() -> tuple["BrowserPool", ...]:
    """The pools currently registered by :meth:`BrowserPool.activate`."""
    return tuple(_ACTIVE)


class BrowserHandle:
    """What a test's ``chromium.launch()`` returns: pages and contexts on a shared browser.

    It records every context it opens; ``close()`` closes those and nothing else. Any attribute
    other than the three below fails loudly, so a test that starts using another part of the
    ``Browser`` API is caught here rather than silently reaching the shared browser.
    """

    __slots__ = ("_browser", "_contexts", "_closed", "_session", "_error")

    def __init__(self, browser: Any, session: "_Session", error: type[BaseException]) -> None:
        self._browser = browser
        self._contexts: list[Any] = []
        self._closed = False
        self._session = session
        self._error = error

    def _check_open(self, what: str) -> None:
        if self._closed:
            raise RuntimeError(f"{what}: this browser handle was closed")
        if not self._session.active:
            raise RuntimeError(f"{what}: the sync_playwright() session of this browser handle has ended")

    def new_page(self, **kw: Any) -> Any:
        """The shared browser's own ``new_page(**kw)``, in a fresh context this handle records."""
        self._check_open("new_page")
        page = self._browser.new_page(**kw)
        self._contexts.append(page.context)
        return page

    def new_context(self, **kw: Any) -> Any:
        """The shared browser's own ``new_context(**kw)``, recorded on this handle."""
        self._check_open("new_context")
        context = self._browser.new_context(**kw)
        self._contexts.append(context)
        return context

    def close(self) -> None:
        """Close the contexts this handle opened, never the shared browser. Idempotent.

        Every recorded context is closed even when one raises; the first error is raised after.
        """
        if self._closed:
            return
        self._closed = True
        first: BaseException | None = None
        for context in self._contexts:
            try:
                context.close()
            except self._error as error:
                first = first or error
        if first is not None:
            raise first


class _Chromium:
    """The ``chromium`` attribute of a session: ``launch()`` only."""

    __slots__ = ("_session",)

    def __init__(self, session: "_Session") -> None:
        self._session = session

    def launch(self, *, args: list[str] | tuple[str, ...] | None = None, headless: bool = True,
               **unknown: Any) -> BrowserHandle:
        """A handle on the pool's browser for ``args``, launched on first use.

        Only ``args`` and ``headless=True`` are understood. Any other keyword, or ``headless`` other
        than ``True``, raises ``TypeError`` naming it, so a launch option is never silently ignored by
        a browser that was launched without it.
        """
        if unknown:
            raise TypeError("BrowserPool chromium.launch() does not support "
                            + ", ".join(f"{name}={value!r}" for name, value in sorted(unknown.items()))
                            + "; add it to the pool's launch flavour key first")
        if headless is not True:
            raise TypeError(f"BrowserPool chromium.launch() supports only headless=True, not headless={headless!r}")
        return self._session.launch(tuple(args or ()))


class _Session:
    """One ``with pool.sync_playwright() as p:`` block."""

    __slots__ = ("_pool", "_handles", "active", "chromium")

    def __init__(self, pool: "BrowserPool") -> None:
        self._pool = pool
        self._handles: list[BrowserHandle] = []
        self.active = False
        self.chromium = _Chromium(self)

    def __enter__(self) -> "_Session":
        self._pool._begin(self)
        self.active = True
        return self

    def launch(self, key: tuple[str, ...]) -> BrowserHandle:
        if not self.active:
            raise RuntimeError("chromium.launch() outside its sync_playwright() block")
        handle = BrowserHandle(self._pool._browser(key), self, self._pool._api.Error)
        self._handles.append(handle)
        return handle

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.active = False
        try:
            self._pool._end(self, failed=exc_type is not None)
        except BaseException:
            if exc_type is None:
                raise
            # The test's own exception is the one that matters; the pool is dirty already.
        return False  # never suppress the test's exception


class BrowserPool:
    """A per-process pool of one Playwright driver and one Chromium per launch flavour.

    ``sync_api`` is the ``playwright.sync_api`` module. With ``one_browser=True`` at most one
    Chromium is kept: launching a flavour first closes every other flavour's browser that has no
    open context (one in use by the running test is left alone).
    """

    def __init__(self, sync_api: Any, *, one_browser: bool = False) -> None:
        self._api = sync_api
        self.one_browser = one_browser
        self.dirty = False
        self._manager: Any = None  # the PlaywrightContextManager
        self._playwright: Any = None
        self._browsers: dict[tuple[str, ...], Any] = {}
        self._session: _Session | None = None

    # -- the module's spelling ----------------------------------------------------------------------

    def sync_playwright(self) -> _Session:
        """A session context manager; entering it gives an object with a ``chromium`` attribute."""
        return _Session(self)

    # -- lifecycle ----------------------------------------------------------------------------------

    def activate(self) -> "BrowserPool":
        """Register this pool for the report hook (:func:`active_pools`)."""
        if self not in _ACTIVE:
            _ACTIVE.append(self)
        return self

    def mark_dirty(self) -> None:
        """Have the next session close every pool browser first, so they relaunch."""
        self.dirty = True

    def close(self) -> None:
        """Close every pool browser and stop Playwright; unregister. Errors are swallowed."""
        if self in _ACTIVE:
            _ACTIVE.remove(self)
        self._close_browsers()
        self._stop_playwright()

    def browsers(self) -> dict[tuple[str, ...], Any]:
        """The pool's live browsers by flavour key (a copy, for tests of the pool itself)."""
        return dict(self._browsers)

    def open_contexts(self) -> list[Any]:
        """Every context open on the pool's connected browsers."""
        found: list[Any] = []
        for browser in self._browsers.values():
            if browser.is_connected():
                found.extend(browser.contexts)
        return found

    # -- internals ----------------------------------------------------------------------------------

    def _driver_alive(self) -> bool:
        manager = self._manager
        if manager is None or self._playwright is None:
            return False
        connection = getattr(manager, "_connection", None)
        if connection is None or getattr(connection, "_closed_error", None) is not None:
            return False
        fiber = getattr(connection, "_dispatcher_fiber", None)
        return fiber is None or not fiber.dead

    def _start_playwright(self) -> None:
        self._manager = self._api.sync_playwright()
        self._playwright = self._manager.start()

    def _stop_playwright(self) -> None:
        manager, self._manager, self._playwright = self._manager, None, None
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass

    def _close_browsers(self, keys: list[tuple[str, ...]] | None = None) -> None:
        for key in list(self._browsers) if keys is None else keys:
            browser = self._browsers.pop(key, None)
            if browser is None:
                continue
            try:
                browser.close()
            except Exception:
                pass

    def _begin(self, session: _Session) -> None:
        if self._session is not None:
            raise RuntimeError("BrowserPool: sync_playwright() sessions cannot be nested")
        # The driver: started once; if it has gone, stopped and started again, once.
        if self._playwright is None:
            self._start_playwright()
        elif not self._driver_alive():
            self._browsers.clear()  # their connection died with the driver
            self._stop_playwright()
            self._start_playwright()
        # A context still open belongs to nobody: refuse, and close its browser so the next session is clean.
        leaked = self.open_contexts()
        if leaked:
            holders = [key for key, browser in self._browsers.items()
                       if browser.is_connected() and browser.contexts]
            self._close_browsers(holders)
            self.dirty = True
            raise RuntimeError(f"BrowserPool: {len(leaked)} browser context(s) were still open when a "
                               "sync_playwright() session began; their browser was closed")
        # A browser that crashed or was closed under the pool relaunches on the next launch().
        self._close_browsers([key for key, browser in self._browsers.items() if not browser.is_connected()])
        if self.dirty:
            self._close_browsers()
            self.dirty = False
        self._session = session

    def _browser(self, key: tuple[str, ...]) -> Any:
        browser = self._browsers.get(key)
        if browser is not None and not browser.is_connected():
            self._close_browsers([key])
            browser = None
        if browser is None:
            if self.one_browser:
                self._close_browsers([other for other, held in self._browsers.items()
                                      if other != key and not (held.is_connected() and held.contexts)])
            browser = self._playwright.chromium.launch(args=list(key))
            self._browsers[key] = browser
        return browser

    def _end(self, session: _Session, *, failed: bool) -> None:
        """Close the session's contexts, then any stray one; raise on a stray after a clean block."""
        error = self._api.Error
        close_raised = False
        try:
            for handle in session._handles:
                handle._closed = True
                for context in handle._contexts:
                    try:
                        context.close()
                    except error:
                        close_raised = True
            stray = self.open_contexts()
            for context in stray:
                try:
                    context.close()
                except error:
                    close_raised = True
        finally:
            self._session = None
        if failed or close_raised or stray:
            self.dirty = True
        if stray and not failed:
            raise RuntimeError(f"BrowserPool: {len(stray)} browser context(s) opened outside a browser handle "
                               "were still open when the sync_playwright() block ended; closed them")
