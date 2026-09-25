"""Build the per-event summary of additive sufficient statistics.

This table is the reason the interactive metrics are both fast and exact.

Voxel accuracy, mean absolute error and RMSE over a filtered set of events are
each of the form ``sum(numerator) / sum(denominator)`` across events. Storing the
numerator and denominator per event - once per segmentation network - means
those metrics roll up over *any* selection by summing roughly twenty thousand
rows: no approximation, no sampling, and no second pass over the 24 million hit
rows. The same holds for the reconstructed-energy panel, whose per-event
deposited sums are computed once here instead of on every slider move.

The angle and energy networks predict one value per *shower*, repeated on every
hit of it, so those are stored here too: ``max(col) FILTER (WHERE
particle_origin = 'A')`` for shower A, and ``particle_origin <> 'A'`` for B -
the 422 'A+B' rows carry shower B's values, measured on every one of them.

``max()`` rather than ``any_value()`` is used for the per-event constants. They
are replicated identically on every hit row of an event, so the two agree - but
``max`` ignores nulls, and it is deterministic. The ingest verification asserts
the constancy that makes this safe (``chk_p0_spread``, ``chk_pt_spread``).

**Two independent scans.** The event aggregate and the cell census each read
the archive on their own. A single ``WITH h AS (SELECT * ...)`` referenced by
both could be materialised by the planner, which on the production file means
24 million rows of 99 columns - about 10 GB - held at once.
"""

from __future__ import annotations

import logging

import duckdb

from ..db import naming
from ..db.ddl import (
    COORD_SYSTEMS, EVENT_COLUMN_NAMES, NETWORK_FRAME, SEG_STAT_COLUMNS, cam_bit,
    create_event_table, csv_model_column, drop_table, frame_code, raw_cam_columns,
)
from ..db.naming import quote
from .derive_proj import keep_predicate

log = logging.getLogger(__name__)

#: Threshold at which a voxel fraction is read as a categorical assignment to
#: shower A, for the classification metrics.
VOXEL_THRESHOLD = 0.5

#: Columns filled by the cell census rather than the event aggregate.
CELL_COLUMNS = ("n_cells", "n_split_cells", "e_split", "chk_bad_split")

_IS_A = "particle_origin = 'A'"
_NOT_A = "particle_origin <> 'A'"      # shower B, including the 'A+B' rows
_NOT_B = "particle_origin <> 'B'"      # rows that define P0 of shower A


def _seg_stats(coord: str) -> dict[str, str]:
    frame = NETWORK_FRAME[coord]
    code = frame_code(coord)
    p = f"CAST({quote(csv_model_column('segmentation', frame, 'pred'))} AS DOUBLE)"
    t = f"CAST({quote(csv_model_column('segmentation', frame, 'true'))} AS DOUBLE)"
    th = VOXEL_THRESHOLD
    # The casts to DOUBLE are explicit: the voxel fractions are REAL, and a
    # future refactor must not be able to demote these accumulators to single
    # precision across fifteen decades of energy.
    exprs = {
        "e_a_pred": f"sum(energy * {p})",
        "e_b_pred": f"sum(energy * (1.0 - {p}))",
        "e_a_true": f"sum(energy * {t})",
        "e_b_true": f"sum(energy * (1.0 - {t}))",
        "sum_abs_err": f"sum(abs({p} - {t}))",
        "sum_wabs_err": f"sum(energy * abs({p} - {t}))",
        "sum_sq_err": f"sum(pow({p} - {t}, 2))",
        "n_correct": f"count(*) FILTER (WHERE ({p} >= {th}) = ({t} >= {th}))",
        "n_true_a": f"count(*) FILTER (WHERE {t} >= {th})",
        "n_pred_a": f"count(*) FILTER (WHERE {p} >= {th})",
        "n_tp": f"count(*) FILTER (WHERE {p} >= {th} AND {t} >= {th})",
    }
    assert set(exprs) == {stem for stem, _ in SEG_STAT_COLUMNS}
    return {f"{stem}_{code}": expr for stem, expr in exprs.items()}


def _spread(column: str, where: str) -> str:
    return (f"coalesce(max({column}) FILTER (WHERE {where}) "
            f"- min({column}) FILTER (WHERE {where}), 0)")


def event_expressions() -> dict[str, str]:
    """SQL for every event-aggregate column (the cell census excluded)."""
    e: dict[str, str] = {
        "event_number": "event_number",
        "ovl": "max(overlap)",
        "e1": "max(incoming_momentum_A)",
        "e2": "max(incoming_momentum_B)",
        "e1_bin": "max(incoming_momentum_bin_A)",
        "e2_bin": "max(incoming_momentum_bin_B)",
        "theta_a": "max(incoming_theta_A)",
        "theta_b": "max(incoming_theta_B)",
        "phi_a": "max(incoming_phi_A)",
        "phi_b": "max(incoming_phi_B)",
        "d": "max(centroid_AB_distance)",
        "d_t": "max(centroid_AB_distance_trans)",
        "d_l": "max(centroid_AB_distance_local)",
    }
    for suffix, csv_suffix in (("", ""), ("_t", "_trans"), ("_l", "_local")):
        for shower in "ab":
            for axis in "xyz":
                e[f"c{shower}{axis}{suffix}"] = (
                    f"max(centroid_{shower.upper()}_{axis}{csv_suffix})"
                )
    # P0 of each shower, recovered as x - x_trans over that shower's rows. The
    # 'A+B' rows belong to both showers' first layer (P0_A = P0_B = that hit in
    # every one of the 685 affected showers), so each shower includes them.
    for shower, where in (("a", _NOT_B), ("b", _NOT_A)):
        for axis in "xyz":
            e[f"p0{shower}{axis}"] = (
                f"avg(CAST({axis} AS DOUBLE) - CAST({axis}_trans AS DOUBLE)) "
                f"FILTER (WHERE {where})"
            )
    e.update({
        "n_hits": "count(*)",
        "n_a_rows": f"count(*) FILTER (WHERE {_IS_A})",
        "n_b_rows": "count(*) FILTER (WHERE particle_origin = 'B')",
        "n_ab_rows": "count(*) FILTER (WHERE particle_origin = 'A+B')",
        "e_ab": "coalesce(sum(energy) FILTER (WHERE particle_origin = 'A+B'), 0.0)",
        "e_dep": "sum(energy)",
    })
    for coord in COORD_SYSTEMS:
        e.update(_seg_stats(coord))
    for coord in COORD_SYSTEMS:
        frame = NETWORK_FRAME[coord]
        code = frame_code(coord)
        energy_pred = quote(csv_model_column("energy", frame, "pred"))
        angle_pred = quote(csv_model_column("angle", frame, "pred"))
        e[f"en_pred_a_{code}"] = f"max({energy_pred}) FILTER (WHERE {_IS_A})"
        e[f"en_pred_b_{code}"] = f"max({energy_pred}) FILTER (WHERE {_NOT_A})"
        e[f"th_pred_a_{code}"] = f"max({angle_pred}) FILTER (WHERE {_IS_A})"
        e[f"th_pred_b_{code}"] = f"max({angle_pred}) FILTER (WHERE {_NOT_A})"
    energy_true = quote(csv_model_column("energy", "absolute", "true"))
    angle_true = quote(csv_model_column("angle", "absolute", "true"))
    e["en_true_a"] = f"max({energy_true}) FILTER (WHERE {_IS_A})"
    e["en_true_b"] = f"max({energy_true}) FILTER (WHERE {_NOT_A})"
    e["th_true_a"] = f"max({angle_true}) FILTER (WHERE {_IS_A})"
    e["th_true_b"] = f"max({angle_true}) FILTER (WHERE {_NOT_A})"

    # Which CAM maps are identically zero over the event (1 energy-model
    # absolute event, 26 local and 38 trans have an all-zero Shap-CAM on the
    # production file): a map with no peak cannot be normalised to one.
    terms = [
        f"CASE WHEN max(abs({quote(csv_name)})) = 0 THEN {1 << cam_bit(model, coord, cam)} ELSE 0 END"
        for _, csv_name, model, coord, cam in raw_cam_columns()
    ]
    e["cam_zero_mask"] = f"CAST({' + '.join(terms)} AS UINTEGER)"

    p0_spreads = [
        _spread(f"(CAST({axis} AS DOUBLE) - CAST({axis}_trans AS DOUBLE))", where)
        for axis in "xyz" for where in (_NOT_B, _NOT_A)
    ]
    e["chk_p0_spread"] = f"greatest({', '.join(p0_spreads)})"
    pt_spreads = []
    for model in ("angle", "energy"):
        for frame in ("absolute", "trans", "local"):
            for field in ("pred", "true"):
                column = quote(csv_model_column(model, frame, field))
                pt_spreads += [_spread(column, _IS_A), _spread(column, _NOT_A)]
    e["chk_pt_spread"] = f"greatest({', '.join(pt_spreads)})"
    return e


def build(con: duckdb.DuckDBPyConnection, name: str, source: str) -> int:
    """Create ``event_<name>`` from the archive relation ``source``; returns the event count."""
    event_physical = naming.event_table(name)
    con.execute(drop_table(event_physical))
    con.execute(create_event_table(event_physical))

    expressions = event_expressions()
    aggregate = ",\n            ".join(f"{sql} AS {col}" for col, sql in expressions.items())
    missing = [c for c in EVENT_COLUMN_NAMES if c not in expressions and c not in CELL_COLUMNS]
    assert not missing, f"no source for event columns {missing}"
    select = ", ".join(
        f"coalesce(c.{col}, 0) AS {col}" if col in CELL_COLUMNS else f"m.{col}"
        for col in EVENT_COLUMN_NAMES
    )

    log.info("Building %s (per-event sufficient statistics, per-shower values)", event_physical)
    con.execute(
        f"""
        INSERT INTO {quote(event_physical)} ({', '.join(EVENT_COLUMN_NAMES)})
        SELECT {select}
        FROM (
            SELECT
            {aggregate}
            FROM {source}
            WHERE {keep_predicate()}
            GROUP BY event_number
        ) m
        LEFT JOIN (
            -- The cell census. A cell both showers deposited in is two rows (one
            -- A, one B) in this schema, so rows are not cells: 1,629,316 cells of
            -- the production file are split, and only 422 remain 'A+B' rows.
            SELECT event_number,
                   count(*)                                   AS n_cells,
                   count(*) FILTER (WHERE k > 1)              AS n_split_cells,
                   coalesce(sum(e) FILTER (WHERE k > 1), 0.0) AS e_split,
                   count(*) FILTER (WHERE k > 1 AND NOT (k = 2 AND lo = 'A' AND hi = 'B'))
                                                              AS chk_bad_split
            FROM (
                SELECT event_number, cellID, count(*) AS k, sum(energy) AS e,
                       min(particle_origin) AS lo, max(particle_origin) AS hi
                FROM {source}
                WHERE {keep_predicate()}
                GROUP BY event_number, cellID
            )
            GROUP BY event_number
        ) c USING (event_number)
        """
    )

    n_events = int(
        con.execute(f"SELECT count(*) FROM {quote(event_physical)}").fetchone()[0]
    )
    log.info("%s holds %s events", event_physical, f"{n_events:,}")
    return n_events


def calibration(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, tuple[float, float]]:
    """Fit the per-shower sampling-fraction calibration constants, per frame.

    A sampling calorimeter records only a fraction of a particle's energy in its
    active cells. On this dataset the summed deposit per event is of order
    0.05 GeV while the incident momenta are 0.4-20 GeV, so a deposited sum and an
    incident momentum are not on the same axis and must never be plotted as if
    they were.

    The constants convert one to the other, fitted from ground truth over the
    whole table::

        c_A = sum(incoming_momentum_A) / sum(E_dep_A_true)
        c_B = sum(incoming_momentum_B) / sum(E_dep_B_true)

    Summing before dividing, rather than averaging per-event ratios, is
    deliberate. A per-event normalisation would force each event's reconstructed
    energy onto its own truth exactly, which removes the containment scatter
    that the resolution measurement exists to quantify. One pair per frame: the
    truth deposits agree across frames to 1e-8 median on the production file,
    so the constants do too, and that agreement is itself a check.
    """
    event_physical = quote(naming.event_table(name))
    out: dict[str, tuple[float, float]] = {}
    for coord in COORD_SYSTEMS:
        code = frame_code(coord)
        row = con.execute(
            f"""
            SELECT sum(CAST(e1 AS DOUBLE)), sum(e_a_true_{code}),
                   sum(CAST(e2 AS DOUBLE)), sum(e_b_true_{code})
            FROM {event_physical}
            """
        ).fetchone()
        p_a, dep_a, p_b, dep_b = (float(v or 0.0) for v in row)
        c_a = p_a / dep_a if dep_a > 0 else float("nan")
        c_b = p_b / dep_b if dep_b > 0 else float("nan")
        out[code] = (c_a, c_b)
        log.info("Sampling-fraction calibration (%s): c_A=%.3f, c_B=%.3f", code, c_a, c_b)
    return out
