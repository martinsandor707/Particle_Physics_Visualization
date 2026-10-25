"""Reconstructed energy versus separation distance - the fourth panel.

The six-stage pipeline this implements:

1. **Voxel energy summation.** Per event, the deposited energy attributed to each
   shower::

       E_dep_A_pred = sum(energy * voxel_fA_pred)
       E_dep_B_pred = sum(energy * (1 - voxel_fA_pred))
       E_dep_A_true = sum(energy * voxel_fA_true)
       E_dep_B_true = sum(energy * (1 - voxel_fA_true))

   These are precomputed at ingest and stored per event, so this endpoint reads
   roughly twenty thousand rows rather than 22.5 million.

2. **Sampling-fraction calibration.** A sampling calorimeter registers only a
   fraction of a particle's energy in its active cells. The summed deposit per
   event here is of order 0.05 GeV while the incident momenta are 0.4-20 GeV, so
   a deposited sum and an incident momentum are quantities on different scales
   and must never share an axis. The calibration constants come from ground
   truth, per shower, over the whole selection::

       c_A = sum(incoming_momentum_A) / sum(E_dep_A_true)
       c_B = sum(incoming_momentum_B) / sum(E_dep_B_true)

       E_reco_A = E_dep_A_pred * c_A
       E_reco_B = E_dep_B_pred * c_B

   Summing before dividing, rather than averaging per-event ratios, is
   deliberate: a per-event normalisation forces each event onto its own truth
   exactly, which erases the containment scatter the resolution measurement
   exists to quantify.

3. **Separation distance** is the per-event ``centroid_AB_distance``.

4. **Discretisation** into the notebook's slices - 50, 100, 150, 200 mm - plus an
   overflow slice for the well-separated majority (see ``stats/slices.py``).

5. **Gaussian parameters** per slice and series, by moments, with an iterated
   core refit (see ``stats/gaussian.py``). Numbers are reported from N = 2; what
   the sample size gates is which *marks* are drawn beside them, per the
   three-mode ladder in :func:`_build_series`.

6. **Reference benchmarks.** Isolated-shower references at the mean true E1 and
   E2 of the selection, so the overlap-degraded reconstructions can be read
   against the single-particle case. They are drawn as a position and a width,
   never as a density curve, and never contribute to the density axis.

**Sliced by incident momentum (B3).** :func:`compute_by_momentum` serves the
same panel with each *shower* placed by its own incident momentum - the
CALIBRATION notebook's response grid, windows (1, 2, 5, 10, 15, 19) ± 0.5 GeV,
or the producer's 1 GeV bins - for every kind of experiment: two showers (the
truth split by default, the network's split on request), one shower with hits,
or the event-level aggregate (one deposit series). What changes, and why:

* **Showers are counted, not events.** Shower A goes by its own momentum and B
  by its own, so one event can sit in two slices, and a shower whose momentum
  falls in no window is counted under ``outside_slices`` and drawn nowhere.
* **The calibration is the D panel's,** per shower over the whole selection
  before slicing, showers outside every window included: the constants do not
  move with the slicing, and a slice can never be calibrated onto its own truth.
* **Each slice has its own energy axis.** A 1 GeV window and a 19 GeV window on
  one shared 0-25 GeV axis leave the first one or two bins across its peak. A
  slice's range is set only by its series that reach the histogram floor;
  where none does, the range comes from the few showers there are and is
  marked provisional. The bin *count* is shared - the Rice rule of the
  smallest drawn series - so no histogram is finer than its statistics.
* **No benchmarks.** The stated 5% isolated-shower reference means nothing for
  a single shower. Each slice instead carries the measured mean incident
  momentum of its showers, with its sample SD and the Student-t 95% interval
  of the mean, so linearity reads directly against the calibrated energies.

The marks of every series come from :func:`_build_series`, the D panel's own
ladder. The momentum-only keys are emitted only in this view, so the D-sliced
payload is unchanged byte for byte.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..errors import ValidationError
from ..stats import clip as clip_mod
from ..stats import gaussian, histogram
from ..stats import momentum as momentum_mod
from ..stats.slices import Slice, build_slices, case_sql
from ..text import typographic
from . import capabilities
from . import showers as showers_mod
from .filters import FilterSpec

log = logging.getLogger(__name__)

#: The four reconstructed series, and how each is labelled in the panel.
SERIES = (
    ("e_a_pred", "Shower A - model", "a", "pred"),
    ("e_b_pred", "Shower B - model", "b", "pred"),
    ("e_a_true", "Shower A - truth", "a", "true"),
    ("e_b_true", "Shower B - truth", "b", "true"),
)

#: Fractional resolution of an isolated, non-overlapping shower, used to draw
#: the reference benchmark curves. Stated explicitly rather than fitted, because
#: this dataset contains no isolated single-particle events to fit it from - it
#: is entirely two-shower. The panel labels these curves as a stated reference.
ISOLATED_RESOLUTION = 0.05


#: Most individual event energies shipped for an event strip. A slice below the
#: histogram threshold holds at most 14 events, so this is only a guard against
#: a future threshold change making the payload unbounded.
MAX_STRIP_POINTS = 200

#: Drawn when a slice is below the histogram floor but still reports moments.
STRIP_MESSAGE = (
    "N = {n}: the density histogram is suppressed - at this sample size it "
    "would be a comb of spikes whose heights are set by the bin width rather "
    "than by physics. The individual events, the mean with its 95% confidence "
    "interval and the sample dispersion are drawn instead, and mu and sigma "
    "are reported in the table with their own uncertainty."
)

#: Drawn when the slice cannot support a continuous curve either.
NO_CURVE_MESSAGE = (
    "N = {n}: below the {threshold}-event floor for a continuous density "
    "curve. A smooth curve from this few events would assert a shape the "
    "sample cannot constrain, so only the events and the summary markers are "
    "drawn. mu and sigma are still reported, with their uncertainty."
)

#: Drawn when every event in the slice carries the same energy.
DEGENERATE_MESSAGE = (
    "N = {n}, all at one energy to floating-point precision. The width is a "
    "measured zero rather than an unknown, and no density curve is drawn: a "
    "delta is not a density and would put an unbounded spike on the axis."
)


def _round(value: float) -> float:
    """Six significant figures - well beyond display precision, far smaller.

    The payload budget for this architecture is 100 KB (CLAUDE.md section 1.1)
    and a full-precision float64 costs ~24 characters in JSON against ~8 here.
    """
    return float(f"{float(value):.6g}")


def _round_all(values: Sequence[float] | np.ndarray) -> list[float]:
    return [_round(v) for v in values]


#: The sample sizes at which each mark becomes drawable, shipped so the client
#: never has to re-derive the policy from a single ambiguous number.
THRESHOLDS = {
    "moment": gaussian.MIN_MOMENT_SAMPLES,
    "curve": gaussian.MIN_CURVE_SAMPLES,
    "histogram": histogram.MIN_HISTOGRAM_SAMPLES,
    "core": gaussian.MIN_CORE_SAMPLES,
    "robust": gaussian.MIN_ROBUST_SAMPLES,
}


@dataclass
class SeriesFit:
    key: str
    label: str
    shower: str
    kind: str
    slice_index: int
    fit: gaussian.GaussianFit
    hist: histogram.Histogram | None
    #: "histogram" | "curve+strip" | "strip" - what the client must draw. An
    #: explicit mode, rather than something inferred from a null histogram.
    draw: str = "strip"
    #: Whether this series may set the density axis maximum. True only above the
    #: histogram threshold: a curve whose peak is 1/(sigma*sqrt(2pi)) with a
    #: poorly determined sigma must not flatten the well-measured slices.
    drives_scale: bool = False
    curve_y: list[float] = field(default_factory=list)
    #: Peak of the drawn curve, so a clipped low-N curve can be named in the
    #: footnote without the client rescanning the array.
    curve_peak: float | None = None
    #: Individual reconstructed energies, drawn *instead of* the histogram when
    #: the slice is below the histogram floor.
    strip: list[float] = field(default_factory=list)
    strip_truncated: bool = False
    message: str = ""

    def markers(self) -> dict[str, float] | None:
        """The mean marker's two interval spans - deliberately kept apart.

        ``ci95`` is the inferential uncertainty *of the mean* and is drawn as a
        capped whisker. ``dispersion`` is the spread *of the events* and is
        drawn as an uncapped shaded band behind the marker. They differ by a
        factor of sqrt(N) and answer opposite questions, so they are named
        separately here to make drawing them with the same mark an explicit
        mistake rather than an easy one.
        """
        if self.fit.mu is None or self.fit.sigma is None:
            return None
        lo, hi = self.fit.mu_ci95 or (self.fit.mu, self.fit.mu)
        return {
            "mu": _round(self.fit.mu),
            "ci95_lo": _round(lo),
            "ci95_hi": _round(hi),
            "dispersion_lo": _round(self.fit.mu - self.fit.sigma),
            "dispersion_hi": _round(self.fit.mu + self.fit.sigma),
        }

    def as_dict(self) -> dict[str, Any]:
        hist = None
        if self.hist is not None:
            # Bin centres are hoisted to axis.hist_centres: they are identical
            # across every series by construction.
            hist = {
                "counts": _round_all(self.hist.counts),
                "n": self.hist.n,
                "n_in_range": self.hist.n_in_range,
            }
        return {
            "key": self.key,
            "label": self.label,
            "shower": self.shower,
            "kind": self.kind,
            "slice": self.slice_index,
            "fit": self.fit.as_dict(),
            "draw": self.draw,
            "drives_scale": self.drives_scale,
            "estimator": self.fit.estimator,
            "histogram": hist,
            # x is hoisted to axis.curve_x, shared by every series.
            "curve": {"y": self.curve_y},
            "curve_peak": self.curve_peak,
            "strip": {
                "values": self.strip,
                "n_shown": len(self.strip),
                "truncated": self.strip_truncated,
            },
            "markers": self.markers(),
            "message": self.message,
        }


@dataclass
class EnergyDistribution:
    #: Separation slices, or the momentum classes of the B3 view.
    slices: Sequence[Slice | momentum_mod.MomentumClass]
    slice_counts: dict[int, int]
    series: list[SeriesFit]
    calibration: dict[str, float | None]
    axis: dict[str, Any]
    benchmarks: list[dict[str, Any]]
    n_events: int
    scale: str
    #: Sample sizes at which each mark becomes drawable.
    thresholds: dict[str, int] = field(
        default_factory=lambda: dict(THRESHOLDS)
    )
    #: The momentum view's own keys, appended after the shared ones and only in
    #: that view - which is what keeps the D-sliced payload byte-identical.
    momentum: dict[str, Any] | None = None
    #: Sentences only the query layer can write (relabelled momentum bins, a
    #: censored sample), for the route's warnings. Not part of the payload.
    notices: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out = {
            "slices": [s.as_dict() for s in self.slices],
            "slice_counts": {str(k): v for k, v in self.slice_counts.items()},
            "series": [s.as_dict() for s in self.series],
            "calibration": self.calibration,
            "axis": self.axis,
            "benchmarks": self.benchmarks,
            "n_events": self.n_events,
            "scale": self.scale,
            "thresholds": self.thresholds,
        }
        if self.momentum is not None:
            out.update(self.momentum)
        return out


def _build_series(
    key: str,
    label: str,
    shower: str,
    kind: str,
    slice_index: int,
    slice_label: str,
    sample: np.ndarray,
    edges_array: np.ndarray,
    curve_x: np.ndarray,
) -> SeriesFit:
    """One series in one separation slice, with the marks its N supports.

    Three regimes, and the numbers in the summary table are the same in all of
    them - only the marks change:

    ==========================  ===============  ============  ==================
    condition                   draw             drives_scale  marks
    ==========================  ===============  ============  ==================
    N >= MIN_HISTOGRAM_SAMPLES  ``histogram``    yes           histogram + curve
    N >= MIN_CURVE_SAMPLES      ``curve+strip``  no            curve + events
    otherwise                   ``strip``        no            events only
    ==========================  ===============  ============  ==================

    A width of exactly zero forces ``strip`` at any N: a delta is not a density,
    and drawing one as a curve would put an infinite spike on the axis.
    """
    finite = sample[np.isfinite(sample)]
    fit = gaussian.fit_gaussian(sample, label=f"{label}, {slice_label}")

    lo, hi = float(edges_array[0]), float(edges_array[-1])
    fit.n_in_range = int(((finite >= lo) & (finite <= hi)).sum())

    n = fit.n
    drawable = fit.sigma_core is not None and (fit.sigma_core or 0) > 0

    if n >= histogram.MIN_HISTOGRAM_SAMPLES and drawable:
        curve = gaussian.gaussian_curve(curve_x, fit.mu_core, fit.sigma_core)
        return SeriesFit(
            key=key, label=label, shower=shower, kind=kind,
            slice_index=slice_index, fit=fit,
            hist=histogram.density_histogram(sample, edges_array),
            draw="histogram", drives_scale=True,
            curve_y=_round_all(curve),
            curve_peak=_round(gaussian.unit_area_amplitude(fit.sigma_core)),
        )

    # Below the histogram floor the events themselves are the honest mark.
    ordered = np.sort(finite)
    strip = _round_all(ordered[:MAX_STRIP_POINTS])
    truncated = bool(ordered.size > MAX_STRIP_POINTS)

    if n >= gaussian.MIN_CURVE_SAMPLES and drawable:
        curve = gaussian.gaussian_curve(curve_x, fit.mu_core, fit.sigma_core)
        return SeriesFit(
            key=key, label=label, shower=shower, kind=kind,
            slice_index=slice_index, fit=fit, hist=None,
            draw="curve+strip", drives_scale=False,
            curve_y=_round_all(curve),
            curve_peak=_round(gaussian.unit_area_amplitude(fit.sigma_core)),
            strip=strip, strip_truncated=truncated,
            message=STRIP_MESSAGE.format(n=n),
        )

    return SeriesFit(
        key=key, label=label, shower=shower, kind=kind,
        slice_index=slice_index, fit=fit, hist=None,
        draw="strip", drives_scale=False,
        strip=strip, strip_truncated=truncated,
        message=(
            DEGENERATE_MESSAGE.format(n=n) if fit.degenerate
            else NO_CURVE_MESSAGE.format(
                n=n, threshold=gaussian.MIN_CURVE_SAMPLES
            )
        ),
    )


#: The ladder under its public name, for the panels that draw a distribution
#: with the same marks (the prediction residuals of Page 2, the B3 view).
build_series = _build_series


def _fetch(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    slices: Sequence[Slice],
    frame_code: str = "abs",
) -> dict[str, np.ndarray]:
    """Per-event energies, slice assignment and truth momenta for the selection.

    ``frame_code`` picks the segmentation network (``abs``, ``trn``, ``loc``)
    whose voxel fractions split each event's deposited energy.
    """
    table = quote(naming.event_table(record.table_name))
    f = frame_code
    return con.execute(
        f"""
        SELECT
            {case_sql(slices)}          AS slice_index,
            e_a_pred_{f} AS e_a_pred, e_b_pred_{f} AS e_b_pred,
            e_a_true_{f} AS e_a_true, e_b_true_{f} AS e_b_true,
            CAST(e1 AS DOUBLE)          AS e1,
            CAST(e2 AS DOUBLE)          AS e2
        FROM {table}
        WHERE {spec.where_sql()}
        """,
        spec.params(),
    ).fetchnumpy()


def compute(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    edges: Sequence[float] | None = None,
    bins: int | None = None,
    calibrated: bool = True,
    clip_low: float = clip_mod.DEFAULT_LOW_PERCENTILE,
    clip_high: float = clip_mod.DEFAULT_HIGH_PERCENTILE,
    coord_system: str = "lab",
    curve_points: int = histogram.CURVE_POINTS,
) -> EnergyDistribution:
    """Build the reconstructed-energy distribution for the active selection.

    Always the segmentation reconstruction - E_A and E_B from that network's
    voxel fractions - of the frame ``coord_system`` names; D stays the
    laboratory separation.
    """
    slices = build_slices(edges) if edges else build_slices()
    columns = _fetch(con, record, spec, slices, ddl.frame_code(coord_system))

    slice_index = np.asarray(columns["slice_index"], dtype=np.int64)
    n_events = int(slice_index.size)

    raw = {
        key: np.nan_to_num(np.asarray(columns[key], dtype=np.float64))
        for key, _, _, _ in SERIES
    }
    e1 = np.nan_to_num(np.asarray(columns["e1"], dtype=np.float64))
    e2 = np.nan_to_num(np.asarray(columns["e2"], dtype=np.float64))

    # --- Stage 2: sampling-fraction calibration, fitted on this selection ----
    dep_a_true = float(raw["e_a_true"].sum())
    dep_b_true = float(raw["e_b_true"].sum())
    c_a = float(e1.sum() / dep_a_true) if dep_a_true > 0 else None
    c_b = float(e2.sum() / dep_b_true) if dep_b_true > 0 else None

    if calibrated and c_a and c_b:
        factor = {"a": c_a, "b": c_b}
        values = {
            key: raw[key] * factor[shower] for key, _, shower, _ in SERIES
        }
        scale, unit = "calibrated", "GeV (incident-equivalent)"
    else:
        values = dict(raw)
        scale, unit = "deposited", "GeV (deposited)"

    # --- Display range, clipped to percentiles for readability --------------
    pooled = np.concatenate([values[key] for key, _, _, _ in SERIES])
    if calibrated and c_a and c_b:
        # Keep the benchmark markers inside the visible range.
        pooled = np.concatenate([pooled, e1, e2])
    clipping = clip_mod.percentile_clip(
        pooled, low=clip_low, high=clip_high, floor_at_zero=True, pad=0.05
    )

    # Round outward to clean tick boundaries before anything is binned, so the
    # histogram bars, the fitted curve and the axis labels all share one range.
    # Rounding only in the chart would leave the bars drifting against the ticks.
    axis_lo, axis_hi, axis_interval = clip_mod.nice_range(clipping.lo, clipping.hi)

    # --- Stages 4 and 5: per slice, per series ------------------------------
    slice_counts = {
        s.index: int((slice_index == s.index).sum()) for s in slices
    }

    # All slices share one binning, or they cannot be compared bin by bin. The
    # count is set by the smallest slice whose histogram will actually be drawn,
    # so no histogram on the panel is finer than its own statistics support - a
    # slice of twenty events binned for twenty thousand is the spike comb again.
    drawn = [
        n for index, n in slice_counts.items()
        if n >= histogram.MIN_HISTOGRAM_SAMPLES
    ]
    resolved_bins = (
        int(bins) if bins is not None
        else histogram.adaptive_bins(min(drawn) if drawn else 0)
    )
    edges_array = histogram.axis_edges(axis_lo, axis_hi, resolved_bins)
    curve_x = histogram.curve_axis(axis_lo, axis_hi, curve_points)
    fitted: list[SeriesFit] = []
    for s in slices:
        mask = slice_index == s.index
        if not mask.any():
            continue
        for key, label, shower, kind in SERIES:
            fitted.append(
                _build_series(
                    key=key, label=label, shower=shower, kind=kind,
                    slice_index=s.index, slice_label=s.label,
                    sample=values[key][mask],
                    edges_array=edges_array, curve_x=curve_x,
                )
            )

    # --- Stage 6: isolated-shower reference benchmarks ----------------------
    benchmarks: list[dict[str, Any]] = []
    if calibrated and c_a and c_b:
        for label, truth, shower in (
            ("Isolated Reference E₁ (no overlap)", e1, "a"),
            ("Isolated Reference E₂ (no overlap)", e2, "b"),
        ):
            if truth.size == 0:
                continue
            mu = float(truth.mean())
            sigma = max(ISOLATED_RESOLUTION * mu, 1e-6)
            benchmarks.append(
                {
                    "label": label,
                    "shower": shower,
                    "mu": _round(mu),
                    "sigma": _round(sigma),
                    "resolution": ISOLATED_RESOLUTION,
                    # Marked, not merely styled: a reader must be able to tell a
                    # stated benchmark from a measured distribution from the
                    # payload alone, and the client must know not to let it near
                    # the density axis.
                    "kind": "benchmark",
                    "fitted": False,
                    "drawn_as": "reference_marker",
                    "tooltip_prefix": "[Reference Benchmark]",
                    "contributes_to_y_axis": False,
                    "note": (
                        "Reference width is a stated single-shower resolution of "
                        f"{100 * ISOLATED_RESOLUTION:.0f}%, not a fit: this "
                        "dataset contains no isolated single-particle events. "
                        "It is drawn as a position and a width rather than as a "
                        "density curve, because a unit-area Gaussian this narrow "
                        f"peaks near {gaussian.unit_area_amplitude(sigma):.2f} "
                        "GeV⁻¹ and would take the density axis away from the "
                        "reconstructions the panel is about."
                    ),
                }
            )

    return EnergyDistribution(
        slices=list(slices),
        slice_counts=slice_counts,
        series=fitted,
        calibration={
            "c_a": c_a,
            "c_b": c_b,
            "sampling_fraction_a": (1.0 / c_a) if c_a else None,
            "sampling_fraction_b": (1.0 / c_b) if c_b else None,
            "applied": bool(calibrated and c_a and c_b),
            "method": (
                "c = sum(incoming_momentum) / sum(deposited energy attributed "
                "by ground truth), fitted per shower over the active selection"
            ),
        },
        axis={
            "lo": axis_lo,
            "hi": axis_hi,
            "interval": axis_interval,
            "unit": unit,
            "bins": resolved_bins,
            "clipping": clipping.as_dict(),
            # Hoisted out of every series: both grids are identical across all
            # twenty series by construction, and shipping twenty copies of each
            # is most of the payload.
            "curve_x": _round_all(curve_x),
            "hist_centres": _round_all(
                0.5 * (edges_array[:-1] + edges_array[1:])
            ),
        },
        benchmarks=benchmarks,
        n_events=n_events,
        scale=scale,
    )


# ------------------------------------------- B3: slices of incident momentum --

#: The deposits a momentum-sliced two-shower panel draws (``series=``): each
#: shower's deposit split by the true segmentation fraction (the default), by
#: the segmentation network's predicted fraction, or both.
SERIES_TRUTH = "truth"
SERIES_MODEL = "model"
SERIES_ALL = "all"
SERIES_SETS: tuple[str, ...] = (SERIES_TRUTH, SERIES_MODEL, SERIES_ALL)

#: Which of the D panel's four series each set keeps, in the D panel's order.
_SET_KINDS: dict[str, tuple[str, ...]] = {
    SERIES_TRUTH: ("true",),
    SERIES_MODEL: ("pred",),
    SERIES_ALL: ("pred", "true"),
}

#: A single shower has nothing to split its deposit from: one series per slice.
DEPOSIT_SET = "deposit"
DEPOSIT_KEY = "e_dep"
DEPOSIT_LABEL = "Shower - deposit"

#: Headroom above a slice's clipped range, a fraction of its span, as the D
#: panel's axis has; the lower bound is pinned at zero.
_AXIS_PAD = 0.05

CENSORED_AGGREGATE_NOTICE = (
    "This experiment is the producer's event-level aggregate, which leaves out "
    "every single-hit event: its lowest-momentum slices hold fewer showers than "
    "were simulated, and their mean response is biased high, because single-hit "
    "showers deposit the least. The hit-level file of the same run keeps them."
)


@dataclass(frozen=True)
class MomentumSeries:
    """One series of the momentum-sliced panel: whose deposit, from which column."""

    key: str
    label: str
    shower: str
    kind: str        # "true" | "pred" | "deposit"
    column: str      # allowlisted event-table column


def _segmentation_column(stem: str, coord_system: str) -> str:
    """``e_a_true`` -> ``e_a_true_trn``: a per-frame segmentation sum of the event table."""
    if stem not in {name for name, _ in ddl.SEG_STAT_COLUMNS}:
        raise ValueError(f"unknown segmentation sum {stem!r}")
    return f"{stem}_{ddl.frame_code(coord_system)}"


def momentum_series(
    record: ExperimentRecord, choice: str | None = None, coord_system: str = "lab"
) -> tuple[str, tuple[MomentumSeries, ...]]:
    """The series set a request selects, and its series in drawing order.

    Two showers: ``truth`` (the default), ``model`` or ``all``, the
    segmentation sums of ``coord_system``'s frame. One shower: its deposit, the
    only series there is - ``truth`` names the same thing, and the network sets
    are refused naming ``series``, because the experiment carries no network.
    """
    if choice is not None and choice not in SERIES_SETS:
        raise ValidationError(
            f"series must be one of {', '.join(SERIES_SETS)}; got {choice!r}.", field="series"
        )
    if record.kind != ddl.KIND_TWO_SHOWER:
        if choice in (SERIES_MODEL, SERIES_ALL):
            capabilities.require(record, "energy", field="series")
        (shower,) = showers_mod.of(record, "a")
        return DEPOSIT_SET, (
            MomentumSeries(DEPOSIT_KEY, DEPOSIT_LABEL, shower.key, "deposit", shower.deposit),
        )
    chosen = choice or SERIES_TRUTH
    return chosen, tuple(
        MomentumSeries(key, label, shower, kind, _segmentation_column(key, coord_system))
        for key, label, shower, kind in SERIES
        if kind in _SET_KINDS[chosen]
    )


def _calibration_column(
    record: ExperimentRecord, shower: showers_mod.ShowerColumns, coord_system: str
) -> str:
    """The deposit the calibration divides by: the truth split, as the D panel's."""
    if record.kind == ddl.KIND_TWO_SHOWER:
        return _segmentation_column(f"e_{shower.key}_true", coord_system)
    return shower.deposit


@dataclass
class MomentumSample:
    """One selection's per-shower momenta, slice indices and deposits.

    Read once per request: the route's budget guard rebuilds the panel from it
    at coarser samplings without going back to the event table.
    """

    showers: tuple[showers_mod.ShowerColumns, ...]
    series_set: str
    series: tuple[MomentumSeries, ...]
    slicing: momentum_mod.MomentumSlicing
    n_events: int
    #: Per shower key: its slice (``momentum.OUTSIDE`` for none), incident
    #: momentum (GeV), whether it deposited energy, and the calibration deposit.
    slice_index: dict[str, np.ndarray]
    momentum: dict[str, np.ndarray]
    present: dict[str, np.ndarray]
    deposit: dict[str, np.ndarray]
    #: Per series key: the raw deposit the series draws.
    values: dict[str, np.ndarray]
    notices: list[str] = field(default_factory=list)


def _floats(column: Any) -> np.ndarray:
    """A fetched column as float64, NULL as NaN."""
    return np.ma.filled(np.ma.asarray(column, dtype=np.float64), np.nan)


def _slicing(
    con: duckdb.DuckDBPyConnection,
    table: str,
    spec: FilterSpec,
    shower_cols: Sequence[showers_mod.ShowerColumns],
    p_slices: str | None,
    half_width: float,
) -> momentum_mod.MomentumSlicing:
    """Windows from the request, or one class per producer bin the selection holds."""
    if (p_slices or momentum_mod.MODE_NOTEBOOK).strip().lower() != momentum_mod.MODE_BINS:
        return momentum_mod.parse_slicing(p_slices, half_width)
    bounds = ", ".join(f"min({s.momentum_bin}), max({s.momentum_bin})" for s in shower_cols)
    row = con.execute(
        f"SELECT {bounds} FROM {table} WHERE {spec.where_sql()}", spec.params()
    ).fetchone()
    lows = [int(v) for v in row[0::2] if v is not None]
    highs = [int(v) for v in row[1::2] if v is not None]
    if not lows:
        # An empty selection holds no bins, which is not the same as an
        # experiment that records none.
        return momentum_mod.MomentumSlicing(momentum_mod.MODE_BINS, (), None)
    return momentum_mod.parse_slicing(momentum_mod.MODE_BINS, half_width, (min(lows), max(highs)))


def _bin_ranges(
    bins: dict[str, np.ndarray], momenta: dict[str, np.ndarray]
) -> dict[int, tuple[float, float]]:
    """The momentum range each producer bin actually holds, over every shower."""
    ranges: dict[int, tuple[float, float]] = {}
    for key, column in bins.items():
        p = momenta[key]
        for k in np.unique(column[column >= 0]):
            found = p[(column == k) & np.isfinite(p)]
            if not found.size:
                continue
            lo, hi = float(found.min()), float(found.max())
            old = ranges.get(int(k))
            ranges[int(k)] = (lo, hi) if old is None else (min(old[0], lo), max(old[1], hi))
    return ranges


def fetch_momentum(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    p_slices: str | None = None,
    half_width: float = momentum_mod.HALF_WIDTH_GEV,
    series: str | None = None,
    coord_system: str = "lab",
) -> MomentumSample:
    """Read the selection's showers once: momenta, slice indices and deposits.

    Each shower is placed by its own momentum: a window tests the stored value
    against the half-open ``[c - h, c + h)`` in double precision (the notebook's
    rule; the two-shower file stores momenta as REAL), a 1 GeV bin tests the
    producer's integer bin column, so a float32 momentum can never move a
    shower across an integer edge.
    """
    series_set, chosen = momentum_series(record, series, coord_system)
    shower_cols = showers_mod.of(record, "both")
    table = quote(naming.event_table(record.table_name))
    slicing = _slicing(con, table, spec, shower_cols, p_slices, half_width)
    classes = slicing.classes

    select: list[str] = []
    for s in shower_cols:
        p = f"CAST({s.momentum} AS DOUBLE)"
        index = (
            momentum_mod.case_sql(classes, p, s.momentum_bin) if classes
            else str(momentum_mod.OUTSIDE)
        )
        select += [
            f"{index} AS slice_{s.key}",
            f"{p} AS p_{s.key}",
            f"({s.present_sql}) AS present_{s.key}",
            f"{_calibration_column(record, s, coord_system)} AS dep_{s.key}",
        ]
        if slicing.uses_bin_column:
            select.append(f"CAST({s.momentum_bin} AS INTEGER) AS bin_{s.key}")
    select += [f"{m.column} AS v_{m.key}" for m in chosen]
    columns = con.execute(
        f"SELECT {', '.join(select)} FROM {table} WHERE {spec.where_sql()}", spec.params()
    ).fetchnumpy()

    keys = [s.key for s in shower_cols]
    momenta = {k: _floats(columns[f"p_{k}"]) for k in keys}
    notices: list[str] = []
    if slicing.uses_bin_column and classes:
        bins = {
            k: np.ma.filled(np.ma.asarray(columns[f"bin_{k}"], dtype=np.int64), -1)
            for k in keys
        }
        relabelled, notices = momentum_mod.relabel_bins(classes, _bin_ranges(bins, momenta))
        slicing = momentum_mod.MomentumSlicing(slicing.mode, tuple(relabelled), slicing.half_width)
    if record.kind == ddl.KIND_SINGLE_EVENTS:
        notices.append(CENSORED_AGGREGATE_NOTICE)

    return MomentumSample(
        showers=tuple(shower_cols),
        series_set=series_set,
        series=chosen,
        slicing=slicing,
        n_events=int(momenta[keys[0]].size),
        slice_index={
            k: np.ma.filled(np.ma.asarray(columns[f"slice_{k}"], dtype=np.int64),
                            momentum_mod.OUTSIDE)
            for k in keys
        },
        momentum=momenta,
        present={
            k: np.ma.filled(np.ma.asarray(columns[f"present_{k}"], dtype=bool), False)
            for k in keys
        },
        deposit={k: np.nan_to_num(_floats(columns[f"dep_{k}"])) for k in keys},
        values={m.key: np.nan_to_num(_floats(columns[f"v_{m.key}"])) for m in chosen},
        notices=notices,
    )


def _momentum_marker(p: np.ndarray) -> dict[str, Any]:
    """The measured mean incident momentum of a slice's showers, with both spans.

    ``sd`` is the dispersion of the momenta (an uncapped band); ``ci95`` is the
    Student-t 95% interval of their mean (a capped whisker). They differ by
    sqrt(N), and both are named so neither can be drawn as the other.
    """
    finite = p[np.isfinite(p)]
    n = int(finite.size)
    if n == 0:
        return {"mean": None, "sd": None, "n": 0, "ci95": None}
    mean = float(finite.mean())
    if n < gaussian.MIN_MOMENT_SAMPLES:
        return {"mean": sig(mean), "sd": None, "n": n, "ci95": None}
    sd = float(finite.std(ddof=gaussian.DDOF))
    half = gaussian.t_quantile_975(n - 1) * sd / math.sqrt(n)
    return {"mean": sig(mean), "sd": sig(sd), "n": n, "ci95": [sig(mean - half), sig(mean + half)]}


@dataclass
class _SliceAxis:
    """One slice's energy range, and what it was set from."""

    lo: float
    hi: float
    interval: float
    clipping: clip_mod.ClipResult
    provisional: bool
    driven_by: list[str]
    n_values: int
    n_outside: int


def _slice_axis(
    parts: Sequence[tuple[MomentumSeries, np.ndarray]], clip_low: float, clip_high: float
) -> _SliceAxis:
    """A slice's display range from its series that reach the histogram floor.

    A slice with no such series takes its range from the few showers it has,
    and the range is marked provisional. ``n_outside`` counts every value of
    every series in the slice beyond the displayed range - the strip points of
    a thin series included - so the clip is disclosed exactly.
    """
    robust = [(m, v) for m, v in parts if v.size >= histogram.MIN_HISTOGRAM_SAMPLES]
    provisional = not robust
    basis = robust or list(parts)
    clipping = clip_mod.percentile_clip(
        np.concatenate([v for _, v in basis]),
        low=clip_low, high=clip_high, floor_at_zero=True, pad=_AXIS_PAD,
    )
    # fine=True extends the tick ladder below 0.1 for uncalibrated deposits of
    # a few hundredths of a GeV; above a span of 1.2 it equals the default.
    lo, hi, interval = clip_mod.nice_range(clipping.lo, clipping.hi, fine=True)
    everything = np.concatenate([v for _, v in parts])
    return _SliceAxis(
        lo=lo, hi=hi, interval=interval, clipping=clipping, provisional=provisional,
        driven_by=[m.key for m, _ in basis],
        n_values=int(everything.size),
        n_outside=int(((everything < lo) | (everything > hi)).sum()),
    )


def _clipping_dict(clipping: clip_mod.ClipResult) -> dict[str, Any]:
    data = clipping.as_dict()
    for key in ("lo", "hi", "data_min", "data_max"):
        data[key] = sig(data[key])
    data["note"] = typographic(data["note"])
    return data


#: The fit's floats, shipped at six significant figures in the momentum view.
_FIT_FLOATS: tuple[str, ...] = (
    "mu", "sigma", "sigma_population", "mu_core", "sigma_core", "sigma_robust",
    "resolution", "resolution_core", "mu_error", "sigma_error", "resolution_error",
    "sigma_bias_factor", "sigma_unbiased",
)


def _compact(fitted: SeriesFit) -> SeriesFit:
    """One momentum-view series at six significant figures, its sentences typeset.

    The D panel ships its fit block at full precision, and that payload is
    pinned. This view carries up to four series in each of twenty slices, and
    the digits past the sixth are budget, not information. Its sentences get
    U+2212 for every signed number (``+/-2.5 sigma`` reads ``+/−2.5``).
    """
    fit = fitted.fit
    for name in _FIT_FLOATS:
        setattr(fit, name, sig(getattr(fit, name)))
    for name in ("mu_ci95", "sigma_ci95"):
        span = getattr(fit, name)
        if span is not None:
            setattr(fit, name, (sig(span[0]), sig(span[1])))
    fitted.message = typographic(fitted.message)
    fit.estimator_note = typographic(fit.estimator_note)
    fit.note = typographic(fit.note)
    return fitted


def build_by_momentum(
    sample: MomentumSample,
    bins: int | None = None,
    calibrated: bool = True,
    clip_low: float = clip_mod.DEFAULT_LOW_PERCENTILE,
    clip_high: float = clip_mod.DEFAULT_HIGH_PERCENTILE,
    curve_points: int = histogram.CURVE_POINTS,
) -> EnergyDistribution:
    """The momentum-sliced panel of one fetched selection."""
    keys = [s.key for s in sample.showers]

    # --- Calibration: per shower, over the whole selection -------------------
    # Every shower counts, in a slice or not, exactly as the D panel's, so the
    # constants are one selection's and do not move with the slicing.
    c: dict[str, float | None] = {}
    for k in keys:
        deposited = float(sample.deposit[k].sum())
        momentum_sum = float(np.nan_to_num(sample.momentum[k]).sum())
        c[k] = momentum_sum / deposited if deposited > 0 else None
    applied = bool(calibrated and all(c.values()))
    if applied:
        values = {m.key: sample.values[m.key] * c[m.shower] for m in sample.series}
        scale, unit = "calibrated", "GeV (incident-equivalent)"
    else:
        values = dict(sample.values)
        scale, unit = "deposited", "GeV (deposited)"

    # --- Each shower in its own slice ----------------------------------------
    classes = sample.slicing.classes
    members = {
        cls.index: {k: (sample.slice_index[k] == cls.index) & sample.present[k] for k in keys}
        for cls in classes
    }
    parts = {
        cls.index: [
            (m, values[m.key][members[cls.index][m.shower]])
            for m in sample.series
            if members[cls.index][m.shower].any()
        ]
        for cls in classes
    }

    # One bin count for every slice, set by the smallest series whose histogram
    # is drawn, so no histogram on the panel is finer than its own statistics.
    drawn = [
        int(v.size) for slice_parts in parts.values() for _, v in slice_parts
        if v.size >= histogram.MIN_HISTOGRAM_SAMPLES and np.ptp(v) > 0
    ]
    resolved_bins = (
        int(bins) if bins is not None
        else histogram.adaptive_bins(min(drawn) if drawn else 0)
    )

    fitted: list[SeriesFit] = []
    slice_axes: list[dict[str, Any]] = []
    for cls in classes:
        slice_parts = parts[cls.index]
        if not slice_parts:
            continue
        axis = _slice_axis(slice_parts, clip_low, clip_high)
        edges_array = histogram.axis_edges(axis.lo, axis.hi, resolved_bins)
        curve_x = histogram.curve_axis(axis.lo, axis.hi, curve_points)
        for m, sample_values in slice_parts:
            fitted.append(_compact(_build_series(
                m.key, m.label, m.shower, m.kind, cls.index, cls.label,
                sample_values, edges_array, curve_x,
            )))
        marker: dict[str, Any] = {"a": None, "b": None}
        for k in keys:
            marker[k] = _momentum_marker(sample.momentum[k][members[cls.index][k]])
        slice_axes.append({
            "slice": cls.index,
            "lo": axis.lo,
            "hi": axis.hi,
            "interval": axis.interval,
            "provisional": axis.provisional,
            "driven_by": axis.driven_by,
            "n_values": axis.n_values,
            "n_outside_axis": axis.n_outside,
            "clipping": _clipping_dict(axis.clipping),
            "curve_x": sig_list(curve_x),
            "hist_centres": sig_list(0.5 * (edges_array[:-1] + edges_array[1:])),
            "momentum": marker,
        })

    by_shower = {
        k: {str(cls.index): int(members[cls.index][k].sum()) for cls in classes} for k in keys
    }

    def per_shower(counts: dict[str, Any]) -> dict[str, Any]:
        return {"a": counts.get("a"), "b": counts.get("b")}

    return EnergyDistribution(
        slices=list(classes),
        slice_counts={
            cls.index: sum(int(members[cls.index][k].sum()) for k in keys) for cls in classes
        },
        series=fitted,
        calibration={
            "c_a": c.get("a"),
            "c_b": c.get("b"),
            "sampling_fraction_a": (1.0 / c["a"]) if c.get("a") else None,
            "sampling_fraction_b": (1.0 / c["b"]) if c.get("b") else None,
            "applied": applied,
            "method": (
                "c = sum(incoming_momentum) / sum(deposited energy"
                + (" attributed by ground truth" if "b" in keys else "")
                + "), fitted per shower over the whole active selection, every shower "
                "included whether or not its momentum falls in a slice"
            ),
        },
        axis={
            "unit": unit,
            "bins": resolved_bins,
            "per_slice": True,
            "curve_points": int(curve_points),
        },
        benchmarks=[],
        n_events=sample.n_events,
        scale=scale,
        momentum={
            "slice_by": "momentum",
            "slicing": sample.slicing.as_dict(),
            "slice_axes": slice_axes,
            "slice_counts_by_shower": per_shower(by_shower),
            "outside_slices": per_shower({
                k: int(((sample.slice_index[k] == momentum_mod.OUTSIDE) & sample.present[k]).sum())
                for k in keys
            }),
            "counted": "showers",
            "series_set": sample.series_set,
            "no_deposit": per_shower({k: int((~sample.present[k]).sum()) for k in keys}),
        },
        notices=list(sample.notices),
    )


def compute_by_momentum(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    p_slices: str | None = None,
    *,
    half_width: float = momentum_mod.HALF_WIDTH_GEV,
    series: str | None = None,
    bins: int | None = None,
    calibrated: bool = True,
    clip_low: float = clip_mod.DEFAULT_LOW_PERCENTILE,
    clip_high: float = clip_mod.DEFAULT_HIGH_PERCENTILE,
    coord_system: str = "lab",
    curve_points: int = histogram.CURVE_POINTS,
) -> EnergyDistribution:
    """The reconstructed-energy panel sliced by each shower's incident momentum (B3).

    ``p_slices`` is ``notebook`` (the default windows), ``bins`` or
    comma-separated window centres in GeV; ``series`` picks the two-shower
    deposits (``truth`` by default). The selection is read once.
    """
    sample = fetch_momentum(
        con, record, spec, p_slices=p_slices, half_width=half_width,
        series=series, coord_system=coord_system,
    )
    return build_by_momentum(
        sample, bins=bins, calibrated=calibrated,
        clip_low=clip_low, clip_high=clip_high, curve_points=curve_points,
    )
