"""Assemble the ``frame=canonical`` response of ``GET /api/projections``.

Kept beside the route rather than inside it so the laboratory-frame path in
``routes_projections.py`` stays exactly as it was. The canonical envelope keeps
every top-level key and shape of the lab envelope - ``meta``, ``panels``,
``centroids``, ``selection``, ``filter``, ``overlays``, ``slab`` - so the
frontend reads it with the same code, and adds a ``frame`` block describing the
co-registration: anchors, window, footprint, sub-sampling, the measured comb,
the density reference, and every count that was excluded or clipped.

One deliberate difference: ``centroids.truth_dataset`` (the lab-frame mean of
the dataset centroids) is omitted, because averaging positions across events
that sit in different places is exactly what this frame exists to avoid; its
frame-consistent replacement is ``centroids.canonical_mean``.
"""

from __future__ import annotations

import math
from typing import Any

import duckdb

from ..config import Settings
from ..db.registry import ExperimentRecord
from ..grid import frame as frame_mod
from ..grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from ..models.common import ApiMeta, Timer, envelope
from ..query import cache as cache_mod
from ..query import canonical, canonical_cache, centroids, density, ensemble, sampling, summary, window
from ..query import stagger as stagger_mod
from ..query.canonical import FrameStats
from ..query.filters import FilterSpec

FRAME_LAB = "lab"
FRAME_CANONICAL = "canonical"
FRAMES = (FRAME_LAB, FRAME_CANONICAL)

ANCHOR_DEFINITION = "entry_backprojection"


def _comb_report(
    report: stagger_mod.StaggerReport,
    intensity: dict[str, float | None],
    k: int,
    n_events: int,
) -> dict[str, Any]:
    """The comb measurement with canonical-frame wording.

    Two instruments, because a footprint splat fills every bin under a cell by
    construction: the occupancy lag-1 of ``stagger.detect`` (the lattice's
    structural comb) and the *energy* lag-1 of the brightest row and of the
    column sums (``stagger.intensity_lag1``), which is what point-binning
    leaves behind. Either below the threshold is reported as a comb. The lab
    note's advice ("switch to Continuous Field") is replaced by what actually
    smooths a footprint comb here.
    """
    data = report.as_dict()
    data["energy_lag1_columns"] = intensity.get("columns")
    data["energy_lag1_core_row"] = intensity.get("core_row")
    del data["occupancy"]  # of the whole accumulation window incl. margins: not a lattice statement
    energy_values = [v for v in intensity.values() if v is not None]
    energy_comb = any(v < stagger_mod.COMB_THRESHOLD for v in energy_values)
    comb = bool(report.staggered or energy_comb)
    data["staggered"] = comb

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:+.2f}"

    measured = (
        f"occupancy lag-1 {fmt(report.lag1)}, energy lag-1 {fmt(intensity.get('core_row'))} "
        f"on the brightest row and {fmt(intensity.get('columns'))} on the column sums"
    )
    if report.lag1 is None and not energy_values:
        data["note"] = (
            "Cell-footprint comb not measurable on this canonical window: too few "
            "columns for the lag-1 statistics."
        )
    elif comb:
        data["note"] = (
            f"A cell-footprint comb is measurable on the canonical grid ({measured}). "
            f"Each cell was split into {k} × {k} sub-deposits over {n_events:,} "
            "co-registered event(s); a larger selection or a coarser display "
            "resolution (Continuous Field with R below the window width in 20 mm bins) "
            "smooths it. It is detector segmentation, not shower structure."
        )
    else:
        data["note"] = f"No cell-footprint comb measured on the canonical grid ({measured})."
    return data


def _smoothing_regime(k: int, footprint: tuple[float, float], pitch: float) -> str:
    """Whether the sub-deposit spacing guarantees a hole-free footprint splat.

    Below the gap-free factor the ensemble of events still fills most bins, but
    that is a statistical statement the comb measurement has to confirm; the
    payload says which regime applies so a reader can weigh the measurement.
    """
    needed = frame_mod.minimum_gapless_subsample(max(footprint), pitch)
    return "sub-cell-sampling-gapless" if k >= needed else "sub-cell-sampling-partial"


def _anchor_offsets(
    pairs: dict[str, centroids.CentroidPair], stats: FrameStats
) -> dict[str, Any]:
    """Measured ensemble centroids minus the anchors, per shower, in mm."""
    d_mean = stats.d_entry.mean
    if d_mean is None or not math.isfinite(d_mean):
        return {}
    half = 0.5 * d_mean
    out: dict[str, Any] = {}
    for key, pair in pairs.items():
        entry: dict[str, Any] = {}
        for shower, point, anchor_x in (("a", pair.a, -half), ("b", pair.b, half)):
            if point.x is None or point.y is None:
                entry[shower] = None
            else:
                entry[shower] = [point.x - anchor_x, point.y]
        out[key] = entry
    return out


def _canonical_mean_pair(stats: FrameStats) -> centroids.CentroidPair:
    a = stats.a.centroid_mean
    b = stats.b.centroid_mean
    ca = centroids.Centroid(x=a[0], y=a[1], z=a[2], energy=float("nan"))
    cb = centroids.Centroid(x=b[0], y=b[1], z=b[2], energy=float("nan"))
    separation = None
    if None not in (a[0], a[1], b[0], b[1]):
        separation = float(math.hypot(a[0] - b[0], a[1] - b[1]))
    return centroids.CentroidPair(
        label="Dataset centroids (mean canonical position)", a=ca, b=cb,
        separation_mm=separation,
    )


_bundle_for = canonical_cache.bundle_for
dataset_reference = canonical_cache.dataset_reference


def build_response(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    settings: Settings,
    *,
    resolution: int,
    display: str,
    channel: str,
    weighting: str,
    rho_norm: str,
    preview: bool,
    timer: Timer,
    lock_scale: bool | None = None,
    scale_mode: str = "decades",
) -> dict[str, Any]:
    """The full canonical-frame response."""
    assert record.lattice is not None
    lattice = record.lattice
    decision = sampling.decide(record, preview, settings.sample_percent)
    footprint = canonical.cell_footprint(con, record)

    bundle, stats, grid, k, was_cached = _bundle_for(
        con, record, spec, settings, footprint, decision.sampled, decision.percent
    )

    # The comb is measured on the uncropped accumulation raster, where the
    # detector's edge trim and sample minimum are met, before any crop.
    comb = _comb_report(
        stagger_mod.detect(bundle.xy.planes["e"]),
        stagger_mod.intensity_lag1(bundle.xy.planes["e"]),
        k, stats.n_events,
    )

    fit = window.fit_window(bundle)
    reference = None
    if rho_norm == density.NORM_DATASET:
        reference = dataset_reference(con, record, settings, footprint)

    rendered = density.render_canonical(
        bundle, fit, display, resolution, channel, weighting, rho_norm, reference
    )

    pairs = centroids.compute(bundle)
    pairs["canonical_mean"] = _canonical_mean_pair(stats)
    centroid_sets = {key: pair.as_dict() for key, pair in pairs.items()}
    anchor_offsets = _anchor_offsets(pairs, stats)

    selection = summary.summarise(con, record, spec)
    selection_dict = selection.as_dict()
    # The lab-frame per-event average of the dataset centroids ships for
    # continuity of the envelope, but averaging positions across events that
    # sit in different places is exactly what this frame exists to avoid; say
    # so, and point at the frame-consistent replacement.
    selection_dict["centroid_dataset"]["label"] = (
        "Dataset centroids (laboratory-frame per-event average; not drawn in the "
        "canonical frame - see centroids.canonical_mean)"
    )
    coherence = summary.angular_coherence(con, record, spec)
    coherence["note"] = (
        "Laboratory-frame azimuth is near-uniform (resultant length above), which is "
        "why no averaged direction is drawn there. In the canonical frame the "
        "directions are co-registered first; the dashed lines are the two ensemble "
        "axes, each with its transverse resultant R̄′ and Rayleigh p stated."
    )
    axes = ensemble.ensemble_axes(stats, grid)

    warnings: list[str] = []
    if decision.sampled:
        warnings.append(decision.reason)

    notices: list[dict[str, str]] = []
    for note in rendered["resolution"]["warnings"]:
        notices.append({"scope": "resolution", "text": note})
    for note in rendered["notices"]:
        notices.append({"scope": "resolution", "text": note})
    notices.append({"scope": "frame", "text": comb["note"]})
    if stats.n_excluded_no_frame:
        notices.append({
            "scope": "frame",
            "text": (
                f"{stats.n_excluded_no_frame:,} selected event(s) have no shower-A "
                "centroid or incident direction and cannot be co-registered; they are "
                "excluded from N and from every canonical panel."
            ),
        })
    if spec.include_undefined_d:
        notices.append({
            "scope": "separation",
            "text": (
                "Events with an undefined A-B separation have no frame: including "
                "them changes nothing in the canonical panels."
            ),
        })
    if stats.n_ill_conditioned:
        notices.append({
            "scope": "frame",
            "text": (
                f"{stats.n_ill_conditioned:,} event(s) enter closer than "
                f"{frame_mod.ILL_CONDITIONED_D_MM:.0f} mm apart, so their rotation angle "
                "is dominated by the anchor uncertainty and effectively random. Their "
                "energy enters ⟨ρ⟩ averaged over azimuth, and their randomly oriented "
                "directions enter the ensemble-axis statistics (R̄′, Rayleigh p, "
                "dispersion band) as noise that pushes R̄′ down and p up."
            ),
        })
    if rho_norm == density.NORM_DATASET:
        ref_k = rendered["rho"].get("ref_k")
        if ref_k and ref_k != k:
            notices.append({
                "scope": "frame",
                "text": (
                    f"The dataset reference peak was measured with {ref_k} × {ref_k} "
                    f"sub-deposits per cell and this selection with {k} × {k}; a peak is a "
                    "maximum statistic, so the two differ by the footprint discretisation "
                    "and colours are comparable only to that extent."
                ),
            })
    if lock_scale is False or scale_mode != "decades":
        notices.append({
            "scope": "frame",
            "text": (
                "lock_scale and scale_mode are laboratory-frame ramp controls and are "
                "ignored here: the canonical ramp is relative to the reference chosen by "
                "rho_norm."
            ),
        })
    if fit.provisional:
        notices.append({
            "scope": "frame",
            "text": (
                f"With {stats.n_events} co-registered event(s) the fitted display "
                "ranges rest on weak evidence and are labelled provisional."
            ),
        })
    if rho_norm == density.NORM_SELECTION:
        notices.append({
            "scope": "frame",
            "text": (
                "Colours are relative to this selection's own peak density (stated in "
                "the footnote); switch the density normalisation to the dataset peak to "
                "compare colours across selections."
            ),
        })
    for note in axes["notes"]:
        notices.append({"scope": "frame", "text": note})

    frame_block: dict[str, Any] = {
        "kind": FRAME_CANONICAL,
        "anchor": ANCHOR_DEFINITION,
        "anchor_note": (
            "Each shower's 3-D centroid is back-projected to the front face along its "
            "incident direction; the midpoint of the two entry points is the origin and "
            "the A→B entry separation is the +x′ axis. D_entry is the transverse entry "
            "separation; D (the slider) is the 3-D centroid distance from the dataset."
        ),
        "z_front_mm": float(lattice.z.lo),
        "depth_mm": float(lattice.z.hi - lattice.z.lo),
        "pitch_mm": grid.pitch,
        "footprint_mm": [footprint[0], footprint[1]],
        "subsample_k": k,
        "subsample_budget_rows": frame_mod.SUBSAMPLE_ROW_BUDGET,
        "rows_scanned": int(round(stats.n_hits * (decision.percent / 100.0 if decision.sampled else 1.0))),
        "smoothing": _smoothing_regime(k, footprint, grid.pitch),
        "subsample_gapless_k": frame_mod.minimum_gapless_subsample(max(footprint), grid.pitch),
        "window": {
            **grid.as_dict(),
            "margin_mm": frame_mod.SHOWER_MARGIN_MM,
            "energy_outside_gev": bundle.energy_outside,
            "energy_fraction_outside": round(bundle.energy_fraction_outside, 8),
        },
        "fit": fit.as_dict(),
        **stats.as_dict(),
        "comb": comb,
        "rho": rendered["rho"],
        "anchor_offsets": anchor_offsets,
        "ensemble": {"a": axes["a"], "b": axes["b"], "fade_p": axes["fade_p"]},
        "notes": axes["notes"],
    }

    meta = ApiMeta(
        table_name=record.table_name,
        exact=bundle.exact,
        query_ms=bundle.query_ms,
        total_ms=timer.elapsed_ms,
        cached=was_cached,
        warnings=warnings,
        notes={
            "frame": FRAME_CANONICAL,
            "resolution": rendered["resolution"],
            "channel": channel,
            "weighting": weighting,
            "sample_percent": decision.percent if decision.sampled else 100.0,
            "stagger": comb,
            "notices": notices,
            "cache": cache_mod.get_cache(
                settings.canonical_cache_entries, name=cache_mod.CANONICAL_CACHE
            ).info(),
        },
    )

    return envelope(
        meta,
        panels=rendered["panels"],
        centroids=centroid_sets,
        selection=selection_dict,
        filter=spec.as_dict(),
        overlays={
            "axes": {},
            "trajectories": [],
            "coherence": coherence,
            "max_trajectory_events": summary.MAX_TRAJECTORY_EVENTS,
            "ensemble_axes": {
                "yz": {"a": axes["a"]["yz"], "b": axes["b"]["yz"]},
                "xz": {"a": axes["a"]["xz"], "b": axes["b"]["xz"]},
            },
            "anchors": axes["anchors"],
        },
        slab={
            "mm": lattice.slab_mm,
            "layers": lattice.slab_iz + 1,
            "z_front": lattice.z.lo,
            "note": (
                "The X′Y′ panel sums the entrance slab: the first "
                f"{lattice.slab_iz + 1} sampling layers, {lattice.slab_mm:.0f} mm from "
                "the front face at z′ = 0."
            ),
        },
        frame=frame_block,
    )
