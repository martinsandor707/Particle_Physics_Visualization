"""``GET /api/selection-cells`` - the selection's detector cells in 3-D (Page 2, Absolute frame).

The Models page's 3-D cells card draws the whole current selection in the
laboratory frame by default (Martin's directive of 2026-10-31), one event
becoming an option of the card. This route serves it: every hit of the
selection, both showers, summed into its detector cell, coloured by the
mean energy per selected event or by a network's energy-weighted Grad-CAM or
Shap-CAM (``query/voxel_selection.py`` argues each choice). The body is the
one-event cubes' (``/api/event?format=voxels&frame=lab&shower=both``) with a
``selection`` block in place of ``event``, so the browser decodes both alike.

**Parameters.** The shared filters; ``channel`` energy (default), gradcam or
shapcam; ``model``, read only by the network channels; ``cap`` 100..15 000
(default 15 000, ranked by energy); ``window`` per_axis (default) or shared,
the event route's rule. There is no ``frame`` - always the laboratory frame -
and no ``shower``: always every hit.

**Refused before any scan.** An experiment without hits or a lattice, under
the ``vox-event`` gate, before the filter is read (an aggregated experiment
is refused as such, not for a selection it could never have made). The
segmentation error and the species, naming ``channel``: they are per-event
quantities with no selection projection. A network channel without the
networks' columns, naming ``channel`` and ``vox-attention``, exactly as the
event route refuses it. An unknown value is the plain validation error
naming its parameter; a cap outside its bounds names ``cap``.

**Budget.** The whole enveloped body is measured as served
(``api/budget.serve_measured``). While it is over the 100 000-byte contract
the cap is lowered by as many of the faintest cubes as the overrun costs on
the wire, each step said in a notice; if even one cube does not fit, the body
is served whole with the stated overrun. A large selection's 15 000 cubes cost
about as much as the contract on their own, so the guard's step is expected
there, and says so.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import canonical, event_inspector, voxel_event, voxel_selection
from ..text import typographic
from . import budget
from .deps import CursorDep, FilterDep, capable

router = APIRouter()

#: The experiment, refused before the filter unless it can serve the 3-D cells (hits and the lattice).
CellsRecordDep = Annotated[ExperimentRecord, capable("vox-event")]


def _cap(cap: int) -> int:
    """The cube cap, refused naming ``cap`` outside the route's bounds."""
    if not voxel_selection.MIN_CAP <= cap <= voxel_selection.MAX_CAP:
        raise ValidationError(typographic(
            f"cap must be an integer from {voxel_selection.MIN_CAP} to {voxel_selection.MAX_CAP:,}; "
            f"got {cap}."), field="cap")
    return cap


@router.get("/api/selection-cells",
            summary="The selection's detector cells as 3-D cubes, both showers summed")
def get_selection_cells(
    con: CursorDep,
    record: CellsRecordDep,
    spec: FilterDep,
    channel: str = Query(
        voxel_event.CHANNEL_ENERGY,
        description=(
            "energy (default): the mean energy per selected event in each cell, as volumetric density "
            "in GeV/mm^3 per event on a log ramp. gradcam | shapcam (signed): the chosen network's "
            "energy-weighted mean over the selection's hits in the cell, on the one-event linear "
            "ramps; they need the networks' columns. segerr and species are per-event quantities and "
            "are refused."
        ),
    ),
    model: str = Query(
        "segmentation",
        description="angle | energy | segmentation: the network a CAM channel reads (lab-frame columns).",
    ),
    cap: int = Query(
        voxel_selection.DEFAULT_CAP,
        description=(
            f"An integer {voxel_selection.MIN_CAP}..{voxel_selection.MAX_CAP} (default "
            f"{voxel_selection.DEFAULT_CAP}): most cubes drawn, ranked by energy; the energy beyond "
            "is counted."
        ),
    ),
    window: str = Query(
        event_inspector.WINDOW_PER_AXIS,
        description=(
            "per_axis (default) | shared: the window rule of /api/event on the selection's cells, "
            "each axis's energy-weighted 0.1st–99.9th percentile range plus a cell, never below 150 mm."
        ),
    ),
):
    timer = Timer()
    event_inspector.check_window(window)
    voxel_selection.resolve(record, channel, model)
    cap = _cap(cap)
    footprint = canonical.cell_footprint(con, record)
    sums, was_cached = voxel_selection.cells_for(con, record, spec, channel, model)
    builder = voxel_selection.build(record, sums, channel, model, window, footprint)
    cam = voxel_selection.cam_note(channel, model)

    def render(drawn_cap: int, steps: list[str]) -> dict[str, Any]:
        body = builder.assemble(drawn_cap, None, requested=cap)
        body.pop("elapsed_ms")
        selection, voxels = body["selection"], body["voxels"]
        notices = [{"scope": "selection", "text": text} for text in (
            selection["quantity"], selection["aggregation"], body["coordinates"]["note"],
            body["window"]["rule"], voxels["scale"]["floor_rule"], *voxels["notes"])]
        if cam is not None:
            notices.append({"scope": "channel", "text": cam["note"]})
        notices += [{"scope": "budget", "text": text} for text in steps]
        meta = ApiMeta(
            table_name=record.table_name, exact=True, query_ms=sums.query_ms,
            total_ms=timer.elapsed_ms, cached=was_cached, warnings=[],
            notes={"format": voxel_event.FORMAT_VOXELS, "frame": voxel_event.FRAME_LAB,
                   "shower": builder.shower, "channel": channel, "model": builder.network,
                   "window": window, "cam": cam, "notices": notices},
        )
        return envelope(meta, **body, filter=spec.as_dict())

    def shrink(drawn_cap: int, size: int, limit: int) -> int | None:
        # Drop as many of the faintest cubes as the overrun costs, at the bytes a cube takes
        # on the wire, with 5% to spare: the rest of the body does not shrink with the cap.
        drawn = min(drawn_cap, builder.n_cubes(None))
        excess = size - voxel_event.BUDGET_TARGET * limit
        smaller = drawn - int(math.ceil(excess / builder.bytes_per_cube(None)))
        return smaller if 1 <= smaller < drawn else None

    def describe(old: int, new: int, size: int, limit: int) -> str:
        drawn = min(old, builder.n_cubes(None))
        return (f"The response measured {size:,} bytes against the {limit:,}-byte contract: the cap "
                f"was lowered from {drawn:,} to {new:,} cubes by energy rank; the energy beyond it is "
                "counted in the cap block.")

    return budget.serve_measured(render, int(cap), shrink, describe, attempts=4,
                                 remedy="a smaller cap or a narrower selection brings it under")
