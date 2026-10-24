"""The ``single_client`` server holds all three kinds and describes each."""

from __future__ import annotations

from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE, SINGLE_HITS_TABLE


def test_the_three_kinds_are_served(single_client):
    listed = {e["table_name"]: e for e in single_client.get("/api/experiments").json()["experiments"]}
    assert listed[BASELINE_TABLE]["kind"] == "two_shower_hits"
    assert listed[SINGLE_HITS_TABLE]["kind"] == "single_shower_hits"
    assert listed[SINGLE_EVENTS_TABLE]["kind"] == "single_shower_events"
    for name in (BASELINE_TABLE, SINGLE_HITS_TABLE, SINGLE_EVENTS_TABLE):
        assert listed[name]["status"] == "ready"
        assert listed[name]["capabilities"]["derived"]["status"] == "current"
    assert listed[SINGLE_HITS_TABLE]["capabilities"]["filters"] == ["e1"]
    assert listed[SINGLE_EVENTS_TABLE]["capabilities"]["has_hits"] is False
