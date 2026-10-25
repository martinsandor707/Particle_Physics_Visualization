"""``GET /api/model-performance`` on the demonstration experiment (two events).

The separation-slice output (``slice_by=d``, the default) is pinned against a
golden captured from the route before ``slice_by`` existed, so the momentum-bin
view can be added beside it without moving a byte of what the sidebar cards
already read. Regenerate the golden only when that output is *meant* to change::

    CALOSRV_WRITE_GOLDEN=1 .venv/bin/python -m pytest tests/test_performance_bins_api.py \
        -k golden

The demonstration file holds two events, so every bin here is a low-N bin; the
statistics at populations 1 to 200 are exercised in ``test_performance_bins_
synthetic.py`` and, on bare arrays, in ``test_performance_bins_stats.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "performance_default.json"
WRITE_ENV = "CALOSRV_WRITE_GOLDEN"

#: The requests whose bodies are pinned: the default, and each network's separation
#: breakdown, one with its own frame and slice edges.
PINNED = {
    "default": {},
    "energy": {"model": "energy"},
    "angle": {"model": "angle"},
    "energy_local_edges": {"model": "energy", "coord_system": "local", "d_edges": "500,1500"},
}

#: Wall-clock fields of ``meta``: they differ on every request.
TIMING = ("query_ms", "total_ms")


def _body(client, params: dict) -> dict:
    response = client.get("/api/model-performance", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    for key in TIMING:
        body["meta"].pop(key)
    return body


def _differences(expected, actual, path=""):
    """Where two JSON trees differ, comparing floats exactly."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            found = sorted(actual) if isinstance(actual, dict) else actual
            yield f"{path}: keys {sorted(expected)} != {found}"
            return
        for key in expected:
            yield from _differences(expected[key], actual[key], f"{path}/{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            size = len(actual) if isinstance(actual, list) else actual
            yield f"{path}: length {len(expected)} != {size}"
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            yield from _differences(e, a, f"{path}[{i}]")
    elif expected != actual:
        yield f"{path}: {expected!r} != {actual!r}"


@pytest.fixture(scope="module")
def golden(client):
    if os.environ.get(WRITE_ENV) == "1":
        captured = {name: _body(client, params) for name, params in PINNED.items()}
        GOLDEN.write_text(json.dumps(captured, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    if not GOLDEN.is_file():
        pytest.skip(f"golden not captured; run with {WRITE_ENV}=1")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_default_response_unchanged(client, golden):
    differences = list(_differences(golden["default"], _body(client, {})))
    assert not differences, "the default model-performance body moved:\n" + "\n".join(differences[:20])


@pytest.mark.parametrize("name", [n for n in PINNED if n != "default"])
def test_every_networks_separation_breakdown_unchanged(client, golden, name):
    differences = list(_differences(golden[name], _body(client, PINNED[name])))
    assert not differences, f"{name}: the separation breakdown moved:\n" + "\n".join(differences[:20])


# ------------------------------------------------------------ slice_by --

SEGMENTATION_SENTENCE = (
    "slice_by=momentum_bin applies to the energy and angle networks, whose predictions are "
    "per shower. Segmentation quality is a property of the whole event, whose two showers "
    "carry two momenta, so it has no single momentum bin; use the separation slices "
    "(slice_by=d)."
)


def _momentum(client, **params):
    response = client.get("/api/model-performance", params={"slice_by": "momentum_bin", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_slice_by_d_is_the_default_byte_for_byte(client):
    default = client.get("/api/model-performance", params={"model": "energy"})
    explicit = client.get("/api/model-performance", params={"model": "energy", "slice_by": "d"})
    a, b = default.json(), explicit.json()
    for body in (a, b):
        for key in TIMING:
            body["meta"].pop(key)
    assert a == b
    assert "by_momentum_bin" not in a and "slice_by" not in a["meta"]


def test_segmentation_has_no_momentum_bin_and_is_told_why(client):
    for params in ({"slice_by": "momentum_bin"},
                   {"model": "segmentation", "slice_by": "momentum_bin", "coord_system": "local"}):
        response = client.get("/api/model-performance", params=params)
        assert response.status_code == 422
        problem = response.json()
        assert problem["field"] == "slice_by" and problem["type"] == "/problems/validation-error"
        assert problem["detail"] == SEGMENTATION_SENTENCE
    # The separation slices still serve it.
    assert client.get("/api/model-performance", params={"slice_by": "d"}).status_code == 200


@pytest.mark.parametrize("value", ["foo", "momentum", "D", ""])
def test_an_unknown_breakdown_is_refused_naming_the_parameter(client, value):
    response = client.get("/api/model-performance", params={"model": "energy", "slice_by": value})
    assert response.status_code == 422
    assert response.json()["field"] == "slice_by"
    assert "d, momentum_bin" in response.json()["detail"]


def test_the_separation_breakdown_rides_along_with_the_momentum_bins(client):
    plain = client.get("/api/model-performance",
                       params={"model": "angle", "d_edges": "500,1500"}).json()
    both = _momentum(client, model="angle", d_edges="500,1500")
    for key in ("cards", "by_slice", "slices"):
        assert both[key] == plain[key]


@pytest.mark.parametrize("model", ["energy", "angle"])
def test_two_events_leave_every_point_low_n_and_every_range_provisional(client, model):
    import contract_check

    body = _momentum(client, model=model)
    contract_check.check(body, "performance_momentum")
    block = body["by_momentum_bin"]
    assert block["bins"]["index"] == list(range(2, 18))
    assert block["n_events"] == 2
    assert [s["key"] for s in block["series"]] == [
        "absolute:a", "absolute:b", "trans:a", "trans:b", "local:a", "local:b"]
    for s in block["series"]:
        # Two events, one shower each: two bins hold a single shower and nothing else exists.
        assert sorted(n for n in s["n"] if n) == [1, 1]
        assert not any(s["drives_scale"])
        # A value is reported at N = 1; no whisker is, because none can be estimated.
        for q in ("rmse", "mae", "bias", "median_rel"):
            assert [v for v in s[q] if v is not None] and all(
                lo is None and hi is None for lo, hi in zip(s[f"{q}_lo"], s[f"{q}_hi"]))
        assert all(m is None for m in s["median_rel_method"])
    assert all(spec["provisional"] and spec["overflow"] == [] for spec in block["y_max"].values())
    assert body["meta"]["warnings"] == []


def test_the_bins_are_the_producers_and_each_shower_sits_in_its_own(client):
    block = _momentum(client, model="energy")["by_momentum_bin"]
    by = {s["key"]: s["n"] for s in block["series"]}
    index = block["bins"]["index"]
    # Event 1: e1 2.71 GeV (bin 2) and e2 12.5 GeV (bin 12); event 2: 17.9 (bin 17) and 6.39 (bin 6).
    assert [index[i] for i, n in enumerate(by["absolute:a"]) if n] == [2, 17]
    assert [index[i] for i, n in enumerate(by["absolute:b"]) if n] == [6, 12]


def test_no_sentence_of_the_momentum_view_signs_a_number_with_a_hyphen(client):
    from calosrv.text import signed_hyphens

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for key, value in node.items():
                if key not in ("table_name",):
                    yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    for model in ("energy", "angle"):
        for text in strings(_momentum(client, model=model)):
            assert not signed_hyphens(text), text
