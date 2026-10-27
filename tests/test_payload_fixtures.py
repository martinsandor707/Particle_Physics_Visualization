"""Recorded route payloads: one source of truth for the pytest contracts and the Node renderers.

The frontend's option builders are tested under Node against real payloads,
not hand-written shapes (the design critique's fix: backend payloads win and
the frontend adapts). Each entry below is served by a booted fixture,
validated against its contract, and stored under ``tests/fixtures/payloads/``.

The stored files must equal what the backend serves today, up to timing
fields and the byte counts a guard quotes. When a payload changes on purpose,
regenerate them:

    CALOSRV_WRITE_PAYLOAD_FIXTURES=1 .venv/bin/python -m pytest -q tests/test_payload_fixtures.py

and the Node tests read the new shape.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

OUT = Path(__file__).resolve().parent / "fixtures" / "payloads"
WRITE = os.environ.get("CALOSRV_WRITE_PAYLOAD_FIXTURES") == "1"

#: Fields that vary from run to run.
TIMING = {"query_ms", "total_ms", "elapsed_ms", "cached", "cache", "created_at", "updated_at"}
_BYTES = re.compile(r"\d[\d,]* bytes")

HITS = {"table_name": SINGLE_HITS_TABLE}
EVENTS = {"table_name": SINGLE_EVENTS_TABLE}
BASE = {"table_name": BASELINE_TABLE}

#: name -> (fixture, path, params, contract or None)
PAYLOADS: dict[str, tuple[str, str, dict, str | None]] = {
    # Capabilities of all three kinds.
    "experiments": ("single_client", "/api/experiments", {}, "experiments"),
    # C7 profiles.
    "profiles_single_w": ("single_client", "/api/profiles", {**HITS, "depth": "w"}, "profiles"),
    "profiles_single_native": ("single_client", "/api/profiles", {**HITS, "depth": "native"},
                               "profiles"),
    "profiles_two_w": ("synthetic_client", "/api/profiles", {"depth": "w"}, "profiles"),
    # B1, B2, resolution.
    "response_single_hits": ("single_client", "/api/response", HITS, "response"),
    "response_single_events": ("single_client", "/api/response", EVENTS, "response"),
    "response_two": ("synthetic_client", "/api/response", {}, "response"),
    # B3.
    "b3_single_notebook": ("single_client", "/api/energy-distribution",
                           {**HITS, "slice_by": "momentum"}, "energy_momentum"),
    "b3_single_bins": ("single_client", "/api/energy-distribution",
                       {**HITS, "slice_by": "momentum", "p_slices": "bins"}, "energy_momentum"),
    "b3_events_bins": ("single_client", "/api/energy-distribution",
                       {**EVENTS, "slice_by": "momentum", "p_slices": "bins"}, "energy_momentum"),
    "b3_two_truth": ("synthetic_client", "/api/energy-distribution",
                     {"slice_by": "momentum", "p_slices": "bins", "series": "truth"},
                     "energy_momentum"),
    "energy_d_two": ("synthetic_client", "/api/energy-distribution", {}, None),
    # C4 distributions.
    "distribution_single_u": ("single_client", "/api/distributions", {**HITS, "quantity": "u"},
                              "distributions"),
    "distribution_single_energy": ("single_client", "/api/distributions",
                                   {**HITS, "quantity": "energy"}, "distributions"),
    "distribution_single_theta_hit": ("single_client", "/api/distributions",
                                      {**HITS, "quantity": "theta", "weighting": "hit"},
                                      "distributions"),
    "distribution_single_phi": ("single_client", "/api/distributions",
                                {**HITS, "quantity": "phi"}, "distributions"),
    "distribution_events_p": ("single_client", "/api/distributions", {**EVENTS, "quantity": "p"},
                              "distributions"),
    "distribution_two_p": ("synthetic_client", "/api/distributions", {"quantity": "p"},
                           "distributions"),
    # C8 correlations.
    "correlation_single_lab": ("single_client", "/api/correlations",
                               {**HITS, "coord_system": "lab"}, "correlations"),
    "correlation_single_local": ("single_client", "/api/correlations",
                                 {**HITS, "coord_system": "local"}, "correlations"),
    "correlation_two_lab": ("synthetic_client", "/api/correlations", {"coord_system": "lab"},
                            "correlations"),
    # C1 + C9.
    "statistics_single_lab": ("single_client", "/api/statistics",
                              {**HITS, "coord_system": "lab"}, "statistics"),
    "statistics_single_local": ("single_client", "/api/statistics",
                                {**HITS, "coord_system": "local"}, "statistics"),
    "statistics_two_local": ("synthetic_client", "/api/statistics", {"coord_system": "local"},
                             "statistics"),
    # C11.
    "primaries_single": ("single_client", "/api/primaries", HITS, "primaries"),
    # Page 2, 2-D: network E2 and prediction density (two-shower), the feature explorer.
    "perf_two_energy": ("synthetic_client", "/api/model-performance",
                        {"slice_by": "momentum_bin", "model": "energy"}, "performance_momentum"),
    "perf_two_angle": ("synthetic_client", "/api/model-performance",
                       {"slice_by": "momentum_bin", "model": "angle"}, "performance_momentum"),
    "pred_density_two_energy": ("synthetic_client", "/api/prediction-density",
                                {"model": "energy", "coord_system": "lab"}, "prediction_density"),
    "pred_density_two_angle": ("synthetic_client", "/api/prediction-density",
                               {"model": "angle", "coord_system": "lab"}, "prediction_density"),
    "features_single_catalog": ("single_client", "/api/features", {**HITS, "view": "catalog"},
                                "features"),
    "features_single_describe": ("single_client", "/api/features",
                                 {**HITS, "view": "describe", "classes": "windows"}, "features"),
    "features_single_corr": ("single_client", "/api/features",
                             {**HITS, "view": "corr", "classes": "label", "class_index": "pooled"},
                             "features"),
    "features_single_hist": ("single_client", "/api/features",
                             {**HITS, "view": "hist", "classes": "windows", "feature": "depth"},
                             "features"),
    "features_single_hist_phi": ("single_client", "/api/features",
                                 {**HITS, "view": "hist", "classes": "label",
                                  "feature": "avg_phi_circ"}, "features"),
    "features_single_hist2d": ("single_client", "/api/features",
                               {**HITS, "view": "hist2d", "classes": "label", "feature": "depth"},
                               "features"),
    "features_events_describe": ("single_client", "/api/features",
                                 {**EVENTS, "view": "describe", "classes": "bins"}, "features"),
    "features_two_corr": ("synthetic_client", "/api/features",
                          {"view": "corr", "classes": "windows", "class_index": "pooled",
                           "shower": "a"}, "features"),
    # 3-D views (Page 2): the densest event's cubes and the ensemble cloud.
    "pick_single_densest": ("single_client", "/api/event/pick", {**HITS, "rule": "densest"},
                            None),
    "event_voxels_base_lab": ("single_client", "/api/event",
                              {**BASE, "event_number": 0, "format": "voxels", "frame": "lab"},
                              "event_voxels"),
    "event_voxels_base_local_shapcam": ("single_client", "/api/event",
                                        {**BASE, "event_number": 0, "format": "voxels",
                                         "frame": "local", "shower": "a", "channel": "shapcam"},
                                        "event_voxels"),
    "event_voxels_base_canonical": ("single_client", "/api/event",
                                    {**BASE, "event_number": 0, "format": "voxels",
                                     "frame": "canonical"}, "event_voxels"),
    # Event 3 is the single-shower fixture's densest (pick_single_densest).
    "event_voxels_single_species": ("single_client", "/api/event",
                                    {**HITS, "event_number": 3, "format": "voxels", "frame": "lab",
                                     "channel": "species"}, "event_voxels"),
    "event_voxels_single_local": ("single_client", "/api/event",
                                  {**HITS, "event_number": 3, "format": "voxels",
                                   "frame": "local"}, "event_voxels"),
    "voxels_base_local": ("single_client", "/api/voxels", {**BASE, "frame": "local"}, "voxels"),
    "voxels_base_canonical_shapcam": ("single_client", "/api/voxels",
                                      {**BASE, "frame": "canonical",
                                       "channel": "shapcam_energy"}, "voxels"),
    "voxels_single_local": ("single_client", "/api/voxels", {**HITS, "frame": "local"}, "voxels"),
    "voxels_two_local": ("synthetic_client", "/api/voxels", {"frame": "local"}, "voxels"),
    # The 2 x 2 on one shower, and the Local frame's C9 block.
    "projections_single_lab": ("single_client", "/api/projections", HITS, None),
    "projections_single_local": ("single_client", "/api/projections",
                                 {**HITS, "coord_system": "local"}, None),
    "projections_base_lab": ("single_client", "/api/projections", BASE, None),
}


#: Per route, payload fields that depend on the moment of serving: the ensemble
#: cloud quotes the 2-D panels' comb only when their bundle is cached (the
#: boot-time warmers race the request), and the feature explorer states its own
#: served size, which counts the timing digits. Stored as served, not compared.
VOLATILE: dict[str, tuple[tuple[str, ...], ...]] = {
    "/api/voxels": (("frame", "comb"), ("frame", "comb_source")),
    "/api/features": (("meta", "budget", "bytes"),),
}


def _masked(value):
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items() if k not in TIMING}
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, str):
        return _BYTES.sub("# bytes", value)
    return value


def _rounded(value):
    """Floats to 12 significant figures: DuckDB's parallel float sums differ in the last bit
    from run to run, which no reader of a payload could see."""
    if isinstance(value, float):
        return float(f"{value:.12g}")
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def _comparable(path: str, body: dict) -> dict:
    body = json.loads(json.dumps(body))
    for keys in VOLATILE.get(path, ()):
        node = body
        for key in keys[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(keys[-1], None)
    return _rounded(body)


def _check(client, name: str) -> None:
    _, path, params, contract = PAYLOADS[name]
    reply = client.get(path, params=params)
    assert reply.status_code == 200, reply.text
    body = reply.json()
    if contract is not None:
        contract_check.check(body, contract)
    stored = OUT / f"{name}.json"
    if WRITE:
        OUT.mkdir(parents=True, exist_ok=True)
        stored.write_text(json.dumps(_masked(body), indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        return
    assert stored.is_file(), f"{stored} missing: regenerate (see the module docstring)"
    recorded = _comparable(path, json.loads(stored.read_text(encoding="utf-8")))
    served = _comparable(path, _masked(body))
    assert recorded == served, (
        f"{name} changed at {_differences(recorded, served)[:5]}: regenerate the payload "
        "fixtures (see the module docstring)")


def _differences(a, b, path: str = "") -> list[str]:
    """The paths at which two payloads differ, for a readable failure."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b)) for d in _differences(a.get(k), b.get(k), f"{path}/{k}")]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {str(a)[:80]} != {str(b)[:80]}"]


def _named(fixture: str) -> list[str]:
    return [name for name, entry in PAYLOADS.items() if entry[0] == fixture]


# The booted clients are requested by name, not through getfixturevalue: the
# collection hook in conftest.py runs every booted-server test before the
# ingested-database tests by reading the fixtures a test declares, and a
# booted module that ran late would close the session's shared connection.

@pytest.mark.parametrize("name", _named("single_client"))
def test_single_client_payloads_are_current_and_satisfy_their_contract(single_client, name):
    _check(single_client, name)


@pytest.mark.parametrize("name", _named("synthetic_client"))
def test_synthetic_client_payloads_are_current_and_satisfy_their_contract(synthetic_client, name):
    _check(synthetic_client, name)


def test_every_payload_names_a_booted_client():
    assert {entry[0] for entry in PAYLOADS.values()} == {"single_client", "synthetic_client"}
