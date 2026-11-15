"""``GET /api/resolution-scaling`` - the energy error scale against 1/√E with its fits (Page 2, ``res-scaling``).

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
toggle sends no request either. Each mode also carries the noise fit
σ/E = a/√E ⊕ b ⊕ c/E (``fits[mode].noise``, or ``noise_reason`` saying why there
is none; Martin's decisions, 2026-11-13): fitted with a², b², c² ≥ 0 to windows
from 1 GeV (``gates.noise_min_gev``), drawn by the E view from 0 GeV, and served
compact, with no curve, no unscaled errors, no note and no band (Martin's
directive, 2026-11-15). The E view draws one fitted curve per series with no
band round it: the noise fit, or a₀/√E from 4 GeV where the series has none. So
the noise block carries no all-free face and no ``band_quantile``: nothing reads
them. No fit block carries a note (FX3): the card read none, and its facts are
the block's fields.

``coord_system`` picks the energy network's input frame on two-shower data
(the D-frame's view asks for ``lab``, whose networks it uses); on the other
kinds it is validated and stated in ``meta`` as not applying.

``estimator`` picks the error scale every window plots (Martin's decisions,
2026-11-12): ``median`` (the default), the median relative error of Model
Error vs. Incident Momentum with its seed and interval; ``robust``, the
IQR-based σ/E; ``sample``, s(R)/R̄. Under median and robust the fits weight each
window by ``se = c·ŷ/√N`` with ``c`` the series' pooled scale (``weight_scale``
on every series), and the noise fit its windows of 1–4 GeV by the same ``c``,
which they do not enter (one pooled scale; Martin's directive, 2026-11-15). One
estimator per response: the card's
Estimator control sends one request per switch, because two estimators in one
body would break the 100 KB contract (about 55 KB more for two showers). An
estimator outside the three is a 422 naming the field ``estimator``, as an
unknown ``coord_system`` is one naming its own.
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
    summary=("Energy error scale (median rel., robust σ/E or sample σ/E) per momentum window "
             "against 1/√E, with WLS fits"),
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
    estimator: str = Query(
        res.DEFAULT_ESTIMATOR,
        description=(
            "median | robust | sample: the error scale each momentum window plots. median (the "
            "default) is median |R − 1|, for a model series the Median rel. of Model Error vs. "
            "Incident Momentum with its seed and interval; robust is σ/E = IQR(R) / (1.349 · "
            "median R) from N = 20 with an exact bootstrap interval; sample is s(R)/R̄ with its "
            "χ² interval. R = E_est / p per event. Any other value is a 422."
        ),
    ),
):
    timer = Timer()
    capabilities.require(record, "res-scaling")
    result = res.compute(con, record, spec, coord_system, estimator)
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
    # The estimators' window fields (method, se, se_rel, alt, median response, tail share) add
    # about 140 bytes a window, and the estimator block and its notes 2–5 KB; each series' pooled
    # weight scale about 300 bytes. That fixture serves 63,197 bytes under median (its tied
    # deposits carry no fit), 76,075 under robust and 68,591 under sample (2026-11-12, after F1–F8).
    # The noise fit adds 596–628 bytes per fitted mode and series, and its two notes about 560:
    # 66,846 under median, 81,712 under robust and 74,210 under sample (2026-11-13). The fix round
    # took the fit and noise notes, the noise definition note and three quadrature fields off the
    # wire and added the all-free face (152–182 bytes) where a noise fit holds a term: 62,869 under
    # median, 74,807 under robust and 68,268 under sample, each noise block 606–674 bytes
    # (2026-11-13, at 7d41c68 + the fix round; the trim of d50d7f6 had already taken 65,683,
    # 79,382 and 72,890). The single-curve round took the all-free face, the noise block's
    # band_quantile and the second scale's c_low and n_low back off the wire and shortened the
    # weight label, the scale rules and the E view's two notes: 61,884 under median, 72,601 under
    # robust and 66,918 under sample, each noise block 415–460 bytes (2026-11-15, at 711fcf3 +
    # SC-backend; 63,044, 74,982 and 68,268 at 711fcf3).
    return budget.serve_measured(build, steps[0], shrink, _describe,
                                 remedy="a narrower momentum selection brings it under")
