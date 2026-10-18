"""The windowed ensemble axis of the absolute frame's depth panels.

In detector coordinates no averaged direction is drawn over the whole face:
the incident azimuth is near-uniform there (mean resultant length 0.012 on
the production file), so a mean would point somewhere arbitrary. The
measurement behind this module says *why* it is uniform, and where it is
not. Measured on the production event table (20,268 events with a defined
separation):

* over the whole face the mean projected slope is +0.006 against a sample
  SD of 0.380 (shower A; B alike): a confidently zero lean, true and empty;
* the directions point at the detector origin: each shower's azimuth equals
  the azimuth of its own position, ``phi = atan2(y, x)``, with a resultant
  length of 1.000, and ``tan(theta) * z = r`` (the centroid's ``r / tan theta``
  is 3,860 mm against its own z of 3,892 mm). The residual against that
  radial line is 1.8 degrees SD. The azimuth is uniform over the face only
  because the entry positions are;
* so the directions of the showers entering one *window* are coherent: in
  300 mm windows of the entry position (262 windows holding 20 events or
  more) the median azimuth resultant is 0.999, the mean lean over the depth
  346 mm against a 33 mm dispersion band, and the 95 % envelope of the mean
  about 8 mm at N = 65.

The axis of a window is therefore the same kind of mark the D-frame draws,
licensed the same way, by measurement: the events whose **entry point** -
the 3-D centroid back-projected to the front face along the incident
direction, as the per-event trajectories are drawn - lies in the panel's
displayed transverse window; their **mean trajectory** through their mean
entry point; the **sample SD of the per-event trajectories at each depth**
(entry spread, slope spread and their covariance, so the band is exact
rather than a wedge from a point) as an uncapped band; and the **Student-t
95 % interval of the mean** as a thin envelope. The two differ by sqrt N and
each names its quantity.

**The gate is the lean against the fan.** A Rayleigh test on the azimuth
misjudges a depth panel's window, which is a strip across the whole face:
for a strip through y = 0 the azimuth flips between 0 and pi while every
projected slope is the same. The projected slopes are plain numbers, so the
honest question is whether the mean lean carries information beyond the fan:
the axis is drawn in full when |mean slope| >= SD of the slopes
(``LEAN_RATIO_MIN``), faded otherwise with the reason stated - "these
showers go straight on average, within a fan of this width". The azimuth
resultant and its Rayleigh p are reported for the record, not used as the
gate. Below two events nothing is an ensemble: one event gets its own
trajectory labelled as such; two get a band with one degree of freedom,
said so; fewer than twenty are labelled weak, as the D-frame's table does.
"""

from __future__ import annotations

import math
import time
from typing import Any

import duckdb

from ..db import naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..grid import frame as frame_mod
from ..text import typographic
from .filters import FilterSpec

#: The depth panels and the transverse coordinate each one plots.
PANELS: dict[str, str] = {"yz": "y", "xz": "x"}

#: The mean lean must reach this many sample SDs of the slopes to be drawn in full.
LEAN_RATIO_MIN = 1.0

#: Depth stations the band and envelope are evaluated at (the band is exact at each).
STATIONS = 9

_SHOWERS = {"a": "A", "b": "B"}


def _finite(value: Any) -> bool:
    return value is not None and math.isfinite(float(value))


def _query(con, table: str, where: str, params: dict[str, Any], shower: str, axis: str) -> dict[str, Any]:
    """One shower's aggregates over the events entering the window."""
    th, ph = f"CAST(theta_{shower} AS DOUBLE)", f"CAST(phi_{shower} AS DOUBLE)"
    cx, cy, cz = (f"CAST(c{shower}{a} AS DOUBLE)" for a in "xyz")
    te = "xe" if axis == "x" else "ye"
    st = "sx" if axis == "x" else "sy"
    row = con.execute(
        f"""
        WITH ev AS (
            SELECT {th} AS th, {ph} AS ph, {cx} AS cx, {cy} AS cy, {cz} AS cz
            FROM {table}
            WHERE {where} AND theta_{shower} IS NOT NULL AND phi_{shower} IS NOT NULL
              AND c{shower}x IS NOT NULL AND c{shower}y IS NOT NULL AND c{shower}z IS NOT NULL
        ), dir AS (
            SELECT *, tan(th) * cos(ph) AS sx, tan(th) * sin(ph) AS sy FROM ev
        ), face AS (
            -- The 3-D centroid back-projected to the front face along the incident direction.
            SELECT *, cx - (cz - $zf) * sx AS xe, cy - (cz - $zf) * sy AS ye FROM dir
        ), win AS (
            SELECT *, {te} AS te, {st} AS st, atan({st}) AS alpha
            FROM face WHERE {te} >= $t0 AND {te} <= $t1
        )
        SELECT (SELECT count(*) FROM face)          AS n_selection,
               count(*)                             AS n,
               avg(te), var_samp(te),
               avg(st), var_samp(st), covar_samp(te, st),
               avg(cos(ph)), avg(sin(ph)),
               stddev_samp(alpha),
               avg(xe), avg(ye)
        FROM win
        """,
        params,
    ).fetchone()
    keys = ("n_selection", "n", "t_mean", "t_var", "s_mean", "s_var", "cov", "cos_mean", "sin_mean",
            "alpha_sd", "x_mean", "y_mean")
    return dict(zip(keys, row))


def _block(agg: dict[str, Any], shower: str, z_front: float, depth_max: float,
           t_min: float, t_max: float) -> dict[str, Any]:
    """The payload block of one shower: the axis, its band, its envelope and their numbers."""
    n = int(agg["n"] or 0)
    out: dict[str, Any] = {
        "n": n,
        "n_selection": int(agg["n_selection"] or 0),
        "anchor": None,
        "slope": None, "slope_sd": None, "se95": None,
        "lean_ratio": None, "fan_deg": None,
        "resultant_azimuth": None, "rayleigh_p": None,
        "faded": False, "label": "", "dof_note": None,
        "axis": None, "band": None, "envelope": None,
    }
    if n == 0 or not _finite(agg["t_mean"]) or not _finite(agg["s_mean"]):
        return out
    t_mean, s_mean = float(agg["t_mean"]), float(agg["s_mean"])
    span = depth_max - z_front
    out["anchor"] = {"t": t_mean, "z": z_front, "x": agg["x_mean"], "y": agg["y_mean"], "sd": None, "se95": None}
    out["slope"] = s_mean
    out["axis"] = [[z_front, t_mean], [depth_max, t_mean + s_mean * span]]
    if n == 1:
        out["label"] = "single event, not an ensemble"
        return out

    ensemble = n >= 2
    t_var = max(0.0, float(agg["t_var"] or 0.0))
    s_var = max(0.0, float(agg["s_var"] or 0.0))
    cov = float(agg["cov"] or 0.0)
    s_sd = math.sqrt(s_var)
    t_value = frame_mod.t_quantile_975(n - 1)
    root_n = math.sqrt(n)
    out["anchor"]["sd"] = math.sqrt(t_var)
    out["anchor"]["se95"] = t_value * math.sqrt(t_var) / root_n
    out["slope_sd"] = s_sd
    out["se95"] = t_value * s_sd / root_n
    out["fan_deg"] = math.degrees(float(agg["alpha_sd"])) if _finite(agg["alpha_sd"]) else None
    if _finite(agg["cos_mean"]) and _finite(agg["sin_mean"]):
        resultant = math.hypot(float(agg["cos_mean"]), float(agg["sin_mean"]))
        out["resultant_azimuth"] = resultant
        out["rayleigh_p"] = frame_mod.rayleigh_p(n, resultant)
    # The sample SD of the per-event trajectory position at each depth: the
    # entry spread, the slope spread and their covariance, exact at every station.
    band, envelope = [], []
    for k in range(STATIONS):
        dz = span * k / (STATIONS - 1)
        centre = t_mean + s_mean * dz
        var = max(0.0, t_var + 2.0 * dz * cov + dz * dz * s_var)
        sd = math.sqrt(var)
        se = t_value * sd / root_n
        band.append([z_front + dz, centre - sd, centre + sd])
        envelope.append([z_front + dz, centre - se, centre + se])
    out["band"], out["envelope"] = band, envelope
    if s_sd > 0:
        ratio = abs(s_mean) / s_sd
        out["lean_ratio"] = ratio
        out["faded"] = ratio < LEAN_RATIO_MIN
    else:
        # Identical slopes: no fan at all, so the lean is as coherent as it gets.
        out["lean_ratio"] = None
        out["faded"] = False
    if n == 2:
        out["dof_note"] = "1 d.o.f."
    if ensemble and n < frame_mod.PROVISIONAL_N:
        out["label"] = f"weak (N = {n})"
    return out


def _note(block: dict[str, Any], shower: str, axis: str, t_min: float, t_max: float) -> str:
    name = _SHOWERS[shower]
    n = block["n"]
    window = f"{axis} ∈ [{t_min:.0f}, {t_max:.0f}] mm"
    if n == 0:
        return typographic(f"Shower {name}: no selected event enters the window {window}; no axis is drawn.")
    head = f"Shower {name}: N = {n:,} of {block['n_selection']:,} selected events enter the window {window}"
    if n == 1:
        return typographic(f"{head}; the dashed line is that event's own incident trajectory, not an ensemble, "
                           "so no dispersion band or interval can be drawn.")
    lean = f"mean lean {block['slope']:+.4f} ± {block['slope_sd']:.4f} SD"
    fan = f"fan ± {block['fan_deg']:.1f}°" if _finite(block["fan_deg"]) else "fan undefined"
    ratio = block["lean_ratio"]
    if ratio is None:
        verdict = "every direction identical, drawn in full"
    elif block["faded"]:
        verdict = (f"lean / fan = {ratio:.2f} < {LEAN_RATIO_MIN:g}: these showers go straight on average within "
                   "that fan, so the axis is drawn faded")
    else:
        verdict = f"lean / fan = {ratio:.2f} ≥ {LEAN_RATIO_MIN:g}, drawn in full"
    dof = f" ({block['dof_note']})" if block["dof_note"] else ""
    weak = f"; {block['label']}" if block["label"] else ""
    return typographic(f"{head}; {lean}{dof}, {fan}; {verdict}{weak}.")


RULE = (
    "Windowed ensemble axis: the selected events whose entry point (3-D centroid back-projected to the "
    "front face along the incident direction) lies in this panel's displayed transverse window. Dashed "
    "line: their mean trajectory through their mean entry point. Shaded band: the sample SD of the "
    "per-event trajectories at each depth (entry spread, slope spread and their covariance). Thin "
    "envelope: the Student-t 95% interval of the mean. Drawn in full when the mean lean reaches one SD "
    "of the slopes, faded otherwise; the azimuth resultant and Rayleigh p are reported, not used as the "
    "gate, because a strip across the face flips the azimuth while the projected slope stays coherent."
)


def window_axis(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    panel: str,
    t_min: float,
    t_max: float,
) -> dict[str, Any]:
    """The two showers' windowed axes on one depth panel, over the events entering ``[t_min, t_max]``."""
    if panel not in PANELS:
        raise ValidationError(f"panel must be one of {', '.join(PANELS)}; got {panel!r}.", field="panel")
    if not (_finite(t_min) and _finite(t_max)) or not float(t_max) > float(t_min):
        raise ValidationError("t_min and t_max must be finite with t_max above t_min.", field="t_min")
    assert record.lattice is not None
    started = time.perf_counter()
    axis = PANELS[panel]
    z_front = float(record.lattice.z.lo)
    depth_max = float(record.lattice.z.hi)
    table = quote(naming.event_table(record.table_name))
    where = spec.where_sql()
    params = {**spec.params(), "zf": z_front, "t0": float(t_min), "t1": float(t_max)}
    blocks = {s: _block(_query(con, table, where, params, s, axis), s, z_front, depth_max, t_min, t_max)
              for s in _SHOWERS}
    return {
        "panel": panel,
        "axis": axis,
        "window": [float(t_min), float(t_max)],
        "z_front": z_front,
        "depth_max": depth_max,
        "stations": STATIONS,
        "lean_ratio_min": LEAN_RATIO_MIN,
        "a": blocks["a"],
        "b": blocks["b"],
        "notes": [_note(blocks[s], s, axis, t_min, t_max) for s in _SHOWERS],
        "rule": RULE,
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
    }
