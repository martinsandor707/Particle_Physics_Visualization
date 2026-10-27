"""``GET /api/prediction-density`` - prediction against truth and its residuals (Page 2).

The pred-truth and pred-residuals cards: for the energy or angle network of one
input frame, a density of (truth, prediction) pairs per shower on dataset-wide
axes, the identity line, and the residual distribution beneath it
(``query/prediction_density.py``). An experiment without reconstruction
networks is refused by its capability gates; the segmentation network is
refused by name, because its per-hit fractions have no per-shower prediction
to plot - its reconstruction is the energy panel.

On an aggregate experiment whose XGBoost analysis is done, the same payload
draws the shipped regressor on the notebook's 20 % validation split within the
selection (``prediction_density.read_xgb``): one shower, ``network.frame`` and
``source`` ``xgb``, and for the angle task ``label=theta`` (the default) or
``label=phi``, whose residual is wrapped to (−π, π]. The networks predict θ
only, so ``label=phi`` is refused on two-shower data and ``label=theta`` is
what they always draw.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import ddl
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import capabilities, density, performance_bins, prediction_density
from .deps import CursorDep, FilterDep, RecordDep

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
    record: RecordDep,
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
    label: str | None = Query(
        None,
        description=(
            "theta | phi: the angle task's output. The networks predict θ only; the XGBoost "
            "angle regressor of an aggregate experiment predicts both (θ by default)."
        ),
    ),
):
    timer = Timer()
    xgboost = record.kind == ddl.KIND_SINGLE_EVENTS
    if xgboost:
        # An aggregate experiment: the XGBoost series, refused while it is not analysed.
        performance_bins.require_xgb(record)
    else:
        # No networks: the same refusal as E2, naming the capability that is missing.
        performance_bins.require_networks(record)
    capabilities.require(record, "pred-truth", "pred-residuals", field="model")
    if model == "segmentation":
        raise ValidationError(SEGMENTATION_REFUSAL, field="model")
    for name, value, allowed in (("model", model, prediction_density.MODELS),
                                 ("coord_system", coord_system, ddl.COORD_SYSTEMS)):
        if value not in allowed:
            raise ValidationError(
                f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name,
            )
    if label is not None:
        offered = prediction_density.XGB_LABELS[model] if xgboost else (
            ("theta",) if model == "angle" else ())
        if label not in offered:
            what = (f"the {model} task predicts {', '.join(offered)}" if offered
                    else f"model={model} has a single output")
            if not xgboost and model == "angle":
                what = "the angle networks predict the polar angle θ only (label=theta)"
            raise ValidationError(f"label={label!r} is not available: {what}.", field="label")

    if xgboost:
        selection = prediction_density.read_xgb(con, record, spec, model, label)
    else:
        selection = prediction_density.read(con, record, spec, model, coord_system)
    residual = prediction_density.residual_block(selection)
    notes = {"model": model, "coord_system": coord_system}
    if xgboost:
        notes.update(source=prediction_density.XGB_CODE, label=selection.label)
    elif label is not None:
        notes["label"] = label

    def respond(granted: int, disclosed: list[str]) -> dict:
        payload = prediction_density.assemble(selection, residual, granted)
        warnings = [*prediction_density.notices(selection, payload), *disclosed]
        if xgboost and not selection.split.get("reproduced", True):
            warnings.append(selection.run["split"]["warning"])
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=warnings,
            notes=notes,
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
