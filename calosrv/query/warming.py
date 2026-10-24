"""Warm the co-registered frames' full-range bundles of the experiments that have them.

Cold, each costs seconds on the production table, so they are computed in the
background after an ingest and at boot - canonical first, then translated and
local, one scan at a time. Only the frames an experiment's capabilities open
are warmed: an aggregated experiment has none, and a frame whose queries do
not yet read one shower would only log a failure.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..config import Settings
from ..db.registry import ExperimentRecord
from . import capabilities


def warm(database, settings: Settings, records: Iterable[ExperimentRecord],
         model: str = "segmentation") -> None:
    """Start the background warmers for ``records``, in the order given."""
    from . import canonical_cache, shower_frames

    records = list(records)
    canonical = [r.table_name for r in records if "canonical" in capabilities.warm_kinds(r)]
    shower = [r.table_name for r in records
              if {"trans", "local"} & set(capabilities.warm_kinds(r))]
    shower_frames.warm(
        database, settings, shower, model=model,
        after=canonical_cache.warm(database, settings, canonical, model=model),
    )
