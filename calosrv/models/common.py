"""The response envelope shared by every data endpoint.

Every payload carries the same metadata block: which experiment it describes,
what selection produced it, how long the query took, whether the numbers are
exact or sampled, and any warnings. Putting it on every response means the
interface never has to guess whether what it is drawing is an estimate.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApiMeta:
    """Provenance for one response."""

    table_name: str
    exact: bool = True
    query_ms: float = 0.0
    total_ms: float = 0.0
    cached: bool = False
    warnings: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "exact": self.exact,
            "query_ms": round(self.query_ms, 3),
            "total_ms": round(self.total_ms, 3),
            "cached": self.cached,
            "warnings": list(self.warnings),
            **self.notes,
        }


class Timer:
    """Wall-clock timer for the ``total_ms`` figure in the KPI card."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0


def json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats with ``None``.

    JSON has no encoding for infinity or NaN, so a single one anywhere in a
    payload aborts the whole response with HTTP 500 - which is how a narrow
    kinematic selection could take down the model-performance panel, since a
    relative residual over a femto-GeV true energy overflows.

    The individual metrics already guard themselves (``stats/metrics.finite``);
    this is the net beneath them, so a future aggregate added to a query cannot
    reintroduce the same 500. ``null`` renders as an em dash in the interface,
    which is the honest reading: the quantity is not defined for this selection.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def envelope(meta: ApiMeta, **payload: Any) -> dict[str, Any]:
    return json_safe({"meta": meta.as_dict(), **payload})
