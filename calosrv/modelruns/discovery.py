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
as such. Only regular files are read - never a symbolic link, which could lead
out of the folder or to a device - and never one over :data:`MAX_BYTES`, which
is checked before reading. Each file is read once, and its sha256 and its
header come from the same bytes. The scan never raises, so a bad file can
never stop the server.

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

#: The largest model file read (a shipped one is a few megabytes): a cap checked
#: before reading, so a stray huge file cannot hold the boot scan.
MAX_BYTES = 256 * 1024 * 1024

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


def _version(raw: Any) -> str:
    if isinstance(raw, list) and all(isinstance(v, int) for v in raw):
        return ".".join(str(v) for v in raw)
    return str(raw)


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    """``parent[key]``, which must be a JSON object; a ``KeyError`` naming the path otherwise."""
    value = parent.get(key)
    if not isinstance(value, dict):
        raise KeyError(key)
    return value


def _read_bytes(path: Path) -> bytes:
    """The file's bytes, once: a regular file under the size cap, else ``ValueError``.

    ``path.is_file()`` follows a symlink, so a link is refused first: the
    folder is mounted from the host, and a link out of it (to ``/dev/zero``,
    say) would hang the boot scan or read a file nobody meant to publish.
    """
    if path.is_symlink():
        raise ValueError("is a symbolic link; only regular files in the models folder are read.")
    if not path.is_file():
        raise ValueError("is not a regular file.")
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"is {size:,} bytes, over the {MAX_BYTES:,}-byte cap for a model file.")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"grew past the {MAX_BYTES:,}-byte cap while it was read.")
    return data


def _parse(document: Any) -> tuple[list[Any], list[Any], int, str, int, str]:
    """``(names, types, num_target, objective, num_trees, base_score)`` of a parsed model file."""
    if not isinstance(document, dict):
        raise KeyError("learner")
    learner = _mapping(document, "learner")
    names = learner.get("feature_names") or []
    types = learner.get("feature_types") or []
    if not isinstance(names, list) or not isinstance(types, list):
        raise TypeError("feature_names and feature_types must be lists")
    param = _mapping(learner, "learner_model_param")
    num_target = int(param.get("num_target", "1"))
    objective = str(_mapping(learner, "objective")["name"])
    booster = _mapping(_mapping(learner, "gradient_booster"), "model")
    trees = int(_mapping(booster, "gbtree_model_param")["num_trees"])
    base_score = str(param.get("base_score", ""))
    return names, types, num_target, objective, trees, base_score


def read_header(path: Path, relative: str, species: str, task: str, seed: int) -> ModelFile | Rejected:
    """Parse one model file's header; a :class:`Rejected` saying why it cannot be used.

    The bytes are read once, and the sha256 and the parse are taken from the
    same bytes, so a file replaced mid-read cannot pair one file's hash with
    another's header. Any failure - an unreadable file, bad JSON, JSON nested
    deeper than the parser allows, a header of the wrong shape - is a
    rejection with its reason, never an exception: one bad file must not
    stop the scan of the others.
    """
    try:
        data = _read_bytes(path)
    except ValueError as exc:
        return Rejected(relative, str(exc))
    except OSError as exc:
        return Rejected(relative, f"could not be read: {exc}")
    sha = hashlib.sha256(data).hexdigest()
    try:
        document = json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return Rejected(relative, f"could not be read: {exc}")
    except RecursionError:
        return Rejected(relative, "is not valid JSON: nested too deeply to parse.")
    except ValueError as exc:
        return Rejected(relative, f"is not valid JSON: {exc}")
    except Exception as exc:  # noqa: BLE001 - a malformed file is a rejection, never a crash
        return Rejected(relative, f"is not valid JSON ({type(exc).__name__}: {exc}).")
    try:
        names, types, num_target, objective, trees, base_score = _parse(document)
    except (KeyError, TypeError, ValueError) as exc:
        return Rejected(relative, f"is not an XGBoost gbtree model file (missing or malformed {exc}).")
    except Exception as exc:  # noqa: BLE001 - a malformed file is a rejection, never a crash
        return Rejected(relative, f"is not an XGBoost gbtree model file ({type(exc).__name__}: {exc}).")
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
        size=len(data), xgboost_version=_version(document.get("version")),
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
        if directory.is_symlink():
            catalogue.rejected.append(Rejected(
                directory.name, "is a symbolic link; only directories in the models folder are read."))
            continue
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
