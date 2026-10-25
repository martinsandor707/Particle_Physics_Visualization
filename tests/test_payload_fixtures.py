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


def _masked(value):
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items() if k not in TIMING}
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, str):
        return _BYTES.sub("# bytes", value)
    return value


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
    assert json.loads(stored.read_text(encoding="utf-8")) == _masked(body), (
        f"{name} changed: regenerate the payload fixtures (see the module docstring)")


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
