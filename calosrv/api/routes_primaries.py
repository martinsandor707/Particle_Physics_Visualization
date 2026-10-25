"""``GET /api/primaries`` - events without a primary-tagged hit, C11 (Page 2).

Single-shower hit experiments only: the tag is a column of the single-shower hit
files, so any other kind is refused with the capability problem naming why.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter

from ..db.registry import ExperimentRecord
from ..models.common import ApiMeta, Timer, envelope
from ..query import primaries
from .deps import CursorDep, FilterDep, capable

router = APIRouter()


@router.get(
    "/api/primaries",
    summary="Events without a primary-tagged hit, per momentum bin, with Wilson intervals",
)
def get_primaries(
    con: CursorDep,
    # Before the filter: a kind that cannot serve the card is refused as such,
    # not for a selection it could never have made.
    record: Annotated[ExperimentRecord, capable("prim-rate")],
    spec: FilterDep,
):
    timer = Timer()
    result = primaries.compute(con, record, spec)
    warnings = ["No events match the current selection."] if result.n_events == 0 else []
    meta = ApiMeta(
        table_name=record.table_name,
        exact=True,
        total_ms=timer.elapsed_ms,
        warnings=warnings,
    )
    return envelope(meta, **result.as_dict(), filter=spec.as_dict())
