"""``GET /api/response`` - the sampling-fraction cards B1, B2 and the resolution (Page 1).

One request feeds three cards: ``parts`` names the ones wanted, and a part not
asked for is ``null`` in the body. B3, the momentum-sliced energy
distributions, lives on ``/api/energy-distribution?slice_by=momentum``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..models.common import ApiMeta, Timer, envelope
from ..query import capabilities, density, response, showers
from ..stats import clip as clip_mod
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


def _guard_note(step: response.Fidelity, first: int, bins: int | None) -> str:
    coarser = f"B1's histogram has {bins} bins and " if bins else ""
    return (
        f"{coarser}numbers are written at {step.digits} significant figures to keep the "
        f"response under the {density.RESPONSE_LIMIT:,}-byte contract ({first:,} bytes at full "
        "fidelity); no statistic changed."
    )


@router.get(
    "/api/response",
    summary="Sampling-fraction distribution, mean per momentum bin and energy resolution",
)
def get_response(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    parts: str | None = Query(
        None,
        description=(
            "Comma-separated cards to compute: b1 (sampling-fraction distribution), b2 (mean "
            "sampling fraction per momentum bin) and resolution (σ/μ per momentum bin). "
            "Defaults to all three; a part not asked for is null."
        ),
    ),
    shower: str = Query(
        "both",
        description=(
            "a | b | both: which shower's series to return. A single-shower experiment has "
            "shower a only; b is refused."
        ),
    ),
    clip_low: float = Query(
        clip_mod.DEFAULT_LOW_PERCENTILE, ge=0.0, le=49.0,
        description="Lower percentile of B1's displayed axis (the axis is zero-based, so it "
                    "is reported and not applied).",
    ),
    clip_high: float = Query(
        clip_mod.DEFAULT_HIGH_PERCENTILE, ge=51.0, le=100.0,
        description="Upper percentile bounding B1's displayed sampling-fraction axis.",
    ),
    bins: int | None = Query(
        None, ge=8, le=500,
        description=(
            "B1 histogram bin count. Left unset, it adapts to the smallest series that draws "
            "a histogram, so no histogram is finer than its own statistics support."
        ),
    ),
):
    timer = Timer()
    wanted = response.parse_parts(parts)
    capabilities.require(record, *(response.GATES[part] for part in wanted), field="parts")
    columns = showers.of(record, shower)
    result = response.compute(
        con, record, spec, columns, response.Request(wanted, clip_low, clip_high, bins))

    def respond(step: response.Fidelity, extra: list[str]) -> dict[str, Any]:
        body = result.as_dict(step)
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=[*result.warnings(), *extra],
            notes={"parts": list(wanted)},
        )
        return envelope(meta, **body, filter=spec.as_dict())

    # Measured as served. The ladder only shortens how B1's histogram and the
    # numbers are written, never a statistic, and says so; if it runs out the
    # response is served over the contract with the size stated.
    steps = response.FIDELITY_STEPS
    body = respond(steps[0], [])
    first = size = density.wire_size(body)
    used = steps[0]
    for step in steps[1:]:
        if size < density.RESPONSE_LIMIT:
            break
        used = step
        body = respond(step, [_guard_note(step, first, result.bins(step))])
        size = density.wire_size(body)
    if size >= density.RESPONSE_LIMIT:
        body = respond(used, [
            _guard_note(used, first, result.bins(used)),
            f"The response is still {size:,} bytes, over the {density.RESPONSE_LIMIT:,}-byte "
            "contract; it is served as it is.",
        ])
    return body
