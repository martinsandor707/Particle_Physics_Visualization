"""The cached canonical bundle of a selection, and its start-up warmer.

The canonical scan is the one query in the service that can take a couple of
seconds: co-registering all 22.5 million production hits at the smallest
honest sub-cell factor (k = 2, see ``grid/frame.py``) measures about 2.0 s.
It is paid once per selection and then served from the canonical LRU; the
full-range selection that every interface opens on is warmed here in the
background as soon as an experiment is ready, so the first page load does not
wait for it.

This module sits in the query layer so both the API assembly and the ingest
job runner can call it without a layering inversion.

**What the key leaves out.** The cache key (``canonical.cache_key``) names the
selection, the sampling, the accumulation grid, ``k`` and the footprint - and
nothing about the display. The display mode, the resolution R and the
reconstruction kernel are all applied afterwards to the cached raw
accumulation grid, so changing any of them re-renders from the cached bundle
in milliseconds and never re-scans the hits.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

import duckdb

from ..config import Settings
from ..db import registry
from ..db.registry import ExperimentRecord
from ..grid import frame as frame_mod
from . import cache as cache_mod
from . import canonical, density, filters
from .canonical import CanonicalBundle, FrameStats
from .filters import FilterSpec

log = logging.getLogger(__name__)


def bundle_for(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    settings: Settings,
    footprint: tuple[float, float],
    sampled: bool,
    percent: float,
) -> tuple[CanonicalBundle, FrameStats, frame_mod.CanonicalGrid, int, bool]:
    """Frame statistics, window, sub-sampling factor and the (cached) bundle.

    Returns ``(bundle, stats, grid, k, was_cached)``. The sampled drag preview
    caps ``k`` at :data:`~calosrv.grid.frame.PREVIEW_MAX_SUBSAMPLE`: it is
    approximate by construction and must stay quick.
    """
    assert record.lattice is not None
    # One canonical form per selection: a bound looser than the data selects
    # the same rows, and clamping lets the interface's snapped full-range
    # request hit the bundle the start-up warmer already computed.
    spec = spec.clamped(record)
    stats = canonical.frame_statistics(con, record, spec)
    grid = frame_mod.plan_window(stats.d_entry_max, stats.theta_max, record.lattice)
    rows_scanned = int(round(stats.n_hits * (percent / 100.0 if sampled else 1.0)))
    k = frame_mod.choose_subsample(rows_scanned)
    if sampled:
        k = min(k, frame_mod.PREVIEW_MAX_SUBSAMPLE)

    cache = cache_mod.get_cache(settings.canonical_cache_entries, name=cache_mod.CANONICAL_CACHE)
    key = canonical.cache_key(spec, sampled, grid, k, footprint)

    def compute() -> CanonicalBundle:
        bundle = canonical.fetch_canonical(
            con, record, spec, stats, grid, k, footprint,
            sampled=sampled, sample_percent=percent,
        )
        if sampled:
            canonical.scale_sample(bundle, percent)
        return bundle

    bundle, was_cached = cache.get_or_compute(key, compute)
    return bundle, stats, grid, k, was_cached


def dataset_reference(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    settings: Settings,
    footprint: tuple[float, float],
) -> dict[str, float]:
    """Peak canonical density of the whole experiment, from its cached full-range bundle.

    The sub-cell factor the reference was measured at rides along as ``k``: a
    slice is usually splatted more finely than the whole dataset, and a peak is
    a maximum statistic, so the two are not measured with quite the same
    estimator. The response discloses both factors.
    """
    full = filters.build(record)
    bundle, _, _, k, _ = bundle_for(con, record, full, settings, footprint, False, 100.0)
    return {**density.selection_peaks(bundle), "k": k}


def warm(database, settings: Settings, table_names: Iterable[str]) -> threading.Thread:
    """Compute the full-range canonical bundle of each experiment in the background.

    Best effort: a failure is logged, never raised, because a warm cache is a
    convenience and the request path computes the same bundle on demand.
    """
    names = [n for n in table_names]

    def run() -> None:
        for name in names:
            try:
                with database.read_cursor() as con:
                    record = registry.require_ready(con, name)
                    footprint = canonical.cell_footprint(con, record)
                    _, stats, grid, k, was_cached = bundle_for(
                        con, record, filters.build(record), settings, footprint, False, 100.0
                    )
                log.info(
                    "Canonical cache warmed for %s: %s events, k=%d, grid %dx%d%s",
                    name, f"{stats.n_events:,}", k, grid.n_x, grid.n_y,
                    " (already cached)" if was_cached else "",
                )
            except Exception:  # noqa: BLE001 - background convenience, never fatal
                log.exception("Canonical cache warm-up failed for %s", name)

    thread = threading.Thread(target=run, name="canonical-warm", daemon=True)
    thread.start()
    return thread
