"""Chunked CSV ingestion.

The shipped standalone file is small (37,877 rows), but the 2combined companion
referenced by ``plan-viz.ipynb`` is 22.7 million rows and roughly 3.1 GB in
memory. Reading in chunks costs nothing at the small size and means the large
file needs no separate code path later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .schema import SchemaKind, detect_schema, find_prediction_columns

#: Columns worth reading, per variant. Anything else in the file (``cellID``,
#: which is bijective with ``(x, y, z)`` and so carries no extra information) is
#: skipped to keep memory down on the large file.
_STANDALONE_USE = [
    "event_number",
    "x",
    "y",
    "z",
    "energy",
    "incoming_momentum",
    "incoming_theta",
    "incoming_phi",
]

_OVERLAP_USE = [
    "event_number",
    "x",
    "y",
    "z",
    "energy",
    "particle_origin",
    "incoming_momentum_A",
    "incoming_momentum_B",
    "incoming_theta_A",
    "incoming_theta_B",
    "incoming_phi_A",
    "incoming_phi_B",
]

_DTYPES = {
    "event_number": "int64",
    "x": "float64",
    "y": "float64",
    "z": "float64",
    "energy": "float64",
}


@dataclass
class RawInput:
    """One ingested file, still unsanitised."""

    path: Path
    kind: SchemaKind
    hits: pd.DataFrame
    prediction_columns: list[str] = field(default_factory=list)
    rows_read: int = 0


def read_header(path: Path) -> list[str]:
    """Read only the column names, without loading the body."""
    return list(pd.read_csv(path, nrows=0).columns)


def load(path: Path, chunk_size: int = 2_000_000) -> RawInput:
    """Read one CSV in chunks and return it with its detected schema."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    columns = read_header(path)
    kind = detect_schema(columns)
    predictions = find_prediction_columns(columns)

    wanted = _OVERLAP_USE if kind is SchemaKind.OVERLAP else _STANDALONE_USE
    # Carry any genuine prediction columns through untouched. They are absent
    # from the shipped data; when they appear, they must reach the dashboard as
    # measured values rather than being regenerated anywhere downstream.
    usecols = wanted + [c for c in predictions if c in columns]

    frames = [
        chunk
        for chunk in pd.read_csv(
            path,
            usecols=usecols,
            dtype={k: v for k, v in _DTYPES.items() if k in usecols},
            chunksize=chunk_size,
        )
    ]
    hits = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    return RawInput(
        path=path,
        kind=kind,
        hits=hits,
        prediction_columns=predictions,
        rows_read=len(hits),
    )


def load_all(paths, chunk_size: int = 2_000_000) -> list[RawInput]:
    """Read every input file, rejecting duplicate schemas.

    Two files of the same variant cannot be merged meaningfully: their event
    numbering is independent, so concatenating would silently collide events.
    """
    inputs = [load(Path(p), chunk_size=chunk_size) for p in paths]

    seen: dict[SchemaKind, Path] = {}
    for item in inputs:
        if item.kind in seen:
            raise ValueError(
                f"Two inputs share the {item.kind.value} schema "
                f"({seen[item.kind].name} and {item.path.name}). "
                "Event numbering is per-file, so they cannot be combined. "
                "Supply at most one file of each variant."
            )
        seen[item.kind] = item.path

    return inputs
