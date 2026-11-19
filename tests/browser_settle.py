"""Settles for the browser tests: wait for a state the page reports, never a guessed delay.

A pointer move is settled when the page has dispatched it. zrender's mousemove handler shows,
fills and places a tooltip synchronously (``static/js/panels/tooltip.js``: no show delay, no
transition, ``hideDelay: 0``), so once the move is dispatched the tooltip a probe reads is the one
for that pointer position.

Measured on 2026-11-19 (``data/dev/design/browser-speed/hover_bench``): Chromium dispatches the move
before ``page.mouse.move`` returns (306 of 306 moves), so the wait below costs one round trip, against
40 ms for the fixed sleep it replaces and two frames (about 33 ms) for ``_frames(page)``. Probes taken
after it were identical to probes taken after the old sleep, and to a second probe 40 ms later.
"""
from __future__ import annotations

#: Installs, once per page, a passive capture listener counting the document's mousemove dispatches
#: and keeping the last one's position; returns the count so far.
_WATCH_MOVES = """() => {
  if (!window.__browserSettleMoves) {
    window.__browserSettleMoves = { n: 0, x: null, y: null };
    document.addEventListener('mousemove', (e) => {
      const w = window.__browserSettleMoves;
      w.n += 1; w.x = e.clientX; w.y = e.clientY;
    }, { capture: true, passive: true });
  }
  return window.__browserSettleMoves.n;
}"""

#: A move dispatched after count `n`, at (x, y) to the pixel.
_MOVED = """([n, x, y]) => { const w = window.__browserSettleMoves;
  return Boolean(w) && w.n > n && Math.abs(w.x - x) <= 1 && Math.abs(w.y - y) <= 1; }"""


def move_pointer(page, x, y, *, steps=1):
    """Move the pointer to (x, y), as ``page.mouse.move`` does, and return once the page has dispatched the
    move to (x, y): every mousemove listener, the tooltip's included, has run. A move the page never
    dispatches fails after 10 s rather than letting a probe read a stale tooltip."""
    n = page.evaluate(_WATCH_MOVES)
    if not isinstance(n, int):
        raise RuntimeError(f"window.__browserSettleMoves is taken by something else on the page ({n!r})")
    page.mouse.move(x, y, steps=steps)
    page.wait_for_function(_MOVED, arg=[n, x, y], timeout=10_000)
