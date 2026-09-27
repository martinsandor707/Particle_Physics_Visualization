"""The six defaults the Admin Settings panel sets, and how a value is validated.

Each field holds a value or ``None`` - "not set at this layer, ask the one
below". The allowed values are exactly the ones the API accepts, read from the
tuples that define them there, so a frame, model or channel the API gains is
offered by the panel without a second list to keep in step.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

import pydantic
from pydantic import BaseModel, ConfigDict, field_validator

from ..db import ddl, naming
from ..errors import ValidationError
from ..grid.resolution import DISPLAY_MODES
from ..query.density import NORMS
from ..query.experiments import FRAME_KINDS
from ..query.planes import CHANNELS

#: The fields, in the order the panel shows them.
FIELDS: tuple[str, ...] = (
    "default_dataset",
    "default_coord_system",
    "default_model",
    "default_channel",
    "default_display_mode",
    "default_rho_norm",
)

#: The bottom layer: the interface's own built-in view, ``state.js`` DEFAULTS
#: (a test holds the two equal). It never moves. The URL hash is written
#: relative to it, so changing it would silently re-read every saved link - the
#: team's view is set in the panel instead.
BUILTIN: dict[str, str | None] = {
    "default_dataset": None,  # the oldest ready experiment
    "default_coord_system": "lab",
    "default_model": "segmentation",
    "default_channel": "density",
    "default_display_mode": None,  # each frame's own: native in the lab, continuous elsewhere
    "default_rho_norm": "selection",
}

#: The interface state key each field sets (``state.js``).
STATE_KEYS: dict[str, str] = {
    "default_dataset": "table_name",
    "default_coord_system": "frame",
    "default_model": "model",
    "default_channel": "channel",
    "default_display_mode": "display",
    "default_rho_norm": "rho_norm",
}

#: The values each enumerated field accepts.
CHOICES: dict[str, tuple[str, ...]] = {
    "default_coord_system": FRAME_KINDS,
    "default_model": ddl.MODELS,
    "default_channel": CHANNELS,
    "default_display_mode": DISPLAY_MODES,
    "default_rho_norm": NORMS,
}


class DisplayDefaults(BaseModel):
    """One layer of defaults. Every field may be unset."""

    model_config = ConfigDict(extra="forbid")

    default_dataset: Optional[str] = None
    default_coord_system: Optional[Literal[FRAME_KINDS]] = None
    default_model: Optional[Literal[ddl.MODELS]] = None
    default_channel: Optional[Literal[CHANNELS]] = None
    default_display_mode: Optional[Literal[DISPLAY_MODES]] = None
    default_rho_norm: Optional[Literal[NORMS]] = None

    @field_validator("default_dataset")
    @classmethod
    def _experiment_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return naming.validate_experiment_name(value)
        except ValidationError as exc:
            raise ValueError(exc.detail) from None


def _message(field: str, error: dict[str, Any], data: dict[str, Any]) -> str:
    if error.get("type") == "extra_forbidden":
        return f"Unknown setting {field!r}; the settings are {', '.join(FIELDS)}."
    if field in CHOICES:
        allowed = ", ".join(CHOICES[field])
        return f"{field} must be one of {allowed}, or null; got {data.get(field)!r}."
    return f"{field}: {error.get('msg', 'invalid value')}"


def clean(data: Any) -> dict[str, str | None]:
    """Validate one layer strictly - the panel's save.

    Returns every key that was sent, with ``None`` kept: in a save, a null
    clears that field's override. Raises the API's 422 ``ValidationError``
    naming the offending field, which the panel shows beside that control.
    """
    if not isinstance(data, dict):
        raise ValidationError(
            "The defaults must be a JSON object keyed by setting name.", field="body"
        )
    try:
        model = DisplayDefaults.model_validate(data)
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        field = str(first["loc"][0]) if first.get("loc") else "body"
        raise ValidationError(_message(field, first, data), field=field) from None
    return {key: getattr(model, key) for key in data}


def clean_lenient(data: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Validate field by field, keeping what is valid - a saved file or the environment.

    One bad value must not discard the others: a hand-edited file with a typo
    in one field keeps the rest. Returns the valid, non-null values and a
    sentence for each one that was dropped.
    """
    kept: dict[str, str] = {}
    problems: list[str] = []
    for key, value in data.items():
        try:
            value = clean({key: value})[key]
        except ValidationError as exc:
            problems.append(exc.detail)
            continue
        if value is not None:
            kept[key] = value
    return kept, problems
