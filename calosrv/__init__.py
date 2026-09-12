"""Out-of-core calorimeter shower reconstruction diagnostic server.

``calosrv`` is the client-server half of this repository. It keeps multi-gigabyte
calorimeter inference CSVs in DuckDB and performs every spatial transformation,
dynamic binning and statistical reduction server-side, handing the browser only
pre-aggregated visual payloads. The frontend never receives a raw hit array.

The batch half - ``build_dashboard.py`` plus the ``calodash`` package - is
untouched and still compiles a standalone ``.html`` file for datasets small
enough to live in a browser. The two packages share no imports on purpose: the
estimators ``calosrv`` needs are re-implemented here so that neither path can
break the other, and ``calosrv/stats/gaussian.py`` documents where it must stay
numerically identical to ``calodash/stats.py``.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
