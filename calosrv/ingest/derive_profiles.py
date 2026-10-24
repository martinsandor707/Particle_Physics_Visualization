"""``profiles_<name>``: each shower's depth and radial energy profile, splatted.

The C7 profiles are per-shower fractions of energy along w (depth along the
incident direction) and ρ (transverse radius) in the Local frame. A cell is
48 × 48 mm against 10 mm radial bins, so binning its centre would leave the
empty-bin comb CLAUDE.md section 2 forbids. Each hit is therefore split into
``k × k × k_z`` sub-deposits over its measured footprint box and the layer
pitch, rotated by its own shower's R(θ, φ) - the construction of the Local
frame's display (``query/shower_frames.py``), so the profiles and the depth
panels agree - and binned:

* **w**: bins of one layer pitch anchored at w = 0, ``floor(w / pitch)``,
  negative bins kept. Every sub-deposit lands in a bin, so no energy is ever
  outside.
* **ρ**: 10 mm bins 0-49 (0-500 mm, the notebook's range) and bin 50 for
  everything beyond.

One row per (event, shower, axis, bin): ``e`` is every sub-deposit in the bin,
``e_wneg`` the part from hits at ``z_local < NEG_DEPTH_MM`` - so the
notebook's convention of dropping those hits is ``e - e_wneg``, and a shower's
fraction in a bin is one value, squared once, whichever convention is drawn.

``k = 6``: the projected spacing of 48.6 / 6 = 8.1 mm is under the 10 mm ρ
bin, so no ρ bin can fall between sub-deposits. ``k_z = 2`` is the Local
frame's depth factor. The comb is measured on the pooled profiles here and
recorded; the query re-measures per selection.
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb
import numpy as np

from ..db import naming
from ..db.ddl import (
    KIND_TWO_SHOWER, NEG_DEPTH_MM, PROFILE_AXIS_R, PROFILE_AXIS_W, PROFILES_COLUMNS,
    create_profiles_table, drop_table,
)
from ..db.naming import quote
from ..query import stagger
from .derive_layers import shower_sql
from .derive_proj import keep_predicate

log = logging.getLogger(__name__)

PROFILE_K = 6
PROFILE_K_Z = 2
R_BIN_MM = 10.0
R_BINS = 50                 # 0 .. 49; bin 50 holds rho >= 500 mm
COMB_THRESHOLD = -0.10


def _own(kind: str, a: str, b: str, single: str) -> str:
    if kind == KIND_TWO_SHOWER:
        return f"CASE WHEN particle_origin = 'A' THEN {a} ELSE {b} END"
    return single


def build(con: duckdb.DuckDBPyConnection, name: str, source: str, layer_pitch_mm: float,
          footprint_mm: tuple[float, float], kind: str = KIND_TWO_SHOWER,
          k: int = PROFILE_K, k_z: int = PROFILE_K_Z) -> dict[str, Any]:
    """Create ``profiles_<name>``; returns the spec and comb the catalogue records."""
    physical = naming.profiles_table(name)
    con.execute(drop_table(physical))
    con.execute(create_profiles_table(physical))
    wx, wy = (float(v) for v in footprint_mm)
    pitch = float(layer_pitch_mm)
    theta = _own(kind, "incoming_theta_A", "incoming_theta_B", "incoming_theta")
    phi = _own(kind, "incoming_phi_A", "incoming_phi_B", "incoming_phi")
    n = int(k) * int(k) * int(k_z)
    log.info("Building %s (Local splat k=%d, k_z=%d, %d sub-deposits per hit)",
             physical, k, k_z, n)
    con.execute(
        f"""
        INSERT INTO {quote(physical)} ({', '.join(c for c, _ in PROFILES_COLUMNS)})
        WITH h AS (
            SELECT event_number, {shower_sql(kind)} AS b,
                   z_local < {NEG_DEPTH_MM!r} AS neg,
                   CAST(x_local AS DOUBLE) AS xl, CAST(y_local AS DOUBLE) AS yl,
                   CAST(z_local AS DOUBLE) AS zl,
                   CAST({theta} AS DOUBLE) AS t, CAST({phi} AS DOUBLE) AS f,
                   energy / {n}.0 AS v
            FROM {source} WHERE {keep_predicate(origin=kind == KIND_TWO_SHOWER)}
        ), r AS (
            SELECT event_number, b, neg, v, xl, yl, zl,
                   cos(t) * cos(f) AS r11, cos(t) * sin(f) AS r12, -sin(t) AS r13,
                   -sin(f) AS r21, cos(f) AS r22,
                   sin(t) * cos(f) AS r31, sin(t) * sin(f) AS r32, cos(t) AS r33
            FROM h
        ), sub AS (
            SELECT ((u.range + 0.5) / {k} - 0.5) * {wx!r}::DOUBLE AS ox,
                   ((v.range + 0.5) / {k} - 0.5) * {wy!r}::DOUBLE AS oy,
                   ((w.range + 0.5) / {k_z} - 0.5) * {pitch!r}::DOUBLE AS oz
            FROM range({k}) u, range({k}) v, range({k_z}) w
        ), keyed AS (
            SELECT event_number, b, neg, v,
                   CAST(floor((zl + r31 * ox + r32 * oy + r33 * oz) / {pitch!r}) AS INTEGER) AS jw,
                   CAST(least(floor(sqrt((xl + r11 * ox + r12 * oy + r13 * oz) ** 2
                                         + (yl + r21 * ox + r22 * oy) ** 2) / {R_BIN_MM!r}),
                              {R_BINS}) AS INTEGER) AS jr
            FROM r, sub
        )
        SELECT event_number, CAST(b AS UTINYINT) AS shower,
               CAST(CASE WHEN GROUPING(jw) = 0 THEN {PROFILE_AXIS_W} ELSE {PROFILE_AXIS_R} END
                    AS UTINYINT) AS axis,
               CAST(coalesce(jw, jr) AS SMALLINT) AS bin,
               sum(v) AS e,
               coalesce(sum(v) FILTER (WHERE neg), 0.0) AS e_wneg
        FROM keyed
        GROUP BY GROUPING SETS ((event_number, b, jw), (event_number, b, jr))
        ORDER BY event_number, shower, axis, bin
        """
    )
    rows = int(con.execute(f"SELECT count(*) FROM {quote(physical)}").fetchone()[0])
    comb = measure_comb(con, name)
    log.info("%s holds %s rows; pooled-profile lag-1 w %s, r %s", physical, f"{rows:,}",
             comb.get("w"), comb.get("r"))
    return {
        "k": int(k), "k_z": int(k_z), "w_bin_mm": pitch, "r_bin_mm": R_BIN_MM,
        "r_bins": R_BINS, "footprint_mm": [wx, wy], "rows": rows, "comb": comb,
        "neg_depth_mm": NEG_DEPTH_MM,
    }


def measure_comb(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, Any]:
    """Lag-1 autocorrelation of the detrended pooled profile on each axis."""
    out: dict[str, Any] = {"threshold": COMB_THRESHOLD, "measured_on": "pooled ingest profile"}
    for key, axis in (("w", PROFILE_AXIS_W), ("r", PROFILE_AXIS_R)):
        rows = con.execute(
            f"SELECT bin, sum(e) FROM {quote(naming.profiles_table(name))} "
            f"WHERE axis = {axis} GROUP BY bin ORDER BY bin"
        ).fetchall()
        if not rows:
            out[key] = None
            continue
        lo, hi = int(rows[0][0]), int(rows[-1][0])
        dense = np.zeros(hi - lo + 1)
        for b, e in rows:
            dense[int(b) - lo] = float(e or 0.0)
        if key == "r":
            dense = dense[:-1] if hi == R_BINS else dense    # the overflow bin is not a profile bin
        out[key] = stagger.profile_lag1(dense)
    return out
