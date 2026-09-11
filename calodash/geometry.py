"""Shower-local coordinate transform.

Raw coordinates sit in the global detector frame: the endcap front face is at
z = 3662.4 mm, not at zero, and a shower's transverse position is wherever the
particle happened to strike. CLAUDE.md section 5 and ``plan-viz.ipynb`` cell 3
both call for the shower's own frame, with the entrance plane at z' = 0.

Cell 3 fixes the entry point definition: *since particles never travel
backwards, the energy-deposition points with the smallest z coordinate are the
entry points into the detector*.

Two structural artifacts follow from that definition and are quantified here
rather than hidden, because both are properties of the transform rather than of
the physics:

Origin pinning
    76.5% of events have exactly one hit in their minimum-z layer. For those the
    energy-weighted centroid *is* that hit, so its shower-local position is
    exactly (0, 0). The single origin bin ends up holding roughly 17.6% of all
    hits. The dashboard exposes an "exclude entry layer" toggle so a reader can
    measure this directly.

Acceptance bias
    Only 91.2% of events enter at the front face. An event entering at global
    layer g can reach at most local layer 59 - g, so deep local layers are
    under-populated by acceptance rather than by shower physics. ``entry_layer``
    is carried to the client so the depth panels can normalise for it.

A note on what is *not* done here: the incident axis is never drawn by
extrapolating ``(theta, phi)`` from the origin. Back-projection shows theta
recovers well (r = 0.973) but phi carries a +0.684 rad offset that scales with
1/p -- solenoidal bending of a positive proton -- and straight-line pointing
misses the observed radius by 213 mm on average. The axis overlay is fitted from
the observed deposits instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constants import Z_PITCH_MM


@dataclass
class ShowerAxis:
    """Least-squares transverse drift of the shower centroid with depth."""

    slope_x: float
    slope_y: float
    depth_max_mm: float

    def endpoints(self) -> dict:
        return {
            "slopeX": self.slope_x,
            "slopeY": self.slope_y,
            "depthMax": self.depth_max_mm,
        }


def to_shower_frame(
    hits: pd.DataFrame, z_front_mm: float, pitch: float = Z_PITCH_MM
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add shower-local coordinates to ``hits`` and derive per-event geometry.

    Returns the augmented hit frame (with ``xl``, ``yl``, ``zl``) and an event
    frame indexed by ``event_number``.
    """
    frame = hits.copy()
    events = frame.groupby("event_number", sort=True)

    # Global sampling-layer index, used to identify the entry layer and to work
    # out how much detector each event had left in front of it.
    global_layer = np.rint((frame["z"].to_numpy() - z_front_mm) / pitch).astype(np.int64)
    frame["global_layer"] = global_layer

    entry_layer = frame.groupby("event_number")["global_layer"].transform("min")
    frame["depth_layer"] = frame["global_layer"] - entry_layer
    frame["zl"] = frame["depth_layer"].to_numpy() * pitch

    # Entry point: energy-weighted centroid of the entry layer only.
    in_entry = frame["global_layer"].to_numpy() == entry_layer.to_numpy()
    weight = np.where(in_entry, frame["energy"].to_numpy(), 0.0)
    frame["_w"] = weight
    frame["_wx"] = weight * frame["x"].to_numpy()
    frame["_wy"] = weight * frame["y"].to_numpy()

    grouped = frame.groupby("event_number", sort=True)
    w_sum = grouped["_w"].sum()
    cx = grouped["_wx"].sum() / w_sum
    cy = grouped["_wy"].sum() / w_sum

    frame["xl"] = frame["x"].to_numpy() - frame["event_number"].map(cx).to_numpy()
    frame["yl"] = frame["y"].to_numpy() - frame["event_number"].map(cy).to_numpy()
    frame = frame.drop(columns=["_w", "_wx", "_wy"])

    event_frame = pd.DataFrame(
        {
            "entry_layer": grouped["global_layer"].min(),
            "n_hits": grouped.size(),
            "entry_x": cx,
            "entry_y": cy,
        }
    )
    event_frame["front_face"] = event_frame["entry_layer"].to_numpy() == 0
    # Number of entry-layer hits, the direct measure of the origin-pinning
    # artifact: a value of 1 means that event contributes an exact (0, 0) hit.
    event_frame["entry_hits"] = (
        frame.loc[in_entry].groupby("event_number").size().reindex(event_frame.index, fill_value=0)
    )

    return frame, event_frame


def fit_shower_axis(hits: pd.DataFrame) -> ShowerAxis:
    """Fit the ensemble shower axis from observed deposits.

    Energy-weighted transverse centroid per depth layer, then a least-squares
    line through it weighted by the energy in each layer. Layers carrying
    negligible energy would otherwise dominate the fit through pure noise.
    """
    energy = hits["energy"].to_numpy()
    depth = hits["zl"].to_numpy()
    frame = pd.DataFrame(
        {
            "zl": depth,
            "w": energy,
            "wx": energy * hits["xl"].to_numpy(),
            "wy": energy * hits["yl"].to_numpy(),
        }
    )
    per_layer = frame.groupby("zl").sum()
    weight = per_layer["w"].to_numpy()
    usable = weight > 0
    if usable.sum() < 2:
        return ShowerAxis(0.0, 0.0, float(depth.max() if depth.size else 0.0))

    z = per_layer.index.to_numpy()[usable]
    w = weight[usable]
    mx = per_layer["wx"].to_numpy()[usable] / w
    my = per_layer["wy"].to_numpy()[usable] / w

    def weighted_slope(values: np.ndarray) -> float:
        z_mean = np.average(z, weights=w)
        v_mean = np.average(values, weights=w)
        denominator = np.sum(w * (z - z_mean) ** 2)
        if denominator <= 0:
            return 0.0
        return float(np.sum(w * (z - z_mean) * (values - v_mean)) / denominator)

    return ShowerAxis(
        slope_x=weighted_slope(mx),
        slope_y=weighted_slope(my),
        depth_max_mm=float(z.max()),
    )


def artifact_summary(hits: pd.DataFrame, events: pd.DataFrame) -> dict:
    """Quantify both structural artifacts, for display in the interface."""
    single_entry = int((events["entry_hits"].to_numpy() == 1).sum())
    n_events = len(events)
    origin_hits = int(((hits["xl"].to_numpy() == 0.0) & (hits["yl"].to_numpy() == 0.0)).sum())
    front_face = int(events["front_face"].to_numpy().sum())

    return {
        "singleEntryEvents": single_entry,
        "singleEntryFraction": single_entry / n_events if n_events else 0.0,
        "originHits": origin_hits,
        "originHitFraction": origin_hits / len(hits) if len(hits) else 0.0,
        "frontFaceEvents": front_face,
        "frontFaceFraction": front_face / n_events if n_events else 0.0,
    }
