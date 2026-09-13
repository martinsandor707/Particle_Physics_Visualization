"""Event-level summary of a selection.

Everything here reads the per-event table, and that is the point.

``avg(d)`` computed over hit rows would weight each event by its hit
multiplicity. Multiplicity correlates strongly with incident momentum, so such a
mean is silently biased toward high-energy events - it looks like a separation
distance and is not one. The same trap applies to the mean E1, the mean E2, and
the average of the dataset's own centroid columns. Keeping all of them in this
module, which never touches the projection table, makes the rule structural
rather than a comment someone can miss.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import duckdb

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from .filters import FilterSpec


@dataclass
class SelectionSummary:
    """Per-event statistics for the active selection."""

    n_events: int
    n_hits: int
    n_events_no_d: int
    e_dep_total: float
    d_mean: float | None
    d_median: float | None
    d_sd: float | None
    d_min: float | None
    d_max: float | None
    e1_mean: float | None
    e2_mean: float | None
    centroid_a: dict[str, float | None]
    centroid_b: dict[str, float | None]
    dataset_separation_mm: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "n_hits": self.n_hits,
            "n_events_no_d": self.n_events_no_d,
            "e_dep_total": self.e_dep_total,
            "d": {
                "mean": self.d_mean,
                "median": self.d_median,
                "sd": self.d_sd,
                "min": self.d_min,
                "max": self.d_max,
            },
            "e1_mean": self.e1_mean,
            "e2_mean": self.e2_mean,
            "centroid_dataset": {
                "label": "Dataset centroids (per-event average)",
                "a": self.centroid_a,
                "b": self.centroid_b,
                "separation_mm": self.dataset_separation_mm,
            },
        }


def summarise(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
) -> SelectionSummary:
    """Summarise the selected events. Roughly 20 000 rows; sub-millisecond."""
    table = quote(naming.event_table(record.table_name))
    row = con.execute(
        f"""
        SELECT
            count(*)                               AS n_events,
            coalesce(sum(n_hits), 0)               AS n_hits,
            count(*) FILTER (WHERE d IS NULL)      AS n_events_no_d,
            coalesce(sum(e_dep), 0.0)              AS e_dep_total,
            avg(d)                                 AS d_mean,
            median(d)                              AS d_median,
            stddev_samp(d)                         AS d_sd,
            min(d)                                 AS d_lo,
            max(d)                                 AS d_hi,
            avg(CAST(e1 AS DOUBLE))                AS e1_mean,
            avg(CAST(e2 AS DOUBLE))                AS e2_mean,
            avg(CAST(cax AS DOUBLE))               AS cax,
            avg(CAST(cay AS DOUBLE))               AS cay,
            avg(CAST(caz AS DOUBLE))               AS caz,
            avg(CAST(cbx AS DOUBLE))               AS cbx,
            avg(CAST(cby AS DOUBLE))               AS cby,
            avg(CAST(cbz AS DOUBLE))               AS cbz
        FROM {table}
        WHERE {spec.where_sql()}
        """,
        spec.params(),
    ).fetchone()

    def value(index: int) -> float | None:
        v = row[index]
        return float(v) if v is not None else None

    centroid_a = {"x": value(11), "y": value(12), "z": value(13)}
    centroid_b = {"x": value(14), "y": value(15), "z": value(16)}

    separation = None
    if all(centroid_a[k] is not None and centroid_b[k] is not None for k in "xy"):
        dx = centroid_a["x"] - centroid_b["x"]
        dy = centroid_a["y"] - centroid_b["y"]
        separation = float((dx * dx + dy * dy) ** 0.5)

    return SelectionSummary(
        n_events=int(row[0] or 0),
        n_hits=int(row[1] or 0),
        n_events_no_d=int(row[2] or 0),
        e_dep_total=float(row[3] or 0.0),
        d_mean=value(4),
        d_median=value(5),
        d_sd=value(6),
        d_min=value(7),
        d_max=value(8),
        e1_mean=value(9),
        e2_mean=value(10),
        centroid_a=centroid_a,
        centroid_b=centroid_b,
        dataset_separation_mm=separation,
    )


#: Largest selection for which individual trajectories are drawn.
#:
#: Above this the depth panels become unreadable spaghetti, and - more to the
#: point - there is no aggregate substitute: see :func:`angular_coherence`.
MAX_TRAJECTORY_EVENTS = 50


def angular_coherence(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
) -> dict[str, Any]:
    """Circular concentration of the incident azimuth over the selection.

    This is the measurement that decides how the depth panels may present
    direction at all.

    Azimuth is circular, so its arithmetic mean is meaningless; the honest
    summary is the mean resultant length ``R = |mean(e^{i phi})|``, which is 1
    when every event points the same way and 0 when they are spread uniformly
    around the circle.

    Measured on the production dataset, ``R`` is 0.012 over the full sample,
    0.042 for a 122-event momentum window, and still only 0.178 for a 7-event
    cut. Azimuth is effectively uniform at every scale reachable through the
    filters. A single averaged trajectory line would therefore point in an
    arbitrary direction while looking authoritative, which is why one is never
    drawn; individual events are shown instead, and only when few enough to read.
    """
    table = quote(naming.event_table(record.table_name))
    row = con.execute(
        f"""
        SELECT
            count(*)                                        AS n,
            avg(cos(CAST(phi_a AS DOUBLE)))                 AS ca,
            avg(sin(CAST(phi_a AS DOUBLE)))                 AS sa,
            avg(cos(CAST(phi_b AS DOUBLE)))                 AS cb,
            avg(sin(CAST(phi_b AS DOUBLE)))                 AS sb,
            avg(CAST(theta_a AS DOUBLE))                    AS theta_a,
            avg(CAST(theta_b AS DOUBLE))                    AS theta_b
        FROM {table}
        WHERE {spec.where_sql()} AND phi_a IS NOT NULL AND phi_b IS NOT NULL
        """,
        spec.params(),
    ).fetchone()

    def resultant(cos_mean, sin_mean) -> float | None:
        if cos_mean is None or sin_mean is None:
            return None
        return float(math.hypot(float(cos_mean), float(sin_mean)))

    return {
        "n": int(row[0] or 0),
        "r_a": resultant(row[1], row[2]),
        "r_b": resultant(row[3], row[4]),
        "theta_a_mean": float(row[5]) if row[5] is not None else None,
        "theta_b_mean": float(row[6]) if row[6] is not None else None,
        "note": (
            "Incident azimuth is near-uniform over this selection, so no single "
            "averaged trajectory is drawn; it would point in an arbitrary "
            "direction. The solid lines are the energy-weighted shower axes "
            "measured from the displayed data."
        ),
    }


def trajectories(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    limit: int = MAX_TRAJECTORY_EVENTS,
) -> list[dict[str, Any]]:
    """Per-event entry points and incident directions, for the depth overlays.

    Returns at most ``limit`` events. Events whose shower-A centroid is
    undefined are skipped: 182 events in the production dataset deposited no
    energy at all in shower A, so they have no entry point to project from.

    The payload is tiny - fifty events times ten floats - so it rides along with
    the projections response rather than costing a second round trip.
    """
    table = quote(naming.event_table(record.table_name))
    rows = con.execute(
        f"""
        SELECT event_number,
               CAST(theta_a AS DOUBLE), CAST(phi_a AS DOUBLE),
               CAST(cax AS DOUBLE), CAST(cay AS DOUBLE), CAST(caz AS DOUBLE),
               CAST(theta_b AS DOUBLE), CAST(phi_b AS DOUBLE),
               CAST(cbx AS DOUBLE), CAST(cby AS DOUBLE), CAST(cbz AS DOUBLE)
        FROM {table}
        WHERE {spec.where_sql()}
          AND theta_a IS NOT NULL AND phi_a IS NOT NULL
          AND cax IS NOT NULL AND cay IS NOT NULL AND caz IS NOT NULL
        ORDER BY event_number
        LIMIT {int(limit)}
        """,
        spec.params(),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        entry = {
            "event": int(r[0]),
            "a": {
                "theta": r[1], "phi": r[2],
                "x": r[3], "y": r[4], "z": r[5],
            },
        }
        # Shower B can be undefined independently of A.
        if all(v is not None for v in r[6:11]):
            entry["b"] = {
                "theta": r[6], "phi": r[7],
                "x": r[8], "y": r[9], "z": r[10],
            }
        out.append(entry)
    return out


def excluded_undefined_d(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord
) -> int:
    """Total events in this experiment with no defined A-B separation."""
    table = quote(naming.event_table(record.table_name))
    row = con.execute(f"SELECT count(*) FROM {table} WHERE d IS NULL").fetchone()
    return int(row[0] or 0)
