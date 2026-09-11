"""Input schema detection.

Two dataset variants exist in this study. The single-particle ``standalone``
files carry one thrown particle per event; the ``2combined`` files overlay two
particles and add the columns needed to define a separation ``D``. Only the
former is present in this repository, but the whole pipeline branches on the
value returned here so the second can be dropped in without a rewrite.
"""

from __future__ import annotations

import re
from enum import Enum


class SchemaKind(str, Enum):
    """Which dataset variant an input file follows."""

    STANDALONE = "standalone"
    OVERLAP = "overlap"


#: Columns that must be present for the single-particle variant.
STANDALONE_REQUIRED = frozenset(
    {
        "event_number",
        "x",
        "y",
        "z",
        "energy",
        "incoming_momentum",
        "incoming_theta",
        "incoming_phi",
    }
)

#: Columns that identify the two-shower overlap variant. ``particle_origin``
#: labels each hit 'A' or 'B'; the per-particle kinematics are suffixed.
OVERLAP_REQUIRED = frozenset(
    {
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
    }
)

#: Any column matching this is a model inference output rather than simulation
#: ground truth. Presence flips the dashboard out of baseline mode; absence
#: triggers the CLAUDE.md section 3 fallback (warning banner, disabled controls,
#: never fabricated numbers).
_PREDICTION_PATTERN = re.compile(
    r"(_pred$|^pred_|gradcam|grad_cam|_cam$|"
    r"^e1_|^e2_|segmentation|_iou$|confidence|attention)",
    re.IGNORECASE,
)


class SchemaError(ValueError):
    """Raised when an input file matches no known dataset variant."""


def detect_schema(columns) -> SchemaKind:
    """Classify a column collection as a known dataset variant.

    ``OVERLAP`` is tested first: an overlap file also satisfies most of the
    standalone requirements, so the more specific match has to win.
    """
    present = frozenset(columns)
    if OVERLAP_REQUIRED <= present:
        return SchemaKind.OVERLAP
    if STANDALONE_REQUIRED <= present:
        return SchemaKind.STANDALONE

    missing = sorted(STANDALONE_REQUIRED - present)
    raise SchemaError(
        "Input file matches neither the standalone nor the 2combined schema. "
        f"Missing standalone columns: {', '.join(missing)}. "
        f"Columns present: {', '.join(sorted(present))}."
    )


def find_prediction_columns(columns) -> list[str]:
    """Return any columns that look like model inference outputs.

    An empty list means the dashboard must operate in ground-truth baseline
    mode. Nothing downstream may invent values to fill the gap.
    """
    return sorted(c for c in columns if _PREDICTION_PATTERN.search(str(c)))
