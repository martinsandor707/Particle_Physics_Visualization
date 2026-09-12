"""Canonical table definitions.

Every ``CREATE TABLE`` in the application is built here, and :data:`HIT_COLUMNS`
is the single source of truth for the 29-column input schema - the ingest CSV
type map in ``calosrv/ingest/csv_spec.py`` is derived from it rather than
restated, so the two can never drift apart.
"""

from __future__ import annotations

from .naming import quote

#: The 29 columns of the inference CSV, in file order.
#:
#: Type choices worth defending:
#:
#: ``energy`` is ``DOUBLE`` while every other measurement is ``REAL``. Per-hit
#: energies span roughly fifteen decades (2.8e-15 to 0.17 GeV). A ``float32``
#: accumulator summing 22.5 million such values loses the entire low tail to
#: round-off, and ``energy * voxel_fA_pred`` products feed directly into the
#: reconstructed-energy panel. Four extra bytes on one column is a trivial price.
#:
#: ``x``/``y``/``z`` are ``REAL``: the detector lattice has 212 x 104 x 60
#: distinct positions on a 20.5 mm longitudinal pitch, so single precision
#: resolves every physical cell centre with many digits to spare.
#:
#: ``cellID`` is ``BIGINT`` because observed values reach 5.06e9, past INT32.
#:
#: ``incoming_momentum_bin_A``/``_B`` hold 0-19, so ``UTINYINT``.
HIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_number", "INTEGER"),
    ("overlap", "SMALLINT"),
    ("cellID", "BIGINT"),
    ("x", "REAL"),
    ("y", "REAL"),
    ("z", "REAL"),
    ("energy", "DOUBLE"),
    ("particle_origin", "VARCHAR"),
    ("earliest_contribution_time_A", "REAL"),
    ("earliest_contribution_time_B", "REAL"),
    ("incoming_momentum_A", "REAL"),
    ("incoming_momentum_B", "REAL"),
    ("incoming_momentum_bin_A", "UTINYINT"),
    ("incoming_momentum_bin_B", "UTINYINT"),
    ("incoming_theta_A", "REAL"),
    ("incoming_theta_B", "REAL"),
    ("incoming_phi_A", "REAL"),
    ("incoming_phi_B", "REAL"),
    ("gradcam", "REAL"),
    ("gradcam_energy", "REAL"),
    ("voxel_fA_pred", "REAL"),
    ("voxel_fA_true", "REAL"),
    ("centroid_A_x", "REAL"),
    ("centroid_A_y", "REAL"),
    ("centroid_A_z", "REAL"),
    ("centroid_B_x", "REAL"),
    ("centroid_B_y", "REAL"),
    ("centroid_B_z", "REAL"),
    ("centroid_AB_distance", "REAL"),
)

HIT_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in HIT_COLUMNS)


def create_hit_table(physical: str) -> str:
    """DDL for the archival raw-hit table.

    This table is written once at ingest and never scanned again by a query
    endpoint: everything interactive reads the narrow projection table or the
    per-event summary. It is kept so that a derived table can always be rebuilt,
    and so a physicist can run ad-hoc SQL against the untouched input.
    """
    body = ",\n    ".join(f"{quote(name)} {sql_type}" for name, sql_type in HIT_COLUMNS)
    return f"CREATE TABLE IF NOT EXISTS {quote(physical)} (\n    {body}\n);"


def create_proj_table(physical: str) -> str:
    """DDL for the narrow projection table - the interactive hot path.

    Twelve columns instead of twenty-nine, with the three spatial coordinates
    replaced by native lattice indices that fit in a byte each. Nominally about
    35 bytes per row, but the per-event constants (``event_number``, ``e1``,
    ``e2``, ``d``, ``ovl``) are identical across every hit of an event and the
    source file is sorted by event, so DuckDB's run-length encoding compresses
    them to almost nothing. Measured expectation is 300-450 MB for 22.5 million
    rows, against roughly 3 GB for the raw table.
    """
    return f"""CREATE TABLE IF NOT EXISTS {quote(physical)} (
    event_number INTEGER,
    ix           USMALLINT,  -- native transverse x bin, 0 .. nx-1
    iy           USMALLINT,  -- native transverse y bin, 0 .. ny-1
    iz           UTINYINT,   -- native sampling layer,   0 .. nz-1
    energy       DOUBLE,
    ge           REAL,       -- gradcam_energy
    fa_pred      REAL,       -- voxel_fA_pred
    fa_true      REAL,       -- voxel_fA_true
    e1           REAL,       -- incoming_momentum_A,  per-event constant
    e2           REAL,       -- incoming_momentum_B,  per-event constant
    d            REAL,       -- centroid_AB_distance, per-event constant, NULLable
    ovl          SMALLINT    -- overlap class,        per-event constant
);"""


def create_event_table(physical: str) -> str:
    """DDL for the per-event summary of additive sufficient statistics.

    The design property that makes the interactive metrics cheap: accuracy, MAE
    and RMSE over an arbitrary filtered subset of events are all of the form
    ``sum(numerator) / sum(denominator)``. Storing the numerators and
    denominators per event means those metrics roll up *exactly* over any
    selection, from roughly 20 000 rows, with no approximation and no re-scan of
    the 22.5 million hit rows.
    """
    return f"""CREATE TABLE IF NOT EXISTS {quote(physical)} (
    event_number INTEGER PRIMARY KEY,
    ovl          SMALLINT,
    e1           REAL,
    e2           REAL,
    e1_bin       UTINYINT,
    e2_bin       UTINYINT,
    theta_a      REAL,
    theta_b      REAL,
    phi_a        REAL,
    phi_b        REAL,
    d            REAL,
    cax REAL, cay REAL, caz REAL,
    cbx REAL, cby REAL, cbz REAL,

    n_hits       BIGINT,
    e_dep        DOUBLE,

    -- Reconstructed-energy panel: deposited energy attributed to each shower.
    e_a_pred     DOUBLE,
    e_b_pred     DOUBLE,
    e_a_true     DOUBLE,
    e_b_true     DOUBLE,

    -- Model-performance panel: additive sufficient statistics.
    sum_abs_err  DOUBLE,
    sum_wabs_err DOUBLE,
    sum_sq_err   DOUBLE,
    n_correct    BIGINT,
    n_true_a     BIGINT,
    n_pred_a     BIGINT,
    n_tp         BIGINT,
    n_shared     BIGINT
);"""


#: Registry of every experiment the server knows about.
#:
#: The kinematic bounds and the lattice geometry are cached here at ingest so
#: ``GET /api/experiments`` touches no hit data at all, and so every projection
#: query for a given experiment bins against identical edges for the lifetime of
#: the table - a lattice re-measured per request could shift by a bin when a
#: filter excludes the outermost hit, and the heatmaps would shimmer.
CREATE_REGISTRY = """CREATE TABLE IF NOT EXISTS "experiment" (
    table_name      VARCHAR PRIMARY KEY,
    display_name    VARCHAR,
    source_files    VARCHAR[],
    status          VARCHAR,          -- pending | ingesting | ready | failed
    error           VARCHAR,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,

    n_hits          BIGINT,
    n_events        BIGINT,
    n_events_no_d   BIGINT,           -- degenerate events with undefined D

    e1_min DOUBLE, e1_max DOUBLE,
    e2_min DOUBLE, e2_max DOUBLE,
    d_min  DOUBLE, d_max  DOUBLE,

    -- Detector lattice, measured at ingest and frozen thereafter.
    --
    -- The coordinate arrays are the authoritative geometry: the transverse x
    -- lattice is NOT uniformly spaced (211 distinct values arranged as tight
    -- pairs 4.4 mm apart, with a group pitch alternating 43.87 / 48.27 mm), so
    -- a bin index cannot be converted to millimetres by multiplying a pitch.
    -- Every physical placement goes through these arrays instead. The pitch
    -- columns are retained only as the *mean* spacing, for reporting.
    x_lo DOUBLE, x_hi DOUBLE, nx INTEGER, x_coords DOUBLE[],
    y_lo DOUBLE, y_hi DOUBLE, ny INTEGER, y_coords DOUBLE[],
    z_lo DOUBLE, z_hi DOUBLE, nz INTEGER, z_coords DOUBLE[],
    pitch_x DOUBLE, pitch_y DOUBLE, pitch_z DOUBLE,
    x_uniform BOOLEAN, y_uniform BOOLEAN, z_uniform BOOLEAN,
    slab_mm DOUBLE, slab_iz INTEGER,

    -- Global colour-scale anchors, so the ramp can be locked across filters.
    cell_e_max  DOUBLE,
    cell_e_p999 DOUBLE,

    overlap_classes SMALLINT[],
    has_sample BOOLEAN
);"""

REGISTRY_COLUMNS: tuple[str, ...] = (
    "table_name", "display_name", "source_files", "status", "error",
    "created_at", "updated_at",
    "n_hits", "n_events", "n_events_no_d",
    "e1_min", "e1_max", "e2_min", "e2_max", "d_min", "d_max",
    "x_lo", "x_hi", "nx", "x_coords",
    "y_lo", "y_hi", "ny", "y_coords",
    "z_lo", "z_hi", "nz", "z_coords",
    "pitch_x", "pitch_y", "pitch_z",
    "x_uniform", "y_uniform", "z_uniform",
    "slab_mm", "slab_iz",
    "cell_e_max", "cell_e_p999", "overlap_classes", "has_sample",
)


def drop_table(physical: str) -> str:
    return f"DROP TABLE IF EXISTS {quote(physical)};"
