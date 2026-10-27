"""Which shipped models an experiment is analysed with: its source file's species and seed.

An aggregate experiment is the file a notebook trained on, and the producer's
file name says which: ``electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3``
is the electron sample of seed 1, so it pairs with
``xgboost_electron/standalone_{momentum,angle}_s1_model.json``. Nothing else is
guessed. An experiment pairs only when

* it is the event-level aggregate kind (the models read its 52 v3 features;
  a hit-level or two-shower experiment has no such row per event),
* it was built from one source file whose name parses (the notebook's split is
  defined on that one file's rows, in its order),
* both tasks' models exist for that species and seed, and
* every feature of both models maps, through the ``ddl`` vocabulary, to a
  column of the event table.

Otherwise the pairing is refused with a sentence naming what is missing, which
travels to the capability block and the Admin Settings list. Pure: reads the
registry record and a :class:`~calosrv.modelruns.discovery.Catalogue`, no IO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..db import ddl, schemas
from ..db.registry import ExperimentRecord
from ..text import listed
from .discovery import TASKS, Catalogue, ModelFile

#: The producer's aggregate file names: species first, ``aggr``, the seed, a version.
SOURCE_PATTERN = re.compile(r"^(?P<species>[a-z]+)_standalone_.*_aggr_s(?P<seed>\d+)_v\d+")

#: The notebooks' labels per task, in each model's output order, as the producer names them.
TASK_LABELS: dict[str, tuple[str, ...]] = {
    "momentum": ("incoming_momentum",),
    "angle": ("incoming_phi", "incoming_theta"),
}

EXPECTED_NAME = "<species>_standalone_…_aggr_s<seed>_v<n>"


@dataclass(frozen=True)
class Source:
    """The species and seed a source file name declares, or why it declares none."""

    file: str | None
    species: str | None = None
    seed: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Pairing:
    """One experiment against the models folder."""

    table_name: str
    kind: str | None
    source: Source
    models: dict[str, ModelFile] = field(default_factory=dict)
    #: Per task, ``(feature, event-table column)`` in the model's feature order.
    columns: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)
    reason: str | None = None

    @property
    def paired(self) -> bool:
        return self.reason is None

    @property
    def species(self) -> str | None:
        return self.source.species

    @property
    def seed(self) -> int | None:
        return self.source.seed

    def as_dict(self) -> dict[str, Any]:
        return {
            "paired": self.paired,
            "species": self.species,
            "seed": self.seed,
            "source_file": self.source.file,
            "models": [self.models[t].header() for t in TASKS if t in self.models],
            "reason": self.reason,
        }


def label_column(label: str) -> str:
    """The event-table column of a notebook label (``incoming_phi`` -> ``phi_a``)."""
    column = ddl.event_feature_column(label)
    if column is None:  # pragma: no cover - the vocabulary names all three
        raise ValueError(f"the aggregate event table has no column for {label!r}")
    return column


def parse_source(record: ExperimentRecord) -> Source:
    """The species and seed of the experiment's one source file."""
    files = sorted(set(record.source_files or []))
    if not files:
        return Source(None, reason="its source file is not recorded, so its species and seed are "
                                   "unknown.")
    if len(files) > 1:
        return Source(files[0], reason=(
            f"it was built from {len(files)} source files; the notebook's 80/20 split is defined "
            "on the rows of one file."))
    stem = files[0].rsplit(".", 1)[0] if "." in files[0] else files[0]
    match = SOURCE_PATTERN.match(stem)
    if match is None:
        return Source(files[0], reason=(
            f"its source file name {files[0]!r} does not name a species and seed "
            f"(expected {EXPECTED_NAME})."))
    return Source(files[0], match.group("species"), int(match.group("seed")))


def pair(record: ExperimentRecord, catalogue: Catalogue | None) -> Pairing:
    """Pair ``record`` with the catalogue's models, or say why it cannot be."""
    kind = record.kind
    name = record.table_name
    if kind != ddl.KIND_SINGLE_EVENTS:
        label = schemas.TRAITS[kind].label if kind in schemas.TRAITS else "of an unknown schema"
        return Pairing(name, kind, Source(None), reason=(
            "the XGBoost models read the 52 event-level features of an aggregate experiment "
            f"(single_shower_events); this experiment is {label}."))
    source = parse_source(record)
    if source.reason is not None:
        return Pairing(name, kind, source, reason=source.reason)
    if catalogue is None or not catalogue.found:
        where = catalogue.root.name if catalogue is not None else "xgboost_models"
        return Pairing(name, kind, source, reason=f"the models folder ({where}) was not found.")
    models: dict[str, ModelFile] = {}
    missing: list[str] = []
    for task in TASKS:
        model = catalogue.get(source.species, source.seed, task)
        if model is None:
            missing.append(f"xgboost_{source.species}/standalone_{task}_s{source.seed}_model.json")
        else:
            models[task] = model
    if missing:
        verb = "is absent or was" if len(missing) == 1 else "are absent or were"
        return Pairing(name, kind, source, models, reason=(
            f"no usable {' or '.join(t for t in TASKS if t not in models)} model for "
            f"{source.species} seed {source.seed}: {' and '.join(missing)} {verb} rejected "
            "(Admin Settings lists the models folder)."))
    columns: dict[str, tuple[tuple[str, str], ...]] = {}
    for task, model in models.items():
        mapped = [(f, ddl.event_feature_column(f)) for f in model.feature_names]
        absent = [f for f, c in mapped if c is None]
        if absent:
            return Pairing(name, kind, source, models, reason=(
                f"the {task} model {model.relative} needs features the event table does not "
                f"have: {listed(absent)}."))
        columns[task] = tuple((f, c) for f, c in mapped if c is not None)
    return Pairing(name, kind, source, models, columns)
