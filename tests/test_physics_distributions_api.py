"""``GET /api/distributions`` on a booted server holding all three kinds.

The contract and the 100 KB budget for every quantity on every kind, twenty
populated momentum bins included; the refusals, each naming its parameter; the
series as the own momentum bins with the low-N populations of the synthetic
single-shower file; the payload guard's disclosed, count-conserving merges;
the sampled preview; and U+2212 in every sentence.
"""

from __future__ import annotations

import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE
from synthetic_single_shower import LOW_N_BINS, LOW_N_COUNTS

from calosrv.query import density, sampling
from calosrv.text import signed_hyphens

#: A single-shower experiment with every one of the twenty 1 GeV bins populated.
WIDE_TABLE = "single_wide"

HIT_QUANTITIES = ("u", "v", "w", "energy")
SHOWER_QUANTITIES = ("theta", "phi", "p")


@pytest.fixture(scope="module")
def wide(single_client, tmp_path_factory):
    """Three showers in each of the bins 0-19, ingested into this module's server."""
    import synthetic_single_shower

    from calosrv.ingest import pipeline

    path = tmp_path_factory.mktemp("c4-wide") / "single_wide.csv"
    synthetic_single_shower.write(path, counts=(3,) * 20, bins=tuple(range(20)))
    database = single_client.app.state.database
    with database.write_lock() as con:
        result = pipeline.run_ingest(con, database.settings, WIDE_TABLE, path)
        assert result.ok, result.warnings
    return WIDE_TABLE


def _get(client, table, quantity, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/distributions?table_name={table}&quantity={quantity}"
                      + (f"&{query}" if query else ""))


def _ok(client, table, quantity, **params) -> dict:
    response = _get(client, table, quantity, **params)
    assert response.status_code == 200, response.text
    body = response.json()
    contract_check.check(body, "distributions")
    assert len(response.content) < density.RESPONSE_LIMIT
    assert density.wire_size(body) == len(response.content)
    return body


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _cases():
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE):
        for quantity in HIT_QUANTITIES:
            yield table, quantity, None
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE):
        for quantity in SHOWER_QUANTITIES:
            for weighting in ("shower", "hit"):
                yield table, quantity, weighting


@pytest.mark.parametrize("table,quantity,weighting", list(_cases()))
def test_every_quantity_meets_the_contract_on_every_kind(single_client, table, quantity,
                                                         weighting):
    params = {"weighting": weighting} if weighting else {}
    body = _ok(single_client, table, quantity, **params)
    assert body["quantity"]["key"] == quantity
    assert body["meta"]["exact"] is True
    assert [s["bin"] for s in body["series"]] == sorted(s["bin"] for s in body["series"])
    for text in _strings(body):
        assert not signed_hyphens(text), text


def test_twenty_populated_momentum_bins_fit_the_budget(single_client, wide):
    sizes = {}
    for quantity in (*HIT_QUANTITIES, *SHOWER_QUANTITIES):
        for weighting in (("shower", "hit") if quantity in SHOWER_QUANTITIES else (None,)):
            params = {"weighting": weighting} if weighting else {}
            response = _get(single_client, wide, quantity, **params)
            assert response.status_code == 200, response.text
            body = response.json()
            contract_check.check(body, "distributions")
            assert [s["bin"] for s in body["series"]] == list(range(20))
            assert body["display"]["coarsened"] == 1
            sizes[quantity, weighting] = len(response.content)
    assert max(sizes.values()) < density.RESPONSE_LIMIT, sizes


def test_hit_quantities_are_refused_without_hits_and_shower_quantities_served(single_client):
    for quantity in HIT_QUANTITIES:
        response = _get(single_client, SINGLE_EVENTS_TABLE, quantity)
        assert response.status_code == 422
        problem = response.json()
        assert problem["field"] == "quantity" and problem["capability"] == "hits"
        assert problem["kind"] == "single_shower_events"
        contract_check.check(problem, "capability_problem")
    body = _ok(single_client, SINGLE_EVENTS_TABLE, "theta")
    assert any("single hit" in note for note in body["notes"])


@pytest.mark.parametrize("table,query,field", [
    (BASELINE_TABLE, "quantity=x", "quantity"),
    (BASELINE_TABLE, "quantity=u&weighting=shower", "weighting"),
    (BASELINE_TABLE, "quantity=theta&weighting=events", "weighting"),
    (BASELINE_TABLE, "quantity=theta&shower=c", "shower"),
    (BASELINE_TABLE, "quantity=theta&clip_low=-1", "clip_low"),
    (BASELINE_TABLE, "quantity=theta&clip_low=50&clip_high=40", "clip_high"),
    (SINGLE_HITS_TABLE, "quantity=u&shower=b", "shower"),
    (SINGLE_HITS_TABLE, "quantity=theta&d_min=10", "d_min"),
])
def test_bad_requests_are_refused_naming_the_parameter(single_client, table, query, field):
    response = single_client.get(f"/api/distributions?table_name={table}&{query}")
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["field"] == field
    assert not signed_hyphens(problem["detail"])


def test_the_series_are_the_own_momentum_bins_with_their_populations(single_client):
    populations = dict(zip(LOW_N_BINS, LOW_N_COUNTS))
    hits = _ok(single_client, SINGLE_HITS_TABLE, "theta")
    # The single-hit event sits alone in bin 4.
    assert {s["bin"]: s["n_showers"] for s in hits["series"]} == {**populations, 4: 1}
    assert [s["label"] for s in hits["series"]][:2] == ["1–2 GeV", "2–3 GeV"]
    # The aggregate omits the single-hit event, and says why its bins are unbalanced.
    events = _ok(single_client, SINGLE_EVENTS_TABLE, "theta")
    assert {s["bin"]: s["n_showers"] for s in events["series"]} == populations


def test_the_single_hit_event_is_one_hit_in_every_hit_quantity(single_client):
    for quantity in HIT_QUANTITIES:
        body = _ok(single_client, SINGLE_HITS_TABLE, quantity)
        (alone,) = [s for s in body["series"] if s["bin"] == 4]
        assert alone["n"] == 1 and alone["n_showers"] == 1


def test_the_hit_weighting_counts_the_same_hits_as_the_hit_quantities(single_client):
    """θ weighted by each shower's hit count (event table) against u's hits (projection)."""
    theta = _ok(single_client, SINGLE_HITS_TABLE, "theta", weighting="hit")
    u = _ok(single_client, SINGLE_HITS_TABLE, "u")
    assert {s["bin"]: s["n"] for s in theta["series"]} == {s["bin"]: s["n"] for s in u["series"]}
    assert theta["quantity"]["weighting"].startswith("hit count")


def test_the_two_shower_series_place_each_shower_in_its_own_bin(single_client):
    body = _ok(single_client, BASELINE_TABLE, "p")
    for s in body["series"]:
        first = body["edges"][s["offset"]]
        assert s["bin"] <= first < s["bin"] + 1
    assert any("incoming_momentum_bin_B" in note for note in body["notes"])
    a = _ok(single_client, BASELINE_TABLE, "u", shower="a")
    b = _ok(single_client, BASELINE_TABLE, "u", shower="b")
    both = _ok(single_client, BASELINE_TABLE, "u")
    assert sum(s["n"] for s in a["series"]) + sum(s["n"] for s in b["series"]) == \
        sum(s["n"] for s in both["series"])


def test_the_guard_merges_whole_bins_and_says_so(single_client, monkeypatch):
    plain = _ok(single_client, SINGLE_HITS_TABLE, "w")
    size = len(_get(single_client, SINGLE_HITS_TABLE, "w").content)
    # Below the unmerged size by more than the timing fields can move it, and
    # above the merged one, which drops half the bins of ten series.
    monkeypatch.setattr(density, "RESPONSE_LIMIT", size - 300)
    merged = _get(single_client, SINGLE_HITS_TABLE, "w").json()
    assert density.wire_size(merged) < size - 300
    assert merged["display"]["coarsened"] == 2
    assert merged["quantity"]["bin_width"] == 2 * plain["quantity"]["bin_width"]
    assert any("coarsened 2 at a time" in w for w in merged["meta"]["warnings"])
    for a, b in zip(plain["series"], merged["series"]):
        assert sum(a["counts"]) + a["below"] + a["above"] == pytest.approx(
            sum(b["counts"]) + b["below"] + b["above"])
    monkeypatch.setattr(density, "RESPONSE_LIMIT", 1000)
    over = _get(single_client, SINGLE_HITS_TABLE, "w").json()
    assert over["display"]["coarsened"] == 4
    assert any("served as it is" in w for w in over["meta"]["warnings"])


def test_the_preview_is_marked_inexact(single_client, monkeypatch):
    exact = _ok(single_client, SINGLE_HITS_TABLE, "energy", preview="true")
    assert exact["meta"]["exact"] is True     # below the sampling threshold: exact anyway
    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    preview = _ok(single_client, SINGLE_HITS_TABLE, "energy", preview="true")
    assert preview["meta"]["exact"] is False
    assert any("sample" in w for w in preview["meta"]["warnings"])
    # θ, φ and p read the event table and never sample.
    theta = _ok(single_client, SINGLE_HITS_TABLE, "theta", preview="true")
    assert theta["meta"]["exact"] is True
