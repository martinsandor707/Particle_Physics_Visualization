"""``GET /api/projections`` - the three spatial panels.

The frontend never receives raw hit rows. What it gets is three quantised
rasters plus the constants needed to read physical values back out of them,
which for the native lattice is around 35 KB in total.
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Query

from ..grid.resolution import (
    DEFAULT_RESOLUTION,
    DISPLAY_MODES,
    MAX_RESOLUTION,
    MIN_RESOLUTION,
    MODE_NATIVE,
    plan_resolution,
)
from ..db import ddl
from ..encode.scale import SCALE_MODES, MODE_DECADES
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import cache as cache_mod
from ..query import centroids, density, panels, planes, projections, sampling
from ..query import stagger as stagger_mod
from ..query import summary
from . import frame_canonical
from .deps import CursorDep, FilterDep, RecordDep, SettingsDep

router = APIRouter()


@router.get("/api/projections", summary="Pre-aggregated XY, YZ and XZ projections")
def get_projections(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    settings: SettingsDep,
    resolution: int = Query(
        DEFAULT_RESOLUTION,
        ge=MIN_RESOLUTION,
        le=MAX_RESOLUTION,
        description="Destination grid fineness R, used in continuous mode only.",
    ),
    display: str = Query(
        MODE_NATIVE,
        description=(
            "native: one bin per real calorimeter cell (hardware truth); in a "
            "co-registered frame, the raw 20 mm accumulation bins (the audit view). "
            "continuous: in the lab frame, a uniform grid at resolution R built by "
            "area-weighted voxel splatting; in a co-registered frame, a conservative "
            "kernel reconstruction of the transverse axes only (Gaussian σ = 10 mm "
            "below 50 events, bilinear tent from 50), depth never smoothed. The "
            "default is native everywhere; the interface always sends it explicitly."
        ),
    ),
    coord_system: str = Query(
        "lab",
        description=(
            "lab: detector coordinates (default). trans: every hit shifted by its own "
            "shower's entry point P0, no rotation. local: translated, then rotated by "
            "the shower's own R(theta, phi). Also selects which network's CAM columns "
            "are read (lab uses the absolute-frame networks)."
        ),
    ),
    model: str = Query(
        "segmentation",
        description="angle | energy | segmentation: the network whose CAM maps are shown.",
    ),
    channel: str | None = Query(
        None,
        description=(
            "density (default), gradcam, gradcam_energy (sum of E x Grad-CAM), shapcam "
            "(signed), shapcam_energy (sum of E x Shap-CAM, signed)."
        ),
    ),
    mode: str | None = Query(
        None,
        description="Deprecated alias of channel, kept for existing links.",
    ),
    weighting: str = Query(
        panels.WEIGHTING_ENERGY,
        description=(
            "How a mean CAM channel is averaged per cell. energy-weighted by "
            "default; count-weighted is dominated by sub-femto-GeV dust hits."
        ),
    ),
    scale_mode: str = Query(MODE_DECADES, description="decades | percentile | fixed"),
    lock_scale: bool = Query(
        True,
        description=(
            "Anchor the colour ramp to the experiment's global maximum so that "
            "moving a slider changes the image rather than the scale."
        ),
    ),
    preview: bool = Query(
        False,
        description=(
            "Serve from the 10% unbiased sample for drag preview. The response "
            "is marked exact=false."
        ),
    ),
    frame: str = Query(
        frame_canonical.FRAME_LAB,
        description=(
            "lab: detector coordinates (default). canonical: every selected event "
            "is co-registered by a rigid-body motion into the centre-of-separation "
            "frame (shower entry points at ∓D_entry/2 on x′, front face at z′ = 0) "
            "and the panels show the ensemble-averaged energy density. Requires "
            "coord_system=lab: the canonical frame is built from laboratory coordinates."
        ),
    ),
    rho_norm: str = Query(
        density.NORM_SELECTION,
        description=(
            "Co-registered frames only. selection: colours relative to this "
            "selection's peak density. dataset: relative to the whole experiment's "
            "peak, so colours are comparable across selections. The reference is "
            "always reported in GeV/mm^2/event."
        ),
    ),
):
    timer = Timer()

    if channel is not None and mode is not None and channel != mode:
        raise ValidationError(
            f"channel={channel!r} and the deprecated mode={mode!r} disagree; send channel only.",
            field="channel",
        )
    channel = channel or mode or panels.CHANNEL_DENSITY

    for name, value, allowed in (
        ("frame", frame, frame_canonical.FRAMES),
        ("coord_system", coord_system, ddl.COORD_SYSTEMS),
        ("model", model, ddl.MODELS),
        ("channel", channel, panels.CHANNELS),
        ("rho_norm", rho_norm, density.NORMS),
        ("display", display, DISPLAY_MODES),
        ("weighting", weighting, panels.WEIGHTINGS),
        ("scale_mode", scale_mode, SCALE_MODES),
    ):
        if value not in allowed:
            raise ValidationError(
                f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name,
            )
    if frame == frame_canonical.FRAME_CANONICAL and coord_system != "lab":
        raise ValidationError(
            "frame=canonical is built from laboratory coordinates; it requires "
            f"coord_system=lab, not {coord_system!r}.",
            field="coord_system",
        )

    if coord_system != "lab":
        from . import frame_shower

        return frame_shower.build_response(
            con, record, spec, settings, kind=coord_system,
            resolution=resolution, display=display, channel=channel, model=model,
            weighting=weighting, rho_norm=rho_norm, preview=preview, timer=timer,
            lock_scale=lock_scale, scale_mode=scale_mode,
        )

    if frame == frame_canonical.FRAME_CANONICAL:
        # `lock_scale` and `scale_mode` are lab-frame ramp controls; the
        # canonical ramp is relative to a stated reference chosen by rho_norm.
        return frame_canonical.build_response(
            con, record, spec, settings,
            resolution=resolution, display=display, channel=channel,
            weighting=weighting, rho_norm=rho_norm, preview=preview, timer=timer,
            lock_scale=lock_scale, scale_mode=scale_mode, model=model,
        )

    decision = sampling.decide(record, preview, settings.sample_percent)
    plan = plan_resolution(record.lattice, display, resolution)

    cache = cache_mod.get_cache(settings.cache_entries)
    base = (*spec.cache_key(), decision.sampled)

    def compute():
        bundle = projections.fetch_native(
            con, record, spec, sampled=decision.sampled, model=model
        )
        if decision.sampled:
            projections.scale_sample(bundle, decision.percent)
        return bundle

    bundle = None
    was_cached = False
    if channel == panels.CHANNEL_DENSITY:
        # Density reads no CAM plane, so any network's bundle of this selection serves it.
        bundle = cache.get_any([(*base, m) for m in (model, *ddl.MODELS) ])
        was_cached = bundle is not None
    if bundle is None:
        bundle, was_cached = cache.get_or_compute((*base, model), compute)

    centroid_sets = {k: v.as_dict() for k, v in centroids.compute(bundle).items()}
    selection = summary.summarise(con, record, spec)
    centroid_sets["truth_dataset"] = selection.as_dict()["centroid_dataset"]

    # One bin per cell keeps every 1-D bin populated, but the XY panel is a
    # product of two axes and the populated (x, y) pairs are not the full
    # product on a staggered detector. Measure it and say so rather than let a
    # geometric comb be read as shower structure.
    stagger = stagger_mod.detect(bundle.xy.planes["e"])

    # Only transient, actionable messages reach the banner. The persistent
    # explanatory notices - the staggered-lattice comb, the resolution plan's
    # caveats, the undefined-D exclusion - are delivered in `meta` and rendered
    # as info popovers beside the control they concern, so they stop consuming
    # the top of the plot area on every request.
    warnings: list[str] = []
    if decision.sampled:
        warnings.append(decision.reason)

    # Depth-panel direction overlays. The measured axes are always valid; the
    # per-event trajectories are only drawn when few enough to read, because
    # incident azimuth does not average (see summary.angular_coherence).
    coherence = summary.angular_coherence(con, record, spec)
    few_events = 0 < selection.n_events <= summary.MAX_TRAJECTORY_EVENTS

    # The two overlays are complements, not layers, and only one is honest at a
    # time. Individual trajectories are exact but unreadable in bulk. The
    # measured axis is an *ensemble* centroid per depth layer: with thousands of
    # events it converges on where the beam actually sits, but across a handful
    # of showers that are in different places it averages positions that have no
    # common centre and wanders the full width of the detector. So below the
    # trajectory threshold the individual lines are drawn and the ensemble axis
    # is withheld; above it, the reverse.
    paths = summary.trajectories(con, record, spec) if few_events else []
    axes = (
        {}
        if few_events
        else {name: panels.shower_axes(bundle, name) for name in ("yz", "xz")}
    )
    cam = planes.cam_note(model, "lab", channel)

    def assemble(plan_used, rendered, budget_notes: list[str]) -> dict:
        notices: list[dict[str, str]] = []
        for note in plan_used.warnings:
            notices.append({"scope": "resolution", "text": note})
        for note in budget_notes:
            notices.append({"scope": "resolution", "text": note})
        if stagger.staggered and plan_used.mode == MODE_NATIVE:
            notices.append({"scope": "resolution", "text": stagger.note})
        if selection.n_events_no_d and not spec.include_undefined_d:
            notices.append({
                "scope": "separation",
                "text": (
                    f"{selection.n_events_no_d:,} selected event(s) have no defined "
                    "A-B separation and are excluded."
                ),
            })
        if cam is not None:
            notices.append({"scope": "channel", "text": cam["note"]})
        notes = {
            "frame": frame_canonical.FRAME_LAB,
            "coord_system": "lab",
            "model": model,
            "resolution": plan_used.as_dict(),
            "channel": channel,
            "weighting": weighting,
            "sample_percent": decision.percent if decision.sampled else 100.0,
            "stagger": stagger.as_dict(),
            "notices": notices,
            "cache": cache.info(),
        }
        if cam is not None:
            notes["cam"] = cam
        meta = ApiMeta(
            table_name=record.table_name,
            exact=bundle.exact,
            query_ms=bundle.query_ms,
            total_ms=timer.elapsed_ms,
            cached=was_cached,
            warnings=warnings,
            notes=notes,
        )
        return envelope(
            meta,
            panels=rendered,
            centroids=centroid_sets,
            selection=selection.as_dict(),
            filter=spec.as_dict(),
            overlays={
                "axes": axes,
                "trajectories": paths,
                "coherence": coherence,
                "max_trajectory_events": summary.MAX_TRAJECTORY_EVENTS,
            },
            slab={
                "mm": record.lattice.slab_mm,
                "layers": record.lattice.slab_iz + 1,
                "z_front": record.lattice.z.lo,
                "note": (
                    "The XY panel sums the entrance slab: the first "
                    f"{record.lattice.slab_iz + 1} sampling layers, "
                    f"{record.lattice.slab_mm:.0f} mm from the front face at "
                    f"z = {record.lattice.z.lo:.1f} mm."
                ),
            },
        )

    def render(plan_used):
        return panels.render_all(
            bundle,
            plan_used,
            channel=channel,
            weighting=weighting,
            global_vmax=record.cell_e_max,
            lock_scale=lock_scale,
            scale_mode=scale_mode,
        )

    body = assemble(plan, render(plan), [])
    size = density.wire_size(body)
    if size < density.RESPONSE_LIMIT or plan.mode == MODE_NATIVE:
        if size >= density.RESPONSE_LIMIT:
            # The native lattice is the hardware truth and has no coarser form;
            # it is served as measured, and says so.
            body = assemble(plan, render(plan), [
                f"The native-lattice response measured {size:,} bytes against the "
                f"{density.RESPONSE_LIMIT:,}-byte contract and is served as it is."
            ])
        return body

    # Continuous display over the contract: lower R along the guard's own
    # sequence, re-rendering from the cached bundle and measuring each candidate
    # exactly as it is served, and disclose every step.
    notes: list[str] = []
    r = plan.r_x
    for _attempt in range(density.MAX_ATTEMPTS):
        new_r = density.next_resolution(r, resolution)
        if new_r == r:
            break
        notes.append(
            f"Resolution lowered from R = {r} to R = {new_r} to keep the response under "
            f"the 100 KB contract ({size:,} bytes at R = {r})."
        )
        r = new_r
        candidate = dataclasses.replace(
            plan_resolution(record.lattice, display, r), requested=resolution
        )
        body = assemble(candidate, render(candidate), list(notes))
        size = density.wire_size(body)
        if size < density.RESPONSE_LIMIT:
            return body
    return assemble(candidate, render(candidate), [
        *notes, f"The response is still {size:,} bytes at R = {r} and is served as it is."
    ])
