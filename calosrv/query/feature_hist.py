"""The feature explorer's D4 histogram and D5 2-D histogram views.

A request names a frame and a shower. The bundle holds every offered feature
of that shower in that frame for the selected events - one read of the event
table, no hit scan - cached in the ``physics`` cache under the clamped
selection. Everything a view varies (class set, feature, scale, the eps
exclusion) is a NumPy step over the cached arrays.

Showers with fewer than two hits are left out on every kind, as the
producer's aggregate leaves them out: their SDs do not exist, and the two
kinds then describe the same events.

* **D4 histograms** - integer counts on edges every class shares: the Rice
  count of the smallest drawn class, aligned to the lattice quantum where the
  values are quantised. A KDE from N ≥ 8, the histogram from N ≥ 15, the
  events themselves below. The range and the automatic scale follow the
  measured values; events at core.py's floor are drawn and counted, not ranged.
* **D5 2-D histograms** - dense integer counts against the deposited energy,
  the pairs themselves below N = 15.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from ..encode.numbers import sig, sig_list
from ..stats import histogram, kde
from ..text import typographic
from . import features_catalog as catalog
from .feature_axes import (comb_cause, measure_comb, plan_axis, resolve_scale,
                           to_axis)
from .features import THRESHOLDS, ClassSet, FeatureBundle
from .features_catalog import Feature

#: The events drawn individually below the histogram floor: at most 14.
MAX_STRIP = histogram.MIN_HISTOGRAM_SAMPLES - 1

#: Bins per axis of the 2-D histograms: 48 for a few classes, 32 for many.
HIST2D_BINS = 48
HIST2D_BINS_MANY = 32
HIST2D_MANY_CLASSES = 6

#: The 2-D histograms' y feature: the notebook plots every feature against it.
HIST2D_Y = "total_hit_energy"

SILVERMAN_RULE = "Silverman: h = 0.9 · min(SD, IQR/1.349) · N^(−1/5), Gaussian kernel"

# -------------------------------------------------------------------- D4 --


def _class_values(bundle: FeatureBundle, cs: ClassSet, feature: Feature, exclude_eps: bool,
                  ) -> tuple[list[np.ndarray], list[int], list[np.ndarray]]:
    """``(values, n excluded, floored)`` per class; ``floored`` flags the values kept
    that involve core.py's floor - drawn and counted, never ranged on."""
    values = bundle.display(feature)
    eps = bundle.eps_mask(feature)
    out, excluded, floored = [], [], []
    for c in cs.classes:
        m = cs.mask(c.index)
        if exclude_eps and eps is not None:
            excluded.append(int((m & eps).sum()))
            m = m & ~eps
        else:
            excluded.append(0)
        out.append(values[m])
        floored.append(eps[m] if eps is not None else np.zeros(int(m.sum()), dtype=bool))
    return out, excluded, floored


def _floored_note(n_floored: int, feature: Feature) -> str:
    what = ("sit at core.py's 10⁻⁶ mm floor" if feature.eps == catalog.EPS_OWN
            else "have a factor of the volume at core.py's 10⁻⁶ mm floor")
    return (f"{n_floored:,} drawn events {what}: not measurements, so they set neither the "
            "range nor the automatic scale. They stay in the counts and the normaliser, "
            "counted per class (n_floored), and fall in n_below or n_above wherever the axis "
            "does not reach them. exclude_eps=true leaves them out.")


def _hist_message(n: int, feature: Feature, kde_notes: Sequence[str]) -> str | None:
    parts: list[str] = []
    if n == 0:
        return "No events in this class."
    if n < kde.MIN_KDE_SAMPLES:
        parts.append(f"N = {n}: below the {kde.MIN_KDE_SAMPLES}-event floor for a density "
                     "curve; the events themselves are drawn.")
    elif n < histogram.MIN_HISTOGRAM_SAMPLES:
        parts.append(f"N = {n}: the histogram is withheld below N = "
                     f"{histogram.MIN_HISTOGRAM_SAMPLES} - it would be a comb whose heights the "
                     "bin width sets - so the events are drawn with the density curve.")
    if feature.circular and n >= kde.MIN_KDE_SAMPLES:
        parts.append("No density curve for an azimuth: a linear kernel would smooth across "
                     "the ±π cut.")
    parts += [note for note in kde_notes if note]
    return typographic(" ".join(parts)) if parts else None


def hist_view(bundle: FeatureBundle, cs: ClassSet, feature: Feature, scale: str,
              exclude_eps: bool, pitch: float | None, curve_points: int = kde.CURVE_POINTS,
              bins_divisor: int = 1) -> dict[str, Any]:
    """D4: per-class counts on shared edges, KDE scaled to counts, strips below N = 15."""
    raw, excluded, floored = _class_values(bundle, cs, feature, exclude_eps)
    sizes = [int(np.isfinite(v).sum()) for v in raw]
    # The range and the automatic scale follow the measured values: a floored
    # value is not a measurement, and >1% of them would pin the 1st percentile.
    measured = [v[~f] for v, f in zip(raw, floored)]
    drawn_measured = [v for v, n in zip(measured, sizes) if n >= histogram.MIN_HISTOGRAM_SAMPLES]
    pooled_measured = np.concatenate(drawn_measured or measured or [np.empty(0)])
    resolved, decades = resolve_scale(feature, bundle.coord_system, scale, pooled_measured,
                                      "scale")
    on_axis = [to_axis(v, resolved) for v in raw]
    per_class = [v for v, _ in on_axis]
    ranged = [to_axis(v, resolved)[0] for v in measured]

    def bins_for(drawn_sizes: list[int]) -> int:
        rice = histogram.adaptive_bins(min(drawn_sizes) if drawn_sizes else 0)
        return max(histogram.MIN_BINS, rice // max(1, bins_divisor))

    axis = plan_axis(feature, bundle.coord_system, per_class, resolved, decades, bins_for,
                     pitch, np.concatenate(raw or [np.empty(0)]), range_per_class=ranged)
    width = axis.width
    q_axis = (float(axis.quantum["value"]) if axis.quantum and axis.quantum.get("verified")
              else None)
    curve_x = np.linspace(axis.lo, axis.hi, int(curve_points))
    series: list[dict[str, Any]] = []
    pooled_counts = np.zeros(axis.bins, dtype=np.int64)
    y_count = y_density = 0.0
    weak_peaks: list[tuple[int, float, float]] = []   # curves of classes that set no range
    n_floored = [int(f.sum()) for f in floored]
    for c, values, (_, n_nonpositive), n_eps, n_flo in zip(cs.classes, per_class, on_axis,
                                                           excluded, n_floored):
        n = int(values.size)
        counted = histogram.count_histogram(values, axis.edges)
        drawn = n >= histogram.MIN_HISTOGRAM_SAMPLES
        kde_block, kde_notes, peak = None, [], 0.0
        if not feature.circular and n >= kde.MIN_KDE_SAMPLES:
            result = kde.gaussian_kde_binned(values, axis.lo, axis.hi, points=int(curve_points),
                                             n_total=n, quantum=q_axis)
            if result.drawn:
                kde_block = {"bandwidth": sig(result.bandwidth), "rule": SILVERMAN_RULE,
                             "pdf": sig_list(result.pdf), "scale_to_counts": sig(n * width),
                             "n_outside_grid": result.n_outside_grid,
                             "per": "per decade" if axis.scale == "log" else f"per {feature.unit}"}
                peak = max(result.pdf, default=0.0)
            else:
                kde_notes = result.notes
        if drawn:
            top = float(max(counted.counts, default=0))
            pooled_counts += np.asarray(counted.counts, dtype=np.int64)
            y_count = max(y_count, top, peak * n * width)
            y_density = max(y_density, top / (n * width), peak)
        elif kde_block is not None:
            weak_peaks.append((c.index, peak * n * width, peak))
        strip = (sig_list(np.sort(values)[:MAX_STRIP])
                 if 0 < n < histogram.MIN_HISTOGRAM_SAMPLES else None)
        series.append({
            "index": c.index,
            "label": c.label,
            "n": n,
            "n_in_range": counted.n_in_range,
            "n_below": counted.n_below,
            "n_above": counted.n_above,
            "n_nonpositive": n_nonpositive,
            "n_excluded_eps": n_eps,
            "n_floored": n_flo,
            "draw": "histogram" if drawn else ("strip" if n else "none"),
            "counts": counted.counts if drawn else [],
            "density_scale": sig(1.0 / (n * width)) if n and width > 0 else None,
            "kde": kde_block,
            "strip": strip,
            "drives_scale": drawn,
            "message": _hist_message(n, feature, kde_notes),
        })
    drawn_any = any(s["drives_scale"] for s in series)
    if drawn_any:
        # A weak class's curve that overflows the robust range is clipped by
        # the interface and disclosed: its true peak travels here.
        overflow = [{"index": index, "peak_count": sig(pc), "peak_density": sig(pd)}
                    for index, pc, pd in weak_peaks if pc > y_count or pd > y_density]
        basis = f"classes with N ≥ {histogram.MIN_HISTOGRAM_SAMPLES}: their bars and curves"
    else:
        # Nothing robust: the weak curves set the range, labelled provisional;
        # with no curve at all there is no density axis to label.
        overflow = []
        y_count = max((pc for _, pc, _ in weak_peaks), default=0.0)
        y_density = max((pd for _, _, pd in weak_peaks), default=0.0)
        basis = (f"no class reaches N = {histogram.MIN_HISTOGRAM_SAMPLES}: the curves of the "
                 "smaller classes, provisional" if weak_peaks
                 else "no class supports a density: the axis carries no density scale")
    has_scale = drawn_any or bool(weak_peaks)
    comb = (measure_comb(pooled_counts, comb_cause(feature, bundle.coord_system))
            if drawn_any and not feature.circular else None)
    view_notes = list(axis.notes)
    if exclude_eps and bundle.eps_mask(feature) is not None:
        view_notes.append("Events whose value of this feature involves a floor are left out "
                          "and counted per class (n_excluded_eps).")
    if sum(n_floored):
        view_notes.append(_floored_note(sum(n_floored), feature))
    if axis.scale == "log" and any(n for _, n in on_axis):
        view_notes.append("Values at or below zero have no place on a log axis: they are "
                          "counted per class (n_nonpositive) and left out of the counts, the "
                          "curve and the normaliser.")
    if comb and comb.get("combed"):
        view_notes.append(comb["note"])
    return {
        "feature": feature.id,
        "scale": axis.scale,
        "requested_scale": scale,
        "axis": axis.as_dict(),
        "series": series,
        "curve_x": sig_list(curve_x),
        "y_max": {
            "count": sig(y_count) if has_scale else None,
            "density": sig(y_density) if has_scale else None,
            "provisional": not drawn_any,
            "overflow": overflow,
            "basis": typographic(basis),
        },
        "comb": comb,
        "exclude_eps": exclude_eps,
        "y_axis": {"default": "density", "density": "count × density_scale = count / (N · bin "
                   "width)", "count": "events per bin (the notebook's stat=count)"},
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }


# -------------------------------------------------------------------- D5 --


def _pairs(bundle: FeatureBundle, cs: ClassSet, fx: Feature, fy: Feature, exclude_eps: bool,
           ) -> tuple[list[tuple[np.ndarray, np.ndarray]], list[int], list[np.ndarray]]:
    """``(pairs, n excluded, floored)`` per class, ``floored`` flagging the kept pairs
    whose x value involves core.py's floor."""
    x_all, y_all = bundle.display(fx), bundle.display(fy)
    eps = bundle.eps_mask(fx)
    out, excluded, floored = [], [], []
    for c in cs.classes:
        m = cs.mask(c.index) & np.isfinite(x_all) & np.isfinite(y_all)
        if exclude_eps and eps is not None:
            excluded.append(int((m & eps).sum()))
            m = m & ~eps
        else:
            excluded.append(0)
        out.append((x_all[m], y_all[m]))
        floored.append(eps[m] if eps is not None else np.zeros(int(m.sum()), dtype=bool))
    return out, excluded, floored


def hist2d_view(bundle: FeatureBundle, cs: ClassSet, feature: Feature, scale: str,
                y_scale: str, exclude_eps: bool, pitch: float | None,
                bins: int | None = None) -> dict[str, Any]:
    """D5: the feature against the deposited energy, dense integer counts per class."""
    fy = catalog.BY_ID[HIST2D_Y]
    pairs, excluded, floored = _pairs(bundle, cs, feature, fy, exclude_eps)
    sizes = [int(x.size) for x, _ in pairs]
    drawn_idx = [i for i, n in enumerate(sizes) if n >= histogram.MIN_HISTOGRAM_SAMPLES]
    chosen = drawn_idx or list(range(len(pairs)))
    # The feature axis is ranged and scaled on the measured values, as D4.
    pooled_x = np.concatenate([pairs[i][0][~floored[i]] for i in chosen] or [np.empty(0)])
    pooled_y = np.concatenate([pairs[i][1] for i in chosen] or [np.empty(0)])
    sx, dx = resolve_scale(feature, bundle.coord_system, scale, pooled_x, "scale")
    sy, dy = resolve_scale(fy, bundle.coord_system, y_scale, pooled_y, "y_scale")

    # A pair needs both coordinates on their axes: a non-positive value on a
    # log axis drops the pair, counted per axis.
    placed, dropped, placed_floored = [], [], []
    for (x, y), f in zip(pairs, floored):
        keep = np.ones(x.size, dtype=bool)
        nx = ny = 0
        if sx == "log":
            nx = int((x <= 0).sum())
            keep &= x > 0
        if sy == "log":
            ny = int((y <= 0).sum())
            keep &= y > 0
        tx = np.log10(x[keep]) if sx == "log" else x[keep]
        ty = np.log10(y[keep]) if sy == "log" else y[keep]
        placed.append((tx, ty))
        dropped.append((nx, ny))
        placed_floored.append(f[keep])
    n_classes = sum(1 for n in sizes if n > 0)
    default_bins = HIST2D_BINS if n_classes <= HIST2D_MANY_CLASSES else HIST2D_BINS_MANY
    nb = int(bins) if bins else default_bins
    x_axis = plan_axis(feature, bundle.coord_system, [x for x, _ in placed], sx, dx,
                       lambda _: nb, pitch, np.concatenate([x for x, _ in pairs] or [np.empty(0)]),
                       range_per_class=[x[~f] for (x, _), f in zip(placed, placed_floored)])
    y_axis = plan_axis(fy, bundle.coord_system, [y for _, y in placed], sy, dy,
                       lambda _: nb, pitch, np.concatenate([y for _, y in pairs] or [np.empty(0)]))
    xe, ye = x_axis.edges, y_axis.edges
    series: list[dict[str, Any]] = []
    max_count = 0
    n_floored = [int(f.sum()) for f in placed_floored]
    for c, (x, y), (nx, ny), n_eps, n_flo in zip(cs.classes, placed, dropped, excluded,
                                                 n_floored):
        n = int(x.size)
        in_x = (x >= xe[0]) & (x <= xe[-1])
        in_y = (y >= ye[0]) & (y <= ye[-1])
        outside = {"x_below": int((x < xe[0]).sum()), "x_above": int((x > xe[-1]).sum()),
                   "y_below": int((y < ye[0]).sum()), "y_above": int((y > ye[-1]).sum()),
                   "total": int((~(in_x & in_y)).sum())}
        base = {"index": c.index, "label": c.label, "n": n, "n_nonpositive_x": nx,
                "n_nonpositive_y": ny, "n_excluded_eps": n_eps, "n_floored": n_flo}
        if n >= histogram.MIN_HISTOGRAM_SAMPLES:
            grid, _, _ = np.histogram2d(x[in_x & in_y], y[in_x & in_y], bins=[xe, ye])
            counts = grid.T.astype(np.int64)          # rows are y bins
            peak = int(counts.max(initial=0))
            max_count = max(max_count, peak)
            series.append({**base, "draw": "histogram", "counts": counts.ravel().tolist(),
                           "max_count": peak, "outside": outside})
        elif n:
            order = np.argsort(x, kind="stable")[:MAX_STRIP]
            series.append({**base, "draw": "pairs",
                           "pairs": [[sig(a), sig(b)] for a, b in zip(x[order], y[order])],
                           "outside": outside})
        else:
            series.append({**base, "draw": "none"})
    view_notes = list(dict.fromkeys(x_axis.notes + y_axis.notes))
    if sum(n_floored):
        view_notes.append(_floored_note(sum(n_floored), feature))
    if any(nx or ny for nx, ny in dropped):
        view_notes.append("Pairs with a value at or below zero on a log axis are left out and "
                          "counted per class and axis.")
    if any(s["draw"] == "pairs" for s in series):
        view_notes.append(f"Classes below N = {histogram.MIN_HISTOGRAM_SAMPLES} show their "
                          "events as points: a 2-D histogram of so few would be a scatter of "
                          "single counts.")
    return {
        "x": x_axis.as_dict(),
        "y": y_axis.as_dict(),
        "layout": "counts are row-major with rows the y bins: counts[iy * x.bins + ix]",
        "series": series,
        "color": {
            "scale": "log10",
            "vmin": 0.0,
            "vmax": sig(math.log10(max_count)) if max_count > 0 else 0.0,
            "max_count": max_count,
            "unit": "events per bin",
            "empty": "transparent",
            "provisional": max_count == 0,
            "note": typographic(
                "Colour is log10 of the count; an empty bin is transparent, and the first "
                "drawn level (count 1, log10 = 0) takes a ramp position with at least 3:1 "
                "contrast against the card."),
        },
        "exclude_eps": exclude_eps,
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }
