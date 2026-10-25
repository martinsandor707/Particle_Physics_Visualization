"""``GET /api/features`` - the event-feature explorer, D2-D5 (Page 2).

One route, five views of one cached bundle: ``catalog`` (the features, their
flags and the class sizes), ``describe`` (D2), ``corr`` (D3), ``hist`` (D4)
and ``hist2d`` (D5). Each view is its card's gate - ``feat-table``,
``feat-corr``, ``feat-hist``, ``feat-hist2d`` - so a two-shower experiment
built before the per-event feature sums existed is refused with the rebuild
sentence instead of failing in SQL.

Every response is measured on the wire against the 100 KB contract, its own
``meta.budget`` and any warning included; a view that could exceed it sheds
resolution in stated steps (curve points, then bins; the describe intervals)
and says which it took.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query

from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import capabilities, density, hit_sql, showers
from ..query import features as features_mod
from ..query import feature_corr, feature_describe, feature_hist
from ..query import features_catalog as catalog
from ..text import typographic
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

VIEWS: tuple[str, ...] = ("catalog", "describe", "corr", "hist", "hist2d")

#: The card each view serves, which is its capability gate.
VIEW_GATES: dict[str, str] = {
    "catalog": "feat-table", "describe": "feat-table", "corr": "feat-corr",
    "hist": "feat-hist", "hist2d": "feat-hist2d",
}

#: Whether floored events are left out by default. Only the correlations
#: leave them out: there the floored volumes (up to 2 × 10⁹ hits/mm³ against a
#: median of 2 × 10⁻⁷) would by themselves set every r involving a density.
#: The others show every event and count the floored ones; the histograms take
#: their range and automatic scale from the measured values only, so the floors
#: are a counted underflow rather than the end of the axis.
EXCLUDE_EPS_DEFAULT: dict[str, bool] = {
    "catalog": False, "describe": False, "corr": True, "hist": False, "hist2d": False,
}

SCALES: tuple[str, ...] = ("auto", "linear", "log")

#: Shrink steps of the histogram views: (curve points, bin divisor) and bins per axis.
HIST_LEVELS: tuple[tuple[int, int], ...] = ((160, 1), (80, 1), (80, 2), (80, 4))
HIST2D_LEVELS: tuple[int, ...] = (48, 32, 24, 16, 12)

_CLASS_SETS = {
    "windows": "The features notebook's momentum windows (1, 2, 5, 10, 19.5) ± 0.5 GeV.",
    "bins": "The producer's 1 GeV momentum bins (its integer bin column).",
    "label": "The binary label p < 2 GeV against p ≥ 2 GeV.",
}


def _choice(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValidationError(f"{name} must be one of {', '.join(allowed)}; got {value!r}.",
                              field=name)


def _pitch(record: ExperimentRecord) -> float | None:
    """The layer pitch quantised depths sit on; ``None`` without hits (it is measured then)."""
    if record.traits is None or not record.traits.has_hits:
        return None
    try:
        return hit_sql.layer_pitch(record)
    except ValueError:
        return None


#: Most passes :func:`_stamp` takes; a byte count changes length only at a power of ten.
_STAMP_PASSES = 5


def _stamp(body: dict[str, Any], level: int) -> int:
    """Write ``meta.budget`` into ``body`` and return the size served, the stamp included.

    The stamp's own digits count toward the size it states, so it is rewritten
    until the two agree.
    """
    size = 0
    for _ in range(_STAMP_PASSES):
        body["meta"]["budget"] = {"bytes": size, "limit": density.RESPONSE_LIMIT, "level": level}
        measured = density.wire_size(body)
        if measured == size:
            break
        size = measured
    return size


def _serve(build: Callable[[int], dict[str, Any]], levels: int) -> dict[str, Any]:
    """Build at the first level whose body, as served, fits the budget.

    Each level is a stated reduction the builder notes in the body itself; if
    even the last does not fit, the response says so rather than failing.
    ``meta.budget.bytes`` is the size of the body returned, warning included.
    """
    body: dict[str, Any] = {}
    level = 0
    for level in range(levels):
        body = build(level)
        if _stamp(body, level) <= density.RESPONSE_LIMIT:
            return body
    body["meta"]["warnings"].append(
        f"The response is still over the {density.RESPONSE_LIMIT:,}-byte budget after every "
        "reduction; meta.budget.bytes gives its size.")
    _stamp(body, level)
    return body


@router.get("/api/features", summary="Event-feature explorer: describe, correlations, histograms")
def get_features(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    view: str = Query(
        "catalog",
        description="catalog | describe (D2) | corr (D3) | hist (D4) | hist2d (D5).",
    ),
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: the frame of the features - the absolute (detector) frame, "
            "the per-shower translated frame, or the Local (shower-fixed) frame. Hit "
            "experiments serve the frames their per-event feature sums were derived for."
        ),
    ),
    shower: str = Query(
        "a", description="a | b: whose features. b exists on two-shower data only."),
    classes: str = Query(
        "windows",
        description=(
            "windows | bins | label: the momentum classes - the features notebook's windows "
            "(1, 2, 5, 10, 19.5) ± 0.5 GeV, the producer's 1 GeV bins, or p < 2 against "
            "p ≥ 2 GeV (the aggregate's stored label)."
        ),
    ),
    class_index: str | None = Query(
        None,
        description=(
            "view=corr: the class whose matrix is returned, or 'pooled' for every class "
            "together (the default). Required with classes=bins."
        ),
    ),
    feature: str | None = Query(
        None, description="view=hist and hist2d: the feature id, from view=catalog."),
    scale: str = Query(
        "auto",
        description=(
            "auto | linear | log: the feature axis. auto takes log for a positive feature "
            "spanning a decade or more; an azimuth is always drawn on (−π, π], and a "
            "lattice-quantised feature only on a linear axis."
        ),
    ),
    y_scale: str = Query(
        "auto", description="view=hist2d: auto | linear | log for the deposited-energy axis."),
    exclude_eps: bool | None = Query(
        None,
        description=(
            "Leave out events whose value involves core.py's 10⁻⁶ mm floor. Default: true for "
            "corr (only in the pairs with the volume or a density), false elsewhere."
        ),
    ),
):
    timer = Timer()
    _choice("view", view, VIEWS)
    gate = VIEW_GATES[view]
    caps = capabilities.require(record, gate)
    _choice("coord_system", coord_system, catalog.COORD_SYSTEMS)
    frames = caps.as_dict()["group1_frames"]
    capabilities.require_choice(record, "coord_system", coord_system, frames, gate)
    if shower not in ("a", "b"):
        raise ValidationError(
            f"shower must be a or b; got {shower!r}. Features are per shower, so the two "
            "showers are never pooled.", field="shower")
    showers.of(record, shower)   # refuses b where there is one shower
    _choice("classes", classes, features_mod.CLASS_MODES)
    _choice("scale", scale, SCALES)
    _choice("y_scale", y_scale, SCALES)
    chosen = None
    if view in ("hist", "hist2d"):
        if not feature:
            raise ValidationError(f"view={view} needs a feature; the ids are listed by "
                                  "view=catalog.", field="feature")
        chosen = catalog.get(record.kind, feature, capability=gate)
    eps = EXCLUDE_EPS_DEFAULT[view] if exclude_eps is None else bool(exclude_eps)

    bundle, cached = features_mod.bundle_for(con, record, spec, coord_system, shower)
    cs = features_mod.class_set(con, record, bundle, classes)
    which = (features_mod.parse_class_index(class_index, cs, required=classes == "bins")
             if view == "corr" else None)
    pitch = _pitch(record)
    common = features_mod.common(bundle, cs, full=view == "catalog")
    base_notes = features_mod.notes(bundle, cs)

    def wrap(payload: dict[str, Any], reduced: str | None = None) -> dict[str, Any]:
        view_notes = payload.pop("view_notes", [])
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            query_ms=0.0 if cached else bundle.query_ms,
            total_ms=timer.elapsed_ms,
            cached=cached,
            warnings=["No events match the current selection."] if bundle.n == 0 else [],
            notes={"view": view, "coord_system": coord_system, "shower": shower,
                   "classes": classes, "min_hits": features_mod.MIN_HITS},
        )
        extra = ([typographic(f"Reduced to stay under the {density.RESPONSE_LIMIT:,}-byte "
                              f"budget: {reduced}.")] if reduced else [])
        return envelope(meta, view=view, **common, **payload,
                        notes=base_notes + view_notes + extra, filter=spec.as_dict())

    if view == "catalog":
        payload = {
            "frames": list(frames),
            "showers": list(caps.showers),
            "class_sets": dict(_CLASS_SETS),
            "views": {v: caps.can(g) for v, g in VIEW_GATES.items()},
            "defaults": {"classes": "windows", "scale": "auto",
                         "exclude_eps": dict(EXCLUDE_EPS_DEFAULT)},
            "thresholds": dict(features_mod.THRESHOLDS),
        }
        body = _serve(lambda _: wrap(dict(payload)), 1)
    elif view == "describe":
        body = _serve(
            lambda lvl: wrap(feature_describe.describe_view(bundle, cs, eps, intervals=lvl == 0),
                             "the interval columns dropped" if lvl else None), 2)
    elif view == "corr":
        body = _serve(
            lambda _: wrap(feature_corr.corr_view(bundle, cs, which, eps)), 1)
    elif view == "hist":
        def build_hist(lvl: int) -> dict[str, Any]:
            points, divisor = HIST_LEVELS[lvl]
            reduced = None if lvl == 0 else (
                f"density curves at {points} points"
                + (f", bins divided by {divisor}" if divisor > 1 else ""))
            return wrap(feature_hist.hist_view(bundle, cs, chosen, scale, eps, pitch,
                                               curve_points=points, bins_divisor=divisor), reduced)
        body = _serve(build_hist, len(HIST_LEVELS))
    else:
        filled = sum(1 for c in common["classes"] if c["n"])
        default = (feature_hist.HIST2D_BINS if filled <= feature_hist.HIST2D_MANY_CLASSES
                   else feature_hist.HIST2D_BINS_MANY)
        steps = [default] + [b for b in HIST2D_LEVELS if b < default]

        def build_2d(lvl: int) -> dict[str, Any]:
            reduced = None if lvl == 0 else f"{steps[lvl]} bins per axis instead of {default}"
            return wrap(feature_hist.hist2d_view(bundle, cs, chosen, scale, y_scale, eps, pitch,
                                                 bins=steps[lvl]), reduced)
        body = _serve(build_2d, len(steps))
    return body
