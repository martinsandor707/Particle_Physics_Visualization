"""C8: the hit-level correlation matrix, with event-grouped jackknife intervals.

The notebook's figure (High_energy_notebook c31) is ``df[cols].corr()`` over
every hit of x_local, y_local, z_local, energy, incoming_momentum,
incoming_theta and incoming_phi. Three things in that matrix are not what they
look like, and this module answers each one:

* **The pairs are not independent.** p, θ and φ take one value per shower,
  repeated on every one of its hits, and the hits of one shower share its
  development, so Fisher's ``1 / sqrt(N - 3)`` with N = hits would quote
  ±0.0003 on everything. The scan returns its moment sums per *event group*
  and the interval is the grouped jackknife on Fisher's z of
  ``stats/jackknife.py`` - Student-t on G - 1 degrees of freedom - with the
  jackknife's ``n_eff`` and the naive iid SE beside it, so the reader sees how
  far the hit count overstates the precision.
* **φ is circular.** A linear r of φ depends on where the cut at ±π falls.
  No Σφ, Σφ² or Σφ·v is ever accumulated: φ enters the scan only as cos φ and
  sin φ, and its cells carry r = null, hatched, with Mardia's circular-linear
  R of the other variable and its jackknife SE. R is quoted only over
  ``jackknife.MIN_MARDIA_AZIMUTHS`` distinct azimuths - counted from the event
  table, not events - and its SE from ``jackknife.MIN_MARDIA_GROUPS`` groups,
  with the null expectation of R² beside it.
* **Per-shower values are weighted by multiplicity.** A hit-level pair weights
  each shower by its hit count, which grows with momentum. Pairs of two
  per-shower values (p, θ, φ among themselves) are therefore aggregated from
  the event table - the rule ``query/__init__.py`` states - once weighted by
  each shower's hits, which reproduces the hit-level value exactly (a test
  pins it), and once unweighted, each shower counting once: the value a
  per-event analysis would quote, given beside it.

**One scan.** The hits of the selection are read once: the count, Σ v_i and
Σ v_i v_j (i ≤ j) of eight variables - x, y, z of the chosen frame, the hit
energy, p, θ, cos φ and sin φ - 45 sums per group, G = min(64, N events)
groups (one per event up to 64 events: a delete-one-event jackknife). The sums
are cached in the physics cache; everything after them is NumPy on a few
kilobytes.

**Conditioning.** r is invariant under a shift of either variable, so each is
accumulated about a fixed offset - laboratory z about the front layer, x and y
about the lattice centre, p about the middle of the selected momentum range -
and ``Σ v² - (Σ v)² / n`` keeps the digits a narrow selection has left.

**Few azimuths.** Mardia's R is the multiple correlation of a variable on
(cos φ, sin φ): an intercept and two slopes, so three azimuths fit any variable
exactly and R = 1 whatever the data, and at the hit level it is then only the
between-shower share of the variance. R is therefore gated on distinct
azimuths, the design points of that fit, and a selection with only two -
where cos φ and sin φ are collinear and the closed form is 0/0 - is never
quoted. :func:`mardia_value` still returns the plain |r| there, so a
leave-one-group-out sample reduced to two azimuths cannot put rounding noise
into the jackknife SE.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..errors import CapabilityError, ValidationError
from ..stats import gaussian, jackknife
from ..stats.jackknife import FisherJackknife
from ..stats.metrics import fisher_z_interval
from ..text import typographic
from . import hit_sql, physics_cache
from . import showers as showers_mod
from .filters import FilterSpec
from .showers import ShowerColumns

#: The ``energy_scale`` request values: the notebook's linear GeV, or log10 GeV.
ENERGY_SCALES: tuple[str, ...] = ("linear", "log10")

DEFAULT_COORD_SYSTEM = "local"
DEFAULT_SHOWER = "both"
DEFAULT_ENERGY_SCALE = "linear"

#: Definition version of the cached sums; part of the cache key.
SUMS_VERSION = 1

#: The variables the hit scan accumulates, in order. φ appears only as cos and sin.
HIT_KEYS: tuple[str, ...] = ("x", "y", "z", "energy", "p", "theta", "cos_phi", "sin_phi")
#: The per-shower variables the event-table scan accumulates.
SHOWER_KEYS: tuple[str, ...] = ("p", "theta", "cos_phi", "sin_phi")

# Indices of the displayed variables (x, y, z, E, p, θ, φ) in the matrix.
_P, _TH, _PHI = 4, 5, 6
_SHOWER_LEVEL = (_P, _TH, _PHI)
# Where each displayed linear variable sits in the hit and the shower sums.
_HIT_INDEX = {0: 0, 1: 1, 2: 2, 3: 3, _P: 4, _TH: 5}
_SHOWER_INDEX = {_P: 0, _TH: 1}
_HIT_COS, _HIT_SIN = 6, 7
_SHOWER_COS, _SHOWER_SIN = 2, 3

#: The per-shower attributes the scans read, as ``(alias, ShowerColumns field)``.
_ATTRS: tuple[tuple[str, str], ...] = (
    ("mom", "momentum"), ("th", "theta"), ("ph", "phi"), ("nh", "hits"),
)
#: A shower enters only with every attribute defined, so all sums cover the same rows.
_COMPLETE = (
    "mom IS NOT NULL AND th IS NOT NULL AND ph IS NOT NULL AND nh > 0 "
    "AND isfinite(mom) AND isfinite(th) AND isfinite(ph)"
)

#: Within this of |r(cos φ, sin φ)| = 1 the two are collinear (two azimuths at most).
COLLINEAR_TOL = jackknife.COLLINEAR_TOL

#: The colour scale of a signed r: PuOr, symmetric about zero (CLAUDE.md
#: section 2). D3's matrix (``query/features.py``) carries the same block.
R_SCALE: dict[str, Any] = {"palette": "puor", "diverging": True, "vmin": -1, "vmax": 1,
                           "label": "Pearson r"}

#: Below this many events the matrix is labelled weak (CLAUDE.md's low-N table).
WEAK_BELOW_EVENTS = gaussian.MIN_ROBUST_SAMPLES

#: What one pair of a cell is, by the ``weighting`` key each cell carries.
WEIGHTINGS: dict[str, str] = {
    "hit": "Each hit is one pair.",
    "hit_shower": (
        "Each hit is one pair; the shower's value repeats on every one of its hits, so a "
        "shower counts in proportion to its hits, which grow with its momentum."
    ),
    "shower_by_hits": (
        "Both are per-shower values, aggregated from the event table with each shower "
        "weighted by its hit count, which reproduces the hit-level value; the per-shower "
        "value, each shower counted once, is given beside it."
    ),
}

#: The frames' axis variables: ``(key, label)`` per axis.
_FRAME_VARIABLES: dict[str, tuple[tuple[str, str], ...]] = {
    "local": (("u", "u (x_local)"), ("v", "v (y_local)"),
              ("w", "w (z_local, depth along the incident direction)")),
    "trans": (("dx", "Δx (x − P₀x, per-shower translated)"),
              ("dy", "Δy (y − P₀y, per-shower translated)"),
              ("dz", "Δz (own-shower layer × pitch)")),
    "lab": (("x", "x (detector)"), ("y", "y (detector)"), ("z", "z (detector, raw)")),
}


@dataclass(frozen=True)
class Variable:
    """One row and column of the matrix."""

    key: str
    label: str
    unit: str
    level: str                  # "hit" | "shower"
    circular: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "unit": self.unit,
                "level": self.level, "circular": self.circular}


def variables(coord_system: str, energy_scale: str) -> tuple[Variable, ...]:
    """The seven displayed variables: the frame's axes, the energy, p, θ and φ."""
    axes = tuple(Variable(key, label, "mm", "hit") for key, label in _FRAME_VARIABLES[coord_system])
    energy = (Variable("energy", "Hit energy E", "GeV", "hit") if energy_scale == "linear"
              else Variable("log10_energy", "log₁₀ hit energy", "log₁₀ GeV", "hit"))
    return axes + (
        energy,
        Variable("p", "Incident momentum p", "GeV", "shower"),
        Variable("theta", "Incident polar angle θ", "rad", "shower"),
        Variable("phi", "Incident azimuth φ", "rad", "shower", circular=True),
    )


# ------------------------------------------------------------------ sums --


@dataclass
class MomentSums:
    """Weight, Σ v_i and Σ v_i v_j per event group: the product of one scan.

    ``shifts`` were subtracted from each variable before accumulation; r does
    not depend on them.
    """

    keys: tuple[str, ...]
    shifts: tuple[float, ...]
    group: np.ndarray           # (G,) group id
    n: np.ndarray               # (G,) total weight: hits, or showers
    s: np.ndarray               # (G, k)
    q: np.ndarray               # (G, k, k), symmetric
    query_ms: float = 0.0

    @property
    def groups(self) -> int:
        return int(self.n.size)

    @property
    def total(self) -> float:
        return float(self.n.sum())

    def pearson(self) -> np.ndarray:
        """The Pearson matrix of the whole selection, ungated."""
        return jackknife.pearson_from_sums(self.n.sum(), self.s.sum(axis=0), self.q.sum(axis=0))

    @classmethod
    def empty(cls, keys: Sequence[str], shifts: Sequence[float]) -> "MomentSums":
        k = len(keys)
        return cls(tuple(keys), tuple(shifts), np.zeros(0, dtype=np.int64), np.zeros(0),
                   np.zeros((0, k)), np.zeros((0, k, k)))


@dataclass(frozen=True)
class Selection:
    """What the event table says the selection holds, before any hit is read."""

    n_events: int           # events with at least one complete selected shower
    n_showers: int          # complete selected showers
    n_hits: int             # their hits, by the event table's counts
    n_incomplete: int       # selected showers missing p, θ or φ, left out of every sum
    n_azimuths: int = 0     # distinct φ among the complete showers: Mardia's design points


def _centred(expr: str, shift: float) -> str:
    """``expr`` about a fixed offset; the offset is a number this module computed."""
    if shift == 0.0:
        return expr
    if not math.isfinite(shift):
        raise ValueError(f"non-finite conditioning shift {shift!r}")
    return f"({expr} - ({float(shift)!r}))"


def _sum_items(values: Sequence[str], weight: str | None, tag: str) -> list[str]:
    """``sum(w v_i)`` and ``sum(w v_i v_j)`` for i ≤ j, as select items."""
    w = f"{weight} * " if weight else ""
    k = len(values)
    items = [f"sum({w}{values[i]}) AS {tag}s{i}" for i in range(k)]
    items += [f"sum({w}{values[i]} * {values[j]}) AS {tag}q{i}_{j}"
              for i in range(k) for j in range(i, k)]
    return items


def _n_items(k: int) -> int:
    return k + k * (k + 1) // 2


def _unpack(rows: Sequence[Sequence[Any]], keys: Sequence[str], shifts: Sequence[float],
            n_col: int, first: int, query_ms: float) -> MomentSums:
    """Rows of ``g, ..., Σv_i ..., Σv_iv_j (i ≤ j) ...`` as a :class:`MomentSums`."""
    k = len(keys)
    groups = len(rows)
    group = np.array([int(r[0]) for r in rows], dtype=np.int64)
    n = np.array([float(r[n_col]) for r in rows], dtype=np.float64)
    s = np.zeros((groups, k))
    q = np.zeros((groups, k, k))
    for g, row in enumerate(rows):
        col = first
        for i in range(k):
            s[g, i] = float(row[col])
            col += 1
        for i in range(k):
            for j in range(i, k):
                q[g, i, j] = q[g, j, i] = float(row[col])
                col += 1
    return MomentSums(tuple(keys), tuple(shifts), group, n, s, q, query_ms)


def _momentum_shift(spec: FilterSpec, showers: tuple[ShowerColumns, ...]) -> float:
    """The middle of the selected momentum range of the chosen showers."""
    ranges = {"e1": (spec.e1_min, spec.e1_max), "e2": (spec.e2_min, spec.e2_max)}
    los, his = [], []
    for s in showers:
        lo, hi = ranges.get(s.momentum, (None, None))
        if lo is not None and hi is not None and math.isfinite(lo) and math.isfinite(hi):
            los.append(float(lo))
            his.append(float(hi))
    if not los:
        return 0.0
    return 0.5 * (min(los) + max(his))


def shifts(record: ExperimentRecord, spec: FilterSpec, showers: tuple[ShowerColumns, ...],
           coord_system: str) -> tuple[float, ...]:
    """The conditioning offset of each of :data:`HIT_KEYS`; r does not depend on them."""
    x0 = y0 = z0 = 0.0
    if coord_system == "lab" and record.lattice is not None:
        lattice = record.lattice
        x0 = 0.5 * (lattice.x.lo + lattice.x.hi)
        y0 = 0.5 * (lattice.y.lo + lattice.y.hi)
        z0 = lattice.z.lo
    p0 = _momentum_shift(spec.clamped(record), showers)
    return (x0, y0, z0, 0.0, p0, 0.0, 0.0, 0.0)


def _attr_cte(record: ExperimentRecord, spec: FilterSpec, showers: tuple[ShowerColumns, ...]) -> str:
    return hit_sql.shower_attr_cte(record, spec, showers, attrs=_ATTRS)


def selection(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
              showers: tuple[ShowerColumns, ...]) -> Selection:
    """Count the selection's events, showers, hits and distinct azimuths from the event table."""
    row = con.execute(
        f"""
        WITH {_attr_cte(record, spec, showers)}
        SELECT count(DISTINCT event_number) FILTER (WHERE {_COMPLETE}),
               count(*) FILTER (WHERE {_COMPLETE}),
               coalesce(sum(nh) FILTER (WHERE {_COMPLETE}), 0),
               count(*),
               count(DISTINCT ph) FILTER (WHERE {_COMPLETE})
        FROM sh
        """,
        spec.params(),
    ).fetchone()
    n_events, n_showers, n_hits, n_present, n_azimuths = (int(v or 0) for v in row)
    return Selection(n_events, n_showers, n_hits, n_present - n_showers, n_azimuths)


def event_sums_sql(record: ExperimentRecord, spec: FilterSpec,
                   showers: tuple[ShowerColumns, ...], n_events: int) -> tuple[str, int]:
    """``(SQL, k)``: per group, the hit-weighted and the unweighted per-shower sums."""
    group, _ = hit_sql.group_key(n_events, p="sh")
    p0 = _momentum_shift(spec.clamped(record), showers)
    values = (_centred("mom", p0), "th", "cos(ph)", "sin(ph)")
    columns = ", ".join(f"{v} AS v{i}" for i, v in enumerate(values))
    names = [f"v{i}" for i in range(len(values))]
    items = ", ".join(_sum_items(names, "w", "w") + _sum_items(names, None, "u"))
    sql = f"""
        WITH {_attr_cte(record, spec, showers)},
        e AS (
            SELECT {group} AS g, nh AS w, {columns}
            FROM sh WHERE {_COMPLETE}
        )
        SELECT g, count(*) AS n_u, sum(w) AS n_w, {items}
        FROM e GROUP BY g ORDER BY g
    """
    return sql, len(values)


def event_sums(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
               showers: tuple[ShowerColumns, ...], n_events: int) -> tuple[MomentSums, MomentSums]:
    """Per-shower p, θ, cos φ, sin φ sums per event group: ``(hit-weighted, unweighted)``."""
    p0 = _momentum_shift(spec.clamped(record), showers)
    shift = (p0, 0.0, 0.0, 0.0)
    if n_events <= 0:
        return MomentSums.empty(SHOWER_KEYS, shift), MomentSums.empty(SHOWER_KEYS, shift)
    sql, k = event_sums_sql(record, spec, showers, n_events)
    start = time.perf_counter()
    rows = con.execute(sql, spec.params()).fetchall()
    ms = (time.perf_counter() - start) * 1000.0
    width = _n_items(k)
    weighted = _unpack(rows, SHOWER_KEYS, shift, n_col=2, first=3, query_ms=ms)
    unweighted = _unpack(rows, SHOWER_KEYS, shift, n_col=1, first=3 + width, query_ms=ms)
    return weighted, unweighted


def hit_scan_sql(record: ExperimentRecord, spec: FilterSpec, showers: tuple[ShowerColumns, ...],
                 coord_system: str, energy_scale: str, n_events: int,
                 sampled: bool = False) -> tuple[str, dict[str, Any], tuple[float, ...]]:
    """``(SQL, params, shifts)`` of the one grouped hit scan."""
    (x, y, z), frame_params = hit_sql.frame_xyz(coord_system, record, p="p")
    group, _ = hit_sql.group_key(n_events, p="p")
    offsets = shifts(record, spec, showers, coord_system)
    energy = "p.energy" if energy_scale == "linear" else "log10(p.energy)"
    # φ is read only through its cosine and sine: never as a linear variable.
    exprs = (x, y, z, energy, "s.mom", "s.th", "cos(s.ph)", "sin(s.ph)")
    values = [_centred(e, shift) for e, shift in zip(exprs, offsets)]
    columns = ", ".join(f"{v} AS v{i}" for i, v in enumerate(values))
    names = [f"v{i}" for i in range(len(values))]
    positive = " AND p.energy > 0" if energy_scale == "log10" else ""
    sql = f"""
        WITH {_attr_cte(record, spec, showers)},
        shc AS (SELECT event_number, b, mom, th, ph FROM sh WHERE {_COMPLETE}),
        h AS (
            SELECT {group} AS g, {columns}
            FROM {hit_sql.proj_table(record, sampled)} p
            JOIN shc s ON {hit_sql.own_shower_join('p', 's')}
            WHERE {spec.where_sql('p')} AND {hit_sql.origin_filter(showers)}{positive}
        )
        SELECT g, count(*) AS n, {', '.join(_sum_items(names, None, ''))}
        FROM h GROUP BY g ORDER BY g
    """
    return sql, {**spec.params(), **frame_params}, offsets


def hit_sums(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
             showers: tuple[ShowerColumns, ...], coord_system: str, energy_scale: str,
             n_events: int, sampled: bool = False) -> MomentSums:
    """The hit scan's sums per event group (uncached)."""
    sql, params, offsets = hit_scan_sql(record, spec, showers, coord_system, energy_scale,
                                        n_events, sampled)
    if n_events <= 0:
        return MomentSums.empty(HIT_KEYS, offsets)
    start = time.perf_counter()
    rows = con.execute(sql, params).fetchall()
    ms = (time.perf_counter() - start) * 1000.0
    return _unpack(rows, HIT_KEYS, offsets, n_col=1, first=2, query_ms=ms)


# -------------------------------------------------------------- analysis --


@dataclass
class Mardia:
    """Mardia's circular-linear R of one variable with φ, and its jackknife SE."""

    R: float | None = None
    se: float | None = None


@dataclass
class Analysis:
    """Everything the payload is rendered from, unrounded."""

    coord_system: str
    shower: str
    energy_scale: str
    showers: tuple[ShowerColumns, ...]
    variables: tuple[Variable, ...]
    selection: Selection
    hit: MomentSums
    hit_fit: FisherJackknife
    shower_w: MomentSums
    shower_w_fit: FisherJackknife
    shower_u: MomentSums
    shower_u_fit: FisherJackknife
    mardia_hit: dict[int, Mardia] = field(default_factory=dict)        # x, y, z, E with φ
    mardia_shower_w: dict[int, Mardia] = field(default_factory=dict)   # p, θ with φ, hit-weighted
    mardia_shower_u: dict[int, Mardia] = field(default_factory=dict)   # p, θ with φ, per shower
    mardia_reason: str | None = None   # why no Mardia R is quoted, else None
    sampled: bool = False
    sample_percent: float = 100.0
    cached: bool = False
    planned_groups: int = 0

    @property
    def groups(self) -> int:
        return self.hit.groups

    @property
    def n_hits(self) -> int:
        return int(round(self.hit.total))

    @property
    def interval_quoted(self) -> bool:
        return (self.selection.n_events >= jackknife.MIN_R_EVENTS
                and self.groups >= jackknife.MIN_JACKKNIFE_GROUPS)


def _check(record: ExperimentRecord, coord_system: str, energy_scale: str) -> None:
    if coord_system not in hit_sql.FRAMES:
        raise ValidationError(
            f"coord_system must be one of {', '.join(hit_sql.FRAMES)}; got {coord_system!r}. "
            "The hit-level correlations are taken in a frame each hit has: the D-frame is an "
            "ensemble co-registration, not a per-hit coordinate.",
            field="coord_system",
        )
    if energy_scale not in ENERGY_SCALES:
        raise ValidationError(
            f"energy_scale must be one of {', '.join(ENERGY_SCALES)}; got {energy_scale!r}.",
            field="energy_scale",
        )
    reason = None
    if coord_system == "lab" and record.lattice is None:
        reason = "No detector lattice was measured for this experiment."
    elif coord_system == "trans":
        try:
            hit_sql.layer_pitch(record)
        except ValueError:
            reason = "No sampling-layer pitch was measured for this experiment."
    if reason is not None:
        raise CapabilityError(
            f"coord_system={coord_system!r} is not available for experiment "
            f"{record.table_name!r}: {reason}",
            field="coord_system", capability=f"frame-{coord_system}", kind=record.kind,
            reason=reason, table_name=record.table_name,
        )


def mardia_value(r_xc: float, r_xs: float, r_cs: float) -> float | None:
    """Mardia's R of x with an angle from r(x, cos), r(x, sin), r(cos, sin), in [0, 1]: :func:`jackknife.mardia_r`."""
    return jackknife.mardia_r(r_xc, r_xs, r_cs)


def _mardia(sums: MomentSums, x: int, c: int, s: int) -> Mardia:
    """R of variable ``x`` with the angle whose cos, sin are ``c``, ``s``, and its jackknife SE.

    Called only once :func:`mardia_reason` has passed the selection. The SE is
    never clamped to zero: an exact fit in every leave-one-out sample is what
    too few directions produce, and the azimuth gate rules that out first.
    """
    value, se = jackknife.mardia_jackknife(sums.n, sums.s, sums.q, x, c, s)
    return Mardia(value, se)


def mardia_reason(a: Analysis) -> str | None:
    """Why the selection's φ cells carry no Mardia R; ``None`` when they do.

    The gate counts distinct azimuths, not events: showers sharing a direction
    are one design point of the fit, however many events hold them.
    """
    reason = jackknife.mardia_gate(a.selection.n_azimuths)
    if reason is None and azimuths(a) != "many":
        reason = ("cos φ and sin φ are collinear: the selection's azimuths are at most two "
                  "directions, which cannot constrain a dependence on the direction.")
    return reason


def azimuths(a: Analysis) -> str:
    """``"none"``, ``"one"``, ``"two"`` or ``"many"``: how many azimuths the selection's hits carry."""
    if a.selection.n_events < jackknife.MIN_R_EVENTS or a.hit.groups == 0:
        return "none"
    r = a.hit_fit.r
    spread = [math.isfinite(float(r[i, i])) for i in (_HIT_COS, _HIT_SIN)]
    if not any(spread):
        return "one"
    r_cs = float(r[_HIT_COS, _HIT_SIN])
    if not all(spread) or not math.isfinite(r_cs) or 1.0 - abs(r_cs) <= COLLINEAR_TOL:
        return "two"
    return "many"


def analyse(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, *,
            coord_system: str = DEFAULT_COORD_SYSTEM, shower: str = DEFAULT_SHOWER,
            energy_scale: str = DEFAULT_ENERGY_SCALE, sampled: bool = False,
            sample_percent: float = 100.0) -> Analysis:
    """Run the scans (the hit scan through the physics cache) and every estimator."""
    _check(record, coord_system, energy_scale)
    chosen = showers_mod.of(record, shower)
    picked = selection(con, record, spec, chosen)
    n_events = picked.n_events
    planned = jackknife.n_groups(n_events)

    key = (*spec.clamped(record).cache_key(), bool(sampled), "c8", SUMS_VERSION, coord_system,
           ",".join(s.key for s in chosen), energy_scale, planned)
    hit, cached = physics_cache.get_or_compute(
        key,
        lambda: hit_sums(con, record, spec, chosen, coord_system, energy_scale, n_events, sampled),
        heavy=True,
    )
    # Event-table products are milliseconds and never cached.
    shower_w, shower_u = event_sums(con, record, spec, chosen, n_events)

    hit_fit = jackknife.fisher_jackknife(hit.n, hit.s, hit.q, n_events)
    shower_w_fit = jackknife.fisher_jackknife(shower_w.n, shower_w.s, shower_w.q, n_events)
    shower_u_fit = jackknife.fisher_jackknife(shower_u.n, shower_u.s, shower_u.q, n_events)

    analysis = Analysis(
        coord_system=coord_system, shower=shower, energy_scale=energy_scale, showers=chosen,
        variables=variables(coord_system, energy_scale), selection=picked,
        hit=hit, hit_fit=hit_fit, shower_w=shower_w, shower_w_fit=shower_w_fit,
        shower_u=shower_u, shower_u_fit=shower_u_fit,
        sampled=bool(sampled), sample_percent=float(sample_percent), cached=cached,
        planned_groups=planned,
    )
    analysis.mardia_reason = mardia_reason(analysis)
    if n_events >= jackknife.MIN_R_EVENTS and analysis.mardia_reason is None:
        for i in range(4):
            analysis.mardia_hit[i] = _mardia(hit, _HIT_INDEX[i], _HIT_COS, _HIT_SIN)
        for i in (_P, _TH):
            x = _SHOWER_INDEX[i]
            analysis.mardia_shower_w[i] = _mardia(shower_w, x, _SHOWER_COS, _SHOWER_SIN)
            analysis.mardia_shower_u[i] = _mardia(shower_u, x, _SHOWER_COS, _SHOWER_SIN)
    return analysis


# ---------------------------------------------------------------- render --


Pair = tuple[float | None, tuple[float, float] | None, float | None, float | None]


def _finite(value: float) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def _pair(fit: FisherJackknife, i: int, j: int) -> Pair:
    """``(r, ci95, se_z, n_eff)`` of one pair of a fit, unrounded; non-finite → None."""
    r = _finite(fit.r[i, j])
    if r is None:
        return None, None, None, None
    lo, hi = _finite(fit.lo[i, j]), _finite(fit.hi[i, j])
    ci = (lo, hi) if lo is not None and hi is not None else None
    n_eff = _finite(fit.n_eff[i, j]) if ci is not None else None
    return r, ci, _finite(fit.se_z[i, j]), n_eff


def _se_iid(n_hits: int) -> float | None:
    """Fisher's SE of atanh r were the hits independent pairs: what the hit count would claim."""
    return 1.0 / math.sqrt(n_hits - 3) if n_hits >= 4 else None


def _cell(r: float | None = None, ci: tuple[float, float] | None = None,
          se_z: float | None = None, n_eff: float | None = None, se_iid: float | None = None,
          hatched: bool = False, weighting: str = "hit", event_r: float | None = None,
          event_ci: tuple[float, float] | None = None,
          mardia: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "r": sig(r),
        "ci95": [sig(ci[0]), sig(ci[1])] if ci else None,
        "se_z": sig(se_z),
        "n_eff": sig(n_eff),
        "se_iid": sig(se_iid),
        "hatched": bool(hatched),
        "weighting": weighting,
        "per_shower_r": sig(event_r),
        "per_shower_ci95": [sig(event_ci[0]), sig(event_ci[1])] if event_ci else None,
        "mardia": mardia,
    }


def _null_r2(a: Analysis) -> float | None:
    """E[R²] under no association over the selection's showers, each counted once."""
    return jackknife.mardia_null_r2(a.selection.n_showers)


def _mardia_dict(a: Analysis, weighted: Mardia,
                 per_shower: Mardia | None = None) -> dict[str, Any] | None:
    if weighted.R is None and (per_shower is None or per_shower.R is None):
        return None
    return {
        "R": sig(weighted.R), "se": sig(weighted.se),
        "per_shower_R": sig(per_shower.R) if per_shower else None,
        "per_shower_se": sig(per_shower.se) if per_shower else None,
        "null_R2": sig(_null_r2(a)),
    }


def _matrix_cell(a: Analysis, i: int, j: int) -> dict[str, Any]:
    shower_i, shower_j = i in _SHOWER_LEVEL, j in _SHOWER_LEVEL
    weighting = ("shower_by_hits" if shower_i and shower_j
                 else "hit_shower" if shower_i or shower_j else "hit")
    if _PHI in (i, j):
        other = j if i == _PHI else i
        if other == _PHI:
            return _cell(hatched=True, weighting=weighting)
        if other in _SHOWER_INDEX:
            mardia = _mardia_dict(a, a.mardia_shower_w.get(other, Mardia()),
                                  a.mardia_shower_u.get(other, Mardia()))
        else:
            mardia = _mardia_dict(a, a.mardia_hit.get(other, Mardia()))
        return _cell(hatched=True, weighting=weighting, mardia=mardia)
    if shower_i and shower_j:
        si, sj = _SHOWER_INDEX[i], _SHOWER_INDEX[j]
        r, ci, se_z, n_eff = _pair(a.shower_w_fit, si, sj)
        event_r, event_ci, _, _ = _pair(a.shower_u_fit, si, sj)
        # Weighted by every selected hit, whether or not the hit cells were sampled.
        hits = a.selection.n_hits
    else:
        r, ci, se_z, n_eff = _pair(a.hit_fit, _HIT_INDEX[i], _HIT_INDEX[j])
        event_r = event_ci = None
        hits = a.n_hits
    se_iid = _se_iid(hits) if r is not None and i != j else None
    return _cell(r, ci, se_z, n_eff, se_iid, False, weighting, event_r, event_ci)


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def _method(a: Analysis) -> str:
    g = a.groups
    if g == 0:
        return "event-grouped jackknife: no events in this selection"
    unit = ("one event each" if a.selection.n_events <= jackknife.MAX_GROUPS
            else f"event_number mod {a.planned_groups}")
    if a.interval_quoted:
        return f"event-grouped jackknife, {_plural(g, 'group')} ({unit})"
    return (f"event-grouped jackknife, {_plural(g, 'group')} ({unit}); too few for an interval, "
            f"which needs {jackknife.MIN_JACKKNIFE_GROUPS}")


def _interval_label(a: Analysis) -> str:
    n = a.selection.n_events
    if n < jackknife.MIN_R_EVENTS:
        return (f"none: a correlation needs at least {jackknife.MIN_R_EVENTS} events; this "
                f"selection has {n}")
    if not a.interval_quoted:
        return (f"none: an interval needs at least {jackknife.MIN_JACKKNIFE_GROUPS} event groups; "
                f"this selection has {a.groups}")
    # The label has one owner, metrics.fisher_z_interval; r and SE do not enter it.
    probe = fisher_z_interval(0.0, n, se_z=1.0, dof=a.groups - 1)
    return probe.label if probe is not None else "95% event-grouped jackknife on Fisher z"


def _no_spread(a: Analysis) -> list[str]:
    """The displayed variables with no spread in this selection."""
    if a.selection.n_events < jackknife.MIN_R_EVENTS:
        return []
    out = []
    diag = np.diag(a.hit_fit.r)
    for i in range(_PHI):
        if not math.isfinite(float(diag[_HIT_INDEX[i]])):
            out.append(a.variables[i].label)
    return out


def _notes(a: Analysis) -> list[str]:
    sel = a.selection
    g = a.groups
    notes: list[str] = []
    if sel.n_events == 0:
        notes.append("No events with hits match the current selection.")
        return [typographic(n) for n in notes]
    if sel.n_events < jackknife.MIN_R_EVENTS:
        notes.append(
            f"Correlations need at least {jackknife.MIN_R_EVENTS} events; this selection holds "
            f"{sel.n_events}, so every cell is empty.")
    elif sel.n_events < WEAK_BELOW_EVENTS:
        quantile = (f" (t₀.₉₇₅ = {gaussian.t_quantile_975(g - 1):.2f} on {g - 1} dof)"
                    if a.interval_quoted else "")
        notes.append(
            f"Weak (N = {sel.n_events} events): every r rests on few independent showers, and "
            f"its interval on {_plural(g, 'jackknife group')}{quantile}.")
    notes.append(
        f"Hits are not independent pairs: p, θ and φ take one value per shower, repeated on "
        f"every one of its hits, and the hits of one shower share its development. The "
        f"sampling unit is the event. Intervals are a grouped jackknife on Fisher's "
        f"z = atanh r over {g} event groups (Student-t on G − 1 degrees of freedom), quoted "
        f"from {jackknife.MIN_JACKKNIFE_GROUPS} groups and |r| < 1. n_eff = 3 + 1/SE² is the "
        f"number of independent pairs the interval is worth; se_iid = 1/√(N − 3) with "
        f"N = {a.n_hits:,} hits is the naive standard error a hit count would claim.")
    if g and g < a.planned_groups:
        where = (f"The {a.sample_percent:g}% sample holds hits from" if a.sampled
                 else "The selection's event numbers fall into")
        notes.append(f"{where} {g} of the {a.planned_groups} jackknife groups.")
    notes.append(
        f"φ is circular, so it has no linear correlation: no Σφ or Σφ² is accumulated, and its "
        f"cells are hatched with r empty. They carry Mardia's circular–linear R of the other "
        f"variable with (cos φ, sin φ), from 0 (no association) to 1, with no sign because a "
        f"circle has no order, quoted from {jackknife.MIN_MARDIA_AZIMUTHS} distinct azimuths, "
        f"and its jackknife standard error from {jackknife.MIN_MARDIA_GROUPS} event groups. R "
        f"is never negative: with no association R² still averages 2/(N − 1) over N showers "
        f"each counted once (null_R2, N = {sel.n_showers:,}), the reference for per_shower_R; "
        f"a hit-weighted R counts a shower by its hits and has no such simple reference.")
    if a.mardia_reason is not None and sel.n_events >= jackknife.MIN_R_EVENTS:
        notes.append(f"{a.mardia_reason} The φ cells carry no R.")
    notes.append(
        "p, θ and φ are per-shower values: a cell pairing one with a hit variable counts each "
        "shower in proportion to its hits, as the notebook's hit-level matrix does. Pairs of "
        "two per-shower values come from the event table, weighted by hits, which equals the "
        "hit-level value, with the per-shower value (each shower counted once) beside it.")
    if a.energy_scale == "linear":
        notes.append(
            "Hit energy is linear, as in the notebook: it spans about fifteen decades, so its r "
            "is set by the most energetic hits. energy_scale=log10 shows the bulk.")
    else:
        notes.append("Hit energy enters as log₁₀ E (every stored hit has E > 0).")
    if a.coord_system == "trans":
        notes.append(
            "Δz is the hit's own-shower layer times the layer pitch, so it takes whole-layer "
            "values.")
    elif a.coord_system == "lab":
        notes.append("x, y, z are the measured lattice coordinates of each hit's cell (raw z).")
    if sel.n_incomplete:
        notes.append(
            f"{sel.n_incomplete:,} selected showers lack p, θ or φ and are left out of every "
            "cell.")
    flat = _no_spread(a)
    if flat:
        notes.append(f"No spread in this selection, so no correlation: {', '.join(flat)}.")
    if a.sampled:
        notes.append(
            f"Drag preview: the hit cells come from the {a.sample_percent:g}% Bernoulli sample "
            f"of hits ({a.n_hits:,} hits); the per-shower cells are exact. Release the slider "
            "for the exact matrix.")
    return [typographic(n) for n in notes]


def render(a: Analysis) -> dict[str, Any]:
    """The payload body (the route adds ``meta`` and ``filter``)."""
    k = len(a.variables)
    quoted = a.interval_quoted
    return {
        "variables": [v.as_dict() for v in a.variables],
        "matrix": [[_matrix_cell(a, i, j) for j in range(k)] for i in range(k)],
        "n_hits": a.n_hits,
        "n_events": a.selection.n_events,
        "n_showers": a.selection.n_showers,
        "groups": a.groups,
        "dof": a.groups - 1 if quoted else None,
        "weak": a.selection.n_events < WEAK_BELOW_EVENTS,
        "method": typographic(_method(a)),
        "interval": typographic(_interval_label(a)),
        "scale": dict(R_SCALE),
        "mardia": {
            "n_azimuths": a.selection.n_azimuths,
            "min_azimuths": jackknife.MIN_MARDIA_AZIMUTHS,
            "min_groups": jackknife.MIN_MARDIA_GROUPS,
            "null_R2": sig(_null_r2(a)),
            "reason": typographic(a.mardia_reason) if a.mardia_reason else None,
        },
        "coord_system": a.coord_system,
        "energy_scale": a.energy_scale,
        "shower": a.shower,
        "showers": [s.label for s in a.showers],
        "weightings": dict(WEIGHTINGS),
        "notes": _notes(a),
    }


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, *,
            coord_system: str = DEFAULT_COORD_SYSTEM, shower: str = DEFAULT_SHOWER,
            energy_scale: str = DEFAULT_ENERGY_SCALE, sampled: bool = False,
            sample_percent: float = 100.0) -> tuple[dict[str, Any], Analysis]:
    """``(payload body, analysis)`` of one request."""
    analysis = analyse(con, record, spec, coord_system=coord_system, shower=shower,
                       energy_scale=energy_scale, sampled=sampled, sample_percent=sample_percent)
    return render(analysis), analysis
