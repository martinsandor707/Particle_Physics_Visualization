"""The single place an experiment name is allowed to become SQL identifier text.

DuckDB, like every other engine, cannot bind a table name as a query parameter -
``SELECT * FROM ?`` is not a thing. Identifiers must therefore be interpolated,
and interpolation is where SQL injection lives. Rather than scatter that risk
across a dozen query modules, every physical table name in the application is
produced by :func:`physical` here, which accepts only names that have already
passed :func:`validate_experiment_name`.

The validation is a strict allowlist pattern, not an escape or a blacklist. A
name that does not match is rejected outright; nothing is sanitised into
acceptability, because a silently rewritten table name is its own bug.
"""

from __future__ import annotations

import hashlib
import re

from ..errors import ValidationError

#: Experiment names are lowercase identifiers. Leading digits are excluded so a
#: name can never be confused with a numeric literal, and the 48-character cap
#: keeps the derived physical names clear of DuckDB's identifier limits.
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

#: Physical table prefixes. Every table the application creates for an
#: experiment carries one of these, which is what lets :func:`is_managed_table`
#: distinguish application tables from anything else in the database file.
HIT_PREFIX = "hit_"
PROJ_PREFIX = "proj_"
EVENT_PREFIX = "event_"
LAYERS_PREFIX = "layers_"
PROFILES_PREFIX = "profiles_"

#: The XGBoost model analysis of an aggregate experiment (``calosrv/modelruns``):
#: one row per task, the validation-split predictions, the cross-validation
#: folds, the gain importances, the 2,000-row binary sample and the depth-3
#: surrogate tree. Derived from the event table and the shipped models, so they
#: are dropped with the experiment and rebuilt by its next analysis.
XGB_RUN_PREFIX = "xgbrun_"
XGB_PRED_PREFIX = "xgbpred_"
XGB_FOLD_PREFIX = "xgbfold_"
XGB_IMP_PREFIX = "xgbimp_"
XGB_BIN_PREFIX = "xgbbin_"
XGB_TREE_PREFIX = "xgbtree_"

#: The model-analysis prefixes, keyed by the table's role.
XGB_PREFIXES: dict[str, str] = {
    "run": XGB_RUN_PREFIX, "pred": XGB_PRED_PREFIX, "fold": XGB_FOLD_PREFIX,
    "imp": XGB_IMP_PREFIX, "bin": XGB_BIN_PREFIX, "tree": XGB_TREE_PREFIX,
}

#: Every prefix, longest first where one could begin another (none do today).
_PREFIXES = (PROFILES_PREFIX, LAYERS_PREFIX, HIT_PREFIX, PROJ_PREFIX, EVENT_PREFIX,
             *XGB_PREFIXES.values())

#: Suffix of the Bernoulli-sampled companion to a projection table, used to
#: serve the drag-preview tier described in the performance plan.
SAMPLE_SUFFIX = "_s10"

#: The registry table itself. Not per-experiment, so it has no prefix.
REGISTRY_TABLE = "experiment"

#: Reserved because they would collide with the registry or with a derived name.
_RESERVED = frozenset({REGISTRY_TABLE, "experiment_registry", "main", "temp", "system"})


def validate_experiment_name(name: str) -> str:
    """Return ``name`` if it is a legal experiment name, else raise.

    Raises :class:`~calosrv.errors.ValidationError` with a message that states
    the rule, so a user who typed ``My Run 3`` learns what to type instead.
    """
    candidate = (name or "").strip()
    if not candidate:
        raise ValidationError("Experiment name must not be empty.")
    if not _NAME_PATTERN.match(candidate):
        raise ValidationError(
            f"Invalid experiment name {candidate!r}. Names must start with a "
            "lowercase letter and contain only lowercase letters, digits and "
            "underscores (max 48 characters).",
            field="table_name",
        )
    if candidate.endswith(SAMPLE_SUFFIX):
        # ``proj_<name>_s10`` is <name>'s preview sample; an experiment called
        # ``<name>_s10`` would own a projection table of the same name, and the
        # two would overwrite and drop each other's tables.
        raise ValidationError(
            f"Invalid experiment name {candidate!r}: the suffix {SAMPLE_SUFFIX!r} is reserved "
            "for preview-sample tables.",
            field="table_name",
        )
    if candidate in _RESERVED:
        raise ValidationError(
            f"Experiment name {candidate!r} is reserved.", field="table_name"
        )
    return candidate


#: Prefix given to a derived name whose file starts with a digit, which the
#: pattern forbids: ``2026_run.csv`` becomes ``exp_2026_run``.
DIGIT_PREFIX = "exp_"

_NOT_NAME_CHARACTER = re.compile(r"[^a-z0-9]+")


#: Hex characters of the fingerprint a long name ends with.
_DIGEST_HEX = 6
_MAX_NAME = 48


def _shorten(name: str) -> str:
    """A name over 48 characters: its first word, its last words, a fingerprint.

    Simulation files differ at the end of long names - ``..._s1_v3`` against
    ``..._aggr_s1_v3`` - so a plain cut makes every one of them the same
    experiment. Keeping the first word and as many trailing words as fit keeps
    the distinguishing tail readable, and a six-character blake2b fingerprint
    of the whole name keeps two names that still meet apart.
    """
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=_DIGEST_HEX // 2).hexdigest()
    budget = _MAX_NAME - 1 - len(digest)
    words = name.split("_")
    head = words[0][:budget]
    tail: list[str] = []
    for word in reversed(words[1:]):
        if len("_".join([head, word, *tail])) > budget:
            break
        tail.insert(0, word)
    return f"{'_'.join([head, *tail]).rstrip('_')}_{digest}"


def derive_experiment_name(stem: str) -> str:
    """The experiment name the automatic ingest gives a dropped file.

    The stem is lower-cased, every run of other characters becomes one
    underscore, leading and trailing underscores go and a leading digit gets
    :data:`DIGIT_PREFIX`. A result over 48 characters keeps its first word and
    its last words around a fingerprint of the whole (:func:`_shorten`). That is
    a derivation, not a sanitisation of user input into acceptability: the
    result still has to pass :func:`validate_experiment_name`, so a reserved
    word or the sample suffix is refused rather than bent into something else.

    ``Production-20k (v2)`` -> ``production_20k_v2``.
    """
    name = _NOT_NAME_CHARACTER.sub("_", stem.lower()).strip("_")
    if name[:1].isdigit():
        name = DIGIT_PREFIX + name
    if len(name) > _MAX_NAME:
        name = _shorten(name)
    return validate_experiment_name(name)


def hit_table(name: str) -> str:
    """Physical name of the retired v37 raw hit table for ``name``.

    No table of this name is created any more - raw rows live in the Parquet
    archive - but a database written by the v37 release still holds them, so
    drop and cleanup must keep reaching it.
    """
    return f"{HIT_PREFIX}{validate_experiment_name(name)}"


def proj_table(name: str, sampled: bool = False) -> str:
    """Physical name of the narrow projection table for ``name``.

    ``sampled=True`` selects the 10% Bernoulli companion used for drag preview.
    """
    base = f"{PROJ_PREFIX}{validate_experiment_name(name)}"
    return f"{base}{SAMPLE_SUFFIX}" if sampled else base


def event_table(name: str) -> str:
    """Physical name of the per-event summary table for ``name``."""
    return f"{EVENT_PREFIX}{validate_experiment_name(name)}"


def layers_table(name: str) -> str:
    """Physical name of the per-(event, shower, layer) table for ``name``."""
    return f"{LAYERS_PREFIX}{validate_experiment_name(name)}"


def profiles_table(name: str) -> str:
    """Physical name of the per-event depth and radial profile table for ``name``."""
    return f"{PROFILES_PREFIX}{validate_experiment_name(name)}"


def xgb_table(role: str, name: str) -> str:
    """Physical name of one model-analysis table of ``name``; ``role`` is a key of
    :data:`XGB_PREFIXES` (``run``, ``pred``, ``fold``, ``imp``, ``bin``, ``tree``)."""
    return f"{XGB_PREFIXES[role]}{validate_experiment_name(name)}"


def xgb_tables(name: str) -> dict[str, str]:
    """Every model-analysis table of ``name``, keyed by role."""
    return {role: xgb_table(role, name) for role in XGB_PREFIXES}


def all_tables(name: str) -> tuple[str, ...]:
    """Every physical table belonging to one experiment, for drop/cleanup."""
    return (
        hit_table(name),
        proj_table(name),
        proj_table(name, sampled=True),
        event_table(name),
        layers_table(name),
        profiles_table(name),
        *xgb_tables(name).values(),
    )


def is_managed_table(physical_name: str) -> bool:
    """Whether a physical table name was created by this application."""
    return physical_name.startswith(_PREFIXES)


def experiment_of(physical_name: str) -> str | None:
    """Recover the experiment name from a physical table name, if managed."""
    for prefix in _PREFIXES:
        if physical_name.startswith(prefix):
            base = physical_name[len(prefix) :]
            if prefix == PROJ_PREFIX and base.endswith(SAMPLE_SUFFIX):
                base = base[: -len(SAMPLE_SUFFIX)]
            return base or None
    return None


def quote(identifier: str) -> str:
    """Quote an already-validated identifier for interpolation into SQL.

    Belt and braces. The identifier reaching here has matched ``_NAME_PATTERN``
    (or is a prefix of one), so it cannot contain a double quote; doubling any
    that appear costs nothing and means this function is still correct if the
    pattern is ever loosened.
    """
    return '"' + identifier.replace('"', '""') + '"'
