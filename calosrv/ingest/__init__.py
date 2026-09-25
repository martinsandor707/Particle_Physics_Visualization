"""Dataset ingestion: CSV on disk to a Parquet archive and queryable DuckDB tables.

One pipeline (``pipeline.run_ingest``), each stage in its own module so a
failure can be pinned to a stage:

``load``          validate the CSV and write it once into the Parquet archive
``lattice_fit``   measure the laboratory lattice and the per-shower frame extents
``derive_proj``   build the ``proj_<name>`` hot-path table from the archive
``derive_events`` build the ``event_<name>`` sufficient-statistics table

``verify`` then asserts the result against the source file and the data
contracts the frames rely on, and ``jobs`` runs the pipeline on a background
worker so a multi-minute ingest never blocks an HTTP request.
"""

from __future__ import annotations

from .jobs import IngestJob, JobStore, get_job_store

__all__ = ["IngestJob", "JobStore", "get_job_store"]
