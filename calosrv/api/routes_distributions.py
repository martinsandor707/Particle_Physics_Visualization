"""``GET /api/distributions`` - the per-momentum-bin distributions, C4 (Page 1).

One quantity per response - u, v, w, hit energy, θ, φ or p - as one histogram
per 1 GeV bin of each shower's own incident momentum, on one shared binning.
θ, φ and p come from the event table of every kind
(``query/shower_distributions.py``); u, v, w and hit energy scan the hits and
are refused, naming ``quantity``, on an experiment that has none
(``query/hit_distributions.py``).

**Payload guard.** A response stays under the 100 KB contract by coarsening
the display bins two, then four at a time - u, v, w and energy merge whole bins,
θ, φ and p are re-binned over the same window, so every count is conserved
either way - each step disclosed; a response still over at the last step is
served as it is with a notice saying so, never silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import density, hit_distributions, shower_distributions
from ..query.shower_distributions import (
    COARSEN_STEPS, DEFAULT_CLIP, HIT_QUANTITIES, QUANTITY_KEYS, SHOWER_QUANTITIES, WEIGHT_HIT,
    WEIGHT_SHOWER, WEIGHTINGS, Prepared,
)
from ..query.showers import SHOWER_CHOICES
from ..text import typographic
from .deps import CursorDep, FilterDep, SettingsDep, capable

router = APIRouter()


def _check(quantity: str, weighting: str | None, shower: str, clip_low: float,
           clip_high: float) -> str:
    """Validate the request's own parameters; return the effective weighting."""
    if quantity not in QUANTITY_KEYS:
        raise ValidationError(
            f"quantity must be one of {', '.join(QUANTITY_KEYS)}; got {quantity!r}.",
            field="quantity")
    if weighting is not None and weighting not in WEIGHTINGS:
        raise ValidationError(
            f"weighting must be one of {', '.join(WEIGHTINGS)}; got {weighting!r}.",
            field="weighting")
    if quantity in HIT_QUANTITIES and weighting == WEIGHT_SHOWER:
        raise ValidationError(
            f"quantity={quantity!r} is a property of hits and is counted per hit; "
            "weighting=shower applies to theta, phi and p only.", field="weighting")
    if shower not in SHOWER_CHOICES:
        raise ValidationError(
            f"shower must be one of {', '.join(SHOWER_CHOICES)}; got {shower!r}.",
            field="shower")
    if not 0.0 <= clip_low < 100.0 or not clip_low < clip_high <= 100.0:
        raise ValidationError(typographic(
            f"The display percentiles must satisfy 0 ≤ clip_low < clip_high ≤ 100; got "
            f"clip_low={clip_low:g}, clip_high={clip_high:g}."),
            field="clip_low" if not 0.0 <= clip_low < 100.0 else "clip_high")
    if quantity in HIT_QUANTITIES:
        return WEIGHT_HIT
    return weighting or WEIGHT_SHOWER


def _guarded(prepared: Prepared, make_meta: Callable[[list[str]], ApiMeta],
             extra: dict[str, Any]) -> dict[str, Any]:
    """The smallest coarsening whose response fits ``density.RESPONSE_LIMIT``, disclosed."""
    limit = density.RESPONSE_LIMIT
    payload: dict[str, Any] = {}
    size = 0
    for coarsen in COARSEN_STEPS:
        warnings = list(prepared.warnings)
        if coarsen > 1:
            warnings.append(
                f"Display bins coarsened {coarsen} at a time over the same window (u, v, w and "
                "hit energy merge whole adjacent bins; θ, φ and p are re-binned, so their edges "
                f"need not nest; every count conserved) to keep the response under {limit:,} "
                "bytes.")
        payload = envelope(make_meta(warnings), **prepared.render(coarsen), **extra)
        size = density.wire_size(payload)
        if size < limit:
            return payload
    payload["meta"]["warnings"].append(
        f"The response is still {size:,} bytes with display bins coarsened {COARSEN_STEPS[-1]} at "
        f"a time, over the {limit:,}-byte budget; it is served as it is.")
    return payload


@router.get("/api/distributions",
            summary="Per-momentum-bin distributions of u, v, w, hit energy, θ, φ and p (C4)")
def get_distributions(
    con: CursorDep,
    record: Annotated[ExperimentRecord, capable("distribution")],
    spec: FilterDep,
    settings: SettingsDep,
    quantity: str = Query(
        "theta",
        description=("u | v | w: Local-frame hit coordinates as footprint-splatted hit counts; "
                     "energy: hit energy on log-spaced bins; theta | phi | p: the showers' "
                     "incident kinematics. u, v, w and energy need hits.")),
    weighting: str | None = Query(
        None,
        description=("theta, phi, p: shower (default; each shower once) or hit (each shower "
                     "weighted by its hit count, the reference notebook's hit sample computed "
                     "exactly). The hit quantities are always counted per hit.")),
    shower: str = Query("both", description="a | b | both (two-shower); a | both (single shower)."),
    clip_low: float = Query(DEFAULT_CLIP[0], description="Lower percentile of the display window."),
    clip_high: float = Query(DEFAULT_CLIP[1],
                             description="Upper percentile of the display window."),
    preview: bool = Query(
        False,
        description=("Serve the hit quantities from the sampled companion table while a slider "
                     "is dragged; the counts are scaled estimates, marked exact: false.")),
):
    timer = Timer()
    weighting = _check(quantity, weighting, shower, clip_low, clip_high)
    if quantity in SHOWER_QUANTITIES:
        prepared = shower_distributions.prepare(
            con, record, spec, quantity=quantity, weighting=weighting, shower=shower,
            low=clip_low, high=clip_high)
    else:
        prepared = hit_distributions.prepare(
            con, record, spec, settings, quantity=quantity, shower=shower, low=clip_low,
            high=clip_high, preview=preview)

    def make_meta(warnings: list[str]) -> ApiMeta:
        return ApiMeta(
            table_name=record.table_name, exact=prepared.exact, query_ms=prepared.query_ms,
            total_ms=timer.elapsed_ms, cached=prepared.cached, warnings=warnings,
            notes={"quantity": quantity},
        )

    extra = {"kind": record.kind, "shower": shower, "filter": spec.as_dict()}
    return _guarded(prepared, make_meta, extra)
