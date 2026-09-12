"""Server-side aggregation queries.

Every SQL string in the application that is not a table definition lives in this
package. Route modules build a :class:`~calosrv.query.filters.FilterSpec` and
call a function here; they never concatenate SQL themselves.

One rule is load-bearing and is enforced by where the code lives rather than by
a comment: **per-event quantities are only ever aggregated from the per-event
table.** ``avg(d)`` taken over hit rows weights each event by its hit
multiplicity, which correlates with incident momentum, and produces a
plausible-looking wrong answer. Those aggregates live in ``summary.py``,
``energy.py`` and ``performance.py``, which read ``event_<name>``;
``projections.py`` reads ``proj_<name>`` and computes no per-event mean.
"""

from __future__ import annotations

from .filters import FilterSpec

__all__ = ["FilterSpec"]
