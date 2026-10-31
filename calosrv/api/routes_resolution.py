"""``GET /api/resolution-scaling`` - σ/E against 1/√E with its fits (Page 2, ``res-scaling``).

One request serves the whole card: every series the experiment carries (the
detector's calibrated deposit per shower, and the energy network or the
XGBoost momentum regressor where there is one), both window modes (the three
anchors and every eligible window) and each mode's three fits. The shower and
the window mode are switched in the browser, with no request
(``query/resolution_scaling.py``).

``coord_system`` picks the energy network's input frame on two-shower data
(the D-frame's view asks for ``lab``, whose networks it uses); on the other
kinds it is validated and stated in ``meta`` as not applying.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..models.common import ApiMeta, Timer, envelope
from ..query import capabilities
from ..query import resolution_scaling as res
from . import budget
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


def _describe(old: tuple[int, int], new: tuple[int, int], size: int, limit: int) -> str:
    what = (f"numbers are written at {new[0]} significant figures"
            if new[0] != old[0] else
            f"each fit's line and band are written at {new[1]} points instead of {old[1]}")
    return (f"The response was {size:,} bytes, over the {limit:,}-byte contract, so {what}; "
            "no statistic changed.")


@router.get(
    "/api/resolution-scaling",
    summary="Energy resolution σ/E per momentum window against 1/√E, with WLS fits",
)
def get_resolution_scaling(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: the input frame of the energy network drawn on two-shower "
            "data - lab the absolute (detector) frame, trans the per-shower translated frame "
            "(legacy), local the Local (shower-fixed) frame. The Separation-Aligned (D-Frame), "
            "Translated view uses the lab networks. Validated on every kind; it applies to "
            "two-shower data only."
        ),
    ),
):
    timer = Timer()
    capabilities.require(record, "res-scaling")
    result = res.compute(con, record, spec, coord_system)
    steps = res.FIDELITY_STEPS

    def build(step: tuple[int, int], notices: list[str]) -> dict[str, Any]:
        digits, band_points = step
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=[*result.warnings(), *notices],
            notes=result.meta_notes(),
        )
        return envelope(meta, **result.as_dict(digits=digits, band_points=band_points),
                        filter=spec.as_dict())

    def shrink(step: tuple[int, int], size: int, limit: int) -> tuple[int, int] | None:
        at = steps.index(step)
        return steps[at + 1] if at + 1 < len(steps) else None

    # About 15-30 KB for two showers and two series each; the ladder guards a dataset
    # with many more windows than the producers write.
    return budget.serve_measured(build, steps[0], shrink, _describe,
                                 remedy="a narrower momentum selection brings it under")
