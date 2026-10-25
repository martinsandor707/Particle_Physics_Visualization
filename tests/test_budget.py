"""The shared measured size guard (``calosrv/api/budget.py``)."""

from __future__ import annotations

import pytest

from calosrv.api import budget
from calosrv.models.common import ApiMeta, envelope
from calosrv.query import density


def _build(cap: int, notices: list[str]) -> dict:
    """A body of ``cap`` ten-character items, its steps said in the warnings."""
    return envelope(ApiMeta(table_name="t", warnings=list(notices)), items=["x" * 10] * cap)


def _halve(cap: int, size: int, limit: int) -> int | None:
    return cap // 2 if cap > 1 else None


def _say(old: int, new: int, size: int, limit: int) -> str:
    return f"cap {old} -> {new} ({size:,} bytes over {limit:,})"


def test_a_body_that_fits_is_served_untouched(monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 10_000)
    body = budget.serve_measured(_build, 100, _halve, _say)
    assert len(body["items"]) == 100 and body["meta"]["warnings"] == []


def test_each_step_is_said_in_the_body_it_produced(monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 2_000)
    body = budget.serve_measured(_build, 1_000, _halve, _say)
    n = len(body["items"])
    assert density.wire_size(body) < 2_000 and n < 1_000
    steps = body["meta"]["warnings"]
    assert steps[0].startswith("cap 1000 -> 500 (")
    assert steps[-1].split(" (")[0].endswith(str(n))
    # One sentence per halving, nothing else.
    assert len(steps) == (1_000 // n).bit_length() - 1


def test_an_overrun_is_served_with_the_size_that_carries_it(monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 120)
    body = budget.serve_measured(_build, 64, _halve, _say, attempts=2,
                                 remedy="fewer items bring it under")
    size = density.wire_size(body)
    assert size >= 120
    final = body["meta"]["warnings"][-1]
    assert f"still {size:,} bytes" in final and "fewer items bring it under" in final
    assert len(body["meta"]["warnings"]) == 3      # two steps, then the overrun


def test_nothing_smaller_stops_the_guard_at_once(monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 10)
    body = budget.serve_measured(_build, 1, _halve, _say)
    (final,) = body["meta"]["warnings"]
    assert f"still {density.wire_size(body):,} bytes" in final


@pytest.mark.parametrize("limit", [50, 400, 5_000])
def test_the_limit_is_read_at_call_time(monkeypatch, limit):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", limit)
    body = budget.serve_measured(_build, 2_000, _halve, _say, attempts=20)
    assert density.wire_size(body) < limit or "still" in body["meta"]["warnings"][-1]
