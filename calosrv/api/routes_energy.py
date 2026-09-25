"""``GET /api/energy-distribution`` - the reconstructed-energy panel."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import ddl
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..stats import clip as clip_mod
from ..stats import histogram
from ..stats.slices import parse_edges
from ..query import density, energy
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

#: Coarser curve samplings the budget guard steps through, in order.
CURVE_POINT_STEPS = (150, 100, 75, 50)


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
    bins: int | None = Query(
        None, ge=8, le=500,
        description=(
            "Histogram bin count. Left unset, it adapts to the smallest slice "
            "above the histogram threshold, so no histogram is finer than its "
            "own statistics support."
        ),
    ),
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
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: which frame's segmentation network splits each "
            "event's energy between the showers. The panel is the segmentation "
            "reconstruction in every model view; D is always the laboratory separation."
        ),
    ),
):
    timer = Timer()
    if coord_system not in ddl.COORD_SYSTEMS:
        raise ValidationError(
            f"coord_system must be one of {', '.join(ddl.COORD_SYSTEMS)}; got {coord_system!r}.",
            field="coord_system",
        )
    edges = parse_edges(d_edges)

    def respond(curve_points: int, extra_warnings: list[str]) -> dict:
        result = energy.compute(
            con, record, spec,
            edges=edges,
            bins=bins,
            calibrated=calibrated,
            clip_low=clip_low,
            clip_high=clip_high,
            coord_system=coord_system,
            curve_points=curve_points,
        )

        warnings: list[str] = list(extra_warnings)
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

        # Low statistics are disclosed rather than suppressed. mu and sigma are
        # still reported for these slices; what is withheld is the histogram, and
        # below the curve floor the curve too, so the warning names which.
        labels = {s.index: s.label for s in result.slices}
        thin = sorted({
            labels.get(s.slice_index, str(s.slice_index))
            for s in result.series if s.draw != "histogram"
        })
        if thin:
            warnings.append(
                "Below the " + str(result.thresholds["histogram"]) + "-event "
                "histogram floor: " + "; ".join(thin) + ". mu and sigma there are "
                "plain sample moments (ddof = 1) rather than core refits, quoted "
                "with their standard errors; the density histogram is suppressed "
                "because at this sample size it is a comb of bin-width spikes, and "
                "these curves do not set the density axis."
            )
        degenerate = sorted({
            labels.get(s.slice_index, str(s.slice_index))
            for s in result.series if s.fit.degenerate
        })
        if degenerate:
            warnings.append(
                "All events share one energy to floating-point precision in: "
                + "; ".join(degenerate) + ". No width can be estimated there and "
                "no density curve is drawn."
            )

        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=warnings,
            # The one addition to this payload (plot 4 sits close to the budget):
            # which network produced the reconstruction.
            notes={"network": {"model": "segmentation", "frame": ddl.NETWORK_FRAME[coord_system]}},
        )
        return envelope(meta, **result.as_dict(), filter=spec.as_dict())

    # The panel grows with the slices: at the maximum of eight slices, each
    # with four fitted curves, the sampled curves alone measured 67 KB of a
    # 120 KB response on the production file. Measured as served and, while
    # over the contract, the curves are re-sampled more coarsely - exact
    # Gaussians at every point shipped, so nothing is approximated but the
    # polyline between them - and the step is disclosed.
    body = respond(histogram.CURVE_POINTS, [])
    first = size = density.wire_size(body)
    for points in CURVE_POINT_STEPS:
        if size < density.RESPONSE_LIMIT:
            break
        body = respond(points, [
            f"Density curves sampled at {points} points instead of {histogram.CURVE_POINTS} "
            f"to keep the response under the {density.RESPONSE_LIMIT:,}-byte contract "
            f"({first:,} bytes at {histogram.CURVE_POINTS}); every point is the exact fitted "
            "Gaussian."
        ])
        size = density.wire_size(body)
    return body
