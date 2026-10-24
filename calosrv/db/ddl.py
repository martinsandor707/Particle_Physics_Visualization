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

#: The three kinds of experiment, one per accepted input schema
#: (calosrv/db/schemas.py): two showers per event with the networks' outputs,
#: one shower per event with its hits, and one shower per event as precomputed
#: event-level features only.
KIND_TWO_SHOWER = "two_shower_hits"
KIND_SINGLE_HITS = "single_shower_hits"
KIND_SINGLE_EVENTS = "single_shower_events"
KINDS: tuple[str, ...] = (KIND_TWO_SHOWER, KIND_SINGLE_HITS, KIND_SINGLE_EVENTS)

#: ``core.SHIFT_Z`` (reference_ipynb_notebooks/core.py:49): the calorimeter front
#: face in raw z. Stored data keep raw z - the producer's v3 aggregate is computed
#: on raw z, and both hit schemas share one lattice whose first layer sits at
#: 3662.4 mm - so this is only a display offset, applied where a panel quotes a
#: depth below the front face and labelled ``z − 3649 mm`` there.
CORE_SHIFT_Z_MM = 3649.0

#: A hit lies behind its shower's entry plane when ``z_local`` is below this,
#: the notebooks' tolerance (High_energy_notebook, diagnose_negative_z).
NEG_DEPTH_MM = -1e-6


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

#: The columns that are legitimately empty: every ``centroid_A_*`` coordinate and
#: the three ``centroid_AB_distance*`` columns, in the events where shower A
#: deposited nothing (57 on the production file). No A centroid exists there, so
#: the separation is undefined, and every consumer tests that with ``IS NULL``.
NULLABLE_COLUMNS: tuple[str, ...] = tuple(
    name for name in HIT_COLUMN_NAMES
    if name.startswith("centroid_A_") or name.startswith("centroid_AB_distance")
)


#: The 21 columns of the single-shower hit file (``*_standalone_..._v3.csv``),
#: one row per cell of one event, in file order.
#:
#: Type choices worth defending:
#:
#: ``x``, ``y``, ``z`` are REAL: the producer writes float32 positions widened to
#: float64 (``3662.39990234375``), so single precision holds them exactly and the
#: measured lattice is bit-identical to the two-shower files'.
#:
#: The ``_trans`` and ``_local`` coordinates, ``energy`` and the incident
#: kinematics are DOUBLE: they are genuine float64 values, and the event
#: features are checked against the producer's aggregate at 10⁻⁹ - REAL would
#: round them by 6 × 10⁻⁸ - while ``incoming_momentum_bin = ⌊p⌋`` is checked on
#: integer boundaries that float32 rounding can cross.
#:
#: ``is_secondary`` is 0/1 as written (UTINYINT; a Parquet BOOLEAN is accepted).
#: The three species columns are free text: ``particle_type`` has an open
#: vocabulary (ions are written ``PDG_100ZZZAAA0``), ``daughter_type`` is a
#: ``;``-joined list, and an empty field - no parent for a primary-tagged cell,
#: no daughters - is read as NULL.
STANDALONE_HIT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_number", "INTEGER"),
    ("cellID", "BIGINT"),
    ("x", "REAL"), ("y", "REAL"), ("z", "REAL"),
    ("x_local", "DOUBLE"), ("y_local", "DOUBLE"), ("z_local", "DOUBLE"),
    ("x_trans", "DOUBLE"), ("y_trans", "DOUBLE"), ("z_trans", "DOUBLE"),
    ("energy", "DOUBLE"),
    ("earliest_contribution_time", "REAL"),
    ("incoming_momentum", "DOUBLE"),
    ("incoming_theta", "DOUBLE"),
    ("incoming_phi", "DOUBLE"),
    ("incoming_momentum_bin", "UTINYINT"),
    ("particle_type", "VARCHAR"),
    ("is_secondary", "UTINYINT"),
    ("parent_type", "VARCHAR"),
    ("daughter_type", "VARCHAR"),
)

#: The seventeen per-frame features of ``core.calc_all_features_v3`` in its key
#: order (core.py:503-510), without the two densities that follow per frame.
CORE_FEATURES: tuple[str, ...] = (
    "width", "height", "depth", "depth_range", "volume",
    "centroid_x", "centroid_y", "centroid_z",
    "mean_r", "std_r", "max_r", "weighted_r_mean",
    "avg_theta", "avg_phi", "angular_spread",
)

#: The suffix each frame's features carry in the aggregated file.
FEATURE_SUFFIX: dict[str, str] = {"abs": "", "trn": "_trans", "loc": "_local"}


def _standalone_event_columns() -> tuple[tuple[str, str], ...]:
    columns: list[tuple[str, str]] = [
        ("event_id", "INTEGER"),
        ("incoming_momentum", "DOUBLE"),
        ("incoming_theta", "DOUBLE"),
        ("incoming_phi", "DOUBLE"),
        ("incoming_momentum_bin", "UTINYINT"),
        ("num_hits", "INTEGER"),
        ("total_hit_energy", "DOUBLE"),
    ]
    for code in ("abs", "trn", "loc"):
        columns += [(f"{name}{FEATURE_SUFFIX[code]}", "DOUBLE") for name in CORE_FEATURES]
    for code in ("abs", "trn", "loc"):
        columns += [(f"{name}{FEATURE_SUFFIX[code]}", "DOUBLE")
                    for name in ("numerical_density", "energy_density")]
    # Not an energy: the producer's class label 1{incoming_momentum >= 2 GeV}.
    columns.append(("energy", "DOUBLE"))
    return tuple(columns)


#: The 59 columns of the single-shower aggregated file
#: (``*_standalone_..._aggr_..._v3.csv``), one row per event, in file order: the
#: output of ``core.calc_all_features_v3`` on raw z, plus a trailing ``energy``
#: that holds the class label 1{p ≥ 2 GeV}. ``event_id`` and the bin are exact
#: integers; every feature is a float64 value.
STANDALONE_EVENT_COLUMNS: tuple[tuple[str, str], ...] = _standalone_event_columns()


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


#: The projection table of a single-shower hit experiment. The shared columns
#: keep the two-shower names and meanings, with the single shower as shower A
#: (``org = 0``), so the frame and projection code reads both kinds; the
#: networks' CAM and segmentation columns and the second-shower filter columns
#: do not exist, and the four species columns are kept for the species views.
PROJ_SINGLE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("event_number", "INTEGER", ""),
    ("ix", "USMALLINT", "laboratory x ordinal, 0 .. nx-1"),
    ("iy", "USMALLINT", "laboratory y ordinal, 0 .. ny-1"),
    ("iz", "UTINYINT", "laboratory sampling layer, 0 .. nz-1"),
    ("org", "UTINYINT", "always 0: the single shower is shower A"),
    ("xt", "REAL", "x_trans: x minus the shower's entry point P0"),
    ("yt", "REAL", "y_trans"),
    ("kt", "UTINYINT", "own-shower layer: round(z_trans / layer pitch)"),
    ("xl", "REAL", "x_local: translated, then rotated by R(theta, phi)"),
    ("yl", "REAL", "y_local"),
    ("zl", "REAL", "z_local: depth along the incident direction"),
    ("energy", "DOUBLE", ""),
    ("e1", "DOUBLE", "incoming_momentum, per-event constant"),
    ("particle_type", "VARCHAR", "the cell's attributed particle"),
    ("is_secondary", "UTINYINT", "0: primary-tagged"),
    ("parent_type", "VARCHAR", "NULL for a primary-tagged cell"),
    ("daughter_type", "VARCHAR", "';'-joined daughters, NULL when none"),
)
PROJ_SINGLE_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, *_ in PROJ_SINGLE_COLUMNS)


def create_proj_table(
    physical: str, columns: tuple[tuple[str, str, str], ...] = PROJ_COLUMNS
) -> str:
    """DDL for the projection table - the interactive hot path.

    One row per hit, carrying the laboratory lattice ordinals, both per-shower
    frames' coordinates, energy, the 18 raw CAM columns (3 networks x 3 frames
    x Grad-CAM / Shap-CAM), the three segmentation networks' voxel fractions and
    the per-event filter columns. DuckDB is columnar, so a query reads only the
    handful of these it names; the per-event constants (``event_number``,
    ``e1``, ``e2``, ``d``, ``ovl``) compress to almost nothing. A single-shower
    experiment passes :data:`PROJ_SINGLE_COLUMNS`.
    """
    # The separating comma goes before each line's comment, never after it.
    lines = []
    for index, (name, sql_type, comment) in enumerate(columns):
        sep = "," if index < len(columns) - 1 else ""
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


# --------------------------------------------------------- Group-1 columns --
#
# Per-shower sums of each event's hits from which every per-frame feature of
# ``core.calc_all_features_v3`` (core.py:459-574) is rebuilt exactly, plus the
# negative-depth counts (C9) and the energy-weighted transverse radius moments
# (C7). Every name is built here - query code never writes one by hand.
#
# ``sum_e_rl``/``sum_e_rl2`` use the 2-D transverse radius ρ = √(x_local² +
# y_local²), the notebook's radial-profile radius, which is not core.py's 3-D
# ``r_local``. The standard deviations are stored as ``stddev_samp`` values
# because recovering them from Σr and Σr² loses ~10⁻⁵ to cancellation where the
# shower is narrow and far from the origin. φ is circular: its linear sums exist
# only to reproduce core.py's arithmetic ``avg_phi`` and ``angular_spread`` for
# parity, beside the circular sums ``sum_cos_phi``/``sum_sin_phi``.

#: The frames Group-1 covers, by their frame code.
GROUP1_FRAMES: tuple[str, ...] = ("abs", "trn", "loc")

#: Per-shower stems, named ``{stem}_{shower}``.
GROUP1_SHOWER_STEMS: tuple[tuple[str, str], ...] = (
    ("n_hits", "BIGINT"),          # num_hits
    ("e_dep", "DOUBLE"),           # total_hit_energy
    ("n_cells", "BIGINT"),         # distinct cells of the shower
    ("w_neg_hits", "BIGINT"),      # hits at z_local < NEG_DEPTH_MM
    ("w_neg_energy", "DOUBLE"),    # their energy
    ("sum_e_rl", "DOUBLE"),        # Σ E·ρ
    ("sum_e_rl2", "DOUBLE"),       # Σ E·ρ²
)

#: Per-frame stems, named ``{stem}_{shower}_{frame}``.
GROUP1_FRAME_STEMS: tuple[tuple[str, str], ...] = tuple(
    (stem, "DOUBLE") for stem in (
        "x_min", "x_max", "y_min", "y_max", "z_min", "z_max",
        "sum_ex", "sum_ey", "sum_ez",
        "sum_r", "sum_r2", "sd_r", "max_r", "sum_er",
        "sum_theta", "sum_theta2", "sd_theta",
        "sum_phi", "sd_phi",
        "sum_cos_phi", "sum_sin_phi",
    )
)


def group1_column(stem: str, shower: str, frame: str | None = None) -> str:
    """The name of one Group-1 column, e.g. ``sd_r_a_loc`` or ``w_neg_hits_b``."""
    _check(shower, ("a", "b"), "shower")
    if frame is None:
        _check(stem, tuple(s for s, _ in GROUP1_SHOWER_STEMS), "Group-1 shower stem")
        return f"{stem}_{shower}"
    _check(stem, tuple(s for s, _ in GROUP1_FRAME_STEMS), "Group-1 frame stem")
    _check(frame, GROUP1_FRAMES, "Group-1 frame")
    return f"{stem}_{shower}_{frame}"


def group1_columns(showers: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Every Group-1 column for the given showers, as ``(name, type)``: 70 per shower."""
    columns: list[tuple[str, str]] = []
    for shower in showers:
        columns += [(group1_column(stem, shower), sql_type) for stem, sql_type in GROUP1_SHOWER_STEMS]
        for frame in GROUP1_FRAMES:
            columns += [(group1_column(stem, shower, frame), sql_type)
                        for stem, sql_type in GROUP1_FRAME_STEMS]
    return tuple(columns)


#: The two-shower event table from derived version 2: today's columns, then
#: Group-1 for both showers ('A+B' rows counted with B, as everywhere else).
EVENT_COLUMNS_V2: tuple[tuple[str, str], ...] = EVENT_COLUMNS + group1_columns(("a", "b"))


def _event_single_columns() -> tuple[tuple[str, str], ...]:
    columns: list[tuple[str, str]] = [
        ("event_number", "INTEGER PRIMARY KEY"),
        ("e1", "DOUBLE"), ("e1_bin", "UTINYINT"),
        ("theta_a", "DOUBLE"), ("phi_a", "DOUBLE"),
    ]
    # Energy-weighted 3-D centroids in the three frames (core.py:491-497; raw z).
    for suffix in ("", "_t", "_l"):
        columns += [(f"ca{axis}{suffix}", "DOUBLE") for axis in "xyz"]
    columns += [(f"p0a{axis}", "DOUBLE") for axis in "xyz"]
    columns += [
        ("n_hits", "BIGINT"), ("n_a_rows", "BIGINT"), ("e_dep", "DOUBLE"),
        ("n_primary_rows", "BIGINT"),      # rows with is_secondary = 0 (C11)
        ("e_primary", "DOUBLE"),
        ("primary_type", "VARCHAR"),       # particle_type of the most energetic primary row
        ("n_null_species", "BIGINT"),
        ("n_parent_mismatch", "BIGINT"),   # (parent_type IS NULL) <> (is_secondary = 0)
        ("n_cells", "BIGINT"), ("n_dup_cells", "BIGINT"),
        ("chk_p0_spread", "DOUBLE"),       # spread of x - x_trans etc. within the event
        ("chk_pt_spread", "DOUBLE"),       # spread of p, theta, phi, bin within the event
        ("chk_bin_rule", "BIGINT"),        # rows with incoming_momentum_bin <> floor(p)
    ]
    return tuple(columns) + group1_columns(("a",))


#: The event table of a single-shower hit experiment: the shower-A names of the
#: two-shower table where the meaning is the same, the species and consistency
#: counts of the hit file, and Group-1 for shower ``a``.
EVENT_SINGLE_COLUMNS: tuple[tuple[str, str], ...] = _event_single_columns()


def _event_feature_columns() -> tuple[tuple[str, str], ...]:
    columns: list[tuple[str, str]] = [
        ("event_number", "INTEGER PRIMARY KEY"),   # event_id
        ("e1", "DOUBLE"),                          # incoming_momentum
        ("theta_a", "DOUBLE"), ("phi_a", "DOUBLE"),
        ("e1_bin", "UTINYINT"),                    # incoming_momentum_bin
        ("n_hits", "BIGINT"),                      # num_hits
        ("e_dep", "DOUBLE"),                       # total_hit_energy
    ]
    for code in ("abs", "trn", "loc"):
        columns += [(f"{name}{FEATURE_SUFFIX[code]}", "DOUBLE") for name in CORE_FEATURES]
    for code in ("abs", "trn", "loc"):
        columns += [(f"{name}{FEATURE_SUFFIX[code]}", "DOUBLE")
                    for name in ("numerical_density", "energy_density")]
    columns.append(("energy_class", "UTINYINT"))   # the file's trailing 'energy' label
    return tuple(columns)


#: The event table of an aggregated experiment: the 59 file columns, the shared
#: names for the kinematics, deposit and hit count so selections and the
#: response panels read every kind alike, and the trailing label renamed to what
#: it is.
EVENT_FEATURE_COLUMNS: tuple[tuple[str, str], ...] = _event_feature_columns()


def create_event_table(
    physical: str, columns: tuple[tuple[str, str], ...] = EVENT_COLUMNS
) -> str:
    """DDL for the per-event summary of additive sufficient statistics.

    The design property that makes the interactive metrics cheap: accuracy, MAE
    and RMSE over an arbitrary filtered subset of events are all of the form
    ``sum(numerator) / sum(denominator)``. Storing the numerators and
    denominators per event - once per segmentation network - means those
    metrics roll up *exactly* over any selection, from about 20 000 rows, with
    no re-scan of the 24 million hit rows. The angle and energy networks predict
    one value per shower, so those live here too, once per event and shower.
    The other kinds pass :data:`EVENT_SINGLE_COLUMNS` or
    :data:`EVENT_FEATURE_COLUMNS`, and two-shower derived version 2 passes
    :data:`EVENT_COLUMNS_V2`.
    """
    body = ",\n    ".join(f"{name} {sql_type}" for name, sql_type in columns)
    return f"CREATE TABLE IF NOT EXISTS {quote(physical)} (\n    {body}\n);"


# ------------------------------------------------- layer and profile tables --

#: Per-(event, shower, own-shower layer) sums: one row per populated layer.
#: ``kt = round(z_trans / layer pitch)``; u, v = ``x_local``, ``y_local``.
LAYERS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_number", "INTEGER"),
    ("shower", "UTINYINT"),        # 0 = A, 1 = B ('A+B' rows with B)
    ("kt", "UTINYINT"),
    ("e_dep", "DOUBLE"),
    ("n_cells", "INTEGER"),
    ("sum_eu", "DOUBLE"),          # Σ E·u
    ("sum_ev", "DOUBLE"),          # Σ E·v
    ("sum_erl", "DOUBLE"),         # Σ E·ρ, ρ = √(u² + v²)
    ("sum_erl2", "DOUBLE"),        # Σ E·ρ²
)

#: The profile axes of :data:`PROFILES_COLUMNS`.
PROFILE_AXIS_W = 0     # depth along the incident direction, bins of the layer pitch
PROFILE_AXIS_R = 1     # transverse radius ρ, 10 mm bins, last bin the overflow

#: Per-(event, shower, axis, bin) energy of the Local-frame footprint splat:
#: one row per populated bin. ``e`` is every sub-deposit landing in the bin;
#: ``e_wneg`` the part coming from hits at ``z_local < NEG_DEPTH_MM``, so the
#: notebook's convention (drop those hits) is a subtraction, not a second key.
PROFILES_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_number", "INTEGER"),
    ("shower", "UTINYINT"),
    ("axis", "UTINYINT"),
    ("bin", "SMALLINT"),
    ("e", "DOUBLE"),
    ("e_wneg", "DOUBLE"),
)


def create_layers_table(physical: str) -> str:
    body = ",\n    ".join(f"{name} {sql_type}" for name, sql_type in LAYERS_COLUMNS)
    return f"CREATE TABLE IF NOT EXISTS {quote(physical)} (\n    {body}\n);"


def create_profiles_table(physical: str) -> str:
    body = ",\n    ".join(f"{name} {sql_type}" for name, sql_type in PROFILES_COLUMNS)
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
    # --- appended for the three-schema extension ---------------------------
    ("derived_version", "INTEGER"),   # layout generation of the derived tables; NULL = 1
    ("capabilities", "VARCHAR"),      # JSON: what ingest measured that the API advertises
)

REGISTRY_COLUMNS: tuple[str, ...] = tuple(name for name, _ in REGISTRY_SCHEMA)

CREATE_REGISTRY = (
    'CREATE TABLE IF NOT EXISTS "experiment" (\n    '
    + ",\n    ".join(f"{name} {sql_type}" for name, sql_type in REGISTRY_SCHEMA)
    + "\n);"
)


def drop_table(physical: str) -> str:
    return f"DROP TABLE IF EXISTS {quote(physical)};"
