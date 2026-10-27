"""Events without a primary-tagged hit: card C11 of Page 2.

A single-shower hit file tags each hit row with the particle attributed to its
cell, and flags the primary particle itself with ``is_secondary = 0``. Ingest
counts each event's flagged rows into ``n_primary_rows`` of the event table, so
this card reads the event table only: no hit is scanned and no cache is needed.

The unit is the event. "No primary" is a property of an event (none of its rows
carries the tag), the fraction of such events in a momentum bin is a binomial
proportion of independent events, and its whisker is the Wilson score interval,
never the Wald interval, which collapses to a point at zero events and leaves
[0, 1] at small N - where a bin of a few events has to stay honest. The count
distribution (how many tagged rows an event holds, 0 to 10) is exact counts,
not an estimate, and carries no whisker.

The measured behaviour is the reverse of what the roadmap expected: most events
hold no primary-tagged hit at all. The payload says so in its notes, labelled as
a measurement of the electron file and not of the selection on screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..errors import ValidationError
from ..stats import metrics
from ..stats import momentum as momentum_mod
from ..text import typographic
from . import showers
from .filters import FilterSpec

#: The event-table column holding the tagged rows of each event (rows with
#: ``is_secondary = 0``), as the shower vocabulary names it.
PRIMARY_ROWS = showers.primary_rows_column()

#: The count distribution runs 0 .. TOP_BUCKET, the last bucket holding that many or more.
TOP_BUCKET = 10

#: Below this many events a bin's Wilson interval is wide enough to say so.
WEAK_N = 20

DEFINITION = (
    "An event has no primary when none of its hit rows has is_secondary = 0, the producer's "
    "primary-particle tag. Each point is the fraction of the selected events that have none, an "
    "event being the unit."
)

#: The roadmap's expectation against the measured file (``data.md`` H8), so a reader
#: is not left to rediscover a result that reversed it.
_REFERENCE = (
    "Reference measurement on the electron file (100,000 events, not this selection): 73.83% "
    "of events hold no primary-tagged hit row, rising from 64% in momentum bin 1 to 80% in bin "
    "18; the roadmap had expected 25–27%."
)


@dataclass(frozen=True)
class BinRate:
    """One momentum bin: its events and those without a primary-tagged hit."""

    bin: int
    label: str
    n: int
    k: int


@dataclass
class PrimaryRates:
    """The selection's events by primary-tag count, overall and per momentum bin."""

    n_events: int
    n_no_primary: int
    n_unknown: int
    bins: list[BinRate]
    counts: list[int]                 # events holding 0, 1, ... TOP_BUCKET - 1, >= TOP_BUCKET rows
    notices: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        overall = metrics.wilson_interval(self.n_no_primary, self.n_events)
        wilsons = [metrics.wilson_interval(b.k, b.n) for b in self.bins]
        tree = {
            "definition": DEFINITION,
            "overall": {
                "n_events": self.n_events,
                "n_no_primary": self.n_no_primary,
                "fraction": sig(self.n_no_primary / self.n_events) if self.n_events else None,
                "interval": _interval(overall),
            },
            "by_bin": {
                "bin": [b.bin for b in self.bins],
                "label": [b.label for b in self.bins],
                "n": [b.n for b in self.bins],
                "k": [b.k for b in self.bins],
                "fraction": [sig(b.k / b.n) for b in self.bins],
                "lo": [sig(w.lo) for w in wilsons],
                "hi": [sig(w.hi) for w in wilsons],
            },
            "primary_count": {
                "value": list(range(TOP_BUCKET + 1)),
                "events": self.counts,
                "top_bucket": f"≥ {TOP_BUCKET}",
            },
            "notes": self._notes(),
        }
        return _typeset(tree)

    def _notes(self) -> list[str]:
        weak = sum(1 for b in self.bins if b.n < WEAK_N)
        notes = [
            DEFINITION + " The rate axis starts at zero.",
            "Whiskers are 95% Wilson score intervals of the fraction, events being the "
            "independent units. The Wald interval is not used: it collapses at zero events and "
            f"leaves [0, 1] at small N. {weak} bin{'s' if weak != 1 else ''} with N < {WEAK_N} "
            f"{'have' if weak != 1 else 'has'} a correspondingly wide interval.",
            "Bins are the producer's integer momentum bin, closed on the left, labelled "
            "with the momenta found in them.",
            f"The count distribution is exact, not an estimate: the number of primary-tagged hit "
            f"rows per event, 0 to {TOP_BUCKET - 1}, and a last bucket of {TOP_BUCKET} or more.",
            _REFERENCE,
        ]
        if self.n_unknown:
            notes.append(
                f"{self.n_unknown:,} selected event{'s' if self.n_unknown != 1 else ''} have no "
                "recorded count of primary-tagged rows and enter no point's rate.")
        return notes + self.notices


def _interval(interval: metrics.Interval | None) -> dict[str, Any] | None:
    if interval is None:
        return None
    return {**interval.as_dict(), "lo": sig(interval.lo), "hi": sig(interval.hi)}


def _typeset(value: Any) -> Any:
    """U+2212 in every sentence that carries a negative number."""
    if isinstance(value, dict):
        return {k: _typeset(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_typeset(v) for v in value]
    return typographic(value) if isinstance(value, str) else value


def compute(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec
) -> PrimaryRates:
    """Two grouped reads of the event table: events per momentum bin, and per tag count."""
    shower = showers.of(record, "a")[0]
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    per_bin = con.execute(
        f"""
        SELECT CAST({shower.momentum_bin} AS INTEGER) AS bin,
               count({PRIMARY_ROWS}) AS n,
               count(*) FILTER (WHERE {PRIMARY_ROWS} = 0) AS k,
               count(*) - count({PRIMARY_ROWS}) AS n_unknown,
               min({shower.momentum}) AS p_lo, max({shower.momentum}) AS p_hi
        FROM {table} WHERE {where} GROUP BY 1 ORDER BY 1
        """,
        spec.params(),
    ).fetchall()
    per_count = con.execute(
        f"""
        SELECT least({PRIMARY_ROWS}, {TOP_BUCKET}) AS c, count(*) AS events
        FROM {table} WHERE {where} AND {PRIMARY_ROWS} IS NOT NULL GROUP BY 1 ORDER BY 1
        """,
        spec.params(),
    ).fetchall()

    counts = [0] * (TOP_BUCKET + 1)
    for tagged, events in per_count:
        counts[int(tagged)] = int(events)

    populated = [row for row in per_bin if row[1]]
    bins: list[BinRate] = []
    notices: list[str] = []
    if populated:
        try:
            classes = momentum_mod.unit_bins(populated[0][0], populated[-1][0])
        except ValidationError as error:
            raise ValidationError(error.detail, field="table_name") from None
        ranges = {int(b): (float(lo), float(hi)) for b, _, _, _, lo, hi in populated}
        classes, notices = momentum_mod.relabel_bins(classes, ranges)
        labels = {int(c.lo): c.label for c in classes}
        bins = [BinRate(int(b), labels[int(b)], int(n), int(k)) for b, n, k, *_ in populated]
    return PrimaryRates(
        n_events=sum(b.n for b in bins),
        n_no_primary=sum(b.k for b in bins),
        n_unknown=sum(int(row[3]) for row in per_bin),
        bins=bins,
        counts=counts,
        notices=notices,
    )
