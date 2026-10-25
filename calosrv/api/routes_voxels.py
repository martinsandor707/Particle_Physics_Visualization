"""``GET /api/voxels`` - the ensemble 3-D voxels of a co-registered frame (Page 2).

The selection's energy as a cloud of 40 mm voxels in the Local frame (every
shower on its own entry point and incident direction; two-shower and
single-shower experiments alike) or the D-frame (two showers per event). The
accumulation, merge, floor, cap and packing are ``query/voxels.py``'s; this
module validates the request, refuses what the experiment cannot serve with a
sentence naming why, quotes the comb and assembles the body under the
100 000-byte contract (:class:`VoxelResponse`).

**Refused, before any scan.** The per-shower translated frame, as a plain
validation error on ``frame``: its exact box-overlap splat has no 3-D
accumulation yet, and the advice names only the frames the experiment offers.
The D-frame on one shower per event: it is built from the A→B separation. The
energy-weighted attention channels without the networks' outputs. An
aggregated experiment, which has no hits (the card's own gate). Every refusal
sentence is set with U+2212.

**The comb is quoted, never re-measured.** The verdict belongs to the raw
accumulation grid before any merge or smoothing (CLAUDE.md section 2). When
the 2-D panels of the same selection, sub-sampling and grid are cached, their
measurement is quoted with its source; otherwise the block is null and the
response says the 2-D panels measure it.

**The D-frame's disclosures travel with the cloud.** Events entering closer
than 80 mm apart have a rotation fixed by anchor noise, so their energy enters
the cloud averaged over azimuth; the anchor residual says how far the two
entry-point definitions sit apart. Both sentences are the 2-D route's
(``frame_canonical``), from the same frame statistics. The Local frame carries
the selection's negative-depth summary, as ``/api/projections`` does.

**Budget.** The whole enveloped body is measured as served
(``api/budget.serve_measured``). While it is over the contract the voxel cap
is lowered: a step is priced from what a voxel actually costs - its packed
bytes in base64, and the ``topk`` entry that disappears with it below 64 -
then measured, and moved to the largest cap whose body, with the sentence
disclosing the step, fits. Voxels are ranked by energy, so the faintest go
first and their energy is counted beyond the cap. When even one voxel does not
fit, nothing is withheld: the body is served whole with the stated overrun.
"""

from __future__ import annotations

from typing import Annotated, Any

import duckdb
import numpy as np
from fastapi import APIRouter, Query

from ..config import Settings
from ..db import ddl
from ..db.registry import ExperimentRecord
from ..errors import ValidationError
from ..grid import frame as frame_mod
from ..grid.frame import KIND_CANONICAL, KIND_LOCAL, KIND_TRANS
from ..models.common import ApiMeta, Timer, envelope
from ..query import canonical, capabilities, density, frame_sql, negative_depth, sampling, voxels
from ..query import planes as planes_mod
from ..query import stagger as stagger_mod
from ..query.filters import FilterSpec
from ..text import typographic
from . import budget, frame_canonical, frame_shower
from .deps import CursorDep, FilterDep, SettingsDep, capable

router = APIRouter()

_TRANS = (
    "frame=trans is not offered: the per-shower translated frame integrates each footprint by "
    "exact box-overlap splatting, which has no 3-D accumulation yet."
)

#: Where a quoted comb comes from, and what is said when there is none.
_COMB_QUOTED = (
    "Comb quoted from the 2-D {title} panels' measurement on the raw {pitch:g} mm accumulation "
    "grid of this selection, at the same sub-sampling and grid; no comb is measured on the "
    "merged {voxel:g} mm voxels, where the merge would hide it."
)
_COMB_ABSENT = (
    "Comb not measured here: it is measured by the 2-D {title} panels on the raw {pitch:g} mm "
    "accumulation grid, before any merge or smoothing, and quoted here once they have been "
    "opened for this selection. No comb is measured on the merged {voxel:g} mm voxels."
)

#: The cache counters under names of their own: a served body carries no
#: ``hits`` or ``points`` key anywhere (CLAUDE.md section 1.1).
_CACHE_COUNTERS = {"hits": "cache_hits", "misses": "cache_misses"}


def offered_frames(record: ExperimentRecord) -> tuple[str, ...]:
    """The voxel frames this experiment's kind offers: Local, and the D-frame on two showers."""
    caps = capabilities.of(record)
    return tuple(f for f in voxels.FRAMES if caps.can(f"frame-{f}"))


def _advice(record: ExperimentRecord) -> str:
    offered = offered_frames(record)
    if not offered:
        return "This experiment offers no 3-D ensemble frame."
    return "Use " + " or ".join(f"frame={f}" for f in offered) + "."


def _invalid(text: str, field: str) -> ValidationError:
    return ValidationError(typographic(text), field=field)


def _validate(record: ExperimentRecord, frame: str, channel: str, model: str, anchor: str,
              coordinates: str) -> None:
    """Refuse an unknown value (400-class typos) or a view the experiment cannot serve."""
    if frame == KIND_TRANS:
        raise _invalid(f"{_TRANS} {_advice(record)}", "frame")
    if frame not in voxels.FRAMES:
        offered = offered_frames(record) or voxels.FRAMES
        raise _invalid(f"frame must be one of {', '.join(offered)}; got {frame!r}.", "frame")
    for name, value, allowed in (
        ("channel", channel, voxels.CHANNELS),
        ("model", model, ddl.MODELS),
        ("anchor", anchor, frame_sql.ANCHORS),
        ("coordinates", coordinates, frame_sql.SOURCES),
    ):
        if value not in allowed:
            raise _invalid(f"{name} must be one of {', '.join(allowed)}; got {value!r}.", name)
    if anchor != frame_sql.ANCHOR_BACKPROJECTED and frame != KIND_CANONICAL:
        raise _invalid(
            "anchor chooses the D-frame's entry-point definition and applies to frame=canonical "
            f"only; got anchor={anchor!r} with frame={frame!r}.", "anchor")
    if coordinates != frame_sql.SOURCE_FILE and frame != KIND_LOCAL:
        raise _invalid(
            "coordinates chooses the Local frame's coordinate source and applies to frame=local "
            f"only; got coordinates={coordinates!r} with frame={frame!r}.", "coordinates")
    capabilities.require(record, f"frame-{frame}", field="frame")
    if channel != planes_mod.CHANNEL_DENSITY:
        capabilities.require(record, "vox-attention", field="channel")


def _typeset_problem(error: ValidationError) -> None:
    """Set a refusal's sentences with U+2212, whichever module wrote them."""
    error.detail = typographic(error.detail)
    error.args = (error.detail,)
    if isinstance(error.extra.get("reason"), str):
        error.extra["reason"] = typographic(error.extra["reason"])


def _comb(settings, record, spec, bundle, n_events: int) -> tuple[dict[str, Any] | None, str]:
    """The matching 2-D bundle's raw-grid comb, and the sentence saying where it came from."""
    words = {"title": voxels.TITLE[bundle.kind], "pitch": bundle.grid.pitch,
             "voxel": voxels.MERGE * bundle.grid.pitch}
    two_d = voxels.cached_2d_bundle(settings, record, spec, bundle)
    if two_d is None:
        return None, _COMB_ABSENT.format(**words)
    if bundle.kind == KIND_LOCAL:
        comb = frame_shower._comb_report(two_d, n_events)
    else:
        comb = frame_canonical._comb_report(
            stagger_mod.detect(two_d.xy.planes["e"]),
            stagger_mod.intensity_lag1(two_d.xy.planes["e"]),
            bundle.subsample_k, n_events,
        )
    return comb, _COMB_QUOTED.format(**words)


def _n_label(n: int) -> str | None:
    """The low-N label of the cloud, in the ensemble views' terms."""
    if n == 0:
        return "No event in the selection is placed in this frame: nothing is drawn."
    if n == 1:
        return ("N = 1: one event's own deposit, not an ensemble; ρ_ref and the cloud are "
                "labelled provisional.")
    if n < frame_mod.PROVISIONAL_N:
        return (f"N = {n}: weak evidence; the cloud and its reference ρ_ref are labelled "
                "provisional.")
    return None


def _b64_len(n_bytes: int) -> int:
    """Characters of ``n_bytes`` bytes in padded base64."""
    return 4 * ((int(n_bytes) + 2) // 3)


def _beyond_cap_notice(n_beyond: int, cap: int, fraction: float) -> str:
    return typographic(
        f"{n_beyond:,} voxel(s) above the floor lie beyond the {cap:,}-voxel cap, ranked by "
        f"energy: {100.0 * fraction:.3g}% of the energy, counted and not drawn.")


class VoxelResponse:
    """One request's voxel bundle, and its body at any voxel cap.

    Every database read happens here, once: the frame statistics and bundle,
    the quoted comb, the negative-depth summary. :meth:`build` then renders
    the body at a cap from memory, and :meth:`serve` runs the measured guard
    over it. The timings and the cache counters are read once too, so one
    rendering measures the same at every call and a step the guard verified
    is the step it serves.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        record: ExperimentRecord,
        spec: FilterSpec,
        settings: Settings,
        frame: str = KIND_LOCAL,
        channel: str = planes_mod.CHANNEL_DENSITY,
        model: str = "segmentation",
        anchor: str = frame_sql.ANCHOR_BACKPROJECTED,
        coordinates: str = frame_sql.SOURCE_FILE,
        cap: int = voxels.DEFAULT_CAP,
        preview: bool = False,
        timer: Timer | None = None,
    ) -> None:
        timer = timer or Timer()
        self.record, self.spec, self.frame, self.channel = record, spec, frame, channel
        self.model, self.anchor, self.coordinates, self.cap = model, anchor, coordinates, cap
        self.decision = sampling.decide(record, preview, settings.sample_percent)
        self.footprint = canonical.cell_footprint(con, record)
        bundle, stats, grid, k, was_cached = voxels.bundle_for(
            con, record, spec, settings, frame, self.footprint, self.decision.sampled,
            self.decision.percent, model, anchor=anchor, source=coordinates,
            any_model=channel == planes_mod.CHANNEL_DENSITY)
        self.bundle, self.stats, self.grid, self.k, self.was_cached = bundle, stats, grid, k, was_cached
        self.classified = voxels.classify(bundle, channel)
        self.n = stats.n_events
        self.two = len(capabilities.of(record).showers) == 2
        self.n_showers = self.n * (2 if self.two else 1)
        self.comb, self.comb_source = _comb(settings, record, spec, bundle, self.n)
        self.cam = planes_mod.cam_note(model, KIND_LOCAL if frame == KIND_LOCAL else "lab", channel)
        self.coordinate_block = (frame_shower._coordinates_block(bundle, record, KIND_LOCAL)
                                 if frame == KIND_LOCAL else None)
        # C9 in the Local frame, where w is the depth it is defined on: the
        # cloud draws voxels upstream of P0, and the 2-D Local response's
        # summary of those hits travels with it (event table only).
        self.negative_w = (negative_depth.summarise(con, record, spec)
                           if frame == KIND_LOCAL else None)
        self.n_label = _n_label(self.n)
        self.warnings = [self.decision.reason] if self.decision.sampled else []
        if self.n == 0:
            self.warnings.append("No events match the current selection in this frame.")
        e_order = bundle.sums["e"][self.classified.order]
        self._energy_above = np.cumsum(e_order) if e_order.size else np.zeros(0)
        self._total_energy = self.classified.energy["total"]
        cache_info = voxels.cache_for(settings).info()
        self._cache_info = {_CACHE_COUNTERS.get(key, key): value for key, value in cache_info.items()}
        self._total_ms = timer.elapsed_ms
        #: The step sentences disclosed so far, in order.
        self._steps: list[str] = []
        self._last: tuple[int, dict[str, Any]] | None = None

    # ------------------------------------------------------------ text --

    def _frame_notice(self) -> str:
        n, n_showers = self.n, self.n_showers
        if self.frame == KIND_LOCAL:
            return (f"Local frame: {n:,} event(s), {n_showers:,} shower(s) superimposed at their "
                    "own entry points, each rotated so its incident direction is +w"
                    + ("; a voxel sums both showers of an event." if self.two else "."))
        return (f"D-frame: {n:,} event(s) co-registered on the midpoint of their two entry "
                "points, the A→B separation along +x′ and the front face at z′ = 0.")

    def notices(self, rendered: dict[str, Any], steps: list[str]) -> list[str]:
        """Every disclosure of the body, the guard's steps first."""
        frame, stats, bundle, grid = self.frame, self.stats, self.bundle, self.grid
        title = voxels.TITLE[frame]
        b = rendered["budget"]
        f = b["energy_fraction"]
        out: list[str] = list(steps)
        out.append(self._frame_notice())
        if frame == KIND_CANONICAL:
            # The 2-D D-frame's own sentences, from the same frame statistics:
            # the cloud draws no axis, so the axis-statistics clause is left out.
            ill = frame_canonical.ill_conditioned_notice(stats.n_ill_conditioned,
                                                         axis_statistics=False)
            if ill:
                out.append(ill)
            residual = frame_canonical.anchor_residual_notice(stats)
            if residual:
                out.append(residual)
        k, fx, fy = self.k, self.footprint[0], self.footprint[1]
        out.append(
            f"Each cell's {fx:.2f} × {fy:.2f} mm footprint was split into {k} × {k}"
            + (f" × {bundle.k_z}" if frame == KIND_LOCAL else "")
            + " sub-deposits, moved with its "
            + ("shower" if frame == KIND_LOCAL else "event")
            + f" and binned on the {grid.pitch:g} mm accumulation grid; pairs of bins were merged "
            f"into {voxels.MERGE * grid.pitch:g} mm voxels centred on the origin. A drawn cube is "
            "axis-aligned and cannot tilt, so a rotated cell appears as the voxels its "
            "sub-deposits fall in.")
        reference = "ρ_ref" if self.channel == planes_mod.CHANNEL_DENSITY else "cam_ref"
        out.append(
            f"Voxels below 10⁻³ of {reference} are not drawn: {b['n_below_floor']:,} voxel(s) "
            f"holding {100.0 * f['below_floor']:.3g}% of the energy, counted.")
        if b["n_beyond_cap"]:
            out.append(_beyond_cap_notice(b["n_beyond_cap"], b["cap"], f["beyond_cap"]))
        if b["n_partial_edge"]:
            out.append(rendered["grid"]["partial_edge"]["note"])
        if f["outside_grid"] > 0:
            out.append(
                f"{100.0 * f['outside_grid']:.3g}% of the energy fell outside the accumulation "
                "grid; it is counted, not drawn.")
        if self.n_label:
            out.append(self.n_label)
        if stats.n_excluded_no_frame:
            out.append(
                f"{stats.n_excluded_no_frame:,} selected event(s) have no A-B separation (no "
                f"shower-A centroid); they are excluded from N and from the {title} voxels."
                if self.two else
                f"{stats.n_excluded_no_frame:,} selected event(s) have no incident direction or "
                f"entry point P0; they are excluded from N and from the {title} voxels.")
        if self.spec.include_undefined_d and self.two:
            out.append(
                "Events with an undefined A-B separation are not co-registered: including them "
                f"changes nothing in the {title} voxels.")
        n_ab = getattr(stats, "n_ab", 0)
        if frame == KIND_LOCAL and n_ab:
            out.append(f"{n_ab:,} hit(s) labelled 'A+B' sit at the origin of this frame and are "
                       "counted with shower B.")
        if self.cam is not None:
            out.append(self.cam["note"])
            zero = getattr(stats, "cam_zero", {}).get(planes_mod.view(self.channel).cam, 0)
            if zero:
                out.append(f"{zero:,} selected event(s) have an all-zero map from the {self.model} "
                           "network in this frame; they contribute energy but no attention.")
        if self.channel == planes_mod.CHANNEL_SHAPCAM_ENERGY:
            out.append(
                "Σ E × Shap-CAM is signed: each sign has its own three decades below the peak "
                "|value|, the two halves meeting at the floor; nothing is clipped.")
        out.append(self.comb_source)
        if self.comb is not None:
            out.append(self.comb["note"])
        if self.coordinate_block is not None:
            out.append(self.coordinate_block["note"])
        if frame == KIND_LOCAL:
            out.append(
                "w is each shower's incident direction by construction; no ensemble axis is "
                "drawn because none could carry information.")
        else:
            out.append(
                "No ensemble axis is drawn on the cloud; the D-frame's axes, with their "
                "dispersion bands and Student-t envelopes, are drawn by the 2-D panels.")
        out.append(rendered["rho"]["norm_note"])
        return [typographic(text) for text in out]

    def _frame_block(self) -> dict[str, Any]:
        frame, stats, bundle, grid, k = self.frame, self.stats, self.bundle, self.grid, self.k
        canonical_frame = frame == KIND_CANONICAL
        gapless = frame_mod.minimum_gapless_subsample(max(self.footprint), grid.pitch)
        block = {
            "kind": frame,
            "title": voxels.TITLE[frame],
            "symbols": voxels.SYMBOLS[frame],
            "n_events": self.n,
            "n_selected": stats.n_selected,
            "n_excluded_no_frame": stats.n_excluded_no_frame,
            "n_showers": self.n_showers,
            "provisional": self.n < frame_mod.PROVISIONAL_N,
            "n_label": self.n_label,
            "anchor": (canonical.ANCHOR_DEFINITIONS[self.anchor] if canonical_frame
                       else "own_shower_entry_point"),
            # Events whose two entry points lie closer than the threshold have
            # an effectively random rotation (D-frame only; null in Local).
            "n_ill_conditioned": stats.n_ill_conditioned if canonical_frame else None,
            "ill_conditioned_threshold_mm": (frame_mod.ILL_CONDITIONED_D_MM if canonical_frame
                                             else None),
            "anchor_residual": dict(stats.anchor_residual) if canonical_frame else None,
            "splat": {
                "regime": "subdeposit3d" if frame == KIND_LOCAL else "subdeposit2d",
                "k": k,
                "k_z": bundle.k_z,
                "footprint_mm": [self.footprint[0], self.footprint[1]],
                "gapless_k": gapless,
                "gapless": k >= gapless,
                "budget_rows": frame_mod.SUBSAMPLE_ROW_BUDGET,
            },
            "depth": {
                "policy": "uniform_bins" if frame == KIND_LOCAL else "native_layers",
                "text": (
                    "uniform bins of the layer pitch along w, never merged or smoothed"
                    if frame == KIND_LOCAL else
                    "the native sampling layers, each one layer pitch thick, never merged"),
                "pitch_mm": bundle.dz,
                "n": grid.n_z,
            },
            "coordinates": self.coordinates if frame == KIND_LOCAL else None,
            "coordinate_check": self.coordinate_block,
            "comb": self.comb,
            "comb_source": self.comb_source,
            "planned_from": (
                "dataset energy-weighted 10⁻⁴ and 0.9999 quantiles plus half a footprint"
                if frame == KIND_LOCAL else
                "the selection's largest entry separation and incident angle plus a "
                f"{frame_mod.SHOWER_MARGIN_MM:g} mm shower margin"),
        }
        if self.negative_w is not None:
            block["negative_w"] = self.negative_w
        return block

    # ----------------------------------------------------------- body --

    def build(self, cap: int, steps: list[str]) -> dict[str, Any]:
        """The whole enveloped body at ``cap`` voxels, with ``steps`` disclosed first."""
        rendered = voxels.render(self.bundle, self.channel, cap, self.classified)
        rendered["budget"]["cap_requested"] = self.cap
        meta = ApiMeta(
            table_name=self.record.table_name,
            exact=self.bundle.exact,
            query_ms=0.0 if self.was_cached else self.bundle.query_ms,
            total_ms=self._total_ms,
            cached=self.was_cached,
            warnings=list(self.warnings),
            notes={
                "frame": self.frame,
                "channel": self.channel,
                "model": self.model,
                "anchor": self.anchor if self.frame == KIND_CANONICAL else None,
                "coordinates": self.coordinates if self.frame == KIND_LOCAL else None,
                "sample_percent": self.decision.percent if self.decision.sampled else 100.0,
                "cam": self.cam,
                "cache": dict(self._cache_info),
                "notices": self.notices(rendered, steps),
            },
        )
        body = voxels.typeset(envelope(
            meta,
            frame=self._frame_block(),
            grid=rendered["grid"],
            voxels=rendered["voxels"],
            scale=rendered["scale"],
            rho=rendered["rho"],
            budget=rendered["budget"],
            topk=rendered["topk"],
            filter=self.spec.as_dict(),
        ))
        self._last = (cap, body)
        return body

    # ---------------------------------------------------------- guard --

    def step_sentence(self, old: int, new: int, size: int, limit: int) -> str:
        """The sentence disclosing one step of the guard."""
        return typographic(
            f"The response measured {size:,} bytes against the {limit:,}-byte contract, so the "
            f"voxel cap was lowered from {min(old, self.classified.n_above):,} to {new:,}: "
            "voxels are ranked by energy, so the faintest go first and their energy is counted "
            "beyond the cap.")

    def describe(self, old: int, new: int, size: int, limit: int) -> str:
        """``serve_measured``'s disclosure of a step it takes, recorded in order."""
        text = self.step_sentence(old, new, size, limit)
        self._steps.append(text)
        return text

    def _body_at(self, cap: int) -> dict[str, Any]:
        if self._last is not None and self._last[0] == cap:
            return self._last[1]
        return self.build(cap, list(self._steps))

    def priced_cap(self, cap_now: int, size: int, limit: int) -> int | None:
        """The largest cap below the current count whose body the price says fits, or None.

        The price is what lowering the cap removes from the measured body: the
        ``xy`` ordinals and ``code`` bytes of the dropped voxels as base64
        characters, and below 64 voxels the ``topk`` entries that go with them
        (at the current body's mean entry size); and what it adds: this step's
        own sentence and, on the first step, the beyond-cap sentence.
        """
        current = min(cap_now, self.classified.n_above)
        body = self._body_at(cap_now)
        xy_bytes = 4 if body["voxels"]["dtype"]["xy"] == "u16le" else 2
        topk = body["topk"]
        entry = (sum(density.wire_size(t) for t in topk) + len(topk)) / len(topk) if topk else 0.0
        first = body["budget"]["n_beyond_cap"] == 0

        def priced(c: int) -> float:
            saved = (_b64_len(xy_bytes * current) - _b64_len(xy_bytes * c)
                     + _b64_len(current) - _b64_len(c)
                     + entry * (len(topk) - min(c, voxels.TOPK)))
            added = density.wire_size(self.step_sentence(cap_now, c, size, limit)) + 1
            if first:
                added += density.wire_size(_beyond_cap_notice(
                    self.classified.n_above - c, c, self._beyond_fraction(c))) + 1
            return size - saved + added

        if current <= 1 or priced(1) >= limit:
            return None
        lo, hi = 1, current
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if priced(mid) < limit:
                lo = mid
            else:
                hi = mid
        return lo

    def _beyond_fraction(self, cap: int) -> float:
        if self._total_energy <= 0 or not self._energy_above.size:
            return 0.0
        kept = float(self._energy_above[min(cap, self._energy_above.size) - 1]) if cap > 0 else 0.0
        return max(0.0, float(self._energy_above[-1]) - kept) / self._total_energy

    def shrink(self, cap_now: int, size: int, limit: int) -> int | None:
        """The next cap: priced, then measured; the largest that fits, or None if none does.

        The priced cap is measured with this step's sentence in the body. From
        there the search gallops up while caps keep fitting, or down until one
        does, and bisects the last interval. Either way the step lands on a cap
        that fits, with the next one up not fitting, so one disclosed step
        suffices. When even one voxel does not fit, nothing is withheld
        (None): the body is served whole with the stated overrun.
        """
        current = min(cap_now, self.classified.n_above)
        if current <= 1:
            return None
        taken = list(self._steps)
        measured: dict[int, bool] = {}

        def fits(c: int) -> bool:
            if c not in measured:
                body = self.build(c, taken + [self.step_sentence(cap_now, c, size, limit)])
                measured[c] = density.wire_size(body) < limit
            return measured[c]

        guess = self.priced_cap(cap_now, size, limit)
        if guess is None:
            if not fits(1):
                return None
            lo, hi = 1, current
        elif fits(guess):
            # Up past a price that was cautious: ``hi`` is the first cap known
            # not to fit (``current`` is over even without this step's sentence).
            lo, step = guess, 1
            while lo + step < current and fits(lo + step):
                lo += step
                step *= 2
            hi = min(lo + step, current)
        else:
            # Down past a price that was bold, to a cap that fits.
            hi, step = guess, 1
            while hi - step > 1 and not fits(hi - step):
                hi -= step
                step *= 2
            lo = hi - step
            if lo <= 1:
                if not fits(1):
                    return None
                lo = 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if fits(mid):
                lo = mid
            else:
                hi = mid
        return lo

    def serve(self) -> dict[str, Any]:
        """The body under the contract, every step of the guard disclosed in it."""
        self._steps = []
        return budget.serve_measured(
            self.build, self.cap, self.shrink, self.describe,
            remedy="a narrower selection or a lower cap brings it under")


@router.get(
    "/api/voxels",
    summary="Ensemble 3-D voxels of the Local frame or the D-frame, floored, capped and packed",
)
def get_voxels(
    con: CursorDep,
    # Before the filter: a kind that cannot serve the card is refused as such,
    # not for a selection it could never have made.
    record: Annotated[ExperimentRecord, capable("vox-ensemble")],
    spec: FilterDep,
    settings: SettingsDep,
    frame: str = Query(
        KIND_LOCAL,
        description=(
            "local (default): Local (shower-fixed), every shower on its own entry point P0 and "
            "rotated so its incident direction is +w. canonical: the Separation-Aligned D-frame, "
            "every event on the midpoint of its two entry points with the A→B separation along "
            "+x′; two showers per event only. trans is refused: its exact box-overlap splat has "
            "no 3-D accumulation yet."
        ),
    ),
    channel: str = Query(
        planes_mod.CHANNEL_DENSITY,
        description=(
            "density (default): ensemble energy density, GeV/mm³/event. gradcam_energy: Σ E × "
            "Grad-CAM. shapcam_energy: Σ E × Shap-CAM, signed. The attention channels need the "
            "networks' outputs; their maps are normalised per event or per shower, so the "
            "ensemble shows where the network attends, not how strongly."
        ),
    ),
    model: str = Query(
        "segmentation",
        description=(
            "angle | energy | segmentation: the network whose CAM maps an attention channel reads "
            "(the Local frame's networks; the D-frame uses the absolute-frame networks). Accepted "
            "and unused for density."
        ),
    ),
    anchor: str = Query(
        frame_sql.ANCHOR_BACKPROJECTED,
        description="frame=canonical only: backprojected (default) or p0, as /api/projections.",
    ),
    coordinates: str = Query(
        frame_sql.SOURCE_FILE,
        description="frame=local only: file (default) or computed, as /api/projections.",
    ),
    cap: int = Query(
        voxels.DEFAULT_CAP, ge=voxels.MIN_CAP, le=voxels.DEFAULT_CAP,
        description=(
            "Most voxels shipped, ranked by energy among those above the 10⁻³ floor. The "
            "whole-response guard lowers it if the body would exceed 100 000 bytes, and says so."
        ),
    ),
    preview: bool = Query(
        False,
        description="Serve from the 10% unbiased sample for drag preview (exact=false).",
    ),
):
    timer = Timer()
    try:
        _validate(record, frame, channel, model, anchor, coordinates)
    except ValidationError as error:
        _typeset_problem(error)
        raise
    return VoxelResponse(con, record, spec, settings, frame=frame, channel=channel, model=model,
                         anchor=anchor, coordinates=coordinates, cap=cap, preview=preview,
                         timer=timer).serve()
