"""S4: the energy panel stays under the payload contract at every low-N rung.

Booted against a synthetic all-models file whose D slices hold 1, 2, 7, 8, 14,
15, 19, 20 and 200 events, so every gate of the panel's ladder - moments,
curve, histogram, core refit, robust width - is on screen in some slice. Every
coordinate system x D-edge preset x E window is requested and measured as
served.
"""

from __future__ import annotations

import itertools

import pytest

from calosrv.db import ddl
from calosrv.query import density

#: Slice edges: the default; the maximum eight slices, one population each;
#: edges that pool populations; a single edge.
D_EDGE_PRESETS = (None, "50,100,150,200,250,300,350", "100,200,300,400", "250")

#: (e1_min, e1_max, e2_min, e2_max); None leaves the bound at the dataset's.
E_WINDOWS = (
    (None, None, None, None),
    (None, 6.0, None, None),
    (12.0, None, None, 8.0),
    (9.0, 10.0, None, None),
)


def test_the_synthetic_file_puts_every_low_n_rung_on_screen(synthetic_client):
    experiments = synthetic_client.get("/api/experiments").json()["experiments"]
    assert [e["status"] for e in experiments] == ["ready"], experiments
    body = synthetic_client.get("/api/energy-distribution",
                                params={"d_edges": D_EDGE_PRESETS[1]}).json()
    assert body["n_events"] == 286
    # One population per slice, the last pooling 20 + 200.
    assert sorted({s["fit"]["n"] for s in body["series"]}) == [1, 2, 7, 8, 14, 15, 19, 220]
    assert {s["draw"] for s in body["series"]} == {"strip", "curve+strip", "histogram"}
    assert {s["fit"]["estimator"] for s in body["series"]} >= {
        "mean_only", "moments_1dof", "moments", "core_refit"}


@pytest.mark.parametrize("coord_system", ddl.COORD_SYSTEMS)
@pytest.mark.parametrize("edges,window", list(itertools.product(D_EDGE_PRESETS, E_WINDOWS)))
def test_every_energy_view_stays_under_the_contract(synthetic_client, coord_system, edges, window):
    params = {"coord_system": coord_system}
    if edges:
        params["d_edges"] = edges
    for key, value in zip(("e1_min", "e1_max", "e2_min", "e2_max"), window):
        if value is not None:
            params[key] = value
    response = synthetic_client.get("/api/energy-distribution", params=params)
    assert response.status_code == 200, response.text
    assert len(response.content) < density.RESPONSE_LIMIT, (params, len(response.content))
    body = response.json()
    assert body["meta"]["network"] == {"model": "segmentation",
                                       "frame": ddl.NETWORK_FRAME[coord_system]}


def test_the_guard_resamples_curves_and_says_so(synthetic_client, monkeypatch):
    base = synthetic_client.get("/api/energy-distribution",
                                params={"d_edges": D_EDGE_PRESETS[1]})
    monkeypatch.setattr(density, "RESPONSE_LIMIT", len(base.content) - 1000)
    response = synthetic_client.get("/api/energy-distribution",
                                    params={"d_edges": D_EDGE_PRESETS[1]})
    body = response.json()
    assert len(response.content) < density.RESPONSE_LIMIT
    assert len(body["axis"]["curve_x"]) < len(base.json()["axis"]["curve_x"])
    assert any("Density curves sampled at" in w for w in body["meta"]["warnings"])
    for series in body["series"]:
        if (series.get("curve") or {}).get("y"):
            assert len(series["curve"]["y"]) == len(body["axis"]["curve_x"])
