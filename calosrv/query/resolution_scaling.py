"""The energy resolution against 1/√E: the ``res-scaling`` card of Page 2.

A calorimeter's resolution is quoted as ``σ/E = a/√E ⊕ b``: a stochastic term
that falls as 1/√E and a constant term that does not. Plotted against
``x = 1/√E`` the stochastic term is a straight line through the origin, which
sits at the right-hand border of a reversed axis (E → ∞). This module measures
one error scale per momentum window for every series the experiment carries and
fits that line to it; ``stats/resolution_fit.py`` holds the fits.

**One ratio for every series: the per-event response ratio.** In window k
(the producer's integer momentum bin, [k, k + 1) GeV, of the shower's own
momentum) each usable event gives ``R = E_est / p``: ``c·E_dep`` for the
detector, with ``c`` the shower's selection-wide calibration; the energy
network's prediction over its truth; the XGBoost momentum regressor's
prediction over the true momentum. Its abscissa is ``x = ⟨1/√p⟩`` over the
window's events. Dividing by p event by event removes the window's own momentum
spread (5.2% at 5 GeV, 1.5% at 19 GeV for a 1 GeV window).

**Three estimators of one window's error scale** (``ESTIMATORS``, one per
response, ``?estimator=``; Martin's decisions, 2026-11-12). On
``pion_hits_with_model_outputs`` (shower A, absolute-frame network, 10–11 GeV,
N = 1,022) this card plotted ``s(R)/R̄`` = 17.15% while Model Error vs.
Incident Momentum (``query/performance_bins.py``) showed a Median rel. of
8.52% for the same events, and the π± curve reads 8.45% there. 17.15 = 8.52 ×
1.4826 × 0.953 × 1.426: ×1.4826 is a definition (``median |R − 1| =
0.6745·σ/E`` for unbiased Gaussian errors, so a median relative error is not a
σ), ×0.953 is bias and centring, and ×1.43 is non-Gaussian tails (4.3% of the
events beyond 3 robust σ against 0.27% for a Gaussian). So the card offers, in
this order:

* ``median``, the default, **Median |rel. err.|**: ``median |R − 1|``, computed
  exactly as Model Error vs. Incident Momentum computes its Median rel.
  (``np.abs(pred − true) / true`` for a model series), with that card's seed
  ``[42, frame, shower, bin, 2]`` and interval (the percentile bootstrap from
  N = 20, the order-statistic interval for 6 ≤ N < 20), so a network or XGBoost
  window equals it bit for bit. Gates: reported from N = 2, whisker from N = 8,
  fits and range from N = 20, the provisional N ≥ 8 fallback kept. The deposit
  takes the median calibration ``c̃ = 1 / median(E_dep/p)`` (below) and the
  frame index :data:`DEPOSIT_FRAME_INDEX`. It is quoted beside σ/E, never
  converted into it.
* ``robust``, **Robust σ (IQR)**: ``IQR(R) / (1.349 · median R)``, type-7
  quartiles, from N = 20 for value, whisker, fit and range alike (the CLAUDE.md
  robust floor), with the exact order-statistic bootstrap of
  ``stats/robust_width.py`` (seed ``[42, frame, shower, bin, 8]``). It is
  invariant under ``R → cR``, and a few badly reconstructed events cannot
  inflate it: 12.03% [11.02, 13.33] in the window above.
* ``sample``, **Sample σ/μ**: today's ``s(R)/R̄`` (ddof = 1), its whisker the
  χ²_{N−1} interval of ``s`` divided by ``R̄`` (Page 1's resolution whisker),
  its fit weight the delta-method standard error, gates 2 / 8 / 20. Its numbers
  did not move by a bit when the other two arrived, and it is Page 1's
  response-ratio series (``response.KIND_RATIO``), so the two cards agree under
  it.

The median and robust fits weight each window by its measured relative
bootstrap SE ``κ = SE / value`` (``stats/resolution_fit.py``, the ``kappa``
argument): the Gaussian asymptotic law understates the measured SE by a median
1.17× (pion file, 2026-11-12). Every window also carries the two estimators not
plotted (``alt``), its median response ``R̃ − 1`` and its share of events
beyond 3 robust σ, and every model series the range of its median response over
each mode's fitted windows: a regressor trained on a bounded range (0–20 GeV)
pulls its predictions toward mid-range (median response +8.2% at 5–6 GeV, −5.4%
at 19–20 GeV on the pion file), which narrows a σ near the ends of that range
and adds a bias to the median rel. there. Martin's decision: disclosed only;
the anchors and fit rules do not change.

**The deposit's calibration under the median estimator.** ``s(R)/R̄`` and the
IQR ratio do not depend on ``c``, but ``median |c·E_dep/p − 1|`` does. With the
ratio of sums ``c = Σp / ΣE_dep`` (``response.calibrate``) the deposit's
per-window median response is +3% to +14% from 5 GeV, because the low-side
leakage tail pulls the mean below the median: pion deposit A at 10–11 GeV reads
18.32% with it and 13.92% with ``c̃ = 1 / median(E_dep/p)`` over the shower's
events with ``E_dep > 0`` (median response +9.0% against +1.7%). So the median
estimator takes ``c̃``, one constant per shower over the selection, the median
analogue of the ratio of sums, and both constants are reported. Without an
event that deposits energy there is no ``c̃``, and the deposit plots nothing
under the median estimator, with a warning.

**The literature curves stay on under every estimator** (Martin's override,
2026-11-12): the reference ECCE figure plots the models' MAE/E directly against
them. Under the median estimator the payload carries
:data:`LITERATURE_WARNING`, which the card shows wherever a curve or a ratio to
one is on.

**The detector series is a benchmark, not a limit.** ``c·E_dep`` is a plain
linear sum; a model that reads the shower's shape (leakage, compensation) can
beat it, so it is labelled "Calibrated deposit c·E_dep — linear-sum benchmark".

**Gates** (CLAUDE.md, the low-N table; per estimator in :data:`ESTIMATOR_GATES`):
under the median and sample estimators a window's value is reported from
N = 2, it is drawn with its whisker from N = 8, and it enters the fits and sets
the y range from N = 20 *and* p ≥ 4 GeV; the robust width waits for N = 20 at
every step. Below 4 GeV, x > 0.5 and the window lies off the axis; it is
counted and listed, never drawn.

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
windows of N ≥ 20 from :data:`E_VIEW_Y_MIN_GEV`, whiskers included. A window
below 2 GeV never sets it, provisional or not: measured on eight stored
experiments (2026-11-10), the windows of N ≥ 20 top out at 23–101% from 1 GeV
and at 20–66% from 2 GeV, so a 1–2 GeV window would spend the axis on itself.
It is counted in ``n_clipped`` when it leaves the top.

**The windows alone set either view's σ/E range** (``linear_y_axis``,
``energy_y_axis``; Martin's decision, 2026-11-11). A fit summarises its
windows; it is not more evidence (CLAUDE.md §2, display ranges follow robust
evidence). So no fitted line, curve or band enters either range, provisional
or not: one that leaves the top is clipped there by the panel with a caret, its
true values in the caret's tooltip and a count in the drawer. Measured on the
five stored experiments (2026-11-11: the production file, the electron and pion
two-shower files and aggregates), the deposit's origin-pinned line at 4 GeV
(58–72%) had set the 1/√E view's top at 70–80% on the three hadron ones, where
their windows peak at 37–44%, whiskers included.

**A fit that does not describe its windows** (``misfit``: ν ≥ 1 and
S = √(χ²/ν) > ``stats/resolution_fit.MISFIT_SCALE``, its residuals averaging
more than five of the windows' own standard errors) is served and drawn like
any other, faded as a provisional fit is, and its note says why. The size of
the misfit decides, not the χ² p-value, which rejects nearly every fit at
hundreds of events a window (``stats/resolution_fit.py`` has the measurement).

**Anchors that do not move with the selection.** The default fit runs through
three nominal windows chosen on the whole table's bin axis
(``performance_bins.dataset_axis``): the lowest bin from 5 GeV (below it the
sampling fraction is still rising, which a/√E + b does not describe), the
highest bin, and the bin between them nearest in log E to the geometric mean of
their centres. On the 0–20 GeV files that is {5, 10, 19}. A series whose
anchor window is thin takes its nearest eligible window from 5 GeV instead, by
name, never one below the floor the low anchor keeps; with too few eligible
windows the fit falls back to windows of N ≥ 8 and is labelled provisional
(never under the robust width, whose every gate is N = 20: it has no weaker
window to fall back on). The "all windows" mode fits every eligible window from 4 GeV, the 4–5 GeV
window included, as asked of it, and its notes say so. Both modes are computed
here; the card's toggle only repaints.

**Reads.** The event table (one row per event: deposits, momenta, bins, the
networks' predictions) and, on an aggregate, the XGBoost prediction table. No
hit is scanned, so a selection of the whole production file costs
milliseconds.
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
from ..encode.numbers import SIGNIFICANT
from ..errors import ValidationError
from ..stats import gaussian
from ..stats import median as median_mod
from ..stats import metrics
from ..stats import resolution_fit as rfit
from ..stats import robust_width as rw
from ..text import fmt_signed, typographic
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

# ------------------------------------------------------------ estimators --
# Martin's decisions of 2026-11-12: the card's Estimator control, in this order, the median
# relative error by default. One estimator per response: two would break the 100 KB contract.

ESTIMATORS: tuple[str, ...] = ("median", "robust", "sample")
DEFAULT_ESTIMATOR = "median"
MEDIAN, ROBUST, SAMPLE = ESTIMATORS

#: Each estimator's gates (the payload's top-level ``gates`` carry the active one's). The median
#: and sample estimators keep the low-N ladder above; the robust width waits for the robust floor
#: at every step, so it has no provisional fallback (that picks N ≥ whisker_n, the same windows).
ESTIMATOR_GATES: dict[str, dict[str, int]] = {
    MEDIAN: {"report_n": REPORT_MIN_N, "whisker_n": WHISKER_MIN_N, "fit_n": FIT_MIN_N},
    ROBUST: {"report_n": rw.MIN_ROBUST_N, "whisker_n": rw.MIN_ROBUST_N, "fit_n": rw.MIN_ROBUST_N},
    SAMPLE: {"report_n": REPORT_MIN_N, "whisker_n": WHISKER_MIN_N, "fit_n": FIT_MIN_N},
}

#: The deposit's frame position in the bootstrap seed ``[42, frame, shower, bin, quantity]``:
#: after the three network frames (0–2) and the XGBoost series (3,
#: ``performance_bins.XGB_FRAME_INDEX``).
DEPOSIT_FRAME_INDEX = performance_bins.XGB_FRAME_INDEX + 1
#: The last seed element of each bootstrapped estimator: the median rel.'s position in
#: ``performance_bins.QUANTITIES`` (so a model window draws Model Error vs. Incident Momentum's
#: own replicates), and the robust width's (``stats/robust_width.SEED_QUANTITY_INDEX``).
MEDIAN_QUANTITY_INDEX = performance_bins.QUANTITY_INDEX["median_rel"]
ROBUST_QUANTITY_INDEX = rw.SEED_QUANTITY_INDEX

ESTIMATOR_LABELS: dict[str, str] = {
    MEDIAN: "Median |rel. err.|", ROBUST: "Robust σ (IQR)", SAMPLE: "Sample σ/μ",
}
ESTIMATOR_QUANTITIES: dict[str, str] = {
    MEDIAN: "median_error", ROBUST: "resolution", SAMPLE: "resolution",
}
ESTIMATOR_SYMBOLS: dict[str, str] = {MEDIAN: "median rel.", ROBUST: "σ/E", SAMPLE: "σ/E"}
AXIS_NAMES: dict[str, str] = {
    MEDIAN: "Median |E_est − p| / p [%]", ROBUST: "Robust σ/E [%]", SAMPLE: "σ/E [%]",
}
ESTIMATOR_DEFINITIONS: dict[str, str] = {
    MEDIAN: ("R = E_est / p per event; the median relative error median |R − 1| per momentum "
             "window, in percent, computed for a model series as median |E_est − p| / p: the "
             "Median rel. of Model Error vs. Incident Momentum, with its events, seed and "
             "interval."),
    ROBUST: ("R = E_est / p per event; σ/E = IQR(R) / (1.349 · median R) per momentum window, in "
             "percent, with type-7 quartiles: a σ-consistent width for Gaussian errors that a "
             "few badly reconstructed events cannot inflate."),
    SAMPLE: ("R = E_est / p per event; σ/E = s(R)/R̄ per momentum window, in percent, with s the "
             "unbiased (ddof = 1) sample SD."),
}
#: ``kappa``: the window's bootstrap relative SE at the fitted value; ``delta``: the delta method.
WEIGHT_METHODS: dict[str, str] = {MEDIAN: "kappa", ROBUST: "kappa", SAMPLE: "delta"}

#: The disclosure every median-against-curve comparison carries (Martin's override, 2026-11-12).
LITERATURE_WARNING = (
    "Note: comparing Median |rel. err.| against a σ/E literature curve (for unbiased Gaussian "
    "errors, median|R − 1| = 0.6745·σ/E; use Robust σ (IQR) for a σ-scaled comparison)."
)
#: How the median relative error and σ/E relate, quoted wherever both appear.
RELATION = (
    "For unbiased Gaussian errors median|R − 1| = 0.6745·σ/E, so a median relative error is "
    "quoted beside σ/E, never converted into it."
)

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


_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _power_of_ten(value: float) -> str:
    """A power of ten as text, ``1e-06`` as "10⁻⁶"; any other value in ``:g`` form."""
    exponent = round(math.log10(value)) if value > 0 else None
    if exponent is None or not math.isclose(value, 10.0 ** exponent, rel_tol=1e-12):
        return f"{value:g}"
    return "10" + str(exponent).translate(_SUPERSCRIPT)


def check_estimator(estimator: str) -> str:
    """The estimator, or a 422 naming the field ``estimator``."""
    if estimator not in ESTIMATORS:
        raise ValidationError(
            f"estimator must be one of {', '.join(ESTIMATORS)}; got {estimator!r}.",
            field="estimator")
    return estimator


@dataclass
class Window:
    """One momentum window of one series: each estimator's value and where it may be drawn.

    ``fit`` holds the moments of R (the sample estimator); ``median_rel`` the
    median relative error with Model Error vs. Incident Momentum's interval,
    computed under the median estimator, and ``median_abs`` its value under the
    others (the cross-reference); ``robust`` the robust width, bootstrapped
    under the robust estimator only. ``estimator`` picks the plotted one, whose
    value, interval, SE and gates the properties below give. The sample
    estimator needs nothing beyond ``fit``.
    """

    bin: int
    label: str
    p_lo: float
    p_hi: float
    fit: gaussian.GaussianFit
    p_mean: float
    x: float
    momentum_spread: float | None
    estimator: str = SAMPLE
    median_rel: median_mod.MedianEstimate | None = None
    median_abs: float | None = None
    median_se: float | None = None
    robust: rw.RobustWidth | None = None
    median_r: float | None = None
    tail: float | None = None

    @property
    def n(self) -> int:
        return self.fit.n

    @property
    def centre(self) -> float:
        return 0.5 * (self.p_lo + self.p_hi)

    @property
    def gates(self) -> dict[str, int]:
        return ESTIMATOR_GATES[self.estimator]

    # -- each estimator's own value, gated, as a fraction --

    @property
    def sample_value(self) -> float | None:
        """σ/μ, where μ > 0 makes it a resolution."""
        f = self.fit
        if f.resolution is None or f.mu is None or not f.mu > 0:
            return None
        return f.resolution

    @property
    def median_value(self) -> float | None:
        """median |R − 1| from N = 2; under the median estimator, Model Error vs. Incident Momentum's."""
        if self.n < ESTIMATOR_GATES[MEDIAN]["report_n"]:
            return None
        if self.median_rel is not None:
            return self.median_rel.value
        return self.median_abs

    @property
    def robust_value(self) -> float | None:
        """IQR(R) / (1.349 · median R) from N = 20 (``robust_width`` gates it)."""
        return None if self.robust is None else self.robust.value

    def value_of(self, estimator: str) -> float | None:
        return {MEDIAN: self.median_value, ROBUST: self.robust_value,
                SAMPLE: self.sample_value}[estimator]

    # -- the plotted estimator --

    @property
    def r(self) -> float | None:
        """The plotted value as a fraction: σ/μ, the median rel. or the robust σ/E."""
        return self.value_of(self.estimator)

    def _interval(self) -> metrics.Interval | None:
        if self.estimator == MEDIAN:
            return None if self.median_rel is None else self.median_rel.interval
        if self.estimator == ROBUST:
            return None if self.robust is None else self.robust.interval
        return None

    @property
    def ci(self) -> tuple[float, float] | None:
        if self.r is None:
            return None
        if self.estimator == SAMPLE:
            f = self.fit
            if f.sigma_ci95 is None:
                return None
            return f.sigma_ci95[0] / f.mu, f.sigma_ci95[1] / f.mu
        interval = self._interval()
        return None if interval is None else (interval.lo, interval.hi)

    @property
    def method(self) -> str | None:
        """The interval's method (``metrics.METHOD_*``), or ``None`` without one."""
        if self.ci is None:
            return None
        if self.estimator == SAMPLE:
            return metrics.METHOD_CHI2_RATIO
        return self._interval().method

    @property
    def se(self) -> float | None:
        """The fit weight's standard error at the measured value: delta method, or bootstrap SD."""
        if self.r is None:
            return None
        if self.estimator == SAMPLE:
            return self.fit.resolution_error
        if self.estimator == MEDIAN:
            return self.median_se
        return self.robust.se

    @property
    def kappa(self) -> float | None:
        """κ = SE / value, the relative SE the median and robust fits weight by; ``None`` under sample."""
        if self.estimator == SAMPLE:
            return None
        return rw.relative_se(self.se, self.r)

    @property
    def tied(self) -> bool:
        """A median or robust value whose bootstrap SE is below ``KAPPA_FLOOR`` of it: no fit weight.

        Tied replicates (``stats/robust_width.KAPPA_FLOOR``): the window is
        drawn with its interval and left out of the fits, and the notes count it.
        """
        if self.estimator == SAMPLE or self.r is None or self.se is None or not self.r > 0:
            return False
        return self.se / self.r < rw.KAPPA_FLOOR

    @property
    def off_axis(self) -> bool:
        return self.p_lo < E_MIN_GEV

    @property
    def usable(self) -> bool:
        """A point a fit can weight: a value with a positive standard error (and κ, where it weights)."""
        if self.estimator != SAMPLE:
            return self.kappa is not None
        return self.r is not None and self.se is not None and self.se > 0

    def fittable(self, threshold: int) -> bool:
        return self.n >= threshold and not self.off_axis and self.usable

    @property
    def eligible(self) -> bool:
        return self.fittable(self.gates["fit_n"])

    @property
    def whisker(self) -> bool:
        return self.n >= self.gates["whisker_n"] and self.ci is not None

    @property
    def dof_note(self) -> str | None:
        """The window's low-N sentence: the sample's degrees of freedom, or the robust floor."""
        if self.estimator == SAMPLE:
            return response._dof_note(self.n)
        if self.estimator == ROBUST and self.robust_value is None and self.robust is not None:
            return self.robust.note or None
        return response._dof_note(self.n) if self.n == 1 else None

    def as_dict(self) -> dict[str, Any]:
        f, r, ci, n = self.fit, self.r, self.ci, self.n
        sample = self.estimator == SAMPLE
        se = self.se

        def pct(v: float | None) -> float | None:
            return None if v is None else 100.0 * v

        return {
            "bin": self.bin, "label": self.label, "p_lo": self.p_lo, "p_hi": self.p_hi,
            "n": n, "p_mean": self.p_mean, "x": self.x,
            "mean_r": f.mu, "sd_r": f.sigma,
            "value": pct(r),
            "ci95": None if ci is None else [100.0 * ci[0], 100.0 * ci[1]],
            "method": self.method,
            "se": pct(se),
            "se_rel": None if sample else self.kappa,
            "se_delta": pct(se) if sample else None,
            "c4": (f.sigma_bias_factor
                   if sample and REPORT_MIN_N <= n < gaussian.MIN_CORE_SAMPLES else None),
            "bias": None if f.mu is None else 100.0 * (f.mu - 1.0),
            "median_response": None if self.median_r is None else 100.0 * (self.median_r - 1.0),
            "tail_share": pct(self.tail),
            "alt": {name: pct(self.value_of(name)) for name in ESTIMATORS
                    if name != self.estimator},
            "momentum_spread": self.momentum_spread,
            "dof_note": self.dof_note,
            "weak": n < self.gates["fit_n"],
            "whisker": self.whisker,
            "eligible": self.eligible,
            "off_axis": self.off_axis,
        }


def windows_of(ratio: np.ndarray, p: np.ndarray, bins: np.ndarray,
               axis: performance_bins.BinAxis, *, estimator: str = DEFAULT_ESTIMATOR,
               relative: np.ndarray | None = None,
               seed: Sequence[int] = (median_mod.BOOTSTRAP_SEED,)) -> list[Window]:
    """Every populated window of one series, in the axis's order.

    ``relative`` is the per-event relative error the median estimator takes the
    median of, aligned with ``ratio``: :func:`compute` passes Model Error vs.
    Incident Momentum's own arithmetic (``|pred − true| / true``, or
    ``|c̃·E_dep − p| / p`` for the deposit, NaN where no ``c̃`` exists); bare
    arrays fall back to ``|R − 1|``. ``seed`` is the series' prefix
    ``(42, frame, shower)``: each window appends its bin and the quantity index
    of its estimator (``MEDIAN_QUANTITY_INDEX``, ``ROBUST_QUANTITY_INDEX``), so
    no window's interval depends on which others one request computed.
    """
    check_estimator(estimator)
    ratio = np.asarray(ratio, dtype=np.float64)
    if relative is None:
        relative = np.abs(ratio - 1.0)
    out = []
    for i, k in enumerate(axis.numbers):
        mask = bins == k
        if not mask.any():
            continue
        pk, rk, rel = p[mask], ratio[mask], relative[mask]
        n = int(pk.size)
        p_mean = float(pk.mean())
        spread = (100.0 * float(pk.std(ddof=gaussian.DDOF)) / p_mean
                  if n >= 2 and p_mean > 0 else None)
        prefix = [*seed, int(k)]
        median_seed = [*prefix, MEDIAN_QUANTITY_INDEX]
        finite_rel = rel[np.isfinite(rel)]
        median_rel = median_se = None
        if estimator == MEDIAN:
            median_rel = median_mod.median_estimate(rel, seed=median_seed)
            median_se = rw.median_se(rel, seed=median_seed)
        out.append(Window(
            bin=int(k), label=axis.labels[i], p_lo=float(axis.p_lo[i]), p_hi=float(axis.p_hi[i]),
            fit=gaussian.fit_gaussian(rk), p_mean=p_mean,
            x=float(np.mean(1.0 / np.sqrt(pk))), momentum_spread=spread,
            estimator=estimator, median_rel=median_rel,
            median_abs=float(np.median(np.sort(finite_rel))) if finite_rel.size else None,
            median_se=median_se,
            robust=rw.robust_width(rk, seed=[*prefix, ROBUST_QUANTITY_INDEX],
                                   bootstrap=estimator == ROBUST),
            median_r=float(np.median(rk)) if n >= gaussian.MIN_MOMENT_SAMPLES else None,
            tail=rw.tail_share(rk),
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
    """The three forms through ``points``: the delta-method law under the sample estimator, κ else."""
    x = [w.x for w in points]
    r = [w.r for w in points]
    n = [w.n for w in points]
    if points and points[0].estimator != SAMPLE:
        kappa = [w.kappa for w in points]
        return {
            rfit.FORM_AFFINE: rfit.fit_affine(x, r, n, kappa),
            rfit.FORM_PINNED: rfit.fit_pinned(x, r, n, kappa),
            rfit.FORM_QUADRATURE: rfit.fit_quadrature(x, r, n, kappa),
        }
    return {
        rfit.FORM_AFFINE: rfit.fit_affine(x, r, n),
        rfit.FORM_PINNED: rfit.fit_pinned(x, r, n),
        rfit.FORM_QUADRATURE: rfit.fit_quadrature(x, r, n),
    }


def mode_fits(mode: str, nominal: Sequence[int], windows: Sequence[Window],
              axis: performance_bins.BinAxis | None = None) -> ModeFits:
    """The points of one mode and its fits, with the whisker-gate fallback when fewer than two remain.

    The gates are the windows' estimator's: N ≥ 20 and the N ≥ 8 fallback under
    the median and sample estimators; under the robust width both are N = 20,
    so it never falls back.
    """
    by_bin = {w.bin: w for w in windows}
    gates = windows[0].gates if windows else ESTIMATOR_GATES[DEFAULT_ESTIMATOR]

    def pick(threshold: int) -> tuple[list[int], list[dict[str, Any]]]:
        if mode == "anchors":
            return _choose_anchors(nominal, windows, threshold, axis)
        return [w.bin for w in windows if w.fittable(threshold)], []

    points, substitutions = pick(gates["fit_n"])
    fallback = False
    if len(points) < rfit.MIN_POINTS[rfit.FORM_AFFINE]:
        weak_points, weak_subs = pick(gates["whisker_n"])
        if len(weak_points) > len(points):
            points, substitutions, fallback = weak_points, weak_subs, True
    return ModeFits(points, substitutions, fallback, _fits([by_bin[k] for k in points]))


# ---------------------------------------------------------------- series --


@dataclass
class Series:
    """One source of one shower across the windows, with both modes' fits.

    ``estimator_label`` names the source (the deposit, a network, XGBoost),
    as it always has; the plotted estimator is the windows' own.
    """

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

    def median_response_range(self, mode: str) -> list[float] | None:
        """``[lo, hi]`` of ``100·(median R − 1)`` over one mode's fitted windows; ``None`` without one."""
        chosen = set(self.modes[mode].points)
        values = [100.0 * (w.median_r - 1.0) for w in self.windows
                  if w.bin in chosen and w.median_r is not None]
        return [min(values), max(values)] if values else None


def build_series(source: str, shower: str, shower_label: str, estimator_label: str,
                 colour_slot: str, ratio: np.ndarray, p: np.ndarray, bins: np.ndarray,
                 axis: performance_bins.BinAxis, nominal: Sequence[int], *,
                 estimator: str = DEFAULT_ESTIMATOR, relative: np.ndarray | None = None,
                 seed: Sequence[int] = (median_mod.BOOTSTRAP_SEED,), **counts: int) -> Series:
    """One series under one estimator; ``relative`` and ``seed`` as :func:`windows_of` takes them."""
    windows = windows_of(ratio, p, bins, axis, estimator=estimator, relative=relative, seed=seed)
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


def _window_span(w: Window) -> tuple[float, float]:
    """What a window draws on a σ/E axis, in percent: its marker, and its whisker where it has one."""
    r = w.r
    if w.whisker:
        return 100.0 * min(r, w.ci[0]), 100.0 * max(r, w.ci[1])
    return 100.0 * r, 100.0 * r


def linear_extents(series: Sequence[Series]) -> list[response.Extent]:
    """The 1/√E view's range extents: its windows, and nothing else.

    Every window on the axis with a σ/E and N ≥ :data:`REPORT_MIN_N`, its
    whisker included where it has one, robust where it is eligible (N ≥
    :data:`FIT_MIN_N` from :data:`E_MIN_GEV`, with a positive SE). No fit
    enters it, provisional or not: a fit summarises the windows and is not more
    evidence, so a line or band that leaves the top is clipped by the panel.
    """
    out: list[response.Extent] = []
    for s in series:
        for w in s.windows:
            if w.r is None or w.off_axis or w.n < REPORT_MIN_N:
                continue
            lo, hi = _window_span(w)
            out.append(response.Extent(lo, hi, 100.0 * w.r, w.eligible))
    return out


def linear_y_axis(series: Sequence[Series]) -> dict[str, Any]:
    """The 1/√E view's zero-based σ/E range, set by the windows alone, with its clipped count."""
    return response._y_axis(linear_extents(series))


def energy_extents(series: Sequence[Series]) -> tuple[list[response.Extent], list[float]]:
    """The E view's range extents, and the tops of the windows below the 2 GeV floor.

    Extents: every window with a σ/E, N ≥ :data:`REPORT_MIN_N` and
    ``p_lo ≥ E_VIEW_Y_MIN_GEV`` (off the 1/√E axis or not), its whisker
    included where it has one, robust from N ≥ :data:`FIT_MIN_N` with a
    positive SE. No fit enters them, as in :func:`linear_extents`. The tops
    (marker, or whisker top where it has one) of the windows below the floor are
    returned apart: they never enter ``response._y_axis``, and are only counted
    against the top it sets.
    """
    out: list[response.Extent] = []
    below: list[float] = []
    for s in series:
        for w in s.windows:
            if w.r is None or w.n < REPORT_MIN_N:
                continue
            lo, hi = _window_span(w)
            if w.p_lo < E_VIEW_Y_MIN_GEV:
                below.append(hi)
                continue
            out.append(response.Extent(lo, hi, 100.0 * w.r, w.n >= FIT_MIN_N and w.usable))
    return out, below


def energy_y_axis(series: Sequence[Series]) -> dict[str, Any]:
    """The E view's zero-based σ/E range, set by the windows alone; those below 2 GeV counted when clipped."""
    extents, below = energy_extents(series)
    if not any(e.robust for e in extents):
        # Nothing robust from the floor: the provisional range follows every
        # reported marker, those below the floor included.
        for s in series:
            for w in s.windows:
                if w.r is not None and w.n >= REPORT_MIN_N and w.p_lo < E_VIEW_Y_MIN_GEV:
                    m = 100.0 * w.r
                    extents.append(response.Extent(m, m, m, False))
    y = response._y_axis(extents)
    y["n_clipped"] += sum(1 for top in below if top > y["hi"])
    return y


def _curve(fit: rfit.Fit, points: int) -> list[list[float]]:
    xs = np.linspace(0.0, X_MAX, points)
    y, lo, hi = rfit.band(fit, xs)
    return [[float(a), 100.0 * float(b), 100.0 * float(c), 100.0 * float(d)]
            for a, b, c, d in zip(xs, y, lo, hi)]


#: How a fit's note names its weights, per law (``WEIGHT_METHODS``).
_WEIGHT_WORDS: dict[str, str] = {
    "delta": "weights 1/se² with se recomputed at the fitted value",
    "kappa": ("weights 1/se², se = κ·ŷ with κ the window's bootstrap relative SE, recomputed at "
              "the fitted value"),
}


def _fit_note(fit: rfit.Fit, provisional: bool, estimator: str = SAMPLE) -> str:
    symbol = ESTIMATOR_SYMBOLS[estimator]
    equation = {
        rfit.FORM_AFFINE: f"{symbol} = a/√E + b",
        rfit.FORM_PINNED: f"{symbol} = a₀/√E, through the origin",
        rfit.FORM_QUADRATURE: f"{symbol} = √(a²/E + b²), fitted as ({symbol})² = A/E + B",
    }[fit.form]
    parts = [f"{equation}: weighted least squares over {fit.n_points} window"
             f"{'s' if fit.n_points != 1 else ''}, {_WEIGHT_WORDS[WEIGHT_METHODS[estimator]]} "
             f"({fit.iterations} refit{'s' if fit.iterations != 1 else ''}"
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
        gates = ESTIMATOR_GATES[estimator]
        parts.append(f"Provisional: fewer than two windows reach N = {gates['fit_n']}, so it runs "
                     f"through windows of N ≥ {gates['whisker_n']}.")
    if fit.misfit:
        parts.append(f"S = {fit.scale_factor:.3g} > {rfit.MISFIT_SCALE:g}: its residuals average "
                     "S times the windows' own standard errors, so its form does not describe "
                     "these windows; it is drawn faded and never sets a range.")
    return " ".join(parts)


def fit_block(fit: rfit.Fit | None, provisional: bool, band_points: int = BAND_POINTS,
              estimator: str = SAMPLE) -> dict[str, Any] | None:
    """One fit for the wire: parameters in percent (a in %·√GeV, b in %), its curve and note.

    Every form carries its ``band_quantile`` and ``misfit`` (:attr:`rfit.Fit.misfit`:
    its form does not describe its windows, so the card draws it faded). The
    quadrature fit's ``curve`` is ``None`` (the 1/√E view tables it); its params
    carry ``rho_a2b2``, the correlation of A and B, so the E view can rebuild its
    band from ``a2``, ``b2``, their SEs and ``band_quantile`` alone. ``estimator``
    names the fitted quantity and the weight law in the note; it defaults to the
    sample estimator, whose delta-method law is ``stats/resolution_fit``'s default.
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
    out["misfit"] = fit.misfit
    out["note"] = _fit_note(fit, provisional, estimator)
    return out


# ----------------------------------------------------------- calibration --


@dataclass(frozen=True)
class MedianCalibration:
    """One shower's median calibration ``c̃ = 1 / median(E_dep / p)``, the median estimator's ``c``."""

    c: float | None
    n_positive: int
    n_zero: int


def median_calibration(sample: response.Sample) -> MedianCalibration:
    """``c̃`` over the shower's usable events of the selection with ``E_dep > 0``; ``None`` without one.

    The median analogue of the ratio of sums ``c = Σp / ΣE_dep``: over the
    events it is taken on, the calibrated deposit's median response
    ``c̃·E_dep / p`` is 1 by construction (the module docstring has why the
    median estimator needs it). An event that deposited nothing has no ratio
    to take the median of; it stays in the windows, at R = 0, and is counted.
    """
    positive = sample.dep > 0.0
    n_positive = int(positive.sum())
    n_zero = int(sample.n - n_positive)
    if not n_positive:
        return MedianCalibration(None, 0, n_zero)
    return MedianCalibration(1.0 / float(np.median(sample.dep[positive] / sample.p[positive])),
                             n_positive, n_zero)


#: Each estimator's whisker, as the estimator block names it.
INTERVAL_METHODS: dict[str, str] = {
    MEDIAN: metrics.METHOD_BOOTSTRAP, ROBUST: metrics.METHOD_BOOTSTRAP,
    SAMPLE: metrics.METHOD_CHI2_RATIO,
}
INTERVAL_LABELS: dict[str, str] = {
    MEDIAN: (f"95% percentile bootstrap of the median from N = {median_mod.MIN_BOOTSTRAP_N} "
             f"(B = {median_mod.BOOTSTRAP_REPLICATES:,}, each replicate's median drawn exactly), "
             f"the distribution-free order-statistic interval for {median_mod.MIN_ORDER_N} ≤ N < "
             f"{median_mod.MIN_BOOTSTRAP_N}, none below: Model Error vs. Incident Momentum's own, "
             "seeded [42, frame, shower, bin, 2] with frame 0–2 the network frames (absolute, "
             "per-shower translated, local), 3 XGBoost and 4 the deposit, shower 0 for A and 1 "
             "for B."),
    ROBUST: (f"95% percentile bootstrap of IQR(R) / (1.349 · median R) from N = "
             f"{rw.MIN_ROBUST_N}, B = {rw.BOOTSTRAP_REPLICATES:,}, each replicate's quartiles "
             "drawn exactly from its resample's order statistics (sequential conditional Betas), "
             "seeded [42, frame, shower, bin, 8] with frames and showers numbered as for the "
             "median."),
    SAMPLE: ("95% χ² interval of s (N − 1 d.o.f.) divided by R̄; R̄'s own uncertainty is "
             "neglected, the delta-method se includes it."),
}
WEIGHT_LABELS: dict[str, str] = {
    "kappa": ("Fit weights 1/se², se = κ·ŷ with κ = SE / value the window's bootstrap relative "
              "SE (the SD, ddof = 1, of the replicates behind its interval), recomputed at the "
              "fitted value ŷ and iterated; the first fit takes the bootstrap SE itself. The "
              "Gaussian asymptotic law would understate these SEs."),
    "delta": ("Fit weights 1/se², se = |r|·√(1/(2(N − 1)) + r²/N), the delta-method standard "
              "error of σ/μ, recomputed at the fitted value and iterated."),
}
CALIBRATION_LABELS: dict[str, str] = {
    "median": ("Under Median |rel. err.| the deposit is c̃·E_dep, with c̃ = 1 / median(E_dep / p) "
               "over the shower's events of the selection with E_dep > 0: one constant per "
               "shower, the median analogue of the ratio of sums c = Σ p / Σ E_dep (c_sum), "
               "which is reported beside it. median |c·E_dep − p| / p depends on c; the robust "
               "and sample widths do not."),
    "sum": ("The deposit is c·E_dep with c = Σ p / Σ E_dep per shower over the selection "
            "(c_sum), fitted once; it cancels in the robust and sample widths. c_median, "
            "1 / median(E_dep / p) over the events with E_dep > 0, is the calibration the "
            "median rel. cross-reference (alt) takes."),
}

_WINDOW_NOTES: dict[str, str] = {
    SAMPLE: (
        "Each window is the producer's integer momentum bin k, [k, k + 1) GeV, of the "
        "shower's own momentum. Per event R = E_est / p; the plotted value is σ/E = s(R)/R̄ in "
        "percent (s with ddof = 1), its whisker the 95% χ² interval of s divided by R̄ "
        "(N − 1 d.o.f.; R̄'s own uncertainty is neglected, the delta-method se_delta "
        "includes it), and its abscissa x = ⟨1/√p⟩ over the window's events. Dividing by p "
        "event by event removes the window's own momentum spread and the estimator's bias, "
        "and c cancels in s(R)/R̄, so the detector series does not depend on the calibration."),
    MEDIAN: (
        "Each window is the producer's integer momentum bin k, [k, k + 1) GeV, of the "
        "shower's own momentum. Per event R = E_est / p; the plotted value is the median "
        "relative error median |R − 1| in percent, for a model series median |E_est − p| / p: "
        "the Median rel. of Model Error vs. Incident Momentum, with its events, its seed and "
        "its interval, the 95% percentile bootstrap of the median from N = 20 (B = 2,000) and "
        "the distribution-free order-statistic interval below. Its abscissa is x = ⟨1/√p⟩ over "
        "the window's events. Dividing by p event by event removes the window's own momentum "
        "spread; unlike σ/E the median relative error keeps the estimator's bias, and it "
        "depends on the deposit's calibration."),
    ROBUST: (
        "Each window is the producer's integer momentum bin k, [k, k + 1) GeV, of the "
        "shower's own momentum. Per event R = E_est / p; the plotted value is the robust "
        "σ/E = IQR(R) / (1.349 · median R) in percent, with type-7 quartiles, its whisker the "
        "95% percentile bootstrap of that ratio (B = 2,000, each replicate's quartiles drawn "
        "exactly from its resample's order statistics), and its abscissa x = ⟨1/√p⟩ over the "
        "window's events. It equals σ/E for Gaussian errors and is not inflated by a few "
        "badly reconstructed events; dividing by p event by event removes the window's own "
        "momentum spread and the estimator's bias, and c cancels in it, so the detector "
        "series does not depend on the calibration."),
}

_GATE_NOTES: dict[str, str] = {
    SAMPLE: (f"σ/E is reported from N = {REPORT_MIN_N}; a window is drawn with its whisker from "
             f"N = {WHISKER_MIN_N}, and enters the fits and sets the y range from N = {FIT_MIN_N} "
             f"and p ≥ {E_MIN_GEV:g} GeV."),
    MEDIAN: (f"The median rel. is reported from N = {REPORT_MIN_N}; a window is drawn with its "
             f"whisker from N = {WHISKER_MIN_N} (its order-statistic interval exists from "
             f"N = {median_mod.MIN_ORDER_N}), and enters the fits and sets the y range from "
             f"N = {FIT_MIN_N} and p ≥ {E_MIN_GEV:g} GeV."),
    ROBUST: (f"Robust σ/E is reported, drawn with its whisker, fitted and allowed to set the y "
             f"range from N = {rw.MIN_ROBUST_N} alone, the robust floor: quartiles of fewer "
             f"events interpolate between single events. A window enters the fits and sets the "
             f"y range from p ≥ {E_MIN_GEV:g} GeV."),
}

_FIT_TAIL = (
    "χ², ν = n − p and its p-value. Where χ²/ν > 1 the standard errors and the 95% band are "
    "scaled by S = √(χ²/ν) (PDG), and the band then takes Student's t₀.₉₇₅,ν rather than "
    "1.96, since S is estimated from the fit's own ν. The band is the 95% confidence band of "
    "the line, not the spread of the events.")

_FITS_NOTES: dict[str, str] = {
    SAMPLE: (
        "Fits: a/√E + b and a₀/√E through the origin, by weighted least squares with weights "
        "1/se², se the delta-method standard error of σ/μ recomputed at the fitted value and "
        "iterated (half steps once the refits oscillate); χ², ν = n − p and its p-value. Where "
        "χ²/ν > 1 the standard errors and the 95% band are scaled by S = √(χ²/ν) (PDG), and the "
        "band then takes Student's t₀.₉₇₅,ν rather than 1.96, since S is estimated from the "
        "fit's own ν. The band is the 95% confidence band of the line, not the spread of the "
        "events. The quadrature form √(a²/E + b²) is fitted as (σ/E)² = A/E + B and tabled, "
        "not drawn; its b and the affine b are different constant terms."),
    ROBUST: (
        "Fits: a/√E + b and a₀/√E through the origin, by weighted least squares with weights "
        "1/se², se = κ·ŷ with κ the window's bootstrap relative SE (the SD of the replicates "
        "behind its interval, over its value), taken at the fitted value ŷ and iterated (half "
        "steps once the refits oscillate); the first fit takes the bootstrap SE itself. "
        + _FIT_TAIL + " The quadrature form √(a²/E + b²) is fitted as (σ/E)² = A/E + B and "
        "tabled, not drawn; its b and the affine b are different constant terms."),
    MEDIAN: (
        "Fits: a/√E + b and a₀/√E through the origin, by weighted least squares with weights "
        "1/se², se = κ·ŷ with κ the window's bootstrap relative SE (the SD of the replicates "
        "behind its interval, over its value), taken at the fitted value ŷ and iterated (half "
        "steps once the refits oscillate); the first fit takes the bootstrap SE itself. "
        + _FIT_TAIL + " The quadrature form √(a²/E + b²) is fitted as (median rel.)² = A/E + B "
        "and tabled, not drawn. The three forms describe the median relative error: their "
        "parameters are not the stochastic and constant terms of a resolution."),
}


def _range_words(values: list[float] | None) -> str:
    if values is None:
        return "no fitted window"
    lo, hi = values
    return f"{fmt_signed(lo, 2, plus=True)}% to {fmt_signed(hi, 2, plus=True)}%"


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
    estimator: str = DEFAULT_ESTIMATOR
    medians: dict[str, MedianCalibration] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Both views' ranges follow the windows alone (the module docstring).
        self.y = linear_y_axis(self.series)
        self.energy_y = energy_y_axis(self.series)

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
            median_cal = self.medians.get(s.key)
            if self.estimator == MEDIAN and s.n and median_cal is not None and median_cal.c is None:
                out.append(
                    f"{s.columns.label}: no event of the selection deposits energy (E_dep > 0), so "
                    "the median calibration c̃ = 1 / median(E_dep / p) does not exist and the "
                    "deposit has no windows under Median |rel. err.| (their values are null); "
                    "Robust σ (IQR) and Sample σ/μ do not depend on the calibration.")
        for s in self.series:
            if s.source != SOURCE_DETECTOR and s.n_missing and not s.n:
                out.append(f"{s.label}: no event of the selection has a finite prediction and "
                           "truth; every one is counted in n_missing and none is drawn.")
        if self.run is not None and not self.run["split"]["reproduced"]:
            out.append(self.run["split"]["warning"])
        return [typographic(w) for w in out if w]

    def _calibration_notes(self) -> list[str]:
        notes = []
        for s in self.samples:
            cal, med = self.calibrations[s.key], self.medians.get(s.key)
            c_tilde = None if med is None else med.c
            label = s.columns.label
            if self.estimator == MEDIAN:
                if c_tilde is None:
                    continue
                c_sum = cal.c.value
                beside = ("" if c_sum is None else
                          f"; the ratio of sums c = Σ p / Σ E_dep = {c_sum:.4g} beside it, which "
                          "a low-side leakage tail would leave with a median response above 1")
                notes.append(f"{label}: c̃ = 1 / median(E_dep / p) = {c_tilde:.4g} over the "
                             f"{med.n_positive:,} events with E_dep > 0, fitted once over the "
                             f"selection, so the deposit's median response over them is 1{beside}.")
                continue
            if cal.c.value is not None:
                notes.append(f"{label}: c = Σ p / Σ E_dep = {cal.c.value:.4g} over "
                             f"N = {cal.n:,} events, fitted once over the whole selection.")
            if c_tilde is not None:
                notes.append(f"{label}: the median rel. cross-reference (alt) takes the median "
                             f"calibration c̃ = 1 / median(E_dep / p) = {c_tilde:.4g}, over the "
                             f"{med.n_positive:,} events with E_dep > 0.")
        return notes

    def _model_range_notes(self) -> list[str]:
        models = [s for s in self.series if s.source != SOURCE_DETECTOR]
        notes = [f"{s.label}: median response R̃ − 1 from "
                 f"{_range_words(s.median_response_range('anchors'))} over the anchors' fitted "
                 f"windows, {_range_words(s.median_response_range('all'))} over every fitted "
                 "window." for s in models]
        if models:
            notes.append(
                "A regressor trained on a bounded momentum range pulls its predictions toward "
                "mid-range, so its median response leaves 1 near the ends of that range: there it "
                "narrows a σ and adds a bias to the median rel.")
        return notes

    def _notes(self) -> list[str]:
        kind = self.record.kind or ""
        est = self.estimator
        gates = ESTIMATOR_GATES[est]
        if est == ROBUST:
            fallback = ("with fewer than two such windows there is no fit, since the robust width "
                        "has no weaker window to fall back on")
        else:
            fallback = (f"with fewer than two such windows its fit runs through windows of "
                        f"N ≥ {gates['whisker_n']} and is provisional")
        notes = [
            response._DEPOSIT_NOTE.get(kind, ""),
            _WINDOW_NOTES[est],
            RELATION,
            "The detector series c·E_dep is a linear-sum benchmark, not a limit: a model that "
            "reads the shower's shape (leakage, compensation) can do better than a plain sum.",
            "E on both axes is the incident momentum p as the producer writes it. For a massive "
            "species √(p² + m²) differs from p by at most m²/2p², 1.7% for a proton at 5 GeV/c.",
            _GATE_NOTES[est],
            _FITS_NOTES[est],
            f"A fit whose residuals average more than {rfit.MISFIT_SCALE:g} of the windows' own "
            f"standard errors (ν ≥ 1 and S = √(χ²/ν) > {rfit.MISFIT_SCALE:g}) has a form that does "
            "not describe its windows: it is drawn faded, as a provisional fit is, and said so in "
            "its tooltip, the fit table and the drawer. The size of the misfit decides, not the χ² "
            "p-value: a window of hundreds of events has so small a standard error that the test "
            "rejects a form for misfits no reader could see.",
            f"Anchors: the lowest bin from {ANCHOR_LOW_GEV:g} GeV (below it the sampling fraction "
            "is still rising), the highest bin and the bin between them nearest in log E to the "
            "geometric mean of their centres, chosen on the whole table so they do not move with "
            f"the selection. A series whose anchor window holds N < {gates['fit_n']} takes its "
            f"nearest window from {ANCHOR_LOW_GEV:g} GeV in log E with N ≥ {gates['fit_n']} "
            f"instead; {fallback}. The other mode fits every window with N ≥ {gates['fit_n']} from "
            f"{E_MIN_GEV:g} GeV, the {E_MIN_GEV:g}–{ANCHOR_LOW_GEV:g} GeV window included, below "
            "the anchors' floor.",
            "The top axis is an exact relabelling of the bottom one, E = 1/x²: a deterministic "
            "unit conversion, and no data are plotted against it.",
        ]
        if est == ROBUST:
            windows = [w for s in self.series for w in s.windows]
            thin = sum(1 for w in windows if w.n < rw.MIN_ROBUST_N)
            notes.append(
                f"{thin} of the {len(windows)} windows across the series hold "
                f"N < {rw.MIN_ROBUST_N} and report no robust σ/E (the robust floor); Sample σ/μ "
                f"reports them from N = {REPORT_MIN_N}.")
        notes.extend(self._calibration_notes())
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
        notes.extend(self._model_range_notes())
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
                         f"{X_MAX:g}; they are listed in off_axis with their "
                         f"{ESTIMATOR_SYMBOLS[est]} and not drawn.")
        for s in self.series:
            tied = [w for w in s.windows
                    if w.tied and w.n >= gates["fit_n"] and not w.off_axis]
            if tied:
                many = len(tied) != 1
                notes.append(
                    f"{s.label}: {len(tied)} window{'s' if many else ''} with a bootstrap SE below "
                    f"{_power_of_ten(rw.KAPPA_FLOOR)} of {'their' if many else 'its'} value (tied values: the "
                    f"replicates differ by rounding alone) carr{'y' if many else 'ies'} no fit weight, "
                    f"so {'they are' if many else 'it is'} drawn but not fitted.")
            for mode_name, mode in s.modes.items():
                for sub in mode.substitutions:
                    notes.append(f"{s.label} ({mode_name}): {sub['reason']}")
                for fit in mode.fits.values():
                    if fit is not None and fit.scale_factor > 1.0:
                        misfit = (f"; S > {rfit.MISFIT_SCALE:g}, so its form does not describe "
                                  "these windows and it is drawn faded" if fit.misfit else "")
                        notes.append(f"{s.label} ({mode_name}, {fit.form}): χ²/ν = "
                                     f"{fit.chi2 / fit.ndf:.3g}, so its errors are scaled by "
                                     f"S = {fit.scale_factor:.3g}{misfit}.")
                affine = mode.fits.get(rfit.FORM_AFFINE)
                if affine is not None and affine.theta[1] < 0:
                    notes.append(f"{s.label} ({mode_name}): the affine b is negative "
                                 f"({100 * affine.theta[1]:.3g}%): the points fall faster than "
                                 "a/√E, and the line is drawn down to zero.")
        y = self.y
        fit_n = gates["fit_n"]
        basis = (f"The y range is provisional: no window from {E_MIN_GEV:g} GeV reaches "
                 f"N = {fit_n}, so it follows the weaker windows' markers." if y["provisional"]
                 else f"The y range follows the windows with N ≥ {fit_n} (whiskers included) "
                      "alone, from zero.")
        fits = ("No fit sets it: a fit summarises its windows and is not more evidence, so a "
                "fitted line or band that leaves the top is clipped there with a caret.")
        clipped = y["n_clipped"]
        notes.append(f"{basis} {fits} {clipped} window{'s' if clipped != 1 else ''} beyond it "
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
            "y": {**self.y, "unit": UNIT, "name": AXIS_NAMES[self.estimator]},
            "energy": self._energy_axis(),
        }

    def _energy_axis(self) -> dict[str, Any]:
        """The E view's axes: E in GeV from zero, its own value range, and the sentences that say why."""
        data_max = float(self.axis.p_hi[-1]) if self.axis.p_hi else None
        x_max = E_VIEW_MAX_GEV
        if data_max is not None:
            x_max = max(E_VIEW_MAX_GEV,
                        math.ceil(data_max / E_VIEW_INTERVAL_GEV) * E_VIEW_INTERVAL_GEV)
        y = self.energy_y
        fit_n = ESTIMATOR_GATES[self.estimator]["fit_n"]
        floor = f"{E_VIEW_Y_MIN_GEV:g} GeV"
        basis = (f"The E view's y range is provisional: no window from {floor} reaches "
                 f"N = {fit_n}, so it follows the windows' markers, those below {floor} "
                 "included." if y["provisional"] else
                 f"The E view's y range follows the windows alone, from zero: those with "
                 f"N ≥ {fit_n} from {floor}, whiskers included; a window below {floor} never "
                 "sets it.")
        fits = ("No fitted curve, band or extrapolation sets it: one that leaves the top is "
                "clipped there with a caret.")
        notes = [
            f"{basis} {fits}",
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
            "y": {**y, "unit": UNIT, "name": AXIS_NAMES[self.estimator]},
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
        gates = ESTIMATOR_GATES[self.estimator]
        fallback = ("with fewer than two, no fit: the robust width has no weaker window to fall "
                    "back on." if self.estimator == ROBUST else
                    f"with fewer than two, windows of N ≥ {gates['whisker_n']} and the fit is "
                    "provisional.")
        return {
            "nominal_bins": list(self.nominal),
            "labels": [self.axis.labels[index[k]] for k in self.nominal],
            "rule": (f"Chosen on the whole table's bins, not the selection: the lowest bin from "
                     f"{ANCHOR_LOW_GEV:g} GeV, the highest bin, and the bin between them nearest "
                     "in log E to the geometric mean of their centres. A series whose anchor "
                     f"holds N < {gates['fit_n']} takes its nearest window from "
                     f"{ANCHOR_LOW_GEV:g} GeV in log E with N ≥ {gates['fit_n']}, named in "
                     f"substitutions; {fallback}"),
        }

    def _estimator_block(self) -> dict[str, Any]:
        est = self.estimator
        rule = "median" if est == MEDIAN else "sum"
        weight = WEIGHT_METHODS[est]
        showers = {}
        for s in self.samples:
            cal, med = self.calibrations[s.key], self.medians.get(s.key)
            showers[s.key] = {
                "c_sum": cal.c.value,
                "c_median": None if med is None else med.c,
                "n": cal.n,
                "n_zero_deposit": None if med is None else med.n_zero,
            }
        return {
            "name": est,
            "label": ESTIMATOR_LABELS[est],
            "quantity": ESTIMATOR_QUANTITIES[est],
            "symbol": ESTIMATOR_SYMBOLS[est],
            "definition": ESTIMATOR_DEFINITIONS[est],
            "axis_name": AXIS_NAMES[est],
            "interval": {"method": INTERVAL_METHODS[est], "label": INTERVAL_LABELS[est]},
            "weight": {"method": weight, "label": WEIGHT_LABELS[weight]},
            "literature": {"drawn": True, "warning": LITERATURE_WARNING if est == MEDIAN else None},
            "calibration": {"rule": rule, "label": CALIBRATION_LABELS[rule], "showers": showers},
            "relation": RELATION,
            "choices": list(ESTIMATORS),
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
                    **{form: fit_block(mode.fits.get(form), mode.provisional, band_points,
                                       self.estimator)
                       for form in (rfit.FORM_AFFINE, rfit.FORM_PINNED, rfit.FORM_QUADRATURE)},
                    "span_gev": fitted_span(mode.points, s.windows),
                }
                for name, mode in s.modes.items()
            },
            "median_response_range": {name: s.median_response_range(name) for name in MODES},
        }

    def as_dict(self, digits: int = SIGNIFICANT, band_points: int = BAND_POINTS) -> dict[str, Any]:
        """The payload body (no ``meta`` or ``filter``), rounded for the wire."""
        tree = {
            "kind": self.record.kind,
            "n_events": self.n_events,
            "unit": UNIT,
            "estimator": self._estimator_block(),
            "axis": self._axis(),
            "gates": {**ESTIMATOR_GATES[self.estimator],
                      "e_min_gev": E_MIN_GEV, "anchor_low_gev": ANCHOR_LOW_GEV,
                      "n_anchors": N_ANCHORS, "misfit_scale": rfit.MISFIT_SCALE},
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
                  nominal: Sequence[int], estimator: str = DEFAULT_ESTIMATOR,
                  ) -> tuple[dict[str, Any], dict[str, Series], dict[str, Any] | None]:
    """The model block, the model series per shower and, on an aggregate, the XGBoost run.

    The relative error is computed as ``performance_bins.point`` computes its
    Median rel., ``|pred − true| / true`` over the same rows, and seeded as it
    seeds them (``[42, frame, shower, bin, …]``), so a window's median value and
    interval equal that card's bit for bit.
    """
    kind = record.kind
    if kind == ddl.KIND_TWO_SHOWER:
        if not caps.models:
            reason = caps.reasons.get("perf-bins", "This experiment carries no networks.")
            return ({"available": False, "source": None, "frame": None, "label": None,
                     "reason": reason, "split": None}, {}, None)
        frame = ddl.NETWORK_FRAME[coord_system]
        label = f"Energy network · {FRAME_WORDS[frame]} frame"
        frame_index = ddl.COORD_SYSTEMS.index(coord_system)
        cols = performance_bins.read_selection(con, record, spec, "energy", [coord_system])
        out = {}
        for shower_index, key in enumerate(shower_labels):
            bins, true = cols[f"bin_{key}"], cols[f"true_{key}"]
            pred = cols[f"pred_{key}_{coord_system}"]
            usable, missing, dropped = _pairs(pred, true, bins)
            pred_u, true_u = pred[usable], true[usable]
            out[key] = build_series(
                SOURCE_NETWORK, key, shower_labels[key], label, frame,
                pred_u / true_u, true_u, bins[usable], axis, nominal,
                estimator=estimator, relative=np.abs(pred_u - true_u) / true_u,
                seed=(median_mod.BOOTSTRAP_SEED, frame_index, shower_index),
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
        pred_u, true_u = pred[usable], true[usable]
        key = next(iter(shower_labels))
        series = build_series(
            SOURCE_XGB, key, shower_labels[key], XGB_LABEL, SOURCE_XGB,
            pred_u / true_u, true_u, bins[usable], axis, nominal,
            estimator=estimator, relative=np.abs(pred_u - true_u) / true_u,
            seed=(median_mod.BOOTSTRAP_SEED, performance_bins.XGB_FRAME_INDEX, 0),
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


def _deposit_inputs(sample: response.Sample, cal: response.Calibration, med: MedianCalibration,
                    estimator: str) -> tuple[np.ndarray, np.ndarray]:
    """The deposit's ``(R, relative error)`` under one estimator.

    Under the robust and sample estimators ``R = c·E_dep / p`` with today's
    ratio of sums, which cancels in both widths; a selection that deposited
    nothing has no c, and its R are all zero either way. Under the median
    estimator ``R = c̃·E_dep / p``. The relative error is always
    ``|c̃·E_dep − p| / p``, Model Error vs. Incident Momentum's arithmetic with
    the deposit as the prediction, and NaN where no c̃ exists, so no median is
    reported then.
    """
    c = cal.c.value
    ratio = (1.0 if c is None else c) * sample.dep / sample.p
    if med.c is None:
        return ratio, np.full(sample.dep.shape, np.nan)
    if estimator == MEDIAN:
        ratio = med.c * sample.dep / sample.p
    return ratio, np.abs(med.c * sample.dep - sample.p) / sample.p


def compute(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec,
            coord_system: str = "lab", estimator: str = DEFAULT_ESTIMATOR) -> ResolutionScaling:
    """Every series of the selection, under one estimator: the detector's per shower and the model's."""
    if coord_system not in ddl.COORD_SYSTEMS:
        raise ValidationError(
            f"coord_system must be one of {', '.join(ddl.COORD_SYSTEMS)}; got {coord_system!r}.",
            field="coord_system")
    check_estimator(estimator)
    caps = capabilities.of(record)
    axis = performance_bins.dataset_axis(con, record)
    nominal = nominal_anchors(axis)
    columns = showers_mod.of(record, "both")
    samples = response.fetch(con, record, spec, columns)
    calibrations = {s.key: response.calibrate(s) for s in samples}
    medians = {s.key: median_calibration(s) for s in samples}
    labels, shower_note = _shower_labels(con, record, spec, caps, columns)
    model, model_series, run = _model_series(con, record, spec, caps, coord_system, labels,
                                             axis, nominal, estimator)
    series: list[Series] = []
    for shower_index, sample in enumerate(samples):
        ratio, relative = _deposit_inputs(sample, calibrations[sample.key], medians[sample.key],
                                          estimator)
        series.append(build_series(
            SOURCE_DETECTOR, sample.key, labels[sample.key], DETECTOR_LABEL, SOURCE_DETECTOR,
            ratio, sample.p, sample.bin, axis, nominal,
            estimator=estimator, relative=relative,
            seed=(median_mod.BOOTSTRAP_SEED, DEPOSIT_FRAME_INDEX, shower_index),
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
        estimator=estimator, medians=medians,
    )
