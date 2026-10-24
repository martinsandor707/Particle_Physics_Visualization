"""``layers_<name>``: per-(event, shower, own-shower layer) sums.

One row per populated layer of each shower, from the archive: the energy, the
cell count, and the energy-weighted first and second moments of the Local
transverse position (u, v) = (``x_local``, ``y_local``) and of its radius
ρ = √(u² + v²). The layer is the shower's own, ``kt = round(z_trans /
pitch)``, counted from its first populated layer exactly as the projection
table stores it. Within one shower a cell has at most one row (checked:
``n_dup_cells`` single-shower, ``chk_bad_split`` two-shower), so ``n_cells``
is a row count.
"""

from __future__ import annotations

import logging

import duckdb

from ..db import naming
from ..db.ddl import KIND_TWO_SHOWER, LAYERS_COLUMNS, create_layers_table, drop_table
from ..db.naming import quote
from .derive_proj import keep_predicate

log = logging.getLogger(__name__)


def shower_sql(kind: str) -> str:
    """The shower index of an archive row: 0 = A, 1 = B ('A+B' rows with B)."""
    if kind == KIND_TWO_SHOWER:
        return "CASE WHEN particle_origin = 'A' THEN 0 ELSE 1 END"
    return "0"


def build(con: duckdb.DuckDBPyConnection, name: str, source: str, layer_pitch_mm: float,
          kind: str = KIND_TWO_SHOWER) -> int:
    """Create ``layers_<name>``; returns its row count."""
    physical = naming.layers_table(name)
    con.execute(drop_table(physical))
    con.execute(create_layers_table(physical))
    u, v = "CAST(x_local AS DOUBLE)", "CAST(y_local AS DOUBLE)"
    log.info("Building %s (per-layer sums)", physical)
    con.execute(
        f"""
        INSERT INTO {quote(physical)} ({', '.join(n for n, _ in LAYERS_COLUMNS)})
        SELECT event_number,
               CAST({shower_sql(kind)} AS UTINYINT) AS shower,
               CAST(round(CAST(z_trans AS DOUBLE) / {float(layer_pitch_mm)!r}) AS UTINYINT) AS kt,
               sum(energy), CAST(count(*) AS INTEGER),
               sum(energy * {u}), sum(energy * {v}),
               sum(energy * sqrt({u} * {u} + {v} * {v})),
               sum(energy * ({u} * {u} + {v} * {v}))
        FROM {source}
        WHERE {keep_predicate(origin=kind == KIND_TWO_SHOWER)}
        GROUP BY ALL
        ORDER BY event_number, shower, kt
        """
    )
    rows = int(con.execute(f"SELECT count(*) FROM {quote(physical)}").fetchone()[0])
    log.info("%s holds %s rows", physical, f"{rows:,}")
    return rows
