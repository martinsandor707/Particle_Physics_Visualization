"""Detector geometry: the lattice, resampling, and the entrance slab.

This package owns every conversion between a bin index and a physical
millimetre position. Nothing outside it multiplies an index by a pitch, because
on this detector that would be wrong: the transverse x lattice is irregular.
"""

from __future__ import annotations

from .lattice import Axis, Lattice
from .resolution import ResolutionPlan, plan_resolution
from .slab import slab_layer_count

__all__ = ["Axis", "Lattice", "ResolutionPlan", "plan_resolution", "slab_layer_count"]
