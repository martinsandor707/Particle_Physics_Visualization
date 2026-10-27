"""Find the shipped XGBoost models: a scan of the models folder, never fatal.

The folder holds one directory per species and one JSON file per task and
seed, as the notebooks saved them::

    xgboost_<species>/standalone_<task>_s<seed>_model.json

``task`` is ``momentum`` (one target, the incident momentum) or ``angle`` (two
targets, the notebook's ``[incoming_phi, incoming_theta]``). Each file's header
is read with the standard library - its feature names and types, the number of
targets and trees, the objective and the XGBoost version that wrote it - and
its bytes are hashed, because the sha256 is what makes a stored analysis stale
when a model is replaced. Nothing here imports XGBoost.

A file that cannot be read, or that is not what its name says (an angle model
with one target, an objective the notebooks did not use, no feature names), is
listed with the reason and left out; a folder that does not exist is reported
as such. The scan never raises, so a bad file can never stop the server.

Headers are cached by path, size and modification time: the Admin Settings
panel's list rescans on every call, and re-hashing sixteen megabyte-sized
files for it would be wasted work.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The tasks the notebooks trained, and the number of targets each must predict.
TASKS: tuple[str, ...] = ("momentum", "angle")
TARGETS: dict[str, int] = {"momentum": 1, "angle": 2}

#: The objective every notebook model was trained with, and the refits use.
OBJECTIVE = "reg:squarederror"

SPECIES_DIR = re.compile(r"^xgboost_(?P<species>[a-z][a-z0-9]*)$")
MODEL_FILE = re.compile(r"^standalone_(?P<task>[a-z]+)_s(?P<seed>\d+)_model\.json$")


@dataclass(frozen=True)
class ModelFile:
    """One shipped model, as its header describes it."""

    path: Path
    relative: str
    species: str
    task: str
    seed: int
    sha256: str
    size: int
    xgboost_version: str
    feature_names: tuple[str, ...]
    feature_types: tuple[str, ...]
    num_target: int
    num_trees: int
    base_score: str
    objective: str

    def header(self) -> dict[str, Any]:
        """What the payloads and the Admin Settings list quote about the file."""
        return {
            "path": self.relative, "species": self.species, "task": self.task,
            "seed": self.seed, "sha256": self.sha256[:12], "bytes": self.size,
            "xgboost_version": self.xgboost_version, "num_target": self.num_target,
            "num_trees": self.num_trees, "n_features": len(self.feature_names),
            "objective": self.objective,
        }


@dataclass(frozen=True)
class Rejected:
    """A file in the folder that is not a usable model, and why."""

    relative: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.relative, "reason": self.reason}


@dataclass
class Catalogue:
    """One scan of the models folder."""

    root: Path
    found: bool
    models: dict[tuple[str, int, str], ModelFile] = field(default_factory=dict)
    rejected: list[Rejected] = field(default_factory=list)
    scanned_at: str = ""

    def get(self, species: str, seed: int, task: str) -> ModelFile | None:
        return self.models.get((species, int(seed), task))

    def as_dict(self) -> dict[str, Any]:
        return {
            "dir": str(self.root),
            "found": self.found,
            "scanned_at": self.scanned_at,
            "files": [m.header() for _, m in sorted(self.models.items())],
            "rejected": [r.as_dict() for r in self.rejected],
        }


#: (path, size, mtime_ns) -> the parsed header, or the reason it was rejected.
_CACHE: dict[tuple[str, int, int], ModelFile | Rejected] = {}
_CACHE_LOCK = threading.Lock()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _version(raw: Any) -> str:
    if isinstance(raw, list) and all(isinstance(v, int) for v in raw):
        return ".".join(str(v) for v in raw)
    return str(raw)


def read_header(path: Path, relative: str, species: str, task: str, seed: int) -> ModelFile | Rejected:
    """Parse one model file's header; a :class:`Rejected` saying why it cannot be used."""
    try:
        size = path.stat().st_size
        sha = _sha256(path)
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return Rejected(relative, f"could not be read: {exc}")
    except ValueError as exc:
        return Rejected(relative, f"is not valid JSON: {exc}")
    try:
        learner = document["learner"]
        names = learner.get("feature_names") or []
        types = learner.get("feature_types") or []
        param = learner["learner_model_param"]
        num_target = int(param.get("num_target", "1"))
        objective = str(learner["objective"]["name"])
        trees = int(learner["gradient_booster"]["model"]["gbtree_model_param"]["num_trees"])
        base_score = str(param.get("base_score", ""))
    except (KeyError, TypeError, ValueError) as exc:
        return Rejected(relative, f"is not an XGBoost gbtree model file (missing {exc}).")
    if not names or not all(isinstance(n, str) for n in names):
        return Rejected(relative, "carries no feature names, so its columns cannot be matched "
                                  "to the event table.")
    if len(set(names)) != len(names):
        return Rejected(relative, "names a feature twice.")
    if objective != OBJECTIVE:
        return Rejected(relative, f"was trained with objective {objective!r}; the notebooks and "
                                  f"the refits use {OBJECTIVE!r}.")
    if num_target != TARGETS[task]:
        return Rejected(relative, f"predicts {num_target} target(s); a {task} model predicts "
                                  f"{TARGETS[task]}.")
    return ModelFile(
        path=path, relative=relative, species=species, task=task, seed=seed, sha256=sha,
        size=size, xgboost_version=_version(document.get("version")),
        feature_names=tuple(names), feature_types=tuple(str(t) for t in types),
        num_target=num_target, num_trees=trees, base_score=base_score, objective=objective,
    )


def _cached_header(path: Path, relative: str, species: str, task: str, seed: int) -> ModelFile | Rejected:
    try:
        stat = path.stat()
    except OSError as exc:
        return Rejected(relative, f"could not be read: {exc}")
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    found = read_header(path, relative, species, task, seed)
    if isinstance(found, Rejected):
        log.warning("Models folder: %s %s", found.relative, found.reason)
    with _CACHE_LOCK:
        for stale in [k for k in _CACHE if k[0] == key[0]]:
            del _CACHE[stale]
        _CACHE[key] = found
    return found


def scan(root: Path) -> Catalogue:
    """Every model under ``root``, and every file that looked like one but is not usable."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    catalogue = Catalogue(root=root, found=root.is_dir(), scanned_at=now)
    if not catalogue.found:
        return catalogue
    try:
        directories = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        catalogue.rejected.append(Rejected(".", f"the folder could not be read: {exc}"))
        return catalogue
    for directory in directories:
        species_match = SPECIES_DIR.match(directory.name)
        try:
            files = sorted(p for p in directory.iterdir() if p.suffix.lower() == ".json")
        except OSError as exc:
            catalogue.rejected.append(Rejected(directory.name, f"could not be read: {exc}"))
            continue
        for path in files:
            relative = f"{directory.name}/{path.name}"
            match = MODEL_FILE.match(path.name)
            if species_match is None or match is None:
                catalogue.rejected.append(Rejected(
                    relative, "does not follow xgboost_<species>/standalone_<task>_s<seed>_model.json."))
                continue
            task = match.group("task")
            if task not in TASKS:
                catalogue.rejected.append(Rejected(
                    relative, f"names the task {task!r}; the notebooks trained {', '.join(TASKS)}."))
                continue
            species, seed = species_match.group("species"), int(match.group("seed"))
            found = _cached_header(path, relative, species, task, seed)
            if isinstance(found, Rejected):
                catalogue.rejected.append(found)
            else:
                catalogue.models[(species, seed, task)] = found
    return catalogue
