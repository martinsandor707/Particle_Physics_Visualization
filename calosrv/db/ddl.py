"""Canonical table definitions and the input schema.

Every ``CREATE TABLE`` in the application is built here, and :data:`HIT_COLUMNS`
is the single source of truth for the 99-column ``hits_all_models`` input
schema - the CSV reader in ``calosrv/ingest/csv_spec.py`` and the Parquet
archive in ``calosrv/db/archive.py`` both derive from it rather than restating
it, so the three can never drift apart.

The same module owns the *vocabulary* of the multi-model data - the three
networks, the three frames each was trained in, the four CAM columns per
network - and the only functions allowed to turn that vocabulary into a column
name (:func:`cam_column`, :func:`seg_column`). Column names cannot be bound as
query parameters, so a request string must never reach SQL; every weight
column a query reads comes from these allowlisted builders.
"""

from __future__ import annotations

from .naming import quote

# ------------------------------------------------------------ vocabulary --

#: The three reconstruction networks, as the API names them.
MODELS: tuple[str, ...] = ("angle", "energy", "segmentation")

#: The three coordinate systems the interface offers, as the API names them.
COORD_SYSTEMS: tuple[str, ...] = ("lab", "trans", "local")

#: The frame each network was trained in, as the CSV column names spell it.
#: ``lab`` is written ``absolute`` in the file. The canonical frame is built
#: from laboratory coordinates, so it uses the absolute-frame networks.
NETWORK_FRAME: dict[str, str] = {"lab": "absolute", "trans": "trans", "local": "local"}

#: The frames in the order the CSV lays their columns out.
CSV_FRAMES: tuple[str, ...] = ("absolute", "local", "trans")

#: Short codes used in derived-table column names.
FRAME_CODE: dict[str, str] = {"absolute": "abs", "trans": "trn", "local": "loc"}
MODEL_CODE: dict[str, str] = {"angle": "an", "energy": "en", "segmentation": "sg"}
CAM_CODE: dict[str, str] = {"gradcam": "gc", "shapcam": "sc"}

#: The six per-network fields, in CSV order. ``pred``/``true`` are per-shower
#: constants for angle and energy and per-hit voxel fractions for segmentation;
#: the four CAM columns are per-voxel values repeated on every hit of the voxel.
MODEL_FIELDS: tuple[str, ...] = (
    "pred", "true", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy",
)

#: Raw CAM fields carried on the hot path. ``*_gradcam_energy`` /
#: ``*_shapcam_energy`` are CAM x E_voxel rescaled per event or per shower;
#: summed over hits they double-count voxel energy, so they stay archival and
#: the energy-weighted channels are computed from the raw CAM and hit energy.
RAW_CAMS: tuple[str, ...] = ("gradcam", "shapcam")

#: ``particle_origin`` codes in the projection table. 'A+B' rows - 422 in the
#: production file - carry shower B's per-shower values and sit at the origin of
#: both per-shower frames, so everything that splits by shower counts them as B.
ORIGIN_A = 0
ORIGIN_B = 1
ORIGIN_AB = 2

SCHEMA_NAME = "hits_all_models"
SCHEMA_VERSION = 1


def _check(value: str, allowed, what: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {what} {value!r}; expected one of {', '.join(allowed)}")
    return value


def frame_code(coord_system: str) -> str:
    """``lab`` -> ``abs``, ``trans`` -> ``trn``, ``local`` -> ``loc``."""
    return FRAME_CODE[NETWORK_FRAME[_check(coord_system, COORD_SYSTEMS, "coordinate system")]]


def cam_column(model: str, coord_system: str, cam: str) -> str:
    """The projection-table column holding one network's raw CAM, e.g. ``sc_en_trn``."""
    _check(model, MODELS, "model")
    _check(cam, RAW_CAMS, "CAM")
    return f"{CAM_CODE[cam]}_{MODEL_CODE[model]}_{frame_code(coord_system)}"


def seg_column(kind: str, coord_system: str) -> str:
    """The segmentation voxel fraction of shower A, e.g. ``fa_pred_abs``."""
    _check(kind, ("pred", "true"), "segmentation field")
    return f"fa_{kind}_{frame_code(coord_system)}"


def csv_model_column(model: str, frame: str, field: str) -> str:
    """The input-file name of one model column, e.g. ``energy_trans_shapcam``."""
    _check(model, MODELS, "model")
    _check(frame, CSV_FRAMES, "network frame")
    _check(field, MODEL_FIELDS, "model field")
    return f"{model}_{frame}_{field}"


def cam_bit(model: str, coord_system: str, cam: str) -> int:
    """Bit of one raw CAM column in the event table's ``cam_zero_mask``."""
    models = MODELS.index(_check(model, MODELS, "model"))
    frames = COORD_SYSTEMS.index(_check(coord_system, COORD_SYSTEMS, "coordinate system"))
    cams = RAW_CAMS.index(_check(cam, RAW_CAMS, "CAM"))
    return (models * len(COORD_SYSTEMS) + frames) * len(RAW_CAMS) + cams


def raw_cam_columns() -> tuple[tuple[str, str, str, str, str], ...]:
    """``(proj_column, csv_column, model, coord_system, cam)`` for all 18 raw CAMs."""
    out = []
    for model in MODELS:
        for coord in COORD_SYSTEMS:
            for cam in RAW_CAMS:
                out.append((
                    cam_column(model, coord, cam),
                    csv_model_column(model, NETWORK_FRAME[coord], cam),
                    model, coord, cam,
                ))
    return tuple(out)


# ---------------------------------------------------------- input schema --


def _hit_columns() -> tuple[tuple[str, str], ...]:
    columns: list[tuple[str, str]] = [
        ("event_number", "INTEGER"),
        ("overlap", "SMALLINT"),
        ("cellID", "BIGINT"),
    ]
    for suffix in ("", "_local", "_trans"):
        columns += [(f"{axis}{suffix}", "REAL") for axis in "xyz"]
    columns += [
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
    ]
    for suffix in ("", "_trans", "_local"):
        for shower in "AB":
            columns += [(f"centroid_{shower}_{axis}{suffix}", "REAL") for axis in "xyz"]
        columns.append((f"centroid_AB_distance{suffix}", "REAL"))
    for model in MODELS:
        for frame in CSV_FRAMES:
            columns += [(csv_model_column(model, frame, f), "REAL") for f in MODEL_FIELDS]
    return tuple(columns)


#: The 99 columns of the ``hits_all_models`` inference CSV, in file order.
#:
#: Type choices worth defending:
#:
#: ``energy`` is ``DOUBLE`` while every other measurement is ``REAL``. Per-hit
#: energies span roughly fifteen decades (5.7e-16 to 0.28 GeV). A ``float32``
#: accumulator summing 24 million such values loses the entire low tail to
#: round-off, and every energy-weighted plane and per-event sum feeds on it.
#:
#: Every coordinate, centroid and model column is ``REAL``: single precision
#: resolves positions to better than 0.0005 mm at +-5 m and keeps more than
#: seven significant digits of the six-decimal CAM and prediction values the
#: file carries, at half the archive bytes of ``DOUBLE``.
#:
#: ``cellID`` is ``BIGINT`` because observed values reach 5.06e9, past INT32.
#:
#: ``incoming_momentum_bin_A``/``_B`` hold 0-19, so ``UTINYINT``.
HIT_COLUMNS: tuple[tuple[str, str], ...] = _hit_columns()

HIT_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in HIT_COLUMNS)


# ----------------------------------------------------- projection table --


def _proj_columns() -> tuple[tuple[str, str, str], ...]:
    columns: list[tuple[str, str, str]] = [
        ("event_number", "INTEGER", ""),
        ("ix", "USMALLINT", "laboratory x ordinal, 0 .. nx-1"),
        ("iy", "USMALLINT", "laboratory y ordinal, 0 .. ny-1"),
        ("iz", "UTINYINT", "laboratory sampling layer, 0 .. nz-1"),
        ("org", "UTINYINT", "particle_origin: 0 A, 1 B, 2 'A+B' (counted as B)"),
        ("xt", "REAL", "x_trans: x minus the hit's own shower entry point P0"),
        ("yt", "REAL", "y_trans"),
        ("kt", "UTINYINT", "own-shower layer: round(z_trans / layer pitch)"),
        ("xl", "REAL", "x_local: translated, then rotated by R(theta, phi) of the own shower"),
        ("yl", "REAL", "y_local"),
        ("zl", "REAL", "z_local: depth along the own shower's incident direction"),
        ("energy", "DOUBLE", ""),
    ]
    for column, csv_name, *_ in raw_cam_columns():
        columns.append((column, "REAL", csv_name))
    for kind in ("pred", "true"):
        for coord in COORD_SYSTEMS:
            columns.append((
                seg_column(kind, coord), "REAL",
                csv_model_column("segmentation", NETWORK_FRAME[coord], kind),
            ))
    columns += [
        ("e1", "REAL", "incoming_momentum_A, per-event constant"),
        ("e2", "REAL", "incoming_momentum_B, per-event constant"),
        ("d", "REAL", "laboratory centroid_AB_distance, per-event constant, NULLable"),
        ("ovl", "SMALLINT", "overlap class, per-event constant"),
    ]
    return tuple(columns)


#: The hot-path projection table, as ``(name, type, source / comment)``.
PROJ_COLUMNS: tuple[tuple[str, str, str], ...] = _proj_columns()
PROJ_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, *_ in PROJ_COLUMNS)


def create_proj_table(physical: str) -> str:
    """DDL for the projection table - the interactive hot path.

    One row per hit, carrying the laboratory lattice ordinals, both per-shower
    frames' coordinates, energy, the 18 raw CAM columns (3 networks x 3 frames
    x Grad-CAM / Shap-CAM), the three segmentation networks' voxel fractions and
    the per-event filter columns. DuckDB is columnar, so a query reads only the
    handful of these it names; the per-event constants (``event_number``,
    ``e1``, ``e2``, ``d``, ``ovl``) compress to almost nothing.
    """
    # The separating comma goes before each line's comment, never after it.
    lines = []
    for index, (name, sql_type, comment) in enumerate(PROJ_COLUMNS):
        sep = "," if index < len(PROJ_COLUMNS) - 1 else ""
        line = f"    {name:<13} {sql_type}{sep}"
        if comment:
            line += f"  -- {comment}"
        lines.append(line)
    return f"CREATE TABLE IF NOT EXISTS {quote(physical)} (\n" + "\n".join(lines) + "\n);"


# ---------------------------------------------------------- event table --

#: Per-frame segmentation sufficient statistics, suffixed ``_abs|_trn|_loc``.
SEG_STAT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("e_a_pred", "DOUBLE"), ("e_b_pred", "DOUBLE"),
    ("e_a_true", "DOUBLE"), ("e_b_true", "DOUBLE"),
    ("sum_abs_err", "DOUBLE"), ("sum_wabs_err", "DOUBLE"), ("sum_sq_err", "DOUBLE"),
    ("n_correct", "BIGINT"), ("n_true_a", "BIGINT"),
    ("n_pred_a", "BIGINT"), ("n_tp", "BIGINT"),
)


def _event_columns() -> tuple[tuple[str, str], ...]:
    columns: list[tuple[str, str]] = [
        ("event_number", "INTEGER PRIMARY KEY"),
        ("ovl", "SMALLINT"),
        ("e1", "REAL"), ("e2", "REAL"),
        ("e1_bin", "UTINYINT"), ("e2_bin", "UTINYINT"),
        ("theta_a", "REAL"), ("theta_b", "REAL"),
        ("phi_a", "REAL"), ("phi_b", "REAL"),
        ("d", "REAL"),
    ]
    for suffix in ("", "_t", "_l"):
        columns += [(f"c{s}{axis}{suffix}", "REAL") for s in "ab" for axis in "xyz"]
    columns += [("d_t", "REAL"), ("d_l", "REAL")]
    columns += [(f"p0{s}{axis}", "DOUBLE") for s in "ab" for axis in "xyz"]
    columns += [
        ("n_hits", "BIGINT"),
        ("n_a_rows", "BIGINT"), ("n_b_rows", "BIGINT"), ("n_ab_rows", "BIGINT"),
        ("e_ab", "DOUBLE"),
        ("e_dep", "DOUBLE"),
    ]
    for coord in COORD_SYSTEMS:
        code = frame_code(coord)
        columns += [(f"{stem}_{code}", sql_type) for stem, sql_type in SEG_STAT_COLUMNS]
    for coord in COORD_SYSTEMS:
        code = frame_code(coord)
        columns += [
            (f"en_pred_a_{code}", "REAL"), (f"en_pred_b_{code}", "REAL"),
            (f"th_pred_a_{code}", "REAL"), (f"th_pred_b_{code}", "REAL"),
        ]
    columns += [
        ("en_true_a", "REAL"), ("en_true_b", "REAL"),
        ("th_true_a", "REAL"), ("th_true_b", "REAL"),
        ("n_cells", "BIGINT"), ("n_split_cells", "BIGINT"), ("e_split", "DOUBLE"),
        ("chk_bad_split", "BIGINT"),
        ("cam_zero_mask", "UINTEGER"),
        ("chk_p0_spread", "DOUBLE"),
        ("chk_pt_spread", "DOUBLE"),
    ]
    return tuple(columns)


#: The per-event summary: additive sufficient statistics and per-shower values.
EVENT_COLUMNS: tuple[tuple[str, str], ...] = _event_columns()
EVENT_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in EVENT_COLUMNS)


def create_event_table(physical: str) -> str:
    """DDL for the per-event summary of additive sufficient statistics.

    The design property that makes the interactive metrics cheap: accuracy, MAE
    and RMSE over an arbitrary filtered subset of events are all of the form
    ``sum(numerator) / sum(denominator)``. Storing the numerators and
    denominators per event - once per segmentation network - means those
    metrics roll up *exactly* over any selection, from about 20 000 rows, with
    no re-scan of the 24 million hit rows. The angle and energy networks predict
    one value per shower, so those live here too, once per event and shower.
    """
    body = ",\n    ".join(f"{name} {sql_type}" for name, sql_type in EVENT_COLUMNS)
    return f"CREATE TABLE IF NOT EXISTS {quote(physical)} (\n    {body}\n);"


# ------------------------------------------------------------- registry --

#: Registry of every experiment the server knows about, as ``(name, type)``.
#:
#: The kinematic bounds and the lattice geometry are cached here at ingest so
#: ``GET /api/experiments`` touches no hit data at all, and so every projection
#: query for a given experiment bins against identical edges for the lifetime of
#: the table - a lattice re-measured per request could shift by a bin when a
#: filter excludes the outermost hit, and the heatmaps would shimmer.
#:
#: The coordinate arrays are the authoritative geometry: the transverse x
#: lattice is NOT uniformly spaced (212 distinct values arranged as tight pairs
#: 4.4 mm apart, with a group pitch alternating 43.87 / 48.27 mm), so a bin
#: index cannot be converted to millimetres by multiplying a pitch. The pitch
#: columns are retained only as the *mean* spacing, for reporting.
#:
#: Columns are only ever appended: :func:`calosrv.db.registry.ensure_registry`
#: adds any that an older database lacks.
REGISTRY_SCHEMA: tuple[tuple[str, str], ...] = (
    ("table_name", "VARCHAR PRIMARY KEY"),
    ("display_name", "VARCHAR"),
    ("source_files", "VARCHAR[]"),
    ("status", "VARCHAR"),
    ("error", "VARCHAR"),
    ("created_at", "TIMESTAMP"),
    ("updated_at", "TIMESTAMP"),
    ("n_hits", "BIGINT"),
    ("n_events", "BIGINT"),
    ("n_events_no_d", "BIGINT"),
    ("e1_min", "DOUBLE"), ("e1_max", "DOUBLE"),
    ("e2_min", "DOUBLE"), ("e2_max", "DOUBLE"),
    ("d_min", "DOUBLE"), ("d_max", "DOUBLE"),
    ("x_lo", "DOUBLE"), ("x_hi", "DOUBLE"), ("nx", "INTEGER"), ("x_coords", "DOUBLE[]"),
    ("y_lo", "DOUBLE"), ("y_hi", "DOUBLE"), ("ny", "INTEGER"), ("y_coords", "DOUBLE[]"),
    ("z_lo", "DOUBLE"), ("z_hi", "DOUBLE"), ("nz", "INTEGER"), ("z_coords", "DOUBLE[]"),
    ("pitch_x", "DOUBLE"), ("pitch_y", "DOUBLE"), ("pitch_z", "DOUBLE"),
    ("x_uniform", "BOOLEAN"), ("y_uniform", "BOOLEAN"), ("z_uniform", "BOOLEAN"),
    ("slab_mm", "DOUBLE"), ("slab_iz", "INTEGER"),
    ("cell_e_max", "DOUBLE"),
    ("cell_e_p999", "DOUBLE"),
    ("overlap_classes", "SMALLINT[]"),
    ("has_sample", "BOOLEAN"),
    # --- appended for the hits_all_models schema --------------------------
    ("schema_name", "VARCHAR"),
    ("schema_version", "INTEGER"),
    ("archive_dir", "VARCHAR"),       # relative to the data directory
    ("archive_parts", "INTEGER"),
    ("archive_rows", "BIGINT"),
    ("archive_bytes", "BIGINT"),
    ("n_cells", "BIGINT"),
    ("n_split_cells", "BIGINT"),
    ("n_ab_rows", "BIGINT"),
    ("frame_bounds", "VARCHAR"),      # JSON, see calosrv.grid.bounds
    ("ingest_report", "VARCHAR"),     # JSON: sanitation, calibration, timings, checks
)

REGISTRY_COLUMNS: tuple[str, ...] = tuple(name for name, _ in REGISTRY_SCHEMA)

CREATE_REGISTRY = (
    'CREATE TABLE IF NOT EXISTS "experiment" (\n    '
    + ",\n    ".join(f"{name} {sql_type}" for name, sql_type in REGISTRY_SCHEMA)
    + "\n);"
)


def drop_table(physical: str) -> str:
    return f"DROP TABLE IF EXISTS {quote(physical)};"
