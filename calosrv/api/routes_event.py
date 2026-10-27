"""``GET /api/event`` - one event: the Event Inspector's rasters, or the 3-D cubes of Page 2.

``format=raster`` (the default) is the reference notebook's comparison figure
(``local-coords.ipynb``, cell 6): nine server-rendered rasters - original,
translated, local; X-Y, X-Z, Y-Z - of one shower, with the incident direction,
the first-layer plane, the origin and the principal-axis tilt, under the
100 KB contract (``query/event_inspector.py``). ``format=voxels`` is the
notebook's 3-D event display (C5, and C6 by species): the event as cubes in
one frame for an orthographic ``echarts-gl`` view (``query/voxel_event.py``),
its whole body measured against the contract by the shared guard
(``api/budget.py``), which lowers the splat pitch and then the cube cap and
says so. ``GET /api/event/pick`` picks an event by a stated notebook rule.

Both formats need hits and the lattice: an aggregated experiment is refused
(422, ``/problems/unsupported-capability``) before anything else, the raster
under the ``event-inspector`` gate and the cubes under ``vox-event``. A
single-shower experiment has one shower per event, so ``shower=b`` is refused
naming the parameter (and, for the cubes, ``both``); the D-frame, the network
channels and the species channel are refused where the data lacks what they
are built from, naming ``frame`` or ``channel``. The voxel-only parameters -
``frame``, ``channel``, ``model`` and ``cap`` - are read only for the cubes: a
raster request is never refused over any of them, and the cubes refuse a cap
outside 100..15000 naming ``cap``. A D-frame event whose entry anchors sit
closer than 80 mm carries the D-frame's own sentence that its orientation is
effectively random.

``window`` names the window rule, read by both formats: ``shared``, one
half-width for every axis of the event, is the raster's default (Page 1's
Event Inspector, pinned by the two-shower golden snapshot); ``per_axis``, one
half-width per axis, is the cubes' default, and the Models page asks the
raster for it too, so the 3-D box and its three projections agree. Any other
value is refused naming ``window``.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import canonical, capabilities, event_inspector, frame_sql, voxel_event
from ..query import showers as showers_mod
from ..text import typographic
from . import budget, frame_canonical
from .deps import CursorDep, FilterDep, RecordDep, capable

router = APIRouter()

#: The experiment, refused unless it can serve the Event Inspector (the pick).
InspectableDep = Annotated[ExperimentRecord, capable("event-inspector")]

_FORMAT_HELP = (
    "raster (default): the Event Inspector's nine rasters of one shower; voxels: the event as "
    "3-D cubes in one frame (Page 2's C5 / C6 display)."
)


def _event_record(
    record: RecordDep,
    format: str = Query(voxel_event.FORMAT_RASTER, description=_FORMAT_HELP),
) -> ExperimentRecord:
    """The experiment, refused unless it can serve the format asked for.

    Before the filter: a kind that cannot serve the view is refused as such,
    not for a selection it could never have made. ``format`` is declared here
    and on the route alike; FastAPI binds the one query parameter to both.
    """
    if format not in voxel_event.FORMATS:
        raise ValidationError(
            f"format must be one of {', '.join(voxel_event.FORMATS)}; got {format!r}.", field="format")
    capabilities.require(record, voxel_event.FORMAT_GATES[format])
    return record


EventRecordDep = Annotated[ExperimentRecord, Depends(_event_record)]


@router.get("/api/event", summary="One event: the Event Inspector's rasters, or its 3-D cubes")
def get_event(
    con: CursorDep,
    record: EventRecordDep,
    spec: FilterDep,
    event_number: int = Query(..., description="The event to draw."),
    format: str = Query(voxel_event.FORMAT_RASTER, description=_FORMAT_HELP),
    shower: str | None = Query(
        None,
        description=(
            "a | b, and both for the cubes: which of the event's showers. Raster: a by default. "
            "Voxels: both by default in the laboratory frame and the D-frame of a two-shower "
            "experiment, a otherwise; both is offered only in those two frames. A single-shower "
            "experiment has only a."
        ),
    ),
    coordinates: str = Query(
        frame_sql.SOURCE_FILE,
        description=(
            "file (default): the translated and local panels (and the Local cubes) use the file's "
            "own columns; computed: the SE(3) motions applied to the laboratory lattice. The "
            "residual between the two is reported either way."
        ),
    ),
    frame: str = Query(
        voxel_event.DEFAULT_FRAME,
        description=(
            "Voxels only. lab | trans | local (default, the notebook's) | canonical: lab and "
            "trans draw one cube per cell; local and canonical split each cell's footprint onto "
            "axis-aligned 20 mm voxels, because a cube cannot tilt. canonical needs two showers."
        ),
    ),
    channel: str = Query(
        voxel_event.CHANNEL_ENERGY,
        description=(
            "Voxels only. energy (default, log volumetric density) | gradcam | shapcam (signed) | "
            "segerr (|f_A,pred − f_A,true|) need the networks' columns; species needs the "
            "single-shower species columns."
        ),
    ),
    model: str = Query(
        "segmentation",
        description="Voxels only. angle | energy | segmentation: the network a CAM channel reads.",
    ),
    # An integer, range-checked only for the cubes: the raster ignores the value, as it
    # ignores frame, channel and model, so a raster request is never refused over its range.
    cap: int | None = Query(
        None,
        description=(
            f"Voxels only. An integer {voxel_event.MIN_CAP}..{voxel_event.MAX_CAP} (default "
            f"{voxel_event.DEFAULT_CAP}): most cubes drawn, ranked by energy; the energy beyond is "
            "counted. Ignored by the raster."
        ),
    ),
    window: str | None = Query(
        None,
        description=(
            "shared | per_axis: the window rule. shared is one half-width for every axis of the "
            "event (the raster's default, the Event Inspector's); per_axis is one half-width per "
            "axis of each frame (the cubes' default, and the Models page's raster), each the axis's "
            "energy-weighted 0.1st–99.9th percentile range plus a cell, never below 150 mm."
        ),
    ),
):
    timer = Timer()
    if window is not None:
        event_inspector.check_window(window)
    if format == voxel_event.FORMAT_VOXELS:
        return _voxels(con, record, spec, timer, event_number, shower, coordinates, frame, channel,
                       model, cap, event_inspector.WINDOW_PER_AXIS if window is None else window)

    shower = "a" if shower is None else shower
    if shower not in event_inspector.SHOWERS:
        raise ValidationError(f"shower must be a or b; got {shower!r}.", field="shower")
    # One of the experiment's own showers: b is refused where there is one per event.
    showers_mod.of(record, shower)
    _check_coordinates(coordinates)
    footprint = canonical.cell_footprint(con, record)
    body = event_inspector.inspect(con, record, spec, event_number, shower, coordinates, footprint,
                                   window=event_inspector.WINDOW_SHARED if window is None else window)
    notices = [{"scope": "event", "text": body["coordinates"]["note"]},
               {"scope": "event", "text": body["window"]["rule"]},
               {"scope": "event", "text": body["scale"]["rule"]}]
    for note in body["grid"]["notes"]:
        notices.append({"scope": "event", "text": note})
    meta = ApiMeta(
        table_name=record.table_name, exact=True, query_ms=body.pop("elapsed_ms"),
        total_ms=timer.elapsed_ms, warnings=_outside(body, event_number),
        notes={"event": int(event_number), "shower": shower, "coordinates": coordinates,
               "notices": notices},
    )
    return envelope(meta, **body, filter=spec.as_dict())


def _check_coordinates(coordinates: str) -> None:
    if coordinates not in frame_sql.SOURCES:
        raise ValidationError(
            f"coordinates must be one of {', '.join(frame_sql.SOURCES)}; got {coordinates!r}.",
            field="coordinates",
        )


def _cap(cap: int | None) -> int:
    """The voxel cap: the default when absent, else an integer within the route's bounds."""
    if cap is None:
        return voxel_event.DEFAULT_CAP
    if not voxel_event.MIN_CAP <= cap <= voxel_event.MAX_CAP:
        raise ValidationError(typographic(
            f"cap must be an integer from {voxel_event.MIN_CAP} to {voxel_event.MAX_CAP:,}; "
            f"got {cap}."), field="cap")
    return cap


def _outside(body: dict[str, Any], event_number: int) -> list[str]:
    if body["event"]["in_selection"]:
        return []
    return [
        f"Event {event_number} lies outside the current selection; it is drawn as asked, and the "
        "previous / next controls walk the selection."
    ]


def _voxels(con, record: ExperimentRecord, spec, timer: Timer, event_number: int, shower: str | None,
            coordinates: str, frame: str, channel: str, model: str, cap: int | None,
            window: str = event_inspector.WINDOW_PER_AXIS) -> dict[str, Any]:
    """The cubes, built once and rendered until the whole enveloped body fits the contract.

    The guard's first lever on a splat frame is the voxel pitch (20 to 40 mm:
    every cell stays drawn); then the cap, lowered by as many of the faintest
    cubes as the overrun costs on the wire. Each step is a notice in the body
    it produced; at most four are taken.
    """
    shower = voxel_event.resolve(record, frame, shower, channel, model)
    _check_coordinates(coordinates)
    cap = _cap(cap)
    footprint = canonical.cell_footprint(con, record)
    builder = voxel_event.build(con, record, spec, event_number, frame, shower, channel, model,
                                coordinates, footprint, window=window)
    if builder.canonical is not None:
        # The D-frame's own sentence for an event whose entry anchors fix no rotation.
        notice = frame_canonical.ill_conditioned_event_notice(builder.canonical["d_entry_mm"])
        if notice:
            builder.build_notes.append(typographic(notice))
    cam = voxel_event.cam_note(builder)

    def render(state: tuple[int, float | None], steps: list[str]) -> dict[str, Any]:
        body = builder.assemble(state[0], state[1], requested=cap)
        voxels = body["voxels"]
        notices = [{"scope": "event", "text": text} for text in (
            body["coordinates"]["note"], body["window"]["rule"], voxels["scale"]["floor_rule"],
            *voxels["notes"])]
        notices += [{"scope": "budget", "text": text} for text in steps]
        meta = ApiMeta(
            table_name=record.table_name, exact=True, query_ms=body.pop("elapsed_ms"),
            total_ms=timer.elapsed_ms, warnings=_outside(body, event_number),
            notes={"event": int(event_number), "format": voxel_event.FORMAT_VOXELS,
                   "shower": shower, "frame": frame, "channel": channel,
                   "model": builder.network,
                   "coordinates": coordinates, "window": window, "cam": cam, "notices": notices},
        )
        return envelope(meta, **body, filter=spec.as_dict())

    def shrink(state: tuple[int, float | None], size: int, limit: int):
        drawn_cap, pitch = state
        if pitch is not None and pitch * 2.0 <= voxel_event.BUDGET_MAX_PITCH_MM:
            return drawn_cap, pitch * 2.0
        # Drop as many of the faintest cubes as the overrun costs, at the bytes a cube
        # takes on the wire, with 5% to spare: the rest of the body (event, notes, the
        # exact top values) does not shrink with the cap, so a proportional cut would
        # undershoot wherever it dominates.
        drawn = min(drawn_cap, builder.n_cubes(pitch))
        excess = size - voxel_event.BUDGET_TARGET * limit
        smaller = drawn - int(math.ceil(excess / builder.bytes_per_cube(pitch)))
        return (smaller, pitch) if 1 <= smaller < drawn else None

    def describe(old, new, size: int, limit: int) -> str:
        if new[1] != old[1]:
            return (f"The response measured {size:,} bytes against the {limit:,}-byte contract: the "
                    f"voxels were coarsened from {old[1]:.0f} mm to {new[1]:.0f} mm, every cell still "
                    "drawn.")
        drawn = min(old[0], builder.n_cubes(old[1]))
        return (f"The response measured {size:,} bytes against the {limit:,}-byte contract: the cap "
                f"was lowered from {drawn:,} to {new[0]:,} cubes by energy rank; the energy beyond "
                "it is counted in the cap block.")

    return budget.serve_measured(render, (int(cap), builder.first_pitch), shrink, describe,
                                 attempts=4, remedy="a smaller cap brings it under")


@router.get("/api/event/pick", summary="An event picked by a stated notebook rule")
def pick_event(
    con: CursorDep,
    record: InspectableDep,
    spec: FilterDep,
    seed: int = Query(42, ge=0, description="Seed of the random draw from the pool (tilted rule)."),
    pool_size: int = Query(20, ge=1, le=200, description="Size of the pool the rule ranks."),
    rule: str | None = Query(
        None,
        description=(
            "tilted (default): a seeded draw from the most tilted of the events with more hits than "
            "the mean (local-coords notebook, Page 1); densest: the event with the most cells, "
            "ties to the lowest number (High_energy notebook, Page 2's 3-D displays)."
        ),
    ),
):
    timer = Timer()
    body = event_inspector.pick(con, record, spec, seed=seed, pool_size=pool_size,
                                rule=event_inspector.RULE_TILTED if rule is None else rule)
    if rule is None:
        # A request that names no rule is answered as before rules existed: the
        # two-shower golden snapshot pins that body byte for byte.
        body.pop("rule_id")
        body.pop("seed_used")
    meta = ApiMeta(table_name=record.table_name, exact=True, total_ms=timer.elapsed_ms)
    return envelope(meta, **body, filter=spec.as_dict())
