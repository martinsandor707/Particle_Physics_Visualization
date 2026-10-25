"""SQL fragments the hit-level physics scans share (C1 statistics, C4 distributions, C8 correlations).

Every hit scan needs the same few things, built here once:

* each shower's per-event attributes - momentum, its bin, θ, φ - as a CTE over
  the event table (:func:`shower_attr_cte`), one row per (event, shower), and
  the join that takes a projected hit to its own shower (:func:`own_shower_join`:
  an 'A+B' row is counted with B, as everywhere);
* a hit's coordinates in a frame (:func:`frame_xyz`): Local (u, v, w) and the
  per-shower translated frame straight from the projection table, and the
  laboratory frame through the measured lattice coordinate arrays - never a
  bin index times a pitch, which the irregular x lattice forbids (CLAUDE.md
  section 2);
* the event-group key of the grouped jackknife (:func:`group_key`).

Every column name comes from ``query/showers.py`` or the projection table's
DDL: a request string never becomes SQL.
"""

from __future__ import annotations

from typing import Any

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..stats import jackknife
from .filters import FilterSpec
from .showers import ShowerColumns

#: The frames a hit scan can read, by their request name.
FRAMES: tuple[str, ...] = ("lab", "trans", "local")

#: ``(axis symbols, unit)`` of each frame's coordinates, for labels.
FRAME_SYMBOLS: dict[str, tuple[str, str, str]] = {
    "lab": ("x", "y", "z"),
    "trans": ("Δx", "Δy", "Δz"),
    "local": ("u", "v", "w"),
}


def proj_table(record: ExperimentRecord, sampled: bool = False) -> str:
    """The quoted projection table (the 10% sample when ``sampled``)."""
    return quote(naming.proj_table(record.table_name, sampled=sampled))


def shower_attr_cte(
    record: ExperimentRecord,
    spec: FilterSpec,
    showers: tuple[ShowerColumns, ...],
    attrs: tuple[tuple[str, str], ...] = (("p", "momentum"), ("mb", "momentum_bin"),
                                          ("th", "theta"), ("ph", "phi")),
    name: str = "sh",
) -> str:
    """``sh(event_number, b, <alias> ...)``: each selected shower's per-event attributes.

    ``attrs`` pairs an output alias with a :class:`ShowerColumns` field name;
    numeric attributes are cast to DOUBLE except the integer momentum bin. A
    shower that deposited nothing in an event has no row. The selection's
    named parameters (``spec.params()``) must be bound by the caller.
    """
    event = quote(naming.event_table(record.table_name))
    parts = []
    for s in showers:
        columns = ", ".join(
            f"CAST({getattr(s, field)} AS {'INTEGER' if field == 'momentum_bin' else 'DOUBLE'}) "
            f"AS {alias}"
            for alias, field in attrs)
        parts.append(f"SELECT event_number, {s.b} AS b, {columns} FROM {event} "
                     f"WHERE {spec.where_sql()} AND {s.present_sql}")
    return f"{name} AS (\n        " + "\n        UNION ALL\n        ".join(parts) + "\n    )"


def own_shower_join(p: str = "p", s: str = "s") -> str:
    """The join condition from projected hit ``p`` to its own shower's row ``s``."""
    return (f"{s}.event_number = {p}.event_number "
            f"AND {s}.b = CASE WHEN {p}.org = {ddl.ORIGIN_A} THEN 0 ELSE 1 END")


def origin_filter(showers: tuple[ShowerColumns, ...]) -> str:
    """The projection predicate keeping only the selected showers' hits (alias ``p``)."""
    clauses = [s.origin_sql for s in showers if s.origin_sql]
    if not clauses or "TRUE" in clauses:
        return "TRUE"
    return "(" + " OR ".join(clauses) + ")"


def layer_pitch(record: ExperimentRecord) -> float:
    """The sampling-layer pitch the experiment was ingested with, in mm."""
    if record.frame_bounds is not None:
        return float(record.frame_bounds.layer_pitch_mm)
    pitch = (record.ingest_report or {}).get("layer_pitch_mm")
    if pitch:
        return float(pitch)
    if record.lattice is not None:
        return float(record.lattice.z.mean_pitch)
    raise ValueError(f"experiment {record.table_name!r} has no layer pitch")


def frame_xyz(coord_system: str, record: ExperimentRecord,
              p: str = "p") -> tuple[tuple[str, str, str], dict[str, Any]]:
    """``((x, y, z) SQL, params)`` of a projected hit's coordinates in ``coord_system``, in mm.

    *local*: ``xl, yl, zl`` (u, v, w). *trans*: ``xt, yt`` and the own-shower
    layer ``kt`` times the pitch. *lab*: the measured lattice coordinates of
    the hit's ordinals, bound as list parameters ``$lab_x/$lab_y/$lab_z``.
    """
    if coord_system == "local":
        return (f"CAST({p}.xl AS DOUBLE)", f"CAST({p}.yl AS DOUBLE)",
                f"CAST({p}.zl AS DOUBLE)"), {}
    if coord_system == "trans":
        pitch = layer_pitch(record)
        return (f"CAST({p}.xt AS DOUBLE)", f"CAST({p}.yt AS DOUBLE)",
                f"CAST({p}.kt AS DOUBLE) * {pitch!r}"), {}
    if coord_system == "lab":
        lattice = record.lattice
        if lattice is None:
            raise ValueError(f"experiment {record.table_name!r} has no lattice")
        params = {
            "lab_x": [float(v) for v in lattice.x.coords],
            "lab_y": [float(v) for v in lattice.y.coords],
            "lab_z": [float(v) for v in lattice.z.coords],
        }
        return (f"list_extract($lab_x, {p}.ix + 1)", f"list_extract($lab_y, {p}.iy + 1)",
                f"list_extract($lab_z, {p}.iz + 1)"), params
    raise ValueError(f"unknown frame {coord_system!r}")


def group_key(n_events: int, p: str = "p") -> tuple[str, int]:
    """``(SQL, G)``: the jackknife group of a hit's event, and the number of groups.

    With no more events than ``jackknife.MAX_GROUPS`` every event is its own
    group - a delete-one-event jackknife; above, the event number modulo G,
    taken non-negative so a negative event number cannot open a group of its own.
    """
    groups = jackknife.n_groups(n_events)
    if n_events <= jackknife.MAX_GROUPS:
        return f"{p}.event_number", groups
    return f"((({p}.event_number % {groups}) + {groups}) % {groups})", groups
