"""The files a fresh clone runs on: the README's Quick start, pinned at the source.

A physicist following the Quick start clones the repository, downloads the data
from the project's Hugging Face dataset and starts ``docker compose``. Every
property that path depends on is checked here without Docker or a network: that
the image builds from tracked files only, that the memory settings the README
names exist with the values it quotes, that the default experiment is the one
the drop folder creates from the downloaded dataset, that the download fetches
the data and the models into the folders they are read from, and that the line
endings Windows would otherwise convert are pinned.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from calosrv.db import naming

ROOT = Path(__file__).resolve().parent.parent

#: The Quick start's data download, as `hf download` reads it: the dataset and
#: one glob per --include, each matched against the dataset's paths.
DATASET = "martinsandor707/particles_combined_all_models"
INCLUDE = ("ingest/*.parquet", "xgboost_models/*.json")
DOWNLOAD = (f"hf download {DATASET} --repo-type dataset "
            + " ".join(f'--include "{pattern}"' for pattern in INCLUDE) + " --local-dir .")


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _tracked() -> set[str]:
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    done = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                          capture_output=True, text=True, cwd=ROOT, timeout=60, check=False)
    if done.returncode != 0:
        pytest.skip("not a git checkout")
    return set(done.stdout.split())


def _env(text: str) -> dict[str, str]:
    pairs = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            pairs[key.strip()] = value.strip()
    return pairs


def _gigabytes(size: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([gm])", size.strip().lower())
    assert match, size
    value = float(match.group(1))
    return value if match.group(2) == "g" else value / 1024.0


# ------------------------------------------------------------ the image --


def test_the_image_builds_from_files_git_tracks():
    """`COPY` of an untracked file fails the build on a fresh clone, as the seed file once did."""
    tracked = _tracked()
    sources = []
    for line in _read("Dockerfile").splitlines():
        parts = line.split()
        if parts[:1] == ["COPY"] and not any(p.startswith("--from") for p in parts):
            sources.extend(parts[1:-1])
    assert "hits_all_models_dummy.parquet" in sources
    for source in sources:
        if source.endswith("/") or (ROOT / source).is_dir():
            assert any(path.startswith(source.rstrip("/") + "/") for path in tracked), source
        else:
            assert source in tracked, f"the Dockerfile copies {source}, which a fresh clone does not have"
    ignore = _read(".dockerignore")
    assert "!hits_all_models_dummy.parquet" in ignore


# ------------------------------------------------- memory, and the profile --


def test_compose_takes_its_memory_from_the_environment_with_safe_defaults():
    compose = _read("docker-compose.yml")
    assert "- DUCKDB_MEMORY_GB=${DUCKDB_MEMORY_GB:-16}" in compose
    assert "mem_limit: ${CONTAINER_MEMORY_LIMIT:-20g}" in compose
    assert "memswap_limit: ${CONTAINER_MEMORY_LIMIT:-20g}" in compose, "no swap on top of the limit"


@pytest.mark.parametrize("profile", [None, "laptop.env"])
def test_every_profile_leaves_headroom_above_duckdbs_ceiling(profile):
    """DuckDB's limit bounds its buffer manager only; the container needs room for the rest."""
    values = {"DUCKDB_MEMORY_GB": "16", "CONTAINER_MEMORY_LIMIT": "20g"}
    if profile:
        values.update(_env(_read(profile)))
    duckdb_gb = float(values["DUCKDB_MEMORY_GB"])
    container_gb = _gigabytes(values["CONTAINER_MEMORY_LIMIT"])
    assert container_gb - duckdb_gb >= 3.0, values


def test_the_laptop_profile_is_what_the_readme_quotes():
    values = _env(_read("laptop.env"))
    assert set(values) == {"DUCKDB_MEMORY_GB", "CONTAINER_MEMORY_LIMIT"}
    assert _gigabytes(values["CONTAINER_MEMORY_LIMIT"]) <= 8.0, "fits a Docker allowance of 8 GB"
    readme = _read("README.md")
    quick = readme[readme.index("## Quick start"):readme.index("## Configuration")]
    assert "docker compose --env-file laptop.env up --build" in quick
    assert f"DUCKDB_MEMORY_GB={values['DUCKDB_MEMORY_GB']}" in quick
    assert f"CONTAINER_MEMORY_LIMIT={values['CONTAINER_MEMORY_LIMIT']}" in quick


# ------------------------------------------------- the data and the view --


def _downloaded(path: str) -> bool:
    """Whether the download fetches ``path``: `hf` matches case-sensitively, `*` crossing `/`."""
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in INCLUDE)


def test_the_default_experiment_is_the_one_the_downloaded_dataset_becomes():
    """The datasets arrive by the download, not the clone, into the folder the drop folder reads."""
    tracked = _tracked()
    assert "ingest/README.md" in tracked
    assert not [path for path in tracked if path.startswith("ingest/") and path != "ingest/README.md"]
    assert _downloaded("ingest/hits_all_models.parquet")
    compose = _read("docker-compose.yml")
    default = re.search(r"- CALOSRV_DEFAULT_DATASET=(\S+)", compose).group(1)
    assert default == naming.derive_experiment_name("hits_all_models")
    assert "- CALOSRV_AUTO_INGEST_DIR=/app/host/ingest" in compose and "- .:/app/host:ro" in compose


def test_the_download_covers_the_models_and_leaves_the_tracked_note_alone():
    """The dataset mirrors both folders; its copy of the drop folder's note may lag the clone's."""
    models = sorted(path for path in _tracked() if path.startswith("xgboost_models/"))
    assert models and all(_downloaded(path) for path in models), "every model the service reads"
    assert not _downloaded("ingest/README.md")


def test_files_docker_reads_keep_their_line_endings_on_windows():
    attributes = _read(".gitattributes")
    for rule in ("hits_all_models_dummy.parquet -text", "Dockerfile text eol=lf",
                 "docker-compose.yml text eol=lf", "*.env text eol=lf"):
        assert rule in attributes, rule


# ------------------------------------------------- the README's commands --


def test_the_quick_start_gives_the_commands_in_order():
    readme = _read("README.md")
    quick = readme[readme.index("## Quick start"):readme.index("## Configuration")]
    # Python and pip on macOS and Linux, then on Windows, then uv on any system:
    # the same download each time, with the version of `hf` it was tested with.
    commands = [
        "git clone https://github.com/martinsandor707/Particle_Physics_Visualization.git",
        "cd Particle_Physics_Visualization",
        "python3 -m venv .venv",
        ".venv/bin/python -m pip install huggingface_hub==2.3.0",
        ".venv/bin/" + DOWNLOAD,
        "py -m venv .venv",
        ".venv\\Scripts\\python -m pip install huggingface_hub==2.3.0",
        ".venv\\Scripts\\" + DOWNLOAD,
        "uv run --only-group dev " + DOWNLOAD,
        "docker compose --env-file laptop.env up --build",
    ]
    positions = [quick.index(command) for command in commands]
    assert positions == sorted(positions), "the commands appear in the order they are run"
    update = quick[quick.index("### Every day"):quick.index("### If something goes wrong")]
    assert update.index("git pull") < update.index(DOWNLOAD) < update.index("up --build")
    assert "hf auth" not in quick, "the dataset is public: the download needs no sign-in"
    assert "http://localhost:8000" in quick
    assert "−" not in "".join(commands), "commands keep ASCII hyphens"


def test_pip_and_uv_install_the_same_hf():
    """pip takes the version from the README, uv from the lock: the two must agree.

    uv installs the `dev` group alone, never the project, whose xgboost-cpu has no macOS wheel.
    """
    group = tomllib.loads(_read("pyproject.toml"))["dependency-groups"]["dev"]
    assert any(re.match(r"huggingface-hub\b", requirement) for requirement in group)
    lock = tomllib.loads(_read("uv.lock"))
    locked = next(package["version"] for package in lock["package"]
                  if package["name"] == "huggingface-hub")
    readme = _read("README.md")
    quick = readme[readme.index("## Quick start"):readme.index("## Configuration")]
    assert set(re.findall(r"huggingface_hub==([\w.]+)", quick)) == {locked}
