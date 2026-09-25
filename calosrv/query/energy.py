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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..stats import clip as clip_mod
from ..stats import gaussian, histogram
from ..stats.slices import Slice, build_slices, case_sql
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
    slices: list[Slice]
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

    def as_dict(self) -> dict[str, Any]:
        return {
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


def _fetch(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    slices: Sequence[Slice],
) -> dict[str, np.ndarray]:
    """Per-event energies, slice assignment and truth momenta for the selection."""
    table = quote(naming.event_table(record.table_name))
    return con.execute(
        f"""
        SELECT
            {case_sql(slices)}          AS slice_index,
            e_a_pred_abs AS e_a_pred, e_b_pred_abs AS e_b_pred,
            e_a_true_abs AS e_a_true, e_b_true_abs AS e_b_true,
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
) -> EnergyDistribution:
    """Build the reconstructed-energy distribution for the active selection."""
    slices = build_slices(edges) if edges else build_slices()
    columns = _fetch(con, record, spec, slices)

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
    curve_x = histogram.curve_axis(axis_lo, axis_hi)
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
                        "GeV^-1 and would take the density axis away from the "
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
