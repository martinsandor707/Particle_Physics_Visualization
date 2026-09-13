"""End-to-end HTTP behaviour, including the automatic baseline seeding."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from calosrv.app import BASELINE_TABLE, create_app
from calosrv.config import load_settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A server booted against an empty database, so seeding is exercised."""
    import os

    from calosrv.db.connection import reset_database
    from calosrv.ingest.jobs import reset_job_store
    from calosrv.query.cache import reset_cache
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    seed = repo_root / "hits_with_gradcam_dummy.csv"
    if not seed.is_file():
        pytest.skip("Demonstration CSV not present")

    reset_database()
    reset_job_store()
    reset_cache()

    data_dir = tmp_path_factory.mktemp("api-data")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_CSV"] = str(seed)

    with TestClient(create_app(load_settings())) as test_client:
        # Seeding runs on a background worker; wait for it to report ready.
        for _ in range(120):
            payload = test_client.get("/api/experiments").json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
            time.sleep(0.25)
        yield test_client

    reset_database()
    reset_job_store()
    reset_cache()


def test_baseline_is_seeded_from_the_whole_demonstration_csv(client):
    """All 1000 rows, through the real pipeline, with no synthetic records."""
    payload = client.get("/api/experiments").json()
    baseline = next(
        e for e in payload["experiments"] if e["table_name"] == BASELINE_TABLE
    )
    assert baseline["status"] == "ready"
    assert baseline["n_hits"] == 1000
    assert baseline["n_events"] == 2
    assert "hits_with_gradcam_dummy.csv" in baseline["source_files"]


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


def test_model_performance_flags_the_missing_angle_column(client):
    """Absent model outputs must be reported, never fabricated."""
    body = client.get("/api/model-performance", params={"model": "angle"}).json()
    assert body["model"]["title"] == "Incident Angle Estimation Model"
    assert any("No predicted-angle column" in w for w in body["meta"]["warnings"])


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
    """A wrong-schema file must fail during ingest, not corrupt a table."""
    response = client.post(
        "/api/upload",
        files={"file": ("wrong.csv", b"alpha,beta\n1,2\n", "text/csv")},
        data={"table_name": "wrongschema", "mode": "create_new"},
    )
    assert response.status_code == 202
    job_id = response.json()["job"]["job_id"]

    for _ in range(80):
        job = client.get(f"/api/upload/{job_id}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "failed"
    assert "29-column" in (job["error"] or "")


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
    assert len(body["schema"]["columns"]) == 29


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Calorimeter Shower Reconstruction" in response.text


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


def test_persistent_notices_are_not_duplicated_into_the_banner(client):
    """Explanatory notices belong beside their control, not across the plots.

    The staggered-lattice note used to be delivered twice - once as a warning
    and once in meta - so the banner could never be dismissed for good.
    """
    body = client.get("/api/projections", params={"display": "native"}).json()
    notices = {n["text"] for n in body["meta"]["notices"]}
    warnings = set(body["meta"]["warnings"])
    assert not (notices & warnings)

    stagger_note = body["meta"]["stagger"].get("note")
    if stagger_note:
        assert stagger_note not in warnings


def test_energy_axis_has_a_clean_interval(client):
    axis = client.get("/api/energy-distribution").json()["axis"]
    assert axis["interval"] > 0
    assert abs(axis["hi"] / axis["interval"] - round(axis["hi"] / axis["interval"])) < 1e-9


def test_energy_series_declare_sparseness(client):
    body = client.get("/api/energy-distribution").json()
    assert body["density_threshold"] == 15
    for series in body["series"]:
        assert "sparse" in series and "rug" in series
        if series["sparse"]:
            assert series["histogram"] is None


# --------------------------------------------------------- asset integrity --


def test_asset_urls_are_version_stamped(client):
    """Markup must reference the exact assets it was built against.

    The page and its scripts are separate downloads with independent cache
    lifetimes, so a browser can hold a stale script against fresh markup. When
    that happened the cached script still expected elements the markup no longer
    had and threw "Cannot set properties of null" during initialisation, killing
    the interface before any chart was configured. Stamping every asset URL with
    a hash of the static tree makes that pairing impossible.
    """
    import re

    html = client.get("/").text
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert refs, "no static assets referenced"

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


def test_index_is_never_cached(client):
    """A stale page would reference a stale stamp and defeat the mechanism."""
    response = client.get("/")
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


def test_every_id_the_scripts_write_to_exists_in_the_markup(client):
    """Guards against the markup and scripts drifting apart in the repository.

    The runtime helpers make a missing element survivable; this makes it a test
    failure instead, so the mismatch never ships.
    """
    import re
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "calosrv" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    present = set(re.findall(r'id="([^"]+)"', html))

    referenced = set()
    for path in (static / "js").rglob("*.js"):
        if "vendor" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        referenced |= set(re.findall(r"getElementById\('([^']+)'\)", source))
        referenced |= set(re.findall(r"setText\('([^']+)'", source))
        referenced |= set(re.findall(r"setHtml\('([^']+)'", source))
        referenced |= set(re.findall(r"setVal\('([^']+)'", source))
        referenced |= set(re.findall(r"setChecked\('([^']+)'", source))
        referenced |= set(re.findall(r"setHidden\('([^']+)'", source))

    missing = sorted(referenced - present)
    assert not missing, f"scripts reference ids absent from index.html: {missing}"


def test_module_imports_are_stamped_too(client):
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

    served = client.get("/static/js/main.js").text
    specifiers = re.findall(r"from\s+'(\.\.?/[^']+)'", served)
    assert specifiers, "main.js should import sibling modules"
    for spec in specifiers:
        assert "?v=" in spec, f"unstamped module specifier: {spec}"


def test_nested_module_imports_are_stamped(client):
    import re

    served = client.get("/static/js/panels/projection.js").text
    for spec in re.findall(r"from\s+'(\.\.?/[^']+)'", served):
        assert "?v=" in spec, f"unstamped module specifier: {spec}"


def test_vendored_bundle_is_served_untouched(client):
    """Rewriting a minified third-party bundle risks more than it gains."""
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "calosrv" / "static"
    on_disk = (static / "js" / "vendor" / "echarts.min.js").read_bytes()
    assert client.get("/static/js/vendor/echarts.min.js").content == on_disk


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
