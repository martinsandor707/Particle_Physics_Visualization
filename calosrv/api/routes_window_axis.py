"""``GET /api/window-axis`` - the ensemble incident axis of the events entering a depth panel's window.

The absolute frame's one sanctioned ensemble direction, licensed per window
by measurement (``query/window_axis.py``): the client asks for it whenever a
depth panel is zoomed to a transverse window narrower than the detector, and
draws nothing of the kind at full extent.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models.common import ApiMeta, Timer, envelope
from ..query import window_axis
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


@router.get("/api/window-axis", summary="The mean incident trajectory of the events entering a depth panel's window")
def get_window_axis(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    panel: str = Query(..., description="yz | xz: the depth panel, which fixes the transverse coordinate."),
    t_min: float = Query(..., description="Lower edge of the displayed transverse window, in mm."),
    t_max: float = Query(..., description="Upper edge of the displayed transverse window, in mm."),
):
    timer = Timer()
    body = window_axis.window_axis(con, record, spec, panel, t_min, t_max)
    notices = [{"scope": "window_axis", "text": text} for text in body["notes"]]
    meta = ApiMeta(
        table_name=record.table_name, exact=True, query_ms=body.pop("elapsed_ms"),
        total_ms=timer.elapsed_ms, notes={"panel": panel, "notices": notices},
    )
    return envelope(meta, **body, filter=spec.as_dict())
