"""Ingest of the two single-shower schemas, and the derived tables every hit kind gains.

Runs on files written from committed data (``synthetic_single_shower.py``),
into the session's ingested database under their own names, so it always
runs. The real electron cuts (``make_single_shower_fixture.py``) add a parity
check on the producer's own aggregate when they are present.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import core_port
import synthetic_single_shower
from calosrv.db import archive, ddl, group1, naming, registry, schemas
from calosrv.db.naming import quote
from calosrv.errors import IngestError
from calosrv.ingest import feature_parity, pipeline, verify as verify_mod, verify_single
from calosrv.stats import profile as profile_stats

REPO = Path(__file__).resolve().parent.parent
REAL_HITS = REPO / "electron_hits_fixture.csv"
REAL_EVENTS = REPO / "electron_events_fixture.csv"

HITS, EVENTS = "single_hits_test", "single_events_test"


@pytest.fixture(scope="module")
def single(ingested, tmp_path_factory):
    """The synthetic hit file and its aggregate, ingested; and the files themselves."""
    folder = tmp_path_factory.mktemp("single-shower")
    hits_csv, events_csv = folder / "hits.csv", folder / "aggr.csv"
    info = synthetic_single_shower.write(hits_csv)
    aggregated = synthetic_single_shower.write_aggregated(hits_csv, events_csv)
    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        hits = pipeline.run_ingest(con, settings, HITS, hits_csv, force_reingest=True)
        events = pipeline.run_ingest(con, settings, EVENTS, events_csv, force_reingest=True)
    return {"database": database, "settings": settings, "info": info, "aggregated": aggregated,
            "hits": hits, "events": events, "hits_csv": hits_csv, "events_csv": events_csv,
            "folder": folder}


def _q(single, sql, params=None):
    with single["database"].read_cursor() as con:
        return con.execute(sql, params or {}).fetchall()


# ------------------------------------------------------------------- ingest --

def test_both_kinds_ingest_and_verify(single):
    hits, events = single["hits"], single["events"]
    assert hits.ok and events.ok, (hits.warnings, events.warnings)
    assert hits.record.kind == ddl.KIND_SINGLE_HITS and hits.record.derived_version == 1
    assert events.record.kind == ddl.KIND_SINGLE_EVENTS and events.record.derived_version == 1
    assert hits.n_events == single["info"]["n_events"]
    assert events.n_events == single["aggregated"]["n_events"] == hits.n_events - 1
    assert events.n_hits == 0 and events.record.lattice is None
    assert (hits.record.e2_min, hits.record.d_min, hits.record.n_events_no_d) == (None, None, 0)


def test_required_tables_exist_per_kind(single):
    with single["database"].read_cursor() as con:
        tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    for name, record in ((HITS, single["hits"].record), (EVENTS, single["events"].record)):
        required = schemas.required_tables(name, record.kind, record.derived_version,
                                           record.has_sample)
        assert required <= tables, required - tables
    assert naming.proj_table(EVENTS) not in tables


def test_verification_reports_the_species_and_rules(single):
    v = single["hits"].verification
    for check in ("species_domain", "unique_cells", "local_rotation", "p0_definition",
                  "group1_partition", "layers_consistency", "profiles_conservation"):
        assert v.checks[check] == "PASS", check
    notices = " ".join(v.notices)
    assert "have no primary-tagged row" in notices
    assert "⌊incoming_momentum⌋ on every row" in notices
    assert "z_local < −1e−06 mm" in notices          # U+2212, never a hyphen
    assert "1 event(s) have a single hit" in notices
    caps = single["hits"].record.capabilities
    assert caps["profiles"]["k"] == 6 and caps["profiles"]["k_z"] == 2
    assert {s["name"] for s in caps["species"]["top"]} >= {"e-", "gamma", "e+"}
    assert caps["momentum_bins"]["rule"] == "floor(p)"
    label = single["events"].record.capabilities["label"]
    assert label["holds"] and label["rule"] == "p >= 2 GeV"


def test_aggregate_label_and_names(single):
    rows = _q(single, f"SELECT e1, energy_class, n_hits, e_dep FROM {quote(naming.event_table(EVENTS))}")
    assert all(cls == int(p >= 2.0) for p, cls, *_ in rows)
    assert all(n >= 2 and e > 0 for *_, n, e in rows)


# ------------------------------------------------------------ Group-1 parity --

def test_group1_rebuilds_the_producers_features(single):
    with single["database"].read_cursor() as con:
        report = feature_parity.compare(con, HITS, EVENTS)
    assert report.ok, report.as_dict()
    assert report.n_hits_only == 1 and report.n_events_only == 0
    assert max(report.max_rel.values()) < 1e-12


def test_two_shower_group1_against_core_port(ingested):
    """Each shower of the demonstration file, through the producer's own function.

    The two-shower schema stores coordinates as 32-bit REAL, so the port is
    fed the values the archive holds, not the CSV's longer text.
    """
    from conftest import SEED_CSV

    df = pd.read_csv(SEED_CSV, float_precision="round_trip")
    df = df[df.energy > 0]
    for column, sql_type in ddl.HIT_COLUMNS:
        if sql_type == "REAL" and column in df:
            df[column] = df[column].astype(np.float32).astype(np.float64)
    with ingested["database"].read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
        assert record.derived_version == 2
        event = quote(naming.event_table(ingested["table"]))
        for shower, member in (("a", df.particle_origin == "A"), ("b", df.particle_origin != "A")):
            part = df[member].rename(columns={f"incoming_momentum_{shower.upper()}": "incoming_momentum"})
            expected = core_port.calc_all_features_v3(part).set_index("event_id")
            for code, suffix in ddl.FEATURE_SUFFIX.items():
                for feature in group1.FEATURES:
                    got = dict(con.execute(
                        f"SELECT event_number, {group1.feature_sql(feature, code, shower)} "
                        f"FROM {event} WHERE n_hits_{shower} > 0").fetchall())
                    for event_id, value in expected[f"{feature}{suffix}"].items():
                        assert got[event_id] == pytest.approx(value, rel=1e-9, abs=1e-9), \
                            (shower, feature, suffix, event_id)


# ------------------------------------------------------- layers and profiles --

def test_layers_hold_each_showers_energy_and_cells(single):
    rows = _q(single, f"""
        SELECT max(abs(l.e - e.e_dep_a) / e.e_dep_a), count(*) FILTER (WHERE l.c <> e.n_cells_a)
        FROM (SELECT event_number, sum(e_dep) e, sum(n_cells) c
              FROM {quote(naming.layers_table(HITS))} GROUP BY 1) l
        JOIN {quote(naming.event_table(HITS))} e USING (event_number)""")
    assert rows[0][0] < 1e-12 and rows[0][1] == 0


def test_profile_sd_from_sql_sums_matches_numpy(single):
    """The C7 contract: per-shower fractions summed in SQL give numpy's ddof=1 SD."""
    profiles = quote(naming.profiles_table(HITS))
    event = quote(naming.event_table(HITS))
    for axis in (ddl.PROFILE_AXIS_W, ddl.PROFILE_AXIS_R):
        sums = _q(single, f"""
            SELECT p.bin, sum(p.e / s.e_dep_a), sum((p.e / s.e_dep_a) ** 2)
            FROM {profiles} p JOIN {event} s USING (event_number)
            WHERE p.axis = {axis} GROUP BY p.bin ORDER BY p.bin""")
        n = _q(single, f"SELECT count(*) FROM {event}")[0][0]
        rows = _q(single, f"""SELECT p.event_number, p.bin, p.e / s.e_dep_a
                              FROM {profiles} p JOIN {event} s USING (event_number)
                              WHERE p.axis = {axis}""")
        bins = [b for b, *_ in sums]
        index = {b: i for i, b in enumerate(bins)}
        events = {e: i for i, e in enumerate(sorted({r[0] for r in rows}))}
        dense = np.zeros((n, len(bins)))
        for e, b, f in rows:
            dense[events[e], index[b]] = f
        est = profile_stats.profile_estimate(np.array([s[1] for s in sums]),
                                             np.array([s[2] for s in sums]), n)
        assert est.mean == pytest.approx(dense.mean(axis=0), abs=1e-15)
        assert est.sd == pytest.approx(dense.std(axis=0, ddof=1), rel=1e-9, abs=1e-12)
        assert dense.sum(axis=1) == pytest.approx(np.ones(n), rel=1e-12)


def test_negative_depth_part_matches_group1(single):
    rows = _q(single, f"""
        SELECT max(abs(p.n - e.w_neg_energy_a) / e.e_dep_a)
        FROM (SELECT event_number, sum(e_wneg) n FROM {quote(naming.profiles_table(HITS))}
              WHERE axis = 0 GROUP BY 1) p
        JOIN {quote(naming.event_table(HITS))} e USING (event_number)""")
    assert rows[0][0] < 1e-12


# ------------------------------------------------------- CSV against Parquet --

def _as_parquet(single, csv_path: Path, schema: schemas.InputSchema) -> Path:
    """The same file as Parquet, written the way another tool would: shuffled, DOUBLE, BOOLEAN."""
    from calosrv.ingest import csv_spec

    target = csv_path.with_suffix(".parquet")
    cols = []
    for c, t in reversed(schema.columns):
        if c == "is_secondary":
            cols.append(f"CAST({c} AS BOOLEAN) AS {c}")
        elif t == "VARCHAR":
            cols.append(f"coalesce({c}, '') AS {c}")
        elif t in ("REAL", "DOUBLE"):
            cols.append(f"CAST({c} AS DOUBLE) AS {c}")
        else:
            cols.append(f"CAST({c} AS BIGINT) AS {c}")
    with single["database"].read_cursor() as con:
        con.execute(f"COPY (SELECT {', '.join(cols)} FROM ({csv_spec.select_sql(csv_path, 0, schema)}) "
                    f"ORDER BY hash({schema.event_key})) TO '{target}' (FORMAT parquet)")
    return target


@pytest.mark.parametrize("kind", ["hits", "events"])
def test_csv_and_parquet_sources_give_identical_tables(single, kind):
    schema = schemas.STANDALONE_HITS if kind == "hits" else schemas.STANDALONE_EVENTS
    csv_name = HITS if kind == "hits" else EVENTS
    source = _as_parquet(single, single[f"{kind}_csv"], schema)
    twin = f"{csv_name}_pq"
    with single["database"].write_lock() as con:
        con.execute("SET threads = 1")
        try:
            result = pipeline.run_ingest(con, single["settings"], twin, source, force_reingest=True)
            assert result.ok
            tables = [t for t in naming.all_tables(csv_name)
                      if con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = $t",
                                     {"t": t}).fetchone()[0]]
            for table in tables:
                other = table.replace(csv_name, twin, 1)
                for a, b in ((table, other), (other, table)):
                    diff = con.execute(f"SELECT count(*) FROM (SELECT * FROM {quote(a)} "
                                       f"EXCEPT ALL SELECT * FROM {quote(b)})").fetchone()[0]
                    assert diff == 0, (table, a, b)
            parts = [archive.part_paths(single["settings"], n) for n in (csv_name, twin)]
            diff = con.execute(
                f"SELECT count(*) FROM (SELECT * FROM {archive.relation_sql(parts[0])} "
                f"EXCEPT ALL SELECT * FROM {archive.relation_sql(parts[1])})").fetchone()[0]
            assert diff == 0
        finally:
            con.execute(f"SET threads = {single['settings'].threads}")


def test_single_shower_archive_is_sorted_by_event(single):
    paths = archive.part_paths(single["settings"], HITS)
    with single["database"].read_cursor() as con:
        stats = con.execute(
            f"SELECT stats_min, stats_max FROM parquet_metadata('{paths[0]}') "
            "WHERE path_in_schema = 'event_number' ORDER BY row_group_id").fetchall()
        ordered = con.execute(
            f"SELECT bool_and(k >= lk) FROM (SELECT event_number k, lag(event_number) OVER () lk "
            f"FROM {archive.relation_sql(paths)}) WHERE lk IS NOT NULL").fetchone()[0]
    assert ordered
    assert all(int(a[1]) <= int(b[0]) for a, b in zip(stats, stats[1:]))


# ------------------------------------------------------------------ refusals --

def test_an_append_of_another_schema_is_refused(single):
    with single["database"].write_lock() as con:
        with pytest.raises(IngestError, match="Cannot append a standalone_events v3 file"):
            pipeline.run_ingest(con, single["settings"], HITS, single["events_csv"],
                                mode="append", event_offset=10_000)
        assert registry.get_experiment(con, HITS).status == registry.STATUS_READY


def test_duplicate_event_ids_are_refused(single):
    doubled = single["folder"] / "doubled.csv"
    lines = single["events_csv"].read_text().splitlines()
    doubled.write_text("\n".join([*lines, lines[1]]) + "\n")
    with single["database"].write_lock() as con:
        with pytest.raises(IngestError, match="event_id is not unique"):
            pipeline.run_ingest(con, single["settings"], "doubled_events", doubled)


# ------------------------------------------------------------------- rebuild --

def test_rebuild_commits_and_a_failed_rebuild_rolls_back(single, monkeypatch):
    settings = single["settings"]
    with single["database"].write_lock() as con:
        before = con.execute(f"SELECT count(*), sum(e) FROM {quote(naming.profiles_table(HITS))}").fetchone()
        result = pipeline.rebuild_atomic(con, settings, HITS)
        assert result.ok
        after = con.execute(f"SELECT count(*), sum(e) FROM {quote(naming.profiles_table(HITS))}").fetchone()
        assert after[0] == before[0] and after[1] == pytest.approx(before[1], rel=1e-12)

        original = verify_mod.check_derived

        def failing(result, *args, **kwargs):
            original(result, *args, **kwargs)
            result.fail("injected", "a failure injected by the test")

        monkeypatch.setattr(verify_single, "check_derived", failing)
        failed = pipeline.rebuild_atomic(con, settings, HITS)
        assert not failed.ok
        record = registry.get_experiment(con, HITS)
        assert record.status == registry.STATUS_READY and record.error is None
        kept = con.execute(f"SELECT count(*), sum(e) FROM {quote(naming.profiles_table(HITS))}").fetchone()
        assert kept[0] == before[0]


# ---------------------------------------------------------------- real cuts --

@pytest.mark.skipif(not (REAL_HITS.is_file() and REAL_EVENTS.is_file()),
                    reason="run tests/make_single_shower_fixture.py to cut the electron files")
def test_real_electron_cut_matches_the_producers_aggregate(ingested):
    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        hits = pipeline.run_ingest(con, settings, "real_hits_cut", REAL_HITS, force_reingest=True)
        events = pipeline.run_ingest(con, settings, "real_events_cut", REAL_EVENTS,
                                     force_reingest=True)
        assert hits.ok and events.ok, (hits.warnings, events.warnings)
        report = feature_parity.compare(con, "real_hits_cut", "real_events_cut")
    assert report.ok, report.as_dict()
    assert report.n_events_only == 0 and report.n_hits_only >= 1
    assert all(math.isfinite(v) and v < 1e-12 for v in report.max_rel.values())
