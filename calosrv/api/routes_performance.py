"""``GET /api/model-performance`` - the sidebar metric cards of one network.

``slice_by`` picks the breakdown beside the cards: ``d`` (the default, and
unchanged byte for byte) the separation slices, ``momentum_bin`` the E2 view of
Page 2 - RMSE, MAE, median relative error and bias per shower across the
incident-momentum bins, for every network frame the experiment offers
(``query/performance_bins.py``). The cards, ``by_slice`` and ``slices`` are the
same in both modes. An experiment without reconstruction networks is refused
whatever is asked of it - except an aggregate experiment whose XGBoost analysis
is done: ``slice_by=momentum_bin`` with ``model=energy`` or ``angle`` serves the
shipped regressor's 20 % validation split as one series of the same shape
(code ``xgb``; the angle task adds φ as its own quantity group), with no cards
and no separation slices, which belong to the two-shower networks.
"""

from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Query

from ..db import ddl
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import density, performance, performance_bins
from ..stats.slices import parse_edges
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

#: The breakdowns beside the cards: separation slices, or incident-momentum bins.
SLICE_CHOICES = ("d", "momentum_bin")

#: The payload guard's steps, in order: significant figures, whether the order-statistic
#: cross-check arrays are kept, and what the step says about itself. The first is the
#: payload as built; the whiskers keep their meaning at every step.
BUDGET_STEPS = (
    (6, True, None),
    (6, False, "the order-statistic cross-check arrays (median_rel_order_lo, _hi and "
               "_coverage) are left out"),
    (4, False, "numbers are rounded to 4 significant figures"),
)

FRAME_WORDS = {
    "absolute": "absolute (detector)", "trans": "per-shower translated", "local": "local",
}

#: Titles and captions per task. ``{frame}`` is the input frame of the network.
MODEL_CAPTIONS = {
    "segmentation": {
        "title": "Segmentation Model",
        "caption": (
            "The segmentation network of the {frame} frame assigns each hit's energy between "
            "the two showers, read from segmentation_{column}_pred against its truth "
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
            "The energy network of the {frame} frame estimates each shower's energy "
            "(energy_{column}_pred), compared here with the incident momentum with no "
            "sampling-fraction calibration applied: the network predicts the momentum "
            "scale directly. The headline is the relative resolution σ of "
            "(pred − true) / true per shower."
        ),
        "primary": ["sigma_rel_a", "sigma_rel_b"],
    },
    "angle": {
        "title": "Incident Angle Estimation Model",
        "caption": (
            "The angle network of the {frame} frame predicts each shower's polar angle θ "
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
            "lab | trans | local: the input frame the network was trained on - lab the "
            "absolute (detector) frame, trans the per-shower translated frame (legacy), "
            "local the Separation-Aligned (D-Frame), Local (shower-fixed) frame. The "
            "Separation-Aligned (D-Frame), Translated view (frame=canonical) uses the "
            "absolute-frame (lab) networks."
        ),
    ),
    d_edges: str | None = Query(
        None, description="Separation-distance slice edges for the breakdown."
    ),
    slice_by: str = Query(
        "d",
        description=(
            "d | momentum_bin: the breakdown beside the cards. d is the separation slices "
            "(by_slice). momentum_bin adds by_momentum_bin for the energy and angle networks: "
            "per shower, in the shower's own incident-momentum bin, for every network frame "
            "the experiment offers; the segmentation network is refused because its "
            "quality belongs to the whole event."
        ),
    ),
):
    timer = Timer()
    for name, value, allowed in (("model", model, ddl.MODELS),
                                 ("coord_system", coord_system, ddl.COORD_SYSTEMS),
                                 ("slice_by", slice_by, SLICE_CHOICES)):
        if value not in allowed:
            raise ValidationError(
                f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name,
            )
    if record.kind == ddl.KIND_SINGLE_EVENTS:
        return _xgboost(con, record, spec, model, coord_system, slice_by, timer)
    performance_bins.require_networks(record)
    if slice_by == "momentum_bin" and model == "segmentation":
        raise ValidationError(performance_bins.SEGMENTATION_REFUSAL, field="slice_by")
    report = performance.compute(
        con, record, spec, model=model, coord_system=coord_system, edges=parse_edges(d_edges),
    )
    by_bin = slice_by == "momentum_bin"
    bins = performance_bins.compute(con, record, spec, model) if by_bin else None

    def respond(step: int = 0, disclosed: Sequence[str] = ()) -> dict:
        notes = {"model": model, "coord_system": coord_system}
        warnings: list[str] = []
        if report.n_events == 0:
            warnings.append("No events match the current selection.")
        extra: dict = {}
        if bins is not None:
            digits, keep_order, _ = BUDGET_STEPS[step]
            notes["slice_by"] = slice_by
            warnings += [*bins.warnings(), *disclosed]
            extra["by_momentum_bin"] = bins.as_dict(digits=digits, keep_order=keep_order)
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=warnings,
            notes=notes,
        )
        return envelope(
            meta,
            **report.as_dict(),
            model=_context(model, coord_system),
            filter=spec.as_dict(),
            **extra,
        )

    body = respond()
    if bins is None:
        return body
    # Six series of twenty bins come to about 40 KB, so this guard is for a dataset with
    # more bins than the producers write: it sheds the order-statistic cross-check
    # arrays and then two significant figures, and says so. A body still over the
    # contract after both is served as it is, with that said too.
    first = size = density.wire_size(body)
    disclosed: list[str] = []
    for step in range(1, len(BUDGET_STEPS)):
        if size < density.RESPONSE_LIMIT:
            break
        disclosed.append(
            f"Over the {density.RESPONSE_LIMIT:,}-byte contract at {first:,} bytes, so "
            f"{BUDGET_STEPS[step][2]}; the whiskers keep their meaning."
        )
        body = respond(step, disclosed)
        size = density.wire_size(body)
    if size >= density.RESPONSE_LIMIT:
        disclosed.append(
            f"Served as it is: {size:,} bytes against the {density.RESPONSE_LIMIT:,}-byte "
            "contract after every reduction.")
        body = respond(len(BUDGET_STEPS) - 1, disclosed)
    return body


#: The aggregate kind's refusal of what only the two-shower networks serve.
XGB_SLICE_REFUSAL = (
    "An aggregate experiment draws the XGBoost series by incident-momentum bin only: "
    "slice_by=momentum_bin with model=energy or model=angle. The separation slices and the "
    "segmentation network need two showers per event."
)


def _xgboost(con, record, spec, model: str, coord_system: str, slice_by: str, timer: Timer) -> dict:
    """E2 of an aggregate experiment: the XGBoost validation-split series, in E2's shape."""
    performance_bins.require_xgb(record)
    if slice_by != "momentum_bin" or model == "segmentation":
        raise ValidationError(XGB_SLICE_REFUSAL, field="slice_by" if slice_by != "momentum_bin"
                              else "model")
    report = performance_bins.compute_xgb(con, record, spec, model)
    titles = {"energy": "XGBoost momentum regressor", "angle": "XGBoost angle regressor"}
    run = report.run

    def respond(step: int = 0, disclosed: Sequence[str] = ()) -> dict:
        digits, keep_order, _ = BUDGET_STEPS[step]
        warnings: list[str] = []
        if report.split["n_selected"] == 0:
            warnings.append("No events match the current selection.")
        warnings += [*report.warnings(), *disclosed]
        meta = ApiMeta(
            table_name=record.table_name, exact=True, total_ms=timer.elapsed_ms,
            warnings=warnings,
            notes={"model": model, "coord_system": coord_system, "slice_by": slice_by,
                   "source": performance_bins.XGB_CODE},
        )
        caption = (
            f"The shipped XGBoost {run['task']} regressor of {run['species']} seed {run['seed']} "
            f"({run['model_file']}) on the notebook's 20 % validation split: "
            f"{report.split['n_validation']:,} of the {report.split['n_selected']:,} selected "
            "events. It reads 52 event-level features of all three frames, so it has no input "
            "frame; coord_system does not apply.")
        return envelope(
            meta,
            n_events=report.split["n_selected"],
            network={"model": model, "frame": performance_bins.XGB_CODE},
            cards=[], by_slice=[], slices=[],
            notes={"cards": ("The metric cards and the separation slices belong to the "
                             "two-shower networks; an aggregate experiment draws the XGBoost "
                             "series by momentum bin only.")},
            model={"title": titles[model], "caption": caption, "primary": [],
                   "network": {"model": model, "frame": performance_bins.XGB_CODE}},
            filter=spec.as_dict(),
            run=run,
            by_momentum_bin=report.as_dict(digits=digits, keep_order=keep_order),
        )

    body = respond()
    first = size = density.wire_size(body)
    disclosed: list[str] = []
    for step in range(1, len(BUDGET_STEPS)):
        if size < density.RESPONSE_LIMIT:
            break
        disclosed.append(
            f"Over the {density.RESPONSE_LIMIT:,}-byte contract at {first:,} bytes, so "
            f"{BUDGET_STEPS[step][2]}; the whiskers keep their meaning.")
        body = respond(step, disclosed)
        size = density.wire_size(body)
    if size >= density.RESPONSE_LIMIT:
        disclosed.append(
            f"Served as it is: {size:,} bytes against the {density.RESPONSE_LIMIT:,}-byte "
            "contract after every reduction.")
        body = respond(len(BUDGET_STEPS) - 1, disclosed)
    return body
