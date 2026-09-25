FROM python:3.11-slim

# curl is used by the container HEALTHCHECK only; nothing in the app shells out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer caches across source edits.
COPY pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip \
    && pip install \
        "fastapi>=0.115,<1" \
        "uvicorn[standard]>=0.32,<1" \
        "duckdb==1.5.5" \
        "numpy>=1.26,<3" \
        "pandas>=2.0,<3" \
        "python-multipart>=0.0.12"

COPY calosrv /app/calosrv

# Seed CSV for the baseline experiment. Copied into the image (1 MB) so a
# first boot with an empty ./data volume still produces a populated dashboard.
COPY hits_all_models_dummy.csv /app/seed/hits_all_models_dummy.csv

# /app/data is the docker-compose volume mount point: DuckDB file, CSV staging
# area, DuckDB's temp spill directory and the Parquet archive all live here.
RUN mkdir -p /app/data/staging /app/data/tmp /app/data/archive

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "calosrv"]
