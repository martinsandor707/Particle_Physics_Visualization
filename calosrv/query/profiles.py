"""C7: the longitudinal (w) and radial (ρ) energy profiles of showers.

A shower's profile is the fraction of its own energy per bin of depth w along
its incident direction, or of transverse radius ρ = √(u² + v²) from that
direction, in the Local frame. Ingest stores every shower's profiles once,
footprint-splatted into sub-deposits so no 10 mm ρ bin falls in a gap between
48 mm cells (``ingest/derive_profiles.py``: one ``profiles_<name>`` row per
event, shower, axis and bin, holding ``e`` and the part ``e_wneg`` from hits
behind the entry plane). A selection's profile is a roll-up of those rows - a
few hundred numbers - never a hit scan. ``depth=native`` replaces w with each
shower's own layers from ``layers_<name>``: the per-shower translated depth,
neither rotated nor splatted.

Two estimators answer two questions, and CLAUDE.md section 2 keeps their
marks apart:

* the **per-shower mean**, every shower weighing the same, is the primary
  line. Its marks are the uncapped **SD band** of the per-shower fractions
  (ddof = 1: where individual showers lie) and the capped **Student-t
  envelope** of the mean (how well the mean is known). The two showers of a
  two-shower event share its geometry, so with both selected the envelope is
  cluster-robust with the event as the cluster (``stats/profile.py``);
* the **pooled ratio of sums** Σe / ΣE - the notebook's estimator, energy
  weighted, so high-momentum showers dominate it - is the secondary dashed
  line, with its own capped interval: the linearised ratio interval with
  events as clusters (``metrics.ratio_estimate``).

Everything is summed in SQL per bin: Σf and Σf² over showers for the band,
Σ_e c_e² and Σ_e M_e c_e over events for the cluster envelope, and the five
ratio sums for the pooled interval. A bin a shower never reached is a zero
fraction for that shower, so every sum is divided by the number of showers,
never by the rows present.

**Normalisation.** Each shower is divided by its own Group-1 deposit
``e_dep``, every hit kept, so its fractions sum to one over the bins of each
axis: energy outside the display window, or beyond ρ = 50 cm, stays in the
normaliser and is reported. The notebook's convention - drop the hits behind
the entry plane (``z_local < −1e−6 mm``) from both the bins and the total - is
the subtraction ``e − e_wneg`` over ``e_dep − w_neg_energy``, one value per
shower and bin either way, so the band is never built from split rows.

**w = 0.** The w bins are multiples of the layer pitch anchored at w = 0, so
no bin straddles the entry plane. The splat still moves energy across it -
half of a first-layer cell lies behind its centre - so the profile's own
energy below w = 0 is reported beside the hit-level fraction. The comb is
measured on the selection's raw pooled profile, every bin, before the display
window (``stagger.profile_lag1``).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..errors import ValidationError
from ..grid import frame as frame_mod
from ..stats import clip, metrics
from ..stats import profile as profile_stats
from ..text import fmt_signed, typographic
from . import physics_cache, stagger
from . import showers as showers_mod
from .filters import FilterSpec
from .hit_sql import layer_pitch
from .showers import ShowerColumns

#: The ``depth`` request parameter: Local-frame w, or each shower's own native layers.
DEPTHS: tuple[str, ...] = ("w", "native")

#: Bumped when the cached sums change meaning.
CACHE_VERSION = 1

#: The bin query's axis code of the native-layer rows (``profiles_`` uses 0 = w, 1 = ρ).
AXIS_KT = 2

#: Under the notebook convention a shower whose kept energy is below this
#: fraction of its deposit - every hit behind its entry plane - has no profile.
NORM_FLOOR = 1e-12

#: The derived-table columns this module reads, as their DDL names them
#: (``ddl.PROFILES_COLUMNS``, ``ddl.LAYERS_COLUMNS``); a test holds them to it.
PROFILE_READS: tuple[str, ...] = ("event_number", "shower", "axis", "bin", "e", "e_wneg")
LAYER_READS: tuple[str, ...] = ("event_number", "shower", "kt", "e_dep")

#: ρ binning when an experiment's record predates the recorded profile spec.
R_BIN_MM = 10.0
R_BINS = 50

_PERCENT = 100.0
_MM_PER_CM = 10.0


# ------------------------------------------------------------------- sums --

@dataclass
class AxisSums:
    """Per-bin sums of one axis over the selected showers, for the bins some shower reached."""

    bins: np.ndarray            # bin index, ascending
    sn: np.ndarray              # Σ_e num_e: the kept energy in the bin
    snn: np.ndarray             # Σ_e num_e²
    snd: np.ndarray             # Σ_e num_e · den_e
    c: np.ndarray               # Σ_i f_i, f the shower's fraction of its normaliser
    q: np.ndarray               # Σ_i f_i²
    cc: np.ndarray | None       # Σ_e c_e² (both showers of an event selected)
    mc: np.ndarray | None       # Σ_e M_e c_e
    n_present: np.ndarray       # showers with kept energy in the bin


@dataclass
class ProfileSums:
    """Everything a profile payload is rendered from: the cached value of one selection."""

    n_showers: int              # N: showers with a profile
    n_events: int               # G: events holding them, the clusters
    n_dropped: int              # showers without kept energy (notebook convention)
    m2: float                   # Σ_e M_e²
    den: float                  # Σ_e den_e = Σ_i E_i, the pooled normaliser
    den2: float                 # Σ_e den_e²
    n_single_cell: int          # showers depositing in one cell
    e_all: float                # Σ e_dep over every present shower
    e_neg: float                # Σ w_neg_energy over the same showers
    clustered: bool             # several showers per event: the event is the cluster
    axes: dict[str, AxisSums]


def _showers_ctes(record: ExperimentRecord, spec: FilterSpec,
                  picked: tuple[ShowerColumns, ...], notebook: bool) -> str:
    """``s0`` every selected shower with energy, ``s`` those with a profile, ``ev`` per event."""
    event = quote(naming.event_table(record.table_name))
    parts = []
    for s in picked:
        e_all = f"CAST({s.shower_energy} AS DOUBLE)"
        parts.append(
            f"SELECT event_number, {s.b} AS shower, {e_all} AS e_all, "
            f"coalesce(CAST({s.w_neg_energy} AS DOUBLE), 0.0) AS e_neg, "
            f"CAST({s.group1('n_cells')} AS BIGINT) AS n_cells "
            f"FROM {event} WHERE {spec.where_sql()} AND {e_all} > 0")
    norm = "e_all - e_neg" if notebook else "e_all"
    return (
        f"s0 AS ({' UNION ALL '.join(parts)}),\n"
        f"s AS (SELECT *, {norm} AS e_norm FROM s0 WHERE {norm} > {NORM_FLOOR!r} * e_all),\n"
        "ev AS (SELECT event_number, count(*) AS m, sum(e_norm) AS den FROM s GROUP BY event_number)"
    )


def _rows_sql(record: ExperimentRecord, depth: str) -> str:
    """The profile rows: both ``profiles_`` axes, or ρ and the native layers."""
    profiles = quote(naming.profiles_table(record.table_name))
    if depth == "w":
        return f"SELECT event_number, shower, axis, bin, e, e_wneg FROM {profiles}"
    layers = quote(naming.layers_table(record.table_name))
    return (f"SELECT event_number, shower, axis, bin, e, e_wneg FROM {profiles} "
            f"WHERE axis = {ddl.PROFILE_AXIS_R} "
            f"UNION ALL SELECT event_number, shower, {AXIS_KT} AS axis, kt AS bin, "
            f"e_dep AS e, 0.0 AS e_wneg FROM {layers}")


def _bins_sql(ctes: str, rows: str, notebook: bool, clustered: bool) -> str:
    """Per-(axis, bin) sums; with ``clustered``, rolled up per event first."""
    num = "pr.e - pr.e_wneg" if notebook else "pr.e"
    head = (f"WITH {ctes},\npr AS ({rows}),\n"
            f"u AS (SELECT pr.event_number, pr.axis, pr.bin, {num} AS num, "
            f"({num}) / s.e_norm AS f, s.e_norm AS den\n"
            "      FROM pr JOIN s ON s.event_number = pr.event_number AND s.shower = pr.shower)")
    if not clustered:
        # One shower per event: the shower is the cluster, and Σ_e c_e² = Σf².
        return (f"{head}\nSELECT axis, bin, sum(num), sum(num * num), sum(num * den), "
                "sum(f), sum(f * f), NULL, NULL, count(*) FILTER (WHERE num > 0)\n"
                "FROM u GROUP BY axis, bin ORDER BY axis, bin")
    return (f"{head},\ncell AS (SELECT event_number, axis, bin, sum(num) AS num, sum(f) AS c, "
            "sum(f * f) AS q, count(*) FILTER (WHERE num > 0) AS present\n"
            "      FROM u GROUP BY event_number, axis, bin)\n"
            "SELECT cell.axis, cell.bin, sum(cell.num), sum(cell.num * cell.num), "
            "sum(cell.num * ev.den), sum(cell.c), sum(cell.q), sum(cell.c * cell.c), "
            "sum(ev.m * cell.c), sum(cell.present)\n"
            "FROM cell JOIN ev USING (event_number) "
            "GROUP BY cell.axis, cell.bin ORDER BY cell.axis, cell.bin")


_AXIS_KEYS = {ddl.PROFILE_AXIS_W: "w", ddl.PROFILE_AXIS_R: "r", AXIS_KT: "kt"}


def compute_sums(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                 picked: tuple[ShowerColumns, ...], depth: str, notebook: bool) -> ProfileSums:
    """The selection's per-bin profile sums: two statements over the event and profile tables."""
    clustered = len(picked) > 1
    ctes = _showers_ctes(record, spec, picked, notebook)
    params = spec.params()
    row = con.execute(
        f"""WITH {ctes}
        SELECT (SELECT count(*) FROM s), (SELECT count(*) FROM ev), (SELECT count(*) FROM s0),
               (SELECT coalesce(sum(m * m), 0) FROM ev),
               (SELECT coalesce(sum(den), 0.0) FROM ev),
               (SELECT coalesce(sum(den * den), 0.0) FROM ev),
               (SELECT count(*) FILTER (WHERE n_cells = 1) FROM s),
               (SELECT coalesce(sum(e_all), 0.0) FROM s0),
               (SELECT coalesce(sum(e_neg), 0.0) FROM s0)""",
        params,
    ).fetchone()
    n, g, n_with_energy, m2, den, den2, single_cell, e_all, e_neg = row
    rows = con.execute(_bins_sql(ctes, _rows_sql(record, depth), notebook, clustered),
                       params).fetchall() if int(n) else []
    axes: dict[str, AxisSums] = {}
    codes = (ddl.PROFILE_AXIS_W, ddl.PROFILE_AXIS_R) if depth == "w" else (AXIS_KT, ddl.PROFILE_AXIS_R)
    for code in codes:
        mine = [r for r in rows if int(r[0]) == code]
        # Columns 2-8: sn, snn, snd, c, q, cc, mc (the last two NULL in the unit form).
        sums = np.asarray([[float(v or 0.0) for v in r[2:9]] for r in mine],
                          dtype=np.float64).reshape(-1, 7)
        axes[_AXIS_KEYS[code]] = AxisSums(
            bins=np.asarray([int(r[1]) for r in mine], dtype=np.int64),
            sn=sums[:, 0], snn=sums[:, 1], snd=sums[:, 2], c=sums[:, 3], q=sums[:, 4],
            cc=sums[:, 5] if clustered else None, mc=sums[:, 6] if clustered else None,
            n_present=np.asarray([int(r[9] or 0) for r in mine], dtype=np.int64),
        )
    return ProfileSums(
        n_showers=int(n), n_events=int(g), n_dropped=int(n_with_energy) - int(n), m2=float(m2),
        den=float(den), den2=float(den2), n_single_cell=int(single_cell),
        e_all=float(e_all), e_neg=float(e_neg), clustered=clustered, axes=axes,
    )


# ------------------------------------------------------------------ axes --

@dataclass(frozen=True)
class AxisPlan:
    """One drawn axis: which bins are displayed and how wide they are."""

    key: str                    # payload key: w | r | kt
    symbol: str
    label: str
    width_mm: float             # bin width
    lo: int                     # first displayed bin
    hi: int                     # last displayed bin, inclusive
    edge0_mm: float             # lower edge of bin ``lo``
    window_source: str          # where the displayed range comes from
    overflow: int | None = None  # ρ's overflow bin: not a profile bin

    @property
    def n_bins(self) -> int:
        return self.hi - self.lo + 1

    def edges_cm(self) -> list[float | None]:
        return sig_list((self.edge0_mm + i * self.width_mm) / _MM_PER_CM for i in range(self.n_bins + 1))


def profile_spec(record: ExperimentRecord) -> dict[str, Any]:
    """The splat and binning ingest recorded for the profiles (``capabilities.profiles``)."""
    measured = record.capabilities or {}
    spec = dict(measured.get("profiles") or {})
    if not spec.get("w_bin_mm"):
        spec["w_bin_mm"] = layer_pitch(record)
    spec.setdefault("r_bin_mm", R_BIN_MM)
    spec.setdefault("r_bins", R_BINS)
    spec.setdefault("footprint_mm", measured.get("footprint_mm"))
    return spec


def _w_plan(record: ExperimentRecord, width: float, sums: AxisSums) -> AxisPlan:
    """The Local frame's dataset-wide depth grid, so the profile lines up with the depth panels."""
    symbol, label = "w", "Depth w along the shower's incident direction (Local frame)"
    bounds = record.frame_bounds
    if bounds is not None and math.isclose(float(bounds.layer_pitch_mm), width, rel_tol=1e-9):
        footprint = tuple((record.capabilities or {}).get("footprint_mm") or (0.0, 0.0))
        grid = frame_mod.plan_shower_window(frame_mod.KIND_LOCAL, bounds, footprint)
        centres = np.asarray(grid.z_coords, dtype=np.float64)
        first = int(round(centres[0] / width - 0.5))
        return AxisPlan("w", symbol, label, width, first, first + int(centres.size) - 1,
                        first * width, "dataset")
    lo, hi = (int(sums.bins.min()), int(sums.bins.max())) if sums.bins.size else (0, 0)
    return AxisPlan("w", symbol, label, width, lo, hi, lo * width, "selection")


def _kt_plan(record: ExperimentRecord, width: float, sums: AxisSums) -> AxisPlan:
    """Each shower's own layers counted from its first: kt = 0 .. n_layers - 1."""
    if record.frame_bounds is not None:
        n_layers, source = int(record.frame_bounds.n_layers_trans), "dataset"
    else:
        n_layers, source = (int(sums.bins.max()) + 1 if sums.bins.size else 1), "selection"
    return AxisPlan("kt", "Δz", "Depth Δz = kt × layer pitch along each shower's own layers "
                    "(per-shower translated frame, not rotated)",
                    width, 0, max(0, n_layers - 1), -0.5 * width, source)


def _r_plan(width: float, n_bins: int) -> AxisPlan:
    return AxisPlan("r", "ρ", "Transverse radius ρ = √(u² + v²) from the incident axis (Local frame)",
                    width, 0, n_bins - 1, 0.0, "fixed", overflow=n_bins)


# ---------------------------------------------------------------- render --

def _dense(bins: np.ndarray, values: np.ndarray | None, lo: int, n: int) -> np.ndarray | None:
    """``values`` placed on bins ``lo .. lo + n - 1``; a bin nobody reached is zero."""
    if values is None:
        return None
    out = np.zeros(n, dtype=np.float64)
    keep = (bins >= lo) & (bins < lo + n)
    out[bins[keep] - lo] = values[keep]
    return out


def _over_under(lo: np.ndarray, hi: np.ndarray, y_hi: float) -> tuple[list[int], list[int]]:
    """Bins whose mark rises above the y range, and bins whose mark falls below zero."""
    over = [int(i) for i in np.flatnonzero(np.isfinite(hi) & (hi > y_hi * (1.0 + 1e-9)))]
    under = [int(i) for i in np.flatnonzero(np.isfinite(lo) & (lo < 0.0))]
    return over, under


def _comb(dense: np.ndarray, plan: AxisPlan, spec: dict[str, Any]) -> dict[str, Any]:
    """The lag-1 comb statistic of the selection's raw pooled profile.

    On the native layers it is recorded but never called a comb: one bin per
    layer cannot alias, so an alternation there would be the detector's own
    layer structure, not a binning artefact.
    """
    lag1 = stagger.profile_lag1(dense) if dense.size else None
    native = plan.key == "kt"
    ingest = ((spec.get("comb") or {}).get(plan.key)) if not native else None
    return {
        "lag1": sig(lag1, 4),
        "combed": None if lag1 is None or native else bool(lag1 < stagger.COMB_THRESHOLD),
        "threshold": stagger.COMB_THRESHOLD,
        "measured_on": ("pooled raw layer profile of this selection, every layer"
                        if native else
                        "pooled raw profile of this selection, every bin, before the display window"),
        "n_bins": int(dense.size),
        "ingest_lag1": sig(ingest, 4),
        "k": None if native else spec.get("k"),
        "k_z": None if native else spec.get("k_z"),
        "regime": "native_layers" if native else "local_subdeposit_splat",
    }


def _splat(plan: AxisPlan, spec: dict[str, Any]) -> dict[str, Any] | None:
    """How the hits were spread over the bins: k × k × k_z sub-deposits of the cell footprint."""
    if plan.key == "kt":
        return None
    k, k_z = spec.get("k"), spec.get("k_z")
    footprint = [float(v) for v in spec.get("footprint_mm") or ()] or None
    spacing = None
    if plan.key == "r" and k and footprint:
        spacing = max(footprint) / float(k)
    elif plan.key == "w" and k_z:
        spacing = float(spec.get("w_bin_mm", plan.width_mm)) / float(k_z)
    return {
        "regime": "local_subdeposit_splat", "k": k, "k_z": k_z,
        "footprint_mm": sig_list(footprint) if footprint else None,
        "bin_mm": sig(plan.width_mm), "spacing_mm": sig(spacing),
        "gap_free": None if spacing is None else bool(spacing <= plan.width_mm * (1.0 + 1e-9)),
    }


def _pooled_line(sn: np.ndarray, snn: np.ndarray, snd: np.ndarray, totals: ProfileSums,
                 scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, str | None]:
    """The pooled ratio of sums per bin and its Student-t interval, events as clusters."""
    value, lo, hi = (np.full(sn.size, np.nan) for _ in range(3))
    label = None
    if totals.n_showers == 0 or totals.den <= 0:
        return value, lo, hi, label
    for i in range(sn.size):
        r = metrics.ratio_estimate(sn[i], totals.den, snn[i], totals.den2, snd[i], totals.n_events)
        if r.value is not None:
            value[i] = r.value * scale
        if r.interval is not None:
            lo[i], hi[i] = r.interval.lo * scale, r.interval.hi * scale
            label = r.interval.label
    return value, lo, hi, label


def _range_mark(centre: np.ndarray, half: np.ndarray, y_hi: float) -> dict[str, Any]:
    """``centre ± half`` at its true values, with the bins the axis clips it at."""
    lo, hi = centre - half, centre + half
    over, under = _over_under(lo, hi, y_hi)
    return {"lo": sig_list(lo), "hi": sig_list(hi), "over": over, "under": under}


def _fractions(sums: AxisSums, totals: ProfileSums, mask: np.ndarray) -> tuple[float, float]:
    """``(pooled, per-shower mean)`` fraction of the energy in the bins ``mask`` selects."""
    pooled = float(sums.sn[mask].sum()) / totals.den if totals.den > 0 else 0.0
    mean = float(sums.c[mask].sum()) / totals.n_showers if totals.n_showers else 0.0
    return pooled, mean


def _outside(plan: AxisPlan, sums: AxisSums, totals: ProfileSums) -> dict[str, Any]:
    """The energy beyond the drawn bins: kept in every normaliser, reported here."""
    below = _fractions(sums, totals, sums.bins < plan.lo)
    above = _fractions(sums, totals, sums.bins > plan.hi)
    top_cm = sig((plan.edge0_mm + plan.n_bins * plan.width_mm) / _MM_PER_CM)
    out: dict[str, Any] = {
        "below_fraction": sig(below[0]), "above_fraction": sig(above[0]),
        "mean_below_fraction": sig(below[1]), "mean_above_fraction": sig(above[1]),
        "window_cm": [sig(plan.edge0_mm / _MM_PER_CM), top_cm],
        "window_source": plan.window_source,
    }
    if plan.overflow is not None:
        out["overflow_from_cm"] = top_cm
    return out


def _raw_profile(plan: AxisPlan, sums: AxisSums) -> np.ndarray:
    """The selection's pooled energy on every bin it reached, before any window.

    ρ runs from its first bin to the last before the overflow, which holds
    everything beyond 50 cm and is no profile bin.
    """
    if plan.overflow is not None:
        return _dense(sums.bins, sums.sn, 0, plan.overflow)
    if not sums.bins.size:
        return np.zeros(0)
    lo = int(sums.bins.min())
    return _dense(sums.bins, sums.sn, lo, int(sums.bins.max()) - lo + 1)


def _w_zero_rule(sums: AxisSums, totals: ProfileSums) -> dict[str, Any]:
    """Energy below w = 0, from the profile itself, beside the hit-level fraction behind it."""
    pooled, mean = _fractions(sums, totals, sums.bins < 0)
    return {
        "at_cm": 0.0,
        "bin_edge": True,
        "energy_fraction_below": sig(pooled),
        "mean_fraction_below": sig(mean),
        "hit_level_c9": sig(totals.e_neg / totals.e_all) if totals.e_all > 0 else None,
        "neg_depth_mm": ddl.NEG_DEPTH_MM,
    }


def render_axis(plan: AxisPlan, sums: AxisSums, totals: ProfileSums,
                spec: dict[str, Any]) -> tuple[dict[str, Any], profile_stats.ProfileEstimate]:
    """One axis of the payload: mean, band, envelope, pooled line, range and disclosures."""
    n, g = totals.n_showers, totals.n_events

    def dense(values: np.ndarray | None) -> np.ndarray | None:
        return _dense(sums.bins, values, plan.lo, plan.n_bins)

    c, q = dense(sums.c), dense(sums.q)
    if totals.clustered:
        est = profile_stats.profile_estimate(c, q, n, cc=dense(sums.cc), mc=dense(sums.mc),
                                             m2=totals.m2, n_clusters=g)
    else:
        est = profile_stats.profile_estimate(c, q, n)
    scale = _PERCENT * _MM_PER_CM / plan.width_mm         # fraction per bin -> % per cm
    mean = est.mean * scale
    pooled, p_lo, p_hi, p_label = _pooled_line(dense(sums.sn), dense(sums.snn), dense(sums.snd),
                                               totals, scale)

    # The y range follows the two lines, never the band or the intervals.
    shown = np.concatenate([mean[np.isfinite(mean)], pooled[np.isfinite(pooled)]])
    y_lo, y_hi, y_step = clip.nice_range(0.0, float(shown.max()) if shown.size else 0.0, fine=True)

    band = _range_mark(mean, est.sd * scale, y_hi) if est.sd is not None else None
    envelope = None
    if est.half95 is not None:
        envelope = {**_range_mark(mean, est.half95 * scale, y_hi), "t": sig(est.t_value, 5),
                    "dof": g - 1, "cluster": "event" if totals.clustered else "shower"}
    p_over, p_under = _over_under(p_lo, p_hi, y_hi)
    clipped = {
        "band": len(band["over"]) if band else 0,
        "envelope": len(envelope["over"]) if envelope else 0,
        "band_below_zero": len(band["under"]) if band else 0,
        "envelope_below_zero": len(envelope["under"]) if envelope else 0,
        "pooled_interval": len(p_over),
        "pooled_interval_below_zero": len(p_under),
    }
    present = dense(sums.n_present.astype(np.float64))
    block: dict[str, Any] = {
        "symbol": plan.symbol, "label": plan.label, "unit": "cm", "value_unit": "% per cm",
        "pitch_mm": sig(plan.width_mm), "edges_cm": plan.edges_cm(),
        "mean": sig_list(mean), "band": band, "envelope": envelope,
        "pooled": {"value": sig_list(pooled), "ci95_lo": sig_list(p_lo), "ci95_hi": sig_list(p_hi),
                   "method": metrics.METHOD_RATIO if p_label else None, "label": p_label,
                   "over": p_over, "under": p_under},
        "n_present": [int(v) for v in present],
        "outside": _outside(plan, sums, totals),
        "comb": _comb(_raw_profile(plan, sums), plan, spec),
        "splat": _splat(plan, spec),
        "w_zero_rule": _w_zero_rule(sums, totals) if plan.key == "w" else None,
        "y": {"lo": float(y_lo), "hi": float(y_hi), "interval": float(y_step),
              "provisional": bool(est.provisional), "clipped": clipped},
    }
    return block, est


# ----------------------------------------------------------------- marks --

def _marks(est: profile_stats.ProfileEstimate | None, totals: ProfileSums) -> list[dict[str, Any]]:
    n = totals.n_showers
    cluster = ("cluster-robust with the event as the cluster, since the two showers of one event "
               "share its geometry" if totals.clustered else "each shower its own sampling unit")
    return [
        {"key": "mean", "label": "Per-shower mean", "style": "solid step line", "drawn": n >= 1,
         "meaning": ("Mean over the selected showers of each shower's own fraction of its energy "
                     "in the bin, per cm: every shower weighs the same. The primary line; at "
                     "N = 1 it is that shower's own profile.")},
        {"key": "band", "label": "SD band (sample dispersion, ddof = 1)", "style": "uncapped shaded band",
         "drawn": bool(est is not None and est.sd is not None),
         "meaning": ("Mean ± the sample standard deviation of the per-shower fractions: where "
                     "individual showers lie. Dispersion of the sample, not an uncertainty of the "
                     "mean; drawn from N = 2.")},
        {"key": "envelope", "label": "95% Student-t envelope of the mean", "style": "capped thin envelope",
         "drawn": bool(est is not None and est.half95 is not None),
         "meaning": (f"Mean ± t(0.975, G − 1) × SE: how well the mean is known; SE {cluster}. "
                     "Drawn from two clusters.")},
        {"key": "pooled", "label": "Pooled ratio of sums (notebook estimator)",
         "style": "dashed step line with capped 95% interval", "drawn": n >= 2,
         "meaning": ("Σ energy in the bin over Σ shower energy, all selected showers pooled, per cm: "
                     "energy-weighted, so high-momentum showers dominate it. Its capped interval is "
                     "the linearised ratio Student-t interval with events as clusters. At N = 1 it "
                     "equals the shower's own profile and is not drawn twice.")},
    ]


# ----------------------------------------------------------------- notes --

def _pct(fraction: float | None, digits: int = 2) -> str:
    return "n/a" if fraction is None else f"{100.0 * fraction:.{digits}f}%"


def _notes(blocks: dict[str, dict[str, Any]], est: profile_stats.ProfileEstimate | None,
           totals: ProfileSums, spec: dict[str, Any], *, depth: str, notebook: bool,
           two_shower: bool) -> list[str]:
    n, g = totals.n_showers, totals.n_events
    if n == 0:
        dropped = (f" {totals.n_dropped:,} selected shower(s) deposit only behind their entry plane, "
                   "which the notebook convention drops." if totals.n_dropped else "")
        return [typographic("No shower in this selection has a profile; nothing is drawn." + dropped)]
    notes: list[str] = []
    who = f"N = {n:,} shower{'s' if n != 1 else ''}"
    if totals.clustered:
        who += f" in G = {g:,} event{'s' if g != 1 else ''}"
    pooled_drawn = n >= 2
    band_drawn = est is not None and est.sd is not None
    envelope_drawn = est is not None and est.half95 is not None
    notes.append(
        f"Primary line: the per-shower mean of each shower's fraction of its own energy per bin "
        f"({who}); every shower weighs the same."
        + (" Dashed line: the pooled ratio of sums, Σ energy in the bin over Σ shower energy, the "
           "notebook's estimator; it weights each shower by its energy, so high-momentum showers "
           "dominate it." if pooled_drawn else
           " The pooled ratio of sums (the notebook's estimator) equals this shower's own "
           "profile and is not drawn twice."))
    envelope = ("cluster-robust with the event as the cluster (the two showers of one event share "
                "its geometry)" if totals.clustered else "each shower its own sampling unit")
    drawn_marks = []
    if band_drawn:
        drawn_marks.append("Shaded band: the sample SD of the per-shower fractions (ddof = 1), "
                           "where individual showers lie.")
    if envelope_drawn:
        drawn_marks.append(f"Capped envelope: the 95% Student-t interval of the mean, {envelope}.")
    if pooled_drawn and envelope_drawn:
        drawn_marks.append("The pooled line's capped interval is the linearised ratio interval "
                           "with events as clusters.")
    if drawn_marks:
        notes.append(" ".join(drawn_marks))
    if n == 1:
        notes.append("N = 1: single shower, not an ensemble. The line is that shower's own "
                     "profile; no band, envelope or interval can be drawn.")
    elif n >= 2:
        if n == 2:
            notes.append("N = 2: the SD band has 1 degree of freedom.")
        if g < 2:
            notes.append(f"G = {g} event: no interval of the mean can be estimated from one cluster, "
                         "so the envelope and the pooled interval are not drawn.")
        elif totals.clustered and g < profile_stats.PROVISIONAL_N:
            dof = f"{g - 1} degree{'s' if g - 1 != 1 else ''} of freedom"
            notes.append(f"The intervals rest on G = {g} events ({dof}), fewer "
                         f"than the {n} showers: the two showers of an event are not independent.")
        if est is not None and est.provisional:
            notes.append(f"N = {n} < {profile_stats.PROVISIONAL_N}: the summary is weak and the y "
                         "range provisional.")
    if notebook:
        notes.append(
            "Notebook convention: hits at z_local < −1e-6 mm "
            f"({_pct(totals.e_neg / totals.e_all if totals.e_all > 0 else None)} of the selection's "
            "energy, hit level) are dropped from every bin and from each shower's normaliser, as "
            "the notebook drops z_local < 0; hits in [−1e-6, 0) mm are kept here.")
        if totals.n_dropped:
            notes.append(f"{totals.n_dropped:,} shower(s) deposit only behind their entry plane and "
                         "have no profile under this convention; they are not counted in N.")
    else:
        notes.append(
            "Each shower is normalised by its own deposited energy, every hit kept (including those "
            "behind its entry plane), so its fractions sum to one over the bins of each axis; "
            "energy outside the drawn window stays in the normaliser, so the curves integrate to "
            "less than 100%.")
    k, k_z = spec.get("k"), spec.get("k_z")
    splat_words = (f"into {k} × {k} × {k_z} sub-deposits" if k and k_z
                   else "into sub-deposits (splat parameters not recorded)")
    notes.append(
        "The notebook point-bins hit centres in 20 mm depth bins over 0–1200 mm and 10 mm radial "
        "bins over 0–500 mm, pooled over the whole file. Here each hit is footprint-splatted "
        f"{splat_words} rotated by its shower's R(θ, φ), depth is binned at the layer pitch "
        f"({spec.get('w_bin_mm', 0):g} mm) anchored at w = 0, and the pooled line sums this "
        "selection only.")
    r = blocks.get("r")
    if r is not None:
        footprint = spec.get("footprint_mm")
        cell = (f" ({footprint[0]:.2f} × {footprint[1]:.2f} mm)" if footprint else "")
        notes.append(
            "ρ = √(u² + v²) is each sub-deposit's 2-D distance from its shower's incident axis; "
            "values are per cm of radius with no 2πρ area factor, as in the notebook. The 10 mm "
            f"radial bins are finer than one cell{cell}, so part of the SD band is cell "
            f"discretisation, not shower-to-shower variation. Beyond ρ = 50 cm lies "
            f"{_pct(r['outside']['above_fraction'])} of the pooled energy (overflow), kept in the "
            "normaliser.")
    w = blocks.get("w")
    if w is not None:
        rule = w["w_zero_rule"]
        below = (f"Below w = 0 lies {_pct(rule['energy_fraction_below'])} of the pooled energy "
                 f"({_pct(rule['mean_fraction_below'])} by the per-shower mean)")
        if notebook:
            why = (f"{below}, although the hits at z_local < −1e-6 mm "
                   f"({_pct(rule['hit_level_c9'])} of the energy, hit level) are dropped: it is "
                   "the part of each kept cell's splat that lies behind w = 0, half of a "
                   "first-layer cell centred there.")
        else:
            why = (f"{below}, against {_pct(rule['hit_level_c9'])} in hits at z_local < −1e-6 mm "
                   "(hit level): the splat moves energy across w = 0, because each first-layer "
                   "cell spans half a layer pitch behind its centre.")
        notes.append("No bin straddles w = 0: the w bins are multiples of the layer pitch anchored "
                     f"there. {why}")
        lo_cm, hi_cm = w["outside"]["window_cm"]
        source = ("the Local frame's dataset-wide depth grid, bin for bin the depth panels' "
                  if w["outside"]["window_source"] == "dataset" else "this selection's populated ")
        notes.append(
            f"Drawn w window {lo_cm:g} to {hi_cm:g} cm ({source}range): "
            f"{_pct(w['outside']['below_fraction'])} of the pooled energy lies below it and "
            f"{_pct(w['outside']['above_fraction'])} above, kept in every normaliser.")
    if depth == "native":
        lag = (blocks.get("kt") or {}).get("comb", {}).get("lag1")
        recorded = (f" (layer-to-layer lag-1 {fmt_signed(lag, 2, plus=True)}, recorded, not a "
                    "comb verdict)" if lag is not None else "")
        notes.append(
            "Native depth: each shower's own sampling layers counted from its first, Δz = kt × "
            f"{spec.get('w_bin_mm', 0):g} mm in the per-shower translated frame. It is not rotated, "
            "so it is not w; one bin per layer, never splatted, so no binning comb can arise "
            f"there{recorded}.")
    combs = [(key, block["comb"]) for key, block in blocks.items()
             if block.get("comb") and block["comb"]["regime"] != "native_layers"]
    if combs:
        measured = ", ".join(
            f"{'ρ' if key == 'r' else key} {fmt_signed(c['lag1'], 2, plus=True)}"
            for key, c in combs if c["lag1"] is not None)
        combed = [("ρ" if key == "r" else key) for key, c in combs if c["combed"]]
        splat = (r or {}).get("splat") or {}
        gap = ""
        if splat.get("spacing_mm") is not None and splat.get("footprint_mm"):
            need_2d = frame_mod.minimum_gapless_subsample(max(splat["footprint_mm"]), splat["bin_mm"])
            verdict_1d = "gap-free" if splat["gap_free"] else "not gap-free"
            gap = (f" Projected sub-deposit spacing {splat['spacing_mm']:.1f} mm against the "
                   f"{splat['bin_mm']:g} mm ρ bin: {verdict_1d} in one dimension, which a 1-D "
                   f"profile needs (a 2-D raster at this bin would need k = {need_2d}).")
        verdict = (f"the pooled profile alternates bin to bin on {', '.join(combed)}: part of its "
                   "structure there is the splat, not the shower." if combed else "no comb.")
        lag = (f"Comb lag-1 of this selection's raw pooled profile, every bin before the display "
               f"window: {measured} (combed below {fmt_signed(stagger.COMB_THRESHOLD, 2)}); {verdict}"
               if measured else "The comb could not be measured: too few populated bins.")
        notes.append(f"Footprint splat k = {k} transverse, k_z = {k_z} in depth.{gap} {lag}")
    if totals.n_single_cell:
        one = totals.n_single_cell == 1
        verb, owner = ("deposits", "its") if one else ("deposit", "each one's")
        notes.append(
            f"{totals.n_single_cell:,} of the {n:,} showers {verb} in one cell: {owner} profile "
            "is that cell's splat footprint alone, which widens the SD band.")
    if two_shower:
        notes.append("'A+B' cells are counted with shower B, as in every per-shower split.")
    parts = []
    for key, block in blocks.items():
        clipped = block["y"]["clipped"]
        found = [f"{clipped[field]} {what} bin(s) {where}" for field, what, where in _CLIP_TERMS
                 if clipped.get(field)]
        if found:
            parts.append(f"{'ρ' if key == 'r' else key}: {', '.join(found)}")
    if parts:
        notes.append("The y range follows the two lines only; band and interval parts beyond it are "
                     "clipped at the axis with an out-of-range marker, and tooltips carry the true "
                     "values. " + "; ".join(parts) + ".")
    return [typographic(text) for text in notes]


#: How the clipped counts of an axis's ``y.clipped`` block are worded.
_CLIP_TERMS: tuple[tuple[str, str, str], ...] = (
    ("band", "SD-band", "above the range"),
    ("envelope", "envelope", "above the range"),
    ("pooled_interval", "pooled-interval", "above the range"),
    ("band_below_zero", "SD-band", "below zero"),
    ("envelope_below_zero", "envelope", "below zero"),
    ("pooled_interval_below_zero", "pooled-interval", "below zero"),
)


# --------------------------------------------------------------- payload --

def _parse(record: ExperimentRecord, shower: str, depth: str, notebook: bool) -> tuple[ShowerColumns, ...]:
    if depth not in DEPTHS:
        raise ValidationError(f"depth must be one of {', '.join(DEPTHS)}; got {depth!r}.", field="depth")
    if notebook and depth == "native":
        raise ValidationError(
            "notebook=true applies the notebook's selection z_local ≥ 0, which is defined along w; "
            "the native-layer table counts every hit of a layer and does not split them. Request "
            "depth=w for the notebook convention (its radial axis is the same).",
            field="notebook",
        )
    return showers_mod.of(record, shower)


def profiles(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, *,
             shower: str = "both", depth: str = "w",
             notebook: bool = False) -> tuple[dict[str, Any], float, bool]:
    """``(body, query_ms, cached)``: the C7 payload without its envelope and filter."""
    picked = _parse(record, shower, depth, notebook)
    clamped = spec.clamped(record)
    key = (*clamped.cache_key(), "profiles", CACHE_VERSION, shower, depth, bool(notebook))
    started = time.perf_counter()
    # The unit form rolls a scan of the profile table into a hundred groups;
    # the clustered form groups it per event first - millions of groups on a
    # production file - so only that one waits its turn with the hit scans.
    totals, cached = physics_cache.get_or_compute(
        key, lambda: compute_sums(con, record, clamped, picked, depth, bool(notebook)),
        heavy=len(picked) > 1)
    query_ms = (time.perf_counter() - started) * 1000.0
    return render(record, totals, shower=shower, depth=depth, notebook=bool(notebook)), query_ms, cached


def render(record: ExperimentRecord, totals: ProfileSums, *, shower: str, depth: str,
           notebook: bool) -> dict[str, Any]:
    """The payload body from a selection's sums: pure NumPy, no query."""
    spec = profile_spec(record)
    width_w = float(spec["w_bin_mm"])
    plans: list[tuple[AxisPlan, AxisSums]] = []
    if depth == "w":
        plans.append((_w_plan(record, width_w, totals.axes["w"]), totals.axes["w"]))
    else:
        plans.append((_kt_plan(record, width_w, totals.axes["kt"]), totals.axes["kt"]))
    plans.append((_r_plan(float(spec["r_bin_mm"]), int(spec["r_bins"])), totals.axes["r"]))

    blocks: dict[str, dict[str, Any]] = {}
    est = None
    for plan, sums in plans:
        blocks[plan.key], axis_est = render_axis(plan, sums, totals, spec)
        if est is None:
            # The labels and gates depend on N and G only: every axis agrees.
            est = axis_est
    n = totals.n_showers
    ensemble = {
        "n_showers": n,
        "n_events": totals.n_events,
        "label": est.label if est is not None else "no showers",
        "dof_note": est.dof_note if est is not None else None,
        "provisional": bool(est.provisional) if est is not None else True,
        "n_single_cell": totals.n_single_cell,
        "clustered": totals.clustered,
        "n_dropped": totals.n_dropped,
    }
    two = record.kind == ddl.KIND_TWO_SHOWER
    return {
        "kind": record.kind,
        "shower": shower,
        "depth": depth,
        "notebook_scale": bool(notebook),
        "convention": {
            "notebook": bool(notebook),
            "label": ("notebook: hits at z_local < −1e−6 mm dropped from the bins and the normaliser"
                      if notebook else "every hit kept; each shower normalised by its own deposit"),
            "neg_depth_mm": ddl.NEG_DEPTH_MM,
            "dropped_energy_fraction": (sig(totals.e_neg / totals.e_all)
                                        if notebook and totals.e_all > 0 else 0.0),
        },
        "ensemble": ensemble,
        "marks": _marks(est, totals),
        "axes": blocks,
        "notes": _notes(blocks, est, totals, spec, depth=depth, notebook=notebook, two_shower=two),
    }
