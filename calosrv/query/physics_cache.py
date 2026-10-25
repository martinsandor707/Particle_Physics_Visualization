"""The cache, single flight and scan gate of the hit-level physics scans.

The physics cards (C1 statistics, C4 hit distributions, C8 correlations, the
feature explorer) each reduce a selection's hits to a few kilobytes of sums -
moment sums per event group, fine histograms - from which every display choice
(clip window, binning, quantity, scale) is a NumPy step. The sums are cached
per selection in the named ``physics`` cache, keyed with the clamped filter
first so invalidating a table reaches them.

Two guards the bundle cache does not give:

* **Single flight.** Two identical requests arriving together (a page load
  and a slider settle, say) share one scan: the second waits for the first's
  result instead of paying for the same seconds of DuckDB work again.
* **One heavy scan at a time.** A hit scan reads every selected hit; several
  at once compete for DuckDB's memory budget. Heavy scans are serialised by a
  process-wide semaphore; event-table reads never take it.
"""

from __future__ import annotations

import dataclasses
import sys
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from . import cache as cache_mod

#: Entries the physics cache holds; the byte budget (``cache.DEFAULT_MAX_BYTES``) binds first.
MAX_ENTRIES = 64

_heavy = threading.BoundedSemaphore(1)
_flight_lock = threading.Lock()
_in_flight: dict[tuple, threading.Event] = {}


def nbytes_of(value: Any) -> int:
    """A generous estimate of a cached value's memory: arrays exactly, the rest roughly."""
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return 64 + sum(nbytes_of(getattr(value, f.name)) for f in dataclasses.fields(value))
    if isinstance(value, dict):
        return 64 + sum(nbytes_of(k) + nbytes_of(v) for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return 56 + sum(nbytes_of(v) for v in value)
    return sys.getsizeof(value)


@dataclasses.dataclass
class Entry:
    """A cached value with its footprint, as ``BundleCache`` requires."""

    value: Any
    nbytes: int


def get_cache() -> cache_mod.BundleCache:
    return cache_mod.get_cache(MAX_ENTRIES, name=cache_mod.PHYSICS_CACHE)


def get_or_compute(key: tuple, compute: Callable[[], Any], heavy: bool = True,
                   cache: cache_mod.BundleCache | None = None) -> tuple[Any, bool]:
    """``(value, was_cached)`` for ``key``; ``key[0]`` must be the table name.

    ``heavy`` scans run one at a time across the process. A request for a key
    already being computed waits for that computation instead of repeating it.
    ``cache`` stores the result somewhere other than the physics cache, for a
    value that carries its own ``nbytes`` and would evict every physics card's
    entry (the 3-D voxel bundles): the single flight and the heavy-scan gate
    are the same.
    """
    wrapped = cache is None
    store = get_cache() if wrapped else cache

    def unwrap(stored: Any) -> Any:
        return stored.value if wrapped else stored

    while True:
        with _flight_lock:
            hit = store.get_any([key])
            if hit is not None:
                return unwrap(hit), True
            event = _in_flight.get(key)
            if event is None:
                event = threading.Event()
                _in_flight[key] = event
                owner = True
            else:
                owner = False
        if not owner:
            # Another thread is computing it: wait, then read what it stored.
            # If it failed (or its table was invalidated meanwhile), loop and
            # compute here.
            event.wait()
            continue
        try:
            def run() -> Any:
                if heavy:
                    with _heavy:
                        value = compute()
                else:
                    value = compute()
                return Entry(value, nbytes_of(value)) if wrapped else value

            stored, cached = store.get_or_compute(key, run)
            return unwrap(stored), cached
        finally:
            with _flight_lock:
                _in_flight.pop(key, None)
            event.set()
