"""``GET /api/model-performance`` - the sidebar KPI card."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models.common import ApiMeta, Timer, envelope
from ..stats.slices import parse_edges
from ..query import performance
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

#: Contextual captions for the model selector. The three architectures are read
#: from the same stored inference columns, so the selector changes which metrics
#: are foregrounded and how they are described - it does not change the data.
MODEL_CAPTIONS = {
    "segmentation": {
        "title": "Segmentation Model",
        "caption": (
            "Per-voxel assignment of deposited energy between the two "
            "overlapping showers, read from voxel_fA_pred against "
            "voxel_fA_true. The headline figure is the energy-weighted mean "
            "absolute error: the fraction of deposited energy assigned to the "
            "wrong shower."
        ),
        "primary": ["classification.accuracy", "regression.mae_energy_weighted"],
    },
    "energy": {
        "title": "Energy Estimation Model",
        "caption": (
            "Reconstructed shower energies, formed by summing deposited energy "
            "under the predicted voxel fractions and calibrating to the "
            "incident momentum scale. The headline figure is the relative "
            "energy resolution."
        ),
        "primary": ["energy_residuals.a.relative_resolution",
                    "energy_residuals.a.relative_bias"],
    },
    "angle": {
        "title": "Incident Angle Estimation Model",
        "caption": (
            "Incident direction reconstruction. This dataset stores the true "
            "incoming_theta and incoming_phi but carries no predicted angle "
            "column, so no angular residual can be computed. Segmentation "
            "metrics are shown as the available baseline."
        ),
        "primary": [],
        "unavailable": (
            "No predicted-angle column exists in the 29-column inference "
            "schema. Angular residuals cannot be derived from ground truth "
            "alone and are not fabricated."
        ),
    },
}


@router.get("/api/model-performance", summary="Voxel and energy reconstruction metrics")
def get_model_performance(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    model: str = Query(
        "segmentation",
        description="segmentation | energy | angle - selects contextual framing.",
    ),
    d_edges: str | None = Query(
        None, description="Separation-distance slice edges for the breakdown."
    ),
):
    timer = Timer()
    report = performance.compute(con, record, spec, edges=parse_edges(d_edges))

    context = MODEL_CAPTIONS.get(model, MODEL_CAPTIONS["segmentation"])
    warnings: list[str] = []
    if "unavailable" in context:
        warnings.append(context["unavailable"])
    if report.n_events == 0:
        warnings.append("No events match the current selection.")

    meta = ApiMeta(
        table_name=record.table_name,
        exact=True,
        total_ms=timer.elapsed_ms,
        warnings=warnings,
        notes={"model": model},
    )
    return envelope(
        meta,
        **report.as_dict(),
        model=context,
        filter=spec.as_dict(),
    )
