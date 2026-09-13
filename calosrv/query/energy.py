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
   core refit (see ``stats/gaussian.py``).

6. **Reference benchmarks.** Dashed isolated-shower curves at the mean true E1
   and E2 of the selection, so the overlap-degraded reconstructions can be read
   against the single-particle case.
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


#: Most individual event energies shipped for a rug strip. A slice below the
#: density threshold holds at most 14 events, so this is only a guard against a
#: future threshold change making the payload unbounded.
MAX_RUG_POINTS = 200

#: Shown in place of the density curve when a slice is too small to estimate one.
INSUFFICIENT_MESSAGE = (
    "Insufficient sample size (N < {threshold}) for continuous density "
    "estimation; plotting individual event points."
)


@dataclass
class SeriesFit:
    key: str
    label: str
    shower: str
    kind: str
    slice_index: int
    fit: gaussian.GaussianFit
    hist: histogram.Histogram | None
    curve_x: list[float] = field(default_factory=list)
    curve_y: list[float] = field(default_factory=list)
    #: Individual reconstructed energies, populated *instead of* the histogram
    #: when the slice is too small for a density estimate.
    rug: list[float] = field(default_factory=list)

    @property
    def sparse(self) -> bool:
        return self.hist is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "shower": self.shower,
            "kind": self.kind,
            "slice": self.slice_index,
            "fit": self.fit.as_dict(),
            "histogram": self.hist.as_dict() if self.hist else None,
            "curve": {"x": self.curve_x, "y": self.curve_y},
            "rug": self.rug,
            "sparse": self.sparse,
            "message": (
                INSUFFICIENT_MESSAGE.format(threshold=gaussian.MIN_SAMPLES)
                if self.sparse else ""
            ),
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
    #: Event count below which continuous density estimation is suppressed.
    density_threshold: int = gaussian.MIN_SAMPLES

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
            "density_threshold": self.density_threshold,
        }


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
            e_a_pred, e_b_pred, e_a_true, e_b_true,
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
    # count is set by the *smallest* slice that will actually be drawn, so no
    # histogram on the panel is finer than its own statistics support - a slice
    # of twenty events binned for twenty thousand is the spike comb again.
    drawn = [
        n for index, n in slice_counts.items() if n >= gaussian.MIN_SAMPLES
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
            sample = values[key][mask]
            fit = gaussian.fit_gaussian(sample, label=f"{label}, {s.label}")

            if fit.insufficient:
                # Below the threshold a density histogram is not a distribution,
                # it is a comb of spikes whose heights are set by the bin width
                # rather than by physics. Ship the events themselves instead.
                finite = sample[np.isfinite(sample)]
                fitted.append(
                    SeriesFit(
                        key=key, label=label, shower=shower, kind=kind,
                        slice_index=s.index, fit=fit, hist=None,
                        rug=[float(v) for v in np.sort(finite)[:MAX_RUG_POINTS]],
                    )
                )
                continue

            hist = histogram.density_histogram(sample, edges_array)

            curve_y: list[float] = []
            if fit.mu_core is not None and fit.sigma_core:
                curve_y = [
                    float(v)
                    for v in gaussian.gaussian_curve(
                        curve_x, fit.mu_core, fit.sigma_core
                    )
                ]

            fitted.append(
                SeriesFit(
                    key=key, label=label, shower=shower, kind=kind,
                    slice_index=s.index, fit=fit, hist=hist,
                    curve_x=[float(v) for v in curve_x] if curve_y else [],
                    curve_y=curve_y,
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
                    "mu": mu,
                    "sigma": sigma,
                    "resolution": ISOLATED_RESOLUTION,
                    "x": [float(v) for v in curve_x],
                    "y": [
                        float(v)
                        for v in gaussian.gaussian_curve(curve_x, mu, sigma)
                    ],
                    "note": (
                        "Reference width is a stated single-shower resolution of "
                        f"{100 * ISOLATED_RESOLUTION:.0f}%, not a fit: this "
                        "dataset contains no isolated single-particle events."
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
        },
        density_threshold=gaussian.MIN_SAMPLES,
        benchmarks=benchmarks,
        n_events=n_events,
        scale=scale,
    )
