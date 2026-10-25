"""What an experiment can serve: the one owner of every per-experiment gate.

``GET /api/experiments`` publishes the block :func:`describe` builds, the
interface builds its pages from it, and every route checks it through
:func:`require` - so a view the data cannot serve is refused with a sentence
naming why (422, ``/problems/unsupported-capability``) instead of failing
inside a query. Panel ids are the interface's card ids, so one table here
decides both what a card shows and what its route answers.

Three things decide a gate: the experiment's kind (two showers with networks,
one shower with hits and species, or event-level features only), what was
measured at ingest (a lattice, the per-shower frame extents), and whether its
derived tables are current - a two-shower experiment ingested before the
Group-1 columns and the layer and profile tables existed is served as before,
with the panels that need those tables off until it is rebuilt.

A single-shower experiment reuses the two-shower query code with shower ``a``
only. Each such reuse is enabled in :data:`SINGLE_SHOWER_READY` by the change
that makes the query layer handle one shower, never before it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..db import ddl, schemas
from ..db.registry import ExperimentRecord
from ..errors import CapabilityError
from . import planes as planes_mod

#: The reference frames, as the API names them, in the interface's order.
FRAME_KINDS: tuple[str, ...] = ("lab", "trans", "local", "canonical")

#: Page 1 cards: the 2 x 2 diagnostic and the physics section.
PAGE1_CARDS: tuple[str, ...] = (
    "xy", "yz", "xz", "energy",
    "profile-w", "profile-r",
    "response-b1", "response-b2", "response-res", "response-b3",
    "distribution", "correlation", "statistics",
)

#: Page 2 cards.
PAGE2_CARDS: tuple[str, ...] = (
    "perf-bins", "pred-truth", "pred-residuals",
    "feat-table", "feat-corr", "feat-hist", "feat-hist2d",
    "prim-rate", "vox-event", "vox-ensemble",
)

#: Gates that are not a card of their own: a voxel channel, a route serving an
#: existing view, a frame, and the deferred XGBoost views.
OTHER_GATES: tuple[str, ...] = (
    "vox-species", "vox-attention", "negative-depth",
    "window-axis", "event-inspector", "compare",
    "frame-lab", "frame-trans", "frame-local", "frame-canonical",
    "xgboost",
)

ALL_GATES: tuple[str, ...] = PAGE1_CARDS + PAGE2_CARDS + OTHER_GATES

#: Gates whose query code handles a single-shower experiment. A gate is added
#: here by the change that teaches its queries to read one shower.
SINGLE_SHOWER_READY: frozenset[str] = frozenset({
    # Page 1 physics cards: written per kind from the start.
    "response-b1", "response-b2", "response-res", "response-b3",
    "profile-w", "profile-r", "distribution", "correlation", "statistics", "negative-depth",
    # Page 2 cards that read the event table or Group-1.
    "feat-table", "feat-corr", "feat-hist", "feat-hist2d", "prim-rate",
    # The 2 x 2 diagnostic's spatial panels in the absolute, per-shower
    # translated and local frames, and the views built on them.
    "xy", "yz", "xz", "frame-lab", "frame-trans", "frame-local",
    "window-axis", "event-inspector", "compare",
})

#: Gates whose route exists in this release. A card's gate stays shut, with
#: :data:`_NOT_IMPLEMENTED` as its reason, until the change that lands its
#: route adds it here, so the catalogue never advertises a view that 404s.
IMPLEMENTED: frozenset[str] = frozenset({
    "xy", "yz", "xz", "energy",
    "window-axis", "event-inspector", "compare",
    "frame-lab", "frame-trans", "frame-local", "frame-canonical",
    # Page 1 physics cards.
    "response-b1", "response-b2", "response-res", "response-b3",
    "profile-w", "profile-r", "distribution", "correlation", "statistics", "negative-depth",
    # Page 2 cards.
    "perf-bins", "pred-truth", "pred-residuals",
    "feat-table", "feat-corr", "feat-hist", "feat-hist2d", "prim-rate",
})

_NO_HITS = "This experiment holds event-level features only (the 59-column aggregate): it has no hits."
_NO_NETWORKS = (
    "This experiment carries no reconstruction-network outputs; network panels need the "
    "hits_all_models schema."
)
_ONE_SHOWER_DFRAME = (
    "Needs two showers per event: the Separation-Aligned (D-Frame) is built from the A→B "
    "separation of the two entry points."
)
_NO_SPECIES = (
    "Needs the particle_type and is_secondary columns of the single-shower hit files; the "
    "two-shower export does not carry them (TODO.md, item 5)."
)
_NO_LATTICE = "No detector lattice was measured for this experiment."
_NO_FRAME_BOUNDS = "The per-shower frame extents were not measured for this experiment."
_XGBOOST = "No precomputed XGBoost model-run artefacts are loaded (see TODO.md)."
_NOT_YET_SINGLE = "Not yet available for single-shower experiments."
_NOT_IMPLEMENTED = "Not served by this release yet."


def _stale(record: ExperimentRecord) -> str:
    return (
        f"Built by an earlier release (derived tables v{record.derived_version or 1}); the "
        "per-event feature columns and the layer and profile tables it needs exist after a "
        "rebuild from the experiment's archive (Admin Settings › Rebuild derived tables)."
    )


@dataclass(frozen=True)
class Capabilities:
    """One experiment's gates, and the lists the catalogue publishes."""

    kind: str | None
    traits: schemas.KindTraits | None
    frames: tuple[str, ...]
    coord_systems: tuple[str, ...]
    models: tuple[str, ...]
    channels: tuple[str, ...]
    gates: dict[str, bool]
    reasons: dict[str, str]
    derived: dict[str, Any]
    measured: dict[str, Any] = field(default_factory=dict)

    def can(self, gate: str) -> bool:
        return bool(self.gates.get(gate, False))

    @property
    def showers(self) -> tuple[str, ...]:
        return self.traits.showers if self.traits is not None else ()

    @property
    def filters(self) -> tuple[str, ...]:
        return self.traits.filter_axes if self.traits is not None else ("e1", "e2", "d")

    def as_dict(self) -> dict[str, Any]:
        traits = self.traits
        group1_frames = ["lab", "trans", "local"] if self.gates.get("feat-table") else []
        return {
            "kind": self.kind,
            "kind_label": traits.label if traits else None,
            "n_showers": len(self.showers),
            "showers": list(self.showers),
            "has_hits": bool(traits and traits.has_hits),
            "has_lattice": self.gates.get("frame-lab", False) or bool(self.measured.get("lattice")),
            "has_frame_bounds": bool(self.measured.get("frame_bounds")),
            "networks": list(self.models),
            "species": self.can("vox-species"),
            "filters": list(self.filters),
            "group1_frames": group1_frames,
            "model_runs": [],
            "pages": {
                "physics": any(self.gates.get(c) for c in PAGE1_CARDS),
                "spatial": any(self.gates.get(c) for c in ("xy", "yz", "xz")),
                "models": any(self.gates.get(c) for c in PAGE2_CARDS),
            },
            "panels": {gate: bool(self.gates.get(gate)) for gate in ALL_GATES},
            "reasons": dict(self.reasons),
            "derived": dict(self.derived),
            "measured": {k: v for k, v in self.measured.items() if k not in ("lattice", "frame_bounds")},
        }


def of(record: ExperimentRecord) -> Capabilities:
    """The gates of one experiment. Pure: reads the registry record, runs no SQL."""
    kind = record.kind
    traits = record.traits
    gates = {gate: False for gate in ALL_GATES}
    reasons: dict[str, str] = {}

    def gate(name: str, ok: bool, reason: str | None = None) -> None:
        gates[name] = bool(ok)
        if not ok and reason:
            reasons.setdefault(name, reason)

    derived = {
        "version": record.derived_version or 1,
        "current": schemas.DERIVED_VERSION.get(kind, 1) if kind else None,
        "status": record.derived_status,
        "notice": _stale(record) if record.derived_status == "stale" else None,
    }
    measured = dict(record.capabilities or {})
    measured["lattice"] = record.lattice is not None
    measured["frame_bounds"] = record.frame_bounds is not None

    if not record.is_ready or traits is None:
        why = f"Not ready (status: {record.status})." if not record.is_ready else (
            "The experiment's schema is not served by this release.")
        for name in ALL_GATES:
            gate(name, False, why)
        return Capabilities(kind, traits, (), (), (), (), gates, reasons, derived, measured)

    two = kind == ddl.KIND_TWO_SHOWER
    single = kind == ddl.KIND_SINGLE_HITS
    hits = traits.has_hits
    lattice = hits and record.lattice is not None
    bounds = hits and record.frame_bounds is not None
    current = record.derived_status == "current"
    networks = traits.has_networks

    def single_ready(name: str) -> bool:
        return two or (single and name in SINGLE_SHOWER_READY)

    def hit_gate(name: str, ok: bool, reason: str) -> None:
        if not hits:
            gate(name, False, _NO_HITS)
        elif not single_ready(name):
            gate(name, False, _NOT_YET_SINGLE)
        else:
            gate(name, ok, reason)

    # Frames.
    hit_gate("frame-lab", lattice, _NO_LATTICE)
    hit_gate("frame-trans", bounds, _NO_FRAME_BOUNDS)
    hit_gate("frame-local", bounds, _NO_FRAME_BOUNDS)
    if single:
        gate("frame-canonical", False, _ONE_SHOWER_DFRAME)
    else:
        hit_gate("frame-canonical", lattice, _NO_LATTICE)

    # The 2 x 2 diagnostic and the views built on the lab lattice.
    for name in ("xy", "yz", "xz", "window-axis"):
        hit_gate(name, lattice, _NO_LATTICE)
    # The Event Inspector draws the per-shower frames beside the lab lattice,
    # so it needs their extents as well.
    hit_gate("event-inspector", lattice and bounds, _NO_LATTICE if not lattice else _NO_FRAME_BOUNDS)
    hit_gate("compare", bounds, _NO_FRAME_BOUNDS)
    if networks:
        gate("energy", True)
    else:
        gate("energy", False, _NO_NETWORKS)

    # Physics section. The response cards read the event table of any kind.
    for name in ("response-b1", "response-b2", "response-res", "response-b3"):
        gate(name, two or single_ready(name) or kind == ddl.KIND_SINGLE_EVENTS, _NOT_YET_SINGLE)
    # Distributions: θ, φ and p come from the event table of every kind; the
    # route refuses the hit quantities where there are no hits.
    gate("distribution", two or single_ready("distribution") or kind == ddl.KIND_SINGLE_EVENTS,
         _NOT_YET_SINGLE)
    hit_gate("correlation", True, "")
    hit_gate("statistics", True, "")
    for name in ("profile-w", "profile-r", "negative-depth"):
        hit_gate(name, current, _stale(record))

    # Page 2.
    for name in ("perf-bins", "pred-truth", "pred-residuals"):
        gate(name, networks, _NO_NETWORKS)
    for name in ("feat-table", "feat-corr", "feat-hist", "feat-hist2d"):
        if kind == ddl.KIND_SINGLE_EVENTS:
            gate(name, True)
        else:
            hit_gate(name, current, _stale(record))
    hit_gate("vox-event", lattice, _NO_LATTICE)
    hit_gate("vox-ensemble", bounds, _NO_FRAME_BOUNDS)
    gate("vox-attention", networks and gates["vox-ensemble"], _NO_NETWORKS)
    gate("vox-species", traits.has_species and gates["vox-event"],
         _NO_SPECIES if not traits.has_species else _NOT_YET_SINGLE)
    gate("prim-rate", traits.has_species and single_ready("prim-rate"),
         _NO_SPECIES if not traits.has_species else _NOT_YET_SINGLE)
    gate("xgboost", False, _XGBOOST)
    for name in ALL_GATES:
        if gates[name] and name not in IMPLEMENTED:
            gate(name, False, _NOT_IMPLEMENTED)

    frames = tuple(f for f in FRAME_KINDS if gates[f"frame-{f}"])
    coord_systems = tuple(c for c in ddl.COORD_SYSTEMS if gates[f"frame-{c}"])
    models = tuple(ddl.MODELS) if networks else ()
    if networks and hits:
        channels = tuple(planes_mod.CHANNELS)
    elif hits and frames:
        channels = ("density",)
    else:
        channels = ()
    return Capabilities(kind, traits, frames, coord_systems, models, channels,
                        gates, reasons, derived, measured)


def require(record: ExperimentRecord, *gates: str, field: str = "table_name") -> Capabilities:
    """Refuse the request unless every gate is open; return the capabilities."""
    caps = of(record)
    for name in gates:
        if name not in ALL_GATES:
            raise ValueError(f"unknown capability {name!r}")
        if not caps.can(name):
            reason = caps.reasons.get(name, "Not available for this experiment.")
            raise CapabilityError(
                f"{name} is not available for experiment {record.table_name!r}: {reason}",
                field=field, capability=name, kind=caps.kind, reason=reason,
                table_name=record.table_name,
            )
    return caps


def require_choice(
    record: ExperimentRecord, field: str, value: str, offered: Sequence[str], capability: str
) -> None:
    """Refuse a frame, model or channel the experiment does not offer."""
    if value not in offered:
        caps = of(record)
        reason = caps.reasons.get(capability) or (
            f"it offers {', '.join(offered)}." if offered else "it offers none.")
        raise CapabilityError(
            f"{field}={value!r} is not available for experiment {record.table_name!r}: {reason}",
            field=field, capability=capability, kind=caps.kind, reason=reason,
            table_name=record.table_name,
        )


def frame_gate(record: ExperimentRecord) -> str:
    """The event-table predicate an event needs to be placed in its per-shower frames."""
    if record.kind == ddl.KIND_TWO_SHOWER:
        return "d IS NOT NULL"
    return "theta_a IS NOT NULL AND phi_a IS NOT NULL AND p0ax IS NOT NULL"


def warm_kinds(record: ExperimentRecord) -> tuple[str, ...]:
    """The cached bundles worth warming for this experiment after ingest or at boot."""
    caps = of(record)
    kinds: list[str] = []
    if caps.can("frame-canonical"):
        kinds.append("canonical")
    if caps.can("frame-trans"):
        kinds.append("trans")
    if caps.can("frame-local"):
        kinds.append("local")
    return tuple(kinds)
