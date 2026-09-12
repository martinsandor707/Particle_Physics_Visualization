"""The response envelope shared by every data endpoint.

Every payload carries the same metadata block: which experiment it describes,
what selection produced it, how long the query took, whether the numbers are
exact or sampled, and any warnings. Putting it on every response means the
interface never has to guess whether what it is drawing is an estimate.
"""

from __future__ import annotations

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


def envelope(meta: ApiMeta, **payload: Any) -> dict[str, Any]:
    return {"meta": meta.as_dict(), **payload}
