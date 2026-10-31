"""The selection's detector cells as cubes: the Absolute-frame 3-D card of Page 2.

``GET /api/selection-cells`` (``api/routes_selection_cells.py``) draws the whole
current selection in the laboratory frame - Martin's directive of 2026-10-31:
the Models page's "One Event in 3-D — Detector Cells" card shows the
selection by default there, one event becoming an option. Every hit of every
selected event, both showers, is summed into its detector cell, and each
populated cell is one cube. The body is the one-event cubes' body
(``/api/event?format=voxels&frame=lab&shower=both``, ``query/voxel_event.py``)
with a ``selection`` block in place of ``event``, so the browser's decoder
reads it unchanged.

**Only the laboratory frame.** Its cells are one lattice shared by every event,
so a selection sums on it without moving anything. The per-shower translated
frame moves each shower by its own entry point and has no common lattice to
sum on; Local and the D-frame tilt or turn the cells, and their selection is
the co-registered cloud of ``GET /api/voxels``.

**Both showers, summed.** As Page 1's Absolute projections sum them - A, B and
'A+B' rows alike - and as the paired 2-D cards beside this one, which reuse
those projections and cannot split showers either. A cube's 2-bit shower code
says whose rows the cell holds over the selection (the one-event builder's
:func:`voxel_event.shower_codes`): over many events most cells hold both
showers' rows and take code 3.

**Energy is a mean per selected event.** A cube's energy is
``Σ E / N`` over the selection, and the colour its volumetric density
``Σ E / (N · V)`` in GeV/mm³ per event, on the one-event view's logarithmic
ramp. N is the number of selected events - ``summary.summarise``'s count, the
``selection.n_events`` every absolute-frame response reports, and the count
Page 1's co-registered frames divide by (``density.py``, ``bundle.n_events``):
there every selected event the frame can place, here every selected event,
since every hit has a laboratory cell. An event with no hit in a cell adds
zero to that cell's mean. Every energy the body quotes - the cap block, the
depth profile, the exact values - is the same mean per selected event.

**The network channels are energy-weighted means over hits.** ``gradcam`` and
``shapcam`` colour a cube by ``Σ E·v / Σ E`` over the selection's hits in the
cell that carry a finite value, read from the laboratory-frame columns of the
chosen network (``ddl.cam_column(model, 'lab', channel)``): Page 1's mean
(``planes.py``, "mean over the bin's hits, weighted by energy") and the
one-event builder's per-cell mean (``voxel_event.merge_cells``). A hit with no
value is left out of both sums rather than read as zero attention; Page 1's
planes keep its energy in the denominator, so the two agree wherever every
hit carries a value, and the count of those that do not travels in the
notes. The ramps are the one-event view's: Grad-CAM linear on [0, 1], Shap-CAM
signed linear on [−1, +1]. Shap-CAM's positive and negative parts are summed
apart (``Σ E·max(v, 0)``, ``Σ E·min(v, 0)``, Page 1's ``esp`` and ``esn``), so
the depth profile's signed shares are sums over hits, never a cell's mean
times its energy.

**Not served: the segmentation error and the species.** Both are per-event
quantities with no selection projection on Page 1; the route refuses them
naming ``channel``, and the card falls back to energy.

**The floor is the drawn cubes'.** The one-event cells regime floors its ramp
at the 1st percentile of the drawn showers' cells, which for one event are
the cubes on screen. A selection holds far more cells than the cap draws, and
a floor over all of them would spend the bottom of the ramp on cells that are
not drawn; so the floor here is the 1st percentile of the drawn cubes'
positive densities (CLAUDE.md section 2: a display range follows the evidence
on screen), ``floor_basis`` ``drawn_cells``. A cube below it is drawn at the
lowest colour, flagged and counted; a degenerate range is stated as such.

**One exact scan, cached.** The projection table under the selection's
filter, ``GROUP BY ix, iy, iz``: Σ E, the row count, the rows' origins
(``bit_or(1 << org)``) and, for a network channel, the valued hits' Σ E and
the two signed parts of Σ E·v. Never the drag-preview sample
(``query/sampling.py``). The per-cell sums are cached per selection, channel
and network in a named cache of their own, behind ``physics_cache``'s single
flight and heavy-scan gate; the window and the cap are rendering, so changing
either re-renders from memory without a scan. The energy channel is served
from a network channel's sums of the same selection when they are cached.

**Rendering.** :class:`SelectionBuilder` is the one-event
:class:`voxel_event.Builder` in its cells regime, holding per-cell sums
instead of hit rows: the window rule (``voxel_event.frame_windows``) on the
selection's cells, the cap by energy rank, the packing, the exact top values
and the per-layer depth profile are the event's, worded per selected event.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, ClassVar

import duckdb
import numpy as np

from ..db import ddl, naming
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from ..errors import NotFoundError, ValidationError
from ..grid import frame as frame_mod
from ..text import typographic
from . import cache as cache_mod
from . import capabilities, event_inspector, frame_sql, physics_cache, planes, summary, voxel_event
from . import showers as showers_mod
from .filters import FilterSpec
from .voxel_event import CHANNEL_ENERGY, CHANNEL_GRADCAM, CHANNEL_SHAPCAM, FRAME_LAB

# ------------------------------------------------------------ vocabulary --

#: The channels the selection view colours by; the network channels among them.
CHANNELS: tuple[str, ...] = (CHANNEL_ENERGY, CHANNEL_GRADCAM, CHANNEL_SHAPCAM)
NETWORK_CHANNELS: tuple[str, ...] = (CHANNEL_GRADCAM, CHANNEL_SHAPCAM)
#: The one-event channels that have no selection projection.
PER_EVENT_CHANNELS: tuple[str, ...] = (voxel_event.CHANNEL_SEGERR, voxel_event.CHANNEL_SPECIES)

#: The cube cap: the cloud's default (most cubes drawn, ranked by energy) and the event's bounds.
DEFAULT_CAP = voxel_event.MAX_CAP
MIN_CAP = voxel_event.MIN_CAP
MAX_CAP = voxel_event.MAX_CAP

UNIT = "GeV/mm^3/event"
#: The depth profile's attention sums, Σ E·v / N.
ATTENTION_UNIT = "GeV/event"

#: Where the energy ramp's floor is measured: the cubes drawn.
FLOOR_BASIS = "drawn_cells"

#: The named cache of per-cell sums: a production selection's whole-detector
#: sums are 14 bytes per populated cell (38 with a network channel's), a few
#: tens of MB for the 1.3 million cells of the lattice at most.
CACHE_NAME = "selection_cells"
CACHE_ENTRIES = 32
CACHE_MAX_BYTES = 128 * 1024 ** 2
#: Bumped when the cached sums change shape, so a stale entry is never read.
CACHE_VERSION = 1

_PER_EVENT = (
    "channel={channel!r} is a per-event quantity with no selection projection on Page 1, so the "
    "selection view does not draw it; it draws energy, gradcam or shapcam. Ask for one event "
    "(GET /api/event?format=voxels) to draw {channel}."
)

_DEPTH_NOTE = (
    "Per-layer sums, per selected event, of every cell inside the window, before the cap: Σ E / N "
    "and, on a network channel, Σ E·v / N (Shap-CAM's positive and negative parts apart), the "
    "exact shares the slice readout quotes."
)

_NAMES = {CHANNEL_GRADCAM: "Grad-CAM", CHANNEL_SHAPCAM: "Shap-CAM"}


# ------------------------------------------------------------- validation --


def resolve(record: ExperimentRecord, channel: str, model: str) -> None:
    """Refuse what the request or the data cannot serve, before any scan.

    A malformed value is the plain validation error naming its parameter; the
    segmentation error and the species are refused naming ``channel``, as
    per-event quantities. A network channel on an experiment without the
    networks' columns is refused exactly as ``voxel_event.resolve`` refuses it,
    under the ``vox-attention`` gate.
    """
    if channel in PER_EVENT_CHANNELS:
        raise ValidationError(_PER_EVENT.format(channel=channel), field="channel")
    for name, value, allowed in (("channel", channel, CHANNELS), ("model", model, ddl.MODELS)):
        if value not in allowed:
            raise ValidationError(f"{name} must be one of {', '.join(allowed)}; got {value!r}.", field=name)
    if channel in NETWORK_CHANNELS:
        capabilities.require_choice(record, "channel", channel, voxel_event.channels_offered(record),
                                    "vox-attention")


# ------------------------------------------------------------------- scan --


@dataclass
class CellSums:
    """One selection's hits summed per detector cell, both showers: what the scan returns and the cache keeps.

    Cells are in (iz, iy, ix) order. ``energy`` is the selection's total
    (not yet divided by N). A network channel's sums run over the hits that
    carry a finite value: their energy, and Σ E·max(v, 0) and Σ E·min(v, 0)
    (≤ 0); None on the energy channel.
    """

    ix: np.ndarray        # u16 lattice ordinals
    iy: np.ndarray        # u16
    iz: np.ndarray        # u8
    energy: np.ndarray    # Σ E, GeV
    origins: np.ndarray   # u8 bit mask of the row origins present: bit org (A 0, B 1, 'A+B' 2)
    n_events: int         # selected events: the per-event normaliser N
    n_hits: int           # hits summed
    channel: str          # energy, or the network channel whose sums follow
    model: str | None     # the network those sums read
    query_ms: float
    valued_energy: np.ndarray | None = None
    positive: np.ndarray | None = None
    negative: np.ndarray | None = None
    n_valued: int = 0     # hits carrying a finite value of the channel

    @property
    def n(self) -> int:
        return int(self.energy.size)

    @property
    def nbytes(self) -> int:
        arrays = (self.ix, self.iy, self.iz, self.energy, self.origins,
                  self.valued_energy, self.positive, self.negative)
        return int(sum(a.nbytes for a in arrays if a is not None)) + 512


def scan_sql(record: ExperimentRecord, spec: FilterSpec, channel: str, model: str | None) -> str:
    """The one aggregation: the selection's hits grouped by detector cell.

    Column names come from ``ddl``'s allowlisted builders; a request string
    never reaches the SQL. ``FILTER (WHERE isfinite(v))`` keeps a hit without
    a value (NULL or NaN) out of every network sum.
    """
    proj = quote(naming.proj_table(record.table_name))
    columns = ["p.ix", "p.iy", "p.iz", "sum(p.energy) AS e", "count(*) AS n",
               "bit_or(1 << p.org) AS origins"]
    if channel in NETWORK_CHANNELS:
        assert model is not None
        v = f"CAST(p.{ddl.cam_column(model, 'lab', channel)} AS DOUBLE)"
        valued = f"FILTER (WHERE isfinite({v}))"
        columns += [f"sum(p.energy) {valued} AS ef",
                    f"sum(p.energy * greatest({v}, 0.0)) {valued} AS esp",
                    f"sum(p.energy * least({v}, 0.0)) {valued} AS esn",
                    f"count(*) {valued} AS nf"]
    return (f"SELECT {', '.join(columns)} FROM {proj} p WHERE {spec.where_sql('p')} "
            "GROUP BY p.ix, p.iy, p.iz")


def explain(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, channel: str,
            model: str | None) -> str:
    """``EXPLAIN`` of the cell query, for the single-scan test."""
    rows = con.execute("EXPLAIN " + scan_sql(record, spec, channel, model), spec.params()).fetchall()
    return "\n".join(str(r[-1]) for r in rows)


def _filled(column: Any, dtype: Any, fill: float = 0) -> np.ndarray:
    """A fetched column with its NULLs (a sum over no valued hit) as ``fill``."""
    return np.asarray(np.ma.filled(np.ma.asarray(column), fill), dtype=dtype)


def scan(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, channel: str,
         model: str | None) -> CellSums:
    """Run the aggregation and count the selection's events; ``model`` is None on the energy channel."""
    started = time.perf_counter()
    data = con.execute(scan_sql(record, spec, channel, model), spec.params()).fetchnumpy()
    # N from the event table: per-event counts never come from hit rows (query/__init__.py).
    n_events = summary.summarise(con, record, spec).n_events
    query_ms = (time.perf_counter() - started) * 1000.0
    ix = _filled(data["ix"], np.uint16)
    iy = _filled(data["iy"], np.uint16)
    iz = _filled(data["iz"], np.uint8)
    # One fixed order, so every sum over cells is taken in the same order on every request.
    order = np.lexsort((ix, iy, iz))
    sums = CellSums(
        ix=ix[order], iy=iy[order], iz=iz[order],
        energy=_filled(data["e"], np.float64)[order],
        origins=_filled(data["origins"], np.uint8)[order],
        n_events=int(n_events), n_hits=int(_filled(data["n"], np.int64).sum()),
        channel=channel, model=model, query_ms=query_ms,
    )
    if channel in NETWORK_CHANNELS:
        sums.valued_energy = _filled(data["ef"], np.float64)[order]
        sums.positive = _filled(data["esp"], np.float64)[order]
        sums.negative = _filled(data["esn"], np.float64)[order]
        sums.n_valued = int(_filled(data["nf"], np.int64).sum())
    return sums


# ------------------------------------------------------------------ cache --


def cache_for() -> cache_mod.BundleCache:
    """The named cache of per-cell sums, in the registry every invalidation reaches."""
    return cache_mod.get_cache(CACHE_ENTRIES, name=CACHE_NAME, max_bytes=CACHE_MAX_BYTES)


def cache_key(spec: FilterSpec, channel: str, model: str | None) -> tuple:
    """Identity of a selection's sums; ``spec`` clamped, ``table_name`` first for invalidation.

    The window and the cap are left out: both re-render from the same sums.
    ``model`` is None on the energy channel, which reads no network column.
    """
    return (*spec.cache_key(), CACHE_NAME, channel, model, CACHE_VERSION)


def cells_for(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, spec: FilterSpec, channel: str,
              model: str) -> tuple[CellSums, bool]:
    """``(sums, was_cached)`` of the selection for ``channel`` (and ``model`` on a network channel)."""
    clamped = spec.clamped(record)
    cache = cache_for()
    network = model if channel in NETWORK_CHANNELS else None
    key = cache_key(clamped, channel, network)
    if channel == CHANNEL_ENERGY:
        # Every network channel's scan carries the energy sums of the same selection.
        hit = cache.get_any([key, *(cache_key(clamped, c, m) for c in NETWORK_CHANNELS for m in ddl.MODELS)])
        if hit is not None:
            return hit, True
    return physics_cache.get_or_compute(key, lambda: scan(con, record, clamped, channel, network),
                                        heavy=True, cache=cache)


# ---------------------------------------------------------------- builder --


@dataclass
class SelectionBuilder(voxel_event.Builder):
    """The selection's cells through the one-event builder's cells regime.

    It holds per-cell sums instead of hit rows (``rows`` is None): each
    "row" of the cells regime is one cell (``cells.inverse`` the identity), its
    energy the selection's mean per event. What reads rows is overridden: the
    total, the depth profile's attention (from the signed per-cell sums), the
    floor (on the drawn cubes); the blocks and sentences are worded per
    selected event.
    """

    ENERGY_UNIT: ClassVar[str] = UNIT
    ENERGY_NOTE: ClassVar[str] = (
        "The notebook's 3-D displays (C5) draw one event; this view draws the selection's mean deposit "
        "per selected event in each detector cell, as volumetric density on the one-event view's "
        "logarithmic ramp with its 1st-percentile floor, taken here on the drawn cubes, because cell "
        "densities span many decades.")
    CELL_VALUE_HOW: ClassVar[str] = "the energy-weighted mean over the selection's hits in the cell"
    CAP_UNIT: ClassVar[str] = "GeV per selected event"
    CAP_SHARE_OF: ClassVar[str] = "the selection's mean energy per event"
    CAP_CELLS_OF: ClassVar[str] = "the selection's"

    sums: CellSums | None = None
    #: Per cell, Σ E·max(v, 0) / N and Σ E·min(v, 0) / N of a network channel: the depth profile's attention.
    attention_parts: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def n_events(self) -> int:
        return int(self.sums.n_events)

    @property
    def energy_total(self) -> float:
        """The selection's mean energy per event, GeV: every cell's, inside the window or not."""
        return float(self.cells.energy.sum())

    # ------------------------------------------------------ depth profile --

    def _cell_depth_attention(self, row_inside: np.ndarray, z_crop: tuple[int, int],
                              n_depth: int) -> dict[str, Any] | None:
        """Σ E·v / N per depth bin from the per-cell signed sums, split by sign for Shap-CAM.

        The parts are sums over hits, so a cell whose hits disagree in sign
        contributes to both halves, as its hits do on Page 1's planes.
        """
        if self.attention_parts is None:
            return None
        depth = self.cells.iz - z_crop[0]
        keep = row_inside & (depth >= 0) & (depth < n_depth)

        def part(weights: np.ndarray) -> tuple[np.ndarray, float]:
            return (np.bincount(depth[keep], weights=weights[keep], minlength=n_depth),
                    float(weights[~row_inside].sum()))

        positive, negative = self.attention_parts
        if self.channel == CHANNEL_SHAPCAM:
            pos, pos_out = part(positive)
            neg, neg_out = part(negative)
            return {"signed": True, "positive": pos, "negative": np.abs(neg),
                    "positive_outside": pos_out, "negative_outside": abs(neg_out)}
        values, outside = part(positive + negative)
        return {"signed": False, "values": values, "outside": outside}

    def _depth_profile(self, cubes: voxel_event.Cubes, cap_block: dict[str, Any]) -> dict[str, Any]:
        profile = super()._depth_profile(cubes, cap_block)
        profile["note"] = typographic(_DEPTH_NOTE)
        if profile["attention"] is not None:
            profile["attention"]["unit"] = ATTENTION_UNIT
        return profile

    # ------------------------------------------------------------- colour --

    def _energy_range(self, dens: np.ndarray) -> tuple[float, float, bool, str]:
        """``(floor, top, degenerate, basis)``: the drawn cubes' 1st-percentile positive density to the brightest."""
        positive = dens[dens > 0]
        top = float(positive.max()) if positive.size else 0.0
        floor = (float(np.percentile(positive, event_inspector.FLOOR_PERCENTILE))
                 if positive.size else 0.0)
        degenerate = not (top > 0.0 and floor > 0.0 and top > floor * (1.0 + voxel_event.DEGENERATE_RTOL))
        return floor, top, degenerate, FLOOR_BASIS

    def _floor_rule(self, floor: float, top: float, degenerate: bool, n_below: int,
                    pitch: float | None) -> str:
        if degenerate:
            if not top > 0.0:
                return ("No drawn cube carries positive energy, so the logarithmic density ramp has "
                        "nothing to span and no cube is coloured.")
            return (f"Every drawn cube holds the same mean energy density per selected event ({top:.3g} "
                    "GeV per mm³ per event), so the logarithmic ramp is degenerate: vmin = vmax, every "
                    "cube is drawn in the ramp's top colour, and colour carries no contrast in this view.")
        below = f"{n_below:,} cube below the floor is" if n_below == 1 else f"{n_below:,} cubes below the floor are"
        return (
            "Logarithmic ramp of the mean volumetric energy density per selected event, Σ E / (N · V) "
            f"in GeV per mm³ per event, from the {event_inspector.FLOOR_PERCENTILE:g}st percentile of "
            f"the drawn cubes' positive densities ({floor:.3g}) to the brightest drawn cube ({top:.3g}); "
            f"{below} drawn at the lowest colour and flagged. The floor is the drawn cubes' own, not "
            "every cell's: the cap keeps the selection's most energetic cells, and a floor taken over all "
            "of them would spend the bottom of the ramp on cells not drawn.")

    def _shower_labels(self) -> list[str]:
        if not self.two:
            return ["Shower", "—", "—", "—"]
        return ["Shower A rows only", "Shower B rows only", "'A+B' rows only (counted with B)",
                "rows of more than one origin across the selection"]

    # ------------------------------------------------------------- blocks --

    def _head_block(self) -> dict[str, Any]:
        """The ``selection`` block in place of the event's: N, what was summed and what a cube is."""
        return {"selection": {
            "n_events": self.n_events,
            "n_hits": int(self.sums.n_hits),
            "n_cells": int(self.cells.n),
            "quantity": typographic(self._quantity()),
            "aggregation": typographic(self._aggregation()),
        }}

    def _quantity(self) -> str:
        n = self.n_events
        per_event = ("Every energy in this body (the cap block, the depth profile, the exact values) is "
                     "a mean per selected event, in GeV per event.")
        if self.channel == CHANNEL_ENERGY:
            return (
                "Each cube is one detector cell holding the selection's mean energy per selected event as "
                f"a volumetric density, Σ E / (N · V) in GeV per mm³ per event: every hit of "
                f"{'both showers' if self.two else 'the shower'} in the cell, summed over the N = {n:,} "
                f"selected events and divided by N and by the cell's {self.footprint[0]:.2f} × "
                f"{self.footprint[1]:.2f} × {self.pitch_z:g} mm volume. " + per_event)
        lo, hi = (-1, 1) if self.channel == CHANNEL_SHAPCAM else (0, 1)
        return (
            f"Each cube is one detector cell coloured by the energy-weighted mean "
            f"{_NAMES[self.channel]} of the {self.model} network (absolute frame) over the selection's "
            f"hits in the cell, Σ E·v / Σ E over every hit of "
            f"{'both showers' if self.two else 'the shower'} that carries a value, on the one-event "
            f"view's fixed linear ramp [{lo:g}, {hi:g}]. Cubes are ranked and capped by the cell's mean "
            "energy per selected event. " + per_event)

    def _aggregation(self) -> str:
        sums = self.sums
        n = self.n_events
        text = (
            f"One exact scan of the projection table, never the preview sample, sums the "
            f"{sums.n_hits:,} hits of the N = {n:,} selected events by detector cell (ix, iy, iz)"
            + (": both showers together, A, B and 'A+B' rows alike, as Page 1's absolute-frame "
               "projections sum them. " if self.two else ". ")
            + "N is the number of selected events, the selection count every absolute-frame response "
            "reports. ")
        if self.channel == CHANNEL_ENERGY:
            text += "An event with no hit in a cell adds zero to that cell's mean."
        else:
            text += ("The channel's mean is taken over the hits in the cell, weighted by their energy, so "
                     "an event weighs in proportion to the energy it deposits there.")
            missing = sums.n_hits - sums.n_valued
            if missing:
                text += (f" {missing:,} of the {sums.n_hits:,} hits carry no {_NAMES[self.channel]} "
                         "value and are left out of its mean; their energy still ranks the cubes.")
        if n == 1:
            text += " With N = 1 the mean is that one event's own deposit."
        return text

    def _window_block(self) -> dict[str, Any]:
        """The event's window numbers on the selection's cells, its rule worded for them."""
        block = super()._window_block()
        percentiles = event_inspector.window_percentiles_text()
        cells = (f"the selection's cells ({'both showers, ' if self.two else ''}summed over its "
                 f"{self.n_events:,} events)")
        tail = (f", never below {event_inspector.WINDOW_MIN_HALF_MM:.0f} mm and snapped outward to "
                f"{event_inspector.WINDOW_SNAP_MM:.0f} mm")
        if self.window_mode == event_inspector.WINDOW_SHARED:
            head = (f"One half-width for the three axes: the widest energy-weighted {percentiles} "
                    f"percentile range of {cells}, plus one cell footprint so the cells at either end are "
                    f"drawn whole{tail} ({self.half:,.0f} mm here)")
        else:
            halves = event_inspector.halves_text(self.halves, event_inspector.SYMBOLS["lab"])
            head = (f"Per-axis half-widths: each axis's own energy-weighted {percentiles} percentile range "
                    f"of {cells}, plus one cell footprint across the beam and one layer pitch along "
                    f"depth, so the cells at either end are drawn whole{tail} ({halves} here). The box "
                    "keeps one scale on all three axes (1:1:1), so each side is as long as its axis's span")
        block["rule"] = typographic(head + "; cells snap it to whole cells. The cells beyond it are "
                                    "counted with the cap, below.")
        return block


def build(record: ExperimentRecord, sums: CellSums, channel: str, model: str,
          window: str = event_inspector.WINDOW_PER_AXIS,
          footprint: tuple[float, float] | None = None) -> SelectionBuilder:
    """Prepare the selection's cells for :meth:`SelectionBuilder.assemble`; no database access.

    A selection with no event, or whose events hold no hit, is a 404 with a
    sentence saying so, as the pick of an empty selection is.
    """
    assert record.lattice is not None
    event_inspector.check_window(window)
    started = time.perf_counter()
    if sums.n_events == 0:
        raise NotFoundError("The selection holds no event, so there is nothing to draw.")
    if sums.n == 0:
        raise NotFoundError(f"The {sums.n_events:,} selected events hold no hit, so there is nothing to draw.")
    lat = record.lattice
    pitch_z = (float(record.frame_bounds.layer_pitch_mm) if record.frame_bounds is not None
               else float(lat.z.mean_pitch))
    fp = footprint or frame_mod.footprint_from_lattice(lat)
    n = float(sums.n_events)
    ix, iy, iz = (np.asarray(a, dtype=np.int64) for a in (sums.ix, sums.iy, sums.iz))
    cells = voxel_event.Cells(ix=ix, iy=iy, iz=iz, energy=sums.energy / n,
                              shower=voxel_event.shower_codes(sums.origins),
                              inverse=np.arange(sums.n, dtype=np.int64))
    parts = None
    if channel in NETWORK_CHANNELS:
        if sums.valued_energy is None:
            raise ValueError(f"the cached sums of channel {sums.channel!r} cannot colour {channel!r}")
        signed = sums.positive + sums.negative
        valued = sums.valued_energy > 0
        cells.value = np.where(valued, signed / np.where(valued, sums.valued_energy, 1.0), np.nan)
        parts = (sums.positive / n, sums.negative / n)

    # The event's window rule on the selection's cells: their lattice centres, weighted by energy.
    centres = np.column_stack([lat.x.coords[ix], lat.y.coords[iy], lat.z.coords[iz]])
    half, halves, windows = voxel_event.frame_windows(window, centres, cells.energy, FRAME_LAB, fp, pitch_z)
    inside = np.ones(sums.n, dtype=bool)
    for i, axis in enumerate("xyz"):
        inside &= (centres[:, i] >= windows[axis][0]) & (centres[:, i] <= windows[axis][1])
    two = len(showers_mod.of(record)) == 2
    return SelectionBuilder(
        record=record, frame=FRAME_LAB, shower="both" if two else "a", channel=channel, model=model,
        source=frame_sql.SOURCE_FILE, footprint=(float(fp[0]), float(fp[1])), pitch_z=pitch_z,
        event={}, in_selection=True, prev_event=None, next_event=None, infos=[], rows=None,
        cells=cells, centres=centres, rotation=None, half=half, windows=windows,
        # Unused: the selection's floor is taken on the drawn cubes (_energy_range).
        floor=math.nan, residual=None,
        outside_cells={"n_cells": int((~inside).sum()), "n_cells_total": sums.n},
        window_mode=window, halves=halves, started=started, sums=sums, attention_parts=parts,
    )


def cam_note(channel: str, model: str) -> dict[str, Any] | None:
    """``meta.cam`` for a network channel: Page 1's note on averaging independently normalised maps."""
    if channel not in NETWORK_CHANNELS:
        return None
    note = planes.cam_note(model, "lab", channel)
    return {**note,
            "aggregation": "energy-weighted mean of the raw value over the selection's hits in the cell",
            "note": typographic(note["note"])}
