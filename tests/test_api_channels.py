"""The /api/projections contract for coord_system, model and channel.

Booted-server tests only (the `client` fixture), kept apart from the
ingested-database tests of test_channels.py because the two share DuckDB's
process-wide connection (see conftest.py).
"""

from __future__ import annotations

import pytest

from calosrv.db import ddl
from calosrv.query import density, panels

# ------------------------------------------------------------ the route --


def test_the_interface_defaults_are_lab_segmentation_density(client):
    body = client.get("/api/projections").json()
    assert body["meta"]["coord_system"] == "lab"
    assert body["meta"]["model"] == "segmentation"
    assert body["meta"]["channel"] == "density"
    assert "frame" not in body


@pytest.mark.parametrize("params,field", [
    ({"model": "gpt"}, "model"),
    ({"coord_system": "polar"}, "coord_system"),
    ({"channel": "saliency"}, "channel"),
    ({"channel": "gradcam", "mode": "density"}, "channel"),
    ({"frame": "canonical", "coord_system": "local"}, "coord_system"),
])
def test_invalid_parameters_are_refused(client, params, field):
    response = client.get("/api/projections", params=params)
    assert response.status_code == 422
    assert response.json().get("field") == field


def test_the_deprecated_mode_alias_still_selects_the_channel(client):
    body = client.get("/api/projections", params={"mode": "gradcam"}).json()
    assert body["meta"]["channel"] == "gradcam"
    assert body["panels"]["xy"]["scale"]["quantity"] == "gradcam"


@pytest.mark.parametrize("frame", ["lab", "canonical"])
@pytest.mark.parametrize("model", ddl.MODELS)
@pytest.mark.parametrize("channel", panels.CHANNELS)
@pytest.mark.parametrize("display,r", [("native", 150), ("continuous", 150), ("continuous", 400)])
def test_every_view_stays_under_the_payload_contract(client, frame, model, channel, display, r):
    response = client.get("/api/projections", params={
        "frame": frame, "model": model, "channel": channel, "display": display, "resolution": r,
    })
    assert response.status_code == 200, response.text
    assert len(response.content) < density.RESPONSE_LIMIT
    assert density.wire_size(response.json()) == len(response.content)


def test_a_density_request_reuses_any_models_bundle(client):
    client.get("/api/projections", params={"model": "segmentation", "e1_max": 19.0})
    body = client.get("/api/projections", params={"model": "angle", "e1_max": 19.0}).json()
    assert body["meta"]["cached"] is True
    cam = client.get("/api/projections", params={"model": "angle", "channel": "gradcam",
                                                 "e1_max": 19.0}).json()
    assert cam["meta"]["cached"] is False, "a CAM channel needs the model's own planes"


def test_the_lab_guard_lowers_r_and_says_so(client, monkeypatch):
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 30_000)
    body = client.get("/api/projections", params={"display": "continuous", "resolution": 400,
                                                  "e1_max": 18.5}).json()
    resolution = body["meta"]["resolution"]
    assert resolution["requested"] == 400 and resolution["r_x"] < 400
    texts = [n["text"] for n in body["meta"]["notices"]]
    assert any("Resolution lowered from R = 400" in t for t in texts)
