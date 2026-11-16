"""The particle filter: which events the event pickers offer.

A reader wants "a 5-6 GeV particle at 10-15 degrees" drawn in 2-D and 3-D.
The kinematic filter (``query/filters.py``) cuts per shower - E1 on shower A,
E2 on shower B - and has no polar angle, so this module adds one filter with
no A/B choice: up to four inclusive bounds, the incident momentum ``p`` in GeV
and the incident polar angle ``theta`` in degrees, each ``None`` for
unbounded. The filter is **active** when any bound is set.

**A shower matches** when it deposited energy (``ShowerColumns.present_sql``)
and every set bound holds for its own momentum and polar angle columns,
theta compared in radians (converted once, here). With no bound set, every
shower with a deposit matches.

**The pool** - the candidates - is the selection (``FilterSpec.where_sql``)
AND the frame gate (``capabilities.frame_gate``: a defined separation for two
showers, an incident direction and an entry point for one) AND, only when the
filter is active, at least one matching shower. With no bound set it is the
selection AND the frame gate, which is exactly the population the pick rules
have always drawn from. Pick for me, Most tilted, Densest and previous / next
all draw from it; the ensemble panels never read it.

**The basis** is what the pool is drawn from (``basis`` on ``GET /api/event``,
``/api/event/pick`` and ``/api/event/candidates``; ``api/deps.py``
``resolve_basis``). ``selection``, the API default, is the pool above, so
every response that names no basis is what it was. ``experiment`` replaces
the selection with the whole experiment (``filters.unbounded``: no E1, E2 or
D clause), so the pool is every event of the experiment AND the frame gate
AND, when active, a matching shower; an E1/E2/D bound sent with it is
refused, never ignored. Both pages use it (Martin, 2026-11-16). The basis is
read off the spec (:func:`basis_of`), so the SQL and the words cannot
disagree: under ``experiment`` the sentences say "events of the experiment"
and "The experiment holds", every block that places the pool carries
``"basis": "experiment"``, ``n_selection`` is the experiment's event count
and ``in_selection`` is true for every event it holds. Under ``selection``
no block carries ``basis``.

Column names come only from ``query/showers.py``; no request string reaches
SQL. The bounds travel as named parameters ``particle_p_min``,
``particle_p_max``, ``particle_theta_min`` and ``particle_theta_max`` (the
angle in radians), and only the bounds that are set appear in the SQL and in
the parameters, because DuckDB refuses a named parameter the SQL does not use.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..errors import NotFoundError, ValidationError
from ..text import typographic
from . import capabilities
from . import showers as showers_mod
from .filters import FilterSpec
from .showers import ShowerColumns

#: The largest polar angle a bound may name, in degrees.
THETA_MAX_DEG = 180.0

#: The parameter names, in the order the bounds are written.
PARAM_P_MIN = "particle_p_min"
PARAM_P_MAX = "particle_p_max"
PARAM_THETA_MIN = "particle_theta_min"
PARAM_THETA_MAX = "particle_theta_max"
PARAMS: tuple[str, ...] = (PARAM_P_MIN, PARAM_P_MAX, PARAM_THETA_MIN, PARAM_THETA_MAX)

#: The en dash between the two ends of an interval.
EN_DASH = "–"

#: The bases of the pool: the E1/E2/D selection (the API default, today's pool) or the whole
#: experiment (both pages' event pickers).
BASIS_SELECTION = "selection"
BASIS_EXPERIMENT = "experiment"
BASES: tuple[str, ...] = (BASIS_SELECTION, BASIS_EXPERIMENT)


def basis_of(spec: FilterSpec) -> str:
    """The basis a spec stands for: the whole experiment's (``filters.unbounded``) or the selection's."""
    return BASIS_EXPERIMENT if spec.whole_experiment else BASIS_SELECTION


def with_basis(block: dict[str, Any], basis: str) -> dict[str, Any]:
    """``block`` led by ``"basis": "experiment"`` under the experiment basis; as it is under the selection."""
    return {"basis": basis, **block} if basis == BASIS_EXPERIMENT else block


def filter_echo(spec: FilterSpec) -> dict[str, Any]:
    """The ``filter`` a pool route echoes: the spec it used, plus ``basis`` under the experiment basis."""
    echo = spec.as_dict()
    if spec.whole_experiment:
        echo["basis"] = BASIS_EXPERIMENT
    return echo


def _rad(degrees: float | None) -> float | None:
    """Degrees to radians: the one conversion of the particle filter's angle."""
    return None if degrees is None else math.radians(float(degrees))


@dataclass(frozen=True)
class ParticleSpec:
    """Up to four inclusive bounds: ``p`` in GeV, ``theta`` in degrees; ``None`` is unbounded."""

    p_min: float | None = None
    p_max: float | None = None
    theta_min_deg: float | None = None
    theta_max_deg: float | None = None

    @property
    def active(self) -> bool:
        """Whether any bound is set."""
        return any(v is not None for v in (self.p_min, self.p_max, self.theta_min_deg, self.theta_max_deg))

    def _clauses(self, shower: ShowerColumns) -> list[str]:
        """The set bounds as comparisons on this shower's own columns."""
        out: list[str] = []
        if self.p_min is not None:
            out.append(f"{shower.momentum} >= ${PARAM_P_MIN}")
        if self.p_max is not None:
            out.append(f"{shower.momentum} <= ${PARAM_P_MAX}")
        if self.theta_min_deg is not None:
            out.append(f"{shower.theta} >= ${PARAM_THETA_MIN}")
        if self.theta_max_deg is not None:
            out.append(f"{shower.theta} <= ${PARAM_THETA_MAX}")
        return out

    def shower_sql(self, shower: ShowerColumns) -> str:
        """The event-table predicate "this shower matches": it deposited energy and every set bound holds.

        A NULL momentum or angle makes the predicate NULL, which every caller reads as no match.
        """
        return " AND ".join([f"({shower.present_sql})", *self._clauses(shower)])

    def pool_sql(self, record: ExperimentRecord) -> str:
        """At least one of the event's showers matches. Only written when the filter is active."""
        return " OR ".join(f"({self.shower_sql(s)})" for s in showers_mod.of(record))

    def params(self) -> dict[str, float]:
        """The set bounds as named parameters, the angle converted to radians."""
        out: dict[str, float] = {}
        for name, value in ((PARAM_P_MIN, self.p_min), (PARAM_P_MAX, self.p_max),
                            (PARAM_THETA_MIN, _rad(self.theta_min_deg)),
                            (PARAM_THETA_MAX, _rad(self.theta_max_deg))):
            if value is not None:
                out[name] = float(value)
        return out

    def as_dict(self) -> dict[str, Any]:
        """The echo every response carries: a null bound is an unset one."""
        return {
            "active": self.active,
            "p_gev": [self.p_min, self.p_max],
            "theta_deg": [self.theta_min_deg, self.theta_max_deg],
            "theta_rad": [_rad(self.theta_min_deg), _rad(self.theta_max_deg)],
        }

    def interval_text(self) -> str:
        """'p in 5.00–6.00 GeV and θ in 10.0–15.0° (0.175–0.262 rad)'; '' when no bound is set.

        The angle's bounds are written in degrees with radians beside them
        (``math.radians``, 3 decimals). The client's ``event_picker.js``
        ``intervalText`` writes the same string.
        """
        parts = []
        p = _interval("p", self.p_min, self.p_max, 2, " GeV")
        if p:
            parts.append(p)
        theta = _interval("θ", self.theta_min_deg, self.theta_max_deg, 1, "°")
        if theta:
            rad = _values(_rad(self.theta_min_deg), _rad(self.theta_max_deg), RAD_DIGITS, " rad")
            parts.append(f"{theta} ({rad})")
        return typographic(" and ".join(parts))


#: Decimals of the radians written beside a degree bound.
RAD_DIGITS = 3


def _values(lo: float | None, hi: float | None, digits: int, unit: str) -> str:
    """The set ends alone: '0.175–0.262 rad' for two, '0.175 rad' for one, '' for none."""
    ends = [f"{v:.{digits}f}" for v in (lo, hi) if v is not None]
    return f"{EN_DASH.join(ends)}{unit}" if ends else ""


def _interval(symbol: str, lo: float | None, hi: float | None, digits: int, unit: str) -> str:
    if lo is not None and hi is not None:
        return f"{symbol} in {_values(lo, hi, digits, unit)}"
    if lo is not None:
        return f"{symbol} ≥ {_values(lo, None, digits, unit)}"
    if hi is not None:
        return f"{symbol} ≤ {_values(None, hi, digits, unit)}"
    return ""


# --------------------------------------------------------------- validation --


def _got(value: float) -> str:
    return typographic(f"{value:g}")


def _momentum(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    # + 0.0 turns a -0.0 bound into 0.0, so it is never echoed or written with a sign.
    value = float(value) + 0.0
    if not math.isfinite(value) or value < 0.0:
        raise ValidationError(
            f"{name} must be a finite momentum of 0 GeV or more; got {_got(value)}.", field=name)
    return value


def _angle(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value) + 0.0
    if not math.isfinite(value) or not 0.0 <= value <= THETA_MAX_DEG:
        raise ValidationError(
            f"{name} must be a finite angle from 0° to {THETA_MAX_DEG:g}°; got {_got(value)}.", field=name)
    return value


def build(record: ExperimentRecord, p_min: float | None = None, p_max: float | None = None,
          theta_min: float | None = None, theta_max: float | None = None) -> ParticleSpec:
    """A validated particle filter: 422 naming the parameter, or the range for an inverted pair.

    ``record`` is the experiment the filter will run on; every bound applies to
    every kind with hits (a single shower's ``p`` is its incident momentum).
    """
    del record  # every kind the pickers serve has a momentum and a polar angle per shower
    spec = ParticleSpec(
        p_min=_momentum(PARAM_P_MIN, p_min), p_max=_momentum(PARAM_P_MAX, p_max),
        theta_min_deg=_angle(PARAM_THETA_MIN, theta_min), theta_max_deg=_angle(PARAM_THETA_MAX, theta_max),
    )
    for field, what, lo, hi in (("particle_p", "momentum", spec.p_min, spec.p_max),
                                ("particle_theta", "angle", spec.theta_min_deg, spec.theta_max_deg)):
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError(typographic(
                f"The particle {what} range is inverted: minimum {lo:g} exceeds maximum {hi:g}."), field=field)
    return spec


INACTIVE = ParticleSpec()


# ------------------------------------------------------------------- sentences --


def two_showers(record: ExperimentRecord) -> bool:
    return len(showers_mod.of(record)) == 2


def placed_words(record: ExperimentRecord) -> str:
    """What the frame gate asks of an event, as the pick sentences write it."""
    return ("with a defined separation" if two_showers(record)
            else "with an incident direction and an entry point")


def population_words(basis: str) -> str:
    """Who the pool's events are: 'selected events', or 'events of the experiment' under its basis."""
    return "events of the experiment" if basis == BASIS_EXPERIMENT else "selected events"


def population_phrase(record: ExperimentRecord, particle: ParticleSpec, basis: str = BASIS_SELECTION) -> str:
    """'selected events with a defined separation[ holding a shower with ... that deposited energy]'.

    Under the experiment basis it opens 'events of the experiment' instead.
    """
    phrase = f"{population_words(basis)} {placed_words(record)}"
    if particle.active:
        interval = particle.interval_text()
        phrase += (f" holding a shower with {interval} that deposited energy" if two_showers(record)
                   else f" whose shower has {interval}")
    return phrase


def empty_pool_detail(record: ExperimentRecord, particle: ParticleSpec, basis: str = BASIS_SELECTION) -> str:
    """The 404's detail when the pool holds no event: 'The selection holds ...' or 'The experiment holds ...'."""
    holder = "The experiment" if basis == BASIS_EXPERIMENT else "The selection"
    if not particle.active:
        return (f"{holder} holds no event with a defined separation to pick from." if two_showers(record)
                else f"{holder} holds no event with an incident direction and an entry point to pick from.")
    interval = particle.interval_text()
    if two_showers(record):
        return typographic(
            f"{holder} holds no candidate event: none of its events {placed_words(record)} holds a "
            f"shower with {interval} that deposited energy.")
    return typographic(
        f"{holder} holds no candidate event: none of its events {placed_words(record)} has its "
        f"shower at {interval}.")


def outside_pool_warning(event_number: int, particle: ParticleSpec) -> str:
    """The warning for an event inside the selection whose showers miss an active filter."""
    return typographic(
        f"Event {int(event_number)} holds no shower matching the particle filter "
        f"({particle.interval_text()}); it is drawn as asked, and the previous / next controls walk "
        "the candidates.")


# ----------------------------------------------------------------------- SQL --


def _table(record: ExperimentRecord) -> str:
    return quote(naming.event_table(record.table_name))


def pool_where(record: ExperimentRecord, spec: FilterSpec, particle: ParticleSpec) -> str:
    """Selection AND frame gate, AND a matching shower when the filter is active."""
    where = f"{spec.where_sql()} AND {capabilities.frame_gate(record)}"
    if particle.active:
        where += f" AND ({particle.pool_sql(record)})"
    return where


def pool_params(spec: FilterSpec, particle: ParticleSpec) -> dict[str, Any]:
    """The parameters :func:`pool_where` uses, and only those."""
    return {**spec.params(), **particle.params()}


def pool_events(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                particle: ParticleSpec) -> np.ndarray:
    """The pool's event numbers, ascending."""
    rows = con.execute(
        f"SELECT event_number FROM {_table(record)} WHERE {pool_where(record, spec, particle)} "
        "ORDER BY event_number", pool_params(spec, particle),
    ).fetchall()
    return np.asarray([int(r[0]) for r in rows], dtype=np.int64)


def matched(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, particle: ParticleSpec,
            event_numbers: list[int]) -> dict[int, list[str]]:
    """Each named event's matching showers, by key in order; an event the table lacks is absent."""
    wanted = sorted({int(e) for e in event_numbers})
    if not wanted:
        return {}
    showers = showers_mod.of(record)
    columns = ", ".join(f"({particle.shower_sql(s)}) AS m_{s.key}" for s in showers)
    slots = {f"ev_{i}": e for i, e in enumerate(wanted)}
    rows = con.execute(
        f"SELECT event_number, {columns} FROM {_table(record)} "
        f"WHERE event_number IN ({', '.join('$' + k for k in slots)})",
        {**particle.params(), **slots},
    ).fetchall()
    return {int(row[0]): [s.key for s, hit in zip(showers, row[1:]) if hit] for row in rows}


def candidates(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
               particle: ParticleSpec) -> dict[str, Any]:
    """The pool's counts: the selection, the events the frame gate cannot place, the pool, its showers.

    One scan of the event table. ``n_showers`` counts the matching showers of
    the pool's events (with no bound set, every shower with a deposit);
    ``n_both`` is null where an event has one shower. Under the experiment
    basis the block opens with ``"basis": "experiment"``, ``n_selection`` is
    the experiment's event count and ``n_unplaceable`` every event of it the
    frame gate refuses.
    """
    showers = showers_mod.of(record)
    two = len(showers) == 2
    gate = capabilities.frame_gate(record)
    pool = f"({particle.pool_sql(record)})" if particle.active else "TRUE"
    match = {s.key: f"({particle.shower_sql(s)})" for s in showers}
    selects = [
        "count(*)",
        f"count(*) FILTER (WHERE NOT ({gate}))",
        f"count(*) FILTER (WHERE {gate} AND {pool})",
        *(f"count(*) FILTER (WHERE {gate} AND {match[s.key]})" for s in showers),
    ]
    if two:
        selects.append(f"count(*) FILTER (WHERE {gate} AND {match['a']} AND {match['b']})")
    row = con.execute(
        f"SELECT {', '.join(selects)} FROM {_table(record)} WHERE {spec.where_sql()}",
        pool_params(spec, particle),
    ).fetchone()
    n_selection, n_unplaceable, n_events = (int(v or 0) for v in row[:3])
    by_shower = {s.key: int(row[3 + i] or 0) for i, s in enumerate(showers)}
    return with_basis({
        "particle": particle.as_dict(),
        "n_selection": n_selection,
        "n_unplaceable": n_unplaceable,
        "n_events": n_events,
        "n_showers": sum(by_shower.values()),
        "by_shower": by_shower,
        "n_both": int(row[3 + len(showers)] or 0) if two else None,
        "showers": [s.key for s in showers],
    }, basis_of(spec))


def membership(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
               particle: ParticleSpec, event_number: int) -> dict[str, Any]:
    """Where one event stands: in the selection, in the pool, its place there and its neighbours.

    One scan of the event table over the selection gives ``in_selection``
    (the selection alone, as it has always meant), ``in_pool``, ``index``
    (0-based in event-number order, null outside the pool), ``n_events`` and
    ``prev`` / ``next`` (the pool's neighbours by event number, whether or not
    the event is in it); one small query gives the matching showers of the
    event and of both neighbours. An event the table does not hold is a 404.
    Under the experiment basis the spec selects every row, so ``in_selection``
    is true for every event the experiment holds.
    """
    gate = capabilities.frame_gate(record)
    pool = f"{gate} AND ({particle.pool_sql(record)})" if particle.active else gate
    ev = int(event_number)
    row = con.execute(
        f"""SELECT count(*) FILTER (WHERE event_number = $ev),
                   count(*) FILTER (WHERE event_number = $ev AND {pool}),
                   count(*) FILTER (WHERE event_number < $ev AND {pool}),
                   count(*) FILTER (WHERE {pool}),
                   max(event_number) FILTER (WHERE event_number < $ev AND {pool}),
                   min(event_number) FILTER (WHERE event_number > $ev AND {pool})
            FROM {_table(record)} WHERE {spec.where_sql()}""",
        {**pool_params(spec, particle), "ev": ev},
    ).fetchone()
    in_selection, in_pool = bool(row[0]), bool(row[1])
    prev_event = int(row[4]) if row[4] is not None else None
    next_event = int(row[5]) if row[5] is not None else None
    found = matched(con, record, particle, [e for e in (ev, prev_event, next_event) if e is not None])
    if ev not in found:
        raise NotFoundError(f"No event {ev} in experiment {record.table_name!r}.")
    return {
        "event_number": ev,
        "in_selection": in_selection,
        "in_pool": in_pool,
        "index": int(row[2]) if in_pool else None,
        "n_events": int(row[3] or 0),
        "prev": prev_event,
        "next": next_event,
        "matched": found[ev],
        "prev_matched": found.get(prev_event) if prev_event is not None else None,
        "next_matched": found.get(next_event) if next_event is not None else None,
    }


def event_candidates(particle: ParticleSpec, member: dict[str, Any],
                     basis: str = BASIS_SELECTION) -> dict[str, Any]:
    """``event.candidates`` of ``GET /api/event``: the echo and the pool fields of a membership.

    Led by ``"basis": "experiment"`` under the experiment basis.
    """
    return with_basis({
        "particle": particle.as_dict(),
        "in_pool": member["in_pool"],
        "index": member["index"],
        "n_events": member["n_events"],
        "matched": member["matched"],
        "prev_matched": member["prev_matched"],
        "next_matched": member["next_matched"],
    }, basis)


def _extreme(fn: str, terms: list[str]) -> str:
    """``least``/``greatest`` of per-shower aggregates (DuckDB's ignore NULL); one term as itself."""
    return terms[0] if len(terms) == 1 else f"{fn}({', '.join(terms)})"


def bounds(con: duckdb.DuckDBPyConnection, record: ExperimentRecord) -> dict[str, Any]:
    """The dataset's own range of every placeable event's showers that deposited energy, for the sliders.

    Over every event the frame gate admits (never the selection), the
    momentum and polar angle of each shower with a deposit - the showers that
    can match at all. The angle is returned in degrees.
    """
    showers = showers_mod.of(record)

    def agg(fn: str, column: str) -> list[str]:
        return [f"{fn}(CASE WHEN {s.present_sql} THEN {getattr(s, column)} END)" for s in showers]

    row = con.execute(
        f"SELECT {_extreme('least', agg('min', 'momentum'))}, {_extreme('greatest', agg('max', 'momentum'))}, "
        f"{_extreme('least', agg('min', 'theta'))}, {_extreme('greatest', agg('max', 'theta'))} "
        f"FROM {_table(record)} WHERE {capabilities.frame_gate(record)}",
    ).fetchone()
    p_lo, p_hi, t_lo, t_hi = (None if v is None else float(v) for v in row)
    return {
        "p_gev": [p_lo, p_hi],
        "theta_deg": [None if t_lo is None else math.degrees(t_lo), None if t_hi is None else math.degrees(t_hi)],
    }
