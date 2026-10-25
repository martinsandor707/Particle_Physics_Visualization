"""``GET /api/statistics`` - descriptive statistics of the hits (C1) and the hits at negative depth (C9).

One request fills the statistics card: the notebook's ``describe()`` table of
the hit coordinates and energy in the chosen frame, beside the energy-weighted
quartiles that answer a different question (``query/statistics.py``), and the
share of hits and energy that lie upstream of their shower's entry point
(``query/negative_depth.py``). The card is gated on ``statistics``: an
aggregated experiment has no hits to describe and is refused naming why. The
negative-depth block has its own gate and is never a reason to refuse the
request - an experiment derived before the Group-1 columns existed gets
``negative_w.available = false`` with the rebuild it needs, and the table
beside it is served as before.

The table is exact; ``preview`` serves it from the 10% sample of hit rows above
two million hits and marks the response ``exact: false``. The event counts and
the negative-depth block come from the event table, so they are exact either way.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..db import ddl
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import density, negative_depth, sampling, showers, statistics
from .deps import CursorDep, FilterDep, SettingsDep, capable

router = APIRouter()


@router.get(
    "/api/statistics",
    summary="Descriptive statistics of the hit coordinates and energy (C1) and of hits at negative depth (C9)",
)
def get_statistics(
    con: CursorDep,
    record: Annotated[ExperimentRecord, capable("statistics")],
    spec: FilterDep,
    settings: SettingsDep,
    coord_system: str = Query(
        "local",
        description=(
            "local (default, as the notebook): u, v, w of each hit in its own shower's frame, "
            "and the 2-D transverse radius ρ. trans: the per-shower translated Δx, Δy and the "
            "own-shower layer depth. lab: the measured lattice coordinates of the hit's cell "
            "(raw z), with the notebook's z − 3649 mm as a labelled row. The negative-depth "
            "block is defined in the Local frame whichever is chosen."
        ),
    ),
    shower: str = Query(
        "both",
        description=(
            "a | b | both: whose hits and showers enter. A two-shower experiment pools A and B "
            "under `both` (A+B rows count with B); a single-shower experiment offers a "
            "(both = a)."
        ),
    ),
    preview: bool = Query(
        False,
        description=(
            "Serve the hit table from the 10% unbiased sample for drag preview (above 2 M "
            "hits). The response is marked exact=false; the event counts and the "
            "negative-depth block stay exact."
        ),
    ),
):
    timer = Timer()
    if coord_system not in ddl.COORD_SYSTEMS:
        raise ValidationError(
            f"coord_system must be one of {', '.join(ddl.COORD_SYSTEMS)}; got {coord_system!r}.",
            field="coord_system",
        )
    scope = showers.of(record, shower)
    statistics.require_frame(record, coord_system)
    decision = sampling.decide(record, preview, settings.sample_percent)

    scan, was_cached = statistics.describe_hits(
        con, record, spec, coord_system, scope, sampled=decision.sampled)
    n_events, n_hits = statistics.selection_counts(con, record, spec, scope)
    negative_w = negative_depth.summarise(con, record, spec, shower)

    warnings: list[str] = []
    if n_events == 0:
        warnings.append("No events match the current selection.")
    if decision.sampled:
        warnings.append(decision.reason)
    notes = statistics.notes(record, coord_system, scope, scan, n_hits,
                             decision.sampled, decision.percent)
    if negative_w["available"]:
        notes += negative_depth.rationale()

    def respond(extra: list[str]) -> dict:
        meta = ApiMeta(
            table_name=record.table_name,
            exact=not decision.sampled,
            query_ms=scan.query_ms,
            total_ms=timer.elapsed_ms,
            cached=was_cached,
            warnings=warnings + extra,
            notes={"coord_system": coord_system, "shower": shower,
                   "sample_percent": decision.percent if decision.sampled else 100.0},
        )
        return envelope(
            meta,
            describe=statistics.block(scan, n_hits),
            n_events=n_events,
            negative_w=negative_w,
            notes=notes,
            filter=spec.as_dict(),
        )

    # At most five rows of sixteen numbers, four splits and a dozen sentences, about
    # 6 KB whatever the selection. Measured as served all the same, and said if it misses.
    payload = respond([])
    size = density.wire_size(payload)
    if size >= density.RESPONSE_LIMIT:
        payload = respond([f"The statistics response measured {size:,} bytes against the "
                           f"{density.RESPONSE_LIMIT:,}-byte contract and is served as it is."])
    return payload
