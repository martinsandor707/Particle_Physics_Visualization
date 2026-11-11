"""``GET /api/resolution-scaling`` - σ/E against 1/√E with its fits (Page 2, ``res-scaling``).

One request serves the whole card: every series the experiment carries (the
detector's calibrated deposit per shower, and the energy network or the
XGBoost momentum regressor where there is one), both window modes (the three
anchors and every eligible window) and each mode's three fits. The shower and
the window mode are switched in the browser, with no request
(``query/resolution_scaling.py``).

The same response serves both of the card's views: the 1/√E view and the E
view, σ/E against E in GeV with its ratio panel. The E view draws the same
windows at E = 1/x², its curves from the fits' parameters, and reads its own
axes from ``axis.energy`` and each mode's fitted ``span_gev``, so the view
toggle sends no request either.

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

    # 56,388 bytes for two showers with a network (the recorded fixture, measured on
    # 2026-11-10: four series over 16 windows, each series' fits about 6 KB, the notes about
    # 5 KB, the E view's axis, spans and quadrature ρ and quantiles 1.6 KB) and about 62 KB at
    # 20 windows; the ladder guards a dataset with many more windows than the producers write.
    return budget.serve_measured(build, steps[0], shrink, _describe,
                                 remedy="a narrower momentum selection brings it under")
