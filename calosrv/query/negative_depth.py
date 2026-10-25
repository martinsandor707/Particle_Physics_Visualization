"""C9: how much of a shower lies at negative depth, from the event table alone.

``w = z_local`` is a hit's depth along its own shower's incident direction,
measured from the shower's entry point P0 (the energy-weighted centroid of its
first populated layer). A hit at ``w < 0`` lies upstream of that point. That is
not rare: on the electron file 95.1% of events hold at least one such hit, and
together they carry 3.98% of the energy (2.83% of the hits). How far that is
physics and how far it is a property of how P0 and the rotation are defined is
not decided here: the card counts these hits and weighs them, which is what
lets a reader judge the notebook's choice to drop them from its profiles *and*
from the normalising total.

Everything is read from the Group-1 columns of the event table - each shower's
hit count, deposit and negative-depth hit count and energy - so this module
never touches the projection table, which is the rule ``query/__init__``
states for per-event quantities. A selection of 100 000 two-shower events
costs 61 ms (measured on a synthetic event table) and needs no cache.
``summarise`` is also what the Local frame embeds in its response, so its
signature and the shape of its result are frozen by
``tests/contracts/statistics.json`` (``$defs/negative_w``).

**What is counted.** A hit is at negative depth when ``w < -10⁻⁶ mm`` (the
notebook's ``tol``; 462 of the electron file's hits lie in ``[-10⁻⁶, 0)`` and
are not counted). The incident momentum that splits the selection is the
shower's *own* (``e1`` for shower A, ``e2`` for B), with the notebook's strict
cuts: ``p < 1 GeV``, ``p > 10 GeV``, and ``mid`` for what remains so that the
three splits partition the selection.

**Which interval for which quantity.** The hits of one shower share its
development, and the two showers of an event share the event, so the sampling
unit is the *event* throughout:

* the share of hits and the share of energy at negative depth are ratios of
  sums over events, with the linearised cluster standard error and a Student-t
  interval (``metrics.ratio_estimate``), clipped to [0, 1] and saying so;
* the share of units holding any such hit is a proportion and takes a Wilson
  interval (``metrics.wilson_interval``). On events it is always given. On
  showers it is given only where each event contributes one shower to the
  selection (single-shower data, or one shower chosen): the two showers of a
  two-shower event are not independent Bernoulli trials, and a shower-level
  interval would understate the width.

The affected-shower fraction statistics follow the notebook's ``describe()``
of the per-event negative-hit fraction, over the showers that have any.
"""

from __future__ import annotations

import math
from typing import Any

import duckdb

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..stats import gaussian, metrics
from ..text import MINUS, typographic
from . import capabilities, showers
from .filters import FilterSpec

#: The depth cut as a magnitude: a hit counts when ``w < -THRESHOLD_MM``.
THRESHOLD_MM = abs(ddl.NEG_DEPTH_MM)

#: The notebook's momentum cuts (GeV), strict: ``p < LOW`` and ``p > HIGH``.
LOW_P_GEV = 1.0
HIGH_P_GEV = 10.0

#: An affected shower with more than this fraction of its hits at negative depth.
OVER_HALF = 0.5

#: Below this many events a fraction's interval is labelled weak evidence.
WEAK_BELOW_N = gaussian.MIN_ROBUST_SAMPLES

#: The splits, in the order they are served: the whole selection, then a partition by momentum.
SPLITS: tuple[tuple[str, str], ...] = (
    ("all", "All selected"),
    ("low", f"p < {LOW_P_GEV:g} GeV"),
    ("mid", f"{LOW_P_GEV:g} ≤ p ≤ {HIGH_P_GEV:g} GeV"),
    ("high", f"p > {HIGH_P_GEV:g} GeV"),
)

#: What each interval is, in a few words, so a table cell and its tooltip can name the
#: quantity. Short on purpose: the Local frame embeds this block in a response that already
#: sits close to the 100 KB contract. :data:`RATIONALE` carries the full sentences.
INTERVALS: dict[str, str] = {
    "hits_fraction": "95% Student-t, ratio of sums, events as clusters",
    "energy_fraction": "95% Student-t, ratio of sums, events as clusters",
    "events_with_any": "95% Wilson score, events",
    "showers_with_any": "95% Wilson score, showers (one per event only)",
}

#: Why those intervals, for a drawer or the statistics card's notes.
RATIONALE: tuple[str, ...] = (
    "A hit is at negative depth when w = z_local < −{threshold} mm in its own shower's frame, "
    "whatever frame the other numbers are drawn in. The counts come from the event table, so "
    "they are exact even on a preview. Energies are the raw deposited hit energies (GeV), not "
    "calibrated to the incident momentum; a share of them is unaffected by the calibration.",
    "The hits of one shower share its development, and the two showers of an event share the "
    "event, so every fraction takes events as its sampling unit: a ratio of sums with the "
    "linearised cluster standard error and a Student-t interval, clipped to [0, 1].",
    "The share of events with any such hit is a proportion and takes a Wilson score interval. "
    "The share of showers is given only where each event contributes one shower: the two "
    "showers of an event are not independent Bernoulli trials.",
)

_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def threshold_label() -> str:
    """The cut as the interface writes it: ``10⁻⁶`` for a power of ten, else the plain number."""
    exponent = math.log10(THRESHOLD_MM)
    if abs(exponent - round(exponent)) < 1e-9:
        return "10" + str(round(exponent)).translate(_SUPERSCRIPT)
    return f"{THRESHOLD_MM:g}"


#: The two sentences that speak of an event's two showers, for one shower per event.
_RATIONALE_ONE_SHOWER: tuple[str, ...] = (
    RATIONALE[0],
    "The hits of one shower share its development, so every fraction takes events as its "
    "sampling unit: a ratio of sums with the linearised cluster standard error and a Student-t "
    "interval, clipped to [0, 1].",
    "The share of events with any such hit is a proportion and takes a Wilson score interval; "
    "with one shower per event it is also the share of showers.",
)


def rationale(n_showers: int = 2) -> list[str]:
    """:data:`RATIONALE` with the cut written in, minus signs typographic, worded for the kind."""
    cut = threshold_label()
    texts = RATIONALE if n_showers > 1 else _RATIONALE_ONE_SHOWER
    return [typographic(text.replace("{threshold}", cut)) for text in texts]


def _fetch(con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _shower_rows(record: ExperimentRecord, spec: FilterSpec,
                 scope: tuple[showers.ShowerColumns, ...]) -> str:
    """``sh(event_number, p, n, nh, e, ne)``: one row per selected shower that deposited energy.

    ``n`` and ``nh`` are the shower's hits and its hits at negative depth, ``e``
    and ``ne`` its deposit and the deposit of those hits - all Group-1 columns
    of one scan, so a fraction cannot exceed one - read through :mod:`showers`,
    so no column name is written here.
    """
    event = quote(naming.event_table(record.table_name))
    selects = [
        f"SELECT event_number, CAST({s.momentum} AS DOUBLE) AS p, "
        f"CAST({s.group1('n_hits')} AS DOUBLE) AS n, CAST({s.w_neg_hits} AS DOUBLE) AS nh, "
        f"CAST({s.shower_energy} AS DOUBLE) AS e, CAST({s.w_neg_energy} AS DOUBLE) AS ne "
        f"FROM {event} WHERE {spec.where_sql()} AND {s.present_sql}"
        for s in scope
    ]
    return "sh AS (" + " UNION ALL ".join(selects) + ")"


def _splits_sql(rows: str) -> str:
    """Per split: the counts, and the five sums of each ratio over *events* as clusters.

    A shower belongs to the split of its own momentum; an event's cluster in a
    split is the sum of its showers that fall in it (zero, one or two), so a
    two-shower event contributes one cluster to ``all`` and up to two to the
    momentum splits.
    """
    low, high = repr(LOW_P_GEV), repr(HIGH_P_GEV)
    return f"""
    WITH {rows},
    tagged AS (
        SELECT 'all' AS split, * FROM sh
        UNION ALL SELECT 'low', * FROM sh WHERE p < {low}
        UNION ALL SELECT 'mid', * FROM sh WHERE p >= {low} AND p <= {high}
        UNION ALL SELECT 'high', * FROM sh WHERE p > {high}
    ),
    ev AS (
        SELECT split, event_number, count(*) AS k, count(*) FILTER (WHERE nh > 0) AS k_any,
               sum(n) AS n, sum(nh) AS nh, sum(e) AS e, sum(ne) AS ne
        FROM tagged GROUP BY split, event_number
    )
    SELECT split, count(*) AS n_events, sum(k) AS n_showers, sum(k_any) AS showers_any,
           count(*) FILTER (WHERE nh > 0) AS events_any,
           sum(n) AS hits, sum(nh) AS hits_neg, sum(e) AS energy, sum(ne) AS energy_neg,
           {metrics.ratio_sums_sql("nh", "n", "h")}, {metrics.ratio_sums_sql("ne", "e", "e")}
    FROM ev GROUP BY split
    """


def _affected_sql(rows: str) -> str:
    """The notebook's ``describe()`` of the negative-depth hit fraction of each affected shower."""
    return f"""
    WITH {rows}
    SELECT count(*) AS n, avg(f) AS mean, stddev_samp(f) AS sd, min(f) AS lo,
           quantile_cont(f, [0.25, 0.5, 0.75]) AS q, max(f) AS hi,
           count(*) FILTER (WHERE f > {OVER_HALF!r}) AS over_half
    FROM (SELECT nh / n AS f FROM sh WHERE nh > 0 AND n > 0)
    """


def _bounds(interval: metrics.Interval | None) -> list[float | None] | None:
    return None if interval is None else [sig(interval.lo), sig(interval.hi)]


def _note(n_events: int) -> str:
    if n_events == 0:
        return "No showers in this split."
    if n_events == 1:
        return "N = 1 event: the fractions are that event's own and carry no interval."
    if n_events < WEAK_BELOW_N:
        return (f"N = {n_events} events: the Student-t interval of a fraction has "
                f"{n_events - 1} degree(s) of freedom; weak evidence below N = {WEAK_BELOW_N}.")
    return ""


def _empty_split(key: str, label: str) -> dict[str, Any]:
    return {
        "key": key, "label": label, "n_events": 0, "n_showers": 0,
        "events_with_any": 0, "events_with_any_ci95": None,
        "showers_with_any": 0, "showers_with_any_ci95": None,
        "hits": 0, "hits_total": 0, "hits_fraction": None, "hits_fraction_ci95": None,
        "energy_gev": 0.0, "energy_total_gev": 0.0, "energy_fraction": None,
        "energy_fraction_ci95": None, "note": _note(0),
    }


def _split(key: str, label: str, row: dict[str, Any] | None, per_event: int) -> dict[str, Any]:
    n_events = 0 if row is None else int(row["n_events"])
    if row is None or n_events == 0:
        return _empty_split(key, label)
    n_showers, events_any, showers_any = int(row["n_showers"]), int(row["events_any"]), int(row["showers_any"])
    hits = metrics.ratio_from_row(row, "h", n_events, bounds=(0.0, 1.0))
    energy = metrics.ratio_from_row(row, "e", n_events, bounds=(0.0, 1.0))
    by_shower = metrics.wilson_interval(showers_any, n_showers) if per_event == 1 else None
    return {
        "key": key, "label": label, "n_events": n_events, "n_showers": n_showers,
        "events_with_any": events_any,
        "events_with_any_ci95": _bounds(metrics.wilson_interval(events_any, n_events)),
        "showers_with_any": showers_any, "showers_with_any_ci95": _bounds(by_shower),
        "hits": int(row["hits_neg"]), "hits_total": int(row["hits"]),
        "hits_fraction": sig(hits.value), "hits_fraction_ci95": _bounds(hits.interval),
        "energy_gev": sig(row["energy_neg"]), "energy_total_gev": sig(row["energy"]),
        "energy_fraction": sig(energy.value), "energy_fraction_ci95": _bounds(energy.interval),
        "note": _note(n_events),
    }


def _affected(row: dict[str, Any]) -> dict[str, Any]:
    q25, q50, q75 = row["q"] if row["q"] is not None else (None, None, None)
    return {
        "n": int(row["n"]), "mean": sig(row["mean"]), "sd": sig(row["sd"]), "min": sig(row["lo"]),
        "q25": sig(q25), "q50": sig(q50), "q75": sig(q75), "max": sig(row["hi"]),
        "n_over_half": int(row["over_half"]),
    }


def _percent(value: float | None, interval: list[float | None] | None, digits: int) -> str:
    if value is None:
        return "n/a"
    text = f"{100.0 * value:.{digits}f}%"
    if interval is not None and None not in interval:
        text += f" [{100.0 * interval[0]:.{digits}f}, {100.0 * interval[1]:.{digits}f}]"
    return text


def _summary(whole: dict[str, Any], per_event: int) -> str:
    """The one-line status text of the selection, intervals in brackets."""
    head = f"w < {MINUS}{threshold_label()} mm"
    if whole["n_events"] == 0:
        return f"{head}: no showers in this selection."
    unit = "showers" if per_event == 1 else "events (either shower)"
    if per_event == 1:
        share = _percent(whole["showers_with_any"] / whole["n_showers"], whole["showers_with_any_ci95"], 1)
    else:
        share = _percent(whole["events_with_any"] / whole["n_events"], whole["events_with_any_ci95"], 1)
    text = (
        f"{head}: {_percent(whole['energy_fraction'], whole['energy_fraction_ci95'], 2)} of energy, "
        f"{_percent(whole['hits_fraction'], whole['hits_fraction_ci95'], 2)} of hits; {share} of {unit}"
        " (95% intervals in brackets)"
    )
    return typographic(text)


def _unavailable(reason: str, per_event: int) -> dict[str, Any]:
    return {
        "available": False, "reason": reason, "threshold_mm": THRESHOLD_MM, "unit": "shower",
        "showers_per_event": per_event, "splits": [], "affected": None,
        "summary": typographic(f"Negative-depth counts are unavailable: {reason}"),
    }


def summarise(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    shower: str = "both",
) -> dict[str, Any]:
    """The ``negative_w`` block of a selection: splits by momentum, affected-shower statistics, summary.

    ``shower`` is ``a``, ``b`` or ``both`` (:func:`showers.of`, which refuses an
    unknown choice, and shower ``b`` of a single-shower experiment, naming the
    parameter). An experiment whose event table lacks the Group-1 columns - one
    ingested before they existed, served as before until it is rebuilt - gets
    ``available: false`` and the reason, not an error: the card beside it
    still works.
    """
    scope = showers.of(record, shower)
    per_event = len(scope)
    caps = capabilities.of(record)
    if not caps.can("negative-depth"):
        return _unavailable(
            caps.reasons.get("negative-depth", "Not available for this experiment."), per_event)

    rows = _shower_rows(record, spec, scope)
    params = spec.params()
    by_split = {r["split"]: r for r in _fetch(con, _splits_sql(rows), params)}
    splits = [_split(key, label, by_split.get(key), per_event) for key, label in SPLITS]
    affected = _affected(_fetch(con, _affected_sql(rows), params)[0])
    return {
        "available": True,
        "threshold_mm": THRESHOLD_MM,
        "unit": "shower",
        "showers_per_event": per_event,
        "splits": splits,
        "affected": affected,
        "intervals": dict(INTERVALS),
        "summary": _summary(splits[0], per_event),
    }
