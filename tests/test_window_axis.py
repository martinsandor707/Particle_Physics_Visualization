"""The windowed ensemble axis of the absolute frame, and where the incident directions point.

The axis of a depth panel's window is the mean trajectory of the events whose
entry point lies in it, with the sample SD of the per-event trajectories at
each depth and the Student-t interval of the mean (``query/window_axis.py``);
``summary.pointing`` measures the directions against the radial line through
each shower's centroid. Both are recomputed here in NumPy from the event table.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.db import naming
from calosrv.db.naming import quote
from calosrv.errors import ValidationError
from calosrv.grid import frame as frame_mod
from calosrv.query import density, filters, summary, window_axis
from calosrv.text import signed_hyphens


def _events(cursor, record, shower):
    """theta, phi and the 3-D centroid of every event with both defined, as arrays."""
    table = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"SELECT theta_{shower}, phi_{shower}, c{shower}x, c{shower}y, c{shower}z FROM {table} "
        f"WHERE theta_{shower} IS NOT NULL AND phi_{shower} IS NOT NULL AND c{shower}x IS NOT NULL "
        f"AND c{shower}y IS NOT NULL AND c{shower}z IS NOT NULL ORDER BY event_number"
    ).fetchall()
    return np.asarray(rows, dtype=np.float64).reshape(-1, 5)


def _entry_and_slope(ev, axis, z_front):
    theta, phi, cx, cy, cz = ev.T
    sx, sy = np.tan(theta) * np.cos(phi), np.tan(theta) * np.sin(phi)
    xe, ye = cx - (cz - z_front) * sx, cy - (cz - z_front) * sy
    return (xe, sx) if axis == "x" else (ye, sy)


# ----------------------------------------------------------- the axis --


def test_the_axis_is_the_mean_trajectory_with_its_exact_band(cursor, record):
    spec = filters.build(record)
    z_front, depth_max = float(record.lattice.z.lo), float(record.lattice.z.hi)
    for panel, axis in (("xz", "x"), ("yz", "y")):
        body = window_axis.window_axis(cursor, record, spec, panel, -1e5, 1e5)
        assert body["panel"] == panel and body["axis"] == axis and body["z_front"] == z_front
        for shower in ("a", "b"):
            ev = _events(cursor, record, shower)
            te, s = _entry_and_slope(ev, axis, z_front)
            block = body[shower]
            n = te.size
            assert block["n"] == n == block["n_selection"]
            if n < 2:
                continue
            assert block["slope"] == pytest.approx(s.mean())
            assert block["slope_sd"] == pytest.approx(s.std(ddof=1))
            assert block["anchor"]["t"] == pytest.approx(te.mean())
            assert block["anchor"]["sd"] == pytest.approx(te.std(ddof=1))
            t_value = frame_mod.t_quantile_975(n - 1)
            assert block["se95"] == pytest.approx(t_value * s.std(ddof=1) / math.sqrt(n))
            assert block["axis"][0] == pytest.approx([z_front, te.mean()])
            assert block["axis"][1] == pytest.approx([depth_max, te.mean() + s.mean() * (depth_max - z_front)])
            cov = np.cov(te, s, ddof=1)[0, 1]
            assert len(block["band"]) == window_axis.STATIONS == len(block["envelope"])
            for (z, lo, hi), (ze, elo, ehi) in zip(block["band"], block["envelope"]):
                dz = z - z_front
                centre = te.mean() + s.mean() * dz
                sd = math.sqrt(max(0.0, te.var(ddof=1) + 2 * dz * cov + dz * dz * s.var(ddof=1)))
                assert (lo, hi) == pytest.approx((centre - sd, centre + sd), abs=1e-9)
                assert z == ze
                assert (elo, ehi) == pytest.approx((centre - t_value * sd / math.sqrt(n),
                                                    centre + t_value * sd / math.sqrt(n)), abs=1e-9)
                # The interval of the mean lies inside the dispersion band once
                # t / sqrt(N) is below one (N >= 7); at N = 2 the one-degree-of-freedom
                # interval is 9 x the SD, which is the honest width, and said so.
                if t_value / math.sqrt(n) <= 1.0:
                    assert lo - 1e-9 <= elo <= ehi <= hi + 1e-9
                else:
                    assert elo <= lo and hi <= ehi
            # The gate is the lean against the fan, and the low-N labels follow the D-frame's table.
            if s.std(ddof=1) > 0:
                ratio = abs(s.mean()) / s.std(ddof=1)
                assert block["lean_ratio"] == pytest.approx(ratio)
                assert block["faded"] is bool(ratio < window_axis.LEAN_RATIO_MIN)
            else:
                assert block["lean_ratio"] is None and block["faded"] is False
            assert block["fan_deg"] == pytest.approx(math.degrees(np.arctan(s).std(ddof=1)))
            assert block["dof_note"] == ("1 d.o.f." if n == 2 else None)
            assert block["label"] == (f"weak (N = {n})" if n < frame_mod.PROVISIONAL_N else "")
            resultant = math.hypot(np.cos(ev[:, 1]).mean(), np.sin(ev[:, 1]).mean())
            assert block["resultant_azimuth"] == pytest.approx(resultant)
            assert 0.0 <= block["rayleigh_p"] <= 1.0
        for note in body["notes"]:
            assert not signed_hyphens(note), note
        assert "lean reaches one SD" in body["rule"]


def test_a_window_holding_one_event_draws_that_trajectory_and_no_band(cursor, record):
    spec = filters.build(record)
    z_front = float(record.lattice.z.lo)
    ev = _events(cursor, record, "a")
    te, s = _entry_and_slope(ev, "x", z_front)
    order = np.argsort(te)
    first = te[order[0]]
    # A window around the lowest entry point that the next one stays out of.
    hi = first + 0.5 * (te[order[1]] - first) if te.size > 1 else first + 1.0
    body = window_axis.window_axis(cursor, record, spec, "xz", first - 1.0, hi)
    block = body["a"]
    assert block["n"] == 1 and block["n_selection"] == te.size
    assert block["label"] == "single event, not an ensemble"
    assert block["band"] is None and block["envelope"] is None and block["faded"] is False
    assert block["slope"] == pytest.approx(s[order[0]])
    assert block["axis"][0] == pytest.approx([z_front, first])
    assert "not an ensemble" in body["notes"][0]


def test_an_empty_window_draws_nothing_and_says_so(cursor, record):
    spec = filters.build(record)
    body = window_axis.window_axis(cursor, record, spec, "yz", 1e6, 1e6 + 1.0)
    for shower in ("a", "b"):
        assert body[shower]["n"] == 0 and body[shower]["axis"] is None
    assert all("no selected event enters the window" in note for note in body["notes"])


def test_a_bad_panel_or_window_is_refused(cursor, record):
    spec = filters.build(record)
    with pytest.raises(ValidationError):
        window_axis.window_axis(cursor, record, spec, "xy", -1.0, 1.0)
    with pytest.raises(ValidationError):
        window_axis.window_axis(cursor, record, spec, "xz", 1.0, 1.0)
    with pytest.raises(ValidationError):
        window_axis.window_axis(cursor, record, spec, "xz", float("nan"), 1.0)


# --------------------------------------------------------- the pointing --


def test_pointing_measures_the_directions_against_the_radial_line(cursor, record):
    spec = filters.build(record)
    out = summary.pointing(cursor, record, spec)
    for shower in ("a", "b"):
        ev = _events(cursor, record, shower)
        theta, phi, cx, cy, cz = ev.T
        residual = np.arctan2(np.sin(phi - np.arctan2(cy, cx)), np.cos(phi - np.arctan2(cy, cx)))
        block = out[shower]
        assert block["n"] == ev.shape[0]
        assert block["mean_deg"] == pytest.approx(math.degrees(residual.mean()))
        if ev.shape[0] >= 2:
            assert block["sd_deg"] == pytest.approx(math.degrees(residual.std(ddof=1)))
        assert block["source_z_mm"] == pytest.approx(np.median(np.hypot(cx, cy) / np.tan(theta)))
        assert block["centroid_z_mm"] == pytest.approx(np.median(cz))
    assert out["note"].startswith("Incident directions point at the detector origin")
    assert not signed_hyphens(out["note"]), out["note"]
    # The low-N table: the demonstration file's two events give one degree of freedom.
    for shower in ("a", "b"):
        n = out[shower]["n"]
        label = " (1 d.o.f., weak)" if n == 2 else " (weak)" if n < 20 else ""
        assert f"{shower.upper()}: " in out["note"]
        assert f"SD over N = {n:,}{label}" in out["note"]


# -------------------------------------------------------------- the route --


def test_the_route_serves_the_axis_under_the_contract(client):
    response = client.get("/api/window-axis", params={"panel": "xz", "t_min": -3000.0, "t_max": 3000.0})
    assert response.status_code == 200
    assert len(response.content) < density.RESPONSE_LIMIT
    body = response.json()
    assert body["panel"] == "xz" and body["axis"] == "x" and body["window"] == [-3000.0, 3000.0]
    assert set(body["a"]) >= {"n", "axis", "band", "envelope", "slope", "lean_ratio", "faded", "label"}
    assert body["meta"]["panel"] == "xz"
    assert [n["scope"] for n in body["meta"]["notices"]] == ["window_axis", "window_axis"]
    for text in (*body["notes"], body["rule"], *(n["text"] for n in body["meta"]["notices"])):
        assert not signed_hyphens(text), text
    assert client.get("/api/window-axis", params={"panel": "xy", "t_min": -1.0, "t_max": 1.0}).status_code == 422
    assert client.get("/api/window-axis", params={"panel": "xz", "t_min": 1.0, "t_max": 1.0}).status_code == 422
    assert client.get("/api/window-axis", params={"panel": "xz", "t_max": 1.0}).status_code == 422


def test_both_frames_report_where_the_directions_point(client):
    lab = client.get("/api/projections").json()
    pointing = lab["overlays"]["pointing"]
    assert pointing["a"]["n"] > 0 and pointing["note"].startswith("Incident directions point")
    assert "centres of deposited energy" in lab["overlays"]["coherence"]["note"]
    canonical = client.get("/api/projections", params={"frame": "canonical"}).json()
    assert canonical["overlays"]["pointing"]["a"]["n"] == pointing["a"]["n"]


def test_a_cloned_selection_has_identical_directions_and_no_fan(synthetic_client):
    """The synthetic file clones two template events, so a window round one template's entry
    point holds many events of one direction: the fan is zero and the axis is drawn in full."""
    payload = synthetic_client.get("/api/projections", params={"d_min": 580, "d_max": 620}).json()
    experiments = synthetic_client.get("/api/experiments").json()["experiments"]
    assert payload["selection"]["n_events"] >= 100
    whole = synthetic_client.get("/api/window-axis", params={
        "panel": "xz", "t_min": -1e5, "t_max": 1e5, "d_min": 580, "d_max": 620}).json()
    for shower in ("a", "b"):
        block = whole[shower]
        assert block["n"] == payload["selection"]["n_events"]
        # Two template directions: a real fan, a lean, both finite.
        assert block["slope_sd"] > 0 and block["fan_deg"] > 0
    anchor = whole["a"]["anchor"]["t"]
    sd = whole["a"]["anchor"]["sd"]
    narrow = synthetic_client.get("/api/window-axis", params={
        "panel": "xz", "t_min": anchor - 2 * sd, "t_max": anchor + 2 * sd, "d_min": 580, "d_max": 620}).json()
    assert 0 < narrow["a"]["n"] <= whole["a"]["n"]
    del experiments
