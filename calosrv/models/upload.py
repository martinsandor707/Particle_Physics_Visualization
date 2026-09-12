"""Upload request validation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class UploadMode(str, Enum):
    """What to do with an experiment name that may already exist.

    ``CREATE_NEW`` drops every table belonging to that name first, producing a
    clean, isolated experiment. ``APPEND`` adds to the existing one, and is
    rejected if the incoming event numbers overlap those already present -
    merging two files that each number events from zero would fuse distinct
    physics events.
    """

    CREATE_NEW = "create_new"
    APPEND = "append"


class UploadRequest(BaseModel):
    table_name: str = Field(
        ...,
        description=(
            "Experiment name: lowercase letters, digits and underscores, "
            "starting with a letter."
        ),
    )
    mode: UploadMode = UploadMode.CREATE_NEW
    display_name: str = ""
    event_offset: int = Field(
        0,
        description=(
            "Shift incoming event numbers by this amount, so a second file that "
            "also numbers events from zero can be appended without collision."
        ),
    )
