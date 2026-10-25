"""The feature explorer's D2 describe view.

A request names a frame and a shower. The bundle holds every offered feature
of that shower in that frame for the selected events - one read of the event
table, no hit scan - cached in the ``physics`` cache under the clamped
selection. Everything a view varies (class set, feature, scale, the eps
exclusion) is a NumPy step over the cached arrays.

Showers with fewer than two hits are left out on every kind, as the
producer's aggregate leaves them out: their SDs do not exist, and the two
kinds then describe the same events.

* **D2 describe** - pandas' describe() per class with both SD forms (ddof 1
  and 0), the mean's Student-t interval, the SD's χ² interval and standard
  error beside them, c4 and the low-N notes taken at the N each feature
  actually used; an azimuth gets the circular summary instead of a linear mean.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from ..encode.numbers import sig
from ..stats import circular, gaussian
from ..stats import describe as describe_mod
from ..text import typographic
from . import features_catalog as catalog
from .features import THRESHOLDS, ClassSet, FeatureBundle
from .features_catalog import Feature

# -------------------------------------------------------------------- D2 --

_DESCRIBE_KEYS = ("n", "n_missing", "mean", "mean_lo", "mean_hi", "sd", "sd_lo", "sd_hi",
                  "sd_population", "min", "q25", "q50", "q75", "max", "n_eps",
                  "sd_se", "c4", "robust")
_CIRCULAR_KEYS = ("mean_direction", "resultant", "circular_sd", "rayleigh_p", "note")


def _sd_se(sd: float | None, n: int) -> float | None:
    """The SD's standard error σ/√(2(N − 1)) under Gaussian values, as GaussianFit.sigma_error."""
    if sd is None or n < gaussian.MIN_MOMENT_SAMPLES:
        return None
    return sd / math.sqrt(2.0 * (n - 1))


def _intervals(v: np.ndarray) -> tuple[float, float, float, float] | None:
    """The mean's Student-t and the SD's χ² 95% intervals; ``None`` below N = 2."""
    n = int(v.size)
    if n < gaussian.MIN_MOMENT_SAMPLES:
        return None
    sd = float(v.std(ddof=gaussian.DDOF))
    mean = float(v.mean())
    df = n - 1
    half = gaussian.t_quantile_975(df) * sd / math.sqrt(n)
    return (mean - half, mean + half,
            sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=True)),
            sd * math.sqrt(df / gaussian.chi2_quantile(df, upper=False)))


def _describe_feature(bundle: FeatureBundle, members: Sequence[np.ndarray], feature: Feature,
                      exclude_eps: bool, intervals: bool,
                      notes_by_n: dict[int, str]) -> dict[str, Any]:
    """One feature's row of D2; ``notes_by_n`` collects describe()'s note for each N met.

    describe()'s note is a function of N alone - N = 2 is one degree of freedom,
    quartiles interpolate below 20 - so it travels once per N rather than in
    every cell, which would double a many-class, small-N table. An azimuth's
    note depends on its directions and stays in its circular block.
    """
    values = bundle.display(feature)
    eps = bundle.eps_mask(feature)
    rows: dict[str, list[Any]] = {k: [] for k in _DESCRIBE_KEYS}
    circ: dict[str, list[Any]] = {k: [] for k in _CIRCULAR_KEYS}
    for m in members:
        v = values[m]
        n_eps = None
        if eps is not None:
            e = eps[m]
            n_eps = int(e.sum())
            if exclude_eps:
                v = v[~e]
        d = describe_mod.describe(v)
        finite = v[np.isfinite(v)]
        moments = d.n >= gaussian.MIN_MOMENT_SAMPLES
        rows["n"].append(d.n)
        rows["n_missing"].append(d.n_nonfinite)
        rows["n_eps"].append(n_eps)
        rows["min"].append(sig(d.min))
        rows["max"].append(sig(d.max))
        # Every low-N label follows the N this feature actually described, after
        # the non-finite and the excluded values - not the class size.
        rows["robust"].append(d.n >= gaussian.MIN_ROBUST_SAMPLES)
        if feature.circular:
            # Never a linear mean, SD or quantile of an angle (CLAUDE.md section 2).
            for key in ("mean", "mean_lo", "mean_hi", "sd", "sd_lo", "sd_hi", "sd_population",
                        "q25", "q50", "q75", "sd_se", "c4"):
                rows[key].append(None)
            summary = circular.describe_circular(finite)
            circ["mean_direction"].append(sig(summary.mean_direction))
            circ["resultant"].append(sig(summary.resultant))
            circ["circular_sd"].append(sig(summary.circular_sd))
            circ["rayleigh_p"].append(sig(summary.rayleigh_p))
            circ["note"].append(typographic(summary.note) if summary.note else None)
            continue
        bounds = _intervals(finite) if intervals else None
        rows["mean"].append(sig(d.mean) if moments else None)
        rows["sd"].append(sig(d.sd) if moments else None)
        rows["sd_population"].append(sig(d.sd_population) if moments else None)
        rows["sd_se"].append(sig(_sd_se(d.sd, d.n)) if moments else None)
        rows["c4"].append(sig(gaussian.c4(d.n)) if moments else None)
        if d.note:
            notes_by_n.setdefault(d.n, typographic(d.note))
        for key, i in (("mean_lo", 0), ("mean_hi", 1), ("sd_lo", 2), ("sd_hi", 3)):
            rows[key].append(sig(bounds[i]) if bounds else None)
        for key in ("q25", "q50", "q75"):
            rows[key].append(sig(getattr(d, key)))
    out: dict[str, Any] = dict(rows)
    if not intervals:
        for key in ("mean_lo", "mean_hi", "sd_lo", "sd_hi"):
            out.pop(key)
    if feature.circular:
        out["circular"] = circ
    return out


def describe_view(bundle: FeatureBundle, cs: ClassSet, exclude_eps: bool,
                  intervals: bool = True) -> dict[str, Any]:
    """D2: the describe() table per class and feature, as struct of arrays per feature."""
    members = [np.flatnonzero(cs.mask(c.index)) for c in cs.classes]
    sizes = [int(m.size) for m in members]
    notes_by_n: dict[int, str] = {}
    table = {f.id: _describe_feature(bundle, members, f, exclude_eps, intervals, notes_by_n)
             for f in catalog.offered(bundle.kind)}
    small = [c.label for c, n in zip(cs.classes, sizes) if 1 < n < gaussian.MIN_ROBUST_SAMPLES]
    view_notes = [
        "Quartiles are np.percentile's linear interpolation, as pandas' describe(); SD is the "
        "sample SD (ddof = 1) and sd_population the ddof = 0 form, for comparison with the "
        "notebook. The mean's 95% interval is Student-t, t(0.975, N − 1) · SD/√N; the SD's is "
        "the χ² interval, which assumes Gaussian values and is too narrow for a heavy tail.",
        "sd_se = SD/√(2(N − 1)) is the SD's own standard error under the same Gaussian "
        "assumption; c4(N) = E[s]/σ is the bias the ddof = 1 SD keeps (it still runs 11.4% low "
        "at N = 3); robust marks N ≥ 20. All three use the N each feature actually "
        "described, after non-finite and excluded values, and so does the note each cell "
        "takes from notes_by_n at its own N - N = 2 is one degree of freedom.",
        "Azimuths get a circular summary - mean direction, mean resultant length R̄, circular "
        "SD and the Rayleigh p - and no linear mean, SD or quartile; min and max lie on "
        "(−π, π].",
    ]
    if small:
        view_notes.append(
            f"Below N = {gaussian.MIN_ROBUST_SAMPLES} the quartiles interpolate between "
            f"individual events ({', '.join(small)}).")
    if exclude_eps:
        view_notes.append(
            "Floored events are left out of the features whose value they set: width, height, "
            "depth and depth range by their own floor, the volume and both densities by any "
            "floored factor.")
    if not intervals:
        view_notes.append("The interval columns were dropped to keep the response within its "
                          "byte budget.")
    return {
        "table": table,
        # The class sizes; c4 and the robust flag are per feature in the table.
        "class_stats": [{"index": c.index, "n": n} for c, n in zip(cs.classes, sizes)],
        "notes_by_n": {str(n): notes_by_n[n] for n in sorted(notes_by_n)},
        "intervals": {
            "mean": "95% Student-t interval of the mean (uncertainty of the aggregate)",
            "sd": "95% χ² interval of the SD (assumes Gaussian values)",
        } if intervals else None,
        "exclude_eps": exclude_eps,
        "thresholds": dict(THRESHOLDS),
        "view_notes": [typographic(t) for t in view_notes],
    }
