"""Typography for the English sentences the server writes into payloads.

A negative number a reader sees is set with the true minus sign U+2212, never
the ASCII hyphen-minus - in notices, footnote text and disclosure sentences
alike, exactly as the interface does for ticks and tooltips (``format.js``).
JSON numbers are untouched: this is presentation only.
"""

from __future__ import annotations

import math
import re

MINUS = "−"

_SIGNED = re.compile(r"(?:(?<![\w.])|(?<=\de))-(?=\d)")


def fmt_signed(value: float | None, digits: int = 2, plus: bool = False, missing: str = "n/a") -> str:
    """``value`` to ``digits`` decimals with a typographic sign; ``plus`` marks positives too."""
    if value is None or not math.isfinite(float(value)):
        return missing
    text = f"{abs(float(value)):.{digits}f}"
    if float(text) == 0.0:
        return text
    if value < 0:
        return MINUS + text
    return f"+{text}" if plus else text


def typographic(text: str) -> str:
    """Replace every hyphen-minus that signs a number (or an exponent) with U+2212."""
    return _SIGNED.sub(MINUS, text)


def signed_hyphens(text: str) -> list[str]:
    """The places a hyphen-minus still signs a number, for tests."""
    return [text[max(0, m.start() - 12):m.end() + 6] for m in _SIGNED.finditer(text)]
