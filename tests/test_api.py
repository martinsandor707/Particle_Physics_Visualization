"""End-to-end HTTP behaviour, including the automatic baseline seeding."""

from __future__ import annotations

import json
import re
import time

import pytest

from calosrv.app import BASELINE_TABLE

# The booted-server `client` fixture lives in conftest.py: the export-asset
# tests need the same running app, and two independently booted copies would
# each reset the shared DuckDB connection under the other.


def test_baseline_is_seeded_from_the_whole_demonstration_csv(client):
    """All 1000 rows, through the real pipeline, with no synthetic records."""
    payload = client.get("/api/experiments").json()
    baseline = next(
        e for e in payload["experiments"] if e["table_name"] == BASELINE_TABLE
    )
    assert baseline["status"] == "ready"
    assert baseline["n_hits"] == 1000
    assert baseline["n_events"] == 2
    assert "hits_all_models_dummy.parquet" in baseline["source_files"]


def test_experiments_reports_the_compute_allocation(client):
    """The header badge needs the resolved memory ceiling and thread count."""
    compute = client.get("/api/experiments").json()["compute"]
    assert compute["duckdb_memory_gb"] == 2
    assert compute["threads"] >= 2
    assert compute["debounce_ms"] == 150


def test_health_reports_the_memory_ceiling(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["duckdb_memory_gb"] == 2


@pytest.mark.parametrize(
    "params",
    [
        {"display": "native"},
        {"display": "continuous", "resolution": 150},
        {"display": "continuous", "resolution": 200},
        {"display": "native", "mode": "gradcam"},
        {"display": "native", "mode": "gradcam", "weighting": "count"},
    ],
)
def test_projections_render_and_stay_within_budget(client, params):
    response = client.get("/api/projections", params=params)
    assert response.status_code == 200
    assert len(response.content) < 100_000

    body = response.json()
    assert set(body["panels"]) == {"xy", "yz", "xz"}
    for panel in body["panels"].values():
        assert panel["encoding"] == "u8-b64"
        assert isinstance(panel["data"], str)


def test_resolution_two_hundred_produces_the_declared_shape(client):
    """R must actually change the grid, and the response must say what it did."""
    at_150 = client.get(
        "/api/projections", params={"display": "continuous", "resolution": 150}
    ).json()
    at_200 = client.get(
        "/api/projections", params={"display": "continuous", "resolution": 200}
    ).json()

    assert at_150["meta"]["resolution"]["r_x"] == 150
    assert at_200["meta"]["resolution"]["r_x"] == 200
    assert at_200["panels"]["xy"]["shape"][1] == 200
    assert at_200["panels"]["xy"]["shape"] != at_150["panels"]["xy"]["shape"]

    # Depth is locked to the native sampling layers in both.
    assert at_150["meta"]["resolution"]["r_z"] == at_200["meta"]["resolution"]["r_z"]


def test_native_mode_matches_the_measured_lattice(client):
    experiments = client.get("/api/experiments").json()["experiments"]
    baseline = next(e for e in experiments if e["table_name"] == BASELINE_TABLE)
    native = baseline["native_resolution"]

    body = client.get("/api/projections", params={"display": "native"}).json()
    assert body["panels"]["xy"]["shape"] == native["xy"]
    assert body["panels"]["yz"]["shape"] == native["yz"]
    assert body["panels"]["xz"]["shape"] == native["xz"]


def test_splatting_conserves_energy_across_resolutions(client):
    """The same selection must hold the same energy at any display resolution."""
    totals = []
    for params in (
        {"display": "native"},
        {"display": "continuous", "resolution": 90},
        {"display": "continuous", "resolution": 250},
    ):
        body = client.get("/api/projections", params=params).json()
        totals.append(body["panels"]["yz"]["total"])
    assert totals[1] == pytest.approx(totals[0], rel=1e-9)
    assert totals[2] == pytest.approx(totals[0], rel=1e-9)


def test_second_identical_request_is_served_from_cache(client):
    params = {"display": "native", "e1_min": 3.0, "e1_max": 17.0}
    first = client.get("/api/projections", params=params).json()
    second = client.get("/api/projections", params=params).json()
    assert second["meta"]["cached"] is True
    assert second["meta"]["total_ms"] < max(first["meta"]["total_ms"], 1.0) + 50


def test_projections_never_return_raw_hits(client):
    """The contract the whole architecture exists to keep."""
    text = client.get("/api/projections").text
    body = json.loads(text)
    assert "hits" not in body
    for panel in body["panels"].values():
        assert "points" not in panel and "rows" not in panel


def test_energy_distribution_is_calibrated_by_default(client):
    body = client.get("/api/energy-distribution").json()
    assert body["scale"] == "calibrated"
    assert body["calibration"]["applied"] is True
    assert body["calibration"]["c_a"] > 1.0
    # Slices must partition every selected event.
    assert sum(body["slice_counts"].values()) == body["n_events"]


def test_energy_distribution_can_report_raw_deposits(client):
    body = client.get(
        "/api/energy-distribution", params={"calibrated": False}
    ).json()
    assert body["scale"] == "deposited"
    assert body["benchmarks"] == []
    assert any("not calibrated" in w for w in body["meta"]["warnings"])


def test_custom_slice_edges_are_honoured(client):
    body = client.get(
        "/api/energy-distribution", params={"d_edges": "500,1500"}
    ).json()
    assert len(body["slices"]) == 3
    assert body["slices"][-1]["hi"] is None


@pytest.mark.parametrize("model,primary", [
    ("segmentation", {"accuracy", "wmae"}),
    ("energy", {"sigma_rel_a", "sigma_rel_b"}),
    ("angle", {"sigma_theta_a", "sigma_theta_b"}),
])
@pytest.mark.parametrize("coord_system,frame", [
    ("lab", "absolute"), ("trans", "trans"), ("local", "local"),
])
def test_model_performance_serves_each_networks_cards(client, model, primary, coord_system, frame):
    body = client.get("/api/model-performance",
                      params={"model": model, "coord_system": coord_system}).json()
    assert body["network"] == {"model": model, "frame": frame}
    assert body["model"]["network"] == body["network"]
    assert {c["id"] for c in body["cards"] if c["primary"]} == primary
    for card in body["cards"]:
        assert set(card) >= {"id", "label", "sub", "value", "unit", "primary", "n", "se",
                             "interval", "note"}
        if card["interval"] is not None:
            assert card["interval"]["level"] == 0.95
            assert card["interval"]["lo"] <= card["value"] <= card["interval"]["hi"]
    assert not body["meta"]["warnings"]


@pytest.mark.parametrize("route", ["/api/model-performance", "/api/energy-distribution"])
@pytest.mark.parametrize("params,field", [
    ({"coord_system": "polar"}, "coord_system"),
    ({"model": "gpt"}, "model"),
])
def test_performance_and_energy_refuse_unknown_networks(client, route, params, field):
    if route == "/api/energy-distribution" and field == "model":
        pytest.skip("the energy panel is always the segmentation reconstruction")
    response = client.get(route, params=params)
    assert response.status_code == 422
    assert response.json().get("field") == field


@pytest.mark.parametrize("coord_system,frame", [
    ("lab", "absolute"), ("trans", "trans"), ("local", "local"),
])
def test_the_energy_panel_names_its_network_and_nothing_else(client, coord_system, frame):
    base = client.get("/api/energy-distribution").json()
    body = client.get("/api/energy-distribution", params={"coord_system": coord_system}).json()
    assert body["meta"]["network"] == {"model": "segmentation", "frame": frame}
    assert set(body) == set(base)
    assert set(body["meta"]) == set(base["meta"])


def test_model_performance_reports_both_error_weightings(client):
    body = client.get("/api/model-performance").json()
    assert body["regression"]["mae"] is not None
    assert body["regression"]["mae_energy_weighted"] is not None
    assert body["by_slice"]


def test_unknown_experiment_is_a_clear_404(client):
    response = client.get("/api/projections", params={"table_name": "does_not_exist"})
    assert response.status_code == 404
    assert "does_not_exist" in response.json()["detail"]


def test_invalid_experiment_name_is_rejected(client):
    response = client.get("/api/projections", params={"table_name": "DROP TABLE x"})
    assert response.status_code == 422


def test_inverted_slider_range_is_rejected(client):
    response = client.get("/api/projections", params={"e1_min": 99, "e1_max": 1})
    assert response.status_code == 422
    assert "inverted" in response.json()["detail"]


def test_unknown_display_mode_is_rejected(client):
    response = client.get("/api/projections", params={"display": "hologram"})
    assert response.status_code == 422


def test_upload_rejects_a_bad_table_name(client):
    response = client.post(
        "/api/upload",
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
        data={"table_name": "Bad Name", "mode": "create_new"},
    )
    assert response.status_code == 422


def test_upload_rejects_a_mismatched_schema(client):
    """A wrong-schema file is refused before a job is queued, naming its columns."""
    response = client.post(
        "/api/upload",
        files={"file": ("wrong.csv", b"alpha,beta\n1,2\n", "text/csv")},
        data={"table_name": "wrongschema", "mode": "create_new"},
    )
    assert response.status_code == 400
    problem = response.json()
    assert "does not match the hits_all_models input schema" in problem["detail"]
    assert "Accepted inputs:" in problem["detail"]
    assert problem["found"] == ["alpha", "beta"]
    assert len(problem["expected"]) == 99
    jobs = client.get("/api/upload").json()["jobs"]
    assert not any(j["table_name"] == "wrongschema" for j in jobs)


def test_append_to_a_missing_experiment_is_rejected(client):
    response = client.post(
        "/api/upload",
        files={"file": ("x.csv", b"a\n1\n", "text/csv")},
        data={"table_name": "neverexisted", "mode": "append"},
    )
    assert response.status_code == 400


def test_upload_info_warns_about_large_files(client):
    body = client.get("/api/upload-info").json()
    assert "no resume" in body["warning"]
    from calosrv.db.ddl import HIT_COLUMN_NAMES

    assert len(body["schema"]["columns"]) == len(HIT_COLUMN_NAMES) == 99
    assert body["schema"]["n_columns"] == 99
    assert body["schema"]["name"] == "hits_all_models"


def test_upload_info_lists_every_accepted_schema(client):
    body = client.get("/api/upload-info").json()
    assert [s["name"] for s in body["schemas"]] == [
        "hits_all_models", "standalone_hits", "standalone_events"]
    assert [s["n_columns"] for s in body["schemas"]] == [99, 21, 59]
    assert [s["kind"] for s in body["schemas"]] == [
        "two_shower_hits", "single_shower_hits", "single_shower_events"]
    assert body["accepted"].startswith("Accepted inputs: hits_all_models (99 columns)")


def test_admin_rebuild_runs_as_a_job_and_keeps_the_experiment_ready(client):
    name = "experiment_baseline"
    assert client.post("/api/admin/experiments/no_such_experiment/rebuild").status_code == 404
    response = client.post(f"/api/admin/experiments/{name}/rebuild")
    assert response.status_code == 202
    job = response.json()["job"]
    assert job["mode"] == "rebuild" and job["source_name"] == "(archive)"
    assert client.post(f"/api/admin/experiments/{name}/rebuild").status_code == 409
    for _ in range(200):
        job = client.get(f"/api/upload/{job['job_id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["kind"] == "two_shower_hits"
    assert job["result"]["schema"]["name"] == "hits_all_models"
    listed = {e["table_name"]: e for e in client.get("/api/experiments").json()["experiments"]}
    assert listed[name]["status"] == "ready"
    assert listed[name]["capabilities"]["derived"]["status"] == "current"


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Calorimeter Shower Reconstruction" in response.text


def test_models_page_is_served(client):
    """The Models page shares the shell and loads echarts-gl; the Physics page never does."""
    response = client.get("/models")
    assert response.status_code == 200
    assert "Calorimeter Shower Reconstruction" in response.text
    html = response.text
    scripts = re.findall(r'<script[^>]*src="([^"?]+)', html)
    assert scripts == ["/static/js/vendor/echarts.min.js", "/static/js/vendor/echarts-gl.min.js",
                       "/static/js/models_main.js"]
    assert '<script type="module" src="/static/js/models_main.js' in html
    assert "echarts-gl" not in client.get("/").text


def test_methodology_page_is_served(client):
    """The Methodology page shares the shell, loads its own entry point and no chart library."""
    response = client.get("/methodology")
    assert response.status_code == 200
    html = response.text
    assert "Calorimeter Shower Reconstruction" in html
    scripts = re.findall(r'<script[^>]*src="([^"?]+)', html)
    assert scripts == ["/static/js/methodology_main.js"]
    assert '<script type="module" src="/static/js/methodology_main.js' in html


def test_depth_overlays_are_complementary(client):
    """Exactly one direction overlay is honest at a time.

    Individual trajectories are exact but unreadable in bulk. The ensemble axis
    converges on the beam position over thousands of events but wanders across
    the detector when asked to average a handful of showers that sit in
    different places. The demonstration table holds two events, so it must get
    the trajectories and not the axis.
    """
    body = client.get("/api/projections").json()
    overlays = body["overlays"]

    assert overlays["trajectories"], "two events is well inside the cap"
    assert overlays["axes"] == {}, "the ensemble axis is meaningless at N=2"

    assert len(overlays["trajectories"]) <= overlays["max_trajectory_events"]
    for path in overlays["trajectories"]:
        assert {"theta", "phi", "x", "y", "z"} <= set(path["a"])

    coherence = overlays["coherence"]
    assert 0.0 <= coherence["r_a"] <= 1.0


def test_payload_stays_under_budget_with_overlays(client):
    response = client.get("/api/projections", params={"display": "native"})
    assert len(response.content) < 100_000


# ------------------------------------------------------- canonical frame --


def test_canonical_frame_is_served_beside_the_lab_frame(client):
    """The API default stays `lab`; `frame=canonical` is a superset envelope."""
    lab = client.get("/api/projections").json()
    assert lab["meta"]["frame"] == "lab"
    assert "frame" not in lab

    response = client.get("/api/projections", params={"frame": "canonical"})
    assert response.status_code == 200
    assert len(response.content) < 100_000
    body = response.json()

    # Every lab key is present, so the interface reads both with one code path.
    assert set(lab) <= set(body)
    assert body["meta"]["frame"] == "canonical"
    frame = body["frame"]
    assert frame["kind"] == "canonical"
    assert frame["anchor"] == "entry_backprojection"
    assert frame["n_events"] == 2
    assert frame["subsample_k"] >= 2, "point-binning combs; k = 1 is never used"
    assert frame["fit"]["provisional"] is True, "two events cannot fix a display range"
    assert frame["rho"]["norm"] == "selection"
    assert frame["rho"]["unit"] == "GeV/mm^2/event"
    assert frame["d_entry"]["mean"] > 0 and frame["d_dataset"]["mean"] > 0
    assert frame["d_entry"]["ci95_half"] > frame["d_entry"]["se"], "the quoted interval is Student-t"
    assert frame["comb"]["note"], "the comb is measured, not asserted"
    assert "energy_lag1_core_row" in frame["comb"], "the comb is measured on energy too, not occupancy alone"
    assert body["meta"]["sample_percent"] == 100.0
    assert frame["rho"]["selection_k"] == frame["subsample_k"]
    assert "canonical" in frame["comb"]["note"].lower() or "comb" in frame["comb"]["note"].lower()
    # Review R-4: meta.stagger was an exact copy of frame.comb in the co-registered frames.
    assert "stagger" not in body["meta"]

    for panel in body["panels"].values():
        assert panel["encoding"] == "u8-b64"
        assert panel["scale"]["unit"] == "a.u."
        assert panel["scale"]["vmin"] == -3.0
        assert "clipped_high" not in panel["scale"]
        assert panel["axes"]["col"]["symbol"] in ("x′", "z′")
        assert panel["topk_unit"] == "GeV/mm^2/event"
        # Sub-floor bins have their own, transparent code; the ramp starts above it.
        assert (panel["empty_code"], panel["below_code"], panel["min_code"]) == (0, 1, 2)
        assert panel["scale"]["floor"] == "transparent"
        assert panel["below_floor_cells"] == panel["scale"]["clipped_low"]
        assert panel["kernel"] == "none", "the API default display is native"

    # Symmetric windows about the origin.
    lo, hi = frame["fit"]["xy"]["col"]["range"]
    assert lo == -hi and frame["fit"]["xy"]["col"]["half_width"] == hi
    assert frame["fit"]["rule"] == "symmetric"
    assert "subsample_regime" in frame and "smoothing" not in frame
    assert frame["reconstruction"]["display"] == "native"
    assert frame["comb"]["measured_on"] == "raw accumulation grid, before display smoothing"
    assert set(frame["rho"]) >= {"basis", "displayed_peak", "displayed_over_ref", "kernel_attenuation"}

    overlays = body["overlays"]
    assert overlays["trajectories"] == [], "individual trajectories are suppressed in this frame"
    assert overlays["axes"] == {}
    assert set(overlays["ensemble_axes"]["xz"]) == {"a", "b"}
    assert set(overlays["anchors"]) == {"a", "b"}
    half = frame["d_entry"]["mean"] / 2
    assert overlays["anchors"]["a"]["x"] == pytest.approx(-half)
    assert overlays["anchors"]["b"]["x"] == pytest.approx(+half)
    assert overlays["ensemble_axes"]["xz"]["a"]["axis"][0] == pytest.approx([0.0, -half])
    # Two events: dispersion band with one degree of freedom, labelled weak.
    assert overlays["ensemble_axes"]["xz"]["a"]["band"] is not None
    assert overlays["ensemble_axes"]["xz"]["a"]["dof_note"] == "1 d.o.f."
    assert frame["ensemble"]["a"]["label"].startswith("weak")

    assert "truth_dataset" not in body["centroids"]
    assert set(body["centroids"]) == {"truth_voxel", "pred_voxel", "canonical_mean"}
    assert set(frame["anchor_offsets"]) == set(body["centroids"])


def test_canonical_frame_rejects_unknown_values(client):
    assert client.get("/api/projections", params={"frame": "hologram"}).status_code == 422
    assert client.get(
        "/api/projections", params={"frame": "canonical", "rho_norm": "peak"}
    ).status_code == 422


def test_canonical_density_reference_is_selectable(client):
    own = client.get("/api/projections", params={"frame": "canonical"}).json()
    dataset = client.get(
        "/api/projections", params={"frame": "canonical", "rho_norm": "dataset"}
    ).json()
    assert own["panels"]["xy"]["scale"]["norm"] == "selection"
    assert dataset["panels"]["xy"]["scale"]["norm"] == "dataset"
    assert dataset["panels"]["xy"]["scale"]["locked"] is True
    # The demo selection is the whole dataset, so both references coincide.
    assert dataset["frame"]["rho"]["ref"]["xy"] == pytest.approx(own["frame"]["rho"]["ref"]["xy"])


def test_canonical_and_lab_bundles_are_cached_separately(client):
    params = {"frame": "canonical", "e1_min": 2.0, "e1_max": 18.0}
    first = client.get("/api/projections", params=params).json()
    second = client.get("/api/projections", params=params).json()
    assert second["meta"]["cached"] is True
    lab = client.get("/api/projections", params={**params, "frame": "lab"}).json()
    assert lab["meta"]["frame"] == "lab"
    caches = client.get("/api/experiments").json()["compute"]
    assert caches["canonical_cache"]["entries"] >= 1
    assert caches["canonical_cache"]["name"] == "canonical"
    assert first["panels"]["xy"]["shape"] != lab["panels"]["xy"]["shape"]


def test_canonical_frame_explains_undefined_separation_events(client):
    body = client.get(
        "/api/projections", params={"frame": "canonical", "include_undefined_d": True}
    ).json()
    texts = [n["text"] for n in body["meta"]["notices"]]
    assert any("undefined A-B separation" in t for t in texts)
    assert body["frame"]["n_excluded_no_frame"] == body["frame"]["n_selected"] - body["frame"]["n_events"]


def test_canonical_continuous_mode_reconstructs_the_symmetric_window(client):
    body = client.get(
        "/api/projections",
        params={"frame": "canonical", "display": "continuous", "resolution": 200},
    ).json()
    resolution = body["meta"]["resolution"]
    assert resolution["mode"] == "continuous"
    assert body["panels"]["xy"]["shape"][1] == 200
    assert resolution["pitch_mm"] == 20.0
    # Two events: the Gaussian kernel, named in the plan and on every panel.
    assert resolution["kernel"]["type"] == "gaussian" and resolution["kernel"]["sigma_mm"] == 10.0
    assert any("Gaussian kernel" in w for w in resolution["warnings"])
    native = client.get("/api/projections", params={"frame": "canonical"}).json()
    assert native["meta"]["resolution"]["mode"] == "native"
    assert native["meta"]["resolution"]["kernel"]["type"] == "none"
    # Both modes crop the same symmetric window.
    assert body["panels"]["xy"]["axes"]["col"]["lo"] == pytest.approx(-body["panels"]["xy"]["axes"]["col"]["hi"])
    assert body["frame"]["fit"] == native["frame"]["fit"]
    for payload in body["panels"].values():
        assert payload["kernel"] == "gaussian"
        # The in-window energy after reconstruction and the disclosed outside share agree.
        outside = 1.0 - payload["total"] / payload["total_energy_all_gev"]
        assert payload["energy_fraction_outside_window"] == pytest.approx(outside, abs=1e-8)
        assert payload["energy_outside_window_gev"] == pytest.approx(
            payload["total_energy_all_gev"] - payload["total"], abs=1e-12
        )
    # Native Grid holds exactly the raw crop, so its two outside figures coincide.
    for payload in native["panels"].values():
        assert payload["energy_fraction_outside_window"] == pytest.approx(
            payload["energy_fraction_outside_window_raw"], abs=1e-8
        )


def test_the_comb_verdict_does_not_depend_on_the_display(client):
    """Measured on the raw accumulation grid, before any display smoothing."""
    native = client.get("/api/projections", params={"frame": "canonical", "display": "native"}).json()
    continuous = client.get(
        "/api/projections", params={"frame": "canonical", "display": "continuous", "resolution": 150}
    ).json()
    assert native["frame"]["comb"] == continuous["frame"]["comb"]
    assert "stagger" not in native["meta"] and "stagger" not in continuous["meta"]
    assert "coarser" not in continuous["frame"]["comb"]["note"]


def test_a_display_or_resolution_change_is_served_from_the_canonical_cache(client):
    params = {"frame": "canonical", "e1_min": 1.0, "e1_max": 19.0}
    client.get("/api/projections", params={**params, "display": "native"})
    for extra in (
        {"display": "continuous", "resolution": 150},
        {"display": "continuous", "resolution": 220},
        {"display": "native"},
    ):
        body = client.get("/api/projections", params={**params, **extra}).json()
        assert body["meta"]["cached"] is True, extra
        assert body["meta"]["total_ms"] < 100, extra


def test_the_reconstruction_is_disclosed(client):
    body = client.get(
        "/api/projections", params={"frame": "canonical", "display": "continuous", "resolution": 150}
    ).json()
    block = body["frame"]["reconstruction"]
    assert {
        "display", "kernel", "label", "sigma_mm", "bin_spread_rms_mm", "blur_rms_mm", "subsample_k",
        "gaussian_below_n", "axes", "depth", "conservative", "floor_ratio",
        "energy_fraction_outside", "below_floor", "note",
    } <= set(block)
    assert block["kernel"] == "gaussian" and block["label"] == "Gaussian σ = 10 mm"
    assert block["axes"] == ["x′", "y′"] and block["gaussian_below_n"] == 50
    assert set(block["blur_rms_mm"]) == {"x", "y"}
    for name, panel in body["panels"].items():
        assert block["energy_fraction_outside"][name] == panel["energy_fraction_outside_window"]
        assert block["below_floor"][name]["cells"] == panel["below_floor_cells"]
    texts = [n["text"] for n in body["meta"]["notices"]]
    assert any("not drawn" in t and "display floor" in t for t in texts)
    rho = body["frame"]["rho"]
    for name in ("xy", "yz", "xz"):
        assert 0 < rho["kernel_attenuation"][name] <= 1.0


def test_the_lab_payload_keys_are_untouched(client):
    """The canonical floor code, kernel and bookkeeping never leak into the lab."""
    body = client.get("/api/projections", params={"display": "continuous", "resolution": 150}).json()
    legacy_panel = {
        "panel", "encoding", "shape", "data", "empty_code", "min_code", "max_code",
        "scale", "axes", "occupancy", "total", "topk",
    }
    legacy_scale = {
        "scale", "vmin", "vmax", "unit", "mode", "locked", "global_vmax",
        "clipped_low", "clipped_high", "empty_cells",
    }
    for name, panel in body["panels"].items():
        assert set(panel) == legacy_panel, name
        extra = {"shared_with"} if name in ("yz", "xz") else set()
        assert set(panel["scale"]) == legacy_scale | extra, name
        assert panel["min_code"] == 1
    assert set(body["meta"]["resolution"]) == {"mode", "requested", "r_x", "r_y", "r_z", "shapes", "warnings"}
    assert "frame" not in body


def test_the_wire_size_helper_measures_what_the_route_sends(client):
    from calosrv.query import density

    response = client.get(
        "/api/projections", params={"frame": "canonical", "display": "continuous", "resolution": 150}
    )
    assert density.wire_size(response.json()) == len(response.content)


def _centred_axis(marginal, edges, half_width):
    """A synthetic origin-centred crop of ``half_width`` mm, with honest bookkeeping."""
    from calosrv.query import window

    n = edges.size - 1
    pitch = (edges[-1] - edges[0]) / n
    lo_index = int(round((0.5 * (edges[-1] - edges[0]) - half_width) / pitch))
    hi_index = n - lo_index
    total = float(marginal.sum())
    outside = float(marginal[:lo_index].sum() + marginal[hi_index:].sum())
    return window.AxisFit(
        lo_index, hi_index, -half_width, half_width, outside / total if total > 0 else 0.0,
        True, symmetric=True,
    )


def _narrow_entrance_window(real_fit):
    """X′Y′ cropped to ±100 mm while the depth panels keep every transverse row -
    the shape of the N = 3, D ≈ 246 mm production case, whose narrow entrance
    window sets a fine display pitch for two wide depth panels."""
    import dataclasses

    from calosrv.query import window

    def fit(bundle):
        base = real_fit(bundle)
        grid = bundle.grid
        plane = bundle.xy.planes["e"]
        row = _centred_axis(plane.sum(axis=1), grid.y_edges, 100.0)
        col = _centred_axis(plane.sum(axis=0), grid.x_edges, 100.0)
        kept = float(plane[row.lo_index:row.hi_index, col.lo_index:col.hi_index].sum())
        xy = window.PanelFit("xy", row, col, float(plane.sum()), kept)

        def full_rows(name, edges):
            depth = bundle.panel(name).planes["e"]
            rows = _centred_axis(depth.sum(axis=1), edges, 0.5 * float(edges[-1] - edges[0]))
            return window.PanelFit(name, rows, base.panel(name).col, float(depth.sum()), float(depth.sum()))

        return dataclasses.replace(
            base, xy=xy, yz=full_rows("yz", grid.y_edges), xz=full_rows("xz", grid.x_edges)
        )

    return fit


def test_the_whole_response_stays_under_budget_on_a_narrow_entrance_window(client, monkeypatch):
    from calosrv.query import window

    monkeypatch.setattr(window, "fit_window", _narrow_entrance_window(window.fit_window))
    response = client.get(
        "/api/projections", params={"frame": "canonical", "display": "continuous", "resolution": 150}
    )
    assert response.status_code == 200
    assert len(response.content) < 100_000
    body = response.json()
    assert body["frame"]["fit"]["xy"]["col"]["range"] == [-100.0, 100.0]
    assert body["meta"]["resolution"]["r_x"] < 150
    texts = [n["text"] for n in body["meta"]["notices"]]
    assert any(t.startswith("Resolution lowered") for t in texts), "the degrade must be disclosed"


def test_the_whole_response_budget_fires_when_the_panel_guard_does_not(client, monkeypatch):
    """With the panel guard lifted, only the whole-response check can keep the
    contract: it must re-render from the cached bundle and say so."""
    from calosrv.query import density, window

    monkeypatch.setattr(window, "fit_window", _narrow_entrance_window(window.fit_window))
    monkeypatch.setattr(density, "PAYLOAD_LIMIT", 10**9)
    response = client.get(
        "/api/projections", params={"frame": "canonical", "display": "continuous", "resolution": 150}
    )
    assert response.status_code == 200
    assert len(response.content) < 100_000
    texts = [n["text"] for n in response.json()["meta"]["notices"]]
    assert any(t.startswith("The whole response measured") for t in texts)
    assert any(t.startswith("Resolution lowered") for t in texts)


def test_persistent_notices_are_not_duplicated_into_the_banner(client):
    """Explanatory notices belong beside their control, not across the plots.

    The staggered-lattice note used to be delivered twice - once as a warning
    and once in meta - so the banner could never be dismissed for good.
    """
    body = client.get("/api/projections", params={"display": "native"}).json()
    notices = {n["text"] for n in body["meta"]["notices"]}
    warnings = set(body["meta"]["warnings"])
    assert not (notices & warnings)

    # The lab frame keeps meta.stagger; only the co-registered copies were dropped.
    stagger_note = body["meta"]["stagger"].get("note")
    if stagger_note:
        assert stagger_note not in warnings


def test_energy_axis_has_a_clean_interval(client):
    axis = client.get("/api/energy-distribution").json()["axis"]
    assert axis["interval"] > 0
    assert abs(axis["hi"] / axis["interval"] - round(axis["hi"] / axis["interval"])) < 1e-9


def test_energy_series_declare_their_marks_and_estimator(client):
    """Every series states what to draw, what it may scale, and how it was fitted."""
    body = client.get("/api/energy-distribution").json()
    assert body["thresholds"]["moment"] == 2
    assert body["thresholds"]["curve"] == 8
    assert body["thresholds"]["histogram"] == 15

    # The shared grids are hoisted out of the series, not repeated in each.
    assert body["axis"]["curve_x"]
    assert body["axis"]["hist_centres"]

    for series in body["series"]:
        assert series["draw"] in {"histogram", "curve+strip", "strip"}
        assert isinstance(series["drives_scale"], bool)
        assert series["estimator"]
        assert "x" not in series["curve"]
        # Only a full histogram series may set the density axis.
        assert series["drives_scale"] == (series["draw"] == "histogram")
        if series["draw"] != "histogram":
            assert series["histogram"] is None
        if series["markers"] is not None:
            m = series["markers"]
            # The two interval marks are separate payload fields precisely so
            # they cannot be drawn with the same mark by accident.
            assert m["ci95_lo"] <= m["mu"] <= m["ci95_hi"]
            assert m["dispersion_lo"] <= m["mu"] <= m["dispersion_hi"]


def test_energy_benchmarks_are_marked_and_carry_no_curve(client):
    """A stated benchmark must be distinguishable from a measurement.

    The frontend draws these as a rule and a band, never as a density, so the
    200-point Gaussian the payload used to carry was dead weight.
    """
    body = client.get("/api/energy-distribution").json()
    for benchmark in body["benchmarks"]:
        assert benchmark["kind"] == "benchmark"
        assert benchmark["fitted"] is False
        assert benchmark["contributes_to_y_axis"] is False
        assert benchmark["tooltip_prefix"] == "[Reference Benchmark]"
        assert "x" not in benchmark and "y" not in benchmark


def test_energy_payload_stays_within_the_budget(client):
    """Architecture B ships pre-aggregated payloads under 100 KB (CLAUDE.md 1.1).

    Each series used to carry its own copy of the 200-point curve grid and the
    120-point bin centres, identical across all twenty by construction; only the
    two-event demonstration dataset kept that from showing.
    """
    raw = client.get("/api/energy-distribution").content
    assert len(raw) < 100_000


# --------------------------------------------------------- asset integrity --


@pytest.mark.parametrize("page", ["/", "/models", "/methodology"])
def test_asset_urls_are_version_stamped(client, page):
    """Markup must reference the exact assets it was built against.

    The page and its scripts are separate downloads with independent cache
    lifetimes, so a browser can hold a stale script against fresh markup. When
    that happened the cached script still expected elements the markup no longer
    had and threw "Cannot set properties of null" during initialisation, killing
    the interface before any chart was configured. Stamping every asset URL with
    a hash of the static tree makes that pairing impossible.
    """
    import re

    html = client.get(page).text
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert refs, "no static assets referenced"
    # The page links are routes, not assets: never stamped.
    for route in ('href="/"', 'href="/models"', 'href="/methodology"'):
        assert route in html, route

    stamps = set()
    for ref in refs:
        assert "?v=" in ref, f"{ref} is not version stamped"
        stamps.add(ref.split("?v=")[1])
    assert len(stamps) == 1, "all assets must share one build stamp"


def test_asset_stamp_changes_when_a_file_changes(tmp_path):
    """The stamp must be derived from content, not fixed at release."""
    from calosrv.app import asset_fingerprint

    (tmp_path / "a.js").write_text("one")
    first = asset_fingerprint(tmp_path)

    (tmp_path / "a.js").write_text("one but longer")
    assert asset_fingerprint(tmp_path) != first

    (tmp_path / "b.css").write_text("x")
    assert asset_fingerprint(tmp_path) not in (first,)


@pytest.mark.parametrize("page", ["/", "/models", "/methodology"])
def test_index_is_never_cached(client, page):
    """A stale page would reference a stale stamp and defeat the mechanism."""
    response = client.get(page)
    assert "no-cache" in response.headers.get("cache-control", "")


def test_versioned_assets_are_immutable_and_bare_ones_revalidate(client):
    """Stamped URLs are safe to keep forever; unstamped ones must be rechecked.

    Relative ES module imports inside main.js cannot carry a stamp, so they rely
    on revalidation to avoid being served stale.
    """
    stamped = client.get("/static/js/main.js?v=abc123")
    assert "immutable" in stamped.headers["cache-control"]

    bare = client.get("/static/js/main.js")
    assert bare.headers["cache-control"] == "no-cache"


#: Static and dynamic import specifiers of a module (relative, `.js`).
_STATIC_IMPORT = re.compile(r"""\bfrom\s*(['"])(\.{1,2}/[^'"?]+?\.js)\1""")
_DYNAMIC_IMPORT = re.compile(r"""\bimport\s*\(\s*(['"])(\.{1,2}/[^'"?]+?\.js)\1""")

#: The id-writing calls the audit reads (dom.js helpers and getElementById).
_ID_CALLS = (r"getElementById\('([^']+)'\)", r"setText\('([^']+)'", r"setHtml\('([^']+)'",
             r"setVal\('([^']+)'", r"setChecked\('([^']+)'", r"setHidden\('([^']+)'")

#: Ids a page leaves out on purpose. The Methodology page has no Details
#: drawer: shell.js looks the drawer up and treats it as optional (every use
#: is guarded), so the page uses the shell for its outline alone.
_OPTIONAL_IDS = {
    "methodology.html": {"inspector", "inspector-title", "inspector-body", "inspector-close"},
}


def _module_graph(entry):
    """Every module an entry point reaches, through static and dynamic imports.

    A static import must resolve. A dynamic import is guarded at run time - a
    panel module another engineer is still building leaves its card saying
    so - so one that does not exist yet is skipped rather than failed.
    """
    seen = set()

    def walk(path):
        if path in seen:
            return
        seen.add(path)
        source = path.read_text(encoding="utf-8")
        for _, spec in _STATIC_IMPORT.findall(source):
            target = (path.parent / spec).resolve()
            assert target.is_file(), f"{path.name} imports missing {spec}"
            walk(target)
        for _, spec in _DYNAMIC_IMPORT.findall(source):
            target = (path.parent / spec).resolve()
            if target.is_file():
                walk(target)

    walk(entry.resolve())
    return seen


def _referenced_ids(modules):
    referenced = {}
    for path in modules:
        source = path.read_text(encoding="utf-8")
        for pattern in _ID_CALLS:
            for element_id in re.findall(pattern, source):
                referenced.setdefault(element_id, path.name)
    return referenced


@pytest.mark.parametrize(("entry", "page"), [("main.js", "index.html"), ("models_main.js", "models.html"),
                                             ("methodology_main.js", "methodology.html")])
def test_every_id_the_scripts_write_to_exists_in_the_markup(entry, page):
    """Guards against the markup and scripts drifting apart in the repository.

    The runtime helpers make a missing element survivable; this makes it a test
    failure instead, so the mismatch never ships. One audit per entry point:
    the modules main.js reaches write to index.html, those models_main.js
    reaches to models.html, so a Physics-page id in a module the Models page
    imports is caught.
    """
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "calosrv" / "static"
    html = (static / page).read_text(encoding="utf-8")
    present = set(re.findall(r'id="([^"]+)"', html)) | _OPTIONAL_IDS.get(page, set())
    referenced = _referenced_ids(_module_graph(static / "js" / entry))
    missing = sorted(f"{element_id} ({module})" for element_id, module in referenced.items()
                     if element_id not in present)
    assert not missing, f"scripts reached from {entry} reference ids absent from {page}: {missing}"


def test_every_module_is_reached_from_an_entry_point():
    """An orphaned module is dead code that still ships, outside both id audits."""
    from pathlib import Path

    js = Path(__file__).resolve().parent.parent / "calosrv" / "static" / "js"
    reached = (_module_graph(js / "main.js") | _module_graph(js / "models_main.js")
               | _module_graph(js / "methodology_main.js"))
    orphans = sorted(str(path.relative_to(js)) for path in js.rglob("*.js")
                     if "vendor" not in path.parts and path.resolve() not in reached)
    assert not orphans, f"modules no entry point reaches: {orphans}"


def test_each_entry_point_keeps_the_other_pages_modules_out():
    """The Models page never loads the Physics page's DOM-bound modules, nor the reverse.

    The panel classes are shared: ProjectionPanel takes its host element from
    its caller and draws the 3-D views' paired projections on Page 2. What stays
    on Page 1 is what builds or drives Page 1's own markup.
    """
    from pathlib import Path

    js = Path(__file__).resolve().parent.parent / "calosrv" / "static" / "js"
    physics = {p.relative_to(js).as_posix() for p in _module_graph(js / "main.js")}
    models = {p.relative_to(js).as_posix() for p in _module_graph(js / "models_main.js")}
    methodology = {p.relative_to(js).as_posix() for p in _module_graph(js / "methodology_main.js")}
    for module in ("main.js", "event_inspector.js", "controls/admin.js", "controls/upload.js",
                   "physics_section.js", "panels/frame_grid.js"):
        assert module not in models, module
    for module in ("models_main.js", "models_cards.js"):
        assert module not in physics, module
    # The article draws no panel and holds no experiment: it may share the
    # leaves (the palettes, the scale, the page helpers), never a page's own.
    for module in ("main.js", "models_main.js", "physics_section.js", "models_cards.js", "voxel_views.js",
                   "event_inspector.js", "lazy_cards.js", "panels/frame_grid.js", "panels/projection.js",
                   "controls/admin.js", "controls/upload.js", "controls/filter_block.js", "export/menu.js"):
        assert module not in methodology, module
    # Nor does either page carry the article.
    for module in sorted(methodology):
        if module == "methodology_main.js" or module.startswith("methodology/"):
            assert module not in physics and module not in models, module


@pytest.mark.parametrize("entry", ["main.js", "models_main.js", "methodology_main.js"])
def test_module_imports_are_stamped_too(client, entry):
    """The entry point alone is not enough to version a module graph.

    A module reached through `import './state.js'` is requested by the browser
    at a bare URL of its own, so stamping only the entry point leaves the rest
    of the graph on whatever each browser already had. That is what produced

        TypeError: state.isTouched is not a function

    when a fresh main.js imported a state.js cached before that method existed -
    and revalidation headers cannot rescue it, because an entry cached *before*
    those headers existed is governed by the freshness it was stored under.
    """
    import re

    served = client.get(f"/static/js/{entry}").text
    specifiers = re.findall(r"from\s+'(\.\.?/[^']+)'", served)
    assert specifiers, f"{entry} should import sibling modules"
    # The guarded dynamic imports (panels, notes, the 3-D views) are requested
    # at bare URLs of their own too.
    specifiers += re.findall(r"import\('(\.\.?/[^']+)'\)", served)
    for spec in specifiers:
        assert "?v=" in spec, f"unstamped module specifier: {spec}"


def test_nested_module_imports_are_stamped(client):
    import re

    served = client.get("/static/js/panels/projection.js").text
    for spec in re.findall(r"from\s+'(\.\.?/[^']+)'", served):
        assert "?v=" in spec, f"unstamped module specifier: {spec}"


@pytest.mark.parametrize("bundle", ["echarts.min.js", "echarts-gl.min.js"])
def test_vendored_bundle_is_served_untouched(client, bundle):
    """Rewriting a minified third-party bundle risks more than it gains."""
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "calosrv" / "static"
    on_disk = (static / "js" / "vendor" / bundle).read_bytes()
    assert client.get(f"/static/js/vendor/{bundle}").content == on_disk


def test_rewriting_leaves_non_import_strings_alone(tmp_path):
    """Only real specifiers may be touched, not lookalikes in strings."""
    from calosrv.app import _JS_IMPORT

    source = (
        "import { a } from './a.js';\n"
        "const msg = 'see ./notes.js for details';\n"
        "const url = `./runtime.js`;\n"
        "await import('./lazy.js');\n"
    )
    out = _JS_IMPORT.sub(r"\1\2\3?v=XYZ\4", source)

    assert "'./a.js?v=XYZ'" in out
    assert "'./lazy.js?v=XYZ'" in out
    # A path mentioned in prose, or built at runtime, must be left as it is.
    assert "see ./notes.js for details" in out
    assert "`./runtime.js`" in out


# ----------------------------------------- the anchor and the coordinate source --


def test_the_canonical_anchor_is_a_stated_measured_choice(client):
    default = client.get("/api/projections", params={"frame": "canonical"}).json()
    frame = default["frame"]
    assert frame["anchor"] == "entry_backprojection" and frame["anchor_choice"] == "backprojected"
    assert frame["anchor_choices"] == ["backprojected", "p0"]
    residual = frame["anchor_residual"]
    assert residual["n"] == frame["n_events"] and residual["a"]["median"] >= 0.0
    assert any("anchor definitions" in n["text"] or "Anchor:" in n["text"]
               for n in default["meta"]["notices"])
    assert default["meta"]["anchor"] == "backprojected"

    p0 = client.get("/api/projections", params={"frame": "canonical", "anchor": "p0"}).json()
    assert p0["frame"]["anchor"] == "p0_backprojection" and p0["frame"]["anchor_choice"] == "p0"
    assert "entry point P0" in p0["frame"]["anchor_note"]
    assert p0["meta"]["anchor"] == "p0"
    assert p0["frame"]["n_events"] == frame["n_events"]
    assert p0["frame"]["anchor_residual"]["a"]["median"] == pytest.approx(residual["a"]["median"], rel=1e-9)
    assert len(client.get("/api/projections", params={"frame": "canonical", "anchor": "p0"}).content) < 100_000

    bad = client.get("/api/projections", params={"frame": "lab", "anchor": "p0"})
    assert bad.status_code == 422 and bad.json()["field"] == "anchor"
    bad = client.get("/api/projections", params={"frame": "canonical", "anchor": "centroid"})
    assert bad.status_code == 422 and bad.json()["field"] == "anchor"


@pytest.mark.parametrize("coord_system", ["trans", "local"])
def test_the_per_shower_frames_report_their_coordinate_source_and_residual(client, coord_system):
    body = client.get("/api/projections", params={"coord_system": coord_system}).json()
    block = body["frame"]["coordinates"]
    assert block["source"] == "file" and block["tolerance_mm"] == 0.01
    assert block["residual_max_mm"] is not None and block["within_tolerance"] is True
    assert block["ingest_residual_mm"] is not None
    assert block["note"].startswith("Coordinates: the file's own")
    # Review R-4: stated once, in the frame block; the client puts it into the frame dot.
    assert not any(n["text"] == block["note"] for n in body["meta"]["notices"])
    assert "stagger" not in body["meta"] and body["frame"]["comb"]["measured_on"]
    assert body["meta"]["coordinates"] == "file"

    computed = client.get("/api/projections", params={"coord_system": coord_system,
                                                       "coordinates": "computed"}).json()
    block = computed["frame"]["coordinates"]
    assert block["source"] == "computed" and block["within_tolerance"] is True
    assert block["note"].startswith("Coordinates: recomputed inside the scan")
    assert computed["meta"]["coordinates"] == "computed"
    assert computed["frame"]["n_events"] == body["frame"]["n_events"]
    assert len(client.get("/api/projections", params={"coord_system": coord_system,
                                                       "coordinates": "computed"}).content) < 100_000

    bad = client.get("/api/projections", params={"coord_system": "lab", "coordinates": "computed"})
    assert bad.status_code == 422 and bad.json()["field"] == "coordinates"
    bad = client.get("/api/projections", params={"coord_system": coord_system, "coordinates": "guess"})
    assert bad.status_code == 422 and bad.json()["field"] == "coordinates"
