#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pandas>=2.0,<3",
#   "numpy>=1.24,<3",
#   "plotly==7.0.0",
# ]
# ///
"""Compile the calorimeter shower reconstruction diagnostic dashboard.

    uv run build_dashboard.py
    uv run build_dashboard.py --input data.csv --output dashboard.html

Reads hit-level calorimeter CSV data and writes a self-contained, fully
client-side HTML dashboard. No server, no live backend, exit code 0 on success.

The heavy lifting lives in the ``calodash`` package; this file is the CLI and
the pipeline wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calodash import cli, geometry, ingest, lattice, payload, reconstruct, render, sanitize
from calodash.constants import COLOR_FLOOR_GEV, ENERGY_BINS, N_LAYERS, N_XY, THEME
from calodash.schema import SchemaError, SchemaKind
from calodash.stats import summarise_band

#: Kinematic columns for the single-particle schema. The overlap schema splits
#: these into _A/_B pairs; that branch activates when such a file is supplied.
STANDALONE_KINEMATICS = ("incoming_momentum", "incoming_theta", "incoming_phi")

#: Decades of dynamic range shown on the density colour scales. Per-hit energies
#: span twelve orders of magnitude; five decades below the peak covers the
#: structure without spending the ramp on cells around 0.1 meV.
COLOR_DECADES = 5.0


def build_event_frame(hits: pd.DataFrame, event_geometry: pd.DataFrame) -> pd.DataFrame:
    """Assemble per-event truth and reconstruction inputs."""
    grouped = hits.groupby("event_number", sort=True)
    events = pd.DataFrame(
        {
            "p_true": grouped["incoming_momentum"].first(),
            "theta": grouped["incoming_theta"].first(),
            "phi": grouped["incoming_phi"].first(),
            "e_dep": grouped["energy"].sum(),
        }
    )
    return events.join(event_geometry, how="left")


def density_extent(
    values: np.ndarray, index: np.ndarray, size: int, scale: np.ndarray | float
) -> tuple[float, float]:
    """Peak and floor, in log10 units, of a normalised density grid.

    Computed on the unfiltered sample and then frozen, so the colour mapping
    does not shift while the sliders move.
    """
    grid = np.bincount(index, weights=values, minlength=size).astype("float64")
    if np.isscalar(scale):
        normalised = grid / max(float(scale), 1.0)
    else:
        normalised = np.divide(
            grid, scale, out=np.zeros_like(grid), where=scale > 0
        )
    peak = float(normalised.max())
    if peak <= 0:
        return (np.log10(COLOR_FLOOR_GEV), 0.0)
    top = float(np.log10(peak))
    return (top - COLOR_DECADES, top)


def main(argv=None) -> int:
    """Run the build, reporting expected failures without a traceback."""
    try:
        return _build(cli.parse_args(argv))
    except (FileNotFoundError, SchemaError, ValueError) as exc:
        # These are the failure modes a user can actually act on -- a missing
        # file, an unrecognised schema, a dataset that sanitises to nothing.
        # A traceback would bury the message that tells them what to fix.
        print(f"build_dashboard: {exc}", file=sys.stderr)
        return 2


def _build(args) -> int:
    log: list[str] = []

    def emit(line: str = "") -> None:
        log.append(line)

    # ---------------------------------------------------------- ingest
    inputs = ingest.load_all(args.input, chunk_size=args.chunk_size)
    primary = next((i for i in inputs if i.kind is SchemaKind.STANDALONE), None)
    overlap = next((i for i in inputs if i.kind is SchemaKind.OVERLAP), None)

    if primary is None:
        raise ValueError(
            "No standalone dataset supplied. The isolated single-particle file "
            "provides the no-overlap reference every panel is built on."
        )

    emit("Inputs")
    for item in inputs:
        emit(f"  {item.path.name}")
        emit(f"    schema {item.kind.value}, {item.rows_read:,} rows")
    predictions = sorted({c for item in inputs for c in item.prediction_columns})
    emit(
        "  model inference columns: "
        + (", ".join(predictions) if predictions else "NONE — ground-truth baseline mode")
    )

    if overlap is not None:
        emit(
            "  ! An overlap dataset was supplied. Separation-D analysis is not yet "
            "wired up; its events are ignored for now."
        )

    # ---------------------------------------------------------- sanitize
    hits, report = sanitize.sanitize(primary.hits, STANDALONE_KINEMATICS)
    emit()
    emit("Sanitisation")
    log.extend(report.lines())

    if args.max_events:
        keep = np.sort(hits["event_number"].unique())[: args.max_events]
        hits = hits[hits["event_number"].isin(keep)].reset_index(drop=True)
        emit(f"  development cap: {len(keep):,} events retained")

    # ---------------------------------------------------------- geometry
    survey = lattice.survey(
        hits["x"].to_numpy(), hits["y"].to_numpy(), hits["z"].to_numpy()
    )
    emit()
    emit("Detector lattice")
    log.extend(survey.lines())

    hits = hits.sort_values(["event_number", "z"], kind="stable").reset_index(drop=True)
    hits, event_geometry = geometry.to_shower_frame(hits, survey.z_front_mm, survey.z_pitch_mm)
    axis = geometry.fit_shower_axis(hits)
    artifacts = geometry.artifact_summary(hits, event_geometry)

    emit()
    emit("Shower-local transform")
    emit(
        f"  origin pinning    {artifacts['singleEntryEvents']:,} events "
        f"({100 * artifacts['singleEntryFraction']:.1f}%) deposit one hit in their entry layer"
    )
    emit(
        f"                    the origin cell therefore holds "
        f"{100 * artifacts['originHitFraction']:.1f}% of all hits"
    )
    emit(
        f"  acceptance        {100 * artifacts['frontFaceFraction']:.1f}% of events "
        f"enter at the front face"
    )
    emit(f"  observed axis     dx/dz={axis.slope_x:+.5f}  dy/dz={axis.slope_y:+.5f}")

    # ---------------------------------------------------- reconstruction
    events = build_event_frame(hits, event_geometry)
    calibration = reconstruct.fit_calibration(events["e_dep"], events["p_true"])
    events = reconstruct.reconstruct(events, calibration)

    emit()
    emit("Conventional reconstruction")
    log.extend(calibration.lines())

    e_reco = events["e_reco"].to_numpy()
    p_true = events["p_true"].to_numpy()
    energy_max = reconstruct.energy_axis_max(e_reco, p_true)
    emit(f"  energy axis maximum {energy_max:.3f} GeV over {ENERGY_BINS} bins")

    for lo, hi in ((0.60, 0.75), (0.75, 0.90), (0.90, 1.00)):
        mask = (p_true >= lo) & (p_true <= hi)
        band = summarise_band(f"{lo:.2f}-{hi:.2f}", e_reco[mask], p_true[mask], 0.0, energy_max)
        if band:
            emit(
                f"    truth band {band.label} GeV: N={band.count:>5,}  "
                f"mu={band.mu:.3f}  sigma={band.sigma:.3f}  sigma/mu={100 * band.resolution:.1f}%"
            )

    # ---------------------------------------------------- build-phase binning
    ix = lattice.quantise_transverse(hits["xl"].to_numpy())
    iy = lattice.quantise_transverse(hits["yl"].to_numpy())
    iz = lattice.quantise_depth(hits["zl"].to_numpy(), survey.z_pitch_mm)
    energy = hits["energy"].to_numpy()

    inside = (ix != lattice.OUTSIDE_WINDOW) & (iy != lattice.OUTSIDE_WINDOW)
    emit()
    emit("Display binning")
    emit(
        f"  transverse window {100 * inside.mean():.1f}% of hits inside "
        f"+/-{lattice.XY_EXTENT_MM:.0f} mm"
    )
    emit(f"  grids             XY {N_XY}x{N_XY}, YZ/XZ {N_XY}x{N_LAYERS}")

    n_events = len(events)
    accept = np.array(
        [
            int((events["entry_layer"].to_numpy() <= N_LAYERS - 1 - layer).sum())
            for layer in range(N_LAYERS)
        ],
        dtype="float64",
    )

    color = {
        "xy": density_extent(
            energy[inside], (iy[inside].astype(int) * N_XY + ix[inside]), N_XY * N_XY, n_events
        ),
        "yz": density_extent(
            energy[inside],
            (iy[inside].astype(int) * N_LAYERS + iz[inside]),
            N_XY * N_LAYERS,
            np.tile(accept, N_XY),
        ),
        "xz": density_extent(
            energy[inside],
            (ix[inside].astype(int) * N_LAYERS + iz[inside]),
            N_XY * N_LAYERS,
            np.tile(accept, N_XY),
        ),
    }
    floor_log = min(v[0] for v in color.values())

    # ------------------------------------------------------------ payload
    events_packed = events.reset_index()
    blob = {
        "meta": {
            "dataset": primary.path.name,
            "schema": primary.kind.value,
            "predictionColumns": predictions,
        },
        "grid": lattice.grid_spec(survey.z_pitch_mm),
        "hits": payload.encode_hits(ix, iy, iz, energy),
        "events": payload.encode_events(
            events_packed,
            {
                "p_true": "<f4",
                "theta": "<f4",
                "phi": "<f4",
                "n_hits": "<u2",
                "e_dep": "<f4",
                "e_reco": "<f4",
                "entry_layer": "<u1",
            },
        ),
        "ranges": {
            "p": [float(p_true.min()), float(p_true.max())],
            "theta": [float(events["theta"].min()), float(events["theta"].max())],
            "phi": [float(events["phi"].min()), float(events["phi"].max())],
            "maxHits": int(events["n_hits"].max()),
            # Opening bands are quantiles, not fractions of the min-max span.
            # The momentum spectrum is flat over roughly 0.63-1.0 GeV with a
            # sparse soft tail below; a span-based default drops the first band
            # into that tail, where a hundred-odd events give a meaningless
            # sigma/mu. Quantiles keep both bands in the populated region.
            "defaultA": [float(np.quantile(p_true, 0.15)), float(np.quantile(p_true, 0.35))],
            "defaultB": [float(np.quantile(p_true, 0.65)), float(np.quantile(p_true, 0.90))],
        },
        "calibration": {"f": calibration.sampling_fraction, "inverse": calibration.inverse},
        "energy": {"max": energy_max, "bins": ENERGY_BINS},
        "axis": axis.endpoints(),
        "artifacts": artifacts,
        "color": {**{k: list(v) for k, v in color.items()}, "floorLog": floor_log},
        "theme": {
            "canvas": THEME["canvas"],
            "card": THEME["card"],
            "border": THEME["border"],
            "text": THEME["text"],
            "muted": THEME["text_muted"],
            "accent": THEME["accent"],
            "showerA": THEME["shower_a"],
            "showerB": THEME["shower_b"],
            "disabled": "#484f58",
        },
    }

    emit()
    emit("Payload")
    log.extend(payload.summarise(blob))

    # ------------------------------------------------------------- render
    document, plotly_source = render.render(payload.to_json(blob), embed_plotly=not args.cdn)
    size = render.write(args.output, document)

    emit()
    emit("Output")
    emit(f"  plotly.js  {plotly_source}")
    emit(f"  written    {args.output}  ({size / 1_048_576:.2f} MiB)")

    if not args.quiet:
        print("\n".join(log))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
