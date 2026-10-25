"""The feature explorer's shared core (D2-D5): one cached per-event bundle, its classes, the common block.

A request names a frame and a shower. The bundle holds every offered feature
of that shower in that frame for the selected events - one read of the event
table, no hit scan - cached in the ``physics`` cache under the clamped
selection. Everything a view varies (class set, feature, scale, the eps
exclusion) is a NumPy step over the cached arrays.

Showers with fewer than two hits are left out on every kind, as the
producer's aggregate leaves them out: their SDs do not exist, and the two
kinds then describe the same events.

This module holds what every view shares: the thresholds and class-set
constants, the cached bundle (one read of the event table), the class sets
built over it, and the common block of every response. The views are in
``feature_describe.py`` (D2), ``feature_corr.py`` (D3), ``feature_hist.py``
(D4, D5) and the axis planning they share in ``feature_axes.py``; each imports
this module, and this module imports none of them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming, schemas
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..stats import circular, gaussian, histogram, kde, momentum
from ..text import typographic
from . import features_catalog as catalog
from . import physics_cache, showers
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
