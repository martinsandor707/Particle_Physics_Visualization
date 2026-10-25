"""Server-side aggregation queries.

Every SQL string in the application that is not a table definition lives in this
package. Route modules build a :class:`~calosrv.query.filters.FilterSpec` and
call a function here; they never concatenate SQL themselves.

One rule is load-bearing and is enforced by where the code lives rather than by
a comment: **per-event quantities are only ever aggregated from the per-event
table.** ``avg(d)`` taken over hit rows weights each event by its hit
multiplicity, which correlates with incident momentum, and produces a
plausible-looking wrong answer. Those aggregates live in the event-table
modules - ``summary.py``, ``energy.py``, ``performance.py``,
``performance_bins.py``, ``prediction_density.py``, ``response.py``,
``negative_depth.py``, ``shower_distributions.py``, ``primaries.py`` and the
feature explorer (``features_catalog.py``, ``features.py``) - which read
``event_<name>``; ``profiles.py`` reads the per-(event, shower) tables
``profiles_<name>`` and ``layers_<name>`` with the event table's per-shower
energies. The hit modules - ``projections.py``, ``hit_distributions.py``,
``statistics.py`` and ``correlations.py`` - read ``proj_<name>`` and take a
per-event quantity from the event table through a join, never by averaging it
over hit rows.
"""

from __future__ import annotations

from .filters import FilterSpec

__all__ = ["FilterSpec"]
