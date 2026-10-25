"""One measured size guard for a route whose whole body must fit the response contract.

``serve_measured`` builds the enveloped body at a first rendering, measures it
exactly as served (:func:`density.wire_size`, against
``density.RESPONSE_LIMIT`` read at call time so a test can lower it) and,
while it is over, asks ``shrink`` for the next rendering and ``describe`` for
the sentence that discloses the step. Every step taken is said in the body it
produced - nothing is withheld silently. If even the last rendering is over,
a final warning quotes the size served, that warning included.

It measures the final body, meta and notices with it, which a guard on one
block (the canonical frame's ``frame_canonical.serve_within_budget``, the
inspector's grid loop) does not.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from ..query import density
from ..text import typographic

#: A rendering: whatever the route varies to shrink its body (a cap, a pitch).
S = TypeVar("S")

#: Default steps before the guard stops shrinking and says so.
ATTEMPTS = 6


def serve_measured(
    build: Callable[[S, list[str]], dict[str, Any]],
    first: S,
    shrink: Callable[[S, int, int], S | None],
    describe: Callable[[S, S, int, int], str],
    attempts: int = ATTEMPTS,
    remedy: str = "a narrower selection brings it under",
) -> dict[str, Any]:
    """The body of the first rendering that fits, or the last one with a stated overrun.

    ``build(state, notices)`` returns the enveloped body and places
    ``notices`` - one sentence per step taken so far - wherever the route
    discloses them. ``shrink(state, size, limit)`` returns the next rendering,
    or None when nothing smaller exists; ``describe(old, new, size, limit)``
    says what the step changed and why, with the size that forced it.
    """
    limit = density.RESPONSE_LIMIT
    state, notices = first, []
    body = build(state, [])
    size = density.wire_size(body)
    for _ in range(attempts):
        if size < limit:
            return body
        smaller = shrink(state, size, limit)
        if smaller is None:
            break
        notices.append(typographic(describe(state, smaller, size, limit)))
        state = smaller
        body = build(state, list(notices))
        size = density.wire_size(body)
    if size < limit:
        return body
    # The warning quotes the size of the body that carries it: settle on the
    # fixed point (the digits of the size change the size by a byte or two).
    warnings = list(body["meta"]["warnings"])
    claimed = size
    notice = ""
    for _ in range(4):
        notice = typographic(
            f"The response is still {claimed:,} bytes after every stated reduction, over the "
            f"{limit:,}-byte contract. It is served as it is rather than with anything withheld; "
            f"{remedy}.")
        served = density.wire_size({**body, "meta": {**body["meta"], "warnings": warnings + [notice]}})
        if served == claimed:
            break
        claimed = served
    body["meta"]["warnings"] = warnings + [notice]
    return body
