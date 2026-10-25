"""The feature explorer's numbers (D2-D5): one cached per-event bundle, its classes, four views.

A request names a frame and a shower. The bundle holds every offered feature
of that shower in that frame for the selected events - one read of the event
table, no hit scan - cached in the ``physics`` cache under the clamped
selection. Everything a view varies (class set, feature, scale, the eps
exclusion) is a NumPy step over the cached arrays.

Showers with fewer than two hits are left out on every kind, as the
producer's aggregate leaves them out: their SDs do not exist, and the two
kinds then describe the same events.

The rules each view follows (CLAUDE.md section 2 throughout):

* **D2 describe** - pandas' describe() per class with both SD forms (ddof 1
  and 0), the mean's Student-t interval and the SD's χ² interval beside them;
  an azimuth gets the circular summary instead of a linear mean.
* **D3 correlations** - Pearson r per class with its Fisher-z 95% interval,
  N = events, each event one independent observation. Floored volume factors
  are left out only of the pairs whose values they corrupt.
* **D4 histograms** - integer counts on edges every class shares: the Rice
  count of the smallest drawn class, aligned to the lattice quantum where the
  values are quantised. A KDE from N ≥ 8, the histogram from N ≥ 15, the
  events themselves below.
* **D5 2-D histograms** - dense integer counts against the deposited energy,
  the pairs themselves below N = 15.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming, schemas
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..errors import ValidationError
from ..stats import circular, gaussian, histogram, kde, momentum
from ..stats import clip as clip_mod
from ..stats import describe as describe_mod
from ..stats.metrics import METHOD_FISHER, fisher_z_interval
from ..text import typographic
from . import features_catalog as catalog
from . import physics_cache, showers, stagger
from .features_catalog import Feature
from .filters import FilterSpec

#: Bumped whenever the bundle's contents change, so stale cache entries miss.
FEATURE_VERSION = 1

#: Fewest hits a shower needs: core.py's SDs need two, and the producer's
#: aggregate drops single-hit events.
MIN_HITS = 2

#: Fewest events a Fisher-z interval needs (SE = 1/√(N − 3)); below it no r is quoted.
MIN_FISHER = 4

#: The class sets, and the corr view's whole-class-set choice.
CLASS_MODES: tuple[str, ...] = ("windows", "bins", "label")
POOLED = "pooled"

#: The events drawn individually below the histogram floor: at most 14.
MAX_STRIP = histogram.MIN_HISTOGRAM_SAMPLES - 1

#: Bins per axis of the 2-D histograms: 48 for a few classes, 32 for many.
HIST2D_BINS = 48
HIST2D_BINS_MANY = 32
HIST2D_MANY_CLASSES = 6

#: The 2-D histograms' y feature: the notebook plots every feature against it.
HIST2D_Y = "total_hit_energy"

SILVERMAN_RULE = "Silverman: h = 0.9 · min(SD, IQR/1.349) · N^(−1/5), Gaussian kernel"

#: Lag-1 autocorrelation that pure counting noise gives after the 9-bin
#: moving-average detrend of ``stagger.profile_lag1``: −10/72, derived for
#: independent counts (cov −10/81 σ² over var 72/81 σ²). The project's comb
#: threshold (−0.10) was set on occupancy profiles; on a count histogram the
#: noise alone sits below it, so the verdict here is taken against this.
NOISE_LAG1 = -10.0 / 72.0

THRESHOLDS = {
    "moment": gaussian.MIN_MOMENT_SAMPLES,
    "curve": kde.MIN_KDE_SAMPLES,
    "histogram": histogram.MIN_HISTOGRAM_SAMPLES,
    "robust": gaussian.MIN_ROBUST_SAMPLES,
    "fisher": MIN_FISHER,
}


# ----------------------------------------------------------------- bundle --


@dataclass
class FeatureBundle:
    """Every offered feature of one shower in one frame, per selected event."""

    table_name: str
    kind: str
    coord_system: str
    shower: str
    event_number: np.ndarray       # int64
    p: np.ndarray                  # incident momentum, GeV
    bin: np.ndarray                # the producer's momentum bin, -1 where NULL
    label: np.ndarray | None       # the aggregate's stored label, -1 where NULL
    values: dict[str, np.ndarray]  # feature id -> stored value (raw z, no offset)
    n_selected: int                # showers in the selection with at least one hit
    n_excluded_single_hit: int
    query_ms: float = 0.0

    @property
    def n(self) -> int:
        return int(self.p.size)

    def floored(self, feature_id: str) -> np.ndarray:
        """Events whose ``feature_id`` (width, height, depth, depth range) sits at the floor."""
        with np.errstate(invalid="ignore"):
            return self.values[feature_id] <= catalog.EPS * (1.0 + 1e-9)

    def volume_floored(self) -> np.ndarray:
        """Events with a floored factor of the volume (width, height or depth)."""
        out = np.zeros(self.n, dtype=bool)
        for name in catalog.VOLUME_FACTORS:
            out |= self.floored(name)
        return out

    def eps_mask(self, feature: Feature) -> np.ndarray | None:
        """Events whose value of ``feature`` involves a floor; ``None`` if it cannot."""
        if feature.eps == catalog.EPS_OWN:
            return self.floored(feature.id)
        if feature.eps == catalog.EPS_VOLUME:
            return self.volume_floored()
        return None

    def display(self, feature: Feature) -> np.ndarray:
        """The values as shown: the D1 depth offset applied, nothing else."""
        offset = catalog.display_offset(feature, self.coord_system)
        values = self.values[feature.id]
        return values + offset if offset is not None else values


def _floats(arrays: dict[str, Any], name: str) -> np.ndarray:
    masked = np.ma.asarray(arrays[name]).astype(np.float64)
    return np.asarray(np.ma.filled(masked, np.nan), dtype=np.float64)


def _ints(arrays: dict[str, Any], name: str) -> np.ndarray:
    masked = np.ma.asarray(arrays[name])
    if masked.dtype.kind not in "iu":
        filled = np.ma.filled(masked.astype(np.float64), np.nan)
        return np.where(np.isfinite(filled), filled, -1).astype(np.int64)
    return np.asarray(np.ma.filled(masked.astype(np.int64), -1), dtype=np.int64)


def _fetch(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
           coord_system: str, shower: str) -> FeatureBundle:
    start = time.perf_counter()
    kind = record.kind
    (s,) = showers.of(record, shower)
    hits = catalog.hits_sql(kind, s)
    stored_label = catalog.label_sql(kind)
    label_sql = f"CAST({stored_label} AS INTEGER)" if stored_label else "CAST(NULL AS INTEGER)"
    columns = catalog.select_list(kind, coord_system, s)
    select = ",\n               ".join(f"{sql} AS v_{fid}" for fid, sql in columns)
    table = quote(naming.event_table(record.table_name))
    arrays = con.execute(
        f"""SELECT event_number,
               CAST({s.momentum} AS DOUBLE) AS p,
               CAST({s.momentum_bin} AS INTEGER) AS bin,
               {label_sql} AS label,
               CAST({hits} AS BIGINT) AS n_hits,
               {select}
            FROM {table}
            WHERE {spec.where_sql()} AND {hits} >= 1
            ORDER BY event_number""",
        spec.params(),
    ).fetchnumpy()

    n_hits = _ints(arrays, "n_hits")
    keep = n_hits >= MIN_HITS
    values: dict[str, np.ndarray] = {}
    for fid, _ in columns:
        v = _floats(arrays, f"v_{fid}")[keep]
        if catalog.BY_ID[fid].circular:
            # (-π, π]: atan2 can return -π, which is the same direction as π.
            v = np.where(np.isfinite(v), circular.wrap_angle(v), v)
        values[fid] = v
    return FeatureBundle(
        table_name=record.table_name, kind=kind, coord_system=coord_system, shower=shower,
        event_number=_ints(arrays, "event_number")[keep],
        p=_floats(arrays, "p")[keep],
        bin=_ints(arrays, "bin")[keep],
        label=_ints(arrays, "label")[keep] if stored_label else None,
        values=values,
        n_selected=int(n_hits.size),
        n_excluded_single_hit=int((~keep).sum()),
        query_ms=(time.perf_counter() - start) * 1000.0,
    )


def bundle_for(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
               coord_system: str, shower: str) -> tuple[FeatureBundle, bool]:
    """``(bundle, was_cached)``: one event-table read per selection, frame and shower."""
    key = (*spec.clamped(record).cache_key(), "features", coord_system, shower,
           MIN_HITS, FEATURE_VERSION)
    return physics_cache.get_or_compute(
        key, lambda: _fetch(con, record, spec, coord_system, shower), heavy=False)


def dataset_bin_range(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                      shower: str) -> tuple[int, int] | None:
    """The momentum-bin column's range over the whole experiment, so a bin's class
    index never moves when the selection changes."""
    def compute() -> tuple[int, int] | None:
        (s,) = showers.of(record, shower)
        hits = catalog.hits_sql(record.kind, s)
        table = quote(naming.event_table(record.table_name))
        bin_sql = f"CAST({s.momentum_bin} AS INTEGER)"
        lo, hi = con.execute(
            f"SELECT min({bin_sql}), max({bin_sql}) FROM {table} WHERE {hits} >= {MIN_HITS}"
        ).fetchone()
        return None if lo is None else (int(lo), int(hi))

    key = (record.table_name, "features-bin-range", shower, MIN_HITS, FEATURE_VERSION)
    value, _ = physics_cache.get_or_compute(key, compute, heavy=False)
    return value


# ---------------------------------------------------------------- classes --


@dataclass
class ClassSet:
    """The momentum classes of one request, and each event's class."""

    mode: str
    classes: list[momentum.MomentumClass]
    index: np.ndarray          # per bundle row; momentum.OUTSIDE in no class
    basis: str
    notices: list[str] = field(default_factory=list)

    def mask(self, which: int | str) -> np.ndarray:
        if which == POOLED:
            return self.index != momentum.OUTSIDE
        return self.index == int(which)

    def size(self, which: int | str) -> int:
        return int(self.mask(which).sum())

    @property
    def n_outside(self) -> int:
        return int((self.index == momentum.OUTSIDE).sum())

    def label_of(self, which: int | str) -> str:
        if which == POOLED:
            return "all classes pooled"
        return next(c.label for c in self.classes if c.index == int(which))

    def as_list(self) -> list[dict[str, Any]]:
        return [{"index": c.index, "label": c.label, "lo": c.lo, "hi": c.hi,
                 "n": self.size(c.index), "kind": c.kind, "centre": c.centre}
                for c in self.classes]


def _label_classes(bundle: FeatureBundle) -> ClassSet:
    classes = momentum.binary_label(momentum.LABEL_THRESHOLD_GEV)
    if bundle.label is None:
        return ClassSet("label", classes, momentum.assign(bundle.p, classes),
                        "incident momentum p, split at 2 GeV")
    stored = bundle.label
    index = np.full(bundle.n, momentum.OUTSIDE, dtype=np.int16)
    index[stored == 0] = 0
    index[stored == 1] = 1
    notices = []
    known = (stored == 0) | (stored == 1)
    disagree = int((known & ((stored == 1) != (bundle.p >= momentum.LABEL_THRESHOLD_GEV))).sum())
    if disagree:
        notices.append(f"{disagree:,} events' stored label disagrees with p ≥ 2 GeV; the classes "
                       "follow the stored label.")
    if int((~known).sum()):
        notices.append(f"{int((~known).sum()):,} events carry a label other than 0 or 1 and "
                       "are in no class.")
    return ClassSet("label", classes, index,
                    "the aggregate's stored label energy_class = 1{p ≥ 2 GeV}", notices)


def class_set(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
              bundle: FeatureBundle, mode: str) -> ClassSet:
    """The ``windows``, ``bins`` or ``label`` classes of the bundle's events."""
    if mode == "windows":
        classes = momentum.windows(momentum.FEATURE_CENTRES_GEV, momentum.HALF_WIDTH_GEV,
                                   field="classes")
        return ClassSet("windows", classes, momentum.assign(bundle.p, classes),
                        "incident momentum p")
    if mode == "label":
        return _label_classes(bundle)
    if mode != "bins":
        raise ValidationError(f"classes must be one of {', '.join(CLASS_MODES)}; got {mode!r}.",
                              field="classes")
    span = dataset_bin_range(con, record, bundle.shower)
    try:
        classes = momentum.unit_bins(*span) if span is not None else []
    except ValidationError as exc:
        raise ValidationError(exc.detail, field="classes") from None
    index = momentum.assign(bundle.p, classes, bins=bundle.bin)
    ranges = {}
    for k in np.unique(bundle.bin[bundle.bin >= 0]):
        p = bundle.p[(bundle.bin == k) & np.isfinite(bundle.p)]
        if p.size:
            ranges[int(k)] = (float(p.min()), float(p.max()))
    classes, notices = momentum.relabel_bins(classes, ranges)
    return ClassSet("bins", classes, index, "the producer's integer momentum-bin column", notices)


def parse_class_index(raw: str | None, cs: ClassSet, required: bool) -> int | str:
    """``class_index``: a class index or ``pooled``; required with ``classes=bins``."""
    if raw is None or raw == "":
        if required:
            raise ValidationError(
                "class_index is required with classes=bins: name one bin's index, or 'pooled' "
                "for every bin together (twenty matrices would not fit one response).",
                field="class_index")
        return POOLED
    if raw.strip().lower() == POOLED:
        return POOLED
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or value not in {c.index for c in cs.classes}:
        offered = ", ".join(str(c.index) for c in cs.classes)
        raise ValidationError(
            f"class_index must be 'pooled' or one of {offered or 'no classes'}; got {raw!r}.",
            field="class_index")
    return value


# ------------------------------------------------------------ common block --


def common(bundle: FeatureBundle, cs: ClassSet, full: bool = False) -> dict[str, Any]:
    """The keys every view carries."""
    return {
        "kind": bundle.kind,
        "coord_system": bundle.coord_system,
        "shower": bundle.shower,
        "classes": cs.as_list(),
        "class_mode": cs.mode,
        "class_basis": cs.basis,
        "n_events": bundle.n,
        "n_selected": bundle.n_selected,
        "n_outside_classes": cs.n_outside,
        "n_excluded_single_hit": bundle.n_excluded_single_hit,
        "features": [catalog.entry(f, bundle.coord_system, full)
                     for f in catalog.offered(bundle.kind)],
    }


_CLASS_NOTES = {
    "windows": ("Momentum classes are the features notebook's windows (1, 2, 5, 10, 19.5) ± 0.5 "
                "GeV, half-open; its 20 GeV class is [19, 20) here because every momentum in "
                "these files is below 20 GeV. Showers in no window are counted, never drawn."),
    "bins": "Momentum classes are the producer's 1 GeV bins (its integer bin column).",
    "label": "Momentum classes are p < 2 GeV against p ≥ 2 GeV, the aggregate's binary label.",
}


def notes(bundle: FeatureBundle, cs: ClassSet) -> list[str]:
    """The sentences every view's Details drawer needs, typographic."""
    out: list[str] = []
    if bundle.kind == ddl.KIND_SINGLE_EVENTS:
        out.append(
            "Features are the producer's aggregate (core.calc_all_features_v3 on raw z), read "
            "as stored. " + schemas.CENSORED_AGGREGATE_NOTICE)
        out.append(
            "avg_phi is the file's arithmetic mean of the hits' azimuths, kept for parity; an "
            "azimuth wraps, so it is not a direction and is never drawn as one. Its circular "
            "mean and angular_spread_circ need Σ cos φ and Σ sin φ per event, which only the "
            "hit files carry.")
    else:
        out.append(
            "Features are rebuilt from the per-shower sums of the event table with core.py's "
            "formulas (calc_all_features_v3, raw z), which reproduce the producer's aggregate "
            "to 10⁻⁹.")
        out.append(
            f"Showers with fewer than {MIN_HITS} hits are left out, as the producer's aggregate "
            f"leaves them out: {bundle.n_excluded_single_hit:,} in this selection.")
        out.append(
            "avg_phi is core.py's arithmetic mean of the hits' azimuths, kept for parity with "
            "the producer's file; an azimuth wraps, so it is not a direction. avg_phi_circ is "
            "the mean direction atan2(Σ sin φ, Σ cos φ).")
    out.append(
        "Centroids are energy-weighted (core.py:491-497); std_r and the SDs inside "
        "angular_spread are sample SDs (ddof = 1); num_hits counts rows. angular_spread adds a "
        "linear SD of φ, which the ±π cut inflates; angular_spread_circ uses the circular SD "
        "√(−2 ln R̄) instead.")
    if bundle.coord_system == "lab":
        out.append(
            f"Depth in the absolute frame is quoted below the front face, z − "
            f"{ddl.CORE_SHIFT_Z_MM:g} mm. The volume, both densities, centroid_z and the radii "
            "use raw z, as the producer computed them, so the volume there is not a geometric "
            "volume.")
    out.append(
        "core.py floors width, height, depth and depth range at 10⁻⁶ mm; a floored factor "
        "makes the volume tiny and both densities enormous.")
    if bundle.kind == ddl.KIND_TWO_SHOWER:
        out.append(
            "Each shower is classed by its own incident momentum and bin; 'A+B' rows count "
            "with shower B, as in every per-shower split.")
    out.append(_CLASS_NOTES[cs.mode])
    if cs.n_outside and cs.mode == "windows":
        out.append(f"{cs.n_outside:,} showers lie in no window.")
    out += cs.notices
    return [typographic(text) for text in out]


# -------------------------------------------------------------------- D2 --

_DESCRIBE_KEYS = ("n", "n_missing", "mean", "mean_lo", "mean_hi", "sd", "sd_lo", "sd_hi",
                  "sd_population", "min", "q25", "q50", "q75", "max", "n_eps")
_CIRCULAR_KEYS = ("mean_direction", "resultant", "circular_sd", "rayleigh_p")


def _intervals(v: np.ndarray) -> tuple[float, float, float, float] | None:
    """The mean's Student-t and the SD's χ² 95% intervals; ``None`` below N = 2."""
    n = int(v.size)
    if n < gaussian.MIN_MOMENT_SAMPLES:
        return None
    sd = float(v.std(ddof=gaussian.DDOF))
    mean = float(v.mean())
    df = n - 1
    half = gaussian.t_quantile_975(df) * sd / math.sqrt(n)
    return (mean - half, mean + half,
            sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=True)),
            sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=False)))


def _describe_feature(bundle: FeatureBundle, members: Sequence[np.ndarray], feature: Feature,
                      exclude_eps: bool, intervals: bool) -> dict[str, Any]:
    values = bundle.display(feature)
    eps = bundle.eps_mask(feature)
    rows: dict[str, list[Any]] = {k: [] for k in _DESCRIBE_KEYS}
    circ: dict[str, list[Any]] = {k: [] for k in _CIRCULAR_KEYS}
    for m in members:
        v = values[m]
        n_eps = None
        if eps is not None:
            e = eps[m]
            n_eps = int(e.sum())
            if exclude_eps:
                v = v[~e]
        d = describe_mod.describe(v)
        finite = v[np.isfinite(v)]
        moments = d.n >= gaussian.MIN_MOMENT_SAMPLES
        rows["n"].append(d.n)
        rows["n_missing"].append(d.n_nonfinite)
        rows["n_eps"].append(n_eps)
        rows["min"].append(sig(d.min))
        rows["max"].append(sig(d.max))
        if feature.circular:
            # Never a linear mean, SD or quantile of an angle (CLAUDE.md section 2).
            for key in ("mean", "mean_lo", "mean_hi", "sd", "sd_lo", "sd_hi", "sd_population",
                        "q25", "q50", "q75"):
                rows[key].append(None)
            summary = circular.describe_circular(finite)
            circ["mean_direction"].append(sig(summary.mean_direction))
            circ["resultant"].append(sig(summary.resultant))
            circ["circular_sd"].append(sig(summary.circular_sd))
            circ["rayleigh_p"].append(sig(summary.rayleigh_p))
            continue
        bounds = _intervals(finite) if intervals else None
        rows["mean"].append(sig(d.mean) if moments else None)
        rows["sd"].append(sig(d.sd) if moments else None)
        rows["sd_population"].append(sig(d.sd_population) if moments else None)
        for key, i in (("mean_lo", 0), ("mean_hi", 1), ("sd_lo", 2), ("sd_hi", 3)):
            rows[key].append(sig(bounds[i]) if bounds else None)
        for key in ("q25", "q50", "q75"):
            rows[key].append(sig(getattr(d, key)))
    out: dict[str, Any] = dict(rows)
    if not intervals:
        for key in ("mean_lo", "mean_hi", "sd_lo", "sd_hi"):
            out.pop(key)
    if feature.circular:
        out["circular"] = circ
    return out


def describe_view(bundle: FeatureBundle, cs: ClassSet, exclude_eps: bool,
                  intervals: bool = True) -> dict[str, Any]:
    """D2: the describe() table per class and feature, as struct of arrays per feature."""
    members = [np.flatnonzero(cs.mask(c.index)) for c in cs.classes]
    sizes = [int(m.size) for m in members]
    table = {f.id: _describe_feature(bundle, members, f, exclude_eps, intervals)
             for f in catalog.offered(bundle.kind)}
    small = [c.label for c, n in zip(cs.classes, sizes) if 1 < n < gaussian.MIN_ROBUST_SAMPLES]
    view_notes = [
        "Quartiles are np.percentile's linear interpolation, as pandas' describe(); SD is the "
        "sample SD (ddof = 1) and sd_population the ddof = 0 form, for comparison with the "
        "notebook. The mean's 95% interval is Student-t, t(0.975, N − 1) · SD/√N; the SD's is "
        "the χ² interval, which assumes Gaussian values and is too narrow for a heavy tail.",
        "Azimuths get a circular summary - mean direction, mean resultant length R̄, circular "
        "SD and the Rayleigh p - and no linear mean, SD or quartile; min and max lie on "
        "(−π, π].",
    ]
    if small:
        view_notes.append(
            f"Below N = {gaussian.MIN_ROBUST_SAMPLES} the quartiles interpolate between "
            f"individual events ({', '.join(small)}).")
    if exclude_eps:
        view_notes.append(
            "Floored events are left out of the features whose value they set: width, height, "
            "depth and depth range by their own floor, the volume and both densities by any "
            "floored factor.")
    if not intervals:
        view_notes.append("The interval columns were dropped to keep the response under 100 KB.")
    return {
        "table": table,
        "class_stats": [{"index": c.index, "n": n,
                         "c4": sig(gaussian.c4(n)) if n >= gaussian.MIN_MOMENT_SAMPLES else None,
                         "robust": n >= gaussian.MIN_ROBUST_SAMPLES}
                        for c, n in zip(cs.classes, sizes)],
        "intervals": {
            "mean": "95% Student-t interval of the mean (uncertainty of the aggregate)",
            "sd": "95% χ² interval of the SD (assumes Gaussian values)",
        } if intervals else None,
        "exclude_eps": exclude_eps,
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }


# -------------------------------------------------------------------- D3 --


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    da, db = a - a.mean(), b - b.mean()
    saa, sbb = float((da * da).sum()), float((db * db).sum())
    if not (saa > 0.0 and sbb > 0.0) or not (math.isfinite(saa) and math.isfinite(sbb)):
        return None
    r = float((da * db).sum()) / math.sqrt(saa * sbb)
    return max(-1.0, min(1.0, r)) if math.isfinite(r) else None


def _pearson_matrix(stack: np.ndarray) -> np.ndarray:
    """Pearson r of every pair of rows of ``stack`` (features × events); NaN without variance."""
    if stack.shape[1] == 0:
        return np.full((stack.shape[0], stack.shape[0]), np.nan)
    centred = stack - stack.mean(axis=1, keepdims=True)
    norms = np.sqrt((centred * centred).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (centred @ centred.T) / np.outer(norms, norms)
    return np.clip(r, -1.0, 1.0)


def _cell(r: float | None, n: int, diagonal: bool) -> tuple[float | None, ...]:
    """``(r, lo, hi)`` of one matrix cell; nothing below N = 4 or without variance."""
    if r is None or not math.isfinite(r) or n < MIN_FISHER:
        return None, None, None
    if diagonal:
        return 1.0, None, None
    interval = fisher_z_interval(r, n)
    if interval is None:
        # |r| = 1: one feature is a linear map of the other; the interval is degenerate.
        return sig(r), sig(r), sig(r)
    return sig(r), sig(interval.lo), sig(interval.hi)


def corr_view(bundle: FeatureBundle, cs: ClassSet, which: int | str,
              exclude_eps: bool) -> dict[str, Any]:
    """D3: Pearson r of every feature pair over one class, upper triangle with the diagonal."""
    features = catalog.offered(bundle.kind)
    mask = cs.mask(which)
    stack = np.vstack([bundle.values[f.id][mask] for f in features])
    floored = bundle.volume_floored()[mask]
    eps_pair = {i for i, f in enumerate(features) if f.id in catalog.EPS_PAIR_FEATURES}
    excluded = floored if exclude_eps else np.zeros_like(floored)
    if np.isfinite(stack).all():
        # Every pair sees the same events (less the floored ones where they are
        # left out): two matrix products instead of a masked pass per pair.
        whole, n_whole = _pearson_matrix(stack), stack.shape[1]
        part = _pearson_matrix(stack[:, ~excluded]) if excluded.any() else whole
        n_part = n_whole - int(excluded.sum())

        def pair(i: int, j: int) -> tuple[float | None, int]:
            if i in eps_pair or j in eps_pair:
                return float(part[i, j]), n_part
            return float(whole[i, j]), n_whole
    else:
        finite = np.isfinite(stack)

        def pair(i: int, j: int) -> tuple[float | None, int]:
            keep = finite[i] & finite[j]
            if i in eps_pair or j in eps_pair:
                keep &= ~excluded
            n = int(keep.sum())
            return (_pearson(stack[i, keep], stack[j, keep]) if n >= MIN_FISHER else None), n
    cells: list[tuple[float | None, ...]] = []
    n_out: list[int] = []
    for i in range(len(features)):
        for j in range(i, len(features)):
            r, n = pair(i, j)
            n_out.append(n)
            cells.append(_cell(r, n, i == j))
    n_class = int(mask.sum())
    view_notes = [
        f"Pearson r over the events of the class, each event one independent observation; "
        f"the 95% interval is Fisher's z with SE 1/√(N − 3), N = events. r is quoted from "
        f"N = {MIN_FISHER}, where that interval first exists; the diagonal is 1 by definition.",
        "Cells of avg_phi, avg_phi_circ and angular_spread are hatched: a linear correlation "
        "of a circular quantity depends on where the ±π cut falls.",
        "Pearson r on features spanning many decades (the volume, both densities, the energy) "
        "stays dominated by their tails even with the floored events left out.",
    ]
    if exclude_eps:
        view_notes.append(
            f"Events with a floored width, height or depth ({int(floored.sum()):,} in this "
            "class) are left out of the pairs involving the volume or a density, the only "
            "values the floor corrupts; every other pair keeps them. exclude_eps=false "
            "reproduces the notebook.")
    return {
        "class": which,
        "class_label": cs.label_of(which),
        "n": n_class,
        "n_excluded_eps": int(floored.sum()) if exclude_eps else 0,
        "exclude_eps": exclude_eps,
        "eps_pair_features": list(catalog.EPS_PAIR_FEATURES) if exclude_eps else [],
        "order": [f.id for f in features],
        "layout": "upper triangle with the diagonal, row-major: (0,0), (0,1) … (0,k−1), (1,1) …",
        "r": [cell[0] for cell in cells],
        "lo": [cell[1] for cell in cells],
        "hi": [cell[2] for cell in cells],
        "n_pairs": n_out,
        "hatched": {f.id: catalog.HATCHED[f.id] for f in features if f.id in catalog.HATCHED},
        "method": METHOD_FISHER,
        "interval": typographic("95% Fisher-z interval, N = events (iid)"),
        "thresholds": {"fisher": MIN_FISHER},
        "view_notes": [typographic(t) for t in view_notes],
    }


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


def _measured_step(values: np.ndarray) -> float | None:
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
        q = pitch if pitch else _measured_step(v)
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


def _snapped_edges(lo: float, hi: float, bins: int, q: float,
                   anchor: float) -> tuple[np.ndarray, int]:
    """Edges half a quantum off the lattice, each bin a whole number of quanta wide."""
    per_bin = max(1, math.ceil((hi - lo) / bins / q - 1e-9))
    width = per_bin * q
    first = anchor + (math.floor((lo - anchor) / q - 0.5 + 1e-9) + 0.5) * q
    n = max(1, math.ceil((hi - first) / width - 1e-9))
    return first + width * np.arange(n + 1, dtype=np.float64), per_bin


def plan_axis(feature: Feature, coord_system: str, per_class: Sequence[np.ndarray],
              scale: str, decades: float | None, bins_for: Any, pitch: float | None,
              raw_pooled: np.ndarray) -> AxisPlan:
    """The shared axis of every class: range from the drawn classes, bins, quantum.

    ``per_class`` are the classes' values already on the axis (log10 on a log
    axis); ``bins_for(drawn sizes)`` is the view's bin rule.
    """
    sizes = [int(v.size) for v in per_class]
    drawn = [v for v in per_class if v.size >= histogram.MIN_HISTOGRAM_SAMPLES]
    provisional = not drawn
    pooled = np.concatenate(drawn or list(per_class) or [np.empty(0)])
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
        clip = clip_mod.percentile_clip(pooled)
        lo, hi, interval = clip_mod.nice_range(clip.lo, clip.hi, fine=True)
        clipping = clip
    bins = int(bins_for([n for n in sizes if n >= histogram.MIN_HISTOGRAM_SAMPLES]))
    quantum = None
    edges = np.linspace(lo, hi, bins + 1, dtype=np.float64)
    if scale == "linear":
        quantum = lattice_quantum(feature, coord_system, raw_pooled, pitch)
        if quantum and quantum["verified"]:
            edges, per_bin = _snapped_edges(lo, hi, bins, float(quantum["value"]),
                                            float(quantum["anchor"]))
            quantum.update(snapped=True, per_bin=per_bin)
        elif quantum:
            notes.append(f"{feature.id} should sit on a lattice of {quantum['value']} "
                         f"{quantum['unit']} but its values do not: bins are not aligned.")
    if scale != "circular":
        # The disclosure counts the values outside the range actually drawn.
        a, b = float(edges[0]), float(edges[-1])
        clipping = clip_mod.ClipResult(
            lo=a, hi=b, low_percentile=clipping.low_percentile,
            high_percentile=clipping.high_percentile, n_total=int(pooled.size),
            n_below=int((pooled < a).sum()), n_above=int((pooled > b).sum()),
            data_min=clipping.data_min, data_max=clipping.data_max, applied=clipping.applied)
    if provisional:
        notes.append(f"No class reaches N = {histogram.MIN_HISTOGRAM_SAMPLES}: the range is "
                     "taken from the under-powered classes and is provisional.")
    return AxisPlan(feature, coord_system, scale, edges, provisional, clipping, quantum,
                    decades, interval, notes)


def _comb(counts: np.ndarray) -> dict[str, Any]:
    """The lag-1 comb statistic of pooled counts, judged against counting noise."""
    bins = int(counts.size)
    minimum = 3 * stagger.DETREND_WINDOW
    if bins < minimum:
        return {"lag1": None, "bins": bins, "combed": None, "noise_reference": sig(NOISE_LAG1),
                "threshold": None, "measured_on": "pooled counts of the drawn classes",
                "note": f"Fewer than {minimum} bins: too short to measure a comb."}
    lag1 = stagger.profile_lag1(counts.astype(np.float64))
    pairs = bins - 2 * (stagger.DETREND_WINDOW // 2) - 1
    threshold = NOISE_LAG1 - 2.0 / math.sqrt(pairs)
    combed = lag1 is not None and lag1 < threshold
    note = (f"Lag-1 autocorrelation of the detrended pooled counts {lag1:.2f}; counting noise "
            f"alone gives {NOISE_LAG1:.2f}, and a comb is called below {threshold:.2f} (two "
            "standard errors lower)." if lag1 is not None else "No variation to measure.")
    if combed:
        note += (" The histogram combs: its bins beat against values the detector lattice "
                 "quantises, which is segmentation, not shower structure.")
    return {"lag1": sig(lag1, 3), "bins": bins, "combed": combed,
            "noise_reference": sig(NOISE_LAG1, 3), "threshold": sig(threshold, 3),
            "measured_on": "pooled counts of the drawn classes", "note": typographic(note)}


# -------------------------------------------------------------------- D4 --


def _class_values(bundle: FeatureBundle, cs: ClassSet, feature: Feature,
                  exclude_eps: bool) -> tuple[list[np.ndarray], list[int]]:
    values = bundle.display(feature)
    eps = bundle.eps_mask(feature)
    out, excluded = [], []
    for c in cs.classes:
        m = cs.mask(c.index)
        if exclude_eps and eps is not None:
            excluded.append(int((m & eps).sum()))
            m = m & ~eps
        else:
            excluded.append(0)
        out.append(values[m])
    return out, excluded


def _hist_message(n: int, feature: Feature, kde_notes: Sequence[str]) -> str | None:
    parts: list[str] = []
    if n == 0:
        return "No events in this class."
    if n < kde.MIN_KDE_SAMPLES:
        parts.append(f"N = {n}: below the {kde.MIN_KDE_SAMPLES}-event floor for a density "
                     "curve; the events themselves are drawn.")
    elif n < histogram.MIN_HISTOGRAM_SAMPLES:
        parts.append(f"N = {n}: the histogram is withheld below N = "
                     f"{histogram.MIN_HISTOGRAM_SAMPLES} - it would be a comb whose heights the "
                     "bin width sets - so the events are drawn with the density curve.")
    if feature.circular and n >= kde.MIN_KDE_SAMPLES:
        parts.append("No density curve for an azimuth: a linear kernel would smooth across "
                     "the ±π cut.")
    parts += [note for note in kde_notes if note]
    return typographic(" ".join(parts)) if parts else None


def hist_view(bundle: FeatureBundle, cs: ClassSet, feature: Feature, scale: str,
              exclude_eps: bool, pitch: float | None, curve_points: int = kde.CURVE_POINTS,
              bins_divisor: int = 1) -> dict[str, Any]:
    """D4: per-class counts on shared edges, KDE scaled to counts, strips below N = 15."""
    raw, excluded = _class_values(bundle, cs, feature, exclude_eps)
    sizes = [int(np.isfinite(v).sum()) for v in raw]
    drawn_raw = [v for v, n in zip(raw, sizes) if n >= histogram.MIN_HISTOGRAM_SAMPLES]
    pooled_raw = np.concatenate(drawn_raw or raw or [np.empty(0)])
    resolved, decades = resolve_scale(feature, bundle.coord_system, scale, pooled_raw, "scale")
    on_axis = [to_axis(v, resolved) for v in raw]
    per_class = [v for v, _ in on_axis]

    def bins_for(drawn_sizes: list[int]) -> int:
        rice = histogram.adaptive_bins(min(drawn_sizes) if drawn_sizes else 0)
        return max(histogram.MIN_BINS, rice // max(1, bins_divisor))

    axis = plan_axis(feature, bundle.coord_system, per_class, resolved, decades, bins_for,
                     pitch, np.concatenate(raw or [np.empty(0)]))
    width = axis.width
    q_axis = (float(axis.quantum["value"]) if axis.quantum and axis.quantum.get("verified")
              else None)
    curve_x = np.linspace(axis.lo, axis.hi, int(curve_points))
    series: list[dict[str, Any]] = []
    pooled_counts = np.zeros(axis.bins, dtype=np.int64)
    y_count = y_density = 0.0
    weak_peaks: list[tuple[int, float, float]] = []   # curves of classes that set no range
    for c, values, (_, n_nonpositive), n_eps in zip(cs.classes, per_class, on_axis, excluded):
        n = int(values.size)
        counted = histogram.count_histogram(values, axis.edges)
        drawn = n >= histogram.MIN_HISTOGRAM_SAMPLES
        kde_block, kde_notes, peak = None, [], 0.0
        if not feature.circular and n >= kde.MIN_KDE_SAMPLES:
            result = kde.gaussian_kde_binned(values, axis.lo, axis.hi, points=int(curve_points),
                                             n_total=n, quantum=q_axis)
            if result.drawn:
                kde_block = {"bandwidth": sig(result.bandwidth), "rule": SILVERMAN_RULE,
                             "pdf": sig_list(result.pdf), "scale_to_counts": sig(n * width),
                             "n_outside_grid": result.n_outside_grid,
                             "per": "per decade" if axis.scale == "log" else f"per {feature.unit}"}
                peak = max(result.pdf, default=0.0)
            else:
                kde_notes = result.notes
        if drawn:
            top = float(max(counted.counts, default=0))
            pooled_counts += np.asarray(counted.counts, dtype=np.int64)
            y_count = max(y_count, top, peak * n * width)
            y_density = max(y_density, top / (n * width), peak)
        elif kde_block is not None:
            weak_peaks.append((c.index, peak * n * width, peak))
        strip = (sig_list(np.sort(values)[:MAX_STRIP])
                 if 0 < n < histogram.MIN_HISTOGRAM_SAMPLES else None)
        series.append({
            "index": c.index,
            "label": c.label,
            "n": n,
            "n_in_range": counted.n_in_range,
            "n_below": counted.n_below,
            "n_above": counted.n_above,
            "n_nonpositive": n_nonpositive,
            "n_excluded_eps": n_eps,
            "draw": "histogram" if drawn else ("strip" if n else "none"),
            "counts": counted.counts if drawn else [],
            "density_scale": sig(1.0 / (n * width)) if n and width > 0 else None,
            "kde": kde_block,
            "strip": strip,
            "drives_scale": drawn,
            "message": _hist_message(n, feature, kde_notes),
        })
    drawn_any = any(s["drives_scale"] for s in series)
    if drawn_any:
        # A weak class's curve that overflows the robust range is clipped by
        # the interface and disclosed: its true peak travels here.
        overflow = [{"index": index, "peak_count": sig(pc), "peak_density": sig(pd)}
                    for index, pc, pd in weak_peaks if pc > y_count or pd > y_density]
        basis = f"classes with N ≥ {histogram.MIN_HISTOGRAM_SAMPLES}: their bars and curves"
    else:
        # Nothing robust: the weak curves set the range, labelled provisional;
        # with no curve at all there is no density axis to label.
        overflow = []
        y_count = max((pc for _, pc, _ in weak_peaks), default=0.0)
        y_density = max((pd for _, _, pd in weak_peaks), default=0.0)
        basis = (f"no class reaches N = {histogram.MIN_HISTOGRAM_SAMPLES}: the curves of the "
                 "smaller classes, provisional" if weak_peaks
                 else "no class supports a density: the axis carries no density scale")
    has_scale = drawn_any or bool(weak_peaks)
    comb = _comb(pooled_counts) if drawn_any and not feature.circular else None
    view_notes = list(axis.notes)
    if exclude_eps and bundle.eps_mask(feature) is not None:
        view_notes.append("Events whose value of this feature involves a floor are left out "
                          "and counted per class (n_excluded_eps).")
    if axis.scale == "log" and any(n for _, n in on_axis):
        view_notes.append("Values at or below zero have no place on a log axis: they are "
                          "counted per class (n_nonpositive) and left out of the counts, the "
                          "curve and the normaliser.")
    if comb and comb.get("combed"):
        view_notes.append(comb["note"])
    return {
        "feature": feature.id,
        "scale": axis.scale,
        "requested_scale": scale,
        "axis": axis.as_dict(),
        "series": series,
        "curve_x": sig_list(curve_x),
        "y_max": {
            "count": sig(y_count) if has_scale else None,
            "density": sig(y_density) if has_scale else None,
            "provisional": not drawn_any,
            "overflow": overflow,
            "basis": typographic(basis),
        },
        "comb": comb,
        "exclude_eps": exclude_eps,
        "y_axis": {"default": "density", "density": "count × density_scale = count / (N · bin "
                   "width)", "count": "events per bin (the notebook's stat=count)"},
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }


# -------------------------------------------------------------------- D5 --


def _pairs(bundle: FeatureBundle, cs: ClassSet, fx: Feature, fy: Feature, exclude_eps: bool,
           ) -> tuple[list[tuple[np.ndarray, np.ndarray]], list[int]]:
    x_all, y_all = bundle.display(fx), bundle.display(fy)
    eps = bundle.eps_mask(fx)
    out, excluded = [], []
    for c in cs.classes:
        m = cs.mask(c.index) & np.isfinite(x_all) & np.isfinite(y_all)
        if exclude_eps and eps is not None:
            excluded.append(int((m & eps).sum()))
            m = m & ~eps
        else:
            excluded.append(0)
        out.append((x_all[m], y_all[m]))
    return out, excluded


def hist2d_view(bundle: FeatureBundle, cs: ClassSet, feature: Feature, scale: str,
                y_scale: str, exclude_eps: bool, pitch: float | None,
                bins: int | None = None) -> dict[str, Any]:
    """D5: the feature against the deposited energy, dense integer counts per class."""
    fy = catalog.BY_ID[HIST2D_Y]
    pairs, excluded = _pairs(bundle, cs, feature, fy, exclude_eps)
    sizes = [int(x.size) for x, _ in pairs]
    drawn_idx = [i for i, n in enumerate(sizes) if n >= histogram.MIN_HISTOGRAM_SAMPLES]
    source = [pairs[i] for i in drawn_idx] or pairs
    pooled_x = np.concatenate([x for x, _ in source] or [np.empty(0)])
    pooled_y = np.concatenate([y for _, y in source] or [np.empty(0)])
    sx, dx = resolve_scale(feature, bundle.coord_system, scale, pooled_x, "scale")
    sy, dy = resolve_scale(fy, bundle.coord_system, y_scale, pooled_y, "y_scale")

    # A pair needs both coordinates on their axes: a non-positive value on a
    # log axis drops the pair, counted per axis.
    placed, dropped = [], []
    for x, y in pairs:
        keep = np.ones(x.size, dtype=bool)
        nx = ny = 0
        if sx == "log":
            nx = int((x <= 0).sum())
            keep &= x > 0
        if sy == "log":
            ny = int((y <= 0).sum())
            keep &= y > 0
        tx = np.log10(x[keep]) if sx == "log" else x[keep]
        ty = np.log10(y[keep]) if sy == "log" else y[keep]
        placed.append((tx, ty))
        dropped.append((nx, ny))
    n_classes = sum(1 for n in sizes if n > 0)
    default_bins = HIST2D_BINS if n_classes <= HIST2D_MANY_CLASSES else HIST2D_BINS_MANY
    nb = int(bins) if bins else default_bins
    x_axis = plan_axis(feature, bundle.coord_system, [x for x, _ in placed], sx, dx,
                       lambda _: nb, pitch, np.concatenate([x for x, _ in pairs] or [np.empty(0)]))
    y_axis = plan_axis(fy, bundle.coord_system, [y for _, y in placed], sy, dy,
                       lambda _: nb, pitch, np.concatenate([y for _, y in pairs] or [np.empty(0)]))
    xe, ye = x_axis.edges, y_axis.edges
    series: list[dict[str, Any]] = []
    max_count = 0
    for c, (x, y), (nx, ny), n_eps in zip(cs.classes, placed, dropped, excluded):
        n = int(x.size)
        in_x = (x >= xe[0]) & (x <= xe[-1])
        in_y = (y >= ye[0]) & (y <= ye[-1])
        outside = {"x_below": int((x < xe[0]).sum()), "x_above": int((x > xe[-1]).sum()),
                   "y_below": int((y < ye[0]).sum()), "y_above": int((y > ye[-1]).sum()),
                   "total": int((~(in_x & in_y)).sum())}
        base = {"index": c.index, "label": c.label, "n": n, "n_nonpositive_x": nx,
                "n_nonpositive_y": ny, "n_excluded_eps": n_eps}
        if n >= histogram.MIN_HISTOGRAM_SAMPLES:
            grid, _, _ = np.histogram2d(x[in_x & in_y], y[in_x & in_y], bins=[xe, ye])
            counts = grid.T.astype(np.int64)          # rows are y bins
            peak = int(counts.max(initial=0))
            max_count = max(max_count, peak)
            series.append({**base, "draw": "histogram", "counts": counts.ravel().tolist(),
                           "max_count": peak, "outside": outside})
        elif n:
            order = np.argsort(x, kind="stable")[:MAX_STRIP]
            series.append({**base, "draw": "pairs",
                           "pairs": [[sig(a), sig(b)] for a, b in zip(x[order], y[order])],
                           "outside": outside})
        else:
            series.append({**base, "draw": "none"})
    view_notes = list(dict.fromkeys(x_axis.notes + y_axis.notes))
    if any(nx or ny for nx, ny in dropped):
        view_notes.append("Pairs with a value at or below zero on a log axis are left out and "
                          "counted per class and axis.")
    if any(s["draw"] == "pairs" for s in series):
        view_notes.append(f"Classes below N = {histogram.MIN_HISTOGRAM_SAMPLES} show their "
                          "events as points: a 2-D histogram of so few would be a scatter of "
                          "single counts.")
    return {
        "x": x_axis.as_dict(),
        "y": y_axis.as_dict(),
        "layout": "counts are row-major with rows the y bins: counts[iy * x.bins + ix]",
        "series": series,
        "color": {
            "scale": "log10",
            "vmin": 0.0,
            "vmax": sig(math.log10(max_count)) if max_count > 0 else 0.0,
            "max_count": max_count,
            "unit": "events per bin",
            "empty": "transparent",
            "provisional": max_count == 0,
            "note": typographic(
                "Colour is log10 of the count; an empty bin is transparent, and the first "
                "drawn level (count 1, log10 = 0) takes a ramp position with at least 3:1 "
                "contrast against the card."),
        },
        "exclude_eps": exclude_eps,
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }
