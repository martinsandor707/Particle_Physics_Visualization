"""The event table of an aggregated (event-features-only) experiment.

The 59-column v3 aggregate is ``core.calc_all_features_v3`` already applied:
one row per event, seventeen spatial features in each of three frames, the
densities, and the kinematics. Nothing is recomputed. The base columns take
the names every other kind uses - ``event_number``, ``e1``, ``theta_a``,
``phi_a``, ``e1_bin``, ``n_hits``, ``e_dep`` - so selections and the response
panels read this table like any other; the features keep their file names.

Three things are checked or normalised on the way in:

* **Duplicate ids are refused** before any table is created: two rows with
  one ``event_id`` would be one event counted twice in every statistic.
* **Non-finite values become NULL**, counted per column, never zero-filled.
* **The trailing ``energy`` column is a label**, 1{p ≥ 2 GeV} on the
  electron file, not an energy. It is stored as ``energy_class`` when it
  holds small whole numbers; verification says what rule it follows.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import duckdb

from ..db import naming
from ..db.ddl import EVENT_FEATURE_COLUMNS, create_event_table, drop_table
from ..db.naming import quote
from ..errors import IngestError

log = logging.getLogger(__name__)

#: Derived name -> the aggregate file's column.
RENAMED: dict[str, str] = {
    "event_number": "event_id",
    "e1": "incoming_momentum",
    "theta_a": "incoming_theta",
    "phi_a": "incoming_phi",
    "e1_bin": "incoming_momentum_bin",
    "n_hits": "num_hits",
    "e_dep": "total_hit_energy",
}


@dataclass
class FeatureReport:
    """What the feature table build did to the file's values."""

    total_rows: int = 0
    kept_rows: int = 0
    non_finite: dict[str, int] = field(default_factory=dict)

    @property
    def removed(self) -> int:
        return self.total_rows - self.kept_rows

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["removed"] = self.removed
        return data


def _source_column(name: str) -> str:
    if name == "energy_class":
        return "energy"
    return RENAMED.get(name, name)


def build(con: duckdb.DuckDBPyConnection, name: str, source: str) -> tuple[int, FeatureReport]:
    """Create ``event_<name>`` from the archive relation ``source``."""
    total, duplicates = con.execute(
        f"SELECT count(*), count(*) - count(DISTINCT event_id) FROM {source}"
    ).fetchone()
    if duplicates:
        raise IngestError(
            f"event_id is not unique in this file: {int(duplicates):,} row(s) repeat an id "
            "already present. Each event must appear once; the file was not ingested.",
            repeated=int(duplicates),
        )

    doubles = [n for n, t in EVENT_FEATURE_COLUMNS if t == "DOUBLE"]
    counts = con.execute(
        "SELECT " + ", ".join(
            f"count(*) FILTER (WHERE {quote(_source_column(n))} IS NOT NULL "
            f"AND NOT isfinite({quote(_source_column(n))}))" for n in doubles)
        + f" FROM {source}"
    ).fetchone()
    report = FeatureReport(total_rows=int(total), kept_rows=int(total),
                           non_finite={n: int(c) for n, c in zip(doubles, counts) if c})

    event_physical = naming.event_table(name)
    con.execute(drop_table(event_physical))
    con.execute(create_event_table(event_physical, EVENT_FEATURE_COLUMNS))
    names = [n for n, _ in EVENT_FEATURE_COLUMNS]
    select = []
    for column, sql_type in EVENT_FEATURE_COLUMNS:
        src = quote(_source_column(column))
        if column == "energy_class":
            select.append(f"CASE WHEN {src} = round({src}) AND {src} BETWEEN 0 AND 255 "
                          f"THEN CAST({src} AS UTINYINT) END")
        elif sql_type == "DOUBLE":
            select.append(f"CASE WHEN isfinite({src}) THEN CAST({src} AS DOUBLE) END")
        else:
            select.append(f"CAST({src} AS {sql_type.split()[0]})")
    log.info("Building %s (event features as the file gives them)", event_physical)
    con.execute(
        f"INSERT INTO {quote(event_physical)} ({', '.join(names)}) "
        f"SELECT {', '.join(select)} FROM {source} ORDER BY event_id"
    )
    if report.non_finite:
        log.warning("Non-finite feature values stored as NULL: %s", report.non_finite)
    n_events = int(con.execute(f"SELECT count(*) FROM {quote(event_physical)}").fetchone()[0])
    return n_events, report


def calibration(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, tuple[float, float | None]]:
    """``c = Σ p / Σ E_dep`` over the file's events (sum before divide)."""
    row = con.execute(
        f"SELECT sum(e1), sum(e_dep) FROM {quote(naming.event_table(name))}"
    ).fetchone()
    p, dep = (float(v or 0.0) for v in row)
    return {"all": (p / dep if dep > 0 else float("nan"), None)}
