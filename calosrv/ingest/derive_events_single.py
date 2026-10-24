"""The per-event table of a single-shower hit experiment.

One shower per event, stored under the shower-A names the two-shower table
uses where the meaning is the same (``e1``, ``theta_a``, ``cax``, Group-1
``*_a``), so selections, the response panels and the per-shower queries read
both kinds through one vocabulary (``query/showers.py``).

Three independent scans of the sorted archive, as for two-shower data: the
event aggregate (kinematics, centroids, P0, the species counts C11 needs and
the per-event consistency checks), the cell census, and the Group-1 sums.

Every per-event constant (momentum, angles, bin) is read with ``max()`` and
its constancy within the event is checked (``chk_pt_spread``), as is P0 (the
entry point recovered as ``x - x_trans``, ``chk_p0_spread``). The producer's
momentum bin is kept as written; ``chk_bin_rule`` counts the rows where it is
not ⌊p⌋, which verification reports.
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb

from ..db import group1, naming
from ..db.ddl import EVENT_SINGLE_COLUMNS, create_event_table, drop_table, group1_columns
from ..db.naming import quote
from .derive_events import _spread
from .derive_proj import keep_predicate

log = logging.getLogger(__name__)

#: Columns the census fills.
CENSUS_COLUMNS = ("n_cells", "n_dup_cells", "n_cells_a")

#: Every row is the one shower's.
MEMBERS: dict[str, str | None] = {"a": None}


def event_expressions() -> dict[str, str]:
    """SQL for every event-aggregate column of the single-shower table."""
    keep = "TRUE"
    e: dict[str, str] = {
        "event_number": "event_number",
        "e1": "max(incoming_momentum)",
        "e1_bin": "max(incoming_momentum_bin)",
        "theta_a": "max(incoming_theta)",
        "phi_a": "max(incoming_phi)",
    }
    # Energy-weighted 3-D centroids, as core.py:491-497 computes them.
    for suffix, cols in (("", ("x", "y", "z")), ("_t", ("x_trans", "y_trans", "z_trans")),
                         ("_l", ("x_local", "y_local", "z_local"))):
        for axis, col in zip("xyz", cols):
            e[f"ca{axis}{suffix}"] = f"sum(energy * CAST({col} AS DOUBLE)) / sum(energy)"
    for axis in "xyz":
        e[f"p0a{axis}"] = f"avg(CAST({axis} AS DOUBLE) - CAST({axis}_trans AS DOUBLE))"
    e.update({
        "n_hits": "count(*)",
        "n_a_rows": "count(*)",
        "e_dep": "sum(energy)",
        "n_primary_rows": "count(*) FILTER (WHERE is_secondary = 0)",
        "e_primary": "coalesce(sum(energy) FILTER (WHERE is_secondary = 0), 0.0)",
        "primary_type": "arg_max(particle_type, energy) FILTER (WHERE is_secondary = 0)",
        "n_null_species": "count(*) FILTER (WHERE particle_type IS NULL)",
        "n_parent_mismatch": "count(*) FILTER (WHERE (parent_type IS NULL) <> (is_secondary = 0))",
        "chk_p0_spread": "greatest(" + ", ".join(
            _spread(f"(CAST({axis} AS DOUBLE) - CAST({axis}_trans AS DOUBLE))", keep)
            for axis in "xyz") + ")",
        "chk_pt_spread": "greatest(" + ", ".join(
            _spread(c, keep) for c in ("incoming_momentum", "incoming_theta", "incoming_phi",
                                       "CAST(incoming_momentum_bin AS DOUBLE)")) + ")",
        "chk_bin_rule": ("count(*) FILTER (WHERE incoming_momentum_bin "
                         "<> CAST(floor(incoming_momentum) AS INTEGER))"),
    })
    return e


def build(con: duckdb.DuckDBPyConnection, name: str, source: str) -> int:
    """Create ``event_<name>`` from the archive relation ``source``; returns the event count."""
    event_physical = naming.event_table(name)
    con.execute(drop_table(event_physical))
    con.execute(create_event_table(event_physical, EVENT_SINGLE_COLUMNS))

    names = [n for n, _ in EVENT_SINGLE_COLUMNS]
    expressions = event_expressions()
    group1_names = {n for n, _ in group1_columns(("a",))}
    missing = [c for c in names
               if c not in expressions and c not in CENSUS_COLUMNS and c not in group1_names]
    assert not missing, f"no source for event columns {missing}"
    select = ", ".join(
        f"coalesce(c.{col}, 0) AS {col}" if col in CENSUS_COLUMNS
        else f"g.{col}" if col in group1_names
        else f"m.{col}"
        for col in names
    )
    aggregate = ",\n            ".join(f"{sql} AS {col}" for col, sql in expressions.items())
    keep = keep_predicate(origin=False)

    log.info("Building %s (single-shower per-event statistics)", event_physical)
    con.execute(
        f"""
        INSERT INTO {quote(event_physical)} ({', '.join(names)})
        SELECT {select}
        FROM (
            SELECT
            {aggregate}
            FROM {source}
            WHERE {keep}
            GROUP BY event_number
        ) m
        LEFT JOIN (
            -- One row per (event, cell) is the file's contract; n_dup_cells
            -- counts the cells that break it.
            SELECT event_number,
                   count(*)                       AS n_cells,
                   count(*) FILTER (WHERE k > 1)  AS n_dup_cells,
                   count(*)                       AS n_cells_a
            FROM (
                SELECT event_number, cellID, count(*) AS k
                FROM {source} WHERE {keep}
                GROUP BY event_number, cellID
            )
            GROUP BY event_number
        ) c USING (event_number)
        LEFT JOIN (
            {group1.scan_sql(source, keep, MEMBERS)}
        ) g USING (event_number)
        ORDER BY m.event_number
        """
    )
    n_events = int(con.execute(f"SELECT count(*) FROM {quote(event_physical)}").fetchone()[0])
    log.info("%s holds %s events", event_physical, f"{n_events:,}")
    return n_events


def calibration(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, tuple[float, float | None]]:
    """The sampling-fraction calibration ``c = Σ p / Σ E_dep`` over every event.

    Sum before divide, as for two-shower data (``derive_events.calibration``),
    so the containment scatter the resolution measures is not normalised
    away. One shower, so one constant; the second slot is ``None``.
    """
    row = con.execute(
        f"SELECT sum(e1), sum(e_dep) FROM {quote(naming.event_table(name))}"
    ).fetchone()
    p, dep = (float(v or 0.0) for v in row)
    c = p / dep if dep > 0 else float("nan")
    log.info("Sampling-fraction calibration: c=%.3f", c)
    return {"all": (c, None)}


def species_facts(con: duckdb.DuckDBPyConnection, name: str, top: int = 6) -> dict[str, Any]:
    """The particle species of the hit cells, for the catalogue and the species views.

    The ``top`` species by energy are named; the rest are "other". Counts are
    of cells (rows), each with one attributed particle - the file never splits
    a cell's energy by species.
    """
    proj = quote(naming.proj_table(name))
    rows = con.execute(
        f"""
        SELECT coalesce(particle_type, '(none)') AS species, count(*) AS cells,
               sum(energy) AS energy, count(*) FILTER (WHERE is_secondary = 0) AS primary_cells
        FROM {proj} GROUP BY 1 ORDER BY energy DESC, species
        """
    ).fetchall()
    total = sum(float(r[2] or 0.0) for r in rows) or 1.0
    events = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE n_primary_rows = 0) "
        f"FROM {quote(naming.event_table(name))}"
    ).fetchone()
    return {
        "n_types": len(rows),
        "top": [{"name": r[0], "cells": int(r[1]), "energy_fraction": float(r[2] or 0.0) / total,
                 "primary_cells": int(r[3])} for r in rows[:top]],
        "primary": {"definition": "is_secondary = 0",
                    "events": int(events[0] or 0),
                    "events_without": int(events[1] or 0)},
    }
