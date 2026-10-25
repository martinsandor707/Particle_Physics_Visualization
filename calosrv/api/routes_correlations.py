"""``GET /api/correlations`` - the hit-level correlation matrix, card C8 (Page 1).

The notebook's hit-level Pearson matrix, served with what it needs to be read
honestly (``query/correlations.py``): an event-grouped jackknife interval on
every cell, with the method, the group count and n_eff in the payload so the
card quotes them rather than a Fisher-z N of hits; φ hatched with Mardia's
circular-linear R instead of a linear r; and the per-shower pairs from the
event table, hit-weighted and per shower. An aggregated experiment has no hits
and is refused by its capability, naming why.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..db.registry import ExperimentRecord
from ..models.common import ApiMeta, Timer, envelope
from ..query import correlations, density, sampling
from .deps import CursorDep, FilterDep, SettingsDep, capable

router = APIRouter()


@router.get("/api/correlations",
            summary="Hit-level correlation matrix with event-grouped jackknife intervals (C8)")
def get_correlations(
    con: CursorDep,
    record: Annotated[ExperimentRecord, capable("correlation")],
    spec: FilterDep,
    settings: SettingsDep,
    coord_system: str = Query(
        correlations.DEFAULT_COORD_SYSTEM,
        description=(
            "local (default, as the notebook): u, v, w of each hit in its own shower's "
            "frame. trans: the per-shower translated Δx, Δy and the own-shower layer depth. "
            "lab: the measured lattice coordinates of the hit's cell (raw z)."
        ),
    ),
    shower: str = Query(
        correlations.DEFAULT_SHOWER,
        description="a | b | both: whose hits enter. A single-shower experiment offers a (both = a).",
    ),
    energy_scale: str = Query(
        correlations.DEFAULT_ENERGY_SCALE,
        description="linear (default, as the notebook): hit energy in GeV. log10: log10 of it.",
    ),
    preview: bool = Query(
        False,
        description=(
            "Serve the hit cells from the 10% unbiased sample for drag preview (above 2 M "
            "hits). The response is marked exact=false; the per-shower cells stay exact."
        ),
    ),
):
    timer = Timer()
    decision = sampling.decide(record, preview, settings.sample_percent)
    body, analysis = correlations.compute(
        con, record, spec, coord_system=coord_system, shower=shower, energy_scale=energy_scale,
        sampled=decision.sampled, sample_percent=decision.percent,
    )
    warnings: list[str] = []
    if analysis.selection.n_events == 0:
        warnings.append("No events match the current selection.")

    # A cached hit scan cost nothing this time: its stored query_ms is the cold
    # scan's, which a latency readout must not be shown again.
    hit_ms = 0.0 if analysis.cached else analysis.hit.query_ms

    def respond(extra: list[str]) -> dict:
        meta = ApiMeta(
            table_name=record.table_name,
            exact=not decision.sampled,
            query_ms=hit_ms + analysis.shower_w.query_ms,
            total_ms=timer.elapsed_ms,
            cached=analysis.cached,
            warnings=warnings + extra,
            notes={"sample_percent": decision.percent if decision.sampled else 100.0},
        )
        return envelope(meta, **body, filter=spec.as_dict())

    # Seven variables make 49 cells whatever the selection, about 13 KB; measured
    # anyway, as served, so a future addition cannot pass the contract silently.
    payload = respond([])
    size = density.wire_size(payload)
    if size >= density.RESPONSE_LIMIT:
        payload = respond([f"The correlation response measured {size:,} bytes against the "
                           f"{density.RESPONSE_LIMIT:,}-byte contract and is served as it is."])
    return payload
