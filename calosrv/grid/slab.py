"""The shower-entrance slab used by the XY projection.

The XY panel shows the transverse plane at shower entry. "Entry" is a depth
window, not a single layer: a 120 mm slab measured from the calorimeter front
face, as specified.

One design note that matters for performance. The front face is a *global*
constant - every event in the dataset starts at z = 3662.4 mm, the physical
entrance plane of the detector - not a per-event minimum. So the slab reduces to
a literal integer comparison on the stored layer index, which DuckDB's zone maps
can use, rather than a window function computing ``min(z)`` per event over 22.5
million rows.

This differs from ``calodash/geometry.py``, which recentres each event on its own
first hit layer. That choice is correct for the shower-local frame the batch
dashboard works in, and wrong here: these projections are in the global detector
frame, where the entrance plane is a fixed piece of hardware.
"""

from __future__ import annotations

import numpy as np

#: Depth of the entrance window, in millimetres.
DEFAULT_SLAB_MM = 120.0


def slab_layer_count(z_coords: np.ndarray, slab_mm: float = DEFAULT_SLAB_MM) -> int:
    """Highest layer index within ``slab_mm`` of the front face.

    With the measured 20.5 mm pitch and a 120 mm window this yields index 5,
    i.e. the six layers at 3662.4 through 3764.9 mm; the seventh layer sits at
    3785.4 mm, outside the window.

    Returns an inclusive index, so the SQL predicate is ``iz <= slab_iz``.
    """
    if z_coords.size == 0:
        return 0
    front = float(z_coords[0])
    inside = np.nonzero(z_coords <= front + slab_mm)[0]
    # Always keep at least the entrance layer itself, even for a slab narrower
    # than one pitch; an empty XY panel would be a worse answer than one layer.
    return int(inside[-1]) if inside.size else 0
