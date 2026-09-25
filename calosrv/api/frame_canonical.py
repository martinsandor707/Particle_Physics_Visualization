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

**Order of work.** The display kernel is chosen from the exact event count
first; the comb is measured next, on the raw uncropped accumulation raster,
so no display choice can touch it (smoothing was measured to hide a real
k = 1 comb in 7 of 7 tests); then the window is fitted, the panels rendered,
and the whole response budgeted.

**Budget.** The panel guard in ``query/density.py`` bounds the rasters, but the
envelope around them - frame block, meta, centroids, notices - adds 13-16 KB
on production v37, and a response whose panels passed the guard measured
108 775 bytes for the five-event slice D 257-258 mm. So the assembled response
is measured exactly as the route serialises it and, if it reaches the
100 000-byte contract, the panels are re-rendered from the cached bundle one
guard step at a time, each candidate measured the same way, until one fits.
The steps continue the guard's own sequence from the state the first pass
served instead of restarting at the requested R: the restart repeated every
attempt, and made a cached R = 400 request on the N = 3 production slice cost
309 ms against a 100 ms budget. Measuring each candidate, rather than
comparing the guard's deliberately over-counted panel size with a limit taken
from the compact wire size, is what keeps a higher request from being served
coarser than the default: that mismatch stepped D 20-40 mm past R = 150 to
R = 112 for any request above 150, although R = 150 fits. Every step is
disclosed.
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
from ..query import canonical, canonical_cache, centroids, density, ensemble, reconstruct, sampling, summary, window
from ..query import stagger as stagger_mod
from ..query import planes as planes_mod
from ..query.panels import CHANNEL_GRADCAM
from ..query.canonical import FrameStats
from ..query.filters import FilterSpec

FRAME_LAB = "lab"
FRAME_CANONICAL = "canonical"
FRAMES = (FRAME_LAB, FRAME_CANONICAL)

ANCHOR_DEFINITION = "entry_backprojection"

#: Where the comb is measured, stated in the payload beside the verdict.
COMB_MEASURED_ON = "raw accumulation grid, before display smoothing"

_PANEL_NAMES = {"xy": "X′Y′", "yz": "Y′Z′", "xz": "X′Z′"}


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
    leaves behind. Either below the threshold is reported as a comb.

    The measurement is always taken on the raw accumulation raster, so the
    verdict is the same whichever display mode is chosen. The note says what
    each mode does with a comb: Native Grid shows it as measured; Continuous
    Field's kernel smooths it for display, which hides it rather than removing
    it - so no advice to "smooth it away" is given.
    """
    data = report.as_dict()
    data["energy_lag1_columns"] = intensity.get("columns")
    data["energy_lag1_core_row"] = intensity.get("core_row")
    del data["occupancy"]  # of the whole accumulation window incl. margins: not a lattice statement
    energy_values = [v for v in intensity.values() if v is not None]
    energy_comb = any(v < stagger_mod.COMB_THRESHOLD for v in energy_values)
    comb = bool(report.staggered or energy_comb)
    data["staggered"] = comb
    data["measured_on"] = COMB_MEASURED_ON

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
            "A cell-footprint comb is measurable on the raw canonical accumulation grid, "
            f"before any display smoothing ({measured}). Each cell was split into {k} × {k} "
            f"sub-deposits over {n_events:,} co-registered event(s). Native Grid shows it as "
            "measured; Continuous Field smooths it for display, which hides it rather than "
            "removing it. It is detector segmentation, not shower structure."
        )
    else:
        data["note"] = (
            "No cell-footprint comb measured on the raw canonical accumulation grid, before "
            f"any display smoothing ({measured})."
        )
    return data


def _subsample_regime(k: int, footprint: tuple[float, float], pitch: float) -> str:
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


def _floor_notice(
    channel: str, display: str, panels: dict[str, dict[str, Any]],
    names: dict[str, str] | None = None,
) -> str:
    """What the display floor leaves undrawn, in the channel's own terms."""
    floor = density.floor_label()
    names = names or _PANEL_NAMES
    view = planes_mod.view(channel)
    label = "Grad-CAM" if view.cam == "gradcam" else "Shap-CAM"
    if view.kind == planes_mod.KIND_RATIO:
        what = "attention" if view.cam == "gradcam" else "attribution"
        if display == MODE_NATIVE:
            return (
                f"{label} in Native Grid: only bins with no hits are transparent, because "
                f"{what} is undefined there; {what} measured on real hits is always "
                "drawn, however little energy they hold."
            )
        masked = ", ".join(
            f"{names[name]} {int(panels[name]['attention_mask']['cells']):,}"
            for name in ("xy", "yz", "xz")
        )
        return (
            f"{label} in Continuous Field: {what} is not drawn where the reconstructed "
            f"energy density is below {floor} of ρ_ref (bins masked: {masked}), because the "
            f"kernel tails carry {what} into bins no measured energy reached."
        )
    if view.is_cam:
        parts = "; ".join(
            f"{names[name]} {int(panels[name].get('below_floor_cells', 0)):,} bins"
            for name in ("xy", "yz", "xz")
        )
        magnitude = "|Σ E·CAM|" if view.kind == planes_mod.KIND_SIGNED else "Σ E·CAM"
        return (
            f"Energy-weighted {label}: bins whose {magnitude} is below {floor} of this "
            f"selection's peak are not drawn ({parts}); bins with no hits are empty."
        )
    # The Native Grid reconstructs nothing, so its bins hold raw energy.
    energy = "reconstructed energy" if display == MODE_CONTINUOUS else "energy"
    parts = "; ".join(
        f"{_PANEL_NAMES[name]} {int(panels[name]['below_floor_cells']):,} bins holding "
        f"{100.0 * panels[name]['below_floor_energy_fraction']:.3g}% of its in-window {energy}"
        for name in ("xy", "yz", "xz")
    )
    return (
        f"Bins below {floor} of ρ_ref are not drawn ({parts}), so the outer edge of the colour "
        f"is the display floor, not the edge of the shower. Bins with no {energy} at all are "
        "empty."
    )


def _attenuation_notice(rho: dict[str, Any]) -> str | None:
    """Dataset normalisation: how far the display lowered this selection's own peak."""
    attenuation = rho.get("kernel_attenuation") or {}
    values = {name: attenuation.get(name) for name in ("xy", "yz", "xz")}
    if any(v is None for v in values.values()) or min(values.values()) >= 0.9995:
        return None
    return (
        "Colours are relative to the whole dataset's raw 20 mm-grid peak. The display "
        f"reconstruction lowers this selection's own peak to {values['xy']:.3f} × its raw value "
        f"in X′Y′ ({values['yz']:.3f} in Y′Z′, {values['xz']:.3f} in X′Z′), so part of a colour "
        "difference between selections can be the display rather than the physics; compare "
        "them in the same display mode and on the same side of the N = "
        f"{frame_mod.GAUSSIAN_KERNEL_BELOW_N} kernel switch."
    )


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
    model: str = "segmentation",
) -> dict[str, Any]:
    """The full canonical-frame response, budgeted as it goes on the wire."""
    assert record.lattice is not None
    lattice = record.lattice
    decision = sampling.decide(record, preview, settings.sample_percent)
    footprint = canonical.cell_footprint(con, record)

    bundle, stats, grid, k, was_cached = _bundle_for(
        con, record, spec, settings, footprint, decision.sampled, decision.percent, model
    )

    # The kernel follows the exact event count, which comes from the event
    # table even when the hits are served from the drag-preview sample.
    kernel = reconstruct.choose_kernel(display, stats.n_events)

    # The comb is measured on the uncropped accumulation raster, where the
    # detector's edge trim and sample minimum are met, before any crop and
    # before any display smoothing.
    comb = _comb_report(
        stagger_mod.detect(bundle.xy.planes["e"]),
        stagger_mod.intensity_lag1(bundle.xy.planes["e"]),
        k, stats.n_events,
    )

    fit = window.fit_window(bundle)
    reference = None
    if rho_norm == density.NORM_DATASET:
        reference = dataset_reference(con, record, settings, footprint)

    def render(limit: int, **resume: Any) -> dict[str, Any]:
        return density.render_canonical(
            bundle, fit, display, resolution, channel, weighting, rho_norm, reference,
            limit=limit, kernel=kernel, **resume,
        )

    rendered = render(density.PAYLOAD_LIMIT)

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

    def assemble(rendered: dict[str, Any], budget_notes: list[str]) -> dict[str, Any]:
        notices: list[dict[str, str]] = []
        for note in rendered["resolution"]["warnings"]:
            notices.append({"scope": "resolution", "text": note})
        for note in rendered["notices"]:
            notices.append({"scope": "resolution", "text": note})
        for note in budget_notes:
            notices.append({"scope": "resolution", "text": note})
        notices.append({"scope": "frame", "text": comb["note"]})
        notices.append({"scope": "frame", "text": _floor_notice(channel, display, rendered["panels"])})
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
            attenuation = _attenuation_notice(rendered["rho"])
            if attenuation:
                notices.append({"scope": "frame", "text": attenuation})
        cam_view = planes_mod.view(channel)
        if cam_view.is_cam and cam_view.kind != planes_mod.KIND_RATIO and rho_norm == density.NORM_DATASET:
            notices.append({
                "scope": "frame",
                "text": (
                    "The dataset density normalisation applies to the density channel only; "
                    "an energy-weighted CAM panel is relative to this selection's own "
                    "raw-grid peak of Σ E·CAM, stated in its footnote."
                ),
            })
        if cam_view.is_cam:
            notices.append({"scope": "frame", "text": planes_mod.cam_note(model, "lab", channel)["note"]})
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
                    "Colours are relative to this selection's own peak density on the raw "
                    f"{grid.pitch:.0f} mm accumulation grid (stated in the footnote), which the "
                    "displayed field never exceeds; switch the density normalisation to the "
                    "dataset peak to compare colours across selections."
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
            "subsample_regime": _subsample_regime(k, footprint, grid.pitch),
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
            "reconstruction": rendered["reconstruction"],
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
                "coord_system": "lab",
                "model": model,
                "resolution": rendered["resolution"],
                "channel": channel,
                "weighting": weighting,
                **({"cam": planes_mod.cam_note(model, "lab", channel)}
                   if planes_mod.view(channel).is_cam else {}),
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

    body = assemble(rendered, [])
    size = density.wire_size(body)
    if size < density.RESPONSE_LIMIT:
        return body

    bare = density.wire_size({**body, "panels": {}})
    measured = (
        f"The whole response measured {size:,} bytes against the "
        f"{density.RESPONSE_LIMIT:,}-byte contract, {bare:,} of them the envelope around the panels"
    )
    guard = rendered["guard"]
    if not guard["fits"]:
        # The panel guard ended over its own, looser limit with no step left
        # or no attempt left; a tighter limit cannot do better.
        return assemble(rendered, [
            f"{measured}; the panel guard had already failed its own limit, so the response is "
            "served as it is."
        ])

    # The panels fit their own guard but the envelope pushed the whole response
    # over the contract. Continue the guard's own sequence from the state it
    # served - never restart it from the requested R - and measure each
    # candidate as it is served, envelope and notices included, rather than
    # predict it. A limit derived from the compact wire size and compared with
    # the guard's deliberately over-counted panel measure rejected states that
    # fit: on production v37, D 20-40 mm, R = 150 serves 98,377 B when asked
    # for directly, yet a request for R = 225 was stepped past it to R = 112.
    # The first pass's steps stay disclosed, in order.
    notes = [
        *rendered["notices"],
        f"{measured}; the panels were re-rendered from the cached bundle, each resolution "
        "measured as it is served.",
    ]
    continuous = display == MODE_CONTINUOUS
    whole = size
    rendered["notices"] = notes
    for _attempt in range(density.MAX_ATTEMPTS):
        step = rendered["guard"]["next"]
        if step is None:
            break
        previous = rendered["guard"]
        # The candidate fits the panel guard (it is coarser than a state that
        # did), so this renders exactly at `step`.
        rendered = render(density.PAYLOAD_LIMIT, start=step)
        if continuous:
            notes.append(
                f"Resolution lowered from R = {previous['r']} to R = {step[0]} to keep the "
                f"payload under the 100 KB contract ({whole:,}-byte response at R = {previous['r']})."
            )
        else:
            notes.append(
                f"Transverse bins merged {step[1]}x to keep the payload under the 100 KB "
                f"contract ({whole:,}-byte response before merging)."
            )
        rendered["notices"] = [*notes, *rendered["notices"]]
        body = assemble(rendered, [])
        whole = density.wire_size(body)
        if whole < density.RESPONSE_LIMIT:
            return body
    if rendered["guard"]["next"] is None:
        where = (
            f"at the minimum resolution R = {rendered['guard']['r']}" if continuous
            else "with every transverse axis merged into a single bin"
        )
    else:
        where = f"after {density.MAX_ATTEMPTS} re-renders"
    return assemble(rendered, [
        f"The response is still {whole:,} bytes {where} and is served as it is."
    ])
