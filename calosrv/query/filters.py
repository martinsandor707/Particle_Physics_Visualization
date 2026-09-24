"""The kinematic filter, shared by every endpoint.

``E1``, ``E2`` and ``D`` are per-event constants that the source file replicates
onto every hit row of an event. That was verified directly against the data, and
it is what keeps filtering cheap: the predicate is a plain row comparison on the
projection table, with no join, no subquery and no window function over 22.5
million rows.

The sharp edge is the null separation distance. Roughly 0.11% of rows carry an
empty ``centroid_AB_distance``, and the emptiness is a property of the event,
not of individual rows: these are degenerate events in which shower A deposited
no energy at all, so there is no A centroid and no A-B separation. ``d BETWEEN a
AND b`` evaluates to NULL for them, SQL treats that as false, and they vanish -
silently, and in numbers that correlate with the overlap regime under study.

So the predicate always writes ``d IS NOT NULL`` explicitly, even though
``BETWEEN`` already implies it. The clause is then self-documenting, it survives
the next person editing it, and the count of what it removes is reported
alongside every result rather than left for someone to discover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..db.registry import ExperimentRecord
from ..errors import ValidationError


@dataclass(frozen=True)
class FilterSpec:
    """A kinematic selection, resolved against an experiment's bounds."""

    table_name: str
    e1_min: float
    e1_max: float
    e2_min: float
    e2_max: float
    d_min: float
    d_max: float
    include_undefined_d: bool = False

    def where_sql(self, alias: str = "") -> str:
        """The ``WHERE`` body for this selection."""
        p = f"{alias}." if alias else ""
        clauses = [
            f"{p}e1 BETWEEN $e1_min AND $e1_max",
            f"{p}e2 BETWEEN $e2_min AND $e2_max",
        ]
        if self.include_undefined_d:
            clauses.append(
                f"({p}d IS NULL OR {p}d BETWEEN $d_min AND $d_max)"
            )
        else:
            clauses.append(f"{p}d IS NOT NULL")
            clauses.append(f"{p}d BETWEEN $d_min AND $d_max")
        return " AND ".join(clauses)

    def params(self) -> dict[str, Any]:
        return {
            "e1_min": self.e1_min,
            "e1_max": self.e1_max,
            "e2_min": self.e2_min,
            "e2_max": self.e2_max,
            "d_min": self.d_min,
            "d_max": self.d_max,
        }

    def clamped(self, record: ExperimentRecord) -> "FilterSpec":
        """The same selection with every bound clamped to the dataset's range.

        A bound looser than the data selects exactly the same rows, so the
        clamped spec is equivalent - but it has one canonical form. The
        interface snaps its slider domains *outward* to a step grid, so its
        "whole dataset" request carries 0.70-20.00 GeV where the data span
        0.708-19.999; without clamping, that request and the one the start-up
        warmer issued from the exact bounds would sit in two cache entries, and
        the two-second canonical scan the warmer paid for would be paid again
        on the first page load.
        """

        def clamp_interval(
            lo_req: float, hi_req: float, lo: float | None, hi: float | None
        ) -> tuple[float, float]:
            # An interval that misses the data entirely must stay empty: clamping
            # its two ends independently would collapse it onto the data extreme
            # and resurrect the boundary event. Only an intersecting interval is
            # equivalent to its clamped form.
            if lo is None or hi is None:
                return lo_req, hi_req
            if hi_req < lo or lo_req > hi:
                return lo_req, hi_req
            return max(lo_req, float(lo)), min(hi_req, float(hi))

        e1_min, e1_max = clamp_interval(self.e1_min, self.e1_max, record.e1_min, record.e1_max)
        e2_min, e2_max = clamp_interval(self.e2_min, self.e2_max, record.e2_min, record.e2_max)
        d_min, d_max = clamp_interval(self.d_min, self.d_max, record.d_min, record.d_max)
        return FilterSpec(
            table_name=self.table_name,
            e1_min=e1_min, e1_max=e1_max,
            e2_min=e2_min, e2_max=e2_max,
            d_min=d_min, d_max=d_max,
            include_undefined_d=self.include_undefined_d,
        )

    def cache_key(self) -> tuple:
        """Identity of this selection, for the projection matrix cache.

        Bounds are rounded to six significant figures so that two slider
        positions a float ulp apart share a cache entry instead of each paying
        for a full scan.
        """
        return (
            self.table_name,
            round(self.e1_min, 6), round(self.e1_max, 6),
            round(self.e2_min, 6), round(self.e2_max, 6),
            round(self.d_min, 4), round(self.d_max, 4),
            self.include_undefined_d,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "e1": [self.e1_min, self.e1_max],
            "e2": [self.e2_min, self.e2_max],
            "d": [self.d_min, self.d_max],
            "include_undefined_d": self.include_undefined_d,
        }


def _resolve(
    value: float | None, fallback: float | None, default: float
) -> float:
    if value is not None:
        return float(value)
    if fallback is not None:
        return float(fallback)
    return default


def build(
    record: ExperimentRecord,
    e1_min: float | None = None,
    e1_max: float | None = None,
    e2_min: float | None = None,
    e2_max: float | None = None,
    d_min: float | None = None,
    d_max: float | None = None,
    include_undefined_d: bool = False,
) -> FilterSpec:
    """Build a filter, defaulting each unset bound to the dataset's own range.

    An unset bound means "no restriction on this axis", which is the dataset's
    full extent - not zero, and not an arbitrary constant that would silently
    exclude data on a dataset with a different energy range.
    """
    spec = FilterSpec(
        table_name=record.table_name,
        e1_min=_resolve(e1_min, record.e1_min, 0.0),
        e1_max=_resolve(e1_max, record.e1_max, 0.0),
        e2_min=_resolve(e2_min, record.e2_min, 0.0),
        e2_max=_resolve(e2_max, record.e2_max, 0.0),
        d_min=_resolve(d_min, record.d_min, 0.0),
        d_max=_resolve(d_max, record.d_max, 0.0),
        include_undefined_d=include_undefined_d,
    )

    for label, lo, hi in (
        ("E1", spec.e1_min, spec.e1_max),
        ("E2", spec.e2_min, spec.e2_max),
        ("D", spec.d_min, spec.d_max),
    ):
        if lo > hi:
            raise ValidationError(
                f"{label} range is inverted: minimum {lo:g} exceeds maximum "
                f"{hi:g}.",
                field=label.lower(),
            )
    return spec
