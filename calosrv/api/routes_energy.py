"""``GET /api/energy-distribution`` - the reconstructed-energy panel."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models.common import ApiMeta, Timer, envelope
from ..stats import clip as clip_mod
from ..stats import histogram
from ..stats.slices import parse_edges
from ..query import energy
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


@router.get(
    "/api/energy-distribution",
    summary="Reconstructed energy distributions across separation-distance slices",
)
def get_energy_distribution(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    d_edges: str | None = Query(
        None,
        description=(
            "Comma-separated separation-distance slice edges in mm. Defaults to "
            "50,100,150,200; an overflow slice for the well-separated "
            "population is always appended."
        ),
    ),
    bins: int = Query(histogram.DEFAULT_BINS, ge=10, le=500),
    calibrated: bool = Query(
        True,
        description=(
            "Apply the per-shower sampling-fraction calibration so energies are "
            "on the incident-momentum scale. With this off, the raw deposited "
            "sums are returned and are NOT comparable with the E1/E2 benchmarks."
        ),
    ),
    clip_low: float = Query(
        clip_mod.DEFAULT_LOW_PERCENTILE, ge=0.0, le=49.0,
        description="Lower percentile bounding the displayed energy axis.",
    ),
    clip_high: float = Query(
        clip_mod.DEFAULT_HIGH_PERCENTILE, ge=51.0, le=100.0,
        description="Upper percentile bounding the displayed energy axis.",
    ),
):
    timer = Timer()
    result = energy.compute(
        con, record, spec,
        edges=parse_edges(d_edges),
        bins=bins,
        calibrated=calibrated,
        clip_low=clip_low,
        clip_high=clip_high,
    )

    warnings: list[str] = []
    clipping = result.axis["clipping"]
    if clipping.get("applied") and clipping.get("n_outside"):
        warnings.append(clipping["note"])
    if not result.calibration["applied"]:
        warnings.append(
            "Energies are raw deposited sums, not calibrated to the incident "
            "momentum scale; the isolated-reference benchmarks are hidden "
            "because they would not be comparable."
        )
    empty = [
        s.label for s in result.slices if result.slice_counts.get(s.index, 0) == 0
    ]
    if empty:
        warnings.append(
            "No events in this selection fall in: " + "; ".join(empty) + "."
        )

    meta = ApiMeta(
        table_name=record.table_name,
        exact=True,
        total_ms=timer.elapsed_ms,
        warnings=warnings,
    )
    return envelope(meta, **result.as_dict(), filter=spec.as_dict())
