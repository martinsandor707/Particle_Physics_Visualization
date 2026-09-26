"""Registry migration, retirement of the v37 schema, and the storage guard.

These run against throwaway in-memory databases and fake mount tables, so they
need no ingested data.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import duckdb
import pytest

from calosrv.config import load_settings, resolve_threads
from calosrv.db import bootstrap, registry
from calosrv.db.ddl import REGISTRY_SCHEMA
from calosrv.db.settings import apply_session_settings
from calosrv.db.storage_guard import assert_disk_backed, backing_fs
from calosrv.errors import StorageConfigError

#: The registry as the canonical-frame release created it: the first 40 columns.
LEGACY_REGISTRY = (
    'CREATE TABLE "experiment" (\n    '
    + ",\n    ".join(f"{n} {t}" for n, t in REGISTRY_SCHEMA[:40])
    + "\n);"
)


def _legacy_database() -> duckdb.DuckDBPyConnection:
    """A database as the v37 release left it: old registry, v37 tables, one ready row."""
    con = duckdb.connect()
    con.execute(LEGACY_REGISTRY)
    for table in ("hit_v37", "proj_v37", "event_v37", "hit_experiment_baseline",
                  "proj_experiment_baseline", "event_experiment_baseline"):
        con.execute(f'CREATE TABLE "{table}" (event_number INTEGER, ge REAL)')
    for name in ("v37", "experiment_baseline"):
        con.execute(
            'INSERT INTO "experiment" (table_name, display_name, status, n_hits) VALUES (?, ?, ?, ?)',
            [name, name, "ready", 1000],
        )
    return con


def test_an_old_registry_gains_the_new_columns():
    con = _legacy_database()
    registry.ensure_registry(con)
    columns = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'experiment'"
    ).fetchall()}
    assert {n for n, _ in REGISTRY_SCHEMA} <= columns
    record = registry.get_experiment(con, "v37")
    assert record is not None and record.schema_name is None


def test_a_v37_experiment_is_marked_unsupported_and_never_read():
    con = _legacy_database()
    ready = bootstrap.bootstrap(con)
    assert ready == []
    record = registry.get_experiment(con, "v37")
    assert record.status == registry.STATUS_FAILED
    assert record.error == bootstrap.UNSUPPORTED_V37_ERROR
    # Idempotent: a second boot does not rewrite the row.
    before = record.updated_at
    bootstrap.bootstrap(con)
    assert registry.get_experiment(con, "v37").updated_at == before


def test_a_v37_experiment_can_still_be_deleted_with_all_its_tables():
    con = _legacy_database()
    bootstrap.bootstrap(con)
    bootstrap.drop_experiment(con, "v37")
    tables = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables").fetchall()}
    assert not {"hit_v37", "proj_v37", "event_v37"} & tables
    assert registry.get_experiment(con, "v37") is None


def test_only_the_demonstration_experiment_is_replaced_automatically():
    con = _legacy_database()
    bootstrap.bootstrap(con)
    assert bootstrap.retire_unsupported(con, "experiment_baseline") is True
    assert registry.get_experiment(con, "experiment_baseline") is None
    assert registry.get_experiment(con, "v37") is not None, "user data must survive"
    assert bootstrap.retire_unsupported(con, "experiment_baseline") is False


def test_a_named_upsert_round_trips_every_new_field():
    con = duckdb.connect()
    registry.ensure_registry(con)
    record = registry.ExperimentRecord(
        table_name="roundtrip", status=registry.STATUS_READY,
        schema_name="hits_all_models", schema_version=1,
        archive_dir="archive/roundtrip", archive_parts=2, archive_rows=24_161_893,
        archive_bytes=123, n_cells=10, n_split_cells=3, n_ab_rows=1,
        ingest_report={"timings": [{"stage": "archive", "seconds": 1.5}]},
    )
    registry.upsert(con, record)
    back = registry.get_experiment(con, "roundtrip")
    for field in ("schema_name", "schema_version", "archive_dir", "archive_parts",
                  "archive_rows", "archive_bytes", "n_cells", "n_split_cells", "n_ab_rows",
                  "ingest_report"):
        assert getattr(back, field) == getattr(record, field), field


# ---------------------------------------------------------- storage guard --

MOUNTINFO = """\
22 1 0:21 / / rw,relatime - btrfs /dev/nvme0n1p2 rw
30 22 0:26 / /tmp rw,nosuid - tmpfs tmpfs rw,size=16G
31 22 0:27 / /home rw,relatime - btrfs /dev/nvme0n1p2 rw
32 22 252:0 / /swapdir rw - ext4 /dev/zram1 rw
"""


@pytest.mark.parametrize(
    ("path", "fstype", "ram"),
    [
        ("/tmp/calosrv/data", "tmpfs", True),
        ("/home/me/project/data/dev", "btrfs", False),
        ("/swapdir/x", "ext4", True),  # a filesystem on a zram device is RAM too
        ("/var/lib/data", "btrfs", False),
    ],
)
def test_the_backing_filesystem_is_found_by_longest_mount_prefix(path, fstype, ram):
    mount = backing_fs(Path(path), MOUNTINFO)
    assert mount.fstype == fstype
    assert mount.ram_backed is ram


def test_a_tmpfs_mounted_over_a_disk_path_is_seen():
    """mountinfo lists the shadowed mount first; the one mounted over it is what is used."""
    overmount = MOUNTINFO + "40 31 8:1 /data /app/data rw - ext4 /dev/sda1 rw\n" \
        "41 40 0:50 / /app/data rw - tmpfs tmpfs rw\n"
    mount = backing_fs(Path("/app/data/tmp"), overmount)
    assert mount.fstype == "tmpfs" and mount.ram_backed


def test_ram_backed_storage_is_refused_unless_explicitly_allowed():
    roles = {"temp_directory": Path("/tmp/calosrv/tmp"), "database": Path("/home/me/data")}
    with pytest.raises(StorageConfigError, match="temp_directory at /tmp/calosrv/tmp is on tmpfs"):
        assert_disk_backed(roles, mountinfo_text=MOUNTINFO)
    found = assert_disk_backed(roles, allow=True, mountinfo_text=MOUNTINFO)
    assert found["database"].fstype == "btrfs"


# ------------------------------------------------------ session settings --


@pytest.mark.parametrize("memory", [1, 2, 4, 10, 16, 64, 100])
def test_threads_never_exceed_the_memory_ceiling_in_gb(memory):
    threads = resolve_threads(memory, 24)
    assert 2 <= threads <= max(2, memory)


def test_the_session_settings_take_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("CALOSRV_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DUCKDB_MEMORY_GB", "2")
    settings = dataclasses.replace(load_settings())
    con = duckdb.connect()
    apply_session_settings(con, settings)
    values = dict(con.execute(
        "SELECT name, value FROM duckdb_settings() WHERE name IN "
        "('preserve_insertion_order', 'allocator_background_threads', 'threads')"
    ).fetchall())
    assert values["preserve_insertion_order"] == "false"
    assert values["allocator_background_threads"] == "true"
    assert int(values["threads"]) == settings.threads <= 2
