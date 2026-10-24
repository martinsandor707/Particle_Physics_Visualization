"""Group-1: per-shower sums from which every per-frame feature of core.py is rebuilt.

``core.calc_all_features_v3`` (reference_ipynb_notebooks/core.py:459-574)
computes seventeen spatial features per frame from one event's hits. Each is a
function of a handful of sums - min and max per axis, Σ E·X, Σ r, the sample
SDs of r, θ and φ - so the event table stores those sums once per shower and
frame (the column vocabulary is ``ddl.GROUP1_*``) and :func:`feature_sql`
rebuilds the features in SQL, to 1e-9 of the producer's own aggregate file.

SQL text only: the ingest stages run it, the feature routes read
:func:`feature_sql`, and no formula is written twice.

The per-hit expressions follow core.py exactly:

* r = √(x² + y² + z²) in the frame's own coordinates, evaluated left to right
  as numpy does;
* θ = arccos(clip(z / (r or 10⁻⁶), −1, 1)) - the clamp also keeps DuckDB's
  ``acos`` inside its domain;
* φ = atan2(y, x), circular. Its *linear* sums exist only so core's arithmetic
  ``avg_phi`` and ``angular_spread`` can be reproduced for parity; the
  sanctioned summaries are ``sum_cos_phi`` and ``sum_sin_phi``;
* the SDs are ``stddev_samp`` (ddof = 1, pandas' default), not recovered from
  Σr²: with r ≈ 4000 mm and SD(r) ≈ 0.35 mm the cancellation would cost 10⁻⁵.
"""

from __future__ import annotations

from .ddl import GROUP1_FRAMES, NEG_DEPTH_MM, group1_column

#: Each frame's coordinate columns in the archive, and their prefix in :func:`hit_sql`.
FRAME_COORDS: dict[str, tuple[str, str, str]] = {
    "abs": ("x", "y", "z"),
    "trn": ("x_trans", "y_trans", "z_trans"),
    "loc": ("x_local", "y_local", "z_local"),
}
_PREFIX = {"abs": "a", "trn": "t", "loc": "l"}

#: core.py's ``eps``.
EPS = 1e-6

#: The seventeen per-frame features, in core.py's key order, and the two densities.
FEATURES: tuple[str, ...] = (
    "width", "height", "depth", "depth_range", "volume",
    "centroid_x", "centroid_y", "centroid_z",
    "mean_r", "std_r", "max_r", "weighted_r_mean",
    "avg_theta", "avg_phi", "angular_spread",
    "numerical_density", "energy_density",
)


def _member_sql(member: str | None) -> str:
    return "TRUE" if member is None else f"({member})"


def hit_sql(source: str, keep: str, members: dict[str, str | None]) -> str:
    """One row per kept hit: energy, membership flags, and r, θ, φ in every frame.

    ``members`` maps a shower key to the archive predicate selecting its rows,
    ``None`` meaning every row (a single-shower experiment).
    """
    flags = ", ".join(f"{_member_sql(m)} AS m_{s}" for s, m in members.items())
    coords = ", ".join(
        f"CAST({col} AS DOUBLE) AS {_PREFIX[f]}{axis}"
        for f in GROUP1_FRAMES for axis, col in zip("xyz", FRAME_COORDS[f])
    )
    radii = ", ".join(
        f"sqrt({p}x * {p}x + {p}y * {p}y + {p}z * {p}z) AS r_{f}"
        for f, p in _PREFIX.items()
    )
    angles = ", ".join(
        f"acos(greatest(-1.0, least(1.0, {p}z / CASE WHEN r_{f} = 0 THEN {EPS!r} ELSE r_{f} END))) "
        f"AS th_{f}, atan2({p}y, {p}x) AS ph_{f}"
        for f, p in _PREFIX.items()
    )
    return (
        f"SELECT *, {angles}, sqrt(lx * lx + ly * ly) AS rl FROM ("
        f"SELECT *, {radii} FROM ("
        f"SELECT event_number, energy, {flags}, {coords} FROM {source} WHERE {keep}))"
    )


def aggregates(shower: str, filtered: bool) -> dict[str, str]:
    """Column name -> aggregate SQL for one shower's Group-1 sums (the cell count excluded).

    ``filtered`` restricts every aggregate to the shower's rows (``m_<s>``);
    without it every row belongs to the shower. A shower with no rows has
    NULL sums, zero counts and zero energy.
    """
    def f(extra: str | None = None) -> str:
        terms = ([f"m_{shower}"] if filtered else []) + ([extra] if extra else [])
        return f" FILTER (WHERE {' AND '.join(terms)})" if terms else ""

    neg = f"lz < {NEG_DEPTH_MM!r}"
    col = lambda stem, frame=None: group1_column(stem, shower, frame)  # noqa: E731
    out = {
        col("n_hits"): f"count(*){f()}",
        col("e_dep"): f"coalesce(sum(energy){f()}, 0.0)",
        col("w_neg_hits"): f"count(*){f(neg)}",
        col("w_neg_energy"): f"coalesce(sum(energy){f(neg)}, 0.0)",
        col("sum_e_rl"): f"sum(energy * rl){f()}",
        col("sum_e_rl2"): f"sum(energy * (lx * lx + ly * ly)){f()}",
    }
    for frame, p in _PREFIX.items():
        x, y, z = f"{p}x", f"{p}y", f"{p}z"
        r, th, ph = f"r_{frame}", f"th_{frame}", f"ph_{frame}"
        out.update({
            col("x_min", frame): f"min({x}){f()}", col("x_max", frame): f"max({x}){f()}",
            col("y_min", frame): f"min({y}){f()}", col("y_max", frame): f"max({y}){f()}",
            col("z_min", frame): f"min({z}){f()}", col("z_max", frame): f"max({z}){f()}",
            col("sum_ex", frame): f"sum(energy * {x}){f()}",
            col("sum_ey", frame): f"sum(energy * {y}){f()}",
            col("sum_ez", frame): f"sum(energy * {z}){f()}",
            col("sum_r", frame): f"sum({r}){f()}",
            col("sum_r2", frame): f"sum({r} * {r}){f()}",
            col("sd_r", frame): f"stddev_samp({r}){f()}",
            col("max_r", frame): f"max({r}){f()}",
            col("sum_er", frame): f"sum(energy * {r}){f()}",
            col("sum_theta", frame): f"sum({th}){f()}",
            col("sum_theta2", frame): f"sum({th} * {th}){f()}",
            col("sd_theta", frame): f"stddev_samp({th}){f()}",
            col("sum_phi", frame): f"sum({ph}){f()}",
            col("sd_phi", frame): f"stddev_samp({ph}){f()}",
            col("sum_cos_phi", frame): f"sum(cos({ph})){f()}",
            col("sum_sin_phi", frame): f"sum(sin({ph})){f()}",
        })
    return out


def scan_sql(source: str, keep: str, members: dict[str, str | None]) -> str:
    """``SELECT event_number, <every shower's sums> ... GROUP BY event_number``."""
    filtered = len(members) > 1 or any(m is not None for m in members.values())
    parts = []
    for shower in members:
        parts += [f"{sql} AS {name}" for name, sql in aggregates(shower, filtered).items()]
    return (f"SELECT event_number, {', '.join(parts)} "
            f"FROM ({hit_sql(source, keep, members)}) GROUP BY event_number")


def feature_sql(feature: str, frame: str, shower: str = "a", alias: str = "") -> str:
    """One core.py feature of one shower in one frame, from the stored sums.

    The ``sum_r = 0`` branch of core.py (one hit sitting at the frame origin,
    which only the per-shower frames' P0 hit can) is reproduced: r, θ and φ
    statistics are zero there. ``std_r`` of a single hit is NULL, as pandas'
    ddof = 1 SD is NaN.
    """
    p = f"{alias}." if alias else ""

    def c(stem: str, per_frame: bool = True) -> str:
        return p + group1_column(stem, shower, frame if per_frame else None)

    n = c("n_hits", False)
    e = c("e_dep", False)
    width = f"greatest({c('x_max')} - {c('x_min')}, {EPS!r})"
    height = f"greatest({c('y_max')} - {c('y_min')}, {EPS!r})"
    depth = f"greatest({c('z_max')}, {EPS!r})"
    volume = f"({width} * {height} * {depth})"
    flat = f"{c('sum_r')} = 0"
    exprs = {
        "width": width,
        "height": height,
        "depth": depth,
        "depth_range": f"greatest({c('z_max')} - {c('z_min')}, {EPS!r})",
        "volume": volume,
        "centroid_x": f"CASE WHEN {e} > 0 THEN {c('sum_ex')} / {e} END",
        "centroid_y": f"CASE WHEN {e} > 0 THEN {c('sum_ey')} / {e} END",
        "centroid_z": f"CASE WHEN {e} > 0 THEN {c('sum_ez')} / {e} END",
        "mean_r": f"CASE WHEN {flat} THEN 0.0 ELSE {c('sum_r')} / {n} END",
        "std_r": f"CASE WHEN {flat} THEN 0.0 ELSE {c('sd_r')} END",
        "max_r": f"CASE WHEN {flat} THEN 0.0 ELSE {c('max_r')} END",
        "weighted_r_mean": f"CASE WHEN {e} > 0 THEN {c('sum_er')} / {e} END",
        "avg_theta": f"CASE WHEN {flat} THEN 0.0 ELSE {c('sum_theta')} / {n} END",
        "avg_phi": f"CASE WHEN {flat} THEN 0.0 ELSE {c('sum_phi')} / {n} END",
        "angular_spread": f"CASE WHEN {flat} THEN 0.0 ELSE {c('sd_theta')} + {c('sd_phi')} END",
        "numerical_density": f"({n} / {volume})",
        "energy_density": f"({e} / {volume})",
    }
    if feature not in exprs:
        raise ValueError(f"unknown Group-1 feature {feature!r}")
    return exprs[feature]


def circular_mean_sql(frame: str, shower: str = "a", alias: str = "") -> str:
    """The mean direction of φ, atan2(Σ sin φ, Σ cos φ): the sanctioned summary."""
    p = f"{alias}." if alias else ""
    return (f"atan2({p}{group1_column('sum_sin_phi', shower, frame)}, "
            f"{p}{group1_column('sum_cos_phi', shower, frame)})")


def resultant_sql(frame: str, shower: str = "a", alias: str = "") -> str:
    """The mean resultant length R̄ of φ, in [0, 1]."""
    p = f"{alias}." if alias else ""
    c = f"{p}{group1_column('sum_cos_phi', shower, frame)}"
    s = f"{p}{group1_column('sum_sin_phi', shower, frame)}"
    n = f"{p}{group1_column('n_hits', shower)}"
    return f"(sqrt({c} * {c} + {s} * {s}) / {n})"
