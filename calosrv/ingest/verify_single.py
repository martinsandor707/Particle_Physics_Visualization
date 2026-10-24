"""Post-ingest assertions for a single-shower hit experiment.

The frame contracts are the two-shower ones with one shower per event: P0
(``x - x_trans``) is one point per event and is the energy-weighted centroid
of the first populated layer, the local coordinates are the translated ones
rotated by the event's own R(θ, φ), and ``z_trans`` sits on whole layers. The
species columns get their own: ``is_secondary`` is 0 or 1, a row with no
parent is exactly a primary-tagged row, and every cell appears once per event.

Findings that describe the data rather than break a contract are notices,
each with its number: how many events carry no primary-tagged row (the C11
headline), how many rows sit at negative depth (C9), single-hit events (whose
SDs are undefined), and whether the producer's momentum bin is ⌊p⌋.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from ..db import naming
from ..db.ddl import NEG_DEPTH_MM
from ..db.naming import quote
from ..grid.lattice import Lattice
from ..text import typographic
from . import frame_checks
from .derive_proj import keep_predicate
from .verify import (
    LAYER_TOLERANCE_MM, P0_TOLERANCE_MM, ROTATION_TOLERANCE_MM, VerificationResult, _exceeds,
    check_derived, check_energy, check_lattice_bounds, check_projection, check_rows,
)

log = logging.getLogger(__name__)


def _archive_checks(con: duckdb.DuckDBPyConnection, source: str, pitch: float) -> dict:
    """One ungrouped scan of the archive over the rows the sanitiser keeps."""
    t, f = "incoming_theta", "incoming_phi"
    xl = f"(x_trans * cos({t}) * cos({f}) + y_trans * cos({t}) * sin({f}) - z_trans * sin({t}))"
    yl = f"(-x_trans * sin({f}) + y_trans * cos({f}))"
    zl = f"(x_trans * sin({t}) * cos({f}) + y_trans * sin({t}) * sin({f}) + z_trans * cos({t}))"
    aggregates = {
        "max_rotation_residual": (
            f"max(greatest(abs(x_local - {xl}), abs(y_local - {yl}), abs(z_local - {zl})))"),
        "max_layer_residual": f"max(abs(z_trans - round(z_trans / {pitch!r}) * {pitch!r}))",
        "bad_secondary": "count(*) FILTER (WHERE is_secondary IS NULL OR is_secondary NOT IN (0, 1))",
        "null_species": "count(*) FILTER (WHERE particle_type IS NULL)",
        "neg_rows": f"count(*) FILTER (WHERE z_local < {NEG_DEPTH_MM!r})",
        "neg_energy": f"coalesce(sum(energy) FILTER (WHERE z_local < {NEG_DEPTH_MM!r}), 0.0)",
        "energy": "sum(energy)",
        "rows": "count(*)",
    }
    names = list(aggregates)
    row = con.execute(
        f"SELECT {', '.join(f'{sql} AS {quote(k)}' for k, sql in aggregates.items())} "
        f"FROM {source} WHERE {keep_predicate(origin=False)}"
    ).fetchone()
    return dict(zip(names, row))


def verify_single(
    con: duckdb.DuckDBPyConnection,
    name: str,
    source: Path | None,
    archive_source: str,
    archive_rows: int,
    layer_pitch_mm: float,
    part_rows: int | None = None,
    lattice_n: tuple[int, int, int] | None = None,
    depth_mm: float | None = None,
    source_format: str = "csv",
    lattice: Lattice | None = None,
    removed_rows: int = 0,
    profiles: dict | None = None,
) -> VerificationResult:
    """Check a single-shower experiment's archive and derived tables."""
    result = VerificationResult()
    event_physical = naming.event_table(name)
    event = quote(event_physical)

    n_parquet = check_rows(result, con, source, archive_source, archive_rows, part_rows,
                           source_format)
    if n_parquet == 0:
        return result
    n_events = check_projection(result, con, name, n_parquet)
    check_lattice_bounds(result, con, name, lattice_n, depth_mm, layer_pitch_mm)
    check_energy(result, con, name)

    row = con.execute(
        f"""SELECT max(chk_p0_spread), max(chk_pt_spread), coalesce(sum(n_dup_cells), 0),
                   coalesce(sum(n_parent_mismatch), 0), coalesce(sum(chk_bin_rule), 0),
                   count(*) FILTER (WHERE chk_bin_rule > 0),
                   count(*) FILTER (WHERE n_primary_rows = 0),
                   count(*) FILTER (WHERE n_hits = 1)
            FROM {event}"""
    ).fetchone()
    p0_spread, pt_spread, dup_cells, mismatch, bin_rows, bin_events, no_primary, single_hit = row
    result.values.update(p0_spread_mm=p0_spread, pt_spread=pt_spread,
                         duplicate_cells=int(dup_cells), events_without_primary=int(no_primary),
                         single_hit_events=int(single_hit))
    if _exceeds(p0_spread, P0_TOLERANCE_MM):
        result.fail("p0_constancy",
                    f"An event's entry point P0 (x - x_trans) varies by up to {p0_spread:.4g} mm "
                    "within the event; the translated frame would not be a rigid shift.")
    else:
        result.passed("p0_constancy")
    if _exceeds(pt_spread, 0.0):
        result.fail("per_event_constancy",
                    f"The incident momentum, angles or bin vary within an event (spread "
                    f"{pt_spread:.4g}).")
    else:
        result.passed("per_event_constancy")
    if dup_cells:
        result.warn("unique_cells",
                    f"{int(dup_cells):,} cell(s) appear more than once within an event; each "
                    "row is meant to be one cell.")
    else:
        result.passed("unique_cells")

    checks = _archive_checks(con, archive_source, layer_pitch_mm)
    rotation = checks["max_rotation_residual"]
    result.values["rotation_residual_mm"] = rotation
    if _exceeds(rotation, ROTATION_TOLERANCE_MM):
        result.fail("local_rotation",
                    f"x/y/z_local differ from R(theta, phi) applied to the translated "
                    f"coordinates by up to {rotation:.4g} mm.")
    else:
        result.passed("local_rotation")
    layer = checks["max_layer_residual"]
    result.values["layer_residual_mm"] = layer
    if _exceeds(layer, LAYER_TOLERANCE_MM):
        result.fail("trans_layers",
                    f"z_trans is off the {layer_pitch_mm} mm layer grid by up to {layer:.4g} mm.")
    else:
        result.passed("trans_layers")
    if checks["bad_secondary"]:
        result.fail("species_domain",
                    f"{int(checks['bad_secondary']):,} row(s) have an is_secondary that is not 0 or 1.")
    elif checks["null_species"]:
        result.warn("species_domain",
                    f"{int(checks['null_species']):,} row(s) carry no particle_type; they are kept "
                    "and drawn as an unknown species.")
    else:
        result.passed("species_domain")
    if mismatch:
        result.warn("primary_tagging",
                    f"{int(mismatch):,} row(s) have a parent_type that disagrees with "
                    "is_secondary (a primary-tagged row has no parent).")
    else:
        result.notice("primary_tagging",
                      f"{int(no_primary):,} of {n_events:,} events "
                      f"({100.0 * int(no_primary) / max(1, n_events):.2f}%) have no primary-tagged "
                      "row (is_secondary = 0); every primary-tagged row has no parent.")
    if bin_rows:
        result.warn("momentum_bin_rule",
                    f"incoming_momentum_bin differs from ⌊incoming_momentum⌋ on {int(bin_rows):,} "
                    f"row(s) in {int(bin_events):,} event(s); the bin column is kept as written.")
    else:
        result.notice("momentum_bin_rule", "incoming_momentum_bin is ⌊incoming_momentum⌋ on every row.")
    neg_rows, rows = int(checks["neg_rows"] or 0), int(checks["rows"] or 0)
    neg_e, energy = float(checks["neg_energy"] or 0.0), float(checks["energy"] or 0.0)
    result.values.update(negative_depth_rows=neg_rows,
                         negative_depth_energy_fraction=neg_e / energy if energy > 0 else None)
    result.notice("negative_depth", typographic(
        f"{neg_rows:,} of {rows:,} kept rows ({100.0 * neg_rows / max(1, rows):.2f}%) lie at "
        f"z_local < {NEG_DEPTH_MM:g} mm, upstream of the entry point along the incident "
        f"direction, carrying {100.0 * neg_e / energy if energy > 0 else 0.0:.2f}% of the energy."))
    if single_hit:
        result.notice("single_hit_events",
                      f"{int(single_hit):,} event(s) have a single hit: their spatial SDs are "
                      "undefined (ddof = 1), and the producer's aggregate omits them.")

    p0_rule = frame_checks.p0_definition_residual(con, archive_source, event_physical, single=True)
    result.values["p0_definition_residual_mm"] = p0_rule["max_mm"]
    result.values["p0_definition_showers"] = p0_rule["n_showers"]
    if p0_rule["n_showers"] == 0:
        result.warn("p0_definition", "No event had an entry point P0 to check against its first layer.")
    elif _exceeds(p0_rule["max_mm"], frame_checks.P0_DEFINITION_TOLERANCE_MM):
        message = typographic(
            f"An event's entry point P0 (x - x_trans) differs from the energy-weighted centroid "
            f"of its first populated layer by up to {p0_rule['max_mm']:.4g} mm "
            f"(x {p0_rule['x']:.4g}, y {p0_rule['y']:.4g}, z {p0_rule['z']:.4g})")
        if removed_rows > 0:
            result.warn("p0_definition",
                        f"{message}; {removed_rows:,} row(s) were removed by the sanitiser, so the "
                        "first-layer rule cannot be confirmed on this file.")
        else:
            result.fail("p0_definition",
                        f"{message}; the per-shower frames are not anchored where the "
                        "documentation says.")
    else:
        result.passed("p0_definition")

    check_derived(result, con, name, ("a",), profiles)
    log.info("Verification for %r: %s (%s)", name, "PASSED" if result.ok else "FAILED",
             ", ".join(f"{k}={v}" for k, v in sorted(result.checks.items())))
    return result
