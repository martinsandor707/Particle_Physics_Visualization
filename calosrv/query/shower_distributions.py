"""C4, the showers' incident kinematics: per-momentum-bin distributions of θ, φ and p.

The distribution card (Page 1, ``distribution``) overlays one histogram per
1 GeV bin of each shower's *own* incident momentum - the reference notebook's
``hue='incoming_momentum_bin'`` - for seven quantities. θ, φ and p are
properties of a shower, one value each, so they are read from the event table
alone, one row per shower; ``query/hit_distributions.py`` serves the hit
quantities (u, v, w and hit energy) and reuses what this module owns for every
C4 quantity: the series, the display window and its disclosure, and the
payload's exact counts.

**The series.** Each shower sits in its own momentum bin - shower A by
``incoming_momentum_bin_A``, B by ``_B`` - read from the producer's integer
column, never re-derived from a float momentum. A bin is labelled "k–k+1 GeV"
only when the momenta found in it lie inside [k, k+1)
(``stats.momentum.relabel_bins``). Series are ordered by bin, at most
``stats.momentum.MAX_CLASSES``, and sparse-trimmed: an offset into the shared
edges and the span from the first to the last non-zero bin.

**Weighting.** The notebook histograms θ, φ and p from a 50 000-hit sample,
so each shower counts once per hit. Both readings are offered and named:
``shower`` counts each shower once; ``hit`` weights it by its hit count - the
notebook's hit-weighted sample computed exactly from the event table, with no
sampling noise. The Rice bin count follows showers in both, because hits of
one shower share its θ, φ and p and add no independent values.

**φ wraps.** An azimuth is drawn over its full period (−π, π], never cropped
- a percentile window would invent an end where the data wrap - and never
averaged: each series carries its mean resultant length R̄ over its showers'
directions and the Rayleigh p beside it, and no linear mean or SD of φ exists
anywhere in the payload (CLAUDE.md section 2).

**Display window.** The 1st–99th percentile of the plotted weights, pooled
over the series, rounded outward (CLAUDE.md section 2); what lies outside is
counted per series as ``below``/``above`` and never dropped. Below
:data:`ROBUST_N` showers the full range is shown and labelled provisional.
Counts are exact; a bar of 3 is three showers, so there is no density floor.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig
from ..errors import ValidationError
from ..stats import circular, clip, gaussian, histogram, momentum
from ..text import listed, typographic
from . import showers as showers_mod
from .filters import FilterSpec
from .showers import ShowerColumns

#: The request's quantities, by family.
SHOWER_QUANTITIES: tuple[str, ...] = ("theta", "phi", "p")
HIT_QUANTITIES: tuple[str, ...] = ("u", "v", "w", "energy")
QUANTITY_KEYS: tuple[str, ...] = HIT_QUANTITIES + SHOWER_QUANTITIES

WEIGHT_SHOWER = "shower"
WEIGHT_HIT = "hit"
WEIGHTINGS: tuple[str, ...] = (WEIGHT_SHOWER, WEIGHT_HIT)

#: Below this many showers a percentile interpolates between individual events
#: (CLAUDE.md section 2, the robust floor): the full range is shown instead and
#: called provisional.
ROBUST_N = gaussian.MIN_ROBUST_SAMPLES

#: Series smaller than this do not set the shared Rice bin count, so a sliver
#: of a bin cut by a slider cannot coarsen every well-measured series.
RICE_FLOOR_N = histogram.MIN_HISTOGRAM_SAMPLES

#: Incident-momentum histogram bins: tenths of a GeV, which tile every 1 GeV
#: momentum bin exactly. The payload guard may widen them to these sizes.
P_BIN_TENTHS: dict[int, int] = {1: 1, 2: 2, 4: 5}

#: The coarsening factors the payload guard tries, in order (count-conserving).
COARSEN_STEPS: tuple[int, ...] = (1, 2, 4)

#: The low and high percentiles of the display window, by default.
DEFAULT_CLIP: tuple[float, float] = (clip.DEFAULT_LOW_PERCENTILE, clip.DEFAULT_HIGH_PERCENTILE)


@dataclass(frozen=True)
class Quantity:
    """What one C4 quantity is, as the payload's ``quantity`` block names it."""

    key: str
    symbol: str
    label: str
    unit: str
    scale: str          # "linear" | "log10": how the axis is drawn
    source: str         # "hits" | "showers": what one count is

    def block(self, weighting: str, bin_width: float, bin_unit: str) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "unit": self.unit, "scale": self.scale,
                "source": self.source, "weighting": weighting,
                "bin_width": sig(bin_width), "bin_unit": bin_unit}


QUANTITIES: dict[str, Quantity] = {
    "u": Quantity("u", "u", "u — Local-frame transverse coordinate (x_local)", "mm", "linear",
                  "hits"),
    "v": Quantity("v", "v", "v — Local-frame transverse coordinate (y_local)", "mm", "linear",
                  "hits"),
    "w": Quantity("w", "w", "w — depth along the incident direction (z_local)", "mm", "linear",
                  "hits"),
    "energy": Quantity("energy", "E", "Hit energy", "GeV", "log10", "hits"),
    "theta": Quantity("theta", "θ", "θ — incident polar angle", "rad", "linear", "showers"),
    "phi": Quantity("phi", "φ", "φ — incident azimuth", "rad", "linear", "showers"),
    "p": Quantity("p", "p", "p — incident momentum", "GeV", "linear", "showers"),
}

_WEIGHTING_TEXT = {
    WEIGHT_SHOWER: "shower count",
    WEIGHT_HIT: "hit count (each shower weighted by its hits)",
}


# ------------------------------------------------------------------ sample --


@dataclass
class ShowerSample:
    """One row per selected shower: its own momentum bin and incident kinematics."""

    mb: np.ndarray        # int64, the producer's momentum bin
    p: np.ndarray         # GeV
    theta: np.ndarray     # rad
    phi: np.ndarray       # rad, wrapped onto (−π, π]
    hits: np.ndarray      # float64, the shower's hit rows
    placed: np.ndarray    # bool, the shower passes the per-shower frame gate
    n_no_bin: int         # selected showers with no momentum bin, excluded and counted
    elapsed_ms: float = 0.0

    @property
    def n(self) -> int:
        return int(self.mb.size)


def _column(data: dict[str, Any], name: str, dtype, fill) -> tuple[np.ndarray, np.ndarray]:
    """``(values, missing)`` of a fetched column, NULLs filled with ``fill``."""
    raw = np.ma.asarray(data[name])
    missing = np.ma.getmaskarray(raw)
    return np.asarray(np.ma.filled(raw, fill), dtype=dtype), missing


def fetch(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
          selected: Sequence[ShowerColumns], gate: str | None = None) -> ShowerSample:
    """Every selected shower of the selection, one row each, from the event table.

    ``gate`` is the event-table predicate of the per-shower frames
    (``capabilities.frame_gate``); a shower failing it cannot be placed in
    the Local frame, and the hit quantities count it out by name.
    """
    started = time.perf_counter()
    event = quote(naming.event_table(record.table_name))
    placed = f"({gate})" if gate else "TRUE"
    parts = [
        f"SELECT CAST({s.momentum_bin} AS INTEGER) AS mb, CAST({s.momentum} AS DOUBLE) AS p, "
        f"CAST({s.theta} AS DOUBLE) AS th, CAST({s.phi} AS DOUBLE) AS ph, "
        f"CAST({s.hits} AS DOUBLE) AS w, {placed} AS placed "
        f"FROM {event} WHERE {spec.where_sql()} AND {s.present_sql}"
        for s in selected
    ]
    data = con.execute("\nUNION ALL\n".join(parts), spec.params()).fetchnumpy()
    mb, no_bin = _column(data, "mb", np.int64, -1)
    p, _ = _column(data, "p", np.float64, np.nan)
    theta, _ = _column(data, "th", np.float64, np.nan)
    phi, _ = _column(data, "ph", np.float64, np.nan)
    hits, _ = _column(data, "w", np.float64, 0.0)
    gate_ok, gate_null = _column(data, "placed", bool, False)
    keep = ~no_bin
    phi = np.where(np.isfinite(phi), circular.wrap_angle(np.nan_to_num(phi)), np.nan)
    return ShowerSample(
        mb=mb[keep], p=p[keep], theta=theta[keep], phi=phi[keep], hits=hits[keep],
        placed=(gate_ok & ~gate_null)[keep], n_no_bin=int(no_bin.sum()),
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


# ------------------------------------------------------------------ series --


@dataclass(frozen=True)
class SeriesClass:
    """One series: a momentum bin, its label and how many showers it holds."""

    bin: int
    label: str
    n_showers: int


def series_classes(sample: ShowerSample, mask: np.ndarray | None = None
                   ) -> tuple[list[SeriesClass], list[str]]:
    """The own momentum bins the (masked) showers occupy, labelled against their momenta.

    Returns the classes in bin order and the notices of any bin whose momenta
    leave [k, k+1) (``stats.momentum.relabel_bins``).
    """
    keep = np.ones(sample.n, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    mb, p = sample.mb[keep], sample.p[keep]
    present = np.unique(mb)
    if present.size == 0:
        return [], []
    lo, hi = int(present[0]), int(present[-1])
    if hi - lo + 1 > momentum.MAX_CLASSES:
        raise ValidationError(
            f"The selection spans momentum bins {lo}–{hi}; the distribution card draws at most "
            f"{momentum.MAX_CLASSES} bins. Narrow the incident-momentum range.", field="e1")
    wanted = {int(k) for k in present}
    ranges: dict[int, tuple[float, float]] = {}
    counts: dict[int, int] = {}
    for k in wanted:
        in_bin = mb == k
        found = p[in_bin][np.isfinite(p[in_bin])]
        counts[k] = int(in_bin.sum())
        if found.size:
            ranges[k] = (float(found.min()), float(found.max()))
    classes = [c for c in momentum.unit_bins(lo, hi) if int(c.lo) in wanted]
    classes, notices = momentum.relabel_bins(classes, ranges)
    return [SeriesClass(int(c.lo), c.label, counts[int(c.lo)]) for c in classes], notices


@dataclass
class Series:
    """One series' counts over the display bins, and what fell either side."""

    cls: SeriesClass
    counts: np.ndarray
    below: float
    above: float
    resultant: float | None = None
    rayleigh_p: float | None = None

    @property
    def total(self) -> float:
        return float(self.counts.sum()) + self.below + self.above


def count_value(value: float, exact: bool) -> int | float | None:
    """A count as the payload ships it: exact integers and binary fractions verbatim.

    Hit counts of the footprint splat are multiples of 1/8, which a float
    holds exactly; rounding them to six significant figures would break the
    sums a reader (and the tests) can check. A sampled preview's scaled
    estimate is an estimate, and gets six figures like every other number.
    """
    number = float(value)
    if not math.isfinite(number):
        return None
    if not exact:
        return sig(number)
    return int(number) if number.is_integer() else number


def trimmed(counts: np.ndarray) -> tuple[int, np.ndarray]:
    """``(offset, span)``: the counts from the first to the last non-zero bin."""
    nonzero = np.flatnonzero(counts)
    if nonzero.size == 0:
        return 0, counts[:0]
    return int(nonzero[0]), counts[int(nonzero[0]):int(nonzero[-1]) + 1]


def series_payload(series: Sequence[Series], exact: bool) -> list[dict[str, Any]]:
    out = []
    for s in series:
        offset, span = trimmed(s.counts)
        out.append({
            "bin": s.cls.bin,
            "label": s.cls.label,
            "n": int(round(s.total)),
            "n_showers": s.cls.n_showers,
            "offset": offset,
            "counts": [count_value(c, exact) for c in span],
            "below": count_value(s.below, exact),
            "above": count_value(s.above, exact),
            "resultant": sig(s.resultant),
            "rayleigh_p": sig(s.rayleigh_p, 3),
        })
    return out


# ------------------------------------------------------------------ window --


def ordinal(value: float) -> str:
    """``1st``, ``2nd``, ``99th``, ``2.5th``: a percentile as a sentence names it."""
    text = f"{value:g}"
    if not float(value).is_integer():
        return text + "th"
    n = int(value)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{text}{suffix}"


def fmt_count(value: float) -> str:
    """A count for a sentence: thousands separated, fractions only where they exist."""
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.3f}".rstrip("0").rstrip(".")


def fmt_value(value: float) -> str:
    return typographic(f"{float(value):.6g}")


def percentile_bins(pooled: np.ndarray, low: float, high: float) -> tuple[int, int]:
    """Inclusive indices of the bins holding the ``low``-th and ``high``-th percentile.

    The bin where the cumulative count first reaches each level: the mass
    before the first is below ``low`` percent, the mass after the second at
    most ``100 - high`` percent - the window is the percentile range rounded
    outward to whole bins.
    """
    cumulative = np.cumsum(np.asarray(pooled, dtype=np.float64))
    total = float(cumulative[-1]) if cumulative.size else 0.0
    if not total > 0:
        return 0, max(0, int(np.asarray(pooled).size) - 1)
    i_lo = int(np.searchsorted(cumulative, low / 100.0 * total, side="left"))
    i_hi = int(np.searchsorted(cumulative, high / 100.0 * total, side="left"))
    # The first populated bin, not an empty one before it (level 0).
    first = int(np.flatnonzero(pooled)[0])
    last = int(np.flatnonzero(pooled)[-1])
    i_lo = min(max(i_lo, first), last)
    i_hi = min(max(i_hi, i_lo), last)
    return i_lo, i_hi


def weighted_percentiles(values: np.ndarray, weights: np.ndarray,
                         low: float, high: float) -> tuple[float, float]:
    """The ``low``/``high`` percentiles of a weighted sample.

    The inverted CDF, so each bound is a value of the sample; with unit
    weights it is the plain sample percentile of that method.
    """
    lo, hi = np.percentile(values, [low, high], weights=weights, method="inverted_cdf")
    return float(lo), float(hi)


@dataclass
class Display:
    """The drawn range of a quantity, and its disclosure."""

    lo: float
    hi: float
    applied: bool            # a percentile crop was applied
    provisional: bool        # set by fewer than ROBUST_N showers
    low: float
    high: float
    n_outside: float
    total: float
    note: str
    coarsened: int = 1

    def as_dict(self, exact: bool) -> dict[str, Any]:
        fraction = self.n_outside / self.total if self.total > 0 else 0.0
        return {
            "lo": sig(self.lo),
            "hi": sig(self.hi),
            "percentiles": [self.low, self.high] if self.applied else None,
            "n_outside": count_value(self.n_outside, exact),
            "fraction_outside": sig(fraction),
            "provisional": self.provisional,
            "coarsened": self.coarsened,
            "note": typographic(self.note),
        }


def window_note(lo: float, hi: float, unit: str, *, applied: bool, low: float, high: float,
                n_outside: float, total: float, what: str, rounding: str,
                n_showers: int) -> str:
    """The display window's disclosure sentence (CLAUDE.md section 2)."""
    span = f"{fmt_value(lo)} to {fmt_value(hi)} {unit}"
    if total <= 0:
        return "Nothing in this selection to draw."
    if not applied:
        return (f"Full range shown ({span}): with {n_showers} shower"
                f"{'' if n_showers == 1 else 's'} a percentile would interpolate between "
                f"individual events, so the range is provisional.")
    tail = ("nothing lies outside it." if n_outside == 0 else
            f"{fmt_count(n_outside)} of {fmt_count(total)} {what} "
            f"({100.0 * n_outside / total:.2f}%) lie outside it, counted per series as "
            "below/above and never dropped from the counts.")
    provisional = (f" Fewer than {ROBUST_N} showers set it, so it is provisional."
                   if n_showers < ROBUST_N else "")
    return (f"Display range covers the {ordinal(low)} to {ordinal(high)} percentile of the "
            f"pooled {what}, rounded outward to {rounding}: {span}; {tail}{provisional}")


def rice_bins(n_showers: Sequence[int]) -> tuple[int, int]:
    """``(bins, N)``: the Rice rule on the smallest series of at least :data:`RICE_FLOOR_N` showers.

    Series below that floor are drawn on the same bins but do not set them;
    when no series reaches it, the smallest populated series does.
    """
    drawn = [int(n) for n in n_showers if n >= RICE_FLOOR_N]
    pool = drawn or [int(n) for n in n_showers if n > 0]
    n_ref = min(pool) if pool else 0
    return histogram.adaptive_bins(n_ref), n_ref


# ------------------------------------------------------------------ render --


@dataclass
class Prepared:
    """A loaded selection, ready to be rendered at any coarsening of its display bins."""

    render: Callable[[int], dict[str, Any]]
    exact: bool = True
    cached: bool = False
    query_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)


def _widen(lo: float, hi: float) -> tuple[float, float]:
    """A non-empty interval around a degenerate one (every value equal)."""
    if hi > lo:
        return lo, hi
    pad = max(abs(lo) * 0.05, 0.01)
    return lo - pad, hi + pad


def _histogram(values: np.ndarray, weights: np.ndarray, edges: np.ndarray
               ) -> tuple[np.ndarray, float, float]:
    """Weighted counts on ``edges`` (the last bin closed) and the weight either side."""
    finite = np.isfinite(values)
    v, w = values[finite], weights[finite]
    lo, hi = float(edges[0]), float(edges[-1])
    inside = (v >= lo) & (v <= hi)
    counts, _ = np.histogram(v[inside], bins=edges, weights=w[inside])
    return counts.astype(np.float64), float(w[v < lo].sum()), float(w[v > hi].sum())


def _edges(quantity: str, values: np.ndarray, weights: np.ndarray, n_series: Sequence[int],
           low: float, high: float, coarsen: int) -> tuple[np.ndarray, bool, str, float, str]:
    """``(edges, applied, rounding, bin_width, bin_unit)`` of θ, φ or p."""
    finite = np.isfinite(values) & (weights > 0)
    v, w = values[finite], weights[finite]
    if quantity == "phi":
        bins, n_ref = rice_bins(n_series)
        bins = max(1, math.ceil(bins / coarsen))
        return (np.linspace(-math.pi, math.pi, bins + 1), False,
                f"{bins} Rice-rule bins (N = {n_ref})", 2 * math.pi / bins, "rad")
    applied = v.size >= ROBUST_N
    if v.size == 0:
        lo, hi = (0.0, 1.0)
    elif applied:
        lo, hi = weighted_percentiles(v, w, low, high)
    else:
        lo, hi = float(v.min()), float(v.max())
    if quantity == "p":
        tenths = P_BIN_TENTHS.get(coarsen, P_BIN_TENTHS[max(P_BIN_TENTHS)])
        g_lo = math.floor(lo)
        g_hi = max(math.ceil(hi), g_lo + 1)
        if hi >= g_hi:  # a momentum exactly on an integer edge still belongs inside
            g_hi += 1
        n = (g_hi - g_lo) * 10 // tenths
        edges = (g_lo * 10 + np.arange(n + 1) * tenths) / 10.0
        return edges, applied, "whole GeV", tenths / 10.0, "GeV"
    lo, hi = _widen(lo, hi)
    nice_lo, nice_hi, interval = clip.nice_range(lo, hi, fine=True)
    bins, n_ref = rice_bins(n_series)
    bins = max(1, math.ceil(bins / coarsen))
    edges = histogram.axis_edges(nice_lo, nice_hi, bins)
    return (edges, applied, f"{interval:g} rad, then {bins} Rice-rule bins (N = {n_ref})",
            (nice_hi - nice_lo) / bins, "rad")


def _concentration(phi: np.ndarray) -> tuple[float | None, float | None]:
    """``(R̄, Rayleigh p)`` of a series' azimuths, one direction per shower.

    In both weightings: the hits of a shower share its φ, so they add no
    directions. A single shower's R̄ is 1 by construction and says nothing
    about concentration, so it is withheld below two showers.
    """
    c, s, n = circular.resultant_sums(phi)
    if n < 2:
        return None, None
    resultant = circular.mean_resultant_length(c, s, n)
    return resultant, circular.rayleigh_p(n, resultant) if resultant is not None else None


def render(sample: ShowerSample, classes: Sequence[SeriesClass], quantity: str, weighting: str,
           low: float, high: float, coarsen: int = 1) -> dict[str, Any]:
    """The θ, φ or p histograms of every series, on one shared binning."""
    q = QUANTITIES[quantity]
    if not classes:
        display = Display(0.0, 0.0, False, quantity != "phi", low, high, 0.0, 0.0,
                          "Nothing in this selection to draw.", coarsen)
        return {"quantity": q.block(_WEIGHTING_TEXT[weighting], 0.0, q.unit), "edges": [],
                "series": [], "display": display.as_dict(exact=True), "splat": None,
                "comb": None}
    values = {"theta": sample.theta, "phi": sample.phi, "p": sample.p}[quantity]
    weights = sample.hits if weighting == WEIGHT_HIT else np.ones(sample.n, dtype=np.float64)
    in_series = np.isin(sample.mb, [c.bin for c in classes])
    edges, applied, rounding, width, unit = _edges(
        quantity, values[in_series], weights[in_series], [c.n_showers for c in classes],
        low, high, coarsen)

    series: list[Series] = []
    for c in classes:
        mine = sample.mb == c.bin
        counts, below, above = _histogram(values[mine], weights[mine], edges)
        s = Series(c, counts, below, above)
        if quantity == "phi":
            s.resultant, s.rayleigh_p = _concentration(values[mine])
        series.append(s)

    n_showers = int(sum(c.n_showers for c in classes))
    total = float(sum(s.total for s in series))
    n_outside = float(sum(s.below + s.above for s in series))
    what = "showers" if weighting == WEIGHT_SHOWER else "hit-weighted showers"
    if quantity == "phi":
        note = ("Full period (−π, π] shown: an azimuth wraps, so it is never cropped to a "
                "percentile window and nothing lies outside it.") if total > 0 else \
            "Nothing in this selection to draw."
    else:
        note = window_note(float(edges[0]), float(edges[-1]), q.unit, applied=applied, low=low,
                           high=high, n_outside=n_outside, total=total, what=what,
                           rounding=rounding, n_showers=n_showers)
    # φ's range is its period, not an estimate, so it is never provisional.
    display = Display(float(edges[0]), float(edges[-1]), applied and quantity != "phi",
                      quantity != "phi" and n_showers < ROBUST_N, low, high, n_outside, total,
                      note, coarsen)
    return {
        "quantity": q.block(_WEIGHTING_TEXT[weighting], width, unit),
        "edges": [sig(e) for e in edges],
        "series": series_payload(series, exact=True),
        "display": display.as_dict(exact=True),
        "splat": None,
        "comb": None,
    }


# ------------------------------------------------------------------- notes --


def kind_notes(record: ExperimentRecord) -> list[str]:
    """What every C4 quantity of this experiment's kind must say."""
    if record.kind == ddl.KIND_SINGLE_EVENTS:
        return [
            "This experiment is the producer's event-level aggregate, which omits every event "
            "with a single hit: the populations of its momentum bins are not balanced, and the "
            "lowest bin loses the most events."
        ]
    if record.kind == ddl.KIND_TWO_SHOWER:
        return [
            "Each shower sits in its own momentum bin: shower A by incoming_momentum_bin_A, "
            "shower B by incoming_momentum_bin_B; hits of 'A+B' cells count with B."
        ]
    return []


def series_notes(classes: Sequence[SeriesClass], sample: ShowerSample) -> list[str]:
    notes = []
    small = [c for c in classes if c.n_showers < RICE_FLOOR_N]
    if small:
        which = "Every series holds" if len(small) == len(classes) else (
            f"{len(small)} of {len(classes)} series hold")
        notes.append(
            f"{which} fewer than {RICE_FLOOR_N} showers ({listed([c.label for c in small], 6)}):"
            " drawn as exact counts on the shared bins, but the shape of a handful of showers "
            "is not a distribution.")
    if sample.n_no_bin:
        notes.append(f"{sample.n_no_bin:,} selected shower(s) carry no momentum bin and are "
                     "not drawn.")
    return notes


def prepare(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, *,
            quantity: str, weighting: str, shower: str, low: float, high: float) -> Prepared:
    """θ, φ or p of the selection's showers, ready to render (event table only)."""
    selected = showers_mod.of(record, shower)
    sample = fetch(con, record, spec, selected)
    classes, notices = series_classes(sample)
    notes = [*kind_notes(record), *notices, *series_notes(classes, sample)]
    missing = int((~np.isfinite({"theta": sample.theta, "phi": sample.phi,
                                 "p": sample.p}[quantity])).sum())
    if missing:
        notes.append(f"{missing:,} shower(s) have no recorded {QUANTITIES[quantity].symbol} "
                     "and are not counted.")
    if weighting == WEIGHT_HIT:
        notes.append(
            "Hit-weighted: each shower counts once per hit, as in the reference notebook's "
            "50 000-hit sample, but computed exactly from every shower's hit count. The bin "
            "count follows showers, because the hits of one shower share its value.")
    if quantity == "phi":
        notes.append(
            "R̄ is the mean resultant length of each series' showers' azimuths, one direction "
            "per shower in either weighting, with the Rayleigh p = exp(−N R̄²) beside it, from "
            "two showers up; φ is never averaged linearly.")

    def draw(coarsen: int) -> dict[str, Any]:
        body = render(sample, classes, quantity, weighting, low, high, coarsen)
        body["notes"] = [typographic(n) for n in notes]
        return body

    return Prepared(draw, exact=True, cached=False, query_ms=sample.elapsed_ms)
