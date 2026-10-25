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
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..encode.numbers import sig, sig_list
from ..stats import clip as clip_mod
from ..stats import histogram, metrics
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

#: Viridis' anchors, as ``static/js/palette.js`` interpolates them into its 256-entry table.
_VIRIDIS = (
    (68, 1, 84), (72, 34, 115), (64, 67, 135), (52, 94, 141), (41, 120, 142),
    (32, 144, 140), (34, 167, 132), (68, 190, 112), (121, 209, 81),
    (189, 222, 38), (253, 231, 37),
)

LABELS = {
    "energy": {
        "truth": "True incident momentum", "pred": "Predicted energy",
        "residual": "Relative energy residual (pred − true) / true", "residual_unit": "fraction",
    },
    "angle": {
        "truth": "True incident polar angle θ", "pred": "Predicted polar angle θ",
        "residual": "Polar-angle residual θ_pred − θ_true", "residual_unit": "mrad",
    },
}


# ------------------------------------------------------------------ colour --


def viridis(t: float) -> tuple[int, int, int]:
    """The colour at ramp position ``t`` of the frontend's Viridis table (entry ``round(255 t)``)."""
    index = int(min(1.0, max(0.0, t)) * 255 + 0.5)
    s = index / 255 * (len(_VIRIDIS) - 1)
    k = min(len(_VIRIDIS) - 2, int(s))
    f = s - k
    a, b = _VIRIDIS[k], _VIRIDIS[k + 1]
    r, g, b_ = (int(round(a[c] + (b[c] - a[c]) * f)) for c in range(3))
    return r, g, b_


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


def ramp_start(step: float = 0.05) -> float:
    """The first ramp position (a multiple of ``step``) that clears 3:1 against the card."""
    t = 0.0
    while t < 1.0 and contrast(viridis(t), CARD_RGB) < MIN_CONTRAST:
        t = round(t + step, 10)
    return t


def color_block(vmax: float) -> dict[str, Any]:
    """The log10 colour scale: where a count of one starts, and the stops from there to the peak."""
    start = ramp_start()
    first = viridis(start)
    ratio = contrast(first, CARD_RGB)
    plain = contrast(viridis(0.0), CARD_RGB)
    stops = [hex_of(viridis(start + (1.0 - start) * i / 6)) for i in range(7)]
    return {
        "scale": "log10",
        "vmin": 0,
        "vmax": sig(vmax),
        "unit": "showers per bin",
        "empty": "transparent",
        "palette": "viridis",
        "ramp": {
            "from": start, "to": 1.0, "stops": stops,
            "first_level": {"count": 1, "color": hex_of(first),
                            "contrast": round(ratio, 2), "against": CARD_HEX},
        },
        "note": typographic(
            f"log10 of the showers per bin, empty bins transparent. A bin holding one shower "
            f"is drawn at position {start:g} of Viridis, {hex_of(first)}, {ratio:.1f}:1 against "
            f"the {CARD_HEX} card: the ramp's own first colour, {hex_of(viridis(0.0))}, is "
            f"{plain:.2f}:1 and would make a count of one disappear."),
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

    @property
    def frame(self) -> str:
        return ddl.NETWORK_FRAME[self.coord_system]

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
    scale = _scale(model)
    parts: list[str] = []
    for shower in showers:
        truth, _ = performance_bins.network_columns(model, "lab", shower)
        parts.append(f"min(CAST({truth} AS DOUBLE)), max(CAST({truth} AS DOUBLE))")
    row = con.execute(f"SELECT {', '.join(parts)} FROM {table}").fetchone()
    found = [float(v) * scale for v in row if v is not None and math.isfinite(float(v))]
    if not found:
        return 0.0, 1.0
    lo, hi = min(found), max(found)
    if not hi > lo:
        pad = max(abs(lo), 1.0) * 0.5
        lo, hi = lo - pad, hi + pad
    lo, hi, _ = clip_mod.nice_range(lo, hi, fine=True)
    if model == "energy" and lo > 0:
        lo = 0.0
    return float(lo), float(hi)


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
    truth_by, pred_by = {}, {}
    for shower in showers:
        t, p = arrays[f"true_{shower}"], arrays[f"pred_{shower}"]
        keep = np.isfinite(t) & np.isfinite(p)
        truth_by[shower], pred_by[shower] = t[keep] * scale, p[keep] * scale
    lo, hi = dataset_range(con, record, model, showers)
    n_events = int(next(iter(arrays.values())).size) if arrays else 0
    return Selection(model, coord_system, lo, hi, n_events, truth_by, pred_by)


# ----------------------------------------------------------------- density --


def density_block(truth: np.ndarray, pred: np.ndarray, lo: float, hi: float,
                  bins: int) -> dict[str, Any]:
    """One shower's pairs: a dense count raster from N = 15, the pairs themselves below.

    ``counts`` is row-major with one row per prediction bin and one column
    per truth bin; a value on ``hi`` falls in the last bin, as in NumPy.
    """
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
        else:
            excluded[shower] = 0
            out[shower] = p - t
    return out, excluded


def residual_block(sel: Selection) -> dict[str, Any]:
    """Each shower's residual histogram, curve, strip and markers, with its estimates beside them."""
    values, excluded = residuals(sel)
    labels = LABELS[sel.model]
    drawn = [s for s in sel.showers if values[s].size >= MIN_DENSITY_SAMPLES]
    provisional = not drawn
    pooled = np.concatenate([values[s] for s in (drawn or sel.showers)] or [np.empty(0)])
    clipping = clip_mod.percentile_clip(pooled, low=clip_mod.DEFAULT_LOW_PERCENTILE,
                                        high=clip_mod.DEFAULT_HIGH_PERCENTILE, pad=0.05)
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
        "axis": {
            "lo": lo, "hi": hi, "interval": interval, "bins": bins,
            "clipping": clipping.as_dict(),
            "provisional": provisional,
            "basis": (
                f"pooled residuals of the showers with N ≥ {MIN_DENSITY_SAMPLES}" if drawn else
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


def _notes(sel: Selection) -> dict[str, str]:
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
            "1st to 99th percentile of the showers with "
            f"N ≥ {MIN_DENSITY_SAMPLES}, rounded outward; the showers beyond it are counted "
            "in axis.outside. The mean's whisker is its Student-t interval and the σ band is "
            "the spread of the showers: two marks, two quantities."),
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
            out.append(f"{who} has no {sel.frame}-frame prediction in this selection.")
        if block["outside"]["total"]:
            o = block["outside"]
            out.append(typographic(
                f"{who}: {o['total']:,} of {block['n']:,} pairs lie outside the shared axis "
                f"(truth {o['truth_below']:,} below and {o['truth_above']:,} above, prediction "
                f"{o['pred_below']:,} below and {o['pred_above']:,} above) and are counted, "
                "not drawn."))
    if payload["residual"]["axis"]["provisional"] and any(
            s.size for s in sel.truth.values()):
        out.append(typographic(
            f"The residual range is provisional: no shower reaches N = {MIN_DENSITY_SAMPLES}."))
    return out


def assemble(sel: Selection, residual: dict[str, Any], bins: int) -> dict[str, Any]:
    """The payload for ``bins`` bins per axis (the residual block is built once, by the caller)."""
    labels = LABELS[sel.model]
    unit = sel.unit
    density = {s: density_block(sel.truth[s], sel.pred[s], sel.lo, sel.hi, bins)
               for s in sel.showers}
    peaks = [d["max_count"] for d in density.values()
             if d["encoding"] == "counts" and d["max_count"] > 0]
    vmax = math.log10(max(peaks)) if peaks else 0.0

    def axis(label: str) -> dict[str, Any]:
        return {"lo": sig(sel.lo), "hi": sig(sel.hi), "n": bins, "unit": unit,
                "label": typographic(label), "zero_based": sel.lo == 0.0}

    payload = {
        "network": {"model": sel.model, "frame": sel.frame},
        "n_events": sel.n_events,
        "axes": {"truth": axis(labels["truth"]), "pred": axis(labels["pred"])},
        "density": density,
        "identity": {"from": sig(sel.lo), "to": sig(sel.hi), "label": "prediction = truth"},
        "color": color_block(vmax),
        "residual": residual,
        "thresholds": {**ENERGY_THRESHOLDS, "density2d": MIN_DENSITY_SAMPLES},
        "notes": _notes(sel),
    }
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
