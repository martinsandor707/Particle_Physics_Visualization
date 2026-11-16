"""A parameter of the wrong type, or a missing required one, is the app's own validation problem.

FastAPI's default answer is ``{"detail": [...]}``; every other refusal here is a
``/problems/validation-error`` naming the field, which the frontend shows beside
the card. One shape for every 422, the event pickers' ``basis`` refusals included.
"""

from __future__ import annotations

import pytest

from calosrv.text import signed_hyphens


@pytest.mark.parametrize("path, params, field", [
    ("/api/projections", {"e1_min": "abc"}, "e1_min"),
    ("/api/energy-distribution", {"bins": "many"}, "bins"),
    ("/api/event", {}, "event_number"),
    ("/api/event", {"event_number": "first"}, "event_number"),
    ("/api/event", {"event_number": 0, "particle_p_min": "five"}, "particle_p_min"),
    ("/api/event/candidates", {"particle_theta_max": "steep"}, "particle_theta_max"),
    ("/api/event/candidates", {"event_number": "first"}, "event_number"),
    ("/api/event/pick", {"draw": "next"}, "draw"),
    ("/api/event/pick", {"draw": -1}, "draw"),
    # The pickers' basis: an unknown one, and a selection bound sent with the whole experiment.
    ("/api/event/pick", {"basis": "x"}, "basis"),
    ("/api/event/candidates", {"basis": "experiment", "e1_min": 1.0}, "e1_min"),
    ("/api/event", {"event_number": 0, "basis": "experiment", "include_undefined_d": "true"},
     "include_undefined_d"),
    # An explicit false is refused too: the experiment basis's echo would contradict it (review R4).
    ("/api/event/candidates", {"basis": "experiment", "include_undefined_d": "false"},
     "include_undefined_d"),
    ("/api/event/pick", {"basis": "experiment", "include_undefined_d": "0"}, "include_undefined_d"),
])
def test_type_and_missing_parameter_errors_are_validation_problems(client, path, params, field):
    reply = client.get(path, params=params)
    assert reply.status_code == 422
    assert reply.headers["content-type"].startswith("application/problem+json")
    problem = reply.json()
    assert problem["type"] == "/problems/validation-error" and problem["status"] == 422
    assert problem["field"] == field and field in problem["detail"]
    assert not signed_hyphens(problem["detail"])
