"""Network performance by incident-momentum bin: the E2 view of Page 2.

``performance.py`` asks how a network degrades as the two showers close in (the
separation slices). This module asks the other question a reconstruction has to
meet: how it behaves across the momentum range. The energy and angle networks
predict *per shower*, so a residual belongs to one shower and to the momentum
that shower was generated at.

**Each shower uses its own bin.** An event holds two showers of two momenta
(``e1``, ``e2``), so it has no single momentum bin. Shower A is placed by
``e1_bin`` and shower B by ``e2_bin`` - the producer's integer column, never
``floor(p)`` recomputed - and the two are separate series with their own N.

**Every network frame in one response.** The chart compares one task trained in
three input frames on a single axis, so all frames the experiment offers are
computed from one read of the selected events: one consistent N, one y range.
The bins themselves come from one more aggregate over the whole event table, so
the axis (and each bin's label) does not move with the selection.

**Statistics per group** (frame, shower, bin), each carrying the uncertainty of
the aggregate it is - a capped whisker is never the dispersion of the sample
(CLAUDE.md section 2) - and each gated on its own terms:

* RMSE (decision D-4, ``stats/rmse.py``): from N = 2 to 19 the χ² interval
  [RMSE·√(n/χ²₀.₉₇₅,ₙ), RMSE·√(n/χ²₀.₀₂₅,ₙ)] under normal residuals centred on
  zero, an assumption the interval states; from N = 20 the seeded percentile
  bootstrap of the RMSE, seeded as the median's. MAE with the Student-t
  interval of the mean absolute residual, clipped at zero (N ≥ 2); bias with
  the Student-t interval of the mean residual (N ≥ 2). All three are reported
  as numbers from N = 1, without an interval, because a value is a claim about
  a sample and an interval is a claim about its population; the card draws a
  bin of one shower as a dot, an observation, never as a bar.
* The median relative error, ``|pred − true| / true``: from N = 6 the
  distribution-free order-statistic interval, from N = 20 the seeded
  percentile bootstrap (``stats/median.py``), the order-statistic interval
  kept beside it as a cross-check. Each group seeds its own bootstrap from
  ``SeedSequence([42, frame, shower, bin, quantity])``, so an interval never
  depends on which other series the request computed.
* For the angle network the polar angle θ is the only prediction (the azimuth
  is not predicted, so there is no angular residual to wrap), residuals are in
  milliradians and a relative error grows like 1 / θ at small θ. Each angle
  point therefore also carries the median ``|Δθ|`` in mrad, the smallest true
  θ of its showers and how many lie below 0.1 rad.

**The y range follows robust evidence.** A point drives the scale only from
N = 15 (the core-refit floor); ``y_max`` is the outward rounding of the
largest interval end among the driving points to a mantissa of
:data:`TOP_MANTISSAS`, each a whole number of round ticks. An under-powered point above it
is clipped by the chart, so it is listed in ``overflow`` with its true value.
When no point drives the scale the range is taken from the weak points'
values alone, never their whiskers, and marked provisional; a whisker beyond it
is clipped and listed in ``overflow`` too.

A shower without a prediction (an event with none of that shower's hits) is
counted per bin in ``n_missing`` and dropped - never zero-filled.

**Groups in parallel.** The RMSE bootstrap costs O(B · n) per group (about
20 ms for 2,000 showers), so the groups of one request are computed on a
thread pool bounded by the service's thread count (``Settings.threads``, the
figure ``/api/health`` reports), built per request and never per group. Every
group draws from its own ``SeedSequence``, so the result is identical to the
serial path whatever the pool size or scheduling; ``workers=1`` is that path.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import SIGNIFICANT, sig, sig_list
from ..errors import CapabilityError, ValidationError
from ..stats import gaussian, median, metrics, momentum
from ..stats import rmse as rmse_mod
from ..text import typographic
from . import capabilities
from . import showers as showers_mod
from .filters import FilterSpec
from .performance import MRAD_PER_RAD

#: The two networks that predict per shower, and the stem of their event-table columns.
STEMS: dict[str, str] = {"energy": "en", "angle": "th"}
MODELS: tuple[str, ...] = tuple(STEMS)
UNITS: dict[str, str] = {"energy": "GeV", "angle": "mrad"}

#: The plotted quantities; a position here is the last element of a bootstrap seed.
QUANTITIES: tuple[str, ...] = ("rmse", "mae", "median_rel", "bias", "median_abs")
QUANTITY_INDEX: dict[str, int] = {name: i for i, name in enumerate(QUANTITIES)}

#: Quantities that can be negative: their range is symmetric about zero.
SIGNED: frozenset[str] = frozenset({"bias"})

#: θ below this (rad) makes a relative angular error mostly a statement about θ.
SMALL_THETA_RAD = 0.1

#: Sample sizes at which each mark becomes drawable, from the helpers that own them.
THRESHOLDS: dict[str, int] = {
    "interval": gaussian.MIN_MOMENT_SAMPLES,
    "order_statistic": median.MIN_ORDER_N,
    "scale": metrics.SHOW_CI_BELOW_N,
    "bootstrap": median.MIN_BOOTSTRAP_N,
}

#: Most under-powered points listed per quantity; the count travels beside the list.
MAX_OVERFLOW_LISTED = 24

SEGMENTATION_REFUSAL = (
    "slice_by=momentum_bin applies to the energy and angle networks, whose predictions are "
    "per shower. Segmentation quality is a property of the whole event, whose two showers "
    "carry two momenta, so it has no single momentum bin; use the separation slices "
    "(slice_by=d)."
)


def network_columns(model: str, coord_system: str, shower: str) -> tuple[str, str]:
    """``(truth, prediction)`` event-table columns of one shower's network.

    ``shower`` is a :class:`~calosrv.query.showers.ShowerColumns` key and the
    frame goes through :func:`ddl.frame_code`: both are allowlisted, so a
    request string never becomes a column name.
    """
    return ddl.prediction_columns(STEMS[model], shower, coord_system)


def require_networks(record: ExperimentRecord) -> capabilities.Capabilities:
    """Refuse an experiment without network outputs (422: field ``model``, capability ``networks``)."""
    caps = capabilities.of(record)
    if not caps.models:
        reason = caps.reasons.get(
            "perf-bins", "This experiment carries no reconstruction-network outputs.")
        raise CapabilityError(
            f"Model performance is not available for experiment {record.table_name!r}: {reason}",
            field="model", capability="networks", kind=caps.kind, reason=reason,
            table_name=record.table_name,
        )
    return caps


def frames_offered(record: ExperimentRecord) -> tuple[str, ...]:
    """The coordinate systems whose networks the experiment carries, in the interface's order.

    The networks' columns exist for every frame of a two-shower experiment
    whether or not its hit frames were measured, so this is not the hit-frame
    gate of the capability block.
    """
    return tuple(ddl.COORD_SYSTEMS) if capabilities.of(record).models else ()


# ------------------------------------------------------------------- axis --


@dataclass(frozen=True)
class BinAxis:
    """The momentum bins of the whole dataset, so the axis never moves with the selection."""

    numbers: tuple[int, ...]
    labels: tuple[str, ...]
    p_lo: tuple[float, ...]
    p_hi: tuple[float, ...]
    notices: tuple[str, ...] = ()


def axis_from_ranges(ranges: dict[int, tuple[float, float]]) -> BinAxis:
    """One bin per integer from the smallest to the largest the producer wrote.

    ``ranges[k]`` is the (smallest, largest) momentum found in bin ``k`` over
    both showers. A bin whose momenta leave [k, k + 1) is labelled by number
    with the range actually found (``momentum.relabel_bins``), and its edges
    are that range: a label must not claim what the data contradict.
    """
    if not ranges:
        return BinAxis((), (), (), ())
    lo_bin, hi_bin = min(ranges), max(ranges)
    if hi_bin - lo_bin + 1 > momentum.MAX_CLASSES:
        raise ValidationError(
            f"slice_by=momentum_bin draws at most {momentum.MAX_CLASSES} momentum bins; the "
            f"data span {hi_bin - lo_bin + 1} (bins {lo_bin} to {hi_bin}).",
            field="slice_by",
        )
    nominal = momentum.unit_bins(lo_bin, hi_bin)
    labelled, notices = momentum.relabel_bins(nominal, ranges)
    numbers, labels, p_lo, p_hi = [], [], [], []
    for plain, checked in zip(nominal, labelled):
        k = int(plain.lo)
        numbers.append(k)
        labels.append(checked.label)
        if checked.label != plain.label:
            found = ranges[k]
            p_lo.append(float(found[0]))
            p_hi.append(float(found[1]))
        else:
            p_lo.append(float(plain.lo))
            p_hi.append(float(plain.hi))
    return BinAxis(tuple(numbers), tuple(labels), tuple(p_lo), tuple(p_hi),
                   tuple(typographic(n) for n in notices))


def dataset_axis(con: duckdb.DuckDBPyConnection, record: ExperimentRecord) -> BinAxis:
    """The bin axis of the whole event table, independent of any selection."""
    table = quote(naming.event_table(record.table_name))
    parts = [
        f"SELECT CAST({sh.momentum_bin} AS INTEGER) AS b, CAST({sh.momentum} AS DOUBLE) AS p "
        f"FROM {table}"
        for sh in showers_mod.of(record, "both")
    ]
    rows = con.execute(
        f"SELECT b, min(p), max(p) FROM ({' UNION ALL '.join(parts)}) "
        "WHERE b IS NOT NULL AND p IS NOT NULL GROUP BY b ORDER BY b"
    ).fetchall()
    return axis_from_ranges({int(b): (float(lo), float(hi)) for b, lo, hi in rows})


# ------------------------------------------------------------------ reads --


def read_selection(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    model: str,
    frames: Sequence[str],
) -> dict[str, np.ndarray]:
    """One read of the selected events: bins, truths and every frame's predictions.

    Keys are ``bin_<s>``, ``true_<s>`` and ``pred_<s>_<coord_system>``. SQL NULL
    becomes NaN; nothing is ever filled with zero.
    """
    table = quote(naming.event_table(record.table_name))
    select: list[str] = []
    for sh in showers_mod.of(record, "both"):
        truth, _ = network_columns(model, frames[0], sh.key)
        select.append(f"CAST({sh.momentum_bin} AS DOUBLE) AS bin_{sh.key}")
        select.append(f"CAST({truth} AS DOUBLE) AS true_{sh.key}")
        for coord in frames:
            _, pred = network_columns(model, coord, sh.key)
            select.append(f"CAST({pred} AS DOUBLE) AS pred_{sh.key}_{coord}")
    raw = con.execute(
        f"SELECT {', '.join(select)} FROM {table} WHERE {spec.where_sql()}", spec.params()
    ).fetchnumpy()
    return {k: np.ma.filled(np.ma.asarray(v).astype(np.float64), np.nan) for k, v in raw.items()}


# ----------------------------------------------------------------- points --


@dataclass
class Point:
    """Every statistic of one (frame, shower, bin) group."""

    n: int
    n_missing: int
    rmse: metrics.Estimate
    mae: metrics.Estimate
    bias: metrics.Estimate
    median_rel: median.MedianEstimate
    median_abs: median.MedianEstimate | None = None
    theta_min: float | None = None
    n_small_theta: int = 0
    n_nonpositive_true: int = 0

    @property
    def drives_scale(self) -> bool:
        return self.n >= metrics.SHOW_CI_BELOW_N

    def triple(self, quantity: str) -> tuple[float | None, float | None, float | None]:
        """``(value, interval lo, interval hi)`` of one plotted quantity."""
        est = getattr(self, quantity)
        if est is None:
            return None, None, None
        interval = est.interval
        return est.value, (interval.lo if interval else None), (interval.hi if interval else None)


def point(model: str, pred: np.ndarray, true: np.ndarray, n_missing: int,
          seed: Sequence[int]) -> Point:
    """The statistics of one group's finite ``(pred, true)`` pairs.

    ``seed`` is ``(42, frame, shower, bin)``; each bootstrapped quantity appends
    its own position in :data:`QUANTITIES`.
    """
    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    n = int(pred.size)
    delta = pred - true
    residual = delta * MRAD_PER_RAD if model == "angle" else delta
    summary = metrics.residual_summary(residual)
    positive = true > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        relative = np.abs(delta[positive]) / true[positive]
    out = Point(
        n=n, n_missing=int(n_missing),
        rmse=rmse_mod.rmse_estimate(residual, seed=[*seed, QUANTITY_INDEX["rmse"]]),
        mae=metrics.mae_estimate(residual), bias=summary.bias,
        median_rel=median.median_estimate(relative, seed=[*seed, QUANTITY_INDEX["median_rel"]]),
        n_nonpositive_true=int(n - positive.sum()),
    )
    if model == "angle":
        out.median_abs = median.median_estimate(
            np.abs(residual), seed=[*seed, QUANTITY_INDEX["median_abs"]])
        if n:
            out.theta_min = float(true.min())
            out.n_small_theta = int((true < SMALL_THETA_RAD).sum())
    return out


# ----------------------------------------------------------------- series --


@dataclass
class Series:
    """One shower of one network frame across the momentum bins."""

    model: str
    coord_system: str
    shower: str
    points: list[Point]

    @property
    def frame(self) -> str:
        return ddl.NETWORK_FRAME[self.coord_system]

    @property
    def key(self) -> str:
        return f"{self.frame}:{self.shower}"

    def as_dict(self, digits: int = SIGNIFICANT, keep_order: bool = True) -> dict[str, Any]:
        pts = self.points

        def nums(values: Sequence[Any]) -> list[float | None]:
            return sig_list(values, digits)

        def column(quantity: str) -> dict[str, list[Any]]:
            triples = [p.triple(quantity) for p in pts]
            return {
                quantity: nums([t[0] for t in triples]),
                f"{quantity}_lo": nums([t[1] for t in triples]),
                f"{quantity}_hi": nums([t[2] for t in triples]),
            }

        out: dict[str, Any] = {
            "key": self.key,
            "network": {"model": self.model, "frame": self.frame},
            "coord_system": self.coord_system,
            "shower": self.shower,
            "n": [p.n for p in pts],
            "n_missing": [p.n_missing for p in pts],
            "drives_scale": [p.drives_scale for p in pts],
            **column("rmse"),
            "rmse_method": [_interval_method(p.rmse) for p in pts],
        }
        mae = column("mae")
        out.update({"mae": mae["mae"], "mae_se": nums([p.mae.se for p in pts]),
                    "mae_lo": mae["mae_lo"], "mae_hi": mae["mae_hi"]})
        out.update(column("median_rel"))
        out["median_rel_method"] = [_method(p.median_rel) for p in pts]
        if keep_order:
            out["median_rel_order_lo"] = nums([_order(p.median_rel, 0) for p in pts])
            out["median_rel_order_hi"] = nums([_order(p.median_rel, 1) for p in pts])
            out["median_rel_order_coverage"] = nums([p.median_rel.order_coverage for p in pts])
        out.update(column("bias"))
        if self.model == "angle":
            out.update(column("median_abs"))
            out["median_abs_method"] = [_method(p.median_abs) for p in pts]
            out["theta_min"] = nums([p.theta_min for p in pts])
            out["n_small_theta"] = [p.n_small_theta for p in pts]
        return out


def _method(est: median.MedianEstimate | None) -> str | None:
    if est is None:
        return None
    if est.bootstrap is not None:
        return metrics.METHOD_BOOTSTRAP
    return metrics.METHOD_ORDER if est.order is not None else None


def _interval_method(est: metrics.Estimate | None) -> str | None:
    """The method of an estimate's interval (``chi2_rmse`` or ``bootstrap_percentile``), else None."""
    return est.interval.method if est is not None and est.interval is not None else None


def _order(est: median.MedianEstimate, end: int) -> float | None:
    if est.order is None:
        return None
    return est.order.hi if end else est.order.lo


# ----------------------------------------------------------------- y axes --


def _top(value: float, lo: float | None, hi: float | None, signed: bool) -> float:
    """How far from zero a point reaches: its farther interval end, else its value."""
    if signed:
        reach = [abs(v) for v in (lo, hi) if v is not None]
        return max(reach) if reach else abs(value)
    return hi if hi is not None else value


#: The mantissas an axis top is rounded up to. Each is a whole number of ticks of a round
#: step - 1.2 of 0.2, 1.5 of 0.25 or 0.5, 3 of 0.5, 6 and 8 of 1 or 2 - so the chart's
#: tick step (``perf_bins.js`` ``dividingInterval``) always lands on the top.
TOP_MANTISSAS: tuple[float, ...] = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)


def nice_top(peak: float) -> float:
    """The smallest ``m × 10^k``, ``m`` in :data:`TOP_MANTISSAS`, at or above ``peak`` (> 0)."""
    exponent = math.floor(math.log10(peak))
    for k in (exponent, exponent + 1):
        for m in TOP_MANTISSAS:
            # Rounded to the mantissa's decimals: 1.2 × 10⁻¹ is 0.12, not 0.12000000000000001.
            top = round(m * 10.0 ** k, max(0, 1 - k))
            if top >= peak * (1 - 1e-12):
                return top
    return peak


def y_axis(series: Sequence[Series], axis: BinAxis, quantity: str,
           digits: int = SIGNIFICANT) -> dict[str, Any]:
    """The display range of one quantity, from the points that carry statistical weight.

    ``value`` is the outward rounding of the largest reach among the points
    with N ≥ 15; ``min`` is zero, or ``−value`` for a signed quantity.
    Under-powered points beyond it are clipped by the chart and listed with
    their true values. With no driving point the range comes from the point
    values of the weak ones and is provisional; a whisker is never part of
    that evidence (a t whisker at N = 2 is twelve standard errors wide), so any
    whisker beyond the provisional range is clipped, counted and listed too.
    """
    signed = quantity in SIGNED
    strong: list[float] = []
    weak: list[tuple[float, float, str, int, Point]] = []
    for s in series:
        for i, p in enumerate(s.points):
            value, lo, hi = p.triple(quantity)
            if value is None:
                continue
            top = _top(value, lo, hi, signed)
            if p.drives_scale:
                strong.append(top)
            else:
                weak.append((top, abs(value) if signed else value, s.key, i, p))
    provisional = not strong
    basis = [core for _, core, *_ in weak] if provisional else strong
    peak = max(basis, default=None)
    top_value = None
    if peak is not None and peak > 0:
        top_value = nice_top(peak)
    overflow = []
    n_over = 0
    if top_value is not None:
        for top, _, key, i, p in sorted(weak, key=lambda w: -w[0]):
            if top <= top_value:
                continue
            n_over += 1
            if len(overflow) < MAX_OVERFLOW_LISTED:
                value, lo, hi = p.triple(quantity)
                overflow.append({"series": key, "bin": axis.numbers[i], "n": p.n,
                                 "value": sig(value, digits), "lo": sig(lo, digits),
                                 "hi": sig(hi, digits)})
    out: dict[str, Any] = {
        "value": sig(top_value, digits),
        "min": None if top_value is None else sig(-top_value if signed else 0.0, digits),
        "provisional": provisional,
        "overflow": overflow,
        "n_overflow": n_over,
        "signed": signed,
    }
    if provisional:
        out["note"] = typographic(
            f"Provisional: no point reaches N = {metrics.SHOW_CI_BELOW_N}, so this range comes "
            "from the values of under-powered points, whiskers excluded.")
        if n_over:
            out["note"] += typographic(
                f" {n_over} point{'s' if n_over != 1 else ''} reach{'' if n_over != 1 else 'es'} "
                "beyond it with a whisker: clipped, with the true values listed.")
    elif n_over:
        out["note"] = typographic(
            f"{n_over} under-powered point{'s' if n_over != 1 else ''} (N < "
            f"{metrics.SHOW_CI_BELOW_N}) exceed{'s' if n_over == 1 else ''} the range: "
            "clipped, with the true values listed.")
    return out


# ----------------------------------------------------------------- report --


def quantity_table(model: str) -> dict[str, dict[str, Any]]:
    """What each plotted quantity is and what its whisker means, for tooltips and the drawer."""
    unit = UNITS[model]
    if model == "energy":
        error, absolute, relative = "pred − true", "|pred − true|", "|pred − true| / true"
    else:
        error = "θ_pred − θ_true"
        absolute = "|θ_pred − θ_true|"
        relative = "|θ_pred − θ_true| / θ_true"
    median_interval = (
        f"95% percentile bootstrap of the median (B = {median.BOOTSTRAP_REPLICATES:,}, seeded "
        f"per series, bin and quantity) from N ≥ {median.MIN_BOOTSTRAP_N}; exact "
        f"order-statistic interval from N ≥ {median.MIN_ORDER_N}"
    )
    table: dict[str, dict[str, Any]] = {
        "rmse": {"label": "RMSE", "unit": unit, "signed": False,
                 "definition": f"√mean ({error})²",
                 "interval": (f"95% χ² interval of the RMSE on n degrees of freedom from "
                              f"N ≥ {rmse_mod.MIN_CHI2_N}, which {rmse_mod.NORMALITY}; 95% "
                              f"percentile bootstrap of the RMSE (B = "
                              f"{median.BOOTSTRAP_REPLICATES:,}, seeded per series, bin and "
                              f"quantity) from N ≥ {median.MIN_BOOTSTRAP_N}")},
        "mae": {"label": "MAE", "unit": unit, "signed": False,
                "definition": f"mean {absolute}",
                "interval": "95% Student-t interval of the mean absolute residual, clipped at 0, "
                            f"from N ≥ {gaussian.MIN_MOMENT_SAMPLES}"},
        "median_rel": {"label": "Median relative error", "unit": "fraction", "signed": False,
                       "definition": f"median {relative}", "interval": median_interval},
        "bias": {"label": "Bias", "unit": unit, "signed": True,
                 "definition": f"mean ({error})",
                 "interval": "95% Student-t interval of the mean residual, from "
                             f"N ≥ {gaussian.MIN_MOMENT_SAMPLES}"},
    }
    if model == "angle":
        table["median_abs"] = {"label": "Median absolute error", "unit": unit, "signed": False,
                               "definition": f"median {absolute}", "interval": median_interval}
    return {k: {f: typographic(v) if isinstance(v, str) else v for f, v in d.items()}
            for k, d in table.items()}


@dataclass
class MomentumBinReport:
    """The E2 block: every frame's per-shower statistics across the momentum bins."""

    model: str
    axis: BinAxis
    series: list[Series]
    n_events: int
    unbinned: dict[str, int] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def frames(self) -> list[str]:
        seen: list[str] = []
        for s in self.series:
            if s.frame not in seen:
                seen.append(s.frame)
        return seen

    def nonpositive_true(self) -> dict[str, int]:
        found = {s.key: sum(p.n_nonpositive_true for p in s.points) for s in self.series}
        return {k: v for k, v in found.items() if v}

    def warnings(self) -> list[str]:
        out = list(self.axis.notices)
        for s in self.series:
            if s.points and not any(p.n for p in s.points) and any(p.n_missing for p in s.points):
                who = "Shower " + s.shower.upper()
                out.append(typographic(
                    f"{who} has no {s.frame}-frame {self.model} prediction in this selection: "
                    "every shower is counted in n_missing and none is drawn."))
        return out

    def as_dict(self, digits: int = SIGNIFICANT, keep_order: bool = True) -> dict[str, Any]:
        quantities = quantity_table(self.model)
        return {
            "model": self.model,
            "frames": self.frames,
            "n_events": self.n_events,
            "quantities": quantities,
            "bins": {"index": list(self.axis.numbers), "label": list(self.axis.labels),
                     "p_lo": sig_list(self.axis.p_lo, digits),
                     "p_hi": sig_list(self.axis.p_hi, digits)},
            "series": [s.as_dict(digits, keep_order) for s in self.series],
            "y_max": {q: y_axis(self.series, self.axis, q, digits) for q in quantities},
            "thresholds": dict(THRESHOLDS),
            "bootstrap": {
                "replicates": median.BOOTSTRAP_REPLICATES,
                "seed": median.BOOTSTRAP_SEED,
                "seed_rule": ("numpy SeedSequence([42, frame, shower, bin, quantity]): frame is "
                              "the position in lab, trans, local, shower 0 for A and 1 for B, "
                              "bin the producer's momentum-bin number, quantity the position "
                              "in rmse, mae, median_rel, bias, median_abs"),
                "sampler": ("order statistics of the resample drawn exactly through Beta "
                            "variates; the same distribution as resampling the bin"),
            },
            "excluded": {"unbinned": dict(self.unbinned),
                         "nonpositive_true": self.nonpositive_true()},
            "notes": dict(self.notes),
        }


def _notes(model: str, axis: BinAxis) -> dict[str, str]:
    notes = {
        "showers": (
            "Showers A and B are separate series, each with its own N. A shower without a "
            "prediction (an event with none of that shower's hits) is counted per bin in "
            "n_missing and dropped, never zero-filled."),
        "own_bin": (
            "Each shower is placed in its own momentum bin: shower A by e1_bin and shower B by "
            "e2_bin, because the two showers of an event carry two momenta. The bins are the "
            "producer's integer column over the whole dataset, so the axis does not move with "
            "the selection."),
        "frames": (
            "One response carries every input frame the networks were trained in (absolute, "
            "the legacy per-shower translated frame, and local), so one task can be compared "
            "across frames on a single axis."),
        "calibration": (
            "The networks predict the momentum scale directly; no sampling-fraction "
            "calibration is applied."),
        "whiskers": (
            "Every whisker is the 95% interval of the aggregate it sits on (its interval is "
            "named in quantities), never the dispersion of the showers in the bin. A bin of "
            f"one shower has a value and no whisker, and the median has none below N = "
            f"{median.MIN_ORDER_N}, because none can be estimated there without assuming a "
            "distribution."),
        "scale": (
            f"A point drives the y range from N = {metrics.SHOW_CI_BELOW_N}. Under-powered "
            "points above it are clipped, with their true values in y_max.overflow; with no "
            "driving point the range is provisional, set by point values only, and any "
            "whisker beyond it is clipped and listed likewise."),
    }
    if model == "angle":
        notes["angle"] = (
            "The angle network predicts the polar angle θ only, so there is no azimuth residual "
            "and nothing to wrap. Residuals are in mrad. A relative error |Δθ| / θ grows like "
            f"1 / θ at small θ, so each point also carries the median |Δθ| in mrad, the "
            f"smallest true θ in the bin (rad) and the number of showers with θ < "
            f"{SMALL_THETA_RAD:g} rad.")
    if axis.notices:
        notes["labels"] = " ".join(axis.notices)
    return {k: typographic(v) for k, v in notes.items()}


def map_groups(fn: Callable[..., Point], tasks: Sequence[tuple], workers: int = 1) -> list[Point]:
    """``[fn(*task) for task in tasks]``, on at most ``workers`` threads, in task order.

    One pool per call (per request), never per group, and none at all for one
    worker or one task. Each task carries its own seed, so no random state is
    shared between threads and the result equals the serial path's exactly.
    """
    tasks = list(tasks)
    workers = max(1, min(int(workers), len(tasks)))
    if workers == 1:
        return [fn(*task) for task in tasks]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="calosrv-e2") as pool:
        return list(pool.map(lambda task: fn(*task), tasks))


def build(columns: dict[str, np.ndarray], axis: BinAxis, model: str,
          frames: Sequence[str], showers: Sequence[str] = ("a", "b"),
          workers: int = 1) -> MomentumBinReport:
    """Every (frame, shower, bin) group of the selected events.

    ``columns`` is :func:`read_selection`'s dict (or the same arrays built
    by hand), ``frames`` the coordinate systems to compute, ``workers`` the
    threads the groups are computed on (the service passes ``Settings.threads``).
    """
    unbinned = {shower: int((~np.isfinite(columns[f"bin_{shower}"])).sum()) for shower in showers}
    n_events = int(next(iter(columns.values())).size) if columns else 0
    keys: list[tuple[str, str]] = []
    tasks: list[tuple] = []
    for coord in frames:
        frame_index = ddl.COORD_SYSTEMS.index(coord)
        for si, shower in enumerate(showers):
            bins = columns[f"bin_{shower}"]
            true = columns[f"true_{shower}"]
            pred = columns[f"pred_{shower}_{coord}"]
            both = np.isfinite(pred) & np.isfinite(true)
            keys.append((coord, shower))
            for k in axis.numbers:
                in_bin = bins == k
                chosen = in_bin & both
                tasks.append((model, pred[chosen], true[chosen], int((in_bin & ~both).sum()),
                              (median.BOOTSTRAP_SEED, frame_index, si, k)))
    points = map_groups(point, tasks, workers)
    per = len(axis.numbers)
    series = [Series(model, coord, shower, points[i * per:(i + 1) * per])
              for i, (coord, shower) in enumerate(keys)]
    return MomentumBinReport(model, axis, series, n_events, unbinned, _notes(model, axis))


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            model: str, workers: int = 1) -> MomentumBinReport:
    """The momentum-bin report of one network over the selection, every frame it offers.

    ``workers`` bounds the threads the groups are computed on (:func:`map_groups`).
    """
    if model not in MODELS:
        raise ValidationError(
            f"slice_by=momentum_bin applies to {' and '.join(MODELS)}; got model {model!r}.",
            field="model")
    require_networks(record)
    frames = frames_offered(record)
    axis = dataset_axis(con, record)
    columns = read_selection(con, record, spec, model, frames)
    shower_keys = tuple(sh.key for sh in showers_mod.of(record, "both"))
    return build(columns, axis, model, frames, shower_keys, workers=workers)


# ------------------------------------------------- the XGBoost series (E2) --
#
# An aggregate experiment carries no networks; its E2 view is the shipped
# XGBoost regressor of its species and seed on the notebook's 20 % validation
# split (``calosrv/modelruns``), as one series of the same shape. Only the
# validation rows are drawn - the other 80 % trained the model and would
# flatter it - and the selection applies to them. The angle task adds the
# azimuth as a quantity group of its own: residuals wrapped to (−π, π], no
# relative error (a relative error of an azimuth means nothing) and no bias
# (the mean of a wrapped residual is an average of a circular quantity).

#: The XGBoost series: its code and label, and its frame position in the seed rule.
XGB_CODE = "xgb"
XGB_FRAME_INDEX = len(ddl.COORD_SYSTEMS)
XGB_TASK: dict[str, str] = {"energy": "momentum", "angle": "angle"}

#: φ's quantities, numbered after :data:`QUANTITIES` in the bootstrap seed.
PHI_QUANTITIES: tuple[str, ...] = ("phi_rmse", "phi_mae", "phi_median_abs")
PHI_QUANTITY_INDEX: dict[str, int] = {q: len(QUANTITIES) + i for i, q in enumerate(PHI_QUANTITIES)}


def require_xgb(record: ExperimentRecord, field: str = "model") -> capabilities.Capabilities:
    """Refuse an aggregate experiment whose XGBoost analysis cannot serve the series.

    Unpaired, it has nothing to draw: refused as an experiment without networks
    (capability ``networks``), the pairing's reason appended. Paired but not
    analysed - queued, running, failed or stale - it is refused on the
    ``xgboost`` capability with the worker's sentence.
    """
    caps = capabilities.of(record)
    if caps.can("xgboost"):
        return caps
    reason = caps.reasons.get("perf-bins") or caps.reasons.get("xgboost", "")
    capability = "xgboost" if caps.model_runs else "networks"
    raise CapabilityError(
        f"Model performance is not available for experiment {record.table_name!r}: {reason}",
        field=field, capability=capability, kind=caps.kind, reason=reason,
        table_name=record.table_name,
    )


def phi_point(pred: np.ndarray, true: np.ndarray, n_missing: int, seed: Sequence[int]) -> Point:
    """φ's statistics of one bin: RMSE, MAE and median |Δφ| of the wrapped residual, in mrad."""
    from ..stats.circular import wrap_angle

    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    residual = wrap_angle(pred - true) * MRAD_PER_RAD
    absent = metrics.Estimate(None, n=int(residual.size),
                              note="Not defined for an azimuth (its residual is circular).")
    return Point(
        n=int(residual.size), n_missing=int(n_missing),
        rmse=rmse_mod.rmse_estimate(residual, seed=[*seed, PHI_QUANTITY_INDEX["phi_rmse"]]),
        mae=metrics.mae_estimate(residual), bias=absent,
        median_rel=median.MedianEstimate(None, int(residual.size), None, None, None,
                                         "Not defined for an azimuth."),
        median_abs=median.median_estimate(np.abs(residual),
                                          seed=[*seed, PHI_QUANTITY_INDEX["phi_median_abs"]]),
    )


@dataclass
class XgbSeries(Series):
    """The XGBoost validation-split series: the network series' fields, plus φ for angle."""

    phi_points: list[Point] | None = None

    @property
    def frame(self) -> str:
        return XGB_CODE

    @property
    def key(self) -> str:
        return f"{XGB_CODE}:{self.shower}"

    def as_dict(self, digits: int = SIGNIFICANT, keep_order: bool = True) -> dict[str, Any]:
        from ..modelruns.views import SERIES_LABEL

        out = super().as_dict(digits, keep_order)
        out["network"] = {"model": self.model, "frame": XGB_CODE}
        out["coord_system"] = XGB_CODE
        out = {"code": XGB_CODE, "label": SERIES_LABEL, **out}
        if self.phi_points is not None:
            pts = self.phi_points
            for name, attr in (("phi_rmse", "rmse"), ("phi_mae", "mae"),
                               ("phi_median_abs", "median_abs")):
                triples = [p.triple(attr) for p in pts]
                out[name] = sig_list([t[0] for t in triples], digits)
                out[f"{name}_lo"] = sig_list([t[1] for t in triples], digits)
                out[f"{name}_hi"] = sig_list([t[2] for t in triples], digits)
            out["phi_mae_se"] = sig_list([p.mae.se for p in pts], digits)
            out["phi_rmse_method"] = [_interval_method(p.rmse) for p in pts]
            out["phi_median_abs_method"] = [_method(p.median_abs) for p in pts]
        return out


def xgb_quantity_table(model: str) -> dict[str, dict[str, Any]]:
    """The network table for θ (or momentum), and φ's three quantities for angle."""
    table = quantity_table(model)
    if model != "angle":
        return table
    median_interval = table["median_abs"]["interval"]
    error = "Δφ = φ_pred − φ_true wrapped to (−π, π]"
    phi = {
        "phi_rmse": {"label": "RMSE of φ", "unit": "mrad", "signed": False,
                     "definition": f"√mean (Δφ)², {error}", "interval": table["rmse"]["interval"]},
        "phi_mae": {"label": "MAE of φ", "unit": "mrad", "signed": False,
                    "definition": f"mean |Δφ|, {error}", "interval": table["mae"]["interval"]},
        "phi_median_abs": {"label": "Median absolute error of φ", "unit": "mrad", "signed": False,
                           "definition": f"median |Δφ|, {error}", "interval": median_interval},
    }
    return {**table, **{k: {f: typographic(v) if isinstance(v, str) else v for f, v in d.items()}
                        for k, d in phi.items()}}


@dataclass
class XgbReport(MomentumBinReport):
    """E2 on an aggregate experiment: the XGBoost series and how the split selects it."""

    run: dict[str, Any] = field(default_factory=dict)
    split: dict[str, Any] = field(default_factory=dict)

    @property
    def frames(self) -> list[str]:
        return [XGB_CODE]

    def warnings(self) -> list[str]:
        out = list(self.axis.notices)
        for s in self.series:
            if s.points and not any(p.n for p in s.points) and any(p.n_missing for p in s.points):
                out.append(typographic(
                    f"The XGBoost {XGB_TASK[self.model]} prediction is missing for every validation event "
                    "of this selection: each is counted in n_missing and none is drawn."))
        if not self.split.get("reproduced", True):
            out.append(self.run["split"]["warning"])
        return out

    def as_dict(self, digits: int = SIGNIFICANT, keep_order: bool = True) -> dict[str, Any]:
        out = super().as_dict(digits, keep_order)
        quantities = xgb_quantity_table(self.model)
        out["quantities"] = quantities
        y_max = {q: y_axis(self.series, self.axis, q, digits) for q in quantity_table(self.model)}
        if self.model == "angle":
            phi_series = [Series(s.model, "lab", s.shower, s.phi_points or []) for s in self.series]
            for name, attr in (("phi_rmse", "rmse"), ("phi_mae", "mae"),
                               ("phi_median_abs", "median_abs")):
                block = y_axis(phi_series, self.axis, attr, digits)
                for entry in block["overflow"]:
                    entry["series"] = f"{XGB_CODE}:a"
                y_max[name] = block
            out["quantity_groups"] = {"theta": list(quantity_table("angle")),
                                      "phi": list(PHI_QUANTITIES)}
        out["y_max"] = y_max
        out["source"] = XGB_CODE
        out["series_label"] = typographic(self.run.get("series_label", ""))
        out["split"] = self.split
        out["bootstrap"] = {
            **out["bootstrap"],
            "seed_rule": (f"numpy SeedSequence([42, {XGB_FRAME_INDEX}, 0, bin, quantity]): "
                          f"{XGB_FRAME_INDEX} is the XGBoost series after the three network "
                          "frames, quantity the position in rmse, mae, median_rel, bias, "
                          "median_abs, phi_rmse, phi_mae, phi_median_abs"),
        }
        return out


def _xgb_notes(model: str, axis: BinAxis) -> dict[str, str]:
    notes = {
        "series": (
            "The shipped XGBoost regressor of this experiment's species and seed, on the "
            "notebook's 20 % validation split (train_test_split(test_size=0.2, "
            "random_state=42)): the rows it was not trained on. The selection applies to them; "
            "the training rows it selects are counted in split.n_training_excluded and not "
            "drawn."),
        "showers": (
            "One shower per event, so one series. An event without a finite prediction or truth "
            "is counted per bin in n_missing and dropped, never zero-filled."),
        "own_bin": (
            "Each event is placed in the producer's momentum bin (e1_bin) over the whole "
            "dataset, so the axis does not move with the selection."),
        "frames": (
            "The model reads 52 event-level features of the absolute, per-shower translated "
            "and local frames at once, so the series has no input frame."),
        "calibration": (
            "The regressor predicts the momentum scale directly; no sampling-fraction "
            "calibration is applied."),
        "whiskers": (
            "Every whisker is the 95% interval of the aggregate it sits on (its interval is "
            "named in quantities), never the dispersion of the events in the bin. A bin of "
            f"one event has a value and no whisker, and the median has none below N = "
            f"{median.MIN_ORDER_N}."),
        "scale": (
            f"A point drives the y range from N = {metrics.SHOW_CI_BELOW_N}. Under-powered "
            "points above it are clipped, with their true values in y_max.overflow; with no "
            "driving point the range is provisional, set by point values only."),
    }
    if model == "angle":
        notes["angle"] = (
            "θ is drawn as the networks' θ: residuals in mrad, a relative error |Δθ| / θ that "
            "grows like 1 / θ at small θ, the median |Δθ|, the smallest true θ and the count "
            f"below {SMALL_THETA_RAD:g} rad. φ is its own quantity group (phi_rmse, phi_mae, "
            "phi_median_abs): its residual is wrapped to (−π, π] and in mrad, with no relative "
            "error and no bias, because φ is an azimuth. The notebook's angle bars showed φ "
            "only; both are offered.")
    if axis.notices:
        notes["labels"] = " ".join(axis.notices)
    return {k: typographic(v) for k, v in notes.items()}


def compute_xgb(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                model: str, workers: int = 1) -> XgbReport:
    """The XGBoost series of an aggregate experiment over the selection's validation rows.

    ``workers`` bounds the threads the groups are computed on (:func:`map_groups`).
    """
    from ..modelruns import store as xgb_store
    from ..modelruns import views as xgb_views

    if model not in MODELS:
        raise ValidationError(
            f"slice_by=momentum_bin applies to {' and '.join(MODELS)}; got model {model!r}.",
            field="model")
    require_xgb(record)
    task = XGB_TASK[model]
    runs = xgb_store.read_runs(con, record.table_name)
    if runs is None or task not in runs:
        reason = "The stored XGBoost analysis is missing; Admin Settings › Model runs re-analyses it."
        raise CapabilityError(
            f"Model performance is not available for experiment {record.table_name!r}: {reason}",
            field="model", capability="xgboost", kind=record.kind, reason=reason,
            table_name=record.table_name)
    axis = dataset_axis(con, record)
    where = spec.where_sql("e")
    rows = xgb_store.read_holdout(con, record, task, where, spec.params())
    n_selected = xgb_store.count_selected(con, record, where, spec.params())
    bins = rows["bin"]
    label = "momentum" if task == "momentum" else "theta"
    true, pred = rows[f"true_{label}"], rows[f"pred_{label}"]
    both = np.isfinite(true) & np.isfinite(pred)
    phi_ok = None
    if task == "angle":
        phi_true, phi_pred = rows["true_phi"], rows["pred_phi"]
        phi_ok = np.isfinite(phi_true) & np.isfinite(phi_pred)
    tasks, phi_tasks = [], []
    for k in axis.numbers:
        in_bin = bins == k
        chosen = in_bin & both
        seed = (median.BOOTSTRAP_SEED, XGB_FRAME_INDEX, 0, k)
        tasks.append((model, pred[chosen], true[chosen], int((in_bin & ~both).sum()), seed))
        if task == "angle":
            pick = in_bin & phi_ok
            phi_tasks.append((phi_pred[pick], phi_true[pick], int((in_bin & ~phi_ok).sum()), seed))
    # θ (or momentum) and φ groups on one pool; φ's follow θ's in the result.
    computed = map_groups(lambda kind, *args: (point if kind == "x" else phi_point)(*args),
                          [("x", *t) for t in tasks] + [("phi", *t) for t in phi_tasks], workers)
    points = computed[:len(tasks)]
    phi_points = computed[len(tasks):] if task == "angle" else None
    series = XgbSeries(model, "lab", "a", points, phi_points=phi_points)
    n_val = int(bins.size)
    run = xgb_views.run_block(runs, task)
    run["series_label"] = xgb_views.SERIES_LABEL
    split = {
        "n_selected": n_selected, "n_validation": n_val,
        "n_training_excluded": n_selected - n_val,
        "fraction": xgb_views.TEST_SIZE,
        "rule": "train_test_split(np.arange(n), test_size=0.2, random_state=42) over the "
                "event table in event_number order (the producer file's order)",
        "reproduced": run["split"]["reproduced"],
    }
    unbinned = {"a": int((~np.isfinite(bins)).sum())}
    return XgbReport(model, axis, [series], n_val, unbinned, _xgb_notes(model, axis),
                     run=run, split=split)
