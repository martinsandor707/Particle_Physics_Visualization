"""The hits_all_models ingest: header rules, the Parquet archive, the derived tables.

Everything here runs on the 2-event demonstration file through the real
pipeline (the session `ingested` fixture), plus a few throwaway experiments
ingested beside it. The production-scale contracts - split cells, 'A+B' rows,
NULL shower-A centroids - are asserted on the real-data fixture when it exists.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import numpy as np
import pytest

from calosrv.db import archive, naming, registry
from calosrv.db.ddl import (
    COORD_SYSTEMS, HIT_COLUMN_NAMES, NETWORK_FRAME, PROJ_COLUMN_NAMES, frame_code,
)
from calosrv.db.naming import quote
from calosrv.errors import EventRangeCollisionError, IngestError
from calosrv.ingest import csv_spec, pipeline

from conftest import FIXTURE_CSV, SEED_CSV


def _write_csv(path: Path, header: list[str], rows: list[list[str]] | None = None) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows or [])
    return path


# ---------------------------------------------------------------- header --


def test_the_header_must_be_the_99_column_schema(tmp_path):
    missing = _write_csv(tmp_path / "missing.csv", list(HIT_COLUMN_NAMES[:-1]))
    with pytest.raises(IngestError, match="does not match the hits_all_models input schema"):
        csv_spec.validate_header(missing)


def test_a_reordered_header_is_refused_because_the_reader_is_positional(tmp_path):
    names = list(HIT_COLUMN_NAMES)
    names[3], names[4] = names[4], names[3]
    with pytest.raises(IngestError, match="different order"):
        csv_spec.validate_header(_write_csv(tmp_path / "order.csv", names))


def test_a_retired_v37_header_is_named_as_such(tmp_path):
    v37 = ["event_number", "overlap", "cellID", "x", "y", "z", "energy", "particle_origin",
           "gradcam", "gradcam_energy", "voxel_fA_pred", "voxel_fA_true"]
    with pytest.raises(IngestError, match="retired v37"):
        csv_spec.validate_header(_write_csv(tmp_path / "v37.csv", v37))


def test_the_demonstration_header_matches_the_schema():
    csv_spec.validate_header(SEED_CSV)


# --------------------------------------------------------------- archive --


def test_the_archive_holds_every_source_row_in_typed_parquet(ingested):
    settings, name = ingested["settings"], ingested["table"]
    manifest = archive.read_manifest(settings, name)
    assert manifest is not None and len(manifest.parts) == 1
    assert manifest.rows == csv_spec.count_data_rows(SEED_CSV) == 1000
    part = archive.part_paths(settings, name)[0]
    assert part.is_file() and part.suffix == ".parquet"
    con = duckdb.connect()
    types = dict(con.execute(
        f"SELECT name, type || coalesce('/' || converted_type, '') "
        f"FROM parquet_schema('{part}')"
    ).fetchall())
    assert types["x"] == "FLOAT"
    assert types["energy"] == "DOUBLE"
    assert types["incoming_momentum_bin_A"] == "INT32/UINT_8"
    assert types["segmentation_local_shapcam"] == "FLOAT"
    groups = con.execute(
        f"SELECT max(row_group_num_rows) FROM parquet_metadata('{part}')"
    ).fetchone()[0]
    assert groups <= archive.ROW_GROUP_SIZE


def test_the_archive_is_readable_while_the_server_holds_the_database(ingested):
    """The point of the archive: another connection can read it at the same time."""
    part = archive.part_paths(ingested["settings"], ingested["table"])[0]
    other = duckdb.connect()
    assert other.execute(f"SELECT count(*) FROM '{part}'").fetchone()[0] == 1000


def test_the_registry_records_the_archive_and_the_schema(record):
    assert record.schema_name == "hits_all_models"
    assert record.schema_version == 1
    assert record.archive_dir == f"archive/{record.table_name}"
    assert record.archive_parts == 1 and record.archive_rows == 1000
    assert record.frame_bounds is not None
    assert set(record.frame_bounds.axes) == {"xt", "yt", "xl", "yl", "zl"}
    assert record.frame_bounds.layer_pitch_mm == pytest.approx(20.5)
    assert record.ingest_report["verification"]["ok"] is True


def test_no_verification_check_fails_on_the_demonstration_file(ingested):
    checks = ingested["verification"].checks
    assert "FAIL" not in checks.values(), checks
    for key in ("archive_row_count", "p0_constancy", "per_shower_constancy",
                "local_rotation", "trans_layers", "truth_consistency", "finite_model_columns"):
        assert checks[key] == "PASS", key


# ------------------------------------------------------------ projection --


def test_the_projection_table_has_the_contracted_columns(cursor, record):
    proj = naming.proj_table(record.table_name)
    columns = [r[0] for r in cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ? "
        "ORDER BY ordinal_position", [proj]).fetchall()]
    assert tuple(columns) == PROJ_COLUMN_NAMES
    assert "ge" not in columns and "fa_true" not in columns


def test_projection_frame_columns_reproduce_the_archive(cursor, record, ingested):
    hits = archive.relation(ingested["settings"], record.table_name)
    proj = quote(naming.proj_table(record.table_name))
    direct = cursor.execute(
        f"SELECT count(*) FILTER (WHERE particle_origin = 'A'), "
        f"count(*) FILTER (WHERE particle_origin = 'B'), sum(CAST(x_trans AS DOUBLE)), "
        f"sum(CAST(z_local AS DOUBLE)), sum(CAST(energy_trans_shapcam AS DOUBLE)) FROM {hits}"
    ).fetchone()
    derived = cursor.execute(
        f"SELECT count(*) FILTER (WHERE org = 0), count(*) FILTER (WHERE org = 1), "
        f"sum(CAST(xt AS DOUBLE)), sum(CAST(zl AS DOUBLE)), sum(CAST(sc_en_trn AS DOUBLE)) "
        f"FROM {proj}"
    ).fetchone()
    assert direct[:2] == derived[:2]
    assert derived[2:] == pytest.approx(direct[2:], rel=1e-12)


def test_the_own_shower_layer_is_a_whole_number_of_pitches(cursor, record, ingested):
    hits = archive.relation(ingested["settings"], record.table_name)
    pitch = record.frame_bounds.layer_pitch_mm
    z_trans = np.array([r[0] for r in cursor.execute(
        f"SELECT DISTINCT z_trans FROM {hits} ORDER BY 1").fetchall()])
    kt = np.array([r[0] for r in cursor.execute(
        f"SELECT DISTINCT kt FROM {quote(naming.proj_table(record.table_name))} ORDER BY 1"
    ).fetchall()])
    np.testing.assert_allclose(kt * pitch, z_trans, atol=1e-3)


# ---------------------------------------------------------------- events --


def test_event_p0_is_the_own_shower_translation(cursor, record, ingested):
    hits = archive.relation(ingested["settings"], record.table_name)
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"""SELECT e.event_number, e.p0ax, e.p0bx, e.p0ay, e.p0by,
                   h.ax, h.bx, h.ay, h.by
            FROM {event} e JOIN (
                SELECT event_number,
                       avg(x - x_trans) FILTER (WHERE particle_origin = 'A') AS ax,
                       avg(x - x_trans) FILTER (WHERE particle_origin = 'B') AS bx,
                       avg(y - y_trans) FILTER (WHERE particle_origin = 'A') AS ay,
                       avg(y - y_trans) FILTER (WHERE particle_origin = 'B') AS by
                FROM {hits} GROUP BY event_number) h USING (event_number)"""
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row[1:5] == pytest.approx(row[5:9], abs=1e-3)


@pytest.mark.parametrize("coord", COORD_SYSTEMS)
def test_per_frame_segmentation_statistics_equal_a_direct_scan(cursor, record, ingested, coord):
    hits = archive.relation(ingested["settings"], record.table_name)
    event = quote(naming.event_table(record.table_name))
    frame, code = NETWORK_FRAME[coord], frame_code(coord)
    p = f"CAST(segmentation_{frame}_pred AS DOUBLE)"
    t = f"CAST(segmentation_{frame}_true AS DOUBLE)"
    direct = cursor.execute(
        f"SELECT sum(energy * {p}), sum(energy * abs({p} - {t})), "
        f"count(*) FILTER (WHERE ({p} >= 0.5) = ({t} >= 0.5)) FROM {hits}"
    ).fetchone()
    stored = cursor.execute(
        f"SELECT sum(e_a_pred_{code}), sum(sum_wabs_err_{code}), sum(n_correct_{code}) "
        f"FROM {event}"
    ).fetchone()
    assert stored[:2] == pytest.approx(direct[:2], rel=1e-12)
    assert stored[2] == direct[2]


def test_per_shower_network_outputs_are_split_by_origin(cursor, record, ingested):
    hits = archive.relation(ingested["settings"], record.table_name)
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"""SELECT e.en_pred_a_trn, e.th_pred_b_loc, e.en_true_a, e.th_true_b,
                   h.en_a, h.th_b, h.true_a, h.theta_b
            FROM {event} e JOIN (
                SELECT event_number,
                       max(energy_trans_pred) FILTER (WHERE particle_origin = 'A') AS en_a,
                       max(angle_local_pred) FILTER (WHERE particle_origin <> 'A') AS th_b,
                       max(incoming_momentum_A) AS true_a,
                       max(incoming_theta_B) AS theta_b
                FROM {hits} GROUP BY event_number) h USING (event_number)"""
    ).fetchall()
    for row in rows:
        assert row[:2] == pytest.approx(row[4:6], rel=1e-6)
        assert row[2] == pytest.approx(row[6], abs=1e-5)
        assert row[3] == pytest.approx(row[7], abs=2e-6)


# ------------------------------------------------- append and rebuild --


@pytest.fixture(scope="module")
def spare(ingested):
    """A second experiment in the same database, for append and rebuild."""
    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        pipeline.run_ingest(con, settings, "spare_experiment", SEED_CSV, build_sample=False)
    yield {"database": database, "settings": settings, "name": "spare_experiment"}
    from calosrv.db.bootstrap import drop_experiment

    with database.write_lock() as con:
        drop_experiment(con, "spare_experiment", settings)


def test_an_append_that_reuses_event_numbers_is_refused(spare):
    with spare["database"].write_lock() as con:
        with pytest.raises(EventRangeCollisionError) as info:
            pipeline.run_ingest(con, spare["settings"], spare["name"], SEED_CSV,
                                mode="append", build_sample=False)
    assert info.value.extra.get("suggested_offset") == 2
    manifest = archive.read_manifest(spare["settings"], spare["name"])
    assert len(manifest.parts) == 1, "a refused append must not leave a part behind"


def test_an_offset_append_adds_a_part_and_the_rows(spare):
    with spare["database"].write_lock() as con:
        result = pipeline.run_ingest(con, spare["settings"], spare["name"], SEED_CSV,
                                     mode="append", event_offset=2, build_sample=False)
    assert result.ok
    assert result.record.archive_parts == 2
    assert result.record.archive_rows == 2000
    assert result.n_events == 4


def test_rebuild_reproduces_the_derived_tables_without_the_csv(spare):
    name = spare["name"]
    event = quote(naming.event_table(name))
    with spare["database"].write_lock() as con:
        before = con.execute(f"SELECT sum(e_dep), sum(e_a_pred_loc), count(*) FROM {event}").fetchone()
        result = pipeline.rebuild(con, spare["settings"], name, build_sample=False)
        after = con.execute(f"SELECT sum(e_dep), sum(e_a_pred_loc), count(*) FROM {event}").fetchone()
    assert result.ok
    assert after == pytest.approx(before, rel=1e-12)


def test_deleting_an_experiment_removes_its_archive(ingested):
    from calosrv.db.bootstrap import drop_experiment

    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        pipeline.run_ingest(con, settings, "doomed_experiment", SEED_CSV, build_sample=False)
        path = archive.archive_path(settings, "doomed_experiment")
        assert path.is_dir()
        assert drop_experiment(con, "doomed_experiment", settings) is True
        assert registry.get_experiment(con, "doomed_experiment") is None
    assert not path.exists()


# ------------------------------------------ the real-data fixture, if present --


@pytest.fixture(scope="module")
def fixture_experiment(ingested):
    if not FIXTURE_CSV.is_file():
        pytest.skip(f"real-data fixture not present at {FIXTURE_CSV}")
    database, settings = ingested["database"], ingested["settings"]
    with database.write_lock() as con:
        if registry.get_experiment(con, "fixture_experiment") is None:
            pipeline.run_ingest(con, settings, "fixture_experiment", FIXTURE_CSV)
    with database.read_cursor() as con:
        yield registry.require_ready(con, "fixture_experiment")


def test_split_cells_are_counted_once(cursor, fixture_experiment):
    event = quote(naming.event_table(fixture_experiment.table_name))
    rows, cells, split, bad = cursor.execute(
        f"SELECT sum(n_hits), sum(n_cells), sum(n_split_cells), sum(chk_bad_split) FROM {event}"
    ).fetchone()
    assert split > 0
    assert cells == rows - split
    assert bad == 0


def test_an_event_without_shower_a_has_no_separation(cursor, fixture_experiment):
    event = quote(naming.event_table(fixture_experiment.table_name))
    rows = cursor.execute(
        f"SELECT d, cax, en_pred_a_abs, n_a_rows FROM {event} WHERE n_a_rows = 0"
    ).fetchall()
    assert rows, "the fixture must carry at least one event without shower A"
    for d, cax, en_a, n_a in rows:
        assert d is None and cax is None and en_a is None and n_a == 0


def test_a_plus_b_rows_carry_shower_b_values_and_sit_at_the_origin(cursor, fixture_experiment, ingested):
    hits = archive.relation(ingested["settings"], fixture_experiment.table_name)
    row = cursor.execute(
        f"""SELECT count(*), max(abs(x_trans) + abs(y_trans) + abs(z_trans)
                              + abs(x_local) + abs(y_local) + abs(z_local))
            FROM {hits} WHERE particle_origin = 'A+B'"""
    ).fetchone()
    assert row[0] > 0
    assert row[1] == 0
