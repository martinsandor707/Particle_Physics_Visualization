"""The sampling-fraction cards of Page 1: B1, B2 and the energy resolution.

All three read the event table only - one row per event, holding each shower's
deposited energy and incident momentum - so a selection of a hundred thousand
events costs milliseconds and needs no cache. The unit is the event: the
sampling fraction ``f = E_dep / p`` is one value per event and shower, each
shower is its own series (shower A by ``e1`` / ``e1_bin``, shower B by ``e2`` /
``e2_bin``), and the two showers of one event are never pooled into one sample.

**Two estimators of one number, kept apart.** B1's marker is the mean of the
per-event fractions, the notebook's estimator. The calibration the energy panel
applies is the ratio of sums, ``c = sum(p) / sum(E_dep)``, and ``100 sum(E_dep)
/ sum(p)`` is the sampling fraction it implies. A ratio of sums weights an event
by its momentum and a mean of ratios weights every event alike, and the
fraction depends on the momentum (the lowest bin of the electron file averages
2.3% against about 3.1% from 5 GeV up), so the two differ: 3.041% against
3.113% on that file. Neither is the "true" sampling fraction. Both are drawn,
each with its own interval, and named as what they are. ``c`` is fitted once per
shower over the whole selection and never per momentum bin: a per-bin ``c``
would force every bin onto its own truth and erase the response curve B2 and
the resolution exist to show.

**What a mark means.** The mean's whisker is its Student-t interval, always the
95% interval at every N and in every bin (a mark that switched between the
standard error and the interval along the axis would change meaning from one
bin to the next). The sample standard deviation is a different quantity
answering a different question, an uncapped band that is sqrt(N) wider than
the whisker. The resolution ``sigma / mu`` is a ratio of two estimates: its
whisker is the delta-method Student-t interval, which carries the uncertainty
of ``mu`` as well as that of ``sigma``, and the chi-squared interval of ``sigma``
alone travels beside it in the series' own unit.

**Why the resolution has two series.** The resolution of the calibrated energy
``c * E_dep`` in a 1 GeV bin of the incident momentum includes the spread of the
momentum inside the bin: a momentum uniform on 0-1 GeV alone gives
``sigma / mu = 0.58`` in the lowest bin, before the detector has contributed
anything. The second series is the spread of ``f = E_dep / p`` itself, which
divides the momentum out and does not change when ``c`` is rescaled; the
momentum spread ``sigma_p / <p>`` rides with both so the reader can see the
share the calibrated series owes to the binning.

**Ranges follow robust evidence.** A y range is taken from the bins and
series with N >= 20, extended by 5% and rounded outward to clean ticks. Where
nothing reaches N = 20 the range is taken from what exists and labelled
provisional on the axis. A weak bin that overflows the range is clipped, not
allowed to rescale it, and the overflow is counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import SIGNIFICANT, plain, sig
from ..errors import ValidationError
from ..stats import clip as clip_mod
from ..stats import gaussian, histogram, metrics
from ..stats import momentum as momentum_mod
from ..text import typographic
from .filters import FilterSpec
from .showers import ShowerColumns

PART_B1, PART_B2, PART_RESOLUTION = "b1", "b2", "resolution"
PARTS: tuple[str, ...] = (PART_B1, PART_B2, PART_RESOLUTION)

#: The capability gate behind each part (``query/capabilities.py``).
GATES: dict[str, str] = {
    PART_B1: "response-b1", PART_B2: "response-b2", PART_RESOLUTION: "response-res",
}

#: Everything on this route that is a ratio of energies is in percent.
UNIT = "%"

#: Below this many events a bin or series is weak: labelled so, and never the
#: evidence a display range is taken from (CLAUDE.md, the robust floor).
WEAK_N = gaussian.MIN_ROBUST_SAMPLES

#: Most individual events shipped for an event strip. A series below the
#: histogram floor holds at most 14, so this only guards a changed threshold
#: and the one case of a degenerate series with thousands of equal events.
MAX_STRIP_POINTS = 200

#: Headroom above the highest robust mark, so it does not sit on the axis edge.
HEADROOM = 0.05

METHOD_DELTA_T = "delta_t"
KIND_CALIBRATED = "calibrated_energy"
KIND_RATIO = "response_ratio"

#: The producer's single-hit omission, measured on the electron file
#: (``data.md`` A2 and A5): said on every response of the aggregate kind.
_CENSORED = (
    "The producer's 59-column aggregate leaves out events with a single hit: on the electron "
    "file that removed 249 of 100,000 events (193 of them in momentum bin 0, 12 in bin 1), so "
    "the events per bin are 4,807 to 5,000 and not 5,000, and the bin-0 mean sampling "
    "fraction is biased high (+2.7%). This sample is not balanced."
)

_DEPOSIT_NOTE = {
    ddl.KIND_TWO_SHOWER: (
        "Each shower's deposit E_dep is the truth segmentation's share of the event's hit energy "
        "(a cell both showers hit is divided by the truth fraction) and p is that shower's own "
        "incident momentum. Showers A and B are separate series with one value per event each; "
        "an event in which a shower has no hit rows is not part of that shower's series."
    ),
    ddl.KIND_SINGLE_HITS: (
        "The deposit E_dep is the shower's total hit energy in GeV, summed over its cells, and p "
        "its incident momentum: one shower per event."
    ),
    ddl.KIND_SINGLE_EVENTS: (
        "The deposit E_dep is the producer's total_hit_energy and p its incoming_momentum, both "
        "read from the 59-column event aggregate: one shower per event, no hits."
    ),
}


# ------------------------------------------------------------- request --


def parse_parts(raw: str | None) -> tuple[str, ...]:
    """``parts`` as a request names it: a comma list of b1, b2, resolution; empty is all three."""
    if raw is None or not raw.strip():
        return PARTS
    wanted = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [part for part in wanted if part not in PARTS]
    if unknown:
        raise ValidationError(
            f"parts must be a comma-separated list of {', '.join(PARTS)}; got {raw!r}.",
            field="parts",
        )
    return tuple(part for part in PARTS if part in wanted)


@dataclass(frozen=True)
class Request:
    """What a request asks for, apart from the selection."""

    parts: tuple[str, ...] = PARTS
    clip_low: float = clip_mod.DEFAULT_LOW_PERCENTILE
    clip_high: float = clip_mod.DEFAULT_HIGH_PERCENTILE
    bins: int | None = None


@dataclass(frozen=True)
class Fidelity:
    """How finely the payload is written; the budget guard steps it down, never the statistics."""

    bins_divisor: int = 1
    digits: int = SIGNIFICANT


#: The budget guard's ladder: B1's histogram coarser and the numbers shorter.
FIDELITY_STEPS: tuple[Fidelity, ...] = (Fidelity(), Fidelity(2, 5), Fidelity(4, 4))


# --------------------------------------------------------------- fetch --


@dataclass
class Sample:
    """One shower's usable events of the selection: one value per event."""

    columns: ShowerColumns
    dep: np.ndarray            # deposited energy (GeV)
    p: np.ndarray              # the shower's incident momentum (GeV)
    bin: np.ndarray            # the producer's integer momentum bin
    n_selected: int            # events of the selection, the shower present or not
    n_absent: int              # ... of which the shower has no hit rows
    n_dropped: int             # present, but with a value no ratio can use
    fraction: np.ndarray = field(init=False)   # f = 100 E_dep / p, per event

    def __post_init__(self) -> None:
        self.fraction = 100.0 * self.dep / self.p

    @property
    def key(self) -> str:
        return self.columns.key

    @property
    def n(self) -> int:
        return int(self.dep.size)


def _floats(column: Any) -> np.ndarray:
    """A fetched column as float64 with NULL as NaN (DuckDB returns NULLs as a masked array)."""
    return np.ma.filled(np.ma.asarray(column, dtype=np.float64), np.nan)


def fetch(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    shower_columns: Sequence[ShowerColumns],
) -> list[Sample]:
    """One statement over the event table, one arm per selected shower.

    A value no ratio can use - a deposit or momentum that is NULL or not finite,
    a negative deposit, a momentum that is not positive - is counted and dropped,
    never zero-filled: a zero would be a measurement of a shower that was not
    measured. An event in which the shower has no hit rows is not a dropped value
    but an absent shower, and is counted apart.
    """
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    arms = [
        f"SELECT {index} AS s, CAST({c.deposit} AS DOUBLE) AS dep, "
        f"CAST({c.momentum} AS DOUBLE) AS p, CAST({c.momentum_bin} AS INTEGER) AS mb, "
        f"COALESCE({c.present_sql}, FALSE) AS present FROM {table} WHERE {where}"
        for index, c in enumerate(shower_columns)
    ]
    rows = con.execute(" UNION ALL ".join(arms), spec.params()).fetchnumpy()
    which = np.asarray(rows["s"])
    dep_all, p_all, bin_all = _floats(rows["dep"]), _floats(rows["p"]), _floats(rows["mb"])
    present_all = np.asarray(rows["present"], dtype=bool)

    samples = []
    for index, columns in enumerate(shower_columns):
        mine = which == index
        dep, p, mb, present = dep_all[mine], p_all[mine], bin_all[mine], present_all[mine]
        usable = (present & np.isfinite(dep) & np.isfinite(p) & np.isfinite(mb)
                  & (dep >= 0.0) & (p > 0.0))
        samples.append(Sample(
            columns, dep[usable], p[usable], mb[usable].astype(np.int64),
            n_selected=int(mine.sum()), n_absent=int((~present).sum()),
            n_dropped=int((present & ~usable).sum()),
        ))
    return samples


# --------------------------------------------------------- calibration --


def _ratio(num: np.ndarray, den: np.ndarray) -> metrics.Estimate:
    """``sum(num) / sum(den)`` with events as clusters and a Student-t interval."""
    n = int(num.size)
    if n == 0:
        return metrics.Estimate(None, n=0, note="No events in this selection.")
    return metrics.ratio_estimate(
        float(num.sum()), float(den.sum()), float((num * num).sum()),
        float((den * den).sum()), float((num * den).sum()), n)


@dataclass(frozen=True)
class Calibration:
    """One shower's selection-wide calibration: a ratio of sums read two ways."""

    n: int
    c: metrics.Estimate           # sum p / sum E_dep: incident GeV per deposited GeV
    fraction: metrics.Estimate    # sum E_dep / sum p: the sampling fraction it implies


def calibrate(sample: Sample) -> Calibration:
    return Calibration(sample.n, _ratio(sample.p, sample.dep), _ratio(sample.dep, sample.p))


def _calibration_block(cal: Calibration) -> dict[str, Any]:
    interval = cal.c.interval
    fraction = cal.fraction.value
    return {
        "c": cal.c.value,
        "sampling_fraction_pct": None if fraction is None else 100.0 * fraction,
        "ci95": None if interval is None else [interval.lo, interval.hi],
        "se": cal.c.se,
        "n": cal.n,
        "method": metrics.METHOD_RATIO,
        "label": (
            "c = Σ p / Σ E_dep over the whole selection, summed before dividing: the calibration "
            "the energy panel applies, fitted once per shower and never per momentum bin. "
            "The sampling fraction it implies is 100 / c. Interval: 95% Student-t on the "
            "linearised ratio, events as clusters (n − 1 d.o.f.)."
        ),
    }


# ------------------------------------------------------------- helpers --


def _fit_block(fit: gaussian.GaussianFit) -> dict[str, Any]:
    """The plain-moment description of one sample: B1 quotes no core refit and draws no curve."""
    if fit.n == 0:
        estimator = "none"
    elif fit.n == 1:
        estimator = "mean_only"
    elif fit.degenerate:
        estimator = "degenerate"
    else:
        estimator = "moments_1dof" if fit.n == gaussian.MIN_MOMENT_SAMPLES else "moments"
    return {
        "n": fit.n,
        "mu": fit.mu,
        "sigma": fit.sigma,
        "sigma_population": fit.sigma_population,
        "mu_error": fit.mu_error,
        "sigma_error": fit.sigma_error,
        "mu_ci95": list(fit.mu_ci95) if fit.mu_ci95 else None,
        "sigma_ci95": list(fit.sigma_ci95) if fit.sigma_ci95 else None,
        "sigma_bias_factor": fit.sigma_bias_factor,
        "sigma_robust": fit.sigma_robust,
        "non_gaussian": fit.non_gaussian,
        "shape_testable": fit.shape_testable,
        "estimator": estimator,
        "moments_subset": "all events of the series (the display clip removes none of them)",
    }


def _rounded(value: Any, digits: int) -> Any:
    """The payload tree with every float at ``digits`` significant figures and U+2212 in text."""
    if isinstance(value, dict):
        return {k: _rounded(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(v, digits) for v in value]
    value = plain(value)
    if isinstance(value, list):
        return [_rounded(v, digits) for v in value]
    if isinstance(value, float):
        return sig(value, digits)
    if isinstance(value, str):
        return typographic(value)
    return value


def _t_whisker(quantity: str) -> dict[str, Any]:
    """The capped whisker's name: always the 95% Student-t interval of the mean, at every N."""
    return {
        "method": metrics.METHOD_T,
        "label": f"95% Student-t interval of the {quantity} (n − 1 d.o.f.), at every N; the "
                 "band is the sample SD, not this interval",
        "level": metrics.CI_LEVEL,
    }


def _dispersion(where: str) -> str:
    return (f"Band: the sample standard deviation (ddof = 1) of the per-event sampling fraction "
            f"{where}, uncapped. It is √N wider than the whisker, which is the 95% Student-t "
            "interval of the mean.")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}%"


def _weak_bins(count: int) -> str:
    return f"{count} bin{'s' if count != 1 else ''} with N < {WEAK_N} {'are' if count != 1 else 'is'} weak."


def _y_note(y: dict[str, Any]) -> str:
    """How a y range was set and what it clips, for the Details drawer."""
    basis = (f"The y range is provisional: no bin reaches N = {WEAK_N}."
             if y["provisional"] else f"The y range follows the bins with N ≥ {WEAK_N}.")
    clipped = y["n_clipped"]
    return (f"{basis} {clipped} bin{'s' if clipped != 1 else ''} draw"
            f"{'' if clipped != 1 else 's'} a mark beyond it (clipped, not rescaled; the true "
            "values are in the tooltip).")


@dataclass(frozen=True)
class Extent:
    """What one bin draws on a y axis: its whole extent, and the part that is not a whisker."""

    lo: float
    hi: float
    core_hi: float
    robust: bool


def _y_axis(extents: Sequence[Extent]) -> dict[str, Any]:
    """The zero-based y range from the robust bins, and the count of marks it clips.

    A bin of N >= 20 may set the top with everything it draws, whisker included.
    With no such bin the range is provisional and is set by the markers and
    bands of what exists, not by whiskers (a t whisker at N = 2 is twelve
    standard errors wide). Every weak bin whose mark leaves the range - above it,
    or below zero, where the axis cuts it - is counted.
    """
    robust = [e.hi for e in extents if e.robust]
    top = max(robust) if robust else max((e.core_hi for e in extents), default=0.0)
    if top > 0.0:
        lo, hi, interval = clip_mod.nice_range(0.0, top * (1.0 + HEADROOM), fine=True)
    else:
        # Nothing to scale against: nice_range's own empty default, 0 to 1.
        lo, hi, interval = clip_mod.nice_range(0.0, 0.0, fine=True)
    return {
        "zero_based": True,
        "lo": lo, "hi": hi, "interval": interval,
        "provisional": not robust,
        "n_clipped": sum(1 for e in extents if e.hi > hi or e.lo < lo),
    }


# ------------------------------------------------------------------ B1 --


@dataclass(frozen=True)
class B1Range:
    """B1's shared x range, set by the series that carry statistical weight."""

    lo: float
    hi: float
    interval: float
    provisional: bool
    clipping: dict[str, Any]


def _histogram_drawable(sample: Sample) -> bool:
    return (sample.n >= histogram.MIN_HISTOGRAM_SAMPLES
            and float(np.ptp(sample.fraction)) > 0.0)


def _b1_range(samples: Sequence[Sample], request: Request) -> B1Range:
    """The percentile range of the robust series, rounded outward, with what lies outside it.

    A series with fewer than 20 events does not set the range; if none has
    that many the range is the data's own and is labelled provisional. The
    outside counts take every series in, weak ones included, against the range
    as finally drawn.
    """
    robust = [s for s in samples if s.n >= WEAK_N]
    basis = robust or [s for s in samples if s.n > 0]
    pooled = np.concatenate([s.fraction for s in basis]) if basis else np.empty(0)
    clip = clip_mod.percentile_clip(
        pooled, low=request.clip_low, high=request.clip_high, floor_at_zero=True, pad=HEADROOM)
    lo, hi, interval = clip_mod.nice_range(clip.lo, clip.hi, fine=True)

    every = np.concatenate([s.fraction for s in samples]) if samples else np.empty(0)
    below, above = int((every < lo).sum()), int((every > hi).sum())
    outside, total = below + above, int(every.size)
    provisional = not robust
    if total == 0:
        note = "No showers in this selection."
    elif provisional:
        note = (f"Provisional range: no series reaches N = {WEAK_N}, so the axis spans the data "
                f"({lo:g}–{hi:g} {UNIT}), rounded outward to tick boundaries.")
    else:
        note = (f"The axis, {lo:g}–{hi:g} {UNIT}, follows percentiles {request.clip_low:g}–"
                f"{request.clip_high:g} of the pooled series with N ≥ {WEAK_N}, rounded "
                f"outward to tick boundaries and zero-based; ")
        note += (f"{outside:,} of {total:,} values ({100 * outside / total:.2f}%) lie outside it "
                 "and are excluded from the view but not from the statistics."
                 if outside else "no value lies outside it.")
    clipping = {
        "lo": lo, "hi": hi,
        "low_percentile": request.clip_low, "high_percentile": request.clip_high,
        "n_total": total, "n_below": below, "n_above": above, "n_outside": outside,
        "fraction_outside": outside / total if total else 0.0,
        "note": note,
    }
    return B1Range(lo, hi, interval, provisional, clipping)


def _b1_bins(samples: Sequence[Sample], request: Request, fidelity: Fidelity) -> int:
    """One bin count for every histogram, set by the smallest series that draws one."""
    drawn = [s.n for s in samples if _histogram_drawable(s)]
    if not drawn:
        return 0
    bins = request.bins or histogram.adaptive_bins(min(drawn))
    return max(histogram.MIN_BINS, bins // fidelity.bins_divisor)


def _strip_message(fit: gaussian.GaussianFit) -> str:
    n = fit.n
    if n == 1:
        return ("N = 1: a single shower fixes a position and nothing else; no width or "
                "uncertainty can be estimated.")
    if fit.degenerate:
        return (f"N = {n}, all at one sampling fraction to floating-point precision: the width "
                "is a measured zero, and a delta is not a density.")
    text = (f"N = {n}: below the {histogram.MIN_HISTOGRAM_SAMPLES}-event histogram floor, where a "
            "density histogram would be a comb of bin-width spikes whose heights are set by the "
            "binning, not the distribution. The individual events, the mean with its 95% "
            "Student-t interval and the sample SD are drawn instead.")
    if n == gaussian.MIN_MOMENT_SAMPLES:
        text += " At N = 2 the SD is one pairwise difference, 1 d.o.f., and the interval is very wide."
    return text


def _b1_series(sample: Sample, cal: Calibration, rng: B1Range,
               edges: np.ndarray | None) -> dict[str, Any]:
    f = sample.fraction
    fit = gaussian.fit_gaussian(f)
    block: dict[str, Any] = {
        "key": sample.key, "label": sample.columns.label,
        "n": sample.n, "n_dropped": sample.n_dropped, "n_absent": sample.n_absent,
        "fit": _fit_block(fit),
    }
    if sample.n == 0:
        return {**block, "draw": "none", "histogram": None, "strip": None, "markers": None,
                "reference": None, "message": "No showers of this series in the selection."}

    markers = None
    if fit.mu is not None and fit.sigma is not None:
        lo, hi = fit.mu_ci95
        markers = {"mu": fit.mu, "ci95_lo": lo, "ci95_hi": hi,
                   "dispersion_lo": fit.mu - fit.sigma, "dispersion_hi": fit.mu + fit.sigma}

    ratio = cal.fraction
    reference = None
    if ratio.value is not None:
        interval = ratio.interval
        reference = {
            "value": 100.0 * ratio.value,
            "ci95_lo": None if interval is None else 100.0 * interval.lo,
            "ci95_hi": None if interval is None else 100.0 * interval.hi,
            "label": "Sum before divide: 100 · Σ E_dep / Σ p over the selection (1 / c, the "
                     "calibration the energy panel applies)",
        }

    if edges is not None and _histogram_drawable(sample):
        counts = histogram.count_histogram(f, edges)
        norm = counts.n * float(edges[1] - edges[0])
        hist = {"density": [c / norm for c in counts.counts], "n_in_range": counts.n_in_range,
                "n_below": counts.n_below, "n_above": counts.n_above}
        return {**block, "draw": "histogram", "histogram": hist, "strip": None,
                "markers": markers, "reference": reference, "message": None}

    ordered = np.sort(f)
    shown = ordered[:MAX_STRIP_POINTS]
    strip = {"values": shown.tolist(), "n_shown": int(shown.size),
             "truncated": bool(ordered.size > MAX_STRIP_POINTS)}
    return {**block, "draw": "strip", "histogram": None, "strip": strip, "markers": markers,
            "reference": reference, "message": _strip_message(fit)}


def _b1(samples: Sequence[Sample], calibrations: dict[str, Calibration], rng: B1Range,
        request: Request, fidelity: Fidelity) -> dict[str, Any]:
    bins = _b1_bins(samples, request, fidelity)
    edges = histogram.axis_edges(rng.lo, rng.hi, bins) if bins else None
    centres = [] if edges is None else (0.5 * (edges[:-1] + edges[1:])).tolist()
    return {
        "axis": {
            "lo": rng.lo, "hi": rng.hi, "interval": rng.interval, "unit": UNIT,
            "bins": bins, "hist_centres": centres,
            "clipping": rng.clipping, "provisional": rng.provisional,
        },
        "series": [_b1_series(s, calibrations[s.key], rng, edges) for s in samples],
        "whisker": _t_whisker("mean of the per-event sampling fractions"),
        "dispersion": _dispersion("of the series"),
    }


# -------------------------------------------------------- momentum bins --


@dataclass
class Group:
    """The events of one momentum bin of one shower."""

    bin_class: momentum_mod.MomentumClass
    mask: np.ndarray


def _bin_groups(sample: Sample) -> tuple[list[Group], list[str]]:
    """The shower's populated momentum bins, labelled against the momenta found in them.

    Bins are the producer's integer ``incoming_momentum_bin`` of the shower's
    own momentum, never ``floor`` of a float32 column, so a momentum that
    rounds onto an integer edge cannot move a shower across it. Bin ``k`` is
    labelled ``k–k+1 GeV`` only when the momenta found in it lie in that
    interval; otherwise the label says so (``stats/momentum.relabel_bins``).
    """
    if sample.n == 0:
        return [], []
    low, high = int(sample.bin.min()), int(sample.bin.max())
    try:
        classes = momentum_mod.unit_bins(low, high)
    except ValidationError as error:
        raise ValidationError(error.detail, field="table_name") from None
    ranges = {}
    for k in np.unique(sample.bin):
        p = sample.p[sample.bin == k]
        ranges[int(k)] = (float(p.min()), float(p.max()))
    classes, notices = momentum_mod.relabel_bins(classes, ranges)
    groups = []
    for cls in classes:
        mask = sample.bin == int(cls.lo)
        if mask.any():
            groups.append(Group(cls, mask))
    return groups, notices


def _band_extent(centre: float | None, spread: float | None,
                 whisker: Sequence[float] | None, n: int) -> Extent | None:
    """The extent of a point, an uncapped band of ``spread`` and a capped whisker."""
    if centre is None:
        return None
    lows, highs = [centre], [centre]
    if spread is not None:
        lows.append(centre - spread)
        highs.append(centre + spread)
    core_hi = max(highs)
    if whisker is not None:
        lows.append(whisker[0])
        highs.append(whisker[1])
    return Extent(min(lows), max(highs), core_hi, n >= WEAK_N)


# ------------------------------------------------------------------ B2 --


def _dof_note(n: int) -> str | None:
    if n == 1:
        return "N = 1: a single shower; no spread or uncertainty can be estimated."
    if n == gaussian.MIN_MOMENT_SAMPLES:
        return "1 d.o.f."
    return None


def _b2_bin(group: Group, sample: Sample) -> tuple[dict[str, Any], Extent | None]:
    mask = group.mask
    dep, p, f = sample.dep[mask], sample.p[mask], sample.fraction[mask]
    fit = gaussian.fit_gaussian(f)
    n = fit.n
    ratio = _ratio(dep, p)
    interval = ratio.interval
    ci = list(fit.mu_ci95) if fit.mu_ci95 else None
    cls = group.bin_class
    record = {
        "bin": int(cls.lo), "label": cls.label, "lo": cls.lo, "hi": cls.hi,
        "n": n,
        "p_mean": float(p.mean()),
        "p_sd": float(p.std(ddof=gaussian.DDOF)) if n >= 2 else None,
        "mean": fit.mu, "sd": fit.sigma, "ci95": ci, "se": fit.mu_error,
        "sd_se": fit.sigma_error,
        "sd_ci95": list(fit.sigma_ci95) if fit.sigma_ci95 else None,
        "c4": fit.sigma_bias_factor if 2 <= n < gaussian.MIN_CORE_SAMPLES else None,
        "dof_note": _dof_note(n),
        "weak": n < WEAK_N,
        # The notebook's scaling factor: 1 / the mean of the per-event fractions.
        "scaling_factor": 100.0 / fit.mu if fit.mu else None,
        "ratio_of_sums": {
            "value": None if ratio.value is None else 100.0 * ratio.value,
            "ci95": None if interval is None else [100.0 * interval.lo, 100.0 * interval.hi],
        },
    }
    return record, _band_extent(fit.mu, fit.sigma, ci, n)


def _b2(samples: Sequence[Sample], groups: dict[str, list[Group]]) -> dict[str, Any]:
    series, extents = [], []
    for sample in samples:
        bins = []
        for group in groups[sample.key]:
            record, extent = _b2_bin(group, sample)
            bins.append(record)
            if extent is not None:
                extents.append(extent)
        series.append({"key": sample.key, "label": sample.columns.label, "bins": bins})
    return {
        "series": series,
        "whisker": _t_whisker("mean sampling fraction in the bin"),
        "dispersion": _dispersion("in the bin"),
        "y": _y_axis(extents),
    }


# ---------------------------------------------------------- resolution --

_WHISKER_LABEL = (
    "95% Student-t interval, ± t(0.975, N − 1) × the delta-method standard error of σ/μ, "
    "which includes the uncertainty of μ. At small N it is symmetric and can cross zero, where "
    "the axis cuts it. The 95% χ² interval of σ alone is in sigma_ci95, in the series' own unit."
)


def _resolution_bin(group: Group, fit: gaussian.GaussianFit, p: np.ndarray
                    ) -> tuple[dict[str, Any], Extent | None]:
    """One bin of one resolution series; ``fit`` is the sample in the series' own unit."""
    n = fit.n
    cls = group.bin_class
    value = se = None
    ci = None
    if fit.resolution is not None and fit.resolution_error is not None:
        value, se = 100.0 * fit.resolution, 100.0 * fit.resolution_error
        half = gaussian.t_quantile_975(n - 1) * se
        ci = [value - half, value + half]
    p_mean = float(p.mean())
    record = {
        "bin": int(cls.lo), "label": cls.label,
        "n": n, "p_mean": p_mean,
        "mu": fit.mu, "sigma": fit.sigma, "sigma_se": fit.sigma_error,
        "sigma_ci95": list(fit.sigma_ci95) if fit.sigma_ci95 else None,
        "value": value, "ci95": ci, "se_delta": se,
        "c4": fit.sigma_bias_factor if 2 <= n < gaussian.MIN_CORE_SAMPLES else None,
        "non_gaussian": fit.non_gaussian,
        "momentum_spread": (100.0 * float(p.std(ddof=gaussian.DDOF)) / p_mean
                            if n >= 2 and p_mean > 0 else None),
        "weak": n < WEAK_N,
    }
    extent = None
    if value is not None:
        extent = Extent(min(value, ci[0]), max(value, ci[1]), value, n >= WEAK_N)
    return record, extent


def _resolution(samples: Sequence[Sample], calibrations: dict[str, Calibration],
                groups: dict[str, list[Group]]) -> dict[str, Any]:
    """Two series per shower: the calibrated energy, and the response ratio.

    ``c`` is the shower's selection-wide constant, so a bin's calibrated
    energy is ``c`` times its own deposits and nothing is refitted per bin. A
    shower whose selection deposited nothing has no ``c`` and no series.
    """
    series, extents = [], []
    for sample in samples:
        c = calibrations[sample.key].c.value
        if c is None:
            continue
        kinds = (
            (KIND_CALIBRATED, f"{sample.columns.label} · calibrated energy c · E_dep", "GeV"),
            (KIND_RATIO, f"{sample.columns.label} · response ratio E_dep / p", UNIT),
        )
        for kind, label, unit in kinds:
            bins = []
            for group in groups[sample.key]:
                values = (c * sample.dep[group.mask] if kind == KIND_CALIBRATED
                          else sample.fraction[group.mask])
                record, extent = _resolution_bin(
                    group, gaussian.fit_gaussian(values), sample.p[group.mask])
                bins.append(record)
                if extent is not None:
                    extents.append(extent)
            series.append({"key": sample.key, "label": label, "kind": kind, "unit": unit,
                           "bins": bins})
    return {
        "series": series,
        "value_unit": UNIT,
        "whisker": {"method": METHOD_DELTA_T, "label": _WHISKER_LABEL, "level": metrics.CI_LEVEL},
        "y": _y_axis(extents),
        "note": (
            "σ/μ in percent per 1 GeV bin of the shower's own momentum, from the unbiased "
            "(ddof = 1) width. Calibrated energy: c · E_dep with c fitted once over the whole "
            "selection. It includes the spread of the momentum inside the bin, σ_p/⟨p⟩, which "
            "alone gives σ/μ = 58% in a bin that spans 0–1 GeV. Response ratio: the spread of "
            "E_dep / p, which divides the momentum out and does not change with c. Below "
            f"N = {gaussian.MIN_CORE_SAMPLES} the bias factor c4(N) of σ is quoted; below "
            f"N = {WEAK_N} the Gaussian-shape verdict is untestable and the bin is weak."
        ),
    }


# ------------------------------------------------------------- the lot --


class Response:
    """B1, B2 and the resolution of one selection, rendered at a chosen fidelity.

    The statistics are computed once; :meth:`as_dict` rebuilds only what the
    fidelity changes (B1's histogram) and rounds, so the budget guard can step
    down without querying again.
    """

    def __init__(self, record: ExperimentRecord, samples: list[Sample], request: Request,
                 undefined_d: int = 0) -> None:
        self.record = record
        self.samples = samples
        self.request = request
        self.undefined_d = undefined_d
        self.calibrations = {s.key: calibrate(s) for s in samples}
        self.b1_range = _b1_range(samples, request) if PART_B1 in request.parts else None

        self.groups: dict[str, list[Group]] = {}
        self.label_notices: list[str] = []
        if PART_B2 in request.parts or PART_RESOLUTION in request.parts:
            for sample in samples:
                self.groups[sample.key], notices = _bin_groups(sample)
                self.label_notices += notices
        self.b2 = _b2(samples, self.groups) if PART_B2 in request.parts else None
        self.resolution = (_resolution(samples, self.calibrations, self.groups)
                           if PART_RESOLUTION in request.parts else None)

    def bins(self, fidelity: Fidelity = Fidelity()) -> int:
        """B1's histogram bin count at ``fidelity``; 0 when no series draws a histogram."""
        if PART_B1 not in self.request.parts:
            return 0
        return _b1_bins(self.samples, self.request, fidelity)

    @property
    def n_events(self) -> int:
        return max((s.n_selected for s in self.samples), default=0)

    def warnings(self) -> list[str]:
        """What a reader of the card needs told about the selection, as served."""
        out = []
        if self.n_events == 0:
            out.append("No events match the current selection.")
        for s in self.samples:
            if s.n_dropped:
                many = s.n_dropped != 1
                out.append(
                    f"{s.columns.label}: {s.n_dropped:,} event{'s' if many else ''} "
                    f"{'were' if many else 'was'} dropped before the ratios (a deposit or "
                    "momentum that is not finite, a negative deposit, or a momentum that is not "
                    "positive), counted and never zero-filled.")
            if s.n_absent:
                many = s.n_absent != 1
                out.append(
                    f"{s.columns.label}: {s.n_absent:,} selected event{'s' if many else ''} "
                    f"{'hold' if many else 'holds'} no hit rows of this shower and "
                    f"{'are' if many else 'is'} not part of its series.")
        if self.b1_range is not None and self.b1_range.clipping["n_outside"]:
            out.append(self.b1_range.clipping["note"])
        return out

    def _notes(self, b1: dict | None, b2: dict | None, resolution: dict | None) -> list[str]:
        """The disclosures of this selection, as the Details drawer lists them."""
        notes = [
            _DEPOSIT_NOTE.get(self.record.kind or "", ""),
            "The sampling fraction is f = E_dep / p per event and shower, in percent. A value "
            "no ratio can use is counted and dropped, never zero-filled. Every mean, SD, ratio "
            "and interval is taken over all the events of its series or bin; a display range "
            "clips the picture and nothing from the statistics.",
        ]
        if self.record.kind == ddl.KIND_SINGLE_EVENTS:
            notes.append(_CENSORED)
        if self.undefined_d:
            notes.append(
                f"{self.undefined_d:,} of the experiment's {self.record.n_events:,} events have "
                "no shower A hits and so no A–B separation. A selection leaves them out unless "
                "include_undefined_d is set, shower B's series included.")
        for s in self.samples:
            cal = self.calibrations[s.key]
            if cal.c.value is not None and cal.fraction.value is not None:
                notes.append(
                    f"{s.columns.label}: c = Σ p / Σ E_dep = {cal.c.value:.3f}, a sampling "
                    f"fraction of {_pct(100.0 * cal.fraction.value)} (sum before divide, "
                    f"N = {cal.n:,} events), fitted once over the whole selection and never "
                    "per momentum bin.")
        if b1 is not None:
            notes += self._b1_notes(b1)
        if b2 is not None:
            weak = sum(1 for s in b2["series"] for b in s["bins"] if b["weak"])
            notes.append(
                "B2: bins are the producer's integer momentum bin of each shower, closed on the "
                "left, [k, k + 1); the notebook's pd.cut closes them on the right, which moves "
                "only a shower exactly on an edge. The scaling factor is 1 / the mean of the "
                "per-event fractions, as the notebook; the per-bin ratio of sums is in the "
                "tooltip and never calibrates.")
            notes.append(f"B2: {_weak_bins(weak)} {_y_note(b2['y'])}")
        if resolution is not None:
            weak = sum(1 for s in resolution["series"] for b in s["bins"] if b["weak"])
            notes.append(f"Resolution: {_weak_bins(weak)} {_y_note(resolution['y'])}")
        return [n for n in notes + self.label_notices if n]

    def _b1_notes(self, b1: dict[str, Any]) -> list[str]:
        notes = [
            "B1: the marker is the mean of the per-event fractions (its whisker the 95% "
            "Student-t interval of that mean, the band the sample SD) and the rule is the "
            "ratio of sums 100 · Σ E_dep / Σ p. They are two different numbers, because the "
            "fraction depends on the momentum and a ratio of sums weights an event by its "
            "momentum."]
        for s in b1["series"]:
            mu = (s["markers"] or {}).get("mu")
            ref = (s["reference"] or {}).get("value")
            if mu is not None and ref is not None:
                notes.append(
                    f"B1, {s['label']}: mean of ratios {_pct(mu)}, ratio of sums {_pct(ref)}, "
                    f"a difference of {abs(ref - mu):.3f} percentage points.")
        notes.append(
            "B1: bar heights are counts / (N × bin width) over all N events, so the area of the "
            "bars is the fraction of events inside the axis. No Gaussian curve is drawn: the "
            "spectrum has a low-side containment tail, and its shape verdict (non_gaussian) "
            f"exists only from N = {WEAK_N}.")
        notes.append("B1: " + self.b1_range.clipping["note"])
        return notes

    def as_dict(self, fidelity: Fidelity = Fidelity()) -> dict[str, Any]:
        """The payload body (no ``meta`` or ``filter``), rounded for the wire."""
        b1 = (_b1(self.samples, self.calibrations, self.b1_range, self.request, fidelity)
              if self.b1_range is not None else None)
        tree = {
            "kind": self.record.kind,
            "unit": UNIT,
            "calibration": {s.key: _calibration_block(self.calibrations[s.key])
                            for s in self.samples},
            "b1": b1,
            "b2": self.b2,
            "resolution": self.resolution,
            "notes": self._notes(b1, self.b2, self.resolution),
        }
        return _rounded(tree, fidelity.digits)


def compute(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    shower_columns: Sequence[ShowerColumns],
    request: Request = Request(),
) -> Response:
    """Read the selection's events once and build every requested part."""
    # The filter leaves events with an undefined A-B separation out; their count is the
    # experiment's, and is told whenever the selection did leave them out.
    left_out = (record.n_events_no_d
                if record.kind == ddl.KIND_TWO_SHOWER and not spec.include_undefined_d else 0)
    return Response(record, fetch(con, record, spec, shower_columns), request, left_out)
