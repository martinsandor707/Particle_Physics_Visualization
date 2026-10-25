"""C1: descriptive statistics of the hit coordinates and energy, in the frame of the card.

The reference notebook prints ``df.describe()`` over every hit - mean, SD,
min, quartiles, max of the three coordinates, the 2-D transverse radius and the
energy - and the production file has 24 million of them, so the table is
reduced inside DuckDB and only the numbers leave it. Two statements read the
selected hits of the projection table, under the physics cache's heavy-scan
gate, and their result is one small record per variable whatever the selection:

1. **The unweighted moments**: ``count``, ``avg``, ``stddev_samp`` (the
   unbiased ``ddof = 1`` width every panel quotes) and ``stddev_pop`` (the
   ``ddof = 0`` form, so the notebook stays directly comparable), ``min``,
   ``max`` and the *exact* quartiles by ``quantile_cont`` - linear
   interpolation between order statistics, pandas' ``describe`` convention.
   Exact quartiles keep every selected value of a column in memory for the
   duration of the statement, which is why the scan is one at a time: 8 bytes
   per row and variable, doubled while the threads' states merge - measured
   +640 MB and 1.9 s for 8 million synthetic hits in memory, so about 2 GB
   for the production file's 24 million hits and five variables.
2. **The energy-weighted columns**: one ``GROUPING SETS`` pass summing each
   hit's energy into 1 mm bins of each coordinate (and 0.01-decade bins of
   ``log10 E`` for the energy itself), from which
   :func:`stats.describe.weighted_quantiles` reads the weighted quartiles to one
   bin. The weighted *mean* is exact, ``Σ E·a / Σ E``, from the first
   statement. Weighting by energy answers where the energy sits rather than
   where the hits are, so these are separate columns under their own label, a
   different weighting and not a correction of the unweighted ones.

**What a row is.** Each hit is one observation. The hits of one shower are
strongly correlated, so no standard error of a mean is quoted: a hit count
would claim a precision the events do not have. The table describes the
sample of hits; the columns that encode dispersion are the SD and the
quartiles, and nothing here is drawn as a point with a whisker.

**Gates.** The mean, quartiles, min and max are reported from one hit, the SD
from two (a single pairwise difference at N = 2, labelled), and the quartiles
are labelled as interpolating between individual hits below
``describe.ROBUST_N`` - the same floors as :func:`stats.describe.describe`.

**Frames.** Coordinates come from :func:`hit_sql.frame_xyz`, so the laboratory
frame goes through the measured lattice arrays and never a bin index times a
pitch. The Local frame adds the 2-D transverse radius ``ρ = √(u² + v²)``, the
reference notebook's ``r_local``; ``core.py``'s ``r_local`` is the 3-D
distance, which is a different quantity and is not reported here. The
laboratory frame adds the notebook's ``z − 3649 mm`` as a labelled display row
(decision D1): every location statistic of ``z`` moved by the offset, the
widths untouched, the stored coordinate left raw.

The response is bounded by construction - at most five rows of sixteen numbers,
the negative-depth block of ``query/negative_depth.py`` and a dozen sentences,
about 6 KB measured - so the route only checks the contract and says so if it
is ever missed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..errors import CapabilityError
from ..stats import describe, gaussian
from ..text import MINUS, typographic
from . import hit_sql, physics_cache
from .filters import FilterSpec
from .showers import ShowerColumns

#: Bump when the cached :class:`Scan` changes shape.
CACHE_VERSION = 1

QUARTILES: tuple[float, float, float] = (0.25, 0.5, 0.75)

#: Width of the energy-weighted coordinate histograms (mm), and of the energy histogram (decades).
FINE_MM = 1.0
LOG_STEP = 0.01

#: Per frame, each coordinate's key and label.
_COORDINATES: dict[str, tuple[tuple[str, str], ...]] = {
    "lab": (("x", "x (detector)"), ("y", "y (detector)"), ("z", "z (detector, raw)")),
    "trans": (("dx", "x_trans (Δx)"), ("dy", "y_trans (Δy)"), ("dz", "z_trans (Δz)")),
    "local": (("u", "x_local (u)"), ("v", "y_local (v)"), ("w", "z_local (w)")),
}

ESTIMATOR = (
    "Each hit is one observation and these columns are unweighted. count, mean, min and max "
    "are exact; the quartiles are exact too (linear interpolation between order statistics, "
    "the pandas describe() convention); sd is the unbiased sample estimator (ddof = 1) and "
    "sd_population the ddof = 0 form. No standard error of a mean is quoted: the hits of one "
    "shower are strongly correlated, so a hit count would claim a precision the events do not have."
)

WEIGHTING_NOTE = (
    "The ew columns weight every hit by its deposited energy. ew_mean = Σ E·a / Σ E exactly; "
    "the ew quartiles are read off 1 mm histograms of the weighted coordinate (0.01-decade "
    "bins of log10 E for the energy row) and are exact to one bin. They say where the energy "
    "sits, not where the hits are: a different weighting, not a correction of the unweighted "
    "columns."
)


@dataclass(frozen=True)
class Variable:
    """One described quantity: its label, and the column of the hit CTE it reads."""

    key: str
    label: str
    unit: str
    column: str            # ``c0``..``c3`` or ``en`` in the hit CTE
    log10: bool = False    # the energy: its weighted histogram is in log10 bins


@dataclass(frozen=True)
class Column:
    """The statistics of one :class:`Variable`, at full precision."""

    variable: Variable
    n: int
    mean: float | None = None
    sd: float | None = None
    sd_population: float | None = None
    minimum: float | None = None
    q25: float | None = None
    q50: float | None = None
    q75: float | None = None
    maximum: float | None = None
    ew_mean: float | None = None
    ew_q25: float | None = None
    ew_q50: float | None = None
    ew_q75: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Scan:
    """What one heavy pass over the selected hits reduces to; this is what the cache holds."""

    coord_system: str
    columns: tuple[Column, ...]
    n_rows: int
    query_ms: float


def variables(coord_system: str) -> tuple[Variable, ...]:
    """The rows of a frame's table: its coordinates, the Local frame's radius, then the energy."""
    out = [Variable(key, label, "mm", f"c{i}") for i, (key, label) in enumerate(_COORDINATES[coord_system])]
    if coord_system == "local":
        out.append(Variable("rho", "ρ = √(u² + v²)", "mm", "c3"))
    out.append(Variable("energy", "Hit energy", "GeV", "en", log10=True))
    return tuple(out)


def require_frame(record: ExperimentRecord, coord_system: str) -> None:
    """Refuse a frame whose coordinates the experiment's measurements cannot place hits in.

    The Local and per-shower translated coordinates are columns of the
    projection table; the laboratory ones need the measured lattice, and the
    translated depth the layer pitch. The frame gates of the capability block
    say which *views* are served, which is a different question.
    """
    reason = None
    if coord_system == "lab" and record.lattice is None:
        reason = "no detector lattice was measured, so a hit's lattice ordinals cannot become positions"
    elif coord_system == "trans":
        try:
            hit_sql.layer_pitch(record)
        except ValueError:
            reason = "no sampling-layer pitch was measured, so a hit's layer cannot become a depth"
    if reason is not None:
        raise CapabilityError(
            f"coord_system={coord_system!r} is not available for experiment "
            f"{record.table_name!r}: {reason}.",
            field="coord_system", capability="statistics", kind=record.kind, reason=reason,
            table_name=record.table_name,
        )


def _fetch(con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _hit_cte(
    record: ExperimentRecord, spec: FilterSpec, coord_system: str,
    scope: tuple[ShowerColumns, ...], sampled: bool,
) -> tuple[str, dict[str, Any]]:
    """``h(c0, c1, c2[, c3], en)``: the selected showers' hits in the frame, and the bound parameters."""
    (x, y, z), frame_params = hit_sql.frame_xyz(coord_system, record)
    inner = (
        f"SELECT {x} AS c0, {y} AS c1, {z} AS c2, CAST(p.energy AS DOUBLE) AS en "
        f"FROM {hit_sql.proj_table(record, sampled)} p "
        f"WHERE {spec.where_sql('p')} AND {hit_sql.origin_filter(scope)}"
    )
    if coord_system == "local":
        cte = f"h AS (SELECT c0, c1, c2, sqrt(c0 * c0 + c1 * c1) AS c3, en FROM ({inner}))"
    else:
        cte = f"h AS ({inner})"
    return cte, {**spec.params(), **frame_params}


def _moment_sql(cte: str, variables_: tuple[Variable, ...]) -> str:
    parts = ["count(*) AS n", "sum(en) AS sum_e"]
    for i, v in enumerate(variables_):
        c = v.column
        parts += [
            f"avg({c}) AS m{i}", f"stddev_samp({c}) AS s{i}", f"stddev_pop({c}) AS sp{i}",
            f"min({c}) AS lo{i}", f"max({c}) AS hi{i}",
            f"quantile_cont({c}, {list(QUARTILES)}) AS q{i}",
            f"sum(en * {c}) AS ew{i}",
        ]
    return f"WITH {cte} SELECT {', '.join(parts)} FROM h"


def _bin_sql(v: Variable) -> str:
    if v.log10:
        return f"CAST(floor(log10({v.column}) * {1.0 / LOG_STEP!r}) AS BIGINT)"
    return f"CAST(floor({v.column} / {FINE_MM!r}) AS BIGINT)"


def _histogram_sql(cte: str, variables_: tuple[Variable, ...]) -> str:
    """Energy summed into the fine bins of every variable, one grouping set each."""
    k = len(variables_)
    names = ", ".join(f"b{i}" for i in range(k))
    bins = ", ".join(f"{_bin_sql(v)} AS b{i}" for i, v in enumerate(variables_))
    sets = ", ".join(f"(b{i})" for i in range(k))
    return (
        f"WITH {cte} SELECT grouping({names}) AS g, {names}, sum(en) AS w "
        f"FROM (SELECT {bins}, en FROM h) GROUP BY GROUPING SETS ({sets})"
    )


def _weighted_quartiles(rows: list[dict[str, Any]], index: int, k: int, v: Variable) -> list[float | None]:
    """The energy-weighted quartiles of variable ``index``, read off its fine histogram."""
    # ``grouping`` has one bit per argument, the first argument the most significant, set
    # when that column is *not* in the grouping set: set ``index`` has every bit but its own.
    mask = ((1 << k) - 1) ^ (1 << (k - 1 - index))
    mine = [r for r in rows if r["g"] == mask]
    lo = np.array([r[f"b{index}"] for r in mine], dtype=np.float64)
    w = np.array([r["w"] for r in mine], dtype=np.float64)
    if v.log10:
        return [None if q is None else float(10.0 ** q)
                for q in describe.weighted_quantiles(lo * LOG_STEP, w, LOG_STEP, QUARTILES)]
    return describe.weighted_quantiles(lo * FINE_MM, w, FINE_MM, QUARTILES)


def _note(n: int) -> str:
    if n == 0:
        return "No hits in this selection."
    notes = []
    if n == 1:
        notes.append("N = 1: a single hit; no spread can be estimated.")
    elif n == 2:
        notes.append("N = 2: the SD is one pairwise difference, 1 d.o.f.")
    if 1 < n < describe.ROBUST_N:
        notes.append(f"Quartiles interpolate between individual hits below N = {describe.ROBUST_N}.")
    return " ".join(notes)


def _column(v: Variable, i: int, n: int, moments: dict[str, Any], ew: list[float | None]) -> Column:
    if n == 0:
        return Column(v, 0, note=_note(0))
    q = moments[f"q{i}"]
    sd = moments[f"s{i}"] if n >= gaussian.MIN_MOMENT_SAMPLES else None
    return Column(
        variable=v, n=n, mean=moments[f"m{i}"], sd=sd, sd_population=moments[f"sp{i}"],
        minimum=moments[f"lo{i}"], q25=q[0], q50=q[1], q75=q[2], maximum=moments[f"hi{i}"],
        ew_mean=moments[f"ew{i}"] / moments["sum_e"], ew_q25=ew[0], ew_q50=ew[1], ew_q75=ew[2],
        note=_note(n),
    )


def scan(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
    coord_system: str, scope: tuple[ShowerColumns, ...], sampled: bool = False,
) -> Scan:
    """The two statements over the selected hits, reduced to one :class:`Column` per variable."""
    started = time.perf_counter()
    vs = variables(coord_system)
    cte, params = _hit_cte(record, spec, coord_system, scope, sampled)
    moments = _fetch(con, _moment_sql(cte, vs), params)[0]
    n = int(moments["n"])
    histograms = _fetch(con, _histogram_sql(cte, vs), params) if n else []
    columns = tuple(
        _column(v, i, n, moments, _weighted_quartiles(histograms, i, len(vs), v) if n else [None] * 3)
        for i, v in enumerate(vs)
    )
    return Scan(coord_system, columns, n, (time.perf_counter() - started) * 1000.0)


def describe_hits(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
    coord_system: str, scope: tuple[ShowerColumns, ...], sampled: bool = False,
) -> tuple[Scan, bool]:
    """``(scan, was_cached)``: the heavy pass, cached per selection, frame and shower scope.

    The key starts with the clamped selection (so the table name is first and a
    re-ingest invalidates it) and names the shower scope by what it selects, so
    ``both`` and ``a`` of a single-shower experiment share one entry.
    """
    key = (*spec.clamped(record).cache_key(), sampled, "c1", CACHE_VERSION, coord_system,
           "".join(s.key for s in scope))
    return physics_cache.get_or_compute(
        key, lambda: scan(con, record, spec, coord_system, scope, sampled), heavy=True)


def selection_counts(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
    scope: tuple[ShowerColumns, ...],
) -> tuple[int, int]:
    """``(events, hits)`` of the selection, exact, from the event table.

    The events with a hit of any selected shower and those showers' hit rows;
    a preview scans a sample of the hits but never of the events, so these stay
    exact beside it.
    """
    event = quote(naming.event_table(record.table_name))
    present = " OR ".join(f"({s.present_sql})" for s in scope)
    hits = " + ".join(s.hits for s in scope)
    events, rows = con.execute(
        f"SELECT count(*), coalesce(sum({hits}), 0) FROM {event} "
        f"WHERE {spec.where_sql()} AND ({present})",
        spec.params(),
    ).fetchone()
    return int(events), int(rows)


def _shifted(column: Column, offset: float) -> Column:
    """The ``z − offset`` row: every location statistic moved, the widths and the count not."""
    def move(value: float | None) -> float | None:
        return None if value is None else value - offset

    v = column.variable
    shifted = Variable("z_shifted", f"z {MINUS} {offset:g} mm", v.unit, v.column)
    return Column(
        shifted, column.n, move(column.mean), column.sd, column.sd_population,
        move(column.minimum), move(column.q25), move(column.q50), move(column.q75),
        move(column.maximum), move(column.ew_mean), move(column.ew_q25), move(column.ew_q50),
        move(column.ew_q75), column.note,
    )


def as_row(column: Column, offset_mm: float | None = None) -> dict[str, Any]:
    """One ``describe_row`` of the payload, numbers to six significant figures."""
    v = column.variable
    row: dict[str, Any] = {
        "key": v.key, "label": v.label, "unit": v.unit, "count": column.n,
        "mean": sig(column.mean), "sd": sig(column.sd), "sd_population": sig(column.sd_population),
        "min": sig(column.minimum), "q25": sig(column.q25), "q50": sig(column.q50),
        "q75": sig(column.q75), "max": sig(column.maximum),
        "ew_mean": sig(column.ew_mean), "ew_q25": sig(column.ew_q25),
        "ew_q50": sig(column.ew_q50), "ew_q75": sig(column.ew_q75),
    }
    if offset_mm is not None:
        row["display_offset_mm"] = offset_mm
    if column.note:
        row["note"] = column.note
    return row


def block(scan_: Scan, n_hits: int) -> dict[str, Any]:
    """The ``describe`` block: the frame's rows, the laboratory frame's shifted z row, the estimator text.

    ``n_hits`` is the selection's exact hit count; a row's ``count`` is the
    number of rows it was computed from, smaller only on a preview sample.
    """
    shifted = None
    if scan_.coord_system == "lab":
        z = next(c for c in scan_.columns if c.variable.key == "z")
        shifted = as_row(_shifted(z, ddl.CORE_SHIFT_Z_MM), ddl.CORE_SHIFT_Z_MM)
    return {
        "coord_system": scan_.coord_system,
        "rows": [as_row(c) for c in scan_.columns],
        "shifted_row": shifted,
        "n_hits": n_hits,
        "estimator": ESTIMATOR,
        "weighting_note": WEIGHTING_NOTE,
    }


def notes(
    record: ExperimentRecord, coord_system: str, scope: tuple[ShowerColumns, ...],
    scan_: Scan, n_hits: int, sampled: bool, percent: float,
) -> list[str]:
    """The explanatory sentences of the card: the frame, the shower scope, the sample."""
    out: list[str] = []
    if coord_system == "lab":
        out.append(
            "x, y, z are the measured cell-centre coordinates of the detector lattice, read "
            "through the stored coordinate arrays; the x lattice is irregular, so its quartiles "
            "are lattice positions. z is the raw detector depth. The row z − "
            f"{ddl.CORE_SHIFT_Z_MM:g} mm is the reference notebook's display offset "
            "(core.SHIFT_Z) as a labelled row, not another coordinate: volume, densities and "
            "centroid_z stay on the raw z."
        )
    elif coord_system == "trans":
        out.append(
            "Δx, Δy are each hit's offset from its own shower's entry point P0, and "
            f"Δz = kt × {hit_sql.layer_pitch(record):g} mm counts whole sampling layers from "
            "the shower's first layer; the frame is translated, not rotated."
        )
    else:
        out.append(
            "u, v, w are each hit's position in its own shower's frame, w along the incident "
            "direction from the entry point P0, so w < 0 lies upstream of it (see the "
            "negative-depth block). ρ = √(u² + v²) is the 2-D transverse radius from the shower "
            "axis, the reference notebook's r_local; core.py's r_local is the 3-D distance and "
            "is not this quantity."
        )
    if any(s.key == "b" for s in scope):
        out.append("Cells holding energy from both showers (A+B rows) are counted with shower B.")
    if sampled:
        out.append(
            f"Preview: computed from a {percent:g}% unbiased sample of the hit rows "
            f"({scan_.n_rows:,} of {n_hits:,}). The counts are the sample's, min and max are "
            "the sample's extremes, and the means and quartiles are estimates; release the "
            "slider for the exact table."
        )
    return [typographic(text) for text in out]
