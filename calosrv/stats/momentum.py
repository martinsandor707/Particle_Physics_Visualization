"""Incident-momentum classes: windows, 1 GeV bins and the binary label.

Two window sets exist on purpose, one per notebook, and each panel says which
it uses:

* **Calibration windows** (1, 2, 5, 10, 15, 19) ± 0.5 GeV - the response grid
  of the CALIBRATION notebook (B3).
* **Feature classes** (1, 2, 5, 10, 19.5) ± 0.5 GeV - the features-by-energy
  notebook's classes. Its "20 GeV" class is [19, 20) here, because every
  momentum in these files is below 20 GeV.

Windows are half-open, ``[c - h, c + h)``, as in the notebooks, and must not
overlap. Showers in no window are counted under :data:`OUTSIDE` and never
drawn. ``-1`` is taken: it is the energy panel's undefined-separation slice
(``stats.slices.UNDEFINED_SLICE``), and B3 rides that panel's machinery.

The 1 GeV bins use the producer's integer ``incoming_momentum_bin`` column, not
``floor(p)``. Each bin is labelled "k–k+1 GeV" only when the measured momenta
of the bin lie inside [k, k+1); otherwise the label states the bin number and
the range actually found, because a file whose bin column disagrees with its
momenta must not be read as if it agreed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

import numpy as np

from ..errors import ValidationError

OUTSIDE = -2

CALIBRATION_CENTRES_GEV: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 15.0, 19.0)
FEATURE_CENTRES_GEV: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 19.5)
HALF_WIDTH_GEV = 0.5
LABEL_THRESHOLD_GEV = 2.0
MAX_CLASSES = 24

KIND_WINDOW = "window"
KIND_BIN = "bin"
KIND_LABEL = "label"

MODE_NOTEBOOK = "notebook"
MODE_BINS = "bins"
MODE_LIST = "list"


def _gev(value: float) -> str:
    return f"{value:g}"


@dataclass(frozen=True)
class MomentumClass:
    index: int
    label: str
    lo: float
    hi: float | None      # None: unbounded above
    kind: str
    centre: float | None = None

    def contains(self, p: float) -> bool:
        return p >= self.lo and (self.hi is None or p < self.hi)

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "label": self.label, "lo": self.lo, "hi": self.hi,
                "kind": self.kind, "centre": self.centre}


def windows(centres: Sequence[float] = CALIBRATION_CENTRES_GEV,
            half: float = HALF_WIDTH_GEV, field: str = "p_slices") -> list[MomentumClass]:
    """Half-open windows ``[c - half, c + half)``; overlap or excess is a 422 on ``field``."""
    if not math.isfinite(half) or half <= 0:
        raise ValidationError(f"The window half-width must be positive; got {half!r}.", field=field)
    cs = sorted(float(c) for c in centres)
    if not cs:
        raise ValidationError("At least one momentum window is needed.", field=field)
    if len(cs) > MAX_CLASSES:
        raise ValidationError(f"At most {MAX_CLASSES} momentum windows; got {len(cs)}.",
                              field=field)
    for a, b in zip(cs, cs[1:]):
        if b - a < 2 * half - 1e-12:
            raise ValidationError(
                f"Momentum windows {_gev(a)} ± {_gev(half)} and {_gev(b)} ± {_gev(half)} GeV "
                "overlap; a shower must belong to one window at most.", field=field)
    return [MomentumClass(i, f"{_gev(c)} ± {_gev(half)} GeV", max(0.0, c - half), c + half,
                          KIND_WINDOW, c) for i, c in enumerate(cs)]


def unit_bins(lo_bin: int, hi_bin: int, field: str = "p_slices") -> list[MomentumClass]:
    """One class per integer bin ``lo_bin .. hi_bin`` of the producer's bin column.

    More than :data:`MAX_CLASSES` is a 422 on ``field``, the request parameter
    that chose the binning.
    """
    lo_bin, hi_bin = int(lo_bin), int(hi_bin)
    if hi_bin < lo_bin:
        return []
    if hi_bin - lo_bin + 1 > MAX_CLASSES:
        raise ValidationError(f"At most {MAX_CLASSES} momentum bins; the data span "
                              f"{hi_bin - lo_bin + 1}.", field=field)
    return [MomentumClass(i, f"{k}–{k + 1} GeV", float(k), float(k + 1), KIND_BIN, k + 0.5)
            for i, k in enumerate(range(lo_bin, hi_bin + 1))]


def binary_label(threshold: float = LABEL_THRESHOLD_GEV) -> list[MomentumClass]:
    """The aggregate's ``energy`` label: 1{p ≥ threshold}."""
    t = float(threshold)
    return [MomentumClass(0, f"p < {_gev(t)} GeV", 0.0, t, KIND_LABEL),
            MomentumClass(1, f"p ≥ {_gev(t)} GeV", t, None, KIND_LABEL)]


def relabel_bins(classes: Sequence[MomentumClass],
                 ranges: Mapping[int, tuple[float, float]]) -> tuple[list[MomentumClass], list[str]]:
    """Bin labels checked against the measured momentum range of each bin.

    ``ranges[k] = (p_min, p_max)`` of the events in bin k. A bin whose momenta
    leave [k, k+1) is relabelled "bin k (p a–b GeV)" and named in a notice.
    """
    out, odd = [], []
    for c in classes:
        if c.kind != KIND_BIN:
            out.append(c)
            continue
        k = int(c.lo)
        found = ranges.get(k)
        if found is not None and not (found[0] >= c.lo and found[1] < c.hi):
            out.append(replace(c, label=f"bin {k} (p {found[0]:.3g}–{found[1]:.3g} GeV)"))
            odd.append(k)
        else:
            out.append(c)
    notices = []
    if odd:
        notices.append(
            f"The producer's momentum bin column disagrees with the momenta in bin"
            f"{'s' if len(odd) > 1 else ''} {', '.join(str(k) for k in odd)}: those bins are "
            "labelled by number with the momentum range actually found.")
    return out, notices


@dataclass(frozen=True)
class MomentumSlicing:
    mode: str
    classes: tuple[MomentumClass, ...]
    half_width: float | None

    @property
    def uses_bin_column(self) -> bool:
        return self.mode == MODE_BINS

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "half_width": self.half_width,
                "centres": [c.centre for c in self.classes],
                "role": "bin column" if self.uses_bin_column else "incident momentum p"}


def parse_slicing(raw: str | None, half: float = HALF_WIDTH_GEV,
                  bin_range: tuple[int, int] | None = None) -> MomentumSlicing:
    """``p_slices``: ``notebook`` (default), ``bins``, or comma-separated centres in GeV."""
    text = (raw or MODE_NOTEBOOK).strip().lower()
    if text == MODE_NOTEBOOK:
        return MomentumSlicing(MODE_NOTEBOOK, tuple(windows(CALIBRATION_CENTRES_GEV, half)), half)
    if text == MODE_BINS:
        if bin_range is None:
            raise ValidationError("This experiment records no momentum bins.", field="p_slices")
        return MomentumSlicing(MODE_BINS, tuple(unit_bins(*bin_range)), None)
    try:
        centres = [float(part) for part in text.split(",") if part.strip()]
    except ValueError:
        raise ValidationError(
            f"p_slices must be 'notebook', 'bins' or comma-separated centres in GeV; got {raw!r}.",
            field="p_slices") from None
    if not centres or not all(math.isfinite(c) and c > 0 for c in centres):
        raise ValidationError("Momentum window centres must be positive numbers in GeV.",
                              field="p_slices")
    return MomentumSlicing(MODE_LIST, tuple(windows(centres, half)), half)


def case_sql(classes: Sequence[MomentumClass], momentum: str, bin_column: str | None = None) -> str:
    """A ``CASE`` assigning each row its class index, else :data:`OUTSIDE`.

    ``momentum`` and ``bin_column`` are allowlisted column names from
    ``query/showers.py``; the bounds are this module's own floats, written as
    literals (DuckDB has no array parameter for a CASE ladder).
    """
    arms = []
    for c in classes:
        if c.kind == KIND_BIN:
            if bin_column is None:
                raise ValueError("bin classes need the bin column")
            arms.append(f"WHEN {bin_column} = {int(c.lo)} THEN {c.index}")
        elif c.hi is None:
            arms.append(f"WHEN {momentum} >= {float(c.lo)!r} THEN {c.index}")
        else:
            arms.append(f"WHEN {momentum} >= {float(c.lo)!r} AND {momentum} < {float(c.hi)!r} "
                        f"THEN {c.index}")
    return "CASE " + " ".join(arms) + f" ELSE {OUTSIDE} END"


def assign(p: np.ndarray, classes: Sequence[MomentumClass],
           bins: np.ndarray | None = None) -> np.ndarray:
    """The class index of each value, :data:`OUTSIDE` for none; NumPy twin of :func:`case_sql`."""
    p = np.asarray(p, dtype=np.float64)
    out = np.full(p.shape, OUTSIDE, dtype=np.int16)
    for c in classes:
        if c.kind == KIND_BIN:
            if bins is None:
                raise ValueError("bin classes need the bin column")
            hit = np.asarray(bins) == int(c.lo)
        else:
            hit = p >= c.lo
            if c.hi is not None:
                hit &= p < c.hi
        out[hit & (out == OUTSIDE)] = c.index
    return out
