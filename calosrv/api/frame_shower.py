"""Assemble the translated and local responses of ``GET /api/projections``.

``coord_system=trans`` and ``coord_system=local`` co-register every *shower*
on its own entry point (and, in the local frame, its own incident direction),
so the two showers of each event lie on top of each other at the origin. The
envelope is the canonical one - ``meta``, ``panels``, ``centroids``,
``selection``, ``filter``, ``overlays``, ``slab`` and a ``frame`` block - read
by the same frontend code; what differs is said in the frame block and the
notices:

* **No separation.** Both showers sit at the origin by construction, so the
  voxel centroid pairs carry ``offset_mm`` (the A-B offset of the superimposed
  centroids, not a separation) and ``separation_mm`` is null. D stays the
  laboratory ``centroid_AB_distance``.
* **``frame_mean``** replaces the canonical ensemble axes: the per-event
  centroid offsets from P0 in this frame, each with its sample SD and its
  Student-t 95% interval of the mean, gated by the low-N table.
* **Directions.** The translated frame does not rotate, so every shower keeps
  its laboratory azimuth - near-uniform - and only individual trajectories are
  drawn, from the origin, for at most 50 events. In the local frame every
  incident direction is +w by construction; nothing is drawn.

Order of work, window floors, kernel gates and the whole-response budget are
the canonical frame's (``frame_canonical.py``).
"""

from __future__ import annotations

from typing import Any

import duckdb

from ..config import Settings
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..grid import frame as frame_mod
from ..grid.frame import KIND_LOCAL, KIND_TRANS
from ..models.common import ApiMeta, Timer, envelope
from ..text import fmt_signed
from ..query import canonical, centroids, density, reconstruct, sampling, summary, window
from ..query import planes as planes_mod
from ..query import shower_frames
from ..query import stagger as stagger_mod
from ..query.filters import FilterSpec
from ..query.shower_frames import ShowerBundle, ShowerStats
from .frame_canonical import (
    COMB_MEASURED_ON, _attenuation_notice, _floor_notice, _reference_notice, serve_within_budget,
)

FRAME_TITLE = {KIND_TRANS: "translated", KIND_LOCAL: "local"}

DEPTH_KIND = {KIND_TRANS: "native_layers", KIND_LOCAL: "uniform_bins"}


def _panel_names(symbols: dict[str, str]) -> dict[str, str]:
    x, y, z = symbols["x"], symbols["y"], symbols["z"]
    return {"xy": f"{x}{y}", "yz": f"{y}{z}", "xz": f"{x}{z}"}


def _fmt(v: float | None) -> str:
    return fmt_signed(v, 2, plus=True)


def _comb_report(bundle: ShowerBundle, n_events: int) -> dict[str, Any]:
    """The footprint comb, measured on the raw uncropped accumulation rasters.

    Along both transverse axes of the entrance-slab raster - the translated
    and local frames do not rotate the lattice onto a common orientation the
    way the canonical frame does, so neither axis can be assumed clean - and,
    in the local frame, along w of both depth rasters, where rotated 20.5 mm
    layers are binned at the layer pitch. Each axis reports the occupancy
    lag-1 (``stagger.detect``) and the energy lag-1 of the column sums and the
    brightest row (``stagger.intensity_lag1``); any below the threshold is a
    comb.
    """
    symbols = bundle.symbols
    xy = bundle.xy.planes["e"]
    axes: dict[str, dict[str, float | None]] = {}
    for name, matrix in (("x", xy), ("y", xy.T)):
        occupancy = stagger_mod.detect(matrix)
        energy = stagger_mod.intensity_lag1(matrix)
        axes[name] = {"occupancy": occupancy.lag1, "energy_columns": energy["columns"],
                      "energy_core_row": energy["core_row"]}
    if bundle.kind == KIND_LOCAL:
        for name, matrix in (("z_yz", bundle.yz.planes["e"]), ("z_xz", bundle.xz.planes["e"])):
            energy = stagger_mod.intensity_lag1(matrix)
            axes[name] = {"occupancy": None, "energy_columns": energy["columns"],
                          "energy_core_row": energy["core_row"]}

    def worst(values: dict[str, float | None]) -> float | None:
        present = [v for v in values.values() if v is not None]
        return min(present) if present else None

    lag1 = {"x": worst(axes["x"]), "y": worst(axes["y"])}
    if bundle.kind == KIND_LOCAL:
        present = [v for v in (worst(axes["z_yz"]), worst(axes["z_xz"])) if v is not None]
        lag1["z"] = min(present) if present else None
    combed = [name for name, v in lag1.items() if v is not None and v < stagger_mod.COMB_THRESHOLD]
    measured = ", ".join(f"{symbols[name]} {_fmt(v)}" for name, v in lag1.items())

    splat = (
        "each cell's footprint is integrated exactly by area-weighted box overlap"
        if bundle.kind == KIND_TRANS else
        f"each cell was split into {bundle.subsample_k} × {bundle.subsample_k} × {bundle.k_z} "
        "rotated sub-deposits"
    )
    if all(v is None for v in lag1.values()):
        note = (
            f"Cell-footprint comb not measurable on this {FRAME_TITLE[bundle.kind]} window: too "
            "few bins for the lag-1 statistics."
        )
    elif combed:
        note = (
            f"A cell-footprint comb is measurable on the raw {FRAME_TITLE[bundle.kind]} "
            f"accumulation grid, before any display smoothing, along "
            f"{' and '.join(symbols[name] for name in combed)} (worst lag-1 per axis: {measured}); "
            f"{splat} over {n_events:,} event(s). Native Grid shows it as measured; Continuous "
            "Field smooths it for display, which hides it rather than removing it. It is "
            "detector segmentation, not shower structure."
        )
    else:
        note = (
            f"No cell-footprint comb measured on the raw {FRAME_TITLE[bundle.kind]} accumulation "
            f"grid, before any display smoothing (worst lag-1 per axis: {measured}); {splat}."
        )
    return {
        "staggered": bool(combed),
        "combed_axes": combed,
        "lag1": lag1,
        "axes": axes,
        "threshold": stagger_mod.COMB_THRESHOLD,
        "measured_on": COMB_MEASURED_ON,
        "note": note,
    }


def _superimposed_pairs(pairs: dict[str, centroids.CentroidPair], symbols: dict[str, str]) -> dict[str, Any]:
    """Voxel centroid pairs with the A-B distance renamed to what it is here."""
    out = {}
    for key, pair in pairs.items():
        data = pair.as_dict()
        data["offset_mm"] = data.pop("separation_mm")
        data["separation_mm"] = None
        data["offset_note"] = (
            f"A-B offset of the two superimposed ensemble centroids in the {symbols['x']}{symbols['y']} "
            "plane, each relative to its own shower's entry point: not a separation, which "
            "is D (laboratory)."
        )
        out[key] = data
    return out


def _frame_mean(stats: ShowerStats, kind: str) -> dict[str, Any]:
    """Mean per-event centroid of each shower in this frame, with SD and t-interval."""
    def point(shower: str) -> dict[str, Any]:
        m = stats.mean[shower]
        return {"x": m["x"].mean, "y": m["y"].mean, "z": m["z"].mean, "energy": None}

    def per(shower: str, attr: str) -> dict[str, float | None]:
        return {axis: getattr(stats.mean[shower][axis], attr) for axis in "xyz"}

    n = stats.n_events
    if n < 2:
        dof = "N = 1: a single event's own centroids; no dispersion or interval is defined."
    elif n < frame_mod.PROVISIONAL_N:
        dof = (
            f"N = {n}: SD with ddof = 1 and a Student-t 95% interval on {n - 1} degree(s) of "
            "freedom; weak evidence, labelled provisional."
        )
    else:
        dof = f"N = {n}: SD with ddof = 1 and a Student-t 95% interval on {n - 1} degrees of freedom."
    column = "centroid_*_trans" if kind == KIND_TRANS else "centroid_*_local"
    # One event has no ensemble to average: its marker is that event's own
    # centroid, and is labelled so wherever the label travels.
    label = (
        f"This single event's own centroid ({column}), relative to each shower's entry point: "
        "not an ensemble mean"
        if n < 2 else
        f"Mean per-event centroid ({column}), relative to each shower's entry point"
    )
    return {
        "label": label,
        "a": point("a"),
        "b": point("b"),
        "separation_mm": None,
        "n": n,
        "sd": {"a": per("a", "sd"), "b": per("b", "sd")},
        "ci95_half": {"a": per("a", "ci95_half"), "b": per("b", "ci95_half")},
        "dof_note": dof,
    }


def build_response(
    con: duckdb.DuckDBPyConnection,
    record: ExperimentRecord,
    spec: FilterSpec,
    settings: Settings,
    *,
    kind: str,
    resolution: int,
    display: str,
    channel: str,
    model: str,
    weighting: str,
    rho_norm: str,
    preview: bool,
    timer: Timer,
    lock_scale: bool | None = None,
    scale_mode: str = "decades",
) -> dict[str, Any]:
    """The full translated- or local-frame response, budgeted as it goes on the wire."""
    if kind not in frame_mod.SHOWER_KINDS:  # pragma: no cover - the route validates first
        raise ValidationError(f"not a per-shower frame: {kind!r}", field="coord_system")
    if record.frame_bounds is None or record.lattice is None:
        raise ValidationError(
            f"Experiment {record.table_name!r} has no per-shower frame extents; re-ingest it "
            "to use the translated and local frames.",
            field="coord_system",
        )
    lattice = record.lattice
    decision = sampling.decide(record, preview, settings.sample_percent)
    footprint = canonical.cell_footprint(con, record)
    symbols = shower_frames.SYMBOLS[kind]
    names = _panel_names(symbols)
    title = FRAME_TITLE[kind]

    if channel == planes_mod.CHANNEL_DENSITY:
        bundle, stats, grid, k, was_cached = shower_frames.density_bundle_for(
            con, record, spec, settings, kind, footprint, decision.sampled, decision.percent, model)
    else:
        bundle, stats, grid, k, was_cached = shower_frames.bundle_for(
            con, record, spec, settings, kind, footprint, decision.sampled, decision.percent, model)

    kernel = reconstruct.choose_kernel(display, stats.n_events)
    comb = _comb_report(bundle, stats.n_events)
    fit = window.fit_window(bundle)
    reference = None
    if rho_norm == density.NORM_DATASET:
        reference = shower_frames.dataset_reference(con, record, settings, kind, footprint)

    def render(limit: int, **resume: Any) -> dict[str, Any]:
        return density.render_canonical(
            bundle, fit, display, resolution, channel, weighting, rho_norm, reference,
            limit=limit, kernel=kernel, symbols=symbols, **resume,
        )

    rendered = render(density.PAYLOAD_LIMIT)

    centroid_sets = _superimposed_pairs(centroids.compute(bundle), symbols)
    centroid_sets["frame_mean"] = _frame_mean(stats, kind)

    selection_dict = summary.summarise(con, record, spec).as_dict()
    selection_dict["centroid_dataset"]["label"] = (
        f"Dataset centroids (laboratory-frame per-event average; not drawn in the {title} "
        "frame - see centroids.frame_mean)"
    )

    if kind == KIND_TRANS:
        coherence = summary.angular_coherence(con, record, spec)
        coherence["note"] = (
            "The translated frame does not rotate, so every shower keeps its laboratory "
            "incident direction and the azimuth keeps its laboratory distribution (resultant "
            "length above): no averaged direction is drawn. Individual trajectories are drawn "
            f"from the origin for at most {summary.MAX_TRAJECTORY_EVENTS} events."
        )
        trajectories = (
            shower_frames.trajectories_from_origin(con, record, spec, summary.MAX_TRAJECTORY_EVENTS)
            if stats.n_events <= summary.MAX_TRAJECTORY_EVENTS else []
        )
        overlays: dict[str, Any] = {
            "axes": {},
            "trajectories": trajectories,
            "coherence": coherence,
            "max_trajectory_events": summary.MAX_TRAJECTORY_EVENTS,
        }
    else:
        coherence = None
        overlays = {}

    warnings: list[str] = []
    if decision.sampled:
        warnings.append(decision.reason)

    cam_view = planes_mod.view(channel)
    depth_axis = grid.axis("z")
    depth_edges = depth_axis.edges
    layer = float(record.frame_bounds.layer_pitch_mm)

    def assemble(rendered: dict[str, Any], budget_notes: list[str]) -> dict[str, Any]:
        notices: list[dict[str, str]] = []
        for note in (*rendered["resolution"]["warnings"], *rendered["notices"], *budget_notes):
            notices.append({"scope": "resolution", "text": note})
        notices.append({"scope": "frame", "text": (
            f"{title.capitalize()} frame: {stats.n_events:,} event(s), {stats.n_showers:,} showers "
            "superimposed at their own entry points"
            + (", each rotated so its incident direction is +w" if kind == KIND_LOCAL else "")
            + ". ⟨ρ⟩ is energy per event and per mm², so it sums both showers of an event."
        )})
        notices.append({"scope": "frame", "text": comb["note"]})
        notices.append({"scope": "frame", "text": _floor_notice(channel, display, rendered["panels"], names)})
        if stats.n_excluded_no_frame:
            notices.append({"scope": "frame", "text": (
                f"{stats.n_excluded_no_frame:,} selected event(s) have no A-B separation (no "
                f"shower-A centroid); they are excluded from N and from every {title} panel."
            )})
        if spec.include_undefined_d:
            notices.append({"scope": "separation", "text": (
                "Events with an undefined A-B separation are not co-registered in the "
                f"{title} frame: including them changes nothing in its panels."
            )})
        if stats.n_ab:
            notices.append({"scope": "frame", "text": (
                f"{stats.n_ab:,} hit(s) labelled 'A+B' sit at the origin of this frame and are "
                "counted with shower B."
            )})
        if cam_view.is_cam:
            notices.append({"scope": "frame", "text": planes_mod.cam_note(model, kind, channel)["note"]})
            zero = stats.cam_zero.get(cam_view.cam, 0)
            if zero:
                notices.append({"scope": "frame", "text": (
                    f"{zero:,} selected event(s) have an all-zero map from the {model} network in "
                    f"the {title} frame; they contribute energy but no attention."
                )})
        if rho_norm == density.NORM_DATASET:
            ref_k = rendered["rho"].get("ref_k")
            if kind == KIND_LOCAL and ref_k and ref_k != k:
                notices.append({"scope": "frame", "text": (
                    f"The dataset reference peak was measured with {ref_k} × {ref_k} × "
                    f"{bundle.k_z} sub-deposits per cell and this selection with {k} × {k} × "
                    f"{bundle.k_z}; a peak is a maximum statistic, so the two differ by the "
                    "footprint discretisation and colours are comparable only to that extent."
                )})
            attenuation = None if cam_view.is_cam else _attenuation_notice(rendered["rho"])
            if attenuation:
                for prime, sym in (("X′Y′", names["xy"]), ("Y′Z′", names["yz"]), ("X′Z′", names["xz"])):
                    attenuation = attenuation.replace(prime, sym)
                notices.append({"scope": "frame", "text": attenuation})
        reference = _reference_notice(channel, rendered["rho"].get("norm", rho_norm), grid.pitch)
        if reference:
            notices.append({"scope": "frame", "text": reference})
        if lock_scale is False or scale_mode != "decades":
            notices.append({"scope": "frame", "text": (
                "lock_scale and scale_mode are laboratory-frame ramp controls and are ignored "
                f"here: the {title} ramp is relative to the reference chosen by rho_norm."
            )})
        if fit.provisional:
            notices.append({"scope": "frame", "text": (
                f"With {stats.n_events} event(s) the fitted display ranges and the mean centroids "
                "rest on weak evidence and are labelled provisional."
            )})
        if kind == KIND_LOCAL:
            notices.append({"scope": "frame", "text": (
                "w is each shower's incident direction by construction; no ensemble axis or "
                "Rayleigh statistic is drawn because none could carry information."
            )})

        frame_block: dict[str, Any] = {
            "kind": kind,
            "anchor": "own_shower_entry_point",
            "anchor_note": (
                "Each hit is shifted by its own shower's entry point P0 - the energy-weighted "
                "x, y centroid of that shower's first populated layer, at that layer's depth"
                + (" - and rotated by that shower's R(θ, φ), so its incident direction is +w"
                   if kind == KIND_LOCAL else "")
                + ". D (the slider) is the laboratory 3-D centroid distance."
            ),
            "symbols": symbols,
            "pitch_mm": grid.pitch,
            "depth_mm": float(depth_edges[-1] - depth_edges[0]),
            "depth": {
                "policy": DEPTH_KIND[kind],
                "text": bundle.depth_policy,
                "pitch_mm": layer,
                "n": grid.n_z,
                "range_mm": [float(depth_edges[0]), float(depth_edges[-1])],
            },
            "footprint_mm": [footprint[0], footprint[1]],
            "splat": {
                "regime": bundle.splat_regime,
                "k": None if kind == KIND_TRANS else k,
                "k_z": None if kind == KIND_TRANS else bundle.k_z,
                "budget_rows": frame_mod.SUBSAMPLE_ROW_BUDGET,
            },
            "subsample_k": None if kind == KIND_TRANS else k,
            "rows_scanned": int(round(stats.n_hits * (decision.percent / 100.0 if decision.sampled else 1.0))),
            "window": {
                **grid.as_dict(),
                "planned_from": "dataset energy-weighted 10⁻⁴ and 0.9999 quantiles plus half a footprint",
                "energy_outside_gev": bundle.energy_outside,
                "energy_fraction_outside": round(bundle.energy_fraction_outside, 8),
                "hits_outside": bundle.n_outside,
            },
            "fit": fit.as_dict(),
            **stats.as_dict(),
            "d_dataset": {
                "mean": stats.d_dataset.mean,
                "ci95_half": stats.d_dataset.ci95_half,
                "sd": stats.d_dataset.sd,
                "n": stats.d_dataset.n,
            },
            "comb": comb,
            "rho": rendered["rho"],
            "reconstruction": rendered["reconstruction"],
            "notes": [],
        }
        if coherence is not None:
            frame_block["coherence"] = {"r_a": coherence.get("r_a"), "r_b": coherence.get("r_b"),
                                        "n": coherence.get("n")}

        meta = ApiMeta(
            table_name=record.table_name,
            exact=bundle.exact,
            query_ms=bundle.query_ms,
            total_ms=timer.elapsed_ms,
            cached=was_cached,
            warnings=warnings,
            notes={
                "frame": kind,
                "coord_system": kind,
                "model": model,
                "resolution": rendered["resolution"],
                "channel": channel,
                "weighting": weighting,
                **({"cam": planes_mod.cam_note(model, kind, channel)} if cam_view.is_cam else {}),
                "sample_percent": decision.percent if decision.sampled else 100.0,
                "stagger": comb,
                "notices": notices,
                "cache": shower_frames.cache_for(settings, kind).info(),
            },
        )

        slab_layers = lattice.slab_iz + 1
        return envelope(
            meta,
            panels=rendered["panels"],
            centroids=centroid_sets,
            selection=selection_dict,
            filter=spec.as_dict(),
            overlays=overlays,
            slab={
                "mm": slab_layers * layer,
                "layers": slab_layers,
                "z_front": 0.0,
                "note": (
                    f"The {names['xy']} panel sums each shower's entrance slab: its own first "
                    f"{slab_layers} sampling layers ({slab_layers * layer:.0f} mm), counted from "
                    "the layer holding its entry point"
                    + (", projected onto the plane perpendicular to its incident direction."
                       if kind == KIND_LOCAL else ".")
                ),
            },
            frame=frame_block,
        )

    return serve_within_budget(assemble, render, rendered, display)

