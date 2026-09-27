"""Parquet sources: accepted, checked before anything is dropped, and read like a CSV.

The ingested demonstration experiment's own archive part is a canonical
99-column Parquet file, so every variant here is cut from it with DuckDB -
reordered, retyped, with a column missing or NaN written in - and fed back
through the real pipeline. The central property is equivalence: a Parquet
file carrying the same data as a CSV must give the same archive and the same
derived tables.
"""

from __future__ import annotations

import contextlib
import gzip
import shutil
from pathlib import Path

import duckdb
import pytest

from calosrv.db import archive, naming, registry
from calosrv.db.ddl import HIT_COLUMN_NAMES, NULLABLE_COLUMNS
from calosrv.db.naming import quote
from calosrv.errors import IngestError
from calosrv.ingest import formats, parquet_spec, pipeline

from conftest import FIXTURE_CSV, SEED_CSV


@pytest.fixture(scope="module")
def part(ingested) -> Path:
    """The demonstration experiment's archive part: a 99-column Parquet file."""
    return archive.part_paths(ingested["settings"], ingested["table"])[0]


def _variant(tmp_path: Path, part: Path, name: str, select: str = "*",
             options: str = "FORMAT parquet") -> Path:
    """A copy of the part, rewritten by ``SELECT {select}``."""
    out = tmp_path / name
    duckdb.connect().execute(
        f"COPY (SELECT {select} FROM read_parquet('{part}')) TO '{out}' ({options})"
    )
    return out


@contextlib.contextmanager
def _experiment(ingested, name: str, source: Path, **kwargs):
    """Ingest ``source`` as ``name`` and drop it again afterwards."""
    from calosrv.db.bootstrap import drop_experiment

    database, settings = ingested["database"], ingested["settings"]
    try:
        with database.write_lock() as con:
            result = pipeline.run_ingest(con, settings, name, source, build_sample=False,
                                         **kwargs)
        yield result
    finally:
        with database.write_lock() as con:
            drop_experiment(con, name, settings)


def _differs(con, left: str, right: str) -> int:
    """Rows in either table that the other lacks, duplicates counted."""
    a, b = quote(left), quote(right)
    return int(con.execute(
        f"SELECT (SELECT count(*) FROM (SELECT * FROM {a} EXCEPT ALL SELECT * FROM {b})) "
        f"+ (SELECT count(*) FROM (SELECT * FROM {b} EXCEPT ALL SELECT * FROM {a}))"
    ).fetchone()[0])


def _types(path: Path) -> list[tuple]:
    return duckdb.connect().execute(
        f"SELECT name, type, converted_type FROM parquet_schema('{path}') WHERE name <> 'duckdb_schema'"
    ).fetchall()


# ------------------------------------------------------------- equivalence --


def test_a_parquet_copy_of_the_data_gives_the_same_archive_and_tables(ingested, part, tmp_path):
    source = tmp_path / "roundtrip.parquet"
    shutil.copyfile(part, source)
    with _experiment(ingested, "parquet_roundtrip", source) as result:
        assert result.ok, result.warnings
        assert result.record.ingest_report["source"]["format"] == "parquet"
        assert result.record.ingest_report["source"]["notices"] == []
        settings = ingested["settings"]
        new_part = archive.part_paths(settings, "parquet_roundtrip")[0]
        assert _types(new_part) == _types(part)
        manifest = archive.read_manifest(settings, "parquet_roundtrip")
        assert [p.source_format for p in manifest.parts] == ["parquet"]
        with ingested["database"].read_cursor() as con:
            for table in (naming.proj_table, naming.event_table):
                assert _differs(con, table(ingested["table"]), table("parquet_roundtrip")) == 0


def test_columns_in_any_order_are_read_by_name(ingested, part, tmp_path):
    reordered = _variant(tmp_path, part, "reordered.parquet",
                         ", ".join(quote(c) for c in reversed(HIT_COLUMN_NAMES)))
    with _experiment(ingested, "parquet_reordered", reordered) as result:
        assert result.ok, result.warnings
        with ingested["database"].read_cursor() as con:
            assert _differs(con, naming.proj_table(ingested["table"]),
                            naming.proj_table("parquet_reordered")) == 0


def test_a_csv_part_and_a_parquet_append_share_one_archive(ingested, part, tmp_path):
    source = tmp_path / "append.parquet"
    shutil.copyfile(part, source)
    with _experiment(ingested, "mixed_formats", SEED_CSV):
        with ingested["database"].write_lock() as con:
            result = pipeline.run_ingest(con, ingested["settings"], "mixed_formats", source,
                                         mode="append", event_offset=2, build_sample=False)
        assert result.ok, result.warnings
        assert result.record.archive_parts == 2 and result.record.archive_rows == 2000
        manifest = archive.read_manifest(ingested["settings"], "mixed_formats")
        assert [p.source_format for p in manifest.parts] == ["csv", "parquet"]


def test_old_manifests_without_a_source_format_still_load(ingested):
    """Parts written before Parquet sources existed carry no format; they were CSV."""
    import json

    path = archive.archive_path(ingested["settings"], ingested["table"]) / archive.MANIFEST
    data = json.loads(path.read_text())
    for entry in data["parts"]:
        entry.pop("source_format", None)
    legacy = archive.Manifest(data["schema_name"], data["schema_version"],
                              [archive.ArchivePart(**p) for p in data["parts"]])
    assert [p.source_format for p in legacy.parts] == ["csv"]


# --------------------------------------------------------------- schema --


def test_a_missing_column_is_refused_by_name(part, tmp_path):
    source = _variant(tmp_path, part, "missing.parquet", "* EXCLUDE (energy)")
    with pytest.raises(IngestError, match="missing columns: energy"):
        parquet_spec.validate(duckdb.connect(), source)


def test_an_unexpected_column_is_refused_by_name(part, tmp_path):
    source = _variant(tmp_path, part, "extra.parquet", "*, 1.5 AS calibration_guess")
    with pytest.raises(IngestError, match="unexpected columns: calibration_guess"):
        parquet_spec.validate(duckdb.connect(), source)


def test_a_pandas_index_column_is_ignored_and_said_to_be(part, tmp_path):
    source = _variant(tmp_path, part, "pandas.parquet", "*, 0::BIGINT AS __index_level_0__")
    check = parquet_spec.validate(duckdb.connect(), source)
    assert any("__index_level_0__" in n for n in check.notices)


def test_a_retired_v37_file_is_named_as_such(tmp_path):
    v37 = tmp_path / "v37.parquet"
    duckdb.connect().execute(
        f"COPY (SELECT 0 AS event_number, 0.0 AS x, 0.5 AS voxel_fA_pred) TO '{v37}' "
        "(FORMAT parquet)"
    )
    with pytest.raises(IngestError, match="retired v37"):
        parquet_spec.validate(duckdb.connect(), v37)


@pytest.mark.parametrize("select, message", [
    ("* REPLACE (CAST(x AS VARCHAR) AS x)", "x is VARCHAR, expected a number"),
    ("* REPLACE (CAST(event_number AS DOUBLE) AS event_number)",
     "event_number is DOUBLE, expected an integer type"),
    ("* REPLACE (CAST(particle_origin = 'A' AS BOOLEAN) AS particle_origin)",
     "particle_origin is BOOLEAN, expected text"),
])
def test_a_column_of_the_wrong_type_is_refused(part, tmp_path, select, message):
    source = _variant(tmp_path, part, "typed.parquet", select)
    with pytest.raises(IngestError, match=message):
        parquet_spec.validate(duckdb.connect(), source)


def test_an_out_of_range_integer_is_refused_before_anything_is_dropped(ingested, part, tmp_path):
    source = _variant(
        tmp_path, part, "range.parquet",
        "* REPLACE (CAST(incoming_momentum_bin_A AS INTEGER) + 300 AS incoming_momentum_bin_A)",
    )
    with _experiment(ingested, "range_victim", SEED_CSV):
        before = archive.read_manifest(ingested["settings"], "range_victim")
        with pytest.raises(IngestError, match="do not fit UTINYINT"):
            with ingested["database"].write_lock() as con:
                pipeline.run_ingest(con, ingested["settings"], "range_victim", source,
                                    build_sample=False)
        with ingested["database"].read_cursor() as con:
            assert registry.get_experiment(con, "range_victim").is_ready
        after = archive.read_manifest(ingested["settings"], "range_victim")
        assert after.as_dict() == before.as_dict()


# ------------------------------------------------------------ precision --


def test_float_sources_widen_without_a_notice(part):
    check = parquet_spec.validate(duckdb.connect(), part)
    assert (check.narrowed, check.notices, check.rows) == ([], [], 1000)


def test_double_sources_are_narrowed_to_the_schema_and_said_to_be(ingested, part, tmp_path):
    source = _variant(tmp_path, part, "double.parquet",
                      "* REPLACE (CAST(x AS DOUBLE) AS x, CAST(incoming_momentum_A AS DOUBLE) "
                      "AS incoming_momentum_A)")
    check = parquet_spec.validate(duckdb.connect(), source)
    assert check.narrowed == ["x", "incoming_momentum_A"]
    assert "6 × 10⁻⁸" in check.notices[0]
    with _experiment(ingested, "parquet_double", source) as result:
        assert result.ok, result.warnings
        assert any("narrowed" in w for w in result.warnings)
        new_part = archive.part_paths(ingested["settings"], "parquet_double")[0]
        assert _types(new_part) == _types(part), "the archive keeps the pinned FLOAT"


# ------------------------------------------------------- missing values --


def test_nan_in_the_undefined_separation_columns_is_read_as_null(part, tmp_path):
    source = _variant(
        tmp_path, part, "nan.parquet",
        "* REPLACE (CASE WHEN event_number = 0 THEN 'NaN'::REAL ELSE centroid_AB_distance END "
        "AS centroid_AB_distance)",
    )
    con = duckdb.connect()
    check = parquet_spec.validate(con, source)
    n_event0 = con.execute(
        f"SELECT count(*) FROM read_parquet('{part}') WHERE event_number = 0").fetchone()[0]
    assert check.nan_as_null == {"centroid_AB_distance": n_event0}
    assert any("read as undefined (NULL)" in n for n in check.notices)
    nulls, nans = con.execute(
        "SELECT count(*) FILTER (WHERE centroid_AB_distance IS NULL), "
        "count(*) FILTER (WHERE isnan(centroid_AB_distance)) "
        f"FROM ({parquet_spec.select_sql(source, 0, check)})"
    ).fetchone()
    assert (nulls, nans) == (n_event0, 0)


def test_nan_in_a_model_column_fails_verification_as_it_would_in_a_csv(ingested, part, tmp_path):
    source = _variant(
        tmp_path, part, "nan_model.parquet",
        "* REPLACE (CASE WHEN event_number = 0 THEN 'NaN'::REAL ELSE segmentation_absolute_pred "
        "END AS segmentation_absolute_pred)",
    )
    with _experiment(ingested, "parquet_nan_model", source) as result:
        assert not result.ok
        assert result.verification.checks["finite_model_columns"] == "FAIL"


def test_a_real_file_with_nan_for_undefined_centroids_matches_its_csv(ingested, tmp_path):
    """pandas-style NaN where the CSV has empty fields: the same experiment results."""
    if not FIXTURE_CSV.is_file():
        pytest.skip(f"real-data fixture not present at {FIXTURE_CSV}")
    with _experiment(ingested, "fixture_csv", FIXTURE_CSV) as csv_result:
        assert csv_result.ok
        fixture_part = archive.part_paths(ingested["settings"], "fixture_csv")[0]
        with_nan = _variant(
            tmp_path, fixture_part, "fixture_nan.parquet",
            "* REPLACE (" + ", ".join(
                f"coalesce({quote(c)}, 'NaN'::REAL) AS {quote(c)}" for c in NULLABLE_COLUMNS
            ) + ")",
        )
        with _experiment(ingested, "fixture_parquet", with_nan) as parquet_result:
            assert parquet_result.ok, parquet_result.warnings
            assert sum(parquet_result.record.ingest_report["source"]["nan_as_null"].values()) > 0
            with ingested["database"].read_cursor() as con:
                for table in (naming.proj_table, naming.event_table):
                    assert _differs(con, table("fixture_csv"), table("fixture_parquet")) == 0


# ----------------------------------------------------- reading the file --


def test_the_row_count_comes_from_the_footer_across_row_groups(part, tmp_path):
    """Summing ``parquet_metadata`` would count every column of every group."""
    source = tmp_path / "groups.parquet"
    con = duckdb.connect()
    # DuckDB writes no row group below its 2048-row vector, so repeat the part.
    con.execute(
        f"COPY (SELECT p.* FROM read_parquet('{part}') p, range(6)) TO '{source}' "
        "(FORMAT parquet, ROW_GROUP_SIZE 2048)"
    )
    groups = con.execute(
        f"SELECT num_row_groups FROM parquet_file_metadata('{source}')").fetchone()[0]
    assert groups >= 2
    assert formats.count_rows(con, source, formats.PARQUET) == 6000


def test_the_format_is_read_from_the_content_not_the_name(part, tmp_path):
    named_csv = tmp_path / "actually_parquet.csv"
    shutil.copyfile(part, named_csv)
    assert formats.detect_format(named_csv) == formats.PARQUET

    truncated = tmp_path / "copying.parquet"
    truncated.write_bytes(part.read_bytes()[: part.stat().st_size // 2])
    with pytest.raises(IngestError, match="no footer"):
        formats.detect_format(truncated)

    packed = tmp_path / "packed.csv"
    packed.write_bytes(gzip.compress(SEED_CSV.read_bytes()[:2048]))
    with pytest.raises(IngestError, match="gzip"):
        formats.detect_format(packed)

    text = tmp_path / "text.parquet"
    shutil.copyfile(SEED_CSV, text)
    with pytest.raises(IngestError, match="not a Parquet file"):
        formats.detect_format(text)

    assert formats.detect_format(SEED_CSV) == formats.CSV


# ------------------------------------------------------------------- API --


def _parquet_bytes(tmp_path: Path) -> bytes:
    from calosrv.ingest import csv_spec

    out = tmp_path / "upload.parquet"
    duckdb.connect().execute(
        f"COPY (SELECT * FROM {csv_spec.read_csv_expression(SEED_CSV)}) TO '{out}' "
        "(FORMAT parquet)"
    )
    return out.read_bytes()


def test_a_parquet_upload_becomes_an_experiment(client, tmp_path):
    import time

    response = client.post(
        "/api/upload",
        files={"file": ("demo.parquet", _parquet_bytes(tmp_path), "application/vnd.apache.parquet")},
        data={"table_name": "parquet_upload", "mode": "create_new"},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job"]["job_id"]
    for _ in range(120):
        job = client.get(f"/api/upload/{job_id}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    assert job["result"]["source"]["format"] == "parquet"
    names = {e["table_name"]: e["status"] for e in client.get("/api/experiments").json()["experiments"]}
    assert names["parquet_upload"] == "ready"


def test_a_compressed_upload_is_refused_before_it_is_queued(client):
    response = client.post(
        "/api/upload",
        files={"file": ("demo.csv", gzip.compress(SEED_CSV.read_bytes()[:4096]), "text/csv")},
        data={"table_name": "gzipped_upload", "mode": "create_new"},
    )
    assert response.status_code == 400
    assert "gzip" in response.json()["detail"]


def test_upload_info_lists_both_formats_and_their_headroom(client):
    body = client.get("/api/upload-info").json()
    assert body["formats"] == ["csv", "parquet"]
    assert body["headroom_factors"]["parquet"] > body["local_headroom_factors"]["parquet"]
    assert "Parquet" in body["warning"] and "no resume" in body["warning"]
