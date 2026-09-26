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


def all_tables(name: str) -> tuple[str, ...]:
    """Every physical table belonging to one experiment, for drop/cleanup."""
    return (
        hit_table(name),
        proj_table(name),
        proj_table(name, sampled=True),
        event_table(name),
    )


def is_managed_table(physical_name: str) -> bool:
    """Whether a physical table name was created by this application."""
    return physical_name.startswith((HIT_PREFIX, PROJ_PREFIX, EVENT_PREFIX))


def experiment_of(physical_name: str) -> str | None:
    """Recover the experiment name from a physical table name, if managed."""
    for prefix in (HIT_PREFIX, PROJ_PREFIX, EVENT_PREFIX):
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
