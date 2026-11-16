"""The particle filter and the event pickers' candidates (``query/particle.py``).

The pool - the selection AND the frame gate AND, when a particle bound is
set, a shower that deposited energy with its incident momentum and polar
angle inside every set bound - is checked against a brute-force pass over
the event table's rows, written here in Python without the module's SQL, on
the synthetic two-shower file (``synthetic_client``), the two-shower
demonstration file (the baseline) and the synthetic single-shower hits
(``single_client``), whose 59-column aggregate is refused before any bound
is read. Then the rules that draw from the pool: the uniform cycle, the
notebook rules inside the pool and, with no bound, as they always were;
previous / next and the matching showers of an event and its neighbours;
the geometry, which the filter never moves; the refusals, the empty pool,
the budget that now measures the event block, and the typography.

**The experiment basis** (``basis=experiment``, physics-subpages brief §3):
the same brute force with every row of the event table in place of the
selection - the pool, the counts, previous / next, the rules and their
sentences, ``in_selection`` true for every event; the whole-experiment spec
(``filters.unbounded``) selecting every row on every kind, NULL momenta and
undefined D included; the refusals of an E1/E2/D bound, the 404 sentences,
the geometry equal under both bases, the budget, and ``basis=selection``
answered byte for byte as a request that names no basis.

``synthetic_client`` tests come first: a booted ``single_client`` resets
the database singleton the other server reads.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re

import numpy as np
import pytest

import contract_check
from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE

from calosrv.db import ddl, naming, registry
from calosrv.db.naming import quote
from calosrv.errors import NotFoundError
from calosrv.query import canonical, density, event_inspector, filters, particle
from calosrv.text import signed_hyphens, typographic

CANDIDATES = "/api/event/candidates"
PICK = "/api/event/pick"
EVENT = "/api/event"
BASE = {"table_name": BASELINE_TABLE}
HITS = {"table_name": SINGLE_HITS_TABLE}
EVENTS = {"table_name": SINGLE_EVENTS_TABLE}

#: The synthetic two-shower file: momenta from 2 to 18 GeV; each event is a clone of one of two
#: templates, (theta_A, theta_B) = (22.30, 26.40) or (16.27, 18.16) degrees, copied verbatim.
TWO_CASES: dict[str, dict] = {
    "off": {},
    "p": {"particle_p_min": 5.0, "particle_p_max": 6.0},
    "theta": {"particle_theta_min": 17.0, "particle_theta_max": 20.0},
    "both": {"particle_p_min": 5.0, "particle_p_max": 9.0, "particle_theta_min": 20.0, "particle_theta_max": 30.0},
    "p_min": {"particle_p_min": 15.0},
    "p_max": {"particle_p_max": 3.0},
    "theta_min": {"particle_theta_min": 25.0},
    "theta_max": {"particle_theta_max": 17.0},
    "empty": {"particle_theta_min": 0.0, "particle_theta_max": 5.0},
}
#: The selections each case is crossed with: the whole file, undefined D included, and an E1 cut.
SELECTIONS: dict[str, dict] = {
    "all": {},
    "undefined_d": {"include_undefined_d": True},
    "e1_cut": {"e1_min": 4.0, "e1_max": 12.0},
}
#: The single-shower file's four polar angles are 16.3, 18.2, 22.3 and 26.4 degrees.
SINGLE_CASES: dict[str, dict] = {
    "off": {},
    "theta": {"particle_theta_min": 20.0, "particle_theta_max": 25.0},
    "p": {"particle_p_min": 5.0, "particle_p_max": 9.0},
    "both": {"particle_p_min": 5.0, "particle_p_max": 9.0, "particle_theta_min": 20.0},
    "theta_max": {"particle_theta_max": 17.0},
    "empty": {"particle_theta_min": 0.0, "particle_theta_max": 5.0},
}
SINGLE_SELECTIONS: dict[str, dict] = {"all": {}, "e1_cut": {"e1_min": 4.0, "e1_max": 12.0}}
#: The baseline's two events: p 2-3 GeV selects event 0 through shower A only.
BASE_CASES: dict[str, dict] = {
    "off": {},
    "p_2_3": {"particle_p_min": 2.0, "particle_p_max": 3.0},
    "p_5_6": {"particle_p_min": 5.0, "particle_p_max": 6.0},
    "theta_min": {"particle_theta_min": 17.0},
}


# ----------------------------------------------------------- brute force --


def _record(client, table: str | None = None):
    with client.app.state.database.read_cursor() as con:
        if table is None:
            table = next(e["table_name"] for e in client.get("/api/experiments").json()["experiments"]
                         if e["status"] == "ready")
        return registry.require_ready(con, table)


def _rows(client, record) -> list[dict]:
    """Every event-table row the pool depends on, in event-number order."""
    two = record.kind == ddl.KIND_TWO_SHOWER
    cols = ["event_number", "e1", "theta_a", "phi_a", "p0ax", "n_hits", "n_cells"]
    if two:
        cols += ["e2", "d", "theta_b", "n_a_rows", "n_b_rows", "n_ab_rows"]
    with client.app.state.database.read_cursor() as con:
        rows = con.execute(f"SELECT {', '.join(cols)} FROM {quote(naming.event_table(record.table_name))} "
                           "ORDER BY event_number").fetchall()
    return [dict(zip(cols, row)) for row in rows]


def _within(value, lo, hi) -> bool:
    if value is None:
        return False
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def _bounds(case: dict) -> tuple:
    rad = lambda v: None if v is None else math.radians(v)  # noqa: E731
    return (case.get("particle_p_min"), case.get("particle_p_max"),
            rad(case.get("particle_theta_min")), rad(case.get("particle_theta_max")))


def _brute(rows: list[dict], record, selection: dict, case: dict, whole: bool = False) -> list[dict]:
    """Per event: in the selection, placeable, its matching showers, in the pool - in plain Python.

    ``whole`` is the experiment basis: every row of the event table is "selected".
    """
    two = record.kind == ddl.KIND_TWO_SHOWER
    spec = filters.build(record, **selection)
    p_min, p_max, t_min, t_max = _bounds(case)
    active = any(v is not None for v in (p_min, p_max, t_min, t_max))
    out = []
    for row in rows:
        selected = _within(row["e1"], spec.e1_min, spec.e1_max)
        if two:
            selected = selected and _within(row["e2"], spec.e2_min, spec.e2_max)
            if spec.include_undefined_d:
                selected = selected and (row["d"] is None or _within(row["d"], spec.d_min, spec.d_max))
            else:
                selected = selected and _within(row["d"], spec.d_min, spec.d_max)
            placeable = row["d"] is not None
            showers = [("a", row["e1"], row["theta_a"], row["n_a_rows"] > 0),
                       ("b", row["e2"], row["theta_b"], row["n_b_rows"] + row["n_ab_rows"] > 0)]
        else:
            placeable = all(row[c] is not None for c in ("theta_a", "phi_a", "p0ax"))
            showers = [("a", row["e1"], row["theta_a"], row["n_hits"] > 0)]
        if whole:
            selected = True
        matched = [key for key, p, theta, present in showers
                   if present and _within(p, p_min, p_max) and _within(theta, t_min, t_max)]
        out.append({"event": int(row["event_number"]), "selected": selected, "placeable": placeable,
                    "matched": matched, "pool": selected and placeable and (bool(matched) or not active),
                    "n_hits": row["n_hits"], "n_cells": row["n_cells"],
                    "theta": {key: theta for key, _, theta, _ in showers}})
    return out


def _expected_counts(brute: list[dict], two: bool) -> dict:
    in_gate = [b for b in brute if b["selected"] and b["placeable"]]
    by = {key: sum(key in b["matched"] for b in in_gate) for key in (("a", "b") if two else ("a",))}
    return {
        "n_selection": sum(b["selected"] for b in brute),
        "n_unplaceable": sum(b["selected"] and not b["placeable"] for b in brute),
        "n_events": sum(b["pool"] for b in brute),
        "n_showers": sum(by.values()),
        "by_shower": by,
        "n_both": sum(len(b["matched"]) == 2 for b in in_gate) if two else None,
        "showers": list(by),
    }


def _expected_member(brute: list[dict], event: int) -> dict:
    pool = [b["event"] for b in brute if b["pool"]]
    row = next(b for b in brute if b["event"] == event)
    prev = max((e for e in pool if e < event), default=None)
    nxt = min((e for e in pool if e > event), default=None)
    matched = {b["event"]: b["matched"] for b in brute}
    return {
        "event_number": event, "in_selection": row["selected"], "in_pool": row["pool"],
        "index": pool.index(event) if row["pool"] else None, "n_events": len(pool),
        "prev": prev, "next": nxt, "matched": row["matched"],
        "prev_matched": None if prev is None else matched[prev],
        "next_matched": None if nxt is None else matched[nxt],
    }


def _samples(brute: list[dict]) -> list[int]:
    """Events to place: both ends, the pool's ends and middle, and one outside the pool."""
    events = [b["event"] for b in brute]
    pool = [b["event"] for b in brute if b["pool"]]
    outside = [b["event"] for b in brute if not b["pool"]]
    picks = {events[0], events[-1], events[len(events) // 2]}
    if pool:
        picks |= {pool[0], pool[-1], pool[len(pool) // 2]}
    if outside:
        picks |= {outside[0], outside[len(outside) // 2]}
    return sorted(picks)


def _ok(client, url: str, **params) -> dict:
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text[:600]
    assert len(response.content) < density.RESPONSE_LIMIT
    return response.json()


def _check_pool(client, record, base: dict, selection: dict, case: dict) -> list[dict]:
    """The route's counts and every sampled event's place against the brute force."""
    brute = _brute(_rows(client, record), record, selection, case)
    two = record.kind == ddl.KIND_TWO_SHOWER
    body = _ok(client, CANDIDATES, **base, **selection, **case)
    contract_check.check(body, "event_candidates")
    counts = {k: v for k, v in body["candidates"].items() if k != "particle"}
    assert counts == _expected_counts(brute, two), (selection, case)
    assert body["candidates"]["particle"]["active"] is bool(case)
    assert body["event"] is None
    for event in _samples(brute):
        placed = _ok(client, CANDIDATES, **base, **selection, **case, event_number=event)
        contract_check.check(placed, "event_candidates")
        assert placed["event"] == _expected_member(brute, event), (selection, case, event)
    with client.app.state.database.read_cursor() as con:
        spec = filters.build(record, **selection)
        spec_particle = _particle(record, case)
        pool = particle.pool_events(con, record, spec, spec_particle)
    assert pool.tolist() == [b["event"] for b in brute if b["pool"]]
    return brute


def _particle(record, case: dict) -> particle.ParticleSpec:
    return particle.build(record, p_min=case.get("particle_p_min"), p_max=case.get("particle_p_max"),
                          theta_min=case.get("particle_theta_min"), theta_max=case.get("particle_theta_max"))


def _strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def _no_hyphen_signs(body: dict) -> None:
    for path, text in _strings(body):
        if path.endswith(("data", ".table_name", ".ix", ".iy", ".iz", ".code", ".flags")):
            continue
        assert not signed_hyphens(text), (path, signed_hyphens(text))


# ===================================================== synthetic two showers ==


@pytest.mark.parametrize("selection", list(SELECTIONS))
@pytest.mark.parametrize("case", list(TWO_CASES))
def test_the_two_shower_pool_is_the_brute_force_one(synthetic_client, case, selection):
    record = _record(synthetic_client)
    brute = _check_pool(synthetic_client, record, {}, SELECTIONS[selection], TWO_CASES[case])
    n_pool = sum(b["pool"] for b in brute)
    n_placeable = sum(b["selected"] and b["placeable"] for b in brute)
    if case == "empty":
        assert n_pool == 0
    elif case == "off":
        assert n_pool == n_placeable
    elif selection == "all":
        # A real narrowing: the pool is non-empty and smaller than the placeable selection.
        assert 0 < n_pool < n_placeable


def test_a_bound_is_inclusive_at_a_stored_momentum(synthetic_client):
    """A bound equal to a stored momentum keeps that shower: both ends are inclusive."""
    record = _record(synthetic_client)
    rows = _rows(synthetic_client, record)
    target = rows[len(rows) // 3]
    case = {"particle_p_min": float(target["e1"]), "particle_p_max": float(target["e1"])}
    brute = _check_pool(synthetic_client, record, {}, {}, case)
    assert "a" in next(b for b in brute if b["event"] == target["event_number"])["matched"]


def test_the_uniform_rule_cycles_through_every_candidate(synthetic_client):
    """N consecutive draws visit every candidate once; the same seed and draw repeat; draw N wraps."""
    record = _record(synthetic_client)
    case = TWO_CASES["both"]
    brute = _brute(_rows(synthetic_client, record), record, {}, case)
    pool = [b["event"] for b in brute if b["pool"]]
    n = len(pool)
    assert n > 2
    drawn = []
    for draw in range(n):
        body = _ok(synthetic_client, PICK, rule="uniform", seed=7, draw=draw, **case)
        contract_check.check(body, "event_candidates", at="pick_uniform")
        assert body["n_events"] == n and body["entry"] == draw + 1 and body["draw"] == draw
        assert body["rule_id"] == "uniform" and body["seed_used"] is True and body["seed"] == 7
        # The documented algorithm: a seeded permutation of the pool in event-number order.
        assert body["event_number"] == pool[int(np.random.default_rng(7).permutation(n)[draw])]
        assert body["matched"] == next(b["matched"] for b in brute if b["event"] == body["event_number"])
        assert body["matched"]
        drawn.append(body["event_number"])
    assert sorted(drawn) == pool and len(set(drawn)) == n
    again = _ok(synthetic_client, PICK, rule="uniform", seed=7, draw=3, **case)
    assert again["event_number"] == drawn[3]
    wrapped = _ok(synthetic_client, PICK, rule="uniform", seed=7, draw=n + 3, **case)
    assert wrapped["event_number"] == drawn[3] and wrapped["entry"] == 4 and wrapped["draw"] == n + 3
    other = [_ok(synthetic_client, PICK, rule="uniform", seed=8, draw=d, **case)["event_number"]
             for d in range(n)]
    assert sorted(other) == pool and other != drawn
    # With no bound the shuffle runs over the whole placeable selection.
    whole = _ok(synthetic_client, PICK, rule="uniform")
    assert whole["n_events"] == sum(b["selected"] and b["placeable"] for b in brute)
    assert whole["particle"]["active"] is False and whole["seed"] == event_inspector.DEFAULT_SEED


def _tilted_fell_back(brute: list[dict]) -> bool:
    """Whether no pool event has more hits than the pool's mean (the tilted rule's fallback)."""
    pool = [b for b in brute if b["pool"]]
    mean = sum(b["n_hits"] for b in pool) / len(pool)
    return not any(b["n_hits"] > mean for b in pool)


def _expected_tilted(brute: list[dict], active: bool,
                     size: int = event_inspector.DEFAULT_POOL_SIZE) -> list[int]:
    pool = [b for b in brute if b["pool"]]
    mean = sum(b["n_hits"] for b in pool) / len(pool)
    dense = [b for b in pool if b["n_hits"] > mean]

    def angle(b):
        keys = b["matched"] if active else list(b["theta"])
        return max(b["theta"][k] for k in keys if b["theta"][k] is not None)

    ranked = sorted(dense, key=lambda b: (-angle(b), b["event"])) if dense else \
        sorted(pool, key=lambda b: (-b["n_hits"], b["event"]))
    return [b["event"] for b in ranked[:size]]


@pytest.mark.parametrize("case", ["off", "p", "theta", "both", "theta_min"])
def test_the_notebook_rules_draw_from_the_pool(synthetic_client, case):
    record = _record(synthetic_client)
    params = TWO_CASES[case]
    brute = _brute(_rows(synthetic_client, record), record, {}, params)
    pool = {b["event"] for b in brute if b["pool"]}
    active = bool(params)
    for seed in (42, 43, 44):
        body = _ok(synthetic_client, PICK, rule="tilted", seed=seed, **params)
        contract_check.check(body, "event_candidates", at="pick_ranked")
        assert body["pool"] == _expected_tilted(brute, active), case
        assert body["event_number"] in pool and set(body["pool"]) <= pool
        assert body["n_events"] == len(pool)
        assert body["matched"] == next(b["matched"] for b in brute if b["event"] == body["event_number"])
        # The sentence says which branch was taken: the notebook's rule or the fallback (S3).
        fell_back = "none has more hits than the mean" in body["rule"]
        assert fell_back is _tilted_fell_back(brute), case
        assert ("those with more hits than the mean" in body["rule"]) is not fell_back, case
        assert body["rule"].endswith("with the service's fallback." if fell_back
                                     else "the reference notebook's selection rule."), case
    densest = _ok(synthetic_client, PICK, rule="densest", **params)
    contract_check.check(densest, "event_candidates", at="pick_ranked")
    ranked = sorted((b for b in brute if b["pool"]), key=lambda b: (-b["n_cells"], b["event"]))
    assert densest["pool"] == [b["event"] for b in ranked[:event_inspector.DEFAULT_POOL_SIZE]]
    assert densest["event_number"] == ranked[0]["event"] and densest["n_cells"] == ranked[0]["n_cells"]
    assert densest["particle"] == _particle(record, params).as_dict()


def test_with_no_bound_a_pick_is_todays_body(synthetic_client):
    """No rule and no bound: today's keys and values. A named rule adds rule_id, seed_used,
    matched and the particle echo, and nothing else moves."""
    bare = _ok(synthetic_client, PICK, seed=7)
    assert set(bare) == {"meta", "event_number", "pool", "pool_size", "mean_hits", "n_events", "seed",
                         "rule", "filter"}
    assert bare["rule"] == (
        f"Among the {bare['n_events']:,} selected events with a defined separation, those with more hits "
        f"than the mean ({bare['mean_hits']:.1f}); of those the {len(bare['pool'])} with the largest "
        "incident polar angle (the larger of the two showers'); one drawn at random with seed 7 - the "
        "reference notebook's selection rule.")
    named = _ok(synthetic_client, PICK, seed=7, rule="tilted")
    for key in ("rule_id", "seed_used", "matched", "particle"):
        named.pop(key)
    for body in (bare, named):
        body["meta"].pop("total_ms")
    assert named == bare
    # A particle bound with no rule names the tilted rule and carries the echo.
    narrowed = _ok(synthetic_client, PICK, seed=7, **TWO_CASES["p"])
    assert narrowed["rule_id"] == "tilted" and narrowed["particle"]["active"] is True


def test_the_pick_sentences_name_the_candidates(synthetic_client):
    params = TWO_CASES["both"]
    interval = "p in 5.00–9.00 GeV and θ in 20.0–30.0° (0.349–0.524 rad)"
    population = (f"selected events with a defined separation holding a shower with {interval} that "
                  "deposited energy")
    tilted = _ok(synthetic_client, PICK, rule="tilted", seed=42, **params)
    # Every candidate here is a clone of one template, so none has more hits than the mean and the
    # sentence names the fallback the code took (S3).
    brute = _brute(_rows(synthetic_client, _record(synthetic_client)), _record(synthetic_client), {}, params)
    assert tilted["n_events"] > 1 and _tilted_fell_back(brute)
    assert tilted["rule"] == (
        f"Among the {tilted['n_events']:,} {population}, none has more hits than the mean "
        f"({tilted['mean_hits']:.1f}), so the {len(tilted['pool'])} with the most hits are taken "
        "instead; one drawn at random with seed 42 - the reference notebook's selection rule, with the "
        "service's fallback.")
    densest = _ok(synthetic_client, PICK, rule="densest", **params)
    assert densest["rule"].startswith(
        f"Among the {densest['n_events']:,} {population}, the one with the most detector cells "
        f"({densest['n_cells']:,}; ties go to the lowest event number)")
    uniform = _ok(synthetic_client, PICK, rule="uniform", seed=5, draw=2, **params)
    n = uniform["n_events"]
    assert uniform["rule"] == (
        f"Drawn uniformly at random from the {n:,} {population}: entry 3 of a seeded shuffle of them in "
        f"event-number order (seed 5, draw 2), so no event repeats until all {n:,} have been drawn.")
    for body in (tilted, densest, uniform):
        _no_hyphen_signs(body)


def test_the_route_walks_the_candidates_and_names_the_matches(synthetic_client):
    """event.prev / event.next walk the pool; event.candidates is the membership block."""
    record = _record(synthetic_client)
    params = TWO_CASES["both"]
    brute = _brute(_rows(synthetic_client, record), record, {}, params)
    pool = [b["event"] for b in brute if b["pool"]]
    outside = next(b["event"] for b in brute if b["selected"] and not b["pool"] and not b["matched"])
    for event in (pool[0], pool[len(pool) // 2], outside):
        expected = _expected_member(brute, event)
        for fmt in ("raster", "voxels"):
            body = _ok(synthetic_client, EVENT, event_number=event, format=fmt, frame="lab", **params)
            if fmt == "voxels":
                contract_check.check(body, "event_voxels")
            block = body["event"]
            assert (block["in_selection"], block["prev"], block["next"]) == (
                expected["in_selection"], expected["prev"], expected["next"])
            contract_check.check(block["candidates"], "event_candidates", at="event_block")
            assert block["candidates"] == {
                "particle": _particle(record, params).as_dict(), "in_pool": expected["in_pool"],
                "index": expected["index"], "n_events": expected["n_events"], "matched": expected["matched"],
                "prev_matched": expected["prev_matched"], "next_matched": expected["next_matched"]}
            warnings = body["meta"]["warnings"]
            if event == outside:
                assert warnings == [
                    f"Event {event} holds no shower matching the particle filter (p in 5.00–9.00 GeV and "
                    "θ in 20.0–30.0° (0.349–0.524 rad)); it is drawn as asked, and the previous / next controls walk the "
                    "candidates."]
            else:
                assert warnings == []


# ------------------------------------------- the experiment basis (synthetic) --

#: The pickers' whole-experiment basis (physics-subpages brief §3).
EXPERIMENT = {"basis": "experiment"}
#: The refusal of an E1/E2/D parameter sent with it (brief §3.1).
NOT_WITH_EXPERIMENT = ("{name} does not apply with basis=experiment: the event pickers draw from the whole "
                       "experiment, narrowed by the particle filter alone.")


def _event_count(client, record) -> int:
    with client.app.state.database.read_cursor() as con:
        return int(con.execute(f"SELECT count(*) FROM {quote(naming.event_table(record.table_name))}")
                   .fetchone()[0])


def _experiment_echo(record) -> dict:
    return {**filters.unbounded(record).as_dict(), "basis": "experiment"}


def _check_experiment_pool(client, record, base: dict, case: dict) -> list[dict]:
    """The experiment basis's counts and every sampled event's place against the whole-table brute force."""
    brute = _brute(_rows(client, record), record, {}, case, whole=True)
    two = record.kind == ddl.KIND_TWO_SHOWER
    body = _ok(client, CANDIDATES, **base, **EXPERIMENT, **case)
    contract_check.check(body, "event_candidates")
    assert list(body["candidates"])[0] == "basis" and body["candidates"]["basis"] == "experiment"
    counts = {k: v for k, v in body["candidates"].items() if k not in ("particle", "basis")}
    assert counts == _expected_counts(brute, two), case
    # n_selection is the experiment's event count: every row of the event table.
    assert counts["n_selection"] == _event_count(client, record) == len(brute)
    assert body["candidates"]["particle"] == _particle(record, case).as_dict()
    assert body["filter"] == _experiment_echo(record)
    assert body["event"] is None
    # The slider bounds never depend on the basis.
    assert body["bounds"] == _ok(client, CANDIDATES, **base, **case)["bounds"]
    for event in _samples(brute):
        placed = _ok(client, CANDIDATES, **base, **EXPERIMENT, **case, event_number=event)
        contract_check.check(placed, "event_candidates")
        assert placed["event"] == _expected_member(brute, event), (case, event)
        assert placed["event"]["in_selection"] is True
    with client.app.state.database.read_cursor() as con:
        pool = particle.pool_events(con, record, filters.unbounded(record), _particle(record, case))
    assert pool.tolist() == [b["event"] for b in brute if b["pool"]]
    return brute


@pytest.mark.parametrize("case", list(TWO_CASES))
def test_the_two_shower_experiment_pool_is_the_brute_force_one(synthetic_client, case):
    record = _record(synthetic_client)
    brute = _check_experiment_pool(synthetic_client, record, {}, TWO_CASES[case])
    n_pool = sum(b["pool"] for b in brute)
    if case == "empty":
        assert n_pool == 0
    elif case == "off":
        assert n_pool == sum(b["placeable"] for b in brute)
    else:
        assert 0 < n_pool < sum(b["placeable"] for b in brute)
    # An E1 cut the selection basis applies never reaches the experiment's pool.
    cut = _brute(_rows(synthetic_client, record), record, SELECTIONS["e1_cut"], TWO_CASES[case])
    assert {b["event"] for b in cut if b["pool"]} <= {b["event"] for b in brute if b["pool"]}
    if case == "off":
        assert sum(b["pool"] for b in cut) < n_pool


def test_the_whole_experiment_spec_selects_every_two_shower_row(synthetic_client):
    record = _record(synthetic_client)
    spec = filters.unbounded(record)
    assert spec.where_sql() == "TRUE" and spec.where_sql("h") == "TRUE" and spec.params() == {}
    with synthetic_client.app.state.database.read_cursor() as con:
        table = quote(naming.event_table(record.table_name))
        n = con.execute(f"SELECT count(*) FROM {table} WHERE {spec.where_sql()}", spec.params()).fetchone()[0]
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    assert n == total > 0


def test_the_uniform_rule_cycles_under_the_experiment_basis(synthetic_client):
    """N consecutive draws visit every candidate of the whole experiment once; draw N wraps."""
    record = _record(synthetic_client)
    case = TWO_CASES["both"]
    brute = _brute(_rows(synthetic_client, record), record, {}, case, whole=True)
    pool = [b["event"] for b in brute if b["pool"]]
    n = len(pool)
    assert n > 2
    drawn = []
    for draw in range(n):
        body = _ok(synthetic_client, PICK, rule="uniform", seed=7, draw=draw, **EXPERIMENT, **case)
        contract_check.check(body, "event_candidates", at="pick_uniform")
        assert body["basis"] == "experiment" and body["filter"] == _experiment_echo(record)
        assert body["n_events"] == n and body["entry"] == draw + 1 and body["draw"] == draw
        assert body["event_number"] == pool[int(np.random.default_rng(7).permutation(n)[draw])]
        assert body["matched"] == next(b["matched"] for b in brute if b["event"] == body["event_number"])
        drawn.append(body["event_number"])
    assert sorted(drawn) == pool and len(set(drawn)) == n
    wrapped = _ok(synthetic_client, PICK, rule="uniform", seed=7, draw=n + 3, **EXPERIMENT, **case)
    assert wrapped["event_number"] == drawn[3] and wrapped["entry"] == 4
    # With no bound the shuffle runs over every placeable event of the experiment. The viewer's first
    # draw is the default seed's draw 0, and its sentence names both.
    first = _ok(synthetic_client, PICK, rule="uniform", **EXPERIMENT)
    placeable = [b["event"] for b in brute if b["placeable"]]
    assert first["n_events"] == len(placeable) and first["particle"]["active"] is False
    assert first["seed"] == event_inspector.DEFAULT_SEED and first["draw"] == 0
    assert first["event_number"] == placeable[int(np.random.default_rng(42).permutation(len(placeable))[0])]
    assert f"(seed {event_inspector.DEFAULT_SEED}, draw 0)" in first["rule"]


@pytest.mark.parametrize("case", ["off", "p", "theta", "both", "theta_min"])
def test_the_notebook_rules_draw_from_the_experiment_pool(synthetic_client, case):
    record = _record(synthetic_client)
    params = TWO_CASES[case]
    brute = _brute(_rows(synthetic_client, record), record, {}, params, whole=True)
    pool = {b["event"] for b in brute if b["pool"]}
    active = bool(params)
    for rule in (None, "tilted"):
        body = _ok(synthetic_client, PICK, seed=43, **EXPERIMENT, **params, **({} if rule is None else {"rule": rule}))
        contract_check.check(body, "event_candidates", at="pick_ranked")
        # Whatever the rule, the experiment basis's body names it, the seed's use, the match and the echo.
        assert body["basis"] == "experiment" and body["rule_id"] == "tilted" and body["seed_used"] is True
        assert body["particle"] == _particle(record, params).as_dict()
        assert body["pool"] == _expected_tilted(brute, active), case
        assert body["event_number"] in pool and body["n_events"] == len(pool)
        assert body["matched"] == next(b["matched"] for b in brute if b["event"] == body["event_number"])
    densest = _ok(synthetic_client, PICK, rule="densest", **EXPERIMENT, **params)
    contract_check.check(densest, "event_candidates", at="pick_ranked")
    ranked = sorted((b for b in brute if b["pool"]), key=lambda b: (-b["n_cells"], b["event"]))
    assert densest["pool"] == [b["event"] for b in ranked[:event_inspector.DEFAULT_POOL_SIZE]]
    assert densest["event_number"] == ranked[0]["event"] and densest["basis"] == "experiment"
    assert densest["filter"] == _experiment_echo(record)


def test_the_experiment_pick_sentences_name_the_experiment(synthetic_client):
    params = TWO_CASES["both"]
    interval = "p in 5.00–9.00 GeV and θ in 20.0–30.0° (0.349–0.524 rad)"
    population = (f"events of the experiment with a defined separation holding a shower with {interval} "
                  "that deposited energy")
    uniform = _ok(synthetic_client, PICK, rule="uniform", seed=5, draw=2, **EXPERIMENT, **params)
    n = uniform["n_events"]
    # The brief's template (§3.4), with this file's counts.
    assert uniform["rule"] == (
        f"Drawn uniformly at random from the {n:,} {population}: entry 3 of a seeded shuffle of them in "
        f"event-number order (seed 5, draw 2), so no event repeats until all {n:,} have been drawn.")
    tilted = _ok(synthetic_client, PICK, rule="tilted", seed=42, **EXPERIMENT, **params)
    assert tilted["rule"] == (
        f"Among the {tilted['n_events']:,} {population}, none has more hits than the mean "
        f"({tilted['mean_hits']:.1f}), so the {len(tilted['pool'])} with the most hits are taken "
        "instead; one drawn at random with seed 42 - the reference notebook's selection rule, with the "
        "service's fallback.")
    densest = _ok(synthetic_client, PICK, rule="densest", **EXPERIMENT, **params)
    assert densest["rule"].startswith(
        f"Among the {densest['n_events']:,} {population}, the one with the most detector cells")
    # Inactive: the population phrase alone.
    bare = _ok(synthetic_client, PICK, seed=7, **EXPERIMENT)
    assert bare["rule"].startswith(
        f"Among the {bare['n_events']:,} events of the experiment with a defined separation, ")
    for body in (uniform, tilted, densest, bare):
        assert "selected" not in body["rule"]
        _no_hyphen_signs(body)


def test_the_route_walks_the_experiment_candidates(synthetic_client):
    """event.prev / event.next walk the whole experiment's pool; in_selection is always true."""
    record = _record(synthetic_client)
    params = TWO_CASES["both"]
    brute = _brute(_rows(synthetic_client, record), record, {}, params, whole=True)
    pool = [b["event"] for b in brute if b["pool"]]
    outside = next(b["event"] for b in brute if not b["pool"] and not b["matched"])
    for event in (pool[0], pool[len(pool) // 2], pool[-1], outside):
        expected = _expected_member(brute, event)
        for fmt in ("raster", "voxels"):
            body = _ok(synthetic_client, EVENT, event_number=event, format=fmt, frame="lab", **EXPERIMENT, **params)
            if fmt == "voxels":
                contract_check.check(body, "event_voxels")
            block = body["event"]
            assert block["in_selection"] is True
            assert (block["prev"], block["next"]) == (expected["prev"], expected["next"])
            contract_check.check(block["candidates"], "event_candidates", at="event_block")
            assert block["candidates"] == {
                "basis": "experiment", "particle": _particle(record, params).as_dict(),
                "in_pool": expected["in_pool"], "index": expected["index"], "n_events": expected["n_events"],
                "matched": expected["matched"], "prev_matched": expected["prev_matched"],
                "next_matched": expected["next_matched"]}
            assert body["filter"] == _experiment_echo(record)
            warnings = body["meta"]["warnings"]
            if event == outside:
                # The outside-pool warning, unchanged.
                assert warnings == [particle.outside_pool_warning(event, _particle(record, params))]
            else:
                assert warnings == []
    # An event an E1 cut leaves out: the selection basis draws it with its warning; the experiment
    # basis, which no cut reaches, holds it and says nothing.
    cut = filters.build(record, **SELECTIONS["e1_cut"])
    left_out = next(b["event"] for b in brute if b["placeable"] and not _within(
        next(r["e1"] for r in _rows(synthetic_client, record) if r["event_number"] == b["event"]),
        cut.e1_min, cut.e1_max))
    for fmt in ("raster", "voxels"):
        under_cut = _ok(synthetic_client, EVENT, event_number=left_out, format=fmt, frame="lab",
                        **SELECTIONS["e1_cut"])
        assert under_cut["event"]["in_selection"] is False and under_cut["meta"]["warnings"]
        whole = _ok(synthetic_client, EVENT, event_number=left_out, format=fmt, frame="lab", **EXPERIMENT)
        assert whole["event"]["in_selection"] is True and whole["meta"]["warnings"] == []
        assert whole["event"]["candidates"]["in_pool"] is True


# ============================================= the baseline and one shower ==


@pytest.mark.parametrize("case", list(BASE_CASES))
@pytest.mark.parametrize("selection", ["all", "undefined_d"])
def test_the_baseline_pool_is_the_brute_force_one(single_client, case, selection):
    record = _record(single_client, BASELINE_TABLE)
    brute = _check_pool(single_client, record, BASE, SELECTIONS[selection], BASE_CASES[case])
    if case == "p_2_3":
        # The demonstration file's event 0 through shower A only.
        assert [(b["event"], b["matched"]) for b in brute if b["pool"]] == [(0, ["a"])]


@pytest.mark.parametrize("case", list(SINGLE_CASES))
@pytest.mark.parametrize("selection", list(SINGLE_SELECTIONS))
def test_the_single_shower_pool_is_the_brute_force_one(single_client, case, selection):
    record = _record(single_client, SINGLE_HITS_TABLE)
    brute = _check_pool(single_client, record, HITS, SINGLE_SELECTIONS[selection], SINGLE_CASES[case])
    body = _ok(single_client, CANDIDATES, **HITS, **SINGLE_SELECTIONS[selection], **SINGLE_CASES[case])
    assert body["candidates"]["n_both"] is None and body["candidates"]["showers"] == ["a"]
    assert set(body["candidates"]["by_shower"]) == {"a"}
    if case == "theta":
        assert 0 < sum(b["pool"] for b in brute) < sum(b["selected"] for b in brute)


def test_an_unplaceable_event_is_counted_and_never_offered(single_client):
    """The frame gate's exclusion, on copies of the event tables with one event made unplaceable.

    Every stored test event is placeable, so the copies are temporary views on
    the read cursor: the baseline with event 1's separation undefined (shower
    A deposited nothing), and the single-shower hits with one polar angle
    removed. ``n_unplaceable`` counts the event once undefined D is admitted;
    it is never in the pool, previous / next step over it, and its showers
    are still named.
    """
    for table, alter, two in (
            (BASELINE_TABLE, "CASE WHEN event_number = 1 THEN NULL ELSE d END AS d, "
                             "CASE WHEN event_number = 1 THEN 0 ELSE n_a_rows END AS n_a_rows", True),
            (SINGLE_HITS_TABLE, "CASE WHEN event_number = {mid} THEN NULL ELSE theta_a END AS theta_a", False)):
        record = _record(single_client, table)
        probe = dataclasses.replace(record, table_name=f"{table}_unplaceable_probe")
        with single_client.app.state.database.read_cursor() as con:
            events = [r[0] for r in con.execute(
                f"SELECT event_number FROM {quote(naming.event_table(table))} ORDER BY 1").fetchall()]
            mid = events[len(events) // 2]
            con.execute(f"CREATE TEMP VIEW {quote(naming.event_table(probe.table_name))} AS "
                        f"SELECT * REPLACE ({alter.format(mid=mid)}) FROM {quote(naming.event_table(table))}")
            target = 1 if two else mid
            selection = {"include_undefined_d": True} if two else {}
            spec = filters.build(probe, **selection)
            for spec_particle in (particle.INACTIVE, particle.build(probe, theta_min=10.0)):
                counts = particle.candidates(con, probe, spec, spec_particle)
                assert counts["n_unplaceable"] == 1 and counts["n_selection"] == len(events)
                assert counts["n_events"] == len(events) - 1
                pool = particle.pool_events(con, probe, spec, spec_particle).tolist()
                assert target not in pool and len(pool) == len(events) - 1
                member = particle.membership(con, probe, spec, spec_particle, target)
                assert member["in_selection"] is True and member["in_pool"] is False and member["index"] is None
                i = events.index(target)
                assert member["prev"] == (events[i - 1] if i > 0 else None)
                assert member["next"] == (events[i + 1] if i + 1 < len(events) else None)
                # Its matching showers are still named: the frame gate keeps it out (the probe's
                # single shower lost its angle, so it matches no angle bound).
                assert member["matched"] == (["b"] if two else [] if spec_particle.active else ["a"])
                for neighbour in events[max(0, i - 1):i] + events[i + 1:i + 2]:
                    # Previous / next step over the unplaceable event.
                    around = particle.membership(con, probe, spec, spec_particle, neighbour)
                    assert target not in (around["prev"], around["next"])
            if two:
                # Undefined D excluded (the default): the event is outside the selection, and no
                # longer counted as unplaceable.
                counts = particle.candidates(con, probe, filters.build(probe), particle.INACTIVE)
                assert counts["n_unplaceable"] == 0 and counts["n_selection"] == len(events) - 1


def test_the_aggregate_is_refused_before_any_bound_is_read(single_client):
    for url in (CANDIDATES, PICK):
        response = single_client.get(url, params={**EVENTS, "particle_p_min": -1})
        assert response.status_code == 422
        problem = response.json()
        contract_check.check(problem, "capability_problem")
        assert problem["field"] == "table_name" and problem["capability"] == "event-inspector"


def test_the_bounds_are_the_datasets_own(single_client):
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE):
        record = _record(single_client, table)
        rows = _rows(single_client, record)
        two = record.kind == ddl.KIND_TWO_SHOWER
        values = []
        for row in rows:
            if two and row["d"] is None:
                continue
            showers = ([(row["e1"], row["theta_a"], row["n_a_rows"] > 0),
                        (row["e2"], row["theta_b"], row["n_b_rows"] + row["n_ab_rows"] > 0)] if two
                       else [(row["e1"], row["theta_a"], row["n_hits"] > 0)])
            values += [(p, t) for p, t, present in showers if present]
        body = _ok(single_client, CANDIDATES, table_name=table, e1_min=4.0, e1_max=5.0)
        # Over every placeable event, never the selection.
        assert body["bounds"]["p_gev"] == pytest.approx([min(p for p, _ in values), max(p for p, _ in values)])
        assert body["bounds"]["theta_deg"] == pytest.approx(
            [math.degrees(min(t for _, t in values)), math.degrees(max(t for _, t in values))])


def test_the_particle_echo_and_interval_text():
    spec = particle.ParticleSpec(p_min=5.0, p_max=6.0, theta_min_deg=10.0, theta_max_deg=15.0)
    assert spec.as_dict() == {"active": True, "p_gev": [5.0, 6.0], "theta_deg": [10.0, 15.0],
                              "theta_rad": [0.17453292519943295, 0.2617993877991494]}
    # The angle's bounds in degrees with radians beside them (brief-fix decision 2, S5).
    assert spec.interval_text() == "p in 5.00–6.00 GeV and θ in 10.0–15.0° (0.175–0.262 rad)"
    cases = [
        (dict(p_min=5.0), "p ≥ 5.00 GeV"), (dict(p_max=6.0), "p ≤ 6.00 GeV"),
        (dict(theta_min_deg=10.0), "θ ≥ 10.0° (0.175 rad)"),
        (dict(theta_max_deg=15.0), "θ ≤ 15.0° (0.262 rad)"),
        (dict(p_min=5.0, theta_max_deg=15.0), "p ≥ 5.00 GeV and θ ≤ 15.0° (0.262 rad)"),
        (dict(p_min=5.004, p_max=5.996, theta_min_deg=10.04, theta_max_deg=14.96),
         "p in 5.00–6.00 GeV and θ in 10.0–15.0° (0.175–0.261 rad)"),
        (dict(theta_min_deg=0.0, theta_max_deg=180.0), "θ in 0.0–180.0° (0.000–3.142 rad)"),
        (dict(theta_min_deg=20.0, theta_max_deg=25.0), "θ in 20.0–25.0° (0.349–0.436 rad)"),
        ({}, ""),
    ]
    for kwargs, text in cases:
        assert particle.ParticleSpec(**kwargs).interval_text() == text, kwargs
    # The radians are math.radians(deg) at 3 decimals, Python's own rounding (the client's pyFixed).
    for deg in (0.05, 7.5, 10.0, 12.34, 15.0, 89.95, 179.9):
        assert particle.ParticleSpec(theta_min_deg=deg).interval_text() == (
            f"θ ≥ {deg:.1f}° ({math.radians(deg):.3f} rad)"), deg
    off = particle.ParticleSpec()
    assert off.active is False and off.params() == {}
    assert off.as_dict() == {"active": False, "p_gev": [None, None], "theta_deg": [None, None],
                             "theta_rad": [None, None]}
    # The angle travels in radians, converted once.
    assert particle.ParticleSpec(theta_max_deg=90.0).params() == {"particle_theta_max": math.pi / 2}


def test_the_event_block_contract_is_one_definition():
    """event_voxels.json carries a local copy of event.candidates (the validator resolves local
    references only); it must stay the definition event_candidates.json holds."""
    voxels = contract_check.load("event_voxels")["$defs"]
    source = contract_check.load("event_candidates")["$defs"]
    assert voxels["candidates"] == source["event_block"]
    assert voxels["particle"] == source["particle"]
    assert "candidates" in voxels["event"]["required"]
    # The recorded uniform pick satisfies its own definition.
    from pathlib import Path

    stored = json.loads((Path(__file__).resolve().parent / "fixtures" / "payloads" / "pick_base_uniform.json")
                        .read_text(encoding="utf-8"))
    stored["meta"].setdefault("query_ms", 0.0)
    stored["meta"].setdefault("total_ms", 0.0)
    stored["meta"].setdefault("cached", False)
    contract_check.check(stored, "event_candidates", at="pick_uniform")


def _placeholders(sql: str) -> set[str]:
    return set(re.findall(r"\$(\w+)", sql))


def test_the_sql_and_its_parameters_are_in_lockstep(single_client):
    """Only the set bounds appear in the SQL and the parameters: DuckDB refuses an unused one."""
    names = ("p_min", "p_max", "theta_min_deg", "theta_max_deg")
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE):
        record = _record(single_client, table)
        spec = filters.build(record)
        for mask in range(1, 16):
            kwargs = {name: 1.0 for i, name in enumerate(names) if mask & (1 << i)}
            spec_particle = particle.ParticleSpec(**kwargs)
            assert _placeholders(spec_particle.pool_sql(record)) == set(spec_particle.params())
            where = particle.pool_where(record, spec, spec_particle)
            assert _placeholders(where) == set(particle.pool_params(spec, spec_particle))
        assert _placeholders(particle.pool_where(record, spec, particle.INACTIVE)) == set(spec.params())


# ------------------------------------------------------------------ geometry --


@pytest.mark.parametrize("fmt", ["raster", "voxels"])
def test_the_filter_never_moves_the_geometry(single_client, fmt):
    """One event and shower with and without a particle filter: the same frames, voxels, window and scale."""
    base = {**BASE, "event_number": 0, "shower": "a", "format": fmt}
    if fmt == "voxels":
        base["frame"] = "lab"
    plain = _ok(single_client, EVENT, **base)
    for case in (BASE_CASES["p_2_3"], BASE_CASES["p_5_6"]):
        narrowed = _ok(single_client, EVENT, **base, **case)
        keys = ("frames", "scale", "grid", "window", "coordinates", "footprint_mm") if fmt == "raster" else \
            ("voxels", "window", "coordinates", "footprint_mm")
        for key in keys:
            assert narrowed[key] == plain[key], key
        # The event block differs only where it places the event among the candidates.
        a, b = dict(plain["event"]), dict(narrowed["event"])
        for key in ("candidates", "prev", "next"):
            a.pop(key), b.pop(key)
        assert a == b
        assert plain["event"]["candidates"]["particle"]["active"] is False
        assert narrowed["event"]["candidates"]["particle"]["active"] is True


def test_the_raster_budget_measures_the_event_block(single_client):
    """The event block, candidates included, is inside the body the guard measures.

    At a limit equal to the measured size of the default body, the guard
    must act (trim the layer planes or coarsen); without the event block
    the same body measures below that limit, so it would not have.
    """
    with single_client.app.state.database.read_cursor() as con:
        record = registry.require_ready(con, BASELINE_TABLE)
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)
        body = event_inspector.inspect(con, record, spec, 0, "a", "file", footprint)
        measured = {k: body[k] for k in ("frames", "scale", "grid", "event")}
        size = density.wire_size(measured)
        without = density.wire_size({k: body[k] for k in ("frames", "scale", "grid")})
        assert without < size < density.RESPONSE_LIMIT
        tight = event_inspector.inspect(con, record, spec, 0, "a", "file", footprint, limit=size)
    trimmed = any((frame.get("layer_planes") or {}).get("trimmed") for frame in tight["frames"].values())
    assert trimmed or tight["grid"]["pitch_mm"] > body["grid"]["pitch_mm"]
    assert tight["event"] == body["event"]


# ------------------------------------------------------------- refusals --


@pytest.mark.parametrize("params, field, detail", [
    ({"particle_p_min": -1}, "particle_p_min",
     "particle_p_min must be a finite momentum of 0 GeV or more; got −1."),
    ({"particle_p_max": "nan"}, "particle_p_max",
     "particle_p_max must be a finite momentum of 0 GeV or more; got nan."),
    ({"particle_p_max": "inf"}, "particle_p_max",
     "particle_p_max must be a finite momentum of 0 GeV or more; got inf."),
    ({"particle_theta_min": 200}, "particle_theta_min",
     "particle_theta_min must be a finite angle from 0° to 180°; got 200."),
    ({"particle_theta_max": -0.5}, "particle_theta_max",
     "particle_theta_max must be a finite angle from 0° to 180°; got −0.5."),
    ({"particle_theta_max": "nan"}, "particle_theta_max",
     "particle_theta_max must be a finite angle from 0° to 180°; got nan."),
    ({"particle_p_min": 6, "particle_p_max": 5}, "particle_p",
     "The particle momentum range is inverted: minimum 6 exceeds maximum 5."),
    ({"particle_theta_min": 15, "particle_theta_max": 10}, "particle_theta",
     "The particle angle range is inverted: minimum 15 exceeds maximum 10."),
], ids=["p-negative", "p-nan", "p-inf", "theta-above", "theta-negative", "theta-nan", "p-inverted",
        "theta-inverted"])
def test_every_bound_is_validated_naming_its_field(single_client, params, field, detail):
    for url, extra in ((CANDIDATES, {}), (PICK, {}), (PICK, {"rule": "uniform"}),
                       (EVENT, {"event_number": 0}), (EVENT, {"event_number": 0, "format": "voxels"})):
        response = single_client.get(url, params={**BASE, **extra, **params})
        assert response.status_code == 422, (url, response.text[:300])
        problem = response.json()
        assert problem["type"] == "/problems/validation-error"
        assert problem["field"] == field and problem["detail"] == detail, (url, problem)
        assert not signed_hyphens(problem["detail"])
    # The edges themselves are accepted.
    for edge in ({"particle_p_min": 0}, {"particle_theta_min": 0, "particle_theta_max": 180}):
        assert single_client.get(CANDIDATES, params={**BASE, **edge}).status_code == 200


def test_the_rule_and_draw_are_validated(single_client):
    bad = single_client.get(PICK, params={**BASE, "rule": "brightest"})
    assert bad.status_code == 422 and bad.json()["field"] == "rule"
    assert "tilted, densest, uniform" in bad.json()["detail"]
    bad = single_client.get(PICK, params={**BASE, "rule": "uniform", "draw": -1})
    assert bad.status_code == 422 and bad.json()["field"] == "draw"


def test_an_empty_pool_is_a_404_with_its_sentence(single_client):
    # The baseline: no shower of 5-6 GeV.
    for rule in (None, "tilted", "densest", "uniform"):
        params = {**BASE, **BASE_CASES["p_5_6"], **({} if rule is None else {"rule": rule})}
        response = single_client.get(PICK, params=params)
        assert response.status_code == 404
        assert response.json()["detail"] == (
            "The selection holds no candidate event: none of its events with a defined separation holds "
            "a shower with p in 5.00–6.00 GeV that deposited energy.")
    # Inactive: today's detail.
    experiments = single_client.get("/api/experiments").json()["experiments"]
    top = next(e for e in experiments if e["table_name"] == BASELINE_TABLE)["bounds"]["e1"][1]
    response = single_client.get(PICK, params={**BASE, "e1_min": top + 5.0, "e1_max": top + 6.0,
                                               "rule": "uniform"})
    assert response.status_code == 404
    assert response.json()["detail"] == "The selection holds no event with a defined separation to pick from."
    # One shower.
    response = single_client.get(PICK, params={**HITS, **SINGLE_CASES["empty"], "rule": "uniform"})
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "The selection holds no candidate event: none of its events with an incident direction and an "
        "entry point has its shower at θ in 0.0–5.0° (0.000–0.087 rad).")
    response = single_client.get(PICK, params={**HITS, "e1_min": 0.0, "e1_max": 0.5})
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "The selection holds no event with an incident direction and an entry point to pick from.")
    # The counts are never a 404: N = 0 is an answer.
    body = _ok(single_client, CANDIDATES, **BASE, **BASE_CASES["p_5_6"], event_number=0)
    assert body["candidates"]["n_events"] == 0 and body["event"]["in_pool"] is False
    assert body["event"]["prev"] is None and body["event"]["next"] is None


def test_a_missing_event_is_a_404_on_the_counts_route(single_client):
    response = single_client.get(CANDIDATES, params={**BASE, "event_number": 10**6})
    assert response.status_code == 404


# ------------------------------------------------------------- sentences --


def test_the_single_shower_sentences(single_client):
    params = {**HITS, **SINGLE_CASES["theta"]}
    interval = "θ in 20.0–25.0° (0.349–0.436 rad)"
    population = f"selected events with an incident direction and an entry point whose shower has {interval}"
    uniform = _ok(single_client, PICK, **params, rule="uniform", draw=1)
    n = uniform["n_events"]
    assert uniform["rule"] == (
        f"Drawn uniformly at random from the {n:,} {population}: entry 2 of a seeded shuffle of them in "
        f"event-number order (seed 42, draw 1), so no event repeats until all {n:,} have been drawn.")
    tilted = _ok(single_client, PICK, **params)
    assert tilted["rule_id"] == "tilted" and tilted["rule"] == (
        f"Among the {tilted['n_events']:,} {population}, those with more hits than the mean "
        f"({tilted['mean_hits']:.1f}); of those the {len(tilted['pool'])} with the largest incident polar "
        "angle of a matching shower; one drawn at random with seed 42 - the reference notebook's "
        "selection rule.")
    assert tilted["matched"] == ["a"] and uniform["matched"] == ["a"]
    # Inactive: today's single-shower sentence, unchanged.
    bare = _ok(single_client, PICK, **HITS, seed=7)
    assert bare["rule"].startswith("Among the 287 selected events with an incident direction and an entry "
                                   "point, those with more hits than the mean")
    assert "matched" not in bare and "particle" not in bare


def test_one_candidate_is_the_only_one(single_client):
    body = _ok(single_client, PICK, **BASE, **BASE_CASES["p_2_3"], rule="uniform", seed=11, draw=5)
    assert body["event_number"] == 0 and body["n_events"] == 1 and body["entry"] == 1
    assert body["rule"] == (
        "The only one of the selected events with a defined separation holding a shower with p in "
        "2.00–3.00 GeV that deposited energy (seed 11, draw 5).")
    assert body["matched"] == ["a"]
    # The notebook rules at N = 1 say there was one event to choose from (S3): never "Among the 1
    # selected events", never a "more hits than the mean" rule that the code could not apply.
    population = ("selected events with a defined separation holding a shower with p in 2.00–3.00 GeV "
                  "that deposited energy")
    for rule in (None, "tilted"):
        tilted = _ok(single_client, PICK, **BASE, **BASE_CASES["p_2_3"], seed=11,
                     **({} if rule is None else {"rule": rule}))
        assert tilted["event_number"] == 0 and tilted["n_events"] == 1 and tilted["pool"] == [0]
        assert tilted["rule_id"] == "tilted" and tilted["seed_used"] is True
        assert tilted["rule"] == (
            f"The only one of the {population}: the reference notebook's selection rule has one event to "
            "choose from (seed 11).")
    densest = _ok(single_client, PICK, **BASE, **BASE_CASES["p_2_3"], rule="densest", seed=11)
    assert densest["event_number"] == 0 and densest["n_events"] == 1 and densest["seed_used"] is False
    assert densest["rule"] == (
        f"The only one of the {population}: the reference notebook's densest event, with one event to "
        "choose from. The choice is deterministic: the seed (11) is echoed and not used.")
    for body in (densest, tilted):
        assert "Among the 1 " not in body["rule"]
        _no_hyphen_signs(body)


def test_the_tilted_fallback_is_said_with_no_bound(single_client):
    """With no bound the fallback is old: all candidates with equal hits take it, and say so (S3)."""
    record = _record(single_client, BASELINE_TABLE)
    probe = dataclasses.replace(record, table_name=f"{BASELINE_TABLE}_equal_hits_probe")
    view = quote(naming.event_table(probe.table_name))
    with single_client.app.state.database.read_cursor() as con:
        # A copy of the baseline in which both events hold the same number of hits.
        con.execute(f"CREATE TEMP VIEW {view} AS SELECT * REPLACE (500 AS n_hits) "
                    f"FROM {quote(naming.event_table(BASELINE_TABLE))}")
        try:
            body = event_inspector.pick(con, probe, filters.build(probe), seed=3)
        finally:
            con.execute(f"DROP VIEW {view}")
    assert body["n_events"] == 2 and body["mean_hits"] == 500.0 and body["pool"] == [0, 1]
    assert body["rule"] == (
        "Among the 2 selected events with a defined separation, none has more hits than the mean "
        "(500.0), so the 2 with the most hits are taken instead; one drawn at random with seed 3 - the "
        "reference notebook's selection rule, with the service's fallback.")


def test_the_pool_size_is_one_constant():
    """S9: pick()'s default, the route's Query default, the Methodology's PICK_SHORTLIST and the
    Most tilted button's title all name event_inspector.DEFAULT_POOL_SIZE."""
    import inspect
    from pathlib import Path

    from calosrv.api import routes_event

    size = event_inspector.DEFAULT_POOL_SIZE
    assert inspect.signature(event_inspector.pick).parameters["pool_size"].default == size
    query = inspect.signature(routes_event.pick_event).parameters["pool_size"].default
    assert query.default == size
    static = Path(routes_event.__file__).resolve().parent.parent / "static" / "js"
    constants = (static / "methodology" / "constants.js").read_text(encoding="utf-8")
    entry = re.search(r"PICK_SHORTLIST: entry\((\d+), '([^']+)'", constants)
    assert entry and int(entry.group(1)) == size
    assert entry.group(2) == "py:calosrv.query.event_inspector:DEFAULT_POOL_SIZE"
    picker = (static / "event_picker.js").read_text(encoding="utf-8")
    title = re.search(r"export const TILTED_TITLE = ([^;]+);", picker, re.S).group(1)
    assert f"the {size} with the largest" in title


def test_a_negative_zero_bound_is_zero(single_client):
    """S11: -0 is a valid bound of 0, echoed and written without a sign."""
    spec = particle.build(None, p_min=-0.0, theta_min=-0.0)
    assert math.copysign(1.0, spec.p_min) == 1.0 and math.copysign(1.0, spec.theta_min_deg) == 1.0
    assert spec.interval_text() == "p ≥ 0.00 GeV and θ ≥ 0.0° (0.000 rad)"
    body = _ok(single_client, PICK, **BASE, particle_p_min="-0", particle_theta_min="-0.0", rule="uniform")
    assert body["particle"]["p_gev"][0] == 0.0 and body["particle"]["theta_deg"][0] == 0.0
    raw = single_client.get(PICK, params={**BASE, "particle_p_min": "-0", "particle_theta_min": "-0.0",
                                          "rule": "uniform"}).text
    assert "-0.0" not in raw and "−0" not in raw
    assert "p ≥ 0.00 GeV and θ ≥ 0.0° (0.000 rad)" in body["rule"]


def test_the_warnings_say_what_previous_and_next_walk(single_client):
    experiments = single_client.get("/api/experiments").json()["experiments"]
    top = next(e for e in experiments if e["table_name"] == BASELINE_TABLE)["bounds"]["e1"][1]
    outside = {"e1_min": top + 5.0, "e1_max": top + 6.0}
    for fmt in ("raster", "voxels"):
        extra = {"format": fmt, **({"frame": "lab"} if fmt == "voxels" else {})}
        plain = _ok(single_client, EVENT, **BASE, **extra, event_number=0, **outside)
        assert plain["meta"]["warnings"] == [
            "Event 0 lies outside the current selection; it is drawn as asked, and the previous / next "
            "controls walk the selection."]
        narrowed = _ok(single_client, EVENT, **BASE, **extra, event_number=0, **outside, **BASE_CASES["p_2_3"])
        assert narrowed["meta"]["warnings"] == [
            "Event 0 lies outside the current selection; it is drawn as asked, and the previous / next "
            "controls walk the candidates."]
        # Inside the selection, outside the candidates: event 1 has no 2-3 GeV shower.
        missed = _ok(single_client, EVENT, **BASE, **extra, event_number=1, **BASE_CASES["p_2_3"])
        assert missed["meta"]["warnings"] == [
            "Event 1 holds no shower matching the particle filter (p in 2.00–3.00 GeV); it is drawn as asked, "
            "and the previous / next controls walk the candidates."]
        assert missed["event"]["candidates"]["in_pool"] is False and missed["event"]["candidates"]["matched"] == []
        assert missed["event"]["prev"] == 0 and missed["event"]["candidates"]["prev_matched"] == ["a"]
        # In the candidates: no warning.
        kept = _ok(single_client, EVENT, **BASE, **extra, event_number=0, **BASE_CASES["p_2_3"])
        assert kept["meta"]["warnings"] == [] and kept["event"]["candidates"]["index"] == 0
        for body in (plain, narrowed, missed, kept):
            _no_hyphen_signs(body)


def test_no_candidates_body_signs_a_number_with_a_hyphen(single_client):
    for table, cases in ((BASELINE_TABLE, BASE_CASES), (SINGLE_HITS_TABLE, SINGLE_CASES)):
        for case in cases.values():
            body = _ok(single_client, CANDIDATES, table_name=table, event_number=0 if table == BASELINE_TABLE
                       else 3, **case)
            _no_hyphen_signs(body)
            assert '"hits"' not in json.dumps(body) and '"points"' not in json.dumps(body)


# ================================== the experiment basis: baseline and one shower ==


@pytest.mark.parametrize("case", list(BASE_CASES))
def test_the_baseline_experiment_pool_is_the_brute_force_one(single_client, case):
    record = _record(single_client, BASELINE_TABLE)
    brute = _check_experiment_pool(single_client, record, BASE, BASE_CASES[case])
    if case == "p_2_3":
        assert [(b["event"], b["matched"]) for b in brute if b["pool"]] == [(0, ["a"])]
    if case == "p_5_6":
        assert not any(b["pool"] for b in brute)


@pytest.mark.parametrize("case", list(SINGLE_CASES))
def test_the_single_shower_experiment_pool_is_the_brute_force_one(single_client, case):
    record = _record(single_client, SINGLE_HITS_TABLE)
    brute = _check_experiment_pool(single_client, record, HITS, SINGLE_CASES[case])
    body = _ok(single_client, CANDIDATES, **HITS, **EXPERIMENT, **SINGLE_CASES[case])
    assert body["candidates"]["n_both"] is None and body["candidates"]["showers"] == ["a"]
    # One shower has no separation: the whole experiment's echo says so.
    assert body["filter"]["include_undefined_d"] is False and body["filter"]["basis"] == "experiment"
    if case == "theta":
        assert 0 < sum(b["pool"] for b in brute) < len(brute)
    # The single shower's p window of the ensemble views never reaches the experiment's pool.
    cut = _brute(_rows(single_client, record), record, SINGLE_SELECTIONS["e1_cut"], SINGLE_CASES[case])
    assert {b["event"] for b in cut if b["pool"]} <= {b["event"] for b in brute if b["pool"]}


@pytest.mark.parametrize("table", [BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE])
def test_the_whole_experiment_spec_selects_every_row(single_client, table):
    """Brief §3.2: count under filters.unbounded = count(*), NULL momenta and undefined D included.

    On every kind's event table (the aggregate's too), then on a copy in which
    events lost a momentum or their separation: the whole experiment keeps them,
    where the full-range selection of ``filters.build`` drops them.
    """
    record = _record(single_client, table)
    spec = filters.unbounded(record)
    assert spec.whole_experiment is True and spec.where_sql() == "TRUE" and spec.params() == {}
    assert spec.include_undefined_d is (record.kind == ddl.KIND_TWO_SHOWER)
    two = record.kind == ddl.KIND_TWO_SHOWER
    probe = dataclasses.replace(record, table_name=f"{table}_null_probe")
    view = quote(naming.event_table(probe.table_name))
    source = quote(naming.event_table(table))
    with single_client.app.state.database.read_cursor() as con:
        def count(name: str, where: str = "TRUE", params=None) -> int:
            return int(con.execute(f"SELECT count(*) FROM {name} WHERE {where}", params or {}).fetchone()[0])

        assert count(source, spec.where_sql(), spec.params()) == count(source) > 0
        events = [r[0] for r in con.execute(f"SELECT event_number FROM {source} ORDER BY 1").fetchall()]
        first, last = events[0], events[-1]
        nulls = f"CASE WHEN event_number = {first} THEN NULL ELSE e1 END AS e1"
        if two:
            nulls += (f", CASE WHEN event_number = {last} THEN NULL ELSE e2 END AS e2"
                      f", CASE WHEN event_number = {last} THEN NULL ELSE d END AS d")
        con.execute(f"CREATE TEMP VIEW {view} AS SELECT * REPLACE ({nulls}) FROM {source}")
        try:
            whole = filters.unbounded(probe)
            assert count(view, whole.where_sql(), whole.params()) == count(view) == len(events)
            full_range = filters.build(probe)
            dropped = count(view) - count(view, full_range.where_sql(), full_range.params())
            assert dropped == (2 if two and first != last else 1)
        finally:
            con.execute(f"DROP VIEW {view}")


def test_the_selection_specs_are_unchanged(single_client):
    """Brief §3.2: the whole-experiment flag moves no spec ``filters.build`` makes."""
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE):
        record = _record(single_client, table)
        two = record.kind == ddl.KIND_TWO_SHOWER
        for selection in ({}, {"e1_min": 1.5, "e1_max": 9.5}, *(({"include_undefined_d": True},) if two else ())):
            spec = filters.build(record, **selection)
            assert spec.whole_experiment is False and spec.clamped(record).whole_experiment is False
            e1 = (selection.get("e1_min", record.e1_min), selection.get("e1_max", record.e1_max))
            if two:
                d_clause = ("(h.d IS NULL OR h.d BETWEEN $d_min AND $d_max)" if spec.include_undefined_d
                            else "h.d IS NOT NULL AND h.d BETWEEN $d_min AND $d_max")
                assert spec.where_sql("h") == (
                    f"h.e1 BETWEEN $e1_min AND $e1_max AND h.e2 BETWEEN $e2_min AND $e2_max AND {d_clause}")
                assert spec.params() == {"e1_min": e1[0], "e1_max": e1[1], "e2_min": record.e2_min,
                                         "e2_max": record.e2_max, "d_min": record.d_min, "d_max": record.d_max}
                assert spec.as_dict() == {"e1": list(e1), "e2": [record.e2_min, record.e2_max],
                                          "d": [record.d_min, record.d_max],
                                          "include_undefined_d": spec.include_undefined_d}
                assert spec.cache_key() == (
                    table, round(e1[0], 6), round(e1[1], 6), round(record.e2_min, 6), round(record.e2_max, 6),
                    round(record.d_min, 4), round(record.d_max, 4), spec.include_undefined_d)
            else:
                assert spec.where_sql() == "e1 BETWEEN $e1_min AND $e1_max"
                assert spec.params() == {"e1_min": e1[0], "e1_max": e1[1]}
                assert spec.as_dict() == {"e1": list(e1), "e2": [None, None], "d": [None, None],
                                          "include_undefined_d": False}
                assert spec.cache_key() == (table, round(e1[0], 6), round(e1[1], 6), None, None, None, None,
                                            False)
            # The whole experiment never shares a cache entry with a selection.
            assert filters.unbounded(record).cache_key() != spec.cache_key()
        whole = filters.unbounded(record)
        assert whole.clamped(record) is whole
        assert whole.as_dict() == {"e1": [None, None], "e2": [None, None], "d": [None, None],
                                   "include_undefined_d": two}


# ------------------------------------------------------- the experiment refusals --

_POOL_ROUTES = ((CANDIDATES, {}), (PICK, {}), (PICK, {"rule": "uniform"}), (EVENT, {"event_number": 0}),
                (EVENT, {"event_number": 0, "format": "voxels"}))


@pytest.mark.parametrize("name, value", [
    # Each one looser than the data, so the selection basis takes it (and selects everything).
    ("e1_min", 0.0), ("e1_max", 1000.0), ("e2_min", 0.0), ("e2_max", 1000.0), ("d_min", 0.0),
    ("d_max", 100000.0), ("include_undefined_d", "true"),
])
def test_a_selection_parameter_is_refused_under_the_experiment_basis(single_client, name, value):
    """Brief §3.1: a silently ignored cut is a selection the reader believes was made."""
    detail = NOT_WITH_EXPERIMENT.format(name=name)
    for table in (BASELINE_TABLE, SINGLE_HITS_TABLE):
        for url, extra in _POOL_ROUTES:
            if table == SINGLE_HITS_TABLE and url == EVENT:
                extra = {**extra, "event_number": 3}
            response = single_client.get(url, params={"table_name": table, **extra, **EXPERIMENT, name: value})
            assert response.status_code == 422, (table, url, response.text[:300])
            problem = response.json()
            assert problem["type"] == "/problems/validation-error"
            # On one shower too: the basis's sentence, not the kind's own refusal of E2 and D.
            assert problem["field"] == name and problem["detail"] == detail, (table, url, problem)
    # The selection basis still takes it, and include_undefined_d=false is the default.
    assert single_client.get(CANDIDATES, params={**BASE, "basis": "selection", name: value}).status_code == 200
    assert single_client.get(CANDIDATES, params={**BASE, **EXPERIMENT,
                                                 "include_undefined_d": "false"}).status_code == 200
    # Two refused at once: the first in the order E1, E2, D, include_undefined_d is named.
    both = single_client.get(CANDIDATES, params={**BASE, **EXPERIMENT, "d_max": 100000.0, "e2_min": 0.0})
    assert both.json()["field"] == "e2_min"


@pytest.mark.parametrize("value", ["x", "Experiment", "", "all", "-1"])
def test_an_unknown_basis_is_refused_naming_it(single_client, value):
    for url, extra in _POOL_ROUTES:
        response = single_client.get(url, params={**BASE, **extra, "basis": value})
        assert response.status_code == 422, (url, response.text[:300])
        problem = response.json()
        assert problem["field"] == "basis"
        assert problem["detail"] == typographic(f"basis must be selection or experiment; got {value!r}.")
        assert not signed_hyphens(problem["detail"])
    if value == "x":
        assert problem["detail"] == "basis must be selection or experiment; got 'x'."


def test_the_aggregate_is_refused_by_its_capability_under_either_basis(single_client):
    gates = {CANDIDATES: "event-inspector", PICK: "event-inspector"}
    for url, extra in _POOL_ROUTES:
        for params in (EXPERIMENT, {**EXPERIMENT, "e1_min": 1.0}, {"basis": "bogus"}):
            response = single_client.get(url, params={**EVENTS, **extra, **params})
            assert response.status_code == 422
            problem = response.json()
            contract_check.check(problem, "capability_problem")
            gate = gates.get(url) or ("vox-event" if extra.get("format") == "voxels" else "event-inspector")
            assert problem["field"] == "table_name" and problem["capability"] == gate, (url, params, problem)


def test_an_empty_experiment_pool_is_a_404_with_its_sentence(single_client):
    for rule in (None, "tilted", "densest", "uniform"):
        params = {**BASE, **EXPERIMENT, **BASE_CASES["p_5_6"], **({} if rule is None else {"rule": rule})}
        response = single_client.get(PICK, params=params)
        assert response.status_code == 404
        assert response.json()["detail"] == (
            "The experiment holds no candidate event: none of its events with a defined separation holds "
            "a shower with p in 5.00–6.00 GeV that deposited energy.")
        response = single_client.get(PICK, params={**HITS, **EXPERIMENT, **SINGLE_CASES["empty"],
                                                   **({} if rule is None else {"rule": rule})})
        assert response.status_code == 404
        assert response.json()["detail"] == (
            "The experiment holds no candidate event: none of its events with an incident direction and an "
            "entry point has its shower at θ in 0.0–5.0° (0.000–0.087 rad).")
    # Inactive: copies of the event tables in which no event can be placed.
    for table, alter, detail in (
            (BASELINE_TABLE, "NULL::DOUBLE AS d",
             "The experiment holds no event with a defined separation to pick from."),
            (SINGLE_HITS_TABLE, "NULL::DOUBLE AS theta_a",
             "The experiment holds no event with an incident direction and an entry point to pick from.")):
        record = _record(single_client, table)
        probe = dataclasses.replace(record, table_name=f"{table}_empty_probe")
        view = quote(naming.event_table(probe.table_name))
        with single_client.app.state.database.read_cursor() as con:
            con.execute(f"CREATE TEMP VIEW {view} AS SELECT * REPLACE ({alter}) "
                        f"FROM {quote(naming.event_table(table))}")
            try:
                for rule in event_inspector.RULES:
                    with pytest.raises(NotFoundError) as caught:
                        event_inspector.pick(con, probe, filters.unbounded(probe), rule=rule)
                    assert caught.value.detail == detail, rule
                counts = particle.candidates(con, probe, filters.unbounded(probe), particle.INACTIVE)
                assert counts["n_events"] == 0 and counts["n_unplaceable"] == counts["n_selection"] > 0
            finally:
                con.execute(f"DROP VIEW {view}")
    # The counts are never a 404: N = 0 is an answer.
    body = _ok(single_client, CANDIDATES, **BASE, **EXPERIMENT, **BASE_CASES["p_5_6"], event_number=0)
    assert body["candidates"]["n_events"] == 0 and body["event"]["in_pool"] is False
    assert body["event"]["in_selection"] is True


def test_an_unplaceable_event_is_counted_under_the_experiment_basis(single_client):
    """The whole experiment holds the events the frame gate refuses: counted, never offered, stepped over.

    The probes of :func:`test_an_unplaceable_event_is_counted_and_never_offered`,
    without include_undefined_d: the experiment basis holds an event without D
    by itself.
    """
    for table, alter, two in (
            (BASELINE_TABLE, "CASE WHEN event_number = 1 THEN NULL ELSE d END AS d, "
                             "CASE WHEN event_number = 1 THEN 0 ELSE n_a_rows END AS n_a_rows", True),
            (SINGLE_HITS_TABLE, "CASE WHEN event_number = {mid} THEN NULL ELSE theta_a END AS theta_a", False)):
        record = _record(single_client, table)
        probe = dataclasses.replace(record, table_name=f"{table}_unplaceable_whole_probe")
        view = quote(naming.event_table(probe.table_name))
        with single_client.app.state.database.read_cursor() as con:
            events = [r[0] for r in con.execute(
                f"SELECT event_number FROM {quote(naming.event_table(table))} ORDER BY 1").fetchall()]
            mid = events[len(events) // 2]
            con.execute(f"CREATE TEMP VIEW {view} AS "
                        f"SELECT * REPLACE ({alter.format(mid=mid)}) FROM {quote(naming.event_table(table))}")
            try:
                target = 1 if two else mid
                spec = filters.unbounded(probe)
                for spec_particle in (particle.INACTIVE, particle.build(probe, theta_min=10.0)):
                    counts = particle.candidates(con, probe, spec, spec_particle)
                    assert counts["basis"] == "experiment"
                    assert counts["n_unplaceable"] == 1 and counts["n_selection"] == len(events)
                    assert counts["n_events"] == len(events) - 1
                    pool = particle.pool_events(con, probe, spec, spec_particle).tolist()
                    assert target not in pool and len(pool) == len(events) - 1
                    member = particle.membership(con, probe, spec, spec_particle, target)
                    assert member["in_selection"] is True and member["in_pool"] is False
                    for neighbour in (e for e in events if e != target):
                        around = particle.membership(con, probe, spec, spec_particle, neighbour)
                        assert around["in_selection"] is True
                        assert target not in (around["prev"], around["next"])
                    drawn = {event_inspector.pick(con, probe, spec, rule="uniform", particle=spec_particle,
                                                  draw=d)["event_number"] for d in range(len(pool))}
                    assert drawn == set(pool)
            finally:
                con.execute(f"DROP VIEW {view}")


# -------------------------------------------- the experiment basis: the bodies --


def test_the_single_shower_experiment_sentences(single_client):
    record = _record(single_client, SINGLE_HITS_TABLE)
    params = {**HITS, **EXPERIMENT, **SINGLE_CASES["theta"]}
    interval = "θ in 20.0–25.0° (0.349–0.436 rad)"
    population = f"events of the experiment with an incident direction and an entry point whose shower has {interval}"
    uniform = _ok(single_client, PICK, **params, rule="uniform", draw=1)
    n = uniform["n_events"]
    assert uniform["rule"] == (
        f"Drawn uniformly at random from the {n:,} {population}: entry 2 of a seeded shuffle of them in "
        f"event-number order (seed 42, draw 1), so no event repeats until all {n:,} have been drawn.")
    tilted = _ok(single_client, PICK, **params)
    assert tilted["rule_id"] == "tilted" and tilted["rule"] == (
        f"Among the {tilted['n_events']:,} {population}, those with more hits than the mean "
        f"({tilted['mean_hits']:.1f}); of those the {len(tilted['pool'])} with the largest incident polar "
        "angle of a matching shower; one drawn at random with seed 42 - the reference notebook's "
        "selection rule.")
    # Inactive: the whole experiment's phrase, and the body names its rule, match and echo anyway.
    bare = _ok(single_client, PICK, **HITS, **EXPERIMENT, seed=7)
    placeable = sum(b["placeable"] for b in _brute(_rows(single_client, record), record, {}, {}, whole=True))
    assert bare["n_events"] == placeable
    assert bare["rule"].startswith(f"Among the {placeable:,} events of the experiment with an incident direction "
                                   "and an entry point, those with more hits than the mean")
    assert bare["basis"] == "experiment" and bare["rule_id"] == "tilted" and bare["matched"] == ["a"]
    assert bare["particle"]["active"] is False and bare["filter"] == _experiment_echo(record)
    for body in (uniform, tilted, bare):
        _no_hyphen_signs(body)


def test_one_experiment_candidate_is_the_only_one(single_client):
    population = ("events of the experiment with a defined separation holding a shower with p in "
                  "2.00–3.00 GeV that deposited energy")
    body = _ok(single_client, PICK, **BASE, **EXPERIMENT, **BASE_CASES["p_2_3"], rule="uniform", seed=11, draw=5)
    assert body["event_number"] == 0 and body["n_events"] == 1
    assert body["rule"] == f"The only one of the {population} (seed 11, draw 5)."
    tilted = _ok(single_client, PICK, **BASE, **EXPERIMENT, **BASE_CASES["p_2_3"], seed=11)
    assert tilted["rule"] == (f"The only one of the {population}: the reference notebook's selection rule has "
                              "one event to choose from (seed 11).")
    densest = _ok(single_client, PICK, **BASE, **EXPERIMENT, **BASE_CASES["p_2_3"], rule="densest", seed=11)
    assert densest["rule"].startswith(f"The only one of the {population}: the reference notebook's densest event")


def test_the_experiment_warnings(single_client):
    """in_selection is always true, so only the outside-pool warning can fire; it is unchanged."""
    for fmt in ("raster", "voxels"):
        extra = {"format": fmt, **({"frame": "lab"} if fmt == "voxels" else {})}
        missed = _ok(single_client, EVENT, **BASE, **EXPERIMENT, **extra, event_number=1, **BASE_CASES["p_2_3"])
        assert missed["meta"]["warnings"] == [
            "Event 1 holds no shower matching the particle filter (p in 2.00–3.00 GeV); it is drawn as asked, "
            "and the previous / next controls walk the candidates."]
        assert missed["event"]["in_selection"] is True and missed["event"]["candidates"]["basis"] == "experiment"
        assert missed["event"]["prev"] == 0 and missed["event"]["candidates"]["prev_matched"] == ["a"]
        kept = _ok(single_client, EVENT, **BASE, **EXPERIMENT, **extra, event_number=0, **BASE_CASES["p_2_3"])
        assert kept["meta"]["warnings"] == [] and kept["event"]["candidates"]["index"] == 0
        plain = _ok(single_client, EVENT, **BASE, **EXPERIMENT, **extra, event_number=0)
        assert plain["meta"]["warnings"] == []
        for body in (missed, kept, plain):
            assert "outside the current selection" not in json.dumps(body)


def _meta_notes(body: dict) -> dict:
    return {k: v for k, v in body["meta"].items() if k not in ("query_ms", "total_ms", "cached", "warnings")}


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


_GEOMETRY = {"raster": ("frames", "scale", "grid", "window", "coordinates", "footprint_mm"),
             "voxels": ("voxels", "window", "coordinates", "footprint_mm")}


@pytest.mark.parametrize("fmt, frame", [("raster", None), ("voxels", "lab"), ("voxels", "local")])
@pytest.mark.parametrize("table, event", [(BASELINE_TABLE, 0), (BASELINE_TABLE, 1), (SINGLE_HITS_TABLE, 3)])
def test_the_basis_never_moves_the_geometry(single_client, fmt, frame, table, event):
    """Brief §3.3: one event and shower under either basis - the same frames, voxels, window, scale
    and layer planes; the event block differs only where it places the event among the candidates."""
    request = {"table_name": table, "event_number": event, "shower": "a", "format": fmt,
               **({} if frame is None else {"frame": frame})}
    record = _record(single_client, table)
    top = record.e1_max
    selections = ({}, {"e1_min": top + 5.0, "e1_max": top + 6.0})
    whole = _ok(single_client, EVENT, **request, **EXPERIMENT)
    narrowed = _ok(single_client, EVENT, **request, **EXPERIMENT,
                   **(BASE_CASES["p_2_3"] if table == BASELINE_TABLE else SINGLE_CASES["theta"]))
    if fmt == "voxels":
        contract_check.check(whole, "event_voxels")
    for selection in selections:
        plain = _ok(single_client, EVENT, **request, **selection)
        for other in (whole, narrowed):
            for key in _GEOMETRY[fmt]:
                assert other[key] == plain[key], (key, selection)
            if fmt == "raster":
                for kind, block in plain["frames"].items():
                    assert other["frames"][kind]["layer_planes"] == block["layer_planes"]
            a, b = dict(plain["event"]), dict(other["event"])
            for key in ("candidates", "prev", "next", "in_selection"):
                a.pop(key), b.pop(key)
            assert a == b
            # The notes the meta carries (the notices, the window rule, the format's own keys).
            assert _meta_notes(other) == _meta_notes(plain)
        assert whole["event"]["in_selection"] is True
        if not selection:
            # The default selection holds every placeable event of these files: the same pool.
            assert {k: v for k, v in whole["event"]["candidates"].items() if k != "basis"} == \
                plain["event"]["candidates"]
            assert (whole["event"]["prev"], whole["event"]["next"]) == (plain["event"]["prev"], plain["event"]["next"])
        else:
            assert plain["event"]["in_selection"] is False


def test_the_experiment_raster_budget_measures_the_event_block(single_client):
    """Under the experiment basis too, the event block (its basis included) is inside the measured body."""
    with single_client.app.state.database.read_cursor() as con:
        record = registry.require_ready(con, BASELINE_TABLE)
        spec = filters.unbounded(record)
        footprint = canonical.cell_footprint(con, record)
        body = event_inspector.inspect(con, record, spec, 0, "a", "file", footprint)
        assert body["event"]["candidates"]["basis"] == "experiment" and body["event"]["in_selection"] is True
        size = density.wire_size({k: body[k] for k in ("frames", "scale", "grid", "event")})
        without = density.wire_size({k: body[k] for k in ("frames", "scale", "grid")})
        assert without < size < density.RESPONSE_LIMIT
        tight = event_inspector.inspect(con, record, spec, 0, "a", "file", footprint, limit=size)
    trimmed = any((frame.get("layer_planes") or {}).get("trimmed") for frame in tight["frames"].values())
    assert trimmed or tight["grid"]["pitch_mm"] > body["grid"]["pitch_mm"]
    assert tight["event"] == body["event"]


def test_every_experiment_body_fits_the_contract_and_its_typography(single_client):
    """Every route under the experiment basis: under 100 KB (``_ok``), no number signed with a hyphen."""
    for table, cases, event in ((BASELINE_TABLE, BASE_CASES, 0), (SINGLE_HITS_TABLE, SINGLE_CASES, 3)):
        for name, case in cases.items():
            params = {"table_name": table, **EXPERIMENT, **case}
            bodies = [_ok(single_client, CANDIDATES, **params, event_number=event)]
            if name not in ("empty", "p_5_6"):
                bodies += [_ok(single_client, PICK, **params, rule=rule) for rule in event_inspector.RULES]
            bodies += [_ok(single_client, EVENT, **params, event_number=event),
                       *(_ok(single_client, EVENT, **params, event_number=event, format="voxels", frame=frame)
                         for frame in ("lab", "local"))]
            for body in bodies:
                _no_hyphen_signs(body)
                assert '"hits"' not in json.dumps(body) and '"points"' not in json.dumps(body)


def test_basis_selection_is_the_request_that_names_none(single_client):
    """Brief §3.3: under basis=selection every response is byte for byte today's (timings aside)."""
    requests = [
        (CANDIDATES, {**BASE, "event_number": 0}), (CANDIDATES, {**BASE, **BASE_CASES["p_2_3"], "event_number": 1}),
        (CANDIDATES, {**HITS, "event_number": 3, "e1_min": 4.0, "e1_max": 12.0}),
        (PICK, {**BASE, "seed": 7}), (PICK, {**BASE, "rule": "uniform", "draw": 1}),
        (PICK, {**HITS, "rule": "densest"}), (PICK, {**BASE, **BASE_CASES["p_2_3"]}),
        (EVENT, {**BASE, "event_number": 0}), (EVENT, {**BASE, "event_number": 1, **BASE_CASES["p_2_3"]}),
        (EVENT, {**BASE, "event_number": 0, "format": "voxels", "frame": "lab"}),
        (EVENT, {**HITS, "event_number": 3, "format": "voxels", "frame": "local"}),
    ]

    def comparable(response) -> dict:
        assert response.status_code == 200, response.text[:300]
        body = response.json()
        for key in ("total_ms", "query_ms", "cached"):
            body["meta"].pop(key, None)
        body.pop("elapsed_ms", None)
        return body

    for url, params in requests:
        today = comparable(single_client.get(url, params=params))
        named = comparable(single_client.get(url, params={**params, "basis": "selection"}))
        assert named == today, (url, params)
        assert "basis" not in set(_keys(named)), (url, params)
