"""The feature explorer's catalogue: what each per-event feature is, and the SQL that reads it.

Page 2's explorer (D2-D5) shows the nineteen features the notebooks give
XGBoost - ``core.calc_all_features_v3`` (reference_ipynb_notebooks/core.py:
459-574) - per shower and frame. Where the numbers come from depends on the
experiment's kind:

* **hit kinds** (two showers with networks, one shower with its hits) rebuild
  them from the per-shower Group-1 sums of the event table through
  ``group1.feature_sql``, the one copy of core.py's formulas; nothing here
  restates them;
* **the aggregated kind** stores the producer's own values under the file's
  names (``width``, ``width_trans``, ``width_local`` ...), read as they are.

Request strings never reach SQL: a feature id is looked up here, and every
column name comes from ``ddl``, ``group1`` or ``showers`` (the rule at
calosrv/db/ddl.py).

Each feature carries what a reader has to know before trusting a number:

* **circular** - an azimuth, never averaged linearly (CLAUDE.md section 2).
  ``avg_phi`` is core.py's *arithmetic* mean of the hits' φ, kept because the
  producer's file and the XGBoost inputs use it; it is not a direction and is
  never drawn as one. Hit kinds also offer ``avg_phi_circ``, the mean direction
  atan2(Σ sin φ, Σ cos φ), which only per-hit sums can give.
* **partly circular** - ``angular_spread`` = SD(θ) + SD(φ) with a *linear* SD
  of φ, which the ±π cut inflates (70.6% of the electron file's tail above
  0.5 rad sits at a centroid azimuth beyond ±2.5 rad); ``angular_spread_circ``
  takes the circular SD √(−2 ln R̄) instead.
* **floored at eps** - core.py floors width, height, depth and depth range at
  10⁻⁶ mm, so a floored factor makes the volume tiny and both densities huge
  (up to 2 × 10⁹ hits/mm³ against a median of 2 × 10⁻⁷ on the electron file).
* **lattice-quantised** - depth and depth range in the absolute and per-shower
  translated frames are whole numbers of 20.5 mm layers, and the hit count is
  an integer, so histogram bins are aligned to that quantum and a log axis,
  which no quantum fits, is not offered for them. Width and height take values
  on the irregular differences of the x and y lattices: no quantum exists, so
  their histograms measure a comb instead.
* **display offset** - the absolute-frame depth is quoted below the front face,
  z − 3649 mm (decision D1); every other value, the volume and the densities
  included, stays on raw z as the producer computed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..db import ddl, group1
from ..errors import CapabilityError, ValidationError
from .showers import ShowerColumns

#: core.py's ``eps``: the floor of width, height, depth and depth range (mm).
EPS = group1.EPS

#: The request's frames and their Group-1 frame codes.
COORD_SYSTEMS: tuple[str, ...] = ddl.COORD_SYSTEMS

#: Axis symbols per frame, for labels: lab x, y, z; per-shower translated Δx,
#: Δy, Δz; Local u, v, w.
SYMBOLS: dict[str, tuple[str, str, str]] = {
    "lab": ("x", "y", "z"),
    "trans": ("Δx", "Δy", "Δz"),
    "local": ("u", "v", "w"),
}

FRAME_WORDS: dict[str, str] = {
    "lab": "absolute (detector)",
    "trans": "per-shower translated",
    "local": "Local (shower-fixed)",
}

#: Quantum kinds.
QUANTUM_LAYER = "layer"     # a whole number of sampling layers (mm)
QUANTUM_COUNT = "count"     # an integer (hits)

#: Which floor a feature's value involves: its own, or the volume's (width,
#: height or depth). core.py:475 builds the volume from depth, not depth range.
EPS_OWN = "own"
EPS_VOLUME = "volume"

#: The features whose own value is floored, by the flag the bundle keeps.
FLOORED: tuple[str, ...] = ("width", "height", "depth", "depth_range")
#: The factors of the volume (core.py:475).
VOLUME_FACTORS: tuple[str, ...] = ("width", "height", "depth")


@dataclass(frozen=True)
class Feature:
    """One per-event feature: meaning, unit and the flags that govern its display."""

    id: str
    label: str                  # with {x}, {y}, {z} for the frame's axis symbols
    unit: str
    description: str
    frame_dependent: bool = True
    circular: bool = False
    partly_circular: bool = False
    eps: str | None = None              # EPS_OWN | EPS_VOLUME | None
    positive: bool = False              # > 0 by construction: a log axis is possible
    quantum: str | None = None          # QUANTUM_LAYER | QUANTUM_COUNT | None
    quantum_frames: tuple[str, ...] = ()
    irregular_lattice: bool = False     # values on irregular lattice differences
    energy_weighted: bool = False
    raw_z: bool = False                 # depends on the absolute frame's raw z
    hit_kinds_only: bool = False
    notebook: bool = True               # one of the notebooks' nineteen XGBoost inputs

    def quantised_in(self, coord_system: str) -> str | None:
        """The quantum kind of this feature in ``coord_system``, else ``None``."""
        if self.quantum == QUANTUM_COUNT:
            return QUANTUM_COUNT
        if self.quantum == QUANTUM_LAYER and coord_system in self.quantum_frames:
            return QUANTUM_LAYER
        return None


#: The catalogue, in the notebooks' XGBoost order (notebooks.md section 5) with
#: the two hit-kind variants after the features they replace.
FEATURES: tuple[Feature, ...] = (
    Feature("width", "width: {x} extent", "mm",
            "x_max − x_min of the shower's hits, floored at 10⁻⁶ mm (core.py:470).",
            eps=EPS_OWN, positive=True, irregular_lattice=True),
    Feature("height", "height: {y} extent", "mm",
            "y_max − y_min of the shower's hits, floored at 10⁻⁶ mm.",
            eps=EPS_OWN, positive=True, irregular_lattice=True),
    Feature("depth", "depth: deepest {z}", "mm",
            "max(z_max, 10⁻⁶) (core.py:473): the deepest hit's coordinate, not an extent. In "
            "the absolute frame it is raw z, quoted below the front face (z − 3649 mm).",
            eps=EPS_OWN, positive=True, quantum=QUANTUM_LAYER, quantum_frames=("lab", "trans"),
            raw_z=True),
    Feature("depth_range", "depth range: {z} extent", "mm",
            "z_max − z_min of the shower's hits, floored at 10⁻⁶ mm.",
            eps=EPS_OWN, positive=True, quantum=QUANTUM_LAYER, quantum_frames=("lab", "trans")),
    Feature("volume", "volume: width × height × depth", "mm³",
            "width × height × depth (core.py:475), with depth the deepest coordinate - raw z "
            "in the absolute frame - so it is not a geometric volume there.",
            eps=EPS_VOLUME, positive=True, raw_z=True),
    Feature("num_hits", "number of hits", "hits",
            "Rows of the shower: one per cell and event.",
            frame_dependent=False, positive=True, quantum=QUANTUM_COUNT),
    Feature("total_hit_energy", "total deposited energy", "GeV",
            "Σ E of the shower's hits: the deposited energy, not the incident momentum.",
            frame_dependent=False, positive=True),
    Feature("centroid_x", "energy-weighted centroid {x}", "mm",
            "Σ E·x / Σ E (core.py:491-497).", energy_weighted=True),
    Feature("centroid_y", "energy-weighted centroid {y}", "mm",
            "Σ E·y / Σ E.", energy_weighted=True),
    Feature("centroid_z", "energy-weighted centroid {z}", "mm",
            "Σ E·z / Σ E; raw z in the absolute frame.", energy_weighted=True, raw_z=True),
    Feature("mean_r", "mean hit radius r", "mm",
            "Mean of r = √(x² + y² + z²) over the hits, in this frame's coordinates.",
            positive=True, raw_z=True),
    Feature("std_r", "SD of hit radius r", "mm",
            "Sample SD (ddof = 1) of r over the hits.", positive=True, raw_z=True),
    Feature("max_r", "maximum hit radius r", "mm",
            "Largest r over the hits.", positive=True, raw_z=True),
    Feature("weighted_r_mean", "energy-weighted mean radius r", "mm",
            "Σ E·r / Σ E.", positive=True, energy_weighted=True, raw_z=True),
    Feature("avg_theta", "mean polar angle θ of the hits", "rad",
            "Mean of θ = arccos(z / r) over the hits.", positive=True, raw_z=True),
    Feature("avg_phi", "arithmetic mean of the hits' azimuth φ", "rad",
            "core.py's arithmetic mean of φ = atan2(y, x). An azimuth wraps, so this is not a "
            "direction: kept for parity with the producer's file and the XGBoost inputs only.",
            circular=True),
    Feature("avg_phi_circ", "mean direction of the hits' azimuth φ", "rad",
            "atan2(Σ sin φ, Σ cos φ): the circular mean of the hits' azimuths.",
            circular=True, hit_kinds_only=True, notebook=False),
    Feature("angular_spread", "angular spread SD(θ) + SD(φ)", "rad",
            "core.py:499: sample SD of θ plus the linear sample SD of φ, which the ±π cut "
            "inflates for showers near the cut.",
            partly_circular=True, positive=True, raw_z=True),
    Feature("angular_spread_circ", "angular spread SD(θ) + circular SD(φ)", "rad",
            "Sample SD of θ plus the circular SD √(−2 ln R̄) of φ: angular_spread without the "
            "branch-cut inflation.",
            positive=True, raw_z=True, hit_kinds_only=True, notebook=False),
    Feature("numerical_density", "hit density: hits / volume", "hits/mm³",
            "num_hits / volume; enormous wherever a factor of the volume is floored.",
            eps=EPS_VOLUME, positive=True, raw_z=True),
    Feature("energy_density", "energy density: energy / volume", "GeV/mm³",
            "total_hit_energy / volume; enormous wherever a factor of the volume is floored.",
            eps=EPS_VOLUME, positive=True, raw_z=True),
)

BY_ID: dict[str, Feature] = {f.id: f for f in FEATURES}

#: The features whose correlations, with eps exclusion on, leave out the
#: events with a floored volume factor: only their values are corrupted by it.
EPS_PAIR_FEATURES: tuple[str, ...] = tuple(f.id for f in FEATURES if f.eps == EPS_VOLUME)

#: Why a feature's cells of the correlation matrix are hatched.
HATCHED: dict[str, str] = {
    "avg_phi": ("An azimuth has no linear correlation: the cells carry Mardia's "
                "circular–linear R, or the circular–circular r_c with the other azimuth. The "
                "notebook's linear r, which jumps where a shower straddles the ±π cut, is kept "
                "beside them for parity only."),
    "avg_phi_circ": ("An azimuth has no linear correlation: the cells carry Mardia's "
                     "circular–linear R, or the circular–circular r_c with the other azimuth."),
    "angular_spread": ("Contains a linear SD of φ, inflated by the ±π cut, so part of its "
                       "variance is the cut's position rather than the shower."),
}

#: The aggregated kind's columns for the frame-independent features.
_EVENTS_BASE: dict[str, str] = {"num_hits": "n_hits", "total_hit_energy": "e_dep"}
_EVENTS_COLUMNS: frozenset[str] = frozenset(name for name, _ in ddl.EVENT_FEATURE_COLUMNS)


def offered(kind: str | None) -> tuple[Feature, ...]:
    """The features an experiment of ``kind`` offers, in catalogue order."""
    if kind == ddl.KIND_SINGLE_EVENTS:
        return tuple(f for f in FEATURES if not f.hit_kinds_only)
    return FEATURES


def get(kind: str | None, feature_id: str, field_name: str = "feature",
        capability: str = "feat-hist") -> Feature:
    """The offered feature ``feature_id``, or a 422 naming the request field.

    An id the catalogue knows but this kind's data cannot serve - a hit-kind
    feature asked of the aggregate - is a capability refusal naming
    ``capability`` (the view's card), so the interface can tell it from a typo.
    """
    features = offered(kind)
    for feature in features:
        if feature.id == feature_id:
            return feature
    if feature_id in BY_ID and BY_ID[feature_id].hit_kinds_only:
        reason = ("It needs the per-hit sums Σ cos φ and Σ sin φ, which only experiments with "
                  "hits carry; the aggregate stores the arithmetic mean of φ only.")
        raise CapabilityError(
            f"{field_name}={feature_id!r} is not available for this experiment: {reason}",
            field=field_name, capability=capability, kind=kind, reason=reason,
        )
    raise ValidationError(
        f"{field_name} must be one of {', '.join(f.id for f in features)}; got {feature_id!r}.",
        field=field_name,
    )


def frame_code(coord_system: str) -> str:
    """``lab`` -> ``abs``, ``trans`` -> ``trn``, ``local`` -> ``loc``."""
    return ddl.frame_code(coord_system)


def display_offset(feature: Feature, coord_system: str) -> float | None:
    """What is added to a stored value before it is shown (decision D1), else ``None``."""
    if feature.id == "depth" and coord_system == "lab":
        return -ddl.CORE_SHIFT_Z_MM
    return None


def label(feature: Feature, coord_system: str) -> str:
    """The feature's name in ``coord_system``'s axis symbols."""
    x, y, z = SYMBOLS[coord_system]
    text = feature.label.format(x=x, y=y, z=z)
    if display_offset(feature, coord_system) is not None:
        text = f"depth: deepest z − {ddl.CORE_SHIFT_Z_MM:g} mm (below the front face)"
    return text


def scales(feature: Feature, coord_system: str) -> list[str]:
    """The x-axis scales offered for ``feature``: ``circular`` for an azimuth, else
    ``linear``, plus ``log`` unless the values are quantised (no log bin fits a quantum)."""
    if feature.circular:
        return ["circular"]
    if feature.quantised_in(coord_system):
        return ["linear"]
    return ["linear", "log"]


def flags(feature: Feature, coord_system: str) -> list[str]:
    """The flag vocabulary the interface keys its notices on."""
    out: list[str] = []
    if feature.circular:
        out.append("circular")
    if feature.partly_circular:
        out.append("partly_circular")
    if feature.eps == EPS_OWN:
        out.append("floored_at_eps")
    elif feature.eps == EPS_VOLUME:
        out.append("floored_factor")
    quantum = feature.quantised_in(coord_system)
    if quantum == QUANTUM_LAYER:
        out.append("lattice_quantised")
    elif quantum == QUANTUM_COUNT:
        out.append("integer")
    if feature.irregular_lattice:
        out.append("irregular_lattice")
    if feature.energy_weighted:
        out.append("energy_weighted")
    if feature.raw_z and coord_system == "lab":
        out.append("raw_z")
    if display_offset(feature, coord_system) is not None:
        out.append("display_offset")
    if feature.hit_kinds_only:
        out.append("hit_kinds_only")
    if not feature.notebook:
        out.append("not_a_notebook_feature")
    return out


def entry(feature: Feature, coord_system: str, full: bool = False) -> dict[str, Any]:
    """The feature as the payloads list it; ``full`` adds the long description."""
    out: dict[str, Any] = {
        "id": feature.id,
        "label": label(feature, coord_system),
        "unit": feature.unit,
        "flags": flags(feature, coord_system),
        "circular": feature.circular,
        "display_offset": display_offset(feature, coord_system),
        "scales": scales(feature, coord_system),
        "hatched": HATCHED.get(feature.id),
        "notebook": feature.notebook,
    }
    if full:
        out["description"] = feature.description
        out["frame_dependent"] = feature.frame_dependent
        out["quantum"] = feature.quantised_in(coord_system)
    return out


# ------------------------------------------------------------------- SQL --


def _events_column(feature: Feature, coord_system: str) -> str:
    """The aggregated kind's column of ``feature``: the file's own name."""
    if feature.id in _EVENTS_BASE:
        name = _EVENTS_BASE[feature.id]
    else:
        name = f"{feature.id}{ddl.FEATURE_SUFFIX[frame_code(coord_system)]}"
    if name not in _EVENTS_COLUMNS:
        raise ValueError(f"the aggregate has no column for {feature.id!r} in {coord_system!r}")
    return name


def _circular_mean_sql(frame: str, shower: ShowerColumns) -> str:
    c, s = shower.group1("sum_cos_phi", frame), shower.group1("sum_sin_phi", frame)
    return (f"CASE WHEN {c} = 0 AND {s} = 0 THEN NULL "
            f"ELSE {group1.circular_mean_sql(frame, shower.key)} END")


def _spread_circ_sql(frame: str, shower: ShowerColumns) -> str:
    """SD(θ) + √(−2 ln R̄) of φ; core.py's zero branch (every hit at the origin) kept."""
    resultant = group1.resultant_sql(frame, shower.key)
    return (f"CASE WHEN {shower.group1('sum_r', frame)} = 0 THEN 0.0 "
            f"WHEN {resultant} <= 0 THEN NULL "
            f"ELSE {shower.group1('sd_theta', frame)} "
            f"+ sqrt(greatest(0.0, -2.0 * ln(least({resultant}, 1.0)))) END")


def column_sql(kind: str | None, feature: Feature, coord_system: str,
               shower: ShowerColumns) -> str:
    """The SQL expression of one feature of one shower in one frame, from allowlisted names."""
    if kind == ddl.KIND_SINGLE_EVENTS:
        if feature.hit_kinds_only:
            raise ValueError(f"{feature.id!r} is not offered for the aggregated kind")
        return _events_column(feature, coord_system)
    frame = frame_code(coord_system)
    if feature.id == "num_hits":
        return shower.group1("n_hits")
    if feature.id == "total_hit_energy":
        return shower.group1("e_dep")
    if feature.id == "avg_phi_circ":
        return _circular_mean_sql(frame, shower)
    if feature.id == "angular_spread_circ":
        return _spread_circ_sql(frame, shower)
    return group1.feature_sql(feature.id, frame, shower.key)


def hits_sql(kind: str | None, shower: ShowerColumns) -> str:
    """The shower's hit count, the column the minimum-hits rule reads."""
    if kind == ddl.KIND_SINGLE_EVENTS:
        return _EVENTS_BASE["num_hits"]
    return shower.group1("n_hits")


def label_sql(kind: str | None) -> str | None:
    """The stored class label, on the aggregated kind only (``energy_class``)."""
    return "energy_class" if kind == ddl.KIND_SINGLE_EVENTS else None


def select_list(kind: str | None, coord_system: str,
                shower: ShowerColumns) -> list[tuple[str, str]]:
    """``(feature id, SQL)`` for every offered feature, cast to DOUBLE."""
    return [(f.id, f"CAST({column_sql(kind, f, coord_system, shower)} AS DOUBLE)")
            for f in offered(kind)]
