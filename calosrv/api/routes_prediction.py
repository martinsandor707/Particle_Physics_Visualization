"""``GET /api/prediction-density`` - prediction against truth and its residuals (Page 2).

The pred-truth and pred-residuals cards: for the energy or angle network of one
input frame, a density of (truth, prediction) pairs per shower on dataset-wide
axes, the identity line, and the residual distribution beneath it
(``query/prediction_density.py``). An experiment without reconstruction
networks is refused by its capability gates; the segmentation network is
refused by name, because its per-hit fractions have no per-shower prediction
to plot - its reconstruction is the energy panel.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..db import ddl
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import density, prediction_density
from .deps import CursorDep, FilterDep, capable

router = APIRouter()

SEGMENTATION_REFUSAL = (
    "segmentation predicts per-hit energy fractions, not a value per shower, so there is no "
    "prediction to plot against truth; its reconstruction is the energy panel "
    "(GET /api/energy-distribution). Choose model=energy or model=angle."
)


@router.get(
    "/api/prediction-density",
    summary="Predicted against true energy or angle, per shower, with the residuals",
)
def get_prediction_density(
    con: CursorDep,
    record: Annotated[ExperimentRecord, capable("pred-truth", "pred-residuals", field="model")],
    spec: FilterDep,
    model: str = Query(
        "energy",
        description="energy | angle: whose per-shower prediction is plotted against its truth.",
    ),
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: the input frame the network was trained on - lab the "
            "absolute (detector) frame, trans the per-shower translated frame (legacy), "
            "local the Separation-Aligned (D-Frame), Local (shower-fixed) frame."
        ),
    ),
    bins: int = Query(
        64, ge=16, le=128,
        description=(
            "Bins per axis of the density. Lowered, with a notice, when the response would "
            "exceed the 100 KB contract; the axis range does not change."
        ),
    ),
):
    timer = Timer()
    if model == "segmentation":
        raise ValidationError(SEGMENTATION_REFUSAL, field="model")
    for name, value, allowed in (("model", model, prediction_density.MODELS),
                                 ("coord_system", coord_system, ddl.COORD_SYSTEMS)):
        if value not in allowed:
            raise ValidationError(
                f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name,
            )

    selection = prediction_density.read(con, record, spec, model, coord_system)
    residual = prediction_density.residual_block(selection)

    def respond(granted: int, disclosed: list[str]) -> dict:
        payload = prediction_density.assemble(selection, residual, granted)
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=[*prediction_density.notices(selection, payload), *disclosed],
            notes={"model": model, "coord_system": coord_system},
        )
        return envelope(meta, **payload, filter=spec.as_dict())

    # Two dense rasters are about 20 KB at 64 bins and 70 KB at 128, so the guard is
    # for the fine end of the range. It steps the bin count down, keeping the
    # dataset-wide range, and says so; a body still over the contract at the
    # coarsest step is served as it is, with that said too.
    body = respond(bins, [])
    first = size = density.wire_size(body)
    granted = bins
    disclosed: list[str] = []
    while size >= density.RESPONSE_LIMIT:
        smaller = prediction_density.next_bins(granted)
        if smaller is None:
            break
        granted = smaller
        disclosed = [
            f"The density is drawn on {granted} bins per axis instead of {bins} to keep the "
            f"response under the {density.RESPONSE_LIMIT:,}-byte contract ({first:,} bytes at "
            f"{bins}); the axis range and every count are unchanged in meaning."
        ]
        body = respond(granted, disclosed)
        size = density.wire_size(body)
    if size >= density.RESPONSE_LIMIT:
        disclosed.append(
            f"Served as it is: {size:,} bytes against the {density.RESPONSE_LIMIT:,}-byte "
            f"contract at the coarsest {granted} bins per axis.")
        body = respond(granted, disclosed)
    return body
