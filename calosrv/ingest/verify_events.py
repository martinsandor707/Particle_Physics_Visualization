"""Post-ingest assertions for an aggregated (event-features-only) experiment.

Nothing here recomputes a feature - the hits are not in the file. What can be
checked is the file's internal consistency: the densities are the hit count
and the energy over the volume in every frame, the translated frame's extents
equal the absolute frame's (a translation preserves widths), and the features
core.py floors at 10⁻⁶ are counted so the explorer can say where a value is
the floor rather than a measurement. The trailing ``energy`` column is
checked against the rule 1{p ≥ 2 GeV} and the bin column against ⌊p⌋.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from ..db import naming
from ..db.ddl import FEATURE_SUFFIX
from ..db.naming import quote
from .derive_features import FeatureReport
from .verify import SUM_TOLERANCE, VerificationResult, _exceeds, check_energy, check_rows

log = logging.getLogger(__name__)

#: The label rule observed on the electron aggregate.
LABEL_THRESHOLD_GEV = 2.0
#: core.py's floor on width, height, depth and depth_range.
EPS = 1e-6


def verify_events(
    con: duckdb.DuckDBPyConnection,
    name: str,
    source: Path | None,
    archive_source: str,
    archive_rows: int,
    part_rows: int | None = None,
    source_format: str = "csv",
    report: FeatureReport | None = None,
) -> VerificationResult:
    """Check an aggregated experiment's archive and feature table."""
    result = VerificationResult()
    event = quote(naming.event_table(name))
    n_parquet = check_rows(result, con, source, archive_source, archive_rows, part_rows,
                           source_format)
    if n_parquet == 0:
        return result
    n_events = int(con.execute(f"SELECT count(*) FROM {event}").fetchone()[0])
    result.values["events"] = n_events
    if n_events == n_parquet:
        result.passed("event_count")
    else:
        result.fail("event_count",
                    f"The feature table holds {n_events:,} events for {n_parquet:,} file rows.")
    check_energy(result, con, name)

    if report and report.non_finite:
        result.notice("non_finite_values",
                      "Non-finite values stored as undefined (NULL): "
                      + ", ".join(f"{c} ({n:,})" for c, n in sorted(report.non_finite.items())) + ".")
    else:
        result.passed("non_finite_values")

    residuals, floors, invariants = [], [], []
    for code, suffix in FEATURE_SUFFIX.items():
        volume = f"volume{suffix}"
        residuals += [
            f"max(abs(numerical_density{suffix} * {volume} - n_hits) / n_hits)",
            f"max(abs(energy_density{suffix} * {volume} - e_dep) / e_dep)",
        ]
        floors.append(" + ".join(
            f"count(*) FILTER (WHERE {f}{suffix} <= {EPS!r})"
            for f in ("width", "height", "depth", "depth_range")))
    # Equal to rounding: x_trans = x - P0 moves both ends of a range by the
    # same float, which can leave the difference a few ulps apart.
    for a, b in (("width_trans", "width"), ("height_trans", "height"),
                 ("depth_range_trans", "depth_range"), ("depth_trans", "depth_range_trans")):
        invariants.append(
            f"count(*) FILTER (WHERE ({a} IS NULL) <> ({b} IS NULL) "
            f"OR abs({a} - {b}) > {SUM_TOLERANCE!r} * greatest(abs({b}), 1e-300))")
    row = con.execute(
        f"SELECT greatest({', '.join(residuals)}), {', '.join(floors)}, "
        f"{' + '.join(invariants)}, "
        f"count(*) FILTER (WHERE energy_class IS NULL), "
        f"count(*) FILTER (WHERE energy_class = 0), count(*) FILTER (WHERE energy_class = 1), "
        f"count(*) FILTER (WHERE energy_class IS DISTINCT FROM "
        f"CAST(e1 >= {LABEL_THRESHOLD_GEV!r} AS UTINYINT)), "
        f"count(*) FILTER (WHERE e1_bin <> CAST(floor(e1) AS INTEGER)) "
        f"FROM {event}"
    ).fetchone()
    density, floor_abs, floor_trn, floor_loc, broken, no_label, zero, one, off_rule, off_bin = row
    result.values.update(density_residual=density,
                         eps_floors={"abs": int(floor_abs), "trn": int(floor_trn),
                                     "loc": int(floor_loc)})
    if _exceeds(density, SUM_TOLERANCE):
        result.warn("density_consistency",
                    f"A density differs from its count or energy over the volume by up to "
                    f"{density:.3g} relative.")
    else:
        result.passed("density_consistency")
    if floor_abs or floor_trn or floor_loc:
        result.notice("eps_floor",
                      f"Extents at core.py's 10⁻⁶ floor (a single layer or column, not a "
                      f"measurement): {int(floor_abs):,} absolute, {int(floor_trn):,} translated, "
                      f"{int(floor_loc):,} local.")
    if broken:
        result.warn("trans_invariants",
                    f"{int(broken):,} value(s) break the translation invariants (translated "
                    "width, height and depth range equal the absolute ones, to 10⁻⁹).")
    else:
        result.passed("trans_invariants")
    if no_label:
        result.notice("label_rule",
                      f"The trailing 'energy' column is not a small whole number on "
                      f"{int(no_label):,} row(s); it is kept in the archive and not interpreted.")
    elif off_rule:
        result.notice("label_rule",
                      f"The trailing 'energy' column is a class label (0 in {int(zero):,} events, "
                      f"1 in {int(one):,}) that departs from 1{{p ≥ {LABEL_THRESHOLD_GEV:g} GeV}} "
                      f"in {int(off_rule):,} event(s).")
    else:
        result.notice("label_rule",
                      f"The trailing 'energy' column is the class label 1{{p ≥ "
                      f"{LABEL_THRESHOLD_GEV:g} GeV}} (0 in {int(zero):,} events, 1 in "
                      f"{int(one):,}); it is stored as energy_class.")
    if off_bin:
        result.notice("momentum_bin_rule",
                      f"incoming_momentum_bin differs from ⌊incoming_momentum⌋ in "
                      f"{int(off_bin):,} event(s); it is kept as written.")
    else:
        result.notice("momentum_bin_rule", "incoming_momentum_bin is ⌊incoming_momentum⌋ in every event.")
    log.info("Verification for %r: %s (%s)", name, "PASSED" if result.ok else "FAILED",
             ", ".join(f"{k}={v}" for k, v in sorted(result.checks.items())))
    return result
