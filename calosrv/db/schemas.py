"""The accepted input schemas: which one a file is, and what each kind can serve.

Three schemas are accepted, one per kind of experiment (``ddl.KINDS``):

* ``hits_all_models`` v1: two showers per event, one row per hit, with three
  networks' predictions and per-hit CAM maps (99 columns, ``ddl.HIT_COLUMNS``);
* ``standalone_hits`` v3: one shower per event, one row per cell, with the
  cell's attributed particle (21 columns, ``ddl.STANDALONE_HIT_COLUMNS``);
* ``standalone_events`` v3: one shower per event as the producer's precomputed
  event features, no hits (59 columns, ``ddl.STANDALONE_EVENT_COLUMNS``).

A CSV is recognised by its exact header (the reader is positional, so the same
names in another order are refused rather than read into the wrong columns); a
Parquet file by its set of column names. A file that is neither is reported
against the schema it resembles most - judged by the columns no other schema
has - and against ``hits_all_models`` when nothing distinguishes it, in one
sentence that also lists what is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..errors import IngestError
from ..text import listed
from . import naming
from .ddl import (
    HIT_COLUMNS,
    KIND_SINGLE_EVENTS,
    KIND_SINGLE_HITS,
    KIND_TWO_SHOWER,
    NULLABLE_COLUMNS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    STANDALONE_EVENT_COLUMNS,
    STANDALONE_HIT_COLUMNS,
)


@dataclass(frozen=True)
class InputSchema:
    """One accepted file layout."""

    name: str
    version: int
    kind: str
    label: str                                  # how a sentence names it
    summary: str                                # what a file of this schema holds
    columns: tuple[tuple[str, str], ...]        # (name, DuckDB type), file order
    event_key: str                              # the event identifier column
    archive_order: tuple[str, ...] = ()         # ORDER BY of each archive part; () keeps source order
    nan_as_null: tuple[str, ...] = ()           # Parquet NaN read as NULL only here
    empty_is_null: tuple[str, ...] = ()         # VARCHAR '' read as NULL on the Parquet path
    boolean_ok: tuple[str, ...] = ()            # integer targets that also accept a Parquet BOOLEAN
    hints: tuple[tuple[str, str], ...] = ()     # (marker column in a refused file, sentence)
    caveat: str = ""                            # what every view of such an experiment must say

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.columns)

    @property
    def n_columns(self) -> int:
        return len(self.columns)

    @property
    def types(self) -> dict[str, str]:
        return dict(self.columns)


@dataclass(frozen=True)
class KindTraits:
    """What an experiment of one kind holds."""

    kind: str
    label: str
    showers: tuple[str, ...]
    has_hits: bool
    has_networks: bool
    has_species: bool
    filter_axes: tuple[str, ...]


_V37_HINT = (
    " This looks like a retired v37 (hits_with_gradcam) file; re-export it "
    f"in the {SCHEMA_NAME} format."
)
_V2_AGGREGATE_HINT = (
    " This looks like a v2 aggregated file (29 columns with GNN node features); "
    "only the 59-column v3 aggregate is accepted."
)

HITS_ALL_MODELS = InputSchema(
    name=SCHEMA_NAME,
    version=SCHEMA_VERSION,
    kind=KIND_TWO_SHOWER,
    label=SCHEMA_NAME,
    summary="two showers per event, one row per hit, with three networks' predictions and CAM maps",
    columns=HIT_COLUMNS,
    event_key="event_number",
    nan_as_null=NULLABLE_COLUMNS,
    hints=(("voxel_fA_pred", _V37_HINT),),
)

STANDALONE_HITS = InputSchema(
    name="standalone_hits",
    version=3,
    kind=KIND_SINGLE_HITS,
    label="standalone_hits v3",
    summary="one shower per event, one row per cell, with the cell's attributed particle",
    columns=STANDALONE_HIT_COLUMNS,
    event_key="event_number",
    archive_order=("event_number", "cellID"),
    empty_is_null=("particle_type", "parent_type", "daughter_type"),
    boolean_ok=("is_secondary",),
)

#: The producer's aggregate is a censored sample: one owner for the sentence every
#: view of it carries. The figures a view quotes beside it are measured on the
#: experiment in hand, never the electron file's.
CENSORED_AGGREGATE_NOTICE = (
    "This experiment is the producer's event-level aggregate, a censored sample: it leaves "
    "out every event with a single hit (its spatial SDs are undefined), so its momentum bins "
    "are not balanced, the lowest bins lose the most events, and their mean response is "
    "biased high, because single-hit showers deposit the least. The hit-level file of the "
    "same run keeps them."
)

STANDALONE_EVENTS = InputSchema(
    name="standalone_events",
    version=3,
    kind=KIND_SINGLE_EVENTS,
    label="standalone_events v3",
    summary="one shower per event as precomputed event features (no hits)",
    columns=STANDALONE_EVENT_COLUMNS,
    event_key="event_id",
    archive_order=("event_id",),
    hints=(("gnn_logical_node", _V2_AGGREGATE_HINT),),
    caveat=CENSORED_AGGREGATE_NOTICE,
)

#: Every accepted schema, the default first: an unrecognised file is reported
#: against it, which keeps the long-standing ``hits_all_models`` sentences.
SCHEMAS: tuple[InputSchema, ...] = (HITS_ALL_MODELS, STANDALONE_HITS, STANDALONE_EVENTS)
DEFAULT: InputSchema = HITS_ALL_MODELS

TRAITS: dict[str, KindTraits] = {
    KIND_TWO_SHOWER: KindTraits(KIND_TWO_SHOWER, "two-shower hits", ("a", "b"),
                                has_hits=True, has_networks=True, has_species=False,
                                filter_axes=("e1", "e2", "d")),
    KIND_SINGLE_HITS: KindTraits(KIND_SINGLE_HITS, "single-shower hits", ("a",),
                                 has_hits=True, has_networks=False, has_species=True,
                                 filter_axes=("e1",)),
    KIND_SINGLE_EVENTS: KindTraits(KIND_SINGLE_EVENTS, "single-shower event features", ("a",),
                                   has_hits=False, has_networks=False, has_species=False,
                                   filter_axes=("e1",)),
}

#: The layout generation of each kind's derived tables. A two-shower experiment
#: ingested before Group-1, ``layers_`` and ``profiles_`` existed has version 1
#: (stored as NULL): it is served as before, and the panels that need those
#: tables stay off until it is rebuilt from its archive.
DERIVED_VERSION: dict[str, int] = {KIND_TWO_SHOWER: 2, KIND_SINGLE_HITS: 1, KIND_SINGLE_EVENTS: 1}

_BY_KEY: dict[tuple[str, int], InputSchema] = {(s.name, s.version): s for s in SCHEMAS}
_BY_KIND: dict[str, InputSchema] = {s.kind: s for s in SCHEMAS}


def get(name: str | None, version: int | None) -> InputSchema | None:
    """The schema a registry row or manifest names, or None when it is not accepted."""
    if name is None or version is None:
        return None
    return _BY_KEY.get((name, int(version)))


def of_kind(kind: str) -> InputSchema:
    return _BY_KIND[kind]


def signature(schema: InputSchema) -> frozenset[str]:
    """The columns of ``schema`` that no other accepted schema has."""
    others: set[str] = set()
    for other in SCHEMAS:
        if other is not schema:
            others.update(other.names)
    return frozenset(schema.names) - others


def nearest(found: Iterable[str]) -> InputSchema:
    """The schema a refused file most resembles, judged by distinctive columns.

    Names every schema shares (``event_number``, the coordinates, ``energy``)
    say nothing about which one a file was meant to be, so only the columns
    unique to a schema count. A tie, or no distinctive column at all, falls to
    :data:`DEFAULT`.
    """
    present = set(found)
    scores = [(len(present & signature(s)), s) for s in SCHEMAS]
    best = max(score for score, _ in scores)
    winners = [s for score, s in scores if score == best]
    if best == 0 or len(winners) > 1:
        return DEFAULT
    return winners[0]


def accepted_sentence() -> str:
    """One sentence naming every accepted schema."""
    parts = [f"{s.label} ({s.n_columns} columns)" for s in SCHEMAS]
    return f"Accepted inputs: {', '.join(parts[:-1])} and {parts[-1]}."


def mismatch_error(file_name: str, schema: InputSchema, found: Sequence[str]) -> IngestError:
    """The refusal of a file whose columns are not ``schema``'s, in one readable sentence."""
    present = list(found)
    missing = [c for c in schema.names if c not in present]
    unexpected = [c for c in present if c not in schema.types]
    parts = []
    if missing:
        parts.append(f"missing columns: {listed(missing)}")
    if unexpected:
        parts.append(f"unexpected columns: {listed(unexpected)}")
    message = (
        f"{file_name} does not match the {schema.label} input schema "
        f"({schema.n_columns} columns; {'; '.join(parts)})."
    )
    for marker, hint in schema.hints:
        if marker in present:
            message += hint
    message += " " + accepted_sentence()
    return IngestError(
        message,
        expected=list(schema.names),
        found=present,
        schema={"name": schema.name, "version": schema.version, "kind": schema.kind},
        accepted=[{"name": s.name, "version": s.version, "n_columns": s.n_columns} for s in SCHEMAS],
    )


def order_error(file_name: str, schema: InputSchema, found: Sequence[str]) -> IngestError:
    """The refusal of a CSV that has a schema's columns in another order."""
    return IngestError(
        f"{file_name} has the expected {schema.n_columns} columns of the {schema.label} "
        "input schema but in a different order. The reader is positional, so the file "
        "must be reordered before it can be ingested.",
        expected=list(schema.names),
        found=list(found),
        schema={"name": schema.name, "version": schema.version, "kind": schema.kind},
    )


def detect_header(file_name: str, found: Sequence[str]) -> InputSchema:
    """The schema a CSV header is, by exact match; raise naming the nearest otherwise."""
    header = tuple(found)
    for schema in SCHEMAS:
        if header == schema.names:
            return schema
    for schema in SCHEMAS:
        if sorted(header) == sorted(schema.names):
            raise order_error(file_name, schema, header)
    raise mismatch_error(file_name, nearest(header), header)


def detect_names(file_name: str, found: Iterable[str]) -> InputSchema:
    """The schema a Parquet file is, by its set of names; raise naming the nearest otherwise.

    The caller drops pandas index columns first: they are not data.
    """
    names = list(found)
    present = set(names)
    for schema in SCHEMAS:
        if present == set(schema.names) and len(names) == schema.n_columns:
            return schema
    raise mismatch_error(file_name, nearest(names), names)


def advertised() -> list[dict]:
    """The accepted schemas as ``GET /api/upload-info`` lists them."""
    return [
        {
            "name": s.name,
            "version": s.version,
            "kind": s.kind,
            "label": s.label,
            "summary": s.summary,
            "n_columns": s.n_columns,
            "columns": list(s.names),
            "note": "A CSV must carry exactly these columns in this order; a Parquet file the "
                    "same names in any order.",
        }
        for s in SCHEMAS
    ]


def derived_status(kind: str | None, stored: int | None) -> str:
    """``current`` or ``stale`` derived tables for a kind; ``unknown`` without a kind."""
    if kind is None or kind not in DERIVED_VERSION:
        return "unknown"
    return "current" if (stored or 1) >= DERIVED_VERSION[kind] else "stale"


def required_tables(name: str, kind: str, derived_version: int | None, has_sample: bool) -> set[str]:
    """The physical tables a ready experiment must have."""
    if kind == KIND_SINGLE_EVENTS:
        return {naming.event_table(name)}
    tables = {naming.proj_table(name), naming.event_table(name)}
    if has_sample:
        tables.add(naming.proj_table(name, sampled=True))
    if (derived_version or 1) >= 2 or kind == KIND_SINGLE_HITS:
        tables |= {naming.layers_table(name), naming.profiles_table(name)}
    return tables
