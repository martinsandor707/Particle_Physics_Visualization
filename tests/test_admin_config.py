"""The defaults behind the Admin Settings panel: layers, persistence, validation, API.

The store tests run on plain experiment descriptions, the shape
``/api/experiments`` lists, so every layering rule is checked without a
database. The API tests use the booted server.
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest

from calosrv.admin import schema
from calosrv.admin.store import DefaultsStore
from calosrv.config import load_settings
from calosrv.errors import ValidationError

ALL_FRAMES = ["lab", "trans", "local", "canonical"]
MODELS = ["angle", "energy", "segmentation"]
CHANNELS = ["density", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy"]


def _experiment(name: str, status: str = "ready", frames=None) -> dict:
    return {"table_name": name, "display_name": name.title(), "status": status, "n_events": 2,
            "frames": frames or ALL_FRAMES, "models": MODELS, "channels": CHANNELS}


EXPERIMENTS = [_experiment("alpha"), _experiment("beta")]


@pytest.fixture
def make_store(tmp_path, monkeypatch):
    """A store on a temporary config file, with the given environment layer."""
    monkeypatch.setenv("CALOSRV_DATA_DIR", str(tmp_path / "data"))
    base = load_settings()

    def build(env: dict[str, str] | None = None) -> DefaultsStore:
        settings = dataclasses.replace(
            base, config_path=tmp_path / "config.json",
            env_defaults=tuple((env or {}).items()),
        )
        return DefaultsStore(settings)

    return build


def _values(store: DefaultsStore, experiments=EXPERIMENTS) -> dict[str, tuple]:
    resolved, _ = store.resolve(experiments)
    return {key: (entry["value"], entry["source"]) for key, entry in resolved.items()}


# -------------------------------------------------------------- layering --


def test_with_nothing_set_the_built_in_view_applies(make_store):
    values = _values(make_store())
    assert values == {
        "default_dataset": ("alpha", "builtin"),  # the oldest ready experiment
        "default_coord_system": ("lab", "builtin"),
        "default_model": ("segmentation", "builtin"),
        "default_channel": ("density", "builtin"),
        "default_display_mode": (None, "builtin"),
        "default_rho_norm": ("selection", "builtin"),
    }
    resolved, _ = make_store().resolve(EXPERIMENTS)
    assert resolved["default_display_mode"]["effective"] == "native"


def test_the_environment_sits_above_the_built_in_view(make_store):
    store = make_store({"default_coord_system": "trans", "default_dataset": "beta"})
    values = _values(store)
    assert values["default_coord_system"] == ("trans", "env")
    assert values["default_dataset"] == ("beta", "env")
    resolved, _ = store.resolve(EXPERIMENTS)
    assert resolved["default_display_mode"]["effective"] == "continuous"


def test_an_invalid_environment_value_is_ignored_and_reported(make_store, caplog):
    store = make_store({"default_model": "gpt", "default_channel": "gradcam"})
    values = _values(store)
    assert values["default_model"] == ("segmentation", "builtin")
    assert values["default_channel"] == ("gradcam", "env")
    notices = store.admin_view(EXPERIMENTS)["notices"]
    assert any("default_model" in n and "gpt" in n for n in notices)
    assert any("gpt" in record.getMessage() for record in caplog.records)


def test_a_save_overrides_the_environment_and_survives_a_restart(make_store, tmp_path):
    store = make_store({"default_coord_system": "trans"})
    store.update({"default_coord_system": "local", "default_channel": "shapcam"}, EXPERIMENTS)
    assert _values(store)["default_coord_system"] == ("local", "admin")

    reopened = make_store({"default_coord_system": "trans"})
    assert _values(reopened)["default_coord_system"] == ("local", "admin")
    assert _values(reopened)["default_channel"] == ("shapcam", "admin")
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["schema_version"] == 1 and saved["updated_at"]
    assert saved["defaults"] == {"default_channel": "shapcam", "default_coord_system": "local"}


def test_a_null_clears_the_saved_value_so_the_layer_beneath_shows(make_store):
    store = make_store({"default_coord_system": "trans"})
    store.update({"default_coord_system": "canonical"}, EXPERIMENTS)
    store.update({"default_coord_system": None}, EXPERIMENTS)
    assert _values(store)["default_coord_system"] == ("trans", "env")
    assert store.admin_view(EXPERIMENTS)["overrides"] == {}


def test_a_save_leaves_no_temporary_file_behind(make_store, tmp_path):
    make_store().update({"default_rho_norm": "dataset"}, EXPERIMENTS)
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("config")) == [
        "config.json"
    ]


# ------------------------------------------------------------ validation --


@pytest.mark.parametrize("patch, field", [
    ({"default_frame": "lab"}, "default_frame"),
    ({"default_channel": "jet"}, "default_channel"),
    ({"default_coord_system": "se3"}, "default_coord_system"),
    ({"default_display_mode": "smooth"}, "default_display_mode"),
    ({"default_dataset": "Not A Name"}, "default_dataset"),
])
def test_an_invalid_save_names_its_field_and_writes_nothing(make_store, tmp_path, patch, field):
    store = make_store()
    with pytest.raises(ValidationError) as info:
        store.update(patch, EXPERIMENTS)
    assert info.value.extra["field"] == field
    assert not (tmp_path / "config.json").exists()


def test_an_unregistered_experiment_is_refused(make_store):
    with pytest.raises(ValidationError) as info:
        make_store().update({"default_dataset": "gamma"}, EXPERIMENTS)
    assert info.value.extra["field"] == "default_dataset"
    assert "gamma" in info.value.detail


def test_a_frame_the_default_experiment_does_not_offer_is_refused(make_store):
    lab_only = [_experiment("alpha", frames=["lab", "canonical"])]
    with pytest.raises(ValidationError) as info:
        make_store().update({"default_coord_system": "trans"}, lab_only)
    assert info.value.extra["field"] == "default_coord_system"
    assert "does not offer 'trans'" in info.value.detail


def test_a_save_body_must_be_an_object(make_store):
    with pytest.raises(ValidationError):
        make_store().update(["default_model", "energy"], EXPERIMENTS)


# ---------------------------------------------------------- broken files --


def test_an_unreadable_file_is_set_aside_and_the_panel_is_told(make_store, tmp_path):
    (tmp_path / "config.json").write_text("{not json")
    store = make_store()
    assert _values(store)["default_coord_system"] == ("lab", "builtin")
    assert any("could not be read" in n for n in store.admin_view(EXPERIMENTS)["notices"])
    assert not (tmp_path / "config.json").exists()
    assert len(list(tmp_path.glob("config.json.corrupt-*"))) == 1


def test_one_bad_saved_value_keeps_the_others(make_store, tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({
        "schema_version": 1, "updated_at": "2026-09-27T10:00:00+00:00",
        "defaults": {"default_coord_system": "trans", "default_channel": "jet"},
    }))
    store = make_store()
    assert _values(store)["default_coord_system"] == ("trans", "admin")
    assert _values(store)["default_channel"] == ("density", "builtin")
    assert any("jet" in n for n in store.admin_view(EXPERIMENTS)["notices"])


# ------------------------------------------------------ dataset fallback --


def test_a_default_experiment_that_is_not_ready_falls_back_and_says_so(make_store):
    experiments = [_experiment("alpha"), _experiment("beta", status="ingesting")]
    store = make_store({"default_dataset": "beta"})
    resolved, notices = store.resolve(experiments)
    assert resolved["default_dataset"] == {"value": "alpha", "source": "fallback",
                                           "configured": "beta"}
    assert any("'beta' is ingesting" in n and "'alpha'" in n for n in notices)


def test_the_boot_block_uses_the_interface_state_names(make_store):
    store = make_store()
    store.update({"default_coord_system": "trans", "default_display_mode": "native"}, EXPERIMENTS)
    block = store.boot_block(EXPERIMENTS)
    assert block == {"table_name": "alpha", "frame": "trans", "model": "segmentation",
                     "channel": "density", "display": "native", "rho_norm": "selection",
                     "notices": []}


def test_every_field_has_a_state_key_and_a_built_in_value():
    assert set(schema.FIELDS) == set(schema.BUILTIN) == set(schema.STATE_KEYS)


# ----------------------------------------------- unnamed-table requests --


def test_a_request_naming_no_experiment_opens_the_default_one(ingested, make_store):
    from calosrv.api.deps import resolve_table
    from calosrv.db.bootstrap import drop_experiment
    from calosrv.ingest import pipeline

    from conftest import SEED_CSV

    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        pipeline.run_ingest(con, settings, "second_default", SEED_CSV, build_sample=False)
    try:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            defaults=make_store({"default_dataset": "second_default"}))))
        with database.read_cursor() as con:
            assert resolve_table(con, request, None).table_name == "second_default"
            request.app.state.defaults = make_store({"default_dataset": "absent_one"})
            oldest = resolve_table(con, request, None).table_name
            assert oldest != "second_default"
    finally:
        with database.write_lock() as con:
            drop_experiment(con, "second_default", settings)


# ------------------------------------------------------------------- API --


def test_the_panel_reads_the_default_view_and_its_sources(client):
    body = client.get("/api/admin/config").json()
    assert body["defaults"]["default_coord_system"] == {"value": "lab", "source": "builtin"}
    assert body["defaults"]["default_dataset"]["value"] == "experiment_baseline"
    assert body["options"]["coord_systems"] == ALL_FRAMES
    assert "experiment_baseline" in {d["table_name"] for d in body["options"]["datasets"]}
    assert body["auto_ingest"]["enabled"] is False


def test_saving_in_the_panel_changes_what_a_new_session_opens_on(client):
    saved = client.post("/api/admin/config",
                        json={"default_coord_system": "canonical", "default_channel": "gradcam"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["defaults"]["default_coord_system"]["source"] == "admin"
    boot = client.get("/api/experiments").json()["defaults"]
    assert (boot["frame"], boot["channel"]) == ("canonical", "gradcam")

    cleared = client.post("/api/admin/config",
                          json={"default_coord_system": None, "default_channel": None})
    assert cleared.json()["overrides"] == {}
    boot = client.get("/api/experiments").json()["defaults"]
    assert (boot["frame"], boot["channel"]) == ("lab", "density")


def test_an_invalid_save_is_a_problem_naming_the_field(client):
    response = client.post("/api/admin/config", json={"default_frame": "lab"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["field"] == "default_frame"


def test_saving_does_not_change_the_api_parameter_defaults(client):
    """The panel governs the interface's cold boot; an API call stays a function of its parameters."""
    client.post("/api/admin/config", json={"default_coord_system": "trans"})
    try:
        meta = client.get("/api/projections").json()["meta"]
        assert meta["coord_system"] == "lab"
    finally:
        client.post("/api/admin/config", json={"default_coord_system": None})
