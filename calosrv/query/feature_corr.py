"""The feature explorer's D3 correlation view.

A request names a frame and a shower. The bundle holds every offered feature
of that shower in that frame for the selected events - one read of the event
table, no hit scan - cached in the ``physics`` cache under the clamped
selection. Everything a view varies (class set, feature, scale, the eps
exclusion) is a NumPy step over the cached arrays.

Showers with fewer than two hits are left out on every kind, as the
producer's aggregate leaves them out: their SDs do not exist, and the two
kinds then describe the same events.

* **D3 correlations** - Pearson r per class with its Fisher-z 95% interval,
  N = events, each event one independent observation. Floored volume factors
  are left out only of the pairs whose values they corrupt. An azimuth has no
  linear r: its cells carry Mardia's circular-linear R, or the
  circular-circular r_c of the two azimuths, with event-grouped jackknife
  uncertainties, and never sit on the colour scale.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from ..encode.numbers import sig
from ..stats import circular, jackknife
from ..stats.metrics import METHOD_FISHER, fisher_z_interval
from ..text import typographic
from . import features_catalog as catalog
from .correlations import R_SCALE
from .features import MIN_FISHER, ClassSet, FeatureBundle
from .features_catalog import Feature

# -------------------------------------------------------------------- D3 --


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    da, db = a - a.mean(), b - b.mean()
    saa, sbb = float((da * da).sum()), float((db * db).sum())
    if not (saa > 0.0 and sbb > 0.0) or not (math.isfinite(saa) and math.isfinite(sbb)):
        return None
    r = float((da * db).sum()) / math.sqrt(saa * sbb)
    return max(-1.0, min(1.0, r)) if math.isfinite(r) else None


def _pearson_matrix(stack: np.ndarray) -> np.ndarray:
    """Pearson r of every pair of rows of ``stack`` (features × events); NaN without variance."""
    if stack.shape[1] == 0:
        return np.full((stack.shape[0], stack.shape[0]), np.nan)
    centred = stack - stack.mean(axis=1, keepdims=True)
    norms = np.sqrt((centred * centred).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (centred @ centred.T) / np.outer(norms, norms)
    return np.clip(r, -1.0, 1.0)


def _cell(r: float | None, n: int, diagonal: bool) -> tuple[float | None, ...]:
    """``(r, lo, hi)`` of one matrix cell; nothing below N = 4 or without variance."""
    if r is None or not math.isfinite(r) or n < MIN_FISHER:
        return None, None, None
    if diagonal:
        return 1.0, None, None
    interval = fisher_z_interval(r, n)
    if interval is None:
        # |r| = 1: one feature is a linear map of the other; the interval is degenerate.
        return sig(r), sig(r), sig(r)
    return sig(r), sig(interval.lo), sig(interval.hi)


#: What each measure of an azimuth's cell in D3 is.
CIRCULAR_MEASURES: dict[str, str] = {
    "mardia": (
        "Mardia's circular–linear R of the linear feature with (cos φ, sin φ) of the azimuth: "
        "0 for no association to 1, unsigned because a circle has no order. se is its "
        "event-grouped jackknife standard error; null_R2 = 2/(N − 1) is what R² averages with "
        f"no association. Quoted from {jackknife.MIN_MARDIA_AZIMUTHS} distinct azimuths, its SE "
        f"from {jackknife.MIN_MARDIA_GROUPS} event groups."),
    "circular_circular": (
        "The Jammalamadaka–SenGupta circular–circular correlation r_c of the two azimuths: "
        "signed, in [−1, 1], unchanged by where the ±π cut falls. ci95 is a 95% event-grouped "
        "jackknife interval on Fisher's z, se_z its standard error; the diagonal is 1 by "
        "definition."),
}


class _AzimuthSums:
    """One class's events in jackknife groups, ready for every azimuth cell of D3.

    Each event is one observation, so the groups are events - one each up to
    64, then event_number mod 64, as C8. The columns are every feature plus the
    cosine and sine of each azimuth. When every value is finite a cell's rows
    are all the events (``whole``) or all but the floored ones (``part``, which
    only the cells of ``part_rows`` - the volume and the densities - use, so
    it holds their columns and the azimuths'), so the grouped sums are taken
    once per row set and each cell reads its columns out of them.
    """

    def __init__(self, features: Sequence[Feature], stack: np.ndarray, events: np.ndarray,
                 part_rows: Sequence[int] = ()) -> None:
        k = len(features)
        self.columns: dict[int, tuple[int, int]] = {}     # azimuth row -> (cos, sin) column
        self.distinct: dict[int, tuple[np.ndarray, int]] = {}
        blocks = [stack]
        for i, feature in enumerate(features):
            if not feature.circular:
                continue
            angle = stack[i]
            self.columns[i] = (k + 2 * len(self.columns), k + 2 * len(self.columns) + 1)
            blocks.append(np.vstack([np.cos(angle), np.sin(angle)]))
            finite = np.isfinite(angle)
            index = np.full(angle.size, -1, dtype=np.int64)
            values, index[finite] = np.unique(angle[finite], return_inverse=True)
            self.distinct[i] = (index, int(values.size))
        self.data = np.vstack(blocks).T
        self.grouping = jackknife.Grouping.of(jackknife.group_ids(events))
        angle_columns = [c for pair in self.columns.values() for c in pair]
        self._layout = {"whole": list(range(self.data.shape[1])),
                        "part": sorted(set(part_rows)) + angle_columns}
        self._shared: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self._shared_distinct: dict[tuple[int, str], int] = {}

    def n_distinct(self, i: int, keep: np.ndarray, shared: str | None) -> int:
        """Distinct values of azimuth ``i`` among the rows ``keep`` holds."""
        index, size = self.distinct[i]
        if shared == "whole":
            return size
        if shared is not None and (i, shared) in self._shared_distinct:
            return self._shared_distinct[(i, shared)]
        chosen = index[keep]
        chosen = chosen[chosen >= 0]
        count = int(np.count_nonzero(np.bincount(chosen, minlength=size))) if chosen.size else 0
        if shared is not None:
            self._shared_distinct[(i, shared)] = count
        return count

    def sums(self, columns: Sequence[int], keep: np.ndarray,
             shared: str | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Grouped sums of ``columns`` over ``keep``; ``shared`` names a row set reused by many cells."""
        if shared is None:
            return self.grouping.sums(self.data[:, list(columns)], keep)
        layout = self._layout[shared]
        if shared not in self._shared:
            self._shared[shared] = self.grouping.sums(self.data[:, layout],
                                                      None if shared == "whole" else keep)
        n_g, s_g, q_g = self._shared[shared]
        idx = np.asarray([layout.index(c) for c in columns])
        return n_g, s_g[:, idx], q_g[:, idx][:, :, idx]


def _circular_cell(features: Sequence[Feature], stack: np.ndarray, sums: _AzimuthSums,
                   keep: np.ndarray, shared: str | None, i: int, j: int,
                   position: int) -> dict[str, Any]:
    """One cell of D3 with an azimuth in it: Mardia's R, or r_c of two azimuths.

    The notebook's linear r of ``avg_phi`` travels as ``parity_r`` only: no
    interval, never on the colour scale.
    """
    fi, fj = features[i], features[j]
    n = int(keep.sum())
    cell: dict[str, Any] = {"position": position, "row": fi.id, "col": fj.id, "n": n,
                            "measure": None, "n_azimuths": None, "value": None, "se": None,
                            "se_z": None, "ci95": None, "null_R2": None, "reason": None,
                            "parity_r": None}
    if fi.circular and fj.circular:
        cell["measure"] = "circular_circular"
        if n < MIN_FISHER:
            cell["reason"] = f"r_c is quoted from N = {MIN_FISHER}; this class has {n}."
        else:
            n_g, s_g, q_g = sums.sums(sums.columns[i] + sums.columns[j], keep, shared)
            value = circular.circular_correlation_from_sums(float(n), s_g.sum(axis=0),
                                                            q_g.sum(axis=0))
            if value is None:
                cell["reason"] = "An azimuth has no spread about its mean direction in this class."
            elif i == j:
                cell["value"] = 1.0
            else:
                cell["value"] = sig(value)
                if n_g.size >= jackknife.MIN_JACKKNIFE_GROUPS:
                    def r_c(n_: float, s_: np.ndarray, q_: np.ndarray) -> np.ndarray:
                        v = circular.circular_correlation_from_sums(n_, s_, q_)
                        return np.asarray(np.nan if v is None else v)

                    loo = jackknife.grouped_jackknife(n_g, s_g, q_g, r_c)
                    with np.errstate(invalid="ignore", divide="ignore"):
                        se_z = jackknife.jackknife_se(np.arctanh(np.clip(loo, -1.0, 1.0)))
                    interval = (fisher_z_interval(value, n, se_z=se_z, dof=int(n_g.size) - 1)
                                if se_z is not None else None)
                    cell["se_z"] = sig(se_z)
                    if interval is not None:
                        cell["ci95"] = [sig(interval.lo), sig(interval.hi)]
    else:
        cell["measure"] = "mardia"
        a_i, x_i = (i, j) if fi.circular else (j, i)
        cell["n_azimuths"] = n_azimuths = sums.n_distinct(a_i, keep, shared)
        cell["null_R2"] = sig(jackknife.mardia_null_r2(n))
        reason = jackknife.mardia_gate(n_azimuths, "this class")
        if reason is None:
            n_g, s_g, q_g = sums.sums((x_i,) + sums.columns[a_i], keep, shared)
            value, se = jackknife.mardia_jackknife(n_g, s_g, q_g, 0, 1, 2)
            if value is None:
                reason = f"{features[x_i].id} has no spread in this class."
            cell["value"], cell["se"] = sig(value), sig(se)
        cell["reason"] = typographic(reason) if reason else None
    if "avg_phi" in (fi.id, fj.id) and fi.notebook and fj.notebook and n >= MIN_FISHER:
        cell["parity_r"] = sig(_pearson(stack[i, keep], stack[j, keep]))
    return cell


def corr_view(bundle: FeatureBundle, cs: ClassSet, which: int | str,
              exclude_eps: bool) -> dict[str, Any]:
    """D3: Pearson r of every feature pair over one class, upper triangle with the diagonal.

    A cell with an azimuth in it has no r, lo or hi - it is hatched and off the
    colour scale - and is described in ``circular_cells`` instead.
    """
    features = catalog.offered(bundle.kind)
    mask = cs.mask(which)
    stack = np.vstack([bundle.values[f.id][mask] for f in features])
    events = bundle.event_number[mask]
    floored = bundle.volume_floored()[mask]
    eps_pair = {i for i, f in enumerate(features) if f.id in catalog.EPS_PAIR_FEATURES}
    circular_rows = {i for i, f in enumerate(features) if f.circular}
    excluded = floored if exclude_eps else np.zeros_like(floored)
    finite = np.isfinite(stack)
    all_finite = bool(finite.all())
    azimuth_sums = (_AzimuthSums(features, stack, events, sorted(eps_pair))
                    if circular_rows else None)

    def kept(i: int, j: int) -> np.ndarray:
        keep = finite[i] & finite[j]
        if i in eps_pair or j in eps_pair:
            keep &= ~excluded
        return keep

    def row_set(i: int, j: int) -> str | None:
        """The shared row set of a pair when every value is finite, else ``None``."""
        if not all_finite:
            return None
        return "part" if (i in eps_pair or j in eps_pair) and excluded.any() else "whole"

    if all_finite:
        # Every pair sees the same events (less the floored ones where they are
        # left out): two matrix products instead of a masked pass per pair.
        whole, n_whole = _pearson_matrix(stack), stack.shape[1]
        part = _pearson_matrix(stack[:, ~excluded]) if excluded.any() else whole
        n_part = n_whole - int(excluded.sum())

        def pair(i: int, j: int) -> tuple[float | None, int]:
            if i in eps_pair or j in eps_pair:
                return float(part[i, j]), n_part
            return float(whole[i, j]), n_whole
    else:
        def pair(i: int, j: int) -> tuple[float | None, int]:
            keep = kept(i, j)
            n = int(keep.sum())
            return (_pearson(stack[i, keep], stack[j, keep]) if n >= MIN_FISHER else None), n
    cells: list[tuple[float | None, ...]] = []
    n_out: list[int] = []
    circular_cells: list[dict[str, Any]] = []
    position = 0
    for i in range(len(features)):
        for j in range(i, len(features)):
            if i in circular_rows or j in circular_rows:
                # An azimuth has no linear r (CLAUDE.md section 2): off the scale.
                keep = kept(i, j)
                n_out.append(int(keep.sum()))
                cells.append((None, None, None))
                circular_cells.append(_circular_cell(features, stack, azimuth_sums, keep,
                                                     row_set(i, j), i, j, position))
            else:
                r, n = pair(i, j)
                n_out.append(n)
                cells.append(_cell(r, n, i == j))
            position += 1
    n_class = int(mask.sum())
    view_notes = [
        f"Pearson r over the events of the class, each event one independent observation; "
        f"the 95% interval is Fisher's z with SE 1/√(N − 3), N = events. r is quoted from "
        f"N = {MIN_FISHER}, where that interval first exists; the diagonal is 1 by definition.",
        "An azimuth (avg_phi, avg_phi_circ) has no linear correlation: a Pearson r of it "
        "changes sign with where the ±π cut falls. Its cells are hatched with r empty and off "
        "the colour scale, and carry Mardia's circular–linear R with a linear feature, or the "
        "circular–circular r_c of the two azimuths (circular_cells). The notebook's linear r "
        "of avg_phi is kept there as parity_r, with no interval, for comparison only. "
        "angular_spread is hatched too: its linear SD of φ is inflated by the cut.",
        "Pearson r on features spanning many decades (the volume, both densities, the energy) "
        "stays dominated by their tails even with the floored events left out.",
    ]
    if exclude_eps:
        view_notes.append(
            f"Events with a floored width, height or depth ({int(floored.sum()):,} in this "
            "class) are left out of the pairs involving the volume or a density, the only "
            "values the floor corrupts; every other pair keeps them. exclude_eps=false "
            "reproduces the notebook.")
    return {
        "class": which,
        "class_label": cs.label_of(which),
        "n": n_class,
        "n_excluded_eps": int(floored.sum()) if exclude_eps else 0,
        "exclude_eps": exclude_eps,
        "eps_pair_features": list(catalog.EPS_PAIR_FEATURES) if exclude_eps else [],
        "order": [f.id for f in features],
        "layout": "upper triangle with the diagonal, row-major: (0,0), (0,1) … (0,k−1), (1,1) …",
        "r": [cell[0] for cell in cells],
        "lo": [cell[1] for cell in cells],
        "hi": [cell[2] for cell in cells],
        "n_pairs": n_out,
        "hatched": {f.id: catalog.HATCHED[f.id] for f in features if f.id in catalog.HATCHED},
        "circular_cells": circular_cells,
        "circular_measures": {k: typographic(v) for k, v in CIRCULAR_MEASURES.items()},
        "scale": dict(R_SCALE),
        "method": METHOD_FISHER,
        "interval": typographic("95% Fisher-z interval, N = events (iid)"),
        "thresholds": {"fisher": MIN_FISHER, "mardia_azimuths": jackknife.MIN_MARDIA_AZIMUTHS,
                       "mardia_groups": jackknife.MIN_MARDIA_GROUPS,
                       "jackknife_groups": jackknife.MIN_JACKKNIFE_GROUPS},
        "view_notes": [typographic(t) for t in view_notes],
    }
