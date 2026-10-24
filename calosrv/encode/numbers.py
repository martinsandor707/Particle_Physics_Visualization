"""Numbers as the payloads ship them: six significant figures, plain Python types.

The 100 KB response contract (CLAUDE.md section 1.1) makes digits a budget: a
full-precision float64 costs ~24 characters of JSON against ~8 at six
significant figures, which is far beyond display precision. This is the rule
``query/energy.py`` has always applied, given one owner for the new payloads.

NumPy scalars are converted to ``int``/``float``: neither FastAPI's encoder
nor ``density.wire_size`` accepts ``np.int64``. Non-finite values become
``None``, which the interface renders as an em dash.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np

SIGNIFICANT = 6


def sig(value: Any, digits: int = SIGNIFICANT) -> float | None:
    """``value`` to ``digits`` significant figures; ``None`` for None, NaN or infinity."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return float(f"{number:.{int(digits)}g}")


def sig_list(values: Iterable[Any], digits: int = SIGNIFICANT) -> list[float | None]:
    return [sig(v, digits) for v in values]


def plain(value: Any) -> Any:
    """A NumPy scalar or array as its Python equivalent; anything else unchanged."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value
