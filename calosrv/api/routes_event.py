"""``GET /api/event`` - the Event Inspector: one shower of one event in three frames.

The reference notebook's comparison figure (``local-coords.ipynb``, cell 6):
nine server-rendered rasters - original, translated, local; X-Y, X-Z, Y-Z -
with the incident direction, the first-layer plane, the origin and the
principal-axis tilt, under the 100 KB contract. ``GET /api/event/pick``
reproduces the notebook's selection rule for a seeded, stated choice.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import canonical, event_inspector, frame_sql
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


@router.get("/api/event", summary="One shower of one event in the original, translated and local frames")
def get_event(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    event_number: int = Query(..., description="The event to draw."),
    shower: str = Query("a", description="a | b: which of the event's two showers."),
    coordinates: str = Query(
        frame_sql.SOURCE_FILE,
        description=(
            "file (default): the translated and local panels use the file's own columns; "
            "computed: the SE(3) motions applied to the laboratory lattice. The residual between "
            "the two is reported either way."
        ),
    ),
):
    timer = Timer()
    if shower not in event_inspector.SHOWERS:
        raise ValidationError(f"shower must be a or b; got {shower!r}.", field="shower")
    if coordinates not in frame_sql.SOURCES:
        raise ValidationError(
            f"coordinates must be one of {', '.join(frame_sql.SOURCES)}; got {coordinates!r}.",
            field="coordinates",
        )
    footprint = canonical.cell_footprint(con, record)
    body = event_inspector.inspect(con, record, spec, event_number, shower, coordinates, footprint)
    warnings: list[str] = []
    if not body["event"]["in_selection"]:
        warnings.append(
            f"Event {event_number} lies outside the current selection; it is drawn as asked, and the "
            "previous / next controls walk the selection."
        )
    notices = [{"scope": "event", "text": body["coordinates"]["note"]},
               {"scope": "event", "text": body["window"]["rule"]},
               {"scope": "event", "text": body["scale"]["rule"]}]
    for note in body["grid"]["notes"]:
        notices.append({"scope": "event", "text": note})
    meta = ApiMeta(
        table_name=record.table_name, exact=True, query_ms=body.pop("elapsed_ms"),
        total_ms=timer.elapsed_ms, warnings=warnings,
        notes={"event": int(event_number), "shower": shower, "coordinates": coordinates,
               "notices": notices},
    )
    return envelope(meta, **body, filter=spec.as_dict())


@router.get("/api/event/pick", summary="The reference notebook's event selection rule, seeded")
def pick_event(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    seed: int = Query(42, ge=0, description="Seed of the random draw from the pool."),
    pool_size: int = Query(20, ge=1, le=200, description="Size of the largest-angle pool."),
):
    timer = Timer()
    body = event_inspector.pick(con, record, spec, seed=seed, pool_size=pool_size)
    meta = ApiMeta(table_name=record.table_name, exact=True, total_ms=timer.elapsed_ms)
    return envelope(meta, **body, filter=spec.as_dict())
