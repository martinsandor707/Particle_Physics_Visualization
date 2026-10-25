"""C8 at query level: the moment sums against DuckDB, φ kept circular, the low-N gates.

The demonstration experiment holds two events, one fewer than a correlation
needs, so its payload is gated to empty cells. The sums beneath the gate are
not, and they are checked here against DuckDB's own ``corr()`` over the same
hits, selected by SQL written independently of the module: every frame, both
energy scales, every shower choice. The jackknife needs four event groups and
is checked on the booted fixtures (``test_physics_correlations_api.py``).
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

import contract_check
from calosrv.db import naming
from calosrv.errors import ValidationError
from calosrv.models.common import ApiMeta, envelope
from calosrv.query import correlations, density, filters, hit_sql
from calosrv.query import showers as showers_mod
from calosrv.stats import jackknife

FRAMES = ("local", "trans", "lab")
SHOWERS = ("both", "a", "b")
#: The oracle's column for each of correlations.HIT_KEYS.
ORACLE = ("x", "y", "z", "e", "mom", "th", "c", "s")


def _oracle(record, spec, coord_system: str, energy_scale: str, shower: str) -> str:
    """SQL of the selected hits with their own shower's p, θ, cos φ, sin φ - not the module's."""
    proj = naming.quote(naming.proj_table(record.table_name))
    event = naming.quote(naming.event_table(record.table_name))
    if coord_system == "local":
        x, y, z = "p.xl", "p.yl", "p.zl"
    elif coord_system == "trans":
        x, y, z = "p.xt", "p.yt", f"p.kt * {hit_sql.layer_pitch(record)!r}"
    else:
        x, y, z = ("list_extract($ox, p.ix + 1)", "list_extract($oy, p.iy + 1)",
                   "list_extract($oz, p.iz + 1)")
    energy = "p.energy" if energy_scale == "linear" else "log10(p.energy)"

    def own(a: str, b: str) -> str:
        return f"CAST(CASE WHEN p.org = 0 THEN ev.{a} ELSE ev.{b} END AS DOUBLE)"

    keep = {"a": "p.org = 0", "b": "p.org IN (1, 2)", "both": "TRUE"}[shower]
    phi = own("phi_a", "phi_b")
    return f"""
        SELECT CAST({x} AS DOUBLE) AS x, CAST({y} AS DOUBLE) AS y, CAST({z} AS DOUBLE) AS z,
               {energy} AS e, {own('e1', 'e2')} AS mom, {own('theta_a', 'theta_b')} AS th,
               cos({phi}) AS c, sin({phi}) AS s, p.event_number AS ev_n
        FROM {proj} p JOIN {event} ev ON ev.event_number = p.event_number
        WHERE {keep} AND {spec.where_sql('ev')}
    """


def _oracle_params(record, spec, coord_system: str) -> dict:
    params = dict(spec.params())
    if coord_system == "lab":
        lattice = record.lattice
        params.update(ox=[float(v) for v in lattice.x.coords],
                      oy=[float(v) for v in lattice.y.coords],
                      oz=[float(v) for v in lattice.z.coords])
    return params


@pytest.mark.parametrize("shower", SHOWERS)
@pytest.mark.parametrize("energy_scale", correlations.ENERGY_SCALES)
@pytest.mark.parametrize("coord_system", FRAMES)
def test_r_from_the_moment_sums_equals_duckdb_corr(cursor, record, coord_system, energy_scale,
                                                   shower):
    spec = filters.build(record)
    a = correlations.analyse(cursor, record, spec, coord_system=coord_system, shower=shower,
                             energy_scale=energy_scale)
    sql = _oracle(record, spec, coord_system, energy_scale, shower)
    pairs = [(i, j) for i in range(len(ORACLE)) for j in range(i + 1, len(ORACLE))]
    row = cursor.execute(
        f"SELECT count(*), {', '.join(f'corr({ORACLE[i]}, {ORACLE[j]})' for i, j in pairs)} "
        f"FROM ({sql})",
        _oracle_params(record, spec, coord_system),
    ).fetchone()
    assert a.n_hits == row[0] > 0
    r = a.hit.pearson()
    checked = 0
    for (i, j), expected in zip(pairs, row[1:]):
        if expected is None or not math.isfinite(expected):
            assert not math.isfinite(r[i, j]), (ORACLE[i], ORACLE[j])
            continue
        assert r[i, j] == pytest.approx(expected, abs=1e-9), (ORACLE[i], ORACLE[j])
        checked += 1
    assert checked >= 15


@pytest.mark.parametrize("shower", SHOWERS)
def test_hit_weighted_per_shower_pairs_equal_the_hit_level_matrix(cursor, record, shower):
    """The event table, each shower weighted by its hits, reproduces the hit-level r exactly."""
    a = correlations.analyse(cursor, record, filters.build(record), shower=shower)
    hit = a.hit.pearson()[4:, 4:]                     # p, θ, cos φ, sin φ at hit level
    weighted = a.shower_w.pearson()
    assert np.array_equal(np.isfinite(weighted), np.isfinite(hit))
    assert np.isfinite(weighted).any()
    # 1e-9 as against corr(): with two events every r here is ±1, where the hit-level
    # sums' cancellation leaves ~1e-11 (on the booted fixtures the two agree to 1e-13).
    assert weighted[np.isfinite(weighted)] == pytest.approx(hit[np.isfinite(hit)], abs=1e-9)
    # The weighted sums count hits, the per-shower sums count showers.
    assert a.shower_w.total == a.n_hits == a.selection.n_hits
    assert a.shower_u.total == a.selection.n_showers
    assert a.shower_w.groups == a.shower_u.groups == a.hit.groups == a.selection.n_events


def _accumulated(sql: str) -> list[str]:
    """The expressions a scan accumulates: everything it selects ``AS v<i>``."""
    out = []
    for match in re.finditer(r" AS v\d+\b", sql):
        depth, i = 0, match.start() - 1
        while i >= 0:
            ch = sql[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            i -= 1
        out.append(sql[i + 1:match.start()].strip())
    return out


def test_phi_enters_only_through_its_cosine_and_sine(record):
    spec = filters.build(record)
    both = showers_mod.of(record, "both")
    for coord_system in FRAMES:
        sql, _, _ = correlations.hit_scan_sql(record, spec, both, coord_system, "linear", 100)
        values = _accumulated(sql)
        assert len(values) == len(correlations.HIT_KEYS)
        assert [v for v in values if "ph" in v] == ["cos(s.ph)", "sin(s.ph)"]
        # Nowhere in the scan is φ itself summed or multiplied.
        assert all(m.group(0) in ("cos(s.ph", "sin(s.ph") for m in re.finditer(r"\w*\(?s\.ph\b", sql))
    event_sql, k = correlations.event_sums_sql(record, spec, both, 100)
    values = _accumulated(event_sql)
    assert k == len(values) == len(correlations.SHOWER_KEYS)
    assert [v for v in values if "ph" in v] == ["cos(ph)", "sin(ph)"]
    assert "phi" not in correlations.HIT_KEYS + correlations.SHOWER_KEYS


def test_the_jackknife_groups_are_events_up_to_64(record):
    spec = filters.build(record)
    both = showers_mod.of(record, "both")
    few, _, _ = correlations.hit_scan_sql(record, spec, both, "local", "linear", 64)
    many, _, _ = correlations.hit_scan_sql(record, spec, both, "local", "linear", 65)
    assert "p.event_number AS g" in few
    assert f"(p.event_number % {jackknife.MAX_GROUPS}) AS g" in many


def test_two_events_are_below_every_gate_and_say_so(cursor, record):
    spec = filters.build(record)
    body, a = correlations.compute(cursor, record, spec)
    payload = envelope(ApiMeta(table_name=record.table_name), **body, filter=spec.as_dict())
    contract_check.check(payload, "correlations")
    assert density.wire_size(payload) < density.RESPONSE_LIMIT
    assert (body["n_events"], body["groups"], body["dof"]) == (2, 2, None)
    assert body["n_showers"] == 4 and body["n_hits"] == a.selection.n_hits > 0
    for row in body["matrix"]:
        for cell in row:
            assert cell["r"] is None and cell["ci95"] is None and cell["mardia"] is None
    assert body["method"] == ("event-grouped jackknife, 2 groups (one event each); too few for "
                              "an interval, which needs 4")
    assert body["interval"] == "none: a correlation needs at least 3 events; this selection has 2"
    assert body["weak"] is True
    assert any("at least 3 events" in note for note in body["notes"])


def test_variables_scale_and_weightings(cursor, record):
    spec = filters.build(record)
    keys = {"local": ["u", "v", "w"], "trans": ["dx", "dy", "dz"], "lab": ["x", "y", "z"]}
    for coord_system in FRAMES:
        for energy_scale, energy in (("linear", "energy"), ("log10", "log10_energy")):
            body, _ = correlations.compute(cursor, record, spec, coord_system=coord_system,
                                           energy_scale=energy_scale)
            variables = body["variables"]
            assert [v["key"] for v in variables] == keys[coord_system] + [energy, "p", "theta", "phi"]
            assert [v["level"] for v in variables] == ["hit"] * 4 + ["shower"] * 3
            assert [v["circular"] for v in variables] == [False] * 6 + [True]
            assert (body["coord_system"], body["energy_scale"]) == (coord_system, energy_scale)
    assert body["scale"] == {"palette": "puor", "diverging": True, "vmin": -1, "vmax": 1,
                             "label": "Pearson r"}
    weighting = [[cell["weighting"] for cell in row] for row in body["matrix"]]
    assert weighting[0][1] == "hit"
    assert weighting[0][4] == weighting[5][2] == weighting[6][0] == "hit_shower"
    assert weighting[4][5] == weighting[5][6] == weighting[6][6] == "shower_by_hits"
    assert set(body["weightings"]) == {"hit", "hit_shower", "shower_by_hits"}
    assert all(cell["hatched"] == (6 in (i, j))
               for i, row in enumerate(body["matrix"]) for j, cell in enumerate(row))


def test_every_note_sets_negative_numbers_with_the_minus_sign(cursor, record):
    from calosrv.text import signed_hyphens

    body, _ = correlations.compute(cursor, record, filters.build(record), coord_system="trans")
    for text in (*body["notes"], body["method"], body["interval"], *body["weightings"].values()):
        assert signed_hyphens(text) == [], text


def test_mardia_value_handles_two_azimuths():
    # Many azimuths: the closed form.
    assert correlations.mardia_value(0.3, 0.4, 0.1) == pytest.approx(
        jackknife.mardia_r(0.3, 0.4, 0.1))
    # Two azimuths: cos and sin collinear, rounding a hair from ±1 - the plain |r|.
    assert correlations.mardia_value(-0.5, 0.5, -1.0 + 1e-15) == pytest.approx(0.5)
    # Two azimuths mirrored about the x axis: cos has no spread, sin carries it.
    assert correlations.mardia_value(float("nan"), -0.25, float("nan")) == pytest.approx(0.25)
    # One azimuth, or a variable with no spread: undefined.
    assert correlations.mardia_value(float("nan"), float("nan"), float("nan")) is None


def test_unknown_parameters_are_refused_naming_the_field(cursor, record):
    spec = filters.build(record)
    for kwargs, field, error in (
        ({"coord_system": "canonical"}, "coord_system", ValidationError),
        ({"energy_scale": "ln"}, "energy_scale", ValidationError),
        ({"shower": "c"}, "shower", ValidationError),
    ):
        with pytest.raises(error) as raised:
            correlations.compute(cursor, record, spec, **kwargs)
        assert raised.value.extra["field"] == field


def test_a_drag_preview_reads_the_sample_and_keeps_the_shower_cells_exact(cursor, record):
    assert record.has_sample
    spec = filters.build(record)
    exact, a = correlations.compute(cursor, record, spec)
    preview, b = correlations.compute(cursor, record, spec, sampled=True, sample_percent=10.0)
    sample = hit_sql.proj_table(record, sampled=True)
    n_sample = cursor.execute(f"SELECT count(*) FROM {sample}").fetchone()[0]
    assert preview["n_hits"] == n_sample < exact["n_hits"]
    # The per-shower sums come from the event table, sampled or not.
    assert np.array_equal(b.shower_w.s, a.shower_w.s) and np.array_equal(b.shower_u.q, a.shower_u.q)
    assert preview["n_events"] == exact["n_events"]
    assert any(note.startswith("Drag preview: the hit cells come from the 10% Bernoulli sample")
               for note in preview["notes"])
    assert not any(note.startswith("Drag preview") for note in exact["notes"])


def test_an_empty_selection_is_served_and_says_so(cursor, record):
    spec = filters.build(record, e1_min=1e6, e1_max=2e6)
    body, a = correlations.compute(cursor, record, spec)
    payload = envelope(ApiMeta(table_name=record.table_name), **body, filter=spec.as_dict())
    contract_check.check(payload, "correlations")
    assert (body["n_events"], body["n_hits"], body["groups"], body["dof"]) == (0, 0, 0, None)
    assert body["method"] == "event-grouped jackknife: no events in this selection"
    assert body["notes"] == ["No events with hits match the current selection."]
