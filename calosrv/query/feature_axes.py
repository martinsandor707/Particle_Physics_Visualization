"""The feature explorer's axis plans: scale, lattice quantum, snapped edges and the comb verdict.

The histogram views (``feature_hist.py``) share one binning across the classes
of a request. This module decides it: the automatic linear or log scale from
the measured values, the lattice quantum where a feature's values are
quantised, the snapped edges aligned to it, the robust display range, and the
lag-1 comb statistic of the pooled counts judged against counting noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from ..encode.numbers import sig, sig_list
from ..errors import ValidationError
from ..stats import clip as clip_mod
from ..stats import histogram
from ..text import typographic
from . import features_catalog as catalog
from . import stagger
from .features_catalog import Feature

#: Lag-1 autocorrelation that pure counting noise gives after the 9-bin
#: moving-average detrend of ``stagger.profile_lag1``: −10/72, derived for
#: independent counts (cov −10/81 σ² over var 72/81 σ²). The project's comb
#: threshold (−0.10) was set on occupancy profiles; on a count histogram the
#: noise alone sits below it, so the verdict here is taken against this.
NOISE_LAG1 = -10.0 / 72.0

# ------------------------------------------------------------ axis plans --


@dataclass
class AxisPlan:
    """One shared axis of a histogram view, in display coordinates (log10 on a log axis)."""

    feature: Feature
    coord_system: str
    scale: str                      # "linear" | "log" | "circular"
    edges: np.ndarray
    provisional: bool
    clipping: clip_mod.ClipResult
    quantum: dict[str, Any] | None
    decades: float | None
    interval: float | None
    notes: list[str]

    @property
    def lo(self) -> float:
        return float(self.edges[0])

    @property
    def hi(self) -> float:
        return float(self.edges[-1])

    @property
    def bins(self) -> int:
        return int(self.edges.size - 1)

    @property
    def width(self) -> float:
        return (self.hi - self.lo) / self.bins

    def as_dict(self) -> dict[str, Any]:
        log10 = self.scale == "log"
        rule = {
            "circular": "the full period (−π, π], equal-width bins",
            "log": ("equal-width bins in log10 of the value; the edges, strips, pairs and "
                    "curve positions are log10 values too"),
            "linear": "equal-width bins",
        }[self.scale]
        if self.quantum and self.quantum.get("snapped"):
            per_bin = self.quantum["per_bin"]
            rule += (f", each {per_bin} quantum{'' if per_bin == 1 else 's'} "
                     f"({per_bin * self.quantum['value']:g} {self.quantum['unit']}) wide, "
                     "edges half a quantum off the lattice values")
        clipping = self.clipping.as_dict()
        for key in ("lo", "hi", "data_min", "data_max"):
            clipping[key] = sig(clipping[key])
        return {
            "feature": self.feature.id,
            "label": catalog.label(self.feature, self.coord_system),
            "unit": self.feature.unit,
            "scale": self.scale,
            "lo": sig(self.lo),
            "hi": sig(self.hi),
            "bins": self.bins,
            "edges": sig_list(self.edges),
            "edges_rule": typographic(rule),
            "clipping": clipping,
            "provisional": self.provisional,
            "log10": log10,
            "quantum_mm": (self.quantum["value"] if self.quantum and self.quantum["unit"] == "mm"
                           and self.quantum.get("verified") else None),
            "quantum": self.quantum,
            "offset": catalog.display_offset(self.feature, self.coord_system),
            "decades": sig(self.decades, 3) if self.decades is not None else None,
            "interval": sig(self.interval) if self.interval is not None else None,
            "notes": [typographic(t) for t in self.notes],
        }


def _decades(values: np.ndarray) -> float | None:
    """log10(p99 / p1) of the positive values; ``None`` with too few to say."""
    v = values[np.isfinite(values) & (values > 0)]
    if v.size < 2:
        return None
    p1, p99 = np.percentile(v, (clip_mod.DEFAULT_LOW_PERCENTILE, clip_mod.DEFAULT_HIGH_PERCENTILE))
    return float(math.log10(p99 / p1)) if p1 > 0 and p99 > 0 else None


def resolve_scale(feature: Feature, coord_system: str, requested: str,
                  pooled: np.ndarray, field_name: str) -> tuple[str, float | None]:
    """``(scale, decades)``: ``auto`` picks log for a positive, unquantised feature
    spanning a decade or more over the classes that set the range."""
    if requested not in ("auto", "linear", "log"):
        raise ValidationError(f"{field_name} must be one of auto, linear, log; got {requested!r}.",
                              field=field_name)
    if feature.circular:
        if requested == "log":
            raise ValidationError(
                f"{feature.id} is an azimuth: it has no log axis and is drawn on its full "
                "period (−π, π].", field=field_name)
        return "circular", None
    quantum = feature.quantised_in(coord_system)
    if quantum and requested == "log":
        what = ("whole numbers of sampling layers" if quantum == catalog.QUANTUM_LAYER
                else "integers")
        raise ValidationError(typographic(
            f"{feature.id} takes {what}: log-spaced bins cannot be aligned with that quantum "
            "and would comb against it. Use scale=linear."), field=field_name)
    decades = _decades(pooled) if feature.positive else None
    if requested == "log":
        return "log", decades
    if requested == "linear" or quantum or not feature.positive:
        return "linear", decades
    return ("log" if decades is not None and decades >= 1.0 else "linear"), decades


def to_axis(values: np.ndarray, scale: str) -> tuple[np.ndarray, int]:
    """``(finite display values, n non-positive dropped)`` on ``scale``."""
    v = values[np.isfinite(values)]
    if scale != "log":
        return v, 0
    positive = v > 0
    return np.log10(v[positive]), int((~positive).sum())


#: Tolerance of the measured lattice step, and the smallest step taken as a lattice (mm).
_STEP_TOLERANCE_MM = 1e-3
_MIN_STEP_MM = 1.0


def measured_step(values: np.ndarray) -> float | None:
    """The lattice step the distinct values sit on: their greatest common divisor.

    Euclid's algorithm on reals with a tolerance, over the gaps between sorted
    distinct values - so 102.5, 553.5 and 861 mm give 20.5 mm, where the
    smallest gap (307.5 mm) would not. ``None`` with fewer than two distinct
    values, or when the values share no step of at least a millimetre.
    """
    unique = np.unique(np.round(values[np.isfinite(values)], 6))
    step = 0.0
    for gap in np.diff(unique):
        a, b = max(step, float(gap)), min(step, float(gap))
        while b > _STEP_TOLERANCE_MM:
            a, b = b, math.fmod(a, b)
            if a - b < _STEP_TOLERANCE_MM:      # a remainder just under a whole step
                b = 0.0
        step = a
        if step < _MIN_STEP_MM:
            return None
    return step if step >= _MIN_STEP_MM else None


def lattice_quantum(feature: Feature, coord_system: str, values: np.ndarray,
                    pitch: float | None) -> dict[str, Any] | None:
    """The quantum a quantised feature's values sit on, verified against the values.

    Layer features take the experiment's layer pitch, or the common step of
    the distinct values when it records none (the aggregate has no lattice).
    The anchor is a value of the data, so an offset depth keeps its lattice
    phase. ``None`` when there is no lattice to beat against.
    """
    kind = feature.quantised_in(coord_system)
    if kind is None:
        return None
    v = values[np.isfinite(values)]
    if kind == catalog.QUANTUM_COUNT:
        q, unit, source = 1.0, "hits", "an integer count"
    else:
        floor = catalog.display_offset(feature, coord_system) or 0.0
        v = v[np.abs(v - floor) > 2 * catalog.EPS]   # floored values: zero extent
        q = pitch if pitch else measured_step(v)
        unit = "mm"
        source = ("the layer pitch" if pitch
                  else "the common step of the distinct values (measured: no lattice is recorded)")
    if q is None or not q > 0 or v.size == 0:
        return None     # one distinct value or none: no lattice to beat against
    anchor = float(v[0])
    steps = (v - anchor) / q
    verified = bool(np.all(np.abs(steps - np.round(steps)) <= 1e-3))
    return {"value": sig(q), "unit": unit, "source": source, "verified": verified,
            "snapped": False, "anchor": sig(anchor), "per_bin": None}


def snapped_edges(lo: float, hi: float, bins: int, q: float,
                   anchor: float) -> tuple[np.ndarray, int]:
    """Edges half a quantum off the lattice, each bin a whole number of quanta wide."""
    per_bin = max(1, math.ceil((hi - lo) / bins / q - 1e-9))
    width = per_bin * q
    first = anchor + (math.floor((lo - anchor) / q - 0.5 + 1e-9) + 0.5) * q
    n = max(1, math.ceil((hi - first) / width - 1e-9))
    return first + width * np.arange(n + 1, dtype=np.float64), per_bin


def plan_axis(feature: Feature, coord_system: str, per_class: Sequence[np.ndarray],
              scale: str, decades: float | None, bins_for: Any, pitch: float | None,
              raw_pooled: np.ndarray,
              range_per_class: Sequence[np.ndarray] | None = None) -> AxisPlan:
    """The shared axis of every class: range from the drawn classes, bins, quantum.

    ``per_class`` are the classes' values already on the axis (log10 on a log
    axis); ``bins_for(drawn sizes)`` is the view's bin rule. ``range_per_class``,
    when given, are the values of each class that may set the range - its
    measurements, without the floored values (CLAUDE.md section 2: display
    ranges follow robust evidence) - while the disclosure still counts every
    drawn value outside the range.
    """
    sizes = [int(v.size) for v in per_class]
    drawn_idx = [i for i, n in enumerate(sizes) if n >= histogram.MIN_HISTOGRAM_SAMPLES]
    provisional = not drawn_idx
    pooled = np.concatenate([per_class[i] for i in drawn_idx] or list(per_class)
                            or [np.empty(0)])
    if range_per_class is None:
        ranged = pooled
    else:
        ranged = np.concatenate([range_per_class[i] for i in drawn_idx] or list(range_per_class)
                                or [np.empty(0)])
        if ranged.size == 0:
            ranged = pooled     # every drawn value is floored: nothing else to range on
    notes: list[str] = []
    interval: float | None = None
    if scale == "circular":
        lo, hi = -math.pi, math.pi
        clipping = clip_mod.ClipResult(lo=lo, hi=hi, low_percentile=0.0, high_percentile=100.0,
                                       n_total=int(pooled.size), n_below=0, n_above=0,
                                       applied=False)
        notes.append("An azimuth is drawn on its full period (−π, π], cut at ±π, with no "
                     "percentile clip: a crop would invent an end where the values wrap.")
    else:
        clip = clip_mod.percentile_clip(ranged)
        lo, hi, interval = clip_mod.nice_range(clip.lo, clip.hi, fine=True)
        clipping = clip
    bins = int(bins_for([n for n in sizes if n >= histogram.MIN_HISTOGRAM_SAMPLES]))
    quantum = None
    edges = np.linspace(lo, hi, bins + 1, dtype=np.float64)
    if scale == "linear":
        quantum = lattice_quantum(feature, coord_system, raw_pooled, pitch)
        if quantum and quantum["verified"]:
            edges, per_bin = snapped_edges(lo, hi, bins, float(quantum["value"]),
                                            float(quantum["anchor"]))
            quantum.update(snapped=True, per_bin=per_bin)
        elif quantum:
            notes.append(f"{feature.id} should sit on a lattice of {quantum['value']} "
                         f"{quantum['unit']} but its values do not: bins are not aligned.")
    if scale != "circular":
        # The disclosure counts every drawn value outside the range actually
        # drawn - floored ones included - against the extremes of all of them.
        a, b = float(edges[0]), float(edges[-1])
        below, above = int((pooled < a).sum()), int((pooled > b).sum())
        clipping = clip_mod.ClipResult(
            lo=a, hi=b, low_percentile=clipping.low_percentile,
            high_percentile=clipping.high_percentile, n_total=int(pooled.size),
            n_below=below, n_above=above,
            data_min=float(pooled.min()) if pooled.size else None,
            data_max=float(pooled.max()) if pooled.size else None,
            applied=clipping.applied or below + above > 0)
    if provisional:
        notes.append(f"No class reaches N = {histogram.MIN_HISTOGRAM_SAMPLES}: the range is "
                     "taken from the under-powered classes and is provisional.")
    return AxisPlan(feature, coord_system, scale, edges, provisional, clipping, quantum,
                    decades, interval, notes)


#: What a comb in a feature's histogram can be blamed on, by its relation to a lattice.
COMB_CAUSES: dict[str, str] = {
    "lattice": ("its bins beat against values the detector lattice quantises, which is "
                "segmentation, not shower structure."),
    "integer": ("its bins beat against the integer values of the count, which is binning, not "
                "shower structure."),
}


def comb_cause(feature: Feature, coord_system: str) -> str | None:
    """``lattice``, ``integer`` or ``None``: what a measured comb of ``feature`` can be blamed on."""
    quantum = feature.quantised_in(coord_system)
    if feature.irregular_lattice or quantum == catalog.QUANTUM_LAYER:
        return "lattice"
    if quantum == catalog.QUANTUM_COUNT:
        return "integer"
    return None


def measure_comb(counts: np.ndarray, cause: str | None = None) -> dict[str, Any]:
    """The lag-1 comb statistic of pooled counts, judged against counting noise.

    ``cause`` (:func:`comb_cause`) names what a comb is blamed on; a feature with
    no lattice or integer relation gets the statistic stated neutrally, since
    noise alone crosses the two-standard-error threshold about 2% of the time.
    """
    bins = int(counts.size)
    minimum = 3 * stagger.DETREND_WINDOW
    if bins < minimum:
        return {"lag1": None, "bins": bins, "combed": None, "noise_reference": sig(NOISE_LAG1),
                "threshold": None, "measured_on": "pooled counts of the drawn classes",
                "cause": cause,
                "note": f"Fewer than {minimum} bins: too short to measure a comb."}
    lag1 = stagger.profile_lag1(counts.astype(np.float64))
    pairs = bins - 2 * (stagger.DETREND_WINDOW // 2) - 1
    threshold = NOISE_LAG1 - 2.0 / math.sqrt(pairs)
    combed = lag1 is not None and lag1 < threshold
    note = (f"Lag-1 autocorrelation of the detrended pooled counts {lag1:.2f}; counting noise "
            f"alone gives {NOISE_LAG1:.2f}, and a comb is called below {threshold:.2f} (two "
            "standard errors lower)." if lag1 is not None else "No variation to measure.")
    if combed and cause in COMB_CAUSES:
        note += f" The histogram combs: {COMB_CAUSES[cause]}"
    elif combed:
        note += (" The counts alternate beyond counting noise. This feature has no lattice or "
                 "integer relation, so nothing is blamed on segmentation; noise alone crosses "
                 "this threshold about 2% of the time.")
    return {"lag1": sig(lag1, 3), "bins": bins, "combed": combed,
            "noise_reference": sig(NOISE_LAG1, 3), "threshold": sig(threshold, 3),
            "measured_on": "pooled counts of the drawn classes", "cause": cause,
            "note": typographic(note)}
