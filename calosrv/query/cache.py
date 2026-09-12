"""LRU cache of native-resolution projection bundles.

This is what turns the resolution control, the display-mode toggle and the
palette picker from database queries into NumPy operations.

The insight is that the *scan* depends only on the kinematic selection, while
the resolution, the display mode, the colour map and the centroid weighting are
all downstream transformations of the same native-resolution aggregates. Caching
at the native-resolution boundary therefore serves all of them from one scan:
change the resolution from 150 to 200 and nothing is re-queried at all.

Entries are keyed by the filter's rounded bounds, so two slider positions a
float ulp apart share an entry rather than each paying for a full scan.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from .projections import NativeBundle

log = logging.getLogger(__name__)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": round(self.hit_rate, 4),
        }


class BundleCache:
    """Thread-safe LRU over :class:`NativeBundle` objects."""

    def __init__(self, max_entries: int = 128) -> None:
        self._max = max(1, max_entries)
        self._entries: OrderedDict[tuple, NativeBundle] = OrderedDict()
        self._lock = threading.Lock()
        self.stats = CacheStats()

    def get_or_compute(
        self, key: tuple, compute: Callable[[], NativeBundle]
    ) -> tuple[NativeBundle, bool]:
        """Return the cached bundle for ``key``, computing it on a miss.

        Returns ``(bundle, was_cached)``. The lock is *not* held while
        ``compute`` runs: a scan can take hundreds of milliseconds, and blocking
        every other reader for its duration would be far worse than the
        occasional duplicated scan when two identical requests race.
        """
        with self._lock:
            bundle = self._entries.get(key)
            if bundle is not None:
                self._entries.move_to_end(key)
                self.stats.hits += 1
                return bundle, True
            self.stats.misses += 1

        bundle = compute()

        with self._lock:
            self._entries[key] = bundle
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)
                self.stats.evictions += 1
        return bundle, False

    def invalidate_table(self, table_name: str) -> int:
        """Drop every entry for one experiment.

        Called when a table is re-ingested or appended to. Without this, an
        append would leave the interface showing pre-append aggregates until the
        entries happened to be evicted.
        """
        with self._lock:
            stale = [k for k in self._entries if k and k[0] == table_name]
            for key in stale:
                del self._entries[key]
        if stale:
            log.info("Invalidated %d cached bundle(s) for %r", len(stale), table_name)
        return len(stale)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def nbytes(self) -> int:
        with self._lock:
            return sum(b.nbytes for b in self._entries.values())

    def info(self) -> dict[str, Any]:
        with self._lock:
            entries = len(self._entries)
        return {
            "entries": entries,
            "max_entries": self._max,
            "bytes": self.nbytes,
            **self.stats.as_dict(),
        }


_cache: BundleCache | None = None
_cache_lock = threading.Lock()


def get_cache(max_entries: int = 128) -> BundleCache:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = BundleCache(max_entries)
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None
