# Stage 1: the data download. A small image of its own (the standard library
# and huggingface_hub), run by docker compose before the dashboard starts; it
# writes ./ingest and ./xgboost_models and exits.
FROM python:3.11-slim AS hf-sync

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/hf-home \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_XET_CHUNK_CACHE_SIZE_BYTES=0 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

RUN pip install "huggingface_hub==2.3.0"

COPY deploy/hf_sync.py /opt/hf_sync.py

WORKDIR /sync
CMD ["python", "/opt/hf_sync.py"]

# Stage 2: the dashboard. Last, so a plain `docker build .` builds it.
FROM python:3.11-slim AS app

# curl is used by the container HEALTHCHECK only; nothing in the app shells out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer caches across source edits. The XGBoost
# model analysis (calosrv/modelruns) needs xgboost and scikit-learn; the CPU
# wheel, because the plain xgboost wheel carries a 1.1 GB NCCL payload the
# service never uses. The models are read from the read-only mount,
# /app/xgboost_models, unless CALOSRV_MODEL_DIR names another folder.
COPY pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip \
    && pip install \
        "fastapi>=0.115,<1" \
        "uvicorn[standard]>=0.32,<1" \
        "duckdb==1.5.5" \
        "numpy>=1.26,<3" \
        "pandas>=2.0,<3" \
        "python-multipart>=0.0.12" \
        "xgboost-cpu==3.2.0" \
        "scikit-learn>=1.5,<2"

COPY calosrv /app/calosrv

# Seed file for the baseline experiment. Copied into the image (142 KB) so a
# first boot with an empty ./data volume still produces a populated dashboard.
COPY hits_all_models_dummy.parquet /app/seed/hits_all_models_dummy.parquet

# /app/data is the docker-compose volume mount point: DuckDB file, CSV staging
# area, DuckDB's temp spill directory and the Parquet archive all live here.
RUN mkdir -p /app/data/staging /app/data/tmp /app/data/archive

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "calosrv"]
