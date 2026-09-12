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


def excluded_undefined_d(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord
) -> int:
    """Total events in this experiment with no defined A-B separation."""
    table = quote(naming.event_table(record.table_name))
    row = con.execute(f"SELECT count(*) FROM {table} WHERE d IS NULL").fetchone()
    return int(row[0] or 0)
