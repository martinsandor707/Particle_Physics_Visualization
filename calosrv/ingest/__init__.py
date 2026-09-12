"""Dataset ingestion: CSV on disk to queryable DuckDB tables.

The pipeline is four stages, each in its own module so a failure can be pinned
to a stage:

``load``          stream the CSV into the archival ``hit_<name>`` table
``lattice_fit``   measure the detector lattice from the loaded data
``derive_proj``   build the narrow ``proj_<name>`` hot-path table
``derive_events`` build the ``event_<name>`` sufficient-statistics table

``verify`` then asserts the result against the source file, and ``jobs``
sequences the whole thing on a background worker so a multi-minute ingest never
blocks an HTTP request.
"""

from __future__ import annotations

from .jobs import IngestJob, JobStore, get_job_store

__all__ = ["IngestJob", "JobStore", "get_job_store"]
