"""LRU caches of native-resolution projection bundles.

This is what turns the resolution control, the display-mode toggle and the
palette picker from database queries into NumPy operations.

The insight is that the *scan* depends only on the kinematic selection, while
the resolution, the display mode, the colour map and the centroid weighting are
all downstream transformations of the same native-resolution aggregates. Caching
at the native-resolution boundary therefore serves all of them from one scan:
change the resolution from 150 to 200 and nothing is re-queried at all.

Entries are keyed by the filter's rounded bounds, so two slider positions a
float ulp apart share an entry rather than each paying for a full scan.

**Two caches, one registry.** The laboratory frame and the canonical frame hold
bundles of different shapes and sizes (a canonical bundle spans a 350 x 138
grid and weighs a few megabytes), so each frame owns a named cache with its own
entry budget. Every cache lives in one registry, so that invalidating a table
after a re-ingest or resetting between tests reaches all of them - a stale
canonical bundle surviving an append would be exactly the failure the lab
cache's invalidation exists to prevent.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)

LAB_CACHE = "lab"
CANONICAL_CACHE = "canonical"
TRANS_CACHE = "trans"
LOCAL_CACHE = "local"

#: Default byte budget per named cache. The entry count alone does not bound
#: memory once bundles differ in size (a canonical bundle is several times a
#: laboratory one), and the Python heap - which these caches live in - sits
#: outside DuckDB's memory_limit, inside the container's ~4 GB of headroom.
DEFAULT_MAX_BYTES = {
    LAB_CACHE: 256 * 1024 ** 2,
    CANONICAL_CACHE: 256 * 1024 ** 2,
    TRANS_CACHE: 128 * 1024 ** 2,
    LOCAL_CACHE: 128 * 1024 ** 2,
}


class Cacheable(Protocol):
    """What a cached bundle must offer: its memory footprint."""

    @property
    def nbytes(self) -> int: ...


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
    """Thread-safe LRU over bundle objects."""

    def __init__(
        self, max_entries: int = 128, name: str = LAB_CACHE, max_bytes: int | None = None
    ) -> None:
        self._max = max(1, max_entries)
        self._max_bytes = max_bytes
        self.name = name
        self._entries: OrderedDict[tuple, Any] = OrderedDict()
        self._lock = threading.Lock()
        self.stats = CacheStats()
        #: Bumped by every invalidation of a table. A scan that was already
        #: running when its table was invalidated read the old tables, so its
        #: result is returned to its caller but never inserted.
        self._generation: dict[Any, int] = {}

    def get_or_compute(
        self, key: tuple, compute: Callable[[], Any]
    ) -> tuple[Any, bool]:
        """Return the cached bundle for ``key``, computing it on a miss.

        Returns ``(bundle, was_cached)``. The lock is *not* held while
        ``compute`` runs: a scan can take hundreds of milliseconds, and blocking
        every other reader for its duration would be far worse than the
        occasional duplicated scan when two identical requests race.
        """
        table = key[0] if key else None
        with self._lock:
            bundle = self._entries.get(key)
            if bundle is not None:
                self._entries.move_to_end(key)
                self.stats.hits += 1
                return bundle, True
            self.stats.misses += 1
            generation = self._generation.get(table, 0)

        bundle = compute()

        with self._lock:
            if self._generation.get(table, 0) != generation:
                return bundle, False
            self._entries[key] = bundle
            self._entries.move_to_end(key)
            while len(self._entries) > self._max or (
                self._max_bytes is not None and len(self._entries) > 1
                and sum(b.nbytes for b in self._entries.values()) > self._max_bytes
            ):
                self._entries.popitem(last=False)
                self.stats.evictions += 1
        return bundle, False

    def get_any(self, keys: list[tuple]) -> Any | None:
        """The first of ``keys`` that is cached, counted as a hit; else ``None``.

        A density request is the same for every network, so it can be served
        from whichever network's bundle of the selection is already cached.
        """
        with self._lock:
            for key in keys:
                bundle = self._entries.get(key)
                if bundle is not None:
                    self._entries.move_to_end(key)
                    self.stats.hits += 1
                    return bundle
        return None

    def invalidate_table(self, table_name: str) -> int:
        """Drop every entry for one experiment.

        Called when a table is re-ingested or appended to. Without this, an
        append would leave the interface showing pre-append aggregates until the
        entries happened to be evicted. Every key starts with the table name.
        """
        with self._lock:
            self._generation[table_name] = self._generation.get(table_name, 0) + 1
            stale = [k for k in self._entries if k and k[0] == table_name]
            for key in stale:
                del self._entries[key]
        if stale:
            log.info(
                "Invalidated %d cached %s bundle(s) for %r", len(stale), self.name, table_name
            )
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
            "name": self.name,
            "entries": entries,
            "max_entries": self._max,
            "max_bytes": self._max_bytes,
            "bytes": self.nbytes,
            **self.stats.as_dict(),
        }


_caches: dict[str, BundleCache] = {}
_cache_lock = threading.Lock()


def get_cache(
    max_entries: int = 128, name: str = LAB_CACHE, max_bytes: int | None = None
) -> BundleCache:
    """The named cache, created on first use with ``max_entries`` and a byte budget."""
    cache = _caches.get(name)
    if cache is None:
        with _cache_lock:
            cache = _caches.get(name)
            if cache is None:
                budget = max_bytes if max_bytes is not None else DEFAULT_MAX_BYTES.get(name)
                cache = BundleCache(max_entries, name=name, max_bytes=budget)
                _caches[name] = cache
    return cache


def invalidate_all(table_name: str) -> int:
    """Drop one experiment's entries from every cache that exists."""
    with _cache_lock:
        caches = list(_caches.values())
    return sum(cache.invalidate_table(table_name) for cache in caches)


def reset_cache() -> None:
    """Forget every cache. Tests call this between booted servers."""
    global _caches
    with _cache_lock:
        _caches = {}
