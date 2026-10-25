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

* RMSE, whose interval is the square root of the Student-t interval of the mean
  squared residual (N ≥ 2); MAE with the Student-t interval of the mean
  absolute residual, clipped at zero (N ≥ 2); bias with the Student-t interval
  of the mean residual (N ≥ 2). All three are reported as numbers from N = 1,
  without an interval, because a value is a claim about a sample and an
  interval is a claim about its population.
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
N = 15 (the core-refit floor); ``y_max`` is the outward 1-2-5 rounding of the
largest interval end among the driving points. An under-powered point above it
is clipped by the chart, so it is listed in ``overflow`` with its true value.
When no point drives the scale the range is taken from the weak points and
marked provisional.

A shower without a prediction (an event with none of that shower's hits) is
counted per bin in ``n_missing`` and dropped - never zero-filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import SIGNIFICANT, sig, sig_list
from ..errors import CapabilityError, ValidationError
from ..stats import clip as clip_mod
from ..stats import gaussian, median, metrics, momentum
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
        rmse=summary.rmse, mae=metrics.mae_estimate(residual), bias=summary.bias,
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


def y_axis(series: Sequence[Series], axis: BinAxis, quantity: str,
           digits: int = SIGNIFICANT) -> dict[str, Any]:
    """The display range of one quantity, from the points that carry statistical weight.

    ``value`` is the outward rounding of the largest reach among the points
    with N ≥ 15; ``min`` is zero, or ``−value`` for a signed quantity.
    Under-powered points beyond it are clipped by the chart and listed with
    their true values. With no driving point the range comes from the weak
    ones and is provisional, and nothing can overflow it.
    """
    signed = quantity in SIGNED
    strong: list[float] = []
    weak: list[tuple[float, str, int, Point]] = []
    for s in series:
        for i, p in enumerate(s.points):
            value, lo, hi = p.triple(quantity)
            if value is None:
                continue
            top = _top(value, lo, hi, signed)
            if p.drives_scale:
                strong.append(top)
            else:
                weak.append((top, s.key, i, p))
    provisional = not strong
    basis = [t for t, *_ in weak] if provisional else strong
    peak = max(basis, default=None)
    top_value = None
    if peak is not None and peak > 0:
        top_value = clip_mod.nice_range(0.0, peak, fine=True)[1]
    overflow = []
    n_over = 0
    if top_value is not None and not provisional:
        for top, key, i, p in sorted(weak, key=lambda w: -w[0]):
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
            "from under-powered points.")
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
                 "interval": "square root of the 95% Student-t interval of the mean squared "
                             f"residual, from N ≥ {gaussian.MIN_MOMENT_SAMPLES}"},
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
            "driving point the range is provisional."),
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


def build(columns: dict[str, np.ndarray], axis: BinAxis, model: str,
          frames: Sequence[str], showers: Sequence[str] = ("a", "b")) -> MomentumBinReport:
    """Every (frame, shower, bin) group of the selected events.

    ``columns`` is :func:`read_selection`'s dict (or the same arrays built
    by hand), ``frames`` the coordinate systems to compute.
    """
    series: list[Series] = []
    unbinned = {shower: int((~np.isfinite(columns[f"bin_{shower}"])).sum()) for shower in showers}
    n_events = int(next(iter(columns.values())).size) if columns else 0
    for coord in frames:
        frame_index = ddl.COORD_SYSTEMS.index(coord)
        for si, shower in enumerate(showers):
            bins = columns[f"bin_{shower}"]
            true = columns[f"true_{shower}"]
            pred = columns[f"pred_{shower}_{coord}"]
            both = np.isfinite(pred) & np.isfinite(true)
            points = []
            for k in axis.numbers:
                in_bin = bins == k
                chosen = in_bin & both
                points.append(point(
                    model, pred[chosen], true[chosen], int((in_bin & ~both).sum()),
                    seed=(median.BOOTSTRAP_SEED, frame_index, si, k),
                ))
            series.append(Series(model, coord, shower, points))
    return MomentumBinReport(model, axis, series, n_events, unbinned, _notes(model, axis))


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            model: str) -> MomentumBinReport:
    """The momentum-bin report of one network over the selection, every frame it offers."""
    if model not in MODELS:
        raise ValidationError(
            f"slice_by=momentum_bin applies to {' and '.join(MODELS)}; got model {model!r}.",
            field="model")
    require_networks(record)
    frames = frames_offered(record)
    axis = dataset_axis(con, record)
    columns = read_selection(con, record, spec, model, frames)
    shower_keys = tuple(sh.key for sh in showers_mod.of(record, "both"))
    return build(columns, axis, model, frames, shower_keys)
