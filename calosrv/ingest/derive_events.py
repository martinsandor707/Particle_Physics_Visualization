"""Build the per-event summary of additive sufficient statistics.

This table is the reason the interactive metrics are both fast and exact.

Voxel accuracy, mean absolute error and RMSE over a filtered set of events are
each of the form ``sum(numerator) / sum(denominator)`` across events. Storing the
numerator and denominator per event means those metrics roll up over *any*
selection by summing roughly twenty thousand rows - no approximation, no
sampling, and no second pass over the 22.5 million hit rows. The same holds for
the reconstructed-energy panel, whose per-event deposited sums are computed once
here instead of on every slider move.

``max()`` rather than ``any_value()`` is used for the per-event constants. They
are replicated identically on every hit row of an event, so the two agree - but
``max`` ignores nulls, which means an event whose separation distance is missing
on some rows and present on others would still get a value. Measurement says
that case does not occur (the nullness is per-event), and ``max`` costs nothing,
so the safe form is the one used.
"""

from __future__ import annotations

import logging

import duckdb

from ..db import naming
from ..db.ddl import create_event_table, drop_table
from ..db.naming import quote

log = logging.getLogger(__name__)

#: Threshold at which a voxel fraction is read as a categorical assignment to
#: shower A, for the classification metrics.
VOXEL_THRESHOLD = 0.5


def build(con: duckdb.DuckDBPyConnection, name: str) -> int:
    """Create ``event_<name>`` from ``hit_<name>``; returns the event count."""
    hit_physical = naming.hit_table(name)
    event_physical = naming.event_table(name)

    con.execute(drop_table(event_physical))
    con.execute(create_event_table(event_physical))

    log.info("Building %s (per-event sufficient statistics)", event_physical)
    con.execute(
        f"""
        INSERT INTO {quote(event_physical)}
        SELECT
            event_number,
            max(overlap)                            AS ovl,
            max(incoming_momentum_A)                AS e1,
            max(incoming_momentum_B)                AS e2,
            max(incoming_momentum_bin_A)            AS e1_bin,
            max(incoming_momentum_bin_B)            AS e2_bin,
            max(incoming_theta_A)                   AS theta_a,
            max(incoming_theta_B)                   AS theta_b,
            max(incoming_phi_A)                     AS phi_a,
            max(incoming_phi_B)                     AS phi_b,
            max(centroid_AB_distance)               AS d,
            max(centroid_A_x) AS cax, max(centroid_A_y) AS cay,
            max(centroid_A_z) AS caz,
            max(centroid_B_x) AS cbx, max(centroid_B_y) AS cby,
            max(centroid_B_z) AS cbz,

            count(*)                                AS n_hits,
            sum(energy)                             AS e_dep,

            -- Deposited energy attributed to each shower. The cast to DOUBLE is
            -- explicit: voxel_fA_* are REAL, and a future refactor must not be
            -- able to quietly demote this accumulator to single precision
            -- across fifteen decades of energy.
            sum(energy * CAST(voxel_fA_pred AS DOUBLE))         AS e_a_pred,
            sum(energy * (1.0 - CAST(voxel_fA_pred AS DOUBLE))) AS e_b_pred,
            sum(energy * CAST(voxel_fA_true AS DOUBLE))         AS e_a_true,
            sum(energy * (1.0 - CAST(voxel_fA_true AS DOUBLE))) AS e_b_true,

            -- Model-performance sufficient statistics.
            sum(abs(CAST(voxel_fA_pred AS DOUBLE)
                    - CAST(voxel_fA_true AS DOUBLE)))           AS sum_abs_err,
            sum(energy * abs(CAST(voxel_fA_pred AS DOUBLE)
                             - CAST(voxel_fA_true AS DOUBLE)))  AS sum_wabs_err,
            sum(pow(CAST(voxel_fA_pred AS DOUBLE)
                    - CAST(voxel_fA_true AS DOUBLE), 2))        AS sum_sq_err,
            count(*) FILTER (
                WHERE (voxel_fA_pred >= {VOXEL_THRESHOLD})
                    = (voxel_fA_true >= {VOXEL_THRESHOLD})
            )                                                    AS n_correct,
            count(*) FILTER (WHERE voxel_fA_true >= {VOXEL_THRESHOLD}) AS n_true_a,
            count(*) FILTER (WHERE voxel_fA_pred >= {VOXEL_THRESHOLD}) AS n_pred_a,
            count(*) FILTER (WHERE voxel_fA_pred >= {VOXEL_THRESHOLD}
                               AND voxel_fA_true >= {VOXEL_THRESHOLD}) AS n_tp,
            count(*) FILTER (WHERE particle_origin = 'A+B')            AS n_shared
        FROM {quote(hit_physical)}
        WHERE energy IS NOT NULL AND isfinite(energy) AND energy > 0
        GROUP BY event_number
        """
    )

    n_events = int(
        con.execute(f"SELECT count(*) FROM {quote(event_physical)}").fetchone()[0]
    )
    log.info("%s holds %s events", event_physical, f"{n_events:,}")
    return n_events


def calibration(con: duckdb.DuckDBPyConnection, name: str) -> tuple[float, float]:
    """Fit the per-shower sampling-fraction calibration constants.

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
    that the resolution measurement exists to quantify.
    """
    event_physical = naming.event_table(name)
    row = con.execute(
        f"""
        SELECT sum(CAST(e1 AS DOUBLE)), sum(e_a_true),
               sum(CAST(e2 AS DOUBLE)), sum(e_b_true)
        FROM {quote(event_physical)}
        """
    ).fetchone()

    p_a, dep_a, p_b, dep_b = (float(v or 0.0) for v in row)
    c_a = p_a / dep_a if dep_a > 0 else float("nan")
    c_b = p_b / dep_b if dep_b > 0 else float("nan")

    log.info(
        "Sampling-fraction calibration: c_A=%.3f (f_A=%.6f), c_B=%.3f (f_B=%.6f)",
        c_a, (1.0 / c_a) if c_a else float("nan"),
        c_b, (1.0 / c_b) if c_b else float("nan"),
    )
    return c_a, c_b
