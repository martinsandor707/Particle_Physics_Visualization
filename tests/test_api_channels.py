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


#: The four reference frames of the interface, as (coord_system, frame).
FRAMES = [("lab", "lab"), ("trans", "lab"), ("local", "lab"), ("lab", "canonical")]


@pytest.mark.parametrize("coord_system,frame", FRAMES)
@pytest.mark.parametrize("model", ddl.MODELS)
@pytest.mark.parametrize("channel", panels.CHANNELS)
@pytest.mark.parametrize("display,r", [("native", 150), ("continuous", 150), ("continuous", 400)])
def test_every_view_stays_under_the_payload_contract(client, coord_system, frame, model, channel,
                                                      display, r):
    response = client.get("/api/projections", params={
        "coord_system": coord_system, "frame": frame, "model": model, "channel": channel,
        "display": display, "resolution": r,
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


# ------------------------------------------------------ per-shower frames --


@pytest.mark.parametrize("coord_system,symbols", [
    ("trans", {"x": "Δx", "y": "Δy", "z": "Δz"}),
    ("local", {"x": "u", "y": "v", "z": "w"}),
])
def test_the_per_shower_frames_answer_with_their_own_contract(client, coord_system, symbols):
    body = client.get("/api/projections", params={"coord_system": coord_system}).json()
    assert body["meta"]["coord_system"] == coord_system
    frame = body["frame"]
    assert frame["kind"] == coord_system
    assert frame["n_showers"] == 2 * frame["n_events"]
    assert frame["splat"]["regime"] == ("box_overlap" if coord_system == "trans" else "subdeposit3d")
    assert frame["depth"]["policy"] == ("native_layers" if coord_system == "trans" else "uniform_bins")
    assert set(frame["comb"]["lag1"]) == ({"x", "y"} if coord_system == "trans" else {"x", "y", "z"})
    axes = body["panels"]["xy"]["axes"]
    assert (axes["col"]["symbol"], axes["row"]["symbol"]) == (symbols["x"], symbols["y"])
    assert body["panels"]["yz"]["axes"]["col"]["symbol"] == symbols["z"]

    # Superimposed at the origin: no separation, an offset instead.
    for key in ("truth_voxel", "pred_voxel"):
        assert body["centroids"][key]["separation_mm"] is None
        assert "offset_mm" in body["centroids"][key]
    mean = body["centroids"]["frame_mean"]
    assert mean["n"] == frame["n_events"]
    assert set(mean["sd"]) == set(mean["ci95_half"]) == {"a", "b"}

    if coord_system == "trans":
        trajectories = body["overlays"]["trajectories"]
        assert trajectories and all(t["a"]["x"] == t["a"]["y"] == t["a"]["z"] == 0.0
                                    for t in trajectories)
        assert "coherence" in frame
    else:
        assert body["overlays"] == {}
        assert "coherence" not in frame
    text = " ".join(n["text"] for n in body["meta"]["notices"])
    assert "x′" not in text and "X′" not in text, "canonical wording leaked into a per-shower frame"


def test_a_per_shower_density_request_reuses_any_models_bundle(client):
    client.get("/api/projections", params={"coord_system": "local", "model": "energy",
                                           "channel": "gradcam", "e2_max": 19.0})
    body = client.get("/api/projections", params={"coord_system": "local", "model": "angle",
                                                  "e2_max": 19.0}).json()
    assert body["meta"]["cached"] is True


def test_the_catalogue_advertises_every_frame_model_and_channel(client):
    experiments = client.get("/api/experiments").json()["experiments"]
    ready = [e for e in experiments if e["status"] == "ready"]
    assert ready
    for entry in ready:
        assert entry["frames"] == ["lab", "trans", "local", "canonical"]
        assert entry["coord_systems"] == list(ddl.COORD_SYSTEMS)
        assert entry["models"] == list(ddl.MODELS)
        assert entry["channels"] == list(panels.CHANNELS)
        assert entry["schema"] == {"name": ddl.SCHEMA_NAME, "version": ddl.SCHEMA_VERSION,
                                   "n_columns": len(ddl.HIT_COLUMN_NAMES)}
        assert entry["archive"]["present"] is True
        assert entry["archive"]["parts"] >= 1 and entry["archive"]["rows"] > 0


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


@pytest.mark.parametrize("coord_system,frame", FRAMES)
@pytest.mark.parametrize("channel", panels.CHANNELS)
@pytest.mark.parametrize("display", ["native", "continuous"])
def test_no_server_sentence_signs_a_number_with_a_hyphen(client, coord_system, frame, channel, display):
    """S3: every negative number in a notice or note is set with U+2212."""
    from calosrv.text import signed_hyphens

    bodies = [client.get("/api/projections", params={
        "coord_system": coord_system, "frame": frame, "channel": channel, "display": display,
    }).json()]
    if channel == "density" and display == "native":
        bodies.append(client.get("/api/energy-distribution",
                                 params={"coord_system": coord_system}).json())
        for model in ddl.MODELS:
            bodies.append(client.get("/api/model-performance",
                                     params={"model": model, "coord_system": coord_system}).json())
    for body in bodies:
        for path, text in _strings(body):
            if path.endswith(("data", ".table_name", ".column", "source_files")):
                continue
            assert not signed_hyphens(text), (path, signed_hyphens(text))
