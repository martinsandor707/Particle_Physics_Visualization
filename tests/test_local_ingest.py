"""Path confinement for server-side ingestion.

An endpoint that opens a server-side path by name is a file-disclosure
primitive unless it is constrained, so the containment check gets its own tests
rather than being covered incidentally.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from calosrv.config import load_settings
from calosrv.errors import IngestError, NotFoundError, ValidationError
from calosrv.ingest import local


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    """A settings object whose ingest root is a temporary directory."""
    root = tmp_path / "host"
    (root / "nested").mkdir(parents=True)
    (root / "good.csv").write_text("a,b\n1,2\n")
    (root / "nested" / "deep.csv").write_text("a,b\n1,2\n")
    (root / "notes.md").write_text("not a dataset")

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.csv"
    secret.write_text("classified\n")

    monkeypatch.setenv("CALOSRV_LOCAL_INGEST_DIR", str(root))
    monkeypatch.setenv("CALOSRV_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    return settings, root, secret


def test_file_inside_the_root_resolves(rooted):
    settings, root, _ = rooted
    assert local.resolve_local_path(settings, str(root / "good.csv")) == root / "good.csv"


def test_relative_paths_resolve_against_the_root(rooted):
    settings, root, _ = rooted
    assert local.resolve_local_path(settings, "nested/deep.csv") == root / "nested" / "deep.csv"


def test_absolute_path_outside_the_root_is_refused(rooted):
    settings, _, secret = rooted
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, str(secret))


def test_dot_dot_traversal_is_refused(rooted):
    """``..`` must be collapsed before the containment check, not after."""
    settings, _, _ = rooted
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, "../outside/secret.csv")
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, "nested/../../outside/secret.csv")


def test_symlink_escape_is_refused(rooted):
    """Resolution must follow symlinks, or a link defeats the whole check."""
    settings, root, secret = rooted
    link = root / "link.csv"
    try:
        link.symlink_to(secret)
    except OSError:  # pragma: no cover - unprivileged Windows
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, str(link))


def test_missing_file_is_a_clear_404(rooted):
    settings, _, _ = rooted
    with pytest.raises(NotFoundError):
        local.resolve_local_path(settings, "absent.csv")


def test_non_csv_is_refused(rooted):
    settings, _, _ = rooted
    with pytest.raises(IngestError):
        local.resolve_local_path(settings, "notes.md")


def test_directory_is_refused(rooted):
    settings, _, _ = rooted
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, "nested")


def test_listing_hides_vendor_directories(rooted):
    """A repository checkout is full of CSVs nobody wants to ingest."""
    settings, root, _ = rooted
    noise = root / ".venv" / "lib" / "site-packages"
    noise.mkdir(parents=True)
    (noise / "fixture.csv").write_text("x\n1\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "cached.csv").write_text("x\n1\n")

    listed = {entry["relative"] for entry in local.list_local_files(settings)}
    assert "good.csv" in listed
    assert "nested/deep.csv" in listed
    assert not any("site-packages" in name or "__pycache__" in name for name in listed)


def test_disabled_when_no_root_is_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("CALOSRV_LOCAL_INGEST_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("CALOSRV_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    assert settings.local_ingest_dir is None
    assert local.list_local_files(settings) == []
    with pytest.raises(ValidationError):
        local.resolve_local_path(settings, "anything.csv")
