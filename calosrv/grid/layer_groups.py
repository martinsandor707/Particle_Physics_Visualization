"""Longitudinal layer groups: a partition of the depth layers into 13 contiguous groups.

The interface calls them *Longitudinal Channels* ("Ch m", or "Rel Ch m" where
depth is counted from each shower's own first layer). In code, in the API and
in the hash they are *layer groups* (``depth_groups``, ``lgroups``), because
"channel" already names the five display channels (``planes.CHANNELS``).

**The partition.** ``counts`` is 13 positive integers summing to ``L``, the
experiment's lattice layer count (``lattice.z.n``: 60 on production, 56 on
the demonstration file, whose lattice skips four unpopulated layers). Group
``m`` holds the layers ``b_{m-1} + 1 .. b_m``, with ``b_m`` the cumulative sums
and ``b_13 = L``. The wire form joins the counts with ``.``.

**Geometry is stored, never multiplied.** A depth axis of a response has its
own native bins and stored edges (the lattice's cell edges in the absolute
frame, ``(k - 1/2) p`` in the co-registered ones). A group's span on it is the
stored edge at its first bin and the stored edge after its last bin, so a seam
is never an index times a pitch. The last group always runs to the end of the
axis, which matters where an axis has more bins than ``L`` (the per-shower
translated frame on a lattice that skips layers); a group wholly beyond the
axis is dropped and reported.

**Pooling.** :func:`pooled_operator` builds the sparse depth operator that maps
the native bins onto the groups, the same kind of matrix the panels already
apply (``splat.build_axis_operator``, ``reconstruct.AxisMap``). Each native bin
lies wholly inside one group, so the operator is an exact area-weighted
overlap and every weight is non-negative:

* *co-registered densities* (GeV mm⁻² per event): weight 1, so a group bin
  holds the group's energy, and dividing by its own area gives the
  width-weighted mean of its layers' densities;
* *absolute-frame bins* (GeV per bin): weight ``p / ΔZ_m``, the group's sum in
  GeV per layer pitch ``p`` - again a weighted mean of the layers' values
  ``E_k p / w_k``, each at most ``E_k`` because no layer cell is narrower than
  the pitch.

Either way a displayed group bin is a weighted mean of native bins and never
exceeds the native per-layer peak, and the energy is conserved:
``Σ_m value_m ΔZ_m / p = Σ_k E_k`` in the absolute frame, ``Σ_m ρ_m ΔZ_m =
Σ_k ρ_k w_k`` in the co-registered ones. Ratio channels pool numerator and
denominator with the same operator; Shap-CAM's signed parts are pooled apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..errors import ValidationError

#: How many groups a partition has.
GROUP_COUNT = 13

#: The request field every refusal names.
FIELD = "depth_groups"

#: Separator of the wire and hash form.
SEPARATOR = "."

_WIRE = re.compile(r"^\s*\d+(\s*\.\s*\d+)*\s*$")

#: How a co-registered depth axis is pooled, and how an absolute-frame one is.
WEIGHT_OVERLAP = "overlap"
WEIGHT_PER_PITCH = "per_pitch"


# ------------------------------------------------------------- partitions --


def uniform_counts(n_layers: int) -> tuple[int, ...]:
    """The uniform partition of ``n_layers``: ``n = 13 q + r`` gives ``r`` groups of ``q + 1`` first, then ``q``.

    60 layers give eight groups of 5 and five of 4; 56 give four of 5 and nine of 4.
    """
    n = int(n_layers)
    if n < GROUP_COUNT:
        raise ValidationError(
            f"A partition into {GROUP_COUNT} layer groups needs at least {GROUP_COUNT} layers; "
            f"this depth axis has {n}.",
            field=FIELD,
        )
    q, r = divmod(n, GROUP_COUNT)
    return tuple([q + 1] * r + [q] * (GROUP_COUNT - r))


def parse_counts(text: str, n_layers: int) -> tuple[int, ...]:
    """The 13 group sizes of ``text`` (``5.5.5.5.5.5.5.5.4.4.4.4.4``), validated against ``n_layers``.

    Refused (422, ``field="depth_groups"``) when malformed, not exactly 13
    integers, any below 1, or summing to anything but ``n_layers``.
    """
    raw = "" if text is None else str(text)
    if not _WIRE.match(raw):
        raise ValidationError(
            f"depth_groups must be {GROUP_COUNT} positive integers joined by '{SEPARATOR}' "
            f"(e.g. {format_counts(uniform_counts(max(int(n_layers), GROUP_COUNT)))}); got {raw!r}.",
            field=FIELD,
        )
    counts = tuple(int(part) for part in raw.split(SEPARATOR))
    if len(counts) != GROUP_COUNT:
        raise ValidationError(
            f"depth_groups must hold exactly {GROUP_COUNT} group sizes; got {len(counts)}.",
            field=FIELD,
        )
    small = [m + 1 for m, c in enumerate(counts) if c < 1]
    if small:
        raise ValidationError(
            "Every layer group must hold at least one layer; group(s) "
            f"{', '.join(str(m) for m in small)} hold none.",
            field=FIELD,
        )
    total = sum(counts)
    if total != int(n_layers):
        raise ValidationError(
            f"depth_groups must sum to this experiment's {int(n_layers)} layers; the sizes sum to {total}.",
            field=FIELD,
        )
    return counts


def format_counts(counts: Any) -> str:
    """The wire form: the counts joined by ``.``."""
    return SEPARATOR.join(str(int(c)) for c in counts)


def boundaries(counts: Any) -> tuple[int, ...]:
    """``b_m``, the last layer (1-based) of each group: the cumulative sums, ``b_13 = L``."""
    out, total = [], 0
    for c in counts:
        total += int(c)
        out.append(total)
    return tuple(out)


# ------------------------------------------------------------- on an axis --


@dataclass(frozen=True)
class GroupBins:
    """One group's native bins on one depth axis: ``start`` inclusive, ``stop`` exclusive (0-based)."""

    group: int
    start: int
    stop: int
    #: The axis cut the group short (it ran past the end), or stretched it (the last group).
    partial: bool = False

    @property
    def n(self) -> int:
        return self.stop - self.start

    def as_dict(self, first_layer: int = 1) -> dict[str, Any]:
        """``first`` and ``last`` in the axis's own 1-based numbering."""
        return {"group": self.group, "first": self.start + first_layer,
                "last": self.stop - 1 + first_layer}


def group_bins(counts: Any, n_bins: int) -> tuple[tuple[GroupBins, ...], tuple[int, ...]]:
    """The groups' bins on an axis of ``n_bins`` native bins, and the groups wholly beyond it.

    Group 13 always runs to ``n_bins``; any other group is clipped at the end
    of the axis, and one that starts past it is dropped and reported.
    """
    n = int(n_bins)
    ends = boundaries(counts)
    kept: list[GroupBins] = []
    beyond: list[int] = []
    start = 0
    for m, end in enumerate(ends, start=1):
        last = m == len(ends)
        if start >= n:
            beyond.append(m)
            start = end
            continue
        stop = n if last else min(end, n)
        kept.append(GroupBins(m, start, stop, partial=stop != end))
        start = end
    return tuple(kept), tuple(beyond)


def pooled_edges(src_edges: Any, bins: tuple[GroupBins, ...]) -> np.ndarray:
    """The groups' edges: the stored source edges at the group boundaries, never a pitch product."""
    src = np.asarray(src_edges, dtype=np.float64)
    if not bins:
        return src[:1].copy()
    picks = [bins[0].start, *(b.stop for b in bins)]
    return src[np.asarray(picks, dtype=np.intp)]


@dataclass(frozen=True)
class PooledAxis:
    """The pooled depth axis: the operator, the group edges and what was cut.

    ``op`` is ``(n_groups_on_axis, n_src)``, applied exactly as an overlap
    operator of ``splat`` (``splat.resample``: ``M @ op.T`` on a column axis).
    ``src_slice`` is the native bins the groups cover, which with ``op`` and
    ``dst_edges`` is what a ``reconstruct.AxisMap`` holds.
    """

    op: np.ndarray
    dst_edges: np.ndarray
    src_edges: np.ndarray
    bins: tuple[GroupBins, ...]
    beyond: tuple[int, ...]
    counts: tuple[int, ...]
    weighting: str
    pitch_mm: float | None = None

    @property
    def n_dst(self) -> int:
        return int(self.dst_edges.size - 1)

    @property
    def src_slice(self) -> slice:
        return slice(0, int(self.src_edges.size - 1))

    @property
    def widths(self) -> np.ndarray:
        return np.diff(self.dst_edges)

    def energy_weights(self) -> np.ndarray:
        """Per group bin, what turns its value back into the energy it holds.

        ``ΔZ_m / p`` for absolute-frame bins (GeV per pitch), 1 for an overlap
        sum; the co-registered renderer divides by the area itself.
        """
        if self.weighting == WEIGHT_PER_PITCH and self.pitch_mm:
            return self.widths / float(self.pitch_mm)
        return np.ones(self.n_dst, dtype=np.float64)

    def groups_block(self, first_layer: int = 1, pooled: bool = True) -> dict[str, Any]:
        """The response's ``depth_layers.groups``."""
        return {
            "counts": [int(c) for c in self.counts],
            "pooled": bool(pooled),
            "bins": [b.as_dict(first_layer) for b in self.bins],
            "beyond_axis": [int(m) for m in self.beyond],
        }


def pooled_operator(
    src_edges: Any, counts: Any, *, pitch_mm: float | None = None,
) -> PooledAxis:
    """The sparse depth operator pooling the native bins of ``src_edges`` into the groups of ``counts``.

    Without ``pitch_mm`` the weights are the exact area-weighted overlap, 1 for
    every bin inside its group (co-registered densities, divided by the group
    bin's own area afterwards). With it, the absolute frame's ``p / ΔZ_m``: the
    group's sum in GeV per layer pitch.
    """
    src = np.asarray(src_edges, dtype=np.float64)
    n_src = int(src.size - 1)
    if n_src < 1:
        raise ValueError("a depth axis needs at least one bin to pool")
    counts = tuple(int(c) for c in counts)
    bins, beyond = group_bins(counts, n_src)
    dst = pooled_edges(src, bins)
    op = np.zeros((len(bins), n_src), dtype=np.float64)
    for row, b in enumerate(bins):
        op[row, b.start:b.stop] = 1.0
    weighting = WEIGHT_OVERLAP
    if pitch_mm is not None:
        weighting = WEIGHT_PER_PITCH
        width = np.diff(dst)
        scale = np.divide(float(pitch_mm), width, out=np.zeros_like(width), where=width > 0)
        op *= scale[:, None]
    return PooledAxis(op=op, dst_edges=dst, src_edges=src, bins=bins, beyond=beyond,
                      counts=counts, weighting=weighting,
                      pitch_mm=None if pitch_mm is None else float(pitch_mm))


# ------------------------------------------------------------ the layers --


def physical_layers(z_lo: float, z_hi: float, pitch_mm: float) -> int:
    """``L_phys``: the detector's layer slots from the first to the last lattice layer.

    ``round((hi - lo) / p) + 1``: 60 on production; 58 on the demonstration
    lattice, whose 56 populated layers run from 3662.4 to 4830.9 mm.
    """
    if not pitch_mm or pitch_mm <= 0:
        return 0
    return int(round((float(z_hi) - float(z_lo)) / float(pitch_mm))) + 1


def start_layer(p0_z: float, z_lo: float, pitch_mm: float) -> int:
    """``s``: a shower's first populated layer as a 0-based physical layer, ``round((p0z - lo) / p)``."""
    return int(round((float(p0_z) - float(z_lo)) / float(pitch_mm)))


def contiguous(coords: Any, pitch_mm: float) -> bool:
    """Whether the layers step by exactly one pitch: false where the lattice skips a layer."""
    c = np.asarray(coords, dtype=np.float64)
    if c.size < 2 or not pitch_mm:
        return True
    return bool(np.allclose(np.diff(c), float(pitch_mm), rtol=0.0, atol=2e-3))


def half_pitch_edges(n: int, pitch_mm: float) -> np.ndarray:
    """``(k - 1/2) p`` for ``k = 0 .. n``: the relative layers' seams along their normal."""
    return (np.arange(int(n) + 1, dtype=np.float64) - 0.5) * float(pitch_mm)


def layer_normal(rotation: Any | None = None) -> np.ndarray:
    """The detector layer planes' unit normal in a frame whose hits were rotated by ``rotation``.

    ``rotation @ ê_z``, the matrix's third column: for ``grid/frame.py``'s
    ``rotation_matrix(θ, φ) = R_y(θ) R_z(φ)`` it is ``(−sin θ, 0, cos θ)`` for
    every φ, because ``R_z`` fixes ê_z. ``None`` (a frame that does not rotate)
    is ê_z itself.
    """
    if rotation is None:
        return np.array([0.0, 0.0, 1.0])
    r = np.asarray(rotation, dtype=np.float64)
    return r @ np.array([0.0, 0.0, 1.0])
