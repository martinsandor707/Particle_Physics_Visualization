"""The energy resolution against 1/√E: the ``res-scaling`` card of Page 2.

A calorimeter's resolution is quoted as ``σ/E = a/√E ⊕ b``: a stochastic term
that falls as 1/√E and a constant term that does not. Plotted against
``x = 1/√E`` the stochastic term is a straight line through the origin, which
sits at the right-hand border of a reversed axis (E → ∞). This module measures
σ/E per momentum window for every series the experiment carries and fits that
line to it; ``stats/resolution_fit.py`` holds the fits.

**One estimator for every series: the per-event response ratio.** In window k
(the producer's integer momentum bin, [k, k + 1) GeV, of the shower's own
momentum) each usable event gives ``R = E_est / p``: ``c·E_dep`` for the
detector, with ``c`` the shower's selection-wide calibration
(``response.calibrate``); the energy network's prediction over its truth; the
XGBoost momentum regressor's prediction over the true momentum. The plotted
value is ``s(R)/R̄`` (ddof = 1) in percent, its whisker the χ²_{N−1} interval
of ``s`` divided by ``R̄`` (Page 1's resolution whisker), its fit weight the
delta-method standard error, and its abscissa ``x = ⟨1/√p⟩`` over the
window's events. Dividing by p event by event removes the window's own
momentum spread (5.2% at 5 GeV, 1.5% at 19 GeV for a 1 GeV window) and each
estimator's per-energy bias, and ``c`` cancels in ``s/R̄``: the detector series
does not depend on the calibration. It is Page 1's response-ratio series
(``response.KIND_RATIO``), so the two cards agree.

**The detector series is a benchmark, not a limit.** ``c·E_dep`` is a plain
linear sum; a model that reads the shower's shape (leakage, compensation) can
beat it, so it is labelled "Calibrated deposit c·E_dep — linear-sum benchmark".

**Gates** (CLAUDE.md, the low-N table): σ/E is reported from N = 2, a window
is drawn with its whisker from N = 8, and it enters the fits and sets the y
range from N = 20 *and* p ≥ 4 GeV. Below 4 GeV, x > 0.5 and the window lies off
the axis; it is counted and listed, never drawn.

**The E view.** The same response serves the card's second view, σ/E against
the energy E in GeV on a linear axis (``axis.energy``), so switching views
sends no request. A window is drawn there at ``E = 1/x²`` of the very
``x = ⟨1/√p⟩`` the fits used: one exact bijection, so a window on its fitted
line in the 1/√E view sits on its fitted curve in E, and its ⟨p⟩, slightly
larger (Jensen's inequality), travels in ``p_mean``. The E view draws the
origin-pinned a₀/√E and, where both terms are defined, the quadrature
a/√E ⊕ b, each from the band ``stats/resolution_fit.band`` gives; the affine
fit stays on the 1/√E view. A curve is solid over its mode's ``span_gev``, the
edges of the windows it was fitted to, dashed beyond and never drawn below
:data:`E_MIN_GEV`. The windows below 4 GeV, off the 1/√E axis, are on this
one, so its σ/E range is its own (``ResolutionScaling.energy_y``): set by the
windows of N ≥ 20 from :data:`E_VIEW_Y_MIN_GEV` (whiskers included) and by the
non-provisional drawn fits over their fitted spans, line only, never the band
or the extrapolation. A window below 2 GeV never sets it, provisional or not:
measured on eight stored experiments (2026-11-10), the windows of N ≥ 20 top
out at 23–101% from 1 GeV and at 20–66% from 2 GeV, so a 1–2 GeV window would
spend the axis on itself. It is counted in ``n_clipped`` when it leaves the top.
The 1/√E view's axis, notes and fits are untouched by any of this.

**Anchors that do not move with the selection.** The default fit runs through
three nominal windows chosen on the whole table's bin axis
(``performance_bins.dataset_axis``): the lowest bin from 5 GeV (below it the
sampling fraction is still rising, which a/√E + b does not describe), the
highest bin, and the bin between them nearest in log E to the geometric mean of
their centres. On the 0–20 GeV files that is {5, 10, 19}. A series whose
anchor window is thin takes its nearest eligible window from 5 GeV instead, by
name, never one below the floor the low anchor keeps; with too few eligible
windows the fit falls back to windows of N ≥ 8 and is labelled provisional.
The "all windows" mode fits every eligible window from 4 GeV, the 4–5 GeV
window included, as asked of it, and its notes say so. Both modes are computed
here; the card's toggle only repaints.

**Reads.** The event table (one row per event: deposits, momenta, bins, the
networks' predictions) and, on an aggregate, the XGBoost prediction table. No
hit is scanned, so a selection of the whole production file costs
milliseconds.
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
from ..encode.numbers import SIGNIFICANT
from ..errors import ValidationError
from ..stats import gaussian
from ..stats import resolution_fit as rfit
from ..text import typographic
from . import capabilities, performance_bins, response
from . import showers as showers_mod
from .filters import FilterSpec

# ------------------------------------------------------------ constants --
# The Methodology article resolves these names (static/js/methodology/constants.js).

#: The bottom axis runs from 0 (E → ∞) to this x = 1/√E, in GeV^−1/2.
X_MAX = 0.5
#: Below this momentum x > X_MAX: the window is off the axis (= 1 / X_MAX²).
E_MIN_GEV = 4.0
#: The low nominal anchor is the lowest bin starting at or above this momentum.
ANCHOR_LOW_GEV = 5.0
N_ANCHORS = 3
#: σ/E is reported (tooltip, drawer) from this N.
REPORT_MIN_N = gaussian.MIN_MOMENT_SAMPLES
#: A window is drawn with its χ² whisker from this N (the CLAUDE.md curve floor).
WHISKER_MIN_N = gaussian.MIN_CURVE_SAMPLES
#: A window enters the fits and sets the y range from this N (the robust floor).
FIT_MIN_N = gaussian.MIN_ROBUST_SAMPLES
#: The top axis's ticks: E = 1/x², plus ∞ at x = 0.
ENERGY_TICKS_GEV: tuple[int, ...] = (5, 10, 15, 20, 30, 50, 100)
#: Points of a fit's line and 95% band over [0, X_MAX].
BAND_POINTS = 21
#: The E view's axis ends here (GeV), or at the dataset's highest window edge rounded up to
#: E_VIEW_INTERVAL_GEV when that is higher.
E_VIEW_MAX_GEV = 80.0
#: Tick interval of the E view's energy axis (GeV).
E_VIEW_INTERVAL_GEV = 10.0
#: A window sets the E view's σ/E range only from this lower edge (GeV): below it never.
E_VIEW_Y_MIN_GEV = 2.0
#: Points in E at which a fit's line is evaluated over its fitted span for the E view's range.
SPAN_POINTS = 41

UNIT = "%"
SOURCE_DETECTOR, SOURCE_NETWORK, SOURCE_XGB = "detector", "network", "xgb"
MODES: tuple[str, ...] = ("anchors", "all")

#: The budget guard's ladder: (significant figures, band points).
FIDELITY_STEPS: tuple[tuple[int, int], ...] = (
    (SIGNIFICANT, BAND_POINTS), (5, BAND_POINTS), (4, BAND_POINTS), (4, 11),
)

#: A one-shower selection is named after its species when one covers this share of it:
#: of every selected event, those without a primary particle included.
DOMINANT_SHARE = 0.95

DETECTOR_LABEL = "Calibrated deposit c·E_dep — linear-sum benchmark"
XGB_LABEL = "XGBoost momentum regressor · validation split"
FRAME_WORDS: dict[str, str] = {
    "absolute": "absolute", "trans": "per-shower translated", "local": "local",
}

#: ``particle_type`` codes of the single-shower hit files and the producer's species
#: words, as the card names them. A word that does not fix a charge (pion, muon) is
#: named without one: a charge is never guessed.
SPECIES_CODES: dict[str, str] = {
    "e-": "Electron e⁻", "e+": "Positron e⁺", "gamma": "Photon γ", "neutron": "Neutron n",
    "proton": "Proton p", "pi+": "Pion π⁺", "pi-": "Pion π⁻", "mu-": "Muon μ⁻",
    "mu+": "Muon μ⁺",
}
SPECIES_WORDS: dict[str, str] = {
    "electron": "Electron e⁻", "positron": "Positron e⁺", "photon": "Photon γ",
    "gamma": "Photon γ", "proton": "Proton p", "neutron": "Neutron n",
    "pion": "Pion", "muon": "Muon",
}

_NO_MODEL_SINGLE_HITS = (
    "A single-shower hit experiment carries no reconstruction network, and the XGBoost models "
    "read the 59-column aggregate only, so only the detector series is drawn."
)


# --------------------------------------------------------------- anchors --


def _centre(axis: performance_bins.BinAxis, i: int) -> float:
    return 0.5 * (axis.p_lo[i] + axis.p_hi[i])


def nominal_anchors(axis: performance_bins.BinAxis) -> tuple[int, ...]:
    """The nominal anchor bins of a bin axis: low, middle, high.

    Low is the lowest bin with ``p_lo ≥ ANCHOR_LOW_GEV``, high the highest
    bin, middle the bin strictly between them whose centre is nearest in
    ``|ln|`` to the geometric mean of their centres (ties to the lower bin).
    0–19 gives (5, 10, 19); 2–17 gives (5, 9, 17). Fewer when the axis has
    fewer bins from 5 GeV.
    """
    eligible = [i for i, lo in enumerate(axis.p_lo) if lo >= ANCHOR_LOW_GEV]
    if not eligible:
        return ()
    low, high = eligible[0], len(axis.numbers) - 1
    if high == low:
        return (axis.numbers[low],)
    target = math.sqrt(_centre(axis, low) * _centre(axis, high))
    between = range(low + 1, high)
    if not between:
        return (axis.numbers[low], axis.numbers[high])
    middle = min(between, key=lambda i: (abs(math.log(_centre(axis, i) / target)), i))
    return (axis.numbers[low], axis.numbers[middle], axis.numbers[high])


# --------------------------------------------------------------- windows --


@dataclass
class Window:
    """One momentum window of one series: the moments of R and where it may be drawn."""

    bin: int
    label: str
    p_lo: float
    p_hi: float
    fit: gaussian.GaussianFit
    p_mean: float
    x: float
    momentum_spread: float | None

    @property
    def n(self) -> int:
        return self.fit.n

    @property
    def centre(self) -> float:
        return 0.5 * (self.p_lo + self.p_hi)

    @property
    def r(self) -> float | None:
        """σ/μ as a fraction, where μ > 0 makes it a resolution."""
        f = self.fit
        if f.resolution is None or f.mu is None or not f.mu > 0:
            return None
        return f.resolution

    @property
    def ci(self) -> tuple[float, float] | None:
        f = self.fit
        if self.r is None or f.sigma_ci95 is None:
            return None
        return f.sigma_ci95[0] / f.mu, f.sigma_ci95[1] / f.mu

    @property
    def se(self) -> float | None:
        return self.fit.resolution_error if self.r is not None else None

    @property
    def off_axis(self) -> bool:
        return self.p_lo < E_MIN_GEV

    @property
    def usable(self) -> bool:
        """A point a fit can weight: a resolution with a positive standard error."""
        return self.r is not None and self.se is not None and self.se > 0

    def fittable(self, threshold: int) -> bool:
        return self.n >= threshold and not self.off_axis and self.usable

    @property
    def eligible(self) -> bool:
        return self.fittable(FIT_MIN_N)

    @property
    def whisker(self) -> bool:
        return self.n >= WHISKER_MIN_N and self.ci is not None

    def as_dict(self) -> dict[str, Any]:
        f, r, ci, n = self.fit, self.r, self.ci, self.n
        return {
            "bin": self.bin, "label": self.label, "p_lo": self.p_lo, "p_hi": self.p_hi,
            "n": n, "p_mean": self.p_mean, "x": self.x,
            "mean_r": f.mu, "sd_r": f.sigma,
            "value": None if r is None else 100.0 * r,
            "ci95": None if ci is None else [100.0 * ci[0], 100.0 * ci[1]],
            "se_delta": None if self.se is None else 100.0 * self.se,
            "c4": (f.sigma_bias_factor
                   if REPORT_MIN_N <= n < gaussian.MIN_CORE_SAMPLES else None),
            "bias": None if f.mu is None else 100.0 * (f.mu - 1.0),
            "momentum_spread": self.momentum_spread,
            "dof_note": response._dof_note(n),
            "weak": n < FIT_MIN_N,
            "whisker": self.whisker,
            "eligible": self.eligible,
            "off_axis": self.off_axis,
        }


def windows_of(ratio: np.ndarray, p: np.ndarray, bins: np.ndarray,
               axis: performance_bins.BinAxis) -> list[Window]:
    """Every populated window of one series, in the axis's order."""
    out = []
    for i, k in enumerate(axis.numbers):
        mask = bins == k
        if not mask.any():
            continue
        pk = p[mask]
        n = int(pk.size)
        p_mean = float(pk.mean())
        spread = (100.0 * float(pk.std(ddof=gaussian.DDOF)) / p_mean
                  if n >= 2 and p_mean > 0 else None)
        out.append(Window(
            bin=int(k), label=axis.labels[i], p_lo=float(axis.p_lo[i]), p_hi=float(axis.p_hi[i]),
            fit=gaussian.fit_gaussian(ratio[mask]), p_mean=p_mean,
            x=float(np.mean(1.0 / np.sqrt(pk))), momentum_spread=spread,
        ))
    return out


# ------------------------------------------------------------------ fits --


@dataclass
class ModeFits:
    """One window mode of one series: the points it fits and the three fits."""

    points: list[int]
    substitutions: list[dict[str, Any]]
    fallback: bool
    fits: dict[str, rfit.Fit | None]

    @property
    def provisional(self) -> bool:
        return self.fallback


def _nearest(target: float, pool: Sequence[Window]) -> Window:
    return min(pool, key=lambda w: (abs(math.log(w.centre / target)), w.bin))


def _choose_anchors(nominal: Sequence[int], windows: Sequence[Window], threshold: int,
                    axis: performance_bins.BinAxis | None = None
                    ) -> tuple[list[int], list[dict[str, Any]]]:
    """The nominal anchors this series can fit, each thin one replaced by its nearest candidate.

    A candidate is a window with ``N ≥ threshold`` from ``ANCHOR_LOW_GEV``, the
    low anchor's own floor (below it the sampling fraction is still rising): a
    thin anchor takes the candidate nearest in ``|ln|`` of the centres that no
    other anchor uses, or is dropped when none is left. ``axis`` names and
    places an anchor the series holds no event in.
    """
    by_bin = {w.bin: w for w in windows}
    on_axis = ({k: (axis.labels[i], 0.5 * (axis.p_lo[i] + axis.p_hi[i]))
                for i, k in enumerate(axis.numbers)} if axis is not None else {})
    candidates = [w for w in windows if w.fittable(threshold) and w.p_lo >= ANCHOR_LOW_GEV]
    chosen = {k for k in nominal if k in by_bin and by_bin[k].fittable(threshold)}
    substitutions = []
    for k in nominal:
        if k in chosen:
            continue
        have = by_bin.get(k)
        n = have.n if have else 0
        label, centre = ((have.label, have.centre) if have else
                         on_axis.get(k, (f"bin {k}", k + 0.5)))
        pool = [w for w in candidates if w.bin not in chosen]
        floor = f"N ≥ {threshold}" + (" (provisional)" if threshold < FIT_MIN_N else "")
        if not pool:
            substitutions.append({"nominal": k, "used": None, "reason": (
                f"The nominal anchor {label} holds N = {n} for this series and no other window "
                f"from {ANCHOR_LOW_GEV:g} GeV with {floor} is left: it is dropped.")})
            continue
        best = _nearest(centre, pool)
        chosen.add(best.bin)
        substitutions.append({"nominal": k, "used": best.bin, "reason": (
            f"The nominal anchor {label} holds N = {n} for this series, below "
            f"{threshold}; the nearest window from {ANCHOR_LOW_GEV:g} GeV in log E with {floor} "
            f"is {best.label} (N = {best.n}).")})
    return sorted(chosen), substitutions


def _fits(points: Sequence[Window]) -> dict[str, rfit.Fit | None]:
    x = [w.x for w in points]
    r = [w.r for w in points]
    n = [w.n for w in points]
    return {
        rfit.FORM_AFFINE: rfit.fit_affine(x, r, n),
        rfit.FORM_PINNED: rfit.fit_pinned(x, r, n),
        rfit.FORM_QUADRATURE: rfit.fit_quadrature(x, r, n),
    }


def mode_fits(mode: str, nominal: Sequence[int], windows: Sequence[Window],
              axis: performance_bins.BinAxis | None = None) -> ModeFits:
    """The points of one mode and its fits, with the N ≥ 8 fallback when fewer than two remain."""
    by_bin = {w.bin: w for w in windows}

    def pick(threshold: int) -> tuple[list[int], list[dict[str, Any]]]:
        if mode == "anchors":
            return _choose_anchors(nominal, windows, threshold, axis)
        return [w.bin for w in windows if w.fittable(threshold)], []

    points, substitutions = pick(FIT_MIN_N)
    fallback = False
    if len(points) < rfit.MIN_POINTS[rfit.FORM_AFFINE]:
        weak_points, weak_subs = pick(WHISKER_MIN_N)
        if len(weak_points) > len(points):
            points, substitutions, fallback = weak_points, weak_subs, True
    return ModeFits(points, substitutions, fallback, _fits([by_bin[k] for k in points]))


# ---------------------------------------------------------------- series --


@dataclass
class Series:
    """One estimator of one shower across the windows, with both modes' fits."""

    source: str
    shower: str
    shower_label: str
    estimator_label: str
    colour_slot: str
    windows: list[Window]
    modes: dict[str, ModeFits]
    n_dropped: int = 0
    n_absent: int = 0
    n_missing: int = 0

    @property
    def key(self) -> str:
        return f"{self.source}:{self.shower}"

    @property
    def label(self) -> str:
        return f"{self.shower_label} · {self.estimator_label}"

    @property
    def n(self) -> int:
        return sum(w.n for w in self.windows)


def build_series(source: str, shower: str, shower_label: str, estimator_label: str,
                 colour_slot: str, ratio: np.ndarray, p: np.ndarray, bins: np.ndarray,
                 axis: performance_bins.BinAxis, nominal: Sequence[int], **counts: int) -> Series:
    windows = windows_of(ratio, p, bins, axis)
    modes = {mode: mode_fits(mode, nominal, windows, axis) for mode in MODES}
    return Series(source, shower, shower_label, estimator_label, colour_slot, windows, modes,
                  **counts)


def _pairs(est: np.ndarray, true: np.ndarray, bins: np.ndarray
           ) -> tuple[np.ndarray, int, int]:
    """Usable rows of a model series: ``(mask, n_missing, n_dropped)``.

    Missing: no finite prediction or truth (a shower without hits has none).
    Dropped: both finite, but a truth that is not positive or no momentum bin;
    neither is ever zero-filled.
    """
    finite = np.isfinite(est) & np.isfinite(true)
    usable = finite & (true > 0) & np.isfinite(bins)
    return usable, int((~finite).sum()), int((finite & ~usable).sum())


# --------------------------------------------------------------- species --


def species_label(code: str | None = None, word: str | None = None) -> str | None:
    """The card's name for a ``particle_type`` code or a producer's species word."""
    if code is not None:
        return SPECIES_CODES.get(code)
    if word:
        return SPECIES_WORDS.get(word.lower(), word.capitalize())
    return None


def _dominant_species(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                      spec: FilterSpec) -> tuple[str | None, str]:
    """The selection's dominant ``primary_type`` where it covers ≥ 95% of the selected events.

    The share is of every selected event: an event without a primary particle
    counts against the name, since nothing says it is of that species.
    """
    table = quote(naming.event_table(record.table_name))
    try:
        rows = con.execute(
            f"SELECT primary_type, count(*) AS n FROM {table} WHERE {spec.where_sql()} "
            "GROUP BY 1 ORDER BY n DESC, 1",
            spec.params()).fetchall()
    except duckdb.Error:
        return None, "The event table holds no primary_type, so the shower is not named."
    total = sum(int(n) for _, n in rows)
    typed = [(code, int(n)) for code, n in rows if code is not None]
    if not typed:
        return None, "No selected event has a primary particle, so the shower is not named."
    code, n = typed[0]
    share = n / total
    untyped = total - sum(m for _, m in typed)
    without = (f"; {untyped:,} of them have no primary particle" if untyped else "")
    label = species_label(code=code)
    if share >= DOMINANT_SHARE and label is not None:
        return label, (f"The shower is named {label}: the primary particle of {n:,} of the "
                       f"{total:,} selected events ({100 * share:.1f}%{without}).")
    return None, (f"The shower is not named after a species: the commonest primary particle, "
                  f"{code}, covers {100 * share:.1f}% of the {total:,} selected events{without}, "
                  f"below {100 * DOMINANT_SHARE:g}%.")


# ------------------------------------------------------------- the lot --


def fitted_span(points: Sequence[int], windows: Sequence[Window]) -> list[float] | None:
    """``[lo, hi]`` in GeV: the smallest ``p_lo`` and the largest ``p_hi`` of the fitted windows.

    The E view draws a fit solid over this span and dashed beyond it. ``None``
    when the mode fits no window.
    """
    chosen = set(points)
    fitted = [w for w in windows if w.bin in chosen]
    if not fitted:
        return None
    return [min(w.p_lo for w in fitted), max(w.p_hi for w in fitted)]


def _span_line(fit: rfit.Fit, span: Sequence[float]) -> np.ndarray:
    """The fit's σ/E in percent at :data:`SPAN_POINTS` energies over ``span``, line only."""
    energies = np.linspace(span[0], span[1], SPAN_POINTS)
    return 100.0 * rfit.band(fit, 1.0 / np.sqrt(energies))[0]


def energy_extents(series: Sequence[Series]) -> tuple[list[response.Extent], list[float]]:
    """The E view's range extents, and the tops of the windows below the 2 GeV floor.

    Extents: every window with a σ/E, N ≥ :data:`REPORT_MIN_N` and
    ``p_lo ≥ E_VIEW_Y_MIN_GEV`` (off the 1/√E axis or not), its whisker
    included where it has one, robust from N ≥ :data:`FIT_MIN_N` with a
    positive SE; and every non-provisional mode's drawn fits, the quadrature
    one where both terms are defined and the pinned one, as lines over their
    fitted span. The tops (marker, or whisker top where it has one) of the
    windows below the floor are returned apart: they never enter
    ``response._y_axis``, and are only counted against the top it sets.
    """
    out: list[response.Extent] = []
    below: list[float] = []
    for s in series:
        for w in s.windows:
            r = w.r
            if r is None or w.n < REPORT_MIN_N:
                continue
            lo, hi = 100.0 * r, 100.0 * r
            if w.whisker:
                lo, hi = 100.0 * min(r, w.ci[0]), 100.0 * max(r, w.ci[1])
            if w.p_lo < E_VIEW_Y_MIN_GEV:
                below.append(hi)
                continue
            out.append(response.Extent(lo, hi, 100.0 * r, w.n >= FIT_MIN_N and w.usable))
        for mode in s.modes.values():
            span = fitted_span(mode.points, s.windows)
            if mode.provisional or span is None:
                continue
            drawn = []
            quad = mode.fits.get(rfit.FORM_QUADRATURE)
            if quad is not None and quad.theta[0] > 0 and quad.theta[1] > 0:
                drawn.append(quad)
            pinned = mode.fits.get(rfit.FORM_PINNED)
            if pinned is not None:
                drawn.append(pinned)
            for fit in drawn:
                line = _span_line(fit, span)
                top = float(line.max())
                out.append(response.Extent(max(0.0, float(line.min())), top, top, True))
    return out, below


def energy_y_axis(series: Sequence[Series]) -> dict[str, Any]:
    """The E view's zero-based σ/E range, with the windows below 2 GeV counted when clipped."""
    extents, below = energy_extents(series)
    y = response._y_axis(extents)
    y["n_clipped"] += sum(1 for top in below if top > y["hi"])
    return y


def _curve(fit: rfit.Fit, points: int) -> list[list[float]]:
    xs = np.linspace(0.0, X_MAX, points)
    y, lo, hi = rfit.band(fit, xs)
    return [[float(a), 100.0 * float(b), 100.0 * float(c), 100.0 * float(d)]
            for a, b, c, d in zip(xs, y, lo, hi)]


def _fit_note(fit: rfit.Fit, provisional: bool) -> str:
    equation = {
        rfit.FORM_AFFINE: "σ/E = a/√E + b",
        rfit.FORM_PINNED: "σ/E = a₀/√E, through the origin",
        rfit.FORM_QUADRATURE: "σ/E = √(a²/E + b²), fitted as (σ/E)² = A/E + B",
    }[fit.form]
    parts = [f"{equation}: weighted least squares over {fit.n_points} window"
             f"{'s' if fit.n_points != 1 else ''}, weights 1/se² with se recomputed at the fitted "
             f"value ({fit.iterations} refit{'s' if fit.iterations != 1 else ''}"
             f"{'' if fit.converged else ', not converged'})."]
    if fit.ndf == 0:
        parts.append("ν = 0: the fit passes through its points exactly, so there is no χ² test.")
    else:
        parts.append(f"χ²/ν = {fit.chi2:.3g}/{fit.ndf}, p = {fit.p_value:.3g}.")
    if fit.scale_factor > 1.0 and fit.form == rfit.FORM_QUADRATURE:
        parts.append(f"χ²/ν > 1, so the standard errors are scaled by S = {fit.scale_factor:.3g} "
                     "(PDG); the unscaled ones are the _stat fields.")
    elif fit.scale_factor > 1.0:
        parts.append(f"χ²/ν > 1, so the standard errors and the band are scaled by "
                     f"S = {fit.scale_factor:.3g} (PDG), and the band takes Student's "
                     f"t₀.₉₇₅,{fit.ndf} = {fit.band_quantile:.4g} for the variance scale S² "
                     f"estimated from ν = {fit.ndf}; the unscaled errors are the _stat fields.")
    if fit.form == rfit.FORM_AFFINE and fit.theta[1] < 0:
        parts.append("b < 0: the points fall faster than a/√E; the line is drawn down to zero.")
    if fit.form == rfit.FORM_QUADRATURE and fit.theta[0] <= 0:
        parts.append("A ≤ 0, so a = √A is undefined; A is reported with its standard error.")
    if fit.form == rfit.FORM_QUADRATURE and fit.theta[1] <= 0:
        parts.append("B ≤ 0, so b = √B is undefined; B is reported with its standard error.")
    if provisional:
        parts.append(f"Provisional: fewer than two windows reach N = {FIT_MIN_N}, so it runs "
                     f"through windows of N ≥ {WHISKER_MIN_N}.")
    return " ".join(parts)


def fit_block(fit: rfit.Fit | None, provisional: bool, band_points: int = BAND_POINTS
              ) -> dict[str, Any] | None:
    """One fit for the wire: parameters in percent (a in %·√GeV, b in %), its curve and note.

    Every form carries its ``band_quantile``. The quadrature fit's ``curve`` is
    ``None`` (the 1/√E view tables it); its params carry ``rho_a2b2``, the
    correlation of A and B, so the E view can rebuild its band from
    ``a2``, ``b2``, their SEs and ``band_quantile`` alone.
    """
    if fit is None:
        return None
    se, se_stat = fit.se, fit.se_stat
    out: dict[str, Any] = {"form": fit.form, "n_points": fit.n_points, "ndf": fit.ndf}
    if fit.form == rfit.FORM_AFFINE:
        out["params"] = {
            "a": 100.0 * fit.theta[0], "se_a": 100.0 * se[0],
            "b": 100.0 * fit.theta[1], "se_b": 100.0 * se[1], "rho_ab": fit.rho,
            "se_a_stat": 100.0 * se_stat[0], "se_b_stat": 100.0 * se_stat[1],
        }
    elif fit.form == rfit.FORM_PINNED:
        out["params"] = {"a0": 100.0 * fit.theta[0], "se_a0": 100.0 * se[0],
                         "se_a0_stat": 100.0 * se_stat[0]}
    else:
        t = rfit.quadrature_terms(fit)

        def pct(v: float | None) -> float | None:
            return None if v is None else 100.0 * v

        out["params"] = {
            "a": pct(t.a), "se_a": pct(t.se_a), "b": pct(t.b), "se_b": pct(t.se_b),
            "b2": 1e4 * t.b2, "se_b2": 1e4 * t.se_b2, "b_defined": t.b_defined,
            # A ≤ 0 leaves a undefined too (a falling σ/E): A is reported as B is.
            "a2": 1e4 * t.a2, "se_a2": 1e4 * t.se_a2, "a_defined": t.a_defined,
            "se_a_stat": pct(t.se_a_stat), "se_b_stat": pct(t.se_b_stat),
            "se_a2_stat": 1e4 * t.se_a2_stat, "se_b2_stat": 1e4 * t.se_b2_stat,
            # The correlation of A and B (S cancels in it): the E view's band needs it.
            "rho_a2b2": fit.rho,
        }
    out.update({
        "chi2": fit.chi2, "p_value": fit.p_value, "scale_factor": fit.scale_factor,
        "iterations": fit.iterations, "converged": fit.converged,
    })
    if fit.form == rfit.FORM_AFFINE:
        out["negative_intercept"] = fit.theta[1] < 0
    out["band_quantile"] = fit.band_quantile
    out["curve"] = None if fit.form == rfit.FORM_QUADRATURE else _curve(fit, band_points)
    out["provisional"] = provisional
    out["note"] = _fit_note(fit, provisional)
    return out


@dataclass
class ResolutionScaling:
    """Every series of one selection, computed once and rendered at a chosen fidelity."""

    record: ExperimentRecord
    axis: performance_bins.BinAxis
    nominal: tuple[int, ...]
    series: list[Series]
    samples: list[response.Sample]
    calibrations: dict[str, response.Calibration]
    model: dict[str, Any]
    coord_system: str
    n_events: int
    undefined_d: int = 0
    shower_note: str | None = None
    run: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.y = response._y_axis(self._extents())
        self.energy_y = energy_y_axis(self.series)

    # ------------------------------------------------------------- y axis --

    def _extents(self) -> list[response.Extent]:
        """Eligible windows (whiskers included), weak drawn ones, and the robust fits' lines."""
        out: list[response.Extent] = []
        for s in self.series:
            for w in s.windows:
                r = w.r
                if r is None or w.off_axis or w.n < REPORT_MIN_N:
                    continue
                lo, hi = 100.0 * r, 100.0 * r
                if w.whisker:
                    lo, hi = 100.0 * min(r, w.ci[0]), 100.0 * max(r, w.ci[1])
                out.append(response.Extent(lo, hi, 100.0 * r, w.eligible))
            for mode in s.modes.values():
                if mode.provisional:
                    continue
                for form in (rfit.FORM_AFFINE, rfit.FORM_PINNED):
                    fit = mode.fits.get(form)
                    if fit is None:
                        continue
                    line = 100.0 * fit.predict(np.linspace(0.0, X_MAX, BAND_POINTS))
                    top = float(line.max())
                    out.append(response.Extent(max(0.0, float(line.min())), top, top, True))
        return out

    # ------------------------------------------------------------- notes --

    @property
    def coord_applies(self) -> bool:
        return self.record.kind == ddl.KIND_TWO_SHOWER and self.model.get("source") == SOURCE_NETWORK

    def meta_notes(self) -> dict[str, Any]:
        note = (f"coord_system = {self.coord_system} selects the energy network's input frame "
                f"({self.model.get('frame')})." if self.coord_applies else
                "coord_system selects the energy network's input frame on two-shower data only; "
                "it does not apply to this experiment.")
        return {"coord_system": self.coord_system, "coord_system_applies": self.coord_applies,
                "coord_system_note": note}

    def warnings(self) -> list[str]:
        out = list(self.axis.notices)
        if self.n_events == 0:
            out.append("No events match the current selection.")
        for s in self.samples:
            if s.n_dropped:
                many = s.n_dropped != 1
                out.append(
                    f"{s.columns.label}: {s.n_dropped:,} event{'s' if many else ''} "
                    f"{'were' if many else 'was'} dropped before the ratios (a deposit or momentum "
                    "that is not finite, a negative deposit, or a momentum that is not positive), "
                    "counted and never zero-filled.")
        for s in self.series:
            if s.source != SOURCE_DETECTOR and s.n_missing and not s.n:
                out.append(f"{s.label}: no event of the selection has a finite prediction and "
                           "truth; every one is counted in n_missing and none is drawn.")
        if self.run is not None and not self.run["split"]["reproduced"]:
            out.append(self.run["split"]["warning"])
        return [typographic(w) for w in out if w]

    def _notes(self) -> list[str]:
        kind = self.record.kind or ""
        notes = [
            response._DEPOSIT_NOTE.get(kind, ""),
            "Each window is the producer's integer momentum bin k, [k, k + 1) GeV, of the "
            "shower's own momentum. Per event R = E_est / p; the plotted value is σ/E = s(R)/R̄ in "
            "percent (s with ddof = 1), its whisker the 95% χ² interval of s divided by R̄ "
            "(N − 1 d.o.f.; R̄'s own uncertainty is neglected, the delta-method se_delta "
            "includes it), and its abscissa x = ⟨1/√p⟩ over the window's events. Dividing by p "
            "event by event removes the window's own momentum spread and the estimator's bias, "
            "and c cancels in s(R)/R̄, so the detector series does not depend on the calibration.",
            "The detector series c·E_dep is a linear-sum benchmark, not a limit: a model that "
            "reads the shower's shape (leakage, compensation) can do better than a plain sum.",
            "E on both axes is the incident momentum p as the producer writes it. For a massive "
            "species √(p² + m²) differs from p by at most m²/2p², 1.7% for a proton at 5 GeV/c.",
            f"σ/E is reported from N = {REPORT_MIN_N}; a window is drawn with its whisker from "
            f"N = {WHISKER_MIN_N}, and enters the fits and sets the y range from N = {FIT_MIN_N} "
            f"and p ≥ {E_MIN_GEV:g} GeV.",
            "Fits: a/√E + b and a₀/√E through the origin, by weighted least squares with weights "
            "1/se², se the delta-method standard error of σ/μ recomputed at the fitted value and "
            "iterated (half steps once the refits oscillate); χ², ν = n − p and its p-value. Where "
            "χ²/ν > 1 the standard errors and the 95% band are scaled by S = √(χ²/ν) (PDG), and the "
            "band then takes Student's t₀.₉₇₅,ν rather than 1.96, since S is estimated from the "
            "fit's own ν. The band is the 95% confidence band of the line, not the spread of the "
            "events. The quadrature form √(a²/E + b²) is fitted as (σ/E)² = A/E + B and tabled, "
            "not drawn; its b and the affine b are different constant terms.",
            f"Anchors: the lowest bin from {ANCHOR_LOW_GEV:g} GeV (below it the sampling fraction "
            "is still rising), the highest bin and the bin between them nearest in log E to the "
            "geometric mean of their centres, chosen on the whole table so they do not move with "
            f"the selection. A series whose anchor window holds N < {FIT_MIN_N} takes its nearest "
            f"window from {ANCHOR_LOW_GEV:g} GeV in log E with N ≥ {FIT_MIN_N} instead; with fewer "
            f"than two such windows its fit runs through windows of N ≥ {WHISKER_MIN_N} and is "
            f"provisional. The other mode fits every window with N ≥ {FIT_MIN_N} from "
            f"{E_MIN_GEV:g} GeV, the {E_MIN_GEV:g}–{ANCHOR_LOW_GEV:g} GeV window included, below "
            "the anchors' floor.",
            "The top axis is an exact relabelling of the bottom one, E = 1/x²: a deterministic "
            "unit conversion, and no data are plotted against it.",
        ]
        for s in self.samples:
            cal = self.calibrations[s.key]
            if cal.c.value is not None:
                notes.append(f"{s.columns.label}: c = Σ p / Σ E_dep = {cal.c.value:.4g} over "
                             f"N = {cal.n:,} events, fitted once over the whole selection.")
        if self.shower_note:
            notes.append(self.shower_note)
        if self.model.get("source") == SOURCE_NETWORK:
            notes.append(
                f"The model series is the energy network of the {FRAME_WORDS[self.model['frame']]} "
                "frame (coord_system), R = predicted energy / its truth; the networks predict the "
                "momentum scale directly, with no calibration.")
        elif self.model.get("source") == SOURCE_XGB:
            split = self.model.get("split") or {}
            notes.append(
                "The model series is the shipped XGBoost momentum regressor on the notebook's 20% "
                f"validation split: {split.get('n_validation', 0):,} of the "
                f"{split.get('n_selected', 0):,} selected events. The detector series uses every "
                "selected event, so the two series do not share their events.")
        elif self.model.get("reason"):
            notes.append(f"No model series: {self.model['reason']}")
        if self.undefined_d:
            notes.append(
                f"{self.undefined_d:,} of the experiment's {self.record.n_events:,} events have no "
                "shower A hits and so no A–B separation; the selection leaves them out unless "
                "include_undefined_d is set.")
        off = self.off_axis()
        if off:
            listed = sum(len(o["bins"]) for o in off)
            events = sum(o["n"] for o in off)
            notes.append(f"Off the axis: {listed} window{'s' if listed != 1 else ''} below "
                         f"{E_MIN_GEV:g} GeV ({events:,} events across the series) have x > "
                         f"{X_MAX:g}; they are listed in off_axis with their σ/E and not drawn.")
        for s in self.series:
            for mode_name, mode in s.modes.items():
                for sub in mode.substitutions:
                    notes.append(f"{s.label} ({mode_name}): {sub['reason']}")
                for fit in mode.fits.values():
                    if fit is not None and fit.scale_factor > 1.0:
                        notes.append(f"{s.label} ({mode_name}, {fit.form}): χ²/ν = "
                                     f"{fit.chi2 / fit.ndf:.3g}, so its errors are scaled by "
                                     f"S = {fit.scale_factor:.3g}.")
                affine = mode.fits.get(rfit.FORM_AFFINE)
                if affine is not None and affine.theta[1] < 0:
                    notes.append(f"{s.label} ({mode_name}): the affine b is negative "
                                 f"({100 * affine.theta[1]:.3g}%): the points fall faster than "
                                 "a/√E, and the line is drawn down to zero.")
        y = self.y
        basis = (f"The y range is provisional: no window from {E_MIN_GEV:g} GeV reaches "
                 f"N = {FIT_MIN_N}." if y["provisional"] else
                 f"The y range follows the windows with N ≥ {FIT_MIN_N} (whiskers included) and "
                 "the fits through them, from zero.")
        clipped = y["n_clipped"]
        notes.append(f"{basis} {clipped} mark{'s' if clipped != 1 else ''} beyond it "
                     f"{'are' if clipped != 1 else 'is'} clipped, not rescaled.")
        return [typographic(n) for n in notes if n]

    def off_axis(self) -> list[dict[str, Any]]:
        out = []
        for s in self.series:
            gone = [w for w in s.windows if w.off_axis]
            if gone:
                out.append({"series": s.key, "bins": [w.bin for w in gone],
                            "n": sum(w.n for w in gone)})
        return out

    # ------------------------------------------------------------- wire --

    def _axis(self) -> dict[str, Any]:
        ticks = [{"e_gev": e, "x": 1.0 / math.sqrt(e), "label": str(e)}
                 for e in ENERGY_TICKS_GEV if 1.0 / math.sqrt(e) <= X_MAX]
        ticks.append({"e_gev": None, "x": 0.0, "label": "∞"})
        return {
            "x": {"min": 0.0, "max": X_MAX, "inverse": True, "interval": 0.1,
                  "unit": "GeV^−1/2", "name": "⟵ 1/√E [GeV⁻¹ᐟ²]"},
            "top": {"name": "Energy (GeV) ⟶", "ticks": ticks,
                    "rule": "E = 1/x², an exact relabelling of the bottom axis; no data are "
                            "plotted against it."},
            "y": {**self.y, "unit": UNIT, "name": "σ/E [%]"},
            "energy": self._energy_axis(),
        }

    def _energy_axis(self) -> dict[str, Any]:
        """The E view's axes: E in GeV from zero, its own σ/E range, and the sentences that say why."""
        data_max = float(self.axis.p_hi[-1]) if self.axis.p_hi else None
        x_max = E_VIEW_MAX_GEV
        if data_max is not None:
            x_max = max(E_VIEW_MAX_GEV,
                        math.ceil(data_max / E_VIEW_INTERVAL_GEV) * E_VIEW_INTERVAL_GEV)
        y = self.energy_y
        floor = f"{E_VIEW_Y_MIN_GEV:g} GeV"
        basis = (f"The E view's y range is provisional: no window from {floor} reaches "
                 f"N = {FIT_MIN_N}." if y["provisional"] else
                 f"The E view's y range follows the windows with N ≥ {FIT_MIN_N} from {floor} "
                 "(whiskers included) and the a/√E ⊕ b and a₀/√E fits over the windows each was "
                 f"fitted to, from zero; a window below {floor} never sets it.")
        clipped = y["n_clipped"]
        notes = [
            f"{basis} {clipped} mark{'s' if clipped != 1 else ''} beyond it "
            f"{'are' if clipped != 1 else 'is'} clipped, not rescaled.",
            f"Fitted curves are drawn from {E_MIN_GEV:g} GeV, the lowest window edge any fit can "
            f"use, to {x_max:g} GeV: solid over the windows each fit ran through, dashed beyond, "
            "where the curve extrapolates its form.",
            "Each window is drawn at E = 1/x² with x = ⟨1/√p⟩, the abscissa the fits used, so a "
            "window on its fitted line in the 1/√E view sits on its fitted curve here; its ⟨p⟩, "
            "slightly larger (Jensen's inequality), is in its tooltip.",
        ]
        return {
            "x": {"min": 0.0, "max": float(x_max), "interval": E_VIEW_INTERVAL_GEV,
                  "unit": "GeV", "name": "Energy E [GeV]"},
            "y": {**y, "unit": UNIT, "name": "σ/E [%]"},
            "curve_min_gev": E_MIN_GEV,
            "y_min_gev": E_VIEW_Y_MIN_GEV,
            "data_max_gev": data_max,
            "rule": typographic(
                "E = 1/x² of the 1/√E view's x = ⟨1/√p⟩: one exact bijection, so both views draw "
                "the same measurements."),
            "notes": [typographic(n) for n in notes],
        }

    def _anchors(self) -> dict[str, Any]:
        index = {k: i for i, k in enumerate(self.axis.numbers)}
        return {
            "nominal_bins": list(self.nominal),
            "labels": [self.axis.labels[index[k]] for k in self.nominal],
            "rule": (f"Chosen on the whole table's bins, not the selection: the lowest bin from "
                     f"{ANCHOR_LOW_GEV:g} GeV, the highest bin, and the bin between them nearest "
                     "in log E to the geometric mean of their centres. A series whose anchor "
                     f"holds N < {FIT_MIN_N} takes its nearest window from {ANCHOR_LOW_GEV:g} GeV "
                     f"in log E with N ≥ {FIT_MIN_N}, named in substitutions; with fewer than two, "
                     f"windows of N ≥ {WHISKER_MIN_N} and the fit is provisional."),
        }

    def _series_dict(self, s: Series, band_points: int) -> dict[str, Any]:
        return {
            "key": s.key, "source": s.source, "shower": s.shower,
            "shower_label": s.shower_label, "estimator_label": s.estimator_label,
            "label": s.label, "colour_slot": s.colour_slot,
            "n": s.n, "n_dropped": s.n_dropped, "n_absent": s.n_absent, "n_missing": s.n_missing,
            "windows": [w.as_dict() for w in s.windows],
            "fits": {
                name: {
                    "points": list(mode.points),
                    "substitutions": list(mode.substitutions),
                    "fallback": mode.fallback, "provisional": mode.provisional,
                    **{form: fit_block(mode.fits.get(form), mode.provisional, band_points)
                       for form in (rfit.FORM_AFFINE, rfit.FORM_PINNED, rfit.FORM_QUADRATURE)},
                    "span_gev": fitted_span(mode.points, s.windows),
                }
                for name, mode in s.modes.items()
            },
        }

    def as_dict(self, digits: int = SIGNIFICANT, band_points: int = BAND_POINTS) -> dict[str, Any]:
        """The payload body (no ``meta`` or ``filter``), rounded for the wire."""
        tree = {
            "kind": self.record.kind,
            "n_events": self.n_events,
            "unit": UNIT,
            "estimator": {
                "name": response.KIND_RATIO,
                "definition": ("R = E_est / p per event; σ/E = s(R)/R̄ per momentum window, in "
                               "percent, with s the unbiased (ddof = 1) sample SD."),
                "label": "σ(R)/μ(R), R = E_est / p",
            },
            "axis": self._axis(),
            "gates": {"report_n": REPORT_MIN_N, "whisker_n": WHISKER_MIN_N, "fit_n": FIT_MIN_N,
                      "e_min_gev": E_MIN_GEV, "anchor_low_gev": ANCHOR_LOW_GEV,
                      "n_anchors": N_ANCHORS},
            "anchors": self._anchors(),
            "model": self.model,
            "series": [self._series_dict(s, band_points) for s in self.series],
            "off_axis": self.off_axis(),
            "notes": self._notes(),
        }
        return response._rounded(tree, digits)


# ---------------------------------------------------------------- compute --


def _model_series(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                  caps: capabilities.Capabilities, coord_system: str,
                  shower_labels: dict[str, str], axis: performance_bins.BinAxis,
                  nominal: Sequence[int]
                  ) -> tuple[dict[str, Any], dict[str, Series], dict[str, Any] | None]:
    """The model block, the model series per shower and, on an aggregate, the XGBoost run."""
    kind = record.kind
    if kind == ddl.KIND_TWO_SHOWER:
        if not caps.models:
            reason = caps.reasons.get("perf-bins", "This experiment carries no networks.")
            return ({"available": False, "source": None, "frame": None, "label": None,
                     "reason": reason, "split": None}, {}, None)
        frame = ddl.NETWORK_FRAME[coord_system]
        label = f"Energy network · {FRAME_WORDS[frame]} frame"
        cols = performance_bins.read_selection(con, record, spec, "energy", [coord_system])
        out = {}
        for key in shower_labels:
            bins, true = cols[f"bin_{key}"], cols[f"true_{key}"]
            pred = cols[f"pred_{key}_{coord_system}"]
            usable, missing, dropped = _pairs(pred, true, bins)
            out[key] = build_series(
                SOURCE_NETWORK, key, shower_labels[key], label, frame,
                pred[usable] / true[usable], true[usable], bins[usable], axis, nominal,
                n_missing=missing, n_dropped=dropped)
        return ({"available": True, "source": SOURCE_NETWORK, "frame": frame, "label": label,
                 "reason": None, "split": None}, out, None)

    if kind == ddl.KIND_SINGLE_EVENTS:
        if not caps.can("xgboost"):
            reason = caps.reasons.get("xgboost", "No XGBoost analysis serves this experiment.")
            return ({"available": False, "source": None, "frame": None, "label": None,
                     "reason": reason, "split": None}, {}, None)
        from ..modelruns import store as xgb_store
        from ..modelruns import views as xgb_views

        runs = xgb_store.read_runs(con, record.table_name)
        if runs is None or "momentum" not in runs:
            reason = ("The stored XGBoost analysis is missing; Admin Settings › Model runs "
                      "re-analyses it.")
            return ({"available": False, "source": None, "frame": None, "label": None,
                     "reason": reason, "split": None}, {}, None)
        where = spec.where_sql("e")
        rows = xgb_store.read_holdout(con, record, "momentum", where, spec.params())
        n_selected = xgb_store.count_selected(con, record, where, spec.params())
        bins, true, pred = rows["bin"], rows["true_momentum"], rows["pred_momentum"]
        usable, missing, dropped = _pairs(pred, true, bins)
        key = next(iter(shower_labels))
        series = build_series(
            SOURCE_XGB, key, shower_labels[key], XGB_LABEL, SOURCE_XGB,
            pred[usable] / true[usable], true[usable], bins[usable], axis, nominal,
            n_missing=missing, n_dropped=dropped)
        run = xgb_views.run_block(runs, "momentum")
        split = {"n_selected": n_selected, "n_validation": int(bins.size),
                 "n_training_excluded": n_selected - int(bins.size),
                 "fraction": xgb_views.TEST_SIZE, "reproduced": run["split"]["reproduced"]}
        return ({"available": True, "source": SOURCE_XGB, "frame": None, "label": XGB_LABEL,
                 "reason": None, "split": split}, {key: series}, run)

    return ({"available": False, "source": None, "frame": None, "label": None,
             "reason": _NO_MODEL_SINGLE_HITS, "split": None}, {}, None)


def _shower_labels(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
                   caps: capabilities.Capabilities,
                   columns: Sequence[showers_mod.ShowerColumns]) -> tuple[dict[str, str], str | None]:
    """Each shower's name on the card, and the sentence that says how a species was chosen."""
    if record.kind == ddl.KIND_TWO_SHOWER:
        return {c.key: c.label for c in columns}, None
    key = columns[0].key
    if record.kind == ddl.KIND_SINGLE_EVENTS:
        word = next((run.get("species") for run in caps.model_runs if run.get("species")), None)
        if word:
            label = species_label(word=word)
            return {key: label}, (f"The shower is named {label}: the species of the paired "
                                  f"XGBoost models ({word}).")
        return {key: columns[0].label}, None
    label, note = _dominant_species(con, record, spec)
    return {key: label or columns[0].label}, note


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            coord_system: str = "lab") -> ResolutionScaling:
    """Every series of the selection: the detector's per shower and the model's where it exists."""
    if coord_system not in ddl.COORD_SYSTEMS:
        raise ValidationError(
            f"coord_system must be one of {', '.join(ddl.COORD_SYSTEMS)}; got {coord_system!r}.",
            field="coord_system")
    caps = capabilities.of(record)
    axis = performance_bins.dataset_axis(con, record)
    nominal = nominal_anchors(axis)
    columns = showers_mod.of(record, "both")
    samples = response.fetch(con, record, spec, columns)
    calibrations = {s.key: response.calibrate(s) for s in samples}
    labels, shower_note = _shower_labels(con, record, spec, caps, columns)
    model, model_series, run = _model_series(con, record, spec, caps, coord_system, labels,
                                             axis, nominal)
    series: list[Series] = []
    for sample in samples:
        # A selection that deposited nothing has no c; its R are all zero either way, and
        # σ/μ, the only plotted number, does not depend on c.
        c = calibrations[sample.key].c.value
        ratio = (1.0 if c is None else c) * sample.dep / sample.p
        series.append(build_series(
            SOURCE_DETECTOR, sample.key, labels[sample.key], DETECTOR_LABEL, SOURCE_DETECTOR,
            ratio, sample.p, sample.bin, axis, nominal,
            n_dropped=sample.n_dropped, n_absent=sample.n_absent))
        if sample.key in model_series:
            series.append(model_series[sample.key])
    left_out = (record.n_events_no_d
                if record.kind == ddl.KIND_TWO_SHOWER and not spec.include_undefined_d else 0)
    return ResolutionScaling(
        record=record, axis=axis, nominal=nominal, series=series, samples=samples,
        calibrations=calibrations, model=model, coord_system=coord_system,
        n_events=max((s.n_selected for s in samples), default=0),
        undefined_d=left_out or 0, shower_note=shower_note, run=run,
    )
