"""The measurement planes every bundle carries, and the channels read from them.

A bundle - laboratory, canonical, translated or local - holds, per panel bin,
nine additive sums over the selected hits of one network in one frame:

=========== ================================ =============================
plane       sum over the bin's hits          read by
=========== ================================ =============================
``e``       E                                density, every ratio's energy weight
``n``       1                                count-weighted means
``efa_true``E * f_A(true)                    truth-voxel centroids, shower axes
``efa_pred``E * f_A(pred)                    predicted-voxel centroids
``eg``      E * GradCAM                      Grad-CAM mean (energy weight), E x Grad-CAM
``g``       GradCAM                          Grad-CAM mean (count weight)
``esp``     E * max(ShapCAM, 0)              Shap-CAM mean, E x Shap-CAM (positive part)
``esn``     E * min(ShapCAM, 0)              Shap-CAM mean, E x Shap-CAM (negative part)
``s``       ShapCAM                          Shap-CAM mean (count weight)
=========== ================================ =============================

Every plane is a plain sum, so every one resamples through the same
conservative operators and survives a Bernoulli preview sample by the same
scale factor. Keeping the positive and negative Shap-CAM parts apart means
each is conserved on its own through any resampling; their sum is the signed
field.

``f_A`` always comes from the frame's *segmentation* network, whatever network
the CAM columns belong to: only segmentation predicts where the energy went.
The column names come from :mod:`calosrv.db.ddl`'s allowlisted builders; a
request string never reaches the SQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import ddl

PLANES: tuple[str, ...] = ("e", "n", "efa_true", "efa_pred", "eg", "g", "esp", "esn", "s")

CHANNEL_DENSITY = "density"
CHANNEL_GRADCAM = "gradcam"
CHANNEL_GRADCAM_ENERGY = "gradcam_energy"
CHANNEL_SHAPCAM = "shapcam"
CHANNEL_SHAPCAM_ENERGY = "shapcam_energy"
CHANNELS: tuple[str, ...] = (
    CHANNEL_DENSITY, CHANNEL_GRADCAM, CHANNEL_GRADCAM_ENERGY,
    CHANNEL_SHAPCAM, CHANNEL_SHAPCAM_ENERGY,
)

WEIGHTING_ENERGY = "energy"
WEIGHTING_COUNT = "count"
WEIGHTINGS = (WEIGHTING_ENERGY, WEIGHTING_COUNT)

#: How each channel is formed from the planes.
KIND_EXTENSIVE = "extensive"   # a sum: density, E x CAM
KIND_RATIO = "ratio"           # a weighted mean: numerator / denominator
KIND_SIGNED = "signed"         # a signed sum: E x Shap-CAM


@dataclass(frozen=True)
class ChannelView:
    """Which planes a channel reads and how it combines them."""

    channel: str
    kind: str
    numerator: tuple[str, ...]      # summed
    denominator: str | None = None  # ratio channels only
    cam: str | None = None          # 'gradcam' | 'shapcam' | None (density)

    @property
    def is_cam(self) -> bool:
        return self.cam is not None


def view(channel: str, weighting: str = WEIGHTING_ENERGY) -> ChannelView:
    """The planes of ``channel``; ``weighting`` chooses the ratio channels' weights."""
    count = weighting == WEIGHTING_COUNT
    if channel == CHANNEL_DENSITY:
        return ChannelView(channel, KIND_EXTENSIVE, ("e",))
    if channel == CHANNEL_GRADCAM:
        return ChannelView(channel, KIND_RATIO, ("g",) if count else ("eg",),
                           "n" if count else "e", cam="gradcam")
    if channel == CHANNEL_SHAPCAM:
        return ChannelView(channel, KIND_RATIO, ("s",) if count else ("esp", "esn"),
                           "n" if count else "e", cam="shapcam")
    if channel == CHANNEL_GRADCAM_ENERGY:
        return ChannelView(channel, KIND_EXTENSIVE, ("eg",), cam="gradcam")
    if channel == CHANNEL_SHAPCAM_ENERGY:
        return ChannelView(channel, KIND_SIGNED, ("esp", "esn"), cam="shapcam")
    raise ValueError(f"unknown channel {channel!r}")


def measures(coord_system: str, model: str) -> tuple[tuple[str, str | None], ...]:
    """``(plane, SQL sum argument)`` per plane; ``None`` means ``count(*)``.

    ``coord_system`` selects the network frame (``lab`` means the
    absolute-frame networks, which the canonical frame uses too).
    """
    gc = ddl.cam_column(model, coord_system, "gradcam")
    sc = ddl.cam_column(model, coord_system, "shapcam")
    fa_true = ddl.seg_column("true", coord_system)
    fa_pred = ddl.seg_column("pred", coord_system)
    return (
        ("e", "energy"),
        ("n", None),
        ("efa_true", f"energy * CAST({fa_true} AS DOUBLE)"),
        ("efa_pred", f"energy * CAST({fa_pred} AS DOUBLE)"),
        ("eg", f"energy * CAST({gc} AS DOUBLE)"),
        ("g", f"CAST({gc} AS DOUBLE)"),
        ("esp", f"energy * greatest(CAST({sc} AS DOUBLE), 0.0)"),
        ("esn", f"energy * least(CAST({sc} AS DOUBLE), 0.0)"),
        ("s", f"CAST({sc} AS DOUBLE)"),
    )


def cam_note(model: str, coord_system: str, channel: str) -> dict | None:
    """What a CAM channel reads, for ``meta.cam`` and the captions."""
    v = view(channel)
    if not v.is_cam:
        return None
    frame = ddl.NETWORK_FRAME[coord_system]
    per = "event" if model == "segmentation" else "shower"
    aggregation = {
        CHANNEL_GRADCAM: "mean over the bin's hits, weighted by energy (or by count)",
        CHANNEL_SHAPCAM: "mean over the bin's hits, weighted by energy (or by count)",
        CHANNEL_GRADCAM_ENERGY: "sum over the bin's hits of E x Grad-CAM",
        CHANNEL_SHAPCAM_ENERGY: "sum over the bin's hits of E x Shap-CAM (signed)",
    }[channel]
    return {
        "column": ddl.csv_model_column(model, frame, v.cam),
        "model": model,
        "network_frame": frame,
        "normalisation": per,
        "aggregation": aggregation,
        "note": (
            f"The {model} network's {v.cam.replace('cam', '-CAM').replace('grad', 'Grad').replace('shap', 'Shap')} "
            f"maps are normalised per {per}, so an ensemble "
            + ("sum" if v.kind != KIND_RATIO else "mean")
            + " over many events mixes independently normalised maps: it shows where "
            "the network attends, not how strongly one event's attention compares with "
            "another's."
        ),
    }
