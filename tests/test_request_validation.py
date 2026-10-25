"""A parameter of the wrong type, or a missing required one, is the app's own validation problem.

FastAPI's default answer is ``{"detail": [...]}``; every other refusal here is a
``/problems/validation-error`` naming the field, which the frontend shows beside
the card. One shape for every 422.
"""

from __future__ import annotations

import pytest

from calosrv.text import signed_hyphens


@pytest.mark.parametrize("path, params, field", [
    ("/api/projections", {"e1_min": "abc"}, "e1_min"),
    ("/api/energy-distribution", {"bins": "many"}, "bins"),
    ("/api/event", {}, "event_number"),
    ("/api/event", {"event_number": "first"}, "event_number"),
])
def test_type_and_missing_parameter_errors_are_validation_problems(client, path, params, field):
    reply = client.get(path, params=params)
    assert reply.status_code == 422
    assert reply.headers["content-type"].startswith("application/problem+json")
    problem = reply.json()
    assert problem["type"] == "/problems/validation-error" and problem["status"] == 422
    assert problem["field"] == field and field in problem["detail"]
    assert not signed_hyphens(problem["detail"])
