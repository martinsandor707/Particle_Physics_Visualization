"""``GET /api/profiles`` - the longitudinal and radial shower profiles, C7 (Page 1).

One request serves both of the card's axes - depth (w along the incident
direction, or each shower's native layers) and transverse radius ρ - from the
ingest-time profile tables, so the response is a few hundred numbers whatever
the selection (``query/profiles.py``). The card is gated on the two panel ids
it fills, ``profile-w`` and ``profile-r``: an aggregated experiment has no hits
to profile, and an experiment derived before the profile tables existed is
refused with the rebuild it needs, never served an empty chart.

``depth_layers`` says how the depth axis is numbered for layer groups
("Longitudinal Channels"): ``depth=native`` is each shower's own relative
layers, served with the reach of every relative layer (``query/layer_profile.py``);
``depth=w`` is the Local frame's w, along which the tilted detector layers
have no common grid, so it carries no numbering.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..db.registry import ExperimentRecord
from ..models.common import ApiMeta, Timer, envelope
from ..query import density, layer_profile, profiles
from ..query import showers as showers_mod
from ..text import typographic
from .deps import CursorDep, FilterDep, capable

router = APIRouter()


@router.get("/api/profiles", summary="Longitudinal (w) and radial (ρ) energy profiles of the selected showers")
def get_profiles(
    con: CursorDep,
    record: Annotated[ExperimentRecord, capable("profile-w", "profile-r")],
    spec: FilterDep,
    shower: str = Query(
        "both",
        description=(
            "a | b | both: which showers are profiled. On two-shower data `both` pools A and B, "
            "with the event as the cluster of the envelope and the pooled interval; a "
            "single-shower experiment accepts `a` and `both`."
        ),
    ),
    depth: str = Query(
        "w",
        description=(
            "w: depth along each shower's incident direction (Local frame), bins of one layer "
            "pitch anchored at w = 0 | native: each shower's own layers kt counted from its "
            "first (per-shower translated frame, not rotated). The radial axis is served with "
            "either."
        ),
    ),
    notebook: bool = Query(
        False,
        description=(
            "Apply the notebook's convention: drop hits at z_local < −1e−6 mm from every bin "
            "and from each shower's normaliser. Defined along w, so only with depth=w."
        ),
    ),
):
    timer = Timer()
    body, query_ms, cached = profiles.profiles(con, record, spec, shower=shower, depth=depth,
                                               notebook=notebook)
    depth_block = _depth_layers(con, record, spec, shower, depth)
    warnings: list[str] = []
    if body["ensemble"]["n_showers"] == 0:
        warnings.append("No shower in the current selection has a profile.")

    def respond(extra: list[str]) -> dict:
        meta = ApiMeta(
            table_name=record.table_name, exact=True, query_ms=query_ms,
            total_ms=timer.elapsed_ms, cached=cached, warnings=[*warnings, *extra],
            notes={"shower": shower, "depth": depth, "notebook": notebook},
        )
        return envelope(meta, **body, depth_layers=depth_block, filter=spec.as_dict())

    # The bins are physical - a layer pitch, 10 mm of radius - over a
    # dataset-wide window, so there is nothing to coarsen: about 15 KB on
    # every selection. Measured as served all the same, and said if it misses.
    payload = respond([])
    size = density.wire_size(payload)
    if size >= density.RESPONSE_LIMIT:
        payload = respond([f"The profile response measured {size:,} bytes against the "
                           f"{density.RESPONSE_LIMIT:,}-byte contract and is served as it is."])
    return payload


def _depth_layers(con, record: ExperimentRecord, spec, shower: str, depth: str) -> dict:
    """C7's ``depth_layers``: relative numbering with the reach on native depth, none along w."""
    if depth == "native":
        bounds = record.frame_bounds
        n_layers = (int(bounds.n_layers_trans) if bounds is not None
                    else layer_profile.physical_layers(record))
        return {
            "numbering": layer_profile.NUMBERING_RELATIVE,
            "reach": layer_profile.reach(con, record, spec, n_layers, showers_mod.of(record, shower)),
            "note": typographic(
                "Relative layers kt + 1, counted from each shower's own first populated layer; the "
                "reach says how many of the selected showers have each relative layer inside the "
                "detector."
            ),
        }
    return {
        "numbering": layer_profile.NUMBERING_NONE,
        "reach": None,
        "note": typographic(
            "Depth w runs along each shower's own incident direction, so the detector layers are "
            "tilted by its (θ, φ) and spaced p / cos θ along w: the selected showers share no common "
            "layer grid on this axis, and no layer group is drawn on it."
        ),
    }
