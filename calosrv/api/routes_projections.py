"""``GET /api/projections`` - the three spatial panels.

The frontend never receives raw hit rows. What it gets is three quantised
rasters plus the constants needed to read physical values back out of them,
which for the native lattice is around 35 KB in total.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..grid.resolution import (
    DEFAULT_RESOLUTION,
    DISPLAY_MODES,
    MAX_RESOLUTION,
    MIN_RESOLUTION,
    MODE_NATIVE,
    plan_resolution,
)
from ..encode.scale import SCALE_MODES, MODE_DECADES
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..query import cache as cache_mod
from ..query import centroids, panels, projections, sampling
from ..query import stagger as stagger_mod
from ..query import summary
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
            "native: one bin per real calorimeter cell (hardware truth). "
            "continuous: uniform grid at resolution R, built by area-weighted "
            "voxel splatting."
        ),
    ),
    mode: str = Query(
        panels.CHANNEL_DENSITY,
        description="density (summed energy) or gradcam (model attention).",
    ),
    weighting: str = Query(
        panels.WEIGHTING_ENERGY,
        description=(
            "How Grad-CAM attention is averaged per cell. energy-weighted by "
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
):
    timer = Timer()

    if display not in DISPLAY_MODES:
        raise ValidationError(
            f"display must be one of {', '.join(DISPLAY_MODES)}; got {display!r}.",
            field="display",
        )
    if mode not in panels.CHANNELS:
        raise ValidationError(
            f"mode must be one of {', '.join(panels.CHANNELS)}; got {mode!r}.",
            field="mode",
        )
    if weighting not in panels.WEIGHTINGS:
        raise ValidationError(
            f"weighting must be one of {', '.join(panels.WEIGHTINGS)}.",
            field="weighting",
        )
    if scale_mode not in SCALE_MODES:
        raise ValidationError(
            f"scale_mode must be one of {', '.join(SCALE_MODES)}.",
            field="scale_mode",
        )

    decision = sampling.decide(record, preview, settings.sample_percent)
    plan = plan_resolution(record.lattice, display, resolution)

    cache = cache_mod.get_cache(settings.cache_entries)
    key = (*spec.cache_key(), decision.sampled)

    def compute():
        bundle = projections.fetch_native(con, record, spec, sampled=decision.sampled)
        if decision.sampled:
            projections.scale_sample(bundle, decision.percent)
        return bundle

    bundle, was_cached = cache.get_or_compute(key, compute)

    rendered = panels.render_all(
        bundle,
        plan,
        channel=mode,
        weighting=weighting,
        global_vmax=record.cell_e_max,
        lock_scale=lock_scale,
        scale_mode=scale_mode,
    )

    centroid_sets = {k: v.as_dict() for k, v in centroids.compute(bundle).items()}
    selection = summary.summarise(con, record, spec)
    centroid_sets["truth_dataset"] = selection.as_dict()["centroid_dataset"]

    # One bin per cell keeps every 1-D bin populated, but the XY panel is a
    # product of two axes and the populated (x, y) pairs are not the full
    # product on a staggered detector. Measure it and say so rather than let a
    # geometric comb be read as shower structure.
    stagger = stagger_mod.detect(bundle.xy.planes["e"])

    warnings = list(plan.warnings)
    if decision.sampled:
        warnings.append(decision.reason)
    if stagger.staggered and plan.mode == MODE_NATIVE:
        warnings.append(stagger.note)
    if selection.n_events_no_d and not spec.include_undefined_d:
        warnings.append(
            f"{selection.n_events_no_d:,} selected event(s) have no defined A-B "
            "separation and are excluded."
        )

    meta = ApiMeta(
        table_name=record.table_name,
        exact=bundle.exact,
        query_ms=bundle.query_ms,
        total_ms=timer.elapsed_ms,
        cached=was_cached,
        warnings=warnings,
        notes={
            "resolution": plan.as_dict(),
            "channel": mode,
            "weighting": weighting,
            "stagger": stagger.as_dict(),
            "cache": cache.info(),
        },
    )

    return envelope(
        meta,
        panels=rendered,
        centroids=centroid_sets,
        selection=selection.as_dict(),
        filter=spec.as_dict(),
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
