"""Ingest-time checks of the per-shower entry point and the D-frame anchors.

Two measurements the frames rest on, taken on every ingest and written into
the verification report:

**What P0 is.** The per-shower frames are built on each shower's entry point
P0, recovered from the file as ``x - x_trans`` and verified to be one point
per shower (``verify.py: p0_constancy``). That proves the translation is
rigid; it does not say what the point *is*. The documentation states the
reference notebook's rule - the energy-weighted ``(x, y)`` centroid of the
shower's first populated layer, at that layer's z - and this module computes
that centroid from the hits and compares it with P0. Measured on the
production file: 40 650 showers, largest residual 0.05 µm, so the rule holds
and the check fails above the rotation check's 0.01 mm tolerance. The 'A+B'
rows belong to both showers' first layer (``derive_events.py``) and are
counted on both sides, as the event table's P0 expressions count them.

**How far the two D-frame anchors sit apart.** The D-frame anchors each
shower on its 3-D centroid back-projected to the front face; the notebook's
origin is P0. Both are back-projected to the same face and their transverse
distance measured per shower, so the choice ``anchor=backprojected|p0`` on the
canonical frame is made against a number. Measured on the production file:
median 46 mm, p90 133 mm, 47% of showers more than one cell footprint apart.
"""

from __future__ import annotations

import math
from typing import Any

import duckdb

from ..db.naming import quote

#: Tolerance of the P0-definition check: the rotation check's, since both
#: compare a stated transform with the file's own numbers.
P0_DEFINITION_TOLERANCE_MM = 0.01

_SHOWERS = (("a", "particle_origin <> 'B'"), ("b", "particle_origin <> 'A'"))

#: The rows the producer's P0 can have been computed from: a finite position
#: and a positive, finite energy. Deliberately looser than the projection's
#: ``keep_predicate``: a row the sanitiser drops for a missing frame
#: coordinate still carried a position and an energy when P0 was computed,
#: and leaving it out would move the recomputed centroid for no reason. A row
#: whose position or energy is itself missing cannot be recovered, so a file
#: the sanitiser trimmed can leave the centroid unconfirmable - the caller
#: warns then rather than fails.
_USABLE = (
    "isfinite(x) AND isfinite(y) AND isfinite(z) AND energy IS NOT NULL AND isfinite(energy) "
    "AND energy > 0 AND particle_origin IN ('A', 'B', 'A+B')"
)


#: A single-shower file: every row is the one shower's, and there is no origin.
_SINGLE = (("a", "TRUE"),)
_USABLE_SINGLE = (
    "isfinite(x) AND isfinite(y) AND isfinite(z) AND energy IS NOT NULL AND isfinite(energy) "
    "AND energy > 0"
)


def p0_definition_residual(
    con: duckdb.DuckDBPyConnection, source: str, event_table: str, single: bool = False
) -> dict[str, Any]:
    """The largest |P0 - first-layer centroid| over every shower, in mm, per axis.

    One grouped scan of the archive per shower side: the shower's first
    populated layer ``z0 = min z``, the energy-weighted ``(x, y)`` centroid of
    its rows at that layer, compared with the event table's ``p0{a,b}{x,y,z}``
    (``p0a*`` only for a single-shower experiment).
    Returns ``{"max_mm": float | None, "n_showers": int, "x": ..., "y": ..., "z": ...}``.
    """
    sides, usable = (_SINGLE, _USABLE_SINGLE) if single else (_SHOWERS, _USABLE)
    parts = []
    for shower, where in sides:
        parts.append(f"""
        SELECT event_number, '{shower}' AS s, CAST(x AS DOUBLE) AS x, CAST(y AS DOUBLE) AS y,
               CAST(z AS DOUBLE) AS z, energy
        FROM {source} WHERE {usable} AND {where}""")
    rows_sql = " UNION ALL ".join(parts)
    p0_b = "" if single else f"""
            UNION ALL
            SELECT event_number, 'b', p0bx, p0by, p0bz FROM {quote(event_table)}"""
    row = con.execute(
        f"""
        WITH s AS ({rows_sql}),
        first AS (SELECT event_number, s, min(z) AS z0 FROM s GROUP BY event_number, s),
        cen AS (
            SELECT s.event_number, s.s, first.z0,
                   sum(x * energy) / sum(energy) AS cx, sum(y * energy) / sum(energy) AS cy
            FROM s JOIN first USING (event_number, s) WHERE s.z = first.z0
            GROUP BY s.event_number, s.s, first.z0
        ),
        p0 AS (
            SELECT event_number, 'a' AS s, p0ax AS px, p0ay AS py, p0az AS pz FROM {quote(event_table)}{p0_b}
        )
        SELECT count(*), max(abs(px - cx)), max(abs(py - cy)), max(abs(pz - z0))
        FROM cen JOIN p0 USING (event_number, s)
        WHERE px IS NOT NULL
        """
    ).fetchone()
    n = int(row[0] or 0)
    axes = {axis: (float(v) if v is not None else None) for axis, v in zip("xyz", row[1:])}
    finite = [v for v in axes.values() if v is not None and math.isfinite(v)]
    worst = max(finite) if finite else None
    if any(v is not None and not math.isfinite(v) for v in axes.values()):
        worst = float("nan")
    return {"max_mm": worst, "n_showers": n, **axes}


def anchor_residual(
    con: duckdb.DuckDBPyConnection, event_table: str, z_front: float, footprint_mm: float
) -> dict[str, Any]:
    """The transverse distance between the two anchor definitions, per shower, over the dataset.

    Both the 3-D centroid and P0 are back-projected to the front face
    ``z_front`` along the shower's incident direction. Returns the median, the
    90th percentile and the count above ``footprint_mm`` per shower, and the
    number of events measured.
    """
    table = quote(event_table)
    row = con.execute(
        f"""
        WITH d AS (
            SELECT
                sqrt(power((cax - (caz - $zf) * tan(theta_a) * cos(phi_a))
                           - (p0ax - (p0az - $zf) * tan(theta_a) * cos(phi_a)), 2)
                   + power((cay - (caz - $zf) * tan(theta_a) * sin(phi_a))
                           - (p0ay - (p0az - $zf) * tan(theta_a) * sin(phi_a)), 2)) AS da,
                sqrt(power((cbx - (cbz - $zf) * tan(theta_b) * cos(phi_b))
                           - (p0bx - (p0bz - $zf) * tan(theta_b) * cos(phi_b)), 2)
                   + power((cby - (cbz - $zf) * tan(theta_b) * sin(phi_b))
                           - (p0by - (p0bz - $zf) * tan(theta_b) * sin(phi_b)), 2)) AS db
            FROM {table}
            WHERE cax IS NOT NULL AND p0ax IS NOT NULL AND cbx IS NOT NULL AND p0bx IS NOT NULL
              AND theta_a IS NOT NULL AND theta_b IS NOT NULL
        )
        SELECT count(*),
               median(da), quantile_cont(da, 0.9), count(*) FILTER (WHERE da > $fp),
               median(db), quantile_cont(db, 0.9), count(*) FILTER (WHERE db > $fp)
        FROM d
        """,
        {"zf": float(z_front), "fp": float(footprint_mm)},
    ).fetchone()

    def f(value: Any) -> float | None:
        return float(value) if value is not None and math.isfinite(float(value)) else None

    return {
        "n_events": int(row[0] or 0),
        "footprint_mm": float(footprint_mm),
        "a": {"median_mm": f(row[1]), "p90_mm": f(row[2]), "over_footprint": int(row[3] or 0)},
        "b": {"median_mm": f(row[4]), "p90_mm": f(row[5]), "over_footprint": int(row[6] or 0)},
        "definition": (
            "transverse distance at the front face between the back-projected 3-D centroid "
            "(the D-frame's default anchor) and the back-projected first-layer entry point "
            "P0 (the reference notebook's origin), per shower"
        ),
    }
