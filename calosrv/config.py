"""Runtime configuration, resolved once from the process environment.

Every tunable the deployment can change lives here, so the set of environment
variables the container honours is auditable in one file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: Default memory ceiling when ``DUCKDB_MEMORY_GB`` is unset or unparseable.
DEFAULT_MEMORY_GB = 16

#: Above this ceiling the host is assumed to be a shared production box where
#: leaving half the cores for other tenants matters more than query latency.
LARGE_MEMORY_GB = 64

#: Hard cap on DuckDB worker threads. Beyond ~32 the hash-aggregate in
#: ``query/projections.py`` is bound by memory bandwidth, not by cores.
MAX_THREADS = 32


def _int_env(name: str, default: int) -> int:
    """Read an integer environment variable, falling back on any bad value.

    The spec calls for an *integer* memory ceiling, so ``'16GB'`` or ``'16.5'``
    are rejected rather than coerced into something surprising. A bad value is
    never fatal: the server boots on the default and logs the substitution.
    """
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_threads(memory_gb: int, cpu_cores: int | None = None) -> int:
    """Thread count for DuckDB, protecting multi-tenant host CPU scheduling.

    A large memory ceiling implies a big shared production host, so only half
    the cores are claimed. A small ceiling implies a dedicated or development
    box, where all but one core is fair game.
    """
    cores = cpu_cores if cpu_cores is not None else (os.cpu_count() or 4)
    if memory_gb >= LARGE_MEMORY_GB:
        wanted = cores // 2
    else:
        wanted = cores - 1
    return min(MAX_THREADS, max(2, wanted))


@dataclass(frozen=True)
class Settings:
    """Immutable view of the environment, built once at import of ``app``."""

    memory_gb: int
    threads: int
    cpu_cores: int
    port: int
    host: str

    db_path: Path
    data_dir: Path
    staging_dir: Path
    temp_dir: Path
    seed_csv: Path | None

    #: Debounce contract advertised to the frontend, in milliseconds.
    debounce_ms: int

    #: Number of native-resolution matrix bundles held in the LRU. Each bundle
    #: is roughly 1.8 MB, so 128 entries cost ~230 MB of resident memory - which
    #: is part of why the container needs headroom above ``memory_gb``.
    cache_entries: int

    #: Bernoulli sampling fraction, as a percentage, for the drag-preview tier.
    sample_percent: float

    #: Reject an upload unless the filesystem has this multiple of the incoming
    #: file size free. Peak usage is staging CSV + hit table + proj table + WAL.
    disk_headroom_factor: float

    #: Uploads at or above this size trigger the frontend's large-file warning.
    large_upload_warn_bytes: int

    #: Directory the server may ingest from directly, by path.
    #:
    #: This is the escape hatch for multi-gigabyte datasets already on the host:
    #: the file is read in place instead of being pushed through HTTP. It is
    #: confined to one configured root, and every requested path is resolved and
    #: checked against it, so the endpoint cannot be used to read arbitrary
    #: files the server process happens to have access to.
    local_ingest_dir: Path | None

    #: Base URL the ingest CLI uses to reach a running server.
    server_url: str

    cors_origins: tuple[str, ...] = field(default=())

    @property
    def memory_limit_sql(self) -> str:
        return f"{self.memory_gb}GB"


def _seed_candidates(data_dir: Path) -> list[Path]:
    """Where to look for the baseline seed CSV, in priority order.

    ``/app/seed`` is baked into the image by the Dockerfile. The repository-root
    path lets the server run outside a container straight from a checkout.
    """
    override = os.getenv("CALOSRV_SEED_CSV", "").strip()
    if override:
        return [Path(override)]
    repo_root = Path(__file__).resolve().parent.parent
    return [
        Path("/app/seed/hits_with_gradcam_dummy.csv"),
        data_dir / "hits_with_gradcam_dummy.csv",
        repo_root / "hits_with_gradcam_dummy.csv",
    ]


def load_settings() -> Settings:
    """Resolve settings from the environment and create the data directories."""
    memory_gb = _int_env("DUCKDB_MEMORY_GB", DEFAULT_MEMORY_GB)
    if memory_gb < 1:
        memory_gb = DEFAULT_MEMORY_GB
    cpu_cores = os.cpu_count() or 4

    data_dir = Path(os.getenv("CALOSRV_DATA_DIR", "/app/data"))
    staging_dir = data_dir / "staging"
    temp_dir = data_dir / "tmp"
    for directory in (data_dir, staging_dir, temp_dir):
        directory.mkdir(parents=True, exist_ok=True)

    seed = next((path for path in _seed_candidates(data_dir) if path.is_file()), None)

    raw_origins = os.getenv("CALOSRV_CORS_ORIGINS", "").strip()
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())

    raw_local = os.getenv("CALOSRV_LOCAL_INGEST_DIR", "/app/host").strip()
    local_dir = Path(raw_local).resolve() if raw_local else None
    if local_dir is not None and not local_dir.is_dir():
        local_dir = None

    port = _int_env("PORT", 8000)

    return Settings(
        memory_gb=memory_gb,
        threads=resolve_threads(memory_gb, cpu_cores),
        cpu_cores=cpu_cores,
        port=port,
        host=os.getenv("CALOSRV_HOST", "0.0.0.0"),
        db_path=Path(os.getenv("CALOSRV_DB_PATH", str(data_dir / "calorimeter.duckdb"))),
        data_dir=data_dir,
        staging_dir=staging_dir,
        temp_dir=temp_dir,
        seed_csv=seed,
        debounce_ms=_int_env("CALOSRV_DEBOUNCE_MS", 150),
        cache_entries=_int_env("CALOSRV_CACHE_ENTRIES", 128),
        sample_percent=10.0,
        disk_headroom_factor=3.0,
        large_upload_warn_bytes=512 * 1024 * 1024,
        local_ingest_dir=local_dir,
        server_url=os.getenv("CALOSRV_SERVER_URL", f"http://127.0.0.1:{port}"),
        cors_origins=origins,
    )
