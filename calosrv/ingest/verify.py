"""Post-ingest assertions.

An ingest that quietly loses rows is worse than one that fails, because nothing
downstream can tell. These checks run after the derived tables are built and
either pass or attach a warning to the experiment record, so a dataset that
behaved unexpectedly is visible in the interface rather than only in a log.

Besides row accounting, they check the *contracts* the per-shower frames and
the network columns are used under, each measured on the production file
before it was relied on: that a shower's entry point P0 is one point, that the
local coordinates are the translated ones rotated by that shower's own
R(theta, phi), that ``z_trans`` sits on whole layers, that ``*_true`` is the
shower's own incident momentum or polar angle, and that per-shower network
outputs are constant within a shower.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from ..db import naming
from ..db.ddl import HIT_COLUMNS, MODELS, csv_model_column
from ..db.naming import quote
from . import csv_spec
from .derive_proj import FRAME_COORDINATES

log = logging.getLogger(__name__)

#: Tolerances, set well above the CSV's six-decimal rounding and REAL storage.
P0_TOLERANCE_MM = 0.01
ROTATION_TOLERANCE_MM = 0.01
LAYER_TOLERANCE_MM = 1e-3
MOMENTUM_TOLERANCE_GEV = 1e-5
THETA_TOLERANCE_RAD = 2e-6


@dataclass
class VerificationResult:
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)
    values: dict[str, float | int | None] = field(default_factory=dict)

    def fail(self, key: str, message: str) -> None:
        self.ok = False
        self.checks[key] = "FAIL"
        self.warnings.append(message)
        log.error("Verification failed - %s: %s", key, message)

    def warn(self, key: str, message: str) -> None:
        self.checks[key] = "WARN"
        self.warnings.append(message)
        log.warning("Verification warning - %s: %s", key, message)

    def notice(self, key: str, message: str) -> None:
        self.checks.setdefault(key, "PASS")
        self.notices.append(message)
        log.info("Verification notice - %s: %s", key, message)

    def passed(self, key: str) -> None:
        self.checks.setdefault(key, "PASS")

    def as_dict(self) -> dict:
        return {"ok": self.ok, "checks": self.checks, "values": self.values,
                "warnings": self.warnings, "notices": self.notices}


def _own(column_a: str, column_b: str) -> str:
    return f"CASE WHEN particle_origin = 'A' THEN {column_a} ELSE {column_b} END"


def _archive_checks(con: duckdb.DuckDBPyConnection, source: str, pitch: float) -> dict:
    """One ungrouped scan of the archive computing every row-level contract."""
    model_columns = [n for n, _ in HIT_COLUMNS if n.split("_")[0] in MODELS]
    finite = {
        c: f"count(*) FILTER (WHERE {quote(c)} IS NULL OR NOT isfinite({quote(c)}))"
        for c in (*model_columns, *FRAME_COORDINATES)
    }
    theta = _own("incoming_theta_A", "incoming_theta_B")
    phi = _own("incoming_phi_A", "incoming_phi_B")
    # R(theta, phi) of the notebook that produced the local frame: first the
    # laboratory azimuth, then the tilt. Applied to the translated vector.
    xl = (f"(x_trans * cos({theta}) * cos({phi}) + y_trans * cos({theta}) * sin({phi}) "
          f"- z_trans * sin({theta}))")
    yl = f"(-x_trans * sin({phi}) + y_trans * cos({phi}))"
    zl = (f"(x_trans * sin({theta}) * cos({phi}) + y_trans * sin({theta}) * sin({phi}) "
          f"+ z_trans * cos({theta}))")
    momentum = _own("incoming_momentum_A", "incoming_momentum_B")
    aggregates = {
        **{f"nonfinite__{c}": sql for c, sql in finite.items()},
        "max_rotation_residual": (
            f"max(greatest(abs(x_local - {xl}), abs(y_local - {yl}), abs(z_local - {zl})))"
        ),
        "max_layer_residual": (
            f"max(abs(z_trans - round(z_trans / {pitch!r}) * {pitch!r}))"
        ),
        "gradcam_outside": " + ".join(
            f"count(*) FILTER (WHERE {quote(csv_model_column(m, f, 'gradcam'))} < 0 "
            f"OR {quote(csv_model_column(m, f, 'gradcam'))} > 1)"
            for m in MODELS for f in ("absolute", "trans", "local")
        ),
        "shapcam_outside": " + ".join(
            f"count(*) FILTER (WHERE abs({quote(csv_model_column(m, f, 'shapcam'))}) > 1)"
            for m in MODELS for f in ("absolute", "trans", "local")
        ),
        "segmentation_outside": " + ".join(
            f"count(*) FILTER (WHERE {quote(csv_model_column('segmentation', f, k))} < 0 "
            f"OR {quote(csv_model_column('segmentation', f, k))} > 1)"
            for f in ("absolute", "trans", "local") for k in ("pred", "true")
        ),
        "ab_rows": "count(*) FILTER (WHERE particle_origin = 'A+B')",
        "ab_off_origin": (
            "count(*) FILTER (WHERE particle_origin = 'A+B' AND ("
            + " OR ".join(f"{c} <> 0" for c in FRAME_COORDINATES) + "))"
        ),
        "bad_origin": ("count(*) FILTER (WHERE particle_origin IS NULL "
                       "OR particle_origin NOT IN ('A', 'B', 'A+B'))"),
    }
    for frame in ("absolute", "trans", "local"):
        energy_true = quote(csv_model_column("energy", frame, "true"))
        angle_true = quote(csv_model_column("angle", frame, "true"))
        aggregates[f"max_momentum_residual__{frame}"] = (
            f"max(abs({energy_true} - {momentum})) FILTER (WHERE particle_origin <> 'A+B')"
        )
        aggregates[f"max_theta_residual__{frame}"] = (
            f"max(abs({angle_true} - {theta})) FILTER (WHERE particle_origin <> 'A+B')"
        )
    names = list(aggregates)
    row = con.execute(
        f"SELECT {', '.join(f'{sql} AS {quote(k)}' for k, sql in aggregates.items())} "
        f"FROM {source}"
    ).fetchone()
    return dict(zip(names, row))


def verify(
    con: duckdb.DuckDBPyConnection,
    name: str,
    source_csv: Path | None,
    archive_source: str,
    archive_rows: int,
    layer_pitch_mm: float,
    part_rows: int | None = None,
    lattice_n: tuple[int, int, int] | None = None,
    depth_mm: float | None = None,
) -> VerificationResult:
    """Check the archive and the derived tables against the source and each other."""
    result = VerificationResult()
    proj_physical = naming.proj_table(name)
    event_physical = naming.event_table(name)
    proj, event = quote(proj_physical), quote(event_physical)

    n_parquet = int(con.execute(f"SELECT count(*) FROM {archive_source}").fetchone()[0])
    n_proj = int(con.execute(f"SELECT count(*) FROM {proj}").fetchone()[0])
    n_events = int(con.execute(f"SELECT count(*) FROM {event}").fetchone()[0])
    result.values.update(archive_rows=n_parquet, proj_rows=n_proj, events=n_events)

    # 1. Every data row of the source must have reached the archive: the part
    #    just written holds the source's rows, and the manifest agrees with the
    #    parts actually on disk (an append adds one part to several).
    expected = csv_spec.count_data_rows(source_csv) if source_csv and source_csv.is_file() else None
    if n_parquet != archive_rows:
        result.fail("archive_row_count",
                    f"The archive manifest lists {archive_rows:,} rows but its parts hold {n_parquet:,}.")
    elif expected is not None and part_rows is not None and expected != part_rows:
        result.fail("archive_row_count",
                    f"The source file holds {expected:,} data rows but its archive part holds "
                    f"{part_rows:,}.")
    else:
        result.passed("archive_row_count")
    if n_parquet == 0:
        result.fail("non_empty", "The archive is empty after ingestion.")
        return result

    # 2. The projection may be smaller (sanitisation) but never larger.
    if n_proj > n_parquet:
        result.fail("projection_size",
                    f"{proj_physical} has more rows ({n_proj:,}) than the archive ({n_parquet:,}).")
    else:
        dropped = n_parquet - n_proj
        if dropped and dropped / n_parquet > 0.05:
            result.warn("projection_size",
                        f"Sanitisation removed {dropped:,} of {n_parquet:,} rows "
                        f"({100.0 * dropped / n_parquet:.2f}%) as unphysical.")
        else:
            result.passed("projection_size")

    # 3. Event counts must agree between the derived tables.
    n_proj_events = int(
        con.execute(f"SELECT count(DISTINCT event_number) FROM {proj}").fetchone()[0]
    )
    if n_proj_events == n_events:
        result.passed("event_count")
    else:
        result.warn("event_count",
                    f"{event_physical} summarises {n_events:,} events but {proj_physical} "
                    f"contains {n_proj_events:,}.")

    # 4. Undefined separation: exactly the events with no shower-A row.
    row = con.execute(
        f"""SELECT count(*) FILTER (WHERE d IS NULL),
                   count(*) FILTER (WHERE (d IS NULL) <> (n_a_rows = 0)),
                   count(*) FILTER (WHERE cbx IS NULL)
            FROM {event}"""
    ).fetchone()
    n_no_d, mismatched, no_b = (int(v or 0) for v in row)
    result.values.update(events_no_d=n_no_d)
    if mismatched or no_b:
        result.fail("null_centroid_events",
                    f"{mismatched:,} event(s) have an undefined separation that does not match "
                    f"an absent shower A, and {no_b:,} lack a shower-B centroid.")
    elif n_no_d:
        result.warn("undefined_separation",
                    f"{n_no_d:,} of {n_events:,} events have no hit attributed to shower A, so no "
                    "A centroid and no A-B separation; they are excluded from D-filtered views.")
    else:
        result.passed("undefined_separation")

    # 5. Lattice and layer indices stay inside what was measured. The own-
    #    shower layer kt counts whole layer pitches from the shower's first
    #    layer, so it is bounded by the detector's depth in pitches - not by the
    #    number of *populated* laboratory layers, which a small file can leave
    #    below the full count (the demonstration file populates 56 of 60).
    idx = con.execute(f"SELECT max(ix), max(iy), max(iz), max(kt) FROM {proj}").fetchone()
    if lattice_n and all(v is not None for v in idx):
        nx, ny, nz = lattice_n
        n_pitches = int(round(depth_mm / layer_pitch_mm)) + 1 if depth_mm is not None else nz
        if idx[0] < nx and idx[1] < ny and idx[2] < nz and idx[3] < n_pitches:
            result.passed("lattice_bounds")
        else:
            result.fail("lattice_bounds",
                        f"Projection indices ({idx[0]}, {idx[1]}, {idx[2]}, kt {idx[3]}) exceed "
                        f"the measured lattice ({nx}, {ny}, {nz}; {n_pitches} layer pitches).")

    # 6. Deposited energy positive and finite in aggregate.
    e_dep = con.execute(
        f"SELECT sum(e_dep), count(*) FILTER (WHERE NOT isfinite(e_dep)) FROM {event}"
    ).fetchone()
    if e_dep[0] is None or not (e_dep[0] > 0) or e_dep[1]:
        result.fail("energy_sanity",
                    f"Total deposited energy is not a usable positive finite value "
                    f"(sum={e_dep[0]}, non-finite events={e_dep[1]}).")
    else:
        result.passed("energy_sanity")

    # 7. Per-shower constancy (event table).
    spreads = con.execute(
        f"""SELECT max(chk_p0_spread), max(chk_pt_spread), coalesce(sum(chk_bad_split), 0),
                   coalesce(sum(n_split_cells), 0), coalesce(sum(n_cells), 0),
                   coalesce(sum(n_ab_rows), 0),
                   count(*) FILTER (WHERE cam_zero_mask <> 0)
            FROM {event}"""
    ).fetchone()
    p0_spread, pt_spread, bad_split, n_split, n_cells, n_ab, n_cam_zero = spreads
    result.values.update(p0_spread_mm=p0_spread, pt_spread=pt_spread,
                         split_cells=int(n_split), cells=int(n_cells), ab_rows=int(n_ab),
                         cam_zero_events=int(n_cam_zero))
    if p0_spread is not None and p0_spread > P0_TOLERANCE_MM:
        result.fail("p0_constancy",
                    f"A shower's entry point P0 (x - x_trans) varies by up to {p0_spread:.4g} mm "
                    "within the shower; the translated frame would not be a rigid shift.")
    else:
        result.passed("p0_constancy")
    if pt_spread is not None and pt_spread > 0:
        result.fail("per_shower_constancy",
                    f"Angle or energy network outputs vary within a shower (spread {pt_spread:.4g}).")
    else:
        result.passed("per_shower_constancy")
    if bad_split:
        result.warn("split_cells",
                    f"{int(bad_split):,} cell(s) appear more than once without being one A row "
                    "plus one B row.")
    else:
        result.passed("split_cells")
    if n_cam_zero:
        result.notice("cam_zero",
                      f"{int(n_cam_zero):,} event(s) have at least one network's CAM map "
                      "identically zero; those maps have no peak to normalise.")

    # 8. Row-level contracts, one scan of the archive.
    checks = _archive_checks(con, archive_source, layer_pitch_mm)
    bad_columns = {k.split("__", 1)[1]: int(v) for k, v in checks.items()
                   if k.startswith("nonfinite__") and v}
    if bad_columns:
        result.fail("finite_model_columns",
                    "Non-finite or missing values in: "
                    + ", ".join(f"{c} ({n:,})" for c, n in sorted(bad_columns.items()))
                    + ". They are rejected rather than replaced, because a filled-in "
                    "prediction would be a fabricated one.")
    else:
        result.passed("finite_model_columns")
    outside = int(checks["gradcam_outside"] or 0) + int(checks["shapcam_outside"] or 0) \
        + int(checks["segmentation_outside"] or 0)
    result.values["cam_values_outside_range"] = outside
    if outside:
        result.warn("cam_ranges",
                    f"{outside:,} model value(s) lie outside their documented range "
                    "(Grad-CAM and voxel fractions in [0, 1], Shap-CAM in [-1, 1]).")
    else:
        result.passed("cam_ranges")
    rotation = checks["max_rotation_residual"]
    result.values["rotation_residual_mm"] = rotation
    if rotation is not None and rotation > ROTATION_TOLERANCE_MM:
        result.fail("local_rotation",
                    f"x/y/z_local differ from R(theta, phi) of the own shower applied to the "
                    f"translated coordinates by up to {rotation:.4g} mm.")
    else:
        result.passed("local_rotation")
    layer = checks["max_layer_residual"]
    result.values["layer_residual_mm"] = layer
    if layer is not None and layer > LAYER_TOLERANCE_MM:
        result.fail("trans_layers",
                    f"z_trans is off the {layer_pitch_mm} mm layer grid by up to {layer:.4g} mm.")
    else:
        result.passed("trans_layers")
    worst_p = max((checks[f"max_momentum_residual__{f}"] or 0.0) for f in ("absolute", "trans", "local"))
    worst_t = max((checks[f"max_theta_residual__{f}"] or 0.0) for f in ("absolute", "trans", "local"))
    result.values.update(momentum_residual_gev=worst_p, theta_residual_rad=worst_t)
    if worst_p > MOMENTUM_TOLERANCE_GEV or worst_t > THETA_TOLERANCE_RAD:
        result.fail("truth_consistency",
                    f"energy_*_true / angle_*_true differ from the own shower's incident "
                    f"momentum / polar angle by up to {worst_p:.3g} GeV / {worst_t:.3g} rad.")
    else:
        result.passed("truth_consistency")
    if checks["bad_origin"]:
        result.fail("ab_rows", f"{int(checks['bad_origin']):,} row(s) have an unknown particle_origin.")
    elif checks["ab_off_origin"]:
        result.fail("ab_rows",
                    f"{int(checks['ab_off_origin']):,} 'A+B' row(s) are not at the origin of "
                    "the per-shower frames.")
    else:
        if checks["ab_rows"]:
            result.notice("ab_rows",
                          f"{int(checks['ab_rows']):,} 'A+B' row(s): at the origin of both "
                          "per-shower frames and counted with shower B.")
        result.passed("ab_rows")

    log.info(
        "Verification for %r: %s (%s)",
        name, "PASSED" if result.ok else "FAILED",
        ", ".join(f"{k}={v}" for k, v in sorted(result.checks.items())),
    )
    return result
