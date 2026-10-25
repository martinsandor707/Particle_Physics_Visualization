"""Event-level summary of a selection.

Everything here reads the per-event table, and that is the point.

``avg(d)`` computed over hit rows would weight each event by its hit
multiplicity. Multiplicity correlates strongly with incident momentum, so such a
mean is silently biased toward high-energy events - it looks like a separation
distance and is not one. The same trap applies to the mean E1, the mean E2, and
the average of the dataset's own centroid columns. Keeping all of them in this
module, which never touches the projection table, makes the rule structural
rather than a comment someone can miss.

A single-shower experiment has one shower per event, stored under the
shower-A names, and no second momentum, no separation D and no B centroid.
Every function here reads the experiment's showers (``query/showers.py``) and
returns the same keys, with ``null`` where the quantity does not exist rather
than a zero that would read as a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import duckdb

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..text import typographic
from . import showers as showers_mod
from .filters import FilterSpec
from .showers import ShowerColumns


def centroid_columns(shower: ShowerColumns) -> tuple[str, str, str]:
    """A shower's energy-weighted 3-D centroid in the event table (raw z), as DOUBLE expressions.

    ``cax, cay, caz`` (``cbx ..`` for B) in both hit kinds; the single shower
    is stored under the shower-A names.
    """
    x, y, z = (f"CAST(c{shower.key}{axis} AS DOUBLE)" for axis in "xyz")
    return x, y, z


def centroid_defined(shower: ShowerColumns) -> str:
    """The event-table predicate: the shower's 3-D centroid is defined."""
    return " AND ".join(f"c{shower.key}{axis} IS NOT NULL" for axis in "xyz")


@dataclass
class SelectionSummary:
    """Per-event statistics for the active selection.

    For a single-shower experiment the D statistics, ``e2_mean``,
    ``n_events_no_d``, ``centroid_b`` and the separation are ``None``.
    """

    n_events: int
    n_hits: int
    n_events_no_d: int | None
    e_dep_total: float
    d_mean: float | None
    d_median: float | None
    d_sd: float | None
    d_min: float | None
    d_max: float | None
    e1_mean: float | None
    e2_mean: float | None
    centroid_a: dict[str, float | None]
    centroid_b: dict[str, float | None] | None
    dataset_separation_mm: float | None
    label: str = "Dataset centroids (per-event average)"

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
                "label": self.label,
                "a": self.centroid_a,
                "b": self.centroid_b,
                "separation_mm": self.dataset_separation_mm,
            },
        }


def _summarise_single(
    con: duckdb.DuckDBPyConnection, table: str, spec: FilterSpec, shower: ShowerColumns,
) -> SelectionSummary:
    """One shower per event: no separation, no second momentum, no B centroid."""
    cx, cy, cz = centroid_columns(shower)
    row = con.execute(
        f"""
        SELECT
            count(*)                               AS n_events,
            coalesce(sum(n_hits), 0)               AS n_hits,
            coalesce(sum(e_dep), 0.0)              AS e_dep_total,
            avg(CAST({shower.momentum} AS DOUBLE)) AS e1_mean,
            avg({cx})                              AS cax,
            avg({cy})                              AS cay,
            avg({cz})                              AS caz
        FROM {table}
        WHERE {spec.where_sql()}
        """,
        spec.params(),
    ).fetchone()

    def value(index: int) -> float | None:
        v = row[index]
        return float(v) if v is not None else None

    return SelectionSummary(
        n_events=int(row[0] or 0),
        n_hits=int(row[1] or 0),
        n_events_no_d=None,
        e_dep_total=float(row[2] or 0.0),
        d_mean=None, d_median=None, d_sd=None, d_min=None, d_max=None,
        e1_mean=value(3),
        e2_mean=None,
        centroid_a={"x": value(4), "y": value(5), "z": value(6)},
        centroid_b=None,
        dataset_separation_mm=None,
        label="Dataset centroid (per-event average)",
    )


def summarise(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
) -> SelectionSummary:
    """Summarise the selected events. Roughly 20 000 rows; sub-millisecond."""
    table = quote(naming.event_table(record.table_name))
    showers = showers_mod.of(record)
    if len(showers) == 1:
        return _summarise_single(con, table, spec, showers[0])
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

    Over every shower of the experiment: a single-shower experiment reports
    ``r_a`` and a null ``r_b``.
    """
    table = quote(naming.event_table(record.table_name))
    showers = showers_mod.of(record)
    sums = ",\n            ".join(
        f"avg(cos(CAST({s.phi} AS DOUBLE))), avg(sin(CAST({s.phi} AS DOUBLE))), "
        f"avg(CAST({s.theta} AS DOUBLE))"
        for s in showers
    )
    defined = " AND ".join(f"{s.phi} IS NOT NULL" for s in showers)
    row = con.execute(
        f"""
        SELECT
            count(*) AS n,
            {sums}
        FROM {table}
        WHERE {spec.where_sql()} AND {defined}
        """,
        spec.params(),
    ).fetchone()

    def resultant(cos_mean, sin_mean) -> float | None:
        if cos_mean is None or sin_mean is None:
            return None
        return float(math.hypot(float(cos_mean), float(sin_mean)))

    r: dict[str, float | None] = {}
    theta: dict[str, float | None] = {}
    for j, s in enumerate(showers):
        r[s.key] = resultant(row[1 + 3 * j], row[2 + 3 * j])
        theta[s.key] = float(row[3 + 3 * j]) if row[3 + 3 * j] is not None else None

    return {
        "n": int(row[0] or 0),
        "r_a": r.get("a"),
        "r_b": r.get("b"),
        "theta_a_mean": theta.get("a"),
        "theta_b_mean": theta.get("b"),
        "note": (
            "Incident azimuth is near-uniform over this selection, so no single "
            "averaged trajectory is drawn; it would point in an arbitrary "
            "direction. The solid lines are the centres of deposited energy per "
            "depth layer, measured from the displayed data: a property of the "
            "summed picture, not a direction."
        ),
    }


def pointing(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
) -> dict[str, Any]:
    """Where the incident directions point, measured against each shower's own position.

    The azimuth is near-uniform over the detector face, but not random: on
    the production file every shower's incident direction points back at the
    detector origin - ``phi = atan2(y, x)`` with a resultant length of 1.000,
    and ``tan(theta) * z = r`` (the 3-D centroid's ``r / tan theta`` is
    3,860 mm against its own z of 3,892 mm). The residual between the
    direction and the radial line through the centroid is 1.8 degrees SD. The
    azimuth is uniform only because the entry positions are, which is what
    licenses the windowed ensemble axis (``query/window_axis.py``) and what
    part of the D-frame's slope dispersion is made of.

    Returns, per shower, the residual's mean and SD in degrees, the median
    ``r / tan theta`` beside the median centroid depth, and N.
    """
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    showers = showers_mod.of(record)
    # Every shower slot is present; one a single-shower experiment lacks is null.
    out: dict[str, Any] = {"a": None, "b": None}
    for s in showers:
        th, ph = f"CAST({s.theta} AS DOUBLE)", f"CAST({s.phi} AS DOUBLE)"
        cx, cy, cz = centroid_columns(s)
        row = con.execute(
            f"""
            WITH ev AS (
                SELECT {th} AS th, {ph} AS ph, {cx} AS cx, {cy} AS cy, {cz} AS cz
                FROM {table}
                WHERE {where} AND {s.theta} IS NOT NULL AND {s.phi} IS NOT NULL
                  AND {centroid_defined(s)}
            ), res AS (
                SELECT atan2(sin(ph - atan2(cy, cx)), cos(ph - atan2(cy, cx))) AS r,
                       CASE WHEN tan(th) > 0 THEN sqrt(cx * cx + cy * cy) / tan(th) END AS zs, cz
                FROM ev
            )
            SELECT count(*), avg(r), stddev_samp(r), median(zs), median(cz) FROM res
            """,
            spec.params(),
        ).fetchone()
        n = int(row[0] or 0)

        def deg(value):
            return math.degrees(float(value)) if value is not None and math.isfinite(float(value)) else None

        out[s.key] = {
            "n": n,
            "mean_deg": deg(row[1]) if n else None,
            "sd_deg": deg(row[2]) if n >= 2 else None,
            "source_z_mm": float(row[3]) if row[3] is not None else None,
            "centroid_z_mm": float(row[4]) if row[4] is not None else None,
        }
    parts = []
    for s in showers:
        block = out[s.key]
        # Two showers are told apart by letter; a single shower needs no name.
        name = f"{s.key.upper()}: " if len(showers) > 1 else ""
        if block["n"] >= 2 and block["sd_deg"] is not None:
            source = (f", r / tan θ = {block['source_z_mm']:,.0f} mm against a centroid depth of "
                      f"{block['centroid_z_mm']:,.0f} mm") if block["source_z_mm"] is not None else ""
            parts.append(f"{name}{block['mean_deg']:+.1f}° ± {block['sd_deg']:.1f}° SD over N = {block['n']:,}{source}")
        elif block["n"] == 1:
            parts.append(f"{name}one event, residual {block['mean_deg']:+.1f}°" if name
                         else f"{block['mean_deg']:+.1f}° for its one event")
    out["note"] = typographic(
        "Incident directions point at the detector origin: against the radial line through each "
        "shower's 3-D centroid the residual is " + "; ".join(parts) + ". The azimuth is uniform over the "
        "face only because the entry points are, so the showers entering one window share a direction: "
        "zoom a depth panel and the ensemble axis of the events entering its window is drawn."
    ) if parts else "Too few events to measure where the incident directions point."
    return out


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
    the projections response rather than costing a second round trip. A
    single-shower experiment's entries carry ``a`` only.
    """
    table = quote(naming.event_table(record.table_name))
    showers = showers_mod.of(record)
    first = showers[0]
    columns = ",\n               ".join(
        f"CAST({s.theta} AS DOUBLE), CAST({s.phi} AS DOUBLE), {', '.join(centroid_columns(s))}"
        for s in showers
    )
    rows = con.execute(
        f"""
        SELECT event_number,
               {columns}
        FROM {table}
        WHERE {spec.where_sql()}
          AND {first.theta} IS NOT NULL AND {first.phi} IS NOT NULL
          AND {centroid_defined(first)}
        ORDER BY event_number
        LIMIT {int(limit)}
        """,
        spec.params(),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        entry: dict[str, Any] = {"event": int(r[0])}
        for j, s in enumerate(showers):
            theta, phi, x, y, z = r[1 + 5 * j: 6 + 5 * j]
            # The first shower is gated above; shower B can be undefined
            # independently of A.
            if j == 0 or all(v is not None for v in (theta, phi, x, y, z)):
                entry[s.key] = {"theta": theta, "phi": phi, "x": x, "y": y, "z": z}
        out.append(entry)
    return out


def excluded_undefined_d(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord
) -> int:
    """Total events in this experiment with no defined A-B separation."""
    table = quote(naming.event_table(record.table_name))
    row = con.execute(f"SELECT count(*) FROM {table} WHERE d IS NULL").fetchone()
    return int(row[0] or 0)
