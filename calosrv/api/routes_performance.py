"""``GET /api/model-performance`` - the sidebar metric cards of one network."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import ddl
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import performance
from ..stats.slices import parse_edges
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

FRAME_WORDS = {"absolute": "laboratory (absolute)", "trans": "translated", "local": "local"}

#: Titles and captions per task. ``{frame}`` is the input frame of the network.
MODEL_CAPTIONS = {
    "segmentation": {
        "title": "Segmentation Model",
        "caption": (
            "The {frame}-frame segmentation network assigns each hit's energy between the "
            "two showers, read from segmentation_{column}_pred against its truth "
            "E_A / E_voxel, which is fractional wherever both showers deposit in one cell. "
            "Classification uses the ≥ 0.5 majority on both sides; a cell shared by both "
            "showers is two rows, so unweighted counts see it twice. The headline is the "
            "energy-weighted MAE, exact over the selection: the fraction of deposited "
            "energy assigned to the wrong shower."
        ),
        "primary": ["accuracy", "wmae"],
    },
    "energy": {
        "title": "Energy Estimation Model",
        "caption": (
            "The {frame}-frame energy network's per-shower estimate (energy_{column}_pred) "
            "against the incident momentum, with no sampling-fraction calibration applied: "
            "the network predicts the momentum scale directly. The headline is the "
            "relative resolution σ of (pred − true) / true per shower."
        ),
        "primary": ["sigma_rel_a", "sigma_rel_b"],
    },
    "angle": {
        "title": "Incident Angle Estimation Model",
        "caption": (
            "The {frame}-frame angle network predicts each shower's polar angle θ "
            "(angle_{column}_pred) against the incident θ; the azimuth φ is not predicted. "
            "θ does not wrap, so its mean residual is a meaningful bias. The headline is "
            "the θ resolution per shower, in mrad."
        ),
        "primary": ["sigma_theta_a", "sigma_theta_b"],
    },
}


def _context(model: str, coord_system: str) -> dict:
    frame = ddl.NETWORK_FRAME[coord_system]
    base = MODEL_CAPTIONS[model]
    return {
        **base,
        "caption": base["caption"].format(frame=FRAME_WORDS[frame], column=frame),
        "network": {"model": model, "frame": frame},
    }


@router.get("/api/model-performance", summary="Metric cards of one network")
def get_model_performance(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    model: str = Query(
        "segmentation",
        description="segmentation | energy | angle: which task's network is evaluated.",
    ),
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: the input frame the network was trained on. The "
            "canonical view uses the absolute-frame (lab) networks."
        ),
    ),
    d_edges: str | None = Query(
        None, description="Separation-distance slice edges for the breakdown."
    ),
):
    timer = Timer()
    for name, value, allowed in (("model", model, ddl.MODELS),
                                 ("coord_system", coord_system, ddl.COORD_SYSTEMS)):
        if value not in allowed:
            raise ValidationError(
                f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name,
            )
    report = performance.compute(
        con, record, spec, model=model, coord_system=coord_system, edges=parse_edges(d_edges),
    )

    warnings: list[str] = []
    if report.n_events == 0:
        warnings.append("No events match the current selection.")

    meta = ApiMeta(
        table_name=record.table_name,
        exact=True,
        total_ms=timer.elapsed_ms,
        warnings=warnings,
        notes={"model": model, "coord_system": coord_system},
    )
    return envelope(
        meta,
        **report.as_dict(),
        model=_context(model, coord_system),
        filter=spec.as_dict(),
    )
