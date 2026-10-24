"""The derive recipe of each experiment kind: which tables, in which order, checked how.

Everything after the archive is per kind. ``pipeline.run_ingest`` and
``pipeline.rebuild`` hand a :class:`DeriveContext` to :func:`derive`, which
dispatches on the input schema's kind:

* **two-shower hits** - lattice, projection, event table with Group-1, layers,
  profiles, preview sample, verification (derived version 2);
* **single-shower hits** - the same tables in the single-shower layout, plus
  the species facts the catalogue advertises (derived version 1);
* **single-shower events** - the feature table alone: no hits, no lattice.

Each stage reports through ``progress(stage, kind)`` and the stopwatch, so a
job shows real progress and the ingest report shows which stage set the
memory peak.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..config import Settings
from ..db import archive, registry, schemas
from ..db.ddl import KIND_SINGLE_EVENTS, KIND_SINGLE_HITS, KIND_TWO_SHOWER
from ..db.naming import event_table, quote
from ..db.schemas import InputSchema
from ..errors import IngestError
from . import (
    derive_events, derive_events_single, derive_features, derive_layers, derive_profiles,
    derive_proj, formats, lattice_fit, verify as verify_mod, verify_events, verify_single,
)
from .result import IngestResult, _Stopwatch
from .source_check import SourceCheck

log = logging.getLogger(__name__)

#: Ordered stages per kind, as (key, label, weight). The weights are rough
#: shares of wall time and only turn a stage into a percentage.
STAGES_BY_KIND: dict[str, tuple[tuple[str, str, float], ...]] = {
    KIND_TWO_SHOWER: (
        ("archive", "Writing the Parquet archive", 0.42),
        ("lattice", "Measuring the detector lattice", 0.03),
        ("projection", "Building the projection table", 0.16),
        ("events", "Building per-event statistics", 0.15),
        ("layers", "Building the per-layer table", 0.03),
        ("profiles", "Splatting the depth and radial profiles", 0.10),
        ("sample", "Building the preview sample", 0.03),
        ("verify", "Verifying the ingested data", 0.08),
    ),
    KIND_SINGLE_HITS: (
        ("archive", "Writing the Parquet archive (sorted by event)", 0.25),
        ("lattice", "Measuring the detector lattice", 0.02),
        ("projection", "Building the projection table", 0.10),
        ("events", "Building per-event statistics", 0.15),
        ("layers", "Building the per-layer table", 0.03),
        ("profiles", "Splatting the depth and radial profiles", 0.30),
        ("sample", "Building the preview sample", 0.02),
        ("verify", "Verifying the ingested data", 0.13),
    ),
    KIND_SINGLE_EVENTS: (
        ("archive", "Writing the Parquet archive", 0.50),
        ("features", "Building the event feature table", 0.30),
        ("verify", "Verifying the ingested data", 0.20),
    ),
}


def stages(kind: str | None, rebuild: bool = False) -> tuple[tuple[str, str, float], ...]:
    """The stage table of ``kind``; a rebuild drops the archive stage and renormalises."""
    table = STAGES_BY_KIND.get(kind or KIND_TWO_SHOWER, STAGES_BY_KIND[KIND_TWO_SHOWER])
    if not rebuild:
        return table
    rest = tuple(s for s in table if s[0] != "archive")
    total = sum(weight for *_, weight in rest) or 1.0
    return tuple((key, label, weight / total) for key, label, weight in rest)


@dataclass
class DeriveContext:
    con: duckdb.DuckDBPyConnection
    settings: Settings
    record: registry.ExperimentRecord
    schema: InputSchema
    source: Path | None
    manifest: archive.Manifest
    build_sample: bool
    watch: _Stopwatch
    progress: Callable[[str, str], None]
    part_rows: int | None = None
    check: SourceCheck | None = None

    @property
    def kind(self) -> str:
        return self.schema.kind

    @property
    def name(self) -> str:
        return self.record.table_name

    @property
    def relation(self) -> str:
        return archive.relation_sql(archive.part_paths(self.settings, self.name, self.manifest))

    def stage(self, key: str) -> None:
        self.progress(key, self.kind)

    @property
    def source_format(self) -> str:
        return self.check.format if self.check else formats.CSV


def derive(ctx: DeriveContext) -> IngestResult:
    """Build and verify every derived table of the context's kind."""
    recipe = {
        KIND_TWO_SHOWER: derive_two_shower,
        KIND_SINGLE_HITS: derive_single_hits,
        KIND_SINGLE_EVENTS: derive_single_events,
    }.get(ctx.kind)
    if recipe is None:
        raise IngestError(f"No derive recipe for experiment kind {ctx.kind!r}.")
    ctx.record.schema_name, ctx.record.schema_version = ctx.schema.name, ctx.schema.version
    return recipe(ctx)


# ------------------------------------------------------------- shared steps --

def _lattice(ctx: DeriveContext):
    ctx.stage("lattice")
    lattice = lattice_fit.measure_lattice(ctx.con, ctx.relation)
    pitch = lattice_fit.layer_pitch(lattice.z.coords)
    # Persist the lattice before the derived tables are verified: the
    # lattice-bounds check reads it, and would otherwise skip itself silently.
    ctx.record.lattice = lattice
    registry.upsert(ctx.con, ctx.record)
    ctx.watch.mark("lattice")
    return lattice, pitch


def _layers_and_profiles(ctx: DeriveContext, pitch: float, footprint) -> dict[str, Any]:
    ctx.stage("layers")
    derive_layers.build(ctx.con, ctx.name, ctx.relation, pitch, ctx.kind)
    ctx.watch.mark("layers")
    ctx.stage("profiles")
    profiles = derive_profiles.build(ctx.con, ctx.name, ctx.relation, pitch, footprint, ctx.kind)
    ctx.watch.mark("profiles")
    return profiles


def _sample(ctx: DeriveContext) -> int:
    if not ctx.build_sample:
        return 0
    ctx.stage("sample")
    rows = derive_proj.build_sample(ctx.con, ctx.name, ctx.settings.sample_percent)
    ctx.watch.mark("sample")
    return rows


def momentum_bins(con: duckdb.DuckDBPyConnection, name: str, two: bool) -> dict[str, Any]:
    """The producer's momentum bins present, and how many events depart from ⌊p⌋."""
    columns = (("e1", "e1_bin"), ("e2", "e2_bin")) if two else (("e1", "e1_bin"),)
    parts = []
    for p, b in columns:
        parts += [f"min({b})", f"max({b})",
                  f"count(*) FILTER (WHERE {b} <> CAST(floor({p}) AS INTEGER))"]
    row = con.execute(f"SELECT {', '.join(parts)} FROM {quote(event_table(name))}").fetchone()
    lo = min(v for v in row[0::3] if v is not None) if any(v is not None for v in row[0::3]) else None
    hi = max(v for v in row[1::3] if v is not None) if any(v is not None for v in row[1::3]) else None
    off = int(sum(int(v or 0) for v in row[2::3]))
    return {"lo": lo, "hi": hi, "n_off_rule": off,
            "rule": "floor(p)" if off == 0 else "as written by the producer"}


def _finish(ctx: DeriveContext, result: IngestResult, *, sanitation: dict[str, Any],
            calibration: dict[str, Any], pitch: float | None,
            verification: verify_mod.VerificationResult) -> IngestResult:
    """Fill the registry record from what the recipe measured, and store it."""
    record = ctx.record
    record.archive_dir = archive.relative_dir(ctx.name)
    record.archive_parts = len(ctx.manifest.parts)
    record.archive_rows = ctx.manifest.rows
    record.archive_bytes = ctx.manifest.bytes
    record.derived_version = schemas.DERIVED_VERSION[ctx.kind]
    # A rebuild reads no source, so it keeps what the last ingest said about it.
    source_report = (ctx.check.as_dict() if ctx.check
                     else (record.ingest_report or {}).get("source"))
    record.ingest_report = {
        "sanitation": sanitation,
        "calibration": calibration,
        "timings": ctx.watch.stages,
        "verification": verification.as_dict(),
        "layer_pitch_mm": pitch,
        "source": source_report,
    }
    record.status = registry.STATUS_READY if verification.ok else registry.STATUS_FAILED
    record.error = None if verification.ok else "; ".join(verification.warnings)
    registry.upsert(ctx.con, record)
    result.verification = verification
    result.timings = ctx.watch.stages
    result.sanitation = sanitation
    result.calibration = calibration
    result.notices = list(ctx.check.notices) if ctx.check else []
    return result


def _apply_bounds(record: registry.ExperimentRecord, bounds: dict[str, Any]) -> None:
    record.n_events_no_d = bounds["n_events_no_d"]
    record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
    record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
    record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
    record.overlaps = bounds["overlaps"]


# ---------------------------------------------------------------- recipes --

def derive_two_shower(ctx: DeriveContext) -> IngestResult:
    con, name, record = ctx.con, ctx.name, ctx.record
    lattice, pitch = _lattice(ctx)

    ctx.stage("projection")
    sanitation = derive_proj.build(con, name, ctx.relation, pitch)
    ctx.watch.mark("projection")

    ctx.stage("events")
    n_events = derive_events.build(con, name, ctx.relation)
    calibration = derive_events.calibration(con, name)
    bounds = lattice_fit.measure_bounds(con, name)
    frame_bounds = lattice_fit.measure_frame_bounds(con, name, pitch)
    cell_e_max, cell_e_p999 = derive_proj.measure_color_anchors(con, name, lattice.slab_iz)
    footprint = lattice_fit.measure_footprint(con, name, lattice)
    ctx.watch.mark("events")

    profiles = _layers_and_profiles(ctx, pitch, footprint)
    sample_rows = _sample(ctx)

    ctx.stage("verify")
    verification = verify_mod.verify(
        con, name, ctx.source, ctx.relation, ctx.manifest.rows, pitch, part_rows=ctx.part_rows,
        lattice_n=(lattice.x.n, lattice.y.n, lattice.z.n),
        depth_mm=float(lattice.z.hi - lattice.z.lo),
        source_format=ctx.source_format, lattice=lattice, removed_rows=sanitation.removed,
    )
    verify_mod.check_derived(verification, con, name, ("a", "b"), profiles)
    bins = momentum_bins(con, name, two=True)
    if bins["n_off_rule"]:
        verification.warn("momentum_bin_rule",
                          f"incoming_momentum_bin_A/B differ from ⌊incoming_momentum⌋ in "
                          f"{bins['n_off_rule']:,} shower(s); the bins are kept as written.")
    ctx.watch.mark("verify")

    counts = con.execute(
        "SELECT coalesce(sum(n_cells), 0), coalesce(sum(n_split_cells), 0), "
        f"coalesce(sum(n_ab_rows), 0) FROM {quote(event_table(name))}"
    ).fetchone()
    record.n_hits = sanitation.kept_rows
    record.n_events = n_events
    _apply_bounds(record, bounds)
    record.cell_e_max, record.cell_e_p999 = cell_e_max, cell_e_p999
    record.has_sample = sample_rows > 0
    record.n_cells, record.n_split_cells, record.n_ab_rows = (int(v) for v in counts)
    record.frame_bounds = frame_bounds
    record.capabilities = {
        "footprint_mm": [float(v) for v in footprint],
        "profiles": {k: profiles[k] for k in ("k", "k_z", "w_bin_mm", "r_bin_mm", "r_bins",
                                              "comb", "neg_depth_mm")},
        "momentum_bins": bins,
    }
    calibration_report = {code: {"c_a": c_a, "c_b": c_b} for code, (c_a, c_b) in calibration.items()}
    result = IngestResult(record=record, n_hits=record.n_hits, n_events=n_events)
    return _finish(ctx, result, sanitation=sanitation.as_dict(), calibration=calibration_report,
                   pitch=pitch, verification=verification)


def derive_single_hits(ctx: DeriveContext) -> IngestResult:
    con, name, record = ctx.con, ctx.name, ctx.record
    lattice, pitch = _lattice(ctx)

    ctx.stage("projection")
    sanitation = derive_proj.build(con, name, ctx.relation, pitch, ctx.kind)
    ctx.watch.mark("projection")

    ctx.stage("events")
    n_events = derive_events_single.build(con, name, ctx.relation)
    calibration = derive_events_single.calibration(con, name)
    bounds = lattice_fit.measure_bounds(con, name, ctx.kind)
    frame_bounds = lattice_fit.measure_frame_bounds(con, name, pitch)
    cell_e_max, cell_e_p999 = derive_proj.measure_color_anchors(con, name, lattice.slab_iz)
    footprint = lattice_fit.measure_footprint(con, name, lattice)
    ctx.watch.mark("events")

    profiles = _layers_and_profiles(ctx, pitch, footprint)
    sample_rows = _sample(ctx)

    ctx.stage("verify")
    verification = verify_single.verify_single(
        con, name, ctx.source, ctx.relation, ctx.manifest.rows, pitch, part_rows=ctx.part_rows,
        lattice_n=(lattice.x.n, lattice.y.n, lattice.z.n),
        depth_mm=float(lattice.z.hi - lattice.z.lo),
        source_format=ctx.source_format, lattice=lattice, removed_rows=sanitation.removed,
        profiles=profiles,
    )
    species = derive_events_single.species_facts(con, name)
    ctx.watch.mark("verify")

    n_cells = con.execute(
        f"SELECT coalesce(sum(n_cells), 0) FROM {quote(event_table(name))}").fetchone()[0]
    record.n_hits = sanitation.kept_rows
    record.n_events = n_events
    _apply_bounds(record, bounds)
    record.cell_e_max, record.cell_e_p999 = cell_e_max, cell_e_p999
    record.has_sample = sample_rows > 0
    record.n_cells, record.n_split_cells, record.n_ab_rows = int(n_cells), 0, 0
    record.frame_bounds = frame_bounds
    record.capabilities = {
        "footprint_mm": [float(v) for v in footprint],
        "profiles": {k: profiles[k] for k in ("k", "k_z", "w_bin_mm", "r_bin_mm", "r_bins",
                                              "comb", "neg_depth_mm")},
        "momentum_bins": momentum_bins(con, name, two=False),
        "species": species,
    }
    calibration_report = {code: {"c_a": c_a, "c_b": c_b} for code, (c_a, c_b) in calibration.items()}
    result = IngestResult(record=record, n_hits=record.n_hits, n_events=n_events)
    return _finish(ctx, result, sanitation=sanitation.as_dict(), calibration=calibration_report,
                   pitch=pitch, verification=verification)


def derive_single_events(ctx: DeriveContext) -> IngestResult:
    con, name, record = ctx.con, ctx.name, ctx.record
    ctx.stage("features")
    n_events, report = derive_features.build(con, name, ctx.relation)
    calibration = derive_features.calibration(con, name)
    bounds = lattice_fit.measure_bounds(con, name, ctx.kind)
    ctx.watch.mark("features")

    ctx.stage("verify")
    verification = verify_events.verify_events(
        con, name, ctx.source, ctx.relation, ctx.manifest.rows, part_rows=ctx.part_rows,
        source_format=ctx.source_format, report=report,
    )
    label = con.execute(
        f"SELECT count(*) FILTER (WHERE energy_class = 0), count(*) FILTER (WHERE energy_class = 1), "
        f"count(*) FILTER (WHERE energy_class IS DISTINCT FROM CAST(e1 >= 2.0 AS UTINYINT)) "
        f"FROM {quote(event_table(name))}"
    ).fetchone()
    ctx.watch.mark("verify")

    record.n_hits = 0
    record.n_events = n_events
    _apply_bounds(record, bounds)
    record.lattice = None
    record.frame_bounds = None
    record.has_sample = False
    record.cell_e_max = record.cell_e_p999 = None
    record.n_cells = record.n_split_cells = record.n_ab_rows = 0
    record.capabilities = {
        "momentum_bins": momentum_bins(con, name, two=False),
        "label": {"column": "energy_class", "rule": "p >= 2 GeV", "holds": int(label[2] or 0) == 0,
                  "counts": {"0": int(label[0] or 0), "1": int(label[1] or 0)}},
        "features": {"source": "file", "circular": ["avg_phi"],
                     "partly_circular": ["angular_spread"]},
    }
    calibration_report = {code: {"c_a": c_a, "c_b": c_b} for code, (c_a, c_b) in calibration.items()}
    result = IngestResult(record=record, n_hits=0, n_events=n_events)
    return _finish(ctx, result, sanitation=report.as_dict(), calibration=calibration_report,
                   pitch=None, verification=verification)
