"""Prediction against truth: what a per-shower network predicted, and how far off.

Page 2's pred-truth and pred-residuals cards. The energy and angle networks
predict one number per shower, so each event contributes two (truth,
prediction) pairs - shower A and shower B, kept apart - and this module
reduces them to a payload far under the 100 KB contract:

**A density of pairs, on axes that do not move.** Truth and prediction share
one range, taken from the *whole* event table whatever the selection (the
outward 1-2-5 rounding of the truth's extent, the energy axis floored at zero),
so the identity line is the diagonal and the picture does not shift as a
filter changes. Counts are integers, one row per prediction bin, row-major;
nothing the axes cut off is dropped silently - ``outside`` counts each side, and
``n_in_range + outside.total == n``. A shower with fewer than 15 pairs gets its
individual pairs instead of a density: one or two showers per cell would be a
statement about the binning (CLAUDE.md section 2).

**A colour that starts visible.** Counts are drawn on log10. Viridis' own first
colour is 1.06:1 against the #1c2128 card, so a cell holding a single shower
would vanish while being "drawn"; the ramp therefore starts at the first
position whose contrast is at least 3:1 and the payload states that colour.

**The residual beneath it, on the energy panel's ladder.** The residual is the
quantity of the model-performance cards: (pred − true) / true for energy,
Δθ in mrad for angle. Its range is the 1st-99th percentile of the showers that
carry statistical weight (N ≥ 15; every shower, labelled provisional, when none
does), rounded outward and disclosed; the bin count follows the smaller drawn
shower. Each shower goes through ``energy.build_series``, so a density
histogram appears from N = 15, the core-refit Gaussian curve from N = 8, the
individual events below, and every mean carries its Student-t whisker apart
from the sample's σ band. Bias, σ and RMSE come with their own intervals from
``metrics.residual_summary``.

The angle network predicts θ only, so there is no azimuth residual to wrap.

**The XGBoost series of an aggregate experiment** (:func:`read_xgb`) is the
shipped regressor on the notebook's 20 % validation split, restricted to the
selection: one shower, the same payload. Its angle task predicts φ as well as
θ, chosen with ``label``; φ's residual is wrapped to (−π, π] (an azimuth's
error of 2π − ε is a small one) and its axes are stated not to wrap.

**φ's residual is circular** (:func:`circular_series`, CLAUDE.md section 2:
never average a circular quantity). Its histogram and RMSE stand, but its
arithmetic mean, the mean's whisker and the σ band, the bias, σ/μ and the
moment σ are withheld - null, never numbers. Its centre and spread are the
circular mean direction (with Fisher's large-sample 95 % interval), the mean
resultant length R̄ and the circular SD √(−2 ln R̄). A Gaussian curve is drawn
only as a fit of the core (the iterated ±2.5σ window, N ≥ 15), labelled so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..stats import circular as circular_mod
from ..stats import clip as clip_mod
from ..stats import gaussian, histogram, metrics
from ..text import typographic
from . import performance_bins
from . import showers as showers_mod
from .energy import THRESHOLDS as ENERGY_THRESHOLDS
from .energy import build_series
from .filters import FilterSpec
from .performance import MRAD_PER_RAD

MODELS = performance_bins.MODELS
UNITS = performance_bins.UNITS

#: Fewest pairs of a shower for which a density is drawn rather than its pairs.
MIN_DENSITY_SAMPLES = histogram.MIN_HISTOGRAM_SAMPLES

#: Bin counts the payload guard steps down through, most to fewest.
BINS_LADDER: tuple[int, ...] = (128, 96, 64, 48, 32, 24, 16)

#: The card the colour ramp is measured against, and the contrast it must clear.
CARD_HEX = "#1c2128"
CARD_RGB = (28, 33, 40)
MIN_CONTRAST = 3.0

#: The sequential palettes' anchors, as ``static/js/palette.js`` interpolates them into its
#: 256-entry tables. ``tests/test_prediction_density_stats.py`` parses that file and asserts
#: these are the same numbers, so the contrast measured here is the contrast the frontend draws.
ANCHORS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "viridis": (
        (68, 1, 84), (72, 34, 115), (64, 67, 135), (52, 94, 141), (41, 120, 142),
        (32, 144, 140), (34, 167, 132), (68, 190, 112), (121, 209, 81),
        (189, 222, 38), (253, 231, 37),
    ),
    "cividis": (
        (0, 32, 76), (0, 42, 102), (0, 52, 110), (39, 63, 108), (60, 74, 107),
        (76, 85, 107), (91, 97, 109), (108, 110, 111), (125, 123, 110),
        (145, 137, 106), (165, 152, 99), (187, 168, 88), (209, 185, 73),
        (232, 202, 51), (255, 221, 0),
    ),
    "plasma": (
        (13, 8, 135), (70, 3, 159), (114, 1, 168), (156, 23, 158), (189, 55, 134),
        (216, 87, 107), (237, 121, 83), (251, 159, 58), (253, 202, 38), (240, 249, 33),
    ),
    "turbo": (
        (48, 18, 59), (70, 107, 227), (40, 187, 236), (49, 242, 153), (136, 255, 63),
        (211, 231, 41), (253, 165, 49), (243, 84, 19), (190, 29, 3), (122, 4, 3),
    ),
}
DEFAULT_PALETTE = "viridis"

LABELS = {
    "energy": {
        "truth": "True incident momentum", "pred": "Predicted energy",
        "residual": "Relative energy residual (pred − true) / true", "residual_unit": "fraction",
    },
    "angle": {
        "truth": "True incident polar angle θ", "pred": "Predicted polar angle θ",
        "residual": "Polar-angle residual θ_pred − θ_true", "residual_unit": "mrad",
    },
    "phi": {
        "truth": "True incident azimuth φ", "pred": "Predicted azimuth φ",
        "residual": "Azimuth residual φ_pred − φ_true, wrapped to (−π, π]",
        "residual_unit": "mrad",
    },
}

#: The XGBoost series' code, and the labels its angle task predicts.
XGB_CODE = "xgb"
XGB_LABELS: dict[str, tuple[str, ...]] = {"energy": ("momentum",), "angle": ("theta", "phi")}


# ------------------------------------------------------------------ colour --


def palette_colour(name: str, t: float) -> tuple[int, int, int]:
    """The colour at ramp position ``t`` of the frontend's table for ``name`` (entry ``round(255 t)``)."""
    anchors = ANCHORS[name]
    index = int(min(1.0, max(0.0, t)) * 255 + 0.5)
    s = index / 255 * (len(anchors) - 1)
    k = min(len(anchors) - 2, int(s))
    f = s - k
    a, b = anchors[k], anchors[k + 1]
    r, g, b_ = (int(round(a[c] + (b[c] - a[c]) * f)) for c in range(3))
    return r, g, b_


def viridis(t: float) -> tuple[int, int, int]:
    return palette_colour("viridis", t)


def luminance(rgb: Sequence[int]) -> float:
    """WCAG relative luminance of an sRGB triple (0-255)."""
    def linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrast(a: Sequence[int], b: Sequence[int]) -> float:
    """WCAG contrast ratio of two sRGB triples."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hex_of(rgb: Sequence[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def ramp_start(name: str = DEFAULT_PALETTE, step: float = 0.05) -> float:
    """The first ramp position (a multiple of ``step``) that clears 3:1 against the card."""
    t = 0.0
    while t < 1.0 and contrast(palette_colour(name, t), CARD_RGB) < MIN_CONTRAST:
        t = round(t + step, 10)
    return t


def _table_contrast(name: str, lo: float, hi: float) -> float:
    """The lowest contrast against the card of the table entries from ``lo`` to ``hi``."""
    first, last = int(lo * 255 + 0.5), int(hi * 255 + 0.5)
    return min(contrast(palette_colour(name, i / 255), CARD_RGB) for i in range(first, last + 1))


def ramp_end(name: str, start: float, step: float = 0.05) -> float:
    """The last ramp position (a multiple of ``step``) up to which every table entry clears 3:1.

    1 for a ramp that brightens all the way; Turbo darkens to a red at its end,
    so its peak is drawn where it still clears, not where the table stops.
    """
    t = 1.0
    while t > start and _table_contrast(name, start, t) < MIN_CONTRAST:
        t = round(t - step, 10)
    return t


def _ramp(name: str) -> dict[str, Any]:
    """One palette's ramp: where a count of one starts, where the peak ends, and seven stops."""
    start = ramp_start(name)
    end = ramp_end(name, start)
    first = palette_colour(name, start)
    stops = [palette_colour(name, start + (end - start) * i / 6) for i in range(7)]
    worst = _table_contrast(name, start, end)
    return {
        "from": start, "to": end, "stops": [hex_of(c) for c in stops],
        "first_level": {"count": 1, "color": hex_of(first),
                        "contrast": round(contrast(first, CARD_RGB), 2), "against": CARD_HEX},
        # Over every table entry the ramp draws, not only the seven stops.
        "min_stop_contrast": round(worst, 2), "clears_everywhere": worst >= MIN_CONTRAST,
    }


def color_block(vmax: float) -> dict[str, Any]:
    """The log10 colour scale: where a count of one starts, and the stops from there to the peak.

    ``ramp`` is the default palette's; ``ramp.by_palette`` carries the measured start and
    first-level colour of every sequential palette the interface offers, each against the
    card, so a user's palette choice never lands a count of one below 3:1.
    """
    ramp = _ramp(DEFAULT_PALETTE)
    start = ramp["from"]
    first = palette_colour(DEFAULT_PALETTE, start)
    ratio = contrast(first, CARD_RGB)
    plain = contrast(palette_colour(DEFAULT_PALETTE, 0.0), CARD_RGB)
    by_palette = {name: _ramp(name) for name in ANCHORS}
    cut = {n: r["to"] for n, r in by_palette.items() if r["to"] < 1.0}
    note = (
        f"log10 of the showers per bin, empty bins transparent. A bin holding one shower "
        f"is drawn at position {start:g} of Viridis, {hex_of(first)}, {ratio:.1f}:1 against "
        f"the {CARD_HEX} card: the ramp's own first colour, "
        f"{hex_of(palette_colour(DEFAULT_PALETTE, 0.0))}, is {plain:.2f}:1 and would make a "
        "count of one disappear. Each offered palette has its own start in ramp.by_palette.")
    if cut:
        note += " " + "; ".join(
            f"{n.capitalize()} darkens towards its end, so its peak is drawn at position {t:g}, "
            f"the last that clears {MIN_CONTRAST:g}:1" for n, t in cut.items()) + "."
    return {
        "scale": "log10",
        "vmin": 0,
        "vmax": sig(vmax),
        "unit": "showers per bin",
        "empty": "transparent",
        "palette": DEFAULT_PALETTE,
        "ramp": {**ramp, "by_palette": by_palette},
        "note": typographic(note),
    }


# -------------------------------------------------------------------- read --


@dataclass
class Selection:
    """The selected showers' finite (truth, prediction) pairs and the dataset-wide axis."""

    model: str
    coord_system: str
    lo: float
    hi: float
    n_events: int
    truth: dict[str, np.ndarray]
    pred: dict[str, np.ndarray]
    #: Per shower, the selected events dropped for a prediction or a truth that is not finite.
    n_missing: dict[str, dict[str, int]] = field(default_factory=dict)
    #: The XGBoost series (``"xgb"``) of an aggregate experiment; ``None`` for the networks.
    source: str | None = None
    #: The XGBoost angle task's label, ``theta`` or ``phi``; ``None`` otherwise.
    label: str | None = None
    #: The XGBoost series' split disclosure and run block.
    split: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)

    @property
    def frame(self) -> str:
        if self.source == XGB_CODE:
            return XGB_CODE
        return ddl.NETWORK_FRAME[self.coord_system]

    @property
    def labels(self) -> dict[str, str]:
        return LABELS["phi" if self.label == "phi" else self.model]

    @property
    def unit(self) -> str:
        return UNITS[self.model]

    @property
    def showers(self) -> tuple[str, ...]:
        return tuple(self.truth)


def _scale(model: str) -> float:
    return MRAD_PER_RAD if model == "angle" else 1.0


def dataset_range(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, model: str,
                  showers: Sequence[str]) -> tuple[float, float]:
    """The shared axis range: the truth's extent over the whole table, rounded outward.

    Each shower's minimum and maximum are read separately and combined here,
    which does not depend on how SQL ``least`` and ``greatest`` treat NULL. The
    energy axis starts at zero, its natural origin; the angle axis keeps its
    rounded lower edge, which its tick labels state.
    """
    table = quote(naming.event_table(record.table_name))
    parts: list[str] = []
    for shower in showers:
        truth, _ = performance_bins.network_columns(model, "lab", shower)
        parts.append(f"min(CAST({truth} AS DOUBLE)), max(CAST({truth} AS DOUBLE))")
    row = con.execute(f"SELECT {', '.join(parts)} FROM {table}").fetchone()
    return _axis_range([v for v in row if v is not None], _scale(model), model)


def read(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
         model: str, coord_system: str) -> Selection:
    """The selection's pairs (finite only, in GeV or mrad) and the dataset-wide axis."""
    table = quote(naming.event_table(record.table_name))
    showers = tuple(sh.key for sh in showers_mod.of(record, "both"))
    select: list[str] = []
    for shower in showers:
        truth, pred = performance_bins.network_columns(model, coord_system, shower)
        select += [f"CAST({truth} AS DOUBLE) AS true_{shower}",
                   f"CAST({pred} AS DOUBLE) AS pred_{shower}"]
    raw = con.execute(
        f"SELECT {', '.join(select)} FROM {table} WHERE {spec.where_sql()}", spec.params()
    ).fetchnumpy()
    arrays = {k: np.ma.filled(np.ma.asarray(v).astype(np.float64), np.nan) for k, v in raw.items()}
    scale = _scale(model)
    truth_by, pred_by, missing = {}, {}, {}
    for shower in showers:
        t, p = arrays[f"true_{shower}"], arrays[f"pred_{shower}"]
        keep = np.isfinite(t) & np.isfinite(p)
        truth_by[shower], pred_by[shower] = t[keep] * scale, p[keep] * scale
        missing[shower] = {"total": int((~keep).sum()), "prediction": int((~np.isfinite(p)).sum()),
                           "truth": int((~np.isfinite(t)).sum())}
    lo, hi = dataset_range(con, record, model, showers)
    n_events = int(next(iter(arrays.values())).size) if arrays else 0
    return Selection(model, coord_system, lo, hi, n_events, truth_by, pred_by, missing)


# ----------------------------------------------------------------- density --


def density_block(truth: np.ndarray, pred: np.ndarray, lo: float, hi: float,
                  bins: int, n_missing: dict[str, int] | None = None) -> dict[str, Any]:
    """One shower's pairs: a dense count raster from N = 15, the pairs themselves below.

    ``counts`` is row-major with one row per prediction bin and one column
    per truth bin; a value on ``hi`` falls in the last bin, as in NumPy.
    ``n_missing`` counts the selected events this shower lost for a prediction or a
    truth that is not finite (a total, and each cause), never zero-filled.
    """
    missing = {"total": 0, "prediction": 0, "truth": 0, **(n_missing or {})}
    n = int(truth.size)
    below_t, above_t = int((truth < lo).sum()), int((truth > hi).sum())
    below_p, above_p = int((pred < lo).sum()), int((pred > hi).sum())
    outside_any = (truth < lo) | (truth > hi) | (pred < lo) | (pred > hi)
    outside = {"truth_below": below_t, "truth_above": above_t,
               "pred_below": below_p, "pred_above": above_p, "total": int(outside_any.sum())}
    if n < MIN_DENSITY_SAMPLES:
        order = np.lexsort((pred, truth))
        return {
            "encoding": "pairs",
            "pairs": [[sig(t), sig(p)] for t, p in zip(truth[order], pred[order])],
            "n": n, "n_in_range": n - outside["total"], "outside": outside,
            "n_missing": missing,
        }
    edges = np.linspace(lo, hi, bins + 1)
    counts, _, _ = np.histogram2d(pred, truth, bins=[edges, edges])
    counts = counts.astype(np.int64)
    return {
        "encoding": "counts",
        "shape": [bins, bins],
        "counts": counts.ravel().tolist(),
        "n": n,
        "n_in_range": int(counts.sum()),
        "max_count": int(counts.max()),
        "outside": outside,
        "n_missing": missing,
    }


# ---------------------------------------------------------------- residual --


def _estimate(e: metrics.Estimate) -> dict[str, Any]:
    iv = e.interval
    return {
        "value": sig(e.value), "se": sig(e.se),
        "interval": None if iv is None else {
            "lo": sig(iv.lo), "hi": sig(iv.hi), "level": iv.level, "method": iv.method,
            "label": typographic(iv.label)},
        "n": e.n, "note": typographic(e.note),
    }


def residuals(sel: Selection) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    """Each shower's residuals on the cards' quantity, and the pairs a relative error cannot take.

    Energy is relative, (pred − true) / true, which needs a positive truth;
    angle is Δθ in mrad.
    """
    out: dict[str, np.ndarray] = {}
    excluded: dict[str, int] = {}
    for shower in sel.showers:
        t, p = sel.truth[shower], sel.pred[shower]
        if sel.model == "energy":
            positive = t > 0
            excluded[shower] = int(t.size - positive.sum())
            out[shower] = (p[positive] - t[positive]) / t[positive]
        elif sel.label == "phi":
            excluded[shower] = 0
            out[shower] = circular_mod.wrap_angle((p - t) / MRAD_PER_RAD) * MRAD_PER_RAD
        else:
            excluded[shower] = 0
            out[shower] = p - t
    return out, excluded


#: The fit fields that describe a line: an arithmetic mean, a moment width and what is built on
#: them. None is a statistic of an azimuth, so φ's residual carries each as null.
LINEAR_FIT_FIELDS: tuple[str, ...] = (
    "mu", "sigma", "sigma_population", "sigma_robust", "resolution", "resolution_core",
    "mu_error", "sigma_error", "resolution_error", "mu_ci95", "sigma_ci95",
    "sigma_bias_factor", "sigma_unbiased", "non_gaussian",
)

#: Fewest residuals for Fisher's large-sample interval of a mean direction (Fisher 1993, 4.4.4).
MIN_DIRECTION_INTERVAL = 25

CORE_FIT_LABEL = (
    "Gaussian fit of the core: the iterated ±2.5σ window of the wrapped residual, where it "
    "does not wrap. It describes the core's shape only; it is not the width or the centre of "
    "the whole distribution, whose spread is the circular SD.")


def direction_interval(radians: np.ndarray, mean: float | None,
                       resultant: float | None) -> dict[str, Any] | None:
    """Fisher's large-sample 95 % interval of a mean direction, in radians; ``None`` below N = 25.

    δ = (1 − ρ₂) / (2 R̄²) with ρ₂ = mean cos 2(θ − θ̄) is the circular
    dispersion and σ = √(δ / n) the standard error; the interval is
    θ̄ ± arcsin(1.96 σ) (Fisher 1993, eqs 4.21 and 4.22).
    """
    a = np.asarray(radians, dtype=np.float64)
    a = a[np.isfinite(a)]
    n = int(a.size)
    if n < MIN_DIRECTION_INTERVAL or mean is None or not resultant:
        return None
    rho2 = float(np.mean(np.cos(2.0 * (a - mean))))
    se = math.sqrt(max(0.0, (1.0 - rho2) / (2.0 * resultant * resultant)) / n)
    z = 1.959963984540054 * se
    if z >= 1.0:
        return None
    half = math.asin(z)
    return {"lo": mean - half, "hi": mean + half, "se": se}


def circular_block(sample_mrad: np.ndarray) -> dict[str, Any]:
    """The wrapped residual's centre and spread on the circle, in mrad."""
    radians = np.asarray(sample_mrad, dtype=np.float64) / MRAD_PER_RAD
    summary = circular_mod.describe_circular(radians)
    interval = direction_interval(radians, summary.mean_direction, summary.resultant)

    def mrad(value: float | None) -> float | None:
        return None if value is None else sig(value * MRAD_PER_RAD)

    note = summary.note
    if not note and interval is None and summary.n >= 2:
        note = (f"N = {summary.n}: below the {MIN_DIRECTION_INTERVAL} residuals Fisher's "
                "large-sample interval of the mean direction needs; none is quoted.")
    return {
        "n": summary.n,
        "unit": "mrad",
        "mean_direction": mrad(summary.mean_direction),
        "mean_direction_se": mrad(interval["se"]) if interval else None,
        "mean_direction_interval": None if interval is None else {
            "lo": mrad(interval["lo"]), "hi": mrad(interval["hi"]), "level": 0.95,
            "method": "fisher_large_sample",
            "label": "95 % large-sample interval of the mean direction (Fisher 1993, 4.4.4)"},
        "resultant": sig(summary.resultant),
        "circular_sd": mrad(summary.circular_sd),
        "rayleigh_p": sig(summary.rayleigh_p),
        "definition": ("mean direction atan2(Σ sin, Σ cos) of the wrapped residuals; mean "
                       "resultant length R̄ = |Σ e^{iθ}| / n in [0, 1]; circular SD √(−2 ln R̄)"),
        "note": typographic(note),
    }


def _withheld(n: int, what: str) -> dict[str, Any]:
    """An estimate φ's residual does not have: null, with the reason."""
    return {"value": None, "se": None, "interval": None, "n": n, "note": typographic(
        f"Not quoted for an azimuth: {what}. The circular mean direction, R̄ and the circular "
        "SD are its centre and spread (series.circular).")}


def circular_series(entry: dict[str, Any], sample_mrad: np.ndarray,
                    rmse: dict[str, Any]) -> dict[str, Any]:
    """A φ residual series: the ladder's histogram and events, with every linear statistic nulled.

    ``entry`` is ``build_series(...).as_dict()`` of the wrapped residual. Its
    marks of a line - the mean marker with its whisker and σ band - and the
    fit's arithmetic mean, moment widths and ratios become null; the core
    refit's Gaussian stays, labelled as a fit of the core, only where it ran
    (N ≥ 15) and its window does not reach the ±π cut.
    """
    out = dict(entry)
    fit = dict(out["fit"])
    n = int(fit.get("n") or 0)
    mu_core, sigma_core = fit.get("mu_core"), fit.get("sigma_core")
    core = bool(fit.get("core_applied")) and sigma_core is not None and sigma_core > 0 and (
        abs(mu_core) + gaussian.CORE_SIGMA * sigma_core < math.pi * MRAD_PER_RAD)
    for key in LINEAR_FIT_FIELDS:
        fit[key] = None
    fit["note"] = ""
    if core:
        out["core_fit"] = {"mu": sig(mu_core), "sigma": sig(sigma_core), "n": int(fit["n_core"]),
                           "unit": "mrad", "label": typographic(CORE_FIT_LABEL)}
    else:
        fit["mu_core"] = fit["sigma_core"] = None
        fit["estimator"] = "circular"
        fit["estimator_note"] = typographic(
            f"N = {n}: summarised on the circle only. A Gaussian of the core needs the "
            f"{gaussian.MIN_CORE_SAMPLES}-residual core refit, and no curve is drawn without it.")
        out["core_fit"] = None
        out["curve"] = {"y": None}
        out["curve_peak"] = None
        if out["draw"] == "curve+strip":
            out["draw"] = "strip"
    if out["draw"] != "histogram":
        out["message"] = typographic(
            f"N = {n}: the individual residuals are drawn; an azimuth's residual has no "
            "arithmetic mean or σ to mark, and its circular statistics are in the tooltip.")
    out["fit"] = fit
    out["markers"] = None
    out["circular"] = circular_block(sample_mrad)
    out["estimates"] = {
        "bias": _withheld(n, "an arithmetic mean of a wrapped residual is not its centre"),
        "sigma": _withheld(n, "a moment σ of a wrapped residual is set by the few residuals "
                              "near ±π, not by its width"),
        "rmse": rmse,
    }
    return out


def residual_block(sel: Selection) -> dict[str, Any]:
    """Each shower's residual histogram, curve, strip and markers, with its estimates beside them."""
    values, excluded = residuals(sel)
    labels = sel.labels
    drawn = [s for s in sel.showers if values[s].size >= MIN_DENSITY_SAMPLES]
    pooled = np.concatenate([values[s] for s in (drawn or sel.showers)] or [np.empty(0)])
    clipping = clip_mod.percentile_clip(pooled, low=clip_mod.DEFAULT_LOW_PERCENTILE,
                                        high=clip_mod.DEFAULT_HIGH_PERCENTILE, pad=0.05)
    # Percentiles of fewer than 20 pooled values are noise and are not taken: the range is
    # then the sample's own extent, which one outlier sets, and is provisional.
    provisional = not drawn or not clipping.applied
    lo, hi, interval = clip_mod.nice_range(clipping.lo, clipping.hi, fine=True)
    bins = histogram.adaptive_bins(min(values[s].size for s in drawn) if drawn else 0)
    edges = histogram.axis_edges(lo, hi, bins)
    curve_x = histogram.curve_axis(lo, hi, histogram.CURVE_POINTS)

    series: dict[str, Any] = {}
    outside: dict[str, Any] = {}
    for shower in sel.showers:
        sample = values[shower]
        fitted = build_series(
            key=f"residual_{shower}", label=f"Shower {shower.upper()} residual", shower=shower,
            kind="residual", slice_index=0, slice_label="all selected events", sample=sample,
            edges_array=edges, curve_x=curve_x,
        )
        summary = metrics.residual_summary(sample)
        if sel.label == "phi":
            series[shower] = circular_series(fitted.as_dict(), sample, _estimate(summary.rmse))
        else:
            series[shower] = {
                **fitted.as_dict(),
                "estimates": {"bias": _estimate(summary.bias), "sigma": _estimate(summary.sigma),
                              "rmse": _estimate(summary.rmse)},
            }
        outside[shower] = {"n": int(sample.size), "below": int((sample < lo).sum()),
                           "above": int((sample > hi).sum())}
    return {
        "quantity": labels["residual"],
        "unit": labels["residual_unit"],
        "statistics": "circular" if sel.label == "phi" else "linear",
        "axis": {
            "lo": lo, "hi": hi, "interval": interval, "bins": bins,
            "clipping": clipping.as_dict(),
            "provisional": provisional,
            "basis": (
                f"pooled residuals of the showers with N ≥ {MIN_DENSITY_SAMPLES}"
                if drawn and clipping.applied else
                f"pooled residuals of the showers with N ≥ {MIN_DENSITY_SAMPLES}: fewer than 20 "
                "values, so their full extent is shown and the range is provisional"
                if drawn else
                f"every shower's residuals: none reaches N = {MIN_DENSITY_SAMPLES}, so this "
                "range is provisional"),
            "outside": outside,
            "curve_x": sig_list(curve_x),
            "hist_centres": sig_list(0.5 * (edges[:-1] + edges[1:])),
        },
        "series": series,
        "excluded": {"nonpositive_truth": excluded},
    }


# ------------------------------------------------------------------ report --


#: What the residual card draws for a linear residual, in the words of its Details drawer.
MARKS_NOTE = (
    "From N = 15 a series is a density histogram, which is its spread, with its fitted Gaussian; "
    "its mean is a long-dashed rule with the 95 % Student-t interval of the mean as two thin "
    "hairlines. Below N = 15 its events are drawn in a reserved band, with the mean's capped "
    "Student-t whisker and an uncapped ± 1 SD bar, the spread of the events: two marks, two "
    "quantities.")

CIRCULAR_RESIDUAL_NOTE = (
    "φ is an azimuth, so its residual is wrapped to (−π, π] and summarised on the circle: no "
    "arithmetic mean, whisker or σ band is drawn, and no bias, σ or σ/μ is quoted. Its centre "
    "is the circular mean direction, with Fisher's large-sample 95 % interval, and its spread "
    "the mean resultant length R̄ and the circular SD √(−2 ln R̄) (series.circular). The "
    "histogram and the RMSE of the wrapped residual stand; a Gaussian curve is drawn only as "
    "a fit of the core, labelled so (series.core_fit).")


def _xgb_notes(sel: Selection) -> dict[str, str]:
    notes = {
        "series": (
            "The shipped XGBoost regressor of this experiment's species and seed on the "
            "notebook's 20 % validation split (train_test_split(test_size=0.2, "
            "random_state=42)), the rows it was not trained on; the selection applies to them, "
            "and the training rows it selects are counted in split.n_training_excluded, not "
            "drawn."),
        "pairs": (
            f"Each count is an event. Below N = {MIN_DENSITY_SAMPLES} pairs the individual "
            "(truth, prediction) pairs are drawn instead of a density, because a cell of one or "
            "two events would be set by the binning, not by the model."),
        "axes": (
            "Truth and prediction share one range taken from the whole event table, whatever "
            "the selection, so the identity line is the diagonal and the picture does not move "
            "when a filter changes. Events beyond it are counted in outside, never dropped "
            "silently."),
        "residual": (
            "The residual is the quantity of the model-performance card. Its range is the "
            "1st to 99th percentile of the residuals when at least 20 are drawn "
            "(axis.clipping.applied); below that it is their full extent and axis.provisional "
            "is set. " + (CIRCULAR_RESIDUAL_NOTE if sel.label == "phi" else MARKS_NOTE)),
    }
    if sel.model == "energy":
        notes["calibration"] = (
            "The regressor predicts the momentum scale directly; no sampling-fraction "
            "calibration is applied.")
        notes["relative"] = (
            "A relative residual needs a positive truth; an event without one is left out and "
            "counted in residual.excluded.")
    elif sel.label == "phi":
        notes["angle"] = (
            "φ is an azimuth. The axes are the angle in mrad as stored and do not wrap: a "
            "prediction near −π for a truth near +π is a small error drawn in a far corner. "
            "The residual below is wrapped to (−π, π], so it measures that error as it is; "
            "the regressor's raw output can leave (−π, π], and is counted in outside when it "
            "leaves the axis.")
    else:
        notes["angle"] = (
            "The angle regressor predicts φ and θ; this is θ (label=phi draws φ). Axes and "
            "residuals are in mrad.")
    return {k: typographic(v) for k, v in notes.items()}


def _notes(sel: Selection) -> dict[str, str]:
    if sel.source == XGB_CODE:
        return _xgb_notes(sel)
    notes = {
        "pairs": (
            "Each count is a shower: shower A and shower B of an event are separate pairs and "
            f"are drawn apart. Below N = {MIN_DENSITY_SAMPLES} pairs a shower gets its "
            "individual (truth, prediction) pairs instead of a density, because a cell of one or "
            "two showers would be set by the binning, not by the network."),
        "axes": (
            "Truth and prediction share one range taken from the whole event table, whatever "
            "the selection, so the identity line is the diagonal and the picture does not move "
            "when a filter changes. Showers beyond it are counted in outside, never dropped "
            "silently."),
        "residual": (
            "The residual is the quantity of the model-performance cards. Its range is the "
            "1st to 99th percentile of the pooled residuals of the showers with "
            f"N ≥ {MIN_DENSITY_SAMPLES}, rounded outward, when at least 20 are pooled "
            "(axis.clipping.applied); below that the percentiles would be noise, the range is "
            "the full extent and axis.provisional is set. The showers beyond it are counted "
            "in axis.outside. " + MARKS_NOTE),
    }
    if sel.model == "energy":
        notes["calibration"] = (
            "The energy network predicts the momentum scale directly; no sampling-fraction "
            "calibration is applied.")
        notes["relative"] = (
            "A relative residual needs a positive truth; a shower without one is left out and "
            "counted in residual.excluded.")
    else:
        notes["angle"] = (
            "The angle network predicts the polar angle θ only, so there is no azimuth residual "
            "and nothing to wrap. Axes and residuals are in mrad.")
    return {k: typographic(v) for k, v in notes.items()}


def notices(sel: Selection, payload: dict[str, Any]) -> list[str]:
    """What a reader must be told about this selection (the response's ``meta.warnings``)."""
    out: list[str] = []
    if sel.n_events == 0:
        out.append("No events match the current selection.")
    for shower in sel.showers:
        block = payload["density"][shower]
        who = f"Shower {shower.upper()}"
        if block["encoding"] == "pairs" and block["n"]:
            out.append(typographic(
                f"{who} has N = {block['n']} (truth, prediction) pairs, below the "
                f"{MIN_DENSITY_SAMPLES} a density needs: its individual pairs are drawn."))
        elif not block["n"] and sel.n_events:
            out.append(f"{who} has no XGBoost validation event in this selection." if
                       sel.source == XGB_CODE else
                       f"{who} has no {sel.frame}-frame prediction in this selection.")
        lost = block["n_missing"]
        if lost["total"]:
            out.append(typographic(
                f"{who}: {lost['total']:,} selected event{'s' if lost['total'] != 1 else ''} "
                f"{'were' if lost['total'] != 1 else 'was'} left out for want of a finite "
                f"prediction ({lost['prediction']:,}) or truth ({lost['truth']:,}); counted, "
                "never zero-filled."))
        if block["outside"]["total"]:
            o = block["outside"]
            out.append(typographic(
                f"{who}: {o['total']:,} of {block['n']:,} pairs lie outside the shared axis "
                f"(truth {o['truth_below']:,} below and {o['truth_above']:,} above, prediction "
                f"{o['pred_below']:,} below and {o['pred_above']:,} above) and are counted, "
                "not drawn."))
    axis = payload["residual"]["axis"]
    if axis["provisional"] and any(s.size for s in sel.truth.values()):
        excluded = payload["residual"]["excluded"]["nonpositive_truth"]
        drawn = any(sel.truth[k].size - excluded.get(k, 0) >= MIN_DENSITY_SAMPLES
                    for k in sel.showers)
        reason = ("fewer than 20 residuals are pooled, so it is their full extent" if drawn
                  else f"no shower reaches N = {MIN_DENSITY_SAMPLES}")
        out.append(typographic(f"The residual range is provisional: {reason}."))
    return out


def assemble(sel: Selection, residual: dict[str, Any], bins: int) -> dict[str, Any]:
    """The payload for ``bins`` bins per axis (the residual block is built once, by the caller)."""
    labels = sel.labels
    unit = sel.unit
    density = {s: density_block(sel.truth[s], sel.pred[s], sel.lo, sel.hi, bins,
                                sel.n_missing.get(s))
               for s in sel.showers}
    peaks = [d["max_count"] for d in density.values()
             if d["encoding"] == "counts" and d["max_count"] > 0]
    # Every drawn cell holding one shower would give log10 = 0 = vmin, a scale a renderer
    # cannot normalise: the colour scale spans at least one count to two.
    vmax = max(math.log10(max(peaks)), math.log10(2)) if peaks else 0.0

    def axis(label: str) -> dict[str, Any]:
        return {"lo": sig(sel.lo), "hi": sig(sel.hi), "n": bins, "unit": unit,
                "label": typographic(label), "zero_based": sel.lo == 0.0}

    network: dict[str, Any] = {"model": sel.model, "frame": sel.frame}
    if sel.source == XGB_CODE:
        network.update(source=XGB_CODE, label=sel.label or XGB_LABELS[sel.model][0])
    payload = {
        "network": network,
        "n_events": sel.n_events,
        "axes": {"truth": axis(labels["truth"]), "pred": axis(labels["pred"])},
        "density": density,
        "identity": {"from": sig(sel.lo), "to": sig(sel.hi), "label": "prediction = truth"},
        "color": color_block(vmax),
        "residual": residual,
        "thresholds": {**ENERGY_THRESHOLDS, "density2d": MIN_DENSITY_SAMPLES},
        "notes": _notes(sel),
    }
    if sel.source == XGB_CODE:
        # n_events counts the validation pairs drawn; n_selected the selection's events,
        # validation and training rows alike, which the status bar reads.
        payload.update(source=XGB_CODE, labels=list(XGB_LABELS[sel.model]),
                       n_selected=sel.split.get("n_selected"), split=sel.split, run=sel.run)
        if sel.label == "phi":
            payload["axes"]["truth"]["circular"] = payload["axes"]["pred"]["circular"] = True
    return typographic_tree(payload)


def typographic_tree(node: Any) -> Any:
    """Every string of a payload with U+2212 for a negative number; keys and numbers untouched."""
    if isinstance(node, str):
        return typographic(node)
    if isinstance(node, dict):
        return {k: typographic_tree(v) for k, v in node.items()}
    if isinstance(node, list):
        return [typographic_tree(v) for v in node]
    return node


def next_bins(bins: int) -> int | None:
    """The largest ladder step below ``bins``; ``None`` at the floor."""
    return next((b for b in BINS_LADDER if b < bins), None)


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            model: str, coord_system: str, bins: int) -> dict[str, Any]:
    """Prediction against truth for one network over the selection."""
    sel = read(con, record, spec, model, coord_system)
    return assemble(sel, residual_block(sel), bins)


# ------------------------------------------------- the XGBoost series --


def read_xgb(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
             model: str, label: str | None) -> Selection:
    """The XGBoost validation pairs of the selection (one shower, ``a``), on dataset-wide axes."""
    from ..modelruns import store as xgb_store
    from ..modelruns import views as xgb_views
    from ..modelruns.pairing import label_column

    task = performance_bins.XGB_TASK[model]
    chosen = label or XGB_LABELS[model][0]
    # The gate is open, but the tables can still be gone: refused (422), never a 500.
    runs = xgb_views.require_runs(con, record, task, field="model")
    where = spec.where_sql("e")
    rows = xgb_store.read_holdout(con, record, task, where, spec.params())
    n_selected = xgb_store.count_selected(con, record, where, spec.params())
    scale = _scale(model)
    t, p = rows[f"true_{chosen}"], rows[f"pred_{chosen}"]
    keep = np.isfinite(t) & np.isfinite(p)
    producer = {"momentum": "incoming_momentum", "theta": "incoming_theta",
                "phi": "incoming_phi"}[chosen]
    column = label_column(producer)
    found = con.execute(
        f"SELECT min(CAST({column} AS DOUBLE)), max(CAST({column} AS DOUBLE)) "
        f"FROM {quote(naming.event_table(record.table_name))}").fetchone()
    lo, hi = _axis_range([v for v in found if v is not None], scale, model)
    run = xgb_views.run_block(runs, task)
    n_val = int(t.size)
    split = {
        "n_selected": n_selected, "n_validation": n_val,
        "n_training_excluded": n_selected - n_val, "fraction": xgb_views.TEST_SIZE,
        "rule": "train_test_split(np.arange(n), test_size=0.2, random_state=42) over the event "
                "table in event_number order (the producer file's order)",
        "reproduced": bool(run.get("split", {}).get("reproduced", True)),
    }
    missing = {"a": {"total": int((~keep).sum()), "prediction": int((~np.isfinite(p)).sum()),
                     "truth": int((~np.isfinite(t)).sum())}}
    return Selection(model, "lab", lo, hi, n_val, {"a": t[keep] * scale}, {"a": p[keep] * scale},
                     missing, source=XGB_CODE, label=chosen if model == "angle" else None,
                     split=split, run=run)


def _axis_range(found: Sequence[float], scale: float, model: str) -> tuple[float, float]:
    """The shared axis from the truth's extremes: scaled, rounded outward, energy from zero."""
    values = [float(v) * scale for v in found if math.isfinite(float(v))]
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    if not hi > lo:
        pad = max(abs(lo), 1.0) * 0.5
        lo, hi = lo - pad, hi + pad
    lo, hi, _ = clip_mod.nice_range(lo, hi, fine=True)
    if model == "energy" and lo > 0:
        lo = 0.0
    return float(lo), float(hi)
