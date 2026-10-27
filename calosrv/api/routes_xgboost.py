"""``GET /api/xgboost`` - the XGBoost model views of Page 2: E1, E3, E4 and E5.

``view`` picks the card: ``cv`` (E1, five-fold cross-validation), ``binary``
(E3, thresholding at 2 GeV on a 99 : 1 sample; the momentum task only),
``surrogate`` (E4, the depth-3 surrogate tree) and ``importance`` (E5, gain
importances); ``task`` is ``momentum`` or ``angle``. Every view is read from
the experiment's stored analysis (``calosrv/modelruns``) and is dataset-wide,
as the notebook computes it: the selection's parameters are accepted, so every
card can send the same filter, and the payload says it does not apply.

The ``xgboost`` capability gate decides whether the experiment can answer: an
experiment of another kind, one whose source file pairs with no models, and
one whose analysis is queued, running, failed or stale are refused (422) with
the gate's sentence - "Analysing: 7 of 18 steps", the failure text, the
pairing's reason.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..modelruns import views
from ..query import capabilities
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()


@router.get("/api/xgboost", summary="XGBoost model views: cross-validation, thresholding, "
                                    "surrogate tree, gain importance")
def get_xgboost(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    view: str = Query(
        ..., description="cv | binary | surrogate | importance: the notebook view (E1, E3, E4, E5)."),
    task: str = Query(
        "momentum",
        description="momentum | angle: which shipped regressor. binary applies to momentum only."),
):
    timer = Timer()
    if view not in views.VIEWS:
        raise ValidationError(f"view must be one of {', '.join(views.VIEWS)}; got {view!r}.",
                              field="view")
    if task not in views.TASKS:
        raise ValidationError(f"task must be one of {', '.join(views.TASKS)}; got {task!r}.",
                              field="task")
    if view == "binary" and task != "momentum":
        raise ValidationError(
            "view=binary thresholds the momentum regressor at 2 GeV; the angle task has no class "
            "boundary. Use task=momentum.", field="task")
    capabilities.require(record, "xgboost", field="view")
    runs = views.require_runs(con, record, task, field="view")
    if view == "cv":
        body = views.cv_view(con, record, runs, task)
    elif view == "binary":
        body = views.binary_view(con, record, runs)
    elif view == "surrogate":
        body = views.surrogate_view(con, record, runs, task)
    else:
        body = views.importance_view(con, record, runs, task)
    run = views.run_block(runs, task)
    warnings = [] if run["split"]["reproduced"] else [run["split"]["warning"]]
    meta = ApiMeta(table_name=record.table_name, exact=True, total_ms=timer.elapsed_ms,
                   warnings=warnings, notes={"view": view, "task": task})
    return envelope(meta, run=run, **views.dataset_wide(spec.as_dict()), **body)
