"""``GET /api/energy-distribution`` - the reconstructed-energy panel.

Two slicings share the panel's machinery, marks and budget guard:

* ``slice_by=d`` (the default for two-shower experiments): the overlap panel,
  events sliced by the A-B separation D.
* ``slice_by=momentum`` (the default, and the only slicing, for single-shower
  experiments): the response grid B3, each shower sliced by its own incident
  momentum, ``p_slices`` choosing the windows or the producer's 1 GeV bins.

A parameter that belongs to the other slicing is refused naming it, never
ignored: a cut the reader believes was made must have been made.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable

import duckdb
from fastapi import APIRouter, Query

from ..db import ddl
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..models.common import ApiMeta, Timer, envelope
from ..stats import clip as clip_mod
from ..stats import histogram
from ..stats import momentum as momentum_mod
from ..stats.slices import parse_edges
from ..query import capabilities, density, energy
from ..query.filters import FilterSpec
from ..text import typographic
from .deps import CursorDep, FilterDep, RecordDep

router = APIRouter()

#: Coarser curve samplings the budget guard steps through, in order.
CURVE_POINT_STEPS = (150, 100, 75, 50)

SLICE_D = "d"
SLICE_MOMENTUM = "momentum"
SLICE_MODES: tuple[str, ...] = (SLICE_D, SLICE_MOMENTUM)

#: ``respond(curve_points, bins, extra_warnings)``: one rendering of the panel.
#: ``bins=None`` keeps the request's own bin count.
Responder = Callable[[int, int | None, list[str]], dict]


def within_budget(respond: Responder) -> dict:
    """The panel under the payload contract, coarsened only as far as it must be.

    The panel grows with its slices: at the maximum of eight D slices, each with
    four fitted curves, the sampled curves alone measured 67 KB of a 120 KB
    response on the production file, and twenty momentum bins of two showers
    need more. Each rendering is measured as served, and while it is over the
    contract the guard steps, disclosing each step it takes:

    1. the curves are re-sampled more coarsely - exact Gaussians at every point
       shipped, so nothing is approximated but the polyline between them;
    2. the shared histogram bin count is halved, down to ``MIN_BINS``;
    3. if the body is still over, it is served as it is, and the response says
       so - withholding a slice or a series would hide data, not disclose it.
    """
    body = respond(histogram.CURVE_POINTS, None, [])
    first = size = density.wire_size(body)
    points = histogram.CURVE_POINTS
    notes: list[str] = []
    for step in CURVE_POINT_STEPS:
        if size < density.RESPONSE_LIMIT:
            return body
        points = step
        notes = [
            f"Density curves sampled at {points} points instead of {histogram.CURVE_POINTS} "
            f"to keep the response under the {density.RESPONSE_LIMIT:,}-byte contract "
            f"({first:,} bytes at {histogram.CURVE_POINTS}); every point is the exact fitted "
            "Gaussian."
        ]
        body = respond(points, None, notes)
        size = density.wire_size(body)
    if size < density.RESPONSE_LIMIT:
        return body

    start = bins = int(body["axis"]["bins"])
    taken = [bins]
    while size >= density.RESPONSE_LIMIT and bins > histogram.MIN_BINS:
        bins = max(histogram.MIN_BINS, bins // 2)
        taken.append(bins)
        body = respond(points, bins, notes + [typographic(
            f"Histograms drawn with {bins} bins instead of {start} "
            f"({' → '.join(str(b) for b in taken)}, halved at each step) to keep the "
            f"response under the {density.RESPONSE_LIMIT:,}-byte contract; every "
            "histogram keeps its range, and the fitted numbers do not depend on the bins."
        )])
        size = density.wire_size(body)
    if size >= density.RESPONSE_LIMIT:
        body["meta"]["warnings"].append(typographic(
            f"The response is still {size:,} bytes with the curves sampled at {points} "
            f"points and {bins} histogram bins, the coarsest this panel draws, over the "
            f"{density.RESPONSE_LIMIT:,}-byte contract. It is served as it is rather than "
            "with any slice or series withheld; a narrower selection, fewer slices or "
            "fewer series bring it under."
        ))
    return body


def _slice_mode(record: ExperimentRecord, slice_by: str | None) -> str:
    """The request's slicing: its own, else D where there is a separation, else momentum."""
    if slice_by is None:
        slice_by = SLICE_D if "d" in capabilities.of(record).filters else SLICE_MOMENTUM
    if slice_by not in SLICE_MODES:
        raise ValidationError(
            f"slice_by must be one of {', '.join(SLICE_MODES)}; got {slice_by!r}.",
            field="slice_by",
        )
    # D slices need the separation and the networks' split (card "energy");
    # momentum slices read any kind's event table (card "response-b3").
    capabilities.require(
        record, "energy" if slice_by == SLICE_D else "response-b3", field="slice_by")
    return slice_by


def _refuse(field: str, value: object, mode: str) -> None:
    """A parameter of the other slicing is a 422 naming it, never ignored."""
    if value is None:
        return
    other = SLICE_MOMENTUM if mode == SLICE_D else SLICE_D
    raise ValidationError(
        f"{field} applies only with slice_by={other}; this request slices by "
        + ("the A–B separation D." if mode == SLICE_D else "incident momentum (p_slices)."),
        field=field,
    )


def _refuse_oversized(record: ExperimentRecord, p_slices: str | None, series: str | None) -> None:
    """The one momentum view that cannot fit 100 KB is refused, never served over budget.

    Two showers in every 1 GeV bin with both the truth and the model split are 80
    fitted series: 148,703 B on the synthetic two-shower fixture and about 167 KB at
    production scale even at the coarsest rendering the guard reaches. Truth or model
    alone fits, and the momentum windows take all four (decided 2026-10-25).
    """
    if ((p_slices or "").strip().lower() == momentum_mod.MODE_BINS
            and (series or "").strip().lower() == energy.SERIES_ALL
            and len(capabilities.of(record).showers) == 2):
        raise ValidationError(
            "series=all with p_slices=bins draws 80 fitted series on two-shower data, more "
            f"than the {density.RESPONSE_LIMIT:,}-byte response contract can carry. Choose "
            "series=truth or series=model with the 1 GeV bins, or keep series=all with the "
            "momentum windows (p_slices=notebook or a list of centres).",
            field="series",
        )


def _half_width(p_slices: str | None, p_half_width: float | None) -> float:
    """The window half-width in GeV; the 1 GeV bins take none."""
    if p_half_width is None:
        return momentum_mod.HALF_WIDTH_GEV
    if (p_slices or "").strip().lower() == momentum_mod.MODE_BINS:
        raise ValidationError(
            "p_half_width sets the half-width of momentum windows; the 1 GeV bins "
            "(p_slices=bins) have none.",
            field="p_half_width",
        )
    if not (math.isfinite(p_half_width) and p_half_width > 0):
        raise ValidationError(
            f"p_half_width must be a positive number of GeV; got {p_half_width!r}.",
            field="p_half_width",
        )
    return float(p_half_width)


@router.get(
    "/api/energy-distribution",
    summary=(
        "Reconstructed energy distributions across separation-distance or "
        "incident-momentum slices"
    ),
)
def get_energy_distribution(
    con: CursorDep,
    record: RecordDep,
    spec: FilterDep,
    d_edges: str | None = Query(
        None,
        description=(
            "Comma-separated separation-distance slice edges in mm. Defaults to "
            "50,100,150,200; an overflow slice for the well-separated "
            "population is always appended. slice_by=d only."
        ),
    ),
    bins: int | None = Query(
        None, ge=8, le=500,
        description=(
            "Histogram bin count. Left unset, it adapts to the smallest slice "
            "above the histogram threshold, so no histogram is finer than its "
            "own statistics support."
        ),
    ),
    calibrated: bool = Query(
        True,
        description=(
            "Apply the per-shower sampling-fraction calibration so energies are "
            "on the incident-momentum scale. With this off, the raw deposited "
            "sums are returned and are NOT comparable with the E1/E2 benchmarks."
        ),
    ),
    clip_low: float = Query(
        clip_mod.DEFAULT_LOW_PERCENTILE, ge=0.0, le=49.0,
        description="Lower percentile bounding the displayed energy axis.",
    ),
    clip_high: float = Query(
        clip_mod.DEFAULT_HIGH_PERCENTILE, ge=51.0, le=100.0,
        description="Upper percentile bounding the displayed energy axis.",
    ),
    coord_system: str = Query(
        "lab",
        description=(
            "lab | trans | local: which frame's segmentation network splits each "
            "event's energy between the showers - lab the absolute (detector) frame, "
            "trans the per-shower translated frame (legacy), local the Separation-Aligned "
            "(D-Frame), Local (shower-fixed) frame. The panel is the segmentation "
            "reconstruction in every model view; D is always the absolute-frame 3-D "
            "centroid distance. Validated for every experiment; a single shower has "
            "no network and ignores it."
        ),
    ),
    slice_by: str | None = Query(
        None,
        description=(
            "d | momentum. d slices events by the A–B separation (two-shower "
            "experiments, their default); momentum places each shower by its own "
            "incident momentum (the response grid, and the only slicing of "
            "single-shower experiments)."
        ),
    ),
    p_slices: str | None = Query(
        None,
        description=(
            "slice_by=momentum: 'notebook' (default) for the CALIBRATION notebook's "
            "windows 1, 2, 5, 10, 15 and 19 GeV ± p_half_width, 'bins' for the "
            "producer's 1 GeV bins, or comma-separated window centres in GeV. "
            "Windows are half-open and must not overlap."
        ),
    ),
    p_half_width: float | None = Query(
        None,
        description="slice_by=momentum: half-width of each momentum window in GeV (0.5).",
    ),
    series: str | None = Query(
        None,
        description=(
            "slice_by=momentum, two-shower experiments: 'truth' (default) draws "
            "each shower's deposit split by the true segmentation fraction, "
            "'model' the segmentation network's split, 'all' both. A single "
            "shower has one series, its deposit."
        ),
    ),
):
    timer = Timer()
    if coord_system not in ddl.COORD_SYSTEMS:
        raise ValidationError(
            f"coord_system must be one of {', '.join(ddl.COORD_SYSTEMS)}; got {coord_system!r}.",
            field="coord_system",
        )
    mode = _slice_mode(record, slice_by)
    if mode == SLICE_MOMENTUM:
        _refuse("d_edges", d_edges, mode)
        _refuse_oversized(record, p_slices, series)
        return _by_momentum(
            con, record, spec, timer,
            p_slices=p_slices, half_width=_half_width(p_slices, p_half_width),
            series=series, bins=bins, calibrated=calibrated,
            clip_low=clip_low, clip_high=clip_high, coord_system=coord_system,
        )
    for name, value in (("p_slices", p_slices), ("p_half_width", p_half_width),
                        ("series", series)):
        _refuse(name, value, mode)
    edges = parse_edges(d_edges)

    def respond(curve_points: int, bins_override: int | None, extra_warnings: list[str]) -> dict:
        result = energy.compute(
            con, record, spec,
            edges=edges,
            bins=bins if bins_override is None else bins_override,
            calibrated=calibrated,
            clip_low=clip_low,
            clip_high=clip_high,
            coord_system=coord_system,
            curve_points=curve_points,
        )

        warnings: list[str] = list(extra_warnings)
        clipping = result.axis["clipping"]
        if clipping.get("applied") and clipping.get("n_outside"):
            warnings.append(clipping["note"])
        if not result.calibration["applied"]:
            warnings.append(
                "Energies are raw deposited sums, not calibrated to the incident "
                "momentum scale; the isolated-reference benchmarks are hidden "
                "because they would not be comparable."
            )
        empty = [
            s.label for s in result.slices if result.slice_counts.get(s.index, 0) == 0
        ]
        if empty:
            warnings.append(
                "No events in this selection fall in: " + "; ".join(empty) + "."
            )

        # Low statistics are disclosed rather than suppressed. mu and sigma are
        # still reported for these slices; what is withheld is the histogram, and
        # below the curve floor the curve too, so the warning names which.
        labels = {s.index: s.label for s in result.slices}
        thin = sorted({
            labels.get(s.slice_index, str(s.slice_index))
            for s in result.series if s.draw != "histogram"
        })
        if thin:
            warnings.append(
                "Below the " + str(result.thresholds["histogram"]) + "-event "
                "histogram floor: " + "; ".join(thin) + ". mu and sigma there are "
                "plain sample moments (ddof = 1) rather than core refits, quoted "
                "with their standard errors; the density histogram is suppressed "
                "because at this sample size it is a comb of bin-width spikes, and "
                "these curves do not set the density axis."
            )
        degenerate = sorted({
            labels.get(s.slice_index, str(s.slice_index))
            for s in result.series if s.fit.degenerate
        })
        if degenerate:
            warnings.append(
                "All events share one energy to floating-point precision in: "
                + "; ".join(degenerate) + ". No width can be estimated there and "
                "no density curve is drawn."
            )

        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=warnings,
            # The one addition to this payload (plot 4 sits close to the budget):
            # which network produced the reconstruction.
            notes={"network": {"model": "segmentation", "frame": ddl.NETWORK_FRAME[coord_system]}},
        )
        return envelope(meta, **result.as_dict(), filter=spec.as_dict())

    return within_budget(respond)


def _by_momentum(
    con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, timer: Timer, *,
    p_slices: str | None, half_width: float, series: str | None, bins: int | None,
    calibrated: bool, clip_low: float, clip_high: float, coord_system: str,
) -> dict:
    """B3: the selection read once, rendered as often as the guard needs."""
    sample = energy.fetch_momentum(
        con, record, spec, p_slices=p_slices, half_width=half_width,
        series=series, coord_system=coord_system,
    )
    # Only the model split is a network's output; the truth split and a single
    # shower's deposit are not, and the payload names no network for them.
    network = (
        {"model": "segmentation", "frame": ddl.NETWORK_FRAME[coord_system]}
        if any(m.kind == "pred" for m in sample.series) else None
    )

    def respond(curve_points: int, bins_override: int | None, extra_warnings: list[str]) -> dict:
        result = energy.build_by_momentum(
            sample,
            bins=bins if bins_override is None else bins_override,
            calibrated=calibrated,
            clip_low=clip_low,
            clip_high=clip_high,
            curve_points=curve_points,
        )
        meta = ApiMeta(
            table_name=record.table_name,
            exact=True,
            total_ms=timer.elapsed_ms,
            warnings=list(extra_warnings) + momentum_warnings(result),
            notes={"network": network},
        )
        return envelope(meta, **result.as_dict(), filter=spec.as_dict())

    return within_budget(respond)


def _ordinal(value: float) -> str:
    """``1`` -> ``1st``, ``99`` -> ``99th``, ``2.5`` -> ``2.5th``."""
    if not float(value).is_integer():
        return f"{value:g}th"
    n = int(value)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def momentum_warnings(result: energy.EnergyDistribution) -> list[str]:
    """What a reader of the momentum-sliced panel must be told, as sentences."""
    block = result.momentum or {}
    labels = {s.index: s.label for s in result.slices}
    two = block.get("outside_slices", {}).get("b") is not None
    warnings: list[str] = list(result.notices)

    def named(selected: Iterable[energy.SeriesFit]) -> list[str]:
        """Slice labels in slice order, naming the shower when there are two."""
        return [
            labels.get(index, str(index)) + (f" (Shower {shower.upper()})" if two else "")
            for index, shower in sorted({(s.slice_index, s.shower) for s in selected})
        ]

    axes = block.get("slice_axes", [])
    clipped = [a for a in axes if a["n_outside_axis"]]
    if clipped:
        low, high = axes[0]["clipping"]["low_percentile"], axes[0]["clipping"]["high_percentile"]
        warnings.append(
            f"Each slice's energy axis spans the {_ordinal(low)} to {_ordinal(high)} "
            f"percentile of the showers that set it; {sum(a['n_outside_axis'] for a in clipped):,} of "
            f"{sum(a['n_values'] for a in axes):,} values lie beyond their slice's axis ("
            + "; ".join(f"{labels[a['slice']]}: {a['n_outside_axis']:,}" for a in clipped)
            + ") and are excluded from the view but not from the statistics."
        )
    provisional = [labels[a["slice"]] for a in axes if a["provisional"]]
    if provisional:
        warnings.append(
            f"No series reaches the {result.thresholds['histogram']}-shower histogram floor "
            "in: " + "; ".join(provisional) + ". Those energy axes are set from the few "
            "showers there are and are provisional."
        )
    if not result.calibration["applied"]:
        warnings.append(
            "Energies are raw deposited sums, not calibrated to the incident momentum "
            "scale; the measured mean-momentum markers are on that scale and are not "
            "comparable with them."
        )
    empty = [s.label for s in result.slices if result.slice_counts.get(s.index, 0) == 0]
    if empty:
        warnings.append("No showers in this selection fall in: " + "; ".join(empty) + ".")

    outside = block.get("outside_slices", {})
    n_outside = sum(v for v in outside.values() if v)
    if n_outside:
        split = f" (A {outside['a']:,}, B {outside['b']:,})" if two else ""
        one = n_outside == 1
        warnings.append(
            f"{n_outside:,} shower{'' if one else 's'}{split} of this selection "
            f"{'has' if one else 'have'} an incident momentum in no slice: "
            f"{'it is' if one else 'they are'} counted, drawn in no slice, and included "
            "in the calibration."
        )
    absent = block.get("no_deposit", {})
    n_absent = sum(v for v in absent.values() if v)
    if n_absent:
        one = n_absent == 1
        warnings.append(
            f"{n_absent:,} shower{'' if one else 's'} deposited no energy (no hits): "
            f"{'it has' if one else 'they have'} no response to draw and "
            f"{'is' if one else 'are'} in no slice."
        )

    thin = named(s for s in result.series if s.draw != "histogram")
    if thin:
        warnings.append(
            f"Below the {result.thresholds['histogram']}-shower histogram floor: "
            + "; ".join(thin) + ". μ and σ there are plain sample moments (ddof = 1) "
            "rather than core refits, quoted with their standard errors; the density "
            "histogram is suppressed because at this sample size it is a comb of "
            "bin-width spikes, and these curves do not set the density axis."
        )
    degenerate = named(s for s in result.series if s.fit.degenerate)
    if degenerate:
        warnings.append(
            "All showers share one energy to floating-point precision in: "
            + "; ".join(degenerate) + ". No width can be estimated there and no density "
            "curve is drawn."
        )
    return [typographic(w) for w in warnings]
