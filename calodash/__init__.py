"""Build-phase library for the calorimeter shower reconstruction diagnostic dashboard.

The package compiles a standalone, fully client-side ``dashboard.html`` from raw
calorimeter hit data. Nothing here renders at request time: every aggregation,
coordinate transform and spatial binning step runs during the build, and the
browser only filters pre-quantised integer cell indices.

Module layout mirrors the pipeline stages:

``schema``       detect which dataset variant an input file is
``ingest``       chunked CSV reading
``sanitize``     validation and unphysical-record removal
``lattice``      detector cell lattice and the display binning grids
``geometry``     shower-local coordinate transform
``reconstruct``  conventional calorimetric energy reconstruction
``stats``        the estimators transcribed from ``plan-viz.ipynb``
``payload``      typed-array encoding of the browser payload
``render``       HTML assembly
"""

__all__ = [
    "constants",
    "schema",
    "cli",
    "ingest",
    "sanitize",
    "lattice",
    "geometry",
    "reconstruct",
    "stats",
    "payload",
    "render",
]

__version__ = "1.0.0"
